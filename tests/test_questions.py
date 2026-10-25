import json
from collections import Counter

from app.questions import (
    DATA_FILE,
    DOMAIN_WEIGHTS,
    DOMAINS,
    REVIEW_FILE,
    TOPIC_DOMAIN,
    load_bank,
    validate,
    validate_review_metadata,
)


def test_bank_is_valid():
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    assert validate(raw) == []


def test_question_review_metadata_covers_the_bank_and_is_honest_about_status():
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    review = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    assert validate_review_metadata(raw, review) == []
    assert review["source_url"].startswith("https://learn.microsoft.com/")
    assert set(review["questions"]) == {question["id"] for question in raw}
    assert all(value is None for value in review["questions"].values())


def test_question_review_metadata_rejects_missing_questions_and_bad_dates():
    assert validate_review_metadata(
        [{"id": "q1"}], {"source_url": "https://learn.microsoft.com", "questions": {"old": "yesterday"}}
    ) == [
        "q1: missing question review metadata",
        "old: review metadata has no matching question",
        "old: reviewed_on must be null or an ISO date",
    ]


def test_enough_questions_and_unique_ids():
    bank = load_bank()
    assert len(bank) >= 60
    assert len(set(bank)) == len(bank)


def test_every_topic_has_enough_questions():
    counts = Counter(q.topic for q in load_bank().values())
    for topic in TOPIC_DOMAIN:
        assert counts[topic] >= 3, f"{topic} has only {counts[topic]} questions"


def test_domain_mix_roughly_matches_exam_weights():
    bank = load_bank()
    counts = Counter(q.domain for q in bank.values())
    for d in DOMAINS:
        share = counts[d] / len(bank)
        assert abs(share - DOMAIN_WEIGHTS[d]) < 0.08, f"{d}: {share:.2f} vs {DOMAIN_WEIGHTS[d]:.2f}"


def test_correct_answer_positions_are_balanced():
    pos = Counter(q.answer for q in load_bank().values())
    assert len(pos) == 4
    assert max(pos.values()) <= 0.4 * len(load_bank())


def test_public_view_hides_answers():
    q = next(iter(load_bank().values()))
    pub = q.public()
    assert "answer" not in pub and "why" not in pub and "why_not" not in pub


def test_weights_sum_to_one():
    assert abs(sum(DOMAIN_WEIGHTS.values()) - 1) < 1e-9


def test_validator_catches_problems():
    bad = [{"id": "x", "domain": "cloud-concepts", "topic": "compute", "difficulty": 9, "q": "", "options": ["a", "a", "b", "c"],
            "answer": 7, "why": "", "why_not": ["", "", ""]}]
    problems = validate(bad)
    assert len(problems) >= 5
