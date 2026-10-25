"""Official Microsoft Learn study links, one per topic, plus content-review transparency.

The data lives in ``data/learn_links.json`` so it can be re-verified and edited without touching code.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from .questions import DOMAINS, REVIEW_FILE, TOPIC_DOMAIN

LINKS_FILE = Path(os.environ.get("LEARN_LINKS_FILE", Path(__file__).parent / "data" / "learn_links.json"))
_HOST = "https://learn.microsoft.com/"


class LearnLinksError(ValueError):
    pass


def validate(data: dict) -> list[str]:
    problems: list[str] = []
    topics = data.get("topics", {})
    for topic in TOPIC_DOMAIN:
        if topic not in topics:
            problems.append(f"{topic}: missing Learn link")
    for topic in topics.keys() - TOPIC_DOMAIN.keys():
        problems.append(f"{topic}: link for an unknown topic")
    for domain in DOMAINS:
        if domain not in data.get("paths", {}):
            problems.append(f"{domain}: missing learning-path link")
    entries = [*topics.values(), *data.get("paths", {}).values()]
    for entry in entries:
        if not str(entry.get("title", "")).strip():
            problems.append(f"{entry.get('url')}: missing title")
        if not str(entry.get("url", "")).startswith(_HOST):
            problems.append(f"{entry.get('url')}: links must point at {_HOST}")
    for key in ("study_guide", "practice_assessment", "exam_page"):
        if not str(data.get(key, "")).startswith(_HOST):
            problems.append(f"{key}: must be a {_HOST} URL")
    for key in ("verified_on", "skills_measured_as_of"):
        if not data.get(key):
            problems.append(f"{key}: required")
    return problems


@lru_cache(maxsize=1)
def load_links() -> dict:
    data = json.loads(LINKS_FILE.read_text(encoding="utf-8"))
    problems = validate(data)
    if problems:
        raise LearnLinksError("Invalid learn_links.json:\n- " + "\n- ".join(problems))
    return data


def topic_link(topic: str) -> dict:
    return load_links()["topics"][topic]


def content_info(total_questions: int) -> dict:
    """What the learner is entitled to know about how trustworthy the question bank is."""
    links = load_links()
    review = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    reviewed = sum(value is not None for value in review["questions"].values())
    return {
        "skills_measured_as_of": links["skills_measured_as_of"],
        "links_verified_on": links["verified_on"],
        "questions": total_questions,
        "reviewed": reviewed,
        "study_guide_url": links["study_guide"],
        "practice_assessment_url": links["practice_assessment"],
        "exam_page_url": links["exam_page"],
    }


if __name__ == "__main__":  # pragma: no cover - prints every link so a human can open and re-verify them
    links = load_links()
    print(f"OK: links valid (verified {links['verified_on']}, skills measured as of {links['skills_measured_as_of']})")
    for key in ("study_guide", "practice_assessment", "exam_page"):
        print(f"  {key}: {links[key]}")
    for topic, entry in links["topics"].items():
        print(f"  {topic:<22} {entry['url']}")
