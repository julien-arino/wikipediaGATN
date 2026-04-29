"""
Orchestration functions for GATN (Global Air Transportation Network) generation.

This module handles the extraction of network structure from scraped destinations
and builds adjacency matrices.
"""

import logging
import traceback

from .adjacency import create_outbound_adjacency_matrix
from .connections import create_outbound_connections_list
from .extract_iata_from_wikipedia import (
    create_manual_mapping_from_scraped_data,
    extract_iata_from_unmapped_destinations,
)
from .result_processing_airports import export_all_airport_data

logger = logging.getLogger(__name__)


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


__all__ = [
    "run_two_pass_iata_extraction",
]


###############################################################################
# Command-line entry point
###############################################################################

def _run_pipeline() -> None:
    # Complete pipeline for GATN generation with two-pass IATA extraction.
    #
    # Steps:
    #   1. Export airport metadata                 (Identifies unmapped URLs into JSON)
    #   2. Initial connections list                (Pass 1 — produces unmapped_destinations.csv)
    #   3. Scrape Wikipedia for unmapped IATAs     (Pass 2)
    #   4. Build manual mapping from scraped data  (Pass 3)
    #   5. Re-run airport metadata export          (Pass 4 - injects manual mappings into JSON)
    #   6. Re-run connections list                 (Pass 5)
    #   7–8. Build asymmetric and symmetric adjacency matrices

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
    connections_csv, connections_cargo_csv, unmapped_csv = create_outbound_connections_list(
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
            print("[STEP 5] Re-exporting airport metadata with enriched mappings…")
            export_all_airport_data(verbose=True)
            
            # Step 6 --------------------------------------------------------
            print(f"\n{'=' * 70}")
            print("[STEP 6] Re-running connections with enriched public JSON data…")
            connections_csv, connections_cargo_csv, unmapped_csv = create_outbound_connections_list(
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

    # Step 7 -------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print("[STEP 7] Creating adjacency matrix and network graphs (directed)…")
    matrix_npz, nodes_txt = create_outbound_adjacency_matrix(
        verbose=True,
        is_cargo=False,
    )

    print(f"\n{'=' * 70}")
    print("[STEP 8] Creating adjacency matrix and network graphs for CARGO (directed)…")
    matrix_cargo_npz, nodes_cargo_txt = create_outbound_adjacency_matrix(
        verbose=True,
        is_cargo=True,
    )

    print(f"\n{'=' * 70}")
    print("✓ PIPELINE COMPLETE")
    print(f"{'=' * 70}")
    print(f"\n  Connections CSV (Pax)     : {connections_csv}")
    print(f"  Connections CSV (Cargo)   : {connections_cargo_csv}")
    print(f"  Matrix (Pax directed)     : {matrix_npz}")
    print(f"  Matrix (Cargo directed)   : {matrix_cargo_npz}")


if __name__ == "__main__":
    _run_pipeline()
