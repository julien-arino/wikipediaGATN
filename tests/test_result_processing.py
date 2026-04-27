import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock


import pytest
from wikipediaGATN.result_processing import export_all_airport_data

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
    monkeypatch.setattr("wikipediaGATN.result_processing.TEMP_RESULTS_DIR", tmp_results)
    monkeypatch.setattr("wikipediaGATN.result_processing.PUBLIC_DATA_DIR",  public)
    return tmp_results, public

def test_export_all_airport_data_invalid_json(data_dirs):
    """
    Test that invalid JSON files are skipped with a warning, while valid ones are processed.
    """
    tmp_results, public = data_dirs

    # Create a valid JSON file
    valid_data = {
        "iata": "YWG",
        "name": "Winnipeg Richardson International Airport",
        "wikipedia_url": "https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport",
        "destinations": []
    }
    (tmp_results / "YWG.0.json").write_text(json.dumps(valid_data), encoding="utf-8")

    # Create an invalid JSON file
    (tmp_results / "ABC.0.json").write_text("{invalid json}", encoding="utf-8")

    # We expect a UserWarning when processing ABC.0.json
    import warnings
    with pytest.warns(UserWarning, match="Skipping ABC.0.json: invalid JSON"):
        output_csv = export_all_airport_data(verbose=True)

    # Verify output CSV exists
    assert os.path.exists(output_csv)

    # Since we mocked pandas, export_all_airport_data uses csv.DictWriter which is fine.
    # Let's check the content of the CSV
    with open(output_csv, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Header + 1 valid row
    assert len(lines) == 2
    assert "YWG" in lines[1]
    assert "ABC" not in lines[1]

def test_export_all_airport_data_missing_dir(tmp_path, monkeypatch):
    """Test FileNotFoundError when TEMP_RESULTS_DIR is missing."""
    monkeypatch.setattr(
        "wikipediaGATN.result_processing.TEMP_RESULTS_DIR",
        tmp_path / "nonexistent"
    )
    with pytest.raises(FileNotFoundError):
        export_all_airport_data()
