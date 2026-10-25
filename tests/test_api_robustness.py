import time

from app.questions import load_bank

L = "learner-robust-0001"


def _q():
    return next(iter(load_bank().values()))


def _answer(client, **extra):
    q = _q()
    body = {"learner": L, "question_id": q.id, "choice": q.answer, **extra}
    return client.post("/api/answer", json=body)


def _answered(client):
    return client.get("/api/readiness", params={"learner": L}).json()["overall"]["answered"]


def test_retrying_an_answer_with_the_same_attempt_id_counts_once(client):
    first = _answer(client, attempt_id="attempt-0001").json()
    again = _answer(client, attempt_id="attempt-0001").json()
    assert first["duplicate"] is False and again["duplicate"] is True
    assert again["correct"] == first["correct"] and again["explanation"] == first["explanation"]  # same payload
    assert _answered(client) == 1


def test_new_attempt_ids_and_missing_ids_each_count(client):
    _answer(client, attempt_id="attempt-0001")
    _answer(client, attempt_id="attempt-0002")
    _answer(client)
    assert _answered(client) == 3


def test_malformed_attempt_id_is_rejected(client):
    assert _answer(client, attempt_id="short").status_code == 422
    assert _answer(client, attempt_id="has spaces in it!").status_code == 422


def test_history_limit_returns_a_clear_conflict(client, monkeypatch):
    monkeypatch.setenv("MAX_ATTEMPTS_PER_LEARNER", "2")
    assert _answer(client).status_code == 200 and _answer(client).status_code == 200
    r = _answer(client)
    assert r.status_code == 409 and "Export your data" in r.json()["detail"]
    assert _answered(client) == 2


def test_learner_ids_must_be_long_enough_to_be_unguessable(client):
    assert client.get("/api/readiness", params={"learner": "a" * 15}).status_code == 422
    assert client.get("/api/readiness", params={"learner": "a" * 16}).status_code == 200
    assert client.get("/api/readiness", params={"learner": "a" * 65}).status_code == 422
    assert client.delete(f"/api/learner/{'b' * 8}").status_code == 422
    assert client.get(f"/api/learner/{'b' * 8}/export").status_code == 422


def test_demo_seed_will_not_silently_destroy_real_history(client):
    _answer(client)
    refused = client.post("/api/demo/seed", params={"learner": L})
    assert refused.status_code == 409 and "replace=true" in refused.json()["detail"]
    assert _answered(client) == 1  # untouched
    assert client.post("/api/demo/seed", params={"learner": L, "replace": "true"}).status_code == 200
    assert _answered(client) > 100
    # demo-on-demo needs no confirmation: nothing real to lose
    assert client.post("/api/demo/seed", params={"learner": L}).status_code == 200


def test_demo_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO", "false")
    assert client.post("/api/demo/seed", params={"learner": L}).status_code == 404


def test_import_rejects_future_timestamps_and_oversized_history(client):
    q = _q()
    row = {"question_id": q.id, "choice": q.answer, "confidence": "sure", "mode": "practice", "ts": time.time()}
    assert client.post(f"/api/learner/{L}/import", json={"version": 1, "attempts": [row]}).status_code == 200
    future = {**row, "ts": time.time() + 10 * 86400}
    assert client.post(f"/api/learner/{L}/import", json={"version": 1, "attempts": [future]}).status_code == 422
    too_many = {"version": 1, "attempts": [row] * 10_001}
    assert client.post(f"/api/learner/{L}/import", json=too_many).status_code in (413, 422)
    assert _answered(client) == 1  # failed imports changed nothing


def test_saved_mode_caps_the_number_of_ids(client):
    ids = [f"q{i}" for i in range(500)]
    assert client.get("/api/quiz", params={"learner": L, "mode": "saved", "question_ids": ids}).status_code == 422


def test_readiness_ignores_answers_to_retired_questions(client):
    from app import db

    _answer(client)
    db.add_attempt(L, "retired-question", "compute", 0, True, "sure")
    assert _answered(client) == 1


def test_error_shape_is_consistent_for_the_frontend(client):
    for r in (
        client.get("/api/quiz", params={"learner": L, "mode": "topic", "topic": "nope"}),
        client.post("/api/explain", json={"question_id": "nope", "choice": 0}),
        client.get("/api/readiness", params={"learner": "bad"}),
    ):
        assert r.status_code in (404, 422) and "detail" in r.json()


def test_ready_and_health_payloads(client):
    ready = client.get("/api/ready").json()
    assert ready["status"] == "ready" and ready["schema"] >= 2 and ready["questions"] == len(load_bank())
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["version"]
