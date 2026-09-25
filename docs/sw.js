/* AMS 靜態站 Service Worker（docs/sw.js；由 assets/app.js 註冊，範圍＝本目錄，主站與 db/ 共用一個）
 *
 * 規則（只處理同源 GET；跨網域的 Apps Script／Worker／Google 雲端硬碟一律不碰）：
 *  - 網址帶 ?v=（資料 .bin、meta.json、assets 程式）→ 快取優先：內容雜湊或建置雜湊已在網址裡，命中就不必再問伺服器
 *    （GitHub Pages 只給 max-age=600，沒有 Service Worker 時每 10 分鐘都要重新驗證每個檔）
 *  - version.json／auth-config.json／stock-config.json → 只走網路（版本偵測與端點設定不能拿舊的）
 *  - 其餘（index.html、無版本值的檔）→ 網路優先，失敗才用快取（廠區網路斷線時仍能開站、查已看過的設備）
 * 頁面載入完成後 app.js 會 postMessage {type:'keep', dir, v:[...]}：列出該站目前用到的所有版本值，
 * 本站 data/ 與共用 assets/ 底下不在清單內的舊版本快取即刪除（另一個站的 data/ 不動）。 */
'use strict';
const CACHE = 'ams-static-v1';
const NET_ONLY = /\/(version|auth-config|stock-config)\.json$/;

self.addEventListener('install', () => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(self.clients.claim()); });

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (err) { return; }
  if (url.origin !== self.location.origin) return;
  if (NET_ONLY.test(url.pathname)) return;
  if (url.searchParams.has('v')) { e.respondWith(cacheFirst(req)); return; }
  e.respondWith(networkFirst(req));
});

async function cacheFirst(req) {
  const c = await caches.open(CACHE);
  const hit = await c.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res && res.ok) c.put(req, res.clone()).catch(() => {});
  return res;
}

async function networkFirst(req) {
  const c = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res && res.ok) c.put(req, res.clone()).catch(() => {});
    return res;
  } catch (err) {
    const hit = await c.match(req);
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener('message', (e) => {
  const m = e.data || {};
  if (m.type !== 'keep' || !Array.isArray(m.v) || typeof m.dir !== 'string') return;
  const keep = new Set(m.v.map(String));
  const dir = m.dir; // 例：/AMS/db/ 或 /AMS/
  const assets = dir.replace(/[^/]+\/$/, '').replace(/db\/$/, '') + 'assets/';
  e.waitUntil((async () => {
    const c = await caches.open(CACHE);
    for (const req of await c.keys()) {
      let u; try { u = new URL(req.url); } catch (err) { continue; }
      const v = u.searchParams.get('v');
      if (!v || keep.has(v)) continue;
      const p = u.pathname;
      if (p.startsWith(dir + 'data/') || p.startsWith(assets)) await c.delete(req);
    }
  })());
});
