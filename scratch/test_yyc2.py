import sys
sys.path.append('src')
from wikipediaGATN.airport_level_functions import *

link = "https://en.wikipedia.org/wiki/Calgary_International_Airport"
result = fetch_wikipedia_airport_wikitext(link)
if isinstance(result, tuple):
    wikitext = result[0]
else:
    wikitext = result

lines = wikitext.split('\n')
for i, line in enumerate(lines):
    if 'Brandon' in line:
        print(f"Line {i}: {line}")
        start = max(0, i-5)
        end = min(len(lines), i+5)
        print('\n'.join(lines[start:end]))
        print("---")
