from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands


LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)


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


def base_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=COLOR,
    )


class ReactionRoleCog(
    commands.Cog
):
    """
    Système de rôles à la réaction.

    Une commande lie un message, un émoji et un rôle. Le bot ajoute
    lui-même la réaction sur le message ciblé. Ensuite, ajouter cette
    réaction donne le rôle, la retirer le retire.
    """

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    def get_pool(self):
        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            raise RuntimeError(
                "Le gestionnaire PostgreSQL est indisponible."
            )

        return database.require_pool()

    async def initialize_database(
        self,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_roles (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,

                emoji TEXT NOT NULL,
                role_id BIGINT NOT NULL,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                UNIQUE (
                    message_id,
                    emoji
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS reaction_roles_message_idx
            ON reaction_roles (
                message_id
            )
            """
        )

        LOGGER.info(
            "Table des rôles à la réaction vérifiée"
        )

    async def get_binding(
        self,
        *,
        message_id: int,
        emoji: str,
    ):
        pool = self.get_pool()

        return await pool.fetchrow(
            """
            SELECT
                guild_id,
                role_id
            FROM reaction_roles
            WHERE message_id = $1
              AND emoji = $2
            """,
            message_id,
            emoji,
        )

    async def upsert_binding(
        self,
        *,
        guild_id: int,
        channel_id: int,
        message_id: int,
        emoji: str,
        role_id: int,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            INSERT INTO reaction_roles (
                guild_id,
                channel_id,
                message_id,
                emoji,
                role_id
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (message_id, emoji)
            DO UPDATE SET
                role_id = EXCLUDED.role_id,
                channel_id = EXCLUDED.channel_id,
                updated_at = NOW()
            """,
            guild_id,
            channel_id,
            message_id,
            emoji,
            role_id,
        )

    async def delete_binding(
        self,
        *,
        message_id: int,
        emoji: str,
    ) -> bool:
        pool = self.get_pool()

        result = await pool.execute(
            """
            DELETE FROM reaction_roles
            WHERE message_id = $1
              AND emoji = $2
            """,
            message_id,
            emoji,
        )

        return result != "DELETE 0"

    async def list_bindings(
        self,
        guild_id: int,
    ) -> list:
        pool = self.get_pool()

        return await pool.fetch(
            """
            SELECT
                channel_id,
                message_id,
                emoji,
                role_id
            FROM reaction_roles
            WHERE guild_id = $1
            ORDER BY message_id, emoji
            """,
            guild_id,
        )

    # ------------------------------------------------------------
    # ÉCOUTE DES RÉACTIONS
    # ------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> None:
        if payload.guild_id is None:
            return

        if payload.member is not None and payload.member.bot:
            return

        try:
            record = await self.get_binding(
                message_id=payload.message_id,
                emoji=str(payload.emoji),
            )
        except RuntimeError:
            return

        if record is None:
            return

        guild = self.bot.get_guild(
            payload.guild_id
        )

        if guild is None:
            return

        role = guild.get_role(
            record["role_id"]
        )

        if role is None:
            LOGGER.warning(
                "Rôle %s introuvable pour la réaction-rôle "
                "du message %s",
                record["role_id"],
                payload.message_id,
            )
            return

        member = payload.member

        if member is None:
            try:
                member = await guild.fetch_member(
                    payload.user_id
                )
            except discord.HTTPException:
                return

        try:
            await member.add_roles(
                role,
                reason="Rôle à la réaction",
            )
        except discord.HTTPException:
            LOGGER.exception(
                "Impossible de donner le rôle %s à %s "
                "(réaction-rôle).",
                role.id,
                member.id,
            )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> None:
        if payload.guild_id is None:
            return

        try:
            record = await self.get_binding(
                message_id=payload.message_id,
                emoji=str(payload.emoji),
            )
        except RuntimeError:
            return

        if record is None:
            return

        guild = self.bot.get_guild(
            payload.guild_id
        )

        if guild is None:
            return

        role = guild.get_role(
            record["role_id"]
        )

        if role is None:
            return

        try:
            member = await guild.fetch_member(
                payload.user_id
            )
        except discord.HTTPException:
            return

        if member.bot:
            return

        try:
            await member.remove_roles(
                role,
                reason="Réaction-rôle retirée",
            )
        except discord.HTTPException:
            LOGGER.exception(
                "Impossible de retirer le rôle %s à %s "
                "(réaction-rôle).",
                role.id,
                member.id,
            )

    # ------------------------------------------------------------
    # COMMANDES
    # ------------------------------------------------------------

    @app_commands.command(
        name="reaction-role",
        description=(
            "Lie une réaction sur un message à un rôle à distribuer."
        ),
    )
    @app_commands.describe(
        message_id="L'identifiant du message à utiliser.",
        emoji="L'émoji sur lequel réagir (classique ou personnalisé).",
        role="Le rôle à donner quand on réagit avec cet émoji.",
        channel=(
            "Le salon contenant le message "
            "(le salon actuel par défaut)."
        ),
    )
    @app_commands.default_permissions(
        manage_roles=True
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    @app_commands.guild_only()
    async def reaction_role(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Serveur requis",
                    "Cette commande doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        target_channel = channel or interaction.channel

        if not isinstance(
            target_channel,
            discord.TextChannel,
        ):
            await interaction.followup.send(
                embed=error_embed(
                    "Salon invalide",
                    (
                        "Précise un salon textuel valide avec "
                        "le paramètre `channel`."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not message_id.isdigit():
            await interaction.followup.send(
                embed=error_embed(
                    "Identifiant invalide",
                    (
                        "`message_id` doit être l'identifiant "
                        "numérique du message (clic droit sur le "
                        "message → Copier l'identifiant)."
                    ),
                ),
                ephemeral=True,
            )
            return

        try:
            message = await target_channel.fetch_message(
                int(message_id)
            )
        except discord.NotFound:
            await interaction.followup.send(
                embed=error_embed(
                    "Message introuvable",
                    (
                        f"Aucun message avec l'identifiant "
                        f"`{message_id}` n'a été trouvé dans "
                        f"{target_channel.mention}."
                    ),
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                embed=error_embed(
                    "Erreur",
                    "Le message n'a pas pu être récupéré.",
                ),
                ephemeral=True,
            )
            return

        try:
            partial_emoji = discord.PartialEmoji.from_str(
                emoji
            )
        except Exception:
            await interaction.followup.send(
                embed=error_embed(
                    "Émoji invalide",
                    (
                        "Je n'ai pas reconnu cet émoji. Utilise un "
                        "émoji classique ou un émoji personnalisé "
                        "de ce serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        try:
            await message.add_reaction(
                partial_emoji
            )
        except discord.HTTPException:
            await interaction.followup.send(
                embed=error_embed(
                    "Réaction impossible",
                    (
                        "Je n'ai pas pu ajouter cette réaction. "
                        "Vérifie que j'ai la permission "
                        "**Ajouter des réactions** et que l'émoji "
                        "vient bien de ce serveur (ou est standard)."
                    ),
                ),
                ephemeral=True,
            )
            return

        emoji_key = str(
            partial_emoji
        )

        try:
            await self.upsert_binding(
                guild_id=guild.id,
                channel_id=target_channel.id,
                message_id=message.id,
                emoji=emoji_key,
                role_id=role.id,
            )
        except Exception:
            LOGGER.exception(
                "Impossible d'enregistrer la réaction-rôle "
                "pour le message %s.",
                message.id,
            )
            await interaction.followup.send(
                embed=error_embed(
                    "Erreur",
                    (
                        "La réaction a été ajoutée, mais la "
                        "association n'a pas pu être enregistrée."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=success_embed(
                "Rôle à la réaction configuré",
                (
                    f"La réaction {emoji_key} sur "
                    f"[ce message]({message.jump_url}) donne "
                    f"maintenant le rôle {role.mention}.\n\n"
                    "Je viens d'ajouter la réaction sur le message : "
                    "les membres n'ont plus qu'à cliquer dessus."
                ),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="reaction-role-retirer",
        description=(
            "Supprime une association réaction ↔ rôle existante."
        ),
    )
    @app_commands.describe(
        message_id="L'identifiant du message concerné.",
        emoji="L'émoji dont il faut retirer l'association.",
    )
    @app_commands.default_permissions(
        manage_roles=True
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    @app_commands.guild_only()
    async def reaction_role_remove(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
    ) -> None:
        if not message_id.isdigit():
            await interaction.response.send_message(
                embed=error_embed(
                    "Identifiant invalide",
                    "`message_id` doit être un identifiant numérique.",
                ),
                ephemeral=True,
            )
            return

        try:
            partial_emoji = discord.PartialEmoji.from_str(
                emoji
            )
        except Exception:
            await interaction.response.send_message(
                embed=error_embed(
                    "Émoji invalide",
                    "Je n'ai pas reconnu cet émoji.",
                ),
                ephemeral=True,
            )
            return

        deleted = await self.delete_binding(
            message_id=int(message_id),
            emoji=str(partial_emoji),
        )

        if not deleted:
            await interaction.response.send_message(
                embed=error_embed(
                    "Association introuvable",
                    (
                        "Aucune réaction-rôle ne correspond à "
                        "ce message et cet émoji."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Association supprimée",
                (
                    "La réaction ne donnera plus ce rôle. "
                    "Je n'ai pas retiré la réaction déjà posée "
                    "sur le message, seulement l'association."
                ),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="reaction-role-liste",
        description=(
            "Liste les associations réaction ↔ rôle du serveur."
        ),
    )
    @app_commands.default_permissions(
        manage_roles=True
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    @app_commands.guild_only()
    async def reaction_role_list(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    "Cette commande doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        records = await self.list_bindings(
            guild.id
        )

        if not records:
            await interaction.response.send_message(
                embed=base_embed(
                    "Rôles à la réaction",
                    "Aucune association n'est configurée sur ce serveur.",
                ),
                ephemeral=True,
            )
            return

        lines = []

        for record in records:
            role = guild.get_role(
                record["role_id"]
            )

            role_text = (
                role.mention if role is not None
                else f"rôle supprimé (`{record['role_id']}`)"
            )

            lines.append(
                f"{record['emoji']} → {role_text} "
                f"(message `{record['message_id']}` dans "
                f"<#{record['channel_id']}>)"
            )

        await interaction.response.send_message(
            embed=base_embed(
                "Rôles à la réaction",
                "\n".join(lines),
            ),
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    cog = ReactionRoleCog(
        bot
    )

    await cog.initialize_database()

    await bot.add_cog(
        cog
    )

    LOGGER.info(
        "Système de rôles à la réaction initialisé"
    )
