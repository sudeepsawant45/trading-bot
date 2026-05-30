# ============================================================
# tests/conftest.py — Test Configuration
# Cleans up disk state before each test run
# Prevents tests from interfering with each other
# ============================================================
import pytest
import os
import glob
from pathlib import Path


@pytest.fixture(autouse=True)
def clean_state_files():
    """
    Auto-runs before every test.
    Deletes any saved RiskManager state files from disk
    so tests don't interfere with each other.
    """
    # Delete state files before test
    _cleanup()
    yield
    # Optionally clean after too
    _cleanup()


def _cleanup():
    """Remove all state JSON files created by RiskManager."""
    try:
        from infra.config import DATA_DIR, setup_dirs
        setup_dirs()
        # Remove state files
        for f in Path(DATA_DIR).glob("state_*.json"):
            f.unlink(missing_ok=True)
        # Remove tax files
        for f in Path(DATA_DIR).glob("tax_*.json"):
            f.unlink(missing_ok=True)
    except Exception:
        pass  # If config not available, skip cleanup
