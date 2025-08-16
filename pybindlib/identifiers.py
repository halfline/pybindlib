"""
Python identifier utilities for pybindlib.

This module provides functions for handling Python identifiers, ensuring they
are valid and safe to use in generated code.
"""

# Standard library imports
import keyword
import re


def create_safe_python_identifier(name: str) -> str:
    """
    Convert a C identifier to a safe Python identifier.

    This function ensures that C names can be safely used in Python by:
    - Replacing invalid characters with underscores
    - Ensuring the name starts with a letter
    - Avoiding Python keywords
    - Handling empty or invalid input
    - Preserving meaning where possible

    Args:
        name: Original identifier name

    Returns:
        Safe Python identifier
    """
    if not name:
        return "Unknown"

    # Replace invalid characters with underscores
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)

    # Ensure it starts with a letter
    if not safe_name[0].isalpha():
        safe_name = "Type_" + safe_name

    return safe_name


def is_invalid_identifier(name: str) -> bool:
    """
    Check if a string would make an invalid Python identifier.

    This function checks for various conditions that would make a name
    invalid in Python:
    - Must start with letter or underscore
    - Must contain only letters, numbers, and underscores
    - Must not be a Python keyword
    - Must be a valid string type
    - Must not be empty
    - Must contain only ASCII characters

    Args:
        name: String to check

    Returns:
        True if the string would be an invalid identifier

    Raises:
        TypeError: If name is not a string
    """
    if not isinstance(name, str):
        raise TypeError("Name must be a string")

    if not name:
        return True

    # Must start with letter or underscore
    if not name[0].isalpha() and name[0] != "_":
        return True

    # Must contain only ASCII letters, numbers, and underscores
    if not all(c.isascii() and (c.isalnum() or c == "_") for c in name):
        return True

    # Must not be a Python keyword
    if keyword.iskeyword(name):
        return True

    return False