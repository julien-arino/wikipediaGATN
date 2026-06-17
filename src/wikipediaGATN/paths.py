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

# ---------------------------------------------------------------------------
# Repo root — always absolute, regardless of how Python was invoked.
# This file lives at src/wikipediaGATN/paths.py, so two .parent calls
# walk up to the repository root.
# ---------------------------------------------------------------------------
_THIS_FILE: Path = Path(__file__).resolve()
REPO_ROOT: Path = _THIS_FILE.parent.parent.parent  # …/src/wikipediaGATN → src → repo

# ---------------------------------------------------------------------------
# Data root — can be overridden via environment variable for testing.
# ---------------------------------------------------------------------------
_env_override = os.environ.get("WIKIPEDIAGATN_DATA_DIR")

DATA_DIR: Path
if _env_override:
    DATA_DIR = Path(_env_override).resolve()
elif (REPO_ROOT / "pyproject.toml").exists() and (REPO_ROOT / "data").exists():
    DATA_DIR = REPO_ROOT / "data"
else:
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
