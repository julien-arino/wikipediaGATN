from wikipediaGATN.airport_level_functions import fetch_wikipedia_airport_info
info = fetch_wikipedia_airport_info("https://en.wikipedia.org/wiki/Amsterdam_Airport_Schiphol", verbose=False)
dests = info.get("destinations", [])
found = [d for d in dests if "accra" in str(d).lower() or "kotoka" in str(d).lower()]
print(f"Found {len(found)} Accra entries in AMS pax destinations:")
for f in found: print(f)

dests_cargo = info.get("destinations_cargo", [])
found_cargo = [d for d in dests_cargo if "accra" in str(d).lower() or "kotoka" in str(d).lower()]
print(f"Found {len(found_cargo)} Accra entries in AMS cargo destinations:")
for f in found_cargo: print(f)
