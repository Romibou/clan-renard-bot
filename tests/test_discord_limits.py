"""Limites de Discord sur les formulaires : un dépassement fait planter l'ouverture du formulaire."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "bot"


def test_modal_labels_fit_discord_limits() -> None:
    too_long = []

    for path in ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")

        for match in re.finditer(r'Label\(\s*text="([^"{]*)"', source):
            if len(match.group(1)) > 45:  # titre d'un champ : 45 caractères maximum
                too_long.append(f"{path.name}: {match.group(1)}")

        for match in re.finditer(r'(?:super\(\).__init__\(title|Modal, title)="([^"{]*)"', source):
            if len(match.group(1)) > 45:  # titre d'un formulaire : 45 caractères maximum
                too_long.append(f"{path.name}: {match.group(1)}")

    assert not too_long, too_long


def test_first_value_handles_untouched_menus() -> None:
    from types import SimpleNamespace

    import discord

    from bot.shared.panels import first_value

    menu = discord.ui.Select(options=[
        discord.SelectOption(label="Oui", value="on", default=True),
        discord.SelectOption(label="Non", value="off"),
    ])
    assert first_value(menu, "off") == "on"  # rien touché : l'option par défaut

    empty = discord.ui.ChannelSelect()
    assert first_value(empty) is None and first_value(empty, 5) == 5

    channel = discord.ui.ChannelSelect(default_values=[discord.Object(id=42)])
    assert first_value(channel).id == 42

    picked = SimpleNamespace(values=["off"], options=[])
    assert first_value(picked, "on") == "off"
