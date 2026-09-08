from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AdventCampaign:
    id: int
    guild_id: int
    year: int
    title: str
    start_date: date
    end_date: date
    timezone: str
    opening_hour: int
    catchup_mode: str
    channel_id: int | None
    announcement_role_id: int | None
    announcements_enabled: bool
    enabled: bool
    day_order: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class AdventReward:
    id: int
    campaign_id: int
    day: int
    reward_type: str
    reward_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AdventOpening:
    id: int
    campaign_id: int
    guild_id: int
    user_id: int
    day: int
    opened_at: datetime
    reward_type: str
    reward_snapshot: dict[str, Any]
    points_awarded: int
    external_status: str


@dataclass(frozen=True, slots=True)
class CalendarState:
    campaign: AdventCampaign
    today: date
    current_day: int | None
    opened_days: frozenset[int]
    missed_days: frozenset[int]
    available_days: frozenset[int]
    future_days: frozenset[int]
    total_points: int


@dataclass(frozen=True, slots=True)
class OpenResult:
    opening: AdventOpening
    reward_message: str
    role_id: int | None
    role_granted: bool = False
