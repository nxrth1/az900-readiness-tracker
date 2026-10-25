from starlette.requests import Request

from app.ratelimit import RateLimiter, client_ip

L = "learner-rate-0001"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_allows_up_to_the_limit_then_blocks_with_retry_after():
    clock = Clock()
    rl = RateLimiter(clock=clock)
    assert [rl.hit("a", 3)[0] for _ in range(3)] == [True, True, True]
    ok, retry = rl.hit("a", 3)
    assert ok is False and 0 < retry <= 60
    clock.t = 59.0
    assert rl.hit("a", 3)[0] is False
    clock.t = 60.5  # the first hit has left the window
    assert rl.hit("a", 3)[0] is True


def test_keys_are_independent():
    rl = RateLimiter(clock=Clock())
    assert rl.hit("a", 1)[0] and not rl.hit("a", 1)[0]
    assert rl.hit("b", 1)[0]


def test_memory_stays_bounded():
    clock = Clock()
    rl = RateLimiter(clock=clock, max_keys=100)
    for i in range(1000):
        clock.t += 0.001
        rl.hit(f"ip-{i}", 5)
    assert len(rl._hits) <= 100


def _request(headers: dict[str, str], host="10.0.0.9") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (host, 1234),
    })


def test_forwarded_header_is_ignored_unless_a_proxy_is_trusted():
    req = _request({"X-Forwarded-For": "1.2.3.4"})
    assert client_ip(req, 0) == "10.0.0.9"


def test_only_entries_added_by_our_proxy_are_trusted():
    spoofed = _request({"X-Forwarded-For": "6.6.6.6, 203.0.113.7"})  # client forged the first entry
    assert client_ip(spoofed, 1) == "203.0.113.7"
    two_proxies = _request({"X-Forwarded-For": "6.6.6.6, 203.0.113.7, 10.1.1.1"})
    assert client_ip(two_proxies, 2) == "203.0.113.7"
    assert client_ip(_request({}), 1) == "10.0.0.9"  # header missing: fall back to the socket peer


def test_api_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    codes = [client.get("/api/meta").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    r = client.get("/api/meta")
    assert int(r.headers["Retry-After"]) >= 1 and "slow down" in r.json()["detail"]
    assert client.get("/api/health").status_code == 200  # probes are never throttled
    assert client.get("/api/ready").status_code == 200


def test_each_client_gets_its_own_budget_behind_a_trusted_proxy(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "2")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")

    def hit(ip):
        return client.get("/api/meta", headers={"X-Forwarded-For": f"spoofed, {ip}"}).status_code

    assert [hit("198.51.100.1"), hit("198.51.100.1"), hit("198.51.100.1")] == [200, 200, 429]
    assert hit("198.51.100.2") == 200  # a different client is unaffected
    # rotating the forged left-most value does not buy extra requests
    assert client.get("/api/meta", headers={"X-Forwarded-For": "other-fake, 198.51.100.1"}).status_code == 429


def test_expensive_routes_have_tighter_budgets(client, monkeypatch):
    monkeypatch.setenv("HEAVY_RATE_LIMIT_PER_MIN", "2")
    assert [client.get(f"/api/learner/{L}/export").status_code for _ in range(3)] == [200, 200, 429]

    monkeypatch.setenv("EXPLAIN_RATE_LIMIT_PER_MIN", "1")
    from app.questions import load_bank

    q = next(iter(load_bank().values()))
    body = {"question_id": q.id, "choice": q.answer}
    assert client.post("/api/explain", json=body).status_code == 200
    assert client.post("/api/explain", json=body).status_code == 429


def test_limits_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "0")
    assert all(client.get("/api/meta").status_code == 200 for _ in range(30))
