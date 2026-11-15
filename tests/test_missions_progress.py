from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from bot.extensions import missions
from bot.extensions.missions import MissionsCog


class FakePool:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchval(self, query: str, *args: object) -> object:
        self.calls.append((query, args))
        return self.value


def make_cog(pool: FakePool) -> MissionsCog:
    cog = MissionsCog(SimpleNamespace())  # type: ignore[arg-type]
    cog.get_pool = lambda: pool  # type: ignore[method-assign]
    return cog


def test_weekly_period_starts_on_monday(monkeypatch) -> None:
    monkeypatch.setattr(missions, "current_paris_date", lambda: date(2026, 11, 19))

    assert missions.get_period_start("daily") == date(2026, 11, 19)
    assert missions.get_period_start("weekly") == date(2026, 11, 16)


async def test_messages_are_counted_from_the_start_of_the_period(monkeypatch) -> None:
    monkeypatch.setattr(missions, "current_paris_date", lambda: date(2026, 11, 16))
    pool = FakePool(7)

    progress = await make_cog(pool).get_period_progress(
        guild_id=1,
        user_id=2,
        metric="messages",
        period="daily",
    )

    query, args = pool.calls[0]
    assert progress == 7
    assert args == (1, 2, date(2026, 11, 16))
    assert "SUM(rewarded_messages)" in query
    assert "statistics_member_state" in query


async def test_daily_claims_are_counted_from_paris_midnight(monkeypatch) -> None:
    monkeypatch.setattr(missions, "current_paris_date", lambda: date(2026, 11, 19))
    pool = FakePool(3)

    progress = await make_cog(pool).get_period_progress(
        guild_id=1,
        user_id=2,
        metric="daily_claims",
        period="weekly",
    )

    start = pool.calls[0][1][2]
    assert progress == 3
    assert isinstance(start, datetime)
    assert start.date() == date(2026, 11, 16)
    assert start.utcoffset() is not None


async def test_streak_keeps_the_recorded_baseline() -> None:
    pool = FakePool(0)

    progress = await make_cog(pool).get_period_progress(
        guild_id=1,
        user_id=2,
        metric="streak",
        period="daily",
    )

    assert progress is None
    assert pool.calls == []
