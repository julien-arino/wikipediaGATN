import sys
sys.path.append('src')
from wikipediaGATN.airport_level_functions import *

link = "https://en.wikipedia.org/wiki/Calgary_International_Airport"
html = fetch_wikipedia_airport_html(link)
wikitext = fetch_wikipedia_airport_wikitext(link)

airlines_html = fetch_wikipedia_airlines(link=link, html_content=html, verbose=True)
dests_html = fetch_wikipedia_destinations(link=link, html_content=html, verbose=True)

print("Sample dests HTML:", list(dests_html)[:5])

found_brandon = [d for d in dests_html if 'brandon' in str(d).lower()]
print("Found Brandon in HTML?", found_brandon)

ad_wiki = parse_wikitext_airlines_destinations(wikitext)
print("Sample wiki ad:", list(ad_wiki.items())[:2])

found_brandon_wiki = [(a, d) for a, dests in ad_wiki.items() for d in dests if 'brandon' in d.lower()]
print("Found Brandon in Wikitext?", found_brandon_wiki)

url_to_codes = build_url_to_codes_map()
print("Brandon in url_to_codes?", any('brandon' in u.lower() for u in url_to_codes.keys()))
