"""
Messages de bienvenue et de départ avec une carte image, à la Koya.

/bienvenue-admin ouvre un panneau avec l'aperçu de la carte :
salon, textes (avec variables), fond personnalisé, couleurs,
assombrissement, disposition, carte oui/non, test dans le salon.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageOps

from bot.shared.checks import unsafe_role_reason
from bot.shared.member_list import MemberPagesView
from bot.shared.member_list import member_list_file as shared_member_list_file
from bot.shared.welcome_card import (
    FONT_NAMES,
    HEIGHT,
    LAYOUTS,
    MAX_FONT_BYTES,
    TEXT_EFFECTS,
    WIDTH,
    has_custom_font,
    install_custom_font,
    parse_hex,
    render_welcome_card,
)

LOGGER = logging.getLogger(__name__)

JOIN, LEAVE = "join", "leave"
KIND_NAMES = {JOIN: "👋 Arrivées", LEAVE: "🚪 Départs"}
# Le fond est recadré en 1024 x 500 puis compressé (~150 Ko) : le fichier
# envoyé peut être gros. La vraie limite est souvent celle de Discord
# pour le compte qui envoie (10 Mo sans Nitro).
MAX_BACKGROUND_BYTES = 50 * 1024 * 1024
MAX_AUTOROLES = 3
MAX_BACKGROUND_PIXELS = 50_000_000  # 50 mégapixels, largement assez pour un fond

DEFAULTS: dict[str, dict[str, Any]] = {
    JOIN: {
        "enabled": False,
        "channel_id": None,
        "message": "Bienvenue {membre} !",
        "title": "Bienvenue",
        "subtitle": "{nom}",
        "text": "Nous sommes {nombre} à présent !",
        "layout": "centre",
        "overlay": 35,
        "title_color": "#FFFFFF",
        "subtitle_color": "#FF9AD5",
        "text_color": "#FFFFFF",
        "border_color": "#FFFFFF",
        # Effet derrière les textes (comme Koya) : ombre douce par défaut.
        "text_effect": "ombre",
        "shadow_color": "#000000",
        "shadow_opacity": 70,
        "shadow_blur": 4,
        "shadow_offset": 4,
        "font": "roboto",
        "card": True,
        # Rôles donnés à chaque nouveau membre (gardés ensuite). Vide = aucun.
        "autoroles": [],
    },
    LEAVE: {
        "enabled": False,
        "channel_id": None,
        "message": "**{nom}** nous a quittés.",
        "title": "Au revoir",
        "subtitle": "{nom}",
        "text": "Nous sommes {nombre} à présent.",
        "layout": "centre",
        "overlay": 45,
        "title_color": "#FFFFFF",
        "subtitle_color": "#9AD1FF",
        "text_color": "#FFFFFF",
        "border_color": "#FFFFFF",
        # Effet derrière les textes (comme Koya) : ombre douce par défaut.
        "text_effect": "ombre",
        "shadow_color": "#000000",
        "shadow_opacity": 70,
        "shadow_blur": 4,
        "shadow_offset": 4,
        "font": "roboto",
        "card": True,
    },
}

VARIABLES_HELP = (
    "`{membre}` mention du membre (dans le message ; son nom sur la carte)\n"
    "`{nom}` nom affiché sur le serveur · `{pseudo}` nom d'utilisateur\n"
    "`{serveur}` nom du serveur · `{nombre}` nombre de membres"
)

COLOR = discord.Color.from_rgb(242, 140, 40)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


def fill_variables(text: str, member: Any, *, on_card: bool = False) -> str:
    guild = member.guild
    values = {
        "{membre}": member.display_name if on_card else member.mention,
        "{nom}": member.display_name,
        "{pseudo}": member.name,
        "{serveur}": guild.name,
        "{nombre}": f"{guild.member_count or len(guild.members):,}".replace(",", " "),
    }

    for key, value in values.items():
        text = text.replace(key, value)

    return text


def merge_settings(kind: str, stored: dict[str, Any] | None) -> dict[str, Any]:
    settings = dict(DEFAULTS[kind])

    for key, value in (stored or {}).items():
        if key in settings:
            settings[key] = value

    if settings["layout"] not in LAYOUTS:
        settings["layout"] = "centre"

    settings["overlay"] = max(0, min(90, int(settings["overlay"] or 0)))

    if settings["font"] not in FONT_NAMES:
        settings["font"] = "roboto"

    if settings["text_effect"] not in TEXT_EFFECTS:
        settings["text_effect"] = "ombre"

    for key, top in (("shadow_opacity", 100), ("shadow_blur", 20), ("shadow_offset", 20)):
        try:
            settings[key] = max(0, min(top, int(settings[key])))
        except (TypeError, ValueError):
            settings[key] = DEFAULTS[kind][key]

    return settings


def prepare_background(data: bytes) -> bytes:
    """Recadre au format de la carte et compresse (fond plus léger en base)."""
    image = Image.open(io.BytesIO(data))

    if image.width * image.height > MAX_BACKGROUND_PIXELS:
        raise ValueError("Image trop grande en pixels.")

    # Une grosse photo JPEG est décodée directement en plus petit :
    # beaucoup moins de mémoire utilisée sur le serveur.
    image.draft("RGB", (WIDTH * 2, HEIGHT * 2))
    image = ImageOps.exif_transpose(image).convert("RGB")
    image = ImageOps.fit(image, (WIDTH, HEIGHT), Image.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def normalize_color(text: str, name: str) -> str:
    cleaned = text.strip()

    if not cleaned:
        raise ValueError(f"{name} : indique une couleur, par exemple #FF9AD5.")

    rgb = parse_hex(cleaned, (-1, -1, -1))

    if rgb == (-1, -1, -1):
        raise ValueError(f"{name} : « {cleaned[:20]} » n'est pas une couleur (exemple : #FF9AD5).")

    return "#{:02X}{:02X}{:02X}".format(*rgb)


# ============================================================
# FENÊTRES DE SAISIE
# ============================================================


def labeled_input(modal: discord.ui.Modal, text: str, default: str, *, description: str | None = None,
                  paragraph: bool = False, max_length: int = 100, required: bool = False) -> discord.ui.TextInput:
    component = discord.ui.TextInput(
        style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short,
        default=default[:max_length] if default else None,
        max_length=max_length,
        required=required,
    )
    modal.add_item(discord.ui.Label(text=text, description=description, component=component))
    return component


class PanelModal(discord.ui.Modal):
    def __init__(self, panel: WelcomePanel, title: str) -> None:
        super().__init__(title=title, timeout=600)
        self.panel = panel

    @property
    def settings(self) -> dict[str, Any]:
        return self.panel.settings

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            notice = await self.apply(interaction)
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        await self.panel.save()
        await self.panel.refresh(interaction, notice=notice)

    async def apply(self, interaction: discord.Interaction) -> str | None:
        raise NotImplementedError


class ChannelModal(PanelModal):
    def __init__(self, panel: WelcomePanel) -> None:
        super().__init__(panel, "📍 Salon")
        channel = panel.guild.get_channel(self.settings["channel_id"] or 0)
        self.channel = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            default_values=[channel] if channel else [],
            min_values=1,
            max_values=1,
        )
        self.add_item(discord.ui.Label(text="Salon des messages", component=self.channel))

    async def apply(self, interaction: discord.Interaction) -> str | None:
        self.settings["channel_id"] = self.channel.values[0].id
        return self.panel.cog.permission_warning(interaction.guild, self.settings["channel_id"])


class TextsModal(PanelModal):
    def __init__(self, panel: WelcomePanel) -> None:
        super().__init__(panel, "✏️ Textes")
        settings = self.settings
        self.message = labeled_input(
            self, "Message (au-dessus de la carte)", settings["message"],
            description="Variables : {membre} {nom} {pseudo} {serveur} {nombre}",
            paragraph=True, max_length=1000,
        )
        self.title_input = labeled_input(self, "Titre de la carte", settings["title"], max_length=40)
        self.subtitle = labeled_input(self, "Sous-titre (en couleur)", settings["subtitle"], max_length=60)
        self.text = labeled_input(self, "Texte du bas", settings["text"], max_length=100)

    async def apply(self, interaction: discord.Interaction) -> str | None:
        if not self.message.value.strip() and not self.settings["card"]:
            raise ValueError("Sans carte, il faut au moins un message.")

        self.settings["message"] = self.message.value.strip()
        self.settings["title"] = self.title_input.value.strip()
        self.settings["subtitle"] = self.subtitle.value.strip()
        self.settings["text"] = self.text.value.strip()
        return None


class StyleModal(PanelModal):
    def __init__(self, panel: WelcomePanel) -> None:
        super().__init__(panel, "🎨 Couleurs et fond")
        settings = self.settings
        self.title_color = labeled_input(self, "Couleur du titre", settings["title_color"], max_length=9,
                                         description="Code couleur, par exemple #FFFFFF.")
        self.subtitle_color = labeled_input(self, "Couleur du sous-titre", settings["subtitle_color"], max_length=9)
        self.text_color = labeled_input(self, "Couleur du texte du bas", settings["text_color"], max_length=9)
        self.border_color = labeled_input(self, "Couleur du contour de l'avatar", settings["border_color"], max_length=9)
        self.overlay = labeled_input(
            self, "Assombrissement du fond (%)", str(settings["overlay"]), max_length=3,
            description="0 = fond tel quel, 90 = presque noir. Rend le texte plus lisible.",
        )

    async def apply(self, interaction: discord.Interaction) -> str | None:
        overlay = self.overlay.value.strip().rstrip("%").strip()

        if not overlay.isdigit() or not 0 <= int(overlay) <= 90:
            raise ValueError("Assombrissement : un nombre entre 0 et 90.")

        self.settings["title_color"] = normalize_color(self.title_color.value, "Titre")
        self.settings["subtitle_color"] = normalize_color(self.subtitle_color.value, "Sous-titre")
        self.settings["text_color"] = normalize_color(self.text_color.value, "Texte du bas")
        self.settings["border_color"] = normalize_color(self.border_color.value, "Contour")
        self.settings["overlay"] = int(overlay)
        return None


EFFECT_CHOICES = {
    "ombre": ("Ombre douce", "🌫️", "Ombre floue derrière le texte, comme Koya."),
    "contour": ("Contour", "✒️", "Bordure nette autour des lettres."),
    "les deux": ("Ombre + contour", "🔲", "Le plus lisible sur un fond chargé."),
    "aucun": ("Aucun effet", "🚫", "Texte brut."),
}


def read_number(value: str, name: str, top: int) -> int:
    cleaned = value.strip().rstrip("%").strip()

    if not cleaned.isdigit() or not 0 <= int(cleaned) <= top:
        raise ValueError(f"{name} : un nombre entre 0 et {top}.")

    return int(cleaned)


class ShadowModal(PanelModal):
    def __init__(self, panel: WelcomePanel) -> None:
        super().__init__(panel, "🌫️ Ombre du texte")
        settings = self.settings
        self.effect = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=label, value=value, emoji=emoji, description=description,
                    default=value == settings["text_effect"],
                )
                for value, (label, emoji, description) in EFFECT_CHOICES.items()
            ]
        )
        self.add_item(discord.ui.Label(text="Effet", component=self.effect))
        self.color = labeled_input(
            self, "Couleur de l'ombre / du contour", settings["shadow_color"], max_length=9,
            description="Noir (#000000) le plus souvent. Une couleur vive donne un effet néon.",
        )
        self.opacity = labeled_input(
            self, "Opacité de l'ombre (%)", str(settings["shadow_opacity"]), max_length=4,
            description="0 = invisible, 100 = ombre pleine.",
        )
        self.blur = labeled_input(
            self, "Flou de l'ombre (0 à 20)", str(settings["shadow_blur"]), max_length=2,
            description="0 = ombre nette, 4 = douce comme Koya, 10+ = halo.",
        )
        self.offset = labeled_input(
            self, "Décalage de l'ombre (0 à 20)", str(settings["shadow_offset"]), max_length=2,
            description="Distance vers le bas. 0 = halo tout autour du texte.",
        )

    async def apply(self, interaction: discord.Interaction) -> str | None:
        opacity = read_number(self.opacity.value, "Opacité", 100)
        blur = read_number(self.blur.value, "Flou", 20)
        offset = read_number(self.offset.value, "Décalage", 20)

        self.settings["text_effect"] = self.effect.values[0] if self.effect.values else self.settings["text_effect"]
        self.settings["shadow_color"] = normalize_color(self.color.value, "Ombre")
        self.settings["shadow_opacity"] = opacity
        self.settings["shadow_blur"] = blur
        self.settings["shadow_offset"] = offset
        return None


def font_label(font: str, custom_name: str | None) -> str:
    if font == "perso" and custom_name:
        return custom_name

    return FONT_NAMES.get(font, "Roboto")


FONT_HELP = "Police de Koya : « Uni Sans Heavy », gratuite sur fontsquirrel.com (.otf)"


class FontModal(PanelModal):
    def __init__(self, panel: WelcomePanel) -> None:
        super().__init__(panel, "🔤 Police de la carte")
        custom = getattr(panel.cog, "custom_font_name", None)
        current = self.settings["font"]
        options = [
            discord.SelectOption(label="Roboto", value="roboto", description="Police d'origine du bot.",
                                 default=current == "roboto"),
            discord.SelectOption(label="Poppins", value="poppins", description="Ronde et géométrique.",
                                 default=current == "poppins"),
        ]

        if custom:
            options.append(
                discord.SelectOption(label=f"Police importée : {custom}"[:100], value="perso",
                                     description="Le fichier que tu as importé.", default=current == "perso")
            )

        self.choice = discord.ui.Select(options=options)
        self.add_item(discord.ui.Label(text="Police utilisée", component=self.choice))
        self.file = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.add_item(
            discord.ui.Label(
                text="Importer une police (remplace l'ancienne)",
                description=FONT_HELP,
                component=self.file,
            )
        )

    async def apply(self, interaction: discord.Interaction) -> str | None:
        files = list(self.file.values)

        if files:
            attachment = files[0]

            if not attachment.filename.lower().endswith((".ttf", ".otf", ".woff")):
                raise ValueError(f"« {attachment.filename} » n'est pas une police (.ttf, .otf ou .woff).")

            if attachment.size > MAX_FONT_BYTES:
                raise ValueError("Fichier trop lourd (10 Mo maximum).")

            data = await attachment.read()
            name = await asyncio.to_thread(install_custom_font, data)

            if name.lower() in ("my font", "untitled", "font", "police importée"):
                name = attachment.filename.rsplit(".", 1)[0][:60] or name
            await self.panel.cog.save_custom_font(name, data)
            self.settings["font"] = "perso"
            return f"🔤 Police « {name} » importée et utilisée sur la carte."

        choice = self.choice.values[0] if self.choice.values else self.settings["font"]

        if choice == "perso" and not has_custom_font():
            raise ValueError("Aucune police importée : ajoute un fichier .ttf ou .otf.")

        self.settings["font"] = choice
        return None


class BackgroundModal(PanelModal):
    def __init__(self, panel: WelcomePanel) -> None:
        super().__init__(panel, "🖼️ Fond de la carte")
        self.file = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.add_item(
            discord.ui.Label(
                text="Nouvelle image de fond",
                description="PNG, JPG, GIF ou WEBP, 50 Mo max. Recadrée en 1024 × 500.",
                component=self.file,
            )
        )
        self.choice = discord.ui.Select(
            options=[
                discord.SelectOption(label="Garder le fond actuel", value="keep", emoji="🖼️", default=True),
                discord.SelectOption(label="Revenir au fond par défaut", value="default", emoji="🌅"),
            ]
        )
        self.add_item(
            discord.ui.Label(text="Sans nouvelle image", description="Utilisé si aucun fichier n'est envoyé.",
                             component=self.choice)
        )

    async def apply(self, interaction: discord.Interaction) -> str | None:
        files = list(self.file.values)

        if files:
            attachment = files[0]

            if not (attachment.content_type or "").startswith("image/"):
                raise ValueError(f"« {attachment.filename} » n'est pas une image.")

            if attachment.size > MAX_BACKGROUND_BYTES:
                raise ValueError("Image trop lourde (50 Mo maximum).")

            try:
                data = await asyncio.to_thread(prepare_background, await attachment.read())
            except ValueError as error:
                raise ValueError(
                    "Image trop grande en pixels (50 mégapixels maximum) : réduis-la un peu."
                ) from error
            except Exception as error:
                raise ValueError("Impossible de lire cette image.") from error

            self.panel.background = data
            self.panel.background_changed = True
            return "🖼️ Nouveau fond enregistré."

        if self.choice.values[0] == "default":
            self.panel.background = None
            self.panel.background_changed = True
            return "🌅 Retour au fond par défaut."

        return None


# ============================================================
# MODÈLES
# ============================================================

# Ce qu'un modèle garde : l'apparence, pas le salon ni l'activation.
DESIGN_KEYS = (
    "message",
    "title",
    "subtitle",
    "text",
    "layout",
    "overlay",
    "title_color",
    "subtitle_color",
    "text_color",
    "border_color",
    "text_effect",
    "shadow_color",
    "shadow_opacity",
    "shadow_blur",
    "shadow_offset",
    "font",
    "card",
)
MAX_TEMPLATES = 25


def design_of(settings: dict[str, Any]) -> dict[str, Any]:
    return {key: settings[key] for key in DESIGN_KEYS if key in settings}


class TemplateNameModal(discord.ui.Modal, title="💾 Enregistrer comme modèle"):
    def __init__(self, panel: WelcomePanel) -> None:
        super().__init__(timeout=600)
        self.panel = panel
        self.name = labeled_input(
            self, "Nom du modèle", "", required=True, max_length=60,
            description="Un modèle du même nom est remplacé.",
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name.value.strip()
        cog = self.panel.cog
        existing = {template["name"] for template in await cog.list_templates(interaction.guild_id)}

        if name not in existing and len(existing) >= MAX_TEMPLATES:
            await interaction.response.send_message(
                embed=error_embed(f"{MAX_TEMPLATES} modèles maximum : supprimes-en un d'abord."), ephemeral=True
            )
            return

        await cog.save_template(
            interaction.guild_id, name, design_of(self.panel.settings), self.panel.background, interaction.user.id
        )
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"💾 Modèle **{name}** enregistré (textes, couleurs, disposition et fond). "
                "Un autre admin peut le charger depuis 🧩 **Modèles**.",
                color=SUCCESS_COLOR,
            ),
            view=None,
        )


class TemplatesView(discord.ui.View):
    def __init__(self, panel: WelcomePanel, templates: list[dict[str, Any]]) -> None:
        super().__init__(timeout=300)
        self.panel = panel

        if templates:
            def options(emoji: str) -> list[discord.SelectOption]:
                return [
                    discord.SelectOption(
                        label=template["name"][:100],
                        value=str(template["id"]),
                        emoji=emoji,
                        description=f"Par {template['author']}"[:100] if template.get("author") else None,
                    )
                    for template in templates
                ]

            load = discord.ui.Select(placeholder="📂 Charger un modèle (avec aperçu)…", options=options("📄"))
            load.callback = self.load
            self.add_item(load)

            delete = discord.ui.Select(placeholder="🗑️ Supprimer un modèle…", options=options("🗑️"))
            delete.callback = self.delete
            self.add_item(delete)

        save = discord.ui.Button(
            label=f"Enregistrer l'apparence actuelle ({KIND_NAMES[panel.kind]})",
            emoji="💾",
            style=discord.ButtonStyle.success,
        )
        save.callback = self.save
        self.add_item(save)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.panel.owner_id

    async def load(self, interaction: discord.Interaction) -> None:
        template = await self.panel.cog.get_template(interaction.guild_id, int(interaction.data["values"][0]))

        if template is None:
            await interaction.response.edit_message(embed=error_embed("Ce modèle n'existe plus."), view=None)
            return

        self.panel.settings.update(design_of(template["settings"]))
        self.panel.background = template["background"]
        self.panel.background_changed = True
        await self.panel.save()
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"📂 Modèle **{template['name']}** appliqué aux {KIND_NAMES[self.panel.kind]}. "
                "Regarde l'aperçu dans le panneau.",
                color=SUCCESS_COLOR,
            ),
            view=None,
        )
        await self.panel.refresh(None, notice=f"📂 Modèle chargé : {template['name']}")

    async def delete(self, interaction: discord.Interaction) -> None:
        name = await self.panel.cog.delete_template(interaction.guild_id, int(interaction.data["values"][0]))
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"🗑️ Modèle **{name}** supprimé." if name else "Ce modèle n'existait plus.",
                color=SUCCESS_COLOR,
            ),
            view=None,
        )

    async def save(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TemplateNameModal(self.panel))


# ============================================================
# RÔLES À L'ARRIVÉE
# ============================================================


def autorole_problems(guild: discord.Guild, role_ids: list[int]) -> list[str]:
    """Ce qui empêcherait le bot de donner ces rôles."""
    me = guild.me
    problems = []

    if me is not None and not me.guild_permissions.manage_roles:
        problems.append("il me manque la permission « Gérer les rôles »")

    for role_id in role_ids:
        role = guild.get_role(int(role_id))

        if role is None:
            problems.append(f"le rôle <@&{role_id}> n'existe plus")
        elif unsafe_role_reason(role) is not None:
            problems.append(unsafe_role_reason(role))
        elif me is not None and role >= me.top_role:
            problems.append(f"mon rôle doit être placé au-dessus de {role.mention} dans la liste des rôles")

    return problems


class AutoroleModal(PanelModal):
    def __init__(self, panel: WelcomePanel) -> None:
        super().__init__(panel, "🎭 Rôles à l'arrivée")
        current = [panel.guild.get_role(int(role_id)) for role_id in self.settings.get("autoroles", [])]
        self.roles = discord.ui.RoleSelect(
            default_values=[role for role in current if role is not None],
            required=False,
            min_values=0,
            max_values=MAX_AUTOROLES,
        )
        self.add_item(
            discord.ui.Label(
                text="Rôles donnés à chaque nouveau membre",
                description=f"{MAX_AUTOROLES} maximum, gardés ensuite. Aucun rôle = désactivé.",
                component=self.roles,
            )
        )

    async def apply(self, interaction: discord.Interaction) -> str | None:
        for role in self.roles.values:
            problem = unsafe_role_reason(interaction.guild.get_role(role.id) or role, interaction.user)

            if problem is not None:
                raise ValueError(f"Rôle refusé : {problem}.")

        self.settings["autoroles"] = [role.id for role in self.roles.values]

        if not self.settings["autoroles"]:
            return "🎭 Plus aucun rôle donné à l'arrivée."

        problems = autorole_problems(interaction.guild, self.settings["autoroles"])
        names = ", ".join(f"<@&{role_id}>" for role_id in self.settings["autoroles"])

        if problems:
            return f"🎭 Rôles à l'arrivée : {names}.\n⚠️ Attention : " + " ; ".join(problems) + "."

        return (
            f"🎭 Chaque nouveau membre recevra {names}. "
            "Pense à désactiver le rôle automatique de DraftBot pour éviter les doublons."
        )


def member_list_file(members: list[Any], roles: list[Any]) -> discord.File:
    header = "Membres sans " + ", ".join(f"@{role.name}" for role in roles) + f" : {len(members)}"
    return shared_member_list_file(members, header, "membres_sans_role.txt")


class BackfillView(MemberPagesView):
    """Confirmation avant de donner les rôles d'arrivée, avec la liste des membres concernés."""

    def __init__(
        self,
        cog: BienvenueCog,
        owner_id: int,
        role_ids: list[int],
        missing: list[discord.Member],
        roles: list[Any] | None = None,
    ) -> None:
        super().__init__(owner_id, missing)
        self.cog = cog
        self.role_ids = role_ids
        self.roles = roles or []
        # « Liste complète » après « Oui » et « Annuler ».
        self.remove_item(self.full_list)
        self.add_item(self.full_list)

    @property
    def missing(self) -> list[Any]:
        return self.members

    def embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="👥 Donner les rôles aux membres actuels ?",
            description=(
                f"**{len(self.missing)}** membre(s) n'ont pas encore "
                + (", ".join(role.mention for role in self.roles) or "ces rôles")
                + ".\nCela peut prendre un peu de temps (Discord limite la vitesse).\n"
                + self.table()
            ),
            color=COLOR,
        )
        embed.set_footer(text=self.footer())
        return embed

    def list_file(self) -> discord.File:
        return member_list_file(self.missing, self.roles)

    @discord.ui.button(label="Oui, donner les rôles", emoji="✅", style=discord.ButtonStyle.success, row=0)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"⏳ Attribution en cours à **{len(self.missing)}** membre(s)… "
                "Je te préviens ici quand c'est fini.",
                color=COLOR,
            ),
            view=None,
        )
        given, failed = await self.cog.backfill(self.missing, self.role_ids)
        text = f"✅ Rôles donnés à **{given}** membre(s)."

        if failed:
            text += f"\n⚠️ Échec pour {failed} membre(s) (permissions ou rôle trop haut)."

        try:
            await interaction.edit_original_response(embed=discord.Embed(description=text, color=SUCCESS_COLOR))
        except discord.HTTPException:
            await interaction.followup.send(text, ephemeral=True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="Annulé, rien n'a changé.", color=COLOR), view=None
        )


# ============================================================
# PANNEAU
# ============================================================


class WelcomePanel(discord.ui.View):
    def __init__(self, cog: BienvenueCog, interaction: discord.Interaction, kind: str) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.origin = interaction
        self.owner_id = interaction.user.id
        self.guild: discord.Guild = interaction.guild
        self.kind = kind
        self.settings: dict[str, Any] = {}
        self.background: bytes | None = None
        self.background_changed = False

    async def load(self) -> None:
        self.settings, self.background = await self.cog.get_settings(self.guild.id, self.kind)
        self.background_changed = False
        self.build()

    async def save(self) -> None:
        await self.cog.save_settings(
            self.guild.id,
            self.kind,
            self.settings,
            background=self.background,
            update_background=self.background_changed,
        )
        self.background_changed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed("Seul l'administrateur qui a ouvert ce panneau peut l'utiliser."),
                ephemeral=True,
            )
            return False

        return True

    def embed(self, notice: str | None = None) -> discord.Embed:
        settings = self.settings
        channel = f"<#{settings['channel_id']}>" if settings["channel_id"] else "*à choisir*"
        lines = [
            f"État : **{'activé ✅' if settings['enabled'] else 'désactivé ❌'}** · Salon : {channel}",
            f"Carte : **{'oui' if settings['card'] else 'non'}** · Disposition : **{settings['layout']}** · "
            f"Assombrissement : **{settings['overlay']} %** · "
            f"Effet du texte : **{EFFECT_CHOICES[settings['text_effect']][0]}**",
            "",
            f"**Message :** {settings['message'] or '*aucun*'}",
        ]

        if self.kind == JOIN:
            roles = settings.get("autoroles") or []
            lines.insert(
                2,
                "🎭 Rôles à l'arrivée : "
                + (", ".join(f"<@&{role_id}>" for role_id in roles) if roles else "*aucun*")
                + " (donnés même si le message est désactivé)",
            )

        if notice:
            lines += ["", f"> {notice}"]

        embed = discord.Embed(
            title=f"{KIND_NAMES[self.kind]} — réglages",
            description="\n".join(lines),
            color=COLOR,
        )
        embed.add_field(name="Variables", value=VARIABLES_HELP, inline=False)

        if settings["card"]:
            embed.set_image(url="attachment://apercu.png")
            embed.set_footer(text="Aperçu avec ton profil")

        return embed

    async def refresh(self, interaction: discord.Interaction | None, *, notice: str | None = None) -> None:
        """interaction None : mise à jour depuis un autre message (modèles)."""
        self.build()
        files = []
        user = (interaction or self.origin).user

        if self.settings["card"]:
            png = await self.cog.render_for(user, self.settings, self.background)
            files.append(discord.File(io.BytesIO(png), filename="apercu.png"))

        kwargs = {"embed": self.embed(notice), "attachments": files, "view": self}

        if interaction is None:
            try:
                await self.origin.edit_original_response(**kwargs)
            except discord.HTTPException:
                LOGGER.warning("Panneau de bienvenue expiré : relance /bienvenue-admin")
        elif interaction.response.is_done():
            await interaction.edit_original_response(**kwargs)
        else:
            await interaction.response.edit_message(**kwargs)

    def button(self, label: str, emoji: str, callback, *, row: int, style=discord.ButtonStyle.secondary) -> None:
        item = discord.ui.Button(label=label, emoji=emoji, style=style, row=row)
        item.callback = callback
        self.add_item(item)

    def build(self) -> None:
        self.clear_items()
        select = discord.ui.Select(
            options=[
                discord.SelectOption(label=name, value=kind, default=kind == self.kind)
                for kind, name in KIND_NAMES.items()
            ],
            row=0,
        )
        select.callback = self.on_kind
        self.add_item(select)

        enabled = bool(self.settings.get("enabled"))
        self.button(
            "Désactiver" if enabled else "Activer",
            "⏸️" if enabled else "▶️",
            self.on_toggle,
            row=1,
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
        )
        self.button("Salon", "📍", self.on_channel, row=1)
        self.button("Textes", "✏️", self.on_texts, row=1, style=discord.ButtonStyle.primary)
        self.button("Fond", "🖼️", self.on_background, row=1)
        self.button("Couleurs", "🎨", self.on_style, row=1)
        self.button(f"Disposition : {self.settings.get('layout', 'centre')}", "📐", self.on_layout, row=2)
        self.button(f"Carte : {'oui' if self.settings.get('card', True) else 'non'}", "🃏", self.on_card, row=2)
        self.button("Aperçu réel", "👁️", self.on_preview, row=2)
        self.button("Modèles", "🧩", self.on_templates, row=2)
        self.button("Tester dans le salon", "📨", self.on_test, row=2)

        self.button("Ombre du texte", "🌫️", self.on_shadow, row=3)
        font = font_label(self.settings.get("font", "roboto"), getattr(self.cog, "custom_font_name", None))
        self.button(f"Police : {font}"[:80], "🔤", self.on_font, row=3)

        if self.kind == JOIN:
            self.button("Rôles à l'arrivée", "🎭", self.on_autoroles, row=3, style=discord.ButtonStyle.primary)
            self.button("Donner aux membres actuels", "👥", self.on_backfill, row=3)

    # -------- actions --------

    async def on_autoroles(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AutoroleModal(self))

    async def on_backfill(self, interaction: discord.Interaction) -> None:
        role_ids = [int(role_id) for role_id in self.settings.get("autoroles") or []]

        if not role_ids:
            await interaction.response.send_message(
                embed=error_embed("Choisis d'abord les rôles avec 🎭 **Rôles à l'arrivée**."), ephemeral=True
            )
            return

        problems = autorole_problems(self.guild, role_ids)

        if problems:
            await interaction.response.send_message(
                embed=error_embed("Impossible pour l'instant : " + " ; ".join(problems) + "."), ephemeral=True
            )
            return

        roles = [self.guild.get_role(role_id) for role_id in role_ids]
        missing = [
            member
            for member in self.guild.members
            if not member.bot and any(role not in member.roles for role in roles)
        ]

        if not missing:
            await interaction.response.send_message(
                embed=discord.Embed(description="✅ Tous les membres ont déjà ces rôles.", color=SUCCESS_COLOR),
                ephemeral=True,
            )
            return

        view = BackfillView(self.cog, self.owner_id, role_ids, missing, roles)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def on_kind(self, interaction: discord.Interaction) -> None:
        self.kind = interaction.data["values"][0]
        await self.load()
        await self.refresh(interaction)

    async def on_toggle(self, interaction: discord.Interaction) -> None:
        if not self.settings["enabled"] and not self.settings["channel_id"]:
            await interaction.response.send_message(
                embed=error_embed("Choisis d'abord le salon avec 📍 **Salon**."), ephemeral=True
            )
            return

        self.settings["enabled"] = not self.settings["enabled"]
        await self.save()
        notice = None

        if self.settings["enabled"]:
            notice = self.cog.permission_warning(self.guild, self.settings["channel_id"]) or "✅ Activé."

        await self.refresh(interaction, notice=notice or "⏸️ Désactivé.")

    async def on_channel(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ChannelModal(self))

    async def on_texts(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TextsModal(self))

    async def on_background(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BackgroundModal(self))

    async def on_style(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(StyleModal(self))

    async def on_shadow(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ShadowModal(self))

    async def on_font(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(FontModal(self))

    async def on_layout(self, interaction: discord.Interaction) -> None:
        current = self.settings["layout"]
        self.settings["layout"] = LAYOUTS[(LAYOUTS.index(current) + 1) % len(LAYOUTS)]
        await self.save()
        await self.refresh(interaction)

    async def on_card(self, interaction: discord.Interaction) -> None:
        if self.settings["card"] and not self.settings["message"].strip():
            await interaction.response.send_message(
                embed=error_embed("Sans carte, il faut un message : écris-le d'abord avec ✏️ **Textes**."),
                ephemeral=True,
            )
            return

        self.settings["card"] = not self.settings["card"]
        await self.save()
        await self.refresh(interaction)

    async def on_preview(self, interaction: discord.Interaction) -> None:
        """Le message exactement comme les membres le verront, visible par toi seul."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        content = fill_variables(self.settings["message"], interaction.user)[:2000]
        kwargs: dict[str, Any] = {
            "content": f"-# 👁️ Aperçu ({KIND_NAMES[self.kind]}), visible par toi seul\n{content}",
            "allowed_mentions": discord.AllowedMentions.none(),
            "ephemeral": True,
        }

        if self.settings["card"]:
            png = await self.cog.render_for(interaction.user, self.settings, self.background)
            kwargs["file"] = discord.File(io.BytesIO(png), filename="apercu.png")

        await interaction.followup.send(**kwargs)

    async def on_templates(self, interaction: discord.Interaction) -> None:
        templates = await self.cog.list_templates(interaction.guild_id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🧩 Modèles de carte",
                description=(
                    "Un modèle garde l'apparence : textes, couleurs, disposition, assombrissement et fond "
                    "(pas le salon ni l'activation). Charger un modèle l'applique aux "
                    f"**{KIND_NAMES[self.kind]}** et met l'aperçu à jour."
                    + ("" if templates else "\n\nAucun modèle pour l'instant.")
                ),
                color=COLOR,
            ),
            view=TemplatesView(self, templates),
            ephemeral=True,
        )

    async def on_test(self, interaction: discord.Interaction) -> None:
        if not self.settings["channel_id"]:
            await interaction.response.send_message(
                embed=error_embed("Choisis d'abord le salon avec 📍 **Salon**."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await self.cog.send_greeting(interaction.user, self.kind, self.settings, self.background)

        if message is None:
            await interaction.followup.send(
                embed=error_embed(
                    self.cog.permission_warning(self.guild, self.settings["channel_id"])
                    or "Envoi impossible dans ce salon."
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"📨 Test envoyé : {message.jump_url}"
            + ("" if self.settings["enabled"] else "\n⚠️ Les messages automatiques sont encore désactivés."),
            ephemeral=True,
        )


# ============================================================
# COG
# ============================================================


class BienvenueCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.cache: dict[tuple[int, str], tuple[dict[str, Any], bytes | None]] = {}
        self.custom_font_name: str | None = None


    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def initialize_database(self) -> None:
        await self.get_pool().execute(
            """
            CREATE TABLE IF NOT EXISTS welcome_settings (
                guild_id BIGINT NOT NULL,
                kind VARCHAR(10) NOT NULL,
                settings JSONB NOT NULL DEFAULT '{}'::JSONB,
                background BYTEA,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, kind)
            )
            """
        )
        await self.get_pool().execute(
            """
            CREATE TABLE IF NOT EXISTS welcome_templates (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                name VARCHAR(60) NOT NULL,
                settings JSONB NOT NULL,
                background BYTEA,
                created_by BIGINT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (guild_id, name)
            )
            """
        )
        # Police importée : gardée ici (jamais dans le dépôt) et recopiée
        # sur le disque à chaque démarrage.
        await self.get_pool().execute(
            """
            CREATE TABLE IF NOT EXISTS welcome_font (
                id SMALLINT PRIMARY KEY DEFAULT 1,
                name VARCHAR(60) NOT NULL,
                data BYTEA NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await self.restore_custom_font()

    async def restore_custom_font(self) -> None:
        row = await self.get_pool().fetchrow("SELECT name, data FROM welcome_font WHERE id = 1")

        if row is None:
            return

        try:
            await asyncio.to_thread(install_custom_font, bytes(row["data"]))
            self.custom_font_name = row["name"]
        except Exception:
            LOGGER.exception("Police importée illisible : la carte utilisera Roboto")

    async def save_custom_font(self, name: str, data: bytes) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO welcome_font (id, name, data) VALUES (1, $1, $2)
            ON CONFLICT (id) DO UPDATE SET name = $1, data = $2, updated_at = NOW()
            """,
            name,
            data,
        )
        self.custom_font_name = name

    # -------- réglages --------

    async def get_settings(self, guild_id: int, kind: str) -> tuple[dict[str, Any], bytes | None]:
        cached = self.cache.get((guild_id, kind))

        if cached is not None:
            return dict(cached[0]), cached[1]

        record = await self.get_pool().fetchrow(
            "SELECT settings, background FROM welcome_settings WHERE guild_id = $1 AND kind = $2",
            guild_id,
            kind,
        )
        stored = None
        background = None

        if record is not None:
            stored = record["settings"]
            stored = json.loads(stored) if isinstance(stored, str) else stored
            background = bytes(record["background"]) if record["background"] else None

        settings = merge_settings(kind, stored)
        self.cache[(guild_id, kind)] = (dict(settings), background)
        return settings, background

    async def save_settings(
        self,
        guild_id: int,
        kind: str,
        settings: dict[str, Any],
        *,
        background: bytes | None = None,
        update_background: bool = False,
    ) -> None:
        payload = json.dumps(settings, ensure_ascii=False)

        if update_background:
            await self.get_pool().execute(
                """
                INSERT INTO welcome_settings (guild_id, kind, settings, background)
                VALUES ($1, $2, $3::jsonb, $4)
                ON CONFLICT (guild_id, kind)
                DO UPDATE SET settings = EXCLUDED.settings, background = EXCLUDED.background,
                              updated_at = NOW()
                """,
                guild_id,
                kind,
                payload,
                background,
            )
        else:
            await self.get_pool().execute(
                """
                INSERT INTO welcome_settings (guild_id, kind, settings)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (guild_id, kind)
                DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW()
                """,
                guild_id,
                kind,
                payload,
            )

        self.cache.pop((guild_id, kind), None)

    # -------- modèles --------

    async def list_templates(self, guild_id: int) -> list[dict[str, Any]]:
        records = await self.get_pool().fetch(
            """
            SELECT id, name, created_by
            FROM welcome_templates
            WHERE guild_id = $1
            ORDER BY LOWER(name)
            LIMIT 25
            """,
            guild_id,
        )
        guild = self.bot.get_guild(guild_id) if hasattr(self.bot, "get_guild") else None
        result = []

        for record in records:
            member = guild.get_member(int(record["created_by"])) if guild else None
            result.append(
                {
                    "id": int(record["id"]),
                    "name": record["name"],
                    "author": member.display_name if member else None,
                }
            )

        return result

    async def get_template(self, guild_id: int, template_id: int) -> dict[str, Any] | None:
        record = await self.get_pool().fetchrow(
            "SELECT name, settings, background FROM welcome_templates WHERE guild_id = $1 AND id = $2",
            guild_id,
            template_id,
        )

        if record is None:
            return None

        settings = record["settings"]
        return {
            "name": record["name"],
            "settings": json.loads(settings) if isinstance(settings, str) else dict(settings),
            "background": bytes(record["background"]) if record["background"] else None,
        }

    async def save_template(
        self, guild_id: int, name: str, design: dict[str, Any], background: bytes | None, user_id: int
    ) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO welcome_templates (guild_id, name, settings, background, created_by)
            VALUES ($1, $2, $3::jsonb, $4, $5)
            ON CONFLICT (guild_id, name)
            DO UPDATE SET settings = EXCLUDED.settings, background = EXCLUDED.background,
                          created_by = EXCLUDED.created_by, updated_at = NOW()
            """,
            guild_id,
            name,
            json.dumps(design, ensure_ascii=False),
            background,
            user_id,
        )

    async def delete_template(self, guild_id: int, template_id: int) -> str | None:
        return await self.get_pool().fetchval(
            "DELETE FROM welcome_templates WHERE guild_id = $1 AND id = $2 RETURNING name",
            guild_id,
            template_id,
        )

    def permission_warning(self, guild: discord.Guild, channel_id: int | None) -> str | None:
        channel = guild.get_channel(channel_id or 0)

        if not isinstance(channel, discord.TextChannel):
            return "⚠️ Ce salon n'existe plus."

        perms = channel.permissions_for(guild.me)
        missing = [
            name
            for name, ok in (
                ("Voir le salon", perms.view_channel),
                ("Envoyer des messages", perms.send_messages),
                ("Joindre des fichiers", perms.attach_files),
            )
            if not ok
        ]

        return f"⚠️ Il me manque dans {channel.mention} : {', '.join(missing)}." if missing else None

    # -------- carte et envoi --------

    async def avatar_bytes(self, member: discord.abc.User) -> bytes | None:
        try:
            return await member.display_avatar.replace(format="png", size=256).read()
        except (discord.HTTPException, ValueError):
            return None

    async def render_for(self, member: Any, settings: dict[str, Any], background: bytes | None) -> bytes:
        avatar = await self.avatar_bytes(member)
        return await asyncio.to_thread(
            render_welcome_card,
            avatar_bytes=avatar,
            title=fill_variables(settings["title"], member, on_card=True),
            subtitle=fill_variables(settings["subtitle"], member, on_card=True),
            text=fill_variables(settings["text"], member, on_card=True),
            background_bytes=background,
            layout=settings["layout"],
            overlay=settings["overlay"],
            title_color=settings["title_color"],
            subtitle_color=settings["subtitle_color"],
            text_color=settings["text_color"],
            border_color=settings["border_color"],
            text_effect=settings["text_effect"],
            shadow_color=settings["shadow_color"],
            shadow_opacity=settings["shadow_opacity"],
            shadow_blur=settings["shadow_blur"],
            shadow_offset=settings["shadow_offset"],
            font=settings["font"],
        )

    async def send_greeting(
        self,
        member: Any,
        kind: str,
        settings: dict[str, Any] | None = None,
        background: bytes | None = None,
    ) -> discord.Message | None:
        if settings is None:
            settings, background = await self.get_settings(member.guild.id, kind)

        channel = member.guild.get_channel(settings["channel_id"] or 0)

        if not isinstance(channel, discord.TextChannel):
            return None

        kwargs: dict[str, Any] = {
            "content": fill_variables(settings["message"], member)[:2000] or None,
            # Pas de mention qui « ping » pour un départ : le membre n'est plus là.
            "allowed_mentions": discord.AllowedMentions(
                everyone=False, roles=False, users=[member] if kind == JOIN else False
            ),
        }

        if settings["card"]:
            png = await self.render_for(member, settings, background)
            kwargs["file"] = discord.File(io.BytesIO(png), filename=f"{kind}.png")

        if not kwargs["content"] and "file" not in kwargs:
            return None

        try:
            return await channel.send(**kwargs)
        except discord.HTTPException:
            LOGGER.warning("Message de %s impossible dans le salon %s", kind, channel.id)
            return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Si le serveur demande d'accepter le règlement, on attend qu'il soit accepté.
        if not getattr(member, "pending", False):
            await self.give_autoroles(member)

        await self.greet(member, JOIN)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if getattr(before, "pending", False) and not getattr(after, "pending", False):
            await self.give_autoroles(after)

    async def give_autoroles(self, member: discord.Member) -> None:
        if member.bot:
            return

        try:
            settings, _ = await self.get_settings(member.guild.id, JOIN)
            roles = [member.guild.get_role(int(role_id)) for role_id in settings.get("autoroles") or []]
            roles = [
                role for role in roles
                if role is not None and role not in member.roles and unsafe_role_reason(role) is None
            ]

            if roles:
                await member.add_roles(*roles, reason="Rôle à l'arrivée")
        except discord.HTTPException:
            LOGGER.warning("Rôles d'arrivée non donnés à %s (permissions ?)", member.id)
        except Exception:
            LOGGER.exception("Rôles d'arrivée non donnés à %s", member.id)

    async def backfill(self, members: list[discord.Member], role_ids: list[int]) -> tuple[int, int]:
        """Donne les rôles d'arrivée aux membres déjà présents qui ne les ont pas."""
        given = failed = 0

        for member in members:
            roles = [member.guild.get_role(role_id) for role_id in role_ids]
            roles = [role for role in roles if role is not None and role not in member.roles]

            if not roles:
                continue

            try:
                await member.add_roles(*roles, reason="Rôle à l'arrivée (membres déjà présents)")
                given += 1
            except discord.HTTPException:
                failed += 1

            await asyncio.sleep(0.3)  # reste sous les limites de Discord

        return given, failed

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.greet(member, LEAVE)

    async def greet(self, member: discord.Member, kind: str) -> None:
        if member.bot:
            return

        try:
            settings, background = await self.get_settings(member.guild.id, kind)

            if settings["enabled"]:
                await self.send_greeting(member, kind, settings, background)
        except Exception:
            LOGGER.exception("Message de %s non envoyé pour %s", kind, member.id)

    # -------- commande --------

    @app_commands.command(name="bienvenue-admin", description="Messages et cartes de bienvenue et de départ.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def bienvenue_admin(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        panel = WelcomePanel(self, interaction, JOIN)
        await panel.load()
        await panel.refresh(interaction)


async def setup(bot: commands.Bot) -> None:
    cog = BienvenueCog(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info("Bienvenue et départs chargés")
