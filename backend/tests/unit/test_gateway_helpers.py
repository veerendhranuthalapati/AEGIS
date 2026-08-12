"""Gateway helper functions tests (pure)."""
from app.gateway.service import is_llm_path, normalize_endpoint


def test_normalize_endpoint_replaces_ids():
    assert normalize_endpoint("/api/users/42") == "/api/users/:id"
    assert normalize_endpoint("/api/users/42/orders/7") == "/api/users/:id/orders/:id"


def test_normalize_endpoint_leaves_names():
    assert normalize_endpoint("/api/auth/login") == "/api/auth/login"
    assert normalize_endpoint("/api/gateway/health") == "/api/gateway/health"


def test_is_llm_path():
    assert is_llm_path("/ai/chat")
    assert is_llm_path("/api/gateway/ai/chat")
    assert is_llm_path("/llm/completions")
    assert not is_llm_path("/api/users/1")
