"""
Tests for the preprocessor module.
"""

import pytest
from unittest.mock import patch, mock_open, MagicMock

from pybindlib.preprocessor import process_headers, parse_function_pointer_typedefs


def test_process_headers_with_referenced_modules():
    """Test header processing with referenced modules."""
    # Mock module with constants
    mock_module = MagicMock()
    mock_module.__dir__ = MagicMock(return_value=["CONSTANT_1", "CONSTANT_2", "_private"])
    mock_module.CONSTANT_1 = 42
    mock_module.CONSTANT_2 = "test"

    with patch("importlib.import_module", return_value=mock_module):
        result = process_headers([], referenced_modules=["test_module"])
        assert result == {}  # No headers to process

        # Test with empty headers list
        result = process_headers([], referenced_modules=["test_module"])
        assert result == {}


def test_process_headers_cpp_output():
    """Test processing of cpp output."""
    # Mock cpp command output
    mock_cpp_output = """
#define SIMPLE_CONSTANT 42
#define HEX_CONSTANT 0xFF
#define OCTAL_CONSTANT 0777
#define STRING_CONSTANT "test"
#define CHAR_CONSTANT 'A'
#define FLOAT_CONSTANT 3.14
#define NEGATIVE_CONSTANT -123
#define EMPTY_CONSTANT
#define FUNCTION_MACRO(x) (x * 2)
#define __BUILTIN_MACRO 1
#define CAST_CONSTANT (unsigned int)123
#define COMPLEX_CONSTANT (1 << 2)
"""

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = mock_cpp_output.strip()

    with patch("subprocess.run", return_value=mock_process):
        result = process_headers(["test.h"])

        # Check valid constants are extracted
        assert result["SIMPLE_CONSTANT"] == "42"
        assert result["HEX_CONSTANT"] == "255"
        assert result["OCTAL_CONSTANT"] == "511"
        assert result["STRING_CONSTANT"] == "'test'"
        assert result["CHAR_CONSTANT"] == "'A'"
        assert result["FLOAT_CONSTANT"] == "3.14"
        assert result["NEGATIVE_CONSTANT"] == "-123"
        assert result["EMPTY_CONSTANT"] == "1"

        # Check invalid/complex constants are skipped
        assert "FUNCTION_MACRO" not in result
        assert "__BUILTIN_MACRO" not in result
        assert "COMPLEX_CONSTANT" not in result


def test_process_headers_error_handling():
    """Test error handling in header processing."""
    # Test cpp command failure
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = "cpp: error: test.h: No such file or directory"

    with patch("subprocess.run", return_value=mock_process):
        result = process_headers(["test.h"])
        assert result == {}

    # Test subprocess exception
    with patch("subprocess.run", side_effect=Exception("Command failed")):
        result = process_headers(["test.h"])
        assert result == {}


def test_process_headers_include_paths():
    """Test header processing with include paths."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "#define TEST_CONSTANT 42\n"

    with patch("subprocess.run", return_value=mock_process) as mock_run:
        process_headers(["test.h"], include_paths=["/usr/include", "/opt/include"])

        # Verify cpp command includes -I options
        cmd = mock_run.call_args[0][0]
        assert "-I" in cmd
        assert "/usr/include" in cmd
        assert "/opt/include" in cmd


def test_parse_function_pointer_typedefs(temp_file):
    """Test function pointer typedef extraction."""
    # Test content with various typedef patterns
    test_content = """
    typedef void (*SimpleCallback)(void);
    typedef int (*ComplexCallback)(int arg1, char* arg2);
    typedef BOOL (CALLBACK* WindowProc)(HWND, UINT, WPARAM, LPARAM);
    typedef void Function(void);  // Not a function pointer
    typedef int* IntPtr;  // Not a function pointer
    typedef struct { int x; } NotAFunction;
    """

    # Write test content
    with open(temp_file, "w") as f:
        f.write(test_content)

    result = parse_function_pointer_typedefs([temp_file])

    # Check function pointer typedefs are found
    assert "SimpleCallback" in result
    assert "ComplexCallback" in result
    assert "WindowProc" in result

    # Check non-function pointer typedefs are not included
    assert "Function" not in result
    assert "IntPtr" not in result
    assert "NotAFunction" not in result


def test_parse_function_pointer_typedefs_error_handling():
    """Test error handling in function pointer typedef parsing."""
    # Test with non-existent file
    result = parse_function_pointer_typedefs(["nonexistent.h"])
    assert result == set()

    # Test with empty file list
    result = parse_function_pointer_typedefs([])
    assert result == set()

    # Test with file read error
    with patch("builtins.open", side_effect=Exception("Read error")):
        result = parse_function_pointer_typedefs(["test.h"])
        assert result == set()


def test_process_headers_value_conversion():
    """Test conversion of different macro value types."""
    mock_cpp_output = """#define INT_DEC 12345
#define INT_HEX 0xABCD
#define INT_OCT 0777
#define FLOAT_SIMPLE 3.14
#define FLOAT_EXP 1.23e4
#define STR_SIMPLE "hello"
#define STR_ESCAPE "hello\\nworld"
#define CHAR_SIMPLE 'X'
#define LONG_SUFFIX 123L
#define INVALID_HEX 0xGHIJ
#define INVALID_OCT 0888
#define INVALID_FLOAT 1.2.3
#define COMPLEX_EXPR (1 + 2)"""

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = mock_cpp_output.strip()

    with patch("subprocess.run", return_value=mock_process):
        result = process_headers(["test.h"])

        # Check numeric conversions
        assert result["INT_DEC"] == "12345"
        assert result["INT_HEX"] == "43981"  # 0xABCD in decimal
        assert result["INT_OCT"] == "511"  # 0777 in decimal
        assert result["FLOAT_SIMPLE"] == "3.14"
        assert result["FLOAT_EXP"] == "12300.0"

        # Check string conversions
        assert result["STR_SIMPLE"] == "'hello'"
        assert "\\n" in result["STR_ESCAPE"]
        assert result["CHAR_SIMPLE"] == "'X'"

        # Check suffix handling
        assert result["LONG_SUFFIX"] == "123"

        # Check invalid values are skipped
        assert "INVALID_HEX" not in result
        assert "INVALID_OCT" not in result
        assert "INVALID_FLOAT" not in result
        assert "COMPLEX_EXPR" not in result