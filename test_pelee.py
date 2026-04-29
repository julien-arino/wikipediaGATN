from wikipediaGATN.airport_level_functions import build_url_to_codes_map
url_map = build_url_to_codes_map()
print(url_map.get('https://en.wikipedia.org/wiki/Pelee_Island_Airport'))
