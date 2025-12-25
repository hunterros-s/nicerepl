# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2024

### Added
- Initial public release
- Claude Code-style REPL with prompt_toolkit and Rich
- Async context managers: `status`, `progress`, `stream`, `group`, `cancelable`
- Cooperative cancellation with `CancelScope`
- Slash command registration with `@repl.command()`
- Event hooks: `@repl.on_start`, `@repl.on_input`, `@repl.on_error`
- Rich-renderable components: `Message`, `CodeBlock`, `Status`, `WelcomeBanner`
- Full type hints with `py.typed` marker
