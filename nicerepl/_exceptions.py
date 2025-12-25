"""Exception hierarchy for NiceREPL."""

from __future__ import annotations


class NiceREPLError(Exception):
    """Base exception for all NiceREPL errors."""


class StateError(NiceREPLError):
    """Invalid state transition.

    Raised when attempting to enter a context manager while another
    is already active (e.g., entering cancelable while confirming).

    Recovery: Ensure context managers don't overlap. Use separate
    async tasks if you need concurrent UI operations.
    """


class NotBoundError(NiceREPLError):
    """UI used before binding to REPL.

    Raised when calling UI methods before repl.run() is called.

    Recovery: Ensure repl.run() is called before using ui.* methods.
    """
