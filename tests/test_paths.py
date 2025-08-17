"""
Tests for path handling utilities.
"""

import os
import pytest
from unittest.mock import patch, mock_open, MagicMock

from pybindlib.paths import (
    generate_output_filename,
    resolve_header_path,
    strip_trailing_whitespace_from_file,
)


def test_generate_output_filename():
    """Test output filename generation."""
    # Test with library name
    assert generate_output_filename("libtest.so.1", "/path/to/lib") == "libtest_so_1.py"
    assert generate_output_filename("lib-test.so", "/path/to/lib") == "lib_test_so.py"
    assert generate_output_filename("lib/test.so", "/path/to/lib") == "lib_test_so.py"

    # Test with None library name (should use fallback path)
    assert generate_output_filename(None, "/path/to/libtest.so") == "libtest_so.py"
    assert generate_output_filename(None, "libtest.so") == "libtest_so.py"

    # Test special characters
    assert generate_output_filename("lib-test-1.2.3.so", "/path/to/lib") == "lib_test_1_2_3_so.py"
    assert generate_output_filename("lib/test/1.so", "/path/to/lib") == "lib_test_1_so.py"

    # Test empty library name
    assert generate_output_filename("", "/path/to/libtest.so") == "libtest_so.py"


def test_resolve_header_path_absolute():
    """Test resolving absolute header paths."""
    path = "/usr/include/freerdp3/freerdp.h"
    assert resolve_header_path(path) == path


def test_resolve_header_path_relative_current_dir(tmp_path):
    """Test resolving header in current directory."""
    # Create a test header file
    header = tmp_path / "test.h"
    header.write_text("")

    # Save current directory
    old_cwd = os.getcwd()
    try:
        # Change to temp directory
        os.chdir(str(tmp_path))
        result = resolve_header_path("test.h")
        assert os.path.samefile(result, header)
    finally:
        # Restore current directory
        os.chdir(old_cwd)


def test_resolve_header_path_include_paths(tmp_path):
    """Test resolving header using include paths."""
    # Create test directories and file
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    header = include_dir / "test.h"
    header.write_text("")

    result = resolve_header_path("test.h", include_paths=[str(include_dir)])
    assert os.path.samefile(result, header)


def test_resolve_header_path_multiple_include_paths(tmp_path):
    """Test resolving header with multiple include paths."""
    # Create test directories and files
    include1 = tmp_path / "include1"
    include2 = tmp_path / "include2"
    include1.mkdir()
    include2.mkdir()

    # Put header in second include path
    header = include2 / "test.h"
    header.write_text("")

    result = resolve_header_path(
        "test.h",
        include_paths=[str(include1), str(include2)]
    )
    assert os.path.samefile(result, header)


def test_resolve_header_path_not_found():
    """Test behavior when header is not found."""
    path = "nonexistent.h"
    include_paths = ["/usr/include", "/usr/local/include"]
    assert resolve_header_path(path, include_paths) == path


def test_strip_trailing_whitespace_from_file(temp_file):
    """Test whitespace stripping from file."""
    # Test with various whitespace patterns
    test_content = [
        "Line with spaces   \n",
        "Line with tabs\t\t\n",
        "Line with mixed spaces and tabs  \t  \n",
        "Line with no trailing whitespace\n",
        "Final line with whitespace  "  # No newline
    ]

    # Write test content
    with open(temp_file, "w", encoding="utf-8") as f:
        f.writelines(test_content)

    # Strip whitespace
    strip_trailing_whitespace_from_file(temp_file)

    # Verify results
    with open(temp_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

        # Check each line is stripped
        assert lines[0] == "Line with spaces\n"
        assert lines[1] == "Line with tabs\n"
        assert lines[2] == "Line with mixed spaces and tabs\n"
        assert lines[3] == "Line with no trailing whitespace\n"
        assert lines[4] == "Final line with whitespace\n"

        # Check file ends with exactly one newline
        assert lines[-1].endswith("\n")


def test_strip_trailing_whitespace_error_handling():
    """Test error handling in whitespace stripping."""
    # Test with non-existent file
    with patch("builtins.open", side_effect=FileNotFoundError):
        strip_trailing_whitespace_from_file("nonexistent.txt")
        # Should not raise exception

    # Test with permission error
    with patch("builtins.open", side_effect=PermissionError):
        strip_trailing_whitespace_from_file("protected.txt")
        # Should not raise exception

    # Test with encoding error
    with patch("builtins.open", side_effect=UnicodeError):
        strip_trailing_whitespace_from_file("invalid_encoding.txt")
        # Should not raise exception


def test_strip_trailing_whitespace_encoding():
    """Test handling of different encodings and special characters."""
    test_content = [
        "ASCII line   \n",
        "Unicode line with emoji 😊   \n",
        "Line with special chars ñ é ß   \n"
    ]

    # Create a mock file object that properly tracks write calls
    mock_file = MagicMock()
    mock_file.write = MagicMock()
    mock_file.writelines = MagicMock()

    # Mock both read and write operations
    mock_open_obj = MagicMock()
    mock_open_obj.__enter__ = MagicMock(return_value=mock_file)
    mock_open_obj.__exit__ = MagicMock(return_value=None)

    # Set up the mock to return our test content when reading
    mock_file.readlines = MagicMock(return_value=test_content)

    with patch("builtins.open", return_value=mock_open_obj):
        strip_trailing_whitespace_from_file("test.txt")

        # Verify write calls
        write_calls = list(mock_file.writelines.call_args[0][0])
        assert write_calls[0] == "ASCII line\n"
        assert write_calls[1] == "Unicode line with emoji 😊\n"
        assert write_calls[2] == "Line with special chars ñ é ß\n"