import sys
from unittest.mock import MagicMock

# Global mocking of dependencies to allow import in this environment
mock_mods = [
    "pandas", "numpy", "scipy", "scipy.sparse", "requests",
    "bs4", "mwparserfromhell", "pycountry", "geopy", "geopy.point"
]
for mod in mock_mods:
    sys.modules[mod] = MagicMock()
if "requests.exceptions" not in sys.modules:
    sys.modules["requests.exceptions"] = MagicMock()

import pytest


def pytest_configure(config):
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "network: marks tests that require a live internet connection or "
        "real scraped data (deselect with -m 'not network')",
    )
