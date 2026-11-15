from __future__ import annotations

from types import SimpleNamespace

from bot.extensions.zz_rankings import RankingsCog


class FakePool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchval(self, query: str, *args: object) -> int:
        self.calls.append((query, args))
        return 0

    async def fetch(self, query: str, *args: object) -> list[object]:
        self.calls.append((query, args))
        return []


def make_cog(*, chunked: bool, pool: FakePool) -> RankingsCog:
    guild = SimpleNamespace(
        chunked=chunked,
        members=[SimpleNamespace(id=10), SimpleNamespace(id=20)],
    )
    bot = SimpleNamespace(
        get_guild=lambda guild_id: guild if guild_id == 1 else None,
        settings=SimpleNamespace(project_root=None),
    )
    cog = RankingsCog.__new__(RankingsCog)
    cog.bot = bot  # type: ignore[assignment]
    cog.get_pool = lambda: pool  # type: ignore[method-assign]
    return cog


def test_present_members_are_listed_only_when_the_guild_is_loaded() -> None:
    pool = FakePool()

    assert make_cog(chunked=True, pool=pool).get_present_member_ids(1) == [10, 20]
    assert make_cog(chunked=False, pool=pool).get_present_member_ids(1) is None
    assert make_cog(chunked=True, pool=pool).get_present_member_ids(999) is None


async def test_every_ranking_query_filters_on_present_members() -> None:
    for ranking_type in ("xp", "money", "streak"):
        pool = FakePool()
        cog = make_cog(chunked=True, pool=pool)

        await cog.get_leaderboard_total_members(guild_id=1, ranking_type=ranking_type)
        await cog.get_leaderboard_records(guild_id=1, ranking_type=ranking_type, page=1)

        assert len(pool.calls) == 2

        for query, args in pool.calls:
            placeholder = f"${len(args)}::BIGINT[]"
            assert args[-1] == [10, 20]
            assert f"user_id = ANY({placeholder})" in query
