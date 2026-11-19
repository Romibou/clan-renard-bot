from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bot.extensions import shop


def row(day: int, amount: int, name: str, kind: str = "shop_purchase") -> dict:
    prefix = "Achat boutique : " if kind == "shop_purchase" else "Remboursement boutique : "
    return {
        "amount": amount,
        "transaction_type": kind,
        "reason": prefix + name,
        "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(days=day),
    }


def test_history_table_is_aligned_and_compact() -> None:
    rows = [
        row(5, -1500, "Rôle VIP"),
        row(4, 1500, "Rôle VIP", "shop_refund"),
        row(3, -500, "Cadre renard rose avec un nom vraiment long"),
    ]
    table = shop.history_table(rows)
    lines = table.splitlines()

    assert lines[0].startswith("Date") and "Pièces" in lines[0]
    assert "06/11/2026" in lines[2] and "−1 500" in lines[2]
    assert "+1 500 ↩" in lines[3] and lines[3].index("+1 500") + 6 == lines[2].index("−1 500") + 6
    assert "Cadre renard rose ave…" in lines[4]
    assert len({len(line) for line in lines}) == 1  # toutes les lignes ont la même largeur
    assert max(len(line) for line in lines) <= 50


async def test_history_view_summary_and_pages() -> None:
    rows = [row(i % 28, -100, f"Article {i}") for i in range(30)]
    view = shop.ShopHistoryView(1, rows)

    assert view.pages == 3 and view.previous_page.disabled
    description = view.embed().description
    assert "**30** achat(s)" in description and "3 000 pièces" in description

    empty = shop.ShopHistoryView(1, [])
    assert "rien acheté" in empty.embed().description and not empty.children
