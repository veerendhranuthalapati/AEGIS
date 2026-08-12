"""Deterministic PII / secret redaction tests."""
from app.core.redact import (
    contains_sensitive,
    redact_text,
    sensitivity_score,
)


def test_email_redacted():
    out, dets = redact_text("contact alice@example.com please")
    assert out == "contact [EMAIL REDACTED] please"
    assert len(dets) == 1


def test_ssn_redacted():
    out, dets = redact_text("ssn 123-45-6789")
    assert "[SSN REDACTED]" in out
    assert dets[0].label.value == "[SSN REDACTED]"


def test_api_key_redacted():
    out, _ = redact_text("key sk-bob-secret-5678 here")
    assert out == "key [API KEY REDACTED] here"


def test_aws_key_redacted():
    out, _ = redact_text("AKIAIOSFODNN7EXAMPLE")
    assert "[API KEY REDACTED]" in out


def test_private_ip_redacted():
    out, _ = redact_text("server at 10.0.4.12")
    assert "[PRIVATE IP REDACTED]" in out


def test_internal_url_redacted():
    out, _ = redact_text("connect to http://localhost:8080/db")
    assert "[INTERNAL URL REDACTED]" in out


def test_private_key_redacted():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAA==\n-----END RSA PRIVATE KEY-----"
    out, dets = redact_text(pem)
    assert "[PRIVATE KEY REDACTED]" in out
    assert len(dets) == 1


def test_valid_card_redacted_luhn():
    # 4111 1111 1111 1111 passes Luhn
    out, _ = redact_text("card 4111 1111 1111 1111")
    assert "[CARD REDACTED]" in out


def test_invalid_card_not_redacted():
    # 4111 1111 1111 1112 fails Luhn
    out, _ = redact_text("card 4111 1111 1111 1112")
    assert "[CARD REDACTED]" not in out


def test_contains_sensitive():
    assert contains_sensitive("user@example.com")
    assert not contains_sensitive("plain text nothing here")


def test_sensitivity_score():
    assert sensitivity_score("") == 0.0
    assert sensitivity_score("email a@b.com here") > 0.0
