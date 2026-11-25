# Public data

This directory contains the assembled data. The snapshot is refreshed
automatically (see [`run_summary.md`](run_summary.md) and the repository's git
history for the exact date of the data currently committed here).

## Raw airport data

* **`airport_data/`**: Subdirectory containing the JSON files for all individually extracted airports.

## Network Datasets

The global air transportation networks are provided in two primary variants:
* Files containing **`-pax`** or **`_pax`** represent the **passenger** network.
* Files containing **`-cargo`** or **`_cargo`** represent the **cargo/freight** network.

For each network variant, we provide four standard graph formats:
* **`.csv`**: A lightweight edge list of connections.
* **`.graphml`**: A rich GraphML XML format containing full node and edge attributes.
* **`.gexf`**: A GEXF XML format natively optimized for Gephi and network visualization tools.
* **`.dot`**: A Graphviz-compatible representation.

### Edge-list CSV columns

Each `global-air-*-network.csv` has one row per origin airport:
* **`origin`**: the origin airport code.
* **`nb_outlinks`**: number of distinct destinations.
* **`outlinks`**: space-separated destination codes (sorted).
* **`weights`**: space-separated, aligned to `outlinks` — the **number of distinct airlines** on each route (not a 0/1 flag).
* **`nb_airlines`**: airlines at the origin (0 for airports whose data came from the unreliable NLP fallback).
* **`seasonal`**: space-separated 0/1, aligned to `outlinks` — `1` marks a seasonal-only or not-yet-started route.

### Graph node and edge attributes

In the `.graphml`/`.gexf`/`.dot` exports:
* **Nodes** carry geographic metadata plus `code_type` (`IATA` or `ICAO`) and, on the passenger graph, `airlines_reliable` (`false` when the data came from the NLP fallback).
* **Edges** carry `weight` (airline count) and `seasonal` (`1`/`0`).

See the [README "Network structure and semantics"](https://github.com/julien-arino/wikipediaGATN#network-structure-and-semantics) section for how to interpret these (e.g. summing a row is *not* out-degree, and the cargo network is partial).

## Interactive Visualizations

We generate interactive, standalone HTML figures using Plotly for both passenger and cargo networks:
* **`...-plotly-geographic.html`**: A 2D interactive geographic map projection.
* **`...-plotly-globe.html`**: An interactive 3D orthographic globe projection.
* **`...-plotly-graph.html`**: A standard, non-geographic network topology layout.

## Matrices and Metadata

* **`adjacency_matrix_pax.npz`** & **`adjacency_matrix_cargo.npz`**: SciPy sparse adjacency matrices.
* **`nodes_pax.txt`** & **`nodes_cargo.txt`**: The ordered index of IATA/ICAO codes corresponding to the rows and columns of the sparse matrices.
* **`airports_information.csv`**: Aggregated geographic and metadata (lat, lon, country, degree) for all processed airports.
* **`ourairports.csv`**: A local cache of the OurAirports open database used for high-confidence, offline metadata resolution.

## Licensing and attribution

This data is **derived from third-party sources** and is subject to their terms,
which differ from the GPL that covers the `wikipediaGATN` source code:

* **Wikipedia** — the network structure (routes, airlines, destinations) and
  much of the airport metadata are extracted from Wikipedia, whose text is
  licensed **[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)**.
  Reuse of this derived data should credit Wikipedia and its contributors and,
  under ShareAlike, distribute any adapted version under compatible terms.
* **OurAirports** — IATA/ICAO codes and geographic metadata are supplemented
  from the [OurAirports](https://ourairports.com/data/) database, released into
  the **public domain**. Attribution is appreciated but not required.

If you redistribute or build on this dataset, please credit both sources (and
cite `wikipediaGATN` itself; see [`CITATION.cff`](../../CITATION.cff)).
