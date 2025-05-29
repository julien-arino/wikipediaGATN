## AIRPORT LEVEL FUNCTIONS
#
# Functions that interact with Wikipedia to fetch airport-level information, including:
# - Wikipedia page link for an airport based on IATA/ICAO code or wikipedia URL
# - Extracting HTML content of the airport page:
#    - Extracting airlines and destinations from the airport page
#    - Extracting IATA/ICAO codes, serves, location, coordinates, airlines, and destinations

import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json
import urllib.parse
from geopy.point import Point

from .paths import TEMP_RESULTS_DIR, PUBLIC_DATA_DIR

###
###
def get_wikipedia_airport_page_link(identifier, verbose=False):
    """
    Given an IATA/ICAO code or Wikipedia URL, return the Wikipedia page URL for the airport.
    If verbose is True, prints the found page title; otherwise, is silent on success.
    """
    if isinstance(identifier, str) and identifier.startswith("http"):
        # Already a Wikipedia URL
        return identifier
    session = requests.Session()
    api_url = "https://en.wikipedia.org/w/api.php"
    headers = {
        "User-Agent": "MyCoolBot/1.0 (myemail@example.com) PythonRequestsLibrary/1.0"
    }
    # Determine if it's IATA (3 letters) or ICAO (4 letters)
    if re.fullmatch(r'[A-Za-z]{3}', identifier):
        search_term = f"{identifier.upper()} airport"
    elif re.fullmatch(r'[A-Za-z]{4}', identifier):
        search_term = f"{identifier.upper()} airport"
    else:
        print("Identifier must be a 3-letter IATA, 4-letter ICAO code, or Wikipedia URL.")
        return None

    # Search for the Wikipedia page title using the code
    search_params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": search_term,
        "formatversion": "2"
    }
    page_title = None
    try:
        response = session.get(url=api_url, params=search_params, headers=headers)
        response.raise_for_status()
        search_data = response.json()
        if search_data.get("query", {}).get("search"):
            page_title = search_data["query"]["search"][0]["title"]
        else:  # Fallback: try just the code
            search_params["srsearch"] = identifier.upper()
            response = session.get(url=api_url, params=search_params, headers=headers)
            response.raise_for_status()
            search_data = response.json()
            if search_data.get("query", {}).get("search"):
                page_title = search_data["query"]["search"][0]["title"]
    except requests.exceptions.RequestException as e:
        print(f"Error during search: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"Could not find page title for {identifier}: {e}")
        return None

    if not page_title:
        print(f"No Wikipedia page title found for {identifier}.")
        return None

    if verbose:
        print(f"Found page title for {identifier}: {page_title}")
    return f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"


###
###
def get_wikipedia_airport_page_html(link, verbose=False):
    """
    Given a Wikipedia page URL, fetches the parsed HTML content of the page.
    """
    session = requests.Session()
    api_url = "https://en.wikipedia.org/w/api.php"
    headers = {
        "User-Agent": "MyCoolBot/1.0 (myemail@example.com) PythonRequestsLibrary/1.0"
    }

    # Extract the page title from the URL and decode it
    match = re.search(r'/wiki/([^#?]+)', link)
    if not match:
        print("Invalid Wikipedia URL.")
        return None
    page_title = urllib.parse.unquote(match.group(1)).replace('_', ' ')
    if verbose:
        print(f"Extracted page title from URL: {page_title}")

    # Fetch the parsed HTML content of the page
    parse_params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "format": "json",
        "formatversion": "2"
    }
    try:
        response = session.get(url=api_url, params=parse_params, headers=headers)
        response.raise_for_status()
        page_data = response.json()
        if page_data.get("parse", {}).get("text"):
            html_content = page_data["parse"]["text"]
            if verbose:
                print(f"Successfully fetched HTML for {page_title}")
            return html_content
        else:
            print(f"Could not retrieve HTML content for {page_title}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page content: {e}")
        return None
    except KeyError:
        print(f"Could not parse content for {page_title}")
        return None

###
###
def extract_airlines_from_airport(identifier="YWG", link=None, html_content=None, verbose=False):
    """
    Extracts a set of airline names from a Wikipedia airport page.
    Accepts:
      - identifier: IATA/ICAO code or Wikipedia page title (default "YWG")
      - link: Wikipedia page URL
      - html_content: HTML content of the Wikipedia page
    The function will fetch missing information as needed.
    """
    if html_content is None:
        if link is None:
            link = get_wikipedia_airport_page_link(identifier, verbose=verbose)
        if not link:
            print("No valid link or identifier provided.")
            return set()
        html_content = get_wikipedia_airport_page_html(link, verbose=verbose)
        if not html_content:
            print(f"Could not fetch HTML for {link}")
            return set()

    soup = BeautifulSoup(html_content, 'html.parser')
    airlines = set()
    headers = soup.find_all(['h2', 'h3', 'h4'])
    for header in headers:
        header_text = header.get_text(strip=True).lower()
        if 'airlines' in header_text and 'destination' in header_text:
            next_table = header.find_next('table')
            if next_table:
                header_row = next_table.find('tr')
                ths = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
                if verbose:
                    print("Table headers:", ths)
                airline_idx = next((i for i, th in enumerate(ths) if 'airline' in th), None)
                if airline_idx is None:
                    if verbose:
                        print("Could not find airline column in:", ths)
                    continue
                for row in next_table.find_all('tr')[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) > airline_idx:
                        airline_cell = cells[airline_idx]
                        links = airline_cell.find_all('a')
                        for link in links:
                            title = link.get('title')
                            if title:
                                airlines.add(title)
            break
    if verbose:
        print(f"Extracted {len(airlines)} airlines.")
    return airlines


###
###
def extract_destinations_from_airport(identifier="YWG", link=None, html_content=None, verbose=False):
    """
    Extracts a set of (destination name, Wikipedia link) from the airport's Wikipedia page.
    Accepts:
      - identifier: IATA/ICAO code or Wikipedia page title (default "YWG")
      - link: Wikipedia page URL
      - html_content: HTML content of the Wikipedia page
    The function will fetch missing information as needed.
    """
    if html_content is None:
        if link is None:
            link = get_wikipedia_airport_page_link(identifier, verbose=verbose)
        if not link:
            print("No valid link or identifier provided.")
            return set()
        html_content = get_wikipedia_airport_page_html(link, verbose=verbose)
        if not html_content:
            print(f"Could not fetch HTML for {link}")
            return set()

    soup = BeautifulSoup(html_content, 'html.parser')
    destinations = set()
    headers = soup.find_all(['h2', 'h3', 'h4'])
    for header in headers:
        header_text = header.get_text(strip=True).lower()
        if 'airlines' in header_text and 'destination' in header_text:
            next_table = header.find_next('table')
            if next_table:
                header_row = next_table.find('tr')
                ths = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
                dest_idx = next((i for i, th in enumerate(ths) if 'destination' in th), None)
                if dest_idx is None:
                    continue
                for row in next_table.find_all('tr')[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) > dest_idx:
                        dest_cell = cells[dest_idx]
                        links = dest_cell.find_all('a')
                        for link in links:
                            title = link.get('title')
                            href = link.get('href')
                            if title and href:
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

###
###
def extract_airlines_destinations_from_airport(identifier="YWG", link=None, html_content=None, verbose=False):
    """
    Extracts a mapping of airlines to their destinations from the airport's Wikipedia page.
    Accepts:
      - identifier: IATA/ICAO code or Wikipedia page title (default "YWG")
      - link: Wikipedia page URL
      - html_content: HTML content of the Wikipedia page
    The function will fetch missing information as needed.
    """
    if html_content is None:
        if link is None:
            link = get_wikipedia_airport_page_link(identifier, verbose=verbose)
        if not link:
            print("No valid link or identifier provided.")
            return {}
        html_content = get_wikipedia_airport_page_html(link, verbose=verbose)
        if not html_content:
            print(f"Could not fetch HTML for {link}")
            return {}

    soup = BeautifulSoup(html_content, 'html.parser')
    airline_dest_map = {}
    headers = soup.find_all(['h2', 'h3', 'h4'])
    for header in headers:
        header_text = header.get_text(strip=True).lower()
        if 'airlines' in header_text and 'destination' in header_text:
            next_table = header.find_next('table')
            if next_table:
                header_row = next_table.find('tr')
                ths = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
                airline_idx = next((i for i, th in enumerate(ths) if 'airline' in th), None)
                dest_idx = next((i for i, th in enumerate(ths) if 'destination' in th), None)
                if airline_idx is None or dest_idx is None:
                    for row in next_table.find_all('tr')[1:]:
                        cells = row.find_all(['td', 'th'])
                        airline_names = set()
                        dest_names = set()
                        for cell in cells:
                            cell_text = cell.get_text(" ", strip=True)
                            if re.search(r'airline', cell_text, re.I):
                                airline_names.update(link.get('title') for link in cell.find_all('a') if link.get('title'))
                            if re.search(r'destination', cell_text, re.I):
                                dest_names.update(link.get('title') for link in cell.find_all('a') if link.get('title'))
                        for airline in airline_names:
                            if airline not in airline_dest_map:
                                airline_dest_map[airline] = set()
                            airline_dest_map[airline].update(dest_names)
                else:
                    for row in next_table.find_all('tr')[1:]:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) > max(airline_idx, dest_idx):
                            airline_cell = cells[airline_idx]
                            dest_cell = cells[dest_idx]
                            airline_names = [link.get('title') for link in airline_cell.find_all('a') if link.get('title')]
                            dest_names = [link.get('title') for link in dest_cell.find_all('a') if link.get('title')]
                            for airline in airline_names:
                                if airline not in airline_dest_map:
                                    airline_dest_map[airline] = set()
                                airline_dest_map[airline].update(dest_names)
            break
    if verbose:
        print(f"Extracted airline-destination map with {len(airline_dest_map)} airlines.")
    return airline_dest_map

###
###
def fallback_extract_airport_information(html_content):
    """
    Fallback: Tries to extract airport info from the HTML if the main infobox logic fails.
    Returns a dictionary with keys: 'iata', 'icao', 'serves', 'location', 'coordinates', 'wikipedia_url'.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    info = {'iata': None, 'icao': None, 'serves': None, 'location': None, 'coordinates': None, 'wikipedia_url': None}

    # Try to find any 3-letter/4-letter codes in the whole page
    text = soup.get_text(" ", strip=True)
    iata_match = re.search(r'\bIATA[:\s\-]*([A-Z0-9]{3})\b', text)
    icao_match = re.search(r'\bICAO[:\s\-]*([A-Z0-9]{4})\b', text)
    if iata_match:
        info['iata'] = iata_match.group(1).upper()
    if icao_match:
        info['icao'] = icao_match.group(1).upper()

    # Try to find a plausible airport name (first h1 or h2)
    title_tag = soup.find(['h1', 'h2'])
    if title_tag:
        info['serves'] = title_tag.get_text(" ", strip=True)

    # Try to find coordinates in decimal format anywhere in the text
    decimal_matches = re.findall(r'(-?\d+\.\d+)', text)
    if len(decimal_matches) >= 2:
        info['coordinates'] = f"{decimal_matches[0]}, {decimal_matches[1]}"
    elif decimal_matches:
        info['coordinates'] = decimal_matches[0]

    # Try to find a location string (look for "Location" in the text)
    location_match = re.search(r'Location[:\s\-]*([^\n]+)', text)
    if location_match:
        info['location'] = location_match.group(1).strip()

    return info

###
###
def extract_iata_icao(identifier="YWG", link=None, html_content=None, verbose=False):
    """
    Extracts the IATA and ICAO codes from the Wikipedia airport page.
    Accepts:
      - identifier: IATA/ICAO code or Wikipedia page title (default "YWG")
      - link: Wikipedia page URL
      - html_content: HTML content of the Wikipedia page
    Returns a tuple: (IATA, ICAO) or (None, None) if not found.
    """
    # Fetch HTML content if not provided
    if html_content is None:
        if link is None:
            link = get_wikipedia_airport_page_link(identifier, verbose=verbose)
        if not link:
            print("No valid link or identifier provided.")
            return (None, None)
        html_content = get_wikipedia_airport_page_html(link, verbose=verbose)
        if not html_content:
            print(f"Could not fetch HTML for {link}")
            return (None, None)
    # If html_content is provided but link is not, try to set link from identifier if it's a URL
    else:
        if link is None and isinstance(identifier, str) and identifier.startswith("http"):
            link = identifier

    soup = BeautifulSoup(html_content, 'html.parser')
    infobox = soup.find('table', class_='infobox')
    iata = None
    icao = None

    if infobox:
        for row in infobox.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            for idx, cell in enumerate(cells):
                text = cell.get_text(" ", strip=True).upper()
                # Look for IATA code
                if "IATA" in text:
                    # Try to get the next cell's text if label is in <th>
                    if idx + 1 < len(cells):
                        iata_candidate = cells[idx + 1].get_text(" ", strip=True).upper()
                        if re.fullmatch(r'[A-Z0-9]{3}', iata_candidate):
                            iata = iata_candidate
                    # Or extract from the same cell if label and code are together
                    match = re.search(r'IATA\s*[:\-]?\s*([A-Z0-9]{3})', text)
                    if match:
                        iata = match.group(1)
                # Look for ICAO code
                if "ICAO" in text:
                    if idx + 1 < len(cells):
                        icao_candidate = cells[idx + 1].get_text(" ", strip=True).upper()
                        if re.fullmatch(r'[A-Z0-9]{4}', icao_candidate):
                            icao = icao_candidate
                    match = re.search(r'ICAO\s*[:\-]?\s*([A-Z0-9]{4})', text)
                    if match:
                        icao = match.group(1)
    return (iata, icao)

###
###
def extract_airport_information(identifier="YWG", link=None, html_content=None, verbose=False):
    """
    Extracts airport information (IATA, ICAO, serves, location, coordinates, airlines, destinations, etc.)
    Accepts:
      - identifier: IATA/ICAO code or Wikipedia page title (default "YWG")
      - link: Wikipedia page URL
      - html_content: HTML content of the Wikipedia page
    The function will fetch missing information as needed.
    Returns a dictionary with these fields plus the Wikipedia page URL as 'wikipedia_url'.
    """
    empty_airport_info = {
        'iata': None,
        'icao': None,
        'serves': None,
        'location': None,
        'coordinates': None,
        'latitude': None,
        'longitude': None,
        'wikipedia_url': None,
        'airlines': [],
        'destinations': [],
        'airlines_destinations': []
    }

    # Fetch html_content if not provided
    if html_content is None:
        if link is None:
            link = get_wikipedia_airport_page_link(identifier, verbose=verbose)
        if not link:
            print("No valid link or identifier provided.")
            return empty_airport_info.copy()
        html_content = get_wikipedia_airport_page_html(link, verbose=verbose)
        if not html_content:
            print(f"Could not fetch HTML for {link}")
            info = empty_airport_info.copy()
            info['wikipedia_url'] = link
            return info
    else:
        # If html_content is provided but link is not, try to set link from identifier if it's a URL
        if link is None and isinstance(identifier, str) and identifier.startswith("http"):
            link = identifier

    soup = BeautifulSoup(html_content, 'html.parser')
    infobox = soup.find('table', class_='infobox')
    info = {
        'iata': None,
        'icao': None,
        'serves': None,
        'location': None,
        'coordinates': None,
        'latitude': None,
        'longitude': None,
        'wikipedia_url': link,
        'airlines': set(),
        'destinations': set(),
        'airlines_destinations': set()
    }

    # Use the robust extractor for IATA/ICAO
    iata, icao = extract_iata_icao(html_content=html_content, verbose=verbose)
    info['iata'] = iata
    info['icao'] = icao

    if infobox:
        for row in infobox.find_all('tr'):
            header = row.find('th')
            data = row.find('td')
            label = header.get_text(" ", strip=True).lower() if header else ""
            value = data.get_text(" ", strip=True) if data else ""

            # Serves
            if ("serves" in label or "served" in label or "city" in label) and data:
                info['serves'] = value

            # Location
            if "location" in label and value:
                info['location'] = value

            # Coordinates: extract only decimal degrees
            if "coordinates" in label and value:
                # Prefer the full value (which may be DMS with N/S/E/W)
                info['coordinates'] = value.strip()
                # Also check for span.geo if not found or value is empty
                if (not info['coordinates'] or info['coordinates'].lower() == "none") and data:
                    span_geo = data.find('span', class_='geo')
                    if span_geo and span_geo.get_text():
                        info['coordinates'] = span_geo.get_text(" ", strip=True)
            # Also check for span.geo if not found
            if not info['coordinates'] and data:
                span_geo = data.find('span', class_='geo')
                if span_geo and span_geo.get_text():
                    coords_from_span = span_geo.get_text(" ", strip=True).split(';')
                    if len(coords_from_span) == 2:
                        try:
                            lat = float(coords_from_span[0].strip())
                            lon = float(coords_from_span[1].strip())
                            info['coordinates'] = f"{lat:.6f}, {lon:.6f}"
                        except ValueError:
                            pass

    # Fallback logic: Trigger if essential codes are missing or if most other info is also missing.
    if (not info['iata'] or not info['icao']) or \
       (not info['serves'] and not info['location'] and not info['coordinates']):
        fallback_data = fallback_extract_airport_information(html_content)
        for key_item in ['iata', 'icao', 'serves', 'location', 'coordinates']:
            if not info[key_item] and fallback_data.get(key_item):
                info[key_item] = fallback_data[key_item]

    coords = info.get("coordinates", "")
    lat, lon = "", ""
    if isinstance(coords, str) and coords:
        lat, lon = parse_lat_lon_from_string(coords)
    info['latitude'] = lat
    info['longitude'] = lon

    # Add airlines and destinations using the new functions
    info['airlines'] = extract_airlines_from_airport(link=link, html_content=html_content, verbose=verbose)
    info['destinations'] = extract_destinations_from_airport(link=link, html_content=html_content, verbose=verbose)
    airlines_destinations = extract_airlines_destinations_from_airport(link=link, html_content=html_content, verbose=verbose)

    # Convert sets to lists before returning
    if isinstance(info.get('airlines'), set):
        info['airlines'] = sorted(list(info['airlines']))
    if isinstance(info.get('destinations'), set):
        info['destinations'] = sorted(list(info['destinations']))
    if isinstance(airlines_destinations, dict):
        info['airlines_destinations'] = {k: sorted(list(v)) for k, v in airlines_destinations.items()}

    return info

###
###
def save_airport_info(airport_info, level=0, verbose=False, save_progress=True):
    """
    Saves the given airport_info dictionary as JSON in CODE/OUTPUT/{IATA}.{level}.json.
    If IATA is not found, uses the Wikipedia page name as the filename (e.g., wiki/Lanseria_International_Airport.N.json).
    Optionally tracks progress in processed_locations.csv (IATA and Wikipedia URL).
    """
    iata_code = airport_info.get('iata')
    if not iata_code:
        # Extract the base Wikipedia page name from the URL
        wiki_url = airport_info.get('wikipedia_url', '')
        match = re.search(r'/wiki/([^/#?]+)', wiki_url)
        if match:
            base_name = f"wiki_{match.group(1)}"
        else:
            base_name = "unknown"
        iata_code = base_name
    filename = f"{iata_code}.{level}.json"
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    output_dir = TEMP_RESULTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    if "destinations" in airport_info and isinstance(airport_info["destinations"], list):
        airport_info["destinations"].sort(key=lambda x: x[0] if isinstance(x, (list, tuple)) and len(x) > 0 else "")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(airport_info, f, ensure_ascii=False, indent=2)

    if save_progress:
        csv_path = os.path.join(output_dir, "processed_locations.csv")
        iata = airport_info.get('iata', '')
        url = airport_info.get('wikipedia_url', '')

        # Read existing entries if file exists, else start with header
        rows = []
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8") as csvfile:
                lines = [line.strip() for line in csvfile.readlines()]
            # Skip header
            rows = [tuple(line.split(",", 1)) for line in lines[1:] if "," in line]
        else:
            # Add header if file does not exist
            with open(csv_path, "w", encoding="utf-8") as csvfile:
                csvfile.write("iata,url\n")

        # Only add if not already present
        if (iata, url) not in rows:
            with open(csv_path, "a", encoding="utf-8") as csvfile:
                csvfile.write(f"{iata},{url}\n")

    if verbose:
        print(f"Saved data to {output_path}")
    return iata_code  # Return the code for tracking processed airports

###
###
def parse_lat_lon_from_string(coord_string):
    """
    Uses geopy to robustly parse latitude and longitude from a coordinate string.
    Returns (latitude, longitude) as strings (decimal degrees).
    """
    try:
        point = Point(coord_string)
        lat = f"{point.latitude:.6f}"
        lon = f"{point.longitude:.6f}"
        return lat, lon
    except Exception:
        return "", ""

