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
from .airport_level_functions import (
    parse_iso3166_2,
    format_airport_json,
    build_url_to_codes_map,
    infer_missing_geographic_data,
    format_destinations_list
)

logger = logging.getLogger(__name__)

# Matches both IATA-style (e.g. YWG.0.json) and wiki-prefixed
# (e.g. wiki_Winnipeg.1.json) filenames produced by the scraper.
_FNAME_RE = re.compile(r"^([A-Z]{3,4}|wiki_[A-Za-z0-9_]+)\.\d+\.json$")


###############################################################################
# AIRPORT DATA EXTRACTION
###############################################################################

def export_all_airport_data(use_new_data: bool = False, verbose: bool = False) -> str:
    """
    Extract metadata from all airport JSON files and write to CSV.

    Scans every ``<IATA>.<distance>.json`` and ``wiki_*.<distance>.json`` file
    in ``PUBLIC_DATA_DIR/airport_data`` (or ``TEMP_RESULTS_DIR`` if use_new_data is True)
    and collects airport metadata into a single ``airports_information.csv``.

    Parameters
    ----------
    use_new_data : bool, optional
        If True, reads from ``TEMP_RESULTS_DIR``. Default: False (reads from ``PUBLIC_DATA_DIR/airport_data``).
    verbose : bool, optional
        If True, prints per-file status and a final summary.  Default: False.

    Returns
    -------
    str
        Absolute path to ``data/public/airports_information.csv``.

    Raises
    ------
    FileNotFoundError
        If the selected directory does not exist.

    Notes
    -----
    * ``outdegree`` is the number of destination airports listed for each
      airport in its JSON file, not the verified network degree.
    * Fields absent from the JSON file are written as empty strings.
    * Run this function before
      :func:`~.connections.create_outbound_connections_list` so that
      ``airports_information.csv`` is available for URL→IATA mapping.
    """
    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    
    if use_new_data:
        scan_dir = TEMP_RESULTS_DIR
    else:
        scan_dir = airport_data_dir
        
    if not os.path.isdir(scan_dir):
        raise FileNotFoundError(f"Directory not found: {scan_dir}")

    # 1. Pre-computation pass: Build url_to_codes mapping
    url_to_codes = build_url_to_codes_map(verbose=verbose)

    # Scan all JSON files in the chosen directory
    valid_files = []
    for fname in sorted(os.listdir(scan_dir)):
        m = _FNAME_RE.match(fname)
        if m:
            valid_files.append((fname, m.group(1)))
        elif fname.endswith(".json"):
            valid_files.append((fname, fname[:-5]))

    rows = []
    skipped = 0

    os.makedirs(airport_data_dir, exist_ok=True)
    
    geolocator = Nominatim(user_agent="wikipediaGATN/1.0")

    for fname, identifier in valid_files:
        fpath = os.path.join(scan_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            warnings.warn(f"Skipping {fname}: cannot read/parse — {exc}", UserWarning, stacklevel=2)
            skipped += 1
            continue

        # --- VALIDATION & CONSOLIDATION ---
        
        # Geopy fallback and offline geographic inference
        data = infer_missing_geographic_data(data)

        # 1. City-Served Split
        city_served = data.get("city-served")
        if not city_served:
            city_served = data.get("location") or data.get("name") or ""
        city_served_wiki = ""
        if city_served and "[[" in city_served:
            city_served_wiki = city_served
            text_match = re.search(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', city_served)
            if text_match:
                city_served = text_match.group(1)
        else:
            if "city-served" in data and data.get("city-served"):
                city_served_wiki = data.get("city-served")
            elif city_served:
                city_served_wiki = city_served

        new_data = {}
        for k, v in data.items():
            if k == "city-served":
                new_data["city-served"] = city_served
                new_data["city-served-wikipedia"] = city_served_wiki
                continue
            
            if k == "airlines":
                new_data["number_airlines"] = len(data.get("airlines", []))
                new_data["outdegree"] = len(data.get("destinations", []))
                
            if k == "airlines_cargo":
                new_data["number_airlines_cargo"] = len(data.get("airlines_cargo", []))
                new_data["outdegree_cargo"] = len(data.get("destinations_cargo", []))
            
            if k == "destinations":
                if "number_airlines" not in new_data:
                    new_data["number_airlines"] = len(data.get("airlines", []))
                    new_data["outdegree"] = len(data.get("destinations", []))
                
                ad_map = data.get("airlines_destinations", {})
                v = format_destinations_list(data.get("destinations", []), ad_map, url_to_codes)
                
            if k == "destinations_cargo":
                if "number_airlines_cargo" not in new_data:
                    new_data["number_airlines_cargo"] = len(data.get("airlines_cargo", []))
                    new_data["outdegree_cargo"] = len(data.get("destinations_cargo", []))
                
                ad_map_c = data.get("airlines_destinations_cargo", {})
                v = format_destinations_list(data.get("destinations_cargo", []), ad_map_c, url_to_codes)
                
            new_data[k] = v
            
        if "number_airlines" not in new_data:
            new_data["number_airlines"] = len(data.get("airlines", []))
            new_data["outdegree"] = len(data.get("destinations", []))
            
        if "number_airlines_cargo" not in new_data:
            new_data["number_airlines_cargo"] = len(data.get("airlines_cargo", []))
            new_data["outdegree_cargo"] = len(data.get("destinations_cargo", []))

        # Ensure timestamps are at the end
        if "date-time-parse" in new_data:
            dt_p = new_data.pop("date-time-parse")
            new_data["date-time-parse"] = dt_p
        if "date-time-wikidata" in new_data:
            dt_w = new_data.pop("date-time-wikidata")
            new_data["date-time-wikidata"] = dt_w

        # --- END VALIDATION & CONSOLIDATION ---

        rows.append({
            "iata":          new_data.get("iata",         ""),
            "icao":          new_data.get("icao",         ""),
            "latitude":      new_data.get("lat") or new_data.get("latitude", ""),
            "longitude":     new_data.get("lon") or new_data.get("longitude", ""),
            "name":          new_data.get("name") or new_data.get("serves", ""),
            "wikipedia_url": new_data.get("wikipedia_url", ""),
            "outdegree":     new_data.get("outdegree", 0),
            "outdegree_cargo": new_data.get("outdegree_cargo", 0),
        })

        # Apply formatting constraints
        new_data = format_airport_json(new_data)

        # Save to public/airport_data
        public_json_path = os.path.join(airport_data_dir, f"{identifier}.json")
        with open(public_json_path, "w", encoding="utf-8") as out_fh:
            json.dump(new_data, out_fh, indent=2, ensure_ascii=False)

    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    output_csv = os.path.join(PUBLIC_DATA_DIR, "airports_information.csv")

    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = [
            "iata", "icao", "latitude", "longitude",
            "name", "wikipedia_url", "outdegree", "outdegree_cargo"
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


def identify_missing_airport_data(verbose: bool = False) -> str:
    """
    Identify airports with missing geographical data.

    Scans all JSON files in ``data/public/airport_data`` and writes a CSV
    to ``data/tmp_results/missing_airport_data.csv`` listing airports that
    lack latitude, longitude, or country information.

    Parameters
    ----------
    verbose : bool, optional
        If True, prints a summary of the missing data. Default: False.

    Returns
    -------
    str
        Absolute path to the generated CSV file.
    """
    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    if not os.path.isdir(airport_data_dir):
        if verbose:
            print(f"Directory not found: {airport_data_dir}")
        return ""

    os.makedirs(TEMP_RESULTS_DIR, exist_ok=True)
    output_csv = os.path.join(TEMP_RESULTS_DIR, "missing_airport_data.csv")
    
    missing_records = []
    
    for fname in sorted(os.listdir(airport_data_dir)):
        if not fname.endswith(".json"):
            continue
            
        fpath = os.path.join(airport_data_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
            
        lat = data.get("lat")
        lon = data.get("lon")
        country = data.get("country_alpha3")
        
        is_missing_latlon = lat is None or lon is None or lat == "" or lon == ""
        is_missing_country = country is None or country == ""
        
        if is_missing_latlon or is_missing_country:
            missing_records.append({
                "iata": data.get("iata", ""),
                "icao": data.get("icao", ""),
                "name": data.get("name") or data.get("city-served", ""),
                "missing_latlon": is_missing_latlon,
                "missing_country": is_missing_country,
                "wikipedia_url": data.get("wikipedia_url", "")
            })
            
    with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["iata", "icao", "name", "missing_latlon", "missing_country", "wikipedia_url"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(missing_records)
        
    if verbose:
        print(f"Found {len(missing_records)} airports with missing data.")
        print(f"Missing data report saved to: {output_csv}")
        
    return output_csv


def enrich_missing_airport_data(verbose: bool = False) -> int:
    """
    Attempt a second round of geocoding for airports with missing data.
    
    Reads data/tmp_results/missing_airport_data.csv, attempts multiple
    queries with Geopy to find lat/lon, and reverse geocodes to find the country.
    Updates the JSON files in data/public/airport_data in place.
    
    Parameters
    ----------
    verbose : bool, optional
        If True, prints progress and success/failure for each missing airport.
        
    Returns
    -------
    int
        The number of airports successfully updated.
    """
    input_csv = os.path.join(TEMP_RESULTS_DIR, "missing_airport_data.csv")
    if not os.path.isfile(input_csv):
        if verbose:
            print(f"Missing data CSV not found: {input_csv}")
        return 0
        
    airport_data_dir = os.path.join(PUBLIC_DATA_DIR, "airport_data")
    geolocator = Nominatim(user_agent="wikipediaGATN/2.0")
    
    fixed_count = 0
    
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing_airports = list(reader)
        
    for row in missing_airports:
        iata = row.get("iata") or row.get("name")
        if not iata:
            continue
            
        json_path = os.path.join(airport_data_dir, f"{iata}.json")
        # Fallback to checking by identifier if iata is missing or different
        if not os.path.isfile(json_path) and row.get("wikipedia_url"):
             identifier = urllib.parse.unquote(row.get("wikipedia_url", "").split("/")[-1].replace("_", " "))
             # try iata, try identifier... Wait, in result_processing_airports the filenames are exactly `identifier`.
             # The scraper makes files like `<IATA>.json` generally.
             pass # just try iata for now, it's safer
             
        if not os.path.isfile(json_path):
            # Sometimes the identifier is not the IATA code if it's missing.
            # Let's search the directory for a matching wikipedia_url
            for fname in os.listdir(airport_data_dir):
                if fname.endswith(".json"):
                    with open(os.path.join(airport_data_dir, fname), "r", encoding="utf-8") as jf:
                        try:
                            d = json.load(jf)
                            if d.get("wikipedia_url") == row.get("wikipedia_url"):
                                json_path = os.path.join(airport_data_dir, fname)
                                iata = fname.replace(".json", "")
                                break
                        except Exception:
                            pass
            
        if not os.path.isfile(json_path):
            if verbose: print(f"Could not find JSON file for {row.get('iata')} or {row.get('wikipedia_url')}")
            continue
            
        with open(json_path, "r", encoding="utf-8") as jf:
            try:
                data = json.load(jf)
            except json.JSONDecodeError:
                continue
                
        lat = data.get("lat")
        lon = data.get("lon")
        
        # 1. Dig out Lat/Lon if missing
        if not lat or not lon:
            queries = []
            if data.get("iata"): queries.append(f'{data.get("iata")} airport')
            if data.get("name"): queries.append(f'{data.get("name")} airport')
            
            # Wikipedia title
            title = urllib.parse.unquote(data.get("wikipedia_url", "").split("/")[-1].replace("_", " "))
            if title: queries.append(title)
                
            if data.get("city-served"): queries.append(f'{data.get("city-served")} airport')
            if data.get("location"): queries.append(data.get("location"))
            if data.get("icao"): queries.append(f'{data.get("icao")} airport')
            
            for query in queries:
                if not query.strip(): continue
                try:
                    time.sleep(1.5) # Be nice to Nominatim (max 1 req/s)
                    loc = geolocator.geocode(query, timeout=5)
                    if loc:
                        lat, lon = str(loc.latitude), str(loc.longitude)
                        data["lat"], data["lon"] = lat, lon
                        if verbose: print(f"[{iata}] Found coordinates via query: '{query}'")
                        break
                except Exception:
                    pass
                    
        # 2. Dig out Country if missing (needs lat/lon)
        country = data.get("country_alpha3")
        if (not country or country == "") and lat and lon:
            try:
                float(lat)
                float(lon)
                res = rg.search((lat, lon), mode=1)
                if res:
                    loc_info = res[0]
                    cc = loc_info.get("cc")
                    if cc:
                        country_obj = pycountry.countries.get(alpha_2=cc)
                        if country_obj:
                            data["country_alpha3"] = country_obj.alpha_3
                            data["country_name"] = country_obj.name
                            if not data.get("location"): data["location"] = loc_info.get("name")
                            if not data.get("region"): data["region"] = loc_info.get("admin1")
                            if not data.get("subdivision_code"): data["subdivision_code"] = loc_info.get("admin2")
                            
                            # Add continent
                            try:
                                continent_code = pc.country_alpha2_to_continent_code(cc)
                                data["continent"] = pc.convert_continent_code_to_continent_name(continent_code)
                            except Exception:
                                pass
                            if verbose: print(f"[{iata}] Found country: {country_obj.name}")
            except Exception:
                pass
                
        # Did we fix something?
        new_lat = data.get("lat")
        new_lon = data.get("lon")
        new_country = data.get("country_alpha3")
        
        fixed_latlon = (new_lat and new_lon) and (row["missing_latlon"] == "True")
        fixed_country = (new_country) and (row["missing_country"] == "True")
        
        if fixed_latlon or fixed_country:
            fixed_count += 1
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(data, jf, indent=2, ensure_ascii=False)
                
    if verbose:
        print(f"Enrichment complete. Successfully updated {fixed_count} airports.")
        
    return fixed_count


__all__ = [
    "export_all_airport_data",
    "check_duplicated_iata_codes",
    "identify_missing_airport_data",
    "enrich_missing_airport_data",
]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compile airport JSONs into airports_information.csv")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    parser.add_argument("--use-new-data", action="store_true", help="Read from TEMP_RESULTS_DIR instead of public data")
    args = parser.parse_args()
    
    export_all_airport_data(use_new_data=args.use_new_data, verbose=not args.quiet)
