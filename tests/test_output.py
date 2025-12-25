"""Tests for OutputManager."""

from __future__ import annotations

from rich.text import Text

from nicerepl._output import OutputManager


class TestOutputManager:
    """Test OutputManager formatting and live content."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        om = OutputManager()
        assert om.block_spacing == 1
        assert om._width == 80
        assert om._live_content == ""
        assert om._live_footer == ""

    def test_init_custom(self) -> None:
        """Test custom initialization."""
        om = OutputManager(block_spacing=2, width=120)
        assert om.block_spacing == 2
        assert om._width == 120

    def test_set_width(self) -> None:
        """Test width setter."""
        om = OutputManager()
        om.set_width(100)
        assert om._width == 100

    def test_format_string(self) -> None:
        """Test formatting a plain string."""
        om = OutputManager(block_spacing=1, width=80)
        result = om._format("Hello")
        # Should end with block_spacing newlines
        assert result.endswith("\n")
        assert "Hello" in result

    def test_format_rich_text(self) -> None:
        """Test formatting Rich Text object."""
        om = OutputManager(block_spacing=1, width=80)
        text = Text("Hello", style="bold")
        result = om._format(text)
        assert "Hello" in result

    def test_set_live_content(self) -> None:
        """Test setting live content."""
        om = OutputManager()
        invalidated = []
        om.set_invalidate_callback(lambda: invalidated.append(True))

        om.set_live("Loading...")
        assert om._live_content != ""
        assert len(invalidated) == 1

    def test_clear_live_content(self) -> None:
        """Test clearing live content."""
        om = OutputManager()
        om.set_live("Loading...")
        om.clear_live()
        assert om._live_content == ""

    def test_set_live_footer(self) -> None:
        """Test setting live footer."""
        om = OutputManager()
        om.set_live_footer("(esc to cancel)")
        assert om._live_footer != ""

    def test_clear_live_footer(self) -> None:
        """Test clearing live footer."""
        om = OutputManager()
        om.set_live_footer("(esc to cancel)")
        om.clear_live_footer()
        assert om._live_footer == ""

    def test_clear_all_live(self) -> None:
        """Test clearing all live content."""
        om = OutputManager()
        om.set_live("Content")
        om.set_live_footer("Footer")
        om.clear_all_live()
        assert om._live_content == ""
        assert om._live_footer == ""

    def test_get_live_content_combined(self) -> None:
        """Test getting combined live content."""
        om = OutputManager()
        om.set_live("Main content")
        om.set_live_footer("Footer")
        combined = om.get_live_content()
        assert "Main content" in combined
        assert "Footer" in combined

    def test_get_live_content_empty(self) -> None:
        """Test getting live content when empty."""
        om = OutputManager()
        assert om.get_live_content() == ""

    def test_has_live_content(self) -> None:
        """Test live content detection."""
        om = OutputManager()
        assert not om.has_live_content()

        om.set_live("Loading...")
        assert om.has_live_content()

        om.clear_live()
        assert not om.has_live_content()

        om.set_live_footer("Footer")
        assert om.has_live_content()

    def test_get_live_height(self) -> None:
        """Test live content height calculation."""
        om = OutputManager()
        assert om.get_live_height() == 0

        om.set_live("Line 1\nLine 2\nLine 3")
        height = om.get_live_height()
        assert height >= 3

    def test_invalidate_callback(self) -> None:
        """Test invalidate callback is called on changes."""
        om = OutputManager()
        calls = []
        om.set_invalidate_callback(lambda: calls.append(1))

        om.set_live("test")
        assert len(calls) == 1

        om.clear_live()
        assert len(calls) == 2

        om.set_live_footer("footer")
        assert len(calls) == 3

        om.clear_live_footer()
        assert len(calls) == 4

    def test_invalidate_no_callback(self) -> None:
        """Test no error when invalidate called without callback."""
        om = OutputManager()
        om.set_live("test")  # Should not raise
        om.clear_live()
