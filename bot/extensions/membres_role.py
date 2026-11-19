"""
/membres-role : choisir un rôle dans un menu et voir la liste de ses
membres (même tableau que « Donner aux membres actuels »).

Chaque choix répond dans un nouveau message, puis le menu se remet à zéro
pour pouvoir rechoisir le même rôle (liste à jour) sans retaper la commande.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.shared.member_list import MemberPagesView, member_list_file
from bot.shared.panels import remember_origin, reset_selection

LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(242, 140, 40)


def safe_filename(text: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in text).strip("_")
    return (cleaned or "role")[:40]


class RoleMembersView(MemberPagesView):
    """Liste des membres qui ont (ou n'ont pas) un rôle, avec un bouton pour inverser."""

    def __init__(self, owner_id: int, role: discord.Role) -> None:
        self.role = role
        self.with_role = True
        super().__init__(owner_id, self.compute())
        self.update_toggle()
        # « Liste complète » après le bouton 🔄.
        self.remove_item(self.full_list)
        self.add_item(self.full_list)

    def compute(self) -> list[Any]:
        humans = [member for member in self.role.guild.members if not member.bot]

        if self.with_role:
            return [member for member in humans if self.role in member.roles]

        return [member for member in humans if self.role not in member.roles]

    def bots_with_role(self) -> int:
        return sum(1 for member in self.role.members if member.bot)

    def update_toggle(self) -> None:
        self.toggle.label = "Voir ceux qui ne l'ont pas" if self.with_role else "Voir ceux qui l'ont"
        self.toggle.emoji = "🔄"

    def embed(self) -> discord.Embed:
        count = len(self.members)

        if self.with_role:
            intro = f"**{count}** membre(s) ont {self.role.mention}."
            bots = self.bots_with_role()

            if bots:
                intro += f" *(+ {bots} bot(s), non affichés)*"
        else:
            intro = f"**{count}** membre(s) n'ont **pas** {self.role.mention}."

        embed = discord.Embed(
            title="🎭 Membres du rôle" if self.with_role else "🎭 Membres sans le rôle",
            description=f"{intro}\n{self.table()}",
            color=self.role.color if self.role.color.value else COLOR,
        )
        embed.set_footer(text=self.footer())
        return embed

    def list_file(self) -> discord.File:
        verb = "avec" if self.with_role else "sans"
        header = f"Membres {verb} @{self.role.name} : {len(self.members)}"
        return member_list_file(self.members, header, f"membres_{verb}_{safe_filename(self.role.name)}.txt")

    @discord.ui.button(label="Voir ceux qui ne l'ont pas", emoji="🔄", style=discord.ButtonStyle.primary, row=0)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.with_role = not self.with_role
        self.set_members(self.compute())
        self.update_toggle()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class RolePickerView(discord.ui.View):
    """Menu du panneau : chaque choix envoie une liste, puis le menu se vide."""

    def __init__(self, owner_id: int) -> None:
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.select = discord.ui.RoleSelect(placeholder="Choisis un rôle…", min_values=1, max_values=1)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def on_select(self, interaction: discord.Interaction) -> None:
        try:
            # Le menu renvoie parfois un rôle « partiel » : on prend le vrai.
            picked = self.select.values[0]
            role = interaction.guild.get_role(picked.id) if interaction.guild else None

            if role is None:
                await interaction.response.send_message("Rôle introuvable.", ephemeral=True)
                return

            if role.is_default():
                await interaction.response.send_message(
                    "`@everyone` contient tout le monde : choisis un autre rôle.", ephemeral=True
                )
                return

            view = RoleMembersView(self.owner_id, role)
            await interaction.response.send_message(
                embed=view.embed(), view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
        finally:
            await reset_selection(self)


class RoleMembersCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="membres-role",
        description="Choisis un rôle et vois la liste de ses membres (nom du compte, ID, arrivée).",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    async def membres_role(self, interaction: discord.Interaction) -> None:
        view = RolePickerView(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎭 Membres par rôle",
                description=(
                    "Choisis un rôle dans le menu : je t'envoie la liste de ses membres.\n"
                    "Le menu se remet à zéro après chaque choix, tu peux rechoisir le même rôle "
                    "pour avoir la liste à jour."
                ),
                color=COLOR,
            ),
            view=view,
            ephemeral=True,
        )
        remember_origin(view, interaction)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleMembersCog(bot))
    LOGGER.info("Commande /membres-role chargée")
