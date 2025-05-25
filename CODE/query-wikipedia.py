import requests

def get_wikipedia_airport_page_html(iata_code):
    """
    Fetches the parsed HTML content of an airport's Wikipedia page.
    """
    session = requests.Session()
    api_url = "https://en.wikipedia.org/w/api.php"
    headers = {
        "User-Agent": "MyCoolBot/1.0 (myemail@example.com) PythonRequestsLibrary/1.0"
    }

    # Step 1: Search for the Wikipedia page title using the IATA code
    search_params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": f"{iata_code} airport", # More specific search
        "formatversion": "2"
    }
    page_title = None
    try:
        response = session.get(url=api_url, params=search_params, headers=headers)
        response.raise_for_status()
        search_data = response.json()
        if search_data.get("query", {}).get("search"):
            page_title = search_data["query"]["search"][0]["title"]
        else: # Fallback if initial search fails
            search_params["srsearch"] = iata_code
            response = session.get(url=api_url, params=search_params, headers=headers)
            response.raise_for_status()
            search_data = response.json()
            if search_data.get("query", {}).get("search"):
                page_title = search_data["query"]["search"][0]["title"]

    except requests.exceptions.RequestException as e:
        print(f"Error during search: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"Could not find page title for {iata_code}: {e}")
        return None

    if not page_title:
        print(f"No Wikipedia page title found for {iata_code}.")
        return None

    print(f"Found page title for {iata_code}: {page_title}")

    # Step 2: Fetch the parsed HTML content of the page
    parse_params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",       # We want the HTML text
        "format": "json",
        "formatversion": "2"  # Modern JSON format
    }
    try:
        response = session.get(url=api_url, params=parse_params, headers=headers)
        response.raise_for_status()
        page_data = response.json()
        if page_data.get("parse", {}).get("text"):
            html_content = page_data["parse"]["text"]
            print(f"Successfully fetched HTML for {page_title}")
            # At this point, html_content contains the HTML.
            # You would then use a library like BeautifulSoup to parse it.
            # For example:
            # from bs4 import BeautifulSoup
            # soup = BeautifulSoup(html_content, 'html.parser')
            # tables = soup.find_all('table', {'class': 'wikitable'})
            # ... further parsing logic ...
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

# Example usage:
#iata = "LHR"  # London Heathrow
#html = get_wikipedia_airport_page_html(iata)
#if html:
#    print(f"First 500 characters of HTML for {iata}:")
#    print(html[:500])
#    # Here you would pass 'html' to your HTML parsing function
