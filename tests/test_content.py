"""Study links, content-review transparency and the review workflow."""
import json
from datetime import date, timedelta

import pytest

from app import learn, review
from app.questions import TOPIC_DOMAIN, load_bank


def test_every_topic_has_an_official_learn_link():
    links = learn.load_links()
    assert set(links["topics"]) == set(TOPIC_DOMAIN)
    for entry in [*links["topics"].values(), *links["paths"].values()]:
        assert entry["url"].startswith("https://learn.microsoft.com/en-us/training/")
        assert entry["title"]
    assert links["skills_measured_as_of"] and links["verified_on"]


def test_link_validation_catches_mistakes():
    good = json.loads(json.dumps(learn.load_links()))
    assert learn.validate(good) == []
    bad = json.loads(json.dumps(good))
    del bad["topics"]["compute"]
    bad["topics"]["storage"]["url"] = "https://example.com/not-microsoft"
    bad["topics"]["bogus"] = {"title": "x", "url": "https://learn.microsoft.com/x"}
    bad["practice_assessment"] = "http://insecure"
    problems = " | ".join(learn.validate(bad))
    assert "compute: missing" in problems and "must point at" in problems
    assert "bogus" in problems and "practice_assessment" in problems


def test_meta_tells_learners_how_much_of_the_bank_is_reviewed(client):
    content = client.get("/api/meta").json()["content"]
    assert content["questions"] == len(load_bank())
    assert content["reviewed"] == 0  # honest: nobody has signed these off yet
    assert content["skills_measured_as_of"] == "2026-07-20"
    assert content["study_guide_url"].startswith("https://learn.microsoft.com/")
    assert content["practice_assessment_url"].startswith("https://learn.microsoft.com/")


def test_answer_response_links_to_the_topic_module(client):
    q = next(iter(load_bank().values()))
    r = client.post("/api/answer", json={"learner": "learner-content-0001", "question_id": q.id, "choice": q.answer})
    assert r.json()["learn"] == learn.topic_link(q.topic)


def test_feedback_url_must_be_https(monkeypatch):
    from app.config import ConfigError, get_settings

    monkeypatch.setenv("FEEDBACK_URL", "http://insecure.example")
    with pytest.raises(ConfigError, match="FEEDBACK_URL"):
        get_settings()
    monkeypatch.setenv("FEEDBACK_URL", "https://github.com/me/repo/issues/new")
    assert get_settings().feedback_url.endswith("/issues/new")


# ---------------------------------------------------------------- review workflow

@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "review.json"
    path.write_text(json.dumps({
        "source_url": "https://learn.microsoft.com/x", "skills_measured_as_of": "2026-07-20",
        "questions": {qid: None for qid in load_bank()},
    }))
    monkeypatch.setattr("app.questions.REVIEW_FILE", path)
    monkeypatch.setattr("app.learn.REVIEW_FILE", path)
    return path


def test_mark_and_unmark_update_the_ledger_atomically(ledger):
    first, second = list(load_bank())[:2]
    review.set_review([first, second], date(2026, 10, 1))
    data = json.loads(ledger.read_text())
    assert data["questions"][first] == "2026-10-01" and data["questions"][second] == "2026-10-01"
    assert data["skills_measured_as_of"] == "2026-07-20"  # other keys survive
    assert not list(ledger.parent.glob(".review-*"))      # no temp files left behind
    review.set_review([first], None)
    assert json.loads(ledger.read_text())["questions"][first] is None
    assert learn.content_info(64)["reviewed"] == 1


def test_review_rejects_unknown_ids_and_future_dates(ledger):
    before = ledger.read_text()
    with pytest.raises(ValueError, match="unknown question"):
        review.set_review(["nope-99"], date(2026, 1, 1))
    with pytest.raises(ValueError, match="future"):
        review.set_review([next(iter(load_bank()))], date.today() + timedelta(days=2))
    assert ledger.read_text() == before


def test_review_cli(ledger, capsys):
    qid = next(iter(load_bank()))
    assert review.main(["status"]) == 0 and "Reviewed 0/64" in capsys.readouterr().out
    assert review.main(["show", qid]) == 0
    shown = capsys.readouterr().out
    assert "<-- correct" in shown and "learn.microsoft.com" in shown and "NOT YET" in shown
    assert review.main(["mark", qid, "--yes"]) == 0
    assert review.main(["list", "--reviewed"]) == 0 and qid in capsys.readouterr().out
    assert review.main(["list", "--unreviewed"]) == 0 and qid not in capsys.readouterr().out
    assert review.main(["mark", "nope", "--yes"]) == 2
    assert review.main(["unmark", qid]) == 0
    assert json.loads(ledger.read_text())["questions"][qid] is None


def test_mark_needs_confirmation(ledger, monkeypatch, capsys):
    qid = next(iter(load_bank()))
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert review.main(["mark", qid]) == 1
    assert json.loads(ledger.read_text())["questions"][qid] is None
