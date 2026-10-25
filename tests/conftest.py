import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Learner ids must be 16+ characters (they are the credential protecting a learner's data).
LEARNER = "learner-test-0001"
OTHER = "learner-test-0002"

_CONFIG_VARS = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "DB_PATH", "LOG_LEVEL", "LOG_JSON", "TRUSTED_PROXY_HOPS",
    "MAX_BODY_BYTES", "RATE_LIMIT_PER_MIN", "HEAVY_RATE_LIMIT_PER_MIN", "EXPLAIN_RATE_LIMIT_PER_MIN",
    "EXPLAIN_TIMEOUT_S", "EXPLAIN_MAX_CONCURRENT", "EXPLAIN_DAILY_CAP", "EXPLAIN_BREAKER_THRESHOLD",
    "EXPLAIN_BREAKER_COOLDOWN_S", "ENABLE_DEMO", "MAX_ATTEMPTS_PER_LEARNER", "DB_BUSY_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Every test starts from default configuration and fresh module-level state."""
    for name in _CONFIG_VARS:
        monkeypatch.delenv(name, raising=False)
    from app import explain

    explain.reset_state()
    yield
    explain.reset_state()


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(path))
    return path


@pytest.fixture()
def client(db_path):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
