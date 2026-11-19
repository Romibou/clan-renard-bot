from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import discord
import pytest

from bot.extensions import role_perso as rp

# ---------------------------------------------------------------
# Validation
# ---------------------------------------------------------------


@pytest.mark.parametrize("emoji", ["🦊", "⭐", "❤️", "👍🏽", "👨‍👩‍👧", "🇫🇷", "1️⃣", "☀️", ""])
def test_clean_emoji_accepts_single_emojis(emoji) -> None:
    assert rp.clean_emoji(f"  {emoji} ") == emoji


@pytest.mark.parametrize("emoji", ["🦊🦊", "abc", "🦊a", "<:renard:123>", ":renard:", "🇫🇷🇧🇪"])
def test_clean_emoji_refuses_the_rest(emoji) -> None:
    with pytest.raises(ValueError):
        rp.clean_emoji(emoji)


def test_clean_name() -> None:
    assert rp.clean_name("  Le   Renard  ") == "Le Renard"

    for bad in ("a", "x" * 26, "Renard 🦊", "@everyone", "<@123>", "pub discord.gg/abc"):
        with pytest.raises(ValueError):
            rp.clean_name(bad)


def test_parse_color() -> None:
    assert rp.parse_color("#FF9AD5") == 0xFF9AD5
    assert rp.parse_color("f0a") == 0xFF00AA
    assert rp.parse_color("#000000") == 0x010101  # 0 = « pas de couleur » pour Discord

    for bad in ("rose", "#12345", "#GGGGGG", ""):
        with pytest.raises(ValueError):
            rp.parse_color(bad)

    assert rp.color_hex(0xFF9AD5) == "#FF9AD5"
    assert rp.role_label("Renard", "🦊") == "Renard 🦊" and rp.role_label("Renard", "") == "Renard"


# ---------------------------------------------------------------
# Embeds, panneaux, tableau
# ---------------------------------------------------------------

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
SETTINGS = {"enabled": True, "price": 50_000, "duration_days": 90, "review_channel_id": 5}


def record(**changes):
    data = {
        "id": 1, "guild_id": 1, "user_id": 42, "name": "Renard", "color": 0xFF9AD5, "emoji": "🦊",
        "status": "active", "role_id": 99, "price_paid": 50_000, "duration_days": 90,
        "decided_at": NOW, "expires_at": NOW + timedelta(days=90), "reminded": False,
    }
    data.update(changes)
    return data


def test_request_embed_shows_everything_for_the_staff() -> None:
    member = SimpleNamespace(mention="<@42>", name="romibuwu")
    embed = rp.request_embed(record(status="pending"), member, settings=SETTINGS)
    text = embed.description + " ".join(f"{f.name} {f.value}" for f in embed.fields)

    assert "Renard 🦊" in text and "#FF9AD5" in text and "romibuwu" in text and "50 000" in text
    assert embed.color.value == 0xFF9AD5


def test_decision_button_ids_are_persistent() -> None:
    view = rp.decision_view("achat", 12)
    ids = [item.item.custom_id for item in view.children]
    assert ids == ["rolepersodec:achat:12:a", "rolepersodec:achat:12:r"]
    assert rp.DecisionButton.__discord_ui_compiled_template__.fullmatch("rolepersodec:modif:3:r")


async def test_member_panel_states() -> None:
    interaction = SimpleNamespace(user=SimpleNamespace(id=42), guild_id=1)

    nothing = rp.MemberPanel(None, interaction, None, None, SETTINGS)
    assert "/boutique" in nothing.embed().description and not nothing.children

    pending = rp.MemberPanel(None, interaction, record(status="pending"), None, SETTINGS)
    assert "attend la validation" in pending.embed().description and not pending.children

    active = rp.MemberPanel(None, interaction, record(), None, SETTINGS)
    labels = [button.label for button in active.children]
    assert labels == ["Nom et icône", "Couleur", "Prolonger (50 000 pièces)", "Supprimer mon rôle"]
    assert "<@&99>" in active.embed().description and "Se termine" in active.embed().description

    change = {"new_name": "Loup", "new_emoji": "🐺"}
    waiting = rp.MemberPanel(None, interaction, record(), change, SETTINGS)
    assert waiting.children[0].disabled and "Loup 🐺" in waiting.embed().description


def test_active_roles_table() -> None:
    guild = SimpleNamespace(get_member=lambda user_id: SimpleNamespace(name=f"compte{user_id}"))
    rows = [record(user_id=7, name="Un nom de rôle très long"), record(user_id=8, name="Loup")]
    lines = rp.active_roles_table(rows, guild).splitlines()

    assert lines[0].split() == ["#", "Compte", "Rôle", "Fin"]
    assert "compte7" in lines[2] and "Un nom de rôle …" in lines[2] and "18/02/27" in lines[2]
    assert len({len(line.rstrip()) for line in lines[2:]}) == 1
    assert rp.active_roles_table([], guild) == "Aucun rôle perso actif."


# ---------------------------------------------------------------
# Décision du staff (base et Discord simulés)
# ---------------------------------------------------------------


class FakePool:
    def __init__(self, row) -> None:
        self.row = row
        self.executed: list = []
        self.update_result = "UPDATE 1"

    async def fetchrow(self, query, *args):
        return self.row

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return self.update_result

    def acquire(self):
        pool = self

        class Context:
            async def __aenter__(self):
                return pool

            async def __aexit__(self, *exc):
                return False

        return Context()

    def transaction(self):
        return self.acquire()


class FakeRole:
    def __init__(self, **kwargs) -> None:
        self.id = 555
        self.mention = "<@&555>"
        self.kwargs = kwargs
        self.deleted = False

    async def delete(self, reason=None):
        self.deleted = True


def make_cog(pool):
    cog = rp.CustomRoles(SimpleNamespace(get_guild=lambda _id: None))
    cog.get_pool = lambda: pool
    cog.notified = []

    async def notify(user_id, embed):
        cog.notified.append((user_id, embed))

    cog.notify = notify
    return cog


def make_guild(member):
    created = []

    async def create_role(**kwargs):
        role = FakeRole(**kwargs)
        created.append(role)
        return role

    guild = SimpleNamespace(
        id=1, name="Clan Renard", roles=[object()] * 10, created=created,
        get_member=lambda user_id: member, create_role=create_role,
    )
    return guild


async def test_accept_creates_bottom_role_not_mentionable_and_gives_it() -> None:
    added = []

    async def add_roles(role, reason=None):
        added.append(role)

    member = SimpleNamespace(id=42, mention="<@42>", add_roles=add_roles)
    pool = FakePool(record(status="pending", role_id=None))
    cog = make_cog(pool)
    guild = make_guild(member)
    interaction = SimpleNamespace(guild=guild, user=SimpleNamespace(id=7, mention="<@7>"))

    text = await cog.accept_request(interaction, 1, None)

    role = guild.created[0]
    assert "créé et donné" in text and added == [role]
    assert role.kwargs["name"] == "Renard 🦊" and role.kwargs["mentionable"] is False
    assert role.kwargs["colour"].value == 0xFF9AD5 and role.kwargs["permissions"].value == 0
    assert cog.notified and cog.notified[0][0] == 42


async def test_accept_twice_deletes_the_extra_role() -> None:
    async def add_roles(role, reason=None):
        return None

    member = SimpleNamespace(id=42, mention="<@42>", add_roles=add_roles)
    pool = FakePool(record(status="pending", role_id=None))
    pool.update_result = "UPDATE 0"  # quelqu'un a décidé juste avant
    cog = make_cog(pool)
    guild = make_guild(member)

    text = await cog.accept_request(
        SimpleNamespace(guild=guild, user=SimpleNamespace(id=7, mention="<@7>")), 1, None)
    assert "quelqu'un d'autre" in text and guild.created[0].deleted


async def test_accept_when_member_left_refunds() -> None:
    pool = FakePool(record(status="pending", role_id=None))
    cog = make_cog(pool)
    guild = make_guild(None)

    text = await cog.accept_request(SimpleNamespace(guild=guild, user=SimpleNamespace(id=7, mention="<@7>")), 1, None)

    assert "remboursée" in text and not guild.created
    refunds = [args for query, args in pool.executed if "wallet = wallet +" in query]
    assert refunds and refunds[0][2] == 50_000


async def test_refuse_refunds_and_tells_the_member() -> None:
    pool = FakePool(record(status="pending", role_id=None))
    cog = make_cog(pool)
    interaction = SimpleNamespace(guild_id=1, user=SimpleNamespace(id=7, mention="<@7>"))

    text = await cog.refuse_request(interaction, 1, "nom inapproprié", None)

    assert "remboursé" in text
    assert any("shop_refund" in query for query, _args in pool.executed)
    assert "nom inapproprié" in cog.notified[0][1].description


async def test_shop_button_only_when_enabled() -> None:
    cog = make_cog(FakePool(None))

    async def disabled(_guild_id):
        return {**SETTINGS, "enabled": False}

    async def enabled(_guild_id):
        return SETTINGS

    cog.get_settings = disabled
    assert await cog.shop_button(1) is None
    cog.get_settings = enabled
    button = await cog.shop_button(1)
    assert isinstance(button, discord.ui.Button) and button.label == "Rôle perso"


async def test_modals_build_within_discord_limits() -> None:
    interaction = SimpleNamespace(user=SimpleNamespace(id=42), guild_id=1)
    panel = rp.MemberPanel(None, interaction, record(), None, SETTINGS)
    admin = SimpleNamespace(settings=SETTINGS, guild=SimpleNamespace(get_channel=lambda _id: None))

    for modal in (
        rp.PurchaseModal(None, SETTINGS),
        rp.NameEmojiModal(panel),
        rp.ColorModal(panel),
        rp.SettingsModal(admin),
        rp.RemoveRoleModal(admin),
        rp.RefuseModal("achat", 1, None),
    ):
        assert 1 <= len(modal.children) <= 5

    assert rp.NameEmojiModal(panel).inputs["name"].default == "Renard"
    assert rp.ColorModal(panel).inputs["color"].default == "#FF9AD5"


def test_intro_shows_price_duration_and_rules() -> None:
    embed = rp.intro_embed(SETTINGS)
    text = " ".join(f"{field.name} {field.value}" for field in embed.fields)
    assert "50 000 pièces" in text and "90 jours" in text and "remboursée" in text and "#FF9AD5" in text

    view = rp.IntroView(None, 42, SETTINGS)
    assert view.children[0].label == "Configurer mon rôle perso"
