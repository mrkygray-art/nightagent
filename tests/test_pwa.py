"""Add to home screen: the manifest, icons, and service worker are served, and the pages link them."""

from app.pwa import ICONS


def test_manifest_opens_the_demo(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["start_url"] == "/demo" and m["display"] == "standalone"
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(i.get("purpose") == "maskable" for i in m["icons"])
    for i in m["icons"]:
        assert client.get(i["src"]).status_code == 200


def test_icons_are_served(client):
    for name in ICONS:
        r = client.get(f"/{name}")
        assert r.status_code == 200 and len(r.content) > 100
    assert client.get("/not-an-icon.png").status_code == 404


def test_service_worker_never_caches_api_or_calls(client):
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert r.headers["cache-control"] == "no-cache"
    assert "url.pathname.startsWith('/api/')" in r.text
    assert "req.method !== 'GET'" in r.text


def test_pages_link_the_manifest(client):
    for page in ("/demo", "/lab"):
        html = client.get(page).text
        assert '<link rel="manifest" href="/manifest.webmanifest">' in html
        assert 'navigator.serviceWorker.register("/sw.js")' in html
    assert 'id="install-btn"' in client.get("/demo").text


def test_other_routes_still_work(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200
