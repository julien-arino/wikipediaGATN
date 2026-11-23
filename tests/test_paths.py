"""Tests for Windows-reserved filename escaping in :mod:`wikipediaGATN.paths`."""

import pytest

from wikipediaGATN.paths import (
    escape_reserved_code,
    is_reserved_code,
    unescape_reserved_code,
)

# Real airport codes that collide with Windows reserved device names.
RESERVED = ["AUX", "NUL", "PRN", "CON", "COM1", "COM9", "LPT1", "LPT9"]
# Ordinary codes that must pass through untouched.
NORMAL = ["YWG", "ORD", "SWGN", "PANU", "BKPR", "wiki_Winnipeg", "unknown"]


@pytest.mark.parametrize("code", RESERVED)
def test_reserved_codes_are_detected(code):
    assert is_reserved_code(code)
    assert is_reserved_code(code.lower())


@pytest.mark.parametrize("code", NORMAL)
def test_normal_codes_are_not_reserved(code):
    assert not is_reserved_code(code)


@pytest.mark.parametrize("code", RESERVED)
def test_reserved_codes_are_escaped_with_underscore(code):
    assert escape_reserved_code(code) == f"{code}_"


@pytest.mark.parametrize("code", NORMAL)
def test_normal_codes_are_not_escaped(code):
    assert escape_reserved_code(code) == code


@pytest.mark.parametrize("code", RESERVED + NORMAL)
def test_escape_unescape_round_trips(code):
    assert unescape_reserved_code(escape_reserved_code(code)) == code


def test_unescape_only_strips_reserved_underscore():
    # A trailing underscore on a non-reserved stem must be preserved.
    assert unescape_reserved_code("ABC_") == "ABC_"
    assert unescape_reserved_code("wiki_") == "wiki_"
    # But a reserved name plus underscore is unescaped.
    assert unescape_reserved_code("AUX_") == "AUX"
