"""AZ-900 Readiness Tracker (unofficial) - application factory and wiring.

Layers (each only talks to the one below it):

    api/            HTTP routers: validation, status codes, response shape
    scoring, selection, planner, insights, explain     domain logic (pure, or isolated side effects)
    db              persistence (SQLite: WAL, migrations, atomic writes)
    config, logging_config, ratelimit, middleware, errors   cross-cutting concerns
"""
from __future__ import annotations

import html
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db, explain
from .api import explain as explain_api
from .api import learners, meta, outcomes, plan, quiz
from .config import get_settings
from .errors import register_error_handlers
from .learn import load_links
from .logging_config import configure_logging, get_logger
from .middleware import RequestContextMiddleware
from .questions import load_bank
from .ratelimit import RateLimiter, limit_general

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()  # raises ConfigError on a bad environment: fail fast, not at 3am
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("startup")
    bank = load_bank()  # fail fast if the question bank is invalid
    load_links()  # ...or if a topic has no valid study link
    db.init_db()
    explain.reset_state()
    app.state.limiter = RateLimiter()
    log.info(
        "ready: v%s, %d questions, db=%s (schema v%d), ai=%s",
        __version__, len(bank), settings.db_path, db.schema_version(), bool(settings.anthropic_api_key),
    )
    yield
    log.info("shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AZ-900 Readiness Tracker (unofficial)",
        description="Practice by topic, see how exam-ready you are. Not affiliated with or endorsed by Microsoft.",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    # Health/ready probes are exempt from rate limits; every other API route shares the general budget.
    app.include_router(meta.router, prefix="/api")
    for router in (quiz.router, learners.router, plan.router, explain_api.router, outcomes.router):
        app.include_router(router, prefix="/api", dependencies=[Depends(limit_general)])

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/privacy", include_in_schema=False)
    def privacy() -> HTMLResponse:
        email = get_settings().contact_email
        contact = (f'<a href="mailto:{html.escape(email, quote=True)}">{html.escape(email)}</a>' if email
                   else "the operator of this site (see the project&rsquo;s repository for contact details)")
        page = (STATIC_DIR / "privacy.html").read_text(encoding="utf-8").replace("{{CONTACT}}", contact)
        return HTMLResponse(page, headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        # Served from the root so its scope covers the whole app; never cached so updates ship at once.
        return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
