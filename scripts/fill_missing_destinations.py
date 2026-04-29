import os
import json
import urllib.parse
from wikipediaGATN.paths import TEMP_RESULTS_DIR
from wikipediaGATN.airport_level_functions import build_url_to_codes_map

def fill_destinations():
    print("Building global URL map...")
    url_map = build_url_to_codes_map(verbose=False)
    
    output_dir = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports")
    if not os.path.exists(output_dir):
        print(f"Directory not found: {output_dir}")
        return
        
    updated_files = 0
    total_dests_updated = 0
    
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json"): continue
        path = os.path.join(output_dir, fname)
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        changed = False
        
        for key in ["destinations", "destinations_cargo"]:
            dests = data.get(key, [])
            for dest in dests:
                if isinstance(dest, dict) and "codes" in dest:
                    d_url = urllib.parse.unquote(dest.get("wikipedia_url", ""))
                    if not d_url: continue
                    
                    codes = url_map.get(d_url, {})
                    
                    new_iata = codes.get("iata", "iata code not found")
                    new_icao = codes.get("icao", "icao code not found")
                    new_gps = codes.get("gps", "gps code not found")
                    
                    # Force array to 3 elements if not already
                    while len(dest["codes"]) < 3:
                        dest["codes"].append("code not found")
                        
                    old_codes = list(dest["codes"])
                    
                    if dest["codes"][0] != new_iata:
                        dest["codes"][0] = new_iata
                        changed = True
                    if dest["codes"][1] != new_icao:
                        dest["codes"][1] = new_icao
                        changed = True
                    if dest["codes"][2] != new_gps:
                        dest["codes"][2] = new_gps
                        changed = True
                        
                    if old_codes != dest["codes"]:
                        total_dests_updated += 1
                        
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            updated_files += 1
            
    print(f"\nDone! Updated {total_dests_updated} destinations across {updated_files} files.")

if __name__ == "__main__":
    fill_destinations()
