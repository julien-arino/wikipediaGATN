import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from query_wikipedia import get_wikipedia_airport_page_html, extract_iata_icao_from_html

def main(iata_code):
    html = get_wikipedia_airport_page_html(iata_code)
    if not html:
        print(f"Could not fetch page for {iata_code}")
        return
    iata, icao = extract_iata_icao_from_html(html)
    print(f"IATA: {iata}")
    print(f"ICAO: {icao}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_extract_iata_icao.py <IATA_CODE>")
    else:
        main(sys.argv[1])

#get_length_1_connections("YWG", clean_output=True)
#get_multi_path_length_connections("YWG", path_length=2, clean_output=True)
