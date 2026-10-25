from __future__ import annotations

import random
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..config import get_settings
from ..learn import topic_link
from ..questions import DOMAINS, TOPIC_NAMES, load_bank
from ..selection import EXAM_SIZE, pick_questions
from .schemas import AnswerIn, LearnerQuery

router = APIRouter(tags=["practice"])


@router.get("/quiz")
def quiz(
    learner: LearnerQuery,
    mode: Literal["adaptive", "topic", "domain", "exam", "saved"] = "adaptive",
    n: int = Query(default=10, ge=1, le=EXAM_SIZE),
    domain: str | None = None,
    topic: str | None = None,
    question_ids: list[str] | None = Query(default=None, max_length=EXAM_SIZE * 3),
) -> dict:
    bank = load_bank()
    if mode == "topic" and topic not in TOPIC_NAMES:
        raise HTTPException(status_code=422, detail="unknown topic")
    if mode == "domain" and domain not in DOMAINS:
        raise HTTPException(status_code=422, detail="unknown domain")
    if mode == "saved":
        if not question_ids:
            raise HTTPException(status_code=422, detail="saved mode requires question_ids")
        if any(question_id not in bank for question_id in question_ids):
            raise HTTPException(status_code=422, detail="saved questions include an unknown question")
    if mode == "exam":
        n = EXAM_SIZE
    questions = pick_questions(
        bank, db.get_attempts(learner, bank), time.time(), mode=mode, n=n,
        domain=domain, topic=topic, question_ids=question_ids, rng=random.Random(),
    )
    return {"mode": mode, "questions": [q.public() for q in questions]}


@router.post("/answer")
def answer(body: AnswerIn) -> dict:
    q = load_bank().get(body.question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="unknown question")
    correct = body.choice == q.answer
    try:
        recorded = db.add_attempt(
            body.learner, q.id, q.topic, body.choice, correct, body.confidence, body.mode, body.seconds,
            attempt_key=body.attempt_id, max_attempts=get_settings().max_attempts_per_learner,
        )
    except db.HistoryLimitError as limit:
        raise HTTPException(
            status_code=409,
            detail=f"History is full ({limit.args[0]} answers). Export your data, then reset to keep practising.",
        ) from None
    return {
        "correct": correct,
        "correct_index": q.answer,
        "explanation": q.why,
        "why_not": q.why_not[body.choice] if not correct else "",
        "topic": q.topic,
        "topic_name": TOPIC_NAMES[q.topic],
        "domain": q.domain,
        "learn": topic_link(q.topic),
        "duplicate": not recorded,
    }
