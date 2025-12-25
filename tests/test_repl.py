"""Tests for REPL command registration and dispatch."""

from __future__ import annotations

from nicerepl._repl import _REPL, _Command


class TestCommandRegistration:
    """Tests for command registration."""

    def test_register_command_with_decorator(self, test_repl: _REPL) -> None:
        """Test registering a command with decorator."""

        @test_repl.command("/test")
        async def test_cmd(args: str) -> None:
            pass

        assert "/test" in test_repl._commands
        cmd = test_repl._commands["/test"]
        assert cmd.name == "/test"
        assert cmd.handler == test_cmd

    def test_register_command_without_slash(self, test_repl: _REPL) -> None:
        """Test command registration adds slash if missing."""

        @test_repl.command("help")
        async def help_cmd(args: str) -> None:
            pass

        assert "/help" in test_repl._commands

    def test_command_description_from_docstring(self, test_repl: _REPL) -> None:
        """Test command description extracted from docstring."""

        @test_repl.command("/doc")
        async def doc_cmd(args: str) -> None:
            """This is the help text."""
            pass

        cmd = test_repl._commands["/doc"]
        assert cmd.description == "This is the help text."

    def test_command_multiline_docstring(self, test_repl: _REPL) -> None:
        """Test only first line of docstring used."""

        @test_repl.command("/multi")
        async def multi_cmd(args: str) -> None:
            """First line.

            More details here.
            """
            pass

        cmd = test_repl._commands["/multi"]
        assert cmd.description == "First line."

    def test_command_no_docstring(self, test_repl: _REPL) -> None:
        """Test command without docstring has empty description."""

        @test_repl.command("/nodoc")
        async def nodoc_cmd(args: str) -> None:
            pass

        cmd = test_repl._commands["/nodoc"]
        assert cmd.description == ""

    def test_register_multiple_commands(self, test_repl: _REPL) -> None:
        """Test registering multiple commands."""

        @test_repl.command("/one")
        async def one(args: str) -> None:
            pass

        @test_repl.command("/two")
        async def two(args: str) -> None:
            pass

        @test_repl.command("/three")
        async def three(args: str) -> None:
            pass

        assert len(test_repl._commands) == 3
        assert "/one" in test_repl._commands
        assert "/two" in test_repl._commands
        assert "/three" in test_repl._commands

    def test_command_case_insensitive(self, test_repl: _REPL) -> None:
        """Test commands stored lowercase."""

        @test_repl.command("/MyCommand")
        async def my_cmd(args: str) -> None:
            pass

        assert "/mycommand" in test_repl._commands


class TestInputHandler:
    """Tests for input handler registration."""

    def test_register_input_handler(self, test_repl: _REPL) -> None:
        """Test registering input handler."""

        @test_repl.on_input
        async def handler(text: str) -> None:
            pass

        assert test_repl._input_handler == handler

    def test_replace_input_handler(self, test_repl: _REPL) -> None:
        """Test replacing input handler."""

        @test_repl.on_input
        async def first(text: str) -> None:
            pass

        @test_repl.on_input
        async def second(text: str) -> None:
            pass

        assert test_repl._input_handler == second


class TestStartHandler:
    """Tests for startup handler registration."""

    def test_register_start_handler(self, test_repl: _REPL) -> None:
        """Test registering start handler."""

        @test_repl.on_start
        async def startup() -> None:
            pass

        assert test_repl._start_handler == startup


class TestErrorHandler:
    """Tests for error handler registration."""

    def test_register_error_handler(self, test_repl: _REPL) -> None:
        """Test registering error handler."""

        @test_repl.on_error
        async def handle_error(error: Exception) -> None:
            pass

        assert test_repl._error_handler == handle_error

    def test_reset_clears_error_handler(self, test_repl: _REPL) -> None:
        """Test reset clears error handler."""

        @test_repl.on_error
        async def handle_error(error: Exception) -> None:
            pass

        test_repl._reset()
        assert test_repl._error_handler is None


class TestPrompt:
    """Tests for prompt property."""

    def test_default_prompt(self, test_repl: _REPL) -> None:
        """Test default prompt value."""
        assert test_repl.prompt == "> "

    def test_set_prompt(self, test_repl: _REPL) -> None:
        """Test setting prompt."""
        test_repl.prompt = ">>> "
        assert test_repl.prompt == ">>> "


class TestReset:
    """Tests for reset functionality."""

    def test_reset_clears_commands(self, test_repl: _REPL) -> None:
        """Test reset clears registered commands."""

        @test_repl.command("/test")
        async def test_cmd(args: str) -> None:
            pass

        test_repl._reset()
        assert len(test_repl._commands) == 0

    def test_reset_clears_handlers(self, test_repl: _REPL) -> None:
        """Test reset clears handlers."""

        @test_repl.on_input
        async def handler(text: str) -> None:
            pass

        @test_repl.on_start
        async def startup() -> None:
            pass

        test_repl._reset()
        assert test_repl._input_handler is None
        assert test_repl._start_handler is None

    def test_reset_restores_default_prompt(self, test_repl: _REPL) -> None:
        """Test reset restores default prompt."""
        test_repl.prompt = "custom> "
        test_repl._reset()
        assert test_repl.prompt == "> "


class TestCommand:
    """Tests for _Command dataclass."""

    def test_command_creation(self) -> None:
        """Test creating a Command."""

        async def handler(args: str) -> None:
            pass

        cmd = _Command(
            name="/test",
            handler=handler,
            description="Test command",
        )
        assert cmd.name == "/test"
        assert cmd.handler == handler
        assert cmd.description == "Test command"
