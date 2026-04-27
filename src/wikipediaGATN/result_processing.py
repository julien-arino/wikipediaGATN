"""
Orchestration functions for GATN (Global Air Transportation Network) generation.

This module transforms raw airport JSON files (produced by Wikipedia scraping)
into structured network representations.  Functions are designed to be called
in the order shown below, but each can also be called independently.

Pipeline
--------
1. :func:`export_all_airport_data`              – extract airport metadata → CSV
2. :func:`check_duplicated_iata_codes`          – deduplicate JSON files
3. :func:`~.connections.create_outbound_connections_list`
                                                – build connections CSV (Pass 1)
4. :func:`~.extract_iata_from_wikipedia.extract_iata_from_unmapped_destinations`
                                                – scrape Wikipedia for IATA codes (Pass 2)
5. :func:`~.extract_iata_from_wikipedia.create_manual_mapping_from_scraped_data`
                                                – build manual mapping CSV (Pass 3)
6. :func:`~.connections.create_outbound_connections_list`
                                                – re-run with enriched data (Pass 4)
7. :func:`~.adjacency.create_outbound_adjacency_matrix`
                                                – build sparse adjacency matrices
"""

import csv
import datetime
import json
import logging
import os
import re
import shutil
import traceback
import warnings

from .adjacency import create_outbound_adjacency_matrix
from .connections import create_outbound_connections_list
from .extract_iata_from_wikipedia import (
    create_manual_mapping_from_scraped_data,
    extract_iata_from_unmapped_destinations,
)
from .paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR

logger = logging.getLogger(__name__)

# Matches both IATA-style (e.g. YWG.0.json) and wiki-prefixed
# (e.g. wiki_Winnipeg.1.json) filenames produced by the scraper.
_FNAME_RE = re.compile(r"^([A-Z]{3,4}|wiki_[A-Za-z0-9_]+)\.\d+\.json$")


###############################################################################
# AIRPORT DATA EXTRACTION
###############################################################################

def export_all_airport_data(verbose: bool = False) -> str:
    """
    Extract metadata from all airport JSON files and write to CSV.

    Scans every ``<IATA>.<distance>.json`` and ``wiki_*.<distance>.json`` file
    in ``TEMP_RESULTS_DIR`` and collects airport metadata into a single
    ``airports_information.csv``.

    Parameters
    ----------
    verbose : bool, optional
        If True, prints per-file status and a final summary.  Default: False.

    Returns
    -------
    str
        Absolute path to ``data/public/airports_information.csv``.

    Raises
    ------
    FileNotFoundError
        If ``TEMP_RESULTS_DIR`` does not exist.

    Notes
    -----
    * ``outdegree`` is the number of destination airports listed for each
      airport in its JSON file, not the verified network degree.
    * Fields absent from the JSON file are written as empty strings.
    * Run this function before
      :func:`~.connections.create_outbound_connections_list` so that
      ``airports_information.csv`` is available for URL→IATA mapping.
    """
    if not os.path.isdir(TEMP_RESULTS_DIR):
        raise FileNotFoundError(
            f"Temporary results directory not found: {TEMP_RESULTS_DIR}\n"
            "Run the Wikipedia scraping step first."
        )

    rows = []
    skipped = 0

    for fname in sorted(os.listdir(TEMP_RESULTS_DIR)):
        m = _FNAME_RE.match(fname)
        if not m:
            continue

        fpath = os.path.join(TEMP_RESULTS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            warnings.warn(f"Skipping {fname}: invalid JSON — {exc}", UserWarning, stacklevel=2)
            skipped += 1
            continue
        except OSError as exc:
            warnings.warn(f"Skipping {fname}: cannot read — {exc}", UserWarning, stacklevel=2)
            skipped += 1
            continue

        rows.append({
            "iata":          data.get("iata",         ""),
            "icao":          data.get("icao",         ""),
            # Store as plain strings; let downstream tools cast to float.
            "latitude":      data.get("latitude",     ""),
            "longitude":     data.get("longitude",    ""),
            "name":          data.get("name") or data.get("serves", ""),
            "wikipedia_url": data.get("wikipedia_url", ""),
            "outdegree":     len(data.get("destinations", [])),
        })

        # Copy the JSON file to public/airport_data, stripping the level
        airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
        os.makedirs(airport_data_dir, exist_ok=True)
        identifier = m.group(1)
        public_json_path = os.path.join(airport_data_dir, f"{identifier}.json")
        shutil.copy2(fpath, public_json_path)

    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")

    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = [
            "iata", "icao", "latitude", "longitude",
            "name", "wikipedia_url", "outdegree",
        ]
        # QUOTE_ALL avoids ambiguity: lat/lon stay as strings here and
        # downstream code that needs floats should cast them explicitly.
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    if verbose:
        print(f"Exported {len(rows):,} airports to {os.path.abspath(output_csv)}")
        if skipped:
            print(f"Skipped {skipped} unreadable files (see warnings above)")

    # Update README.md with the processing date
    readme_path = os.path.join(PUBLIC_DATA_DIR, "README.md")
    if os.path.exists(readme_path):
        today_str = datetime.date.today().isoformat()
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if "extracted on" in content:
            content = re.sub(r"\(extracted on \d{4}-\d{2}-\d{2}\)", f"(extracted on {today_str})", content)
        else:
            content = content.rstrip() + f"\n\nData extracted on {today_str}.\n"
            
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(content)

    return output_csv


###############################################################################
# DEDUPLICATION
###############################################################################

def check_duplicated_iata_codes(verbose: bool = False) -> int:
    """
    Remove duplicate airport JSON files, keeping the lowest-distance version.

    When the scraper revisits an airport at a greater distance from the seed
    (e.g. both ``YWG.0.json`` and ``YWG.1.json`` exist), the higher-distance
    file is deleted because the lower-distance file was scraped closer to the
    seed and is considered more accurate.

    Parameters
    ----------
    verbose : bool, optional
        If True, prints the name of each removed file.  Default: False.

    Returns
    -------
    int
        Number of duplicate files removed.

    Raises
    ------
    FileNotFoundError
        If ``TEMP_RESULTS_DIR`` does not exist.

    Notes
    -----
    This function **modifies the filesystem** by deleting files.  Run it after
    Wikipedia scraping is complete and before any processing steps.
    """
    if not os.path.isdir(TEMP_RESULTS_DIR):
        raise FileNotFoundError(
            f"Temporary results directory not found: {TEMP_RESULTS_DIR}\n"
            "Run the Wikipedia scraping step first."
        )

    pattern = re.compile(r"^([A-Z]{3})\.(\d+)\.json$")
    files_by_iata: dict = {}

    for fname in os.listdir(TEMP_RESULTS_DIR):
        m = pattern.match(fname)
        if m:
            iata  = m.group(1)
            level = int(m.group(2))
            files_by_iata.setdefault(iata, []).append((level, fname))

    removed = 0
    for iata, files in files_by_iata.items():
        if len(files) <= 1:
            continue

        files.sort()                                      # ascending by level
        to_remove = [fname for _, fname in files[1:]]    # keep files[0]

        for fname in to_remove:
            fpath = os.path.join(TEMP_RESULTS_DIR, fname)
            try:
                os.remove(fpath)
                removed += 1
                if verbose:
                    print(f"  Removed duplicate: {fname}")
            except OSError as exc:
                warnings.warn(
                    f"Could not remove {fname}: {exc}",
                    UserWarning, stacklevel=2,
                )

    if verbose:
        if removed:
            print(f"Removed {removed} duplicate file(s).")
        else:
            print("No duplicate IATA code files found.")

    return removed


###############################################################################
# TWO-PASS WORKFLOW
###############################################################################

def run_two_pass_iata_extraction(
    batch_size: int = 50,
    delay: float = 0.5,
    verbose: bool = False,
) -> dict:
    """
    Execute Passes 2 and 3 of the IATA recovery workflow.

    Assumes Pass 1 (:func:`~.connections.create_outbound_connections_list`)
    has already been run and ``unmapped_destinations.csv`` exists.

    Pass 2
        Fetches each unmapped Wikipedia URL and extracts the IATA code.
    Pass 3
        Filters successful extractions by confidence and writes
        ``manual_airport_mapping.csv`` for use in the next
        :func:`~.connections.create_outbound_connections_list` call.

    Parameters
    ----------
    batch_size : int, optional
        Number of HTTP requests before a longer pause is inserted to respect
        Wikipedia's servers.  Default: 50.
    delay : float, optional
        Per-request delay in seconds.  Default: 0.5.
    verbose : bool, optional
        If True, prints detailed per-URL progress.  Default: False.

    Returns
    -------
    dict
        ``{'extraction_result': dict, 'mapping_count': int}``

        *extraction_result* is the dict returned by
        :func:`~.extract_iata_from_wikipedia.extract_iata_from_unmapped_destinations`
        (keys: ``total``, ``successful``, ``skipped``, ``failed``, ``csv_path``).

        *mapping_count* is the number of entries written to
        ``manual_airport_mapping.csv``.
    """
    if verbose:
        print(f"\n{'=' * 70}")
        print("TWO-PASS IATA EXTRACTION WORKFLOW")
        print(f"{'=' * 70}")
        print("\n[PASS 2] Scraping Wikipedia for unmapped IATA codes…")
        print("(Allow ~15 minutes for 1 500+ URLs)\n")

    extraction_result = extract_iata_from_unmapped_destinations(
        batch_size=batch_size,
        delay=delay,
        verbose=verbose,
    )

    if verbose:
        print("\n[PASS 3] Creating manual_airport_mapping.csv…")

    mapping_count = create_manual_mapping_from_scraped_data(
        min_confidence=0.70,
        verbose=verbose,
    )

    return {
        "extraction_result": extraction_result,
        "mapping_count":     mapping_count,
    }


###############################################################################
# Public surface
###############################################################################

# Re-export the pipeline functions that live in sibling modules so that
# callers can do `from wikipediaGATN.result_processing import *` and get
# everything they need.  __init__.py is the canonical public API; the list
# here mirrors it for completeness.
__all__ = [
    "export_all_airport_data",
    "check_duplicated_iata_codes",
    "run_two_pass_iata_extraction",
    # Re-exported from sibling modules:
    "create_outbound_connections_list",
    "extract_iata_from_unmapped_destinations",
    "create_manual_mapping_from_scraped_data",
    "create_outbound_adjacency_matrix",
]


###############################################################################
# Command-line entry point
###############################################################################

def _run_pipeline() -> None:
    # Complete pipeline for GATN generation with two-pass IATA extraction.
    #
    # Steps:
    #   1. Export airport metadata
    #   2. Initial connections list  (Pass 1 — identifies unmapped URLs)
    #   3. Scrape Wikipedia for unmapped IATA codes  (Pass 2)
    #   4. Build manual mapping from scraped data    (Pass 3)
    #   5. Re-run connections with enriched mappings (Pass 4)
    #   6–7. Build asymmetric and symmetric adjacency matrices

    print("=" * 70)
    print("GLOBAL AIR TRANSPORTATION NETWORK (GATN)")
    print("Complete Processing Pipeline")
    print("=" * 70)

    # Step 1 ----------------------------------------------------------------
    print("\n[STEP 1] Exporting airport metadata…")
    export_all_airport_data(verbose=True)

    # Step 2 ----------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print("[STEP 2] Creating initial outbound connections list…")
    connections_csv, unmapped_csv = create_outbound_connections_list(
        verbose=True,
        export_unmapped=True,
    )

    # Steps 3–4 -------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print("[STEPS 3–4] Running two-pass IATA extraction…")
    print("(Approximately 20 minutes for a full global dataset)")

    try:
        two_pass = run_two_pass_iata_extraction(
            batch_size=50,
            delay=0.5,
            verbose=True,
        )
        extraction    = two_pass["extraction_result"]

        # Proceed to re-run whenever there was anything to process at all —
        # even if all codes were already resolved from a prior run.
        if extraction["total"] > 0:
            # Step 5 --------------------------------------------------------
            print(f"\n{'=' * 70}")
            print("[STEP 5] Re-running connections with enriched mappings…")
            connections_csv, unmapped_csv = create_outbound_connections_list(
                verbose=True,
                export_unmapped=True,
            )
        else:
            print("\n⚠️  unmapped_destinations.csv is empty — skipping re-run.")
            print("    This is expected if all destinations were already resolved.")

    except Exception:  # noqa: BLE001
        # Print the full traceback so the user knows exactly what went wrong,
        # then fall through to still produce the adjacency matrices from
        # whatever connections data is already on disk.
        print("\n✗ Two-pass extraction failed — see traceback below.")
        traceback.print_exc()
        print("\nContinuing with existing connections data…")

    # Steps 6–7 -------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print("[STEP 6] Creating adjacency matrix (directed)…")
    matrix_npz, nodes_txt = create_outbound_adjacency_matrix(
        symmetric=False,
        verbose=True,
    )

    print(f"\n{'=' * 70}")
    print("[STEP 7] Creating adjacency matrix (symmetric)…")
    matrix_sym_npz, nodes_sym_txt = create_outbound_adjacency_matrix(
        symmetric=True,
        verbose=True,
    )

    print(f"\n{'=' * 70}")
    print("✓ PIPELINE COMPLETE")
    print(f"{'=' * 70}")
    print(f"\n  Connections CSV   : {connections_csv}")
    print(f"  Matrix (directed) : {matrix_npz}")
    print(f"  Matrix (symmetric): {matrix_sym_npz}")


if __name__ == "__main__":
    _run_pipeline()
