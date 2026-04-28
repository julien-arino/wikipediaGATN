"""
Airport data extraction and validation.

This module transforms raw airport JSON files (produced by Wikipedia scraping)
into structured airport metadata, and deduplicates scraping results.
"""

import csv
import datetime
import json
import logging
import os
import re
import shutil
import time
import urllib.parse
import warnings

import pycountry
import pycountry_convert as pc
import requests
import reverse_geocoder as rg
from geopy.geocoders import Nominatim

from .paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR

logger = logging.getLogger(__name__)

# Matches both IATA-style (e.g. YWG.0.json) and wiki-prefixed
# (e.g. wiki_Winnipeg.1.json) filenames produced by the scraper.
_FNAME_RE = re.compile(r"^([A-Z]{3,4}|wiki_[A-Za-z0-9_]+)\.\d+\.json$")


###############################################################################
# AIRPORT DATA EXTRACTION
###############################################################################

def export_all_airport_data(verbose: bool = False) -> str:
    """
    Extract metadata from all airport JSON files and write to CSV.

    Scans every ``<IATA>.<distance>.json`` and ``wiki_*.<distance>.json`` file
    in ``TEMP_RESULTS_DIR`` and collects airport metadata into a single
    ``airports_information.csv``.

    Parameters
    ----------
    verbose : bool, optional
        If True, prints per-file status and a final summary.  Default: False.

    Returns
    -------
    str
        Absolute path to ``data/public/airports_information.csv``.

    Raises
    ------
    FileNotFoundError
        If ``TEMP_RESULTS_DIR`` does not exist.

    Notes
    -----
    * ``outdegree`` is the number of destination airports listed for each
      airport in its JSON file, not the verified network degree.
    * Fields absent from the JSON file are written as empty strings.
    * Run this function before
      :func:`~.connections.create_outbound_connections_list` so that
      ``airports_information.csv`` is available for URL→IATA mapping.
    """
    if not os.path.isdir(TEMP_RESULTS_DIR):
        raise FileNotFoundError(
            f"Temporary results directory not found: {TEMP_RESULTS_DIR}\n"
            "Run the Wikipedia scraping step first."
        )

    # 1. Pre-computation pass: Build url_to_codes mapping
    url_to_codes = {}
    
    # Also load processed_locations.csv if it exists to get any extra IATA mappings
    processed_csv_path = os.path.join(TEMP_RESULTS_DIR, "processed_locations.csv")
    if os.path.exists(processed_csv_path):
        with open(processed_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") and row.get("iata"):
                    url_to_codes[row["url"]] = {"iata": row["iata"], "icao": "icao code not found"}
                    
    # Also load manual_airport_mapping.csv for any manually scraped overrides
    manual_csv_path = os.path.join(TEMP_RESULTS_DIR, "manual_airport_mapping.csv")
    if os.path.exists(manual_csv_path):
        with open(manual_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url") and row.get("iata"):
                    url_to_codes[row["url"]] = {"iata": row["iata"], "icao": "icao code not found"}

    # Scan all JSON files in TEMP_RESULTS_DIR to build the map
    valid_files = []
    all_destinations = set()
    for fname in sorted(os.listdir(TEMP_RESULTS_DIR)):
        m = _FNAME_RE.match(fname)
        if not m:
            continue
        valid_files.append((fname, m.group(1)))
        
        fpath = os.path.join(TEMP_RESULTS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if "wikipedia_url" in data:
                    url_to_codes[data["wikipedia_url"]] = {
                        "iata": data.get("iata", "iata code not found") or "iata code not found",
                        "icao": data.get("icao", "icao code not found") or "icao code not found"
                    }
                for dest in data.get("destinations", []):
                    if len(dest) >= 2:
                        all_destinations.add(dest[1])
        except (json.JSONDecodeError, OSError):
            continue

    # Bulk resolve Wikipedia redirects for both known URLs and unresolved destinations
    unresolved_urls = [url for url in all_destinations if url not in url_to_codes]
    urls_to_resolve = list(url_to_codes.keys()) + unresolved_urls
    
    if verbose:
        print(f"Resolving canonical titles for {len(urls_to_resolve)} URLs via Wikipedia API...")
    
    headers = {'User-Agent': 'wikipediaGATN/1.0 (julien.arino@example.com)'}
    for i in range(0, len(urls_to_resolve), 50):
        chunk = urls_to_resolve[i:i+50]
        titles = [urllib.parse.unquote(url.split('/wiki/')[-1]) for url in chunk]
        titles_str = "|".join(titles)
        try:
            r = requests.get(f'https://en.wikipedia.org/w/api.php?action=query&titles={titles_str}&redirects=1&format=json', headers=headers)
            if r.status_code != 200:
                if verbose: print(f"Wikipedia API error {r.status_code}: {r.text[:100]}")
                time.sleep(2)
                continue
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
                
                # If chunk URL was in url_to_codes, propagate its code to canonical
                # If chunk URL was an unresolved destination, see if its canonical is in url_to_codes
                for url, orig_title in zip(chunk, titles):
                    canonical = title_to_canonical.get(orig_title)
                    if canonical:
                        canonical_url = f"https://en.wikipedia.org/wiki/{canonical.replace(' ', '_')}"
                        if url in url_to_codes:
                            url_to_codes[canonical_url] = url_to_codes[url]
                        elif canonical_url in url_to_codes:
                            url_to_codes[url] = url_to_codes[canonical_url]
        except Exception as exc:
            if verbose: print(f"Redirect resolution failed for a chunk: {exc}")
        time.sleep(0.1)

    rows = []
    skipped = 0

    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    os.makedirs(airport_data_dir, exist_ok=True)
    
    geolocator = Nominatim(user_agent="wikipediaGATN/1.0")

    for fname, identifier in valid_files:
        fpath = os.path.join(TEMP_RESULTS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            warnings.warn(f"Skipping {fname}: cannot read/parse — {exc}", UserWarning, stacklevel=2)
            skipped += 1
            continue

        # --- VALIDATION & CONSOLIDATION ---
        
        # Geopy fallback if missing lat/lon
        lat = data.get("lat") or data.get("latitude")
        lon = data.get("lon") or data.get("longitude")
        if not lat or not lon:
            try:
                title = urllib.parse.unquote(data.get("wikipedia_url", "").split("/")[-1].replace("_", " "))
                if title:
                    time.sleep(1) # Geopy Nominatim requires 1 sec sleep
                    loc = geolocator.geocode(title)
                    if loc:
                        lat, lon = str(loc.latitude), str(loc.longitude)
                        data["lat"], data["lon"] = lat, lon
            except Exception:
                pass
        
        # Check if we need to infer location data
        needs_inference = not all([
            data.get("location"), data.get("region"), data.get("country_alpha3"),
            data.get("country_name"), data.get("subdivision_code")
        ])
        
        inferred_country_cc = None
        
        if needs_inference and lat and lon:
            try:
                float(lat)
                float(lon)
                res = rg.search((lat, lon), mode=1)
                if res:
                    loc_info = res[0]
                    if not data.get("location"): data["location"] = loc_info.get("name")
                    if not data.get("region"): data["region"] = loc_info.get("admin1")
                    if not data.get("subdivision_code"): data["subdivision_code"] = loc_info.get("admin2")
                    
                    cc = loc_info.get("cc")
                    inferred_country_cc = cc
                    if cc and (not data.get("country_alpha3") or not data.get("country_name")):
                        country = pycountry.countries.get(alpha_2=cc)
                        if country:
                            if not data.get("country_alpha3"): data["country_alpha3"] = country.alpha_3
                            if not data.get("country_name"): data["country_name"] = country.name
            except ValueError:
                pass

        continent_name = ""
        alpha2 = inferred_country_cc
        if not alpha2 and data.get("country_alpha3"):
            country = pycountry.countries.get(alpha_3=data.get("country_alpha3"))
            if country:
                alpha2 = country.alpha_2
        if alpha2:
            try:
                continent_code = pc.country_alpha2_to_continent_code(alpha2)
                continent_name = pc.convert_continent_code_to_continent_name(continent_code)
            except Exception:
                pass

        # 1. City-Served Split
        city_served = data.get("city-served", "")
        city_served_wiki = ""
        if city_served and "[[" in city_served:
            city_served_wiki = city_served
            text_match = re.search(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', city_served)
            if text_match:
                city_served = text_match.group(1)
        else:
            if "city-served" in data:
                city_served_wiki = data.get("city-served")

        new_data = {}
        for k, v in data.items():
            if k == "city-served":
                new_data["city-served"] = city_served
                new_data["city-served-wikipedia"] = city_served_wiki
                continue
            
            if k == "altitude":
                new_data["altitude"] = v
                if continent_name:
                    new_data["continent"] = continent_name
                continue
                
            if k == "airlines":
                new_data["number_airlines"] = len(data.get("airlines", []))
                new_data["outdegree"] = len(data.get("destinations", []))
            
            if k == "destinations":
                if "number_airlines" not in new_data:
                    new_data["number_airlines"] = len(data.get("airlines", []))
                    new_data["outdegree"] = len(data.get("destinations", []))
                
                new_dests = []
                for dest in data.get("destinations", []):
                    if len(dest) >= 2:
                        city, url = dest[0], dest[1]
                        codes = url_to_codes.get(url, {"iata": "iata code not found", "icao": "icao code not found"})
                        new_dest = [city, url, codes["iata"], codes["icao"]]
                        new_dests.append(new_dest)
                    else:
                        new_dests.append(dest)
                v = new_dests
                
            new_data[k] = v
            
        if "number_airlines" not in new_data:
            new_data["number_airlines"] = len(data.get("airlines", []))
            new_data["outdegree"] = len(data.get("destinations", []))

        # --- END VALIDATION & CONSOLIDATION ---

        rows.append({
            "iata":          new_data.get("iata",         ""),
            "icao":          new_data.get("icao",         ""),
            "latitude":      new_data.get("lat") or new_data.get("latitude", ""),
            "longitude":     new_data.get("lon") or new_data.get("longitude", ""),
            "name":          new_data.get("name") or new_data.get("serves", ""),
            "wikipedia_url": new_data.get("wikipedia_url", ""),
            "outdegree":     new_data.get("outdegree", 0),
        })

        # Save to public/airport_data
        public_json_path = os.path.join(airport_data_dir, f"{identifier}.json")
        with open(public_json_path, "w", encoding="utf-8") as out_fh:
            json.dump(new_data, out_fh, indent=2, ensure_ascii=False)

    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")

    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = [
            "iata", "icao", "latitude", "longitude",
            "name", "wikipedia_url", "outdegree",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    if verbose:
        print(f"Exported {len(rows):,} airports to {os.path.abspath(output_csv)}")
        if skipped:
            print(f"Skipped {skipped} unreadable files (see warnings above)")

    readme_path = os.path.join(PUBLIC_DATA_DIR, "README.md")
    if os.path.exists(readme_path):
        today_str = datetime.date.today().isoformat()
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if "extracted on" in content:
            content = re.sub(r"\(extracted on \d{4}-\d{2}-\d{2}\)", f"(extracted on {today_str})", content)
        else:
            content = content.rstrip() + f"\n\nData extracted on {today_str}.\n"
            
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(content)

    return output_csv


###############################################################################
# DEDUPLICATION
###############################################################################

def check_duplicated_iata_codes(verbose: bool = False) -> int:
    """
    Remove duplicate airport JSON files, keeping the lowest-distance version.

    When the scraper revisits an airport at a greater distance from the seed
    (e.g. both ``YWG.0.json`` and ``YWG.1.json`` exist), the higher-distance
    file is deleted because the lower-distance file was scraped closer to the
    seed and is considered more accurate.

    Parameters
    ----------
    verbose : bool, optional
        If True, prints the name of each removed file.  Default: False.

    Returns
    -------
    int
        Number of duplicate files removed.

    Raises
    ------
    FileNotFoundError
        If ``TEMP_RESULTS_DIR`` does not exist.

    Notes
    -----
    This function **modifies the filesystem** by deleting files.  Run it after
    Wikipedia scraping is complete and before any processing steps.
    """
    if not os.path.isdir(TEMP_RESULTS_DIR):
        raise FileNotFoundError(
            f"Temporary results directory not found: {TEMP_RESULTS_DIR}\n"
            "Run the Wikipedia scraping step first."
        )

    pattern = re.compile(r"^([A-Z]{3})\.(\d+)\.json$")
    files_by_iata: dict = {}

    for fname in os.listdir(TEMP_RESULTS_DIR):
        m = pattern.match(fname)
        if m:
            iata  = m.group(1)
            level = int(m.group(2))
            files_by_iata.setdefault(iata, []).append((level, fname))

    removed = 0
    for iata, files in files_by_iata.items():
        if len(files) <= 1:
            continue

        files.sort()                                      # ascending by level
        to_remove = [fname for _, fname in files[1:]]    # keep files[0]

        for fname in to_remove:
            fpath = os.path.join(TEMP_RESULTS_DIR, fname)
            try:
                os.remove(fpath)
                removed += 1
                if verbose:
                    print(f"  Removed duplicate: {fname}")
            except OSError as exc:
                warnings.warn(
                    f"Could not remove {fname}: {exc}",
                    UserWarning, stacklevel=2,
                )

    if verbose:
        if removed:
            print(f"Removed {removed} duplicate file(s).")
        else:
            print("No duplicate IATA code files found.")

    return removed


__all__ = [
    "export_all_airport_data",
    "check_duplicated_iata_codes",
]
