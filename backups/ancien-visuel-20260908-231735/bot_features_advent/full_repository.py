from __future__ import annotations

from bot.features.advent.models import AdventOpening
from bot.features.advent.repository import (
    AdventRepository,
    _opening_from_record,
)


class FullAdventRepository(AdventRepository):
    """
    Complète AdventRepository avec les opérations liées aux membres.

    Cette classe est utilisée par l'extension principale. Elle permet
    de garder le premier dépôt lisible tout en séparant les requêtes
    de consultation et de réinitialisation.
    """

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

    async def get_opening(
        self,
        *,
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

    async def count_campaign_openings(
        self,
        campaign_id: int,
    ) -> int:
        value = await self.database.fetchval(
            """
            SELECT COUNT(*)
            FROM advent_openings
            WHERE campaign_id = $1
            """,
            campaign_id,
        )

        return int(value or 0)

    async def count_campaign_members(
        self,
        campaign_id: int,
    ) -> int:
        value = await self.database.fetchval(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM advent_openings
            WHERE campaign_id = $1
            """,
            campaign_id,
        )

        return int(value or 0)

    async def get_pending_role_openings(
        self,
        *,
        guild_id: int,
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
            WHERE guild_id = $1
              AND user_id = $2
              AND reward_type = 'role'
              AND external_status IN ('pending', 'failed')
            ORDER BY opened_at
            """,
            guild_id,
            user_id,
        )

        return [
            _opening_from_record(record)
            for record in records
        ]
