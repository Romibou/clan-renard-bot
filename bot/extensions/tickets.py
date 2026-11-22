"""
Tickets : un salon privé entre un membre et le staff.

- /ticket-admin : salon du message, catégorie Discord où créer les
  tickets, salon des logs, types de tickets (nom, emoji, description,
  rôles staff qui les voient), texte du message, publication.
- Message public : bouton 📩 Ouvrir un ticket → menu des types →
  raison → salon privé créé (membre + rôles staff du type + admins).
- Dans le ticket : fiche complète du membre, 🙋 Prendre en charge,
  👥 Gérer les membres (staff), 🔒 Fermer.
- Fermeture : délai de 10 secondes (annulable), transcript .txt dans le
  salon des logs et en MP au membre, puis suppression du salon.

Les boutons des messages publics et des tickets marchent même après un
redémarrage du bot (boutons persistants).
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import unicodedata
from datetime import datetime
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.shared.panels import first_value, remember_origin, reset_selection

LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(88, 101, 242)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WAITING_COLOR = discord.Color.from_rgb(235, 174, 65)

CLOSE_DELAY = 10
MAX_TYPES = 25
MAX_STAFF_ROLES = 5
MAX_TRANSCRIPT_MESSAGES = 5000
DEFAULT_TITLE = "🎫 Support du serveur"
DEFAULT_TEXT = (
    "**Besoin du staff ? Ouvre un ticket !**\n"
    "📬 Un ticket est un salon **privé** entre toi et l'équipe.\n\n"
    "🔑 Une **question**, un **problème** ou une **demande** qui a besoin du staff : "
    "c'est ici que ça se passe.\n\n"
    "⏳ L'équipe est **bénévole** : merci d'être **patient** et de ne pas mentionner "
    "le staff en boucle."
)
DEFAULT_BUTTON = "Ouvrir un ticket"
DEFAULT_TYPES = (
    ("J'ai une question", "❓", "Une question à poser au staff."),
    ("J'ai un problème", "🚨", "Un problème à signaler."),
    ("Contacter l'animation", "🎉", "Pour l'équipe d'animation."),
    ("Contacter l'administration", "📌", "Pour les demandes particulières."),
    ("Autre demande", "🌱", "Tout ce qui ne rentre pas dans les autres catégories."),
)


# ============================================================
# OUTILS (fonctions pures, testées)
# ============================================================


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


def ts(moment: datetime | None, style: str = "f") -> str:
    return f"<t:{int(moment.timestamp())}:{style}>" if moment else "—"


def slug(text: str, limit: int = 20) -> str:
    """Nom de salon Discord : minuscules, sans accent, tirets."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    plain = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return plain[:limit].strip("-") or "membre"


def channel_name(number: int, username: str) -> str:
    return f"ticket-{number:04d}-{slug(username)}"


def parse_emoji(text: str) -> str:
    """Emoji d'un type : vide, un emoji classique ou <:nom:id> du serveur."""
    value = (text or "").strip()

    if not value:
        return ""

    if re.fullmatch(r"<a?:\w{2,32}:\d{15,25}>", value):
        return value

    if len(value) > 8 or any(char.isalnum() for char in value):
        raise ValueError("Emoji invalide : mets un seul emoji (❓, 🎉…) ou un emoji du serveur.")

    return value


def roles_text(member: Any, limit: int = 900) -> str:
    """Rôles du membre (du plus haut au plus bas), sans @everyone, tronqués proprement."""
    roles = [role for role in reversed(getattr(member, "roles", [])) if not role.is_default()]

    if not roles:
        return "*aucun*"

    text = ""

    for index, role in enumerate(roles):
        piece = role.mention if not text else f", {role.mention}"

        if len(text) + len(piece) > limit:
            return text + f" *(+{len(roles) - index})*"

        text += piece

    return text


def duration_text(start: datetime, end: datetime) -> str:
    seconds = max(0, int((end - start).total_seconds()))
    days, rest = divmod(seconds, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes = rest // 60

    if days:
        return f"{days} j {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{max(1, minutes)} min"


def transcript_text(ticket: Any, type_label: str, member_label: str, closer_label: str,
                    messages: list[Any], closed_at: datetime) -> str:
    """Conversation complète en texte brut (heure de Paris non garantie : UTC indiqué)."""
    lines = [
        f"Ticket n°{ticket['number']:04d} — {type_label}",
        f"Membre : {member_label}",
        f"Ouvert le {ticket['opened_at']:%d/%m/%Y %H:%M} UTC — "
        f"fermé le {closed_at:%d/%m/%Y %H:%M} UTC par {closer_label}",
        f"Raison : {ticket['reason']}",
        f"Messages : {len(messages)}",
        "─" * 60,
    ]

    for message in messages:
        author = getattr(message.author, "name", "?")
        content = message.content or ""

        if getattr(message, "embeds", None) and not content:
            first = message.embeds[0]
            content = f"[embed] {first.title or ''} {first.description or ''}".strip()

        lines.append(f"[{message.created_at:%d/%m/%Y %H:%M}] {author} : {content}")

        for attachment in getattr(message, "attachments", []):
            lines.append(f"    📎 {attachment.filename} : {attachment.url}")

    return "\n".join(lines) + "\n"


def is_admin(member: Any) -> bool:
    permissions = getattr(member, "guild_permissions", None)
    return bool(permissions and (permissions.administrator or permissions.manage_guild))


def is_staff(member: Any, staff_role_ids: list[int]) -> bool:
    if is_admin(member):
        return True

    return any(role.id in staff_role_ids for role in getattr(member, "roles", []))


def get_cog(client: Any) -> Tickets | None:
    return client.get_cog("Tickets") if client else None


# ============================================================
# EMBEDS
# ============================================================


def panel_embed(settings: dict[str, Any], guild: Any) -> discord.Embed:
    embed = discord.Embed(
        title=settings["panel_title"] or DEFAULT_TITLE,
        description=settings["panel_text"] or DEFAULT_TEXT,
        color=COLOR,
    )

    icon = getattr(getattr(guild, "icon", None), "url", None)

    if icon:
        embed.set_thumbnail(url=icon)

    return embed


def ticket_embeds(ticket: Any, ticket_type: Any, member: Any) -> list[discord.Embed]:
    """Fiche d'ouverture : ticket, membre, rôles, puis la raison."""
    emoji = ticket_type["emoji"] or "🎫"
    main = discord.Embed(
        title=f"📬 Ticket n°{ticket['number']:04d}",
        description=f"👋 {member.mention}, bienvenue dans ton ticket **{ticket_type['label']}**.\n"
                    "Explique ta demande ici, un membre du staff va te répondre.",
        color=COLOR,
    )
    main.add_field(
        name="🎫 Ticket",
        value=(
            f"{emoji} Type : **{ticket_type['label']}**\n"
            f"🔢 Numéro : `{ticket['number']:04d}`\n"
            f"📅 Ouvert le : {ts(ticket['opened_at'])}"
        ),
        inline=False,
    )
    main.add_field(
        name="⭐ Membre",
        value=(
            f"{member.mention} · `{member.name}` · `{member.id}`\n"
            f"📅 Compte créé le : {ts(member.created_at, 'D')} ({ts(member.created_at, 'R')})\n"
            f"📥 Arrivé sur le serveur : {ts(getattr(member, 'joined_at', None), 'D')}"
        ),
        inline=False,
    )
    main.add_field(name="🔑 Rôles", value=roles_text(member), inline=False)

    avatar = getattr(getattr(member, "display_avatar", None), "url", None)

    if avatar:
        main.set_thumbnail(url=avatar)

    reason = discord.Embed(title="📌 Raison du ticket", description=ticket["reason"][:4000], color=COLOR)
    return [main, reason]


def admin_embed(settings: dict[str, Any], types: list[Any], guild: Any, notice: str | None,
                open_count: int) -> discord.Embed:
    def place(channel_id: int | None) -> str:
        return f"<#{channel_id}>" if channel_id else "*à choisir*"

    lines = [
        f"📣 Salon du message : {place(settings['panel_channel_id'])}"
        + (" · ✅ publié" if settings["panel_message_id"] else " · *pas encore publié*"),
        f"📁 Catégorie des tickets : {place(settings['category_id'])}",
        f"🗂️ Salon des logs (transcripts) : {place(settings['log_channel_id'])}",
        f"👤 Tickets ouverts en même temps par membre : **{settings['max_open']}**",
        f"🟢 Tickets ouverts en ce moment : **{open_count}**",
        "",
        f"**Types de tickets ({len(types)}/{MAX_TYPES}) :**",
    ]

    if types:
        for ticket_type in types:
            roles = ", ".join(f"<@&{role_id}>" for role_id in ticket_type["staff_role_ids"]) or "*admins seulement*"
            lines.append(f"{ticket_type['emoji'] or '🎫'} **{ticket_type['label']}** → {roles}")
    else:
        lines.append("*aucun : ajoute-en avec ➕ ou crée ceux par défaut avec 🧩.*")

    if notice:
        lines += ["", f"> {notice}"]

    return discord.Embed(title="🎫 Tickets — réglages", description="\n".join(lines)[:4000], color=COLOR)


# ============================================================
# BOUTONS PERSISTANTS
# ============================================================


class OpenTicketButton(discord.ui.DynamicItem[discord.ui.Button], template=r"ticket:open"):
    def __init__(self, label: str = DEFAULT_BUTTON) -> None:
        super().__init__(
            discord.ui.Button(label=label[:80] or DEFAULT_BUTTON, emoji="📩",
                              style=discord.ButtonStyle.success, custom_id="ticket:open")
        )

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button,
                             match: re.Match[str]) -> OpenTicketButton:
        return cls(item.label or DEFAULT_BUTTON)

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = get_cog(interaction.client)

        if cog is None:
            await interaction.response.send_message("Module indisponible.", ephemeral=True)
            return

        await cog.start_opening(interaction)


class TicketActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ticket:(?P<action>close|claim|staff):(?P<id>[0-9]+)",
):
    STYLES = {
        "close": ("Fermer", "🔒", discord.ButtonStyle.danger),
        "claim": ("Prendre en charge", "🙋", discord.ButtonStyle.primary),
        "staff": ("Gérer les membres", "👥", discord.ButtonStyle.secondary),
    }

    def __init__(self, action: str, ticket_id: int) -> None:
        label, emoji, style = self.STYLES[action]
        super().__init__(
            discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"ticket:{action}:{ticket_id}")
        )
        self.action = action
        self.ticket_id = ticket_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button,
                             match: re.Match[str]) -> TicketActionButton:
        return cls(match["action"], int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = get_cog(interaction.client)

        if cog is None:
            await interaction.response.send_message("Module indisponible.", ephemeral=True)
            return

        await cog.ticket_action(interaction, self.action, self.ticket_id)


def ticket_view(ticket_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)

    for action in ("claim", "staff", "close"):
        view.add_item(TicketActionButton(action, ticket_id))

    return view


def panel_view(settings: dict[str, Any]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(OpenTicketButton(settings["button_label"] or DEFAULT_BUTTON))
    return view


# ============================================================
# OUVERTURE (membre)
# ============================================================


class ReasonModal(discord.ui.Modal):
    def __init__(self, cog: Tickets, ticket_type: Any) -> None:
        super().__init__(title=f"{ticket_type['emoji'] or '🎫'} {ticket_type['label']}"[:45], timeout=900)
        self.cog = cog
        self.ticket_type = ticket_type
        self.reason = discord.ui.TextInput(style=discord.TextStyle.paragraph, min_length=5, max_length=1000)
        self.add_item(discord.ui.Label(
            text="Raison du ticket",
            description="Explique en quelques mots : le staff la verra en ouvrant le ticket.",
            component=self.reason,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await self.cog.open_ticket(interaction, self.ticket_type["id"], self.reason.value.strip())
        await interaction.followup.send(text, ephemeral=True)


class TypePickerView(discord.ui.View):
    def __init__(self, cog: Tickets, types: list[Any]) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.types = {str(ticket_type["id"]): ticket_type for ticket_type in types}
        select = discord.ui.Select(
            placeholder="Choisis la catégorie de ton ticket…",
            options=[
                discord.SelectOption(
                    label=ticket_type["label"][:100],
                    value=str(ticket_type["id"]),
                    description=(ticket_type["description"] or None) and ticket_type["description"][:100],
                    emoji=ticket_type["emoji"] or None,
                )
                for ticket_type in types
            ],
        )
        select.callback = self.on_pick
        self.select = select
        self.add_item(select)

    async def on_pick(self, interaction: discord.Interaction) -> None:
        ticket_type = self.types.get(self.select.values[0])

        if ticket_type is None:
            await interaction.response.send_message(embed=error_embed("Type introuvable."), ephemeral=True)
            return

        await interaction.response.send_modal(ReasonModal(self.cog, ticket_type))


# ============================================================
# DANS LE TICKET
# ============================================================


class MembersModal(discord.ui.Modal):
    def __init__(self, cog: Tickets, ticket_id: int) -> None:
        super().__init__(title="👥 Membres du ticket", timeout=600)
        self.cog = cog
        self.ticket_id = ticket_id
        self.action = discord.ui.Select(options=[
            discord.SelectOption(label="Ajouter au ticket", value="add", emoji="➕", default=True),
            discord.SelectOption(label="Retirer du ticket", value="remove", emoji="➖"),
        ])
        self.add_item(discord.ui.Label(text="Action", component=self.action))
        self.users = discord.ui.UserSelect(min_values=1, max_values=5)
        self.add_item(discord.ui.Label(text="Membres", component=self.users))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = await self.cog.change_members(
            interaction, self.ticket_id, list(self.users.values), add=first_value(self.action, "add") == "add")
        await interaction.response.send_message(text, ephemeral=True)


class CloseConfirmView(discord.ui.View):
    def __init__(self, cog: Tickets, ticket_id: int, user_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.ticket_id = ticket_id
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Oui, fermer", emoji="🔒", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="🔒 Fermeture lancée.", embed=None, view=None)
        await self.cog.schedule_close(interaction, self.ticket_id)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Le ticket reste ouvert.", embed=None, view=None)


class CancelCloseView(discord.ui.View):
    def __init__(self, cog: Tickets, ticket_id: int) -> None:
        super().__init__(timeout=CLOSE_DELAY + 5)
        self.cog = cog
        self.ticket_id = ticket_id

    @discord.ui.button(label="Annuler la fermeture", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.cog.cancel_close(self.ticket_id):
            self.stop()
            await interaction.response.edit_message(
                embed=discord.Embed(description=f"↩️ Fermeture annulée par {interaction.user.mention}.",
                                    color=SUCCESS_COLOR),
                view=None,
            )
        else:
            await interaction.response.send_message("Trop tard, le ticket se ferme.", ephemeral=True)


# ============================================================
# PANNEAU ADMIN : /ticket-admin
# ============================================================


class SettingsModal(discord.ui.Modal):
    def __init__(self, panel: AdminPanel) -> None:
        super().__init__(title="⚙️ Réglages des tickets", timeout=900)
        self.panel = panel
        settings = panel.settings
        guild = panel.guild

        def channel_select(channel_id: int | None, types: list[discord.ChannelType]) -> discord.ui.ChannelSelect:
            channel = guild.get_channel(channel_id or 0)
            return discord.ui.ChannelSelect(channel_types=types, default_values=[channel] if channel else [],
                                            min_values=1, max_values=1)

        self.panel_channel = channel_select(settings["panel_channel_id"], [discord.ChannelType.text])
        self.add_item(discord.ui.Label(text="Salon du message « Ouvrir un ticket »", component=self.panel_channel))
        self.category = channel_select(settings["category_id"], [discord.ChannelType.category])
        self.add_item(discord.ui.Label(
            text="Catégorie où créer les tickets", description="Une catégorie Discord (50 salons maximum).",
            component=self.category,
        ))
        self.log_channel = channel_select(settings["log_channel_id"], [discord.ChannelType.text])
        self.add_item(discord.ui.Label(
            text="Salon des logs", description="Transcripts des tickets fermés (garde-le privé).",
            component=self.log_channel,
        ))
        self.max_open = discord.ui.TextInput(default=str(settings["max_open"]), max_length=2)
        self.add_item(discord.ui.Label(
            text="Tickets ouverts par membre", description="En même temps, de 1 à 5.", component=self.max_open,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.max_open.value.strip()

        if not value.isdigit() or not 1 <= int(value) <= 5:
            await interaction.response.send_message(embed=error_embed("Un nombre entre 1 et 5."), ephemeral=True)
            return

        # Un menu laissé vide garde le salon déjà choisi.
        def chosen(select: Any, key: str) -> int | None:
            picked = first_value(select)
            return picked.id if picked is not None else self.panel.settings[key]

        self.panel.settings.update(
            panel_channel_id=chosen(self.panel_channel, "panel_channel_id"),
            category_id=chosen(self.category, "category_id"),
            log_channel_id=chosen(self.log_channel, "log_channel_id"),
            max_open=int(value),
        )
        await self.panel.cog.save_settings(interaction.guild_id, self.panel.settings)
        problem = self.panel.cog.setup_problem(interaction.guild, self.panel.settings)
        await self.panel.refresh(interaction, problem or "✅ Réglages enregistrés.")


class TextModal(discord.ui.Modal):
    def __init__(self, panel: AdminPanel) -> None:
        super().__init__(title="✏️ Message des tickets", timeout=900)
        self.panel = panel
        settings = panel.settings
        self.title_input = discord.ui.TextInput(default=settings["panel_title"] or DEFAULT_TITLE, max_length=200)
        self.add_item(discord.ui.Label(text="Titre", component=self.title_input))
        self.text = discord.ui.TextInput(style=discord.TextStyle.paragraph,
                                         default=settings["panel_text"] or DEFAULT_TEXT, max_length=3000)
        self.add_item(discord.ui.Label(text="Texte", description="Markdown accepté (**gras**, emojis…).",
                                       component=self.text))
        self.button = discord.ui.TextInput(default=settings["button_label"] or DEFAULT_BUTTON, max_length=60)
        self.add_item(discord.ui.Label(text="Texte du bouton", component=self.button))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.panel.settings.update(
            panel_title=self.title_input.value.strip(),
            panel_text=self.text.value.strip(),
            button_label=self.button.value.strip(),
        )
        await self.panel.cog.save_settings(interaction.guild_id, self.panel.settings)
        notice = "✏️ Texte enregistré."

        if self.panel.settings["panel_message_id"]:
            notice += " Le message public est à jour."

        await self.panel.refresh(interaction, notice)


class TypeModal(discord.ui.Modal):
    """Ajouter (ticket_type None) ou modifier / supprimer un type."""

    def __init__(self, panel: AdminPanel, ticket_type: Any = None) -> None:
        super().__init__(title="✏️ Type de ticket" if ticket_type else "➕ Nouveau type de ticket", timeout=900)
        self.panel = panel
        self.ticket_type = ticket_type
        data = ticket_type or {}
        self.label = discord.ui.TextInput(default=data.get("label"), min_length=2, max_length=60)
        self.add_item(discord.ui.Label(text="Nom", description="Exemple : Contacter l'animation", component=self.label))
        self.emoji = discord.ui.TextInput(default=data.get("emoji") or None, required=False, max_length=60)
        self.add_item(discord.ui.Label(text="Emoji (facultatif)", component=self.emoji))
        self.description = discord.ui.TextInput(default=data.get("description") or None, required=False,
                                                max_length=100)
        self.add_item(discord.ui.Label(text="Description dans le menu (facultatif)", component=self.description))
        roles = [panel.guild.get_role(role_id) for role_id in data.get("staff_role_ids") or []]
        self.roles = discord.ui.RoleSelect(default_values=[role for role in roles if role], min_values=0,
                                           max_values=MAX_STAFF_ROLES, required=False)
        self.add_item(discord.ui.Label(
            text="Rôles staff qui voient ces tickets",
            description="Les admins (Gérer le serveur) voient tous les tickets.",
            component=self.roles,
        ))

        if ticket_type:
            self.delete = discord.ui.Select(options=[
                discord.SelectOption(label="Garder ce type", value="keep", emoji="✅", default=True),
                discord.SelectOption(label="Supprimer ce type", value="delete", emoji="🗑️",
                                     description="Les tickets déjà ouverts restent ouverts."),
            ])
            self.add_item(discord.ui.Label(text="Garder ou supprimer", component=self.delete))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = self.panel.cog

        if self.ticket_type and first_value(self.delete, "keep") == "delete":
            await cog.delete_type(interaction.guild_id, self.ticket_type["id"])
            notice = f"🗑️ Type **{self.ticket_type['label']}** supprimé."
        else:
            try:
                emoji = parse_emoji(self.emoji.value)
            except ValueError as error:
                await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
                return

            role_ids = [role.id for role in self.roles.values]
            await cog.save_type(interaction.guild_id, self.ticket_type["id"] if self.ticket_type else None,
                                self.label.value.strip(), emoji, self.description.value.strip(), role_ids)
            notice = f"✅ Type **{self.label.value.strip()}** enregistré."

        if self.panel.settings["panel_message_id"]:
            notice += " Le message public est à jour."

        await self.panel.refresh(interaction, notice)


class AdminPanel(discord.ui.View):
    def __init__(self, cog: Tickets, interaction: discord.Interaction, settings: dict[str, Any],
                 types: list[Any], open_count: int) -> None:
        super().__init__(timeout=900)
        self.cog = cog
        self.guild = interaction.guild
        self.owner_id = interaction.user.id
        self.settings = settings
        self.types = types
        self.open_count = open_count
        self.build()

    def build(self) -> None:
        self.clear_items()

        if self.types:
            select = discord.ui.Select(
                placeholder="✏️ Modifier ou supprimer un type…",
                options=[
                    discord.SelectOption(label=ticket_type["label"][:100], value=str(ticket_type["id"]),
                                         emoji=ticket_type["emoji"] or None)
                    for ticket_type in self.types
                ],
                row=0,
            )
            select.callback = self.on_edit_type
            self.type_select = select
            self.add_item(select)

        buttons = [
            ("Réglages", "⚙️", discord.ButtonStyle.primary, self.on_settings, 1),
            ("Ajouter un type", "➕", discord.ButtonStyle.success, self.on_add_type, 1),
            ("Texte du message", "✏️", discord.ButtonStyle.secondary, self.on_text, 1),
            ("Publier / mettre à jour", "📣", discord.ButtonStyle.success, self.on_publish, 2),
            ("Tickets ouverts", "📋", discord.ButtonStyle.secondary, self.on_list, 2),
        ]

        if not self.types:
            buttons.append(("Créer les types par défaut", "🧩", discord.ButtonStyle.secondary, self.on_defaults, 2))

        for label, emoji, style, callback, row in buttons:
            button = discord.ui.Button(label=label, emoji=emoji, style=style, row=row)
            button.callback = callback
            self.add_item(button)

    def embed(self, notice: str | None = None) -> discord.Embed:
        return admin_embed(self.settings, self.types, self.guild, notice, self.open_count)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def refresh(self, interaction: discord.Interaction, notice: str | None = None) -> None:
        # Mise à jour du message public comprise : ça peut dépasser 3 secondes.
        if not interaction.response.is_done():
            await interaction.response.defer()

        self.settings = await self.cog.get_settings(self.guild.id)
        self.types = await self.cog.get_types(self.guild.id)
        self.open_count = await self.cog.open_count(self.guild.id)
        self.build()

        if self.settings["panel_message_id"]:
            await self.cog.publish(self.guild, self.settings, quiet=True)

        await interaction.edit_original_response(embed=self.embed(notice), view=self)

    async def on_settings(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SettingsModal(self))

    async def on_text(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TextModal(self))

    async def on_add_type(self, interaction: discord.Interaction) -> None:
        if len(self.types) >= MAX_TYPES:
            await interaction.response.send_message(
                embed=error_embed(f"{MAX_TYPES} types maximum (limite des menus Discord)."), ephemeral=True)
            return

        await interaction.response.send_modal(TypeModal(self))

    async def on_edit_type(self, interaction: discord.Interaction) -> None:
        try:
            chosen = next((t for t in self.types if str(t["id"]) == self.type_select.values[0]), None)

            if chosen is None:
                await interaction.response.send_message(embed=error_embed("Type introuvable."), ephemeral=True)
                return

            await interaction.response.send_modal(TypeModal(self, dict(chosen)))
        finally:
            # Le menu redevient vide : on peut rechoisir le même type.
            await reset_selection(self)

    async def on_defaults(self, interaction: discord.Interaction) -> None:
        for label, emoji, description in DEFAULT_TYPES:
            await self.cog.save_type(interaction.guild_id, None, label, emoji, description, [])

        await self.refresh(interaction, "🧩 5 types créés. Choisis leurs rôles staff avec le menu ✏️.")

    async def on_publish(self, interaction: discord.Interaction) -> None:
        problem = self.cog.setup_problem(interaction.guild, self.settings)

        if problem is None and not self.types:
            problem = "⚠️ Ajoute au moins un type de ticket."

        if problem:
            await interaction.response.send_message(embed=error_embed(problem.lstrip("⚠️ ")), ephemeral=True)
            return

        await interaction.response.defer()
        notice = await self.cog.publish(interaction.guild, self.settings)
        await self.refresh(interaction, notice)

    async def on_list(self, interaction: discord.Interaction) -> None:
        rows = await self.cog.open_tickets(interaction.guild_id)
        lines = [
            f"`{row['number']:04d}` <#{row['channel_id']}> · <@{row['user_id']}> · {row['type_label']} · "
            f"{ts(row['opened_at'], 'R')}" + (f" · 🙋 <@{row['claimed_by']}>" if row["claimed_by"] else "")
            for row in rows[:40]
        ]
        await interaction.response.send_message(
            embed=discord.Embed(title=f"📋 Tickets ouverts ({len(rows)})",
                                description="\n".join(lines) or "Aucun ticket ouvert.", color=COLOR),
            ephemeral=True,
        )


# ============================================================
# COG
# ============================================================


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.closing: dict[int, asyncio.Task] = {}
        self.open_locks: dict[tuple[int, int], asyncio.Lock] = {}

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id BIGINT PRIMARY KEY,
                panel_channel_id BIGINT,
                panel_message_id BIGINT,
                category_id BIGINT,
                log_channel_id BIGINT,
                panel_title TEXT NOT NULL DEFAULT '',
                panel_text TEXT NOT NULL DEFAULT '',
                button_label TEXT NOT NULL DEFAULT '',
                max_open INTEGER NOT NULL DEFAULT 1,
                counter INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_types (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                label VARCHAR(60) NOT NULL,
                emoji VARCHAR(60) NOT NULL DEFAULT '',
                description VARCHAR(100) NOT NULL DEFAULT '',
                staff_role_ids BIGINT[] NOT NULL DEFAULT '{}',
                deleted BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                number INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                type_id BIGINT NOT NULL REFERENCES ticket_types(id),
                channel_id BIGINT,
                reason TEXT NOT NULL,
                status VARCHAR(10) NOT NULL DEFAULT 'open',
                claimed_by BIGINT,
                opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                closed_at TIMESTAMPTZ,
                closed_by BIGINT
            )
            """
        )
        await pool.execute(
            "CREATE INDEX IF NOT EXISTS tickets_open_idx ON tickets (guild_id, user_id) WHERE status = 'open'"
        )

    # -------- lecture / écriture --------

    async def get_settings(self, guild_id: int) -> dict[str, Any]:
        row = await self.get_pool().fetchrow("SELECT * FROM ticket_settings WHERE guild_id = $1", guild_id)
        defaults = {
            "panel_channel_id": None, "panel_message_id": None, "category_id": None, "log_channel_id": None,
            "panel_title": "", "panel_text": "", "button_label": "", "max_open": 1,
        }
        return {**defaults, **({key: row[key] for key in defaults} if row else {})}

    async def save_settings(self, guild_id: int, settings: dict[str, Any]) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO ticket_settings (guild_id, panel_channel_id, panel_message_id, category_id, log_channel_id,
                                         panel_title, panel_text, button_label, max_open)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (guild_id) DO UPDATE SET
                panel_channel_id = $2, panel_message_id = $3, category_id = $4, log_channel_id = $5,
                panel_title = $6, panel_text = $7, button_label = $8, max_open = $9
            """,
            guild_id, settings["panel_channel_id"], settings["panel_message_id"], settings["category_id"],
            settings["log_channel_id"], settings["panel_title"], settings["panel_text"], settings["button_label"],
            settings["max_open"],
        )

    async def get_types(self, guild_id: int) -> list[Any]:
        rows = await self.get_pool().fetch(
            "SELECT * FROM ticket_types WHERE guild_id = $1 AND deleted = FALSE ORDER BY id", guild_id)
        return [dict(row) | {"staff_role_ids": list(row["staff_role_ids"] or [])} for row in rows]

    async def get_type(self, type_id: int) -> dict[str, Any] | None:
        row = await self.get_pool().fetchrow("SELECT * FROM ticket_types WHERE id = $1", type_id)
        return dict(row) | {"staff_role_ids": list(row["staff_role_ids"] or [])} if row else None

    async def save_type(self, guild_id: int, type_id: int | None, label: str, emoji: str, description: str,
                        role_ids: list[int]) -> None:
        pool = self.get_pool()

        if type_id is None:
            await pool.execute(
                """
                INSERT INTO ticket_types (guild_id, label, emoji, description, staff_role_ids)
                VALUES ($1, $2, $3, $4, $5)
                """,
                guild_id, label, emoji, description, role_ids,
            )
        else:
            await pool.execute(
                """
                UPDATE ticket_types SET label = $3, emoji = $4, description = $5, staff_role_ids = $6
                WHERE id = $1 AND guild_id = $2
                """,
                type_id, guild_id, label, emoji, description, role_ids,
            )

    async def delete_type(self, guild_id: int, type_id: int) -> None:
        await self.get_pool().execute(
            "UPDATE ticket_types SET deleted = TRUE WHERE id = $1 AND guild_id = $2", type_id, guild_id)

    async def get_ticket(self, ticket_id: int) -> Any:
        return await self.get_pool().fetchrow("SELECT * FROM tickets WHERE id = $1", ticket_id)

    async def open_count(self, guild_id: int) -> int:
        return int(await self.get_pool().fetchval(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = $1 AND status = 'open'", guild_id) or 0)

    async def open_tickets(self, guild_id: int) -> list[Any]:
        return list(await self.get_pool().fetch(
            """
            SELECT tickets.*, ticket_types.label AS type_label FROM tickets
            JOIN ticket_types ON ticket_types.id = tickets.type_id
            WHERE tickets.guild_id = $1 AND tickets.status = 'open' ORDER BY tickets.opened_at
            """,
            guild_id,
        ))

    # -------- vérifications --------

    def setup_problem(self, guild: discord.Guild, settings: dict[str, Any]) -> str | None:
        me = guild.me
        category = guild.get_channel(settings["category_id"] or 0)
        panel = guild.get_channel(settings["panel_channel_id"] or 0)
        logs = guild.get_channel(settings["log_channel_id"] or 0)

        if not isinstance(category, discord.CategoryChannel):
            return "⚠️ Choisis la catégorie où créer les tickets (⚙️ Réglages)."

        if panel is None or logs is None:
            return "⚠️ Choisis le salon du message et le salon des logs (⚙️ Réglages)."

        missing = []

        if not category.permissions_for(me).manage_channels:
            missing.append(f"« Gérer les salons » dans la catégorie {category.name}")

        if not category.permissions_for(me).manage_roles:
            missing.append(f"« Gérer les permissions » dans la catégorie {category.name}")

        for channel in (panel, logs):
            permissions = channel.permissions_for(me)

            if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
                missing.append(f"voir / écrire / intégrer des liens dans {channel.mention}")

        if not logs.permissions_for(me).attach_files:
            missing.append(f"« Joindre des fichiers » dans {logs.mention} (transcripts)")

        return f"⚠️ Il manque au bot : {' ; '.join(missing)}." if missing else None

    # -------- message public --------

    async def publish(self, guild: discord.Guild, settings: dict[str, Any], *, quiet: bool = False) -> str:
        channel = guild.get_channel(settings["panel_channel_id"] or 0)

        if not isinstance(channel, discord.TextChannel):
            return "⚠️ Salon du message introuvable."

        embed = panel_embed(settings, guild)
        view = panel_view(settings)

        if settings["panel_message_id"]:
            try:
                message = await channel.fetch_message(settings["panel_message_id"])

                if message.author.id == guild.me.id:
                    await message.edit(embed=embed, view=view)
                    return "📣 Message public mis à jour."
            except discord.HTTPException:
                pass

            if quiet:
                return ""

        try:
            message = await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            return "⚠️ Impossible d'envoyer le message dans ce salon (permissions ?)."

        settings["panel_message_id"] = message.id
        await self.save_settings(guild.id, settings)
        return f"📣 Message publié dans {channel.mention}."

    # -------- ouverture --------

    async def start_opening(self, interaction: discord.Interaction) -> None:
        settings = await self.get_settings(interaction.guild_id)
        types = await self.get_types(interaction.guild_id)

        if not types or self.setup_problem(interaction.guild, settings):
            await interaction.response.send_message(
                embed=error_embed("Les tickets ne sont pas encore prêts : préviens un admin."), ephemeral=True)
            return

        count = await self.get_pool().fetchval(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = $1 AND user_id = $2 AND status = 'open'",
            interaction.guild_id, interaction.user.id,
        )

        if count >= settings["max_open"]:
            await interaction.response.send_message(
                embed=error_embed("Tu as déjà un ticket ouvert : continue la discussion dedans."), ephemeral=True)
            return

        embed = discord.Embed(
            title="📬 Choix de la catégorie",
            description="Choisis ci-dessous la **catégorie** qui correspond le mieux à ta demande.",
            color=COLOR,
        )
        icon = getattr(interaction.guild.icon, "url", None)

        if icon:
            embed.set_thumbnail(url=icon)

        await interaction.response.send_message(embed=embed, view=TypePickerView(self, types), ephemeral=True)

    def overwrites(self, guild: discord.Guild, member: discord.Member,
                   staff_role_ids: list[int]) -> dict[Any, discord.PermissionOverwrite]:
        talk = dict(view_channel=True, send_messages=True, read_message_history=True,
                    attach_files=True, embed_links=True, add_reactions=True)
        overwrites: dict[Any, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(**talk),
            guild.me: discord.PermissionOverwrite(**talk, manage_channels=True, manage_messages=True),
        }

        for role_id in staff_role_ids:
            role = guild.get_role(role_id)

            if role is not None:
                overwrites[role] = discord.PermissionOverwrite(**talk, manage_messages=True)

        return overwrites

    async def open_ticket(self, interaction: discord.Interaction, type_id: int, reason: str) -> str:
        guild = interaction.guild
        member = interaction.user
        lock = self.open_locks.setdefault((guild.id, member.id), asyncio.Lock())

        async with lock:
            settings = await self.get_settings(guild.id)
            ticket_type = await self.get_type(type_id)

            if ticket_type is None or ticket_type["deleted"] or ticket_type["guild_id"] != guild.id:
                return "❌ Ce type de ticket n'existe plus."

            if self.setup_problem(guild, settings):
                return "❌ Les tickets ne sont pas prêts : préviens un admin."

            pool = self.get_pool()
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = $1 AND user_id = $2 AND status = 'open'",
                guild.id, member.id,
            )

            if count >= settings["max_open"]:
                return "❌ Tu as déjà un ticket ouvert."

            category = guild.get_channel(settings["category_id"])

            if len(category.channels) >= 50:
                return "❌ La catégorie des tickets est pleine (50 salons) : préviens un admin."

            number = await pool.fetchval(
                "UPDATE ticket_settings SET counter = counter + 1 WHERE guild_id = $1 RETURNING counter", guild.id)

            if number is None:
                return "❌ Les tickets ne sont pas configurés : préviens un admin."
            ticket = await pool.fetchrow(
                """
                INSERT INTO tickets (guild_id, number, user_id, type_id, reason)
                VALUES ($1, $2, $3, $4, $5) RETURNING *
                """,
                guild.id, number, member.id, type_id, reason,
            )

            try:
                channel = await guild.create_text_channel(
                    channel_name(number, member.name),
                    category=category,
                    overwrites=self.overwrites(guild, member, ticket_type["staff_role_ids"]),
                    topic=f"Ticket n°{number:04d} · {ticket_type['label']} · {member} ({member.id})",
                    reason=f"Ticket n°{number} de {member}",
                )
            except discord.HTTPException:
                LOGGER.exception("Salon de ticket non créé")
                await pool.execute("DELETE FROM tickets WHERE id = $1", ticket["id"])
                return "❌ Impossible de créer le salon du ticket : préviens un admin (permissions du bot)."

            await pool.execute("UPDATE tickets SET channel_id = $2 WHERE id = $1", ticket["id"], channel.id)

        pings = " ".join([member.mention] + [f"<@&{role_id}>" for role_id in ticket_type["staff_role_ids"]])

        try:
            await channel.send(
                content=pings,
                embeds=ticket_embeds(ticket, ticket_type, member),
                view=ticket_view(ticket["id"]),
                allowed_mentions=discord.AllowedMentions(
                    users=[member], roles=[discord.Object(role_id) for role_id in ticket_type["staff_role_ids"]],
                    everyone=False,
                ),
            )
        except discord.HTTPException:
            LOGGER.exception("Fiche du ticket %s non envoyée", ticket["id"])

        await self.log(guild, settings, discord.Embed(
            description=f"📬 Ticket n°`{number:04d}` ouvert par {member.mention} · "
                        f"{ticket_type['emoji'] or '🎫'} {ticket_type['label']} · {channel.mention}",
            color=COLOR,
        ))
        return f"✅ Ton ticket est ouvert : {channel.mention}"

    # -------- actions dans le ticket --------

    async def ticket_action(self, interaction: discord.Interaction, action: str, ticket_id: int) -> None:
        ticket = await self.get_ticket(ticket_id)

        if ticket is None or ticket["status"] != "open" or ticket["guild_id"] != interaction.guild_id:
            await interaction.response.send_message(embed=error_embed("Ce ticket est déjà fermé."), ephemeral=True)
            return

        ticket_type = await self.get_type(ticket["type_id"]) or {"staff_role_ids": [], "label": "?"}
        staff = is_staff(interaction.user, ticket_type["staff_role_ids"])
        owner = interaction.user.id == ticket["user_id"]

        if action == "close":
            if not (staff or owner):
                await interaction.response.send_message(embed=error_embed("Tu ne peux pas fermer ce ticket."),
                                                        ephemeral=True)
                return

            if ticket_id in self.closing:
                await interaction.response.send_message("La fermeture est déjà en cours.", ephemeral=True)
                return

            await interaction.response.send_message(
                embed=discord.Embed(description="🔒 Fermer ce ticket ? La conversation sera enregistrée puis "
                                                "le salon supprimé.", color=WAITING_COLOR),
                view=CloseConfirmView(self, ticket_id, interaction.user.id),
                ephemeral=True,
            )
            return

        if not staff:
            await interaction.response.send_message(embed=error_embed("Réservé au staff de ce ticket."),
                                                    ephemeral=True)
            return

        if action == "claim":
            if ticket["claimed_by"]:
                await interaction.response.send_message(
                    f"Déjà pris en charge par <@{ticket['claimed_by']}>.", ephemeral=True)
                return

            await self.get_pool().execute("UPDATE tickets SET claimed_by = $2 WHERE id = $1",
                                          ticket_id, interaction.user.id)
            await interaction.response.send_message(
                embed=discord.Embed(description=f"🙋 {interaction.user.mention} prend en charge ce ticket.",
                                    color=SUCCESS_COLOR),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        await interaction.response.send_modal(MembersModal(self, ticket_id))

    async def change_members(self, interaction: discord.Interaction, ticket_id: int, users: list[Any],
                             *, add: bool) -> str:
        ticket = await self.get_ticket(ticket_id)
        channel = interaction.guild.get_channel(ticket["channel_id"] or 0) if ticket else None

        if channel is None:
            return "❌ Salon du ticket introuvable."

        done = []

        for user in users:
            member = interaction.guild.get_member(user.id)

            if member is None or member.bot or member.id == ticket["user_id"]:
                continue

            try:
                if add:
                    await channel.set_permissions(member, view_channel=True, send_messages=True,
                                                  read_message_history=True, attach_files=True,
                                                  reason=f"Ajouté au ticket par {interaction.user}")
                else:
                    await channel.set_permissions(member, overwrite=None,
                                                  reason=f"Retiré du ticket par {interaction.user}")
                done.append(member.mention)
            except discord.HTTPException:
                continue

        if not done:
            return "Personne n'a été modifié (le propriétaire du ticket et les bots ne comptent pas)."

        verb = "ajouté(s) au" if add else "retiré(s) du"

        try:
            await channel.send(
                embed=discord.Embed(description=f"👥 {', '.join(done)} {verb} ticket par {interaction.user.mention}.",
                                    color=COLOR),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass

        return f"✅ {', '.join(done)} {verb} ticket."

    # -------- fermeture --------

    def cancel_close(self, ticket_id: int) -> bool:
        task = self.closing.pop(ticket_id, None)

        if task is None or task.done():
            return False

        task.cancel()
        return True

    async def schedule_close(self, interaction: discord.Interaction, ticket_id: int) -> None:
        ticket = await self.get_ticket(ticket_id)
        channel = interaction.guild.get_channel(ticket["channel_id"] or 0) if ticket else None

        if channel is None or ticket_id in self.closing:
            return

        try:
            await channel.send(
                embed=discord.Embed(
                    description=f"🔒 {interaction.user.mention} ferme le ticket : suppression dans "
                                f"**{CLOSE_DELAY} secondes**.",
                    color=WAITING_COLOR,
                ),
                view=CancelCloseView(self, ticket_id),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass

        self.closing[ticket_id] = asyncio.create_task(self._close_later(ticket_id, interaction.user))

    async def _close_later(self, ticket_id: int, closer: discord.Member) -> None:
        try:
            await asyncio.sleep(CLOSE_DELAY)
        except asyncio.CancelledError:
            return

        try:
            await self.finalize(ticket_id, closer)
        except Exception:
            LOGGER.exception("Fermeture du ticket %s impossible", ticket_id)
        finally:
            self.closing.pop(ticket_id, None)

    async def finalize(self, ticket_id: int, closer: Any) -> None:
        pool = self.get_pool()
        ticket = await pool.fetchrow(
            """
            UPDATE tickets SET status = 'closed', closed_at = NOW(), closed_by = $2
            WHERE id = $1 AND status = 'open' RETURNING *
            """,
            ticket_id, closer.id,
        )

        if ticket is None:
            return

        guild = self.bot.get_guild(ticket["guild_id"])

        if guild is None:
            return

        settings = await self.get_settings(guild.id)
        ticket_type = await self.get_type(ticket["type_id"]) or {"label": "?", "emoji": ""}
        channel = guild.get_channel(ticket["channel_id"] or 0)
        member = guild.get_member(ticket["user_id"]) or self.bot.get_user(ticket["user_id"])
        member_label = f"{member.name} ({ticket['user_id']})" if member else str(ticket["user_id"])
        messages: list[Any] = []

        if isinstance(channel, discord.TextChannel):
            try:
                messages = [message async for message in
                            channel.history(limit=MAX_TRANSCRIPT_MESSAGES, oldest_first=True)]
            except discord.HTTPException:
                LOGGER.warning("Historique du ticket %s illisible", ticket_id)

        text = transcript_text(ticket, ticket_type["label"], member_label, f"{closer.name}", messages,
                               ticket["closed_at"])
        filename = f"ticket-{ticket['number']:04d}.txt"
        summary = discord.Embed(title=f"🔒 Ticket n°{ticket['number']:04d} fermé", color=ERROR_COLOR)
        summary.add_field(name="Type", value=f"{ticket_type['emoji'] or '🎫'} {ticket_type['label']}")
        summary.add_field(name="Membre", value=f"<@{ticket['user_id']}> · `{ticket['user_id']}`")
        summary.add_field(name="Fermé par", value=closer.mention)
        summary.add_field(name="Pris en charge par",
                          value=f"<@{ticket['claimed_by']}>" if ticket["claimed_by"] else "—")
        summary.add_field(name="Durée", value=duration_text(ticket["opened_at"], ticket["closed_at"]))
        summary.add_field(name="Messages", value=str(len(messages)))
        summary.add_field(name="Raison", value=ticket["reason"][:1000], inline=False)

        await self.log(guild, settings, summary,
                       discord.File(io.BytesIO(text.encode("utf-8")), filename=filename))

        if member is not None:
            try:
                await member.send(
                    embed=discord.Embed(
                        description=f"🔒 Ton ticket **n°{ticket['number']:04d}** sur **{guild.name}** est fermé.\n"
                                    "Voici la conversation, si tu veux la garder.",
                        color=COLOR,
                    ),
                    file=discord.File(io.BytesIO(text.encode("utf-8")), filename=filename),
                )
            except (discord.HTTPException, AttributeError):
                pass

        if isinstance(channel, discord.TextChannel):
            try:
                await channel.delete(reason=f"Ticket n°{ticket['number']} fermé par {closer}")
            except discord.HTTPException:
                LOGGER.warning("Salon du ticket %s non supprimé", ticket_id)

    async def log(self, guild: discord.Guild, settings: dict[str, Any], embed: discord.Embed,
                  file: discord.File | None = None) -> None:
        channel = guild.get_channel(settings["log_channel_id"] or 0)

        if not isinstance(channel, discord.abc.Messageable):
            return

        try:
            kwargs: dict[str, Any] = {"embed": embed, "allowed_mentions": discord.AllowedMentions.none()}

            if file is not None:
                kwargs["file"] = file

            await channel.send(**kwargs)
        except discord.HTTPException:
            LOGGER.warning("Log de ticket non envoyé")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Salon de ticket supprimé à la main : le ticket est marqué fermé."""
        try:
            await self.get_pool().execute(
                """
                UPDATE tickets SET status = 'closed', closed_at = NOW()
                WHERE channel_id = $1 AND status = 'open'
                """,
                channel.id,
            )
        except Exception:
            LOGGER.exception("Ticket du salon supprimé non mis à jour")

    # -------- commande --------

    @app_commands.command(name="ticket-admin", description="Configure le système de tickets.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def ticket_admin(self, interaction: discord.Interaction) -> None:
        settings = await self.get_settings(interaction.guild_id)
        types = await self.get_types(interaction.guild_id)
        panel = AdminPanel(self, interaction, settings, types, await self.open_count(interaction.guild_id))
        await interaction.response.send_message(embed=panel.embed(), view=panel, ephemeral=True)
        remember_origin(panel, interaction)


async def setup(bot: commands.Bot) -> None:
    cog = Tickets(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)
    bot.add_dynamic_items(OpenTicketButton, TicketActionButton)
    LOGGER.info("Tickets chargés")
