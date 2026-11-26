"""Tests for production security headers, rate limiting, and error handling."""

from fastapi.testclient import TestClient
from backend.core.config import settings
from backend.core.rate_limit import SlidingWindowRateLimiter
from backend.main import app, rate_limiter


client = TestClient(app, raise_server_exceptions=False)


def test_security_headers_and_request_id():
    response = client.get("/api/v1/health", headers={"X-Request-ID": "req-12345"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-12345"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_invalid_request_id_is_replaced():
    response = client.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces!"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad id with spaces!"
    assert len(response.headers["X-Request-ID"]) > 8


def test_index_served_with_no_cache():
    response = client.get("/")
    assert response.status_code == 200
    assert "no-cache" in response.headers.get("Cache-Control", "")


def test_sliding_window_rate_limiter_enforces_limit():
    limiter = SlidingWindowRateLimiter()
    assert limiter.allow("client-1", limit=2, window_seconds=60)[0] is True
    assert limiter.allow("client-1", limit=2, window_seconds=60)[0] is True
    allowed, retry_after = limiter.allow("client-1", limit=2, window_seconds=60)
    assert allowed is False
    assert retry_after >= 1


def test_verify_rate_limit_returns_429(monkeypatch):
    rate_limiter.clear()
    monkeypatch.setattr(settings, "RATE_LIMIT_VERIFY_PER_MINUTE", 2)
    # Trigger validation (422) twice, then 3rd request should be rate limited (429)
    assert client.post("/api/v1/verify", json={}).status_code == 422
    assert client.post("/api/v1/verify", json={}).status_code == 422
    blocked = client.post("/api/v1/verify", json={})
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "RateLimitExceeded"
    assert int(blocked.headers["Retry-After"]) >= 1
