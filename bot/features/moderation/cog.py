"""
Commandes de modération et logique centrale des sanctions.

Toutes les sanctions (manuelles, automatiques ou de l'AutoMod) passent
par ModerationCog.sanction : action Discord, cas numéroté dans le
casier, message privé avec bouton de contestation, journal, puis
échelle de sanctions automatiques pour les avertissements.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.features.moderation import appeals
from bot.features.moderation.core import (
    APPEALABLE,
    BAN,
    FINE,
    KICK,
    MAXIMUM_BAN,
    MAXIMUM_MUTE,
    MUTE,
    UNBAN,
    UNMUTE,
    WARN,
    case_embed,
    dm_embed,
    format_duration,
    hierarchy_error,
    label,
    next_step,
    parse_sanction_duration,
    step_for,
    steps_from_json,
    utc_now,
)
from bot.features.moderation.repository import ModerationRepository
from bot.shared.economy import apply_signed_change, refresh_level_roles

LOGGER = logging.getLogger(__name__)

SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
INFO_COLOR = discord.Color.from_rgb(102, 179, 255)

DEFAULT_REASON = "Aucune raison indiquée."


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


def success_embed(text: str) -> discord.Embed:
    return discord.Embed(description=text, color=SUCCESS_COLOR)


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = ModerationRepository(bot.database)  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        if not self.tempban_loop.is_running():
            self.tempban_loop.start()

    def cog_unload(self) -> None:
        self.tempban_loop.cancel()

    # ============================================================
    # LOGIQUE CENTRALE
    # ============================================================

    async def send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
        *,
        view: discord.ui.View | None = None,
        channel_id: int | None = None,
    ) -> discord.Message | None:
        if channel_id is None:
            settings = await self.repository.get_settings(guild.id)
            channel_id = settings["log_channel_id"]

        if channel_id is None:
            return None

        channel = guild.get_channel(int(channel_id))

        if not isinstance(channel, discord.abc.Messageable):
            return None

        try:
            kwargs: dict[str, Any] = {"embed": embed}

            if view is not None:
                kwargs["view"] = view

            return await channel.send(**kwargs)
        except discord.HTTPException:
            LOGGER.warning("Journal de modération inaccessible sur %s", guild.id)
            return None

    async def notify_member(
        self,
        user: discord.abc.User,
        case: dict[str, Any],
        guild: discord.Guild,
    ) -> bool:
        settings = await self.repository.get_settings(guild.id)
        appeal_possible = (
            case["action"] in APPEALABLE
            and settings["appeal_channel_id"] is not None
        )

        try:
            await user.send(
                embed=dm_embed(case, guild.name, appeal_possible=appeal_possible),
                view=appeals.appeal_view(int(case["id"])) if appeal_possible else None,
            )
            return True
        except (discord.HTTPException, AttributeError):
            return False

    async def sanction(
        self,
        *,
        guild: discord.Guild,
        target: discord.Member | discord.User,
        moderator: discord.Member | None,
        action: str,
        reason: str | None,
        duration: timedelta | None = None,
        amount: int | None = None,
        delete_message_seconds: int = 0,
        escalate: bool = True,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """
        Applique une sanction. Retourne (cas, infos) ; cas vaut None si
        Discord a refusé l'action (infos["error"] explique pourquoi).
        """
        reason = (reason or "").strip() or DEFAULT_REASON
        moderator_id = moderator.id if moderator is not None else None
        audit_reason = (
            f"{moderator} : {reason}" if moderator is not None else f"Auto : {reason}"
        )[:500]
        info: dict[str, Any] = {"dm_sent": False, "escalation": None, "error": None}

        case = await self.repository.create_case(
            guild_id=guild.id,
            user_id=target.id,
            moderator_id=moderator_id,
            action=action,
            reason=reason,
            duration=duration,
            amount=amount,
            active=action not in {KICK},
        )

        try:
            # Prévenir AVANT d'expulser ou bannir : après, le bot ne
            # partage plus de serveur avec le membre.
            if action in {KICK, BAN}:
                info["dm_sent"] = await self.notify_member(target, case, guild)

            if action == MUTE:
                assert isinstance(target, discord.Member)
                await target.timeout(duration, reason=audit_reason)

            elif action == KICK:
                assert isinstance(target, discord.Member)
                await target.kick(reason=audit_reason)

            elif action == BAN:
                await guild.ban(
                    target,
                    reason=audit_reason,
                    delete_message_seconds=delete_message_seconds,
                )

            elif action == FINE:
                result = await apply_signed_change(
                    self.bot.database,  # type: ignore[attr-defined]
                    guild_id=guild.id,
                    user_id=target.id,
                    xp=0,
                    coins=-abs(int(amount or 0)),
                    transaction_type="fine",
                    reason=f"Amende (cas n°{case['id']}) : {reason}",
                )
                case["amount"] = -result["coins_delta"]
                await self.repository.set_amount(int(case["id"]), case["amount"])

        except (discord.HTTPException, AssertionError) as error:
            await self.repository.delete_case(int(case["id"]))
            info["error"] = (
                "Discord a refusé l'action : vérifie que j'ai la permission "
                "nécessaire et que mon rôle est au-dessus de celui du membre."
                if isinstance(error, discord.Forbidden)
                else f"L'action a échoué ({error.__class__.__name__})."
            )
            return None, info

        if action not in {KICK, BAN}:
            info["dm_sent"] = await self.notify_member(target, case, guild)

        await self.send_log(guild, case_embed(case))

        if action == WARN and escalate and isinstance(target, discord.Member):
            info["escalation"] = await self.escalate(guild, target)

        return case, info

    async def escalate(
        self,
        guild: discord.Guild,
        member: discord.Member,
    ) -> dict[str, Any] | None:
        """Applique le palier de l'échelle atteint par ce membre, s'il y en a un."""
        settings = await self.repository.get_settings(guild.id)
        steps = steps_from_json(settings["escalation"])
        warns = await self.repository.active_warn_count(
            guild.id,
            member.id,
            settings["warn_expiry_days"],
        )
        step = step_for(steps, warns)

        if step is None:
            return None

        me = guild.me

        if me is not None and member.top_role >= me.top_role:
            return {"step": step, "case": None, "warns": warns}

        case, _ = await self.sanction(
            guild=guild,
            target=member,
            moderator=None,
            action=step.action,
            reason=f"Sanction automatique : {warns} avertissements",
            duration=step.duration,
            escalate=False,
        )

        return {"step": step, "case": case, "warns": warns}

    async def revoke(
        self,
        guild: discord.Guild,
        case_id: int,
        *,
        moderator: discord.abc.User | None,
        reason: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Annule une sanction et répare ses effets (unmute, unban, remboursement)."""
        case = await self.repository.get_case(case_id)

        if case is None or int(case["guild_id"]) != guild.id:
            return None, f"Aucune sanction n°{case_id} sur ce serveur."

        if case["revoked_at"] is not None:
            return None, f"La sanction n°{case_id} est déjà annulée."

        if case["action"] in {UNMUTE, UNBAN}:
            return None, "Ce cas n'est pas une sanction."

        revoked = await self.repository.revoke_case(
            case_id,
            revoked_by=moderator.id if moderator is not None else None,
            reason=reason,
        )

        if revoked is None:
            return None, f"La sanction n°{case_id} est déjà annulée."

        user_id = int(case["user_id"])
        audit_reason = f"Annulation du cas n°{case_id} : {reason}"[:500]

        try:
            if case["action"] == MUTE and case["active"]:
                member = guild.get_member(user_id)

                if member is not None and member.is_timed_out():
                    await member.timeout(None, reason=audit_reason)

            elif case["action"] == BAN and case["active"]:
                await guild.unban(discord.Object(id=user_id), reason=audit_reason)

            elif case["action"] == FINE and case.get("amount"):
                result = await apply_signed_change(
                    self.bot.database,  # type: ignore[attr-defined]
                    guild_id=guild.id,
                    user_id=user_id,
                    xp=0,
                    coins=int(case["amount"]),
                    transaction_type="fine_refund",
                    reason=f"Remboursement de l'amende n°{case_id}",
                )
                await refresh_level_roles(
                    self.bot,
                    guild.get_member(user_id),
                    result["old_xp"],
                    result["new_xp"],
                )
        except discord.NotFound:
            pass
        except discord.HTTPException:
            LOGGER.warning("Effet de la sanction %s non annulé sur Discord", case_id)

        embed = discord.Embed(
            title=f"↩️ Sanction n°{case_id} annulée",
            description=(
                f"{label(str(case['action']))} de <@{user_id}>\n"
                f"**Raison de l'annulation :** {reason}"
            ),
            color=SUCCESS_COLOR,
            timestamp=utc_now(),
        )
        embed.add_field(
            name="Par",
            value=f"<@{moderator.id}>" if moderator else "🤖 Automatique",
        )
        await self.send_log(guild, embed)

        user = self.bot.get_user(user_id)

        if user is not None:
            try:
                await user.send(
                    embed=discord.Embed(
                        description=(
                            f"↩️ Ta sanction n°{case_id} ({label(str(case['action']))}) "
                            f"sur **{guild.name}** a été **annulée**."
                            + (
                                "\nTon amende t'a été remboursée."
                                if case["action"] == FINE and case.get("amount")
                                else ""
                            )
                        ),
                        color=SUCCESS_COLOR,
                    )
                )
            except discord.HTTPException:
                pass

        return revoked, None

    # ============================================================
    # CONTESTATIONS
    # ============================================================

    async def appeal_problem(self, case_id: int, user_id: int) -> str | None:
        case = await self.repository.get_case(case_id)

        if case is None or int(case["user_id"]) != user_id:
            return "❌ Cette sanction est introuvable."

        if case["revoked_at"] is not None:
            return "✅ Cette sanction a déjà été annulée."

        if case["appeal_status"] is not None:
            return "📨 Tu as déjà contesté cette sanction : une seule contestation est possible."

        settings = await self.repository.get_settings(int(case["guild_id"]))

        if settings["appeal_channel_id"] is None:
            return "❌ Les contestations ne sont plus acceptées sur ce serveur."

        return None

    async def submit_appeal(
        self,
        interaction: discord.Interaction,
        case_id: int,
        text: str,
    ) -> None:
        problem = await self.appeal_problem(case_id, interaction.user.id)

        if problem is not None:
            await interaction.response.send_message(problem, ephemeral=True)
            return

        if not await self.repository.set_appeal(
            case_id,
            status=appeals.PENDING,
            text=text,
            only_if_status=None,
        ):
            await interaction.response.send_message(
                "📨 Tu as déjà contesté cette sanction.",
                ephemeral=True,
            )
            return

        case = await self.repository.get_case(case_id)
        guild = self.bot.get_guild(int(case["guild_id"]))
        settings = await self.repository.get_settings(int(case["guild_id"]))
        sent = None

        if guild is not None:
            sent = await self.send_log(
                guild,
                appeals.appeal_embed(case, text),
                view=appeals.decision_view(case_id),
                channel_id=settings["appeal_channel_id"],
            )

        if sent is None:
            await self.repository.set_appeal(
                case_id,
                status=None,  # type: ignore[arg-type]
                only_if_status=appeals.PENDING,
            )
            await interaction.response.send_message(
                "❌ Ta contestation n'a pas pu être transmise. Réessaie plus tard.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "📨 Ta contestation a été envoyée à l'équipe de modération. "
            "Tu recevras la réponse ici.",
            ephemeral=True,
        )

    async def decide_appeal(
        self,
        interaction: discord.Interaction,
        case_id: int,
        accept: bool,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            return

        status = appeals.ACCEPTED if accept else appeals.REFUSED

        if not await self.repository.set_appeal(
            case_id,
            status=status,
            only_if_status=appeals.PENDING,
        ):
            await interaction.response.send_message(
                "Cette contestation a déjà été traitée.",
                ephemeral=True,
            )
            return

        case = await self.repository.get_case(case_id)
        await interaction.response.defer()

        if accept:
            await self.revoke(
                guild,
                case_id,
                moderator=interaction.user,
                reason="Contestation acceptée",
            )
        else:
            user = self.bot.get_user(int(case["user_id"]))

            if user is not None:
                try:
                    await user.send(
                        embed=discord.Embed(
                            description=(
                                f"❌ Ta contestation de la sanction n°{case_id} "
                                f"sur **{guild.name}** a été **refusée**. "
                                "La sanction est maintenue."
                            ),
                            color=ERROR_COLOR,
                        )
                    )
                except discord.HTTPException:
                    pass

        embed = interaction.message.embeds[0] if interaction.message.embeds else None

        if embed is not None:
            embed.color = SUCCESS_COLOR if accept else ERROR_COLOR
            embed.add_field(
                name="Décision",
                value=(
                    f"{'✅ Acceptée' if accept else '❌ Refusée'} par "
                    f"{interaction.user.mention}"
                ),
                inline=False,
            )

        try:
            await interaction.message.edit(
                embed=embed,
                view=appeals.decision_view(case_id, disabled=True),
            )
        except discord.HTTPException:
            pass

    # ============================================================
    # FIN DES BANNISSEMENTS TEMPORAIRES
    # ============================================================

    @tasks.loop(seconds=60)
    async def tempban_loop(self) -> None:
        try:
            cases = await self.repository.expired_tempbans()
        except Exception:
            LOGGER.exception("Impossible de lire les bannissements temporaires.")
            return

        for case in cases:
            guild = self.bot.get_guild(int(case["guild_id"]))

            if guild is None:
                continue

            try:
                await guild.unban(
                    discord.Object(id=int(case["user_id"])),
                    reason=f"Fin du bannissement temporaire (cas n°{case['id']})",
                )
            except discord.NotFound:
                pass
            except discord.HTTPException:
                LOGGER.warning("Débannissement automatique impossible : cas %s", case["id"])
                continue

            await self.repository.close_case(int(case["id"]))
            await self.send_log(
                guild,
                discord.Embed(
                    title="🕊️ Fin de bannissement temporaire",
                    description=(
                        f"<@{case['user_id']}> peut revenir sur le serveur "
                        f"(cas n°{case['id']})."
                    ),
                    color=SUCCESS_COLOR,
                    timestamp=utc_now(),
                ),
            )

    @tempban_loop.before_loop
    async def before_tempban_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ============================================================
    # OUTILS DES COMMANDES
    # ============================================================

    async def check_target(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        *,
        needs_bot_power: bool,
    ) -> bool:
        moderator = interaction.user

        if not isinstance(moderator, discord.Member):
            return False

        problem = hierarchy_error(
            moderator,
            target,
            needs_bot_power=needs_bot_power,
        )

        if problem is not None:
            await interaction.response.send_message(
                embed=error_embed(problem),
                ephemeral=True,
            )
            return False

        return True

    def confirmation(
        self,
        case: dict[str, Any],
        info: dict[str, Any],
        verb: str,
    ) -> discord.Embed:
        lines = [f"✅ {verb} — cas n°**{case['id']}**."]

        if case.get("duration_seconds"):
            lines.append(f"Durée : **{format_duration(case['duration_seconds'])}**.")

        if case["action"] == FINE:
            lines.append(
                f"Pièces retirées : **{int(case.get('amount') or 0):,}**.".replace(",", " ")
            )

        if not info["dm_sent"]:
            lines.append("📭 Le membre n'a pas pu être prévenu en message privé.")

        escalation = info.get("escalation")

        if escalation is not None:
            step = escalation["step"]

            if escalation["case"] is not None:
                lines.append(
                    f"⚡ **Échelle de sanctions** : {escalation['warns']} "
                    f"avertissements → {step.describe()} appliquée "
                    f"(cas n°{escalation['case']['id']})."
                )
            else:
                lines.append(
                    f"⚡ Palier de {escalation['warns']} avertissements atteint, "
                    "mais je n'ai pas pu appliquer la sanction automatique."
                )

        return success_embed("\n".join(lines))

    async def run(
        self,
        interaction: discord.Interaction,
        *,
        target: discord.Member | discord.User,
        action: str,
        reason: str | None,
        verb: str,
        duration: timedelta | None = None,
        amount: int | None = None,
        delete_message_seconds: int = 0,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        case, info = await self.sanction(
            guild=interaction.guild,  # type: ignore[arg-type]
            target=target,
            moderator=interaction.user,  # type: ignore[arg-type]
            action=action,
            reason=reason,
            duration=duration,
            amount=amount,
            delete_message_seconds=delete_message_seconds,
        )

        if case is None:
            await interaction.followup.send(embed=error_embed(info["error"]), ephemeral=True)
            return

        await interaction.followup.send(
            embed=self.confirmation(case, info, verb),
            ephemeral=True,
        )

    # ============================================================
    # COMMANDES
    # ============================================================

    @app_commands.command(name="warn", description="Donne un avertissement à un membre.")
    @app_commands.rename(member="membre", reason="raison")
    @app_commands.describe(member="Membre à avertir.", reason="Raison, visible par le membre.")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: app_commands.Range[str, 1, 400],
    ) -> None:
        if await self.check_target(interaction, member, needs_bot_power=False):
            await self.run(
                interaction,
                target=member,
                action=WARN,
                reason=reason,
                verb=f"{member.mention} a reçu un avertissement",
            )

    @app_commands.command(name="mute", description="Exclut temporairement un membre (il ne peut plus écrire ni parler).")
    @app_commands.rename(member="membre", duration="duree", reason="raison")
    @app_commands.describe(
        member="Membre à exclure.",
        duration="Durée : 10m, 2h, 3j… (28 jours maximum).",
        reason="Raison, visible par le membre.",
    )
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        try:
            delay = parse_sanction_duration(duration, maximum=MAXIMUM_MUTE)
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        if delay is None:
            await interaction.response.send_message(
                embed=error_embed("Indique une durée, par exemple `30m` ou `2h`."),
                ephemeral=True,
            )
            return

        if member.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=error_embed("Discord ne permet pas d'exclure un administrateur."),
                ephemeral=True,
            )
            return

        if await self.check_target(interaction, member, needs_bot_power=True):
            await self.run(
                interaction,
                target=member,
                action=MUTE,
                reason=reason,
                duration=delay,
                verb=f"{member.mention} est exclu temporairement",
            )

    @app_commands.command(name="unmute", description="Met fin à l'exclusion d'un membre.")
    @app_commands.rename(member="membre", reason="raison")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def unmute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        if not member.is_timed_out():
            await interaction.response.send_message(
                embed=error_embed(f"{member.mention} n'est pas exclu."),
                ephemeral=True,
            )
            return

        reason = reason or DEFAULT_REASON

        try:
            await member.timeout(None, reason=f"{interaction.user} : {reason}"[:500])
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("Discord a refusé : vérifie mes permissions et mon rôle."),
                ephemeral=True,
            )
            return

        latest = await self.repository.latest_active_case(interaction.guild_id, member.id, MUTE)

        if latest is not None:
            await self.repository.close_case(int(latest["id"]))

        case = await self.repository.create_case(
            guild_id=interaction.guild_id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action=UNMUTE,
            reason=reason,
            active=False,
        )
        await self.send_log(interaction.guild, case_embed(case))
        await interaction.response.send_message(
            embed=success_embed(f"🔊 {member.mention} peut de nouveau écrire et parler."),
            ephemeral=True,
        )

    @app_commands.command(name="kick", description="Expulse un membre du serveur (il peut revenir avec une invitation).")
    @app_commands.rename(member="membre", reason="raison")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        if await self.check_target(interaction, member, needs_bot_power=True):
            await self.run(
                interaction,
                target=member,
                action=KICK,
                reason=reason,
                verb=f"{member} a été expulsé",
            )

    @app_commands.command(name="ban", description="Bannit un membre, définitivement ou pour une durée (tempban).")
    @app_commands.rename(
        user="membre",
        duration="duree",
        reason="raison",
        delete_messages="supprimer_messages",
    )
    @app_commands.describe(
        user="Membre (ou identifiant) à bannir.",
        duration="Vide = définitif. Sinon : 1h, 3j, 2sem… (1 an maximum).",
        reason="Raison, visible par le membre.",
        delete_messages="Supprimer ses messages récents.",
    )
    @app_commands.choices(
        delete_messages=[
            app_commands.Choice(name="Ne rien supprimer", value=0),
            app_commands.Choice(name="Dernière heure", value=3600),
            app_commands.Choice(name="Dernières 24 heures", value=86400),
            app_commands.Choice(name="7 derniers jours", value=604800),
        ]
    )
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        duration: str | None = None,
        reason: app_commands.Range[str, 1, 400] | None = None,
        delete_messages: app_commands.Choice[int] | None = None,
    ) -> None:
        try:
            delay = parse_sanction_duration(duration, maximum=MAXIMUM_BAN)
        except ValueError as error:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
            return

        member = interaction.guild.get_member(user.id)  # type: ignore[union-attr]

        if member is not None and not await self.check_target(
            interaction,
            member,
            needs_bot_power=True,
        ):
            return

        await self.run(
            interaction,
            target=member or user,
            action=BAN,
            reason=reason,
            duration=delay,
            delete_message_seconds=delete_messages.value if delete_messages else 0,
            verb=(
                f"{user} est banni pour {format_duration(int(delay.total_seconds()))}"
                if delay
                else f"{user} est banni définitivement"
            ),
        )

    @app_commands.command(name="unban", description="Lève le bannissement d'un utilisateur.")
    @app_commands.rename(user_id="identifiant", reason="raison")
    @app_commands.describe(user_id="Identifiant Discord de l'utilisateur banni.")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        if not user_id.strip().isdigit():
            await interaction.response.send_message(
                embed=error_embed("Indique l'identifiant numérique de l'utilisateur."),
                ephemeral=True,
            )
            return

        guild = interaction.guild
        target = discord.Object(id=int(user_id))
        reason = reason or DEFAULT_REASON

        try:
            await guild.unban(target, reason=f"{interaction.user} : {reason}"[:500])
        except discord.NotFound:
            await interaction.response.send_message(
                embed=error_embed("Cet utilisateur n'est pas banni."),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("Discord a refusé : vérifie la permission « Bannir des membres »."),
                ephemeral=True,
            )
            return

        latest = await self.repository.latest_active_case(guild.id, target.id, BAN)

        if latest is not None:
            await self.repository.close_case(int(latest["id"]))

        case = await self.repository.create_case(
            guild_id=guild.id,
            user_id=target.id,
            moderator_id=interaction.user.id,
            action=UNBAN,
            reason=reason,
            active=False,
        )
        await self.send_log(guild, case_embed(case))
        await interaction.response.send_message(
            embed=success_embed(f"🕊️ <@{target.id}> n'est plus banni."),
            ephemeral=True,
        )

    @app_commands.command(name="amende", description="Retire des pièces à un membre, comme sanction.")
    @app_commands.rename(member="membre", amount="montant", reason="raison")
    @app_commands.describe(
        member="Membre à sanctionner.",
        amount="Pièces à retirer (le portefeuille ne descend pas sous 0).",
        reason="Raison, visible par le membre.",
    )
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def fine(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000],
        reason: app_commands.Range[str, 1, 400],
    ) -> None:
        if await self.check_target(interaction, member, needs_bot_power=False):
            await self.run(
                interaction,
                target=member,
                action=FINE,
                reason=reason,
                amount=int(amount),
                verb=f"{member.mention} a reçu une amende",
            )

    @app_commands.command(name="pardon", description="Annule une sanction (retire un avertissement, démute, débannit, rembourse).")
    @app_commands.rename(case_id="numero", reason="raison")
    @app_commands.describe(case_id="Numéro du cas (dans /casier ou le journal).")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def pardon(
        self,
        interaction: discord.Interaction,
        case_id: int,
        reason: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        case = await self.repository.get_case(case_id)

        if (
            case is not None
            and case["action"] == BAN
            and not interaction.user.guild_permissions.ban_members  # type: ignore[union-attr]
        ):
            await interaction.response.send_message(
                embed=error_embed("Il faut la permission « Bannir des membres » pour annuler un bannissement."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        revoked, problem = await self.revoke(
            interaction.guild,
            case_id,
            moderator=interaction.user,
            reason=reason or DEFAULT_REASON,
        )

        if revoked is None:
            await interaction.followup.send(embed=error_embed(problem), ephemeral=True)
            return

        await interaction.followup.send(
            embed=success_embed(
                f"↩️ Sanction n°{case_id} ({label(str(revoked['action']))}) "
                f"de <@{revoked['user_id']}> annulée."
            ),
            ephemeral=True,
        )

    @app_commands.command(name="casier", description="Affiche le casier de modération d'un membre.")
    @app_commands.rename(user="membre")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def casier(
        self,
        interaction: discord.Interaction,
        user: discord.User,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        embed = await self.build_record_embed(guild, user)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def build_record_embed(
        self,
        guild: discord.Guild,
        user: discord.abc.User,
    ) -> discord.Embed:
        settings = await self.repository.get_settings(guild.id)
        steps = steps_from_json(settings["escalation"])
        cases = await self.repository.member_cases(guild.id, user.id, limit=12)
        counts = await self.repository.count_by_action(guild.id, user.id)
        notes = await self.repository.member_notes(guild.id, user.id)
        warns = await self.repository.active_warn_count(
            guild.id,
            user.id,
            settings["warn_expiry_days"],
        )
        member = guild.get_member(user.id)

        embed = discord.Embed(
            title=f"📁 Casier de {user.display_name}",
            color=INFO_COLOR,
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        identity = [
            f"{user.mention} • `{user.id}`",
            f"Compte créé <t:{int(user.created_at.timestamp())}:R>",
        ]

        if member is not None and member.joined_at is not None:
            identity.append(f"Arrivé <t:{int(member.joined_at.timestamp())}:R>")

        status = "✅ Aucune sanction en cours"

        if member is None:
            try:
                await guild.fetch_ban(user)
                status = "🔨 Banni"
            except discord.HTTPException:
                status = "🚪 N'est pas sur le serveur"
        elif member.is_timed_out() and member.timed_out_until is not None:
            status = f"🔇 Exclu jusqu'à <t:{int(member.timed_out_until.timestamp())}:f>"

        identity.append(f"**État :** {status}")
        embed.description = "\n".join(identity)

        upcoming = next_step(steps, warns)
        warn_text = f"**{warns}** sur les {settings['warn_expiry_days']} derniers jours"

        if upcoming is not None:
            warn_text += (
                f"\nProchaine sanction automatique à **{upcoming.warns}** : "
                f"{upcoming.describe()}"
            )

        embed.add_field(name="⚠️ Avertissements actifs", value=warn_text, inline=False)

        totals = " · ".join(
            f"{label(action).split(' ')[0]} {counts[action]}"
            for action in (WARN, MUTE, KICK, BAN, FINE)
            if counts.get(action)
        )
        embed.add_field(name="Total", value=totals or "Casier vierge", inline=False)

        if cases:
            lines = []

            for case in cases:
                line = (
                    f"`#{case['id']}` {label(str(case['action']))} "
                    f"<t:{int(case['created_at'].timestamp())}:d>"
                )

                if case.get("duration_seconds"):
                    line += f" ({format_duration(case['duration_seconds'])})"

                if case.get("amount"):
                    line += f" ({case['amount']} pièces)"

                line += f" — {str(case.get('reason') or '')[:60]}"

                if case["revoked_at"] is not None:
                    line = f"~~{line}~~ ↩️"

                lines.append(line)

            embed.add_field(
                name="Historique (le plus récent en haut)",
                value="\n".join(lines)[:1024],
                inline=False,
            )

        if notes:
            embed.add_field(
                name="🗒️ Notes de l'équipe",
                value="\n".join(
                    f"`n{note['id']}` <t:{int(note['created_at'].timestamp())}:d> "
                    f"<@{note['author_id']}> : {note['content'][:120]}"
                    for note in notes
                )[:1024],
                inline=False,
            )

        embed.set_footer(text="Visible uniquement par toi • /pardon <numéro> pour annuler une sanction")

        return embed

    note = app_commands.Group(
        name="note",
        description="Notes privées de l'équipe de modération sur un membre.",
        default_permissions=discord.Permissions(moderate_members=True),
        guild_only=True,
    )

    @note.command(name="ajouter", description="Ajoute une note privée au casier d'un membre.")
    @app_commands.rename(user="membre", content="texte")
    async def note_add(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        content: app_commands.Range[str, 1, 500],
    ) -> None:
        note_id = await self.repository.add_note(
            interaction.guild_id,
            user.id,
            interaction.user.id,
            content,
        )
        await interaction.response.send_message(
            embed=success_embed(
                f"🗒️ Note `n{note_id}` ajoutée au casier de {user.mention}. "
                "Le membre n'en est pas informé."
            ),
            ephemeral=True,
        )

    @note.command(name="supprimer", description="Supprime une note du casier.")
    @app_commands.rename(note_id="numero")
    @app_commands.describe(note_id="Numéro de la note (sans le n), visible dans /casier.")
    async def note_delete(
        self,
        interaction: discord.Interaction,
        note_id: int,
    ) -> None:
        deleted = await self.repository.delete_note(interaction.guild_id, note_id)
        await interaction.response.send_message(
            embed=(
                success_embed(f"🗑️ Note `n{note_id}` supprimée.")
                if deleted
                else error_embed(f"Aucune note n{note_id} sur ce serveur.")
            ),
            ephemeral=True,
        )

    @app_commands.command(name="clear", description="Supprime des messages récents dans ce salon.")
    @app_commands.rename(amount="nombre", member="membre")
    @app_commands.describe(
        amount="Nombre de messages à supprimer (100 maximum).",
        member="Ne supprimer que les messages de ce membre.",
    )
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        member: discord.Member | None = None,
    ) -> None:
        channel = interaction.channel

        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await interaction.response.send_message(
                embed=error_embed("Cette commande s'utilise dans un salon textuel."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        remaining = int(amount)

        def check(message: discord.Message) -> bool:
            nonlocal remaining

            if remaining <= 0 or message.pinned:
                return False

            if member is not None and message.author.id != member.id:
                return False

            remaining -= 1
            return True

        try:
            deleted = await channel.purge(
                limit=500 if member is not None else int(amount),
                check=check,
                before=interaction.created_at,
                reason=f"/clear par {interaction.user}",
            )
        except discord.HTTPException:
            await interaction.followup.send(
                embed=error_embed("Discord a refusé : vérifie la permission « Gérer les messages »."),
                ephemeral=True,
            )
            return

        await self.send_log(
            interaction.guild,
            discord.Embed(
                title="🧹 Messages supprimés",
                description=(
                    f"**{len(deleted)}** message(s) dans {channel.mention}"
                    + (f" de {member.mention}" if member else "")
                    + f"\nPar {interaction.user.mention}"
                ),
                color=INFO_COLOR,
                timestamp=utc_now(),
            ),
        )
        await interaction.followup.send(
            embed=success_embed(
                f"🧹 {len(deleted)} message(s) supprimé(s). Les messages épinglés sont conservés."
            ),
            ephemeral=True,
        )

    async def set_lock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None,
        reason: str | None,
        *,
        locked: bool,
    ) -> None:
        target = channel or interaction.channel

        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Choisis un salon textuel."),
                ephemeral=True,
            )
            return

        everyone = interaction.guild.default_role
        overwrite = target.overwrites_for(everyone)

        if locked and overwrite.send_messages is False:
            await interaction.response.send_message(
                embed=error_embed(f"{target.mention} est déjà verrouillé."),
                ephemeral=True,
            )
            return

        overwrite.send_messages = False if locked else None
        overwrite.send_messages_in_threads = False if locked else None
        overwrite.add_reactions = False if locked else None

        try:
            await target.set_permissions(
                everyone,
                overwrite=overwrite,
                reason=f"{'Verrouillage' if locked else 'Déverrouillage'} par {interaction.user}",
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=error_embed("Discord a refusé : vérifie la permission « Gérer les salons »."),
                ephemeral=True,
            )
            return

        text = (
            "🔒 **Salon verrouillé** par l'équipe de modération."
            + (f"\n**Raison :** {reason}" if reason else "")
            if locked
            else "🔓 **Salon déverrouillé**, vous pouvez de nouveau écrire."
        )

        try:
            await target.send(text)
        except discord.HTTPException:
            pass

        await self.send_log(
            interaction.guild,
            discord.Embed(
                description=f"{'🔒' if locked else '🔓'} {target.mention} "
                f"{'verrouillé' if locked else 'déverrouillé'} par {interaction.user.mention}"
                + (f"\n**Raison :** {reason}" if reason else ""),
                color=INFO_COLOR,
                timestamp=utc_now(),
            ),
        )
        await interaction.response.send_message(
            embed=success_embed(f"{target.mention} {'verrouillé' if locked else 'déverrouillé'}."),
            ephemeral=True,
        )

    @app_commands.command(name="lock", description="Verrouille un salon : les membres ne peuvent plus y écrire.")
    @app_commands.rename(channel="salon", reason="raison")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        reason: app_commands.Range[str, 1, 300] | None = None,
    ) -> None:
        await self.set_lock(interaction, channel, reason, locked=True)

    @app_commands.command(name="unlock", description="Déverrouille un salon.")
    @app_commands.rename(channel="salon")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await self.set_lock(interaction, channel, None, locked=False)
