"""
Modération automatique.

- Filtres natifs de Discord (AutoMod) gérés par le bot : liens
  d'invitation, mots interdits, mentions de masse. Discord bloque le
  message lui-même, sans que le bot ait besoin de lire le contenu des
  messages ; le bot ajoute ensuite un avertissement (et l'échelle de
  sanctions s'applique).
- Anti-spam : trop de messages en peu de temps → exclusion temporaire
  et suppression des messages.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import timedelta
from typing import Any

import discord
from discord.ext import commands

from bot.features.moderation.core import MUTE, WARN

LOGGER = logging.getLogger(__name__)

RULE_PREFIX = "Clan Renard • "
INVITE_PATTERNS = [
    r"discord(?:app)?\.(?:gg|io|me|li|com/invite)/[a-z0-9-]+",
    r"dsc\.gg/[a-z0-9-]+",
]
RULE_REASONS = {
    "invites": "lien d'invitation vers un autre serveur",
    "words": "mot interdit",
    "mentions": "mentions de masse",
}
WARN_COOLDOWN_SECONDS = 60
SETTINGS_TTL_SECONDS = 60


def clean_words(text: str) -> list[str]:
    """« mot1, mot2\\nmot3 » → liste sans doublons, 60 caractères max par mot."""
    words: list[str] = []

    for part in text.replace("\n", ",").split(","):
        word = part.strip().lower()

        if word and len(word) <= 60 and word not in words:
            words.append(word)

    return words[:1000]


def desired_rules(automod: dict[str, Any]) -> dict[str, dict[str, Any] | None]:
    """Configuration de chaque règle AutoMod du bot (None = désactivée)."""
    rules: dict[str, dict[str, Any] | None] = {
        "invites": None,
        "words": None,
        "mentions": None,
    }

    if automod.get("invites"):
        rules["invites"] = {
            "name": f"{RULE_PREFIX}Liens d'invitation",
            "trigger": discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                regex_patterns=INVITE_PATTERNS,
            ),
            "message": "Les liens d'invitation vers d'autres serveurs sont interdits ici.",
        }

    if automod.get("words"):
        rules["words"] = {
            "name": f"{RULE_PREFIX}Mots interdits",
            "trigger": discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                keyword_filter=list(automod["words"]),
            ),
            "message": "Ton message contient un mot interdit sur ce serveur.",
        }

    if int(automod.get("mention_limit") or 0) > 0:
        rules["mentions"] = {
            "name": f"{RULE_PREFIX}Mentions de masse",
            "trigger": discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.mention_spam,
                mention_limit=int(automod["mention_limit"]),
            ),
            "message": "Trop de mentions dans un seul message.",
        }

    return rules


class AutomodCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._settings: dict[int, tuple[float, dict[str, Any]]] = {}
        self._recent: dict[tuple[int, int], deque] = {}
        self._warned: dict[tuple[int, int, str], float] = {}

    @property
    def moderation(self):
        return self.bot.get_cog("ModerationCog")

    async def settings(self, guild_id: int) -> dict[str, Any]:
        cached = self._settings.get(guild_id)

        if cached is not None and cached[0] > time.monotonic():
            return cached[1]

        settings = await self.moderation.repository.get_settings(guild_id)
        self._settings[guild_id] = (time.monotonic() + SETTINGS_TTL_SECONDS, settings)

        return settings

    def forget_settings(self, guild_id: int) -> None:
        self._settings.pop(guild_id, None)

    # ------------------------------------------------------------
    # Règles AutoMod de Discord
    # ------------------------------------------------------------

    async def sync_rules(self, guild: discord.Guild) -> str | None:
        """
        Crée, modifie ou supprime les règles AutoMod du bot pour
        correspondre aux réglages. Retourne un message d'erreur ou None.
        """
        repository = self.moderation.repository
        settings = await repository.get_settings(guild.id)
        rule_ids: dict[str, int] = {
            key: int(value) for key, value in settings["automod_rule_ids"].items()
        }

        try:
            existing = {rule.id: rule for rule in await guild.fetch_automod_rules()}
        except discord.Forbidden:
            return (
                "Je n'ai pas la permission « Gérer le serveur », nécessaire "
                "pour configurer l'AutoMod de Discord."
            )
        except discord.HTTPException:
            return "Discord n'a pas répondu, réessaie dans un instant."

        errors = []

        for key, wanted in desired_rules(settings["automod"]).items():
            rule = existing.get(rule_ids.get(key, 0))

            try:
                if wanted is None:
                    if rule is not None:
                        await rule.delete(reason="Désactivé dans /moderation-admin")
                    rule_ids.pop(key, None)
                    continue

                actions = [
                    discord.AutoModRuleAction(custom_message=wanted["message"]),
                ]

                if rule is not None:
                    await rule.edit(
                        name=wanted["name"],
                        trigger=wanted["trigger"],
                        actions=actions,
                        enabled=True,
                        reason="Mis à jour depuis /moderation-admin",
                    )
                else:
                    created = await guild.create_automod_rule(
                        name=wanted["name"],
                        event_type=discord.AutoModRuleEventType.message_send,
                        trigger=wanted["trigger"],
                        actions=actions,
                        enabled=True,
                        reason="Créé depuis /moderation-admin",
                    )
                    rule_ids[key] = created.id

            except discord.HTTPException as error:
                LOGGER.warning("Règle AutoMod %s non synchronisée : %s", key, error)
                errors.append(
                    f"{RULE_REASONS[key]} : Discord a refusé ({error.text or error.status})"
                )

        await repository.update_settings(guild.id, automod_rule_ids=rule_ids)
        self.forget_settings(guild.id)

        return " ; ".join(errors) or None

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction) -> None:
        if self.moderation is None:
            return

        try:
            settings = await self.settings(execution.guild_id)
        except Exception:
            return

        key = next(
            (
                name
                for name, rule_id in settings["automod_rule_ids"].items()
                if int(rule_id) == execution.rule_id
            ),
            None,
        )

        if key is None:
            return

        # Un seul avertissement par membre et par règle et par minute :
        # quelqu'un qui insiste n'enchaîne pas 10 avertissements d'un coup.
        cooldown_key = (execution.guild_id, execution.user_id, key)
        now = time.monotonic()

        if now - self._warned.get(cooldown_key, 0) < WARN_COOLDOWN_SECONDS:
            return

        self._warned[cooldown_key] = now

        guild = self.bot.get_guild(execution.guild_id)

        if guild is None:
            return

        member = guild.get_member(execution.user_id)

        if member is None or member.bot:
            return

        reason = f"AutoMod : {RULE_REASONS[key]}"

        if execution.matched_keyword and key == "words":
            reason += f" (« {execution.matched_keyword} »)"

        await self.moderation.sanction(
            guild=guild,
            target=member,
            moderator=None,
            action=WARN,
            reason=reason,
        )

    # ------------------------------------------------------------
    # Anti-spam
    # ------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild

        if (
            guild is None
            or message.author.bot
            or message.webhook_id is not None
            or not isinstance(message.author, discord.Member)
            or self.moderation is None
        ):
            return

        if message.author.guild_permissions.manage_messages:
            return

        try:
            automod = (await self.settings(guild.id))["automod"]
        except Exception:
            return

        limit = int(automod.get("spam_messages") or 0)

        if limit <= 0:
            return

        window = max(2, int(automod.get("spam_seconds") or 8))
        key = (guild.id, message.author.id)
        now = time.monotonic()
        recent = self._recent.setdefault(key, deque())
        recent.append((now, message))

        while recent and now - recent[0][0] > window:
            recent.popleft()

        if len(recent) < limit:
            return

        messages = [item[1] for item in recent]
        recent.clear()

        if message.author.is_timed_out():
            return

        minutes = max(1, int(automod.get("spam_mute_minutes") or 10))
        await self.moderation.sanction(
            guild=guild,
            target=message.author,
            moderator=None,
            action=MUTE,
            reason=f"Anti-spam : {len(messages)} messages en {window} secondes",
            duration=timedelta(minutes=minutes),
        )

        by_channel: dict[int, list[discord.Message]] = {}

        for spam in messages:
            by_channel.setdefault(spam.channel.id, []).append(spam)

        for channel_messages in by_channel.values():
            channel = channel_messages[0].channel

            try:
                if len(channel_messages) == 1:
                    await channel_messages[0].delete()
                else:
                    await channel.delete_messages(channel_messages)
            except (discord.HTTPException, AttributeError):
                pass
