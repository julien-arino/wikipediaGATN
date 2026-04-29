import json
import os
import csv
import pytest
import warnings
from pathlib import Path
from wikipediaGATN.result_processing_airports import export_all_airport_data

@pytest.fixture()
def data_dirs(tmp_path, monkeypatch):
    """
    Create tmp_results/airports_rooted_sweep and public/airport_data sub-directories,
    monkeypatch both module-level path constants, and return (tmp_results_sweep, public_airport_data).
    """
    tmp_results = tmp_path / "tmp_results"
    tmp_results.mkdir()
    sweep_dir = tmp_results / "airports_rooted_sweep"
    sweep_dir.mkdir()
    
    public = tmp_path / "public"
    public.mkdir()
    airport_data = public / "airport_data"
    airport_data.mkdir()
    
    monkeypatch.setattr("wikipediaGATN.result_processing_airports.TEMP_RESULTS_DIR", tmp_results)
    monkeypatch.setattr("wikipediaGATN.result_processing_airports.PUBLIC_DATA_DIR",  public)
    
    return sweep_dir, airport_data

def test_export_all_airport_data_invalid_json(data_dirs):
    """
    Test that invalid JSON files are skipped with a warning, while valid ones are processed.
    """
    sweep_dir, airport_data = data_dirs

    # Create a valid JSON file in the sweep dir
    valid_data = {
        "iata": "YWG",
        "name": "Winnipeg Richardson International Airport",
        "wikipedia_url": "https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport",
        "destinations": []
    }
    (sweep_dir / "YWG.0.json").write_text(json.dumps(valid_data), encoding="utf-8")

    # Create an invalid JSON file in the sweep dir
    (sweep_dir / "ABC.0.json").write_text("{invalid json}", encoding="utf-8")

    # We expect a UserWarning when processing ABC.0.json
    # The actual message contains "cannot read/parse — Expecting value"
    with pytest.warns(UserWarning, match="Skipping ABC.0.json: cannot read/parse"):
        output_csv = export_all_airport_data(use_new_data=True, verbose=True)

    # Verify output CSV exists
    assert os.path.exists(output_csv)

    # Check the content of the CSV
    with open(output_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 1 valid row
    assert len(rows) == 1
    assert rows[0]["iata"] == "YWG"

def test_export_all_airport_data_missing_dir(tmp_path, monkeypatch):
    """Test FileNotFoundError when the scan directory is missing."""
    monkeypatch.setattr(
        "wikipediaGATN.result_processing_airports.TEMP_RESULTS_DIR",
        tmp_path / "nonexistent"
    )
    # use_new_data=True will look for nonexistent/airports_rooted_sweep
    with pytest.raises(FileNotFoundError):
        export_all_airport_data(use_new_data=True)
