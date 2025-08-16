"""
Header file preprocessing and macro extraction for pybindlib.
"""

# Standard library imports
import importlib
import re
import subprocess

# Local imports
from .logging import logger


def process_headers(
    header_files: list[str],
    include_paths: list[str] = None,
    referenced_modules: list[str] = None,
) -> dict[str, str]:
    """
    Process C header files using cpp to extract macro definitions.

    Args:
        header_files: List of header files to process
        include_paths: Optional list of additional include paths
        referenced_modules: Optional list of pre-built modules to check for constants

    Returns:
        Dictionary mapping macro names to their values
    """
    # First try to import referenced modules and collect their constants
    existing_constants = {}
    if referenced_modules:
        import sys

        # Add current directory to path to find local modules
        if "" not in sys.path:
            sys.path.insert(0, "")

        for module_name in referenced_modules:
            try:
                # Import the module directly
                logger.debug(f"Importing module {module_name}")
                module = importlib.import_module(module_name)
                # Get the constants from the module's namespace
                for name in dir(module):
                    if not name.startswith("_"):
                        logger.debug(f"Found constant {name} in {module_name}")
                        existing_constants[name] = True
            except (ImportError, AttributeError) as e:
                logger.warning(
                    f"Could not import constants from {module_name}: {e}"
                )

    if not header_files:
        return {}

    # Build cpp command base with include paths
    cpp_cmd = ["cpp", "-dM"]
    if include_paths:
        for path in include_paths:
            cpp_cmd.extend(["-I", path])

    macros = {}

    def _parse_cpp_output(text: str) -> None:
        for line in text.splitlines():
            if not line.startswith("#define"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            name = parts[1]
            value = parts[2] if len(parts) > 2 else None
            # Skip if this constant already exists in a referenced module
            if name in existing_constants:
                continue
            # Skip function-like macros and built-ins
            if "(" in name or name.startswith("__"):
                continue
            # Convert value to Python
            if value:
                try:
                    # Strip outer parentheses if present
                    while value.startswith("(") and value.endswith(")"):
                        value = value[1:-1].strip()
                    # Handle C-style casts
                    cast_patterns = [
                        r"\((void\s*\*|long|int|unsigned|float|double|char|short|size_t|unsigned\s+\w+)\s*\)",
                        r"\((const\s+)?(void\s*\*|char\s*\*)\s*\)",
                        r"\((unsigned\s+long(\s+long)?|long(\s+long)?(\s+int)?)\s*\)",
                    ]
                    for pattern in cast_patterns:
                        if re.match(pattern, value):
                            value = value.split(")", 1)[1].strip()
                            while value.startswith("(") and value.endswith(")"):
                                value = value[1:-1].strip()
                            break
                    # Handle scientific notation floats
                    sci_match = re.match(r"^[+-]?\d+(?:\.\d+)?[eE][+-]?\d+(?:[fFlL])?$", value)
                    if sci_match:
                        # Strip float suffixes if present
                        suffix = value[-1]
                        if suffix in ("f", "F", "l", "L"):
                            value_num = value[:-1]
                        else:
                            value_num = value
                        try:
                            value = str(float(value_num))
                        except ValueError:
                            logger.debug(f"Invalid scientific float for {name}: {value}")
                            return
                    # Handle hex/octal numbers
                    elif value.startswith("0x") or value.startswith("0X"):
                        try:
                            if value.endswith(("l", "L")):
                                value = value[:-1]
                            value = str(int(value, 16))
                        except ValueError:
                            logger.debug(
                                f"Invalid hex value for {name}: {value}"
                            )
                            return
                    elif value.startswith("0") and value not in ("0",):
                        try:
                            if value.endswith(("l", "L")):
                                value = value[:-1]
                            value = str(int(value, 8))
                        except ValueError:
                            logger.debug(
                                f"Invalid octal value for {name}: {value}"
                            )
                            return
                    # Handle decimal numbers (ints and simple floats)
                    elif value.replace(".", "", 1).replace("l", "", 1).replace(
                        "L", "", 1
                    ).isdigit() or (
                        value.startswith("-") and value[1:].isdigit()
                    ):
                        try:
                            if value.endswith(("l", "L")):
                                value = value[:-1]
                            if "." in value:
                                value = str(float(value))
                            else:
                                value = str(int(value))
                        except ValueError:
                            logger.debug(
                                f"Invalid decimal value for {name}: {value}"
                            )
                            return
                    # String literals
                    elif (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        try:
                            if value[0] == '"':
                                value = (
                                    value[1:-1]
                                    .encode("utf-8")
                                    .decode("unicode_escape")
                                )
                            else:
                                value = value[1:-1]
                            value = repr(value)
                        except (UnicodeError, ValueError):
                            logger.debug(
                                f"Invalid string value for {name}: {value}"
                            )
                            return
                    else:
                        # Any other value that still contains identifiers should be skipped
                        ident_tokens = re.findall(
                            r"[A-Za-z_][A-Za-z0-9_]*", value
                        )
                        if ident_tokens:
                            logger.debug(
                                f"Skipping macro with unresolved identifiers {name} = {value}"
                            )
                            return
                        logger.debug(
                            f"Skipping non-literal macro {name} = {value}"
                        )
                        return
                    # Final validation - ensure it's a valid Python literal
                    try:
                        compile(value, "<string>", "eval")
                    except (SyntaxError, ValueError):
                        logger.debug(
                            f"Invalid Python literal for {name}: {value}"
                        )
                        return
                except (ValueError, SyntaxError) as e:
                    logger.debug(f"Error processing {name}: {value} - {str(e)}")
                    return
            else:
                value = "1"
            logger.debug(f"Adding constant {name} = {value}")
            macros[name] = value

    # Process each header file
    for header in header_files:
        try:
            cmd = cpp_cmd + [header]
            result = subprocess.run(
                cmd, check=False, capture_output=True, text=True
            )
            if result.returncode != 0:
                logger.warning(
                    f"Failed to preprocess {header}: {result.stderr}"
                )
                continue
            _parse_cpp_output(result.stdout)
        except Exception as e:
            logger.warning(f"Error processing {header}: {e}")

    return macros


def parse_function_pointer_typedefs(header_files: list[str]) -> set[str]:
    """
    Scan header files and collect typedef names that define function pointers.
    This is a best-effort regex-based extractor to fill missing typedefs when
    DWARF info is not available.

    Returns:
        Set of typedef identifiers, e.g., {'ACQUIRE_CREDENTIALS_HANDLE_FN_A'}
    """
    fn_typedef_names: set[str] = set()
    if not header_files:
        return fn_typedef_names

    # Regex: typedef <ret> (<cc>* Name) (args...);
    pattern = re.compile(
        r"typedef\s+[^;\n]*\(\s*[^)]*\*\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\([^;]*\)\s*;"
    )

    for path in header_files:
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
                for match in pattern.finditer(text):
                    name = match.group(1)
                    if name and name.isidentifier():
                        fn_typedef_names.add(name)
        except Exception as e:
            logger.debug(f"Failed to read header {path}: {e}")

    return fn_typedef_names
