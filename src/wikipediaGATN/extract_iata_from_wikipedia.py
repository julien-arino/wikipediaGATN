"""
Extract IATA codes from unmapped destination URLs.

This module resolves destination airports by first performing a fast, offline 
lookup against the authoritative OurAirports database. If the airport is not 
found, it falls back to fetching the Wikipedia page and extracting the IATA code 
using pattern matching (e.g. ``(IATA: XXX, ICAO: YYYY)``).

Typical workflow
----------------
1. Run ``create_outbound_connections_list()``      → generates ``unmapped_destinations.csv``
2. Run ``extract_iata_from_unmapped_destinations()`` → populates IATA codes in that CSV
3. Run ``create_manual_mapping_from_scraped_data()`` → builds ``manual_airport_mapping.csv``
4. Rerun ``create_outbound_connections_list()``    → better coverage using the new mappings
"""

import csv
import os
import re
import time
import warnings
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR

# ---------------------------------------------------------------------------
# Package-level constants
# ---------------------------------------------------------------------------

#: Wikipedia API bot policy requires a meaningful User-Agent that includes
#: the package name, version, and a contact address.
_USER_AGENT = (
    "wikipediaGATN/0.1.0 "
    "(Global Air Transportation Networks research; "
    "julien.arino@umanitoba.ca)"
)

# Compiled regex patterns used by _extract_iata_from_wikipedia_page.
# Compiled once at module load rather than on every function call.

#: Pattern 1 – standard Wikipedia infobox: ``(IATA: XYZ, ICAO: ABCD …)``
_PAT_IATA_STANDARD = re.compile(r"\(IATA:\s*([A-Z]{3})\s*[,)]", re.IGNORECASE)

#: Pattern 2 – closing-paren variant: ``IATA: XYZ)``
_PAT_IATA_PAREN = re.compile(r"IATA:\s*([A-Z]{3})\)", re.IGNORECASE)

#: Pattern 3 – generic code mention (lowest confidence)
_PAT_IATA_GENERIC = re.compile(r"(?:IATA|Code)[:\s]+([A-Z]{3})(?:\s|,|\))", re.IGNORECASE)

#: ICAO codes are always 4 uppercase letters
_PAT_ICAO = re.compile(r"ICAO:\s*([A-Z]{4})", re.IGNORECASE)

#: Common English trigrams that could be mistaken for IATA codes by pattern 3.
#: This list is intentionally conservative — extend it rather than shrink it.
_COMMON_WORD_TRIGRAMS = frozenset({
    "THE", "FOR", "AND", "USE", "SEE", "NOT", "ARE", "NEW", "AIR",
    "NAV", "FAA", "ICA", "ATC", "VFR", "IFR", "GPS", "UTC", "GMT",
})

#: Paragraph-text substrings that indicate disambiguation or redirect pages —
#: these should be skipped.  Note: "for the" is intentionally excluded because
#: it appears in many legitimate airport descriptions.
_SKIP_PHRASES = frozenset({
    "redirect",
    "not to be confused",
    "for other uses",
    "may refer to",
    "disambiguation",
})


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _is_safe_wikipedia_url(url: str) -> bool:
    """
    Ensure the URL is a valid Wikipedia URL.

    Checks that the scheme is 'https' and the domain is 'wikipedia.org'
    or a subdomain of it (e.g., 'en.wikipedia.org', 'fr.wikipedia.org').
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        domain = parsed.netloc.lower()
        return domain == "wikipedia.org" or domain.endswith(".wikipedia.org")
    except Exception:  # noqa: BLE001
        return False


def _extract_iata_from_wikipedia_page(url: str, verbose: bool = False) -> dict:
    """
    Fetch a Wikipedia page and extract the airport's IATA code.

    Tries three patterns in decreasing order of confidence:

    1. Standard infobox format: ``(IATA: XYZ, ICAO: ABCD …)`` — confidence 0.95
    2. Closing-paren variant: ``IATA: XYZ)``                    — confidence 0.90
    3. Generic code mention: ``IATA: XYZ`` or ``Code: XYZ``     — confidence 0.70

    Only the first five non-disambiguation paragraphs are examined.

    Parameters
    ----------
    url : str
        Full Wikipedia URL for the airport page.
    verbose : bool, optional
        If True, prints extraction details to stdout.  Default: False.

    Returns
    -------
    dict
        A result dictionary with the following keys:

        * ``'iata'``           – extracted IATA code (3 uppercase letters) or ``None``.
        * ``'icao'``           – extracted ICAO code (4 letters) or ``None``.
        * ``'confidence'``     – float in [0, 1]; 0 means extraction failed.
        * ``'extracted_text'`` – first 200 characters of the paragraph where the
          code was found, or ``None``.
        * ``'error'``          – human-readable error description, or ``None``.
    """
    result = {
        "iata":           None,
        "icao":           None,
        "confidence":     0.0,
        "extracted_text": None,
        "error":          None,
    }

    if not _is_safe_wikipedia_url(url):
        result["error"] = f"Invalid or unsafe URL: {url}"
        if verbose:
            print(f"    Validation failed: {url}")
        return result

    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        result["error"] = f"HTTP error: {exc}"
        if verbose:
            print(f"    Request failed: {exc}")
        return result

    try:
        soup       = BeautifulSoup(response.content, "html.parser")
        paragraphs = soup.find_all("p")
        examined   = 0

        for para in paragraphs:
            text = para.get_text(separator=" ", strip=True)
            if not text:
                continue

            # Skip disambiguation / redirect paragraphs
            text_lower = text.lower()
            if any(phrase in text_lower for phrase in _SKIP_PHRASES):
                continue

            examined += 1
            if examined > 5:
                break

            # ---- Pattern 1: standard infobox ----------------------------
            m = _PAT_IATA_STANDARD.search(text)
            if m:
                iata = m.group(1).upper()
                result["iata"]           = iata
                result["confidence"]     = 0.95
                result["extracted_text"] = text[:200]
                icao_m = _PAT_ICAO.search(text)
                if icao_m:
                    result["icao"] = icao_m.group(1).upper()
                if verbose:
                    print(f"    [P1] Found {iata} in: {text[:100]}…")
                return result

            # ---- Pattern 2: closing-paren variant -----------------------
            m = _PAT_IATA_PAREN.search(text)
            if m:
                iata = m.group(1).upper()
                result["iata"]           = iata
                result["confidence"]     = 0.90
                result["extracted_text"] = text[:200]
                if verbose:
                    print(f"    [P2] Found {iata} in: {text[:100]}…")
                return result

            # ---- Pattern 3: generic mention (low confidence) ------------
            if "airport" in text_lower or "iata" in text_lower:
                m = _PAT_IATA_GENERIC.search(text)
                if m:
                    iata = m.group(1).upper()
                    if iata not in _COMMON_WORD_TRIGRAMS:
                        result["iata"]           = iata
                        result["confidence"]     = 0.70
                        result["extracted_text"] = text[:200]
                        if verbose:
                            print(f"    [P3] Found {iata} in: {text[:100]}…")
                        return result

        result["error"] = "No IATA pattern found in first 5 content paragraphs"
        if verbose:
            print("    No IATA code found")

    except Exception as exc:  # noqa: BLE001
        result["error"] = f"Parse error: {exc}"
        warnings.warn(
            f"Unexpected parse error for {url}: {exc}",
            UserWarning,
            stacklevel=2,
        )
        if verbose:
            print(f"    Parse error: {exc}")

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_iata_from_unmapped_destinations(
    csv_path: str = None,
    batch_size: int = 50,
    delay: float = 0.5,
    verbose: bool = False,
) -> dict:
    """
    Extract IATA codes from Wikipedia pages for unmapped destinations.

    Reads ``unmapped_destinations.csv`` and attempts to resolve each URL.
    It prioritizes an instantaneous offline lookup against the OurAirports 
    database, falling back to Wikipedia web scraping only if the URL is not found.
    Results are written back to the same file atomically (write to a temp file 
    then rename).

    Rows that already have an IATA code are skipped and reported separately
    so that the success count only reflects codes extracted in *this* run.

    Parameters
    ----------
    csv_path : str, optional
        Path to ``unmapped_destinations.csv``.  Defaults to
        ``data/public/unmapped_destinations.csv``.
    batch_size : int, optional
        After every *batch_size* HTTP requests a longer pause is inserted to
        be polite to Wikipedia's servers.  Default: 50.
    delay : float, optional
        Per-request delay in seconds.  Default: 0.5.
    verbose : bool, optional
        If True, prints detailed per-URL progress.  Default: False.

    Returns
    -------
    dict
        Summary with keys ``'total'``, ``'successful'``, ``'skipped'``,
        ``'failed'``, and ``'csv_path'``.

    Raises
    ------
    FileNotFoundError
        If *csv_path* does not exist.

    Examples
    --------
    >>> # doctest: +SKIP
    >>> from wikipediaGATN.extract_iata_from_wikipedia import (
    ...     extract_iata_from_unmapped_destinations)
    >>> result = extract_iata_from_unmapped_destinations(verbose=True)
    >>> print(f"Extracted {result['successful']} new IATA codes")
    """
    if csv_path is None:
        csv_path = os.path.join(PUBLIC_DATA_DIR, "unmapped_destinations.csv")

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Unmapped destinations file not found: {csv_path}\n"
            "Run create_outbound_connections_list(export_unmapped=True) first."
        )

    if verbose:
        print(f"Loading unmapped destinations from {csv_path}…")

    with open(csv_path, "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    total      = len(rows)
    successful = 0   # new codes extracted in this run
    skipped    = 0   # rows that already had a code
    failed     = 0

    if total == 0:
        if verbose:
            print("CSV is empty — nothing to do.")
        return {"total": 0, "successful": 0, "skipped": 0, "failed": 0, "csv_path": csv_path}

    if verbose:
        print(f"Found {total:,} rows\n")

    for idx, row in enumerate(rows, 1):
        url = row.get("url", "").strip()

        # ---- Already resolved in a previous run -------------------------
        if row.get("iata", "").strip():
            if verbose:
                print(f"[{idx}/{total}] Skipping (already has IATA): {url}")
            skipped += 1
            continue

        if verbose:
            print(f"[{idx}/{total}] Fetching: {url}")

        # ---- Offline Fast-Path: Check OurAirports Database First --------
        from .airport_level_functions import _load_ourairports_data
        oa_cache = _load_ourairports_data()
        
        # OurAirports has some http links and some https links, so we'll match by end of path
        url_end = url.split("wikipedia.org/")[-1]
        oa_match = next((row for wiki, row in oa_cache.items() if wiki.endswith(url_end)), None)
        
        if oa_match and oa_match.get("iata_code"):
            row["iata"] = oa_match["iata_code"]
            row["source"] = "ourairports_db (conf: 1.00)"
            successful += 1
            if verbose:
                print(f"    → {row['iata']} (offline from OurAirports)\n")
            continue

        # ---- Fallback: Web Scrape Wikipedia Page ------------------------
        result = _extract_iata_from_wikipedia_page(url, verbose=verbose)

        if result["iata"]:
            row["iata"]   = result["iata"]
            # Store confidence as a 0–1 float string so downstream parsing
            # can compare directly against numeric thresholds.
            row["source"] = f"scraped (conf: {result['confidence']:.2f})"
            successful   += 1
            if verbose:
                print(f"    → {result['iata']} (conf: {result['confidence']:.0%})\n")
        else:
            row["source"] = f"failed ({result.get('error', 'unknown')})"
            failed       += 1
            if verbose:
                print(f"    → failed: {result.get('error', 'unknown')}\n")

        # ---- Polite delay -----------------------------------------------
        # Longer pause every batch_size requests; skip the extra sleep after
        # the very last URL.
        if idx < total:
            if idx % batch_size == 0:
                pause = delay * batch_size
                if verbose:
                    print(f"Processed {idx}/{total}. Pausing {pause:.1f}s…\n")
                time.sleep(pause)
            else:
                time.sleep(delay)

    # ---- Atomic write-back ----------------------------------------------
    # Write to a temp file first; rename only when the write succeeds.
    # This prevents data loss if the process is interrupted mid-write.
    tmp_path = csv_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["url", "count", "iata", "name", "source"]
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path, csv_path)
    except Exception as exc:
        # Leave the .tmp file for inspection; don't clobber the original
        warnings.warn(
            f"Failed to write results to {csv_path}: {exc}\n"
            f"Partial results are in {tmp_path}",
            UserWarning,
            stacklevel=2,
        )
        raise

    if verbose:
        print(f"\n{'=' * 70}")
        print("EXTRACTION COMPLETE")
        print(f"{'=' * 70}")
        print(f"Total rows         : {total:,}")
        print(f"New codes found    : {successful:,}")
        print(f"Already had code   : {skipped:,}")
        print(f"Failed             : {failed:,}")
        if (successful + failed) > 0:
            rate = successful / (successful + failed) * 100
            print(f"Success rate (new) : {rate:.1f}%")
        print(f"Updated CSV        : {os.path.abspath(csv_path)}")
        print("\n💡 Next: run create_manual_mapping_from_scraped_data() then")
        print("   rerun create_outbound_connections_list() for better coverage.")

    return {
        "total":      total,
        "successful": successful,
        "skipped":    skipped,
        "failed":     failed,
        "csv_path":   csv_path,
    }


def create_manual_mapping_from_scraped_data(
    unmapped_csv: str = None,
    output_csv: str = None,
    min_confidence: float = 0.70,
    verbose: bool = False,
) -> int:
    """
    Build ``manual_airport_mapping.csv`` from successfully scraped IATA codes.

    Reads the updated ``unmapped_destinations.csv`` produced by
    :func:`extract_iata_from_unmapped_destinations`, filters entries by
    confidence threshold, and writes a clean mapping file that
    :func:`~wikipediaGATN.connections.create_outbound_connections_list` will
    use as its highest-priority source on the next run.

    Parameters
    ----------
    unmapped_csv : str, optional
        Path to ``unmapped_destinations.csv``.
        Defaults to ``data/public/unmapped_destinations.csv``.
    output_csv : str, optional
        Destination path for ``manual_airport_mapping.csv``.
        Defaults to ``data/tmp_results/manual_airport_mapping.csv``.
    min_confidence : float, optional
        Minimum confidence threshold in [0, 1].  Entries scraped with
        confidence below this value are excluded.  Default: 0.70.
    verbose : bool, optional
        If True, prints a summary.  Default: False.

    Returns
    -------
    int
        Number of entries written to the manual mapping file.

    Raises
    ------
    FileNotFoundError
        If *unmapped_csv* does not exist.
    ValueError
        If *min_confidence* is outside [0, 1].
    """
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError(
            f"min_confidence must be in [0, 1], got {min_confidence!r}"
        )

    if unmapped_csv is None:
        unmapped_csv = os.path.join(PUBLIC_DATA_DIR, "unmapped_destinations.csv")

    if output_csv is None:
        output_csv = os.path.join(TEMP_RESULTS_DIR, "manual_airport_mapping.csv")

    if not os.path.exists(unmapped_csv):
        raise FileNotFoundError(
            f"Unmapped destinations file not found: {unmapped_csv}\n"
            "Run extract_iata_from_unmapped_destinations() first."
        )

    with open(unmapped_csv, "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    manual_mappings = []
    for row in rows:
        iata = row.get("iata", "").strip().upper()

        # Skip missing / sentinel values
        if not iata or iata in {"NONE", "ERROR", ""}:
            continue

        # Parse confidence stored as a 0–1 float string: "scraped (conf: 0.95)"
        source = row.get("source", "")
        if "conf:" in source:
            try:
                conf_match = re.search(r"conf:\s*([\d.]+)", source)
                if conf_match:
                    conf = float(conf_match.group(1))
                    # Values > 1 indicate the old %-based format; normalise.
                    if conf > 1.0:
                        conf /= 100.0
                    if conf < min_confidence:
                        continue
            except (ValueError, AttributeError):
                pass  # If unparseable, include the entry rather than drop it

        manual_mappings.append({
            "url":    row.get("url", ""),
            "iata":   iata,
            "name":   row.get("name", ""),
            "source": "web_scraped",
        })

    os.makedirs(TEMP_RESULTS_DIR, exist_ok=True)
    with open(output_csv, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["url", "iata", "name", "source"])
        writer.writeheader()
        writer.writerows(manual_mappings)

    if verbose:
        print(
            f"Created manual_airport_mapping.csv with "
            f"{len(manual_mappings):,} entries "
            f"(min_confidence={min_confidence:.0%})"
        )
        print(f"  Output: {os.path.abspath(output_csv)}")

    return len(manual_mappings)
