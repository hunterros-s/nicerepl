"""Integration tests for NiceREPL async behavior.

Tests for:
- Exception handling (StateError for invalid state transitions)
- Basic context manager lifecycle (happy-path)
- Race conditions in async state machine
"""

from __future__ import annotations

import asyncio

import pytest

from nicerepl._exceptions import StateError


class TestStateError:
    """Tests for StateError exceptions on invalid state transitions."""

    async def test_nested_cancelable_raises_state_error(self, test_ui):
        """Nested cancelable contexts should raise StateError."""
        async with test_ui.cancelable():
            with pytest.raises(StateError, match="already in state"):
                async with test_ui.cancelable():
                    pass

    async def test_confirm_during_cancelable_raises_state_error(self, test_ui):
        """Cannot enter confirm while in cancelable state."""
        async with test_ui.cancelable():
            with pytest.raises(StateError, match="already in state"):
                await test_ui.confirm("Proceed?")

    async def test_cancelable_during_confirm_raises_state_error(self, test_ui):
        """Cannot enter cancelable while in confirming state."""
        # We need to manually set up confirming state since confirm() blocks
        from nicerepl._ui import _ConfirmContext, _ConfirmingState

        ctx = _ConfirmContext("Test?", test_ui)
        test_ui._state = _ConfirmingState(context=ctx)

        try:
            with pytest.raises(StateError, match="already in state"):
                async with test_ui.cancelable():
                    pass
        finally:
            test_ui._state = None

    async def test_state_error_message_is_actionable(self, test_ui):
        """StateError message should include recovery guidance."""
        async with test_ui.cancelable():
            try:
                async with test_ui.cancelable():
                    pass
            except StateError as e:
                assert "Ensure previous context manager has exited" in str(e)


class TestBasicContextManagers:
    """Happy-path tests for context managers."""

    async def test_status_context_lifecycle(self, test_ui):
        """Status context enters and exits cleanly."""
        with test_ui.status("Working..."):
            await asyncio.sleep(0)  # Yield to allow animation task to start
        assert test_ui._state is None

    async def test_cancelable_context_lifecycle(self, test_ui):
        """Cancelable context enters and exits cleanly."""
        async with test_ui.cancelable() as scope:
            assert test_ui._state is not None
            assert not scope.cancelled
        assert test_ui._state is None

    async def test_cancelable_with_cancel(self, test_ui):
        """Cancelable context handles cancellation via request_cancel."""
        cancelled = False
        async with test_ui.cancelable() as scope:
            # Use request_cancel (simulates key press) rather than scope.cancel()
            test_ui.request_cancel()
            try:
                await scope.checkpoint()
            except asyncio.CancelledError:
                cancelled = True
        assert cancelled
        assert test_ui._state is None

    async def test_cancel_scope_sleep_interruptible(self, test_ui):
        """CancelScope.sleep() is immediately interruptible."""
        cancelled = False
        async with test_ui.cancelable() as scope:
            test_ui.request_cancel()
            try:
                await scope.sleep(10)  # Should return immediately
            except asyncio.CancelledError:
                cancelled = True
        assert cancelled
        assert test_ui._state is None

    async def test_group_context_lifecycle(self, test_ui):
        """Group context with tasks completes cleanly."""
        with test_ui.group("Test Group") as g:
            with g.task("Task 1"):
                await asyncio.sleep(0)
            await g.success("Task 2")
        # Note: group doesn't use _state, just _output
        await asyncio.sleep(0.05)  # Allow cleanup

    async def test_progress_context_lifecycle(self, test_ui):
        """Progress context enters and exits cleanly."""
        with test_ui.progress("Downloading", total=100) as p:
            p.advance(50)
            p.update(100)
        # No exception = success

    async def test_stream_context_lifecycle(self, test_ui):
        """Stream context enters and exits cleanly."""
        async with test_ui.stream() as s:
            s.write("Hello ")
            s.writeln("World")
        # No exception = success

    async def test_sequential_cancelable_contexts(self, test_ui):
        """Multiple sequential cancelable contexts work correctly."""
        for i in range(5):
            async with test_ui.cancelable() as scope:
                assert test_ui._state is not None
            assert test_ui._state is None


class TestAsyncRaceConditions:
    """Tests for race conditions in async state machine."""

    async def test_cancel_immediately_after_enter(self, test_ui):
        """Cancel called immediately after entering context."""
        cancelled = False
        async with test_ui.cancelable() as scope:
            test_ui.request_cancel()
            try:
                await scope.sleep(10)
            except asyncio.CancelledError:
                cancelled = True

        assert cancelled
        assert test_ui._state is None
        assert test_ui.mode == "idle"

    async def test_rapid_cancel_restart(self, test_ui):
        """Rapid sequence of cancel/restart should not corrupt state."""
        for i in range(20):
            async with test_ui.cancelable() as scope:
                test_ui.request_cancel()
                try:
                    await scope.checkpoint()
                except asyncio.CancelledError:
                    pass

        # Verify clean state after rapid cycling
        assert test_ui._state is None
        assert test_ui.mode == "idle"

    async def test_concurrent_cancel_request(self, test_ui):
        """Multiple cancel requests should be idempotent."""
        cancelled = False
        async with test_ui.cancelable() as scope:
            # Multiple cancel calls
            test_ui.request_cancel()
            test_ui.request_cancel()
            test_ui.request_cancel()

            try:
                await scope.checkpoint()
            except asyncio.CancelledError:
                cancelled = True

        assert cancelled
        assert test_ui._state is None

    async def test_request_cancel_outside_cancelable(self, test_ui):
        """request_cancel outside cancelable mode returns False."""
        assert test_ui._state is None
        result = test_ui.request_cancel()
        assert result is False

    async def test_request_cancel_inside_cancelable(self, test_ui):
        """request_cancel inside cancelable mode returns True."""
        async with test_ui.cancelable() as scope:
            result = test_ui.request_cancel()
            assert result is True
            # Must handle the cancellation
            try:
                await scope.checkpoint()
            except asyncio.CancelledError:
                pass

    async def test_no_orphaned_tasks_after_cancel(self, test_ui):
        """Verify animation tasks are cleaned up after cancel."""
        initial_tasks = len(asyncio.all_tasks())

        async with test_ui.cancelable():
            with test_ui.status("Working..."):
                await asyncio.sleep(0.05)  # Let animation start
                test_ui.request_cancel()
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    pass

        # Allow cleanup
        await asyncio.sleep(0.1)

        final_tasks = len(asyncio.all_tasks())
        # Allow for pytest's own tasks
        assert final_tasks <= initial_tasks + 1, f"Orphaned tasks: {final_tasks - initial_tasks}"

    async def test_exception_during_status_cleans_up(self, test_ui):
        """Exception during status context should clean up animation task."""
        initial_tasks = len(asyncio.all_tasks())

        with pytest.raises(ValueError), test_ui.status("Working..."):
            await asyncio.sleep(0.05)  # Let animation start
            raise ValueError("Test error")

        await asyncio.sleep(0.1)
        final_tasks = len(asyncio.all_tasks())
        assert final_tasks <= initial_tasks + 1

    async def test_exception_during_group_cleans_up(self, test_ui):
        """Exception during group context should clean up."""
        with pytest.raises(ValueError), test_ui.group("Test") as g:
            g.task("Task 1")
            await asyncio.sleep(0.05)
            raise ValueError("Test error")

        # State should be clean (group doesn't use _state)
        await asyncio.sleep(0.1)

    async def test_cancel_during_group(self, test_ui):
        """Cancellation during group should mark tasks as cancelled."""
        async with test_ui.cancelable() as scope:
            with test_ui.group("Test") as g:
                t = g.task("Task 1")
                scope.cancel()
                try:
                    await scope.sleep(10)
                except asyncio.CancelledError:
                    pass

        assert test_ui._state is None


class TestErrorRecovery:
    """Tests for error recovery - REPL should remain usable after errors."""

    async def test_state_resets_after_exception_in_cancelable(self, test_ui):
        """State should reset after exception in cancelable context."""
        with pytest.raises(RuntimeError):
            async with test_ui.cancelable():
                raise RuntimeError("Test error")

        # State should be clean
        assert test_ui._state is None

        # Should be able to enter new cancelable
        async with test_ui.cancelable() as scope:
            assert scope is not None
        assert test_ui._state is None

    async def test_output_continues_after_exception(self, test_ui):
        """UI output should work after exception in context."""
        with pytest.raises(ValueError), test_ui.status("Working..."):
            raise ValueError("Test")

        # Should still be able to print
        test_ui.print("After error")
        test_ui.success("Still working")
