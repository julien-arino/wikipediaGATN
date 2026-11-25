"""
Unit tests for the Wikipedia *parsers* — the code that actually extracts
airlines and destinations from a page.

These run fully offline against the small committed fixtures in
``tests/fixtures/wikitext`` and ``tests/fixtures/html`` (see
``tests/fixtures/README.md``).  No network access and no live crawl are
required.
"""

import warnings
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from wikipediaGATN import airport_level_functions as alf

FIXTURES = Path(__file__).parent / "fixtures"
WIKITEXT = (FIXTURES / "wikitext" / "winnipeg_sample.wikitext").read_text(
    encoding="utf-8"
)
AIRLINES_HTML = (FIXTURES / "html" / "airlines_destinations.html").read_text(
    encoding="utf-8"
)
PROSE_HTML = (FIXTURES / "html" / "prose_no_table.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestFeetToMetres:
    def test_converts_feet_string(self):
        # 783 ft -> 238.66 m
        assert alf._feet_to_metres("783") == "238.66"

    def test_strips_units_and_commas(self):
        assert alf._feet_to_metres("1,000 ft") == str(round(1000 * 0.3048, 2))

    def test_none_returns_none(self):
        assert alf._feet_to_metres(None) is None

    def test_unparseable_returns_input(self):
        assert alf._feet_to_metres("not a number") == "not a number"


class TestParseLatLonFromString:
    def test_decimal_pair(self):
        lat, lon = alf.parse_lat_lon_from_string("49.91, -97.24")
        assert lat.startswith("49.91")
        assert lon.startswith("-97.24")

    def test_invalid_returns_empty_and_warns(self):
        with pytest.warns(UserWarning):
            lat, lon = alf.parse_lat_lon_from_string("not-a-coordinate")
        assert (lat, lon) == ("", "")


class TestFormatAirportJson:
    def test_orders_known_keys_first(self):
        data = {"destinations": [], "iata": "YWG", "icao": "CYWG"}
        out = alf.format_airport_json(data)
        keys = list(out.keys())
        assert keys[0] == "iata"
        assert keys[1] == "icao"
        assert keys.index("iata") < keys.index("destinations")

    def test_preserves_unknown_keys(self):
        out = alf.format_airport_json({"iata": "YWG", "custom_extra": 1})
        assert out["custom_extra"] == 1


class TestCleanInfoboxValue:
    def test_nowrap_template_unwrapped(self):
        assert alf.clean_infobox_value("{{nowrap|783 ft}}") == "783 ft"

    def test_unbulleted_list_joined(self):
        assert alf.clean_infobox_value("{{Unbulleted list|A|B|C}}") == "A, B, C"

    def test_url_template_bare(self):
        assert alf.clean_infobox_value("{{URL|example.com}}") == "example.com"


class TestParseIso3166:
    def test_canada_manitoba(self):
        out = alf.parse_iso3166_2("CA-MB")
        assert out is not None
        assert out["country_alpha3"] == "CAN"
        assert out["country_name"] == "Canada"

    def test_invalid_returns_none(self):
        assert alf.parse_iso3166_2("ZZ-ZZ") is None


# ---------------------------------------------------------------------------
# Wikitext parsers (the primary data path)
# ---------------------------------------------------------------------------


class TestParseInfoboxFromWikitext:
    def test_empty_wikitext_returns_empty(self):
        assert alf.parse_infobox_from_wikitext("") == {}

    def test_no_infobox_returns_empty(self):
        assert alf.parse_infobox_from_wikitext("Just some prose, no template.") == {}

    def test_extracts_iata_icao(self):
        box = alf.parse_infobox_from_wikitext(WIKITEXT)
        assert box["IATA"] == "YWG"
        assert box["ICAO"] == "CYWG"

    def test_derives_lat_lon_from_coord(self):
        box = alf.parse_infobox_from_wikitext(WIKITEXT)
        # {{coord|49|54|36|N|097|14|24|W|...}} -> 49.91, -97.24
        assert box["lat"].startswith("49.91")
        assert box["lon"].startswith("-97.24")

    def test_resolves_region_to_country(self):
        box = alf.parse_infobox_from_wikitext(WIKITEXT)
        assert box["country_alpha3"] == "CAN"
        assert box["country_name"] == "Canada"

    def test_ignores_image_owner_operator_keys(self):
        box = alf.parse_infobox_from_wikitext(WIKITEXT)
        assert "image" not in box
        assert "owner" not in box
        assert "operator" not in box


class TestParseWikitextAirlinesDestinations:
    def test_passenger_airlines_extracted(self):
        result = alf.parse_wikitext_airlines_destinations(WIKITEXT)
        assert set(result["passenger"].keys()) == {"WestJet", "Air Canada"}

    def test_destination_names_and_urls(self):
        result = alf.parse_wikitext_airlines_destinations(WIKITEXT)
        westjet = {d["name"] for d in result["passenger"]["WestJet"]}
        assert westjet == {"Calgary", "Toronto"}
        urls = {d["wikipedia_url"] for d in result["passenger"]["WestJet"]}
        assert "https://en.wikipedia.org/wiki/Calgary_International_Airport" in urls

    def test_cargo_section_separated(self):
        result = alf.parse_wikitext_airlines_destinations(WIKITEXT)
        assert set(result["cargo"].keys()) == {"FedEx Express"}
        assert "FedEx Express" not in result["passenger"]


# ---------------------------------------------------------------------------
# HTML parsers (fallback path)
# ---------------------------------------------------------------------------


class TestFetchWikipediaAirlines:
    def test_extracts_airline_titles(self):
        soup = BeautifulSoup(AIRLINES_HTML, "html.parser")
        airlines = alf.fetch_wikipedia_airlines(soup=soup)
        assert airlines == {"WestJet", "Air Canada"}

    def test_empty_html_returns_empty_set(self):
        assert alf.fetch_wikipedia_airlines(html_content="") == set()


class TestFetchWikipediaDestinations:
    def test_extracts_destination_pairs(self):
        soup = BeautifulSoup(AIRLINES_HTML, "html.parser")
        dests = alf.fetch_wikipedia_destinations(soup=soup)
        names = {name for name, _url in dests}
        assert "Calgary International Airport" in names
        assert "Vancouver International Airport" in names
        for _name, url in dests:
            assert url.startswith("https://en.wikipedia.org/wiki/")


class TestFetchWikipediaAirlinesDestinations:
    def test_passenger_mapping(self):
        soup = BeautifulSoup(AIRLINES_HTML, "html.parser")
        result = alf.fetch_wikipedia_airlines_destinations(soup=soup)
        assert "WestJet" in result["passenger"]
        assert result["passenger"]["WestJet"] == {
            "Calgary International Airport",
            "Toronto Pearson International Airport",
        }

    def test_cargo_mapping_separated(self):
        soup = BeautifulSoup(AIRLINES_HTML, "html.parser")
        result = alf.fetch_wikipedia_airlines_destinations(soup=soup)
        assert "FedEx Express" in result["cargo"]
        assert "FedEx Express" not in result["passenger"]

    def test_maintenance_box_table_skipped(self):
        # The ambox table carries no airline links; if it were not skipped the
        # passenger mapping would be empty.
        soup = BeautifulSoup(AIRLINES_HTML, "html.parser")
        result = alf.fetch_wikipedia_airlines_destinations(soup=soup)
        assert result["passenger"]

    def test_table_data_not_flagged_as_fallback(self):
        # Data parsed from a real table is reliable: nlp_fallback stays False.
        soup = BeautifulSoup(AIRLINES_HTML, "html.parser")
        result = alf.fetch_wikipedia_airlines_destinations(soup=soup)
        assert result["nlp_fallback"] is False

    def test_nlp_fallback_flagged_when_used(self, monkeypatch):
        # A page with an "Airlines and destinations" section but no table falls
        # back to the NLP path; when that yields pairs the result is flagged.
        monkeypatch.setattr(
            alf,
            "parse_fallback_nlp_airlines_destinations",
            lambda *a, **k: {("Acme Air", "Springfield")},
        )
        soup = BeautifulSoup(PROSE_HTML, "html.parser")
        result = alf.fetch_wikipedia_airlines_destinations(soup=soup)
        assert result["nlp_fallback"] is True
        assert result["passenger"].get("Acme Air") == {"Springfield"}

    def test_empty_nlp_fallback_not_flagged(self, monkeypatch):
        # If the fallback finds nothing, the (empty) result stays "reliable".
        monkeypatch.setattr(
            alf,
            "parse_fallback_nlp_airlines_destinations",
            lambda *a, **k: set(),
        )
        soup = BeautifulSoup(PROSE_HTML, "html.parser")
        result = alf.fetch_wikipedia_airlines_destinations(soup=soup)
        assert result["nlp_fallback"] is False


class TestFallbackFetchWikipediaAirportInfo:
    def test_regex_extracts_codes_and_coords(self):
        info = alf.fallback_fetch_wikipedia_airport_info(PROSE_HTML)
        assert info["iata"] == "TST"
        assert info["icao"] == "KTST"
        assert info["coordinates"] == "45.12, -93.45"
        assert info["serves"] == "Test Regional Airport"


class TestNlpFallback:
    def test_returns_set_without_crashing(self):
        # spaCy's NER output is model-dependent, so we assert only the contract:
        # a set of (airline, destination) string pairs.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = alf.parse_fallback_nlp_airlines_destinations(PROSE_HTML)
        assert isinstance(result, set)
        for pair in result:
            assert isinstance(pair, tuple) and len(pair) == 2
