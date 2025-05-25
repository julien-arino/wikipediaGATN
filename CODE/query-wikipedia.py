import requests
from bs4 import BeautifulSoup
import re
import time

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

def get_second_degree_connections(initial_code, delay=1.0):
    """
    Given an initial airport code (IATA/ICAO/Wikipedia URL), lists direct connections,
    then lists all second-degree connections (destinations from each direct destination).
    Returns a dict: { direct_destination_name: set((name, url), ...) }
    """
    # First degree: direct destinations from the initial airport
    html = get_wikipedia_airport_page_html(initial_code)
    if not html:
        print(f"Could not fetch page for {initial_code}")
        return {}

    direct_destinations = extract_destinations_from_html(html)
    print(f"Direct destinations from {initial_code}: {[name for name, url in direct_destinations]}")

    second_degree = {}
    for dest_name, dest_url in direct_destinations:
        print(f"Fetching connections for {dest_name} ({dest_url})...")
        dest_html = get_wikipedia_airport_page_html(dest_url)
        if dest_html:
            dest_connections = extract_destinations_from_html(dest_html)
            second_degree[dest_name] = dest_connections
        else:
            second_degree[dest_name] = set()
        time.sleep(delay)  # Be polite to Wikipedia's servers

    return second_degree

# Example usage:
iata = "YWG"
html = get_wikipedia_airport_page_html(iata)
if html:
    print("Airlines:", extract_airlines_from_html(html))
    print("Destinations:", extract_destinations_from_html(html))
    print("Airline → Destinations:", extract_airlines_destinations_from_html(html))

second_degree = get_second_degree_connections("YWG")
# for dest, connections in second_degree.items():
#     print(f"{dest} connects to: {[name for name, url in connections]}")
