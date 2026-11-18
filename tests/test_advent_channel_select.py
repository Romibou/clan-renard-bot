from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest

from bot.features.advent import admin_panel


class FakeTextChannel(discord.TextChannel):
    """Vrai type TextChannel, sans passer par Discord."""

    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


@pytest.mark.parametrize("action, command", [("channel", "set_channel"), ("publish", "publish_panel")])
async def test_channel_menu_resolves_the_real_channel(monkeypatch, action, command) -> None:
    """
    Bug : le menu renvoie un salon « partiel » (AppCommandChannel) ; le
    panneau le refusait toujours avec « Choisis un salon textuel classique ».
    """
    calls: list = []
    errors: list = []

    async def fake_invoke(interaction, cog, name, *args):
        calls.append((cog, name, args))

    async def fake_error(interaction, text):
        errors.append(text)

    monkeypatch.setattr(admin_panel, "invoke_command", fake_invoke)
    monkeypatch.setattr(admin_panel, "send_error", fake_error)

    real = FakeTextChannel(42)
    guild = SimpleNamespace(get_channel=lambda channel_id: real if channel_id == 42 else None)
    select = admin_panel.AdminChannelSelect(action=action)
    # Ce que discord.py met dans values : un objet partiel, pas un TextChannel.
    select._values = [SimpleNamespace(id=42)]
    monkeypatch.setattr(type(select), "values", property(lambda self: self._values))

    await select.callback(SimpleNamespace(guild=guild))

    assert errors == []
    assert calls and calls[0][1] == command and calls[0][2][0] is real


async def test_channel_menu_refuses_unknown_channel(monkeypatch) -> None:
    errors: list = []

    async def fake_error(interaction, text):
        errors.append(text)

    monkeypatch.setattr(admin_panel, "send_error", fake_error)
    select = admin_panel.AdminChannelSelect(action="channel")
    select._values = [SimpleNamespace(id=7)]
    monkeypatch.setattr(type(select), "values", property(lambda self: self._values))

    await select.callback(SimpleNamespace(guild=SimpleNamespace(get_channel=lambda _id: None)))
    assert errors == ["Choisis un salon textuel classique."]
