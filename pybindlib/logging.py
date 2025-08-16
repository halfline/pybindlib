"""
Logging configuration for pybindlib.

This module provides a consistent logging setup with colored output and
appropriate formatting for different verbosity levels.
"""

# Standard library imports
import logging
import sys

# Local imports
from .output import Fore, Style, _has_colorama


class ColoredFormatter(logging.Formatter):
    """
    Custom formatter that adds colors to log levels.

    This formatter enhances log output by:
    - Adding color-coding to different log levels
    - Using Unicode symbols for better readability
    - Gracefully falling back when color isn't available
    - Maintaining consistent formatting across platforms
    """

    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def __init__(self, use_color: bool, *args, **kwargs):
        if not args and not kwargs:
            kwargs["fmt"] = "%(levelname_colored)s%(message)s"
        super().__init__(*args, **kwargs)
        self.use_color = use_color and _has_colorama

    def format(self, record):
        # Add colored level name
        level_color = (
            self.COLORS.get(record.levelname, "") if self.use_color else ""
        )
        record.levelname_colored = (
            f"{level_color}▸{Style.RESET_ALL} " if self.use_color else "▸ "
        )
        return super().format(record)


def setup_logging(
    verbose: bool = False, use_color: bool = True
) -> logging.Logger:
    """
    Configure logging based on verbosity level.

    This function sets up a consistent logging configuration that:
    - Uses appropriate log levels based on verbosity
    - Adds color-coding when available
    - Formats messages for readability
    - Handles both stdout and stderr appropriately
    - Cleans up any existing handlers

    Args:
        verbose: Enable verbose logging output
        use_color: Whether to use colored output

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("pybindlib")

    # Clear any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Set logging level
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    # Create console handler with custom formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Custom formatter with colors if available
    formatter = ColoredFormatter(
        use_color, "%(levelname_colored)s%(message)s", datefmt="%H:%M:%S"
    )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# Initialize the default project logger. Uses INFO level logging and enables
# color output on terminals that support it. Modules can create alternative
# logger instances via setup_logging() when different settings are needed.
#
# Usage:
#   1. from pybindlib import logger
#   2. from pybindlib.logging import setup_logging
#
# The default configuration outputs to stdout and falls back to plain text
# when color is not supported.
logger = setup_logging(verbose=False, use_color=True)