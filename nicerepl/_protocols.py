"""Protocol definitions for NiceREPL.

These protocols enable:
1. Breaking circular dependencies between REPL and UI
2. Testing with mock implementations
3. Potential for alternative implementations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from nicerepl._output import OutputManager


@runtime_checkable
class REPLProtocol(Protocol):
    """Protocol for REPL interface.

    Used by UI components that need to interact with the REPL
    without directly depending on the concrete _REPL class.
    """

    @property
    def prompt(self) -> str:
        """Get the current prompt string."""
        ...

    @prompt.setter
    def prompt(self, value: str) -> None:
        """Set the prompt string."""
        ...

    def exit(self) -> None:
        """Request REPL exit."""
        ...


@runtime_checkable
class UIProtocol(Protocol):
    """Protocol for UI interface.

    Used by REPL to delegate UI state management without
    directly depending on the concrete _UI class.
    """

    @property
    def mode(self) -> str:
        """Get current UI mode (idle, cancelable, confirming)."""
        ...

    def request_cancel(self, *, strict: bool = False) -> bool:
        """Request cancellation of current operation.

        Returns True if something was cancelled, False otherwise.
        """
        ...

    def respond_confirm(self, value: bool, *, strict: bool = False) -> bool:
        """Respond to a pending confirmation prompt.

        Returns True if there was a pending confirm, False otherwise.
        """
        ...

    def _bind(self, output: OutputManager) -> None:
        """Bind to an OutputManager instance."""
        ...


@runtime_checkable
class OutputProtocol(Protocol):
    """Protocol for output management.

    Abstracts the output layer for rendering content.
    """

    def print(self, content: object) -> None:
        """Print content to scrollback."""
        ...

    def set_live(self, content: object) -> None:
        """Set live content (spinner/progress)."""
        ...

    def clear_live(self) -> None:
        """Clear main live content."""
        ...

    def set_live_footer(self, content: object) -> None:
        """Set persistent footer."""
        ...

    def clear_live_footer(self) -> None:
        """Clear the live footer."""
        ...

    def has_live_content(self) -> bool:
        """Check if there's live content to display."""
        ...
