import math

from app.questions import TOPIC_WEIGHTS
from app.scoring import HALF_LIFE_DAYS, Attempt, history, readiness, topic_posteriors

NOW = 1_800_000_000.0
DAY = 86400.0


def att(topic="compute", correct=True, conf="sure", age_days=0.0, qid="q1"):
    return Attempt(qid, topic, correct, conf, NOW - age_days * DAY)


def score_of(attempts, topic="compute"):
    return topic_posteriors(attempts, NOW)[topic]["score"]


def test_topic_weights_sum_to_one():
    assert math.isclose(sum(TOPIC_WEIGHTS.values()), 1.0)


def test_new_learner_starts_neutral_and_uncertain():
    r = readiness([], NOW)
    assert r["overall"]["answered"] == 0
    assert r["overall"]["status"] == "start"
    assert math.isclose(r["overall"]["score"], 0.5)
    assert r["overall"]["p_pass"] < 0.01


def test_correct_answers_raise_and_wrong_answers_lower_the_score():
    base = score_of([])
    assert score_of([att(correct=True)]) > base
    assert score_of([att(correct=False, conf="guess")]) < base


def test_lucky_guess_counts_less_than_a_confident_correct_answer():
    assert score_of([att(conf="guess")]) < score_of([att(conf="sure")])
    # a guessed-correct answer carries equal success and failure credit: it tells us nothing about the mean
    assert math.isclose(score_of([att(conf="guess")]), 0.5)
    # ...but it still tightens the range slightly, because we did observe something
    guess = topic_posteriors([att(conf="guess")], NOW)["compute"]
    blank = topic_posteriors([], NOW)["compute"]
    assert guess["sd"] < blank["sd"]


def test_confident_error_hurts_more_than_a_wrong_guess():
    assert score_of([att(correct=False, conf="sure")]) < score_of([att(correct=False, conf="guess")])


def test_old_evidence_fades():
    fresh = score_of([att(correct=False, age_days=0)])
    stale = score_of([att(correct=False, age_days=HALF_LIFE_DAYS * 3)])
    assert fresh < stale < 0.5 + 1e-9
    assert stale > fresh


def test_more_evidence_narrows_the_range():
    few = topic_posteriors([att(qid=f"q{i}") for i in range(2)], NOW)["compute"]
    many = topic_posteriors([att(qid=f"q{i}") for i in range(20)], NOW)["compute"]
    assert (many["high"] - many["low"]) < (few["high"] - few["low"])


def test_perfect_learner_reaches_ready():
    attempts = [att(topic=t, qid=f"{t}-{i}") for t in TOPIC_WEIGHTS for i in range(10)]
    o = readiness(attempts, NOW)["overall"]
    assert o["score"] > 0.85
    assert o["p_pass"] > 0.95
    assert o["status"] == "ready"


def test_struggling_learner_is_told_to_keep_practising():
    attempts = [att(topic=t, correct=False, conf="guess", qid=f"{t}-{i}") for t in TOPIC_WEIGHTS for i in range(6)]
    o = readiness(attempts, NOW)["overall"]
    assert o["score"] < 0.3
    assert o["status"] == "keep"


def test_weak_topic_is_top_win():
    attempts = [att(topic=t, qid=f"{t}-{i}") for t in TOPIC_WEIGHTS for i in range(8)]
    attempts += [att(topic="networking", correct=False, qid=f"n{i}") for i in range(8)]
    r = readiness(attempts, NOW)
    assert r["wins"][0]["topic"] == "networking"
    assert r["wins"] == sorted(r["wins"], key=lambda w: w["gain"], reverse=True)


def test_confident_mistakes_are_reported():
    attempts = [att(topic="storage", correct=False, conf="sure", qid=f"s{i}") for i in range(3)]
    r = readiness(attempts, NOW)
    assert r["misconceptions"][0]["topic"] == "storage" and r["misconceptions"][0]["count"] == 3


def test_future_attempts_are_ignored():
    r = readiness([att(age_days=-2)], NOW)
    assert r["overall"]["answered"] == 0


def test_domain_scores_are_weighted_means_of_topics():
    r = readiness([att(topic="compute", qid="c")], NOW)
    d = next(x for x in r["domains"] if x["id"] == "architecture-services")
    topics = {t["id"]: t["score"] for t in r["topics"]}
    expected = sum(topics[t] for t in d["topics"]) / len(d["topics"])
    assert math.isclose(d["score"], expected)


def test_history_is_chronological_and_improves_with_practice():
    attempts = []
    for day in range(6, -1, -1):
        for t in TOPIC_WEIGHTS:
            attempts.append(att(topic=t, qid=f"{t}-{day}", age_days=day + 0.3))
    h = history(attempts, NOW, days=7)
    dates = [x["date"] for x in h]
    assert dates == sorted(dates)
    assert h[-1]["score"] > h[0]["score"]


def test_history_empty_for_no_attempts():
    assert history([], NOW) == []


def test_history_reports_answers_per_study_day():
    attempts = [att(qid="first", age_days=0.1), att(qid="second", age_days=0.1)]
    h = history(attempts, NOW)
    assert len(h) == 1
    assert h[0]["activity"] == 2
