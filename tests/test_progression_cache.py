from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from bot.extensions.progression import ProgressionCog


class FakePool:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.fetch_calls = 0

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_calls += 1
        return self.rows

    async def execute(self, query: str, *args: object) -> str:
        return "OK"


def make_cog(pool: FakePool) -> ProgressionCog:
    bot = SimpleNamespace(database=SimpleNamespace(pool=pool))
    cog = ProgressionCog(bot)  # type: ignore[arg-type]
    cog.get_pool = lambda: pool  # type: ignore[method-assign]
    return cog


def make_member(*role_ids: int) -> SimpleNamespace:
    return SimpleNamespace(
        guild=SimpleNamespace(id=1),
        roles=[SimpleNamespace(id=role_id) for role_id in role_ids],
    )


async def test_multiplier_uses_highest_role_and_single_query() -> None:
    pool = FakePool(
        [
            {"role_id": 10, "multiplier": Decimal("1.50")},
            {"role_id": 20, "multiplier": Decimal("3.00")},
        ]
    )
    cog = make_cog(pool)

    assert await cog.get_member_xp_multiplier(make_member(10, 20)) == Decimal("3.00")
    assert await cog.get_member_xp_multiplier(make_member(10)) == Decimal("1.50")
    assert await cog.get_member_xp_multiplier(make_member(99)) == Decimal("1.00")
    assert pool.fetch_calls == 1


async def test_multiplier_cache_is_cleared_when_a_rule_changes() -> None:
    pool = FakePool([{"role_id": 10, "multiplier": Decimal("2.00")}])
    cog = make_cog(pool)

    await cog.get_member_xp_multiplier(make_member(10))
    await cog.set_role_xp_multiplier(
        guild_id=1,
        role_id=10,
        multiplier=Decimal("4"),
    )
    pool.rows = [{"role_id": 10, "multiplier": Decimal("4.00")}]

    assert await cog.get_member_xp_multiplier(make_member(10)) == Decimal("4.00")
    assert pool.fetch_calls == 2


def test_message_cooldown_is_tracked_in_memory() -> None:
    cog = make_cog(FakePool([]))

    assert not cog.is_in_message_cooldown(guild_id=1, user_id=2, cooldown_seconds=60)

    cog.remember_message_reward(guild_id=1, user_id=2)

    assert cog.is_in_message_cooldown(guild_id=1, user_id=2, cooldown_seconds=60)
    assert not cog.is_in_message_cooldown(guild_id=1, user_id=3, cooldown_seconds=60)
    assert not cog.is_in_message_cooldown(guild_id=1, user_id=2, cooldown_seconds=0)


def test_message_cooldown_accounts_for_time_already_elapsed() -> None:
    cog = make_cog(FakePool([]))

    cog.remember_message_reward(guild_id=1, user_id=2, elapsed_seconds=50)

    assert cog.is_in_message_cooldown(guild_id=1, user_id=2, cooldown_seconds=60)
    assert not cog.is_in_message_cooldown(guild_id=1, user_id=2, cooldown_seconds=45)
