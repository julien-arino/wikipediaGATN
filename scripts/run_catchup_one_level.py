"""
Resumes an interrupted BFS network crawl, expanding the frontier by exactly one level.
"""

from wikipediaGATN.wikipedia_network_level import continue_existing_search_one_step

if __name__ == "__main__":
    # Run catchup for the current N-1 level
    continue_existing_search_one_step(delay=0.33, verbose=True)
