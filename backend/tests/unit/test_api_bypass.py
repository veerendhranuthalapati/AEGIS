"""API rule-engine bypass regression tests.

Each case verifies that encoding/normalization cannot evade deterministic
detection. Fixes should improve normalization, not add one-off signatures.
"""
from __future__ import annotations

import pytest

from app.security.api.rules import ApiRulesEngine
from tests.conftest import make_ctx


@pytest.fixture
def engine() -> ApiRulesEngine:
    return ApiRulesEngine()


def _blocked(engine: ApiRulesEngine, **ctx_kwargs) -> bool:
    ctx = make_ctx(**ctx_kwargs)
    findings = engine.inspect(ctx, {})
    return len(findings) > 0


class TestSqliBypass:
    @pytest.mark.parametrize(
        "query",
        [
            "%27%20OR%201%3D1%20--",
            "%2527%20OR%201%3D1%20--",
            "1+%OR+1%3D1",
            "1+%OR+%1%3D1",
            "1%09OR%091%3D1",
            "1%0aOR%0a1%3D1",
            "' Or 1=1 --",
            "' OR 1=1 --",
        ],
    )
    def test_sqli_variants_blocked(self, engine: ApiRulesEngine, query: str) -> None:
        assert _blocked(engine, query_string=f"q={query}")


class TestPathTraversalBypass:
    @pytest.mark.parametrize(
        "payload",
        [
            "..%2F..%2Fetc%2Fpasswd",
            "..%252F..%252Fetc%252Fpasswd",
            "..%2f..%2fetc%2fpasswd",
            "..%5c..%5cetc%5cpasswd",
            "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        ],
    )
    def test_traversal_variants_blocked(self, engine: ApiRulesEngine, payload: str) -> None:
        assert _blocked(engine, query_string=f"q={payload}")


class TestSsrfBypass:
    @pytest.mark.parametrize(
        "target",
        [
            "http%3A%2F%2F169.254.169.254%2Flatest%2Fmeta-data%2F",
            "http%3A%2F%2F127.0.0.1%2Fadmin",
            "http%3A%2F%2F2130706433%2F",  # decimal 127.0.0.1
            "http%3A%2F%2F0x7f000001%2F",
        ],
    )
    def test_ssrf_variants_blocked(self, engine: ApiRulesEngine, target: str) -> None:
        assert _blocked(engine, query_string=f"url={target}")


class TestCmdInjectionBypass:
    @pytest.mark.parametrize(
        "payload",
        [
            "%3B%20id%3B%20whoami",
            "%3b%09id%3b%09whoami",
            "%7C%20id",
            ";%0aid;",
        ],
    )
    def test_cmd_variants_blocked(self, engine: ApiRulesEngine, payload: str) -> None:
        assert _blocked(engine, query_string=f"q={payload}")


class TestLegitimateTraffic:
    def test_benign_search_allowed(self, engine: ApiRulesEngine) -> None:
        ctx = make_ctx(query_string="q=weather+forecast")
        assert engine.inspect(ctx, {}) == []
