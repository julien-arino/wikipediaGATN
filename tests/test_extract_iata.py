"""
Tests for :mod:`wikipediaGATN.extract_iata_from_wikipedia`.

HTTP calls are intercepted via ``@patch`` at the correct module-level
namespace.  All filesystem I/O uses ``tmp_path`` fixtures.

Patch target for ``requests.get``:
    ``'wikipediaGATN.extract_iata_from_wikipedia.requests.get'``
    NOT ``'requests.get'`` — the latter patches the global namespace and
    has no effect on code that has already bound ``import requests`` locally.
"""

import csv
from unittest.mock import Mock, patch

import pytest
import requests
import requests.exceptions

from wikipediaGATN.extract_iata_from_wikipedia import (
    _extract_iata_from_wikipedia_page,
    create_manual_mapping_from_scraped_data,
    extract_iata_from_unmapped_destinations,
)

# Correct patch target — must match the ``import requests`` binding inside
# the module under test, not the global requests namespace.
_REQUESTS_GET = "wikipediaGATN.extract_iata_from_wikipedia.requests.get"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(html_bytes: bytes) -> Mock:
    """Return a mock response that returns *html_bytes* and does not raise."""
    r = Mock()
    r.content = html_bytes
    r.raise_for_status = Mock()
    return r


def _write_unmapped_csv(path, rows):
    """Write rows to *path* as a valid unmapped_destinations CSV."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["url", "count", "iata", "name", "source"]
        )
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# _extract_iata_from_wikipedia_page
# ---------------------------------------------------------------------------

class TestExtractIataFromWikipediaPage:

    @patch(_REQUESTS_GET)
    def test_standard_infobox_format(self, mock_get):
        """Extracts IATA from ``(IATA: YYZ, ICAO: CYYZ)`` format."""
        mock_get.return_value = _make_response(
            b"<p>Toronto Pearson International Airport (IATA: YYZ, ICAO: CYYZ)</p>"
        )
        result = _extract_iata_from_wikipedia_page("https://en.wikipedia.org/wiki/T")
        assert result["iata"] == "YYZ"
        assert result["confidence"] >= 0.9

    @patch(_REQUESTS_GET)
    def test_icao_also_extracted(self, mock_get):
        """ICAO code is extracted alongside IATA."""
        mock_get.return_value = _make_response(
            b"<p>Airport (IATA: YYZ, ICAO: CYYZ)</p>"
        )
        result = _extract_iata_from_wikipedia_page("https://example.com")
        assert result["iata"] == "YYZ"
        assert result["icao"] == "CYYZ"

    @patch(_REQUESTS_GET)
    def test_iata_not_found_returns_none(self, mock_get):
        """Returns iata=None and confidence=0 when no code is present."""
        mock_get.return_value = _make_response(
            b"<p>This page has no airport codes at all.</p>"
        )
        result = _extract_iata_from_wikipedia_page("https://example.com")
        assert result["iata"] is None
        assert result["confidence"] == 0.0

    @patch(_REQUESTS_GET)
    def test_network_error_returns_error_dict(self, mock_get):
        """``requests.exceptions.ConnectionError`` is caught; returns error dict."""
        mock_get.side_effect = requests.exceptions.ConnectionError("timeout")
        result = _extract_iata_from_wikipedia_page("https://example.com")
        assert result["iata"] is None
        assert result["error"] is not None

    @patch(_REQUESTS_GET)
    def test_http_error_returns_error_dict(self, mock_get):
        """``requests.exceptions.HTTPError`` from raise_for_status is caught."""
        r = Mock()
        r.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        mock_get.return_value = r
        result = _extract_iata_from_wikipedia_page("https://example.com/missing")
        assert result["iata"] is None
        assert result["error"] is not None

    @patch(_REQUESTS_GET)
    def test_extracts_from_third_paragraph(self, mock_get):
        """Scans multiple paragraphs — finds code in paragraph 3."""
        mock_get.return_value = _make_response(b"""
            <html><body>
                <p>First paragraph, no code.</p>
                <p>Second paragraph, no code.</p>
                <p>Third paragraph (IATA: YUL, ICAO: CYUL)</p>
            </body></html>
        """)
        result = _extract_iata_from_wikipedia_page("https://example.com")
        assert result["iata"] == "YUL"

    @patch(_REQUESTS_GET)
    def test_four_letter_token_not_accepted_as_iata(self, mock_get):
        """IATA codes must be exactly 3 letters — 4-letter tokens are rejected."""
        mock_get.return_value = _make_response(
            b"<p>(IATA: LONG)</p>"
        )
        result = _extract_iata_from_wikipedia_page("https://example.com")
        assert result["iata"] != "LONG"

    @patch(_REQUESTS_GET)
    def test_disambiguation_page_skipped(self, mock_get):
        """Pages whose text includes 'may refer to' yield no extraction."""
        mock_get.return_value = _make_response(
            b"<p>This article may refer to multiple airports including YYZ.</p>"
        )
        result = _extract_iata_from_wikipedia_page("https://example.com")
        # Disambiguation guard should prevent a confident extraction
        assert result["iata"] is None or result["confidence"] < 0.9

    @patch(_REQUESTS_GET)
    def test_result_keys_always_present(self, mock_get):
        """Result dict always contains all expected keys regardless of outcome."""
        mock_get.return_value = _make_response(b"<p>no code</p>")
        result = _extract_iata_from_wikipedia_page("https://example.com")
        for key in ("iata", "icao", "confidence", "extracted_text", "error"):
            assert key in result


# ---------------------------------------------------------------------------
# extract_iata_from_unmapped_destinations
# ---------------------------------------------------------------------------

class TestExtractIataFromUnmappedDestinations:

    def test_raises_when_csv_missing(self):
        """FileNotFoundError when the CSV path does not exist."""
        with pytest.raises(FileNotFoundError):
            extract_iata_from_unmapped_destinations(
                csv_path="/nonexistent/path/file.csv"
            )

    def test_empty_csv_returns_zero_counts(self, tmp_path):
        """An empty (header-only) CSV yields all-zero summary counts."""
        csv_path = tmp_path / "unmapped.csv"
        _write_unmapped_csv(csv_path, [])
        result = extract_iata_from_unmapped_destinations(
            csv_path=str(csv_path), delay=0.0, verbose=False
        )
        assert result["total"]      == 0
        assert result["successful"] == 0
        assert result["skipped"]    == 0
        assert result["failed"]     == 0

    def test_existing_iata_counted_as_skipped(self, tmp_path):
        """A row that already has an IATA code is counted as skipped, not fetched."""
        csv_path = tmp_path / "unmapped.csv"
        _write_unmapped_csv(csv_path, [{
            "url":    "https://en.wikipedia.org/wiki/Toronto",
            "count":  "10",
            "iata":   "YYZ",
            "name":   "Toronto Pearson",
            "source": "manual",
        }])
        result = extract_iata_from_unmapped_destinations(
            csv_path=str(csv_path), delay=0.0, verbose=False
        )
        assert result["total"]   == 1
        assert result["skipped"] == 1
        assert result["successful"] == 0

    @patch(_REQUESTS_GET)
    def test_successful_extraction_increments_successful(self, mock_get, tmp_path):
        """A row without IATA that yields a code increments ``successful``."""
        mock_get.return_value = _make_response(
            b"<p>Airport (IATA: YYZ, ICAO: CYYZ)</p>"
        )
        csv_path = tmp_path / "unmapped.csv"
        _write_unmapped_csv(csv_path, [{
            "url":    "https://en.wikipedia.org/wiki/Toronto_Pearson",
            "count":  "5",
            "iata":   "",
            "name":   "",
            "source": "to_be_scraped",
        }])
        result = extract_iata_from_unmapped_destinations(
            csv_path=str(csv_path), delay=0.0, verbose=False
        )
        assert result["total"]      == 1
        assert result["successful"] == 1
        assert result["skipped"]    == 0

    @patch(_REQUESTS_GET)
    def test_failed_extraction_increments_failed(self, mock_get, tmp_path):
        """A row without IATA where the page has no code increments ``failed``."""
        mock_get.return_value = _make_response(b"<p>No code here.</p>")
        csv_path = tmp_path / "unmapped.csv"
        _write_unmapped_csv(csv_path, [{
            "url":    "https://en.wikipedia.org/wiki/SomeOtherPage",
            "count":  "1",
            "iata":   "",
            "name":   "",
            "source": "to_be_scraped",
        }])
        result = extract_iata_from_unmapped_destinations(
            csv_path=str(csv_path), delay=0.0, verbose=False
        )
        assert result["total"]  == 1
        assert result["failed"] == 1

    def test_return_dict_has_expected_keys(self, tmp_path):
        """Summary dict always contains all documented keys."""
        csv_path = tmp_path / "unmapped.csv"
        _write_unmapped_csv(csv_path, [])
        result = extract_iata_from_unmapped_destinations(
            csv_path=str(csv_path), delay=0.0, verbose=False
        )
        for key in ("total", "successful", "skipped", "failed", "csv_path"):
            assert key in result


# ---------------------------------------------------------------------------
# create_manual_mapping_from_scraped_data
# ---------------------------------------------------------------------------

class TestCreateManualMappingFromScrapedData:

    def test_raises_when_unmapped_csv_missing(self, tmp_path):
        """FileNotFoundError when unmapped_destinations.csv is absent."""
        with pytest.raises(FileNotFoundError):
            create_manual_mapping_from_scraped_data(
                unmapped_csv=str(tmp_path / "nonexistent.csv"),
                output_csv=str(tmp_path / "out.csv"),
            )

    def test_raises_on_invalid_confidence(self, tmp_path):
        """ValueError when min_confidence is outside [0, 1]."""
        csv_path = tmp_path / "unmapped.csv"
        _write_unmapped_csv(csv_path, [])
        with pytest.raises(ValueError, match="min_confidence"):
            create_manual_mapping_from_scraped_data(
                unmapped_csv=str(csv_path),
                output_csv=str(tmp_path / "out.csv"),
                min_confidence=1.5,
            )

    def test_high_confidence_entry_included(self, tmp_path):
        """Entry with conf >= threshold is written to the output file."""
        csv_path   = tmp_path / "unmapped.csv"
        output_csv = tmp_path / "mapping.csv"
        _write_unmapped_csv(csv_path, [{
            "url":    "https://example.com/1",
            "count":  "1",
            "iata":   "YYZ",
            "name":   "Toronto Pearson",
            "source": "scraped (conf: 0.95)",
        }])
        count = create_manual_mapping_from_scraped_data(
            unmapped_csv=str(csv_path),
            output_csv=str(output_csv),
            min_confidence=0.70,
            verbose=False,
        )
        assert count == 1
        assert output_csv.exists()
        with open(output_csv, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["iata"] == "YYZ"

    def test_low_confidence_entry_excluded(self, tmp_path):
        """Entry with conf < threshold is NOT written."""
        csv_path   = tmp_path / "unmapped.csv"
        output_csv = tmp_path / "mapping.csv"
        _write_unmapped_csv(csv_path, [
            {"url": "https://example.com/1", "count": "1", "iata": "YYZ",
             "name": "Toronto", "source": "scraped (conf: 0.95)"},   # pass
            {"url": "https://example.com/2", "count": "1", "iata": "ABC",
             "name": "Unknown", "source": "scraped (conf: 0.50)"},   # fail
        ])
        count = create_manual_mapping_from_scraped_data(
            unmapped_csv=str(csv_path),
            output_csv=str(output_csv),
            min_confidence=0.70,
            verbose=False,
        )
        assert count == 1

    def test_empty_iata_skipped(self, tmp_path):
        """Rows with an empty IATA value are not written."""
        csv_path   = tmp_path / "unmapped.csv"
        output_csv = tmp_path / "mapping.csv"
        _write_unmapped_csv(csv_path, [{
            "url":    "https://example.com/1",
            "count":  "1",
            "iata":   "",
            "name":   "Unknown",
            "source": "failed",
        }])
        count = create_manual_mapping_from_scraped_data(
            unmapped_csv=str(csv_path),
            output_csv=str(output_csv),
            verbose=False,
        )
        assert count == 0

    def test_multiple_valid_entries(self, tmp_path):
        """All entries above threshold are written."""
        csv_path   = tmp_path / "unmapped.csv"
        output_csv = tmp_path / "mapping.csv"
        _write_unmapped_csv(csv_path, [
            {"url": f"https://example.com/{i}", "count": str(i),
             "iata": code, "name": f"Airport {i}",
             "source": "scraped (conf: 0.95)"}
            for i, code in enumerate(["YYZ", "YUL", "YVR"], 1)
        ])
        count = create_manual_mapping_from_scraped_data(
            unmapped_csv=str(csv_path),
            output_csv=str(output_csv),
            verbose=False,
        )
        assert count == 3

    def test_output_csv_fieldnames(self, tmp_path):
        """Output CSV has exactly the expected column headers."""
        csv_path   = tmp_path / "unmapped.csv"
        output_csv = tmp_path / "mapping.csv"
        _write_unmapped_csv(csv_path, [{
            "url": "https://example.com/1", "count": "1",
            "iata": "YYZ", "name": "Toronto", "source": "scraped (conf: 0.95)",
        }])
        create_manual_mapping_from_scraped_data(
            unmapped_csv=str(csv_path),
            output_csv=str(output_csv),
            verbose=False,
        )
        with open(output_csv, encoding="utf-8") as fh:
            headers = csv.DictReader(fh).fieldnames
        assert set(headers) == {"url", "iata", "name", "source"}
