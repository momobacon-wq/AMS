/**
 * AMS 備品庫存 API（Google Apps Script 網頁應用程式；獨立專案，不是綁在試算表上的那支）
 *
 * 資料：試算表「物料管理系統」（INVENTORY_SS_ID）
 *   Inventory 分頁：A PartNumber(料號 CR…，唯一鍵) | B Name(完整型號) | C Brand | D Spec | E Location | F Quantity
 *                   | G Protocol | H Family | I Contract | J ContractQty | K MinQty | L Note   （A–F 與 Transmitter 網站相容）
 *   Logs 分頁：     A Timestamp | B EmployeeID | C ActionType | D PartNumber | E ChangeAmount | F Balance
 *                   | G EmployeeName | H KKS | I Note | J WorkOrder | K Source | L TxnId   （最新在第 2 列，與 Transmitter 相同）
 *   ActionType：OUT 領取、IN 放入、STOCKTAKE 盤點（設絕對數量）、IMPORT 重建匯入；Transmitter 另有 CHECK_IN/OUT、BATCH_IN/OUT、LOGIN、CREATE
 * 使用者：試算表「物料管理系統 的副本」（USERS_SS_ID）的 Users 分頁（EMPLOYEE_ID、EMPLOYEE_NAME）— 與登入閘門同一份
 *
 * 指令碼屬性（專案設定 → 指令碼屬性）：
 *   INVENTORY_SS_ID  物料管理系統 試算表 ID
 *   USERS_SS_ID      物料管理系統 的副本 試算表 ID（讀 Users）
 *   AUTH_SECRET      與登入閘門（tools/auth/Code.gs）同一個值 → 可驗證 AMS 工作階段 token（從登入專案的指令碼屬性複製）
 *   STOCK_TOKEN      py tools/stock/print_token.py 印出的值（由站台密語導出；換密語後要重貼）
 *
 * 請求：POST、Content-Type text/plain、JSON {action, id, token, stockToken, ...}；一律回 JSON {ok, ...}
 *   list                          → {ok, rev, items:[{pn, model, brand, spec, loc, qty, proto, family, contract, cqty, min, note}]}
 *   logs  {pn?, kks?, limit?}     → {ok, rows:[{ts, id, name, action, pn, delta, bal, kks, note, wo, source, txn}]}
 *   txn   {txnId, items:[{pn, delta}], kks?, note?, wo?, source?} → {ok, results:[{pn, qty}], replay?}
 *   （盤點 adjust 已移除：數量調整直接在試算表改 Quantity 並手動在 Logs 補一列 STOCKTAKE；Worker 版見 tools/stock/README.md）
 * 驗證失敗 → {ok:false, auth:true, error}；伺服器錯誤 → {ok:false, transient:true, error}
 * 一次性管理函式（編輯器手動執行）：setup()（補表頭 G–L 與格式）、migrateFromImport()（Import 分頁 → Inventory，先備份）
 *
 * 部署：部署 → 新增部署作業 → 網頁應用程式 → 執行身分「我」、誰可以存取「所有人」→ 網址填 docs/db/stock-config.json 的 endpoint。
 * 已知限制：Transmitter 的綁定式腳本與本專案各自使用 LockService，兩邊「同一秒」同時出入庫時可能互相覆蓋數量；Logs 為附加式，
 *          可用 auditBalances() 由紀錄重算比對。
 */
var INV_SHEET = 'Inventory';
var LOG_SHEET = 'Logs';
var USERS_SHEET = 'Users';
var IMPORT_SHEET = 'Import';
var INV_HDR = ['PartNumber', 'Name', 'Brand', 'Spec', 'Location', 'Quantity', 'Protocol', 'Family', 'Contract', 'ContractQty', 'MinQty', 'Note'];
var LOG_HDR = ['Timestamp', 'EmployeeID', 'ActionType', 'PartNumber', 'ChangeAmount', 'Balance', 'EmployeeName', 'KKS', 'Note', 'WorkOrder', 'Source', 'TxnId'];
var TZ = 'Asia/Taipei';
var MAX_LOG_ROWS = 300;

function doGet(e) {
  try { prop_('INVENTORY_SS_ID'); return json_({ ok: true, service: 'ams-stock' }); }
  catch (err) { return json_({ ok: false, service: 'ams-stock', error: String(err && err.message || err) }); }
}

function doPost(e) {
  var body = {};
  try { body = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (err) { return json_({ ok: false, error: '請求格式錯誤' }); }
  var action = String(body.action || '');
  try {
    var who = auth_(body);
    if (!who.ok) return json_({ ok: false, auth: true, error: who.error });
    if (action === 'list') return json_(list_());
    if (action === 'logs') return json_(logs_(body));
    if (action === 'txn') return json_(txn_(body, who));
    return json_({ ok: false, error: '未知的動作' });
  } catch (err) {
    console.error(err);
    return json_({ ok: false, transient: true, error: '伺服器暫時無法服務：' + String(err && err.message || err) });
  }
}

/* ---------------- 驗證：AMS 工作階段 token（HMAC）＋ 密語導出的 STOCK_TOKEN ---------------- */
function auth_(body) {
  var st = String(body.stockToken || '');
  if (!st || st !== prop_('STOCK_TOKEN')) return { ok: false, error: '未授權（密語不符或站台設定不完整）' };
  var id = canon_(body.id);
  var v = verify_(id, String(body.token || ''));
  if (!v.ok) return { ok: false, error: v.error };
  var u = findUserById_(id);
  if (!u) return { ok: false, error: '此代號已不在使用者清單中。' };
  return { ok: true, id: u.id, name: u.name };
}

/* ---------------- 讀 ---------------- */
function list_() {
  var t = readInventory_();
  var items = t.rows.filter(function (r) { return str_(r[t.col.PartNumber]) !== ''; }).map(function (r) { return rowItem_(r, t.col); });
  var json = JSON.stringify(items);
  var rev = Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, json, Utilities.Charset.UTF_8)).slice(0, 12);
  return { ok: true, rev: rev, items: items };
}
function rowItem_(r, col) {
  var g = function (k) { return col[k] == null ? '' : r[col[k]]; };
  return {
    pn: str_(g('PartNumber')), model: str_(g('Name')), brand: str_(g('Brand')), spec: str_(g('Spec')), loc: str_(g('Location')),
    qty: num_(g('Quantity')), proto: str_(g('Protocol')), family: str_(g('Family')), contract: str_(g('Contract')),
    cqty: g('ContractQty') === '' ? null : num_(g('ContractQty')), min: g('MinQty') === '' ? null : num_(g('MinQty')), note: str_(g('Note')),
  };
}
function logs_(body) {
  var sh = logSheet_();
  var last = sh.getLastRow();
  var limit = Math.max(1, Math.min(MAX_LOG_ROWS, Number(body.limit) || MAX_LOG_ROWS));
  var pn = str_(body.pn), kks = canonKks_(body.kks);
  var out = [];
  if (last < 2) return { ok: true, rows: out };
  // 有篩選時多掃一些列（最多 3000），沒有篩選只取最新 limit 列
  var n = Math.min(last - 1, (pn || kks) ? 3000 : limit);
  var vals = sh.getRange(2, 1, n, LOG_HDR.length).getValues();
  for (var i = 0; i < vals.length && out.length < limit; i++) {
    var r = vals[i];
    if (pn && str_(r[3]) !== pn) continue;
    if (kks && canonKks_(r[7]) !== kks) continue;
    out.push({ ts: ts_(r[0]), id: str_(r[1]), action: str_(r[2]), pn: str_(r[3]), delta: r[4] === '' || r[4] === '-' ? null : num_(r[4]), bal: r[5] === '' || r[5] === '-' ? null : num_(r[5]),
      name: str_(r[6]), kks: str_(r[7]), note: str_(r[8]), wo: str_(r[9]), source: str_(r[10]), txn: str_(r[11]) });
  }
  return { ok: true, rows: out };
}

/* ---------------- 寫：領取／放入（整批驗證、先寫紀錄再改數量、txnId 冪等） ---------------- */
function txn_(body, who) {
  var txnId = clip_(body.txnId, 40);
  if (!/^[A-Za-z0-9_-]{8,40}$/.test(txnId)) return { ok: false, error: 'txnId 格式錯誤' };
  var items = Array.isArray(body.items) ? body.items : [];
  if (!items.length) return { ok: false, error: '沒有項目' };
  if (items.length > 50) return { ok: false, error: '一次最多 50 項' };
  var kks = clip_(canonKks_(body.kks), 40), note = clip_(body.note, 200), wo = clip_(body.wo, 40), source = clip_(body.source, 20) || 'ams';
  var cache = CacheService.getScriptCache();
  var prev = cache.get('txn:' + txnId);
  if (prev) { var pj = JSON.parse(prev); pj.replay = true; return pj; }
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    prev = cache.get('txn:' + txnId);
    if (prev) { var pj2 = JSON.parse(prev); pj2.replay = true; return pj2; }
    var seen = findTxnInLog_(txnId);
    if (seen) { var res0 = { ok: true, results: seen, replay: true }; cache.put('txn:' + txnId, JSON.stringify({ ok: true, results: seen }), 21600); return res0; }
    var t = readInventory_();
    var byPn = {};
    t.rows.forEach(function (r, i) { var k = str_(r[t.col.PartNumber]); if (k && byPn[k] == null) byPn[k] = i; });
    // 合併同料號、逐項驗證（任一失敗整批不寫）
    var merged = {}, order = [];
    for (var i = 0; i < items.length; i++) {
      var pn = str_(items[i].pn), d = Math.trunc(Number(items[i].delta));
      if (!pn) return { ok: false, error: '第 ' + (i + 1) + ' 項缺料號' };
      if (!Number.isFinite(d) || d === 0 || Math.abs(d) > 9999) return { ok: false, error: pn + '：數量必須是非零整數' };
      if (byPn[pn] == null) return { ok: false, error: '料號不存在：' + pn };
      if (merged[pn] == null) { merged[pn] = 0; order.push(pn); }
      merged[pn] += d;
    }
    var plan = [];
    for (var k = 0; k < order.length; k++) {
      var p = order[k], ri = byPn[p], cur = num_(t.rows[ri][t.col.Quantity]), nq = cur + merged[p];
      if (nq < 0) return { ok: false, error: p + '：庫存不足（現有 ' + cur + '，要領 ' + (-merged[p]) + '）' };
      plan.push({ pn: p, row: ri, delta: merged[p], qty: nq });
    }
    var now = new Date();
    var logSh = logSheet_();
    var rows = plan.map(function (x) {
      return [now, cell_(who.id), x.delta > 0 ? 'IN' : 'OUT', cell_(x.pn), x.delta, x.qty, cell_(who.name), cell_(kks), cell_(note), cell_(wo), cell_(source), cell_(txnId)];
    });
    // 先寫紀錄（最新在上：整批插在第 2 列，批內順序照 plan），再改數量
    logSh.insertRowsBefore(2, rows.length);
    logSh.getRange(2, 1, rows.length, LOG_HDR.length).setValues(rows);
    plan.forEach(function (x) { t.sheet.getRange(x.row + 2, t.col.Quantity + 1).setValue(x.qty); });
    SpreadsheetApp.flush();
    var out = { ok: true, results: plan.map(function (x) { return { pn: x.pn, qty: x.qty, delta: x.delta }; }) };
    cache.put('txn:' + txnId, JSON.stringify(out), 21600);
    cache.remove('inventory');
    return out;
  } finally { lock.releaseLock(); }
}
function findTxnInLog_(txnId) {
  var sh = logSheet_(), last = sh.getLastRow();
  if (last < 2) return null;
  var n = Math.min(last - 1, 500);
  var vals = sh.getRange(2, 1, n, LOG_HDR.length).getValues();
  var out = [];
  for (var i = 0; i < vals.length; i++) if (str_(vals[i][11]) === txnId) out.push({ pn: str_(vals[i][3]), qty: num_(vals[i][5]), delta: num_(vals[i][4]) });
  return out.length ? out : null;
}

/* ---------------- 試算表存取 ---------------- */
function inv_() { return SpreadsheetApp.openById(prop_('INVENTORY_SS_ID')); }
function invSheet_() { var sh = inv_().getSheetByName(INV_SHEET); if (!sh) throw new Error('找不到分頁 ' + INV_SHEET); return sh; }
function logSheet_() {
  var ss = inv_(), sh = ss.getSheetByName(LOG_SHEET);
  if (!sh) { sh = ss.insertSheet(LOG_SHEET); sh.appendRow(LOG_HDR); sh.setFrozenRows(1); }
  return sh;
}
/** Inventory 全表：{sheet, hdr, col:{name→index}, rows}（rows[i] ＝ 試算表第 i+2 列，含空白列以保持列號對應） */
function readInventory_() {
  var sh = invSheet_();
  var vals = sh.getDataRange().getValues();
  if (!vals.length) throw new Error('Inventory 是空的');
  var hdr = vals[0].map(function (h) { return String(h == null ? '' : h).trim(); });
  var col = {};
  hdr.forEach(function (h, i) { if (h && col[h] == null) col[h] = i; });
  ['PartNumber', 'Quantity'].forEach(function (k) { if (col[k] == null) throw new Error('Inventory 缺欄位 ' + k); });
  return { sheet: sh, hdr: hdr, col: col, rows: vals.slice(1) };
}

/* ---------------- 使用者（與登入閘門同一份 Users 分頁） ---------------- */
function readUsers_() {
  var cache = CacheService.getScriptCache(), c = cache.get('users');
  if (c) return JSON.parse(c);
  var ss = SpreadsheetApp.openById(prop_('USERS_SS_ID'));
  var sh = ss.getSheetByName(USERS_SHEET);
  if (!sh) throw new Error('找不到分頁 ' + USERS_SHEET);
  var vals = sh.getDataRange().getDisplayValues();
  var hdr = (vals[0] || []).map(function (h) { return norm_(h).toUpperCase(); });
  var ci = hdr.indexOf('EMPLOYEE_ID'), cn = hdr.indexOf('EMPLOYEE_NAME');
  if (ci < 0) ci = 0;
  if (cn < 0) cn = 1;
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    var id = canon_(vals[i][ci]), raw = String(vals[i][cn] == null ? '' : vals[i][cn]).trim();
    if (id && raw) out.push({ id: id, name: raw });
  }
  cache.put('users', JSON.stringify(out), 300);
  return out;
}
function findUserById_(id) {
  var us = readUsers_(), cid = canon_(id);
  for (var i = 0; i < us.length; i++) if (us[i].id === cid) return us[i];
  return null;
}

/* ---------------- 工作階段 token（與 tools/auth/Code.gs 相同：HMAC-SHA256，密鑰 AUTH_SECRET） ---------------- */
function hmac_(msg) {
  var raw = Utilities.computeHmacSha256Signature(msg, prop_('AUTH_SECRET'));
  return Utilities.base64EncodeWebSafe(raw).replace(/=+$/, '');
}
function verify_(id, token) {
  var m = /^(\d+)\.([A-Za-z0-9_-]+)$/.exec(token || '');
  if (!id || !m) return { ok: false, error: '工作階段無效，請重新登入。' };
  var exp = Number(m[1]);
  if (!(exp > Date.now())) return { ok: false, error: '工作階段已逾期，請重新登入。' };
  if (hmac_(canon_(id) + '|' + exp) !== m[2]) return { ok: false, error: '工作階段無效，請重新登入。' };
  return { ok: true, exp: exp };
}

/* ---------------- 一次性管理函式（在編輯器選取後執行） ---------------- */
/** 補表頭：Inventory G–L、Logs G–L；Logs 文字欄設純文字格式 */
function setup() {
  var ss = inv_();
  var inv = ss.getSheetByName(INV_SHEET);
  if (!inv) { inv = ss.insertSheet(INV_SHEET); }
  var cur = inv.getLastColumn() ? inv.getRange(1, 1, 1, inv.getLastColumn()).getValues()[0].map(function (h) { return String(h || '').trim(); }) : [];
  INV_HDR.forEach(function (h, i) { if (cur[i] !== h) inv.getRange(1, i + 1).setValue(h); });
  inv.setFrozenRows(1);
  var lg = logSheet_();
  var lh = lg.getRange(1, 1, 1, LOG_HDR.length).getValues()[0].map(function (h) { return String(h || '').trim(); });
  LOG_HDR.forEach(function (h, i) { if (lh[i] !== h) lg.getRange(1, i + 1).setValue(h); });
  lg.getRange('A:A').setNumberFormat('yyyy-mm-dd hh:mm:ss');
  lg.getRange('G:L').setNumberFormat('@');
  Logger.log('setup done: ' + INV_HDR.join(',') + ' / ' + LOG_HDR.join(','));
}
/** Import 分頁（tools/stock/contracts_to_inventory.py 產生的 CSV 貼上，含表頭）→ 取代 Inventory；舊分頁先複製為 Inventory_backup_日期 */
function migrateFromImport() {
  var ss = inv_();
  var imp = ss.getSheetByName(IMPORT_SHEET);
  if (!imp) throw new Error('找不到分頁 ' + IMPORT_SHEET + '：請先新增並貼上 inventory_import.csv');
  var vals = imp.getDataRange().getValues();
  var hdr = vals[0].map(function (h) { return String(h || '').trim(); });
  INV_HDR.forEach(function (h, i) { if (hdr[i] !== h) throw new Error('Import 表頭第 ' + (i + 1) + ' 欄應為 ' + h + '，實際 ' + hdr[i]); });
  var rows = vals.slice(1).filter(function (r) { return String(r[0] || '').trim() !== ''; });
  var seen = {};
  rows.forEach(function (r) { var k = String(r[0]).trim(); if (seen[k]) throw new Error('料號重複：' + k); seen[k] = 1; });
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var inv = invSheet_();
    var stamp = Utilities.formatDate(new Date(), TZ, 'yyyyMMdd_HHmm');
    inv.copyTo(ss).setName(INV_SHEET + '_backup_' + stamp);
    inv.clearContents();
    inv.getRange(1, 1, 1, INV_HDR.length).setValues([INV_HDR]);
    inv.getRange(2, 1, rows.length, INV_HDR.length).setValues(rows.map(function (r) { return INV_HDR.map(function (_, i) { return r[i] == null ? '' : r[i]; }); }));
    inv.setFrozenRows(1);
    var lg = logSheet_(), now = new Date();
    var logRows = rows.map(function (r) { return [now, 'system', 'IMPORT', cell_(String(r[0])), '', num_(r[5]), 'migrateFromImport', '', cell_('重建：' + String(r[8] || '') + ' 合約數 ' + String(r[9] || '')), '', 'ams-stock', '']; });
    lg.insertRowsBefore(2, logRows.length);
    lg.getRange(2, 1, logRows.length, LOG_HDR.length).setValues(logRows);
    SpreadsheetApp.flush();
    CacheService.getScriptCache().remove('inventory');
    Logger.log('migrated ' + rows.length + ' rows; backup ' + INV_SHEET + '_backup_' + stamp);
  } finally { lock.releaseLock(); }
}
/** 由 Logs 重算：自最近一筆 IMPORT/STOCKTAKE 起累加 IN/OUT/CHECK_*/BATCH_*，與 Inventory 現值比對，結果寫到 Logger */
function auditBalances() {
  var t = readInventory_();
  var sh = logSheet_(), last = sh.getLastRow();
  var vals = last < 2 ? [] : sh.getRange(2, 1, last - 1, LOG_HDR.length).getValues();
  var base = {}, delta = {};
  for (var i = 0; i < vals.length; i++) { // 最新在上：由新到舊，遇到 IMPORT/STOCKTAKE 就固定基準
    var r = vals[i], pn = str_(r[3]), a = str_(r[2]);
    if (!pn || base[pn] != null) continue;
    if (a === 'IMPORT' || a === 'STOCKTAKE' || a === 'CREATE') { base[pn] = num_(r[5]); continue; }
    if (/^(IN|OUT|CHECK_IN|CHECK_OUT|BATCH_IN|BATCH_OUT)$/.test(a)) delta[pn] = (delta[pn] || 0) + num_(r[4]);
  }
  var bad = [];
  t.rows.forEach(function (r) {
    var pn = str_(r[t.col.PartNumber]); if (!pn) return;
    if (base[pn] == null) return;
    var expect = base[pn] + (delta[pn] || 0), have = num_(r[t.col.Quantity]);
    if (expect !== have) bad.push(pn + ': 紀錄推算 ' + expect + ' ≠ 現值 ' + have);
  });
  Logger.log(bad.length ? bad.join('\n') : '全部一致（' + Object.keys(base).length + ' 個料號有基準）');
}

/* ---------------- 工具 ---------------- */
function prop_(k) { var v = PropertiesService.getScriptProperties().getProperty(k); if (!v) throw new Error('指令碼屬性未設定：' + k); return v; }
function norm_(s) { s = String(s == null ? '' : s); try { s = s.normalize('NFKC'); } catch (e) { /* ignore */ } return s.replace(/\s+/g, '').trim(); }
function canon_(s) { return norm_(s).replace(/^0+(?=\d)/, ''); }
function canonKks_(s) { return norm_(s).toUpperCase(); }
function str_(v) { return String(v == null ? '' : v).trim(); }
function num_(v) { var n = Number(v); return Number.isFinite(n) ? n : 0; }
function clip_(s, n) { return String(s == null ? '' : s).slice(0, n); }
function cell_(s) { s = String(s == null ? '' : s); return /^[=+\-@\t\r]/.test(s) ? "'" + s : s; }
function ts_(d) { return d instanceof Date ? Utilities.formatDate(d, TZ, 'yyyy-MM-dd HH:mm:ss') : str_(d); }
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
