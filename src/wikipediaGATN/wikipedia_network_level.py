## WIKIPEDIA PARSING MODULE
#
# This module provides functions to extract airport information from Wikipedia pages,
# by following links to airport pages and saving the information in JSON files.

import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json
import urllib.parse

from .paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

from .wikipedia_airport_level import (
    get_wikipedia_airport_page_link,
    extract_airport_information,
    extract_airlines_from_airport,
    extract_destinations_from_airport,
    extract_airlines_destinations_from_airport,
    save_airport_info
)

###
###
def clean_output_directory(levels=None, verbose=False):
    """
    Removes files in the OUTPUT directory matching the pattern .0.json, .1.json, etc.
    Also removes processed_locations.csv if present.
    If levels is None, removes all files matching .<number>.json.
    If levels is a list of integers, only removes files matching those levels.
    """
    output_dir = TEMP_RESULTS_DIR 
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    if not os.path.exists(output_dir):
        if verbose:
            print("OUTPUT directory does not exist.")
        return

    removed = 0
    for fname in os.listdir(output_dir):
        if levels is None:
            if re.match(r".*\.\d+\.json$", fname):
                os.remove(os.path.join(output_dir, fname))
                removed += 1
        else:
            for lvl in levels:
                if fname.endswith(f".{lvl}.json"):
                    os.remove(os.path.join(output_dir, fname))
                    removed += 1
                    break

    # Remove processed_locations.csv if present
    csv_path = os.path.join(output_dir, "processed_locations.csv")
    if os.path.exists(csv_path):
        os.remove(csv_path)
        if verbose:
            print("Removed processed_locations.csv from OUTPUT directory.")

    if verbose:
        print(f"Removed {removed} file(s) from OUTPUT directory.")

###
###
def get_connections_level_N(from_length=0, delay=1.0, verbose=False):
    """
    For all airports with files named XXX.{from_length}.json (where XXX is a 3-letter IATA code),
    process their destinations and save info for each unprocessed destination as YYY.{from_length+1}.json.
    Only processes the "next generation" (one step), not recursively.
    """
    output_dir = TEMP_RESULTS_DIR
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    os.makedirs(output_dir, exist_ok=True)

    # Helper to load processed URLs from CSV
    def get_processed_urls():
        csv_path = os.path.join(output_dir, "processed_locations.csv")
        urls = set()
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8") as csvfile:
                lines = [line.strip() for line in csvfile.readlines()]
            # Skip header
            for line in lines[1:]:
                parts = line.split(",", 1)
                if len(parts) == 2:
                    urls.add(parts[1])
        return urls

    # Find all files matching pattern XXX.{from_length}.json where XXX is a 3-letter IATA code
    pattern = re.compile(r"^[A-Z0-9]{{3}}\.{}\.(json)$".format(from_length))
    json_files = [f for f in os.listdir(output_dir) if pattern.match(f)]

    processed_urls = get_processed_urls()
    for json_file in json_files:
        json_path = os.path.join(output_dir, json_file)
        with open(json_path, "r", encoding="utf-8") as f:
            airport_info = json.load(f)
        destinations = airport_info.get("destinations", [])
        origin_iata = airport_info.get('iata', 'UNKNOWN')
        for dest_name, dest_url in destinations:
            if dest_url in processed_urls:
                if verbose:
                    print(f"From {origin_iata} to {dest_name}: skipping - already processed")
                continue
            if verbose:
                print(f"From {origin_iata} to {dest_name}: processing destination")
            dest_info = extract_airport_information(dest_url)
            dest_iata = dest_info.get('iata') or dest_name
            filename = f"{dest_iata}.{from_length+1}.json"
            # Save only if not already present
            if not os.path.exists(os.path.join(output_dir, filename)):
                save_airport_info(dest_info, level=from_length+1, verbose=verbose)
            processed_urls.add(dest_url)
            time.sleep(delay)

###
###
def check_processed_list(verbose=False):
    """
    Checks the processed_locations.csv file for duplicate URL entries.
    Exports all entries with iata == "None" to failed_lookups.csv (sorted by URL).
    Then discards all entries with iata == "None", sorts the rest by IATA code, and overwrites the original file.
    """
    output_dir = TEMP_RESULTS_DIR
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    csv_path = os.path.join(output_dir, "processed_locations.csv")
    failed_csv_path = os.path.join(output_dir, "failed_lookups.csv")
    if not os.path.exists(csv_path):
        if verbose:
            print("processed_locations.csv does not exist.")
        return

    # Read all entries, skipping header
    with open(csv_path, "r", encoding="utf-8") as csvfile:
        lines = [line.strip() for line in csvfile.readlines()]
    if not lines or lines[0] != "iata,url":
        if verbose:
            print("processed_locations.csv is empty or missing header.")
        return

    entries = []
    for line in lines[1:]:
        parts = line.split(",", 1)
        if len(parts) == 2:
            iata, url = parts
            entries.append((iata, url))

    # Export all entries with iata == "None" to failed_lookups.csv, sorted by url
    failed_entries = sorted([entry for entry in entries if entry[0] == "None"], key=lambda x: x[1])
    with open(failed_csv_path, "w", encoding="utf-8") as failedfile:
        failedfile.write("iata,url\n")
        for iata, url in failed_entries:
            failedfile.write(f"{iata},{url}\n")
    if verbose:
        print(f"Exported {len(failed_entries)} failed lookups to {failed_csv_path}")

    # Discard all entries with iata == "None"
    valid_entries = [entry for entry in entries if entry[0] != "None"]

    # Remove duplicates by URL (keep the first occurrence)
    seen_urls = set()
    unique_entries = []
    for iata, url in valid_entries:
        if url not in seen_urls:
            unique_entries.append((iata, url))
            seen_urls.add(url)

    # Sort by IATA code
    cleaned_entries = sorted(unique_entries, key=lambda x: (x[0], x[1]))

    # Write back to file
    with open(csv_path, "w", encoding="utf-8") as csvfile:
        csvfile.write("iata,url\n")
        for iata, url in cleaned_entries:
            csvfile.write(f"{iata},{url}\n")

    if verbose:
        print(f"Cleaned processed_locations.csv: {len(cleaned_entries)} unique entries.")

###
###
def iterate_search_until_distance_N(seed_iata, dist=1, delay=1.0, verbose=False):
    """
    Starts from seed_iata, extracts and saves airport info, then iteratively calls get_connections_level_N
    for from_length=0 up to dist-1. Stops after generating files for distance dist.
    """
    # Step 1: Get seed link and info
    link = get_wikipedia_airport_page_link(seed_iata, verbose=verbose)
    if not link:
        print(f"Could not find Wikipedia page for {seed_iata}")
        return
    airport_details = extract_airport_information(link)
    if not airport_details.get("destinations"):
        print(f"No connection information found for {seed_iata}")
        save_airport_info(airport_details, level=0, verbose=verbose)
        return
    save_airport_info(airport_details, level=0, verbose=verbose)

    # Step 2: Iteratively expand connections up to distance N
    for k in range(dist):
        if verbose:
            print(f"\nExpanding connections at distance {k+1}...")
        get_connections_level_N(from_length=k, delay=delay, verbose=verbose)

###
###
def iterate_search_until_empty(seed_iata, delay=1.0, verbose=False):
    """
    Starts from seed_iata, extracts and saves airport info, then repeatedly calls get_connections_level_N
    until no new results are generated.
    """
    # Step 1: Get seed link and info
    link = get_wikipedia_airport_page_link(seed_iata, verbose=verbose)
    if not link:
        print(f"Could not find Wikipedia page for {seed_iata}")
        return
    airport_details = extract_airport_information(link)
    if not airport_details.get("destinations"):
        print(f"No connection information found for {seed_iata}")
        save_airport_info(airport_details, level=0, verbose=verbose)
        return
    save_airport_info(airport_details, level=0, verbose=verbose)

    # Step 2: Expand until no new results
    k = 0
    while True:
        if verbose:
            print(f"\nExpanding connections at distance {k+1}...")
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        output_dir = TEMP_RESULTS_DIR
        before = set(f for f in os.listdir(output_dir) if re.match(r"^[A-Z0-9]{{3}}\.{}\.(json)$".format(k+1), f))
        get_connections_level_N(from_length=k, delay=delay, verbose=verbose)
        after = set(f for f in os.listdir(output_dir) if re.match(r"^[A-Z0-9]{{3}}\.{}\.(json)$".format(k+1), f))
        new_files = after - before
        if not new_files:
            if verbose:
                print(f"No new connections found at distance {k+1}. Stopping.")
            break
        k += 1

###
###
def continue_existing_search_one_step(delay=1.0, verbose=False):
    """
    Finds the highest level N of files named XXX.N.json in OUTPUT (where XXX is a 3-letter IATA code),
    and runs one iteration of get_connections_level_N(from_length=N, ...).
    """
    output_dir = TEMP_RESULTS_DIR
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    if not os.path.exists(output_dir):
        print("OUTPUT directory does not exist.")
        return

    # Find all files matching pattern XXX.N.json where XXX is a 3-letter IATA code and N is an integer
    pattern = re.compile(r"^[A-Z0-9]{3}\.(\d+)\.json$")
    max_level = -1
    for fname in os.listdir(output_dir):
        match = pattern.match(fname)
        if match:
            level = int(match.group(1))
            if level > max_level:
                max_level = level

    if max_level == -1:
        print("No valid airport connection files found in OUTPUT.")
        return

    if verbose:
        print(f"Continuing search from level {max_level} to level {max_level+1}...")

    get_connections_level_N(from_length=max_level, delay=delay, verbose=verbose)

###
###
def continue_existing_search_until_empty(delay=1.0, verbose=False):
    """
    Finds the highest level N of files named XXX.N.json in OUTPUT (where XXX is a 3-letter IATA code),
    and repeatedly runs get_connections_level_N(from_length=N, ...) until no new results are generated.
    """
    output_dir = TEMP_RESULTS_DIR
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    if not os.path.exists(output_dir):
        print("OUTPUT directory does not exist.")
        return

    # Find all files matching pattern XXX.N.json where XXX is a 3-letter IATA code and N is an integer
    pattern = re.compile(r"^[A-Z0-9]{3}\.(\d+)\.json$")
    max_level = -1
    for fname in os.listdir(output_dir):
        match = pattern.match(fname)
        if match:
            level = int(match.group(1))
            if level > max_level:
                max_level = level

    if max_level == -1:
        print("No valid airport connection files found in OUTPUT.")
        return

    k = max_level
    while True:
        if verbose:
            print(f"Continuing search from level {k} to level {k+1}...")
        before = set(f for f in os.listdir(output_dir) if re.match(r"^[A-Z0-9]{{3}}\.{}\.(json)$".format(k+1), f))
        get_connections_level_N(from_length=k, delay=delay, verbose=verbose)
        after = set(f for f in os.listdir(output_dir) if re.match(r"^[A-Z0-9]{{3}}\.{}\.(json)$".format(k+1), f))
        new_files = after - before
        if not new_files:
            if verbose:
                print(f"No new connections found at level {k+1}. Stopping.")
            break
        k += 1

