# wikipediaGATN Scripts

This directory contains various utility and execution scripts used to build, fix, test, and manage the Global Air Transportation Networks (GATN) datasets.

## Pipeline and Execution Scripts

These scripts are used to drive the core Breadth-First Search (BFS) network crawling logic over Wikipedia:

* **`run_get_next_level.py`**: Automatically determines the current maximum BFS level in `tmp_results` and triggers a crawl for the next level.
* **`run_catchup_one_level.py`**: Resumes an interrupted BFS network crawl, expanding the frontier by exactly one level.
* **`run_catchup_to_end.py`**: Resumes an interrupted BFS network crawl and continues automatically until the queue is completely empty.

## Missing Airport and Metadata Resolution

These scripts are part of the pipeline to resolve destinations that lack metadata or are missing from the `OurAirports` database:

* **`scrape_missing_airports.py`**: Orchestrates the scraping of airports that were listed as destinations but were missing from the offline OurAirports database.
* **`fill_missing_destinations.py`**: Fills missing IATA/ICAO/GPS codes for destinations in the temporary directory by matching their Wikipedia URLs against the global URL map.
* **`merge_missing_airports.py`**: Merges JSON data from successfully scraped missing airports (in `tmp_results`) back into the main `public/airport_data` repository.
* **`relevel_missing_airports.py`**: Adjusts the BFS sweep distance levels for missing airports that were just resolved, assigning them the correct level relative to their parent seeds.

## Data Consolidation and Formatting

Scripts for consolidating extracted data into the final network formats and maintaining JSON consistency:

* **`output_information_all_airports.py`**: Orchestrates the deduplication of scraped IATA files and exports the consolidated `airports_information.csv`.
* **`fix_destinations_codes.py`**: Updates destination code lists across public JSONs by looking up their Wikipedia URLs in the global URL map, fixing missing or changed IATA/ICAO codes.
* **`reorder_json_keys.py`**: Utility script to re-format all public airport JSON files, ensuring their keys are ordered consistently according to the canonical schema.
* **`sync_json_counts.py`**: Utility script that recalculates the `number_airlines`, `outdegree`, `number_airlines_cargo`, and `outdegree_cargo` properties for all public JSON files.

## Legacy and Test Scripts

These scripts are primarily used for testing edge-cases or maintaining legacy extraction methodologies:

* **`grab_info_from_IATA.py`**: Legacy script to extract airport information and destinations directly from a Wikipedia page based on its IATA code.
* **`grab_tricky_info_from_IATA.py`**: Legacy script built to test data extraction on tricky airports (like YWG) that have complex infoboxes or destination tables.
* **`run_out_of_YWG_length_1.py`**: Test script that crawls exactly one level out from YWG (Winnipeg), explicitly verifying handling of known tricky URLs like MSP and YUL.
* **`run_out_of_YWG_length_2.py`**: Test script that crawls two levels out from YWG (Winnipeg) starting from a clean slate.
* **`run_out_of_YWG_to_end.py`**: Test script that performs a complete, clean-slate network crawl starting from YWG (Winnipeg) until exhaustion. This is the script that is used to generate the initial distribution of airports.
