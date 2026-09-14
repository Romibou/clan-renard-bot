from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands


LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WARNING_COLOR = discord.Color.from_rgb(235, 174, 65)

DAILY_COOLDOWN_HOURS = 24
DAILY_STREAK_GRACE_HOURS = 48


def base_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=COLOR,
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


def warning_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=WARNING_COLOR,
    )


def format_number(
    value: int,
) -> str:
    return f"{int(value):,}".replace(",", " ")


def discord_timestamp(
    value: datetime,
    style: str = "R",
) -> str:
    timestamp = int(
        value.astimezone(timezone.utc).timestamp()
    )

    return f"<t:{timestamp}:{style}>"


def xp_for_level(
    level: int,
) -> int:
    level = max(0, int(level))

    if level == 0:
        return 0

    return (
        5 * (level - 1) * level * (2 * level - 1) // 6
        + 25 * level * (level - 1)
        + 100 * level
    )


def level_from_xp(
    total_xp: int,
) -> int:
    total_xp = max(0, int(total_xp))

    low = 0
    high = 1

    while xp_for_level(high) <= total_xp:
        high *= 2

    while low + 1 < high:
        middle = (low + high) // 2

        if xp_for_level(middle) <= total_xp:
            low = middle
        else:
            high = middle

    return low


@dataclass(slots=True)
class DailyClaimResult:
    claimed: bool
    enabled: bool

    current_streak: int
    best_streak: int
    total_claims: int

    xp_reward: int
    coins_reward: int

    base_xp: int
    base_coins: int

    bonus_xp: int
    bonus_coins: int
    bonus_steps: int

    total_xp: int
    wallet: int

    old_level: int
    new_level: int

    last_claim_at: datetime | None
    next_claim_at: datetime | None
    streak_expires_at: datetime | None


class DailyConfigurationModal(
    discord.ui.Modal,
):
    def __init__(
        self,
        *,
        cog: DailyCog,
        guild_id: int,
        settings: dict[str, Any],
    ) -> None:
        super().__init__(
            title="Configuration du quotidien",
            timeout=300,
        )

        self.cog = cog
        self.guild_id = guild_id

        self.base_xp_input = discord.ui.TextInput(
            label="XP de base",
            placeholder="Exemple : 100",
            default=str(settings["base_xp"]),
            required=True,
            min_length=1,
            max_length=9,
        )

        self.base_coins_input = discord.ui.TextInput(
            label="Pièces de base",
            placeholder="Exemple : 50",
            default=str(settings["base_coins"]),
            required=True,
            min_length=1,
            max_length=9,
        )

        self.streak_xp_bonus_input = discord.ui.TextInput(
            label="Bonus XP par jour de série",
            placeholder="Exemple : 10",
            default=str(
                settings["streak_xp_bonus"]
            ),
            required=True,
            min_length=1,
            max_length=9,
        )

        self.streak_coins_bonus_input = (
            discord.ui.TextInput(
                label="Bonus pièces par jour de série",
                placeholder="Exemple : 5",
                default=str(
                    settings["streak_coins_bonus"]
                ),
                required=True,
                min_length=1,
                max_length=9,
            )
        )

        self.maximum_bonus_days_input = (
            discord.ui.TextInput(
                label="Nombre maximum de jours de bonus",
                placeholder="Exemple : 30",
                default=str(
                    settings["maximum_bonus_days"]
                ),
                required=True,
                min_length=1,
                max_length=4,
            )
        )

        self.add_item(
            self.base_xp_input
        )
        self.add_item(
            self.base_coins_input
        )
        self.add_item(
            self.streak_xp_bonus_input
        )
        self.add_item(
            self.streak_coins_bonus_input
        )
        self.add_item(
            self.maximum_bonus_days_input
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            base_xp = int(
                str(
                    self.base_xp_input.value
                ).strip()
            )

            base_coins = int(
                str(
                    self.base_coins_input.value
                ).strip()
            )

            streak_xp_bonus = int(
                str(
                    self.streak_xp_bonus_input.value
                ).strip()
            )

            streak_coins_bonus = int(
                str(
                    self.streak_coins_bonus_input.value
                ).strip()
            )

            maximum_bonus_days = int(
                str(
                    self.maximum_bonus_days_input.value
                ).strip()
            )
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    (
                        "Tous les champs doivent contenir "
                        "des nombres entiers."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not 0 <= base_xp <= 100_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "XP de base invalide",
                    (
                        "L'XP de base doit être comprise "
                        "entre **0** et **100 000 000**."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not 0 <= base_coins <= 100_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Pièces de base invalides",
                    (
                        "Les pièces de base doivent être "
                        "comprises entre **0** et "
                        "**100 000 000**."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not 0 <= streak_xp_bonus <= 10_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Bonus XP invalide",
                    (
                        "Le bonus d'XP doit être compris "
                        "entre **0** et **10 000 000**."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not 0 <= streak_coins_bonus <= 10_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Bonus de pièces invalide",
                    (
                        "Le bonus de pièces doit être compris "
                        "entre **0** et **10 000 000**."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not 0 <= maximum_bonus_days <= 1_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Limite invalide",
                    (
                        "Le nombre maximum de jours de bonus "
                        "doit être compris entre **0** et "
                        "**1 000**."
                    ),
                ),
                ephemeral=True,
            )
            return

        await self.cog.update_settings(
            guild_id=self.guild_id,
            base_xp=base_xp,
            base_coins=base_coins,
            streak_xp_bonus=streak_xp_bonus,
            streak_coins_bonus=streak_coins_bonus,
            maximum_bonus_days=maximum_bonus_days,
        )

        maximum_reward_xp = (
            base_xp
            + streak_xp_bonus
            * maximum_bonus_days
        )

        maximum_reward_coins = (
            base_coins
            + streak_coins_bonus
            * maximum_bonus_days
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Configuration enregistrée",
                (
                    f"XP de base : "
                    f"**{format_number(base_xp)} XP**\n"
                    f"Pièces de base : "
                    f"**{format_number(base_coins)} pièces**\n\n"
                    f"Bonus par jour de série : "
                    f"**+{format_number(streak_xp_bonus)} XP** "
                    f"et "
                    f"**+{format_number(streak_coins_bonus)} "
                    f"pièces**\n"
                    f"Bonus limité à "
                    f"**{format_number(maximum_bonus_days)} "
                    f"jours**\n\n"
                    f"Récompense maximale : "
                    f"**{format_number(maximum_reward_xp)} XP** "
                    f"et "
                    f"**{format_number(maximum_reward_coins)} "
                    f"pièces**."
                ),
            ),
            ephemeral=True,
        )


class DailyAdminView(
    discord.ui.View,
):
    def __init__(
        self,
        *,
        cog: DailyCog,
        owner_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=600,
        )

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Panneau personnel",
                (
                    "Seul l'administrateur ayant ouvert "
                    "ce panneau peut utiliser ses boutons."
                ),
            ),
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Configuration",
        emoji="⚙️",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def configure_daily(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
        )

        await interaction.response.send_modal(
            DailyConfigurationModal(
                cog=self.cog,
                guild_id=self.guild_id,
                settings=settings,
            )
        )

    @discord.ui.button(
        label="Activer/désactiver",
        emoji="🔌",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def toggle_daily(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
        )

        new_state = not bool(
            settings["enabled"]
        )

        await self.cog.set_enabled(
            guild_id=self.guild_id,
            enabled=new_state,
        )

        updated_embed = (
            await self.cog.build_admin_embed(
                self.guild_id
            )
        )

        await interaction.response.edit_message(
            embed=updated_embed,
            view=self,
        )

        await interaction.followup.send(
            embed=success_embed(
                "État modifié",
                (
                    "La récompense quotidienne est "
                    f"maintenant "
                    f"**{'activée' if new_state else 'désactivée'}**."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Actualiser",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def refresh_panel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        updated_embed = (
            await self.cog.build_admin_embed(
                self.guild_id
            )
        )

        await interaction.response.edit_message(
            embed=updated_embed,
            view=self,
        )


class DailyCog(
    commands.Cog,
):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

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
            CREATE TABLE IF NOT EXISTS daily_settings (
                guild_id BIGINT PRIMARY KEY,

                enabled BOOLEAN NOT NULL DEFAULT TRUE,

                base_xp BIGINT NOT NULL DEFAULT 100
                    CHECK (
                        base_xp >= 0
                        AND base_xp <= 100000000
                    ),

                base_coins BIGINT NOT NULL DEFAULT 50
                    CHECK (
                        base_coins >= 0
                        AND base_coins <= 100000000
                    ),

                streak_xp_bonus BIGINT NOT NULL DEFAULT 10
                    CHECK (
                        streak_xp_bonus >= 0
                        AND streak_xp_bonus <= 10000000
                    ),

                streak_coins_bonus BIGINT NOT NULL DEFAULT 5
                    CHECK (
                        streak_coins_bonus >= 0
                        AND streak_coins_bonus <= 10000000
                    ),

                maximum_bonus_days INTEGER NOT NULL DEFAULT 30
                    CHECK (
                        maximum_bonus_days >= 0
                        AND maximum_bonus_days <= 1000
                    ),

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_members (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,

                current_streak INTEGER NOT NULL DEFAULT 0
                    CHECK (current_streak >= 0),

                best_streak INTEGER NOT NULL DEFAULT 0
                    CHECK (best_streak >= 0),

                total_claims BIGINT NOT NULL DEFAULT 0
                    CHECK (total_claims >= 0),

                last_claim_at TIMESTAMPTZ,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                PRIMARY KEY (
                    guild_id,
                    user_id
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_claims (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,

                streak INTEGER NOT NULL
                    CHECK (streak >= 1),

                xp_reward BIGINT NOT NULL
                    CHECK (xp_reward >= 0),

                coins_reward BIGINT NOT NULL
                    CHECK (coins_reward >= 0),

                base_xp BIGINT NOT NULL
                    CHECK (base_xp >= 0),

                base_coins BIGINT NOT NULL
                    CHECK (base_coins >= 0),

                bonus_xp BIGINT NOT NULL
                    CHECK (bonus_xp >= 0),

                bonus_coins BIGINT NOT NULL
                    CHECK (bonus_coins >= 0),

                claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS daily_members_claim_idx
            ON daily_members (
                guild_id,
                last_claim_at
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS daily_claims_member_idx
            ON daily_claims (
                guild_id,
                user_id,
                claimed_at DESC
            )
            """
        )

        LOGGER.info(
            "Tables du système quotidien vérifiées"
        )

    async def ensure_settings(
        self,
        guild_id: int,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            INSERT INTO daily_settings (
                guild_id
            )
            VALUES ($1)
            ON CONFLICT (guild_id)
            DO NOTHING
            """,
            guild_id,
        )

    async def get_settings(
        self,
        guild_id: int,
    ) -> dict[str, Any]:
        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                enabled,
                base_xp,
                base_coins,
                streak_xp_bonus,
                streak_coins_bonus,
                maximum_bonus_days
            FROM daily_settings
            WHERE guild_id = $1
            """,
            guild_id,
        )

        if record is None:
            raise RuntimeError(
                "La configuration quotidienne est introuvable."
            )

        return {
            "enabled": bool(
                record["enabled"]
            ),
            "base_xp": int(
                record["base_xp"]
            ),
            "base_coins": int(
                record["base_coins"]
            ),
            "streak_xp_bonus": int(
                record["streak_xp_bonus"]
            ),
            "streak_coins_bonus": int(
                record["streak_coins_bonus"]
            ),
            "maximum_bonus_days": int(
                record["maximum_bonus_days"]
            ),
        }

    async def update_settings(
        self,
        *,
        guild_id: int,
        base_xp: int,
        base_coins: int,
        streak_xp_bonus: int,
        streak_coins_bonus: int,
        maximum_bonus_days: int,
    ) -> None:
        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()

        await pool.execute(
            """
            UPDATE daily_settings
            SET
                base_xp = $2,
                base_coins = $3,
                streak_xp_bonus = $4,
                streak_coins_bonus = $5,
                maximum_bonus_days = $6,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            base_xp,
            base_coins,
            streak_xp_bonus,
            streak_coins_bonus,
            maximum_bonus_days,
        )

    async def set_enabled(
        self,
        *,
        guild_id: int,
        enabled: bool,
    ) -> None:
        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()

        await pool.execute(
            """
            UPDATE daily_settings
            SET
                enabled = $2,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            enabled,
        )

    async def build_admin_embed(
        self,
        guild_id: int,
    ) -> discord.Embed:
        settings = await self.get_settings(
            guild_id
        )

        maximum_reward_xp = (
            settings["base_xp"]
            + settings["streak_xp_bonus"]
            * settings["maximum_bonus_days"]
        )

        maximum_reward_coins = (
            settings["base_coins"]
            + settings["streak_coins_bonus"]
            * settings["maximum_bonus_days"]
        )

        embed = base_embed(
            "🎁 Administration du quotidien",
            (
                "Configure les récompenses obtenues avec "
                "`/quotidien`.\n\n"
                "Une récompense peut être récupérée toutes "
                "les **24 heures**.\n"
                "La série est perdue après **48 heures** "
                "sans récupération."
            ),
        )

        embed.add_field(
            name="État",
            value=(
                "Activé ✅"
                if settings["enabled"]
                else "Désactivé ❌"
            ),
            inline=True,
        )

        embed.add_field(
            name="Délai",
            value=(
                f"**{DAILY_COOLDOWN_HOURS} heures**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Expiration de la série",
            value=(
                f"Après **{DAILY_STREAK_GRACE_HOURS} heures**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Récompense de base",
            value=(
                f"✨ **{format_number(settings['base_xp'])} XP**\n"
                f"💰 **{format_number(settings['base_coins'])} "
                "pièces**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Bonus par jour de série",
            value=(
                f"✨ **+{format_number(settings['streak_xp_bonus'])} "
                "XP**\n"
                f"💰 **+{format_number(settings['streak_coins_bonus'])} "
                "pièces**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Limite du bonus",
            value=(
                f"**{format_number(settings['maximum_bonus_days'])} "
                "jours**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Récompense maximale",
            value=(
                f"✨ **{format_number(maximum_reward_xp)} XP**\n"
                f"💰 **{format_number(maximum_reward_coins)} "
                "pièces**"
            ),
            inline=False,
        )

        embed.set_footer(
            text=(
                "Le premier jour donne uniquement la récompense "
                "de base. Le bonus commence au deuxième jour."
            )
        )

        return embed

    async def claim_daily_reward(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> DailyClaimResult:
        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()
        current_time = datetime.now(
            timezone.utc
        )

        cooldown_duration = timedelta(
            hours=DAILY_COOLDOWN_HOURS
        )

        streak_grace_duration = timedelta(
            hours=DAILY_STREAK_GRACE_HOURS
        )

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1, 0)
                    )
                    """,
                    f"daily:{guild_id}:{user_id}",
                )

                settings = await connection.fetchrow(
                    """
                    SELECT
                        enabled,
                        base_xp,
                        base_coins,
                        streak_xp_bonus,
                        streak_coins_bonus,
                        maximum_bonus_days
                    FROM daily_settings
                    WHERE guild_id = $1
                    FOR SHARE
                    """,
                    guild_id,
                )

                if settings is None:
                    raise RuntimeError(
                        "La configuration quotidienne est introuvable."
                    )

                await connection.execute(
                    """
                    INSERT INTO daily_members (
                        guild_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (
                        guild_id,
                        user_id
                    )
                    DO NOTHING
                    """,
                    guild_id,
                    user_id,
                )

                daily_member = await connection.fetchrow(
                    """
                    SELECT
                        current_streak,
                        best_streak,
                        total_claims,
                        last_claim_at
                    FROM daily_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )

                if daily_member is None:
                    raise RuntimeError(
                        "Le profil quotidien n'a pas pu être créé."
                    )

                current_streak = int(
                    daily_member["current_streak"] or 0
                )

                best_streak = int(
                    daily_member["best_streak"] or 0
                )

                total_claims = int(
                    daily_member["total_claims"] or 0
                )

                last_claim_at = (
                    daily_member["last_claim_at"]
                )

                if not bool(settings["enabled"]):
                    return DailyClaimResult(
                        claimed=False,
                        enabled=False,
                        current_streak=current_streak,
                        best_streak=best_streak,
                        total_claims=total_claims,
                        xp_reward=0,
                        coins_reward=0,
                        base_xp=0,
                        base_coins=0,
                        bonus_xp=0,
                        bonus_coins=0,
                        bonus_steps=0,
                        total_xp=0,
                        wallet=0,
                        old_level=0,
                        new_level=0,
                        last_claim_at=last_claim_at,
                        next_claim_at=None,
                        streak_expires_at=None,
                    )

                if last_claim_at is not None:
                    next_claim_at = (
                        last_claim_at
                        + cooldown_duration
                    )

                    streak_expires_at = (
                        last_claim_at
                        + streak_grace_duration
                    )

                    if current_time < next_claim_at:
                        return DailyClaimResult(
                            claimed=False,
                            enabled=True,
                            current_streak=current_streak,
                            best_streak=best_streak,
                            total_claims=total_claims,
                            xp_reward=0,
                            coins_reward=0,
                            base_xp=int(
                                settings["base_xp"]
                            ),
                            base_coins=int(
                                settings["base_coins"]
                            ),
                            bonus_xp=0,
                            bonus_coins=0,
                            bonus_steps=0,
                            total_xp=0,
                            wallet=0,
                            old_level=0,
                            new_level=0,
                            last_claim_at=last_claim_at,
                            next_claim_at=next_claim_at,
                            streak_expires_at=streak_expires_at,
                        )

                if last_claim_at is None:
                    new_streak = 1
                else:
                    elapsed = (
                        current_time
                        - last_claim_at
                    )

                    if elapsed <= streak_grace_duration:
                        new_streak = (
                            current_streak + 1
                        )
                    else:
                        new_streak = 1

                new_best_streak = max(
                    best_streak,
                    new_streak,
                )

                new_total_claims = (
                    total_claims + 1
                )

                base_xp = int(
                    settings["base_xp"]
                )

                base_coins = int(
                    settings["base_coins"]
                )

                streak_xp_bonus = int(
                    settings["streak_xp_bonus"]
                )

                streak_coins_bonus = int(
                    settings["streak_coins_bonus"]
                )

                maximum_bonus_days = int(
                    settings["maximum_bonus_days"]
                )

                bonus_steps = min(
                    max(0, new_streak - 1),
                    maximum_bonus_days,
                )

                bonus_xp = (
                    streak_xp_bonus
                    * bonus_steps
                )

                bonus_coins = (
                    streak_coins_bonus
                    * bonus_steps
                )

                xp_reward = (
                    base_xp
                    + bonus_xp
                )

                coins_reward = (
                    base_coins
                    + bonus_coins
                )

                await connection.execute(
                    """
                    INSERT INTO progression_members (
                        guild_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (
                        guild_id,
                        user_id
                    )
                    DO NOTHING
                    """,
                    guild_id,
                    user_id,
                )

                progression_member = (
                    await connection.fetchrow(
                        """
                        SELECT
                            total_xp,
                            wallet
                        FROM progression_members
                        WHERE guild_id = $1
                          AND user_id = $2
                        FOR UPDATE
                        """,
                        guild_id,
                        user_id,
                    )
                )

                if progression_member is None:
                    raise RuntimeError(
                        "Le profil de progression est introuvable."
                    )

                old_total_xp = int(
                    progression_member["total_xp"] or 0
                )

                old_level = level_from_xp(
                    old_total_xp
                )

                updated_progression = (
                    await connection.fetchrow(
                        """
                        UPDATE progression_members
                        SET
                            total_xp =
                                total_xp + $3,

                            wallet =
                                wallet + $4,

                            lifetime_coins =
                                lifetime_coins + $4,

                            updated_at = NOW()

                        WHERE guild_id = $1
                          AND user_id = $2

                        RETURNING
                            total_xp,
                            wallet
                        """,
                        guild_id,
                        user_id,
                        xp_reward,
                        coins_reward,
                    )
                )

                if updated_progression is None:
                    raise RuntimeError(
                        "La progression n'a pas pu être mise à jour."
                    )

                total_xp = int(
                    updated_progression["total_xp"]
                )

                wallet = int(
                    updated_progression["wallet"]
                )

                new_level = level_from_xp(
                    total_xp
                )

                await connection.execute(
                    """
                    UPDATE daily_members
                    SET
                        current_streak = $3,
                        best_streak = $4,
                        total_claims = $5,
                        last_claim_at = $6,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                    new_streak,
                    new_best_streak,
                    new_total_claims,
                    current_time,
                )

                await connection.execute(
                    """
                    INSERT INTO daily_claims (
                        guild_id,
                        user_id,
                        streak,
                        xp_reward,
                        coins_reward,
                        base_xp,
                        base_coins,
                        bonus_xp,
                        bonus_coins,
                        claimed_at
                    )
                    VALUES (
                        $1,
                        $2,
                        $3,
                        $4,
                        $5,
                        $6,
                        $7,
                        $8,
                        $9,
                        $10
                    )
                    """,
                    guild_id,
                    user_id,
                    new_streak,
                    xp_reward,
                    coins_reward,
                    base_xp,
                    base_coins,
                    bonus_xp,
                    bonus_coins,
                    current_time,
                )

                if coins_reward != 0:
                    await connection.execute(
                        """
                        INSERT INTO progression_transactions (
                            guild_id,
                            user_id,
                            actor_id,
                            amount,
                            transaction_type,
                            reason
                        )
                        VALUES (
                            $1,
                            $2,
                            NULL,
                            $3,
                            'daily_reward',
                            'Récompense quotidienne'
                        )
                        """,
                        guild_id,
                        user_id,
                        coins_reward,
                    )

                next_claim_at = (
                    current_time
                    + cooldown_duration
                )

                streak_expires_at = (
                    current_time
                    + streak_grace_duration
                )

                return DailyClaimResult(
                    claimed=True,
                    enabled=True,
                    current_streak=new_streak,
                    best_streak=new_best_streak,
                    total_claims=new_total_claims,
                    xp_reward=xp_reward,
                    coins_reward=coins_reward,
                    base_xp=base_xp,
                    base_coins=base_coins,
                    bonus_xp=bonus_xp,
                    bonus_coins=bonus_coins,
                    bonus_steps=bonus_steps,
                    total_xp=total_xp,
                    wallet=wallet,
                    old_level=old_level,
                    new_level=new_level,
                    last_claim_at=current_time,
                    next_claim_at=next_claim_at,
                    streak_expires_at=streak_expires_at,
                )

    async def update_level_roles(
        self,
        *,
        member: discord.Member,
        level: int,
    ) -> list[discord.Role]:
        progression_cog = self.bot.get_cog(
            "ProgressionCog"
        )

        if progression_cog is None:
            LOGGER.warning(
                (
                    "Impossible d'actualiser les rôles de niveau "
                    "de %s : ProgressionCog introuvable."
                ),
                member.id,
            )
            return []

        grant_roles = getattr(
            progression_cog,
            "grant_earned_level_roles",
            None,
        )

        if grant_roles is None:
            LOGGER.warning(
                (
                    "La méthode grant_earned_level_roles "
                    "est introuvable dans ProgressionCog."
                )
            )
            return []

        try:
            result = await grant_roles(
                member,
                level,
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'actualiser les rôles "
                    "de niveau de %s."
                ),
                member.id,
            )
            return []

        return list(result or [])

    @app_commands.command(
        name="quotidien",
        description=(
            "Récupère ta récompense quotidienne."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        3.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def quotidien(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Serveur requis",
                    (
                        "Cette commande doit être utilisée "
                        "dans un serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        try:
            result = await self.claim_daily_reward(
                guild_id=guild.id,
                user_id=interaction.user.id,
            )

            if not result.enabled:
                await interaction.followup.send(
                    embed=warning_embed(
                        "Quotidien désactivé",
                        (
                            "Les récompenses quotidiennes "
                            "sont actuellement désactivées "
                            "sur ce serveur."
                        ),
                    ),
                    ephemeral=True,
                )
                return

            if not result.claimed:
                if result.next_claim_at is None:
                    next_claim_text = "inconnue"
                else:
                    next_claim_text = discord_timestamp(
                        result.next_claim_at,
                        "R",
                    )

                if result.streak_expires_at is None:
                    expiration_text = "inconnue"
                else:
                    expiration_text = discord_timestamp(
                        result.streak_expires_at,
                        "R",
                    )

                embed = warning_embed(
                    "Récompense déjà récupérée",
                    (
                        "Tu as déjà récupéré ta récompense "
                        "quotidienne.\n\n"
                        f"🔥 Série actuelle : "
                        f"**{format_number(result.current_streak)} "
                        f"jour"
                        f"{'s' if result.current_streak != 1 else ''}**\n"
                        f"🏆 Meilleure série : "
                        f"**{format_number(result.best_streak)} "
                        f"jour"
                        f"{'s' if result.best_streak != 1 else ''}**\n\n"
                        f"🎁 Prochaine récompense : "
                        f"{next_claim_text}\n"
                        f"⌛ Expiration de la série : "
                        f"{expiration_text}"
                    ),
                )

                if result.next_claim_at is not None:
                    embed.add_field(
                        name="Date de disponibilité",
                        value=discord_timestamp(
                            result.next_claim_at,
                            "F",
                        ),
                        inline=False,
                    )

                await interaction.followup.send(
                    embed=embed,
                    ephemeral=True,
                )
                return

            granted_roles: list[discord.Role] = []

            if isinstance(
                interaction.user,
                discord.Member,
            ):
                granted_roles = (
                    await self.update_level_roles(
                        member=interaction.user,
                        level=result.new_level,
                    )
                )

            bonus_text = ""

            if (
                result.bonus_xp > 0
                or result.bonus_coins > 0
            ):
                bonus_text = (
                    "\n\n**Bonus de série :**\n"
                    f"✨ +{format_number(result.bonus_xp)} XP\n"
                    f"💰 +{format_number(result.bonus_coins)} "
                    "pièces"
                )

            level_text = ""

            if result.new_level > result.old_level:
                level_text = (
                    "\n\n🎉 Tu es passé"
                    f"{'e' if getattr(interaction.user, 'display_name', '').endswith('e') else ''} "
                    f"du niveau **{result.old_level}** "
                    f"au niveau **{result.new_level}** !"
                )

            roles_text = ""

            if granted_roles:
                roles_text = (
                    "\n🎭 Nouveau rôle de niveau : "
                    + ", ".join(
                        role.mention
                        for role in granted_roles
                    )
                )

            embed = success_embed(
                "Récompense quotidienne récupérée",
                (
                    f"✨ Tu as reçu "
                    f"**{format_number(result.xp_reward)} XP**.\n"
                    f"💰 Tu as reçu "
                    f"**{format_number(result.coins_reward)} "
                    f"pièces**."
                    f"{bonus_text}"
                    f"{level_text}"
                    f"{roles_text}"
                ),
            )

            embed.add_field(
                name="🔥 Série actuelle",
                value=(
                    f"**{format_number(result.current_streak)} "
                    f"jour"
                    f"{'s' if result.current_streak != 1 else ''}**"
                ),
                inline=True,
            )

            embed.add_field(
                name="🏆 Meilleure série",
                value=(
                    f"**{format_number(result.best_streak)} "
                    f"jour"
                    f"{'s' if result.best_streak != 1 else ''}**"
                ),
                inline=True,
            )

            embed.add_field(
                name="🎁 Récompenses récupérées",
                value=(
                    f"**{format_number(result.total_claims)}**"
                ),
                inline=True,
            )

            embed.add_field(
                name="Progression actuelle",
                value=(
                    f"Niveau : **{result.new_level}**\n"
                    f"XP totale : "
                    f"**{format_number(result.total_xp)}**\n"
                    f"Portefeuille : "
                    f"**{format_number(result.wallet)} pièces**"
                ),
                inline=False,
            )

            if result.next_claim_at is not None:
                embed.add_field(
                    name="Prochaine récompense",
                    value=(
                        f"{discord_timestamp(result.next_claim_at, 'R')}\n"
                        f"{discord_timestamp(result.next_claim_at, 'F')}"
                    ),
                    inline=False,
                )

            if result.streak_expires_at is not None:
                embed.set_footer(
                    text=(
                        "Tu disposes de 48 heures après cette "
                        "récupération pour conserver ta série."
                    )
                )

            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
            )

        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'attribuer la récompense "
                    "quotidienne de %s sur le serveur %s."
                ),
                interaction.user.id,
                guild.id,
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Erreur",
                    (
                        "Ta récompense quotidienne n'a pas "
                        "pu être récupérée.\n"
                        "Aucune récompense n'a été perdue."
                    ),
                ),
                ephemeral=True,
            )

    @app_commands.command(
        name="quotidien-admin",
        description=(
            "Configure les récompenses quotidiennes."
        ),
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.guild_only()
    async def quotidien_admin(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    (
                        "Cette commande doit être utilisée "
                        "dans un serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        try:
            embed = await self.build_admin_embed(
                guild.id
            )

            view = DailyAdminView(
                cog=self,
                owner_id=interaction.user.id,
                guild_id=guild.id,
            )

            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True,
            )

        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'ouvrir l'administration "
                    "du quotidien sur le serveur %s."
                ),
                guild.id,
            )

            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=error_embed(
                        "Erreur",
                        (
                            "Le panneau du quotidien "
                            "n'a pas pu être ouvert."
                        ),
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Erreur",
                        (
                            "Le panneau du quotidien "
                            "n'a pas pu être ouvert."
                        ),
                    ),
                    ephemeral=True,
                )


async def setup(
    bot: commands.Bot,
) -> None:
    cog = DailyCog(
        bot
    )

    await cog.initialize_database()
    await bot.add_cog(
        cog
    )

    LOGGER.info(
        "Système permanent de récompenses quotidiennes initialisé"
    )
