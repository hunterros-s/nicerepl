#!/usr/bin/env python3
"""NiceREPL Demo - run with: python demo.py"""

import asyncio

from nicerepl import WelcomeBanner, repl, ui

LOGO = r"""
  · ˚ ✦  ╔══════════════╗  ✦ ˚ ·
         ║  > nice_     ║
    ·  · ║  > repl_     ║ ·  ·
  ˚   ✦  ╚══════════════╝  ✦   ˚
"""


@repl.on_start
async def startup():
    """Show welcome banner."""
    banner = WelcomeBanner(
        title="NiceREPL v0.3.0",
        ascii_art=LOGO,
        left_info=[
            "Terminal UI framework",
            "github.com/hunterros-s/nicerepl",
        ],
        right_sections=[
            ("Try these", ["/build  - grouped tasks", "/progress  - progress bar", "/code  - syntax highlighting"]),
            ("Keys", ["ESC  - cancel operation", "↑/↓  - history"]),
        ],
        color="bright_cyan",
    )
    ui.print(banner)


@repl.command("/help")
async def help_cmd(args: str):
    """Show commands."""
    ui.print("""[bold]Commands[/bold]
  /spinner   - Spinner demo
  /progress  - Progress bar demo
  /build     - Multi-step workflow (try ESC!)
  /code      - Code block demo
  /stream    - Streaming output demo
  /confirm   - Confirmation prompt
  /quit      - Exit""")


@repl.command("/spinner")
async def spinner_cmd(args: str):
    """Spinner demo."""
    async with ui.cancelable():
        with ui.status("Analyzing...") as s:
            await asyncio.sleep(1)
            s.update("Processing...")
            await asyncio.sleep(1)
            s.update("Finishing up...")
            await asyncio.sleep(0.5)
        ui.success("Done!")


@repl.command("/progress")
async def progress_cmd(args: str):
    """Progress bar demo."""
    with ui.progress("Downloading", total=100, show_time=True) as p:
        for _ in range(100):
            await asyncio.sleep(0.02)
            p.advance(1)
    ui.success("Download complete!")


@repl.command("/build")
async def build_cmd(args: str):
    """Multi-step build workflow with cancellation support."""
    async with ui.cancelable() as scope:
        ui.info("Starting build...")

        try:
            with ui.group("Installing dependencies") as g:
                for pkg in ["numpy", "pandas", "rich"]:
                    with g.task(f"Installing {pkg}"):
                        await scope.sleep(0.4)

            with ui.group("Running checks") as g:
                with g.task("Linting"):
                    await scope.sleep(0.5)
                with g.task("Type checking"):
                    await scope.sleep(0.5)
                with g.task("Running tests"):
                    await scope.sleep(0.8)
                await g.info("All checks passed")

            with ui.group("Building") as g:
                with g.task("Compiling"):
                    await scope.sleep(0.6)
                with g.task("Bundling"):
                    await scope.sleep(0.4)
                await g.info("Output: dist/app.js (48kb)")

            ui.success("Build complete!")

        except asyncio.CancelledError:
            ui.warning("Build cancelled")
            raise


@repl.command("/code")
async def code_cmd(args: str):
    """Code block demo."""
    code = '''def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"

print(greet("World"))'''
    ui.code(code, language="python", title="example.py")


@repl.command("/stream")
async def stream_cmd(args: str):
    """Streaming output demo."""
    text = "This text streams in character by character, simulating an LLM response. "
    with ui.stream() as s:
        for char in text:
            s.write(char)
            await asyncio.sleep(0.02)
    ui.print("")


@repl.command("/confirm")
async def confirm_cmd(args: str):
    """Confirmation prompt demo."""
    if await ui.confirm("Do you want to proceed?"):
        ui.success("Confirmed!")
    else:
        ui.info("Cancelled")


@repl.command("/quit")
async def quit_cmd(args: str):
    """Exit."""
    repl.exit()


@repl.on_input
async def handle(text: str):
    """Echo input back."""
    ui.echo(text)
    with ui.status("Thinking..."):
        await asyncio.sleep(1)
    ui.print(f"You said: [italic]{text}[/italic]")


if __name__ == "__main__":
    repl.run()
