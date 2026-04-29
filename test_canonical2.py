import requests
import urllib.parse
headers = {'User-Agent': 'wikipediaGATN/1.0 (julien.arino@example.com)'}
r = requests.get('https://en.wikipedia.org/w/api.php?action=query&titles=Rome_Fiumicino_Airport&redirects=1&format=json', headers=headers)
print(r.json())
