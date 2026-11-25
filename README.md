# wikipediaGATN

[![Tests](https://github.com/julien-arino/wikipediaGATN/actions/workflows/tests.yml/badge.svg)](https://github.com/julien-arino/wikipediaGATN/actions/workflows/tests.yml)
[![Docs](https://github.com/julien-arino/wikipediaGATN/actions/workflows/docs.yml/badge.svg)](https://github.com/julien-arino/wikipediaGATN/actions/workflows/docs.yml)
[![PyPI version](https://img.shields.io/pypi/v/wikipediaGATN.svg)](https://pypi.org/project/wikipediaGATN/)
[![Python versions](https://img.shields.io/pypi/pyversions/wikipediaGATN.svg)](https://pypi.org/project/wikipediaGATN/)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Overview

`wikipediaGATN` scrapes Wikipedia airport pages to assemble the **Global Air Transportation Networks (GATN)**: two directed graphs in which each node is an airport (identified by its IATA code, or its 4-letter ICAO code where no IATA code exists) and each directed edge represents a scheduled route between two airports for passengers (pax) or cargo. The edge weight is the number of distinct airlines reported on that route — see [Network structure and semantics](#network-structure-and-semantics) for what the nodes, edges, weights, and attributes mean.

### Why build the network from Wikipedia?

Comprehensive commercial datasets of the GATN exist (IATA, OAG, and similar providers), but they are often prohibitively priced and cannot be redistributed. `wikipediaGATN` seeks a middle ground: it does not attempt to capture flight *volumes*, but it reconstructs the *structure* of the network — which airports are connected to which — entirely from publicly available Wikipedia data, and ships the result under an open licence. This makes it suitable for empirical studies of air-travel connectivity, epidemic-spread modelling, and teaching graph/network analysis, where an open, reproducible snapshot of the network structure is more valuable than paid access to traffic figures. The trade-off is that coverage and accuracy depend on the quality of each airport's Wikipedia page (see the limitations noted in the documentation).

## Data

The collected data is available in the [`data/public/`](https://github.com/julien-arino/wikipediaGATN/tree/main/data/public) directory. See ``data/public/README.md`` for a detailed description of the files.

**What ships on PyPI.** As of the current release the PyPI wheel **bundles the pre-built networks** (the `.graphml`/`.gexf`/`.dot`/`.csv` graphs, the `.npz` adjacency matrices, the node lists, and `airports_information.csv`), so `pip install wikipediaGATN` is enough to load and analyse the global graphs. What is **not** on PyPI: the full per-airport raw JSON crawl (`data/public/airport_data/`) and the interactive Plotly `*.html` visualisations — clone the repository for those. See [Installation → Bundled network data](https://julien-arino.github.io/wikipediaGATN/installation.html#bundled-network-data).

## Network structure and semantics

Before using the graphs it helps to know exactly what the nodes and edges mean.

**Size (current snapshot).**

| Network | Airports (nodes) | Routes (edges) | 4-letter ICAO nodes | Bidirectional edges |
|---|---|---|---|---|
| Passenger (`pax`) | ~4,360 | ~64,100 | ~90 | ~89% |
| Cargo | ~920 | ~4,650 | ~5 | ~46% |

Counts drift as Wikipedia is re-crawled; rebuild with the pipeline for exact current figures.

**Nodes.** Each node is an airport, identified by its 3-letter **IATA** code where one exists and its 4-letter **ICAO** code otherwise (about 90 passenger nodes). Each exported graph node carries a `code_type` attribute (`"IATA"` or `"ICAO"`) so the two are distinguishable, alongside geographic metadata (lat/lon, city served, country, admin-1).

**Edges and weights.** A directed edge A → B means at least one airline operates a scheduled A → B route. The edge **weight is the number of distinct airlines** reported on that route (roughly 1–25 for passenger, 1–19 for cargo), **not** a 0/1 presence flag. So **summing a node's row is not its out-degree**: use the count of non-zero entries for out-degree, and the row sum only when you specifically want total airline-route multiplicity.

**Seasonal / future routes.** Routes annotated on Wikipedia as seasonal-only or not-yet-started are flagged with a `seasonal` edge attribute (`1` = seasonal/future, `0` = year-round) instead of being treated as ordinary edges; the network CSVs carry a matching `seasonal` column.

**NLP-fallback reliability.** When an airport page has no parseable route table, the airline/destination data is recovered with an NLP fallback whose airline *names* are unreliable. Those airports do **not** publish airline counts (their edges get weight 1 and their `nb_airlines` is dropped), and their passenger graph nodes are marked `airlines_reliable = False`.

**Directed vs symmetric.** The default graphs are **directed**. A `symmetric` build (files suffixed `_sym`) adds the reverse of every edge; where both A → B and B → A exist with different weights the symmetric weight is the **maximum** of the two (`max(A, Aᵀ)`), not the sum. Use the symmetric version for an undirected connectivity view that tolerates under-reporting of small airports' outbound routes.

**Cargo coverage is partial.** The crawler follows *passenger* destination links, so the cargo network is a by-product: it is smaller and less complete than the passenger one (far fewer of its edges are bidirectional — ~46% vs ~89%), and some real cargo hubs may be missing or under-connected. Treat the cargo graph as indicative, not exhaustive.

**Provenance and accuracy.** All structure is derived from Wikipedia (supplemented by OurAirports metadata), so coverage and accuracy track the quality of each airport's Wikipedia page.

## Using Pre-built Data & Network Analysis

The global network data in `data/public/` is automatically updated weekly via GitHub Actions. **You do not need to run your own crawl to use this data.** You can clone this repository (or download the `data/` folder) and immediately load the provided sparse matrices to perform graph analysis.

For more details on available files and advanced analysis examples, see the [Quickstart Tutorials](https://julien-arino.github.io/wikipediaGATN/quickstart.html).

Here is an end-to-end example showing how to load the passenger network from the pre-built `.npz` file and analyze it with `networkx`:

```python
import numpy as np
import scipy.sparse
import networkx as nx

# 1. Load the node labels (IATA codes)
with open('data/public/nodes_pax.txt', 'r') as f:
    iata_codes = [line.strip() for line in f]

# 2. Load the sparse adjacency matrix
matrix = scipy.sparse.load_npz('data/public/adjacency_matrix_pax.npz')

# 3. Create a NetworkX directed graph
G = nx.from_scipy_sparse_array(matrix, create_using=nx.DiGraph)

# 4. Map node indices to their actual IATA codes
mapping = {i: code for i, code in enumerate(iata_codes)}
nx.relabel_nodes(G, mapping, copy=False)

print(f"Network has {G.number_of_nodes()} airports and {G.number_of_edges()} routes.")

# 5. Basic analysis: find the airport with the most incoming flights
in_degrees = dict(G.in_degree())
most_connected = max(in_degrees, key=in_degrees.get)
print(f"Most connected destination: {most_connected} ({in_degrees[most_connected]} incoming routes)")
```

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
```

## Documentation

Full documentation, including the API reference and quickstart tutorials, is available at
<https://julien-arino.github.io/wikipediaGATN/>.

## Contributing

Contributions are welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) for how to set up a
development environment, run the tests, and open a pull request, and
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) for the standards we expect of participants.

## Citation

If you use `wikipediaGATN` in your research, please cite it. Citation metadata is provided in
[`CITATION.cff`](CITATION.cff); GitHub renders a ready-to-use citation from that file via the
"Cite this repository" button on the repository page.

## License

`wikipediaGATN` is released under the GNU General Public License v3.0 or later; see
[`LICENSE`](LICENSE). Note that data under `data/public/` is derived from Wikipedia and OurAirports
and is subject to those sources' own terms — see [`data/public/README.md`](data/public/README.md).

