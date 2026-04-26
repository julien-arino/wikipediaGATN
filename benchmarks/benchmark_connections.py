import re
import timeit
from urllib.parse import unquote

def _extract_airport_name_from_url_original(url: str):
    if not url:
        return None

    m = re.search(r"/wiki/(.+?)(?:\?|$)", url)
    if not m:
        return None

    name = unquote(m.group(1))
    name = re.sub(r"[_\-\u2013\u2014]", " ", name)   # –, —, -, _
    name = re.sub(r"\s+International\s+Airport$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+National\s+Airport$",      "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+Airport$",                 "", name, flags=re.IGNORECASE)

    name = name.strip()
    return name if name else None

# Pre-compiled version for even better performance
RE_WIKI = re.compile(r"/wiki/(.+?)(?:\?|$)")
RE_DASHES = re.compile(r"[_\-\u2013\u2014]")
RE_SUFFIX = re.compile(r"\s+(?:International\s+|National\s+)?Airport$", re.IGNORECASE)

def _extract_airport_name_from_url_precompiled(url: str):
    if not url:
        return None

    m = RE_WIKI.search(url)
    if not m:
        return None

    name = unquote(m.group(1))
    name = RE_DASHES.sub(" ", name)
    name = RE_SUFFIX.sub("", name)

    name = name.strip()
    return name if name else None

test_urls = [
    "https://en.wikipedia.org/wiki/Heathrow_Airport",
    "https://en.wikipedia.org/wiki/Los_Angeles_International_Airport",
    "https://en.wikipedia.org/wiki/Washington_National_Airport",
    "https://en.wikipedia.org/wiki/Winnipeg_Richardson_International_Airport",
    "https://en.wikipedia.org/wiki/London_Gatwick_Airport?action=edit",
    "https://en.wikipedia.org/wiki/Paris-Charles_de_Gaulle_Airport",
    "https://en.wikipedia.org/wiki/Singapore_Changi_Airport",
    "https://en.wikipedia.org/wiki/Some_Other_Place",
    "invalid_url"
]

def run_benchmark():
    n = 100000

    t_orig = timeit.timeit(lambda: [ _extract_airport_name_from_url_original(url) for url in test_urls ], number=n)
    print(f"Original:    {t_orig:.4f}s")

    t_pre = timeit.timeit(lambda: [ _extract_airport_name_from_url_precompiled(url) for url in test_urls ], number=n)
    print(f"Precompiled: {t_pre:.4f}s")

    print(f"Improvement (Pre): {(t_orig - t_pre) / t_orig * 100:.2f}%")

if __name__ == "__main__":
    # Verify correctness
    for url in test_urls:
        orig = _extract_airport_name_from_url_original(url)
        pre = _extract_airport_name_from_url_precompiled(url)
        if orig != pre:
            print(f"Mismatch for {url}:")
            print(f"  Orig: {orig}")
            print(f"  Pre:  {pre}")

    run_benchmark()
