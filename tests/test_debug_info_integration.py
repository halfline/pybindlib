"""
Integration tests for debuginfo handling using real compiled shared libraries.
"""

import os
import shutil
import subprocess
import textwrap
import pytest

from pybindlib.debug_info import (
    load_library_and_debug_info,
    collect_all_structures_and_typedefs,
)
from pybindlib.preprocessor import (
    process_headers,
    parse_function_pointer_typedefs,
)


@pytest.fixture
def toolchain_available():
    required = ["gcc"]
    missing = [t for t in required if shutil.which(t) is None]
    if missing:
        pytest.skip(f"Missing required tools: {', '.join(missing)}")


def _compile_shared(tmp_path: os.PathLike, name: str = "libtest") -> str:
    """Compile a simple shared library with DWARF info and return path to .so."""
    src = tmp_path / "test.c"
    hdr = tmp_path / "test.h"

    hdr.write_text(
        textwrap.dedent(
            r"""
            #ifndef TEST_H
            #define TEST_H

            #include <stdint.h>

            #define BUFFER_SIZE 128
            #define HEX_VALUE 0x2A
            #define FLOAT_EXP 1.23e4

            typedef int Counter;

            typedef struct MyStruct {
                int value;
                uint8_t small;
            } MyStruct;

            // Function pointer typedef to be discovered
            typedef void (*SimpleCallback)(int);

            #endif
            """
        )
    )

    src.write_text(
        textwrap.dedent(
            r"""
            #include "test.h"

            // Ensure the struct appears in debug info by using it
            __attribute__((visibility("default")))
            int add_numbers(MyStruct* s, Counter addend) {
                if (!s) return -1;
                return s->value + (int)addend;
            }

            __attribute__((visibility("default")))
            void do_callback(SimpleCallback cb) {
                if (cb) cb(42);
            }
            """
        )
    )

    so_path = tmp_path / f"{name}.so"
    # Build shared object with debug info
    cmd = [
        "gcc",
        "-g",
        "-fPIC",
        "-shared",
        "-o",
        str(so_path),
        str(src),
    ]
    subprocess.run(cmd, check=True)
    return str(so_path)


def test_unstripped_library_dwarf(tmp_path, toolchain_available):
    so_path = _compile_shared(tmp_path)

    debug_files, library_name, debug_path, build_id, exported_functions = load_library_and_debug_info(
        so_path
    )

    # Should use the original path as debug file when unstripped
    assert os.path.realpath(debug_path) == os.path.realpath(so_path)
    # Check exported functions we declared
    assert "add_numbers" in exported_functions
    assert "do_callback" in exported_functions

    # Collect structures and typedefs
    structures, typedefs = collect_all_structures_and_typedefs(
        debug_files, skip_progress=True
    )

    # Our struct name should be present among collected structures
    assert any(c_name == "MyStruct" for (c_name, _size) in structures.keys())
    # Our typedef should be present (best-effort depending on toolchain)
    assert "Counter" in typedefs


@pytest.mark.skipif(shutil.which("eu-strip") is None, reason="eu-strip not available")
def test_separate_debuginfo_via_debuglink(tmp_path, toolchain_available):
    so_path = _compile_shared(tmp_path)

    # Use eu-strip to create a separate debuginfo file and add .gnu_debuglink
    dbg_path = tmp_path / "libtest.so.debug"
    subprocess.run(["eu-strip", "-g", "-f", str(dbg_path), so_path], check=True)

    # Confirm main .so no longer has DWARF, but has debuglink
    debug_files, library_name, debug_path, build_id, exported_functions = load_library_and_debug_info(
        so_path
    )

    # Should resolve to the separate debug file we created
    assert os.path.realpath(debug_path) == os.path.realpath(str(dbg_path))

    # We still should be able to collect structures and typedefs
    structures, typedefs = collect_all_structures_and_typedefs(
        debug_files, skip_progress=True
    )
    assert any(c_name == "MyStruct" for (c_name, _size) in structures.keys())


@pytest.mark.skipif(shutil.which("dwz") is None, reason="dwz not available")
@pytest.mark.skipif(shutil.which("eu-strip") is None, reason="eu-strip not available")
def test_dwz_on_separate_debuginfo(tmp_path, toolchain_available):
    so_path = _compile_shared(tmp_path)
    dbg_path = tmp_path / "libtest.so.debug"
    subprocess.run(["eu-strip", "-g", "-f", str(dbg_path), so_path], check=True)

    # Optimize the debug file with dwz
    subprocess.run(["dwz", str(dbg_path)], check=True)

    # Still should load and parse structures
    debug_files, library_name, debug_path, build_id, exported_functions = load_library_and_debug_info(
        so_path
    )
    assert os.path.realpath(debug_path) == os.path.realpath(str(dbg_path))

    structures, typedefs = collect_all_structures_and_typedefs(
        debug_files, skip_progress=True
    )
    assert any(c_name == "MyStruct" for (c_name, _size) in structures.keys())


@pytest.mark.skipif(shutil.which("cpp") is None, reason="cpp not available")
def test_header_processing_integration(tmp_path):
    # Create a header with several macros, including hex and scientific notation
    header = tmp_path / "macros.h"
    header.write_text(
        textwrap.dedent(
            r"""
            #define SIMPLE_CONSTANT 42
            #define HEX_CONSTANT 0xFF
            #define FLOAT_EXP 1.23e4
            #define STR_CONSTANT "hello\nworld"
            #define EMPTY_CONSTANT
            typedef void (*SimpleCallback)(int);
            """
        )
    )

    macros = process_headers([str(header)], include_paths=[], referenced_modules=[])

    assert macros["SIMPLE_CONSTANT"] == "42"
    assert macros["HEX_CONSTANT"] == "255"
    assert macros["FLOAT_EXP"] == "12300.0"
    assert macros["STR_CONSTANT"].startswith("'") and "\\n" in macros["STR_CONSTANT"]
    assert macros["EMPTY_CONSTANT"] == "1"

    fn_typedefs = parse_function_pointer_typedefs([str(header)])
    assert "SimpleCallback" in fn_typedefs