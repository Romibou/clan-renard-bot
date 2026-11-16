from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")

SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

# Pièces qu'un membre peut donner au total par jour (heure de Paris).
# Limite les abus avec des comptes secondaires.
DAILY_GIFT_LIMIT = 500

MAXIMUM_REASON_LENGTH = 100


class GiftError(Exception):
    """Erreur affichable au membre."""


@dataclass(frozen=True, slots=True)
class GiftResult:
    amount: int
    giver_wallet: int
    given_today: int


def format_coins(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def paris_midnight(
    moment: datetime | None = None,
) -> datetime:
    current = (moment or datetime.now(PARIS_TIMEZONE)).astimezone(
        PARIS_TIMEZONE
    )

    return current.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def check_gift_allowed(
    *,
    amount: int,
    wallet: int,
    given_today: int,
    limit: int = DAILY_GIFT_LIMIT,
) -> None:
    if amount <= 0:
        raise GiftError("Le montant doit être supérieur à 0.")

    remaining = max(0, limit - given_today)

    if amount > remaining:
        if remaining == 0:
            raise GiftError(
                f"Tu as déjà donné **{format_coins(limit)} pièces** "
                "aujourd'hui, la limite quotidienne. "
                "Réessaie demain."
            )

        raise GiftError(
            f"Tu peux encore donner **{format_coins(remaining)} "
            f"pièces** aujourd'hui (limite de "
            f"{format_coins(limit)} par jour)."
        )

    if amount > wallet:
        raise GiftError(
            f"Tu n'as que **{format_coins(wallet)} pièces**."
        )


class GiftCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError(
                "Le gestionnaire PostgreSQL est indisponible."
            )

        return database.require_pool()

    async def transfer_coins(
        self,
        *,
        guild_id: int,
        giver_id: int,
        receiver_id: int,
        amount: int,
        reason: str,
    ) -> GiftResult:
        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                # Verrous dans un ordre fixe : deux dons croisés
                # simultanés ne peuvent pas se bloquer mutuellement.
                for user_id in sorted((giver_id, receiver_id)):
                    await connection.execute(
                        """
                        SELECT pg_advisory_xact_lock(
                            hashtextextended($1, 0)
                        )
                        """,
                        f"progression:{guild_id}:{user_id}",
                    )

                await connection.execute(
                    """
                    INSERT INTO progression_members (
                        guild_id,
                        user_id
                    )
                    SELECT $1, UNNEST($2::BIGINT[])
                    ON CONFLICT (guild_id, user_id)
                    DO NOTHING
                    """,
                    guild_id,
                    [giver_id, receiver_id],
                )

                wallet = await connection.fetchval(
                    """
                    SELECT wallet
                    FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild_id,
                    giver_id,
                )

                given_today = await connection.fetchval(
                    """
                    SELECT COALESCE(SUM(-amount), 0)
                    FROM progression_transactions
                    WHERE guild_id = $1
                      AND user_id = $2
                      AND transaction_type = 'gift_sent'
                      AND created_at >= $3
                    """,
                    guild_id,
                    giver_id,
                    paris_midnight(),
                )

                check_gift_allowed(
                    amount=amount,
                    wallet=int(wallet or 0),
                    given_today=int(given_today or 0),
                )

                new_wallet = await connection.fetchval(
                    """
                    UPDATE progression_members
                    SET
                        wallet = wallet - $3,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    RETURNING wallet
                    """,
                    guild_id,
                    giver_id,
                    amount,
                )

                # Un don n'est pas de l'argent « gagné » : le total
                # historique (lifetime_coins) du receveur ne bouge pas,
                # sinon les dons serviraient à valider des missions.
                await connection.execute(
                    """
                    UPDATE progression_members
                    SET
                        wallet = wallet + $3,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    receiver_id,
                    amount,
                )

                await connection.executemany(
                    """
                    INSERT INTO progression_transactions (
                        guild_id,
                        user_id,
                        actor_id,
                        amount,
                        transaction_type,
                        reason
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    [
                        (
                            guild_id,
                            giver_id,
                            giver_id,
                            -amount,
                            "gift_sent",
                            reason,
                        ),
                        (
                            guild_id,
                            receiver_id,
                            giver_id,
                            amount,
                            "gift_received",
                            reason,
                        ),
                    ],
                )

        return GiftResult(
            amount=amount,
            giver_wallet=int(new_wallet or 0),
            given_today=int(given_today or 0) + amount,
        )

    @app_commands.command(
        name="donner",
        description="Donne des pièces à un autre membre.",
    )
    @app_commands.rename(
        member="membre",
        amount="montant",
        reason="raison",
    )
    @app_commands.describe(
        member="Membre qui reçoit les pièces.",
        amount=(
            f"Nombre de pièces (au plus {DAILY_GIFT_LIMIT} par jour)."
        ),
        reason="Message facultatif affiché avec le don.",
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        10.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def donner(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, DAILY_GIFT_LIMIT],
        reason: app_commands.Range[
            str,
            1,
            MAXIMUM_REASON_LENGTH,
        ] | None = None,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Don impossible",
                    description="Tu ne peux pas te donner des pièces.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if member.bot:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Don impossible",
                    description="Les bots n'ont pas de portefeuille.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        cleaned_reason = (reason or "").strip()

        try:
            result = await self.transfer_coins(
                guild_id=guild.id,
                giver_id=interaction.user.id,
                receiver_id=member.id,
                amount=int(amount),
                reason=cleaned_reason or "Don entre membres",
            )
        except GiftError as error:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Don impossible",
                    description=str(error),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        description = (
            f"{interaction.user.mention} a donné "
            f"**{format_coins(result.amount)} pièces** "
            f"à {member.mention} !"
        )

        if cleaned_reason:
            description += f"\n\n💬 {cleaned_reason}"

        embed = discord.Embed(
            title="🎁 Don de pièces",
            description=description,
            color=SUCCESS_COLOR,
        )
        embed.set_footer(
            text=(
                f"Il te reste {format_coins(result.giver_wallet)} "
                f"pièces • Donné aujourd'hui : "
                f"{format_coins(result.given_today)}/"
                f"{format_coins(DAILY_GIFT_LIMIT)}"
            )
        )

        await interaction.followup.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                roles=False,
                users=[member],
            ),
        )


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(GiftCog(bot))
    LOGGER.info("Commande /donner chargée")
