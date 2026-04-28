import csv
import json
import os
import requests
import time
import traceback
import warnings
from typing import Union

from dateutil import parser as dt_parser

from .paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR
from .wikipedia_airport_level import (
    get_wikipedia_airport_page_wikitext,
    get_wikipedia_airport_page_html,
    extract_airlines_destinations_from_wikitext,
    fallback_nlp_extract_airlines_destinations,
    extract_airlines_destinations_from_airport,
    extract_airport_information,
    extract_airlines_from_airport,
    extract_destinations_from_airport,
    _SESSION,
    _API_URL
)

# Shared mapping state
_URL_TO_CODES = None


def _load_url_to_codes(verbose: bool = False) -> dict:
    """Load URL -> IATA/ICAO mapping from CSV files to resolve new destinations."""
    global _URL_TO_CODES
    if _URL_TO_CODES is not None:
        return _URL_TO_CODES

    _URL_TO_CODES = {}
    
    # Load processed_locations.csv
    csv_path = os.path.join(TEMP_RESULTS_DIR, "processed_locations.csv")
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("url") and row.get("iata"):
                    _URL_TO_CODES[row["url"]] = {"iata": row["iata"], "icao": "icao code not found"}

    # Load manual overrides
    manual_path = os.path.join(TEMP_RESULTS_DIR, "manual_airport_mapping.csv")
    if os.path.exists(manual_path):
        with open(manual_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("url") and row.get("iata"):
                    _URL_TO_CODES[row["url"]] = {"iata": row["iata"], "icao": "icao code not found"}
                    
    # Also load all existing public airport JSONs to capture their own explicit IATA/ICAOs
    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    if os.path.isdir(airport_data_dir):
        for fname in os.listdir(airport_data_dir):
            if not fname.endswith(".json"): continue
            try:
                with open(os.path.join(airport_data_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    url = data.get("wikipedia_url")
                    if url:
                        _URL_TO_CODES[url] = {
                            "iata": data.get("iata") or "iata code not found",
                            "icao": data.get("icao") or "icao code not found"
                        }
            except Exception:
                pass
                
    if verbose:
        print(f"Loaded {len(_URL_TO_CODES)} pre-mapped Wikipedia destination URLs. Resolving canonical titles...")
        
    # Bulk resolve Wikipedia redirects for all known URLs
    urls_to_resolve = list(_URL_TO_CODES.keys())
    canonical_map = {}
    
    import urllib.parse
    headers = {'User-Agent': 'wikipediaGATN/1.0 (julien.arino@example.com)'}
    for i in range(0, len(urls_to_resolve), 50):
        chunk = urls_to_resolve[i:i+50]
        titles = [urllib.parse.unquote(url.split('/wiki/')[-1]) for url in chunk]
        titles_str = "|".join(titles)
        try:
            r = requests.get(f'https://en.wikipedia.org/w/api.php?action=query&titles={titles_str}&redirects=1&format=json', headers=headers, timeout=10)
            if r.status_code == 200:
                res_json = r.json()
                if 'query' in res_json:
                    title_to_canonical = {t: t.replace('_', ' ') for t in titles}
                    if 'normalized' in res_json['query']:
                        for n in res_json['query']['normalized']:
                            title_to_canonical[n['from']] = n['to']
                    if 'redirects' in res_json['query']:
                        for rd in res_json['query']['redirects']:
                            for orig, norm in list(title_to_canonical.items()):
                                if norm == rd['from']:
                                    title_to_canonical[orig] = rd['to']
                    
                    for orig_url, orig_title in zip(chunk, titles):
                        canonical_title = title_to_canonical.get(orig_title, orig_title)
                        canonical_url = f"https://en.wikipedia.org/wiki/{canonical_title.replace(' ', '_')}"
                        if canonical_url != orig_url:
                            # Map the canonical URL to the original URL's codes
                            canonical_map[canonical_url] = _URL_TO_CODES[orig_url]
        except Exception:
            pass
            
    # Add the canonicalized URLs back into the global dictionary
    _URL_TO_CODES.update(canonical_map)
    
    if verbose:
        print(f"Resolved canonical URLs. Dictionary now contains {len(_URL_TO_CODES)} entries.")
        
    return _URL_TO_CODES


def check_needs_refresh(file_paths: list[str], verbose: bool = False) -> list[str]:
    """
    Check multiple public JSON files to see if their Wikipedia pages have been updated
    since they were last parsed.
    
    Returns a list of file paths that actually need to be refreshed.
    """
    to_refresh = []
    
    # 1. Parse local dates and extract URLs
    urls_to_check = {} # title -> { 'path': path, 'local_dt': dt }
    
    for fpath in file_paths:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            url = data.get("wikipedia_url")
            dt_parse_str = data.get("date-time-parse")
            
            if not url:
                continue
                
            title = url.split("/wiki/")[-1].replace("_", " ")
            
            if not dt_parse_str:
                # Missing parse time means we definitely need to refresh to get it
                to_refresh.append(fpath)
                continue
                
            urls_to_check[title] = {
                'path': fpath,
                'local_dt': dt_parser.isoparse(dt_parse_str)
            }
        except (json.JSONDecodeError, OSError, ValueError):
            # Broken file or broken datetime: queue it for refresh to repair it
            to_refresh.append(fpath)
            
    if not urls_to_check:
        return to_refresh
        
    titles = list(urls_to_check.keys())
    if verbose:
        print(f"Batch-checking Wikidata edit timestamps for {len(titles)} Wikipedia pages...")
        
    # 2. Batch query Wikipedia API for 'timestamp'
    # API allows up to 50 titles per request
    for i in range(0, len(titles), 50):
        chunk = titles[i:i+50]
        titles_str = "|".join(chunk)
        
        params = {
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "titles": titles_str,
            "rvprop": "timestamp",
            "redirects": 1
        }
        
        try:
            response = _SESSION.get(_API_URL, params=params, timeout=20)
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            
            for page in pages.values():
                title = page.get("title")
                revisions = page.get("revisions")
                if not title or not revisions:
                    continue
                    
                remote_dt_str = revisions[0].get("timestamp")
                if not remote_dt_str:
                    continue
                    
                remote_dt = dt_parser.isoparse(remote_dt_str)
                
                # Check if the title was redirected
                # If so, find the original title we requested
                orig_title = None
                if title in urls_to_check:
                    orig_title = title
                else:
                    # In a real redirect, we'd need to trace it, but for simplicity
                    # we can iterate and match. If the page is completely different, we skip.
                    for t in chunk:
                        if t.lower() == title.lower() or t.replace(" ", "_").lower() == title.replace(" ", "_").lower():
                            orig_title = t
                            break
                            
                if orig_title:
                    local_info = urls_to_check[orig_title]
                    if remote_dt > local_info['local_dt']:
                        to_refresh.append(local_info['path'])
                        if verbose:
                            print(f"  ↻ {orig_title} needs refresh (remote {remote_dt} > local {local_info['local_dt']})")
                            
        except Exception as exc:
            if verbose:
                print(f"Error checking timestamps for chunk starting at index {i}: {exc}")
                
        time.sleep(0.5) # Be nice to the API
        
    return to_refresh


def refresh_airport_file(fpath: str, refresh_all_data: bool = False, verbose: bool = False) -> bool:
    """
    Refresh a single airport JSON file.
    
    If `refresh_all_data` is False, it only updates the airlines and destinations,
    leaving the rest of the file exactly as it was (preserving geocoding).
    """
    if verbose:
        print(f"\nRefreshing {os.path.basename(fpath)}...")
        
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"  ✗ Failed to load {fpath}: {exc}")
        return False
        
    url = data.get("wikipedia_url")
    if not url:
        print(f"  ✗ No wikipedia_url found in {fpath}. Cannot refresh.")
        return False
        
    if refresh_all_data:
        # Re-fetch EVERYTHING
        new_data = extract_airport_information(link=url, verbose=verbose)
        
        # We need to map destinations to the expected format
        url_map = _load_url_to_codes(verbose=False)
        mapped_destinations = []
        for dest in new_data.get("destinations", []):
            if len(dest) >= 2:
                city, d_url = dest[0], dest[1]
                codes = url_map.get(d_url, {"iata": "iata code not found", "icao": "icao code not found"})
                mapped_destinations.append([city, d_url, codes["iata"], codes["icao"]])
            else:
                mapped_destinations.append(dest)
                
        new_data["destinations"] = mapped_destinations
        new_data["outdegree"] = len(mapped_destinations)
        new_data["number_airlines"] = len(new_data.get("airlines", []))
        
        # We must NOT lose the country/lat/lon if they were inferred manually in result_processing_airports!
        # So we merge `new_data` INTO `data` to prefer the new parsed stuff, but keep old geocoding if missing.
        for key in ["lat", "lon", "country_alpha3", "country_name", "location", "region", "subdivision_code", "continent"]:
            if not new_data.get(key) and data.get(key):
                new_data[key] = data[key]
                
        data = new_data
    else:
        # Partial refresh: only airlines and destinations
        wikitext, dt_wikidata = get_wikipedia_airport_page_wikitext(link=url, verbose=verbose)
        
        if not wikitext:
            print(f"  ✗ Failed to fetch wikitext for {url}")
            return False
            
        ad_map_wikitext = extract_airlines_destinations_from_wikitext(wikitext)
        
        airlines = []
        destinations = []
        airlines_destinations = {}
        
        if ad_map_wikitext:
            airlines = sorted(ad_map_wikitext.keys())
            destinations = sorted({
                (d["name"], d["wikipedia_url"])
                for dests in ad_map_wikitext.values()
                for d in dests
            })
            airlines_destinations = {
                airline: sorted({d["name"] for d in dests})
                for airline, dests in ad_map_wikitext.items()
            }
        else:
            # Fallback to HTML
            html_content = get_wikipedia_airport_page_html(link=url, verbose=verbose)
            airlines = sorted(list(extract_airlines_from_airport(link=url, html_content=html_content)))
            destinations = sorted(list(extract_destinations_from_airport(link=url, html_content=html_content)))
            ad_map = extract_airlines_destinations_from_airport(link=url, html_content=html_content)
            airlines_destinations = {k: sorted(v) for k, v in ad_map.items()}

        # Map destinations
        url_map = _load_url_to_codes(verbose=False)
        
        # Resolve any unknown Wikipedia URLs (redirects)
        unresolved = [d[1] for d in destinations if len(d) >= 2 and d[1] not in url_map]
        if unresolved:
            import urllib.parse
            headers = {'User-Agent': 'wikipediaGATN/1.0 (julien.arino@example.com)'}
            for i in range(0, len(unresolved), 50):
                chunk = unresolved[i:i+50]
                titles = [urllib.parse.unquote(url.split('/wiki/')[-1]) for url in chunk]
                titles_str = "|".join(titles)
                try:
                    r = requests.get(f'https://en.wikipedia.org/w/api.php?action=query&titles={titles_str}&redirects=1&format=json', headers=headers, timeout=10)
                    if r.status_code == 200:
                        res_json = r.json()
                        if 'query' in res_json:
                            title_to_canonical = {t: t.replace('_', ' ') for t in titles}
                            if 'normalized' in res_json['query']:
                                for n in res_json['query']['normalized']:
                                    title_to_canonical[n['from']] = n['to']
                            if 'redirects' in res_json['query']:
                                for rd in res_json['query']['redirects']:
                                    for orig, norm in list(title_to_canonical.items()):
                                        if norm == rd['from']:
                                            title_to_canonical[orig] = rd['to']
                            
                            # Build reverse map: canonical -> original url
                            for orig_url, orig_title in zip(chunk, titles):
                                canonical_title = title_to_canonical.get(orig_title, orig_title)
                                canonical_url = f"https://en.wikipedia.org/wiki/{canonical_title.replace(' ', '_')}"
                                if canonical_url in url_map:
                                    # Copy the canonical codes to the original url so we map it correctly
                                    url_map[orig_url] = url_map[canonical_url]
                except Exception:
                    pass

        mapped_destinations = []
        for dest in destinations:
            if isinstance(dest, dict):
                mapped_destinations.append(dest)
            elif isinstance(dest, (list, tuple)) and len(dest) >= 2:
                city, d_url = dest[0], dest[1]
                codes = url_map.get(d_url, {"iata": "iata code not found", "icao": "icao code not found"})
                
                op_airlines = []
                for al_name, cities in airlines_destinations.items():
                    if city in cities:
                        op_airlines.append(al_name)
                        
                mapped_destinations.append({
                    "city": city,
                    "wikipedia_url": d_url,
                    "codes": [codes["iata"], codes["icao"]],
                    "airlines": sorted(op_airlines)
                })
            else:
                mapped_destinations.append(dest)
                
        # Update the dictionary
        from datetime import datetime, timezone
        data["airlines"] = airlines
        data["destinations"] = mapped_destinations
        data["airlines_destinations"] = airlines_destinations
        data["number_airlines"] = len(airlines)
        data["outdegree"] = len(mapped_destinations)
        data["date-time-parse"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if dt_wikidata:
            data["date-time-wikidata"] = dt_wikidata
            
    # Always ensure timestamps are at the end
    if "date-time-parse" in data:
        dt_p = data.pop("date-time-parse")
        data["date-time-parse"] = dt_p
    if "date-time-wikidata" in data:
        dt_w = data.pop("date-time-wikidata")
        data["date-time-wikidata"] = dt_w
        
    with open(fpath, "w", encoding="utf-8") as out_fh:
        json.dump(data, out_fh, indent=2, ensure_ascii=False)
        
    print(f"  ✓ Refreshed {data.get('iata', os.path.basename(fpath))} ({len(data.get('destinations', []))} destinations)")
    return True


def refresh_airports(target: Union[str, list[str]] = "all", refresh_all_data: bool = False, verbose: bool = True):
    """
    Refresh JSON files in data/public/airport_data based on Wikipedia edit timestamps.
    
    Parameters
    ----------
    target : str or list[str]
        Can be "all" to check all files, a single file path, or a list of file paths.
    refresh_all_data : bool
        If False, only updates airlines and destinations. If True, re-fetches everything.
    verbose : bool
        Print progress.
    """
    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    if not os.path.isdir(airport_data_dir):
        print(f"Directory not found: {airport_data_dir}")
        return
        
    files_to_check = []
    
    if target == "all":
        for fname in os.listdir(airport_data_dir):
            if fname.endswith(".json"):
                files_to_check.append(os.path.join(airport_data_dir, fname))
    elif isinstance(target, str):
        files_to_check = [target]
    elif isinstance(target, list):
        files_to_check = target
        
    if not files_to_check:
        print("No files to check.")
        return
        
    if verbose:
        print(f"\nChecking {len(files_to_check)} files for Wikipedia updates...")
        
    files_to_refresh = check_needs_refresh(files_to_check, verbose=verbose)
    
    if not files_to_refresh:
        print("✓ All files are up to date! No refreshing needed.")
        return
        
    if verbose:
        print(f"\nFound {len(files_to_refresh)} files that need refreshing.")
        
    success_count = 0
    for fpath in files_to_refresh:
        if refresh_airport_file(fpath, refresh_all_data=refresh_all_data, verbose=verbose):
            success_count += 1
            
    print(f"\nRefresh complete. Successfully updated {success_count}/{len(files_to_refresh)} files.")

if __name__ == "__main__":
    refresh_airports(target="all", refresh_all_data=False, verbose=True)
