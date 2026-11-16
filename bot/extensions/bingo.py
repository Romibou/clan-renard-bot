"""
Bingo : un administrateur lance « trouve le nombre » dans un salon.
Les membres proposent un nombre avec un bouton ; le premier qui
trouve gagne la récompense. Plusieurs manches possibles (un nouveau
nombre à chaque fois), indices « plus grand / plus petit » en privé,
nombre d'essais limité si on veut.

Le bouton passe par une fenêtre de saisie : le bot n'a pas besoin de
lire les messages du salon.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.extensions.rappel import parse_duration
from bot.shared.economy import credit_progression, refresh_level_roles

LOGGER = logging.getLogger(__name__)

BINGO_COLOR = discord.Color.from_rgb(80, 200, 220)
WIN_COLOR = discord.Color.from_rgb(88, 191, 126)
DONE_COLOR = discord.Color.from_rgb(120, 120, 135)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

MAX_NUMBER = 1_000_000
MAX_REWARD = 1_000_000
MAX_ROUNDS = 10
DEFAULT_DURATION = timedelta(minutes=30)
MAX_DURATION = timedelta(days=1)
GUESS_COOLDOWN = 2.0  # secondes entre deux propositions d'un même membre
EMBED_REFRESH = 5.0  # secondes minimum entre deux mises à jour du message


def format_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


def describe_reward(xp: int, coins: int) -> str:
    parts = []

    if coins:
        parts.append(f"{format_number(coins)} pièces")
    if xp:
        parts.append(f"{format_number(xp)} XP")

    return " et ".join(parts) if parts else "la gloire éternelle"


def parse_guess(text: str) -> int | None:
    cleaned = re.sub(r"[\s  .]", "", text)
    return int(cleaned) if re.fullmatch(r"-?\d{1,9}", cleaned) else None


def hint(guess: int, secret: int) -> str:
    return "⬆️ C'est **plus grand**" if guess < secret else "⬇️ C'est **plus petit**"


def build_bingo_embed(record, *, guesses: int, players: int) -> discord.Embed:
    finished = record["status"] != "running"
    rounds = int(record["rounds"])
    current = int(record["round"])
    winners = list(record["winner_ids"] or [])
    found = list(record["found_numbers"] or [])

    lines = []

    if record["note"]:
        lines += [str(record["note"]), ""]

    lines.append(
        f"🔢 Trouve le nombre entre **{format_number(record['min_value'])}** "
        f"et **{format_number(record['max_value'])}** !"
    )
    lines.append(f"🎁 Récompense : **{describe_reward(int(record['xp']), int(record['coins']))}** par nombre trouvé")

    if rounds > 1:
        lines.append(f"🎱 Manche **{min(current, rounds)}/{rounds}**" if not finished else f"🎱 {rounds} manches")

    rules = ["💡 Indices plus grand / plus petit (en privé)" if record["hints"] else "🙈 Sans indice"]

    if record["max_attempts"]:
        rules.append(f"🎯 {record['max_attempts']} essai(s) par manche")

    lines.append(" · ".join(rules))
    lines.append(f"👥 {players} joueur(s) · {guesses} proposition(s)")

    if winners:
        lines += ["", "**Gagnants :**"]
        lines += [
            f"• Manche {index}: <@{user_id}> avec **{format_number(number)}**"
            for index, (user_id, number) in enumerate(zip(winners, found), start=1)
        ]

    if finished:
        if record["status"] == "expired" and len(winners) < rounds:
            lines += ["", f"⌛ Temps écoulé ! Le nombre était **{format_number(record['secret'])}**."]
        elif record["status"] == "stopped" and len(winners) < rounds:
            lines += ["", f"🛑 Bingo arrêté. Le nombre était **{format_number(record['secret'])}**."]
        title, color = "🎱 Bingo terminé", DONE_COLOR
    else:
        lines += ["", f"⏰ Fin <t:{int(record['ends_at'].timestamp())}:R> · Clique sur **🎯 Proposer un nombre** !"]
        title, color = "🎱 BINGO !", BINGO_COLOR

    embed = discord.Embed(title=title, description="\n".join(lines), color=color)
    embed.set_footer(text=f"Bingo n°{record['id']} • Clan Renard")

    return embed


class GuessModal(discord.ui.Modal, title="🎯 Proposer un nombre"):
    def __init__(self, cog: BingoCog, bingo_id: int, low: int, high: int) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.bingo_id = bingo_id
        self.number = discord.ui.TextInput(
            label=f"Ton nombre ({format_number(low)} à {format_number(high)})"[:45],
            placeholder="42",
            max_length=12,
        )
        self.add_item(self.number)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.guess(interaction, self.bingo_id, self.number.value)


class GuessButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"bingo:guess:(?P<id>[0-9]+)",
):
    """Bouton persistant : fonctionne encore après un redémarrage."""

    def __init__(self, bingo_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Proposer un nombre" if not disabled else "Terminé",
                emoji="🎯",
                style=discord.ButtonStyle.success if not disabled else discord.ButtonStyle.secondary,
                custom_id=f"bingo:guess:{bingo_id}",
                disabled=disabled,
            )
        )
        self.bingo_id = bingo_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]) -> GuessButton:
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("BingoCog")

        if cog is None:
            await interaction.response.send_message(
                embed=error_embed("Le bingo n'est pas chargé."), ephemeral=True
            )
            return

        await cog.open_guess(interaction, self.bingo_id)


def bingo_view(bingo_id: int, *, disabled: bool = False) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(GuessButton(bingo_id, disabled=disabled))
    return view


class BingoCog(commands.Cog):
    bingo = app_commands.Group(
        name="bingo",
        description="Bingo « trouve le nombre » avec récompense.",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.cooldowns: dict[tuple[int, int], float] = {}
        self.locks: dict[int, asyncio.Lock] = {}
        self.dirty: set[int] = set()
        self.last_refresh: dict[int, float] = {}

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS bingos (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT,
                created_by BIGINT NOT NULL,
                min_value INTEGER NOT NULL,
                max_value INTEGER NOT NULL,
                secret INTEGER NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                coins INTEGER NOT NULL DEFAULT 0,
                rounds SMALLINT NOT NULL DEFAULT 1,
                round SMALLINT NOT NULL DEFAULT 1,
                hints BOOLEAN NOT NULL DEFAULT TRUE,
                max_attempts INTEGER NOT NULL DEFAULT 0,
                note VARCHAR(200),
                status VARCHAR(10) NOT NULL DEFAULT 'running',
                winner_ids BIGINT[] NOT NULL DEFAULT '{}',
                found_numbers INTEGER[] NOT NULL DEFAULT '{}',
                ends_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS bingo_guesses (
                bingo_id BIGINT NOT NULL REFERENCES bingos(id) ON DELETE CASCADE,
                round SMALLINT NOT NULL,
                user_id BIGINT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (bingo_id, round, user_id)
            )
            """
        )
        await pool.execute(
            "CREATE INDEX IF NOT EXISTS bingos_running_idx ON bingos (ends_at) WHERE status = 'running'"
        )

    async def cog_load(self) -> None:
        if not self.loop.is_running():
            self.loop.start()

    def cog_unload(self) -> None:
        self.loop.cancel()

    def lock_for(self, bingo_id: int) -> asyncio.Lock:
        return self.locks.setdefault(bingo_id, asyncio.Lock())

    # ------------------------------------------------------------
    # MESSAGE PUBLIC
    # ------------------------------------------------------------

    async def counts(self, bingo_id: int) -> tuple[int, int]:
        record = await self.get_pool().fetchrow(
            """
            SELECT COALESCE(SUM(attempts), 0) AS guesses, COUNT(DISTINCT user_id) AS players
            FROM bingo_guesses WHERE bingo_id = $1
            """,
            bingo_id,
        )
        return int(record["guesses"]), int(record["players"])

    async def refresh_message(self, bingo_id: int) -> None:
        pool = self.get_pool()
        record = await pool.fetchrow("SELECT * FROM bingos WHERE id = $1", bingo_id)

        if record is None or record["message_id"] is None:
            return

        channel = self.bot.get_channel(int(record["channel_id"]))

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        guesses, players = await self.counts(bingo_id)
        self.last_refresh[bingo_id] = time.monotonic()
        self.dirty.discard(bingo_id)

        try:
            await channel.get_partial_message(int(record["message_id"])).edit(
                embed=build_bingo_embed(record, guesses=guesses, players=players),
                view=bingo_view(bingo_id, disabled=record["status"] != "running"),
            )
        except discord.HTTPException:
            LOGGER.warning("Message du bingo %s non modifiable", bingo_id)

    # ------------------------------------------------------------
    # PROPOSITIONS
    # ------------------------------------------------------------

    async def open_guess(self, interaction: discord.Interaction, bingo_id: int) -> None:
        record = await self.get_pool().fetchrow(
            "SELECT status, min_value, max_value, ends_at FROM bingos WHERE id = $1", bingo_id
        )

        if record is None or record["status"] != "running" or record["ends_at"] <= datetime.now(timezone.utc):
            await interaction.response.send_message(
                embed=error_embed("Ce bingo est terminé."), ephemeral=True
            )
            return

        await interaction.response.send_modal(
            GuessModal(self, bingo_id, int(record["min_value"]), int(record["max_value"]))
        )

    async def guess(self, interaction: discord.Interaction, bingo_id: int, text: str) -> None:
        user = interaction.user
        number = parse_guess(text)
        now = time.monotonic()
        key = (bingo_id, user.id)

        if now - self.cooldowns.get(key, 0) < GUESS_COOLDOWN:
            await interaction.response.send_message(
                embed=error_embed("Doucement ! Attends 2 secondes entre deux propositions."),
                ephemeral=True,
            )
            return

        async with self.lock_for(bingo_id):
            pool = self.get_pool()
            record = await pool.fetchrow("SELECT * FROM bingos WHERE id = $1", bingo_id)

            if record is None or record["status"] != "running" or record["ends_at"] <= datetime.now(timezone.utc):
                await interaction.response.send_message(embed=error_embed("Ce bingo est terminé."), ephemeral=True)
                return

            low, high = int(record["min_value"]), int(record["max_value"])

            if number is None or not low <= number <= high:
                await interaction.response.send_message(
                    embed=error_embed(f"Propose un nombre entier entre {format_number(low)} et {format_number(high)}."),
                    ephemeral=True,
                )
                return

            current_round = int(record["round"])
            attempts = int(
                await pool.fetchval(
                    "SELECT attempts FROM bingo_guesses WHERE bingo_id = $1 AND round = $2 AND user_id = $3",
                    bingo_id,
                    current_round,
                    user.id,
                )
                or 0
            )
            limit = int(record["max_attempts"])

            if limit and attempts >= limit:
                await interaction.response.send_message(
                    embed=error_embed(
                        f"Tu as utilisé tes {limit} essai(s) pour cette manche. "
                        + ("Attends la manche suivante !" if current_round < int(record["rounds"]) else "")
                    ),
                    ephemeral=True,
                )
                return

            self.cooldowns[key] = now
            attempts += 1
            await pool.execute(
                """
                INSERT INTO bingo_guesses (bingo_id, round, user_id, attempts)
                VALUES ($1, $2, $3, 1)
                ON CONFLICT (bingo_id, round, user_id)
                DO UPDATE SET attempts = bingo_guesses.attempts + 1
                """,
                bingo_id,
                current_round,
                user.id,
            )

            secret = int(record["secret"])

            if number != secret:
                left = f" Il te reste {limit - attempts} essai(s)." if limit else ""
                text_hint = f"{hint(number, secret)} que {format_number(number)}." if record["hints"] else (
                    f"❌ Ce n'est pas {format_number(number)}."
                )
                await interaction.response.send_message(text_hint + left, ephemeral=True)
                self.dirty.add(bingo_id)
                return

            # Trouvé !
            finished = current_round >= int(record["rounds"])
            new_secret = random.randint(low, high)
            updated = await pool.fetchrow(
                """
                UPDATE bingos
                SET round = round + 1,
                    secret = CASE WHEN $3 THEN secret ELSE $4 END,
                    status = CASE WHEN $3 THEN 'finished' ELSE status END,
                    winner_ids = array_append(winner_ids, $2),
                    found_numbers = array_append(found_numbers, $5)
                WHERE id = $1 AND status = 'running' AND round = $6
                RETURNING *
                """,
                bingo_id,
                user.id,
                finished,
                new_secret,
                secret,
                current_round,
            )

            if updated is None:
                await interaction.response.send_message(embed=error_embed("Trop tard, quelqu'un a été plus rapide !"), ephemeral=True)
                return

            await interaction.response.send_message(
                f"🎉 **BINGO !** C'était bien **{format_number(secret)}** !", ephemeral=True
            )

        xp, coins = int(record["xp"]), int(record["coins"])

        if xp or coins:
            try:
                old_xp, new_xp = await credit_progression(
                    self.bot.database,
                    guild_id=interaction.guild_id,
                    user_id=user.id,
                    xp=xp,
                    coins=coins,
                    transaction_type="bingo",
                    reason=f"Bingo n°{bingo_id}",
                )
                await refresh_level_roles(self.bot, interaction.guild.get_member(user.id), old_xp, new_xp)
            except Exception:
                LOGGER.exception("Récompense du bingo %s non versée", bingo_id)

        channel = interaction.channel
        lines = [
            f"🎉 {user.mention} a trouvé le nombre **{format_number(secret)}** en {attempts} essai(s) "
            f"et gagne **{describe_reward(xp, coins)}** !"
        ]

        if not finished:
            lines.append(
                f"🎱 Manche **{current_round + 1}/{record['rounds']}** : un nouveau nombre a été tiré, à vous de jouer !"
            )

        if channel is not None:
            try:
                await channel.send(
                    "\n".join(lines),
                    allowed_mentions=discord.AllowedMentions(users=[user]),
                )
            except discord.HTTPException:
                pass

        await self.refresh_message(bingo_id)

    # ------------------------------------------------------------
    # FIN ET BOUCLE
    # ------------------------------------------------------------

    async def stop_bingo(self, bingo_id: int, status: str) -> bool:
        async with self.lock_for(bingo_id):
            updated = await self.get_pool().fetchval(
                "UPDATE bingos SET status = $2 WHERE id = $1 AND status = 'running' RETURNING id",
                bingo_id,
                status,
            )

        if updated is None:
            return False

        await self.refresh_message(bingo_id)
        self.locks.pop(bingo_id, None)
        return True

    @tasks.loop(seconds=5)
    async def loop(self) -> None:
        try:
            expired = await self.get_pool().fetch(
                "SELECT id FROM bingos WHERE status = 'running' AND ends_at <= NOW()"
            )

            for record in expired:
                await self.stop_bingo(int(record["id"]), "expired")
        except Exception:
            LOGGER.exception("Fin des bingos impossible")

        now = time.monotonic()

        for bingo_id in list(self.dirty):
            if now - self.last_refresh.get(bingo_id, 0) >= EMBED_REFRESH:
                try:
                    await self.refresh_message(bingo_id)
                except Exception:
                    LOGGER.exception("Mise à jour du bingo %s impossible", bingo_id)
                    self.dirty.discard(bingo_id)

        # Ménage des délais anti-spam.
        if len(self.cooldowns) > 5000:
            self.cooldowns = {k: v for k, v in self.cooldowns.items() if now - v < GUESS_COOLDOWN}

    @loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------
    # COMMANDES
    # ------------------------------------------------------------

    @bingo.command(name="lancer", description="Lance un bingo « trouve le nombre » dans un salon.")
    @app_commands.rename(
        coins="pieces",
        low="minimum",
        high="maximum",
        rounds="manches",
        duration="duree",
        hints="indices",
        attempts="essais",
        channel="salon",
    )
    @app_commands.describe(
        coins="Pièces gagnées par chaque gagnant.",
        xp="XP gagnée par chaque gagnant.",
        low="Plus petit nombre possible (1 par défaut).",
        high="Plus grand nombre possible (100 par défaut).",
        rounds="Nombre de manches : un nouveau nombre et un nouveau gagnant à chaque fois.",
        duration="Durée maximale (30m par défaut, 1j maximum).",
        hints="Dire en privé « plus grand / plus petit » (oui par défaut).",
        attempts="Essais par membre et par manche (0 = illimité).",
        message="Texte affiché sur le bingo.",
        channel="Salon du bingo (ce salon par défaut).",
    )
    async def lancer(
        self,
        interaction: discord.Interaction,
        coins: app_commands.Range[int, 0, MAX_REWARD] = 0,
        xp: app_commands.Range[int, 0, MAX_REWARD] = 0,
        low: app_commands.Range[int, -MAX_NUMBER, MAX_NUMBER] = 1,
        high: app_commands.Range[int, -MAX_NUMBER, MAX_NUMBER] = 100,
        rounds: app_commands.Range[int, 1, MAX_ROUNDS] = 1,
        duration: str | None = None,
        hints: bool = True,
        attempts: app_commands.Range[int, 0, 1000] = 0,
        message: app_commands.Range[str, 1, 200] | None = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if high - low < 1:
            await interaction.response.send_message(
                embed=error_embed("Le maximum doit être plus grand que le minimum."), ephemeral=True
            )
            return

        delay = DEFAULT_DURATION if duration is None else parse_duration(duration)

        if delay is None or not timedelta(minutes=1) <= delay <= MAX_DURATION:
            await interaction.response.send_message(
                embed=error_embed("Durée invalide : entre 1 minute et 1 jour, par exemple `30m` ou `2h`."),
                ephemeral=True,
            )
            return

        target = channel or interaction.channel

        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                embed=error_embed("Choisis un salon textuel avec l'option `salon`."), ephemeral=True
            )
            return

        pool = self.get_pool()
        running = await pool.fetchval(
            "SELECT id FROM bingos WHERE channel_id = $1 AND status = 'running'", target.id
        )

        if running:
            await interaction.response.send_message(
                embed=error_embed(
                    f"Un bingo (n°{running}) est déjà en cours dans {target.mention}. "
                    "Arrête-le avec `/bingo arreter` ou choisis un autre salon."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        record = await pool.fetchrow(
            """
            INSERT INTO bingos (
                guild_id, channel_id, created_by, min_value, max_value, secret,
                xp, coins, rounds, hints, max_attempts, note, ends_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *
            """,
            interaction.guild_id,
            target.id,
            interaction.user.id,
            int(low),
            int(high),
            random.randint(int(low), int(high)),
            int(xp),
            int(coins),
            int(rounds),
            bool(hints),
            int(attempts),
            message.strip() if message else None,
            datetime.now(timezone.utc) + delay,
        )

        try:
            sent = await target.send(
                embed=build_bingo_embed(record, guesses=0, players=0),
                view=bingo_view(int(record["id"])),
            )
        except discord.HTTPException:
            await pool.execute("DELETE FROM bingos WHERE id = $1", record["id"])
            await interaction.followup.send(
                embed=error_embed(f"Je ne peux pas écrire dans {target.mention}."), ephemeral=True
            )
            return

        await pool.execute("UPDATE bingos SET message_id = $2 WHERE id = $1", record["id"], sent.id)
        await interaction.followup.send(
            f"✅ Bingo n°{record['id']} lancé dans {target.mention} : nombre entre "
            f"{format_number(low)} et {format_number(high)}, {rounds} manche(s), "
            f"récompense {describe_reward(int(xp), int(coins))}. [Voir le bingo]({sent.jump_url})\n"
            "🤫 Le nombre est tiré au hasard : même toi tu ne le connais pas !",
            ephemeral=True,
        )

    @bingo.command(name="arreter", description="Arrête le bingo en cours et révèle le nombre.")
    @app_commands.rename(channel="salon")
    @app_commands.describe(channel="Salon du bingo (ce salon par défaut).")
    async def arreter(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        target = channel or interaction.channel
        bingo_id = await self.get_pool().fetchval(
            "SELECT id FROM bingos WHERE channel_id = $1 AND status = 'running'",
            getattr(target, "id", 0),
        )

        if bingo_id is None or not await self.stop_bingo(int(bingo_id), "stopped"):
            await interaction.response.send_message(
                embed=error_embed("Aucun bingo en cours dans ce salon."), ephemeral=True
            )
            return

        await interaction.response.send_message(f"🛑 Bingo n°{bingo_id} arrêté.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    bot.add_dynamic_items(GuessButton)

    cog = BingoCog(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info("Bingo chargé")
