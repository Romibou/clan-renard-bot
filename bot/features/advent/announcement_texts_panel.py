"""
Panneau « Textes des annonces » de /avent-admin : texte par défaut,
message de la dernière case, messages spéciaux par jour, jours avec
@everyone, aperçu d'un jour, retour aux textes d'origine.
"""

from __future__ import annotations

import logging
from typing import Any

import discord

from bot.features.advent.announcement_texts import (
    DEFAULT_LAST_MESSAGE,
    DEFAULT_MESSAGE,
    DEFAULT_TITLE,
    LAST_DAY,
    MAX_MESSAGE,
    MAX_TITLE,
    VARIABLES_HELP,
    AnnouncementTexts,
    AnnouncementTextsRepository,
    build_announcement,
    format_days,
    parse_days,
)
from bot.shared.embeds import base_embed
from bot.shared.panels import first_value, reset_selection, send_panel

LOGGER = logging.getLogger(__name__)

ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


def shorten(text: str, limit: int = 180) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def labeled(modal: discord.ui.Modal, label: str, default: str | None, *, description: str | None = None,
            paragraph: bool = False, max_length: int = 200, required: bool = False) -> discord.ui.TextInput:
    component = discord.ui.TextInput(
        style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short,
        default=(default or "")[:max_length] or None,
        max_length=max_length,
        required=required,
    )
    modal.add_item(discord.ui.Label(text=label, description=description, component=component))
    return component


# ============================================================
# FENÊTRES
# ============================================================


class TextsModal(discord.ui.Modal):
    def __init__(self, panel: TextsPanel, title: str) -> None:
        super().__init__(title=title, timeout=600)
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            notice = self.apply()
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        await self.panel.save_and_refresh(interaction, notice)

    def apply(self) -> str:
        raise NotImplementedError


class DefaultTextsModal(TextsModal):
    def __init__(self, panel: TextsPanel) -> None:
        super().__init__(panel, "✏️ Texte par défaut des annonces")
        texts = panel.texts
        self.title_input = labeled(
            self, "Titre", texts.title or DEFAULT_TITLE, max_length=MAX_TITLE,
            description="Vide = titre d'origine. Variables : {jour} {titre} {serveur}…",
        )
        self.message = labeled(
            self, "Message (tous les jours)", texts.message or DEFAULT_MESSAGE,
            paragraph=True, max_length=MAX_MESSAGE, description="Vide = message d'origine.",
        )
        self.last_message = labeled(
            self, f"Message de la dernière case ({LAST_DAY})", texts.last_message or DEFAULT_LAST_MESSAGE,
            paragraph=True, max_length=MAX_MESSAGE, description="Vide = message d'origine.",
        )
        self.opening = discord.ui.Select(
            options=[
                discord.SelectOption(label="Afficher l'heure d'ouverture", value="yes", emoji="🕒",
                                     default=texts.show_opening),
                discord.SelectOption(label="Ne pas l'afficher", value="no", emoji="🚫",
                                     default=not texts.show_opening),
            ]
        )
        self.add_item(discord.ui.Label(text="Encart « Ouverture » sous le message", component=self.opening))

    def apply(self) -> str:
        texts = self.panel.texts

        def clean(value: str, default: str) -> str | None:
            value = value.strip()
            return None if not value or value == default else value

        texts.title = clean(self.title_input.value, DEFAULT_TITLE)
        texts.message = clean(self.message.value, DEFAULT_MESSAGE)
        texts.last_message = clean(self.last_message.value, DEFAULT_LAST_MESSAGE)
        texts.show_opening = first_value(self.opening, "yes") == "yes"
        return "✏️ Texte par défaut enregistré."


class DayMessageModal(TextsModal):
    def __init__(self, panel: TextsPanel, day: int) -> None:
        super().__init__(panel, f"📅 Message spécial du jour {day}")
        self.day = day
        current = panel.texts.day_messages.get(day)
        self.message = labeled(
            self, f"Message du jour {day}", current, paragraph=True, max_length=MAX_MESSAGE,
            description="Remplace le message par défaut ce jour-là. Vide = message par défaut.",
        )

    def apply(self) -> str:
        text = self.message.value.strip()

        if text:
            self.panel.texts.day_messages[self.day] = text
            return f"📅 Message spécial du jour {self.day} enregistré."

        self.panel.texts.day_messages.pop(self.day, None)
        return f"📅 Le jour {self.day} reprend le message par défaut."


class EveryoneDaysModal(TextsModal):
    def __init__(self, panel: TextsPanel) -> None:
        super().__init__(panel, "📢 Jours avec @everyone")
        self.days = labeled(
            self, "Jours où mentionner @everyone", format_days(panel.texts.everyone_days),
            description="Par exemple : 1, 24. Les autres jours, le rôle choisi (ou personne). Vide = jamais.",
            max_length=100,
        )

    def apply(self) -> str:
        self.panel.texts.everyone_days = parse_days(self.days.value)
        days = self.panel.texts.everyone_days
        notice = f"📢 @everyone les jours : {format_days(days)}." if days else "📢 @everyone n'est plus utilisé."
        warning = self.panel.everyone_warning()
        return f"{notice}\n{warning}" if warning and days else notice


# ============================================================
# PANNEAU
# ============================================================


def day_options(texts: AnnouncementTexts, special_marker: bool) -> list[discord.SelectOption]:
    options = []

    for day in range(1, LAST_DAY + 1):
        marks = []

        if special_marker and day in texts.day_messages:
            marks.append("message spécial")
        if day in texts.everyone_days:
            marks.append("@everyone")

        options.append(
            discord.SelectOption(
                label=f"Jour {day}",
                value=str(day),
                emoji="✏️" if special_marker and day in texts.day_messages else None,
                description=", ".join(marks) or None,
            )
        )

    return options


class TextsPanel(discord.ui.View):
    def __init__(
        self,
        *,
        campaign: Any,
        texts: AnnouncementTexts,
        repository: AnnouncementTextsRepository,
        owner_id: int,
        guild: discord.Guild,
    ) -> None:
        super().__init__(timeout=900)
        self.campaign = campaign
        self.texts = texts
        self.repository = repository
        self.owner_id = owner_id
        self.guild = guild
        self.confirm_reset = False
        self.build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Seul l'administrateur qui a ouvert ce panneau peut l'utiliser."),
                ephemeral=True,
            )
            return False

        return True

    def everyone_warning(self) -> str | None:
        channel = self.guild.get_channel(self.campaign.channel_id or 0)

        if channel is None or self.guild.me is None:
            return None

        if not channel.permissions_for(self.guild.me).mention_everyone:
            return (
                f"⚠️ Il me manque la permission « Mentionner @everyone » dans {channel.mention} : "
                "la mention ne notifiera personne."
            )

        return None

    # -------- affichage --------

    def embed(self, notice: str | None = None) -> discord.Embed:
        texts = self.texts
        role = self.guild.get_role(self.campaign.announcement_role_id or 0)
        lines = [
            f"Campagne **{self.campaign.year}** · annonces "
            f"**{'activées ✅' if self.campaign.announcements_enabled else 'désactivées ❌'}**",
            f"Mention habituelle : {role.mention if role else 'aucune'}"
            + (f" · @everyone les jours **{format_days(texts.everyone_days)}**" if texts.everyone_days else ""),
            "",
            f"**Titre :** {shorten(texts.title or DEFAULT_TITLE, 120)}"
            + ("" if texts.title else " *(d'origine)*"),
            f"**Message :** {shorten(texts.message or DEFAULT_MESSAGE)}" + ("" if texts.message else " *(d'origine)*"),
            f"**Jour {LAST_DAY} :** {shorten(texts.last_message or DEFAULT_LAST_MESSAGE)}"
            + ("" if texts.last_message else " *(d'origine)*"),
            f"**Encart « Ouverture » :** {'affiché' if texts.show_opening else 'masqué'}",
        ]

        if texts.day_messages:
            lines += ["", "**Messages spéciaux :**"]
            lines += [
                f"• Jour {day} : {shorten(text, 90)}" for day, text in sorted(texts.day_messages.items())
            ]

        if self.confirm_reset:
            lines += ["", "⚠️ Clique encore sur **Textes d'origine** pour tout effacer."]

        if notice:
            lines += ["", *[f"> {line}" for line in notice.split("\n")]]

        embed = base_embed("📝 Textes des annonces de l'Avent", "\n".join(lines)[:4096])
        embed.add_field(name="Variables", value=VARIABLES_HELP, inline=False)
        return embed

    def build(self) -> None:
        self.clear_items()

        edit_day = discord.ui.Select(
            placeholder="📅 Écrire le message spécial d'un jour…",
            options=day_options(self.texts, True),
            row=0,
        )
        edit_day.callback = self.on_edit_day
        self.add_item(edit_day)

        preview = discord.ui.Select(
            placeholder="👁️ Voir l'aperçu de l'annonce d'un jour…",
            options=day_options(self.texts, True),
            row=1,
        )
        preview.callback = self.on_preview
        self.add_item(preview)

        def button(label: str, emoji: str, callback, style=discord.ButtonStyle.secondary) -> None:
            item = discord.ui.Button(label=label, emoji=emoji, style=style, row=2)
            item.callback = callback
            self.add_item(item)

        button("Texte par défaut", "✏️", self.on_default, discord.ButtonStyle.primary)
        button("Jours @everyone", "📢", self.on_everyone)
        button(
            "Confirmer ?" if self.confirm_reset else "Textes d'origine",
            "⚠️" if self.confirm_reset else "🔄",
            self.on_reset,
            discord.ButtonStyle.danger,
        )

    async def save_and_refresh(self, interaction: discord.Interaction, notice: str | None) -> None:
        await self.repository.save(self.campaign.id, self.texts)
        self.confirm_reset = False
        self.build()
        await interaction.response.edit_message(embed=self.embed(notice), view=self)

    # -------- actions --------

    async def on_default(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(DefaultTextsModal(self))

    async def on_everyone(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(EveryoneDaysModal(self))

    async def on_edit_day(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(DayMessageModal(self, int(interaction.data["values"][0])))
        await reset_selection(self)

    async def on_preview(self, interaction: discord.Interaction) -> None:
        day = int(interaction.data["values"][0])
        role = self.guild.get_role(self.campaign.announcement_role_id or 0)
        announcement = build_announcement(
            campaign=self.campaign, day=day, texts=self.texts, guild_name=self.guild.name, role=role
        )
        content = announcement["content"]
        header = f"-# 👁️ Aperçu de l'annonce du jour {day}, visible par toi seul (les boutons du calendrier seront dessous)"
        await interaction.response.send_message(
            content=f"{header}\n{content}" if content else header,
            embed=announcement["embed"],
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )
        await reset_selection(self)

    async def on_reset(self, interaction: discord.Interaction) -> None:
        if not self.confirm_reset:
            self.confirm_reset = True
            self.build()
            await interaction.response.edit_message(embed=self.embed(), view=self)
            return

        await self.repository.reset(self.campaign.id)
        self.texts = AnnouncementTexts()
        self.confirm_reset = False
        self.build()
        await interaction.response.edit_message(
            embed=self.embed("🔄 Tous les textes sont revenus à ceux d'origine."), view=self
        )


async def open_texts_panel(interaction: discord.Interaction, campaign: Any) -> None:
    repository = AnnouncementTextsRepository(lambda: interaction.client.database.require_pool())
    texts = await repository.get(campaign.id)
    panel = TextsPanel(
        campaign=campaign,
        texts=texts,
        repository=repository,
        owner_id=interaction.user.id,
        guild=interaction.guild,
    )
    await send_panel(interaction, embed=panel.embed(), view=panel)
