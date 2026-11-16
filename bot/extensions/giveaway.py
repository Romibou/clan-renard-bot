"""
Giveaways : un administrateur lance un tirage au sort, les membres
participent avec un bouton, et le bot tire les gagnants à la fin.

Le lot peut être un simple texte (à remettre à la main), et/ou être
remis automatiquement : pièces et/ou rôle Discord.
"""

from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.extensions.rappel import parse_duration
from bot.shared.economy import credit_progression, refresh_level_roles

LOGGER = logging.getLogger(__name__)

GIVEAWAY_COLOR = discord.Color.from_rgb(255, 120, 170)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

MINIMUM_DURATION = timedelta(minutes=1)
MAXIMUM_DURATION = timedelta(days=30)
MAXIMUM_WINNERS = 20


def error_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=ERROR_COLOR,
    )


def format_coins(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def draw_winners(
    entrants: list[int],
    count: int,
    rng: random.Random | None = None,
) -> list[int]:
    """Tire au plus `count` gagnants distincts parmi les participants."""
    unique = list(dict.fromkeys(entrants))
    generator = rng or random.SystemRandom()

    return generator.sample(unique, k=min(count, len(unique)))


def prize_lines(record) -> list[str]:
    lines = [f"🎁 **{record['prize']}**"]

    if record["coins"]:
        lines.append(
            f"💰 {format_coins(int(record['coins']))} pièces par gagnant "
            "(remises automatiquement)"
        )

    if record["role_id"]:
        lines.append(
            f"🎭 Rôle <@&{record['role_id']}> (remis automatiquement)"
        )

    return lines


def build_giveaway_embed(
    record,
    *,
    entries: int,
    winners: list[int] | None = None,
) -> discord.Embed:
    ends_at = int(record["ends_at"].timestamp())
    lines = prize_lines(record)

    if winners is None:
        lines += [
            "",
            f"⏰ Fin : <t:{ends_at}:R> (<t:{ends_at}:f>)",
            f"🏆 Gagnant(s) : **{record['winners_count']}**",
        ]

        if record["min_level"]:
            lines.append(f"⭐ Niveau minimum : **{record['min_level']}**")

        lines += [
            f"👥 Participants : **{entries}**",
            "",
            "Clique sur **Participer** pour tenter ta chance !",
        ]
        title = "🎉 GIVEAWAY"
    else:
        lines += [
            "",
            f"👥 Participants : **{entries}**",
            (
                "🏆 Gagnant(s) : "
                + ", ".join(f"<@{user_id}>" for user_id in winners)
                if winners
                else "😢 Aucun participant : pas de gagnant."
            ),
        ]
        title = "🎉 GIVEAWAY TERMINÉ"

    embed = discord.Embed(
        title=title,
        description="\n".join(lines),
        color=GIVEAWAY_COLOR if winners is None else SUCCESS_COLOR,
    )
    embed.set_footer(text=f"Giveaway n°{record['id']} • organisé par le Clan Renard")

    return embed


class JoinGiveawayButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"giveaway:join:(?P<id>[0-9]+)",
):
    """Bouton persistant : fonctionne encore après un redémarrage."""

    def __init__(
        self,
        giveaway_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Participer" if not disabled else "Terminé",
                emoji="🎉",
                style=(
                    discord.ButtonStyle.success
                    if not disabled
                    else discord.ButtonStyle.secondary
                ),
                custom_id=f"giveaway:join:{giveaway_id}",
                disabled=disabled,
            )
        )
        self.giveaway_id = giveaway_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> JoinGiveawayButton:
        return cls(int(match["id"]))

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        cog = interaction.client.get_cog("GiveawayCog")

        if cog is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Indisponible",
                    "Le module des giveaways n'est pas chargé.",
                ),
                ephemeral=True,
            )
            return

        await cog.toggle_entry(interaction, self.giveaway_id)


def giveaway_view(
    giveaway_id: int,
    *,
    disabled: bool = False,
) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(JoinGiveawayButton(giveaway_id, disabled=disabled))

    return view


class GiveawayCog(commands.Cog):
    giveaway = app_commands.Group(
        name="giveaway",
        description="Lance et gère les giveaways du serveur.",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

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
            CREATE TABLE IF NOT EXISTS giveaways (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT,
                host_id BIGINT NOT NULL,
                prize VARCHAR(200) NOT NULL,
                winners_count SMALLINT NOT NULL
                    CHECK (winners_count BETWEEN 1 AND 20),
                coins INTEGER NOT NULL DEFAULT 0 CHECK (coins >= 0),
                role_id BIGINT,
                min_level INTEGER NOT NULL DEFAULT 0,
                ends_at TIMESTAMPTZ NOT NULL,
                ended BOOLEAN NOT NULL DEFAULT FALSE,
                winner_ids BIGINT[] NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                giveaway_id BIGINT NOT NULL
                    REFERENCES giveaways(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (giveaway_id, user_id)
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS giveaways_pending_idx
            ON giveaways (ends_at)
            WHERE ended = FALSE
            """
        )

    async def cog_load(self) -> None:
        if not self.end_loop.is_running():
            self.end_loop.start()

    def cog_unload(self) -> None:
        self.end_loop.cancel()

    # ------------------------------------------------------------
    # PARTICIPATION
    # ------------------------------------------------------------

    async def get_giveaway(self, giveaway_id: int):
        return await self.get_pool().fetchrow(
            "SELECT * FROM giveaways WHERE id = $1",
            giveaway_id,
        )

    async def count_entries(self, giveaway_id: int) -> int:
        return int(
            await self.get_pool().fetchval(
                "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = $1",
                giveaway_id,
            )
            or 0
        )

    async def get_member_level(self, guild_id: int, user_id: int) -> int:
        from bot.extensions.progression import level_from_xp

        total_xp = await self.get_pool().fetchval(
            """
            SELECT total_xp
            FROM progression_members
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

        return level_from_xp(int(total_xp or 0))

    async def toggle_entry(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
    ) -> None:
        record = await self.get_giveaway(giveaway_id)

        if (
            record is None
            or record["ended"]
            or record["ends_at"] <= datetime.now(timezone.utc)
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Giveaway terminé",
                    "Ce giveaway est terminé, il n'est plus possible de participer.",
                ),
                ephemeral=True,
            )
            return

        if interaction.user.bot:
            return

        pool = self.get_pool()

        removed = await pool.execute(
            """
            DELETE FROM giveaway_entries
            WHERE giveaway_id = $1
              AND user_id = $2
            """,
            giveaway_id,
            interaction.user.id,
        )

        if removed != "DELETE 0":
            await interaction.response.send_message(
                "👋 Tu ne participes plus à ce giveaway. "
                "Reclique sur **Participer** si tu changes d'avis.",
                ephemeral=True,
            )
            await self.refresh_message(record)
            return

        min_level = int(record["min_level"] or 0)

        if min_level > 0:
            level = await self.get_member_level(
                int(record["guild_id"]),
                interaction.user.id,
            )

            if level < min_level:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Niveau insuffisant",
                        (
                            f"Ce giveaway demande le niveau **{min_level}**. "
                            f"Tu es niveau **{level}** : continue à "
                            "discuter pour monter de niveau !"
                        ),
                    ),
                    ephemeral=True,
                )
                return

        await pool.execute(
            """
            INSERT INTO giveaway_entries (giveaway_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            giveaway_id,
            interaction.user.id,
        )

        await interaction.response.send_message(
            "🎉 Ta participation est enregistrée, bonne chance ! "
            "(Reclique sur le bouton pour te retirer.)",
            ephemeral=True,
        )
        await self.refresh_message(record)

    async def fetch_message(self, record) -> discord.Message | None:
        if record["message_id"] is None:
            return None

        channel = self.bot.get_channel(int(record["channel_id"]))

        if not isinstance(channel, discord.abc.Messageable):
            return None

        try:
            return await channel.fetch_message(int(record["message_id"]))
        except discord.HTTPException:
            return None

    async def refresh_message(self, record) -> None:
        """Met à jour le compteur de participants (sans bloquer le clic)."""
        message = await self.fetch_message(record)

        if message is None:
            return

        try:
            await message.edit(
                embed=build_giveaway_embed(
                    record,
                    entries=await self.count_entries(int(record["id"])),
                )
            )
        except discord.HTTPException:
            LOGGER.debug("Compteur du giveaway %s non mis à jour.", record["id"])

    # ------------------------------------------------------------
    # FIN ET TIRAGE
    # ------------------------------------------------------------

    async def present_entrants(self, record) -> list[int]:
        """Participants encore présents sur le serveur."""
        records = await self.get_pool().fetch(
            "SELECT user_id FROM giveaway_entries WHERE giveaway_id = $1",
            int(record["id"]),
        )
        user_ids = [int(row["user_id"]) for row in records]
        guild = self.bot.get_guild(int(record["guild_id"]))

        if guild is None or not guild.chunked:
            return user_ids

        return [
            user_id
            for user_id in user_ids
            if guild.get_member(user_id) is not None
        ]

    async def deliver_prizes(self, record, winners: list[int]) -> list[str]:
        """Remet pièces et rôle. Retourne les problèmes rencontrés."""
        problems: list[str] = []
        guild = self.bot.get_guild(int(record["guild_id"]))
        coins = int(record["coins"] or 0)
        role = (
            guild.get_role(int(record["role_id"]))
            if guild is not None and record["role_id"]
            else None
        )

        if record["role_id"] and role is None:
            problems.append("le rôle du lot n'existe plus")

        for user_id in winners:
            member = guild.get_member(user_id) if guild is not None else None

            if coins > 0:
                try:
                    old_xp, new_xp = await credit_progression(
                        self.bot.database,  # type: ignore[attr-defined]
                        guild_id=int(record["guild_id"]),
                        user_id=user_id,
                        xp=0,
                        coins=coins,
                        transaction_type="giveaway",
                        reason=f"Giveaway n°{record['id']} : {record['prize']}",
                    )
                    await refresh_level_roles(self.bot, member, old_xp, new_xp)
                except Exception:
                    LOGGER.exception("Pièces du giveaway %s non versées", record["id"])
                    problems.append(f"pièces non versées à <@{user_id}>")

            if role is not None and member is not None:
                try:
                    await member.add_roles(
                        role,
                        reason=f"Giveaway n°{record['id']}",
                    )
                except discord.HTTPException:
                    problems.append(f"rôle non donné à <@{user_id}>")

        return problems

    async def finish(
        self,
        giveaway_id: int,
        *,
        reroll: bool = False,
    ) -> tuple[list[int], list[str]] | None:
        """
        Termine le giveaway (ou le retire au sort à nouveau) et annonce
        les gagnants. None si le giveaway n'existe pas ou est déjà fini.
        """
        pool = self.get_pool()

        if reroll:
            record = await pool.fetchrow(
                "SELECT * FROM giveaways WHERE id = $1 AND ended = TRUE",
                giveaway_id,
            )
        else:
            # Le passage à ended = TRUE est atomique : deux fins
            # simultanées ne peuvent pas tirer deux fois.
            record = await pool.fetchrow(
                """
                UPDATE giveaways
                SET ended = TRUE
                WHERE id = $1
                  AND ended = FALSE
                RETURNING *
                """,
                giveaway_id,
            )

        if record is None:
            return None

        entrants = await self.present_entrants(record)

        if reroll:
            previous = set(int(user_id) for user_id in record["winner_ids"])
            entrants = [user_id for user_id in entrants if user_id not in previous]

        winners = draw_winners(entrants, int(record["winners_count"]))

        await pool.execute(
            "UPDATE giveaways SET winner_ids = $2 WHERE id = $1",
            giveaway_id,
            list(winners) if not reroll else list(record["winner_ids"]) + winners,
        )

        problems = await self.deliver_prizes(record, winners)
        entries = await self.count_entries(giveaway_id)

        message = await self.fetch_message(record)

        if message is not None and not reroll:
            try:
                await message.edit(
                    embed=build_giveaway_embed(
                        record,
                        entries=entries,
                        winners=winners,
                    ),
                    view=giveaway_view(giveaway_id, disabled=True),
                )
            except discord.HTTPException:
                LOGGER.warning("Message du giveaway %s non modifiable.", giveaway_id)

        channel = self.bot.get_channel(int(record["channel_id"]))

        if isinstance(channel, discord.abc.Messageable):
            if winners:
                mentions = ", ".join(f"<@{user_id}>" for user_id in winners)
                text = (
                    f"🎉 {'Nouveau tirage ! ' if reroll else ''}Félicitations "
                    f"{mentions} : tu remportes **{record['prize']}** !"
                )
            else:
                text = (
                    f"😢 Le giveaway **{record['prize']}** est terminé "
                    "sans participant éligible."
                )

            try:
                await channel.send(
                    text,
                    reference=message,
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions(
                        everyone=False,
                        roles=False,
                        users=[discord.Object(id=user_id) for user_id in winners],
                    ),
                )
            except discord.HTTPException:
                LOGGER.warning("Annonce du giveaway %s impossible.", giveaway_id)

        return winners, problems

    @tasks.loop(seconds=30)
    async def end_loop(self) -> None:
        try:
            records = await self.get_pool().fetch(
                """
                SELECT id
                FROM giveaways
                WHERE ended = FALSE
                  AND ends_at <= NOW()
                """
            )
        except Exception:
            LOGGER.exception("Impossible de lire les giveaways à terminer.")
            return

        for record in records:
            try:
                await self.finish(int(record["id"]))
            except Exception:
                LOGGER.exception("Échec de la fin du giveaway %s", record["id"])

    @end_loop.before_loop
    async def before_end_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------
    # COMMANDES
    # ------------------------------------------------------------

    @giveaway.command(
        name="lancer",
        description="Lance un giveaway dans un salon.",
    )
    @app_commands.rename(
        prize="lot",
        duration="duree",
        winners="gagnants",
        coins="pieces",
        min_level="niveau_minimum",
        channel="salon",
    )
    @app_commands.describe(
        prize="Ce que les gagnants remportent (texte affiché).",
        duration="Durée, par exemple 30m, 2h, 3j ou 1sem.",
        winners="Nombre de gagnants (1 par défaut).",
        coins="Pièces remises automatiquement à chaque gagnant.",
        role="Rôle remis automatiquement à chaque gagnant.",
        min_level="Niveau minimum pour participer.",
        channel="Salon du giveaway (ce salon par défaut).",
    )
    async def launch(
        self,
        interaction: discord.Interaction,
        prize: app_commands.Range[str, 1, 200],
        duration: str,
        winners: app_commands.Range[int, 1, MAXIMUM_WINNERS] = 1,
        coins: app_commands.Range[int, 0, 1_000_000] = 0,
        role: discord.Role | None = None,
        min_level: app_commands.Range[int, 0, 1000] = 0,
        channel: discord.TextChannel | None = None,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            return

        delay = parse_duration(duration)

        if delay is None or not MINIMUM_DURATION <= delay <= MAXIMUM_DURATION:
            await interaction.response.send_message(
                embed=error_embed(
                    "Durée invalide",
                    "Indique une durée entre 1 minute et 30 jours, "
                    "par exemple `30m`, `2h`, `3j` ou `1sem`.",
                ),
                ephemeral=True,
            )
            return

        if role is not None:
            me = guild.me

            if (
                role.is_default()
                or role.managed
                or me is None
                or role >= me.top_role
            ):
                await interaction.response.send_message(
                    embed=error_embed(
                        "Rôle impossible à donner",
                        f"Je ne peux pas attribuer {role.mention} : il doit "
                        "être placé sous mon rôle et ne pas être géré par "
                        "une intégration.",
                    ),
                    ephemeral=True,
                )
                return

        target = channel or interaction.channel

        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                embed=error_embed(
                    "Salon invalide",
                    "Choisis un salon textuel avec l'option `salon`.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        pool = self.get_pool()
        record = await pool.fetchrow(
            """
            INSERT INTO giveaways (
                guild_id, channel_id, host_id, prize, winners_count,
                coins, role_id, min_level, ends_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            guild.id,
            target.id,
            interaction.user.id,
            prize.strip(),
            int(winners),
            int(coins),
            role.id if role is not None else None,
            int(min_level),
            datetime.now(timezone.utc) + delay,
        )

        try:
            message = await target.send(
                embed=build_giveaway_embed(record, entries=0),
                view=giveaway_view(int(record["id"])),
            )
        except discord.HTTPException:
            await pool.execute("DELETE FROM giveaways WHERE id = $1", record["id"])
            await interaction.followup.send(
                embed=error_embed(
                    "Envoi impossible",
                    f"Je ne peux pas écrire dans {target.mention}.",
                ),
                ephemeral=True,
            )
            return

        await pool.execute(
            "UPDATE giveaways SET message_id = $2 WHERE id = $1",
            record["id"],
            message.id,
        )

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Giveaway lancé",
                description=(
                    f"[Voir le giveaway]({message.jump_url}) — "
                    f"n°**{record['id']}**.\n"
                    f"Fin <t:{int(record['ends_at'].timestamp())}:R>. "
                    "Le tirage se fait automatiquement."
                ),
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

    @giveaway.command(
        name="terminer",
        description="Termine un giveaway maintenant et tire les gagnants.",
    )
    @app_commands.rename(giveaway_id="numero")
    @app_commands.describe(giveaway_id="Numéro du giveaway (en bas du message).")
    async def end_now(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
    ) -> None:
        await self._admin_finish(interaction, giveaway_id, reroll=False)

    @giveaway.command(
        name="retirer",
        description="Tire de nouveaux gagnants pour un giveaway terminé.",
    )
    @app_commands.rename(giveaway_id="numero")
    @app_commands.describe(giveaway_id="Numéro du giveaway (en bas du message).")
    async def reroll(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
    ) -> None:
        await self._admin_finish(interaction, giveaway_id, reroll=True)

    async def _admin_finish(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
        *,
        reroll: bool,
    ) -> None:
        record = await self.get_giveaway(giveaway_id)

        if record is None or record["guild_id"] != interaction.guild_id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Giveaway introuvable",
                    f"Aucun giveaway n°{giveaway_id} sur ce serveur.",
                ),
                ephemeral=True,
            )
            return

        if reroll and not record["ended"]:
            await interaction.response.send_message(
                embed=error_embed(
                    "Giveaway en cours",
                    "Ce giveaway n'est pas terminé : utilise "
                    "`/giveaway terminer` d'abord.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.finish(giveaway_id, reroll=reroll)

        if result is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Déjà terminé",
                    "Ce giveaway est déjà terminé. Utilise "
                    "`/giveaway retirer` pour tirer de nouveaux gagnants.",
                ),
                ephemeral=True,
            )
            return

        winners, problems = result
        description = (
            "Gagnant(s) : " + ", ".join(f"<@{user_id}>" for user_id in winners)
            if winners
            else "Aucun participant éligible."
        )

        if problems:
            description += "\n\n⚠️ À faire à la main : " + " ; ".join(problems) + "."

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Tirage effectué",
                description=description,
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_dynamic_items(JoinGiveawayButton)

    cog = GiveawayCog(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info("Système de giveaways chargé")
