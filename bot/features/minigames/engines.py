"""
Règles des mini-jeux et IA, sans Discord (facile à tester).

- Morpion (3×3) : IA minimax, imbattable en difficile.
- Puissance 4 (6×7) : IA minimax avec élagage alpha-bêta.
- Pierre-feuille-ciseaux : IA aléatoire, ou qui apprend les
  habitudes du joueur en difficile.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

EASY = "facile"
NORMAL = "normal"
HARD = "difficile"
DIFFICULTIES = (EASY, NORMAL, HARD)


# ============================================================
# MORPION
# ============================================================

LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


@dataclass
class TicTacToe:
    """Cases 0 à 8 ; 0 = vide, 1 = premier joueur (❌), 2 = second (⭕)."""

    board: list[int] = field(default_factory=lambda: [0] * 9)
    turn: int = 1

    def legal_moves(self) -> list[int]:
        return [index for index, value in enumerate(self.board) if value == 0]

    def play(self, cell: int) -> None:
        if not 0 <= cell < 9 or self.board[cell] != 0:
            raise ValueError("Case déjà prise.")
        if self.winner() or self.is_full():
            raise ValueError("Partie terminée.")

        self.board[cell] = self.turn
        self.turn = 3 - self.turn

    def winner(self) -> int:
        return tictactoe_winner(self.board)

    def winning_line(self) -> tuple[int, int, int] | None:
        for line in LINES:
            a, b, c = line
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return line
        return None

    def is_full(self) -> bool:
        return all(self.board)

    def finished(self) -> bool:
        return bool(self.winner()) or self.is_full()


def tictactoe_winner(board: list[int]) -> int:
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return 0


@lru_cache(maxsize=None)
def _minimax_ttt(board: tuple[int, ...], player: int, me: int) -> int:
    """Score de la position pour `me` (victoire rapide > victoire lente)."""
    winner = tictactoe_winner(list(board))

    if winner:
        return 10 if winner == me else -10
    if all(board):
        return 0

    scores = []

    for cell in range(9):
        if board[cell] == 0:
            child = board[:cell] + (player,) + board[cell + 1:]
            score = _minimax_ttt(child, 3 - player, me)
            # Une victoire lointaine vaut un peu moins qu'une proche.
            scores.append(score - (1 if score > 0 else -1 if score < 0 else 0))

    return max(scores) if player == me else min(scores)


def tictactoe_best_moves(game: TicTacToe) -> list[int]:
    me = game.turn
    board = tuple(game.board)
    best: list[int] = []
    best_score = -100

    for cell in game.legal_moves():
        child = board[:cell] + (me,) + board[cell + 1:]
        score = _minimax_ttt(child, 3 - me, me)

        if score > best_score:
            best, best_score = [cell], score
        elif score == best_score:
            best.append(cell)

    return best


def tictactoe_ai_move(game: TicTacToe, difficulty: str, rng: random.Random | None = None) -> int:
    rng = rng or random.Random()
    moves = game.legal_moves()
    smart_chance = {EASY: 0.25, NORMAL: 0.75, HARD: 1.0}.get(difficulty, 0.75)

    if rng.random() < smart_chance:
        return rng.choice(tictactoe_best_moves(game))

    # Même « au hasard », l'IA facile saisit une victoire immédiate une fois sur deux.
    if difficulty != EASY or rng.random() < 0.5:
        for cell in moves:
            game.board[cell] = game.turn
            won = tictactoe_winner(game.board) == game.turn
            game.board[cell] = 0
            if won:
                return cell

    return rng.choice(moves)


# ============================================================
# PUISSANCE 4
# ============================================================

ROWS = 6
COLUMNS = 7


@dataclass
class ConnectFour:
    """grid[ligne][colonne], ligne 0 = en haut. 1 = 🔴, 2 = 🟡."""

    grid: list[list[int]] = field(default_factory=lambda: [[0] * COLUMNS for _ in range(ROWS)])
    turn: int = 1
    last_move: tuple[int, int] | None = None

    def legal_moves(self) -> list[int]:
        return [column for column in range(COLUMNS) if self.grid[0][column] == 0]

    def play(self, column: int) -> int:
        if column not in self.legal_moves():
            raise ValueError("Colonne pleine.")
        if self.finished():
            raise ValueError("Partie terminée.")

        row = drop_row(self.grid, column)
        self.grid[row][column] = self.turn
        self.last_move = (row, column)
        self.turn = 3 - self.turn
        return row

    def winner(self) -> int:
        return connect_four_winner(self.grid)

    def winning_cells(self) -> set[tuple[int, int]]:
        return set(_winning_cells(self.grid))

    def is_full(self) -> bool:
        return all(self.grid[0][column] for column in range(COLUMNS))

    def finished(self) -> bool:
        return bool(self.winner()) or self.is_full()


def drop_row(grid: list[list[int]], column: int) -> int:
    for row in range(ROWS - 1, -1, -1):
        if grid[row][column] == 0:
            return row
    raise ValueError("Colonne pleine.")


DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _winning_cells(grid: list[list[int]]) -> list[tuple[int, int]]:
    for row in range(ROWS):
        for column in range(COLUMNS):
            player = grid[row][column]
            if not player:
                continue
            for dr, dc in DIRECTIONS:
                cells = [(row + dr * k, column + dc * k) for k in range(4)]
                if all(
                    0 <= r < ROWS and 0 <= c < COLUMNS and grid[r][c] == player
                    for r, c in cells
                ):
                    return cells
    return []


def connect_four_winner(grid: list[list[int]]) -> int:
    cells = _winning_cells(grid)
    return grid[cells[0][0]][cells[0][1]] if cells else 0


# --- IA : plateau « à plat » (42 cases) pour aller vite ---------------

WINDOWS: tuple[tuple[int, int, int, int], ...] = tuple(
    tuple((row + dr * k) * COLUMNS + column + dc * k for k in range(4))
    for row in range(ROWS)
    for column in range(COLUMNS)
    for dr, dc in DIRECTIONS
    if 0 <= row + dr * 3 < ROWS and 0 <= column + dc * 3 < COLUMNS
)
WINDOWS_BY_CELL: tuple[tuple[tuple[int, int, int, int], ...], ...] = tuple(
    tuple(window for window in WINDOWS if cell in window) for cell in range(ROWS * COLUMNS)
)
CENTER_CELLS = tuple(row * COLUMNS + COLUMNS // 2 for row in range(ROWS))


def _wins_at(board: list[int], cell: int) -> bool:
    player = board[cell]
    return any(
        board[a] == player and board[b] == player and board[c] == player and board[d] == player
        for a, b, c, d in WINDOWS_BY_CELL[cell]
    )


def _drop_flat(board: list[int], column: int) -> int:
    for row in range(ROWS - 1, -1, -1):
        cell = row * COLUMNS + column
        if board[cell] == 0:
            return cell
    return -1


def evaluate_connect_four(grid: list[list[int]], me: int) -> int:
    return _evaluate([value for row in grid for value in row], me)


def _evaluate(board: list[int], me: int) -> int:
    other = 3 - me
    score = 3 * sum(1 for cell in CENTER_CELLS if board[cell] == me)

    for a, b, c, d in WINDOWS:
        values = (board[a], board[b], board[c], board[d])
        mine = values.count(me)
        theirs = values.count(other)

        if mine and theirs:
            continue
        if mine == 3:
            score += 50
        elif mine == 2:
            score += 10
        elif theirs == 3:
            score -= 80
        elif theirs == 2:
            score -= 8

    return score


ORDER = (3, 2, 4, 1, 5, 0, 6)  # le centre d'abord : l'élagage est plus efficace
WIN_SCORE = 1_000_000


def _search(board: list[int], depth: int, alpha: float, beta: float, player: int, me: int) -> float:
    moves = [column for column in ORDER if board[column] == 0]

    if depth == 0 or not moves:
        return _evaluate(board, me)

    maximizing = player == me
    best = -float("inf") if maximizing else float("inf")

    for column in moves:
        cell = _drop_flat(board, column)
        board[cell] = player

        if _wins_at(board, cell):
            score = (WIN_SCORE + depth) if maximizing else -(WIN_SCORE + depth)
        else:
            score = _search(board, depth - 1, alpha, beta, 3 - player, me)

        board[cell] = 0

        if maximizing:
            best = max(best, score)
            alpha = max(alpha, score)
        else:
            best = min(best, score)
            beta = min(beta, score)

        if alpha >= beta:
            break

    return best


DEPTHS = {EASY: 1, NORMAL: 3, HARD: 5}


def connect_four_ai_move(
    game: ConnectFour,
    difficulty: str,
    rng: random.Random | None = None,
) -> int:
    rng = rng or random.Random()
    moves = game.legal_moves()
    me = game.turn

    if difficulty == EASY and rng.random() < 0.4:
        return rng.choice(moves)

    board = [value for row in game.grid for value in row]
    depth = DEPTHS.get(difficulty, 3)
    best_score = -float("inf")
    best: list[int] = []

    for column in [c for c in ORDER if c in moves]:
        cell = _drop_flat(board, column)
        board[cell] = me

        if _wins_at(board, cell):
            score = WIN_SCORE * 2
        else:
            score = _search(board, depth, -float("inf"), float("inf"), 3 - me, me)

        board[cell] = 0

        if score > best_score:
            best, best_score = [column], score
        elif score == best_score:
            best.append(column)

    return rng.choice(best)


# ============================================================
# PIERRE-FEUILLE-CISEAUX
# ============================================================

ROCK, PAPER, SCISSORS = "pierre", "feuille", "ciseaux"
RPS_CHOICES = (ROCK, PAPER, SCISSORS)
RPS_EMOJIS = {ROCK: "🪨", PAPER: "📄", SCISSORS: "✂️"}
BEATS = {ROCK: SCISSORS, PAPER: ROCK, SCISSORS: PAPER}
COUNTER = {loser: winner for winner, loser in BEATS.items()}


def rps_result(first: str, second: str) -> int:
    """1 = le premier gagne, 2 = le second, 0 = égalité."""
    if first == second:
        return 0
    return 1 if BEATS[first] == second else 2


def rps_ai_move(history: list[str], difficulty: str, rng: random.Random | None = None) -> str:
    """
    history : choix précédents du joueur humain.
    Difficile : devine son prochain coup d'après ce qu'il a joué après
    son dernier choix (et sinon son coup préféré), puis le contre.
    """
    rng = rng or random.Random()

    if difficulty != HARD or not history or rng.random() < 0.2:
        return rng.choice(RPS_CHOICES)

    followers = Counter(
        history[index + 1] for index in range(len(history) - 1) if history[index] == history[-1]
    )
    guess_pool = followers or Counter(history)
    predicted = guess_pool.most_common(1)[0][0]

    return COUNTER[predicted]


@dataclass
class RockPaperScissors:
    best_of: int = 3
    scores: list[int] = field(default_factory=lambda: [0, 0])
    rounds: list[tuple[str, str, int]] = field(default_factory=list)

    @property
    def target(self) -> int:
        return self.best_of // 2 + 1

    def play_round(self, first: str, second: str) -> int:
        if self.finished():
            raise ValueError("Partie terminée.")

        result = rps_result(first, second)

        if result:
            self.scores[result - 1] += 1

        self.rounds.append((first, second, result))
        return result

    def winner(self) -> int:
        for index, score in enumerate(self.scores):
            if score >= self.target:
                return index + 1
        return 0

    def finished(self) -> bool:
        # Les égalités ne comptent pas : on rejoue (avec une limite).
        return bool(self.winner()) or len(self.rounds) >= self.best_of * 3
