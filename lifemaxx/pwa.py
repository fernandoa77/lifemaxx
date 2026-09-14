import json

from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import HttpResponse


def manifest(request):
    """Return the install manifest with static URLs resolved for this deployment."""
    payload = {
        "name": "LifeMaxx",
        "short_name": "LifeMaxx",
        "description": "Panel personal de rendimiento y bienestar.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0B1016",
        "theme_color": "#090B0F",
        "icons": [
            {
                "src": staticfiles_storage.url("icons/lifemaxx-icon-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": staticfiles_storage.url("icons/lifemaxx-icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
        ],
    }
    return HttpResponse(json.dumps(payload), content_type="application/manifest+json")


def service_worker(request):
    """Minimal worker to make the installed app available offline after a visit."""
    script = """const CACHE = 'lifemaxx-v1';
const APP_SHELL = ['/'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});"""
    return HttpResponse(script, content_type="application/javascript")
