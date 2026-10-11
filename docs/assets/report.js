/* AMS 解析網頁 — 前端錯誤回報（未捕捉錯誤、未處理的 Promise 拒絕、資源載入失敗、資料檔載入失敗）
 *
 * 送到備品庫存 Worker 的 action=clientlog（tools/stock/worker：寫 D1 表 client_log；本機 mock_server 記到 mock_log.jsonl）。
 * 端點：<meta name="ams-report" content="…/stock-config.json">，沒有就用 <meta name="ams-stock-config">（db 站）；兩者都沒有＝不回報。
 * 規則：只在已登入（AMSAuth.user.token）時送（Worker 只驗登入 token，不需要密語）；每次載入最多 8 筆、同一訊息不重送；
 *       跨網域腳本的 "Script error." 略過；回報本身失敗一律吞掉，絕不影響頁面。core.js 的 D.fetchJSON 失敗會呼叫 AMSReport.send('load', …)。
 * 查看：npx wrangler d1 execute ams-stock --remote --command "SELECT ts, emp_id, kind, msg, page, build FROM client_log ORDER BY id DESC LIMIT 50" */
'use strict';
(function () {
  const MAX = 8;
  const seen = new Set();
  let n = 0;
  let cfgP = null;
  const R = (window.AMSReport = { send: send, count: () => n });

  function endpoint() {
    if (cfgP) return cfgP;
    const m = document.querySelector('meta[name="ams-report"]') || document.querySelector('meta[name="ams-stock-config"]');
    const url = m && m.getAttribute('content');
    cfgP = url
      ? fetch(url, { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).then((j) => (j && /^https?:\/\//.test(String(j.endpoint || '')) ? String(j.endpoint) : null)).catch(() => null)
      : Promise.resolve(null);
    return cfgP;
  }
  function meta(name, attr) { const m = document.querySelector('meta[name="' + name + '"]'); return m ? (m.getAttribute(attr || 'content') || '') : ''; }

  async function send(kind, msg, extra) {
    try {
      msg = String(msg == null ? '' : msg).slice(0, 500);
      if (!msg) return;
      const key = kind + '|' + msg;
      if (seen.has(key) || n >= MAX) return;
      seen.add(key); n++;
      const u = window.AMSAuth && window.AMSAuth.user;
      if (!u || !u.token) return;
      const ep = await endpoint();
      if (!ep) return;
      const body = JSON.stringify({
        action: 'clientlog', id: u.id, token: u.token, name: u.name,
        kind: String(kind || 'error').slice(0, 20), msg,
        stack: String((extra && extra.stack) || '').slice(0, 2000),
        path: String((extra && extra.path) || '').slice(0, 200),
        page: location.hash.slice(0, 200),
        site: (meta('ams-auth-config', 'data-site') || document.title).slice(0, 60),
        build: meta('ams-build').slice(0, 20), app: meta('ams-build', 'data-app').slice(0, 20),
        ua: navigator.userAgent.slice(0, 200),
      });
      await fetch(ep, { method: 'POST', mode: 'cors', keepalive: true, headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body });
    } catch (e) { /* 回報本身絕不能再拋錯 */ }
  }

  // capture=true：<script>／<link>／<img> 載入失敗的 error 事件不冒泡，只有在捕獲階段才收得到
  window.addEventListener('error', (e) => {
    try {
      const t = e && e.target;
      if (t && t !== window && t.tagName) {
        const src = t.getAttribute && (t.getAttribute('src') || t.getAttribute('href'));
        if (src) send('resource', t.tagName.toLowerCase() + ' 載入失敗：' + String(src).slice(0, 200));
        return;
      }
      const msg = (e && e.message) || (e && e.error && String(e.error)) || '';
      if (!msg || /^Script error\.?$/.test(msg)) return;
      const where = e.filename ? ' @' + String(e.filename).replace(/^.*\/assets\//, 'assets/') + ':' + (e.lineno || 0) : '';
      send('error', msg + where, { stack: e.error && e.error.stack });
    } catch (err) { /* ignore */ }
  }, true);
  window.addEventListener('unhandledrejection', (e) => {
    try {
      const r = e && e.reason;
      send('unhandledrejection', (r && r.message) || String(r), { stack: r && r.stack });
    } catch (err) { /* ignore */ }
  });
  R.ready = true;
})();
