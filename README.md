# wikipediaGATN

[![Tests](https://github.com/julien-arino/wikipediaGATN/actions/workflows/tests.yml/badge.svg)](https://github.com/julien-arino/wikipediaGATN/actions/workflows/tests.yml)
[![Docs](https://github.com/julien-arino/wikipediaGATN/actions/workflows/docs.yml/badge.svg)](https://github.com/julien-arino/wikipediaGATN/actions/workflows/docs.yml)
[![PyPI version](https://img.shields.io/pypi/v/wikipediaGATN.svg)](https://pypi.org/project/wikipediaGATN/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Overview

`wikipediaGATN` scrapes Wikipedia airport pages to assemble the **Global Air Transportation Networks (GATN)**: two directed graphs in which each node is an airport (identified by its IATA code) and each directed edge represents a scheduled route between two airports for passengers (pax) or cargo. 

## Data

The collected data is available in the [`data/public/`](https://github.com/julien-arino/wikipediaGATN/tree/main/data/public) directory. See ``data/public/README.md`` for a detailed description of the files.

## Package pipeline

The package handles the full pipeline:

1. **Crawling** — breadth-first traversal from a seed airport, following destination links to neighbouring airport pages.
2. **Parsing** — extraction of IATA/ICAO codes, geographic coordinates, and route tables from Wikipedia infoboxes and HTML tables, supplemented by the authoritative [OurAirports](https://ourairports.com/) database for metadata.
3. **IATA recovery** — resolution of destination URLs that lack an obvious code, prioritizing offline lookups in the [OurAirports](https://ourairports.com/) database before falling back to Wikipedia scraping.
4. **Export** — sparse adjacency matrices (`.npz`), node lists, airport metadata CSVs ready for network analysis, and interactive Plotly visualisations (`.html`).
5. **Updates** — on demand maintenance of the network through incremental scraping and synchronization with upstream [OurAirports](https://ourairports.com/) metadata changes, keeping the graphs up to date. Updates are easy to perform as GitHub actions (see .github/workflows/refresh_data.yml).

The resulting networks can be used for empirical studies of air-travel connectivity, epidemic-spread modelling and transportation network analysis, among other things. 
They also provide great examples in courses about graphs/networks, data science and computational social science.

## Installation

### From PyPI (Recommended)

To install the latest stable version directly from PyPI:

```bash
pip install wikipediaGATN
```

### From Source

For development or to access the latest changes, clone the repository and install it:

```bash
git clone https://github.com/julien-arino/wikipediaGATN.git
cd wikipediaGATN
pip install .
```

If you wish to contribute, install in editable mode with development dependencies:

```bash
pip install -e ".[dev]"
```

If running from the source repository before deploying the package, set:

```bash
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

Some scripts are provided as examples in the `scripts/` directory, which comprise instructions to carry out all steps of the pipeline..

For function example, the following builds a network for all airports reachable within two hops of Winnipeg (YWG) and exports it as a sparse adjacency matrix:

```python
from wikipediaGATN.wikipedia_network_level import iterate_search_until_distance_N
from wikipediaGATN import (
    export_all_airport_data,
    create_outbound_connections_list,
    run_two_pass_iata_extraction,
    create_outbound_adjacency_matrix,
)

# 1. Crawl Wikipedia — save one JSON file per airport to data/tmp_results/
iterate_search_until_distance_N("YWG", dist=2, delay=0.5, verbose=True)

# 2. Process and export crawled airport data (creates public/airport_data/ and airports_information.csv)
export_all_airport_data(use_new_data=True, verbose=True)

# 3. Build connections CSV (maps destination URLs to IATA codes)
connections_csv, cargo_csv, unmapped_csv = create_outbound_connections_list(
    verbose=True, export_unmapped=True
)

# 4. Recover IATA codes for any destinations that could not be mapped automatically
#    (scrapes Wikipedia; allow ~15 minutes for a large unmapped set)
run_two_pass_iata_extraction(batch_size=50, delay=0.5, verbose=True)

# 5. Re-export airport data to apply the recovered manual mappings
export_all_airport_data(use_new_data=True, verbose=True)

# 6. Re-run connections with the enriched mapping
create_outbound_connections_list(verbose=True)

# 7. Export sparse adjacency matrices to data/public/
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

