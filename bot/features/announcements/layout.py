"""
Formats « grand » et « pleine largeur » des annonces : le nouveau
type de message Discord (« Components V2 »).

- grand : chaque cadre devient un bloc (Container) avec la barre de
  couleur, un peu plus large qu'un cadre classique ;
- pleine largeur : un message texte normal (plain_text), car même
  sans bloc, les messages « Components V2 » ont une largeur limitée.

Différences avec le format classique :
- l'en-tête et le pied de page deviennent du petit texte gris ;
- les sections s'empilent (pas de colonnes) ;
- les boutons liens sont dans le dernier bloc ;
- Discord limite le texte total à 4 000 caractères et le message à
  40 éléments.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import discord

from bot.features.announcements.model import UPLOAD_PREFIX, message_content

MAX_LAYOUT_TEXT = 4000
MAX_LAYOUT_COMPONENTS = 40


def _image_url(embed: dict[str, Any], key: str, uploads: dict[int, str]) -> str | None:
    url = (embed.get(key) or {}).get("url") or ""

    if url.startswith(UPLOAD_PREFIX):
        try:
            name = uploads.get(int(url[len(UPLOAD_PREFIX):]))
        except ValueError:
            name = None

        return f"attachment://{name}" if name else None

    return url or None


def _timestamp(embed: dict[str, Any], now: datetime | None) -> int | None:
    value = embed.get("timestamp")

    if value is True and now is not None:
        return int(now.timestamp())

    if isinstance(value, str) and value:
        try:
            return int(datetime.fromisoformat(value).timestamp())
        except ValueError:
            return None

    return None


def layout_texts(
    draft: dict[str, Any],
    *,
    now: datetime | None = None,
    placeholder: str | None = None,
) -> list[dict[str, Any]]:
    """
    Découpe chaque cadre en morceaux de texte (sans Discord) :
    [{"header": str, "fields": str, "footer": str, "color": int|None,
      "image": dict, "thumbnail": dict}, ...]
    """
    blocks = []

    for embed in draft.get("embeds", []):
        has_body = bool(
            embed.get("title")
            or embed.get("description")
            or embed.get("fields")
            or (embed.get("image") or {}).get("url")
            or (embed.get("thumbnail") or {}).get("url")
        )

        if not has_body and not placeholder:
            continue

        header_lines = []
        author = (embed.get("author") or {}).get("name")

        if author:
            header_lines.append(f"-# {author}")

        title = embed.get("title")

        if title:
            header_lines.append(f"## [{title}]({embed['url']})" if embed.get("url") else f"## {title}")

        description = embed.get("description") or ("" if has_body else placeholder or "")

        if description:
            header_lines.append(description)

        fields = "\n\n".join(
            f"**{field['name']}**\n{field['value']}".replace("**​**\n", "").strip()
            for field in embed.get("fields") or []
        )

        footer_parts = []
        footer = (embed.get("footer") or {}).get("text")

        if footer:
            footer_parts.append(footer)

        stamp = _timestamp(embed, now)

        if stamp is not None:
            footer_parts.append(f"<t:{stamp}:f>")

        blocks.append(
            {
                "header": "\n".join(header_lines),
                "fields": fields,
                "footer": f"-# {' · '.join(footer_parts)}" if footer_parts else "",
                "color": embed.get("color"),
                "image": embed.get("image") or {},
                "thumbnail": embed.get("thumbnail") or {},
            }
        )

    return blocks


def plain_text(
    draft: dict[str, Any],
    *,
    now: datetime | None = None,
    placeholder: str | None = None,
) -> str:
    """
    Format pleine largeur : tout devient un message texte normal
    (titre en gros, en-tête et pied de page en petit texte gris).
    Les images envoyées sont jointes au message ; les liens d'images
    sont ajoutés tels quels (Discord en affiche l'aperçu).
    """
    parts = [message_content(draft)]

    for block, embed in zip(
        layout_texts(draft, now=now, placeholder=placeholder),
        [e for e in draft.get("embeds", []) if placeholder or _has_body(e)],
    ):
        lines = [block["header"], block["fields"]]

        for key in ("thumbnail", "image"):
            url = (embed.get(key) or {}).get("url") or ""

            if url.startswith("http"):
                lines.append(url)

        lines.append(block["footer"])
        parts.append("\n\n".join(line for line in lines if line))

    return "\n\n".join(part for part in parts if part)


def layout_problems(draft: dict[str, Any]) -> list[str]:
    """Limites propres au format grand."""
    found = []
    blocks = layout_texts(draft, now=datetime.now())
    text = len(message_content(draft)) + sum(
        len(block["header"]) + len(block["fields"]) + len(block["footer"]) for block in blocks
    )

    if text > MAX_LAYOUT_TEXT:
        found.append(
            f"En format grand, Discord limite le texte total à {MAX_LAYOUT_TEXT} caractères "
            f"(ici {text}). Raccourcis, ou repasse en format classique."
        )

    if count_components(draft) > MAX_LAYOUT_COMPONENTS:
        found.append("Trop d'éléments pour le format grand : retire un cadre ou des boutons.")

    return found


def count_components(draft: dict[str, Any]) -> int:
    total = 1 if message_content(draft) else 0
    framed = draft.get("format") != "text"

    for block in layout_texts(draft, now=datetime.now()):
        total += 1 if framed else 1  # le bloc, ou le séparateur entre cadres
        total += 1 if block["header"] or block["fields"] else 0
        total += 1 if block["fields"] and block["header"] else 0
        total += 2 if block["thumbnail"].get("url") else 0  # section + miniature
        total += 2 if block["image"].get("url") else 0  # galerie + image
        total += 2 if block["footer"] else 0  # séparateur + texte

    buttons = len(draft.get("buttons") or [])
    total += buttons + (buttons + 4) // 5

    return total


def build_layout(
    draft: dict[str, Any],
    *,
    uploads: dict[int, str] | None = None,
    now: datetime | None = None,
    placeholder: str | None = None,
) -> discord.ui.LayoutView:
    uploads = uploads or {}
    framed = draft.get("format") != "text"
    view = discord.ui.LayoutView(timeout=None)
    top = message_content(draft)

    if top:
        view.add_item(discord.ui.TextDisplay(top))

    containers: list[discord.ui.Container] = []

    for block, embed in zip(
        layout_texts(draft, now=now, placeholder=placeholder),
        [e for e in draft.get("embeds", []) if placeholder or _has_body(e)],
    ):
        # Pleine largeur : les éléments vont directement dans le message,
        # avec un séparateur entre deux cadres.
        if not framed and len(view.children) > (1 if top else 0):
            view.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))

        container = discord.ui.Container(accent_colour=block["color"]) if framed else view
        thumbnail = _image_url(embed, "thumbnail", uploads)
        header = block["header"]

        if header and thumbnail:
            container.add_item(
                discord.ui.Section(header, accessory=discord.ui.Thumbnail(thumbnail))
            )
        elif header:
            container.add_item(discord.ui.TextDisplay(header))
        elif thumbnail:
            container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(thumbnail)))

        if block["fields"]:
            container.add_item(discord.ui.TextDisplay(block["fields"]))

        image = _image_url(embed, "image", uploads)

        if image:
            container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(image)))

        if block["footer"]:
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(block["footer"]))

        if not framed:
            continue

        if not container.children:
            continue

        containers.append(container)
        view.add_item(container)

    buttons = draft.get("buttons") or []

    for start in range(0, len(buttons), 5):
        row = discord.ui.ActionRow()

        for button in buttons[start:start + 5]:
            label = button.get("label")
            row.add_item(
                discord.ui.Button(
                    label=None if label in (None, "", "​") else label,
                    url=button["url"],
                    emoji=button.get("emoji"),
                )
            )

        (containers[-1] if containers else view).add_item(row)

    return view


def _has_body(embed: dict[str, Any]) -> bool:
    return bool(
        embed.get("title")
        or embed.get("description")
        or embed.get("fields")
        or (embed.get("image") or {}).get("url")
        or (embed.get("thumbnail") or {}).get("url")
    )
