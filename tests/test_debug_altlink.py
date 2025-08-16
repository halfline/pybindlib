"""
Integration test for .gnu_debugaltlink auxiliary debuginfo handling.
"""

import os
import shutil
import subprocess
import pytest

from pybindlib.debug_info import load_library_and_debug_info


@pytest.fixture
def toolchain():
    missing = [t for t in ["gcc", "eu-strip", "objcopy"] if shutil.which(t) is None]
    if missing:
        pytest.skip("Missing tools: " + ", ".join(missing))


def _compile_shared(tmp_path):
    src = tmp_path / "a.c"
    src.write_text(
        """
        __attribute__((visibility("default")))
        int exported(int x){ return x+1; }
        """
    )
    so = tmp_path / "libalt.so"
    subprocess.run(["gcc", "-g", "-fPIC", "-shared", "-o", str(so), str(src)], check=True)
    return str(so)


def test_gnu_debugaltlink_resolution(tmp_path, toolchain):
    so_path = _compile_shared(tmp_path)

    # Create detached debuginfo file
    dbg_path = tmp_path / "libalt.so.debug"
    subprocess.run(["eu-strip", "-g", "-f", str(dbg_path), so_path], check=True)

    # Create an auxiliary debug file
    aux_filename = "alt.debug"
    aux_path = tmp_path / aux_filename
    aux_path.write_bytes(open(dbg_path, "rb").read())

    # Create section contents: filename + null
    secfile = tmp_path / "secdata.bin"
    secfile.write_bytes(aux_filename.encode("utf-8") + b"\x00")

    # Add .gnu_debugaltlink pointing to our aux file (relative path)
    subprocess.run(
        [
            "objcopy",
            "--add-section",
            f".gnu_debugaltlink={secfile}",
            "--set-section-flags",
            ".gnu_debugaltlink=readonly,data",
            str(dbg_path),
        ],
        check=True,
    )

    # Load and verify auxiliary file is discovered
    debug_files, library_name, resolved_debug_path, build_id, exported = load_library_and_debug_info(
        so_path
    )
    assert os.path.realpath(resolved_debug_path) == os.path.realpath(str(dbg_path))
    assert debug_files.has_auxiliary()
    assert os.path.realpath(debug_files.auxiliary_file.file_path) == os.path.realpath(
        str(aux_path)
    )