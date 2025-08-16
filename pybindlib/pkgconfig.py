"""Package configuration wrapper using pkg-config.

This module provides a wrapper around the pkg-config command line tool to extract
library and include directory information for packages.
"""

import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass
class PkgConfigResult:
    """Results from querying pkg-config."""
    libraries: Set[str]  # Library names without -l prefix
    include_dirs: Set[str]  # Include directories without -I prefix
    cflags: str  # Raw CFLAGS string
    libs: str  # Raw Libs string

    def get_library_dirs(self) -> Set[str]:
        """Get library directories from the libs string."""
        return self._extract_values(self.libs, "-L")

    def get_library_names(self) -> Set[str]:
        """Get library names from the libs string."""
        return self.libraries

    def get_include_dirs(self) -> Set[str]:
        """Get include directories from the cflags string."""
        return self.include_dirs

    @staticmethod
    def _extract_values(flags: str, prefix: str) -> Set[str]:
        """Extract values with given prefix from flags string."""
        values = set()
        for part in shlex.split(flags):
            if part.startswith(prefix):
                values.add(part[len(prefix):])
        return values


class PkgConfig:
    """Wrapper for pkg-config command line tool."""

    def __init__(self, pkg_config_binary: str = "pkg-config") -> None:
        """Initialize PkgConfig wrapper.

        Args:
            pkg_config_binary: Path to pkg-config binary. Defaults to "pkg-config"
                which assumes it's in PATH.
        """
        self.pkg_config_binary = pkg_config_binary
        self._verify_pkg_config()

    def _verify_pkg_config(self) -> None:
        """Verify pkg-config is available and working.

        Raises:
            RuntimeError: If pkg-config is not available or not working
        """
        try:
            subprocess.run(
                [self.pkg_config_binary, "--version"],
                check=True,
                capture_output=True,
                text=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(
                f"pkg-config not available or not working: {e}"
            ) from e

    def _run_pkg_config(
        self,
        args: List[str],
        package: str,
        check: bool = True
    ) -> str:
        """Run pkg-config with given arguments.

        Args:
            args: Arguments to pass to pkg-config
            package: Package name to query
            check: Whether to check return code

        Returns:
            Command output as string

        Raises:
            subprocess.CalledProcessError: If check=True and pkg-config returns non-zero
        """
        cmd = [self.pkg_config_binary] + args + [package]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check
        )
        return result.stdout.strip()

    def exists(self, package: str) -> bool:
        """Check if a package exists.

        Args:
            package: Name of the package to check

        Returns:
            True if package exists, False otherwise
        """
        try:
            self._run_pkg_config(["--exists"], package)
            return True
        except subprocess.CalledProcessError:
            return False

    def get_version(self, package: str) -> Optional[str]:
        """Get package version.

        Args:
            package: Name of the package to query

        Returns:
            Package version string or None if package not found
        """
        try:
            return self._run_pkg_config(["--modversion"], package)
        except subprocess.CalledProcessError:
            return None

    def query(self, package: str) -> PkgConfigResult:
        """Query package information from pkg-config.

        Args:
            package: Name of the package to query

        Returns:
            PkgConfigResult containing extracted information

        Raises:
            subprocess.CalledProcessError: If package not found or other error
        """
        cflags = self._run_pkg_config(["--cflags"], package)
        libs = self._run_pkg_config(["--libs"], package)

        result = PkgConfigResult(
            libraries=set(),  # Will be populated below
            include_dirs=set(),  # Will be populated below
            cflags=cflags,
            libs=libs
        )

        # Use PkgConfigResult's extract_values method
        result.libraries = result._extract_values(libs, "-l")
        result.include_dirs = result._extract_values(cflags, "-I")

        return result
