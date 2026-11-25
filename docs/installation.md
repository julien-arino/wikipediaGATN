# Installation

## From PyPI (Recommended)

To install the latest stable version directly from PyPI:

```bash
pip install wikipediaGATN
```

### Bundled network data

The PyPI wheel **ships the pre-built global networks**, so you can read and
analyse them immediately without scraping Wikipedia or cloning the repository.
Bundled inside the package (under `wikipediaGATN/_data/public/`) are, for both
the passenger and cargo networks:

- the graph files `.graphml`, `.gexf`, `.dot`, and the edge-list `.csv`;
- the sparse adjacency matrices (`adjacency_matrix_*.npz`) and node lists
  (`nodes_*.txt`);
- `airports_information.csv`.

`wikipediaGATN.paths.PUBLIC_DATA_DIR` resolves to this bundled copy
automatically when you have not run a local crawl, so the quickstart "load the
pre-built network" examples work straight from a `pip install`.

What is **not** bundled (to keep the wheel small): the interactive Plotly
`*.html` visualisations and `ourairports.csv` (the latter is downloaded on
demand). The bundled data is a read-only snapshot; to run your own crawl and
write fresh data, install from source or set the `WIKIPEDIAGATN_DATA_DIR`
environment variable to a writable directory.

## From Source

For development or to access the latest changes, clone the repository and install it:

```bash
git clone https://github.com/julien-arino/wikipediaGATN.git
cd wikipediaGATN
pip install .
```

## Development Installation

If you wish to contribute to the project, install it in editable mode with development dependencies:

```bash
pip install -e ".[dev]"
```

## Required Post-Install Step

The NLP fallback for airline/destination extraction requires the `en_core_web_sm` model:

```bash
python -m spacy download en_core_web_sm
```
