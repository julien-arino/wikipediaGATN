import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json

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
        # Extract the page title from the URL
        match = re.search(r'/wiki/([^#?]+)', identifier)
        if not match:
            print("Invalid Wikipedia URL.")
            return None
        page_title = match.group(1).replace('_', ' ')
        print(f"Extracted page title from URL: {page_title}")
    else:
        # Determine if it's IATA (3 letters) or ICAO (4 letters)
        if re.fullmatch(r'[A-Za-z]{3}', identifier):
            search_term = f"{identifier.upper()} airport"
        elif re.fullmatch(r'[A-Za-z]{4}', identifier):
            search_term = f"{identifier.upper()} airport"
        else:
            print("Identifier must be a 3-letter IATA, 4-letter ICAO code, or Wikipedia URL.")
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

        print(f"Found page title for {identifier}: {page_title}")

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
            next_table = header.find_next('table')
            if next_table:
                header_row = next_table.find('tr')
                ths = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
                print("Table headers:", ths)
                airline_idx = next((i for i, th in enumerate(ths) if 'airline' in th), None)
                if airline_idx is None:
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
    return airlines

def extract_destinations_from_html(html_content):
    """
    Extracts a set of (destination name, Wikipedia link) from the Wikipedia airport page HTML.
    Looks for a table under a header containing 'Airlines and destinations'.
    Returns a set of (name, url) tuples.
    """
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
                print("Table headers:", ths)
                dest_idx = next((i for i, th in enumerate(ths) if 'destination' in th), None)
                if dest_idx is None:
                    print("Could not find destination column in:", ths)
                    continue
                for row in next_table.find_all('tr')[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) > dest_idx:
                        dest_cell = cells[dest_idx]
                        links = dest_cell.find_all('a')
                        for link in links:
                            title = link.get('title')
                            href = link.get('href')
                            if title and href and href.startswith('/wiki/'):
                                full_url = f"https://en.wikipedia.org{href}"
                                destinations.add((title, full_url))
            break
    return destinations

def extract_airlines_destinations_from_html(html_content):
    """
    Extracts a mapping of airlines to their destinations from the Wikipedia airport page HTML.
    Looks for a table under a header containing 'Airlines and destinations'.
    Returns a dictionary where keys are airline names and values are sets of destination names.
    """
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
                print("Table headers:", ths)
                airline_idx = next((i for i, th in enumerate(ths) if 'airline' in th), None)
                dest_idx = next((i for i, th in enumerate(ths) if 'destination' in th), None)
                if airline_idx is None or dest_idx is None:
                    print("Could not find airline or destination columns in:", ths)
                    continue
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
    return airline_dest_map

def extract_iata_icao_from_html(html_content):
    """
    Extracts the IATA and ICAO codes from the Wikipedia airport page HTML.
    Returns a tuple: (IATA, ICAO) or (None, None) if not found.
    """
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

def get_second_degree_connections(initial_code, delay=1.0):
    """
    Given an initial airport code (IATA/ICA/Wikipedia URL), lists direct connections,
    then lists all second-degree connections (destinations from each direct destination).
    For each airport considered, calls save_airport_info_and_destinations unless the file already exists in CODE/OUTPUT.
    Returns a dict: { direct_destination_name: set((name, url), ...) }
    """
    # Ensure OUTPUT directory exists as a subdirectory of CODE
    output_dir = os.path.join(os.path.dirname(__file__), "OUTPUT")
    os.makedirs(output_dir, exist_ok=True)

    # First degree: direct destinations from the initial airport
    html = get_wikipedia_airport_page_html(initial_code)
    if not html:
        print(f"Could not fetch page for {initial_code}")
        return {}

    # Save info for the initial airport if not already present
    initial_info = extract_airport_information(html)
    iata_code = initial_info.get('iata') or str(initial_code)
    initial_filename = os.path.join(output_dir, f"{iata_code}.json")
    if not os.path.exists(initial_filename):
        save_airport_info_and_destinations(initial_code)

    direct_destinations = extract_destinations_from_html(html)
    print(f"Direct destinations from {initial_code}: {[name for name, url in direct_destinations]}")

    second_degree = {}
    for dest_name, dest_url in direct_destinations:
        dest_html = get_wikipedia_airport_page_html(dest_url)
        if dest_html:
            dest_info = extract_airport_information(dest_html)
            dest_iata = dest_info.get('iata') or dest_name
            dest_filename = os.path.join(output_dir, f"{dest_iata}.json")
            if not os.path.exists(dest_filename):
                save_airport_info_and_destinations(dest_url)
            dest_connections = extract_destinations_from_html(dest_html)
            second_degree[dest_name] = dest_connections
        else:
            print(f"Could not fetch page for {dest_name}")
            second_degree[dest_name] = set()
        time.sleep(delay)  # Be polite to Wikipedia's servers

    return second_degree

def extract_airport_information(html_content):
    """
    Extracts IATA, ICAO, city/metropolitan area served, location, and coordinates from the Wikipedia airport page HTML.
    Returns a dictionary with keys: 'iata', 'icao', 'serves', 'location', 'coordinates'.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    infobox = soup.find('table', class_='infobox')
    info = {'iata': None, 'icao': None, 'serves': None, 'location': None, 'coordinates': None}

    if infobox:
        for row in infobox.find_all('tr'):
            header = row.find('th')
            data = row.find('td')
            label = header.get_text(" ", strip=True).lower() if header else ""
            value = data.get_text(" ", strip=True) if data else ""

            # IATA and ICAO: search for them anywhere in the row
            row_text = row.get_text(" ", strip=True)
            iata_match = re.search(r'IATA\s*[:\-]?\s*([A-Z0-9]{3})', row_text, re.I)
            icao_match = re.search(r'ICAO\s*[:\-]?\s*([A-Z0-9]{4})', row_text, re.I)
            if iata_match:
                info['iata'] = iata_match.group(1).upper()
            if icao_match:
                info['icao'] = icao_match.group(1).upper()
            # Sometimes codes are in separate rows
            if "iata" in label and not info['iata']:
                code = value.strip().upper()
                if re.fullmatch(r'[A-Z0-9]{3}', code):
                    info['iata'] = code
            if "icao" in label and not info['icao']:
                code = value.strip().upper()
                if re.fullmatch(r'[A-Z0-9]{4}', code):
                    info['icao'] = code

            # Serves: look for "serves" or "served" in the label, but ignore if the value is an airline
            if ("serves" in label or "served" in label or "city" in label) and data:
                # Heuristic: if value contains "region", "area", or a city name (not an airline)
                if not re.search(r'airlines?|airways?|westjet|delta|united|lufthansa|air canada|jetblue|easyjet|ryanair', value, re.I):
                    info['serves'] = value

            # Location: always capture if present
            if "location" in label and value:
                info['location'] = value

            # Coordinates: always capture if present
            if "coordinates" in label and value:
                # Try to extract the last purely numeric coordinate pair (decimal degrees)
                # Example: '43°38′06″N 001°22′04″E / 43.63500°N 1.36778°E / 43.63500; 1.36778'
                matches = re.findall(r'([+-]?\d+\.\d+)\s*;\s*([+-]?\d+\.\d+)', value)
                if matches:
                    lat, lon = matches[-1]
                    info['coordinates'] = f"{lat}, {lon}"
                else:
                    info['coordinates'] = value

    return info

def save_airport_info_and_destinations(identifier, level=0):
    """
    For a given identifier (IATA/ICAO code or Wikipedia URL), fetches the Wikipedia page,
    extracts airport information and destinations, and saves the result as JSON in CODE/OUTPUT/{IATA}.{level}.json.
    Adds a field 'num_destinations' to airport_info and 'wikipedia_url' with the page address.
    """
    html = get_wikipedia_airport_page_html(identifier)
    if not html:
        print(f"Could not fetch Wikipedia page for {identifier}")
        return None

    airport_info = extract_airport_information(html)
    destinations = list(extract_destinations_from_html(html))  # Convert set to list for JSON serialization

    # Add number of destinations to airport_info
    airport_info['num_destinations'] = len(destinations)

    # Add Wikipedia page address to airport_info
    if isinstance(identifier, str) and identifier.startswith("http"):
        airport_info['wikipedia_url'] = identifier
    else:
        # Try to reconstruct the Wikipedia URL from the page title
        session = requests.Session()
        api_url = "https://en.wikipedia.org/w/api.php"
        headers = {
            "User-Agent": "MyCoolBot/1.0 (myemail@example.com) PythonRequestsLibrary/1.0"
        }
        if re.fullmatch(r'[A-Za-z]{3}', identifier):
            search_term = f"{identifier.upper()} airport"
        elif re.fullmatch(r'[A-Za-z]{4}', identifier):
            search_term = f"{identifier.upper()} airport"
        else:
            search_term = identifier
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
        except Exception:
            page_title = None
        if page_title:
            airport_info['wikipedia_url'] = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
        else:
            airport_info['wikipedia_url'] = None

    # Use IATA code for filename, fallback to identifier if not found
    iata_code = airport_info.get('iata') or str(identifier)
    filename = f"{iata_code}.{level}.json"
    output_dir = os.path.join(os.path.dirname(__file__), "OUTPUT")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    result = {
        "airport_info": airport_info,
        "destinations": destinations
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Saved data to {output_path}")
    return iata_code  # Return the code for tracking processed airports

def get_second_degree_connections(initial_code, delay=1.0, clean_output=False):
    """
    Given an initial airport code (IATA/ICAO/Wikipedia URL), lists direct connections,
    then lists all second-degree connections (destinations from each direct destination).
    For each airport considered, calls save_airport_info_and_destinations unless the airport has already been processed (any level).
    If clean_output is True, deletes all JSON files in CODE/OUTPUT before starting.
    Returns a dict: { direct_destination_name: set((name, url), ...) }
    """
    output_dir = os.path.join(os.path.dirname(__file__), "OUTPUT")
    os.makedirs(output_dir, exist_ok=True)

    # Optionally clean OUTPUT directory
    if clean_output:
        for fname in os.listdir(output_dir):
            if fname.endswith(".json"):
                os.remove(os.path.join(output_dir, fname))
        print("Cleaned OUTPUT directory.")

    processed_airports = set()

    # Level 0: initial airport
    html = get_wikipedia_airport_page_html(initial_code)
    if not html:
        print(f"Could not fetch page for {initial_code}")
        return {}

    initial_info = extract_airport_information(html)
    iata_code = initial_info.get('iata') or str(initial_code)
    # Check if this airport has already been processed (any level)
    already_processed = any(f.startswith(f"{iata_code}.") and f.endswith(".json") for f in os.listdir(output_dir))
    if not already_processed:
        save_airport_info_and_destinations(initial_code, level=0)
    processed_airports.add(iata_code)

    direct_destinations = extract_destinations_from_html(html)
    print(f"Direct destinations from {initial_code}: {[name for name, url in direct_destinations]}")

    second_degree = {}
    for dest_name, dest_url in direct_destinations:
        dest_html = get_wikipedia_airport_page_html(dest_url)
        if dest_html:
            dest_info = extract_airport_information(dest_html)
            dest_iata = dest_info.get('iata') or dest_name
            # Check if this airport has already been processed (any level)
            already_processed = any(f.startswith(f"{dest_iata}.") and f.endswith(".json") for f in os.listdir(output_dir))
            if not already_processed:
                save_airport_info_and_destinations(dest_url, level=1)
            processed_airports.add(dest_iata)
            dest_connections = extract_destinations_from_html(dest_html)
            second_degree[dest_name] = dest_connections
        else:
            print(f"Could not fetch page for {dest_name}")
            second_degree[dest_name] = set()
        time.sleep(delay)  # Be polite to Wikipedia's servers

    return second_degree

def get_multi_path_length_connections(initial_code, path_length=2, delay=1.0, clean_output=False):
    """
    Crawls airport connections for several path lengths.
    Tracks processed airports by their Wikipedia URL.
    Saves each airport's info using save_airport_info_and_destinations with the correct path length.
    """
    output_dir = os.path.join(os.path.dirname(__file__), "OUTPUT")
    os.makedirs(output_dir, exist_ok=True)

    # Optionally clean OUTPUT directory
    if clean_output:
        for fname in os.listdir(output_dir):
            if fname.endswith(".json"):
                os.remove(os.path.join(output_dir, fname))
        print("Cleaned OUTPUT directory.")

    processed_urls = set()
    url_to_info = {}  # url -> (iata, name, url)
    to_process = [(initial_code, 0)]

    for plen in range(path_length + 1):
        print(f"\nProcessing path length {plen} ({len(to_process)} airports)...")
        current_generation = to_process
        to_process = []
        for identifier, level in current_generation:
            # Always fetch the page to get the Wikipedia URL and info
            html = get_wikipedia_airport_page_html(identifier)
            if not html:
                print(f"Could not fetch page for {identifier}")
                continue

            airport_info = extract_airport_information(html)
            iata_code = airport_info.get('iata') or str(identifier)
            airport_name = airport_info.get('serves') or iata_code
            wikipedia_url = airport_info.get('wikipedia_url')
            if not wikipedia_url:
                if isinstance(identifier, str) and identifier.startswith("http"):
                    wikipedia_url = identifier

            if wikipedia_url in processed_urls:
                print(f"Already processed {wikipedia_url} in an earlier path, skipping.")
                continue

            # Save info for this airport
            save_airport_info_and_destinations(identifier, level=level)
            processed_urls.add(wikipedia_url)
            url_to_info[wikipedia_url] = (iata_code, airport_name, wikipedia_url)

            # Only continue if not at last path length
            if level < path_length:
                destinations = extract_destinations_from_html(html)
                for dest_name, dest_url in destinations:
                    # Always fetch the destination page to get its Wikipedia URL
                    dest_html = get_wikipedia_airport_page_html(dest_url)
                    if not dest_html:
                        continue
                    dest_info = extract_airport_information(dest_html)
                    dest_iata = dest_info.get('iata') or dest_name
                    dest_airport_name = dest_info.get('serves') or dest_name
                    dest_wikipedia_url = dest_info.get('wikipedia_url') or dest_url
                    if dest_wikipedia_url in processed_urls:
                        print(f"Already processed {dest_wikipedia_url} in an earlier path, skipping.")
                        continue
                    to_process.append((dest_url, level + 1))
                    time.sleep(delay)
            time.sleep(delay)

    # Optionally, return the mapping for reference
    return url_to_info

if __name__ == "__main__":
    # Example usage:
    get_multi_path_length_connections("YWG", clean_output=True)