"""
Tests for ``refresh_airport_data.check_needs_refresh``.

``check_needs_refresh`` decides which stored airport JSON files are stale by
comparing each file's ``date-time-parse`` timestamp against the latest revision
timestamp returned by the Wikipedia API.  The Wikipedia API call is mocked with
``responses`` so the test is offline and deterministic, and ``time.sleep`` is
patched out so the per-batch politeness delay does not slow the suite.
"""

import json

import pytest
import responses

from wikipediaGATN import refresh_airport_data as rad

_API_URL = "https://en.wikipedia.org/w/api.php"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Remove the 0.5s politeness delay between API batches."""
    monkeypatch.setattr(rad.time, "sleep", lambda *_a, **_k: None)


def _write_airport(dir_path, code, url, dt_parse="2024-01-01T00:00:00Z"):
    payload = {"iata": code, "wikipedia_url": url}
    if dt_parse is not None:
        payload["date-time-parse"] = dt_parse
    fpath = dir_path / f"{code}.json"
    fpath.write_text(json.dumps(payload), encoding="utf-8")
    return str(fpath)


def _api_body(title, timestamp):
    return {
        "query": {
            "pages": {
                "123": {
                    "title": title,
                    "revisions": [{"timestamp": timestamp}],
                }
            }
        }
    }


def test_missing_timestamp_is_queued_without_network(tmp_path):
    # No date-time-parse -> must refresh; no API call should be needed.
    fpath = _write_airport(
        tmp_path, "YWG", "https://en.wikipedia.org/wiki/Foo", dt_parse=None
    )
    assert rad.check_needs_refresh([fpath]) == [fpath]


def test_file_without_url_is_skipped(tmp_path):
    fpath = tmp_path / "bad.json"
    fpath.write_text(json.dumps({"iata": "ZZZ"}), encoding="utf-8")
    assert rad.check_needs_refresh([str(fpath)]) == []


def test_broken_json_is_queued_for_repair(tmp_path):
    fpath = tmp_path / "broken.json"
    fpath.write_text("{ this is not json", encoding="utf-8")
    assert rad.check_needs_refresh([str(fpath)]) == [str(fpath)]


@responses.activate
def test_remote_newer_is_queued(tmp_path):
    fpath = _write_airport(
        tmp_path,
        "YWG",
        "https://en.wikipedia.org/wiki/Foo_Airport",
        dt_parse="2024-01-01T00:00:00Z",
    )
    responses.add(
        responses.GET,
        _API_URL,
        json=_api_body("Foo Airport", "2025-06-01T00:00:00Z"),
        status=200,
    )
    assert rad.check_needs_refresh([fpath]) == [fpath]


@responses.activate
def test_remote_older_is_not_queued(tmp_path):
    fpath = _write_airport(
        tmp_path,
        "YYC",
        "https://en.wikipedia.org/wiki/Bar_Airport",
        dt_parse="2025-01-01T00:00:00Z",
    )
    responses.add(
        responses.GET,
        _API_URL,
        json=_api_body("Bar Airport", "2024-06-01T00:00:00Z"),
        status=200,
    )
    assert rad.check_needs_refresh([fpath]) == []


@responses.activate
def test_api_error_does_not_raise(tmp_path):
    fpath = _write_airport(
        tmp_path,
        "YWG",
        "https://en.wikipedia.org/wiki/Foo_Airport",
        dt_parse="2024-01-01T00:00:00Z",
    )
    responses.add(responses.GET, _API_URL, status=500)
    # A failing API call is swallowed; the file is simply not flagged stale.
    assert rad.check_needs_refresh([fpath]) == []
