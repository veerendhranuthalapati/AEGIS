"""URL/form decoding for security inspection only.

These helpers normalize request fragments before deterministic rule matching.
They must **not** be used to rewrite the request forwarded to upstream services.
"""
from __future__ import annotations

import urllib.parse


def decode_for_inspection(raw: str, *, max_rounds: int = 2) -> str:
    """Decode application/x-www-form-urlencoded and percent-encoding for inspection.

    Handles:
    - ``+`` as space (form encoding)
    - Valid ``%XX`` hex sequences (including double-encoding within ``max_rounds``)
    - Malformed ``%`` prefixes used for evasion (``%OR`` → ``OR``, ``%1`` → ``1``)

    Bounded to ``max_rounds`` to avoid unbounded decoding loops.
    """
    if not raw:
        return ""
    current = raw.replace("+", " ")
    for _ in range(max_rounds):
        decoded = urllib.parse.unquote(current)
        if decoded == current:
            break
        current = decoded
    # After bounded decoding, strip leftover ``%`` from malformed evasion (%OR, %1).
    return current.replace("%", "")


def inspection_variants(*parts: str | None, max_rounds: int = 2) -> list[str]:
    """Return unique decoded variants (lowercased) for multi-pass rule scanning."""
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        for candidate in (part, decode_for_inspection(part, max_rounds=max_rounds)):
            lowered = candidate.lower()
            if lowered not in seen:
                seen.add(lowered)
                out.append(lowered)
    return out
