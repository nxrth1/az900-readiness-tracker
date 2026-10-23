"""Question bank: loading, validation and lookup.

The bank is a plain JSON file so that anyone can add questions without touching code.
Run ``python -m app.questions`` to validate it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(os.environ.get("QUESTIONS_FILE", Path(__file__).parent / "data" / "questions.json"))
REVIEW_FILE = Path(os.environ.get("QUESTION_REVIEW_FILE", Path(__file__).parent / "data" / "question_review.json"))

# Domains and topics follow the three domains of the public AZ-900 skills outline.
# Weights are the midpoints of the published ranges (25-30, 35-40, 30-35), normalised to sum to 1.
DOMAINS: dict[str, dict] = {
    "cloud-concepts": {
        "name": "Cloud concepts",
        "range": (25, 30),
        "topics": {
            "benefits": "Cloud benefits",
            "economics": "Cloud economics",
            "service-types": "Service types",
            "shared-responsibility": "Shared responsibility",
            "cloud-models": "Cloud models",
        },
    },
    "architecture-services": {
        "name": "Azure architecture and services",
        "range": (35, 40),
        "topics": {
            "core-architecture": "Core architecture",
            "compute": "Compute",
            "networking": "Networking",
            "storage": "Storage",
            "identity-security": "Identity and security",
        },
    },
    "management-governance": {
        "name": "Management and governance",
        "range": (30, 35),
        "topics": {
            "cost-management": "Cost management",
            "governance": "Governance and compliance",
            "management-tools": "Management tools",
            "monitoring": "Monitoring",
        },
    },
}

_total = sum(sum(d["range"]) / 2 for d in DOMAINS.values())
DOMAIN_WEIGHTS: dict[str, float] = {k: (sum(d["range"]) / 2) / _total for k, d in DOMAINS.items()}
TOPIC_DOMAIN: dict[str, str] = {t: d for d, v in DOMAINS.items() for t in v["topics"]}
TOPIC_NAMES: dict[str, str] = {t: n for v in DOMAINS.values() for t, n in v["topics"].items()}
# Each topic carries an equal share of its domain's exam weight.
TOPIC_WEIGHTS: dict[str, float] = {
    t: DOMAIN_WEIGHTS[d] / len(DOMAINS[d]["topics"]) for t, d in TOPIC_DOMAIN.items()
}


@dataclass(frozen=True)
class Question:
    id: str
    domain: str
    topic: str
    difficulty: int
    q: str
    options: tuple[str, ...]
    answer: int
    why: str
    why_not: tuple[str, ...]

    def public(self) -> dict:
        """The question as sent to the browser: no answer, no explanations."""
        return {
            "id": self.id,
            "domain": self.domain,
            "topic": self.topic,
            "topic_name": TOPIC_NAMES[self.topic],
            "difficulty": self.difficulty,
            "q": self.q,
            "options": list(self.options),
        }


class QuestionBankError(ValueError):
    pass


def validate(raw: list[dict]) -> list[str]:
    """Return a list of human-readable problems (empty list means the bank is valid)."""
    problems: list[str] = []
    seen: set[str] = set()
    for i, r in enumerate(raw):
        qid = r.get("id", f"#{i}")
        if qid in seen:
            problems.append(f"{qid}: duplicate id")
        seen.add(qid)
        if r.get("topic") not in TOPIC_DOMAIN:
            problems.append(f"{qid}: unknown topic {r.get('topic')!r}")
        elif TOPIC_DOMAIN[r["topic"]] != r.get("domain"):
            problems.append(f"{qid}: topic {r['topic']!r} does not belong to domain {r.get('domain')!r}")
        opts = r.get("options", [])
        if len(opts) != 4 or len(set(opts)) != 4:
            problems.append(f"{qid}: needs exactly 4 distinct options")
        if r.get("answer") not in range(len(opts)):
            problems.append(f"{qid}: answer index out of range")
        wn = r.get("why_not", [])
        if len(wn) != len(opts):
            problems.append(f"{qid}: why_not must have one entry per option")
        else:
            for j, note in enumerate(wn):
                if j == r.get("answer") and note:
                    problems.append(f"{qid}: why_not for the correct option must be empty")
                if j != r.get("answer") and not note:
                    problems.append(f"{qid}: missing why_not for option {j}")
        for field in ("q", "why"):
            if not str(r.get(field, "")).strip():
                problems.append(f"{qid}: empty {field}")
        if r.get("difficulty") not in (1, 2, 3):
            problems.append(f"{qid}: difficulty must be 1, 2 or 3")
    return problems


def validate_review_metadata(raw: list[dict], metadata: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(metadata, dict):
        return ["question review metadata must be an object"]
    if not isinstance(metadata.get("source_url"), str) or not metadata["source_url"].startswith("https://"):
        problems.append("question review metadata needs an HTTPS source_url")
    reviews = metadata.get("questions")
    if not isinstance(reviews, dict):
        return problems + ["question review metadata needs a questions object"]
    bank_ids = {question.get("id") for question in raw}
    for missing in sorted(bank_ids - reviews.keys()):
        problems.append(f"{missing}: missing question review metadata")
    for stale in sorted(reviews.keys() - bank_ids):
        problems.append(f"{stale}: review metadata has no matching question")
    for question_id, reviewed_on in reviews.items():
        if reviewed_on is None:
            continue
        try:
            checked = date.fromisoformat(reviewed_on)
            if checked.isoformat() != reviewed_on or checked > date.today():
                raise ValueError
        except (TypeError, ValueError):
            problems.append(f"{question_id}: reviewed_on must be null or an ISO date")
    return problems


@lru_cache(maxsize=1)
def load_bank() -> dict[str, Question]:
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    problems = validate(raw)
    review = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    problems.extend(validate_review_metadata(raw, review))
    if problems:
        raise QuestionBankError("Invalid question bank:\n- " + "\n- ".join(problems))
    return {
        r["id"]: Question(
            id=r["id"],
            domain=r["domain"],
            topic=r["topic"],
            difficulty=r["difficulty"],
            q=r["q"],
            options=tuple(r["options"]),
            answer=r["answer"],
            why=r["why"],
            why_not=tuple(r["why_not"]),
        )
        for r in raw
    }


if __name__ == "__main__":  # pragma: no cover
    bank = load_bank()
    by_domain: dict[str, int] = {}
    for q in bank.values():
        by_domain[q.domain] = by_domain.get(q.domain, 0) + 1
    print(f"OK: {len(bank)} questions")
    review_data = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    reviewed = sum(value is not None for value in review_data["questions"].values())
    print(f"Content review: {reviewed}/{len(review_data['questions'])} checked against {review_data['source_url']}")
    for d, n in by_domain.items():
        print(f"  {DOMAINS[d]['name']}: {n} ({n / len(bank):.0%}; exam weight ~{DOMAIN_WEIGHTS[d]:.0%})")
