from wikipediaGATN.airport_level_functions import fetch_wikipedia_airport_info
info = fetch_wikipedia_airport_info("https://en.wikipedia.org/wiki/Addis_Ababa_Bole_International_Airport", verbose=False)
dests = info.get("destinations", [])
found = [d for d in dests if "accra" in str(d).lower() or "kotoka" in str(d).lower()]
print(f"Found {len(found)} Accra entries in ADD's wikipedia destinations:")
for f in found: print(f)
