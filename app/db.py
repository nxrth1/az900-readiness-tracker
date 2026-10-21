"""Tiny SQLite persistence layer (standard library only).

SQLite keeps the demo zero-config. The three tables are small and the queries are plain SQL,
so moving to Postgres or Supabase later is a connection-string change plus minor syntax tweaks.
"""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .scoring import Attempt
from .questions import load_bank

SCHEMA = """
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
);
CREATE INDEX IF NOT EXISTS idx_attempts_learner ON attempts (learner_id, ts);

CREATE TABLE IF NOT EXISTS explanations (
    question_id TEXT NOT NULL,
    choice      INTEGER NOT NULL,
    style       TEXT NOT NULL,
    language    TEXT NOT NULL,
    text        TEXT NOT NULL,
    model       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    PRIMARY KEY (question_id, choice, style, language)
);
"""


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", Path(__file__).resolve().parent.parent / "readiness.db"))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    db_path().parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)


def add_attempt(learner: str, question_id: str, topic: str, chosen: int, correct: bool,
                confidence: str, mode: str = "practice", seconds: float | None = None,
                ts: float | None = None) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO attempts (learner_id, question_id, topic, chosen, correct, confidence, mode, seconds, ts)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (learner, question_id, topic, chosen, int(correct), confidence, mode, seconds, ts or time.time()),
        )


def add_attempts_bulk(rows: list[tuple]) -> None:
    """rows: (learner, question_id, topic, chosen, correct, confidence, mode, seconds, ts)"""
    with connect() as c:
        c.executemany(
            "INSERT INTO attempts (learner_id, question_id, topic, chosen, correct, confidence, mode, seconds, ts)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def get_attempts(learner: str) -> list[Attempt]:
    bank = load_bank()
    with connect() as c:
        rows = c.execute(
            "SELECT question_id, topic, correct, confidence, ts FROM attempts WHERE learner_id = ? ORDER BY ts",
            (learner,),
        ).fetchall()
    return [
        Attempt(r["question_id"], r["topic"], bool(r["correct"]), r["confidence"], r["ts"])
        for r in rows
        if r["question_id"] in bank  # ignore answers to questions that were later removed
    ]


def clear_learner(learner: str) -> int:
    with connect() as c:
        return c.execute("DELETE FROM attempts WHERE learner_id = ?", (learner,)).rowcount


def get_cached_explanation(question_id: str, choice: int, style: str, language: str) -> str | None:
    with connect() as c:
        row = c.execute(
            "SELECT text FROM explanations WHERE question_id=? AND choice=? AND style=? AND language=?",
            (question_id, choice, style, language),
        ).fetchone()
    return row["text"] if row else None


def cache_explanation(question_id: str, choice: int, style: str, language: str, text: str, model: str) -> None:
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO explanations (question_id, choice, style, language, text, model, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (question_id, choice, style, language, text, model, time.time()),
        )
