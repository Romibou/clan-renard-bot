from datetime import date, datetime
from zoneinfo import ZoneInfo

from bot.features.advent.models import AdventCampaign
from bot.features.advent.service import AdventService


def campaign(opening_hour: int = 0) -> AdventCampaign:
    return AdventCampaign(
        id=1,
        guild_id=1,
        year=2026,
        title="Calendrier de l'Avent",
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 24),
        timezone="Europe/Paris",
        opening_hour=opening_hour,
        catchup_mode="disabled",
        channel_id=None,
        announcement_role_id=None,
        announcements_enabled=False,
        enabled=True,
        day_order=tuple(range(1, 25)),
    )


def test_current_day_during_campaign() -> None:
    moment = datetime(
        2026,
        12,
        8,
        12,
        0,
        tzinfo=ZoneInfo("Europe/Paris"),
    )

    assert AdventService.current_day(
        campaign(),
        moment,
    ) == 8


def test_before_campaign() -> None:
    moment = datetime(
        2026,
        11,
        30,
        23,
        59,
        tzinfo=ZoneInfo("Europe/Paris"),
    )

    assert AdventService.current_day(
        campaign(),
        moment,
    ) is None


def test_opening_hour_keeps_previous_day() -> None:
    moment = datetime(
        2026,
        12,
        8,
        5,
        30,
        tzinfo=ZoneInfo("Europe/Paris"),
    )

    assert AdventService.current_day(
        campaign(opening_hour=6),
        moment,
    ) == 7
