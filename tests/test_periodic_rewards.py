from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from bot.extensions import periodic_rewards as periodic
from bot.extensions.periodic_rewards import (
    MONTHLY,
    WEEKLY,
    apply_bonus,
    describe_settings,
    next_reset,
    parse_amount,
    period_start,
    previous_period_start,
    streak_bonus,
)


def paris(*args) -> datetime:
    return datetime(*args, tzinfo=periodic.PARIS)


def test_weekly_period_starts_monday_paris_time() -> None:
    # Mercredi 18 novembre 2026 → semaine du lundi 16.
    assert period_start(WEEKLY, paris(2026, 11, 18, 15, 0)) == date(2026, 11, 16)
    # Dimanche 23h30 à Paris = encore la même semaine, même si UTC dit autre chose.
    assert period_start(WEEKLY, paris(2026, 11, 22, 23, 30)) == date(2026, 11, 16)
    # Lundi 00h30 à Paris (dimanche 23h30 UTC) = nouvelle semaine.
    assert period_start(WEEKLY, datetime(2026, 11, 22, 23, 30, tzinfo=timezone.utc)) == date(2026, 11, 23)
    assert previous_period_start(WEEKLY, date(2026, 11, 16)) == date(2026, 11, 9)
    assert next_reset(WEEKLY, paris(2026, 11, 18, 15, 0)) == paris(2026, 11, 23, 0, 0)


def test_monthly_period_and_year_change() -> None:
    assert period_start(MONTHLY, paris(2026, 11, 30, 23, 59)) == date(2026, 11, 1)
    assert previous_period_start(MONTHLY, date(2026, 1, 1)) == date(2025, 12, 1)
    assert previous_period_start(MONTHLY, date(2026, 3, 1)) == date(2026, 2, 1)
    assert next_reset(MONTHLY, paris(2026, 12, 15, 12, 0)) == paris(2027, 1, 1, 0, 0)
    assert next_reset(MONTHLY, paris(2027, 1, 31, 12, 0)) == paris(2027, 2, 1, 0, 0)


def test_streak_bonus() -> None:
    assert streak_bonus(1, 10, 50) == 0
    assert streak_bonus(3, 10, 50) == 20
    assert streak_bonus(12, 10, 50) == 50  # plafonné
    assert streak_bonus(5, 0, 50) == 0
    assert apply_bonus(700, 20) == 840
    assert apply_bonus(0, 50) == 0


def test_parse_amount_and_description() -> None:
    assert parse_amount("1 500", "XP") == 1500
    assert parse_amount("20 %", "Bonus", 1000) == 20

    with pytest.raises(ValueError):
        parse_amount("-5", "XP")

    with pytest.raises(ValueError):
        parse_amount("2000", "Bonus", 1000)

    text = describe_settings(WEEKLY, {"xp": 700, "coins": 100, "bonus_percent": 10, "bonus_max": 50, "enabled": True})
    assert "700 XP" in text and "+10 % par semaine" in text and "/hebdomadaire" in text
    off = describe_settings(MONTHLY, {"xp": 1, "coins": 1, "bonus_percent": 0, "bonus_max": 50, "enabled": False})
    assert "désactivée" in off and "Pas de bonus" in off


def test_settings_modal_limits() -> None:
    cog = SimpleNamespace()
    modal = periodic.PeriodicSettingsModal(cog, MONTHLY, {**periodic.DEFAULTS[MONTHLY], "enabled": True})
    assert len(modal.title) <= 45 and len(modal.children) == 5

    for item in modal.children:
        assert len(item.text) <= 45
        assert item.description is None or len(item.description) <= 100


class FakeConnection:
    """Simule juste ce que claim() demande à la base."""

    def __init__(self, claims: dict) -> None:
        self.claims = claims  # (kind, period_start) -> streak
        self.progress = {"total_xp": 1000, "wallet": 0}
        self.transactions: list = []

    async def execute(self, query, *args):
        if "INSERT INTO periodic_reward_claims" in query:
            self.claims[(args[2], args[3])] = args[4]
        elif "UPDATE progression_members" in query:
            self.progress["total_xp"] += args[2]
            self.progress["wallet"] += args[3]
        elif "progression_transactions" in query:
            self.transactions.append(args)

    async def fetch(self, query, *args):
        kind, since = args[2], args[3]
        return [
            {"period_start": start, "streak": streak}
            for (claim_kind, start), streak in self.claims.items()
            if claim_kind == kind and start >= since
        ]

    async def fetchval(self, query, *args):
        if "MAX(streak)" in query:
            return max([s for (k, _), s in self.claims.items() if k == args[2]], default=0)
        return self.progress["total_xp"]

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def acquire(self):
        return self.connection

    async def fetchrow(self, query, *args):
        return None  # réglages par défaut


async def test_claim_streak_and_already_claimed() -> None:
    connection = FakeConnection({(WEEKLY, date(2026, 11, 9)): 2})
    cog = periodic.PeriodicRewardsCog(SimpleNamespace(database=SimpleNamespace(require_pool=lambda: FakePool(connection))))
    now = paris(2026, 11, 18, 12, 0)

    first = await cog.claim(1, 10, WEEKLY, now)
    assert first.status == "claimed" and first.streak == 3 and first.bonus == 20
    assert (first.xp, first.coins) == (840, 120)
    assert connection.progress == {"total_xp": 1840, "wallet": 120}
    assert connection.transactions and first.new_xp == 1840

    again = await cog.claim(1, 10, WEEKLY, now)
    assert again.status == "already" and again.streak == 3
    assert connection.progress["wallet"] == 120  # pas payé deux fois

    # Une semaine sautée : la série repart à 1.
    later = await cog.claim(1, 10, WEEKLY, paris(2026, 12, 2, 12, 0))
    assert later.streak == 1 and later.bonus == 0 and later.best_streak == 3
