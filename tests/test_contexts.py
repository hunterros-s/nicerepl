"""Tests for UI context managers."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from nicerepl._output import OutputManager
from nicerepl._ui import (
    _UI,
    _CancelableState,
)


class TestStatusContext:
    """Tests for status spinner context manager.

    Note: _StatusContext uses asyncio.create_task for animation,
    so these tests must run in an async context.
    """

    @pytest.mark.asyncio
    async def test_status_enter_sets_live(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test entering status sets live content."""
        output_manager.set_live = MagicMock()

        with test_ui.status("Loading..."):
            output_manager.set_live.assert_called()

    @pytest.mark.asyncio
    async def test_status_exit_prints_success(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test normal exit prints success."""
        output_manager.print = MagicMock()
        output_manager.clear_live = MagicMock()

        with test_ui.status("Done"):
            pass

        output_manager.print.assert_called()
        output_manager.clear_live.assert_called()

    @pytest.mark.asyncio
    async def test_status_exit_on_error_prints_error(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test error exit prints error status."""
        output_manager.print = MagicMock()

        with pytest.raises(ValueError), test_ui.status("Working..."):
            raise ValueError("test error")

        output_manager.print.assert_called()

    @pytest.mark.asyncio
    async def test_status_update_message(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test updating status message."""
        output_manager.set_live = MagicMock()

        with test_ui.status("First") as s:
            s.update("Second")
            # Should have been called multiple times
            assert output_manager.set_live.call_count >= 2


class TestProgressContext:
    """Tests for progress bar context manager."""

    def test_progress_enter_sets_live(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test entering progress sets live content."""
        output_manager.set_live = MagicMock()

        with test_ui.progress("Loading", total=10):
            output_manager.set_live.assert_called()

    def test_progress_advance(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test advancing progress."""
        output_manager.set_live = MagicMock()

        with test_ui.progress("Loading", total=10) as p:
            initial_calls = output_manager.set_live.call_count
            p.advance(5)
            assert output_manager.set_live.call_count > initial_calls

    def test_progress_update(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test setting absolute progress."""
        output_manager.set_live = MagicMock()

        with test_ui.progress("Loading", total=10) as p:
            initial_calls = output_manager.set_live.call_count
            p.update(7)
            assert output_manager.set_live.call_count > initial_calls

    def test_progress_exit_prints(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test exit prints completion message."""
        output_manager.print = MagicMock()
        output_manager.clear_live = MagicMock()

        with test_ui.progress("Task", total=10):
            pass

        output_manager.print.assert_called()
        output_manager.clear_live.assert_called()


class TestStreamContext:
    """Tests for streaming text context manager."""

    @pytest.mark.asyncio
    async def test_stream_write(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test writing to stream."""
        output_manager.set_live = MagicMock()

        async with test_ui.stream() as s:
            s.write("Hello ")
            s.write("World")
            assert output_manager.set_live.call_count >= 2

    @pytest.mark.asyncio
    async def test_stream_writeln(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test writeln adds newline."""
        output_manager.set_live = MagicMock()

        async with test_ui.stream() as s:
            s.writeln("Line 1")
            s.writeln("Line 2")

    @pytest.mark.asyncio
    async def test_stream_exit_prints_buffer(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test exit prints accumulated buffer."""
        output_manager.print = MagicMock()
        output_manager.clear_live = MagicMock()

        async with test_ui.stream() as s:
            s.write("Content")

        output_manager.print.assert_called()
        output_manager.clear_live.assert_called()


class TestCancelableContext:
    """Tests for cancelable async context manager."""

    @pytest.mark.asyncio
    async def test_cancelable_sets_state(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test entering cancelable sets UI state."""
        async with test_ui.cancelable():
            assert isinstance(test_ui._state, _CancelableState)

    @pytest.mark.asyncio
    async def test_cancelable_clears_state_on_exit(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test exiting cancelable clears state."""
        async with test_ui.cancelable():
            pass

        assert test_ui._state is None

    @pytest.mark.asyncio
    async def test_cancelable_shows_footer(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test cancelable shows interrupt hint."""
        output_manager.set_live_footer = MagicMock()

        async with test_ui.cancelable():
            output_manager.set_live_footer.assert_called()

    @pytest.mark.asyncio
    async def test_cancelable_returns_scope(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test cancelable returns CancelScope."""
        async with test_ui.cancelable() as scope:
            assert hasattr(scope, "sleep")
            assert hasattr(scope, "cancel")

    @pytest.mark.asyncio
    async def test_cancelable_suppresses_cancelled_error(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test cancelable catches and suppresses CancelledError.

        Note: We test the __aexit__ behavior directly since CancelScope.cancel()
        also cancels the running task (which would be the test itself).
        """
        output_manager.print = MagicMock()
        output_manager.clear_live = MagicMock()
        output_manager.clear_live_footer = MagicMock()

        # Manually test the context manager's exception handling
        ctx = test_ui.cancelable()
        scope = await ctx.__aenter__()

        # Simulate CancelledError being raised inside the context
        result = await ctx.__aexit__(
            asyncio.CancelledError,
            asyncio.CancelledError(),
            None,
        )

        # Should return True (suppress the error)
        assert result is True
        # Should have printed "Interrupted"
        output_manager.print.assert_called()
        # State should be cleared
        assert test_ui._state is None

    @pytest.mark.asyncio
    async def test_cancelable_double_enter_raises(
        self, test_ui: _UI, output_manager: OutputManager
    ) -> None:
        """Test nested cancelable raises StateError."""
        from nicerepl._exceptions import StateError

        async with test_ui.cancelable():
            with pytest.raises(StateError, match="already in state"):
                async with test_ui.cancelable():
                    pass
