"""
Bonus d'XP temporaire pour tout le serveur (par exemple « XP ×2 à Noël »).

Réglé depuis /progression-admin → bouton « Bonus d'XP ». Le bonus
s'applique à l'XP des messages et du vocal, en plus des multiplicateurs
de rôle (ils se multiplient : VIP ×1,5 pendant un bonus ×2 = ×3).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

LOGGER = logging.getLogger(__name__)

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")

BOOST_COLOR = discord.Color.from_rgb(255, 196, 64)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

MINIMUM_MULTIPLIER = Decimal("1.1")
MAXIMUM_MULTIPLIER = Decimal("5")
MAXIMUM_DURATION = timedelta(days=60)
CACHE_TTL_SECONDS = 60.0

DATE_PATTERN = re.compile(
    r"^(?P<day>\d{1,2})/(?P<month>\d{1,2})(?:/(?P<year>\d{2,4}))?"
    r"(?:\s+(?P<hour>\d{1,2})(?:[:hH](?P<minute>\d{2})?)?)?$"
)


@dataclass(frozen=True, slots=True)
class XPBoost:
    multiplier: Decimal
    starts_at: datetime
    ends_at: datetime
    label: str

    def is_active(self, moment: datetime) -> bool:
        return self.starts_at <= moment < self.ends_at


def format_multiplier(value: Decimal) -> str:
    text = f"{value.normalize():f}"
    return text.replace(".", ",")


def format_paris(moment: datetime) -> str:
    return f"<t:{int(moment.timestamp())}:F>"


def parse_multiplier(text: str) -> Decimal | None:
    """
    « 2 », « x2 », « ×1,5 »… → Decimal. « 1 », « 0 » ou vide → None
    (arrêter le bonus).
    """
    cleaned = text.strip().lower().lstrip("x×").replace(",", ".").strip()

    if cleaned in {"", "0", "1", "1.0"}:
        return None

    try:
        value = Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError(
            "Le multiplicateur doit être un nombre, par exemple 2 ou 1,5."
        ) from error

    if not MINIMUM_MULTIPLIER <= value <= MAXIMUM_MULTIPLIER:
        raise ValueError(
            "Le multiplicateur doit être compris entre 1,1 et 5 "
            "(ou 1 pour arrêter le bonus)."
        )

    return value.quantize(Decimal("0.01"))


def parse_paris_datetime(
    text: str,
    *,
    now: datetime,
    end_of_day: bool,
) -> datetime:
    """
    « 24/12 », « 24/12 18:00 », « 24/12/2026 18h » → date heure de Paris.

    Sans année : l'année en cours, ou la suivante si la date est déjà
    passée depuis plus d'un jour (pour programmer janvier en décembre).
    Sans heure : 00:00 pour un début, 23:59 pour une fin.
    """
    match = DATE_PATTERN.match(text.strip())

    if match is None:
        raise ValueError(
            f"Date « {text.strip()} » incomprise. "
            "Écris par exemple 24/12 ou 24/12 18:00."
        )

    local_now = now.astimezone(PARIS_TIMEZONE)
    year_text = match.group("year")

    if match.group("hour") is None:
        hour, minute = (23, 59) if end_of_day else (0, 0)
    else:
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)

    def build(year: int) -> datetime:
        try:
            return datetime(
                year,
                int(match.group("month")),
                int(match.group("day")),
                hour,
                minute,
                tzinfo=PARIS_TIMEZONE,
            )
        except ValueError as error:
            raise ValueError(
                f"Date « {text.strip()} » invalide."
            ) from error

    if year_text is not None:
        year = int(year_text)
        return build(year + 2000 if year < 100 else year)

    candidate = build(local_now.year)

    if candidate < local_now - timedelta(days=1):
        candidate = build(local_now.year + 1)

    return candidate


def parse_boost_form(
    *,
    multiplier_text: str,
    start_text: str,
    end_text: str,
    now: datetime,
) -> tuple[Decimal, datetime, datetime] | None:
    """Valide le formulaire. None = arrêter le bonus en cours."""
    multiplier = parse_multiplier(multiplier_text)

    if multiplier is None:
        return None

    starts_at = (
        parse_paris_datetime(start_text, now=now, end_of_day=False)
        if start_text.strip()
        else now
    )

    if not end_text.strip():
        raise ValueError("Indique la date de fin du bonus.")

    ends_at = parse_paris_datetime(end_text, now=now, end_of_day=True)

    if ends_at <= starts_at:
        raise ValueError("La fin doit être après le début.")

    if ends_at <= now:
        raise ValueError("La date de fin est déjà passée.")

    if ends_at - starts_at > MAXIMUM_DURATION:
        raise ValueError("Un bonus dure 60 jours au maximum.")

    return multiplier, starts_at, ends_at


def start_announcement(boost: XPBoost) -> discord.Embed:
    return discord.Embed(
        title=f"🚀 {boost.label} : XP ×{format_multiplier(boost.multiplier)} !",
        description=(
            "Toute l'XP gagnée en écrivant et en vocal est multipliée "
            f"par **{format_multiplier(boost.multiplier)}** jusqu'au "
            f"{format_paris(boost.ends_at)}.\n\n"
            "Profitez-en !"
        ),
        color=BOOST_COLOR,
    )


def end_announcement(boost: XPBoost) -> discord.Embed:
    return discord.Embed(
        title=f"⏹️ Fin du bonus : {boost.label}",
        description=(
            "Le bonus d'XP est terminé : l'XP revient à la normale. "
            "Merci à tous pour votre participation !"
        ),
        color=BOOST_COLOR,
    )


class XPBoostModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        cog: XPBoostCog,
        current: XPBoost | None,
    ) -> None:
        super().__init__(title="Bonus d'XP du serveur", timeout=300)
        self.cog = cog

        def paris(moment: datetime) -> str:
            return moment.astimezone(PARIS_TIMEZONE).strftime("%d/%m/%Y %H:%M")

        self.multiplier = discord.ui.TextInput(
            label="Multiplicateur (1 = arrêter le bonus)",
            placeholder="2",
            default=(
                format_multiplier(current.multiplier)
                if current is not None
                else None
            ),
            max_length=6,
        )
        self.start = discord.ui.TextInput(
            label="Début, heure de Paris (vide = maintenant)",
            placeholder="24/12 00:00",
            default=paris(current.starts_at) if current is not None else None,
            required=False,
            max_length=20,
        )
        self.end = discord.ui.TextInput(
            label="Fin, heure de Paris",
            placeholder="26/12 23:59",
            default=paris(current.ends_at) if current is not None else None,
            required=False,
            max_length=20,
        )
        self.label = discord.ui.TextInput(
            label="Nom du bonus",
            placeholder="Bonus de Noël",
            default=current.label if current is not None else None,
            required=False,
            max_length=60,
        )
        self.announce = discord.ui.TextInput(
            label="Annoncer début et fin dans ce salon ? oui/non",
            default="oui",
            max_length=3,
        )

        for item in (
            self.multiplier,
            self.start,
            self.end,
            self.label,
            self.announce,
        ):
            self.add_item(item)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild_id = interaction.guild_id

        if guild_id is None:
            return

        now = datetime.now(timezone.utc)

        try:
            parsed = parse_boost_form(
                multiplier_text=str(self.multiplier.value),
                start_text=str(self.start.value or ""),
                end_text=str(self.end.value or ""),
                now=now,
            )
        except ValueError as error:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Bonus non enregistré",
                    description=str(error),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if parsed is None:
            stopped = await self.cog.stop_boost(guild_id)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⏹️ Bonus d'XP arrêté" if stopped else "Aucun bonus",
                    description=(
                        "L'XP revient à la normale."
                        if stopped
                        else "Aucun bonus d'XP n'était programmé."
                    ),
                    color=SUCCESS_COLOR,
                ),
                ephemeral=True,
            )
            return

        multiplier, starts_at, ends_at = parsed
        label = str(self.label.value or "").strip() or "Bonus d'XP"
        announce = str(self.announce.value).strip().lower() in {
            "oui",
            "o",
            "yes",
            "y",
        }

        await self.cog.save_boost(
            guild_id=guild_id,
            multiplier=multiplier,
            starts_at=starts_at,
            ends_at=ends_at,
            label=label,
            channel_id=interaction.channel_id if announce else None,
            actor_id=interaction.user.id,
        )

        state = (
            "est **actif dès maintenant**"
            if starts_at <= now
            else f"commencera le {format_paris(starts_at)}"
        )
        announce_text = (
            "Le début et la fin seront annoncés dans ce salon."
            if announce
            else "Aucune annonce ne sera publiée."
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Bonus d'XP enregistré",
                description=(
                    f"**{label}** : XP ×{format_multiplier(multiplier)}\n"
                    f"Le bonus {state} et se termine le "
                    f"{format_paris(ends_at)}.\n\n{announce_text}\n"
                    "Il s'ajoute aux multiplicateurs de rôle."
                ),
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )


class XPBoostCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot
        self._cache: dict[int, tuple[float, XPBoost | None]] = {}

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def initialize_database(self) -> None:
        await self.get_pool().execute(
            """
            CREATE TABLE IF NOT EXISTS xp_boosts (
                guild_id BIGINT PRIMARY KEY,
                multiplier NUMERIC(4, 2) NOT NULL
                    CHECK (multiplier > 1 AND multiplier <= 5),
                starts_at TIMESTAMPTZ NOT NULL,
                ends_at TIMESTAMPTZ NOT NULL,
                label VARCHAR(100) NOT NULL,
                channel_id BIGINT,
                start_announced BOOLEAN NOT NULL DEFAULT FALSE,
                end_announced BOOLEAN NOT NULL DEFAULT FALSE,
                created_by BIGINT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CHECK (ends_at > starts_at)
            )
            """
        )

    async def cog_load(self) -> None:
        await self.initialize_database()

        if not self.announcement_loop.is_running():
            self.announcement_loop.start()

    def cog_unload(self) -> None:
        self.announcement_loop.cancel()

    async def get_boost(
        self,
        guild_id: int,
        *,
        use_cache: bool = True,
    ) -> XPBoost | None:
        cached = self._cache.get(guild_id)

        if use_cache and cached is not None and cached[0] > time.monotonic():
            return cached[1]

        record = await self.get_pool().fetchrow(
            """
            SELECT multiplier, starts_at, ends_at, label
            FROM xp_boosts
            WHERE guild_id = $1
            """,
            guild_id,
        )

        boost = (
            XPBoost(
                multiplier=Decimal(str(record["multiplier"])),
                starts_at=record["starts_at"],
                ends_at=record["ends_at"],
                label=str(record["label"]),
            )
            if record is not None
            else None
        )

        self._cache[guild_id] = (time.monotonic() + CACHE_TTL_SECONDS, boost)

        return boost

    async def get_active_multiplier(
        self,
        guild_id: int,
        moment: datetime | None = None,
    ) -> Decimal:
        """Multiplicateur du bonus en cours, 1 s'il n'y en a pas."""
        try:
            boost = await self.get_boost(guild_id)
        except Exception:
            LOGGER.exception("Impossible de lire le bonus d'XP du serveur %s", guild_id)
            return Decimal("1")

        current = moment or datetime.now(timezone.utc)

        if boost is None or not boost.is_active(current):
            return Decimal("1")

        return boost.multiplier

    async def save_boost(
        self,
        *,
        guild_id: int,
        multiplier: Decimal,
        starts_at: datetime,
        ends_at: datetime,
        label: str,
        channel_id: int | None,
        actor_id: int,
    ) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO xp_boosts (
                guild_id, multiplier, starts_at, ends_at, label,
                channel_id, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (guild_id)
            DO UPDATE SET
                multiplier = EXCLUDED.multiplier,
                starts_at = EXCLUDED.starts_at,
                ends_at = EXCLUDED.ends_at,
                label = EXCLUDED.label,
                channel_id = EXCLUDED.channel_id,
                created_by = EXCLUDED.created_by,
                start_announced = FALSE,
                end_announced = FALSE,
                updated_at = NOW()
            """,
            guild_id,
            multiplier,
            starts_at,
            ends_at,
            label[:100],
            channel_id,
            actor_id,
        )
        self._cache.pop(guild_id, None)

    async def stop_boost(self, guild_id: int) -> bool:
        result = await self.get_pool().execute(
            "DELETE FROM xp_boosts WHERE guild_id = $1",
            guild_id,
        )
        self._cache.pop(guild_id, None)

        return result != "DELETE 0"

    async def open_admin_modal(
        self,
        interaction: discord.Interaction,
    ) -> None:
        current = None

        if interaction.guild_id is not None:
            current = await self.get_boost(interaction.guild_id, use_cache=False)

            if current is not None and current.ends_at <= datetime.now(timezone.utc):
                current = None

        await interaction.response.send_modal(
            XPBoostModal(cog=self, current=current)
        )

    @tasks.loop(seconds=60)
    async def announcement_loop(self) -> None:
        try:
            records = await self.get_pool().fetch(
                """
                SELECT *
                FROM xp_boosts
                WHERE channel_id IS NOT NULL
                  AND (NOT start_announced OR NOT end_announced)
                  AND starts_at <= NOW()
                """
            )
        except Exception:
            LOGGER.exception("Impossible de lire les bonus d'XP à annoncer.")
            return

        now = datetime.now(timezone.utc)

        for record in records:
            boost = XPBoost(
                multiplier=Decimal(str(record["multiplier"])),
                starts_at=record["starts_at"],
                ends_at=record["ends_at"],
                label=str(record["label"]),
            )
            channel = self.bot.get_channel(int(record["channel_id"]))
            ended = now >= boost.ends_at

            try:
                if not record["start_announced"] and not ended:
                    if isinstance(channel, discord.abc.Messageable):
                        await channel.send(embed=start_announcement(boost))

                    await self.mark(record["guild_id"], "start_announced")

                elif ended and not record["end_announced"]:
                    # Pas d'annonce de fin pour un bonus jamais annoncé
                    # (bot éteint pendant toute sa durée).
                    if record["start_announced"] and isinstance(
                        channel,
                        discord.abc.Messageable,
                    ):
                        await channel.send(embed=end_announcement(boost))

                    await self.mark(record["guild_id"], "end_announced")
            except discord.HTTPException:
                LOGGER.warning(
                    "Annonce du bonus d'XP impossible dans le salon %s.",
                    record["channel_id"],
                )
                await self.mark(record["guild_id"], "start_announced")
                if ended:
                    await self.mark(record["guild_id"], "end_announced")

    async def mark(self, guild_id: int, column: str) -> None:
        assert column in {"start_announced", "end_announced"}
        await self.get_pool().execute(
            f"UPDATE xp_boosts SET {column} = TRUE WHERE guild_id = $1",
            guild_id,
        )

    @announcement_loop.before_loop
    async def before_announcement_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(XPBoostCog(bot))
    LOGGER.info("Bonus d'XP du serveur chargé")
