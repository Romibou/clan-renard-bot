from __future__ import annotations

import asyncio
import io
import logging
import random
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.shared.progression_card import render_progression_card


LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WARNING_COLOR = discord.Color.from_rgb(235, 174, 65)

VOICE_REWARD_INTERVAL_SECONDS = 60


def base_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=COLOR,
    )


def success_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=SUCCESS_COLOR,
    )


def error_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=ERROR_COLOR,
    )


def warning_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=WARNING_COLOR,
    )


def format_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def xp_for_level(level: int) -> int:
    """
    Quantité totale d'XP nécessaire pour atteindre un niveau,
    avec la courbe utilisée pour la progression.
    """
    level = max(0, int(level))

    if level == 0:
        return 0

    return (
        5 * (level - 1) * level * (2 * level - 1) // 6
        + 25 * level * (level - 1)
        + 100 * level
    )


def level_from_xp(total_xp: int) -> int:
    """
    Retrouve le niveau correspondant à une quantité totale d'XP.
    """
    total_xp = max(0, int(total_xp))

    low = 0
    high = 1

    while xp_for_level(high) <= total_xp:
        high *= 2

    while low + 1 < high:
        middle = (low + high) // 2

        if xp_for_level(middle) <= total_xp:
            low = middle
        else:
            high = middle

    return low


def xp_needed_for_next_level(level: int) -> int:
    return xp_for_level(level + 1) - xp_for_level(level)


class ProgressionView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        owner_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(timeout=300)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Panneau personnel",
                (
                    "Ce panneau appartient à un autre membre.\n"
                    "Utilise `/progression` pour ouvrir le tien."
                ),
            ),
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="Classement XP",
        emoji="🏆",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def xp_leaderboard(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    "Cette action doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        embed = await self.cog.build_leaderboard_embed(
            guild=guild,
            ranking_type="xp",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Classement argent",
        emoji="💰",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def money_leaderboard(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    "Cette action doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        embed = await self.cog.build_leaderboard_embed(
            guild=guild,
            ranking_type="money",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


class AdminMemberSelect(discord.ui.UserSelect):
    def __init__(
        self,
        panel: ProgressionAdminView,
    ) -> None:
        self.panel = panel

        super().__init__(
            placeholder="Sélectionne un membre à gérer…",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.values:
            return

        selected = self.values[0]
        self.panel.selected_user_id = selected.id

        await interaction.response.send_message(
            embed=success_embed(
                "Membre sélectionné",
                (
                    f"{selected.mention} est maintenant sélectionné.\n"
                    "Tu peux utiliser **Modifier** ou **Réinitialiser**."
                ),
            ),
            ephemeral=True,
        )


class ProgressionConfigModal(
    discord.ui.Modal,
    title="Configuration de la progression",
):
    cooldown = discord.ui.TextInput(
        label="Délai entre deux gains, en secondes",
        placeholder="60",
        min_length=1,
        max_length=4,
    )

    xp_min = discord.ui.TextInput(
        label="XP minimum par message",
        placeholder="15",
        min_length=1,
        max_length=6,
    )

    xp_max = discord.ui.TextInput(
        label="XP maximum par message",
        placeholder="25",
        min_length=1,
        max_length=6,
    )

    coins_min = discord.ui.TextInput(
        label="Pièces minimum par message",
        placeholder="2",
        min_length=1,
        max_length=6,
    )

    coins_max = discord.ui.TextInput(
        label="Pièces maximum par message",
        placeholder="4",
        min_length=1,
        max_length=6,
    )

    def __init__(
        self,
        *,
        cog: ProgressionCog,
        guild_id: int,
        settings: dict[str, Any],
    ) -> None:
        super().__init__(timeout=300)

        self.cog = cog
        self.guild_id = guild_id

        self.cooldown.default = str(settings["cooldown_seconds"])
        self.xp_min.default = str(settings["xp_min"])
        self.xp_max.default = str(settings["xp_max"])
        self.coins_min.default = str(settings["coins_min"])
        self.coins_max.default = str(settings["coins_max"])

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            cooldown = int(self.cooldown.value)
            xp_min = int(self.xp_min.value)
            xp_max = int(self.xp_max.value)
            coins_min = int(self.coins_min.value)
            coins_max = int(self.coins_max.value)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    "Tous les champs doivent contenir des nombres entiers.",
                ),
                ephemeral=True,
            )
            return

        if not 5 <= cooldown <= 3600:
            await interaction.response.send_message(
                embed=error_embed(
                    "Délai invalide",
                    "Le délai doit être compris entre 5 et 3 600 secondes.",
                ),
                ephemeral=True,
            )
            return

        if not 0 <= xp_min <= xp_max <= 1_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "XP invalide",
                    (
                        "Les valeurs d'XP doivent être positives et le "
                        "minimum ne doit pas dépasser le maximum."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not 0 <= coins_min <= coins_max <= 1_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Argent invalide",
                    (
                        "Les valeurs d'argent doivent être positives et le "
                        "minimum ne doit pas dépasser le maximum."
                    ),
                ),
                ephemeral=True,
            )
            return

        await self.cog.update_settings(
            guild_id=self.guild_id,
            cooldown_seconds=cooldown,
            xp_min=xp_min,
            xp_max=xp_max,
            coins_min=coins_min,
            coins_max=coins_max,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Configuration enregistrée",
                (
                    f"Cooldown : **{cooldown} secondes**\n"
                    f"XP : **{xp_min} à {xp_max}**\n"
                    f"Argent : **{coins_min} à {coins_max} pièces**\n"
                    "L'XP vocal se configure avec le bouton **XP vocal**."
                ),
            ),
            ephemeral=True,
        )


class AdjustMemberModal(
    discord.ui.Modal,
    title="Modifier un membre",
):
    xp_delta = discord.ui.TextInput(
        label="XP à ajouter ou retirer",
        placeholder="Exemples : 500 ou -200",
        default="0",
        min_length=1,
        max_length=12,
    )

    coins_delta = discord.ui.TextInput(
        label="Pièces à ajouter ou retirer",
        placeholder="Exemples : 100 ou -50",
        default="0",
        min_length=1,
        max_length=12,
    )

    reason = discord.ui.TextInput(
        label="Raison",
        placeholder="Correction administrative",
        default="Correction administrative",
        max_length=200,
        required=False,
    )

    def __init__(
        self,
        *,
        cog: ProgressionCog,
        guild_id: int,
        user_id: int,
    ) -> None:
        super().__init__(timeout=300)

        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            xp_delta = int(self.xp_delta.value)
            coins_delta = int(self.coins_delta.value)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    "Utilise uniquement des nombres entiers.",
                ),
                ephemeral=True,
            )
            return

        if abs(xp_delta) > 100_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur trop grande",
                    "La modification d'XP est trop importante.",
                ),
                ephemeral=True,
            )
            return

        if abs(coins_delta) > 100_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur trop grande",
                    "La modification d'argent est trop importante.",
                ),
                ephemeral=True,
            )
            return

        stats = await self.cog.adjust_member(
            guild_id=self.guild_id,
            user_id=self.user_id,
            xp_delta=xp_delta,
            coins_delta=coins_delta,
            actor_id=interaction.user.id,
            reason=(
                self.reason.value.strip()
                or "Correction administrative"
            ),
        )

        guild = interaction.guild

        if guild is not None:
            member = guild.get_member(self.user_id)

            if member is None:
                try:
                    member = await guild.fetch_member(self.user_id)
                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException,
                ):
                    member = None

            if member is not None:
                await self.cog.grant_earned_level_roles(
                    member,
                    int(stats["level"]),
                )

        await interaction.response.send_message(
            embed=success_embed(
                "Progression modifiée",
                (
                    f"Membre : <@{self.user_id}>\n"
                    f"XP : **{format_number(stats['total_xp'])}**\n"
                    f"Niveau : **{stats['level']}**\n"
                    f"Argent : **{format_number(stats['wallet'])} pièces**"
                ),
            ),
            ephemeral=True,
        )


class ConfirmProgressionResetView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        owner_id: int,
        guild_id: int,
        user_id: int,
    ) -> None:
        super().__init__(timeout=60)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.user_id = user_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Action interdite",
                "Seul l'administrateur ayant lancé cette action peut répondre.",
            ),
            ephemeral=True,
        )
        return False

    async def disable_buttons(
        self,
        interaction: discord.Interaction,
    ) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await interaction.response.edit_message(view=self)

    @discord.ui.button(
        label="Confirmer la réinitialisation",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.reset_member(
            guild_id=self.guild_id,
            user_id=self.user_id,
        )

        await self.disable_buttons(interaction)

        await interaction.followup.send(
            embed=success_embed(
                "Progression réinitialisée",
                (
                    f"La progression de <@{self.user_id}> "
                    "a été entièrement supprimée."
                ),
            ),
            ephemeral=True,
        )

        self.stop()

    @discord.ui.button(
        label="Annuler",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.disable_buttons(interaction)
        self.stop()


class XPMultiplierModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        role: discord.Role,
    ) -> None:
        super().__init__(
            title="Multiplicateur d'XP",
            timeout=300,
        )

        self.cog = cog
        self.role = role

        self.multiplier_input = discord.ui.TextInput(
            label="Multiplicateur",
            placeholder="Exemple : 1.5, 2 ou 0 pour supprimer",
            required=True,
            min_length=1,
            max_length=5,
        )

        self.add_item(self.multiplier_input)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "❌ Cette action doit être utilisée dans un serveur.",
                ephemeral=True,
            )
            return

        raw_value = (
            str(self.multiplier_input.value)
            .strip()
            .replace(",", ".")
        )

        try:
            multiplier = Decimal(raw_value)
        except InvalidOperation:
            await interaction.response.send_message(
                "❌ Entre un nombre valide, par exemple `1.5`, `2` ou `0`.",
                ephemeral=True,
            )
            return

        if multiplier != Decimal("0") and not (
            Decimal("1.00") <= multiplier <= Decimal("10.00")
        ):
            await interaction.response.send_message(
                (
                    "❌ Le multiplicateur doit être compris entre "
                    "**1 et 10**.\nEntre `0` pour supprimer la règle."
                ),
                ephemeral=True,
            )
            return

        try:
            saved = await self.cog.set_role_xp_multiplier(
                guild_id=guild.id,
                role_id=self.role.id,
                multiplier=multiplier,
            )
        except ValueError as error:
            await interaction.response.send_message(
                f"❌ {error}",
                ephemeral=True,
            )
            return

        if saved:
            normalized = multiplier.quantize(Decimal("0.01"))

            await interaction.response.send_message(
                embed=success_embed(
                    "Multiplicateur enregistré",
                    (
                        f"Les membres possédant {self.role.mention} "
                        f"gagneront maintenant **x{normalized.normalize()} XP**.\n\n"
                        "Ce multiplicateur s'applique aux messages et au vocal.\n"
                        "Si un membre possède plusieurs rôles, seul le "
                        "multiplicateur le plus élevé sera utilisé."
                    ),
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=success_embed(
                    "Multiplicateur supprimé",
                    (
                        f"{self.role.mention} ne possède plus "
                        "de multiplicateur d'XP."
                    ),
                ),
                ephemeral=True,
            )


class LevelRewardRoleModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        role: discord.Role,
    ) -> None:
        super().__init__(
            title="Rôle de niveau",
            timeout=300,
        )

        self.cog = cog
        self.role = role

        self.level_input = discord.ui.TextInput(
            label="Niveau demandé",
            placeholder="Exemple : 10 ou 0 pour supprimer",
            required=True,
            min_length=1,
            max_length=5,
        )

        self.add_item(self.level_input)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "❌ Cette action doit être utilisée dans un serveur.",
                ephemeral=True,
            )
            return

        try:
            required_level = int(
                str(self.level_input.value).strip()
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Entre un niveau entier valide.",
                ephemeral=True,
            )
            return

        if not 0 <= required_level <= 10_000:
            await interaction.response.send_message(
                (
                    "❌ Le niveau doit être compris entre **1 et 10 000**.\n"
                    "Entre `0` pour supprimer la règle."
                ),
                ephemeral=True,
            )
            return

        if required_level != 0:
            bot_member = guild.me

            if self.role.is_default():
                await interaction.response.send_message(
                    "❌ Le rôle `@everyone` ne peut pas être utilisé.",
                    ephemeral=True,
                )
                return

            if self.role.managed:
                await interaction.response.send_message(
                    "❌ Ce rôle est géré par Discord ou une intégration.",
                    ephemeral=True,
                )
                return

            if bot_member is None:
                await interaction.response.send_message(
                    "❌ Impossible de retrouver le rôle du bot.",
                    ephemeral=True,
                )
                return

            if not bot_member.guild_permissions.manage_roles:
                await interaction.response.send_message(
                    "❌ Le bot n'a pas la permission **Gérer les rôles**.",
                    ephemeral=True,
                )
                return

            if self.role >= bot_member.top_role:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Hiérarchie incorrecte",
                        (
                            f"Le rôle {self.role.mention} est au-dessus "
                            "du rôle principal du bot.\n\n"
                            "Déplace le rôle du bot plus haut."
                        ),
                    ),
                    ephemeral=True,
                )
                return

        try:
            saved = await self.cog.set_level_reward_role(
                guild_id=guild.id,
                role_id=self.role.id,
                required_level=required_level,
            )
        except ValueError as error:
            await interaction.response.send_message(
                f"❌ {error}",
                ephemeral=True,
            )
            return

        if saved:
            await interaction.response.send_message(
                embed=success_embed(
                    "Rôle de niveau enregistré",
                    (
                        f"Le rôle {self.role.mention} sera donné aux membres "
                        f"ayant atteint le niveau **{required_level}**."
                    ),
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=success_embed(
                    "Rôle de niveau supprimé",
                    (
                        f"{self.role.mention} n'est plus une "
                        "récompense de niveau."
                    ),
                ),
                ephemeral=True,
            )


class ProgressionRuleRoleSelect(discord.ui.RoleSelect):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        action: str,
    ) -> None:
        self.cog = cog
        self.action = action

        super().__init__(
            placeholder="Choisis un rôle…",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.values:
            await interaction.response.send_message(
                "❌ Aucun rôle sélectionné.",
                ephemeral=True,
            )
            return

        selected = self.values[0]

        if isinstance(selected, discord.Role):
            role = selected
        else:
            guild = interaction.guild

            if guild is None:
                await interaction.response.send_message(
                    "❌ Serveur introuvable.",
                    ephemeral=True,
                )
                return

            role = guild.get_role(selected.id)

            if role is None:
                await interaction.response.send_message(
                    "❌ Rôle introuvable.",
                    ephemeral=True,
                )
                return

        if self.action == "multiplier":
            await interaction.response.send_modal(
                XPMultiplierModal(
                    cog=self.cog,
                    role=role,
                )
            )
            return

        if self.action == "level-role":
            await interaction.response.send_modal(
                LevelRewardRoleModal(
                    cog=self.cog,
                    role=role,
                )
            )
            return

        await interaction.response.send_message(
            "❌ Action administrative inconnue.",
            ephemeral=True,
        )


class ProgressionRuleRoleView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        owner_id: int,
        action: str,
    ) -> None:
        super().__init__(timeout=180)

        self.owner_id = owner_id

        self.add_item(
            ProgressionRuleRoleSelect(
                cog=cog,
                action=action,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            (
                "❌ Seul l'administrateur ayant ouvert ce menu "
                "peut l'utiliser."
            ),
            ephemeral=True,
        )
        return False

class VoiceXPConfigModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        guild_id: int,
        current_value: int,
    ) -> None:
        super().__init__(
            title="Configuration de l'XP vocal",
            timeout=300,
        )

        self.cog = cog
        self.guild_id = guild_id

        self.voice_xp_input = discord.ui.TextInput(
            label="XP gagnée chaque minute en vocal",
            placeholder="Exemple : 5",
            default=str(current_value),
            required=True,
            min_length=1,
            max_length=7,
        )

        self.add_item(self.voice_xp_input)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            voice_xp = int(
                str(self.voice_xp_input.value).strip()
            )
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    "Entre un nombre entier, par exemple `5`.",
                ),
                ephemeral=True,
            )
            return

        if not 0 <= voice_xp <= 1_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    (
                        "L'XP vocal doit être comprise entre "
                        "**0 et 1 000 000**."
                    ),
                ),
                ephemeral=True,
            )
            return

        await self.cog.update_voice_xp(
            guild_id=self.guild_id,
            voice_xp_per_minute=voice_xp,
        )

        if voice_xp == 0:
            description = (
                "Le gain automatique d'XP en vocal est maintenant "
                "**désactivé**."
            )
        else:
            description = (
                "Les membres éligibles gagneront désormais "
                f"**{format_number(voice_xp)} XP par minute** "
                "passée en vocal."
            )

        await interaction.response.send_message(
            embed=success_embed(
                "XP vocal configurée",
                description,
            ),
            ephemeral=True,
        )




class ProgressionAdminView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        owner_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(timeout=600)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.selected_user_id: int | None = None

        self.add_item(AdminMemberSelect(self))

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Panneau personnel",
                "Ce panneau appartient à un autre administrateur.",
            ),
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="Configuration",
        emoji="⚙️",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def configuration(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )

        await interaction.response.send_modal(
            ProgressionConfigModal(
                cog=self.cog,
                guild_id=self.guild_id,
                settings=settings,
            )
        )

    @discord.ui.button(
        label="Activer/désactiver",
        emoji="🔌",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_system(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )

        enabled = not settings["enabled"]

        await self.cog.set_setting_boolean(
            guild_id=self.guild_id,
            column="enabled",
            value=enabled,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "État modifié",
                (
                    "Le gain automatique d'XP et d'argent est maintenant "
                    f"**{'activé' if enabled else 'désactivé'}**."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Notifications de niveau",
        emoji="🔔",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_notifications(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )

        enabled = not settings["level_notifications"]

        await self.cog.set_setting_boolean(
            guild_id=self.guild_id,
            column="level_notifications",
            value=enabled,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Notifications modifiées",
                (
                    "Les annonces de montée de niveau sont maintenant "
                    f"**{'activées' if enabled else 'désactivées'}**."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Modifier le membre",
        emoji="✏️",
        style=discord.ButtonStyle.success,
        row=2,
    )
    async def modify_member(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.selected_user_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Aucun membre",
                    "Sélectionne d'abord un membre dans le menu.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            AdjustMemberModal(
                cog=self.cog,
                guild_id=self.guild_id,
                user_id=self.selected_user_id,
            )
        )

    @discord.ui.button(
        label="Réinitialiser le membre",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=2,
    )
    async def reset_selected_member(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.selected_user_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Aucun membre",
                    "Sélectionne d'abord un membre dans le menu.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=warning_embed(
                "Confirmation obligatoire",
                (
                    f"Tu vas supprimer l'XP et l'argent de "
                    f"<@{self.selected_user_id}>.\n\n"
                    "**Cette action est définitive.**"
                ),
            ),
            view=ConfirmProgressionResetView(
                cog=self.cog,
                owner_id=self.owner_id,
                guild_id=self.guild_id,
                user_id=self.selected_user_id,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Multiplicateur XP",
        emoji="✨",
        style=discord.ButtonStyle.primary,
        row=3,
    )
    async def configure_xp_multiplier(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            embed=base_embed(
                "✨ Multiplicateur d'XP",
                (
                    "Choisis le rôle auquel appliquer un multiplicateur.\n\n"
                    "Ensuite, entre une valeur entre **1 et 10**.\n"
                    "Entre `0` pour supprimer son multiplicateur."
                ),
            ),
            view=ProgressionRuleRoleView(
                cog=self.cog,
                owner_id=interaction.user.id,
                action="multiplier",
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Rôle de niveau",
        emoji="🎭",
        style=discord.ButtonStyle.primary,
        row=3,
    )
    async def configure_level_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            embed=base_embed(
                "🎭 Rôle de niveau",
                (
                    "Choisis le rôle qui devra être donné automatiquement.\n\n"
                    "Ensuite, indique le niveau nécessaire.\n"
                    "Entre `0` pour supprimer cette récompense."
                ),
            ),
            view=ProgressionRuleRoleView(
                cog=self.cog,
                owner_id=interaction.user.id,
                action="level-role",
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Voir les règles",
        emoji="📋",
        style=discord.ButtonStyle.secondary,
        row=3,
    )
    async def show_progression_rules(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "❌ Cette action doit être utilisée dans un serveur.",
                ephemeral=True,
            )
            return

        embed = await self.cog.build_progression_rules_embed(guild)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="XP vocal",
        emoji="🎙️",
        style=discord.ButtonStyle.secondary,
        row=4,
    )
    async def configure_voice_xp(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )
    
        modal = VoiceXPConfigModal(
            cog=self.cog,
            guild_id=self.guild_id,
            current_value=int(
                settings["voice_xp_per_minute"]
            ),
        )
    
        await interaction.response.send_modal(modal)



class ProgressionCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

        self._settings_cache: dict[
            int,
            tuple[float, dict[str, Any]],
        ] = {}

    async def cog_load(self) -> None:
        if not self.voice_xp_loop.is_running():
            self.voice_xp_loop.start()

    def cog_unload(self) -> None:
        if self.voice_xp_loop.is_running():
            self.voice_xp_loop.cancel()

    def get_pool(self):
        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            raise RuntimeError(
                "Le gestionnaire PostgreSQL est indisponible."
            )

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_settings (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                cooldown_seconds INTEGER NOT NULL DEFAULT 60
                    CHECK (
                        cooldown_seconds >= 5
                        AND cooldown_seconds <= 3600
                    ),
                xp_min INTEGER NOT NULL DEFAULT 15
                    CHECK (xp_min >= 0),
                xp_max INTEGER NOT NULL DEFAULT 25
                    CHECK (xp_max >= xp_min),
                coins_min INTEGER NOT NULL DEFAULT 2
                    CHECK (coins_min >= 0),
                coins_max INTEGER NOT NULL DEFAULT 4
                    CHECK (coins_max >= coins_min),
                voice_xp_per_minute INTEGER NOT NULL DEFAULT 5
                    CHECK (
                        voice_xp_per_minute >= 0
                        AND voice_xp_per_minute <= 1000000
                    ),
                level_notifications BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        # Migration nécessaire si progression_settings existait
        # déjà avant l'ajout de l'XP vocal.
        await pool.execute(
            """
            ALTER TABLE progression_settings
            ADD COLUMN IF NOT EXISTS voice_xp_per_minute INTEGER
                NOT NULL DEFAULT 5
                CHECK (
                    voice_xp_per_minute >= 0
                    AND voice_xp_per_minute <= 1000000
                )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_members (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                total_xp BIGINT NOT NULL DEFAULT 0
                    CHECK (total_xp >= 0),
                wallet BIGINT NOT NULL DEFAULT 0
                    CHECK (wallet >= 0),
                lifetime_coins BIGINT NOT NULL DEFAULT 0
                    CHECK (lifetime_coins >= 0),
                rewarded_messages BIGINT NOT NULL DEFAULT 0
                    CHECK (rewarded_messages >= 0),
                last_reward_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_transactions (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                actor_id BIGINT,
                amount BIGINT NOT NULL,
                transaction_type VARCHAR(50) NOT NULL,
                reason VARCHAR(200) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_role_multipliers (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                multiplier NUMERIC(6, 2) NOT NULL
                    CHECK (
                        multiplier >= 1.00
                        AND multiplier <= 10.00
                    ),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_level_roles (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                required_level INTEGER NOT NULL
                    CHECK (
                        required_level >= 1
                        AND required_level <= 10000
                    ),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_voice_rewards (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                last_reward_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                rewarded_minutes BIGINT NOT NULL DEFAULT 0
                    CHECK (rewarded_minutes >= 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS progression_members_xp_idx
            ON progression_members (
                guild_id,
                total_xp DESC
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS progression_members_wallet_idx
            ON progression_members (
                guild_id,
                wallet DESC
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS progression_transactions_user_idx
            ON progression_transactions (
                guild_id,
                user_id,
                created_at DESC
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS progression_level_roles_level_idx
            ON progression_level_roles (
                guild_id,
                required_level
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS progression_role_multipliers_guild_idx
            ON progression_role_multipliers (
                guild_id
            )
            """
        )

        LOGGER.info(
            "Tables du système de progression vérifiées"
        )

    async def ensure_settings(
        self,
        guild_id: int,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            INSERT INTO progression_settings (
                guild_id
            )
            VALUES ($1)
            ON CONFLICT (guild_id) DO NOTHING
            """,
            guild_id,
        )

    async def get_settings(
        self,
        guild_id: int,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        current_time = time.monotonic()
        cached = self._settings_cache.get(guild_id)

        if (
            use_cache
            and cached is not None
            and cached[0] > current_time
        ):
            return cached[1]

        await self.ensure_settings(guild_id)

        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                enabled,
                cooldown_seconds,
                xp_min,
                xp_max,
                coins_min,
                coins_max,
                voice_xp_per_minute,
                level_notifications
            FROM progression_settings
            WHERE guild_id = $1
            """,
            guild_id,
        )

        if record is None:
            raise RuntimeError(
                "La configuration de progression est introuvable."
            )

        settings = {
            "enabled": bool(record["enabled"]),
            "cooldown_seconds": int(
                record["cooldown_seconds"]
            ),
            "xp_min": int(record["xp_min"]),
            "xp_max": int(record["xp_max"]),
            "coins_min": int(record["coins_min"]),
            "coins_max": int(record["coins_max"]),
            "voice_xp_per_minute": int(
                record["voice_xp_per_minute"]
            ),
            "level_notifications": bool(
                record["level_notifications"]
            ),
        }

        self._settings_cache[guild_id] = (
            current_time + 60,
            settings,
        )

        return settings

    async def update_settings(
        self,
        *,
        guild_id: int,
        cooldown_seconds: int,
        xp_min: int,
        xp_max: int,
        coins_min: int,
        coins_max: int,
    ) -> None:
        await self.ensure_settings(guild_id)

        pool = self.get_pool()

        await pool.execute(
            """
            UPDATE progression_settings
            SET
                cooldown_seconds = $2,
                xp_min = $3,
                xp_max = $4,
                coins_min = $5,
                coins_max = $6,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            cooldown_seconds,
            xp_min,
            xp_max,
            coins_min,
            coins_max,
        )

        self._settings_cache.pop(
            guild_id,
            None,
        )

    async def update_voice_xp(
        self,
        *,
        guild_id: int,
        voice_xp_per_minute: int,
    ) -> None:
        if not 0 <= voice_xp_per_minute <= 1_000_000:
            raise ValueError(
                "L'XP vocal doit être comprise entre 0 et 1 000 000."
            )

        await self.ensure_settings(guild_id)

        pool = self.get_pool()

        await pool.execute(
            """
            UPDATE progression_settings
            SET
                voice_xp_per_minute = $2,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            voice_xp_per_minute,
        )

        self._settings_cache.pop(
            guild_id,
            None,
        )

    async def set_setting_boolean(
        self,
        *,
        guild_id: int,
        column: str,
        value: bool,
    ) -> None:
        if column not in {
            "enabled",
            "level_notifications",
        }:
            raise ValueError(
                "Colonne de configuration invalide."
            )

        await self.ensure_settings(guild_id)

        pool = self.get_pool()

        await pool.execute(
            f"""
            UPDATE progression_settings
            SET
                {column} = $2,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            value,
        )

        self._settings_cache.pop(guild_id, None)

    async def get_member_stats(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> dict[str, int]:
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                total_xp,
                wallet,
                lifetime_coins,
                rewarded_messages
            FROM progression_members
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

        if record is None:
            total_xp = 0
            wallet = 0
            lifetime_coins = 0
            rewarded_messages = 0
        else:
            total_xp = int(record["total_xp"] or 0)
            wallet = int(record["wallet"] or 0)
            lifetime_coins = int(record["lifetime_coins"] or 0)
            rewarded_messages = int(
                record["rewarded_messages"] or 0
            )

        return {
            "total_xp": total_xp,
            "wallet": wallet,
            "lifetime_coins": lifetime_coins,
            "rewarded_messages": rewarded_messages,
            "level": level_from_xp(total_xp),
        }

    async def get_member_rank(
        self,
        *,
        guild_id: int,
        user_id: int,
        total_xp: int,
    ) -> int | None:
        if total_xp <= 0:
            return None

        pool = self.get_pool()

        rank = await pool.fetchval(
            """
            SELECT COUNT(*) + 1
            FROM progression_members
            WHERE guild_id = $1
              AND (
                    total_xp > $2
                    OR (
                        total_xp = $2
                        AND user_id < $3
                    )
              )
            """,
            guild_id,
            total_xp,
            user_id,
        )

        return int(rank) if rank is not None else None

    async def get_member_xp_multiplier(
        self,
        member: discord.Member,
    ) -> Decimal:
        role_ids = [
            role.id
            for role in member.roles
        ]

        if not role_ids:
            return Decimal("1.00")

        pool = self.get_pool()

        value = await pool.fetchval(
            """
            SELECT MAX(multiplier)
            FROM progression_role_multipliers
            WHERE guild_id = $1
              AND role_id = ANY($2::BIGINT[])
            """,
            member.guild.id,
            role_ids,
        )

        if value is None:
            return Decimal("1.00")

        multiplier = Decimal(str(value))

        if multiplier < Decimal("1.00"):
            return Decimal("1.00")

        return multiplier

    async def set_role_xp_multiplier(
        self,
        *,
        guild_id: int,
        role_id: int,
        multiplier: Decimal,
    ) -> bool:
        pool = self.get_pool()

        if multiplier == Decimal("0"):
            await pool.execute(
                """
                DELETE FROM progression_role_multipliers
                WHERE guild_id = $1
                  AND role_id = $2
                """,
                guild_id,
                role_id,
            )
            return False

        normalized = multiplier.quantize(
            Decimal("0.01")
        )

        if not Decimal("1.00") <= normalized <= Decimal("10.00"):
            raise ValueError(
                "Le multiplicateur doit être compris entre 1 et 10."
            )

        await pool.execute(
            """
            INSERT INTO progression_role_multipliers (
                guild_id,
                role_id,
                multiplier,
                updated_at
            )
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (guild_id, role_id)
            DO UPDATE SET
                multiplier = EXCLUDED.multiplier,
                updated_at = NOW()
            """,
            guild_id,
            role_id,
            normalized,
        )

        return True

    async def set_level_reward_role(
        self,
        *,
        guild_id: int,
        role_id: int,
        required_level: int,
    ) -> bool:
        pool = self.get_pool()

        if required_level == 0:
            await pool.execute(
                """
                DELETE FROM progression_level_roles
                WHERE guild_id = $1
                  AND role_id = $2
                """,
                guild_id,
                role_id,
            )
            return False

        if not 1 <= required_level <= 10_000:
            raise ValueError(
                "Le niveau doit être compris entre 1 et 10 000."
            )

        await pool.execute(
            """
            INSERT INTO progression_level_roles (
                guild_id,
                role_id,
                required_level,
                updated_at
            )
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (guild_id, role_id)
            DO UPDATE SET
                required_level = EXCLUDED.required_level,
                updated_at = NOW()
            """,
            guild_id,
            role_id,
            required_level,
        )

        return True

    async def grant_earned_level_roles(
        self,
        member: discord.Member,
        level: int,
    ) -> list[discord.Role]:
        pool = self.get_pool()

        # On récupère TOUS les rôles de palier du serveur (pas seulement
        # ceux débloqués) afin de pouvoir retirer les anciens paliers
        # que le membre possède déjà.
        records = await pool.fetch(
            """
            SELECT
                role_id,
                required_level
            FROM progression_level_roles
            WHERE guild_id = $1
            ORDER BY required_level ASC
            """,
            member.guild.id,
        )

        if not records:
            return []

        bot_member = member.guild.me

        if bot_member is None:
            return []

        if not bot_member.guild_permissions.manage_roles:
            LOGGER.warning(
                "Le bot n'a pas la permission Gérer les rôles "
                "sur le serveur %s.",
                member.guild.id,
            )
            return []

        # Le palier le plus élevé que le membre a débloqué avec ce
        # niveau (les enregistrements sont triés par required_level
        # croissant, donc le dernier qui convient est le plus haut).
        target_record = None

        for record in records:
            if int(record["required_level"]) <= level:
                target_record = record
            else:
                break

        target_role: discord.Role | None = None

        if target_record is not None:
            role = member.guild.get_role(
                int(target_record["role_id"])
            )

            if (
                role is not None
                and not role.is_default()
                and not role.managed
                and role < bot_member.top_role
            ):
                target_role = role

        roles_to_add: list[discord.Role] = []

        if target_role is not None and target_role not in member.roles:
            roles_to_add.append(target_role)

        # Tous les autres rôles de palier que le membre possède déjà
        # doivent être retirés pour qu'il n'en garde qu'un seul.
        roles_to_remove: list[discord.Role] = []

        for record in records:
            role = member.guild.get_role(
                int(record["role_id"])
            )

            if role is None:
                continue

            if target_role is not None and role.id == target_role.id:
                continue

            if role.is_default() or role.managed:
                continue

            if role >= bot_member.top_role:
                continue

            if role in member.roles:
                roles_to_remove.append(role)

        if not roles_to_add and not roles_to_remove:
            return []

        try:
            if roles_to_add:
                await member.add_roles(
                    *roles_to_add,
                    reason=(
                        "Récompenses automatiques de progression "
                        f"— niveau {level}"
                    ),
                )

            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason=(
                        "Nettoyage des anciens rôles de niveau "
                        f"— niveau {level}"
                    ),
                )
        except discord.HTTPException:
            LOGGER.exception(
                "Impossible de mettre à jour les rôles de niveau de %s.",
                member.id,
            )
            return []

        return roles_to_add

    async def build_progression_rules_embed(
        self,
        guild: discord.Guild,
    ) -> discord.Embed:
        pool = self.get_pool()

        settings = await self.get_settings(
            guild.id,
            use_cache=False,
        )

        voice_xp = int(
            settings["voice_xp_per_minute"]
        )


        multiplier_records = await pool.fetch(
            """
            SELECT
                role_id,
                multiplier
            FROM progression_role_multipliers
            WHERE guild_id = $1
            ORDER BY multiplier DESC, role_id ASC
            """,
            guild.id,
        )

        level_records = await pool.fetch(
            """
            SELECT
                role_id,
                required_level
            FROM progression_level_roles
            WHERE guild_id = $1
            ORDER BY required_level ASC, role_id ASC
            """,
            guild.id,
        )

        embed = base_embed(
            "⚙️ Règles de progression",
            (
                "Configuration des multiplicateurs d'XP "
                "et des récompenses de niveau.\n\n"
                f"🎙️ Le vocal rapporte **{voice_xp} XP "
                "par minute** lorsqu'au moins deux membres actifs "
                "sont présents."
            ),
        )

        if multiplier_records:
            lines: list[str] = []

            for record in multiplier_records:
                role_id = int(record["role_id"])
                multiplier = Decimal(str(record["multiplier"]))
                role = guild.get_role(role_id)

                role_text = (
                    role.mention
                    if role is not None
                    else f"Rôle supprimé (`{role_id}`)"
                )

                lines.append(
                    f"• {role_text} → **x{multiplier.normalize()} XP**"
                )

            embed.add_field(
                name="✨ Multiplicateurs d'XP",
                value="\n".join(lines)[:1024],
                inline=False,
            )
        else:
            embed.add_field(
                name="✨ Multiplicateurs d'XP",
                value="Aucun multiplicateur configuré.",
                inline=False,
            )

        if level_records:
            lines = []

            for record in level_records:
                role_id = int(record["role_id"])
                required_level = int(record["required_level"])
                role = guild.get_role(role_id)

                role_text = (
                    role.mention
                    if role is not None
                    else f"Rôle supprimé (`{role_id}`)"
                )

                lines.append(
                    f"• Niveau **{required_level}** → {role_text}"
                )

            embed.add_field(
                name="🎭 Rôles de niveau",
                value="\n".join(lines)[:1024],
                inline=False,
            )
        else:
            embed.add_field(
                name="🎭 Rôles de niveau",
                value="Aucun rôle de niveau configuré.",
                inline=False,
            )

        embed.set_footer(
            text="Entre 0 dans un formulaire pour supprimer une règle."
        )

        return embed

    async def award_message(
        self,
        *,
        guild_id: int,
        user_id: int,
        settings: dict[str, Any],
        xp_multiplier: Decimal = Decimal("1.00"),
    ) -> dict[str, Any] | None:
        pool = self.get_pool()
        current_time = datetime.now(timezone.utc)

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1, 0)
                    )
                    """,
                    f"progression:{guild_id}:{user_id}",
                )

                await connection.execute(
                    """
                    INSERT INTO progression_members (
                        guild_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id, user_id)
                    DO NOTHING
                    """,
                    guild_id,
                    user_id,
                )

                current = await connection.fetchrow(
                    """
                    SELECT
                        total_xp,
                        last_reward_at
                    FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )

                if current is None:
                    return None

                last_reward_at = current["last_reward_at"]

                if last_reward_at is not None:
                    elapsed = (
                        current_time - last_reward_at
                    ).total_seconds()

                    if elapsed < settings["cooldown_seconds"]:
                        return None

                base_xp_gain = random.randint(
                    int(settings["xp_min"]),
                    int(settings["xp_max"]),
                )

                xp_gain = int(
                    (
                        Decimal(base_xp_gain)
                        * xp_multiplier
                    ).quantize(
                        Decimal("1"),
                        rounding=ROUND_HALF_UP,
                    )
                )

                coins_gain = random.randint(
                    int(settings["coins_min"]),
                    int(settings["coins_max"]),
                )

                old_xp = int(current["total_xp"] or 0)
                old_level = level_from_xp(old_xp)

                updated = await connection.fetchrow(
                    """
                    UPDATE progression_members
                    SET
                        total_xp = total_xp + $3,
                        wallet = wallet + $4,
                        lifetime_coins = lifetime_coins + $4,
                        rewarded_messages = rewarded_messages + 1,
                        last_reward_at = $5,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    RETURNING
                        total_xp,
                        wallet
                    """,
                    guild_id,
                    user_id,
                    xp_gain,
                    coins_gain,
                    current_time,
                )

                if updated is None:
                    return None

                if coins_gain != 0:
                    await connection.execute(
                        """
                        INSERT INTO progression_transactions (
                            guild_id,
                            user_id,
                            actor_id,
                            amount,
                            transaction_type,
                            reason
                        )
                        VALUES (
                            $1,
                            $2,
                            NULL,
                            $3,
                            'message_reward',
                            'Récompense de message'
                        )
                        """,
                        guild_id,
                        user_id,
                        coins_gain,
                    )

                total_xp = int(updated["total_xp"])

                return {
                    "xp_gain": xp_gain,
                    "coins_gain": coins_gain,
                    "base_xp_gain": base_xp_gain,
                    "xp_multiplier": xp_multiplier,
                    "total_xp": total_xp,
                    "wallet": int(updated["wallet"]),
                    "old_level": old_level,
                    "new_level": level_from_xp(total_xp),
                }

    async def reset_voice_timer(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            INSERT INTO progression_voice_rewards (
                guild_id,
                user_id,
                last_reward_at,
                updated_at
            )
            VALUES ($1, $2, NOW(), NOW())
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET
                last_reward_at = NOW(),
                updated_at = NOW()
            """,
            guild_id,
            user_id,
        )

    async def award_voice_minute(
        self,
        *,
        member: discord.Member,
        xp_multiplier: Decimal,
        voice_xp_per_minute: int,
    ) -> dict[str, Any] | None:
        pool = self.get_pool()
        current_time = datetime.now(timezone.utc)

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1, 0)
                    )
                    """,
                    f"progression:{member.guild.id}:{member.id}",
                )

                await connection.execute(
                    """
                    INSERT INTO progression_members (
                        guild_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id, user_id)
                    DO NOTHING
                    """,
                    member.guild.id,
                    member.id,
                )

                insert_status = await connection.execute(
                    """
                    INSERT INTO progression_voice_rewards (
                        guild_id,
                        user_id,
                        last_reward_at,
                        rewarded_minutes,
                        updated_at
                    )
                    VALUES ($1, $2, $3, 0, NOW())
                    ON CONFLICT (guild_id, user_id)
                    DO NOTHING
                    """,
                    member.guild.id,
                    member.id,
                    current_time,
                )

                if insert_status == "INSERT 0 1":
                    return None

                voice_record = await connection.fetchrow(
                    """
                    SELECT
                        last_reward_at
                    FROM progression_voice_rewards
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    member.guild.id,
                    member.id,
                )

                if voice_record is None:
                    return None

                last_reward_at = voice_record["last_reward_at"]

                elapsed = (
                    current_time - last_reward_at
                ).total_seconds()

                if elapsed < VOICE_REWARD_INTERVAL_SECONDS:
                    return None

                current = await connection.fetchrow(
                    """
                    SELECT
                        total_xp
                    FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    member.guild.id,
                    member.id,
                )

                if current is None:
                    return None

                xp_gain = int(
                    (
                        Decimal(voice_xp_per_minute)
                        * xp_multiplier
                    ).quantize(
                        Decimal("1"),
                        rounding=ROUND_HALF_UP,
                    )
                )

                xp_gain = max(0, xp_gain)

                old_xp = int(current["total_xp"] or 0)
                old_level = level_from_xp(old_xp)

                resulting_xp = await connection.fetchval(
                    """
                    UPDATE progression_members
                    SET
                        total_xp = total_xp + $3,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    RETURNING total_xp
                    """,
                    member.guild.id,
                    member.id,
                    xp_gain,
                )

                if resulting_xp is None:
                    return None

                await connection.execute(
                    """
                    UPDATE progression_voice_rewards
                    SET
                        last_reward_at = $3,
                        rewarded_minutes = rewarded_minutes + 1,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    member.guild.id,
                    member.id,
                    current_time,
                )

                total_xp = int(resulting_xp)

                return {
                    "xp_gain": xp_gain,
                    "xp_multiplier": xp_multiplier,
                    "total_xp": total_xp,
                    "old_level": old_level,
                    "new_level": level_from_xp(total_xp),
                }

    def is_active_voice_member(
        self,
        member: discord.Member,
    ) -> bool:
        if member.bot:
            return False

        voice = member.voice

        if voice is None or voice.channel is None:
            return False

        if member.guild.afk_channel is not None:
            if voice.channel.id == member.guild.afk_channel.id:
                return False

        if voice.self_mute or voice.mute:
            return False

        if voice.self_deaf or voice.deaf:
            return False

        return True

    async def send_voice_level_notification(
        self,
        *,
        member: discord.Member,
        result: dict[str, Any],
        granted_roles: list[discord.Role],
    ) -> None:
        settings = await self.get_settings(member.guild.id)

        if not settings["level_notifications"]:
            return

        channel = member.guild.system_channel

        if channel is None:
            return

        bot_member = member.guild.me

        if bot_member is None:
            return

        permissions = channel.permissions_for(bot_member)

        if not (
            permissions.view_channel
            and permissions.send_messages
            and permissions.embed_links
        ):
            return

        multiplier = Decimal(
            str(result["xp_multiplier"])
        )

        multiplier_text = ""

        if multiplier > Decimal("1.00"):
            multiplier_text = (
                "\n✨ Multiplicateur de rôle : "
                f"**x{multiplier.normalize()}**"
            )

        roles_text = ""

        if granted_roles:
            roles_text = (
                "\n🎭 Rôle(s) débloqué(s) : "
                + ", ".join(
                    role.mention
                    for role in granted_roles
                )
            )

        embed = success_embed(
            "Niveau supérieur !",
            (
                f"{member.mention} vient d'atteindre le "
                f"**niveau {result['new_level']}** grâce au vocal !\n\n"
                f"🎙️ XP gagné : **{result['xp_gain']}**"
                f"{multiplier_text}"
                f"{roles_text}"
            ),
        )

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            LOGGER.debug(
                "Impossible d'envoyer la notification de niveau vocal.",
                exc_info=True,
            )

    @tasks.loop(seconds=60)
    async def voice_xp_loop(self) -> None:
        for guild in self.bot.guilds:
            try:
                settings = await self.get_settings(guild.id)

                if not settings["enabled"]:
                    continue


                voice_xp_per_minute = int(
                    settings["voice_xp_per_minute"]
                )

                if voice_xp_per_minute <= 0:
                    continue

                
                
                channels: list[
                    discord.VoiceChannel | discord.StageChannel
                ] = [
                    *guild.voice_channels,
                    *guild.stage_channels,
                ]

                for channel in channels:
                    human_members = [
                        member
                        for member in channel.members
                        if not member.bot
                    ]

                    active_members = [
                        member
                        for member in human_members
                        if self.is_active_voice_member(member)
                    ]

                    if len(active_members) < 2:
                        for member in human_members:
                            await self.reset_voice_timer(
                                guild_id=guild.id,
                                user_id=member.id,
                            )

                        continue

                    active_ids = {
                        member.id
                        for member in active_members
                    }

                    for member in human_members:
                        if member.id not in active_ids:
                            await self.reset_voice_timer(
                                guild_id=guild.id,
                                user_id=member.id,
                            )

                    for member in active_members:
                        try:
                            multiplier = (
                                await self.get_member_xp_multiplier(
                                    member
                                )
                            )

                            result = await self.award_voice_minute(
                                member=member,
                                xp_multiplier=multiplier,
                                voice_xp_per_minute=voice_xp_per_minute,
                            )


                            if result is None:
                                continue

                            granted_roles = (
                                await self.grant_earned_level_roles(
                                    member,
                                    int(result["new_level"]),
                                )
                            )

                            if (
                                result["new_level"]
                                > result["old_level"]
                            ):
                                await self.send_voice_level_notification(
                                    member=member,
                                    result=result,
                                    granted_roles=granted_roles,
                                )

                        except Exception:
                            LOGGER.exception(
                                (
                                    "Impossible d'attribuer l'XP vocal "
                                    "à %s dans le serveur %s"
                                ),
                                member.id,
                                guild.id,
                            )

            except Exception:
                LOGGER.exception(
                    (
                        "Impossible de traiter les récompenses vocales "
                        "du serveur %s"
                    ),
                    guild.id,
                )

    @voice_xp_loop.before_loop
    async def before_voice_xp_loop(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        changed = (
            before.channel != after.channel
            or before.self_mute != after.self_mute
            or before.self_deaf != after.self_deaf
            or before.mute != after.mute
            or before.deaf != after.deaf
        )

        if not changed:
            return

        try:
            await self.reset_voice_timer(
                guild_id=member.guild.id,
                user_id=member.id,
            )
        except Exception:
            LOGGER.exception(
                "Impossible de réinitialiser le minuteur vocal de %s.",
                member.id,
            )

    async def adjust_member(
        self,
        *,
        guild_id: int,
        user_id: int,
        xp_delta: int,
        coins_delta: int,
        actor_id: int,
        reason: str,
    ) -> dict[str, int]:
        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1, 0)
                    )
                    """,
                    f"progression:{guild_id}:{user_id}",
                )

                await connection.execute(
                    """
                    INSERT INTO progression_members (
                        guild_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id, user_id)
                    DO NOTHING
                    """,
                    guild_id,
                    user_id,
                )

                current = await connection.fetchrow(
                    """
                    SELECT
                        total_xp,
                        wallet,
                        lifetime_coins
                    FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )

                if current is None:
                    raise RuntimeError(
                        "Le membre n'a pas pu être créé."
                    )

                old_xp = int(current["total_xp"] or 0)
                old_wallet = int(current["wallet"] or 0)
                lifetime_coins = int(
                    current["lifetime_coins"] or 0
                )

                new_xp = max(0, old_xp + xp_delta)
                new_wallet = max(0, old_wallet + coins_delta)

                actual_coins_delta = new_wallet - old_wallet

                new_lifetime_coins = (
                    lifetime_coins
                    + max(0, actual_coins_delta)
                )

                await connection.execute(
                    """
                    UPDATE progression_members
                    SET
                        total_xp = $3,
                        wallet = $4,
                        lifetime_coins = $5,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                    new_xp,
                    new_wallet,
                    new_lifetime_coins,
                )

                if actual_coins_delta != 0:
                    await connection.execute(
                        """
                        INSERT INTO progression_transactions (
                            guild_id,
                            user_id,
                            actor_id,
                            amount,
                            transaction_type,
                            reason
                        )
                        VALUES (
                            $1,
                            $2,
                            $3,
                            $4,
                            'admin_adjustment',
                            $5
                        )
                        """,
                        guild_id,
                        user_id,
                        actor_id,
                        actual_coins_delta,
                        reason[:200],
                    )

        return {
            "total_xp": new_xp,
            "wallet": new_wallet,
            "level": level_from_xp(new_xp),
        }

    async def reset_member(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> None:
        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    DELETE FROM progression_transactions
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                )

                await connection.execute(
                    """
                    DELETE FROM progression_voice_rewards
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                )

                await connection.execute(
                    """
                    DELETE FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                )

    async def build_progression_card(
        self,
        *,
        member: discord.Member | discord.User,
        guild_id: int,
    ) -> discord.File:
        stats = await self.get_member_stats(
            guild_id=guild_id,
            user_id=member.id,
        )

        total_xp = stats["total_xp"]
        level = stats["level"]

        current_level_xp = xp_for_level(level)
        next_level_xp = xp_for_level(level + 1)

        current_progress = max(
            0,
            total_xp - current_level_xp,
        )

        required_progress = max(
            1,
            next_level_xp - current_level_xp,
        )

        rank = await self.get_member_rank(
            guild_id=guild_id,
            user_id=member.id,
            total_xp=total_xp,
        )

        avatar_bytes: bytes | None = None

        try:
            avatar_bytes = await member.display_avatar.read()
        except discord.HTTPException:
            LOGGER.debug(
                "Impossible de télécharger l'avatar de %s.",
                member.id,
                exc_info=True,
            )

        image = await asyncio.to_thread(
            render_progression_card,
            avatar_bytes=avatar_bytes,
            display_name=member.display_name,
            level=level,
            rank=rank,
            total_xp=total_xp,
            current_xp=current_progress,
            required_xp=required_progress,
            wallet=stats["wallet"],
            lifetime_coins=stats["lifetime_coins"],
        )

        if isinstance(image, io.BytesIO):
            image.seek(0)
            buffer = image
        elif isinstance(image, bytes):
            buffer = io.BytesIO(image)
        else:
            raise TypeError(
                "render_progression_card doit retourner bytes ou BytesIO."
            )

        return discord.File(
            buffer,
            filename=f"progression-{member.id}.png",
        )

    async def build_leaderboard_embed(
        self,
        *,
        guild: discord.Guild,
        ranking_type: str,
    ) -> discord.Embed:
        pool = self.get_pool()

        if ranking_type == "money":
            records = await pool.fetch(
                """
                SELECT
                    user_id,
                    wallet,
                    total_xp
                FROM progression_members
                WHERE guild_id = $1
                ORDER BY
                    wallet DESC,
                    total_xp DESC,
                    user_id ASC
                LIMIT 10
                """,
                guild.id,
            )

            title = "💰 Classement de l'argent"
        else:
            records = await pool.fetch(
                """
                SELECT
                    user_id,
                    wallet,
                    total_xp
                FROM progression_members
                WHERE guild_id = $1
                ORDER BY
                    total_xp DESC,
                    wallet DESC,
                    user_id ASC
                LIMIT 10
                """,
                guild.id,
            )

            title = "🏆 Classement XP"

        if not records:
            return base_embed(
                title,
                "Aucun membre ne possède encore de progression.",
            )

        medals = {
            1: "🥇",
            2: "🥈",
            3: "🥉",
        }

        lines: list[str] = []

        for position, record in enumerate(
            records,
            start=1,
        ):
            user_id = int(record["user_id"])
            member = guild.get_member(user_id)

            member_text = (
                member.mention
                if member is not None
                else f"<@{user_id}>"
            )

            prefix = medals.get(
                position,
                f"**{position}.**",
            )

            total_xp = int(record["total_xp"] or 0)
            wallet = int(record["wallet"] or 0)

            if ranking_type == "money":
                value = f"**{format_number(wallet)} pièces**"
            else:
                level = level_from_xp(total_xp)

                value = (
                    f"niveau **{level}** — "
                    f"**{format_number(total_xp)} XP**"
                )

            lines.append(
                f"{prefix} {member_text} — {value}"
            )

        return base_embed(
            title,
            "\n".join(lines),
        )

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        guild = message.guild

        if guild is None:
            return

        if message.author.bot:
            return

        if message.webhook_id is not None:
            return

        try:
            settings = await self.get_settings(guild.id)

            if not settings["enabled"]:
                return

            if not isinstance(message.author, discord.Member):
                return

            xp_multiplier = await self.get_member_xp_multiplier(
                message.author
            )

            result = await self.award_message(
                guild_id=guild.id,
                user_id=message.author.id,
                settings=settings,
                xp_multiplier=xp_multiplier,
            )

            if result is None:
                return

            granted_roles = await self.grant_earned_level_roles(
                message.author,
                int(result["new_level"]),
            )

            if result["new_level"] <= result["old_level"]:
                return

            if not settings["level_notifications"]:
                return

            roles_text = ""

            if granted_roles:
                roles_text = (
                    "\n🎭 Rôle(s) débloqué(s) : "
                    + ", ".join(
                        role.mention
                        for role in granted_roles
                    )
                )

            multiplier = Decimal(
                str(result["xp_multiplier"])
            )

            multiplier_text = ""

            if multiplier > Decimal("1.00"):
                multiplier_text = (
                    "\n✨ Multiplicateur de rôle : "
                    f"**x{multiplier.normalize()}**"
                )

            embed = success_embed(
                "Niveau supérieur !",
                (
                    f"{message.author.mention} vient d'atteindre "
                    f"le **niveau {result['new_level']}** !\n\n"
                    f"✨ XP gagné : **{result['xp_gain']}**\n"
                    f"💰 Argent gagné : "
                    f"**{result['coins_gain']} pièces**"
                    f"{multiplier_text}"
                    f"{roles_text}"
                ),
            )

            try:
                await message.channel.send(embed=embed)
            except discord.HTTPException:
                LOGGER.debug(
                    "Impossible d'envoyer la notification de niveau.",
                    exc_info=True,
                )

        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'attribuer la récompense de message "
                    "à %s dans le serveur %s"
                ),
                message.author.id,
                guild.id,
            )

    @app_commands.command(
        name="progression",
        description="Affiche ton niveau, ton XP et ton argent.",
    )
    @app_commands.describe(
        membre="Membre dont tu veux consulter la progression."
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        4.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def progression(
        self,
        interaction: discord.Interaction,
        membre: discord.Member | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Serveur requis",
                    "Cette commande doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        selected_member = (
            membre
            if membre is not None
            else interaction.user
        )

        try:
            progression_file = await self.build_progression_card(
                member=selected_member,
                guild_id=guild.id,
            )
        except Exception:
            LOGGER.exception(
                "Impossible de générer la carte de progression de %s",
                selected_member.id,
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Erreur de génération",
                    (
                        "La carte de progression n'a pas pu être générée. "
                        "Consulte les logs du bot."
                    ),
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(color=COLOR)
        embed.set_image(
            url=f"attachment://{progression_file.filename}"
        )

        view = ProgressionView(
            cog=self,
            owner_id=interaction.user.id,
            guild_id=guild.id,
        )

        await interaction.followup.send(
            embed=embed,
            file=progression_file,
            view=view,
            ephemeral=True,
        )

    @app_commands.command(
        name="progression-admin",
        description="Ouvre le panneau administratif de la progression.",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.guild_only()
    async def progression_admin(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    "Cette commande doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        settings = await self.get_settings(
            guild.id,
            use_cache=False,
        )

        embed = base_embed(
            "⚙️ Administration de la progression",
            (
                "Configure le gain automatique d'XP et d'argent, "
                "ou sélectionne un membre pour modifier sa progression.\n\n"
                f"🎙️ Le vocal rapporte actuellement "
                f"**{settings['voice_xp_per_minute']} XP "
                "par minute**, sans argent."
            ),
        )

        embed.add_field(
            name="Système",
            value=(
                "Activé ✅"
                if settings["enabled"]
                else "Désactivé ❌"
            ),
            inline=True,
        )

        embed.add_field(
            name="Cooldown messages",
            value=f"**{settings['cooldown_seconds']} secondes**",
            inline=True,
        )

        embed.add_field(
            name="Notifications",
            value=(
                "Activées ✅"
                if settings["level_notifications"]
                else "Désactivées ❌"
            ),
            inline=True,
        )

        embed.add_field(
            name="🎙️ XP vocal",
            value=(
                f"**{settings['voice_xp_per_minute']} XP/minute**\n"
                "Minimum 2 membres actifs."
            ),
            inline=False,
        )

        view = ProgressionAdminView(
            cog=self,
            owner_id=interaction.user.id,
            guild_id=guild.id,
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    cog = ProgressionCog(bot)

    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info(
        "Système permanent d'XP et d'argent initialisé"
    )
