"""REPL singleton for NiceREPL."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

# =============================================================================
# DEBUG MODE
# =============================================================================
# Set NICEREPL_DEBUG=1 to enable debug logging

_DEBUG = os.environ.get("NICEREPL_DEBUG", "").lower() in ("1", "true", "yes")

# Configure logging
_logger = logging.getLogger("nicerepl")
if _DEBUG:
    logging.basicConfig(
        level=logging.DEBUG,
        format="[nicerepl] %(levelname)s: %(message)s",
    )
    _logger.setLevel(logging.DEBUG)
else:
    _logger.addHandler(logging.NullHandler())

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.output.flush_stdout import flush_stdout
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.styles import Style

from nicerepl._output import OutputManager
from nicerepl._ui import ui


class _BoundedHistory(InMemoryHistory):
    """InMemoryHistory with maximum size to prevent unbounded memory growth.

    Keeps the most recent entries, dropping oldest when limit is reached.
    """

    def __init__(self, max_size: int = 1000) -> None:
        super().__init__()
        self._max_size = max_size

    def store_string(self, string: str) -> None:
        super().store_string(string)
        # Trim oldest entries if over limit
        while len(self._storage) > self._max_size:
            self._storage.pop(0)


@dataclass
class _Command:
    """A registered command."""

    name: str
    handler: Callable[[str], Awaitable[None]]
    description: str


class _SyncVt100Output(Vt100_Output):
    """VT100 output with DEC mode 2026 (synchronized) for flicker-free rendering."""

    def flush(self) -> None:
        if not self._buffer:
            return
        data = "".join(self._buffer)
        self._buffer = []
        flush_stdout(self.stdout, "\x1b[?2026h" + data + "\x1b[?2026l")


class _CommandCompleter(Completer):
    """Completer for slash commands."""

    def __init__(self, repl: _REPL) -> None:
        self._repl = repl

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()

        if not text.startswith("/"):
            return

        prefix = text[1:].lower()

        for cmd in self._repl._commands.values():
            cmd_name = cmd.name[1:]  # Remove leading /
            if cmd_name.lower().startswith(prefix):
                yield Completion(
                    text=cmd_name,
                    start_position=-len(prefix),
                    display=cmd.name,
                    display_meta=cmd.description,
                )


class _REPL:
    """REPL singleton."""

    def __init__(self) -> None:
        self._prompt_str = "> "
        self._commands: dict[str, _Command] = {}
        self._input_handler: Callable[[str], Awaitable[None]] | None = None
        self._start_handler: Callable[[], Awaitable[None]] | None = None
        self._error_handler: Callable[[Exception], Awaitable[None]] | None = None
        self._running = False
        self._handling = False
        self._cancelling = False  # True while waiting for cancellation to complete
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._current_task: asyncio.Task | None = None
        self._output: OutputManager | None = None
        self._app: Application | None = None

    @property
    def prompt(self) -> str:
        """Get the prompt string."""
        return self._prompt_str

    @prompt.setter
    def prompt(self, value: str) -> None:
        """Set the prompt string."""
        self._prompt_str = value

    @property
    def _out(self) -> OutputManager:
        """Get output manager, raising if not initialized."""
        if self._output is None:
            raise RuntimeError("REPL not running")
        return self._output

    def _reset(self) -> None:
        """Reset REPL state for testing. Clears handlers and runtime state."""
        self._prompt_str = "> "
        self._commands.clear()
        self._input_handler = None
        self._start_handler = None
        self._error_handler = None
        self._running = False
        self._handling = False
        self._cancelling = False
        self._input_queue = asyncio.Queue()
        self._current_task = None
        self._output = None
        self._app = None

    def on_input(self, func: Callable[[str], Awaitable[None]]) -> Callable[[str], Awaitable[None]]:
        """Decorator to register the main input handler.

        Example:
            @repl.on_input
            async def main(text: str):
                ui.echo(text)
                ui.print("You said: " + text)
        """
        self._input_handler = func
        return func

    def on_start(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """Decorator to register the startup handler.

        Example:
            @repl.on_start
            async def startup():
                ui.print(WelcomeBanner(...))
        """
        self._start_handler = func
        return func

    def on_error(
        self, func: Callable[[Exception], Awaitable[None]]
    ) -> Callable[[Exception], Awaitable[None]]:
        """Decorator to register a global error handler.

        Called when an unhandled exception occurs in a command or input handler.
        If no error handler is registered, errors are displayed with traceback.

        Example:
            @repl.on_error
            async def handle_error(error: Exception):
                ui.error(f"Something went wrong: {error}")
                # Optionally log, send telemetry, etc.
        """
        self._error_handler = func
        return func

    def command(
        self, name: str
    ) -> Callable[[Callable[[str], Awaitable[None]]], Callable[[str], Awaitable[None]]]:
        """Decorator to register a slash command.

        Example:
            @repl.command("/help")
            async def help_cmd(args: str):
                ui.print("Available commands: /help, /quit")
        """

        def decorator(func: Callable[[str], Awaitable[None]]) -> Callable[[str], Awaitable[None]]:
            cmd_name = name if name.startswith("/") else f"/{name}"
            description = func.__doc__ or ""
            description = description.strip().split("\n")[0]

            self._commands[cmd_name.lower()] = _Command(
                name=cmd_name,
                handler=func,
                description=description,
            )
            return func

        return decorator

    def exit(self) -> None:
        """Exit the REPL."""
        self._running = False
        if self._app:
            self._app.exit()

    def run(self) -> None:
        """Run the REPL (sync wrapper around async)."""
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """Run the REPL."""
        width = shutil.get_terminal_size().columns
        self._output = OutputManager(block_spacing=1, width=width)
        self._running = True

        # Bind UI to our output manager
        ui._bind(self._output)

        # Call startup handler
        if self._start_handler:
            await self._start_handler()

        # Create input buffer
        history = _BoundedHistory(max_size=1000)
        input_buffer = Buffer(
            history=history,
            completer=_CommandCompleter(self),
            complete_while_typing=True,
            multiline=True,
        )

        # Key bindings
        kb = KeyBindings()

        @kb.add("escape", "enter")
        def on_escape_enter(event: KeyPressEvent) -> None:
            """Insert newline on Escape+Enter."""
            event.current_buffer.insert_text("\n")

        @kb.add("c-j")
        def on_ctrl_j(event: KeyPressEvent) -> None:
            """Insert newline on Ctrl+J (for Shift+Enter via terminal config)."""
            event.current_buffer.insert_text("\n")

        @kb.add("enter")
        def on_enter(event: KeyPressEvent) -> None:
            text = input_buffer.text.strip()
            if not text:
                return

            # Queue input if cancelling (will be processed after cancel completes)
            if self._cancelling:
                input_buffer.append_to_history()
                input_buffer.reset()
                self._input_queue.put_nowait(text)
                return

            if self._handling:
                return

            input_buffer.append_to_history()
            input_buffer.reset()

            self._handling = True

            async def run_handler() -> None:
                try:
                    await self._handle_input(text)
                except Exception as e:
                    # Surface errors (CancelledError already handled by cancelable())
                    if not isinstance(e, asyncio.CancelledError):
                        ui.error(f"Error: {e}")
                finally:
                    self._handling = False
                    self._cancelling = False
                    self._current_task = None
                    # Process any queued input
                    await self._process_queued_input()

            self._current_task = asyncio.create_task(run_handler())

        @kb.add("escape", eager=True)
        def on_escape(event: KeyPressEvent) -> None:
            """Cancel current operation."""
            if self._handling and self._current_task and not self._cancelling:
                ui.request_cancel()  # UI decides what to do based on mode
                self._cancelling = True  # Wait for cancellation to complete

        @kb.add("c-c", eager=True)
        def on_ctrl_c(event: KeyPressEvent) -> None:
            if self._handling and not self._cancelling:
                ui.request_cancel()  # UI decides what to do based on mode
                self._cancelling = True  # Wait for cancellation to complete
            elif not self._handling:
                input_buffer.text = ""

        @kb.add("c-d")
        def on_ctrl_d(event: KeyPressEvent) -> None:
            self.exit()

        @kb.add("y", eager=True)
        @kb.add("Y", eager=True)
        def on_y(event: KeyPressEvent) -> None:
            if not ui.respond_confirm(True):
                event.current_buffer.insert_text(event.data)

        @kb.add("n", eager=True)
        @kb.add("N", eager=True)
        def on_n(event: KeyPressEvent) -> None:
            if not ui.respond_confirm(False):
                event.current_buffer.insert_text(event.data)

        @kb.add("up")
        def on_up(event: KeyPressEvent) -> None:
            event.current_buffer.auto_up()

        @kb.add("down")
        def on_down(event: KeyPressEvent) -> None:
            event.current_buffer.auto_down()

        # Layout
        def get_separator():
            return [("class:separator", "─" * width)]

        def get_status():
            return [("class:status", "  ↵ send")]

        def get_live_text():
            content = self._out.get_live_content()
            return ANSI(content) if content else ""

        layout = Layout(
            HSplit(
                [
                    ConditionalContainer(
                        Window(
                            content=FormattedTextControl(get_live_text),
                            height=self._out.get_live_height,
                        ),
                        filter=Condition(self._out.has_live_content),
                    ),
                    Window(content=FormattedTextControl(get_separator), height=1),
                    VSplit(
                        [
                            Window(
                                content=FormattedTextControl(
                                    lambda: [("class:prompt", self._prompt_str)]
                                ),
                                width=len(self._prompt_str),
                                dont_extend_width=True,
                            ),
                            Window(content=BufferControl(buffer=input_buffer)),
                        ],
                        height=lambda: max(1, input_buffer.document.line_count),
                    ),
                    Window(content=FormattedTextControl(get_separator), height=1),
                    Window(content=FormattedTextControl(get_status), height=1),
                ]
            )
        )

        # Create application
        output = _SyncVt100Output.from_pty(sys.stdout)

        style = Style.from_dict(
            {
                "prompt": "ansicyan bold",
                "separator": "ansibrightblack",
                "status": "ansibrightblack",
            }
        )

        self._app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            min_redraw_interval=0.016,
            output=output,
            style=style,
        )

        self._out.set_output(output)
        self._out.set_invalidate_callback(self._app.invalidate)

        await self._app.run_async()

    async def _handle_input(self, text: str) -> None:
        """Handle user input."""
        _logger.debug(f"Handling input: {text!r}")
        try:
            # Check if it's a command
            if text.startswith("/"):
                parts = text.split(maxsplit=1)
                cmd_name = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                cmd = self._commands.get(cmd_name)
                if cmd:
                    _logger.debug(f"Executing command: {cmd_name}")
                    self._current_task = asyncio.current_task()
                    await cmd.handler(args)
                else:
                    ui.error(f"Unknown command: {cmd_name}")
                    ui.print("[dim]Type /help for available commands.[/dim]")
            elif self._input_handler:
                _logger.debug("Executing input handler")
                self._current_task = asyncio.current_task()
                await self._input_handler(text)
            else:
                ui.print("[dim]No handler registered.[/dim]")
        except asyncio.CancelledError:
            _logger.debug("Handler cancelled")
            pass  # Handled by ui.cancelable() context
        except Exception as e:
            _logger.exception("Error in handler")
            # Use custom error handler if registered
            if self._error_handler:
                try:
                    await self._error_handler(e)
                except Exception:
                    # Error handler itself failed, fall back to default
                    _logger.exception("Error handler failed")
                    ui.error("Error:")
                    ui.print(f"[red]{traceback.format_exc()}[/red]")
            else:
                # Default error display
                ui.error("Error:")
                ui.print(f"[red]{traceback.format_exc()}[/red]")

    async def _process_queued_input(self) -> None:
        """Process any queued input that was submitted during cancellation."""
        while not self._input_queue.empty():
            try:
                text = self._input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            self._handling = True
            try:
                await self._handle_input(text)
            except Exception as e:
                if not isinstance(e, asyncio.CancelledError):
                    ui.error(f"Error: {e}")
            finally:
                self._handling = False
                self._cancelling = False


# =============================================================================
# DEFAULT INSTANCE PATTERN
# =============================================================================
# Instead of a hard singleton, we use a default instance that can be replaced
# for testing. This provides the same ergonomics but allows test isolation.

_default_repl: _REPL | None = None


def get_repl() -> _REPL:
    """Get the default REPL instance, creating it if needed."""
    global _default_repl
    if _default_repl is None:
        _default_repl = _REPL()
    return _default_repl


def reset_repl() -> None:
    """Reset the default REPL instance. For testing only."""
    global _default_repl
    if _default_repl is not None:
        _default_repl._reset()
    _default_repl = None


# Module-level convenience - same ergonomics as before
repl = get_repl()
