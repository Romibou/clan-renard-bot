from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import discord
import pytest

from bot.extensions import anniversaire as bday
from bot.extensions.anniversaire import (
    Birthday,
    age_on,
    celebration_day,
    fill,
    next_birthday,
    validate_date,
)

TODAY = date(2026, 11, 20)


# ---------------------------------------------------------------
# Dates
# ---------------------------------------------------------------


def test_next_birthday_and_february_29() -> None:
    assert next_birthday(25, 12, TODAY) == date(2026, 12, 25)
    assert next_birthday(20, 11, TODAY) == TODAY  # c'est aujourd'hui
    assert next_birthday(1, 1, TODAY) == date(2027, 1, 1)
    # 2027 n'est pas bissextile : fêté le 28 février, 2028 l'est.
    assert celebration_day(29, 2, 2027) == date(2027, 2, 28)
    assert celebration_day(29, 2, 2028) == date(2028, 2, 29)
    assert next_birthday(29, 2, TODAY) == date(2027, 2, 28)


def test_age() -> None:
    assert age_on(2005, 25, 12, date(2026, 12, 25)) == 21
    assert age_on(2005, 25, 12, date(2026, 12, 24)) == 20
    assert age_on(2004, 29, 2, date(2027, 2, 28)) == 23  # fêté le 28
    assert age_on(None, 1, 1, TODAY) is None


@pytest.mark.parametrize(
    "day, month, year",
    [(31, 4, None), (30, 2, None), (29, 2, 2023), (1, 13, None), (0, 5, None), (1, 1, 1850), (1, 1, 2025)],
)
def test_invalid_dates(day, month, year) -> None:
    with pytest.raises(ValueError):
        validate_date(day, month, year, TODAY)


def test_valid_dates() -> None:
    validate_date(29, 2, None, TODAY)  # sans année, le 29 février est accepté
    validate_date(29, 2, 2004, TODAY)
    validate_date(31, 12, 2001, TODAY)


def member(**changes):
    guild = SimpleNamespace(name="Clan Renard", id=1)
    m = SimpleNamespace(guild=guild, mention="<@5>", display_name="Squich", id=5, bot=False)
    for key, value in changes.items():
        setattr(m, key, value)
    return m


def test_variables() -> None:
    m = member()
    assert fill("Joyeux anniversaire {membre} sur {serveur} !", m, 21) == "Joyeux anniversaire <@5> sur Clan Renard !"
    assert fill("{age} Passe une super journée !", m, 21, on_card=True) == "21 ans ! Passe une super journée !"
    assert fill("{age} Passe une super journée !", m, None, on_card=True) == "Passe une super journée !"
    assert fill("{membre}", m, None, on_card=True) == "Squich"


def test_shown_age_respects_privacy() -> None:
    birthday = Birthday(25, 12, 2005, show_age=False, updated_at=None, last_celebrated_year=0)
    assert birthday.shown_age(date(2026, 12, 25)) is None
    birthday.show_age = True
    assert birthday.shown_age(date(2026, 12, 25)) == 21


# ---------------------------------------------------------------
# Panneaux
# ---------------------------------------------------------------


def check_modal(modal: discord.ui.Modal) -> None:
    assert len(modal.title) <= 45 and len(modal.children) <= 5

    for item in modal.children:
        assert len(item.text) <= 45, item.text
        assert item.description is None or len(item.description) <= 100, item.description


async def test_member_panel_states() -> None:
    owner = member()
    panel = bday.MemberPanel(SimpleNamespace(), owner, None)
    labels = [item.label for item in panel.children]
    assert labels == ["Enregistrer", "Prochains anniversaires"]
    assert "pas encore enregistré" in panel.embed().description
    check_modal(bday.BirthdayModal(panel))

    panel.birthday = Birthday(25, 12, None, True, None, 0)
    panel.build()
    labels = [item.label for item in panel.children]
    assert labels[0] == "Modifier ma date" and "Retirer" in labels
    age_button = next(item for item in panel.children if "âge" in item.label)
    assert age_button.disabled  # pas d'année : rien à cacher
    assert "25 décembre" in panel.embed().description


class FakeCog:
    def __init__(self) -> None:
        self.saved: list = []

    async def save_birthday(self, guild_id, user_id, day, month, year, show_age):
        self.saved.append((day, month, year))
        return Birthday(day, month, year, show_age, datetime.now(timezone.utc), 0)

    async def get_birthday(self, *args, **kwargs):
        return None


class FakeResponse:
    def __init__(self) -> None:
        self.sent: list = []
        self.edits: list = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)


async def test_change_cooldown() -> None:
    cog = FakeCog()
    panel = bday.MemberPanel(cog, member(), Birthday(25, 12, None, True, datetime.now(timezone.utc), 0))
    interaction = SimpleNamespace(guild_id=1, response=FakeResponse())

    await panel.save(interaction, 26, 12, None)
    assert cog.saved == [] and "30 jours" in interaction.response.sent[0]["embed"].description

    panel.birthday.updated_at = datetime.now(timezone.utc) - timedelta(days=31)
    await panel.save(SimpleNamespace(guild_id=1, response=FakeResponse()), 26, 12, None)
    assert cog.saved == [(26, 12, None)]

    # Remettre la même date (ex. ajouter seulement l'année) n'est pas une modification.
    panel.birthday.updated_at = datetime.now(timezone.utc)
    await panel.save(SimpleNamespace(guild_id=1, response=FakeResponse()), 26, 12, None)
    assert len(cog.saved) == 2


async def test_admin_panel_and_modals() -> None:
    guild = SimpleNamespace(get_channel=lambda _id: None, get_role=lambda _id: None)
    interaction = SimpleNamespace(user=SimpleNamespace(id=1), guild=guild)
    panel = bday.AdminPanel(SimpleNamespace(), interaction, dict(bday.DEFAULT_SETTINGS), None)

    rows: dict[int, int] = {}
    for item in panel.children:
        rows[item.row] = rows.get(item.row, 0) + 1
    assert all(count <= 5 for count in rows.values())
    assert "désactivé" in panel.embed().description

    for modal_class in (bday.ChannelRoleModal, bday.TimeGiftModal, bday.TextsModal, bday.BackgroundModal):
        check_modal(modal_class(panel))

    gift = bday.TimeGiftModal(panel)
    gift.hour._value = "25"
    with pytest.raises(ValueError):
        await gift.apply(None)
    gift.hour._value = "18"
    gift.coins._value = "500"
    gift.xp._value = "1000"
    await gift.apply(None)
    assert (panel.settings["hour"], panel.settings["coins"], panel.settings["xp"]) == (18, 500, 1000)


# ---------------------------------------------------------------
# Célébration automatique
# ---------------------------------------------------------------


class FakePool:
    def __init__(self, members: list[dict]) -> None:
        self.members = members
        self.grants: list = []

    async def fetch(self, query, *args):
        if "birthday_role_grants" in query:
            return [g for g in self.grants if g["granted_on"] < args[0]]
        return [m for m in self.members if m["active"] and m["last_celebrated_year"] < args[1]]

    async def fetchrow(self, query, *args):
        return None  # réglages : on les remplace dans le test

    async def fetchval(self, query, *args):
        if "UPDATE birthday_members SET last_celebrated_year" in query:
            for m in self.members:
                if m["user_id"] == args[1] and m["last_celebrated_year"] < args[2]:
                    m["last_celebrated_year"] = args[2]
                    return m["user_id"]
        return None

    async def execute(self, query, *args):
        if "INSERT INTO birthday_role_grants" in query:
            self.grants.append({"guild_id": args[0], "user_id": args[1], "role_id": args[2], "granted_on": args[3]})
        elif "DELETE FROM birthday_role_grants" in query:
            self.grants = [g for g in self.grants if g["user_id"] != args[1]]


async def test_run_once_celebrates_once_and_removes_role_next_day(monkeypatch) -> None:
    roles_added: list = []
    roles_removed: list = []
    wishes: list = []
    gifts: list = []

    role = SimpleNamespace(id=77)

    async def add_roles(r, reason=None):
        roles_added.append(r.id)

    async def remove_roles(r, reason=None):
        roles_removed.append(r.id)

    members = {
        user_id: SimpleNamespace(id=user_id, bot=False, add_roles=add_roles, remove_roles=remove_roles, roles=[role])
        for user_id in (5, 6)
    }
    guild = SimpleNamespace(id=1, get_member=lambda _id: members.get(_id), get_role=lambda _id: role)
    pool = FakePool([
        {"guild_id": 1, "user_id": 5, "day": 20, "month": 11, "year": 2000, "show_age": True,
         "active": True, "last_celebrated_year": 0, "updated_at": None},
        {"guild_id": 1, "user_id": 6, "day": 21, "month": 11, "year": None, "show_age": True,
         "active": True, "last_celebrated_year": 0, "updated_at": None},
    ])
    bot = SimpleNamespace(
        guilds=[guild], get_guild=lambda _id: guild,
        database=SimpleNamespace(require_pool=lambda: pool),
    )
    cog = bday.BirthdayCog(bot)
    settings = {**bday.DEFAULT_SETTINGS, "enabled": True, "hour": 9, "role_id": 77, "coins": 500, "channel_id": 3}

    async def get_settings(guild_id):
        return settings, None

    async def send_wishes(m, age, s, background):
        wishes.append((m.id, age))

    async def credit(database, **kwargs):
        gifts.append(kwargs["coins"])
        return 0, 0

    async def no_roles(*args):
        return None

    monkeypatch.setattr(cog, "get_settings", get_settings)
    monkeypatch.setattr(cog, "send_wishes", send_wishes)
    monkeypatch.setattr(bday, "credit_progression", credit)
    monkeypatch.setattr(bday, "refresh_level_roles", no_roles)

    # Avant l'heure choisie : rien.
    await cog.run_once(datetime(2026, 11, 20, 8, 0, tzinfo=bday.PARIS))
    assert wishes == []

    # À l'heure : le 5 est fêté (20 novembre), pas le 6 (21 novembre).
    await cog.run_once(datetime(2026, 11, 20, 9, 5, tzinfo=bday.PARIS))
    assert wishes == [(5, 26)] and roles_added == [77] and gifts == [500]

    # Une deuxième passe le même jour ne refait rien.
    await cog.run_once(datetime(2026, 11, 20, 12, 0, tzinfo=bday.PARIS))
    assert len(wishes) == 1 and gifts == [500]

    # Le lendemain : rôle retiré au 5, et c'est au tour du 6.
    await cog.run_once(datetime(2026, 11, 21, 9, 30, tzinfo=bday.PARIS))
    assert roles_removed == [77]
    assert wishes[-1] == (6, None)


# ---------------------------------------------------------------
# Style des souhaits (cadre Renard Bot)
# ---------------------------------------------------------------


def styled_member():
    guild = SimpleNamespace(name="Clan Renard", id=1, icon=None)
    return SimpleNamespace(
        guild=guild, mention="<@5>", display_name="Fragger", id=5, bot=False,
        display_avatar=SimpleNamespace(url="https://cdn.example/avatar.png"),
    )


def test_wishes_embed_in_renard_style() -> None:
    settings = {**bday.DEFAULT_SETTINGS, "coins": 100000, "xp": 0}
    now = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
    embed = bday.build_wishes_embed(styled_member(), 18, settings, now=now)

    assert embed.title == "🎂 Joyeux anniversaire !"
    assert "joyeux anniversaire** à <@5>" in embed.description
    assert "🎈 **18 ans** aujourd'hui !" in embed.description
    assert "🎁 Cadeau du Clan : **100 000 pièces**" in embed.description
    assert embed.thumbnail.url == "https://cdn.example/avatar.png"
    assert embed.footer.text == "L'équipe Clan Renard 🦊" and embed.timestamp == now
    assert embed.colour == bday.RENARD_PINK

    no_age = bday.build_wishes_embed(styled_member(), None, {**bday.DEFAULT_SETTINGS}, now=now)
    assert "ans" not in no_age.description and "Cadeau" not in no_age.description


@pytest.mark.parametrize("style, has_embed, has_file", [("embed", True, False), ("card", False, True), ("both", True, True)])
async def test_send_wishes_styles(monkeypatch, style, has_embed, has_file) -> None:
    sent: list = []

    class Channel(discord.TextChannel):
        def __init__(self):
            pass

        async def send(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(jump_url="url")

    m = styled_member()
    m.guild.get_channel = lambda _id: Channel()
    cog = bday.BirthdayCog(SimpleNamespace())

    async def card(*args):
        return b"png"

    monkeypatch.setattr(cog, "render_card", card)
    await cog.send_wishes(m, 18, {**bday.DEFAULT_SETTINGS, "channel_id": 3, "style": style}, None)

    kwargs = sent[0]
    assert ("embed" in kwargs) is has_embed and ("file" in kwargs) is has_file
    assert kwargs["content"] == ("<@5>" if has_embed else kwargs["content"])
    if style == "both":
        assert kwargs["embed"].image.url == "attachment://anniversaire.png"
