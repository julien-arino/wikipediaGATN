# wikipediaGATN

## Overview

`wikipediaGATN` scrapes Wikipedia airport pages to assemble the **Global Air Transportation Networks (GATN)**: two directed graphs in which each node is an airport (identified by its IATA code) and each directed edge represents a scheduled route between two airports for passengers (pax) or cargo.

The package handles the full pipeline:

1. **Crawling** — breadth-first traversal from a seed airport, following destination links to neighbouring airport pages.
2. **Parsing** — extraction of IATA/ICAO codes, geographic coordinates, and route tables from Wikipedia infoboxes and HTML tables, supplemented by the authoritative [OurAirports](https://ourairports.com/) database for metadata.
3. **IATA recovery** — resolution of destination URLs that lack an obvious code, prioritizing offline lookups in the [OurAirports](https://ourairports.com/) database before falling back to Wikipedia scraping.
4. **Export** — sparse adjacency matrices (`.npz`), node lists, airport metadata CSVs ready for network analysis, and interactive Plotly visualisations (`.html`).
5. **Updates** — on demand maintenance of the network through incremental scraping and synchronization with upstream [OurAirports](https://ourairports.com/) metadata changes, keeping the graphs up to date.

The resulting networks can be used for empirical studies of air-travel connectivity, epidemic-spread modelling and transportation network analysis. They also provide great examples in courses about graphs/networks, data science and computational social science.

## Setting up

If using a virtual environment
```bash
source /path/to/venv/bin/activate
```

If running before deploying the package, you need to run stuff from the top directory in the repo. Set

```
export PYTHONPATH=src
```

and then call the code using, e.g.,

```
python -m scripts.grab_info_from_IATA
```

Note the nonstandard call: `-m`, `.` instead of `/` to indicate a subdirectory and no `.py` extension.


## Required post-install step — spaCy language model

The NLP fallback for airline/destination extraction requires the
`en_core_web_sm` model, which cannot be declared as a standard PyPI
dependency:

```bash
python -m spacy download en_core_web_sm
```

### Dependencies

| Package | Purpose |
|---|---|
| `requests`, `beautifulsoup4` | Wikipedia HTTP requests and HTML parsing |
| `mwparserfromhell` | Wikitext infobox parsing |
| `spacy` | NLP fallback for unstructured route tables |
| `geopy`, `pycountry` | Coordinate and ISO 3166-2 parsing |
| `numpy`, `scipy` | Sparse adjacency matrix construction |
| `pandas` | CSV I/O and data manipulation |
| `networkx` | Graph construction and layout |
| `plotly` | Interactive HTML visualisation |

---

## Example use

The following builds a network for all airports reachable within two hops of
Winnipeg (YWG) and exports it as a sparse adjacency matrix:

```python
from wikipediaGATN.wikipedia_network_level import iterate_search_until_distance_N
from wikipediaGATN.result_processing import (
    create_outbound_connections_list,
    run_two_pass_iata_extraction,
    create_outbound_adjacency_matrix,
)

# 1. Crawl Wikipedia — save one JSON file per airport to data/tmp_results/
iterate_search_until_distance_N("YWG", dist=2, delay=0.5, verbose=True)

# 2. Build connections CSV (maps destination URLs to IATA codes)
connections_csv, unmapped_csv = create_outbound_connections_list(
    verbose=True, export_unmapped=True
)

# 3. Recover IATA codes for any destinations that could not be mapped automatically
#    (scrapes Wikipedia; allow ~15 minutes for a large unmapped set)
run_two_pass_iata_extraction(batch_size=50, delay=0.5, verbose=True)

# 4. Re-run connections with the enriched mapping
create_outbound_connections_list(verbose=True)

# 5. Export sparse adjacency matrices to data/public/
matrix_npz, nodes_txt = create_outbound_adjacency_matrix(symmetric=False, verbose=True)
matrix_sym_npz, nodes_sym_txt = create_outbound_adjacency_matrix(symmetric=True, verbose=True)
```

For a full global crawl (several hours) replace step 1 with:

```python
from wikipediaGATN.wikipedia_network_level import iterate_search_until_empty
iterate_search_until_empty("YWG", delay=0.5, verbose=True)
```

To resume after an interruption:

```python
from wikipediaGATN.wikipedia_network_level import continue_existing_search_until_empty
continue_existing_search_until_empty(delay=0.5, verbose=True)

