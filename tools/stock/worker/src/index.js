/**
 * AMS 備品庫存 API — Cloudflare Worker + D1（與 tools/stock/Code.gs 同一套請求／回應格式，前端 docs/assets/stock.js 不分後端）
 *
 * 請求：POST /（Content-Type text/plain，JSON {action, id, token, name, stockToken, ...}）；GET / 健康檢查；一律回 JSON {ok, ...}
 *   list                          → {ok, rev, lowCount, items:[{pn, model, brand, spec, loc, qty, proto, family, contract, cqty, min, note}]}
 *                                   lowCount＝qty ≤ min_qty 的料號數（min_qty NULL 不算）
 *   logs  {pn?, kks?, limit?, since?, until?, before?} → {ok, rows:[{ts, id, name, action, pn, delta, bal, kks, note, wo, source, txn, rid}]}
 *                                   since／until＝ISO UTC 字串（ts >= since、ts < until）；before＝ledger id 游標（只回 id < before）；單次最多 300 列，rid 給前端當下一頁游標
 *   txn   {txnId, items:[{pn, delta}], kks?, note?, wo?, source?} → {ok, results:[{pn, qty, delta, min, low}], replay?}
 *                                   low＝寫入後 qty ≤ min_qty；庫存不足（含別人剛領走）→ {ok:false, stale:true, error, items:[{pn, qty}]} 讓前端就地更新數量
 *   clientlog {kind, msg, stack?, path?, page?, site?, build?, app?, ua?} → {ok, dropped?}   前端錯誤回報（docs/assets/report.js）；只驗登入 token、不需 stockToken；寫 client_log
 *                                   每人每分鐘最多 10 筆，超過回 {ok:true, dropped:true} 不寫
 *   （盤點 adjust 已移除：數量調整用 wrangler d1 execute 同時 UPDATE items ＋ INSERT ledger STOCKTAKE，見 tools/stock/README.md）
 * 驗證：stockToken === env.STOCK_TOKEN（站台密語導出）＋ AMS 登入 token（HMAC-SHA256，密鑰 env.AUTH_SECRET，與登入閘門相同）
 *   ＋ D1 表 revoked 沒有該員工代號（停權：INSERT INTO revoked 即時生效，clientlog 也擋）
 *   失敗 → {ok:false, auth:true, error}；伺服器錯誤 → {ok:false, transient:true, error}（固定文案，原文只進 console）
 * 限速：wrangler.toml 的 ratelimit binding env.RL（每 IP 每分鐘 60 次 POST；沒有 binding 就不限），超限回 HTTP 429 {ok:false, transient:true}
 * 資料：D1 表 items / ledger / txns / client_log / revoked（schema.sql）。txn 用 DB.batch（單一交易）：INSERT txns（重送＝主鍵衝突→回上次結果）、
 *   UPDATE items qty（CHECK(qty>=0) 兜底）、INSERT ledger（balance 由 items 現值帶出）。
 * CORS：只對 env.ALLOWED_ORIGINS（逗號分隔）回 Access-Control-Allow-Origin。
 */
const TZ = 'Asia/Taipei';
const MAX_LOG_ROWS = 300;
const CLIENTLOG_PER_MIN = 10;   // clientlog 每人每分鐘上限（超過丟棄）
const LEDGER_COLS = 'ts, emp_id, emp_name, action, pn, delta, balance, kks, note, wo, source, txn_id';

export default {
  async fetch(req, env) {
    const cors = corsHeaders(req.headers.get('Origin') || '', env);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: { ...cors, 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '86400' } });
    if (req.method === 'GET') return json({ ok: true, service: 'ams-stock', backend: 'd1' }, cors);
    if (req.method !== 'POST') return json({ ok: false, error: 'method not allowed' }, cors, 405);
    // 每 IP 限速（Cloudflare Rate Limiting binding；本機 wrangler dev 沒有 env.RL 時不限）：所有 POST 一律先算，未登入的垃圾流量也算
    if (env.RL && env.RL.limit) {
      const ip = req.headers.get('cf-connecting-ip') || req.headers.get('x-forwarded-for') || 'unknown';
      let limited = false;
      try { limited = !((await env.RL.limit({ key: ip })) || {}).success; } catch (e) { console.error('ratelimit', e); }
      if (limited) return json({ ok: false, transient: true, error: '請求太頻繁，請一分鐘後再試' }, { ...cors, 'Retry-After': '60' }, 429);
    }
    let body = {};
    try { body = JSON.parse(await req.text() || '{}'); } catch (e) { return json({ ok: false, error: '請求格式錯誤' }, cors); }
    const action = String(body.action || '');
    try {
      if (action === 'clientlog') return json(await clientlog(body, env), cors);
      const who = await auth(body, env);
      if (!who.ok) return json({ ok: false, auth: true, error: who.error }, cors);
      if (action === 'list') return json(await list(env), cors);
      if (action === 'logs') return json(await logs(body, env), cors);
      if (action === 'txn') return json(await txn(body, who, env), cors);
      return json({ ok: false, error: '未知的動作' }, cors);
    } catch (e) {
      console.error(action, e); // D1 原文（表結構、SQL）只留在 Worker 紀錄，不回給使用者
      return json({ ok: false, transient: true, error: '伺服器暫時無法服務，請稍後再試' }, cors);
    }
  },
};

/* ---------------- 驗證 ---------------- */
async function auth(body, env) {
  const st = String(body.stockToken || '');
  if (!env.STOCK_TOKEN || !env.AUTH_SECRET) return { ok: false, error: '站台設定不完整（STOCK_TOKEN／AUTH_SECRET 未設定）' };
  if (!st || !safeEq(st, env.STOCK_TOKEN)) return { ok: false, error: '未授權（密語不符）' };
  const id = canon(body.id);
  const v = await verify(id, String(body.token || ''), env.AUTH_SECRET);
  if (!v.ok) return { ok: false, error: v.error };
  if (await isRevoked(id, env)) return { ok: false, error: REVOKED_MSG };
  return { ok: true, id, name: clip(norm(body.name), 40) || id };
}
const REVOKED_MSG = '此員工代號已停用，請洽管理者。';
/** 停權黑名單（schema.sql revoked；npx wrangler d1 execute ams-stock --remote --command "INSERT OR IGNORE INTO revoked VALUES ('代號', datetime('now'))"） */
async function isRevoked(id, env) {
  if (!id) return false;
  const r = await env.DB.prepare('SELECT 1 AS x FROM revoked WHERE emp_id = ?1').bind(id).first();
  return !!r;
}
async function hmac(msg, secret) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(msg)));
  let s = ''; for (const c of sig) s += String.fromCharCode(c);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
async function verify(id, token, secret) {
  const m = /^(\d+)\.([A-Za-z0-9_-]+)$/.exec(token || '');
  if (!id || !m) return { ok: false, error: '工作階段無效，請重新登入。' };
  const exp = Number(m[1]);
  if (!(exp > Date.now())) return { ok: false, error: '工作階段已逾期，請重新登入。' };
  if (!safeEq(await hmac(id + '|' + exp, secret), m[2])) return { ok: false, error: '工作階段無效，請重新登入。' };
  return { ok: true, exp };
}
function safeEq(a, b) { a = String(a); b = String(b); if (a.length !== b.length) return false; let r = 0; for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i); return r === 0; }

/* ---------------- 讀 ---------------- */
async function list(env) {
  const { results } = await env.DB.prepare('SELECT pn, model, brand, spec, loc, qty, proto, family, contract, cqty, min_qty AS min, note FROM items ORDER BY pn').all();
  const meta = await env.DB.prepare('SELECT COUNT(*) AS c, MAX(updated_at) AS m, SUM(CASE WHEN min_qty IS NOT NULL AND qty <= min_qty THEN 1 ELSE 0 END) AS low FROM items').first();
  return { ok: true, rev: `${meta.c}-${meta.m || ''}`, lowCount: Number(meta.low) || 0, items: results.map((r) => ({ ...r, qty: Number(r.qty) || 0, cqty: r.cqty == null ? null : Number(r.cqty), min: r.min == null ? null : Number(r.min) })) };
}
async function logs(body, env) {
  const limit = Math.max(1, Math.min(MAX_LOG_ROWS, Number(body.limit) || MAX_LOG_ROWS));
  const pn = str(body.pn), kks = canonKks(body.kks);
  const since = isoOrEmpty(body.since), until = isoOrEmpty(body.until);           // ts 是 ISO UTC 字串，直接字串比較
  const before = Math.max(0, Math.trunc(Number(body.before)) || 0);                 // ledger id 游標（上一頁最後一列的 rid）
  const { results } = await env.DB.prepare(`SELECT id, ${LEDGER_COLS} FROM ledger WHERE (?1 = '' OR pn = ?1) AND (?2 = '' OR kks = ?2) AND (?4 = '' OR ts >= ?4) AND (?5 = '' OR ts < ?5) AND (?6 = 0 OR id < ?6) ORDER BY id DESC LIMIT ?3`)
    .bind(pn, kks, limit, since, until, before).all();
  return { ok: true, rows: results.map(ledgerRow) };
}
function ledgerRow(r) {
  return { ts: fmtTs(r.ts), id: r.emp_id || '', name: r.emp_name || '', action: r.action || '', pn: r.pn || '', delta: r.delta == null ? null : Number(r.delta), bal: r.balance == null ? null : Number(r.balance), kks: r.kks || '', note: r.note || '', wo: r.wo || '', source: r.source || '', txn: r.txn_id || '', rid: Number(r.id) || 0 };
}
/** 只接受 ISO 8601 開頭的字串（2026-09-26 或 2026-09-25T16:00:00.000Z），其餘視為沒給 */
function isoOrEmpty(v) { const s = str(v); return /^\d{4}-\d{2}-\d{2}(T[\d:.]+Z?)?$/.test(s) ? s : ''; }

/* ---------------- 寫 ---------------- */
async function txn(body, who, env) {
  const txnId = clip(body.txnId, 40);
  if (!/^[A-Za-z0-9_-]{8,40}$/.test(txnId)) return { ok: false, error: 'txnId 格式錯誤' };
  const items = Array.isArray(body.items) ? body.items : [];
  if (!items.length) return { ok: false, error: '沒有項目' };
  if (items.length > 50) return { ok: false, error: '一次最多 50 項' };
  const kks = clip(canonKks(body.kks), 40), note = clip(body.note, 200), wo = clip(body.wo, 40), source = clip(body.source, 20) || 'ams';
  const merged = new Map();
  for (let i = 0; i < items.length; i++) {
    const pn = str(items[i].pn), d = Math.trunc(Number(items[i].delta));
    if (!pn) return { ok: false, error: `第 ${i + 1} 項缺料號` };
    if (!Number.isFinite(d) || d === 0 || Math.abs(d) > 9999) return { ok: false, error: pn + '：數量必須是非零整數' };
    merged.set(pn, (merged.get(pn) || 0) + d);
  }
  const prev = await replay(txnId, env);
  if (prev) return prev;
  const pns = Array.from(merged.keys());
  const cur = await qtyOf(pns, env);
  const plan = [];
  for (const pn of pns) {
    if (!cur.has(pn)) return { ok: false, error: '料號不存在：' + pn };
    const d = merged.get(pn), q = cur.get(pn).qty;
    if (q + d < 0) return stale(pn, q, -d, cur, pns);
    plan.push({ pn, delta: d });
  }
  const ts = new Date().toISOString();
  const stmts = [env.DB.prepare('INSERT INTO txns (txn_id, ts, emp_id) VALUES (?1, ?2, ?3)').bind(txnId, ts, who.id)];
  for (const p of plan) {
    stmts.push(env.DB.prepare('UPDATE items SET qty = qty + ?1, updated_at = ?2 WHERE pn = ?3').bind(p.delta, ts, p.pn));
    stmts.push(env.DB.prepare(`INSERT INTO ledger (${LEDGER_COLS}) SELECT ?1, ?2, ?3, ?4, ?5, ?6, qty, ?7, ?8, ?9, ?10, ?11 FROM items WHERE pn = ?5`)
      .bind(ts, who.id, who.name, p.delta > 0 ? 'IN' : 'OUT', p.pn, p.delta, kks, note, wo, source, txnId));
  }
  try { await env.DB.batch(stmts); } catch (e) {
    const msg = String(e && e.message || e);
    if (/UNIQUE|PRIMARY KEY/i.test(msg)) { const again = await replay(txnId, env); if (again) return again; }
    if (/CHECK/i.test(msg)) {
      // 預檢之後、寫入之前被別人領走（CHECK(qty>=0) 兜底）：重讀現量，用與預檢相同的格式回 stale 清單
      const now = await qtyOf(pns, env);
      for (const pn of pns) { const q = now.has(pn) ? now.get(pn).qty : 0, d = merged.get(pn); if (q + d < 0) return stale(pn, q, -d, now, pns); }
      return { ok: false, stale: true, error: '庫存不足（剛被別人領走），請確認數量後再試', items: pns.map((pn) => ({ pn, qty: now.has(pn) ? now.get(pn).qty : 0 })) };
    }
    throw e;
  }
  const after = await qtyOf(pns, env);
  return { ok: true, results: plan.map((p) => resultRow(p.pn, p.delta, after.get(p.pn))) };
}
/** 庫存不足的回應：stale:true ＋ 本批全部料號的現量，前端就地更新輸入框上限與「現有 N」，不必關窗重整 */
function stale(pn, q, want, cur, pns) {
  return { ok: false, stale: true, error: `${pn}：庫存不足（現有 ${q}，要領 ${want}）`, items: pns.map((p) => ({ pn: p, qty: cur.has(p) ? cur.get(p).qty : 0 })) };
}
function resultRow(pn, delta, st) {
  const qty = st ? st.qty : null, min = st ? st.min : null;
  return { pn, qty, delta, min, low: min != null && qty != null && qty <= min };
}
async function replay(txnId, env) {
  const { results } = await env.DB.prepare('SELECT l.pn, l.delta, l.balance, i.min_qty FROM ledger l LEFT JOIN items i ON i.pn = l.pn WHERE l.txn_id = ?1 ORDER BY l.id').bind(txnId).all();
  if (!results.length) return null;
  return { ok: true, replay: true, results: results.map((r) => resultRow(r.pn, Number(r.delta), { qty: Number(r.balance), min: r.min_qty == null ? null : Number(r.min_qty) })) };
}
/** pn → {qty, min}（min 為 NULL 代表不提醒） */
async function qtyOf(pns, env) {
  const { results } = await env.DB.prepare(`SELECT pn, qty, min_qty FROM items WHERE pn IN (${pns.map(() => '?').join(',')})`).bind(...pns).all();
  return new Map(results.map((r) => [r.pn, { qty: Number(r.qty) || 0, min: r.min_qty == null ? null : Number(r.min_qty) }]));
}

/* ---------------- 前端錯誤回報 ---------------- */
async function clientlog(body, env) {
  if (!env.AUTH_SECRET) return { ok: false, error: '站台設定不完整' };
  const id = canon(body.id);
  const v = await verify(id, String(body.token || ''), env.AUTH_SECRET);
  if (!v.ok) return { ok: false, auth: true, error: v.error };
  if (await isRevoked(id, env)) return { ok: false, auth: true, error: REVOKED_MSG };
  const msg = clip(body.msg, 500);
  if (!msg) return { ok: false, error: '缺 msg' };
  // 每人每分鐘上限（索引 client_log_emp_ts）：超過就丟棄但仍回 ok，前端不必重試
  const minuteAgo = new Date(Date.now() - 60 * 1000).toISOString();
  const n = await env.DB.prepare('SELECT COUNT(*) AS c FROM client_log WHERE emp_id = ?1 AND ts > ?2').bind(id, minuteAgo).first();
  if (Number(n && n.c) >= CLIENTLOG_PER_MIN) return { ok: true, dropped: true };
  await env.DB.prepare('INSERT INTO client_log (ts, emp_id, emp_name, site, kind, msg, stack, path, page, build, app, ua) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)')
    .bind(new Date().toISOString(), id, clip(norm(body.name), 40), clip(body.site, 60), clip(body.kind, 20) || 'error', msg, clip(body.stack, 2000), clip(body.path, 200), clip(body.page, 200), clip(body.build, 20), clip(body.app, 20), clip(body.ua, 200)).run();
  return { ok: true };
}

/* ---------------- 工具 ---------------- */
function corsHeaders(origin, env) {
  const allowed = String(env.ALLOWED_ORIGINS || '').split(',').map((s) => s.trim()).filter(Boolean);
  const h = { 'Cache-Control': 'no-store', Vary: 'Origin' };
  if (origin && allowed.includes(origin)) h['Access-Control-Allow-Origin'] = origin;
  return h;
}
function json(o, headers, status) { return new Response(JSON.stringify(o), { status: status || 200, headers: { ...headers, 'Content-Type': 'application/json; charset=utf-8' } }); }
function norm(s) { s = String(s == null ? '' : s); try { s = s.normalize('NFKC'); } catch (e) { /* ignore */ } return s.replace(/\s+/g, '').trim(); }
function canon(s) { return norm(s).replace(/^0+(?=\d)/, ''); }
function canonKks(s) { return norm(s).toUpperCase(); }
function str(v) { return String(v == null ? '' : v).trim(); }
function clip(s, n) { return String(s == null ? '' : s).slice(0, n); }
function fmtTs(iso) {
  if (!iso) return '';
  const d = new Date(iso); if (Number.isNaN(d.getTime())) return String(iso);
  return new Intl.DateTimeFormat('sv-SE', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(d).replace('T', ' ');
}
