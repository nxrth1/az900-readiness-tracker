import json
import logging
import sqlite3

from fastapi.testclient import TestClient

from app.logging_config import configure_logging, get_logger, request_id_var

L = "learner-mw-test-0001"


def test_every_response_has_a_request_id(client):
    r = client.get("/api/health")
    assert len(r.headers["X-Request-ID"]) >= 6
    assert client.get("/api/health").headers["X-Request-ID"] != r.headers["X-Request-ID"]


def test_sane_incoming_request_id_is_kept_and_unsafe_one_replaced(client):
    assert client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"}).headers["X-Request-ID"] == "trace-abc-123"
    evil = client.get("/api/health", headers={"X-Request-ID": "x\r\nSet-Cookie: a=b"})
    assert "Set-Cookie" not in evil.headers and evil.headers["X-Request-ID"] != "x"


def test_security_headers_and_csp(client):
    page = client.get("/")
    assert page.headers["X-Content-Type-Options"] == "nosniff"
    assert page.headers["X-Frame-Options"] == "DENY"
    csp = page.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]  # scripts stay locked down
    assert "Content-Security-Policy" not in client.get("/docs").headers  # Swagger UI needs its CDN assets
    assert client.get("/api/meta").headers["Cache-Control"] == "no-store"


def test_hsts_only_over_https(client, monkeypatch):
    assert "Strict-Transport-Security" not in client.get("/api/health").headers
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    r = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert "max-age" in r.headers["Strict-Transport-Security"]


def test_oversized_body_is_rejected_by_content_length(client, monkeypatch):
    monkeypatch.setenv("MAX_BODY_BYTES", "1000")
    r = client.post(f"/api/learner/{L}/import", content=b"x" * 5000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and "too large" in r.json()["detail"]
    assert "X-Request-ID" in r.headers


def test_oversized_chunked_body_is_rejected_without_a_content_length(client, monkeypatch):
    monkeypatch.setenv("MAX_BODY_BYTES", "1000")

    def chunks():
        for _ in range(5):
            yield b"x" * 600

    r = client.post(f"/api/learner/{L}/import", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_normal_sized_body_still_works(client, monkeypatch):
    monkeypatch.setenv("MAX_BODY_BYTES", "1000")
    assert client.post(f"/api/learner/{L}/import", json={"version": 1, "attempts": []}).status_code == 200


def test_access_log_never_contains_the_query_string(client, caplog):
    with caplog.at_level(logging.INFO, logger="az900.access"):
        client.get("/api/readiness", params={"learner": L})
    lines = [r for r in caplog.records if r.name == "az900.access"]
    assert lines and lines[-1].path == "/api/readiness" and lines[-1].status == 200
    assert all(L not in r.getMessage() and L not in str(r.__dict__) for r in lines)


def test_unexpected_errors_become_a_generic_500_with_a_request_id(client, monkeypatch, caplog):
    import app.api.meta as meta_api

    def boom():
        raise RuntimeError("secret internal detail /srv/app/db.py")

    monkeypatch.setattr(meta_api, "load_bank", boom)
    with caplog.at_level(logging.ERROR):
        r = client.get("/api/health")
    assert r.status_code == 500
    body = r.json()
    assert body["request_id"] == r.headers["X-Request-ID"]
    assert "secret" not in r.text and "Traceback" not in r.text
    assert any("secret internal detail" in (rec.exc_text or "") or rec.exc_info for rec in caplog.records)  # logged server-side


def test_database_contention_is_a_retryable_503(client, monkeypatch):
    from app import db

    def locked(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "get_attempt_rows", locked)
    r = client.get("/api/readiness", params={"learner": L})
    assert r.status_code == 503 and r.headers["Retry-After"] == "2"
    assert "locked" not in r.text  # no internals


def test_ready_reports_database_failure_but_health_stays_up(client, monkeypatch):
    from app import db

    assert client.get("/api/ready").json()["status"] == "ready"
    monkeypatch.setattr(db, "ping", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O error")))
    assert client.get("/api/ready").status_code == 503
    assert client.get("/api/health").status_code == 200  # liveness must not depend on the database


def test_json_logs_carry_the_request_id(capsys):
    configure_logging("INFO", json_logs=True)
    token = request_id_var.set("req-123456")
    try:
        get_logger("test").info("hello", extra={"answer": 42})
    finally:
        request_id_var.reset(token)
        configure_logging("INFO", json_logs=False)
    line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert line["msg"] == "hello" and line["request_id"] == "req-123456" and line["answer"] == 42


def test_startup_creates_missing_database_directory(tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setenv("DB_PATH", str(tmp_path / "nested" / "dir" / "app.db"))
    with TestClient(app) as c:
        assert c.get("/api/ready").status_code == 200
