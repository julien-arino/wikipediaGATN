"""
Pytest configuration and shared fixtures for wikipediaGATN tests.

Custom markers
--------------
network
    Tests that require a live internet connection or real scraped data on disk.
    Skip them in CI with:

        pytest -m "not network"

    Run them explicitly with:

        pytest -m network

Isolation
---------
The ``public_dir`` and ``tmp_results_dir`` fixtures in the individual test
modules monkeypatch the module-level ``PUBLIC_DATA_DIR`` and
``TEMP_RESULTS_DIR`` path constants so that no test ever touches the real
``data/`` directory.
"""

import pytest


def pytest_configure(config):
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "network: marks tests that require a live internet connection or "
        "real scraped data (deselect with -m 'not network')",
    )
