# pybindlib
Generate Python ctypes bindings from shared libraries.

A tool to help generate Python ctypes bindings from shared libraries. It reads DWARF debug information from library files to understand C structures and types, then generates equivalent Python classes.

## Features

- Reads DWARF debug information to understand C types and structures
- Generates Python ctypes classes that match the C structures
- Handles complex type relationships and dependencies
- Creates proper Python modules with types, symbols, and constants submodules
- Provides clean imports like `from mylib.types import MyStruct`

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

## Installation

## Usage

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
