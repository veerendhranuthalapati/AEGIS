"""Shared detection primitives and MITRE ATT&CK/ATLAS metadata."""
from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY_WEIGHT = {"LOW": 0.25, "MEDIUM": 0.45, "HIGH": 0.7, "CRITICAL": 1.0}


@dataclass
class Finding:
    """A single security signal produced by any detection layer."""

    rule_id: str
    name: str
    severity: str
    score: float  # 0..1 contribution to the aggregate risk
    reasons: list[str] = field(default_factory=list)
    mitre: list[str] = field(default_factory=list)
    source: str = "rules"  # rules | ml | llm | behavior | correlation
    details: dict | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "severity": self.severity,
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "mitre": self.mitre,
            "source": self.source,
        }


# --- MITRE mappings (structured metadata, no invented techniques) ----------

MITRE_REFERENCE = {
    "account-takeover": {"id": "T1078", "name": "Valid Accounts", "source": "mitre-attack"},
    "brute-force": {"id": "T1110", "name": "Brute Force", "source": "mitre-attack"},
    "credential-stuffing": {
        "id": "T1110.004",
        "name": "Credential Stuffing",
        "source": "mitre-attack",
    },
    "scanning": {"id": "T1595", "name": "Active Scanning", "source": "mitre-attack"},
    "enumeration": {"id": "T1083", "name": "File and Directory Discovery", "source": "mitre-attack"},
    "protocol-abuse": {
        "id": "T1071",
        "name": "Application Layer Protocol",
        "source": "mitre-attack",
    },
    "exploit-public-facing": {
        "id": "T1190",
        "name": "Exploit Public-Facing Application",
        "source": "mitre-attack",
    },
    "command-execution": {
        "id": "T1059",
        "name": "Command and Scripting Interpreter",
        "source": "mitre-attack",
    },
    "data-exfiltration": {
        "id": "T1041",
        "name": "Exfiltration Over C2 Channel",
        "source": "mitre-attack",
    },
    "data-collection": {
        "id": "T1005",
        "name": "Data from Local System",
        "source": "mitre-attack",
    },
    "dos": {"id": "T1499", "name": "Endpoint Denial of Service", "source": "mitre-attack"},
    "privilege-escalation": {
        "id": "T1068",
        "name": "Exploitation for Privilege Escalation",
        "source": "mitre-attack",
    },
    "obfuscation": {
        "id": "T1027",
        "name": "Obfuscated Files or Information",
        "source": "mitre-attack",
    },
    "log-poisoning": {"id": "T1070", "name": "Indicator Removal", "source": "mitre-attack"},
    "resource-hijacking": {
        "id": "T1496",
        "name": "Resource Hijacking",
        "source": "mitre-attack",
    },
    "valid-account-abuse": {
        "id": "T1078",
        "name": "Valid Accounts",
        "source": "mitre-attack",
    },
}

ATLAS_REFERENCE = {
    "prompt-injection": {"id": "AML.T0051", "name": "LLM Prompt Injection", "source": "mitre-atlas"},
    "indirect-prompt-injection": {
        "id": "AML.T0024",
        "name": "Indirect Prompt Injection",
        "source": "mitre-atlas",
    },
}
