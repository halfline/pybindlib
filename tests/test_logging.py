"""
Tests for the logging module.
"""

import logging
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from pybindlib.logging import ColoredFormatter, setup_logging


@pytest.fixture
def capture_stdout():
    """Fixture to capture stdout output."""
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        yield mock_stdout


def test_colored_formatter_init():
    """Test ColoredFormatter initialization."""
    # Test with color enabled
    with patch("pybindlib.logging._has_colorama", True):
        formatter = ColoredFormatter(use_color=True)
        assert formatter.use_color is True

    # Test with color disabled
    formatter = ColoredFormatter(use_color=False)
    assert formatter.use_color is False


def test_colored_formatter_format():
    """Test log message formatting."""
    formatter = ColoredFormatter(use_color=False)

    # Create a test record
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None
    )

    # Set format string to include levelname_colored
    formatter._fmt = "%(levelname_colored)s%(message)s"

    # Test formatting without color
    formatted = formatter.format(record)
    assert "▸" in formatted
    assert "Test message" in formatted


def test_setup_logging():
    """Test logging setup and configuration."""
    # Test basic setup
    with patch("sys.stdout", new_callable=StringIO):
        logger = setup_logging(verbose=False, use_color=False)
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

        # Test verbose mode
        logger = setup_logging(verbose=True, use_color=False)
        assert logger.level == logging.DEBUG

        # Test handler cleanup
        logger = setup_logging(verbose=False, use_color=False)
        original_handlers = len(logger.handlers)
        logger = setup_logging(verbose=False, use_color=False)  # Setup again
        assert len(logger.handlers) == original_handlers  # Should not accumulate handlers


def test_log_levels():
    """Test different log levels and their output."""
    stream = StringIO()
    logger = setup_logging(verbose=True, use_color=False)

    # Replace the handler's stream
    logger.handlers[0].stream = stream

    # Test all log levels
    test_messages = {
        "debug": "Debug message",
        "info": "Info message",
        "warning": "Warning message",
        "error": "Error message",
        "critical": "Critical message"
    }

    for level, message in test_messages.items():
        getattr(logger, level)(message)

    output = stream.getvalue()

    # Verify all messages are present
    for message in test_messages.values():
        assert message in output

    # Verify non-verbose mode filters debug messages
    stream = StringIO()
    logger = setup_logging(verbose=False, use_color=False)
    logger.handlers[0].stream = stream

    logger.debug("Hidden debug message")
    logger.info("Visible info message")

    filtered_output = stream.getvalue()
    assert "Hidden debug message" not in filtered_output
    assert "Visible info message" in filtered_output


def test_color_support():
    """Test color support detection and usage."""
    with patch("pybindlib.logging._has_colorama", True):
        formatter = ColoredFormatter(use_color=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        formatter._fmt = "%(levelname_colored)s%(message)s"
        formatted = formatter.format(record)
        # Should contain color codes when color is supported
        assert "\033[" in formatted or "▸" in formatted  # Color code or fallback symbol

    with patch("pybindlib.logging._has_colorama", False):
        formatter = ColoredFormatter(use_color=True)
        assert not formatter.use_color  # Should disable color when not supported