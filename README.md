# pybindlib
Generate Python ctypes bindings from shared libraries.

A tool to help generate Python ctypes bindings from shared libraries. It reads DWARF debug information from library files to understand C structures and types, then generates equivalent Python classes.

## Features

- Reads DWARF debug information to understand C types and structures
- Generates Python ctypes classes that match the C structures
- Handles complex type relationships and dependencies
- Creates proper Python modules with types, symbols, and constants submodules
- Provides clean imports like `from mylib.types import MyStruct`
- Extracts constants and macros from header files
- Automatically discovers library paths using pkg-config

## Requirements

- Python 3.12 or newer
- Debug symbols for the libraries you want to analyze:
  ```bash
  # Install debug symbols for a specific package
  sudo dnf debuginfo-install libfreerdp3

  # Or enable debuginfo repos and install manually
  sudo dnf install 'dnf-command(debuginfo-install)'
  sudo dnf debuginfo-install libfreerdp3
  ```
- C preprocessor (cpp) for header file analysis:
  ```bash
  # Install gcc which includes cpp
  sudo dnf install gcc
  ```
- pkg-config for library and include path discovery:
  ```bash
  # Install pkg-config
  sudo dnf install pkgconf-pkg-config
  ```

## Installation

## Usage

Generate bindings for a shared library:

```bash
# Basic usage
pybindlib /usr/lib/libexample.so

# Extract constants from headers
pybindlib --headers /usr/include/example.h /usr/lib/libexample.so

# Add include paths for header processing
pybindlib -I /usr/include -I /usr/local/include --headers /usr/include/example.h /usr/lib/libexample.so

# Specify output file
pybindlib -o bindings.py /usr/lib/libexample.so

# Process multiple libraries at once
pybindlib -o output/ libone.so libtwo.so

# Use pkg-config to find library and include paths
pybindlib --pkgconfig freerdp3 --headers /usr/include/freerdp3/freerdp.h

# Enable verbose output
pybindlib -v /usr/lib/libexample.so
```

The generated bindings provide a clean Python API:

```python
from ctypes import *
from example.types import MyStruct
from example.symbols import my_function
from example.constants import BUFFER_SIZE

# Create and use structures
structure = MyStruct()
structure.field = BUFFER_SIZE

# Call library functions
my_function.argtypes = [POINTER(MyStruct)]
my_function.restype = c_int
result = my_function(byref(structure))
```

## Development

To set up a development environment:

```bash
# Install Python 3.12 or newer
uv python install 3.12
# Optional: install shims for python/python3
uv python install --default

# Create a virtual environment
uv venv -p 3.12
# Optional: activate the environment
source .venv/bin/activate

# Sync dependencies (including dev tools)
uv sync

# Run tests
uv run pytest
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, workflow guidelines, and coding style.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
