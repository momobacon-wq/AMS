/**
 * AMS 備品庫存 API — Cloudflare Worker + D1（與 tools/stock/Code.gs 同一套請求／回應格式，前端 docs/assets/stock.js 不分後端）
 *
 * 請求：POST /（Content-Type text/plain，JSON {action, id, token, name, stockToken, ...}）；GET / 健康檢查；一律回 JSON {ok, ...}
 *   list                          → {ok, rev, items:[{pn, model, brand, spec, loc, qty, proto, family, contract, cqty, min, note}]}
 *   logs  {pn?, kks?, limit?}     → {ok, rows:[{ts, id, name, action, pn, delta, bal, kks, note, wo, source, txn}]}
 *   txn   {txnId, items:[{pn, delta}], kks?, note?, wo?, source?} → {ok, results:[{pn, qty, delta}], replay?}
 *   adjust {pn, qty, note?}       → {ok, results:[{pn, qty, delta}]}
 * 驗證：stockToken === env.STOCK_TOKEN（站台密語導出）＋ AMS 登入 token（HMAC-SHA256，密鑰 env.AUTH_SECRET，與登入閘門相同）
 *   失敗 → {ok:false, auth:true, error}；伺服器錯誤 → {ok:false, transient:true, error}
 * 資料：D1 表 items / ledger / txns（schema.sql）。txn 用 DB.batch（單一交易）：INSERT txns（重送＝主鍵衝突→回上次結果）、
 *   UPDATE items qty（CHECK(qty>=0) 兜底）、INSERT ledger（balance 由 items 現值帶出）。
 * CORS：只對 env.ALLOWED_ORIGINS（逗號分隔）回 Access-Control-Allow-Origin。
 */
const TZ = 'Asia/Taipei';
const MAX_LOG_ROWS = 300;
const LEDGER_COLS = 'ts, emp_id, emp_name, action, pn, delta, balance, kks, note, wo, source, txn_id';

export default {
  async fetch(req, env) {
    const cors = corsHeaders(req.headers.get('Origin') || '', env);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: { ...cors, 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '86400' } });
    if (req.method === 'GET') return json({ ok: true, service: 'ams-stock', backend: 'd1' }, cors);
    if (req.method !== 'POST') return json({ ok: false, error: 'method not allowed' }, cors, 405);
    let body = {};
    try { body = JSON.parse(await req.text() || '{}'); } catch (e) { return json({ ok: false, error: '請求格式錯誤' }, cors); }
    const action = String(body.action || '');
    try {
      const who = await auth(body, env);
      if (!who.ok) return json({ ok: false, auth: true, error: who.error }, cors);
      if (action === 'list') return json(await list(env), cors);
      if (action === 'logs') return json(await logs(body, env), cors);
      if (action === 'txn') return json(await txn(body, who, env), cors);
      if (action === 'adjust') return json(await adjust(body, who, env), cors);
      return json({ ok: false, error: '未知的動作' }, cors);
    } catch (e) {
      console.error(e);
      return json({ ok: false, transient: true, error: '伺服器暫時無法服務：' + (e && e.message || e) }, cors);
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
  return { ok: true, id, name: clip(norm(body.name), 40) || id };
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
  const meta = await env.DB.prepare('SELECT COUNT(*) AS c, MAX(updated_at) AS m FROM items').first();
  return { ok: true, rev: `${meta.c}-${meta.m || ''}`, items: results.map((r) => ({ ...r, qty: Number(r.qty) || 0, cqty: r.cqty == null ? null : Number(r.cqty), min: r.min == null ? null : Number(r.min) })) };
}
async function logs(body, env) {
  const limit = Math.max(1, Math.min(MAX_LOG_ROWS, Number(body.limit) || MAX_LOG_ROWS));
  const pn = str(body.pn), kks = canonKks(body.kks);
  const { results } = await env.DB.prepare(`SELECT id, ${LEDGER_COLS} FROM ledger WHERE (?1 = '' OR pn = ?1) AND (?2 = '' OR kks = ?2) ORDER BY id DESC LIMIT ?3`).bind(pn, kks, limit).all();
  return { ok: true, rows: results.map(ledgerRow) };
}
function ledgerRow(r) {
  return { ts: fmtTs(r.ts), id: r.emp_id || '', name: r.emp_name || '', action: r.action || '', pn: r.pn || '', delta: r.delta == null ? null : Number(r.delta), bal: r.balance == null ? null : Number(r.balance), kks: r.kks || '', note: r.note || '', wo: r.wo || '', source: r.source || '', txn: r.txn_id || '' };
}

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
    const d = merged.get(pn), q = cur.get(pn);
    if (q + d < 0) return { ok: false, error: `${pn}：庫存不足（現有 ${q}，要領 ${-d}）` };
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
    if (/CHECK/i.test(msg)) return { ok: false, error: '庫存不足（剛被別人領走），請重新整理後再試' };
    throw e;
  }
  const after = await qtyOf(pns, env);
  return { ok: true, results: plan.map((p) => ({ pn: p.pn, qty: after.get(p.pn), delta: p.delta })) };
}
async function replay(txnId, env) {
  const { results } = await env.DB.prepare('SELECT pn, delta, balance FROM ledger WHERE txn_id = ?1 ORDER BY id').bind(txnId).all();
  if (!results.length) return null;
  return { ok: true, replay: true, results: results.map((r) => ({ pn: r.pn, qty: Number(r.balance), delta: Number(r.delta) })) };
}
async function qtyOf(pns, env) {
  const { results } = await env.DB.prepare(`SELECT pn, qty FROM items WHERE pn IN (${pns.map(() => '?').join(',')})`).bind(...pns).all();
  return new Map(results.map((r) => [r.pn, Number(r.qty) || 0]));
}
async function adjust(body, who, env) {
  const pn = str(body.pn), q = Math.trunc(Number(body.qty)), note = clip(body.note, 200);
  if (!pn) return { ok: false, error: '缺料號' };
  if (!Number.isFinite(q) || q < 0 || q > 99999) return { ok: false, error: '數量必須是 0 以上的整數' };
  const cur = await qtyOf([pn], env);
  if (!cur.has(pn)) return { ok: false, error: '料號不存在：' + pn };
  const ts = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare('UPDATE items SET qty = ?1, updated_at = ?2 WHERE pn = ?3').bind(q, ts, pn),
    env.DB.prepare(`INSERT INTO ledger (${LEDGER_COLS}) VALUES (?1, ?2, ?3, 'STOCKTAKE', ?4, ?5, ?6, '', ?7, '', 'ams-stock', '')`).bind(ts, who.id, who.name, pn, q - cur.get(pn), q, note),
  ]);
  return { ok: true, results: [{ pn, qty: q, delta: q - cur.get(pn) }] };
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
