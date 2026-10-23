"""AZ-900 Readiness Tracker (unofficial) - FastAPI application."""
from __future__ import annotations

import os
import random
import re
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, scoring
from .demo import build_demo_attempts
from .explain import explain
from .planner import PlanError, build_plan
from .questions import DOMAIN_WEIGHTS, DOMAINS, TOPIC_NAMES, load_bank
from .selection import EXAM_SIZE, pick_questions

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
LEARNER_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_bank()  # fail fast if the question bank is invalid
    db.init_db()
    yield


app = FastAPI(
    title="AZ-900 Readiness Tracker (unofficial)",
    description="Practice by topic, see how exam-ready you are. Not affiliated with or endorsed by Microsoft.",
    version="1.0.0",
    lifespan=lifespan,
)


def _learner(value: str) -> str:
    if not LEARNER_RE.match(value):
        raise HTTPException(status_code=422, detail="learner must be 6-64 characters: letters, digits, _ or -")
    return value


class AnswerIn(BaseModel):
    learner: str
    question_id: str
    choice: int = Field(ge=0, le=3)
    confidence: Literal["sure", "guess"] = "sure"
    mode: Literal["adaptive", "topic", "domain", "exam", "practice", "saved"] = "practice"
    seconds: float | None = Field(default=None, ge=0, le=3600)


class ExplainIn(BaseModel):
    question_id: str
    choice: int = Field(ge=0, le=3)
    style: Literal["simple", "exam-tip"] = "simple"
    language: Literal["en", "sw"] = "en"


class ImportAttempt(BaseModel):
    question_id: str
    choice: int = Field(ge=0, le=3)
    confidence: Literal["sure", "guess"]
    mode: Literal["adaptive", "topic", "domain", "exam", "practice", "saved"] = "practice"
    seconds: float | None = Field(default=None, ge=0, le=3600)
    ts: float = Field(ge=0)


class ImportIn(BaseModel):
    version: Literal[1]
    attempts: list[ImportAttempt] = Field(max_length=10000)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "questions": len(load_bank())}


@app.get("/api/meta")
def meta() -> dict:
    bank = load_bank()
    counts: dict[str, int] = {}
    for q in bank.values():
        counts[q.topic] = counts.get(q.topic, 0) + 1
    return {
        "ai": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "pass_mark": scoring.PASS_MARK,
        "exam_size": EXAM_SIZE,
        "total_questions": len(bank),
        "domains": [
            {
                "id": d,
                "name": m["name"],
                "weight": DOMAIN_WEIGHTS[d],
                "range": list(m["range"]),
                "topics": [{"id": t, "name": n, "questions": counts.get(t, 0)} for t, n in m["topics"].items()],
            }
            for d, m in DOMAINS.items()
        ],
    }


@app.get("/api/quiz")
def quiz(
    learner: str,
    mode: Literal["adaptive", "topic", "domain", "exam", "saved"] = "adaptive",
    n: int = Query(default=10, ge=1, le=EXAM_SIZE),
    domain: str | None = None,
    topic: str | None = None,
    question_ids: list[str] | None = Query(default=None),
) -> dict:
    learner = _learner(learner)
    if mode == "topic" and topic not in TOPIC_NAMES:
        raise HTTPException(status_code=422, detail="unknown topic")
    if mode == "domain" and domain not in DOMAINS:
        raise HTTPException(status_code=422, detail="unknown domain")
    if mode == "saved":
        bank_ids = load_bank()
        if not question_ids:
            raise HTTPException(status_code=422, detail="saved mode requires question_ids")
        if any(question_id not in bank_ids for question_id in question_ids):
            raise HTTPException(status_code=422, detail="saved questions include an unknown question")
    if mode == "exam":
        n = EXAM_SIZE
    questions = pick_questions(
        load_bank(), db.get_attempts(learner), time.time(), mode=mode, n=n,
        domain=domain, topic=topic, question_ids=question_ids, rng=random.Random(),
    )
    return {"mode": mode, "questions": [q.public() for q in questions]}


@app.post("/api/answer")
def answer(body: AnswerIn) -> dict:
    learner = _learner(body.learner)
    q = load_bank().get(body.question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="unknown question")
    correct = body.choice == q.answer
    db.add_attempt(learner, q.id, q.topic, body.choice, correct, body.confidence, body.mode, body.seconds)
    return {
        "correct": correct,
        "correct_index": q.answer,
        "explanation": q.why,
        "why_not": q.why_not[body.choice] if not correct else "",
        "topic": q.topic,
        "topic_name": TOPIC_NAMES[q.topic],
        "domain": q.domain,
    }


@app.get("/api/readiness")
def readiness(learner: str) -> dict:
    learner = _learner(learner)
    attempts = db.get_attempts(learner)
    report = scoring.readiness(attempts)
    report["history"] = scoring.history(attempts)
    report["total_questions"] = len(load_bank())
    return report


@app.get("/api/plan")
def plan(
    learner: str,
    exam_date: date,
    hours_per_week: float = Query(default=5, ge=0.5, le=40),
    days: str = Query(default="0,1,2,3,4,5", description="Study weekdays, Monday=0 ... Sunday=6, comma separated"),
    today: date | None = None,
) -> dict:
    learner = _learner(learner)
    try:
        study_days = [int(x) for x in days.split(",") if x.strip() != ""]
    except ValueError:
        raise HTTPException(status_code=422, detail="days must be comma-separated weekday numbers 0-6")
    report = scoring.readiness(db.get_attempts(learner))
    try:
        return build_plan(report, today or date.today(), exam_date, hours_per_week, study_days)
    except PlanError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/explain")
def explain_endpoint(body: ExplainIn) -> dict:
    q = load_bank().get(body.question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="unknown question")
    return explain(q, body.choice, body.style, body.language)


@app.post("/api/demo/seed")
def seed_demo(learner: str) -> dict:
    learner = _learner(learner)
    db.clear_learner(learner)
    rows = build_demo_attempts(learner, load_bank())
    db.add_attempts_bulk(rows)
    return {"seeded": len(rows)}


@app.delete("/api/learner/{learner}")
def reset(learner: str) -> dict:
    learner = _learner(learner)
    return {"deleted": db.clear_learner(learner)}


@app.get("/api/learner/{learner}/export")
def export_learner(learner: str) -> dict:
    learner = _learner(learner)
    return {"format": "az900-readiness-tracker", "version": 1, "attempts": db.get_attempt_records(learner)}


@app.post("/api/learner/{learner}/import")
def import_learner(learner: str, body: ImportIn) -> dict:
    learner = _learner(learner)
    bank = load_bank()
    rows = []
    for attempt in body.attempts:
        question = bank.get(attempt.question_id)
        if question is None:
            raise HTTPException(status_code=422, detail=f"unknown question in import: {attempt.question_id}")
        rows.append((
            learner, question.id, question.topic, attempt.choice, int(attempt.choice == question.answer),
            attempt.confidence, attempt.mode, attempt.seconds, attempt.ts,
        ))
    deleted = db.replace_attempts(learner, rows)
    return {"imported": len(rows), "replaced": deleted}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
