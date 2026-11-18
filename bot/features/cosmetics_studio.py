"""
Création de cosmétiques depuis Discord (/profil-admin).

- 🆕 Créer un cosmétique : type, thème, nom, image envoyée depuis le PC
  (ou texte pour un titre) ; aperçu sur ta carte de profil.
- 📦 Créer une collection : fond, cadre, badge et effet d'un même thème
  en une fois (jusqu'à 4 images + un titre), avec aperçu et confirmation.
- 🔁 Changer l'image d'un cosmétique existant.

Les images envoyées sont préparées au bon format (fond 1200 × 500,
cadre et effet 1200 × 500 transparents, badge 256 × 256) et stockées
dans la base de données : Render efface les fichiers à chaque
redéploiement, le bot les remet donc en place à chaque démarrage
(dossier assets/profile/uploaded/).
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import discord
from PIL import Image, ImageOps

LOGGER = logging.getLogger(__name__)

CARD_SIZE = (1200, 500)
BADGE_SIZE = (256, 256)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 50_000_000

TYPES = ("background", "frame", "badge", "effect", "title")
TYPE_LABELS = {
    "background": ("Fond", "🖼️"),
    "frame": ("Cadre", "🔲"),
    "badge": ("Badge", "🏅"),
    "effect": ("Effet", "✨"),
    "title": ("Titre", "🏷️"),
}
FILENAME_KEYWORDS = {
    "background": ("fond", "background", "bg", "arriere", "wallpaper", "banniere", "banner"),
    "frame": ("cadre", "frame", "bordure", "border", "contour"),
    "badge": ("badge", "icone", "icon", "logo", "embleme"),
    "effect": ("effet", "effect", "fx", "overlay", "particule", "particles"),
}

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


def slugify(text: str) -> str:
    """« Volcan 2026 » → « volcan-2026 » (lettres, chiffres, tirets)."""
    import unicodedata

    text = unicodedata.normalize("NFD", text.strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:40]


def make_identifier(cosmetic_type: str, theme: str) -> str:
    return f"{cosmetic_type}-{slugify(theme)}"


# ============================================================
# IMAGES
# ============================================================


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
    except Exception as error:
        raise ValueError("Ce fichier n'est pas une image lisible.") from error

    if image.width * image.height > MAX_PIXELS:
        raise ValueError("Image trop grande (50 mégapixels maximum).")

    image = ImageOps.exif_transpose(image)
    return image.convert("RGBA")


def transparency(image: Image.Image) -> float:
    """Part de pixels transparents (alpha < 128), de 0 à 1."""
    histogram = image.getchannel("A").histogram()
    return sum(histogram[:128]) / max(1, image.width * image.height)


def frame_shape(image: Image.Image) -> tuple[float, float]:
    """
    (transparence du centre, opacité du bord) : un cadre a le centre vide
    et un contour plein sur les 4 % extérieurs de l'image.
    """
    w, h = image.size
    center = image.crop((int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)))
    bw, bh = max(1, int(w * 0.04)), max(1, int(h * 0.04))
    border = image.copy()
    border.paste((0, 0, 0, 0), (bw, bh, w - bw, h - bh))
    border_area = w * h - (w - 2 * bw) * (h - 2 * bh)
    opaque_border = sum(border.getchannel("A").histogram()[128:]) / max(1, border_area)
    return transparency(center), opaque_border


def guess_type(filename: str, image: Image.Image) -> str:
    """Type deviné d'après le nom du fichier, sinon d'après l'image."""
    name = slugify(Path(filename).stem)

    for cosmetic_type, words in FILENAME_KEYWORDS.items():
        if any(re.search(rf"(^|-){word}(-|$)", name) for word in words):
            return cosmetic_type

    ratio = image.width / max(1, image.height)

    if 0.75 <= ratio <= 1.33:
        return "badge"

    if transparency(image) < 0.05:
        return "background"

    center, border = frame_shape(image)

    if center > 0.85 and border > 0.15:
        return "frame"

    return "effect"


def prepare_image(data: bytes, cosmetic_type: str) -> tuple[bytes, list[str]]:
    """Met l'image au format attendu par la carte de profil. Retourne (PNG, avertissements)."""
    image = _open(data)
    warnings: list[str] = []
    w, h = image.size

    if cosmetic_type == "background":
        if w < 900 or h < 375:
            warnings.append(f"Image petite ({w} × {h}) : le fond sera un peu flou. Idéal : 1200 × 500.")
        if abs(w / h - 2.4) > 0.6:
            warnings.append("Format éloigné de 1200 × 500 : le fond est recadré au centre.")
        result = ImageOps.fit(image, CARD_SIZE, Image.LANCZOS)

    elif cosmetic_type in ("frame", "effect"):
        clear = transparency(image)

        if cosmetic_type == "frame":
            center, _ = frame_shape(image)

            if center < 0.6:
                raise ValueError(
                    "Un cadre doit avoir le centre transparent (PNG avec transparence), "
                    "sinon il cache toute la carte."
                )
        elif clear < 0.2:
            raise ValueError(
                "Un effet doit être en grande partie transparent (PNG), "
                "sinon il cache toute la carte."
            )

        if abs(w / h - 2.4) > 0.3:
            warnings.append(f"Format {w} × {h} : l'image est étirée en 1200 × 500 (idéal : 1200 × 500).")
        result = image.resize(CARD_SIZE, Image.LANCZOS)

    elif cosmetic_type == "badge":
        if transparency(image) < 0.02:
            warnings.append("Pas de transparence : le carré de fond du badge sera visible.")
        if not 0.75 <= w / max(1, h) <= 1.33:
            warnings.append("Badge pas carré : il est réduit pour tenir dans un carré.")
        result = Image.new("RGBA", BADGE_SIZE, (0, 0, 0, 0))
        contained = ImageOps.contain(image, BADGE_SIZE, Image.LANCZOS)
        result.paste(contained, ((BADGE_SIZE[0] - contained.width) // 2, (BADGE_SIZE[1] - contained.height) // 2))

    else:
        raise ValueError("Un titre n'a pas d'image.")

    output = io.BytesIO()
    result.save(output, format="PNG", optimize=True)
    return output.getvalue(), warnings


# ============================================================
# STOCKAGE (base + fichiers)
# ============================================================

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS profile_cosmetic_images (
    guild_id BIGINT NOT NULL,
    identifier VARCHAR(50) NOT NULL,
    data BYTEA NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, identifier)
)
"""


def uploaded_path(guild_id: int, identifier: str) -> str:
    """Chemin relatif à assets/profile/ (format attendu par la carte de profil)."""
    return f"uploaded/{guild_id}/{identifier}.png"


def write_file(assets_root: Path, relative: str, data: bytes) -> None:
    target = assets_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


async def save_image(cog: Any, guild_id: int, identifier: str, data: bytes) -> str:
    pool = cog.get_pool()
    await pool.execute(CREATE_TABLE)
    await pool.execute(
        """
        INSERT INTO profile_cosmetic_images (guild_id, identifier, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, identifier) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
        """,
        guild_id,
        identifier,
        data,
    )
    relative = uploaded_path(guild_id, identifier)
    await asyncio.to_thread(write_file, cog.assets_root, relative, data)
    return relative


async def restore_images(cog: Any) -> int:
    """Au démarrage : réécrit sur le disque les images envoyées depuis Discord."""
    pool = cog.get_pool()
    await pool.execute(CREATE_TABLE)
    records = await pool.fetch("SELECT guild_id, identifier, data FROM profile_cosmetic_images")

    for record in records:
        relative = uploaded_path(int(record["guild_id"]), str(record["identifier"]))
        await asyncio.to_thread(write_file, cog.assets_root, relative, bytes(record["data"]))

    return len(records)


async def existing_identifiers(cog: Any, guild_id: int, identifiers: list[str]) -> set[str]:
    rows = await cog.get_pool().fetch(
        "SELECT identifier FROM profile_cosmetics WHERE guild_id = $1 AND identifier = ANY($2::text[])",
        guild_id,
        identifiers,
    )
    return {str(row["identifier"]) for row in rows}


# ============================================================
# APERÇU
# ============================================================


@dataclass
class PlannedCosmetic:
    cosmetic_type: str
    identifier: str
    display_name: str
    image: bytes | None = None
    value: str | None = None
    source: str = ""
    warnings: list[str] = field(default_factory=list)


async def render_preview(cog: Any, interaction: discord.Interaction, planned: list[PlannedCosmetic]) -> discord.File | None:
    """Carte de profil de l'admin avec les cosmétiques prévus, sans rien enregistrer."""
    guild_id = interaction.guild_id
    member = interaction.user
    temp_files: list[Path] = []

    try:
        profile = await cog.get_profile(guild_id=guild_id, user_id=member.id)
        equipped = dict(await cog.get_equipped_cosmetics(guild_id=guild_id, user_id=member.id))
        streak = await cog.get_current_daily_streak(guild_id=guild_id, user_id=member.id)
        avatar = await member.display_avatar.replace(size=256, format="png").read()
        token = uuid.uuid4().hex[:10]

        for item in planned:
            asset_path = None

            if item.image is not None:
                asset_path = f"uploaded/_apercu/{token}-{item.cosmetic_type}.png"
                await asyncio.to_thread(write_file, cog.assets_root, asset_path, item.image)
                temp_files.append(cog.assets_root / asset_path)

            equipped[item.cosmetic_type] = {
                "identifier": item.identifier,
                "cosmetic_type": item.cosmetic_type,
                "display_name": item.display_name,
                "asset_path": asset_path,
                "value": item.value,
            }

        output = await asyncio.to_thread(
            cog._render_profile_sync, member.id, member.display_name, avatar, dict(profile), equipped, streak
        )
        return discord.File(output, filename="apercu-cosmetique.png")
    except Exception:
        LOGGER.exception("Aperçu du cosmétique impossible")
        return None
    finally:
        for path in temp_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def plan_lines(planned: list[PlannedCosmetic]) -> list[str]:
    lines = []

    for item in planned:
        label, emoji = TYPE_LABELS[item.cosmetic_type]
        source = f" ← `{item.source}`" if item.source else ""
        lines.append(f"{emoji} **{item.display_name}** · `{item.identifier}`{source}")

        for warning in item.warnings:
            lines.append(f"  ⚠️ {warning}")

    return lines


async def create_all(cog: Any, guild_id: int, planned: list[PlannedCosmetic]) -> list[Any]:
    created = []

    for item in planned:
        asset_path = None

        if item.image is not None:
            asset_path = await save_image(cog, guild_id, item.identifier, item.image)

        record = await cog.create_cosmetic(
            guild_id=guild_id,
            identifier=item.identifier,
            cosmetic_type=item.cosmetic_type,
            display_name=item.display_name,
            description=f"Cosmétique {item.display_name}",
            asset_path=asset_path,
            value=item.value,
        )
        created.append(record)

    return created


def next_steps(identifiers: list[str]) -> str:
    return (
        "**Et maintenant ?**\n"
        "• 🎁 **Distribuer** (ici) pour le donner à un membre\n"
        "• `/boutique-admin` pour le vendre contre des pièces\n"
        "• `/avent-admin` → **Ajouter un cosmétique à la boutique** avec l'identifiant "
        + ", ".join(f"`{identifier}`" for identifier in identifiers[:4])
        + "\n• 📚 **Catalogue** pour retrouver son ID"
    )


async def read_attachment(attachment: discord.Attachment) -> bytes:
    if attachment.size > MAX_UPLOAD_BYTES:
        raise ValueError(f"« {attachment.filename} » est trop lourde (25 Mo maximum).")

    if attachment.content_type and not attachment.content_type.startswith("image/"):
        raise ValueError(f"« {attachment.filename} » n'est pas une image.")

    return await attachment.read()


# ============================================================
# FENÊTRES
# ============================================================


def labeled(modal: discord.ui.Modal, label: str, *, description: str | None = None, required: bool = True,
            max_length: int = 60, placeholder: str | None = None, default: str | None = None) -> discord.ui.TextInput:
    component = discord.ui.TextInput(required=required, max_length=max_length, placeholder=placeholder, default=default)
    modal.add_item(discord.ui.Label(text=label, description=description, component=component))
    return component


class CreateCosmeticModal(discord.ui.Modal):
    def __init__(self, cog: Any) -> None:
        super().__init__(title="🆕 Créer un cosmétique", timeout=900)
        self.cog = cog
        self.type_select = discord.ui.Select(
            options=[
                discord.SelectOption(label=label, value=key, emoji=emoji)
                for key, (label, emoji) in TYPE_LABELS.items()
            ]
        )
        self.add_item(discord.ui.Label(text="Type", component=self.type_select))
        self.theme = labeled(
            self, "Thème (collection)", placeholder="volcan-2026",
            description="Identifiant = type-thème (ex. frame-volcan-2026). Même thème = même collection.",
        )
        self.name = labeled(self, "Nom affiché", placeholder="Cadre volcan", max_length=100)
        self.file = discord.ui.FileUpload(required=False, min_values=0, max_values=1)
        self.add_item(
            discord.ui.Label(
                text="Image (PNG conseillé)",
                description="Fond/cadre/effet : 1200 × 500 · badge : carré 256 × 256 · titre : pas d'image",
                component=self.file,
            )
        )
        self.value = labeled(
            self, "Texte du titre (ou valeur d'effet)", required=False, max_length=100,
            description="Titre : le texte affiché. Effet : « snow » ajoute une neige animée.",
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        cosmetic_type = self.type_select.values[0]
        theme = slugify(self.theme.value)
        name = self.name.value.strip()
        value = self.value.value.strip() or None

        try:
            if not theme:
                raise ValueError("Le thème doit contenir des lettres ou des chiffres (ex. volcan-2026).")

            identifier = make_identifier(cosmetic_type, theme)

            if await existing_identifiers(self.cog, interaction.guild_id, [identifier]):
                raise ValueError(
                    f"`{identifier}` existe déjà. Choisis un autre thème, ou utilise "
                    "🔁 **Changer l'image** pour le modifier."
                )

            files = list(self.file.values)
            planned = PlannedCosmetic(cosmetic_type, identifier, name, value=value)

            if cosmetic_type == "title":
                if not value:
                    raise ValueError("Un titre a besoin de son texte (dernier champ).")
            else:
                if not files:
                    raise ValueError("Envoie l'image du cosmétique.")
                planned.image, planned.warnings = await asyncio.to_thread(
                    prepare_image, await read_attachment(files[0]), cosmetic_type
                )
                planned.source = files[0].filename
        except ValueError as error:
            await interaction.followup.send(embed=error_embed(str(error)), ephemeral=True)
            return

        record = (await create_all(self.cog, interaction.guild_id, [planned]))[0]
        preview = await render_preview(self.cog, interaction, [planned])
        embed = discord.Embed(
            title="✅ Cosmétique créé",
            description="\n".join(plan_lines([planned]))
            + f"\nID : `#{record['id']}`\n\n"
            + next_steps([identifier]),
            color=SUCCESS_COLOR,
        )
        kwargs: dict[str, Any] = {"embed": embed, "ephemeral": True}

        if preview is not None:
            embed.set_image(url="attachment://apercu-cosmetique.png")
            embed.set_footer(text="Aperçu sur ta carte de profil (rien n'est équipé)")
            kwargs["file"] = preview

        await interaction.followup.send(**kwargs)


class CollectionModal(discord.ui.Modal):
    def __init__(self, cog: Any) -> None:
        super().__init__(title="📦 Créer une collection", timeout=900)
        self.cog = cog
        self.theme = labeled(
            self, "Thème (collection)", placeholder="volcan-2026",
            description="Les identifiants seront background-…, frame-…, badge-…, effect-…",
        )
        self.name = labeled(
            self, "Nom de la collection", placeholder="Volcan",
            description="Noms affichés : « Fond Volcan », « Cadre Volcan »…",
        )
        self.files = discord.ui.FileUpload(required=True, min_values=1, max_values=4)
        self.add_item(
            discord.ui.Label(
                text="Images (1 à 4 : fond, cadre, badge, effet)",
                description="Mets fond / cadre / badge / effet dans le nom des fichiers, sinon je devine.",
                component=self.files,
            )
        )
        self.title_text = labeled(
            self, "Titre de la collection (facultatif)", required=False, max_length=100,
            placeholder="Seigneur des volcans", description="Crée aussi un titre title-… avec ce texte.",
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        theme = slugify(self.theme.value)
        name = self.name.value.strip()
        planned: list[PlannedCosmetic] = []

        try:
            if not theme:
                raise ValueError("Le thème doit contenir des lettres ou des chiffres (ex. volcan-2026).")

            for attachment in self.files.values:
                data = await read_attachment(attachment)
                image = await asyncio.to_thread(_open, data)
                cosmetic_type = guess_type(attachment.filename, image)

                if any(item.cosmetic_type == cosmetic_type for item in planned):
                    label = TYPE_LABELS[cosmetic_type][0].lower()
                    raise ValueError(
                        f"Deux images ont été reconnues comme « {label} ». Renomme les fichiers avec "
                        "fond / cadre / badge / effet (ex. volcan-cadre.png)."
                    )

                prepared, warnings = await asyncio.to_thread(prepare_image, data, cosmetic_type)
                planned.append(
                    PlannedCosmetic(
                        cosmetic_type,
                        make_identifier(cosmetic_type, theme),
                        f"{TYPE_LABELS[cosmetic_type][0]} {name}",
                        image=prepared,
                        source=attachment.filename,
                        warnings=warnings,
                    )
                )

            if self.title_text.value.strip():
                planned.append(
                    PlannedCosmetic("title", make_identifier("title", theme), f"Titre {name}",
                                    value=self.title_text.value.strip())
                )

            planned.sort(key=lambda item: TYPES.index(item.cosmetic_type))
            taken = await existing_identifiers(self.cog, interaction.guild_id, [item.identifier for item in planned])

            if taken:
                raise ValueError(
                    "Ces identifiants existent déjà : " + ", ".join(f"`{i}`" for i in sorted(taken))
                    + ". Choisis un autre thème, ou modifie-les avec 🔁 **Changer l'image**."
                )
        except ValueError as error:
            await interaction.followup.send(embed=error_embed(str(error)), ephemeral=True)
            return

        preview = await render_preview(self.cog, interaction, planned)
        embed = discord.Embed(
            title=f"📦 Collection « {name} » — vérifie avant de créer",
            description="\n".join(plan_lines(planned))
            + "\n\nSi un type est mal reconnu, annule et renomme le fichier (fond / cadre / badge / effet).",
            color=COLOR,
        )
        view = ConfirmCollectionView(self.cog, interaction.user.id, planned, name)
        kwargs: dict[str, Any] = {"embed": embed, "view": view, "ephemeral": True}

        if preview is not None:
            embed.set_image(url="attachment://apercu-cosmetique.png")
            embed.set_footer(text="Aperçu : toute la collection équipée sur ta carte")
            kwargs["file"] = preview

        await interaction.followup.send(**kwargs)


class ConfirmCollectionView(discord.ui.View):
    def __init__(self, cog: Any, owner_id: int, planned: list[PlannedCosmetic], name: str) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.planned = planned
        self.name = name

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="Créer la collection", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.defer()

        taken = await existing_identifiers(self.cog, interaction.guild_id, [i.identifier for i in self.planned])

        if taken:
            await interaction.edit_original_response(
                embed=error_embed("Entre-temps, ces identifiants ont été créés : " + ", ".join(sorted(taken))),
                view=None, attachments=[],
            )
            return

        records = await create_all(self.cog, interaction.guild_id, self.planned)
        lines = [
            f"{TYPE_LABELS[record['cosmetic_type']][1]} **{record['display_name']}** · `{record['identifier']}` · `#{record['id']}`"
            for record in records
        ]
        await interaction.edit_original_response(
            embed=discord.Embed(
                title=f"✅ Collection « {self.name} » créée",
                description="\n".join(lines) + "\n\n" + next_steps([r["identifier"] for r in records])
                + "\n\nElle apparaît dans `/collections` dès qu'elle a au moins 2 objets.",
                color=SUCCESS_COLOR,
            ),
            view=None,
            attachments=[],
        )

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="Annulé : rien n'a été créé.", color=COLOR), view=None, attachments=[]
        )


class ReplaceImageModal(discord.ui.Modal):
    def __init__(self, cog: Any) -> None:
        super().__init__(title="🔁 Changer l'image", timeout=900)
        self.cog = cog
        self.identifier = labeled(
            self, "Identifiant du cosmétique", placeholder="frame-volcan-2026", max_length=50,
            description="Visible dans 📚 Catalogue. Les membres qui l'ont gardent le cosmétique.",
        )
        self.file = discord.ui.FileUpload(required=True, min_values=1, max_values=1)
        self.add_item(discord.ui.Label(text="Nouvelle image", component=self.file))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        identifier = self.identifier.value.strip().lower()
        record = await self.cog.get_pool().fetchrow(
            """
            SELECT id, identifier, cosmetic_type, display_name, value, description
            FROM profile_cosmetics WHERE guild_id = $1 AND identifier = $2
            """,
            interaction.guild_id,
            identifier,
        )

        try:
            if record is None:
                raise ValueError(f"Aucun cosmétique `{identifier}` (regarde 📚 **Catalogue**).")
            if record["cosmetic_type"] == "title":
                raise ValueError("Un titre n'a pas d'image.")

            attachment = list(self.file.values)[0]
            image, warnings = await asyncio.to_thread(
                prepare_image, await read_attachment(attachment), str(record["cosmetic_type"])
            )
        except ValueError as error:
            await interaction.followup.send(embed=error_embed(str(error)), ephemeral=True)
            return

        asset_path = await save_image(self.cog, interaction.guild_id, identifier, image)
        await self.cog.get_pool().execute(
            "UPDATE profile_cosmetics SET asset_path = $3, updated_at = NOW() WHERE guild_id = $1 AND identifier = $2",
            interaction.guild_id,
            identifier,
            asset_path,
        )
        planned = PlannedCosmetic(
            str(record["cosmetic_type"]), identifier, str(record["display_name"]),
            image=image, value=record["value"], source=attachment.filename, warnings=warnings,
        )
        preview = await render_preview(self.cog, interaction, [planned])
        embed = discord.Embed(
            title="🔁 Image remplacée",
            description="\n".join(plan_lines([planned]))
            + "\nLes membres qui l'ont équipé voient la nouvelle image tout de suite.",
            color=SUCCESS_COLOR,
        )
        kwargs: dict[str, Any] = {"embed": embed, "ephemeral": True}

        if preview is not None:
            embed.set_image(url="attachment://apercu-cosmetique.png")
            kwargs["file"] = preview

        await interaction.followup.send(**kwargs)


GUIDE = """\
**🖼️ Fond** — l'arrière-plan de la carte. Idéal : **1200 × 500** (2,4 fois plus large que haut), \
recadré au centre si besoin. Pas besoin de transparence.

**🔲 Cadre** — posé par-dessus la carte : **PNG 1200 × 500 avec le centre transparent**. \
Le bot découpe la carte selon la forme du cadre (coins arrondis compris). Refusé si le centre n'est pas transparent.

**🏅 Badge** — petite icône sur la carte : **PNG carré, idéalement 256 × 256, fond transparent**.

**✨ Effet** — calque par-dessus (paillettes, neige, lumière…) : **PNG 1200 × 500 surtout transparent**. \
Avec la valeur `snow` (ou « snow » / « neige » dans le thème), le bot ajoute en plus une neige générée.

**🏷️ Titre** — pas d'image : juste un texte affiché sur la carte.

**Thème** : `volcan-2026` donne `background-volcan-2026`, `frame-volcan-2026`… Les cosmétiques d'un même \
thème forment une **collection** dans `/collections` (à partir de 2).

**Images** : envoyées depuis ton PC (25 Mo max), redimensionnées automatiquement et gardées dans la base \
de données (elles survivent aux redéploiements de Render).\
"""
