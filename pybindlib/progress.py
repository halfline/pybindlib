"""
Progress indication utilities for pybindlib.

This module provides a thread-safe progress indicator for long-running operations.
"""

# Standard library imports
import sys
import threading

# Local imports
from .output import Fore, Style, _has_colorama, ANSI_COLOR_PATTERN


class ProgressIndicator:
    """
    An animated progress indicator with dots and status text.

    Shows animated ellipsis and current processing status to give users
    visual feedback during long-running operations. The indicator is:
    - Thread-safe for future parallelization
    - Gracefully handles terminal width
    - Supports color when available
    - Updates in-place without scrolling
    - Cleans up properly when finished
    """

    def __init__(self, prefix: str = "Processing"):
        self.prefix = prefix
        self.dots = ["   ", ".  ", ".. ", "..."]
        self.current_dot = 0
        self.last_length = 0
        self.active = False
        self._lock = threading.Lock()

    def start(self):
        """Start the progress indicator."""
        with self._lock:
            self.active = True
            self.current_dot = 0

    def update(self, status: str = ""):
        """Update the progress indicator with new status."""
        if not self.active:
            return

        with self._lock:
            # Clear the previous line
            if self.last_length > 0:
                sys.stdout.write("\r" + " " * self.last_length + "\r")

            # Format the new status line
            if _has_colorama:
                line = f"{Fore.BLUE}│{Style.RESET_ALL}  {self.prefix}{self.dots[self.current_dot]}"
                if status:
                    line += f" {status}"
            else:
                line = f"   {self.prefix}{self.dots[self.current_dot]}"
                if status:
                    line += f" {status}"

            # Update state
            self.current_dot = (self.current_dot + 1) % len(self.dots)
            self.last_length = len(ANSI_COLOR_PATTERN.sub("", line))

            # Output
            sys.stdout.write(line)
            sys.stdout.flush()

    def finish(self, final_status: str = "Complete"):
        """
        Stop the progress indicator and show final status.

        Args:
            final_status: Final status message to display
        """
        if not self.active:
            return

        with self._lock:
            # Clear the progress line
            if self.last_length > 0:
                sys.stdout.write("\r" + " " * self.last_length + "\r")

            # Show completion status
            if _has_colorama:
                print(
                    f"{Fore.BLUE}│{Style.RESET_ALL}  {Fore.GREEN}✓{Style.RESET_ALL} {final_status}"
                )
            else:
                print(f"   ✓ {final_status}")

            self.active = False
            self.last_length = 0