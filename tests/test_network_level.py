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

import os
import pytest
from wikipediaGATN.wikipedia_network_level import clean_output_directory

@pytest.fixture
def mock_results_dir(tmp_path, monkeypatch):
    """Mock TEMP_RESULTS_DIR to a temporary directory."""
    results_dir = tmp_path / "tmp_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("wikipediaGATN.wikipedia_network_level.TEMP_RESULTS_DIR", results_dir)
    return results_dir

def test_clean_output_directory_no_dir(mock_results_dir, monkeypatch):
    """Returns 0 when the directory does not exist."""
    non_existent = mock_results_dir / "does_not_exist"
    monkeypatch.setattr("wikipediaGATN.wikipedia_network_level.TEMP_RESULTS_DIR", non_existent)

    assert not non_existent.exists()
    assert clean_output_directory(verbose=False) == 0

def test_clean_output_directory_all(mock_results_dir):
    """levels=None removes all matching JSON files and processed_locations.csv."""
    # Create matching files
    (mock_results_dir / "YWG.0.json").write_text("{}", encoding="utf-8")
    (mock_results_dir / "YYZ.1.json").write_text("{}", encoding="utf-8")
    (mock_results_dir / "wiki_London.2.json").write_text("{}", encoding="utf-8")
    (mock_results_dir / "processed_locations.csv").write_text("iata,url", encoding="utf-8")

    # Run clean
    count = clean_output_directory(levels=None, verbose=False)

    # Verify
    assert count == 3
    assert not (mock_results_dir / "YWG.0.json").exists()
    assert not (mock_results_dir / "YYZ.1.json").exists()
    assert not (mock_results_dir / "wiki_London.2.json").exists()
    assert not (mock_results_dir / "processed_locations.csv").exists()

def test_clean_output_directory_with_levels(mock_results_dir):
    """Filtering by specific levels works."""
    # Create files at different levels
    (mock_results_dir / "YWG.0.json").write_text("{}", encoding="utf-8")
    (mock_results_dir / "YYZ.1.json").write_text("{}", encoding="utf-8")
    (mock_results_dir / "LHR.2.json").write_text("{}", encoding="utf-8")

    # Remove only levels 0 and 2
    count = clean_output_directory(levels=[0, 2], verbose=False)

    assert count == 2
    assert not (mock_results_dir / "YWG.0.json").exists()
    assert (mock_results_dir / "YYZ.1.json").exists()
    assert not (mock_results_dir / "LHR.2.json").exists()

def test_clean_output_directory_keeps_unrelated_files(mock_results_dir):
    """Files not matching the patterns are preserved."""
    # Matching file
    (mock_results_dir / "YWG.0.json").write_text("{}", encoding="utf-8")

    # Unrelated files
    (mock_results_dir / "random.txt").write_text("keep me", encoding="utf-8")
    (mock_results_dir / "some.json").write_text("{}", encoding="utf-8")
    (mock_results_dir / "YWG.0.bak").write_text("{}", encoding="utf-8")

    count = clean_output_directory(levels=None, verbose=False)

    assert count == 1
    assert not (mock_results_dir / "YWG.0.json").exists()
    assert (mock_results_dir / "random.txt").exists()
    assert (mock_results_dir / "some.json").exists()
    assert (mock_results_dir / "YWG.0.bak").exists()
