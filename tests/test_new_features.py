from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import discord
import pytest
from discord import app_commands

from bot.extensions.aide import build_help_embed
from bot.extensions.daily import DailyReminderToggleView, get_reminder_time
from bot.extensions.donner import GiftError, check_gift_allowed, paris_midnight
from bot.extensions.zz_rankings import RankingsCog, get_period_start

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from restaurer_base import dependency_order  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")


# ---------- Heure du rappel quotidien ----------


def test_reminder_is_sent_at_the_chosen_hour_the_next_day() -> None:
    claimed = datetime(2026, 11, 16, 20, 0, tzinfo=PARIS)

    assert get_reminder_time(claimed, 9).astimezone(PARIS) == datetime(
        2026, 11, 17, 9, 0, tzinfo=PARIS
    )
    assert get_reminder_time(claimed, 0).astimezone(PARIS) == datetime(
        2026, 11, 17, 0, 0, tzinfo=PARIS
    )


def test_reminder_hour_follows_daylight_saving_time() -> None:
    claimed = datetime(2027, 3, 27, 12, 0, tzinfo=PARIS)

    reminder = get_reminder_time(claimed, 9).astimezone(PARIS)

    assert reminder.hour == 9
    assert reminder.date() == date(2027, 3, 28)


async def test_reminder_view_offers_the_24_hours() -> None:
    view = DailyReminderToggleView(
        cog=SimpleNamespace(),  # type: ignore[arg-type]
        owner_id=1,
        guild_id=1,
        user_id=1,
    )
    selects = [item for item in view.children if isinstance(item, discord.ui.Select)]

    assert [option.value for option in selects[0].options] == [str(h) for h in range(24)]
    view.to_components()


# ---------- /aide ----------


def make_command(name: str, *, admin: bool = False) -> app_commands.Command:
    async def callback(interaction: discord.Interaction) -> None:
        return None

    command = app_commands.Command(
        name=name,
        description=f"Description de {name}",
        callback=callback,
    )

    if admin:
        command.default_permissions = discord.Permissions(manage_guild=True)

    return command


def test_help_lists_member_commands_by_category_and_hides_admin_ones() -> None:
    commands_list = [
        make_command("quotidien"),
        make_command("classement"),
        make_command("nouvelle-commande"),
        make_command("boutique-admin", admin=True),
    ]

    member_embed = build_help_embed(commands_list, show_admin=False)
    text = "\n".join(f"{field.name}\n{field.value}" for field in member_embed.fields)

    assert "`/quotidien`" in text
    assert "`/classement`" in text
    assert "`/nouvelle-commande`" in text
    assert "boutique-admin" not in text

    admin_embed = build_help_embed(commands_list, show_admin=True)
    assert "boutique-admin" in admin_embed.fields[-1].value


# ---------- Classements de période ----------


def test_period_start_is_monday_or_first_of_month() -> None:
    thursday = date(2026, 11, 19)

    assert get_period_start("xp_week", thursday) == date(2026, 11, 16)
    assert get_period_start("xp_month", thursday) == date(2026, 11, 1)


async def test_weekly_ranking_query_uses_daily_statistics() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakePool:
        async def fetch(self, query: str, *args: object) -> list[dict[str, int]]:
            calls.append((query, args))
            return [
                {"user_id": 7, "period_xp": 900},
                {"user_id": 3, "period_xp": 400},
            ]

    cog = RankingsCog.__new__(RankingsCog)
    cog.bot = SimpleNamespace(get_guild=lambda guild_id: None)  # type: ignore[assignment]
    cog.get_pool = lambda: FakePool()  # type: ignore[method-assign]

    personal = await cog.get_personal_leaderboard_data(
        guild_id=1,
        user_id=3,
        ranking_type="xp_week",
    )
    total = await cog.get_leaderboard_total_members(guild_id=1, ranking_type="xp_week")

    assert personal["rank"] == 2
    assert personal["period_xp"] == 400
    assert total == 2
    assert "FROM statistics_daily" in calls[0][0]
    assert "SUM(xp_gained)" in calls[0][0]


# ---------- /donner ----------


def test_gift_rules() -> None:
    check_gift_allowed(amount=100, wallet=100, given_today=400)

    with pytest.raises(GiftError, match="encore donner"):
        check_gift_allowed(amount=200, wallet=1000, given_today=400)

    with pytest.raises(GiftError, match="limite quotidienne"):
        check_gift_allowed(amount=1, wallet=1000, given_today=500)

    with pytest.raises(GiftError, match="Tu n'as que"):
        check_gift_allowed(amount=50, wallet=20, given_today=0)


def test_gift_day_starts_at_paris_midnight() -> None:
    late_evening_utc = datetime(2026, 11, 16, 23, 30, tzinfo=ZoneInfo("UTC"))

    assert paris_midnight(late_evening_utc) == datetime(2026, 11, 17, 0, 0, tzinfo=PARIS)


# ---------- Restauration ----------


async def test_restore_fills_parent_tables_first() -> None:
    class FakeConnection:
        async def fetch(self, query: str) -> list[dict[str, str]]:
            return [
                {"child": "achats", "parent": "articles"},
                {"child": "articles", "parent": "campagnes"},
            ]

    order = await dependency_order(
        FakeConnection(),  # type: ignore[arg-type]
        ["achats", "articles", "campagnes", "membres"],
    )

    assert order.index("campagnes") < order.index("articles") < order.index("achats")
    assert sorted(order) == ["achats", "articles", "campagnes", "membres"]
