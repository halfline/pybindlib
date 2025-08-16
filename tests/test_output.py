"""
Tests for output formatting utilities.
"""

import re
from io import StringIO
from unittest.mock import patch

import pytest

from pybindlib.output import (
    print_banner,
    print_section_header,
    print_file_info,
    print_success,
    print_stats,
    _strip_ansi,
)


def test_strip_ansi():
    """Test stripping ANSI color codes."""
    text = "\x1b[32mHello\x1b[0m \x1b[1mWorld\x1b[0m"
    assert _strip_ansi(text) == "Hello World"


def test_print_banner_with_color(capsys):
    """Test banner printing with color."""
    with patch("pybindlib.output._has_colorama", True):
        print_banner("Test Banner", use_color=True)
        captured = capsys.readouterr()
        output = captured.out

        # Should contain cyan box characters
        assert "╭" in output
        assert "╮" in output
        assert "╰" in output
        assert "╯" in output
        assert "─" in output
        assert "│" in output

        # Should contain ANSI color codes
        assert "\x1b[36m" in output  # Cyan
        assert "\x1b[32m" in output  # Green
        assert "\x1b[0m" in output   # Reset

        # Should contain the text
        assert "Test Banner" in output

        # Box should be properly aligned
        lines = output.strip().split("\n")
        assert len(lines) == 3  # Box should be 3 lines

        # Remove ANSI codes and check alignment
        clean_lines = [_strip_ansi(line) for line in lines]
        assert len(clean_lines[0]) == len(clean_lines[1]) == len(clean_lines[2])
        assert clean_lines[1].endswith("│")  # Right border should align


def test_print_banner_without_color(capsys):
    """Test banner printing without color."""
    print_banner("Test Banner", use_color=False)
    captured = capsys.readouterr()
    output = captured.out

    # Should use ASCII box characters
    assert "+" in output
    assert "-" in output
    assert "|" in output

    # Should not contain ANSI color codes
    assert "\x1b[" not in output

    # Should contain the text
    assert "Test Banner" in output

    # Box should be properly aligned
    lines = output.strip().split("\n")
    assert len(lines) == 3  # Box should be 3 lines
    assert len(lines[0]) == len(lines[1]) == len(lines[2])
    assert lines[1].endswith("|")  # Right border should align


def test_print_banner_with_ansi_text(capsys):
    """Test banner printing with text containing ANSI codes."""
    with patch("pybindlib.output._has_colorama", True):
        text = f"\x1b[1mBold\x1b[0m Text"
        print_banner(text, use_color=True)
        captured = capsys.readouterr()
        output = captured.out

        # Box width should account for text length without ANSI codes
        text_len = len("Bold Text")
        assert f"─" * (text_len + 2) in output

        # Box should be properly aligned
        lines = output.strip().split("\n")
        clean_lines = [_strip_ansi(line) for line in lines]
        assert len(clean_lines[0]) == len(clean_lines[1]) == len(clean_lines[2])
        assert clean_lines[1].endswith("│")  # Right border should align


def test_print_banner_with_wide_text(capsys):
    """Test banner printing with wide text to verify alignment."""
    wide_text = "This is a much longer banner text to test alignment"
    with patch("pybindlib.output._has_colorama", True):
        print_banner(wide_text, use_color=True)
        captured = capsys.readouterr()
        output = captured.out

        # Box should be properly aligned
        lines = output.strip().split("\n")
        clean_lines = [_strip_ansi(line) for line in lines]

        # All lines should have the same width
        widths = [len(line) for line in clean_lines]
        assert len(set(widths)) == 1  # All widths should be equal

        # Verify box corners align
        assert clean_lines[0][0] == "╭" and clean_lines[0][-1] == "╮"
        assert clean_lines[1][0] == "│" and clean_lines[1][-1] == "│"
        assert clean_lines[2][0] == "╰" and clean_lines[2][-1] == "╯"


"""
Tests for the output module.
"""

import re
import pytest
from unittest.mock import patch

from pybindlib.output import (
    print_banner,
    print_section_header,
    print_file_info,
    print_success,
    print_stats,
    ANSI_COLOR_PATTERN,
)


def test_print_banner(capsys):
    """Test banner printing with and without color."""
    # Force no color to simplify capture
    with patch("pybindlib.output._has_colorama", False):
        print_banner("Test Banner", use_color=True)
        captured = capsys.readouterr()
        output = captured.out
        assert "Test Banner" in output
        assert "+" in output  # ASCII box characters
        assert "-" in output
        assert "|" in output

        # Test without color
        print_banner("Test Banner", use_color=False)
        captured = capsys.readouterr()
        output = captured.out
        assert "Test Banner" in output
        assert "+" in output  # ASCII box characters
        assert "-" in output
        assert "|" in output


def test_print_section_header(capsys):
    """Test section header printing with and without color."""
    title = "Test Section"

    # Force no color to simplify capture
    with patch("pybindlib.output._has_colorama", False):
        print_section_header(title, use_color=True)
        out = capsys.readouterr().out
        assert title in out
        assert "──" in out  # Plain style when no color

    # Test without color
    print_section_header(title, use_color=False)
    out = capsys.readouterr().out
    assert title in out
    assert "──" in out
    assert not bool(ANSI_COLOR_PATTERN.search(out))


def test_print_file_info(capsys):
    """Test file info printing with various conditions."""
    label = "Test File"
    path = "/path/to/file"

    # Force no color to simplify capture
    with patch("pybindlib.output._has_colorama", False):
        print_file_info(label, path, exists=True, use_color=True)
        out = capsys.readouterr().out
        assert label in out
        assert path in out
        assert "✓" in out

    # Test non-existing file
    with patch("pybindlib.output._has_colorama", False):
        print_file_info(label, path, exists=False, use_color=True)
        out = capsys.readouterr().out
        assert "✗" in out

    # Test without color
    print_file_info(label, path, exists=True, use_color=False)
    out = capsys.readouterr().out
    assert label in out
    assert path in out
    assert "✓" in out
    assert not bool(ANSI_COLOR_PATTERN.search(out))


def test_print_success(capsys):
    """Test success message printing."""
    message = "Operation completed successfully"

    # Force no color to simplify capture
    with patch("pybindlib.output._has_colorama", False):
        print_success(message, use_color=True)
        out = capsys.readouterr().out
        assert message in out
        assert "✓" in out

    # Test without color
    print_success(message, use_color=False)
    out = capsys.readouterr().out
    assert message in out
    assert "✓" in out
    assert not bool(ANSI_COLOR_PATTERN.search(out))


def test_print_stats(capsys):
    """Test statistics printing."""
    structures = 10
    typedefs = 5

    # Force no color to simplify capture
    with patch("pybindlib.output._has_colorama", False):
        print_stats(structures, typedefs, use_color=True)
        out = capsys.readouterr().out
        assert str(structures) in out
        assert str(typedefs) in out
        assert "Structures:" in out
        assert "Typedefs:" in out

    # Test without color
    print_stats(structures, typedefs, use_color=False)
    out = capsys.readouterr().out
    assert str(structures) in out
    assert str(typedefs) in out
    assert "Structures:" in out
    assert "Typedefs:" in out
    assert not bool(ANSI_COLOR_PATTERN.search(out))


def test_ansi_color_pattern():
    """Test ANSI color pattern matching."""
    # Test pattern matches ANSI color codes
    test_string = "\x1b[31mRed Text\x1b[0m"
    assert ANSI_COLOR_PATTERN.search(test_string)

    # Test pattern doesn't match non-ANSI text
    test_string = "Plain Text"
    assert not ANSI_COLOR_PATTERN.search(test_string)

    # Test pattern matches multiple color codes
    test_string = "\x1b[31mRed\x1b[32mGreen\x1b[0m"
    matches = ANSI_COLOR_PATTERN.findall(test_string)
    assert len(matches) == 3


def test_color_fallback(capsys):
    """Test color fallback when colorama is not available."""
    with patch("pybindlib.output._has_colorama", False):
        # Test all output functions with color enabled but colorama unavailable
        print_banner("Test Banner", use_color=True)
        print_section_header("Test Section", use_color=True)
        print_file_info("Test Label", "test/path", use_color=True)
        print_success("Test Success", use_color=True)
        print_stats(5, 10, use_color=True)

        captured = capsys.readouterr()
        output = captured.out

        # Should not contain any ANSI color codes
        assert "\x1b[" not in output

        # Should contain the text
        assert "Test Banner" in output
        assert "Test Section" in output
        assert "Test Label" in output
        assert "test/path" in output
        assert "Test Success" in output
        assert "Structures: 5" in output
        assert "Typedefs: 10" in output