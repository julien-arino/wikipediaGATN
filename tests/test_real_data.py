"""
Integration tests for the high-level pipeline functions.

These exercise ``export_all_airport_data``, ``check_duplicated_iata_codes`` and
``create_outbound_connections_list`` end to end against a small, committed
fixture dataset (see ``tests/fixtures`` and the ``isolated_data_dir`` fixture in
``conftest.py``).  Everything runs offline in a temporary directory, so the
tests are deterministic and never touch the real ``data/`` tree or the network.

Previously these required a prior live crawl (and wrote into the real
``data/public``); they were marked ``network`` and skipped in CI, so the
pipeline went untested.  They now build their own fixture instead.
"""

import csv
import json
import os

from wikipediaGATN.connections import create_outbound_connections_list
from wikipediaGATN.result_processing_airports import (
    check_duplicated_iata_codes,
    export_all_airport_data,
)

# The three airports provided by the committed fixtures.
FIXTURE_IATA = {"YWG", "YYC", "AUX"}


class TestExportAllAirportData:

    def test_creates_airports_information_csv(self, isolated_data_dir):
        csv_path = export_all_airport_data(verbose=False)
        assert os.path.exists(csv_path), f"Expected {csv_path} to exist"
        assert "airports_information.csv" in csv_path

    def test_airports_csv_has_expected_columns(self, isolated_data_dir):
        export_all_airport_data(verbose=False)
        expected = {
            "iata",
            "icao",
            "latitude",
            "longitude",
            "name",
            "wikipedia_url",
            "outdegree",
            "outdegree_cargo",
            "number_airlines",
            "number_airlines_cargo",
        }
        csv_path = isolated_data_dir / "airports_information.csv"
        with open(csv_path, encoding="utf-8") as fh:
            headers = set(next(csv.reader(fh)))
        assert expected.issubset(headers), f"Missing columns: {expected - headers}"

    def test_airports_csv_has_all_fixture_rows(self, isolated_data_dir):
        export_all_airport_data(verbose=False)
        csv_path = isolated_data_dir / "airports_information.csv"
        with open(csv_path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        iatas = {r["iata"] for r in rows}
        assert FIXTURE_IATA.issubset(iatas), f"Missing airports: {FIXTURE_IATA - iatas}"

    def test_airports_csv_iata_codes_uppercase(self, isolated_data_dir):
        export_all_airport_data(verbose=False)
        csv_path = isolated_data_dir / "airports_information.csv"
        with open(csv_path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                iata = row.get("iata", "").strip()
                if iata:
                    assert iata == iata.upper(), f"Lowercase IATA: {iata!r}"
                    assert len(iata) == 3, f"Non-3-letter IATA: {iata!r}"

    def test_returns_absolute_path(self, isolated_data_dir):
        path = export_all_airport_data(verbose=False)
        assert os.path.isabs(path), f"Expected absolute path, got: {path!r}"

    def test_reserved_code_written_with_escaped_filename(self, isolated_data_dir):
        """The reserved code AUX is re-exported as the Windows-safe AUX_.json."""
        export_all_airport_data(verbose=False)
        airport_data_dir = isolated_data_dir / "airport_data"
        assert (airport_data_dir / "AUX_.json").exists()
        assert not (airport_data_dir / "AUX.json").exists()
        # And the data inside still carries the real code.
        data = json.loads((airport_data_dir / "AUX_.json").read_text(encoding="utf-8"))
        assert data["iata"] == "AUX"


class TestCheckDuplicatedIataCodes:

    def test_returns_zero_when_no_duplicates(self, isolated_data_dir):
        result = check_duplicated_iata_codes(verbose=False)
        assert result == 0

    def test_removes_higher_distance_duplicate(self, isolated_data_dir):
        sweep = isolated_data_dir.parent / "tmp_results" / "airports_rooted_sweep"
        (sweep / "YWG.0.json").write_text("{}", encoding="utf-8")
        (sweep / "YWG.1.json").write_text("{}", encoding="utf-8")
        removed = check_duplicated_iata_codes(verbose=False)
        assert removed == 1
        assert (sweep / "YWG.0.json").exists()
        assert not (sweep / "YWG.1.json").exists()

    def test_handles_reserved_code_duplicate(self, isolated_data_dir):
        """Dedup works for escaped reserved-code files (AUX_.<level>.json)."""
        sweep = isolated_data_dir.parent / "tmp_results" / "airports_rooted_sweep"
        (sweep / "AUX_.0.json").write_text("{}", encoding="utf-8")
        (sweep / "AUX_.1.json").write_text("{}", encoding="utf-8")
        removed = check_duplicated_iata_codes(verbose=False)
        assert removed == 1
        assert (sweep / "AUX_.0.json").exists()
        assert not (sweep / "AUX_.1.json").exists()


class TestCreateOutboundConnectionsList:

    def test_creates_connections_csv(self, isolated_data_dir):
        export_all_airport_data(verbose=False)
        connections_csv, _, _ = create_outbound_connections_list(
            verbose=False, export_unmapped=True
        )
        assert os.path.exists(connections_csv), f"Expected {connections_csv} to exist"

    def test_connections_csv_has_expected_columns(self, isolated_data_dir):
        export_all_airport_data(verbose=False)
        create_outbound_connections_list(verbose=False)
        csv_path = isolated_data_dir / "global-air-pax-network.csv"
        with open(csv_path, encoding="utf-8") as fh:
            headers = set(next(csv.reader(fh)))
        assert {"origin", "nb_outlinks", "outlinks"}.issubset(headers)

    def test_connections_csv_non_empty(self, isolated_data_dir):
        export_all_airport_data(verbose=False)
        create_outbound_connections_list(verbose=False)
        csv_path = isolated_data_dir / "global-air-pax-network.csv"
        with open(csv_path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) > 0

    def test_origin_codes_are_valid_iata(self, isolated_data_dir):
        import re

        _IATA = re.compile(r"^[A-Z]{3}$")
        export_all_airport_data(verbose=False)
        create_outbound_connections_list(verbose=False)
        csv_path = isolated_data_dir / "global-air-pax-network.csv"
        with open(csv_path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                origin = row.get("origin", "").strip()
                assert _IATA.match(origin), f"Invalid origin IATA: {origin!r}"

    def test_reserved_code_appears_as_origin(self, isolated_data_dir):
        """AUX (stored as AUX_.json) is read back as a valid origin node."""
        export_all_airport_data(verbose=False)
        create_outbound_connections_list(verbose=False)
        csv_path = isolated_data_dir / "global-air-pax-network.csv"
        with open(csv_path, encoding="utf-8") as fh:
            origins = {row["origin"] for row in csv.DictReader(fh)}
        assert "AUX" in origins
