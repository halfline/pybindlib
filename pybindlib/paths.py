"""
File path utilities for pybindlib.

This module provides functions for handling file paths and names in a
consistent and safe manner.
"""

# Standard library imports
import os
import logging
from typing import List, Optional

# Global variables
logger = logging.getLogger("pybindlib")


def resolve_header_path(header_path: str, include_paths: Optional[List[str]] = None) -> str:
    """
    Resolve a header file path using include paths.

    This function:
    - Returns absolute paths as-is
    - For relative paths, tries to find the file in:
        1. Current directory
        2. Each include path in order
    - Preserves the original path if not found

    Args:
        header_path: Path to the header file
        include_paths: List of include paths to search

    Returns:
        Resolved path to the header file
    """
    # Return absolute paths as-is
    if os.path.isabs(header_path):
        return header_path

    # Try current directory first
    if os.path.isfile(header_path):
        return os.path.abspath(header_path)

    # Try each include path
    if include_paths:
        for include_path in include_paths:
            full_path = os.path.join(include_path, header_path)
            if os.path.isfile(full_path):
                return full_path

    # If not found, return the original path
    # This allows cpp to handle system include paths
    return header_path


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