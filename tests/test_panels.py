from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest

from bot.extensions import daily, progression, shop
from bot.features.advent import admin_panel
from bot.shared.panels import reset_selection, send_panel


class FakeResponse:
    def __init__(self, done: bool = False) -> None:
        self.done = done
        self.sent: list = []
        self.edits: list = []
        self.modals: list = []

    def is_done(self) -> bool:
        return self.done

    async def send_message(self, **kwargs):
        self.done = True
        self.sent.append(kwargs)

    async def edit_message(self, **kwargs):
        self.done = True
        self.edits.append(kwargs)

    async def send_modal(self, modal):
        self.done = True
        self.modals.append(modal)


class FakeInteraction:
    def __init__(self, user_id: int = 1) -> None:
        self.user = SimpleNamespace(id=user_id, guild_permissions=SimpleNamespace(administrator=True))
        self.response = FakeResponse()
        self.original_edits: list = []
        self.guild = None
        self.guild_id = 1

    async def edit_original_response(self, **kwargs):
        self.original_edits.append(kwargs)


# ---------------------------------------------------------------
# Outil commun
# ---------------------------------------------------------------


async def test_send_panel_remembers_how_to_reset() -> None:
    interaction = FakeInteraction()
    view = discord.ui.View()
    await send_panel(interaction, view=view, content="Panneau")

    assert interaction.response.sent[0]["ephemeral"] is True
    assert view.panel_origin is interaction

    await reset_selection(view)
    assert interaction.original_edits == [{"view": view}]


async def test_send_panel_as_followup_and_reset_errors_are_silent() -> None:
    edits: list = []

    async def message_edit(**kwargs):
        edits.append(kwargs)

    async def followup_send(**kwargs):
        return SimpleNamespace(edit=message_edit)

    interaction = FakeInteraction()
    interaction.response.done = True
    interaction.followup = SimpleNamespace(send=followup_send)
    view = discord.ui.View()
    await send_panel(interaction, view=view)
    await reset_selection(view)
    assert edits == [{"view": view}]

    async def expired(**kwargs):
        raise discord.HTTPException(SimpleNamespace(status=401, reason="x"), "token expiré")

    broken = discord.ui.View()
    broken.panel_origin = SimpleNamespace(edit_original_response=expired)
    await reset_selection(broken)  # ne lève rien
    await reset_selection(None)


# ---------------------------------------------------------------
# /avent-admin
# ---------------------------------------------------------------


async def test_advent_menu_resets_after_every_action(monkeypatch) -> None:
    calls: list = []

    async def fake_invoke(interaction, cog, name, *args):
        calls.append(name)

    monkeypatch.setattr(admin_panel, "invoke_command", fake_invoke)
    view = admin_panel.AdventAdminPanelView(owner_id=1)
    origin = FakeInteraction()
    view.panel_origin = origin
    select = view.children[0]

    for _ in range(2):  # la même action deux fois de suite
        select._values = ["configuration"]
        monkeypatch.setattr(type(select), "values", property(lambda self: self._values))
        await select.callback(FakeInteraction())

    assert calls == ["show_configuration", "show_configuration"]
    assert len(origin.original_edits) == 2  # menu remis à zéro à chaque fois


async def test_advent_pickers_open_a_new_message_instead_of_replacing_the_panel(monkeypatch) -> None:
    view = admin_panel.AdventAdminPanelView(owner_id=1)
    view.panel_origin = FakeInteraction()
    select = view.children[0]
    select._values = ["channel"]
    monkeypatch.setattr(type(select), "values", property(lambda self: self._values))
    interaction = FakeInteraction()

    await select.callback(interaction)

    assert interaction.response.edits == []  # le panneau n'est plus remplacé
    sent = interaction.response.sent[0]
    assert sent["ephemeral"] and isinstance(sent["view"], admin_panel.PickerView)
    assert sent["view"].panel_origin is interaction


@pytest.mark.parametrize("kind", ["reward_points", "reward_role"])
async def test_reward_type_menu_resets(monkeypatch, kind) -> None:
    picker_view = admin_panel.PickerView(owner_id=1, picker=admin_panel.RewardTypeSelect())
    origin = FakeInteraction()
    picker_view.panel_origin = origin
    select = picker_view.children[0]
    select._values = [kind]
    monkeypatch.setattr(type(select), "values", property(lambda self: self._values))
    interaction = FakeInteraction()

    await select.callback(interaction)

    if kind == "reward_role":
        assert interaction.response.edits == [] and interaction.response.sent  # nouveau message
    else:
        assert interaction.response.modals
    assert len(origin.original_edits) == 1


# ---------------------------------------------------------------
# Autres panneaux : les menus de choix sont remis à zéro
# ---------------------------------------------------------------


@pytest.mark.parametrize(
    "select_class",
    [
        shop.ShopRoleSelect,
        shop.ShopCosmeticSelect,
        progression.ProgressionRuleRoleSelect,
        daily.DailyResetMemberSelect,
        admin_panel.AdminChannelSelect,
        admin_panel.AdminRoleSelect,
        admin_panel.AdminUserSelect,
        admin_panel.AdminActionSelect,
    ],
)
def test_choice_menus_reset_after_use(select_class) -> None:
    import inspect

    source = inspect.getsource(select_class.callback)
    assert "reset_selection(self.view)" in source
