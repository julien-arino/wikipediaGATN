"""
Airport-level Wikipedia scraping and data extraction functions.

Functions in this module interact with the Wikipedia API to fetch and parse
airport pages, and supplement the extracted data using the authoritative
OurAirports database.

Core Pipeline Functions:

1. :func:`fetch_wikipedia_airport_link`         resolve an identifier to a URL
2. :func:`fetch_wikipedia_airport_html`         fetch parsed HTML
3. :func:`fetch_wikipedia_airport_wikitext`     fetch raw wikitext
4. :func:`fetch_wikipedia_airlines`             set of airline names
5. :func:`fetch_wikipedia_destinations`         set of (name, URL) tuples
6. :func:`fetch_wikipedia_airlines_destinations` airline → destinations map
7. :func:`fetch_wikipedia_airport_info`         all metadata in one dict
8. :func:`save_airport_info`                    persist dict to JSON + progress CSV

OurAirports Integration & Validation:

* :func:`infer_missing_geographic_data`         supplement missing data via OurAirports
* :func:`compare_airports_with_ourairports`     audit extracted data against OurAirports
* :func:`find_active_missing_airports`          identify unmapped airports in OurAirports
* :func:`build_url_to_codes_map`                map Wikipedia URLs to IATA codes

Helper / Fallback functions:

* :func:`format_airport_json`
* :func:`parse_infobox_from_wikitext`
* :func:`clean_infobox_value`
* :func:`parse_lat_lon_from_string`
* :func:`parse_iso3166_2`
* :func:`format_destinations_list`
* :func:`fallback_fetch_wikipedia_airport_info`
* :func:`parse_fallback_nlp_airlines_destinations`
* :func:`parse_wikitext_airlines_destinations`
"""

import csv
from datetime import datetime, timezone
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
    "fetch_wikipedia_airport_link",
    "fetch_wikipedia_airport_html",
    "fetch_wikipedia_airport_wikitext",
    "fetch_wikipedia_airlines",
    "fetch_wikipedia_destinations",
    "fetch_wikipedia_airlines_destinations",
    "fetch_wikipedia_airport_info",
    "save_airport_info",
    "parse_infobox_from_wikitext",
    "clean_infobox_value",
    "parse_lat_lon_from_string",
    "parse_iso3166_2",
    "fallback_fetch_wikipedia_airport_info",
    "parse_fallback_nlp_airlines_destinations",
    "parse_wikitext_airlines_destinations",
    "format_airport_json",
]

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_API_URL = "https://en.wikipedia.org/w/api.php"

# Wikipedia's bot policy requires a descriptive User-Agent with a contact
# address so they can reach out if the bot misbehaves.
_HEADERS = {
    "User-Agent": (
        "wikipediaGATN/1.0 (https://github.com/julien-arino; julien.arino@umanitoba.ca) "
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
# Formatting helper
# ---------------------------------------------------------------------------

def format_airport_json(data: dict) -> dict:
    """
    Enforce a strict ordering of JSON keys for airport data output.
    """
    key_order = [
        "iata", "icao", "gps", "city-served", "city-served-wikipedia", "location",
        "lat", "lon", "altitude", "continent",
        "country_alpha3", "country_name",
        "admin1_code", "admin1_name", "admin2_name",
        "wikipedia_url",
        "outdegree", "number_airlines",
        "airlines", "destinations", "airlines_destinations",
        "outdegree_cargo", "number_airlines_cargo",
        "airlines_cargo", "destinations_cargo", "airlines_destinations_cargo",
        "date-time-parse", "date-time-wikidata"
    ]
    
    formatted = {}
    
    # 1. Insert known keys in the specified order
    for k in key_order:
        if k in data:
            formatted[k] = data[k]
            
    # 2. Append any extra keys that might exist (to prevent data loss)
    for k, v in data.items():
        if k not in formatted:
            formatted[k] = v
            
    return formatted
# ---------------------------------------------------------------------------
# Wikipedia page lookup
# ---------------------------------------------------------------------------

def fetch_wikipedia_airport_link(identifier: str, verbose: bool = False):
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
        return f"https://en.wikipedia.org/wiki/{search_term.replace(' ', '_')}"
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

def fetch_wikipedia_airport_html(link: str, verbose: bool = False):
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
        "redirects":     1,
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


def fetch_wikipedia_airport_wikitext(link: str, verbose: bool = False):
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
        "rvprop":   "content|timestamp",
        "redirects": 1,
    }
    try:
        response = _SESSION.get(_API_URL, params=params, timeout=20)
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            revisions = page.get("revisions")
            if revisions:
                wikitext = revisions[0].get("slots", {}).get("main", {}).get("*")
                timestamp = revisions[0].get("timestamp")
                if verbose:
                    print(f"Fetched wikitext for {page_title!r} ({len(wikitext or ''):,} chars, edit: {timestamp})")
                return wikitext, timestamp
        warnings.warn(f"No wikitext revisions found for {page_title!r}.",
                      UserWarning, stacklevel=2)
        return None, None
    except requests.exceptions.RequestException as exc:
        logger.warning("Error fetching wikitext for %r", link, exc_info=exc)
        return None, None
    except (KeyError, ValueError) as exc:
        logger.warning("Could not parse wikitext response for %r", page_title, exc_info=exc)
        return None, None


# ---------------------------------------------------------------------------
# Shared fetch helper
# ---------------------------------------------------------------------------

def _fetch_html_if_needed(identifier, link, html_content, verbose):
    """Resolve link and html_content when either is absent."""
    if html_content is not None:
        return link, html_content
    if link is None:
        link = fetch_wikipedia_airport_link(identifier, verbose=verbose)
    if not link:
        warnings.warn(f"Could not resolve Wikipedia link for {identifier!r}.",
                      UserWarning, stacklevel=3)
        return None, None
    html_content = fetch_wikipedia_airport_html(link, verbose=verbose)
    if not html_content:
        warnings.warn(f"Could not fetch HTML for {link!r}.", UserWarning, stacklevel=3)
    return link, html_content


# ---------------------------------------------------------------------------
# Table-based destination/airline extraction
# ---------------------------------------------------------------------------

def fetch_wikipedia_airlines(
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
        table = None
        for tbl in header.find_all_next('table'):
            classes = tbl.get('class', [])
            if any('ambox' in c or 'box' in c for c in classes):
                continue
            table = tbl
            break
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


def fetch_wikipedia_destinations(
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
        table = None
        for tbl in header.find_all_next('table'):
            classes = tbl.get('class', [])
            if any('ambox' in c or 'box' in c for c in classes):
                continue
            table = tbl
            break
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
                    if href.split(':', 1)[0] in ('/wiki/Wikipedia', '/wiki/Help', '/wiki/File', '/wiki/Category', '/wiki/Template', '/wiki/Portal'):
                        continue
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


def fetch_wikipedia_airlines_destinations(
    identifier: str = "YWG",
    link=None,
    html_content=None,
    verbose: bool = False,
    soup=None,
) -> dict:
    """
    Extract an airline to destinations mapping from an airport's Wikipedia page.

    Falls back to :func:`parse_fallback_nlp_airlines_destinations` if no
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
    dict
        ``{"passenger": {airline_name: {destination_name, ...}, ...}, "cargo": {...}}``
    """
    if soup is None:
        link, html_content = _fetch_html_if_needed(identifier, link, html_content, verbose)
        if not html_content:
            return {}
        soup = BeautifulSoup(html_content, 'html.parser')

    result: dict = {"passenger": {}, "cargo": {}}

    for header in soup.find_all(['h2', 'h3', 'h4']):
        header_text = header.get_text(strip=True).lower()
        if 'airlines' not in header_text or 'destination' not in header_text:
            continue
            
        header_level = header.name
        for tbl in header.find_all_next('table'):
            classes = tbl.get('class', [])
            if any('ambox' in c or 'box' in c for c in classes):
                continue
                
            # Check if we left the section
            prev_level_header = tbl.find_previous(header_level)
            if prev_level_header and prev_level_header.get_text(strip=True) != header.get_text(strip=True):
                break
                
            prev_header = tbl.find_previous(['h2', 'h3', 'h4'])
            is_cargo = prev_header and 'cargo' in prev_header.get_text(strip=True).lower()
            target_dict = result["cargo"] if is_cargo else result["passenger"]

            header_row = tbl.find('tr')
            if not header_row:
                continue
            ths         = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
            airline_idx = next((i for i, th in enumerate(ths) if 'airline' in th), None)
            dest_idx    = next((i for i, th in enumerate(ths) if 'destination' in th), None)

            if airline_idx is None or dest_idx is None:
                # Column headers not found — scan each cell for keywords
                for row in tbl.find_all('tr')[1:]:
                    cells         = row.find_all(['td', 'th'])
                    airline_names: set = set()
                    dest_names:    set = set()
                    for cell in cells:
                        cell_text = cell.get_text(" ", strip=True)
                        if re.search(r'airline', cell_text, re.I):
                            for a in cell.find_all('a'):
                                if a.get('title') and not a.get('href', '').startswith(('/wiki/Wikipedia:', '/wiki/Help:', '/wiki/File:', '/wiki/Category:', '/wiki/Template:', '/wiki/Portal:')):
                                    airline_names.add(a.get('title'))
                        if re.search(r'destination', cell_text, re.I):
                            for a in cell.find_all('a'):
                                if a.get('title') and not a.get('href', '').startswith(('/wiki/Wikipedia:', '/wiki/Help:', '/wiki/File:', '/wiki/Category:', '/wiki/Template:', '/wiki/Portal:')):
                                    dest_names.add(a.get('title'))
                    for airline in airline_names:
                        target_dict.setdefault(airline, set()).update(dest_names)
            else:
                for row in tbl.find_all('tr')[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) <= max(airline_idx, dest_idx):
                        continue
                    airline_names = [
                        a.get('title') for a in cells[airline_idx].find_all('a')
                        if a.get('title') and not a.get('href', '').startswith(('/wiki/Wikipedia:', '/wiki/Help:', '/wiki/File:', '/wiki/Category:', '/wiki/Template:', '/wiki/Portal:'))
                    ]
                    dest_names = [
                        a.get('title') for a in cells[dest_idx].find_all('a')
                        if a.get('title') and not a.get('href', '').startswith(('/wiki/Wikipedia:', '/wiki/Help:', '/wiki/File:', '/wiki/Category:', '/wiki/Template:', '/wiki/Portal:'))
                    ]
                    for airline in airline_names:
                        target_dict.setdefault(airline, set()).update(dest_names)
        break

    if verbose:
        total_airlines = len(result['passenger']) + len(result['cargo'])
        print(f"Extracted airline-destination map: {total_airlines} airlines.")

    # NLP fallback
    if not result["passenger"] and not result["cargo"]:
        if verbose:
            print("No table data found — trying NLP fallback...")
        for org, gpe in parse_fallback_nlp_airlines_destinations(
            html_content, verbose=verbose, soup=soup
        ):
            result["passenger"].setdefault(org, set()).add(gpe)

    return result


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


def fetch_wikipedia_airport_info(
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
        'country_name':          None,
        'admin1_code':           None,
        'admin1_name':           None,
        'admin2_name':           None,
        'wikipedia_url':         None,
        'airlines':              [],
        'destinations':          [],
        'airlines_destinations': [],
    }

    if link is None:
        link = fetch_wikipedia_airport_link(identifier, verbose=verbose)
    if not link:
        return _EMPTY.copy()

    # Capture the exact moment we initiate the extraction (standardized to match Wikipedia's Z format)
    dt_parse = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    html_content = fetch_wikipedia_airport_html(link, verbose=verbose)
    if not html_content:
        return {**_EMPTY, 'wikipedia_url': link, 'date-time-parse': dt_parse}

    wikitext, dt_wikidata = fetch_wikipedia_airport_wikitext(link, verbose=verbose)
    if not wikitext:
        return {**_EMPTY, 'wikipedia_url': link, 'date-time-parse': dt_parse}

    infobox = parse_infobox_from_wikitext(wikitext, verbose=verbose)
    if not infobox:
        warnings.warn(f"Could not parse infobox for {link!r}.", UserWarning, stacklevel=2)
        return {**_EMPTY, 'wikipedia_url': link, 'date-time-parse': dt_parse, 'date-time-wikidata': dt_wikidata}

    iata_raw = infobox.get('IATA')
    iata_clean = re.search(r'[A-Za-z]{3}', str(iata_raw)).group(0).upper() if iata_raw and re.search(r'[A-Za-z]{3}', str(iata_raw)) else None
    
    icao_raw = infobox.get('ICAO')
    icao_clean = re.search(r'[A-Za-z]{4}', str(icao_raw)).group(0).upper() if icao_raw and re.search(r'[A-Za-z]{4}', str(icao_raw)) else None

    info: dict = {
        'iata':                  iata_clean,
        'icao':                  icao_clean,
        'city-served':           infobox.get('city-served'),
        'location':              infobox.get('location'),
        'lat':                   infobox.get('lat'),
        'lon':                   infobox.get('lon'),
        'altitude':              (
            infobox.get('elevation-m')
            or _feet_to_metres(infobox.get('elevation-f'))
        ),
        'country_alpha3':        infobox.get('country_alpha3'),
        'country_name':          infobox.get('country_name'),
        'admin1_code':           infobox.get('admin1_code'),
        'admin1_name':           infobox.get('region') or infobox.get('admin1_name'),
        'admin2_name':           None,
        'wikipedia_url':         link,
        'airlines':              set(),
        'destinations':          set(),
        'airlines_destinations': set(),
        'date-time-parse':       dt_parse,
        'date-time-wikidata':    dt_wikidata,
    }

    ad_map_wikitext = parse_wikitext_airlines_destinations(wikitext)
    
    # Intelligent HTML Fallback
    # If wikitext found no passenger airlines but did find cargo, it likely missed a wikitable
    html_content = None
    if not ad_map_wikitext['passenger'] and ad_map_wikitext['cargo']:
        html_content = fetch_wikipedia_airport_html(link=link, verbose=verbose)
        ad_map_html = fetch_wikipedia_airlines_destinations(
            link=link, html_content=html_content, verbose=verbose, soup=None)
        if ad_map_html['passenger']:
            ad_map_wikitext['passenger'] = ad_map_html['passenger']

    if not ad_map_wikitext['passenger'] and not ad_map_wikitext['cargo']:
        if not html_content:
            html_content = fetch_wikipedia_airport_html(link=link, verbose=verbose)
        soup = BeautifulSoup(html_content, 'html.parser') if html_content else None
        ad_map = fetch_wikipedia_airlines_destinations(
            link=link, html_content=html_content, verbose=verbose, soup=soup)
    else:
        ad_map = ad_map_wikitext

    # Passenger data
    info['airlines'] = sorted(ad_map['passenger'].keys())
    info['destinations'] = sorted({
        (d["name"], d["wikipedia_url"]) if isinstance(d, dict) else d
        for dests in ad_map['passenger'].values()
        for d in dests
    })
    info['airlines_destinations'] = {
        airline: sorted({d["name"] if isinstance(d, dict) else d for d in dests})
        for airline, dests in ad_map['passenger'].items()
    }
    
    # Cargo data
    info['airlines_cargo'] = sorted(ad_map['cargo'].keys())
    info['destinations_cargo'] = sorted({
        (d["name"], d["wikipedia_url"]) if isinstance(d, dict) else d
        for dests in ad_map['cargo'].values()
        for d in dests
    })
    info['airlines_destinations_cargo'] = {
        airline: sorted({d["name"] if isinstance(d, dict) else d for d in dests})
        for airline, dests in ad_map['cargo'].items()
    }

    return info


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_airport_info(
    airport_info: dict,
    level: int = 0,
    verbose: bool = False,
    save_progress: bool = True,
    iata_from: str = "",
) -> str:
    """
    Persist an airport info dictionary to ``TEMP_RESULTS_DIR/<CODE>.<level>.json``.

    Parameters
    ----------
    airport_info : dict
        Dict as returned by :func:`fetch_wikipedia_airport_info`.
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
        iata_code = airport_info.get('icao')
    if not iata_code:
        iata_code = airport_info.get('gps')
    if not iata_code:
        wiki_url  = airport_info.get('wikipedia_url', '')
        m         = re.search(r'/wiki/([^/#?]+)', wiki_url)
        iata_code = f"wiki_{m.group(1)}" if m else "unknown"

    output_dir  = os.path.join(TEMP_RESULTS_DIR, "airports_rooted_sweep")
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
            iata_code,
            airport_info.get('wikipedia_url', ''),
            iata_from,
        )

    if verbose:
        print(f"Saved {iata_code} -> {output_path}")

    return iata_code


def _record_progress(output_dir: str, iata_icao_gps: str, url: str, iata_icao_gps_from: str = "") -> None:
    """Append an (iata_icao_gps, url, iata_icao_gps_from) row to processed_locations.csv if not already present."""
    csv_path   = os.path.join(TEMP_RESULTS_DIR, "processed_locations.csv")
    fieldnames = ["iata_icao_gps", "url", "iata_icao_gps_from"]

    existing: set = set()
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                col1 = row.get("iata_icao_gps", row.get("iata", ""))
                existing.add((col1, row.get("url", "")))

    if (iata_icao_gps, url) in existing:
        return

    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        if write_header:
            writer.writeheader()
        writer.writerow({"iata_icao_gps": iata_icao_gps, "url": url, "iata_icao_gps_from": iata_icao_gps_from})


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

def parse_fallback_nlp_airlines_destinations(
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
    value = re.sub(r'<!--.*?-->', '', value, flags=re.DOTALL)
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

    m = re.search(r'\{\{[Ii]nfobox[ \t]+(?:airport|military).*?(\n|\|)', wikitext, flags=re.IGNORECASE)
    if not m:
        if verbose:
            print("No suitable Infobox (airport/military) found in wikitext.")
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

    # Strip HTML comments that may obscure parameter definitions on the same line
    infobox_text = re.sub(r'<!--.*?-->', '', infobox_text, flags=re.DOTALL)
    # Strip citations (which can span multiple lines) before line-by-line parsing
    infobox_text = re.sub(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>', '', infobox_text, flags=re.DOTALL | re.IGNORECASE)

    for line in infobox_text.split('\n'):
        line_stripped = line.strip()
        if not line_stripped.startswith('|'):
            continue
        parts = line_stripped[1:].split('=', 1)
        if len(parts) != 2:
            continue
        key, value = parts[0].strip(), parts[1].strip()
        if _IGNORED.search(key):
            continue
        if value.replace(" ", "") == "{{ubl|class=nowrap":
            continue

        value = clean_infobox_value(value)

        if key.lower() == "coordinates":
            coord_m = re.search(r'\{\{[Cc]oord\|(.*?)\}\}', value)
            if coord_m:
                inner = coord_m.group(1)
                
                region_m = re.search(r'region:([A-Za-z0-9\-]+)', inner)
                if region_m:
                    region = region_m.group(1)
                    
                args = [arg.strip() for arg in inner.split('|') 
                        if '=' not in arg and 'region:' not in arg.lower() and arg.strip()]
                
                try:
                    lat, lon = None, None
                    if len(args) >= 8:
                        lat = (float(args[0]) + float(args[1])/60 + float(args[2])/3600) * (1 if args[3].upper() == "N" else -1)
                        lon = (float(args[4]) + float(args[5])/60 + float(args[6])/3600) * (1 if args[7].upper() == "E" else -1)
                    elif len(args) >= 6:
                        lat = (float(args[0]) + float(args[1])/60) * (1 if args[2].upper() == "N" else -1)
                        lon = (float(args[3]) + float(args[4])/60) * (1 if args[5].upper() == "E" else -1)
                    elif len(args) >= 4:
                        lat = float(args[0]) * (1 if args[1].upper() == "N" else -1)
                        lon = float(args[2]) * (1 if args[3].upper() == "E" else -1)
                    elif len(args) >= 2:
                        lat, lon = float(args[0]), float(args[1])
                        
                    if lat is not None and lon is not None:
                        infobox_data['lat'] = f"{lat:.6f}"
                        infobox_data['lon'] = f"{lon:.6f}"
                except ValueError:
                    pass


        infobox_data[key] = value

    if region:
        iso = parse_iso3166_2(region)
        if iso:
            infobox_data.update(iso)

    if not infobox_data.get('admin1_code') and infobox_data.get('region'):
        iso = parse_iso3166_2(infobox_data['region'])
        if iso:
            infobox_data.update(iso)

    infobox_data = {
        k: v for k, v in infobox_data.items()
        if v and not (str(v).strip().startswith("<!--") and str(v).strip().endswith("-->"))
    }

    if verbose:
        print(f"Parsed infobox keys: {list(infobox_data.keys())}")
    return infobox_data


def parse_wikitext_airlines_destinations(wikitext: str) -> dict:
    """
    Extract airline to destinations data from ``{{Airport-dest-list}}`` templates.

    Only destinations expressed as Wikipedia wikilinks are included.

    Parameters
    ----------
    wikitext : str
        Full wikitext of the airport Wikipedia page.

    Returns
    -------
    dict
        ``{"passenger": {airline_name: [{"name": str, "wikipedia_url": str}, ...], ...}, "cargo": {...}}``
    """
    wikicode      = mwparserfromhell.parse(wikitext)
    result: dict  = {"passenger": {}, "cargo": {}}

    for template in wikicode.filter_templates():
        t_name = template.name.lower().strip().replace("-", " ")
        if not (t_name.startswith("airport dest list") or t_name.startswith("airport destination list")):
            continue
            
        # Find the closest preceding heading
        is_cargo = False
        try:
            # We must iterate backwards from the template's index in the parent's nodes
            nodes = wikicode.nodes
            idx = nodes.index(template)
            for i in range(idx, -1, -1):
                if isinstance(nodes[i], mwparserfromhell.nodes.heading.Heading):
                    if "cargo" in str(nodes[i].title).lower():
                        is_cargo = True
                    break
        except ValueError:
            pass # Template not found in top-level nodes, assume passenger
            
        target_dict = result["cargo"] if is_cargo else result["passenger"]

        positional = [p for p in template.params if str(p.name).strip().isdigit()]
        positional.sort(key=lambda p: int(str(p.name).strip()))
        
        step = 2
        if template.has("3rdcoltitle"): step += 1
        if template.has("4thcoltitle"): step += 1
        if template.has("5thcoltitle"): step += 1
        if template.has("6thcoltitle"): step += 1
        
        for i in range(0, len(positional) - (step - 1), step):
            airline_raw = str(positional[i].value)
            dests_raw = str(positional[i+1].value)

            # Resolve airline name
            airline_wikicode = mwparserfromhell.parse(
                re.sub(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>', '', airline_raw, flags=re.DOTALL | re.IGNORECASE).strip()
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
            dests_raw = re.sub(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>', '', dests_raw, flags=re.DOTALL | re.IGNORECASE).strip()
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
                if airline not in target_dict:
                    target_dict[airline] = []
                # Avoid duplicating destinations if they are listed in multiple templates in the same section
                existing_urls = {d['wikipedia_url'] for d in target_dict[airline]}
                target_dict[airline].extend([d for d in dest_objs if d['wikipedia_url'] not in existing_urls])

    return result


# ---------------------------------------------------------------------------
# Fallback HTML info extraction
# ---------------------------------------------------------------------------

def fallback_fetch_wikipedia_airport_info(html_content: str) -> dict:
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
        if '-' in region_code:
            country_code, subdivision = region_code.split('-', 1)
            country = pycountry.countries.get(alpha_2=country_code.upper())
            s = pycountry.subdivisions.get(code=region_code.upper())
            if country:
                return {
                    'country_alpha3':   country.alpha_3,
                    'country_name':     country.name,
                    'admin1_code':      f"{country.alpha_2}-{subdivision.upper()}",
                    'admin1_name':      s.name if s else None,
                }
                
        # Exact string match fallback for things like "Pennsylvania"
        region_code_lower = region_code.strip().lower()
        
        # Legacy name map for common outdated geocoder names (e.g., French pre-2016 regions)
        legacy_names = {
            "aquitaine": "FR-NAQ",
            "alsace": "FR-GES",
            "champagne-ardenne": "FR-GES",
            "lorraine": "FR-GES",
            "auvergne": "FR-ARA",
            "rhône-alpes": "FR-ARA",
            "bourgogne": "FR-BFC",
            "franche-comté": "FR-BFC",
            "bretagne": "FR-BRE",
            "centre": "FR-CVL",
            "corse": "FR-COR",
            "languedoc-roussillon": "FR-OCC",
            "midi-pyrénées": "FR-OCC",
            "nord-pas-de-calais": "FR-HDF",
            "picardie": "FR-HDF",
            "basse-normandie": "FR-NOR",
            "haute-normandie": "FR-NOR",
            "pays de la loire": "FR-PDL",
            "provence-alpes-côte d'azur": "FR-PAC"
        }
        if region_code_lower in legacy_names:
            iso_code = legacy_names[region_code_lower]
            country_code, subdivision = iso_code.split('-', 1)
            country = pycountry.countries.get(alpha_2=country_code.upper())
            s = pycountry.subdivisions.get(code=iso_code.upper())
            return {
                'country_alpha3':   country.alpha_3 if country else None,
                'country_name':     country.name if country else None,
                'admin1_code':      f"{country_code.upper()}-{subdivision.upper()}",
                'admin1_name':      s.name if s else None,
            }
            
        # Short strings like "US" or "CA" should not be treated as subdivisions
        if len(region_code_lower) > 2:
            for s in pycountry.subdivisions:
                if s.name.lower() == region_code_lower:
                    country_code, subdivision = s.code.split('-', 1)
                    country = pycountry.countries.get(alpha_2=country_code.upper())
                    return {
                        'country_alpha3':   country.alpha_3 if country else None,
                        'country_name':     country.name if country else None,
                        'admin1_code':      f"{country_code.upper()}-{subdivision.upper()}",
                        'admin1_name':      s.name,
                    }
        return None
    except Exception as exc:
        warnings.warn(
            f"Could not parse ISO 3166-2 code {region_code!r}: {exc}",
            UserWarning, stacklevel=2,
        )
        return None

# ---------------------------------------------------------------------------
# Centralized Processing Helpers
# ---------------------------------------------------------------------------

def build_url_to_codes_map(verbose: bool = False) -> dict:
    """
    Builds a mapping from Wikipedia URL to IATA/ICAO codes.
    Loads from local JSONs, manual overrides, and processes redirects via Wikipedia API.
    """
    from .paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR
    import json
    import os
    import csv
    import urllib.parse
    import requests
    
    if verbose:
        print("Building global URL-to-IATA/ICAO map...")
        
    url_to_codes = {}
    
    # Hardcoded manual overrides for known edge cases where Wikipedia and ourairports disagree
    # without any redirect linking them.
    MANUAL_OVERRIDES = {
        "https://en.wikipedia.org/wiki/Obuasi_Airport": {
            "iata": "iata code not found",
            "icao": "icao code not found",
            "gps": "GH-0006"
        }
    }
    for url, codes in MANUAL_OVERRIDES.items():
        url_to_codes[urllib.parse.unquote(url)] = codes
    
    csv_path = os.path.join(TEMP_RESULTS_DIR, "processed_locations.csv")
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                code = row.get("iata_icao_gps", row.get("iata"))
                if row.get("url") and code:
                    url_to_codes[urllib.parse.unquote(row["url"])] = {"iata": code, "icao": "icao code not found"}

    manual_path = os.path.join(TEMP_RESULTS_DIR, "manual_airport_mapping.csv")
    if os.path.exists(manual_path):
        with open(manual_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("url") and row.get("iata"):
                    url_to_codes[urllib.parse.unquote(row["url"])] = {"iata": row["iata"], "icao": "icao code not found", "gps": "gps code not found"}
                    
    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    if os.path.exists(airport_data_dir):
        for fname in os.listdir(airport_data_dir):
            if not fname.endswith(".json"): continue
            try:
                with open(os.path.join(airport_data_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    url = urllib.parse.unquote(data.get("wikipedia_url")) if data.get("wikipedia_url") else None
                    if url:
                        url_to_codes[url] = {
                            "iata": data.get("iata") or "iata code not found",
                            "icao": data.get("icao") or "icao code not found",
                            "gps": data.get("gps") or "gps code not found"
                        }
            except Exception:
                pass
                
    # Also load from TEMP_RESULTS_DIR subdirectories JSON files (from recent scrapes)
    for subdir in ["airports_rooted_sweep", "missing_from_ourairports"]:
        dir_path = os.path.join(TEMP_RESULTS_DIR, subdir)
        if os.path.exists(dir_path):
            for fname in os.listdir(dir_path):
                if not fname.endswith(".json"): continue
                try:
                    with open(os.path.join(dir_path, fname), "r", encoding="utf-8") as f:
                        data = json.load(f)
                        url = urllib.parse.unquote(data.get("wikipedia_url")) if data.get("wikipedia_url") else None
                        if url:
                            if url not in url_to_codes:
                                url_to_codes[url] = {
                                    "iata": data.get("iata") or "iata code not found",
                                    "icao": data.get("icao") or "icao code not found",
                                    "gps": data.get("gps") or "gps code not found"
                                }
                            else:
                                if data.get("iata"): url_to_codes[url]["iata"] = data["iata"]
                                if data.get("icao"): url_to_codes[url]["icao"] = data["icao"]
                                if data.get("gps"): url_to_codes[url]["gps"] = data["gps"]
                except Exception:
                    pass

    # We only resolve redirects for URLs found in the JSON/manual files, NOT the massive ourairports.csv cache
    urls_to_resolve = list(url_to_codes.keys())
    
    # Now load from ourairports.csv so they don't get sent to Wikipedia API
    try:
        from .airport_level_functions import _load_ourairports_data
        ourairports_data = _load_ourairports_data()
        for url, data in ourairports_data.items():
            if url:
                parsed_url = urllib.parse.unquote(url)
                if parsed_url not in url_to_codes:
                    gps_code = data.get("gps_code")
                    if not gps_code and not data.get("iata_code") and not data.get("icao_code"):
                        gps_code = data.get("ident")
                        
                    url_to_codes[parsed_url] = {
                        "iata": data.get("iata_code") or "iata code not found",
                        "icao": data.get("icao_code") or "icao code not found",
                        "gps": gps_code or "gps code not found"
                    }
    except Exception as e:
        if verbose: print(f"Error loading ourairports data: {e}")
        
    canonical_map = {}
    
    headers = {'User-Agent': 'wikipediaGATN/1.0 (julien.arino@example.com)'}
    for i in range(0, len(urls_to_resolve), 50):
        chunk = urls_to_resolve[i:i+50]
        titles = [urllib.parse.unquote(url.split('/wiki/')[-1]) for url in chunk]
        titles_str = "|".join(titles)
        try:
            r = requests.get(f'https://en.wikipedia.org/w/api.php?action=query&titles={titles_str}&redirects=1&format=json', headers=headers, timeout=10)
            if r.status_code == 200:
                res_json = r.json()
                if 'query' in res_json:
                    title_to_canonical = {t: t.replace('_', ' ') for t in titles}
                    if 'normalized' in res_json['query']:
                        for n in res_json['query']['normalized']:
                            title_to_canonical[n['from']] = n['to']
                    if 'redirects' in res_json['query']:
                        for rd in res_json['query']['redirects']:
                            for orig, norm in list(title_to_canonical.items()):
                                if norm == rd['from']:
                                    title_to_canonical[orig] = rd['to']
                    
                    for orig_url, orig_title in zip(chunk, titles):
                        canonical_title = title_to_canonical.get(orig_title, orig_title)
                        canonical_url = urllib.parse.unquote(f"https://en.wikipedia.org/wiki/{canonical_title.replace(' ', '_')}")
                        if canonical_url != orig_url:
                            canonical_map[canonical_url] = url_to_codes[orig_url]
        except Exception as e:
            if verbose: print(f"Wikipedia API error resolving canonicals: {e}")
            
    url_to_codes.update(canonical_map)
    return url_to_codes

def format_destinations_list(raw_destinations: list, airlines_destinations_map: dict, url_to_codes: dict) -> list:
    """
    Format a list of destinations into a strict schema of dictionaries.
    Looks up IATA/ICAO codes using url_to_codes map.
    Deduplicates destinations that resolve to the same canonical URL or airport code.
    """
    import urllib.parse
    mapped_dict = {}
    
    for dest in raw_destinations:
        if isinstance(dest, dict):
            # Already formatted, use url as key
            d_url = dest.get("wikipedia_url")
            if d_url:
                if d_url in mapped_dict:
                    mapped_dict[d_url]["airlines"] = sorted(list(set(mapped_dict[d_url].get("airlines", []) + dest.get("airlines", []))))
                else:
                    mapped_dict[d_url] = dest
            continue
            
        elif isinstance(dest, (list, tuple)) and len(dest) >= 2:
            city, d_url = dest[0], urllib.parse.unquote(dest[1])
            canonical_url = d_url
            
            codes = url_to_codes.get(d_url)
            if not codes:
                # Fallback: query Wikipedia API to see if this is a redirect to a known URL
                try:
                    import requests
                    headers = {'User-Agent': 'wikipediaGATN/1.0 (julien.arino@example.com)'}
                    title = urllib.parse.unquote(d_url.split('/wiki/')[-1])
                    r = requests.get(f'https://en.wikipedia.org/w/api.php?action=query&titles={title}&redirects=1&format=json', headers=headers, timeout=5)
                    if r.status_code == 200:
                        res_json = r.json()
                        if 'query' in res_json and 'redirects' in res_json['query']:
                            # It's a redirect, get the target
                            target_title = res_json['query']['redirects'][0]['to']
                            target_url = urllib.parse.unquote(f"https://en.wikipedia.org/wiki/{target_title.replace(' ', '_')}")
                            canonical_url = target_url
                            if target_url in url_to_codes:
                                codes = url_to_codes[target_url]
                                # Cache it for next time
                                url_to_codes[d_url] = codes
                except Exception:
                    pass
                    
            if not codes:
                codes = {"iata": "iata code not found", "icao": "icao code not found", "gps": "gps code not found"}
                
            op_airlines = []
            for al_name, cities in airlines_destinations_map.items():
                if city in cities:
                    op_airlines.append(al_name)
                    
            # Determine merge key
            merge_key = canonical_url
            if codes.get("iata", "iata code not found") != "iata code not found":
                merge_key = codes["iata"]
            elif codes.get("icao", "icao code not found") != "icao code not found":
                merge_key = codes["icao"]
            elif codes.get("gps", "gps code not found") != "gps code not found":
                merge_key = codes["gps"]
                
            if merge_key in mapped_dict:
                mapped_dict[merge_key]["airlines"] = sorted(list(set(mapped_dict[merge_key]["airlines"] + op_airlines)))
            else:
                mapped_dict[merge_key] = {
                    "city": city,
                    "wikipedia_url": canonical_url,
                    "codes": [codes.get("iata", "iata code not found"), codes.get("icao", "icao code not found"), codes.get("gps", "gps code not found")],
                    "airlines": sorted(list(set(op_airlines)))
                }
                
    return list(mapped_dict.values())

_OURAIRPORTS_CACHE = None

def _load_ourairports_data():
    global _OURAIRPORTS_CACHE
    if _OURAIRPORTS_CACHE is not None:
        return _OURAIRPORTS_CACHE
        
    import os
    import csv
    import requests
    from .paths import PUBLIC_DATA_DIR
    
    ourairports_path = os.path.join(PUBLIC_DATA_DIR, "ourairports.csv")
    if not os.path.exists(ourairports_path):
        url = "https://davidmegginson.github.io/ourairports-data/airports.csv"
        try:
            print(f"Downloading OurAirports dataset from {url}...")
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            with open(ourairports_path, "w", encoding="utf-8") as f:
                f.write(r.text)
        except Exception as e:
            print(f"Warning: Failed to download OurAirports dataset: {e}")
            _OURAIRPORTS_CACHE = {}
            return _OURAIRPORTS_CACHE
            
    cache = {}
    try:
        with open(ourairports_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                iata = row.get("iata_code", "").strip()
                icao = row.get("icao_code", "").strip()
                wiki = row.get("wikipedia_link", "").strip()
                if iata: cache[iata] = row
                if icao: cache[icao] = row
                if wiki: cache[wiki] = row
    except Exception as e:
        print(f"Warning: Failed to parse OurAirports dataset: {e}")
        
    _OURAIRPORTS_CACHE = cache
    return _OURAIRPORTS_CACHE

def infer_missing_geographic_data(data: dict) -> dict:
    """
    Attempt to infer missing geographic data (lat, lon, admin1, admin2, country)
    using the geopy and reverse_geocoder fallbacks.
    Returns the mutated data dictionary.
    """
    import pycountry_convert as pc
    import pycountry
    from geopy.geocoders import Nominatim
    
    geolocator = Nominatim(user_agent="wikipediaGATN")
    
    # -------------------------------------------------------------------------
    # Priority 1: OurAirports Database
    # -------------------------------------------------------------------------
    oa_cache = _load_ourairports_data()
    oa_row = None
    if data.get("iata") and data.get("iata") in oa_cache:
        oa_row = oa_cache[data["iata"]]
    elif data.get("icao") and data.get("icao") in oa_cache:
        oa_row = oa_cache[data["icao"]]
    elif data.get("wikipedia_url") and data.get("wikipedia_url") in oa_cache:
        oa_row = oa_cache[data["wikipedia_url"]]
    if oa_row:
        # Add gps code if available
        if oa_row.get("gps_code"):
            data["gps"] = oa_row["gps_code"].strip()
            
        # Backfill coordinates if missing
        if not data.get("lat") or not data.get("lon"):
            if oa_row.get("latitude_deg") and oa_row.get("longitude_deg"):
                data["lat"] = str(oa_row["latitude_deg"])
                data["lon"] = str(oa_row["longitude_deg"])
                
        # Resolve authoritative country and region
        if oa_row.get("iso_country"):
            c = pycountry.countries.get(alpha_2=oa_row["iso_country"])
            if c:
                data["country_alpha3"] = c.alpha_3
                data["country_name"] = c.name
                
        if oa_row.get("iso_region"):
            data["admin1_code"] = oa_row["iso_region"]
            try:
                s = pycountry.subdivisions.get(code=oa_row["iso_region"])
                if s:
                    data["admin1_name"] = s.name
            except Exception:
                pass
                
    # -------------------------------------------------------------------------
    # Priority 2: Fallback processing and Geopy
    # -------------------------------------------------------------------------
    
    # Fallback for city-served
    if not data.get("city-served") and data.get("location"):
        data["city-served"] = data.get("location")
    if not data.get("city-served-wikipedia") and data.get("location"):
        data["city-served-wikipedia"] = data.get("location")
        
    # Simplify city-served and location (strip wikitext and grab the first part before a comma)
    import mwparserfromhell
    for key in ["city-served", "location"]:
        if data.get(key):
            try:
                # Strip wikitext like [[Link|Text]] -> Text
                clean_text = mwparserfromhell.parse(str(data[key])).strip_code().strip()
                # Split by comma to grab the core city (e.g., "Pau, Pyrénées-Atlantiques" -> "Pau")
                if "," in clean_text:
                    clean_text = clean_text.split(",")[0].strip()
                data[key] = clean_text
            except Exception:
                pass
        
    # Clean up dirty legacy admin codes
    if data.get("admin1_code"):
        if len(str(data.get("admin1_code"))) > 6:
            # ISO-3166-2 codes are max 6 characters (e.g. FR-NAQ). Anything longer is garbage text.
            data["admin1_code"] = None
        elif "-" not in str(data.get("admin1_code")) and data.get("country_alpha3"):
            # If the code is missing the country prefix (e.g., 'NAQ' instead of 'FR-NAQ'), prepend it
            try:
                c = pycountry.countries.get(alpha_3=data["country_alpha3"])
                if c:
                    data["admin1_code"] = f"{c.alpha_2}-{data['admin1_code']}"
            except Exception:
                pass
                
        # Resolve admin1_name if it was erroneously set to the code (e.g., US-WI)
        if data.get("admin1_code") and data.get("admin1_name") == data.get("admin1_code"):
            try:
                s = pycountry.subdivisions.get(code=data["admin1_code"])
                if s:
                    data["admin1_name"] = s.name
            except Exception:
                pass
    
    # Fill in lat/lon if missing but we have an ISO region or location (only if OurAirports failed)
    if not data.get("lat") or not data.get("lon"):
        query = data.get("admin1_name") or data.get("location")
        if query:
            try:
                import time
                time.sleep(1) # Be nice to Nominatim
                loc = geolocator.geocode(query, timeout=10)
                if loc:
                    data["lat"] = str(loc.latitude)
                    data["lon"] = str(loc.longitude)
            except Exception:
                pass

    # Reverse geocoder fallback for country and admin info
    if not data.get("admin1_code") or len(str(data.get("admin1_code"))) > 3 or not data.get("country_alpha3") or not data.get("admin2_name"):
        if data.get("lat") and data.get("lon"):
            try:
                import reverse_geocoder as rg
                res = rg.search((data["lat"], data["lon"]), mode=1)
                if res:
                    match = res[0]
                    # Fix admin1
                    if not data.get("admin1_code") or len(str(data.get("admin1_code"))) > 3:
                        iso = parse_iso3166_2(match.get("admin1", ""))
                        if iso:
                            data.update(iso)
                    # Fix admin2
                    if not data.get("admin2_name") and match.get("admin2"):
                        data["admin2_name"] = match.get("admin2")
                    # Fix country
                    if not data.get("country_alpha3") and match.get("cc"):
                        c = pycountry.countries.get(alpha_2=match.get("cc"))
                if c:
                            data["country_alpha3"] = c.alpha_3
                            data["country_name"] = c.name
            except Exception:
                pass

    # Fix continent if missing
    if not data.get("continent") and data.get("country_alpha3"):
        try:
            c = pycountry.countries.get(alpha_3=data["country_alpha3"])
            if c:
                cont_code = pc.country_alpha2_to_continent_code(c.alpha_2)
                data["continent"] = pc.map_continent_code_to_continent_name(cont_code)
        except Exception:
            pass
            
    return data

def compare_airports_with_ourairports(output_csv: str = None) -> str:
    """
    Compares airports in airports_information.csv with ourairports.csv and 
    generates a CSV of airports in ourairports.csv that we have not picked up.
    
    Criteria for an airport to be included:
    1. It must not be "closed"
    2. It must have a wikipedia_link
    3. It must not be present in airports_information.csv
    """
    import os
    import csv
    from .paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR
    
    if output_csv is None:
        os.makedirs(TEMP_RESULTS_DIR, exist_ok=True)
        output_csv = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports.csv")
        
    airports_info_path = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")
    ourairports_path = os.path.join(PUBLIC_DATA_DIR, "ourairports.csv")
    
    if not os.path.exists(airports_info_path):
        raise FileNotFoundError(f"{airports_info_path} does not exist.")
    if not os.path.exists(ourairports_path):
        raise FileNotFoundError(f"{ourairports_path} does not exist.")
        
    known_iatas = set()
    known_icaos = set()
    known_wikis = set()
    
    with open(airports_info_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("iata"): known_iatas.add(row["iata"].strip().upper())
            if row.get("icao"): known_icaos.add(row["icao"].strip().upper())
            if row.get("wikipedia_url"): 
                wiki = row["wikipedia_url"].strip()
                known_wikis.add(wiki)
                known_wikis.add(wiki.split("wikipedia.org/")[-1])
                
    missing_airports = []
    
    with open(ourairports_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("type") == "closed":
                continue
                
            if row.get("scheduled_service") != "yes":
                continue
                
            wiki_link = row.get("wikipedia_link", "").strip()
            if not wiki_link:
                continue
                
            iata = row.get("iata_code", "").strip().upper()
            icao = row.get("icao_code", "").strip().upper()
            wiki_end = wiki_link.split("wikipedia.org/")[-1]
            
            # Check if we already picked it up
            if (iata and iata in known_iatas) or \
               (icao and icao in known_icaos) or \
               (wiki_link in known_wikis) or \
               (wiki_end in known_wikis):
                continue
                
            missing_airports.append(row)
            
    if missing_airports:
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=missing_airports[0].keys())
            writer.writeheader()
            writer.writerows(missing_airports)
            
    print(f"Found {len(missing_airports)} missing airports with wikipedia links.")
    if missing_airports:
        print(f"Exported to {output_csv}")
        
    return output_csv

def find_active_missing_airports(input_csv: str = None, output_csv: str = None, max_workers: int = 5) -> str:
    """
    Takes the CSV generated by compare_airports_with_ourairports and checks the 
    Wikipedia page for each airport. If the page contains an 'Airlines and destinations'
    or 'Cargo' section, it is saved to a new active CSV.
    """
    import os
    import csv
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .paths import TEMP_RESULTS_DIR
    
    if input_csv is None:
        input_csv = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports.csv")
    if output_csv is None:
        os.makedirs(TEMP_RESULTS_DIR, exist_ok=True)
        output_csv = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports_active.csv")
        
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"{input_csv} does not exist. Run compare_airports_with_ourairports() first.")
        
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        airports = list(reader)
        fieldnames = reader.fieldnames
        
    if not airports:
        print("Input CSV is empty.")
        return output_csv
        
    print(f"Checking {len(airports)} Wikipedia pages for active flight sections...")
    
    active_airports = []
    
    def check_active(airport):
        url = airport.get("wikipedia_link", "").strip()
        if not url:
            return None
            
        try:
            headers = {"User-Agent": "wikipediaGATN/0.1.0 (Global Air Transportation Networks research; julien.arino@umanitoba.ca)"}
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            html = res.text.lower()
            if 'id="airlines_and_destinations"' in html or 'id="passenger"' in html or 'id="cargo"' in html or 'id="airlines"' in html:
                return airport
        except Exception:
            pass
        return None

    processed = 0
    total = len(airports)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_active, a): a for a in airports}
        for future in as_completed(futures):
            processed += 1
            result = future.result()
            if result:
                active_airports.append(result)
                
            if processed % 100 == 0 or processed == total:
                print(f"Processed {processed}/{total} pages. Found {len(active_airports)} active so far...", end="\\r", flush=True)
                
    print(f"\\nFound {len(active_airports)} active missing airports out of {total} total.")
    
    if active_airports:
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(active_airports)
        print(f"Exported active airports to {output_csv}")
        
    return output_csv
