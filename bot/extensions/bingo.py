"""
Bingo : un administrateur lance « trouve le nombre » dans un salon.
Le premier qui trouve gagne la récompense. Plusieurs manches
possibles (un nouveau nombre à chaque fois), nombre d'essais limité
si on veut.

Les indices ne sont pas automatiques : l'admin qui lance reçoit le
nombre en privé (et à chaque nouvelle manche) et anime lui-même.
`/bingo nombre` le réaffiche. Qui connaît le nombre ne peut pas jouer.

Deux façons de jouer :
- **dans le salon** (par défaut) : les membres écrivent leurs nombres
  directement, autant qu'ils veulent ; 🎉 sur le bon nombre.
  Il faut « Message Content Intent » sur le Developer Portal ;
- **avec un bouton** (si le bot ne peut pas lire les messages) :
  « 🎯 Proposer un nombre » ouvre une fenêtre.

Pour encaisser le spam, l'état des bingos en cours est gardé en
mémoire ; seuls les essais sont recopiés en base toutes les quelques
secondes, et une victoire est validée en base (une seule fois).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.extensions.rappel import parse_duration
from bot.shared.economy import credit_progression, refresh_level_roles

LOGGER = logging.getLogger(__name__)

BINGO_COLOR = discord.Color.from_rgb(80, 200, 220)
DONE_COLOR = discord.Color.from_rgb(120, 120, 135)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

MAX_NUMBER = 1_000_000
MAX_REWARD = 1_000_000
MAX_ROUNDS = 10
DEFAULT_DURATION = timedelta(minutes=30)
MAX_DURATION = timedelta(days=1)
CHAT_COOLDOWN = 0.8  # secondes entre deux nombres d'un même membre (salon)
BUTTON_COOLDOWN = 2.0  # idem avec le bouton
EMBED_REFRESH = 5.0  # secondes minimum entre deux mises à jour du message

# Résultats d'une proposition.
WRONG, WIN, LATE, CLOSED, OUT_OF_RANGE, LIMIT, COOLDOWN, KNOWS = (
    "wrong", "win", "late", "closed", "out_of_range", "limit", "cooldown", "knows",
)


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
    """Le message entier doit être un nombre (« 42 », « 1 000 »)."""
    cleaned = re.sub(r"[\s  .]", "", text)
    return int(cleaned) if re.fullmatch(r"-?\d{1,9}", cleaned) else None


def build_bingo_embed(record: Any, *, guesses: int, players: int) -> discord.Embed:
    finished = record["status"] != "running"
    rounds = int(record["rounds"])
    current = int(record["round"])
    winners = list(record["winner_ids"] or [])
    found = list(record["found_numbers"] or [])
    chat = bool(record["chat_mode"])

    lines = []

    if record["note"]:
        lines += [str(record["note"]), ""]

    lines.append(
        f"🔢 Trouve le nombre entre **{format_number(record['min_value'])}** "
        f"et **{format_number(record['max_value'])}** !"
    )
    lines.append(
        f"🎁 Récompense : **{describe_reward(int(record['xp']), int(record['coins']))}** par nombre trouvé"
    )

    if rounds > 1:
        lines.append(f"🎱 Manche **{min(current, rounds)}/{rounds}**" if not finished else f"🎱 {rounds} manches")

    rules = [f"💬 Indices donnés par <@{record['created_by']}>"]

    if record["max_attempts"]:
        rules.append(f"🎯 {record['max_attempts']} essai(s) par manche")

    lines.append(" · ".join(rules))
    lines.append(f"👥 {players} joueur(s) · {guesses} proposition(s)")

    if winners:
        lines += ["", "**Gagnants :**"]
        lines += [
            f"• Manche {index} : <@{user_id}> avec **{format_number(number)}**"
            for index, (user_id, number) in enumerate(zip(winners, found), start=1)
        ]

    if finished:
        if record["status"] == "expired" and len(winners) < rounds:
            lines += ["", f"⌛ Temps écoulé ! Le nombre était **{format_number(record['secret'])}**."]
        elif record["status"] == "stopped" and len(winners) < rounds:
            lines += ["", f"🛑 Bingo arrêté. Le nombre était **{format_number(record['secret'])}**."]
        title, color = "🎱 Bingo terminé", DONE_COLOR
    else:
        how = (
            "✍️ **Écris tes nombres directement dans ce salon !**"
            if chat
            else "Clique sur **🎯 Proposer un nombre** !"
        )
        lines += ["", f"⏰ Fin <t:{int(record['ends_at'].timestamp())}:R> · {how}"]
        title, color = "🎱 BINGO !", BINGO_COLOR

    embed = discord.Embed(title=title, description="\n".join(lines), color=color)
    embed.set_footer(text=f"Bingo n°{record['id']} • Clan Renard")

    return embed


# ============================================================
# ÉTAT EN MÉMOIRE
# ============================================================


@dataclass
class BingoState:
    id: int
    guild_id: int
    channel_id: int
    low: int
    high: int
    secret: int
    round: int
    rounds: int
    hints: bool
    max_attempts: int
    xp: int
    coins: int
    ends_at: datetime
    chat_mode: bool
    created_by: int = 0
    knowers: set[int] = field(default_factory=set)  # qui connaît le nombre (ne peut pas jouer)
    attempts: dict[tuple[int, int], int] = field(default_factory=dict)  # (manche, membre) -> essais
    pending: dict[tuple[int, int], int] = field(default_factory=dict)  # à recopier en base
    players: set[int] = field(default_factory=set)
    guesses: int = 0
    limit_warned: set[tuple[int, int]] = field(default_factory=set)

    @classmethod
    def from_record(cls, record: Any) -> BingoState:
        return cls(
            id=int(record["id"]),
            guild_id=int(record["guild_id"]),
            channel_id=int(record["channel_id"]),
            low=int(record["min_value"]),
            high=int(record["max_value"]),
            secret=int(record["secret"]),
            round=int(record["round"]),
            rounds=int(record["rounds"]),
            hints=bool(record["hints"]),
            max_attempts=int(record["max_attempts"]),
            xp=int(record["xp"]),
            coins=int(record["coins"]),
            ends_at=record["ends_at"],
            chat_mode=bool(record["chat_mode"]),
            created_by=int(record["created_by"]),
            knowers={int(record["created_by"]), *(int(u) for u in (record["knower_ids"] or []))},
        )

    @property
    def open(self) -> bool:
        return self.ends_at > datetime.now(timezone.utc)


@dataclass
class GuessOutcome:
    kind: str
    number: int = 0
    attempts: int = 0
    secret: int = 0
    round: int = 0
    rounds: int = 0
    finished: bool = False
    left: int | None = None


# ============================================================
# BOUTON (mode sans lecture des messages)
# ============================================================


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
        await self.cog.guess_from_button(interaction, self.bingo_id, self.number.value)


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
            await interaction.response.send_message(embed=error_embed("Le bingo n'est pas chargé."), ephemeral=True)
            return

        await cog.open_guess(interaction, self.bingo_id)


def bingo_view(bingo_id: int, *, disabled: bool = False) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(GuessButton(bingo_id, disabled=disabled))
    return view


# ============================================================
# COG
# ============================================================


class BingoCog(commands.Cog):
    bingo = app_commands.Group(
        name="bingo",
        description="Bingo « trouve le nombre » avec récompense.",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.states: dict[int, BingoState] = {}
        self.by_channel: dict[int, int] = {}
        self.cooldowns: dict[tuple[int, int], float] = {}
        self.locks: dict[int, asyncio.Lock] = {}
        self.dirty: set[int] = set()
        self.background_tasks: set[asyncio.Task] = set()
        self.last_refresh: dict[int, float] = {}

    @property
    def can_read_messages(self) -> bool:
        intents = getattr(self.bot, "intents", None)
        return bool(getattr(intents, "message_content", False))

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
            "ALTER TABLE bingos ADD COLUMN IF NOT EXISTS chat_mode BOOLEAN NOT NULL DEFAULT FALSE"
        )
        await pool.execute(
            "ALTER TABLE bingos ADD COLUMN IF NOT EXISTS knower_ids BIGINT[] NOT NULL DEFAULT '{}'"
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
        try:
            for record in await self.get_pool().fetch("SELECT * FROM bingos WHERE status = 'running'"):
                await self.load_state(record)
        except Exception:
            LOGGER.exception("Bingos en cours non rechargés")

        if not self.loop.is_running():
            self.loop.start()

    def cog_unload(self) -> None:
        self.loop.cancel()

    async def load_state(self, record: Any) -> BingoState:
        state = BingoState.from_record(record)
        rows = await self.get_pool().fetch(
            "SELECT round, user_id, attempts FROM bingo_guesses WHERE bingo_id = $1", state.id
        )

        for row in rows:
            state.attempts[(int(row["round"]), int(row["user_id"]))] = int(row["attempts"])
            state.players.add(int(row["user_id"]))
            state.guesses += int(row["attempts"])

        self.states[state.id] = state
        self.by_channel[state.channel_id] = state.id
        return state

    def forget(self, bingo_id: int) -> None:
        state = self.states.pop(bingo_id, None)

        if state is not None and self.by_channel.get(state.channel_id) == bingo_id:
            self.by_channel.pop(state.channel_id, None)

        self.locks.pop(bingo_id, None)
        self.dirty.discard(bingo_id)

    def lock_for(self, bingo_id: int) -> asyncio.Lock:
        return self.locks.setdefault(bingo_id, asyncio.Lock())

    # ------------------------------------------------------------
    # PROPOSITIONS (logique commune)
    # ------------------------------------------------------------

    async def process(self, bingo_id: int, user_id: int, number: int, cooldown: float) -> GuessOutcome:
        state = self.states.get(bingo_id)

        if state is None or not state.open:
            return GuessOutcome(CLOSED)

        if user_id in state.knowers:
            return GuessOutcome(KNOWS)

        if not state.low <= number <= state.high:
            return GuessOutcome(OUT_OF_RANGE)

        now = time.monotonic()
        key = (bingo_id, user_id)

        if now - self.cooldowns.get(key, 0) < cooldown:
            return GuessOutcome(COOLDOWN)

        async with self.lock_for(bingo_id):
            if self.states.get(bingo_id) is not state or not state.open:
                return GuessOutcome(CLOSED)

            current = state.round
            attempt_key = (current, user_id)
            attempts = state.attempts.get(attempt_key, 0)

            if state.max_attempts and attempts >= state.max_attempts:
                return GuessOutcome(LIMIT, round=current, rounds=state.rounds)

            self.cooldowns[key] = now
            attempts += 1
            state.attempts[attempt_key] = attempts
            state.pending[attempt_key] = state.pending.get(attempt_key, 0) + 1
            state.players.add(user_id)
            state.guesses += 1
            self.dirty.add(bingo_id)
            left = state.max_attempts - attempts if state.max_attempts else None

            if number != state.secret:
                return GuessOutcome(WRONG, number=number, attempts=attempts, left=left)

            secret = state.secret
            finished = current >= state.rounds
            new_secret = random.randint(state.low, state.high)
            await self.flush(state)
            updated = await self.get_pool().fetchrow(
                """
                UPDATE bingos
                SET round = round + 1,
                    secret = CASE WHEN $3 THEN secret ELSE $4 END,
                    status = CASE WHEN $3 THEN 'finished' ELSE status END,
                    winner_ids = array_append(winner_ids, $2),
                    found_numbers = array_append(found_numbers, $5)
                WHERE id = $1 AND status = 'running' AND round = $6
                RETURNING id
                """,
                bingo_id,
                user_id,
                finished,
                new_secret,
                secret,
                current,
            )

            if updated is None:
                return GuessOutcome(LATE)

            if finished:
                self.forget(bingo_id)
            else:
                state.round += 1
                state.secret = new_secret
                task = asyncio.create_task(self.tell_knowers(state))
                self.background_tasks.add(task)
                task.add_done_callback(self.background_tasks.discard)

            return GuessOutcome(
                WIN,
                number=number,
                attempts=attempts,
                secret=secret,
                round=current,
                rounds=state.rounds,
                finished=finished,
            )

    async def reward(self, guild: discord.Guild, user: discord.abc.User, bingo_id: int, xp: int, coins: int) -> None:
        if not xp and not coins:
            return

        try:
            old_xp, new_xp = await credit_progression(
                self.bot.database,
                guild_id=guild.id,
                user_id=user.id,
                xp=xp,
                coins=coins,
                transaction_type="bingo",
                reason=f"Bingo n°{bingo_id}",
            )
            await refresh_level_roles(self.bot, guild.get_member(user.id), old_xp, new_xp)
        except Exception:
            LOGGER.exception("Récompense du bingo %s non versée", bingo_id)

    def win_text(self, user: discord.abc.User, outcome: GuessOutcome, xp: int, coins: int) -> str:
        lines = [
            f"🎉 **BINGO !** {user.mention} a trouvé le nombre **{format_number(outcome.secret)}** "
            f"en {outcome.attempts} essai(s) et gagne **{describe_reward(xp, coins)}** !"
        ]

        if not outcome.finished:
            lines.append(
                f"🎱 Manche **{outcome.round + 1}/{outcome.rounds}** : un nouveau nombre "
                "a été tiré, à vous de jouer !"
            )
        else:
            lines.append("🏁 Le bingo est terminé, merci d'avoir joué !")

        return "\n".join(lines)

    # ------------------------------------------------------------
    # PROPOSITIONS ÉCRITES DANS LE SALON
    # ------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        bingo_id = self.by_channel.get(message.channel.id)

        if bingo_id is None:
            return

        state = self.states.get(bingo_id)

        if state is None or not state.chat_mode:
            return

        number = parse_guess(message.content)

        if number is None:
            return  # discussion normale : ignorée

        outcome = await self.process(bingo_id, message.author.id, number, CHAT_COOLDOWN)

        try:
            if outcome.kind == KNOWS:
                warned = (0, message.author.id)

                if warned not in state.limit_warned:
                    state.limit_warned.add(warned)
                    await message.add_reaction("🤫")
            elif outcome.kind == LIMIT:
                warned = (outcome.round, message.author.id)

                if warned not in state.limit_warned:
                    state.limit_warned.add(warned)
                    await message.add_reaction("⛔")
            elif outcome.kind == WIN:
                await message.add_reaction("🎉")
                await message.reply(
                    self.win_text(message.author, outcome, state.xp, state.coins),
                    mention_author=True,
                )
        except discord.HTTPException:
            pass

        if outcome.kind == WIN:
            await self.reward(message.guild, message.author, bingo_id, state.xp, state.coins)
            await self.refresh_message(bingo_id)

    # ------------------------------------------------------------
    # PROPOSITIONS AVEC LE BOUTON
    # ------------------------------------------------------------

    async def open_guess(self, interaction: discord.Interaction, bingo_id: int) -> None:
        state = self.states.get(bingo_id)

        if state is None or not state.open:
            await interaction.response.send_message(embed=error_embed("Ce bingo est terminé."), ephemeral=True)
            return

        await interaction.response.send_modal(GuessModal(self, bingo_id, state.low, state.high))

    async def guess_from_button(self, interaction: discord.Interaction, bingo_id: int, text: str) -> None:
        state = self.states.get(bingo_id)
        number = parse_guess(text)

        if state is not None and number is None:
            await interaction.response.send_message(
                embed=error_embed(f"Écris un nombre entier entre {format_number(state.low)} et {format_number(state.high)}."),
                ephemeral=True,
            )
            return

        outcome = await self.process(bingo_id, interaction.user.id, number or 0, BUTTON_COOLDOWN)
        respond = interaction.response.send_message

        if outcome.kind == CLOSED:
            await respond(embed=error_embed("Ce bingo est terminé."), ephemeral=True)
        elif outcome.kind == OUT_OF_RANGE:
            await respond(
                embed=error_embed(f"Écris un nombre entre {format_number(state.low)} et {format_number(state.high)}."),
                ephemeral=True,
            )
        elif outcome.kind == COOLDOWN:
            await respond(embed=error_embed("Doucement ! Attends 2 secondes entre deux propositions."), ephemeral=True)
        elif outcome.kind == LIMIT:
            await respond(embed=error_embed(f"Tu as utilisé tes {state.max_attempts} essai(s) pour cette manche."), ephemeral=True)
        elif outcome.kind == KNOWS:
            await respond(embed=error_embed("Tu connais le nombre : tu ne peux pas jouer à ce bingo !"), ephemeral=True)
        elif outcome.kind == LATE:
            await respond(embed=error_embed("Trop tard, quelqu'un a été plus rapide !"), ephemeral=True)
        elif outcome.kind == WRONG:
            text = f"❌ Ce n'est pas {format_number(outcome.number)}."

            if outcome.left is not None:
                text += f" Il te reste {outcome.left} essai(s)."

            await respond(text, ephemeral=True)
        else:  # WIN
            await respond(f"🎉 **BINGO !** C'était bien **{format_number(outcome.secret)}** !", ephemeral=True)

            if interaction.channel is not None:
                try:
                    await interaction.channel.send(
                        self.win_text(interaction.user, outcome, state.xp, state.coins),
                        allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
                    )
                except discord.HTTPException:
                    pass

            await self.reward(interaction.guild, interaction.user, bingo_id, state.xp, state.coins)
            await self.refresh_message(bingo_id)

    # ------------------------------------------------------------
    # MESSAGE PUBLIC, BASE ET FIN
    # ------------------------------------------------------------

    async def tell_knowers(self, state: BingoState) -> None:
        """Nouvelle manche : l'animateur reçoit le nouveau nombre en privé."""
        guild = self.bot.get_guild(state.guild_id)

        if guild is None:
            return

        for user_id in list(state.knowers):
            member = guild.get_member(user_id)

            if member is None:
                continue

            try:
                await member.send(
                    f"🎱 Bingo n°{state.id}, manche **{state.round}/{state.rounds}** : "
                    f"le nouveau nombre est **{format_number(state.secret)}**. À toi de donner les indices !"
                )
            except discord.HTTPException:
                pass

    async def flush(self, state: BingoState) -> None:
        """Recopie les essais en base (appelé régulièrement et avant une victoire)."""
        if not state.pending:
            return

        pending, state.pending = state.pending, {}

        try:
            await self.get_pool().executemany(
                """
                INSERT INTO bingo_guesses (bingo_id, round, user_id, attempts)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (bingo_id, round, user_id)
                DO UPDATE SET attempts = bingo_guesses.attempts + EXCLUDED.attempts
                """,
                [(state.id, round_, user_id, count) for (round_, user_id), count in pending.items()],
            )
        except Exception:
            LOGGER.exception("Essais du bingo %s non enregistrés", state.id)

            for key, count in pending.items():
                state.pending[key] = state.pending.get(key, 0) + count

    async def counts(self, bingo_id: int) -> tuple[int, int]:
        state = self.states.get(bingo_id)

        if state is not None:
            return state.guesses, len(state.players)

        record = await self.get_pool().fetchrow(
            """
            SELECT COALESCE(SUM(attempts), 0) AS guesses, COUNT(DISTINCT user_id) AS players
            FROM bingo_guesses WHERE bingo_id = $1
            """,
            bingo_id,
        )
        return int(record["guesses"]), int(record["players"])

    async def refresh_message(self, bingo_id: int) -> None:
        record = await self.get_pool().fetchrow("SELECT * FROM bingos WHERE id = $1", bingo_id)

        if record is None or record["message_id"] is None:
            return

        channel = self.bot.get_channel(int(record["channel_id"]))

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        guesses, players = await self.counts(bingo_id)
        self.last_refresh[bingo_id] = time.monotonic()
        self.dirty.discard(bingo_id)
        running = record["status"] == "running"
        view = None if record["chat_mode"] else bingo_view(bingo_id, disabled=not running)

        try:
            await channel.get_partial_message(int(record["message_id"])).edit(
                embed=build_bingo_embed(record, guesses=guesses, players=players),
                view=view,
            )
        except discord.HTTPException:
            LOGGER.warning("Message du bingo %s non modifiable", bingo_id)

    async def stop_bingo(self, bingo_id: int, status: str) -> bool:
        async with self.lock_for(bingo_id):
            state = self.states.get(bingo_id)

            if state is not None:
                await self.flush(state)

            updated = await self.get_pool().fetchval(
                "UPDATE bingos SET status = $2 WHERE id = $1 AND status = 'running' RETURNING id",
                bingo_id,
                status,
            )

        if updated is None:
            return False

        guesses_players = await self.counts(bingo_id)
        self.forget(bingo_id)
        await self.refresh_message(bingo_id)

        if status == "expired" and guesses_players[0]:
            channel = self.bot.get_channel(state.channel_id) if state else None

            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                try:
                    await channel.send(
                        f"⌛ Fin du bingo ! Le nombre était **{format_number(state.secret)}**."
                    )
                except discord.HTTPException:
                    pass

        return True

    @tasks.loop(seconds=5)
    async def loop(self) -> None:
        for state in list(self.states.values()):
            if not state.open:
                try:
                    await self.stop_bingo(state.id, "expired")
                except Exception:
                    LOGGER.exception("Fin du bingo %s impossible", state.id)
                continue

            await self.flush(state)

        now = time.monotonic()

        for bingo_id in list(self.dirty):
            if now - self.last_refresh.get(bingo_id, 0) >= EMBED_REFRESH:
                try:
                    await self.refresh_message(bingo_id)
                except Exception:
                    LOGGER.exception("Mise à jour du bingo %s impossible", bingo_id)
                    self.dirty.discard(bingo_id)

        if len(self.cooldowns) > 5000:
            self.cooldowns = {k: v for k, v in self.cooldowns.items() if now - v < BUTTON_COOLDOWN}

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

        if target.id in self.by_channel:
            await interaction.response.send_message(
                embed=error_embed(
                    f"Un bingo (n°{self.by_channel[target.id]}) est déjà en cours dans {target.mention}. "
                    "Arrête-le avec `/bingo arreter` ou choisis un autre salon."
                ),
                ephemeral=True,
            )
            return

        chat_mode = self.can_read_messages
        warning = ""

        if chat_mode:
            perms = target.permissions_for(target.guild.me)

            if not perms.add_reactions or not perms.read_message_history:
                warning = (
                    "\n⚠️ Il me manque « Ajouter des réactions » ou « Voir les anciens messages » "
                    f"dans {target.mention} : je ne pourrai pas réagir aux propositions."
                )

        await interaction.response.defer(ephemeral=True, thinking=True)
        pool = self.get_pool()
        record = await pool.fetchrow(
            """
            INSERT INTO bingos (
                guild_id, channel_id, created_by, min_value, max_value, secret,
                xp, coins, rounds, hints, max_attempts, note, ends_at, chat_mode
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
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
            False,  # indices automatiques : remplacés par l'animateur
            int(attempts),
            message.strip() if message else None,
            datetime.now(timezone.utc) + delay,
            chat_mode,
        )

        try:
            kwargs: dict[str, Any] = {"embed": build_bingo_embed(record, guesses=0, players=0)}

            if not chat_mode:
                kwargs["view"] = bingo_view(int(record["id"]))

            sent = await target.send(**kwargs)
        except discord.HTTPException:
            await pool.execute("DELETE FROM bingos WHERE id = $1", record["id"])
            await interaction.followup.send(
                embed=error_embed(f"Je ne peux pas écrire dans {target.mention}."), ephemeral=True
            )
            return

        await pool.execute("UPDATE bingos SET message_id = $2 WHERE id = $1", record["id"], sent.id)
        await self.load_state(record)

        how = (
            "Les membres écrivent leurs nombres directement dans le salon."
            if chat_mode
            else "⚠️ Je ne peux pas lire les messages (Message Content Intent désactivé) : "
            "les membres passent par le bouton 🎯."
        )
        await interaction.followup.send(
            f"✅ Bingo n°{record['id']} lancé dans {target.mention} : nombre entre "
            f"{format_number(low)} et {format_number(high)}, {rounds} manche(s), "
            f"récompense {describe_reward(int(xp), int(coins))}. [Voir le bingo]({sent.jump_url})\n"
            f"{how}\n\n🤫 Le nombre à trouver est **{format_number(record['secret'])}** (garde-le pour toi). "
            "C'est toi qui donnes les indices dans le salon, et tu ne peux pas jouer à ce bingo. "
            "À chaque nouvelle manche, je t'envoie le nouveau nombre en privé "
            f"(ou fais `/bingo nombre`).{warning}",
            ephemeral=True,
        )

    @bingo.command(name="arreter", description="Arrête le bingo en cours et révèle le nombre.")
    @app_commands.rename(channel="salon")
    @app_commands.describe(channel="Salon du bingo (ce salon par défaut).")
    async def arreter(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        target = channel or interaction.channel
        bingo_id = self.by_channel.get(getattr(target, "id", 0))

        if bingo_id is None or not await self.stop_bingo(bingo_id, "stopped"):
            await interaction.response.send_message(
                embed=error_embed("Aucun bingo en cours dans ce salon."), ephemeral=True
            )
            return

        await interaction.response.send_message(f"🛑 Bingo n°{bingo_id} arrêté.", ephemeral=True)

    @bingo.command(name="nombre", description="Affiche en privé le nombre du bingo en cours (tu ne pourras plus jouer).")
    @app_commands.rename(channel="salon")
    @app_commands.describe(channel="Salon du bingo (ce salon par défaut).")
    async def nombre(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        target = channel or interaction.channel
        state = self.states.get(self.by_channel.get(getattr(target, "id", 0), 0))

        if state is None:
            await interaction.response.send_message(
                embed=error_embed("Aucun bingo en cours dans ce salon."), ephemeral=True
            )
            return

        if interaction.user.id not in state.knowers:
            state.knowers.add(interaction.user.id)
            await self.get_pool().execute(
                "UPDATE bingos SET knower_ids = array_append(knower_ids, $2) WHERE id = $1",
                state.id,
                interaction.user.id,
            )

        manche = f" (manche {state.round}/{state.rounds})" if state.rounds > 1 else ""
        await interaction.response.send_message(
            f"🤫 Le nombre du bingo n°{state.id}{manche} est **{format_number(state.secret)}**.\n"
            "Tu peux donner des indices dans le salon, mais tu ne peux plus jouer à ce bingo.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_dynamic_items(GuessButton)

    cog = BingoCog(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info("Bingo chargé")
