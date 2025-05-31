def create_outbound_connections_list(verbose=False):
    """
    Parses JSON files in TEMP_RESULTS_DIR named like XYZ.n.json (e.g., YWG.1.json, YWG.2.json),
    and creates a CSV listing outbound connections for each origin airport.

    NOTE: Only keeps one entry per airport (preferring distance 1, then lowest available distance).

    Output CSV columns:
    - origin: IATA code of the origin airport
    - nb_outlinks: number of destination airports linked
    - outlinks: space-separated IATA codes of destination airports

    This function combines information from:
    - airports_information.csv: maps Wikipedia URLs to IATA codes
    - processed_locations.csv (optional): provides extra mappings not in airports_information
    - *.json files: contain the core data about outbound airport connections

    Output saved to PUBLIC_DATA_DIR/outbound_connections.csv
    """
    import pandas as pd
    import os
    from .paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR
    import re
    import json
    import csv

    # MODIFICATION 1: Updated pattern to handle various airport code formats
    pattern = re.compile(r"^([A-Za-z0-9_]+)\.(\d+)\.json$")

    # MODIFICATION 9: Use dict to store only one entry per airport
    # Key: origin_iata, Value: connection data with lowest distance
    airport_connections = {}

    # -----------------------------
    # STEP 1: Load Wikipedia→IATA mappings
    # -----------------------------

    url_to_iata = {}

    # 1a. airports_information.csv is our primary mapping source
    airport_info_path = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")
    if os.path.exists(airport_info_path):
        try:
            airport_df = pd.read_csv(airport_info_path)
            # MODIFICATION 2: Handle potential missing columns gracefully
            if 'wikipedia_url' in airport_df.columns and 'iata' in airport_df.columns:
                # Filter out empty/null values
                valid_mappings = airport_df.dropna(subset=['wikipedia_url', 'iata'])
                url_to_iata = dict(zip(valid_mappings['wikipedia_url'], valid_mappings['iata']))
            elif verbose:
                print("Warning: airports_information.csv missing required columns")
        except Exception as e:
            if verbose:
                print(f"Could not load airports_information.csv: {e}")

    # 1b. processed_locations.csv is a fallback or supplement
    processed_locations_path = os.path.join(TEMP_RESULTS_DIR, "processed_locations.csv")
    if os.path.exists(processed_locations_path):
        try:
            processed_df = pd.read_csv(processed_locations_path)
            # MODIFICATION 3: Handle different column names that might exist
            url_col = None
            iata_col = None

            # Check for various possible column names
            for col in processed_df.columns:
                if 'url' in col.lower():
                    url_col = col
                if 'iata' in col.lower():
                    iata_col = col

            if url_col and iata_col:
                processed_mappings = processed_df.dropna(subset=[url_col, iata_col])
                processed_url_to_iata = dict(zip(processed_mappings[url_col], processed_mappings[iata_col]))
                url_to_iata.update(processed_url_to_iata)
            elif verbose:
                print(f"processed_locations.csv columns: {list(processed_df.columns)}")
        except Exception as e:
            if verbose:
                print(f"Could not load processed_locations.csv: {e}")

    if verbose:
        print(f"Loaded {len(url_to_iata)} URL-to-IATA mappings")

    # -----------------------------
    # STEP 2: Process each JSON file
    # -----------------------------
    for fname in os.listdir(TEMP_RESULTS_DIR):
        if not fname.endswith('.json'):
            continue

        match = pattern.match(fname)
        if match:
            origin_code, distance_str = match.groups()
            distance = int(distance_str)
            fpath = os.path.join(TEMP_RESULTS_DIR, fname)

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # MODIFICATION 4: More robust IATA extraction
                # Try multiple sources for the origin IATA code
                origin_iata = None

                # First, try the 'iata' field
                if data.get("iata"):
                    origin_iata = data["iata"]
                # If that's empty, try extracting from filename
                elif origin_code and len(origin_code) == 3 and origin_code.isupper():
                    origin_iata = origin_code
                # For wiki-based names, look harder in the data
                elif origin_code.startswith("wiki_"):
                    # Try to find IATA in the JSON data itself
                    origin_iata = data.get("iata") or data.get("IATA")

                if not origin_iata:
                    if verbose:
                        print(f"No IATA code found for {fname}")
                    continue

                # MODIFICATION 10: Check if we should keep this airport's data
                # Keep only if:
                # 1. We haven't seen this airport before, OR
                # 2. This distance is lower than what we have stored
                if origin_iata in airport_connections:
                    existing_distance = airport_connections[origin_iata].get("_distance", float('inf'))
                    if distance >= existing_distance:
                        # Skip this file - we already have data at lower/equal distance
                        if verbose:
                            print(f"Skipping {fname} - already have {origin_iata} at distance {existing_distance}")
                        continue

                # MODIFICATION 5: Handle different destination data structures
                destinations = data.get("destinations", [])

                # Handle case where destinations might be in different formats
                if not destinations:
                    # Try alternative field names
                    destinations = data.get("destination", []) or data.get("dest", [])

                # Map destination Wikipedia URLs → IATA codes
                outlinks = []
                for dest in destinations:
                    dest_iata = None
                    dest_url = None

                    # Handle different destination formats
                    if isinstance(dest, list) and len(dest) >= 2:
                        # Format: [name, wikipedia_url]
                        dest_url = dest[1]
                    elif isinstance(dest, dict):
                        # Format: {"name": "...", "wikipedia_url": "..."}
                        dest_url = dest.get("wikipedia_url") or dest.get("url")
                    elif isinstance(dest, tuple) and len(dest) >= 2:
                        # Format: (name, wikipedia_url)
                        dest_url = dest[1]

                    if dest_url:
                        dest_iata = url_to_iata.get(dest_url)
                        if dest_iata:
                            outlinks.append(dest_iata)
                        elif verbose:
                            print(f"Could not find IATA for URL: {dest_url}")

                # MODIFICATION 6: Remove duplicates and sort for consistency
                outlinks = sorted(list(set(outlinks)))
                nb_outlinks = len(outlinks)
                outlinks_str = " ".join(outlinks)

                # MODIFICATION 11: Store/update the airport connection data
                airport_connections[origin_iata] = {
                    "origin": origin_iata,
                    "nb_outlinks": nb_outlinks,
                    "outlinks": outlinks_str,
                    "_distance": distance  # Keep internally for debugging/selection logic
                }

                if verbose:
                    action = "Updated" if origin_iata in airport_connections else "Added"
                    print(
                        f"{action} [{distance}] {origin_iata}: {nb_outlinks} connections -> {outlinks_str[:50]}{'...' if len(outlinks_str) > 50 else ''}")

            except json.JSONDecodeError as e:
                if verbose:
                    print(f"Invalid JSON in {fname}: {e}")
            except Exception as e:
                if verbose:
                    print(f"Failed to process {fname}: {e}")

    # -----------------------------
    # STEP 3: Write output to CSV
    # -----------------------------
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")

    # Convert dictionary values to list
    connections = list(airport_connections.values())

    # MODIFICATION 7: Sort connections for consistent output
    connections.sort(key=lambda x: x["origin"])

    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["origin", "nb_outlinks", "outlinks"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        for row in connections:
            # Filter out internal fields that start with underscore
            csv_row = {k: v for k, v in row.items() if not k.startswith('_')}
            writer.writerow(csv_row)

    if verbose:
        print(f"\nExported {len(connections)} unique airport connections to {output_csv}")
        print(f"Absolute path: {os.path.abspath(output_csv)}")

        # MODIFICATION 8: Add summary statistics
        if connections:
            total_outlinks = sum(c["nb_outlinks"] for c in connections)
            print(f"Total outbound connections: {total_outlinks}")
            print(f"Average connections per airport: {total_outlinks / len(connections):.1f}")

            # Show breakdown by distance level used (for debugging)
            distances = []
            for airport_code in airport_connections:
                # We still track distance internally for selection logic
                distances.append(airport_connections[airport_code].get("_distance", "unknown"))

            from collections import Counter
            distance_counts = Counter(distances)
            print("Data sources used (distance levels):")
            for dist in sorted(distance_counts.keys()):
                print(f"  Distance {dist}: {distance_counts[dist]} airports")

    return output_csv


# -----------------------------
# Run this script directly
# -----------------------------
if __name__ == "__main__":
    from .paths import PUBLIC_DATA_DIR

    output_path = create_outbound_connections_list(verbose=True)
    print("CSV created at:", output_path)