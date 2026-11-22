"""
/hebdomadaire et /mensuel : une récompense par semaine et par mois,
comme /quotidien mais en plus gros.

- Semaine : du lundi 00h00 au dimanche 23h59 (heure de Paris).
- Mois : du 1er à 00h00 à la fin du mois (heure de Paris).
- Série : réclamer plusieurs semaines (ou mois) d'affilée donne un
  bonus en pourcentage, plafonné.

Les montants se règlent dans /quotidien-admin (boutons Hebdomadaire
et Mensuel).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from bot.shared.economy import refresh_level_roles
from bot.shared.panels import first_value

LOGGER = logging.getLogger(__name__)

PARIS = ZoneInfo("Europe/Paris")
WEEKLY, MONTHLY = "weekly", "monthly"

DEFAULTS = {
    WEEKLY: {"xp": 700, "coins": 100, "bonus_percent": 10, "bonus_max": 50},
    MONTHLY: {"xp": 3000, "coins": 500, "bonus_percent": 10, "bonus_max": 50},
}
LABELS = {
    WEEKLY: {
        "title": "Récompense hebdomadaire",
        "emoji": "🗓️",
        "unit": "semaine",
        "units": "semaines",
        "command": "/hebdomadaire",
        "already": "cette semaine",
    },
    MONTHLY: {
        "title": "Récompense mensuelle",
        "emoji": "📅",
        "unit": "mois",
        "units": "mois",
        "command": "/mensuel",
        "already": "ce mois-ci",
    },
}
MAX_AMOUNT = 10_000_000

COLOR = discord.Color.from_rgb(242, 140, 40)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
WARNING_COLOR = discord.Color.from_rgb(240, 180, 60)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)


def format_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


# ------------------------------------------------------------
# PÉRIODES (heure de Paris)
# ------------------------------------------------------------


def period_start(kind: str, moment: datetime) -> date:
    """Premier jour de la période en cours : lundi ou 1er du mois."""
    day = moment.astimezone(PARIS).date()

    if kind == WEEKLY:
        return day - timedelta(days=day.weekday())

    return day.replace(day=1)


def previous_period_start(kind: str, start: date) -> date:
    if kind == WEEKLY:
        return start - timedelta(days=7)

    return (start - timedelta(days=1)).replace(day=1)


def next_period_start(kind: str, start: date) -> date:
    if kind == WEEKLY:
        return start + timedelta(days=7)

    return (start.replace(day=28) + timedelta(days=4)).replace(day=1)


def next_reset(kind: str, moment: datetime) -> datetime:
    """Date (UTC) à laquelle la prochaine récompense devient disponible."""
    upcoming = next_period_start(kind, period_start(kind, moment))
    return datetime.combine(upcoming, time(0, 0), tzinfo=PARIS).astimezone(timezone.utc)


def streak_bonus(streak: int, bonus_percent: int, bonus_max: int) -> int:
    """Bonus en % : +bonus_percent par période d'affilée après la première."""
    return max(0, min((streak - 1) * bonus_percent, bonus_max))


def apply_bonus(amount: int, percent: int) -> int:
    return amount + amount * percent // 100


@dataclass
class ClaimResult:
    status: str  # "claimed", "already", "disabled"
    xp: int = 0
    coins: int = 0
    streak: int = 0
    best_streak: int = 0
    bonus: int = 0
    old_xp: int = 0
    new_xp: int = 0
    next_at: datetime | None = None


# ------------------------------------------------------------
# RÉGLAGES (modal de /quotidien-admin)
# ------------------------------------------------------------


def parse_amount(text: str, name: str, maximum: int = MAX_AMOUNT) -> int:
    cleaned = text.replace(" ", "").replace(" ", "").replace("%", "")

    if not cleaned.isdigit() or int(cleaned) > maximum:
        raise ValueError(f"{name} : écris un nombre entre 0 et {format_number(maximum)}.")

    return int(cleaned)


class PeriodicSettingsModal(discord.ui.Modal):
    def __init__(self, cog: PeriodicRewardsCog, kind: str, settings: dict) -> None:
        super().__init__(title=f"{LABELS[kind]['emoji']} {LABELS[kind]['title']}", timeout=600)
        self.cog = cog
        self.kind = kind
        units = LABELS[kind]["units"]

        def field(label: str, value: int, description: str) -> discord.ui.TextInput:
            component = discord.ui.TextInput(default=str(value), max_length=12)
            self.add_item(discord.ui.Label(text=label, description=description, component=component))
            return component

        self.xp = field("XP", settings["xp"], "XP gagnée à chaque réclamation (avant bonus).")
        self.coins = field("Pièces", settings["coins"], "Pièces gagnées à chaque réclamation (avant bonus).")
        self.bonus_percent = field(
            "Bonus de série (%)",
            settings["bonus_percent"],
            f"Bonus ajouté par {LABELS[kind]['unit']} réclamé(e) d'affilée. 0 = pas de bonus.",
        )
        self.bonus_max = field("Bonus maximum (%)", settings["bonus_max"], f"Plafond du bonus de série en {units}.")

        self.enabled = discord.ui.Select(
            options=[
                discord.SelectOption(label="Activée", value="on", emoji="✅", default=settings["enabled"]),
                discord.SelectOption(label="Désactivée", value="off", emoji="❌", default=not settings["enabled"]),
            ]
        )
        self.add_item(discord.ui.Label(text="État", component=self.enabled))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            values = {
                "xp": parse_amount(self.xp.value, "XP"),
                "coins": parse_amount(self.coins.value, "Pièces"),
                "bonus_percent": parse_amount(self.bonus_percent.value, "Bonus de série", 1000),
                "bonus_max": parse_amount(self.bonus_max.value, "Bonus maximum", 1000),
                "enabled": first_value(self.enabled, "on") == "on",
            }
        except ValueError as error:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"❌ {error}", color=ERROR_COLOR), ephemeral=True
            )
            return

        await self.cog.save_settings(interaction.guild_id, self.kind, values)
        labels = LABELS[self.kind]
        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"✅ {labels['title']} enregistrée",
                description=describe_settings(self.kind, values),
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )


def describe_settings(kind: str, settings: dict) -> str:
    labels = LABELS[kind]
    lines = [
        f"État : **{'activée ✅' if settings['enabled'] else 'désactivée ❌'}** (`{labels['command']}`)",
        f"✨ **{format_number(settings['xp'])} XP** · 💰 **{format_number(settings['coins'])} pièces**",
    ]

    if settings["bonus_percent"] and settings["bonus_max"]:
        lines.append(
            f"🔥 Série : +{settings['bonus_percent']} % par {labels['unit']} d'affilée, "
            f"jusqu'à +{settings['bonus_max']} %"
        )
    else:
        lines.append("🔥 Pas de bonus de série")

    return "\n".join(lines)


# ------------------------------------------------------------
# COG
# ------------------------------------------------------------


class PeriodicRewardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
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
            CREATE TABLE IF NOT EXISTS periodic_reward_settings (
                guild_id BIGINT NOT NULL,
                kind VARCHAR(10) NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                xp BIGINT NOT NULL CHECK (xp >= 0),
                coins BIGINT NOT NULL CHECK (coins >= 0),
                bonus_percent INTEGER NOT NULL DEFAULT 10 CHECK (bonus_percent >= 0),
                bonus_max INTEGER NOT NULL DEFAULT 50 CHECK (bonus_max >= 0),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, kind)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS periodic_reward_claims (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                kind VARCHAR(10) NOT NULL,
                period_start DATE NOT NULL,
                streak INTEGER NOT NULL,
                xp BIGINT NOT NULL,
                coins BIGINT NOT NULL,
                claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id, kind, period_start)
            )
            """
        )

    # -------- réglages --------

    async def get_settings(self, guild_id: int, kind: str) -> dict:
        record = await self.get_pool().fetchrow(
            "SELECT * FROM periodic_reward_settings WHERE guild_id = $1 AND kind = $2",
            guild_id,
            kind,
        )

        if record is None:
            return {**DEFAULTS[kind], "enabled": True}

        return {
            "xp": int(record["xp"]),
            "coins": int(record["coins"]),
            "bonus_percent": int(record["bonus_percent"]),
            "bonus_max": int(record["bonus_max"]),
            "enabled": bool(record["enabled"]),
        }

    async def save_settings(self, guild_id: int, kind: str, values: dict) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO periodic_reward_settings
                (guild_id, kind, enabled, xp, coins, bonus_percent, bonus_max)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (guild_id, kind)
            DO UPDATE SET enabled = EXCLUDED.enabled,
                          xp = EXCLUDED.xp,
                          coins = EXCLUDED.coins,
                          bonus_percent = EXCLUDED.bonus_percent,
                          bonus_max = EXCLUDED.bonus_max,
                          updated_at = NOW()
            """,
            guild_id,
            kind,
            values["enabled"],
            values["xp"],
            values["coins"],
            values["bonus_percent"],
            values["bonus_max"],
        )

    async def open_admin(self, interaction: discord.Interaction, kind: str) -> None:
        """Appelé par les boutons de /quotidien-admin."""
        settings = await self.get_settings(interaction.guild_id, kind)
        await interaction.response.send_modal(PeriodicSettingsModal(self, kind, settings))

    # -------- réclamation --------

    async def claim(self, guild_id: int, user_id: int, kind: str, now: datetime | None = None) -> ClaimResult:
        now = now or datetime.now(timezone.utc)
        settings = await self.get_settings(guild_id, kind)
        start = period_start(kind, now)
        next_at = next_reset(kind, now)

        if not settings["enabled"]:
            return ClaimResult("disabled", next_at=next_at)

        async with self.get_pool().acquire() as connection:
            async with connection.transaction():
                # Même verrou que le reste de l'économie : pas de double paiement.
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"progression:{guild_id}:{user_id}",
                )
                rows = await connection.fetch(
                    """
                    SELECT period_start, streak
                    FROM periodic_reward_claims
                    WHERE guild_id = $1 AND user_id = $2 AND kind = $3
                      AND period_start >= $4
                    """,
                    guild_id,
                    user_id,
                    kind,
                    previous_period_start(kind, start),
                )
                best = await connection.fetchval(
                    """
                    SELECT COALESCE(MAX(streak), 0) FROM periodic_reward_claims
                    WHERE guild_id = $1 AND user_id = $2 AND kind = $3
                    """,
                    guild_id,
                    user_id,
                    kind,
                )
                by_start = {row["period_start"]: int(row["streak"]) for row in rows}

                if start in by_start:
                    return ClaimResult(
                        "already",
                        streak=by_start[start],
                        best_streak=int(best or 0),
                        next_at=next_at,
                    )

                streak = by_start.get(previous_period_start(kind, start), 0) + 1
                bonus = streak_bonus(streak, settings["bonus_percent"], settings["bonus_max"])
                xp = apply_bonus(settings["xp"], bonus)
                coins = apply_bonus(settings["coins"], bonus)

                await connection.execute(
                    """
                    INSERT INTO periodic_reward_claims
                        (guild_id, user_id, kind, period_start, streak, xp, coins)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    guild_id,
                    user_id,
                    kind,
                    start,
                    streak,
                    xp,
                    coins,
                )
                await connection.execute(
                    """
                    INSERT INTO progression_members (guild_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id, user_id) DO NOTHING
                    """,
                    guild_id,
                    user_id,
                )
                old_xp = int(
                    await connection.fetchval(
                        """
                        SELECT total_xp FROM progression_members
                        WHERE guild_id = $1 AND user_id = $2
                        FOR UPDATE
                        """,
                        guild_id,
                        user_id,
                    )
                    or 0
                )
                await connection.execute(
                    """
                    UPDATE progression_members
                    SET total_xp = total_xp + $3,
                        wallet = wallet + $4,
                        lifetime_coins = lifetime_coins + $4,
                        updated_at = NOW()
                    WHERE guild_id = $1 AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                    xp,
                    coins,
                )

                if coins:
                    await connection.execute(
                        """
                        INSERT INTO progression_transactions
                            (guild_id, user_id, actor_id, amount, transaction_type, reason)
                        VALUES ($1, $2, NULL, $3, $4, $5)
                        """,
                        guild_id,
                        user_id,
                        coins,
                        kind,
                        LABELS[kind]["title"],
                    )

        return ClaimResult(
            "claimed",
            xp=xp,
            coins=coins,
            streak=streak,
            best_streak=max(int(best or 0), streak),
            bonus=bonus,
            old_xp=old_xp,
            new_xp=old_xp + xp,
            next_at=next_at,
        )

    async def run_claim(self, interaction: discord.Interaction, kind: str) -> None:
        labels = LABELS[kind]
        # Comme /quotidien : tout est visible par le membre seul.
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            result = await self.claim(interaction.guild_id, interaction.user.id, kind)
        except Exception:
            LOGGER.exception("Récompense %s impossible", kind)
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ La récompense n'a pas pu être versée. Réessaie dans un instant.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        stamp = int(result.next_at.timestamp()) if result.next_at else None

        if result.status == "disabled":
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ La {labels['title'].lower()} est désactivée sur ce serveur.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if result.status == "already":
            await interaction.followup.send(
                embed=discord.Embed(
                    title=f"⏳ Déjà récupérée {labels['already']}",
                    description=(
                        f"Prochaine {labels['title'].lower()} <t:{stamp}:R> (<t:{stamp}:f>).\n"
                        f"🔥 Série : **{result.streak} {labels['units'] if result.streak > 1 else labels['unit']}** "
                        f"d'affilée"
                    ),
                    color=WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return

        lines = [
            f"✨ **+{format_number(result.xp)} XP**",
            f"💰 **+{format_number(result.coins)} pièces**",
            "",
            f"🔥 Série : **{result.streak} {labels['units'] if result.streak > 1 else labels['unit']}** d'affilée"
            + (f" (bonus **+{result.bonus} %**)" if result.bonus else ""),
        ]

        if result.best_streak > result.streak:
            lines.append(f"🏅 Record : {result.best_streak} {labels['units']}")

        lines.append(f"⏰ Prochaine récompense <t:{stamp}:R>")
        embed = discord.Embed(
            title=f"{labels['emoji']} {labels['title']}",
            description="\n".join(lines),
            color=SUCCESS_COLOR,
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

        try:
            await refresh_level_roles(self.bot, interaction.user, result.old_xp, result.new_xp)
        except Exception:
            LOGGER.exception("Rôles de niveau non mis à jour après %s", kind)

    @app_commands.command(name="hebdomadaire", description="Récupère ta récompense de la semaine.")
    @app_commands.guild_only()
    async def hebdomadaire(self, interaction: discord.Interaction) -> None:
        await self.run_claim(interaction, WEEKLY)

    @app_commands.command(name="mensuel", description="Récupère ta récompense du mois.")
    @app_commands.guild_only()
    async def mensuel(self, interaction: discord.Interaction) -> None:
        await self.run_claim(interaction, MONTHLY)


async def setup(bot: commands.Bot) -> None:
    cog = PeriodicRewardsCog(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info("Récompenses hebdomadaire et mensuelle chargées")
