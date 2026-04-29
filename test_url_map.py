from wikipediaGATN.airport_level_functions import build_url_to_codes_map
url_map = build_url_to_codes_map(verbose=False)
target = "https://en.wikipedia.org/wiki/Harle_Airfield"
print("Harle:", url_map.get(target))
