"""Rich renderables for NiceREPL (escape hatch for advanced users)."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.syntax import Syntax
from rich.text import Text

from nicerepl.styles import (
    DEFAULT_BORDER_COLOR,
    ICON_BULLET,
    STATUS_STYLES,
)


class Message:
    """A structured message with bullet and indented content.

    Example:
        ui.print(Message("Hello!", header="You", color="blue"))
    """

    def __init__(
        self,
        content: str,
        *,
        header: str | None = None,
        color: str = DEFAULT_BORDER_COLOR,
        icon: str | None = None,
    ) -> None:
        self.content = content
        self.header = header
        self.color = color
        self.icon = icon or ICON_BULLET

    def __rich__(self) -> Text:
        text = Text()
        text.append(f"{self.icon} ", style=self.color)
        if self.header:
            text.append(f"{self.header}\n", style=self.color)
            lines = self.content.split("\n")
            for i, line in enumerate(lines):
                text.append(f"  {line}")
                if i < len(lines) - 1:
                    text.append("\n")
        else:
            text.append(self.content)
        return text


class CodeBlock:
    """A syntax-highlighted code block.

    Example:
        ui.print(CodeBlock("print('hello')", language="python", title="example.py"))
    """

    def __init__(
        self,
        code: str,
        *,
        language: str = "text",
        title: str | None = None,
        line_numbers: bool = True,
    ) -> None:
        self.code = code
        self.language = language
        self.title = title
        self.line_numbers = line_numbers

    def __rich__(self) -> RenderableType:
        syntax = Syntax(
            self.code,
            self.language,
            line_numbers=self.line_numbers,
            word_wrap=True,
            background_color="default",
        )
        padded_syntax = Padding(syntax, (0, 0, 0, 2))

        if self.title:
            header = Text(f"  {self.title}", style="dim")
            return Group(header, padded_syntax)
        return padded_syntax


class Status:
    """A status badge with icon and message.

    Example:
        ui.print(Status("success", "Build completed"))
    """

    def __init__(self, status: str, message: str) -> None:
        if status not in STATUS_STYLES:
            raise ValueError(f"Unknown status: {status}. Valid: {list(STATUS_STYLES.keys())}")
        self.status = status
        self.message = message

    def __rich__(self) -> Text:
        color, icon = STATUS_STYLES[self.status]
        return Text.assemble((f"{icon} ", color), self.message)


class WelcomeBanner:
    """A customizable startup banner with two-column layout.

    Example:
        ui.print(WelcomeBanner(
            title="MyApp v1.0",
            greeting="Welcome!",
            ascii_art="...",
            left_info=["Built with NiceREPL"],
            right_sections=[("Tips", ["Type /help"])],
        ))
    """

    def __init__(
        self,
        *,
        title: str | None = None,
        greeting: str | None = None,
        ascii_art: str | None = None,
        left_info: list[str] | None = None,
        right_sections: list[tuple[str, list[str]]] | None = None,
        color: str = "cyan",
    ) -> None:
        self.title = title
        self.greeting = greeting
        self.ascii_art = ascii_art
        self.left_info = left_info or []
        self.right_sections = right_sections or []
        self.color = color

    def __rich__(self) -> RenderableType:
        from rich.columns import Columns

        left_parts = []

        if self.greeting:
            left_parts.append(Text(self.greeting, style="bold"))
            left_parts.append(Text(""))

        if self.ascii_art:
            art_text = Text(self.ascii_art.strip("\n"), style=self.color)
            left_parts.append(art_text)
            left_parts.append(Text(""))

        for info in self.left_info:
            left_parts.append(Text(info, style="dim"))

        left_column = Group(*left_parts) if left_parts else Text("")

        right_parts = []

        for section_title, items in self.right_sections:
            right_parts.append(Text(section_title, style=f"bold {self.color}"))
            for item in items:
                right_parts.append(Text(f"  {item}"))
            right_parts.append(Text(""))

        right_column = Group(*right_parts) if right_parts else Text("")

        title_line = Text(f"─ {self.title} ", style="dim") if self.title else None

        columns = Columns([left_column, right_column], padding=(0, 4), expand=True)

        if title_line:
            return Group(title_line, Text(""), columns)
        return columns
