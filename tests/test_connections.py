"""
Tests for :mod:`wikipediaGATN.connections`.

Pure-function helpers (``_normalize_url``, ``_extract_airport_name_from_url``,
``_fuzzy_match_iata``) are tested directly.  Functions that read the
filesystem (``_build_url_to_iata_mapping``, ``create_outbound_connections_list``)
use real temp-directory fixtures populated with minimal CSV/JSON files, and
both ``TEMP_RESULTS_DIR`` and ``PUBLIC_DATA_DIR`` are monkeypatched at the
module level so no real data directory is touched.
"""

import csv
import json
import os
from pathlib import Path

import pytest

from wikipediaGATN.connections import (
    _build_url_to_iata_mapping,
    _extract_airport_name_from_url,
    _fuzzy_match_iata,
    _normalize_url,
    create_outbound_connections_list,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def data_dirs(tmp_path, monkeypatch):
    """
    Create tmp_results/ and public/ sub-directories, monkeypatch both
    module-level path constants, and return (tmp_results, public).
    """
    tmp_results = tmp_path / "tmp_results"
    public      = tmp_path / "public"
    tmp_results.mkdir()
    public.mkdir()
    monkeypatch.setattr("wikipediaGATN.connections.TEMP_RESULTS_DIR", tmp_results)
    monkeypatch.setattr("wikipediaGATN.connections.PUBLIC_DATA_DIR",  public)
    return tmp_results, public


def _write_airport_json(tmp_results: Path, iata: str, level: int,
                        destinations: list = None) -> Path:
    """Write a minimal airport JSON fixture and return its path."""
    data = {
        "iata":         iata,
        "wikipedia_url": f"https://en.wikipedia.org/wiki/{iata}_Airport",
        "destinations": destinations or [],
    }
    path = tmp_results / f"{iata}.{level}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_airports_csv(public: Path, rows: list) -> Path:
    """Write a minimal airports_information.csv."""
    path = public / "airports_information.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["iata", "wikipedia_url", "name"])
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# _normalize_url
# ---------------------------------------------------------------------------

class TestNormalizeUrl:

    def test_basic_lowercased(self):
        url = "https://en.wikipedia.org/wiki/Toronto_Pearson"
        assert _normalize_url(url) == "https://en.wikipedia.org/wiki/toronto_pearson"

    def test_trailing_slash_removed(self):
        result = _normalize_url("https://en.wikipedia.org/wiki/Toronto/")
        assert not result.endswith("/")

    def test_empty_string_returns_empty(self):
        assert _normalize_url("") == ""

    def test_none_returns_empty(self):
        assert _normalize_url(None) == ""

    def test_already_lowercase_unchanged(self):
        url = "https://en.wikipedia.org/wiki/example"
        assert _normalize_url(url) == url

    def test_percent_encoding_decoded(self):
        # %C3%A9 is é
        result = _normalize_url("https://en.wikipedia.org/wiki/Montr%C3%A9al")
        assert "%" not in result

    def test_result_is_always_lowercase(self):
        url = "HTTPS://EN.WIKIPEDIA.ORG/WIKI/EXAMPLE"
        assert _normalize_url(url) == _normalize_url(url).lower()


# ---------------------------------------------------------------------------
# _extract_airport_name_from_url
# ---------------------------------------------------------------------------

class TestExtractAirportNameFromUrl:

    def test_basic_extraction(self):
        url = "https://en.wikipedia.org/wiki/Toronto_Pearson_International_Airport"
        result = _extract_airport_name_from_url(url)
        assert result is not None
        # The URL title should contribute to the name
        assert "Toronto" in result or "Pearson" in result

    def test_airport_suffix_stripped(self):
        url = "https://en.wikipedia.org/wiki/Example_Airport"
        result = _extract_airport_name_from_url(url)
        if result:
            assert "airport" not in result.lower()

    def test_international_suffix_stripped(self):
        url = "https://en.wikipedia.org/wiki/Los_Angeles_International_Airport"
        result = _extract_airport_name_from_url(url)
        if result:
            assert "international" not in result.lower()

    def test_underscores_replaced_with_spaces(self):
        url = "https://en.wikipedia.org/wiki/Los_Angeles_International"
        result = _extract_airport_name_from_url(url)
        if result:
            assert "_" not in result

    def test_no_wiki_segment_returns_none(self):
        assert _extract_airport_name_from_url(
            "https://en.wikipedia.org/notawiki/Example"
        ) is None

    def test_empty_string_returns_none(self):
        assert _extract_airport_name_from_url("") is None

    def test_none_returns_none(self):
        assert _extract_airport_name_from_url(None) is None


# ---------------------------------------------------------------------------
# _fuzzy_match_iata
# ---------------------------------------------------------------------------

class TestFuzzyMatchIata:

    def test_exact_match_returns_code_and_high_ratio(self):
        iata_dict = {"Toronto Pearson": "YYZ"}
        code, ratio = _fuzzy_match_iata("Toronto Pearson", frozenset(iata_dict.items()))
        assert code == "YYZ"
        assert ratio >= 0.95

    def test_below_threshold_returns_none(self):
        iata_dict = {"Toronto Pearson": "YYZ"}
        code, ratio = _fuzzy_match_iata("Completely Different", frozenset(iata_dict.items()))
        assert code is None

    def test_empty_name_returns_none(self):
        code, ratio = _fuzzy_match_iata("", frozenset({"Toronto": "YYZ"}.items()))
        assert code is None
        assert ratio == 0.0

    def test_empty_dict_returns_none(self):
        code, ratio = _fuzzy_match_iata("Toronto Pearson", frozenset({}.items()))
        assert code is None
        assert ratio == 0.0

    def test_matching_is_case_insensitive(self):
        iata_dict = {"toronto pearson": "YYZ"}
        code_upper, _ = _fuzzy_match_iata("TORONTO PEARSON", frozenset(iata_dict.items()))
        code_lower, _ = _fuzzy_match_iata("toronto pearson", frozenset(iata_dict.items()))
        assert code_upper == "YYZ"
        assert code_lower == "YYZ"

    def test_returns_best_among_multiple_candidates(self):
        iata_dict = {
            "Montreal Trudeau":   "YUL",
            "Montreal Downtown":  "YMQ",
        }
        code, ratio = _fuzzy_match_iata("Montreal Trudeau", frozenset(iata_dict.items()))
        assert code == "YUL"

    def test_ratio_is_float(self):
        _, ratio = _fuzzy_match_iata("test", frozenset({"test airport": "TST"}.items()))
        assert isinstance(ratio, float)


# ---------------------------------------------------------------------------
# _build_url_to_iata_mapping
# ---------------------------------------------------------------------------

class TestBuildUrlToIataMapping:

    def test_returns_two_dicts(self, data_dirs):
        """Function always returns exactly two dicts."""
        url_to_iata, name_to_iata = _build_url_to_iata_mapping(verbose=False)
        assert isinstance(url_to_iata, dict)
        assert isinstance(name_to_iata, dict)

    def test_empty_when_no_source_files(self, data_dirs):
        """Both dicts are empty when no source CSVs exist."""
        url_to_iata, name_to_iata = _build_url_to_iata_mapping(verbose=False)
        assert url_to_iata == {}
        assert name_to_iata == {}

    def test_loads_airports_information_csv(self, data_dirs):
        """Entries from airports_information.csv are returned."""
        _, public = data_dirs
        _write_airports_csv(public, [
            {"iata": "YYZ",
             "wikipedia_url": "https://en.wikipedia.org/wiki/Toronto_Pearson",
             "name": "Toronto Pearson"},
        ])
        url_to_iata, name_to_iata = _build_url_to_iata_mapping(verbose=False)
        # URL is normalised (lowercased, slash-stripped)
        normalized = "https://en.wikipedia.org/wiki/toronto_pearson"
        assert url_to_iata.get(normalized) == "YYZ"

    def test_name_mapping_populated(self, data_dirs):
        """Name-to-IATA dict is populated from the name column."""
        _, public = data_dirs
        _write_airports_csv(public, [
            {"iata": "YUL",
             "wikipedia_url": "https://en.wikipedia.org/wiki/Montreal_YUL",
             "name": "Montreal Trudeau"},
        ])
        _, name_to_iata = _build_url_to_iata_mapping(verbose=False)
        assert "Montreal Trudeau" in name_to_iata
        assert name_to_iata["Montreal Trudeau"] == "YUL"

    def test_manual_mapping_overrides_airports_csv(self, data_dirs):
        """manual_airport_mapping.csv (highest priority) overrides airports_information.csv."""
        tmp_results, public = data_dirs
        # airports_information.csv has the "wrong" code
        _write_airports_csv(public, [
            {"iata": "OLD",
             "wikipedia_url": "https://en.wikipedia.org/wiki/Some_Airport",
             "name": "Some Airport"},
        ])
        # manual mapping has the correct override
        manual_path = tmp_results / "manual_airport_mapping.csv"
        with open(manual_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["url", "iata", "name", "source"])
            writer.writeheader()
            writer.writerow({
                "url":    "https://en.wikipedia.org/wiki/Some_Airport",
                "iata":   "NEW",
                "name":   "Some Airport",
                "source": "manual",
            })
        url_to_iata, _ = _build_url_to_iata_mapping(verbose=False)
        normalized = "https://en.wikipedia.org/wiki/some_airport"
        assert url_to_iata.get(normalized) == "NEW"


# ---------------------------------------------------------------------------
# create_outbound_connections_list
# ---------------------------------------------------------------------------

class TestCreateOutboundConnectionsList:

    def test_raises_when_tmp_results_dir_missing(self, tmp_path, monkeypatch):
        """FileNotFoundError when TEMP_RESULTS_DIR does not exist."""
        monkeypatch.setattr(
            "wikipediaGATN.connections.TEMP_RESULTS_DIR",
            tmp_path / "nonexistent",
        )
        monkeypatch.setattr(
            "wikipediaGATN.connections.PUBLIC_DATA_DIR",
            tmp_path / "public",
        )
        with pytest.raises(FileNotFoundError):
            create_outbound_connections_list(verbose=False)

    def test_returns_tuple_of_two_strings(self, data_dirs):
        """Returns ``(connections_csv_path, unmapped_csv_path_or_None)``."""
        tmp_results, _ = data_dirs
        _write_airport_json(tmp_results, "YWG", 0, destinations=[])
        result = create_outbound_connections_list(verbose=False, export_unmapped=False)
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[0], str)

    def test_connections_csv_created(self, data_dirs):
        """global-air-transportation-network.csv is written to PUBLIC_DATA_DIR."""
        tmp_results, public = data_dirs
        _write_airport_json(tmp_results, "YWG", 0, destinations=[])
        csv_path, _ = create_outbound_connections_list(verbose=False)
        assert os.path.exists(csv_path)
        assert "global-air-transportation-network.csv" in csv_path

    def test_connections_csv_contains_origin(self, data_dirs):
        """The origin IATA code appears in global-air-transportation-network.csv."""
        tmp_results, public = data_dirs
        _write_airport_json(tmp_results, "YWG", 0, destinations=[])
        csv_path, _ = create_outbound_connections_list(verbose=False)
        with open(csv_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "YWG" in content

    def test_destinations_resolved_via_airports_csv(self, data_dirs):
        """A destination whose URL is in airports_information.csv is resolved."""
        tmp_results, public = data_dirs
        dest_url = "https://en.wikipedia.org/wiki/Toronto_Pearson_International_Airport"
        # Seed airport points to YYZ's URL
        _write_airport_json(tmp_results, "YWG", 0, destinations=[
            ["Toronto Pearson", dest_url],
        ])
        # airports_information.csv maps that URL to YYZ
        _write_airports_csv(public, [
            {"iata":          "YYZ",
             "wikipedia_url": dest_url,
             "name":          "Toronto Pearson"},
        ])
        csv_path, _ = create_outbound_connections_list(verbose=False)
        with open(csv_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "YYZ" in content

    def test_unmapped_csv_none_when_export_false(self, data_dirs):
        """unmapped_csv is None when export_unmapped=False."""
        tmp_results, _ = data_dirs
        _write_airport_json(tmp_results, "YWG", 0)
        _, unmapped = create_outbound_connections_list(
            verbose=False, export_unmapped=False
        )
        assert unmapped is None

    def test_unmapped_csv_written_when_destinations_unresolved(self, data_dirs):
        """unmapped_destinations.csv is written when URLs cannot be resolved."""
        tmp_results, _ = data_dirs
        _write_airport_json(tmp_results, "YWG", 0, destinations=[
            ["Unknown Airport", "https://en.wikipedia.org/wiki/Nowhere"],
        ])
        _, unmapped = create_outbound_connections_list(
            verbose=False, export_unmapped=True
        )
        # The URL had no mapping, so unmapped file should exist
        assert unmapped is not None
        assert os.path.exists(unmapped)

    def test_lower_distance_file_wins_over_higher(self, data_dirs):
        """When both YWG.0.json and YWG.1.json exist, the level-0 data is used."""
        tmp_results, public = data_dirs
        dest_url = "https://en.wikipedia.org/wiki/Some_Airport"
        # Level 0: has a destination
        _write_airport_json(tmp_results, "YWG", 0, destinations=[
            ["Some Airport", dest_url],
        ])
        # Level 1: no destinations
        _write_airport_json(tmp_results, "YWG", 1, destinations=[])
        _write_airports_csv(public, [
            {"iata": "YYZ", "wikipedia_url": dest_url, "name": "Some Airport"},
        ])
        csv_path, _ = create_outbound_connections_list(verbose=False)
        with open(csv_path, encoding="utf-8") as fh:
            content = fh.read()
        # Destination resolved from level-0 file
        assert "YYZ" in content

    def test_corrupt_json_skipped_without_crash(self, data_dirs):
        """A corrupt JSON file is skipped with a warning; valid files still processed."""
        tmp_results, _ = data_dirs
        (tmp_results / "BAD.0.json").write_text("{not valid json}", encoding="utf-8")
        _write_airport_json(tmp_results, "YWG", 0, destinations=[])
        # Should not raise
        csv_path, _ = create_outbound_connections_list(verbose=False)
        assert os.path.exists(csv_path)
