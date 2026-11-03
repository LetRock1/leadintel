"""The service answers, says when it is ready, and every response carries the security headers."""

from __future__ import annotations

from pathlib import Path

from app import __version__

MIGRATIONS = Path(__file__).resolve().parents[1] / "app" / "db" / "migrations" / "versions"


def test_health_answers_with_the_version(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_ready_checks_database_models_and_jobs(client):
    r = client.get("/api/ready")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": True, "lead_model": True, "uplift_model": True, "background_jobs": True}
    assert body["schema"] == sorted(p.stem for p in MIGRATIONS.glob("0*.py"))[-1]  # the newest migration


def test_security_headers_and_request_id(client):
    r = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert r.headers["Cache-Control"] == "no-store"
    assert client.get("/api/health").headers["X-Request-ID"]  # one is made when the caller sends none


def test_openapi_documents_both_apis(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "/api/v1/courses" in paths
    assert "/api/v1/auth/signup" in paths
    assert "/api/v1/crm/leads" in paths
    assert "/api/v1/crm/capacity" in paths


def test_validation_errors_name_the_field(client):
    r = client.post("/api/v1/auth/login", json={"email": "someone@example.com"})
    assert r.status_code == 422
    assert "password" in r.json()["detail"]


def test_unknown_routes_are_404_json(client):
    r = client.get("/api/v1/no-such-thing")
    assert r.status_code == 404
    assert r.json()["detail"]


def test_cors_allows_the_two_frontends(client):
    for origin in ("http://localhost:5173", "http://localhost:5174"):
        r = client.options("/api/v1/courses", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        assert r.headers.get("access-control-allow-origin") == origin
    r = client.options(
        "/api/v1/courses", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in r.headers
