from __future__ import annotations

import math
import random
from collections.abc import Iterable
from pathlib import Path

from PIL import (
    Image,
    ImageDraw,
    ImageFilter,
    ImageFont,
)

from bot.features.advent.theme import (
    AdventPalette,
    Color,
    ColorAlpha,
)


Point = tuple[int, int]
Box = tuple[int, int, int, int]


def create_vertical_gradient(
    size: tuple[int, int],
    top: Color,
    bottom: Color,
) -> Image.Image:
    """
    Crée rapidement un fond dégradé en fabriquant une bande verticale
    d'un pixel, ensuite étirée sur toute la largeur.
    """
    width, height = size
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()

    denominator = max(1, height - 1)

    for y in range(height):
        ratio = y / denominator
        colour = tuple(
            round(
                top[channel]
                + (
                    bottom[channel] - top[channel]
                ) * ratio
            )
            for channel in range(3)
        )
        pixels[0, y] = colour

    return strip.resize(
        (width, height),
        Image.Resampling.BILINEAR,
    ).convert("RGBA")


def rounded_layer(
    size: tuple[int, int],
    box: Box,
    *,
    radius: int,
    fill: ColorAlpha,
    outline: ColorAlpha | None = None,
    width: int = 1,
    blur: int = 0,
) -> Image.Image:
    layer = Image.new(
        "RGBA",
        size,
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(layer)

    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )

    if blur > 0:
        layer = layer.filter(
            ImageFilter.GaussianBlur(blur)
        )

    return layer


def add_soft_glow(
    image: Image.Image,
    center: Point,
    radius: int,
    colour: ColorAlpha,
) -> None:
    layer = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(layer)

    x, y = center
    draw.ellipse(
        (
            x - radius,
            y - radius,
            x + radius,
            y + radius,
        ),
        fill=colour,
    )

    layer = layer.filter(
        ImageFilter.GaussianBlur(
            max(4, radius // 2)
        )
    )
    image.alpha_composite(layer)


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    box: Box,
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: Color | ColorAlpha,
    stroke_width: int = 0,
    stroke_fill: Color | ColorAlpha | None = None,
    vertical_offset: int = 0,
) -> None:
    left, top, right, bottom = box

    text_box = draw.textbbox(
        (0, 0),
        text,
        font=font,
        stroke_width=stroke_width,
    )
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]

    x = left + (right - left - text_width) / 2
    y = (
        top
        + (bottom - top - text_height) / 2
        - text_box[1]
        + vertical_offset
    )

    draw.text(
        (round(x), round(y)),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def draw_star(
    draw: ImageDraw.ImageDraw,
    center: Point,
    *,
    outer_radius: int,
    inner_radius: int,
    fill: Color | ColorAlpha,
    points: int = 4,
    rotation: float = 0.0,
) -> None:
    coordinates: list[Point] = []
    cx, cy = center

    for index in range(points * 2):
        angle = (
            rotation
            - math.pi / 2
            + index * math.pi / points
        )
        radius = (
            outer_radius
            if index % 2 == 0
            else inner_radius
        )

        coordinates.append(
            (
                round(cx + math.cos(angle) * radius),
                round(cy + math.sin(angle) * radius),
            )
        )

    draw.polygon(coordinates, fill=fill)


def draw_snowflake(
    draw: ImageDraw.ImageDraw,
    center: Point,
    *,
    radius: int,
    fill: Color | ColorAlpha,
    width: int = 2,
) -> None:
    cx, cy = center

    for arm in range(6):
        angle = arm * math.pi / 3
        end_x = cx + math.cos(angle) * radius
        end_y = cy + math.sin(angle) * radius

        draw.line(
            (cx, cy, end_x, end_y),
            fill=fill,
            width=width,
        )

        branch_distance = radius * 0.63
        branch_x = cx + math.cos(angle) * branch_distance
        branch_y = cy + math.sin(angle) * branch_distance

        for direction in (-1, 1):
            branch_angle = angle + direction * math.pi / 4
            branch_length = radius * 0.28

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
                    branch_x,
                    branch_y,
                    child_x,
                    child_y,
                ),
                fill=fill,
                width=max(1, width - 1),
            )


def draw_flower(
    draw: ImageDraw.ImageDraw,
    center: Point,
    *,
    radius: int,
    palette: AdventPalette,
    rotation: float = 0.0,
) -> None:
    cx, cy = center
    petal_radius = max(3, radius // 2)

    for petal in range(5):
        angle = (
            rotation
            + petal * 2 * math.pi / 5
            - math.pi / 2
        )
        petal_x = cx + math.cos(angle) * radius * 0.72
        petal_y = cy + math.sin(angle) * radius * 0.72

        draw.ellipse(
            (
                round(petal_x - petal_radius),
                round(petal_y - petal_radius),
                round(petal_x + petal_radius),
                round(petal_y + petal_radius),
            ),
            fill=palette.pink_light,
            outline=palette.pink,
            width=max(1, radius // 8),
        )

    center_radius = max(3, radius // 3)
    draw.ellipse(
        (
            cx - center_radius,
            cy - center_radius,
            cx + center_radius,
            cy + center_radius,
        ),
        fill=palette.gold_rose,
    )


def draw_leaf(
    draw: ImageDraw.ImageDraw,
    center: Point,
    *,
    length: int,
    angle: float,
    fill: Color | ColorAlpha,
) -> None:
    cx, cy = center
    half_width = max(2, length // 4)

    direction_x = math.cos(angle)
    direction_y = math.sin(angle)
    perpendicular_x = -direction_y
    perpendicular_y = direction_x

    tip = (
        round(cx + direction_x * length),
        round(cy + direction_y * length),
    )
    left = (
        round(cx + perpendicular_x * half_width),
        round(cy + perpendicular_y * half_width),
    )
    right = (
        round(cx - perpendicular_x * half_width),
        round(cy - perpendicular_y * half_width),
    )

    draw.polygon(
        [left, tip, right, (cx, cy)],
        fill=fill,
    )


def draw_flowering_branch(
    draw: ImageDraw.ImageDraw,
    points: Iterable[Point],
    *,
    palette: AdventPalette,
    seed: int,
) -> None:
    branch_points = list(points)

    if len(branch_points) < 2:
        return

    randomizer = random.Random(seed)

    draw.line(
        branch_points,
        fill=palette.pink_dark,
        width=7,
        joint="curve",
    )

    for index in range(1, len(branch_points) - 1):
        x, y = branch_points[index]

        if index % 2 == 0:
            draw_leaf(
                draw,
                (x, y),
                length=randomizer.randint(18, 29),
                angle=randomizer.uniform(-2.8, -0.3),
                fill=palette.plum_light,
            )
        else:
            draw_leaf(
                draw,
                (x, y),
                length=randomizer.randint(18, 29),
                angle=randomizer.uniform(0.3, 2.8),
                fill=palette.plum_light,
            )

        if index % 2 == 1 or index == len(branch_points) - 2:
            draw_flower(
                draw,
                (
                    x + randomizer.randint(-7, 7),
                    y + randomizer.randint(-7, 7),
                ),
                radius=randomizer.randint(10, 16),
                palette=palette,
                rotation=randomizer.random(),
            )


def draw_lock(
    draw: ImageDraw.ImageDraw,
    center: Point,
    *,
    size: int,
    colour: Color | ColorAlpha,
) -> None:
    cx, cy = center
    body_width = size
    body_height = round(size * 0.72)
    shackle_width = round(size * 0.62)
    shackle_height = round(size * 0.60)

    body_left = cx - body_width // 2
    body_top = cy
    body_right = cx + body_width // 2
    body_bottom = body_top + body_height

    shackle_left = cx - shackle_width // 2
    shackle_top = body_top - shackle_height
    shackle_right = cx + shackle_width // 2
    shackle_bottom = body_top + round(size * 0.15)

    draw.arc(
        (
            shackle_left,
            shackle_top,
            shackle_right,
            shackle_bottom,
        ),
        start=180,
        end=360,
        fill=colour,
        width=max(3, size // 8),
    )

    draw.rounded_rectangle(
        (
            body_left,
            body_top,
            body_right,
            body_bottom,
        ),
        radius=max(3, size // 7),
        fill=colour,
    )

    keyhole_radius = max(2, size // 11)
    draw.ellipse(
        (
            cx - keyhole_radius,
            body_top + body_height // 3 - keyhole_radius,
            cx + keyhole_radius,
            body_top + body_height // 3 + keyhole_radius,
        ),
        fill=(55, 32, 58, 255),
    )
    draw.rectangle(
        (
            cx - max(1, keyhole_radius // 2),
            body_top + body_height // 3,
            cx + max(1, keyhole_radius // 2),
            body_top + body_height // 3
            + keyhole_radius * 2,
        ),
        fill=(55, 32, 58, 255),
    )


def draw_check(
    draw: ImageDraw.ImageDraw,
    center: Point,
    *,
    size: int,
    colour: Color | ColorAlpha,
    width: int,
) -> None:
    cx, cy = center

    draw.line(
        (
            cx - size // 2,
            cy,
            cx - size // 8,
            cy + size // 3,
            cx + size // 2,
            cy - size // 2,
        ),
        fill=colour,
        width=width,
        joint="curve",
    )


def draw_cross(
    draw: ImageDraw.ImageDraw,
    center: Point,
    *,
    size: int,
    colour: Color | ColorAlpha,
    width: int,
) -> None:
    cx, cy = center
    half = size // 2

    draw.line(
        (
            cx - half,
            cy - half,
            cx + half,
            cy + half,
        ),
        fill=colour,
        width=width,
    )
    draw.line(
        (
            cx + half,
            cy - half,
            cx - half,
            cy + half,
        ),
        fill=colour,
        width=width,
    )


def draw_gift(
    draw: ImageDraw.ImageDraw,
    box: Box,
    *,
    palette: AdventPalette,
    opened: bool = False,
    special: bool = False,
    muted: bool = False,
) -> None:
    """
    Dessine un paquet cadeau sans utiliser d'image externe.

    Le cadeau peut être fermé, ouvert, spécial pour le 24,
    ou assombri lorsqu'il est verrouillé/manqué.
    """
    left, top, right, bottom = box
    width = right - left
    height = bottom - top

    base_colour: Color = (
        palette.gold_rose
        if special
        else palette.pink
    )
    ribbon_colour: Color = (
        palette.pink_white
        if special
        else palette.pink_light
    )

    if muted:
        base_colour = (
            round(base_colour[0] * 0.55),
            round(base_colour[1] * 0.55),
            round(base_colour[2] * 0.55),
        )
        ribbon_colour = palette.locked

    lid_height = max(8, round(height * 0.18))
    body_top = top + lid_height

    if opened:
        # Boîte ouverte.
        lid_top = top - round(height * 0.08)
        lid_left = left - round(width * 0.09)
        lid_right = right + round(width * 0.09)

        draw.rounded_rectangle(
            (
                lid_left,
                lid_top,
                lid_right,
                lid_top + lid_height,
            ),
            radius=max(3, lid_height // 3),
            fill=base_colour,
            outline=palette.pink_white,
            width=2,
        )

        # Lumière sortant du cadeau.
        draw.polygon(
            [
                (
                    left + round(width * 0.27),
                    body_top,
                ),
                (
                    left + round(width * 0.40),
                    top - round(height * 0.28),
                ),
                (
                    left + round(width * 0.50),
                    body_top,
                ),
            ],
            fill=(255, 222, 239, 95),
        )
        draw.polygon(
            [
                (
                    left + round(width * 0.50),
                    body_top,
                ),
                (
                    left + round(width * 0.65),
                    top - round(height * 0.20),
                ),
                (
                    left + round(width * 0.74),
                    body_top,
                ),
            ],
            fill=(255, 197, 225, 75),
        )
    else:
        draw.rounded_rectangle(
            (
                left - round(width * 0.05),
                top,
                right + round(width * 0.05),
                body_top + 2,
            ),
            radius=max(3, lid_height // 3),
            fill=base_colour,
            outline=palette.pink_white,
            width=2,
        )

    draw.rounded_rectangle(
        (
            left,
            body_top,
            right,
            bottom,
        ),
        radius=max(4, round(width * 0.08)),
        fill=base_colour,
        outline=palette.pink_white,
        width=2,
    )

    ribbon_width = max(7, round(width * 0.18))
    center_x = (left + right) // 2

    draw.rectangle(
        (
            center_x - ribbon_width // 2,
            body_top,
            center_x + ribbon_width // 2,
            bottom,
        ),
        fill=ribbon_colour,
    )

    # Nœud.
    bow_y = top - max(1, round(height * 0.03))
    bow_width = round(width * 0.33)
    bow_height = round(height * 0.25)

    draw.ellipse(
        (
            center_x - bow_width,
            bow_y - bow_height // 2,
            center_x,
            bow_y + bow_height // 2,
        ),
        fill=ribbon_colour,
        outline=palette.pink_white,
        width=2,
    )
    draw.ellipse(
        (
            center_x,
            bow_y - bow_height // 2,
            center_x + bow_width,
            bow_y + bow_height // 2,
        ),
        fill=ribbon_colour,
        outline=palette.pink_white,
        width=2,
    )
    draw.ellipse(
        (
            center_x - ribbon_width // 2,
            bow_y - ribbon_width // 2,
            center_x + ribbon_width // 2,
            bow_y + ribbon_width // 2,
        ),
        fill=palette.pink_white,
    )


def draw_fox_emblem(
    image: Image.Image,
    center: Point,
    *,
    size: int,
    palette: AdventPalette,
    project_root: Path,
) -> None:
    """
    Utilise le logo facultatif si présent.

    Chemin attendu :
    assets/branding/clan_renard_logo.png

    Sans logo, un emblème de renard stylisé est dessiné
    automatiquement.
    """
    logo_path = (
        project_root
        / "assets"
        / "branding"
        / "clan_renard_logo.png"
    )

    if logo_path.exists():
        try:
            with Image.open(logo_path) as source:
                logo = source.convert("RGBA")
                logo.thumbnail(
                    (size, size),
                    Image.Resampling.LANCZOS,
                )

                x = center[0] - logo.width // 2
                y = center[1] - logo.height // 2
                image.alpha_composite(logo, (x, y))
                return
        except OSError:
            # Un logo invalide ne doit pas empêcher le calendrier
            # d'être généré.
            pass

    layer = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(layer)

    cx, cy = center
    half = size // 2

    # Halo circulaire.
    draw.ellipse(
        (
            cx - half,
            cy - half,
            cx + half,
            cy + half,
        ),
        fill=(52, 25, 57, 235),
        outline=palette.pink,
        width=max(3, size // 28),
    )

    face_width = round(size * 0.54)
    face_height = round(size * 0.48)
    face_top = cy - round(size * 0.17)

    # Oreilles.
    draw.polygon(
        [
            (
                cx - face_width // 2,
                face_top + round(size * 0.09),
            ),
            (
                cx - round(size * 0.43),
                cy - round(size * 0.38),
            ),
            (
                cx - round(size * 0.08),
                face_top,
            ),
        ],
        fill=palette.pink_white,
    )
    draw.polygon(
        [
            (
                cx + face_width // 2,
                face_top + round(size * 0.09),
            ),
            (
                cx + round(size * 0.43),
                cy - round(size * 0.38),
            ),
            (
                cx + round(size * 0.08),
                face_top,
            ),
        ],
        fill=palette.pink_white,
    )

    # Intérieur des oreilles.
    draw.polygon(
        [
            (
                cx - round(size * 0.30),
                cy - round(size * 0.20),
            ),
            (
                cx - round(size * 0.37),
                cy - round(size * 0.31),
            ),
            (
                cx - round(size * 0.17),
                cy - round(size * 0.16),
            ),
        ],
        fill=palette.pink,
    )
    draw.polygon(
        [
            (
                cx + round(size * 0.30),
                cy - round(size * 0.20),
            ),
            (
                cx + round(size * 0.37),
                cy - round(size * 0.31),
            ),
            (
                cx + round(size * 0.17),
                cy - round(size * 0.16),
            ),
        ],
        fill=palette.pink,
    )

    # Tête.
    draw.ellipse(
        (
            cx - face_width // 2,
            face_top,
            cx + face_width // 2,
            face_top + face_height,
        ),
        fill=palette.pink_white,
    )

    # Joues anguleuses.
    draw.polygon(
        [
            (
                cx - face_width // 2,
                cy,
            ),
            (
                cx,
                cy + round(size * 0.31),
            ),
            (
                cx,
                cy - round(size * 0.02),
            ),
        ],
        fill=palette.white,
    )
    draw.polygon(
        [
            (
                cx + face_width // 2,
                cy,
            ),
            (
                cx,
                cy + round(size * 0.31),
            ),
            (
                cx,
                cy - round(size * 0.02),
            ),
        ],
        fill=palette.white,
    )

    eye_radius = max(2, size // 35)
    eye_y = cy - round(size * 0.02)

    draw.ellipse(
        (
            cx - round(size * 0.16) - eye_radius,
            eye_y - eye_radius,
            cx - round(size * 0.16) + eye_radius,
            eye_y + eye_radius,
        ),
        fill=palette.plum,
    )
    draw.ellipse(
        (
            cx + round(size * 0.16) - eye_radius,
            eye_y - eye_radius,
            cx + round(size * 0.16) + eye_radius,
            eye_y + eye_radius,
        ),
        fill=palette.plum,
    )

    nose_radius = max(3, size // 24)
    nose_y = cy + round(size * 0.15)

    draw.ellipse(
        (
            cx - nose_radius,
            nose_y - nose_radius,
            cx + nose_radius,
            nose_y + nose_radius,
        ),
        fill=palette.plum,
    )

    image.alpha_composite(layer)


def add_subtle_texture(
    image: Image.Image,
    *,
    seed: int,
    opacity: int = 12,
) -> None:
    """
    Ajoute un grain très léger pour éviter un fond trop plat.

    Le seed fixe garantit le même rendu à chaque génération.
    """
    randomizer = random.Random(seed)
    texture = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )
    pixels = texture.load()
    width, height = image.size

    for _ in range((width * height) // 30):
        x = randomizer.randrange(width)
        y = randomizer.randrange(height)
        brightness = randomizer.randint(180, 255)
        pixels[x, y] = (
            brightness,
            brightness,
            brightness,
            randomizer.randint(1, opacity),
        )

    image.alpha_composite(texture)
