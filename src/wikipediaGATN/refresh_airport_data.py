"""
Incremental updater for airport JSON data.

This module provides tools to refresh existing airport JSON data files without
needing to scrape everything from scratch. It utilizes the Wikipedia API to check
the 'last modified' timestamps of Wikipedia pages and compares them against the
local parse times. Only airports whose Wikipedia pages have been updated since 
they were last parsed are fetched again.

It also supports partial refreshes (only updating airlines and destinations) and
local-only migrations (applying geographic inference without network calls).

Typical usage:
    python -m wikipediaGATN.refresh_airport_data --target all --local-only
    python -m wikipediaGATN.refresh_airport_data --target all
"""

import json
import os
import requests
import time
import urllib.parse
from typing import Union

from dateutil import parser as dt_parser

from .paths import PUBLIC_DATA_DIR
from .airport_level_functions import (
    fetch_wikipedia_airport_wikitext,
    fetch_wikipedia_airport_html,
    parse_wikitext_airlines_destinations,
    fetch_wikipedia_airlines_destinations,
    fetch_wikipedia_airport_info,
    format_airport_json,
    build_url_to_codes_map,
    format_destinations_list,
    infer_missing_geographic_data,
    _SESSION,
    _API_URL
)




def check_needs_refresh(file_paths: list[str], verbose: bool = False) -> list[str]:
    """
    Filter a list of JSON files to find those that need to be refreshed.
    
    This function compares the local ``date-time-parse`` timestamp stored in each
    JSON file against the latest revision timestamp from the Wikipedia API. It 
    batches Wikipedia API requests (up to 50 titles per query) for efficiency.

    Parameters
    ----------
    file_paths : list of str
        List of absolute file paths to the airport JSON files.
    verbose : bool, optional
        If True, prints progress and details about which files need updates.
        Default is False.

    Returns
    -------
    list of str
        A subset of ``file_paths`` containing only the files that have either:
        1. Been updated on Wikipedia since they were last scraped.
        2. Are missing a ``date-time-parse`` field and therefore must be repaired.
        3. Encountered a parsing or decode error.
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


def refresh_airport_file(fpath: str, refresh_all_data: bool = False, local_only: bool = False, verbose: bool = False, file_idx: int = None, total_files: int = None, url_map: dict = None, start_time: float = None) -> bool:
    """
    Refresh a single airport JSON file.
    
    Depending on the flags provided, this function can perform a full web scrape,
    a partial web scrape (only destinations), or a purely offline data migration.

    Parameters
    ----------
    fpath : str
        Absolute path to the airport JSON file to refresh.
    refresh_all_data : bool, optional
        If True, re-fetches all metadata (infobox) from Wikipedia. If False,
        only re-fetches the airlines and destinations. Default is False.
    local_only : bool, optional
        If True, skips Wikipedia web scraping completely and purely applies 
        the latest formatting, data schema migrations, and geographic inferences
        using the offline OurAirports database. Default is False.
    verbose : bool, optional
        If True, prints detailed progress output. Default is False.
    file_idx : int, optional
        Current index in a batch (for logging ETA).
    total_files : int, optional
        Total number of files in the batch (for logging ETA).
    url_map : dict, optional
        A pre-computed mapping from Wikipedia URLs to IATA/ICAO codes. If not
        provided, it will be built dynamically.
    start_time : float, optional
        The Unix timestamp when the batch started (for logging ETA).

    Returns
    -------
    bool
        True if the file was successfully loaded, updated, and saved. False otherwise.
    """
    if verbose:
        progress_str = f" [{file_idx}/{total_files}]" if file_idx is not None and total_files is not None else ""
        time_str = ""
        if start_time is not None and file_idx is not None and total_files is not None and file_idx > 1:
            elapsed = time.time() - start_time
            avg_time = elapsed / (file_idx - 1)
            eta = avg_time * (total_files - file_idx + 1)
            time_str = f" (elapsed: {int(elapsed)}s, ETA: {int(eta)}s)"
            
        print(f"\nRefreshing {os.path.basename(fpath)}{progress_str}{time_str}...")
        
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
        
    if local_only:
        # Just update geographic info and destination schemas locally
        data = infer_missing_geographic_data(data)
        if url_map is None:
            url_map = build_url_to_codes_map(verbose=False)
        mapped_destinations = format_destinations_list(data.get("destinations", []), data.get("airlines_destinations", {}), url_map)
        if len(mapped_destinations) == 0:
            data["airlines_destinations"] = {}
            data["airlines"] = []
            
        data["destinations"] = mapped_destinations
        data["outdegree"] = len(mapped_destinations)
        data["number_airlines"] = len(data.get("airlines", []))
        
        # Migrate old legacy schema keys
        if "region" in data:
            if "admin1_name" not in data:
                data["admin1_name"] = data["region"]
            del data["region"]
        if "subdivision_code" in data:
            if "admin1_code" not in data:
                data["admin1_code"] = data["subdivision_code"]
            del data["subdivision_code"]
            
    elif refresh_all_data:
        # Re-fetch EVERYTHING
        new_data = fetch_wikipedia_airport_info(link=url, verbose=verbose)
        
        if url_map is None:
            url_map = build_url_to_codes_map(verbose=False)
            
        mapped_destinations = format_destinations_list(new_data.get("destinations", []), new_data.get("airlines_destinations", {}), url_map)
        mapped_destinations_cargo = format_destinations_list(new_data.get("destinations_cargo", []), new_data.get("airlines_destinations_cargo", {}), url_map)
                
        if len(mapped_destinations) == 0:
            new_data["airlines_destinations"] = {}
            new_data["airlines"] = []
            
        if len(mapped_destinations_cargo) == 0:
            new_data["airlines_destinations_cargo"] = {}
            new_data["airlines_cargo"] = []
            
        new_data["destinations"] = mapped_destinations
        new_data["outdegree"] = len(mapped_destinations)
        new_data["number_airlines"] = len(new_data.get("airlines", []))
        
        new_data["destinations_cargo"] = mapped_destinations_cargo
        new_data["outdegree_cargo"] = len(mapped_destinations_cargo)
        new_data["number_airlines_cargo"] = len(new_data.get("airlines_cargo", []))
        
        # Migrate old legacy schema keys if they exist in the existing data
        if "region" in data:
            if "admin1_name" not in data:
                data["admin1_name"] = data["region"]
            del data["region"]
        if "subdivision_code" in data:
            if "admin1_code" not in data:
                data["admin1_code"] = data["subdivision_code"]
            del data["subdivision_code"]
            
        # We must NOT lose the country/lat/lon if they were inferred manually in result_processing_airports!
        # So we merge `new_data` INTO `data` to prefer the new parsed stuff, but keep old geocoding if missing.
        for key in ["lat", "lon", "country_alpha3", "country_name", "location", "admin1_name", "admin1_code", "admin2_name", "continent"]:
            if not new_data.get(key) and data.get(key):
                new_data[key] = data[key]
                
        new_data = infer_missing_geographic_data(new_data)
        
        data = new_data
    else:
        # Partial refresh: only airlines and destinations
        wikitext, dt_wikidata = fetch_wikipedia_airport_wikitext(link=url, verbose=verbose)
        
        if not wikitext:
            print(f"  ✗ Failed to fetch wikitext for {url}")
            return False
            
        ad_map_wikitext = parse_wikitext_airlines_destinations(wikitext)
        
        # Intelligent HTML Fallback
        html_content = None
        if not ad_map_wikitext['passenger'] and ad_map_wikitext['cargo']:
            html_content = fetch_wikipedia_airport_html(link=url, verbose=verbose)
            ad_map_html = fetch_wikipedia_airlines_destinations(
                link=url, html_content=html_content, verbose=verbose, soup=None)
            if ad_map_html['passenger']:
                ad_map_wikitext['passenger'] = ad_map_html['passenger']

        if not ad_map_wikitext['passenger'] and not ad_map_wikitext['cargo']:
            if not html_content:
                html_content = fetch_wikipedia_airport_html(link=url, verbose=verbose)
            ad_map = fetch_wikipedia_airlines_destinations(link=url, html_content=html_content, verbose=verbose)
        else:
            ad_map = ad_map_wikitext
            
        # Passenger data
        airlines = sorted(ad_map['passenger'].keys())
        destinations = sorted({
            (d["name"], d["wikipedia_url"]) if isinstance(d, dict) else d
            for dests in ad_map['passenger'].values()
            for d in dests
        })
        airlines_destinations = {
            airline: sorted({d["name"] if isinstance(d, dict) else d for d in dests})
            for airline, dests in ad_map['passenger'].items()
        }
        
        # Cargo data
        airlines_cargo = sorted(ad_map['cargo'].keys())
        destinations_cargo = sorted({
            (d["name"], d["wikipedia_url"]) if isinstance(d, dict) else d
            for dests in ad_map['cargo'].values()
            for d in dests
        })
        airlines_destinations_cargo = {
            airline: sorted({d["name"] if isinstance(d, dict) else d for d in dests})
            for airline, dests in ad_map['cargo'].items()
        }

        # Map destinations
        if url_map is None:
            url_map = build_url_to_codes_map(verbose=False)
        
        # Resolve any unknown Wikipedia URLs (redirects)
        all_dests = destinations + destinations_cargo
        unresolved = [d[1] for d in all_dests if len(d) >= 2 and d[1] not in url_map]
        if unresolved:
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

        mapped_destinations = format_destinations_list(destinations, airlines_destinations, url_map)
        mapped_destinations_cargo = format_destinations_list(destinations_cargo, airlines_destinations_cargo, url_map)
                
        if len(mapped_destinations) == 0:
            airlines_destinations = {}
            airlines = []
            
        if len(mapped_destinations_cargo) == 0:
            airlines_destinations_cargo = {}
            airlines_cargo = []
            
        # Update the dictionary
        from datetime import datetime, timezone
        data["airlines"] = airlines
        data["destinations"] = mapped_destinations
        data["airlines_destinations"] = airlines_destinations
        data["number_airlines"] = len(airlines)
        data["outdegree"] = len(mapped_destinations)
        
        data["airlines_cargo"] = airlines_cargo
        data["destinations_cargo"] = mapped_destinations_cargo
        data["airlines_destinations_cargo"] = airlines_destinations_cargo
        data["number_airlines_cargo"] = len(airlines_cargo)
        data["outdegree_cargo"] = len(mapped_destinations_cargo)
        data["date-time-parse"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if dt_wikidata:
            data["date-time-wikidata"] = dt_wikidata
            
    # Format JSON order before saving
    data = format_airport_json(data)
    
    with open(fpath, "w", encoding="utf-8") as out_fh:
        json.dump(data, out_fh, indent=2, ensure_ascii=False)
        
    print(f"  ✓ Refreshed {data.get('iata', os.path.basename(fpath))}")
    return True


def refresh_airports(target: Union[str, list[str]] = "all", refresh_all_data: bool = False, local_only: bool = False, force: bool = False, verbose: bool = True):
    """
    Orchestrate the batch refresh of airport JSON files.
    
    Scans the ``PUBLIC_DATA_DIR/airport_data`` directory, determines which files
    require an update (via Wikipedia API timestamps), and refreshes them.

    Parameters
    ----------
    target : str or list of str, optional
        Can be "all" to check all files in the directory, a single file path, 
        or a list of specific file paths. Default is "all".
    refresh_all_data : bool, optional
        If True, re-fetches all metadata (infobox). If False, only updates 
        airlines and destinations. Default is False.
    local_only : bool, optional
        If True, skips Wikipedia timestamp checks and scraping, and only applies
        local geographic inferences and schema migrations. Default is False.
    force : bool, optional
        If True, skips the Wikipedia timestamp check and forces a refresh on 
        all targeted files. Default is False.
    verbose : bool, optional
        If True, prints detailed progress and ETA. Default is True.
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
        print(f"\nChecking {len(files_to_check)} files...")
        
    if force or local_only:
        if verbose and force:
            print("Force flag is set. Skipping Wikipedia timestamp checks.")
        elif verbose and local_only:
            print("Local-only flag is set. Skipping Wikipedia timestamp checks.")
        files_to_refresh = files_to_check
    else:
        files_to_refresh = check_needs_refresh(files_to_check, verbose=verbose)
    
    if not files_to_refresh:
        print("✓ All files are up to date! No refreshing needed.")
        return
        
    if verbose:
        print(f"\nFound {len(files_to_refresh)} files that need refreshing.")
        
    files_to_refresh.sort()
    
    if verbose:
        print("\nPre-computing global Wikipedia URL to IATA/ICAO code map...")
    global_url_map = build_url_to_codes_map(verbose=False)
    
    success_count = 0
    total_files = len(files_to_refresh)
    start_time = time.time()
    for idx, fpath in enumerate(files_to_refresh, 1):
        if refresh_airport_file(fpath, refresh_all_data=refresh_all_data, local_only=local_only, verbose=verbose, file_idx=idx, total_files=total_files, url_map=global_url_map, start_time=start_time):
            success_count += 1
            
    print(f"\nRefresh complete. Successfully updated {success_count}/{len(files_to_refresh)} files.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Refresh airport JSON data from Wikipedia.")
    parser.add_argument("--target", type=str, nargs="+", default="all",
                        help="Target 'all' or specific JSON file paths.")
    parser.add_argument("--all-data", action="store_true",
                        help="Refresh all metadata (infobox), not just destinations/airlines.")
    parser.add_argument("--local-only", action="store_true",
                        help="Offline refresh to update formatting and infer missing geography.")
    parser.add_argument("--force", action="store_true",
                        help="Force refresh even if Wikipedia page hasn't been updated.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress verbose output.")
    
    args = parser.parse_args()
    
    # If target is a list of length 1 and equals "all", normalize it
    if isinstance(args.target, list) and len(args.target) == 1 and args.target[0] == "all":
        args.target = "all"
        
    refresh_airports(
        target=args.target,
        refresh_all_data=args.all_data,
        local_only=args.local_only,
        force=args.force,
        verbose=not args.quiet
    )
