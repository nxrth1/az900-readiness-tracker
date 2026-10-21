from datetime import date, timedelta

import pytest

from app.planner import MOCK_MINUTES, PlanError, build_plan
from app.questions import TOPIC_WEIGHTS
from app.scoring import Attempt, readiness

NOW = 1_800_000_000.0
TODAY = date(2026, 10, 20)  # a Tuesday
ALL = [0, 1, 2, 3, 4, 5]


def fresh():
    return readiness([], NOW)


def weak_networking():
    at = [Attempt(f"{t}-{i}", t, True, "sure", NOW - 3600) for t in TOPIC_WEIGHTS for i in range(8)]
    at += [Attempt(f"n{i}", "networking", False, "sure", NOW - 3600) for i in range(10)]
    return readiness(at, NOW)


def plan(report=None, exam_in=21, hours=6, days=ALL):
    return build_plan(report or fresh(), TODAY, TODAY + timedelta(days=exam_in), hours, days)


def test_plan_ends_before_exam_and_uses_only_chosen_days():
    p = plan(days=[0, 2, 4])
    exam = date.fromisoformat(p["exam"])
    for d in p["days"]:
        dd = date.fromisoformat(d["date"])
        assert TODAY <= dd < exam and dd.weekday() in (0, 2, 4)


def test_minutes_match_budget_and_never_exceed_daily_capacity():
    p = plan(hours=6, days=ALL)
    per_day = 60  # 6h / 6 days
    for d in p["days"]:
        assert d["minutes"] == sum(b["minutes"] for b in d["blocks"])
        if not any(b["type"] == "mock" for b in d["blocks"]):
            assert d["minutes"] <= per_day
    assert p["total_minutes"] == sum(d["minutes"] for d in p["days"])


def test_weak_topic_gets_the_most_time():
    p = plan(weak_networking(), exam_in=28)
    assert p["focus"][0]["topic"] == "networking"
    # strong topics need no new study time, so the weak one gets (nearly) all of it
    assert p["focus"][0]["minutes"] >= 0.8 * sum(f["minutes"] for f in p["focus"])


def test_mixed_strengths_rank_by_need():
    at = [Attempt(f"{t}-{i}", t, True, "sure", NOW - 3600) for t in TOPIC_WEIGHTS for i in range(8)]
    at += [Attempt(f"n{i}", "networking", False, "sure", NOW - 3600) for i in range(10)]
    at += [Attempt(f"m{i}", "monitoring", i % 2 == 0, "sure", NOW - 3600) for i in range(10)]
    p = plan(readiness(at, NOW), exam_in=28)
    mins = {f["topic"]: f["minutes"] for f in p["focus"]}
    assert mins["networking"] > mins["monitoring"] > 0


def test_mock_exam_is_scheduled_about_a_week_out():
    p = plan(exam_in=28)
    assert p["mock_dates"]
    final_mock = date.fromisoformat(p["mock_dates"][-1])  # the one closest to the exam
    assert 3 <= (date.fromisoformat(p["exam"]) - final_mock).days <= 9
    assert len(p["mock_dates"]) == 2  # long runway adds a mid-point checkpoint
    day = next(d for d in p["days"] if d["date"] == p["mock_dates"][-1])
    assert any(b["type"] == "mock" and b["minutes"] == MOCK_MINUTES for b in day["blocks"])


def test_last_day_before_exam_is_light_review_only():
    p = plan(exam_in=14, days=[0, 1, 2, 3, 4, 5, 6])
    last = p["days"][-1]
    assert last["days_to_exam"] == 1
    assert {b["type"] for b in last["blocks"]} == {"review"}
    assert last["minutes"] < max(d["minutes"] for d in p["days"])


def test_confident_mistakes_are_reviewed_on_the_last_day():
    at = [Attempt(f"s{i}", "storage", False, "sure", NOW - 60) for i in range(3)]
    p = plan(readiness(at, NOW), exam_in=14, days=[0, 1, 2, 3, 4, 5, 6])
    assert "storage" in {b["topic"] for b in p["days"][-1]["blocks"]}


def test_no_topic_repeated_within_a_day():
    p = plan(exam_in=30, hours=10)
    for d in p["days"]:
        topics = [b["topic"] for b in d["blocks"] if b["type"] in ("learn", "practice")]
        assert len(topics) == len(set(topics))


def test_first_visit_is_learn_then_practice():
    p = plan(exam_in=30, hours=10)
    seen = set()
    for d in p["days"]:
        for b in d["blocks"]:
            if b["type"] in ("learn", "practice"):
                assert b["type"] == ("practice" if b["topic"] in seen else "learn")
                seen.add(b["topic"])


def test_more_hours_means_more_study_time():
    assert plan(hours=12)["total_minutes"] > plan(hours=4)["total_minutes"]


def test_new_learner_is_warned_the_plan_is_generic():
    assert any("not practised" in w for w in plan()["warnings"])
    assert not any("not practised" in w for w in plan(weak_networking())["warnings"])


def test_short_runway_warns():
    p = plan(exam_in=3, days=[0, 1, 2, 3, 4, 5, 6])
    assert any("little runway" in w for w in p["warnings"])


@pytest.mark.parametrize("kwargs", [
    dict(exam_in=0), dict(exam_in=-3), dict(exam_in=500), dict(hours=0.1), dict(hours=99), dict(days=[]), dict(days=[9]),
])
def test_bad_inputs_raise(kwargs):
    with pytest.raises(PlanError):
        plan(**kwargs)


def test_study_days_all_after_exam_is_an_error():
    # exam tomorrow (Wednesday); only Sunday selected, and today is Tuesday
    with pytest.raises(PlanError):
        build_plan(fresh(), TODAY, TODAY + timedelta(days=1), 5, [6])


def test_api_plan_endpoint(client):
    client.post("/api/demo/seed", params={"learner": "learner-plan-1"})
    exam = (date.today() + timedelta(days=21)).isoformat()
    r = client.get("/api/plan", params={"learner": "learner-plan-1", "exam_date": exam, "hours_per_week": 6})
    assert r.status_code == 200
    body = r.json()
    assert body["days"] and body["focus"] and body["days_to_exam"] == 21
    assert client.get("/api/plan", params={"learner": "learner-plan-1", "exam_date": "2020-01-01"}).status_code == 422
    assert client.get("/api/plan", params={"learner": "learner-plan-1", "exam_date": exam, "days": "a,b"}).status_code == 422
