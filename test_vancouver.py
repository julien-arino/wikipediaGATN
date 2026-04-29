from wikipediaGATN.airport_level_functions import fetch_wikipedia_airport_info
info = fetch_wikipedia_airport_info("https://en.wikipedia.org/wiki/Vancouver_Airport")
print(info["wikipedia_url"])
