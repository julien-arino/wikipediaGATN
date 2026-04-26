"""
Generate outbound airport connections list from Wikipedia data.

This module parses JSON files from Wikipedia scraping and creates a CSV file
listing outbound connections for each airport. It exports unmapped destination
URLs to a CSV for later processing via web scraping.
"""

import csv
import functools
import json
import logging
import os
import re
import warnings
from collections import Counter
from difflib import SequenceMatcher
from urllib.parse import unquote

import pandas as pd

from .paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-compiled regular expressions for performance
# ---------------------------------------------------------------------------
# Filename patterns for the two allowed JSON file shapes
_FNAME_IATA_RE  = re.compile(r"^([A-Z]{3})\.(\d+)\.json$")
_FNAME_WIKI_RE  = re.compile(r"^(wiki_[A-Za-z0-9_]+)\.(\d+)\.json$")

# URL and airport name extraction patterns
_WIKI_PATH_RE   = re.compile(r"/wiki/(.+?)(?:\?|$)")
_CLEAN_CHARS_RE = re.compile(r"[_\-\u2013\u2014]")
_AIRPORT_SUFFIX_RE = re.compile(
    r"\s+(?:(?:International|National)\s+)?Airport$",
    flags=re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1024)
def _normalize_url(url: str) -> str:
    """
    Normalize a Wikipedia URL for consistent dictionary lookup.

    Decodes percent-encoding, strips trailing slashes, and lowercases
    the entire string so that ``/wiki/Foo`` and ``/wiki/foo/`` map to the
    same key.

    Parameters
    ----------
    url : str
        Raw Wikipedia URL (may be empty or None).

    Returns
    -------
    str
        Normalized URL, or ``""`` if *url* is falsy.
    """
    if not url:
        return ""
    url = unquote(url)
    url = url.rstrip("/")
    return url.lower()


def _extract_airport_name_from_url(url: str):
    """
    Extract a human-readable airport name from a Wikipedia URL.

    Strips the ``/wiki/`` prefix, converts underscores/dashes to spaces,
    and removes common suffixes such as "International Airport".

    Parameters
    ----------
    url : str
        Wikipedia URL, e.g. ``https://en.wikipedia.org/wiki/Heathrow_Airport``.

    Returns
    -------
    str or None
        Cleaned airport name suitable for fuzzy matching, or ``None`` if the
        URL does not contain a recognisable ``/wiki/`` path segment.
    """
    if not url:
        return None

    m = _WIKI_PATH_RE.search(url)
    if not m:
        return None

    name = unquote(m.group(1))
    name = _CLEAN_CHARS_RE.sub(" ", name)
    # Combine suffix removals into a single pass
    name = _AIRPORT_SUFFIX_RE.sub("", name)

    name = name.strip()
    return name if name else None


@functools.lru_cache(maxsize=1024)
def _fuzzy_match_iata(airport_name: str, name_to_iata_items: frozenset):
    """
    Find the best IATA code for *airport_name* using fuzzy string matching.

    Uses :class:`difflib.SequenceMatcher` to compare *airport_name* against
    every key in *name_to_iata*.  Only returns a match when the similarity
    ratio meets the minimum threshold (0.75).

    .. note::
       This is an O(n) scan over *name_to_iata* and should only be invoked
       after direct URL lookup has failed.

    Parameters
    ----------
    airport_name : str
        Human-readable airport name extracted from a URL.
    name_to_iata_items : frozenset
        Frozenset of ``(airport_name_lower, iata_code)`` tuples.

    Returns
    -------
    tuple of (str or None, float)
        ``(best_iata_code, best_ratio)`` if a match above threshold is found,
        ``(None, best_ratio)`` otherwise.
    """
    if not airport_name or not name_to_iata_items:
        return None, 0.0

    # Threshold raised from 0.6 → 0.75 to reduce false-positive matches
    THRESHOLD = 0.75

    best_iata  = None
    best_ratio = 0.0
    query      = airport_name.lower()

    for stored_name, iata in name_to_iata_items:
        ratio = SequenceMatcher(None, query, stored_name.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_iata  = iata

    return (best_iata, best_ratio) if best_ratio >= THRESHOLD else (None, best_ratio)


def _load_csv_mapping(path: str, url_col: str, iata_col: str, name_col: str = None,
                      label: str = "", verbose: bool = False):
    """
    Load a URL→IATA (and optionally name→IATA) mapping from a CSV file.

    Performs a **single** pass over the DataFrame to build both dictionaries
    simultaneously.

    Parameters
    ----------
    path : str
        Absolute path to the CSV file.
    url_col : str
        Name of the column containing Wikipedia URLs.
    iata_col : str
        Name of the column containing IATA codes.
    name_col : str, optional
        Name of the column containing airport names.  If ``None``, the name
        mapping is not populated.
    label : str, optional
        Human-readable label used in verbose/warning messages.
    verbose : bool, optional
        If True, prints a loading summary.

    Returns
    -------
    tuple of (dict, dict)
        ``(url_to_iata, name_to_iata)`` dictionaries.  Both may be empty if
        the file cannot be read or required columns are absent.
    """
    url_to_iata  = {}
    name_to_iata = {}

    if not os.path.exists(path):
        return url_to_iata, name_to_iata

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        warnings.warn(f"Could not read {label} ({path}): {exc}", UserWarning, stacklevel=3)
        return url_to_iata, name_to_iata

    missing = [c for c in [url_col, iata_col] if c not in df.columns]
    if missing:
        warnings.warn(
            f"{label}: expected columns {missing} not found. "
            f"Available columns: {list(df.columns)}",
            UserWarning, stacklevel=3,
        )
        return url_to_iata, name_to_iata

    df = df.dropna(subset=[url_col, iata_col])

    # Single pass — build both dicts at once using zip() for speed
    if name_col and name_col in df.columns:
        for url_val, iata_val, name_val in zip(df[url_col], df[iata_col], df[name_col]):
            url  = _normalize_url(str(url_val))
            iata = str(iata_val).strip().upper()
            if url and iata:
                url_to_iata[url] = iata
            if pd.notna(name_val):
                name = str(name_val).strip()
                if name and iata:
                    name_to_iata[name] = iata
    else:
        for url_val, iata_val in zip(df[url_col], df[iata_col]):
            url  = _normalize_url(str(url_val))
            iata = str(iata_val).strip().upper()
            if url and iata:
                url_to_iata[url] = iata

    if verbose:
        print(f"  {label}: loaded {len(url_to_iata):,} URL mappings"
              + (f", {len(name_to_iata):,} name mappings" if name_to_iata else ""))

    return url_to_iata, name_to_iata


def _build_url_to_iata_mapping(verbose: bool = False):
    """
    Build a comprehensive URL→IATA mapping from all available source files.

    Loads three CSV sources in priority order (lowest → highest), so that
    later sources override earlier ones for the same URL:

    1. ``data/public/airports_information.csv``  (generated by scraping)
    2. ``data/tmp_results/processed_locations.csv``  (intermediate scraping state)
    3. ``data/tmp_results/manual_airport_mapping.csv``  (highest priority —
       hand-curated overrides)

    Parameters
    ----------
    verbose : bool, optional
        If True, prints a summary for each source file loaded.

    Returns
    -------
    tuple of (dict, dict)
        ``(url_to_iata, name_to_iata)`` — combined mappings from all sources.
    """
    url_to_iata  = {}
    name_to_iata = {}

    # ---- Source 1: airports_information.csv --------------------------------
    u, n = _load_csv_mapping(
        path     = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv"),
        url_col  = "wikipedia_url",
        iata_col = "iata",
        name_col = "name",
        label    = "airports_information.csv",
        verbose  = verbose,
    )
    url_to_iata.update(u)
    name_to_iata.update(n)

    # ---- Source 2: processed_locations.csv ---------------------------------
    # Column names are not fixed — detect them by checking for 'url' / 'iata'
    # / 'name' substrings, but require an **unambiguous** match.
    proc_path = os.path.join(TEMP_RESULTS_DIR, "processed_locations.csv")
    if os.path.exists(proc_path):
        try:
            proc_df   = pd.read_csv(proc_path)
            url_cols  = [c for c in proc_df.columns if "url"  in c.lower()]
            iata_cols = [c for c in proc_df.columns if "iata" in c.lower()]
            name_cols = [c for c in proc_df.columns if "name" in c.lower()]

            if len(url_cols) == 1 and len(iata_cols) == 1:
                u, n = _load_csv_mapping(
                    path     = proc_path,
                    url_col  = url_cols[0],
                    iata_col = iata_cols[0],
                    name_col = name_cols[0] if len(name_cols) == 1 else None,
                    label    = "processed_locations.csv",
                    verbose  = verbose,
                )
                url_to_iata.update(u)
                name_to_iata.update(n)
            elif verbose:
                print(
                    f"  processed_locations.csv: ambiguous columns "
                    f"(url_cols={url_cols}, iata_cols={iata_cols}) — skipped"
                )
        except Exception as exc:
            warnings.warn(
                f"Could not read processed_locations.csv: {exc}",
                UserWarning, stacklevel=2,
            )

    # ---- Source 3: manual_airport_mapping.csv (highest priority) -----------
    u, n = _load_csv_mapping(
        path     = os.path.join(TEMP_RESULTS_DIR, "manual_airport_mapping.csv"),
        url_col  = "url",
        iata_col = "iata",
        name_col = "name",
        label    = "manual_airport_mapping.csv",
        verbose  = verbose,
    )
    url_to_iata.update(u)
    name_to_iata.update(n)

    return url_to_iata, name_to_iata


def _extract_origin_iata(data: dict, origin_code: str) -> str | None:
    """
    Resolve the IATA code for an origin airport from its JSON data.

    Checks the JSON payload first, then falls back to the filename stem.
    Both the lowercase ``"iata"`` and uppercase ``"IATA"`` keys are checked
    in a single step.

    Parameters
    ----------
    data : dict
        Parsed JSON content of the airport file.
    origin_code : str
        The filename stem (e.g. ``"YWG"`` or ``"wiki_Winnipeg"``).

    Returns
    -------
    str or None
        IATA code (3 uppercase letters), or ``None`` if unresolvable.
    """
    # Check JSON payload (both key casings) first
    iata = data.get("iata") or data.get("IATA")
    if iata:
        return str(iata).strip().upper()

    # Fall back to filename stem only when it is a valid 3-letter IATA code
    if len(origin_code) == 3 and origin_code.isupper():
        return origin_code

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_outbound_connections_list(
    verbose: bool = False,
    export_unmapped: bool = True,
):
    """
    Parse JSON files in ``TEMP_RESULTS_DIR`` and write a connections CSV.

    Reads every ``<IATA>.<distance>.json`` and ``wiki_*.<distance>.json`` file,
    maps destination Wikipedia URLs to IATA codes using a three-source lookup
    table, and writes the result to ``outbound_connections.csv``.  When
    multiple files exist for the same airport (different scraping distances),
    the file closest to the seed (lowest distance) is used.

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
        If ``TEMP_RESULTS_DIR`` does not exist.

    Notes
    -----
    Destination lookup uses two strategies in sequence:

    1. **Direct URL match** against the combined URL→IATA mapping.
    2. **Fuzzy name match** (similarity ≥ 0.75) against the name→IATA mapping,
       applied only when strategy 1 fails.

    Examples
    --------
    >>> # doctest: +SKIP
    >>> connections_csv, unmapped_csv = create_outbound_connections_list(verbose=True)
    """

    if not os.path.isdir(TEMP_RESULTS_DIR):
        raise FileNotFoundError(
            f"Temporary results directory not found: {TEMP_RESULTS_DIR}\n"
            "Run the Wikipedia scraping step first to populate this directory."
        )

    airport_connections: dict  = {}
    unmapped_destinations      = Counter()

    # ------------------------------------------------------------------
    # Build URL→IATA mapping from all available sources
    # ------------------------------------------------------------------
    if verbose:
        print("Building URL-to-IATA mapping...")

    url_to_iata, name_to_iata = _build_url_to_iata_mapping(verbose=verbose)

    if verbose:
        print(f"  Total URL mappings : {len(url_to_iata):,}")
        print(f"  Total name mappings: {len(name_to_iata):,}\n")
        print("Processing airport JSON files...")

    # Optimization: Convert name mapping to a frozenset once for cached matching
    name_to_iata_items = frozenset(name_to_iata.items())

    # ------------------------------------------------------------------
    # Process each JSON file
    # ------------------------------------------------------------------
    for fname in sorted(os.listdir(TEMP_RESULTS_DIR)):
        if not fname.endswith(".json"):
            continue

        # Match against either allowed filename pattern
        m = _FNAME_IATA_RE.match(fname) or _FNAME_WIKI_RE.match(fname)
        if not m:
            continue

        origin_code  = m.group(1)
        distance     = int(m.group(2))
        fpath        = os.path.join(TEMP_RESULTS_DIR, fname)

        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            warnings.warn(f"Skipping {fname}: invalid JSON — {exc}", UserWarning, stacklevel=2)
            continue
        except OSError as exc:
            warnings.warn(f"Skipping {fname}: cannot read — {exc}", UserWarning, stacklevel=2)
            continue

        # Resolve IATA code for this origin airport
        origin_iata = _extract_origin_iata(data, origin_code)
        if not origin_iata:
            if verbose:
                print(f"  ⚠  No IATA code found for {fname} — skipping")
            continue

        # Keep only the file closest to the seed (lowest distance)
        existing = airport_connections.get(origin_iata)
        if existing is not None and distance >= existing["_distance"]:
            continue

        # ------------------------------------------------------------------
        # Map destination URLs → IATA codes
        # ------------------------------------------------------------------
        destinations = (
            data.get("destinations")
            or data.get("destination")
            or data.get("dest")
            or []
        )

        outlinks: set = set()
        for dest in destinations:
            dest_url = None

            if isinstance(dest, (list, tuple)) and len(dest) >= 2:
                dest_url = dest[1]
            elif isinstance(dest, dict):
                dest_url = dest.get("wikipedia_url") or dest.get("url")

            if not dest_url:
                continue

            # Strategy 1: direct normalized URL lookup
            dest_iata = url_to_iata.get(_normalize_url(dest_url))

            # Strategy 2: fuzzy name matching (only when strategy 1 fails)
            if not dest_iata:
                airport_name = _extract_airport_name_from_url(dest_url)
                if airport_name:
                    dest_iata, _ = _fuzzy_match_iata(airport_name, name_to_iata_items)

            if dest_iata:
                outlinks.add(dest_iata)
            else:
                unmapped_destinations[dest_url] += 1

        airport_connections[origin_iata] = {
            "origin"      : origin_iata,
            "outlinks"    : outlinks,
            "_distance"   : distance,
        }

        if verbose:
            print(f"  [{distance}] {origin_iata}: {len(outlinks)} connections")

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
        # Use QUOTE_ALL so that nb_outlinks is written as an integer string
        # and is read back as a string that downstream code can safely cast.
        # Avoids the QUOTE_NONNUMERIC pitfall where unquoted numerics are
        # silently interpreted as floats by csv.reader / pandas.
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["origin", "nb_outlinks", "outlinks"],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for row in connections:
            # Finalize outlinks: sort the set and join with spaces
            outlinks_sorted = sorted(row["outlinks"])

            # Prepare row for CSV: exclude internal fields but include processed outlinks
            csv_row = {k: v for k, v in row.items() if not k.startswith("_")}
            csv_row["nb_outlinks"] = len(outlinks_sorted)
            csv_row["outlinks"]    = " ".join(outlinks_sorted)

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