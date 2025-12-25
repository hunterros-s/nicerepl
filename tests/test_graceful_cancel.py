"""Tests for graceful cancellation functionality."""

from __future__ import annotations

import asyncio
import time

import pytest

from nicerepl._ui import (
    _SLOW_CANCEL_THRESHOLD,
    CancelScope,
    _check_slow_cancel,
    _current_scope,
    check_cancelled,
)


class TestCancelScopeCompletionTracking:
    """Tests for CancelScope completion tracking."""

    def test_initial_completed_state(self) -> None:
        """Test initial completed state is False."""
        scope = CancelScope()
        assert not scope.completed

    def test_mark_completed_sets_flag(self) -> None:
        """Test _mark_completed sets the completed flag."""
        scope = CancelScope()
        assert not scope.completed
        scope._mark_completed()
        assert scope.completed

    @pytest.mark.asyncio
    async def test_wait_completed_blocks_until_marked(self) -> None:
        """Test wait_completed blocks until _mark_completed is called."""
        scope = CancelScope()

        async def mark_later():
            await asyncio.sleep(0.05)
            scope._mark_completed()

        # Start the marking task
        mark_task = asyncio.create_task(mark_later())

        # Wait should complete when mark_completed is called
        await asyncio.wait_for(scope.wait_completed(), timeout=1.0)
        assert scope.completed

        await mark_task

    @pytest.mark.asyncio
    async def test_wait_completed_returns_immediately_if_already_complete(self) -> None:
        """Test wait_completed returns immediately if already completed."""
        scope = CancelScope()
        scope._mark_completed()

        # Should not block
        await asyncio.wait_for(scope.wait_completed(), timeout=0.1)

    def test_cancel_sets_cancel_time(self) -> None:
        """Test cancel() sets _cancel_time."""
        scope = CancelScope()
        assert scope._cancel_time is None
        scope.cancel()
        assert scope._cancel_time is not None
        assert scope._cancel_time <= time.monotonic()

    def test_cancel_only_sets_time_once(self) -> None:
        """Test cancel() only sets _cancel_time on first call."""
        scope = CancelScope()
        scope.cancel()
        first_time = scope._cancel_time
        scope.cancel()  # Second call
        assert scope._cancel_time == first_time


class TestCheckCancelled:
    """Tests for check_cancelled() global helper."""

    def test_check_cancelled_no_scope(self) -> None:
        """Test check_cancelled does nothing when no scope is active."""
        # Should not raise
        check_cancelled()

    def test_check_cancelled_scope_not_cancelled(self) -> None:
        """Test check_cancelled does nothing when scope is not cancelled."""
        scope = CancelScope()
        token = _current_scope.set(scope)
        try:
            # Should not raise
            check_cancelled()
        finally:
            _current_scope.reset(token)

    def test_check_cancelled_scope_cancelled(self) -> None:
        """Test check_cancelled raises when scope is cancelled."""
        scope = CancelScope()
        scope.cancel()
        token = _current_scope.set(scope)
        try:
            with pytest.raises(asyncio.CancelledError):
                check_cancelled()
        finally:
            _current_scope.reset(token)


class TestScopeIter:
    """Tests for scope.iter() sync iteration wrapper."""

    def test_iter_completes_without_cancel(self) -> None:
        """Test iter completes when not cancelled."""
        scope = CancelScope()
        items = list(range(5))
        result = list(scope.iter(items))
        assert result == items

    def test_iter_raises_when_cancelled(self) -> None:
        """Test iter raises CancelledError when scope is cancelled."""
        scope = CancelScope()
        items = list(range(100))
        result = []

        with pytest.raises(asyncio.CancelledError):
            for i, item in enumerate(scope.iter(items)):
                result.append(item)
                if i == 5:
                    scope.cancel()

        # Should have processed items 0-5 before cancel was detected
        assert len(result) == 6
        assert result == list(range(6))


class TestScopeAiter:
    """Tests for scope.aiter() async iteration wrapper."""

    @pytest.mark.asyncio
    async def test_aiter_completes_without_cancel(self) -> None:
        """Test aiter completes when not cancelled."""
        scope = CancelScope()

        async def async_items():
            for i in range(5):
                yield i

        result = [item async for item in scope.aiter(async_items())]
        assert result == list(range(5))

    @pytest.mark.asyncio
    async def test_aiter_raises_when_cancelled(self) -> None:
        """Test aiter raises CancelledError when scope is cancelled."""
        scope = CancelScope()

        async def async_items():
            for i in range(100):
                yield i

        result = []
        i = 0
        with pytest.raises(asyncio.CancelledError):
            async for item in scope.aiter(async_items()):
                result.append(item)
                if i == 5:
                    scope.cancel()
                i += 1

        # Should have processed items 0-5 before cancel was detected
        assert len(result) == 6


class TestSlowCancelWarning:
    """Tests for slow cancel warning functionality."""

    def test_check_slow_cancel_no_scope(self) -> None:
        """Test _check_slow_cancel does nothing when no scope is active."""
        from unittest.mock import MagicMock

        mock_output = MagicMock()
        # Should not raise or call set_live_footer
        _check_slow_cancel(mock_output)
        mock_output.set_live_footer.assert_not_called()

    def test_check_slow_cancel_not_cancelling(self) -> None:
        """Test _check_slow_cancel does nothing when not cancelling."""
        from unittest.mock import MagicMock

        scope = CancelScope()
        token = _current_scope.set(scope)
        try:
            mock_output = MagicMock()
            _check_slow_cancel(mock_output)
            mock_output.set_live_footer.assert_not_called()
        finally:
            _current_scope.reset(token)

    def test_check_slow_cancel_quick_cancel(self) -> None:
        """Test _check_slow_cancel does nothing for quick cancels."""
        from unittest.mock import MagicMock

        scope = CancelScope()
        scope.cancel()
        token = _current_scope.set(scope)
        try:
            mock_output = MagicMock()
            # Called immediately after cancel, should be under threshold
            _check_slow_cancel(mock_output)
            mock_output.set_live_footer.assert_not_called()
        finally:
            _current_scope.reset(token)

    def test_check_slow_cancel_slow_cancel(self) -> None:
        """Test _check_slow_cancel shows warning for slow cancels."""
        from unittest.mock import MagicMock

        from rich.text import Text

        scope = CancelScope()
        scope.cancel()
        # Simulate time passing by setting _cancel_time in the past
        scope._cancel_time = time.monotonic() - _SLOW_CANCEL_THRESHOLD - 1

        token = _current_scope.set(scope)
        try:
            mock_output = MagicMock()
            _check_slow_cancel(mock_output)
            mock_output.set_live_footer.assert_called_once()
            # Check the footer text
            call_args = mock_output.set_live_footer.call_args
            footer_text = call_args[0][0]
            assert isinstance(footer_text, Text)
            assert "slow to cancel" in str(footer_text)
        finally:
            _current_scope.reset(token)


class TestContextVariable:
    """Tests for _current_scope context variable."""

    def test_default_is_none(self) -> None:
        """Test default value is None."""
        assert _current_scope.get() is None

    def test_set_and_reset(self) -> None:
        """Test setting and resetting the context variable."""
        scope = CancelScope()
        assert _current_scope.get() is None

        token = _current_scope.set(scope)
        assert _current_scope.get() is scope

        _current_scope.reset(token)
        assert _current_scope.get() is None

    def test_nested_scopes(self) -> None:
        """Test nested scope handling."""
        scope1 = CancelScope()
        scope2 = CancelScope()

        assert _current_scope.get() is None

        token1 = _current_scope.set(scope1)
        assert _current_scope.get() is scope1

        token2 = _current_scope.set(scope2)
        assert _current_scope.get() is scope2

        _current_scope.reset(token2)
        assert _current_scope.get() is scope1

        _current_scope.reset(token1)
        assert _current_scope.get() is None
