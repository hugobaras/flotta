// Mode hors ligne du contrôle chauffeur : la page, la checklist et les fichiers de l'application
// restent disponibles sans réseau une fois visités. Les envois en attente sont gérés par la page.
const VERSION = "flotta-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((noms) => Promise.all(noms.filter((n) => n !== VERSION).map((n) => caches.delete(n)))).then(() => self.clients.claim()),
  );
});

const reseauPuisCache = async (req) => {
  const cache = await caches.open(VERSION);
  try {
    const rep = await fetch(req);
    if (rep.ok) cache.put(req, rep.clone());
    return rep;
  } catch {
    const enCache = await cache.match(req);
    if (enCache) return enCache;
    throw new Error("hors ligne");
  }
};

const cacheDabord = async (req) => {
  const cache = await caches.open(VERSION);
  const enCache = await cache.match(req);
  if (enCache) return enCache;
  const rep = await fetch(req);
  if (rep.ok) cache.put(req, rep.clone());
  return rep;
};

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (req.mode === "navigate" && (url.pathname.startsWith("/c/") || url.pathname.startsWith("/t/"))) e.respondWith(reseauPuisCache(req));
  else if (/^\/api\/(controle|tournee)\/[^/]+$/.test(url.pathname)) e.respondWith(reseauPuisCache(req));
  else if (url.pathname.startsWith("/_next/static/")) e.respondWith(cacheDabord(req));
});
