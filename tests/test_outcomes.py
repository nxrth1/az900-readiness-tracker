"""Reported real-world results and the calibration report built from them."""
from datetime import date, timedelta

import pytest

from app import db
from app.calibration import calibration_report
from app.questions import load_bank

L = "learner-outcome-0001"
TODAY = date.today().isoformat()


def _practise(client, n=12, correct=True):
    for q in list(load_bank().values())[:n]:
        choice = q.answer if correct else (q.answer + 1) % 4
        client.post("/api/answer", json={"learner": L, "question_id": q.id, "choice": choice})


def _exam(**kw):
    return {"learner": L, "kind": "exam", "happened_on": TODAY, "passed": True, **kw}


def test_reporting_an_exam_stores_the_apps_prediction_at_that_moment(client):
    _practise(client, 12)
    r = client.post("/api/outcome", json=_exam(score=742))
    assert r.status_code == 200
    snap = r.json()["snapshot"]
    assert snap["answered"] == 12 and 0 < snap["est_score"] < 1 and 0 <= snap["p_pass"] <= 1
    stored = client.get("/api/outcomes", params={"learner": L}).json()["outcomes"]
    assert len(stored) == 1 and stored[0]["passed"] == 1 and stored[0]["score"] == 742


def test_snapshot_ignores_practice_done_after_the_result_date(client):
    _practise(client, 12)  # all answered "today"
    last_week = (date.today() - timedelta(days=7)).isoformat()
    snap = client.post("/api/outcome", json=_exam(happened_on=last_week)).json()["snapshot"]
    assert snap["answered"] == 0  # at the time of that exam the learner had not practised yet


def test_client_cannot_supply_or_forge_the_snapshot(client):
    _practise(client, 5)
    r = client.post("/api/outcome", json={**_exam(), "est_score": 0.99, "p_pass": 0.99})
    assert r.status_code == 200 and r.json()["snapshot"]["p_pass"] != 0.99  # extra fields are ignored


@pytest.mark.parametrize("body", [
    {"kind": "exam"},                                                    # missing passed
    {"kind": "exam", "passed": True, "score": 50},                       # scaled score out of range
    {"kind": "practice_assessment"},                                     # missing percent
    {"kind": "practice_assessment", "score": 140},                       # percent out of range
    {"kind": "practice_assessment", "score": 80, "passed": True},        # passed is exam-only
    {"kind": "exam", "passed": True, "happened_on": "2999-01-01"},       # future
    {"kind": "exam", "passed": True, "happened_on": "2001-01-01"},       # older than a year
    {"kind": "mock", "passed": True},                                    # unknown kind
])
def test_invalid_reports_are_rejected(client, body):
    payload = {"learner": L, "happened_on": TODAY, **body}
    assert client.post("/api/outcome", json=payload).status_code == 422
    assert client.get("/api/outcomes", params={"learner": L}).json()["outcomes"] == []


def test_practice_assessment_report(client):
    _practise(client, 8)
    assert client.post("/api/outcome", json={
        "learner": L, "kind": "practice_assessment", "happened_on": TODAY, "score": 76.5,
    }).status_code == 200


def test_report_limit(client, monkeypatch):
    monkeypatch.setenv("MAX_OUTCOMES_PER_LEARNER", "2")
    assert client.post("/api/outcome", json=_exam()).status_code == 200
    assert client.post("/api/outcome", json=_exam()).status_code == 200
    r = client.post("/api/outcome", json=_exam())
    assert r.status_code == 409 and "already reported" in r.json()["detail"]


def test_resetting_a_learner_also_deletes_their_reported_results(client):
    _practise(client, 3)
    client.post("/api/outcome", json=_exam())
    client.delete(f"/api/learner/{L}")
    assert client.get("/api/outcomes", params={"learner": L}).json()["outcomes"] == []
    assert db.get_all_outcomes() == []


def test_results_are_private_to_their_learner(client):
    client.post("/api/outcome", json=_exam())
    other = client.get("/api/outcomes", params={"learner": "somebody-else-00001"}).json()
    assert other["outcomes"] == []
    assert all("learner" not in o for o in db.get_all_outcomes())  # aggregate view carries no ids


# ---------------------------------------------------------------- calibration maths

def _o(kind="exam", p=0.5, passed=1, est=0.6, score=None, answered=50):
    return {"kind": kind, "p_pass": p, "passed": passed, "est_score": est, "score": score, "answered": answered}


def test_well_calibrated_predictions_beat_the_baseline():
    rows = [_o(p=0.9, passed=1)] * 9 + [_o(p=0.9, passed=0)] + [_o(p=0.1, passed=0)] * 9 + [_o(p=0.1, passed=1)]
    rep = calibration_report(rows)["exam"]
    assert rep["n"] == 20 and rep["pass_rate"] == 0.5
    assert rep["brier"] < rep["baseline_brier"] and rep["beats_baseline"] is True
    top = rep["bins"][-1]
    assert top["n"] == 10 and top["mean_predicted"] == pytest.approx(0.9) and top["observed_pass_rate"] == pytest.approx(0.9)
    assert "Not enough" in rep["verdict"]  # 20 results is still too few to judge


def test_confident_but_wrong_predictions_are_flagged():
    rows = [_o(p=0.95, passed=0)] * 20 + [_o(p=0.95, passed=1)] * 20 + [_o(p=0.05, passed=1)] * 5
    rep = calibration_report(rows)["exam"]
    assert rep["beats_baseline"] is False and "recalibrate" in rep["verdict"]


def test_low_evidence_results_are_ignored():
    rows = [_o(answered=3, p=0.99, passed=0), _o(answered=40, p=0.7, passed=1)]
    rep = calibration_report(rows, min_answered=20)
    assert rep["ignored_low_evidence"] == 1 and rep["exam"]["n"] == 1


def test_practice_assessment_bias_and_correlation():
    rows = [_o("practice_assessment", est=0.80, score=70, passed=None),
            _o("practice_assessment", est=0.60, score=50, passed=None),
            _o("practice_assessment", est=0.70, score=60, passed=None)]
    pa = calibration_report(rows)["practice_assessment"]
    assert pa["bias_points"] == pytest.approx(10.0)       # the app is 10 points optimistic
    assert pa["mean_abs_error_points"] == pytest.approx(10.0)
    assert pa["correlation"] == pytest.approx(1.0)


def test_empty_report_is_safe():
    rep = calibration_report([])
    assert rep["exam"] == {"n": 0} and rep["practice_assessment"] == {"n": 0}


def test_migration_3_upgrades_a_v2_database(db_path):
    import sqlite3

    db.init_db()
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE outcomes")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()
    db.init_db()
    assert db.schema_version() == db.LATEST_VERSION == 3
    assert db.get_all_outcomes() == []
