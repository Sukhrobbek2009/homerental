import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, settings
from app.main import GENERIC_ERROR_MESSAGE, app
from app.ratelimit import WINDOW_SECONDS, RateLimiter, limiter

ALLOWED_ORIGIN = settings.cors_origin_list[0]
OTHER_ORIGIN = "https://evil.example.com"


@app.get("/api/_test/boom")
def _boom() -> dict:
    raise RuntimeError("secret internal detail: db password is hunter2")


# ---- CORS ---------------------------------------------------------------


def test_listed_origin_is_allowed(client):
    response = client.get("/api/health", headers={"Origin": ALLOWED_ORIGIN})
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_unlisted_origin_gets_no_cors_headers(client):
    response = client.get("/api/health", headers={"Origin": OTHER_ORIGIN})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_unlisted_origin_is_refused(client):
    headers = {"Origin": OTHER_ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"}
    response = client.options("/api/auth/login", headers=headers)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_listed_origin_allows_auth_header(client):
    headers = {"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "PATCH", "Access-Control-Request-Headers": "authorization,content-type"}
    response = client.options("/api/listings/abc", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize("value", ["*", "https://ok.example.com,*", "https://*.example.com"])
def test_wildcard_cors_origins_are_refused(value):
    with pytest.raises(ValidationError, match="wildcards"):
        Settings(cors_origins=value)


@pytest.mark.parametrize("value", ["example.com", "https://example.com/app", "ftp://example.com"])
def test_malformed_cors_origins_are_refused(value):
    with pytest.raises(ValidationError):
        Settings(cors_origins=value)


def test_cors_origins_are_normalized():
    configured = Settings(cors_origins=" https://a.example.com/ , http://localhost:4000,, ")
    assert configured.cors_origin_list == ["https://a.example.com", "http://localhost:4000"]


# ---- Rate limiting ------------------------------------------------------


@pytest.fixture()
def rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 5)
    limiter.reset()
    yield
    limiter.reset()


def _login(client, headers=None):
    return client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "password1"}, headers=headers or {})


def test_sixth_login_in_a_minute_is_429(client, rate_limited):
    assert [_login(client).status_code for _ in range(5)] == [401] * 5

    blocked = _login(client)

    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert "Too many attempts" in blocked.json()["detail"]


def test_signup_is_limited_separately_from_login(client, rate_limited):
    for _ in range(5):
        _login(client)
    assert _login(client).status_code == 429

    statuses = [
        client.post(
            "/api/auth/signup",
            json={"full_name": "Rate Test", "email": f"rate-{i}@example.com", "password": "password1"},
        ).status_code
        for i in range(6)
    ]

    assert statuses == [201] * 5 + [429]


def test_limit_is_per_client_ip_behind_trusted_proxy(client, rate_limited, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    for _ in range(5):
        _login(client, {"X-Forwarded-For": "203.0.113.1"})
    assert _login(client, {"X-Forwarded-For": "203.0.113.1"}).status_code == 429

    assert _login(client, {"X-Forwarded-For": "203.0.113.2"}).status_code == 401
    # A client-supplied entry in front of the proxy's own doesn't change the key.
    assert _login(client, {"X-Forwarded-For": "198.51.100.9, 203.0.113.1"}).status_code == 429


def test_forged_forwarded_for_is_ignored_without_trusted_proxy(client, rate_limited):
    for i in range(5):
        _login(client, {"X-Forwarded-For": f"203.0.113.{i}"})

    assert _login(client, {"X-Forwarded-For": "203.0.113.99"}).status_code == 429


def test_window_expires():
    window = RateLimiter()
    key = ("login", "1.2.3.4")
    assert all(window.hit(key, 2, now=t) is None for t in (0.0, 1.0))
    assert window.hit(key, 2, now=2.0) == pytest.approx(WINDOW_SECONDS - 2.0)
    assert window.hit(key, 2, now=WINDOW_SECONDS + 0.5) is None


# ---- Unexpected errors ---------------------------------------------------


def test_unexpected_error_is_generic_500_and_logged(caplog):
    with TestClient(app, raise_server_exceptions=False) as quiet_client:
        with caplog.at_level(logging.ERROR, logger="app.errors"):
            response = quiet_client.get("/api/_test/boom", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == GENERIC_ERROR_MESSAGE
    assert "hunter2" not in response.text and "Traceback" not in response.text
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN

    [record] = [r for r in caplog.records if r.name == "app.errors"]
    assert body["error_id"] in record.getMessage()
    assert "hunter2" in caplog.text and "RuntimeError" in caplog.text


def test_expected_errors_are_unchanged(client):
    assert client.get("/api/listings/does-not-exist").json() == {"detail": "Listing not found"}


# ---- Request logging ------------------------------------------------------


def test_requests_are_logged_with_method_path_status_and_time(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.requests"):
        client.get("/api/health?probe=1")
        client.get("/api/listings/missing")

    messages = [r.getMessage() for r in caplog.records if r.name == "app.requests"]
    assert any(m.startswith("GET /api/health 200 ") and "ms" in m for m in messages), messages
    assert any(m.startswith("GET /api/listings/missing 404 ") for m in messages), messages
    assert not any("probe=1" in m for m in messages)
