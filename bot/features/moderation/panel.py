"""Panneau /moderation-admin : tous les réglages de la modération."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.features.moderation.automod import clean_words, desired_rules
from bot.features.moderation.core import (
    escalation_to_text,
    parse_escalation,
    steps_from_json,
    steps_to_json,
)

PANEL_COLOR = discord.Color.from_rgb(102, 179, 255)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)


def on_off(value: bool) -> str:
    return "✅ Activé" if value else "❌ Désactivé"


def panel_embed(settings: dict[str, Any]) -> discord.Embed:
    automod = settings["automod"]
    steps = steps_from_json(settings["escalation"])

    embed = discord.Embed(
        title="🛡️ Administration de la modération",
        description=(
            "Règle ici le journal, les contestations, l'échelle de sanctions "
            "automatiques et la modération automatique."
        ),
        color=PANEL_COLOR,
    )
    embed.add_field(
        name="📋 Journal",
        value=(
            f"<#{settings['log_channel_id']}>"
            if settings["log_channel_id"]
            else "Aucun salon : les sanctions ne sont pas journalisées."
        ),
        inline=True,
    )
    embed.add_field(
        name="📨 Contestations",
        value=(
            f"Reçues dans <#{settings['appeal_channel_id']}>"
            if settings["appeal_channel_id"]
            else "❌ Désactivées"
        ),
        inline=True,
    )
    embed.add_field(
        name=f"⚡ Échelle (avertissements des {settings['warn_expiry_days']} derniers jours)",
        value=(
            "\n".join(f"**{step.warns}** → {step.describe()}" for step in steps)
            or "Aucune sanction automatique."
        ),
        inline=False,
    )

    words = automod.get("words") or []
    spam = int(automod.get("spam_messages") or 0)
    mentions = int(automod.get("mention_limit") or 0)

    embed.add_field(
        name="🤖 Modération automatique",
        value="\n".join(
            [
                f"🔗 Liens d'invitation : {on_off(bool(automod.get('invites')))}",
                f"🚫 Mots interdits : {f'✅ {len(words)} mot(s)' if words else '❌ Aucun'}",
                (
                    f"📣 Mentions de masse : ✅ {mentions} mentions max"
                    if mentions
                    else "📣 Mentions de masse : ❌ Désactivé"
                ),
                (
                    f"💬 Anti-spam : ✅ {spam} messages en {automod['spam_seconds']} s "
                    f"→ exclusion {automod['spam_mute_minutes']} min"
                    if spam
                    else "💬 Anti-spam : ❌ Désactivé"
                ),
            ]
        ),
        inline=False,
    )
    embed.set_footer(
        text=(
            "Les filtres utilisent l'AutoMod de Discord : le message est bloqué "
            "avant d'être publié, puis le bot ajoute un avertissement."
        )
    )

    return embed


def moderation(interaction: discord.Interaction):
    return interaction.client.get_cog("ModerationCog")


def automod_cog(interaction: discord.Interaction):
    return interaction.client.get_cog("AutomodCog")


async def save_automod(
    interaction: discord.Interaction,
    changes: dict[str, Any],
) -> None:
    """Enregistre les réglages AutoMod puis synchronise les règles Discord."""
    repository = moderation(interaction).repository
    settings = await repository.get_settings(interaction.guild_id)
    automod = dict(settings["automod"])
    automod.update(changes)
    await repository.update_settings(interaction.guild_id, automod=automod)

    await interaction.response.defer(ephemeral=True, thinking=True)
    error = await automod_cog(interaction).sync_rules(interaction.guild)
    settings = await repository.get_settings(interaction.guild_id)

    if error:
        await interaction.followup.send(
            embed=discord.Embed(
                title="⚠️ Réglage enregistré, mais pas appliqué partout",
                description=error,
                color=ERROR_COLOR,
            ),
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        content="✅ Réglage enregistré.",
        embed=panel_embed(settings),
        ephemeral=True,
    )


class EscalationModal(discord.ui.Modal, title="Échelle de sanctions"):
    def __init__(self, settings: dict[str, Any]) -> None:
        super().__init__(timeout=600)
        self.steps = discord.ui.TextInput(
            label="Un palier par ligne (vide = aucune)",
            style=discord.TextStyle.paragraph,
            default=escalation_to_text(steps_from_json(settings["escalation"])),
            placeholder="3 = mute 1h\n5 = kick\n7 = ban 7j\n9 = ban",
            required=False,
            max_length=500,
        )
        self.expiry = discord.ui.TextInput(
            label="Un avertissement compte pendant (jours)",
            default=str(settings["warn_expiry_days"]),
            max_length=4,
        )
        self.add_item(self.steps)
        self.add_item(self.expiry)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            steps = parse_escalation(str(self.steps.value or ""))
            days = int(str(self.expiry.value).strip())

            if not 1 <= days <= 3650:
                raise ValueError("La durée de validité doit être entre 1 et 3650 jours.")
        except ValueError as error:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"❌ {error}", color=ERROR_COLOR),
                ephemeral=True,
            )
            return

        repository = moderation(interaction).repository
        await repository.update_settings(
            interaction.guild_id,
            escalation=steps_to_json(steps),
            warn_expiry_days=days,
        )
        await interaction.response.send_message(
            content="✅ Échelle enregistrée.",
            embed=panel_embed(await repository.get_settings(interaction.guild_id)),
            ephemeral=True,
        )


class WordsModal(discord.ui.Modal, title="Mots interdits"):
    def __init__(self, words: list[str]) -> None:
        super().__init__(timeout=600)
        self.words = discord.ui.TextInput(
            label="Séparés par des virgules (vide = désactiver)",
            style=discord.TextStyle.paragraph,
            default=", ".join(words)[:4000],
            placeholder="mot1, mot2, *morceau*",
            required=False,
            max_length=4000,
        )
        self.add_item(self.words)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await save_automod(interaction, {"words": clean_words(str(self.words.value or ""))})


class NumbersModal(discord.ui.Modal):
    """Formulaire de réglages numériques (mentions, anti-spam)."""

    def __init__(
        self,
        *,
        title: str,
        fields: list[tuple[str, str, str, int, int]],
    ) -> None:
        super().__init__(title=title, timeout=600)
        self.specs = fields
        self.inputs: list[discord.ui.TextInput] = []

        for _, label, default, _, _ in fields:
            text_input = discord.ui.TextInput(label=label, default=default, max_length=4)
            self.inputs.append(text_input)
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        changes: dict[str, int] = {}

        for (key, label, _, minimum, maximum), text_input in zip(self.specs, self.inputs):
            try:
                value = int(str(text_input.value).strip())
            except ValueError:
                value = -1

            if not minimum <= value <= maximum:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"❌ « {label} » doit être entre {minimum} et {maximum}.",
                        color=ERROR_COLOR,
                    ),
                    ephemeral=True,
                )
                return

            changes[key] = value

        await save_automod(interaction, changes)


class ChannelPicker(discord.ui.ChannelSelect):
    def __init__(self, setting: str) -> None:
        super().__init__(
            placeholder="Choisis un salon…",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )
        self.setting = setting

    async def callback(self, interaction: discord.Interaction) -> None:
        channel = self.values[0]
        resolved = interaction.guild.get_channel(channel.id)
        me = interaction.guild.me

        if resolved is None or not resolved.permissions_for(me).send_messages:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Je ne peux pas écrire dans {channel.mention}.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        repository = moderation(interaction).repository
        await repository.update_settings(interaction.guild_id, **{self.setting: channel.id})
        automod = automod_cog(interaction)

        if automod is not None:
            automod.forget_settings(interaction.guild_id)

        await interaction.response.edit_message(
            content="✅ Salon enregistré.",
            embed=panel_embed(await repository.get_settings(interaction.guild_id)),
            view=None,
        )


class DisableAppealsButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Désactiver les contestations", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction) -> None:
        repository = moderation(interaction).repository
        await repository.update_settings(interaction.guild_id, appeal_channel_id=None)
        await interaction.response.edit_message(
            content="✅ Contestations désactivées : les messages privés n'auront plus le bouton.",
            embed=panel_embed(await repository.get_settings(interaction.guild_id)),
            view=None,
        )


class OwnerView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float = 600) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            "❌ Ce panneau appartient à un autre administrateur.",
            ephemeral=True,
        )
        return False


class ModerationPanel(OwnerView):
    async def settings(self, interaction: discord.Interaction) -> dict[str, Any]:
        return await moderation(interaction).repository.get_settings(interaction.guild_id)

    async def pick_channel(
        self,
        interaction: discord.Interaction,
        setting: str,
        text: str,
        *,
        with_disable: bool = False,
    ) -> None:
        view = OwnerView(interaction.user.id, timeout=180)
        view.add_item(ChannelPicker(setting))

        if with_disable:
            view.add_item(DisableAppealsButton())

        await interaction.response.send_message(text, view=view, ephemeral=True)

    @discord.ui.button(label="Salon du journal", emoji="📋", row=0)
    async def log_channel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.pick_channel(
            interaction,
            "log_channel_id",
            "📋 Choisis le salon où seront publiées toutes les sanctions (réservé à l'équipe, de préférence).",
        )

    @discord.ui.button(label="Contestations", emoji="📨", row=0)
    async def appeal_channel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.pick_channel(
            interaction,
            "appeal_channel_id",
            "📨 Choisis le salon (réservé à l'équipe) où arriveront les contestations. "
            "Les membres sanctionnés auront alors un bouton « Contester » dans leur message privé.",
            with_disable=True,
        )

    @discord.ui.button(label="Échelle de sanctions", emoji="⚡", row=0)
    async def escalation(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(EscalationModal(await self.settings(interaction)))

    @discord.ui.button(label="Liens d'invitation", emoji="🔗", row=1)
    async def invites(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        settings = await self.settings(interaction)
        await save_automod(interaction, {"invites": not settings["automod"].get("invites")})

    @discord.ui.button(label="Mots interdits", emoji="🚫", row=1)
    async def words(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        settings = await self.settings(interaction)
        await interaction.response.send_modal(WordsModal(settings["automod"].get("words") or []))

    @discord.ui.button(label="Mentions de masse", emoji="📣", row=1)
    async def mentions(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        automod = (await self.settings(interaction))["automod"]
        await interaction.response.send_modal(
            NumbersModal(
                title="Mentions de masse",
                fields=[
                    (
                        "mention_limit",
                        "Mentions max par message (0 = désactiver)",
                        str(automod.get("mention_limit") or 0),
                        0,
                        50,
                    ),
                ],
            )
        )

    @discord.ui.button(label="Anti-spam", emoji="💬", row=1)
    async def antispam(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        automod = (await self.settings(interaction))["automod"]
        await interaction.response.send_modal(
            NumbersModal(
                title="Anti-spam",
                fields=[
                    ("spam_messages", "Messages (0 = désactiver)", str(automod["spam_messages"]), 0, 50),
                    ("spam_seconds", "En combien de secondes", str(automod["spam_seconds"]), 2, 60),
                    ("spam_mute_minutes", "Minutes d'exclusion", str(automod["spam_mute_minutes"]), 1, 1440),
                ],
            )
        )

    @discord.ui.button(label="Actualiser", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=panel_embed(await self.settings(interaction)), view=self)


class ModerationPanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="moderation-admin", description="Règle le journal, les contestations, l'échelle et l'AutoMod.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def moderation_admin(self, interaction: discord.Interaction) -> None:
        cog = self.bot.get_cog("ModerationCog")
        settings = await cog.repository.get_settings(interaction.guild_id)

        # Si une règle a été supprimée à la main dans Discord, la
        # recréer au prochain enregistrement : signalé dans le panneau.
        desired = {key for key, rule in desired_rules(settings["automod"]).items() if rule}
        missing = desired - set(settings["automod_rule_ids"])

        await interaction.response.send_message(
            content=(
                "⚠️ Certains filtres ne sont pas encore actifs dans Discord : "
                "modifie un réglage pour les recréer."
                if missing
                else None
            ),
            embed=panel_embed(settings),
            view=ModerationPanel(interaction.user.id),
            ephemeral=True,
        )
