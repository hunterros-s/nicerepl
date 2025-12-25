"""Internal output management for NiceREPL."""

from __future__ import annotations

import io
import os
from collections.abc import Callable

from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text
from rich.console import Console, RenderableType


def _is_dumb_terminal() -> bool:
    """Check if running in a dumb terminal with limited capabilities."""
    term = os.environ.get("TERM", "").lower()
    return term in ("dumb", "")


class OutputManager:
    """Unified output manager for all content.

    Single formatting path for both scrollback and live content.
    Owns spacing decisions - content components know nothing about spacing.
    """

    def __init__(self, block_spacing: int = 1, width: int = 80) -> None:
        self.block_spacing = block_spacing
        self._width = width
        self._live_content = ""
        self._live_footer = ""
        self._invalidate_callback: Callable[[], None] | None = None
        self._output = None  # Set when app is running
        self._dumb_terminal = _is_dumb_terminal()

    def set_invalidate_callback(self, callback: Callable[[], None]) -> None:
        """Set callback to invalidate display when live content changes."""
        self._invalidate_callback = callback

    def set_output(self, output) -> None:
        """Set the output device for printing."""
        self._output = output

    def set_width(self, width: int) -> None:
        """Set the terminal width."""
        self._width = width

    def print(self, content: RenderableType | str) -> None:
        """Print content to scrollback."""
        formatted = self._format(content)
        if self._output:
            print_formatted_text(ANSI(formatted), output=self._output)
        else:
            print_formatted_text(ANSI(formatted))

    def set_live(self, content: RenderableType | str) -> None:
        """Set live content (spinner/progress)."""
        self._live_content = self._format(content)
        self._invalidate()

    def clear_live(self) -> None:
        """Clear main live content."""
        self._live_content = ""
        self._invalidate()

    def set_live_footer(self, content: RenderableType | str) -> None:
        """Set persistent footer (e.g., cancelable indicator)."""
        self._live_footer = self._render_to_ansi(content).rstrip("\n")
        self._invalidate()

    def clear_live_footer(self) -> None:
        """Clear the live footer."""
        self._live_footer = ""
        self._invalidate()

    def clear_all_live(self) -> None:
        """Clear both main live content and footer."""
        self._live_content = ""
        self._live_footer = ""
        self._invalidate()

    def get_live_content(self) -> str:
        """Get combined live content (main + footer)."""
        parts = []
        if self._live_content:
            parts.append(self._live_content.rstrip("\n"))
        if self._live_footer:
            parts.append(self._live_footer)
        if parts:
            sep = "\n" * (self.block_spacing + 1)
            return sep.join(parts) + "\n" * self.block_spacing
        return ""

    def get_live_height(self) -> int:
        """Get height for live content window."""
        content = self.get_live_content()
        if not content:
            return 0
        return content.count("\n") + 1

    def has_live_content(self) -> bool:
        """Check if there's live content to display."""
        return bool(self._live_content or self._live_footer)

    def _format(self, content: RenderableType | str) -> str:
        """Single formatting path for ALL content."""
        ansi = self._render_to_ansi(content)
        return ansi.rstrip("\n") + "\n" * self.block_spacing

    def _render_to_ansi(self, content: RenderableType | str) -> str:
        """Render Rich content to ANSI string.

        Handles graceful degradation for dumb terminals by disabling
        colors and styles when TERM=dumb or TERM is unset.
        """
        buffer = io.StringIO()
        if self._dumb_terminal:
            # No colors or fancy formatting for dumb terminals
            console = Console(
                file=buffer,
                force_terminal=False,
                no_color=True,
                width=self._width,
            )
        else:
            console = Console(file=buffer, force_terminal=True, width=self._width)
        console.print(content, end="")
        return buffer.getvalue()

    def _invalidate(self) -> None:
        """Trigger display refresh."""
        if self._invalidate_callback:
            self._invalidate_callback()
