from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.extensions.drop import DropCog, build_drop_embed, describe_amounts, is_trap
from bot.shared.economy import apply_signed_change

UTC = timezone.utc


def make_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": 4,
        "xp": 500,
        "coins": 0,
        "max_claims": 3,
        "hidden": False,
        "note": None,
        "ended": False,
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
    }
    record.update(overrides)
    return record


def test_describe_amounts() -> None:
    assert describe_amounts(500, 0) == "+500 XP"
    assert describe_amounts(0, -1200) == "−1 200 pièces"
    assert describe_amounts(100, -50) == "+100 XP et −50 pièces"
    assert is_trap(0, -1)
    assert not is_trap(10, 0)


def test_visible_drop_shows_the_reward() -> None:
    embed = build_drop_embed(make_record(), [], finished=False)

    assert "+500 XP" in embed.description
    assert "3** premiers" in embed.description


def test_mystery_drop_hides_amounts_until_it_ends() -> None:
    record = make_record(xp=-300, hidden=True)
    claims = [(1, -300, 0)]

    running = build_drop_embed(record, claims, finished=False)
    assert "300" not in running.description
    assert "mystère" in running.description.lower()
    assert "<@1>" in running.description

    finished = build_drop_embed(record, claims, finished=True)
    assert "−300 XP" in finished.description
    assert "piège" in finished.description


def test_expired_drop_without_claims() -> None:
    embed = build_drop_embed(make_record(ended=True), [], finished=True)

    assert "Personne" in embed.description


class FakeConnection:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state

    async def execute(self, query: str, *args: object) -> str:
        if query.strip().startswith("UPDATE progression_members"):
            self.state["update"] = args
        if "INSERT INTO progression_transactions" in query:
            self.state["transaction"] = args
        if "INSERT INTO drop_claims" in query:
            self.state.setdefault("claims", []).append(args[1])
        if "UPDATE drops SET ended" in query:
            self.state["ended"] = True
        return "OK"

    async def fetchrow(self, query: str, *args: object):
        if "FROM drops" in query:
            return self.state["drop"]
        return {"total_xp": self.state["xp"], "wallet": self.state["wallet"]}

    async def fetchval(self, query: str, *args: object):
        if "EXISTS" in query:
            return args[1] in self.state.get("claims", [])
        return len(self.state.get("claims", []))


class FakeDatabase:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state

    @asynccontextmanager
    async def transaction(self):
        yield FakeConnection(self.state)


async def test_negative_drop_never_goes_below_zero() -> None:
    state: dict[str, object] = {"xp": 100, "wallet": 30}

    result = await apply_signed_change(
        FakeDatabase(state),
        guild_id=1,
        user_id=2,
        xp=-500,
        coins=-200,
        transaction_type="drop",
        reason="Drop n°1",
    )

    assert result == {"old_xp": 100, "new_xp": 0, "xp_delta": -100, "coins_delta": -30}
    assert state["update"] == (1, 2, 0, 0, 0)
    assert state["transaction"][2] == -30


async def test_positive_drop_counts_as_earned_coins() -> None:
    state: dict[str, object] = {"xp": 100, "wallet": 30}

    result = await apply_signed_change(
        FakeDatabase(state),
        guild_id=1,
        user_id=2,
        xp=50,
        coins=70,
        transaction_type="drop",
        reason="Drop n°1",
    )

    assert result["coins_delta"] == 70
    assert state["update"] == (1, 2, 150, 100, 70)


async def test_places_are_limited_and_one_per_member() -> None:
    state: dict[str, object] = {"drop": make_record(max_claims=2)}
    cog = DropCog.__new__(DropCog)
    cog.bot = SimpleNamespace(database=FakeDatabase(state))  # type: ignore[assignment]

    assert (await cog.reserve_claim(4, 1))[1] == "ok"
    assert (await cog.reserve_claim(4, 1))[1] == "already"
    assert (await cog.reserve_claim(4, 2))[1] == "ok"
    assert state["ended"] is True
    assert (await cog.reserve_claim(4, 3))[1] == "full"


async def test_expired_drop_cannot_be_claimed() -> None:
    state: dict[str, object] = {
        "drop": make_record(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    }
    cog = DropCog.__new__(DropCog)
    cog.bot = SimpleNamespace(database=FakeDatabase(state))  # type: ignore[assignment]

    assert (await cog.reserve_claim(4, 1))[1] == "ended"
