"""Shared pytest fixtures.  Ensures the local packages are importable and the
API tests use an isolated temporary data directory."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reconstruction"))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))  # for the `eval` evaluation package


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: end-to-end test that runs full SfM")

# Point the backend at a throwaway data dir BEFORE app modules import config.
os.environ.setdefault(
    "DRISHTI_DATA_DIR", tempfile.mkdtemp(prefix="drishti_test_"))
