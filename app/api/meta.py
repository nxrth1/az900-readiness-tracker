from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .. import __version__, db, scoring
from ..config import get_settings
from ..learn import content_info
from ..logging_config import get_logger
from ..questions import DOMAIN_WEIGHTS, DOMAINS, load_bank
from ..ratelimit import limit_general
from ..selection import EXAM_SIZE

router = APIRouter(tags=["meta"])
log = get_logger("health")


@router.get("/health", summary="Liveness: the process is up")
def health() -> dict:
    return {"status": "ok", "version": __version__, "questions": len(load_bank())}


@router.get("/ready", summary="Readiness: the database answers and the question bank is loaded")
def ready():
    try:
        db.ping()
        schema = db.schema_version()
        questions = len(load_bank())
    except Exception as exc:
        log.error("readiness check failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "unavailable"}, headers={"Retry-After": "5"})
    return {"status": "ready", "schema": schema, "questions": questions}


@router.get("/meta", dependencies=[Depends(limit_general)])
def meta() -> dict:
    bank = load_bank()
    counts: dict[str, int] = {}
    for q in bank.values():
        counts[q.topic] = counts.get(q.topic, 0) + 1
    return {
        "ai": bool(get_settings().anthropic_api_key),
        "pass_mark": scoring.PASS_MARK,
        "exam_size": EXAM_SIZE,
        "total_questions": len(bank),
        "content": content_info(len(bank)),
        "feedback_url": get_settings().feedback_url,
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
