// Offline en snel: de app zelf en de kaartdata uit de cache, prijzen worden ververst zodra er verbinding is,
// kaartscans blijven bewaard zodra ze een keer geladen zijn.
const SHELL = "kp-shell-v1", DATA = "kp-data-v1", IMG = "kp-img-v1";
self.addEventListener("install", e => { e.waitUntil(caches.open(SHELL).then(c => c.addAll(["/", "/kp-shim.js", "/manifest.webmanifest"])).catch(() => {})); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  if (url.pathname.startsWith("/img/")) {
    e.respondWith(caches.open(IMG).then(async c => { const hit = await c.match(e.request); if (hit) return hit; const r = await fetch(e.request); if (r.ok) c.put(e.request, r.clone()); return r; }));
    return;
  }
  const cacheName = /\.(json)$/.test(url.pathname) ? DATA : SHELL;
  e.respondWith(fetch(e.request).then(r => { if (r.ok && !r.redirected) caches.open(cacheName).then(c => c.put(e.request, r.clone())); return r; })
    .catch(() => caches.match(e.request).then(hit => hit || Response.error())));
});
