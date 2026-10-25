"""Request models and shared parameter types for the HTTP API."""
from __future__ import annotations

import time
from datetime import date
from typing import Annotated, Literal

from fastapi import Path, Query
from pydantic import BaseModel, Field, field_validator, model_validator

# The learner id is the only credential protecting a learner's data, so it must be unguessable:
# the browser generates a UUID (36 chars); anything shorter than 16 is rejected outright.
LEARNER_PATTERN = r"^[A-Za-z0-9_-]{16,64}$"
LearnerQuery = Annotated[str, Query(pattern=LEARNER_PATTERN, description="Anonymous learner id (16-64 chars: letters, digits, _ or -)")]
LearnerPath = Annotated[str, Path(pattern=LEARNER_PATTERN)]

Mode = Literal["adaptive", "topic", "domain", "exam", "practice", "saved"]
Confidence = Literal["sure", "guess"]
ATTEMPT_KEY_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
MAX_IMPORT_ATTEMPTS = 10_000
CLOCK_SKEW_S = 86_400  # imported timestamps may be at most a day in the future


class AnswerIn(BaseModel):
    learner: str = Field(pattern=LEARNER_PATTERN)
    question_id: str = Field(min_length=1, max_length=64)
    choice: int = Field(ge=0, le=3)
    confidence: Confidence = "sure"
    mode: Mode = "practice"
    seconds: float | None = Field(default=None, ge=0, le=3600)
    attempt_id: str | None = Field(
        default=None, pattern=ATTEMPT_KEY_PATTERN,
        description="Optional idempotency key: re-sending the same id never records a second attempt.",
    )


class ExplainIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    choice: int = Field(ge=0, le=3)
    style: Literal["simple", "exam-tip"] = "simple"
    language: Literal["en", "sw"] = "en"


class ImportAttempt(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    choice: int = Field(ge=0, le=3)
    confidence: Confidence
    mode: Mode = "practice"
    seconds: float | None = Field(default=None, ge=0, le=3600)
    ts: float = Field(ge=0)

    @field_validator("ts")
    @classmethod
    def _not_from_the_future(cls, value: float) -> float:
        if value > time.time() + CLOCK_SKEW_S:
            raise ValueError("timestamp is in the future")
        return value


class ImportIn(BaseModel):
    version: Literal[1]
    attempts: list[ImportAttempt] = Field(max_length=MAX_IMPORT_ATTEMPTS)


class OutcomeIn(BaseModel):
    """A real-world result the learner wants to tell us about."""

    learner: str = Field(pattern=LEARNER_PATTERN)
    kind: Literal["exam", "practice_assessment"]
    happened_on: date
    passed: bool | None = Field(default=None, description="Official exam only")
    score: float | None = Field(
        default=None,
        description="Exam: optional scaled score 100-1000. Practice assessment: percent 0-100 (required)",
    )

    @model_validator(mode="after")
    def _check_fields_for_kind(self) -> OutcomeIn:
        today = date.today()
        if self.happened_on > today:
            raise ValueError("happened_on cannot be in the future")
        if (today - self.happened_on).days > 365:
            raise ValueError("happened_on must be within the last year")
        if self.kind == "exam":
            if self.passed is None:
                raise ValueError("an exam result needs passed true/false")
            if self.score is not None and not 100 <= self.score <= 1000:
                raise ValueError("an exam scaled score is between 100 and 1000")
        else:
            if self.score is None:
                raise ValueError("a practice assessment needs a score (percent)")
            if not 0 <= self.score <= 100:
                raise ValueError("a practice assessment score is a percent between 0 and 100")
            if self.passed is not None:
                raise ValueError("passed applies to official exams only")
        return self
