from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from .. import db, scoring
from ..config import get_settings
from ..questions import load_bank
from ..ratelimit import limit_heavy
from .schemas import LearnerQuery, OutcomeIn

router = APIRouter(tags=["calibration"])

EAT = timezone(timedelta(hours=3))  # same day boundary the dashboard history uses


def snapshot_as_of(learner: str, happened_on) -> dict:
    """What the app believed on the *day of the result*, from answers given up to the end of that day."""
    end = datetime(happened_on.year, happened_on.month, happened_on.day, 23, 59, 59, tzinfo=EAT).timestamp()
    attempts = [a for a in db.get_attempts(learner, load_bank()) if a.ts <= end]
    report = scoring.readiness(attempts, now=end)
    o = report["overall"]
    return {"est_score": o["score"], "p_pass": o["p_pass"], "answered": o["answered"],
            "unique_seen": o["unique_seen"], "coverage": o["coverage"]}


@router.post("/outcome", dependencies=[Depends(limit_heavy)])
def report_outcome(body: OutcomeIn) -> dict:
    snapshot = snapshot_as_of(body.learner, body.happened_on)
    try:
        outcome_id = db.add_outcome(
            body.learner, body.kind, body.happened_on.isoformat(), body.passed, body.score, snapshot,
            max_outcomes=get_settings().max_outcomes_per_learner,
        )
    except db.OutcomeLimitError as limit:
        raise HTTPException(status_code=409, detail=f"You have already reported {limit.args[0]} results.") from None
    return {"id": outcome_id, "snapshot": snapshot}


@router.get("/outcomes")
def list_outcomes(learner: LearnerQuery) -> dict:
    return {"outcomes": db.get_outcomes(learner)}
