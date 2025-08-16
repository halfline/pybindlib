"""
ELF and DWARF debug information handling for pybindlib.

This module provides the core functionality for extracting and processing debug
information from ELF files. It handles the complex task of:
- Locating and loading debug files
- Parsing DWARF debug information
- Extracting structure and type definitions
- Resolving type references across multiple files
- Handling auxiliary debug files

The module is designed to be robust against:
- Missing or incomplete debug information
- Split debug files
- Cross-file type references
- Name conflicts and collisions
- Platform-specific variations
"""

# Standard library imports
import os

# Third-party imports
from elftools.dwarf.die import DIE
from elftools.elf.elffile import ELFFile

# Local imports
from .identifiers import create_safe_python_identifier, is_invalid_identifier
from .logging import logger
from .progress import ProgressIndicator

__all__ = [
    "DebugFileInfo",
    "DebugInfoFiles",
    "TypeInfo",
    "StructMember",
    "QualityScore",
    "TypedefInfo",
    "StructureDefinition",
    "calculate_type_byte_size",
    "collect_all_structures_and_typedefs",
    "collect_and_merge_structure_info",
    "build_structure_name_mapping",
    "extract_name_from_debug_info",
    "MAX_FUNCTION_NAME_LENGTH",
    "find_referenced_debug_entry",
    "build_auxiliary_debug_entry_index",
]

# Constants
MAX_DISPLAY_NAME_LENGTH = 40
MAX_FUNCTION_NAME_LENGTH = 100

# Basic type mapping from C to ctypes
BASIC_CTYPE_MAPPING = {
    ("char", 1): "c_char",
    ("signed char", 1): "c_byte",
    ("unsigned char", 1): "c_ubyte",
    ("short", 2): "c_short",
    ("unsigned short", 2): "c_ushort",
    ("int", 4): "c_int",
    ("unsigned int", 4): "c_uint",
    ("long", 8): "c_long",
    ("unsigned long", 8): "c_ulong",
    ("long long", 8): "c_longlong",
    ("unsigned long long", 8): "c_ulonglong",
    ("float", 4): "c_float",
    ("double", 8): "c_double",
    ("long double", 16): "c_longdouble",
    ("bool", 1): "c_bool",
    ("_Bool", 1): "c_bool",
}


class DebugFileInfo:
    """Container for debug file information."""

    def __init__(
        self, debug_file: ELFFile, file_path: str, is_auxiliary: bool = False
    ):
        self.debug_file = debug_file
        self.file_path = file_path
        self.is_auxiliary = is_auxiliary
        self._debug_info = None

    @property
    def debug_info(self):
        """Get DWARF debug info, caching the result."""
        if self._debug_info is None:
            self._debug_info = self.debug_file.get_dwarf_info()
        return self._debug_info


class DebugInfoFiles:
    """Container for main and auxiliary debug files."""

    def __init__(
        self,
        main_file: DebugFileInfo | None = None,
        auxiliary_file: DebugFileInfo | None = None,
    ):
        self.main_file = main_file
        self.auxiliary_file = auxiliary_file

    def all_files(self) -> list[DebugFileInfo]:
        """Get list of all debug files."""
        files = []
        if self.main_file:
            files.append(self.main_file)
        if self.auxiliary_file:
            files.append(self.auxiliary_file)
        return files

    def has_auxiliary(self) -> bool:
        """Check if auxiliary debug file is present."""
        return self.auxiliary_file is not None

    def count(self) -> int:
        """Get total number of debug files."""
        return len(self.all_files())

    def __iter__(self):
        """Iterate over all debug files."""
        yield from self.all_files()


class TypeInfo:
    """Information about a converted DWARF type."""

    def __init__(
        self,
        ctypes_expression: str,
        size_bytes: int | None,
        description: str,
        struct_base_name: str | None = None,
    ):
        self.ctypes_expression = ctypes_expression
        self.size_bytes = size_bytes
        self.description = description
        self.struct_base_name = struct_base_name


class StructMember:
    """Information about a structure member."""

    def __init__(
        self, offset: int, name: str, ctypes_expression: str, description: str
    ):
        self.offset = offset
        self.name = name
        self.ctypes_expression = ctypes_expression
        self.description = description


class QualityScore:
    """Score for ranking type representations."""

    def __init__(self, base_score: int, size_score: int):
        self.base_score = base_score
        self.size_score = size_score
        self.total = (base_score, size_score)  # For comparison compatibility

    def __gt__(self, other):
        return self.total > other.total

    def __eq__(self, other):
        return self.total == other.total


class TypedefInfo:
    """Information about a typedef."""

    def __init__(
        self, representation: str, quality_score: QualityScore, description: str
    ):
        self.representation = representation
        self.quality_score = quality_score
        self.description = description


class StructureDefinition:
    """
    Represents a C structure/class/union with all its members.

    This class holds all the information we've extracted about a structure
    from the debug information, including its name, size, and all member fields
    with their types and offsets.

    Attributes:
        name: The original C structure name
        size: Size of the structure in bytes
        members: List of StructMember objects
    """

    def __init__(self, name: str, size: int):
        self.name = name
        self.size = size
        self.members: list[StructMember] = []


def calculate_type_byte_size(
    type_entry: DIE,
    debug_files: DebugInfoFiles,
    auxiliary_index: dict[int, object],
) -> int | None:
    """
    Calculate the size in bytes of a debug type entry.

    This function handles the complex task of determining type sizes from debug
    information. This is crucial for generating correct ctypes structures as we
    need to know how much space each field takes to calculate offsets and padding.

    The function handles various special cases:
    - Platform-specific pointer sizes
    - Array dimensions and element counts
    - Type modifiers (const, volatile, etc.)
    - Typedefs and type aliases
    - Cross-file type references

    Args:
        type_entry: The debug type entry
        debug_files: Container for all debug file information
        auxiliary_index: Index of auxiliary entries

    Returns:
        Size in bytes, or None if unknown
    """
    if type_entry is None:
        return None

    # Check for explicit size attribute
    byte_size_attr = type_entry.attributes.get("DW_AT_byte_size")
    if byte_size_attr and isinstance(byte_size_attr.value, int):
        return int(byte_size_attr.value)

    tag = type_entry.tag

    # For type modifiers, get size of underlying type
    if tag in (
        "DW_TAG_const_type",
        "DW_TAG_volatile_type",
        "DW_TAG_restrict_type",
        "DW_TAG_typedef",
    ):
        base_type = find_referenced_debug_entry(
            type_entry, "DW_AT_type", debug_files, auxiliary_index
        )
        return calculate_type_byte_size(base_type, debug_files, auxiliary_index)

    # Pointers have platform-specific size
    if tag == "DW_TAG_pointer_type":
        try:
            # Use main debug info to get address size
            main_debug_info = debug_files.main_file.debug_info
            return int(
                getattr(
                    type_entry.cu,
                    "address_size",
                    getattr(main_debug_info.config, "address_size", 8),
                )
            )
        except Exception:
            return 8

    # Arrays: element size × element count
    if tag == "DW_TAG_array_type":
        element_type = find_referenced_debug_entry(
            type_entry, "DW_AT_type", debug_files, auxiliary_index
        )
        element_size = calculate_type_byte_size(
            element_type, debug_files, auxiliary_index
        )
        if element_size is None:
            return None

        total_elements = 1
        for child in type_entry.iter_children():
            if child.tag == "DW_TAG_subrange_type":
                # Try to get element count directly
                count_attr = child.attributes.get("DW_AT_count")
                if count_attr and isinstance(count_attr.value, int):
                    total_elements *= int(count_attr.value)
                else:
                    # Calculate from bounds
                    upper_bound_attr = child.attributes.get("DW_AT_upper_bound")
                    lower_bound_attr = child.attributes.get("DW_AT_lower_bound")
                    if upper_bound_attr and isinstance(
                        upper_bound_attr.value, int
                    ):
                        lower_bound = (
                            int(lower_bound_attr.value)
                            if (
                                lower_bound_attr
                                and isinstance(lower_bound_attr.value, int)
                            )
                            else 0
                        )
                        total_elements *= (
                            int(upper_bound_attr.value) - lower_bound + 1
                        )

        return element_size * max(total_elements, 1)

    return None


def collect_and_merge_structure_info(
    entry: DIE,
    debug_files: DebugInfoFiles,
    auxiliary_index: dict[int, object],
    structures_output: dict[tuple[str, int], StructureDefinition],
    progress_callback=None,
) -> None:
    """
    Process a structure/class/union debug entry and collect its information.

    This function examines a debug entry representing a C structure and extracts
    all relevant information. It handles the complex case where we might see the
    same structure multiple times with different member information (due to how
    debug info is organized) by merging and choosing the best available information.

    The function:
    - Validates structure names and sizes
    - Merges duplicate structure definitions
    - Ranks member type quality to choose best representation
    - Handles unions vs structs differently
    - Preserves member order for proper layout
    - Tracks progress for user feedback

    Args:
        entry: The debug structure entry
        debug_files: Container for all debug file information
        auxiliary_index: Index of auxiliary entries
        structures_output: Dictionary to store collected structures
        progress_callback: Optional callback to update progress display
    """
    # Extract structure name and validate it
    raw_name = extract_name_from_debug_info(
        entry.attributes.get("DW_AT_name"), debug_files
    )
    if not raw_name or is_invalid_identifier(raw_name):
        return

    # Update progress with current struct name
    if progress_callback:
        # Truncate long names for display
        display_name = (
            raw_name
            if len(raw_name) <= MAX_DISPLAY_NAME_LENGTH
            else raw_name[:37] + "..."
        )
        progress_callback(f"struct {display_name}")

    # Get structure size
    byte_size_attr = entry.attributes.get("DW_AT_byte_size")
    if (
        not byte_size_attr
        or not isinstance(byte_size_attr.value, int)
        or byte_size_attr.value <= 0
    ):
        return

    structure_size = int(byte_size_attr.value)
    structure_key = (raw_name, structure_size)
    structure_def = structures_output.setdefault(
        structure_key, StructureDefinition(name=raw_name, size=structure_size)
    )

    def rank_ctypes_quality(ctypes_expr: str, size_hint) -> QualityScore:
        """
        Rank the quality of a ctypes expression for choosing the best representation.

        When we have multiple possible representations for the same field,
        we prefer more specific and accurate types over generic ones.

        Returns:
            QualityScore where higher values indicate better quality
        """
        if ctypes_expr == "c_void_p":
            base_score = 0
        elif ctypes_expr.startswith("(c_ubyte * "):
            base_score = 1
        elif ctypes_expr.startswith("@STRUCTREF:"):
            base_score = 2
        elif ctypes_expr.startswith(
            ("c_int", "c_uint", "c_bool", "c_float", "c_double")
        ):
            base_score = 3
        elif ctypes_expr.startswith("(") and "*" in ctypes_expr:
            base_score = 4
        else:
            base_score = 2

        size_score = 1 if (size_hint is not None) else 0
        return QualityScore(base_score=base_score, size_score=size_score)

    is_union = entry.tag == "DW_TAG_union_type"
    candidate_members = {}

    # Start with existing members (if any)
    if is_union:
        # In unions, members can have the same offset but different names
        for member in structure_def.members:
            key = (member.offset, member.name)
            candidate_members[key] = {
                "offset": member.offset,
                "name": member.name,
                "ctypes_expression": member.ctypes_expression,
                "size_hint": None,
                "description": member.description,
                "quality": rank_ctypes_quality(member.ctypes_expression, None),
            }
    else:
        # In structs, each offset should have only one member
        for member in structure_def.members:
            candidate_members[member.offset] = {
                "offset": member.offset,
                "name": member.name,
                "ctypes_expression": member.ctypes_expression,
                "size_hint": None,
                "description": member.description,
                "quality": rank_ctypes_quality(member.ctypes_expression, None),
            }

    # Process all member entries in this DWARF entry
    for child in entry.iter_children():
        if child.tag != "DW_TAG_member":
            continue

        member_name = extract_name_from_debug_info(
            child.attributes.get("DW_AT_name"), debug_files
        )
        if not member_name or is_invalid_identifier(member_name):
            continue

        member_offset = parse_struct_member_offset(child)
        if member_offset is None:
            continue

        # Get type information for this member
        member_type_entry = find_referenced_debug_entry(
            child, "DW_AT_type", debug_files, auxiliary_index
        )
        type_info = convert_dwarf_type_to_ctypes(
            member_type_entry, debug_files, auxiliary_index
        )
        quality_score = rank_ctypes_quality(
            type_info.ctypes_expression, type_info.size_bytes
        )

        new_member_info = {
            "offset": member_offset,
            "name": member_name,
            "ctypes_expression": type_info.ctypes_expression,
            "size_hint": type_info.size_bytes,
            "description": type_info.description,
            "quality": quality_score,
        }

        if is_union:
            # Union members: key by (offset, name) since multiple members can share offsets
            member_key = (member_offset, member_name)
            existing_member = candidate_members.get(member_key)
            if (
                existing_member is None
                or quality_score > existing_member["quality"]
            ):
                candidate_members[member_key] = new_member_info
            elif quality_score == existing_member["quality"] and len(
                member_name
            ) > len(existing_member["name"]):
                # If quality is equal, prefer longer names (often more descriptive)
                candidate_members[member_key] = new_member_info
        else:
            # Struct members: key by offset only
            existing_member = candidate_members.get(member_offset)
            if (
                existing_member is None
                or quality_score > existing_member["quality"]
            ):
                candidate_members[member_offset] = new_member_info
            elif quality_score == existing_member["quality"] and len(
                member_name
            ) > len(existing_member["name"]):
                # If quality is equal, prefer longer names (often more descriptive)
                candidate_members[member_offset] = new_member_info

    # Convert best candidates back to StructMember objects
    structure_def.members = []
    if is_union:
        # Sort union members by name for stable output
        sorted_members = sorted(
            candidate_members.values(), key=lambda m: m["name"]
        )
    else:
        # Sort struct members by offset for proper layout
        sorted_members = sorted(
            candidate_members.values(), key=lambda m: m["offset"]
        )

    for member_info in sorted_members:
        structure_def.members.append(
            StructMember(
                offset=member_info["offset"],
                name=member_info["name"],
                ctypes_expression=member_info["ctypes_expression"],
                description=member_info["description"],
            )
        )


def collect_all_structures_and_typedefs(
    debug_files: DebugInfoFiles, skip_progress: bool = False
) -> tuple[dict[tuple[str, int], StructureDefinition], dict[str, TypedefInfo]]:
    """
    Collect all structure and typedef information from debug data.

    This is the main entry point for gathering type information. It processes
    all debug files to build a complete picture of all structures and type
    aliases defined in the library.

    The function handles several complex cases:
    - Multiple debug files (main + auxiliary)
    - Cross-file type references
    - Name conflicts and collisions
    - Incomplete or partial information
    - Progress tracking for large files

    Args:
        debug_files: Container for all debug file information
        skip_progress: If True, disable progress indicators

    Returns:
        Tuple of (structures_dict, typedefs_dict) containing all collected information
    """
    logger.debug("Starting structure and typedef collection")
    structures: dict[tuple[str, int], StructureDefinition] = {}
    typedefs: dict[str, TypedefInfo] = {}
    auxiliary_entry_index = build_auxiliary_debug_entry_index(debug_files)

    if auxiliary_entry_index:
        logger.debug(
            f"Built auxiliary entry index with {len(auxiliary_entry_index)} entries"
        )

    # Set up progress indicator
    progress = None
    if not skip_progress:
        progress = ProgressIndicator("Analyzing structures")
        progress.start()

    # Collect structures from all debug files
    structure_count = 0
    processed_count = 0

    for debug_file_info in debug_files:
        file_type = "main" if not debug_file_info.is_auxiliary else "auxiliary"
        logger.debug(
            f"Processing {file_type} debug file: {debug_file_info.file_path}"
        )

        compilation_units = 0
        for compilation_unit in debug_file_info.debug_info.iter_CUs():
            compilation_units += 1
            for entry in compilation_unit.iter_DIEs():
                if entry.tag in (
                    "DW_TAG_structure_type",
                    "DW_TAG_class_type",
                    "DW_TAG_union_type",
                ):
                    collect_and_merge_structure_info(
                        entry,
                        debug_files,
                        auxiliary_entry_index,
                        structures,
                        progress_callback=progress.update if progress else None,
                    )
                    structure_count += 1
                    processed_count += 1

        logger.debug(
            f"Processed {compilation_units} compilation units from {file_type} file"
        )

    if progress:
        progress.finish(f"Found {len(structures)} unique structures")
    logger.debug(
        f"Found {len(structures)} unique structures after processing {structure_count} structure entries"
    )

    # Collect typedefs from all debug files
    typedef_progress = None
    if not skip_progress:
        typedef_progress = ProgressIndicator("Analyzing typedefs")
        typedef_progress.start()

    scan_debug_info_for_type_aliases(
        debug_files,
        auxiliary_entry_index,
        typedefs,
        progress_callback=typedef_progress.update if typedef_progress else None,
    )

    if typedef_progress:
        typedef_progress.finish(f"Found {len(typedefs)} typedefs")
    logger.debug(f"Collected {len(typedefs)} typedefs")

    return structures, typedefs


def read_library_name_from_elf(elf_file: ELFFile) -> str | None:
    """
    Extract the official library name (SONAME) from an ELF shared library.

    The SONAME is the "official" name that other programs use to link against
    this library. For example, libfreerdp.so.3 might have SONAME "libfreerdp.so.3"
    which is what we should use in our Python bindings to load the library.

    This is important because:
    - It ensures we use the correct library at runtime
    - It follows the system's library versioning scheme
    - It allows proper library upgrades
    - It maintains ABI compatibility

    Args:
        elf_file: The parsed ELF file object

    Returns:
        The SONAME string if found, None otherwise
    """
    # The .dynamic section contains runtime linking information
    dynamic_section = elf_file.get_section_by_name(".dynamic")
    if not dynamic_section:
        return None

    # Get the string table that contains the actual text values
    try:
        for tag in dynamic_section.iter_tags():
            if tag.entry.d_tag == "DT_SONAME":
                return tag.soname
    except Exception as error:
        logger.debug(f"Error reading SONAME: {error}")

    return None


def read_build_identifier(elf_file: ELFFile) -> str | None:
    """
    Extract the unique build identifier from an ELF file.

    The build ID is a unique hash that identifies this exact build of the library.
    It's used to locate matching debug information files and verify we're working
    with the correct version of a library.

    This is crucial because:
    - Debug info must match exactly to be useful
    - System debug files are organized by build ID
    - It prevents version mismatches
    - It ensures accurate type information

    Args:
        elf_file: The parsed ELF file object

    Returns:
        The build ID as a hex string if found, None otherwise
    """

    def extract_from_note_section(section):
        """Helper to extract build ID from a notes section."""
        if not section or not hasattr(section, "iter_notes"):
            return None

        try:
            for note in section.iter_notes():
                if note.n_type == "NT_GNU_BUILD_ID":
                    return note.n_desc
        except Exception as error:
            logger.debug(f"Error reading notes: {error}")
        return None

    # First try the dedicated build ID section
    build_id = extract_from_note_section(
        elf_file.get_section_by_name(".note.gnu.build-id")
    )
    if build_id:
        return build_id

    # Fall back to checking all note sections
    for section in elf_file.iter_sections():
        if section.name.startswith(".note"):
            build_id = extract_from_note_section(section)
            if build_id:
                return build_id

    return None


def locate_debug_file_by_debuglink(
    elf_path: str, elf_file: ELFFile
) -> str | None:
    """
    Find separate debug information file using GNU debuglink section.

    Many Linux distributions separate debug information from the main library
    to save space. The .gnu_debuglink section contains the name of the
    corresponding debug file and a checksum to verify it matches.

    The function searches in standard locations:
    1. Same directory as the library
    2. /usr/lib/debug + library path
    3. /usr/lib/debug

    Args:
        elf_path: Path to the main ELF file
        elf_file: The parsed ELF file object

    Returns:
        Path to the debug file if found, None otherwise
    """
    debuglink_section = elf_file.get_section_by_name(".gnu_debuglink")
    if not debuglink_section:
        return None

    try:
        section_data = debuglink_section.data()
        debug_filename = section_data.split(b"\0")[0].decode()

        # Search in standard debug file locations
        search_paths = [
            os.path.dirname(elf_path),
            "/usr/lib/debug" + os.path.dirname(elf_path),
            "/usr/lib/debug",
        ]

        for path in search_paths:
            debug_path = os.path.join(path, debug_filename)
            if os.path.exists(debug_path):
                return debug_path
    except Exception as error:
        logger.debug(f"Error reading debuglink section: {error}")

    return None


def locate_debug_file_by_build_id(build_id: str | None) -> str | None:
    """Locate debug file using build ID."""
    if not build_id:
        return None

    # Standard debug file locations for build ID
    search_paths = [
        "/usr/lib/debug/.build-id",
        "/var/cache/debuginfo/.build-id",
    ]

    for path in search_paths:
        debug_path = os.path.join(path, build_id[:2], build_id[2:] + ".debug")
        if os.path.exists(debug_path):
            return debug_path
    return None


def locate_fallback_debug_file(real_path: str) -> str | None:
    """Try fallback locations for debug file."""
    # Common debug file naming patterns
    patterns = [
        real_path + ".debug",
        os.path.join("/usr/lib/debug", real_path.lstrip("/")),
    ]

    for path in patterns:
        if os.path.exists(path):
            return path
    return None


def locate_alternate_debug_file(
    debug_path: str, debug_file: ELFFile
) -> str | None:
    """
    Find additional debug information referenced by .gnu_debugaltlink.

    Some debug information is stored in a separate "auxiliary" file to avoid
    duplication. This is common when multiple libraries share debug info.
    The .gnu_debugaltlink section points to this auxiliary file.

    Args:
        debug_path: Path to the main debug file
        debug_file: The parsed debug ELF file

    Returns:
        Path to the auxiliary debug file if found, None otherwise
    """
    debugalt_section = debug_file.get_section_by_name(".gnu_debugaltlink")
    if not debugalt_section:
        return None

    try:
        section_data = debugalt_section.data()
    except Exception:
        return None

    null_position = section_data.find(b"\x00")
    if null_position <= 0:
        return None

    auxiliary_filename = section_data[:null_position].decode(
        "utf-8", errors="replace"
    )
    debug_directory = os.path.dirname(os.path.abspath(debug_path))

    candidate_paths = [
        # Relative to debug file directory
        os.path.join(debug_directory, auxiliary_filename),
        # System debug directory
        os.path.join("/usr/lib/debug", auxiliary_filename.lstrip("/")),
    ]

    for path in candidate_paths:
        if os.path.exists(path):
            return path

    return None


def get_exported_function_names(elf_file: ELFFile) -> list[str]:
    """
    Extract names of exported functions from an ELF file.

    This looks at the symbol table to find all global functions that are
    exported from the library and can be called by other programs.

    Args:
        elf_file: The parsed ELF file object

    Returns:
        List of exported function names
    """

    def collect_from_section(sec, out: set[str]):
        """Helper to collect function names from a symbol table section."""
        if not sec or not hasattr(sec, "iter_symbols"):
            return

        try:
            for sym in sec.iter_symbols():
                if (
                    sym.entry.st_info.type == "STT_FUNC"
                    and sym.entry.st_info.bind == "STB_GLOBAL"
                ):
                    out.add(sym.name)
        except Exception as error:
            logger.debug(f"Error reading symbols: {error}")

    exported = set()

    # Check both .symtab and .dynsym sections
    collect_from_section(elf_file.get_section_by_name(".symtab"), exported)
    collect_from_section(elf_file.get_section_by_name(".dynsym"), exported)

    return sorted(exported)


def read_string_from_dwarf_section(section, offset: int) -> str | None:
    """Read a string from a DWARF section at the given offset."""
    try:
        data = section.get_string(offset)
        if data is None:
            return None
        if isinstance(data, (bytes, bytearray)):
            return bytes(data).decode("utf-8", errors="replace")
        # Some versions may already return str
        return str(data)
    except Exception:
        return None


def extract_name_from_debug_info(
    attribute, debug_files: DebugInfoFiles
) -> str | None:
    """
    Extract a string name from debug information attribute value.

    Debug information stores names in various formats - sometimes inline, sometimes as
    offsets into string tables, sometimes in alternate files. This function
    handles all these cases to extract the actual name string.

    Args:
        attribute: The debug attribute containing the name
        debug_files: Container for all debug file information

    Returns:
        The extracted name string, or None if not found
    """
    if attribute is None:
        return None

    # Get main and auxiliary debug files
    main_debug_info = debug_files.main_file.debug_info
    main_debug_file = debug_files.main_file.debug_file
    auxiliary_debug_file = (
        debug_files.auxiliary_file.debug_file
        if debug_files.auxiliary_file
        else None
    )

    form, value = attribute.form, attribute.value

    # If already a Python string, return it directly
    if isinstance(value, str):
        return value

    # String stored directly in the attribute
    if form == "DW_FORM_string" and isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")

    # String stored in main .debug_str section
    if form == "DW_FORM_strp" and isinstance(value, int) and main_debug_info:
        string_section = getattr(main_debug_info, "debug_str_sec", None)
        if string_section is not None:
            return read_string_from_dwarf_section(string_section, value)

    # String stored in .debug_line_str section
    if (
        form == "DW_FORM_line_strp"
        and isinstance(value, int)
        and main_debug_info
    ):
        line_string_section = getattr(
            main_debug_info, "debug_line_str_sec", None
        )
        if line_string_section is not None:
            return read_string_from_dwarf_section(line_string_section, value)

    # String stored in auxiliary debug file
    if (
        form in ("DW_FORM_GNU_strp_alt", "DW_FORM_GNU_line_strp_alt")
        and auxiliary_debug_file is not None
    ):
        section_name = (
            ".debug_str"
            if form == "DW_FORM_GNU_strp_alt"
            else ".debug_line_str"
        )
        section = auxiliary_debug_file.get_section_by_name(section_name)
        if section is not None and isinstance(value, int):
            return read_string_from_dwarf_section(section, value)
        return "<auxiliary-string>"

    # Fallback for byte data
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")

    return None


def build_auxiliary_debug_entry_index(
    debug_files: DebugInfoFiles,
) -> dict[int, object]:
    """
    Build an index of all debug entries in the auxiliary debug file.

    When debug information is split across multiple files, we need to be able
    to quickly look up entries by their offset. This builds that lookup table
    for the auxiliary debug file if present.

    Args:
        debug_files: Container for all debug file information

    Returns:
        Dictionary mapping offsets to debug entries from auxiliary file
    """
    entry_index: dict[int, object] = {}

    if debug_files.auxiliary_file:
        for (
            compilation_unit
        ) in debug_files.auxiliary_file.debug_info.iter_CUs():
            for entry in compilation_unit.iter_DIEs():
                entry_index[getattr(entry, "offset", -1)] = entry

    return entry_index


def find_referenced_debug_entry(
    entry: DIE,
    attribute_name: str,
    debug_files: DebugInfoFiles,
    auxiliary_index: dict[int, object],
) -> DIE | None:
    """
    Follow a reference from one debug entry to another.

    Debug entries often reference other entries (like a struct member
    referencing its type). This function resolves those references,
    handling both local and auxiliary file references.

    Args:
        entry: The debug entry containing the reference
        attribute_name: Name of the attribute that contains the reference
        debug_files: Container for all debug file information
        auxiliary_index: Index of auxiliary debug entries

    Returns:
        The referenced debug entry, or None if not found
    """
    attribute = entry.attributes.get(attribute_name)
    if attribute is None:
        return None

    form, value = attribute.form, attribute.value

    # Standard reference within same debug file
    if form.startswith("DW_FORM_ref") and form != "DW_FORM_GNU_ref_alt":
        try:
            target = entry.get_DIE_from_attribute(attribute_name)
            return target
        except NotImplementedError:
            pass

    # Reference to auxiliary debug file
    if form == "DW_FORM_GNU_ref_alt" and isinstance(value, int):
        return auxiliary_index.get(value)

    return None


def remove_type_qualifiers_and_typedefs(
    type_entry: DIE,
    debug_files: DebugInfoFiles,
    auxiliary_index: dict[int, object],
) -> DIE | None:
    """Follow typedef and qualifier chains to find the underlying type."""
    # Implementation depends on specific needs
    return None


def convert_dwarf_type_to_ctypes(
    type_entry: DIE,
    debug_files: DebugInfoFiles,
    auxiliary_index: dict[int, object],
) -> TypeInfo:
    """
    Convert a debug type entry into ctypes equivalent information.

    This is the core function that maps C types to Python ctypes. It handles
    basic types, structures, pointers, arrays, etc. Returns comprehensive
    information needed to generate the Python binding.

    Args:
        type_entry: The debug type entry to convert
        debug_files: Container for all debug file information
        auxiliary_index: Index of auxiliary entries

    Returns:
        TypeInfo object containing ctypes_expression, size_bytes, description,
        and struct_base_name (if applicable)
    """
    if type_entry is None:
        return TypeInfo(
            ctypes_expression="c_void_p",
            size_bytes=8,
            description="unresolved type",
            struct_base_name=None,
        )

    # First, check if this is a structure after peeling qualifiers
    peeled_type = remove_type_qualifiers_and_typedefs(
        type_entry, debug_files, auxiliary_index
    )
    if peeled_type is not None and peeled_type.tag in (
        "DW_TAG_structure_type",
        "DW_TAG_class_type",
        "DW_TAG_union_type",
    ):
        struct_name = (
            extract_name_from_debug_info(
                peeled_type.attributes.get("DW_AT_name"), debug_files
            )
            or ""
        )
        struct_size = calculate_type_byte_size(
            peeled_type, debug_files, auxiliary_index
        )

        if (
            struct_name
            and not is_invalid_identifier(struct_name)
            and struct_size
        ):
            base_name = create_safe_python_identifier(struct_name)
            # Use special marker for struct references that will be resolved later
            return TypeInfo(
                ctypes_expression=f"@STRUCTREF:{base_name}:{int(struct_size)}",
                size_bytes=struct_size,
                description=f"{peeled_type.tag.replace('DW_TAG_', '')} {struct_name}",
                struct_base_name=base_name,
            )

    # Handle the original type entry
    tag = type_entry.tag
    type_name = (
        extract_name_from_debug_info(
            type_entry.attributes.get("DW_AT_name"), debug_files
        )
        or ""
    )
    type_size = calculate_type_byte_size(
        type_entry, debug_files, auxiliary_index
    )
    description = type_name or tag.replace("DW_TAG_", "")

    # Basic types (int, float, etc.)
    if tag == "DW_TAG_base_type" and type_size is not None:
        ctypes_equivalent = BASIC_CTYPE_MAPPING.get((type_name, type_size))
        if ctypes_equivalent:
            return TypeInfo(
                ctypes_expression=ctypes_equivalent,
                size_bytes=type_size,
                description=f"{type_name}",
                struct_base_name=None,
            )

        # Fallback mappings for basic types
        if "unsigned" in type_name:
            return TypeInfo(
                ctypes_expression=f"c_uint{type_size * 8}",
                size_bytes=type_size,
                description=f"{type_name}",
                struct_base_name=None,
            )
        if any(
            keyword in type_name
            for keyword in ("signed", "char", "short", "int", "long")
        ):
            return TypeInfo(
                ctypes_expression=f"c_int{min(type_size, 8) * 8}",
                size_bytes=type_size,
                description=f"{type_name}",
                struct_base_name=None,
            )
        if type_name in ("float", "double"):
            return TypeInfo(
                ctypes_expression=f"c_{'float' if type_size == 4 else 'double'}",
                size_bytes=type_size,
                description=f"{type_name}",
                struct_base_name=None,
            )

    # Pointer types
    if tag == "DW_TAG_pointer_type":
        return TypeInfo(
            ctypes_expression="c_void_p",
            size_bytes=type_size or 8,
            description=f"pointer to {description}",
            struct_base_name=None,
        )

    # Type qualifiers and typedefs - follow the chain
    if tag in (
        "DW_TAG_typedef",
        "DW_TAG_const_type",
        "DW_TAG_volatile_type",
        "DW_TAG_restrict_type",
    ):
        base_type = find_referenced_debug_entry(
            type_entry, "DW_AT_type", debug_files, auxiliary_index
        )
        return convert_dwarf_type_to_ctypes(
            base_type, debug_files, auxiliary_index
        )

    # Array types
    if tag == "DW_TAG_array_type":
        element_type = find_referenced_debug_entry(
            type_entry, "DW_AT_type", debug_files, auxiliary_index
        )
        element_info = convert_dwarf_type_to_ctypes(
            element_type, debug_files, auxiliary_index
        )

        total_count = 1
        for child in type_entry.iter_children():
            if child.tag == "DW_TAG_subrange_type":
                count_attr = child.attributes.get("DW_AT_count")
                if count_attr and isinstance(count_attr.value, int):
                    total_count *= int(count_attr.value)
                else:
                    upper_bound_attr = child.attributes.get("DW_AT_upper_bound")
                    lower_bound_attr = child.attributes.get("DW_AT_lower_bound")
                    if upper_bound_attr and isinstance(
                        upper_bound_attr.value, int
                    ):
                        lower_bound = (
                            int(lower_bound_attr.value)
                            if (
                                lower_bound_attr
                                and isinstance(lower_bound_attr.value, int)
                            )
                            else 0
                        )
                        total_count *= (
                            int(upper_bound_attr.value) - lower_bound + 1
                        )

        if element_info.size_bytes is not None:
            return TypeInfo(
                ctypes_expression=f"({element_info.ctypes_expression} * {total_count})",
                size_bytes=(element_info.size_bytes or 1) * total_count,
                description=f"array of {total_count} × {element_info.description or 'unknown'}",
                struct_base_name=None,
            )

        # Fallback if we can't determine element size
        total_size = calculate_type_byte_size(
            type_entry, debug_files, auxiliary_index
        )
        if total_size:
            return TypeInfo(
                ctypes_expression=f"(c_ubyte * {total_size})",
                size_bytes=total_size,
                description=f"array of {description}",
                struct_base_name=None,
            )

    # Unknown or complex types - represent as byte array if we know the size
    if type_size is not None:
        return TypeInfo(
            ctypes_expression=f"(c_ubyte * {type_size})",
            size_bytes=type_size,
            description=f"{tag.replace('DW_TAG_', '')} {description}",
            struct_base_name=None,
        )

    # Complete fallback
    return TypeInfo(
        ctypes_expression="c_void_p",
        size_bytes=8,
        description=f"unresolved {description}",
        struct_base_name=None,
    )


def parse_struct_member_offset(member_entry: DIE) -> int | None:
    """Parse structure member offset from debug info."""
    location_attr = member_entry.attributes.get("DW_AT_data_member_location")
    if not location_attr:
        return None

    # Simple integer offset
    if isinstance(location_attr.value, int):
        return int(location_attr.value)

    # DWARF expression (commonly used for offsets)
    if location_attr.form.endswith("exprloc") and isinstance(
        location_attr.value, (bytes, bytearray)
    ):
        expression_data = bytes(location_attr.value)
        if expression_data and expression_data[0] == 0x23:  # DW_OP_plus_uconst
            # Decode ULEB128 encoded value
            value = 0
            shift = 0
            for byte in expression_data[1:]:
                value |= (byte & 0x7F) << shift
                if (byte & 0x80) == 0:
                    break
                shift += 7
            return value

    return None


def rank_ctypes_quality(ctypes_expr: str, size_hint) -> QualityScore:
    """Rank the quality of a ctypes type representation."""
    # Implementation depends on specific needs
    return QualityScore()


def scan_debug_info_for_type_aliases(
    debug_files: DebugInfoFiles,
    auxiliary_index: dict[int, object],
    typedefs_output: dict[str, TypedefInfo],
    progress_callback=None,
) -> None:
    """
    Scan debug information for typedef declarations.

    Typedefs create aliases for existing types. We collect these to generate
    equivalent Python typedefs. This helps maintain the same API that
    C code would use.

    Args:
        debug_files: Container for all debug file information
        auxiliary_index: Index of auxiliary entries
        typedefs_output: Dictionary to store collected typedef information
        progress_callback: Optional callback to update progress display
    """

    def rank_typedef_quality(ctypes_expr: str, size_hint) -> QualityScore:
        """Rank the quality of a typedef representation."""
        if ctypes_expr == "c_void_p":
            base_score = 0
        elif ctypes_expr.startswith("(c_ubyte * "):
            base_score = 1
        elif ctypes_expr.startswith("@STRUCTREF:"):
            base_score = 2
        elif ctypes_expr.startswith(
            ("c_int", "c_uint", "c_bool", "c_float", "c_double")
        ):
            base_score = 3
        elif ctypes_expr.startswith("(") and "*" in ctypes_expr:
            base_score = 4
        else:
            base_score = 2

        size_score = 1 if size_hint is not None else 0
        return QualityScore(base_score=base_score, size_score=size_score)

    # Process all debug files for typedefs
    typedef_count = 0
    for debug_file_info in debug_files:
        for compilation_unit in debug_file_info.debug_info.iter_CUs():
            for entry in compilation_unit.iter_DIEs():
                if entry.tag != "DW_TAG_typedef":
                    continue

                # Get the typedef name
                typedef_name = extract_name_from_debug_info(
                    entry.attributes.get("DW_AT_name"), debug_files
                )
                if not typedef_name or is_invalid_identifier(typedef_name):
                    continue

                # Update progress with current typedef
                typedef_count += 1
                if progress_callback and typedef_count % 5 == 0:
                    display_name = (
                        typedef_name
                        if len(typedef_name) <= MAX_DISPLAY_NAME_LENGTH
                        else typedef_name[:37] + "..."
                    )
                    progress_callback(f"typedef {display_name}")

                # Get the underlying type
                base_type_entry = find_referenced_debug_entry(
                    entry, "DW_AT_type", debug_files, auxiliary_index
                )
                peeled_type = remove_type_qualifiers_and_typedefs(
                    base_type_entry, debug_files, auxiliary_index
                )

                # Check if this typedef points to a structure
                prefer_struct_reference = False
                target_struct_base = None
                target_struct_size = None

                if peeled_type is not None and peeled_type.tag in (
                    "DW_TAG_structure_type",
                    "DW_TAG_class_type",
                    "DW_TAG_union_type",
                ):
                    struct_name = extract_name_from_debug_info(
                        peeled_type.attributes.get("DW_AT_name"), debug_files
                    )
                    target_struct_size = calculate_type_byte_size(
                        peeled_type, debug_files, auxiliary_index
                    )
                    if (
                        struct_name
                        and not is_invalid_identifier(struct_name)
                        and target_struct_size
                    ):
                        target_struct_base = create_safe_python_identifier(
                            struct_name
                        )
                        prefer_struct_reference = True

                # Convert the base type to ctypes
                type_info = convert_dwarf_type_to_ctypes(
                    base_type_entry, debug_files, auxiliary_index
                )
                quality_score = rank_typedef_quality(
                    type_info.ctypes_expression, type_info.size_bytes
                )

                # Decide on the representation
                if prefer_struct_reference and target_struct_base:
                    representation = f"STRUCT::{target_struct_base}:{int(target_struct_size or 0)}"
                else:
                    representation = type_info.ctypes_expression

                # Update our collection with the best representation
                existing_typedef = typedefs_output.get(typedef_name)
                if (
                    existing_typedef is None
                    or quality_score > existing_typedef.quality_score
                ):
                    typedefs_output[typedef_name] = TypedefInfo(
                        representation=representation,
                        quality_score=quality_score,
                        description=type_info.description,
                    )
                elif (
                    existing_typedef is not None
                    and quality_score == existing_typedef.quality_score
                ):
                    # If quality is equal, prefer struct references or longer representations
                    if representation.startswith(
                        "STRUCT::"
                    ) and not existing_typedef.representation.startswith(
                        "STRUCT::"
                    ):
                        typedefs_output[typedef_name] = TypedefInfo(
                            representation=representation,
                            quality_score=quality_score,
                            description=type_info.description,
                        )
                    elif len(representation) > len(
                        existing_typedef.representation
                    ):
                        typedefs_output[typedef_name] = TypedefInfo(
                            representation=representation,
                            quality_score=quality_score,
                            description=type_info.description,
                        )


def load_library_and_debug_info(
    input_path: str,
) -> tuple[DebugInfoFiles, str, str, str, list[str]]:
    """
    Load a shared library and locate its debug information.

    This function handles the complex process of loading an ELF file and
    finding all the associated debug information files. It tries multiple
    standard locations and methods to locate debug data.

    Args:
        input_path: Path to the shared library or debug file

    Returns:
        Tuple of (debug_files, library_name, debug_path, build_id, exported_functions)
        where debug_files is a DebugInfoFiles container
    """
    real_path = os.path.realpath(input_path)
    logger.debug(f"Resolved input path: {real_path}")

    # Read basic metadata from the original file
    with open(real_path, "rb") as file_handle:
        input_elf = ELFFile(file_handle)
        library_name = read_library_name_from_elf(
            input_elf
        ) or os.path.basename(real_path)
        build_id = read_build_identifier(input_elf)
        exported_functions = get_exported_function_names(input_elf)
        logger.debug(f"Library SONAME: {library_name}")
        logger.debug(f"Build ID: {build_id or 'none'}")
        logger.debug(f"Found {len(exported_functions)} exported functions")

    # Try to locate debug information file
    debug_file_path = None

    # Method 1: GNU debuglink section
    logger.debug("Searching for debug file using GNU debuglink...")
    with open(real_path, "rb") as file_handle:
        input_elf = ELFFile(file_handle)
        debug_file_path = locate_debug_file_by_debuglink(real_path, input_elf)
        if debug_file_path:
            logger.debug(f"Found debug file via debuglink: {debug_file_path}")

    # Method 2: Build ID based lookup
    if not debug_file_path and build_id:
        logger.debug("Searching for debug file using build ID...")
        debug_file_path = locate_debug_file_by_build_id(build_id)
        if debug_file_path:
            logger.debug(f"Found debug file via build ID: {debug_file_path}")

    # Method 3: Fallback location
    if not debug_file_path:
        logger.debug("Trying fallback debug file location...")
        debug_file_path = locate_fallback_debug_file(real_path)
        if debug_file_path:
            logger.debug(f"Found debug file via fallback: {debug_file_path}")

    # Method 4: Use original file as debug file
    if not debug_file_path:
        logger.debug("Using original file as debug file")
        debug_file_path = real_path

    # Load the debug file
    debug_file_handle = open(debug_file_path, "rb")
    debug_file = ELFFile(debug_file_handle)

    if not debug_file.has_dwarf_info():
        raise SystemExit(
            f"No DWARF debug information found in the library.\n"
            f"\n"
            f"  Input file:     {real_path}\n"
            f"  Library name:   {library_name}\n"
            f"  Debuginfo file: {debug_file_path}\n"
            f"  Build ID:       {build_id or 'none'}\n"
            f"\n"
            f"Debug information is required to generate ctypes bindings.\n"
            f"Try installing the corresponding debuginfo/dbgsym package for this library,\n"
            f"or compile the library with debug symbols (-g flag)."
        )

    logger.debug("Successfully loaded main debug information")
    main_file = DebugFileInfo(
        debug_file=debug_file, file_path=debug_file_path, is_auxiliary=False
    )

    # Try to locate auxiliary debug information
    auxiliary_file = None
    auxiliary_debug_path = locate_alternate_debug_file(
        debug_file_path, debug_file
    )

    if auxiliary_debug_path:
        # Resolve any relative path components
        auxiliary_debug_path = os.path.realpath(auxiliary_debug_path)
        logger.debug(f"Resolved auxiliary debug path: {auxiliary_debug_path}")

    if auxiliary_debug_path and os.path.exists(auxiliary_debug_path):
        logger.debug(f"Found auxiliary debug file: {auxiliary_debug_path}")
        try:
            auxiliary_file_handle = open(auxiliary_debug_path, "rb")
            auxiliary_debug_file = ELFFile(auxiliary_file_handle)
            if auxiliary_debug_file.has_dwarf_info():
                auxiliary_file = DebugFileInfo(
                    debug_file=auxiliary_debug_file,
                    file_path=auxiliary_debug_path,
                    is_auxiliary=True,
                )
                logger.debug("Successfully loaded auxiliary debug information")
        except Exception as caught_exception:
            logger.debug(
                f"Failed to load auxiliary debug file: {caught_exception}"
            )
    else:
        logger.debug("No auxiliary debug file found")

    debug_files = DebugInfoFiles(
        main_file=main_file, auxiliary_file=auxiliary_file
    )

    # Use debug file's build ID if available, otherwise original
    final_build_id = read_build_identifier(debug_file) or build_id

    return (
        debug_files,
        library_name,
        debug_file_path,
        final_build_id,
        exported_functions,
    )


def build_structure_name_mapping(
    structures: dict[tuple[str, int], StructureDefinition],
) -> dict[tuple[str, int], str]:
    """
    Build a mapping from C structure names to Python class names.

    When multiple structures have the same name but different sizes (which can
    happen with different versions or configurations), we need to create unique
    Python class names. This function handles that by adding size suffixes
    when necessary.

    Args:
        structures: Dictionary of all collected structures

    Returns:
        Dictionary mapping (c_name, size) tuples to Python class names
    """
    # Group structures by base name to detect conflicts
    base_name_to_sizes: dict[str, set] = {}
    for c_name, size in structures.keys():
        python_base_name = create_safe_python_identifier(c_name)
        base_name_to_sizes.setdefault(python_base_name, set()).add(size)

    # Create final mapping with size suffixes where needed
    name_mapping: dict[tuple[str, int], str] = {}
    for c_structure_name, size in structures.keys():
        python_base_name = create_safe_python_identifier(c_structure_name)
        if len(base_name_to_sizes[python_base_name]) == 1:
            # No conflict, use simple name
            final_python_name = python_base_name
        else:
            # Conflict exists, add size suffix
            final_python_name = f"{python_base_name}__{size}"
        name_mapping[(c_structure_name, size)] = final_python_name

    return name_mapping
