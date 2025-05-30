def create_outbound_connections_list(verbose=False):
    """
    Parses JSON files in TEMP_RESULTS_DIR named like XYZ.n.json (e.g., YWG.1.json, YWG.2.json),
    and creates a CSV listing outbound connections for each origin airport at distance `n`.

    Output CSV columns:
    - distance: 1 or 2 (extracted from the filename)
    - origin: IATA code of the origin airport
    - nb_outlinks: number of destination airports linked
    - outlinks: space-separated IATA codes of destination airports

    This function combines information from:
    - airports_information.csv: maps Wikipedia URLs to IATA codes
    - processed_locations.csv (optional): provides extra mappings not in airports_information
    - *.json files: contain the core data about outbound airport connections

    Output saved to PUBLIC_DATA_DIR/outbound_connections_V2.csv
    """
    import pandas as pd
    import os
    from .paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR
    import re
    import json
    import csv

    # Match filenames like YWG.1.json, where:
    # - YWG is the airport code
    # - 1 is the connection distance
    pattern = re.compile(r"^([A-Z0-9]{3})\.(\d+)\.json$")
    connections = []

    # -----------------------------
    # STEP 1: Load Wikipedia→IATA mappings
    # -----------------------------

    url_to_iata = {}

    # 1a. airports_information.csv is our primary mapping source
    airport_info_path = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")
    if os.path.exists(airport_info_path):
        airport_df = pd.read_csv(airport_info_path)
        url_to_iata = dict(zip(airport_df['wikipedia_url'], airport_df['iata']))

    # 1b. processed_locations.csv is a fallback or supplement
    # It's used when some mappings are missing from airports_information.csv
    processed_locations_path = os.path.join(TEMP_RESULTS_DIR, "processed_locations.csv")
    if os.path.exists(processed_locations_path):
        try:
            processed_df = pd.read_csv(processed_locations_path)
            if 'wikipedia_url' in processed_df.columns and 'iata' in processed_df.columns:
                processed_url_to_iata = dict(zip(processed_df['wikipedia_url'], processed_df['iata']))
                # Merge in any new mappings or overwrite missing ones
                url_to_iata.update(processed_url_to_iata)
        except Exception as e:
            if verbose:
                print(f"Could not load processed_locations.csv: {e}")

    # -----------------------------
    # STEP 2: Process each JSON file
    # -----------------------------
    for fname in os.listdir(TEMP_RESULTS_DIR):
        match = pattern.match(fname)
        if match:
            origin_code, distance_str = match.groups()
            distance = int(distance_str)
            fpath = os.path.join(TEMP_RESULTS_DIR, fname)

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # JSON contains:
                # - "iata": the origin airport
                # - "destinations": a list of [name, wikipedia_url] pairs
                origin_iata = data.get("iata", "")
                destinations = data.get("destinations", [])

                if not origin_iata:
                    if verbose:
                        print(f"No IATA code found in {fname}")
                    continue

                # Map destination Wikipedia URLs → IATA codes
                outlinks = []
                for dest in destinations:
                    if isinstance(dest, list) and len(dest) >= 2:
                        dest_url = dest[1]  # Wikipedia URL
                        dest_iata = url_to_iata.get(dest_url)
                        if dest_iata:
                            outlinks.append(dest_iata)
                        elif verbose:
                            print(f"Could not find IATA for URL: {dest_url}")

                nb_outlinks = len(outlinks)
                outlinks_str = " ".join(outlinks)

                # Add row to the output list
                connections.append({
                    "distance": distance,
                    "origin": origin_iata,
                    "nb_outlinks": nb_outlinks,
                    "outlinks": outlinks_str
                })

                if verbose and nb_outlinks > 0:
                    print(f"[{distance}] {origin_iata}: {nb_outlinks} connections -> {outlinks_str[:50]}...")

            except Exception as e:
                if verbose:
                    print(f"Failed to process {fname}: {e}")

    # -----------------------------
    # STEP 3: Write output to CSV
    # -----------------------------
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")

    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["distance", "origin", "nb_outlinks", "outlinks"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        for row in connections:
            writer.writerow(row)

    if verbose:
        print(f"\nExported {len(connections)} airport connections to {output_csv}")
        print(f"Absolute path: {os.path.abspath(output_csv)}")

    return output_csv

# -----------------------------
# Run this script directly
# -----------------------------
if __name__ == "__main__":
    from .paths import PUBLIC_DATA_DIR
    output_path = create_outbound_connections_list(verbose=False)
    print("CSV created at:", output_path)
