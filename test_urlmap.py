from wikipediaGATN.airport_level_functions import build_url_to_codes_map
url_map = build_url_to_codes_map(verbose=False)
print(url_map["https://en.wikipedia.org/wiki/Middle_Bass_Island_Airport"])
