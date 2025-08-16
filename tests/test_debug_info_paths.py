"""
Additional tests for debug info path resolution and SONAME handling.
"""

import os
import shutil
import subprocess
import pytest

from pybindlib import debug_info as di
from pybindlib.debug_info import load_library_and_debug_info


@pytest.fixture
def gcc_available():
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")


def _compile_shared_with_soname(tmp_path, soname):
    c = tmp_path / "soname.c"
    c.write_text(
        """
        __attribute__((visibility("default")))
        int myfunc(void) { return 7; }
        """
    )
    so = tmp_path / "libsoname.so"
    cmd = [
        "gcc",
        "-g",
        "-fPIC",
        "-shared",
        "-Wl,-soname," + soname,
        "-o",
        str(so),
        str(c),
    ]
    subprocess.run(cmd, check=True)
    return str(so)


def test_soname_extraction(tmp_path, gcc_available):
    soname = "libmysoname.so.9"
    so_path = _compile_shared_with_soname(tmp_path, soname)

    debug_files, library_name, debug_path, build_id, exported = load_library_and_debug_info(
        so_path
    )
    # The extracted library name should match SONAME
    assert library_name == soname


def test_build_id_lookup_integration(monkeypatch, tmp_path, gcc_available):
    # Compile a library (with build-id)
    c = tmp_path / "b.c"
    c.write_text("__attribute__((visibility(\"default\"))) int f(void){return 1;}")
    so = tmp_path / "libbid.so"
    subprocess.run(["gcc", "-g", "-fPIC", "-shared", "-o", str(so), str(c)], check=True)

    # Read its build-id using our function
    with open(so, "rb") as fh:
        elf = di.ELFFile(fh)
        bid = di.read_build_identifier(elf)

    # Create a fake build-id path with a valid debug file (copy of so)
    if isinstance(bid, (bytes, bytearray)):
        bid_hex = bid.hex()
    else:
        bid_hex = str(bid) if bid is not None else None

    assert bid_hex, "build-id not found on compiled object"

    fake_root = tmp_path / ".build-id"
    leaf_dir = fake_root / bid_hex[:2]
    leaf_dir.mkdir(parents=True, exist_ok=True)
    target = leaf_dir / (bid_hex[2:] + ".debug")
    # Use a copy of the .so as the debug file (it has DWARF)
    target.write_bytes(open(so, "rb").read())

    # Monkeypatch the search function to prefer our temp root
    original = di.locate_debug_file_by_build_id

    def fake_locate_debug_file_by_build_id(build_id: str | None):
        # Mirror the logic but use our path
        if not build_id:
            return None
        debug_path = os.path.join(str(fake_root), build_id[:2], build_id[2:] + ".debug")
        return debug_path if os.path.exists(debug_path) else None

    monkeypatch.setattr(di, "locate_debug_file_by_build_id", fake_locate_debug_file_by_build_id)

    # Now load via our high-level function; it should resolve to our debug file
    debug_files, library_name, debug_path, build_id2, exported = load_library_and_debug_info(
        str(so)
    )
    assert os.path.realpath(debug_path) == os.path.realpath(str(target))


def test_locate_fallback_debug_file(tmp_path):
    # Create a fake real path and a .debug neighbor
    real = tmp_path / "libx.so"
    real.write_bytes(b"\x7fELF")
    neighbor = tmp_path / "libx.so.debug"
    neighbor.write_bytes(b"\x7fELF")

    path = di.locate_fallback_debug_file(str(real))
    assert path is not None
    assert os.path.realpath(path) == os.path.realpath(str(neighbor))