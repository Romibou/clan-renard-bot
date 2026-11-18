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


# ---------------------------------------------------------------
# Modèles et aperçu
# ---------------------------------------------------------------


def test_design_keeps_look_not_channel() -> None:
    settings = bienvenue.merge_settings(bienvenue.JOIN, {"channel_id": 3, "enabled": True, "title": "Yo"})
    design = bienvenue.design_of(settings)

    assert design["title"] == "Yo" and "channel_id" not in design and "enabled" not in design
    assert set(design) == set(bienvenue.DESIGN_KEYS)


class FakeResponse:
    def __init__(self) -> None:
        self.edits: list = []
        self.sent: list = []

    def is_done(self) -> bool:
        return False

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)

    async def send_message(self, *args, **kwargs):
        self.sent.append(kwargs)

    async def send_modal(self, modal):
        self.sent.append(modal)


async def test_load_template_applies_design_and_refreshes() -> None:
    saved: list = []

    class Cog:
        async def get_template(self, guild_id, template_id):
            return {
                "name": "Noël",
                "settings": {"title": "Joyeux Noël", "layout": "gauche", "channel_id": 999},
                "background": b"fond",
            }

        async def save_settings(self, *args, **kwargs):
            saved.append(kwargs)

    guild = SimpleNamespace(id=1, get_channel=lambda _id: None)
    origin = SimpleNamespace(user=SimpleNamespace(id=7), guild=guild)
    panel = bienvenue.WelcomePanel(Cog(), origin, bienvenue.JOIN)
    panel.settings = bienvenue.merge_settings(bienvenue.JOIN, {"channel_id": 3, "enabled": True})
    refreshed: list = []

    async def fake_refresh(interaction, notice=None):
        refreshed.append(notice)

    panel.refresh = fake_refresh
    view = bienvenue.TemplatesView(panel, [{"id": 4, "name": "Noël", "author": "Romi"}])
    assert len(view.children) == 3

    interaction = SimpleNamespace(guild_id=1, data={"values": ["4"]}, response=FakeResponse())
    await view.load(interaction)

    assert panel.settings["title"] == "Joyeux Noël" and panel.settings["layout"] == "gauche"
    assert panel.settings["channel_id"] == 3 and panel.settings["enabled"]  # salon gardé
    assert panel.background == b"fond" and saved[0]["update_background"] is True
    assert refreshed == ["📂 Modèle chargé : Noël"]


def test_template_modal_and_empty_view() -> None:
    panel = SimpleNamespace(kind=bienvenue.LEAVE, owner_id=7, settings={}, background=None)
    view = bienvenue.TemplatesView(panel, [])
    assert len(view.children) == 1  # juste « Enregistrer »
    check_modal(bienvenue.TemplateNameModal(panel))


async def test_real_preview_is_private(monkeypatch) -> None:
    class Cog:
        async def render_for(self, member, settings, background):
            return png_bytes((10, 10))

    guild = SimpleNamespace(id=1, name="Clan Renard", member_count=10, members=[], get_channel=lambda _id: None)
    user = SimpleNamespace(id=7, mention="<@7>", display_name="Romi", name="romi", guild=guild)
    panel = bienvenue.WelcomePanel(Cog(), SimpleNamespace(user=user, guild=guild), bienvenue.JOIN)
    panel.settings = bienvenue.merge_settings(bienvenue.JOIN, None)
    sent: list = []

    async def defer(**kwargs):
        return None

    async def followup_send(**kwargs):
        sent.append(kwargs)

    interaction = SimpleNamespace(
        user=user,
        response=SimpleNamespace(defer=defer),
        followup=SimpleNamespace(send=followup_send),
    )
    await panel.on_preview(interaction)

    assert sent[0]["ephemeral"] and "Bienvenue <@7> !" in sent[0]["content"]
    assert sent[0]["file"].filename == "apercu.png"
    assert sent[0]["allowed_mentions"].users is False


def test_background_limits(monkeypatch) -> None:
    # Une grosse photo JPEG passe et ressort petite.
    output = io.BytesIO()
    Image.new("RGB", (6000, 4000), (10, 120, 200)).save(output, format="JPEG", quality=95)
    prepared = bienvenue.prepare_background(output.getvalue())
    assert Image.open(io.BytesIO(prepared)).size == (WIDTH, HEIGHT)
    assert len(prepared) < 300_000

    # Trop de pixels : refusé proprement (protège la mémoire du serveur).
    monkeypatch.setattr(bienvenue, "MAX_BACKGROUND_PIXELS", 1000)

    with pytest.raises(ValueError):
        bienvenue.prepare_background(png_bytes((100, 100)))


# ---------------------------------------------------------------
# Rôles à l'arrivée
# ---------------------------------------------------------------


class FakeRole:
    def __init__(self, role_id: int, position: int = 1, managed: bool = False, default: bool = False) -> None:
        self.id = role_id
        self.position = position
        self.managed = managed
        self._default = default
        self.mention = f"<@&{role_id}>"

    def is_default(self) -> bool:
        return self._default

    def __ge__(self, other) -> bool:
        return self.position >= other.position


def autorole_member(roles=(), pending=False, bot=False):
    added: list = []

    async def add_roles(*new_roles, reason=None):
        added.extend(role.id for role in new_roles)

    member = SimpleNamespace(id=5, bot=bot, pending=pending, roles=list(roles), add_roles=add_roles)
    member.added = added
    return member


def autorole_cog(monkeypatch, role_ids, guild_roles):
    cog = bienvenue.BienvenueCog(SimpleNamespace())

    async def get_settings(guild_id, kind):
        return bienvenue.merge_settings(kind, {"autoroles": role_ids}), None

    async def greet(member, kind):
        return None

    monkeypatch.setattr(cog, "get_settings", get_settings)
    monkeypatch.setattr(cog, "greet", greet)
    guild = SimpleNamespace(id=1, get_role=lambda role_id: guild_roles.get(role_id))
    return cog, guild


async def test_new_member_gets_roles(monkeypatch) -> None:
    membre = FakeRole(10)
    cog, guild = autorole_cog(monkeypatch, [10], {10: membre})
    member = autorole_member()
    member.guild = guild

    await cog.on_member_join(member)
    assert member.added == [10]

    # Un bot n'est pas concerné, et un rôle déjà possédé n'est pas redonné.
    bot_member = autorole_member(bot=True)
    bot_member.guild = guild
    await cog.on_member_join(bot_member)
    assert bot_member.added == []

    already = autorole_member(roles=[membre])
    already.guild = guild
    await cog.on_member_join(already)
    assert already.added == []


async def test_waits_for_rules_acceptance(monkeypatch) -> None:
    cog, guild = autorole_cog(monkeypatch, [10], {10: FakeRole(10)})
    member = autorole_member(pending=True)
    member.guild = guild

    await cog.on_member_join(member)
    assert member.added == []  # règlement pas encore accepté

    after = autorole_member(pending=False)
    after.guild = guild
    await cog.on_member_update(SimpleNamespace(pending=True), after)
    assert after.added == [10]


def test_autorole_problems() -> None:
    me = SimpleNamespace(guild_permissions=SimpleNamespace(manage_roles=True), top_role=FakeRole(1, position=5))
    roles = {10: FakeRole(10, position=2), 11: FakeRole(11, position=9), 12: FakeRole(12, managed=True)}
    guild = SimpleNamespace(me=me, get_role=lambda role_id: roles.get(role_id))

    assert bienvenue.autorole_problems(guild, [10]) == []
    problems = bienvenue.autorole_problems(guild, [11, 12, 99])
    assert len(problems) == 3 and "au-dessus" in problems[0]

    me.guild_permissions.manage_roles = False
    assert "Gérer les rôles" in bienvenue.autorole_problems(guild, [10])[0]


async def test_backfill(monkeypatch) -> None:
    monkeypatch.setattr(bienvenue.asyncio, "sleep", lambda _s: _noop())
    role = FakeRole(10)
    guild = SimpleNamespace(get_role=lambda _id: role)
    members = [autorole_member() for _ in range(3)]

    for member in members:
        member.guild = guild

    given, failed = await bienvenue.BienvenueCog(SimpleNamespace()).backfill(members, [10])
    assert (given, failed) == (3, 0) and all(m.added == [10] for m in members)


async def _noop():
    return None


async def test_panel_shows_autorole_buttons_only_for_arrivals() -> None:
    guild = SimpleNamespace(id=1, get_channel=lambda _id: None, get_role=lambda _id: None)
    interaction = SimpleNamespace(user=SimpleNamespace(id=7), guild=guild)
    panel = bienvenue.WelcomePanel(SimpleNamespace(), interaction, bienvenue.JOIN)
    panel.settings = bienvenue.merge_settings(bienvenue.JOIN, {"autoroles": [10]})
    panel.build()
    labels = [getattr(item, "label", None) for item in panel.children]
    assert "Rôles à l'arrivée" in labels and "Donner aux membres actuels" in labels
    assert "<@&10>" in panel.embed().description

    rows: dict[int, int] = {}
    for item in panel.children:
        rows[item.row] = rows.get(item.row, 0) + 1
    assert all(count <= 5 for count in rows.values())
    check_modal(bienvenue.AutoroleModal(panel))

    panel.kind = bienvenue.LEAVE
    panel.settings = bienvenue.merge_settings(bienvenue.LEAVE, None)
    panel.build()
    assert "Rôles à l'arrivée" not in [getattr(item, "label", None) for item in panel.children]
