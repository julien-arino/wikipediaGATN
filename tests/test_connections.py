"""
Tests for :mod:`wikipediaGATN.connections`.

Functions that read the filesystem (``create_outbound_connections_list``)
use real temp-directory fixtures populated with minimal JSON files, and
``PUBLIC_DATA_DIR`` is monkeypatched at the module level so no real data
directory is touched.
"""

import json
import os
from pathlib import Path

import pytest

from wikipediaGATN.connections import create_outbound_connections_list

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def data_dirs(tmp_path, monkeypatch):
    """
    Create public/ sub-directory, monkeypatch module-level path constants,
    and return the public directory path.
    """
    public = tmp_path / "public"
    public.mkdir()
    airport_data = public / "airport_data"
    airport_data.mkdir()
    monkeypatch.setattr("wikipediaGATN.connections.PUBLIC_DATA_DIR", public)

    tmp_results = tmp_path / "tmp_results"
    tmp_results.mkdir()
    monkeypatch.setattr("wikipediaGATN.connections.TEMP_RESULTS_DIR", tmp_results)

    return public


def _write_airport_json(public: Path, iata: str, destinations: list = None) -> Path:
    """Write a minimal airport JSON fixture to public/airport_data and return its path."""
    data = {
        "iata": iata,
        "wikipedia_url": f"https://en.wikipedia.org/wiki/{iata}_Airport",
        "destinations": destinations or [],
    }
    path = public / "airport_data" / f"{iata}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# create_outbound_connections_list
# ---------------------------------------------------------------------------


class TestCreateOutboundConnectionsList:

    def test_raises_when_airport_data_dir_missing(self, tmp_path, monkeypatch):
        """FileNotFoundError when airport_data directory does not exist."""
        public = tmp_path / "public"
        public.mkdir()
        # airport_data is NOT created
        monkeypatch.setattr("wikipediaGATN.connections.PUBLIC_DATA_DIR", public)
        with pytest.raises(FileNotFoundError):
            create_outbound_connections_list(verbose=False)

    def test_returns_tuple_of_three_strings(self, data_dirs):
        """Returns ``(connections_csv, cargo_csv, unmapped_csv_or_None)``."""
        public = data_dirs
        _write_airport_json(public, "YWG", destinations=[])
        result = create_outbound_connections_list(verbose=False, export_unmapped=False)
        assert isinstance(result, tuple) and len(result) == 3
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_connections_csv_created(self, data_dirs):
        """global-air-pax-network.csv is written to PUBLIC_DATA_DIR."""
        public = data_dirs
        _write_airport_json(public, "YWG", destinations=[])
        csv_path, _, _ = create_outbound_connections_list(verbose=False)
        assert os.path.exists(csv_path)
        assert "global-air-pax-network.csv" in csv_path

    def test_connections_csv_contains_origin(self, data_dirs):
        """The origin IATA code appears in global-air-pax-network.csv."""
        public = data_dirs
        _write_airport_json(public, "YWG", destinations=[])
        csv_path, _, _ = create_outbound_connections_list(verbose=False)
        with open(csv_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "YWG" in content

    def test_destinations_from_json_included(self, data_dirs):
        """A destination already mapped in the JSON is included in the CSV."""
        public = data_dirs
        # Destinations in the new dict format
        destinations = [
            {
                "name": "Toronto Pearson",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Toronto_Pearson_International_Airport",
                "codes": ["YYZ", "CYYZ"],
            }
        ]
        _write_airport_json(public, "YWG", destinations=destinations)
        csv_path, _, _ = create_outbound_connections_list(verbose=False)
        with open(csv_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "YYZ" in content

    def test_unmapped_csv_none_when_export_false(self, data_dirs):
        """unmapped_csv is None when export_unmapped=False."""
        public = data_dirs
        _write_airport_json(public, "YWG")
        _, _, unmapped = create_outbound_connections_list(
            verbose=False, export_unmapped=False
        )
        assert unmapped is None

    def test_unmapped_csv_written_when_destinations_unresolved(self, data_dirs):
        """unmapped_destinations.csv is written when URLs cannot be resolved."""
        public = data_dirs
        # Destination with URL but NO codes
        destinations = [
            {
                "name": "Unknown Airport",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Nowhere",
                "codes": [],
            }
        ]
        _write_airport_json(public, "YWG", destinations=destinations)
        _, _, unmapped = create_outbound_connections_list(
            verbose=False, export_unmapped=True
        )
        # The URL had no mapping, so unmapped file should exist
        assert unmapped is not None
        assert os.path.exists(unmapped)

    def test_corrupt_json_skipped_without_crash(self, data_dirs):
        """A corrupt JSON file is skipped with a warning; valid files still processed."""
        public = data_dirs
        (public / "airport_data" / "BAD.json").write_text(
            "{not valid json}", encoding="utf-8"
        )
        _write_airport_json(public, "YWG", destinations=[])
        # Should not raise
        csv_path, _, _ = create_outbound_connections_list(verbose=False)
        assert os.path.exists(csv_path)
