"""Deterministic PII / secret / sensitive-value detection and redaction.

This is a first-pass, rule-based layer. It never attempts to be exhaustive;
the ML and contextual layers run on top of it. Redaction is applied before
any sensitive value can be written to logs, events, or returned downstream.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RedactLabel(str, Enum):
    EMAIL = "[EMAIL REDACTED]"
    PHONE = "[PHONE REDACTED]"
    CARD = "[CARD REDACTED]"
    SSN = "[SSN REDACTED]"
    SECRET = "[SECRET REDACTED]"
    TOKEN = "[TOKEN REDACTED]"
    KEY = "[API KEY REDACTED]"
    PRIVATE_KEY = "[PRIVATE KEY REDACTED]"
    CREDENTIAL = "[CREDENTIAL REDACTED]"
    URL_INTERNAL = "[INTERNAL URL REDACTED]"
    IP_PRIVATE = "[PRIVATE IP REDACTED]"


_PATTERNS: list[tuple[RedactLabel, re.Pattern[str]]] = [
    (
        RedactLabel.PRIVATE_KEY,
        re.compile(
            r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END "
            r"(RSA |EC |OPENSSH )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    (
        RedactLabel.KEY,
        re.compile(
            r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"
            r"|\bsk-[A-Za-z0-9-]{8,}\b"
            r"|\bxox[baprs]-[A-Za-z0-9-]{10,}\b"
            r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
            r"|\brk_live_[A-Za-z0-9]{20,}\b"
        ),
    ),
    (
        RedactLabel.EMAIL,
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        RedactLabel.PHONE,
        re.compile(
            r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"
        ),
    ),
    (
        RedactLabel.CARD,
        re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    ),
    (
        RedactLabel.SSN,
        re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
    ),
    (
        RedactLabel.URL_INTERNAL,
        re.compile(
            r"https?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+"
            r"|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)"
            r"(?::\d+)?(?:/[^\s'\"]*)?",
            re.IGNORECASE,
        ),
    ),
    (
        RedactLabel.IP_PRIVATE,
        re.compile(
            r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
        ),
    ),
]


def _luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    parity = len(digits) % 2
    total = 0
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


@dataclass
class Detection:
    label: RedactLabel
    value: str
    start: int
    end: int


def find_detections(text: str) -> list[Detection]:
    """Return all rule-based detections in ``text`` (non-overlapping)."""
    if not text:
        return []
    detections: list[Detection] = []
    for label, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if label is RedactLabel.CARD and not _luhn_valid(match.group(0)):
                continue
            detections.append(
                Detection(label, match.group(0), match.start(), match.end())
            )
    detections.sort(key=lambda d: (d.start, -(d.end - d.start)))
    merged: list[Detection] = []
    for detection in detections:
        if merged and detection.start < merged[-1].end:
            continue
        merged.append(detection)
    return merged


def redact_text(text: str) -> tuple[str, list[Detection]]:
    """Redact sensitive values in ``text``.

    Returns the redacted text and the list of detections. The original
    sensitive values are returned only to the caller that explicitly needs
    them; they are never logged by the audit/event pipeline.
    """
    detections = find_detections(text)
    if not detections:
        return text, []
    out: list[str] = []
    cursor = 0
    for detection in detections:
        out.append(text[cursor : detection.start])
        out.append(detection.label.value)
        cursor = detection.end
    out.append(text[cursor:])
    return "".join(out), detections


def contains_sensitive(text: str) -> bool:
    return bool(find_detections(text))


def sensitivity_score(text: str) -> float:
    """0..1 score reflecting how much sensitive content a string carries."""
    if not text:
        return 0.0
    detections = find_detections(text)
    if not detections:
        return 0.0
    covered = sum(d.end - d.start for d in detections)
    return min(1.0, covered / max(1, len(text)) + 0.4 * len(detections))


def sanitize_known_secrets(text: str, *secrets: str) -> str:
    """Remove known secret values from log-safe strings."""
    if not text:
        return text
    out = text
    for secret in secrets:
        if secret and len(secret) >= 8:
            out = out.replace(secret, "[SECRET REDACTED]")
    return out
