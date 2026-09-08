from __future__ import annotations

import json
from datetime import date
from typing import Any, Iterable

import asyncpg

from bot.core.database import Database
from bot.features.advent.models import (
    AdventCampaign,
    AdventOpening,
    AdventReward,
)


def _json_object(value: Any) -> dict[str, Any]:
    """
    asyncpg peut retourner JSONB sous forme de chaîne ou d'objet,
    selon la configuration. Cette fonction accepte les deux.
    """
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        decoded = json.loads(value)

        if isinstance(decoded, dict):
            return decoded

    raise TypeError("La valeur JSON attendue n'est pas un objet.")


def _campaign_from_record(
    record: asyncpg.Record,
) -> AdventCampaign:
    return AdventCampaign(
        id=record["id"],
        guild_id=record["guild_id"],
        year=record["year"],
        title=record["title"],
        start_date=record["start_date"],
        end_date=record["end_date"],
        timezone=record["timezone"],
        opening_hour=record["opening_hour"],
        catchup_mode=record["catchup_mode"],
        channel_id=record["channel_id"],
        announcement_role_id=record["announcement_role_id"],
        announcements_enabled=record["announcements_enabled"],
        enabled=record["enabled"],
        day_order=tuple(record["day_order"]),
    )


def _reward_from_record(
    record: asyncpg.Record,
) -> AdventReward:
    return AdventReward(
        id=record["id"],
        campaign_id=record["campaign_id"],
        day=record["day"],
        reward_type=record["reward_type"],
        reward_data=_json_object(record["reward_data"]),
    )


def _opening_from_record(
    record: asyncpg.Record,
) -> AdventOpening:
    return AdventOpening(
        id=record["id"],
        campaign_id=record["campaign_id"],
        guild_id=record["guild_id"],
        user_id=record["user_id"],
        day=record["day"],
        opened_at=record["opened_at"],
        reward_type=record["reward_type"],
        reward_snapshot=_json_object(record["reward_snapshot"]),
        points_awarded=record["points_awarded"],
        external_status=record["external_status"],
    )


class AdventRepository:
    """
    Toutes les requêtes PostgreSQL propres au calendrier de l'Avent.

    Les commandes Discord n'effectuent jamais directement de SQL :
    elles passent par le service, qui utilise ensuite ce dépôt.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    async def ensure_guild_settings(
        self,
        guild_id: int,
        default_timezone: str,
    ) -> None:
        await self.database.execute(
            """
            INSERT INTO guild_settings (
                guild_id,
                timezone
            )
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO NOTHING
            """,
            guild_id,
            default_timezone,
        )

    async def get_guild_timezone(
        self,
        guild_id: int,
        default_timezone: str,
    ) -> str:
        await self.ensure_guild_settings(
            guild_id,
            default_timezone,
        )

        value = await self.database.fetchval(
            """
            SELECT timezone
            FROM guild_settings
            WHERE guild_id = $1
            """,
            guild_id,
        )

        return str(value or default_timezone)

    async def set_guild_timezone(
        self,
        guild_id: int,
        timezone: str,
    ) -> None:
        await self.database.execute(
            """
            INSERT INTO guild_settings (
                guild_id,
                timezone,
                updated_at
            )
            VALUES ($1, $2, NOW())
            ON CONFLICT (guild_id)
            DO UPDATE SET
                timezone = EXCLUDED.timezone,
                updated_at = NOW()
            """,
            guild_id,
            timezone,
        )

    async def get_campaign(
        self,
        guild_id: int,
        year: int,
    ) -> AdventCampaign | None:
        record = await self.database.fetchrow(
            """
            SELECT
                id,
                guild_id,
                year,
                title,
                start_date,
                end_date,
                timezone,
                opening_hour,
                catchup_mode,
                channel_id,
                announcement_role_id,
                announcements_enabled,
                enabled,
                day_order
            FROM advent_campaigns
            WHERE guild_id = $1
              AND year = $2
            """,
            guild_id,
            year,
        )

        if record is None:
            return None

        return _campaign_from_record(record)

    async def get_campaign_by_id(
        self,
        campaign_id: int,
    ) -> AdventCampaign | None:
        record = await self.database.fetchrow(
            """
            SELECT
                id,
                guild_id,
                year,
                title,
                start_date,
                end_date,
                timezone,
                opening_hour,
                catchup_mode,
                channel_id,
                announcement_role_id,
                announcements_enabled,
                enabled,
                day_order
            FROM advent_campaigns
            WHERE id = $1
            """,
            campaign_id,
        )

        if record is None:
            return None

        return _campaign_from_record(record)

    async def get_latest_campaign(
        self,
        guild_id: int,
    ) -> AdventCampaign | None:
        record = await self.database.fetchrow(
            """
            SELECT
                id,
                guild_id,
                year,
                title,
                start_date,
                end_date,
                timezone,
                opening_hour,
                catchup_mode,
                channel_id,
                announcement_role_id,
                announcements_enabled,
                enabled,
                day_order
            FROM advent_campaigns
            WHERE guild_id = $1
            ORDER BY year DESC
            LIMIT 1
            """,
            guild_id,
        )

        if record is None:
            return None

        return _campaign_from_record(record)

    async def get_enabled_campaigns(
        self,
    ) -> list[AdventCampaign]:
        records = await self.database.fetch(
            """
            SELECT
                id,
                guild_id,
                year,
                title,
                start_date,
                end_date,
                timezone,
                opening_hour,
                catchup_mode,
                channel_id,
                announcement_role_id,
                announcements_enabled,
                enabled,
                day_order
            FROM advent_campaigns
            WHERE enabled = TRUE
            ORDER BY guild_id, year
            """
        )

        return [
            _campaign_from_record(record)
            for record in records
        ]

    async def create_or_update_campaign(
        self,
        *,
        guild_id: int,
        year: int,
        title: str,
        start_date: date,
        end_date: date,
        timezone: str,
        opening_hour: int,
        catchup_mode: str,
        day_order: Iterable[int],
    ) -> AdventCampaign:
        order = list(day_order)

        record = await self.database.fetchrow(
            """
            INSERT INTO advent_campaigns (
                guild_id,
                year,
                title,
                start_date,
                end_date,
                timezone,
                opening_hour,
                catchup_mode,
                day_order,
                enabled,
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
                $9::SMALLINT[],
                TRUE,
                NOW()
            )
            ON CONFLICT (guild_id, year)
            DO UPDATE SET
                title = EXCLUDED.title,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                timezone = EXCLUDED.timezone,
                opening_hour = EXCLUDED.opening_hour,
                catchup_mode = EXCLUDED.catchup_mode,
                day_order = EXCLUDED.day_order,
                enabled = TRUE,
                updated_at = NOW()
            RETURNING
                id,
                guild_id,
                year,
                title,
                start_date,
                end_date,
                timezone,
                opening_hour,
                catchup_mode,
                channel_id,
                announcement_role_id,
                announcements_enabled,
                enabled,
                day_order
            """,
            guild_id,
            year,
            title,
            start_date,
            end_date,
            timezone,
            opening_hour,
            catchup_mode,
            order,
        )

        if record is None:
            raise RuntimeError(
                "PostgreSQL n'a pas retourné la campagne créée."
            )

        return _campaign_from_record(record)

    async def update_campaign_channel(
        self,
        campaign_id: int,
        channel_id: int | None,
    ) -> None:
        await self.database.execute(
            """
            UPDATE advent_campaigns
            SET channel_id = $2,
                updated_at = NOW()
            WHERE id = $1
            """,
            campaign_id,
            channel_id,
        )

    async def update_campaign_catchup(
        self,
        campaign_id: int,
        catchup_mode: str,
    ) -> None:
        await self.database.execute(
            """
            UPDATE advent_campaigns
            SET catchup_mode = $2,
                updated_at = NOW()
            WHERE id = $1
            """,
            campaign_id,
            catchup_mode,
        )

    async def update_announcements(
        self,
        campaign_id: int,
        *,
        enabled: bool,
        role_id: int | None,
    ) -> None:
        await self.database.execute(
            """
            UPDATE advent_campaigns
            SET announcements_enabled = $2,
                announcement_role_id = $3,
                updated_at = NOW()
            WHERE id = $1
            """,
            campaign_id,
            enabled,
            role_id,
        )

    async def set_campaign_enabled(
        self,
        campaign_id: int,
        enabled: bool,
    ) -> None:
        await self.database.execute(
            """
            UPDATE advent_campaigns
            SET enabled = $2,
                updated_at = NOW()
            WHERE id = $1
            """,
            campaign_id,
            enabled,
        )

    async def delete_campaign(
        self,
        campaign_id: int,
    ) -> None:
        await self.database.execute(
            """
            DELETE FROM advent_campaigns
            WHERE id = $1
            """,
            campaign_id,
        )

    async def get_reward(
        self,
        campaign_id: int,
        day: int,
    ) -> AdventReward | None:
        record = await self.database.fetchrow(
            """
            SELECT
                id,
                campaign_id,
                day,
                reward_type,
                reward_data
            FROM advent_rewards
            WHERE campaign_id = $1
              AND day = $2
            """,
            campaign_id,
            day,
        )

        if record is None:
            return None

        return _reward_from_record(record)

    async def list_rewards(
        self,
        campaign_id: int,
    ) -> list[AdventReward]:
        records = await self.database.fetch(
            """
            SELECT
                id,
                campaign_id,
                day,
                reward_type,
                reward_data
            FROM advent_rewards
            WHERE campaign_id = $1
            ORDER BY day
            """,
            campaign_id,
        )

        return [
            _reward_from_record(record)
            for record in records
        ]

    async def upsert_reward(
        self,
        *,
        campaign_id: int,
        day: int,
        reward_type: str,
        reward_data: dict[str, Any],
    ) -> AdventReward:
        record = await self.database.fetchrow(
            """
            INSERT INTO advent_rewards (
                campaign_id,
                day,
                reward_type,
                reward_data,
                updated_at
            )
            VALUES ($1, $2, $3, $4::JSONB, NOW())
            ON CONFLICT (campaign_id, day)
            DO UPDATE SET
                reward_type = EXCLUDED.reward_type,
                reward_data = EXCLUDED.reward_data,
                updated_at = NOW()
            RETURNING
                id,
                campaign_id,
                day,
                reward_type,
                reward_data
            """,
            campaign_id,
            day,
            reward_type,
            json.dumps(
                reward_data,
                ensure_ascii=False,
            ),
        )

        if record is None:
            raise RuntimeError(
                "PostgreSQL n'a pas retourné la récompense créée."
            )

        return _reward_from_record(record)

    async def delete_reward(
        self,
        campaign_id: int,
        day: int,
    ) -> bool:
        result = await self.database.execute(
            """
            DELETE FROM advent_rewards
            WHERE campaign_id = $1
              AND day = $2
            """,
            campaign_id,
            day,
        )

        return result != "DELETE 0"

    async def get_opening(
        self,
        campaign_id: int,
        user_id: int,
        day: int,
    ) -> AdventOpening | None:
        record = await self.database.fetchrow(
            """
            SELECT
                id,
                campaign_id,
                guild_id,
                user_id,
                day,
                opened_at,
                reward_type,
                reward_snapshot,
                points_awarded,
                external_status
            FROM advent_openings
            WHERE campaign_id = $1
              AND user_id = $2
              AND day = $3
            """,
            campaign_id,
            user_id,
            day,
        )

        if record is None:
            return None

        return _opening_from_record(record)

    async def get_user_openings(
        self,
        campaign_id: int,
        user_id: int,
    ) -> list[AdventOpening]:
        records = await self.database.fetch(
            """
            SELECT
                id,
                campaign_id,
                guild_id,
                user_id,
                day,
                opened_at,
                reward_type,
                reward_snapshot,
                points_awarded,
                external_status
            FROM advent_openings
            WHERE campaign_id = $1
              AND user_id = $2
            ORDER BY day
            """,
            campaign_id,
            user_id,
        )

        return [
            _opening_from_record(record)
            for record in records
        ]

    async def get_user_total_points(
        self,
        campaign_id: int,
        user_id: int,
    ) -> int:
        value = await self.database.fetchval(
            """
            SELECT COALESCE(SUM(points_awarded), 0)
            FROM advent_openings
            WHERE campaign_id = $1
              AND user_id = $2
            """,
            campaign_id,
            user_id,
        )

        return int(value or 0)
