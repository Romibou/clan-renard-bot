from __future__ import annotations

import random
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from bot.extensions.bilan import is_recap_open, recap_year
from bot.extensions.giveaway import build_giveaway_embed, draw_winners
from bot.extensions.xp_boost import (
    XPBoost,
    XPBoostCog,
    parse_boost_form,
    parse_multiplier,
    parse_paris_datetime,
)
from bot.features.advent.admin_panel import AdminModal, RewardTypeSelect
from bot.features.advent.models import AdventOpening
from bot.features.advent.permanent_rewards import deliver_permanent_reward
from bot.features.advent.reward_service import RewardService
from bot.shared.recap_card import RecapStats, build_recap_cards, render_recap_card

PARIS = ZoneInfo("Europe/Paris")
UTC = timezone.utc


# ---------- Nouvelles récompenses de l'Avent ----------


def test_coins_xp_and_cosmetic_rewards_resolve() -> None:
    service = RewardService()

    coins = service._resolve_definition("coins", {"coins": 250})
    assert coins.snapshot["coins"] == 250
    assert "250 pièces" in coins.message
    assert coins.external_status == "pending"
    assert coins.points == 0

    xp = service._resolve_definition("xp", {"xp": 1000, "message": "Bravo !"})
    assert xp.snapshot == {"xp": 1000, "message": "Bravo !"}

    cosmetic = service._resolve_definition(
        "cosmetic",
        {"cosmetic_id": 7, "name": "Cadre givré"},
    )
    assert cosmetic.snapshot["cosmetic_id"] == 7
    assert "Cadre givré" in cosmetic.message
    assert "/profil" in cosmetic.message


def test_random_reward_can_pick_coins() -> None:
    resolved = RewardService()._resolve_definition(
        "random",
        {"choices": [{"type": "coins", "weight": 1, "data": {"coins": 40}}]},
    )

    assert resolved.reward_type == "coins"
    assert resolved.snapshot["coins"] == 40
    assert resolved.snapshot["selected_from_random"] is True


@pytest.mark.parametrize("data", [{"coins": 0}, {"coins": -5}, {"coins": "beaucoup"}])
def test_invalid_amounts_are_rejected(data: dict[str, object]) -> None:
    from bot.features.advent.exceptions import RewardConfigurationError

    with pytest.raises(RewardConfigurationError):
        RewardService()._resolve_definition("coins", data)


def make_opening(reward_type: str, snapshot: dict[str, object]) -> AdventOpening:
    return AdventOpening(
        id=99,
        campaign_id=1,
        guild_id=1,
        user_id=5,
        day=3,
        opened_at=datetime.now(UTC),
        reward_type=reward_type,
        reward_snapshot=snapshot,
        points_awarded=0,
        external_status="pending",
    )


class FakeConnection:
    def __init__(self, log: list[tuple[str, tuple[object, ...]]]) -> None:
        self.log = log

    async def execute(self, query: str, *args: object) -> str:
        self.log.append((" ".join(query.split()), args))
        return "OK"

    async def fetchval(self, query: str, *args: object) -> int:
        return 900


class FakeDatabase:
    def __init__(self) -> None:
        self.log: list[tuple[str, tuple[object, ...]]] = []

    @asynccontextmanager
    async def transaction(self):
        yield FakeConnection(self.log)


class FakeService:
    def __init__(self) -> None:
        self.results: list[tuple[int, bool]] = []

    async def mark_role_result(self, *, opening_id: int, success: bool, error=None) -> None:
        self.results.append((opening_id, success))


async def test_coins_reward_is_credited_to_the_wallet() -> None:
    database = FakeDatabase()
    service = FakeService()
    bot = SimpleNamespace(database=database, get_cog=lambda name: None)

    ok, warning = await deliver_permanent_reward(
        bot=bot,  # type: ignore[arg-type]
        guild=SimpleNamespace(id=1),  # type: ignore[arg-type]
        member=None,
        user_id=5,
        opening=make_opening("coins", {"coins": 250}),
        service=service,  # type: ignore[arg-type]
    )

    assert ok and warning is None
    update = next(q for q in database.log if q[0].startswith("UPDATE progression_members"))
    assert update[1] == (1, 5, 0, 250)
    assert any("advent_reward" in q[1] for q in database.log)
    assert service.results == [(99, True)]


async def test_cosmetic_reward_goes_to_the_profile_inventory() -> None:
    granted: list[dict[str, object]] = []

    async def grant_cosmetic(**kwargs: object) -> None:
        granted.append(kwargs)

    profile = SimpleNamespace(grant_cosmetic=grant_cosmetic)
    bot = SimpleNamespace(
        database=FakeDatabase(),
        get_cog=lambda name: profile if name == "ProfileCog" else None,
    )
    service = FakeService()

    ok, _ = await deliver_permanent_reward(
        bot=bot,  # type: ignore[arg-type]
        guild=SimpleNamespace(id=1),  # type: ignore[arg-type]
        member=None,
        user_id=5,
        opening=make_opening("cosmetic", {"cosmetic_id": 7, "name": "Cadre"}),
        service=service,  # type: ignore[arg-type]
    )

    assert ok
    assert granted[0]["cosmetic_id"] == 7
    assert granted[0]["user_id"] == 5


async def test_failed_delivery_is_reported_not_lost() -> None:
    bot = SimpleNamespace(database=FakeDatabase(), get_cog=lambda name: None)
    service = FakeService()

    ok, warning = await deliver_permanent_reward(
        bot=bot,  # type: ignore[arg-type]
        guild=SimpleNamespace(id=1),  # type: ignore[arg-type]
        member=None,
        user_id=5,
        opening=make_opening("cosmetic", {"cosmetic_id": 7}),
        service=service,  # type: ignore[arg-type]
    )

    assert not ok
    assert "administrateur" in (warning or "")
    assert service.results == [(99, False)]


def test_reward_type_menu_and_forms() -> None:
    values = [option.value for option in RewardTypeSelect().options]

    assert values == [
        "reward_message",
        "reward_points",
        "reward_coins",
        "reward_xp",
        "reward_cosmetic",
        "reward_role",
        "reward_random",
    ]
    assert set(AdminModal(action="reward_coins").inputs) == {"day", "amount", "message", "year"}
    assert set(AdminModal(action="reward_cosmetic").inputs) == {
        "day",
        "identifier",
        "message",
        "year",
    }


# ---------- Bonus d'XP ----------


NOW = datetime(2026, 12, 20, 15, 0, tzinfo=PARIS).astimezone(UTC)


def test_parse_multiplier() -> None:
    assert parse_multiplier("2") == Decimal("2.00")
    assert parse_multiplier("x1,5") == Decimal("1.50")
    assert parse_multiplier("×3") == Decimal("3.00")
    assert parse_multiplier("1") is None
    assert parse_multiplier("") is None

    for invalid in ("6", "1.05", "deux"):
        with pytest.raises(ValueError):
            parse_multiplier(invalid)


def test_parse_paris_dates() -> None:
    start = parse_paris_datetime("24/12", now=NOW, end_of_day=False)
    end = parse_paris_datetime("26/12", now=NOW, end_of_day=True)
    january = parse_paris_datetime("02/01 18h", now=NOW, end_of_day=True)

    assert start == datetime(2026, 12, 24, 0, 0, tzinfo=PARIS)
    assert end == datetime(2026, 12, 26, 23, 59, tzinfo=PARIS)
    assert january == datetime(2027, 1, 2, 18, 0, tzinfo=PARIS)

    with pytest.raises(ValueError):
        parse_paris_datetime("31/02", now=NOW, end_of_day=False)


def test_boost_form_validation() -> None:
    multiplier, starts, ends = parse_boost_form(
        multiplier_text="2",
        start_text="",
        end_text="26/12",
        now=NOW,
    ) or (None, None, None)

    assert multiplier == Decimal("2.00")
    assert starts == NOW
    assert ends.astimezone(PARIS).day == 26

    assert parse_boost_form(multiplier_text="1", start_text="", end_text="", now=NOW) is None

    with pytest.raises(ValueError, match="après le début"):
        parse_boost_form(multiplier_text="2", start_text="26/12", end_text="24/12", now=NOW)

    with pytest.raises(ValueError, match="fin"):
        parse_boost_form(multiplier_text="2", start_text="", end_text="", now=NOW)


async def test_boost_only_applies_during_its_window() -> None:
    cog = XPBoostCog.__new__(XPBoostCog)
    cog._cache = {}
    boost = XPBoost(
        multiplier=Decimal("2"),
        starts_at=NOW,
        ends_at=NOW + timedelta(days=2),
        label="Noël",
    )

    async def get_boost(guild_id: int, *, use_cache: bool = True) -> XPBoost:
        return boost

    cog.get_boost = get_boost  # type: ignore[method-assign]

    assert await cog.get_active_multiplier(1, NOW - timedelta(minutes=1)) == 1
    assert await cog.get_active_multiplier(1, NOW + timedelta(hours=1)) == 2
    assert await cog.get_active_multiplier(1, NOW + timedelta(days=2)) == 1


async def test_boost_multiplies_role_multiplier() -> None:
    from bot.extensions.progression import ProgressionCog

    class Pool:
        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            return [{"role_id": 10, "multiplier": Decimal("1.50")}]

    async def active(guild_id: int) -> Decimal:
        return Decimal("2.00")

    boost_cog = SimpleNamespace(get_active_multiplier=active)
    bot = SimpleNamespace(get_cog=lambda name: boost_cog if name == "XPBoostCog" else None)
    cog = ProgressionCog(bot)  # type: ignore[arg-type]
    cog.get_pool = lambda: Pool()  # type: ignore[method-assign]
    member = SimpleNamespace(guild=SimpleNamespace(id=1), roles=[SimpleNamespace(id=10)])

    assert await cog.get_member_xp_multiplier(member) == Decimal("3.00")  # type: ignore[arg-type]


# ---------- Giveaway ----------


def test_draw_winners_is_unique_and_bounded() -> None:
    rng = random.Random(4)

    winners = draw_winners([1, 2, 3, 3, 4], 3, rng)
    assert len(winners) == 3
    assert len(set(winners)) == 3
    assert set(winners) <= {1, 2, 3, 4}

    assert sorted(draw_winners([1, 2], 5, rng)) == [1, 2]
    assert draw_winners([], 2, rng) == []


def test_giveaway_embed_shows_prize_and_automatic_rewards() -> None:
    record = {
        "id": 12,
        "prize": "Nitro",
        "coins": 500,
        "role_id": 77,
        "ends_at": datetime(2026, 12, 24, tzinfo=UTC),
        "winners_count": 2,
        "min_level": 5,
    }

    running = build_giveaway_embed(record, entries=8)
    assert "Nitro" in running.description
    assert "500 pièces" in running.description
    assert "<@&77>" in running.description
    assert "Niveau minimum : **5**" in running.description
    assert "Participants : **8**" in running.description

    finished = build_giveaway_embed(record, entries=8, winners=[1, 2])
    assert "TERMINÉ" in finished.title
    assert "<@1>" in finished.description


# ---------- Bilan ----------


def test_recap_availability_window() -> None:
    assert not is_recap_open(date(2026, 12, 30))
    assert is_recap_open(date(2026, 12, 31))
    assert is_recap_open(date(2027, 1, 31))
    assert not is_recap_open(date(2027, 2, 1))

    assert recap_year(date(2026, 12, 31)) == 2026
    assert recap_year(date(2027, 1, 15)) == 2026


def make_stats(**overrides: object) -> RecapStats:
    values = dict(
        year=2026,
        xp_gained=48210,
        year_rank=3,
        ranked_members=57,
        rewarded_messages=2410,
        voice_minutes=4385,
        coins_gained=7320,
        best_day="14/12",
        best_day_xp=1820,
        daily_claims=212,
        best_streak=45,
        advent_openings=18,
        stats_since="12/09/2026",
    )
    values.update(overrides)
    return RecapStats(**values)  # type: ignore[arg-type]


def test_recap_cards_content() -> None:
    cards = dict((label, value) for label, value, _ in build_recap_cards(make_stats()))

    assert cards["XP GAGNÉE"] == "48 210 XP"
    assert cards["CLASSEMENT DE L'ANNÉE"] == "#3 sur 57"
    assert cards["TEMPS EN VOCAL"] == "73 h 05"
    assert cards["CALENDRIER DE L'AVENT"] == "18/24 cases"

    empty = dict(
        (label, value)
        for label, value, _ in build_recap_cards(
            make_stats(year_rank=None, advent_openings=None, best_day=None, best_streak=1)
        )
    )
    assert empty["CLASSEMENT DE L'ANNÉE"] == "Non classé"
    assert empty["CALENDRIER DE L'AVENT"] == "—"
    assert empty["MEILLEURE SÉRIE"] == "1 jour"


def test_recap_card_renders_a_png() -> None:
    image = render_recap_card(
        display_name="Renard",
        avatar_bytes=None,
        stats=make_stats(),
    )

    assert image.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
