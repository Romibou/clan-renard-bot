from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks


LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

# La précision vient maintenant du scheduling individuel
# (asyncio.sleep par rappel) ; cette boucle n'est qu'un filet de
# sécurité pour les cas où un rappel n'a pas pu être programmé
# (redémarrage du bot entre l'insertion et l'appel, erreur, etc.).
REMINDER_CHECK_INTERVAL_SECONDS = 60

MINIMUM_DELAY = timedelta(seconds=10)
MAXIMUM_DELAY = timedelta(days=90)

DURATION_PATTERN = re.compile(
    r"^"
    r"(?:(?P<weeks>\d+)\s*(?:sem(?:aines?)?|w))?"
    r"(?:(?P<days>\d+)\s*(?:j(?:ours?)?|d))?"
    r"(?:(?P<hours>\d+)\s*(?:h(?:eures?)?))?"
    r"(?:(?P<minutes>\d+)\s*(?:m(?:in(?:utes?)?)?))?"
    r"(?:(?P<seconds>\d+)\s*(?:s(?:ec(?:ondes?)?)?))?"
    r"$",
    re.IGNORECASE,
)


def parse_duration(
    text: str,
) -> timedelta | None:
    """
    Comprend des formats du type "10m", "2h", "1j12h", "3sem".
    Un texte composé uniquement de chiffres est traité comme des
    minutes (ex: "45" -> 45 minutes).
    """
    cleaned = text.strip().lower().replace(" ", "")

    if not cleaned:
        return None

    if cleaned.isdigit():
        return timedelta(
            minutes=int(cleaned)
        )

    match = DURATION_PATTERN.match(
        cleaned
    )

    if not match:
        return None

    parts = match.groupdict()

    if not any(parts.values()):
        return None

    return timedelta(
        weeks=int(parts["weeks"] or 0),
        days=int(parts["days"] or 0),
        hours=int(parts["hours"] or 0),
        minutes=int(parts["minutes"] or 0),
        seconds=int(parts["seconds"] or 0),
    )


def success_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=SUCCESS_COLOR,
    )


def error_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=ERROR_COLOR,
    )


def base_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=COLOR,
    )


def scheduled_embed(
    *,
    destination_text: str,
    reason: str,
    trigger_at: datetime,
) -> discord.Embed:
    """
    Embed aéré affiché quand un rappel vient d'être programmé,
    avec des champs séparés plutôt qu'une description dense.
    """
    timestamp = int(trigger_at.timestamp())

    embed = discord.Embed(
        title="✅ Rappel programmé",
        description="Ton rappel a bien été enregistré.",
        color=SUCCESS_COLOR,
    )

    embed.add_field(
        name="⏰ Quand",
        value=f"<t:{timestamp}:R>\n<t:{timestamp}:f>",
        inline=True,
    )
    embed.add_field(
        name="📍 Où",
        value=destination_text,
        inline=True,
    )
    embed.add_field(
        name="📝 Raison",
        value=reason,
        inline=False,
    )

    return embed


def reminder_embed(
    *,
    mention: str,
    reason: str,
    created_at: datetime,
) -> discord.Embed:
    """
    Embed aéré envoyé au moment du rappel, façon DraftBot :
    une phrase avec un timestamp relatif, puis le motif dans
    son propre champ pour créer de l'espace visuel.
    """
    created_ts = int(created_at.timestamp())

    embed = discord.Embed(
        title="⏰ Rappel",
        description=(
            f"{mention}, tu m'as demandé de te rappeler ceci "
            f"<t:{created_ts}:R>."
        ),
        color=COLOR,
    )

    embed.add_field(
        name="\u200b",
        value=f"📝 {reason}",
        inline=False,
    )

    return embed


class RelaunchButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"rappel:relaunch:(?P<id>[0-9]+)",
):
    """
    Bouton persistant "Relancer le rappel" attaché à chaque rappel
    envoyé. Le custom_id encode l'id du rappel d'origine, ce qui
    permet au bouton de continuer à fonctionner même après un
    redémarrage du bot (nécessite discord.py >= 2.4).
    """

    def __init__(self, reminder_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Relancer le rappel",
                emoji="🔄",
                style=discord.ButtonStyle.primary,
                custom_id=f"rappel:relaunch:{reminder_id}",
            )
        )
        self.reminder_id = reminder_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> "RelaunchButton":
        return cls(int(match["id"]))

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        cog = interaction.client.get_cog("ReminderCog")

        if cog is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    "Le système de rappels est indisponible.",
                ),
                ephemeral=True,
            )
            return

        await cog.relaunch_reminder(
            interaction,
            self.reminder_id,
        )


class ReminderCog(
    commands.Cog
):
    """
    Rappels personnels programmés (/rappel), envoyés dans le salon
    d'origine ou en message privé, à l'heure demandée.
    """

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot
        self._scheduled_tasks: set[asyncio.Task] = set()

        self.check_reminders.start()

    def cog_unload(self) -> None:
        self.check_reminders.cancel()

        for task in list(self._scheduled_tasks):
            task.cancel()

    def get_pool(self):
        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            raise RuntimeError(
                "Le gestionnaire PostgreSQL est indisponible."
            )

        return database.require_pool()

    async def initialize_database(
        self,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT,
                channel_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,

                reason TEXT NOT NULL,
                destination TEXT NOT NULL,

                trigger_at TIMESTAMPTZ NOT NULL,
                sent BOOLEAN NOT NULL DEFAULT FALSE,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS reminders_pending_idx
            ON reminders (
                trigger_at
            )
            WHERE sent = FALSE
            """
        )

        # Migration douce pour les bases déjà existantes : on stocke
        # le délai d'origine afin de pouvoir relancer un rappel à
        # l'identique depuis le bouton "Relancer le rappel".
        await pool.execute(
            """
            ALTER TABLE reminders
            ADD COLUMN IF NOT EXISTS delay_seconds INTEGER
            """
        )

        LOGGER.info(
            "Table des rappels vérifiée"
        )

    # ------------------------------------------------------------
    # SCHEDULING PRÉCIS (par rappel, en complément du polling)
    # ------------------------------------------------------------

    def schedule_reminder(
        self,
        reminder_id: int,
        trigger_at: datetime,
    ) -> None:
        """
        Programme l'envoi exact d'un rappel via asyncio.sleep, pour
        ne pas dépendre uniquement du passage périodique de
        check_reminders (qui ne garantit qu'une précision à
        ~REMINDER_CHECK_INTERVAL_SECONDS près).
        """
        task = self.bot.loop.create_task(
            self._wait_then_send(
                reminder_id,
                trigger_at,
            )
        )
        self._scheduled_tasks.add(task)
        task.add_done_callback(
            self._scheduled_tasks.discard
        )

    async def reschedule_pending(self) -> None:
        """
        À appeler au démarrage : reprogramme précisément tous les
        rappels en attente, pour ne pas perdre la précision après
        un redémarrage du bot.
        """
        pool = self.get_pool()

        records = await pool.fetch(
            """
            SELECT id, trigger_at
            FROM reminders
            WHERE sent = FALSE
            """
        )

        for record in records:
            self.schedule_reminder(
                record["id"],
                record["trigger_at"],
            )

    async def _wait_then_send(
        self,
        reminder_id: int,
        trigger_at: datetime,
    ) -> None:
        delay = (
            trigger_at - datetime.now(timezone.utc)
        ).total_seconds()

        if delay > 0:
            await asyncio.sleep(delay)

        await self.claim_and_send(reminder_id)

    async def claim_and_send(
        self,
        reminder_id: int,
    ) -> None:
        """
        Marque le rappel comme envoyé de façon atomique (UPDATE ...
        WHERE sent = FALSE) puis l'envoie. L'atomicité empêche un
        double envoi si le scheduling précis et la boucle de
        sécurité se déclenchent pour le même rappel.
        """
        try:
            pool = self.get_pool()
        except RuntimeError:
            return

        record = await pool.fetchrow(
            """
            UPDATE reminders
            SET sent = TRUE
            WHERE id = $1
              AND sent = FALSE
            RETURNING
                id,
                guild_id,
                channel_id,
                user_id,
                reason,
                destination,
                delay_seconds,
                created_at
            """,
            reminder_id,
        )

        if record is None:
            # Déjà envoyé par ailleurs (scheduling précis ou boucle
            # de sécurité) : rien à faire.
            return

        await self.send_reminder(record)

    # ------------------------------------------------------------
    # COMMANDE
    # ------------------------------------------------------------

    @app_commands.command(
        name="rappel",
        description="Programme un rappel personnel.",
    )
    @app_commands.describe(
        raison="Le motif du rappel.",
        temps="Dans combien de temps (ex: 10m, 2h, 1j12h, 3sem).",
        destination="Où recevoir le rappel.",
    )
    @app_commands.choices(
        destination=[
            app_commands.Choice(
                name="Dans ce salon",
                value="channel",
            ),
            app_commands.Choice(
                name="En message privé",
                value="dm",
            ),
        ]
    )
    async def rappel(
        self,
        interaction: discord.Interaction,
        raison: app_commands.Range[str, 1, 200],
        temps: str,
        destination: app_commands.Choice[str],
    ) -> None:
        delay = parse_duration(
            temps
        )

        if delay is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Durée incomprise",
                    (
                        "Je n'ai pas compris ce format de durée. "
                        "Exemples valides : `10m`, `2h`, `1j12h`, "
                        "`3sem`, ou juste un nombre de minutes "
                        "comme `45`."
                    ),
                ),
                ephemeral=True,
            )
            return

        if delay < MINIMUM_DELAY:
            await interaction.response.send_message(
                embed=error_embed(
                    "Durée trop courte",
                    "Le rappel doit être fixé au moins 10 secondes à l'avance.",
                ),
                ephemeral=True,
            )
            return

        if delay > MAXIMUM_DELAY:
            await interaction.response.send_message(
                embed=error_embed(
                    "Durée trop longue",
                    "Le rappel ne peut pas dépasser 90 jours.",
                ),
                ephemeral=True,
            )
            return

        trigger_at = datetime.now(timezone.utc) + delay

        try:
            pool = self.get_pool()

            reminder_id = await pool.fetchval(
                """
                INSERT INTO reminders (
                    guild_id,
                    channel_id,
                    user_id,
                    reason,
                    destination,
                    trigger_at,
                    delay_seconds
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                interaction.guild.id if interaction.guild else None,
                interaction.channel_id,
                interaction.user.id,
                raison,
                destination.value,
                trigger_at,
                int(delay.total_seconds()),
            )
        except Exception:
            LOGGER.exception(
                "Impossible d'enregistrer un rappel pour %s.",
                interaction.user.id,
            )
            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    "Le rappel n'a pas pu être enregistré. Réessaie plus tard.",
                ),
                ephemeral=True,
            )
            return

        self.schedule_reminder(
            reminder_id,
            trigger_at,
        )

        destination_text = (
            "Dans ce salon" if destination.value == "channel"
            else "En message privé"
        )

        await interaction.response.send_message(
            embed=scheduled_embed(
                destination_text=destination_text,
                reason=raison,
                trigger_at=trigger_at,
            ),
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # ENVOI DES RAPPELS
    # ------------------------------------------------------------

    async def send_reminder(
        self,
        record,
    ) -> None:
        user = self.bot.get_user(
            record["user_id"]
        )

        if user is None:
            try:
                user = await self.bot.fetch_user(
                    record["user_id"]
                )
            except discord.HTTPException:
                user = None

        mention = user.mention if user is not None else f"<@{record['user_id']}>"

        embed = reminder_embed(
            mention=mention,
            reason=record["reason"],
            created_at=record["created_at"],
        )

        view = discord.ui.View(timeout=None)
        view.add_item(
            RelaunchButton(record["id"])
        )

        delivered = False

        if record["destination"] == "dm":
            if user is not None:
                try:
                    await user.send(
                        content="⏰ Petit rappel !",
                        embed=embed,
                        view=view,
                    )
                    delivered = True
                except discord.HTTPException:
                    delivered = False

            if not delivered:
                channel = self.bot.get_channel(
                    record["channel_id"]
                )

                if isinstance(
                    channel,
                    (discord.TextChannel, discord.Thread),
                ):
                    try:
                        await channel.send(
                            content=f"<@{record['user_id']}>",
                            embed=embed,
                            view=view,
                        )
                        delivered = True
                    except discord.HTTPException:
                        delivered = False
        else:
            channel = self.bot.get_channel(
                record["channel_id"]
            )

            if isinstance(
                channel,
                (discord.TextChannel, discord.Thread),
            ):
                try:
                    await channel.send(
                        content=f"<@{record['user_id']}>",
                        embed=embed,
                        view=view,
                    )
                    delivered = True
                except discord.HTTPException:
                    delivered = False

            if not delivered and user is not None:
                try:
                    await user.send(
                        embed=embed,
                        view=view,
                    )
                    delivered = True
                except discord.HTTPException:
                    delivered = False

        if not delivered:
            LOGGER.warning(
                "Rappel %s non délivré à %s "
                "(salon supprimé et/ou DMs fermés).",
                record["id"],
                record["user_id"],
            )

    @tasks.loop(
        seconds=REMINDER_CHECK_INTERVAL_SECONDS,
    )
    async def check_reminders(self) -> None:
        try:
            pool = self.get_pool()
        except RuntimeError:
            return

        try:
            records = await pool.fetch(
                """
                SELECT id
                FROM reminders
                WHERE sent = FALSE
                  AND trigger_at <= NOW()
                ORDER BY trigger_at
                LIMIT 50
                """
            )
        except Exception:
            LOGGER.exception(
                "Impossible de récupérer les rappels à envoyer."
            )
            return

        for record in records:
            await self.claim_and_send(
                record["id"]
            )

    @check_reminders.before_loop
    async def before_check_reminders(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------
    # RELANCE (bouton "Relancer le rappel")
    # ------------------------------------------------------------

    async def relaunch_reminder(
        self,
        interaction: discord.Interaction,
        reminder_id: int,
    ) -> None:
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                guild_id,
                channel_id,
                user_id,
                reason,
                destination,
                delay_seconds
            FROM reminders
            WHERE id = $1
            """,
            reminder_id,
        )

        if record is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Rappel introuvable",
                    "Ce rappel n'existe plus, je ne peux pas le relancer.",
                ),
                ephemeral=True,
            )
            return

        if record["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Action impossible",
                    "Seule la personne à l'origine du rappel peut le relancer.",
                ),
                ephemeral=True,
            )
            return

        delay_seconds = record["delay_seconds"] or int(
            MINIMUM_DELAY.total_seconds()
        )
        trigger_at = datetime.now(timezone.utc) + timedelta(
            seconds=delay_seconds
        )

        try:
            await pool.execute(
                """
                INSERT INTO reminders (
                    guild_id,
                    channel_id,
                    user_id,
                    reason,
                    destination,
                    trigger_at,
                    delay_seconds
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                record["guild_id"],
                record["channel_id"],
                record["user_id"],
                record["reason"],
                record["destination"],
                trigger_at,
                delay_seconds,
            )
        except Exception:
            LOGGER.exception(
                "Impossible de relancer le rappel %s.",
                reminder_id,
            )
            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    "Le rappel n'a pas pu être relancé. Réessaie plus tard.",
                ),
                ephemeral=True,
            )
            return

        destination_text = (
            "Dans ce salon" if record["destination"] == "channel"
            else "En message privé"
        )

        await interaction.response.send_message(
            embed=scheduled_embed(
                destination_text=destination_text,
                reason=record["reason"],
                trigger_at=trigger_at,
            ),
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    # Enregistre le "template" du bouton "Relancer le rappel" pour
    # qu'il reste cliquable même après un redémarrage du bot.
    # Nécessite discord.py >= 2.4.
    bot.add_dynamic_items(
        RelaunchButton
    )

    cog = ReminderCog(
        bot
    )

    await cog.initialize_database()

    await bot.add_cog(
        cog
    )

    LOGGER.info(
        "Système de rappels personnels initialisé"
    )
