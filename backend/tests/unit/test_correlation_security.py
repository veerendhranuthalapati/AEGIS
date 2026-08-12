"""Correlation engine security and correctness tests."""
from __future__ import annotations

from datetime import datetime, timezone

from app.security.correlation.engine import EventLike, correlate


def _event(
    event_id: str,
    event_type: str,
    *,
    correlation_key: str | None = "actor-1",
    severity: str = "HIGH",
) -> EventLike:
    return EventLike(
        event_id=event_id,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        actor_id=correlation_key,
        source_ip="127.0.0.1",
        endpoint="/test",
        correlation_key=correlation_key,
        mitre=["T1190"],
    )


def test_correlates_injection_campaign():
    events = [
        _event("e1", "SQLI_INDICATOR"),
        _event("e2", "PATH_TRAVERSAL"),
        _event("e3", "SSRF_INDICATOR"),
    ]
    incidents = correlate(events)
    assert len(incidents) >= 1
    assert any("injection" in i.attack_type.lower() for i in incidents)


def test_unrelated_single_events_do_not_over_correlate():
    events = [_event("e1", "SQLI_INDICATOR")]
    incidents = correlate(events)
    assert incidents == []


def test_duplicate_event_ids_not_double_counted():
    events = [
        _event("e1", "SQLI_INDICATOR"),
        _event("e1", "SQLI_INDICATOR"),
        _event("e2", "PATH_TRAVERSAL"),
    ]
    incidents = correlate(events)
    for inc in incidents:
        assert len(inc.related_event_ids) == len(set(inc.related_event_ids))


def test_malformed_empty_events_safe():
    assert correlate([]) == []


def test_timeline_sorted_chronologically():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        EventLike(
            event_id="late",
            event_type="SQLI_INDICATOR",
            timestamp=base.replace(hour=3),
            severity="HIGH",
            actor_id="a",
            source_ip="1.1.1.1",
            endpoint="/s",
            correlation_key="a",
        ),
        EventLike(
            event_id="early",
            event_type="PATH_TRAVERSAL",
            timestamp=base.replace(hour=1),
            severity="HIGH",
            actor_id="a",
            source_ip="1.1.1.1",
            endpoint="/s",
            correlation_key="a",
        ),
    ]
    incidents = correlate(events)
    assert incidents
    times = [t["time"] for t in incidents[0].timeline]
    assert times == sorted(times)
