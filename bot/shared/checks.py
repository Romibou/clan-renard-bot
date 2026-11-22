from __future__ import annotations

import discord
from discord import app_commands


def guild_only():
    async def predicate(
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage()

        return True

    return app_commands.check(predicate)


# Permissions qu'un rôle distribué automatiquement (réaction, boutique,
# arrivée, niveau, anniversaire, Avent…) ne doit jamais donner : sinon
# n'importe quel membre pourrait obtenir des pouvoirs de modération.
DANGEROUS_PERMISSIONS = (
    ("administrator", "Administrateur"),
    ("manage_guild", "Gérer le serveur"),
    ("manage_roles", "Gérer les rôles"),
    ("manage_channels", "Gérer les salons"),
    ("manage_webhooks", "Gérer les webhooks"),
    ("manage_messages", "Gérer les messages"),
    ("manage_nicknames", "Gérer les pseudos"),
    ("manage_expressions", "Gérer les expressions"),
    ("manage_events", "Gérer les événements"),
    ("manage_threads", "Gérer les fils"),
    ("kick_members", "Expulser des membres"),
    ("ban_members", "Bannir des membres"),
    ("moderate_members", "Exclure temporairement des membres"),
    ("mention_everyone", "Mentionner @everyone"),
    ("view_audit_log", "Voir les logs du serveur"),
)


def unsafe_role_reason(role: discord.Role, actor: discord.abc.User | None = None) -> str | None:
    """
    Raison pour laquelle ce rôle ne doit pas être distribué par le bot,
    ou None s'il n'y a pas de problème.

    - rôle @everyone ou géré par une intégration ;
    - rôle qui donne des permissions de modération ou d'administration ;
    - rôle placé au même niveau ou au-dessus du rôle le plus haut de
      `actor` (Discord interdit à un modérateur de donner un tel rôle :
      le bot ne doit pas servir à contourner cette règle). Le
      propriétaire du serveur n'est pas concerné.
    """
    if role.is_default():
        return "le rôle @everyone ne peut pas être distribué"

    if role.managed:
        return f"{role.mention} est géré par Discord ou une intégration"

    dangerous = [label for name, label in DANGEROUS_PERMISSIONS if getattr(role.permissions, name, False)]

    if dangerous:
        return (
            f"{role.mention} donne des permissions sensibles ({', '.join(dangerous[:3])}"
            + ("…" if len(dangerous) > 3 else "")
            + ") : il ne peut pas être distribué automatiquement"
        )

    guild = getattr(role, "guild", None)
    top_role = getattr(actor, "top_role", None)

    if (
        actor is not None
        and top_role is not None
        and guild is not None
        and getattr(guild, "owner_id", None) != actor.id
        and role >= top_role
    ):
        return f"{role.mention} est au même niveau ou au-dessus de ton rôle le plus haut"

    return None
