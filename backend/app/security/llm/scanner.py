"""Deterministic prompt-injection and jailbreak scanning.

This layer is deliberately heuristic and is combined with the ML classifier
and (optionally) an external LLM analyzer. Security decisions never rely on
a single LLM judgment.
"""
from __future__ import annotations

import base64
import binascii
import html
import re
import unicodedata
import urllib.parse

from app.security.base import ATLAS_REFERENCE, Finding, SEVERITY_WEIGHT


def _finding(
    rule_id: str,
    name: str,
    severity: str,
    reasons: list[str],
    mitre: list[str],
    source: str = "llm",
    details: dict | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        name=name,
        severity=severity,
        score=SEVERITY_WEIGHT[severity],
        reasons=reasons,
        mitre=mitre,
        source=source,
        details=details,
    )


_DIRECT_INJECTION = re.compile(
    r"\b(ignore|disregard|forget|override|skip|bypass)\b[^.]{0,120}"
    r"\b(instructions|prompt|rules|directives|system message|system prompt|"
    r"previous instructions|all previous|above instructions)\b",
    re.IGNORECASE,
)
_DIRECT_INJECTION_2 = re.compile(
    r"\b(you are now|from now on|act as|pretend to be|imagine you are|"
    r"respond as|new instructions|new role)\b",
    re.IGNORECASE,
)
_SYSTEM_PROMPT_EXTRACTION = re.compile(
    r"\b(repeat your|show( me)? your|print( out)? your|reveal your|"
    r"display your|what (were you told|is your|are your|instructions? did you"
    r" receive|system prompt|initial prompt))\b[^.]{0,120}"
    r"\b(system prompt|instructions|prompt|rules|messages?|memory)\b",
    re.IGNORECASE,
)
_JAILBREAK = re.compile(
    r"\b(do anything now|jailbreak|jail broken|developer mode|dan\b|"
    r"aizawa|hypothetical scenario|fiction(?:al)? scenario|"
    r"role-play|roleplay|in this story|out of character|"
    r"unrestricted mode|no restrictions|no limits)\b",
    re.IGNORECASE,
)
_OVERRIDE = re.compile(
    r"\b(you must|you will|you are required|you have to|must obey|"
    r"always respond|respond only|say yes|do not refuse|"
    r"answer regardless|give me the answer)\b",
    re.IGNORECASE,
)
_SENSITIVE_EXTRACTION = re.compile(
    r"\b(show( me)? (all )?(users|employees|customers)|"
    r"select \* from (users|accounts|orders|credit|payment)|"
    r"list (all )?(users|accounts|emails|customers|ssns|credit cards)|"
    r"show (api key|password|secret|token|credentials|ssn|credit card)|"
    r"(the )?(database|schema|table) (schema|names)|"
    r"dump (the )?(database|table|users)|"
    r"other users['\u2019]? (data|information|private|emails))\b",
    re.IGNORECASE,
)
_TOOL_MANIPULATION = re.compile(
    r"\b(call|invoke|trigger|execute|run|use) (the )?(tool|function|command) "
    r"(called )?['\"]?[a-z_]+['\"]?\b",
    re.IGNORECASE,
)
_TOOL_TARGETS = re.compile(
    r"\b(delete_user|delete_user\s*\(|execute_payment|transfer_|send_email\s*\("
    r"|upload_file\s*\(|create_admin|grant_|revoke_|drop_|truncate )",
    re.IGNORECASE,
)
_URL_INSTRUCTION = re.compile(
    r"\b(open|fetch|load|retrieve|read|scrape) (this )?((the )?"
    r"(url|link|page|website|content)|https?://[^\s'\"]+)",
    re.IGNORECASE,
)
_OBFUSCATION_INSTRUCTION = re.compile(
    r"\b(decode|unpack|deobfuscate|decrypt|translate from|base64 (it|this)|"
    r"hex (encode|decode)|rot13|caesar|morse)\b",
    re.IGNORECASE,
)

# Obfuscation-resistant variants: matched against whitespace-stripped input
# so letter-spacing ("i g n o r e") cannot bypass detection.
_GLUED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "LLM-001",
        re.compile(
            r"ignore(?:all)?(?:previous|above|the)?instructions?"
            r"|disregard(?:all)?(?:previous|the)?instructions?"
            r"|forget(?:all)?(?:previous|the)?instructions?"
            r"|ignoreallrules|bypasstherules|overridetheinstructions",
            re.IGNORECASE,
        ),
    ),
    (
        "LLM-002",
        re.compile(
            r"(?:reveal|show|print|display|repeat)yourt?he?(initial)?(?:system)?prompt"
            r"|revealthe(?:system)?prompt|whatwereyoutold|whatisyour(systemprompt|prompt|initialprompt)",
            re.IGNORECASE,
        ),
    ),
    (
        "LLM-003",
        re.compile(
            r"doanythingnow|actasdan|jailbreak|jailbroken|developermode|"
            r"unrestrictedmode|norestrictions|nolimits|outofcharacter|inthisstory",
            re.IGNORECASE,
        ),
    ),
    (
        "LLM-004",
        re.compile(
            r"youmustobey|mustobeymy|alwaysrespond|respondonly|sayyes|"
            r"donotrefuse|neverrefuse|givemetheanswer",
            re.IGNORECASE,
        ),
    ),
    (
        "LLM-005",
        re.compile(
            r"showmeall(users|customers|employees|accounts)|listall(users|customers|employees|accounts)"
            r"|select\*from(users|accounts|orders|credit|payment)"
            r"|show(me)?(all)?(api)?(keys|apikeys|secrets|passwords)"
            r"|revealtheapikey|dump(ther)?database",
            re.IGNORECASE,
        ),
    ),
    (
        "LLM-006",
        re.compile(
            r"callthetool|invokethetool|executethetool|usethetool"
            r"|delete_user|grant_admin|execute_payment|create_admin|send_email\(",
            re.IGNORECASE,
        ),
    ),
    (
        "LLM-007",
        re.compile(
            r"openthisurl|fetchthisurl|loadthisurl|readthisurl|opentheurl|fetchthedata",
            re.IGNORECASE,
        ),
    ),
]

_ZERO_WIDTH = str.maketrans("", "", "\u200b\u200c\u200d\ufeff")
_B64_RUN = re.compile(r"[A-Za-z0-9+/=]{16,}")
_JSON_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")


def _json_unescape(text: str) -> str:
    """Decode JSON ``\\uXXXX`` escapes so encoded keywords cannot hide.

    Only ``\\uXXXX`` escapes are handled (no ``\\n`` etc.) to avoid mangling
    legitimately-escaped newlines/tabs in prompts.
    """
    return _JSON_ESCAPE.sub(
        lambda m: chr(int(m.group(0)[2:], 16)), text
    )


def _html_unescape(text: str) -> str:
    """Decode numeric + named HTML entities (``&#105;gnore``, ``&lt;``)."""
    try:
        return html.unescape(text)
    except Exception:  # noqa: BLE001
        return text


def _normalize_variants(text: str) -> list[str]:
    """Produce obfuscation-resistant variants of the prompt."""
    variants: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        if value not in seen:
            seen.add(value)
            variants.append(value)

    add(text)
    nfkc = unicodedata.normalize("NFKC", text)
    add(nfkc)
    no_zero = nfkc.translate(_ZERO_WIDTH)
    add(no_zero)
    de_spaced = re.sub(r"\s+", "", no_zero)
    add(de_spaced)
    try:
        unquoted = urllib.parse.unquote_to_bytes(no_zero).decode("utf-8", errors="ignore")
        add(unquoted)
    except Exception:  # noqa: BLE001
        pass
    for decoded in _b64_decoded(no_zero):
        add(decoded)
    json_decoded = _json_unescape(nfkc)
    if json_decoded != nfkc:
        add(json_decoded)
    html_decoded = _html_unescape(nfkc)
    if html_decoded != nfkc:
        add(html_decoded)
    return variants


def _b64_decoded(text: str) -> list[str]:
    decoded: list[str] = []
    for match in _B64_RUN.finditer(text):
        cand = match.group(0)
        padded = cand + "=" * (-len(cand) % 4)
        try:
            raw = base64.b64decode(padded, validate=False)
        except (binascii.Error, ValueError):
            continue
        try:
            out = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if len(out) < 8:
            continue
        printable = sum(c.isprintable() or c.isspace() for c in out)
        if printable / len(out) < 0.85:
            continue
        decoded.append(out)
    return decoded


class LlmScanner:
    """Deterministic scanner for LLM request payloads."""

    def scan(self, text: str | None) -> list[Finding]:
        if not text:
            return []
        text = text.strip()
        if len(text) > 200_000:
            text = text[:200_000]
        findings: list[Finding] = []

        for variant in _normalize_variants(text):
            self._scan_variant(variant, findings)

        return findings

    def _scan_variant(self, text: str, findings: list[Finding]) -> None:
        lower = text.lower()
        found = {f.rule_id for f in findings}

        if (
            not found.issuperset({"LLM-001"})
            and (
                _DIRECT_INJECTION.search(text)
                or _DIRECT_INJECTION_2.search(text)
                or _matches_glued("LLM-001", lower)
            )
        ):
            findings.append(
                _finding(
                    "LLM-001",
                    "Direct prompt injection",
                    "HIGH",
                    ["Prompt contains instruction-override phrases"],
                    [ATLAS_REFERENCE["prompt-injection"]["id"]],
                    details={"category": "direct_prompt_injection"},
                )
            )

        if (
            not found.issuperset({"LLM-002"})
            and (_SYSTEM_PROMPT_EXTRACTION.search(text) or _matches_glued("LLM-002", lower))
        ):
            findings.append(
                _finding(
                    "LLM-002",
                    "System prompt extraction attempt",
                    "HIGH",
                    ["Prompt attempts to extract the system prompt"],
                    [ATLAS_REFERENCE["prompt-injection"]["id"]],
                    details={"category": "system_prompt_extraction"},
                )
            )

        if (
            not found.issuperset({"LLM-003"})
            and (_JAILBREAK.search(text) or _matches_glued("LLM-003", lower))
        ):
            findings.append(
                _finding(
                    "LLM-003",
                    "Jailbreak attempt",
                    "HIGH",
                    ["Prompt uses known jailbreak/roleplay framing"],
                    [ATLAS_REFERENCE["prompt-injection"]["id"]],
                    details={"category": "jailbreak"},
                )
            )

        if (
            not found.issuperset({"LLM-004"})
            and (_OVERRIDE.search(text) or _matches_glued("LLM-004", lower))
        ):
            findings.append(
                _finding(
                    "LLM-004",
                    "Instruction override attempt",
                    "MEDIUM",
                    ["Prompt demands unconditional compliance"],
                    [ATLAS_REFERENCE["prompt-injection"]["id"]],
                    details={"category": "instruction_override"},
                )
            )

        if (
            not found.issuperset({"LLM-005"})
            and (_SENSITIVE_EXTRACTION.search(text) or _matches_glued("LLM-005", lower))
        ):
            findings.append(
                _finding(
                    "LLM-005",
                    "Sensitive information extraction",
                    "HIGH",
                    ["Prompt requests sensitive data"],
                    ["T1005"],
                    details={"category": "sensitive_extraction"},
                )
            )

        if (
            not found.issuperset({"LLM-006"})
            and (
                _TOOL_MANIPULATION.search(text)
                or _TOOL_TARGETS.search(text)
                or _matches_glued("LLM-006", lower)
            )
        ):
            findings.append(
                _finding(
                    "LLM-006",
                    "Tool manipulation attempt",
                    "HIGH",
                    ["Prompt attempts to invoke restricted tools"],
                    ["T1213"],
                    details={"category": "tool_manipulation"},
                )
            )

        if (
            not found.issuperset({"LLM-007"})
            and (_URL_INSTRUCTION.search(text) or _matches_glued("LLM-007", lower))
        ):
            findings.append(
                _finding(
                    "LLM-007",
                    "Suspicious fetch instruction",
                    "MEDIUM",
                    ["Prompt instructs the model to fetch external content"],
                    ["T1071"],
                    details={"category": "url_fetch"},
                )
            )

        if (
            not found.issuperset({"LLM-008"})
            and _OBFUSCATION_INSTRUCTION.search(text)
        ):
            findings.append(
                _finding(
                    "LLM-008",
                    "Obfuscation instruction",
                    "LOW",
                    ["Prompt requests decoding/obfuscation of content"],
                    ["T1027"],
                    details={"category": "obfuscation"},
                )
            )

        if (
            not found.issuperset({"LLM-009"})
            and (self._looks_like_base64(text) or self._hex_blob(text))
        ):
            findings.append(
                _finding(
                    "LLM-009",
                    "Encoded payload obfuscation",
                    "LOW",
                    ["Payload contains large encoded blobs"],
                    ["T1027"],
                    details={"category": "encoded_blob"},
                )
            )

    @staticmethod
    def _looks_like_base64(text: str) -> bool:
        lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 40]
        hits = 0
        for line in lines:
            try:
                decoded = base64.b64decode(line, validate=True)
                if decoded:
                    hits += 1
            except (binascii.Error, ValueError):
                continue
        return hits >= 2

    @staticmethod
    def _hex_blob(text: str) -> bool:
        return len(re.findall(r"\b[0-9a-f]{64}\b", text, re.IGNORECASE)) >= 2


def _matches_glued(rule_id: str, lower: str) -> bool:
    for rid, pattern in _GLUED_PATTERNS:
        if rid == rule_id and pattern.search(lower):
            return True
    return False


def scan_prompt_for_injection(text: str | None) -> list[Finding]:
    """Convenience wrapper."""
    return LlmScanner().scan(text)
