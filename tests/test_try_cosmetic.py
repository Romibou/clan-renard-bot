from __future__ import annotations

from types import SimpleNamespace

import discord

from bot.extensions import advent_shop, shop
from bot.features import cosmetics_studio as studio


def permanent_item(identifier, item_type, cosmetic_id=None):
    return {
        "id": hash(identifier) % 1000, "identifier": identifier, "display_name": identifier,
        "description": "", "item_type": item_type, "role_id": 5 if item_type == "role" else None,
        "cosmetic_id": cosmetic_id, "price": 500, "minimum_level": 0, "enabled": True,
    }


def advent_item(identifier, cosmetic_id=None):
    return {
        "id": hash(identifier) % 1000, "identifier": identifier, "display_name": identifier,
        "emoji": "🎁", "item_type": "profile_cosmetic" if cosmetic_id else "role",
        "cosmetic_id": cosmetic_id, "price": 150, "min_openings": 0,
    }


async def test_permanent_shop_try_button_only_for_cosmetics() -> None:
    view = shop.PermanentShopView(cog=SimpleNamespace(), owner_id=1, guild_id=1)
    items = [permanent_item("frame-volcan-2026", "cosmetic", 20), permanent_item("role-vip", "role")]

    view.selected_identifier = "frame-volcan-2026"
    view.update_components(items=items, purchased_item_ids=set(), wallet=0, level=1)
    assert not view.try_button.disabled and view.selected_cosmetic_id == 20
    assert view.buy_button.disabled  # pas assez de pièces… mais on peut essayer

    view.selected_identifier = "role-vip"
    view.update_components(items=items, purchased_item_ids=set(), wallet=1000, level=1)
    assert view.try_button.disabled and view.selected_cosmetic_id is None

    view.update_components(items=[], purchased_item_ids=set(), wallet=0, level=1)
    assert view.try_button.disabled


async def test_advent_shop_try_button_only_for_cosmetics() -> None:
    view = advent_shop.AdventShopView(cog=SimpleNamespace(), owner_id=1, guild_id=1, campaign_id=1)
    items = [advent_item("frame-snow-2026", 7), advent_item("noel-2026")]

    view.selected_identifier = "frame-snow-2026"
    view.update_components(items=items, purchased_item_ids=set(), balance=0, openings=0)
    assert not view.try_button.disabled and view.selected_cosmetic_id == 7

    view.selected_identifier = "noel-2026"
    view.update_components(items=items, purchased_item_ids=set(), balance=0, openings=0)
    assert view.try_button.disabled


class FakeResponse:
    def __init__(self) -> None:
        self.sent: list = []

    async def defer(self, **kwargs):
        return None

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


async def test_try_cosmetic_sends_private_preview(monkeypatch) -> None:
    record = {"id": 7, "identifier": "frame-snow-2026", "cosmetic_type": "frame", "display_name": "Cadre givre",
              "value": None, "asset_path": "frames/givre-2026.png", "enabled": True}

    async def fetchrow(query, guild_id, cosmetic_id):
        return record if cosmetic_id == 7 else None

    profile = SimpleNamespace(get_pool=lambda: SimpleNamespace(fetchrow=fetchrow))
    sent: list = []

    async def followup_send(**kwargs):
        sent.append(kwargs)

    async def fake_preview(cog, interaction, rec):
        return discord.File(__import__("io").BytesIO(b"png"), filename="apercu-cosmetique.png")

    monkeypatch.setattr(studio, "render_existing_preview", fake_preview)
    interaction = SimpleNamespace(
        guild_id=1,
        client=SimpleNamespace(get_cog=lambda name: profile),
        response=FakeResponse(),
        followup=SimpleNamespace(send=followup_send),
    )

    await studio.try_cosmetic(interaction, 7)
    assert sent[0]["ephemeral"] and "Cadre givre" in sent[0]["embed"].title
    assert "Rien n'est acheté" in sent[0]["embed"].description

    await studio.try_cosmetic(interaction, 99)
    assert "n'existe plus" in sent[1]["embed"].description

    no_profile = SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: None), response=FakeResponse())
    await studio.try_cosmetic(no_profile, 7)
    assert no_profile.response.sent and no_profile.response.sent[0]["ephemeral"]
