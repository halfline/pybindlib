"""
Output formatting utilities for pybindlib.

This module provides functions for formatting console output with colors and
consistent styling. It gracefully degrades when color support is not available.
"""

# Standard library imports
import re
import sys

# Third-party imports
try:
    from colorama import Back, Fore, Style
    from colorama import init as init_colorama

    init_colorama()
    _has_colorama = True
except ImportError:
    # Fallback if colorama isn't available
    class _ColorFallback:
        def __getattr__(self, name):
            return ""

    Fore = Back = Style = _ColorFallback()
    _has_colorama = False

# Pattern for removing ANSI color codes when calculating string length
ANSI_COLOR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI color codes from text."""
    return ANSI_COLOR_PATTERN.sub("", text)


def print_banner(text: str, use_color: bool = True):
    """
    Print a banner with a cyan box around it.

    Args:
        text: The text to display in the banner
        use_color: Whether to use color output
    """
    if use_color and _has_colorama:
        # Create colored text first to ensure proper width calculation
        colored_text = f"{Fore.GREEN}{text}{Style.RESET_ALL}"

        # Get text length without ANSI codes for box sizing
        text_len = len(_strip_ansi(text))

        # Box drawing characters
        top_left = "╭"
        top_right = "╮"
        bottom_left = "╰"
        bottom_right = "╯"
        horizontal = "─"
        vertical = "│"

        # Draw box with proper spacing
        print(f"\n{Fore.CYAN}{top_left}{horizontal * (text_len + 2)}{top_right}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{vertical}{Style.RESET_ALL} {colored_text} {Fore.CYAN}{vertical}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{bottom_left}{horizontal * (text_len + 2)}{bottom_right}{Style.RESET_ALL}")
    else:
        # Simple ASCII box for non-color output
        text_len = len(text)
        print(f"\n+{'-' * (text_len + 2)}+")
        print(f"| {text} |")
        print(f"+{'-' * (text_len + 2)}+")


def print_section_header(title: str, use_color: bool = True):
    """Print a formatted section header."""
    if use_color and _has_colorama:
        print(f"{Fore.BLUE}{Style.BRIGHT}┌─ {title}{Style.RESET_ALL}")
    else:
        print(f"── {title}")


def print_file_info(
    label: str, path: str, exists: bool = True, use_color: bool = True
):
    """Print formatted file information."""
    if use_color and _has_colorama:
        status = (
            f"{Fore.GREEN}✓{Style.RESET_ALL}"
            if exists
            else f"{Fore.RED}✗{Style.RESET_ALL}"
        )
        print(
            f"│  {status} {Fore.WHITE}{Style.BRIGHT}{label}:{Style.RESET_ALL} {path}"
        )
    else:
        status = "✓" if exists else "✗"
        print(f"   {status} {label}: {path}")


def print_success(message: str, use_color: bool = True):
    """Print a success message with formatting."""
    if use_color and _has_colorama:
        print(f"\n{Fore.GREEN}{Style.BRIGHT}🎉 {message}{Style.RESET_ALL}")
    else:
        print(f"\n✓ {message}")


def print_stats(
    structures_count: int, typedefs_count: int, use_color: bool = True
):
    """Print statistics with nice formatting."""
    if use_color and _has_colorama:
        print(
            f"{Fore.BLUE}│  {Fore.WHITE}{Style.BRIGHT}Structures:{Style.RESET_ALL} {Fore.CYAN}{structures_count}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.BLUE}│  {Fore.WHITE}{Style.BRIGHT}Typedefs:{Style.RESET_ALL} {Fore.CYAN}{typedefs_count}{Style.RESET_ALL}"
        )
    else:
        print(f"   Structures: {structures_count}")
        print(f"   Typedefs: {typedefs_count}")
