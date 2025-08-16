"""
pybindlib - Generate Python ctypes bindings from shared
libraries.
"""

__version__ = "0.1.0"

from .logging import logger

__all__: list[str] = [
    "__version__",
    "identifiers",
    "logger",
    "output",
    "progress",
]
