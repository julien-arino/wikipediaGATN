"""
Generate outbound airport connections list from public JSON data.

This module parses augmented JSON files from the public airport_data directory
and creates a CSV file listing outbound connections for each airport. It exports
unmapped destination URLs to a CSV for later processing via web scraping.
"""

import csv
import json
import logging
import os
import warnings
from collections import Counter

from .paths import PUBLIC_DATA_DIR

logger = logging.getLogger(__name__)

def create_outbound_connections_list(
    verbose: bool = False,
    export_unmapped: bool = True,
):
    """
    Parse JSON files in ``PUBLIC_DATA_DIR/airport_data`` and write a connections CSV.

    Reads every ``<IATA>.json`` file, extracts the pre-mapped destination IATA codes,
    and writes the result to ``outbound_connections.csv``.

    Optionally exports a second CSV listing destination URLs that could not be
    mapped, so they can be resolved in a subsequent scraping pass.

    Parameters
    ----------
    verbose : bool, optional
        If True, prints detailed progress to stdout.  Default: False.
    export_unmapped : bool, optional
        If True, writes ``unmapped_destinations.csv`` listing all destination
        URLs that could not be resolved to an IATA code.  Default: True.

    Returns
    -------
    tuple of (str, str or None)
        ``(connections_csv_path, unmapped_csv_path)``.
        *unmapped_csv_path* is ``None`` when no unmapped URLs were found or
        when ``export_unmapped=False``.

    Raises
    ------
    FileNotFoundError
        If ``PUBLIC_DATA_DIR/airport_data`` does not exist.
    """
    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    if not os.path.isdir(airport_data_dir):
        raise FileNotFoundError(
            f"Public airport_data directory not found: {airport_data_dir}\n"
            "Run export_all_airport_data() first to populate this directory."
        )

    airport_connections: dict = {}
    unmapped_destinations = Counter()

    if verbose:
        print("Processing public airport JSON files...")

    for fname in sorted(os.listdir(airport_data_dir)):
        if not fname.endswith(".json"):
            continue

        fpath = os.path.join(airport_data_dir, fname)

        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            warnings.warn(f"Skipping {fname}: cannot read — {exc}", UserWarning, stacklevel=2)
            continue

        origin_iata = data.get("iata")
        if not origin_iata or origin_iata == "iata code not found":
            origin_iata = data.get("icao")
        
        if not origin_iata or origin_iata == "icao code not found":
            if verbose:
                print(f"  ⚠  No origin IATA or ICAO code found in {fname} — skipping")
            continue

        destinations = data.get("destinations", [])
        outlinks = set()

        for dest in destinations:
            # dest is a list: [name, wikipedia_url, dest_iata, dest_icao]
            if len(dest) >= 2:
                dest_url = dest[1]
                dest_iata = dest[2] if len(dest) > 2 else None
                dest_icao = dest[3] if len(dest) > 3 else None
                
                if dest_iata and dest_iata != "iata code not found":
                    outlinks.add(dest_iata)
                elif dest_icao and dest_icao != "icao code not found":
                    outlinks.add(dest_icao)
                elif dest_url:
                    unmapped_destinations[dest_url] += 1

        airport_connections[origin_iata] = {
            "origin": origin_iata,
            "outlinks": outlinks,
        }

        if verbose:
            print(f"  {origin_iata}: {len(outlinks)} connections")

    # ------------------------------------------------------------------
    # Report unmapped destinations
    # ------------------------------------------------------------------
    if unmapped_destinations and verbose:
        print(f"\n⚠️  {len(unmapped_destinations):,} unmapped destination URLs "
              f"({sum(unmapped_destinations.values()):,} total occurrences)")
        print("   Top 10 unmapped:")
        for url, count in unmapped_destinations.most_common(10):
            print(f"     {count:>4}x  {url}")

    # ------------------------------------------------------------------
    # Write outbound_connections.csv
    # ------------------------------------------------------------------
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "outbound_connections.csv")

    connections = sorted(airport_connections.values(), key=lambda x: x["origin"])

    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["origin", "nb_outlinks", "outlinks"],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for row in connections:
            outlinks_sorted = sorted(row["outlinks"])
            csv_row = {
                "origin": row["origin"],
                "nb_outlinks": len(outlinks_sorted),
                "outlinks": " ".join(outlinks_sorted),
            }
            writer.writerow(csv_row)

    if verbose:
        total = sum(len(c["outlinks"]) for c in connections)
        print(f"\n{'=' * 70}")
        print(" CONNECTIONS EXPORT COMPLETE")
        print(f"{'=' * 70}")
        print(f"Output   : {os.path.abspath(output_csv)}")
        print(f"Airports : {len(connections):,}")
        print(f"Total connections: {total:,}")

    # ------------------------------------------------------------------
    # Write unmapped_destinations.csv  (optional)
    # ------------------------------------------------------------------
    unmapped_csv = None
    if export_unmapped and unmapped_destinations:
        unmapped_csv = os.path.join(PUBLIC_DATA_DIR, "unmapped_destinations.csv")

        unmapped_list = sorted(
            ({"url": url, "count": count, "iata": "", "name": "", "source": "to_be_scraped"}
             for url, count in unmapped_destinations.items()),
            key=lambda x: x["count"],
            reverse=True,
        )

        with open(unmapped_csv, "w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=["url", "count", "iata", "name", "source"])
            writer.writeheader()
            writer.writerows(unmapped_list)

        if verbose:
            print(f"\n{'=' * 70}")
            print("UNMAPPED DESTINATIONS EXPORT")
            print(f"{'=' * 70}")
            print(f"Output   : {os.path.abspath(unmapped_csv)}")
            print(f"Unique unmapped URLs     : {len(unmapped_destinations):,}")
            print(f"Total unmapped occurrences: {sum(unmapped_destinations.values()):,}")
            print("\n💡 Next step: run extract_iata_from_wikipedia() to resolve these URLs.")

    return output_csv, unmapped_csv
