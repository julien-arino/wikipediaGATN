"""
Single source of truth for package version and the Wikipedia User-Agent.

The version is read from the installed package metadata so it can never drift
from ``pyproject.toml``.  When the code is run from a source checkout that has
not been installed (no ``*.dist-info``), we fall back to the hard-coded string
below, which should match ``pyproject.toml``.

Wikimedia's bot policy requires a descriptive User-Agent that identifies the
software and gives a real contact address, so a single shared constant is used
for every HTTP request the package makes.
"""

from importlib.metadata import PackageNotFoundError, version

#: Fallback used only when running from an uninstalled source tree.
_FALLBACK_VERSION = "0.1.4"

try:
    __version__ = version("wikipediaGATN")
except PackageNotFoundError:  # pragma: no cover - only hit in uninstalled trees
    __version__ = _FALLBACK_VERSION

#: Contact address exposed to Wikimedia per their User-Agent policy.
CONTACT = "julien.arino@umanitoba.ca"

#: Shared User-Agent for every request to Wikipedia / the Wikimedia APIs.
USER_AGENT = (
    f"wikipediaGATN/{__version__} "
    f"(https://github.com/julien-arino/wikipediaGATN; {CONTACT}) "
    "python-requests"
)

__all__ = ["__version__", "USER_AGENT", "CONTACT"]
