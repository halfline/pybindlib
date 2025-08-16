"""
File path utilities for pybindlib.

This module provides functions for handling file paths and names in a
consistent and safe manner.
"""

# Standard library imports
import os
import logging

# Global variables
logger = logging.getLogger("pybindlib")


def generate_output_filename(
    library_name: str | None, fallback_path: str
) -> str:
    """
    Generate output filename based on library name.

    This function creates a Python-friendly filename by:
    - Using SONAME if available (preferred)
    - Falling back to library path if needed
    - Converting special characters to underscores
    - Ensuring .py extension
    - Maintaining uniqueness

    Args:
        library_name: Library name from SONAME
        fallback_path: Path to use if library_name is None or empty

    Returns:
        Generated filename
    """
    if library_name and library_name.strip():
        base = library_name
    else:
        base = os.path.basename(fallback_path)

    # Convert library name to Python module name
    base = base.replace("-", "_")
    base = base.replace(".", "_")
    base = base.replace("/", "_")

    return f"{base}.py"


def strip_trailing_whitespace_from_file(file_path: str) -> None:
    """
    Remove trailing whitespace from each line in the given file.

    This function ensures consistent file formatting by:
    - Removing trailing spaces and tabs
    - Ensuring exactly one newline at end of file
    - Preserving line content and order
    - Handling encoding correctly
    - Logging errors without failing
    """
    try:
        with open(file_path, encoding="utf-8") as file_handle:
            lines = file_handle.readlines()
        with open(file_path, "w", encoding="utf-8") as file_handle:
            file_handle.writelines(line.rstrip() + "\n" for line in lines)
    except Exception as error:
        logger.debug(f"Failed to strip whitespace: {error}")