from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


Color = tuple[int, int, int]
ColorAlpha = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class AdventPalette:
    background_top: Color = (24, 12, 32)
    background_bottom: Color = (55, 26, 59)
    background_glow: ColorAlpha = (202, 89, 145, 54)

    panel: ColorAlpha = (43, 22, 51, 225)
    panel_light: ColorAlpha = (72, 35, 72, 220)
    panel_border: ColorAlpha = (225, 131, 174, 175)

    pink_dark: Color = (151, 70, 111)
    pink: Color = (229, 144, 179)
    pink_light: Color = (247, 186, 211)
    pink_white: Color = (255, 237, 247)

    plum: Color = (80, 37, 78)
    plum_light: Color = (117, 56, 101)

    gold_rose: Color = (234, 167, 177)
    white: Color = (255, 248, 252)
    muted: Color = (199, 169, 192)

    available: Color = (255, 171, 214)
    opened: Color = (123, 211, 164)
    missed: Color = (208, 89, 117)
    locked: Color = (111, 83, 116)

    shadow: ColorAlpha = (4, 1, 8, 115)
    transparent: ColorAlpha = (0, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class AdventLayout:
    width: int = 1600
    height: int = 1000

    outer_margin: int = 54
    header_height: int = 210

    grid_x: int = 120
    grid_y: int = 270

    card_width: int = 205
    card_height: int = 145

    column_gap: int = 25
    row_gap: int = 25

    columns: int = 6
    rows: int = 4

    card_radius: int = 28

    @property
    def grid_width(self) -> int:
        return (
            self.columns * self.card_width
            + (self.columns - 1) * self.column_gap
        )

    @property
    def grid_height(self) -> int:
        return (
            self.rows * self.card_height
            + (self.rows - 1) * self.row_gap
        )

    def card_position(
        self,
        position: int,
    ) -> tuple[int, int]:
        if not 0 <= position < 24:
            raise ValueError(
                "La position d'une case doit être comprise entre 0 et 23."
            )

        column = position % self.columns
        row = position // self.columns

        x = self.grid_x + column * (
            self.card_width + self.column_gap
        )
        y = self.grid_y + row * (
            self.card_height + self.row_gap
        )

        return x, y


PALETTE = AdventPalette()
LAYOUT = AdventLayout()


def _font_candidates(
    project_root: Path,
    *,
    bold: bool,
) -> list[Path]:
    custom_name = "title.ttf" if bold else "regular.ttf"

    candidates = [
        (
            project_root
            / "assets"
            / "advent"
            / "fonts"
            / custom_name
        ),
    ]

    if bold:
        candidates.extend(
            [
                Path(
                    "/usr/share/fonts/truetype/dejavu/"
                    "DejaVuSans-Bold.ttf"
                ),
                Path("C:/Windows/Fonts/arialbd.ttf"),
                Path(
                    "/System/Library/Fonts/Supplemental/"
                    "Arial Bold.ttf"
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

    return candidates


def load_font(
    project_root: Path,
    size: int,
    *,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Charge d'abord une police personnalisée déposée dans assets/.

    Si aucune police personnalisée n'est présente, une police système
    courante est utilisée. Le bot reste donc fonctionnel sans asset.
    """
    for candidate in _font_candidates(
        project_root,
        bold=bold,
    ):
        if not candidate.exists():
            continue

        try:
            return ImageFont.truetype(
                str(candidate),
                size=size,
            )
        except OSError:
            continue

    try:
        return ImageFont.truetype(
            "DejaVuSans-Bold.ttf"
            if bold
            else "DejaVuSans.ttf",
            size=size,
        )
    except OSError:
        return ImageFont.load_default()
