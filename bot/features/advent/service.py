from __future__ import annotations

import os


from datetime import date, datetime, timedelta
from typing import Any

from bot.features.advent.constants import (
    CATCHUP_ENABLED,
    DEFAULT_DAY_ORDER,
    DEFAULT_END_DAY,
    DEFAULT_OPENING_HOUR,
    DEFAULT_START_DAY,
    DEFAULT_TITLE,
)
from bot.features.advent.exceptions import (
    CampaignDisabled,
    CampaignFinished,
    CampaignNotConfigured,
    CampaignNotStarted,
    DayAlreadyOpened,
    DayNotAvailable,
)
from bot.features.advent.models import (
    AdventCampaign,
    CalendarState,
    OpenResult,
)
from bot.features.advent.repository import AdventRepository
from bot.features.advent.reward_service import RewardService
from bot.features.advent.transaction_repository import (
    AdventTransactionRepository,
)
from bot.shared.dates import now_in_timezone


class AdventService:
    def __init__(
        self,
        repository: AdventRepository,
        transactions: AdventTransactionRepository,
        reward_service: RewardService,
        default_timezone: str,
    ) -> None:
        self.repository = repository
        self.transactions = transactions
        self.reward_service = reward_service
        self.default_timezone = default_timezone

    async def create_default_campaign(
        self,
        *,
        guild_id: int,
        year: int,
        timezone: str | None = None,
        title: str = DEFAULT_TITLE,
    ) -> AdventCampaign:
        selected_timezone = timezone or self.default_timezone

        await self.repository.set_guild_timezone(
            guild_id,
            selected_timezone,
        )

        campaign = await self.repository.create_or_update_campaign(
            guild_id=guild_id,
            year=year,
            title=title.strip() or DEFAULT_TITLE,
            start_date=date(year, 12, DEFAULT_START_DAY),
            end_date=date(year, 12, DEFAULT_END_DAY),
            timezone=selected_timezone,
            opening_hour=DEFAULT_OPENING_HOUR,
            catchup_mode="disabled",
            day_order=DEFAULT_DAY_ORDER,
        )

        return campaign

    async def get_campaign_for_display(
        self,
        guild_id: int,
    ) -> AdventCampaign:
        timezone = await self.repository.get_guild_timezone(
            guild_id,
            self.default_timezone,
        )
        local_now = now_in_timezone(timezone)

        campaign = await self.repository.get_campaign(
            guild_id,
            local_now.year,
        )

        if campaign is None:
            campaign = await self.repository.get_latest_campaign(
                guild_id,
            )

        if campaign is None:
            raise CampaignNotConfigured(
                "Le calendrier de l'Avent n'a pas encore été "
                "configuré sur ce serveur."
            )

        return campaign

    async def get_campaign_for_year(
        self,
        guild_id: int,
        year: int,
    ) -> AdventCampaign:
        campaign = await self.repository.get_campaign(
            guild_id,
            year,
        )

        if campaign is None:
            raise CampaignNotConfigured(
                f"Aucune campagne n'est configurée pour {year}."
            )

        return campaign

    @staticmethod
    def effective_date(
        campaign: AdventCampaign,
        moment: datetime | None = None,
    ) -> date:
        test_date = os.getenv("ADVENT_TEST_DATE", "").strip()

        if test_date:
            return date.fromisoformat(test_date)

        local_now = moment or now_in_timezone(campaign.timezone)

        # Si l'ouverture est configurée à 06:00, la période comprise
        # entre minuit et 05:59 appartient encore à la veille.
        shifted = local_now - timedelta(
            hours=campaign.opening_hour,
        )

        return shifted.date()

    @classmethod
    def current_day(
        cls,
        campaign: AdventCampaign,
        moment: datetime | None = None,
    ) -> int | None:
        current_date = cls.effective_date(campaign, moment)

        if current_date < campaign.start_date:
            return None

        if current_date > campaign.end_date:
            return None

        day = (
            current_date - campaign.start_date
        ).days + 1

        if not 1 <= day <= 24:
            return None

        return day

    async def get_calendar_state(
        self,
        *,
        guild_id: int,
        user_id: int,
        campaign: AdventCampaign | None = None,
        moment: datetime | None = None,
    ) -> CalendarState:
        selected = campaign or await self.get_campaign_for_display(
            guild_id
        )

        openings = await self.repository.get_user_openings(
            selected.id,
            user_id,
        )
        opened_days = frozenset(
            opening.day for opening in openings
        )

        effective_today = self.effective_date(
            selected,
            moment,
        )
        active_day = self.current_day(
            selected,
            moment,
        )

        all_days = set(range(1, 25))
        missed_days: set[int] = set()
        available_days: set[int] = set()
        future_days: set[int] = set()

        if effective_today < selected.start_date:
            future_days = all_days.copy()

        elif effective_today > selected.end_date:
            missed_days = all_days - set(opened_days)

        else:
            if active_day is None:
                future_days = all_days - set(opened_days)
            else:
                previous_days = set(range(1, active_day))

                if selected.catchup_mode == CATCHUP_ENABLED:
                    available_days.update(
                        previous_days - set(opened_days)
                    )
                else:
                    missed_days.update(
                        previous_days - set(opened_days)
                    )

                if active_day not in opened_days:
                    available_days.add(active_day)

                future_days.update(
                    set(range(active_day + 1, 25))
                )

        total_points = sum(
            opening.points_awarded
            for opening in openings
        )

        return CalendarState(
            campaign=selected,
            today=effective_today,
            current_day=active_day,
            opened_days=opened_days,
            missed_days=frozenset(missed_days),
            available_days=frozenset(available_days),
            future_days=frozenset(future_days),
            total_points=total_points,
        )

    async def open_day(
        self,
        *,
        guild_id: int,
        user_id: int,
        requested_day: int | None = None,
        campaign: AdventCampaign | None = None,
        moment: datetime | None = None,
    ) -> OpenResult:
        selected = campaign or await self.get_campaign_for_display(
            guild_id
        )

        if not selected.enabled:
            raise CampaignDisabled(
                "Le calendrier est actuellement désactivé."
            )

        effective_today = self.effective_date(
            selected,
            moment,
        )

        if effective_today < selected.start_date:
            raise CampaignNotStarted(
                f"Le calendrier ouvrira le "
                f"{selected.start_date.strftime('%d/%m/%Y')}."
            )

        if effective_today > selected.end_date:
            raise CampaignFinished(
                "Le calendrier de cette année est terminé."
            )

        state = await self.get_calendar_state(
            guild_id=guild_id,
            user_id=user_id,
            campaign=selected,
            moment=moment,
        )

        if requested_day is None:
            target_day = state.current_day
        else:
            target_day = requested_day

        if target_day is None:
            raise DayNotAvailable(
                "Aucune case n'est disponible actuellement."
            )

        if not 1 <= target_day <= 24:
            raise DayNotAvailable(
                "Le numéro de case doit être compris entre 1 et 24."
            )

        if target_day in state.opened_days:
            raise DayAlreadyOpened(
                f"La case {target_day} a déjà été ouverte."
            )

        if target_day not in state.available_days:
            if (
                state.current_day is not None
                and target_day > state.current_day
            ):
                raise DayNotAvailable(
                    "Cette case appartient au futur."
                )

            raise DayNotAvailable(
                "Cette case n'est pas disponible. "
                "Le rattrapage est peut-être désactivé."
            )

        configured_reward = await self.repository.get_reward(
            selected.id,
            target_day,
        )
        resolved = self.reward_service.resolve(
            configured_reward
        )

        opening, created = (
            await self.transactions.create_opening_atomically(
                campaign_id=selected.id,
                guild_id=guild_id,
                user_id=user_id,
                day=target_day,
                reward_id=(
                    configured_reward.id
                    if configured_reward is not None
                    else None
                ),
                reward_type=resolved.reward_type,
                reward_snapshot=resolved.snapshot,
                points_awarded=resolved.points,
                external_status=resolved.external_status,
            )
        )

        if not created:
            raise DayAlreadyOpened(
                f"La case {target_day} vient déjà d'être ouverte."
            )

        return OpenResult(
            opening=opening,
            reward_message=resolved.message,
            role_id=resolved.role_id,
        )

    async def mark_role_result(
        self,
        *,
        opening_id: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        await self.transactions.update_external_status(
            opening_id,
            status="completed" if success else "failed",
            error=error,
        )

    async def get_reward_history(
        self,
        *,
        campaign_id: int,
        user_id: int,
    ) -> list[dict[str, Any]]:
        openings = await self.repository.get_user_openings(
            campaign_id,
            user_id,
        )

        return [
            {
                "day": opening.day,
                "reward_type": opening.reward_type,
                "snapshot": opening.reward_snapshot,
                "points": opening.points_awarded,
                "opened_at": opening.opened_at,
                "external_status": opening.external_status,
            }
            for opening in openings
        ]

    async def get_leaderboard(
        self,
        campaign_id: int,
        limit: int = 10,
    ) -> list[dict[str, int]]:
        return await self.transactions.leaderboard(
            campaign_id,
            limit,
        )
