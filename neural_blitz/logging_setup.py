"""Logging configuration with Rich and plain fallbacks."""

from __future__ import annotations

import logging
import sys

from neural_blitz.errors import ConfigError

try:
    from rich.console import Console
    from rich.logging import RichHandler

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None  # type: ignore[misc, assignment]
    RichHandler = None  # type: ignore[misc, assignment]

logger = logging.getLogger("neural_blitz")
console = Console(stderr=False) if RICH_AVAILABLE else None
error_console = Console(stderr=True) if RICH_AVAILABLE else None


def configure_logging(level: str, use_rich: bool) -> None:
    resolved = getattr(logging, level.upper(), None)
    if not isinstance(resolved, int):
        raise ConfigError(f"Invalid log level: {level}")
    handlers: list[logging.Handler]
    if use_rich and RICH_AVAILABLE and error_console is not None and RichHandler is not None:
        handlers = [RichHandler(console=error_console, markup=False, rich_tracebacks=True, show_path=False)]
        fmt = "%(message)s"
    else:
        handlers = [logging.StreamHandler(sys.stderr)]
        fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    logging.basicConfig(
        level=resolved,
        format=fmt,
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def emit_error(message: str, use_rich: bool = True) -> None:
    if use_rich and RICH_AVAILABLE and error_console is not None:
        from rich.panel import Panel

        error_console.print(Panel.fit(message, title="Error", style="bold red"))
    else:
        print(f"Error: {message}", file=sys.stderr)
