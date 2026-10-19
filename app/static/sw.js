// Service worker mínimo: permite instalar EDI como app en el celular. No guarda caché (EDI necesita el servidor).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
