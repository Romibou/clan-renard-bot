"""
/bilan : carte récapitulative de l'année d'un membre (« Clan Renard 2026 »).

Ouvert aux membres du 31 décembre au 31 janvier (heure de Paris), pour
garder l'effet de surprise. Les administrateurs peuvent le consulter à
tout moment pour le préparer.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from bot.shared.members import present_member_ids
from bot.shared.recap_card import RecapStats, render_recap_card

LOGGER = logging.getLogger(__name__)

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
RECAP_COLOR = discord.Color.from_rgb(255, 195, 87)


def recap_year(today: date) -> int:
    """En janvier, on regarde l'année qui vient de se terminer."""
    return today.year - 1 if today.month == 1 else today.year


def is_recap_open(today: date) -> bool:
    """Du 31 décembre au 31 janvier inclus."""
    return (today.month == 12 and today.day == 31) or today.month == 1


class RecapCog(commands.Cog):
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

    async def _fetchval(self, query: str, *args) -> object:
        """Une table absente (module désactivé) compte comme 0."""
        try:
            return await self.get_pool().fetchval(query, *args)
        except asyncpg.UndefinedTableError:
            return None

    async def collect_stats(
        self,
        *,
        guild_id: int,
        user_id: int,
        year: int,
    ) -> RecapStats:
        pool = self.get_pool()
        first_day = date(year, 1, 1)
        last_day = date(year, 12, 31)

        try:
            totals = await pool.fetchrow(
                """
                SELECT
                    COALESCE(SUM(xp_gained), 0)::BIGINT AS xp,
                    COALESCE(SUM(rewarded_messages), 0)::BIGINT AS messages,
                    COALESCE(SUM(voice_minutes), 0)::BIGINT AS voice,
                    COALESCE(SUM(coins_gained), 0)::BIGINT AS coins
                FROM statistics_daily
                WHERE guild_id = $1
                  AND user_id = $2
                  AND statistic_date BETWEEN $3 AND $4
                """,
                guild_id,
                user_id,
                first_day,
                last_day,
            )
            best_day = await pool.fetchrow(
                """
                SELECT statistic_date, xp_gained
                FROM statistics_daily
                WHERE guild_id = $1
                  AND user_id = $2
                  AND statistic_date BETWEEN $3 AND $4
                ORDER BY xp_gained DESC, statistic_date ASC
                LIMIT 1
                """,
                guild_id,
                user_id,
                first_day,
                last_day,
            )
            ranking = await pool.fetchrow(
                """
                WITH totals AS (
                    SELECT user_id, SUM(xp_gained) AS xp
                    FROM statistics_daily
                    WHERE guild_id = $1
                      AND statistic_date BETWEEN $2 AND $3
                      AND (
                            $5::BIGINT[] IS NULL
                            OR user_id = ANY($5::BIGINT[])
                      )
                    GROUP BY user_id
                    HAVING SUM(xp_gained) > 0
                )
                SELECT
                    (SELECT COUNT(*) FROM totals) AS ranked,
                    (
                        SELECT COUNT(*) + 1
                        FROM totals AS other
                        WHERE other.xp > mine.xp
                           OR (other.xp = mine.xp AND other.user_id < mine.user_id)
                    ) AS rank
                FROM totals AS mine
                WHERE mine.user_id = $4
                """,
                guild_id,
                first_day,
                last_day,
                user_id,
                present_member_ids(self.bot, guild_id),
            )
            since = await pool.fetchval(
                """
                SELECT MIN(statistic_date)
                FROM statistics_daily
                WHERE guild_id = $1
                """,
                guild_id,
            )
        except asyncpg.UndefinedTableError:
            totals = best_day = ranking = since = None

        year_start = datetime(year, 1, 1, tzinfo=PARIS_TIMEZONE)
        year_end = datetime(year + 1, 1, 1, tzinfo=PARIS_TIMEZONE)

        daily_claims = await self._fetchval(
            """
            SELECT COUNT(*)
            FROM daily_claims
            WHERE guild_id = $1
              AND user_id = $2
              AND claimed_at >= $3
              AND claimed_at < $4
            """,
            guild_id,
            user_id,
            year_start,
            year_end,
        )
        best_streak = await self._fetchval(
            """
            SELECT best_streak
            FROM daily_members
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )
        campaign_exists = await self._fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM advent_campaigns
                WHERE guild_id = $1
                  AND year = $2
            )
            """,
            guild_id,
            year,
        )
        advent_openings = None

        if campaign_exists:
            advent_openings = int(
                await self._fetchval(
                    """
                    SELECT COUNT(*)
                    FROM advent_openings AS opening
                    JOIN advent_campaigns AS campaign
                        ON campaign.id = opening.campaign_id
                    WHERE campaign.guild_id = $1
                      AND campaign.year = $2
                      AND opening.user_id = $3
                    """,
                    guild_id,
                    year,
                    user_id,
                )
                or 0
            )

        return RecapStats(
            year=year,
            xp_gained=int(totals["xp"]) if totals else 0,
            year_rank=int(ranking["rank"]) if ranking else None,
            ranked_members=int(ranking["ranked"]) if ranking else 0,
            rewarded_messages=int(totals["messages"]) if totals else 0,
            voice_minutes=int(totals["voice"]) if totals else 0,
            coins_gained=int(totals["coins"]) if totals else 0,
            best_day=(
                best_day["statistic_date"].strftime("%d/%m")
                if best_day is not None
                else None
            ),
            best_day_xp=int(best_day["xp_gained"]) if best_day else 0,
            daily_claims=int(daily_claims or 0),
            best_streak=int(best_streak or 0),
            advent_openings=advent_openings,
            stats_since=(
                since.strftime("%d/%m/%Y")
                if since is not None and since > date(year, 1, 1)
                else None
            ),
        )

    @app_commands.command(
        name="bilan",
        description="Affiche le bilan de ton année sur le serveur.",
    )
    @app_commands.rename(member="membre")
    @app_commands.describe(member="Membre dont tu veux voir le bilan.")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        10.0,
        key=lambda interaction: (interaction.guild_id, interaction.user.id),
    )
    async def bilan(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            return

        today = datetime.now(PARIS_TIMEZONE).date()
        year = recap_year(today)
        permissions = getattr(interaction.user, "guild_permissions", None)
        is_admin = permissions is not None and permissions.manage_guild

        if not is_recap_open(today) and not is_admin:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=f"🎁 Le bilan {year} arrive bientôt !",
                    description=(
                        f"Ton bilan de l'année {year} sera disponible le "
                        f"**31 décembre**. Patience, il se prépare… 🦊"
                    ),
                    color=RECAP_COLOR,
                ),
                ephemeral=True,
            )
            return

        target = member or interaction.user

        await interaction.response.defer(
            thinking=True,
            ephemeral=not is_recap_open(today),
        )

        try:
            stats = await self.collect_stats(
                guild_id=guild.id,
                user_id=target.id,
                year=year,
            )

            try:
                avatar_bytes = await target.display_avatar.replace(
                    size=256,
                    static_format="png",
                ).read()
            except (discord.DiscordException, ValueError, OSError):
                avatar_bytes = None

            image = await asyncio.to_thread(
                render_recap_card,
                display_name=target.display_name,
                avatar_bytes=avatar_bytes,
                stats=stats,
                background_path=(
                    Path(__file__).resolve().parents[2]
                    / "assets"
                    / "statistics"
                    / "statistics_background.png"
                ),
            )
        except Exception:
            LOGGER.exception("Impossible de générer le bilan de %s", target.id)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Bilan indisponible",
                    description="Le bilan n'a pas pu être généré. Réessaie plus tard.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        content = None

        if not is_recap_open(today):
            content = (
                "👀 Aperçu administrateur : les membres pourront utiliser "
                "`/bilan` du 31 décembre au 31 janvier."
            )

        await interaction.followup.send(
            content=content,
            file=discord.File(image, filename=f"bilan-{year}.png"),
            ephemeral=not is_recap_open(today),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RecapCog(bot))
    LOGGER.info("Commande /bilan chargée")
