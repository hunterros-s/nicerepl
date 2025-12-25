"""Tests for Rich-renderable components."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from nicerepl._components import CodeBlock, Message, Status, WelcomeBanner


def render_to_string(renderable, width: int = 80) -> str:
    """Helper to render a Rich object to string."""
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=True, width=width)
    console.print(renderable, end="")
    return buffer.getvalue()


class TestMessage:
    """Tests for Message component."""

    def test_simple_message(self) -> None:
        """Test message without header."""
        msg = Message("Hello world")
        output = render_to_string(msg)
        assert "Hello world" in output

    def test_message_with_header(self) -> None:
        """Test message with header."""
        msg = Message("Content here", header="Title")
        output = render_to_string(msg)
        assert "Title" in output
        assert "Content here" in output

    def test_message_custom_icon(self) -> None:
        """Test message with custom icon."""
        msg = Message("Test", icon="*")
        output = render_to_string(msg)
        assert "*" in output

    def test_multiline_content(self) -> None:
        """Test message with multiline content."""
        msg = Message("Line 1\nLine 2\nLine 3", header="Multi")
        output = render_to_string(msg)
        assert "Line 1" in output
        assert "Line 2" in output
        assert "Line 3" in output


class TestCodeBlock:
    """Tests for CodeBlock component."""

    def test_simple_code(self) -> None:
        """Test basic code block."""
        code = CodeBlock("print('hello')", language="python")
        output = render_to_string(code)
        assert "print" in output
        assert "hello" in output

    def test_code_with_title(self) -> None:
        """Test code block with title."""
        code = CodeBlock("x = 1", language="python", title="example.py")
        output = render_to_string(code)
        assert "example.py" in output

    def test_code_no_line_numbers(self) -> None:
        """Test code block without line numbers."""
        code = CodeBlock("x = 1", language="python", line_numbers=False)
        output = render_to_string(code)
        # Just verify it renders without error
        assert "x" in output and "1" in output


class TestStatus:
    """Tests for Status component."""

    def test_success_status(self) -> None:
        """Test success status."""
        status = Status("success", "Build completed")
        output = render_to_string(status)
        assert "Build completed" in output

    def test_error_status(self) -> None:
        """Test error status."""
        status = Status("error", "Test failed")
        output = render_to_string(status)
        assert "Test failed" in output

    def test_warning_status(self) -> None:
        """Test warning status."""
        status = Status("warning", "Deprecated API")
        output = render_to_string(status)
        assert "Deprecated API" in output

    def test_info_status(self) -> None:
        """Test info status."""
        status = Status("info", "Version 1.0")
        output = render_to_string(status)
        assert "Version 1.0" in output

    def test_invalid_status(self) -> None:
        """Test invalid status raises error."""
        with pytest.raises(ValueError, match="Unknown status"):
            Status("invalid", "message")


class TestWelcomeBanner:
    """Tests for WelcomeBanner component."""

    def test_minimal_banner(self) -> None:
        """Test banner with minimal options."""
        banner = WelcomeBanner()
        output = render_to_string(banner)
        # Should render without error
        assert output is not None

    def test_banner_with_title(self) -> None:
        """Test banner with title."""
        banner = WelcomeBanner(title="MyApp v1.0")
        output = render_to_string(banner)
        assert "MyApp v1.0" in output

    def test_banner_with_greeting(self) -> None:
        """Test banner with greeting."""
        banner = WelcomeBanner(greeting="Welcome!")
        output = render_to_string(banner)
        assert "Welcome!" in output

    def test_banner_with_ascii_art(self) -> None:
        """Test banner with ASCII art."""
        banner = WelcomeBanner(ascii_art="  *  \n *** \n*****")
        output = render_to_string(banner)
        assert "***" in output

    def test_banner_with_left_info(self) -> None:
        """Test banner with left info."""
        banner = WelcomeBanner(left_info=["Line 1", "Line 2"])
        output = render_to_string(banner)
        assert "Line 1" in output
        assert "Line 2" in output

    def test_banner_with_sections(self) -> None:
        """Test banner with right sections."""
        banner = WelcomeBanner(
            right_sections=[
                ("Commands", ["/help", "/quit"]),
                ("Tips", ["Press ESC to cancel"]),
            ]
        )
        output = render_to_string(banner)
        assert "Commands" in output
        assert "/help" in output
        assert "Tips" in output

    def test_full_banner(self) -> None:
        """Test fully configured banner."""
        banner = WelcomeBanner(
            title="TestApp",
            greeting="Hello!",
            ascii_art="[*]",
            left_info=["Built with Python"],
            right_sections=[("Help", ["/help"])],
            color="blue",
        )
        output = render_to_string(banner)
        assert "TestApp" in output
        assert "Hello!" in output
        assert "/help" in output
