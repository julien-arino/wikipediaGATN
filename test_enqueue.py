import urllib.parse
from collections import deque
from wikipediaGATN.airport_level_functions import fetch_wikipedia_airport_info, build_url_to_codes_map, format_destinations_list

url_map = build_url_to_codes_map(verbose=False)
seed = "https://en.wikipedia.org/wiki/Kelleys_Island_Land_Field"
queue = deque([(seed, 0, "89D")])
visited = set([seed])

while queue:
    current_url, level, forced_code = queue.popleft()
    print(f"Scraping {current_url} at level {level}")
    info = fetch_wikipedia_airport_info(current_url)
    
    destinations = format_destinations_list(info.get("destinations", []), info.get("airlines_destinations", {}), url_map)
    print(f"Found {len(destinations)} pax dests.")
    
    for d in destinations:
        if isinstance(d, dict):
            d_url = urllib.parse.unquote(d.get("wikipedia_url", ""))
            print(f"Checking dest URL: {d_url}")
            if d_url and d_url not in visited:
                print(f"-> Enqueuing {d_url} at level {level + 1}")
                queue.append((d_url, level + 1, None))
                visited.add(d_url)
    break # Just test the first pop
