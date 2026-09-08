from __future__ import annotations

import json
from typing import Any

from bot.core.database import Database
from bot.features.advent.models import AdventOpening
from bot.features.advent.repository import _opening_from_record


class AdventTransactionRepository:
    """
    Requêtes nécessitant une transaction ou concernant les fonctions
    annexes du calendrier.

    La contrainte UNIQUE de PostgreSQL reste la protection définitive
    contre deux ouvertures simultanées.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_opening_atomically(
        self,
        *,
        campaign_id: int,
        guild_id: int,
        user_id: int,
        day: int,
        reward_id: int | None,
        reward_type: str,
        reward_snapshot: dict[str, Any],
        points_awarded: int,
        external_status: str,
    ) -> tuple[AdventOpening, bool]:
        """
        Crée une ouverture une seule fois.

        Retour :
            (ouverture, True)  → l'ouverture vient d'être créée ;
            (ouverture, False) → elle existait déjà.
        """
        pool = self.database.require_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                record = await connection.fetchrow(
                    """
                    INSERT INTO advent_openings (
                        campaign_id,
                        guild_id,
                        user_id,
                        day,
                        reward_id,
                        reward_type,
                        reward_snapshot,
                        points_awarded,
                        external_status
                    )
                    VALUES (
                        $1,
                        $2,
                        $3,
                        $4,
                        $5,
                        $6,
                        $7::JSONB,
                        $8,
                        $9
                    )
                    ON CONFLICT (
                        campaign_id,
                        user_id,
                        day
                    )
                    DO NOTHING
                    RETURNING
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
                    """,
                    campaign_id,
                    guild_id,
                    user_id,
                    day,
                    reward_id,
                    reward_type,
                    json.dumps(
                        reward_snapshot,
                        ensure_ascii=False,
                    ),
                    points_awarded,
                    external_status,
                )

                if record is not None:
                    return _opening_from_record(record), True

                existing = await connection.fetchrow(
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

                if existing is None:
                    raise RuntimeError(
                        "L'ouverture n'a été ni créée ni retrouvée."
                    )

                return _opening_from_record(existing), False

    async def update_external_status(
        self,
        opening_id: int,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        await self.database.execute(
            """
            UPDATE advent_openings
            SET external_status = $2,
                external_error = $3
            WHERE id = $1
            """,
            opening_id,
            status,
            error,
        )

    async def leaderboard(
        self,
        campaign_id: int,
        limit: int = 10,
    ) -> list[dict[str, int]]:
        records = await self.database.fetch(
            """
            SELECT
                user_id,
                COUNT(*)::INTEGER AS opened_count,
                COALESCE(SUM(points_awarded), 0)::INTEGER
                    AS total_points
            FROM advent_openings
            WHERE campaign_id = $1
            GROUP BY user_id
            ORDER BY
                opened_count DESC,
                total_points DESC,
                user_id ASC
            LIMIT $2
            """,
            campaign_id,
            limit,
        )

        return [
            {
                "user_id": int(record["user_id"]),
                "opened_count": int(record["opened_count"]),
                "total_points": int(record["total_points"]),
            }
            for record in records
        ]

    async def save_panel(
        self,
        *,
        campaign_id: int,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        await self.database.execute(
            """
            INSERT INTO advent_panels (
                campaign_id,
                guild_id,
                channel_id,
                message_id,
                updated_at
            )
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (campaign_id)
            DO UPDATE SET
                guild_id = EXCLUDED.guild_id,
                channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id,
                updated_at = NOW()
            """,
            campaign_id,
            guild_id,
            channel_id,
            message_id,
        )

    async def get_panel(
        self,
        campaign_id: int,
    ) -> dict[str, int] | None:
        record = await self.database.fetchrow(
            """
            SELECT
                guild_id,
                channel_id,
                message_id
            FROM advent_panels
            WHERE campaign_id = $1
            """,
            campaign_id,
        )

        if record is None:
            return None

        return {
            "guild_id": int(record["guild_id"]),
            "channel_id": int(record["channel_id"]),
            "message_id": int(record["message_id"]),
        }

    async def announcement_exists(
        self,
        campaign_id: int,
        day: int,
    ) -> bool:
        value = await self.database.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM advent_announcements
                WHERE campaign_id = $1
                  AND day = $2
            )
            """,
            campaign_id,
            day,
        )

        return bool(value)

    async def reserve_announcement(
        self,
        *,
        campaign_id: int,
        day: int,
        channel_id: int,
    ) -> bool:
        result = await self.database.execute(
            """
            INSERT INTO advent_announcements (
                campaign_id,
                day,
                channel_id
            )
            VALUES ($1, $2, $3)
            ON CONFLICT (campaign_id, day)
            DO NOTHING
            """,
            campaign_id,
            day,
            channel_id,
        )

        return result != "INSERT 0 0"

    async def complete_announcement(
        self,
        *,
        campaign_id: int,
        day: int,
        message_id: int,
    ) -> None:
        await self.database.execute(
            """
            UPDATE advent_announcements
            SET message_id = $3,
                announced_at = NOW()
            WHERE campaign_id = $1
              AND day = $2
            """,
            campaign_id,
            day,
            message_id,
        )

    async def cancel_announcement_reservation(
        self,
        *,
        campaign_id: int,
        day: int,
    ) -> None:
        await self.database.execute(
            """
            DELETE FROM advent_announcements
            WHERE campaign_id = $1
              AND day = $2
              AND message_id IS NULL
            """,
            campaign_id,
            day,
        )

    async def audit(
        self,
        *,
        guild_id: int,
        campaign_id: int | None,
        actor_id: int | None,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        await self.database.execute(
            """
            INSERT INTO advent_audit_logs (
                guild_id,
                campaign_id,
                actor_id,
                action,
                details
            )
            VALUES ($1, $2, $3, $4, $5::JSONB)
            """,
            guild_id,
            campaign_id,
            actor_id,
            action,
            json.dumps(
                details or {},
                ensure_ascii=False,
            ),
        )

    async def reset_user(
        self,
        *,
        campaign_id: int,
        user_id: int,
    ) -> int:
        result = await self.database.execute(
            """
            DELETE FROM advent_openings
            WHERE campaign_id = $1
              AND user_id = $2
            """,
            campaign_id,
            user_id,
        )

        return self._affected_rows(result)

    @staticmethod
    def _affected_rows(result: str) -> int:
        try:
            return int(result.rsplit(" ", maxsplit=1)[-1])
        except (ValueError, IndexError):
            return 0
