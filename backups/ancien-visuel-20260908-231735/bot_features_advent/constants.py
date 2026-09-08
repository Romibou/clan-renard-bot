from __future__ import annotations


DEFAULT_TITLE = "Calendrier de l'Avent"
DEFAULT_TIMEZONE = "Europe/Paris"
DEFAULT_START_DAY = 1
DEFAULT_END_DAY = 24
DEFAULT_OPENING_HOUR = 0

CATCHUP_DISABLED = "disabled"
CATCHUP_ENABLED = "enabled"

VALID_CATCHUP_MODES = {
    CATCHUP_DISABLED,
    CATCHUP_ENABLED,
}

REWARD_MESSAGE = "message"
REWARD_POINTS = "points"
REWARD_ROLE = "role"
REWARD_RANDOM = "random"

VALID_REWARD_TYPES = {
    REWARD_MESSAGE,
    REWARD_POINTS,
    REWARD_ROLE,
    REWARD_RANDOM,
}

# Ordre visuel volontairement mélangé.
# Chaque nombre indique le jour affiché à cette position.
DEFAULT_DAY_ORDER = (
    7, 18, 2, 24, 11, 15,
    3, 20, 9, 14, 1, 22,
    16, 5, 21, 10, 13, 8,
    17, 4, 23, 6, 19, 12,
)

IMAGE_WIDTH = 1600
IMAGE_HEIGHT = 1000
GRID_COLUMNS = 6
GRID_ROWS = 4
