"""Deterministic API rules engine tests."""
from app.security.api.rules import ApiRulesEngine
from tests.conftest import make_ctx


def rule_ids(findings):
    return {f.rule_id for f in findings}


def test_sqli_detected_in_body():
    ctx = make_ctx(method="POST", body_text="' OR 1=1 --", headers={"content-type": "application/json"}, body_json=None)
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-006" in rule_ids(findings)


def test_sqli_detected_in_percent_encoded_query():
    ctx = make_ctx(query_string="q=%27%20OR%201=1%20--")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-006" in rule_ids(findings)


def test_sqli_detected_in_plus_encoded_query():
    ctx = make_ctx(query_string="q=%27+OR+1%3D1+--")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-006" in rule_ids(findings)


def test_sqli_detected_in_malformed_plus_evasion():
    ctx = make_ctx(query_string="q=1+%OR+%1%3D1")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-006" in rule_ids(findings)


def test_command_injection_plus_encoded_query():
    ctx = make_ctx(query_string="q=%3B+id%3B+whoami%3B+cat+%2Fetc%2Fpasswd")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-007" in rule_ids(findings)


def test_union_select_detected():
    ctx = make_ctx(body_text="UNION SELECT username,password FROM users")
    assert "API-006" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_path_traversal_detected():
    ctx = make_ctx(query_string="file=..%2F..%2Fetc%2Fpasswd")
    assert "API-005" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_path_traversal_plain_dots():
    ctx = make_ctx(query_string="file=../../etc/passwd")
    assert "API-005" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_command_injection_detected():
    ctx = make_ctx(query_string="q=%3B%20id%3B%20whoami")
    assert "API-007" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_ssrf_detected():
    ctx = make_ctx(query_string="url=http://169.254.169.254/latest/meta-data/")
    assert "API-008" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_xxe_detected():
    ctx = make_ctx(
        method="POST",
        headers={"content-type": "application/xml"},
        body_text="<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>",
    )
    assert "API-009" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_header_spoofing_detected():
    ctx = make_ctx(headers={"x-forwarded-for": "10.0.0.5"})
    assert "API-010" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_known_scanner_user_agent_detected():
    ctx = make_ctx(user_agent="sqlmap/1.7 (http://sqlmap.org)")
    assert "API-011" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_http_smuggling_detected():
    ctx = make_ctx(headers={"content-length": "10", "transfer-encoding": "chunked"})
    assert "API-003" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_trace_method_flagged():
    ctx = make_ctx(method="TRACE")
    assert "API-004" in rule_ids(ApiRulesEngine().inspect(ctx))


def test_bola_from_stats():
    ctx = make_ctx(actor_id="user-a")
    findings = ApiRulesEngine().inspect(ctx, stats={"bola_attempt": True})
    assert "API-016" in rule_ids(findings)


def test_rate_abuse_high():
    ctx = make_ctx(actor_id="user-a")
    findings = ApiRulesEngine().inspect(
        ctx, stats={"request_rate_per_min": 25.0, "baseline_rate_per_min": 1.0}
    )
    assert "API-013" in rule_ids(findings)
    matched = [f for f in findings if f.rule_id == "API-013"][0]
    assert matched.severity == "HIGH"


def test_rate_abuse_low_traffic_no_finding():
    ctx = make_ctx(actor_id="user-a")
    findings = ApiRulesEngine().inspect(
        ctx, stats={"request_rate_per_min": 2.0, "baseline_rate_per_min": 1.0}
    )
    assert "API-013" not in rule_ids(findings)


def test_rate_abuse_cold_start_no_finding():
    ctx = make_ctx(actor_id="user-a")
    findings = ApiRulesEngine().inspect(
        ctx, stats={"request_rate_per_min": 2.0, "baseline_rate_per_min": 0.0}
    )
    assert "API-013" not in rule_ids(findings)


def test_clean_request_no_findings():
    ctx = make_ctx(query_string="q=hello+world", user_agent="Mozilla/5.0")
    findings = ApiRulesEngine().inspect(ctx, stats={})
    assert findings == []


def test_inspection_does_not_mutate_request_context():
    """Normalization is inspection-only; forwarded query_string must stay raw."""
    raw_qs = "q=1+%OR+%1%3D1"
    ctx = make_ctx(query_string=raw_qs)
    ApiRulesEngine().inspect(ctx, stats={})
    assert ctx.query_string == raw_qs


def test_sqli_double_encoded_query():
    ctx = make_ctx(query_string="q=%2527%2520OR%25201%253D1%2520--")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-006" in rule_ids(findings)


def test_sqli_double_encoded_body():
    ctx = make_ctx(
        method="POST",
        body_text='{"q": "%2527%2520OR%25201%253D1%2520--"}',
        headers={"content-type": "application/json"},
    )
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-006" in rule_ids(findings)


def test_command_injection_ifs_substitution():
    ctx = make_ctx(query_string="cmd=${IFS}cat%20/etc/passwd")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-007" in rule_ids(findings)


def test_command_injection_env_interpreter():
    ctx = make_ctx(query_string="x=${ENV}python")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-007" in rule_ids(findings)


def test_ssrf_decimal_ip():
    ctx = make_ctx(query_string="url=http://2130706433/latest/meta-data/")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-008" in rule_ids(findings)


def test_ssrf_hex_ip():
    ctx = make_ctx(query_string="url=http://0x7f000001/")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-008" in rule_ids(findings)


def test_ssrf_dns_rebinding_domain():
    ctx = make_ctx(query_string="url=http://127.0.0.1.sslip.io/health")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-008" in rule_ids(findings)


def test_ssrf_decimal_ip_percent_encoded():
    ctx = make_ctx(query_string="url=http%3A%2F%2F2130706433%2F")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-008" in rule_ids(findings)


def test_ssrf_hex_ip_percent_encoded():
    ctx = make_ctx(query_string="url=http%3A%2F%2F0x7f000001%2F")
    findings = ApiRulesEngine().inspect(ctx)
    assert "API-008" in rule_ids(findings)
