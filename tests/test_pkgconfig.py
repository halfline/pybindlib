"""Tests for pkg-config wrapper functionality."""

import os
import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest

from pybindlib.pkgconfig import PkgConfig, PkgConfigResult


@pytest.fixture
def mock_run():
    """Mock subprocess.run for testing."""
    with patch("subprocess.run") as mock:
        yield mock


def test_verify_pkg_config_success(mock_run):
    """Test successful pkg-config verification."""
    mock_run.return_value.stdout = "0.29.2\n"

    pkg_config = PkgConfig()
    # Should not raise any exceptions


def test_verify_pkg_config_not_found(mock_run):
    """Test pkg-config not found error."""
    mock_run.side_effect = FileNotFoundError("No such file")

    with pytest.raises(RuntimeError, match="pkg-config not available"):
        PkgConfig()


def test_verify_pkg_config_error(mock_run):
    """Test pkg-config error."""
    mock_run.side_effect = subprocess.CalledProcessError(1, ["pkg-config"])

    with pytest.raises(RuntimeError, match="pkg-config not available"):
        PkgConfig()


def test_exists_true(mock_run):
    """Test package exists check - true case."""
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = ""

    pkg_config = PkgConfig()
    assert pkg_config.exists("existing-package") is True

    mock_run.assert_called_with(
        ["pkg-config", "--exists", "existing-package"],
        capture_output=True,
        text=True,
        check=True
    )


def test_exists_false(mock_run):
    """Test package exists check - false case."""
    def mock_pkg_config(*args, **kwargs):
        """Mock pkg-config responses based on arguments."""
        cmd = args[0]
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "0.29.2\n", "")
        elif "--exists" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    mock_run.side_effect = mock_pkg_config

    pkg_config = PkgConfig()
    assert pkg_config.exists("nonexistent-package") is False


def test_get_version(mock_run):
    """Test getting package version."""
    mock_run.return_value.stdout = "1.2.3\n"

    pkg_config = PkgConfig()
    assert pkg_config.get_version("test-package") == "1.2.3"

    mock_run.assert_called_with(
        ["pkg-config", "--modversion", "test-package"],
        capture_output=True,
        text=True,
        check=True
    )


def test_get_version_not_found(mock_run):
    """Test getting version of nonexistent package."""
    def mock_pkg_config(*args, **kwargs):
        """Mock pkg-config responses based on arguments."""
        cmd = args[0]
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "0.29.2\n", "")
        elif "--modversion" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    mock_run.side_effect = mock_pkg_config

    pkg_config = PkgConfig()
    assert pkg_config.get_version("nonexistent-package") is None


def test_query_basic(mock_run):
    """Test basic package query."""
    def mock_pkg_config(*args, **kwargs):
        """Mock pkg-config responses based on arguments."""
        cmd = args[0]
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "0.29.2\n", "")
        elif "--cflags" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "-I/usr/include/test", "")
        elif "--libs" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "-L/usr/lib -ltest", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    mock_run.side_effect = mock_pkg_config

    pkg_config = PkgConfig()
    result = pkg_config.query("test-package")

    assert isinstance(result, PkgConfigResult)
    assert result.libraries == {"test"}
    assert result.include_dirs == {"/usr/include/test"}
    assert result.cflags == "-I/usr/include/test"
    assert result.libs == "-L/usr/lib -ltest"


def test_query_multiple_flags(mock_run):
    """Test query with multiple libraries and include dirs."""
    def mock_pkg_config(*args, **kwargs):
        """Mock pkg-config responses based on arguments."""
        cmd = args[0]
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "0.29.2\n", "")
        elif "--cflags" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0,
                "-I/usr/include/test1 -I/usr/include/test2 -DSOME_DEFINE",
                ""
            )
        elif "--libs" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0,
                "-L/usr/lib -ltest1 -ltest2 -L/usr/local/lib -ltest3",
                ""
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    mock_run.side_effect = mock_pkg_config

    pkg_config = PkgConfig()
    result = pkg_config.query("test-package")

    assert result.libraries == {"test1", "test2", "test3"}
    assert result.include_dirs == {"/usr/include/test1", "/usr/include/test2"}


def test_query_package_not_found(mock_run):
    """Test query with nonexistent package."""
    def mock_pkg_config(*args, **kwargs):
        """Mock pkg-config responses based on arguments."""
        cmd = args[0]
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "0.29.2\n", "")
        raise subprocess.CalledProcessError(1, cmd, "Package not found")

    mock_run.side_effect = mock_pkg_config

    pkg_config = PkgConfig()
    with pytest.raises(subprocess.CalledProcessError):
        pkg_config.query("nonexistent-package")


def test_custom_pkg_config_path(mock_run):
    """Test using custom pkg-config binary path."""
    mock_run.return_value.stdout = "0.29.2\n"

    pkg_config = PkgConfig(pkg_config_binary="/custom/path/pkg-config")
    pkg_config.exists("test-package")

    mock_run.assert_called_with(
        ["/custom/path/pkg-config", "--exists", "test-package"],
        capture_output=True,
        text=True,
        check=True
    )


@pytest.mark.integration
def test_integration_with_real_pc_file(tmp_path, monkeypatch):
    """Integration test using a real pkg-config file.

    This test creates an actual .pc file and uses the system's pkg-config
    to verify our wrapper's functionality with variable substitution,
    dependencies, and other pkg-config features.
    """
    # Create pkgconfig directory
    pkgconfig_dir = tmp_path / "pkgconfig"
    pkgconfig_dir.mkdir()

    # Create test .pc file
    pc_content = dedent("""
        prefix=/usr/local
        exec_prefix=${prefix}
        libdir=${exec_prefix}/lib64
        includedir=${prefix}/include/testlib

        Name: testlib
        Description: Test library for pkg-config parsing
        Version: 1.2.3
        Requires: zlib >= 1.2
        Conflicts:
        Cflags: -I${includedir} -I${includedir}/extra -DTEST_FEATURE=1
        Libs: -L${libdir} -ltestlib -lm
        Libs.private: -ldl
    """)
    pc_file = pkgconfig_dir / "testlib.pc"
    pc_file.write_text(pc_content)

    # Set PKG_CONFIG_PATH to our test directory
    monkeypatch.setenv("PKG_CONFIG_PATH", str(pkgconfig_dir))

    # Create PkgConfig instance
    pkg_config = PkgConfig()

    # Test package detection
    assert pkg_config.exists("testlib") is True
    assert pkg_config.exists("nonexistent") is False

    # Test version extraction
    assert pkg_config.get_version("testlib") == "1.2.3"

    # Test full query
    result = pkg_config.query("testlib")

    # Verify libraries (including those from dependencies)
    assert "testlib" in result.libraries
    assert "m" in result.libraries  # from -lm
    assert "z" in result.libraries  # from zlib dependency

    # Verify include directories with variable substitution
    expected_includes = {
        "/usr/local/include/testlib",
        "/usr/local/include/testlib/extra"
    }
    assert result.include_dirs == expected_includes

    # Verify raw flags contain defines and dependency flags
    assert "-DTEST_FEATURE=1" in result.cflags
    assert "-L/usr/local/lib64" in result.libs
    assert "-ltestlib" in result.libs