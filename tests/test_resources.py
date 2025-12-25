"""Resource management and memory leak tests.

Tests for:
- Async task cleanup after context exit
- Memory bounds over long sessions
- No orphaned animation tasks
"""

from __future__ import annotations

import asyncio
import gc

import pytest


class TestTaskCleanup:
    """Verify async tasks are properly cleaned up."""

    async def test_status_animation_task_cancelled(self, test_ui):
        """Status animation task should be cancelled on exit."""
        with test_ui.status("Working..."):
            # Animation task is running
            await asyncio.sleep(0.1)

        # Give time for task cancellation
        await asyncio.sleep(0.05)

        # No lingering animation tasks
        for task in asyncio.all_tasks():
            coro_name = str(task.get_coro())
            assert "_animate" not in coro_name, f"Orphaned animation task: {coro_name}"

    async def test_group_animation_task_cancelled(self, test_ui):
        """Group animation task should be cancelled on exit."""
        with test_ui.group("Test") as g:
            t = g.task("Task")
            await asyncio.sleep(0.1)
            t.success()

        await asyncio.sleep(0.05)

        for task in asyncio.all_tasks():
            coro_name = str(task.get_coro())
            assert "_animate" not in coro_name, f"Orphaned animation task: {coro_name}"

    async def test_cancel_scope_has_task_reference(self, test_ui):
        """CancelScope should have task reference during context."""
        scope = None
        async with test_ui.cancelable() as s:
            scope = s
            # During the context, _task should reference the current task
            assert scope._task is not None
            assert scope._task is asyncio.current_task()

        # After exit, the scope's task reference is still the test task
        # (which is still running). This is fine - the scope is no longer
        # used after __aexit__ so the reference doesn't cause issues.

    async def test_multiple_status_contexts_no_task_leak(self, test_ui):
        """Multiple sequential status contexts should not leak tasks."""
        initial_tasks = len(asyncio.all_tasks())

        for i in range(10):
            with test_ui.status(f"Task {i}"):
                await asyncio.sleep(0.02)

        await asyncio.sleep(0.1)
        final_tasks = len(asyncio.all_tasks())

        # Should have same number of tasks (allow 1 for test framework)
        assert final_tasks <= initial_tasks + 1, f"Leaked {final_tasks - initial_tasks} tasks"

    async def test_exception_in_status_cancels_animation(self, test_ui):
        """Exception in status context should still cancel animation task."""
        initial_tasks = len(asyncio.all_tasks())

        for _ in range(5):
            with pytest.raises(ValueError), test_ui.status("Working..."):
                await asyncio.sleep(0.02)
                raise ValueError("Test")

        await asyncio.sleep(0.1)
        final_tasks = len(asyncio.all_tasks())
        assert final_tasks <= initial_tasks + 1


class TestMemoryBounds:
    """Verify memory doesn't grow unboundedly."""

    async def test_repeated_context_managers_no_leak(self, test_ui):
        """Repeated context manager usage should not leak."""
        gc.collect()
        initial_objects = len(gc.get_objects())

        for _ in range(100):
            with test_ui.status("Test"):
                await asyncio.sleep(0)

        for _ in range(100):
            with test_ui.group("Test") as g:
                await g.success("Done")

        gc.collect()
        final_objects = len(gc.get_objects())

        # Allow some growth but flag massive leaks (>10000 objects)
        growth = final_objects - initial_objects
        assert growth < 10000, f"Excessive object growth: {growth}"

    async def test_repeated_cancelable_no_state_leak(self, test_ui):
        """Repeated cancelable contexts should not leak state."""
        for i in range(100):
            async with test_ui.cancelable() as scope:
                if i % 10 == 0:
                    scope.cancel()
                    try:
                        await scope.checkpoint()
                    except asyncio.CancelledError:
                        pass

        assert test_ui._state is None, "State should be None after all contexts exit"

    @pytest.mark.slow
    async def test_long_session_memory_stable(self, test_ui):
        """Simulate long session - memory should stay bounded."""
        import tracemalloc

        tracemalloc.start()

        for i in range(500):
            async with test_ui.cancelable():
                with test_ui.status(f"Task {i}"):
                    await asyncio.sleep(0)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Fail if using more than 50MB (generous bound)
        assert current < 50 * 1024 * 1024, f"Memory: {current / 1024 / 1024:.1f}MB"

    @pytest.mark.slow
    async def test_groups_with_many_tasks_cleanup(self, test_ui):
        """Groups with many tasks should clean up properly."""
        gc.collect()

        for _ in range(50):
            with test_ui.group("Batch") as g:
                for j in range(10):
                    with g.task(f"Task {j}"):
                        await asyncio.sleep(0)

        gc.collect()
        # If we get here without OOM or hanging, test passes


class TestOutputManagerCleanup:
    """Tests for OutputManager live content cleanup."""

    async def test_live_content_cleared_after_status(self, test_ui):
        """Live content should be cleared after status context."""
        with test_ui.status("Working..."):
            await asyncio.sleep(0.02)

        assert not test_ui._output.has_live_content()

    async def test_live_content_cleared_after_progress(self, test_ui):
        """Live content should be cleared after progress context."""
        with test_ui.progress("Downloading", total=100) as p:
            p.update(100)

        assert not test_ui._output.has_live_content()

    async def test_live_content_cleared_after_group(self, test_ui):
        """Live content should be cleared after group context."""
        with test_ui.group("Test") as g:
            await g.success("Done")

        assert not test_ui._output.has_live_content()

    async def test_live_footer_cleared_after_cancelable(self, test_ui):
        """Live footer should be cleared after cancelable context."""
        async with test_ui.cancelable():
            pass

        assert not test_ui._output.has_live_content()

    async def test_live_content_cleared_on_exception(self, test_ui):
        """Live content should be cleared even on exception."""
        with pytest.raises(ValueError), test_ui.status("Working..."):
            raise ValueError("Test")

        assert not test_ui._output.has_live_content()
