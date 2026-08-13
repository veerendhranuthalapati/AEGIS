"""Adversarial model output scenarios — output scanner must handle dangerous content."""
from __future__ import annotations

import pytest

from app.security.llm.output import scan_output

OUTPUT_CASES: list[tuple[str, str, bool]] = [
    ("credentials", "password=SuperSecret123! api_key=sk-leaked-key-abcdef", True),
    ("pii", "Customer: Jane Doe, ssn=987-65-4321, card=4111111111111111", True),
    ("internal_url", "Visit http://10.0.4.12/admin or db.internal.corp", True),
    ("dangerous_instruction", "Run: rm -rf / and delete all user accounts", True),
    ("benign", "The capital of France is Paris.", False),
]


@pytest.mark.parametrize("name,text,should_flag", OUTPUT_CASES)
def test_output_scan(name: str, text: str, should_flag: bool) -> None:
    result = scan_output(text)
    if should_flag:
        assert result.findings or result.detections, f"{name} should be flagged"
    else:
        assert not result.detections
