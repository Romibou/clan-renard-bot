from __future__ import annotations

from types import SimpleNamespace

import discord

from bot.extensions.advent_shop import AdventShopView
from bot.extensions.shop import PermanentShopView
from bot.shared.pagination import resolve_page


def permanent_items(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": index,
            "identifier": f"article-{index}",
            "display_name": f"Article {index}",
            "item_type": "role",
            "price": index,
            "minimum_level": 0,
        }
        for index in range(1, count + 1)
    ]


def advent_items(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": index,
            "identifier": f"cadeau-{index}",
            "display_name": f"Cadeau {index}",
            "emoji": "🎁",
            "price": index,
            "min_openings": 0,
        }
        for index in range(1, count + 1)
    ]


def make_permanent_view() -> PermanentShopView:
    return PermanentShopView(
        cog=SimpleNamespace(),  # type: ignore[arg-type]
        owner_id=1,
        guild_id=1,
    )


def update_permanent(view: PermanentShopView, items: list[dict[str, object]]) -> None:
    view.update_components(
        items=items,
        purchased_item_ids=set(),
        wallet=1000,
        level=10,
    )


def option_values(select: discord.ui.Select) -> list[str]:
    return [option.value for option in select.options]


def test_resolve_page_follows_the_selected_item() -> None:
    identifiers = [f"a{index}" for index in range(60)]

    assert resolve_page(identifiers, "a30", 0) == (1, "a30")
    assert resolve_page(identifiers, None, 2) == (2, "a50")
    assert resolve_page(identifiers, "disparu", 9) == (2, "a50")
    assert resolve_page([], None, 3) == (0, None)


async def test_small_shop_has_no_page_buttons() -> None:
    view = make_permanent_view()
    update_permanent(view, permanent_items(10))

    assert len(option_values(view.item_select)) == 10
    assert view.next_page_button not in view.children
    view.to_components()


async def test_large_shop_shows_every_item_across_pages() -> None:
    view = make_permanent_view()
    items = permanent_items(60)
    seen: list[str] = []

    update_permanent(view, items)
    assert view.page_indicator.label == "Page 1/3"
    assert view.previous_page_button.disabled
    assert not view.next_page_button.disabled
    view.to_components()

    for _ in range(3):
        seen += option_values(view.item_select)
        view.page += 1
        view.selected_identifier = None
        update_permanent(view, items)

    assert seen == [str(item["identifier"]) for item in items]
    assert view.next_page_button.disabled


async def test_selected_item_stays_on_its_page_after_refresh() -> None:
    view = make_permanent_view()
    items = permanent_items(60)
    view.selected_identifier = "article-40"

    update_permanent(view, items)

    assert view.page == 1
    assert "article-40" in option_values(view.item_select)
    selected = [option for option in view.item_select.options if option.default]
    assert [option.value for option in selected] == ["article-40"]


async def test_change_page_selects_the_first_item_of_the_new_page() -> None:
    view = make_permanent_view()
    items = permanent_items(60)
    update_permanent(view, items)
    refreshed: list[str | None] = []

    async def fake_refresh(interaction: object) -> None:
        refreshed.append(view.selected_identifier)

    view.refresh = fake_refresh  # type: ignore[method-assign]

    await view.change_page(SimpleNamespace(), 1)  # type: ignore[arg-type]
    await view.change_page(SimpleNamespace(), 5)  # type: ignore[arg-type]

    assert refreshed == ["article-26", "article-51"]


async def test_emptied_shop_removes_page_buttons() -> None:
    view = make_permanent_view()
    update_permanent(view, permanent_items(60))
    update_permanent(view, [])

    assert view.page_indicator not in view.children
    assert view.item_select.disabled


async def test_advent_shop_is_paginated_too() -> None:
    view = AdventShopView(
        cog=SimpleNamespace(),  # type: ignore[arg-type]
        owner_id=1,
        guild_id=1,
        campaign_id=1,
    )
    view.update_components(
        items=advent_items(30),
        purchased_item_ids=set(),
        balance=1000,
        openings=24,
    )

    assert len(view.product_select.options) == 25
    assert view.page_indicator.label == "Page 1/2"
    view.to_components()
