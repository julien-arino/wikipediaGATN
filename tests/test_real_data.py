"""
Integration tests against real scraped data.

These tests require ``TEMP_RESULTS_DIR`` to contain at least one valid airport
JSON file (i.e. the Wikipedia scraping step has been run).  They are marked
``network`` so they can be skipped in CI:

    pytest -m "not network"

or run explicitly on a machine that has the data:

    pytest -m network tests/test_real_data.py -v
"""

import csv
import os

import pytest

from wikipediaGATN.connections import create_outbound_connections_list
from wikipediaGATN.paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR
from wikipediaGATN.result_processing_airports import (
    check_duplicated_iata_codes,
    export_all_airport_data,
)

# ---------------------------------------------------------------------------
# Module-level skip: all tests in this file require real scraped data.
# ---------------------------------------------------------------------------

def _count_json_files() -> int:
    if not os.path.isdir(TEMP_RESULTS_DIR):
        return 0
    return sum(1 for f in os.listdir(TEMP_RESULTS_DIR) if f.endswith(".json"))


pytestmark = pytest.mark.network


@pytest.fixture(scope="module", autouse=True)
def require_scraped_data():
    """Skip every test in this module when no JSON files are present."""
    n = _count_json_files()
    if n == 0:
        pytest.skip(
            f"No JSON files found in {TEMP_RESULTS_DIR}. "
            "Run the Wikipedia scraping step first, or use "
            "pytest -m 'not network' to skip these tests."
        )
    return n


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExportAllAirportData:

    def test_creates_airports_information_csv(self):
        """export_all_airport_data writes airports_information.csv."""
        csv_path = export_all_airport_data(verbose=False)
        assert os.path.exists(csv_path), f"Expected {csv_path} to exist"
        assert "airports_information.csv" in csv_path

    def test_airports_csv_has_expected_columns(self):
        """airports_information.csv contains the required column headers."""
        export_all_airport_data(verbose=False)
        expected = {"iata", "icao", "latitude", "longitude",
                    "name", "wikipedia_url", "outdegree"}
        csv_path = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")
        with open(csv_path, encoding="utf-8") as fh:
            headers = set(next(csv.reader(fh)))
        assert expected.issubset(headers), \
            f"Missing columns: {expected - headers}"

    def test_airports_csv_non_empty(self):
        """airports_information.csv has at least one data row."""
        export_all_airport_data(verbose=False)
        csv_path = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")
        with open(csv_path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) > 0, "airports_information.csv has no data rows"

    def test_airports_csv_iata_codes_uppercase(self):
        """IATA codes present in the CSV are 3 uppercase letters."""
        export_all_airport_data(verbose=False)
        csv_path = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")
        with open(csv_path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                iata = row.get("iata", "").strip()
                if iata:
                    assert iata == iata.upper(), f"Lowercase IATA: {iata!r}"
                    assert len(iata) == 3, f"Non-3-letter IATA: {iata!r}"

    def test_returns_absolute_path(self):
        """Return value is an absolute path string."""
        path = export_all_airport_data(verbose=False)
        assert os.path.isabs(path), f"Expected absolute path, got: {path!r}"


class TestCheckDuplicatedIataCodes:

    def test_returns_int(self):
        """Returns an integer count of duplicates removed."""
        result = check_duplicated_iata_codes(verbose=False)
        assert isinstance(result, int)
        assert result >= 0

    def test_no_duplicates_after_running(self):
        """Running a second time finds no additional duplicates."""
        check_duplicated_iata_codes(verbose=False)
        second_pass = check_duplicated_iata_codes(verbose=False)
        assert second_pass == 0, \
            f"Second dedup pass still found {second_pass} duplicate(s)"


class TestCreateOutboundConnectionsList:

    def test_creates_connections_csv(self):
        """create_outbound_connections_list writes global-air-transportation-network.csv."""
        export_all_airport_data(verbose=False)
        connections_csv, _ = create_outbound_connections_list(
            verbose=False, export_unmapped=True
        )
        assert os.path.exists(connections_csv), \
            f"Expected {connections_csv} to exist"

    def test_connections_csv_has_expected_columns(self):
        """global-air-transportation-network.csv has origin, nb_outlinks, outlinks columns."""
        export_all_airport_data(verbose=False)
        create_outbound_connections_list(verbose=False)
        csv_path = os.path.join(PUBLIC_DATA_DIR, "global-air-transportation-network.csv")
        with open(csv_path, encoding="utf-8") as fh:
            headers = set(next(csv.reader(fh)))
        assert {"origin", "nb_outlinks", "outlinks"}.issubset(headers)

    def test_connections_csv_non_empty(self):
        """global-air-transportation-network.csv has at least one data row."""
        export_all_airport_data(verbose=False)
        create_outbound_connections_list(verbose=False)
        csv_path = os.path.join(PUBLIC_DATA_DIR, "global-air-transportation-network.csv")
        with open(csv_path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) > 0

    def test_unmapped_csv_created_when_requested(self):
        """unmapped_destinations.csv is written when export_unmapped=True."""
        export_all_airport_data(verbose=False)
        connections_csv, unmapped_csv = create_outbound_connections_list(
            verbose=False, export_unmapped=True
        )
        # unmapped_csv is None only when every destination was resolved
        if unmapped_csv is not None:
            assert os.path.exists(unmapped_csv)
            assert "unmapped_destinations.csv" in unmapped_csv

    def test_origin_codes_are_valid_iata(self):
        """All origin codes in global-air-transportation-network.csv are 3 uppercase letters."""
        import re
        _IATA = re.compile(r"^[A-Z]{3}$")
        export_all_airport_data(verbose=False)
        create_outbound_connections_list(verbose=False)
        csv_path = os.path.join(PUBLIC_DATA_DIR, "global-air-transportation-network.csv")
        with open(csv_path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                origin = row.get("origin", "").strip()
                assert _IATA.match(origin), \
                    f"Invalid origin IATA in connections CSV: {origin!r}"
