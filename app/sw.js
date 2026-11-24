// "__BUILD__" is replaced by app/build.py with a hash of the build, so each deploy gets its own cache
// and old caches are deleted on activate. index.html and lots.json are network-first (fresh when online,
// cached when offline); icons and the manifest are cache-first.
const PREFIX = 'arts-finder-';
const SHELL = PREFIX + '__BUILD__';
const FILES = ['./', './index.html', './manifest.webmanifest', './icon.svg', './icon-180.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith(PREFIX) && k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
const networkFirst = async req => {
  const cache = await caches.open(SHELL);
  try { const res = await fetch(req); if (res.ok) cache.put(req, res.clone()); return res; }
  catch (_) { const hit = await cache.match(req); if (hit) return hit; throw _; }
};
const cacheFirst = async req => (await caches.match(req)) || fetch(req);
const isFresh = url => /(^|\/)(index\.html|lots\.json)?$/.test(new URL(url).pathname);  // the page itself and the data
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(req.mode === 'navigate' || isFresh(req.url) ? networkFirst(req) : cacheFirst(req));
});
