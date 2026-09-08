from datetime import date
from pathlib import Path

import pytest

from bot.features.advent.image_generator import (
    AdventImageGenerator,
)
from bot.features.advent.models import (
    AdventCampaign,
    CalendarState,
)


@pytest.mark.asyncio
async def test_calendar_is_valid_png() -> None:
    root = Path(__file__).resolve().parents[1]
    generator = AdventImageGenerator(root)

    campaign = AdventCampaign(
        id=1,
        guild_id=1,
        year=2026,
        title="Calendrier de l'Avent",
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 24),
        timezone="Europe/Paris",
        opening_hour=0,
        catchup_mode="disabled",
        channel_id=None,
        announcement_role_id=None,
        announcements_enabled=False,
        enabled=True,
        day_order=tuple(range(1, 25)),
    )

    state = CalendarState(
        campaign=campaign,
        today=date(2026, 12, 8),
        current_day=8,
        opened_days=frozenset(
            {1, 2, 3}
        ),
        missed_days=frozenset(
            {4, 5, 6, 7}
        ),
        available_days=frozenset(
            {8}
        ),
        future_days=frozenset(
            range(9, 25)
        ),
        total_points=300,
    )

    rendered = await generator.render(
        state,
        "Test Clan Renard",
    )

    data = rendered.buffer.getvalue()

    assert data.startswith(
        b"\x89PNG\r\n\x1a\n"
    )
    assert len(data) > 10_000
    assert rendered.filename.endswith(
        ".png"
    )
