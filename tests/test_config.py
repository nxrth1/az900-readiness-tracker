import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, get_settings


def test_defaults():
    s = get_settings()
    assert s.anthropic_api_key is None and s.anthropic_model == "claude-sonnet-5-5"
    assert s.rate_limit_per_min == 240 and s.trusted_proxy_hops == 0 and s.enable_demo is True


def test_values_are_read_at_call_time(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "7")
    assert get_settings().rate_limit_per_min == 7
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "9")
    assert get_settings().rate_limit_per_min == 9


@pytest.mark.parametrize("name,value", [
    ("RATE_LIMIT_PER_MIN", "lots"), ("RATE_LIMIT_PER_MIN", "-1"), ("TRUSTED_PROXY_HOPS", "99"),
    ("EXPLAIN_TIMEOUT_S", "0"), ("ENABLE_DEMO", "maybe"), ("LOG_LEVEL", "LOUD"),
])
def test_bad_values_are_rejected_with_a_clear_message(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match=name):
        get_settings()


@pytest.mark.parametrize("raw,expected", [("true", True), ("1", True), ("off", False), ("NO", False)])
def test_booleans(monkeypatch, raw, expected):
    monkeypatch.setenv("ENABLE_DEMO", raw)
    assert get_settings().enable_demo is expected


def test_app_refuses_to_start_on_bad_configuration(db_path, monkeypatch):
    from app.main import app

    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "nonsense")
    with pytest.raises(ConfigError):
        with TestClient(app):
            pass
