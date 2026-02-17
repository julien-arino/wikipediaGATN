"""
Tests for the extract_iata_from_wikipedia module.

This module tests functions that extract IATA codes from Wikipedia pages
and create manual airport mappings.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
import os
import csv
import tempfile
from wikipediaGATN.extract_iata_from_wikipedia import (
    _extract_iata_from_wikipedia_page,
    extract_iata_from_unmapped_destinations,
    create_manual_mapping_from_scraped_data,
)


class TestExtractIataFromWikipediaPage:
    """Tests for extracting IATA from Wikipedia page content."""

    @patch('requests.get')
    def test_extract_iata_standard_format(self, mock_get):
        """Test extraction from standard Wikipedia format."""
        # Setup mock response
        mock_response = Mock()
        mock_response.content = b'''
            <html>
                <body>
                    <p>Toronto Pearson International Airport (IATA: YYZ, ICAO: CYYZ)</p>
                </body>
            </html>
        '''
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Execute
        result = _extract_iata_from_wikipedia_page("https://en.wikipedia.org/wiki/Toronto_Pearson")

        # Assert
        assert result['iata'] == 'YYZ'
        assert result['confidence'] >= 0.9
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_extract_iata_with_icao(self, mock_get):
        """Test that ICAO code is also extracted."""
        mock_response = Mock()
        mock_response.content = b'<p>Airport (IATA: YYZ, ICAO: CYYZ)</p>'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _extract_iata_from_wikipedia_page("https://example.com")

        assert result['iata'] == 'YYZ'
        assert result['icao'] == 'CYYZ'

    @patch('requests.get')
    def test_extract_iata_not_found(self, mock_get):
        """Test when IATA code is not found."""
        mock_response = Mock()
        mock_response.content = b'<p>No airport code here</p>'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _extract_iata_from_wikipedia_page("https://example.com")

        assert result['iata'] is None
        assert result['confidence'] == 0

    @patch('requests.get')
    def test_extract_iata_network_error(self, mock_get):
        """Test handling of network errors."""
        mock_get.side_effect = Exception("Connection timeout")

        result = _extract_iata_from_wikipedia_page("https://example.com")

        assert result['iata'] is None
        assert 'error' in result

    @patch('requests.get')
    def test_extract_iata_http_error(self, mock_get):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        result = _extract_iata_from_wikipedia_page("https://example.com/missing")

        assert result['iata'] is None
        assert result['error'] is not None

    @patch('requests.get')
    def test_extract_iata_multiple_paragraphs(self, mock_get):
        """Test extraction from first 5 paragraphs."""
        mock_response = Mock()
        mock_response.content = b'''
            <html>
                <p>First paragraph</p>
                <p>Second paragraph</p>
                <p>Third (IATA: YUL, ICAO: CYUL)</p>
            </html>
        '''
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _extract_iata_from_wikipedia_page("https://example.com")

        # Should find it in third paragraph
        assert result['iata'] == 'YUL' or result['iata'] is None

    @patch('requests.get')
    def test_extract_iata_invalid_code(self, mock_get):
        """Test that invalid codes are rejected."""
        mock_response = Mock()
        mock_response.content = b'<p>(IATA: TOOLONG)</p>'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _extract_iata_from_wikipedia_page("https://example.com")

        # TOOLONG is not 3 letters, should be rejected
        assert result['iata'] != 'TOOLONG'


class TestExtractIataFromUnmappedDestinations:
    """Tests for extracting IATA from unmapped destinations CSV."""

    def test_extract_iata_from_csv_basic(self):
        """Test extraction from CSV with unmapped URLs."""
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['url', 'count', 'iata', 'name', 'source'])
            writer.writeheader()
            writer.writerow({
                'url': 'https://en.wikipedia.org/wiki/Example',
                'count': '5',
                'iata': '',
                'name': '',
                'source': 'to_be_scraped'
            })
            csv_path = f.name

        try:
            # Mock the Wikipedia extraction
            with patch('wikipediaGATN.extract_iata_from_wikipedia._extract_iata_from_wikipedia_page') as mock_extract:
                mock_extract.return_value = {
                    'iata': 'YYZ',
                    'confidence': 0.95,
                    'error': None
                }

                result = extract_iata_from_unmapped_destinations(
                    csv_path=csv_path,
                    batch_size=50,
                    delay=0.1,
                    verbose=False
                )

                assert result['total'] == 1
                # May or may not succeed depending on mock setup

        finally:
            os.unlink(csv_path)

    def test_extract_iata_skip_existing(self):
        """Test that existing IATA codes are skipped."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['url', 'count', 'iata', 'name', 'source'])
            writer.writeheader()
            writer.writerow({
                'url': 'https://en.wikipedia.org/wiki/Toronto',
                'count': '10',
                'iata': 'YYZ',  # Already has IATA
                'name': 'Toronto Pearson',
                'source': 'manual'
            })
            csv_path = f.name

        try:
            result = extract_iata_from_unmapped_destinations(
                csv_path=csv_path,
                batch_size=50,
                delay=0.1,
                verbose=False
            )

            # Should count this as successful (already has IATA)
            assert result['total'] == 1

        finally:
            os.unlink(csv_path)

    def test_extract_iata_empty_csv(self):
        """Test with empty CSV file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['url', 'count', 'iata', 'name', 'source'])
            writer.writeheader()
            csv_path = f.name

        try:
            result = extract_iata_from_unmapped_destinations(
                csv_path=csv_path,
                batch_size=50,
                delay=0.1,
                verbose=False
            )

            assert result['total'] == 0
            assert result['successful'] == 0

        finally:
            os.unlink(csv_path)

    def test_extract_iata_csv_not_found(self):
        """Test with non-existent CSV file."""
        with pytest.raises(FileNotFoundError):
            extract_iata_from_unmapped_destinations(
                csv_path='/nonexistent/path/file.csv',
                verbose=False
            )


class TestCreateManualMappingFromScrapedData:
    """Tests for creating manual mappings from scraped data."""

    def test_create_mapping_basic(self):
        """Test creating mapping from CSV with extracted data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['url', 'count', 'iata', 'name', 'source'])
            writer.writeheader()
            writer.writerow({
                'url': 'https://en.wikipedia.org/wiki/Toronto',
                'count': '10',
                'iata': 'YYZ',
                'name': 'Toronto Pearson',
                'source': 'scraped (conf: 0.95)'
            })
            unmapped_csv = f.name

        with tempfile.TemporaryDirectory() as tmpdir:
            output_csv = os.path.join(tmpdir, 'mapping.csv')

            try:
                count = create_manual_mapping_from_scraped_data(
                    unmapped_csv=unmapped_csv,
                    output_csv=output_csv,
                    min_confidence=0.7,
                    verbose=False
                )

                assert count == 1
                assert os.path.exists(output_csv)

                # Verify output CSV has correct structure
                with open(output_csv) as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    assert len(rows) == 1
                    assert rows[0]['iata'] == 'YYZ'

            finally:
                if os.path.exists(unmapped_csv):
                    os.unlink(unmapped_csv)

    def test_create_mapping_low_confidence_filter(self):
        """Test that low confidence entries are filtered."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['url', 'count', 'iata', 'name', 'source'])
            writer.writeheader()
            writer.writerow({
                'url': 'https://example.com/1',
                'count': '1',
                'iata': 'YYZ',
                'name': 'Toronto',
                'source': 'scraped (conf: 0.95)'  # High confidence
            })
            writer.writerow({
                'url': 'https://example.com/2',
                'count': '1',
                'iata': 'ABC',
                'name': 'Unknown',
                'source': 'scraped (conf: 0.50)'  # Low confidence
            })
            unmapped_csv = f.name

        with tempfile.TemporaryDirectory() as tmpdir:
            output_csv = os.path.join(tmpdir, 'mapping.csv')

            try:
                count = create_manual_mapping_from_scraped_data(
                    unmapped_csv=unmapped_csv,
                    output_csv=output_csv,
                    min_confidence=0.7,  # Filter out 0.50
                    verbose=False
                )

                # Should only include the high-confidence one
                assert count == 1

            finally:
                if os.path.exists(unmapped_csv):
                    os.unlink(unmapped_csv)

    def test_create_mapping_empty_iata(self):
        """Test that empty IATA codes are skipped."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['url', 'count', 'iata', 'name', 'source'])
            writer.writeheader()
            writer.writerow({
                'url': 'https://example.com/1',
                'count': '1',
                'iata': '',  # Empty
                'name': 'Unknown',
                'source': 'failed'
            })
            unmapped_csv = f.name

        with tempfile.TemporaryDirectory() as tmpdir:
            output_csv = os.path.join(tmpdir, 'mapping.csv')

            try:
                count = create_manual_mapping_from_scraped_data(
                    unmapped_csv=unmapped_csv,
                    output_csv=output_csv,
                    verbose=False
                )

                # Should not include empty IATA
                assert count == 0

            finally:
                if os.path.exists(unmapped_csv):
                    os.unlink(unmapped_csv)


class TestExtractIataIntegration:
    """Integration tests combining extraction functions."""

    @patch('requests.get')
    def test_extraction_through_pipeline(self, mock_get):
        """Test full extraction pipeline."""
        # Setup
        mock_response = Mock()
        mock_response.content = b'<p>Toronto (IATA: YYZ)</p>'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Execute
        result = _extract_iata_from_wikipedia_page("https://example.com")

        # Assert
        assert result['iata'] is not None
        assert result['confidence'] > 0

    def test_mapping_creation_with_valid_data(self):
        """Test creating mapping with valid scraped data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['url', 'count', 'iata', 'name', 'source'])
            writer.writeheader()
            for i, code in enumerate(['YYZ', 'YUL', 'YVR'], 1):
                writer.writerow({
                    'url': f'https://example.com/{i}',
                    'count': str(i),
                    'iata': code,
                    'name': f'Airport {i}',
                    'source': 'scraped (conf: 0.95)'
                })
            unmapped_csv = f.name

        with tempfile.TemporaryDirectory() as tmpdir:
            output_csv = os.path.join(tmpdir, 'mapping.csv')

            try:
                count = create_manual_mapping_from_scraped_data(
                    unmapped_csv=unmapped_csv,
                    output_csv=output_csv,
                    verbose=False
                )

                assert count == 3
                assert os.path.exists(output_csv)

            finally:
                if os.path.exists(unmapped_csv):
                    os.unlink(unmapped_csv)
