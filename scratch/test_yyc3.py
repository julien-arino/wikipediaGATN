import sys
sys.path.append('src')
from wikipediaGATN.airport_level_functions import *

link = "https://en.wikipedia.org/wiki/Calgary_International_Airport"
result = fetch_wikipedia_airport_wikitext(link)
if isinstance(result, tuple):
    wikitext = result[0]
else:
    wikitext = result

ad_wiki = parse_wikitext_airlines_destinations(wikitext)
print("Keys:", ad_wiki.keys())
for table_type, table_data in ad_wiki.items():
    if 'WestJet Encore' in table_data:
        print(f"WestJet Encore in {table_type}:", table_data['WestJet Encore'])
    
    for airline, dests in table_data.items():
        for d in dests:
            if 'brandon' in d.lower():
                print(f"Found Brandon under {airline} in {table_type} as: {d}")

