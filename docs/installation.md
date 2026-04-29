# Installation

## Standard Installation

Currently, `wikipediaGATN` can be installed from source.

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
