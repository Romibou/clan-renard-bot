from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import discord
import pytest

from bot.features.advent import announcement_texts_panel as panel_module
from bot.features.advent.announcement_texts import (
    AnnouncementTexts,
    build_announcement,
    format_days,
    parse_days,
)
from bot.features.advent.models import AdventCampaign


def campaign(**changes) -> AdventCampaign:
    values = dict(
        id=1, guild_id=10, year=2026, title="Calendrier de l'Avent",
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 24),
        timezone="Europe/Paris", opening_hour=18, catchup_mode="disabled",
        channel_id=55, announcement_role_id=77, announcements_enabled=True,
        enabled=True, day_order=tuple(range(1, 25)),
    )
    values.update(changes)
    return AdventCampaign(**values)


ROLE = SimpleNamespace(mention="<@&77>")


def test_default_texts_match_the_original_announcement() -> None:
    result = build_announcement(campaign=campaign(), day=5, texts=AnnouncementTexts(), guild_name="Clan Renard", role=ROLE)
    embed = result["embed"]

    assert embed.title == "🎄 Jour 5 — Calendrier de l'Avent"
    assert embed.description == (
        "La case **n°5** du calendrier de **Clan Renard** est maintenant disponible !\n\n"
        "Clique sur le bouton ci-dessous pour ouvrir ta case personnelle et découvrir ta récompense."
    )
    assert embed.fields[0].name == "Ouverture" and "18:00" in embed.fields[0].value
    assert result["content"] == "<@&77>"
    assert result["allowed_mentions"].roles is True and result["allowed_mentions"].everyone is False

    last = build_announcement(campaign=campaign(), day=24, texts=AnnouncementTexts(), guild_name="X", role=None)
    assert last["embed"].description.startswith("La grande case **n°24** est enfin disponible !")
    assert last["content"] is None


def test_custom_texts_variables_special_days_and_everyone() -> None:
    texts = AnnouncementTexts(
        title="🦊 Case {jour}/24",
        message="Plus que {jours_restants} jours sur {serveur} ! Ouverture à {heure}.",
        day_messages={6: "Bonne Saint-Nicolas ! 🎅 Case {jour} ouverte."},
        everyone_days={1, 24},
        show_opening=False,
    )

    day3 = build_announcement(campaign=campaign(), day=3, texts=texts, guild_name="Clan Renard", role=ROLE)
    assert day3["embed"].title == "🦊 Case 3/24"
    assert day3["embed"].description == "Plus que 21 jours sur Clan Renard ! Ouverture à 18:00."
    assert day3["embed"].fields == []  # encart « Ouverture » masqué

    day6 = build_announcement(campaign=campaign(), day=6, texts=texts, guild_name="Clan Renard", role=ROLE)
    assert day6["embed"].description == "Bonne Saint-Nicolas ! 🎅 Case 6 ouverte."

    day1 = build_announcement(campaign=campaign(), day=1, texts=texts, guild_name="Clan Renard", role=ROLE)
    assert day1["content"] == "@everyone"
    assert day1["allowed_mentions"].everyone is True and day1["allowed_mentions"].roles is False

    # Le 24 sans message spécial ni « dernier message » personnalisé : texte d'origine du 24.
    day24 = build_announcement(campaign=campaign(), day=24, texts=texts, guild_name="Clan Renard", role=ROLE)
    assert "grande case" in day24["embed"].description


def test_parse_days() -> None:
    assert parse_days("1, 24 6;6") == {1, 6, 24}
    assert parse_days("") == set()
    assert format_days({24, 1, 6}) == "1, 6, 24"

    for bad in ("0", "25", "lundi"):
        with pytest.raises(ValueError):
            parse_days(bad)


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list = []
        self.resets = 0

    async def save(self, campaign_id, texts):
        self.saved.append(texts)

    async def reset(self, campaign_id):
        self.resets += 1


def make_panel(texts: AnnouncementTexts | None = None):
    me = SimpleNamespace()
    channel = SimpleNamespace(
        mention="<#55>",
        permissions_for=lambda member: SimpleNamespace(mention_everyone=False),
    )
    guild = SimpleNamespace(
        name="Clan Renard",
        me=me,
        get_channel=lambda _id: channel,
        get_role=lambda _id: ROLE,
    )
    return panel_module.TextsPanel(
        campaign=campaign(),
        texts=texts or AnnouncementTexts(),
        repository=FakeRepository(),
        owner_id=9,
        guild=guild,
    )


def check_modal(modal: discord.ui.Modal) -> None:
    assert len(modal.title) <= 45 and len(modal.children) <= 5

    for item in modal.children:
        assert len(item.text) <= 45, item.text
        assert item.description is None or len(item.description) <= 100, item.description


async def test_panel_limits_and_modals() -> None:
    panel = make_panel(AnnouncementTexts(day_messages={6: "Saint-Nicolas"}, everyone_days={1}))

    selects = [item for item in panel.children if isinstance(item, discord.ui.Select)]
    assert len(selects) == 2 and all(len(select.options) == 24 for select in selects)
    assert selects[0].options[5].emoji is not None  # jour 6 marqué
    assert len(panel.embed("note").description) <= 4096

    check_modal(panel_module.DefaultTextsModal(panel))
    check_modal(panel_module.DayMessageModal(panel, 6))
    check_modal(panel_module.EveryoneDaysModal(panel))


async def test_modals_apply_changes() -> None:
    panel = make_panel()

    default = panel_module.DefaultTextsModal(panel)
    default.title_input._value = "🦊 Case {jour}"
    default.message._value = panel_module.DEFAULT_MESSAGE  # inchangé = reste « d'origine »
    default.last_message._value = ""
    default.opening._values = ["no"]
    default.apply()
    assert panel.texts.title == "🦊 Case {jour}" and panel.texts.message is None
    assert panel.texts.last_message is None and panel.texts.show_opening is False

    day = panel_module.DayMessageModal(panel, 6)
    day.message._value = "Saint-Nicolas !"
    day.apply()
    assert panel.texts.day_messages == {6: "Saint-Nicolas !"}

    day = panel_module.DayMessageModal(panel, 6)
    day.message._value = "  "
    day.apply()
    assert panel.texts.day_messages == {}

    everyone = panel_module.EveryoneDaysModal(panel)
    everyone.days._value = "1, 24"
    notice = everyone.apply()
    assert panel.texts.everyone_days == {1, 24}
    assert "Mentionner @everyone" in notice  # permission manquante signalée


class FakeResponse:
    def __init__(self) -> None:
        self.edits: list = []
        self.sent: list = []

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


async def test_reset_needs_two_clicks_and_preview_is_private() -> None:
    panel = make_panel(AnnouncementTexts(title="X"))

    first = SimpleNamespace(response=FakeResponse())
    await panel.on_reset(first)
    assert panel.repository.resets == 0 and panel.confirm_reset

    second = SimpleNamespace(response=FakeResponse())
    await panel.on_reset(second)
    assert panel.repository.resets == 1 and panel.texts.is_default()

    preview = SimpleNamespace(response=FakeResponse(), data={"values": ["24"]})
    await panel.on_preview(preview)
    sent = preview.response.sent[0]
    assert sent["ephemeral"] and "grande case" in sent["embed"].description
    assert sent["allowed_mentions"].roles is False
