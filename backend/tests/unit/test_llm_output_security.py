"""Output security for LLM provider responses."""
from __future__ import annotations

import json

from app.security.llm.output import scan_output


def test_pii_redacted_in_model_output() -> None:
    text = json.dumps(
        {"choices": [{"message": {"content": "User ssn=123-45-6789 email=a@b.com"}}]}
    )
    scan = scan_output(text)
    assert "123-45-6789" not in scan.redacted_text
    assert scan.detections


def test_api_key_redacted() -> None:
    text = 'Here is your key: sk-mock-internal-key-999'
    scan = scan_output(text)
    assert "sk-mock" not in scan.redacted_text


def test_internal_url_flagged() -> None:
    text = "Connect to db_host=10.0.4.12 or admin@corp.internal"
    scan = scan_output(text)
    assert scan.findings


def test_jwt_like_secret_redacted() -> None:
    text = "password=SuperSecret123! and api_key=sk-leaked-abcdefghijklmnop"
    scan = scan_output(text)
    assert "sk-leaked" not in scan.redacted_text
