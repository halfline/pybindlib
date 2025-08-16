"""
Tests for the debug_info module.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from pybindlib.debug_info import (
    DebugFileInfo,
    DebugInfoFiles,
    TypeInfo,
    StructMember,
    QualityScore,
    TypedefInfo,
    StructureDefinition,
    calculate_type_byte_size,
    extract_name_from_debug_info,
    parse_struct_member_offset,
    build_structure_name_mapping,
)


def test_debug_file_info():
    """Test DebugFileInfo class."""
    mock_elf = MagicMock()
    mock_dwarf = MagicMock()
    mock_elf.get_dwarf_info.return_value = mock_dwarf

    debug_info = DebugFileInfo(mock_elf, "/path/to/debug", False)
    assert debug_info.file_path == "/path/to/debug"
    assert not debug_info.is_auxiliary

    # Test debug_info property caching
    assert debug_info.debug_info == mock_dwarf
    mock_elf.get_dwarf_info.assert_called_once()

    # Second access should use cached value
    assert debug_info.debug_info == mock_dwarf
    mock_elf.get_dwarf_info.assert_called_once()


def test_debug_info_files():
    """Test DebugInfoFiles container."""
    main_file = DebugFileInfo(MagicMock(), "/path/main", False)
    aux_file = DebugFileInfo(MagicMock(), "/path/aux", True)

    # Test with both files
    files = DebugInfoFiles(main_file, aux_file)
    assert files.main_file == main_file
    assert files.auxiliary_file == aux_file
    assert files.has_auxiliary()
    assert files.count() == 2
    assert list(files) == [main_file, aux_file]

    # Test with only main file
    files = DebugInfoFiles(main_file)
    assert files.main_file == main_file
    assert files.auxiliary_file is None
    assert not files.has_auxiliary()
    assert files.count() == 1
    assert list(files) == [main_file]


def test_type_info():
    """Test TypeInfo class."""
    type_info = TypeInfo(
        ctypes_expression="c_int",
        size_bytes=4,
        description="integer type",
        struct_base_name="MyStruct"
    )

    assert type_info.ctypes_expression == "c_int"
    assert type_info.size_bytes == 4
    assert type_info.description == "integer type"
    assert type_info.struct_base_name == "MyStruct"


def test_struct_member():
    """Test StructMember class."""
    member = StructMember(
        offset=8,
        name="count",
        ctypes_expression="c_int",
        description="counter value"
    )

    assert member.offset == 8
    assert member.name == "count"
    assert member.ctypes_expression == "c_int"
    assert member.description == "counter value"


def test_quality_score():
    """Test QualityScore comparison."""
    score1 = QualityScore(base_score=3, size_score=1)
    score2 = QualityScore(base_score=3, size_score=0)
    score3 = QualityScore(base_score=3, size_score=1)

    assert score1 > score2
    assert not score2 > score1
    assert score1 == score3
    assert score1.total == (3, 1)


def test_typedef_info():
    """Test TypedefInfo class."""
    quality = QualityScore(base_score=3, size_score=1)
    typedef = TypedefInfo(
        representation="c_int",
        quality_score=quality,
        description="integer type"
    )

    assert typedef.representation == "c_int"
    assert typedef.quality_score == quality
    assert typedef.description == "integer type"


def test_structure_definition():
    """Test StructureDefinition class."""
    struct = StructureDefinition(name="MyStruct", size=16)
    assert struct.name == "MyStruct"
    assert struct.size == 16
    assert struct.members == []

    # Add members
    member1 = StructMember(0, "field1", "c_int", "first field")
    member2 = StructMember(4, "field2", "c_float", "second field")
    struct.members = [member1, member2]

    assert len(struct.members) == 2
    assert struct.members[0].name == "field1"
    assert struct.members[1].name == "field2"


def test_calculate_type_byte_size():
    """Test type size calculation."""
    mock_entry = MagicMock()
    mock_entry.attributes = {}
    mock_files = MagicMock()
    aux_index = {}

    # Test with explicit byte size
    mock_entry.attributes["DW_AT_byte_size"] = MagicMock(value=4)
    assert calculate_type_byte_size(mock_entry, mock_files, aux_index) == 4

    # Test with no size information
    mock_entry.attributes = {}
    assert calculate_type_byte_size(mock_entry, mock_files, aux_index) is None

    # Test with None entry
    assert calculate_type_byte_size(None, mock_files, aux_index) is None


def test_parse_struct_member_offset():
    """Test structure member offset parsing."""
    mock_entry = MagicMock()
    mock_entry.attributes = {}

    # Test with direct integer offset
    mock_entry.attributes["DW_AT_data_member_location"] = MagicMock(value=8)
    assert parse_struct_member_offset(mock_entry) == 8

    # Test with no location attribute
    mock_entry.attributes = {}
    assert parse_struct_member_offset(mock_entry) is None


def test_build_structure_name_mapping():
    """Test structure name mapping generation."""
    structures = {
        ("MyStruct", 16): StructureDefinition("MyStruct", 16),
        ("MyStruct", 32): StructureDefinition("MyStruct", 32),
        ("OtherStruct", 8): StructureDefinition("OtherStruct", 8),
    }

    mapping = build_structure_name_mapping(structures)

    # Check that conflicting names get size suffixes
    assert mapping[("MyStruct", 16)] == "MyStruct__16"
    assert mapping[("MyStruct", 32)] == "MyStruct__32"
    # Check that unique names don't get suffixes
    assert mapping[("OtherStruct", 8)] == "OtherStruct"


def test_extract_name_from_debug_info():
    """Test debug info name extraction."""
    mock_files = MagicMock()
    mock_attr = MagicMock()

    # Test with direct string value
    mock_attr.value = "TestName"
    assert extract_name_from_debug_info(mock_attr, mock_files) == "TestName"

    # Test with None attribute
    assert extract_name_from_debug_info(None, mock_files) is None

    # Test with bytes value
    mock_attr.value = b"BytesName"
    mock_attr.form = "DW_FORM_string"
    assert extract_name_from_debug_info(mock_attr, mock_files) == "BytesName"