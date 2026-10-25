import sqlite3
import threading

import pytest

from app import db

L = "learner-db-test-0001"


def _row(i=0, learner=L, confidence="sure"):
    return (learner, f"q-{i}", "compute", 0, 1, confidence, "practice", None, 1000.0 + i)


def test_fresh_database_is_wal_and_fully_migrated(db_path):
    db.init_db()
    assert db.schema_version() == db.LATEST_VERSION
    with db.connect() as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tables = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"attempts", "explanations"} <= tables
    assert db.ping() is True


def test_init_is_idempotent(db_path):
    db.init_db()
    db.add_attempt(L, "q-1", "compute", 0, True, "sure")
    db.init_db()
    db.init_db()
    assert db.count_attempts(L) == 1
    assert db.schema_version() == db.LATEST_VERSION


def test_legacy_unversioned_database_is_adopted_without_losing_data(db_path):
    """A database created by the pre-migration app (user_version 0, no attempt_key) upgrades in place."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id TEXT NOT NULL, question_id TEXT NOT NULL,
            topic TEXT NOT NULL, chosen INTEGER NOT NULL, correct INTEGER NOT NULL,
            confidence TEXT NOT NULL CHECK (confidence IN ('sure', 'guess')),
            mode TEXT NOT NULL DEFAULT 'practice', seconds REAL, ts REAL NOT NULL);
        CREATE TABLE explanations (
            question_id TEXT NOT NULL, choice INTEGER NOT NULL, style TEXT NOT NULL, language TEXT NOT NULL,
            text TEXT NOT NULL, model TEXT NOT NULL, created_at REAL NOT NULL,
            PRIMARY KEY (question_id, choice, style, language));
        INSERT INTO attempts (learner_id, question_id, topic, chosen, correct, confidence, mode, seconds, ts)
        VALUES ('legacy-learner-00001', 'q-1', 'compute', 2, 0, 'guess', 'practice', 4.5, 123.0);
    """)
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    conn.close()

    db.init_db()

    assert db.schema_version() == db.LATEST_VERSION
    rows = db.get_attempt_rows("legacy-learner-00001")
    assert len(rows) == 1 and rows[0]["question_id"] == "q-1" and rows[0]["choice"] == 2
    assert db.add_attempt("legacy-learner-00001", "q-2", "compute", 0, True, "sure", attempt_key="key-12345678")


def test_database_from_a_newer_app_is_refused(db_path):
    db.init_db()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="newer than this app"):
        db.init_db()


def test_attempt_key_makes_retries_idempotent_per_learner(db_path):
    db.init_db()
    assert db.add_attempt(L, "q-1", "compute", 0, True, "sure", attempt_key="retry-key-0001") is True
    assert db.add_attempt(L, "q-1", "compute", 0, True, "sure", attempt_key="retry-key-0001") is False
    assert db.count_attempts(L) == 1
    # the same key from a different learner is a different attempt
    assert db.add_attempt("another-learner-0002", "q-1", "compute", 0, True, "sure", attempt_key="retry-key-0001")
    # no key means no deduplication
    assert db.add_attempt(L, "q-1", "compute", 0, True, "sure") and db.add_attempt(L, "q-1", "compute", 0, True, "sure")
    assert db.count_attempts(L) == 3


def test_history_cap_is_enforced(db_path):
    db.init_db()
    for i in range(2):
        db.add_attempt(L, f"q-{i}", "compute", 0, True, "sure", max_attempts=2)
    with pytest.raises(db.HistoryLimitError):
        db.add_attempt(L, "q-9", "compute", 0, True, "sure", max_attempts=2)
    assert db.count_attempts(L) == 2


def test_replace_is_all_or_nothing(db_path):
    db.init_db()
    db.add_attempts_bulk([_row(0), _row(1)])
    bad = [_row(2), _row(3, confidence="not-a-confidence")]  # violates the CHECK constraint mid-batch
    with pytest.raises(sqlite3.IntegrityError):
        db.replace_attempts(L, bad)
    assert [r["question_id"] for r in db.get_attempt_rows(L)] == ["q-0", "q-1"]  # old history untouched


def test_concurrent_writers_do_not_lose_rows_or_hit_locks(db_path):
    db.init_db()
    errors: list[Exception] = []

    def worker(n: int):
        try:
            for i in range(25):
                db.add_attempt(L, f"q-{n}-{i}", "compute", 0, True, "sure", attempt_key=f"k-{n}-{i:03d}-pad")
        except Exception as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert db.count_attempts(L) == 200


def test_get_attempts_can_ignore_retired_questions(db_path):
    db.init_db()
    db.add_attempt(L, "q-keep", "compute", 0, True, "sure")
    db.add_attempt(L, "q-gone", "compute", 0, True, "sure")
    assert len(db.get_attempts(L)) == 2
    assert [a.question_id for a in db.get_attempts(L, {"q-keep"})] == ["q-keep"]


def test_count_attempts_can_exclude_demo(db_path):
    db.init_db()
    db.add_attempts_bulk([(L, "q-1", "compute", 0, 1, "sure", "demo", None, 1.0)])
    assert db.count_attempts(L) == 1 and db.count_attempts(L, exclude_mode="demo") == 0


def test_online_backup_is_a_usable_copy(db_path, tmp_path):
    db.init_db()
    db.add_attempt(L, "q-1", "compute", 0, True, "sure")
    dest = tmp_path / "copy.db"
    db.backup(str(dest))
    copy = sqlite3.connect(dest)
    assert copy.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
    assert copy.execute("PRAGMA user_version").fetchone()[0] == db.LATEST_VERSION
    copy.close()
