from __future__ import annotations

from bot.shared.cosmetic_catalogue import (
    TABLE_HEADER,
    CataloguePager,
    CatalogueItem,
    build_pages,
    group_by_theme,
    item_row,
    load_items,
)


def item(id_, identifier, name, kind="background", **extra) -> CatalogueItem:
    return CatalogueItem(id=id_, identifier=identifier, name=name, cosmetic_type=kind, **extra)


def test_rows_are_aligned_columns() -> None:
    rows = [
        TABLE_HEADER,
        item_row(item(3, "background-snow-2026", "Fond d'hiver 2026", advent_price=175, owners=2)),
        item_row(item(36, "title-bot", "BOT", "title", shop_price=500, owners=12)),
        item_row(item(5, "effect-snow-2026", "Flocon de neige 2026 avec un nom très long", "effect", enabled=False)),
    ]

    # Chaque colonne commence au même endroit sur toutes les lignes.
    for column in ("Type", "Nom affiché", "Identifiant"):
        start = TABLE_HEADER.index(column)
        assert all(row[start - 1] == " " for row in rows[1:])

    assert all(len(row) == len(TABLE_HEADER) for row in rows)
    assert rows[1].startswith("#3   Fond  Fond d'hiver 2026")
    assert rows[1].endswith("-   175   2") and rows[2].endswith("500     -  12")
    assert "[off] Flocon de neige…" in rows[3]  # désactivé, nom trop long coupé


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

    assert themes[-1].label == "📦 Autres" and themes[0].label.startswith("❄️")
    volcan = next(theme for theme in themes if "Volcan" in theme.label)
    assert [i.name for i in volcan.items] == ["Fond volcan", "Badge volcan"]  # fond avant badge
    assert len(next(theme for theme in themes if theme.key == "unique").items) == 1


def test_pages_fit_in_messages() -> None:
    items = [item(i, f"background-theme{i % 30}-2026", f"Cosmétique numéro {i}") for i in range(300)]
    pages = build_pages(group_by_theme(items), total=len(items))

    assert len(pages) > 1 and all(len(page) <= 2000 for page in pages)
    assert all(page.count("```") % 2 == 0 for page in pages)  # blocs de code bien fermés
    assert sum(page.count("\n#") for page in pages) == 300
    assert pages[-1].endswith(f"Page {len(pages)}/{len(pages)}")

    empty = build_pages([], total=0)
    assert len(empty) == 1 and "Aucun cosmétique" in empty[0]


async def test_pager_buttons() -> None:
    pager = CataloguePager(["a", "b", "c"], owner_id=1)
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
