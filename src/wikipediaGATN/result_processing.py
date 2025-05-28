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
    Browses all XYZ.n.json files in TEMP_RESULTS_DIR, extracts IATA, ICAO, coordinates,
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
                coords = data.get("coordinates", "")
                # Prefer "name", fallback to "serves", fallback to ""
                name = data.get("name") or data.get("serves", "")
                wiki_url = data.get("wikipedia_url", "")
                destinations = data.get("destinations", [])
                outdegree = len(destinations)
                rows.append({
                    "iata": iata,
                    "icao": icao,
                    "coordinates": coords,
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
        fieldnames = ["iata", "icao", "coordinates", "name", "wikipedia_url", "outdegree"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    if verbose:
        print(f"Exported {len(rows)} airports to {output_csv}")

