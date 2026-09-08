# ============================================================
# CLAN RENARD — INSTALLATEUR DU NOUVEAU VISUEL
# PAQUET 1/3
#
# À placer dans :
# clan-renard-bot/installer_nouveau_visuel.py
#
# Ne pas exécuter avant d'avoir collé les 3 paquets.
# ============================================================

from __future__ import annotations

import math
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ============================================================
# CHEMINS DU PROJET
# ============================================================

ROOT = Path(__file__).resolve().parent

BOT_DIRECTORY = ROOT / "bot" / "features" / "advent"

ASSETS_DIRECTORY = ROOT / "assets" / "advent"
BACKGROUND_DIRECTORY = ASSETS_DIRECTORY / "backgrounds"
GIFTS_DIRECTORY = ASSETS_DIRECTORY / "gifts"
DECORATIONS_DIRECTORY = ASSETS_DIRECTORY / "decorations"

BRANDING_DIRECTORY = ROOT / "assets" / "branding"
GENERATED_DIRECTORY = ROOT / "generated"

BACKUP_DIRECTORY = (
    ROOT
    / "backups"
    / f"ancien-visuel-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
)

TEMPLATE_PATH = BACKGROUND_DIRECTORY / "calendar_template.png"
LOGO_PATH = BRANDING_DIRECTORY / "clan_renard_logo.png"


# ============================================================
# DIMENSIONS ET PALETTE
# ============================================================

WIDTH = 1400
HEIGHT = 900

COLORS = {
    "background_top": (24, 13, 31, 255),
    "background_bottom": (43, 21, 49, 255),
    "panel": (36, 18, 43, 238),
    "panel_border": (133, 75, 108, 210),
    "panel_border_light": (232, 151, 187, 75),
    "card": (50, 27, 57, 255),
    "card_border": (111, 63, 91, 255),
    "pink": (231, 149, 184, 255),
    "pink_light": (248, 211, 228, 255),
    "pink_white": (255, 245, 250, 255),
    "muted": (194, 164, 187, 255),
    "plum": (79, 38, 76, 255),
    "gold": (230, 181, 141, 255),
    "green": (121, 201, 158, 255),
    "red": (215, 103, 131, 255),
    "shadow": (4, 1, 8, 120),
}


# ============================================================
# OUTILS
# ============================================================

def ensure_directories() -> None:
    for directory in (
        BOT_DIRECTORY,
        BACKGROUND_DIRECTORY,
        GIFTS_DIRECTORY,
        DECORATIONS_DIRECTORY,
        BRANDING_DIRECTORY,
        GENERATED_DIRECTORY,
        BACKUP_DIRECTORY,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def find_font(*, bold: bool = False) -> Path | None:
    custom_name = "title.ttf" if bold else "regular.ttf"

    candidates = [
        ASSETS_DIRECTORY / "fonts" / custom_name,
    ]

    if bold:
        candidates.extend(
            [
                Path(
                    "/usr/share/fonts/truetype/dejavu/"
                    "DejaVuSans-Bold.ttf"
                ),
                Path("C:/Windows/Fonts/georgiab.ttf"),
                Path("C:/Windows/Fonts/arialbd.ttf"),
                Path(
                    "/System/Library/Fonts/Supplemental/"
                    "Georgia Bold.ttf"
                ),
            ]
        )
    else:
        candidates.extend(
            [
                Path(
                    "/usr/share/fonts/truetype/dejavu/"
                    "DejaVuSans.ttf"
                ),
                Path("C:/Windows/Fonts/arial.ttf"),
                Path(
                    "/System/Library/Fonts/Supplemental/"
                    "Arial.ttf"
                ),
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    path = find_font(bold=bold)

    if path is not None:
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            pass

    try:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        return ImageFont.truetype(name, size=size)
    except OSError:
        return ImageFont.load_default()


def centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    selected_font: ImageFont.ImageFont,
    fill: tuple[int, ...],
    *,
    stroke_width: int = 0,
    stroke_fill: tuple[int, ...] | None = None,
) -> None:
    bounds = draw.textbbox(
        (0, 0),
        text,
        font=selected_font,
        stroke_width=stroke_width,
    )

    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]

    left, top, right, bottom = box

    x = left + (right - left - text_width) / 2
    y = top + (bottom - top - text_height) / 2 - bounds[1]

    draw.text(
        (round(x), round(y)),
        text,
        font=selected_font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def create_gradient() -> Image.Image:
    strip = Image.new("RGBA", (1, HEIGHT))
    pixels = strip.load()

    top = COLORS["background_top"]
    bottom = COLORS["background_bottom"]

    for y in range(HEIGHT):
        ratio = y / max(1, HEIGHT - 1)

        pixels[0, y] = tuple(
            round(
                top[index]
                + (bottom[index] - top[index]) * ratio
            )
            for index in range(4)
        )

    return strip.resize(
        (WIDTH, HEIGHT),
        Image.Resampling.BILINEAR,
    )


def add_glow(
    image: Image.Image,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int, int],
) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    x, y = center

    draw.ellipse(
        (
            x - radius,
            y - radius,
            x + radius,
            y + radius,
        ),
        fill=color,
    )

    layer = layer.filter(
        ImageFilter.GaussianBlur(radius // 2)
    )
    image.alpha_composite(layer)


def draw_star(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, ...],
) -> None:
    cx, cy = center
    points: list[tuple[int, int]] = []

    for index in range(8):
        angle = -math.pi / 2 + index * math.pi / 4
        current_radius = radius if index % 2 == 0 else radius // 4

        points.append(
            (
                round(cx + math.cos(angle) * current_radius),
                round(cy + math.sin(angle) * current_radius),
            )
        )

    draw.polygon(points, fill=color)


def draw_snowflake(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, ...],
) -> None:
    cx, cy = center

    for index in range(6):
        angle = index * math.pi / 3

        end_x = cx + math.cos(angle) * radius
        end_y = cy + math.sin(angle) * radius

        draw.line(
            (cx, cy, end_x, end_y),
            fill=color,
            width=2,
        )


def draw_leaf(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    angle: float,
    *,
    length: int = 24,
) -> None:
    cx, cy = center

    dx = math.cos(angle)
    dy = math.sin(angle)

    perpendicular_x = -dy
    perpendicular_y = dx

    tip = (
        round(cx + dx * length),
        round(cy + dy * length),
    )
    left = (
        round(cx + perpendicular_x * 7),
        round(cy + perpendicular_y * 7),
    )
    right = (
        round(cx - perpendicular_x * 7),
        round(cy - perpendicular_y * 7),
    )

    draw.polygon(
        [left, tip, right, (cx, cy)],
        fill=(100, 49, 89, 210),
    )


def draw_flower(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
) -> None:
    cx, cy = center
    petal_radius = max(4, radius // 2)

    for index in range(5):
        angle = -math.pi / 2 + index * 2 * math.pi / 5

        x = cx + math.cos(angle) * radius * 0.72
        y = cy + math.sin(angle) * radius * 0.72

        draw.ellipse(
            (
                round(x - petal_radius),
                round(y - petal_radius),
                round(x + petal_radius),
                round(y + petal_radius),
            ),
            fill=(239, 164, 196, 225),
        )

    center_radius = max(3, radius // 3)

    draw.ellipse(
        (
            cx - center_radius,
            cy - center_radius,
            cx + center_radius,
            cy + center_radius,
        ),
        fill=COLORS["pink_light"],
    )


def draw_branch(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    *,
    mirrored: bool = False,
) -> None:
    draw.line(
        points,
        fill=(134, 66, 106, 220),
        width=5,
        joint="curve",
    )

    for index, point in enumerate(points[1:-1], start=1):
        x, y = point

        if mirrored:
            leaf_angle = -2.4 if index % 2 else 2.7
        else:
            leaf_angle = -0.7 if index % 2 else 0.4

        draw_leaf(
            draw,
            (x, y),
            leaf_angle,
            length=19 if index % 2 else 24,
        )

        if index % 2:
            draw_flower(
                draw,
                (x + (5 if mirrored else -5), y - 3),
                10,
            )


def paste_logo_or_emblem(
    image: Image.Image,
    center: tuple[int, int],
    size: int,
) -> None:
    if LOGO_PATH.exists():
        try:
            with Image.open(LOGO_PATH) as source:
                logo = source.convert("RGBA")
                logo.thumbnail(
                    (size, size),
                    Image.Resampling.LANCZOS,
                )

                image.alpha_composite(
                    logo,
                    (
                        center[0] - logo.width // 2,
                        center[1] - logo.height // 2,
                    ),
                )
                return
        except OSError:
            print(
                "AVERTISSEMENT : le logo existe mais ne peut pas être lu."
            )

    # Emblème minimaliste si aucun vrai logo n'est disponible.
    draw = ImageDraw.Draw(image)
    cx, cy = center
    half = size // 2

    draw.ellipse(
        (
            cx - half,
            cy - half,
            cx + half,
            cy + half,
        ),
        fill=(46, 22, 52, 255),
        outline=COLORS["pink"],
        width=3,
    )

    # Oreilles.
    draw.polygon(
        [
            (cx - 29, cy - 12),
            (cx - 38, cy - 39),
            (cx - 8, cy - 25),
        ],
        fill=COLORS["pink_white"],
    )
    draw.polygon(
        [
            (cx + 29, cy - 12),
            (cx + 38, cy - 39),
            (cx + 8, cy - 25),
        ],
        fill=COLORS["pink_white"],
    )

    # Tête.
    draw.ellipse(
        (
            cx - 31,
            cy - 27,
            cx + 31,
            cy + 30,
        ),
        fill=COLORS["pink_white"],
    )

    # Bas du museau.
    draw.polygon(
        [
            (cx - 29, cy + 2),
            (cx, cy + 35),
            (cx + 29, cy + 2),
            (cx, cy + 12),
        ],
        fill=(255, 255, 255, 255),
    )

    # Yeux et nez.
    draw.ellipse(
        (cx - 17, cy - 4, cx - 11, cy + 2),
        fill=COLORS["plum"],
    )
    draw.ellipse(
        (cx + 11, cy - 4, cx + 17, cy + 2),
        fill=COLORS["plum"],
    )
    draw.ellipse(
        (cx - 5, cy + 13, cx + 5, cy + 21),
        fill=COLORS["plum"],
    )


# ============================================================
# CRÉATION DU TEMPLATE STATIQUE
# ============================================================

def create_calendar_template() -> None:
    image = create_gradient()

    # Deux halos seulement, très discrets.
    add_glow(
        image,
        (170, 100),
        260,
        (211, 95, 149, 24),
    )
    add_glow(
        image,
        (1240, 800),
        300,
        (202, 91, 148, 20),
    )

    # Ombre du panneau principal.
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)

    shadow_draw.rounded_rectangle(
        (40, 47, 1360, 867),
        radius=32,
        fill=COLORS["shadow"],
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(12)
    )
    image.alpha_composite(shadow)

    draw = ImageDraw.Draw(image)

    # Panneau principal : un cadre simple.
    draw.rounded_rectangle(
        (35, 35, 1365, 855),
        radius=32,
        fill=COLORS["panel"],
        outline=COLORS["panel_border"],
        width=2,
    )

    draw.rounded_rectangle(
        (47, 47, 1353, 843),
        radius=25,
        outline=COLORS["panel_border_light"],
        width=1,
    )

    # Séparateur de l'en-tête.
    draw.line(
        (85, 174, 1315, 174),
        fill=(138, 78, 111, 130),
        width=1,
    )

    # Logo et nom de la communauté.
    paste_logo_or_emblem(
        image,
        center=(112, 104),
        size=86,
    )

    draw.text(
        (169, 76),
        "CLAN RENARD",
        font=font(27, bold=True),
        fill=COLORS["pink_white"],
    )

    draw.text(
        (170, 111),
        "Une surprise chaque jour",
        font=font(16),
        fill=COLORS["muted"],
    )

    # Titre centré, avec de l'espace réservé à l'année dynamique.
    centered_text(
        draw,
        (410, 57, 1090, 113),
        "CALENDRIER DE L'AVENT",
        font(39, bold=True),
        COLORS["pink_light"],
    )

    # NOTE : la zone (460,115)-(1040,153) reste vide ici volontairement.
    # C'est image_generator.py qui y écrit "Calendrier de <pseudo>"
    # à chaque rendu — la mettre ici en statique créerait un
    # chevauchement avec le texte dynamique.

    # Zone réservée aux informations dynamiques (édition/progression).
    # Le contenu texte est ajouté par image_generator.py, pas ici,
    # pour éviter tout chevauchement avec le rendu dynamique.
    draw.rounded_rectangle(
        (1080, 68, 1305, 143),
        radius=18,
        fill=(51, 27, 57, 210),
        outline=(122, 70, 100, 150),
        width=1,
    )

    # Décoration limitée à deux angles.
    draw_branch(
        draw,
        [
            (39, 237),
            (65, 213),
            (91, 197),
            (124, 181),
        ],
    )

    draw_branch(
        draw,
        [
            (1361, 742),
            (1338, 772),
            (1306, 798),
            (1268, 823),
        ],
        mirrored=True,
    )

    # Quelques éléments décoratifs fixes seulement.
    for center, radius in (
        ((1259, 197), 12),
        ((1308, 225), 8),
        ((87, 749), 10),
    ):
        draw_snowflake(
            draw,
            center,
            radius,
            (239, 174, 207, 105),
        )

    for center, radius in (
        ((1198, 148), 8),
        ((212, 157), 6),
        ((1314, 690), 7),
        ((82, 694), 6),
    ):
        draw_star(
            draw,
            center,
            radius,
            (255, 220, 237, 125),
        )

    # Ligne discrète du pied de page.
    draw.line(
        (84, 807, 1316, 807),
        fill=(138, 78, 111, 105),
        width=1,
    )

    draw.text(
        (84, 817),
        "CLAN RENARD",
        font=font(13, bold=True),
        fill=COLORS["muted"],
    )

    footer = "CALENDRIER PERSONNEL"
    footer_font = font(13)
    footer_bounds = draw.textbbox(
        (0, 0),
        footer,
        font=footer_font,
    )
    footer_width = footer_bounds[2] - footer_bounds[0]

    draw.text(
        (1316 - footer_width, 817),
        footer,
        font=footer_font,
        fill=COLORS["muted"],
    )

    image.save(
        TEMPLATE_PATH,
        format="PNG",
        optimize=True,
        compress_level=6,
    )

    print(f"OK : template créé -> {TEMPLATE_PATH}")


ASSET_SIZE = 256

GIFT_CLOSED_PATH = GIFTS_DIRECTORY / "gift_closed.png"
GIFT_AVAILABLE_PATH = GIFTS_DIRECTORY / "gift_available.png"
GIFT_OPENED_PATH = GIFTS_DIRECTORY / "gift_opened.png"
GIFT_DAY_24_PATH = GIFTS_DIRECTORY / "gift_day_24.png"

LOCK_PATH = DECORATIONS_DIRECTORY / "lock.png"
CHECK_PATH = DECORATIONS_DIRECTORY / "check.png"
MISSED_CROSS_PATH = DECORATIONS_DIRECTORY / "missed_cross.png"
SPARKLE_PATH = DECORATIONS_DIRECTORY / "sparkle.png"
SNOWFLAKE_PATH = DECORATIONS_DIRECTORY / "snowflake.png"

ASSETS_PREVIEW_PATH = GENERATED_DIRECTORY / "assets_preview.png"


def transparent_canvas(
    size: int = ASSET_SIZE,
) -> Image.Image:
    return Image.new(
        "RGBA",
        (size, size),
        (0, 0, 0, 0),
    )


def save_asset(
    image: Image.Image,
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image.save(
        path,
        format="PNG",
        optimize=True,
        compress_level=6,
    )

    print(f"OK : asset créé -> {path}")


def add_asset_shadow(
    image: Image.Image,
    box: tuple[int, int, int, int],
    *,
    radius: int = 15,
    opacity: int = 105,
) -> None:
    shadow = transparent_canvas(
        image.width
    )
    shadow_draw = ImageDraw.Draw(shadow)

    left, top, right, bottom = box

    shadow_draw.rounded_rectangle(
        (
            left + 5,
            top + 10,
            right + 5,
            bottom + 10,
        ),
        radius=radius,
        fill=(8, 2, 12, opacity),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(9)
    )
    image.alpha_composite(shadow)


def add_asset_glow(
    image: Image.Image,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int, int],
    *,
    blur: int = 22,
) -> None:
    layer = transparent_canvas(
        image.width
    )
    layer_draw = ImageDraw.Draw(layer)

    cx, cy = center

    layer_draw.ellipse(
        (
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
        ),
        fill=color,
    )

    layer = layer.filter(
        ImageFilter.GaussianBlur(blur)
    )
    image.alpha_composite(layer)


def draw_ribbon_tails(
    draw: ImageDraw.ImageDraw,
    *,
    center_x: int,
    start_y: int,
    length: int,
    width: int,
    color: tuple[int, int, int, int],
) -> None:
    half_width = width // 2

    draw.polygon(
        [
            (center_x - half_width, start_y),
            (
                center_x - half_width - 20,
                start_y + length,
            ),
            (
                center_x - 6,
                start_y + length - 16,
            ),
            (center_x, start_y + 16),
        ],
        fill=color,
    )

    draw.polygon(
        [
            (center_x + half_width, start_y),
            (
                center_x + half_width + 20,
                start_y + length,
            ),
            (
                center_x + 6,
                start_y + length - 16,
            ),
            (center_x, start_y + 16),
        ],
        fill=color,
    )


def draw_gift_bow(
    draw: ImageDraw.ImageDraw,
    *,
    center: tuple[int, int],
    color: tuple[int, int, int, int],
    highlight: tuple[int, int, int, int],
    large: bool = False,
) -> None:
    cx, cy = center

    bow_width = 57 if large else 49
    bow_height = 35 if large else 30
    knot_radius = 14 if large else 12

    draw.ellipse(
        (
            cx - bow_width,
            cy - bow_height,
            cx - 3,
            cy + bow_height,
        ),
        fill=color,
        outline=highlight,
        width=3,
    )

    draw.ellipse(
        (
            cx + 3,
            cy - bow_height,
            cx + bow_width,
            cy + bow_height,
        ),
        fill=color,
        outline=highlight,
        width=3,
    )

    draw.ellipse(
        (
            cx - knot_radius,
            cy - knot_radius,
            cx + knot_radius,
            cy + knot_radius,
        ),
        fill=highlight,
        outline=(255, 248, 252, 235),
        width=2,
    )


def draw_closed_gift(
    image: Image.Image,
    *,
    available: bool = False,
    special: bool = False,
) -> None:
    if available:
        add_asset_glow(
            image,
            center=(128, 132),
            radius=90,
            color=(239, 135, 188, 85),
            blur=25,
        )

    if special:
        add_asset_glow(
            image,
            center=(128, 132),
            radius=88,
            color=(230, 181, 141, 65),
            blur=25,
        )

    draw = ImageDraw.Draw(image)

    body_box = (
        45,
        92,
        211,
        218,
    )
    lid_box = (
        34,
        73,
        222,
        113,
    )

    add_asset_shadow(
        image,
        body_box,
        radius=18,
        opacity=100,
    )

    draw = ImageDraw.Draw(image)

    if special:
        body_color = (184, 103, 112, 255)
        body_bottom = (137, 66, 86, 255)
        ribbon_color = COLORS["gold"]
        ribbon_highlight = (255, 224, 192, 255)
        outline = (250, 210, 176, 255)
    elif available:
        body_color = (218, 116, 166, 255)
        body_bottom = (158, 72, 123, 255)
        ribbon_color = (255, 211, 230, 255)
        ribbon_highlight = (255, 241, 248, 255)
        outline = (255, 219, 237, 255)
    else:
        body_color = (182, 91, 137, 255)
        body_bottom = (120, 57, 103, 255)
        ribbon_color = (233, 158, 192, 255)
        ribbon_highlight = (250, 215, 230, 255)
        outline = (226, 155, 190, 220)

    draw.rounded_rectangle(
        body_box,
        radius=19,
        fill=body_bottom,
        outline=outline,
        width=3,
    )

    draw.rounded_rectangle(
        (
            body_box[0] + 3,
            body_box[1] + 3,
            body_box[2] - 3,
            151,
        ),
        radius=15,
        fill=body_color,
    )

    draw.rectangle(
        (
            body_box[0] + 3,
            139,
            body_box[2] - 3,
            body_box[3] - 18,
        ),
        fill=body_bottom,
    )

    draw.rounded_rectangle(
        body_box,
        radius=19,
        outline=outline,
        width=3,
    )

    ribbon_width = 33 if special else 29

    draw.rectangle(
        (
            128 - ribbon_width // 2,
            body_box[1],
            128 + ribbon_width // 2,
            body_box[3],
        ),
        fill=ribbon_color,
    )

    draw.rectangle(
        (
            128 - ribbon_width // 2 + 4,
            body_box[1] + 4,
            128 - ribbon_width // 2 + 8,
            body_box[3] - 5,
        ),
        fill=(
            ribbon_highlight[0],
            ribbon_highlight[1],
            ribbon_highlight[2],
            105,
        ),
    )

    draw.rounded_rectangle(
        lid_box,
        radius=14,
        fill=body_color,
        outline=outline,
        width=3,
    )

    draw.rectangle(
        (
            128 - ribbon_width // 2,
            lid_box[1],
            128 + ribbon_width // 2,
            lid_box[3],
        ),
        fill=ribbon_color,
    )

    draw.line(
        (
            lid_box[0] + 13,
            lid_box[1] + 9,
            lid_box[2] - 13,
            lid_box[1] + 9,
        ),
        fill=(
            255,
            236,
            245,
            85,
        ),
        width=3,
    )

    draw_gift_bow(
        draw,
        center=(128, 70),
        color=ribbon_color,
        highlight=ribbon_highlight,
        large=special,
    )

    if available:
        for center, radius in (
            ((33, 79), 9),
            ((222, 116), 7),
            ((202, 39), 6),
        ):
            draw_star(
                draw,
                center,
                radius,
                (255, 231, 243, 225),
            )

    if special:
        for center, radius in (
            ((38, 53), 10),
            ((217, 55), 8),
            ((225, 143), 6),
        ):
            draw_star(
                draw,
                center,
                radius,
                (255, 224, 189, 230),
            )


def draw_opened_gift(
    image: Image.Image,
) -> None:
    add_asset_glow(
        image,
        center=(128, 128),
        radius=94,
        color=(121, 201, 158, 65),
        blur=25,
    )

    draw = ImageDraw.Draw(image)

    body_box = (
        48,
        116,
        208,
        220,
    )

    add_asset_shadow(
        image,
        body_box,
        radius=18,
        opacity=100,
    )

    draw = ImageDraw.Draw(image)

    body_color = (118, 171, 144, 255)
    body_dark = (66, 121, 102, 255)
    ribbon_color = (224, 243, 232, 255)
    outline = (188, 235, 211, 255)

    light_layer = transparent_canvas()
    light_draw = ImageDraw.Draw(light_layer)

    light_draw.polygon(
        [
            (82, 125),
            (101, 38),
            (120, 125),
        ],
        fill=(209, 249, 225, 80),
    )
    light_draw.polygon(
        [
            (112, 125),
            (143, 25),
            (157, 125),
        ],
        fill=(246, 231, 247, 65),
    )
    light_draw.polygon(
        [
            (144, 125),
            (187, 53),
            (178, 125),
        ],
        fill=(209, 249, 225, 55),
    )

    light_layer = light_layer.filter(
        ImageFilter.GaussianBlur(5)
    )
    image.alpha_composite(light_layer)

    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        body_box,
        radius=18,
        fill=body_dark,
        outline=outline,
        width=3,
    )

    draw.rounded_rectangle(
        (
            body_box[0] + 3,
            body_box[1] + 3,
            body_box[2] - 3,
            164,
        ),
        radius=14,
        fill=body_color,
    )

    draw.rectangle(
        (
            body_box[0] + 3,
            151,
            body_box[2] - 3,
            body_box[3] - 17,
        ),
        fill=body_dark,
    )

    draw.rounded_rectangle(
        body_box,
        radius=18,
        outline=outline,
        width=3,
    )

    draw.rectangle(
        (
            114,
            body_box[1],
            142,
            body_box[3],
        ),
        fill=ribbon_color,
    )

    lid = transparent_canvas()
    lid_draw = ImageDraw.Draw(lid)

    lid_draw.rounded_rectangle(
        (
            35,
            80,
            220,
            118,
        ),
        radius=13,
        fill=body_color,
        outline=outline,
        width=3,
    )

    lid_draw.rectangle(
        (
            114,
            80,
            142,
            118,
        ),
        fill=ribbon_color,
    )

    draw_gift_bow(
        lid_draw,
        center=(128, 78),
        color=ribbon_color,
        highlight=(250, 255, 252, 255),
    )

    lid = lid.rotate(
        8,
        resample=Image.Resampling.BICUBIC,
        center=(128, 98),
    )
    image.alpha_composite(
        lid,
        (-12, -34),
    )

    draw = ImageDraw.Draw(image)

    draw.line(
        (
            181,
            65,
            195,
            78,
            222,
            45,
        ),
        fill=COLORS["green"],
        width=9,
        joint="curve",
    )

    for center, radius in (
        ((71, 58), 7),
        ((161, 42), 8),
        ((205, 103), 5),
    ):
        draw_star(
            draw,
            center,
            radius,
            (222, 248, 233, 220),
        )


def create_gift_assets() -> None:
    closed = transparent_canvas()
    draw_closed_gift(
        closed,
        available=False,
        special=False,
    )
    save_asset(
        closed,
        GIFT_CLOSED_PATH,
    )

    available = transparent_canvas()
    draw_closed_gift(
        available,
        available=True,
        special=False,
    )
    save_asset(
        available,
        GIFT_AVAILABLE_PATH,
    )

    opened = transparent_canvas()
    draw_opened_gift(opened)
    save_asset(
        opened,
        GIFT_OPENED_PATH,
    )

    special = transparent_canvas()
    draw_closed_gift(
        special,
        available=False,
        special=True,
    )
    save_asset(
        special,
        GIFT_DAY_24_PATH,
    )


def create_lock_asset() -> None:
    image = transparent_canvas()
    draw = ImageDraw.Draw(image)

    add_asset_glow(
        image,
        center=(128, 135),
        radius=76,
        color=(147, 111, 142, 30),
        blur=22,
    )

    draw = ImageDraw.Draw(image)

    draw.arc(
        (
            73,
            43,
            183,
            154,
        ),
        start=180,
        end=360,
        fill=(189, 164, 187, 255),
        width=18,
    )

    draw.line(
        (
            73,
            98,
            73,
            135,
        ),
        fill=(189, 164, 187, 255),
        width=18,
    )
    draw.line(
        (
            183,
            98,
            183,
            135,
        ),
        fill=(189, 164, 187, 255),
        width=18,
    )

    draw.rounded_rectangle(
        (
            52,
            112,
            204,
            220,
        ),
        radius=24,
        fill=(101, 72, 101, 255),
        outline=(199, 173, 195, 255),
        width=4,
    )

    draw.ellipse(
        (
            115,
            145,
            141,
            171,
        ),
        fill=(42, 22, 49, 255),
    )
    draw.polygon(
        [
            (121, 165),
            (135, 165),
            (143, 197),
            (113, 197),
        ],
        fill=(42, 22, 49, 255),
    )

    save_asset(
        image,
        LOCK_PATH,
    )


def create_check_asset() -> None:
    image = transparent_canvas()

    add_asset_glow(
        image,
        center=(128, 128),
        radius=88,
        color=(121, 201, 158, 45),
        blur=24,
    )

    draw = ImageDraw.Draw(image)

    draw.ellipse(
        (
            36,
            36,
            220,
            220,
        ),
        fill=(50, 104, 83, 245),
        outline=(151, 224, 185, 255),
        width=6,
    )

    draw.line(
        (
            77,
            129,
            112,
            163,
            181,
            84,
        ),
        fill=(227, 251, 237, 255),
        width=18,
        joint="curve",
    )

    save_asset(
        image,
        CHECK_PATH,
    )


def create_cross_asset() -> None:
    image = transparent_canvas()

    add_asset_glow(
        image,
        center=(128, 128),
        radius=88,
        color=(215, 103, 131, 42),
        blur=24,
    )

    draw = ImageDraw.Draw(image)

    draw.ellipse(
        (
            36,
            36,
            220,
            220,
        ),
        fill=(100, 44, 61, 240),
        outline=(231, 135, 158, 255),
        width=6,
    )

    draw.line(
        (
            84,
            84,
            172,
            172,
        ),
        fill=(255, 224, 232, 255),
        width=17,
    )
    draw.line(
        (
            172,
            84,
            84,
            172,
        ),
        fill=(255, 224, 232, 255),
        width=17,
    )

    save_asset(
        image,
        MISSED_CROSS_PATH,
    )


def create_sparkle_asset() -> None:
    image = transparent_canvas()

    add_asset_glow(
        image,
        center=(128, 128),
        radius=79,
        color=(241, 162, 200, 55),
        blur=22,
    )

    draw = ImageDraw.Draw(image)

    draw_star(
        draw,
        center=(128, 128),
        radius=78,
        color=(255, 223, 239, 255),
    )
    draw_star(
        draw,
        center=(198, 69),
        radius=28,
        color=(232, 174, 205, 235),
    )
    draw_star(
        draw,
        center=(62, 193),
        radius=20,
        color=(255, 236, 245, 210),
    )

    save_asset(
        image,
        SPARKLE_PATH,
    )


def create_snowflake_asset() -> None:
    image = transparent_canvas()
    draw = ImageDraw.Draw(image)

    cx = 128
    cy = 128
    radius = 89
    color = (243, 206, 225, 240)

    for index in range(6):
        angle = index * math.pi / 3

        end_x = cx + math.cos(angle) * radius
        end_y = cy + math.sin(angle) * radius

        draw.line(
            (
                cx,
                cy,
                round(end_x),
                round(end_y),
            ),
            fill=color,
            width=7,
        )

        branch_distance = radius * 0.62
        branch_x = cx + math.cos(angle) * branch_distance
        branch_y = cy + math.sin(angle) * branch_distance

        for direction in (-1, 1):
            branch_angle = (
                angle
                + direction * math.pi / 4
            )
            branch_length = 30

            child_x = (
                branch_x
                - math.cos(branch_angle) * branch_length
            )
            child_y = (
                branch_y
                - math.sin(branch_angle) * branch_length
            )

            draw.line(
                (
                    round(branch_x),
                    round(branch_y),
                    round(child_x),
                    round(child_y),
                ),
                fill=color,
                width=5,
            )

    draw.ellipse(
        (
            cx - 9,
            cy - 9,
            cx + 9,
            cy + 9,
        ),
        fill=(255, 239, 247, 255),
    )

    save_asset(
        image,
        SNOWFLAKE_PATH,
    )


def create_decoration_assets() -> None:
    create_lock_asset()
    create_check_asset()
    create_cross_asset()
    create_sparkle_asset()
    create_snowflake_asset()


def load_thumbnail(
    path: Path,
    *,
    size: tuple[int, int],
) -> Image.Image:
    with Image.open(path) as source:
        asset = source.convert("RGBA")

    asset.thumbnail(
        size,
        Image.Resampling.LANCZOS,
    )

    return asset


def create_assets_preview() -> None:
    preview_width = 1200
    preview_height = 700

    preview = Image.new(
        "RGBA",
        (preview_width, preview_height),
        COLORS["background_top"],
    )

    add_glow(
        preview,
        center=(190, 100),
        radius=250,
        color=(211, 95, 149, 28),
    )
    add_glow(
        preview,
        center=(1050, 620),
        radius=260,
        color=(202, 91, 148, 22),
    )

    draw = ImageDraw.Draw(preview)

    draw.rounded_rectangle(
        (
            28,
            28,
            preview_width - 28,
            preview_height - 28,
        ),
        radius=30,
        fill=(37, 19, 44, 240),
        outline=COLORS["panel_border"],
        width=2,
    )

    centered_text(
        draw,
        (80, 52, 1120, 112),
        "PACK GRAPHIQUE — CLAN RENARD",
        font(36, bold=True),
        COLORS["pink_light"],
    )

    centered_text(
        draw,
        (80, 110, 1120, 146),
        "Cadeaux et icônes du calendrier de l'Avent",
        font(18),
        COLORS["muted"],
    )

    items = [
        (
            "Cadeau fermé",
            GIFT_CLOSED_PATH,
        ),
        (
            "Disponible",
            GIFT_AVAILABLE_PATH,
        ),
        (
            "Cadeau ouvert",
            GIFT_OPENED_PATH,
        ),
        (
            "Case du 24",
            GIFT_DAY_24_PATH,
        ),
        (
            "Verrouillée",
            LOCK_PATH,
        ),
        (
            "Ouverte",
            CHECK_PATH,
        ),
        (
            "Manquée",
            MISSED_CROSS_PATH,
        ),
        (
            "Étincelles",
            SPARKLE_PATH,
        ),
    ]

    card_width = 250
    card_height = 215
    gap_x = 26
    gap_y = 28
    start_x = 61
    start_y = 174

    for index, (label, path) in enumerate(items):
        column = index % 4
        row = index // 4

        x = start_x + column * (
            card_width + gap_x
        )
        y = start_y + row * (
            card_height + gap_y
        )

        draw.rounded_rectangle(
            (
                x,
                y,
                x + card_width,
                y + card_height,
            ),
            radius=22,
            fill=COLORS["card"],
            outline=COLORS["card_border"],
            width=2,
        )

        asset = load_thumbnail(
            path,
            size=(145, 145),
        )

        preview.alpha_composite(
            asset,
            (
                x + (card_width - asset.width) // 2,
                y + 12,
            ),
        )

        centered_text(
            draw,
            (
                x + 8,
                y + 165,
                x + card_width - 8,
                y + 203,
            ),
            label,
            font(17, bold=True),
            COLORS["pink_white"],
        )

    preview.save(
        ASSETS_PREVIEW_PATH,
        format="PNG",
        optimize=True,
        compress_level=6,
    )

    print(
        f"OK : aperçu des assets créé -> {ASSETS_PREVIEW_PATH}"
    )


def create_all_graphic_assets() -> None:
    print()
    print("Création du template statique...")
    create_calendar_template()

    print()
    print("Création des cadeaux...")
    create_gift_assets()

    print()
    print("Création des icônes...")
    create_decoration_assets()

    print()
    print("Création de la planche d'aperçu...")
    create_assets_preview()
# ============================================================
# CLAN RENARD — INSTALLATEUR DU NOUVEAU VISUEL
# PAQUET 3/3
#
# Générateur rapide avec cache + intégration bot + installation.
# À coller immédiatement sous le paquet 2/3.
# ============================================================

import py_compile
from io import BytesIO


# ============================================================
# EMPLACEMENT DU NOUVEAU GÉNÉRATEUR DANS LE BOT
# ============================================================

IMAGE_GENERATOR_PATH = BOT_DIRECTORY / "image_generator.py"


# ============================================================
# CONTENU DU NOUVEAU GÉNÉRATEUR (RAPIDE + CACHE)
#
# Ce texte est écrit tel quel dans bot/features/advent/image_generator.py
# Il ne dépend PAS de ce script d'installation : une fois installé,
# le bot peut l'importer indépendamment.
# ============================================================

IMAGE_GENERATOR_SOURCE = '''# ============================================================
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
'''


# ============================================================
# SAUVEGARDE DES ANCIENS FICHIERS PYTHON DU BOT
# ============================================================

def backup_existing_generator() -> None:
    if not BOT_DIRECTORY.exists():
        return

    python_files = list(BOT_DIRECTORY.glob("*.py"))

    if not python_files:
        print("Aucun ancien fichier Python trouvé dans", BOT_DIRECTORY)
        return

    backup_target = BACKUP_DIRECTORY / "bot_features_advent"
    backup_target.mkdir(parents=True, exist_ok=True)

    for source_file in python_files:
        shutil.copy2(source_file, backup_target / source_file.name)
        print(f"Sauvegardé : {source_file.name}")

    print(f"OK : anciens fichiers sauvegardés -> {backup_target}")


# ============================================================
# ÉCRITURE DU NOUVEAU GÉNÉRATEUR
# ============================================================

def install_image_generator() -> None:
    BOT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    IMAGE_GENERATOR_PATH.write_text(
        IMAGE_GENERATOR_SOURCE,
        encoding="utf-8",
    )

    print(f"OK : nouveau générateur installé -> {IMAGE_GENERATOR_PATH}")


def verify_generator_syntax() -> None:
    try:
        py_compile.compile(
            str(IMAGE_GENERATOR_PATH),
            doraise=True,
        )
        print("OK : la syntaxe du nouveau générateur est valide.")
    except py_compile.PyCompileError as error:
        print("ERREUR : le nouveau générateur contient une erreur de syntaxe.")
        print(error)
        raise


# ============================================================
# APERÇU FINAL DU CALENDRIER (avec le nouveau générateur)
# ============================================================

def render_demo_calendar() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "clan_renard_image_generator",
        IMAGE_GENERATOR_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    day_states: dict[int, str] = {}
    for day in range(1, 25):
        if day < 9:
            day_states[day] = "opened"
        elif day == 9:
            day_states[day] = "available"
        elif day in (10, 11):
            day_states[day] = "missed"
        else:
            day_states[day] = "locked"

    payload = module.AdventCalendarRenderer.render(
        username="Pseudo",
        year=datetime.now().year,
        points=950,
        day_states=day_states,
    )

    demo_path = GENERATED_DIRECTORY / "nouveau-calendrier-apercu.png"
    demo_path.write_bytes(payload)

    print(f"OK : aperçu du calendrier généré -> {demo_path}")

    # Deuxième rendu identique : doit venir du cache (quasi instantané).
    start = datetime.now()
    module.AdventCalendarRenderer.render(
        username="Pseudo",
        year=datetime.now().year,
        points=950,
        day_states=day_states,
    )
    elapsed_ms = (datetime.now() - start).total_seconds() * 1000
    print(f"OK : second rendu (cache) en {elapsed_ms:.2f} ms")


# ============================================================
# INSTALLATION COMPLÈTE
# ============================================================

def run_installation() -> None:
    print("============================================================")
    print("CLAN RENARD — INSTALLATION DU NOUVEAU VISUEL")
    print("============================================================")

    ensure_directories()

    print()
    print("Étape 1/5 — Sauvegarde des anciens fichiers...")
    backup_existing_generator()

    print()
    print("Étape 2/5 — Génération du pack graphique...")
    create_all_graphic_assets()

    print()
    print("Étape 3/5 — Installation du nouveau générateur...")
    install_image_generator()

    print()
    print("Étape 4/5 — Vérification de la syntaxe...")
    verify_generator_syntax()

    print()
    print("Étape 5/5 — Génération d'un aperçu de calendrier...")
    render_demo_calendar()

    print()
    print("============================================================")
    print("INSTALLATION TERMINÉE")
    print("============================================================")
    print()
    print("Prochaine étape : dans ton code du bot, importe et utilise")
    print("le nouveau générateur, par exemple :")
    print()
    print("    from bot.features.advent.image_generator import (")
    print("        AdventCalendarRenderer,")
    print("    )")
    print()
    print("    png_bytes = AdventCalendarRenderer.render(")
    print("        username=member.display_name,")
    print("        year=2026,")
    print("        points=user_points,")
    print("        day_states=user_day_states,  # dict {jour: état}")
    print("    )")
    print()
    print("Aucun fichier PostgreSQL, récompense ou commande n'a été touché.")


if __name__ == "__main__":
    run_installation()

# ============================================================
# FIN — TU PEUX LANCER LE SCRIPT
# ============================================================
