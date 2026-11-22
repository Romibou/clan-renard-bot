from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import discord
import pytest

from bot.extensions import tickets as tk

NOW = datetime(2026, 11, 22, 18, 5, tzinfo=timezone.utc)


def test_channel_name_and_slug() -> None:
    assert tk.channel_name(7, "Romibou") == "ticket-0007-romibou"
    assert tk.channel_name(123, "Élodie_42!") == "ticket-0123-elodie-42"
    assert tk.channel_name(1, "🦊🦊") == "ticket-0001-membre"


def test_parse_emoji() -> None:
    assert tk.parse_emoji("") == "" and tk.parse_emoji(" ❓ ") == "❓"
    assert tk.parse_emoji("<:renard:123456789012345678>") == "<:renard:123456789012345678>"

    for bad in ("abc", "❓ question", ":renard:"):
        with pytest.raises(ValueError):
            tk.parse_emoji(bad)


def fake_role(role_id: int, default: bool = False):
    return SimpleNamespace(id=role_id, mention=f"<@&{role_id}>", is_default=lambda: default)


def test_roles_text_skips_everyone_and_truncates() -> None:
    member = SimpleNamespace(roles=[fake_role(1, default=True)] + [fake_role(100 + i) for i in range(60)])
    text = tk.roles_text(member, limit=100)
    assert "<@&1>" not in text and text.startswith("<@&159>") and "(+" in text
    assert tk.roles_text(SimpleNamespace(roles=[fake_role(1, default=True)])) == "*aucun*"


def test_staff_detection() -> None:
    admin = SimpleNamespace(guild_permissions=discord.Permissions(manage_guild=True), roles=[])
    helper = SimpleNamespace(guild_permissions=discord.Permissions.none(), roles=[fake_role(5)])
    member = SimpleNamespace(guild_permissions=discord.Permissions.none(), roles=[fake_role(9)])
    assert tk.is_staff(admin, []) and tk.is_staff(helper, [5]) and not tk.is_staff(member, [5])


def test_duration_and_transcript() -> None:
    assert tk.duration_text(NOW, NOW + timedelta(seconds=20)) == "1 min"
    assert tk.duration_text(NOW, NOW + timedelta(hours=2, minutes=5)) == "2 h 5 min"
    assert tk.duration_text(NOW, NOW + timedelta(days=3, hours=1)) == "3 j 1 h"

    ticket = {"number": 7, "opened_at": NOW, "reason": "Question sur Halloween"}
    attachment = SimpleNamespace(filename="capture.png", url="https://cdn/capture.png")
    messages = [
        SimpleNamespace(author=SimpleNamespace(name="romibou"), content="Bonjour !", created_at=NOW,
                        embeds=[], attachments=[attachment]),
        SimpleNamespace(author=SimpleNamespace(name="Renard Bot"), content="", created_at=NOW,
                        embeds=[discord.Embed(title="📬 Ticket n°0007")], attachments=[]),
    ]
    text = tk.transcript_text(ticket, "Question", "romibou (42)", "modo", messages, NOW + timedelta(hours=1))

    assert "Ticket n°0007 — Question" in text and "Raison : Question sur Halloween" in text
    assert "[22/11/2026 18:05] romibou : Bonjour !" in text and "📎 capture.png" in text
    assert "[embed] 📬 Ticket n°0007" in text and "Messages : 2" in text


def test_ticket_embeds_show_member_details() -> None:
    member = SimpleNamespace(
        mention="<@42>", name="romibou", id=42, created_at=NOW - timedelta(days=2000), joined_at=NOW,
        roles=[fake_role(1, default=True), fake_role(5)], display_avatar=SimpleNamespace(url="https://a/b.png"),
    )
    ticket = {"number": 12, "opened_at": NOW, "reason": "Évènement d'Halloween"}
    ticket_type = {"label": "Contacter l'animation", "emoji": "🎉"}
    main, reason = tk.ticket_embeds(ticket, ticket_type, member)
    text = " ".join(f"{field.name} {field.value}" for field in main.fields)

    assert main.title == "📬 Ticket n°0012" and "`romibou`" in text and "`42`" in text
    assert "Compte créé" in text and "Arrivé" in text and "<@&5>" in text and "Contacter l'animation" in text
    assert reason.description == "Évènement d'Halloween" and main.thumbnail.url == "https://a/b.png"


def test_persistent_buttons_and_panel() -> None:
    view = tk.ticket_view(3)
    ids = [item.item.custom_id for item in view.children]
    assert ids == ["ticket:claim:3", "ticket:staff:3", "ticket:close:3"]
    assert tk.TicketActionButton.__discord_ui_compiled_template__.fullmatch("ticket:close:99")

    settings = {"panel_title": "", "panel_text": "", "button_label": ""}
    embed = tk.panel_embed(settings, SimpleNamespace(icon=None))
    assert embed.title == tk.DEFAULT_TITLE and "privé" in embed.description
    assert tk.panel_view(settings).children[0].item.custom_id == "ticket:open"


def test_type_picker_and_modals_build() -> None:
    types = [
        {"id": 1, "label": "J'ai une question", "emoji": "❓", "description": "Une question.", "staff_role_ids": []},
        {"id": 2, "label": "Autre", "emoji": "", "description": "", "staff_role_ids": [5]},
    ]
    picker = tk.TypePickerView(None, types)
    options = picker.select.options
    assert [o.label for o in options] == ["J'ai une question", "Autre"] and options[1].description is None

    assert len(tk.ReasonModal(None, types[0]).children) == 1
    guild = SimpleNamespace(get_role=lambda _id: None, get_channel=lambda _id: None)
    settings = {"panel_channel_id": None, "category_id": None, "log_channel_id": None, "max_open": 1,
                "panel_title": "", "panel_text": "", "button_label": "", "panel_message_id": None}
    panel = SimpleNamespace(guild=guild, settings=settings)
    assert len(tk.SettingsModal(panel).children) == 4
    assert len(tk.TextModal(panel).children) == 3
    assert len(tk.TypeModal(panel).children) == 4
    assert len(tk.TypeModal(panel, types[1]).children) == 5
    assert len(tk.MembersModal(None, 1).children) == 2


def test_admin_embed_lists_types_and_missing_settings() -> None:
    settings = {"panel_channel_id": 1, "panel_message_id": None, "category_id": None, "log_channel_id": 3,
                "max_open": 1}
    types = [{"label": "Animation", "emoji": "🎉", "staff_role_ids": [5, 6]}]
    text = tk.admin_embed(settings, types, None, "ok", 2).description
    assert "<#1>" in text and "*à choisir*" in text and "pas encore publié" in text
    assert "🎉 **Animation** → <@&5>, <@&6>" in text and "**2**" in text


class Obj:
    """Comme SimpleNamespace, mais utilisable comme clé de dictionnaire (permissions des salons)."""

    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class FakePool:
    def __init__(self) -> None:
        self.executed: list = []

    async def fetchval(self, query, *args):
        if "COUNT(*)" in query:
            return 0
        if "counter + 1" in query:
            return 8
        return None

    async def fetchrow(self, query, *args):
        if "INSERT INTO tickets" in query:
            return {"id": 55, "number": args[1], "user_id": args[2], "opened_at": NOW, "reason": args[4]}
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "UPDATE 1"


async def test_open_ticket_creates_private_channel_for_member_and_staff() -> None:
    pool = FakePool()
    cog = tk.Tickets(SimpleNamespace())
    cog.get_pool = lambda: pool
    staff_role = Obj(id=5, mention="<@&5>")
    sent = []
    created = {}

    class Channel:
        id = 900
        mention = "<#900>"

        async def send(self, **kwargs):
            sent.append(kwargs)

    async def create_text_channel(name, **kwargs):
        created.update(name=name, **kwargs)
        return Channel()

    category = SimpleNamespace(channels=[])
    everyone, me = object(), object()
    guild = SimpleNamespace(
        id=1, default_role=everyone, me=me, get_role=lambda role_id: staff_role if role_id == 5 else None,
        get_channel=lambda _id: category, create_text_channel=create_text_channel,
    )
    member = Obj(id=42, name="Romibou", mention="<@42>", created_at=NOW, joined_at=NOW, roles=[], display_avatar=None)

    async def get_settings(_guild_id):
        return {"max_open": 1, "category_id": 3, "log_channel_id": None}

    async def get_type(_type_id):
        return {"id": 2, "guild_id": 1, "deleted": False, "label": "Animation", "emoji": "🎉",
                "staff_role_ids": [5]}

    cog.get_settings = get_settings
    cog.get_type = get_type
    cog.setup_problem = lambda guild, settings: None

    text = await cog.open_ticket(SimpleNamespace(guild=guild, user=member), 2, "Évènement d'Halloween")

    assert "<#900>" in text and created["name"] == "ticket-0008-romibou" and created["category"] is category
    overwrites = created["overwrites"]
    assert overwrites[everyone].view_channel is False
    assert overwrites[member].view_channel and overwrites[member].send_messages
    assert overwrites[staff_role].view_channel and overwrites[me].manage_channels
    assert sent and "<@42>" in sent[0]["content"] and "<@&5>" in sent[0]["content"]
    assert len(sent[0]["embeds"]) == 2 and any("channel_id" in q for q, _ in pool.executed)
