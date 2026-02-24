"""
Minimal setup.py — retained for compatibility with tools that still call
``python setup.py ...`` directly (e.g. older editable-install workflows,
some CI systems, ``pip install -e .`` on pip < 21.3).

All project metadata and build configuration live in ``pyproject.toml``.
This file must *not* duplicate that metadata; it simply delegates.

Usage
-----
    # Standard install
    pip install .

    # Editable / development install
    pip install -e ".[dev]"

    # After install, download the required spaCy language model:
    python -m spacy download en_core_web_sm
"""

from setuptools import setup

# All configuration is read from pyproject.toml by setuptools ≥ 61.
# This call is intentionally left empty.
setup()