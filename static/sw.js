/* 班级教学管理平台 - Service Worker
 * 策略：
 *   - 静态资源（CDN / static）：Cache First + 后台更新
 *   - HTML 页面：Network First（离线时回退缓存）
 */
const CACHE_NAME = 'class-manager-v1';
const CDN_ASSETS = [
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js',
  'https://cdn.jsdelivr.net/npm/htmx.org@1.9.10/dist/htmx.min.js',
];
const LOCAL_STATIC = [
  '/static/css/style.css',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(LOCAL_STATIC))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// 后台预缓存 CDN 资源（不阻塞 install）
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'PRECACHE_CDN') {
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CDN_ASSETS));
  }
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // 仅处理同源请求和已知 CDN，跨站图片等交给浏览器
  const isCdn = CDN_ASSETS.includes(url.href) || CDN_ASSETS.includes(request.url);
  if (url.origin !== location.origin && !isCdn) return;

  // 静态资源：Cache First
  if (isCdn || url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const fetchPromise = fetch(request).then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        });
        return cached || fetchPromise;
      })
    );
    return;
  }

  // HTML 页面：Network First
  if (request.mode === 'navigate' || url.pathname.endsWith('/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/')))
    );
  }
});
