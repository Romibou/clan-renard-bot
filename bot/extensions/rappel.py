from __future__ import annotations

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

REMINDER_CHECK_INTERVAL_SECONDS = 30

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

        self.check_reminders.start()

    def cog_unload(self) -> None:
        self.check_reminders.cancel()

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

        LOGGER.info(
            "Table des rappels vérifiée"
        )

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

            await pool.execute(
                """
                INSERT INTO reminders (
                    guild_id,
                    channel_id,
                    user_id,
                    reason,
                    destination,
                    trigger_at
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                interaction.guild.id if interaction.guild else None,
                interaction.channel_id,
                interaction.user.id,
                raison,
                destination.value,
                trigger_at,
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

        timestamp = int(
            trigger_at.timestamp()
        )

        destination_text = (
            "dans ce salon" if destination.value == "channel"
            else "en message privé"
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Rappel programmé",
                (
                    f"Je te préviendrai **{destination_text}** "
                    f"<t:{timestamp}:R> (<t:{timestamp}:f>).\n\n"
                    f"📝 {raison}"
                ),
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
        pool = self.get_pool()

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

        embed = base_embed(
            "⏰ Rappel",
            record["reason"],
        )

        delivered = False

        if record["destination"] == "dm":
            if user is not None:
                try:
                    await user.send(
                        content="⏰ Petit rappel !",
                        embed=embed,
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
                    )
                    delivered = True
                except discord.HTTPException:
                    delivered = False

            if not delivered and user is not None:
                try:
                    await user.send(
                        embed=embed
                    )
                    delivered = True
                except discord.HTTPException:
                    delivered = False

        await pool.execute(
            """
            UPDATE reminders
            SET sent = TRUE
            WHERE id = $1
            """,
            record["id"],
        )

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
                SELECT
                    id,
                    guild_id,
                    channel_id,
                    user_id,
                    reason,
                    destination
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
            await self.send_reminder(
                record
            )

    @check_reminders.before_loop
    async def before_check_reminders(self) -> None:
        await self.bot.wait_until_ready()


async def setup(
    bot: commands.Bot,
) -> None:
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
