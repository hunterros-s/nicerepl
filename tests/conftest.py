"""Pytest fixtures for NiceREPL tests."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from nicerepl._output import OutputManager
from nicerepl._repl import _REPL
from nicerepl._ui import _UI

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def captured_output() -> io.StringIO:
    """StringIO buffer for capturing output."""
    return io.StringIO()


@pytest.fixture
def test_console(captured_output: io.StringIO) -> Console:
    """Rich Console that writes to StringIO instead of terminal."""
    return Console(
        file=captured_output,
        force_terminal=True,
        width=80,
        color_system="truecolor",
    )


@pytest.fixture
def output_manager() -> OutputManager:
    """Fresh OutputManager instance for testing."""
    return OutputManager(block_spacing=1, width=80)


@pytest.fixture
def test_ui(output_manager: OutputManager) -> Generator[_UI, None, None]:
    """Fresh UI instance bound to test output manager."""
    ui_instance = _UI()
    ui_instance._bind(output_manager)
    yield ui_instance
    ui_instance._reset()


@pytest.fixture
def test_repl() -> Generator[_REPL, None, None]:
    """Fresh REPL instance for testing."""
    repl_instance = _REPL()
    yield repl_instance
    repl_instance._reset()


@pytest.fixture
def reset_global_ui() -> Generator[None, None, None]:
    """Reset the global ui singleton before and after test."""
    from nicerepl._ui import ui

    ui._reset()
    yield
    ui._reset()


@pytest.fixture
def reset_global_repl() -> Generator[None, None, None]:
    """Reset the global repl singleton before and after test."""
    from nicerepl._repl import repl

    repl._reset()
    yield
    repl._reset()
