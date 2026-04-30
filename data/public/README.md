# Public data

This directory contains the assembled data. Airports were extracted on 2026-04-29, while connections were checked on 2026-04-30.

## Raw airport data

* **`airport_data/`**: Subdirectory containing the JSON files for all individually extracted airports.

## Network Datasets

The global air transportation networks are provided in two primary variants:
* Files containing **`-pax-`** (or no suffix in matrix/node files) represent the **passenger** network.
* Files containing **`-cargo-`** represent the **cargo/freight** network.

For each network variant, we provide four standard graph formats:
* **`.csv`**: A lightweight edge list of connections.
* **`.graphml`**: A rich GraphML XML format containing full node and edge attributes.
* **`.gexf`**: A GEXF XML format natively optimized for Gephi and network visualization tools.
* **`.dot`**: A Graphviz-compatible representation.

## Interactive Visualizations

We generate interactive, standalone HTML figures using Plotly for both passenger and cargo networks:
* **`...-plotly-geographic.html`**: A 2D interactive geographic map projection.
* **`...-plotly-globe.html`**: An interactive 3D orthographic globe projection.
* **`...-plotly-graph.html`**: A standard, non-geographic network topology layout.

## Matrices and Metadata

* **`adjacency_matrix.npz`** & **`adjacency_matrix_cargo.npz`**: SciPy sparse adjacency matrices.
* **`nodes.txt`** & **`nodes_cargo.txt`**: The ordered index of IATA/ICAO codes corresponding to the rows and columns of the sparse matrices.
* **`airports_information.csv`**: Aggregated geographic and metadata (lat, lon, country, degree) for all processed airports.
* **`ourairports.csv`**: A local cache of the OurAirports open database used for high-confidence, offline metadata resolution.
