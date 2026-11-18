"""
Anniversaires.

Membres : /anniversaire ouvre un panneau privé pour enregistrer,
modifier ou retirer sa date (année facultative), choisir d'afficher
son âge ou non, et voir les prochains anniversaires du serveur.

Admins : /anniversaire-admin règle le salon des souhaits, l'heure,
le message, la carte (même style que la bienvenue), le rôle donné
pour la journée et un cadeau en pièces / XP.

Le jour J (heure de Paris), à l'heure choisie, le bot souhaite
l'anniversaire, donne le rôle (retiré automatiquement le lendemain)
et le cadeau. Une seule célébration par membre et par an, même si la
date est modifiée. Né un 29 février : fêté le 28 les années non
bissextiles.
"""

from __future__ import annotations

import asyncio
import calendar
import re
import io
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.shared.economy import credit_progression, refresh_level_roles
from bot.shared.members import present_member_ids
from bot.shared.panels import reset_selection, send_panel
from bot.shared.welcome_card import render_welcome_card

LOGGER = logging.getLogger(__name__)

PARIS = ZoneInfo("Europe/Paris")
COLOR = discord.Color.from_rgb(255, 154, 213)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
MIN_YEAR = 1900
CHANGE_COOLDOWN = timedelta(days=30)  # une modification de date tous les 30 jours
MAX_REWARD = 1_000_000

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "channel_id": None,
    "role_id": None,
    "hour": 9,
    "message": "Toute l'équipe de **{serveur}** souhaite un **joyeux anniversaire** à {membre} ! 🎉",
    "card": True,
    # embed = cadre aux couleurs du bot, card = carte image, both = cadre + carte
    "style": "embed",
    "title": "Joyeux anniversaire",
    "subtitle": "{nom}",
    "text": "{age} Passe une super journée !",
    "coins": 0,
    "xp": 0,
}

VARIABLES_HELP = (
    "`{membre}` mention · `{nom}` nom affiché · `{serveur}` nom du serveur\n"
    "`{age}` « 25 ans ! » si le membre a donné son année et accepte de l'afficher, sinon rien"
)


STYLES = ("embed", "card", "both")
STYLE_NAMES = {"embed": "cadre", "card": "carte image", "both": "cadre + carte"}
RENARD_PINK = discord.Color.from_rgb(255, 154, 213)


def build_wishes_embed(member: Any, age: int | None, settings: dict[str, Any], *, now: datetime) -> discord.Embed:
    """Cadre des souhaits, dans le style de Renard Bot."""
    guild = member.guild
    title = fill(settings["title"] or "Joyeux anniversaire", member, age, on_card=True)
    lines = [fill(settings["message"], member, age)]

    if age is not None:
        lines.append(f"🎈 **{age} ans** aujourd'hui !")

    gift = []

    if settings["coins"]:
        gift.append(f"**{format_number(settings['coins'])} pièces**")
    if settings["xp"]:
        gift.append(f"**{format_number(settings['xp'])} XP**")

    if gift:
        lines.append(f"🎁 Cadeau du Clan : {' et '.join(gift)}, profite bien !")

    embed = discord.Embed(
        title=f"🎂 {title} !".replace("! !", "!"),
        description="\n".join(lines)[:4096],
        color=RENARD_PINK,
        timestamp=now,
    )
    icon = guild.icon.url if getattr(guild, "icon", None) else None
    embed.set_author(name=guild.name, icon_url=icon)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"L'équipe {guild.name} 🦊")
    return embed


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


def format_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


# ============================================================
# DATES
# ============================================================


def validate_date(day: int, month: int, year: int | None, today: date) -> None:
    if not 1 <= month <= 12:
        raise ValueError("Le mois doit être entre 1 et 12.")

    # 2000 est bissextile : le 29 février est accepté si l'année n'est pas donnée.
    max_day = calendar.monthrange(year or 2000, month)[1]

    if not 1 <= day <= max_day:
        raise ValueError(
            f"Le {day} {MONTHS[month - 1]} n'existe pas"
            + (f" en {year}." if year else ".")
        )

    if year is not None and not MIN_YEAR <= year <= today.year - 5:
        raise ValueError(f"L'année doit être entre {MIN_YEAR} et {today.year - 5}.")


def celebration_day(day: int, month: int, year: int) -> date:
    """Date fêtée cette année-là (29 février → 28 février hors années bissextiles)."""
    if month == 2 and day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)

    return date(year, month, day)


def next_birthday(day: int, month: int, today: date) -> date:
    this_year = celebration_day(day, month, today.year)
    return this_year if this_year >= today else celebration_day(day, month, today.year + 1)


def age_on(birth_year: int | None, day: int, month: int, on: date) -> int | None:
    if birth_year is None:
        return None

    had_birthday = (on.month, on.day) >= (month, day) or on == celebration_day(day, month, on.year)
    return on.year - birth_year - (0 if had_birthday else 1)


def format_day(day: int, month: int) -> str:
    return f"{day} {MONTHS[month - 1]}"


def parse_int(text: str, name: str) -> int:
    cleaned = text.strip()

    if not cleaned.isdigit():
        raise ValueError(f"{name} : écris un nombre.")

    return int(cleaned)


def fill(template: str, member: Any, age: int | None, *, on_card: bool = False) -> str:
    age_text = f"{age} ans !" if age is not None else ""
    text = (
        template.replace("{membre}", member.display_name if on_card else member.mention)
        .replace("{nom}", member.display_name)
        .replace("{serveur}", member.guild.name)
        .replace("{age}", age_text)
    )
    # « {age} » vide ne doit pas laisser de double espace.
    return re.sub(r" {2,}", " ", text).strip()


@dataclass
class Birthday:
    day: int
    month: int
    year: int | None
    show_age: bool
    updated_at: datetime | None
    last_celebrated_year: int

    def shown_age(self, on: date) -> int | None:
        return age_on(self.year, self.day, self.month, on) if self.show_age else None


# ============================================================
# PANNEAU MEMBRE
# ============================================================


class BirthdayModal(discord.ui.Modal):
    def __init__(self, panel: MemberPanel) -> None:
        super().__init__(title="🎂 Mon anniversaire", timeout=600)
        self.panel = panel
        current = panel.birthday

        def field(label: str, value: Any, placeholder: str, description: str | None = None,
                  required: bool = True, max_length: int = 2) -> discord.ui.TextInput:
            component = discord.ui.TextInput(
                default=str(value) if value is not None else None,
                placeholder=placeholder,
                required=required,
                max_length=max_length,
            )
            self.add_item(discord.ui.Label(text=label, description=description, component=component))
            return component

        self.day = field("Jour", current.day if current else None, "25")
        self.month = field("Mois (en chiffre)", current.month if current else None, "12",
                           description="1 = janvier … 12 = décembre")
        self.year = field(
            "Année de naissance (facultatif)", current.year if current else None, "2005",
            description="Seulement pour afficher ton âge. Tu peux la laisser vide.",
            required=False, max_length=4,
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            day = parse_int(self.day.value, "Jour")
            month = parse_int(self.month.value, "Mois")
            year = parse_int(self.year.value, "Année") if self.year.value.strip() else None
            validate_date(day, month, year, datetime.now(PARIS).date())
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        await self.panel.save(interaction, day, month, year)


class MemberPanel(discord.ui.View):
    def __init__(self, cog: BirthdayCog, member: discord.Member, birthday: Birthday | None) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.member = member
        self.birthday = birthday
        self.confirm_remove = False
        self.build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.member.id

    def embed(self, notice: str | None = None) -> discord.Embed:
        today = datetime.now(PARIS).date()
        lines = []

        if self.birthday is None:
            lines.append("Tu n'as pas encore enregistré ton anniversaire.")
            lines.append("Clique sur **🎂 Enregistrer** : le serveur pourra te le souhaiter le jour J !")
        else:
            b = self.birthday
            upcoming = next_birthday(b.day, b.month, today)
            stamp = int(datetime.combine(upcoming, time(0, 0), tzinfo=PARIS).timestamp())
            lines.append(f"🎂 Ton anniversaire : **{format_day(b.day, b.month)}**")

            if b.year:
                age = age_on(b.year, b.day, b.month, upcoming)
                lines.append(
                    f"🎈 Tu auras **{age} ans** · âge {'visible ✅' if b.show_age else 'caché 🙈'} dans les souhaits"
                )
            else:
                lines.append("🎈 Année non renseignée : ton âge ne sera pas affiché.")

            if upcoming == today:
                lines.append("🥳 **C'est aujourd'hui ! Joyeux anniversaire !**")
            else:
                lines.append(f"⏳ Prochain anniversaire <t:{stamp}:R> ({(upcoming - today).days} jours)")

            if b.day == 29 and b.month == 2:
                lines.append("-# Né un 29 février : fêté le 28 février les autres années.")

        if self.confirm_remove:
            lines += ["", "⚠️ Clique encore sur **Retirer** pour confirmer."]

        if notice:
            lines += ["", f"> {notice}"]

        return discord.Embed(title="🎂 Mon anniversaire", description="\n".join(lines), color=COLOR)

    def build(self) -> None:
        self.clear_items()

        def button(label: str, emoji: str, callback, style=discord.ButtonStyle.secondary, disabled=False) -> None:
            item = discord.ui.Button(label=label, emoji=emoji, style=style, disabled=disabled)
            item.callback = callback
            self.add_item(item)

        has = self.birthday is not None
        button("Modifier ma date" if has else "Enregistrer", "🎂", self.on_set, discord.ButtonStyle.primary)

        if has:
            button(
                "Cacher mon âge" if self.birthday.show_age else "Afficher mon âge",
                "🙈" if self.birthday.show_age else "🎈",
                self.on_toggle_age,
                disabled=self.birthday.year is None,
            )
            button(
                "Confirmer ?" if self.confirm_remove else "Retirer",
                "⚠️" if self.confirm_remove else "🗑️",
                self.on_remove,
                discord.ButtonStyle.danger,
            )

        button("Prochains anniversaires", "📅", self.on_upcoming)

    async def refresh(self, interaction: discord.Interaction, notice: str | None = None) -> None:
        self.build()
        await interaction.response.edit_message(embed=self.embed(notice), view=self)

    async def save(self, interaction: discord.Interaction, day: int, month: int, year: int | None) -> None:
        current = self.birthday

        if current is None:
            current = await self.cog.get_birthday(interaction.guild_id, self.member.id, include_removed=True)

        if current is not None and (current.day, current.month, current.year) != (day, month, year):
            if current.updated_at and datetime.now(timezone.utc) - current.updated_at < CHANGE_COOLDOWN:
                allowed = current.updated_at + CHANGE_COOLDOWN
                await interaction.response.send_message(
                    embed=error_embed(
                        "Tu as déjà modifié ta date il y a moins de 30 jours. "
                        f"Prochaine modification possible <t:{int(allowed.timestamp())}:R>. "
                        "En cas d'erreur, demande à un admin."
                    ),
                    ephemeral=True,
                )
                return

        show_age = current.show_age if current else True
        self.birthday = await self.cog.save_birthday(
            interaction.guild_id, self.member.id, day, month, year, show_age
        )
        self.confirm_remove = False
        await self.refresh(interaction, "🎂 Date enregistrée !")

    async def on_set(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BirthdayModal(self))

    async def on_toggle_age(self, interaction: discord.Interaction) -> None:
        if self.birthday is None:
            return

        self.birthday.show_age = not self.birthday.show_age
        await self.cog.set_show_age(interaction.guild_id, self.member.id, self.birthday.show_age)
        await self.refresh(
            interaction,
            "🎈 Ton âge sera affiché dans les souhaits." if self.birthday.show_age else "🙈 Ton âge restera secret.",
        )

    async def on_remove(self, interaction: discord.Interaction) -> None:
        if not self.confirm_remove:
            self.confirm_remove = True
            await self.refresh(interaction)
            return

        await self.cog.delete_birthday(interaction.guild_id, self.member.id)
        self.birthday = None
        self.confirm_remove = False
        await self.refresh(interaction, "🗑️ Ton anniversaire a été retiré.")

    async def on_upcoming(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=await self.cog.upcoming_embed(interaction.guild), ephemeral=True
        )


# ============================================================
# PANNEAU ADMIN
# ============================================================


class AdminModal(discord.ui.Modal):
    def __init__(self, panel: AdminPanel, title: str) -> None:
        super().__init__(title=title, timeout=600)
        self.panel = panel

    def text(self, label: str, value: Any, *, description: str | None = None, paragraph: bool = False,
             max_length: int = 100, required: bool = False) -> discord.ui.TextInput:
        component = discord.ui.TextInput(
            default=str(value)[:max_length] if value not in (None, "") else None,
            style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short,
            max_length=max_length,
            required=required,
        )
        self.add_item(discord.ui.Label(text=label, description=description, component=component))
        return component

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            notice = await self.apply(interaction)
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        await self.panel.cog.save_settings(interaction.guild_id, self.panel.settings)
        await self.panel.refresh(interaction, notice)

    async def apply(self, interaction: discord.Interaction) -> str | None:
        raise NotImplementedError


class ChannelRoleModal(AdminModal):
    def __init__(self, panel: AdminPanel) -> None:
        super().__init__(panel, "📍 Salon et rôle")
        guild = panel.guild
        channel = guild.get_channel(panel.settings["channel_id"] or 0)
        role = guild.get_role(panel.settings["role_id"] or 0)
        self.channel = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            default_values=[channel] if channel else [],
            min_values=1,
            max_values=1,
        )
        self.add_item(discord.ui.Label(text="Salon des souhaits", component=self.channel))
        self.role = discord.ui.RoleSelect(default_values=[role] if role else [], required=False,
                                          min_values=0, max_values=1)
        self.add_item(
            discord.ui.Label(
                text="Rôle donné pour la journée (facultatif)",
                description="Retiré automatiquement le lendemain. Vide = pas de rôle.",
                component=self.role,
            )
        )

    async def apply(self, interaction: discord.Interaction) -> str | None:
        self.panel.settings["channel_id"] = self.channel.values[0].id
        roles = list(self.role.values)
        self.panel.settings["role_id"] = roles[0].id if roles else None
        return self.panel.cog.permission_warning(interaction.guild, self.panel.settings) or "📍 Salon et rôle enregistrés."


class TimeGiftModal(AdminModal):
    def __init__(self, panel: AdminPanel) -> None:
        super().__init__(panel, "⏰ Heure et cadeau")
        settings = panel.settings
        self.hour = self.text("Heure des souhaits (0 à 23, Paris)", settings["hour"], max_length=2, required=True)
        self.coins = self.text("Pièces offertes", settings["coins"], max_length=8, required=True,
                               description="0 = pas de pièces.")
        self.xp = self.text("XP offerte", settings["xp"], max_length=8, required=True, description="0 = pas d'XP.")

    async def apply(self, interaction: discord.Interaction) -> str | None:
        hour = parse_int(self.hour.value, "Heure")

        if not 0 <= hour <= 23:
            raise ValueError("L'heure doit être entre 0 et 23.")

        coins = parse_int(self.coins.value, "Pièces")
        xp = parse_int(self.xp.value, "XP")

        if coins > MAX_REWARD or xp > MAX_REWARD:
            raise ValueError(f"{format_number(MAX_REWARD)} maximum.")

        self.panel.settings.update(hour=hour, coins=coins, xp=xp)
        return "⏰ Heure et cadeau enregistrés."


class TextsModal(AdminModal):
    def __init__(self, panel: AdminPanel) -> None:
        super().__init__(panel, "✏️ Message et carte")
        settings = panel.settings
        self.message = self.text("Message", settings["message"], paragraph=True, max_length=1500, required=True,
                                 description="Variables : {membre} {nom} {serveur} {age}")
        self.title_input = self.text("Titre (cadre et carte)", settings["title"], max_length=40)
        self.subtitle = self.text("Sous-titre de la carte", settings["subtitle"], max_length=60)
        self.bottom = self.text("Texte du bas de la carte", settings["text"], max_length=100)

    async def apply(self, interaction: discord.Interaction) -> str | None:
        self.panel.settings.update(
            message=self.message.value.strip(),
            title=self.title_input.value.strip(),
            subtitle=self.subtitle.value.strip(),
            text=self.bottom.value.strip(),
        )
        return "✏️ Textes enregistrés."


class BackgroundModal(AdminModal):
    def __init__(self, panel: AdminPanel) -> None:
        super().__init__(panel, "🖼️ Fond de la carte")
        self.file = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.add_item(discord.ui.Label(text="Nouvelle image de fond", component=self.file,
                                       description="Recadrée en 1024 × 500. Vide = garder le fond actuel."))
        self.choice = discord.ui.Select(
            options=[
                discord.SelectOption(label="Garder le fond actuel", value="keep", default=True),
                discord.SelectOption(label="Revenir au fond par défaut", value="default"),
            ]
        )
        self.add_item(discord.ui.Label(text="Sans nouvelle image", component=self.choice))

    async def apply(self, interaction: discord.Interaction) -> str | None:
        from bot.extensions.bienvenue import MAX_BACKGROUND_BYTES, prepare_background

        files = list(self.file.values)

        if files:
            attachment = files[0]

            if not (attachment.content_type or "").startswith("image/"):
                raise ValueError(f"« {attachment.filename} » n'est pas une image.")
            if attachment.size > MAX_BACKGROUND_BYTES:
                raise ValueError("Image trop lourde.")

            try:
                self.panel.background = await asyncio.to_thread(prepare_background, await attachment.read())
            except Exception as error:
                raise ValueError("Impossible de lire cette image.") from error

            await self.panel.cog.save_background(interaction.guild_id, self.panel.background)
            return "🖼️ Nouveau fond enregistré."

        if self.choice.values[0] == "default":
            self.panel.background = None
            await self.panel.cog.save_background(interaction.guild_id, None)
            return "🌅 Retour au fond par défaut."

        return None


class AdminRemoveSelect(discord.ui.UserSelect):
    def __init__(self, cog: BirthdayCog) -> None:
        super().__init__(placeholder="Membre dont retirer l'anniversaire…", min_values=1, max_values=1)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            member = self.values[0]
            removed = await self.cog.delete_birthday(interaction.guild_id, member.id)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=(
                        f"🗑️ Anniversaire de {member.mention} retiré : il pourra en enregistrer un nouveau."
                        if removed
                        else f"{member.mention} n'avait pas d'anniversaire enregistré."
                    ),
                    color=SUCCESS_COLOR,
                ),
                ephemeral=True,
            )
        finally:
            await reset_selection(self.view)


class AdminPanel(discord.ui.View):
    def __init__(self, cog: BirthdayCog, interaction: discord.Interaction, settings: dict, background: bytes | None) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = interaction.user.id
        self.guild: discord.Guild = interaction.guild
        self.settings = settings
        self.background = background
        self.build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Seul l'administrateur qui a ouvert ce panneau peut l'utiliser."), ephemeral=True
            )
            return False
        return True

    def embed(self, notice: str | None = None) -> discord.Embed:
        s = self.settings
        channel = f"<#{s['channel_id']}>" if s["channel_id"] else "*à choisir*"
        role = f"<@&{s['role_id']}>" if s["role_id"] else "aucun"
        gift = []

        if s["coins"]:
            gift.append(f"{format_number(s['coins'])} pièces")
        if s["xp"]:
            gift.append(f"{format_number(s['xp'])} XP")

        lines = [
            f"État : **{'activé ✅' if s['enabled'] else 'désactivé ❌'}** · Salon : {channel}",
            f"Heure : **{s['hour']:02d}:00** (Paris) · Rôle du jour : {role}",
            f"Cadeau : **{' et '.join(gift) if gift else 'aucun'}** · Style : **{STYLE_NAMES.get(s.get('style'), 'cadre')}**",
            "",
            f"**Message :** {s['message']}",
        ]

        if notice:
            lines += ["", f"> {notice}"]

        embed = discord.Embed(title="🎂 Anniversaires — réglages", description="\n".join(lines)[:4096], color=COLOR)
        embed.add_field(name="Variables", value=VARIABLES_HELP, inline=False)
        embed.set_footer(text="Une seule célébration par membre et par an, même si la date change.")
        return embed

    def build(self) -> None:
        self.clear_items()

        def button(label: str, emoji: str, callback, *, row: int, style=discord.ButtonStyle.secondary) -> None:
            item = discord.ui.Button(label=label, emoji=emoji, style=style, row=row)
            item.callback = callback
            self.add_item(item)

        enabled = self.settings["enabled"]
        button("Désactiver" if enabled else "Activer", "⏸️" if enabled else "▶️", self.on_toggle, row=0,
               style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success)
        button("Salon et rôle", "📍", self.on_channel, row=0)
        button("Heure et cadeau", "⏰", self.on_time, row=0)
        button("Message et carte", "✏️", self.on_texts, row=0, style=discord.ButtonStyle.primary)
        button("Fond", "🖼️", self.on_background, row=1)
        button(f"Style : {STYLE_NAMES.get(self.settings.get('style'), 'cadre')}", "🎨", self.on_card, row=1)
        button("Tester dans le salon", "📨", self.on_test, row=1)
        button("Liste", "📋", self.on_list, row=1)
        button("Retirer un membre", "🗑️", self.on_remove_member, row=1, style=discord.ButtonStyle.danger)

    async def refresh(self, interaction: discord.Interaction, notice: str | None = None) -> None:
        self.build()
        await interaction.response.edit_message(embed=self.embed(notice), view=self)

    async def on_toggle(self, interaction: discord.Interaction) -> None:
        if not self.settings["enabled"] and not self.settings["channel_id"]:
            await interaction.response.send_message(
                embed=error_embed("Choisis d'abord le salon avec 📍 **Salon et rôle**."), ephemeral=True
            )
            return

        self.settings["enabled"] = not self.settings["enabled"]
        await self.cog.save_settings(interaction.guild_id, self.settings)
        warning = self.cog.permission_warning(self.guild, self.settings) if self.settings["enabled"] else None
        await self.refresh(interaction, warning or ("✅ Activé." if self.settings["enabled"] else "⏸️ Désactivé."))

    async def on_channel(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ChannelRoleModal(self))

    async def on_time(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TimeGiftModal(self))

    async def on_texts(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TextsModal(self))

    async def on_background(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BackgroundModal(self))

    async def on_card(self, interaction: discord.Interaction) -> None:
        current = self.settings.get("style") if self.settings.get("style") in STYLES else "embed"
        self.settings["style"] = STYLES[(STYLES.index(current) + 1) % len(STYLES)]
        await self.cog.save_settings(interaction.guild_id, self.settings)
        notices = {
            "embed": "🎨 Style **cadre** : mention du membre, cadre rose avec son avatar, âge et cadeau.",
            "card": "🎨 Style **carte image** : le message puis la carte, comme la bienvenue.",
            "both": "🎨 Style **cadre + carte** : le cadre, avec la carte en grande image.",
        }
        await self.refresh(interaction, notices[self.settings["style"]] + " Teste avec 📨.")

    async def on_test(self, interaction: discord.Interaction) -> None:
        if not self.settings["channel_id"]:
            await interaction.response.send_message(
                embed=error_embed("Choisis d'abord le salon avec 📍 **Salon et rôle**."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        birthday = await self.cog.get_birthday(interaction.guild_id, interaction.user.id)
        age = birthday.shown_age(datetime.now(PARIS).date()) if birthday else None
        message = await self.cog.send_wishes(interaction.user, age, self.settings, self.background)
        await interaction.followup.send(
            f"📨 Test envoyé : {message.jump_url}\n-# Ni rôle ni cadeau pendant un test."
            if message
            else "❌ Envoi impossible : " + (self.cog.permission_warning(self.guild, self.settings) or "salon introuvable."),
            ephemeral=True,
        )

    async def on_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=await self.cog.upcoming_embed(interaction.guild, limit=40, title="📋 Tous les anniversaires"),
            ephemeral=True,
        )

    async def on_remove_member(self, interaction: discord.Interaction) -> None:
        view = discord.ui.View(timeout=300)
        view.add_item(AdminRemoveSelect(self.cog))
        await send_panel(
            interaction,
            embed=discord.Embed(
                description="Choisis le membre dont l'anniversaire doit être retiré (date fausse, troll…).",
                color=COLOR,
            ),
            view=view,
        )


# ============================================================
# COG
# ============================================================


class BirthdayCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._running = False

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS birthday_members (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                day SMALLINT NOT NULL CHECK (day BETWEEN 1 AND 31),
                month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
                year SMALLINT,
                show_age BOOLEAN NOT NULL DEFAULT TRUE,
                last_celebrated_year SMALLINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await pool.execute(
            "ALTER TABLE birthday_members ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE"
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS birthday_settings (
                guild_id BIGINT PRIMARY KEY,
                settings JSONB NOT NULL DEFAULT '{}'::JSONB,
                background BYTEA,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS birthday_role_grants (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                granted_on DATE NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

    async def cog_load(self) -> None:
        if not self.loop.is_running():
            self.loop.start()

    def cog_unload(self) -> None:
        self.loop.cancel()

    # -------- données des membres --------

    @staticmethod
    def _record_to_birthday(record: Any) -> Birthday:
        return Birthday(
            day=int(record["day"]),
            month=int(record["month"]),
            year=int(record["year"]) if record["year"] else None,
            show_age=bool(record["show_age"]),
            updated_at=record["updated_at"],
            last_celebrated_year=int(record["last_celebrated_year"] or 0),
        )

    async def get_birthday(self, guild_id: int, user_id: int, *, include_removed: bool = False) -> Birthday | None:
        record = await self.get_pool().fetchrow(
            "SELECT * FROM birthday_members WHERE guild_id = $1 AND user_id = $2"
            + ("" if include_removed else " AND active = TRUE"),
            guild_id, user_id,
        )
        return self._record_to_birthday(record) if record else None

    async def save_birthday(
        self, guild_id: int, user_id: int, day: int, month: int, year: int | None, show_age: bool
    ) -> Birthday:
        record = await self.get_pool().fetchrow(
            """
            INSERT INTO birthday_members (guild_id, user_id, day, month, year, show_age)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET day = EXCLUDED.day, month = EXCLUDED.month, year = EXCLUDED.year,
                          show_age = EXCLUDED.show_age, active = TRUE, updated_at = NOW()
            RETURNING *
            """,
            guild_id, user_id, day, month, year, show_age,
        )
        return self._record_to_birthday(record)

    async def set_show_age(self, guild_id: int, user_id: int, show_age: bool) -> None:
        await self.get_pool().execute(
            "UPDATE birthday_members SET show_age = $3 WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id, show_age,
        )

    async def delete_birthday(self, guild_id: int, user_id: int) -> bool:
        """
        Retire la date sans effacer « déjà fêté cette année » : retirer puis
        remettre son anniversaire ne permet pas d'être fêté deux fois.
        """
        result = await self.get_pool().fetchval(
            """
            UPDATE birthday_members SET active = FALSE
            WHERE guild_id = $1 AND user_id = $2 AND active = TRUE
            RETURNING user_id
            """,
            guild_id, user_id,
        )
        return result is not None

    async def upcoming_embed(self, guild: discord.Guild, *, limit: int = 10, title: str = "📅 Prochains anniversaires") -> discord.Embed:
        records = await self.get_pool().fetch(
            "SELECT user_id, day, month FROM birthday_members WHERE guild_id = $1 AND active = TRUE", guild.id
        )
        present = present_member_ids(self.bot, guild.id)
        allowed = set(present) if present is not None else None
        today = datetime.now(PARIS).date()
        upcoming = sorted(
            (next_birthday(int(r["day"]), int(r["month"]), today), int(r["user_id"]), int(r["day"]), int(r["month"]))
            for r in records
            if allowed is None or int(r["user_id"]) in allowed
        )
        lines = []

        for when, user_id, day, month in upcoming[:limit]:
            if when == today:
                suffix = "🥳 **aujourd'hui !**"
            else:
                stamp = int(datetime.combine(when, time(0, 0), tzinfo=PARIS).timestamp())
                suffix = f"<t:{stamp}:R>"
            lines.append(f"🎂 <@{user_id}> — **{format_day(day, month)}** · {suffix}")

        description = "\n".join(lines) if lines else "Aucun anniversaire enregistré pour l'instant."

        if len(upcoming) > limit:
            description += f"\n… et {len(upcoming) - limit} autre(s)."

        embed = discord.Embed(title=title, description=description[:4096], color=COLOR)
        embed.set_footer(text=f"{len(upcoming)} anniversaire(s) enregistré(s) · /anniversaire pour ajouter le tien 🎂")
        return embed

    # -------- réglages --------

    async def get_settings(self, guild_id: int) -> tuple[dict[str, Any], bytes | None]:
        record = await self.get_pool().fetchrow(
            "SELECT settings, background FROM birthday_settings WHERE guild_id = $1", guild_id
        )
        settings = dict(DEFAULT_SETTINGS)

        if record is not None:
            stored = record["settings"]
            stored = json.loads(stored) if isinstance(stored, str) else (stored or {})
            settings.update({key: value for key, value in stored.items() if key in DEFAULT_SETTINGS})

        background = bytes(record["background"]) if record is not None and record["background"] else None
        return settings, background

    async def save_settings(self, guild_id: int, settings: dict[str, Any]) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO birthday_settings (guild_id, settings)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (guild_id) DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW()
            """,
            guild_id, json.dumps(settings, ensure_ascii=False),
        )

    async def save_background(self, guild_id: int, background: bytes | None) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO birthday_settings (guild_id, background)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET background = EXCLUDED.background, updated_at = NOW()
            """,
            guild_id, background,
        )

    def permission_warning(self, guild: discord.Guild, settings: dict[str, Any]) -> str | None:
        channel = guild.get_channel(settings["channel_id"] or 0)

        if not isinstance(channel, discord.TextChannel):
            return "⚠️ Le salon des souhaits n'existe plus."

        perms = channel.permissions_for(guild.me)
        missing = [
            name
            for name, ok in (
                ("Voir le salon", perms.view_channel),
                ("Envoyer des messages", perms.send_messages),
                ("Intégrer des liens", perms.embed_links or settings.get("style") == "card"),
                ("Joindre des fichiers", perms.attach_files or settings.get("style") == "embed"),
            )
            if not ok
        ]

        role = guild.get_role(settings["role_id"] or 0) if settings["role_id"] else None

        if settings["role_id"] and role is None:
            missing.append("le rôle choisi n'existe plus")
        elif role is not None and (not guild.me.guild_permissions.manage_roles or role >= guild.me.top_role):
            missing.append("Gérer les rôles (et mon rôle doit être au-dessus du rôle d'anniversaire)")

        return f"⚠️ Il me manque : {', '.join(missing)}." if missing else None

    # -------- célébration --------

    async def render_card(self, member: Any, age: int | None, settings: dict, background: bytes | None) -> bytes:
        try:
            avatar = await member.display_avatar.replace(format="png", size=256).read()
        except (discord.HTTPException, ValueError):
            avatar = None

        return await asyncio.to_thread(
            render_welcome_card,
            avatar_bytes=avatar,
            title=fill(settings["title"], member, age, on_card=True),
            subtitle=fill(settings["subtitle"], member, age, on_card=True),
            text=fill(settings["text"], member, age, on_card=True),
            background_bytes=background,
            subtitle_color="#FFD166",
        )

    async def send_wishes(self, member: Any, age: int | None, settings: dict, background: bytes | None):
        channel = member.guild.get_channel(settings["channel_id"] or 0)

        if not isinstance(channel, discord.TextChannel):
            return None

        style = settings.get("style") if settings.get("style") in STYLES else "embed"
        kwargs: dict[str, Any] = {
            "allowed_mentions": discord.AllowedMentions(everyone=False, roles=False, users=[member]),
        }

        if style == "card":
            kwargs["content"] = fill(settings["message"], member, age)[:2000] or None
        else:
            # La mention au-dessus du cadre : le membre reçoit une notification.
            kwargs["content"] = member.mention
            kwargs["embed"] = build_wishes_embed(member, age, settings, now=datetime.now(timezone.utc))

        if style in ("card", "both"):
            png = await self.render_card(member, age, settings, background)
            kwargs["file"] = discord.File(io.BytesIO(png), filename="anniversaire.png")

            if style == "both":
                kwargs["embed"].set_image(url="attachment://anniversaire.png")

        try:
            return await channel.send(**kwargs)
        except discord.HTTPException:
            LOGGER.warning("Souhaits d'anniversaire impossibles dans %s", channel.id)
            return None

    async def celebrate(self, guild: discord.Guild, member: discord.Member, birthday: Birthday,
                        settings: dict, background: bytes | None, today: date) -> None:
        # Réservation : une seule célébration par an, même avec deux boucles ou un redémarrage.
        reserved = await self.get_pool().fetchval(
            """
            UPDATE birthday_members SET last_celebrated_year = $3
            WHERE guild_id = $1 AND user_id = $2 AND last_celebrated_year < $3
            RETURNING user_id
            """,
            guild.id, member.id, today.year,
        )

        if reserved is None:
            return

        await self.send_wishes(member, birthday.shown_age(today), settings, background)

        role = guild.get_role(settings["role_id"] or 0) if settings["role_id"] else None

        if role is not None:
            try:
                await member.add_roles(role, reason="Anniversaire")
                await self.get_pool().execute(
                    """
                    INSERT INTO birthday_role_grants (guild_id, user_id, role_id, granted_on)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, user_id)
                    DO UPDATE SET role_id = EXCLUDED.role_id, granted_on = EXCLUDED.granted_on
                    """,
                    guild.id, member.id, role.id, today,
                )
            except discord.HTTPException:
                LOGGER.warning("Rôle d'anniversaire non donné à %s", member.id)

        if settings["coins"] or settings["xp"]:
            try:
                old_xp, new_xp = await credit_progression(
                    self.bot.database,
                    guild_id=guild.id,
                    user_id=member.id,
                    xp=int(settings["xp"]),
                    coins=int(settings["coins"]),
                    transaction_type="birthday",
                    reason=f"Anniversaire {today.year}",
                )
                await refresh_level_roles(self.bot, member, old_xp, new_xp)
            except Exception:
                LOGGER.exception("Cadeau d'anniversaire non versé à %s", member.id)

    async def remove_expired_roles(self, today: date) -> None:
        records = await self.get_pool().fetch(
            "SELECT guild_id, user_id, role_id FROM birthday_role_grants WHERE granted_on < $1", today
        )

        for record in records:
            guild = self.bot.get_guild(int(record["guild_id"]))
            member = guild.get_member(int(record["user_id"])) if guild else None
            role = guild.get_role(int(record["role_id"])) if guild else None

            if member is not None and role is not None and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Fin de l'anniversaire")
                except discord.HTTPException:
                    LOGGER.warning("Rôle d'anniversaire non retiré à %s", member.id)
                    continue

            await self.get_pool().execute(
                "DELETE FROM birthday_role_grants WHERE guild_id = $1 AND user_id = $2",
                int(record["guild_id"]), int(record["user_id"]),
            )

    async def run_once(self, now: datetime | None = None) -> None:
        now = (now or datetime.now(timezone.utc)).astimezone(PARIS)
        today = now.date()
        await self.remove_expired_roles(today)

        for guild in list(self.bot.guilds):
            settings, background = await self.get_settings(guild.id)

            if not settings["enabled"] or now.hour < int(settings["hour"]):
                continue

            records = await self.get_pool().fetch(
                "SELECT * FROM birthday_members WHERE guild_id = $1 AND active = TRUE AND last_celebrated_year < $2",
                guild.id, today.year,
            )

            for record in records:
                birthday = self._record_to_birthday(record)

                if celebration_day(birthday.day, birthday.month, today.year) != today:
                    continue

                member = guild.get_member(int(record["user_id"]))

                if member is None or member.bot:
                    continue

                try:
                    await self.celebrate(guild, member, birthday, settings, background, today)
                except Exception:
                    LOGGER.exception("Anniversaire de %s non fêté", member.id)

    @tasks.loop(minutes=5)
    async def loop(self) -> None:
        if self._running:
            return

        self._running = True

        try:
            await self.run_once()
        except Exception:
            LOGGER.exception("Boucle des anniversaires interrompue")
        finally:
            self._running = False

    @loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()

    # -------- commandes --------

    @app_commands.command(name="anniversaire", description="Enregistre ton anniversaire et vois les prochains.")
    @app_commands.guild_only()
    async def anniversaire(self, interaction: discord.Interaction) -> None:
        birthday = await self.get_birthday(interaction.guild_id, interaction.user.id)
        panel = MemberPanel(self, interaction.user, birthday)
        await interaction.response.send_message(embed=panel.embed(), view=panel, ephemeral=True)

    @app_commands.command(name="anniversaires", description="Affiche les prochains anniversaires du serveur.")
    @app_commands.guild_only()
    async def anniversaires(self, interaction: discord.Interaction) -> None:
        # Public : tout le salon voit la liste. Les mentions ne notifient personne.
        await interaction.response.send_message(
            embed=await self.upcoming_embed(interaction.guild),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="anniversaire-admin", description="Réglages des anniversaires (salon, rôle, cadeau…).")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def anniversaire_admin(self, interaction: discord.Interaction) -> None:
        settings, background = await self.get_settings(interaction.guild_id)
        panel = AdminPanel(self, interaction, settings, background)
        await send_panel(interaction, embed=panel.embed(), view=panel)


async def setup(bot: commands.Bot) -> None:
    cog = BirthdayCog(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)
    LOGGER.info("Anniversaires chargés")
