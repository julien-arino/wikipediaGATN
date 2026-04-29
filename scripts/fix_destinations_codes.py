import os
import json
import urllib.parse
from wikipediaGATN.paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR
from wikipediaGATN.airport_level_functions import build_url_to_codes_map

def fix():
    print("Building global URL map...")
    url_map = build_url_to_codes_map(verbose=False)
    
    files_to_check = []
    
    # 1. Public Data
    d1 = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    if os.path.exists(d1):
        for f in os.listdir(d1):
            if f.endswith(".json"):
                files_to_check.append(os.path.join(d1, f))
                
    # 2. Tmp Results
    d2 = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports")
    if os.path.exists(d2):
        for f in os.listdir(d2):
            if f.endswith(".json"):
                files_to_check.append(os.path.join(d2, f))
                
    for path in files_to_check:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            
        changed = False
        
        for key in ["destinations", "destinations_cargo"]:
            dests = data.get(key, [])
            for dest in dests:
                if isinstance(dest, dict) and "codes" in dest:
                    d_url = urllib.parse.unquote(dest.get("wikipedia_url", ""))
                    codes = url_map.get(d_url, {})
                    gps = codes.get("gps", "gps code not found")
                    
                    if len(dest["codes"]) == 2:
                        dest["codes"].append(gps)
                        changed = True
                    elif len(dest["codes"]) == 3:
                        if dest["codes"][2] != gps:
                            dest["codes"][2] = gps
                            changed = True
                            
        if changed:
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    fix()
