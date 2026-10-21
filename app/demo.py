"""Deterministic demo history so the dashboard has something to show in a pitch."""
from __future__ import annotations

import random
import time

from .questions import Question

# Chance of a correct answer per topic at the END of the demo period.
PROFILE = {
    "benefits": 0.95, "economics": 0.92, "service-types": 0.95, "shared-responsibility": 0.80, "cloud-models": 0.95,
    "core-architecture": 0.86, "compute": 0.90, "networking": 0.50, "storage": 0.86, "identity-security": 0.80,
    "cost-management": 0.52, "governance": 0.72, "management-tools": 0.82, "monitoring": 0.86,
}
SKIPPED = {"cost-management": 0.5}  # fewer attempts on the weakest topic, as real learners do


def build_demo_attempts(learner: str, bank: dict[str, Question], now: float | None = None,
                        days: int = 10, seed: int = 20261020) -> list[tuple]:
    now = now or time.time()
    rng = random.Random(seed)
    qs = list(bank.values())
    rows: list[tuple] = []
    for back in range(days - 1, -1, -1):
        progress = 1 - back / (days - 1)  # 0 = first day, 1 = today
        n_today = rng.randint(14, 24)
        for _ in range(n_today):
            q = rng.choice(qs)
            if rng.random() < SKIPPED.get(q.topic, 0):
                continue
            final = PROFILE[q.topic]
            p = min(0.97, 0.55 + (final + 0.05 - 0.55) * progress**0.6)  # improves over time
            correct = rng.random() < p
            chosen = q.answer if correct else rng.choice([i for i in range(4) if i != q.answer])
            if correct:
                confidence = "sure" if rng.random() < 0.9 else "guess"
            else:
                confidence = "sure" if rng.random() < 0.2 else "guess"
            ts = now - back * 86400 - rng.uniform(0, 8 * 3600) - 600
            rows.append((learner, q.id, q.topic, chosen, int(correct), confidence, "demo", round(rng.uniform(8, 40), 1), ts))
    rows.sort(key=lambda r: r[-1])
    return rows
