from wikipediaGATN.paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR
import os, csv, urllib.parse, json

url_to_codes = {}

manual_path = os.path.join(TEMP_RESULTS_DIR, "manual_airport_mapping.csv")
with open(manual_path, "r", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row.get("url") and row.get("iata"):
            url_to_codes[urllib.parse.unquote(row["url"])] = {"iata": row["iata"], "icao": "icao code not found", "gps": "gps code not found"}
            
target = 'https://en.wikipedia.org/wiki/Pelee_Island_Airport'
print("After manual:", url_to_codes.get(target))

airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
for fname in os.listdir(airport_data_dir):
    if not fname.endswith(".json"): continue
    with open(os.path.join(airport_data_dir, fname), "r", encoding="utf-8") as f:
        data = json.load(f)
        url = urllib.parse.unquote(data.get("wikipedia_url")) if data.get("wikipedia_url") else None
        if url:
            url_to_codes[url] = {
                "iata": data.get("iata") or "iata code not found",
                "icao": data.get("icao") or "icao code not found",
                "gps": data.get("gps") or "gps code not found"
            }
print("After public JSON:", url_to_codes.get(target))

if os.path.exists(TEMP_RESULTS_DIR):
    for fname in os.listdir(TEMP_RESULTS_DIR):
        if not fname.endswith(".json"): continue
        with open(os.path.join(TEMP_RESULTS_DIR, fname), "r", encoding="utf-8") as f:
            data = json.load(f)
            url = urllib.parse.unquote(data.get("wikipedia_url")) if data.get("wikipedia_url") else None
            if url:
                url_to_codes[url] = {
                    "iata": data.get("iata") or "iata code not found",
                    "icao": data.get("icao") or "icao code not found",
                    "gps": data.get("gps") or "gps code not found"
                }
print("After temp JSON:", url_to_codes.get(target))
