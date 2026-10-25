/* Service worker: makes the app installable and its shell load instantly, even on a flaky connection.
 *
 * What it does NOT do: cache anything from /api. Questions, answers and readiness always come from the
 * server (answers are never shipped to the browser in advance), so practice needs a connection. Offline,
 * the shell opens and the app explains that it cannot reach the server; nothing is lost.
 *
 * Bump VERSION whenever the ?v= on the assets in index.html changes (a test enforces that they match).
 */
const VERSION = 'az900-v9';
const SHELL = [
  '/',
  '/privacy',
  '/static/styles.css?v=9',
  '/static/app.js?v=9',
  '/static/pwa.js?v=9',
  '/static/manifest.webmanifest',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/sw.js') return; // always live

  if (request.mode === 'navigate') {
    // Pages: network first so updates arrive immediately; the cached copy is only the offline fallback.
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) { const copy = response.clone(); caches.open(VERSION).then((cache) => cache.put(request, copy)); }
          return response;
        })
        .catch(() => caches.match(request).then((hit) => hit || caches.match('/'))),
    );
    return;
  }

  // Versioned static assets (?v=N) never change for a given URL, so the cache is authoritative.
  event.respondWith(
    caches.match(request).then((hit) => hit || fetch(request).then((response) => {
      if (response.ok && url.pathname.startsWith('/static/')) {
        const copy = response.clone();
        caches.open(VERSION).then((cache) => cache.put(request, copy));
      }
      return response;
    })),
  );
});
