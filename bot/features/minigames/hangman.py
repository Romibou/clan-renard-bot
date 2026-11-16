"""
Pendu : règles et liste de mots (sans Discord).

Les lettres se proposent sans accent : « E » révèle aussi É, È, Ê…
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field

MAX_ERRORS = 7

GALLOWS = (
    "  ┌───┐\n  │\n  │\n  │\n ═╧═",
    "  ┌───┐\n  │   O\n  │\n  │\n ═╧═",
    "  ┌───┐\n  │   O\n  │   │\n  │\n ═╧═",
    "  ┌───┐\n  │   O\n  │  /│\n  │\n ═╧═",
    "  ┌───┐\n  │   O\n  │  /│\\\n  │\n ═╧═",
    "  ┌───┐\n  │   O\n  │  /│\\\n  │  /\n ═╧═",
    "  ┌───┐\n  │   O\n  │  /│\\\n  │  / \\\n ═╧═",
    "  ┌───┐\n  │   X\n  │  /│\\\n  │  / \\\n ═╧═  💀",
)

WORDS: dict[str, tuple[str, ...]] = {
    "Animaux": (
        "renard", "loup", "chat", "chien", "lapin", "hibou", "castor", "écureuil",
        "hérisson", "blaireau", "sanglier", "chevreuil", "girafe", "éléphant",
        "crocodile", "kangourou", "pingouin", "dauphin", "requin", "baleine",
        "tortue", "papillon", "abeille", "fourmi", "araignée", "serpent",
        "panthère", "guépard", "rhinocéros", "hippopotame", "ornithorynque",
        "caméléon", "flamant", "perroquet", "chauve-souris", "méduse", "pieuvre",
        "koala", "panda", "zèbre", "lynx", "marmotte",
    ),
    "Jeux vidéo": (
        "manette", "console", "joystick", "pixel", "niveau", "boss", "quête",
        "inventaire", "personnage", "multijoueur", "sauvegarde", "checkpoint",
        "avatar", "classement", "tournoi", "streameur", "speedrun", "potion",
        "épée", "bouclier", "donjon", "aventure", "plateforme", "arcade",
        "casque", "clavier", "souris", "écran", "graphisme", "mission",
    ),
    "Nourriture": (
        "croissant", "baguette", "fromage", "chocolat", "crêpe", "gaufre",
        "pizza", "raclette", "tartiflette", "ratatouille", "croque-monsieur",
        "macaron", "éclair", "madeleine", "brioche", "confiture", "spaghetti",
        "hamburger", "frites", "sushi", "fraise", "framboise", "ananas",
        "pastèque", "citrouille", "champignon", "omelette", "quiche", "sandwich",
        "beignet", "caramel", "vanille", "cannelle", "noisette",
    ),
    "Nature": (
        "montagne", "rivière", "cascade", "forêt", "volcan", "désert", "océan",
        "glacier", "prairie", "tempête", "arc-en-ciel", "éclair", "nuage",
        "tornade", "avalanche", "étoile", "comète", "galaxie", "planète",
        "soleil", "printemps", "automne", "hiver", "flocon", "tournesol",
        "coquelicot", "champignon", "sapin", "chêne", "bambou",
    ),
    "Maison et objets": (
        "parapluie", "lampe", "fauteuil", "canapé", "horloge", "miroir",
        "téléphone", "ordinateur", "télévision", "réfrigérateur", "aspirateur",
        "bougie", "couverture", "oreiller", "valise", "lunettes", "ciseaux",
        "trousse", "cartable", "guitare", "piano", "trompette", "violon",
        "appareil", "boussole", "jumelles", "télescope", "trampoline",
    ),
    "Fêtes et hiver": (
        "calendrier", "cadeau", "guirlande", "bonhomme", "traîneau", "renne",
        "lutin", "chaussette", "cheminée", "réveillon", "feux", "bûche",
        "sapin", "étoile", "neige", "patinoire", "écharpe", "bonnet", "moufle",
        "chocolat", "anniversaire", "confettis", "déguisement", "citrouille",
    ),
}

LENGTHS = {"facile": (3, 6), "normal": (6, 9), "difficile": (9, 30)}


def base_letter(char: str) -> str:
    """É → E, ç → C, œ → OE (lettre sans accent, en majuscule)."""
    special = {"œ": "OE", "Œ": "OE", "æ": "AE", "Æ": "AE"}

    if char in special:
        return special[char]

    decomposed = unicodedata.normalize("NFD", char)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def normalize(text: str) -> str:
    return "".join(base_letter(char) for char in text.strip())


def letter_count(word: str) -> int:
    return sum(1 for char in word if char.isalpha())


def pick_word(difficulty: str = "normal", rng: random.Random | None = None) -> tuple[str, str]:
    """Retourne (mot, catégorie) adapté à la difficulté."""
    rng = rng or random.Random()
    low, high = LENGTHS.get(difficulty, LENGTHS["normal"])
    pool = [
        (word, category)
        for category, words in WORDS.items()
        for word in words
        if low <= letter_count(word) <= high
    ]

    if not pool:
        pool = [(word, category) for category, words in WORDS.items() for word in words]

    return rng.choice(pool)


@dataclass
class Hangman:
    word: str
    category: str = ""
    max_errors: int = MAX_ERRORS
    guessed: list[str] = field(default_factory=list)  # lettres proposées (sans accent)
    wrong: list[str] = field(default_factory=list)  # lettres fausses
    wrong_words: list[str] = field(default_factory=list)
    errors: int = 0
    solved_by_word: bool = False

    @property
    def needed(self) -> set[str]:
        # « œ » donne deux lettres à trouver : O et E.
        return {letter for char in self.word if char.isalpha() for letter in base_letter(char)}

    @property
    def solved(self) -> bool:
        return self.solved_by_word or self.needed <= set(self.guessed)

    @property
    def lost(self) -> bool:
        return not self.solved and self.errors >= self.max_errors

    def finished(self) -> bool:
        return self.solved or self.lost

    def guess_letter(self, letter: str) -> bool:
        letter = base_letter(letter.strip()[:1])

        if not letter.isalpha() or len(letter) != 1:
            raise ValueError("Propose une lettre.")
        if letter in self.guessed:
            raise ValueError(f"La lettre {letter} a déjà été proposée.")
        if self.finished():
            raise ValueError("Partie terminée.")

        self.guessed.append(letter)

        if letter in self.needed:
            return True

        self.wrong.append(letter)
        self.errors += 1
        return False

    def guess_word(self, text: str) -> bool:
        if self.finished():
            raise ValueError("Partie terminée.")

        attempt = normalize(text).replace(" ", "")

        if not attempt:
            raise ValueError("Écris un mot.")

        if attempt == normalize(self.word).replace(" ", ""):
            self.solved_by_word = True
            return True

        self.wrong_words.append(text.strip()[:30])
        self.errors += 1
        return False

    def masked(self) -> str:
        """« É _ _ P H A N T » (tirets et espaces affichés tels quels)."""
        shown = []

        for char in self.word.upper():
            if not char.isalpha():
                shown.append(char)
            elif self.solved or set(base_letter(char)) <= set(self.guessed):
                shown.append(char)
            else:
                shown.append("_")

        return " ".join(shown)

    def gallows(self) -> str:
        return GALLOWS[min(self.errors, len(GALLOWS) - 1)]
