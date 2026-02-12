"""
Generate outbound airport connections list from Wikipedia data.

This module parses JSON files from Wikipedia scraping and creates a CSV file
listing outbound connections for each airport. It exports unmapped destination
URLs to a CSV for later processing via web scraping.
"""

import os
import re
import json
import csv
from collections import Counter
from difflib import SequenceMatcher
from urllib.parse import unquote

from .paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR


def _normalize_url(url):
    """Normalize a Wikipedia URL for consistent matching."""
    if not url:
        return ""
    url = unquote(url)
    url = url.rstrip('/')
    return url.lower()


def _extract_airport_name_from_url(url):
    """Extract airport name from Wikipedia URL."""
    if not url:
        return None

    match = re.search(r'/wiki/(.+?)(?:\?|$)', url)
    if not match:
        return None

    name = unquote(match.group(1))
    name = re.sub(r'[_\-–—]', ' ', name)
    name = re.sub(r'\s+International\s+Airport$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+National\s+Airport$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+Airport$', '', name, flags=re.IGNORECASE)

    return name.strip() if name.strip() else None


def _fuzzy_match_iata(airport_name, iata_codes_by_name):
    """Use fuzzy matching to find IATA code from airport name."""
    if not airport_name or not iata_codes_by_name:
        return None, 0

    best_match = None
    best_ratio = 0
    airport_name_lower = airport_name.lower()

    for stored_name, iata in iata_codes_by_name.items():
        ratio = SequenceMatcher(None, airport_name_lower, stored_name.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = iata

    return (best_match, best_ratio) if best_ratio >= 0.6 else (None, best_ratio)


def _build_url_to_iata_mapping(verbose=False):
    """Build comprehensive URL-to-IATA mapping with multiple strategies."""
    import pandas as pd

    url_to_iata = {}
    name_to_iata = {}

    # Load from airports_information.csv
    airport_info_path = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")
    if os.path.exists(airport_info_path):
        try:
            airport_df = pd.read_csv(airport_info_path)
            if 'wikipedia_url' in airport_df.columns and 'iata' in airport_df.columns:
                valid = airport_df.dropna(subset=['wikipedia_url', 'iata'])

                for _, row in valid.iterrows():
                    url = _normalize_url(row['wikipedia_url'])
                    iata = str(row['iata']).strip().upper()
                    if url and iata:
                        url_to_iata[url] = iata

                if 'name' in airport_df.columns:
                    for _, row in valid.iterrows():
                        name = str(row.get('name', '')).strip()
                        iata = str(row['iata']).strip().upper()
                        if name and iata:
                            name_to_iata[name] = iata

                if verbose:
                    print(f"Loaded {len(url_to_iata)} URL mappings from airports_information.csv")
        except Exception as e:
            if verbose:
                print(f"⚠ Could not load airports_information.csv: {e}")

    # Load from processed_locations.csv
    processed_locations_path = os.path.join(TEMP_RESULTS_DIR, "processed_locations.csv")
    if os.path.exists(processed_locations_path):
        try:
            processed_df = pd.read_csv(processed_locations_path)
            url_col = None
            iata_col = None
            name_col = None

            for col in processed_df.columns:
                if 'url' in col.lower():
                    url_col = col
                if 'iata' in col.lower():
                    iata_col = col
                if 'name' in col.lower():
                    name_col = col

            if url_col and iata_col:
                processed_mappings = processed_df.dropna(subset=[url_col, iata_col])
                for _, row in processed_mappings.iterrows():
                    url = _normalize_url(row[url_col])
                    iata = str(row[iata_col]).strip().upper()
                    if url and iata:
                        url_to_iata[url] = iata

                if name_col:
                    for _, row in processed_mappings.iterrows():
                        name = str(row[name_col]).strip()
                        iata = str(row[iata_col]).strip().upper()
                        if name and iata:
                            name_to_iata[name] = iata

                if verbose:
                    print(f" Loaded additional mappings from processed_locations.csv")
        except Exception as e:
            if verbose:
                print(f"⚠ Could not load processed_locations.csv: {e}")

    # Load from manual_airport_mapping.csv (highest priority)
    manual_mapping_path = os.path.join(TEMP_RESULTS_DIR, "manual_airport_mapping.csv")
    if os.path.exists(manual_mapping_path):
        try:
            manual_df = pd.read_csv(manual_mapping_path)
            manual_count = 0

            for _, row in manual_df.iterrows():
                url = _normalize_url(row['url'])
                iata = str(row['iata']).strip().upper()

                if url and iata:
                    url_to_iata[url] = iata
                    manual_count += 1

                if 'name' in manual_df.columns and pd.notna(row.get('name')):
                    name = str(row['name']).strip()
                    if name:
                        name_to_iata[name] = iata

            if verbose:
                print(f"Loaded {manual_count} manual mappings from manual_airport_mapping.csv")
        except Exception as e:
            if verbose:
                print(f"⚠ Could not load manual_airport_mapping.csv: {e}")

    return url_to_iata, name_to_iata


def create_outbound_connections_list(verbose=False, export_unmapped=True):
    """
    Parse JSON files and create a CSV listing outbound connections.

    Optionally exports unmapped destination URLs to a CSV file for later
    processing via Wikipedia web scraping.

    Parameters
    ----------
    verbose : bool, optional
        If True, prints status messages (default: False)
    export_unmapped : bool, optional
        If True, exports unmapped URLs to data/public/unmapped_destinations.csv
        for later processing via web scraping (default: True)

    Returns
    -------
    tuple of (str, str)
        - Path to outbound_connections.csv
        - Path to unmapped_destinations.csv (or None if no unmapped URLs)
    """

    pattern = re.compile(r"^([A-Za-z0-9_]+)\.(\d+)\.json$")
    airport_connections = {}
    unmapped_destinations = Counter()

    # Load mappings
    if verbose:
        print("Building URL-to-IATA mapping...")

    url_to_iata, name_to_iata = _build_url_to_iata_mapping(verbose=verbose)

    if verbose:
        print(f" Total URL mappings available: {len(url_to_iata)}")
        print(f" Total name mappings available: {len(name_to_iata)}\n")

    # Process JSON files
    if verbose:
        print("Processing airport JSON files...")

    for fname in os.listdir(TEMP_RESULTS_DIR):
        if not fname.endswith('.json'):
            continue

        match = pattern.match(fname)
        if not match:
            continue

        origin_code, distance_str = match.groups()
        distance = int(distance_str)
        fpath = os.path.join(TEMP_RESULTS_DIR, fname)

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Extract origin IATA code
            origin_iata = None
            if data.get("iata"):
                origin_iata = data["iata"]
            elif origin_code and len(origin_code) == 3 and origin_code.isupper():
                origin_iata = origin_code
            elif origin_code.startswith("wiki_"):
                origin_iata = data.get("iata") or data.get("IATA")

            if not origin_iata:
                if verbose:
                    print(f"  ⚠ No IATA code found for {fname}")
                continue

            # Keep only lowest distance for each airport
            if origin_iata in airport_connections:
                existing_distance = airport_connections[origin_iata].get("_distance", float('inf'))
                if distance >= existing_distance:
                    continue

            # Extract destinations
            destinations = data.get("destinations", [])
            if not destinations:
                destinations = data.get("destination", []) or data.get("dest", [])

            # Map destination URLs → IATA codes
            outlinks = []
            for dest in destinations:
                dest_url = None

                if isinstance(dest, list) and len(dest) >= 2:
                    dest_url = dest[1]
                elif isinstance(dest, dict):
                    dest_url = dest.get("wikipedia_url") or dest.get("url")
                elif isinstance(dest, tuple) and len(dest) >= 2:
                    dest_url = dest[1]

                if not dest_url:
                    continue

                dest_iata = None

                # Strategy 1: Direct URL matching (normalized)
                normalized_url = _normalize_url(dest_url)
                if normalized_url in url_to_iata:
                    dest_iata = url_to_iata[normalized_url]
                else:
                    # Strategy 2: Fuzzy name matching
                    airport_name = _extract_airport_name_from_url(dest_url)
                    if airport_name:
                        matched_iata, match_ratio = _fuzzy_match_iata(airport_name, name_to_iata)
                        if matched_iata:
                            dest_iata = matched_iata

                # Track unmapped URLs
                if not dest_iata:
                    unmapped_destinations[dest_url] += 1

                # Add IATA code if found
                if dest_iata:
                    outlinks.append(dest_iata)

            # Remove duplicates and sort
            outlinks = sorted(list(set(outlinks)))
            nb_outlinks = len(outlinks)
            outlinks_str = " ".join(outlinks)

            # Store airport connection data
            airport_connections[origin_iata] = {
                "origin": origin_iata,
                "nb_outlinks": nb_outlinks,
                "outlinks": outlinks_str,
                "_distance": distance
            }

            if verbose:
                print(f"  [{distance}] {origin_iata}: {nb_outlinks} connections")

        except Exception as e:
            if verbose:
                print(f"  ✗ Failed to process {fname}: {e}")

    # Report unmapped destinations
    if unmapped_destinations:
        if verbose:
            print(f"\n⚠️  Found {len(unmapped_destinations)} unmapped destination URLs")
            print(f"   (Total occurrences: {sum(unmapped_destinations.values())})")
            print(f"   Top 10 unmapped:")
            for url, count in unmapped_destinations.most_common(10):
                print(f"     {count}x: {url}")

    # Write connections to CSV
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")

    connections = sorted(
        airport_connections.values(),
        key=lambda x: x["origin"]
    )

    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["origin", "nb_outlinks", "outlinks"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        for row in connections:
            csv_row = {k: v for k, v in row.items() if not k.startswith('_')}
            writer.writerow(csv_row)

    if verbose:
        print(f"\n" + "=" * 70)
        print(f" CONNECTIONS EXPORT COMPLETE")
        print(f"=" * 70)
        print(f"Output: {os.path.abspath(output_csv)}")
        print(f"Airports: {len(connections)}")
        total_connections = sum(c['nb_outlinks'] for c in connections)
        print(f"Total connections: {total_connections}")

    # Export unmapped destinations to CSV
    unmapped_csv = None
    if export_unmapped and unmapped_destinations:
        unmapped_csv = os.path.join(PUBLIC_DATA_DIR, "unmapped_destinations.csv")

        # Create list of unmapped destinations with metadata
        unmapped_list = []
        for url, count in unmapped_destinations.items():
            unmapped_list.append({
                'url': url,
                'count': count,
                'iata': '',  # Will be filled in by web scraping
                'name': '',
                'source': 'to_be_scraped'
            })

        # Sort by count (most common first)
        unmapped_list.sort(key=lambda x: x['count'], reverse=True)

        with open(unmapped_csv, "w", encoding="utf-8", newline="") as csvfile:
            fieldnames = ["url", "count", "iata", "name", "source"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in unmapped_list:
                writer.writerow(row)

        if verbose:
            print(f"\n" + "=" * 70)
            print(f"UNMAPPED DESTINATIONS EXPORT")
            print(f"=" * 70)
            print(f"Output: {os.path.abspath(unmapped_csv)}")
            print(f"Total unique unmapped URLs: {len(unmapped_destinations)}")
            print(f"Total unmapped occurrences: {sum(unmapped_destinations.values())}")
            print(f"\n💡 Next step: Use extract_iata_from_wikipedia() to scrape IATA codes")
            print(f"   from these Wikipedia pages and populate the 'iata' column.")

    return output_csv, unmapped_csv

