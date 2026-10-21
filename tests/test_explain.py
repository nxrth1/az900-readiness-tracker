"""The Claude call is exercised with a stub client, so no network or API key is needed."""
import sys
import types

import pytest

from app import db, explain as explain_mod
from app.questions import load_bank


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


def install_fake_anthropic(monkeypatch, reply="Think of it like an M-Pesa agent.", boom=False):
    calls = []

    class Messages:
        def create(self, **kw):
            calls.append(kw)
            if boom:
                raise RuntimeError("rate limited")
            return _Resp(reply)

    class Anthropic:
        def __init__(self, **kw):
            self.kw = kw
            self.messages = Messages()

    mod = types.ModuleType("anthropic")
    mod.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    return calls


@pytest.fixture()
def q(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "x.db"))
    db.init_db()
    return next(iter(load_bank().values()))


def test_claude_path_sends_ground_truth_and_caches(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls = install_fake_anthropic(monkeypatch)
    wrong = (q.answer + 1) % 4

    first = explain_mod.explain(q, wrong, "simple", "en")
    assert first == {"text": "Think of it like an M-Pesa agent.", "source": "claude"}
    assert len(calls) == 1
    sent = calls[0]
    assert sent["model"] == explain_mod.MODEL
    assert sent["system"] == explain_mod.SYSTEM_PROMPT
    assert q.why in sent["messages"][0]["content"]
    assert sent["max_tokens"] <= 500

    second = explain_mod.explain(q, wrong, "simple", "en")
    assert second["source"] == "cache" and len(calls) == 1  # no second API call

    explain_mod.explain(q, wrong, "simple", "sw")  # different language is a different cache entry
    assert len(calls) == 2


def test_api_failure_falls_back_to_builtin(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    install_fake_anthropic(monkeypatch, boom=True)
    r = explain_mod.explain(q, q.answer, "simple", "en")
    assert r == {"text": q.why, "source": "builtin"}


def test_empty_model_output_falls_back(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    install_fake_anthropic(monkeypatch, reply="   ")
    assert explain_mod.explain(q, q.answer)["source"] == "builtin"
