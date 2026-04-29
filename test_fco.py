from wikipediaGATN.airport_level_functions import build_url_to_codes_map
url_map = build_url_to_codes_map(verbose=False)
for k, v in url_map.items():
    if v.get('iata') == 'FCO':
        print(f"Found FCO mapping: {k} -> {v}")
print("Checking Leonardo:", url_map.get("https://en.wikipedia.org/wiki/Leonardo_da_Vinci–Fiumicino_Airport"))
