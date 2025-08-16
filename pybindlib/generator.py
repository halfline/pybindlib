"""
Python code generation for pybindlib.

This module handles the generation of Python ctypes bindings from the collected
debug information. It focuses on creating a clean, usable Python API that follows
best practices while maintaining compatibility with the original C library.

The generated code is structured into submodules to provide a clean namespace
and avoid naming conflicts:
- types: Contains structure and type definitions
- symbols: Contains exported function symbols
- constants: Contains macro definitions (optional)
"""

# Standard library imports
import os
import time

# Third-party imports
from colorama import Back, Fore, Style

# Local imports
from .debug_info import (
    MAX_FUNCTION_NAME_LENGTH,
    DebugInfoFiles,
    StructureDefinition,
    TypedefInfo,
    build_auxiliary_debug_entry_index,
    build_structure_name_mapping,
    extract_name_from_debug_info,
    find_referenced_debug_entry,
)
from .identifiers import create_safe_python_identifier
from .logging import logger
from .output import ANSI_COLOR_PATTERN, _has_colorama, print_stats


def generate_python_module(
    output_path: str,
    library_name: str,
    build_id: str | None,
    structures: dict[tuple[str, int], StructureDefinition],
    typedefs: dict[str, TypedefInfo],
    exported_functions: list[str],
    macros: dict[str, str] | None = None,
) -> None:
    """
    Generate a Python module with ctypes bindings.

    This function takes the collected structure and typedef information and
    generates a complete Python module with ctypes bindings. The module is
    structured into submodules to provide a clean namespace and avoid naming
    conflicts:

    - types: Contains structure and type definitions
    - symbols: Contains exported function symbols
    - constants: Contains macro definitions (optional)

    The generated module includes:
    - Proper error handling for library loading
    - Automatic fallback to full path if SONAME fails
    - Clean submodule organization
    - Helpful usage examples in docstrings
    - Type hints and docstrings for better IDE support

    Args:
        output_path: Path to write the output file
        library_name: Name of the library (SONAME)
        build_id: Optional build ID from the library
        structures: All collected structure information
        typedefs: All collected typedef information
        exported_functions: List of exported function names
        macros: Optional dictionary of macro definitions
    """
    module_name = os.path.splitext(os.path.basename(output_path))[0]

    with open(output_path, "w", encoding="utf-8") as output_file:
        # Write module header
        output_file.write(
            "# Auto-generated ctypes bindings for " + library_name + "\n"
        )
        output_file.write("#\n")
        output_file.write("# Library Information:\n")
        output_file.write("#   SONAME:      " + library_name + "\n")
        if build_id:
            output_file.write("#   Build ID:    " + build_id + "\n")
        source_path = os.path.realpath(library_name)
        output_file.write("#   Source File: " + source_path + "\n")
        output_file.write(
            "#   Generated:   " + time.strftime("%Y-%m-%d %H:%M:%S %Z") + "\n"
        )
        output_file.write("#\n")
        output_file.write(
            "# This module provides Python ctypes bindings for the C library structures,\n"
        )
        output_file.write("# types, and constants. Use it like this:\n")
        output_file.write("#\n")
        output_file.write("# Method 1 - Import specific items:\n")
        output_file.write(
            "#   from " + module_name + ".types import MyStruct\n"
        )
        output_file.write(
            "#   from " + module_name + ".symbols import my_function\n"
        )
        output_file.write(
            "#   from " + module_name + ".constants import BUFFER_SIZE\n"
        )
        output_file.write("#\n")
        output_file.write("#   # Create and use a structure\n")
        output_file.write("#   structure = MyStruct()\n")
        output_file.write("#   structure.field = BUFFER_SIZE\n")
        output_file.write("#   result = my_function(structure)\n")
        output_file.write("#\n")
        output_file.write("# Method 2 - Import whole module:\n")
        output_file.write("#   import " + module_name + "\n")
        output_file.write("#\n")
        output_file.write("#   # Access everything through the module\n")
        output_file.write(
            "#   structure = " + module_name + ".types.MyStruct()\n"
        )
        output_file.write(
            "#   structure.field = " + module_name + ".constants.BUFFER_SIZE\n"
        )
        output_file.write(
            "#   result = " + module_name + ".symbols.my_function(structure)\n"
        )
        output_file.write("#\n")

        # Write imports
        output_file.write("from ctypes import *\n")
        output_file.write("import sys\n\n")

        # Load library
        output_file.write(
            "# Load the shared library - try SONAME first, fall back to original path\n"
        )
        output_file.write("try:\n")
        output_file.write('    symbols = CDLL("' + library_name + '")\n')
        output_file.write("except OSError as error1:\n")
        output_file.write("    try:\n")
        output_file.write('        symbols = CDLL("' + source_path + '")\n')
        output_file.write("    except OSError as error2:\n")
        output_file.write(
            '        error_message = "Failed to load shared library. Tried:\\n"\n'
        )
        output_file.write(
            '        error_message += "  SONAME: " + library_name + " (error: " + str(error1) + ")\\n"\n'
        )
        output_file.write(
            '        error_message += "  Path:   " + source_path + " (error: " + str(error2) + ")\\n"\n'
        )
        output_file.write('        error_message += "\\n"\n')
        output_file.write(
            '        error_message += "Make sure the library is installed and accessible via LD_LIBRARY_PATH,\\n"\n'
        )
        output_file.write(
            '        error_message += "or that the full path exists and has proper permissions."\n'
        )
        output_file.write("        raise ImportError(error_message) from None\n\n")

        # Write type definitions
        output_file.write("class types:\n")
        output_file.write('    """\n')
        output_file.write(
            "    Container for all structure and type definitions from the library.\n"
        )
        output_file.write("\n")
        output_file.write(
            "    Each C structure, union, or class becomes a Python class inheriting from\n"
        )
        output_file.write(
            "    ctypes.Structure. All types include size information and field layouts\n"
        )
        output_file.write("    that match the original C definitions.\n")
        output_file.write('    """\n\n')
        output_file.write(
            "    # Forward declarations for all structure types\n\n"
        )
        output_file.write(
            "    # Field definitions (ordered by dependencies)\n\n"
        )

        # Write structures
        for (c_name, size), struct_def in structures.items():
            python_name = create_safe_python_identifier(c_name)
            output_file.write(f"    class {python_name}(Structure):\n")
            output_file.write("        pass\n\n")

        # Write typedefs
        output_file.write("    # Typedef aliases from C typedefs\n\n")
        for typedef_name, typedef_info in typedefs.items():
            python_name = create_safe_python_identifier(typedef_name)
            output_file.write(
                f"    class {python_name}({typedef_info.representation}):\n"
            )
            if typedef_info.description:
                output_file.write(f'        """{typedef_info.description}"""\n')
            output_file.write("        pass\n\n")

        # Write exported symbols
        output_file.write(
            "# Exported function names discovered from ELF analysis\n"
        )
        output_file.write("EXPORT_SYMBOLS = [\n")
        for name in exported_functions:
            output_file.write(f"    {repr(name)},\n")
        output_file.write("]\n\n")

        # Write constants if available
        if macros:
            output_file.write("# Constants\n")
            for name, value in macros.items():
                output_file.write(f"{name} = {value}\n")
            output_file.write("\n")

        # Enable submodule-style imports
        output_file.write(
            f"# Enable 'from {module_name}.types import StructName' and 'from {module_name}.symbols import function_name'\n"
        )
        output_file.write("import types as _types_module\n")
        output_file.write("import sys as _sys\n\n")

        # Create symbols submodule
        output_file.write(
            "# Create 'symbols' as a real submodule that forwards lookups to the CDLL and supports dir()\n"
        )
        output_file.write(
            f"_symbols_module = _types_module.ModuleType('{module_name}.symbols')\n\n"
        )
        output_file.write("def _symbols___getattr__(name):\n")
        output_file.write(
            "    # Forward attribute access to the underlying CDLL\n"
        )
        output_file.write("    return getattr(symbols, name)\n\n")
        output_file.write("def _symbols___dir__():\n")
        output_file.write("    # Present only exported names we baked in\n")
        output_file.write("    return sorted(EXPORT_SYMBOLS)\n\n")
        output_file.write(
            "_symbols_module.__getattr__ = _symbols___getattr__\n"
        )
        output_file.write("_symbols_module.__dir__ = _symbols___dir__\n\n")

        # Create types submodule
        output_file.write("# Create 'types' submodule\n")
        output_file.write(
            f"_types_submodule = _types_module.ModuleType('{module_name}.types')\n"
        )
        output_file.write("for _attr_name in dir(types):\n")
        output_file.write("    if not _attr_name.startswith('_'):\n")
        output_file.write(
            "        setattr(_types_submodule, _attr_name, getattr(types, _attr_name))\n\n"
        )

        # Create constants submodule if needed
        if macros:
            output_file.write("# Create 'constants' submodule\n")
            output_file.write(
                f"_constants_module = _types_module.ModuleType('{module_name}.constants')\n"
            )
            for name, value in macros.items():
                output_file.write(
                    f"setattr(_constants_module, {repr(name)}, {value})\n"
                )
            output_file.write("\n")

        # Register submodules
        output_file.write("# Register submodules\n")
        output_file.write(
            f"_sys.modules['{module_name}.types'] = _types_submodule\n"
        )
        output_file.write(
            f"_sys.modules['{module_name}.symbols'] = _symbols_module\n"
        )
        if macros:
            output_file.write(
                f"_sys.modules['{module_name}.constants'] = _constants_module\n"
            )
        output_file.write("\n")

        # Clean up temporary names
        output_file.write("# Clean up temporary names\n")
        output_file.write(
            "del _types_module, _sys, _symbols_module, _symbols___getattr__, _symbols___dir__, _types_submodule"
        )
        if macros:
            output_file.write(", _constants_module")
        output_file.write(", _attr_name\n\n")

        # Public API
        output_file.write("# Public API\n")
        if macros:
            output_file.write("__all__ = ['symbols', 'types', 'constants']\n")
        else:
            output_file.write("__all__ = ['symbols', 'types']\n")


def generate_constants_section(macros: dict[str, str], module_name: str) -> str:
    """
    Generate Python code for the constants section as a real submodule.

    This function creates a proper Python submodule for constants rather than
    just adding them to the global namespace. This provides better organization
    and avoids potential naming conflicts.

    The generated code:
    - Creates a real module object for proper import behavior
    - Filters out invalid identifiers and special names
    - Preserves the original macro values
    - Registers the module in sys.modules for proper import machinery

    Args:
        macros: Dictionary of macro names and values
        module_name: Name of the generated module for submodule registration

    Returns:
        String containing Python code defining constants submodule
    """
    if not macros:
        return ""

    lines: list[str] = []
    lines.append("\n# Create 'constants' submodule")
    lines.append(
        f"_constants_module = _types_module.ModuleType('{module_name}.constants')"
    )
    lines.append("")
    lines.append("# Constants extracted from header files")
    for macro_name, macro_value in sorted(macros.items()):
        if not macro_name.isidentifier():
            continue
        if macro_name.startswith("__"):
            continue
        lines.append(
            "setattr(_constants_module, "
            + repr(macro_name)
            + ", "
            + macro_value
            + ")"
        )
    lines.append("")
    lines.append("# Register constants submodule")
    lines.append(f"_sys.modules['{module_name}.constants'] = _constants_module")
    lines.append("")
    lines.append("# Clean up temporary names")
    lines.append("del _constants_module")
    return "\n".join(lines) + "\n"


def find_usage_example(
    debug_files: DebugInfoFiles,
    all_structures: dict[tuple[str, int], StructureDefinition],
) -> dict[str, str]:
    """
    Find a function and struct example for usage documentation.

    This function analyzes debug information to discover functions that take
    struct pointers as parameters, then generates example code showing how to
    use the generated Python bindings. This helps users understand how to
    properly use the bindings with real function and struct names.

    The function prioritizes finding examples that:
    - Use real function and struct names from the library
    - Show proper pointer handling with byref()
    - Demonstrate struct field access
    - Include proper type annotations
    - Follow common usage patterns

    Args:
        debug_files: Container for all debug file information
        all_structures: Dictionary of all discovered structures

    Returns:
        Dictionary containing example information with keys:
        - function: Name of example function
        - struct: Name of example struct
        - field: Name of example struct field
        - argtypes: String showing function argument types
        - call_args: String showing function call arguments
    """
    # Default fallback examples in case we can't find real ones
    example = {
        "function": "some_function",
        "struct": "MyStruct",
        "field": "field_name",
        "argtypes": "[POINTER(MyStruct)]",
        "call_args": "byref(structure)",
    }

    # Early exit if no structures were discovered
    if not all_structures:
        logger.debug(
            "Usage example: no structures available; using fallback example"
        )
        return example

    # Build lookup indices for cross-referencing debug information
    name_mapping = build_structure_name_mapping(all_structures)
    auxiliary_entry_index = build_auxiliary_debug_entry_index(debug_files)

    # Create reverse mapping: C struct name -> Python class name (ignoring size conflicts)
    c_name_to_python = {
        c_structure_name: python_name
        for (c_structure_name, size), python_name in name_mapping.items()
    }
    logger.debug(
        f"Usage example: available struct names={len(c_name_to_python)}; sample={list(c_name_to_python.keys())[:5]}"
    )
    # Diagnostics: sample a few structures and their first member names
    sample_structs = []
    for (c_name, size), struct_def in list(all_structures.items())[:5]:
        first_member = (
            struct_def.members[0].name if struct_def.members else "<no-members>"
        )
        sample_structs.append((c_name, first_member))
    logger.debug(
        f"Usage example: sample structs (first member): {sample_structs}"
    )

    candidate_examples = []

    # Counters for diagnostics
    total_subprograms = 0
    total_formal_params = 0
    total_pointer_params = 0
    total_struct_pointer_params = 0
    total_struct_pointer_known = 0

    # Collect a few CU names for diagnostics (verbose only)
    compilation_unit_names: list[str] = []

    # Search through all debug files (main + auxiliary) for function examples
    for debug_file_info in debug_files:
        for compilation_unit in debug_file_info.debug_info.iter_CUs():
            # Extract compilation unit name to filter relevant code
            compilation_unit_name_attribute = (
                compilation_unit.get_top_DIE().attributes.get("DW_AT_name")
            )
            compilation_unit_name = (
                extract_name_from_debug_info(
                    compilation_unit_name_attribute, debug_files
                )
                if compilation_unit_name_attribute
                else None
            )

            if len(compilation_unit_names) < 5:
                compilation_unit_names.append(compilation_unit_name or "<none>")

            # FILTERING: Only process compilation units with names starting with '.'
            # This typically filters out system headers and focuses on main library code
            if (
                not compilation_unit_name
                or not compilation_unit_name.startswith(".")
            ):
                continue

            # Scan all debug entries in this compilation unit for function definitions
            for entry in compilation_unit.iter_DIEs():
                if (
                    entry.tag == "DW_TAG_subprogram"
                ):  # Function/method definition
                    total_subprograms += 1
                    func_name = extract_name_from_debug_info(
                        entry.attributes.get("DW_AT_name"), debug_files
                    )

                    # FUNCTION NAME FILTERING
                    if (
                        not func_name
                        or func_name.startswith("_")
                        or len(func_name) > MAX_FUNCTION_NAME_LENGTH
                    ):
                        continue
                    if (
                        not func_name.replace("_", "")
                        .replace("-", "")
                        .isalnum()
                        or not func_name.isascii()
                    ):
                        continue
                    if any(ord(c) < 32 or ord(c) > 126 for c in func_name):
                        continue

                    # PARAMETER ANALYSIS
                    matched_index = None
                    matched_struct_name = None

                    for idx, child in enumerate(entry.iter_children()):
                        if child.tag == "DW_TAG_formal_parameter":
                            total_formal_params += 1

                            # Inspect the raw attribute first
                            type_attr = child.attributes.get("DW_AT_type")
                            if total_formal_params <= 10:
                                if type_attr is None:
                                    logger.debug(
                                        "Usage example: DW_AT_type attribute missing on parameter"
                                    )
                                else:
                                    logger.debug(
                                        f"Usage example: DW_AT_type form={getattr(type_attr, 'form', None)} value_type={type(type_attr.value).__name__}"
                                    )

                            param_type = find_referenced_debug_entry(
                                child,
                                "DW_AT_type",
                                debug_files,
                                auxiliary_entry_index,
                            )
                            base_type = param_type
                            visited = set()

                            # Diagnostic: log first few parameters' initial tag
                            if total_formal_params <= 10:
                                init_tag = (
                                    getattr(base_type, "tag", None)
                                    if base_type is not None
                                    else None
                                )
                                logger.debug(
                                    f"Usage example: param initial tag={init_tag}"
                                )

                            while (
                                base_type
                                and getattr(base_type, "offset", None)
                                not in visited
                            ):
                                visited.add(getattr(base_type, "offset", None))

                                # Diagnostic: log peel step tag (first few only)
                                if total_formal_params <= 10:
                                    logger.debug(
                                        f"Usage example: peel step tag={base_type.tag}"
                                    )

                                if base_type.tag == "DW_TAG_pointer_type":
                                    total_pointer_params += 1
                                    base_type = find_referenced_debug_entry(
                                        base_type,
                                        "DW_AT_type",
                                        debug_files,
                                        auxiliary_entry_index,
                                    )
                                elif base_type.tag in (
                                    "DW_TAG_typedef",
                                    "DW_TAG_const_type",
                                    "DW_TAG_volatile_type",
                                ):
                                    base_type = find_referenced_debug_entry(
                                        base_type,
                                        "DW_AT_type",
                                        debug_files,
                                        auxiliary_entry_index,
                                    )
                                else:
                                    break

                            if (
                                base_type
                                and base_type.tag
                                in (
                                    "DW_TAG_structure_type",
                                    "DW_TAG_class_type",
                                )
                                and base_type.tag != "DW_TAG_union_type"
                            ):
                                total_struct_pointer_params += 1
                                struct_name = extract_name_from_debug_info(
                                    base_type.attributes.get("DW_AT_name"),
                                    debug_files,
                                )
                                if struct_name in c_name_to_python:
                                    total_struct_pointer_known += 1
                                    matched_index = idx
                                    matched_struct_name = struct_name
                                    break
                                # Log a few misses for diagnostics
                                elif len(candidate_examples) < 3:
                                    logger.debug(
                                        f"Usage example: struct param refers to '{struct_name}' not in discovered structures"
                                    )

                    if matched_index is not None and matched_struct_name:
                        python_struct_name = c_name_to_python[
                            matched_struct_name
                        ]
                        struct_key = next(
                            (
                                (c_name, size)
                                for (c_name, size) in all_structures.keys()
                                if c_name == matched_struct_name
                            ),
                            None,
                        )
                        if struct_key:
                            struct_def = all_structures[struct_key]
                            good_field = next(
                                (
                                    m.name
                                    for m in struct_def.members
                                    if not m.name.startswith("_")
                                    and len(m.name) < 20
                                ),
                                None,
                            )
                            if good_field:
                                total_params = len(list(entry.iter_children()))
                                if matched_index == 0:
                                    argtypes_str = (
                                        f"[POINTER({python_struct_name}), ...]"
                                    )
                                    call_args_str = "byref(structure), ..."
                                elif matched_index == total_params - 1:
                                    argtypes_str = (
                                        f"[..., POINTER({python_struct_name})]"
                                    )
                                    call_args_str = "..., byref(structure)"
                                else:
                                    argtypes_str = f"[..., POINTER({python_struct_name}), ...]"
                                    call_args_str = "..., byref(structure), ..."
                                candidate_examples.append(
                                    {
                                        "function": func_name,
                                        "struct": python_struct_name,
                                        "field": good_field,
                                        "argtypes": argtypes_str,
                                        "call_args": call_args_str,
                                    }
                                )

    logger.debug(f"Usage example: sampled CUs: {compilation_unit_names}")
    logger.debug(f"Usage example: candidate_examples={len(candidate_examples)}")
    logger.debug(
        f"Usage example: subprograms={total_subprograms}, formal_params={total_formal_params}, pointer_params={total_pointer_params}, struct_ptr_params={total_struct_pointer_params}, struct_ptr_known={total_struct_pointer_known}"
    )

    # If we didn't find any candidates, try a second pass without CU name filtering
    if not candidate_examples:
        logger.debug("Usage example: retrying without CU name filtering")
        for debug_file_info in debug_files:
            for compilation_unit in debug_file_info.debug_info.iter_CUs():
                for entry in compilation_unit.iter_DIEs():
                    if entry.tag == "DW_TAG_subprogram":
                        func_name = extract_name_from_debug_info(
                            entry.attributes.get("DW_AT_name"), debug_files
                        )
                        if (
                            not func_name
                            or func_name.startswith("_")
                            or len(func_name) > MAX_FUNCTION_NAME_LENGTH
                        ):
                            continue
                        if (
                            not func_name.replace("_", "")
                            .replace("-", "")
                            .isalnum()
                            or not func_name.isascii()
                        ):
                            continue
                        if any(ord(c) < 32 or ord(c) > 126 for c in func_name):
                            continue

                        matched_index = None
                        matched_struct_name = None

                        for idx, child in enumerate(entry.iter_children()):
                            if child.tag == "DW_TAG_formal_parameter":
                                param_type = find_referenced_debug_entry(
                                    child,
                                    "DW_AT_type",
                                    debug_files,
                                    auxiliary_entry_index,
                                )
                                base_type = param_type
                                visited = set()

                                while (
                                    base_type
                                    and getattr(base_type, "offset", None)
                                    not in visited
                                ):
                                    visited.add(
                                        getattr(base_type, "offset", None)
                                    )

                                    if base_type.tag == "DW_TAG_pointer_type":
                                        base_type = find_referenced_debug_entry(
                                            base_type,
                                            "DW_AT_type",
                                            debug_files,
                                            auxiliary_entry_index,
                                        )
                                    elif base_type.tag in (
                                        "DW_TAG_typedef",
                                        "DW_TAG_const_type",
                                        "DW_TAG_volatile_type",
                                    ):
                                        base_type = find_referenced_debug_entry(
                                            base_type,
                                            "DW_AT_type",
                                            debug_files,
                                            auxiliary_entry_index,
                                        )
                                    else:
                                        break

                                if (
                                    base_type
                                    and base_type.tag
                                    in (
                                        "DW_TAG_structure_type",
                                        "DW_TAG_class_type",
                                    )
                                    and base_type.tag != "DW_TAG_union_type"
                                ):
                                    struct_name = extract_name_from_debug_info(
                                        base_type.attributes.get("DW_AT_name"),
                                        debug_files,
                                    )
                                    if struct_name in c_name_to_python:
                                        matched_index = idx
                                        matched_struct_name = struct_name
                                        break

                        if matched_index is not None and matched_struct_name:
                            python_struct_name = c_name_to_python[
                                matched_struct_name
                            ]
                            struct_key = next(
                                (
                                    (c_name, size)
                                    for (c_name, size) in all_structures.keys()
                                    if c_name == matched_struct_name
                                ),
                                None,
                            )
                            if struct_key:
                                struct_def = all_structures[struct_key]
                                good_field = next(
                                    (
                                        m.name
                                        for m in struct_def.members
                                        if not m.name.startswith("_")
                                        and len(m.name) < 20
                                    ),
                                    None,
                                )
                                if good_field:
                                    total_params = len(
                                        list(entry.iter_children())
                                    )
                                    if matched_index == 0:
                                        argtypes_str = f"[POINTER({python_struct_name}), ...]"
                                        call_args_str = "byref(structure), ..."
                                    elif matched_index == total_params - 1:
                                        argtypes_str = f"[..., POINTER({python_struct_name})]"
                                        call_args_str = "..., byref(structure)"
                                    else:
                                        argtypes_str = f"[..., POINTER({python_struct_name}), ...]"
                                        call_args_str = (
                                            "..., byref(structure), ..."
                                        )
                                    candidate_examples.append(
                                        {
                                            "function": func_name,
                                            "struct": python_struct_name,
                                            "field": good_field,
                                            "argtypes": argtypes_str,
                                            "call_args": call_args_str,
                                        }
                                    )
        logger.debug(
            f"Usage example: second-pass candidate_examples={len(candidate_examples)}"
        )

    # SELECT BEST EXAMPLE
    if candidate_examples:
        candidate_examples.sort(
            key=lambda x: (len(x["function"]), x["function"])
        )
        best_example = next(
            (
                c
                for c in candidate_examples
                if c["function"].replace("_", "").isalnum()
                and not any(
                    ch in c["function"] for ch in ["@", "$", ".", "(", ")"]
                )
                and len(c["function"]) >= 3
            ),
            candidate_examples[0],
        )
        return best_example

    logger.debug("Usage example: no candidates found; using fallback example")
    return example


def _highlight_python_snippet(line: str) -> str:
    """Apply very simple syntax highlighting to a single Python line.
    Only foreground colors are used so the background can remain active.
    """
    # Keywords
    import re as _re

    def color_keywords(text: str) -> str:
        # Python keywords + literals
        pattern = _re.compile(
            r"\b(from|import|as|class|def|return|None|True|False)\b"
        )
        return pattern.sub(
            lambda m: f"{Fore.BLUE}{m.group(0)}{Fore.BLACK}", text
        )

    def color_builtin_types(text: str) -> str:
        pattern = _re.compile(r"\b(POINTER|c_int|byref)\b")
        return pattern.sub(
            lambda m: f"{Fore.MAGENTA}{m.group(0)}{Fore.BLACK}", text
        )

    # Handle comments: color from first # onward
    if "#" in line:
        before, _, after = line.partition("#")
        before = color_builtin_types(color_keywords(before))
        comment = f"{Fore.GREEN}#{after}{Fore.BLACK}"
        return before + comment

    return color_builtin_types(color_keywords(line))


def _render_white_block_fixed_width(
    lines: list[str], margin_prefix: str, width: int
) -> None:
    """Render lines with a white background padded to a fixed width.
    Foreground is black by default; tokens may be re-colored by the highlighter.
    Width counts visible characters only (ANSI codes excluded).
    """
    for raw_line in lines:
        # Apply highlighting (may inject ANSI sequences)
        colored_line = _highlight_python_snippet(raw_line)
        # Measure visible length without ANSI
        visible_len = len(ANSI_COLOR_PATTERN.sub("", colored_line))
        pad = " " * max(0, width - visible_len)
        # Keep background active across whole line; start with black foreground baseline
        print(
            f"{margin_prefix}{Back.WHITE}{Fore.BLACK}{colored_line}{pad}{Style.RESET_ALL}"
        )


def print_usage_example(
    debug_files: DebugInfoFiles,
    all_structures: dict[tuple[str, int], StructureDefinition],
    all_typedefs: dict[str, TypedefInfo],
    output_filename: str,
    use_color: bool = True,
) -> None:
    """
    Print a formatted usage example with real discovered function and struct names.

    Args:
        debug_files: Container for all debug file information
        all_structures: Dictionary of all discovered structures
        all_typedefs: Dictionary of all discovered typedefs
        output_filename: Name of the generated output file
        use_color: Whether to use colored output
    """
    # Find real examples from the discovered types and functions
    example = find_usage_example(debug_files, all_structures)

    module_name = os.path.splitext(output_filename)[0]

    if use_color and _has_colorama:
        print(f"\n{Fore.BLUE}┌─ Summary{'─' * 56}{Style.RESET_ALL}")
        print_stats(len(all_structures), len(all_typedefs), use_color=use_color)
        print(f"{Fore.BLUE}│{Style.RESET_ALL}")
        print(
            f"{Fore.BLUE}│  {Fore.WHITE}{Style.BRIGHT}Hypothetical Example:{Style.RESET_ALL}"
        )
        print(f"{Fore.BLUE}│  {Style.RESET_ALL}")

        margin = f"{Fore.BLUE}│  {Style.RESET_ALL}"
        code_lines: list[str] = [
            "```python",
            "from ctypes import *",
            f"from {module_name}.types import {example['struct']}",
            f"from {module_name}.symbols import {example['function']}",
            f"from {module_name}.constants import BUFFER_SIZE",
            "",
            "# Create and populate struct:",
            f"structure = {example['struct']}()",
            f"structure.{example['field']} = BUFFER_SIZE",
            "",
            "# Set up function prototype and call:",
            f"{example['function']}.argtypes = {example['argtypes']}",
            f"{example['function']}.restype = c_int",
            f"result = {example['function']}({example['call_args']})",
            "```",
        ]
        _render_white_block_fixed_width(
            code_lines, margin_prefix=margin, width=64
        )

        print(f"{Fore.BLUE}└{'─' * 66}{Style.RESET_ALL}")
    else:
        print("\n── Summary")
        print_stats(len(all_structures), len(all_typedefs), use_color=use_color)
        print("\nHypothetical Example:")
        print("")
        print("```python")
        print("from ctypes import *")
        print(f"from {module_name}.types import {example['struct']}")
        print(f"from {module_name}.symbols import {example['function']}")
        print(f"from {module_name}.constants import BUFFER_SIZE")
        print("")
        print("# Create and populate struct:")
        print(f"structure = {example['struct']}()")
        print(f"structure.{example['field']} = BUFFER_SIZE")
        print("")
        print("# Set up function prototype and call:")
        print(f"{example['function']}.argtypes = {example['argtypes']}")
        print(f"{example['function']}.restype = c_int")
        print(f"result = {example['function']}({example['call_args']})")
        print("```")
