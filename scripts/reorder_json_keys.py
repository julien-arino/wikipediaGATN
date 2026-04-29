import os
import json

from wikipediaGATN.paths import PUBLIC_DATA_DIR
from wikipediaGATN.airport_level_functions import format_airport_json

def reorder():
    d = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    for f in os.listdir(d):
        if not f.endswith(".json"): continue
        p = os.path.join(d, f)
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            
        new_data = format_airport_json(data)
            
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(new_data, fh, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    reorder()
