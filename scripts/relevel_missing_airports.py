"""
Adjusts the BFS sweep distance levels for missing airports that were just resolved, assigning them the correct level relative to their parent seeds.
"""

import os
import json
import urllib.parse
import csv
from collections import deque

from wikipediaGATN.paths import TEMP_RESULTS_DIR

def run_relevel():
    input_csv = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports_active.csv")
    output_dir = os.path.join(TEMP_RESULTS_DIR, "missing_from_ourairports")
    
    # 1. Read CSV for seed order
    seed_urls = []
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            link = row.get("wikipedia_link", "").strip()
            if link:
                seed_urls.append(urllib.parse.unquote(link))
                
    # 2. Load all scraped nodes into memory
    nodes = {} # url -> { "fname": str, "code": str, "dests": list, "data": dict }
    
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json"): continue
        path = os.path.join(output_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        url = urllib.parse.unquote(data.get("wikipedia_url", ""))
        if not url: continue
        
        # Get all destination URLs
        dests = []
        for d in data.get("destinations", []) + data.get("destinations_cargo", []):
            if isinstance(d, dict) and d.get("wikipedia_url"):
                dests.append(urllib.parse.unquote(d["wikipedia_url"]))
                
        code = fname.split(".")[0]
        nodes[url] = {
            "fname": fname,
            "code": code,
            "dests": dests,
            "data": data,
            "path": path
        }

    # 3. BFS to assign levels
    levels = {} # url -> level
    visited = set()
    
    # Initialize queue sequentially from seeds
    for seed in seed_urls:
        if seed not in visited and seed in nodes:
            queue = deque([(seed, 0)])
            visited.add(seed)
            
            while queue:
                curr_url, curr_level = queue.popleft()
                levels[curr_url] = curr_level
                
                # Enqueue children
                for dest_url in nodes[curr_url]["dests"]:
                    if dest_url in nodes and dest_url not in visited:
                        visited.add(dest_url)
                        queue.append((dest_url, curr_level + 1))
                        
    # Ensure any disconnected nodes not in CSV but somehow downloaded are leveled? 
    # (Shouldn't happen since we only downloaded CSV ones as .0.json)
    for url in nodes:
        if url not in levels:
            print(f"Warning: {nodes[url]['code']} was not reachable from seeds! Leaving as level 0.")
            levels[url] = 0

    # 4. Rename files
    renamed = 0
    for url, info in nodes.items():
        old_path = info["path"]
        new_fname = f"{info['code']}.{levels[url]}.json"
        new_path = os.path.join(output_dir, new_fname)
        
        if new_fname != info["fname"]:
            os.rename(old_path, new_path)
            renamed += 1
            print(f"Renamed {info['fname']} -> {new_fname}")
            
    print(f"\nDone! Renamed {renamed} files based on proper BFS leveling.")

if __name__ == "__main__":
    run_relevel()
