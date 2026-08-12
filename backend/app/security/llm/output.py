"""LLM output security: sensitive output detection and redaction.

Model output is treated as untrusted input. Before it reaches the client,
PII, secrets and dangerous instructions are detected. Sensitive values are
redacted and are never written to logs or the event store.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.redact import Detection, redact_text

_SYSTEM_PROMPT_LEAK = re.compile(
    r"\b(system prompt|system message|initial prompt|developer instructions)\b"
    r"[^.]{0,100}\b(was|is|you are an?)\b",
    re.IGNORECASE,
)
_DANGEROUS_INSTRUCTIONS = re.compile(
    r"\b(delete\s+(all|the)?\s*(user|account|record|data)|"
    r"drop\s+(table|database)|truncate\s+\w+|"
    r"rm\s+-rf|format\s+\w+:|"
    r"disable\s+(mfa|2fa|security)|revoke\s+(all\s+)?(permissions|access)|"
    r"transfer\s+all\s+(funds|money)|shut\s+down|kill\s+-9)\b",
    re.IGNORECASE,
)
_INTERNAL_HOSTNAME = re.compile(
    r"\b(?:[\w-]+\.)?(?:internal|intranet|corp|local)\.(?:local|lan|net)\b|"
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    re.IGNORECASE,
)


@dataclass
class OutputScanResult:
    redacted_text: str
    detections: list[Detection]
    findings: list[str]
    sensitivity_score: float


def scan_output(text: str | None) -> OutputScanResult:
    if not text:
        return OutputScanResult("", [], [], 0.0)
    redacted, detections = redact_text(text)
    findings: list[str] = []

    if detections:
        labels = {d.label for d in detections}
        findings.append(f"PII/secret detected in model output: {sorted(labels)}")

    if _SYSTEM_PROMPT_LEAK.search(text):
        findings.append("Possible system prompt leakage in model output")
    if _DANGEROUS_INSTRUCTIONS.search(text):
        findings.append("Dangerous instruction in model output")
    if _INTERNAL_HOSTNAME.search(text):
        findings.append("Internal host/IP reference in model output")

    score = min(1.0, 0.5 * (1 if detections else 0) + 0.5 * len(findings) / 3)
    return OutputScanResult(
        redacted_text=redacted,
        detections=detections,
        findings=findings,
        sensitivity_score=score,
    )
