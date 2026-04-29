"""
Tests for :mod:`wikipediaGATN.airport_level_functions`.
"""

import pytest
import requests
import warnings
from unittest.mock import Mock, patch
from wikipediaGATN.airport_level_functions import fetch_wikipedia_airport_html

# Correct patch target for the shared session in the module
_SESSION_GET = "wikipediaGATN.airport_level_functions._SESSION.get"

class TestFetchWikipediaAirportHtml:
    """Test suite for fetch_wikipedia_airport_html function."""

    @patch(_SESSION_GET)
    def test_get_html_success(self, mock_get):
        """Verify successful HTML retrieval from Wikipedia API."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "parse": {
                "text": "<html><body>Airport content</body></html>"
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        link = "https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport"
        result = fetch_wikipedia_airport_html(link)

        assert result == "<html><body>Airport content</body></html>"
        mock_get.assert_called_once()
        # Verify params
        args, kwargs = mock_get.call_args
        params = kwargs.get('params', {})
        assert params.get('page') == "Winnipeg James Armstrong Richardson International Airport"
        assert params.get('action') == "parse"
        assert params.get('prop') == "text"

    @patch(_SESSION_GET)
    def test_get_html_verbose(self, mock_get, capsys):
        """Verify verbose flag prints progress messages."""
        mock_response = Mock()
        mock_response.json.return_value = {"parse": {"text": "some html"}}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        link = "https://en.wikipedia.org/wiki/YWG"
        fetch_wikipedia_airport_html(link, verbose=True)

        captured = capsys.readouterr()
        assert "Fetching HTML for 'YWG'..." in captured.out
        assert "Fetched HTML for 'YWG' (9 chars)" in captured.out

    def test_get_html_invalid_url(self):
        """Verify handling of invalid Wikipedia URLs."""
        link = "https://example.com/not_a_wiki_link"
        with pytest.warns(UserWarning, match="Invalid Wikipedia URL"):
            result = fetch_wikipedia_airport_html(link)
        assert result is None

    @patch(_SESSION_GET)
    def test_get_html_request_exception(self, mock_get, caplog):
        """Verify handling of requests exceptions."""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")
        link = "https://en.wikipedia.org/wiki/YWG"
        result = fetch_wikipedia_airport_html(link)
        assert "Error fetching HTML for" in caplog.text
        assert result is None

    @patch(_SESSION_GET)
    def test_get_html_no_content(self, mock_get):
        """Verify handling of missing HTML content in API response."""
        mock_response = Mock()
        mock_response.json.return_value = {"parse": {}}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        link = "https://en.wikipedia.org/wiki/YWG"
        with pytest.warns(UserWarning, match="No HTML content returned"):
            result = fetch_wikipedia_airport_html(link)
        assert result is None

    @patch(_SESSION_GET)
    def test_get_html_json_error(self, mock_get, caplog):
        """Verify handling of malformed JSON or ValueErrors."""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Malformed JSON")
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        link = "https://en.wikipedia.org/wiki/YWG"
        result = fetch_wikipedia_airport_html(link)
        assert "Could not parse HTML response" in caplog.text
        assert result is None
