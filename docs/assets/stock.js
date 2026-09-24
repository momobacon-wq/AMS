/* AMS 解析網頁 — 備品庫存（倉庫試算表「物料管理系統」＋ tools/stock/Code.gs API）
 *  - AMS.Stock：設定（stock-config.json）、API 呼叫（與 auth.js 同樣 text/plain JSON POST）、清單快取、對照規則、領取／放入視窗、紀錄視窗
 *  - AMS.StockView：#/stock/ 備品庫存總表（搜尋、購物車批次領取／放入、紀錄、裝機位號反查）
 *  - 查詢卡（card.js）在「一目了然」加「備品庫存」一組，呼叫 AMS.Stock.fillCard()
 * 寫入需要 AMS 工作階段（AMSAuth.user）＋由解鎖金鑰導出的 STOCK_TOKEN（sha256("ams-stock:"+base64(raw key))），沒有密語的人拿到端點也不能讀寫。
 * 對照規則（與 tools/stock/contracts_to_inventory.py 的 FAMILY_RULES 一致）：
 *   正規化＝大寫、去空白／-／_／／；E+H 以「+」前段為本體；Rosemount 壓力／溫度元件／雷達／電磁（3051、2051、2088、3051S、3051L、214C、5408、8732E）本體＝前 12 碼
 *   第一層「同型號」：本體碼相同；第二層「同系列」：系列鍵相同（3051CD、3051TG、644、PMD75、TMT82…）。AMS 型號只有家族名 → 只能到第二層。 */
'use strict';
(function () {
  const AMS = window.AMS;
  const U = AMS.U;
  const D = AMS.data;
  const S = (AMS.Stock = { enabled: false, config: null });
  const meta = document.querySelector('meta[name="ams-stock-config"]');
  const CONFIG_URL = (meta && meta.getAttribute('content')) || 'stock-config.json';
  const TIMEOUT_MS = 20000;
  const LIST_TTL = 30 * 1000;
  let tokenP = null;
  let listP = null; let listAt = 0; let listData = null;

  /* ---------------- 設定與呼叫 ---------------- */
  S.ready = function () {
    if (S._ready) return S._ready;
    S._ready = (async () => {
      let cfg = null;
      try { const r = await fetch(CONFIG_URL, { cache: 'no-cache' }); if (r.ok) cfg = await r.json(); } catch (e) { /* 無設定＝關閉 */ }
      S.config = cfg || {};
      const ep = S.config.endpoint;
      S.enabled = !!(ep && /^https?:\/\//.test(String(ep)) && window.AMSAuth && AMSAuth.user && AMSAuth.user.token);
      if (!S.enabled && ep) console.warn('AMS.Stock: 需要登入工作階段才能使用備品庫存');
      return S.enabled;
    })();
    return S._ready;
  };
  async function token() {
    if (tokenP) return tokenP;
    tokenP = (async () => {
      if (!D.key) return 'plain';  // 明文開發模式（mock）
      const raw = new Uint8Array(await crypto.subtle.exportKey('raw', D.key));
      let b = ''; for (const c of raw) b += String.fromCharCode(c);
      const dig = await crypto.subtle.digest('SHA-256', new TextEncoder().encode('ams-stock:' + btoa(b)));
      return Array.from(new Uint8Array(dig), (x) => x.toString(16).padStart(2, '0')).join('');
    })();
    return tokenP;
  }
  S.call = async function (action, extra) {
    if (!S.enabled) throw new Error('備品庫存未啟用');
    const u = AMSAuth.user || {};
    const body = JSON.stringify(Object.assign({ action, id: u.id, token: u.token, stockToken: await token() }, extra || {}));
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), TIMEOUT_MS);
    try {
      const r = await fetch(S.config.endpoint, { method: 'POST', mode: 'cors', redirect: 'follow', signal: ctl.signal, headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body });
      if (!r.ok) throw new Error('端點錯誤 HTTP ' + r.status);
      let j = null;
      try { j = JSON.parse(await r.text()); } catch (e) { throw new Error('端點回應不是 JSON'); }
      if (!j || typeof j !== 'object') throw new Error('端點回應格式錯誤');
      if (!j.ok) { const err = new Error(j.error || '失敗'); err.auth = !!j.auth; err.transient = !!j.transient; throw err; }
      return j;
    } catch (e) {
      if (e && e.name === 'AbortError') throw new Error('連線逾時（' + TIMEOUT_MS / 1000 + ' 秒）');
      throw e;
    } finally { clearTimeout(t); }
  };
  /** 全部料號（30 秒快取；force 重抓）→ {items, byPn, rev, at} */
  S.list = function (force) {
    const now = Date.now();
    if (!force && listData && now - listAt < LIST_TTL) return Promise.resolve(listData);
    if (listP && !force) return listP;
    listP = S.call('list').then((j) => {
      const items = (j.items || []).map((it) => Object.assign({}, it, { qty: U.num(it.qty), core: S.core(it.model), fam: S.family(it.model) }));
      const byPn = new Map(items.map((it) => [it.pn, it]));
      listData = { items, byPn, rev: j.rev || '', at: Date.now() };
      listAt = listData.at;
      return listData;
    }).finally(() => { listP = null; });
    return listP;
  };
  S.invalidate = function () { listAt = 0; };
  S.txn = async function (o) {
    const txnId = (crypto.randomUUID ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2, 10))).replace(/[^A-Za-z0-9_-]/g, '').slice(0, 40);
    const j = await S.call('txn', { txnId, items: o.items, kks: o.kks || '', note: o.note || '', wo: o.wo || '', source: o.source || 'ams' });
    S.invalidate();
    return j;
  };
  S.logs = (o) => S.call('logs', o || {}).then((j) => j.rows || []);

  /* ---------------- 對照規則 ---------------- */
  const FAMILY_RULES = [/^3051S/, /^3051[CLT][A-Z]?/, /^2051[CT][A-Z]?/, /^2088[AG]/, /^644/, /^848T/, /^5408/, /^8732E/, /^214C/, /^PMD75/, /^PMP71/, /^TMT82/];
  const CORE12 = /^(3051|2051|2088|214C|5408|8732E)/; // 本體＝前 12 碼的家族
  // AMS 廠牌型號（DeviceTypes.Name）→ 系列鍵；'X*' ＝ 該前綴下所有系列（型別未知）
  const AMS_FAMILY = [[/TMT82/i, 'TMT82'], [/Deltabar/i, 'PMD75'], [/Cerabar/i, 'PMP71'], [/^644\b/, '644'], [/^848\b/, '848T'], [/^3051S/, '3051S'], [/^3051\b/, '3051*'], [/^2051\b/, '2051*'], [/^2088\b/, '2088*'], [/^5408/, '5408'], [/8732EM/, '8732E'], [/^214C/, '214C']];
  S.norm = (s) => String(s == null ? '' : s).toUpperCase().replace(/[\s\-_/]/g, '');
  S.base = (s) => S.norm(s).split('+')[0];
  S.family = function (code) {
    const n = S.norm(code);
    for (const r of FAMILY_RULES) { const m = n.match(r); if (m) return m[0]; }
    return n.slice(0, 5);
  };
  S.core = function (code) { const b = S.base(code); return CORE12.test(b) ? b.slice(0, 12) : b; };
  S.amsFamily = function (model) { const t = String(model || '').trim(); for (const [re, f] of AMS_FAMILY) if (re.test(t)) return f; return ''; };
  const famMatch = (devFam, fam) => (devFam.endsWith('*') ? fam.startsWith(devFam.slice(0, -1)) && !(devFam === '3051*' && fam === '3051S') : devFam === fam);
  /** ctx: {codes:[{code, src}], amsModel} → {exact:[item], family:[item], basis:[string]} */
  S.match = function (ctx, items) {
    const cores = new Set(); const fams = new Set(); const basis = [];
    for (const c of ctx.codes || []) { const b = S.base(c.code); if (!b) continue; cores.add(S.core(b)); fams.add(S.family(b)); basis.push(c.src + ' ' + c.code); }
    // AMS 型號只有家族名（3051、644…）：沒有工程文件型號碼時才用它（3051* 會涵蓋 3051C/T/L 全部系列）
    const af = !cores.size && ctx.amsModel ? S.amsFamily(ctx.amsModel) : '';
    if (af) { fams.add(af); basis.push('AMS 型號 ' + ctx.amsModel + ' → ' + af.replace('*', ' 全系列')); }
    const exact = []; const family = [];
    for (const it of items) {
      if (cores.has(it.core)) { exact.push(it); continue; }
      for (const f of fams) { if (famMatch(f, it.fam)) { family.push(it); break; } }
    }
    const byQty = (a, b) => (b.qty - a.qty) || a.pn.localeCompare(b.pn);
    exact.sort(byQty); family.sort(byQty);
    return { exact, family, basis };
  };

  /* ---------------- 共用畫面：庫存列 ---------------- */
  const qtyCls = (it) => (it.qty <= 0 ? 'out' : (it.min != null && it.qty <= it.min ? 'low' : ''));
  function qtyPill(it) {
    const c = qtyCls(it);
    return U.h('span', { class: 'stk-qty ' + c, title: c === 'out' ? '缺貨' : (c === 'low' ? '低於安全存量 ' + it.min : '') }, String(it.qty), c === 'out' ? U.h('span', { class: 'stk-qtyx' }, '缺') : (c === 'low' ? U.h('span', { class: 'stk-qtyx' }, '低') : null));
  }
  function actBtns(it, ctx, onDone) {
    const out = U.h('button', { type: 'button', class: 'btn xs', disabled: it.qty <= 0, title: it.qty <= 0 ? '缺貨' : '領取 ' + it.pn }, '領取');
    const inn = U.h('button', { type: 'button', class: 'btn xs', title: '放入 ' + it.pn }, '放入');
    out.addEventListener('click', () => S.openTxn({ mode: 'out', items: [{ it, n: 1 }], kks: ctx.kks, source: ctx.source, onDone }));
    inn.addEventListener('click', () => S.openTxn({ mode: 'in', items: [{ it, n: 1 }], kks: ctx.kks, source: ctx.source, onDone }));
    return U.h('span', { class: 'stk-acts' }, out, inn);
  }
  function rowEl(it, ctx, onDone, tier) {
    return U.h('tr', { class: 'stk-row ' + qtyCls(it), 'data-pn': it.pn },
      U.h('td', { class: 'nowrap mono' }, it.pn, tier ? U.h('span', { class: 'pill plain stk-tier' }, tier) : null),
      U.h('td', { class: 'mono stk-model', title: it.model }, it.model, it.proto ? U.h('span', { class: 'stk-proto' }, it.proto) : null),
      U.h('td', {}, it.spec || ''),
      U.h('td', { class: 'ar' }, qtyPill(it)),
      U.h('td', { class: 'nowrap' }, it.loc || ''),
      U.h('td', { class: 'nowrap' }, actBtns(it, ctx, onDone)));
  }
  function table(rows) {
    return U.h('div', { class: 'tbl-scroll stk-wrap' }, U.h('table', { class: 'mini stk' },
      U.h('thead', {}, U.h('tr', {}, ...['料號', '型號', '量程／規格', '庫存', '儲位', '操作'].map((h) => U.h('th', {}, h)))),
      U.h('tbody', {}, ...rows)));
  }

  /* ---------------- 查詢卡：一目了然「備品庫存」 ---------------- */
  /** grid：要填的容器；ctx：{tag, alias, codes:[{code,src}], amsModel} */
  S.fillCard = async function (grid, ctx) {
    grid.innerHTML = '<p class="muted cl-empty">載入庫存…</p>';
    let L = null;
    try { L = await S.list(); } catch (e) { grid.innerHTML = ''; grid.appendChild(errBox(e, () => S.fillCard(grid, ctx))); return; }
    if (!grid.isConnected) return;
    const m = S.match(ctx, L.items);
    grid.innerHTML = '';
    const rctx = { kks: ctx.tag, source: 'ams-card' };
    const redo = () => { S.invalidate(); S.fillCard(grid, ctx); };
    const head = U.h('div', { class: 'stk-head' },
      U.h('span', { class: 'stk-sum' }, `同型號 ${m.exact.length} 項 · 同系列 ${m.family.length} 項`),
      U.h('span', { class: 'muted small' }, ' 更新 ' + new Date(L.at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })),
      U.h('button', { type: 'button', class: 'btn xs', onclick: redo }, '重新整理'),
      U.h('button', { type: 'button', class: 'btn xs', onclick: () => S.showLogs({ kks: ctx.tag, title: '此位號的備品出入紀錄' }) }, '此位號紀錄'),
      U.h('a', { class: 'lk small', href: '#/stock/' }, '庫存總表 ›'));
    grid.appendChild(head);
    if (!m.exact.length && !m.family.length) {
      grid.appendChild(U.h('p', { class: 'muted cl-empty' }, '無對應備品（同系列亦無）。' + (m.basis.length ? '依據：' + m.basis.join('；') : '此設備沒有可比對的型號碼')));
      return;
    }
    if (m.exact.length) grid.appendChild(table(m.exact.map((it) => rowEl(it, rctx, redo, '同型號'))));
    else grid.appendChild(U.h('p', { class: 'muted small stk-note' }, '沒有本體型號相同的備品；以下為同系列（選項碼不同，請確認量程、輸出與接口）。'));
    if (m.family.length) {
      const det = U.h('details', { class: 'stk-fam', open: !m.exact.length });
      det.appendChild(U.h('summary', {}, `同系列 ${m.family.length} 項（選項碼不同，需人工確認）`));
      det.appendChild(table(m.family.map((it) => rowEl(it, rctx, redo, '同系列'))));
      grid.appendChild(det);
    }
    grid.appendChild(U.h('p', { class: 'muted small stk-note' }, '依據：' + m.basis.join('；')));
  };
  function errBox(e, retry) {
    const box = U.h('p', { class: 'cl-empty stk-err' }, (e && e.auth ? '未授權：' : '無法讀取庫存：') + ((e && e.message) || e));
    if (retry) box.appendChild(U.h('button', { type: 'button', class: 'btn xs', onclick: retry }, '重試'));
    return box;
  }

  /* ---------------- 領取／放入視窗 ---------------- */
  let modal = null;
  const onKey = (e) => { if (e.key === 'Escape' && modal) { e.preventDefault(); closeModal(); } };
  function closeModal() { if (modal) { modal.remove(); modal = null; document.body.classList.remove('auth-locked'); document.removeEventListener('keydown', onKey, true); } }
  function openModal(el, focusSel) {
    modal = el; document.body.appendChild(el); document.body.classList.add('auth-locked');
    document.addEventListener('keydown', onKey, true);
    setTimeout(() => { const f = focusSel ? el.querySelector(focusSel) : null; if (f) { f.focus(); if (f.select) f.select(); } }, 0);
  }
  /** o: {mode:'out'|'in', items:[{it, n}], kks, source, onDone} */
  S.openTxn = function (o) {
    closeModal();
    const out = o.mode === 'out';
    const rows = o.items.map(({ it, n }) => {
      const inp = U.h('input', { type: 'number', min: 1, max: out ? Math.max(1, it.qty) : 9999, step: 1, value: String(Math.max(1, n || 1)), class: 'stk-n', 'aria-label': '數量 ' + it.pn });
      return { it, inp, el: U.h('div', { class: 'stk-line' }, U.h('div', { class: 'stk-line-t' }, U.h('b', { class: 'mono' }, it.pn), ' ', U.h('span', { class: 'mono small' }, it.model), U.h('span', { class: 'muted small' }, ` 現有 ${it.qty}${it.loc ? ' · ' + it.loc : ''}`)), inp) };
    });
    const kks = U.h('input', { type: 'text', value: o.kks || '', placeholder: '安裝位號 KKS（選填）', autocapitalize: 'characters', spellcheck: 'false', maxlength: 40 });
    const note = U.h('input', { type: 'text', placeholder: out ? '用途／備註（例：故障更換）' : '用途／備註（例：退回倉庫）', maxlength: 200 });
    const wo = U.h('input', { type: 'text', placeholder: '工單／申請單號（選填）', maxlength: 40 });
    const msg = U.h('div', { class: 'auth-msg', role: 'status', 'aria-live': 'polite' });
    const btn = U.h('button', { class: 'btn primary auth-btn', type: 'submit' }, out ? '確認領取' : '確認放入');
    const cancel = U.h('button', { class: 'btn auth-btn', type: 'button', onclick: closeModal }, '取消');
    const form = U.h('form', { class: 'auth-card stk-card', autocomplete: 'off', novalidate: true },
      U.h('div', { class: 'auth-brand' }, U.h('span', { class: 'brand-mark', 'aria-hidden': 'true' }, out ? '領' : '入'),
        U.h('div', null, U.h('h1', { id: 'stk-title' }, out ? '領取備品' : '放入備品'), U.h('p', { class: 'auth-sub' }, `操作人：${(AMSAuth.user && AMSAuth.user.name) || ''}（${(AMSAuth.user && AMSAuth.user.id) || ''}）；每筆都會寫入倉庫紀錄。`))),
      U.h('div', { class: 'stk-lines' }, rows.map((r) => r.el)),
      U.h('label', { class: 'auth-field' }, U.h('span', {}, '安裝位號 KKS'), kks),
      U.h('label', { class: 'auth-field' }, U.h('span', {}, '用途／備註'), note),
      U.h('label', { class: 'auth-field' }, U.h('span', {}, '工單／申請單號'), wo),
      msg, U.h('div', { class: 'stk-btns' }, btn, cancel));
    const gate = U.h('div', { id: 'stk-gate', class: 'auth-gate stk-gate', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'stk-title' }, form);
    if (AMS.Autocomplete && AMS.tagSuggestSource) { try { new AMS.Autocomplete(kks, Object.assign({}, AMS.tagSuggestSource, { onPick: (it) => { kks.value = it.tag || it.key; }, onEnter: () => {} })); } catch (e) { /* 索引未載入 */ } }
    let busy = false;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (busy) return;
      const items = [];
      for (const r of rows) {
        const n = Math.trunc(Number(r.inp.value));
        if (!(n >= 1)) { msg.textContent = r.it.pn + '：請輸入 1 以上的整數'; msg.className = 'auth-msg bad'; r.inp.focus(); return; }
        if (out && n > r.it.qty) { msg.textContent = `${r.it.pn}：庫存只有 ${r.it.qty}`; msg.className = 'auth-msg bad'; r.inp.focus(); return; }
        items.push({ pn: r.it.pn, delta: out ? -n : n });
      }
      busy = true; btn.disabled = true; msg.textContent = '寫入中…'; msg.className = 'auth-msg';
      try {
        const j = await S.txn({ items, kks: kks.value.trim(), note: note.value.trim(), wo: wo.value.trim(), source: o.source || 'ams' });
        closeModal();
        U.toast((out ? '已領取：' : '已放入：') + (j.results || []).map((x) => `${x.pn} → 剩 ${x.qty}`).join('、'), 4000);
        if (o.onDone) o.onDone(j);
      } catch (err) {
        msg.textContent = ((err && err.auth) ? '未授權：' : '寫入失敗：') + ((err && err.message) || err); msg.className = 'auth-msg bad';
      } finally { busy = false; btn.disabled = false; }
    });
    openModal(gate, '.stk-n');
  };

  /* ---------------- 紀錄視窗 ---------------- */
  const ACT_LABEL = { OUT: '領取', IN: '放入', CHECK_OUT: '領取', CHECK_IN: '放入', BATCH_OUT: '領取', BATCH_IN: '放入', STOCKTAKE: '盤點', IMPORT: '匯入', CREATE: '新增', LOGIN: '登入' };
  S.logRows = function (rows, opt) {
    opt = opt || {};
    const tr = rows.map((r) => U.h('tr', { class: 'stk-log ' + String(r.action || '').toLowerCase() },
      U.h('td', { class: 'nowrap' }, r.ts || ''),
      U.h('td', {}, U.h('span', { class: 'pill plain' }, ACT_LABEL[r.action] || r.action || '')),
      U.h('td', { class: 'mono nowrap' }, opt.pnLink ? U.h('a', { class: 'lk', href: '#/stock/?q=' + encodeURIComponent(r.pn || '') }, r.pn || '') : (r.pn || '')),
      U.h('td', { class: 'ar' }, r.delta == null ? '' : (r.delta > 0 ? '+' : '') + r.delta),
      U.h('td', { class: 'ar' }, r.bal == null ? '' : String(r.bal)),
      U.h('td', { class: 'nowrap' }, r.name ? `${r.name}（${r.id}）` : (r.id || '')),
      U.h('td', { class: 'mono' }, r.kks ? U.h('a', { class: 'lk', href: '#/card/' + encodeURIComponent(r.kks) }, r.kks) : ''),
      U.h('td', {}, [r.note, r.wo ? '單號 ' + r.wo : '', r.source && r.source !== 'ams' ? r.source : ''].filter(Boolean).join(' · '))));
    return U.h('div', { class: 'tbl-scroll' }, U.h('table', { class: 'mini stk-logs' },
      U.h('thead', {}, U.h('tr', {}, ...['時間', '動作', '料號', '增減', '結餘', '員工', '位號 KKS', '備註'].map((h) => U.h('th', {}, h)))),
      U.h('tbody', {}, ...(tr.length ? tr : [U.h('tr', {}, U.h('td', { colspan: 8, class: 'muted' }, '（沒有紀錄）'))]))));
  };
  S.showLogs = async function (o) {
    closeModal();
    const body = U.h('div', { class: 'stk-logbody' }, U.h('p', { class: 'muted' }, '載入紀錄…'));
    const card = U.h('div', { class: 'auth-card stk-card wide' },
      U.h('div', { class: 'auth-brand' }, U.h('span', { class: 'brand-mark', 'aria-hidden': 'true' }, '錄'),
        U.h('div', null, U.h('h1', { id: 'stk-title' }, o.title || '備品出入紀錄'), U.h('p', { class: 'auth-sub' }, o.kks ? '位號 ' + o.kks : (o.pn ? '料號 ' + o.pn : '最新 300 筆')))),
      body, U.h('div', { class: 'stk-btns' }, U.h('button', { class: 'btn auth-btn', type: 'button', onclick: closeModal }, '關閉')));
    openModal(U.h('div', { id: 'stk-gate', class: 'auth-gate stk-gate', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'stk-title' }, card), '.stk-btns button');
    try { const rows = await S.logs({ kks: o.kks, pn: o.pn, limit: o.limit || 300 }); body.innerHTML = ''; body.appendChild(S.logRows(rows, { pnLink: true })); }
    catch (e) { body.innerHTML = ''; body.appendChild(errBox(e)); }
  };

  /* ---------------- 裝機位號反查（掃全部 card aux 分塊；結果快取） ---------------- */
  let devIndexP = null;
  S.deviceIndex = function () {
    if (devIndexP) return devIndexP;
    devIndexP = (async () => {
      await AMS.devices.load();
      const ix = await D.loadAuxIndex();
      const byCore = new Map(); const byFam = new Map();
      const add = (map, k, alias) => { if (!k) return; let s = map.get(k); if (!s) { s = new Set(); map.set(k, s); } s.add(alias); };
      const rows = AMS.devices.sheet.rows;
      for (let i = 0; i < rows.length; i++) { const af = S.amsFamily(rows[i][26]); if (af && !af.endsWith('*')) add(byFam, af, U.text(rows[i][1])); }
      for (const f of ix.files || []) {
        const j = await D.fetchJSON(f);
        for (const alias in (j.by_alias || {})) {
          const sec = (j.by_alias[alias] && j.by_alias[alias].sec) || {};
          for (const kind of ['instlist', 'eomr']) {
            for (const ent of ((sec[kind] || {}).entries || [])) {
              const r = (ent.rows || []).find((x) => x[0] === (kind === 'instlist' ? '完整型號碼' : '出廠型號'));
              const code = r && r[1] ? String(r[1]).split('/')[0] : '';
              if (!code) continue;
              add(byCore, S.core(code), alias); add(byFam, S.family(code), alias);
            }
          }
        }
        D.cache.delete(f);
      }
      return { byCore, byFam };
    })().catch((e) => { devIndexP = null; throw e; });
    return devIndexP;
  };
  S.showDevices = async function (it) {
    closeModal();
    const body = U.h('div', { class: 'stk-logbody' }, U.h('p', { class: 'muted' }, '掃描設備型號碼…（第一次約需數秒）'));
    const card = U.h('div', { class: 'auth-card stk-card wide' },
      U.h('div', { class: 'auth-brand' }, U.h('span', { class: 'brand-mark', 'aria-hidden': 'true' }, '裝'),
        U.h('div', null, U.h('h1', { id: 'stk-title' }, '可安裝此備品的位號'), U.h('p', { class: 'auth-sub mono' }, it.pn + ' · ' + it.model))),
      body, U.h('div', { class: 'stk-btns' }, U.h('button', { class: 'btn auth-btn', type: 'button', onclick: closeModal }, '關閉')));
    openModal(U.h('div', { id: 'stk-gate', class: 'auth-gate stk-gate', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'stk-title' }, card), '.stk-btns button');
    try {
      const di = await S.deviceIndex();
      const ex = Array.from(di.byCore.get(it.core) || []);
      const fam = Array.from(di.byFam.get(it.fam) || []).filter((a) => !ex.includes(a));
      const list = (arr) => U.h('div', { class: 'stk-devs' }, arr.sort().map((a) => { const i3 = AMS.devices.byAlias.get(a); const tag = i3 != null ? U.text(AMS.devices.sheet.rows[i3][0]) : ''; return U.h('a', { class: 'chip-btn', href: '#/card/' + encodeURIComponent(a), onclick: closeModal }, tag || a, tag ? U.h('span', { class: 'muted small' }, ' ' + a) : null); }));
      body.innerHTML = '';
      body.appendChild(U.h('h3', { class: 'sum-gh' }, `同型號（本體碼相同）${ex.length} 台`));
      body.appendChild(ex.length ? list(ex) : U.h('p', { class: 'muted cl-empty' }, '（無）'));
      body.appendChild(U.h('h3', { class: 'sum-gh' }, `同系列 ${fam.length} 台`));
      body.appendChild(fam.length ? list(fam.slice(0, 400)) : U.h('p', { class: 'muted cl-empty' }, '（無）'));
      if (fam.length > 400) body.appendChild(U.h('p', { class: 'muted small' }, `（只列前 400 台）`));
    } catch (e) { body.innerHTML = ''; body.appendChild(errBox(e)); }
  };

  /* ---------------- #/stock/ 備品庫存總表 ---------------- */
  class StockView {
    constructor(root, route) {
      this.root = root; this.route = route;
      this.cart = new Map(); // pn → n
      this.tab = 'inv'; this.sortKey = 'pn'; this.sortDir = 1; this.filter = 'all';
      root.className = 'view stock-view';
      root.innerHTML = `<header class="sv-head"><div class="sv-crumb"><span class="mode-badge">庫存</span> 倉庫備品 · <a class="lk soft" href="#/card/">⌂ 設備查詢</a></div><h1 class="sv-title">備品庫存</h1>
        <p class="sv-lead">資料來自倉庫試算表「物料管理系統」；領取／放入會即時寫回並留下紀錄（員工、位號、用途、單號）。搜尋：空白＝同時符合、逗號＝任一符合（例：<code>3051CD, PMD75</code>）。</p></header>
        <div class="stk-tools"><div class="seg" role="tablist"><button type="button" class="seg-btn" data-tab="inv" aria-pressed="true">庫存</button><button type="button" class="seg-btn" data-tab="log" aria-pressed="false">紀錄</button></div>
        <input class="cq-input stk-q" type="search" placeholder="搜尋料號／型號／量程／儲位…" spellcheck="false" aria-label="搜尋庫存">
        <div class="stk-filters"></div><button type="button" class="btn sm stk-reload">重新整理</button><span class="muted small stk-at"></span></div>
        <div class="stk-body"><div class="loading-box"><div class="spinner"></div><p class="lb-msg">載入庫存…</p></div></div>
        <div class="stk-cart" hidden></div>`;
      this.q = root.querySelector('.stk-q'); this.body = root.querySelector('.stk-body'); this.cartEl = root.querySelector('.stk-cart');
      const q0 = route && route.params ? route.params.get('q') : '';
      if (q0) this.q.value = q0;
      this.q.addEventListener('input', U.debounce(() => this.render(), 120));
      root.querySelectorAll('.seg-btn').forEach((b) => b.addEventListener('click', () => { this.tab = b.dataset.tab; root.querySelectorAll('.seg-btn').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); this.load(); }));
      root.querySelector('.stk-reload').addEventListener('click', () => { S.invalidate(); this.load(true); });
      const fl = root.querySelector('.stk-filters');
      for (const [k, l] of [['all', '全部'], ['out', '缺貨'], ['low', '低於安全存量'], ['HART', 'HART'], ['FF', 'FF']]) {
        const b = U.h('button', { type: 'button', class: 'chip-btn' + (k === 'all' ? ' on' : ''), 'data-f': k }, l);
        b.addEventListener('click', () => { this.filter = k; fl.querySelectorAll('.chip-btn').forEach((x) => x.classList.toggle('on', x === b)); this.render(); });
        fl.appendChild(b);
      }
      this.load();
    }
    update(route) { this.route = route; const q0 = route && route.params ? route.params.get('q') : null; if (q0 != null) { this.q.value = q0; this.render(); } }
    destroy() { this.destroyed = true; closeModal(); }
    async load(force) {
      if (this.tab === 'log') { this.body.innerHTML = '<p class="muted cl-empty">載入紀錄…</p>'; try { this.logs = await S.logs({ limit: 300 }); if (!this.destroyed) this.render(); } catch (e) { this.body.innerHTML = ''; this.body.appendChild(errBox(e, () => this.load(true))); } return; }
      try { this.L = await S.list(force); if (!this.destroyed) this.render(); }
      catch (e) { this.body.innerHTML = ''; this.body.appendChild(errBox(e, () => this.load(true))); }
    }
    terms() { return this.q.value.trim().toUpperCase().split(/[,，]/).map((g) => g.trim().split(/\s+/).filter(Boolean)).filter((g) => g.length); }
    hit(text) { const g = this.terms(); if (!g.length) return true; return g.some((and) => and.every((t) => text.includes(t))); }
    render() {
      if (this.tab === 'log') {
        const rows = (this.logs || []).filter((r) => this.hit([r.ts, r.action, r.pn, r.id, r.name, r.kks, r.note, r.wo].join(' ').toUpperCase()));
        this.body.innerHTML = '';
        const bar = U.h('div', { class: 'stk-head' }, U.h('span', { class: 'stk-sum' }, `${rows.length} 筆（最新 300 筆內）`), U.h('button', { type: 'button', class: 'btn xs', onclick: () => this.exportCsv(rows) }, '匯出 CSV'));
        this.body.appendChild(bar); this.body.appendChild(S.logRows(rows, { pnLink: true }));
        this.cartEl.hidden = true;
        return;
      }
      if (!this.L) return;
      this.root.querySelector('.stk-at').textContent = '更新 ' + new Date(this.L.at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
      let items = this.L.items.filter((it) => this.hit([it.pn, it.model, it.brand, it.spec, it.loc, it.proto, it.fam, it.contract, it.note].join(' ').toUpperCase()));
      if (this.filter === 'out') items = items.filter((it) => it.qty <= 0);
      else if (this.filter === 'low') items = items.filter((it) => it.qty <= 0 || (it.min != null && it.qty <= it.min));
      else if (this.filter === 'HART' || this.filter === 'FF') items = items.filter((it) => it.proto === this.filter);
      const k = this.sortKey, d = this.sortDir;
      items.sort((a, b) => { const x = a[k], y = b[k]; return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x == null ? '' : x).localeCompare(String(y == null ? '' : y), 'zh-Hant')) * d || a.pn.localeCompare(b.pn); });
      const total = items.reduce((s, it) => s + it.qty, 0);
      this.body.innerHTML = '';
      this.body.appendChild(U.h('div', { class: 'stk-head' }, U.h('span', { class: 'stk-sum' }, `${items.length} 個料號 · 共 ${U.int(total)} 只`), U.h('span', { class: 'muted small' }, `（全部 ${this.L.items.length} 個料號，缺貨 ${this.L.items.filter((x) => x.qty <= 0).length}）`)));
      const cols = [['pn', '料號'], ['model', '型號'], ['brand', '廠牌'], ['spec', '量程／規格'], ['proto', '協定'], ['qty', '庫存'], ['loc', '儲位'], ['contract', '合約'], ['', '購物車'], ['', '']];
      const th = cols.map(([key, label]) => { const b = U.h('th', { class: key ? 'sortable' + (this.sortKey === key ? (d > 0 ? ' asc' : ' desc') : '') : '' }, label); if (key) b.addEventListener('click', () => { if (this.sortKey === key) this.sortDir = -this.sortDir; else { this.sortKey = key; this.sortDir = 1; } this.render(); }); return b; });
      const tb = U.h('tbody');
      for (const it of items) {
        const n = this.cart.get(it.pn) || 0;
        const minus = U.h('button', { type: 'button', class: 'btn xs', disabled: !n, 'aria-label': '減少 ' + it.pn, onclick: () => this.setCart(it.pn, n - 1) }, '－');
        const plus = U.h('button', { type: 'button', class: 'btn xs', 'aria-label': '增加 ' + it.pn, onclick: () => this.setCart(it.pn, n + 1) }, '＋');
        tb.appendChild(U.h('tr', { class: 'stk-row ' + qtyCls(it) + (n ? ' incart' : ''), 'data-pn': it.pn },
          U.h('td', { class: 'nowrap mono' }, it.pn),
          U.h('td', { class: 'mono stk-model', title: it.model }, it.model, it.note ? U.h('span', { class: 'muted small' }, ' ' + it.note) : null),
          U.h('td', {}, it.brand || ''),
          U.h('td', {}, it.spec || ''),
          U.h('td', { class: 'ac' }, it.proto || ''),
          U.h('td', { class: 'ar' }, qtyPill(it), it.cqty != null ? U.h('span', { class: 'muted small', title: '合約數量' }, ' /' + it.cqty) : null),
          U.h('td', { class: 'nowrap' }, it.loc || ''),
          U.h('td', { class: 'small' }, it.contract || ''),
          U.h('td', { class: 'nowrap stk-cartc' }, minus, U.h('span', { class: 'stk-cn' + (n ? ' on' : '') }, String(n)), plus),
          U.h('td', { class: 'nowrap' }, U.h('button', { type: 'button', class: 'btn xs', title: '哪些位號可用這顆備品', onclick: () => S.showDevices(it) }, '裝機位號'), ' ', U.h('button', { type: 'button', class: 'btn xs', onclick: () => S.showLogs({ pn: it.pn, title: '料號 ' + it.pn + ' 的紀錄' }) }, '紀錄'))));
      }
      if (!items.length) tb.appendChild(U.h('tr', {}, U.h('td', { colspan: cols.length, class: 'muted' }, '（沒有符合的料號）')));
      this.body.appendChild(U.h('div', { class: 'tbl-scroll stk-wrap' }, U.h('table', { class: 'mini stk full' }, U.h('thead', {}, U.h('tr', {}, ...th)), tb)));
      this.renderCart();
    }
    setCart(pn, n) { if (n <= 0) this.cart.delete(pn); else this.cart.set(pn, n); this.render(); }
    renderCart() {
      const el = this.cartEl;
      if (!this.cart.size) { el.hidden = true; el.innerHTML = ''; return; }
      let units = 0; this.cart.forEach((n) => { units += n; });
      const items = () => Array.from(this.cart, ([pn, n]) => ({ it: this.L.byPn.get(pn), n })).filter((x) => x.it);
      const done = () => { this.cart.clear(); S.invalidate(); this.load(true); };
      el.hidden = false; el.innerHTML = '';
      el.appendChild(U.h('span', { class: 'stk-cart-sum' }, `已選 ${this.cart.size} 個料號 · ${units} 只`));
      el.appendChild(U.h('button', { type: 'button', class: 'btn sm primary', onclick: () => S.openTxn({ mode: 'out', items: items(), source: 'ams-stock', onDone: done }) }, '領取'));
      el.appendChild(U.h('button', { type: 'button', class: 'btn sm', onclick: () => S.openTxn({ mode: 'in', items: items(), source: 'ams-stock', onDone: done }) }, '放入'));
      el.appendChild(U.h('button', { type: 'button', class: 'btn sm', onclick: () => { this.cart.clear(); this.render(); } }, '清空'));
    }
    exportCsv(rows) {
      const esc = (v) => { const s = String(v == null ? '' : v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
      const lines = [['時間', '動作', '料號', '增減', '結餘', '員工代號', '姓名', '位號', '備註', '單號', '來源', 'TxnId'].join(',')];
      for (const r of rows) lines.push([r.ts, r.action, r.pn, r.delta, r.bal, r.id, r.name, r.kks, r.note, r.wo, r.source, r.txn].map(esc).join(','));
      const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
      const a = U.h('a', { href: URL.createObjectURL(blob), download: 'stock_logs_' + new Date().toISOString().slice(0, 10) + '.csv' });
      document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
    }
  }
  AMS.StockView = StockView;
})();
