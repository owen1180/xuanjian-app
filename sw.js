/* 玄鉴命理馆 · Service Worker
   策略：
   - 应用壳（html/css/js/manifest/图标）安装时预缓存，运行时 network-first 以便更新；
   - pyodide 运行时与 engine.zip 体积大且罕改：network-first（联网先取真文件，离线才回退缓存），
     且仅当响应为有效 JS/WASM/ZIP/JSON 时才写入缓存，杜绝把 GitHub Pages 的 HTML 错误页缓存成坏模块。 */
const CACHE = "xuanjian-v3";
const SHELL = [
  "./", "index.html", "styles.css", "app.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png",
  "icons/icon-maskable-512.png"
];

self.addEventListener("install", (e) => {
  // 单个图标缺失不应导致整个 SW 安装失败
  e.waitUntil(
    caches.open(CACHE).then((c) => Promise.allSettled(SHELL.map((u) => c.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) =>
      Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isCacheable(res) {
  if (!res || !res.ok) return false;
  const ct = res.headers.get("content-type") || "";
  return /javascript|wasm|zip|json/.test(ct);
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  // 大体积、罕更新：network-first，离线回退缓存（且只缓存合法类型）
  if (url.pathname.endsWith(".wasm") || url.pathname.endsWith("engine.zip") ||
      url.pathname.endsWith("python_stdlib.zip") || url.pathname.includes("/pyodide/")) {
    e.respondWith((async () => {
      const cache = await caches.open(CACHE);
      try {
        const res = await fetch(e.request);
        if (isCacheable(res)) cache.put(e.request, res.clone());
        return res;
      } catch (err) {
        const hit = await cache.match(e.request);
        if (hit) return hit;
        throw err;
      }
    })());
    return;
  }

  // 其余：network-first，失败回退缓存（含导航回退 index.html）
  e.respondWith(
    fetch(e.request).then((res) => {
      if (res && res.ok) caches.open(CACHE).then((c) => c.put(e.request, res.clone()));
      return res;
    }).catch(() => caches.match(e.request).then((r) => r || caches.match("index.html")))
  );
});
