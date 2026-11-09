/* Service Worker: guarda la "cáscara" de la app para que abra SIN conexión.
 * Los datos (programación, cola, fotos) viven en IndexedDB, no aquí. */
const CACHE = "sgml-v12";
const CASCARA = [
  "./", "index.html", "login.html", "backoffice.html", "dashboard.html",
  "supervisor.html", "programacion.html", "app.js", "js/auth.js", "js/auth-session.js", "js/admin.js",
  "js/api.js", "js/dashboard.js", "js/supervisor.js", "js/programacion.js",
  "manifest.webmanifest", "icono.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CASCARA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((claves) => Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET" || new URL(e.request.url).pathname.startsWith("/api/")) return;
  // Red primero (para recibir actualizaciones) y caché si no hay conexión.
  e.respondWith(fetch(e.request)
    .then((r) => { const copia = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copia)); return r; })
    .catch(() => caches.match(e.request, { ignoreSearch: true })));
});
