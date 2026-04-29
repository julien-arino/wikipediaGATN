"""
Resumes an interrupted BFS network crawl and continues automatically until the queue is completely empty.
"""

from wikipediaGATN.wikipedia_network_level import continue_existing_search_until_empty

if __name__ == "__main__":
    # Run catchup to end
    continue_existing_search_until_empty(delay=0.33, verbose=True)
