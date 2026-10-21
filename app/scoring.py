"""The readiness engine.

Every practice answer is evidence about one topic. For each topic we keep a Beta posterior over
"the chance this learner answers a question on this topic correctly":

    alpha = 1 + sum(credit_for_success)      beta = 1 + sum(credit_for_failure)

so an untouched topic starts at 50% with wide uncertainty, and the estimate tightens as evidence arrives.
Evidence is adjusted three ways:

* Recency   - an answer loses half its weight every ``HALF_LIFE_DAYS`` (forgetting curve).
* Confidence - a correct answer marked "guess" counts as half a success and half a failure.
* Misconceptions - a wrong answer marked "sure" counts ``CONFIDENT_ERROR_BOOST`` times as much
  as a wrong guess, because confident errors are the most dangerous kind of gap.

Topic estimates roll up to domains and to an overall estimated exam score using the exam weights.
Because topics are treated as independent, the overall variance is the weighted sum of the topic
variances, which gives a normal approximation for the probability of reaching the pass line.

This is a study aid, not a prediction: the real exam is scored on a scaled 1-1000 range with a
pass mark of 700, which we approximate as 70% accuracy.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .questions import DOMAIN_WEIGHTS, DOMAINS, TOPIC_DOMAIN, TOPIC_NAMES, TOPIC_WEIGHTS

PASS_MARK = 0.70
HALF_LIFE_DAYS = 10.0
GUESS_CREDIT = 0.5
CONFIDENT_ERROR_BOOST = 1.5
TARGET_EVIDENCE = 4.0  # effective answers on a topic before we call the reading "reliable"
GOAL_SCORE = 0.80  # the level used to size the "biggest wins"
Z80 = 1.2816  # one-sided 90% z-score -> 10th/90th percentile band


@dataclass(frozen=True)
class Attempt:
    question_id: str
    topic: str
    correct: bool
    confidence: str  # "sure" | "guess"
    ts: float  # unix seconds


def _weight(age_days: float) -> float:
    return 0.5 ** (max(age_days, 0.0) / HALF_LIFE_DAYS)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def topic_posteriors(attempts: list[Attempt], now: float) -> dict[str, dict]:
    stats = {
        t: {"a": 0.0, "b": 0.0, "n_eff": 0.0, "answered": 0, "unique": set(), "last_ts": None}
        for t in TOPIC_DOMAIN
    }
    for at in attempts:
        if at.topic not in stats or at.ts > now:
            continue
        w = _weight((now - at.ts) / 86400.0)
        s = stats[at.topic]
        if at.correct and at.confidence == "sure":
            s["a"] += w
        elif at.correct:
            s["a"] += GUESS_CREDIT * w
            s["b"] += (1 - GUESS_CREDIT) * w
        elif at.confidence == "sure":
            s["b"] += CONFIDENT_ERROR_BOOST * w
        else:
            s["b"] += w
        s["n_eff"] += w
        s["answered"] += 1
        s["unique"].add(at.question_id)
        if s["last_ts"] is None or at.ts > s["last_ts"]:
            s["last_ts"] = at.ts

    out: dict[str, dict] = {}
    for t, s in stats.items():
        alpha, beta = 1.0 + s["a"], 1.0 + s["b"]
        total = alpha + beta
        mean = alpha / total
        sd = math.sqrt(alpha * beta / (total**2 * (total + 1)))
        out[t] = {
            "id": t,
            "name": TOPIC_NAMES[t],
            "domain": TOPIC_DOMAIN[t],
            "score": mean,
            "sd": sd,
            "low": max(0.0, mean - Z80 * sd),
            "high": min(1.0, mean + Z80 * sd),
            "n_eff": s["n_eff"],
            "coverage": min(1.0, s["n_eff"] / TARGET_EVIDENCE),
            "answered": s["answered"],
            "unique_seen": len(s["unique"]),
            "last_ts": s["last_ts"],
        }
    return out


def _combine(parts: list[tuple[float, dict]]) -> tuple[float, float]:
    """Weighted mean and standard deviation of independent topic estimates."""
    wsum = sum(w for w, _ in parts)
    mean = sum(w * p["score"] for w, p in parts) / wsum
    var = sum((w / wsum) ** 2 * p["sd"] ** 2 for w, p in parts)
    return mean, math.sqrt(var)


def _status(p_pass: float, coverage: float, weakest_domain: float) -> tuple[str, str]:
    if coverage < 0.35:
        return "start", "Just getting started"
    if p_pass >= 0.85 and weakest_domain >= 0.60:
        return "ready", "Looking ready to book"
    if p_pass >= 0.55:
        return "close", "Close: shore up the weak spots"
    return "keep", "Keep practising"


def readiness(attempts: list[Attempt], now: float | None = None) -> dict:
    """Full readiness report for one learner as of ``now`` (defaults to the current time)."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    topics = topic_posteriors(attempts, now)

    domains = []
    for d, meta in DOMAINS.items():
        parts = [(TOPIC_WEIGHTS[t], topics[t]) for t in meta["topics"]]
        mean, sd = _combine(parts)
        domains.append(
            {
                "id": d,
                "name": meta["name"],
                "weight": DOMAIN_WEIGHTS[d],
                "range": list(meta["range"]),
                "score": mean,
                "low": max(0.0, mean - Z80 * sd),
                "high": min(1.0, mean + Z80 * sd),
                "coverage": sum(topics[t]["coverage"] for t in meta["topics"]) / len(meta["topics"]),
                "topics": list(meta["topics"]),
            }
        )

    mean, sd = _combine([(TOPIC_WEIGHTS[t], topics[t]) for t in topics])
    p_pass = 1.0 - _norm_cdf((PASS_MARK - mean) / sd) if sd > 0 else float(mean >= PASS_MARK)
    coverage = sum(t["coverage"] for t in topics.values()) / len(topics)
    status, label = _status(p_pass, coverage, min(d["score"] for d in domains))

    wins = []
    for t, tp in topics.items():
        gain = TOPIC_WEIGHTS[t] * max(0.0, GOAL_SCORE - tp["score"]) * 100
        if gain <= 0:
            continue
        if tp["answered"] == 0:
            reason = f"Not practised yet. Getting to {GOAL_SCORE:.0%} here would add about {gain:.1f} points."
        else:
            reason = (
                f"Scoring about {tp['score']:.0%} on this topic. "
                f"Reaching {GOAL_SCORE:.0%} would add about {gain:.1f} points to your estimated score."
            )
        wins.append({"topic": t, "name": tp["name"], "domain": tp["domain"], "gain": gain,
                     "score": tp["score"], "reason": reason})
    wins.sort(key=lambda w: w["gain"], reverse=True)

    cutoff = now - 14 * 86400
    conf_wrong: dict[str, int] = defaultdict(int)
    for at in attempts:
        if at.ts >= cutoff and at.ts <= now and not at.correct and at.confidence == "sure":
            conf_wrong[at.topic] += 1
    misconceptions = sorted(
        ({"topic": t, "name": TOPIC_NAMES[t], "count": c} for t, c in conf_wrong.items()),
        key=lambda m: m["count"], reverse=True,
    )

    return {
        "pass_mark": PASS_MARK,
        "overall": {
            "score": mean,
            "low": max(0.0, mean - Z80 * sd),
            "high": min(1.0, mean + Z80 * sd),
            "p_pass": p_pass,
            "status": status,
            "status_label": label,
            "coverage": coverage,
            "answered": sum(1 for a in attempts if a.ts <= now),
            "unique_seen": len({a.question_id for a in attempts if a.ts <= now}),
        },
        "domains": domains,
        "topics": list(topics.values()),
        "wins": wins[:3],
        "misconceptions": misconceptions[:4],
    }


def history(attempts: list[Attempt], now: float | None = None, days: int = 14, tz_offset_hours: float = 3.0) -> list[dict]:
    """Estimated exam score at the end of each day that has any evidence (oldest first)."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    if not attempts:
        return []
    tz = timezone(timedelta(hours=tz_offset_hours))
    today = datetime.fromtimestamp(now, tz).date()
    out = []
    for back in range(days - 1, -1, -1):
        day = today - timedelta(days=back)
        end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=tz).timestamp()
        end = min(end, now)
        seen = [a for a in attempts if a.ts <= end]
        if not seen:
            continue
        r = readiness(seen, now=end)
        out.append({"date": day.isoformat(), "score": r["overall"]["score"], "answered": len(seen)})
    return out
