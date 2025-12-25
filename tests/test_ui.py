"""Tests for UI output methods and state management."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from nicerepl._output import OutputManager
from nicerepl._ui import (
    _UI,
    CancelScope,
    _CancelableState,
)


class TestUIBinding:
    """Tests for UI binding and state."""

    def test_unbound_ui_raises(self) -> None:
        """Test unbound UI raises on output methods."""
        ui = _UI()
        with pytest.raises(RuntimeError, match="UI not bound"):
            ui.print("test")

    def test_bound_ui_works(self, test_ui: _UI) -> None:
        """Test bound UI accepts output."""
        # Should not raise
        test_ui.print("test")

    def test_mode_idle_by_default(self, test_ui: _UI) -> None:
        """Test mode is idle by default."""
        assert test_ui.mode == "idle"

    def test_reset_clears_state(self, test_ui: _UI) -> None:
        """Test reset clears UI state."""
        test_ui._state = _CancelableState(scope=CancelScope())
        test_ui._reset()
        assert test_ui._state is None
        assert test_ui._output is None


class TestCancelScope:
    """Tests for CancelScope."""

    def test_initial_state(self) -> None:
        """Test initial cancelled state is False."""
        scope = CancelScope()
        assert not scope.cancelled

    def test_cancel_sets_flag(self) -> None:
        """Test cancel sets cancelled flag."""
        scope = CancelScope()
        scope.cancel()
        assert scope.cancelled

    @pytest.mark.asyncio
    async def test_checkpoint_raises_when_cancelled(self) -> None:
        """Test checkpoint raises CancelledError when cancelled."""
        scope = CancelScope()
        scope.cancel()
        with pytest.raises(asyncio.CancelledError):
            await scope.checkpoint()

    @pytest.mark.asyncio
    async def test_checkpoint_passes_when_not_cancelled(self) -> None:
        """Test checkpoint passes when not cancelled."""
        scope = CancelScope()
        await scope.checkpoint()  # Should not raise

    @pytest.mark.asyncio
    async def test_sleep_raises_when_cancelled(self) -> None:
        """Test sleep raises immediately when already cancelled."""
        scope = CancelScope()
        scope.cancel()
        with pytest.raises(asyncio.CancelledError):
            await scope.sleep(10)

    @pytest.mark.asyncio
    async def test_sleep_completes_normally(self) -> None:
        """Test sleep completes when not cancelled."""
        scope = CancelScope()
        await scope.sleep(0.01)  # Should complete

    @pytest.mark.asyncio
    async def test_sleep_interrupted_by_cancel(self) -> None:
        """Test sleep is interrupted by cancel."""
        scope = CancelScope()

        async def cancel_after_delay():
            await asyncio.sleep(0.05)
            scope.cancel()

        task = asyncio.create_task(cancel_after_delay())

        with pytest.raises(asyncio.CancelledError):
            await scope.sleep(10)  # Would take forever, but cancel interrupts

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestUIOutputMethods:
    """Tests for UI output methods."""

    def test_print_calls_output(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test print delegates to output manager."""
        # Mock the print method
        output_manager.print = MagicMock()
        test_ui.print("Hello")
        output_manager.print.assert_called_once()

    def test_echo_formats_with_prefix(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test echo adds prefix."""
        output_manager.print = MagicMock()
        test_ui.echo("test input")
        output_manager.print.assert_called_once()
        # Check the call included the text
        call_arg = output_manager.print.call_args[0][0]
        assert "test input" in str(call_arg)

    def test_success_prints_message(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test success prints with checkmark."""
        output_manager.print = MagicMock()
        test_ui.success("Done!")
        output_manager.print.assert_called_once()

    def test_error_prints_message(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test error prints with X."""
        output_manager.print = MagicMock()
        test_ui.error("Failed!")
        output_manager.print.assert_called_once()

    def test_warning_prints_message(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test warning prints with triangle."""
        output_manager.print = MagicMock()
        test_ui.warning("Careful!")
        output_manager.print.assert_called_once()

    def test_info_prints_message(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test info prints with i."""
        output_manager.print = MagicMock()
        test_ui.info("Note:")
        output_manager.print.assert_called_once()


class TestRequestCancel:
    """Tests for request_cancel facade."""

    def test_request_cancel_when_idle(self, test_ui: _UI) -> None:
        """Test request_cancel returns False when idle."""
        assert not test_ui.request_cancel()

    def test_request_cancel_when_cancelable(self, test_ui: _UI) -> None:
        """Test request_cancel cancels scope when in cancelable state."""
        scope = CancelScope()
        test_ui._state = _CancelableState(scope=scope)

        assert test_ui.request_cancel()
        assert scope.cancelled

    def test_request_cancel_strict_raises(self, test_ui: _UI) -> None:
        """Test request_cancel with strict=True raises when idle."""
        with pytest.raises(RuntimeError, match="Nothing to cancel"):
            test_ui.request_cancel(strict=True)


class TestRespondConfirm:
    """Tests for respond_confirm facade."""

    def test_respond_confirm_when_idle(self, test_ui: _UI) -> None:
        """Test respond_confirm returns False when idle."""
        assert not test_ui.respond_confirm(True)

    def test_respond_confirm_strict_raises(self, test_ui: _UI) -> None:
        """Test respond_confirm with strict=True raises when idle."""
        with pytest.raises(RuntimeError, match="No pending confirm"):
            test_ui.respond_confirm(True, strict=True)


class TestCollapsed:
    """Tests for collapsed output."""

    def test_collapsed_title_only(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test collapsed with max_chars=0 shows only title."""
        output_manager.print = MagicMock()
        test_ui.collapsed("Title", "Long content here\nLine 2\nLine 3")
        output_manager.print.assert_called_once()
        call_arg = str(output_manager.print.call_args[0][0])
        assert "Title" in call_arg
        assert "3 lines" in call_arg

    def test_collapsed_with_preview(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test collapsed with max_chars shows preview."""
        output_manager.print = MagicMock()
        test_ui.collapsed("Title", "A" * 200, max_chars=50)
        output_manager.print.assert_called_once()
        call_arg = str(output_manager.print.call_args[0][0])
        assert "Title" in call_arg
        assert "more chars" in call_arg

    def test_collapsed_full_content(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test collapsed with max_chars=None shows full content."""
        output_manager.print = MagicMock()
        test_ui.collapsed("Title", "Full content here", max_chars=None)
        output_manager.print.assert_called_once()
        call_arg = str(output_manager.print.call_args[0][0])
        assert "Full content here" in call_arg

    def test_thinking_uses_collapsed(self, test_ui: _UI, output_manager: OutputManager) -> None:
        """Test thinking delegates to collapsed."""
        output_manager.print = MagicMock()
        test_ui.thinking("Reasoning here")
        output_manager.print.assert_called_once()
        call_arg = str(output_manager.print.call_args[0][0])
        assert "Thinking" in call_arg
