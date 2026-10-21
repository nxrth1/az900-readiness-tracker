import random
from collections import Counter

from app.questions import DOMAIN_WEIGHTS, load_bank
from app.scoring import Attempt
from app.selection import EXAM_SIZE, pick_questions

NOW = 1_800_000_000.0
BANK = load_bank()


def run(**kw):
    kw.setdefault("rng", random.Random(1))
    return pick_questions(BANK, kw.pop("attempts", []), NOW, **kw)


def test_topic_mode_only_returns_that_topic():
    qs = run(mode="topic", topic="networking", n=8)
    assert qs and all(q.topic == "networking" for q in qs)


def test_domain_mode_only_returns_that_domain():
    qs = run(mode="domain", domain="cloud-concepts", n=10)
    assert len(qs) == 10 and all(q.domain == "cloud-concepts" for q in qs)


def test_no_duplicates_and_respects_n():
    qs = run(mode="adaptive", n=10)
    assert len(qs) == 10 and len({q.id for q in qs}) == 10


def test_exam_mode_size_and_domain_mix():
    qs = run(mode="exam", n=EXAM_SIZE)
    assert len(qs) == EXAM_SIZE and len({q.id for q in qs}) == EXAM_SIZE
    counts = Counter(q.domain for q in qs)
    for d, w in DOMAIN_WEIGHTS.items():
        assert abs(counts[d] / EXAM_SIZE - w) < 0.06


def test_adaptive_prefers_the_weak_topic():
    attempts = []
    for q in BANK.values():
        if q.topic == "networking":
            attempts.append(Attempt(q.id, q.topic, False, "sure", NOW - 3600))
        else:
            attempts.append(Attempt(q.id, q.topic, True, "sure", NOW - 3 * 86400))
    qs = run(mode="adaptive", n=10)
    qs_with_history = pick_questions(BANK, attempts, NOW, mode="adaptive", n=10, rng=random.Random(2))
    net = sum(q.topic == "networking" for q in qs_with_history)
    assert net >= 3
    assert net > sum(q.topic == "networking" for q in qs)


def test_adaptive_resurfaces_wrong_answers_before_fresh_correct_ones():
    wrong = next(iter(BANK.values()))
    attempts = [Attempt(wrong.id, wrong.topic, False, "sure", NOW - 2 * 86400)]
    attempts += [Attempt(q.id, q.topic, True, "sure", NOW - 600) for q in BANK.values() if q.id != wrong.id][:20]
    qs = pick_questions(BANK, attempts, NOW, mode="adaptive", n=5, rng=random.Random(3))
    assert wrong.id in {q.id for q in qs}


def test_unknown_filters_return_empty():
    assert run(mode="topic", topic="nope") == []
