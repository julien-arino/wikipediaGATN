"""
Tests for :mod:`wikipediaGATN.wikipedia_network_level`.

Focuses on testing the functionality of check_processed_list.
"""

import os
import csv
import pytest

from wikipediaGATN.wikipedia_network_level import check_processed_list

@pytest.fixture
def tmp_results_dir(tmp_path, monkeypatch):
    """Fixture to mock TEMP_RESULTS_DIR to a temporary directory."""
    monkeypatch.setattr("wikipediaGATN.wikipedia_network_level.TEMP_RESULTS_DIR", str(tmp_path))
    return tmp_path

class TestCheckProcessedList:
    def test_missing_csv_returns_gracefully(self, tmp_results_dir, capsys):
        """Test that if processed_locations.csv doesn't exist, it prints a message and returns."""
        check_processed_list(verbose=True)
        captured = capsys.readouterr()
        assert "processed_locations.csv does not exist" in captured.out

    def test_empty_csv_returns_gracefully(self, tmp_results_dir, capsys):
        """Test that an empty processed_locations.csv file gracefully returns."""
        csv_path = os.path.join(tmp_results_dir, "processed_locations.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            pass  # empty file

        check_processed_list(verbose=True)
        captured = capsys.readouterr()
        assert "processed_locations.csv is empty or has unexpected headers" in captured.out

    def test_unexpected_headers_returns_gracefully(self, tmp_results_dir, capsys):
        """Test that a processed_locations.csv file with the wrong headers gracefully returns."""
        csv_path = os.path.join(tmp_results_dir, "processed_locations.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["foo", "bar"])

        check_processed_list(verbose=True)
        captured = capsys.readouterr()
        assert "processed_locations.csv is empty or has unexpected headers" in captured.out

    def test_deduplication_and_sorting(self, tmp_results_dir):
        """Test that duplicate URLs are removed and output is sorted by (iata, url)."""
        csv_path = os.path.join(tmp_results_dir, "processed_locations.csv")
        entries = [
            ("YWG", "url1"),
            ("YYZ", "url2"),
            ("YVR", "url3"),
            ("YWG", "url1"),  # Duplicate
            ("YUL", "url2"),  # Duplicate URL, different IATA (first one is kept by algorithm)
        ]

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["iata", "url"])
            writer.writerows(entries)

        check_processed_list(verbose=True)

        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert headers == ["iata", "url"]
            results = list(reader)

        expected = [
            ["YVR", "url3"],
            ["YWG", "url1"],
            ["YYZ", "url2"],
        ]
        assert results == expected

    def test_failed_lookups_exported(self, tmp_results_dir, capsys):
        """Test that entries with iata == 'None' are exported to failed_lookups.csv and removed."""
        csv_path = os.path.join(tmp_results_dir, "processed_locations.csv")
        entries = [
            ("YWG", "url1"),
            ("None", "url2"),
            ("None", "url3"),
            ("YYZ", "url4"),
            ("None", "url2"),
        ]

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["iata", "url"])
            writer.writerows(entries)

        check_processed_list(verbose=True)

        failed_csv_path = os.path.join(tmp_results_dir, "failed_lookups.csv")
        assert os.path.exists(failed_csv_path)

        with open(failed_csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert headers == ["iata", "url"]
            results = list(reader)

        expected_failed = [
            ["None", "url2"],
            ["None", "url2"],
            ["None", "url3"],
        ]
        assert results == expected_failed

        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            next(reader)
            main_results = list(reader)

        expected_main = [
            ["YWG", "url1"],
            ["YYZ", "url4"],
        ]
        assert main_results == expected_main

        captured = capsys.readouterr()
        assert "Exported 3 failed lookups" in captured.out

    def test_no_failed_lookups_does_not_create_file(self, tmp_results_dir, capsys):
        """Test that if there are no None lookups, failed_lookups.csv is not created."""
        csv_path = os.path.join(tmp_results_dir, "processed_locations.csv")
        entries = [
            ("YWG", "url1"),
        ]

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["iata", "url"])
            writer.writerows(entries)

        check_processed_list(verbose=True)

        failed_csv_path = os.path.join(tmp_results_dir, "failed_lookups.csv")
        assert not os.path.exists(failed_csv_path)

        captured = capsys.readouterr()
        assert "No failed lookups found." in captured.out
