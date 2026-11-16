"""
Annonces : un studio pour écrire des messages publiés par le bot
(aperçu en direct, modèles, images, boutons liens, mentions), les
modifier après coup, les programmer, et importer/exporter le format
Discohook.

Commandes (réservées à « Gérer le serveur ») :
/annonce creer · /annonce modifier · /annonce programmees · /annonce historique
"""

from __future__ import annotations

import io
import logging
import re
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.features.announcements.model import (
    NEW_FORMATS,
    AnnouncementError,
    attachment_name,
    default_draft,
    from_discord_message,
    is_empty,
    message_content,
    problems,
    render_embeds,
    summary_title,
    upload_ids,
)
from bot.features.announcements.layout import build_layout, plain_text
from bot.features.announcements.repository import AnnouncementRepository
from bot.features.announcements.studio import (
    FORMAT_NAMES,
    INFO_COLOR,
    SUCCESS_COLOR,
    StudioView,
    button_label,
    error_embed,
)
from bot.shared.dates import get_timezone

LOGGER = logging.getLogger(__name__)

MESSAGE_LINK = re.compile(
    r"https?://(?:\w+\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)"
)
MAX_FILES_BYTES = 24 * 1024 * 1024
PREVIEW_PLACEHOLDER = "*Cadre vide : clique sur ✏️ **Texte** pour écrire ton annonce.*"
CACHE_SIZE = 12


def links_view(draft: dict[str, Any]) -> discord.ui.View | None:
    buttons = draft.get("buttons") or []

    if not buttons:
        return None

    view = discord.ui.View(timeout=None)

    for index, button in enumerate(buttons):
        view.add_item(
            discord.ui.Button(
                label=button_label(button),
                url=button["url"],
                emoji=button.get("emoji"),
                row=index // 5,
            )
        )

    return view


def allowed_mentions(draft: dict[str, Any]) -> discord.AllowedMentions:
    mention = draft.get("mention")

    return discord.AllowedMentions(
        everyone=mention in ("everyone", "here"),
        roles=True,
        users=True,
    )


class AnnouncementCog(commands.Cog):
    annonce = app_commands.Group(
        name="annonce",
        description="Écrire, programmer et modifier des annonces publiées par le bot.",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = AnnouncementRepository(self.get_pool)
        self.tz_name = getattr(getattr(bot, "settings", None), "default_timezone", None) or "Europe/Paris"

        try:
            self.tz = get_timezone(self.tz_name)
        except ValueError:
            self.tz_name = "Europe/Paris"
            self.tz = get_timezone(self.tz_name)

        self._images: OrderedDict[int, tuple[str, bytes]] = OrderedDict()
        self._loop_turns = 0

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def cog_load(self) -> None:
        try:
            await self.repository.recover_stuck()
        except Exception:
            LOGGER.exception("Annonces programmées : reprise impossible")

        if not self.schedule_loop.is_running():
            self.schedule_loop.start()

    def cog_unload(self) -> None:
        self.schedule_loop.cancel()

    # ============================================================
    # BROUILLONS ET IMAGES
    # ============================================================

    def new_draft(self, guild: discord.Guild) -> dict[str, Any]:
        return default_draft(guild.name, guild.icon.url if guild.icon else None)

    def cache_image(self, image_id: int, filename: str, data: bytes) -> None:
        self._images[image_id] = (filename, data)
        self._images.move_to_end(image_id)

        while len(self._images) > CACHE_SIZE:
            self._images.popitem(last=False)

    async def load_images(
        self, guild_id: int, draft: dict[str, Any]
    ) -> tuple[dict[int, str], list[discord.File]]:
        """Noms attachment:// et fichiers à joindre pour les images envoyées."""
        wanted = upload_ids(draft)
        missing = {image_id for image_id in wanted if image_id not in self._images}

        if missing:
            for image_id, (filename, data) in (
                await self.repository.get_images(guild_id, missing)
            ).items():
                self.cache_image(image_id, filename, data)

        names: dict[int, str] = {}
        files: list[discord.File] = []
        total = 0

        for image_id in sorted(wanted):
            if image_id not in self._images:
                continue

            filename, data = self._images[image_id]
            name = attachment_name(image_id, filename)
            names[image_id] = name
            total += len(data)
            files.append(discord.File(io.BytesIO(data), filename=name))

        if total > MAX_FILES_BYTES:
            raise AnnouncementError(
                "Les images envoyées pèsent plus de 24 Mo au total : "
                "retires-en une ou utilise des liens."
            )

        return names, files

    async def payload(self, guild: discord.Guild, draft: dict[str, Any]) -> dict[str, Any]:
        names, files = await self.load_images(guild.id, draft)

        if draft.get("format") in NEW_FORMATS:
            # Nouveau format : tout est dans la vue (pas de texte ni de cadre classique).
            return {
                "view": build_layout(draft, uploads=names, now=datetime.now(timezone.utc)),
                "files": files,
                "allowed_mentions": allowed_mentions(draft),
            }

        if draft.get("format") == "text":
            # Pleine largeur : un message texte normal, sans cadre.
            return {
                "content": plain_text(draft, now=datetime.now(timezone.utc)) or None,
                "embeds": [],
                "files": files,
                "view": links_view(draft),
                "allowed_mentions": allowed_mentions(draft),
            }

        embeds = [
            discord.Embed.from_dict(data)
            for data in render_embeds(draft, uploads=names, now=datetime.now(timezone.utc))
        ]

        return {
            "content": message_content(draft) or None,
            "embeds": embeds,
            "files": files,
            "view": links_view(draft),
            "allowed_mentions": allowed_mentions(draft),
        }

    # ============================================================
    # APERÇU DU STUDIO
    # ============================================================

    async def studio_message(self, studio: StudioView, *, notice: str | None = None) -> dict[str, Any]:
        draft = studio.draft

        try:
            names, files = await self.load_images(studio.guild.id, draft)
        except AnnouncementError as error:
            names, files = {}, []
            notice = f"{notice}\n⚠️ {error}" if notice else f"⚠️ {error}"

        mention = {
            "everyone": "@everyone",
            "here": "@here",
            "role": f"<@&{draft.get('role_id')}>",
        }.get(draft.get("mention"), "aucune")
        channel = f"<#{draft['channel_id']}>" if draft.get("channel_id") else "*à choisir*"

        lines = ["### 📝 Studio d'annonce"]

        if draft.get("editing"):
            editing = draft["editing"]
            lines.append(
                f"✏️ Modification de [cette annonce](https://discord.com/channels/"
                f"{studio.guild.id}/{editing['channel_id']}/{editing['message_id']})"
            )

        lines.append(
            f"📍 Salon : {channel} · 📣 Mention : {mention} · "
            f"🖊️ Cadre {studio.index + 1}/{len(draft['embeds'])}"
        )

        if draft.get("format") in NEW_FORMATS:
            name = FORMAT_NAMES[draft["format"]]
            lines.append(
                f"📐 Format **{name}** : l'aperçu ci-dessous est approximatif, clique sur 👁️ **Aperçu réel**."
            )

        if len(draft.get("buttons", [])) > 5:
            lines.append(f"🔗 {len(draft['buttons'])} boutons (5 visibles dans l'aperçu)")

        if studio.confirm_reset:
            lines.append("⚠️ Clique encore sur le bouton rouge pour confirmer.")

        if notice:
            lines += [f"> {line}" for line in notice.split("\n") if line]

        issues = [issue for issue in problems(draft) if not is_empty(draft)]
        lines += [f"⚠️ {issue}" for issue in issues[:3]]
        lines.append("**─────── Aperçu ───────**")

        header = "\n".join(lines)
        body = message_content(draft)
        room = 2000 - len(header) - 2

        if len(body) > room:
            body = body[: max(0, room - 25)] + "… *(aperçu coupé)*"

        content = f"{header}\n{body}" if body else header
        embeds = [
            discord.Embed.from_dict(data)
            for data in render_embeds(
                draft,
                uploads=names,
                now=datetime.now(timezone.utc),
                placeholder=PREVIEW_PLACEHOLDER,
            )
        ]

        return {
            "content": content[:2000],
            "embeds": embeds[:10],
            "attachments": files,
            "allowed_mentions": discord.AllowedMentions.none(),
        }

    async def large_preview(self, interaction: discord.Interaction, draft: dict[str, Any]) -> None:
        """Aperçu exact du format grand, dans un message privé à part."""
        try:
            names, files = await self.load_images(interaction.guild_id, draft)
        except AnnouncementError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        if draft.get("format") == "text":
            view = links_view(draft)
            await interaction.response.send_message(
                content=plain_text(
                    draft, now=datetime.now(timezone.utc), placeholder=PREVIEW_PLACEHOLDER
                )[:2000],
                files=files,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
                **({"view": view} if view else {}),
            )
            return

        try:
            await interaction.response.send_message(
                view=build_layout(
                    draft,
                    uploads=names,
                    now=datetime.now(timezone.utc),
                    placeholder=PREVIEW_PLACEHOLDER,
                ),
                files=files,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            await interaction.response.send_message(
                embed=error_embed(f"Discord a refusé l'aperçu : `{str(error)[:300]}`"),
                ephemeral=True,
            )

    async def open_studio(
        self,
        interaction: discord.Interaction,
        draft: dict[str, Any],
        *,
        notice: str | None = None,
    ) -> None:
        studio = StudioView(self, interaction, draft)
        await self.repository.save_draft(interaction.guild_id, interaction.user.id, studio.draft)
        kwargs = await self.studio_message(studio, notice=notice)

        if interaction.response.is_done():
            await interaction.edit_original_response(**kwargs, view=studio)
        else:
            files = kwargs.pop("attachments")
            await interaction.response.send_message(**kwargs, files=files, view=studio, ephemeral=True)

    async def keep_previous_draft(self, guild_id: int, user_id: int) -> str | None:
        """Avant de remplacer un brouillon non vide, on le garde comme modèle."""
        previous = await self.repository.get_draft(guild_id, user_id)

        if previous is None or is_empty(previous) or previous.get("editing"):
            return None

        if await self.repository.count_templates(guild_id) >= 25:
            return None

        name = f"Brouillon du {datetime.now(self.tz):%d/%m %Hh%M}"
        await self.repository.save_template(guild_id, name, previous, user_id)

        return f"💾 Ton brouillon précédent est gardé dans 🧩 Modèles (« {name} »)."

    # ============================================================
    # CONTRÔLES
    # ============================================================

    def permission_problem(
        self,
        guild: discord.Guild,
        draft: dict[str, Any],
        *,
        member: discord.abc.User | None = None,
    ) -> str | None:
        channel = guild.get_channel(draft.get("channel_id") or 0)

        if not isinstance(channel, discord.TextChannel):
            return "Choisis le salon de publication avec 📣 Salon et mention."

        me = guild.me
        perms = channel.permissions_for(me)
        missing = [
            name
            for name, ok in (
                ("Voir le salon", perms.view_channel),
                ("Envoyer des messages", perms.send_messages),
                ("Intégrer des liens", perms.embed_links),
                ("Joindre des fichiers", perms.attach_files or not upload_ids(draft)),
            )
            if not ok
        ]

        if missing:
            return f"Il me manque dans {channel.mention} : " + ", ".join(missing) + "."

        mention = draft.get("mention")
        role = guild.get_role(draft.get("role_id") or 0) if mention == "role" else None

        if mention == "role" and role is None:
            return "Le rôle à mentionner n'existe plus."

        needs_everyone = mention in ("everyone", "here") or (role is not None and not role.mentionable)

        if needs_everyone and not perms.mention_everyone:
            return (
                f"Il me manque la permission « Mentionner @everyone, @here et tous "
                f"les rôles » dans {channel.mention}."
            )

        if (
            needs_everyone
            and isinstance(member, discord.Member)
            and not channel.permissions_for(member).mention_everyone
        ):
            return "Tu n'as pas toi-même le droit de mentionner @everyone ou ce rôle dans ce salon."

        return None

    def check_ready(
        self,
        guild: discord.Guild,
        draft: dict[str, Any],
        *,
        member: discord.abc.User | None = None,
    ) -> discord.TextChannel:
        issues = problems(draft)

        if issues:
            raise AnnouncementError("\n".join(f"• {issue}" for issue in issues))

        problem = self.permission_problem(guild, draft, member=member)

        if problem:
            raise AnnouncementError(problem)

        return guild.get_channel(draft["channel_id"])

    # ============================================================
    # PUBLICATION
    # ============================================================

    async def publish(
        self,
        guild: discord.Guild,
        draft: dict[str, Any],
        author: discord.abc.User | discord.Object,
        *,
        scheduled: bool = False,
    ) -> discord.Message:
        channel = self.check_ready(
            guild,
            draft,
            member=author if isinstance(author, discord.Member) else None,
        )
        payload = await self.payload(guild, draft)

        if payload.get("view") is None:
            payload.pop("view", None)

        try:
            message = await channel.send(**payload)
        except discord.HTTPException as error:
            raise AnnouncementError(
                f"Discord a refusé le message : `{str(error)[:300]}`"
            ) from error

        snapshot = dict(draft, editing=None)
        await self.repository.record_published(
            guild.id, channel.id, message.id, author.id, summary_title(draft), snapshot, scheduled=scheduled
        )
        await self.log(
            guild,
            f"📣 Annonce {'programmée ' if scheduled else ''}publiée par <@{author.id}> "
            f"dans {channel.mention} : [{summary_title(draft)}]({message.jump_url})",
        )

        return message

    async def fetch_own_message(self, guild: discord.Guild, channel_id: int, message_id: int) -> discord.Message:
        channel = guild.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            raise AnnouncementError("Le salon de cette annonce n'existe plus.")

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound as error:
            raise AnnouncementError("Ce message n'existe plus.") from error
        except discord.HTTPException as error:
            raise AnnouncementError("Je n'arrive pas à lire ce message.") from error

        if message.author.id != self.bot.user.id:
            raise AnnouncementError(
                "Je ne peux modifier que mes propres messages (pas ceux d'un membre ou d'un autre bot)."
            )

        return message

    async def apply_edit(
        self,
        guild: discord.Guild,
        draft: dict[str, Any],
        user: discord.abc.User,
    ) -> discord.Message:
        editing = draft["editing"]
        issues = problems(draft)

        if issues:
            raise AnnouncementError("\n".join(f"• {issue}" for issue in issues))

        message = await self.fetch_own_message(guild, editing["channel_id"], editing["message_id"])
        large = draft.get("format") in NEW_FORMATS

        if bool(message.flags.components_v2) != large:
            published = "grand" if message.flags.components_v2 else "classique ou pleine largeur"
            raise AnnouncementError(
                "Discord ne permet pas de passer au format grand (ou d'en sortir) "
                f"sur une annonce déjà publiée (elle est en format {published}). "
                "Remets ce format, ou publie une nouvelle annonce."
            )

        payload = await self.payload(guild, draft)

        try:
            if large:
                await message.edit(
                    view=payload["view"],
                    attachments=payload["files"],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await message.edit(
                    content=payload["content"],
                    embeds=payload["embeds"],
                    attachments=payload["files"],
                    view=payload["view"],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.HTTPException as error:
            raise AnnouncementError(f"Discord a refusé la modification : `{str(error)[:300]}`") from error

        snapshot = dict(draft, editing=None, channel_id=editing["channel_id"])
        await self.repository.record_edited(
            guild.id, editing["channel_id"], message.id, user.id, summary_title(draft), snapshot
        )
        await self.log(
            guild,
            f"✏️ Annonce modifiée par {user.mention} : [{summary_title(draft)}]({message.jump_url})",
        )

        return message

    async def schedule(self, interaction: discord.Interaction, draft: dict[str, Any], moment: datetime) -> int:
        channel = self.check_ready(interaction.guild, draft, member=interaction.user)
        snapshot = dict(draft, editing=None)
        scheduled_id = await self.repository.schedule(
            interaction.guild_id, channel.id, snapshot, moment, interaction.user.id
        )
        await self.log(
            interaction.guild,
            f"⏰ Annonce n°{scheduled_id} programmée par {interaction.user.mention} "
            f"dans {channel.mention} pour le <t:{int(moment.timestamp())}:F> : "
            f"{summary_title(draft)}",
        )

        return scheduled_id

    async def log(self, guild: discord.Guild, text: str) -> None:
        """Trace dans le salon de logs de la modération, s'il est configuré."""
        moderation = self.bot.get_cog("ModerationCog")

        if moderation is None:
            return

        try:
            await moderation.send_log(guild, discord.Embed(description=text, color=INFO_COLOR))
        except Exception:
            LOGGER.warning("Journal des annonces indisponible", exc_info=True)

    # ============================================================
    # ENVOIS PROGRAMMÉS
    # ============================================================

    @tasks.loop(seconds=30)
    async def schedule_loop(self) -> None:
        try:
            due = await self.repository.claim_due()
        except Exception:
            LOGGER.exception("Lecture des annonces programmées impossible")
            return

        for record in due:
            await self.send_scheduled(record)

        self._loop_turns += 1

        if self._loop_turns % 720 == 1:  # environ toutes les 6 heures
            try:
                removed = await self.repository.delete_orphan_images()

                if removed:
                    LOGGER.info("%s image(s) d'annonce inutilisée(s) supprimée(s)", removed)
            except Exception:
                LOGGER.exception("Nettoyage des images d'annonce impossible")

    @schedule_loop.before_loop
    async def before_schedule_loop(self) -> None:
        await self.bot.wait_until_ready()

    async def send_scheduled(self, record: dict[str, Any]) -> None:
        guild = self.bot.get_guild(int(record["guild_id"]))
        draft = record["data"]
        draft["channel_id"] = int(record["channel_id"])
        error: str | None = None
        message: discord.Message | None = None

        if guild is None:
            error = "Serveur introuvable."
        else:
            try:
                message = await self.publish(
                    guild, draft, discord.Object(id=int(record["created_by"])), scheduled=True
                )
            except AnnouncementError as failure:
                error = str(failure)
            except Exception as failure:
                LOGGER.exception("Annonce programmée %s non envoyée", record["id"])
                error = f"Erreur inattendue : {failure}"

        await self.repository.finish_scheduled(
            int(record["id"]), message_id=message.id if message else None, error=error
        )

        if error is None or guild is None:
            return

        text = (
            f"❌ L'annonce programmée n°{record['id']} (« {summary_title(draft)} ») "
            f"n'a pas pu être publiée :\n{error}"
        )
        await self.log(guild, text)
        creator = guild.get_member(int(record["created_by"]))

        if creator is not None:
            try:
                await creator.send(embed=error_embed(text))
            except discord.HTTPException:
                pass

    # ============================================================
    # COMMANDES
    # ============================================================

    @annonce.command(name="creer", description="Ouvre le studio pour écrire une annonce (ton brouillon est gardé).")
    async def creer(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        draft = await self.repository.get_draft(interaction.guild_id, interaction.user.id)
        notice = None

        if draft is None:
            draft = self.new_draft(interaction.guild)
            notice = "Bienvenue ! Commence par ✏️ **Texte**, puis choisis le salon avec 📣."
        elif draft.get("editing"):
            notice = "Tu étais en train de modifier une annonce publiée."
        elif not is_empty(draft):
            notice = "Ton brouillon a été retrouvé."

        await self.open_studio(interaction, draft, notice=notice)

    @annonce.command(name="modifier", description="Modifie une annonce déjà publiée par le bot.")
    @app_commands.describe(lien="Lien du message (clic droit → Copier le lien du message)")
    async def modifier(self, interaction: discord.Interaction, lien: str) -> None:
        match = MESSAGE_LINK.search(lien)

        if match is None or int(match[1]) != interaction.guild_id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Colle le lien d'un message de ce serveur (clic droit sur le message → "
                    "**Copier le lien du message**)."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        channel_id, message_id = int(match[2]), int(match[3])

        try:
            message = await self.fetch_own_message(interaction.guild, channel_id, message_id)
        except AnnouncementError as error:
            await interaction.edit_original_response(embed=error_embed(str(error)))
            return

        draft = await self.repository.get_published(interaction.guild_id, message_id)
        notice = "✏️ Fais tes changements puis clique sur 💾 **Enregistrer les modifications**."

        if draft is None:
            draft = from_discord_message(
                message.content,
                [embed.to_dict() for embed in message.embeds],
                [component.to_dict() for component in message.components],
            )
            notice += (
                "\nℹ️ Ce message n'a pas été créé avec le studio : vérifie les images "
                "(re-envoie-les avec 🖼️ si besoin)."
            )

        kept = await self.keep_previous_draft(interaction.guild_id, interaction.user.id)

        if kept:
            notice += f"\n{kept}"

        draft["channel_id"] = channel_id
        draft["editing"] = {"channel_id": channel_id, "message_id": message_id}
        # La mention n'est pas renvoyée lors d'une modification.
        await self.open_studio(interaction, draft, notice=notice)

    @annonce.command(name="programmees", description="Liste les annonces programmées (annuler ou reprendre).")
    async def programmees(self, interaction: discord.Interaction) -> None:
        records = await self.repository.list_scheduled(interaction.guild_id)

        if not records:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⏰ Annonces programmées",
                    description="Aucune annonce en attente. Programme-en une depuis `/annonce creer`.",
                    color=INFO_COLOR,
                ),
                ephemeral=True,
            )
            return

        lines = [
            f"**n°{r['id']}** · <t:{int(r['send_at'].timestamp())}:f> (<t:{int(r['send_at'].timestamp())}:R>) "
            f"· <#{r['channel_id']}> · {summary_title(r['data'])} · par <@{r['created_by']}>"
            for r in records
        ]
        await interaction.response.send_message(
            embed=discord.Embed(title="⏰ Annonces programmées", description="\n".join(lines), color=INFO_COLOR),
            view=ScheduledView(self, interaction.user.id, records),
            ephemeral=True,
        )

    @annonce.command(name="historique", description="Les dernières annonces publiées par le bot.")
    async def historique(self, interaction: discord.Interaction) -> None:
        records = await self.repository.list_history(interaction.guild_id)

        if not records:
            description = "Aucune annonce publiée avec le studio pour l'instant."
        else:
            description = "\n".join(
                f"<t:{int(r['created_at'].timestamp())}:d> · "
                f"[{r['title']}](https://discord.com/channels/{interaction.guild_id}/{r['channel_id']}/{r['message_id']}) "
                f"· <#{r['channel_id']}> · <@{r['author_id']}>"
                + (" · ⏰" if r["scheduled"] else "")
                + (f" · ✏️ modifiée <t:{int(r['edited_at'].timestamp())}:R>" if r["edited_at"] else "")
                for r in records
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="📜 Historique des annonces",
                description=description[:4096],
                color=INFO_COLOR,
            ).set_footer(text="Pour corriger une annonce : /annonce modifier <lien>"),
            ephemeral=True,
        )


class ScheduledView(discord.ui.View):
    def __init__(self, cog: AnnouncementCog, owner_id: int, records: list[dict[str, Any]]) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id

        options = [
            discord.SelectOption(
                label=f"n°{r['id']} · {summary_title(r['data'])}"[:100],
                value=str(r["id"]),
                description=r["send_at"].astimezone(cog.tz).strftime("Le %d/%m/%Y à %Hh%M"),
            )
            for r in records
        ]

        cancel = discord.ui.Select(placeholder="❌ Annuler un envoi…", options=options)
        cancel.callback = self.cancel
        self.add_item(cancel)

        resume = discord.ui.Select(
            placeholder="✏️ Reprendre dans le studio (l'envoi est annulé)…",
            options=[discord.SelectOption(label=o.label, value=o.value, description=o.description) for o in options],
        )
        resume.callback = self.resume
        self.add_item(resume)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def cancel(self, interaction: discord.Interaction) -> None:
        scheduled_id = int(interaction.data["values"][0])
        record = await self.cog.repository.cancel_scheduled(interaction.guild_id, scheduled_id)

        if record is None:
            await interaction.response.edit_message(
                embed=error_embed("Cette annonce a déjà été envoyée ou annulée."), view=None
            )
            return

        await self.cog.log(
            interaction.guild,
            f"🗑️ Annonce programmée n°{scheduled_id} annulée par {interaction.user.mention}.",
        )
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"🗑️ Annonce n°{scheduled_id} annulée : elle ne sera pas publiée.",
                color=SUCCESS_COLOR,
            ),
            view=None,
        )

    async def resume(self, interaction: discord.Interaction) -> None:
        scheduled_id = int(interaction.data["values"][0])
        record = await self.cog.repository.cancel_scheduled(interaction.guild_id, scheduled_id)

        if record is None:
            await interaction.response.edit_message(
                embed=error_embed("Cette annonce a déjà été envoyée ou annulée."), view=None
            )
            return

        notice = f"⏰ Envoi n°{scheduled_id} annulé : modifie l'annonce puis reprogramme-la."
        kept = await self.cog.keep_previous_draft(interaction.guild_id, interaction.user.id)

        if kept:
            notice += f"\n{kept}"

        draft = record["data"]
        draft["channel_id"] = int(record["channel_id"])
        draft["editing"] = None
        await self.cog.open_studio(interaction, draft, notice=notice)


async def setup(bot: commands.Bot) -> None:
    cog = AnnouncementCog(bot)
    await cog.repository.initialize()
    await bot.add_cog(cog)

    LOGGER.info("Studio d'annonces chargé")
