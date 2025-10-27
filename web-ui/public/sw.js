const CACHE_VERSION = 'igorek-cache-v1';
const CACHE_NAME = CACHE_VERSION;
const MAX_CACHE_AGE_MS = 7 * 24 * 60 * 60 * 1000; // 7 дней

const PRECACHE_URLS = [
  '/',
  '/web-ui/',
  '/web-ui/index.html',
  '/web-ui/manifest.json',
  '/favicon.ico',
  '/web-ui/icon-192.png',
  '/web-ui/icon-512.png',
];

const STATIC_PATH_PREFIXES = [
  '/web-ui/assets/',
  '/web-ui/img/',
  '/web-ui/fonts/',
  '/assets/',
  '/img/',
  '/fonts/',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .catch((error) => {
        console.warn('[SW] Pre-cache failed:', error);
      }),
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
          return undefined;
        }),
      ),
    ),
  );
  clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (shouldBypass(url)) {
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(handleNavigation(request));
    return;
  }

  if (isStaticAsset(url, request)) {
    event.respondWith(cacheFirst(request));
    return;
  }
});

function shouldBypass(url) {
  const path = url.pathname;
  return (
    path.startsWith('/api/') ||
    (path.startsWith('/image/') && !path.startsWith('/web-ui/')) ||
    path.startsWith('/chat') ||
    path.startsWith('/uploads/') ||
    path.startsWith('/openapi')
  );
}

function isStaticAsset(url, request) {
  if (STATIC_PATH_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) {
    return true;
  }
  return ['style', 'script', 'image', 'font'].includes(request.destination);
}

async function handleNavigation(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request);
    const cachedResponse = await withCacheTimestamp(response.clone());
    await cache.put(request, cachedResponse);
    return response;
  } catch (error) {
    const fallback =
      (await cache.match(request)) ||
      (await cache.match('/web-ui/index.html')) ||
      (await cache.match('/web-ui/')) ||
      (await cache.match('/'));
    if (fallback) {
      return fallback;
    }
    throw error;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  if (cached) {
    const timestamp = Number(cached.headers.get('sw-cache-timestamp'));
    if (Number.isFinite(timestamp) && Date.now() - timestamp <= MAX_CACHE_AGE_MS) {
      return cached;
    }
  }

  try {
    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.ok) {
      const cachedResponse = await withCacheTimestamp(networkResponse.clone());
      await cache.put(request, cachedResponse);
    }
    return networkResponse;
  } catch (error) {
    if (cached) {
      return cached;
    }
    throw error;
  }
}

async function withCacheTimestamp(response) {
  const headers = new Headers(response.headers);
  headers.set('sw-cache-timestamp', Date.now().toString());
  const body = await response.blob();
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
