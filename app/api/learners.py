from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import db, scoring
from ..config import get_settings
from ..demo import build_demo_attempts
from ..insights import learning_insights
from ..questions import load_bank
from ..ratelimit import limit_heavy
from .schemas import ImportIn, LearnerPath, LearnerQuery

router = APIRouter(tags=["learner"])


@router.get("/readiness")
def readiness(learner: LearnerQuery) -> dict:
    bank = load_bank()
    rows = [r for r in db.get_attempt_rows(learner) if r["question_id"] in bank]  # one query, one pass
    attempts = db.rows_to_attempts(rows)
    report = scoring.readiness(attempts)
    report["history"] = scoring.history(attempts)
    report["insights"] = learning_insights(rows)
    report["total_questions"] = len(bank)
    return report


@router.post("/demo/seed", dependencies=[Depends(limit_heavy)])
def seed_demo(learner: LearnerQuery, replace: bool = False) -> dict:
    if not get_settings().enable_demo:
        raise HTTPException(status_code=404, detail="demo data is disabled on this server")
    if db.count_attempts(learner, exclude_mode="demo") and not replace:
        raise HTTPException(
            status_code=409,
            detail="This learner has real practice history. Pass replace=true to overwrite it with demo data.",
        )
    rows = build_demo_attempts(learner, load_bank())
    db.replace_attempts(learner, rows)  # one atomic swap: never a half-seeded or empty state
    return {"seeded": len(rows)}


@router.delete("/learner/{learner}", dependencies=[Depends(limit_heavy)])
def reset(learner: LearnerPath) -> dict:
    return {"deleted": db.clear_learner(learner)}


@router.get("/learner/{learner}/export", dependencies=[Depends(limit_heavy)])
def export_learner(learner: LearnerPath) -> dict:
    return {"format": "az900-readiness-tracker", "version": 1, "attempts": db.get_attempt_records(learner)}


@router.post("/learner/{learner}/import", dependencies=[Depends(limit_heavy)])
def import_learner(learner: LearnerPath, body: ImportIn) -> dict:
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
