// Lekki Suites service worker (fix36 - PWA)
// Goal: the site opens like an app, and the basic pages still load on a weak network.
// The admin area is NEVER cached - reception must always see live data.

const CACHE = "lekkisuites-v1";

// Pages and assets we want available offline.
const SHELL = [
  "/",
  "/rooms",
  "/amenities",
  "/dining",
  "/contact",
  "/book",
  "/ticket",
  "/static/style.css?v=27",
  "/static/logo.png",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // addAll fails as a whole if one URL 404s, so add them one by one.
      Promise.all(
        SHELL.map((url) => cache.add(url).catch(() => null))
      )
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // Only plain page/asset loads. Never touch POSTs or the admin area.
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/admin")) return;

  // Page navigation: try the network first so guests always get fresh prices,
  // fall back to the cached copy when there is no signal.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() =>
          caches.match(req).then((hit) => hit || caches.match("/"))
        )
    );
    return;
  }

  // Static files: serve from cache first, they barely change.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((hit) => {
        if (hit) return hit;
        return fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
          return res;
        });
      })
    );
  }
});
