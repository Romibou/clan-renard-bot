# ============================================================
# CLAN RENARD — GÉNÉRATEUR D'IMAGE DU CALENDRIER (RAPIDE)
#
# Fichier généré automatiquement par installer_nouveau_visuel.py
# Ne redessine plus le décor à chaque appel : le fond et les
# cadeaux sont chargés une seule fois, puis réutilisés.
# ============================================================

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------
# Chemins (ce fichier vit dans bot/features/advent/)
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[3]

ASSETS_DIRECTORY = ROOT / "assets" / "advent"
TEMPLATE_PATH = ASSETS_DIRECTORY / "backgrounds" / "calendar_template.png"

GIFTS_DIRECTORY = ASSETS_DIRECTORY / "gifts"
DECORATIONS_DIRECTORY = ASSETS_DIRECTORY / "decorations"

GIFT_PATHS = {
    "closed": GIFTS_DIRECTORY / "gift_closed.png",
    "available": GIFTS_DIRECTORY / "gift_available.png",
    "opened": GIFTS_DIRECTORY / "gift_opened.png",
    "day_24": GIFTS_DIRECTORY / "gift_day_24.png",
}

ICON_PATHS = {
    "lock": DECORATIONS_DIRECTORY / "lock.png",
    "check": DECORATIONS_DIRECTORY / "check.png",
    "missed": DECORATIONS_DIRECTORY / "missed_cross.png",
    "sparkle": DECORATIONS_DIRECTORY / "sparkle.png",
}

COLORS = {
    "pink_light": (248, 211, 228, 255),
    "pink_white": (255, 245, 250, 255),
    "muted": (194, 164, 187, 255),
    "card": (50, 27, 57, 255),
    "card_border": (111, 63, 91, 255),
}

_FONT_CACHE: dict[tuple[int, bool], ImageFont.ImageFont] = {}


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    key = (size, bold)

    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf")
        if bold
        else Path("C:/Windows/Fonts/arial.ttf"),
    ]

    for candidate in candidates:
        if candidate.exists():
            try:
                loaded = ImageFont.truetype(str(candidate), size=size)
                _FONT_CACHE[key] = loaded
                return loaded
            except OSError:
                continue

    try:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        loaded = ImageFont.truetype(name, size=size)
    except OSError:
        loaded = ImageFont.load_default()

    _FONT_CACHE[key] = loaded
    return loaded


def _centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    selected_font: ImageFont.ImageFont,
    fill: tuple[int, ...],
) -> None:
    bounds = draw.textbbox((0, 0), text, font=selected_font)

    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]

    left, top, right, bottom = box

    x = left + (right - left - text_width) / 2
    y = top + (bottom - top - text_height) / 2 - bounds[1]

    draw.text((round(x), round(y)), text, font=selected_font, fill=fill)


class AdventCalendarRenderer:
    """
    Rendu du calendrier de l'Avent.

    Le fond et les cadeaux sont chargés UNE SEULE FOIS (au premier
    rendu), puis réutilisés en mémoire. Chaque rendu ne dessine que
    ce qui change : numéros, états des cases, pseudo, progression.

    Un petit cache mémoire évite de regénérer une image identique
    à la précédente pour le même utilisateur.
    """

    _template: Image.Image | None = None
    _gift_thumbnails: dict[str, Image.Image] = {}
    _icon_thumbnails: dict[str, Image.Image] = {}

    _cache: dict[str, bytes] = {}
    _cache_order: list[str] = []
    _cache_limit = 40

    GRID_COLUMNS = 6
    GRID_ROWS = 4
    GRID_LEFT = 85
    GRID_RIGHT = 1315
    GRID_TOP = 178
    GRID_BOTTOM = 780
    CELL_GAP = 16

    # ------------------------------------------------------------
    # Chargement paresseux, une seule fois par process.
    # ------------------------------------------------------------

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._template is not None:
            return

        if not TEMPLATE_PATH.exists():
            raise FileNotFoundError(
                f"Fond introuvable : {TEMPLATE_PATH}. "
                "Lance d'abord installer_nouveau_visuel.py."
            )

        with Image.open(TEMPLATE_PATH) as source:
            cls._template = source.convert("RGBA")

        gift_size = cls._cell_gift_size()

        for name, path in GIFT_PATHS.items():
            with Image.open(path) as source:
                thumbnail = source.convert("RGBA")
            thumbnail.thumbnail(gift_size, Image.Resampling.LANCZOS)
            cls._gift_thumbnails[name] = thumbnail

        icon_size = (44, 44)

        for name, path in ICON_PATHS.items():
            with Image.open(path) as source:
                thumbnail = source.convert("RGBA")
            thumbnail.thumbnail(icon_size, Image.Resampling.LANCZOS)
            cls._icon_thumbnails[name] = thumbnail

    @classmethod
    def reload_assets(cls) -> None:
        """Force un rechargement (utile après un changement d'assets)."""
        cls._template = None
        cls._gift_thumbnails = {}
        cls._icon_thumbnails = {}
        cls._cache = {}
        cls._cache_order = []
        cls._ensure_loaded()

    # ------------------------------------------------------------
    # Géométrie de la grille (24 cases, 6 colonnes x 4 lignes).
    # ------------------------------------------------------------

    @classmethod
    def _cell_geometry(cls) -> tuple[float, float]:
        usable_width = cls.GRID_RIGHT - cls.GRID_LEFT
        usable_height = cls.GRID_BOTTOM - cls.GRID_TOP

        cell_width = (
            usable_width - cls.CELL_GAP * (cls.GRID_COLUMNS - 1)
        ) / cls.GRID_COLUMNS
        cell_height = (
            usable_height - cls.CELL_GAP * (cls.GRID_ROWS - 1)
        ) / cls.GRID_ROWS

        return cell_width, cell_height

    @classmethod
    def _cell_gift_size(cls) -> tuple[int, int]:
        cell_width, cell_height = cls._cell_geometry()
        side = round(min(cell_width, cell_height) * 0.62)
        return (side, side)

    @classmethod
    def _cell_box(cls, day_index: int) -> tuple[int, int, int, int]:
        column = day_index % cls.GRID_COLUMNS
        row = day_index // cls.GRID_COLUMNS

        cell_width, cell_height = cls._cell_geometry()

        left = cls.GRID_LEFT + column * (cell_width + cls.CELL_GAP)
        top = cls.GRID_TOP + row * (cell_height + cls.CELL_GAP)

        return (
            round(left),
            round(top),
            round(left + cell_width),
            round(top + cell_height),
        )

    # ------------------------------------------------------------
    # Cache.
    # ------------------------------------------------------------

    @classmethod
    def _cache_key(
        cls,
        *,
        username: str,
        year: int,
        points: int,
        day_states: dict[int, str],
    ) -> str:
        states = "|".join(
            f"{day}:{day_states.get(day, 'closed')}" for day in range(1, 25)
        )
        return f"{username}::{year}::{points}::{states}"

    @classmethod
    def _store_in_cache(cls, key: str, payload: bytes) -> None:
        cls._cache[key] = payload
        cls._cache_order.append(key)

        while len(cls._cache_order) > cls._cache_limit:
            oldest_key = cls._cache_order.pop(0)
            cls._cache.pop(oldest_key, None)

    # ------------------------------------------------------------
    # Dessin d'une case.
    # ------------------------------------------------------------

    @classmethod
    def _gift_key_for(cls, day: int, state: str) -> str:
        if day == 24 and state != "opened":
            return "day_24"
        if state in ("opened", "available"):
            return state
        return "closed"

    @classmethod
    def _draw_cell(
        cls,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        day: int,
        state: str,
        box: tuple[int, int, int, int],
    ) -> None:
        left, top, right, bottom = box

        draw.rounded_rectangle(
            box,
            radius=14,
            fill=COLORS["card"],
            outline=COLORS["card_border"],
            width=2,
        )

        gift_thumbnail = cls._gift_thumbnails[cls._gift_key_for(day, state)]

        gift_x = left + (right - left - gift_thumbnail.width) // 2
        gift_y = top + 10

        image.alpha_composite(gift_thumbnail, (gift_x, gift_y))

        draw.text(
            (left + 10, top + 6),
            str(day),
            font=_font(19, bold=True),
            fill=COLORS["pink_white"],
            stroke_width=2,
            stroke_fill=(30, 14, 34, 220),
        )

        icon_name = None
        if state == "opened":
            icon_name = "check"
        elif state == "missed":
            icon_name = "missed"
        elif state == "available":
            icon_name = "sparkle"
        elif state == "locked":
            icon_name = "lock"

        if icon_name is not None:
            icon = cls._icon_thumbnails[icon_name]
            icon_x = right - icon.width - 4
            icon_y = bottom - icon.height - 4
            image.alpha_composite(icon, (icon_x, icon_y))

    # ------------------------------------------------------------
    # Rendu complet.
    # ------------------------------------------------------------

    @classmethod
    def render(
        cls,
        *,
        username: str,
        year: int,
        points: int,
        day_states: dict[int, str],
    ) -> bytes:
        """
        day_states : dict {jour: état}, état parmi
        "locked", "available", "opened", "missed".
        Les jours absents du dict sont traités comme "locked".

        Retourne les octets PNG prêts à envoyer sur Discord
        (discord.File(BytesIO(...), filename="avent.png")).
        """
        cls._ensure_loaded()

        opened_count = sum(
            1 for state in day_states.values() if state == "opened"
        )

        cache_key = cls._cache_key(
            username=username,
            year=year,
            points=points,
            day_states=day_states,
        )

        cached_payload = cls._cache.get(cache_key)
        if cached_payload is not None:
            return cached_payload

        image = cls._template.copy()
        draw = ImageDraw.Draw(image)

        _centered_text(
            draw,
            (1090, 78, 1295, 106),
            f"ÉDITION {year}",
            _font(15, bold=True),
            COLORS["pink_light"],
        )

        _centered_text(
            draw,
            (1090, 108, 1295, 134),
            f"{opened_count}/24 · {points} pts",
            _font(13),
            COLORS["muted"],
        )

        _centered_text(
            draw,
            (460, 115, 1040, 153),
            f"Calendrier de {username}",
            _font(18),
            COLORS["muted"],
        )

        for day in range(1, 25):
            state = day_states.get(day, "locked")
            box = cls._cell_box(day - 1)
            cls._draw_cell(image, draw, day, state, box)

        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True, compress_level=4)
        payload = buffer.getvalue()

        cls._store_in_cache(cache_key, payload)

        return payload

# ============================================================
# COMPATIBILITÉ AVEC L'ANCIEN SYSTÈME DU BOT
# ============================================================

import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class RenderedCalendar:
    buffer: BytesIO
    filename: str


class AdventImageGenerator:
    """
    Adaptateur assurant la compatibilité entre l'ancien système
    du bot et le nouveau moteur rapide AdventCalendarRenderer.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or ROOT

    async def render(
        self,
        state,
        username: str,
        *,
        avatar_bytes: bytes | None = None,
        preview: bool = False,
    ) -> RenderedCalendar:
        # avatar_bytes et preview sont conservés pour rester
        # compatibles avec les commandes existantes.
        del avatar_bytes, preview

        day_states: dict[int, str] = {}

        for day in range(1, 25):
            if day in state.opened_days:
                day_states[day] = "opened"
            elif day in state.available_days:
                day_states[day] = "available"
            elif day in state.missed_days:
                day_states[day] = "missed"
            else:
                day_states[day] = "locked"

        payload = await asyncio.to_thread(
            AdventCalendarRenderer.render,
            username=username,
            year=state.campaign.year,
            points=state.total_points,
            day_states=day_states,
        )

        safe_username = "".join(
            character if character.isalnum() else "-"
            for character in username
        ).strip("-")

        if not safe_username:
            safe_username = "membre"

        filename = f"calendrier-{safe_username[:30]}.png"

        return RenderedCalendar(
            buffer=BytesIO(payload),
            filename=filename,
        )
