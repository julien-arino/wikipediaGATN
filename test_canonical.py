import urllib.parse
import json
from wikipediaGATN.airport_level_functions import fetch_wikipedia_airport_info

# test wikipedia API canonical
link1 = "https://en.wikipedia.org/wiki/Rome_Fiumicino_Airport"
link2 = "https://en.wikipedia.org/wiki/Leonardo_da_Vinci–Fiumicino_Airport"

import requests
session = requests.Session()
def resolve(link):
    title = urllib.parse.unquote(link.split("/")[-1])
    params = {
        "action": "query",
        "titles": title,
        "redirects": 1,
        "format": "json"
    }
    r = session.get("https://en.wikipedia.org/w/api.php", params=params).json()
    return r

print("Link 1:", resolve(link1))
print("Link 2:", resolve(link2))
