from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import discord

from bot.extensions import membres_role
from bot.shared.member_list import member_table


class FakeRole:
    def __init__(self, guild, role_id: int = 10, name: str = "🦊 Membre") -> None:
        self.guild = guild
        self.id = role_id
        self.name = name
        self.mention = f"<@&{role_id}>"
        self.color = discord.Color.default()

    @property
    def members(self):
        return [member for member in self.guild.members if self in member.roles]

    def is_default(self) -> bool:
        return False


def member(name: str, member_id: int, day: int, roles: list, bot: bool = False):
    return SimpleNamespace(
        name=name,
        display_name=name.upper(),
        id=member_id,
        joined_at=datetime(2026, 1, day, tzinfo=timezone.utc),
        roles=roles,
        bot=bot,
    )


def build():
    guild = SimpleNamespace(members=[])
    role = FakeRole(guild)
    guild.members = [
        member("zoe", 3, 20, [role]),
        member("adam", 1, 2, [role]),
        member("sans_role", 2, 5, []),
        member("robot", 4, 1, [role], bot=True),
    ]
    return guild, role


async def test_role_members_view_lists_humans_sorted_and_toggles() -> None:
    _guild, role = build()
    view = membres_role.RoleMembersView(7, role)

    assert [m.name for m in view.members] == ["adam", "zoe"]
    description = view.embed().description
    assert "**2** membre(s) ont <@&10>" in description and "1 bot(s)" in description
    assert "robot" not in description and "Compte" in description

    view.with_role = False
    view.set_members(view.compute())
    view.update_toggle()
    assert [m.name for m in view.members] == ["sans_role"]
    assert "n'ont **pas**" in view.embed().description and view.toggle.label == "Voir ceux qui l'ont"

    file = view.list_file()
    assert file.filename.startswith("membres_sans_") and b"SANS_ROLE" in file.fp.read()


def test_empty_table_and_safe_filename() -> None:
    assert member_table([]) == "Aucun membre."
    assert membres_role.safe_filename("🦊 Membre VIP!") == "Membre_VIP"
    assert membres_role.safe_filename("🦊") == "role"


async def test_picker_resets_menu_after_each_choice(monkeypatch) -> None:
    guild, role = build()
    guild.get_role = lambda _id: role
    resets = []

    async def fake_reset(view):
        resets.append(view)

    monkeypatch.setattr(membres_role, "reset_selection", fake_reset)
    picker = membres_role.RolePickerView(7)
    picker.select._values = [SimpleNamespace(id=10)]  # type: ignore[attr-defined]
    sent = []

    async def send_message(**kwargs):
        sent.append(kwargs)

    interaction = SimpleNamespace(guild=guild, response=SimpleNamespace(send_message=send_message))

    for _ in range(2):
        await picker.on_select(interaction)

    assert len(sent) == 2 and len(resets) == 2
    assert isinstance(sent[0]["view"], membres_role.RoleMembersView) and sent[0]["ephemeral"]
