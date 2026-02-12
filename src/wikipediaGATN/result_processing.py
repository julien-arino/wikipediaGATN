"""
Processing functions to generate GATN (Global Air Transportation Network) graph.

This module orchestrates the transformation of raw airport data (JSON files from
Wikipedia scraping) into structured network representations. It provides functions
for extracting airport metadata and generating network connectivity data.

Functions in this module build upon each other:
1. export_all_airport_data() - Extract airport metadata from JSON files
2. check_duplicated_iata_codes() - Clean up duplicate airport records
3. create_outbound_connections_list() - Generate airport connections list (Pass 1)
4. extract_iata_from_unmapped_destinations() - Scrape Wikipedia for IATA codes (Pass 2)
5. create_manual_mapping_from_scraped_data() - Create manual mapping file (Pass 3)
6. create_outbound_adjacency_matrix() - Create sparse adjacency matrices (Pass 4)
"""

import os
import re
import json
import csv

from src.wikipediaGATN.paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR
from src.wikipediaGATN.connections import create_outbound_connections_list
from src.wikipediaGATN.adjacency import create_outbound_adjacency_matrix
from src.wikipediaGATN.extract_iata_from_wikipedia import (
    extract_iata_from_unmapped_destinations,
    create_manual_mapping_from_scraped_data
)

###############################################################################
# AIRPORT DATA EXTRACTION FUNCTIONS
###############################################################################

def export_all_airport_data(verbose=False):
    """
    Extract metadata from all airport JSON files and export to CSV.

    Browses all XYZ.n.json files in TEMP_RESULTS_DIR and extracts airport
    metadata including IATA code, ICAO code, location, name, Wikipedia URL,
    and outdegree (number of connections).

    Parameters
    ----------
    verbose : bool, optional
        If True, prints status messages (default: False)

    Returns
    -------
    str
        Path to the output CSV file (data/public/airports_information.csv)

    Output CSV Format
    -----------------
    Columns: iata, icao, latitude, longitude, name, wikipedia_url, outdegree

    Notes
    -----
    - Outdegree is the number of destination airports listed for each airport
    - Some airports may have missing fields, which appear as empty strings
    - This function is typically run before create_outbound_connections_list()
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

    return output_csv


def check_duplicated_iata_codes(verbose=False):
    """
    Check for and remove duplicate IATA code files, keeping the lowest distance version.

    For each IATA code, if there are files with different distance levels
    (e.g., YWG.0.json and YWG.1.json), removes the higher-level files and keeps
    only the lowest level. This ensures each airport appears only once.

    Parameters
    ----------
    verbose : bool, optional
        If True, prints status messages (default: False)

    Notes
    -----
    - This function modifies the file system by deleting files
    - It's recommended to run this after Wikipedia scraping is complete
    - Lower distance levels generally have more accurate data (closer to seed)
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


###############################################################################
# TWO-PASS WORKFLOW FUNCTIONS
###############################################################################

def run_two_pass_iata_extraction(batch_size=50, delay=0.5, verbose=False):
    """
    Execute the two-pass workflow to maximize IATA code recovery.

    This performs Passes 2 and 3 of the complete workflow:
    - Pass 2: Scrape Wikipedia for unmapped destination URLs
    - Pass 3: Create manual mapping file from scraped data

    Assumes Pass 1 (create_outbound_connections_list) has already been run.

    Parameters
    ----------
    batch_size : int, optional
        Number of URLs to process before pausing (default: 50)
    delay : float, optional
        Delay in seconds between requests (default: 0.5)
    verbose : bool, optional
        If True, prints detailed progress (default: False)

    Returns
    -------
    dict
        Summary of extraction results:
        - 'extraction_result': Result from extract_iata_from_unmapped_destinations()
        - 'mapping_count': Number of entries in manual_airport_mapping.csv
    """

    if verbose:
        print("\n" + "=" * 70)
        print("TWO-PASS IATA EXTRACTION WORKFLOW")
        print("=" * 70)

    # Pass 2: Scrape Wikipedia for IATA codes
    if verbose:
        print("\n[PASS 2] Scraping Wikipedia for unmapped IATA codes...")
        print("(This takes ~15 minutes for 1,500+ URLs)\n")

    extraction_result = extract_iata_from_unmapped_destinations(
        batch_size=batch_size,
        delay=delay,
        verbose=verbose
    )

    # Pass 3: Create manual mapping from scraped data
    if verbose:
        print("\n[PASS 3] Creating manual_airport_mapping.csv...")

    mapping_count = create_manual_mapping_from_scraped_data(
        min_confidence=0.7,
        verbose=verbose
    )

    return {
        'extraction_result': extraction_result,
        'mapping_count': mapping_count
    }


###############################################################################
# CONVENIENCE IMPORTS
###############################################################################

__all__ = [
    'export_all_airport_data',
    'check_duplicated_iata_codes',
    'create_outbound_connections_list',
    'extract_iata_from_unmapped_destinations',
    'create_manual_mapping_from_scraped_data',
    'create_outbound_adjacency_matrix',
    'run_two_pass_iata_extraction',
]


###############################################################################
# MAIN EXECUTION
###############################################################################

if __name__ == "__main__":
    """
    Complete pipeline for GATN generation with two-pass IATA extraction.
    
    Runs all 4+ passes:
    1. Export airport metadata
    2. Create initial connections list (identifies unmapped URLs)
    3. Scrape Wikipedia for unmapped IATA codes
    4. Create manual mapping from scraped data
    5. Re-run connections with enriched data
    6. Create adjacency matrices
    """
    print("=" * 70)
    print("GLOBAL AIR TRANSPORTATION NETWORK (GATN)")
    print("Complete Processing Pipeline with Two-Pass IATA Extraction")
    print("=" * 70)

    # Step 1: Export airport metadata
    print("\n[STEP 1] Exporting airport metadata...")
    export_csv = export_all_airport_data(verbose=True)

    # Step 2: Create initial connections list (Pass 1 of two-pass workflow)
    print("\n" + "=" * 70)
    print("[STEP 2] Creating initial outbound connections list (Pass 1)...")
    connections_csv, unmapped_csv = create_outbound_connections_list(
        verbose=True,
        export_unmapped=True
    )

    # Step 3 & 4: Run two-pass IATA extraction
    print("\n" + "=" * 70)
    print("[STEPS 3-4] Running two-pass IATA extraction...")
    print("(This will take approximately 20 minutes)")

    try:
        two_pass_result = run_two_pass_iata_extraction(
            batch_size=50,
            delay=0.5,
            verbose=True
        )

        extraction = two_pass_result['extraction_result']
        mapping_count = two_pass_result['mapping_count']

        if extraction['successful'] > 0:
            # Step 5: Re-run connections with enriched data
            print("\n" + "=" * 70)
            print("[STEP 5] Re-running connections with enriched data...")
            connections_csv, unmapped_csv = create_outbound_connections_list(
                verbose=True,
                export_unmapped=True
            )

            # Step 6: Create adjacency matrices
            print("\n" + "=" * 70)
            print("[STEP 6] Creating adjacency matrix (non-symmetric)...")
            matrix_npz, nodes_txt = create_outbound_adjacency_matrix(
                symmetric=False,
                verbose=True
            )

            print("\n" + "=" * 70)
            print("[STEP 7] Creating adjacency matrix (symmetric)...")
            matrix_sym_npz, nodes_sym_txt = create_outbound_adjacency_matrix(
                symmetric=True,
                verbose=True
            )

            print("\n" + "=" * 70)
            print("✓ ALL PROCESSING COMPLETE!")
            print("=" * 70)
            print(f"\nTwo-Pass IATA Extraction Summary:")
            print(f"  Successfully extracted: {extraction['successful']}/{extraction['total']}")
            print(f"  Success rate: {extraction['successful']/extraction['total']*100:.1f}%")
            print(f"  Manual mappings created: {mapping_count}")
            print(f"\nOutput Files:")
            print(f"  Connections: {connections_csv}")
            print(f"  Matrix (asymmetric): {matrix_npz}")
            print(f"  Matrix (symmetric): {matrix_sym_npz}")
        else:
            print("\n⚠️ No unmapped URLs to extract. Skipping two-pass workflow.")
            print("This is fine if you already have complete mappings.")

    except ImportError as e:
        print(f"\n⚠️ Missing dependencies for two-pass extraction: {e}")
        print("Install with: pip install requests beautifulsoup4")
        print("\nContinuing with standard pipeline (steps 6-7)...")

        # Still create adjacency matrices with current connections
        print("\n" + "=" * 70)
        print("[STEP 6] Creating adjacency matrix (non-symmetric)...")
        matrix_npz, nodes_txt = create_outbound_adjacency_matrix(
            symmetric=False,
            verbose=True
        )

        print("\n" + "=" * 70)
        print("[STEP 7] Creating adjacency matrix (symmetric)...")
        matrix_sym_npz, nodes_sym_txt = create_outbound_adjacency_matrix(
            symmetric=True,
            verbose=True
        )

        print("\n" + "=" * 70)
        print("✓ STANDARD PIPELINE COMPLETE")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Error during two-pass extraction: {e}")
        print("Continuing with standard pipeline...")

        # Still create adjacency matrices
        print("\n" + "=" * 70)
        print("[STEP 6] Creating adjacency matrix (non-symmetric)...")
        matrix_npz, nodes_txt = create_outbound_adjacency_matrix(
            symmetric=False,
            verbose=True
        )

        print("\n" + "=" * 70)
        print("[STEP 7] Creating adjacency matrix (symmetric)...")
        matrix_sym_npz, nodes_sym_txt = create_outbound_adjacency_matrix(
            symmetric=True,
            verbose=True
        )