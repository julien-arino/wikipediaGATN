"""
Canonical filesystem paths for the wikipediaGATN package.

All modules import their directory constants from here so that path logic
is defined exactly once.  The directory layout assumed by this module is::

    <repo_root>/
    ├── src/
    │   └── wikipediaGATN/   ← this file lives here (two levels below repo root)
    │       └── paths.py
    └── data/
        ├── tmp_results/     ← TEMP_RESULTS_DIR  (raw scraper output)
        └── public/          ← PUBLIC_DATA_DIR   (CSVs, matrices, network graphs)

Environment variable override
------------------------------
Set ``WIKIPEDIAGATN_DATA_DIR`` to redirect all data I/O to a different
directory.  This is primarily useful for testing::

    WIKIPEDIAGATN_DATA_DIR=/tmp/test_data pytest

When the variable is set, ``DATA_DIR``, ``TEMP_RESULTS_DIR``, and
``PUBLIC_DATA_DIR`` all resolve relative to the override root instead of the
repository root.
"""

import os
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------
_THIS_FILE: Path = Path(__file__).resolve()


def _find_repo_root(start_path: Path) -> Optional[Path]:
    """
    Search upwards from start_path for the repository root.
    The root is identified by the presence of 'pyproject.toml' containing 'wikipediaGATN'.
    """
    # Start searching from the parent of the current file
    for parent in [start_path] + list(start_path.parents):
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            try:
                with open(pyproject, "r", encoding="utf-8") as f:
                    content = f.read()
                    # Look for the project name in pyproject.toml
                    if 'name = "wikipediaGATN"' in content:
                        return parent
            except Exception:
                pass
    return None


REPO_ROOT: Optional[Path] = _find_repo_root(_THIS_FILE)

# ---------------------------------------------------------------------------
# Data root — can be overridden via environment variable for testing.
# ---------------------------------------------------------------------------
_env_override = os.environ.get("WIKIPEDIAGATN_DATA_DIR")

DATA_DIR: Path
if _env_override:
    DATA_DIR = Path(_env_override).resolve()
elif REPO_ROOT and (REPO_ROOT / "data").exists():
    # If we are in the source repository, use the bundled data directory
    DATA_DIR = REPO_ROOT / "data"
else:
    # Default to "data" in the current working directory for installed packages
    DATA_DIR = Path.cwd() / "data"

# ---------------------------------------------------------------------------
# Subdirectories
# ---------------------------------------------------------------------------

#: Temporary directory for raw JSON files produced by the Wikipedia scraper.
TEMP_RESULTS_DIR: Path = DATA_DIR / "tmp_results"

#: Directory for processed, public-facing outputs (CSVs, sparse matrices, network graphs).
PUBLIC_DATA_DIR: Path = DATA_DIR / "public"

# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------
__all__ = [
    "REPO_ROOT",
    "DATA_DIR",
    "TEMP_RESULTS_DIR",
    "PUBLIC_DATA_DIR",
]
