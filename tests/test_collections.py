from __future__ import annotations

from types import SimpleNamespace

from bot.extensions.collection import (
    build_collections,
    build_collections_embed,
    collection_key,
    collection_label,
    server_emoji,
)


def cosmetic(cosmetic_id: int, identifier: str, cosmetic_type: str, name: str) -> dict[str, object]:
    return {
        "id": cosmetic_id,
        "identifier": identifier,
        "cosmetic_type": cosmetic_type,
        "display_name": name,
    }


CATALOG = [
    cosmetic(1, "background-volcan-2026", "background", "Fond volcan"),
    cosmetic(2, "frame-volcan-2026", "frame", "Cadre volcan"),
    cosmetic(3, "badge-volcan-2026", "badge", "Badge volcan"),
    cosmetic(4, "background-snow-2026", "background", "Fond d'hiver"),
    cosmetic(5, "effect-snow-2026", "effect", "Flocons"),
    cosmetic(6, "title-bot", "title", "BOT"),
    cosmetic(7, "renard-special", "badge", "Hors convention"),
]


def test_collection_key_follows_the_naming_convention() -> None:
    assert collection_key("badge-volcan-2026") == "volcan-2026"
    assert collection_key("Background-Snow-2026") == "snow-2026"
    assert collection_key("title-bot") == "bot"
    assert collection_key("renard-special") is None
    assert collection_key("badge") is None


def test_collection_label() -> None:
    assert collection_label("volcan-2026") == "🌋 Volcan 2026"
    assert collection_label("snow-2026") == "❄️ Hiver 2026"
    assert collection_label("pirate-2027") == "Pirate 2027"
    assert collection_label("ocean") == "🌊 Océan"


def test_collections_group_count_and_sort() -> None:
    collections = build_collections(CATALOG, owned_ids={4, 5, 1})

    assert [collection.key for collection in collections] == ["snow-2026", "volcan-2026"]
    snow, volcan = collections
    assert snow.complete and snow.owned == 2
    assert not volcan.complete and volcan.owned == 1
    assert [item.cosmetic_type for item in volcan.items] == ["background", "frame", "badge"]


def test_embed_shows_progress_and_custom_emojis() -> None:
    embed = build_collections_embed(
        build_collections(CATALOG, owned_ids={4, 5, 1}),
        member_name="Renard",
        yes="<:clanrenard_yes:1>",
        no="<:clanrenard_no:2>",
    )

    assert "**1/2**" in embed.description
    assert embed.fields[0].name == "❄️ Hiver 2026 — 2/2 <:clanrenard_yes:1>"
    assert embed.fields[1].name == "🌋 Volcan 2026 — 1/3 <:clanrenard_no:2>"
    assert "<:clanrenard_yes:1> Fond volcan" in embed.fields[1].value
    assert "<:clanrenard_no:2> Cadre volcan" in embed.fields[1].value


def test_server_emoji_falls_back_to_standard_emojis() -> None:
    guild = SimpleNamespace(emojis=[])

    assert server_emoji(guild, "clanrenard_yes", "✅") == "✅"  # type: ignore[arg-type]
    assert server_emoji(None, "clanrenard_yes", "✅") == "✅"


def test_empty_catalog() -> None:
    embed = build_collections_embed([], member_name="Renard")

    assert "Aucune collection" in embed.description
