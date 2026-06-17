# Installation

## From PyPI (Recommended)

To install the latest stable version directly from PyPI:

```bash
pip install wikipediaGATN
```

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
