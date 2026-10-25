FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/readiness.db \
    LOG_JSON=true \
    PORT=8000

WORKDIR /srv

# Reproducible installs: exact versions from the lock file, not "latest".
COPY requirements.txt requirements.lock ./
RUN pip install -r requirements.lock

# Run as an unprivileged user; /data is the only writable path.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data && chown app:app /data
COPY --chown=app:app app ./app
COPY --chown=app:app static ./static
USER app

VOLUME /data
EXPOSE 8000

# Liveness only (no DB access): the platform's readiness check should use /api/ready.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=2)"

# Single worker on purpose: SQLite + in-memory rate limiter/circuit breaker are per-process.
# Our middleware writes the access log (with request ids), so uvicorn's own is disabled.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log --no-server-header --timeout-graceful-shutdown 20"]
