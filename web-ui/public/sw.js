self.addEventListener('install', (event) => {
  console.log('Service Worker installing...');
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  console.log('Service Worker activating...');
  clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Пока просто проксируем все запросы в сеть
  // Позже можно прикрутить кэширование для оффлайна
});
