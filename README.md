# AZ-900 Readiness Tracker

> **Unofficial study tool.** Not affiliated with, endorsed by, or sponsored by Microsoft. All 64 questions are original and written from the public AZ-900 skills outline on Microsoft Learn. No Microsoft logos are used.

Most learners finish a practice test with one number and no idea whether it means they should book the exam. **Readiness Tracker** turns every practice answer into an honest, topic-by-topic estimate of how ready you are, tells you what to study next, and shows its uncertainty instead of hiding it.

Built for the **#1MillionDevs Vibe Coding Hackathon: AZ-900 Exam Prep Edition** (challenge: *Progress / Readiness Tracker*, with a bonus *Study Planner*).

| Dashboard | Practice feedback |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Feedback](docs/screenshots/feedback.png) |

## What makes it different

- **A score with error bars.** "64% (likely 59 to 68%), about a 4% chance of reaching the 70% pass line on today's evidence." Early on the range is wide; it narrows as you answer more.
- **Honest about guessing.** Before each answer you mark *I'm sure* or *Just guessing*. A lucky guess counts for little. A confident wrong answer counts extra and is flagged as a misconception.
- **Weighted like the exam.** Topic scores roll up into the three exam domains using the published weightings (25-30%, 35-40%, 30-35%).
- **Tells you where the points are.** "Biggest wins next" ranks topics by how many exam points you would gain by reaching 80%.
- **Forgetting is modelled.** Evidence fades with a 10-day half-life, so a topic you have not touched in weeks drifts back toward uncertainty.
- **Smart review (spaced repetition).** Picks questions from high-value weak topics, brings back anything you got wrong, and rests things you just got right.
- **Exam-date study planner.** Give it your exam date, hours per week and study days. It builds a day-by-day schedule that puts time where it raises your score most, interleaves topics, adds a mock exam about a week out, and keeps the final day to light review of your weak spots and confident mistakes. Rebuild it any time as your readiness changes.
- **Mock exam.** 40 questions sampled by exam weight, no feedback until the end, then a full review.
- **Explain it simply (optional, Claude).** Re-explains a question in plain English or Kiswahili with an everyday East African analogy, grounded in the curated explanation so it cannot invent facts. See [docs/PROMPTS.md](docs/PROMPTS.md).

## Quick start

Requires Python 3.11+.

```bash
git clone <your-repo-url> az900-readiness-tracker
cd az900-readiness-tracker
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Click **Load demo data** on the dashboard to see a populated example straight away.

Optional AI explanations:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # Windows PowerShell: $env:ANTHROPIC_API_KEY="..."
export ANTHROPIC_MODEL=claude-sonnet-5-5   # optional, this is the default
```

Without a key everything else works; the explain button is hidden. Explanations are cached per question, wrong choice, style and language, so API usage is bounded no matter how many people use the app.

### Docker

```bash
docker build -t az900-readiness .
docker run -p 8000:8000 -v az900data:/data -e ANTHROPIC_API_KEY=... az900-readiness
```

### Public demo on Render

This repository includes a Render Blueprint for deploying the app as a Docker web service. To create a public demo, push the repository to GitHub, sign in to Render, choose **New → Blueprint**, and connect this repository. Render reads `render.yaml` and builds the app; the health check uses `/api/meta`.

The Blueprint uses Render's free instance for a prototype. Free instances spin down when idle and have an ephemeral filesystem, so practice history stored in SQLite can be lost when the service restarts, spins down, or redeploys. Use a persistent disk on a paid instance if learner history must survive those events. AI explanations remain optional; no API key is needed for the core app.

## How the readiness score works

Every answer is evidence about one of 14 topics. For each topic we keep a Beta distribution over "the chance you answer a question on this topic correctly".

| Signal | Effect |
|---|---|
| Start | Beta(1, 1): 50% with wide uncertainty, so an untouched topic never looks ready |
| Correct and *sure* | Full success credit |
| Correct but *guessing* | Half success, half failure: it tells us nothing about the mean |
| Wrong and *guessing* | Full failure credit |
| Wrong but *sure* | 1.5x failure credit and flagged as a misconception |
| Age | Weight halves every 10 days |

Then:

1. **Topic** estimate = posterior mean; the likely range is the 10th to 90th percentile (normal approximation).
2. **Domain** estimate = mean of its topics.
3. **Overall** estimated score = exam-weighted mean of topics, using each domain's midpoint weight split evenly across its topics.
4. **Pass likelihood** = probability the overall score is at least 70%, treating topics as independent so variances add.
5. **Status**: *Just getting started* (little evidence), *Keep practising*, *Close*, or *Looking ready to book* (at least 85% pass likelihood and no domain below 60%).

Limitations, stated plainly: the real exam is scored on a scaled 1-1000 range with a pass mark of 700, which this approximates as 70% accuracy; domain weights are the midpoints of Microsoft's published ranges; topics are not truly independent; and a 64-question bank is a small sample. Treat the output as a study guide, not a prediction. The maths lives in [`app/scoring.py`](app/scoring.py) and is covered by tests.

## Architecture

```
 Browser (vanilla JS, inline SVG, no build step)
    |  /api/quiz  /api/answer  /api/readiness  /api/explain
    v
 FastAPI (app/main.py)
    |-- selection.py   adaptive review, topic/domain drills, mock exam sampling
    |-- planner.py     exam-date study schedule built from the readiness report
    |-- scoring.py     Beta posteriors, recency decay, roll-up, pass likelihood, history
    |-- explain.py     Claude explainer + cache + offline fallback
    |-- questions.py   loads and validates data/questions.json
    `-- db.py          SQLite: attempts + cached explanations
```

SQLite keeps setup to zero. The queries are plain SQL, so moving to Postgres or Supabase is a connection change.

### API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta` | Domains, topics, weights, counts, whether AI is on |
| GET | `/api/quiz?learner=&mode=&n=&domain=&topic=` | Questions (never includes answers). Modes: `adaptive`, `topic`, `domain`, `exam` |
| POST | `/api/answer` | Record an answer; returns correctness and explanations |
| GET | `/api/readiness?learner=` | Full report: overall, domains, topics, wins, misconceptions, history |
| GET | `/api/plan?learner=&exam_date=&hours_per_week=&days=` | Day-by-day study plan from the learner's current readiness (`days` = weekday numbers, Mon=0) |
| POST | `/api/explain` | Claude explanation (or built-in fallback) |
| POST | `/api/demo/seed?learner=` | Load a deterministic demo history |
| DELETE | `/api/learner/{id}` | Delete a learner's history |

Interactive docs at `/docs`. Learners are anonymous random IDs stored in the browser; there is no login.

## Project layout

```
app/            backend (see architecture above) and demo.py (demo data)
app/data/       questions.json, the question bank
static/         index.html, app.js, styles.css
tests/          64 tests: bank validity, scoring maths, selection, planner, API, Claude path (stubbed)
docs/           PROMPTS.md, PITCH.md, screenshots
```

### How the planner allocates time

Need per topic = exam weight x (gap to a target a little above 80% + a small bonus for topics with little evidence). Total minutes come from hours per week and chosen study days; topic time is split in proportion to need and cut into 25-minute blocks, interleaved so no topic repeats within a day. The first visit to a topic is a *Learn* block, later visits are *Practise* blocks. Code: [`app/planner.py`](app/planner.py).

## Question bank

`app/data/questions.json` holds 64 original questions across the three domains and 14 topics (cloud concepts 19, architecture and services 25, management and governance 20). Each has a curated explanation and a one-line reason **every wrong option is wrong**.

```json
{
  "id": "mg-08", "domain": "management-governance", "topic": "governance", "difficulty": 2,
  "q": "To stop anyone from accidentally deleting a production database ... which lock?",
  "options": ["ReadOnly", "CanNotDelete", "Audit", "Deny"], "answer": 1,
  "why": "A CanNotDelete lock lets authorised users read and modify a resource but prevents deletion.",
  "why_not": ["ReadOnly would also block modifications.", "", "Audit is a policy effect, not a lock type.", "Deny is a policy effect, not a lock type."]
}
```

Add questions by editing the file, then validate:

```bash
python -m app.questions     # checks ids, topics, 4 distinct options, why_not entries, etc.
python -m pytest -q
```

**Before you rely on it:** the questions were written from the public skills outline, but you should still read them against Microsoft Learn. Content accuracy is what learners (and judges) care about most. Do not paste in real exam questions or brain-dump material.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Covers question-bank integrity and exam-weight balance, every rule of the scoring model (guess credit, confident-error penalty, decay, narrowing uncertainty, status labels, history), question selection, the planner (budget, mock and light-review placement, interleaving, input errors), the full API including input validation and learner isolation, and the Claude path with a stubbed client (prompt contents, caching, failure fallback).

## Roadmap

- Move domain and topic definitions into a config file so other certifications (AZ-104, AWS Cloud Practitioner, Google Cloud Digital Leader) are a data swap.
- Optional sign-in and Supabase/Postgres storage for cross-device progress.
- Per-question difficulty calibration from real learner results.
- Instructor view: cohort heatmap by topic.

## Licence

MIT. See [LICENSE](LICENSE).
