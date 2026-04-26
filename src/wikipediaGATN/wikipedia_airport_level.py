"""
Airport-level Wikipedia scraping and data extraction functions.

Functions in this module interact with the Wikipedia API to fetch and parse
airport pages.  They are designed to be called in sequence, but each can also
be used standalone:

1. :func:`get_wikipedia_airport_page_link`         resolve an identifier to a URL
2. :func:`get_wikipedia_airport_page_html`         fetch parsed HTML
3. :func:`get_wikipedia_airport_page_wikitext`     fetch raw wikitext
4. :func:`extract_airlines_from_airport`           set of airline names
5. :func:`extract_destinations_from_airport`       set of (name, URL) tuples
6. :func:`extract_airlines_destinations_from_airport`  airline → destinations map
7. :func:`extract_airport_information`             all metadata in one dict
8. :func:`save_airport_info`                       persist dict to JSON + progress CSV

Helper / fallback functions:

* :func:`parse_infobox_from_wikitext`
* :func:`clean_infobox_value`
* :func:`parse_lat_lon_from_string`
* :func:`parse_iso3166_2`
* :func:`fallback_extract_airport_information`
* :func:`fallback_nlp_extract_airlines_destinations`
* :func:`extract_airlines_destinations_from_wikitext`
"""

import csv
import json
import os
import re
import logging
import urllib.parse
import warnings

import mwparserfromhell
import pycountry
import requests
from bs4 import BeautifulSoup
from geopy.point import Point

from .paths import TEMP_RESULTS_DIR

logger = logging.getLogger(__name__)

__all__ = [
    "get_wikipedia_airport_page_link",
    "get_wikipedia_airport_page_html",
    "get_wikipedia_airport_page_wikitext",
    "extract_airlines_from_airport",
    "extract_destinations_from_airport",
    "extract_airlines_destinations_from_airport",
    "extract_airport_information",
    "save_airport_info",
    "parse_infobox_from_wikitext",
    "clean_infobox_value",
    "parse_lat_lon_from_string",
    "parse_iso3166_2",
    "fallback_extract_airport_information",
    "fallback_nlp_extract_airlines_destinations",
    "extract_airlines_destinations_from_wikitext",
]

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_API_URL = "https://en.wikipedia.org/w/api.php"

# Wikipedia's bot policy requires a descriptive User-Agent with a contact
# address so they can reach out if the bot misbehaves.
_HEADERS = {
    "User-Agent": (
        "wikipediaGATN/1.0 (https://github.com/jarino; jarino@umanitoba.ca) "
        "python-requests"
    )
}

# Shared session — reuses TCP connections across all requests in a pipeline run.
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)

# ---------------------------------------------------------------------------
# spaCy model — loaded once; None if the model is not installed.
# ---------------------------------------------------------------------------
try:
    import spacy as _spacy
    _NLP = _spacy.load("en_core_web_sm")
except (ImportError, OSError):
    _NLP = None


# ---------------------------------------------------------------------------
# Wikipedia page lookup
# ---------------------------------------------------------------------------

def get_wikipedia_airport_page_link(identifier: str, verbose: bool = False):
    """
    Resolve an airport identifier to its Wikipedia page URL.

    Resolution order:

    1. If *identifier* is already a Wikipedia URL, the title is decoded from it.
    2. If *identifier* matches ``[A-Za-z]{3}`` or ``[A-Za-z]{4}`` (IATA/ICAO),
       search for ``"<CODE> airport"``.
    3. Otherwise, treat *identifier* as a free-text name; append ``" airport"``
       if the word is not already present.

    Parameters
    ----------
    identifier : str
        IATA code, ICAO code, Wikipedia URL, or free-text airport name.
    verbose : bool, optional
        Print search term and result.  Default: False.

    Returns
    -------
    str or None
        Canonical Wikipedia URL, or ``None`` if no page was found.
    """
    # 1. Wikipedia URL — decode title directly
    if isinstance(identifier, str) and identifier.startswith("http"):
        m = re.search(r'/wiki/([^#?]+)', identifier)
        if not m:
            warnings.warn(f"Invalid Wikipedia URL: {identifier!r}", UserWarning, stacklevel=2)
            return None
        search_term = urllib.parse.unquote(m.group(1)).replace('_', ' ')
        if verbose:
            print(f"Extracted page title from URL: {search_term}")
    # 2. IATA (3-letter) or ICAO (4-letter)
    elif re.fullmatch(r'[A-Za-z]{3,4}', identifier):
        search_term = f"{identifier.upper()} airport"
    # 3. Free-text name
    else:
        search_term = (
            identifier
            if "airport" in identifier.lower()
            else f"{identifier} airport"
        )

    if verbose:
        print(f"Searching Wikipedia for: {search_term!r}")

    params = {
        "action":        "query",
        "format":        "json",
        "list":          "search",
        "srsearch":      search_term,
        "formatversion": "2",
    }
    try:
        response = _SESSION.get(_API_URL, params=params, timeout=15)
        response.raise_for_status()
        results = response.json().get("query", {}).get("search", [])
    except requests.exceptions.RequestException as exc:
        logger.warning("Wikipedia search failed for %r", identifier, exc_info=exc)
        return None
    except (KeyError, ValueError) as exc:
        logger.warning("Could not parse search response for %r", identifier, exc_info=exc)
        return None

    if not results:
        warnings.warn(f"No Wikipedia page found for {identifier!r}.", UserWarning, stacklevel=2)
        return None

    # Prefer a result whose title contains "airport"
    page_title = next(
        (r["title"] for r in results if "airport" in r["title"].lower()),
        results[0]["title"],
    )

    if verbose:
        print(f"Resolved {identifier!r} -> {page_title!r}")

    return f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"


# ---------------------------------------------------------------------------
# HTML and wikitext fetchers
# ---------------------------------------------------------------------------

def get_wikipedia_airport_page_html(link: str, verbose: bool = False):
    """
    Fetch the parsed HTML content of a Wikipedia page.

    Parameters
    ----------
    link : str
        Wikipedia page URL (``https://en.wikipedia.org/wiki/<Title>``).
    verbose : bool, optional
        Print progress messages.  Default: False.

    Returns
    -------
    str or None
        HTML string, or ``None`` on failure.
    """
    m = re.search(r'/wiki/([^#?]+)', link)
    if not m:
        warnings.warn(f"Invalid Wikipedia URL: {link!r}", UserWarning, stacklevel=2)
        return None
    page_title = urllib.parse.unquote(m.group(1)).replace('_', ' ')
    if verbose:
        print(f"Fetching HTML for {page_title!r}...")

    params = {
        "action":        "parse",
        "page":          page_title,
        "prop":          "text",
        "format":        "json",
        "formatversion": "2",
    }
    try:
        response = _SESSION.get(_API_URL, params=params, timeout=20)
        response.raise_for_status()
        html = response.json().get("parse", {}).get("text")
        if not html:
            warnings.warn(f"No HTML content returned for {page_title!r}.",
                          UserWarning, stacklevel=2)
        elif verbose:
            print(f"Fetched HTML for {page_title!r} ({len(html):,} chars)")
        return html
    except requests.exceptions.RequestException as exc:
        logger.warning("Error fetching HTML for %r", link, exc_info=exc)
        return None
    except (KeyError, ValueError) as exc:
        logger.warning("Could not parse HTML response for %r", page_title, exc_info=exc)
        return None


def get_wikipedia_airport_page_wikitext(link: str, verbose: bool = False):
    """
    Fetch the raw wikitext source of a Wikipedia page.

    Parameters
    ----------
    link : str
        Wikipedia page URL.
    verbose : bool, optional
        Print progress messages.  Default: False.

    Returns
    -------
    str or None
        Wikitext string, or ``None`` on failure.
    """
    m = re.search(r'/wiki/([^#?]+)', link)
    if not m:
        warnings.warn(f"Invalid Wikipedia URL: {link!r}", UserWarning, stacklevel=2)
        return None
    page_title = urllib.parse.unquote(m.group(1)).replace('_', ' ')
    if verbose:
        print(f"Fetching wikitext for {page_title!r}...")

    params = {
        "action":   "query",
        "format":   "json",
        "prop":     "revisions",
        "titles":   page_title,
        "rvslots":  "*",
        "rvprop":   "content",
    }
    try:
        response = _SESSION.get(_API_URL, params=params, timeout=20)
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            revisions = page.get("revisions")
            if revisions:
                wikitext = revisions[0].get("slots", {}).get("main", {}).get("*")
                if verbose:
                    print(f"Fetched wikitext for {page_title!r} ({len(wikitext or ''):,} chars)")
                return wikitext
        warnings.warn(f"No wikitext revisions found for {page_title!r}.",
                      UserWarning, stacklevel=2)
        return None
    except requests.exceptions.RequestException as exc:
        logger.warning("Error fetching wikitext for %r", link, exc_info=exc)
        return None
    except (KeyError, ValueError) as exc:
        logger.warning("Could not parse wikitext response for %r", page_title, exc_info=exc)
        return None


# ---------------------------------------------------------------------------
# Shared fetch helper
# ---------------------------------------------------------------------------

def _fetch_html_if_needed(identifier, link, html_content, verbose):
    """Resolve link and html_content when either is absent."""
    if html_content is not None:
        return link, html_content
    if link is None:
        link = get_wikipedia_airport_page_link(identifier, verbose=verbose)
    if not link:
        warnings.warn(f"Could not resolve Wikipedia link for {identifier!r}.",
                      UserWarning, stacklevel=3)
        return None, None
    html_content = get_wikipedia_airport_page_html(link, verbose=verbose)
    if not html_content:
        warnings.warn(f"Could not fetch HTML for {link!r}.", UserWarning, stacklevel=3)
    return link, html_content


# ---------------------------------------------------------------------------
# Table-based destination/airline extraction
# ---------------------------------------------------------------------------

def extract_airlines_from_airport(
    identifier: str = "YWG",
    link=None,
    html_content=None,
    verbose: bool = False,
    soup=None,
) -> set:
    """
    Extract airline names from an airport's Wikipedia page.

    Parameters
    ----------
    identifier : str, optional
        IATA/ICAO code, Wikipedia URL, or name.  Default: ``"YWG"``.
    link : str or None, optional
        Wikipedia page URL (fetched automatically if absent).
    html_content : str or None, optional
        Pre-fetched HTML (fetched automatically if absent).
    verbose : bool, optional
        Print progress.  Default: False.
    soup : BeautifulSoup or None, optional
        Pre-parsed BeautifulSoup object.  Default: None.

    Returns
    -------
    set of str
        Airline names extracted from the *Airlines and destinations* table.
    """
    if soup is None:
        link, html_content = _fetch_html_if_needed(identifier, link, html_content, verbose)
        if not html_content:
            return set()
        soup = BeautifulSoup(html_content, 'html.parser')

    airlines = set()

    for header in soup.find_all(['h2', 'h3', 'h4']):
        header_text = header.get_text(strip=True).lower()
        if 'airlines' not in header_text or 'destination' not in header_text:
            continue
        table = header.find_next('table')
        if not table:
            break
        header_row = table.find('tr')
        if not header_row:
            break
        ths = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
        if verbose:
            print("Table headers:", ths)
        airline_idx = next((i for i, th in enumerate(ths) if 'airline' in th), None)
        if airline_idx is None:
            if verbose:
                print("No airline column found in:", ths)
            break
        for row in table.find_all('tr')[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) > airline_idx:
                # Use a_tag instead of link to avoid shadowing the outer link parameter
                for a_tag in cells[airline_idx].find_all('a'):
                    title = a_tag.get('title')
                    if title:
                        airlines.add(title)
        break

    if verbose:
        print(f"Extracted {len(airlines)} airlines.")
    return airlines


def extract_destinations_from_airport(
    identifier: str = "YWG",
    link=None,
    html_content=None,
    verbose: bool = False,
    soup=None,
) -> set:
    """
    Extract destination (name, Wikipedia URL) pairs from an airport page.

    Parameters
    ----------
    identifier : str, optional
        IATA/ICAO code, Wikipedia URL, or name.  Default: ``"YWG"``.
    link : str or None, optional
        Wikipedia page URL (fetched automatically if absent).
    html_content : str or None, optional
        Pre-fetched HTML (fetched automatically if absent).
    verbose : bool, optional
        Print progress.  Default: False.
    soup : BeautifulSoup or None, optional
        Pre-parsed BeautifulSoup object.  Default: None.

    Returns
    -------
    set of tuple[str, str]
        ``(destination_name, wikipedia_url)`` pairs.
    """
    if soup is None:
        link, html_content = _fetch_html_if_needed(identifier, link, html_content, verbose)
        if not html_content:
            return set()
        soup = BeautifulSoup(html_content, 'html.parser')

    destinations = set()

    for header in soup.find_all(['h2', 'h3', 'h4']):
        header_text = header.get_text(strip=True).lower()
        if 'airlines' not in header_text or 'destination' not in header_text:
            continue
        table = header.find_next('table')
        if not table:
            break
        header_row = table.find('tr')
        if not header_row:
            break
        ths      = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
        dest_idx = next((i for i, th in enumerate(ths) if 'destination' in th), None)
        if dest_idx is None:
            break
        for row in table.find_all('tr')[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) <= dest_idx:
                continue
            # Use a_tag to avoid shadowing the outer link parameter
            for a_tag in cells[dest_idx].find_all('a'):
                title = a_tag.get('title')
                href  = a_tag.get('href', '')
                if not title:
                    continue
                if href.startswith('/wiki/'):
                    full_url = f"https://en.wikipedia.org{href}"
                elif href.startswith('http'):
                    full_url = href
                else:
                    continue
                destinations.add((title, full_url))
        break

    if verbose:
        print(f"Extracted {len(destinations)} destinations.")
    return destinations


def extract_airlines_destinations_from_airport(
    identifier: str = "YWG",
    link=None,
    html_content=None,
    verbose: bool = False,
    soup=None,
) -> dict:
    """
    Extract an airline to destinations mapping from an airport's Wikipedia page.

    Falls back to :func:`fallback_nlp_extract_airlines_destinations` if no
    table-based data is found.

    Parameters
    ----------
    identifier : str, optional
        IATA/ICAO code, Wikipedia URL, or name.  Default: ``"YWG"``.
    link : str or None, optional
        Wikipedia page URL (fetched automatically if absent).
    html_content : str or None, optional
        Pre-fetched HTML (fetched automatically if absent).
    verbose : bool, optional
        Print progress.  Default: False.
    soup : BeautifulSoup or None, optional
        Pre-parsed BeautifulSoup object.  Default: None.

    Returns
    -------
    dict[str, set[str]]
        ``{airline_name: {destination_name, ...}, ...}``
    """
    if soup is None:
        link, html_content = _fetch_html_if_needed(identifier, link, html_content, verbose)
        if not html_content:
            return {}
        soup = BeautifulSoup(html_content, 'html.parser')

    airline_dest_map: dict = {}

    for header in soup.find_all(['h2', 'h3', 'h4']):
        header_text = header.get_text(strip=True).lower()
        if 'airlines' not in header_text or 'destination' not in header_text:
            continue
        table = header.find_next('table')
        if not table:
            break
        header_row = table.find('tr')
        if not header_row:
            break
        ths         = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
        airline_idx = next((i for i, th in enumerate(ths) if 'airline' in th), None)
        dest_idx    = next((i for i, th in enumerate(ths) if 'destination' in th), None)

        if airline_idx is None or dest_idx is None:
            # Column headers not found — scan each cell for keywords
            for row in table.find_all('tr')[1:]:
                cells         = row.find_all(['td', 'th'])
                airline_names: set = set()
                dest_names:    set = set()
                for cell in cells:
                    cell_text = cell.get_text(" ", strip=True)
                    if re.search(r'airline', cell_text, re.I):
                        airline_names.update(
                            a.get('title') for a in cell.find_all('a') if a.get('title')
                        )
                    if re.search(r'destination', cell_text, re.I):
                        dest_names.update(
                            a.get('title') for a in cell.find_all('a') if a.get('title')
                        )
                for airline in airline_names:
                    airline_dest_map.setdefault(airline, set()).update(dest_names)
        else:
            for row in table.find_all('tr')[1:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) <= max(airline_idx, dest_idx):
                    continue
                airline_names = [
                    a.get('title') for a in cells[airline_idx].find_all('a')
                    if a.get('title')
                ]
                dest_names = [
                    a.get('title') for a in cells[dest_idx].find_all('a')
                    if a.get('title')
                ]
                for airline in airline_names:
                    airline_dest_map.setdefault(airline, set()).update(dest_names)
        break

    if verbose:
        print(f"Extracted airline-destination map: {len(airline_dest_map)} airlines.")

    # NLP fallback
    if not airline_dest_map:
        if verbose:
            print("No table data found — trying NLP fallback...")
        for org, gpe in fallback_nlp_extract_airlines_destinations(
            html_content, verbose=verbose, soup=soup
        ):
            airline_dest_map.setdefault(org, set()).add(gpe)

    return airline_dest_map


# ---------------------------------------------------------------------------
# Full airport information extraction
# ---------------------------------------------------------------------------

def _feet_to_metres(value_str):
    """Convert a feet elevation string to a metres string, or return it as-is."""
    if not value_str:
        return None
    try:
        feet   = float(re.sub(r"[^\d.]", "", value_str))
        return str(round(feet * 0.3048, 2))
    except (ValueError, TypeError):
        return value_str


def extract_airport_information(
    identifier: str = "YWG",
    link=None,
    verbose: bool = False,
) -> dict:
    """
    Extract all available metadata for an airport from its Wikipedia page.

    Parameters
    ----------
    identifier : str, optional
        IATA/ICAO code, Wikipedia URL, or name.  Default: ``"YWG"``.
    link : str or None, optional
        Wikipedia page URL (fetched automatically if absent).
    verbose : bool, optional
        Print progress.  Default: False.

    Returns
    -------
    dict
        Keys: ``iata``, ``icao``, ``city-served``, ``location``, ``lat``,
        ``lon``, ``altitude``, ``region``, ``country_alpha3``,
        ``country_name``, ``subdivision_code``, ``wikipedia_url``,
        ``airlines``, ``destinations``, ``airlines_destinations``.
    """
    _EMPTY: dict = {
        'iata':                  None,
        'icao':                  None,
        'city-served':           None,
        'location':              None,
        'lat':                   None,
        'lon':                   None,
        'altitude':              None,
        'region':                None,
        'country_alpha3':        None,
        'country_name':          None,
        'subdivision_code':      None,
        'wikipedia_url':         None,
        'airlines':              [],
        'destinations':          [],
        'airlines_destinations': [],
    }

    if link is None:
        link = get_wikipedia_airport_page_link(identifier, verbose=verbose)
    if not link:
        return _EMPTY.copy()

    html_content = get_wikipedia_airport_page_html(link, verbose=verbose)
    if not html_content:
        return {**_EMPTY, 'wikipedia_url': link}

    wikitext = get_wikipedia_airport_page_wikitext(link, verbose=verbose)
    if not wikitext:
        return {**_EMPTY, 'wikipedia_url': link}

    infobox = parse_infobox_from_wikitext(wikitext, verbose=verbose)
    if not infobox:
        warnings.warn(f"Could not parse infobox for {link!r}.", UserWarning, stacklevel=2)
        return {**_EMPTY, 'wikipedia_url': link}

    info: dict = {
        'iata':                  infobox.get('IATA'),
        'icao':                  infobox.get('ICAO'),
        'city-served':           infobox.get('city-served'),
        'location':              infobox.get('location'),
        'lat':                   infobox.get('lat'),
        'lon':                   infobox.get('lon'),
        'altitude':              (
            infobox.get('elevation-m')
            or _feet_to_metres(infobox.get('elevation-f'))
        ),
        'region':                infobox.get('region'),
        'country_alpha3':        infobox.get('country_alpha3'),
        'country_name':          infobox.get('country_name'),
        'subdivision_code':      infobox.get('subdivision_code'),
        'wikipedia_url':         link,
        'airlines':              set(),
        'destinations':          set(),
        'airlines_destinations': set(),
    }

    soup = BeautifulSoup(html_content, 'html.parser') if html_content else None

    info['airlines']     = extract_airlines_from_airport(
        link=link, html_content=html_content, verbose=verbose, soup=soup)
    info['destinations'] = extract_destinations_from_airport(
        link=link, html_content=html_content, verbose=verbose, soup=soup)
    ad_map               = extract_airlines_destinations_from_airport(
        link=link, html_content=html_content, verbose=verbose, soup=soup)

    # Normalise to JSON-serialisable types
    if isinstance(info['airlines'], set):
        info['airlines'] = sorted(info['airlines'])
    if isinstance(info['destinations'], set):
        info['destinations'] = sorted(info['destinations'])
    info['airlines_destinations'] = {k: sorted(v) for k, v in ad_map.items()}

    return info


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_airport_info(
    airport_info: dict,
    level: int = 0,
    verbose: bool = False,
    save_progress: bool = True,
) -> str:
    """
    Persist an airport info dictionary to ``TEMP_RESULTS_DIR/<CODE>.<level>.json``.

    Parameters
    ----------
    airport_info : dict
        Dict as returned by :func:`extract_airport_information`.
    level : int, optional
        BFS distance level from the seed airport.  Default: 0.
    verbose : bool, optional
        Print the saved path.  Default: False.
    save_progress : bool, optional
        Append to ``processed_locations.csv``.  Default: True.

    Returns
    -------
    str
        The IATA code (or ``wiki_<title>`` / ``"unknown"``) used as the
        filename prefix.
    """
    iata_code = airport_info.get('iata')
    if not iata_code:
        wiki_url  = airport_info.get('wikipedia_url', '')
        m         = re.search(r'/wiki/([^/#?]+)', wiki_url)
        iata_code = f"wiki_{m.group(1)}" if m else "unknown"

    output_dir  = TEMP_RESULTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{iata_code}.{level}.json")

    # Sort destinations on a copy so we do not mutate the caller's dict.
    info_to_save = dict(airport_info)
    if isinstance(info_to_save.get("destinations"), list):
        info_to_save["destinations"] = sorted(
            info_to_save["destinations"],
            key=lambda x: x[0] if isinstance(x, (list, tuple)) and x else "",
        )

    # Atomic write — crash never leaves a truncated JSON file.
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(info_to_save, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, output_path)

    if save_progress:
        _record_progress(
            output_dir,
            airport_info.get('iata', ''),
            airport_info.get('wikipedia_url', ''),
        )

    if verbose:
        print(f"Saved {iata_code} -> {output_path}")

    return iata_code


def _record_progress(output_dir: str, iata: str, url: str) -> None:
    """Append an (iata, url) row to processed_locations.csv if not already present."""
    csv_path   = os.path.join(output_dir, "processed_locations.csv")
    fieldnames = ["iata", "url"]

    existing: set = set()
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                existing.add((row.get("iata", ""), row.get("url", "")))

    if (iata, url) in existing:
        return

    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        if write_header:
            writer.writeheader()
        writer.writerow({"iata": iata, "url": url})


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def parse_lat_lon_from_string(coord_string: str):
    """
    Parse a coordinate string into decimal-degree latitude and longitude.

    Parameters
    ----------
    coord_string : str
        Any format accepted by geopy (DMS, decimal, etc.).

    Returns
    -------
    tuple[str, str]
        ``(latitude, longitude)`` as 6-decimal-place strings,
        or ``("", "")`` on parse failure.
    """
    try:
        pt = Point(coord_string)
        return f"{pt.latitude:.6f}", f"{pt.longitude:.6f}"
    except Exception as exc:
        warnings.warn(
            f"Could not parse coordinate string {coord_string!r}: {exc}",
            UserWarning, stacklevel=2,
        )
        return "", ""


# ---------------------------------------------------------------------------
# NLP fallback
# ---------------------------------------------------------------------------

def fallback_nlp_extract_airlines_destinations(
    html_content: str,
    verbose: bool = False,
    soup=None,
) -> set:
    """
    Use spaCy NER to extract (airline, destination) pairs as a last resort.

    Parameters
    ----------
    html_content : str
        Parsed HTML of the airport Wikipedia page.
    verbose : bool, optional
        Print match counts.  Default: False.
    soup : BeautifulSoup or None, optional
        Pre-parsed BeautifulSoup object.  Default: None.

    Returns
    -------
    set of tuple[str, str]
        ``(ORG entity, GPE entity)`` pairs.

    Notes
    -----
    Requires ``en_core_web_sm``.  Install with::

        python -m spacy download en_core_web_sm

    Returns an empty set if the model is not available.
    """
    if _NLP is None:
        warnings.warn(
            "spaCy model 'en_core_web_sm' is not installed. "
            "Run: python -m spacy download en_core_web_sm",
            UserWarning, stacklevel=2,
        )
        return set()

    if soup is None:
        soup = BeautifulSoup(html_content, 'html.parser')

    section = soup.find(
        lambda tag: tag.name in ['h2', 'h3', 'h4']
        and 'airline' in tag.get_text(strip=True).lower()
    )

    if section:
        parts = [section.get_text(" ", strip=True)]
        table = section.find_next('table')
        if table:
            parts.append(table.get_text(" ", strip=True))
        section_text = "\n".join(parts)
    else:
        section_text = soup.get_text(" ", strip=True)

    doc     = _NLP(section_text)
    orgs    = {ent.text for ent in doc.ents if ent.label_ == "ORG"}
    gpes    = {ent.text for ent in doc.ents if ent.label_ == "GPE"}
    results = {(org, gpe) for org in orgs for gpe in gpes}

    if verbose:
        print(f"spaCy fallback found {len(results)} (airline, destination) pairs.")
    return results


# ---------------------------------------------------------------------------
# Infobox parsing
# ---------------------------------------------------------------------------

def clean_infobox_value(value: str) -> str:
    """
    Normalise a wikitext infobox value string.

    * ``{{nowrap|...}}``          -> inner content
    * ``{{Unbulleted list|...}}`` -> comma-separated items
    * ``{{URL|...}}``             -> bare URL

    Parameters
    ----------
    value : str
        Raw wikitext value.

    Returns
    -------
    str
        Cleaned string with wikilinks preserved as ``[[X]]``.
    """
    wikicode = mwparserfromhell.parse(value)
    for template in wikicode.filter_templates(recursive=True):
        name = template.name.strip().lower()
        if name == "nowrap" and template.params:
            value    = str(template.params[0].value)
            wikicode = mwparserfromhell.parse(value)
        elif name == "unbulleted list":
            value    = ", ".join(str(p.value).strip() for p in template.params)
            wikicode = mwparserfromhell.parse(value)
        elif name == "url" and template.params:
            value    = str(template.params[0].value)
            wikicode = mwparserfromhell.parse(value)
    return str(wikicode).strip()


def parse_infobox_from_wikitext(wikitext: str, verbose: bool = False) -> dict:
    """
    Parse the ``{{Infobox airport}}`` template from wikitext into a dict.

    Parameters
    ----------
    wikitext : str
        Full wikitext source of the airport Wikipedia page.
    verbose : bool, optional
        Print parsed key list.  Default: False.

    Returns
    -------
    dict
        ``{field_name: cleaned_value, ...}`` plus derived ``lat``, ``lon``,
        ``region``, and ISO 3166-2 country fields when available.
        Returns ``{}`` if no infobox is found.
    """
    if not wikitext:
        return {}

    m = re.search(r'\{\{[Ii]nfobox airport.*?(\n|\|)', wikitext)
    if not m:
        if verbose:
            print("No Infobox airport found in wikitext.")
        return {}

    # Extract full template text by matching brace pairs.
    start       = m.start()
    brace_depth = 1   # already inside the opening {{
    end         = start + 2
    while end < len(wikitext):
        pair = wikitext[end:end + 2]
        if pair == '{{':
            brace_depth += 1
            end += 2
        elif pair == '}}':
            brace_depth -= 1
            end += 2
            if brace_depth == 0:
                break
        else:
            end += 1
    infobox_text = wikitext[start:end]

    _IGNORED     = re.compile(r'image|footnote|owner|operator|mapframe|pushpin', re.I)
    infobox_data: dict = {}
    region: str | None = None

    for line in infobox_text.split('\n'):
        if not line.startswith('|'):
            continue
        parts = line[1:].split('=', 1)
        if len(parts) != 2:
            continue
        key, value = parts[0].strip(), parts[1].strip()
        if _IGNORED.search(key):
            continue
        if value.replace(" ", "") == "{{ubl|class=nowrap":
            continue

        value = clean_infobox_value(value)

        if key.lower() == "coordinates":
            value  = re.sub(r'\| *display *= *inline,title *', '', value, flags=re.I).strip()
            coord_m = re.search(
                r'\{\{[Cc]oord\|(\d+)\|(\d+)\|(\d+)\|([NS])\|(\d+)\|(\d+)\|(\d+)\|([EW])'
                r'(?:\|region:([A-Za-z0-9\-]+))?',
                value,
            )
            if coord_m:
                lat = (int(coord_m.group(1))
                       + int(coord_m.group(2)) / 60
                       + int(coord_m.group(3)) / 3600)
                if coord_m.group(4).upper() == 'S':
                    lat = -lat
                lon = (int(coord_m.group(5))
                       + int(coord_m.group(6)) / 60
                       + int(coord_m.group(7)) / 3600)
                if coord_m.group(8).upper() == 'W':
                    lon = -lon
                infobox_data['lat'] = f"{lat:.6f}"
                infobox_data['lon'] = f"{lon:.6f}"
                region = coord_m.group(9)
                if region:
                    infobox_data['region'] = region

        infobox_data[key] = value

    if region:
        iso = parse_iso3166_2(region)
        if iso:
            infobox_data.update(iso)

    infobox_data = {
        k: v for k, v in infobox_data.items()
        if v and not (str(v).strip().startswith("<!--") and str(v).strip().endswith("-->"))
    }

    if verbose:
        print(f"Parsed infobox keys: {list(infobox_data.keys())}")
    return infobox_data


def extract_airlines_destinations_from_wikitext(wikitext: str) -> dict:
    """
    Extract airline to destinations data from ``{{Airport-dest-list}}`` templates.

    Only destinations expressed as Wikipedia wikilinks are included.

    Parameters
    ----------
    wikitext : str
        Full wikitext of the airport Wikipedia page.

    Returns
    -------
    dict[str, list[dict]]
        ``{airline_name: [{"name": str, "wikipedia_url": str}, ...], ...}``
    """
    # Pre-clean: strip refs, unwrap {{nowrap|...}}, normalise piped wikilinks
    clean = re.sub(r'<ref[^/].*?</ref>', '', wikitext, flags=re.DOTALL)
    clean = re.sub(r'\{\{nowrap\|([^{}]+?)\}\}', r'\1', clean, flags=re.I)
    clean = re.sub(r'\[\[([^\]|]+)\|[^\]]+\]\]', r'[[\1]]', clean)

    wikicode      = mwparserfromhell.parse(clean)
    airlines_dest: dict = {}

    for template in wikicode.filter_templates():
        if not template.name.lower().strip().startswith("airport-dest-list"):
            continue

        for param in template.params:
            parts = str(param.value).split('|', 1)
            if len(parts) != 2:
                continue
            airline_raw, dests_raw = parts

            # Resolve airline name
            airline_wikicode = mwparserfromhell.parse(
                re.sub(r'<ref.*?</ref>', '', airline_raw, flags=re.DOTALL).strip()
            )
            wikilinks = airline_wikicode.filter_wikilinks()
            if wikilinks:
                wl      = wikilinks[0]
                airline = (
                    wl.text.strip_code().strip()
                    if wl.text
                    else wl.title.strip_code().strip()
                )
            else:
                airline = airline_wikicode.strip_code().strip()

            if not airline:
                continue

            # Resolve destinations — only accept wikilinks
            dest_wikicode = mwparserfromhell.parse(dests_raw)
            dest_objs = [
                {
                    "name": (
                        wl.text.strip_code().strip()
                        if wl.text
                        else wl.title.strip_code().strip()
                    ),
                    "wikipedia_url": (
                        "https://en.wikipedia.org/wiki/"
                        + wl.title.strip_code().strip().replace(' ', '_')
                    ),
                }
                for wl in dest_wikicode.filter_wikilinks()
                if wl.title.strip_code().strip()
            ]

            if dest_objs:
                airlines_dest[airline] = dest_objs

    return airlines_dest


# ---------------------------------------------------------------------------
# Fallback HTML info extraction
# ---------------------------------------------------------------------------

def fallback_extract_airport_information(html_content: str) -> dict:
    """
    Extract basic airport info from HTML when the infobox cannot be parsed.

    Parameters
    ----------
    html_content : str
        Parsed HTML of the airport Wikipedia page.

    Returns
    -------
    dict
        Keys: ``iata``, ``icao``, ``serves``, ``location``,
        ``coordinates``, ``wikipedia_url``.  Values are strings or ``None``.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(" ", strip=True)
    info: dict = {
        'iata':          None,
        'icao':          None,
        'serves':        None,
        'location':      None,
        'coordinates':   None,
        'wikipedia_url': None,
    }

    m = re.search(r'\bIATA[:\s\-]*([A-Z0-9]{3})\b', text)
    if m:
        info['iata'] = m.group(1).upper()

    m = re.search(r'\bICAO[:\s\-]*([A-Z0-9]{4})\b', text)
    if m:
        info['icao'] = m.group(1).upper()

    title_tag = soup.find(['h1', 'h2'])
    if title_tag:
        info['serves'] = title_tag.get_text(" ", strip=True)

    decimals = re.findall(r'-?\d+\.\d+', text)
    if len(decimals) >= 2:
        info['coordinates'] = f"{decimals[0]}, {decimals[1]}"
    elif decimals:
        info['coordinates'] = decimals[0]

    m = re.search(r'Location[:\s\-]*([^\n]+)', text)
    if m:
        info['location'] = m.group(1).strip()

    return info


# ---------------------------------------------------------------------------
# ISO 3166-2 helper
# ---------------------------------------------------------------------------

def parse_iso3166_2(region_code: str):
    """
    Resolve an ISO 3166-2 region code to country and subdivision details.

    Parameters
    ----------
    region_code : str
        Code in the form ``"CC-SUB"`` (e.g. ``"CA-MB"``).

    Returns
    -------
    dict or None
        ``{'country_alpha3': str, 'country_name': str, 'subdivision_code': str}``
        or ``None`` if *region_code* is invalid or the country is not found.
    """
    try:
        if '-' not in region_code:
            return None
        country_code, subdivision = region_code.split('-', 1)
        country = pycountry.countries.get(alpha_2=country_code.upper())
        if not country:
            return None
        return {
            'country_alpha3':   country.alpha_3,
            'country_name':     country.name,
            'subdivision_code': subdivision.upper(),
        }
    except Exception as exc:
        warnings.warn(
            f"Could not parse ISO 3166-2 code {region_code!r}: {exc}",
            UserWarning, stacklevel=2,
        )
        return None
