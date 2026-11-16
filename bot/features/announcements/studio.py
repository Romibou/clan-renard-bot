"""
Studio d'annonce : panneau éphémère avec aperçu en direct, boutons
d'édition et fenêtres de saisie (popups).

Toute la logique Discord « lourde » (publication, images, contrôles)
est dans le Cog (bot/extensions/annonces.py) ; ce fichier ne gère
que l'interface.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import discord

from bot.extensions.rappel import parse_duration
from bot.features.announcements.model import (
    MAX_EMBEDS,
    MAX_IMAGE_BYTES,
    UPLOAD_PREFIX,
    URL_PATTERN,
    AnnouncementError,
    buttons_to_text,
    color_to_text,
    convert_date_tokens,
    convert_emojis,
    export_message,
    fields_to_text,
    import_message,
    parse_color,
    parse_datetime,
    summary_title,
    text_to_buttons,
    text_to_fields,
    upload_ids,
)

if TYPE_CHECKING:
    from bot.extensions.annonces import AnnouncementCog

LOGGER = logging.getLogger(__name__)

STUDIO_TIMEOUT = 14 * 60  # le jeton d'une interaction expire après 15 min
KEEP_UPLOAD = "📎 image envoyée (efface ce texte pour la retirer)"
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
INFO_COLOR = discord.Color.from_rgb(242, 140, 40)

HELP_TEXT = """\
**Mise en forme** (dans les textes et les sections)
**\\*\\*gras\\*\\***, *\\*italique\\**, __\\_\\_souligné\\_\\___, ~~\\~\\~barré\\~\\~~~, ||\\|\\|spoiler\\|\\|||
`# Gros titre`, `## Titre`, `### Petit titre`, `-# petit texte gris`
`- élément de liste`, `> citation`, `[texte](https://lien)`

**Dates à l'heure de chaque membre**
`{date:25/12 18h}` → date et heure complètes
`{dans:25/12 18h}` → « dans 3 jours »
`{jour:25/12}` → « 25 décembre 2026 » · `{heure:18h30}` → « 18:30 »
Fonctionne aussi avec `demain 21h`, `aujourd'hui 20h`, `25/12/2026 18:00`.

**Émojis, rôles et salons**
Dans n'importe quel salon, tape `\\:emoji:`, `\\@Rôle` ou `\\#salon` puis envoie : \
Discord affiche le code (`<:renard:123…>`, `<@&123…>`, `<#123…>`). Colle ce code dans le studio.

**Sections** : une ligne `## Titre` puis le contenu en dessous.
**Boutons** : une ligne par bouton, `🎮 Texte | https://lien`.

**Mise en page très précise** : construis le message sur **discohook.app**, \
copie son JSON (éditeur JSON) et colle-le avec 📥 **Importer**.\
"""


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(title="❌ Impossible", description=text, color=ERROR_COLOR)


async def send_error(interaction: discord.Interaction, text: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(embed=error_embed(text), ephemeral=True)
    else:
        await interaction.response.send_message(embed=error_embed(text), ephemeral=True)


def label_input(
    text: str,
    *,
    description: str | None = None,
    default: str | None = None,
    placeholder: str | None = None,
    paragraph: bool = False,
    max_length: int = 256,
    required: bool = False,
) -> tuple[discord.ui.Label, discord.ui.TextInput]:
    component = discord.ui.TextInput(
        style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short,
        default=(default or None) and default[:max_length],
        placeholder=placeholder,
        max_length=max_length,
        required=required,
    )

    return discord.ui.Label(text=text, description=description, component=component), component


def frame_name(embed: dict[str, Any]) -> str:
    text = embed.get("title") or embed.get("description") or "vide"
    return " ".join(text.split())[:80] or "vide"


def button_label(button: dict[str, Any]) -> str | None:
    label = button.get("label") or ""
    return None if label in ("", "​") else label


FORMAT_NAMES = {"classic": "classique", "large": "grand", "text": "pleine largeur"}
FORMAT_NOTICES = {
    "classic": "📐 Format **classique** : le cadre habituel des bots.",
    "large": (
        "📐 Format **grand** : un bloc avec la barre de couleur, un peu plus large. En-tête et pied "
        "de page en petit texte, sections empilées, 4 000 caractères au total. "
        "Clique sur 👁️ **Aperçu réel** pour le voir."
    ),
    "text": (
        "📐 Format **pleine largeur** : un message texte normal, sans cadre ni barre de couleur, "
        "qui prend toute la largeur du salon. Images et boutons en dessous, pas de miniature. "
        "2 000 caractères au total. Clique sur 👁️ **Aperçu réel** pour le voir."
    ),
}


# ============================================================
# FENÊTRES DE SAISIE
# ============================================================


class StudioModal(discord.ui.Modal):
    def __init__(self, studio: StudioView, title: str) -> None:
        super().__init__(title=title, timeout=600)
        self.studio = studio

    @property
    def embed(self) -> dict[str, Any]:
        return self.studio.current_embed

    def dates(self, text: str) -> str:
        converted, errors = convert_date_tokens(text, self.studio.cog.tz, datetime.now(timezone.utc))

        if errors:
            raise AnnouncementError(
                f"Date non comprise : `{errors[0]}`. Exemples : `{{date:25/12 18h}}`, "
                "`{dans:demain 21h}`."
            )

        return self.emojis(converted)

    def emojis(self, text: str) -> str:
        return convert_emojis(
            text,
            [
                (emoji.name, emoji.id, emoji.animated)
                for emoji in getattr(self.studio.guild, "emojis", ())
            ],
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            notice = await self.apply(interaction)
        except AnnouncementError as error:
            await send_error(interaction, str(error))
            return

        await self.studio.refresh(interaction, notice=notice)

    async def apply(self, interaction: discord.Interaction) -> str | None:
        raise NotImplementedError

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        LOGGER.exception("Erreur dans le studio d'annonce", exc_info=error)
        await send_error(interaction, "Une erreur inattendue est survenue. Réessaie.")


class TextModal(StudioModal):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(studio, f"✏️ Texte du cadre {studio.index + 1}")
        embed = self.embed

        label, self.title_input = label_input(
            "Titre", default=embed.get("title"), max_length=256
        )
        self.add_item(label)
        label, self.url_input = label_input(
            "Lien du titre (facultatif)",
            description="Le titre devient cliquable.",
            default=embed.get("url"),
            placeholder="https://…",
            max_length=500,
        )
        self.add_item(label)
        label, self.description_input = label_input(
            "Contenu du cadre",
            description="Markdown, émojis et {date:25/12 18h} acceptés.",
            default=embed.get("description"),
            paragraph=True,
            max_length=4000,
        )
        self.add_item(label)
        label, self.content_input = label_input(
            "Message au-dessus du cadre (facultatif)",
            description="Texte simple affiché hors du cadre, sous la mention.",
            default=studio.draft.get("content"),
            paragraph=True,
            max_length=1900,
        )
        self.add_item(label)

    async def apply(self, interaction: discord.Interaction) -> str | None:
        url = self.url_input.value.strip()

        if url and not URL_PATTERN.match(url):
            raise AnnouncementError("Le lien du titre doit commencer par https://.")

        self.embed["title"] = self.dates(self.title_input.value.strip())
        self.embed["url"] = url
        self.embed["description"] = self.dates(self.description_input.value.strip())
        self.studio.draft["content"] = self.dates(self.content_input.value.strip())

        return None


def choice_select(options: list[tuple[str, str, str | None]], current: str) -> discord.ui.Select:
    return discord.ui.Select(
        options=[
            discord.SelectOption(label=label, value=value, emoji=emoji, default=value == current)
            for label, value, emoji in options
        ],
        min_values=1,
        max_values=1,
    )


class StyleModal(StudioModal):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(studio, f"🎨 Style du cadre {studio.index + 1}")
        embed = self.embed

        label, self.color_input = label_input(
            "Couleur de la barre",
            description="Code (#F28C28) ou nom : orange, rouge, bleu, vert, violet, rose…",
            default=color_to_text(embed.get("color")),
            max_length=20,
        )
        self.add_item(label)
        label, self.author_input = label_input(
            "En-tête (au-dessus du titre)",
            description="Vide = pas d'en-tête.",
            default=(embed.get("author") or {}).get("name"),
            max_length=256,
        )
        self.add_item(label)
        label, self.footer_input = label_input(
            "Pied de page",
            description="Vide = pas de pied de page.",
            default=(embed.get("footer") or {}).get("text"),
            max_length=2048,
        )
        self.add_item(label)

        self.timestamp_select = choice_select(
            [
                ("Date de publication", "yes", "🕒"),
                ("Aucune date", "no", "🚫"),
            ],
            "yes" if embed.get("timestamp") else "no",
        )
        self.add_item(discord.ui.Label(text="Date en bas du cadre", component=self.timestamp_select))

        has_icon = bool(
            (embed.get("author") or {}).get("icon_url")
            or (embed.get("footer") or {}).get("icon_url")
        )
        self.icon_select = choice_select(
            [
                ("Logo du serveur dans l'en-tête et le pied", "yes", "🦊"),
                ("Pas de logo", "no", "🚫"),
            ],
            "yes" if has_icon else "no",
        )
        self.add_item(discord.ui.Label(text="Logo", component=self.icon_select))

    async def apply(self, interaction: discord.Interaction) -> str | None:
        embed = self.embed
        color = parse_color(self.color_input.value)

        if color is None:
            embed.pop("color", None)
        else:
            embed["color"] = color

        guild = interaction.guild
        icon = guild.icon.url if guild and guild.icon and self.icon_select.values[0] == "yes" else None

        author = self.author_input.value.strip()
        footer = self.footer_input.value.strip()

        embed.pop("author", None)
        embed.pop("footer", None)

        if author:
            embed["author"] = {"name": author}
            if icon:
                embed["author"]["icon_url"] = icon

        if footer:
            embed["footer"] = {"text": footer}
            if icon:
                embed["footer"]["icon_url"] = icon

        if self.timestamp_select.values[0] == "yes":
            embed["timestamp"] = True
        else:
            embed.pop("timestamp", None)

        if self.icon_select.values[0] == "yes" and icon is None and (author or footer):
            return "ℹ️ Le serveur n'a pas de logo : rien n'a été ajouté."

        return None


class ImagesModal(StudioModal):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(studio, f"🖼️ Images du cadre {studio.index + 1}")
        embed = self.embed

        self.image_file = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.add_item(
            discord.ui.Label(
                text="Grande image : envoyer un fichier",
                description="PNG, JPG, GIF ou WEBP, 8 Mo maximum.",
                component=self.image_file,
            )
        )
        label, self.image_url = label_input(
            "…ou grande image : lien",
            default=self.current(embed, "image"),
            placeholder="https://…",
            max_length=500,
        )
        self.add_item(label)

        self.thumbnail_file = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.add_item(
            discord.ui.Label(
                text="Miniature (en haut à droite) : fichier",
                component=self.thumbnail_file,
            )
        )
        label, self.thumbnail_url = label_input(
            "…ou miniature : lien",
            default=self.current(embed, "thumbnail"),
            placeholder="https://…",
            max_length=500,
        )
        self.add_item(label)

    @staticmethod
    def current(embed: dict[str, Any], key: str) -> str:
        url = (embed.get(key) or {}).get("url") or ""

        return KEEP_UPLOAD if url.startswith(UPLOAD_PREFIX) else url

    async def resolve(
        self,
        interaction: discord.Interaction,
        key: str,
        upload: discord.ui.FileUpload,
        link: discord.ui.TextInput,
    ) -> None:
        files = list(upload.values)

        if files:
            attachment = files[0]

            if not (attachment.content_type or "").startswith("image/"):
                raise AnnouncementError(f"« {attachment.filename} » n'est pas une image.")

            if attachment.size > MAX_IMAGE_BYTES:
                raise AnnouncementError(
                    f"« {attachment.filename} » est trop lourde (8 Mo maximum)."
                )

            data = await attachment.read()
            image_id = await self.studio.cog.repository.add_image(
                interaction.guild_id, attachment.filename, attachment.content_type, data
            )
            self.studio.cog.cache_image(image_id, attachment.filename, data)
            self.embed[key] = {"url": f"{UPLOAD_PREFIX}{image_id}"}
            return

        value = link.value.strip()

        if value == KEEP_UPLOAD:
            return

        if not value:
            self.embed.pop(key, None)
            return

        if not URL_PATTERN.match(value) or not value.lower().startswith("http"):
            raise AnnouncementError("Le lien d'une image doit commencer par https://.")

        self.embed[key] = {"url": value}

    async def apply(self, interaction: discord.Interaction) -> str | None:
        await self.resolve(interaction, "image", self.image_file, self.image_url)
        await self.resolve(interaction, "thumbnail", self.thumbnail_file, self.thumbnail_url)

        return None


class SectionsModal(StudioModal):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(studio, f"📑 Sections du cadre {studio.index + 1}")
        fields = self.embed.get("fields") or []

        label, self.text_input = label_input(
            "Sections",
            description="Une ligne « ## Titre » puis le contenu. Vide = aucune section.",
            default=fields_to_text(fields),
            placeholder="## 📅 Date\n{date:25/12 21h}\n## 🎁 Récompense\n1 000 pièces",
            paragraph=True,
            max_length=4000,
        )
        self.add_item(label)

        inline = "yes" if fields and fields[0].get("inline") else "no"
        self.layout_select = choice_select(
            [
                ("Côte à côte (jusqu'à 3 par ligne)", "yes", "↔️"),
                ("Les unes sous les autres", "no", "↕️"),
            ],
            inline if fields else "yes",
        )
        self.add_item(discord.ui.Label(text="Disposition", component=self.layout_select))

    async def apply(self, interaction: discord.Interaction) -> str | None:
        text = self.dates(self.text_input.value)
        self.embed["fields"] = text_to_fields(text, self.layout_select.values[0] == "yes")

        return None


class ButtonsModal(StudioModal):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(studio, "🔗 Boutons liens")

        label, self.text_input = label_input(
            "Boutons sous l'annonce",
            description="Une ligne par bouton : « 🎮 Texte | https://lien ». 25 maximum.",
            default=buttons_to_text(studio.draft.get("buttons", [])),
            placeholder="📜 Règlement | https://discord.com/channels/…\n🎥 Twitch | https://twitch.tv/…",
            paragraph=True,
            max_length=4000,
        )
        self.add_item(label)

    async def apply(self, interaction: discord.Interaction) -> str | None:
        self.studio.draft["buttons"] = text_to_buttons(self.emojis(self.text_input.value))

        return None


class DeliveryModal(StudioModal):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(studio, "📣 Salon et mention")
        guild = studio.guild
        draft = studio.draft

        channel = guild.get_channel(draft["channel_id"]) if draft.get("channel_id") else None
        self.channel_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            default_values=[channel] if channel else [],
            required=True,
            min_values=1,
            max_values=1,
        )
        self.add_item(discord.ui.Label(text="Salon de publication", component=self.channel_select))

        self.mention_select = choice_select(
            [
                ("Personne", "none", "🔕"),
                ("@everyone (tout le serveur)", "everyone", "📢"),
                ("@here (membres en ligne)", "here", "🟢"),
                ("Un rôle (choisi ci-dessous)", "role", "🎭"),
            ],
            draft.get("mention", "none"),
        )
        self.add_item(
            discord.ui.Label(
                text="Mention",
                description="Envoie une notification. Affichée au-dessus du cadre.",
                component=self.mention_select,
            )
        )

        role = guild.get_role(draft["role_id"]) if draft.get("role_id") else None
        self.role_select = discord.ui.RoleSelect(
            default_values=[role] if role else [],
            required=False,
            min_values=0,
            max_values=1,
        )
        self.add_item(discord.ui.Label(text="Rôle à mentionner", component=self.role_select))

    async def apply(self, interaction: discord.Interaction) -> str | None:
        draft = self.studio.draft
        mention = self.mention_select.values[0]
        roles = list(self.role_select.values)

        if mention == "role" and not roles:
            raise AnnouncementError("Choisis le rôle à mentionner (ou une autre mention).")

        if self.channel_select.values:
            draft["channel_id"] = self.channel_select.values[0].id

        draft["mention"] = mention
        draft["role_id"] = roles[0].id if mention == "role" else None

        warning = self.studio.cog.permission_problem(
            interaction.guild, draft, member=interaction.user
        )

        return f"⚠️ {warning}" if warning else None


class ScheduleModal(StudioModal):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(studio, "⏰ Programmer l'annonce")

        label, self.when_input = label_input(
            "Date et heure de publication",
            description=f"Heure de {studio.cog.tz_name}. Ex : 01/12 18h, demain 9h, dans 2h.",
            placeholder="01/12/2026 18:00",
            max_length=40,
            required=True,
        )
        self.add_item(label)

    async def apply(self, interaction: discord.Interaction) -> str | None:
        text = self.when_input.value.strip()
        now = datetime.now(timezone.utc)
        moment: datetime | None

        if text.lower().startswith("dans "):
            delay = parse_duration(text[5:])
            moment = now + delay if delay else None
        else:
            moment = parse_datetime(text, self.studio.cog.tz, now)

            if moment is None:
                delay = parse_duration(text)
                moment = now + delay if delay else None

        if moment is None:
            raise AnnouncementError(
                f"Je ne comprends pas « {text} ». Exemples : `01/12 18h`, "
                "`25/12/2026 18:00`, `demain 9h`, `dans 2h`."
            )

        if moment < now + timedelta(minutes=1):
            raise AnnouncementError("Cette date est déjà passée (ou dans moins d'une minute).")

        if moment > now + timedelta(days=366):
            raise AnnouncementError("Une annonce se programme au plus un an à l'avance.")

        scheduled_id = await self.studio.cog.schedule(interaction, self.studio.draft, moment)
        self.studio.reset_after_send()
        stamp = int(moment.timestamp())

        return (
            f"⏰ Annonce n°{scheduled_id} programmée pour le <t:{stamp}:F> (<t:{stamp}:R>). "
            "Gère-la avec `/annonce programmees`. Le studio repart sur un brouillon vide."
        )


class ImportModal(StudioModal):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(studio, "📥 Importer (Discohook / JSON)")

        label, self.json_input = label_input(
            "JSON à coller",
            description="Copié depuis l'éditeur JSON de discohook.app.",
            placeholder='{"content": "...", "embeds": [ ... ]}',
            paragraph=True,
            max_length=4000,
        )
        self.add_item(label)

        self.file_input = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.add_item(
            discord.ui.Label(
                text="…ou un fichier .json",
                description="Pour les messages trop longs pour être collés.",
                component=self.file_input,
            )
        )

    async def apply(self, interaction: discord.Interaction) -> str | None:
        text = self.json_input.value.strip()
        files = list(self.file_input.values)

        if files:
            if files[0].size > 200_000:
                raise AnnouncementError("Fichier trop gros (200 Ko maximum).")

            try:
                text = (await files[0].read()).decode("utf-8-sig")
            except UnicodeDecodeError as error:
                raise AnnouncementError("Ce fichier n'est pas un texte JSON.") from error

        if not text:
            raise AnnouncementError("Colle un JSON ou envoie un fichier .json.")

        imported, warnings = import_message(text)
        draft = self.studio.draft
        draft["content"] = imported["content"]
        draft["embeds"] = imported["embeds"] or [{"title": "", "description": "", "fields": []}]
        draft["buttons"] = imported["buttons"]
        self.studio.index = 0

        lines = [f"📥 Importé : {len(imported['embeds'])} cadre(s), {len(imported['buttons'])} bouton(s)."]
        lines += [f"⚠️ {warning}" for warning in warnings]

        return "\n".join(lines)


class TemplateNameModal(discord.ui.Modal):
    def __init__(self, studio: StudioView, menu_interaction: discord.Interaction) -> None:
        super().__init__(title="💾 Enregistrer comme modèle", timeout=600)
        self.studio = studio
        self.menu_interaction = menu_interaction
        label, self.name_input = label_input(
            "Nom du modèle",
            description="Un modèle du même nom est remplacé.",
            default=summary_title(studio.draft)[:80],
            max_length=80,
            required=True,
        )
        self.add_item(label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name_input.value.strip()
        repository = self.studio.cog.repository
        existing = {template["name"] for template in await repository.list_templates(interaction.guild_id)}

        if name not in existing and await repository.count_templates(interaction.guild_id) >= 25:
            await send_error(interaction, "25 modèles maximum : supprimes-en un d'abord.")
            return

        template = dict(self.studio.draft, editing=None)
        await repository.save_template(interaction.guild_id, name, template, interaction.user.id)
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"💾 Modèle **{name}** enregistré.",
                color=SUCCESS_COLOR,
            ),
            view=None,
        )


# ============================================================
# PETITES VUES ANNEXES
# ============================================================


class TemplatesView(discord.ui.View):
    def __init__(self, studio: StudioView, templates: list[dict[str, Any]]) -> None:
        super().__init__(timeout=300)
        self.studio = studio

        if templates:
            load = discord.ui.Select(
                placeholder="📂 Charger un modèle dans le studio…",
                options=[
                    discord.SelectOption(label=t["name"][:100], value=str(t["id"]), emoji="📄")
                    for t in templates
                ],
            )
            load.callback = self.load
            self.add_item(load)

            delete = discord.ui.Select(
                placeholder="🗑️ Supprimer un modèle…",
                options=[
                    discord.SelectOption(label=t["name"][:100], value=str(t["id"]), emoji="🗑️")
                    for t in templates
                ],
            )
            delete.callback = self.delete
            self.add_item(delete)

        save = discord.ui.Button(
            label="Enregistrer le brouillon actuel comme modèle",
            emoji="💾",
            style=discord.ButtonStyle.success,
        )
        save.callback = self.save
        self.add_item(save)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.studio.owner_id

    async def load(self, interaction: discord.Interaction) -> None:
        template_id = int(interaction.data["values"][0])
        template = await self.studio.cog.repository.get_template(interaction.guild_id, template_id)

        if template is None:
            await send_error(interaction, "Ce modèle n'existe plus.")
            return

        template["editing"] = self.studio.draft.get("editing")

        if not template.get("embeds"):
            template["embeds"] = [{"title": "", "description": "", "fields": []}]

        self.studio.draft = template
        self.studio.index = 0
        await interaction.response.edit_message(
            embed=discord.Embed(description="📂 Modèle chargé dans le studio.", color=SUCCESS_COLOR),
            view=None,
        )
        await self.studio.refresh(None, notice=f"📂 Modèle chargé : {summary_title(template)}")

    async def delete(self, interaction: discord.Interaction) -> None:
        template_id = int(interaction.data["values"][0])
        name = await self.studio.cog.repository.delete_template(interaction.guild_id, template_id)
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"🗑️ Modèle **{name}** supprimé." if name else "Ce modèle n'existait plus.",
                color=SUCCESS_COLOR,
            ),
            view=None,
        )

    async def save(self, interaction: discord.Interaction) -> None:
        if self.studio.is_empty():
            await send_error(interaction, "Le brouillon est vide : rien à enregistrer.")
            return

        await interaction.response.send_modal(TemplateNameModal(self.studio, interaction))


class ConfirmPublishView(discord.ui.View):
    def __init__(self, studio: StudioView) -> None:
        super().__init__(timeout=180)
        self.studio = studio

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.studio.owner_id

    @discord.ui.button(label="Publier maintenant", emoji="🚀", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=discord.Embed(description="⏳ Publication en cours…", color=INFO_COLOR),
            view=None,
        )

        try:
            message = await self.studio.cog.publish(
                interaction.guild, self.studio.draft, interaction.user
            )
        except AnnouncementError as error:
            await interaction.edit_original_response(embed=error_embed(str(error)))
            return

        await interaction.edit_original_response(
            embed=discord.Embed(
                description=f"✅ Annonce publiée : {message.jump_url}",
                color=SUCCESS_COLOR,
            )
        )
        self.studio.reset_after_send()
        await self.studio.refresh(
            None,
            notice=f"✅ Publiée : {message.jump_url}\nLe studio repart sur un brouillon vide.",
        )

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=discord.Embed(description="Publication annulée.", color=INFO_COLOR),
            view=None,
        )


# ============================================================
# LE STUDIO
# ============================================================


class StudioView(discord.ui.View):
    def __init__(
        self,
        cog: AnnouncementCog,
        origin: discord.Interaction,
        draft: dict[str, Any],
    ) -> None:
        super().__init__(timeout=STUDIO_TIMEOUT)
        self.cog = cog
        self.origin = origin
        self.owner_id = origin.user.id
        self.guild: discord.Guild = origin.guild
        self.draft = draft
        self.index = 0
        self.confirm_reset = False

        if not self.draft.get("embeds"):
            self.draft["embeds"] = [{"title": "", "description": "", "fields": []}]

        self.build()

    # -------- état --------

    @property
    def current_embed(self) -> dict[str, Any]:
        self.index = max(0, min(self.index, len(self.draft["embeds"]) - 1))
        return self.draft["embeds"][self.index]

    @property
    def editing(self) -> bool:
        return bool(self.draft.get("editing"))

    def is_empty(self) -> bool:
        from bot.features.announcements.model import is_empty

        return is_empty(self.draft)

    def reset_after_send(self) -> None:
        channel_id = None if self.editing else self.draft.get("channel_id")
        chosen_format = self.draft.get("format", "classic")
        self.draft = self.cog.new_draft(self.guild)
        self.draft["format"] = chosen_format  # on garde le format choisi

        if channel_id:
            self.draft["channel_id"] = channel_id

        self.index = 0

    # -------- affichage --------

    async def refresh(
        self,
        interaction: discord.Interaction | None,
        *,
        notice: str | None = None,
    ) -> None:
        self.confirm_reset = False if notice != "reset?" else self.confirm_reset
        await self.cog.repository.save_draft(self.guild.id, self.owner_id, self.draft)
        self.build()
        kwargs = await self.cog.studio_message(self, notice=notice if notice != "reset?" else None)

        try:
            if interaction is not None and not interaction.response.is_done():
                await interaction.response.edit_message(**kwargs, view=self)
            else:
                await self.origin.edit_original_response(**kwargs, view=self)
        except discord.HTTPException as error:
            LOGGER.warning("Studio d'annonce non mis à jour : %s", error)

            if interaction is not None:
                await send_error(
                    interaction,
                    "Discord a refusé l'aperçu (image introuvable, émoji invalide "
                    f"ou lien incorrect ?).\n`{str(error)[:300]}`",
                )

    async def on_timeout(self) -> None:
        try:
            await self.origin.edit_original_response(
                content=(
                    "⌛ Le studio s'est fermé après 14 minutes. Ton brouillon est "
                    "enregistré : `/annonce creer` pour le reprendre."
                ),
                view=None,
            )
        except discord.HTTPException:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await send_error(interaction, "Ce studio appartient à quelqu'un d'autre.")
            return False

        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: Any, /) -> None:
        LOGGER.exception("Erreur dans le studio d'annonce", exc_info=error)
        await send_error(interaction, "Une erreur inattendue est survenue. Réessaie.")

    # -------- composants --------

    def button(
        self,
        label: str,
        emoji: str,
        callback,
        *,
        row: int,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        disabled: bool = False,
    ) -> None:
        item = discord.ui.Button(label=label, emoji=emoji, style=style, row=row, disabled=disabled)
        item.callback = callback
        self.add_item(item)

    def build(self) -> None:
        self.clear_items()
        embeds = self.draft["embeds"]

        self.button("Texte", "✏️", self.on_text, row=0, style=discord.ButtonStyle.primary)
        self.button("Style", "🎨", self.on_style, row=0)
        self.button("Images", "🖼️", self.on_images, row=0)
        self.button("Sections", "📑", self.on_sections, row=0)
        self.button("Boutons", "🔗", self.on_buttons, row=0)

        options = [
            discord.SelectOption(
                label=f"Cadre {number} : {frame_name(embed)}",
                value=str(number - 1),
                emoji="🖊️" if number - 1 == self.index else "🗂️",
                default=number - 1 == self.index,
            )
            for number, embed in enumerate(embeds, start=1)
        ]

        if len(embeds) < MAX_EMBEDS:
            options.append(
                discord.SelectOption(
                    label="Ajouter un cadre",
                    value="add",
                    emoji="➕",
                    description="Un cadre de plus sous les autres (10 max).",
                )
            )

        if len(embeds) > 1:
            options.append(
                discord.SelectOption(
                    label=f"Supprimer le cadre {self.index + 1}",
                    value="delete",
                    emoji="🗑️",
                )
            )

        select = discord.ui.Select(options=options, row=1, placeholder="Cadre à modifier")
        select.callback = self.on_frame
        self.add_item(select)

        self.button("Salon et mention", "📣", self.on_delivery, row=2)
        self.button("Modèles", "🧩", self.on_templates, row=2)
        self.button("Importer", "📥", self.on_import, row=2)
        self.button("Exporter", "📤", self.on_export, row=2)
        self.button("Aide", "❔", self.on_help, row=2)

        if self.editing:
            self.button(
                "Enregistrer les modifications",
                "💾",
                self.on_publish,
                row=3,
                style=discord.ButtonStyle.success,
            )
        else:
            self.button("Publier", "🚀", self.on_publish, row=3, style=discord.ButtonStyle.success)
            self.button("Programmer", "⏰", self.on_schedule, row=3, style=discord.ButtonStyle.primary)

        current = self.draft.get("format", "classic")
        # Discord ne permet pas de changer le format d'un message publié.
        self.button(
            f"Format : {FORMAT_NAMES.get(current, 'classique')}",
            "📐",
            self.on_format,
            row=3,
            disabled=self.editing,
        )

        if current != "classic":
            self.button("Aperçu réel", "👁️", self.on_large_preview, row=3)

        self.button(
            "Confirmer : tout effacer ?" if self.confirm_reset
            else ("Quitter la modification" if self.editing else "Recommencer"),
            "⚠️" if self.confirm_reset else "🔄",
            self.on_reset,
            row=3,
            style=discord.ButtonStyle.danger,
        )

        # Aperçu des boutons liens (les 5 premiers).
        for button in self.draft.get("buttons", [])[:5]:
            try:
                self.add_item(
                    discord.ui.Button(
                        label=button_label(button),
                        url=button["url"],
                        emoji=button.get("emoji"),
                        row=4,
                    )
                )
            except (ValueError, TypeError):
                continue

    # -------- actions --------

    async def on_text(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TextModal(self))

    async def on_style(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(StyleModal(self))

    async def on_images(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ImagesModal(self))

    async def on_sections(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SectionsModal(self))

    async def on_buttons(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ButtonsModal(self))

    async def on_delivery(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(DeliveryModal(self))

    async def on_import(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ImportModal(self))

    async def on_frame(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]
        embeds = self.draft["embeds"]

        if value == "add":
            color = self.current_embed.get("color")
            embeds.append({"title": "", "description": "", "fields": [], **({"color": color} if color else {})})
            self.index = len(embeds) - 1
        elif value == "delete":
            if len(embeds) > 1:
                embeds.pop(self.index)
                self.index = max(0, self.index - 1)
        else:
            self.index = int(value)

        await self.refresh(interaction)

    async def on_templates(self, interaction: discord.Interaction) -> None:
        templates = await self.cog.repository.list_templates(interaction.guild_id)
        description = (
            "Charge un modèle pour repartir d'une annonce type, ou enregistre "
            "ton brouillon actuel pour le réutiliser plus tard."
            if templates
            else "Aucun modèle pour l'instant. Enregistre ton brouillon actuel pour le réutiliser."
        )
        await interaction.response.send_message(
            embed=discord.Embed(title="🧩 Modèles d'annonce", description=description, color=INFO_COLOR),
            view=TemplatesView(self, templates),
            ephemeral=True,
        )

    async def on_export(self, interaction: discord.Interaction) -> None:
        if self.is_empty():
            await send_error(interaction, "Le brouillon est vide : rien à exporter.")
            return

        text = export_message(self.draft)
        note = (
            "Ouvre **discohook.app**, ouvre l'éditeur **JSON** et colle le contenu "
            "du fichier. Une fois retouché, recopie le JSON et utilise 📥 **Importer**."
        )

        if upload_ids(self.draft):
            note += (
                "\n⚠️ Les images envoyées depuis Discord ne sont pas exportées : "
                "elles restent dans le studio, ré-ajoute-les après l'import."
            )

        await interaction.response.send_message(
            content=note,
            file=discord.File(io.BytesIO(text.encode("utf-8")), filename="annonce.json"),
            ephemeral=True,
        )

    async def on_help(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=discord.Embed(title="❔ Studio d'annonce : astuces", description=HELP_TEXT, color=INFO_COLOR),
            ephemeral=True,
        )

    async def on_publish(self, interaction: discord.Interaction) -> None:
        if self.editing:
            await interaction.response.defer()

            try:
                message = await self.cog.apply_edit(interaction.guild, self.draft, interaction.user)
            except AnnouncementError as error:
                await send_error(interaction, str(error))
                return

            self.reset_after_send()
            await self.refresh(
                None,
                notice=f"💾 Annonce modifiée : {message.jump_url}\nLe studio repart sur un brouillon vide.",
            )
            return

        try:
            self.cog.check_ready(interaction.guild, self.draft, member=interaction.user)
        except AnnouncementError as error:
            await send_error(interaction, str(error))
            return

        draft = self.draft
        mention = {
            "everyone": "**@everyone** (tout le serveur sera notifié)",
            "here": "**@here** (les membres en ligne seront notifiés)",
            "role": f"<@&{draft.get('role_id')}>",
        }.get(draft.get("mention"), "aucune")
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🚀 Publier l'annonce ?",
                description=(
                    f"**{summary_title(draft)}**\n"
                    f"Salon : <#{draft['channel_id']}>\nMention : {mention}"
                ),
                color=INFO_COLOR,
            ),
            view=ConfirmPublishView(self),
            ephemeral=True,
        )

    async def on_schedule(self, interaction: discord.Interaction) -> None:
        try:
            self.cog.check_ready(interaction.guild, self.draft, member=interaction.user)
        except AnnouncementError as error:
            await send_error(interaction, str(error))
            return

        await interaction.response.send_modal(ScheduleModal(self))

    async def on_format(self, interaction: discord.Interaction) -> None:
        order = ("classic", "large", "text")
        current = self.draft.get("format", "classic")
        self.draft["format"] = order[(order.index(current) + 1) % len(order)] if current in order else "large"
        await self.refresh(interaction, notice=FORMAT_NOTICES[self.draft["format"]])

    async def on_large_preview(self, interaction: discord.Interaction) -> None:
        await self.cog.large_preview(interaction, self.draft)

    async def on_reset(self, interaction: discord.Interaction) -> None:
        if not self.confirm_reset:
            self.confirm_reset = True
            await self.refresh(interaction, notice="reset?")
            return

        self.confirm_reset = False
        was_editing = self.editing
        self.draft = self.cog.new_draft(self.guild)
        self.index = 0
        await self.refresh(
            interaction,
            notice="🔄 Modification abandonnée : le message publié n'a pas changé."
            if was_editing
            else "🔄 Brouillon effacé.",
        )
