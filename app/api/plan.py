from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from .. import db, scoring
from ..planner import PlanError, build_plan
from ..questions import load_bank
from .schemas import LearnerQuery

router = APIRouter(tags=["planner"])


@router.get("/plan")
def plan(
    learner: LearnerQuery,
    exam_date: date,
    hours_per_week: float = Query(default=5, ge=0.5, le=40),
    days: str = Query(default="0,1,2,3,4,5", max_length=32,
                      description="Study weekdays, Monday=0 ... Sunday=6, comma separated"),
    today: date | None = None,
) -> dict:
    try:
        study_days = [int(x) for x in days.split(",") if x.strip() != ""]
    except ValueError:
        raise HTTPException(status_code=422, detail="days must be comma-separated weekday numbers 0-6") from None
    report = scoring.readiness(db.get_attempts(learner, load_bank()))
    try:
        return build_plan(report, today or date.today(), exam_date, hours_per_week, study_days)
    except PlanError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
