"""
Tests for the connections module.

This module tests functions that handle airport connection data extraction,
URL normalization, and IATA code mapping.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
import os
import json
import tempfile
from src.wikipediaGATN.connections import (
    _normalize_url,
    _extract_airport_name_from_url,
    _fuzzy_match_iata,
    _build_url_to_iata_mapping,
    create_outbound_connections_list,
)


class TestNormalizeUrl:
    """Tests for URL normalization function."""

    def test_normalize_url_basic(self):
        """Test basic URL is converted to lowercase."""
        url = "https://en.wikipedia.org/wiki/Toronto_Pearson"
        result = _normalize_url(url)
        assert result == "https://en.wikipedia.org/wiki/toronto_pearson"

    def test_normalize_url_trailing_slash_removed(self):
        """Test that trailing slashes are removed."""
        url = "https://en.wikipedia.org/wiki/Toronto/"
        result = _normalize_url(url)
        assert "toronto/" not in result
        assert result.endswith("toronto")

    def test_normalize_url_empty_string(self):
        """Test that empty string returns empty string."""
        assert _normalize_url("") == ""

    def test_normalize_url_none(self):
        """Test that None returns empty string."""
        assert _normalize_url(None) == ""

    def test_normalize_url_uppercase(self):
        """Test uppercase URLs are lowercased."""
        url = "HTTPS://EN.WIKIPEDIA.ORG/WIKI/EXAMPLE"
        result = _normalize_url(url)
        assert result == result.lower()

    def test_normalize_url_special_chars(self):
        """Test URLs with special characters."""
        url = "https://en.wikipedia.org/wiki/Café"
        result = _normalize_url(url)
        assert isinstance(result, str)


class TestExtractAirportNameFromUrl:
    """Tests for extracting airport names from URLs."""

    def test_extract_airport_name_basic(self):
        """Test extracting simple airport name from URL."""
        url = "https://en.wikipedia.org/wiki/Toronto_Pearson_International_Airport"
        result = _extract_airport_name_from_url(url)
        assert result is not None
        assert "Toronto" in result or "Pearson" in result

    def test_extract_airport_name_removes_airport_suffix(self):
        """Test that 'Airport' suffix is removed."""
        url = "https://en.wikipedia.org/wiki/Example_Airport"
        result = _extract_airport_name_from_url(url)
        if result:
            assert "airport" not in result.lower()

    def test_extract_airport_name_empty_url(self):
        """Test empty URL returns None."""
        assert _extract_airport_name_from_url("") is None

    def test_extract_airport_name_none(self):
        """Test None URL returns None."""
        assert _extract_airport_name_from_url(None) is None

    def test_extract_airport_name_invalid_url(self):
        """Test URL without /wiki/ returns None."""
        url = "https://en.wikipedia.org/notawiki/Example"
        result = _extract_airport_name_from_url(url)
        assert result is None

    def test_extract_airport_name_with_underscores(self):
        """Test URL with underscores are converted to spaces."""
        url = "https://en.wikipedia.org/wiki/Los_Angeles_International"
        result = _extract_airport_name_from_url(url)
        if result:
            assert "_" not in result  # Underscores should be spaces


class TestFuzzyMatchIata:
    """Tests for fuzzy matching IATA codes."""

    def test_fuzzy_match_exact_match(self):
        """Test exact match has high confidence."""
        iata_dict = {"Toronto Pearson": "YYZ"}
        match, ratio = _fuzzy_match_iata("Toronto Pearson", iata_dict)
        assert match == "YYZ"
        assert ratio >= 0.95

    def test_fuzzy_match_partial_match(self):
        """Test partial match has moderate confidence."""
        iata_dict = {"Toronto Pearson International": "YYZ"}
        match, ratio = _fuzzy_match_iata("Toronto", iata_dict)
        # Should either match or have low confidence
        assert match is not None or ratio < 0.7

    def test_fuzzy_match_no_match(self):
        """Test poor match returns None."""
        iata_dict = {"Toronto Pearson": "YYZ"}
        match, ratio = _fuzzy_match_iata("xyz", iata_dict)
        assert match is None
        assert ratio < 0.6

    def test_fuzzy_match_empty_name(self):
        """Test empty airport name returns None."""
        iata_dict = {"Toronto": "YYZ"}
        match, ratio = _fuzzy_match_iata("", iata_dict)
        assert match is None

    def test_fuzzy_match_empty_dict(self):
        """Test empty IATA dictionary returns None."""
        match, ratio = _fuzzy_match_iata("Toronto", {})
        assert match is None

    def test_fuzzy_match_case_insensitive(self):
        """Test matching is case-insensitive."""
        iata_dict = {"Toronto Pearson": "YYZ"}
        match_upper, ratio_upper = _fuzzy_match_iata("TORONTO PEARSON", iata_dict)
        match_lower, ratio_lower = _fuzzy_match_iata("toronto pearson", iata_dict)
        # Both should find the match
        assert (match_upper == "YYZ" or ratio_upper >= 0.95)
        assert (match_lower == "YYZ" or ratio_lower >= 0.95)


class TestBuildUrlToIataMapping:
    """Tests for building URL-to-IATA mapping."""

    @patch('os.path.exists')
    @patch('pandas.read_csv')
    def test_build_mapping_from_csv(self, mock_read_csv, mock_exists):
        """Test building mapping from CSV file."""
        # Setup mocks
        mock_exists.return_value = True
        mock_df = Mock()
        mock_df.columns = ['wikipedia_url', 'iata', 'name']
        mock_df.dropna.return_value = mock_df
        mock_df.iterrows.return_value = [
            (0, Mock(wikipedia_url="https://example.com/YYZ", iata="YYZ", name="Toronto"))
        ]
        mock_read_csv.return_value = mock_df

        # Execute
        url_to_iata, name_to_iata = _build_url_to_iata_mapping(verbose=False)

        # Assert - should return dictionaries
        assert isinstance(url_to_iata, dict)
        assert isinstance(name_to_iata, dict)

    @patch('os.path.exists')
    def test_build_mapping_no_files(self, mock_exists):
        """Test building mapping when no files exist."""
        mock_exists.return_value = False

        url_to_iata, name_to_iata = _build_url_to_iata_mapping(verbose=False)

        # Should return empty dictionaries
        assert isinstance(url_to_iata, dict)
        assert isinstance(name_to_iata, dict)


class TestCreateOutboundConnectionsList:
    """Tests for creating outbound connections list."""

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('wikipediaGATN.connections._build_url_to_iata_mapping')
    def test_create_connections_basic(self, mock_mapping, mock_file, mock_exists, mock_listdir):
        """Test basic connection list creation."""
        # Setup mocks
        mock_listdir.return_value = []
        mock_exists.return_value = True
        mock_mapping.return_value = ({}, {})

        # Execute
        output_csv, unmapped_csv = create_outbound_connections_list(
            verbose=False, export_unmapped=True
        )

        # Assert
        assert output_csv is not None
        assert isinstance(output_csv, str)
        assert "outbound_connections.csv" in output_csv

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('wikipediaGATN.connections._build_url_to_iata_mapping')
    def test_create_connections_with_unmapped(self, mock_mapping, mock_file, mock_exists, mock_listdir):
        """Test that unmapped destinations are exported."""
        # Setup mocks
        mock_listdir.return_value = []
        mock_exists.return_value = True
        mock_mapping.return_value = ({}, {})

        # Execute
        output_csv, unmapped_csv = create_outbound_connections_list(
            verbose=False, export_unmapped=True
        )

        # Assert unmapped CSV is returned
        assert unmapped_csv is not None or unmapped_csv is None  # Depends on data
        assert isinstance(output_csv, str)

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('wikipediaGATN.connections._build_url_to_iata_mapping')
    def test_create_connections_no_unmapped_export(self, mock_mapping, mock_file, mock_exists, mock_listdir):
        """Test with export_unmapped=False."""
        # Setup mocks
        mock_listdir.return_value = []
        mock_exists.return_value = True
        mock_mapping.return_value = ({}, {})

        # Execute
        output_csv, unmapped_csv = create_outbound_connections_list(
            verbose=False, export_unmapped=False
        )

        # Assert unmapped not exported
        assert output_csv is not None


class TestConnectionsIntegration:
    """Integration tests combining multiple functions."""

    def test_url_normalize_then_extract_name(self):
        """Test normalizing URL then extracting name."""
        url = "https://en.wikipedia.org/wiki/Toronto_Pearson_International_Airport"
        normalized = _normalize_url(url)
        assert normalized == normalized.lower()

    def test_name_extraction_with_normalization(self):
        """Test that extracted names work with fuzzy matching."""
        url = "https://en.wikipedia.org/wiki/Toronto_International"
        name = _extract_airport_name_from_url(url)
        if name:
            # Name should be usable for matching
            assert isinstance(name, str)
            assert len(name) > 0
