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

Resolution order
----------------
``DATA_DIR`` (the writable root for scraper output and exports) is resolved as:

1. ``WIKIPEDIAGATN_DATA_DIR`` if set;
2. ``<repo_root>/data`` when running from a source checkout;
3. ``<cwd>/data`` otherwise.

``PUBLIC_DATA_DIR`` normally sits at ``DATA_DIR/public``.  When that directory
does not exist — the typical case for a plain ``pip install`` with no local
crawl — it falls back to the **pre-built network data bundled inside the
installed wheel** (``wikipediaGATN/_data/public``), so reading the published
networks works out of the box.  This fallback is read-only: to run your own
crawl, point ``WIKIPEDIAGATN_DATA_DIR`` at a writable directory.
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


def _packaged_public_dir() -> Optional[Path]:
    """Locate pre-built network data bundled inside the installed package.

    Returns the ``wikipediaGATN/_data/public`` directory shipped in the wheel
    (via hatch ``force-include``; see ``pyproject.toml``), or ``None`` when the
    package carries no bundled data — e.g. an editable/source install, where
    the repository ``data/`` directory is used instead.
    """
    try:
        from importlib.resources import files

        public = files("wikipediaGATN").joinpath("_data", "public")
        public_path = Path(str(public))
    except (ModuleNotFoundError, TypeError, ValueError, NotImplementedError):
        return None
    return public_path if public_path.is_dir() else None


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


def _resolve_public_dir(data_dir: Path, bundled: Optional[Path]) -> Path:
    """Choose the public-data directory.

    Prefer ``data_dir/public``; fall back to the wheel-bundled ``bundled``
    directory only when the local one does not exist.  Kept as a small pure
    function so the fallback is directly testable.
    """
    local = data_dir / "public"
    if not local.exists() and bundled is not None:
        return bundled
    return local


#: Directory for processed, public-facing outputs (CSVs, sparse matrices, network
#: graphs).  Falls back to the data bundled inside the installed wheel when no
#: local ``public`` directory exists, so a plain ``pip install`` can read the
#: pre-built networks without a prior crawl (see module docstring).
PUBLIC_DATA_DIR: Path = _resolve_public_dir(DATA_DIR, _packaged_public_dir())

# ---------------------------------------------------------------------------
# Windows-reserved filename handling
# ---------------------------------------------------------------------------
# A handful of real airport codes (e.g. AUX = Araguaína, NUL = Nulato,
# PRN = Pristina) collide with Windows reserved device names.  A file whose
# base name — the part before the first dot — is one of these cannot be created
# or checked out on Windows (``git clone`` fails with "invalid path").  We store
# such codes with a trailing underscore on disk (``AUX`` -> ``AUX_.json``) and
# strip it again when recovering the code, so the in-memory code is always the
# real one.  Matching is case-insensitive and ignores any extension.

#: Windows reserved device names (without extension), upper-cased.
_WINDOWS_RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def is_reserved_code(code: str) -> bool:
    """Return True if ``code`` collides with a Windows reserved device name."""
    return code.upper() in _WINDOWS_RESERVED_NAMES


def escape_reserved_code(code: str) -> str:
    """Return a filesystem-safe stem for ``code``.

    Appends a single underscore to Windows reserved device names (``AUX`` ->
    ``AUX_``); all other codes are returned unchanged.  Inverse of
    :func:`unescape_reserved_code`.
    """
    return f"{code}_" if is_reserved_code(code) else code


def unescape_reserved_code(stem: str) -> str:
    """Recover an airport code from an on-disk stem.

    Strips the trailing underscore added by :func:`escape_reserved_code` when,
    and only when, the remaining stem is a Windows reserved device name.  A
    ``.json`` (or other) extension, if present, is ignored and preserved-free:
    pass the stem without extension.
    """
    if stem.endswith("_") and is_reserved_code(stem[:-1]):
        return stem[:-1]
    return stem


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------
__all__ = [
    "REPO_ROOT",
    "DATA_DIR",
    "TEMP_RESULTS_DIR",
    "PUBLIC_DATA_DIR",
    "is_reserved_code",
    "escape_reserved_code",
    "unescape_reserved_code",
]
