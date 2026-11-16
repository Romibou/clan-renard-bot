"""
/drop : un administrateur fait apparaître une récompense dans un salon.
Les premiers membres à cliquer reçoivent l'XP et/ou les pièces annoncées.

Les montants peuvent être négatifs pour piéger les plus rapides : l'XP
et le portefeuille ne descendent jamais sous 0. L'option « mystere »
cache le contenu jusqu'au clic.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.extensions.rappel import parse_duration
from bot.shared.economy import apply_signed_change, refresh_level_roles

LOGGER = logging.getLogger(__name__)

DROP_COLOR = discord.Color.from_rgb(255, 196, 64)
TRAP_COLOR = discord.Color.from_rgb(220, 75, 85)
DONE_COLOR = discord.Color.from_rgb(120, 120, 135)

MAXIMUM_AMOUNT = 1_000_000
MAXIMUM_CLAIMS = 50
DEFAULT_DURATION = timedelta(minutes=10)
MAXIMUM_DURATION = timedelta(days=1)


def format_number(value: int) -> str:
    return f"{abs(int(value)):,}".replace(",", " ")


def describe_amounts(xp: int, coins: int) -> str:
    """« +500 XP et −200 pièces »."""
    parts = []

    if xp:
        parts.append(f"{'+' if xp > 0 else '−'}{format_number(xp)} XP")

    if coins:
        parts.append(
            f"{'+' if coins > 0 else '−'}{format_number(coins)} pièces"
        )

    return " et ".join(parts) if parts else "rien du tout"


def is_trap(xp: int, coins: int) -> bool:
    return xp < 0 or coins < 0


def build_drop_embed(
    record,
    claims: list[tuple[int, int, int]],
    *,
    finished: bool,
) -> discord.Embed:
    """claims : (user_id, xp réellement appliquée, pièces réellement appliquées)."""
    xp = int(record["xp"])
    coins = int(record["coins"])
    hidden = bool(record["hidden"])
    remaining = int(record["max_claims"]) - len(claims)
    trap = is_trap(xp, coins)

    if hidden and not finished:
        content = "❓ **Récompense mystère**… bonne ou mauvaise surprise ?"
    else:
        content = f"{'🪤' if trap else '🎁'} **{describe_amounts(xp, coins)}**"

    lines = []

    if record["note"]:
        lines.append(str(record["note"]))
        lines.append("")

    lines.append(content)

    if not finished:
        expires = int(record["expires_at"].timestamp())
        plural = "s" if remaining > 1 else ""
        lines += [
            "",
            f"⚡ Les **{remaining}** premier{plural} à cliquer l'emporte{'nt' if remaining > 1 else ''} !",
            f"⏰ Disparaît <t:{expires}:R>.",
        ]

    if claims:
        lines += ["", "**Récupéré par :**"]
        # Un drop mystère ne révèle les montants qu'une fois terminé.
        reveal = finished or not hidden
        lines += [
            (
                f"• <@{user_id}> ({describe_amounts(xp_delta, coins_delta)})"
                if reveal
                else f"• <@{user_id}>"
            )
            for user_id, xp_delta, coins_delta in claims[:20]
        ]

        if len(claims) > 20:
            lines.append(f"… et {len(claims) - 20} autre(s).")

    if finished:
        if not claims:
            lines += ["", "💨 Personne n'a été assez rapide, le drop a disparu."]
        elif trap and hidden:
            lines += ["", "😈 C'était un piège !"]

    if finished:
        title, color = "📦 Drop terminé", DONE_COLOR
    elif hidden:
        title, color = "📦 Un drop mystère est apparu !", DROP_COLOR
    else:
        title = "📦 Un drop est apparu !"
        color = TRAP_COLOR if trap else DROP_COLOR

    embed = discord.Embed(
        title=title,
        description="\n".join(lines),
        color=color,
    )
    embed.set_footer(text=f"Drop n°{record['id']} • Clan Renard")

    return embed


class ClaimDropButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"drop:claim:(?P<id>[0-9]+)",
):
    """Bouton persistant : fonctionne encore après un redémarrage."""

    def __init__(
        self,
        drop_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Récupérer" if not disabled else "Terminé",
                emoji="🎁",
                style=(
                    discord.ButtonStyle.success
                    if not disabled
                    else discord.ButtonStyle.secondary
                ),
                custom_id=f"drop:claim:{drop_id}",
                disabled=disabled,
            )
        )
        self.drop_id = drop_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> ClaimDropButton:
        return cls(int(match["id"]))

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        cog = interaction.client.get_cog("DropCog")

        if cog is None:
            await interaction.response.send_message(
                "❌ Le module des drops n'est pas chargé.",
                ephemeral=True,
            )
            return

        await cog.claim(interaction, self.drop_id)


def drop_view(drop_id: int, *, disabled: bool = False) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(ClaimDropButton(drop_id, disabled=disabled))

    return view


class DropCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS drops (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT,
                created_by BIGINT NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                coins INTEGER NOT NULL DEFAULT 0,
                max_claims SMALLINT NOT NULL
                    CHECK (max_claims BETWEEN 1 AND 50),
                hidden BOOLEAN NOT NULL DEFAULT FALSE,
                note VARCHAR(200),
                expires_at TIMESTAMPTZ NOT NULL,
                ended BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS drop_claims (
                drop_id BIGINT NOT NULL
                    REFERENCES drops(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                xp_delta INTEGER NOT NULL DEFAULT 0,
                coins_delta INTEGER NOT NULL DEFAULT 0,
                claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (drop_id, user_id)
            )
            """
        )

    async def cog_load(self) -> None:
        if not self.expire_loop.is_running():
            self.expire_loop.start()

    def cog_unload(self) -> None:
        self.expire_loop.cancel()

    async def get_claims(self, drop_id: int) -> list[tuple[int, int, int]]:
        records = await self.get_pool().fetch(
            """
            SELECT user_id, xp_delta, coins_delta
            FROM drop_claims
            WHERE drop_id = $1
            ORDER BY claimed_at
            """,
            drop_id,
        )

        return [
            (int(row["user_id"]), int(row["xp_delta"]), int(row["coins_delta"]))
            for row in records
        ]

    async def reserve_claim(self, drop_id: int, user_id: int):
        """
        Réserve une place pour ce membre. Le verrou sur la ligne du drop
        empêche de dépasser le nombre de places, même avec des clics
        simultanés. Retourne (drop, statut) avec statut parmi
        « ok », « already », « full », « ended ».
        """
        async with self.bot.database.transaction() as connection:  # type: ignore[attr-defined]
            record = await connection.fetchrow(
                "SELECT * FROM drops WHERE id = $1 FOR UPDATE",
                drop_id,
            )

            if (
                record is None
                or record["ended"]
                or record["expires_at"] <= datetime.now(timezone.utc)
            ):
                return record, "ended"

            already = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM drop_claims
                    WHERE drop_id = $1 AND user_id = $2
                )
                """,
                drop_id,
                user_id,
            )

            if already:
                return record, "already"

            count = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM drop_claims WHERE drop_id = $1",
                    drop_id,
                )
                or 0
            )

            if count >= int(record["max_claims"]):
                return record, "full"

            await connection.execute(
                "INSERT INTO drop_claims (drop_id, user_id) VALUES ($1, $2)",
                drop_id,
                user_id,
            )

            if count + 1 >= int(record["max_claims"]):
                await connection.execute(
                    "UPDATE drops SET ended = TRUE WHERE id = $1",
                    drop_id,
                )

            return record, "ok"

    async def claim(
        self,
        interaction: discord.Interaction,
        drop_id: int,
    ) -> None:
        if interaction.user.bot or interaction.guild is None:
            return

        record, status = await self.reserve_claim(drop_id, interaction.user.id)

        if status != "ok":
            messages = {
                "already": "Tu as déjà récupéré ce drop !",
                "full": "Trop tard, quelqu'un a été plus rapide ! 💨",
                "ended": "Ce drop a disparu. 💨",
            }
            await interaction.response.send_message(
                messages[status],
                ephemeral=True,
            )
            return

        xp = int(record["xp"])
        coins = int(record["coins"])

        try:
            result = await apply_signed_change(
                self.bot.database,  # type: ignore[attr-defined]
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                xp=xp,
                coins=coins,
                transaction_type="drop",
                reason=f"Drop n°{drop_id}",
            )
        except Exception:
            LOGGER.exception("Drop %s non versé à %s", drop_id, interaction.user.id)
            await interaction.response.send_message(
                "❌ La récompense n'a pas pu être versée. Préviens un administrateur.",
                ephemeral=True,
            )
            return

        await self.get_pool().execute(
            """
            UPDATE drop_claims
            SET xp_delta = $3, coins_delta = $4
            WHERE drop_id = $1 AND user_id = $2
            """,
            drop_id,
            interaction.user.id,
            result["xp_delta"],
            result["coins_delta"],
        )

        xp_delta = result["xp_delta"]
        coins_delta = result["coins_delta"]

        if is_trap(xp, coins) and xp_delta <= 0 and coins_delta <= 0:
            if xp_delta == 0 and coins_delta == 0:
                text = "😈 **Piégé !** Heureusement, tu n'avais rien à perdre."
            else:
                lost = describe_amounts(xp_delta, coins_delta).replace("−", "")
                text = f"😈 **Piégé !** Tu perds {lost}."
        elif is_trap(xp, coins):
            text = (
                "😈 **Surprise !** Résultat : "
                f"**{describe_amounts(xp_delta, coins_delta)}**."
            )
        else:
            text = f"🎉 Tu remportes **{describe_amounts(result['xp_delta'], result['coins_delta'])}** !"

        await interaction.response.send_message(text, ephemeral=True)

        member = (
            interaction.user
            if isinstance(interaction.user, discord.Member)
            else None
        )

        try:
            await refresh_level_roles(
                self.bot,
                member,
                result["old_xp"],
                result["new_xp"],
            )
        except Exception:
            LOGGER.exception("Rôles de niveau non mis à jour après le drop %s", drop_id)

        await self.refresh_message(drop_id)

    async def refresh_message(self, drop_id: int) -> None:
        record = await self.get_pool().fetchrow(
            "SELECT * FROM drops WHERE id = $1",
            drop_id,
        )

        if record is None or record["message_id"] is None:
            return

        channel = self.bot.get_channel(int(record["channel_id"]))

        if not isinstance(channel, discord.abc.Messageable):
            return

        finished = bool(record["ended"])

        try:
            message = await channel.fetch_message(int(record["message_id"]))
            await message.edit(
                embed=build_drop_embed(
                    record,
                    await self.get_claims(drop_id),
                    finished=finished,
                ),
                view=drop_view(drop_id, disabled=finished),
            )
        except discord.HTTPException:
            LOGGER.debug("Message du drop %s non modifiable.", drop_id)

    @tasks.loop(seconds=30)
    async def expire_loop(self) -> None:
        try:
            records = await self.get_pool().fetch(
                """
                UPDATE drops
                SET ended = TRUE
                WHERE ended = FALSE
                  AND expires_at <= NOW()
                RETURNING id
                """
            )
        except Exception:
            LOGGER.exception("Impossible de clôturer les drops expirés.")
            return

        for record in records:
            await self.refresh_message(int(record["id"]))

    @expire_loop.before_loop
    async def before_expire_loop(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="drop",
        description="Fait apparaître un drop d'XP ou de pièces à récupérer.",
    )
    @app_commands.rename(
        coins="pieces",
        claims="gagnants",
        duration="duree",
        hidden="mystere",
        channel="salon",
    )
    @app_commands.describe(
        xp="XP gagnée (négatif pour en retirer).",
        coins="Pièces gagnées (négatif pour en retirer).",
        claims="Nombre de membres qui peuvent le récupérer (1 par défaut).",
        duration="Durée avant disparition (10m par défaut, 1j maximum).",
        hidden="Cacher le contenu jusqu'au clic (idéal pour un piège).",
        message="Texte affiché sur le drop.",
        channel="Salon du drop (ce salon par défaut).",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def drop(
        self,
        interaction: discord.Interaction,
        xp: app_commands.Range[int, -MAXIMUM_AMOUNT, MAXIMUM_AMOUNT] = 0,
        coins: app_commands.Range[int, -MAXIMUM_AMOUNT, MAXIMUM_AMOUNT] = 0,
        claims: app_commands.Range[int, 1, MAXIMUM_CLAIMS] = 1,
        duration: str | None = None,
        hidden: bool = False,
        message: app_commands.Range[str, 1, 200] | None = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            return

        if xp == 0 and coins == 0:
            await interaction.response.send_message(
                "❌ Indique de l'`xp` et/ou des `pieces` (négatif pour un piège).",
                ephemeral=True,
            )
            return

        delay = DEFAULT_DURATION if duration is None else parse_duration(duration)

        if delay is None or not timedelta(seconds=30) <= delay <= MAXIMUM_DURATION:
            await interaction.response.send_message(
                "❌ Durée invalide : entre 30 secondes et 1 jour, par exemple `5m` ou `2h`.",
                ephemeral=True,
            )
            return

        target = channel or interaction.channel

        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "❌ Choisis un salon textuel avec l'option `salon`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        pool = self.get_pool()
        record = await pool.fetchrow(
            """
            INSERT INTO drops (
                guild_id, channel_id, created_by, xp, coins,
                max_claims, hidden, note, expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            guild.id,
            target.id,
            interaction.user.id,
            int(xp),
            int(coins),
            int(claims),
            bool(hidden),
            message.strip() if message else None,
            datetime.now(timezone.utc) + delay,
        )

        try:
            sent = await target.send(
                embed=build_drop_embed(record, [], finished=False),
                view=drop_view(int(record["id"])),
            )
        except discord.HTTPException:
            await pool.execute("DELETE FROM drops WHERE id = $1", record["id"])
            await interaction.followup.send(
                f"❌ Je ne peux pas écrire dans {target.mention}.",
                ephemeral=True,
            )
            return

        await pool.execute(
            "UPDATE drops SET message_id = $2 WHERE id = $1",
            record["id"],
            sent.id,
        )

        await interaction.followup.send(
            f"✅ Drop n°{record['id']} lancé : {describe_amounts(int(xp), int(coins))}"
            f"{' (mystère)' if hidden else ''}, {claims} place(s). "
            f"[Voir le drop]({sent.jump_url})",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_dynamic_items(ClaimDropButton)

    cog = DropCog(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info("Commande /drop chargée")
