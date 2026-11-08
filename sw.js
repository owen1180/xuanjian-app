/* 玄鉴命理馆 · Service Worker
   策略：
   - 应用壳（html/css/js/manifest/图标）安装时预缓存，运行时 network-first 以便更新；
   - pyodide 运行时与 engine.zip 体积大且罕改，运行时 cache-first 缓存，首次联网下载后永久离线可用。 */
const CACHE = "xuanjian-v1";
const SHELL = [
  "./", "index.html", "styles.css", "app.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png",
  "icons/icon-maskable-512.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // 大体积、罕更新：cache-first
  if (url.pathname.endsWith(".wasm") || url.pathname.endsWith("engine.zip") ||
      url.pathname.endsWith("python_stdlib.zip") || url.pathname.includes("/pyodide/")) {
    e.respondWith(
      caches.open(CACHE).then(async (c) => {
        const hit = await c.match(e.request);
        if (hit) return hit;
        const res = await fetch(e.request);
        if (res && res.ok) c.put(e.request, res.clone());
        return res;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  // 其余：network-first，失败回退缓存（含导航回退 index.html）
  e.respondWith(
    fetch(e.request).then((res) => {
      const c = caches.open(CACHE);
      if (res && res.ok) c.then((cc) => cc.put(e.request, res.clone()));
      return res;
    }).catch(() => caches.match(e.request).then((r) => r || caches.match("index.html")))
  );
});
