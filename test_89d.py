from collections import deque
from wikipediaGATN.airport_level_functions import fetch_wikipedia_airport_info
import urllib.parse

seed = "https://en.wikipedia.org/wiki/Kelleys_Island_Land_Field"
visited = set()
queue = deque([(seed, 0)])

while queue:
    url, level = queue.popleft()
    if url in visited: continue
    visited.add(url)
    
    print(f"Level {level} - Scraping {url}")
    info = fetch_wikipedia_airport_info(url)
    dests = info.get("destinations", [])
    print(f"Found {len(dests)} dests.")
    
    for d in dests:
        d_url = urllib.parse.unquote(d.get("wikipedia_url", ""))
        if d_url and d_url not in visited:
            queue.append((d_url, level + 1))
            
