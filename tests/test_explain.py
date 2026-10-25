"""The Claude call is exercised with a stub client, so no network or API key is needed."""
import sys
import threading
import time as _time
import types

import pytest

from app import db
from app import explain as explain_mod
from app.explain import CircuitBreaker
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


# ---------------------------------------------------------------- resilience


def test_model_name_follows_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
    assert explain_mod.MODEL == "claude-test-model"


def test_circuit_opens_after_repeated_failures_and_stops_calling_the_api(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("EXPLAIN_BREAKER_THRESHOLD", "3")
    calls = install_fake_anthropic(monkeypatch, boom=True)
    for _ in range(3):
        assert explain_mod.explain(q, q.answer)["source"] == "builtin"
    assert len(calls) == 3 and explain_mod.breaker.is_open
    for _ in range(5):  # the outage no longer costs a timeout per request
        assert explain_mod.explain(q, q.answer)["source"] == "builtin"
    assert len(calls) == 3


def test_circuit_breaker_half_open_probe_and_recovery():
    now = [0.0]
    cb = CircuitBreaker(clock=lambda: now[0])
    assert cb.allow(60)
    cb.failure(2)
    assert cb.allow(60) and not cb.is_open  # one failure is below the threshold
    cb.failure(2)
    assert cb.is_open and not cb.allow(60)
    now[0] = 61.0
    assert cb.allow(60) is True      # cooldown over: exactly one probe is let through
    assert cb.allow(60) is False
    cb.failure(2)                    # probe failed: stay open for another cooldown
    assert not cb.allow(60)
    now[0] = 130.0
    assert cb.allow(60) is True
    cb.success()                     # probe worked: closed again
    assert not cb.is_open and cb.allow(60) and cb.allow(60)


def test_a_success_resets_the_failure_streak(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("EXPLAIN_BREAKER_THRESHOLD", "2")
    install_fake_anthropic(monkeypatch, boom=True)
    explain_mod.explain(q, q.answer)
    install_fake_anthropic(monkeypatch)            # recovers
    assert explain_mod.explain(q, q.answer, "exam-tip")["source"] == "claude"
    install_fake_anthropic(monkeypatch, boom=True)
    explain_mod.explain(q, q.answer)
    assert not explain_mod.breaker.is_open        # streak was reset, so one new failure is not enough


def test_identical_concurrent_requests_make_one_live_call(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls = install_fake_anthropic(monkeypatch)
    slow = sys.modules["anthropic"].Anthropic

    class SlowMessages:
        def create(self, **kw):
            calls.append(kw)
            _time.sleep(0.3)
            return _Resp("slow answer")

    slow.__init__ = lambda self, **kw: setattr(self, "messages", SlowMessages())
    results: list[str] = []
    threads = [threading.Thread(target=lambda: results.append(explain_mod.explain(q, q.answer)["source"])) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert sorted(results) == ["cache"] * 5 + ["claude"]


def test_excess_concurrency_is_shed_to_the_builtin_text(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("EXPLAIN_MAX_CONCURRENT", "1")
    monkeypatch.setattr(explain_mod, "SEMAPHORE_WAIT_S", 0.05)
    started, release = threading.Event(), threading.Event()
    install_fake_anthropic(monkeypatch)

    class BlockingMessages:
        def create(self, **kw):
            started.set()
            release.wait(5)
            return _Resp("late answer")

    sys.modules["anthropic"].Anthropic.__init__ = lambda self, **kw: setattr(self, "messages", BlockingMessages())
    holder = threading.Thread(target=lambda: explain_mod.explain(q, q.answer, "simple", "en"))
    holder.start()
    assert started.wait(2)
    try:
        shed = explain_mod.explain(q, q.answer, "exam-tip", "en")  # different key, so it is not coalesced
        assert shed["source"] == "builtin"
    finally:
        release.set()
        holder.join()


def test_daily_cap_stops_live_calls_but_cache_keeps_working(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("EXPLAIN_DAILY_CAP", "1")
    calls = install_fake_anthropic(monkeypatch)
    assert explain_mod.explain(q, q.answer, "simple")["source"] == "claude"
    assert explain_mod.explain(q, q.answer, "exam-tip")["source"] == "builtin"  # over budget
    assert len(calls) == 1
    assert explain_mod.explain(q, q.answer, "simple")["source"] == "cache"     # cached answers are free


def test_a_cache_write_failure_does_not_lose_a_good_answer(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    install_fake_anthropic(monkeypatch)
    monkeypatch.setattr(db, "cache_explanation", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    assert explain_mod.explain(q, q.answer)["source"] == "claude"
    assert not explain_mod.breaker.is_open  # a storage problem is not an API outage


def test_the_api_client_is_reused_between_requests(q, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    install_fake_anthropic(monkeypatch)
    made = []
    cls = sys.modules["anthropic"].Anthropic
    original = cls.__init__
    cls.__init__ = lambda self, **kw: (made.append(kw), original(self, **kw))[1]
    explain_mod.explain(q, q.answer, "simple")
    explain_mod.explain(q, q.answer, "exam-tip")
    assert len(made) == 1 and made[0]["api_key"] == "test-key" and made[0]["timeout"] > 0
