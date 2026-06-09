"""
Tests for :mod:`wikipediaGATN.wikipedia_network_level`.
"""

import csv
import json
from unittest.mock import call, patch

import pytest

from wikipediaGATN.wikipedia_network_level import (
    _find_max_level,
    _level_pattern,
    _read_processed_urls,
    check_processed_list,
    clean_output_directory,
    continue_existing_search_one_step,
    continue_existing_search_until_empty,
    get_connections_level_N,
    iterate_search_until_distance_N,
    iterate_search_until_empty,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_results_dir(tmp_path, monkeypatch):
    """
    Create a tmp_results/airports_rooted_sweep directory,
    monkeypatch TEMP_RESULTS_DIR, and return the path.
    """
    tmp_results = tmp_path / "tmp_results"
    tmp_results.mkdir()
    sweep_dir = tmp_results / "airports_rooted_sweep"
    sweep_dir.mkdir()
    monkeypatch.setattr(
        "wikipediaGATN.wikipedia_network_level.TEMP_RESULTS_DIR", tmp_results
    )
    return sweep_dir


# ---------------------------------------------------------------------------
# _level_pattern
# ---------------------------------------------------------------------------


class TestLevelPattern:

    def test_matches_iata_format(self):
        pat = _level_pattern(1)
        assert pat.match("YWG.1.json")
        assert not pat.match("YWG.2.json")

    def test_matches_wiki_prefix_format(self):
        pat = _level_pattern(2)
        assert pat.match("wiki_London_Heathrow.2.json")
        assert not pat.match("wiki_London_Heathrow.1.json")

    def test_does_not_match_other_files(self):
        pat = _level_pattern(0)
        assert not pat.match("processed_locations.csv")
        assert not pat.match("YWG.0.txt")


# ---------------------------------------------------------------------------
# _find_max_level
# ---------------------------------------------------------------------------


class TestFindMaxLevel:

    def test_empty_dir_returns_minus_one(self, tmp_results_dir):
        assert _find_max_level(tmp_results_dir) == -1

    def test_finds_max_iata_level(self, tmp_results_dir):
        (tmp_results_dir / "YWG.0.json").touch()
        (tmp_results_dir / "YYZ.1.json").touch()
        (tmp_results_dir / "LHR.2.json").touch()
        assert _find_max_level(tmp_results_dir) == 2

    def test_ignores_wiki_prefix_files(self, tmp_results_dir):
        (tmp_results_dir / "YWG.0.json").touch()
        (tmp_results_dir / "wiki_London.5.json").touch()
        # Should only consider [A-Z]{3}.<N>.json
        assert _find_max_level(tmp_results_dir) == 0

    def test_ignores_non_json_files(self, tmp_results_dir):
        (tmp_results_dir / "YWG.0.json").touch()
        (tmp_results_dir / "YYZ.1.txt").touch()
        assert _find_max_level(tmp_results_dir) == 0


# ---------------------------------------------------------------------------
# _read_processed_urls
# ---------------------------------------------------------------------------


class TestReadProcessedUrls:

    def test_missing_file_returns_empty_set(self, tmp_results_dir):
        assert _read_processed_urls(tmp_results_dir.parent) == set()

    def test_reads_urls_from_csv(self, tmp_results_dir):
        csv_path = tmp_results_dir.parent / "processed_locations.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["iata_icao_gps", "url", "iata_icao_gps_from"])
            writer.writerow(
                ["YWG", "https://en.wikipedia.org/wiki/Winnipeg_Airport", ""]
            )
            writer.writerow(
                ["YYZ", "https://en.wikipedia.org/wiki/Toronto_Pearson", ""]
            )

        urls = _read_processed_urls(tmp_results_dir.parent)
        assert len(urls) == 2
        assert "https://en.wikipedia.org/wiki/Winnipeg_Airport" in urls
        assert "https://en.wikipedia.org/wiki/Toronto_Pearson" in urls

    def test_handles_empty_url_column(self, tmp_results_dir):
        csv_path = tmp_results_dir.parent / "processed_locations.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["iata_icao_gps", "url", "iata_icao_gps_from"])
            writer.writerow(["YWG", "", ""])

        assert _read_processed_urls(tmp_results_dir) == set()


# ---------------------------------------------------------------------------
# clean_output_directory
# ---------------------------------------------------------------------------


class TestCleanOutputDirectory:

    def test_removes_all_json_files_when_levels_is_none(self, tmp_results_dir):
        (tmp_results_dir / "YWG.0.json").touch()
        (tmp_results_dir / "YYZ.1.json").touch()
        (tmp_results_dir.parent / "processed_locations.csv").touch()

        removed = clean_output_directory(levels=None)
        assert removed == 2
        assert not (tmp_results_dir / "YWG.0.json").exists()
        assert not (tmp_results_dir / "YYZ.1.json").exists()
        assert not (tmp_results_dir.parent / "processed_locations.csv").exists()

    def test_removes_only_specified_levels(self, tmp_results_dir):
        (tmp_results_dir / "YWG.0.json").touch()
        (tmp_results_dir / "YYZ.1.json").touch()
        (tmp_results_dir / "LHR.2.json").touch()

        removed = clean_output_directory(levels=[0, 2])
        assert removed == 2
        assert not (tmp_results_dir / "YWG.0.json").exists()
        assert (tmp_results_dir / "YYZ.1.json").exists()
        assert not (tmp_results_dir / "LHR.2.json").exists()

    def test_handles_nonexistent_directory(self, tmp_path, monkeypatch):
        nonexistent = tmp_path / "not_here"
        monkeypatch.setattr(
            "wikipediaGATN.wikipedia_network_level.TEMP_RESULTS_DIR", nonexistent
        )
        assert clean_output_directory() == 0

    def test_warns_on_os_error_during_json_removal(self, tmp_results_dir):
        (tmp_results_dir / "YWG.0.json").touch()

        with patch("os.remove", side_effect=OSError("Permission denied")):
            with pytest.warns(UserWarning, match="Could not remove YWG.0.json"):
                clean_output_directory()

    def test_warns_on_os_error_during_csv_removal(self, tmp_results_dir):
        (tmp_results_dir.parent / "processed_locations.csv").touch()

        # We need to be careful with patch side_effect here.
        # os.remove is called for JSONs then for CSV.
        def mocked_remove(path):
            if "processed_locations.csv" in str(path):
                raise OSError("CSV Error")
            # For others, do nothing or original

        with patch("os.remove", side_effect=mocked_remove):
            with pytest.warns(
                UserWarning, match="Could not remove processed_locations.csv"
            ):
                clean_output_directory()


# ---------------------------------------------------------------------------
# check_processed_list
# ---------------------------------------------------------------------------


class TestCheckProcessedList:

    def test_deduplicates_urls_and_sorts_entries(self, tmp_results_dir):
        csv_path = tmp_results_dir.parent / "processed_locations.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["iata_icao_gps", "url", "iata_icao_gps_from"])
            writer.writerow(["YYZ", "url1", ""])
            writer.writerow(["YWG", "url2", ""])
            writer.writerow(["YWG", "url2", ""])  # duplicate
            writer.writerow(["AMS", "url3", ""])

        check_processed_list()

        with open(csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        assert len(rows) == 3
        # Sorted by (iata, url): AMS, YWG, YYZ
        assert rows[0]["iata_icao_gps"] == "AMS"
        assert rows[1]["iata_icao_gps"] == "YWG"
        assert rows[2]["iata_icao_gps"] == "YYZ"

    def test_exports_none_iata_to_failed_lookups(self, tmp_results_dir):
        csv_path = tmp_results_dir.parent / "processed_locations.csv"
        failed_path = tmp_results_dir.parent / "failed_lookups.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["iata_icao_gps", "url", "iata_icao_gps_from"])
            writer.writerow(["None", "fail_url1", ""])
            writer.writerow(["YWG", "ok_url1", ""])

        check_processed_list()

        # Check main file
        with open(csv_path, "r", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        assert rows[0]["iata_icao_gps"] == "YWG"
        assert rows[0]["url"] == "ok_url1"

        # Check failed lookups file
        with open(failed_path, "r", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        assert rows[0]["url"] == "fail_url1"

    def test_missing_file_handled_gracefully(self, tmp_results_dir):
        # No processed_locations.csv
        check_processed_list()
        assert not (tmp_results_dir.parent / "failed_lookups.csv").exists()

    def test_unexpected_headers_warned_if_verbose(self, tmp_results_dir, capsys):
        csv_path = tmp_results_dir.parent / "processed_locations.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["bad", "header"])

        check_processed_list(verbose=True)
        captured = capsys.readouterr()
        assert "unexpected headers" in captured.out


# ---------------------------------------------------------------------------
# get_connections_level_N
# ---------------------------------------------------------------------------


class TestGetConnectionsLevelN:

    def test_processes_files_at_correct_level_and_fetches_destinations(
        self, tmp_results_dir
    ):
        # Setup source file at level 0
        origin_data = {
            "iata": "YWG",
            "destinations": [
                ["Toronto", "https://en.wikipedia.org/wiki/Toronto_Pearson"]
            ],
        }
        with open(tmp_results_dir / "YWG.0.json", "w", encoding="utf-8") as fh:
            json.dump(origin_data, fh)

        # Mock dependencies
        with (
            patch(
                "wikipediaGATN.wikipedia_network_level.fetch_wikipedia_airport_info"
            ) as mock_extract,
            patch(
                "wikipediaGATN.wikipedia_network_level.save_airport_info"
            ) as mock_save,
            patch("time.sleep"),
        ):  # skip sleep

            mock_extract.return_value = {"iata": "YYZ", "name": "Toronto Pearson"}

            written = get_connections_level_N(from_length=0)

            assert written == 1
            mock_extract.assert_called_once_with(
                "https://en.wikipedia.org/wiki/Toronto_Pearson", verbose=False
            )
            mock_save.assert_called_once()
            # arg 0 to save_airport_info is dest_info, arg level should be 1
            assert mock_save.call_args[1]["level"] == 1

    def test_skips_already_processed_urls(self, tmp_results_dir):
        # Setup processed_locations.csv
        with open(
            tmp_results_dir.parent / "processed_locations.csv",
            "w",
            newline="",
            encoding="utf-8",
        ) as fh:
            writer = csv.writer(fh)
            writer.writerow(["iata_icao_gps", "url", "iata_icao_gps_from"])
            writer.writerow(
                ["YYZ", "https://en.wikipedia.org/wiki/Toronto_Pearson", ""]
            )

        # Setup source file at level 0
        origin_data = {
            "iata": "YWG",
            "destinations": [
                ["Toronto", "https://en.wikipedia.org/wiki/Toronto_Pearson"]
            ],
        }
        with open(tmp_results_dir / "YWG.0.json", "w", encoding="utf-8") as fh:
            json.dump(origin_data, fh)

        with (
            patch(
                "wikipediaGATN.wikipedia_network_level.fetch_wikipedia_airport_info"
            ) as mock_extract,
            patch("time.sleep"),
        ):

            written = get_connections_level_N(from_length=0)
            assert written == 0
            mock_extract.assert_not_called()

    def test_handles_corrupt_json_with_warning(self, tmp_results_dir):
        with open(tmp_results_dir / "BAD.0.json", "w", encoding="utf-8") as fh:
            fh.write("not json")

        with pytest.warns(UserWarning, match="Skipping BAD.0.json"):
            written = get_connections_level_N(from_length=0)
            assert written == 0

    def test_handles_malformed_destination_entry(self, tmp_results_dir):
        origin_data = {
            "iata": "YWG",
            "destinations": ["invalid"],  # should be list of [name, url]
        }
        with open(tmp_results_dir / "YWG.0.json", "w", encoding="utf-8") as fh:
            json.dump(origin_data, fh)

        with pytest.warns(UserWarning, match="Malformed destination entry"):
            written = get_connections_level_N(from_length=0)
            assert written == 0


# ---------------------------------------------------------------------------
# High-level iteration functions
# ---------------------------------------------------------------------------


class TestHighLevelIteration:

    @patch("wikipediaGATN.wikipedia_network_level.fetch_wikipedia_airport_link")
    @patch("wikipediaGATN.wikipedia_network_level.fetch_wikipedia_airport_info")
    @patch("wikipediaGATN.wikipedia_network_level.save_airport_info")
    @patch("wikipediaGATN.wikipedia_network_level.get_connections_level_N")
    def test_iterate_search_until_distance_N(
        self, mock_get_conn, mock_save, mock_extract, mock_get_link
    ):
        mock_get_link.return_value = "link"
        mock_extract.return_value = {
            "iata": "YWG",
            "destinations": [["Toronto", "link2"]],
        }

        iterate_search_until_distance_N("YWG", dist=2)

        mock_get_link.assert_called_once_with("YWG", verbose=False)
        mock_extract.assert_called_once_with("link", verbose=False)
        mock_save.assert_called_once_with(
            mock_extract.return_value, level=0, verbose=False
        )
        # Should be called twice for dist=2
        assert mock_get_conn.call_count == 2
        mock_get_conn.assert_has_calls(
            [
                call(from_length=0, delay=1.0, verbose=False),
                call(from_length=1, delay=1.0, verbose=False),
            ]
        )

    @patch("wikipediaGATN.wikipedia_network_level.fetch_wikipedia_airport_link")
    @patch("wikipediaGATN.wikipedia_network_level.fetch_wikipedia_airport_info")
    @patch("wikipediaGATN.wikipedia_network_level.save_airport_info")
    @patch("wikipediaGATN.wikipedia_network_level.get_connections_level_N")
    def test_iterate_search_until_empty(
        self, mock_get_conn, mock_save, mock_extract, mock_get_link, tmp_results_dir
    ):
        mock_get_link.return_value = "link"
        mock_extract.return_value = {
            "iata": "YWG",
            "destinations": [["Toronto", "link2"]],
        }

        # We need to simulate the while True loop stopping.
        # It stops when no new files are found at level k+1.
        # Let's say it finds something at level 1, then nothing at level 2.
        def side_effect(from_length, **kwargs):
            if from_length == 0:
                (tmp_results_dir / "YYZ.1.json").touch()
            return 0

        mock_get_conn.side_effect = side_effect

        iterate_search_until_empty("YWG")

        assert mock_get_conn.call_count == 2

    @patch("wikipediaGATN.wikipedia_network_level.get_connections_level_N")
    def test_continue_existing_search_one_step(self, mock_get_conn, tmp_results_dir):
        (tmp_results_dir / "YWG.2.json").touch()  # max_level = 2

        continue_existing_search_one_step()

        # from_length = max(0, 2-1) = 1
        mock_get_conn.assert_called_once_with(from_length=1, delay=1.0, verbose=False)

    @patch("wikipediaGATN.wikipedia_network_level.get_connections_level_N")
    def test_continue_existing_search_until_empty(self, mock_get_conn, tmp_results_dir):
        (tmp_results_dir / "YWG.1.json").touch()  # max_level = 1

        # Similar to until_empty, simulate no new files after one call
        iterate_search_until_empty_call_count = 0

        def side_effect(from_length, **kwargs):
            return 0

        mock_get_conn.side_effect = side_effect

        continue_existing_search_until_empty()

        # Starts from k=1, calls get_connections_level_N(from_length=1)
        # No new files at level 2 -> stops.
        mock_get_conn.assert_called_once_with(from_length=1, delay=1.0, verbose=False)
