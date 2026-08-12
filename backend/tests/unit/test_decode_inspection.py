"""Tests for inspection-only URL/form decoding."""
from app.security.api.decode import decode_for_inspection


def test_plus_encoded_sqli_evasion():
    result = decode_for_inspection("1+%OR+%1%3D1").lower()
    assert "or 1=1" in result


def test_percent_encoded_sqli():
    assert decode_for_inspection("%27+OR+1%3D1+--").lower() == "' or 1=1 --"


def test_double_encoded_sqli():
    assert decode_for_inspection("%2527%2520OR%25201%253D1%2520--").lower() == "' or 1=1 --"


def test_plus_as_space_benign():
    assert decode_for_inspection("hello+world") == "hello world"


def test_valid_percent_space():
    assert decode_for_inspection("hello%20world") == "hello world"


def test_malformed_percent_or():
    assert decode_for_inspection("%OR") == "OR"


def test_bounded_rounds_no_infinite():
    # Triple-encoded quote — two rounds leave one encoding step undecoded.
    result = decode_for_inspection("%252527", max_rounds=2)
    assert result in ("27", "'")
