/* Le service worker d'ALMA SOCIAL : l'écran s'ouvre même sans réseau, pour
 * qu'on puisse déposer des photos dans un sous-sol de chantier. Les photos
 * elles-mêmes attendent dans IndexedDB (attente.js), pas ici.
 * Monter VERSION à chaque changement d'un fichier de SHELL. */
const VERSION = "alma-social-5";
const SHELL = ["/", "/static/app.css?v=5",
               "/static/js/attente.js?v=5",
               "/static/js/socle.js?v=5",
               "/static/js/deposer.js?v=5",
               "/static/js/viseur.js?v=5",
               "/static/js/aujourdhui.js?v=5",
               "/static/js/calendrier.js?v=5",
               "/static/js/boite.js?v=5",
               "/static/js/resultats.js?v=5",
               "/static/js/demander.js?v=5",
               "/static/js/studio.js?v=5",
               "/static/js/marques.js?v=5",
               "/static/js/sante.js?v=5",
               "/static/js/reglages.js?v=5",
               "/static/js/demarrage.js?v=5",
               "/static/fonts/ArchivoBlack-Regular.ttf", "/static/fonts/DMSans.ttf",
               "/static/icone.svg", "/static/icone-192.png", "/manifest.webmanifest"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  // L'API, les aperçus, les médias : toujours le réseau, jamais une réponse périmée.
  if (u.pathname.startsWith("/api/") || u.pathname.startsWith("/apercu/") || u.pathname.startsWith("/m/")
      || u.pathname.startsWith("/go/") || u.pathname.startsWith("/logo/")) return;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r.ok && SHELL.includes(u.pathname + u.search)) caches.open(VERSION).then(c => c.put(e.request, r.clone()));
      return r;
    }).catch(() => caches.match(e.request).then(r => r || caches.match("/")))
  );
});
