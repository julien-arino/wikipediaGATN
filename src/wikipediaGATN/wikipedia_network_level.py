"""
Network-level BFS crawling of airport Wikipedia pages.

This module drives the breadth-first expansion of the airport network.
Starting from a seed IATA code it iteratively fetches each airport's
destinations, saves the results as ``<CODE>.<level>.json`` files in
``TEMP_RESULTS_DIR``, and tracks progress in ``processed_locations.csv``
so that interrupted runs can be resumed.

Typical usage::

    from wikipediaGATN.wikipedia_network_level import iterate_search_until_distance_N

    # Crawl two hops out from Winnipeg
    iterate_search_until_distance_N("YWG", dist=2, delay=0.5, verbose=True)

Functions
---------
clean_output_directory            delete scraped files to start fresh
get_connections_level_N           expand one BFS level
check_processed_list              deduplicate / clean progress CSV
iterate_search_until_distance_N   crawl to a fixed depth
iterate_search_until_empty        crawl until no new airports are found
continue_existing_search_one_step     resume a partially-complete crawl by one step
continue_existing_search_until_empty  resume and run to completion
"""

import csv
import json
import os
import re
import time
import warnings

from .paths import TEMP_RESULTS_DIR
from .wikipedia_airport_level import (
    get_wikipedia_airport_page_link,
    extract_airport_information,
    save_airport_info,
)

__all__ = [
    "clean_output_directory",
    "get_connections_level_N",
    "check_processed_list",
    "iterate_search_until_distance_N",
    "iterate_search_until_empty",
    "continue_existing_search_one_step",
    "continue_existing_search_until_empty",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Matches both IATA-style (e.g. YWG.2.json) and wiki-prefixed filenames.
_FNAME_RE = re.compile(r"^(?:[A-Z]{3}|wiki_[A-Za-z0-9_]+)\.\d+\.json$")


def _level_pattern(level: int) -> re.Pattern:
    """Return a compiled regex matching airport JSON files at *level*."""
    return re.compile(r"^(?:[A-Z]{3}|wiki_[A-Za-z0-9_]+)\." + re.escape(str(level)) + r"\.json$")


def _find_max_level(output_dir: str) -> int:
    """
    Return the highest BFS level present in *output_dir*, or ``-1`` if none.

    Only IATA-style filenames (``[A-Z]{3}.<N>.json``) are considered when
    determining the frontier level — ``wiki_*`` files may appear at any
    level but are not used to drive the expansion loop.
    """
    pattern  = re.compile(r"^[A-Z]{3}\.(\d+)\.json$")
    max_level = -1
    for fname in os.listdir(output_dir):
        m = pattern.match(fname)
        if m:
            lvl = int(m.group(1))
            if lvl > max_level:
                max_level = lvl
    return max_level


def _read_processed_urls(output_dir: str) -> set:
    """
    Load the set of already-processed Wikipedia URLs from ``processed_locations.csv``.

    Uses :mod:`csv` so URLs containing commas are handled correctly.
    """
    csv_path = os.path.join(output_dir, "processed_locations.csv")
    urls: set = set()
    if not os.path.exists(csv_path):
        return urls
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            url = row.get("url", "").strip()
            if url:
                urls.add(url)
    return urls


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_output_directory(levels=None, verbose: bool = False) -> int:
    """
    Delete scraped airport JSON files from ``TEMP_RESULTS_DIR``.

    Also removes ``processed_locations.csv`` so the next run starts fresh.

    Parameters
    ----------
    levels : list of int or None, optional
        If ``None`` (default), removes **all** ``.<N>.json`` files.
        If a list of integers is given, only files at those BFS levels are
        removed (e.g. ``levels=[2, 3]``).
    verbose : bool, optional
        Print a summary of what was removed.  Default: False.

    Returns
    -------
    int
        Total number of JSON files removed.
    """
    output_dir = TEMP_RESULTS_DIR
    if not os.path.isdir(output_dir):
        if verbose:
            print("TEMP_RESULTS_DIR does not exist — nothing to clean.")
        return 0

    removed = 0
    for fname in os.listdir(output_dir):
        if levels is None:
            if _FNAME_RE.match(fname):
                try:
                    os.remove(os.path.join(output_dir, fname))
                    removed += 1
                except OSError as exc:
                    warnings.warn(f"Could not remove {fname}: {exc}", UserWarning, stacklevel=2)
        else:
            for lvl in levels:
                if fname.endswith(f".{lvl}.json") and _FNAME_RE.match(fname):
                    try:
                        os.remove(os.path.join(output_dir, fname))
                        removed += 1
                    except OSError as exc:
                        warnings.warn(f"Could not remove {fname}: {exc}", UserWarning, stacklevel=2)
                    break

    csv_path = os.path.join(output_dir, "processed_locations.csv")
    if os.path.exists(csv_path):
        try:
            os.remove(csv_path)
            if verbose:
                print("Removed processed_locations.csv.")
        except OSError as exc:
            warnings.warn(f"Could not remove processed_locations.csv: {exc}",
                          UserWarning, stacklevel=2)

    if verbose:
        print(f"Removed {removed} JSON file(s) from {output_dir}")
    return removed


def get_connections_level_N(
    from_length: int = 0,
    delay: float = 1.0,
    verbose: bool = False,
) -> int:
    """
    Expand the airport network by one BFS level.

    For every airport file at level *from_length* (``<CODE>.<from_length>.json``),
    fetch each listed destination that has not yet been processed and save its
    data as ``<CODE>.<from_length+1>.json``.

    Parameters
    ----------
    from_length : int, optional
        Source BFS level.  Default: 0.
    delay : float, optional
        Seconds to sleep between Wikipedia requests.  Default: 1.0.
    verbose : bool, optional
        Print per-destination progress.  Default: False.

    Returns
    -------
    int
        Number of new destination files written.
    """
    output_dir = TEMP_RESULTS_DIR
    os.makedirs(output_dir, exist_ok=True)

    pat        = _level_pattern(from_length)
    json_files = sorted(f for f in os.listdir(output_dir) if pat.match(f))

    processed_urls = _read_processed_urls(output_dir)
    written = 0

    for json_file in json_files:
        json_path = os.path.join(output_dir, json_file)
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                airport_info = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            warnings.warn(f"Skipping {json_file}: {exc}", UserWarning, stacklevel=2)
            continue

        origin_iata  = airport_info.get('iata', 'UNKNOWN')
        destinations = airport_info.get("destinations", [])

        for dest_entry in destinations:
            # Destinations are stored as [name, url] pairs.
            if not isinstance(dest_entry, (list, tuple)) or len(dest_entry) < 2:
                warnings.warn(
                    f"Malformed destination entry in {json_file}: {dest_entry!r}",
                    UserWarning, stacklevel=2,
                )
                continue
            dest_name, dest_url = dest_entry[0], dest_entry[1]

            if dest_url in processed_urls:
                if verbose:
                    print(f"  {origin_iata} -> {dest_name}: already processed, skipping")
                continue

            if verbose:
                print(f"  {origin_iata} -> {dest_name}: fetching...")

            dest_info = extract_airport_information(dest_url, verbose=verbose)
            dest_iata = dest_info.get('iata') or dest_name
            out_path  = os.path.join(output_dir, f"{dest_iata}.{from_length + 1}.json")

            if not os.path.exists(out_path):
                save_airport_info(dest_info, level=from_length + 1, verbose=verbose)
                written += 1

            processed_urls.add(dest_url)
            time.sleep(delay)

    if verbose:
        print(f"Level {from_length} -> {from_length + 1}: wrote {written} new file(s).")
    return written


def check_processed_list(verbose: bool = False) -> None:
    """
    Deduplicate and clean ``processed_locations.csv``.

    * Exports rows with ``iata == "None"`` to ``failed_lookups.csv``.
    * Removes those rows and any duplicate URLs from the main file.
    * Re-sorts by (iata, url).

    Parameters
    ----------
    verbose : bool, optional
        Print summary counts.  Default: False.
    """
    output_dir      = TEMP_RESULTS_DIR
    csv_path        = os.path.join(output_dir, "processed_locations.csv")
    failed_csv_path = os.path.join(output_dir, "failed_lookups.csv")

    if not os.path.exists(csv_path):
        if verbose:
            print("processed_locations.csv does not exist.")
        return

    # Read using csv module so commas inside URLs are handled correctly.
    entries: list = []
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != ["iata", "url"]:
            if verbose:
                print("processed_locations.csv is empty or has unexpected headers.")
            return
        for row in reader:
            entries.append((row.get("iata", "").strip(), row.get("url", "").strip()))

    failed_entries = sorted(
        [(iata, url) for iata, url in entries if iata == "None"],
        key=lambda x: x[1],
    )

    # Only write failed_lookups.csv when there is something to report.
    if failed_entries:
        with open(failed_csv_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
            writer.writerow(["iata", "url"])
            writer.writerows(failed_entries)
        if verbose:
            print(f"Exported {len(failed_entries)} failed lookups to {failed_csv_path}")
    elif verbose:
        print("No failed lookups found.")

    # Deduplicate valid entries by URL, then sort.
    seen_urls: set = set()
    unique_entries = []
    for iata, url in entries:
        if iata != "None" and url not in seen_urls:
            unique_entries.append((iata, url))
            seen_urls.add(url)
    cleaned_entries = sorted(unique_entries, key=lambda x: (x[0], x[1]))

    # Write cleaned file using csv module.
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
        writer.writerow(["iata", "url"])
        writer.writerows(cleaned_entries)

    if verbose:
        print(f"Cleaned processed_locations.csv: {len(cleaned_entries)} unique entries.")


def iterate_search_until_distance_N(
    seed_iata: str,
    dist: int = 1,
    delay: float = 1.0,
    verbose: bool = False,
) -> None:
    """
    Crawl the airport network to a fixed BFS depth.

    Parameters
    ----------
    seed_iata : str
        IATA code of the starting airport (e.g. ``"YWG"``).
    dist : int, optional
        Maximum BFS depth.  ``dist=1`` fetches only direct connections from
        the seed.  Default: 1.
    delay : float, optional
        Seconds to sleep between Wikipedia requests.  Default: 1.0.
    verbose : bool, optional
        Print per-airport progress.  Default: False.
    """
    link = get_wikipedia_airport_page_link(seed_iata, verbose=verbose)
    if not link:
        warnings.warn(f"Could not find Wikipedia page for {seed_iata!r}.",
                      UserWarning, stacklevel=2)
        return

    airport_details = extract_airport_information(link, verbose=verbose)
    save_airport_info(airport_details, level=0, verbose=verbose)

    if not airport_details.get("destinations"):
        warnings.warn(f"No destinations found for {seed_iata!r}. Stopping after seed.",
                      UserWarning, stacklevel=2)
        return

    for k in range(dist):
        if verbose:
            print(f"\nExpanding connections at distance {k + 1}...")
        get_connections_level_N(from_length=k, delay=delay, verbose=verbose)


def iterate_search_until_empty(
    seed_iata: str,
    delay: float = 1.0,
    verbose: bool = False,
) -> None:
    """
    Crawl the airport network until no new airports are discovered.

    Parameters
    ----------
    seed_iata : str
        IATA code of the starting airport.
    delay : float, optional
        Seconds between Wikipedia requests.  Default: 1.0.
    verbose : bool, optional
        Print per-airport progress.  Default: False.

    Notes
    -----
    For a global crawl this may run for many hours.  Use
    :func:`iterate_search_until_distance_N` if you want a bounded run.
    """
    link = get_wikipedia_airport_page_link(seed_iata, verbose=verbose)
    if not link:
        warnings.warn(f"Could not find Wikipedia page for {seed_iata!r}.",
                      UserWarning, stacklevel=2)
        return

    airport_details = extract_airport_information(link, verbose=verbose)
    save_airport_info(airport_details, level=0, verbose=verbose)

    if not airport_details.get("destinations"):
        warnings.warn(f"No destinations found for {seed_iata!r}. Stopping after seed.",
                      UserWarning, stacklevel=2)
        return

    output_dir = TEMP_RESULTS_DIR
    k = 0
    while True:
        if verbose:
            print(f"\nExpanding connections at distance {k + 1}...")
        pat    = _level_pattern(k + 1)
        before = {f for f in os.listdir(output_dir) if pat.match(f)}
        get_connections_level_N(from_length=k, delay=delay, verbose=verbose)
        after    = {f for f in os.listdir(output_dir) if pat.match(f)}
        new_files = after - before
        if not new_files:
            if verbose:
                print(f"No new connections found at distance {k + 1}. Stopping.")
            break
        k += 1


def continue_existing_search_one_step(delay: float = 1.0, verbose: bool = False) -> None:
    """
    Resume a partially-complete crawl by processing one additional BFS step.

    Finds the highest level *N* already present in ``TEMP_RESULTS_DIR`` and
    re-runs ``get_connections_level_N(from_length=N-1)`` — stepping back one
    level ensures the previous frontier is complete before advancing.

    Parameters
    ----------
    delay : float, optional
        Seconds between Wikipedia requests.  Default: 1.0.
    verbose : bool, optional
        Print progress.  Default: False.
    """
    output_dir = TEMP_RESULTS_DIR
    if not os.path.isdir(output_dir):
        warnings.warn(f"TEMP_RESULTS_DIR does not exist: {output_dir}",
                      UserWarning, stacklevel=2)
        return

    max_level = _find_max_level(output_dir)
    if max_level == -1:
        warnings.warn("No valid airport connection files found in TEMP_RESULTS_DIR.",
                      UserWarning, stacklevel=2)
        return

    # Guard against max_level == 0, which would pass from_length=-1.
    from_length = max(0, max_level - 1)
    if verbose:
        print(f"Resuming from level {from_length} to level {from_length + 1}...")

    get_connections_level_N(from_length=from_length, delay=delay, verbose=verbose)


def continue_existing_search_until_empty(delay: float = 1.0, verbose: bool = False) -> None:
    """
    Resume a partially-complete crawl and run to completion.

    Finds the highest BFS level *N* already present in ``TEMP_RESULTS_DIR``
    and continues expanding from that point until no new airports are found.

    Parameters
    ----------
    delay : float, optional
        Seconds between Wikipedia requests.  Default: 1.0.
    verbose : bool, optional
        Print progress.  Default: False.

    Notes
    -----
    Assumes the current highest level is already complete.  If it is not,
    use :func:`continue_existing_search_one_step` first.
    """
    output_dir = TEMP_RESULTS_DIR
    if not os.path.isdir(output_dir):
        warnings.warn(f"TEMP_RESULTS_DIR does not exist: {output_dir}",
                      UserWarning, stacklevel=2)
        return

    max_level = _find_max_level(output_dir)
    if max_level == -1:
        warnings.warn("No valid airport connection files found in TEMP_RESULTS_DIR.",
                      UserWarning, stacklevel=2)
        return

    k = max_level
    while True:
        if verbose:
            print(f"Continuing search from level {k} to level {k + 1}...")
        pat       = _level_pattern(k + 1)
        before    = {f for f in os.listdir(output_dir) if pat.match(f)}
        get_connections_level_N(from_length=k, delay=delay, verbose=verbose)
        after     = {f for f in os.listdir(output_dir) if pat.match(f)}
        new_files = after - before
        if not new_files:
            if verbose:
                print(f"No new connections found at level {k + 1}. Stopping.")
            break
        k += 1