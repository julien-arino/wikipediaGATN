"""
Generates interactive Plotly visualisations for the GATN networks.

This script creates geographic, globe, and graph-theoretic layouts 
for both the Passenger and Cargo networks, saving them as HTML 
files in the public data directory.
"""

import subprocess
import os
import sys

def run_visualisation():
    print("Generating interactive network visualisations...")
    # Add src to PYTHONPATH
    env = os.environ.copy()
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path

    # Use the current python executable
    cmd = [sys.executable, "-m", "wikipediaGATN.visualise_gatn"]
    
    try:
        result = subprocess.run(cmd, env=env, check=True)
        print("\nVisualisation generation complete.")
    except subprocess.CalledProcessError as e:
        print(f"\nError during visualisation: {e}")

if __name__ == "__main__":
    run_visualisation()
