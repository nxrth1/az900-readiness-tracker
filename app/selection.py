"""Choosing which questions to show.

Adaptive review blends three signals per question: how much the question's topic could still add to
the exam score, whether the learner got it wrong last time, and how long it has been since they saw it
(a lightweight spaced-repetition rule). Mock exams sample by exam weight instead.
"""
from __future__ import annotations

import math
import random

from .questions import DOMAIN_WEIGHTS, TOPIC_WEIGHTS, Question
from .scoring import Attempt, readiness

EXAM_SIZE = 40


def _last_results(attempts: list[Attempt]) -> dict[str, Attempt]:
    last: dict[str, Attempt] = {}
    for a in sorted(attempts, key=lambda x: x.ts):
        last[a.question_id] = a
    return last


def pick_questions(
    bank: dict[str, Question],
    attempts: list[Attempt],
    now: float,
    mode: str = "adaptive",
    n: int = 10,
    domain: str | None = None,
    topic: str | None = None,
    question_ids: list[str] | None = None,
    rng: random.Random | None = None,
) -> list[Question]:
    rng = rng or random.Random()
    pool = list(bank.values())
    if mode == "topic":
        pool = [q for q in pool if q.topic == topic]
    elif mode == "domain":
        pool = [q for q in pool if q.domain == domain]
    elif mode == "saved":
        saved = set(question_ids or [])
        pool = [q for q in pool if q.id in saved]
    if not pool:
        return []

    if mode == "exam":
        return _exam_sample(pool, min(n or EXAM_SIZE, len(pool)), rng)

    report = readiness(attempts, now)
    gains = {t["id"]: TOPIC_WEIGHTS[t["id"]] * max(0.0, 0.8 - t["score"]) for t in report["topics"]}
    top_gain = max(gains.values()) or 1.0
    last = _last_results(attempts)

    scored: list[tuple[float, Question]] = []
    for q in pool:
        s = 0.8 * (gains[q.topic] / top_gain)
        prev = last.get(q.id)
        if prev is None:
            s += 0.6  # unseen
        else:
            age_days = max(0.0, (now - prev.ts) / 86400.0)
            if not prev.correct:
                # Wrong last time: bring it back ahead of merely-unseen questions, unless it was seconds ago.
                s += 1.5 if age_days >= 0.02 else 0.2
            elif prev.confidence == "guess":
                s += 0.5  # right but unsure
            elif age_days < 1:
                s -= 0.8
            else:
                s += min(age_days / 14.0, 1.0) * 0.4
        s += rng.random() * 0.15
        scored.append((s, q))
    scored.sort(key=lambda p: p[0], reverse=True)

    n = min(n, len(scored))
    cap = max(2, math.ceil(n * 0.4)) if mode == "adaptive" else n
    chosen: list[Question] = []
    per_topic: dict[str, int] = {}
    leftovers: list[Question] = []
    for _, q in scored:
        if len(chosen) >= n:
            break
        if per_topic.get(q.topic, 0) >= cap:
            leftovers.append(q)
            continue
        chosen.append(q)
        per_topic[q.topic] = per_topic.get(q.topic, 0) + 1
    for q in leftovers:  # relax the cap if the pool is too narrow
        if len(chosen) >= n:
            break
        chosen.append(q)
    rng.shuffle(chosen)
    return chosen


def _exam_sample(pool: list[Question], n: int, rng: random.Random) -> list[Question]:
    by_domain: dict[str, list[Question]] = {}
    for q in pool:
        by_domain.setdefault(q.domain, []).append(q)
    wsum = sum(DOMAIN_WEIGHTS[d] for d in by_domain)
    quotas = {d: min(len(qs), round(n * DOMAIN_WEIGHTS[d] / wsum)) for d, qs in by_domain.items()}
    # Fix rounding drift so the total is exactly n where the pool allows it.
    while sum(quotas.values()) < n:
        room = [d for d in quotas if quotas[d] < len(by_domain[d])]
        if not room:
            break
        quotas[max(room, key=lambda d: DOMAIN_WEIGHTS[d])] += 1
    while sum(quotas.values()) > n:
        quotas[max(quotas, key=lambda d: quotas[d])] -= 1
    chosen: list[Question] = []
    for d, qs in by_domain.items():
        chosen.extend(rng.sample(qs, quotas[d]))
    rng.shuffle(chosen)
    return chosen
