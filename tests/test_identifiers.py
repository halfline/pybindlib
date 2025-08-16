"""
Tests for the identifiers module.
"""

import pytest
from pybindlib.identifiers import create_safe_python_identifier, is_invalid_identifier


def test_create_safe_python_identifier():
    """Test conversion of identifiers to safe Python names."""
    # Test empty input
    assert create_safe_python_identifier("") == "Unknown"

    # Test valid identifiers (should remain unchanged)
    assert create_safe_python_identifier("valid_name") == "valid_name"
    assert create_safe_python_identifier("ValidName") == "ValidName"
    assert create_safe_python_identifier("name123") == "name123"

    # Test invalid characters
    assert create_safe_python_identifier("invalid-name") == "invalid_name"
    assert create_safe_python_identifier("special@chars") == "special_chars"
    assert create_safe_python_identifier("spaces in name") == "spaces_in_name"

    # Test names starting with numbers
    assert create_safe_python_identifier("123name") == "Type_123name"
    assert create_safe_python_identifier("42") == "Type_42"

    # Test special characters
    assert create_safe_python_identifier("$special") == "Type__special"
    assert create_safe_python_identifier("name!@#") == "name___"

    # Test mixed cases
    assert create_safe_python_identifier("Mixed-Case_Name!") == "Mixed_Case_Name_"
    assert create_safe_python_identifier("C++_Class") == "C___Class"


def test_is_invalid_identifier():
    """Test identifier validation."""
    # Test valid identifiers
    assert not is_invalid_identifier("valid_name")
    assert not is_invalid_identifier("ValidName")
    assert not is_invalid_identifier("name123")
    assert not is_invalid_identifier("_private")

    # Test invalid identifiers
    assert is_invalid_identifier("")  # Empty string
    assert is_invalid_identifier("123name")  # Starts with number
    assert is_invalid_identifier("invalid-name")  # Contains hyphen
    assert is_invalid_identifier("special@chars")  # Contains special characters
    assert is_invalid_identifier("spaces in name")  # Contains spaces

    # Test Python keywords
    assert is_invalid_identifier("class")
    assert is_invalid_identifier("def")
    assert is_invalid_identifier("return")
    assert is_invalid_identifier("import")

    # Test invalid types
    with pytest.raises(TypeError, match="Name must be a string"):
        is_invalid_identifier(None)
    with pytest.raises(TypeError, match="Name must be a string"):
        is_invalid_identifier(123)  # Non-string input

    # Test special characters
    assert is_invalid_identifier("name!")
    assert is_invalid_identifier("$name")
    assert is_invalid_identifier("name@domain")

    # Test Unicode characters - these should be considered invalid
    assert is_invalid_identifier("café")  # Non-ASCII characters
    assert is_invalid_identifier("π")  # Mathematical symbols
    assert is_invalid_identifier("名前")  # Non-Latin characters