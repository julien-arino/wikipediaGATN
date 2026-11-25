# Configuration file for the Sphinx documentation builder.

import os
import sys

sys.path.insert(0, os.path.abspath("../src"))

# -- Project information -----------------------------------------------------

project = "wikipediaGATN"
copyright = "2024, Julien Arino, Adriana-Stefania Ciupeanu"
author = "Julien Arino, Adriana-Stefania Ciupeanu"
release = "0.1.0"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# -- Extension configuration -------------------------------------------------

# Map .md to MyST
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Generate anchors for headings (h1–h3) so cross-document links of the form
# ``usage.md#interpreting-the-networks`` resolve.
myst_heading_anchors = 3
