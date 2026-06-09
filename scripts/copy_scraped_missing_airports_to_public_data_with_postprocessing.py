"""
Merges JSON data from successfully scraped missing airports (in tmp_results) back into the main public/airport_data repository, including symmetrisation of connections.
"""

import json
import os
import re
import shutil

TMP_RESULTS_DIR = "data/tmp_results/missing_from_ourairports"
PUBLIC_DATA_DIR = "data/public/airport_data"

def get_city_name(data):
    """Fallback logic to get a decent city name string."""
    if data.get("city"): return data["city"]
    if data.get("city-served-wikipedia"): return data["city-served-wikipedia"]
    if data.get("city-served"): return data["city-served"]
    if data.get("location"): return data["location"]
    return "Unknown City"

def get_best_code(codes):
    """Return IATA > ICAO > GPS"""
    for c in codes:
        if c and c not in ["iata code not found", "icao code not found", "gps code not found"]:
            return c
    return None

def symmetrise_link(target_code, missing_data, route_airlines, is_cargo=False):
    """
    Inject `missing_data` into the public `target_code.json` file as a destination,
    using `route_airlines`.
    """
    target_path = os.path.join(PUBLIC_DATA_DIR, f"{target_code}.json")
    if not os.path.exists(target_path):
        return False
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            target_data = json.load(f)
    except Exception as e:
        print(f"Error reading {target_path}: {e}")
        return False
        
    dest_key = "destinations_cargo" if is_cargo else "destinations"
    airlines_dest_key = "airlines_destinations_cargo" if is_cargo else "airlines_destinations"
    
    if dest_key not in target_data or not isinstance(target_data[dest_key], list): 
        target_data[dest_key] = []
    if airlines_dest_key not in target_data or not isinstance(target_data[airlines_dest_key], dict): 
        target_data[airlines_dest_key] = {}
    
    missing_code = missing_data.get("iata") or missing_data.get("icao") or missing_data.get("gps")
    if not missing_code:
        return False
        
    missing_city = get_city_name(missing_data)
    
    # Check if missing_code is already in target's destinations
    already_exists = False
    for d in target_data[dest_key]:
        d_code = get_best_code(d.get("codes", []))
        if d_code == missing_code:
            already_exists = True
            # Merge airlines if already exists
            existing_airlines = set(d.get("airlines", []))
            new_airlines = set(route_airlines)
            d["airlines"] = sorted(list(existing_airlines | new_airlines))
            break
            
    if not already_exists:
        target_data[dest_key].append({
            "city": missing_city,
            "wikipedia_url": missing_data.get("wikipedia_url", ""),
            "codes": [
                missing_data.get("iata", "iata code not found"), 
                missing_data.get("icao", "icao code not found"), 
                missing_data.get("gps", "gps code not found")
            ],
            "airlines": sorted(list(set(route_airlines)))
        })
        print(f"    [+] Added {missing_code} ({missing_city}) to {target_code}'s {dest_key}")
        
    # Update airlines_destinations dictionary
    for al in route_airlines:
        if al not in target_data[airlines_dest_key]:
            target_data[airlines_dest_key][al] = []
        if missing_city not in target_data[airlines_dest_key][al]:
            target_data[airlines_dest_key][al].append(missing_city)
            target_data[airlines_dest_key][al].sort()
            
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(target_data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return True
    except Exception as e:
        print(f"Error writing {target_path}: {e}")
        return False

def main():
    if not os.path.exists(TMP_RESULTS_DIR):
        print(f"Error: {TMP_RESULTS_DIR} does not exist.")
        return
        
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    
    files = [f for f in os.listdir(TMP_RESULTS_DIR) if f.endswith(".json")]
    print(f"Found {len(files)} files to merge.")
    
    for fname in sorted(files):
        # Extract base code (e.g. 1RL.0.json -> 1RL)
        match = re.match(r"^([^.]+)\.\d+\.json$", fname)
        if not match:
            print(f"Skipping malformed filename: {fname}")
            continue
        base_code = match.group(1)
        
        src_path = os.path.join(TMP_RESULTS_DIR, fname)
        dst_path = os.path.join(PUBLIC_DATA_DIR, f"{base_code}.json")
        
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                missing_data = json.load(f)
        except Exception as e:
            print(f"Error reading {src_path}: {e}")
            continue
            
        print(f"Processing {base_code}...")
        
        # Symmetrise passenger destinations
        for d in missing_data.get("destinations", []):
            dest_code = get_best_code(d.get("codes", []))
            if dest_code:
                symmetrise_link(dest_code, missing_data, d.get("airlines", []), is_cargo=False)
                
        # Symmetrise cargo destinations
        for d in missing_data.get("destinations_cargo", []):
            dest_code = get_best_code(d.get("codes", []))
            if dest_code:
                symmetrise_link(dest_code, missing_data, d.get("airlines", []), is_cargo=True)
                
        # Copy to public directory
        shutil.copy2(src_path, dst_path)
        print(f"  -> Copied to {dst_path}")
        
    print("Merge complete.")

if __name__ == "__main__":
    main()
