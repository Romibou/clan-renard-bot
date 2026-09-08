from __future__ import annotations

import asyncio
import io
import logging
import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import (
    Image,
    ImageDraw,
    ImageFilter,
    ImageOps,
)

from bot.features.advent.image_components import (
    add_soft_glow,
    add_subtle_texture,
    create_vertical_gradient,
    draw_centered_text,
    draw_check,
    draw_cross,
    draw_flower,
    draw_flowering_branch,
    draw_fox_emblem,
    draw_gift,
    draw_lock,
    draw_snowflake,
    draw_star,
    rounded_layer,
)
from bot.features.advent.models import CalendarState
from bot.features.advent.theme import (
    LAYOUT,
    PALETTE,
    AdventLayout,
    AdventPalette,
    load_font,
)
from bot.shared.text import truncate


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RenderedCalendar:
    buffer: io.BytesIO
    filename: str


class AdventImageGenerator:
    """
    Génère l'intégralité du calendrier avec Pillow.

    Aucune image correspondant à l'état d'un membre n'est enregistrée
    sur le disque. Le PNG final reste dans un BytesIO, puis Discord
    le reçoit directement.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        palette: AdventPalette = PALETTE,
        layout: AdventLayout = LAYOUT,
    ) -> None:
        self.project_root = project_root
        self.palette = palette
        self.layout = layout

        # Les polices sont chargées une seule fois et réutilisées.
        self.title_font = load_font(
            project_root,
            62,
            bold=True,
        )
        self.subtitle_font = load_font(
            project_root,
            27,
            bold=False,
        )
        self.member_font = load_font(
            project_root,
            31,
            bold=True,
        )
        self.day_font = load_font(
            project_root,
            37,
            bold=True,
        )
        self.status_font = load_font(
            project_root,
            17,
            bold=True,
        )
        self.stats_font = load_font(
            project_root,
            21,
            bold=False,
        )
        self.small_font = load_font(
            project_root,
            16,
            bold=False,
        )

    async def render(
        self,
        state: CalendarState,
        display_name: str,
        *,
        avatar_bytes: bytes | None = None,
        preview: bool = False,
    ) -> RenderedCalendar:
        """
        Exécute Pillow dans un thread séparé.

        La génération d'image est synchrone et consomme du processeur.
        asyncio.to_thread évite de figer le bot pendant le rendu.
        """
        return await asyncio.to_thread(
            self._render_sync,
            state,
            display_name,
            avatar_bytes,
            preview,
        )

    def _render_sync(
        self,
        state: CalendarState,
        display_name: str,
        avatar_bytes: bytes | None,
        preview: bool,
    ) -> RenderedCalendar:
        image = self._create_background(
            state.campaign.year
        )

        self._draw_outer_frame(image)
        self._draw_decorations(image)
        self._draw_header(
            image,
            state,
            display_name,
            avatar_bytes,
            preview=preview,
        )
        self._draw_grid(image, state)
        self._draw_footer(image, state)

        add_subtle_texture(
            image,
            seed=state.campaign.year + state.campaign.guild_id,
            opacity=9,
        )

        # Conversion finale en RGB : PNG plus compact et prévisible.
        flattened = Image.new(
            "RGB",
            image.size,
            self.palette.background_top,
        )
        flattened.paste(
            image.convert("RGB"),
            (0, 0),
        )

        buffer = io.BytesIO()
        flattened.save(
            buffer,
            format="PNG",
            optimize=True,
            compress_level=7,
        )
        buffer.seek(0)

        safe_name = "".join(
            character
            for character in display_name.lower()
            if character.isalnum()
        )[:20]

        if not safe_name:
            safe_name = "membre"

        filename = (
            f"calendrier-avent-"
            f"{state.campaign.year}-"
            f"{safe_name}.png"
        )

        return RenderedCalendar(
            buffer=buffer,
            filename=filename,
        )

    def _create_background(
        self,
        year: int,
    ) -> Image.Image:
        size = (
            self.layout.width,
            self.layout.height,
        )

        image = create_vertical_gradient(
            size,
            self.palette.background_top,
            self.palette.background_bottom,
        )

        # Plusieurs halos très doux apportent du relief.
        add_soft_glow(
            image,
            (250, 170),
            260,
            (214, 90, 148, 42),
        )
        add_soft_glow(
            image,
            (1380, 180),
            240,
            (178, 82, 148, 38),
        )
        add_soft_glow(
            image,
            (780, 900),
            320,
            (221, 116, 161, 25),
        )

        # Vignette sombre autour de l'image.
        vignette = Image.new(
            "L",
            size,
            0,
        )
        vignette_draw = ImageDraw.Draw(vignette)

        vignette_draw.ellipse(
            (
                -250,
                -300,
                self.layout.width + 250,
                self.layout.height + 350,
            ),
            fill=225,
        )

        vignette = vignette.filter(
            ImageFilter.GaussianBlur(115)
        )
        inverse = ImageOps.invert(vignette)

        dark_layer = Image.new(
            "RGBA",
            size,
            (9, 3, 14, 0),
        )
        dark_layer.putalpha(
            inverse.point(
                lambda value: round(value * 0.58)
            )
        )
        image.alpha_composite(dark_layer)

        # Quelques petites poussières lumineuses déterministes.
        randomizer = random.Random(year * 991)
        draw = ImageDraw.Draw(image)

        for _ in range(75):
            x = randomizer.randint(
                self.layout.outer_margin,
                self.layout.width
                - self.layout.outer_margin,
            )
            y = randomizer.randint(
                self.layout.outer_margin,
                self.layout.height
                - self.layout.outer_margin,
            )
            radius = randomizer.choice((1, 1, 1, 2))

            draw.ellipse(
                (
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                ),
                fill=(
                    255,
                    213,
                    235,
                    randomizer.randint(25, 80),
                ),
            )

        return image

    def _draw_outer_frame(
        self,
        image: Image.Image,
    ) -> None:
        margin = self.layout.outer_margin
        box = (
            margin,
            margin,
            self.layout.width - margin,
            self.layout.height - margin,
        )

        shadow_box = (
            box[0] + 8,
            box[1] + 13,
            box[2] + 8,
            box[3] + 13,
        )

        shadow = rounded_layer(
            image.size,
            shadow_box,
            radius=42,
            fill=self.palette.shadow,
            blur=16,
        )
        image.alpha_composite(shadow)

        panel = rounded_layer(
            image.size,
            box,
            radius=42,
            fill=(34, 15, 42, 178),
            outline=self.palette.panel_border,
            width=3,
        )
        image.alpha_composite(panel)

        inner_box = (
            margin + 13,
            margin + 13,
            self.layout.width - margin - 13,
            self.layout.height - margin - 13,
        )

        inner_line = rounded_layer(
            image.size,
            inner_box,
            radius=34,
            fill=(0, 0, 0, 0),
            outline=(246, 178, 210, 58),
            width=2,
        )
        image.alpha_composite(inner_line)

    def _draw_decorations(
        self,
        image: Image.Image,
    ) -> None:
        layer = Image.new(
            "RGBA",
            image.size,
            (0, 0, 0, 0),
        )
        draw = ImageDraw.Draw(layer)

        # Branches fleuries inspirées du thème de référence.
        draw_flowering_branch(
            draw,
            [
                (62, 210),
                (95, 177),
                (132, 153),
                (173, 127),
                (220, 113),
                (268, 86),
            ],
            palette=self.palette,
            seed=1201,
        )
        draw_flowering_branch(
            draw,
            [
                (1538, 185),
                (1502, 154),
                (1460, 128),
                (1415, 108),
                (1365, 87),
                (1325, 64),
            ],
            palette=self.palette,
            seed=1202,
        )

        # Petites branches en bas, orientées vers le centre.
        draw_flowering_branch(
            draw,
            [
                (65, 865),
                (105, 890),
                (155, 907),
                (208, 924),
            ],
            palette=self.palette,
            seed=1203,
        )
        draw_flowering_branch(
            draw,
            [
                (1535, 862),
                (1494, 888),
                (1447, 907),
                (1395, 924),
            ],
            palette=self.palette,
            seed=1204,
        )

        # Flocons décoratifs.
        snowflakes = (
            (343, 92, 18),
            (1230, 106, 15),
            (92, 420, 13),
            (1506, 398, 18),
            (88, 681, 17),
            (1512, 700, 12),
            (332, 944, 13),
            (1278, 943, 16),
        )

        for x, y, radius in snowflakes:
            draw_snowflake(
                draw,
                (x, y),
                radius=radius,
                fill=(247, 190, 216, 145),
                width=2,
            )

        # Étoiles et scintillements.
        stars = (
            (405, 133, 12),
            (1178, 159, 10),
            (1420, 244, 9),
            (189, 253, 8),
            (77, 575, 9),
            (1530, 560, 10),
            (395, 919, 8),
            (1198, 926, 10),
        )

        for index, (x, y, radius) in enumerate(stars):
            draw_star(
                draw,
                (x, y),
                outer_radius=radius,
                inner_radius=max(2, radius // 4),
                fill=(
                    255,
                    215,
                    236,
                    175,
                ),
                points=4,
                rotation=index * 0.15,
            )

        # Fleurs isolées.
        for x, y, radius in (
            (315, 74, 10),
            (1280, 72, 9),
            (97, 316, 8),
            (1499, 299, 10),
            (275, 942, 9),
            (1335, 941, 8),
        ):
            draw_flower(
                draw,
                (x, y),
                radius=radius,
                palette=self.palette,
                rotation=(x + y) / 500,
            )

        image.alpha_composite(layer)

    def _draw_header(
        self,
        image: Image.Image,
        state: CalendarState,
        display_name: str,
        avatar_bytes: bytes | None,
        *,
        preview: bool,
    ) -> None:
        draw = ImageDraw.Draw(image)
        header_top = 78
        emblem_center = (800, 142)

        add_soft_glow(
            image,
            emblem_center,
            95,
            (237, 133, 183, 50),
        )

        draw_fox_emblem(
            image,
            emblem_center,
            size=135,
            palette=self.palette,
            project_root=self.project_root,
        )

        title = truncate(
            state.campaign.title.upper(),
            34,
        )

        # Titre à gauche du renard.
        draw_centered_text(
            draw,
            (
                260,
                header_top,
                710,
                header_top + 72,
            ),
            title,
            font=self.title_font,
            fill=self.palette.pink_white,
            stroke_width=2,
            stroke_fill=self.palette.plum,
        )

        # Année et identité à droite.
        draw_centered_text(
            draw,
            (
                890,
                header_top + 2,
                1345,
                header_top + 67,
            ),
            str(state.campaign.year),
            font=self.title_font,
            fill=self.palette.pink_light,
            stroke_width=2,
            stroke_fill=self.palette.plum,
        )

        member_name = truncate(
            display_name,
            24,
        )

        self._draw_member_identity(
            image,
            member_name,
            avatar_bytes,
        )

        if preview:
            preview_box = (
                685,
                226,
                915,
                260,
            )

            draw.rounded_rectangle(
                preview_box,
                radius=14,
                fill=(229, 144, 179, 42),
                outline=(247, 186, 211, 120),
                width=1,
            )

            draw_centered_text(
                draw,
                preview_box,
                "MODE APERÇU",
                font=self.small_font,
                fill=self.palette.pink_light,
            )

    def _draw_member_identity(
        self,
        image: Image.Image,
        member_name: str,
        avatar_bytes: bytes | None,
    ) -> None:
        draw = ImageDraw.Draw(image)

        avatar_center = (520, 211)
        avatar_size = 50

        avatar = self._prepare_avatar(
            avatar_bytes,
            avatar_size,
        )

        if avatar is not None:
            border_radius = avatar_size // 2 + 4

            draw.ellipse(
                (
                    avatar_center[0] - border_radius,
                    avatar_center[1] - border_radius,
                    avatar_center[0] + border_radius,
                    avatar_center[1] + border_radius,
                ),
                fill=self.palette.pink,
            )

            image.alpha_composite(
                avatar,
                (
                    avatar_center[0] - avatar_size // 2,
                    avatar_center[1] - avatar_size // 2,
                ),
            )
            text_left = 558
        else:
            # Petit médaillon avec une patte simplifiée.
            radius = avatar_size // 2

            draw.ellipse(
                (
                    avatar_center[0] - radius,
                    avatar_center[1] - radius,
                    avatar_center[0] + radius,
                    avatar_center[1] + radius,
                ),
                fill=self.palette.plum_light,
                outline=self.palette.pink,
                width=3,
            )

            self._draw_paw(
                draw,
                avatar_center,
                size=26,
            )
            text_left = 558

        draw.text(
            (text_left, 192),
            member_name,
            font=self.member_font,
            fill=self.palette.white,
            stroke_width=1,
            stroke_fill=self.palette.plum,
        )

        draw.text(
            (text_left, 226),
            "Calendrier personnel",
            font=self.small_font,
            fill=self.palette.muted,
        )

    def _prepare_avatar(
        self,
        avatar_bytes: bytes | None,
        size: int,
    ) -> Image.Image | None:
        if not avatar_bytes:
            return None

        try:
            with Image.open(
                io.BytesIO(avatar_bytes)
            ) as source:
                avatar = source.convert("RGBA")
                avatar = ImageOps.fit(
                    avatar,
                    (size, size),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
        except (OSError, ValueError):
            logger.warning(
                "Impossible de lire l'avatar du membre"
            )
            return None

        mask = Image.new(
            "L",
            (size, size),
            0,
        )
        mask_draw = ImageDraw.Draw(mask)

        mask_draw.ellipse(
            (0, 0, size - 1, size - 1),
            fill=255,
        )
        avatar.putalpha(mask)

        return avatar

    def _draw_paw(
        self,
        draw: ImageDraw.ImageDraw,
        center: tuple[int, int],
        *,
        size: int,
    ) -> None:
        cx, cy = center
        colour = self.palette.pink_white

        pad_width = round(size * 0.58)
        pad_height = round(size * 0.52)

        draw.ellipse(
            (
                cx - pad_width // 2,
                cy - round(size * 0.05),
                cx + pad_width // 2,
                cy + pad_height,
            ),
            fill=colour,
        )

        toe_radius = max(2, size // 7)

        for offset_x, offset_y in (
            (-round(size * 0.28), -round(size * 0.23)),
            (-round(size * 0.09), -round(size * 0.34)),
            (round(size * 0.12), -round(size * 0.34)),
            (round(size * 0.30), -round(size * 0.20)),
        ):
            draw.ellipse(
                (
                    cx + offset_x - toe_radius,
                    cy + offset_y - toe_radius,
                    cx + offset_x + toe_radius,
                    cy + offset_y + toe_radius,
                ),
                fill=colour,
            )

    def _draw_grid(
        self,
        image: Image.Image,
        state: CalendarState,
    ) -> None:
        if (
            len(state.campaign.day_order) != 24
            or set(state.campaign.day_order)
            != set(range(1, 25))
        ):
            day_order = tuple(range(1, 25))
        else:
            day_order = state.campaign.day_order

        for position, day in enumerate(day_order):
            x, y = self.layout.card_position(position)

            if day in state.opened_days:
                status = "opened"
            elif day in state.available_days:
                status = (
                    "today"
                    if day == state.current_day
                    else "catchup"
                )
            elif day in state.missed_days:
                status = "missed"
            else:
                status = "future"

            self._draw_day_card(
                image,
                day=day,
                x=x,
                y=y,
                status=status,
            )

    def _draw_day_card(
        self,
        image: Image.Image,
        *,
        day: int,
        x: int,
        y: int,
        status: str,
    ) -> None:
        width = self.layout.card_width
        height = self.layout.card_height
        radius = self.layout.card_radius

        card_box = (
            x,
            y,
            x + width,
            y + height,
        )

        shadow_box = (
            x + 5,
            y + 8,
            x + width + 5,
            y + height + 8,
        )

        shadow = rounded_layer(
            image.size,
            shadow_box,
            radius=radius,
            fill=self.palette.shadow,
            blur=8,
        )
        image.alpha_composite(shadow)

        if status == "opened":
            card_fill = (39, 72, 65, 215)
            border = (
                *self.palette.opened,
                220,
            )
            border_width = 3
        elif status == "today":
            card_fill = (91, 42, 82, 238)
            border = (
                *self.palette.available,
                255,
            )
            border_width = 5

            add_soft_glow(
                image,
                (
                    x + width // 2,
                    y + height // 2,
                ),
                105,
                (255, 146, 208, 43),
            )
        elif status == "catchup":
            card_fill = (75, 39, 72, 225)
            border = (
                *self.palette.gold_rose,
                210,
            )
            border_width = 3
        elif status == "missed":
            card_fill = (52, 29, 53, 220)
            border = (
                *self.palette.missed,
                175,
            )
            border_width = 3
        else:
            card_fill = (42, 27, 48, 205)
            border = (
                *self.palette.locked,
                125,
            )
            border_width = 2

        panel = rounded_layer(
            image.size,
            card_box,
            radius=radius,
            fill=card_fill,
            outline=border,
            width=border_width,
        )
        image.alpha_composite(panel)

        draw = ImageDraw.Draw(image)

        # Numéro dans le coin supérieur gauche.
        number_circle = (
            x + 13,
            y + 12,
            x + 61,
            y + 60,
        )

        if day == 24:
            number_fill = (
                *self.palette.gold_rose,
                240,
            )
            number_text = self.palette.plum
        elif status == "opened":
            number_fill = (
                *self.palette.opened,
                205,
            )
            number_text = self.palette.background_top
        elif status == "today":
            number_fill = (
                *self.palette.available,
                235,
            )
            number_text = self.palette.plum
        else:
            number_fill = (
                *self.palette.plum_light,
                190,
            )
            number_text = self.palette.pink_white

        draw.ellipse(
            number_circle,
            fill=number_fill,
            outline=(
                255,
                232,
                244,
                130,
            ),
            width=2,
        )

        draw_centered_text(
            draw,
            number_circle,
            str(day),
            font=self.day_font,
            fill=number_text,
            vertical_offset=-1,
        )

        gift_left = x + 83
        gift_top = y + 37
        gift_right = x + 159
        gift_bottom = y + 112

        draw_gift(
            draw,
            (
                gift_left,
                gift_top,
                gift_right,
                gift_bottom,
            ),
            palette=self.palette,
            opened=status == "opened",
            special=day == 24,
            muted=status in {"future", "missed"},
        )

        # Indicateur d'état placé à droite du cadeau.
        indicator_center = (
            x + 178,
            y + 78,
        )

        if status == "opened":
            draw_check(
                draw,
                indicator_center,
                size=31,
                colour=self.palette.opened,
                width=7,
            )
        elif status == "future":
            draw_lock(
                draw,
                (
                    indicator_center[0],
                    indicator_center[1] - 8,
                ),
                size=27,
                colour=self.palette.locked,
            )
        elif status == "missed":
            draw_cross(
                draw,
                indicator_center,
                size=27,
                colour=self.palette.missed,
                width=6,
            )
        elif status in {"today", "catchup"}:
            draw_star(
                draw,
                indicator_center,
                outer_radius=17,
                inner_radius=5,
                fill=self.palette.available,
                points=4,
                rotation=math.pi / 4,
            )

        label, label_colour = self._status_label(status)

        label_box = (
            x + 14,
            y + height - 31,
            x + width - 14,
            y + height - 7,
        )

        draw_centered_text(
            draw,
            label_box,
            label,
            font=self.status_font,
            fill=label_colour,
        )

        if day == 24:
            # Petites étincelles propres à la dernière case.
            draw_star(
                draw,
                (x + width - 30, y + 25),
                outer_radius=10,
                inner_radius=3,
                fill=self.palette.pink_white,
                points=4,
                rotation=0.2,
            )
            draw_star(
                draw,
                (x + width - 54, y + 17),
                outer_radius=6,
                inner_radius=2,
                fill=self.palette.gold_rose,
                points=4,
                rotation=0.8,
            )

    def _status_label(
        self,
        status: str,
    ) -> tuple[str, tuple[int, int, int]]:
        if status == "opened":
            return "OUVERTE", self.palette.opened

        if status == "today":
            return "DISPONIBLE", self.palette.available

        if status == "catchup":
            return "À RATTRAPER", self.palette.gold_rose

        if status == "missed":
            return "MANQUÉE", self.palette.missed

        return "VERROUILLÉE", self.palette.muted

    def _draw_footer(
        self,
        image: Image.Image,
        state: CalendarState,
    ) -> None:
        draw = ImageDraw.Draw(image)

        opened_count = len(state.opened_days)
        missed_count = len(state.missed_days)

        footer_box = (
            370,
            954,
            1230,
            986,
        )

        stats = (
            f"{opened_count}/24 cases ouvertes"
            f"   •   {missed_count} manquée(s)"
            f"   •   {state.total_points} points"
        )

        draw_centered_text(
            draw,
            footer_box,
            stats,
            font=self.stats_font,
            fill=self.palette.pink_light,
        )

        draw.text(
            (83, 960),
            "CLAN RENARD",
            font=self.small_font,
            fill=self.palette.muted,
        )

        if state.current_day is not None:
            day_message = (
                f"Jour {state.current_day}"
            )
        elif state.today < state.campaign.start_date:
            day_message = "Bientôt disponible"
        else:
            day_message = "Campagne terminée"

        right_box = draw.textbbox(
            (0, 0),
            day_message,
            font=self.small_font,
        )
        text_width = right_box[2] - right_box[0]

        draw.text(
            (
                self.layout.width - 83 - text_width,
                960,
            ),
            day_message,
            font=self.small_font,
            fill=self.palette.muted,
        )
