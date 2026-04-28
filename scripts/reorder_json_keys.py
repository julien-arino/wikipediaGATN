import os
import json

from wikipediaGATN.paths import PUBLIC_DATA_DIR

PREFERRED_ORDER = [
    "iata", "icao", "name", "city-served", "city-served-wikipedia", 
    "location", "lat", "lon", "altitude", "continent", "region", 
    "country_alpha3", "country_name", "subdivision_code", 
    "wikipedia_url", "number_airlines", "outdegree", "airlines", 
    "destinations", "airlines_destinations", 
    "date-time-parse", "date-time-wikidata"
]

def reorder():
    d = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    for f in os.listdir(d):
        if not f.endswith(".json"): continue
        p = os.path.join(d, f)
        with open(p, "r") as fh:
            data = json.load(fh)
            
        new_data = {}
        for k in PREFERRED_ORDER:
            if k in data:
                new_data[k] = data.pop(k)
                
        # append any leftover keys
        for k, v in data.items():
            new_data[k] = v
            
        with open(p, "w") as fh:
            json.dump(new_data, fh, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    reorder()
