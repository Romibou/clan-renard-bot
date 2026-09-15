from __future__ import annotations

import asyncio
import io
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.shared.statistics_card import render_statistics_card


LOGGER = logging.getLogger(__name__)

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
STATISTICS_UPDATE_INTERVAL_SECONDS = 60

ERROR_COLOR = discord.Color.from_rgb(
    220,
    75,
    85,
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


def xp_for_level(
    level: int,
) -> int:
    """
    Retourne la quantité totale d'XP nécessaire
    pour atteindre un niveau.
    """
    level = max(
        0,
        int(level),
    )

    if level == 0:
        return 0

    return (
        5
        * (level - 1)
        * level
        * (2 * level - 1)
        // 6
        + 25 * level * (level - 1)
        + 100 * level
    )


def level_from_xp(
    total_xp: int,
) -> int:
    """
    Retourne le niveau correspondant à une quantité totale d'XP.
    """
    total_xp = max(
        0,
        int(total_xp),
    )

    low = 0
    high = 1

    while xp_for_level(high) <= total_xp:
        high *= 2

    while low + 1 < high:
        middle = (
            low + high
        ) // 2

        if xp_for_level(middle) <= total_xp:
            low = middle
        else:
            high = middle

    return low


def current_paris_date() -> date:
    """
    Retourne la date actuelle dans le fuseau Europe/Paris.
    """
    return datetime.now(
        PARIS_TIMEZONE
    ).date()


def normalize_period(
    period: str,
) -> str:
    """
    Vérifie et normalise la période demandée.
    """
    normalized = str(
        period
    ).strip().lower()

    if normalized not in {
        "today",
        "7d",
    }:
        raise ValueError(
            "La période doit être `today` ou `7d`."
        )

    return normalized


class StatisticsCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

        self._synchronization_lock = (
            asyncio.Lock()
        )

    async def cog_load(
        self,
    ) -> None:
        if not self.statistics_update_loop.is_running():
            self.statistics_update_loop.start()

    def cog_unload(
        self,
    ) -> None:
        if self.statistics_update_loop.is_running():
            self.statistics_update_loop.cancel()

    def get_pool(
        self,
    ):
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

    def get_background_path(
        self,
    ) -> Path:
        return (
            Path(__file__).resolve().parents[2]
            / "assets"
            / "statistics"
            / "statistics_background.png"
        )

    async def initialize_database(
        self,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS statistics_member_state (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,

                total_xp BIGINT NOT NULL DEFAULT 0,
                wallet BIGINT NOT NULL DEFAULT 0,
                lifetime_coins BIGINT NOT NULL DEFAULT 0,
                rewarded_messages BIGINT NOT NULL DEFAULT 0,
                rewarded_minutes BIGINT NOT NULL DEFAULT 0,

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
            CREATE TABLE IF NOT EXISTS statistics_daily (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                statistic_date DATE NOT NULL,

                xp_gained BIGINT NOT NULL DEFAULT 0
                    CHECK (xp_gained >= 0),

                coins_gained BIGINT NOT NULL DEFAULT 0
                    CHECK (coins_gained >= 0),

                coins_spent BIGINT NOT NULL DEFAULT 0
                    CHECK (coins_spent >= 0),

                rewarded_messages BIGINT NOT NULL DEFAULT 0
                    CHECK (rewarded_messages >= 0),

                voice_minutes BIGINT NOT NULL DEFAULT 0
                    CHECK (voice_minutes >= 0),

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                PRIMARY KEY (
                    guild_id,
                    user_id,
                    statistic_date
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS statistics_rank_snapshots (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                snapshot_date DATE NOT NULL,

                xp_rank INTEGER NOT NULL
                    CHECK (xp_rank >= 1),

                money_rank INTEGER NOT NULL
                    CHECK (money_rank >= 1),

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                PRIMARY KEY (
                    guild_id,
                    user_id,
                    snapshot_date
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS statistics_daily_member_idx
            ON statistics_daily (
                guild_id,
                user_id,
                statistic_date DESC
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS statistics_rank_member_idx
            ON statistics_rank_snapshots (
                guild_id,
                user_id,
                snapshot_date DESC
            )
            """
        )

        LOGGER.info(
            "Tables du système de statistiques vérifiées"
        )

    async def capture_daily_ranks(
        self,
        *,
        connection: Any,
        guild_id: int,
        snapshot_date: date,
    ) -> None:
        already_captured = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM statistics_rank_snapshots
                WHERE guild_id = $1
                  AND snapshot_date = $2
            )
            """,
            guild_id,
            snapshot_date,
        )

        if already_captured:
            return

        await connection.execute(
            """
            WITH ranked_members AS (
                SELECT
                    guild_id,
                    user_id,

                    ROW_NUMBER() OVER (
                        ORDER BY
                            total_xp DESC,
                            wallet DESC,
                            user_id ASC
                    ) AS xp_rank,

                    ROW_NUMBER() OVER (
                        ORDER BY
                            wallet DESC,
                            total_xp DESC,
                            user_id ASC
                    ) AS money_rank

                FROM progression_members
                WHERE guild_id = $1
            )
            INSERT INTO statistics_rank_snapshots (
                guild_id,
                user_id,
                snapshot_date,
                xp_rank,
                money_rank
            )
            SELECT
                guild_id,
                user_id,
                $2,
                xp_rank,
                money_rank
            FROM ranked_members
            ON CONFLICT (
                guild_id,
                user_id,
                snapshot_date
            )
            DO NOTHING
            """,
            guild_id,
            snapshot_date,
        )

    async def synchronize_guild(
        self,
        guild_id: int,
    ) -> None:
        async with self._synchronization_lock:
            pool = self.get_pool()

            statistic_date = (
                current_paris_date()
            )

            async with pool.acquire() as connection:
                async with connection.transaction():
                    await self.capture_daily_ranks(
                        connection=connection,
                        guild_id=guild_id,
                        snapshot_date=statistic_date,
                    )

                    current_records = await connection.fetch(
                        """
                        SELECT
                            members.user_id,
                            members.total_xp,
                            members.wallet,
                            members.lifetime_coins,
                            members.rewarded_messages,

                            COALESCE(
                                voice.rewarded_minutes,
                                0
                            ) AS rewarded_minutes

                        FROM progression_members AS members

                        LEFT JOIN progression_voice_rewards AS voice
                            ON voice.guild_id = members.guild_id
                           AND voice.user_id = members.user_id

                        WHERE members.guild_id = $1
                        """,
                        guild_id,
                    )

                    if not current_records:
                        return

                    state_records = await connection.fetch(
                        """
                        SELECT
                            user_id,
                            total_xp,
                            wallet,
                            lifetime_coins,
                            rewarded_messages,
                            rewarded_minutes
                        FROM statistics_member_state
                        WHERE guild_id = $1
                        """,
                        guild_id,
                    )

                    previous_states = {
                        int(record["user_id"]): record
                        for record in state_records
                    }

                    daily_updates: list[
                        tuple[
                            int,
                            int,
                            date,
                            int,
                            int,
                            int,
                            int,
                            int,
                        ]
                    ] = []

                    state_updates: list[
                        tuple[
                            int,
                            int,
                            int,
                            int,
                            int,
                            int,
                            int,
                        ]
                    ] = []

                    for record in current_records:
                        user_id = int(
                            record["user_id"]
                        )

                        total_xp = int(
                            record["total_xp"]
                            or 0
                        )

                        wallet = int(
                            record["wallet"]
                            or 0
                        )

                        lifetime_coins = int(
                            record["lifetime_coins"]
                            or 0
                        )

                        rewarded_messages = int(
                            record["rewarded_messages"]
                            or 0
                        )

                        rewarded_minutes = int(
                            record["rewarded_minutes"]
                            or 0
                        )

                        previous = (
                            previous_states.get(
                                user_id
                            )
                        )

                        if previous is not None:
                            previous_xp = int(
                                previous["total_xp"]
                                or 0
                            )

                            previous_wallet = int(
                                previous["wallet"]
                                or 0
                            )

                            previous_lifetime = int(
                                previous["lifetime_coins"]
                                or 0
                            )

                            previous_messages = int(
                                previous["rewarded_messages"]
                                or 0
                            )

                            previous_minutes = int(
                                previous["rewarded_minutes"]
                                or 0
                            )

                            xp_gained = max(
                                0,
                                total_xp
                                - previous_xp,
                            )

                            coins_gained = max(
                                0,
                                lifetime_coins
                                - previous_lifetime,
                            )

                            wallet_difference = (
                                wallet
                                - previous_wallet
                            )

                            coins_spent = max(
                                0,
                                coins_gained
                                - wallet_difference,
                            )

                            messages_gained = max(
                                0,
                                rewarded_messages
                                - previous_messages,
                            )

                            voice_minutes_gained = max(
                                0,
                                rewarded_minutes
                                - previous_minutes,
                            )

                            if any(
                                (
                                    xp_gained,
                                    coins_gained,
                                    coins_spent,
                                    messages_gained,
                                    voice_minutes_gained,
                                )
                            ):
                                daily_updates.append(
                                    (
                                        guild_id,
                                        user_id,
                                        statistic_date,
                                        xp_gained,
                                        coins_gained,
                                        coins_spent,
                                        messages_gained,
                                        voice_minutes_gained,
                                    )
                                )

                        state_updates.append(
                            (
                                guild_id,
                                user_id,
                                total_xp,
                                wallet,
                                lifetime_coins,
                                rewarded_messages,
                                rewarded_minutes,
                            )
                        )

                    if daily_updates:
                        await connection.executemany(
                            """
                            INSERT INTO statistics_daily (
                                guild_id,
                                user_id,
                                statistic_date,
                                xp_gained,
                                coins_gained,
                                coins_spent,
                                rewarded_messages,
                                voice_minutes,
                                updated_at
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
                                NOW()
                            )
                            ON CONFLICT (
                                guild_id,
                                user_id,
                                statistic_date
                            )
                            DO UPDATE SET
                                xp_gained =
                                    statistics_daily.xp_gained
                                    + EXCLUDED.xp_gained,

                                coins_gained =
                                    statistics_daily.coins_gained
                                    + EXCLUDED.coins_gained,

                                coins_spent =
                                    statistics_daily.coins_spent
                                    + EXCLUDED.coins_spent,

                                rewarded_messages =
                                    statistics_daily.rewarded_messages
                                    + EXCLUDED.rewarded_messages,

                                voice_minutes =
                                    statistics_daily.voice_minutes
                                    + EXCLUDED.voice_minutes,

                                updated_at = NOW()
                            """,
                            daily_updates,
                        )

                    if state_updates:
                        await connection.executemany(
                            """
                            INSERT INTO statistics_member_state (
                                guild_id,
                                user_id,
                                total_xp,
                                wallet,
                                lifetime_coins,
                                rewarded_messages,
                                rewarded_minutes,
                                updated_at
                            )
                            VALUES (
                                $1,
                                $2,
                                $3,
                                $4,
                                $5,
                                $6,
                                $7,
                                NOW()
                            )
                            ON CONFLICT (
                                guild_id,
                                user_id
                            )
                            DO UPDATE SET
                                total_xp =
                                    EXCLUDED.total_xp,

                                wallet =
                                    EXCLUDED.wallet,

                                lifetime_coins =
                                    EXCLUDED.lifetime_coins,

                                rewarded_messages =
                                    EXCLUDED.rewarded_messages,

                                rewarded_minutes =
                                    EXCLUDED.rewarded_minutes,

                                updated_at = NOW()
                            """,
                            state_updates,
                        )

    async def get_current_member_data(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> dict[str, int]:
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                total_xp,
                wallet,
                lifetime_coins,
                rewarded_messages
            FROM progression_members
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

        if record is None:
            return {
                "total_xp": 0,
                "wallet": 0,
                "lifetime_coins": 0,
                "rewarded_messages": 0,
            }

        return {
            "total_xp": int(
                record["total_xp"]
                or 0
            ),
            "wallet": int(
                record["wallet"]
                or 0
            ),
            "lifetime_coins": int(
                record["lifetime_coins"]
                or 0
            ),
            "rewarded_messages": int(
                record["rewarded_messages"]
                or 0
            ),
        }

    async def get_best_daily_streak(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> int:
        """
        Retourne la meilleure série quotidienne du membre.

        Si le membre n'a jamais utilisé /quotidien,
        la valeur retournée est zéro.
        """
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                best_streak
            FROM daily_members
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

        if record is None:
            return 0

        return max(
            0,
            int(
                record["best_streak"]
                or 0
            ),
        )

    async def get_period_statistics(
        self,
        *,
        guild_id: int,
        user_id: int,
        start_date: date,
    ) -> dict[str, int]:
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                COALESCE(
                    SUM(xp_gained),
                    0
                ) AS xp_gained,

                COALESCE(
                    SUM(coins_gained),
                    0
                ) AS coins_gained,

                COALESCE(
                    SUM(coins_spent),
                    0
                ) AS coins_spent,

                COALESCE(
                    SUM(rewarded_messages),
                    0
                ) AS rewarded_messages,

                COALESCE(
                    SUM(voice_minutes),
                    0
                ) AS voice_minutes

            FROM statistics_daily
            WHERE guild_id = $1
              AND user_id = $2
              AND statistic_date >= $3
            """,
            guild_id,
            user_id,
            start_date,
        )

        if record is None:
            return {
                "xp_gained": 0,
                "coins_gained": 0,
                "coins_spent": 0,
                "rewarded_messages": 0,
                "voice_minutes": 0,
            }

        return {
            "xp_gained": int(
                record["xp_gained"]
                or 0
            ),
            "coins_gained": int(
                record["coins_gained"]
                or 0
            ),
            "coins_spent": int(
                record["coins_spent"]
                or 0
            ),
            "rewarded_messages": int(
                record["rewarded_messages"]
                or 0
            ),
            "voice_minutes": int(
                record["voice_minutes"]
                or 0
            ),
        }

    async def get_current_ranks(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> dict[str, int | None]:
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            WITH ranked_members AS (
                SELECT
                    user_id,

                    ROW_NUMBER() OVER (
                        ORDER BY
                            total_xp DESC,
                            wallet DESC,
                            user_id ASC
                    ) AS xp_rank,

                    ROW_NUMBER() OVER (
                        ORDER BY
                            wallet DESC,
                            total_xp DESC,
                            user_id ASC
                    ) AS money_rank

                FROM progression_members
                WHERE guild_id = $1
            )
            SELECT
                xp_rank,
                money_rank
            FROM ranked_members
            WHERE user_id = $2
            """,
            guild_id,
            user_id,
        )

        if record is None:
            return {
                "xp_rank": None,
                "money_rank": None,
            }

        return {
            "xp_rank": int(
                record["xp_rank"]
            ),
            "money_rank": int(
                record["money_rank"]
            ),
        }

    async def get_historical_ranks(
        self,
        *,
        guild_id: int,
        user_id: int,
        start_date: date,
    ) -> dict[str, int | None]:
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                xp_rank,
                money_rank
            FROM statistics_rank_snapshots
            WHERE guild_id = $1
              AND user_id = $2
              AND snapshot_date >= $3
            ORDER BY
                snapshot_date ASC
            LIMIT 1
            """,
            guild_id,
            user_id,
            start_date,
        )

        if record is None:
            return {
                "xp_rank": None,
                "money_rank": None,
            }

        return {
            "xp_rank": int(
                record["xp_rank"]
            ),
            "money_rank": int(
                record["money_rank"]
            ),
        }

    @tasks.loop(
        seconds=STATISTICS_UPDATE_INTERVAL_SECONDS
    )
    async def statistics_update_loop(
        self,
    ) -> None:
        for guild in self.bot.guilds:
            try:
                await self.synchronize_guild(
                    guild.id
                )
            except Exception:
                LOGGER.exception(
                    (
                        "Impossible d'actualiser les statistiques "
                        "du serveur %s."
                    ),
                    guild.id,
                )

    @statistics_update_loop.before_loop
    async def before_statistics_update_loop(
        self,
    ) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="stats",
        description=(
            "Affiche tes statistiques ou celles d'un membre."
        ),
    )
    @app_commands.rename(
        period="periode",
        member="membre",
    )
    @app_commands.describe(
        period="Période à afficher.",
        member=(
            "Membre dont tu veux consulter les statistiques."
        ),
    )
    @app_commands.choices(
        period=[
            app_commands.Choice(
                name="Aujourd'hui",
                value="today",
            ),
            app_commands.Choice(
                name="7 derniers jours",
                value="7d",
            ),
        ]
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        4.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def stats(
        self,
        interaction: discord.Interaction,
        period: app_commands.Choice[str],
        member: discord.Member | None = None,
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

        selected_member = (
            member
            if member is not None
            else interaction.user
        )

        selected_period = normalize_period(
            period.value
        )

        today = current_paris_date()

        if selected_period == "7d":
            start_date = today - timedelta(
                days=6
            )

            period_label = (
                "7 DERNIERS JOURS"
            )
        else:
            start_date = today
            period_label = "AUJOURD'HUI"

        try:
            await self.synchronize_guild(
                guild.id
            )

            current_data = (
                await self.get_current_member_data(
                    guild_id=guild.id,
                    user_id=selected_member.id,
                )
            )

            period_data = (
                await self.get_period_statistics(
                    guild_id=guild.id,
                    user_id=selected_member.id,
                    start_date=start_date,
                )
            )

            best_streak = (
                await self.get_best_daily_streak(
                    guild_id=guild.id,
                    user_id=selected_member.id,
                )
            )

            current_ranks = (
                await self.get_current_ranks(
                    guild_id=guild.id,
                    user_id=selected_member.id,
                )
            )

            historical_ranks = (
                await self.get_historical_ranks(
                    guild_id=guild.id,
                    user_id=selected_member.id,
                    start_date=start_date,
                )
            )

            current_xp_rank = (
                current_ranks["xp_rank"]
            )

            old_xp_rank = (
                historical_ranks["xp_rank"]
            )

            current_money_rank = (
                current_ranks["money_rank"]
            )

            old_money_rank = (
                historical_ranks["money_rank"]
            )

            xp_rank_change: int | None = None
            money_rank_change: int | None = None

            if (
                current_xp_rank is not None
                and old_xp_rank is not None
            ):
                xp_rank_change = (
                    old_xp_rank
                    - current_xp_rank
                )

            if (
                current_money_rank is not None
                and old_money_rank is not None
            ):
                money_rank_change = (
                    old_money_rank
                    - current_money_rank
                )

            total_xp = int(
                current_data["total_xp"]
            )

            current_level = level_from_xp(
                total_xp
            )

            next_level_total_xp = xp_for_level(
                current_level + 1
            )

            xp_to_next_level = max(
                0,
                next_level_total_xp
                - total_xp,
            )

            avatar_bytes: bytes | None = None

            try:
                avatar_bytes = await (
                    selected_member
                    .display_avatar
                    .read()
                )
            except discord.HTTPException:
                LOGGER.debug(
                    (
                        "Impossible de télécharger "
                        "l'avatar de %s."
                    ),
                    selected_member.id,
                    exc_info=True,
                )

            image = await asyncio.to_thread(
                render_statistics_card,
                display_name=(
                    selected_member.display_name
                ),
                avatar_bytes=avatar_bytes,
                period_label=period_label,
                level=current_level,
                total_xp=total_xp,
                wallet=int(
                    current_data["wallet"]
                ),
                xp_to_next_level=xp_to_next_level,
                xp_gained=int(
                    period_data["xp_gained"]
                ),
                coins_gained=int(
                    period_data["coins_gained"]
                ),

                # Conservé pour la compatibilité avec
                # l'historique des statistiques.
                coins_spent=int(
                    period_data["coins_spent"]
                ),

                # Affiché à la place des pièces dépensées.
                best_streak=best_streak,

                rewarded_messages=int(
                    period_data["rewarded_messages"]
                ),
                voice_minutes=int(
                    period_data["voice_minutes"]
                ),
                xp_rank=current_xp_rank,
                money_rank=current_money_rank,
                xp_rank_change=xp_rank_change,
                money_rank_change=money_rank_change,
                background_path=(
                    self.get_background_path()
                ),
            )

            if isinstance(
                image,
                io.BytesIO,
            ):
                image.seek(0)
                buffer = image

            elif isinstance(
                image,
                bytes,
            ):
                buffer = io.BytesIO(
                    image
                )

            else:
                raise TypeError(
                    (
                        "render_statistics_card doit "
                        "retourner bytes ou BytesIO."
                    )
                )

            statistics_file = discord.File(
                buffer,
                filename=(
                    f"statistiques-"
                    f"{selected_member.id}-"
                    f"{selected_period}.png"
                ),
            )

            await interaction.followup.send(
                file=statistics_file,
                ephemeral=True,
            )

        except Exception:
            LOGGER.exception(
                (
                    "Impossible de générer les statistiques "
                    "de %s sur le serveur %s."
                ),
                selected_member.id,
                guild.id,
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Erreur de génération",
                    (
                        "Les statistiques n'ont pas pu "
                        "être générées.\n"
                        "Consulte les logs du bot."
                    ),
                ),
                ephemeral=True,
            )


async def setup(
    bot: commands.Bot,
) -> None:
    cog = StatisticsCog(
        bot
    )

    await cog.initialize_database()
    await bot.add_cog(
        cog
    )

    LOGGER.info(
        "Système permanent de statistiques initialisé"
    )
