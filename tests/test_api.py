from app.explain import SYSTEM_PROMPT, build_user_prompt
from app.questions import load_bank

L = "learner-test-01"


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert len(meta["domains"]) == 3
    assert abs(sum(d["weight"] for d in meta["domains"]) - 1) < 1e-9
    assert meta["total_questions"] >= 60


def test_index_and_static_are_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Readiness Tracker" in r.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_quiz_does_not_leak_answers(client):
    data = client.get("/api/quiz", params={"learner": L, "mode": "adaptive", "n": 10}).json()
    assert len(data["questions"]) == 10
    for q in data["questions"]:
        assert set(q) == {"id", "domain", "topic", "topic_name", "difficulty", "q", "options"}


def test_answer_flow_updates_readiness(client):
    bank = load_bank()
    q = next(iter(bank.values()))
    wrong = (q.answer + 1) % 4

    r = client.post("/api/answer", json={"learner": L, "question_id": q.id, "choice": q.answer}).json()
    assert r["correct"] is True and r["why_not"] == "" and r["correct_index"] == q.answer

    r = client.post("/api/answer", json={"learner": L, "question_id": q.id, "choice": wrong, "confidence": "sure"}).json()
    assert r["correct"] is False and r["why_not"] and r["explanation"]

    rep = client.get("/api/readiness", params={"learner": L}).json()
    assert rep["overall"]["answered"] == 2
    assert rep["misconceptions"][0]["topic"] == q.topic
    assert len(rep["topics"]) == 14 and len(rep["domains"]) == 3


def test_validation(client):
    q = next(iter(load_bank().values()))
    assert client.post("/api/answer", json={"learner": L, "question_id": q.id, "choice": 4}).status_code == 422
    assert client.post("/api/answer", json={"learner": L, "question_id": "nope", "choice": 0}).status_code == 404
    assert client.post("/api/answer", json={"learner": "x", "question_id": q.id, "choice": 0}).status_code == 422
    assert client.post("/api/answer", json={"learner": L, "question_id": q.id, "choice": 0, "confidence": "maybe"}).status_code == 422
    assert client.get("/api/quiz", params={"learner": L, "mode": "topic", "topic": "zzz"}).status_code == 422
    assert client.get("/api/readiness", params={"learner": "bad id!"}).status_code == 422


def test_learners_are_isolated_and_reset_works(client):
    q = next(iter(load_bank().values()))
    client.post("/api/answer", json={"learner": L, "question_id": q.id, "choice": q.answer})
    assert client.get("/api/readiness", params={"learner": "someone-else-1"}).json()["overall"]["answered"] == 0
    assert client.delete(f"/api/learner/{L}").json()["deleted"] == 1
    assert client.get("/api/readiness", params={"learner": L}).json()["overall"]["answered"] == 0


def test_export_import_round_trip_and_reject_unknown_question(client):
    q = next(iter(load_bank().values()))
    client.post("/api/answer", json={
        "learner": L, "question_id": q.id, "choice": q.answer, "confidence": "guess",
        "mode": "topic", "seconds": 12.5,
    })
    exported = client.get(f"/api/learner/{L}/export").json()
    assert exported["format"] == "az900-readiness-tracker"
    assert len(exported["attempts"]) == 1

    other = "learner-test-02"
    assert client.post(f"/api/learner/{other}/import", json=exported).json()["imported"] == 1
    assert client.get("/api/readiness", params={"learner": other}).json()["overall"]["answered"] == 1
    assert client.post(f"/api/learner/{other}/import", json={
        "version": 1, "attempts": [{**exported["attempts"][0], "question_id": "missing"}],
    }).status_code == 422
    assert client.get("/api/readiness", params={"learner": other}).json()["overall"]["answered"] == 1


def test_demo_seed_populates_dashboard(client):
    assert client.post("/api/demo/seed", params={"learner": L}).json()["seeded"] > 100
    rep = client.get("/api/readiness", params={"learner": L}).json()
    assert rep["overall"]["answered"] > 100
    assert len(rep["history"]) >= 5
    assert 0.4 < rep["overall"]["score"] < 0.9


def test_exam_mode_returns_forty(client):
    data = client.get("/api/quiz", params={"learner": L, "mode": "exam"}).json()
    assert len(data["questions"]) == 40


def test_saved_question_mode_returns_only_requested_questions(client):
    q = next(iter(load_bank().values()))
    response = client.get("/api/quiz", params={
        "learner": L, "mode": "saved", "n": 1, "question_ids": [q.id],
    })
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["questions"]] == [q.id]
    assert client.get("/api/quiz", params={
        "learner": L, "mode": "saved", "question_ids": ["unknown"],
    }).status_code == 422


def test_explain_falls_back_without_api_key(client):
    q = next(iter(load_bank().values()))
    r = client.post("/api/explain", json={"question_id": q.id, "choice": q.answer}).json()
    assert r["source"] == "builtin" and r["text"] == q.why
    wrong = (q.answer + 1) % 4
    r = client.post("/api/explain", json={"question_id": q.id, "choice": wrong, "language": "sw"}).json()
    assert q.why_not[wrong] in r["text"]


def test_prompt_contains_ground_truth_and_guardrails():
    q = next(iter(load_bank().values()))
    wrong = (q.answer + 1) % 4
    p = build_user_prompt(q, wrong, "simple", "sw")
    assert q.why in p and q.options[q.answer] in p and "Kiswahili" in p and "incorrect" in p
    assert "ground truth" in SYSTEM_PROMPT and "110 words" in SYSTEM_PROMPT and "never claim to be official" in SYSTEM_PROMPT.lower()
