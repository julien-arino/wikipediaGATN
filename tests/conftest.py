"""
Pytest configuration and shared fixtures for wikipediaGATN tests.

Custom markers
--------------
network
    Tests that require a live internet connection.  Skip them in CI with::

        pytest -m "not network"

    Run them explicitly with::

        pytest -m network

Isolation
---------
The ``public_dir`` and ``tmp_results_dir`` fixtures in the individual test
modules monkeypatch the module-level ``PUBLIC_DATA_DIR`` and
``TEMP_RESULTS_DIR`` path constants so that no test ever touches the real
``data/`` directory.

The shared ``isolated_data_dir`` fixture below goes further: it builds a
complete temporary ``data/public`` tree seeded from the committed
``tests/fixtures`` and redirects *every* module's path constants to it, so the
higher-level pipeline functions (``export_all_airport_data``,
``create_outbound_connections_list``, ...) can run fully offline against a small
deterministic dataset instead of a live crawl.
"""

import shutil
from pathlib import Path

import pytest

#: Directory holding committed test fixtures (small airport JSON files, a
#: minimal OurAirports CSV, ...).
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def pytest_configure(config):
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "network: marks tests that require a live internet connection "
        "(deselect with -m 'not network')",
    )


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Build an isolated ``data/`` tree seeded from ``tests/fixtures``.

    Creates ``<tmp>/data/public/airport_data`` populated with the committed
    fixture airports and a minimal ``ourairports.csv`` cache (so no download is
    attempted), plus an empty ``<tmp>/data/tmp_results``.  All path constants —
    both the source ``wikipediaGATN.paths`` values (re-imported at call time by
    some helpers) and the copies bound at import time in the individual modules —
    are redirected here, and the OurAirports in-memory cache is reset.

    Returns the ``public`` directory as a :class:`pathlib.Path`.
    """
    data_dir = tmp_path / "data"
    public_dir = data_dir / "public"
    airport_data_dir = public_dir / "airport_data"
    tmp_results_dir = data_dir / "tmp_results"
    airport_data_dir.mkdir(parents=True)
    tmp_results_dir.mkdir(parents=True)
    # Scraper sweep dir that check_duplicated_iata_codes requires to exist.
    (tmp_results_dir / "airports_rooted_sweep").mkdir()

    # Seed the fixture airports and the minimal OurAirports cache.
    for src in (FIXTURES_DIR / "airport_data").glob("*.json"):
        shutil.copy(src, airport_data_dir / src.name)
    shutil.copy(FIXTURES_DIR / "ourairports.csv", public_dir / "ourairports.csv")

    # Redirect the source constants (re-imported at call time by helpers such as
    # _load_ourairports_data and build_url_to_codes_map).
    monkeypatch.setattr("wikipediaGATN.paths.DATA_DIR", data_dir, raising=False)
    monkeypatch.setattr("wikipediaGATN.paths.PUBLIC_DATA_DIR", public_dir)
    monkeypatch.setattr("wikipediaGATN.paths.TEMP_RESULTS_DIR", tmp_results_dir)

    # Redirect the copies bound at import time in each module.
    for module in (
        "wikipediaGATN.result_processing_airports",
        "wikipediaGATN.connections",
        "wikipediaGATN.adjacency",
    ):
        monkeypatch.setattr(f"{module}.PUBLIC_DATA_DIR", public_dir, raising=False)
        monkeypatch.setattr(
            f"{module}.TEMP_RESULTS_DIR", tmp_results_dir, raising=False
        )

    # Reset the OurAirports cache so it re-reads our fixture CSV.
    monkeypatch.setattr(
        "wikipediaGATN.airport_level_functions._OURAIRPORTS_CACHE", None, raising=False
    )

    return public_dir
