from __future__ import annotations

from bot.shared.cosmetic_catalogue import (
    CataloguePager,
    CatalogueItem,
    build_pages,
    group_by_theme,
    item_line,
    load_items,
)


def item(id_, identifier, name, kind="background", **extra) -> CatalogueItem:
    return CatalogueItem(id=id_, identifier=identifier, name=name, cosmetic_type=kind, **extra)


def test_item_line_shows_id_name_and_sales() -> None:
    line = item_line(item(12, "background-snow-2026", "Fond d'hiver", shop_price=500, advent_price=175, owners=3))
    assert line == "`#12` 🖼️ **Fond d'hiver** · 💰 500 · 🎄 175 pts · 👥 3"
    assert "🚫 désactivé" in item_line(item(3, "badge-x", "Vieux", "badge", enabled=False))


def test_grouping_by_theme() -> None:
    themes = group_by_theme(
        [
            item(1, "badge-volcan-2026", "Badge volcan", "badge"),
            item(2, "background-volcan-2026", "Fond volcan"),
            item(3, "background-snow-2026", "Fond neige"),
            item(4, "titre-unique", "Titre seul", "title"),
            item(5, "mon-cosmetique", "Sans thème"),
        ]
    )
    labels = [theme.label for theme in themes]

    assert labels[-1] == "📦 Autres" and labels[0].startswith("❄️")
    volcan = next(theme for theme in themes if "Volcan" in theme.label)
    assert [i.name for i in volcan.items] == ["Fond volcan", "Badge volcan"]  # fond avant badge
    unique = next(theme for theme in themes if theme.key == "unique")
    assert len(unique.items) == 1  # contrairement à /collections, un thème d'un seul objet s'affiche


def test_pages_respect_discord_limits() -> None:
    items = [item(i, f"background-theme{i % 40}-2026", f"Cosmétique numéro {i} avec un long nom") for i in range(400)]
    pages = build_pages(group_by_theme(items), total=len(items))

    assert len(pages) > 1
    for page in pages:
        assert len(page) <= 6000 and len(page.fields) <= 25
        assert all(len(field.value) <= 1024 for field in page.fields)

    shown = sum(field.value.count("`#") for page in pages for field in page.fields)
    assert shown == 400

    empty = build_pages([], total=0)
    assert len(empty) == 1 and "Aucun cosmétique" in empty[0].description


async def test_pager_buttons() -> None:
    pages = build_pages(group_by_theme([item(1, "badge-a-1", "A"), item(2, "badge-a-1x", "B")]), total=2)
    pager = CataloguePager(pages * 3, owner_id=1)
    assert pager.previous.disabled and not pager.next.disabled


class FakePool:
    async def fetch(self, query, guild_id):
        if "FROM profile_cosmetics" in query:
            return [
                {"id": 12, "identifier": "background-snow-2026", "cosmetic_type": "background",
                 "display_name": "Fond d'hiver", "enabled": True},
                {"id": 13, "identifier": "frame-snow-2026", "cosmetic_type": "frame",
                 "display_name": "Cadre givré", "enabled": True},
            ]
        if "permanent_shop_items" in query:
            return [{"cosmetic_id": 12, "price": 500}]
        if "advent_shop_items_v2" in query:
            raise RuntimeError("table absente")  # ne doit pas casser le catalogue
        return [{"cosmetic_id": 13, "price": 4}]


async def test_load_items_combines_sources() -> None:
    items = {i.id: i for i in await load_items(FakePool(), 1)}

    assert items[12].shop_price == 500 and items[12].advent_price is None
    assert items[13].owners == 4 and items[13].shop_price is None
