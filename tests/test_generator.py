"""
Tests for the generator module.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from pybindlib.debug_info import (
    DebugFileInfo,
    DebugInfoFiles,
    StructMember,
    StructureDefinition,
    TypedefInfo,
    QualityScore,
)
from pybindlib.generator import (
    generate_python_module,
    generate_constants_section,
    find_usage_example,
    _highlight_python_snippet,
)


def test_generate_python_module(temp_file):
    """Test Python module generation."""
    # Setup test data
    structures = {
        ("TestStruct", 8): StructureDefinition("TestStruct", 8),
    }
    structures[("TestStruct", 8)].members = [
        StructMember(0, "field1", "c_int", "test field")
    ]

    typedefs = {
        "TestTypedef": TypedefInfo(
            "c_void_p",
            QualityScore(base_score=3, size_score=1),
            "test typedef"
        )
    }

    exported_functions = ["test_function"]
    macros = {"TEST_MACRO": "42"}

    # Generate module
    generate_python_module(
        temp_file,
        "libtest.so",
        "test-build-id",
        structures,
        typedefs,
        exported_functions,
        macros
    )

    # Verify generated content
    with open(temp_file, "r") as f:
        content = f.read()

        # Check basic structure
        assert "class types:" in content
        assert "class TestStruct(Structure):" in content
        assert "class TestTypedef(c_void_p):" in content
        assert "EXPORT_SYMBOLS = [" in content
        assert "'test_function'" in content
        assert "TEST_MACRO = 42" in content

        # Check module organization
        assert "import types as _types_module" in content
        assert "import sys as _sys" in content
        assert "_symbols_module = _types_module.ModuleType" in content
        assert "_types_submodule = _types_module.ModuleType" in content
        assert "_constants_module = _types_module.ModuleType" in content


def test_generate_constants_section():
    """Test constants section generation."""
    macros = {
        "VALID_CONSTANT": "42",
        "ANOTHER_CONSTANT": "'test'",
        "__INVALID__": "123",  # Should be skipped
        "Invalid Name": "456",  # Should be skipped
    }

    result = generate_constants_section(macros, "test_module")

    # Check content
    assert "VALID_CONSTANT" in result
    assert "ANOTHER_CONSTANT" in result
    assert "__INVALID__" not in result
    assert "Invalid Name" not in result
    assert "_constants_module = _types_module.ModuleType" in result
    assert "_sys.modules['test_module.constants']" in result


def test_find_usage_example():
    """Test finding usage examples from debug info."""
    # Create mock debug files and structures
    mock_debug_files = MagicMock()
    mock_debug_files.main_file = MagicMock()
    mock_debug_files.auxiliary_file = None

    structures = {
        ("TestStruct", 16): StructureDefinition("TestStruct", 16),
    }
    structures[("TestStruct", 16)].members = [
        StructMember(0, "test_field", "c_int", "test field")
    ]

    # Test with no structures
    example = find_usage_example(mock_debug_files, {})
    assert example["struct"] == "MyStruct"  # Should use default

    # Test with structures but no debug info
    example = find_usage_example(mock_debug_files, structures)
    assert example["struct"] == "MyStruct"  # Should use default when no functions found


def test_highlight_python_snippet():
    """Test Python code syntax highlighting."""
    # Test keyword highlighting
    result = _highlight_python_snippet("from module import Class")
    assert "from" in result
    assert "import" in result

    # Test builtin type highlighting
    result = _highlight_python_snippet("POINTER(c_int)")
    assert "POINTER" in result
    assert "c_int" in result

    # Test comment highlighting
    result = _highlight_python_snippet("code # comment")
    assert "#" in result
    assert "comment" in result