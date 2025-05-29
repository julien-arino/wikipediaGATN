## PROCESSING FUNCTIONS
#
# Functions that use the results to generate the GATN graph and related information

import os
import re
import json
import csv

from .paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

###
###
def export_all_airport_data(verbose=False):
    """
    Browses all XYZ.n.json files in TEMP_RESULTS_DIR, extracts IATA, ICAO, latitude, longitude,
    airport name, Wikipedia URL, and number of destinations (outdegree).
    Exports this as a CSV to PUBLIC_DATA_DIR/airports_information.csv.
    """
    pattern = re.compile(r"^[A-Z0-9]{3}\.\d+\.json$")
    rows = []
    for fname in os.listdir(TEMP_RESULTS_DIR):
        if pattern.match(fname):
            fpath = os.path.join(TEMP_RESULTS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                iata = data.get("iata", "")
                icao = data.get("icao", "")
                lat = data.get("latitude", "")
                lon = data.get("longitude", "")
                name = data.get("name") or data.get("serves", "")
                wiki_url = data.get("wikipedia_url", "")
                destinations = data.get("destinations", [])
                outdegree = len(destinations)
                rows.append({
                    "iata": iata,
                    "icao": icao,
                    "latitude": lat,
                    "longitude": lon,
                    "name": name,
                    "wikipedia_url": wiki_url,
                    "outdegree": outdegree
                })
            except Exception as e:
                if verbose:
                    print(f"Failed to process {fname}: {e}")

    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")
    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["iata", "icao", "latitude", "longitude", "name", "wikipedia_url", "outdegree"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    if verbose:
        print(f"Exported {len(rows)} airports to {output_csv}")

###
###
def check_duplicated_iata_codes(verbose=False):
    """
    Checks for duplicated IATA codes in TEMP_RESULTS_DIR (i.e., files with the same IATA but different levels).
    If duplicates are found, removes the highest level files, keeping only the lowest level for each IATA.
    """
    pattern = re.compile(r"^([A-Z0-9]{3})\.(\d+)\.json$")
    files_by_iata = {}

    # Collect all files by IATA code
    for fname in os.listdir(TEMP_RESULTS_DIR):
        match = pattern.match(fname)
        if match:
            iata, level = match.group(1), int(match.group(2))
            if iata not in files_by_iata:
                files_by_iata[iata] = []
            files_by_iata[iata].append((level, fname))

    removed_files = []
    for iata, files in files_by_iata.items():
        if len(files) > 1:
            # Sort by level, keep the lowest, remove the rest
            files.sort()
            to_remove = [fname for _, fname in files[1:]]
            for fname in to_remove:
                fpath = os.path.join(TEMP_RESULTS_DIR, fname)
                try:
                    os.remove(fpath)
                    removed_files.append(fname)
                    if verbose:
                        print(f"Removed duplicate: {fname}")
                except Exception as e:
                    if verbose:
                        print(f"Failed to remove {fname}: {e}")

    if verbose:
        if removed_files:
            print(f"Removed {len(removed_files)} duplicate files.")
        else:
            print("No duplicate IATA code files found.")