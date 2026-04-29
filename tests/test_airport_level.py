import pytest
import unittest.mock as mock
import warnings

# This must be here since other tests expect requests.exceptions.RequestException and other things to not be mocked initially. We mock it manually only for this file.
try:
    import requests
except ImportError:
    pass

import wikipediaGATN.airport_level_functions as wal

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_url(mock_get):
    url = "https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport"

    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": [
                {"title": "Winnipeg James Armstrong Richardson International Airport"}
            ]
        }
    }
    mock_get.return_value = mock_response

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link(mock_get):
    url = "https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport"

    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": [
                {"title": "Winnipeg James Armstrong Richardson International Airport"}
            ]
        }
    }
    mock_get.return_value = mock_response

    assert wal.fetch_wikipedia_airport_link(url) == url

    with pytest.warns(UserWarning, match="Invalid Wikipedia URL"):
        assert wal.fetch_wikipedia_airport_link("https://example.com/not_a_wiki") is None

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_iata(mock_get):
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": [
                {"title": "Winnipeg James Armstrong Richardson International Airport"}
            ]
        }
    }
    mock_get.return_value = mock_response

    result = wal.fetch_wikipedia_airport_link("YWG")

    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["srsearch"] == "YWG airport"
    assert result == "https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport"

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_freetext(mock_get):
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": [
                {"title": "London Heathrow Airport"}
            ]
        }
    }
    mock_get.return_value = mock_response

    result = wal.fetch_wikipedia_airport_link("London Heathrow")

    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["srsearch"] == "London Heathrow airport"
    assert result == "https://en.wikipedia.org/wiki/London_Heathrow_Airport"

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_freetext_has_airport(mock_get):
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": [
                {"title": "London Heathrow Airport"}
            ]
        }
    }
    mock_get.return_value = mock_response

    result = wal.fetch_wikipedia_airport_link("London Heathrow Airport")

    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["srsearch"] == "London Heathrow Airport"
    assert result == "https://en.wikipedia.org/wiki/London_Heathrow_Airport"

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_request_exception(mock_get, caplog):
    import requests
    mock_get.side_effect = requests.exceptions.RequestException("Network error")

    result = wal.fetch_wikipedia_airport_link("YWG")

    assert "Wikipedia search failed" in caplog.text
    assert result is None

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_json_error(mock_get, caplog):
    mock_response = mock.MagicMock()
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_get.return_value = mock_response

    result = wal.fetch_wikipedia_airport_link("YWG")

    assert "Could not parse search response" in caplog.text
    assert result is None

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_no_results(mock_get):
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": []
        }
    }
    mock_get.return_value = mock_response

    with pytest.warns(UserWarning, match="No Wikipedia page found"):
        result = wal.fetch_wikipedia_airport_link("XYZ")

    assert result is None

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_prefer_airport_title(mock_get):
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": [
                {"title": "Los Angeles (city)"},
                {"title": "Los Angeles International Airport"}
            ]
        }
    }
    mock_get.return_value = mock_response

    result = wal.fetch_wikipedia_airport_link("LAX")

    assert result == "https://en.wikipedia.org/wiki/Los_Angeles_International_Airport"

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_verbose(mock_get, capsys):
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": [
                {"title": "Winnipeg James Armstrong Richardson International Airport"}
            ]
        }
    }
    mock_get.return_value = mock_response

    result = wal.fetch_wikipedia_airport_link("YWG", verbose=True)
    captured = capsys.readouterr()

    assert "Searching Wikipedia for: 'YWG airport'" in captured.out
    assert "Resolved 'YWG' -> 'Winnipeg James Armstrong Richardson International Airport'" in captured.out
    assert result == "https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport"

@mock.patch("wikipediaGATN.airport_level_functions._SESSION.get")
def test_fetch_wikipedia_airport_link_verbose_url(mock_get, capsys):
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "query": {
            "search": [
                {"title": "Winnipeg James Armstrong Richardson International Airport"}
            ]
        }
    }
    mock_get.return_value = mock_response

    url = "https://en.wikipedia.org/wiki/Winnipeg_James_Armstrong_Richardson_International_Airport"
    result = wal.fetch_wikipedia_airport_link(url, verbose=True)
    captured = capsys.readouterr()

    assert "Extracted page title from URL: Winnipeg James Armstrong Richardson International Airport" in captured.out
    assert result == url
