/* Service worker mínimo: hace la página instalable. No guarda nada en caché (los datos son siempre del servidor). */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
