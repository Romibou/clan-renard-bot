"""
Annonces : modèle de données et règles, sans aucun accès à Discord
ni à la base (donc facile à tester).

Une annonce (brouillon, modèle ou annonce programmée) est un simple
dictionnaire JSON, proche du format de l'API Discord et de Discohook :

    {
        "content": "texte au-dessus du cadre",
        "embeds": [ {title, description, url, color, author, footer,
                     image, thumbnail, fields, timestamp}, ... ],
        "buttons": [ {"label": ..., "url": ..., "emoji": ...}, ... ],
        "channel_id": 123 | None,
        "mention": "none" | "everyone" | "here" | "role",
        "role_id": 456 | None,
        "editing": {"channel_id": ..., "message_id": ...} | None,
    }

Une image envoyée depuis Discord est stockée en base et notée
"upload:<id>" à la place d'un lien.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from datetime import datetime, timedelta, tzinfo
from typing import Any

# Limites de Discord.
MAX_CONTENT = 2000
MAX_EMBEDS = 10
MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_FIELDS = 25
MAX_FIELD_NAME = 256
MAX_FIELD_VALUE = 1024
MAX_FOOTER = 2048
MAX_AUTHOR = 256
MAX_EMBEDS_TOTAL = 6000
MAX_BUTTONS = 25
MAX_BUTTON_LABEL = 80

MAX_IMAGE_BYTES = 8 * 1024 * 1024
UPLOAD_PREFIX = "upload:"

DEFAULT_COLOR = 0xF28C28  # orange renard

MENTIONS = ("none", "everyone", "here", "role")

# classic = cadre habituel ; large = nouveau format Discord, dans un bloc ;
# text = message texte simple, en pleine largeur comme un message de membre.
FORMATS = ("classic", "large", "text")
NEW_FORMATS = ("large",)  # formats « Components V2 »

COLOR_NAMES = {
    "renard": 0xF28C28,
    "orange": 0xF28C28,
    "rouge": 0xE74C3C,
    "jaune": 0xF1C40F,
    "or": 0xD4AF37,
    "vert": 0x2ECC71,
    "bleu": 0x3498DB,
    "cyan": 0x1ABC9C,
    "violet": 0x9B59B6,
    "rose": 0xFF78AA,
    "blanc": 0xFFFFFF,
    "gris": 0x95A5A6,
    "noir": 0x111111,
    "blurple": 0x5865F2,
}


class AnnouncementError(ValueError):
    """Erreur à montrer telle quelle à l'administrateur."""


# ------------------------------------------------------------
# BROUILLON PAR DÉFAUT
# ------------------------------------------------------------


def default_embed(guild_name: str, icon_url: str | None) -> dict[str, Any]:
    author: dict[str, Any] = {"name": guild_name}
    footer: dict[str, Any] = {"text": f"L'équipe {guild_name}"}

    if icon_url:
        author["icon_url"] = icon_url
        footer["icon_url"] = icon_url

    return {
        "title": "",
        "description": "",
        "color": DEFAULT_COLOR,
        "author": author,
        "footer": footer,
        "timestamp": True,
        "fields": [],
    }


def default_draft(guild_name: str, icon_url: str | None) -> dict[str, Any]:
    return {
        "content": "",
        "embeds": [default_embed(guild_name, icon_url)],
        "buttons": [],
        "channel_id": None,
        "mention": "none",
        "role_id": None,
        "editing": None,
        "format": "classic",
    }


def normalize_draft(data: Any) -> dict[str, Any]:
    """Complète un brouillon lu en base (anciennes versions, valeurs manquantes)."""
    if isinstance(data, str):
        data = json.loads(data)

    if not isinstance(data, dict):
        data = {}

    draft = copy.deepcopy(data)
    draft.setdefault("content", "")
    draft["content"] = str(draft["content"] or "")

    embeds = draft.get("embeds")
    draft["embeds"] = [
        _clean_embed(embed) for embed in embeds if isinstance(embed, dict)
    ][:MAX_EMBEDS] if isinstance(embeds, list) else []

    buttons = draft.get("buttons")
    draft["buttons"] = [
        button
        for button in (buttons if isinstance(buttons, list) else [])
        if isinstance(button, dict) and button.get("label") and button.get("url")
    ][:MAX_BUTTONS]

    draft["channel_id"] = _optional_int(draft.get("channel_id"))
    draft["role_id"] = _optional_int(draft.get("role_id"))

    if draft.get("mention") not in MENTIONS:
        draft["mention"] = "none"

    if draft["mention"] == "role" and draft["role_id"] is None:
        draft["mention"] = "none"

    draft["format"] = draft.get("format") if draft.get("format") in FORMATS else "classic"

    editing = draft.get("editing")

    if isinstance(editing, dict) and editing.get("message_id"):
        draft["editing"] = {
            "channel_id": int(editing["channel_id"]),
            "message_id": int(editing["message_id"]),
        }
    else:
        draft["editing"] = None

    return draft


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


EMBED_KEYS = (
    "title",
    "description",
    "url",
    "color",
    "author",
    "footer",
    "image",
    "thumbnail",
    "fields",
    "timestamp",
)


def _clean_embed(embed: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}

    for key in EMBED_KEYS:
        if key in embed and embed[key] not in (None, "", [], {}):
            cleaned[key] = copy.deepcopy(embed[key])

    cleaned.setdefault("title", "")
    cleaned.setdefault("description", "")

    fields = cleaned.get("fields")
    cleaned["fields"] = [
        {
            "name": str(field.get("name") or "​"),
            "value": str(field.get("value") or "​"),
            "inline": bool(field.get("inline", False)),
        }
        for field in (fields if isinstance(fields, list) else [])
        if isinstance(field, dict)
    ][:MAX_FIELDS]

    if "color" in cleaned:
        try:
            cleaned["color"] = int(cleaned["color"])
        except (TypeError, ValueError):
            cleaned.pop("color")

    for key in ("author", "footer", "image", "thumbnail"):
        if key in cleaned and not isinstance(cleaned[key], dict):
            cleaned.pop(key)

    return cleaned


# ------------------------------------------------------------
# CONTENU
# ------------------------------------------------------------


def embed_has_body(embed: dict[str, Any]) -> bool:
    """Le cadre contient-il autre chose que la signature ?"""
    return bool(
        embed.get("title")
        or embed.get("description")
        or embed.get("fields")
        or (embed.get("image") or {}).get("url")
        or (embed.get("thumbnail") or {}).get("url")
    )


def is_empty(draft: dict[str, Any]) -> bool:
    return not draft.get("content", "").strip() and not any(
        embed_has_body(embed) for embed in draft.get("embeds", [])
    )


def embed_length(embed: dict[str, Any]) -> int:
    total = len(embed.get("title") or "") + len(embed.get("description") or "")
    total += len((embed.get("author") or {}).get("name") or "")
    total += len((embed.get("footer") or {}).get("text") or "")

    for field in embed.get("fields") or []:
        total += len(field.get("name") or "") + len(field.get("value") or "")

    return total


def problems(draft: dict[str, Any]) -> list[str]:
    """Tout ce qui empêcherait Discord d'accepter le message."""
    found: list[str] = []

    if is_empty(draft):
        found.append("L'annonce est vide : ajoute au moins un titre ou un texte.")

    if len(mention_text(draft) + draft.get("content", "")) > MAX_CONTENT:
        found.append(
            f"Le message au-dessus du cadre dépasse {MAX_CONTENT} caractères."
        )

    total = 0

    for index, embed in enumerate(draft.get("embeds", []), start=1):
        name = f"Cadre {index}"
        total += embed_length(embed)

        if len(embed.get("title") or "") > MAX_TITLE:
            found.append(f"{name} : titre trop long ({MAX_TITLE} max).")

        if len(embed.get("description") or "") > MAX_DESCRIPTION:
            found.append(f"{name} : texte trop long ({MAX_DESCRIPTION} max).")

        if len(embed.get("fields") or []) > MAX_FIELDS:
            found.append(f"{name} : {MAX_FIELDS} sections maximum.")

        for field in embed.get("fields") or []:
            if len(field["name"]) > MAX_FIELD_NAME:
                found.append(f"{name} : un titre de section dépasse {MAX_FIELD_NAME} caractères.")
            if len(field["value"]) > MAX_FIELD_VALUE:
                found.append(
                    f"{name} : la section « {field['name'][:40]} » dépasse "
                    f"{MAX_FIELD_VALUE} caractères."
                )

        if len((embed.get("footer") or {}).get("text") or "") > MAX_FOOTER:
            found.append(f"{name} : pied de page trop long.")

        if len((embed.get("author") or {}).get("name") or "") > MAX_AUTHOR:
            found.append(f"{name} : en-tête trop long ({MAX_AUTHOR} max).")

    if draft.get("format") in NEW_FORMATS:
        from bot.features.announcements.layout import layout_problems

        found += layout_problems(draft)
    elif draft.get("format") == "text":
        from bot.features.announcements.layout import MAX_PARTS, plain_parts

        count = len(plain_parts(draft, now=datetime.now()))

        if count > MAX_PARTS:
            found.append(
                f"En pleine largeur, l'annonce ferait {count} messages : {MAX_PARTS} maximum "
                "(environ 10 000 caractères). Raccourcis-la."
            )
    elif total > MAX_EMBEDS_TOTAL:
        found.append(
            f"Les cadres font {total} caractères au total "
            f"(Discord en accepte {MAX_EMBEDS_TOTAL})."
        )

    return found


def mention_text(draft: dict[str, Any]) -> str:
    mention = draft.get("mention", "none")

    if mention == "everyone":
        return "@everyone"
    if mention == "here":
        return "@here"
    if mention == "role" and draft.get("role_id"):
        return f"<@&{draft['role_id']}>"
    return ""


def message_content(draft: dict[str, Any]) -> str:
    """Texte final du message : la mention puis le texte hors cadre."""
    parts = [mention_text(draft), draft.get("content", "").strip()]

    return "\n".join(part for part in parts if part)


def upload_ids(draft: dict[str, Any]) -> set[int]:
    found: set[int] = set()

    for embed in draft.get("embeds", []):
        for key in ("image", "thumbnail"):
            url = (embed.get(key) or {}).get("url") or ""

            if url.startswith(UPLOAD_PREFIX):
                try:
                    found.add(int(url[len(UPLOAD_PREFIX):]))
                except ValueError:
                    pass

    return found


def attachment_name(upload_id: int, filename: str) -> str:
    """Nom de fichier sûr pour attachment://, unique par image."""
    stem, _, extension = filename.rpartition(".")

    if not stem:
        stem, extension = filename, "png"

    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem)[:40] or "image"
    extension = re.sub(r"[^A-Za-z0-9]+", "", extension)[:5] or "png"

    return f"{upload_id}_{stem}.{extension.lower()}"


def render_embeds(
    draft: dict[str, Any],
    *,
    uploads: dict[int, str] | None = None,
    now: datetime | None = None,
    placeholder: str | None = None,
) -> list[dict[str, Any]]:
    """
    Cadres au format de l'API Discord, prêts pour discord.Embed.from_dict.
    `uploads` associe l'id d'une image envoyée à son nom attachment://.
    """
    uploads = uploads or {}
    rendered: list[dict[str, Any]] = []

    for embed in draft.get("embeds", []):
        data = copy.deepcopy(embed)

        for key in ("image", "thumbnail"):
            url = (data.get(key) or {}).get("url") or ""

            if url.startswith(UPLOAD_PREFIX):
                try:
                    name = uploads.get(int(url[len(UPLOAD_PREFIX):]))
                except ValueError:
                    name = None

                if name:
                    data[key] = {"url": f"attachment://{name}"}
                else:
                    data.pop(key, None)
            elif not url:
                data.pop(key, None)

        timestamp = data.pop("timestamp", None)

        if timestamp is True and now is not None:
            data["timestamp"] = now.isoformat()
        elif isinstance(timestamp, str) and timestamp:
            data["timestamp"] = timestamp

        for key in ("title", "description", "url"):
            if not data.get(key):
                data.pop(key, None)

        if not data.get("fields"):
            data.pop("fields", None)

        if not embed_has_body(embed):
            if not placeholder:
                # Un cadre sans contenu (juste la signature) n'est pas publié.
                continue
            data["description"] = placeholder

        if not any(
            key in data
            for key in ("title", "description", "fields", "image", "thumbnail", "author", "footer")
        ):
            continue

        rendered.append(data)

    return rendered


# ------------------------------------------------------------
# DATES : {date:...} et {dans:...}
# ------------------------------------------------------------

DATE_PATTERN = re.compile(
    r"^(?:(?P<word>aujourd'hui|aujourdhui|demain|après-demain|apres-demain)"
    r"|(?P<day>\d{1,2})/(?P<month>\d{1,2})(?:/(?P<year>\d{2,4}))?)"
    r"(?:\s*(?:à|a)?\s*(?P<hour>\d{1,2})\s*(?:[h:]\s*(?P<minute>\d{2})?)?)?$",
    re.IGNORECASE,
)


def parse_datetime(text: str, tz: tzinfo, now: datetime) -> datetime | None:
    """
    Comprend "25/12/2026 18:00", "25/12 18h", "25/12/2026",
    "demain 18h30", "aujourd'hui 21h". Sans année : la prochaine
    occurrence. Sans heure : minuit. Retourne une date avec fuseau.
    """
    cleaned = " ".join(text.strip().lower().replace("’", "'").split())
    match = DATE_PATTERN.match(cleaned)

    if match is None:
        return None

    local_now = now.astimezone(tz)
    hour = int(match["hour"] or 0)
    minute = int(match["minute"] or 0)

    if hour > 23 or minute > 59:
        return None

    if match["word"]:
        offset = {
            "aujourd'hui": 0,
            "aujourdhui": 0,
            "demain": 1,
            "après-demain": 2,
            "apres-demain": 2,
        }[match["word"]]
        day = (local_now + timedelta(days=offset)).date()

        return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)

    year_text = match["year"]
    year = int(year_text) if year_text else local_now.year

    if year_text and len(year_text) == 2:
        year += 2000

    try:
        result = datetime(
            year, int(match["month"]), int(match["day"]), hour, minute, tzinfo=tz
        )
    except ValueError:
        return None

    if not year_text and result < local_now - timedelta(days=1):
        try:
            result = result.replace(year=year + 1)
        except ValueError:
            return None

    return result


DATE_TOKEN = re.compile(r"\{(date|dans|heure|jour):([^{}]+)\}", re.IGNORECASE)
TOKEN_STYLES = {"date": "F", "dans": "R", "heure": "t", "jour": "D"}


def convert_date_tokens(text: str, tz: tzinfo, now: datetime) -> tuple[str, list[str]]:
    """
    Remplace {date:25/12 18h} par une date Discord qui s'affiche à
    l'heure de chaque membre. {dans:...} = « dans 3 jours »,
    {heure:...} = « 18:00 », {jour:...} = « 25 décembre 2026 ».
    Retourne le texte et la liste des dates non comprises.
    """
    errors: list[str] = []

    def replace(match: re.Match[str]) -> str:
        moment = parse_datetime(match[2], tz, now)

        if moment is None:
            errors.append(match[0])
            return match[0]

        return f"<t:{int(moment.timestamp())}:{TOKEN_STYLES[match[1].lower()]}>"

    return DATE_TOKEN.sub(replace, text), errors


EMOJI_SHORTCODE = re.compile(r"(?<![<\w\\]):([A-Za-z0-9_~]{2,32}):(?!\d)")


def convert_emojis(text: str, emojis: list[tuple[str, int, bool]]) -> str:
    """
    Remplace « :clanrenard_yes: » par le vrai émoji du serveur
    (<:clanrenard_yes:123…>). Dans une fenêtre de saisie, Discord ne
    le fait pas tout seul. Les noms inconnus restent tels quels.
    """
    by_name: dict[str, str] = {}

    for name, emoji_id, animated in emojis:
        by_name.setdefault(name, f"<{'a' if animated else ''}:{name}:{emoji_id}>")
        by_name.setdefault(name.lower(), by_name[name])

    def replace(match: re.Match[str]) -> str:
        name = match[1]
        return by_name.get(name) or by_name.get(name.lower()) or match[0]

    return EMOJI_SHORTCODE.sub(replace, text) if by_name else text


# ------------------------------------------------------------
# SECTIONS, BOUTONS, COULEURS (saisie texte)
# ------------------------------------------------------------


def fields_to_text(fields: list[dict[str, Any]]) -> str:
    blocks = []

    for field in fields:
        value = "" if field["value"] == "​" else field["value"]
        name = "" if field["name"] == "​" else field["name"]
        blocks.append(f"## {name}\n{value}".rstrip())

    return "\n".join(blocks)


def text_to_fields(text: str, inline: bool) -> list[dict[str, Any]]:
    """
    Une section commence par une ligne « ## Titre », les lignes
    suivantes forment son contenu.
    """
    fields: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    orphan: list[str] = []

    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("## "):
            current = {"name": line[3:].strip() or "​", "lines": []}
            fields.append(current)
        elif current is None:
            if line.strip():
                orphan.append(line)
        else:
            current["lines"].append(line)

    if orphan:
        raise AnnouncementError(
            "Chaque section doit commencer par une ligne `## Titre`.\n"
            f"Ligne sans titre : « {orphan[0][:60]} »"
        )

    if len(fields) > MAX_FIELDS:
        raise AnnouncementError(f"{MAX_FIELDS} sections maximum par cadre.")

    result = []

    for field in fields:
        value = "\n".join(field["lines"]).strip() or "​"

        if len(field["name"]) > MAX_FIELD_NAME:
            raise AnnouncementError(
                f"Le titre « {field['name'][:40]}… » dépasse {MAX_FIELD_NAME} caractères."
            )

        if len(value) > MAX_FIELD_VALUE:
            raise AnnouncementError(
                f"La section « {field['name'][:40]} » dépasse "
                f"{MAX_FIELD_VALUE} caractères."
            )

        result.append({"name": field["name"], "value": value, "inline": inline})

    return result


URL_PATTERN = re.compile(r"^(https?://|discord://)\S+$", re.IGNORECASE)
CUSTOM_EMOJI = re.compile(r"^<a?:\w{2,32}:\d{15,25}>$")


def _is_emoji(token: str) -> bool:
    if CUSTOM_EMOJI.match(token):
        return True

    return all(
        unicodedata.category(char) in ("So", "Sk", "Mn", "Cf", "Me")
        or char in "‍️"
        or "\U0001f1e6" <= char <= "\U0001f1ff"
        for char in token
    ) and any(unicodedata.category(char) == "So" or "\U0001f1e6" <= char <= "\U0001f1ff" for char in token)


def buttons_to_text(buttons: list[dict[str, Any]]) -> str:
    lines = []

    for button in buttons:
        label = button["label"]

        if button.get("emoji"):
            label = f"{button['emoji']} {label}"

        lines.append(f"{label} | {button['url']}")

    return "\n".join(lines)


def text_to_buttons(text: str) -> list[dict[str, Any]]:
    """Une ligne par bouton : « 🎮 Texte | https://lien »."""
    buttons: list[dict[str, Any]] = []

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()

        if not line:
            continue

        label, separator, url = line.rpartition("|")

        if not separator:
            raise AnnouncementError(
                f"Ligne « {line[:60]} » : écris `Texte | https://lien`."
            )

        label, url = label.strip(), url.strip()

        if not URL_PATTERN.match(url):
            raise AnnouncementError(
                f"« {url[:60]} » n'est pas un lien valide (il doit commencer par https://)."
            )

        emoji = None
        first, _, rest = label.partition(" ")

        if rest and _is_emoji(first):
            emoji, label = first, rest.strip()
        elif not rest and _is_emoji(first):
            emoji, label = first, ""

        if not label and not emoji:
            raise AnnouncementError(f"Le bouton vers {url[:60]} n'a pas de texte.")

        if len(label) > MAX_BUTTON_LABEL:
            raise AnnouncementError(
                f"Le texte « {label[:30]}… » dépasse {MAX_BUTTON_LABEL} caractères."
            )

        button: dict[str, Any] = {"label": label or "​", "url": url}

        if emoji:
            button["emoji"] = emoji

        buttons.append(button)

    if len(buttons) > MAX_BUTTONS:
        raise AnnouncementError(f"{MAX_BUTTONS} boutons maximum.")

    return buttons


def parse_color(text: str) -> int | None:
    """« #F28C28 », « F28C28 », « orange »… Vide = pas de couleur."""
    cleaned = text.strip().lower().lstrip("#")

    if not cleaned:
        return None

    if cleaned in COLOR_NAMES:
        return COLOR_NAMES[cleaned]

    if re.fullmatch(r"[0-9a-f]{6}", cleaned):
        return int(cleaned, 16)

    if re.fullmatch(r"[0-9a-f]{3}", cleaned):
        return int("".join(char * 2 for char in cleaned), 16)

    raise AnnouncementError(
        f"Couleur « {text.strip()[:20]} » inconnue. Écris un code comme "
        "`#F28C28` ou un nom : " + ", ".join(sorted(COLOR_NAMES)) + "."
    )


def color_to_text(color: int | None) -> str:
    return "" if color is None else f"#{int(color):06X}"


# ------------------------------------------------------------
# DISCOHOOK : IMPORT / EXPORT
# ------------------------------------------------------------


def _emoji_text(emoji: Any) -> str | None:
    if isinstance(emoji, str):
        return emoji or None

    if isinstance(emoji, dict):
        if emoji.get("id"):
            prefix = "a" if emoji.get("animated") else ""
            return f"<{prefix}:{emoji.get('name') or 'emoji'}:{emoji['id']}>"
        return emoji.get("name") or None

    return None


def import_message(text: str) -> tuple[dict[str, Any], list[str]]:
    """
    Lit le JSON de Discohook (éditeur JSON ou sauvegarde) ou d'un
    autre outil au format de l'API Discord. Retourne le contenu
    importé (content, embeds, buttons) et des avertissements.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise AnnouncementError(
            f"Ce n'est pas du JSON valide (ligne {error.lineno}, colonne {error.colno})."
        ) from error

    warnings: list[str] = []

    if isinstance(data, dict) and isinstance(data.get("messages"), list):
        messages = data["messages"]

        if not messages:
            raise AnnouncementError("La sauvegarde ne contient aucun message.")

        if len(messages) > 1:
            warnings.append(
                f"La sauvegarde contient {len(messages)} messages : seul le premier est importé."
            )

        data = messages[0].get("data", messages[0]) if isinstance(messages[0], dict) else {}

    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]

    if not isinstance(data, dict):
        raise AnnouncementError("Format inconnu : il faut un message avec `content` et/ou `embeds`.")

    content = data.get("content") or ""

    if not isinstance(content, str):
        content = str(content)

    raw_embeds = data.get("embeds") or []

    if not isinstance(raw_embeds, list):
        raise AnnouncementError("`embeds` doit être une liste.")

    if len(raw_embeds) > MAX_EMBEDS:
        warnings.append(f"Seuls les {MAX_EMBEDS} premiers cadres sont gardés.")

    embeds = [_clean_embed(embed) for embed in raw_embeds[:MAX_EMBEDS] if isinstance(embed, dict)]

    for embed in embeds:
        for key in ("image", "thumbnail"):
            url = (embed.get(key) or {}).get("url") or ""

            if url.startswith("attachment://"):
                embed.pop(key, None)
                warnings.append(
                    "Une image jointe au fichier ne peut pas être importée : "
                    "ajoute-la avec 🖼️ Images."
                )

    buttons: list[dict[str, Any]] = []
    skipped = 0

    for row in data.get("components") or []:
        if not isinstance(row, dict):
            continue

        for component in row.get("components") or []:
            if not isinstance(component, dict) or component.get("type") != 2:
                continue

            if component.get("style") == 5 and component.get("url"):
                button: dict[str, Any] = {
                    "label": str(component.get("label") or "​")[:MAX_BUTTON_LABEL],
                    "url": component["url"],
                }
                emoji = _emoji_text(component.get("emoji"))

                if emoji:
                    button["emoji"] = emoji

                buttons.append(button)
            else:
                skipped += 1

    if skipped:
        warnings.append(
            f"{skipped} bouton(s) d'action ignoré(s) : seuls les boutons liens sont gérés."
        )

    imported = {"content": content, "embeds": embeds, "buttons": buttons[:MAX_BUTTONS]}

    if is_empty({**imported, "embeds": embeds}):
        raise AnnouncementError("Le message importé est vide.")

    return imported, list(dict.fromkeys(warnings))


def export_message(draft: dict[str, Any], uploads: dict[int, str] | None = None) -> str:
    """JSON à coller dans l'éditeur JSON de Discohook."""
    embeds = render_embeds(
        draft,
        uploads=uploads or {},
        now=datetime.now().astimezone(),
    )
    data: dict[str, Any] = {
        "content": message_content(draft) or None,
        "embeds": embeds,
        "attachments": [],
    }

    if draft.get("buttons"):
        rows = []

        for start in range(0, len(draft["buttons"]), 5):
            row = []

            for button in draft["buttons"][start:start + 5]:
                component: dict[str, Any] = {
                    "type": 2,
                    "style": 5,
                    "label": button["label"],
                    "url": button["url"],
                }

                if button.get("emoji"):
                    component["emoji"] = _export_emoji(button["emoji"])

                row.append(component)

            rows.append({"type": 1, "components": row})

        data["components"] = rows

    return json.dumps(data, ensure_ascii=False, indent=2)


def _export_emoji(text: str) -> dict[str, Any]:
    match = re.match(r"^<(a?):(\w+):(\d+)>$", text)

    if match:
        return {"name": match[2], "id": match[3], "animated": bool(match[1])}

    return {"name": text}


def from_discord_message(
    content: str,
    embeds: list[dict[str, Any]],
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconstruit un brouillon à partir d'un message déjà publié."""
    text = json.dumps({"content": content, "embeds": embeds, "components": components})

    try:
        imported, _ = import_message(text)
    except AnnouncementError:
        imported = {"content": content, "embeds": [], "buttons": []}

    mention = "none"
    role_id = None
    body = imported["content"]
    first, _, rest = body.partition("\n")

    if first.strip() == "@everyone":
        mention, body = "everyone", rest
    elif first.strip() == "@here":
        mention, body = "here", rest
    elif re.fullmatch(r"<@&\d+>", first.strip()):
        mention, role_id, body = "role", int(first.strip()[3:-1]), rest

    for embed in imported["embeds"]:
        # Une date de publication devient « date de la modification ».
        if embed.get("timestamp"):
            embed["timestamp"] = True

    return normalize_draft(
        {
            "content": body,
            "embeds": imported["embeds"],
            "buttons": imported["buttons"],
            "mention": mention,
            "role_id": role_id,
        }
    )


def summary_title(draft: dict[str, Any]) -> str:
    """Petit nom lisible pour les listes (historique, programmées)."""
    for embed in draft.get("embeds", []):
        if embed.get("title"):
            return embed["title"][:80]

    for embed in draft.get("embeds", []):
        if embed.get("description"):
            return embed["description"].split("\n", 1)[0][:80]

    text = draft.get("content", "").strip()

    return text.split("\n", 1)[0][:80] if text else "Annonce sans titre"
