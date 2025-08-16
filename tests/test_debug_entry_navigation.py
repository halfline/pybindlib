"""
Tests focused on DWARF entry navigation and auxiliary index behavior using mocks.
"""

from types import SimpleNamespace
import pytest

from pybindlib.debug_info import (
    DebugFileInfo,
    DebugInfoFiles,
    build_auxiliary_debug_entry_index,
    find_referenced_debug_entry,
    extract_name_from_debug_info,
)


class MockDIE:
    def __init__(self, tag, offset=None, attributes=None, referent=None):
        self.tag = tag
        self.offset = offset if offset is not None else 0
        self.attributes = attributes or {}
        self._referent = referent
        self.cu = SimpleNamespace(address_size=8)

    def get_DIE_from_attribute(self, attr_name):
        # Simulate local ref resolution
        if self._referent is None:
            raise NotImplementedError
        return self._referent

    def iter_children(self):
        return iter(())


class MockDebugInfo:
    def __init__(self, cus):
        self._cus = cus
        self.config = SimpleNamespace(address_size=8)
        self.debug_str_sec = None
        self.debug_line_str_sec = None

    def iter_CUs(self):
        return iter(self._cus)


class MockCU:
    def __init__(self, dies):
        self._dies = dies

    def iter_DIEs(self):
        return iter(self._dies)

    def get_top_DIE(self):
        return self._dies[0] if self._dies else MockDIE("DW_TAG_compile_unit")


class MockELF:
    def __init__(self, dwarf_info):
        self._dwarf_info = dwarf_info

    def get_dwarf_info(self):
        return self._dwarf_info

    def get_section_by_name(self, name):
        return None


def test_build_aux_index_and_reference_resolution():
    # Create auxiliary DIEs with offsets
    aux_die_target = MockDIE("DW_TAG_base_type", offset=0x100)
    aux_cu = MockCU([aux_die_target])
    aux_info = MockDebugInfo([aux_cu])

    main_die = MockDIE(
        "DW_TAG_typedef",
        attributes={"DW_AT_type": SimpleNamespace(form="DW_FORM_GNU_ref_alt", value=0x100)},
    )
    main_cu = MockCU([main_die])
    main_info = MockDebugInfo([main_cu])

    main_elf = MockELF(main_info)
    aux_elf = MockELF(aux_info)

    debug_files = DebugInfoFiles(
        main_file=DebugFileInfo(main_elf, "/tmp/main.debug", False),
        auxiliary_file=DebugFileInfo(aux_elf, "/tmp/aux.debug", True),
    )

    index = build_auxiliary_debug_entry_index(debug_files)
    assert 0x100 in index

    # Now resolve reference from main die into auxiliary
    resolved = find_referenced_debug_entry(
        main_die, "DW_AT_type", debug_files, index
    )
    assert resolved is aux_die_target


def test_extract_name_from_inlined_and_string_tables():
    # Main info with no string sections
    info = MockDebugInfo([MockCU([])])
    elf = MockELF(info)
    debug_files = DebugInfoFiles(
        main_file=DebugFileInfo(elf, "/tmp/main", False), auxiliary_file=None
    )

    # Direct python string value
    attr = SimpleNamespace(form="DW_FORM_string", value="DirectName")
    assert extract_name_from_debug_info(attr, debug_files) == "DirectName"

    # Bytes value (inlined)
    attr_b = SimpleNamespace(form="DW_FORM_string", value=b"BytesName")
    assert extract_name_from_debug_info(attr_b, debug_files) == "BytesName"

    # Auxiliary string ref fallback when aux exists but section missing
    aux_info = MockDebugInfo([MockCU([])])
    aux_elf = MockELF(aux_info)
    debug_files2 = DebugInfoFiles(
        main_file=DebugFileInfo(elf, "/tmp/main", False),
        auxiliary_file=DebugFileInfo(aux_elf, "/tmp/aux", True),
    )
    attr_alt = SimpleNamespace(form="DW_FORM_GNU_strp_alt", value=0x10)
    # Section missing returns placeholder per implementation path
    assert extract_name_from_debug_info(attr_alt, debug_files2) in (None, "<auxiliary-string>")