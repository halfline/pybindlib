"""
Tests for the progress module.
"""

import pytest
from unittest.mock import patch, MagicMock

from pybindlib.progress import ProgressIndicator


def test_progress_indicator_init():
    """Test progress indicator initialization."""
    progress = ProgressIndicator("Testing")
    assert progress.prefix == "Testing"
    assert not progress.active
    assert progress.current_dot == 0
    assert progress.last_length == 0


def test_progress_indicator_start():
    """Test starting the progress indicator."""
    progress = ProgressIndicator()
    assert not progress.active

    progress.start()
    assert progress.active
    assert progress.current_dot == 0


def test_progress_indicator_update(capsys):
    """Test progress indicator updates."""
    progress = ProgressIndicator("Testing")
    progress.start()

    # Test update without status (force no color to simplify)
    with patch("pybindlib.progress._has_colorama", False):
        progress.update()
        out = capsys.readouterr().out
        assert "Testing" in out
        assert any(dots in out for dots in ["   ", ".  ", ".. ", "..."])

    # Test update with status
    with patch("pybindlib.progress._has_colorama", False):
        progress.update("Processing item 1")
        out = capsys.readouterr().out
        assert "Testing" in out
        assert "Processing item 1" in out

    # Test dot rotation
    initial_dot = progress.current_dot
    progress.update()
    assert progress.current_dot == (initial_dot + 1) % len(progress.dots)


def test_progress_indicator_finish(capsys):
    """Test finishing the progress indicator."""
    progress = ProgressIndicator("Testing")
    progress.start()

    # Test with default completion message (force no color)
    with patch("pybindlib.progress._has_colorama", False):
        progress.finish()
        out = capsys.readouterr().out
        assert "Complete" in out
        assert not progress.active
        assert progress.last_length == 0

    # Test with custom completion message
    progress = ProgressIndicator("Testing")
    progress.start()
    with patch("pybindlib.progress._has_colorama", False):
        progress.finish("All done!")
        out = capsys.readouterr().out
        assert "All done!" in out


def test_progress_indicator_inactive():
    """Test operations on inactive progress indicator."""
    progress = ProgressIndicator()

    # Update should do nothing when inactive
    with patch("sys.stdout") as mock_stdout:
        progress.update("Test")
        mock_stdout.write.assert_not_called()

    # Finish should do nothing when inactive
    with patch("sys.stdout") as mock_stdout:
        progress.finish()
        mock_stdout.write.assert_not_called()


def test_progress_indicator_thread_safety():
    """Test thread safety of progress indicator."""
    progress = ProgressIndicator()
    progress.start()

    # Mock the lock to verify it's used
    mock_lock = MagicMock()
    progress._lock = mock_lock

    # Test update
    progress.update("Test")
    mock_lock.__enter__.assert_called_once()
    mock_lock.__exit__.assert_called_once()

    # Reset mock and test finish
    mock_lock.reset_mock()
    progress.finish()
    mock_lock.__enter__.assert_called_once()
    mock_lock.__exit__.assert_called_once()


def test_progress_indicator_line_clearing(capsys):
    """Test line clearing behavior."""
    progress = ProgressIndicator("Testing")
    progress.start()

    # First update sets last_length (force no color)
    with patch("pybindlib.progress._has_colorama", False):
        progress.update("Test")
        out = capsys.readouterr().out
        assert out  # Some output produced
        initial_length = progress.last_length
        assert initial_length > 0

        # Second update should clear previous line
        progress.update("Longer test message")
        out = capsys.readouterr().out
        # We expect carriage returns to be used for clearing when active
        assert "\r" in out or "\n" in out

        # Finish should clear the last progress line
        progress.finish()
        out = capsys.readouterr().out
        assert "✓" in out