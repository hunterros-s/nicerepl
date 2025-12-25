"""NiceREPL - Streamlit for the Terminal.

A simple, powerful way to build interactive terminal applications.

Example:
    from nicerepl import repl, ui

    @repl.on_input
    async def main(text: str):
        ui.echo(text)
        with ui.status("Thinking..."):
            await asyncio.sleep(1)
        ui.success("Done!")

    @repl.command("/help")
    async def help_cmd(args: str):
        ui.print("Commands: /help, /quit")

    @repl.command("/quit")
    async def quit_cmd(args: str):
        repl.exit()

    repl.run()
"""

from importlib.metadata import version as _get_version

# Optional escape hatch for advanced users
from nicerepl._components import CodeBlock, Message, Status, WelcomeBanner

# Exceptions
from nicerepl._exceptions import NiceREPLError, NotBoundError, StateError
from nicerepl._repl import repl
from nicerepl._ui import check_cancelled, ui

try:
    __version__ = _get_version("nicerepl")
except Exception:
    __version__ = "0.0.0"  # Fallback for editable installs without metadata

__all__ = [
    # Core API
    "repl",
    "ui",
    "check_cancelled",
    # Components (escape hatch)
    "Message",
    "CodeBlock",
    "Status",
    "WelcomeBanner",
    # Exceptions
    "NiceREPLError",
    "StateError",
    "NotBoundError",
]
