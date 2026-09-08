from __future__ import annotations

from bot.features.advent.full_repository import (
    FullAdventRepository,
)


class AdminAdventRepository(FullAdventRepository):
    """
    Dépôt complet utilisé par les commandes administratives.

    Il ajoute les champs modifiables qui ne nécessitaient pas
    d'apparaître dans le dépôt de base.
    """

    async def update_campaign_timezone(
        self,
        campaign_id: int,
        timezone: str,
    ) -> None:
        await self.database.execute(
            """
            UPDATE advent_campaigns
            SET timezone = $2,
                updated_at = NOW()
            WHERE id = $1
            """,
            campaign_id,
            timezone,
        )

    async def update_opening_hour(
        self,
        campaign_id: int,
        opening_hour: int,
    ) -> None:
        await self.database.execute(
            """
            UPDATE advent_campaigns
            SET opening_hour = $2,
                updated_at = NOW()
            WHERE id = $1
            """,
            campaign_id,
            opening_hour,
        )
