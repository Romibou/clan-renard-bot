from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.config import Settings
from bot.core.database import Database
from bot.core.extension_loader import load_extensions
from bot.core.health import HealthServer


logger = logging.getLogger(__name__)


class ClanRenardBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()

        # Utile pour l'attribution de rôles et les futurs modules.
        # Il faut également activer Server Members Intent sur le
        # Discord Developer Portal.
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            owner_id=settings.owner_id,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                roles=True,
                users=True,
                replied_user=False,
            ),
        )

        self.settings = settings
        self.database = Database(
            settings.database_url,
            settings.project_root,
        )
        self.health_server = HealthServer(self, settings.port)

    async def setup_hook(self) -> None:
        await self.database.connect()
        await self.database.apply_schema()
        await load_extensions(self)
        await self.health_server.start()
        await self._sync_application_commands()

    async def _sync_application_commands(self) -> None:
        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)

            # Copie les commandes globales dans le serveur de test.
            # Elles apparaissent alors généralement en quelques secondes.
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)

            logger.info(
                "%s commande(s) synchronisée(s) sur le serveur de test %s",
                len(synced),
                self.settings.dev_guild_id,
            )
            return

        synced = await self.tree.sync()
        logger.info(
            "%s commande(s) globale(s) synchronisée(s)",
            len(synced),
        )

    async def on_ready(self) -> None:
        if self.user is None:
            return

        logger.info(
            "Bot connecté : %s (%s) | %s serveur(s)",
            self.user,
            self.user.id,
            len(self.guilds),
        )

        activity = discord.Game(name="Bot du Clan Renard")
        await self.change_presence(
            status=discord.Status.online,
            activity=activity,
        )

    async def close(self) -> None:
        await self.health_server.stop()
        await self.database.close()
        await super().close()

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.exception(
            "Erreur de commande d'application",
            exc_info=error,
        )

        if isinstance(error, app_commands.MissingPermissions):
            message = (
                "❌ Tu n'as pas les permissions nécessaires "
                "pour utiliser cette commande."
            )
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            message = (
                "❌ Il me manque des permissions Discord : "
                f"`{missing}`."
            )
        elif isinstance(error, app_commands.CommandOnCooldown):
            message = (
                "⏳ Cette commande est temporairement limitée. "
                f"Réessaie dans {error.retry_after:.1f} seconde(s)."
            )
        elif isinstance(error, app_commands.CheckFailure):
            message = (
                "❌ Tu ne peux pas utiliser cette commande ici."
            )
        else:
            message = (
                "❌ Une erreur inattendue est survenue. "
                "L'erreur a été enregistrée dans les logs du bot."
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    message,
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    message,
                    ephemeral=True,
                )
        except discord.HTTPException:
            logger.exception(
                "Impossible d'envoyer le message d'erreur à Discord"
            )
