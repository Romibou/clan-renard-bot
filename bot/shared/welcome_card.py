"""
Carte de bienvenue / de départ (1024 × 500), dans l'esprit de Koya :
fond personnalisable assombri, avatar rond avec bordure, grand titre,
sous-titre coloré (le pseudo) et une ligne de texte.

Trois dispositions : « centre » (avatar en haut, texte dessous),
« gauche » (avatar à gauche) et « droite » (avatar à droite).
"""

from __future__ import annotations

import io
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

WIDTH, HEIGHT = 1024, 500
LAYOUTS = ("centre", "gauche", "droite")

# Effet derrière les textes : ombre douce (comme Koya), contour net,
# les deux, ou rien.
TEXT_EFFECTS = ("ombre", "contour", "les deux", "aucun")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Polices épaisses d'abord (Roboto Black est installée dans l'image Docker).
HEAVY_FONTS = (
    "Roboto-Black.ttf",
    "NotoSans-Black.ttf",
    "NotoSans-ExtraBold.ttf",
    "Roboto-Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
    "arialbd.ttf",
)
BOLD_FONTS = (
    "Roboto-Bold.ttf",
    "NotoSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
    "arialbd.ttf",
)

# Polices au choix : (fichiers du titre, fichiers du texte), essayés dans
# l'ordre. Poppins est fournie dans assets/fonts (licence OFL).
FONTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "roboto": (HEAVY_FONTS, BOLD_FONTS),
    "poppins": (("Poppins-ExtraBold.ttf", *HEAVY_FONTS), ("Poppins-Bold.ttf", *BOLD_FONTS)),
}
FONT_NAMES = {"roboto": "Roboto", "poppins": "Poppins"}


@lru_cache(maxsize=1)
def _font_index() -> dict[str, str]:
    """Polices disponibles : celles du système Linux et celles du dépôt."""
    index: dict[str, str] = {}

    for root in ("/usr/share/fonts", str(PROJECT_ROOT / "assets" / "fonts")):
        if not os.path.isdir(root):
            continue

        for folder, _, files in os.walk(root):
            for name in files:
                if name.lower().endswith((".ttf", ".otf")):
                    index.setdefault(name, os.path.join(folder, name))

    return index


@lru_cache(maxsize=64)
def load_font(
    size: int, heavy: bool = True, family: str = "roboto"
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    index = _font_index()
    heavy_files, bold_files = FONTS.get(family, FONTS["roboto"])

    for name in heavy_files if heavy else bold_files:
        path = index.get(name, name)

        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue

    fallback = index.get("NotoSans-Regular.ttf")

    if fallback:
        return ImageFont.truetype(fallback, size)

    return ImageFont.load_default(size)


def parse_hex(color: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    text = (color or "").strip().lstrip("#")

    if len(text) == 3:
        text = "".join(char * 2 for char in text)

    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return default


def default_background() -> Image.Image:
    """Dégradé « coucher de soleil renard » quand aucun fond n'est choisi."""
    top = (38, 24, 70)
    bottom = (242, 120, 60)
    gradient = Image.new("RGB", (1, HEIGHT))

    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        gradient.putpixel(
            (0, y),
            tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)),
        )

    return gradient.resize((WIDTH, HEIGHT))


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    size: int,
    *,
    heavy: bool = True,
    minimum: int = 14,
    family: str = "roboto",
) -> ImageFont.ImageFont:
    while size > minimum:
        font = load_font(size, heavy, family)

        if draw.textlength(text, font=font) <= max_width:
            return font

        size -= 2

    return load_font(minimum, heavy, family)


def circle_avatar(avatar: Image.Image, diameter: int, border: int, border_color: tuple[int, int, int]) -> Image.Image:
    total = diameter + border * 2
    scale = 4  # dessin en grand puis réduit : bords lisses
    canvas = Image.new("RGBA", (total * scale, total * scale), (0, 0, 0, 0))
    ring = ImageDraw.Draw(canvas)
    ring.ellipse((0, 0, total * scale - 1, total * scale - 1), fill=(*border_color, 255))

    picture = ImageOps.fit(avatar.convert("RGBA"), (diameter * scale, diameter * scale), Image.LANCZOS)
    mask = Image.new("L", picture.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, picture.size[0] - 1, picture.size[1] - 1), fill=255)
    canvas.paste(picture, (border * scale, border * scale), mask)

    return canvas.resize((total, total), Image.LANCZOS)


class TextStyle:
    """Effet appliqué aux textes de la carte (ombre et/ou contour)."""

    def __init__(
        self,
        effect: str = "les deux",
        color: tuple[int, int, int] = (20, 16, 30),
        opacity: int = 70,
        blur: int = 5,
        offset: int = 4,
    ) -> None:
        self.effect = effect if effect in TEXT_EFFECTS else "ombre"
        self.color = color
        self.opacity = max(0, min(100, int(opacity)))
        self.blur = max(0, min(20, int(blur)))
        self.offset = max(0, min(20, int(offset)))


def draw_text(
    image: Image.Image,
    position: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    *,
    anchor: str,
    style: TextStyle | None = None,
) -> None:
    """Texte avec ombre douce et/ou contour, lisible sur n'importe quel fond."""
    style = style or TextStyle()
    outline = style.effect in ("contour", "les deux")

    if style.effect in ("ombre", "les deux") and style.opacity:
        alpha = style.opacity * 255 // 100
        # Ombre seule : elle épouse les lettres (comme Koya). Avec le
        # contour, elle est plus large pour ressortir derrière lui.
        spread = 4 if outline else 1
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(
            (position[0] + style.offset * 0.6, position[1] + style.offset),
            text,
            font=font,
            fill=(*style.color, alpha),
            anchor=anchor,
            stroke_width=spread,
            stroke_fill=(*style.color, alpha),
        )

        if style.blur:
            layer = layer.filter(ImageFilter.GaussianBlur(style.blur))

        image.alpha_composite(layer)

    ImageDraw.Draw(image).text(
        position,
        text,
        font=font,
        fill=(*fill, 255),
        anchor=anchor,
        stroke_width=2 if outline else 0,
        stroke_fill=(*style.color, 255),
    )


def render_welcome_card(
    *,
    avatar_bytes: bytes | None,
    title: str,
    subtitle: str,
    text: str,
    background_bytes: bytes | None = None,
    layout: str = "centre",
    overlay: int = 35,
    title_color: str = "#FFFFFF",
    subtitle_color: str = "#FF9AD5",
    text_color: str = "#FFFFFF",
    border_color: str = "#FFFFFF",
    text_effect: str = "les deux",
    shadow_color: str = "#14101E",
    shadow_opacity: int = 70,
    shadow_blur: int = 5,
    shadow_offset: int = 4,
    font: str = "roboto",
) -> bytes:
    """Retourne la carte en PNG."""
    if background_bytes:
        try:
            background = Image.open(io.BytesIO(background_bytes))
            background = ImageOps.fit(background.convert("RGB"), (WIDTH, HEIGHT), Image.LANCZOS)
        except Exception:
            background = default_background()
    else:
        background = default_background()

    image = background.convert("RGBA")
    alpha = max(0, min(90, int(overlay))) * 255 // 100

    if alpha:
        image.alpha_composite(Image.new("RGBA", image.size, (0, 0, 0, alpha)))

    try:
        avatar = Image.open(io.BytesIO(avatar_bytes)) if avatar_bytes else None
    except Exception:
        avatar = None

    if avatar is None:
        avatar = Image.new("RGB", (256, 256), (88, 101, 242))

    white = (255, 255, 255)
    title_rgb = parse_hex(title_color, white)
    subtitle_rgb = parse_hex(subtitle_color, (255, 154, 213))
    text_rgb = parse_hex(text_color, white)
    border_rgb = parse_hex(border_color, white)
    style = TextStyle(
        text_effect, parse_hex(shadow_color, (20, 16, 30)), shadow_opacity, shadow_blur, shadow_offset
    )
    family = font if font in FONTS else "roboto"
    draw = ImageDraw.Draw(image)
    layout = layout if layout in LAYOUTS else "centre"

    title = title.strip()
    subtitle = subtitle.strip()
    text = text.strip()

    if layout == "centre":
        diameter, border = 230, 8
        disc = circle_avatar(avatar, diameter, border, border_rgb)
        image.alpha_composite(disc, ((WIDTH - disc.width) // 2, 40))
        center = WIDTH / 2
        y = 40 + disc.height + 18

        if title:
            font = fit_text(draw, title.upper(), 900, 92, family=family)
            draw_text(image, (center, y), title.upper(), font, title_rgb, anchor="mt", style=style)
            y += font.size + 10

        if subtitle:
            font = fit_text(draw, subtitle.upper(), 880, 44, family=family)
            draw_text(image, (center, y), subtitle.upper(), font, subtitle_rgb, anchor="mt", style=style)
            y += font.size + 12

        if text:
            font = fit_text(draw, text.upper(), 900, 30, heavy=False, family=family)
            draw_text(image, (center, min(y, HEIGHT - 40)), text.upper(), font, text_rgb, anchor="mt", style=style)
    else:
        diameter, border = 280, 9
        disc = circle_avatar(avatar, diameter, border, border_rgb)
        disc_x = 60 if layout == "gauche" else WIDTH - 60 - disc.width
        image.alpha_composite(disc, (disc_x, (HEIGHT - disc.height) // 2))

        text_left = disc_x + disc.width + 50 if layout == "gauche" else 60
        text_right = WIDTH - 60 if layout == "gauche" else disc_x - 50
        width = text_right - text_left
        anchor_x = text_left if layout == "gauche" else text_right
        anchor = "l" if layout == "gauche" else "r"

        lines = []

        if title:
            lines.append((title.upper(), fit_text(draw, title.upper(), width, 84, family=family), title_rgb, 12))
        if subtitle:
            lines.append((subtitle.upper(), fit_text(draw, subtitle.upper(), width, 42, family=family), subtitle_rgb, 14))
        if text:
            lines.append((text.upper(), fit_text(draw, text.upper(), width, 28, heavy=False, family=family), text_rgb, 0))

        total = sum(font.size + gap for _, font, _, gap in lines)
        y = (HEIGHT - total) / 2

        for content, font, color, gap in lines:
            draw_text(image, (anchor_x, y), content, font, color, anchor=f"{anchor}t", style=style)
            y += font.size + gap

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", compress_level=3)
    return output.getvalue()
