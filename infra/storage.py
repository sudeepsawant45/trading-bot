# ============================================================
# infra/storage.py — Atomic File Storage
# Prevents data corruption on system crash
# ============================================================
import json
import os
from pathlib import Path
from infra.logger import get_logger

log = get_logger("Storage")

def save_json(data: dict, filepath: Path) -> bool:
    """
    Atomically save JSON to disk.
    Writes to .tmp first, then os.replace() — crash-safe.
    .tmp is cleaned up even if os.replace() fails.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp = filepath.with_suffix(".tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, filepath)
        return True
    except Exception as e:
        log.error(f"Failed to save {filepath}: {e}")
        return False
    finally:
        # Always clean up .tmp even if replace() failed
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass

def load_json(filepath: Path) -> dict:
    """
    Load JSON from disk. Returns empty dict on any error.
    Handles corrupted files gracefully.
    """
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        log.error(f"Corrupted JSON {filepath}: {e}. Returning empty dict.")
        # Backup corrupted file for debugging
        bak = filepath.with_suffix(".corrupted")
        try:
            os.replace(filepath, bak)
            log.warning(f"Corrupted file backed up to {bak}")
        except Exception:
            pass
        return {}
    except Exception as e:
        log.error(f"Failed to load {filepath}: {e}")
        return {}
