"""
Common test fixtures for pybindlib tests.
"""

import os
import pytest
import tempfile


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_file():
    """Create a temporary file."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
        yield tmp_path
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)