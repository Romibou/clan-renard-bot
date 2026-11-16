from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import discord
import pytest

from bot.extensions.annonces import AnnouncementCog, allowed_mentions, links_view
from bot.features.announcements import studio as studio_module
from bot.features.announcements.model import (
    AnnouncementError,
    attachment_name,
    convert_date_tokens,
    default_draft,
    export_message,
    fields_to_text,
    from_discord_message,
    import_message,
    is_empty,
    message_content,
    normalize_draft,
    parse_color,
    parse_datetime,
    problems,
    render_embeds,
    text_to_buttons,
    text_to_fields,
    upload_ids,
)

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def filled_draft() -> dict:
    draft = default_draft("Clan Renard", "https://cdn.example/icon.png")
    draft["embeds"][0]["title"] = "Soirée jeux"
    draft["embeds"][0]["description"] = "Rendez-vous ce soir !"
    draft["channel_id"] = 10
    return draft


# ---------------------------------------------------------------
# Dates
# ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("25/12/2026 18:00", datetime(2026, 12, 25, 18, 0, tzinfo=PARIS)),
        ("25/12 18h", datetime(2026, 12, 25, 18, 0, tzinfo=PARIS)),
        ("01/12 18h30", datetime(2026, 12, 1, 18, 30, tzinfo=PARIS)),
        ("25/12/26", datetime(2026, 12, 25, 0, 0, tzinfo=PARIS)),
        ("demain 21h", datetime(2026, 11, 17, 21, 0, tzinfo=PARIS)),
        ("aujourd'hui à 20:15", datetime(2026, 11, 16, 20, 15, tzinfo=PARIS)),
        ("10/01 9h", datetime(2027, 1, 10, 9, 0, tzinfo=PARIS)),  # année suivante
    ],
)
def test_parse_datetime(text, expected) -> None:
    assert parse_datetime(text, PARIS, NOW) == expected


@pytest.mark.parametrize("text", ["32/12", "25/13", "demain 25h", "bientôt", ""])
def test_parse_datetime_rejects(text) -> None:
    assert parse_datetime(text, PARIS, NOW) is None


def test_date_tokens() -> None:
    text, errors = convert_date_tokens("Le {date:25/12 18h}, soit {dans:25/12 18h} !", PARIS, NOW)
    stamp = int(datetime(2026, 12, 25, 18, tzinfo=PARIS).timestamp())

    assert text == f"Le <t:{stamp}:F>, soit <t:{stamp}:R> !"
    assert errors == []

    _, errors = convert_date_tokens("{date:n'importe quoi}", PARIS, NOW)
    assert errors == ["{date:n'importe quoi}"]


# ---------------------------------------------------------------
# Saisies texte
# ---------------------------------------------------------------


def test_sections_round_trip() -> None:
    fields = text_to_fields("## 📅 Date\nSamedi\n21h\n## 🎁 Lot\n1 000 pièces", inline=True)

    assert fields == [
        {"name": "📅 Date", "value": "Samedi\n21h", "inline": True},
        {"name": "🎁 Lot", "value": "1 000 pièces", "inline": True},
    ]
    assert text_to_fields(fields_to_text(fields), inline=True) == fields
    assert text_to_fields("", inline=False) == []


def test_sections_need_titles() -> None:
    with pytest.raises(AnnouncementError):
        text_to_fields("texte sans titre", inline=False)


def test_buttons() -> None:
    buttons = text_to_buttons(
        "🎮 Jouer | https://example.com\nRèglement|https://discord.com/channels/1/2\n"
        "<:renard:123456789012345678> Site | https://renard.fr"
    )

    assert buttons == [
        {"label": "Jouer", "url": "https://example.com", "emoji": "🎮"},
        {"label": "Règlement", "url": "https://discord.com/channels/1/2"},
        {"label": "Site", "url": "https://renard.fr", "emoji": "<:renard:123456789012345678>"},
    ]

    with pytest.raises(AnnouncementError):
        text_to_buttons("Pas de lien")

    with pytest.raises(AnnouncementError):
        text_to_buttons("Mauvais | ftp://truc")


def test_colors() -> None:
    assert parse_color("#F28C28") == 0xF28C28
    assert parse_color("abc") == 0xAABBCC
    assert parse_color("Bleu") == 0x3498DB
    assert parse_color("") is None

    with pytest.raises(AnnouncementError):
        parse_color("arc-en-ciel")


# ---------------------------------------------------------------
# Rendu et contrôles
# ---------------------------------------------------------------


def test_default_draft_is_empty_and_not_published() -> None:
    draft = default_draft("Clan Renard", None)

    assert is_empty(draft)
    assert render_embeds(draft, now=NOW) == []
    assert problems(draft)
    # Dans l'aperçu, le cadre vide montre une consigne.
    assert render_embeds(draft, now=NOW, placeholder="vide")[0]["description"] == "vide"


def test_render_with_upload_and_mentions() -> None:
    draft = filled_draft()
    draft["embeds"][0]["image"] = {"url": "upload:7"}
    draft["mention"] = "role"
    draft["role_id"] = 42
    draft["content"] = "Venez nombreux"

    assert upload_ids(draft) == {7}
    name = attachment_name(7, "mon affiche.PNG")
    assert name == "7_mon_affiche.png"

    embed = render_embeds(draft, uploads={7: name}, now=NOW)[0]
    assert embed["image"] == {"url": f"attachment://{name}"}
    assert embed["timestamp"] == NOW.isoformat()
    discord.Embed.from_dict(embed)  # accepté par discord.py

    assert message_content(draft) == "<@&42>\nVenez nombreux"
    assert problems(draft) == []

    # Image disparue de la base : retirée plutôt que cassée.
    assert "image" not in render_embeds(draft, uploads={}, now=NOW)[0]


def test_problems_limits() -> None:
    draft = filled_draft()
    draft["embeds"][0]["title"] = "x" * 300
    draft["content"] = "y" * 2100

    found = problems(draft)
    assert any("titre trop long" in issue for issue in found)
    assert any("au-dessus du cadre" in issue for issue in found)


def test_normalize_repairs_bad_data() -> None:
    draft = normalize_draft(
        json.dumps({"embeds": [{"title": "a", "color": "12"}, "pas un cadre"], "mention": "role"})
    )

    assert draft["embeds"][0]["color"] == 12
    assert len(draft["embeds"]) == 1
    assert draft["mention"] == "none"  # rôle manquant
    assert draft["buttons"] == [] and draft["editing"] is None


# ---------------------------------------------------------------
# Discohook
# ---------------------------------------------------------------


def test_import_discohook_backup_and_export_round_trip() -> None:
    backup = {
        "messages": [
            {
                "data": {
                    "content": "Hello",
                    "embeds": [
                        {"title": "T", "description": "D", "color": 255,
                         "image": {"url": "attachment://x.png"}},
                    ],
                    "components": [
                        {"type": 1, "components": [
                            {"type": 2, "style": 5, "label": "Site", "url": "https://a.fr",
                             "emoji": {"name": "renard", "id": "123456789012345678"}},
                            {"type": 2, "style": 1, "label": "Action", "custom_id": "x"},
                        ]}
                    ],
                }
            },
            {"data": {"content": "second"}},
        ]
    }

    imported, warnings = import_message(json.dumps(backup))

    assert imported["content"] == "Hello"
    assert imported["embeds"][0]["title"] == "T"
    assert "image" not in imported["embeds"][0]
    assert imported["buttons"] == [
        {"label": "Site", "url": "https://a.fr", "emoji": "<:renard:123456789012345678>"}
    ]
    assert len(warnings) == 3

    draft = normalize_draft({**imported, "channel_id": 1})
    exported = json.loads(export_message(draft))
    again, _ = import_message(json.dumps(exported))
    assert again["embeds"][0]["description"] == "D"
    assert again["buttons"] == imported["buttons"]


@pytest.mark.parametrize("text", ["pas du json", "[]", '{"content": ""}'])
def test_import_rejects(text) -> None:
    with pytest.raises(AnnouncementError):
        import_message(text)


def test_from_discord_message_detects_mention() -> None:
    draft = from_discord_message(
        "@everyone\nCe soir !",
        [{"type": "rich", "title": "Event", "timestamp": "2026-11-16T12:00:00+00:00"}],
        [],
    )

    assert draft["mention"] == "everyone"
    assert draft["content"] == "Ce soir !"
    assert draft["embeds"][0]["timestamp"] is True


# ---------------------------------------------------------------
# Interface (construction sans Discord)
# ---------------------------------------------------------------


def test_links_view_and_mentions() -> None:
    assert links_view({"buttons": []}) is None

    view = links_view({"buttons": [{"label": f"B{i}", "url": "https://a.fr"} for i in range(7)]})
    assert len(view.children) == 7
    assert view.children[6].row == 1

    assert allowed_mentions({"mention": "everyone"}).everyone is True
    assert allowed_mentions({"mention": "role"}).everyone is False


def fake_studio_parts():
    guild = SimpleNamespace(
        id=1,
        name="Clan Renard",
        icon=None,
        get_channel=lambda _id: None,
        get_role=lambda _id: None,
    )
    origin = SimpleNamespace(user=SimpleNamespace(id=5), guild=guild)
    cog = SimpleNamespace(tz=PARIS, tz_name="Europe/Paris")
    return cog, origin


def check_modal_limits(modal: discord.ui.Modal) -> None:
    assert len(modal.title) <= 45
    assert len(modal.children) <= 5

    for item in modal.children:
        if isinstance(item, discord.ui.Label):
            assert len(item.text) <= 45, item.text
            assert item.description is None or len(item.description) <= 100, item.description
            component = item.component
            placeholder = getattr(component, "placeholder", None)
            assert placeholder is None or len(placeholder) <= 100, placeholder


async def test_studio_builds_and_modals_respect_discord_limits() -> None:
    cog, origin = fake_studio_parts()
    draft = filled_draft()
    draft["buttons"] = [{"label": "Site", "url": "https://a.fr"}] * 7
    draft["embeds"][0]["image"] = {"url": "upload:3"}

    view = studio_module.StudioView(cog, origin, draft)
    labels = [getattr(item, "label", None) for item in view.children]

    assert "Publier" in labels and "Programmer" in labels
    assert sum(1 for item in view.children if getattr(item, "url", None)) == 5
    assert len(view.children) <= 25

    for modal_class in (
        studio_module.TextModal,
        studio_module.StyleModal,
        studio_module.ImagesModal,
        studio_module.SectionsModal,
        studio_module.ButtonsModal,
        studio_module.DeliveryModal,
        studio_module.ScheduleModal,
        studio_module.ImportModal,
    ):
        check_modal_limits(modal_class(view))

    images = studio_module.ImagesModal(view)
    assert images.image_url.default == studio_module.KEEP_UPLOAD

    # Mode modification : pas de programmation, bouton d'enregistrement.
    draft["editing"] = {"channel_id": 10, "message_id": 99}
    view.build()
    labels = [getattr(item, "label", None) for item in view.children]
    assert "Enregistrer les modifications" in labels
    assert "Programmer" not in labels


async def test_reset_after_send_keeps_channel_but_not_when_editing() -> None:
    cog, origin = fake_studio_parts()
    cog.new_draft = lambda guild: default_draft(guild.name, None)

    view = studio_module.StudioView(cog, origin, filled_draft())
    view.reset_after_send()
    assert view.draft["channel_id"] == 10 and is_empty(view.draft)

    editing = filled_draft()
    editing["editing"] = {"channel_id": 10, "message_id": 99}
    view = studio_module.StudioView(cog, origin, editing)
    view.reset_after_send()
    assert view.draft["channel_id"] is None and view.draft["editing"] is None


def test_permission_problem_messages() -> None:
    cog = AnnouncementCog.__new__(AnnouncementCog)
    guild = SimpleNamespace(get_channel=lambda _id: None)

    assert "salon" in cog.permission_problem(guild, filled_draft())
