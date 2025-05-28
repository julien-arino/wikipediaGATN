import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json
import urllib.parse

def get_wikipedia_airport_page_html(identifier):
    """
    Fetches the parsed HTML content of an airport's Wikipedia page.
    Accepts:
      - 3-letter IATA code (e.g., 'LHR')
      - 4-letter ICAO code (e.g., 'EGLL')
      - Wikipedia page URL (e.g., 'https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport')
    """
    session = requests.Session()
    api_url = "https://en.wikipedia.org/w/api.php"
    headers = {
        "User-Agent": "MyCoolBot/1.0 (myemail@example.com) PythonRequestsLibrary/1.0"
    }

    # Check if identifier is a Wikipedia URL
    if isinstance(identifier, str) and identifier.startswith("http"):
        # Extract the page title from the URL and decode it
        match = re.search(r'/wiki/([^#?]+)', identifier)
        if not match:
            print(f"Invalid Wikipedia URL: {identifier}")
            return None
        page_title = urllib.parse.unquote(match.group(1)).replace('_', ' ')
        # print(f"Extracted page title from URL: {page_title}") # Verbose, can be commented out
    else:
        # Determine if it's IATA (3 letters) or ICAO (4 letters)
        identifier_upper = str(identifier).upper() # Ensure uppercase for matching
        if re.fullmatch(r'[A-Z0-9]{3}', identifier_upper): # Allow numbers in IATA like '00A'
            search_term = f"{identifier_upper} airport"
        elif re.fullmatch(r'[A-Z0-9]{4}', identifier_upper): # Allow numbers in ICAO
            search_term = f"{identifier_upper} airport"
        else:
            print(f"Identifier '{identifier}' must be a 3-letter IATA, 4-letter ICAO code, or Wikipedia URL.")
            return None

        # Step 1: Search for the Wikipedia page title using the code
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
                search_params["srsearch"] = identifier_upper
                response = session.get(url=api_url, params=search_params, headers=headers)
                response.raise_for_status()
                search_data = response.json()
                if search_data.get("query", {}).get("search"):
                    page_title = search_data["query"]["search"][0]["title"]
        except requests.exceptions.RequestException as e:
            print(f"Error during search for '{identifier}': {e}")
            return None
        except (KeyError, IndexError) as e:
            print(f"Could not find page title for '{identifier}': {e}")
            return None

        if not page_title:
            print(f"No Wikipedia page title found for '{identifier}'.")
            return None

        # print(f"Found page title for {identifier}: {page_title}") # Verbose

    # Step 2: Fetch the parsed HTML content of the page
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
            # print(f"Successfully fetched HTML for {page_title}") # Verbose
            return html_content
        else:
            print(f"Could not retrieve HTML content for {page_title}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page content for {page_title}: {e}")
        return None
    except KeyError:
        print(f"Could not parse content for {page_title}")
        return None

def extract_airlines_from_html(html_content):
    """
    Extracts a list of airlines from the Wikipedia airport page HTML.
    Looks for a table under a header containing 'Airlines and destinations'.
    Returns a set of airline names.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    airlines = set()

    headers = soup.find_all(['h2', 'h3', 'h4'])
    for header in headers:
        header_text = header.get_text(strip=True).lower()
        if 'airlines' in header_text and 'destination' in header_text:
            next_table = header.find_next('table', class_=lambda x: x != 'navbox' and x != 'nowraplinks') # Avoid navboxes
            if next_table and next_table.find('tr'): # Ensure table has rows
                header_row = next_table.find('tr')
                ths = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])] # Some tables use td in header
                # print("Table headers:", ths) # Verbose
                airline_idx = next((i for i, th_text in enumerate(ths) if 'airline' in th_text), None)
                if airline_idx is None:
                    # print("Could not find airline column in:", ths) # Verbose
                    continue # Try next table if this one doesn't have the column
                for row in next_table.find_all('tr')[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) > airline_idx:
                        airline_cell = cells[airline_idx]
                        # Extract from direct text or links, prioritizing titles
                        links = airline_cell.find_all('a')
                        found_airline_in_links = False
                        for link in links:
                            title = link.get('title')
                            if title and not title.startswith("Edit section"): # Filter out edit links
                                airlines.add(title)
                                found_airline_in_links = True
                        if not found_airline_in_links: # Fallback to cell text if no suitable links
                            airline_text = airline_cell.get_text(" ", strip=True)
                            if airline_text:
                                airlines.add(airline_text)
            # break # Original code breaks after first match, consider if multiple tables are possible
    return airlines

def extract_destinations_from_html(html_content):
    """
    Extracts a set of (destination name, Wikipedia link) from the Wikipedia airport page HTML.
    Looks for a table under a header containing 'Airlines and destinations'.
    Returns a set of (name, url) tuples with properly formatted URLs.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    destinations = set()

    headers = soup.find_all(['h2', 'h3', 'h4'])
    for header in headers:
        header_text = header.get_text(strip=True).lower()
        if 'airlines' in header_text and 'destination' in header_text:
            next_table = header.find_next('table', class_=lambda x: x != 'navbox' and x != 'nowraplinks') # Avoid navboxes
            if next_table and next_table.find('tr'):
                header_row = next_table.find('tr')
                ths = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]
                dest_idx = next((i for i, th_text in enumerate(ths) if 'destination' in th_text), None)
                if dest_idx is None:
                    continue
                for row in next_table.find_all('tr')[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) > dest_idx:
                        dest_cell = cells[dest_idx]
                        links = dest_cell.find_all('a')
                        if not links: # If no links, try to get text (e.g. for seasonal notes without links)
                            dest_text = dest_cell.get_text(" ", strip=True)
                            if dest_text: # Add as name, URL will be None or a placeholder
                                destinations.add((dest_text, None)) # Or create a search URL?
                        for link in links:
                            title = link.get('title')
                            href = link.get('href')
                            # Filter out non-airport links or red links
                            if title and href and not href.startswith('#') and 'action=edit' not in href:
                                if href.startswith('/wiki/'):
                                    full_url = f"https://en.wikipedia.org{href}"
                                elif href.startswith('http'):
                                    full_url = href
                                else: # Skip relative URLs that are not /wiki/
                                    continue
                                full_url = urllib.parse.unquote(full_url)
                                destinations.add((title, full_url))
            # break # Original code breaks, consider if multiple tables needed
    return destinations

def fallback_extract_airport_information(html_content):
    """
    Fallback: Tries to extract airport info from the HTML if the main infobox logic fails.
    Returns a dictionary with keys: 'iata', 'icao', 'serves', 'location', 'coordinates', 'wikipedia_url'.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    info = {'iata': None, 'icao': None, 'serves': None, 'location': None, 'coordinates': None, 'wikipedia_url': None}

    text_content = soup.get_text(" ", strip=True) # Renamed variable for clarity
    
    # Try to find any 3-letter/4-letter codes in the whole page
    # More specific regex to avoid matching random capitalized words
    iata_match = re.search(r'\bIATA\s*[:\-]\s*([A-Z0-9]{3})\b', text_content, re.IGNORECASE)
    if not iata_match: # Fallback if "IATA:" prefix is not there but code might be
        iata_match = re.search(r'\b([A-Z]{3})\b\s*\(IATA\)', text_content) # e.g. LHR (IATA)
    if iata_match:
        info['iata'] = iata_match.group(1).upper()

    icao_match = re.search(r'\bICAO\s*[:\-]\s*([A-Z0-9]{4})\b', text_content, re.IGNORECASE)
    if not icao_match:
        icao_match = re.search(r'\b([A-Z]{4})\b\s*\(ICAO\)', text_content) # e.g. EGLL (ICAO)
    if icao_match:
        info['icao'] = icao_match.group(1).upper()

    # Try to find a plausible airport name (first h1)
    title_tag = soup.find('h1', id='firstHeading') # More specific
    if title_tag:
        info['serves'] = title_tag.get_text(" ", strip=True)

    # Try to find coordinates in decimal format anywhere in the text
    # Look for lat, long patterns or decimal degrees
    coord_patterns = [
        r'Coordinates:\s*.*?(-?\d+\.\d+)\s*([NS])\s*.*?(-?\d+\.\d+)\s*([EW])', # DMS-like with N/S/E/W
        r'(-?\d+\.\d+°?[NS])\s*.*?(-?\d+\.\d+°?[EW])', # Degrees symbol
        r'(-?\d+\.\d+),\s*(-?\d+\.\d+)', # Simple decimal pair
    ]
    for pattern in coord_patterns:
        coord_match = re.search(pattern, text_content)
        if coord_match and len(coord_match.groups()) >= 2:
            # Basic extraction, no conversion from DMS for now
            info['coordinates'] = f"{coord_match.group(1)}, {coord_match.group(2)}" 
            break 
    if not info['coordinates']: # Fallback if structured patterns fail
        decimal_matches = re.findall(r'(-?\d+\.\d+)', text_content)
        if len(decimal_matches) >= 2:
            # Take first two plausible decimals, hoping they are lat/lon
            info['coordinates'] = f"{decimal_matches[0]}, {decimal_matches[1]}"
        elif decimal_matches:
            info['coordinates'] = decimal_matches[0]


    # Try to find a location string (look for "Location" in the text)
    location_match = re.search(r'Location\s*[:\-]\s*([^\n.,]+(?:,\s*[^\n.,]+)*)', text_content, re.IGNORECASE)
    if location_match:
        info['location'] = location_match.group(1).strip()
    
    # wikipedia_url is usually derived from the input or search, not easily found in fallback from text

    return info

def extract_airlines_destinations_from_html(html_content):
    """
    Extracts a mapping of airlines to their destinations from the Wikipedia airport page HTML.
    Looks for a table under a header containing 'Airlines and destinations'.
    Returns a dictionary where keys are airline names and values are sets of (destination name, destination URL).
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    airline_dest_map = {}

    headers = soup.find_all(['h2', 'h3', 'h4'])
    for header in headers:
        header_text = header.get_text(strip=True).lower()
        if 'airlines' in header_text and 'destination' in header_text:
            next_table = header.find_next('table', class_=lambda x: x != 'navbox' and x != 'nowraplinks')
            if next_table and next_table.find('tr'):
                header_row = next_table.find('tr')
                ths = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]
                
                airline_idx = next((i for i, th_text in enumerate(ths) if 'airline' in th_text), None)
                dest_idx = next((i for i, th_text in enumerate(ths) if 'destination' in th_text), None)

                if airline_idx is not None and dest_idx is not None:
                    for row in next_table.find_all('tr')[1:]: # Skip header row
                        cells = row.find_all(['td', 'th'])
                        if len(cells) > max(airline_idx, dest_idx):
                            airline_cell = cells[airline_idx]
                            dest_cell = cells[dest_idx]
                            
                            current_airlines = set()
                            airline_links = airline_cell.find_all('a')
                            if airline_links:
                                for link in airline_links:
                                    title = link.get('title')
                                    if title and not title.startswith("Edit section"):
                                        current_airlines.add(title)
                            if not current_airlines: # Fallback to text if no links
                                airline_text = airline_cell.get_text(" ", strip=True)
                                if airline_text:
                                    current_airlines.add(airline_text)

                            current_destinations = set()
                            dest_links = dest_cell.find_all('a')
                            if dest_links:
                                for link in dest_links:
                                    title = link.get('title')
                                    href = link.get('href')
                                    if title and href and not href.startswith('#') and 'action=edit' not in href:
                                        if href.startswith('/wiki/'):
                                            full_url = f"https://en.wikipedia.org{href}"
                                        elif href.startswith('http'):
                                            full_url = href
                                        else:
                                            continue
                                        full_url = urllib.parse.unquote(full_url)
                                        current_destinations.add((title, full_url))
                            if not current_destinations: # Fallback to text
                                dest_text = dest_cell.get_text(" ", strip=True)
                                if dest_text: # Add as name, URL will be None
                                    current_destinations.add((dest_text, None))
                                    
                            for airline_name in current_airlines:
                                if airline_name not in airline_dest_map:
                                    airline_dest_map[airline_name] = set()
                                airline_dest_map[airline_name].update(current_destinations)
                # else: # Fallback if columns not found by name (original file had complex logic here)
                    # print(f"Could not reliably find Airline/Destination columns by header in {header_text}") # Verbose
            # break # Consider if multiple tables are relevant
    return airline_dest_map

def extract_iata_icao_from_html(html_content):
    """
    Extracts the IATA and ICAO codes from the Wikipedia airport page HTML.
    Returns a tuple: (IATA, ICAO) or (None, None) if not found.
    This is the reference implementation for IATA/ICAO extraction.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    infobox = soup.find('table', class_='infobox')
    iata = None
    icao = None

    if infobox:
        for row in infobox.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            for idx, cell_tag in enumerate(cells): # Renamed for clarity
                text_upper = cell_tag.get_text(" ", strip=True).upper() # Renamed
                
                # Look for IATA code
                if not iata: # Process only if not already found
                    if "IATA" in text_upper:
                        # Try to get the next cell's text if label is in <th>
                        if idx + 1 < len(cells):
                            iata_candidate = cells[idx + 1].get_text(" ", strip=True).upper()
                            if re.fullmatch(r'[A-Z0-9]{3}', iata_candidate):
                                iata = iata_candidate
                        
                        # Or extract from the same cell if label and code are together
                        # This can overwrite if next_cell also matched, which is the behavior of this reference func.
                        match = re.search(r'IATA\s*[:\-]?\s*([A-Z0-9]{3})', text_upper)
                        if match:
                            iata = match.group(1)
                
                # Look for ICAO code
                if not icao: # Process only if not already found
                    if "ICAO" in text_upper:
                        if idx + 1 < len(cells):
                            icao_candidate = cells[idx + 1].get_text(" ", strip=True).upper()
                            if re.fullmatch(r'[A-Z0-9]{4}', icao_candidate):
                                icao = icao_candidate
                        
                        match = re.search(r'ICAO\s*[:\-]?\s*([A-Z0-9]{4})', text_upper)
                        if match:
                            icao = match.group(1)
    return (iata, icao)

def get_second_degree_connections(initial_code, delay=1.0):
    """
    Given an initial airport code (IATA/ICA/Wikipedia URL), lists direct connections,
    then lists all second-degree connections (destinations from each direct destination).
    For each airport considered, calls save_airport_info_and_destinations unless the file already exists in CODE/OUTPUT.
    Returns a dict: { direct_destination_name: set((name, url), ...) }
    """
    # Ensure OUTPUT directory exists as a subdirectory of CODE
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    output_dir = os.path.join(script_dir, "OUTPUT")
    os.makedirs(output_dir, exist_ok=True)

    # First degree: direct destinations from the initial airport
    html = get_wikipedia_airport_page_html(initial_code)
    if not html:
        print(f"Could not fetch page for {initial_code}")
        return {}

    # Save info for the initial airport if not already present
    initial_airport_obj = extract_airport_information(html) # Renamed for clarity
    iata_code = initial_airport_obj.get('iata') # Use the extracted IATA
    if not iata_code: # Fallback if IATA couldn't be extracted
        # Create a safe filename from initial_code if it's a string
        iata_code = re.sub(r'[^A-Za-z0-9_]', '', str(initial_code).split('/')[-1]) if isinstance(initial_code, str) else "UNKNOWN_INITIAL"


    initial_filename_base = f"{iata_code}.0" # Level 0
    # Check if any file starting with this base exists (e.g., CODE.0.json)
    if not any(f.startswith(initial_filename_base) and f.endswith(".json") for f in os.listdir(output_dir)):
        save_airport_info_and_destinations(initial_code, level=0) # Pass original identifier

    direct_destinations = extract_destinations_from_html(html)
    print(f"Direct destinations from {initial_code} ({iata_code}): {[name for name, url in direct_destinations if name]}")

    second_degree_connections_map = {} # Renamed
    for dest_name, dest_url in direct_destinations:
        if not dest_url: # Skip if URL is None (e.g. text-only destination)
            print(f"Skipping destination '{dest_name}' due to missing URL.")
            second_degree_connections_map[dest_name] = set()
            continue

        dest_html = get_wikipedia_airport_page_html(dest_url)
        time.sleep(delay)  # Be polite to Wikipedia's servers BEFORE processing

        if dest_html:
            dest_airport_obj = extract_airport_information(dest_html) # Renamed
            dest_iata = dest_airport_obj.get('iata')
            if not dest_iata: # Fallback for filename if IATA not found
                 dest_iata = re.sub(r'[^A-Za-z0-9_]', '', dest_name) if dest_name else "UNKNOWN_DEST"


            dest_filename_base = f"{dest_iata}.1" # Level 1
            if not any(f.startswith(dest_filename_base) and f.endswith(".json") for f in os.listdir(output_dir)):
                 save_airport_info_and_destinations(dest_url, level=1) # Pass URL

            dest_connections = extract_destinations_from_html(dest_html)
            second_degree_connections_map[dest_name] = dest_connections
        else:
            print(f"Could not fetch page for destination: {dest_name}")
            second_degree_connections_map[dest_name] = set()
        

    return second_degree_connections_map

# दिस इज द फंक्शन वी नीड टू अपडेट (This is the function we need to update)
def extract_airport_information(html_content): # THIS IS THE SECOND DEFINITION TO BE UPDATED
    """
    Robustly extracts IATA, ICAO, serves, location, coordinates, and wikipedia_url from the Wikipedia airport page HTML.
    Uses a revised logic for IATA/ICAO extraction to mirror extract_iata_icao_from_html's approach.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    infobox = soup.find('table', class_='infobox')
    info = {'iata': None, 'icao': None, 'serves': None, 'location': None, 'coordinates': None}

    if infobox:
        for row in infobox.find_all('tr'):
            cells = row.find_all(['th', 'td']) 

            # --- Revised IATA/ICAO Extraction Logic ---
            for idx, cell_tag in enumerate(cells): 
                current_cell_text_upper = cell_tag.get_text(" ", strip=True).upper()

                # IATA extraction
                if not info['iata']: 
                    if "IATA" in current_cell_text_upper:
                        if idx + 1 < len(cells):
                            next_cell_text_upper = cells[idx + 1].get_text(" ", strip=True).upper()
                            if re.fullmatch(r'[A-Z0-9]{3}', next_cell_text_upper):
                                info['iata'] = next_cell_text_upper
                        
                        iata_match_current_cell = re.search(r'IATA\s*[:\-]?\s*([A-Z0-9]{3})', current_cell_text_upper)
                        if iata_match_current_cell:
                            info['iata'] = iata_match_current_cell.group(1)

                # ICAO extraction
                if not info['icao']: 
                    if "ICAO" in current_cell_text_upper:
                        if idx + 1 < len(cells):
                            next_cell_text_upper = cells[idx + 1].get_text(" ", strip=True).upper()
                            if re.fullmatch(r'[A-Z0-9]{4}', next_cell_text_upper):
                                info['icao'] = next_cell_text_upper
                        
                        icao_match_current_cell = re.search(r'ICAO\s*[:\-]?\s*([A-Z0-9]{4})', current_cell_text_upper)
                        if icao_match_current_cell:
                            info['icao'] = icao_match_current_cell.group(1)
            # --- End of Revised IATA/ICAO Extraction Logic ---

            # Now extract other fields using the row's th/td pairing
            header_tag = row.find('th')
            data_tag = row.find('td')
            
            if header_tag and data_tag: # Process only if a clear header-data pair exists for these fields
                label = header_tag.get_text(" ", strip=True).lower()
                value = data_tag.get_text(" ", strip=True)

                # Serves (set only if not already found)
                if not info['serves'] and ("serves" in label or "served" in label or "city" in label or "area served" in label):
                    info['serves'] = value

                # Location (set only if not already found)
                if not info['location'] and "location" in label:
                    info['location'] = value

                # Coordinates and potentially Wikipedia URL from GeoHack link (set only if not already found)
                if not info['coordinates'] and "coordinates" in label:
                    # Only extract coordinates, do NOT set info['wikipedia_url'] here!
                    decimal_matches = re.findall(r'(-?\d+\.\d+)', value)
                    if len(decimal_matches) >= 2:
                        info['coordinates'] = f"{decimal_matches[0]}, {decimal_matches[1]}"
                    elif decimal_matches:
                        info['coordinates'] = decimal_matches[0]
                    else:
                        span_geo = data_tag.find('span', class_='geo')
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
    # This uses the fallback_extract_airport_information function defined in this file.
    if (not info['iata'] or not info['icao']) or \
       (not info['serves'] and not info['location'] and not info['coordinates']):
        # print(f"Infobox extraction for {info.get('serves', 'Unknown Airport')} incomplete ({info}), trying fallback.") # Verbose
        fallback_data = fallback_extract_airport_information(html_content)
        for key_item in ['iata', 'icao', 'serves', 'location', 'coordinates']: # Iterate specific keys for fallback
            if not info[key_item] and fallback_data.get(key_item):
                info[key_item] = fallback_data[key_item]

    return info

def save_airport_info_and_destinations(identifier, level=0):
    """
    For a given identifier (IATA/ICAO code or Wikipedia URL), fetches the Wikipedia page,
    extracts airport information and destinations, and saves the result as JSON in CODE/OUTPUT/{FILENAME}.{level}.json.
    Adds 'num_destinations' and 'wikipedia_url_page' to airport_info.
    Filename uses IATA, then ICAO, then a sanitized name from 'serves' or identifier.
    """
    html = get_wikipedia_airport_page_html(identifier)
    if not html:
        print(f"Could not fetch Wikipedia page for '{identifier}' in save_airport_info_and_destinations")
        return None

    airport_info = extract_airport_information(html) # This now uses the updated function
    
    # Attempt to get destinations and airlines_dest_map
    destinations_set = extract_destinations_from_html(html)
    destinations_list = sorted(list(destinations_set), key=lambda x: x[0] if isinstance(x, (list, tuple)) and x and x[0] else "")
    
    airlines_dest_map = extract_airlines_destinations_from_html(html)
    # Convert sets in airlines_dest_map to sorted lists for JSON
    for airline, dests in airlines_dest_map.items():
        airlines_dest_map[airline] = sorted(list(dests), key=lambda x: x[0] if isinstance(x, (list, tuple)) and x and x[0] else "")


    airport_info['num_destinations'] = len(destinations_list)

    # Determine the wikipedia_url of the current page being processed
    current_page_wikipedia_url = None
    if isinstance(identifier, str) and identifier.startswith("http"):
        current_page_wikipedia_url = identifier
    else: # Try to reconstruct from API search if it was a code
        # This logic is similar to get_wikipedia_airport_page_html's search part
        session = requests.Session()
        api_url = "https://en.wikipedia.org/w/api.php"
        headers = {"User-Agent": "MyCoolBot/1.0 (myemail@example.com) PythonRequestsLibrary/1.0"}
        search_term_for_url = f"{str(identifier).upper()} airport" if not str(identifier).startswith("http") else str(identifier)
        
        search_params = {"action": "query", "format": "json", "list": "search", "srsearch": search_term_for_url, "formatversion": "2"}
        try:
            response = session.get(url=api_url, params=search_params, headers=headers)
            response.raise_for_status()
            search_data = response.json()
            if search_data.get("query", {}).get("search"):
                page_title = search_data["query"]["search"][0]["title"]
                current_page_wikipedia_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}"
        except Exception as e:
            # print(f"Could not reconstruct Wikipedia URL for {identifier}: {e}") # Verbose
            pass
    
    airport_info['wikipedia_url_page'] = current_page_wikipedia_url
    # If infobox extraction found a GeoHack URL, it's in airport_info['wikipedia_url']
    # 'wikipedia_url_page' is specifically the URL of the page we just processed.

    # Filename logic: IATA, then ICAO, then sanitized name
    base_filename = airport_info.get('iata')
    if not base_filename:
        base_filename = airport_info.get('icao')
    if not base_filename:
        name_for_file = airport_info.get('serves') or airport_info.get('location') or str(identifier)
        # Sanitize name_for_file for filesystem
        safe_name = re.sub(r'[^\w\s-]', '', name_for_file).strip().replace(' ', '_')
        safe_name = re.sub(r'[-_]+', '_', safe_name) # Consolidate multiple separators
        base_filename = safe_name if safe_name else "unknown_airport"
    
    filename = f"{base_filename}.{level}.json"
    
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    output_dir = os.path.join(script_dir, "OUTPUT")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    result = {
        "airport_info": airport_info,
        "destinations_list": destinations_list, # List of (name, url) tuples
        "airlines_dest_map": airlines_dest_map  # Dict of airline -> list of (dest_name, dest_url)
    }

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved data to {output_path}")
    except Exception as e:
        print(f"Error saving data to {output_path}: {e}")
        return None
        
    return base_filename 


def get_length_1_connections(initial_code, delay=1.0, clean_output=False):
    """
    For a given initial airport code (IATA/ICAO/Wikipedia URL), saves info for the initial airport,
    then for each direct destination, saves its info (unless already processed).
    """
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    output_dir = os.path.join(script_dir, "OUTPUT")
    os.makedirs(output_dir, exist_ok=True)

    if clean_output:
        print(f"Cleaning OUTPUT directory: {output_dir}")
        for fname in os.listdir(output_dir):
            if fname.endswith(".json"):
                try:
                    os.remove(os.path.join(output_dir, fname))
                except OSError as e:
                    print(f"Error removing file {fname}: {e}")
        print("Cleaned OUTPUT directory.")

    processed_filenames = set() # Store base filenames that have been saved in this run

    # Save info for the initial airport (level 0)
    print(f"\nProcessing initial airport: {initial_code} (Level 0)")
    initial_file_base = save_airport_info_and_destinations(initial_code, level=0)
    if initial_file_base:
        processed_filenames.add(initial_file_base)
        
        # Load the saved JSON to get destinations for level 1 processing
        initial_json_path = os.path.join(output_dir, f"{initial_file_base}.0.json")
        if os.path.exists(initial_json_path):
            try:
                with open(initial_json_path, "r", encoding="utf-8") as f:
                    initial_data = json.load(f)
                direct_destinations = initial_data.get("destinations_list", [])
            except Exception as e:
                print(f"Error reading initial airport data from {initial_json_path}: {e}")
                direct_destinations = [] # Cannot proceed with level 1 if destinations are not loaded
        else:
            print(f"Initial airport data file {initial_json_path} not found. Cannot process level 1.")
            direct_destinations = []


        # Save info for each direct destination (level 1)
        print(f"\nProcessing direct destinations from {initial_code} (Level 1)...")
        for dest_idx, (dest_name, dest_url) in enumerate(direct_destinations):
            print(f"  Processing destination {dest_idx+1}/{len(direct_destinations)}: '{dest_name}'")
            if not dest_url: # Skip if URL is None
                print(f"    Skipping destination '{dest_name}' due to missing URL.")
                continue

            # We need to determine a potential base filename for the destination *before* saving
            # to check if it might have been processed under a different identifier but same IATA/name.
            # This is tricky without fetching first. A simpler check is if a file for this *URL* (or its derived name) exists.
            # For this function, we'll rely on save_airport_info_and_destinations to handle naming.
            # We check if a file with level 1 for a *similar name* might exist, but it's imperfect.
            # The most robust way is to fetch, get IATA, then check.

            # Fetch destination HTML to extract its IATA for more robust processed check
            temp_dest_html = get_wikipedia_airport_page_html(dest_url)
            if temp_dest_html:
                temp_dest_info = extract_airport_information(temp_dest_html)
                dest_file_base_check = temp_dest_info.get('iata') or \
                                   temp_dest_info.get('icao') or \
                                   re.sub(r'[^\w\s-]', '', dest_name).strip().replace(' ', '_')
                
                # Check if a level 1 file for this destination base already exists
                potential_dest_file_lvl1 = f"{dest_file_base_check}.1.json"
                if os.path.exists(os.path.join(output_dir, potential_dest_file_lvl1)):
                    print(f"    Skipping already saved (level 1) destination: '{dest_name}' ({potential_dest_file_lvl1})")
                    if dest_file_base_check: processed_filenames.add(dest_file_base_check) # Mark as processed for this run
                    continue
            else:
                print(f"    Could not fetch preliminary HTML for '{dest_name}' to check IATA. Will attempt save.")


            dest_file_base = save_airport_info_and_destinations(dest_url, level=1)
            if dest_file_base:
                processed_filenames.add(dest_file_base)
            time.sleep(delay) 
    else:
        print(f"Failed to process and save initial airport {initial_code}.")


def get_multi_path_length_connections(initial_code, path_length=2, delay=1.0, clean_output=False):
    """
    For a given initial airport code, crawls connections up to path_length.
    Each airport is saved as {FILENAME_BASE}.{level}.json in CODE/OUTPUT.
    FILENAME_BASE is derived from IATA, then ICAO, then sanitized name.
    Avoids re-processing airports if their {FILENAME_BASE}.{any_level}.json file already exists.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    output_dir = os.path.join(script_dir, "OUTPUT")
    os.makedirs(output_dir, exist_ok=True)

    if clean_output:
        print(f"Cleaning OUTPUT directory: {output_dir}")
        for fname in os.listdir(output_dir):
            if fname.endswith(".json"):
                try:
                    os.remove(os.path.join(output_dir, fname))
                except OSError as e:
                    print(f"Error removing file {fname}: {e}")
        print("Cleaned OUTPUT directory.")

    # Set of base filenames that have been saved/processed to avoid redundant saves and fetches
    # A base filename is like "LHR" or "Winnipeg_James_Armstrong_Richardson_International_Airport"
    globally_saved_bases = set() 
    for fname in os.listdir(output_dir): # Pre-populate with existing files
        if fname.endswith(".json"):
            parts = fname.split('.')
            if len(parts) >= 3: # e.g. LHR.0.json
                globally_saved_bases.add(parts[0])


    # Queue stores (identifier_for_API_call, current_processing_level)
    queue = [(initial_code, 0)]
    
    # Keep track of identifiers added to queue to avoid cycles within a single run for non-saved items
    # (identifier, level)
    queued_identifiers_levels = set([(initial_code,0)])


    while queue:
        current_identifier, current_level = queue.pop(0)

        if current_level > path_length:
            continue

        print(f"\nProcessing: '{current_identifier}' at Level {current_level}")

        # Determine a preliminary base filename for checking if already saved
        # This requires fetching HTML first if identifier is not an obvious code
        # This is slightly inefficient as save_airport_info_and_destinations will fetch again
        # but necessary to check globally_saved_bases before committing to a full save.
        pre_fetch_html = get_wikipedia_airport_page_html(current_identifier)
        if not pre_fetch_html:
            print(f"  Skipping '{current_identifier}': Could not pre-fetch HTML.")
            time.sleep(delay) # Still delay even on failure to avoid hammering
            continue
        
        pre_fetch_info = extract_airport_information(pre_fetch_html)
        current_base_filename = pre_fetch_info.get('iata') or \
                                pre_fetch_info.get('icao') or \
                                (re.sub(r'[^\w\s-]', '', pre_fetch_info.get('serves') or str(current_identifier)).strip().replace(' ', '_'))
        current_base_filename = re.sub(r'[-_]+', '_', current_base_filename) if current_base_filename else "unknown_temp"


        # If this base filename has been saved at any level, we assume its info is captured.
        # And we don't need to re-save or re-process its destinations *from this path*.
        # However, we *do* need its destinations if it was saved by a *previous run* and not yet explored in *this run*.
        
        target_json_filename = f"{current_base_filename}.{current_level}.json"
        target_json_path = os.path.join(output_dir, target_json_filename)

        if current_base_filename in globally_saved_bases and os.path.exists(target_json_path):
            print(f"  '{current_identifier}' (as {current_base_filename}) Level {current_level} data already exists. Loading for further processing.")
            # Load existing data to get destinations for the next level
            try:
                with open(target_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                destinations_to_queue = data.get("destinations_list", [])
            except Exception as e:
                print(f"  Error loading existing data {target_json_path}: {e}. Cannot queue destinations.")
                destinations_to_queue = []
        else:
            # Save (or re-save if base was known but not this level's file)
            # save_airport_info_and_destinations will return the base filename it used.
            saved_base_filename = save_airport_info_and_destinations(current_identifier, level=current_level)
            time.sleep(delay) # Delay after each successful save (API call)

            if not saved_base_filename:
                print(f"  Skipping '{current_identifier}': Failed to save airport info.")
                continue # Critical failure, cannot proceed with this item
            
            globally_saved_bases.add(saved_base_filename) # Mark this base as saved in this run

            # Load the just-saved JSON to get info and destinations
            # The filename used by save_airport_info_and_destinations might differ if IATA was found later
            actual_json_path = os.path.join(output_dir, f"{saved_base_filename}.{current_level}.json")
            if not os.path.exists(actual_json_path):
                print(f"  File {actual_json_path} not found after saving, skipping destination queuing.")
                destinations_to_queue = []
            else:
                try:
                    with open(actual_json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    destinations_to_queue = data.get("destinations_list", [])
                except Exception as e:
                    print(f"  Error loading data from {actual_json_path} after save: {e}")
                    destinations_to_queue = []


        # If not at the max path_length, add its destinations to the queue for the next level
        if current_level < path_length:
            for dest_name, dest_url in destinations_to_queue:
                if not dest_url: # Skip destinations with no URL
                    continue
                
                # Check if this destination (identifier, next_level) is already in queue to avoid redundant immediate processing
                if (dest_url, current_level + 1) not in queued_identifiers_levels:
                     # Pre-check if destination base is already globally saved to avoid adding it if fully processed
                    temp_dest_html = get_wikipedia_airport_page_html(dest_url) # Quick peek
                    if temp_dest_html:
                        temp_dest_info = extract_airport_information(temp_dest_html)
                        dest_base_check = temp_dest_info.get('iata') or \
                                          temp_dest_info.get('icao') or \
                                          (re.sub(r'[^\w\s-]', '', temp_dest_info.get('serves') or dest_name).strip().replace(' ', '_'))
                        dest_base_check = re.sub(r'[-_]+', '_', dest_base_check) if dest_base_check else "unknown_dest_temp"

                        # If this destination's base is already in globally_saved_bases,
                        # it means we have processed it (or it existed before this run).
                        # We don't need to add it to the queue again unless we implement logic
                        # to explore from already saved nodes if their specific level file is missing.
                        # For now, if base is known, assume it's covered or will be by another path.
                        if dest_base_check not in globally_saved_bases:
                            queue.append((dest_url, current_level + 1))
                            queued_identifiers_levels.add((dest_url, current_level + 1))
                        # else:
                            # print(f"    Destination base '{dest_base_check}' already globally processed. Not re-queueing from this path.") # Verbose
                    else: # If can't pre-fetch, add to queue and let main loop handle it
                        queue.append((dest_url, current_level + 1))
                        queued_identifiers_levels.add((dest_url, current_level + 1))
                        # print(f"    Could not pre-fetch for {dest_name}, adding to queue.") # Verbose
        # else:
            # print(f"  Reached max path length for '{current_identifier}'.") # Verbose

    print("\nMulti-path connections processing complete.")


if __name__ == '__main__':
    # Example Usages:
    # Ensure the OUTPUT directory is next to this script.

    # Initial airport code can be IATA, ICAO, or full Wikipedia URL
    initial_airport = "YWG"  # Winnipeg James Armstrong Richardson International Airport
    # initial_airport = "https://en.wikipedia.org/wiki/Toronto_Pearson_International_Airport"
    # initial_airport = "LHR" # London Heathrow

    # --- Simple 0-degree and 1st-degree connections ---
    # This will save initial_airport.0.json and its direct_destinations.1.json files
    print("Running: Get Length 1 Connections")
    get_length_1_connections(initial_airport, delay=0.2, clean_output=True)
    # print("-" * 50)

    # --- Multi-path length connections ---
    # This will crawl up to path_length, creating {AIRPORT_ID}.{level}.json for each
    # Example: initial_airport.0.json, then its destinations as .1.json, then their destinations as .2.json
    # print("Running: Get Multi-Path Length Connections")
    # get_multi_path_length_connections(initial_airport, path_length=1, delay=0.2, clean_output=True)
    # # For a deeper crawl, increase path_length (e.g., path_length=2).
    # Be mindful of the number of requests and disk space.
    # get_multi_path_length_connections(initial_airport, path_length=2, delay=0.2, clean_output=False) # Append to previous run

    # print("\nScript finished.")

    # --- Example of how to use extract_airlines_destinations_from_html ---
    # test_html = get_wikipedia_airport_page_html("LHR")
    # if test_html:
    #     print("\nExtracting airlines and destinations map for LHR:")
    #     ad_map = extract_airlines_destinations_from_html(test_html)
    #     for airline, dests in list(ad_map.items())[:5]: # Print first 5 airlines
    #         print(f"  Airline: {airline}")
    #         for d_name, d_url in list(dests)[:3]: # Print first 3 destinations for that airline
    #             print(f"    Destination: {d_name} ({d_url})")


    # --- Example of how to use extract_airport_information directly ---
    # test_html_info = get_wikipedia_airport_page_html("FRA") # Frankfurt Airport
    # if test_html_info:
    #     print("\nExtracting airport information for FRA:")
    #     airport_details = extract_airport_information(test_html_info)
    #     print(json.dumps(airport_details, indent=2))