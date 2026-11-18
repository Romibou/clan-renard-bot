from __future__ import annotations

import asyncio
import io
import logging
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from bot.core.bot import ClanRenardBot


LOGGER = logging.getLogger(__name__)

PROFILE_WIDTH = 1200
PROFILE_HEIGHT = 500

PROFILE_COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")

HEX_COLOR_PATTERN = re.compile(
    r"^#?[0-9a-fA-F]{6}$"
)

IDENTIFIER_PATTERN = re.compile(
    r"^[a-z0-9_-]{1,50}$"
)

COSMETIC_TYPES = (
    "title",
    "badge",
    "background",
    "frame",
    "effect",
)

CosmeticType = Literal[
    "title",
    "badge",
    "background",
    "frame",
    "effect",
]

COSMETIC_LABELS = {
    "title": "Titre",
    "badge": "Badge",
    "background": "Arrière-plan",
    "frame": "Cadre",
    "effect": "Effet",
}

EQUIPPED_COLUMNS = {
    "title": "equipped_title",
    "badge": "equipped_badge",
    "background": "equipped_background",
    "frame": "equipped_frame",
    "effect": "equipped_effect",
}


def success_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=SUCCESS_COLOR,
    )


def error_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=ERROR_COLOR,
    )


def normalize_color(
    value: str,
) -> str | None:
    normalized = value.strip()

    if not normalized:
        return None

    if not normalized.startswith("#"):
        normalized = f"#{normalized}"

    if not HEX_COLOR_PATTERN.fullmatch(
        normalized
    ):
        return None

    return normalized.upper()


def color_tuple(
    value: str,
) -> tuple[int, int, int]:
    normalized = (
        normalize_color(value)
        or "#E268A1"
    )

    return (
        int(normalized[1:3], 16),
        int(normalized[3:5], 16),
        int(normalized[5:7], 16),
    )


def truncate(
    value: str,
    maximum: int,
) -> str:
    if len(value) <= maximum:
        return value

    return value[: maximum - 1] + "…"


def font(
    size: int,
    *,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[str] = []

    if bold:
        candidates.extend(
            [
                (
                    "/usr/share/fonts/truetype/dejavu/"
                    "DejaVuSans-Bold.ttf"
                ),
                (
                    "/usr/share/fonts/truetype/liberation2/"
                    "LiberationSans-Bold.ttf"
                ),
                "C:/Windows/Fonts/arialbd.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                (
                    "/usr/share/fonts/truetype/dejavu/"
                    "DejaVuSans.ttf"
                ),
                (
                    "/usr/share/fonts/truetype/liberation2/"
                    "LiberationSans-Regular.ttf"
                ),
                str(
                    Path(__file__).resolve().parents[2]
                    / "assets"
                    / "fonts"
                    / "NotoSans-Regular.ttf"
                ),
                "C:/Windows/Fonts/arial.ttf",
            ]
        )

    for candidate in candidates:
        try:
            return ImageFont.truetype(
                candidate,
                size=size,
            )
        except OSError:
            continue

    return ImageFont.load_default()


def fit_layer(
    layer: Image.Image,
    size: tuple[int, int],
) -> Image.Image:
    """
    Adapte un calque transparent (cadre, effet) à la carte.

    Contrairement au fond, il n'est pas recadré : un cadre en 1400x500
    perdrait ses bords gauche et droit. Il est donc légèrement étiré
    pour occuper exactement la carte.
    """
    if layer.size == size:
        return layer

    return layer.resize(
        size,
        Image.Resampling.LANCZOS,
    )


def readability_overlay(
    size: tuple[int, int],
) -> Image.Image:
    """
    Voile sombre en dégradé derrière le texte, pour qu'il reste
    lisible sur un fond illustré sans masquer toute l'image.
    """
    width, height = size
    overlay = Image.new("L", (width, 1), 0)
    pixels = overlay.load()

    def smooth(start: float, end: float, value: float) -> float:
        ratio = min(1.0, max(0.0, (value - start) / (end - start)))
        return ratio * ratio * (3 - 2 * ratio)

    for x in range(width):
        # Léger voile sur l'avatar, montée douce vers la zone du
        # texte, puis redescente vers le bord droit (badge).
        rise = smooth(180, 520, x)
        fall = smooth(880, width, x)
        alpha = 55 + 125 * rise - 70 * fall
        pixels[x, 0] = int(alpha)

    mask = overlay.resize((width, height))
    shade = Image.new("RGBA", size, (8, 10, 18, 255))
    shade.putalpha(mask)

    return shade


# Bordure dessinée par défaut quand aucun cadre n'est équipé.
DEFAULT_BORDER_BOX = (35, 35, 1165, 465)
DEFAULT_BORDER_RADIUS = 40


def detect_frame_shape(
    frame: Image.Image,
) -> tuple[tuple[int, int, int, int], int] | None:
    """
    Contour extérieur d'un cadre : rectangle occupé par ses pixels
    visibles et rayon de ses coins. None si le cadre est vide.
    """
    visible = frame.getchannel("A").point(
        lambda alpha: 255 if alpha > 60 else 0
    )
    box = visible.getbbox()

    if box is None:
        return None

    left, top, right, bottom = box
    # Sur la ligne du haut du cadre, le trait commence après l'arrondi
    # du coin : cet écart donne une bonne estimation du rayon.
    row = top + 1
    first = next(
        (
            x
            for x in range(left, right)
            if visible.getpixel((x, row))
        ),
        left,
    )
    radius = max(8, min(80, first - left))

    return (left, top, right, bottom), radius


def shape_card(
    card: Image.Image,
    frame: Image.Image | None,
) -> Image.Image:
    """
    Découpe la carte selon son contour visible (le cadre équipé, ou la
    bordure par défaut) avec des coins arrondis transparents.

    Sans cela, le fond dépassait autour du cadre et Discord rognait
    les coins de l'image.
    """
    shape = detect_frame_shape(frame) if frame is not None else None

    if shape is None:
        if frame is not None:
            return card

        box, radius = DEFAULT_BORDER_BOX, DEFAULT_BORDER_RADIUS
    else:
        box, radius = shape

    left, top, right, bottom = box
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (left, top, right - 1, bottom - 1),
        radius=radius,
        fill=255,
    )

    shaped = card.copy()
    shaped.putalpha(
        ImageChops.multiply(card.getchannel("A"), mask)
    )

    return shaped.crop(box)


def load_rgba_asset(
    assets_root: Path,
    relative_path: str | None,
) -> Image.Image | None:
    if not relative_path:
        return None

    try:
        root = assets_root.resolve()
        target = (
            root / relative_path
        ).resolve()

        if (
            target != root
            and root not in target.parents
        ):
            LOGGER.warning(
                "Chemin d'asset refusé : %s",
                relative_path,
            )
            return None

        if not target.is_file():
            LOGGER.warning(
                (
                    "Asset de profil introuvable : "
                    "chemin reçu=%r, chemin final=%s"
                ),
                relative_path,
                target,
            )
            return None

        with Image.open(target) as image:
            return image.convert("RGBA")

    except (
        OSError,
        ValueError,
    ):
        LOGGER.warning(
            "Impossible de charger l'asset %s",
            relative_path,
            exc_info=True,
        )
        return None


def create_gradient(
    color: tuple[int, int, int],
) -> Image.Image:
    image = Image.new(
        "RGBA",
        (
            PROFILE_WIDTH,
            PROFILE_HEIGHT,
        ),
    )

    pixels = image.load()

    secondary = (
        max(10, color[0] // 3),
        max(10, color[1] // 3),
        max(20, color[2] // 3),
    )

    for y in range(PROFILE_HEIGHT):
        ratio = (
            y
            / max(
                1,
                PROFILE_HEIGHT - 1,
            )
        )

        red = int(
            color[0] * (1 - ratio)
            + secondary[0] * ratio
        )

        green = int(
            color[1] * (1 - ratio)
            + secondary[1] * ratio
        )

        blue = int(
            color[2] * (1 - ratio)
            + secondary[2] * ratio
        )

        for x in range(PROFILE_WIDTH):
            horizontal = (
                x / PROFILE_WIDTH
            )

            modifier = int(
                20 * horizontal
            )

            pixels[x, y] = (
                max(0, red - modifier),
                max(0, green - modifier),
                max(0, blue - modifier),
                255,
            )

    return image


def apply_snow_effect(
    image: Image.Image,
    user_id: int,
) -> None:
    draw = ImageDraw.Draw(
        image,
        "RGBA",
    )

    seed = user_id

    for _ in range(90):
        seed = (
            seed * 1_103_515_245
            + 12_345
        ) & 0x7FFFFFFF

        x = seed % PROFILE_WIDTH

        seed = (
            seed * 1_103_515_245
            + 12_345
        ) & 0x7FFFFFFF

        y = seed % PROFILE_HEIGHT
        radius = 2 + seed % 5
        alpha = 80 + seed % 130

        draw.ellipse(
            (
                x - radius,
                y - radius,
                x + radius,
                y + radius,
            ),
            fill=(
                255,
                255,
                255,
                alpha,
            ),
        )


class ProfileBioModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        cog: ProfileCog,
        owner: discord.Member | discord.User,
        current_bio: str,
        current_color: str,
    ) -> None:
        super().__init__(
            title="Personnaliser mon profil",
            timeout=300,
        )

        self.cog = cog
        self.owner = owner

        self.bio = discord.ui.TextInput(
            label="Phrase personnalisée",
            placeholder=(
                "Exemple : Un renard ne recule jamais."
            ),
            style=discord.TextStyle.paragraph,
            default=current_bio,
            required=False,
            max_length=250,
        )

        self.color = discord.ui.TextInput(
            label="Couleur hexadécimale",
            placeholder="#E268A1",
            default=current_color,
            required=True,
            min_length=6,
            max_length=7,
        )

        self.add_item(self.bio)
        self.add_item(self.color)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        normalized_color = normalize_color(
            str(self.color.value)
        )

        if normalized_color is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Couleur invalide",
                    (
                        "Utilise une couleur hexadécimale.\n"
                        "Exemple : `#E268A1`."
                    ),
                ),
                ephemeral=True,
            )
            return

        bio = str(
            self.bio.value
        ).strip()

        await self.cog.update_profile(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            bio=bio,
            color_hex=normalized_color,
        )

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        await interaction.followup.send(
            embed=success_embed(
                "Profil enregistré",
                (
                    "Ta biographie et ta couleur "
                    "ont été mises à jour."
                ),
            ),
            ephemeral=True,
        )

        await self.cog.send_profile(
            interaction,
            member=self.owner,
            ephemeral=True,
        )


class CosmeticSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        cog: ProfileCog,
        owner_id: int,
        cosmetics: list[Any],
        placeholder: str = "Choisis un cosmétique à équiper…",
        row: int | None = None,
    ) -> None:
        self.cog = cog
        self.owner_id = owner_id

        options: list[
            discord.SelectOption
        ] = []

        for cosmetic in cosmetics[:25]:
            cosmetic_type = str(
                cosmetic["cosmetic_type"]
            )

            identifier = str(
                cosmetic["identifier"]
            )

            label = (
                f"{COSMETIC_LABELS.get(cosmetic_type, cosmetic_type)}"
                f" — {cosmetic['display_name']}"
            )

            options.append(
                discord.SelectOption(
                    label=truncate(
                        label,
                        100,
                    ),
                    value=(
                        f"{cosmetic_type}:"
                        f"{identifier}"
                    ),
                    description=truncate(
                        (
                            str(
                                cosmetic[
                                    "description"
                                ]
                            )
                            or "Cosmétique de profil"
                        ),
                        100,
                    ),
                )
            )

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if (
            interaction.user.id
            != self.owner_id
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Inventaire personnel",
                    (
                        "Cet inventaire ne "
                        "t'appartient pas."
                    ),
                ),
                ephemeral=True,
            )
            return

        try:
            cosmetic_type, identifier = (
                self.values[0].split(
                    ":",
                    maxsplit=1,
                )
            )
        except (
            IndexError,
            ValueError,
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Sélection invalide",
                    (
                        "Impossible de lire "
                        "le cosmétique."
                    ),
                ),
                ephemeral=True,
            )
            return

        try:
            cosmetic = (
                await self.cog.equip_cosmetic(
                    guild_id=interaction.guild_id,
                    user_id=interaction.user.id,
                    cosmetic_type=cosmetic_type,
                    identifier=identifier,
                )
            )
        except ValueError as error:
            await interaction.response.send_message(
                embed=error_embed(
                    "Équipement impossible",
                    str(error),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Cosmétique équipé",
                (
                    f"**{cosmetic['display_name']}** est "
                    "maintenant visible sur ton profil.\n\n"
                    "Utilise le bouton **Actualiser** pour "
                    "voir le résultat."
                ),
            ),
            ephemeral=True,
        )


class CosmeticInventoryView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        cog: ProfileCog,
        owner_id: int,
        cosmetics: list[Any],
    ) -> None:
        super().__init__(
            timeout=300,
        )

        self.cog = cog
        self.owner_id = owner_id

        # Un menu Discord contient 25 choix au maximum : au-delà,
        # l'inventaire est réparti sur plusieurs menus (4 lignes,
        # la dernière étant réservée au bouton).
        pages = [
            cosmetics[start:start + 25]
            for start in range(0, len(cosmetics), 25)
        ][:4]

        self.remove_item(self.reset_cosmetics)

        for index, page in enumerate(pages):
            placeholder = "Choisis un cosmétique à équiper…"

            if len(pages) > 1:
                first = index * 25 + 1
                last = index * 25 + len(page)
                placeholder = (
                    f"Cosmétiques {first} à {last}…"
                )

            self.add_item(
                CosmeticSelect(
                    cog=cog,
                    owner_id=owner_id,
                    cosmetics=page,
                    placeholder=placeholder,
                    row=index,
                )
            )

        # Le bouton est replacé sous le dernier menu.
        self.reset_cosmetics.row = len(pages)
        self.add_item(self.reset_cosmetics)

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if (
            interaction.user.id
            == self.owner_id
        ):
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Inventaire personnel",
                (
                    "Cet inventaire appartient "
                    "à un autre membre."
                ),
            ),
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Tout retirer",
        emoji="🧹",
        style=discord.ButtonStyle.danger,
        row=1,
    )
    async def reset_cosmetics(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.reset_cosmetics(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Cosmétiques retirés",
                (
                    "Ton titre, ton badge, ton arrière-plan, "
                    "ton cadre et ton effet ont été retirés."
                ),
            ),
            ephemeral=True,
        )


class ProfileView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: ProfileCog,
        owner: discord.Member | discord.User,
    ) -> None:
        super().__init__(
            timeout=600,
        )

        self.cog = cog
        self.owner = owner

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if (
            interaction.user.id
            == self.owner.id
        ):
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Profil personnel",
                (
                    "Tu ne peux pas modifier "
                    "le profil d'un autre membre."
                ),
            ),
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Personnaliser",
        emoji="✏️",
        style=discord.ButtonStyle.primary,
    )
    async def customize(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        profile = await self.cog.get_profile(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_modal(
            ProfileBioModal(
                cog=self.cog,
                owner=self.owner,
                current_bio=str(
                    profile["bio"]
                ),
                current_color=str(
                    profile["color_hex"]
                ),
            )
        )

    @discord.ui.button(
        label="Inventaire",
        emoji="🎒",
        style=discord.ButtonStyle.secondary,
    )
    async def inventory(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cosmetics = (
            await self.cog.get_owned_cosmetics(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            )
        )

        if not cosmetics:
            await interaction.response.send_message(
                embed=error_embed(
                    "Inventaire vide",
                    (
                        "Tu ne possèdes encore aucun cosmétique.\n"
                        "Tu pourras en obtenir dans la boutique "
                        "ou pendant les événements."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎒 Inventaire du profil",
                description=(
                    "Choisis le cosmétique que "
                    "tu souhaites équiper."
                ),
                color=PROFILE_COLOR,
            ),
            view=CosmeticInventoryView(
                cog=self.cog,
                owner_id=interaction.user.id,
                cosmetics=cosmetics,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Collections",
        emoji="📚",
        style=discord.ButtonStyle.secondary,
    )
    async def show_collections(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        collection_cog = interaction.client.get_cog("CollectionCog")

        if collection_cog is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Indisponible",
                    "Le module des collections n'est pas chargé.",
                ),
                ephemeral=True,
            )
            return

        await collection_cog.send_collections(
            interaction,
            self.owner,
        )

    @discord.ui.button(
        label="Actualiser",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
    )
    async def refresh(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        await self.cog.send_profile(
            interaction,
            member=self.owner,
            ephemeral=True,
        )


class CreateCosmeticModal(
    discord.ui.Modal
):
    def __init__(
        self,
        *,
        cog: ProfileCog,
    ) -> None:
        super().__init__(
            title="Créer un cosmétique",
            timeout=600,
        )

        self.cog = cog

        self.identifier = discord.ui.TextInput(
            label="Identifiant",
            placeholder="badge-noel-2026",
            max_length=50,
        )

        self.cosmetic_type = discord.ui.TextInput(
            label="Type",
            placeholder=(
                "title, badge, background, frame ou effect"
            ),
            max_length=20,
        )

        self.display_name = discord.ui.TextInput(
            label="Nom affiché",
            placeholder="Flocon de Noël",
            max_length=100,
        )

        self.asset_path = discord.ui.TextInput(
            label="Chemin de l'image",
            placeholder="badges/flocon-noel.png",
            required=False,
            max_length=250,
        )

        self.value = discord.ui.TextInput(
            label="Valeur facultative",
            placeholder=(
                "Texte du titre ou identifiant d'effet"
            ),
            required=False,
            max_length=250,
        )

        self.add_item(self.identifier)
        self.add_item(self.cosmetic_type)
        self.add_item(self.display_name)
        self.add_item(self.asset_path)
        self.add_item(self.value)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        identifier = str(
            self.identifier.value
        ).strip().lower()

        cosmetic_type = str(
            self.cosmetic_type.value
        ).strip().lower()

        display_name = str(
            self.display_name.value
        ).strip()

        asset_path = str(
            self.asset_path.value
        ).strip()

        value = str(
            self.value.value
        ).strip()

        if not IDENTIFIER_PATTERN.fullmatch(
            identifier
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Identifiant invalide",
                    (
                        "Utilise uniquement des lettres minuscules, "
                        "des chiffres, `_` ou `-`."
                    ),
                ),
                ephemeral=True,
            )
            return

        if cosmetic_type not in COSMETIC_TYPES:
            await interaction.response.send_message(
                embed=error_embed(
                    "Type invalide",
                    (
                        "Types autorisés : `title`, `badge`, "
                        "`background`, `frame`, `effect`."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not display_name:
            await interaction.response.send_message(
                embed=error_embed(
                    "Nom invalide",
                    "Le nom ne peut pas être vide.",
                ),
                ephemeral=True,
            )
            return

        cosmetic = await self.cog.create_cosmetic(
            guild_id=interaction.guild_id,
            identifier=identifier,
            cosmetic_type=cosmetic_type,
            display_name=display_name,
            description=(
                f"Cosmétique {display_name}"
            ),
            asset_path=asset_path or None,
            value=value or None,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Cosmétique créé",
                (
                    f"**{cosmetic['display_name']}** a été créé.\n\n"
                    f"Identifiant : `{cosmetic['identifier']}`\n"
                    f"Type : `{cosmetic['cosmetic_type']}`"
                ),
            ),
            ephemeral=True,
        )


class AdminCosmeticSelect(
    discord.ui.Select
):
    def __init__(
        self,
        *,
        cosmetics: list[Any],
        placeholder: str = "Choisis le cosmétique…",
        row: int = 1,
    ) -> None:
        self.selected_cosmetic_id: int | None = None

        options = [
            discord.SelectOption(
                label=truncate(
                    str(
                        cosmetic[
                            "display_name"
                        ]
                    ),
                    100,
                ),
                value=str(
                    cosmetic["id"]
                ),
                description=truncate(
                    (
                        f"{COSMETIC_LABELS.get(str(cosmetic['cosmetic_type']))}"
                        f" • {cosmetic['identifier']}"
                    ),
                    100,
                ),
            )
            for cosmetic in cosmetics[:25]
        ]

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        self.selected_cosmetic_id = int(
            self.values[0]
        )

        # Le dernier menu utilisé fait foi lorsque les cosmétiques
        # sont répartis sur plusieurs menus.
        if self.view is not None:
            self.view.selected_cosmetic_id = (
                self.selected_cosmetic_id
            )

        await interaction.response.defer()


class AdminMemberSelect(
    discord.ui.UserSelect
):
    def __init__(self) -> None:
        self.selected_user_id: int | None = None

        super().__init__(
            placeholder="Choisis le membre…",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        self.selected_user_id = (
            self.values[0].id
        )

        await interaction.response.defer()


class GrantCosmeticView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        cog: ProfileCog,
        guild_id: int,
        cosmetics: list[Any],
    ) -> None:
        super().__init__(
            timeout=300,
        )

        self.cog = cog
        self.guild_id = guild_id

        self.member_select = (
            AdminMemberSelect()
        )

        self.selected_cosmetic_id: int | None = None

        self.add_item(
            self.member_select
        )

        # Un menu Discord contient 25 choix au maximum : au-delà,
        # les cosmétiques sont répartis sur plusieurs menus
        # (lignes 1 à 3, la ligne 4 étant celle du bouton).
        pages = [
            cosmetics[start:start + 25]
            for start in range(0, len(cosmetics), 25)
        ][:3]

        for index, page in enumerate(pages):
            placeholder = "Choisis le cosmétique…"

            if len(pages) > 1:
                first = index * 25 + 1
                last = index * 25 + len(page)
                placeholder = (
                    f"Cosmétiques {first} à {last}…"
                )

            self.add_item(
                AdminCosmeticSelect(
                    cosmetics=page,
                    placeholder=placeholder,
                    row=index + 1,
                )
            )

    @discord.ui.button(
        label="Distribuer",
        emoji="🎁",
        style=discord.ButtonStyle.success,
        row=4,
    )
    async def grant(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        user_id = (
            self.member_select
            .selected_user_id
        )

        cosmetic_id = self.selected_cosmetic_id

        if (
            user_id is None
            or cosmetic_id is None
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Sélection incomplète",
                    (
                        "Choisis un membre et un cosmétique "
                        "avant de valider."
                    ),
                ),
                ephemeral=True,
            )
            return

        cosmetic = (
            await self.cog.grant_cosmetic(
                guild_id=self.guild_id,
                user_id=user_id,
                cosmetic_id=cosmetic_id,
                source="admin",
            )
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Cosmétique distribué",
                (
                    f"**{cosmetic['display_name']}** a été "
                    f"ajouté à l'inventaire de <@{user_id}>."
                ),
            ),
            ephemeral=True,
        )


class DeleteCosmeticModal(
    discord.ui.Modal,
    title="Supprimer un cosmétique",
):
    identifier = discord.ui.TextInput(
        label="Identifiant du cosmétique",
        placeholder="exemple : badge-noel",
        min_length=1,
        max_length=50,
    )

    def __init__(
        self,
        cog: ProfileCog,
    ) -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                (
                    "❌ Cette action doit être "
                    "utilisée sur un serveur."
                ),
                ephemeral=True,
            )
            return

        try:
            display_name = (
                await self.cog.delete_cosmetic(
                    guild_id=interaction.guild_id,
                    identifier=str(
                        self.identifier.value
                    ),
                )
            )
        except ValueError as error:
            await interaction.response.send_message(
                embed=error_embed(
                    "Cosmétique introuvable",
                    str(error),
                ),
                ephemeral=True,
            )
            return
        except Exception:
            LOGGER.exception(
                (
                    "Impossible de supprimer "
                    "le cosmétique"
                )
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Suppression impossible",
                    (
                        "Une erreur inattendue "
                        "s'est produite."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Cosmétique supprimé",
                (
                    f"Le cosmétique **{display_name}** a été "
                    "désactivé et retiré des profils qui "
                    "l'utilisaient."
                ),
            ),
            ephemeral=True,
        )


class ProfileAdminView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        cog: ProfileCog,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=600,
        )

        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(
        label="Créer un cosmétique",
        emoji="➕",
        style=discord.ButtonStyle.primary,
    )
    async def create_cosmetic_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            CreateCosmeticModal(
                cog=self.cog,
            )
        )

    @discord.ui.button(
        label="Distribuer",
        emoji="🎁",
        style=discord.ButtonStyle.success,
    )
    async def grant_cosmetic_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cosmetics = await self.cog.list_cosmetics(
            guild_id=self.guild_id,
        )

        if not cosmetics:
            await interaction.response.send_message(
                embed=error_embed(
                    "Aucun cosmétique",
                    (
                        "Crée d'abord un cosmétique avec "
                        "**Créer un cosmétique**."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎁 Distribuer un cosmétique",
                description=(
                    "Sélectionne le membre "
                    "puis le cosmétique."
                ),
                color=PROFILE_COLOR,
            ),
            view=GrantCosmeticView(
                cog=self.cog,
                guild_id=self.guild_id,
                cosmetics=cosmetics,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Catalogue",
        emoji="📚",
        style=discord.ButtonStyle.secondary,
    )
    async def catalogue_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        # Tous les cosmétiques par thème, avec nom affiché, ID et prix.
        from bot.shared.cosmetic_catalogue import send_catalogue

        await send_catalogue(interaction)

    @discord.ui.button(
        label="Supprimer un cosmétique",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
    )
    async def delete_cosmetic_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            DeleteCosmeticModal(
                self.cog
            )
        )


class ProfileCog(commands.Cog):
    def __init__(
        self,
        bot: ClanRenardBot,
    ) -> None:
        self.bot = bot

        self.assets_root = (
            bot.settings.project_root
            / "assets"
            / "profile"
        )

        self.assets_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        for directory in (
            "badges",
            "backgrounds",
            "frames",
            "effects",
        ):
            (
                self.assets_root
                / directory
            ).mkdir(
                parents=True,
                exist_ok=True,
            )

    def get_pool(self):
        return (
            self.bot.database
            .require_pool()
        )

    async def initialize_database(
        self,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS member_profiles (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,

                bio VARCHAR(250)
                    NOT NULL DEFAULT '',

                color_hex VARCHAR(7)
                    NOT NULL DEFAULT '#E268A1',

                equipped_title VARCHAR(50),
                equipped_badge VARCHAR(50),
                equipped_background VARCHAR(50),
                equipped_frame VARCHAR(50),
                equipped_effect VARCHAR(50),

                created_at TIMESTAMPTZ
                    NOT NULL DEFAULT NOW(),

                updated_at TIMESTAMPTZ
                    NOT NULL DEFAULT NOW(),

                PRIMARY KEY (
                    guild_id,
                    user_id
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_cosmetics (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT NOT NULL,
                identifier VARCHAR(50) NOT NULL,

                cosmetic_type VARCHAR(20) NOT NULL
                    CHECK (
                        cosmetic_type IN (
                            'title',
                            'badge',
                            'background',
                            'frame',
                            'effect'
                        )
                    ),

                display_name VARCHAR(100) NOT NULL,

                description VARCHAR(250)
                    NOT NULL DEFAULT '',

                asset_path VARCHAR(250),
                value VARCHAR(250),

                enabled BOOLEAN
                    NOT NULL DEFAULT TRUE,

                created_at TIMESTAMPTZ
                    NOT NULL DEFAULT NOW(),

                updated_at TIMESTAMPTZ
                    NOT NULL DEFAULT NOW(),

                UNIQUE (
                    guild_id,
                    identifier
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_inventory (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,

                cosmetic_id BIGINT NOT NULL
                    REFERENCES profile_cosmetics(id)
                    ON DELETE CASCADE,

                source VARCHAR(50)
                    NOT NULL DEFAULT 'unknown',

                acquired_at TIMESTAMPTZ
                    NOT NULL DEFAULT NOW(),

                PRIMARY KEY (
                    guild_id,
                    user_id,
                    cosmetic_id
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS
                profile_inventory_user_idx
            ON profile_inventory (
                guild_id,
                user_id
            )
            """
        )

        LOGGER.info(
            "Tables du système de profils vérifiées"
        )

    async def get_profile(
        self,
        *,
        guild_id: int | None,
        user_id: int,
    ):
        if guild_id is None:
            raise ValueError(
                (
                    "Le profil doit être utilisé "
                    "dans un serveur."
                )
            )

        pool = self.get_pool()

        await pool.execute(
            """
            INSERT INTO member_profiles (
                guild_id,
                user_id
            )
            VALUES ($1, $2)
            ON CONFLICT (
                guild_id,
                user_id
            )
            DO NOTHING
            """,
            guild_id,
            user_id,
        )

        return await pool.fetchrow(
            """
            SELECT
                guild_id,
                user_id,
                bio,
                color_hex,
                equipped_title,
                equipped_badge,
                equipped_background,
                equipped_frame,
                equipped_effect
            FROM member_profiles
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

    async def get_current_daily_streak(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> int:
        """
        Retourne la série quotidienne réellement active.

        La valeur stockée dans daily_members est considérée
        comme expirée si la dernière récompense remonte à
        plus d'un jour dans le fuseau Europe/Paris.
        """
        record = await self.get_pool().fetchrow(
            """
            SELECT
                current_streak,
                last_claim_at
            FROM daily_members
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

        if record is None:
            return 0

        current_streak = max(
            0,
            int(
                record["current_streak"]
                or 0
            ),
        )

        last_claim_at = record[
            "last_claim_at"
        ]

        if (
            current_streak <= 0
            or last_claim_at is None
        ):
            return 0

        current_date = datetime.now(
            PARIS_TIMEZONE
        ).date()

        last_claim_date = (
            last_claim_at.astimezone(
                PARIS_TIMEZONE
            ).date()
        )

        difference = (
            current_date
            - last_claim_date
        ).days

        if difference in {
            0,
            1,
        }:
            return current_streak

        return 0

    async def update_profile(
        self,
        *,
        guild_id: int | None,
        user_id: int,
        bio: str,
        color_hex: str,
    ) -> None:
        if guild_id is None:
            return

        await self.get_profile(
            guild_id=guild_id,
            user_id=user_id,
        )

        await self.get_pool().execute(
            """
            UPDATE member_profiles
            SET
                bio = $3,
                color_hex = $4,
                updated_at = NOW()
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
            bio,
            color_hex,
        )

    async def list_cosmetics(
        self,
        *,
        guild_id: int,
    ) -> list[Any]:
        records = await self.get_pool().fetch(
            """
            SELECT
                id,
                guild_id,
                identifier,
                cosmetic_type,
                display_name,
                description,
                asset_path,
                value
            FROM profile_cosmetics
            WHERE guild_id = $1
              AND enabled = TRUE
            ORDER BY
                cosmetic_type,
                display_name
            LIMIT 75
            """,
            guild_id,
        )

        return list(records)

    async def get_owned_cosmetics(
        self,
        *,
        guild_id: int | None,
        user_id: int,
    ) -> list[Any]:
        if guild_id is None:
            return []

        records = await self.get_pool().fetch(
            """
            SELECT
                cosmetic.id,
                cosmetic.identifier,
                cosmetic.cosmetic_type,
                cosmetic.display_name,
                cosmetic.description,
                cosmetic.asset_path,
                cosmetic.value
            FROM profile_inventory AS inventory
            INNER JOIN profile_cosmetics AS cosmetic
                ON cosmetic.id = inventory.cosmetic_id
            WHERE inventory.guild_id = $1
              AND inventory.user_id = $2
              AND cosmetic.enabled = TRUE
            ORDER BY
                cosmetic.cosmetic_type,
                cosmetic.display_name
            LIMIT 100
            """,
            guild_id,
            user_id,
        )

        return list(records)

    async def create_cosmetic(
        self,
        *,
        guild_id: int | None,
        identifier: str,
        cosmetic_type: str,
        display_name: str,
        description: str,
        asset_path: str | None,
        value: str | None,
    ):
        if guild_id is None:
            raise ValueError(
                "Serveur introuvable."
            )

        if cosmetic_type not in COSMETIC_TYPES:
            raise ValueError(
                "Type de cosmétique invalide."
            )

        return await self.get_pool().fetchrow(
            """
            INSERT INTO profile_cosmetics (
                guild_id,
                identifier,
                cosmetic_type,
                display_name,
                description,
                asset_path,
                value,
                enabled,
                updated_at
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                TRUE,
                NOW()
            )
            ON CONFLICT (
                guild_id,
                identifier
            )
            DO UPDATE SET
                cosmetic_type =
                    EXCLUDED.cosmetic_type,

                display_name =
                    EXCLUDED.display_name,

                description =
                    EXCLUDED.description,

                asset_path =
                    EXCLUDED.asset_path,

                value =
                    EXCLUDED.value,

                enabled = TRUE,
                updated_at = NOW()
            RETURNING
                id,
                identifier,
                cosmetic_type,
                display_name
            """,
            guild_id,
            identifier,
            cosmetic_type,
            display_name,
            description,
            asset_path,
            value,
        )

    async def delete_cosmetic(
        self,
        *,
        guild_id: int,
        identifier: str,
    ) -> str:
        normalized_identifier = (
            identifier
            .strip()
            .lower()
        )

        if not normalized_identifier:
            raise ValueError(
                (
                    "L'identifiant du cosmétique "
                    "est obligatoire."
                )
            )

        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                cosmetic = (
                    await connection.fetchrow(
                        """
                        SELECT
                            id,
                            identifier,
                            display_name,
                            cosmetic_type
                        FROM profile_cosmetics
                        WHERE guild_id = $1
                          AND identifier = $2
                        FOR UPDATE
                        """,
                        guild_id,
                        normalized_identifier,
                    )
                )

                if cosmetic is None:
                    raise ValueError(
                        (
                            "Aucun cosmétique ne possède "
                            "cet identifiant."
                        )
                    )

                cosmetic_id = int(
                    cosmetic["id"]
                )

                display_name = str(
                    cosmetic["display_name"]
                )

                shop_cosmetics_enabled = (
                    await connection.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name =
                                  'advent_shop_items_v2'
                              AND column_name =
                                  'cosmetic_id'
                        )
                        """
                    )
                )

                if shop_cosmetics_enabled:
                    shop_item_records = (
                        await connection.fetch(
                            """
                            SELECT id
                            FROM advent_shop_items_v2
                            WHERE cosmetic_id = $1
                            """,
                            cosmetic_id,
                        )
                    )

                    shop_item_ids = [
                        int(record["id"])
                        for record
                        in shop_item_records
                    ]

                    if shop_item_ids:
                        await connection.execute(
                            """
                            DELETE FROM
                                advent_shop_purchases_v2
                            WHERE item_id =
                                ANY($1::BIGINT[])
                            """,
                            shop_item_ids,
                        )

                        await connection.execute(
                            """
                            DELETE FROM
                                advent_shop_items_v2
                            WHERE id =
                                ANY($1::BIGINT[])
                            """,
                            shop_item_ids,
                        )

                await connection.execute(
                    """
                    UPDATE member_profiles
                    SET
                        equipped_title = CASE
                            WHEN equipped_title = $2
                                THEN NULL
                            ELSE equipped_title
                        END,

                        equipped_badge = CASE
                            WHEN equipped_badge = $2
                                THEN NULL
                            ELSE equipped_badge
                        END,

                        equipped_background = CASE
                            WHEN equipped_background = $2
                                THEN NULL
                            ELSE equipped_background
                        END,

                        equipped_frame = CASE
                            WHEN equipped_frame = $2
                                THEN NULL
                            ELSE equipped_frame
                        END,

                        equipped_effect = CASE
                            WHEN equipped_effect = $2
                                THEN NULL
                            ELSE equipped_effect
                        END,

                        updated_at = NOW()

                    WHERE guild_id = $1
                      AND (
                          equipped_title = $2
                          OR equipped_badge = $2
                          OR equipped_background = $2
                          OR equipped_frame = $2
                          OR equipped_effect = $2
                      )
                    """,
                    guild_id,
                    normalized_identifier,
                )

                await connection.execute(
                    """
                    DELETE FROM profile_inventory
                    WHERE cosmetic_id = $1
                    """,
                    cosmetic_id,
                )

                await connection.execute(
                    """
                    DELETE FROM profile_cosmetics
                    WHERE id = $1
                    """,
                    cosmetic_id,
                )

        return display_name

    async def grant_cosmetic(
        self,
        *,
        guild_id: int,
        user_id: int,
        cosmetic_id: int,
        source: str,
    ):
        cosmetic = await self.get_pool().fetchrow(
            """
            SELECT
                id,
                guild_id,
                identifier,
                display_name
            FROM profile_cosmetics
            WHERE id = $1
              AND guild_id = $2
              AND enabled = TRUE
            """,
            cosmetic_id,
            guild_id,
        )

        if cosmetic is None:
            raise ValueError(
                "Le cosmétique n'existe pas."
            )

        await self.get_pool().execute(
            """
            INSERT INTO profile_inventory (
                guild_id,
                user_id,
                cosmetic_id,
                source
            )
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (
                guild_id,
                user_id,
                cosmetic_id
            )
            DO NOTHING
            """,
            guild_id,
            user_id,
            cosmetic_id,
            source,
        )

        return cosmetic

    async def equip_cosmetic(
        self,
        *,
        guild_id: int | None,
        user_id: int,
        cosmetic_type: str,
        identifier: str,
    ):
        if guild_id is None:
            raise ValueError(
                "Serveur introuvable."
            )

        if cosmetic_type not in EQUIPPED_COLUMNS:
            raise ValueError(
                "Type de cosmétique invalide."
            )

        cosmetic = await self.get_pool().fetchrow(
            """
            SELECT
                cosmetic.id,
                cosmetic.identifier,
                cosmetic.cosmetic_type,
                cosmetic.display_name
            FROM profile_inventory AS inventory
            INNER JOIN profile_cosmetics AS cosmetic
                ON cosmetic.id = inventory.cosmetic_id
            WHERE inventory.guild_id = $1
              AND inventory.user_id = $2
              AND cosmetic.identifier = $3
              AND cosmetic.cosmetic_type = $4
              AND cosmetic.enabled = TRUE
            """,
            guild_id,
            user_id,
            identifier,
            cosmetic_type,
        )

        if cosmetic is None:
            raise ValueError(
                "Tu ne possèdes pas ce cosmétique."
            )

        await self.get_profile(
            guild_id=guild_id,
            user_id=user_id,
        )

        column = EQUIPPED_COLUMNS[
            cosmetic_type
        ]

        await self.get_pool().execute(
            f"""
            UPDATE member_profiles
            SET
                {column} = $3,
                updated_at = NOW()
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
            identifier,
        )

        return cosmetic

    async def reset_cosmetics(
        self,
        *,
        guild_id: int | None,
        user_id: int,
    ) -> None:
        if guild_id is None:
            return

        await self.get_pool().execute(
            """
            UPDATE member_profiles
            SET
                equipped_title = NULL,
                equipped_badge = NULL,
                equipped_background = NULL,
                equipped_frame = NULL,
                equipped_effect = NULL,
                updated_at = NOW()
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

    async def get_equipped_cosmetics(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        records = await self.get_pool().fetch(
            """
            SELECT
                cosmetic.identifier,
                cosmetic.cosmetic_type,
                cosmetic.display_name,
                cosmetic.asset_path,
                cosmetic.value
            FROM member_profiles AS profile
            INNER JOIN profile_cosmetics AS cosmetic
                ON cosmetic.guild_id =
                    profile.guild_id
               AND cosmetic.enabled = TRUE
               AND cosmetic.identifier IN (
                    profile.equipped_title,
                    profile.equipped_badge,
                    profile.equipped_background,
                    profile.equipped_frame,
                    profile.equipped_effect
               )
            WHERE profile.guild_id = $1
              AND profile.user_id = $2
            """,
            guild_id,
            user_id,
        )

        return {
            str(
                record["cosmetic_type"]
            ): record
            for record in records
        }

    async def get_advent_stats(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> tuple[int, int]:
        record = await self.get_pool().fetchrow(
            """
            SELECT
                COUNT(opening.id)::INTEGER
                    AS openings,

                COALESCE(
                    SUM(opening.points_awarded),
                    0
                )::BIGINT AS points

            FROM advent_openings AS opening
            INNER JOIN advent_campaigns AS campaign
                ON campaign.id =
                    opening.campaign_id
            WHERE opening.guild_id = $1
              AND opening.user_id = $2
              AND campaign.year = (
                    SELECT MAX(year)
                    FROM advent_campaigns
                    WHERE guild_id = $1
              )
            """,
            guild_id,
            user_id,
        )

        if record is None:
            return 0, 0

        return (
            int(
                record["openings"]
                or 0
            ),
            int(
                record["points"]
                or 0
            ),
        )

    async def render_profile(
        self,
        *,
        guild_id: int,
        member: discord.Member | discord.User,
    ) -> discord.File:
        profile = await self.get_profile(
            guild_id=guild_id,
            user_id=member.id,
        )

        equipped = (
            await self.get_equipped_cosmetics(
                guild_id=guild_id,
                user_id=member.id,
            )
        )

        current_streak = (
            await self.get_current_daily_streak(
                guild_id=guild_id,
                user_id=member.id,
            )
        )

        avatar_bytes = (
            await member.display_avatar.replace(
                size=256,
                format="png",
            ).read()
        )

        output = await asyncio.to_thread(
            self._render_profile_sync,
            member.id,
            member.display_name,
            avatar_bytes,
            dict(profile),
            equipped,
            current_streak,
        )

        return discord.File(
            output,
            filename=(
                f"profile-{member.id}.png"
            ),
        )

    def _render_profile_sync(
        self,
        user_id: int,
        display_name: str,
        avatar_bytes: bytes,
        profile: dict[str, Any],
        equipped: dict[str, Any],
        current_streak: int,
    ) -> io.BytesIO:
        selected_color = color_tuple(
            str(profile["color_hex"])
        )

        background = create_gradient(
            selected_color
        )

        background_cosmetic = (
            equipped.get("background")
        )

        if background_cosmetic is not None:
            asset = load_rgba_asset(
                self.assets_root,
                background_cosmetic[
                    "asset_path"
                ],
            )

            if asset is not None:
                fitted = ImageOps.fit(
                    asset,
                    (
                        PROFILE_WIDTH,
                        PROFILE_HEIGHT,
                    ),
                    method=(
                        Image.Resampling.LANCZOS
                    ),
                )

                background.alpha_composite(
                    fitted
                )

        overlay = Image.new(
            "RGBA",
            background.size,
            (0, 0, 0, 0),
        )

        overlay_draw = ImageDraw.Draw(
            overlay,
            "RGBA",
        )

        has_illustration = (
            background_cosmetic is not None
        )
        has_frame = (
            equipped.get("frame") is not None
        )

        if has_illustration:
            # Fond illustré : on garde l'image visible et on assombrit
            # seulement la zone du texte, en dégradé.
            background.alpha_composite(
                readability_overlay(background.size)
            )
        else:
            overlay_draw.rounded_rectangle(
                (35, 35, 1165, 465),
                radius=40,
                fill=(10, 12, 20, 155),
            )

        # La bordure de couleur n'est dessinée que sans cadre équipé :
        # sinon elle se superposait au cadre.
        if not has_frame:
            overlay_draw.rounded_rectangle(
                (35, 35, 1165, 465),
                radius=40,
                outline=(
                    selected_color[0],
                    selected_color[1],
                    selected_color[2],
                    230,
                ),
                width=4,
            )

        background.alpha_composite(
            overlay
        )

        effect = equipped.get(
            "effect"
        )

        if effect is not None:
            effect_value = str(
                effect["value"]
                or ""
            ).lower()

            if (
                effect_value == "snow"
                or "neige" in effect_value
                or "snow"
                in str(
                    effect["identifier"]
                ).lower()
            ):
                apply_snow_effect(
                    background,
                    user_id,
                )

            effect_asset = load_rgba_asset(
                self.assets_root,
                effect["asset_path"],
            )

            if effect_asset is not None:
                effect_asset = fit_layer(
                    effect_asset,
                    background.size,
                )

                background.alpha_composite(
                    effect_asset
                )

        with Image.open(
            io.BytesIO(
                avatar_bytes
            )
        ) as avatar_source:
            avatar = avatar_source.convert(
                "RGBA"
            )

        avatar = ImageOps.fit(
            avatar,
            (
                270,
                270,
            ),
            method=Image.Resampling.LANCZOS,
        )

        mask = Image.new(
            "L",
            avatar.size,
            0,
        )

        mask_draw = ImageDraw.Draw(
            mask
        )

        mask_draw.ellipse(
            (
                0,
                0,
                269,
                269,
            ),
            fill=255,
        )

        avatar.putalpha(
            mask
        )

        avatar_border = Image.new(
            "RGBA",
            (
                294,
                294,
            ),
            (
                0,
                0,
                0,
                0,
            ),
        )

        border_draw = ImageDraw.Draw(
            avatar_border
        )

        border_draw.ellipse(
            (
                0,
                0,
                293,
                293,
            ),
            fill=(
                selected_color[0],
                selected_color[1],
                selected_color[2],
                255,
            ),
        )

        avatar_border.alpha_composite(
            avatar,
            (
                12,
                12,
            ),
        )

        background.alpha_composite(
            avatar_border,
            (
                75,
                103,
            ),
        )

        draw = ImageDraw.Draw(
            background,
            "RGBA",
        )

        title = "Membre du Clan"

        title_cosmetic = equipped.get(
            "title"
        )

        if title_cosmetic is not None:
            title = str(
                title_cosmetic["value"]
                or title_cosmetic[
                    "display_name"
                ]
            )

        bio = str(
            profile["bio"]
        ).strip()

        if not bio:
            bio = (
                "Ce membre n'a pas encore écrit "
                "sa phrase personnalisée."
            )

        draw.text(
            (
                410,
                90,
            ),
            truncate(
                display_name,
                28,
            ),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 140),
            font=font(
                52,
                bold=True,
            ),
            fill=(
                255,
                255,
                255,
                255,
            ),
        )

        draw.text(
            (
                413,
                155,
            ),
            truncate(
                title,
                45,
            ),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 140),
            font=font(
                28,
                bold=True,
            ),
            fill=(
                selected_color[0],
                selected_color[1],
                selected_color[2],
                255,
            ),
        )

        wrapped_bio = textwrap.wrap(
            bio,
            width=48,
        )[:3]

        draw.multiline_text(
            (
                413,
                215,
            ),
            "\n".join(
                wrapped_bio
            ),
            font=font(24),
            fill=(
                235,
                235,
                240,
                255,
            ),
            spacing=10,
            stroke_width=2,
            stroke_fill=(0, 0, 0, 130),
        )

        # Série quotidienne actuelle en bas à droite.
        streak_value = max(
            0,
            int(current_streak),
        )

        streak_label = (
            "JOUR"
            if streak_value == 1
            else "JOURS"
        )

        streak_text = (
            f"SÉRIE • {streak_value} "
            f"{streak_label}"
        )

        streak_font = font(
            21,
            bold=True,
        )

        streak_text_box = draw.textbbox(
            (
                0,
                0,
            ),
            streak_text,
            font=streak_font,
        )

        streak_text_width = (
            streak_text_box[2]
            - streak_text_box[0]
        )

        streak_text_height = (
            streak_text_box[3]
            - streak_text_box[1]
        )

        streak_right = 1128
        streak_bottom = 427
        streak_horizontal_padding = 22
        streak_vertical_padding = 13

        streak_left = (
            streak_right
            - streak_text_width
            - streak_horizontal_padding * 2
        )

        streak_top = (
            streak_bottom
            - streak_text_height
            - streak_vertical_padding * 2
        )

        draw.rounded_rectangle(
            (
                streak_left,
                streak_top,
                streak_right,
                streak_bottom,
            ),
            radius=18,
            fill=(
                14,
                16,
                26,
                205,
            ),
            outline=(
                selected_color[0],
                selected_color[1],
                selected_color[2],
                225,
            ),
            width=2,
        )

        draw.text(
            (
                streak_right
                - streak_horizontal_padding,
                streak_top
                + streak_vertical_padding
                - streak_text_box[1],
            ),
            streak_text,
            font=streak_font,
            fill=(
                255,
                255,
                255,
                255,
            ),
            anchor="ra",
        )

        badge_cosmetic = equipped.get(
            "badge"
        )

        if badge_cosmetic is not None:
            badge_asset = load_rgba_asset(
                self.assets_root,
                badge_cosmetic[
                    "asset_path"
                ],
            )

            if badge_asset is not None:
                badge_asset.thumbnail(
                    (
                        120,
                        120,
                    ),
                    Image.Resampling.LANCZOS,
                )

                background.alpha_composite(
                    badge_asset,
                    (
                        1015,
                        75,
                    ),
                )
            else:
                draw.ellipse(
                    (
                        1020,
                        80,
                        1125,
                        185,
                    ),
                    fill=(
                        selected_color[0],
                        selected_color[1],
                        selected_color[2],
                        230,
                    ),
                    outline=(
                        255,
                        255,
                        255,
                        230,
                    ),
                    width=4,
                )

                draw.text(
                    (
                        1050,
                        103,
                    ),
                    "★",
                    font=font(
                        50,
                        bold=True,
                    ),
                    fill=(
                        255,
                        255,
                        255,
                        255,
                    ),
                )

        frame_cosmetic = equipped.get(
            "frame"
        )
        applied_frame = None
        if frame_cosmetic is not None:
            frame_asset = load_rgba_asset(
                self.assets_root,
                frame_cosmetic[
                    "asset_path"
                ],
            )

            if frame_asset is not None:
                frame_asset = fit_layer(
                    frame_asset,
                    background.size,
                )
                background.alpha_composite(
                    frame_asset
                )
                applied_frame = frame_asset
        output = io.BytesIO()
        shape_card(
            background,
            applied_frame,
        ).save(
            output,
            format="PNG",
            optimize=True,
        )

        output.seek(0)

        return output

    async def send_profile(
        self,
        interaction: discord.Interaction,
        *,
        member: discord.Member | discord.User,
        ephemeral: bool,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Serveur requis",
                    (
                        "Les profils sont disponibles "
                        "uniquement dans un serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        profile_file = (
            await self.render_profile(
                guild_id=interaction.guild_id,
                member=member,
            )
        )

        extra: dict[str, Any] = {}

        # Les boutons (personnaliser, inventaire…) ne s'affichent que
        # sur son propre profil. discord.py refuse view=None dans un
        # message de suivi : la vue n'est passée que si elle existe.
        if member.id == interaction.user.id:
            extra["view"] = ProfileView(
                cog=self,
                owner=member,
            )

        await interaction.followup.send(
            file=profile_file,
            ephemeral=ephemeral,
            **extra,
        )

    @app_commands.command(
        name="profil",
        description=(
            "Affiche ton profil ou celui d'un membre."
        ),
    )
    @app_commands.describe(
        membre=(
            "Membre dont tu souhaites "
            "afficher le profil."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        4.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def profile(
        self,
        interaction: discord.Interaction,
        membre: discord.Member | None = None,
    ) -> None:
        await interaction.response.defer(
            thinking=True,
        )

        selected_member = (
            membre
            if membre is not None
            else interaction.user
        )

        await self.send_profile(
            interaction,
            member=selected_member,
            ephemeral=False,
        )

    @app_commands.command(
        name="profil-admin",
        description=(
            "Ouvre le panneau administratif des profils."
        ),
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.guild_only()
    async def profile_admin(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    (
                        "Cette commande doit être "
                        "utilisée sur un serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="⚙️ Administration des profils",
            description=(
                "Depuis ce panneau, tu peux créer des titres, "
                "badges, arrière-plans, cadres et effets, puis "
                "les distribuer aux membres.\n\n"
                "Les images doivent être placées dans "
                "`assets/profile/`."
            ),
            color=PROFILE_COLOR,
        )

        embed.add_field(
            name="Types disponibles",
            value=(
                "• `title`\n"
                "• `badge`\n"
                "• `background`\n"
                "• `frame`\n"
                "• `effect`"
            ),
            inline=True,
        )

        embed.add_field(
            name="Exemples de chemins",
            value=(
                "`badges/flocon.png`\n"
                "`backgrounds/noel.png`\n"
                "`frames/noel.png`\n"
                "`effects/neige.png`"
            ),
            inline=True,
        )

        await interaction.response.send_message(
            embed=embed,
            view=ProfileAdminView(
                cog=self,
                guild_id=interaction.guild_id,
            ),
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    if not isinstance(
        bot,
        ClanRenardBot,
    ):
        raise TypeError(
            (
                "L'extension Profile nécessite "
                "ClanRenardBot."
            )
        )

    cog = ProfileCog(bot)

    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info(
        "Système de profils initialisé"
    )


async def teardown(
    bot: commands.Bot,
) -> None:
    await bot.remove_cog(
        "ProfileCog"
    )

    LOGGER.info(
        "Système de profils déchargé"
    )
