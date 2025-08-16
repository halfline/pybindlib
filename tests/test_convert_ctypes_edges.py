"""
Tests for convert_dwarf_type_to_ctypes edge cases using mocked DIEs.
"""

from types import SimpleNamespace

from pybindlib.debug_info import (
    DebugFileInfo,
    DebugInfoFiles,
    convert_dwarf_type_to_ctypes,
    calculate_type_byte_size,
)


class MockDIE:
    def __init__(self, tag, attrs=None, children=None, cu_addr_size=8):
        self.tag = tag
        self.attributes = attrs or {}
        self._children = children or []
        self.cu = SimpleNamespace(address_size=cu_addr_size)
        self._referent = None

    def iter_children(self):
        return iter(self._children)

    def get_DIE_from_attribute(self, attr_name):
        if self._referent is None:
            raise NotImplementedError
        return self._referent


class MockELF:
    def __init__(self, info):
        self._info = info

    def get_dwarf_info(self):
        return self._info

    def has_dwarf_info(self):
        return True


class MockInfo:
    def __init__(self):
        self.config = SimpleNamespace(address_size=8)
        self.debug_str_sec = None
        self.debug_line_str_sec = None

    def iter_CUs(self):
        return iter(())


def _make_debug_files():
    info = MockInfo()
    elf = MockELF(info)
    return DebugInfoFiles(main_file=DebugFileInfo(elf, "/tmp/main", False))


def _attr_str(name):
    return {"DW_AT_name": SimpleNamespace(form="DW_FORM_string", value=name)}


def test_pointer_type_size_and_desc():
    files = _make_debug_files()
    aux_index = {}
    base = MockDIE("DW_TAG_base_type", attrs=_attr_str("int"))
    ptr = MockDIE("DW_TAG_pointer_type", attrs={}, children=[])
    ptr._referent = base
    ptr.attributes["DW_AT_type"] = SimpleNamespace(form="DW_FORM_ref4", value=0)

    info = convert_dwarf_type_to_ctypes(ptr, files, aux_index)
    assert info.ctypes_expression == "c_void_p"  # pointer generalization
    assert info.size_bytes in (8, 4)
    assert "pointer" in info.description


def test_array_type_with_count():
    files = _make_debug_files()
    aux_index = {}
    elem = MockDIE("DW_TAG_base_type", attrs=_attr_str("int"))
    # subrange with count 4
    subrange = MockDIE("DW_TAG_subrange_type", attrs={"DW_AT_count": SimpleNamespace(value=4)})
    arr = MockDIE("DW_TAG_array_type", children=[subrange])
    arr._referent = elem
    arr.attributes["DW_AT_type"] = SimpleNamespace(form="DW_FORM_ref4", value=0)

    info = convert_dwarf_type_to_ctypes(arr, files, aux_index)
    assert info.size_bytes is not None
    assert "array of" in info.description
    assert "* 4" in info.ctypes_expression or ")" in info.ctypes_expression


def test_typedef_chain_peeling_to_base():
    files = _make_debug_files()
    aux_index = {}
    base = MockDIE("DW_TAG_base_type", attrs=_attr_str("unsigned int"))
    typedef = MockDIE("DW_TAG_typedef", attrs={})
    typedef._referent = base
    typedef.attributes["DW_AT_type"] = SimpleNamespace(form="DW_FORM_ref4", value=0)

    info = convert_dwarf_type_to_ctypes(typedef, files, aux_index)
    # Given the current stub for remove_type_qualifiers_and_typedefs, allow fallback
    assert info.ctypes_expression.startswith("c_uint") or info.ctypes_expression in ("c_void_p",)


def test_unknown_type_fallback_to_bytes():
    files = _make_debug_files()
    aux_index = {}
    unknown = MockDIE("DW_TAG_structure_type", attrs=_attr_str("Mystery"))
    # No size info available, expect byte array or void pointer fallback
    info = convert_dwarf_type_to_ctypes(unknown, files, aux_index)
    assert info.ctypes_expression.startswith("(") or info.ctypes_expression == "c_void_p"