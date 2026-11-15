from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import discord

from bot.extensions.profile import CosmeticInventoryView, GrantCosmeticView
from bot.extensions.rappel import parse_duration
from bot.extensions.reaction_roles import emoji_match_key
from bot.extensions.shop import ShopCosmeticSelectView


def make_cosmetics(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": index,
            "identifier": f"badge-{index}",
            "cosmetic_type": "badge",
            "display_name": f"Badge {index}",
            "description": "",
        }
        for index in range(1, count + 1)
    ]


def select_values(view: discord.ui.View) -> list[str]:
    return [
        option.value
        for item in view.children
        if isinstance(item, discord.ui.Select)
        and not isinstance(item, discord.ui.UserSelect)
        for option in item.options
    ]


async def test_inventory_shows_more_than_25_cosmetics() -> None:
    view = CosmeticInventoryView(
        cog=SimpleNamespace(),  # type: ignore[arg-type]
        owner_id=1,
        cosmetics=make_cosmetics(60),
    )

    assert len(select_values(view)) == 60
    assert view.reset_cosmetics.row == 3
    view.to_components()


async def test_small_inventory_keeps_a_single_menu() -> None:
    view = CosmeticInventoryView(
        cog=SimpleNamespace(),  # type: ignore[arg-type]
        owner_id=1,
        cosmetics=make_cosmetics(3),
    )

    selects = [item for item in view.children if isinstance(item, discord.ui.Select)]
    assert len(selects) == 1
    assert view.reset_cosmetics.row == 1


async def test_admin_menus_show_more_than_25_cosmetics() -> None:
    grant_view = GrantCosmeticView(
        cog=SimpleNamespace(),  # type: ignore[arg-type]
        guild_id=1,
        cosmetics=make_cosmetics(60),
    )
    shop_view = ShopCosmeticSelectView(
        cog=SimpleNamespace(),  # type: ignore[arg-type]
        owner_id=1,
        cosmetics=make_cosmetics(60),
    )

    assert len(select_values(grant_view)) == 60
    assert len(select_values(shop_view)) == 60
    grant_view.to_components()
    shop_view.to_components()


def test_reminder_durations_accept_common_french_formats() -> None:
    assert parse_duration("1h30") == timedelta(minutes=90)
    assert parse_duration("1 heure 30") == timedelta(minutes=90)
    assert parse_duration("5mn") == timedelta(minutes=5)
    assert parse_duration("1j12h") == timedelta(days=1, hours=12)
    assert parse_duration("45") == timedelta(minutes=45)
    assert parse_duration("bientôt") is None


def test_reaction_emojis_match_despite_discord_variations() -> None:
    assert emoji_match_key("<a:coucou:123>") == emoji_match_key("<:coucou:123>")
    assert emoji_match_key("<:ancien_nom:123>") == emoji_match_key("<:nouveau_nom:123>")
    assert emoji_match_key("❤️") == emoji_match_key("❤")
    assert emoji_match_key("👍") != emoji_match_key("👎")
