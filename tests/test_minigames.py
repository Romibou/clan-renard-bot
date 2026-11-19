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
    assert all(button.disabled for button in view.children if button is not view.rematch_button)
    assert view.rematch_button in view.children and not view.rematch_button.disabled


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
        "hints": False,
        "chat_mode": True,
        "created_by": 99,
        "knower_ids": [],
        "guild_id": 1,
        "channel_id": 50,
        "max_attempts": 5,
        "secret": 77,
        "ends_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    record.update(changes)
    return record


def test_bingo_embed_hides_secret_until_end() -> None:
    running = bingo_module.build_bingo_embed(bingo_record(), guesses=12, players=4)
    # Le nombre secret ne doit pas apparaître (l'heure de fin peut contenir « 77 »).
    assert "**77**" not in running.description
    assert "Manche **2/3**" in running.description
    assert "<@10>" in running.description and "**42**" in running.description

    expired = bingo_module.build_bingo_embed(bingo_record(status="expired"), guesses=12, players=4)
    assert "**77**" in expired.description
    assert "<@99>" in running.description  # l'animateur donne les indices
    assert "dans ce salon" in running.description


class FakePool:
    def __init__(self) -> None:
        self.round_updates = 0
        self.flushed: list = []

    async def fetchrow(self, query, *args):
        self.round_updates += 1
        return {"id": args[0]} if self.round_updates == 1 else None

    async def executemany(self, query, rows):
        self.flushed.extend(rows)


def bingo_cog_with_state(**changes):
    pool = FakePool()
    bot = SimpleNamespace(database=SimpleNamespace(require_pool=lambda: pool), intents=SimpleNamespace(message_content=True))
    cog = bingo_module.BingoCog(bot)
    state = bingo_module.BingoState.from_record(bingo_record(round=1, winner_ids=[], found_numbers=[], **changes))
    cog.states[state.id] = state
    cog.by_channel[state.channel_id] = state.id
    return cog, state, pool


async def test_bingo_process_flow(monkeypatch) -> None:
    async def nothing(_state):
        return None

    cog, state, pool = bingo_cog_with_state(max_attempts=2, secret=77)
    monkeypatch.setattr(cog, "tell_knowers", nothing)
    process = cog.process

    assert (await process(3, 99, 77, 0)).kind == bingo_module.KNOWS  # l'animateur ne joue pas
    assert (await process(3, 10, 500, 0)).kind == bingo_module.OUT_OF_RANGE

    wrong = await process(3, 10, 12, 0)
    assert wrong.kind == bingo_module.WRONG and wrong.left == 1
    assert (await process(3, 10, 13, 10)).kind == bingo_module.COOLDOWN

    assert (await process(3, 10, 14, 0)).kind == bingo_module.WRONG
    assert (await process(3, 10, 77, 0)).kind == bingo_module.LIMIT  # 2 essais utilisés

    win = await process(3, 20, 77, 0)
    assert win.kind == bingo_module.WIN and win.secret == 77 and not win.finished
    assert state.round == 2 and 1 <= state.secret <= 100
    assert (2, 10) not in state.attempts  # nouvelle manche : essais remis à zéro
    assert sum(row[3] for row in pool.flushed) == 3  # essais recopiés en base
    assert state.guesses == 3 and state.players == {10, 20}


async def test_bingo_last_round_closes() -> None:
    cog, state, _pool = bingo_cog_with_state(rounds=1, secret=5)
    win = await cog.process(3, 10, 5, 0)

    assert win.finished
    assert 3 not in cog.states and 50 not in cog.by_channel
    assert (await cog.process(3, 11, 5, 0)).kind == bingo_module.CLOSED


async def test_bingo_reads_channel_messages(monkeypatch) -> None:
    cog, state, _pool = bingo_cog_with_state(secret=42)
    reactions: list[str] = []
    replies: list[str] = []

    async def nothing(*args, **kwargs):
        return None

    monkeypatch.setattr(cog, "reward", nothing)
    monkeypatch.setattr(cog, "refresh_message", nothing)
    monkeypatch.setattr(cog, "tell_knowers", nothing)

    def message(user_id: int, content: str):
        async def add_reaction(emoji):
            reactions.append(emoji)

        async def reply(text, **kwargs):
            replies.append(text)

        return SimpleNamespace(
            author=SimpleNamespace(id=user_id, bot=False, mention=f"<@{user_id}>"),
            guild=SimpleNamespace(id=1),
            channel=SimpleNamespace(id=50),
            content=content,
            add_reaction=add_reaction,
            reply=reply,
        )

    await cog.on_message(message(10, "salut tout le monde"))
    await cog.on_message(message(10, "17"))
    assert reactions == [] and state.guesses == 1  # pas d'indice automatique

    await cog.on_message(message(99, "42"))
    assert reactions == ["🤫"]  # l'animateur ne peut pas jouer

    await cog.on_message(message(11, "42"))
    assert reactions[-1] == "🎉" and "BINGO" in replies[0]


# ---------------------------------------------------------------
# Pendu
# ---------------------------------------------------------------

from bot.features.minigames.hangman import (  # noqa: E402
    GALLOWS,
    MAX_ERRORS,
    WORDS,
    Hangman,
    base_letter,
    letter_count,
    pick_word,
)


def test_hangman_accents_and_rules() -> None:
    game = Hangman(word="écureuil", category="Animaux")

    assert game.masked() == "_ _ _ _ _ _ _ _"
    assert game.guess_letter("e") is True  # « e » révèle É et E
    assert game.masked() == "É _ _ _ E _ _ _"

    with pytest.raises(ValueError):
        game.guess_letter("E")  # déjà proposée

    assert game.guess_letter("z") is False and game.errors == 1 and game.wrong == ["Z"]

    for letter in "CURIL":
        game.guess_letter(letter)

    assert game.solved and game.masked() == "É C U R E U I L"


def test_hangman_word_guess_and_loss() -> None:
    game = Hangman(word="arc-en-ciel")
    assert game.masked() == "_ _ _ - _ _ - _ _ _ _"
    assert game.guess_word("ARC EN CIEL") is False  # les tirets comptent
    assert game.guess_word("arc-en-ciel") is True and game.solved

    lost = Hangman(word="loup")

    for letter in "ABCDEFG":
        lost.guess_letter(letter)

    assert lost.errors == MAX_ERRORS and lost.lost and lost.finished()
    assert lost.gallows() == GALLOWS[-1]


def test_hangman_word_list() -> None:
    assert base_letter("ç") == "C" and base_letter("œ") == "OE"
    assert Hangman(word="cœur").needed == {"C", "O", "E", "U", "R"}

    for difficulty, (low, high) in (("facile", (3, 6)), ("difficile", (9, 30))):
        for seed in range(20):
            word, category = pick_word(difficulty, random.Random(seed))
            assert low <= letter_count(word) <= high and word in WORDS[category]

    assert len(GALLOWS) == MAX_ERRORS + 1


async def test_pendu_duel_turns_and_win() -> None:
    cog = FakeCog()
    view = jeux.PenduView(cog, players=[10, 20], stake=100, match_id=5, guild_id=1, options={})
    view.board = Hangman(word="loup", category="Animaux")
    view.turn_index = 0
    view.build()

    await view.play(interaction_for(10), letter="L")  # bonne lettre : 10 rejoue
    assert view.current_player == 10

    wrong = interaction_for(20)
    await view.play(wrong, letter="O")
    assert wrong.response.messages  # pas son tour

    await view.play(interaction_for(10), letter="Z")  # erreur : la main passe
    assert view.current_player == 20

    await view.play(interaction_for(20), word="loup")
    assert view.over and cog.settled == [(5, 20)]
    assert all(item.disabled for item in view.children if item is not view.rematch_button)
    assert view.rematch_button in view.children  # gardé même après la reconstruction des boutons


async def test_pendu_solo_loss_and_duel_draw() -> None:
    cog = FakeCog()
    solo = jeux.PenduView(cog, players=[None, 10], stake=0, match_id=None, guild_id=1, options={})
    solo.board = Hangman(word="loup")
    assert solo.current_player == 10

    for letter in "ABCDEFG":
        await solo.play(interaction_for(10), letter=letter)

    assert solo.over and cog.results[-1] == (1, None)  # l'« IA » gagne : défaite en solo

    cog = FakeCog()
    duel = jeux.PenduView(cog, players=[10, 20], stake=50, match_id=8, guild_id=1, options={})
    duel.board = Hangman(word="loup", max_errors=2)
    duel.turn_index = 0
    await duel.play(interaction_for(10), letter="A")
    await duel.play(interaction_for(20), letter="B")
    assert duel.over and cog.settled == [(8, None)]  # pendu en duel : mises rendues


def test_pendu_view_limits() -> None:
    view = jeux.PenduView(FakeCog(), players=[1, 2], stake=0, match_id=None, guild_id=1, options={})
    view.board = Hangman(word="abcdefghijklm")

    for letter in "ABCDEFGHIJKLM":
        view.board.guessed.append(letter)

    view.build()
    first_select = view.children[0]
    assert first_select.disabled and len(view.children) == 4
    assert len(view.embed().description) <= 4096


def test_leaderboard_lines() -> None:
    rows = [
        {"user_id": 1, "wins": 8, "losses": 2, "draws": 0, "ai_wins": 3, "ai_losses": 1, "coins_net": 1500},
        {"user_id": 2, "wins": 1, "losses": 1, "draws": 0, "ai_wins": 0, "ai_losses": 0, "coins_net": -200},
        {"user_id": 3, "wins": 0, "losses": 0, "draws": 0, "ai_wins": 9, "ai_losses": 0, "coins_net": 0},
        {"user_id": 4, "wins": 0, "losses": 3, "draws": 1, "ai_wins": 0, "ai_losses": 0, "coins_net": 0},
    ]

    lines = jeux.leaderboard_lines(rows, "wins")
    assert lines[0] == "🥇 <@1> — **8** V · 2 D · 0 N · 80 %"
    assert lines[3].startswith("**4.** <@4>")

    coins = jeux.leaderboard_lines(rows, "coins_net")
    assert "**+1 500** pièces" in coins[0] and "**−200** pièces" in coins[1]
    assert "**9** victoires" in jeux.leaderboard_lines(rows, "ai_wins")[2]


# ---------------------------------------------------------------
# Revanche
# ---------------------------------------------------------------


class RematchCog(FakeCog):
    def __init__(self, wallet: int = 10_000) -> None:
        super().__init__()
        self.wallet = wallet
        self.reserved: list = []

    def is_busy(self, guild_id, user_id):
        return (guild_id, user_id) in self.busy

    def reserve(self, guild_id, users):
        self.reserved.append(set(users))
        self.busy |= {(guild_id, user) for user in users}

    async def get_wallet(self, guild_id, user_id):
        return self.wallet

    rematch = jeux.GamesCog.rematch
    create_game = jeux.GamesCog.create_game


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(id=len(self.sent))


def rematch_interaction(user_id: int, members: dict):
    interaction = interaction_for(user_id)
    interaction.guild = SimpleNamespace(id=1, get_member=lambda member_id: members.get(member_id))
    interaction.channel = FakeChannel()
    return interaction


async def finished_morpion(cog, players, stake=0, match_id=None):
    view = jeux.MorpionView(cog, players=players, stake=stake, match_id=match_id, guild_id=1, options={"difficulty": HARD})
    view.update_buttons()
    await view.forfeit_button(interaction_for(next(p for p in players if p is not None)))
    return view


async def test_rematch_between_members_sends_new_challenge_with_same_stake() -> None:
    cog = RematchCog()
    view = await finished_morpion(cog, [10, 20], stake=300, match_id=1)
    assert view.rematch_button in view.children

    opponent = SimpleNamespace(id=20, mention="<@20>", guild=SimpleNamespace(id=1))
    challenger = SimpleNamespace(id=10, mention="<@10>", guild=SimpleNamespace(id=1))
    interaction = rematch_interaction(10, {20: opponent})
    interaction.user = challenger
    await view.on_rematch(interaction)

    sent = interaction.channel.sent
    assert len(sent) == 1 and isinstance(sent[0]["view"], jeux.ChallengeView)
    challenge = sent[0]["view"]
    assert challenge.stake == 300 and challenge.opponent is opponent and challenge.options["difficulty"] == HARD
    assert view.rematch_closed and view.rematch_button not in view.children

    # Deuxième clic : refusé, une seule revanche par partie.
    again = rematch_interaction(20, {10: challenger})
    await view.on_rematch(again)
    assert again.response.messages and not again.channel.sent


async def test_rematch_against_ai_starts_new_game_and_checks_wallet() -> None:
    cog = RematchCog()
    view = await finished_morpion(cog, [10, None])
    interaction = rematch_interaction(10, {})
    await view.on_rematch(interaction)

    new_game = interaction.channel.sent[0]["view"]
    assert isinstance(new_game, jeux.MorpionView) and None in new_game.players and new_game.difficulty == HARD
    if new_game.watchdog:
        new_game.watchdog.cancel()

    poor = RematchCog(wallet=10)
    staked = await finished_morpion(poor, [10, 20], stake=300, match_id=2)
    broke = rematch_interaction(10, {20: SimpleNamespace(id=20, mention="<@20>")})
    await staked.on_rematch(broke)
    assert broke.response.messages and not broke.channel.sent and not staked.rematch_closed


async def test_rematch_button_expires() -> None:
    cog = RematchCog()
    view = await finished_morpion(cog, [10, 20])
    view.message = SimpleNamespace(edit=lambda **kwargs: _noop_async())
    await view.expire_rematch()
    assert view.rematch_closed and view.is_finished()
    view.ensure_rematch_button()
    assert view.rematch_button not in view.children


async def _noop_async():
    return None
