"""
Mini-jeux : morpion, puissance 4 et pierre-feuille-ciseaux, contre
un membre ou contre l'IA.

Contre un membre, on peut miser des pièces : le défié doit accepter
(ou proposer une autre mise, que le défieur doit alors accepter).
Les deux mises sont retirées des portefeuilles au début de la partie
et le gagnant récupère le tout. Égalité = chacun est remboursé.
Une partie interrompue par un redémarrage du bot est remboursée.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.features.minigames.engines import (
    COLUMNS,
    EASY,
    HARD,
    NORMAL,
    ROWS,
    RPS_CHOICES,
    RPS_EMOJIS,
    ConnectFour,
    RockPaperScissors,
    TicTacToe,
    connect_four_ai_move,
    rps_ai_move,
    tictactoe_ai_move,
)
from bot.features.minigames.hangman import Hangman, base_letter, pick_word
from bot.shared.members import present_member_ids

LOGGER = logging.getLogger(__name__)

MORPION, PUISSANCE4, PFC, PENDU = "morpion", "puissance4", "pfc", "pendu"
GAME_NAMES = {
    MORPION: "❌⭕ Morpion",
    PUISSANCE4: "🔴🟡 Puissance 4",
    PFC: "🪨📄✂️ Pierre-feuille-ciseaux",
    PENDU: "🔤 Pendu",
}

MAX_STAKE = 100_000
CHALLENGE_TIMEOUT = timedelta(minutes=3)
# Le bouton 🔁 Revanche reste disponible ce temps-là après la fin d'une partie.
REMATCH_WINDOW = timedelta(minutes=10)

# Tâches lancées en arrière-plan : asyncio ne garde qu'une référence
# faible, on les retient donc ici jusqu'à leur fin.
BACKGROUND_TASKS: set[asyncio.Future] = set()


def keep_task(task: asyncio.Future) -> asyncio.Future:
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return task
MOVE_TIMEOUT = timedelta(minutes=2)
RPS_ROUND_TIMEOUT = timedelta(seconds=60)

GAME_COLOR = discord.Color.from_rgb(120, 140, 255)
WIN_COLOR = discord.Color.from_rgb(88, 191, 126)
DRAW_COLOR = discord.Color.from_rgb(150, 150, 160)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)

AI_NAME = "🤖 l'IA"


def format_coins(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {text}", color=ERROR_COLOR)


MEDALS = ("🥇", "🥈", "🥉")


def leaderboard_lines(rows: list[Any], metric: str) -> list[str]:
    """Une ligne par joueur, dans l'ordre du classement."""
    lines = []

    for index, row in enumerate(rows):
        rank = MEDALS[index] if index < 3 else f"**{index + 1}.**"
        wins, losses, draws = int(row["wins"]), int(row["losses"]), int(row["draws"])

        if metric == "coins_net":
            coins = int(row["coins_net"])
            detail = f"**{'+' if coins >= 0 else '−'}{format_coins(abs(coins))}** pièces · {wins} V / {losses} D"
        elif metric == "ai_wins":
            detail = f"**{int(row['ai_wins'])}** victoires · {int(row['ai_losses'])} défaites"
        else:
            played = wins + losses + draws
            ratio = f" · {round(100 * wins / played)} %" if played else ""
            detail = f"**{wins}** V · {losses} D · {draws} N{ratio}"

        lines.append(f"{rank} <@{int(row['user_id'])}> — {detail}")

    return lines


class BetError(Exception):
    """Mise impossible (portefeuille insuffisant…)."""


def player_name(user_id: int | None) -> str:
    return AI_NAME if user_id is None else f"<@{user_id}>"


# ============================================================
# DÉFI ENTRE MEMBRES
# ============================================================


class StakeModal(discord.ui.Modal, title="💬 Proposer une autre mise"):
    def __init__(self, challenge: ChallengeView) -> None:
        super().__init__(timeout=300)
        self.challenge = challenge
        self.amount = discord.ui.TextInput(
            label="Mise de chaque joueur (0 = sans mise)",
            default=str(challenge.stake),
            max_length=7,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = self.amount.value.replace(" ", "")

        if not text.isdigit() or int(text) > MAX_STAKE:
            await interaction.response.send_message(
                embed=error_embed(f"Écris un nombre entre 0 et {format_coins(MAX_STAKE)}."),
                ephemeral=True,
            )
            return

        await self.challenge.counter_offer(interaction, int(text))


class ChallengeView(discord.ui.View):
    """Message public : « A défie B ». Celui qui doit répondre est `waiting_for`."""

    def __init__(
        self,
        cog: GamesCog,
        game: str,
        challenger: discord.Member,
        opponent: discord.Member,
        stake: int,
        options: dict[str, Any],
    ) -> None:
        super().__init__(timeout=CHALLENGE_TIMEOUT.total_seconds())
        self.cog = cog
        self.game = game
        self.challenger = challenger
        self.opponent = opponent
        self.stake = stake
        self.options = options
        self.waiting_for = opponent
        self.message: discord.Message | None = None
        self.closed = False
        self.lock = asyncio.Lock()

    def embed(self) -> discord.Embed:
        lines = [f"{self.challenger.mention} défie {self.opponent.mention} !"]

        if self.game == PFC:
            lines.append(f"Au meilleur des **{self.options['best_of']}** manche(s).")

        if self.stake:
            lines += [
                "",
                f"💰 Mise : **{format_coins(self.stake)} pièces** chacun",
                f"🏆 Le gagnant remporte **{format_coins(self.stake * 2)} pièces**.",
            ]
        else:
            lines += ["", "🎲 Partie amicale, sans mise."]

        lines += [
            "",
            f"👉 {self.waiting_for.mention}, à toi de répondre "
            f"(<t:{int((datetime.now(timezone.utc) + CHALLENGE_TIMEOUT).timestamp())}:R>).",
        ]

        return discord.Embed(
            title=f"{GAME_NAMES[self.game]} — Défi",
            description="\n".join(lines),
            color=GAME_COLOR,
        )

    def players(self) -> set[int]:
        return {self.challenger.id, self.opponent.id}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.players():
            await interaction.response.send_message(
                embed=error_embed("Ce défi ne te concerne pas. Lance le tien avec `/jeu` !"),
                ephemeral=True,
            )
            return False

        return True

    async def close(self, embed: discord.Embed) -> None:
        self.closed = True
        self.stop()
        self.cog.release(self.challenger.guild.id, self.players())

        if self.message is not None:
            try:
                await self.message.edit(content=None, embed=embed, view=None)
            except discord.HTTPException:
                pass

    async def on_timeout(self) -> None:
        if not self.closed:
            await self.close(
                discord.Embed(
                    title=f"{GAME_NAMES[self.game]} — Défi expiré",
                    description=f"⌛ {self.waiting_for.mention} n'a pas répondu à temps.",
                    color=DRAW_COLOR,
                )
            )

    @discord.ui.button(label="Accepter", emoji="✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.lock:
            if self.closed:
                return

            if interaction.user.id != self.waiting_for.id:
                await interaction.response.send_message(
                    embed=error_embed(f"C'est à {self.waiting_for.mention} d'accepter."),
                    ephemeral=True,
                )
                return

            try:
                match_id = await self.cog.take_stakes(
                    interaction.guild_id, self.challenger.id, self.opponent.id, self.stake, self.game
                )
            except BetError as error:
                await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
                return
            except Exception:
                LOGGER.exception("Mise impossible à prélever")
                await interaction.response.send_message(
                    embed=error_embed("Impossible de prélever les mises pour l'instant. Réessaie."),
                    ephemeral=True,
                )
                return

            self.closed = True
            self.stop()

        players = [self.challenger.id, self.opponent.id]
        random.shuffle(players)
        view = self.cog.create_game(
            self.game,
            players=players,
            stake=self.stake,
            match_id=match_id,
            guild_id=interaction.guild_id,
            options=self.options,
        )
        await interaction.response.edit_message(
            content=" ".join(f"<@{user_id}>" for user_id in players),
            embed=view.embed(),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True),
        )
        view.message = await interaction.original_response()
        view.start()

    @discord.ui.button(label="Autre mise", emoji="💬", style=discord.ButtonStyle.primary)
    async def other_stake(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.waiting_for.id:
            await interaction.response.send_message(
                embed=error_embed(f"C'est à {self.waiting_for.mention} de répondre."),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(StakeModal(self))

    async def counter_offer(self, interaction: discord.Interaction, amount: int) -> None:
        async with self.lock:
            if self.closed:
                await interaction.response.send_message(
                    embed=error_embed("Ce défi est terminé."), ephemeral=True
                )
                return

            wallet = await self.cog.get_wallet(interaction.guild_id, interaction.user.id)

            if amount > wallet:
                await interaction.response.send_message(
                    embed=error_embed(f"Tu n'as que **{format_coins(wallet)} pièces**."),
                    ephemeral=True,
                )
                return

            self.stake = amount
            self.waiting_for = self.challenger if interaction.user.id == self.opponent.id else self.opponent
            # Le délai repart pour l'autre joueur.
            self.timeout = CHALLENGE_TIMEOUT.total_seconds()
            await interaction.response.edit_message(
                content=f"{self.waiting_for.mention}, {interaction.user.mention} propose une autre mise.",
                embed=self.embed(),
                view=self,
                allowed_mentions=discord.AllowedMentions(users=[self.waiting_for]),
            )

    @discord.ui.button(label="Refuser", emoji="✖️", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.lock:
            if self.closed:
                return

            word = "annulé" if interaction.user.id == self.challenger.id else "refusé"
            await interaction.response.defer()
            await self.close(
                discord.Embed(
                    title=f"{GAME_NAMES[self.game]} — Défi {word}",
                    description=f"{interaction.user.mention} a {word} le défi.",
                    color=DRAW_COLOR,
                )
            )


# ============================================================
# PARTIES
# ============================================================


class GameView(discord.ui.View):
    """
    Base commune : deux joueurs (None = IA), délai par coup,
    abandon, fin de partie et paiement.
    """

    game = ""

    def __init__(
        self,
        cog: GamesCog,
        *,
        players: list[int | None],
        stake: int,
        match_id: int | None,
        guild_id: int,
        options: dict[str, Any],
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.players = players
        self.stake = stake
        self.match_id = match_id
        self.guild_id = guild_id
        self.difficulty = options.get("difficulty", NORMAL)
        self.message: discord.Message | None = None
        self.deadline = datetime.now(timezone.utc) + MOVE_TIMEOUT
        self.over = False
        self.result_text = ""
        self.lock = asyncio.Lock()
        self.watchdog: asyncio.Task | None = None
        self.options = dict(options)
        self.rematch_button: discord.ui.Button | None = None
        self.rematch_closed = False
        self.rematch_timer: asyncio.TimerHandle | None = None

    # -------- outils --------

    @property
    def vs_ai(self) -> bool:
        return None in self.players

    def humans(self) -> set[int]:
        return {user_id for user_id in self.players if user_id is not None}

    def header(self) -> list[str]:
        lines = []

        if self.vs_ai:
            lines.append(f"Difficulté : **{self.difficulty}**")

        if self.stake:
            lines.append(
                f"💰 Mise : {format_coins(self.stake)} pièces chacun · "
                f"🏆 {format_coins(self.stake * 2)} pour le gagnant"
            )

        return lines

    def reset_deadline(self, delay: timedelta = MOVE_TIMEOUT) -> None:
        self.deadline = datetime.now(timezone.utc) + delay

    def start(self) -> None:
        self.watchdog = asyncio.create_task(self.watch())

    async def watch(self) -> None:
        try:
            while not self.over:
                remaining = (self.deadline - datetime.now(timezone.utc)).total_seconds()

                if remaining > 0:
                    await asyncio.sleep(min(remaining, 15))
                    continue

                async with self.lock:
                    if not self.over and datetime.now(timezone.utc) >= self.deadline:
                        await self.on_deadline()
        except asyncio.CancelledError:
            pass
        except Exception:
            LOGGER.exception("Surveillance de partie interrompue")

    async def on_deadline(self) -> None:
        raise NotImplementedError

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.humans():
            await interaction.response.send_message(
                embed=error_embed("Tu ne joues pas dans cette partie. Lance la tienne avec `/jeu` !"),
                ephemeral=True,
            )
            return False

        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: Any, /) -> None:
        LOGGER.exception("Erreur dans un mini-jeu", exc_info=error)

        try:
            await interaction.followup.send(embed=error_embed("Erreur inattendue."), ephemeral=True)
        except discord.HTTPException:
            pass

    async def refresh(self, interaction: discord.Interaction | None = None) -> None:
        self.ensure_rematch_button()
        kwargs = {"embed": self.embed(), "view": self}

        if interaction is not None and not interaction.response.is_done():
            await interaction.response.edit_message(**kwargs)
        elif self.message is not None:
            try:
                await self.message.edit(**kwargs)
            except discord.HTTPException:
                LOGGER.warning("Message de partie non modifiable")

    def embed(self) -> discord.Embed:
        raise NotImplementedError

    def disable_all(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def end(self, winner_index: int, reason: str) -> None:
        """winner_index : 1 ou 2 (joueur gagnant), 0 = égalité ou partie annulée."""
        if self.over:
            return

        self.over = True
        self.disable_all()
        self.schedule_rematch_expiry()
        winner = self.players[winner_index - 1] if winner_index else None
        loser = self.players[2 - winner_index] if winner_index else None

        lines = [reason]

        if self.stake and self.match_id is not None:
            if winner_index:
                lines.append(f"💰 {player_name(winner)} remporte **{format_coins(self.stake * 2)} pièces** !")
            else:
                lines.append("💰 Les mises sont rendues.")

        self.result_text = "\n".join(lines)

        try:
            if self.match_id is not None:
                await self.cog.settle(self.match_id, winner)
            await self.cog.record_result(self, winner_index, winner, loser)
        except Exception:
            LOGGER.exception("Fin de partie : enregistrement impossible")

        self.cog.release(self.guild_id, self.humans())

    # -------- revanche --------

    def ensure_rematch_button(self) -> None:
        """Après la fin : ajoute 🔁 Revanche (même si la vue a reconstruit ses boutons)."""
        if not self.over or self.rematch_closed:
            return

        if self.rematch_button is None:
            self.rematch_button = discord.ui.Button(
                label="Revanche", emoji="🔁", style=discord.ButtonStyle.success, row=4
            )
            self.rematch_button.callback = self.on_rematch

        self.rematch_button.disabled = False

        if self.rematch_button not in self.children:
            self.add_item(self.rematch_button)

    def schedule_rematch_expiry(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        self.rematch_timer = loop.call_later(
            REMATCH_WINDOW.total_seconds(), lambda: keep_task(asyncio.ensure_future(self.expire_rematch()))
        )

    def close_rematch(self) -> None:
        """Retire le bouton Revanche et libère la vue."""
        self.rematch_closed = True

        if self.rematch_button is not None and self.rematch_button in self.children:
            self.remove_item(self.rematch_button)

        if self.rematch_timer is not None:
            self.rematch_timer.cancel()

        self.stop()

    async def expire_rematch(self) -> None:
        if self.rematch_closed:
            return

        self.close_rematch()

        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_rematch(self, interaction: discord.Interaction) -> None:
        if self.rematch_closed:
            await interaction.response.send_message(
                embed=error_embed("La revanche a déjà été demandée."), ephemeral=True
            )
            return

        await self.cog.rematch(interaction, self)

    async def forfeit_button(self, interaction: discord.Interaction) -> None:
        async with self.lock:
            if self.over:
                return

            index = self.players.index(interaction.user.id) + 1
            await self.end(3 - index, f"🏳️ {interaction.user.mention} abandonne.")
            await self.refresh(interaction)

    def add_forfeit(self, row: int) -> None:
        button = discord.ui.Button(label="Abandonner", emoji="🏳️", style=discord.ButtonStyle.secondary, row=row)
        button.callback = self.forfeit_button
        self.add_item(button)


class TurnGameView(GameView):
    """Jeux au tour par tour (morpion, puissance 4)."""

    board: Any

    @property
    def current_player(self) -> int | None:
        return self.players[self.board.turn - 1]

    async def on_deadline(self) -> None:
        loser_index = self.board.turn
        await self.end(3 - loser_index, f"⌛ {player_name(self.current_player)} n'a pas joué à temps : défaite.")
        await self.refresh()

    def status_line(self) -> str:
        if self.over:
            return self.result_text

        return (
            f"👉 À {player_name(self.current_player)} de jouer "
            f"(<t:{int(self.deadline.timestamp())}:R>)"
        )

    async def human_move(self, interaction: discord.Interaction, move: int) -> None:
        async with self.lock:
            if self.over:
                await interaction.response.defer()
                return

            if interaction.user.id != self.current_player:
                await interaction.response.send_message(
                    embed=error_embed("Ce n'est pas ton tour."), ephemeral=True
                )
                return

            try:
                self.board.play(move)
            except ValueError as error:
                await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
                return

            self.reset_deadline()
            await self.after_move()
            self.update_buttons()
            await self.refresh(interaction)

            if not self.over and self.current_player is None:
                await self.ai_turn()

    async def ai_turn(self) -> None:
        await asyncio.sleep(0.8)  # on laisse le temps de voir le coup
        move = await asyncio.to_thread(self.ai_move)
        self.board.play(move)
        self.reset_deadline()
        await self.after_move()
        self.update_buttons()
        await self.refresh()

    def ai_move(self) -> int:
        raise NotImplementedError

    async def after_move(self) -> None:
        winner = self.board.winner()

        if winner:
            await self.end(winner, f"🏆 {player_name(self.players[winner - 1])} gagne la partie !")
        elif self.board.is_full():
            await self.end(0, "🤝 Égalité !")

    def update_buttons(self) -> None:
        raise NotImplementedError

    def start(self) -> None:
        super().start()

        if self.current_player is None:
            keep_task(asyncio.create_task(self.locked_ai_turn()))

    async def locked_ai_turn(self) -> None:
        async with self.lock:
            if not self.over:
                await self.ai_turn()


class MorpionView(TurnGameView):
    game = MORPION
    SYMBOLS = {1: "❌", 2: "⭕"}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.board = TicTacToe()

        for cell in range(9):
            button = discord.ui.Button(label="​", style=discord.ButtonStyle.secondary, row=cell // 3)
            button.callback = self.make_callback(cell)
            self.add_item(button)

        self.add_forfeit(row=3)

    def make_callback(self, cell: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self.human_move(interaction, cell)

        return callback

    def ai_move(self) -> int:
        return tictactoe_ai_move(self.board, self.difficulty)

    def update_buttons(self) -> None:
        line = self.board.winning_line() or ()

        for cell, button in enumerate(self.children[:9]):
            value = self.board.board[cell]
            button.label = None if value else "​"
            button.emoji = self.SYMBOLS.get(value)
            button.style = (
                discord.ButtonStyle.success
                if cell in line
                else discord.ButtonStyle.danger
                if value == 1
                else discord.ButtonStyle.primary
                if value == 2
                else discord.ButtonStyle.secondary
            )
            button.disabled = self.over or bool(value)

    def embed(self) -> discord.Embed:
        lines = [
            f"❌ {player_name(self.players[0])}  contre  ⭕ {player_name(self.players[1])}",
            *self.header(),
            "",
            self.status_line(),
        ]
        return discord.Embed(
            title=GAME_NAMES[MORPION],
            description="\n".join(lines),
            color=WIN_COLOR if self.over else GAME_COLOR,
        )


class PuissanceView(TurnGameView):
    game = PUISSANCE4
    DISCS = {0: "⚫", 1: "🔴", 2: "🟡"}
    NUMBERS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.board = ConnectFour()

        for column in range(COLUMNS):
            button = discord.ui.Button(
                emoji=self.NUMBERS[column],
                style=discord.ButtonStyle.secondary,
                row=0 if column < 4 else 1,
            )
            button.callback = self.make_callback(column)
            self.add_item(button)

        self.add_forfeit(row=1)

    def make_callback(self, column: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self.human_move(interaction, column)

        return callback

    def ai_move(self) -> int:
        return connect_four_ai_move(self.board, self.difficulty)

    def update_buttons(self) -> None:
        legal = set(self.board.legal_moves())

        for column, button in enumerate(self.children[:COLUMNS]):
            button.disabled = self.over or column not in legal

    def grid_text(self) -> str:
        winning = self.board.winning_cells() if self.over else set()
        last = self.board.last_move
        rows = []

        for row in range(ROWS):
            cells = []

            for column in range(COLUMNS):
                value = self.board.grid[row][column]
                cells.append("🟢" if (row, column) in winning else self.DISCS[value])

            rows.append("".join(cells))

        footer = "".join(self.NUMBERS)

        if last is not None and not self.over:
            footer += f"  (dernier coup : colonne {last[1] + 1})"

        return "\n".join(rows) + "\n" + footer

    def embed(self) -> discord.Embed:
        lines = [
            f"🔴 {player_name(self.players[0])}  contre  🟡 {player_name(self.players[1])}",
            *self.header(),
            "",
            self.grid_text(),
            "",
            self.status_line(),
        ]
        return discord.Embed(
            title=GAME_NAMES[PUISSANCE4],
            description="\n".join(lines),
            color=WIN_COLOR if self.over else GAME_COLOR,
        )


class PfcView(GameView):
    game = PFC

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        options = kwargs["options"]
        super().__init__(*args, **kwargs)
        self.board = RockPaperScissors(best_of=int(options.get("best_of", 3)))
        self.choices: dict[int, str] = {}
        self.history: list[str] = []  # choix de l'humain (pour l'IA difficile)
        self.last_round = ""
        self.reset_deadline(RPS_ROUND_TIMEOUT)

        for choice in RPS_CHOICES:
            button = discord.ui.Button(
                label=choice.capitalize(),
                emoji=RPS_EMOJIS[choice],
                style=discord.ButtonStyle.primary,
            )
            button.callback = self.make_callback(choice)
            self.add_item(button)

        self.add_forfeit(row=0)

    def make_callback(self, choice: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self.choose(interaction, choice)

        return callback

    async def choose(self, interaction: discord.Interaction, choice: str) -> None:
        async with self.lock:
            if self.over:
                await interaction.response.defer()
                return

            if interaction.user.id in self.choices:
                await interaction.response.send_message(
                    embed=error_embed("Tu as déjà choisi pour cette manche."), ephemeral=True
                )
                return

            self.choices[interaction.user.id] = choice

            if self.vs_ai:
                ai_choice = rps_ai_move(self.history, self.difficulty)
                self.history.append(choice)
                human_index = self.players.index(interaction.user.id)
                picks = [ai_choice, ai_choice]
                picks[human_index] = choice
                await self.resolve(picks)
                await self.refresh(interaction)
                return

            if len(self.choices) < 2:
                await interaction.response.send_message(
                    f"{RPS_EMOJIS[choice]} Choix enregistré : **{choice}**. On attend l'autre joueur…",
                    ephemeral=True,
                )
                await self.refresh()
                return

            await self.resolve([self.choices[self.players[0]], self.choices[self.players[1]]])
            await self.refresh(interaction)

    async def resolve(self, picks: list[str]) -> None:
        result = self.board.play_round(picks[0], picks[1])
        self.choices = {}
        self.reset_deadline(RPS_ROUND_TIMEOUT)
        number = len(self.board.rounds)
        shown = (
            f"{RPS_EMOJIS[picks[0]]} contre {RPS_EMOJIS[picks[1]]}"
        )
        self.last_round = (
            f"Manche {number} : {shown} → "
            + ("égalité, on rejoue !" if result == 0 else f"point pour {player_name(self.players[result - 1])}")
        )

        if self.board.finished():
            winner = self.board.winner()

            if winner:
                await self.end(winner, f"🏆 {player_name(self.players[winner - 1])} gagne la partie !")
            else:
                await self.end(0, "🤝 Trop d'égalités : match nul !")

    async def on_deadline(self) -> None:
        missing = [index + 1 for index, user_id in enumerate(self.players) if user_id is not None and user_id not in self.choices]

        if len(missing) == 1:
            await self.end(3 - missing[0], f"⌛ {player_name(self.players[missing[0] - 1])} n'a pas joué à temps : défaite.")
        else:
            await self.end(0, "⌛ Personne n'a joué à temps : partie annulée.")

        await self.refresh()

    def embed(self) -> discord.Embed:
        first, second = self.players
        lines = [
            f"{player_name(first)} **{self.board.scores[0]}** – **{self.board.scores[1]}** {player_name(second)}",
            f"Au meilleur des {self.board.best_of} manches (premier à {self.board.target}).",
            *self.header(),
        ]

        if self.last_round:
            lines += ["", self.last_round]

        if self.over:
            lines += ["", self.result_text]
        else:
            waiting = [
                f"{'✅' if user_id in self.choices else '⏳'} {player_name(user_id)}"
                for user_id in self.players
                if user_id is not None
            ]
            lines += [
                "",
                "Choisis en secret : " + " · ".join(waiting),
                f"⏰ Fin de la manche <t:{int(self.deadline.timestamp())}:R>",
            ]

        return discord.Embed(
            title=GAME_NAMES[PFC],
            description="\n".join(lines),
            color=WIN_COLOR if self.over else GAME_COLOR,
        )


class WordGuessModal(discord.ui.Modal, title="🔤 Proposer le mot entier"):
    def __init__(self, view: PenduView) -> None:
        super().__init__(timeout=300)
        self.view_ref = view
        self.word = discord.ui.TextInput(label="Le mot (sans souci d'accents)", max_length=40)
        self.add_item(self.word)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.view_ref.play(interaction, word=self.word.value)


class PenduView(GameView):
    """
    Pendu. En solo : le joueur cherche seul. En duel : les deux joueurs
    cherchent le même mot à tour de rôle ; une bonne lettre fait
    rejouer, une erreur passe la main. Celui qui complète le mot gagne.
    Pendu complet en duel : personne ne gagne (mises rendues).
    """

    game = PENDU
    HALVES = ("ABCDEFGHIJKLM", "NOPQRSTUVWXYZ")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        word, category = pick_word(self.difficulty)
        self.board = Hangman(word=word, category=category)
        self.turn_index = next(i for i, user_id in enumerate(self.players) if user_id is not None)
        self.last_action = ""
        self.build()

    @property
    def current_player(self) -> int:
        return self.players[self.turn_index]

    def header(self) -> list[str]:
        lines = [f"Mots **{self.difficulty}s** · Catégorie : **{self.board.category}**"]

        if self.stake:
            lines.append(
                f"💰 Mise : {format_coins(self.stake)} pièces chacun · "
                f"🏆 {format_coins(self.stake * 2)} pour le gagnant"
            )

        return lines

    def build(self) -> None:
        self.clear_items()

        for row, letters in enumerate(self.HALVES):
            remaining = [letter for letter in letters if letter not in self.board.guessed]
            select = discord.ui.Select(
                placeholder=f"Lettres {letters[0]} à {letters[-1]}…" if remaining else "Toutes proposées",
                options=[discord.SelectOption(label=letter, value=letter) for letter in remaining]
                or [discord.SelectOption(label="—", value="-")],
                disabled=self.over or not remaining,
                row=row,
            )
            select.callback = self.on_letter
            self.add_item(select)

        word_button = discord.ui.Button(
            label="Proposer le mot", emoji="🔤", style=discord.ButtonStyle.primary, row=2, disabled=self.over
        )
        word_button.callback = self.on_word
        self.add_item(word_button)
        self.add_forfeit(row=2)

        if self.over:
            self.disable_all()

    def disable_all(self) -> None:
        for item in self.children:
            item.disabled = True

    async def on_letter(self, interaction: discord.Interaction) -> None:
        await self.play(interaction, letter=interaction.data["values"][0])

    async def on_word(self, interaction: discord.Interaction) -> None:
        if not self.over and interaction.user.id != self.current_player:
            await interaction.response.send_message(embed=error_embed("Ce n'est pas ton tour."), ephemeral=True)
            return

        await interaction.response.send_modal(WordGuessModal(self))

    async def play(
        self,
        interaction: discord.Interaction,
        *,
        letter: str | None = None,
        word: str | None = None,
    ) -> None:
        async with self.lock:
            if self.over:
                await interaction.response.defer()
                return

            if interaction.user.id != self.current_player:
                await interaction.response.send_message(embed=error_embed("Ce n'est pas ton tour."), ephemeral=True)
                return

            try:
                found = self.board.guess_letter(letter) if letter else self.board.guess_word(word or "")
            except ValueError as error:
                await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)
                return

            who = f"<@{interaction.user.id}>"

            if letter:
                self.last_action = (
                    f"✅ {who} : la lettre **{base_letter(letter)}** est dans le mot !"
                    if found
                    else f"❌ {who} : pas de **{base_letter(letter)}**."
                )
            else:
                self.last_action = (
                    f"✅ {who} a trouvé le mot !" if found else f"❌ {who} : ce n'est pas « {word.strip()[:30]} »."
                )

            self.reset_deadline()
            winner_index = self.turn_index + 1

            if self.board.solved:
                await self.end(winner_index, f"🏆 {who} trouve le mot **{self.board.word.upper()}** !")
            elif self.board.lost:
                if self.vs_ai:
                    loser_index = self.players.index(None) + 1
                    await self.end(loser_index, f"💀 Pendu ! Le mot était **{self.board.word.upper()}**.")
                else:
                    await self.end(0, f"💀 Pendu ! Personne ne gagne. Le mot était **{self.board.word.upper()}**.")
            elif not found and not self.vs_ai:
                self.turn_index = 1 - self.turn_index  # une erreur passe la main

            self.build()
            await self.refresh(interaction)

    async def on_deadline(self) -> None:
        loser = self.turn_index + 1

        if self.vs_ai:
            await self.end(self.players.index(None) + 1, f"⌛ Temps écoulé ! Le mot était **{self.board.word.upper()}**.")
        else:
            await self.end(
                3 - loser,
                f"⌛ {player_name(self.current_player)} n'a pas joué à temps : défaite. "
                f"Le mot était **{self.board.word.upper()}**.",
            )

        self.build()
        await self.refresh()

    def embed(self) -> discord.Embed:
        board = self.board
        players = (
            f"🧍 {player_name(self.current_player)} joue en solo"
            if self.vs_ai
            else f"{player_name(self.players[0])}  contre  {player_name(self.players[1])}"
        )
        lines = [
            players,
            *self.header(),
            "",
            f"```\n{board.gallows()}\n```",
            f"## `{board.masked()}`",
            f"❤️ Erreurs : **{board.errors}/{board.max_errors}**",
        ]

        if board.wrong:
            lines.append("🚫 Lettres absentes : " + " ".join(board.wrong))

        if board.wrong_words:
            lines.append("🚫 Mots refusés : " + ", ".join(board.wrong_words))

        if self.last_action:
            lines += ["", self.last_action]

        if self.over:
            lines += ["", self.result_text]
        else:
            lines += [
                "",
                f"👉 À {player_name(self.current_player)} de jouer "
                f"(<t:{int(self.deadline.timestamp())}:R>) : choisis une lettre ou propose le mot.",
            ]

            if not self.vs_ai:
                lines.append("-# Bonne lettre : tu rejoues. Erreur : la main passe.")

        return discord.Embed(
            title=GAME_NAMES[PENDU],
            description="\n".join(lines),
            color=WIN_COLOR if self.over else GAME_COLOR,
        )


VIEWS: dict[str, type[GameView]] = {
    MORPION: MorpionView,
    PUISSANCE4: PuissanceView,
    PFC: PfcView,
    PENDU: PenduView,
}


# ============================================================
# COG
# ============================================================

DIFFICULTY_CHOICES = [
    app_commands.Choice(name="Facile", value=EASY),
    app_commands.Choice(name="Normal", value=NORMAL),
    app_commands.Choice(name="Difficile", value=HARD),
]


class GamesCog(commands.Cog):
    jeu = app_commands.Group(
        name="jeu",
        description="Mini-jeux contre un membre (avec mise possible) ou contre l'IA.",
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.busy: set[tuple[int, int]] = set()

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS minigame_matches (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                game VARCHAR(20) NOT NULL,
                player1_id BIGINT NOT NULL,
                player2_id BIGINT NOT NULL,
                stake INTEGER NOT NULL CHECK (stake >= 0),
                status VARCHAR(12) NOT NULL DEFAULT 'running',
                winner_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ended_at TIMESTAMPTZ
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS minigame_stats (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                game VARCHAR(20) NOT NULL,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                draws INTEGER NOT NULL DEFAULT 0,
                ai_wins INTEGER NOT NULL DEFAULT 0,
                ai_losses INTEGER NOT NULL DEFAULT 0,
                ai_draws INTEGER NOT NULL DEFAULT 0,
                coins_net BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, game)
            )
            """
        )

    async def cog_load(self) -> None:
        # Les parties en cours sont perdues au redémarrage : on rembourse.
        try:
            records = await self.get_pool().fetch(
                "SELECT id FROM minigame_matches WHERE status = 'running'"
            )

            for record in records:
                await self.settle(int(record["id"]), None)

            if records:
                LOGGER.info("%s partie(s) interrompue(s) remboursée(s)", len(records))
        except Exception:
            LOGGER.exception("Remboursement des parties interrompues impossible")

    # -------- occupation --------

    def is_busy(self, guild_id: int, user_id: int) -> bool:
        return (guild_id, user_id) in self.busy

    def reserve(self, guild_id: int, users: set[int]) -> None:
        self.busy |= {(guild_id, user_id) for user_id in users}

    def release(self, guild_id: int, users: set[int]) -> None:
        self.busy -= {(guild_id, user_id) for user_id in users}

    # -------- argent --------

    async def get_wallet(self, guild_id: int, user_id: int) -> int:
        return int(
            await self.get_pool().fetchval(
                "SELECT wallet FROM progression_members WHERE guild_id = $1 AND user_id = $2",
                guild_id,
                user_id,
            )
            or 0
        )

    async def _lock(self, connection, guild_id: int, user_ids: list[int]) -> None:
        for user_id in sorted(set(user_ids)):
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"progression:{guild_id}:{user_id}",
            )

    async def take_stakes(
        self, guild_id: int, first: int, second: int, stake: int, game: str
    ) -> int | None:
        """Retire la mise aux deux joueurs et crée la partie. None si sans mise."""
        if stake <= 0:
            return None

        async with self.get_pool().acquire() as connection:
            async with connection.transaction():
                await self._lock(connection, guild_id, [first, second])
                rows = await connection.fetch(
                    """
                    SELECT user_id, wallet FROM progression_members
                    WHERE guild_id = $1 AND user_id = ANY($2::BIGINT[])
                    FOR UPDATE
                    """,
                    guild_id,
                    [first, second],
                )
                wallets = {int(r["user_id"]): int(r["wallet"] or 0) for r in rows}

                for user_id in (first, second):
                    if wallets.get(user_id, 0) < stake:
                        raise BetError(
                            f"<@{user_id}> n'a que **{format_coins(wallets.get(user_id, 0))} pièces** : "
                            f"pas assez pour miser {format_coins(stake)}. Proposez une autre mise."
                        )

                match_id = await connection.fetchval(
                    """
                    INSERT INTO minigame_matches (guild_id, game, player1_id, player2_id, stake)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    guild_id,
                    game,
                    first,
                    second,
                    stake,
                )
                await connection.execute(
                    """
                    UPDATE progression_members
                    SET wallet = wallet - $3, updated_at = NOW()
                    WHERE guild_id = $1 AND user_id = ANY($2::BIGINT[])
                    """,
                    guild_id,
                    [first, second],
                    stake,
                )
                reason = f"Mise : {GAME_NAMES[game]} (partie n°{match_id})"
                await connection.executemany(
                    """
                    INSERT INTO progression_transactions
                        (guild_id, user_id, actor_id, amount, transaction_type, reason)
                    VALUES ($1, $2, NULL, $3, 'minigame_bet', $4)
                    """,
                    [(guild_id, user_id, -stake, reason) for user_id in (first, second)],
                )

        return int(match_id)

    async def settle(self, match_id: int, winner_id: int | None) -> bool:
        """Paie le gagnant (ou rembourse). Une seule fois par partie."""
        async with self.get_pool().acquire() as connection:
            async with connection.transaction():
                record = await connection.fetchrow(
                    """
                    UPDATE minigame_matches
                    SET status = $2, winner_id = $3, ended_at = NOW()
                    WHERE id = $1 AND status = 'running'
                    RETURNING *
                    """,
                    match_id,
                    "finished" if winner_id else "refunded",
                    winner_id,
                )

                if record is None:
                    return False

                guild_id = int(record["guild_id"])
                stake = int(record["stake"])
                players = [int(record["player1_id"]), int(record["player2_id"])]
                name = GAME_NAMES.get(record["game"], record["game"])

                if winner_id:
                    payouts = [(winner_id, stake * 2, "minigame_win", f"Victoire : {name} (partie n°{match_id})")]
                else:
                    payouts = [
                        (user_id, stake, "minigame_refund", f"Remboursement : {name} (partie n°{match_id})")
                        for user_id in players
                    ]

                await self._lock(connection, guild_id, [user_id for user_id, *_ in payouts])

                for user_id, amount, kind, reason in payouts:
                    # Un gain de mise n'est pas de l'argent « gagné » au sens des
                    # missions (comme un don) : lifetime_coins ne bouge pas.
                    await connection.execute(
                        """
                        UPDATE progression_members
                        SET wallet = wallet + $3, updated_at = NOW()
                        WHERE guild_id = $1 AND user_id = $2
                        """,
                        guild_id,
                        user_id,
                        amount,
                    )
                    await connection.execute(
                        """
                        INSERT INTO progression_transactions
                            (guild_id, user_id, actor_id, amount, transaction_type, reason)
                        VALUES ($1, $2, NULL, $3, $4, $5)
                        """,
                        guild_id,
                        user_id,
                        amount,
                        kind,
                        reason,
                    )

        return True

    async def record_result(
        self,
        view: GameView,
        winner_index: int,
        winner: int | None,
        loser: int | None,
    ) -> None:
        prefix = "ai_" if view.vs_ai else ""
        rows = []

        for user_id in view.humans():
            if not winner_index:
                column, coins = "draws", 0
            elif user_id == winner:
                column, coins = "wins", view.stake if view.match_id else 0
            else:
                column, coins = "losses", -view.stake if view.match_id else 0

            rows.append((view.guild_id, user_id, view.game, coins, prefix + column))

        pool = self.get_pool()

        for guild_id, user_id, game, coins, column in rows:
            await pool.execute(
                f"""
                INSERT INTO minigame_stats (guild_id, user_id, game, {column}, coins_net)
                VALUES ($1, $2, $3, 1, $4)
                ON CONFLICT (guild_id, user_id, game)
                DO UPDATE SET {column} = minigame_stats.{column} + 1,
                              coins_net = minigame_stats.coins_net + $4
                """,
                guild_id,
                user_id,
                game,
                coins,
            )

    # -------- lancement --------

    def create_game(
        self,
        game: str,
        *,
        players: list[int | None],
        stake: int,
        match_id: int | None,
        guild_id: int,
        options: dict[str, Any],
    ) -> GameView:
        view = VIEWS[game](
            self,
            players=players,
            stake=stake,
            match_id=match_id,
            guild_id=guild_id,
            options=options,
        )

        if isinstance(view, TurnGameView):
            view.update_buttons()

        return view

    async def rematch(self, interaction: discord.Interaction, old: GameView) -> None:
        """
        🔁 Revanche : même jeu, mêmes options, même mise.
        Contre l'IA (ou pendu solo), la partie repart tout de suite.
        Contre un membre, c'est un nouveau défi : l'autre doit accepter,
        surtout s'il y a une mise.
        """
        guild = interaction.guild
        user = interaction.user
        humans = old.humans()
        opponent_id = next((user_id for user_id in humans if user_id != user.id), None)

        if guild is None or interaction.channel is None:
            return

        if any(self.is_busy(guild.id, user_id) for user_id in humans):
            await interaction.response.send_message(
                embed=error_embed("Un des joueurs est déjà dans une autre partie ou un autre défi."),
                ephemeral=True,
            )
            return

        opponent = guild.get_member(opponent_id) if opponent_id is not None else None

        if opponent_id is not None and opponent is None:
            await interaction.response.send_message(
                embed=error_embed("Ton adversaire n'est plus sur le serveur."), ephemeral=True
            )
            return

        if old.stake:
            wallet = await self.get_wallet(guild.id, user.id)

            if wallet < old.stake:
                await interaction.response.send_message(
                    embed=error_embed(
                        f"Il te faut **{format_coins(old.stake)} pièces** pour la même mise "
                        f"(tu en as {format_coins(wallet)})."
                    ),
                    ephemeral=True,
                )
                return

        # Une seule revanche par partie : le bouton disparaît du message.
        old.close_rematch()
        await interaction.response.edit_message(view=old)

        if opponent is None:
            players: list[int | None] = [user.id, None]
            random.shuffle(players)
            self.reserve(guild.id, {user.id})
            view = self.create_game(
                old.game, players=players, stake=0, match_id=None, guild_id=guild.id, options=old.options
            )

            try:
                view.message = await interaction.channel.send(
                    content=f"🔁 Revanche de {user.mention} !",
                    embed=view.embed(),
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                self.release(guild.id, {user.id})
                raise

            view.start()
            return

        self.reserve(guild.id, {user.id, opponent.id})
        challenge = ChallengeView(self, old.game, user, opponent, old.stake, old.options)

        try:
            challenge.message = await interaction.channel.send(
                content=f"🔁 {opponent.mention}, {user.mention} te demande une revanche !",
                embed=challenge.embed(),
                view=challenge,
                allowed_mentions=discord.AllowedMentions(users=[opponent]),
            )
        except discord.HTTPException:
            self.release(guild.id, {user.id, opponent.id})
            raise

    async def launch(
        self,
        interaction: discord.Interaction,
        game: str,
        opponent: discord.Member | None,
        stake: int,
        options: dict[str, Any],
    ) -> None:
        user = interaction.user
        guild_id = interaction.guild_id

        if opponent is not None and opponent.id == user.id:
            opponent = None  # se défier soi-même = jouer contre l'IA

        if opponent is not None and opponent.bot:
            await interaction.response.send_message(
                embed=error_embed("Les bots ne jouent pas : laisse `adversaire` vide pour affronter l'IA."),
                ephemeral=True,
            )
            return

        if self.is_busy(guild_id, user.id):
            await interaction.response.send_message(
                embed=error_embed("Tu as déjà une partie ou un défi en cours. Termine-le d'abord !"),
                ephemeral=True,
            )
            return

        if opponent is None:
            if stake:
                await interaction.response.send_message(
                    embed=error_embed("Les mises se font contre un membre. Seul ou contre l'IA, c'est pour l'honneur !"),
                    ephemeral=True,
                )
                return

            players: list[int | None] = [user.id, None]
            random.shuffle(players)
            self.reserve(guild_id, {user.id})
            view = self.create_game(
                game, players=players, stake=0, match_id=None, guild_id=guild_id, options=options
            )
            try:
                await interaction.response.send_message(embed=view.embed(), view=view)
                view.message = await interaction.original_response()
            except discord.HTTPException:
                self.release(guild_id, {user.id})
                raise

            view.start()
            return

        if self.is_busy(guild_id, opponent.id):
            await interaction.response.send_message(
                embed=error_embed(f"{opponent.mention} est déjà en pleine partie. Réessaie plus tard !"),
                ephemeral=True,
            )
            return

        if stake:
            wallet = await self.get_wallet(guild_id, user.id)

            if wallet < stake:
                await interaction.response.send_message(
                    embed=error_embed(f"Tu n'as que **{format_coins(wallet)} pièces**."),
                    ephemeral=True,
                )
                return

        self.reserve(guild_id, {user.id, opponent.id})
        challenge = ChallengeView(self, game, user, opponent, stake, options)
        try:
            await interaction.response.send_message(
                content=f"{opponent.mention}, tu es défié !",
                embed=challenge.embed(),
                view=challenge,
                allowed_mentions=discord.AllowedMentions(users=[opponent]),
            )
            challenge.message = await interaction.original_response()
        except discord.HTTPException:
            self.release(guild_id, {user.id, opponent.id})
            raise

    # -------- commandes --------

    @jeu.command(name="morpion", description="Morpion (3 alignés) contre un membre ou l'IA.")
    @app_commands.describe(
        adversaire="Le membre à défier (vide = contre l'IA).",
        mise="Pièces misées par chaque joueur (contre un membre).",
        difficulte="Niveau de l'IA.",
    )
    @app_commands.choices(difficulte=DIFFICULTY_CHOICES)
    async def morpion(
        self,
        interaction: discord.Interaction,
        adversaire: discord.Member | None = None,
        mise: app_commands.Range[int, 0, MAX_STAKE] = 0,
        difficulte: app_commands.Choice[str] | None = None,
    ) -> None:
        await self.launch(
            interaction, MORPION, adversaire, mise,
            {"difficulty": difficulte.value if difficulte else NORMAL},
        )

    @jeu.command(name="puissance4", description="Puissance 4 contre un membre ou l'IA.")
    @app_commands.describe(
        adversaire="Le membre à défier (vide = contre l'IA).",
        mise="Pièces misées par chaque joueur (contre un membre).",
        difficulte="Niveau de l'IA.",
    )
    @app_commands.choices(difficulte=DIFFICULTY_CHOICES)
    async def puissance4(
        self,
        interaction: discord.Interaction,
        adversaire: discord.Member | None = None,
        mise: app_commands.Range[int, 0, MAX_STAKE] = 0,
        difficulte: app_commands.Choice[str] | None = None,
    ) -> None:
        await self.launch(
            interaction, PUISSANCE4, adversaire, mise,
            {"difficulty": difficulte.value if difficulte else NORMAL},
        )

    @jeu.command(name="pfc", description="Pierre-feuille-ciseaux contre un membre ou l'IA.")
    @app_commands.describe(
        adversaire="Le membre à défier (vide = contre l'IA).",
        mise="Pièces misées par chaque joueur (contre un membre).",
        manches="Nombre de manches (3 par défaut).",
        difficulte="Niveau de l'IA (difficile = elle apprend tes habitudes).",
    )
    @app_commands.choices(
        manches=[
            app_commands.Choice(name="1 manche", value=1),
            app_commands.Choice(name="Au meilleur des 3", value=3),
            app_commands.Choice(name="Au meilleur des 5", value=5),
        ],
        difficulte=[DIFFICULTY_CHOICES[1], DIFFICULTY_CHOICES[2]],
    )
    async def pfc(
        self,
        interaction: discord.Interaction,
        adversaire: discord.Member | None = None,
        mise: app_commands.Range[int, 0, MAX_STAKE] = 0,
        manches: app_commands.Choice[int] | None = None,
        difficulte: app_commands.Choice[str] | None = None,
    ) -> None:
        await self.launch(
            interaction, PFC, adversaire, mise,
            {
                "best_of": manches.value if manches else 3,
                "difficulty": difficulte.value if difficulte else NORMAL,
            },
        )

    @jeu.command(name="pendu", description="Pendu en solo, ou en duel contre un membre (avec mise possible).")
    @app_commands.describe(
        adversaire="Le membre à défier (vide = en solo).",
        mise="Pièces misées par chaque joueur (contre un membre).",
        difficulte="Longueur des mots : facile (courts), normal, difficile (longs).",
    )
    @app_commands.choices(difficulte=DIFFICULTY_CHOICES)
    async def pendu(
        self,
        interaction: discord.Interaction,
        adversaire: discord.Member | None = None,
        mise: app_commands.Range[int, 0, MAX_STAKE] = 0,
        difficulte: app_commands.Choice[str] | None = None,
    ) -> None:
        await self.launch(
            interaction, PENDU, adversaire, mise,
            {"difficulty": difficulte.value if difficulte else NORMAL},
        )

    @jeu.command(name="classement", description="Les meilleurs joueurs aux mini-jeux.")
    @app_commands.describe(jeu="Un jeu en particulier (tous par défaut).", tri="Ce qui compte pour le classement.")
    @app_commands.choices(
        jeu=[app_commands.Choice(name=name, value=game) for game, name in GAME_NAMES.items()],
        tri=[
            app_commands.Choice(name="Victoires contre des membres", value="wins"),
            app_commands.Choice(name="Gains des mises", value="coins_net"),
            app_commands.Choice(name="Victoires contre l'IA / en solo", value="ai_wins"),
        ],
    )
    async def classement(
        self,
        interaction: discord.Interaction,
        jeu: app_commands.Choice[str] | None = None,
        tri: app_commands.Choice[str] | None = None,
    ) -> None:
        metric = tri.value if tri else "wins"
        rows = await self.get_pool().fetch(
            f"""
            SELECT user_id,
                   SUM(wins) AS wins, SUM(losses) AS losses, SUM(draws) AS draws,
                   SUM(ai_wins) AS ai_wins, SUM(ai_losses) AS ai_losses,
                   SUM(coins_net) AS coins_net
            FROM minigame_stats
            WHERE guild_id = $1 AND ($2::text IS NULL OR game = $2)
            GROUP BY user_id
            HAVING SUM({metric}) <> 0
            ORDER BY SUM({metric}) DESC, SUM(wins) DESC
            LIMIT 200
            """,
            interaction.guild_id,
            jeu.value if jeu else None,
        )
        present = present_member_ids(self.bot, interaction.guild_id)

        if present is not None:
            allowed = set(present)
            rows = [row for row in rows if int(row["user_id"]) in allowed]

        ranking = leaderboard_lines(rows, metric)
        title = f"🏆 Classement des mini-jeux — {jeu.name if jeu else 'tous les jeux'}"
        embed = discord.Embed(title=title, color=GAME_COLOR)
        embed.description = "\n".join(ranking[:10]) if ranking else "Personne n'est encore classé ici. À vous de jouer !"
        own = next((index for index, row in enumerate(rows) if int(row["user_id"]) == interaction.user.id), None)

        if own is not None and own >= 10:
            embed.add_field(name="Ta place", value=ranking[own], inline=False)

        embed.set_footer(text=f"Classé par : {tri.name if tri else 'Victoires contre des membres'}")
        await interaction.response.send_message(embed=embed)

    @jeu.command(name="stats", description="Victoires, défaites et gains aux mini-jeux.")
    @app_commands.describe(membre="Le membre (toi par défaut).")
    async def stats(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        member = membre or interaction.user
        records = await self.get_pool().fetch(
            "SELECT * FROM minigame_stats WHERE guild_id = $1 AND user_id = $2",
            interaction.guild_id,
            member.id,
        )
        embed = discord.Embed(title=f"🎮 Mini-jeux de {member.display_name}", color=GAME_COLOR)
        total_net = 0

        for game, name in GAME_NAMES.items():
            record = next((r for r in records if r["game"] == game), None)

            if record is None:
                embed.add_field(name=name, value="*Jamais joué*", inline=False)
                continue

            total_net += int(record["coins_net"])
            embed.add_field(
                name=name,
                value=(
                    f"👥 Contre des membres : **{record['wins']}** V · {record['losses']} D · {record['draws']} N\n"
                    f"🤖 Contre l'IA / en solo : **{record['ai_wins']}** V · {record['ai_losses']} D · {record['ai_draws']} N\n"
                    f"💰 Mises : {'+' if record['coins_net'] >= 0 else '−'}"
                    f"{format_coins(abs(int(record['coins_net'])))} pièces"
                ),
                inline=False,
            )

        embed.set_footer(
            text=f"Bilan des mises : {'+' if total_net >= 0 else '−'}{format_coins(abs(total_net))} pièces"
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    cog = GamesCog(bot)
    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info("Mini-jeux chargés")
