import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_manifest_is_installable(client):
    r = client.get("/static/manifest.webmanifest")
    assert r.status_code == 200 and "json" in r.headers["content-type"]
    m = r.json()
    assert m["display"] == "standalone" and m["start_url"] == "/" and m["name"] and m["short_name"]
    sizes = {(i["sizes"], i["purpose"]) for i in m["icons"]}
    assert ("192x192", "any") in sizes and ("512x512", "any") in sizes and ("512x512", "maskable") in sizes
    for icon in m["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_index_links_the_manifest_icons_and_privacy_page(client):
    html = client.get("/").text
    for needle in ('rel="manifest"', 'rel="apple-touch-icon"', 'name="theme-color"', 'href="/privacy"', "/static/pwa.js"):
        assert needle in html


def test_service_worker_is_served_from_root_and_never_cached(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.headers["Cache-Control"] == "no-cache" and r.headers["Service-Worker-Allowed"] == "/"


def test_service_worker_never_touches_the_api():
    sw = (STATIC / "sw.js").read_text()
    assert "startsWith('/api/')" in sw and "return; // always live" in sw
    assert "cache.put(request" in sw and "url.pathname.startsWith('/static/')" in sw  # only static files are stored


def test_service_worker_precache_matches_the_assets_index_actually_loads():
    """If someone bumps ?v= in index.html but forgets sw.js, offline loads would silently break."""
    html = (STATIC / "index.html").read_text()
    sw = (STATIC / "sw.js").read_text()
    shell = set(re.findall(r"'(/[^']*)'", sw.split("const SHELL = [")[1].split("];")[0]))
    loaded = set(re.findall(r'(?:href|src)="(/static/[^"]+\?v=\d+)"', html))
    assert loaded and loaded <= shell, f"precache is missing {loaded - shell}"
    version = re.search(r"const VERSION = 'az900-v(\d+)'", sw).group(1)
    assert all(url.endswith(f"?v={version}") for url in loaded)
    for path in shell:
        if path not in ("/", "/privacy"):
            assert (STATIC / path.removeprefix("/static/").split("?")[0]).exists(), path


def test_privacy_page(client):
    r = client.get("/privacy")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "no third-party analytics" in r.text.lower() and "{{CONTACT}}" not in r.text
    assert "the operator of this site" in r.text


def test_privacy_page_shows_the_configured_contact_safely(client, monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", 'help@example.com"><script>alert(1)</script>')
    body = client.get("/privacy").text
    assert "<script>alert(1)" not in body and "help@example.com" in body


def test_privacy_page_is_consistent_with_what_the_code_stores(client):
    """The page claims there are no cookies and that queries are not logged: keep those promises true."""
    r = client.get("/api/meta")
    assert "set-cookie" not in r.headers
    assert not re.search(r"document\.cookie", (STATIC / "app.js").read_text())
    assert json.loads((STATIC / "manifest.webmanifest").read_text())["scope"] == "/"
