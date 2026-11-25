"""
Generate outbound airport connections list from public JSON data.

This module parses augmented JSON files from the public airport_data directory
and creates CSV files listing outbound passenger and cargo connections for each
airport. It exports unmapped destination URLs to a separate CSV for later
processing via web scraping.
"""

import csv
import json
import logging
import os
import warnings
from collections import Counter

from .paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR, unescape_reserved_code

logger = logging.getLogger(__name__)


def create_outbound_connections_list(
    verbose: bool = False,
    export_unmapped: bool = True,
):
    """
    Parse JSON files in ``PUBLIC_DATA_DIR/airport_data`` and write connection CSVs.

    Reads every ``<IATA>.json`` file, extracts the pre-mapped destination IATA codes,
    and writes the results to ``global-air-pax-network.csv`` and
    ``global-air-cargo-network.csv``.

    Optionally exports a third CSV listing destination URLs that could not be
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
    tuple of (str, str, str | None)
        ``(pax_csv_path, cargo_csv_path, unmapped_csv_path)``.
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
    airport_connections_cargo: dict = {}
    unmapped_destinations: Counter[str] = Counter()

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
            warnings.warn(
                f"Skipping {fname}: cannot read — {exc}", UserWarning, stacklevel=2
            )
            continue

        origin_iata = data.get("iata")
        if not origin_iata or origin_iata == "iata code not found":
            origin_iata = data.get("icao")

        if not origin_iata or origin_iata == "icao code not found":
            origin_iata = data.get("gps")

        if not origin_iata or origin_iata == "gps code not found":
            origin_iata = unescape_reserved_code(
                fname[:-5] if fname.endswith(".json") else fname
            )

        if not origin_iata:
            if verbose:
                print(
                    f"  [warning] No origin IATA, ICAO, GPS, or Ident code found in {fname} - skipping"
                )
            continue

        destinations = data.get("destinations", [])
        destinations_cargo = data.get("destinations_cargo", [])

        # When the airline/destination data came from the NLP fallback, its
        # airline counts are unreliable (every detected organisation is paired
        # with every place), so we do not publish them: fallback passenger edges
        # get weight 1 (presence only) and the airport's nb_airlines is dropped.
        # The fallback only ever populates passenger data, so cargo is unaffected.
        is_fallback = bool(data.get("airlines_nlp_fallback"))

        outlinks_weighted: Counter[str] = Counter()
        outlinks_cargo_weighted: Counter[str] = Counter()
        # Per-edge seasonality: a code maps to True only while every route to it
        # seen so far is seasonal; one year-round route flips it to False.
        seasonal_pax: dict[str, bool] = {}
        seasonal_cargo: dict[str, bool] = {}

        for dest_list, link_weighted_counter, seasonal_tracker in [
            (destinations, outlinks_weighted, seasonal_pax),
            (destinations_cargo, outlinks_cargo_weighted, seasonal_cargo),
        ]:
            for dest in dest_list:
                if isinstance(dest, dict):
                    # New dictionary format
                    dest_url = dest.get("wikipedia_url")
                    codes = dest.get("codes", [])
                    dest_iata = codes[0] if len(codes) > 0 else None
                    dest_icao = codes[1] if len(codes) > 1 else None
                    dest_gps = codes[2] if len(codes) > 2 else None
                    airline_count = len(dest.get("airlines", []))
                    dest_seasonal = bool(dest.get("seasonal"))
                elif isinstance(dest, list) and len(dest) >= 2:
                    # Old array format
                    dest_url = dest[1]
                    dest_iata = dest[2] if len(dest) > 2 else None
                    dest_icao = dest[3] if len(dest) > 3 else None
                    dest_gps = dest[4] if len(dest) > 4 else None
                    airline_count = 1  # Fallback for old format
                    dest_seasonal = False
                else:
                    continue

                # Suppress unreliable fallback-derived passenger airline counts.
                if is_fallback and link_weighted_counter is outlinks_weighted:
                    airline_count = 1

                target_code = None
                if dest_iata and dest_iata != "iata code not found":
                    target_code = dest_iata
                elif dest_icao and dest_icao != "icao code not found":
                    target_code = dest_icao
                elif dest_gps and dest_gps != "gps code not found":
                    target_code = dest_gps
                elif dest_url:
                    unmapped_destinations[dest_url] += 1

                if target_code:
                    # In case the same destination appears multiple times (rare but possible),
                    # we take the maximum airline count or sum them?
                    # Usually it's just one entry per destination.
                    link_weighted_counter[target_code] = max(
                        link_weighted_counter[target_code], airline_count
                    )
                    if target_code in seasonal_tracker:
                        seasonal_tracker[target_code] = (
                            seasonal_tracker[target_code] and dest_seasonal
                        )
                    else:
                        seasonal_tracker[target_code] = dest_seasonal

        airport_connections[origin_iata] = {
            "origin": origin_iata,
            "outlinks_weighted": outlinks_weighted,
            "seasonal_map": seasonal_pax,
            # Do not publish the airport-level airline count for fallback-sourced
            # data; it is an inflated artefact of the NLP pairing.
            "nb_airlines": 0 if is_fallback else (data.get("number_airlines", 0) or 0),
        }
        airport_connections_cargo[origin_iata] = {
            "origin": origin_iata,
            "outlinks_weighted": outlinks_cargo_weighted,
            "seasonal_map": seasonal_cargo,
            "nb_airlines": data.get("number_airlines_cargo", 0) or 0,
        }

        if verbose:
            print(f"  {origin_iata}: {len(outlinks_weighted)} connections")

    # ------------------------------------------------------------------
    # Report unmapped destinations
    # ------------------------------------------------------------------
    if unmapped_destinations and verbose:
        print(
            f"\n[warning] {len(unmapped_destinations):,} unmapped destination URLs "
            f"({sum(unmapped_destinations.values()):,} total occurrences)"
        )
        print("   Top 10 unmapped:")
        for url, count in unmapped_destinations.most_common(10):
            print(f"     {count:>4}x  {url}")

    # ------------------------------------------------------------------
    # Write global-air-pax-network.csv
    # ------------------------------------------------------------------
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "global-air-pax-network.csv")
    output_cargo_csv = os.path.join(PUBLIC_DATA_DIR, "global-air-cargo-network.csv")

    connections = sorted(airport_connections.values(), key=lambda x: x["origin"])
    connections_cargo = sorted(
        airport_connections_cargo.values(), key=lambda x: x["origin"]
    )

    for csv_path, conn_list in [
        (output_csv, connections),
        (output_cargo_csv, connections_cargo),
    ]:
        with open(csv_path, "w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=[
                    "origin",
                    "nb_outlinks",
                    "outlinks",
                    "weights",
                    "nb_airlines",
                    "seasonal",
                ],
                quoting=csv.QUOTE_ALL,
            )
            writer.writeheader()
            for row in conn_list:
                outlinks_sorted = sorted(row["outlinks_weighted"].keys())
                weights = [
                    str(row["outlinks_weighted"][code]) for code in outlinks_sorted
                ]
                seasonal_map = row.get("seasonal_map", {})
                # 0/1 per edge, aligned to the sorted outlinks: 1 = seasonal-only.
                seasonal_flags = [
                    "1" if seasonal_map.get(code) else "0" for code in outlinks_sorted
                ]
                csv_row = {
                    "origin": row["origin"],
                    "nb_outlinks": len(outlinks_sorted),
                    "outlinks": " ".join(outlinks_sorted),
                    "weights": " ".join(weights),
                    "nb_airlines": row.get("nb_airlines", 0),
                    "seasonal": " ".join(seasonal_flags),
                }
                writer.writerow(csv_row)

    if verbose:
        total = sum(len(c["outlinks_weighted"]) for c in connections)
        total_cargo = sum(len(c["outlinks_weighted"]) for c in connections_cargo)
        print(f"\n{'=' * 70}")
        print(" CONNECTIONS EXPORT COMPLETE")
        print(f"{'=' * 70}")
        print(f"Output (Pax)   : {os.path.abspath(output_csv)}")
        print(f"Output (Cargo) : {os.path.abspath(output_cargo_csv)}")
        print(f"Airports       : {len(connections):,}")
        print(f"Total connections (Pax):   {total:,}")
        print(f"Total connections (Cargo): {total_cargo:,}")

    # ------------------------------------------------------------------
    # Write unmapped_destinations.csv  (optional)
    # ------------------------------------------------------------------
    unmapped_csv = None
    if export_unmapped and unmapped_destinations:
        os.makedirs(TEMP_RESULTS_DIR, exist_ok=True)
        unmapped_csv = os.path.join(TEMP_RESULTS_DIR, "unmapped_destinations.csv")

        unmapped_list = sorted(
            (
                {
                    "url": url,
                    "count": count,
                    "iata": "",
                    "name": "",
                    "source": "to_be_scraped",
                }
                for url, count in unmapped_destinations.items()
            ),
            key=lambda x: int(str(x["count"])),
            reverse=True,
        )

        with open(unmapped_csv, "w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(
                csvfile, fieldnames=["url", "count", "iata", "name", "source"]
            )
            writer.writeheader()
            writer.writerows(unmapped_list)

        if verbose:
            print(f"\n{'=' * 70}")
            print("UNMAPPED DESTINATIONS EXPORT")
            print(f"{'=' * 70}")
            print(f"Output   : {os.path.abspath(unmapped_csv)}")
            print(f"Unique unmapped URLs     : {len(unmapped_destinations):,}")
            print(
                f"Total unmapped occurrences: {sum(unmapped_destinations.values()):,}"
            )
            print(
                "\n[tip] Next step: run extract_iata_from_wikipedia() to resolve these URLs."
            )

    return output_csv, output_cargo_csv, unmapped_csv
