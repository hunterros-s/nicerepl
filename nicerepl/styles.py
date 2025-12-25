"""Default styling constants for NiceREPL components."""

from __future__ import annotations

# Icons
ICON_SUCCESS = "\u2713"  # ✓
ICON_ERROR = "\u2717"  # ✗
ICON_WARNING = "\u26a0"  # ⚠
ICON_INFO = "\u2139"  # ℹ
ICON_BULLET = "\u25cf"  # ●
ICON_CANCELLED = "\u25cb"  # ○

# Spinner frames (braille animation)
SPINNER_FRAMES = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"

# Progress bar characters
PROGRESS_FILLED = "\u2588"  # █
PROGRESS_EMPTY = "\u2591"  # ░

# Tree characters for indented results
TREE_INDENT = "\u2514"  # └

# Tree box drawing for grouped output
TREE_BRANCH = "├"  # Middle item connector
TREE_CORNER = "╰"  # Last item (rounded)
TREE_PIPE = "│"  # Vertical continuation
TREE_HORIZ = "──"  # Horizontal line
TREE_ARROW = "➤"  # Arrow head

# Composed connectors
TREE_MID = "├──➤ "  # Middle item prefix
TREE_LAST = "╰──➤ "  # Last item prefix

# Colors
COLOR_SUCCESS = "green"
COLOR_ERROR = "red"
COLOR_WARNING = "yellow"
COLOR_INFO = "blue"
COLOR_CANCELLED = "dim"
COLOR_SPINNER = "cyan"
COLOR_PROGRESS = "cyan"

# Default component styles
DEFAULT_BORDER_COLOR = "dim"
DEFAULT_MESSAGE_BORDER = "dim"

# Status type mappings
STATUS_STYLES: dict[str, tuple[str, str]] = {
    "success": (COLOR_SUCCESS, ICON_SUCCESS),
    "error": (COLOR_ERROR, ICON_ERROR),
    "warning": (COLOR_WARNING, ICON_WARNING),
    "info": (COLOR_INFO, ICON_INFO),
}
