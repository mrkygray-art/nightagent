"""Lets phones add NightAgent to the home screen as an app (Chrome, Firefox, DuckDuckGo, Safari).

Serves the web app manifest, the icons in app/static/, and a small service worker. Calls,
tickets, and every /api/ request always go to the network; the worker only keeps a copy of
the pages and icons so the app opens (with a "no signal" note) when the phone is offline.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response

router = APIRouter()

STATIC = Path(__file__).parent / "static"
ICONS = {"icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png", "icon.svg"}

# Bump when sw.js or the icons change, so installed phones pick up the new copy.
VERSION = "1"

MANIFEST = {
    "name": "NightAgent",
    "short_name": "NightAgent",
    "description": "Call Sam, the after-hours AI voice agent, and follow your service ticket.",
    "id": "/demo",
    "start_url": "/demo",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#101a2e",
    "theme_color": "#101a2e",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
}

SW_JS = r"""// NightAgent service worker: lets the app open from the home screen. Calls, tickets, and
// every /api/ request always go straight to the network; only the pages and icons are kept.
const CACHE = 'nightagent-__VERSION__';
const PAGES = ['/demo', '/lab'];
const KEEP = [...PAGES, '/icon-192.png', '/icon-512.png', '/icon.svg'];

const timeout = (ms) => new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), ms));

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(KEEP.map((u) => new Request(u, { cache: 'reload' })))));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((n) => n.startsWith('nightagent-') && n !== CACHE).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return; // network only

  // Opening a page: always try the network first (8s max, for weak signal), else the saved copy
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await Promise.race([fetch(req), timeout(8000)]);
        if (fresh.ok && PAGES.includes(url.pathname)) (await caches.open(CACHE)).put(url.pathname, fresh.clone());
        return fresh;
      } catch {
        const saved = await caches.match(PAGES.includes(url.pathname) ? url.pathname : '/demo');
        return saved || Response.error();
      }
    })());
    return;
  }

  // Icons: use the saved copy, else the network
  if (KEEP.includes(url.pathname)) {
    event.respondWith(caches.match(url.pathname).then((hit) => hit || fetch(req)));
  }
});
""".replace("__VERSION__", VERSION)


@router.get("/manifest.webmanifest")
def manifest() -> JSONResponse:
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@router.get("/sw.js")
def service_worker() -> Response:
    # no-cache so a new version reaches phones on their next visit
    return Response(SW_JS, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


def _icon_route(name: str) -> None:
    @router.get(f"/{name}", include_in_schema=False)
    def icon() -> FileResponse:
        return FileResponse(STATIC / name, headers={"Cache-Control": "public, max-age=86400"})


for _name in ICONS:
    _icon_route(_name)
