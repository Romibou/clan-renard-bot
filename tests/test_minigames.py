from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot.extensions import bingo as bingo_module
from bot.extensions import jeux
from bot.features.minigames.engines import (
    HARD,
    NORMAL,
    PAPER,
    ROCK,
    SCISSORS,
    ConnectFour,
    RockPaperScissors,
    TicTacToe,
    connect_four_ai_move,
    rps_ai_move,
    rps_result,
    tictactoe_ai_move,
)

# ---------------------------------------------------------------
# Moteurs
# ---------------------------------------------------------------


def test_tictactoe_rules() -> None:
    game = TicTacToe()

    for cell in (0, 3, 1, 4, 2):
        game.play(cell)

    assert game.winner() == 1
    assert game.winning_line() == (0, 1, 2)

    with pytest.raises(ValueError):
        game.play(5)

    with pytest.raises(ValueError):
        TicTacToe(board=[1, 0, 0, 0, 0, 0, 0, 0, 0]).play(0)


def test_tictactoe_hard_ai_never_loses() -> None:
    rng = random.Random(7)

    for ai in (1, 2):
        for _ in range(100):
            game = TicTacToe()

            while not game.finished():
                move = tictactoe_ai_move(game, HARD, rng) if game.turn == ai else rng.choice(game.legal_moves())
                game.play(move)

            assert game.winner() != 3 - ai


def test_tictactoe_ai_takes_win_and_blocks() -> None:
    game = TicTacToe(board=[1, 1, 0, 2, 2, 0, 0, 0, 0], turn=2)
    assert tictactoe_ai_move(game, HARD) == 5  # gagne

    game = TicTacToe(board=[1, 1, 0, 2, 0, 0, 0, 0, 0], turn=2)
    assert tictactoe_ai_move(game, HARD) == 2  # bloque


def test_connect_four_rules() -> None:
    game = ConnectFour()

    for column in (0, 1, 0, 1, 0, 1):
        game.play(column)

    assert game.grid[5][0] == 1 and game.grid[3][0] == 1
    game.play(0)
    assert game.winner() == 1
    assert game.winning_cells() == {(2, 0), (3, 0), (4, 0), (5, 0)}

    full = ConnectFour()

    for _ in range(6):
        full.grid[0][3] = 1

    assert 3 not in full.legal_moves()


def test_connect_four_ai_wins_and_blocks() -> None:
    game = ConnectFour()

    for column in (0, 6, 1, 6, 2):
        game.play(column)

    # Au jaune de jouer : il doit bloquer en 3.
    assert connect_four_ai_move(game, NORMAL) == 3

    game.play(5)  # le jaune joue ailleurs
    assert connect_four_ai_move(game, NORMAL) == 3  # le rouge gagne


def test_connect_four_hard_beats_random() -> None:
    rng = random.Random(3)
    wins = 0

    for _ in range(3):
        game = ConnectFour()

        while not game.finished():
            game.play(connect_four_ai_move(game, HARD, rng) if game.turn == 1 else rng.choice(game.legal_moves()))

        wins += game.winner() == 1

    assert wins == 3


def test_rps() -> None:
    assert rps_result(ROCK, SCISSORS) == 1
    assert rps_result(ROCK, PAPER) == 2
    assert rps_result(PAPER, PAPER) == 0

    # Le joueur alterne pierre/feuille : l'IA difficile prévoit « feuille » et joue ciseaux.
    history = [ROCK, PAPER, ROCK, PAPER, ROCK]
    picks = [rps_ai_move(history, HARD, random.Random(seed)) for seed in range(30)]
    assert picks.count(SCISSORS) > 20

    match = RockPaperScissors(best_of=3)
    match.play_round(ROCK, SCISSORS)
    match.play_round(ROCK, ROCK)
    assert not match.finished()
    match.play_round(PAPER, ROCK)
    assert match.winner() == 1 and match.finished()


def test_rps_draw_limit() -> None:
    match = RockPaperScissors(best_of=1)

    for _ in range(3):
        match.play_round(ROCK, ROCK)

    assert match.finished() and match.winner() == 0


# ---------------------------------------------------------------
# Parties Discord (sans réseau)
# ---------------------------------------------------------------


class FakeCog:
    def __init__(self) -> None:
        self.settled: list[tuple[int, int | None]] = []
        self.results: list[tuple[int, int | None]] = []
        self.busy: set = set()

    async def settle(self, match_id, winner):
        self.settled.append((match_id, winner))
        return True

    async def record_result(self, view, winner_index, winner, loser):
        self.results.append((winner_index, winner))

    def release(self, guild_id, users):
        self.busy -= {(guild_id, user) for user in users}


class FakeResponse:
    def __init__(self) -> None:
        self.done = False
        self.messages: list = []

    def is_done(self) -> bool:
        return self.done

    async def edit_message(self, **kwargs):
        self.done = True

    async def send_message(self, *args, **kwargs):
        self.done = True
        self.messages.append((args, kwargs))

    async def defer(self, **kwargs):
        self.done = True


def interaction_for(user_id: int):
    return SimpleNamespace(user=SimpleNamespace(id=user_id, mention=f"<@{user_id}>"), response=FakeResponse())


async def test_morpion_between_members_pays_winner() -> None:
    cog = FakeCog()
    view = jeux.MorpionView(cog, players=[10, 20], stake=500, match_id=7, guild_id=1, options={})
    view.update_buttons()

    # 20 essaie de jouer alors que ce n'est pas son tour.
    wrong = interaction_for(20)
    await view.human_move(wrong, 0)
    assert view.board.board[0] == 0 and wrong.response.messages

    for user, cell in ((10, 0), (20, 3), (10, 1), (20, 4), (10, 2)):
        await view.human_move(interaction_for(user), cell)

    assert view.over
    assert cog.settled == [(7, 10)]
    assert cog.results == [(1, 10)]
    assert "1 000 pièces" in view.result_text
    assert all(button.disabled for button in view.children)


async def test_forfeit_and_timeout() -> None:
    cog = FakeCog()
    view = jeux.PuissanceView(cog, players=[10, 20], stake=0, match_id=None, guild_id=1, options={})
    await view.forfeit_button(interaction_for(10))
    assert view.over and cog.results == [(2, 20)] and cog.settled == []

    cog = FakeCog()
    view = jeux.MorpionView(cog, players=[10, 20], stake=100, match_id=3, guild_id=1, options={})
    view.deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    await view.on_deadline()
    assert cog.settled == [(3, 20)]  # 10 devait jouer : il perd


async def test_game_against_ai(monkeypatch) -> None:
    async def no_sleep(_):
        return None

    monkeypatch.setattr(jeux.asyncio, "sleep", no_sleep)
    cog = FakeCog()
    view = jeux.MorpionView(cog, players=[10, None], stake=0, match_id=None, guild_id=1, options={"difficulty": HARD})
    view.update_buttons()

    while not view.over:
        move = random.choice(view.board.legal_moves())
        await view.human_move(interaction_for(10), move)

    assert view.board.winner() != 1  # l'IA difficile ne perd jamais
    assert cog.results and cog.settled == []


async def test_pfc_between_members() -> None:
    cog = FakeCog()
    view = jeux.PfcView(cog, players=[10, 20], stake=50, match_id=9, guild_id=1, options={"best_of": 1})

    first = interaction_for(10)
    await view.choose(first, ROCK)
    assert not view.over and first.response.messages  # choix enregistré en privé

    again = interaction_for(10)
    await view.choose(again, PAPER)
    assert view.choices == {10: ROCK}  # on ne change pas d'avis

    await view.choose(interaction_for(20), SCISSORS)
    assert view.over and cog.settled == [(9, 10)]


async def test_pfc_timeout_one_missing() -> None:
    cog = FakeCog()
    view = jeux.PfcView(cog, players=[10, 20], stake=50, match_id=4, guild_id=1, options={"best_of": 3})
    view.choices = {20: ROCK}
    await view.on_deadline()
    assert cog.settled == [(4, 20)]


def test_views_respect_discord_limits() -> None:
    cog = FakeCog()

    for view_class in (jeux.MorpionView, jeux.PuissanceView, jeux.PfcView):
        view = view_class(cog, players=[1, 2], stake=0, match_id=None, guild_id=1, options={})
        rows: dict[int, int] = {}

        for item in view.children:
            rows[item.row] = rows.get(item.row, 0) + 1

        assert all(count <= 5 for count in rows.values())
        assert len(view.embed().description) <= 4096


# ---------------------------------------------------------------
# Bingo
# ---------------------------------------------------------------


def test_bingo_helpers() -> None:
    assert bingo_module.parse_guess(" 1 000 ") == 1000
    assert bingo_module.parse_guess("42") == 42
    assert bingo_module.parse_guess("-5") == -5
    assert bingo_module.parse_guess("4,2") is None
    assert bingo_module.parse_guess("abc") is None
    assert "plus grand" in bingo_module.hint(10, 50)
    assert "plus petit" in bingo_module.hint(90, 50)
    assert bingo_module.describe_reward(0, 500) == "500 pièces"
    assert bingo_module.describe_reward(0, 0) == "la gloire éternelle"


def bingo_record(**changes):
    record = {
        "id": 3,
        "status": "running",
        "rounds": 3,
        "round": 2,
        "winner_ids": [10],
        "found_numbers": [42],
        "note": "Bonne chance !",
        "min_value": 1,
        "max_value": 100,
        "xp": 0,
        "coins": 500,
        "hints": True,
        "max_attempts": 5,
        "secret": 77,
        "ends_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    record.update(changes)
    return record


def test_bingo_embed_hides_secret_until_end() -> None:
    running = bingo_module.build_bingo_embed(bingo_record(), guesses=12, players=4)
    assert "77" not in running.description
    assert "Manche **2/3**" in running.description
    assert "<@10>" in running.description and "**42**" in running.description

    expired = bingo_module.build_bingo_embed(bingo_record(status="expired"), guesses=12, players=4)
    assert "**77**" in expired.description
