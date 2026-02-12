"""
Extract IATA codes from Wikipedia airport pages.

This module fetches Wikipedia pages for unmapped destination airports and
extracts their IATA codes using pattern matching. It handles the standard
Wikipedia format: "IATA: XXX, ICAO: YYYY, FAA LID: ZZZ"

Typical workflow:
1. Run create_outbound_connections_list() → generates unmapped_destinations.csv
2. Run extract_iata_from_unmapped_destinations() → populates IATA codes
3. (Optional) Update manual_airport_mapping.csv with successful extractions
4. Rerun create_outbound_connections_list() → better coverage
"""

import os
import re
import csv
import time
from urllib.parse import unquote

from .paths import PUBLIC_DATA_DIR, TEMP_RESULTS_DIR


def _extract_iata_from_wikipedia_page(url, verbose=False):
    """
    Fetch and parse a Wikipedia page to extract IATA code.
    
    Wikipedia airport pages follow a standard format:
    "... (IATA: XXX, ICAO: YYYY, FAA LID: ZZZ) ..."
    
    Parameters
    ----------
    url : str
        Wikipedia URL for an airport
    verbose : bool
        If True, prints extraction details
    
    Returns
    -------
    dict with keys:
        - 'iata': Extracted IATA code (3 uppercase letters) or None
        - 'icao': Extracted ICAO code or None
        - 'confidence': Confidence score (0-1)
        - 'extracted_text': The text snippet where IATA was found
    """
    import requests
    from bs4 import BeautifulSoup
    
    result = {
        'iata': None,
        'icao': None,
        'confidence': 0,
        'extracted_text': None,
        'error': None
    }
    
    try:
        # Fetch the Wikipedia page
        headers = {
            'User-Agent': 'wikipediaGATN/0.1.0 (research data extraction)'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get the first paragraph (usually contains IATA code)
        paragraphs = soup.find_all('p')
        
        for para in paragraphs[:5]:  # Check first 5 paragraphs
            text = para.get_text(separator=' ', strip=True)
            
            # Skip disambiguation/redirect text (it's noise)
            if any(skip in text.lower() for skip in ['redirect', 'not to be confused', 'for other uses', 'for the']):
                continue
            
            # Pattern 1: Standard Wikipedia format
            # "... (IATA: XYZ, ICAO: ABCD, FAA LID: ZZZ) ..."
            match = re.search(r'\(IATA:\s*([A-Z]{3}),', text, re.IGNORECASE)
            if match:
                iata = match.group(1).upper()
                result['iata'] = iata
                result['confidence'] = 0.95  # High confidence
                result['extracted_text'] = text[:200]  # First 200 chars
                
                # Also try to get ICAO
                icao_match = re.search(r'ICAO:\s*([A-Z]{4})', text, re.IGNORECASE)
                if icao_match:
                    result['icao'] = icao_match.group(1).upper()
                
                if verbose:
                    print(f"   Found {iata} in: {text[:100]}...")
                return result
            
            # Pattern 2: Alternative format
            # "... IATA: XYZ)"
            match = re.search(r'IATA:\s*([A-Z]{3})\)', text, re.IGNORECASE)
            if match:
                iata = match.group(1).upper()
                result['iata'] = iata
                result['confidence'] = 0.90
                result['extracted_text'] = text[:200]
                return result
            
            # Pattern 3: In a info box or list
            # "Code: XYZ" (less reliable)
            if 'airport' in text.lower() or 'iata' in text.lower():
                match = re.search(r'(?:IATA|Code)[:\s]+([A-Z]{3})(?:\s|,|\))', text)
                if match:
                    iata = match.group(1).upper()
                    # Verify it looks like a real IATA code
                    if iata not in ['THE', 'FOR', 'AND', 'USE', 'SEE']:
                        result['iata'] = iata
                        result['confidence'] = 0.7
                        result['extracted_text'] = text[:200]
                        return result
        
        if verbose:
            print(f"  No IATA code found in first 5 paragraphs")
        result['error'] = 'No IATA pattern found'
        
    except requests.exceptions.RequestException as e:
        result['error'] = f'HTTP Error: {str(e)}'
        if verbose:
            print(f"   Request failed: {e}")
    except Exception as e:
        result['error'] = f'Parse Error: {str(e)}'
        if verbose:
            print(f"   Parse error: {e}")
    
    return result


def extract_iata_from_unmapped_destinations(csv_path=None, batch_size=50, delay=0.5, verbose=False):
    """
    Extract IATA codes from Wikipedia pages for unmapped destinations.
    
    Processes unmapped_destinations.csv in batches to avoid overloading
    Wikipedia servers. Results are saved back to the CSV file.
    
    Parameters
    ----------
    csv_path : str, optional
        Path to unmapped_destinations.csv. If None, uses default:
        data/public/unmapped_destinations.csv
    batch_size : int, optional
        Number of URLs to process before pausing (default: 50)
    delay : float, optional
        Delay in seconds between requests (default: 0.5)
    verbose : bool, optional
        If True, prints detailed progress (default: False)
    
    Returns
    -------
    dict with summary:
        - 'total': Total URLs processed
        - 'successful': Successfully extracted IATA codes
        - 'failed': Failed to extract
        - 'csv_path': Path to updated CSV
    
    Example
    -------
    >>> from wikipediaGATN.extract_iata_from_wikipedia import extract_iata_from_unmapped_destinations
    >>> result = extract_iata_from_unmapped_destinations(verbose=True)
    >>> print(f"Found {result['successful']} IATA codes")
    """
    
    # Use default path if not provided
    if csv_path is None:
        csv_path = os.path.join(PUBLIC_DATA_DIR, "unmapped_destinations.csv")
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"File not found: {csv_path}")
    
    if verbose:
        print(f"Loading unmapped destinations from {csv_path}...")
    
    # Read existing data
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    total = len(rows)
    successful = 0
    failed = 0
    
    if verbose:
        print(f"Found {total} unmapped URLs\n")
    
    # Process each URL
    for idx, row in enumerate(rows, 1):
        url = row['url']
        
        # Skip if already has IATA
        if row.get('iata', '').strip():
            if verbose:
                print(f"[{idx}/{total}] Already has IATA: {url}")
            successful += 1
            continue
        
        if verbose:
            print(f"[{idx}/{total}] Processing: {url}")
        
        # Extract IATA from Wikipedia page
        result = _extract_iata_from_wikipedia_page(url, verbose=verbose)
        
        if result['iata']:
            row['iata'] = result['iata']
            row['source'] = f'scraped (conf: {result["confidence"]:.0%})'
            successful += 1
            
            if verbose:
                print(f"         Found IATA: {result['iata']}\n")
        else:
            failed += 1
            row['source'] = f'failed ({result.get("error", "unknown")})'
            
            if verbose:
                print(f"     Failed: {result.get('error', 'unknown')}\n")
        
        # Polite delay between requests
        if idx % batch_size == 0 and idx < total:
            if verbose:
                print(f"Processed {idx}/{total}. Pausing {delay * batch_size:.1f}s to be nice to Wikipedia...\n")
            time.sleep(delay * batch_size)
        else:
            time.sleep(delay)
    
    # Write results back to CSV
    output_csv = csv_path  # Overwrite original file
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["url", "count", "iata", "name", "source"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    if verbose:
        print("=" * 70)
        print("EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Total URLs: {total}")
        print(f"Successfully extracted: {successful}")
        print(f"Failed: {failed}")
        print(f"Success rate: {successful / total * 100:.1f}%")
        print(f"Updated CSV: {os.path.abspath(output_csv)}")
        print("\n💡 Next: Use this CSV to update manual_airport_mapping.csv")
        print("   or rerun create_outbound_connections_list() with the updated data")
    
    return {
        'total': total,
        'successful': successful,
        'failed': failed,
        'csv_path': output_csv
    }


def create_manual_mapping_from_scraped_data(unmapped_csv=None, output_csv=None, min_confidence=0.7, verbose=False):
    """
    Create a manual_airport_mapping.csv from successfully scraped IATA codes.
    
    Parameters
    ----------
    unmapped_csv : str, optional
        Path to unmapped_destinations.csv (default: data/public/unmapped_destinations.csv)
    output_csv : str, optional
        Path to output manual_airport_mapping.csv (default: data/temp/manual_airport_mapping.csv)
    min_confidence : float, optional
        Minimum confidence threshold (0-1, default: 0.7)
    verbose : bool, optional
        If True, prints details
    
    Returns
    -------
    int
        Number of entries written to manual mapping
    """
    
    if unmapped_csv is None:
        unmapped_csv = os.path.join(PUBLIC_DATA_DIR, "unmapped_destinations.csv")
    
    if output_csv is None:
        output_csv = os.path.join(TEMP_RESULTS_DIR, "manual_airport_mapping.csv")
    
    # Read unmapped destinations with extracted IATA codes
    rows = []
    with open(unmapped_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    # Filter for successfully extracted entries
    manual_mappings = []
    for row in rows:
        iata = row.get('iata', '').strip()
        
        # Skip if no IATA found
        if not iata or iata.upper() in ['NONE', '', 'ERROR']:
            continue
        
        # Check confidence if available in source
        if 'conf:' in row.get('source', ''):
            try:
                conf_str = re.search(r'conf:\s*([\d.]+)', row['source'])
                if conf_str:
                    conf = float(conf_str.group(1))
                    if conf < min_confidence:
                        continue
            except:
                pass
        
        manual_mappings.append({
            'url': row['url'],
            'iata': iata.upper(),
            'name': row.get('name', ''),
            'source': 'web_scraped'
        })
    
    # Write to manual mapping file
    os.makedirs(TEMP_RESULTS_DIR, exist_ok=True)
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["url", "iata", "name", "source"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manual_mappings)
    
    if verbose:
        print(f" Created manual_airport_mapping.csv with {len(manual_mappings)} entries")
        print(f"  Output: {os.path.abspath(output_csv)}")
    
    return len(manual_mappings)
