from __future__ import annotations

import io
from types import SimpleNamespace

import discord
import pytest
from PIL import Image

from bot.extensions import bienvenue
from bot.shared.welcome_card import HEIGHT, LAYOUTS, WIDTH, parse_hex, render_welcome_card


def png_bytes(size=(300, 200), color=(200, 30, 30)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("layout", LAYOUTS)
def test_card_renders_every_layout(layout) -> None:
    data = render_welcome_card(
        avatar_bytes=png_bytes((128, 128), (20, 60, 160)),
        title="Bienvenue",
        subtitle="un pseudo vraiment très très très long pour tester",
        text="Nous sommes 1 234 à présent !",
        background_bytes=png_bytes((1920, 1080)),
        layout=layout,
    )
    image = Image.open(io.BytesIO(data))
    assert image.size == (WIDTH, HEIGHT) and image.format == "PNG"


def test_card_survives_bad_inputs() -> None:
    data = render_welcome_card(
        avatar_bytes=b"pas une image",
        title="",
        subtitle="",
        text="",
        background_bytes=b"pas une image non plus",
        layout="bizarre",
        overlay=500,
        title_color="pas une couleur",
    )
    assert Image.open(io.BytesIO(data)).size == (WIDTH, HEIGHT)


def test_overlay_darkens_background() -> None:
    def pixel(overlay: int) -> int:
        data = render_welcome_card(
            avatar_bytes=None, title="", subtitle="", text="",
            background_bytes=png_bytes((1024, 500), (200, 200, 200)), overlay=overlay,
        )
        return Image.open(io.BytesIO(data)).getpixel((5, 5))[0]

    assert pixel(0) > pixel(50) > pixel(90)


def test_colors() -> None:
    assert parse_hex("#ff9ad5", (0, 0, 0)) == (255, 154, 213)
    assert parse_hex("fff", (0, 0, 0)) == (255, 255, 255)
    assert parse_hex("rouge", (1, 2, 3)) == (1, 2, 3)
    assert bienvenue.normalize_color(" #ff9ad5 ", "Titre") == "#FF9AD5"

    with pytest.raises(ValueError):
        bienvenue.normalize_color("violet", "Titre")


def fake_member(**changes):
    guild = SimpleNamespace(name="Clan Renard", member_count=499, members=[])
    member = SimpleNamespace(
        guild=guild, mention="<@5>", display_name="Squich", name="squich._.", id=5, bot=False
    )
    for key, value in changes.items():
        setattr(member, key, value)
    return member


def test_variables() -> None:
    member = fake_member()
    text = "Bienvenue {membre} ({pseudo}) sur {serveur}, nous sommes {nombre} !"
    assert bienvenue.fill_variables(text, member) == "Bienvenue <@5> (squich._.) sur Clan Renard, nous sommes 499 !"
    assert bienvenue.fill_variables("{membre}", member, on_card=True) == "Squich"

    member.guild.member_count = 12345
    assert bienvenue.fill_variables("{nombre}", member) == "12 345"


def test_merge_settings_and_background() -> None:
    settings = bienvenue.merge_settings(bienvenue.JOIN, {"title": "Coucou", "layout": "n'importe", "overlay": 150, "inconnu": 1})
    assert settings["title"] == "Coucou" and settings["layout"] == "centre" and settings["overlay"] == 90
    assert "inconnu" not in settings
    assert bienvenue.merge_settings(bienvenue.LEAVE, None)["title"] == "Au revoir"

    prepared = bienvenue.prepare_background(png_bytes((3000, 3000)))
    assert Image.open(io.BytesIO(prepared)).size == (WIDTH, HEIGHT)


def check_modal(modal: discord.ui.Modal) -> None:
    assert len(modal.title) <= 45 and len(modal.children) <= 5

    for item in modal.children:
        assert len(item.text) <= 45, item.text
        assert item.description is None or len(item.description) <= 100, item.description


async def test_panel_and_modals_respect_limits() -> None:
    guild = SimpleNamespace(id=1, get_channel=lambda _id: None)
    interaction = SimpleNamespace(user=SimpleNamespace(id=7), guild=guild)
    panel = bienvenue.WelcomePanel(SimpleNamespace(), interaction, bienvenue.JOIN)
    panel.settings = bienvenue.merge_settings(bienvenue.JOIN, None)
    panel.build()

    rows: dict[int, int] = {}

    for item in panel.children:
        rows[item.row] = rows.get(item.row, 0) + 1

    assert all(count <= 5 for count in rows.values())
    assert "Activer" in [getattr(item, "label", None) for item in panel.children]
    assert len(panel.embed("note").description) < 4096

    for modal_class in (
        bienvenue.ChannelModal,
        bienvenue.TextsModal,
        bienvenue.StyleModal,
        bienvenue.BackgroundModal,
    ):
        check_modal(modal_class(panel))


async def test_style_modal_validation() -> None:
    panel = SimpleNamespace(settings=bienvenue.merge_settings(bienvenue.JOIN, None), guild=None)
    modal = bienvenue.StyleModal(panel)
    modal.overlay._value = "95"

    with pytest.raises(ValueError):
        await modal.apply(None)

    modal.overlay._value = "50 %"
    modal.title_color._value = "#00ff00"
    await modal.apply(None)
    assert panel.settings["overlay"] == 50 and panel.settings["title_color"] == "#00FF00"


async def test_send_greeting(monkeypatch) -> None:
    sent: list[dict] = []

    class Channel(discord.TextChannel):
        def __init__(self):
            pass

        async def send(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(jump_url="url")

    channel = Channel()
    member = fake_member()
    member.guild.get_channel = lambda _id: channel
    cog = bienvenue.BienvenueCog(SimpleNamespace())

    async def avatar(_member):
        return png_bytes((64, 64))

    monkeypatch.setattr(cog, "avatar_bytes", avatar)
    settings = bienvenue.merge_settings(bienvenue.JOIN, {"channel_id": 3, "enabled": True})

    assert await cog.send_greeting(member, bienvenue.JOIN, settings, None) is not None
    assert sent[0]["content"] == "Bienvenue <@5> !"
    assert sent[0]["file"].filename == "join.png"

    leave = bienvenue.merge_settings(bienvenue.LEAVE, {"channel_id": 3, "card": False})
    await cog.send_greeting(member, bienvenue.LEAVE, leave, None)
    assert "file" not in sent[1] and sent[1]["allowed_mentions"].users is False

    bot_member = fake_member(bot=True)
    calls: list = []

    async def fake_send(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(cog, "send_greeting", fake_send)
    await cog.greet(bot_member, bienvenue.JOIN)
    assert calls == []  # les bots ne sont pas accueillis
