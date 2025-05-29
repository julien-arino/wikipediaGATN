import os

# Root directory of the repo
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Data directory at the repo root
DATA_DIR = os.path.join(REPO_ROOT, "data")

# Subdirectories
TEMP_RESULTS_DIR = os.path.join(DATA_DIR, "tmp_results")
PUBLIC_DATA_DIR = os.path.join(DATA_DIR, "public")