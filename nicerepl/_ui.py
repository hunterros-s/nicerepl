"""UI singleton for NiceREPL output.

This module provides:
- CancelScope: Cooperative cancellation using async events
- State types: Union-based state machine for UI modes
- Context managers: Status, Progress, Stream, Group, Cancelable, Confirm
- _UI class: Main UI singleton with output methods and context managers
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

T = TypeVar("T")

from rich.console import RenderableType
from rich.text import Text

# =============================================================================
# CANCEL SCOPE
# =============================================================================

# Context variable to track the current active cancel scope
_current_scope: ContextVar[CancelScope | None] = ContextVar("cancel_scope", default=None)


class CancelScope:
    """Cooperative cancellation scope.

    Cancellation is checked automatically at every `await`. You only need
    explicit checks for synchronous loops:

        # Async code - cancellation is automatic
        async for line in async_file:
            await process(line)

        # Sync iteration - use wrapper
        for item in scope.iter(sync_iterable):
            process(item)

        # Tight CPU loop - explicit check
        for i in range(1000000):
            if i % 1000 == 0:
                check_cancelled()
            compute(i)
    """

    def __init__(self) -> None:
        self._cancel_event = asyncio.Event()
        self._completed_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._token: Token | None = None
        self._cancel_time: float | None = None

    def cancel(self) -> None:
        """Request cancellation of this scope.

        This is idempotent - multiple calls have the same effect as one.
        Cancellation is cooperative - code must check via checkpoint(), sleep(),
        iter(), aiter(), or check_cancelled().
        """
        if not self._cancel_event.is_set():
            self._cancel_event.set()
            self._cancel_time = time.monotonic()

    @property
    def cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancel_event.is_set()

    @property
    def completed(self) -> bool:
        """Check if the scope has completed (cleanup finished)."""
        return self._completed_event.is_set()

    def _mark_completed(self) -> None:
        """Mark this scope as completed. Called by _CancelableContext.__aexit__."""
        self._completed_event.set()

    async def wait_completed(self) -> None:
        """Wait until the scope has completed cleanup."""
        await self._completed_event.wait()

    async def checkpoint(self) -> None:
        """Yield point - raises CancelledError if scope is cancelled."""
        if self._cancel_event.is_set():
            raise asyncio.CancelledError()
        await asyncio.sleep(0)

    async def sleep(self, seconds: float) -> None:
        """Sleep that's immediately interruptible by cancel()."""
        if self._cancel_event.is_set():
            raise asyncio.CancelledError()

        try:
            await asyncio.wait_for(self._cancel_event.wait(), timeout=seconds)
            # Event was set before timeout expired
            raise asyncio.CancelledError()
        except asyncio.TimeoutError:
            # Timeout expired = normal sleep completion
            pass

    def iter(self, iterable: Iterable[T]) -> Iterator[T]:
        """Wrap sync iterable to check cancellation each iteration.

        Example:
            for chunk in scope.iter(large_file):
                process(chunk)  # Cancellation checked automatically
        """
        for item in iterable:
            if self._cancel_event.is_set():
                raise asyncio.CancelledError()
            yield item

    async def aiter(self, async_iterable: AsyncIterable[T]) -> AsyncIterator[T]:
        """Wrap async iterable to check cancellation each iteration."""
        async for item in async_iterable:
            if self._cancel_event.is_set():
                raise asyncio.CancelledError()
            yield item


def check_cancelled() -> None:
    """Check if current operation should cancel. Call in tight loops.

    Raises CancelledError if the current cancel scope has been cancelled.
    Safe to call outside of a cancel scope (does nothing).

    Example:
        for i in range(1000000):
            if i % 1000 == 0:
                check_cancelled()
            compute(i)
    """
    scope = _current_scope.get()
    if scope and scope.cancelled:
        raise asyncio.CancelledError()


# Slow cancel warning threshold in seconds
_SLOW_CANCEL_THRESHOLD = 3.0


def _check_slow_cancel(output: OutputManager) -> None:
    """Check if cancel is taking too long and update footer if so."""
    scope = _current_scope.get()
    if scope and scope._cancel_time is not None:
        elapsed = time.monotonic() - scope._cancel_time
        if elapsed >= _SLOW_CANCEL_THRESHOLD:
            output.set_live_footer(Text("(operation slow to cancel...)", style="dim yellow"))


def _with_checkpoint(f):
    """Decorator that adds checkpoint after method execution.

    Works with methods on objects that have a `_ui` attribute pointing to the UI singleton.
    Calls checkpoint() on the current cancel scope if one is active.
    """

    @functools.wraps(f)
    async def wrapper(self, *args, **kwargs):
        result = f(self, *args, **kwargs)
        # Get scope from UI state instead of ContextVar
        if isinstance(self._ui._state, _CancelableState):
            await self._ui._state.scope.checkpoint()
        return result

    return wrapper


from nicerepl.styles import (
    COLOR_CANCELLED,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SPINNER,
    COLOR_SUCCESS,
    COLOR_WARNING,
    ICON_BULLET,
    ICON_CANCELLED,
    ICON_ERROR,
    ICON_INFO,
    ICON_SUCCESS,
    ICON_WARNING,
    SPINNER_FRAMES,
    TREE_LAST,
    TREE_MID,
)

if TYPE_CHECKING:
    from nicerepl._output import OutputManager


# =============================================================================
# STATE TYPES
# =============================================================================
# Union type makes invalid states unrepresentable - only one mode at a time


@dataclass
class _CancelableState:
    """State when inside ui.cancelable() context."""

    scope: CancelScope


@dataclass
class _ConfirmingState:
    """State when waiting for y/n confirm response."""

    context: _ConfirmContext


# Union type: can only be in one state at a time
_UIState = None | _CancelableState | _ConfirmingState


# =============================================================================
# CONTEXT MANAGERS
# =============================================================================
# These provide the ui.status(), ui.progress(), etc. context manager syntax


class _StatusContext:
    """Context manager for status spinner."""

    def __init__(self, message: str, ui: _UI) -> None:
        self._message = message
        self._ui = ui
        self._frame = 0
        self._task: asyncio.Task | None = None

    def update(self, message: str) -> None:
        """Update the status message."""
        self._message = message
        self._update_display()

    def _update_display(self) -> None:
        frame_char = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
        text = Text.assemble(
            (f"{frame_char} ", COLOR_SPINNER),
            self._message,
        )
        self._ui._out.set_live(text)

    async def _animate(self) -> None:
        try:
            while True:
                await asyncio.sleep(0.08)
                self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
                self._update_display()
                _check_slow_cancel(self._ui._out)
        except asyncio.CancelledError:
            pass

    def __enter__(self) -> _StatusContext:
        self._update_display()
        self._task = asyncio.create_task(self._animate())
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

        if exc_type is None:
            text = Text.assemble((f"{ICON_SUCCESS} ", "green"), self._message)
        else:
            text = Text.assemble((f"{ICON_ERROR} ", "red"), self._message)
        self._ui._out.print(text)
        self._ui._out.clear_live()


class _ProgressContext:
    """Context manager for progress bar using Rich Progress."""

    def __init__(
        self,
        description: str,
        total: float,
        ui: _UI,
        show_percentage: bool = True,
        show_speed: bool = False,
        show_time: bool = False,
        bar_width: int = 25,
    ) -> None:
        from rich.progress import (
            BarColumn,
            Progress,
            SpinnerColumn,
            TaskProgressColumn,
            TextColumn,
            TimeRemainingColumn,
            TransferSpeedColumn,
        )

        self._description = description
        self._total = total
        self._ui = ui

        columns = [
            SpinnerColumn(),
            TextColumn("[cyan]{task.description}"),
            BarColumn(bar_width=bar_width),
        ]
        if show_percentage:
            columns.append(TaskProgressColumn())
        if show_speed:
            columns.append(TransferSpeedColumn())
        if show_time:
            columns.append(TimeRemainingColumn())

        self._progress = Progress(*columns, disable=True)  # Disable auto-refresh
        self._task_id = None

    def advance(self, amount: float = 1) -> None:
        """Advance progress by the given amount."""
        if self._task_id is None:
            raise RuntimeError("advance() called outside of context manager")
        self._progress.advance(self._task_id, amount)
        self._update_display()

    def update(self, completed: float) -> None:
        """Set absolute progress value."""
        if self._task_id is None:
            raise RuntimeError("update() called outside of context manager")
        self._progress.update(self._task_id, completed=completed)
        self._update_display()

    def _update_display(self) -> None:
        self._ui._out.set_live(self._progress.get_renderable())

    def __enter__(self) -> _ProgressContext:
        self._task_id = self._progress.add_task(self._description, total=self._total)
        self._update_display()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is None:
            text = Text.assemble((f"{ICON_SUCCESS} ", "green"), f"{self._description} complete")
        else:
            text = Text.assemble((f"{ICON_ERROR} ", "red"), f"{self._description} failed")
        self._ui._out.print(text)
        self._ui._out.clear_live()


class _CancelableContext:
    """Async context manager for cancelable operations with cancel scope."""

    def __init__(self, ui: _UI) -> None:
        self._ui = ui
        self._scope = CancelScope()

    async def __aenter__(self) -> CancelScope:
        if self._ui._state is not None:
            from nicerepl._exceptions import StateError

            raise StateError(
                f"Cannot enter cancelable: already in state {self._ui._state}. "
                f"Ensure previous context manager has exited."
            )

        self._ui._state = _CancelableState(scope=self._scope)
        self._scope._task = asyncio.current_task()
        # Set context variable for check_cancelled() and _check_slow_cancel()
        self._scope._token = _current_scope.set(self._scope)
        self._ui._out.set_live_footer(Text("(esc to interrupt)", style="dim"))
        return self._scope  # Return scope so users can call scope.sleep()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool | None:
        # Signal completion so request_cancel() callers know we're done
        self._scope._mark_completed()

        # Reset context variable
        if self._scope._token is not None:
            _current_scope.reset(self._scope._token)

        self._ui._state = None
        self._ui._out.clear_live_footer()
        self._ui._out.clear_live()
        if exc_type is asyncio.CancelledError:
            self._ui.error("Interrupted")
            return True  # Suppress, don't propagate
        return None


class _ConfirmContext:
    """Blocking confirmation prompt."""

    def __init__(self, message: str, ui: _UI) -> None:
        self._message = message
        self._ui = ui
        self._result: bool | None = None
        self._event = asyncio.Event()

    def respond(self, value: bool) -> None:
        """Called by key handler to set result."""
        self._result = value
        self._event.set()

    async def wait(self) -> bool:
        """Show prompt and wait for y/n response."""
        if self._ui._state is not None:
            from nicerepl._exceptions import StateError

            raise StateError(
                f"Cannot enter confirm: already in state {self._ui._state}. "
                f"Ensure previous context manager has exited."
            )

        self._ui._state = _ConfirmingState(context=self)
        self._ui._out.set_live(
            Text.assemble(
                ("? ", "yellow"),
                self._message,
                (" [y/n] ", "dim"),
            )
        )

        try:
            await self._event.wait()
        finally:
            self._ui._state = None
            self._ui._out.clear_live()

        # After event.wait(), respond() must have been called
        if self._result is None:
            raise RuntimeError("Confirm event set but no result provided")

        # Print result to scrollback
        icon = ICON_SUCCESS if self._result else ICON_ERROR
        color = COLOR_SUCCESS if self._result else COLOR_ERROR
        answer = "yes" if self._result else "no"
        self._ui._out.print(
            Text.assemble(
                (f"{icon} ", color),
                self._message,
                (f" {answer}", "dim"),
            )
        )

        return self._result


class _StreamContext:
    """Async context manager for streaming text."""

    def __init__(self, ui: _UI) -> None:
        self._ui = ui
        self._buffer = ""

    def write(self, text: str) -> None:
        """Append text to the stream."""
        self._buffer += text
        self._ui._out.set_live(self._buffer)

    def writeln(self, text: str) -> None:
        """Append text with newline."""
        self.write(text + "\n")

    async def __aenter__(self) -> _StreamContext:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._buffer:
            self._ui._out.print(self._buffer)
        self._ui._out.clear_live()


class _Task:
    """A live item in a group. Spinner until completed."""

    def __init__(self, group: _GroupContext, text: str, index: int) -> None:
        self._group = group
        self._text = text
        self._index = index
        self._completed = False

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = value
        self._group._update_task(self._index, value)

    def success(self, text: str | None = None) -> None:
        self._complete(ICON_SUCCESS, COLOR_SUCCESS, text)

    def error(self, text: str | None = None) -> None:
        self._complete(ICON_ERROR, COLOR_ERROR, text)

    def warning(self, text: str | None = None) -> None:
        self._complete(ICON_WARNING, COLOR_WARNING, text)

    def info(self, text: str | None = None) -> None:
        self._complete(ICON_INFO, COLOR_INFO, text)

    def cancelled(self, text: str | None = None) -> None:
        self._complete(ICON_CANCELLED, COLOR_CANCELLED, text)

    def _complete(self, icon: str, color: str, text: str | None) -> None:
        if self._completed:
            return
        self._completed = True
        self._group._finish_task(self._index, icon, color, text or self._text)

    def __enter__(self) -> _Task:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not self._completed:
            if exc_type is asyncio.CancelledError:
                self.cancelled()
            elif exc_type:
                self.error()
            else:
                self.success()

    async def __aenter__(self) -> _Task:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


class _GroupContext:
    """Context manager for grouped output with tree brackets."""

    def __init__(self, title: str, ui: _UI, icon: str | None = None) -> None:
        self._title = title
        self._ui = ui
        self._icon = icon or ICON_BULLET
        self._items: list[tuple[str, str | None, str | None, bool]] = []
        self._tasks: list[_Task] = []
        self._frame = 0
        self._anim_task: asyncio.Task | None = None

    def task(self, text: str) -> _Task:
        """Create a live task with spinner."""
        index = len(self._items)
        self._items.append((text, None, None, True))
        self._update_display()
        t = _Task(self, text, index)
        self._tasks.append(t)
        return t

    @_with_checkpoint
    def success(self, text: str) -> None:
        """Add a completed success item."""
        self.task(text).success()

    @_with_checkpoint
    def error(self, text: str) -> None:
        """Add a completed error item."""
        self.task(text).error()

    @_with_checkpoint
    def warning(self, text: str) -> None:
        """Add a completed warning item."""
        self.task(text).warning()

    @_with_checkpoint
    def info(self, text: str) -> None:
        """Add a completed info item."""
        self.task(text).info()

    @_with_checkpoint
    def cancelled(self, text: str) -> None:
        """Add a completed cancelled item."""
        self.task(text).cancelled()

    def _update_task(self, index: int, text: str) -> None:
        """Called by Task.text setter."""
        old = self._items[index]
        self._items[index] = (text, old[1], old[2], old[3])
        self._update_display()

    def _finish_task(self, index: int, icon: str, color: str, text: str) -> None:
        """Called by Task completion methods."""
        self._items[index] = (text, icon, color, False)
        self._update_display()

    def _update_display(self) -> None:
        """Update live display with current state."""
        lines = [Text.assemble((f"{self._icon} ", COLOR_SPINNER), self._title)]

        for i, (text, icon, color, is_loading) in enumerate(self._items):
            is_last = i == len(self._items) - 1
            connector = TREE_LAST if is_last else TREE_MID

            if is_loading:
                frame = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
                line = Text.assemble(
                    (connector, "dim"),
                    (f"{frame} ", COLOR_SPINNER),
                    (text, "dim"),
                )
            elif icon:
                line = Text.assemble(
                    (connector, "dim"),
                    (f"{icon} ", color or ""),
                    (text, "dim"),
                )
            else:
                line = Text.assemble((connector, "dim"), (text, "dim"))
            lines.append(line)

        content = Text("\n").join(lines)
        self._ui._out.set_live(content)

    def _render_final(self, success: bool, cancelled: bool = False) -> Text:
        """Render final output with correct last-item connector."""
        if cancelled:
            icon, color = ICON_CANCELLED, COLOR_CANCELLED
        elif success:
            icon, color = ICON_SUCCESS, COLOR_SUCCESS
        else:
            icon, color = ICON_ERROR, COLOR_ERROR

        lines = [Text.assemble((f"{icon} ", color), self._title)]

        for i, (text, item_icon, item_color, _) in enumerate(self._items):
            is_last = i == len(self._items) - 1
            connector = TREE_LAST if is_last else TREE_MID

            if item_icon:
                line = Text.assemble(
                    (connector, "dim"),
                    (f"{item_icon} ", item_color or ""),
                    (text, "dim"),
                )
            else:
                line = Text.assemble((connector, "dim"), (text, "dim"))
            lines.append(line)

        return Text("\n").join(lines)

    async def _animate(self) -> None:
        """Animate spinners for loading items."""
        try:
            while True:
                await asyncio.sleep(0.08)
                self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
                if any(item[3] for item in self._items):
                    self._update_display()
                _check_slow_cancel(self._ui._out)
        except asyncio.CancelledError:
            pass

    def __enter__(self) -> _GroupContext:
        self._update_display()
        self._anim_task = asyncio.create_task(self._animate())
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        is_cancelled = exc_type is asyncio.CancelledError
        for t in self._tasks:
            if not t._completed:
                t.cancelled() if is_cancelled else t.error()

        if self._anim_task:
            self._anim_task.cancel()
            self._anim_task = None
        self._ui._out.clear_live()
        final = self._render_final(success=(exc_type is None), cancelled=is_cancelled)
        self._ui._out.print(final)


# =============================================================================
# UI CLASS
# =============================================================================
# Main UI singleton providing output methods and context managers


class _UI:
    """UI singleton for all output operations."""

    def __init__(self) -> None:
        self._output: OutputManager | None = None
        self._state: _UIState = None  # Union type for UI state

    @property
    def mode(self) -> str:
        """Current UI mode (for debugging/logging)."""
        if self._state is None:
            return "idle"
        return type(self._state).__name__.removeprefix("_").removesuffix("State").lower()

    # === Facade Methods (for REPL key handlers) ===

    def request_cancel(self, *, strict: bool = False) -> bool:
        """Request cancellation of current operation.

        Returns True if something was cancelled, False otherwise.
        Use strict=True to raise RuntimeError if nothing to cancel.
        """
        if isinstance(self._state, _CancelableState):
            # Show cancelling footer IMMEDIATELY
            self._out.set_live_footer(Text("(cancelling...)", style="dim yellow"))
            self._state.scope.cancel()
            return True
        if strict:
            raise RuntimeError("Nothing to cancel - not in cancelable mode")
        return False

    def respond_confirm(self, value: bool, *, strict: bool = False) -> bool:
        """Respond to a pending confirmation prompt.

        Returns True if there was a pending confirm, False otherwise.
        Use strict=True to raise RuntimeError if no pending confirm.
        """
        if isinstance(self._state, _ConfirmingState):
            self._state.context.respond(value)
            return True
        if strict:
            raise RuntimeError("No pending confirm - not in confirming mode")
        return False

    # === Internal Methods ===

    def _bind(self, output: OutputManager) -> None:
        """Bind to an OutputManager instance."""
        self._output = output

    def _check_bound(self) -> None:
        if self._output is None:
            raise RuntimeError("UI not bound to REPL. Call repl.run() first.")

    @property
    def _out(self) -> OutputManager:
        """Get output manager, raising if not bound."""
        if self._output is None:
            raise RuntimeError("UI not bound to REPL. Call repl.run() first.")
        return self._output

    def _reset(self) -> None:
        """Reset UI state for testing. Clears output binding and state."""
        self._output = None
        self._state = None

    # === Output Methods ===

    def print(self, content: RenderableType | str) -> None:
        """Print any Rich renderable to scrollback."""
        self._out.print(content)

    def echo(self, text: str) -> None:
        """Echo user input with > prefix and dark background highlight."""
        self._out.print(Text(f"> {text}", style="white on grey23"))

    def code(self, code: str, *, language: str = "python", title: str | None = None) -> None:
        """Print syntax-highlighted code block."""
        from nicerepl._components import CodeBlock

        self._out.print(CodeBlock(code, language=language, title=title))

    def markdown(self, text: str) -> None:
        """Print rendered markdown."""
        from rich.markdown import Markdown

        self._out.print(Markdown(text))

    # === Status Badges ===

    def success(self, message: str) -> None:
        """Print success badge (green checkmark)."""
        self._out.print(Text.assemble((f"{ICON_SUCCESS} ", "green"), message))

    def error(self, message: str) -> None:
        """Print error badge (red X)."""
        self._out.print(Text.assemble((f"{ICON_ERROR} ", "red"), message))

    def warning(self, message: str) -> None:
        """Print warning badge (yellow triangle)."""
        self._out.print(Text.assemble((f"{ICON_WARNING} ", "yellow"), message))

    def info(self, message: str) -> None:
        """Print info badge (blue i)."""
        self._out.print(Text.assemble((f"{ICON_INFO} ", "blue"), message))

    # === Context Managers ===

    def status(self, message: str = "Working...") -> _StatusContext:
        """Create a status spinner context manager.

        Example:
            with ui.status("Thinking..."):
                await do_work()
        """
        self._check_bound()
        return _StatusContext(message, self)

    def progress(
        self,
        description: str = "Progress",
        total: float = 100,
        show_percentage: bool = True,
        show_speed: bool = False,
        show_time: bool = False,
        bar_width: int = 25,
    ) -> _ProgressContext:
        """Create a progress bar context manager.

        Example:
            with ui.progress("Downloading", total=100) as p:
                for i in range(100):
                    p.advance(1)
        """
        self._check_bound()
        return _ProgressContext(
            description,
            total,
            self,
            show_percentage=show_percentage,
            show_speed=show_speed,
            show_time=show_time,
            bar_width=bar_width,
        )

    def stream(self) -> _StreamContext:
        """Create a streaming text async context manager.

        Example:
            async with ui.stream() as s:
                async for chunk in generate():
                    s.write(chunk)
        """
        self._check_bound()
        return _StreamContext(self)

    def group(self, title: str, icon: str | None = None) -> _GroupContext:
        """Create a group context for bracketed output.

        Items appear live as added. On exit, last item gets rounded corner.

        Example:
            with ui.group("Installing...") as g:
                g.success("Downloaded packages")
                g.info("Verified checksums")
        """
        self._check_bound()
        return _GroupContext(title, self, icon)

    def cancelable(self) -> _CancelableContext:
        """Create a cancelable operation wrapper.

        Shows "(esc to interrupt)" footer. On cancellation, prints "Interrupted".
        Returns a CancelScope with sleep() for immediate interrupt response.

        Example:
            async with ui.cancelable() as scope:
                await scope.sleep(1.0)  # Immediately interruptible
                with ui.group("Working") as g:
                    await scope.sleep(0.5)
                    await g.success("Done")
        """
        self._check_bound()
        return _CancelableContext(self)

    async def confirm(self, message: str) -> bool:
        """Blocking confirmation prompt.

        Shows message with [y/n] and waits for keypress.

        Example:
            if await ui.confirm("Delete these files?"):
                # user pressed y
            else:
                # user pressed n
        """
        self._check_bound()
        ctx = _ConfirmContext(message, self)
        return await ctx.wait()

    def collapsed(
        self,
        title: str,
        content: str,
        max_chars: int | None = 0,
        style: str = "dim",
    ) -> None:
        """Print content with configurable truncation.

        Args:
            title: Header text
            content: Body content
            max_chars: 0=title only, N=first N chars, None=full content
            style: Rich style for the content

        Example:
            ui.collapsed("Details", long_text)  # Just "▶ Details (42 lines)"
            ui.collapsed("Details", long_text, max_chars=100)  # Preview
            ui.collapsed("Details", long_text, max_chars=None)  # Full
        """
        content = content.strip()
        parts = []

        if max_chars is None:
            # Show everything
            parts.append(Text.assemble(("▶ ", style), (title, style)))
            for line in content.split("\n"):
                parts.append(Text(f"  {line}", style=style))
        elif max_chars > 0:
            # Show truncated preview
            parts.append(Text.assemble(("▶ ", style), (title, style)))
            if len(content) > max_chars:
                preview = content[:max_chars]
                remaining = len(content) - max_chars
                parts.append(Text(f"  {preview}...", style=style))
                parts.append(Text(f"  ({remaining:,} more chars)", style="dim"))
            else:
                for line in content.split("\n"):
                    parts.append(Text(f"  {line}", style=style))
        else:
            # max_chars=0, just show title + line count
            line_count = content.count("\n") + 1
            parts.append(
                Text.assemble(
                    ("▶ ", style),
                    (title, style),
                    (f" ({line_count} lines)", "dim"),
                )
            )

        self._out.print(Text("\n").join(parts))

    def thinking(self, content: str, max_chars: int | None = 0) -> None:
        """Print agent thinking/reasoning in collapsed form.

        Example:
            ui.thinking("I need to analyze this code...")
        """
        self.collapsed("Thinking...", content, max_chars=max_chars, style="dim italic")


# =============================================================================
# DEFAULT INSTANCE PATTERN
# =============================================================================
# Instead of a hard singleton, we use a default instance that can be replaced
# for testing. This provides the same ergonomics but allows test isolation.

_default_ui: _UI | None = None


def get_ui() -> _UI:
    """Get the default UI instance, creating it if needed."""
    global _default_ui
    if _default_ui is None:
        _default_ui = _UI()
    return _default_ui


def reset_ui() -> None:
    """Reset the default UI instance. For testing only."""
    global _default_ui
    if _default_ui is not None:
        _default_ui._reset()
    _default_ui = None


# Module-level convenience - same ergonomics as before
ui = get_ui()
