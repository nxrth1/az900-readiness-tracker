from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..explain import explain
from ..questions import load_bank
from ..ratelimit import limit_explain
from .schemas import ExplainIn

router = APIRouter(tags=["ai"])


@router.post("/explain", dependencies=[Depends(limit_explain)])
def explain_endpoint(body: ExplainIn) -> dict:
    q = load_bank().get(body.question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="unknown question")
    return explain(q, body.choice, body.style, body.language)
