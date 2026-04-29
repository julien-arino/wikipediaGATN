import os
import json
import glob
import sys

# Ensure we can import wikipediaGATN
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from wikipediaGATN.airport_level_functions import format_airport_json

airport_data_dir = "/home/jarino/github/wikipediaGATN/data/public/airport_data"
files = glob.glob(os.path.join(airport_data_dir, "*.json"))

changed_files = 0
for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception as e:
        print(f"Error reading {f}: {e}")
        continue
        
    updated = False
    
    # Pax
    dest_len = len(data.get("destinations", []))
    air_len = len(data.get("airlines", []))
    
    if data.get("outdegree") != dest_len:
        data["outdegree"] = dest_len
        updated = True
        
    if data.get("number_airlines") != air_len:
        data["number_airlines"] = air_len
        updated = True
        
    # Cargo
    dest_cargo_len = len(data.get("destinations_cargo", []))
    air_cargo_len = len(data.get("airlines_cargo", []))
    
    if data.get("outdegree_cargo") != dest_cargo_len:
        data["outdegree_cargo"] = dest_cargo_len
        updated = True
        
    if data.get("number_airlines_cargo") != air_cargo_len:
        data["number_airlines_cargo"] = air_cargo_len
        updated = True
        
    if updated:
        # Re-format the JSON so keys are in standard order
        data = format_airport_json(data)
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        changed_files += 1

print(f"Updated {changed_files} JSON files out of {len(files)} total files.")

if changed_files > 0:
    print("Re-exporting airports_information.csv...")
    from wikipediaGATN.result_processing_airports import export_all_airport_data
    export_all_airport_data(verbose=True)
