from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from bot.features.advent.admin_panel import (
    AdminActionSelect,
    CatchupDaysModal,
    parse_catchup_days,
)
from bot.features.advent.models import AdventOpening
from bot.features.advent.service import AdventService, catchup_window
from tests.test_advent_fixes import make_campaign

PARIS = ZoneInfo("Europe/Paris")
DECEMBER_10 = datetime(2026, 12, 10, 12, 0, tzinfo=PARIS)


def test_catchup_window() -> None:
    assert catchup_window(10, 3) == {7, 8, 9}
    assert catchup_window(2, 5) == {1}
    assert catchup_window(1, 3) == set()
    assert catchup_window(10, None) == set(range(1, 10))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ("unlimited", None)),
        ("  ", ("unlimited", None)),
        ("0", ("disabled", None)),
        ("3", ("limited", 3)),
        ("3 jours", ("limited", 3)),
        ("5j", ("limited", 5)),
        ("23", ("limited", 23)),
    ],
)
def test_parse_catchup_days(text: str, expected: tuple[str, int | None]) -> None:
    assert parse_catchup_days(text) == expected


@pytest.mark.parametrize("text", ["24", "-1", "trois", "2.5"])
def test_parse_catchup_days_rejects_invalid_values(text: str) -> None:
    with pytest.raises(ValueError):
        parse_catchup_days(text)


def make_service(openings: list[int]) -> AdventService:
    async def get_user_openings(campaign_id: int, user_id: int) -> list[AdventOpening]:
        return [
            AdventOpening(
                id=day,
                campaign_id=1,
                guild_id=1,
                user_id=user_id,
                day=day,
                opened_at=DECEMBER_10,
                reward_type="message",
                reward_snapshot={},
                points_awarded=0,
                external_status="not_required",
            )
            for day in openings
        ]

    return AdventService(
        repository=SimpleNamespace(get_user_openings=get_user_openings),  # type: ignore[arg-type]
        transactions=SimpleNamespace(),  # type: ignore[arg-type]
        reward_service=SimpleNamespace(),  # type: ignore[arg-type]
        default_timezone="Europe/Paris",
    )


async def test_limited_catchup_only_offers_recent_days() -> None:
    campaign = replace(make_campaign(), catchup_mode="enabled", catchup_days=3)
    service = make_service(openings=[8])

    state = await service.get_calendar_state(
        guild_id=1,
        user_id=1,
        campaign=campaign,
        moment=DECEMBER_10,
    )

    assert state.available_days == {7, 9, 10}
    assert state.missed_days == {1, 2, 3, 4, 5, 6}
    assert state.opened_days == {8}


async def test_unlimited_catchup_offers_every_past_day() -> None:
    campaign = replace(make_campaign(), catchup_mode="enabled", catchup_days=None)
    service = make_service(openings=[])

    state = await service.get_calendar_state(
        guild_id=1,
        user_id=1,
        campaign=campaign,
        moment=DECEMBER_10,
    )

    assert state.available_days == set(range(1, 11))
    assert state.missed_days == set()


async def test_disabled_catchup_ignores_the_limit() -> None:
    campaign = replace(make_campaign(), catchup_mode="disabled", catchup_days=3)
    service = make_service(openings=[])

    state = await service.get_calendar_state(
        guild_id=1,
        user_id=1,
        campaign=campaign,
        moment=DECEMBER_10,
    )

    assert state.available_days == {10}
    assert state.missed_days == set(range(1, 10))


async def test_modal_shows_the_current_setting() -> None:
    assert CatchupDaysModal(current=3, catchup_enabled=True).days.default == "3"
    assert CatchupDaysModal(current=None, catchup_enabled=False).days.default == "0"
    assert not CatchupDaysModal(current=None, catchup_enabled=True).days.default


def test_catchup_limit_is_in_the_admin_menu() -> None:
    options = AdminActionSelect().options

    assert "catchup_days" in [option.value for option in options]
    assert len(options) <= 25
