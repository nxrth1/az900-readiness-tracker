"""Runtime configuration.

Everything is read from environment variables *at call time* (never cached at import), so tests and
operators can change behaviour without re-importing modules. Invalid values raise ``ConfigError`` and
the app refuses to start (see ``main.lifespan``) rather than limping along with a silent default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "readiness.db"


class ConfigError(RuntimeError):
    """An environment variable has an unusable value."""


def _int(name: str, default: int, lo: int, hi: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def _float(name: str, default: float, lo: float, hi: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


def _https_url(name: str) -> str | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    if not raw.startswith("https://"):
        raise ConfigError(f"{name} must start with https://, got {raw!r}")
    return raw


@dataclass(frozen=True)
class Settings:
    # storage
    db_path: Path
    db_busy_timeout_s: float
    max_attempts_per_learner: int
    # logging
    log_level: str
    log_json: bool
    # edge protection
    trusted_proxy_hops: int      # 0 = not behind a proxy; 1 = Render/Fly/Heroku-style single proxy
    max_body_bytes: int
    rate_limit_per_min: int      # every /api route, per client; 0 disables
    heavy_rate_limit_per_min: int  # import / export / demo / reset
    explain_rate_limit_per_min: int
    # optional AI explanations
    anthropic_api_key: str | None
    anthropic_model: str
    explain_timeout_s: float
    explain_max_concurrent: int
    explain_daily_cap: int       # live Claude calls per UTC day; 0 = unlimited
    breaker_threshold: int       # consecutive failures before the circuit opens
    breaker_cooldown_s: int
    # features
    enable_demo: bool
    feedback_url: str | None     # e.g. https://github.com/you/repo/issues/new : enables "report a problem" links
    contact_email: str | None    # shown on the privacy page
    max_outcomes_per_learner: int


def get_settings() -> Settings:
    level = os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(f"LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL, got {level!r}")
    db = os.environ.get("DB_PATH", "").strip()
    return Settings(
        db_path=Path(db) if db else DEFAULT_DB,
        db_busy_timeout_s=_float("DB_BUSY_TIMEOUT_S", 5.0, 0.0, 60.0),
        max_attempts_per_learner=_int("MAX_ATTEMPTS_PER_LEARNER", 10_000, 1, 1_000_000),
        log_level=level,
        log_json=_bool("LOG_JSON", False),
        trusted_proxy_hops=_int("TRUSTED_PROXY_HOPS", 0, 0, 5),
        max_body_bytes=_int("MAX_BODY_BYTES", 2_000_000, 1_000, 50_000_000),
        rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 240, 0, 100_000),
        heavy_rate_limit_per_min=_int("HEAVY_RATE_LIMIT_PER_MIN", 12, 0, 100_000),
        explain_rate_limit_per_min=_int("EXPLAIN_RATE_LIMIT_PER_MIN", 12, 0, 100_000),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "").strip() or "claude-sonnet-5-5",
        explain_timeout_s=_float("EXPLAIN_TIMEOUT_S", 15.0, 1.0, 120.0),
        explain_max_concurrent=_int("EXPLAIN_MAX_CONCURRENT", 4, 1, 64),
        explain_daily_cap=_int("EXPLAIN_DAILY_CAP", 2000, 0, 10_000_000),
        breaker_threshold=_int("EXPLAIN_BREAKER_THRESHOLD", 5, 1, 1000),
        breaker_cooldown_s=_int("EXPLAIN_BREAKER_COOLDOWN_S", 60, 1, 86_400),
        enable_demo=_bool("ENABLE_DEMO", True),
        feedback_url=_https_url("FEEDBACK_URL"),
        contact_email=os.environ.get("CONTACT_EMAIL", "").strip() or None,
        max_outcomes_per_learner=_int("MAX_OUTCOMES_PER_LEARNER", 20, 1, 1000),
    )
