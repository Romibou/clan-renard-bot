"""
Contestations : le membre sanctionné clique sur « Contester » dans son
message privé, explique sa version, et l'équipe de modération accepte
(la sanction est annulée) ou refuse depuis le salon des contestations.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import discord

from bot.features.moderation.core import label

LOGGER = logging.getLogger(__name__)

PENDING = "pending"
ACCEPTED = "accepted"
REFUSED = "refused"


def moderation_cog(interaction: discord.Interaction) -> Any | None:
    return interaction.client.get_cog("ModerationCog")


class AppealModal(discord.ui.Modal, title="Contester une sanction"):
    explanation = discord.ui.TextInput(
        label="Explique pourquoi tu contestes",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=1000,
        placeholder="Reste poli et précis : ce qui s'est passé, pourquoi c'est une erreur…",
    )

    def __init__(self, case_id: int) -> None:
        super().__init__(timeout=900)
        self.case_id = case_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = moderation_cog(interaction)

        if cog is None:
            await interaction.response.send_message(
                "❌ La modération est indisponible, réessaie plus tard.",
                ephemeral=True,
            )
            return

        await cog.submit_appeal(
            interaction,
            self.case_id,
            str(self.explanation.value),
        )


class AppealButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"modappeal:(?P<case>[0-9]+)",
):
    def __init__(self, case_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Contester",
                emoji="📨",
                style=discord.ButtonStyle.secondary,
                custom_id=f"modappeal:{case_id}",
                disabled=disabled,
            )
        )
        self.case_id = case_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> AppealButton:
        return cls(int(match["case"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = moderation_cog(interaction)

        if cog is None:
            await interaction.response.send_message(
                "❌ La modération est indisponible, réessaie plus tard.",
                ephemeral=True,
            )
            return

        problem = await cog.appeal_problem(self.case_id, interaction.user.id)

        if problem is not None:
            await interaction.response.send_message(problem, ephemeral=True)
            return

        await interaction.response.send_modal(AppealModal(self.case_id))


class AppealDecisionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"modappealdecision:(?P<case>[0-9]+):(?P<choice>[ar])",
):
    def __init__(
        self,
        case_id: int,
        accept: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Accepter et annuler la sanction" if accept else "Refuser",
                emoji="✅" if accept else "❌",
                style=(
                    discord.ButtonStyle.success
                    if accept
                    else discord.ButtonStyle.danger
                ),
                custom_id=f"modappealdecision:{case_id}:{'a' if accept else 'r'}",
                disabled=disabled,
            )
        )
        self.case_id = case_id
        self.accept = accept

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> AppealDecisionButton:
        return cls(int(match["case"]), match["choice"] == "a")

    async def callback(self, interaction: discord.Interaction) -> None:
        permissions = getattr(interaction.user, "guild_permissions", None)

        if permissions is None or not permissions.moderate_members:
            await interaction.response.send_message(
                "❌ Seule l'équipe de modération peut traiter les contestations.",
                ephemeral=True,
            )
            return

        cog = moderation_cog(interaction)

        if cog is None:
            await interaction.response.send_message(
                "❌ La modération est indisponible, réessaie plus tard.",
                ephemeral=True,
            )
            return

        await cog.decide_appeal(interaction, self.case_id, self.accept)


def appeal_view(case_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(AppealButton(case_id))
    return view


def decision_view(case_id: int, *, disabled: bool = False) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(AppealDecisionButton(case_id, True, disabled=disabled))
    view.add_item(AppealDecisionButton(case_id, False, disabled=disabled))
    return view


def appeal_embed(case: dict[str, Any], text: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"📨 Contestation du cas n°{case['id']}",
        description=text[:4000],
        color=discord.Color.from_rgb(102, 179, 255),
    )
    embed.add_field(name="Membre", value=f"<@{case['user_id']}>", inline=True)
    embed.add_field(name="Sanction", value=label(str(case["action"])), inline=True)
    embed.add_field(
        name="Par",
        value=(
            f"<@{case['moderator_id']}>"
            if case.get("moderator_id")
            else "🤖 Modération automatique"
        ),
        inline=True,
    )
    embed.add_field(
        name="Raison de la sanction",
        value=str(case.get("reason") or "Aucune raison indiquée.")[:1024],
        inline=False,
    )

    return embed
