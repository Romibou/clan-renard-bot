"""
Rôles personnalisés, achetés dans /boutique et validés par le staff.

Parcours :

1. /boutique → 🎨 Rôle perso : le membre choisit un nom, une couleur et
   un emoji (ajouté après le nom), puis paie.
2. La demande part dans le salon de validation choisi dans
   /boutique-admin → 🎨 Rôles perso. Le staff (Gérer les rôles) accepte
   ou refuse ; un refus rembourse le membre.
3. Accepté : le bot crée le rôle tout en bas de la liste (sa couleur ne
   passe donc pas devant celle des autres rôles) et le donne au membre.
4. /role-perso : voir la date de fin, changer la couleur (tout de suite),
   le nom ou l'emoji (de nouveau validé par le staff), prolonger en
   repayant, ou supprimer son rôle.
5. Rappel en MP 7 jours avant la fin ; à la fin, le rôle est supprimé.
   Il est aussi supprimé si le membre quitte le serveur.

Le rôle n'est pas mentionnable : Discord ne permet pas de réserver la
mention d'un rôle à une seule personne (ce serait tout le monde ou personne).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.shared.member_list import short
from bot.shared.panels import first_value

LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WAITING_COLOR = discord.Color.from_rgb(235, 174, 65)

DEFAULT_PRICE = 50_000
DEFAULT_DAYS = 90
MAX_PRICE = 10_000_000
MAX_DAYS = 3650
REMINDER_BEFORE = timedelta(days=7)
NAME_MIN, NAME_MAX = 2, 25
# Discord refuse plus de 250 rôles par serveur : on garde de la marge.
MAX_GUILD_ROLES = 245

OPEN_STATUSES = ("pending", "active")


# ============================================================
# VALIDATION (fonctions pures, testées)
# ============================================================

ZWJ = 0x200D
VARIATION = 0xFE0F
KEYCAP = 0x20E3


def is_emoji_base(code: int) -> bool:
    """Caractère qui s'affiche comme un emoji (hors modificateurs)."""
    return (
        0x1F000 <= code <= 0x1FAFF
        or 0x2600 <= code <= 0x27BF
        or 0x2300 <= code <= 0x23FF
        or 0x2B00 <= code <= 0x2BFF
        or 0x2190 <= code <= 0x21FF
        or 0x25A0 <= code <= 0x25FF
        or code in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x24C2, 0x2934, 0x2935, 0x3030, 0x303D, 0x3297, 0x3299)
    )


def is_modifier(code: int) -> bool:
    return (
        code in (ZWJ, VARIATION, KEYCAP)
        or 0x1F3FB <= code <= 0x1F3FF  # couleurs de peau
        or 0xE0020 <= code <= 0xE007F  # drapeaux régionaux (tags)
    )


def has_emoji(text: str) -> bool:
    return any(is_emoji_base(ord(char)) for char in text) or "<:" in text or "<a:" in text


def clean_emoji(text: str) -> str:
    """Un seul emoji Unicode (ou rien). Les emojis du serveur ne marchent pas dans un nom de rôle."""
    value = (text or "").strip()

    if not value:
        return ""

    if value.startswith("<") or re.fullmatch(r":\w+:", value):
        raise ValueError(
            "Les emojis personnalisés du serveur ne s'affichent pas dans un nom de rôle : "
            "choisis un emoji classique (🦊, 🌸, ⭐…)."
        )

    codes = [ord(char) for char in value]

    # Touches 1️⃣, #️⃣… : chiffre (+ FE0F) + 20E3.
    if KEYCAP in codes and value[0] in "0123456789#*" and all(
        code == KEYCAP or code == VARIATION for code in codes[1:]
    ):
        return value

    regional = [code for code in codes if 0x1F1E6 <= code <= 0x1F1FF]

    if regional:
        if len(regional) == 2 and len(codes) == 2:
            return value  # drapeau 🇫🇷

        raise ValueError("Un seul emoji à la fois, s'il te plaît.")

    if any(not is_emoji_base(code) and not is_modifier(code) for code in codes):
        raise ValueError("L'icône doit être un emoji (🦊, 🌸, ⭐…), sans texte.")

    # Un emoji composé (👨‍👩‍👧) est relié par des ZWJ : un seul « vrai » emoji par morceau.
    segments: list[int] = [0]

    for code in codes:
        if code == ZWJ:
            segments.append(0)
        elif is_emoji_base(code) and not is_modifier(code):
            segments[-1] += 1

    if any(count != 1 for count in segments):
        raise ValueError("Un seul emoji à la fois, s'il te plaît.")

    return value


def clean_name(text: str) -> str:
    name = re.sub(r"\s+", " ", (text or "").strip())

    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise ValueError(f"Le nom doit faire entre {NAME_MIN} et {NAME_MAX} caractères.")

    if has_emoji(name):
        raise ValueError("Pas d'emoji dans le nom : mets-le dans le champ « Icône ».")

    if "@" in name or "<" in name or "discord.gg" in name.lower():
        raise ValueError("Le nom ne peut pas contenir de « @ », de « < » ni de lien.")

    return name


def parse_color(text: str) -> int:
    value = (text or "").strip().lstrip("#")

    if len(value) == 3:
        value = "".join(char * 2 for char in value)

    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise ValueError("Couleur invalide : utilise un code comme #FF9AD5.")

    color = int(value, 16)
    # #000000 veut dire « pas de couleur » pour Discord : on prend un noir quasi pur.
    return color or 0x010101


def color_hex(color: int) -> str:
    return f"#{color:06X}"


def role_label(name: str, emoji: str) -> str:
    return f"{name} {emoji}".strip()


def ts(moment: datetime | None, style: str = "f") -> str:
    return f"<t:{int(moment.timestamp())}:{style}>" if moment else "—"


def format_coins(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


def is_staff(user: Any) -> bool:
    permissions = getattr(user, "guild_permissions", None)
    return bool(permissions and (permissions.manage_roles or permissions.administrator))


def get_cog(client: Any) -> CustomRoles | None:
    return client.get_cog("CustomRoles") if client else None


# ============================================================
# EMBEDS
# ============================================================


def request_embed(record: Any, member: Any, *, settings: dict[str, Any]) -> discord.Embed:
    """Message de validation d'un achat (salon du staff)."""
    label = role_label(record["name"], record["emoji"])
    embed = discord.Embed(
        title="🎨 Demande de rôle perso",
        description=(
            f"{member.mention if member else '<@' + str(record['user_id']) + '>'} veut le rôle "
            f"**{discord.utils.escape_markdown(label)}**."
        ),
        color=record["color"],
    )
    embed.add_field(name="Nom", value=discord.utils.escape_markdown(record["name"]), inline=True)
    embed.add_field(name="Icône", value=record["emoji"] or "*aucune*", inline=True)
    embed.add_field(name="Couleur", value=f"`{color_hex(record['color'])}` (couleur de ce message)", inline=True)
    embed.add_field(
        name="Membre",
        value=f"Compte : `{getattr(member, 'name', '?')}`\nID : `{record['user_id']}`",
        inline=True,
    )
    embed.add_field(
        name="Achat",
        value=f"{format_coins(record['price_paid'])} pièces · {settings['duration_days']} jours",
        inline=True,
    )
    embed.set_footer(text="Refuser rembourse le membre. Accepter crée le rôle et le lui donne.")
    return embed


def change_embed(change: Any, record: Any, member: Any) -> discord.Embed:
    """Message de validation d'un changement de nom ou d'emoji."""
    before = role_label(record["name"], record["emoji"])
    after = role_label(change["new_name"], change["new_emoji"])
    embed = discord.Embed(
        title="✏️ Changement de rôle perso",
        description=(
            f"{member.mention if member else '<@' + str(record['user_id']) + '>'} veut renommer son rôle.\n"
            f"**Avant :** {discord.utils.escape_markdown(before)}\n"
            f"**Après :** {discord.utils.escape_markdown(after)}"
        ),
        color=record["color"],
    )
    embed.set_footer(text=f"Compte : {getattr(member, 'name', '?')} · ID : {record['user_id']} · Gratuit")
    return embed


def decided(embed: discord.Embed, text: str, color: discord.Color) -> discord.Embed:
    embed.color = color
    embed.add_field(name="Décision", value=text, inline=False)
    embed.set_footer(text=None)
    return embed


# ============================================================
# BOUTONS PERSISTANTS DU SALON DE VALIDATION
# ============================================================


class RefuseModal(discord.ui.Modal):
    def __init__(self, kind: str, target_id: int, message: discord.Message | None) -> None:
        super().__init__(title="Refuser la demande", timeout=600)
        self.kind = kind
        self.target_id = target_id
        self.message = message
        self.reason = discord.ui.TextInput(style=discord.TextStyle.paragraph, required=False, max_length=300)
        self.add_item(
            discord.ui.Label(
                text="Raison (envoyée au membre)",
                description="Facultatif. Exemple : nom inapproprié.",
                component=self.reason,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog = get_cog(interaction.client)

        if cog is None:
            await interaction.response.send_message("Module indisponible.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        reason = self.reason.value.strip()

        if self.kind == "achat":
            text = await cog.refuse_request(interaction, self.target_id, reason, self.message)
        else:
            text = await cog.refuse_change(interaction, self.target_id, reason, self.message)

        await interaction.followup.send(text, ephemeral=True)


class DecisionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"rolepersodec:(?P<kind>achat|modif):(?P<id>[0-9]+):(?P<choice>[ar])",
):
    def __init__(self, kind: str, target_id: int, accept: bool) -> None:
        super().__init__(
            discord.ui.Button(
                label="Accepter" if accept else "Refuser",
                emoji="✅" if accept else "✖️",
                style=discord.ButtonStyle.success if accept else discord.ButtonStyle.danger,
                custom_id=f"rolepersodec:{kind}:{target_id}:{'a' if accept else 'r'}",
            )
        )
        self.kind = kind
        self.target_id = target_id
        self.accept = accept

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]
    ) -> DecisionButton:
        return cls(match["kind"], int(match["id"]), match["choice"] == "a")

    async def callback(self, interaction: discord.Interaction) -> None:
        if not is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Il faut la permission **Gérer les rôles** pour décider."), ephemeral=True
            )
            return

        cog = get_cog(interaction.client)

        if cog is None:
            await interaction.response.send_message("Module indisponible.", ephemeral=True)
            return

        if not self.accept:
            await interaction.response.send_modal(RefuseModal(self.kind, self.target_id, interaction.message))
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        if self.kind == "achat":
            text = await cog.accept_request(interaction, self.target_id, interaction.message)
        else:
            text = await cog.accept_change(interaction, self.target_id, interaction.message)

        await interaction.followup.send(text, ephemeral=True)


def decision_view(kind: str, target_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(DecisionButton(kind, target_id, True))
    view.add_item(DecisionButton(kind, target_id, False))
    return view


# ============================================================
# ACHAT (depuis /boutique)
# ============================================================


def role_inputs(modal: discord.ui.Modal, *, name: str = "", color: str = "", emoji: str = "",
                with_color: bool = True, with_name: bool = True) -> dict[str, discord.ui.TextInput]:
    fields: dict[str, discord.ui.TextInput] = {}

    if with_name:
        fields["name"] = discord.ui.TextInput(default=name or None, min_length=NAME_MIN, max_length=NAME_MAX)
        modal.add_item(discord.ui.Label(
            text="Nom du rôle", description=f"{NAME_MIN} à {NAME_MAX} caractères, sans emoji.", component=fields["name"],
        ))

    if with_color:
        fields["color"] = discord.ui.TextInput(default=color or None, placeholder="#FF9AD5", min_length=3, max_length=7)
        modal.add_item(discord.ui.Label(
            text="Couleur (code hex)", description="Exemple : #FF9AD5. Cherche « color picker » pour en trouver une.",
            component=fields["color"],
        ))

    if with_name:
        fields["emoji"] = discord.ui.TextInput(default=emoji or None, required=False, max_length=16)
        modal.add_item(discord.ui.Label(
            text="Icône (facultatif)", description="Un emoji, placé après le nom. Exemple : 🦊",
            component=fields["emoji"],
        ))

    return fields


class PurchaseModal(discord.ui.Modal):
    def __init__(self, cog: CustomRoles, settings: dict[str, Any]) -> None:
        super().__init__(title="🎨 Créer mon rôle perso", timeout=900)
        self.cog = cog
        self.settings = settings
        self.inputs = role_inputs(self)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            name = clean_name(self.inputs["name"].value)
            color = parse_color(self.inputs["color"].value)
            emoji = clean_emoji(self.inputs["emoji"].value)
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        view = ConfirmPurchaseView(self.cog, interaction.user.id, name, color, emoji, self.settings)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)


class ConfirmPurchaseView(discord.ui.View):
    def __init__(self, cog: CustomRoles, owner_id: int, name: str, color: int, emoji: str,
                 settings: dict[str, Any]) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.name = name
        self.color = color
        self.emoji = emoji
        self.settings = settings
        self.confirm.label = f"Payer {format_coins(settings['price'])} pièces"

    def embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎨 Ton rôle perso",
            description=(
                f"**{discord.utils.escape_markdown(role_label(self.name, self.emoji))}**\n\n"
                f"🎨 Couleur : `{color_hex(self.color)}` (la couleur de ce message)\n"
                f"⏳ Durée : **{self.settings['duration_days']} jours** à partir de la validation\n"
                f"💰 Prix : **{format_coins(self.settings['price'])} pièces**\n\n"
                "Ta demande sera **vérifiée par le staff**. Si elle est refusée, tu es **remboursé**.\n"
                "-# Le rôle est placé tout en bas de la liste : c'est TON rôle, pas une couleur de pseudo."
            ),
            color=self.color,
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="Payer", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="⏳ Envoi de ta demande…", color=WAITING_COLOR), view=None
        )
        embed = await self.cog.create_request(interaction, self.name, self.color, self.emoji)
        await interaction.edit_original_response(embed=embed)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="Annulé, rien n'a été payé.", color=COLOR), view=None
        )


def intro_embed(settings: dict[str, Any]) -> discord.Embed:
    """Présentation du rôle perso (prix, durée, règles) avant le formulaire."""
    embed = discord.Embed(
        title="🎨 Ton rôle perso",
        description=(
            "Crée **ton propre rôle** sur le serveur : tu choisis son nom, sa couleur et son icône.\n"
            "Il apparaît sur ton profil Discord, dans la liste des rôles."
        ),
        color=COLOR,
    )
    embed.add_field(name="💰 Prix", value=f"**{format_coins(settings['price'])} pièces**", inline=True)
    embed.add_field(name="⏳ Durée", value=f"**{settings['duration_days']} jours**, prolongeable", inline=True)
    embed.add_field(
        name="📝 Ce que tu choisis",
        value=(
            f"• **Nom** : {NAME_MIN} à {NAME_MAX} caractères, sans emoji\n"
            "• **Couleur** : un code hex, par exemple `#FF9AD5`\n"
            "• **Icône** (facultatif) : un emoji placé après le nom, par exemple « Renard 🦊 »"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛡️ Validation",
        value=(
            "Le staff vérifie chaque demande. **Refusée = remboursée.**\n"
            "Tu paies seulement après avoir vu le récapitulatif."
        ),
        inline=False,
    )
    embed.set_footer(text="Ensuite : /role-perso pour voir la date de fin, changer la couleur, le nom ou prolonger.")
    return embed


class IntroView(discord.ui.View):
    def __init__(self, cog: CustomRoles, owner_id: int, settings: dict[str, Any]) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.settings = settings

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="Configurer mon rôle perso", emoji="🎨", style=discord.ButtonStyle.success)
    async def configure(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(PurchaseModal(self.cog, self.settings))


class CustomRoleShopButton(discord.ui.Button):
    """Bouton ajouté à /boutique quand les rôles perso sont activés."""

    def __init__(self, price: int) -> None:
        super().__init__(label="Rôle perso", emoji="🎨", style=discord.ButtonStyle.primary, row=1)
        self.price = price

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = get_cog(interaction.client)

        if cog is None:
            await interaction.response.send_message("Module indisponible.", ephemeral=True)
            return

        await cog.open_purchase(interaction)


# ============================================================
# PANNEAU MEMBRE : /role-perso
# ============================================================


class NameEmojiModal(discord.ui.Modal):
    def __init__(self, panel: MemberPanel) -> None:
        super().__init__(title="✏️ Nom et icône", timeout=900)
        self.panel = panel
        record = panel.record
        self.inputs = role_inputs(self, name=record["name"], emoji=record["emoji"], with_color=False)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            name = clean_name(self.inputs["name"].value)
            emoji = clean_emoji(self.inputs["emoji"].value)
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await self.panel.cog.request_change(interaction, self.panel.record, name, emoji)
        await interaction.followup.send(text, ephemeral=True)
        await self.panel.reload()


class ColorModal(discord.ui.Modal):
    def __init__(self, panel: MemberPanel) -> None:
        super().__init__(title="🎨 Couleur", timeout=900)
        self.panel = panel
        self.inputs = role_inputs(self, color=color_hex(panel.record["color"]), with_name=False)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            color = parse_color(self.inputs["color"].value)
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await self.panel.cog.change_color(interaction, self.panel.record, color)
        await interaction.followup.send(text, ephemeral=True)
        await self.panel.reload()


class ConfirmView(discord.ui.View):
    """Petite confirmation « Oui / Annuler » qui appelle `action`."""

    def __init__(self, owner_id: int, label: str, style: discord.ButtonStyle, action) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.action = action
        self.yes.label = label
        self.yes.style = style

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="Oui", emoji="✅")
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="⏳ Un instant…", color=WAITING_COLOR), view=None
        )
        text = await self.action(interaction)
        await interaction.edit_original_response(embed=discord.Embed(description=text, color=COLOR))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="Annulé.", color=COLOR), view=None
        )


class MemberPanel(discord.ui.View):
    def __init__(self, cog: CustomRoles, interaction: discord.Interaction, record: Any,
                 change: Any, settings: dict[str, Any]) -> None:
        super().__init__(timeout=900)
        self.cog = cog
        self.origin = interaction
        self.owner_id = interaction.user.id
        self.record = record
        self.change = change
        self.settings = settings
        self.build()

    def build(self) -> None:
        self.clear_items()

        if self.record is None or self.record["status"] != "active":
            return

        buttons = [
            ("Nom et icône", "✏️", discord.ButtonStyle.primary, self.on_name, self.change is not None),
            ("Couleur", "🎨", discord.ButtonStyle.secondary, self.on_color, False),
            (f"Prolonger ({format_coins(self.settings['price'])} pièces)", "⏳",
             discord.ButtonStyle.success, self.on_extend, False),
            ("Supprimer mon rôle", "🗑️", discord.ButtonStyle.danger, self.on_delete, False),
        ]

        for label, emoji, style, callback, disabled in buttons:
            button = discord.ui.Button(label=label, emoji=emoji, style=style, disabled=disabled)
            button.callback = callback
            self.add_item(button)

    def embed(self) -> discord.Embed:
        record = self.record

        if record is None:
            return discord.Embed(
                title="🎨 Ton rôle perso",
                description=(
                    "Tu n'as pas de rôle perso.\n"
                    + (
                        f"Crée le tien dans `/boutique` → **🎨 Rôle perso** "
                        f"({format_coins(self.settings['price'])} pièces, {self.settings['duration_days']} jours)."
                        if self.settings["enabled"]
                        else "Les rôles perso ne sont pas disponibles pour le moment."
                    )
                ),
                color=COLOR,
            )

        label = discord.utils.escape_markdown(role_label(record["name"], record["emoji"]))

        if record["status"] == "pending":
            return discord.Embed(
                title="🎨 Ton rôle perso",
                description=(
                    f"⏳ Ta demande **{label}** attend la validation du staff.\n"
                    "Tu recevras un message privé dès qu'elle est traitée. Si elle est refusée, tu es remboursé."
                ),
                color=WAITING_COLOR,
            )

        lines = [
            f"**Rôle :** <@&{record['role_id']}>",
            f"**Nom :** {label}",
            f"**Couleur :** `{color_hex(record['color'])}`",
            f"**Créé le :** {ts(record['decided_at'], 'D')}",
            f"**Se termine le :** {ts(record['expires_at'], 'F')} ({ts(record['expires_at'], 'R')})",
        ]

        if self.change is not None:
            lines.append(
                f"\n✏️ Changement en attente de validation : "
                f"**{discord.utils.escape_markdown(role_label(self.change['new_name'], self.change['new_emoji']))}**"
            )

        lines.append(
            "\n-# 🎨 La couleur change tout de suite · ✏️ le nom et l'icône sont vérifiés par le staff (gratuit)"
        )
        return discord.Embed(title="🎨 Ton rôle perso", description="\n".join(lines), color=record["color"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def reload(self) -> None:
        self.record, self.change = await self.cog.member_state(self.origin.guild_id, self.owner_id)
        self.build()

        try:
            await self.origin.edit_original_response(embed=self.embed(), view=self)
        except discord.HTTPException:
            pass

    async def on_name(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(NameEmojiModal(self))

    async def on_color(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ColorModal(self))

    async def on_extend(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.get_settings(interaction.guild_id)
        new_end = max(self.record["expires_at"], datetime.now(timezone.utc)) + timedelta(days=settings["duration_days"])

        async def action(confirm_interaction: discord.Interaction) -> str:
            text = await self.cog.extend(confirm_interaction, self.record["id"])
            await self.reload()
            return text

        await interaction.response.send_message(
            embed=discord.Embed(
                description=(
                    f"Prolonger ton rôle de **{settings['duration_days']} jours** pour "
                    f"**{format_coins(settings['price'])} pièces** ?\nNouvelle fin : {ts(new_end, 'D')}."
                ),
                color=COLOR,
            ),
            view=ConfirmView(self.owner_id, f"Payer {format_coins(settings['price'])} pièces",
                             discord.ButtonStyle.success, action),
            ephemeral=True,
        )

    async def on_delete(self, interaction: discord.Interaction) -> None:
        async def action(confirm_interaction: discord.Interaction) -> str:
            text = await self.cog.end_role(self.record["id"], "removed", reason="supprimé par son propriétaire")
            await self.reload()
            return text or "🗑️ Ton rôle perso a été supprimé."

        await interaction.response.send_message(
            embed=discord.Embed(
                description="Supprimer ton rôle perso ? **Ce n'est pas remboursé** et c'est définitif.",
                color=ERROR_COLOR,
            ),
            view=ConfirmView(self.owner_id, "Oui, supprimer", discord.ButtonStyle.danger, action),
            ephemeral=True,
        )


# ============================================================
# PANNEAU ADMIN (depuis /boutique-admin)
# ============================================================


class SettingsModal(discord.ui.Modal):
    def __init__(self, panel: AdminPanel) -> None:
        super().__init__(title="⚙️ Rôles perso", timeout=900)
        self.panel = panel
        settings = panel.settings
        self.state = discord.ui.Select(options=[
            discord.SelectOption(label="Activés", value="on", emoji="✅", default=settings["enabled"]),
            discord.SelectOption(label="Désactivés", value="off", emoji="⏸️", default=not settings["enabled"]),
        ])
        self.add_item(discord.ui.Label(text="Achat dans /boutique", component=self.state))
        self.price = discord.ui.TextInput(default=str(settings["price"]), max_length=9)
        self.add_item(discord.ui.Label(text="Prix (pièces)", component=self.price))
        self.days = discord.ui.TextInput(default=str(settings["duration_days"]), max_length=4)
        self.add_item(discord.ui.Label(
            text="Durée (jours)", description="90 = 3 mois. Valable aussi pour chaque prolongation.", component=self.days,
        ))
        channel = panel.guild.get_channel(settings["review_channel_id"] or 0)
        self.channel = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text], default_values=[channel] if channel else [],
            min_values=1, max_values=1,
        )
        self.add_item(discord.ui.Label(
            text="Salon des demandes", description="Où le staff accepte ou refuse (garde-le privé).",
            component=self.channel,
        ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        price, days = self.price.value.replace(" ", ""), self.days.value.strip()

        if not price.isdigit() or not 0 <= int(price) <= MAX_PRICE:
            await interaction.response.send_message(
                embed=error_embed(f"Prix : un nombre entre 0 et {format_coins(MAX_PRICE)}."), ephemeral=True)
            return

        if not days.isdigit() or not 1 <= int(days) <= MAX_DAYS:
            await interaction.response.send_message(
                embed=error_embed(f"Durée : un nombre de jours entre 1 et {MAX_DAYS}."), ephemeral=True)
            return

        channel = first_value(self.channel)

        if channel is None:
            await interaction.response.send_message(
                embed=error_embed("Choisis le salon des demandes."), ephemeral=True)
            return

        settings = {
            "enabled": first_value(self.state, "off") == "on",
            "price": int(price),
            "duration_days": int(days),
            "review_channel_id": channel.id,
        }
        await self.panel.cog.save_settings(interaction.guild_id, settings)
        warning = self.panel.cog.channel_problem(interaction.guild, settings["review_channel_id"])
        await self.panel.refresh(interaction, notice=warning or "✅ Réglages enregistrés.")


class RemoveRoleModal(discord.ui.Modal):
    def __init__(self, panel: AdminPanel) -> None:
        super().__init__(title="🗑️ Retirer un rôle perso", timeout=600)
        self.panel = panel
        self.user = discord.ui.UserSelect(min_values=1, max_values=1)
        self.add_item(discord.ui.Label(text="Membre", component=self.user))
        self.reason = discord.ui.TextInput(required=False, max_length=200)
        self.add_item(discord.ui.Label(text="Raison (envoyée au membre)", component=self.reason))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        user = first_value(self.user)

        if user is None:
            await interaction.response.send_message(embed=error_embed("Choisis un membre."), ephemeral=True)
            return
        record, _change = await self.panel.cog.member_state(interaction.guild_id, user.id)

        if record is None or record["status"] != "active":
            await interaction.response.send_message(
                embed=error_embed(f"{user.mention} n'a pas de rôle perso actif."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await self.panel.cog.end_role(
            record["id"], "removed", reason=self.reason.value.strip() or "retiré par le staff", by_staff=True,
        )
        await interaction.followup.send(text or f"🗑️ Rôle perso de {user.mention} supprimé.", ephemeral=True)
        await self.panel.refresh(None)


class AdminPanel(discord.ui.View):
    def __init__(self, cog: CustomRoles, interaction: discord.Interaction, settings: dict[str, Any],
                 counts: dict[str, int]) -> None:
        super().__init__(timeout=900)
        self.cog = cog
        self.origin = interaction
        self.guild = interaction.guild
        self.owner_id = interaction.user.id
        self.settings = settings
        self.counts = counts

    def embed(self, notice: str | None = None) -> discord.Embed:
        settings = self.settings
        channel = f"<#{settings['review_channel_id']}>" if settings["review_channel_id"] else "*à choisir*"
        lines = [
            f"État : **{'activés ✅' if settings['enabled'] else 'désactivés ⏸️'}**",
            f"Prix : **{format_coins(settings['price'])} pièces** · Durée : **{settings['duration_days']} jours**",
            f"Salon des demandes : {channel}",
            "",
            f"🟢 Rôles actifs : **{self.counts.get('active', 0)}** · "
            f"⏳ Demandes en attente : **{self.counts.get('pending', 0)}**",
            "",
            "-# Le membre choisit nom, couleur et emoji, paie, puis le staff valide dans le salon. "
            "Refus = remboursement. Le rôle est créé tout en bas, non mentionnable, et supprimé à la fin "
            "(rappel en MP 7 jours avant) ou si le membre part.",
        ]

        if notice:
            lines += ["", f"> {notice}"]

        return discord.Embed(title="🎨 Rôles perso — réglages", description="\n".join(lines), color=COLOR)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def refresh(self, interaction: discord.Interaction | None, *, notice: str | None = None) -> None:
        self.settings = await self.cog.get_settings(self.guild.id)
        self.counts = await self.cog.counts(self.guild.id)
        kwargs = {"embed": self.embed(notice), "view": self}

        if interaction is None:
            try:
                await self.origin.edit_original_response(**kwargs)
            except discord.HTTPException:
                pass
        else:
            await interaction.response.edit_message(**kwargs)

    @discord.ui.button(label="Réglages", emoji="⚙️", style=discord.ButtonStyle.primary)
    async def settings_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SettingsModal(self))

    @discord.ui.button(label="Liste des rôles", emoji="📋", style=discord.ButtonStyle.secondary)
    async def list_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        rows = await self.cog.active_roles(self.guild.id)
        await interaction.response.send_message(embed=active_roles_embed(rows, self.guild), ephemeral=True)

    @discord.ui.button(label="Retirer un rôle", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(RemoveRoleModal(self))


def active_roles_table(rows: list[Any], guild: Any) -> str:
    """Tableau aligné : n°, compte du membre, nom du rôle, date de fin."""
    if not rows:
        return "Aucun rôle perso actif."

    entries = []

    for number, row in enumerate(rows, 1):
        member = guild.get_member(row["user_id"]) if guild else None
        account = member.name if member else str(row["user_id"])
        entries.append((str(number), short(account, 16), short(role_label(row["name"], ""), 16),
                        row["expires_at"].strftime("%d/%m/%y")))

    widths = [max(len(header), max(len(entry[index]) for entry in entries))
              for index, header in enumerate(("#", "Compte", "Rôle", "Fin"))]
    line = "{:>%d} {:<%d} {:<%d} {}" % tuple(widths[:3])
    lines = [line.format("#", "Compte", "Rôle", "Fin"), "─" * (sum(widths) + 3)]
    lines += [line.format(*entry) for entry in entries]
    return "\n".join(lines)


def active_roles_embed(rows: list[Any], guild: Any) -> discord.Embed:
    table = active_roles_table(rows[:40], guild)
    more = f"\n-# … et {len(rows) - 40} autre(s)." if len(rows) > 40 else ""
    return discord.Embed(
        title=f"📋 Rôles perso actifs ({len(rows)})",
        description=f"```\n{table}\n```{more}",
        color=COLOR,
    )


# ============================================================
# COG
# ============================================================


class CustomRoles(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def cog_load(self) -> None:
        self.expiry_loop.start()

    async def cog_unload(self) -> None:
        self.expiry_loop.cancel()

    async def initialize_database(self) -> None:
        pool = self.get_pool()
        await pool.execute(
            f"""
            CREATE TABLE IF NOT EXISTS custom_role_settings (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                price INTEGER NOT NULL DEFAULT {DEFAULT_PRICE},
                duration_days INTEGER NOT NULL DEFAULT {DEFAULT_DAYS},
                review_channel_id BIGINT
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_roles (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                name VARCHAR(40) NOT NULL,
                color INTEGER NOT NULL,
                emoji VARCHAR(32) NOT NULL DEFAULT '',
                status VARCHAR(10) NOT NULL DEFAULT 'pending',
                role_id BIGINT,
                price_paid INTEGER NOT NULL,
                duration_days INTEGER NOT NULL,
                review_channel_id BIGINT,
                review_message_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                decided_at TIMESTAMPTZ,
                decided_by BIGINT,
                expires_at TIMESTAMPTZ,
                reminded BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
        # Un seul rôle perso (en attente ou actif) par membre.
        await pool.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS custom_roles_one_open
            ON custom_roles (guild_id, user_id) WHERE status IN ('pending', 'active')
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_role_changes (
                id BIGSERIAL PRIMARY KEY,
                custom_role_id BIGINT NOT NULL REFERENCES custom_roles(id) ON DELETE CASCADE,
                new_name VARCHAR(40) NOT NULL,
                new_emoji VARCHAR(32) NOT NULL DEFAULT '',
                status VARCHAR(10) NOT NULL DEFAULT 'pending',
                review_channel_id BIGINT,
                review_message_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                decided_by BIGINT
            )
            """
        )

    # -------- réglages --------

    async def get_settings(self, guild_id: int) -> dict[str, Any]:
        row = await self.get_pool().fetchrow("SELECT * FROM custom_role_settings WHERE guild_id = $1", guild_id)

        if row is None:
            return {"enabled": False, "price": DEFAULT_PRICE, "duration_days": DEFAULT_DAYS, "review_channel_id": None}

        return {
            "enabled": bool(row["enabled"]),
            "price": int(row["price"]),
            "duration_days": int(row["duration_days"]),
            "review_channel_id": row["review_channel_id"],
        }

    async def save_settings(self, guild_id: int, settings: dict[str, Any]) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO custom_role_settings (guild_id, enabled, price, duration_days, review_channel_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE SET
                enabled = $2, price = $3, duration_days = $4, review_channel_id = $5
            """,
            guild_id, settings["enabled"], settings["price"], settings["duration_days"], settings["review_channel_id"],
        )

    def channel_problem(self, guild: discord.Guild, channel_id: int | None) -> str | None:
        channel = guild.get_channel(channel_id or 0)

        if channel is None:
            return "⚠️ Salon des demandes introuvable."

        permissions = channel.permissions_for(guild.me)
        missing = [
            name for name, ok in (
                ("Voir le salon", permissions.view_channel),
                ("Envoyer des messages", permissions.send_messages),
                ("Intégrer des liens", permissions.embed_links),
            ) if not ok
        ]

        if not guild.me.guild_permissions.manage_roles:
            missing.append("Gérer les rôles (sur le serveur)")

        return f"⚠️ Il manque au bot : {', '.join(missing)}." if missing else None

    async def shop_button(self, guild_id: int) -> CustomRoleShopButton | None:
        """Bouton à ajouter à /boutique, ou None si les rôles perso sont désactivés."""
        try:
            settings = await self.get_settings(guild_id)
        except Exception:
            LOGGER.exception("Réglages des rôles perso illisibles")
            return None

        return CustomRoleShopButton(settings["price"]) if settings["enabled"] else None

    # -------- lecture --------

    async def member_state(self, guild_id: int, user_id: int) -> tuple[Any, Any]:
        pool = self.get_pool()
        record = await pool.fetchrow(
            """
            SELECT * FROM custom_roles
            WHERE guild_id = $1 AND user_id = $2 AND status IN ('pending', 'active')
            """,
            guild_id, user_id,
        )
        change = None

        if record is not None:
            change = await pool.fetchrow(
                "SELECT * FROM custom_role_changes WHERE custom_role_id = $1 AND status = 'pending'", record["id"]
            )

        return record, change

    async def counts(self, guild_id: int) -> dict[str, int]:
        rows = await self.get_pool().fetch(
            "SELECT status, COUNT(*) AS n FROM custom_roles WHERE guild_id = $1 GROUP BY status", guild_id
        )
        return {row["status"]: int(row["n"]) for row in rows}

    async def active_roles(self, guild_id: int) -> list[Any]:
        return list(await self.get_pool().fetch(
            "SELECT * FROM custom_roles WHERE guild_id = $1 AND status = 'active' ORDER BY expires_at", guild_id
        ))

    # -------- argent --------

    @staticmethod
    async def pay(connection, guild_id: int, user_id: int, price: int, reason: str) -> bool:
        if price <= 0:
            return True

        updated = await connection.execute(
            """
            UPDATE progression_members SET wallet = wallet - $3, updated_at = NOW()
            WHERE guild_id = $1 AND user_id = $2 AND wallet >= $3
            """,
            guild_id, user_id, price,
        )

        if updated == "UPDATE 0":
            return False

        await connection.execute(
            """
            INSERT INTO progression_transactions (guild_id, user_id, actor_id, amount, transaction_type, reason)
            VALUES ($1, $2, $2, $3, 'shop_purchase', $4)
            """,
            guild_id, user_id, -price, f"Achat boutique : {reason}"[:200],
        )
        return True

    @staticmethod
    async def refund(connection, guild_id: int, user_id: int, amount: int, reason: str) -> None:
        if amount <= 0:
            return

        await connection.execute(
            """
            UPDATE progression_members SET wallet = wallet + $3, updated_at = NOW()
            WHERE guild_id = $1 AND user_id = $2
            """,
            guild_id, user_id, amount,
        )
        await connection.execute(
            """
            INSERT INTO progression_transactions (guild_id, user_id, actor_id, amount, transaction_type, reason)
            VALUES ($1, $2, NULL, $3, 'shop_refund', $4)
            """,
            guild_id, user_id, amount, f"Remboursement boutique : {reason}"[:200],
        )

    async def notify(self, user_id: int, embed: discord.Embed) -> None:
        """Message privé au membre (ignoré s'il a fermé ses MP)."""
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await user.send(embed=embed)
        except (discord.HTTPException, AttributeError):
            LOGGER.info("MP impossible au membre %s (rôle perso)", user_id)

    # -------- achat --------

    async def open_purchase(self, interaction: discord.Interaction) -> None:
        settings = await self.get_settings(interaction.guild_id)

        if not settings["enabled"]:
            await interaction.response.send_message(
                embed=error_embed("Les rôles perso ne sont pas disponibles pour le moment."), ephemeral=True)
            return

        if self.channel_problem(interaction.guild, settings["review_channel_id"]):
            await interaction.response.send_message(
                embed=error_embed("Les rôles perso ne sont pas encore prêts (salon du staff à configurer)."),
                ephemeral=True,
            )
            return

        record, _change = await self.member_state(interaction.guild_id, interaction.user.id)

        if record is not None:
            text = (
                "Ta demande de rôle perso attend déjà la validation du staff."
                if record["status"] == "pending"
                else "Tu as déjà un rôle perso : gère-le avec `/role-perso`."
            )
            await interaction.response.send_message(embed=error_embed(text), ephemeral=True)
            return

        view = IntroView(self, interaction.user.id, settings)
        await interaction.response.send_message(embed=intro_embed(settings), view=view, ephemeral=True)

    async def create_request(self, interaction: discord.Interaction, name: str, color: int, emoji: str) -> discord.Embed:
        guild = interaction.guild
        settings = await self.get_settings(guild.id)
        label = role_label(name, emoji)

        if not settings["enabled"]:
            return error_embed("Les rôles perso viennent d'être désactivés : rien n'a été payé.")

        channel = guild.get_channel(settings["review_channel_id"] or 0)

        if channel is None or self.channel_problem(guild, settings["review_channel_id"]):
            return error_embed("Le salon du staff n'est pas configuré : rien n'a été payé.")

        pool = self.get_pool()

        try:
            async with pool.acquire() as connection:
                async with connection.transaction():
                    if not await self.pay(connection, guild.id, interaction.user.id, settings["price"],
                                          f"Rôle perso « {label} »"):
                        return error_embed(f"Il te faut **{format_coins(settings['price'])} pièces**.")

                    record = await connection.fetchrow(
                        """
                        INSERT INTO custom_roles (guild_id, user_id, name, color, emoji, price_paid,
                                                  duration_days, review_channel_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        RETURNING *
                        """,
                        guild.id, interaction.user.id, name, color, emoji, settings["price"],
                        settings["duration_days"], channel.id,
                    )
        except Exception as error:
            if "custom_roles_one_open" in str(error):
                return error_embed("Tu as déjà un rôle perso ou une demande en cours : rien n'a été payé.")

            LOGGER.exception("Achat de rôle perso impossible")
            return error_embed("Erreur pendant l'achat : rien n'a été payé.")

        try:
            message = await channel.send(
                embed=request_embed(record, interaction.user, settings=settings),
                view=decision_view("achat", record["id"]),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            LOGGER.exception("Demande de rôle perso non envoyée au staff")

            async with pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("UPDATE custom_roles SET status = 'refused' WHERE id = $1", record["id"])
                    await self.refund(connection, guild.id, interaction.user.id, settings["price"],
                                      f"Rôle perso « {label} » (envoi impossible)")

            return error_embed("Impossible d'envoyer ta demande au staff : tu as été remboursé.")

        await pool.execute("UPDATE custom_roles SET review_message_id = $2 WHERE id = $1", record["id"], message.id)
        return discord.Embed(
            title="✅ Demande envoyée !",
            description=(
                f"Ton rôle **{discord.utils.escape_markdown(label)}** attend la validation du staff.\n"
                "Tu recevras un message privé dès qu'il est accepté (ou refusé et remboursé).\n"
                "Suis ta demande avec `/role-perso`."
            ),
            color=color,
        )

    async def accept_request(self, interaction: discord.Interaction, record_id: int,
                             message: discord.Message | None) -> str:
        guild = interaction.guild
        pool = self.get_pool()
        record = await pool.fetchrow("SELECT * FROM custom_roles WHERE id = $1 AND guild_id = $2", record_id, guild.id)

        if record is None or record["status"] != "pending":
            return "Cette demande a déjà été traitée."

        member = guild.get_member(record["user_id"])

        if member is None:
            await self.decide_refusal(record, interaction.user, "le membre a quitté le serveur", message)
            return "Le membre a quitté le serveur : demande refusée et remboursée."

        if len(guild.roles) >= MAX_GUILD_ROLES:
            return "❌ Le serveur a presque atteint la limite de 250 rôles de Discord : supprime des rôles d'abord."

        label = role_label(record["name"], record["emoji"])

        try:
            role = await guild.create_role(
                name=label,
                colour=discord.Colour(record["color"]),
                permissions=discord.Permissions.none(),
                hoist=False,
                mentionable=False,
                reason=f"Rôle perso de {member} (accepté par {interaction.user})",
            )
        except discord.HTTPException:
            return "❌ Impossible de créer le rôle : le bot a-t-il la permission **Gérer les rôles** ?"

        try:
            await member.add_roles(role, reason="Rôle perso")
        except discord.HTTPException:
            await self.safe_delete_role(role, "Rôle perso non attribuable")
            return "❌ Rôle créé mais impossible à donner (rôle du bot trop bas ?). Rien n'a changé."

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=int(record["duration_days"]))
        updated = await pool.execute(
            """
            UPDATE custom_roles SET status = 'active', role_id = $2, decided_at = $3, decided_by = $4,
                                    expires_at = $5, reminded = FALSE
            WHERE id = $1 AND status = 'pending'
            """,
            record_id, role.id, now, interaction.user.id, expires,
        )

        if updated == "UPDATE 0":
            # Un autre membre du staff a décidé en même temps.
            await self.safe_delete_role(role, "Décision en double")
            return "Cette demande vient d'être traitée par quelqu'un d'autre."

        await self.close_message(message, record, f"✅ Accepté par {interaction.user.mention} · fin {ts(expires, 'D')}",
                                 SUCCESS_COLOR)
        await self.notify(record["user_id"], discord.Embed(
            title="🎉 Ton rôle perso est prêt !",
            description=(
                f"Le staff de **{guild.name}** a accepté ton rôle **{discord.utils.escape_markdown(label)}**.\n"
                f"Il dure jusqu'au {ts(expires, 'D')}. Gère-le avec `/role-perso`."
            ),
            color=record["color"],
        ))
        return f"✅ Rôle {role.mention} créé et donné à {member.mention}."

    async def decide_refusal(self, record: Any, moderator: Any, reason: str, message: discord.Message | None) -> bool:
        pool = self.get_pool()
        label = role_label(record["name"], record["emoji"])

        async with pool.acquire() as connection:
            async with connection.transaction():
                updated = await connection.execute(
                    """
                    UPDATE custom_roles SET status = 'refused', decided_at = NOW(), decided_by = $2
                    WHERE id = $1 AND status = 'pending'
                    """,
                    record["id"], moderator.id,
                )

                if updated == "UPDATE 0":
                    return False

                await self.refund(connection, record["guild_id"], record["user_id"], int(record["price_paid"]),
                                  f"Rôle perso « {label} » (refusé)")

        await self.close_message(
            message, record,
            f"✖️ Refusé par {moderator.mention} · remboursé" + (f"\nRaison : {reason}" if reason else ""),
            ERROR_COLOR,
        )
        guild = self.bot.get_guild(record["guild_id"])
        await self.notify(record["user_id"], discord.Embed(
            title="Rôle perso refusé",
            description=(
                f"Le staff de **{guild.name if guild else 'ton serveur'}** a refusé ton rôle "
                f"**{discord.utils.escape_markdown(label)}**.\n"
                + (f"Raison : {reason}\n" if reason else "")
                + f"💰 Tes **{format_coins(int(record['price_paid']))} pièces** t'ont été rendues. "
                "Tu peux refaire une demande dans `/boutique`."
            ),
            color=ERROR_COLOR,
        ))
        return True

    async def refuse_request(self, interaction: discord.Interaction, record_id: int, reason: str,
                             message: discord.Message | None) -> str:
        record = await self.get_pool().fetchrow(
            "SELECT * FROM custom_roles WHERE id = $1 AND guild_id = $2", record_id, interaction.guild_id)

        if record is None or not await self.decide_refusal(record, interaction.user, reason, message):
            return "Cette demande a déjà été traitée."

        return "✖️ Demande refusée, le membre est remboursé."

    async def close_message(self, message: discord.Message | None, record: Any, text: str,
                            color: discord.Color) -> None:
        """Retire les boutons du message du staff et note la décision."""
        if message is None:
            return

        try:
            embed = message.embeds[0] if message.embeds else discord.Embed()
            await message.edit(embed=decided(embed, text, color), view=None)
        except discord.HTTPException:
            pass

    @staticmethod
    async def safe_delete_role(role: discord.Role | None, reason: str) -> None:
        if role is None:
            return

        try:
            await role.delete(reason=reason)
        except discord.HTTPException:
            LOGGER.warning("Rôle perso %s non supprimé", getattr(role, "id", "?"))

    # -------- modifications --------

    async def change_color(self, interaction: discord.Interaction, record: Any, color: int) -> str:
        role = interaction.guild.get_role(record["role_id"] or 0)

        if role is None:
            return "❌ Ton rôle est introuvable sur le serveur."

        try:
            await role.edit(colour=discord.Colour(color), reason="Rôle perso : nouvelle couleur")
        except discord.HTTPException:
            return "❌ Impossible de changer la couleur pour le moment."

        await self.get_pool().execute("UPDATE custom_roles SET color = $2 WHERE id = $1", record["id"], color)
        return f"🎨 Couleur changée en `{color_hex(color)}`."

    async def request_change(self, interaction: discord.Interaction, record: Any, name: str, emoji: str) -> str:
        if name == record["name"] and emoji == record["emoji"]:
            return "Rien n'a changé."

        settings = await self.get_settings(interaction.guild_id)
        channel = interaction.guild.get_channel(settings["review_channel_id"] or 0)

        if channel is None:
            return "❌ Le salon du staff n'est plus configuré : réessaie plus tard."

        pool = self.get_pool()

        if await pool.fetchval(
            "SELECT 1 FROM custom_role_changes WHERE custom_role_id = $1 AND status = 'pending'", record["id"]
        ):
            return "Un changement attend déjà la validation du staff."

        change = await pool.fetchrow(
            """
            INSERT INTO custom_role_changes (custom_role_id, new_name, new_emoji, review_channel_id)
            VALUES ($1, $2, $3, $4) RETURNING *
            """,
            record["id"], name, emoji, channel.id,
        )

        try:
            message = await channel.send(
                embed=change_embed(change, record, interaction.user),
                view=decision_view("modif", change["id"]),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            await pool.execute("DELETE FROM custom_role_changes WHERE id = $1", change["id"])
            return "❌ Impossible d'envoyer la demande au staff."

        await pool.execute("UPDATE custom_role_changes SET review_message_id = $2 WHERE id = $1", change["id"], message.id)
        return "✏️ Changement envoyé au staff : tu recevras un MP dès qu'il est validé."

    async def load_change(self, change_id: int, guild_id: int) -> tuple[Any, Any]:
        pool = self.get_pool()
        change = await pool.fetchrow("SELECT * FROM custom_role_changes WHERE id = $1", change_id)

        if change is None:
            return None, None

        record = await pool.fetchrow(
            "SELECT * FROM custom_roles WHERE id = $1 AND guild_id = $2", change["custom_role_id"], guild_id)
        return change, record

    async def accept_change(self, interaction: discord.Interaction, change_id: int,
                            message: discord.Message | None) -> str:
        change, record = await self.load_change(change_id, interaction.guild_id)

        if change is None or record is None or change["status"] != "pending":
            return "Cette demande a déjà été traitée."

        if record["status"] != "active":
            await self.get_pool().execute("UPDATE custom_role_changes SET status = 'refused' WHERE id = $1", change_id)
            await self.close_message(message, None, "Le rôle n'existe plus.", ERROR_COLOR)
            return "Ce rôle perso n'est plus actif."

        role = interaction.guild.get_role(record["role_id"] or 0)
        label = role_label(change["new_name"], change["new_emoji"])

        if role is None:
            return "❌ Le rôle est introuvable sur le serveur."

        try:
            await role.edit(name=label, reason=f"Rôle perso renommé (accepté par {interaction.user})")
        except discord.HTTPException:
            return "❌ Impossible de renommer le rôle (permissions du bot ?)."

        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE custom_role_changes SET status = 'accepted', decided_by = $2 WHERE id = $1",
                    change_id, interaction.user.id)
                await connection.execute(
                    "UPDATE custom_roles SET name = $2, emoji = $3 WHERE id = $1",
                    record["id"], change["new_name"], change["new_emoji"])

        await self.close_message(message, record, f"✅ Accepté par {interaction.user.mention}", SUCCESS_COLOR)
        await self.notify(record["user_id"], discord.Embed(
            description=f"✅ Ton rôle perso s'appelle maintenant **{discord.utils.escape_markdown(label)}**.",
            color=record["color"],
        ))
        return f"✅ Rôle renommé en **{discord.utils.escape_markdown(label)}**."

    async def refuse_change(self, interaction: discord.Interaction, change_id: int, reason: str,
                            message: discord.Message | None) -> str:
        change, record = await self.load_change(change_id, interaction.guild_id)

        if change is None or record is None:
            return "Cette demande a déjà été traitée."

        updated = await self.get_pool().execute(
            "UPDATE custom_role_changes SET status = 'refused', decided_by = $2 WHERE id = $1 AND status = 'pending'",
            change_id, interaction.user.id,
        )

        if updated == "UPDATE 0":
            return "Cette demande a déjà été traitée."

        await self.close_message(
            message, record,
            f"✖️ Refusé par {interaction.user.mention}" + (f"\nRaison : {reason}" if reason else ""), ERROR_COLOR,
        )
        await self.notify(record["user_id"], discord.Embed(
            description=(
                f"✖️ Le staff a refusé le nouveau nom **"
                f"{discord.utils.escape_markdown(role_label(change['new_name'], change['new_emoji']))}**."
                + (f"\nRaison : {reason}" if reason else "")
                + "\nTon rôle garde son nom actuel. Tu peux proposer autre chose avec `/role-perso`."
            ),
            color=ERROR_COLOR,
        ))
        return "✖️ Changement refusé."

    async def extend(self, interaction: discord.Interaction, record_id: int) -> str:
        settings = await self.get_settings(interaction.guild_id)
        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                record = await connection.fetchrow(
                    "SELECT * FROM custom_roles WHERE id = $1 AND status = 'active' FOR UPDATE", record_id)

                if record is None:
                    return "Ce rôle perso n'est plus actif."

                label = role_label(record["name"], record["emoji"])

                if not await self.pay(connection, record["guild_id"], record["user_id"], settings["price"],
                                      f"Prolongation du rôle perso « {label} »"):
                    return f"❌ Il te faut **{format_coins(settings['price'])} pièces**."

                new_end = max(record["expires_at"], datetime.now(timezone.utc)) + timedelta(
                    days=settings["duration_days"])
                await connection.execute(
                    "UPDATE custom_roles SET expires_at = $2, reminded = FALSE WHERE id = $1", record_id, new_end)

        return f"⏳ Rôle prolongé jusqu'au {ts(new_end, 'D')} !"

    # -------- fin de vie --------

    async def end_role(self, record_id: int, status: str, *, reason: str, by_staff: bool = False) -> str | None:
        """Supprime le rôle Discord et clôt la fiche (expired / removed)."""
        pool = self.get_pool()
        record = await pool.fetchrow(
            "UPDATE custom_roles SET status = $2 WHERE id = $1 AND status = 'active' RETURNING *", record_id, status)

        if record is None:
            return "Ce rôle perso n'est déjà plus actif."

        await pool.execute(
            "UPDATE custom_role_changes SET status = 'refused' WHERE custom_role_id = $1 AND status = 'pending'",
            record_id)
        guild = self.bot.get_guild(record["guild_id"])
        role = guild.get_role(record["role_id"] or 0) if guild else None
        await self.safe_delete_role(role, f"Rôle perso : {reason}")
        label = discord.utils.escape_markdown(role_label(record["name"], record["emoji"]))

        if status == "expired":
            await self.notify(record["user_id"], discord.Embed(
                description=(
                    f"⌛ Ton rôle perso **{label}** est arrivé à sa fin et a été supprimé.\n"
                    "Tu peux en recréer un dans `/boutique` → 🎨 Rôle perso."
                ),
                color=WAITING_COLOR,
            ))
        elif by_staff:
            await self.notify(record["user_id"], discord.Embed(
                description=f"🗑️ Ton rôle perso **{label}** a été retiré par le staff.\nRaison : {reason}",
                color=ERROR_COLOR,
            ))

        return None

    @tasks.loop(minutes=10)
    async def expiry_loop(self) -> None:
        try:
            await self.run_expiry()
        except Exception:
            LOGGER.exception("Vérification des rôles perso impossible")

    @expiry_loop.before_loop
    async def before_expiry(self) -> None:
        await self.bot.wait_until_ready()

    async def run_expiry(self) -> None:
        pool = self.get_pool()
        now = datetime.now(timezone.utc)

        for record in await pool.fetch(
            "SELECT * FROM custom_roles WHERE status = 'active' AND expires_at <= $1", now
        ):
            await self.end_role(record["id"], "expired", reason="durée terminée")

        for record in await pool.fetch(
            """
            SELECT * FROM custom_roles
            WHERE status = 'active' AND reminded = FALSE AND expires_at <= $1
            """,
            now + REMINDER_BEFORE,
        ):
            await pool.execute("UPDATE custom_roles SET reminded = TRUE WHERE id = $1", record["id"])
            await self.notify(record["user_id"], discord.Embed(
                description=(
                    f"⏳ Ton rôle perso **{discord.utils.escape_markdown(role_label(record['name'], record['emoji']))}** "
                    f"se termine {ts(record['expires_at'], 'R')} ({ts(record['expires_at'], 'D')}).\n"
                    "Prolonge-le avec `/role-perso` → ⏳ Prolonger."
                ),
                color=WAITING_COLOR,
            ))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        try:
            record, _change = await self.member_state(member.guild.id, member.id)

            if record is not None and record["status"] == "active":
                await self.end_role(record["id"], "removed", reason="le membre a quitté le serveur")
        except Exception:
            LOGGER.exception("Rôle perso d'un membre parti non supprimé")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Rôle supprimé à la main : la fiche est close (sans MP)."""
        try:
            await self.get_pool().execute(
                "UPDATE custom_roles SET status = 'removed' WHERE role_id = $1 AND status = 'active'", role.id)
        except Exception:
            LOGGER.exception("Fiche de rôle perso non mise à jour")

    # -------- commandes --------

    @app_commands.command(name="role-perso", description="Voir et gérer ton rôle personnalisé.")
    @app_commands.guild_only()
    async def role_perso(self, interaction: discord.Interaction) -> None:
        settings = await self.get_settings(interaction.guild_id)
        record, change = await self.member_state(interaction.guild_id, interaction.user.id)
        panel = MemberPanel(self, interaction, record, change, settings)
        await interaction.response.send_message(embed=panel.embed(), view=panel, ephemeral=True)

    async def open_admin(self, interaction: discord.Interaction) -> None:
        """Ouvert depuis /boutique-admin → 🎨 Rôles perso."""
        settings = await self.get_settings(interaction.guild_id)
        counts = await self.counts(interaction.guild_id)
        panel = AdminPanel(self, interaction, settings, counts)
        await interaction.response.send_message(embed=panel.embed(), view=panel, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = CustomRoles(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)
    bot.add_dynamic_items(DecisionButton)
    LOGGER.info("Rôles perso chargés")
