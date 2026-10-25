"""SQLite persistence: connections, versioned migrations, and the queries the app needs.

Design notes
* WAL journal + busy timeout: readers never block the writer, and short write contention waits
  instead of failing with "database is locked".
* Writes use ``BEGIN IMMEDIATE`` so a transaction that reads then writes can never hit the
  read-to-write lock-upgrade deadlock that deferred transactions suffer from.
* Schema changes are numbered migrations tracked in ``PRAGMA user_version``; they are idempotent and
  safe to run from several workers starting at once.
* This module knows nothing about the question bank. Callers decide which rows are meaningful.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from collections.abc import Callable, Container, Iterator
from contextlib import contextmanager

from .config import get_settings
from .logging_config import get_logger
from .scoring import Attempt

log = get_logger("db")


class HistoryLimitError(Exception):
    """A learner has reached ``MAX_ATTEMPTS_PER_LEARNER``."""


# ---------------------------------------------------------------- connections

@contextmanager
def connect(write: bool = False) -> Iterator[sqlite3.Connection]:
    """A short-lived connection. With ``write=True`` the body runs in one atomic transaction."""
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path, timeout=settings.db_busy_timeout_s, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")  # safe with WAL; per-connection setting
    try:
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def ping() -> bool:
    with connect() as c:
        return c.execute("SELECT 1").fetchone()[0] == 1


# ---------------------------------------------------------------- migrations

def _migrate_1(c: sqlite3.Connection) -> None:
    """Original schema. IF NOT EXISTS so databases created before versioning adopt it untouched."""
    c.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            learner_id  TEXT NOT NULL,
            question_id TEXT NOT NULL,
            topic       TEXT NOT NULL,
            chosen      INTEGER NOT NULL,
            correct     INTEGER NOT NULL,
            confidence  TEXT NOT NULL CHECK (confidence IN ('sure', 'guess')),
            mode        TEXT NOT NULL DEFAULT 'practice',
            seconds     REAL,
            ts          REAL NOT NULL
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_attempts_learner ON attempts (learner_id, ts)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS explanations (
            question_id TEXT NOT NULL,
            choice      INTEGER NOT NULL,
            style       TEXT NOT NULL,
            language    TEXT NOT NULL,
            text        TEXT NOT NULL,
            model       TEXT NOT NULL,
            created_at  REAL NOT NULL,
            PRIMARY KEY (question_id, choice, style, language)
        )""")


def _migrate_2(c: sqlite3.Connection) -> None:
    """Idempotency keys (a retried request must not double-count) and a per-question index."""
    columns = {row["name"] for row in c.execute("PRAGMA table_info(attempts)")}
    if "attempt_key" not in columns:
        c.execute("ALTER TABLE attempts ADD COLUMN attempt_key TEXT")
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_attempts_key ON attempts (learner_id, attempt_key)"
        " WHERE attempt_key IS NOT NULL"
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts (learner_id, question_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_explanations_created ON explanations (created_at)")


def _migrate_3(c: sqlite3.Connection) -> None:
    """Real-world results (exam or Microsoft practice assessment) with the app's prediction at the time.

    The snapshot columns are computed by the server from the learner's history up to the day of the
    result, never taken from the client, so they cannot be forged and the calibration data stays honest.
    """
    c.execute("""
        CREATE TABLE IF NOT EXISTS outcomes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            learner_id   TEXT NOT NULL,
            kind         TEXT NOT NULL CHECK (kind IN ('exam', 'practice_assessment')),
            happened_on  TEXT NOT NULL,
            passed       INTEGER,
            score        REAL,
            reported_at  REAL NOT NULL,
            est_score    REAL NOT NULL,
            p_pass       REAL NOT NULL,
            answered     INTEGER NOT NULL,
            unique_seen  INTEGER NOT NULL,
            coverage     REAL NOT NULL,
            CHECK ((kind = 'exam' AND passed IS NOT NULL) OR (kind = 'practice_assessment' AND score IS NOT NULL))
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_learner ON outcomes (learner_id)")


MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, _migrate_1), (2, _migrate_2), (3, _migrate_3),
]
LATEST_VERSION = MIGRATIONS[-1][0]


def schema_version() -> int:
    with connect() as c:
        return c.execute("PRAGMA user_version").fetchone()[0]


def migrate() -> int:
    """Bring the database up to ``LATEST_VERSION``. Returns the resulting version."""
    with connect() as c:
        for version, step in MIGRATIONS:
            c.execute("BEGIN IMMEDIATE")  # serialises concurrent starters
            try:
                current = c.execute("PRAGMA user_version").fetchone()[0]  # re-read under the lock
                if current > LATEST_VERSION:
                    raise RuntimeError(
                        f"Database schema v{current} is newer than this app (v{LATEST_VERSION}). Upgrade the app."
                    )
                if current < version:
                    step(c)
                    c.execute(f"PRAGMA user_version = {version}")
                    log.info("migrated database to schema v%d", version)
                c.execute("COMMIT")
            except BaseException:
                if c.in_transaction:
                    c.execute("ROLLBACK")
                raise
        return c.execute("PRAGMA user_version").fetchone()[0]


def init_db() -> None:
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        mode = c.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if str(mode).lower() != "wal":
        log.warning("SQLite WAL mode unavailable (journal_mode=%s); concurrency will be reduced", mode)
    migrate()


def backup(dest: str) -> None:
    """Consistent online copy (safe while the app is serving traffic)."""
    with connect() as src:
        target = sqlite3.connect(dest)
        try:
            src.backup(target)
        finally:
            target.close()


# ---------------------------------------------------------------- attempts

_INSERT = (
    "INSERT INTO attempts (learner_id, question_id, topic, chosen, correct, confidence, mode, seconds, ts)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def add_attempt(learner: str, question_id: str, topic: str, chosen: int, correct: bool,
                confidence: str, mode: str = "practice", seconds: float | None = None,
                ts: float | None = None, attempt_key: str | None = None,
                max_attempts: int | None = None) -> bool:
    """Record one answer. Returns False if ``attempt_key`` was already recorded (a retry)."""
    with connect(write=True) as c:
        if attempt_key and c.execute(
            "SELECT 1 FROM attempts WHERE learner_id = ? AND attempt_key = ?", (learner, attempt_key)
        ).fetchone():
            return False
        if max_attempts is not None:
            count = c.execute("SELECT COUNT(*) FROM attempts WHERE learner_id = ?", (learner,)).fetchone()[0]
            if count >= max_attempts:
                raise HistoryLimitError(max_attempts)
        c.execute(
            "INSERT INTO attempts (learner_id, question_id, topic, chosen, correct, confidence, mode,"
            " seconds, ts, attempt_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (learner, question_id, topic, chosen, int(correct), confidence, mode, seconds,
             ts if ts is not None else time.time(), attempt_key),
        )
    return True


def add_attempts_bulk(rows: list[tuple]) -> None:
    """rows: (learner, question_id, topic, chosen, correct, confidence, mode, seconds, ts)"""
    with connect(write=True) as c:
        c.executemany(_INSERT, rows)


def replace_attempts(learner: str, rows: list[tuple]) -> int:
    """Replace one learner's history atomically (all or nothing). Returns how many rows were removed."""
    with connect(write=True) as c:
        deleted = c.execute("DELETE FROM attempts WHERE learner_id = ?", (learner,)).rowcount
        c.executemany(_INSERT, rows)
    return deleted


def get_attempt_rows(learner: str) -> list[dict]:
    """Every stored answer for a learner, oldest first."""
    with connect() as c:
        rows = c.execute(
            "SELECT question_id, topic, chosen AS choice, correct, confidence, mode, seconds, ts"
            " FROM attempts WHERE learner_id = ? ORDER BY ts, id",
            (learner,),
        ).fetchall()
    return [dict(row) for row in rows]


def rows_to_attempts(rows: list[dict], valid_ids: Container[str] | None = None) -> list[Attempt]:
    """Scoring input from stored rows, optionally ignoring questions that no longer exist."""
    return [
        Attempt(r["question_id"], r["topic"], bool(r["correct"]), r["confidence"], r["ts"])
        for r in rows
        if valid_ids is None or r["question_id"] in valid_ids
    ]


def get_attempts(learner: str, valid_ids: Container[str] | None = None) -> list[Attempt]:
    return rows_to_attempts(get_attempt_rows(learner), valid_ids)


def get_attempt_records(learner: str) -> list[dict]:
    """Rows in the portable export shape (no topic; it is derived from the bank on import)."""
    keep = ("question_id", "choice", "correct", "confidence", "mode", "seconds", "ts")
    return [{k: row[k] for k in keep} for row in get_attempt_rows(learner)]


def count_attempts(learner: str, exclude_mode: str | None = None) -> int:
    with connect() as c:
        if exclude_mode is None:
            row = c.execute("SELECT COUNT(*) FROM attempts WHERE learner_id = ?", (learner,)).fetchone()
        else:
            row = c.execute(
                "SELECT COUNT(*) FROM attempts WHERE learner_id = ? AND mode != ?", (learner, exclude_mode)
            ).fetchone()
    return row[0]


def clear_learner(learner: str) -> int:
    """Delete everything we hold about a learner (answers and reported results). Returns answers removed."""
    with connect(write=True) as c:
        c.execute("DELETE FROM outcomes WHERE learner_id = ?", (learner,))
        return c.execute("DELETE FROM attempts WHERE learner_id = ?", (learner,)).rowcount


# ---------------------------------------------------------------- outcomes (real-world results)

class OutcomeLimitError(Exception):
    """A learner has reported ``MAX_OUTCOMES_PER_LEARNER`` results."""


def add_outcome(learner: str, kind: str, happened_on: str, passed: bool | None, score: float | None,
                snapshot: dict, max_outcomes: int) -> int:
    with connect(write=True) as c:
        count = c.execute("SELECT COUNT(*) FROM outcomes WHERE learner_id = ?", (learner,)).fetchone()[0]
        if count >= max_outcomes:
            raise OutcomeLimitError(max_outcomes)
        cur = c.execute(
            "INSERT INTO outcomes (learner_id, kind, happened_on, passed, score, reported_at, est_score, p_pass,"
            " answered, unique_seen, coverage) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (learner, kind, happened_on, None if passed is None else int(passed), score, time.time(),
             snapshot["est_score"], snapshot["p_pass"], snapshot["answered"], snapshot["unique_seen"],
             snapshot["coverage"]),
        )
        return int(cur.lastrowid)


_OUTCOME_COLUMNS = "id, kind, happened_on, passed, score, reported_at, est_score, p_pass, answered, unique_seen, coverage"


def get_outcomes(learner: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            f"SELECT {_OUTCOME_COLUMNS} FROM outcomes WHERE learner_id = ? ORDER BY happened_on DESC, id DESC",
            (learner,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_outcomes() -> list[dict]:
    """Every reported result, without learner ids (for the aggregate calibration report)."""
    with connect() as c:
        return [dict(r) for r in c.execute(f"SELECT {_OUTCOME_COLUMNS} FROM outcomes").fetchall()]


# ---------------------------------------------------------------- explanation cache

def get_cached_explanation(question_id: str, choice: int, style: str, language: str) -> str | None:
    with connect() as c:
        row = c.execute(
            "SELECT text FROM explanations WHERE question_id=? AND choice=? AND style=? AND language=?",
            (question_id, choice, style, language),
        ).fetchone()
    return row["text"] if row else None


def cache_explanation(question_id: str, choice: int, style: str, language: str, text: str, model: str) -> None:
    with connect(write=True) as c:
        c.execute(
            "INSERT OR REPLACE INTO explanations (question_id, choice, style, language, text, model, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (question_id, choice, style, language, text, model, time.time()),
        )


def count_explanations_since(ts: float) -> int:
    """Live model calls since ``ts`` (every live call leaves exactly one cache row)."""
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM explanations WHERE created_at >= ?", (ts,)).fetchone()[0]


# ---------------------------------------------------------------- ops CLI

def _cli(argv: list[str]) -> int:  # pragma: no cover - thin wrapper
    usage = "usage: python -m app.db [migrate | version | backup DEST]"
    if not argv:
        print(usage)
        return 2
    cmd, *rest = argv
    if cmd == "migrate":
        init_db()
        print(f"schema v{schema_version()}")
    elif cmd == "version":
        print(f"schema v{schema_version()} (app expects v{LATEST_VERSION})")
    elif cmd == "backup" and len(rest) == 1:
        backup(rest[0])
        print(f"backup written to {rest[0]}")
    else:
        print(usage)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli(sys.argv[1:]))
