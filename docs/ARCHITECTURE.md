# Architecture

The app is deliberately small: one FastAPI process, one SQLite file, a vanilla-JS frontend with no build
step. This document explains how it is layered, what happens when things go wrong, and where the limits are.

## Layers

```
 Browser  (static/app.js: timeouts, GET retry, idempotent answers, local session + backup)
    |
    v
 middleware.py   request id | access log (path only) | security headers + CSP | body-size limit | last-resort 500
    |
    v
 api/            thin routers: validate input -> call domain -> shape response
   meta  quiz  learners  plan  explain  outcomes      schemas.py (pydantic models, learner-id rules)
    |        \
    |         `-- ratelimit.py   per-client sliding window (general / heavy / explain budgets)
    v
 domain          scoring.py  selection.py  planner.py  insights.py  questions.py   (pure functions)
                 explain.py  (Claude call wrapped in breaker + single-flight + concurrency cap + daily cap)
                 learn.py (official Learn links, review status)   calibration.py (prediction vs reality)
    |
    v
 db.py           SQLite: WAL, BEGIN IMMEDIATE writes, numbered migrations, idempotency keys, backup
```

Cross-cutting: `config.py` (validated environment), `logging_config.py` (request-id aware, JSON optional),
`errors.py` (consistent error bodies). `main.create_app()` wires everything and `lifespan` fails fast on a
bad config, a broken question bank, or a database that cannot be migrated.

Rules that keep it maintainable:

* Routers contain no business logic and no SQL. Domain modules never import FastAPI.
* `db.py` knows nothing about the question bank; callers pass `valid_ids` when they want retired questions ignored.
* Configuration is read when needed, never cached at import, so behaviour is testable and changeable per process.

## Trust and calibration

* `data/learn_links.json` maps each topic to its official Microsoft Learn module and records the skills-outline version
  the links were checked against. It is validated at startup (every topic must have a `learn.microsoft.com` link).
* `data/question_review.json` is the review ledger (`null` = no person has checked it). `app.review` is the only
  supported way to change it; the dashboard reports the reviewed count, so the app never overstates its content.
* `POST /api/outcome` stores a real exam result or practice-assessment score. The prediction stored beside it is
  computed on the server from the learner's answers **up to the end of the day of the result**, so it cannot be
  forged and later practice cannot leak into it. `app.calibration` turns those rows into reliability bins and a
  Brier score versus a baseline, and refuses to declare victory below 30 exam results.

## Installable app

`static/manifest.webmanifest` + `static/sw.js` (served from `/sw.js` so its scope is the whole app). The worker
precaches the shell and serves versioned static files from cache, tries the network first for pages, and **never
touches `/api`**. A test keeps `index.html`'s asset versions and the worker's precache list in lockstep.

## Request lifecycle

1. Middleware assigns (or sanitises) an `X-Request-ID`, rejects oversized bodies, and starts the access-log timer.
2. The router dependency applies the rate limit for the client (`X-Forwarded-For` is only trusted for entries added by
   `TRUSTED_PROXY_HOPS` proxies of your own).
3. Pydantic validates the input (learner ids must be 16-64 characters of `[A-Za-z0-9_-]`).
4. The handler calls domain code and `db.py`. Writes run inside one `BEGIN IMMEDIATE` transaction.
5. The response gets security headers; `/api/*` is `Cache-Control: no-store`. One access-log line is written with the
   method, path (never the query string), status and duration.

## What happens when...

| Situation | Behaviour |
|---|---|
| Claude API is down, slow, rate-limited or returns nothing | Learner gets the curated explanation; the circuit opens after 5 consecutive failures and skips the API for 60 s, then lets one probe through |
| 50 learners ask for the same explanation at once | One live call; the rest wait briefly and read the cache |
| More than 4 live model calls are already in flight | Extra requests get the curated explanation immediately instead of queueing |
| Daily model budget (`EXPLAIN_DAILY_CAP`) is spent | Curated explanations until the next UTC day; cached answers keep being served |
| No API key | AI is off and the button is hidden; everything else is unchanged |
| Two writers hit SQLite together | The second waits (busy timeout) instead of failing; persistent contention returns a retryable 503 |
| Browser retries an answer after a dropped connection | `attempt_id` makes the retry a no-op; the answer is counted once |
| Import fails half-way | The whole replace is one transaction, so the old history is untouched |
| A bad client floods the API | 429 with `Retry-After`; the frontend shows a friendly message |
| Huge or endless upload | 413 before it is parsed (checked by `Content-Length` and by bytes actually received) |
| Unexpected exception | Generic 500 with a request id; the stack trace is only in the server log |
| Bad environment variable | The app refuses to start and says which variable is wrong |
| Database file from a newer app version | The app refuses to start rather than risk corrupting it |
| Learner reports a nonsense result (future date, score out of range) | 422 with a readable message; nothing is stored |
| Question removed from the bank | Old answers to it are ignored in scoring; ids should be retired, never reused |

## Data model and migrations

`attempts` (one row per answer) and `explanations` (cache of live model output). Schema changes are numbered
functions in `db.MIGRATIONS`, tracked in `PRAGMA user_version`, idempotent, and serialised across workers with
`BEGIN IMMEDIATE`. To change the schema: append `(3, _migrate_3)`, write a test that upgrades a v2 database, done.
Databases created before versioning existed are adopted in place (covered by `tests/test_db.py`).

Operations: `python -m app.db version | migrate | backup DEST` (the backup is a consistent online copy).

## Security model

* There are no accounts. The learner id is a random bearer secret generated in the browser (a UUID, 122 bits), which is
  why the server insists on 16+ characters. Anyone holding it can read, export, replace or delete that history, and
  nobody else can. Ids are kept out of logs (access logs record paths only).
* The CSP allows scripts only from the app's own origin. Inline `style` attributes are still permitted because the UI
  uses them; there are no inline scripts or event-handler attributes.
* The Claude key stays on the server. Learners can only choose an option index; the prompt is built from the curated
  question data, so there is no user-supplied text to inject.
* Anything that gets more sensitive (real accounts, cohorts, PII) should add authentication first; the learner-id model
  is a deliberate fit for an anonymous study tool, not a general pattern.

## Known limits (by design)

* **One process.** SQLite, the rate limiter and the circuit breaker are per-process, which is why the Dockerfile runs a
  single uvicorn worker. That comfortably serves a study tool; WAL-mode SQLite handles far more than this app will see.
* **Free-tier disks are ephemeral.** On Render's free plan the history resets on redeploy or spin-down. Attach a disk
  at `/data` or move to Postgres for durability; the learner Export/Import backup is the user-facing safety net.
* **Scaling out** means: Postgres (the SQL is plain; `db.py` is the only file to change), a shared limiter (Redis behind
  `RateLimiter.hit`) and a shared breaker/cache. Nothing else in the code assumes a single process.
