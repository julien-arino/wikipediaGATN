"""
Orchestrates the scraping of airports that were listed as destinations but were missing from the offline OurAirports database.
"""

import csv
import json
import os
import shutil
import time
import urllib.parse
from collections import deque

from wikipediaGATN.airport_level_functions import (
    build_url_to_codes_map,
    fetch_wikipedia_airport_info,
    format_airport_json,
    format_destinations_list,
    infer_missing_geographic_data,
)
from wikipediaGATN.paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR


def scrape_missing_airports():
    input_csv = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports_active.csv")
    output_dir = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports")

    if not os.path.exists(input_csv):
        print(f"File not found: {input_csv}")
        return

    if os.path.exists(output_dir):
        print(f"Clearing existing directory: {output_dir}")
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print("Building global URL map...")
    url_map = build_url_to_codes_map(verbose=False)

    # Pre-load known public airports
    known_public_urls = set()
    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    if os.path.exists(airport_data_dir):
        for fname in os.listdir(airport_data_dir):
            if fname.endswith(".json"):
                try:
                    with open(
                        os.path.join(airport_data_dir, fname), "r", encoding="utf-8"
                    ) as f:
                        data = json.load(f)
                        if data.get("wikipedia_url"):
                            known_public_urls.add(
                                urllib.parse.unquote(data["wikipedia_url"])
                            )
                except Exception:
                    pass

    print(
        f"Loaded {len(known_public_urls)} existing airport URLs from public database."
    )

    # Read initial URLs from CSV
    initial_urls = []
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            link = row.get("wikipedia_link", "").strip()
            if link:
                code = (
                    row.get("iata_code", "").strip()
                    or row.get("icao_code", "").strip()
                    or row.get("ident", "").strip()
                )
                initial_urls.append((urllib.parse.unquote(link), code))

    print(f"Loaded {len(initial_urls)} target airports from CSV.")

    visited = set(known_public_urls)  # don't visit if already public!

    processed_count = 0
    saved_count = 0

    for seed_url, forced_code in initial_urls:
        if seed_url in visited:
            continue
        queue = deque([(seed_url, 0, forced_code)])
        visited.add(seed_url)

        while queue:
            current_url, level, forced_code_curr = queue.popleft()

            processed_count += 1

            print(f"[{processed_count}] Level {level} - Scraping: {current_url}")

            info = fetch_wikipedia_airport_info(current_url, verbose=False)
            if not info or not info.get("wikipedia_url"):
                continue

            # Register the canonical resolved URL as visited just in case
            canonical_url = urllib.parse.unquote(info["wikipedia_url"])
            if canonical_url in known_public_urls:
                print(f"  -> Resolved to known public URL {canonical_url}. Skipping.")
                continue
            visited.add(canonical_url)

            # Determine code from url_map
            code = None
            iata = icao = gps = None

            if forced_code_curr:
                code = forced_code_curr
                # Try to get the other codes if available
                if canonical_url in url_map:
                    codes = url_map[canonical_url]
                    iata = codes.get("iata", "iata code not found")
                    icao = codes.get("icao", "icao code not found")
                    gps = codes.get("gps", "gps code not found")
            elif canonical_url in url_map:
                codes = url_map[canonical_url]
                iata = codes.get("iata", "iata code not found")
                icao = codes.get("icao", "icao code not found")
                gps = codes.get("gps", "gps code not found")

                if iata != "iata code not found" and iata:
                    code = iata
                elif icao != "icao code not found" and icao:
                    code = icao
                elif gps != "gps code not found" and gps:
                    code = gps

            if not code:
                print(
                    f"  -> Skipping: No valid IATA/ICAO/GPS code in ourairports.csv for {canonical_url}"
                )
                continue

            # Check if ANY of the available codes are already processed
            already_processed = False
            for c in [iata, icao, gps]:
                if not c or c in [
                    "iata code not found",
                    "icao code not found",
                    "gps code not found",
                ]:
                    continue

                # Check public database
                if os.path.exists(os.path.join(airport_data_dir, f"{c}.json")):
                    print(
                        f"  -> Skipping: {c} is already in the main airport database."
                    )
                    already_processed = True
                    break

                # Check current missing sweep (any level)
                existing_sweep_files = [
                    f for f in os.listdir(output_dir) if f.startswith(f"{c}.")
                ]
                if existing_sweep_files:
                    print(
                        f"  -> Skipping: {c} already processed in current sweep at a different level."
                    )
                    already_processed = True
                    break

            if already_processed:
                continue

            # Format destinations
            destinations = format_destinations_list(
                info.get("destinations", []),
                info.get("airlines_destinations", {}),
                url_map,
            )
            destinations_cargo = format_destinations_list(
                info.get("destinations_cargo", []),
                info.get("airlines_destinations_cargo", {}),
                url_map,
            )

            airlines = info.get("airlines", [])
            airlines_cargo = info.get("airlines_cargo", [])

            info["destinations"] = destinations
            info["destinations_cargo"] = destinations_cargo
            info["outdegree"] = len(destinations)
            info["outdegree_cargo"] = len(destinations_cargo)
            info["number_airlines"] = len(airlines)
            info["number_airlines_cargo"] = len(airlines_cargo)

            # Filter Logic at Level 0: Must have destinations, or must have cargo operations.
            valid_dests = [d for d in destinations if isinstance(d, dict)]
            valid_cargo_dests = [d for d in destinations_cargo if isinstance(d, dict)]
            has_valid_dests = len(valid_dests) > 0
            has_valid_cargo_dests = len(valid_cargo_dests) > 0
            has_cargo_airlines = len(airlines_cargo) > 0

            if level == 0:
                if (
                    not has_valid_dests
                    and not has_valid_cargo_dests
                    and not has_cargo_airlines
                ):
                    print("  -> Skipping: No valid destinations or cargo operations.")
                    continue

            # Try to infer geographics
            info = infer_missing_geographic_data(info)
            info = format_airport_json(info)

            fname = f"{code}.{level}.json"
            fpath = os.path.join(output_dir, fname)

            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)

            saved_count += 1
            print(
                f"  -> Saved {fname} ({len(destinations)} pax dests, {len(destinations_cargo)} cargo dests)"
            )

            # Enqueue new destinations
            all_dests = destinations + destinations_cargo
            for d in all_dests:
                if isinstance(d, dict):
                    d_url = urllib.parse.unquote(d.get("wikipedia_url", ""))
                    if d_url and d_url not in visited:
                        queue.append((d_url, level + 1, None))
                        visited.add(d_url)  # pre-mark to avoid duplicate enqueuing

            time.sleep(0.5)  # respectful pause

    print(f"\nDone! Processed {processed_count} URLs, saved {saved_count} JSON files.")


if __name__ == "__main__":
    scrape_missing_airports()
