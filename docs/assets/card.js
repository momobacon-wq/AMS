/* AMS 解析網頁 — card 模式（02_設備查詢卡）：索引 → alias → 03 欄位、關鍵組態、附加資料（AMS DB 補充＋工程文件比對）、快速連結、最近變更、參數現值
 * 欄位可帶 src:{lvl,text}（CONTRACT.md「src 契約」）；卡片上方「來源：隱藏｜徽章｜完整」三段切換（規格有 src_defs 才顯示）。
 * 沒有查詢字串（#/card/）＝查詢首頁（範例、最近查過）；規格有 summary 時，查到設備先顯示「一目了然」摘要（位號、廠牌型號、設計規格、協定、
 * 量程單位、警報／跳機設定值、DCS 盤櫃／Case／卡位／點號／端子、P&ID／邏輯圖、文件頁碼），其餘區段收在「完整資料」內。 */
'use strict';
(function () {
  const AMS = window.AMS;
  const U = AMS.U;
  const D = AMS.data;

  // 規格預設值（02.json 缺欄位時使用；內容同 specs/02.md）
  const T = (label, col, extra) => Object.assign({ label, col }, extra || {});
  const R = (label, col, fmt, extra) => Object.assign({ label, col, raw: true, fmt }, extra || {});
  const DEFAULT = {
    title: '02_設備查詢卡',
    default_query: 'G11HAD60BT001',
    input: { label: '查詢位號', prompt: '可輸入清單外的舊位號、HART/FF tag、CMX 位號或 alias' },
    lookup: {
      index_sheet: '05', key_col: 0, src_col: 2, alias_col: 4, count_col: 7, target_sheet: '03', target_alias_col: 1, target_tag_col: 0,
      msg: {
        empty: '請輸入位號…',
        notfound: '查無此字串（萬用字元 * ? 不適用）：請到『05_位號索引』以 Ctrl+F 搜尋部分字串',
        notfound_near: '找不到完全相符的位號，以下列出相近的位號：',
        found_via: '「{q}」已自動對應到 {key}（去掉前後綴／分隔符）。',
        found: '來源：{src}［鍵 {key}］', no_device: '（測試定義清單位號，無對應設備）', device: ' → 目前位號 {tag}',
        multi: '只顯示第一台（優先序最高）',
      },
      labels: { alias: '設備別名 alias', count: '此字串對應設備數' },
    },
    sections: [
      { label: '1. 識別', fields: [T('位號', 0), T('設備別名', 1), T('子機組', 2), T('系統碼＋系統名稱', [3, 4], { join: ' ', trim: true }), T('迴路類型', 6), T('儀表類別', 7), T('製造商', 15), T('型號', 16), T('協定', 18), T('設備版本', 19), T('設備 ID', 21), T('設備序號', 22), T('感測器序號', 24), T('最終組裝號', 26)] },
      { label: '2. 量程與組態', fields: [R('LRV 量程下限', 28, 'General'), R('URV 量程上限', 29, 'General'), T('單位', 30), T('單位碼', 31), T('量程信心', 32), T('量程來源參數', 34), T('量程註記', 33, { span: 2 }), T('感測器型式', 39), T('接線方式', 40), R('感測器下限 LSL', 36, 'General'), R('感測器上限 USL', 37, 'General'), R('阻尼(s)', 41, 'General'), T('轉換函數', 49), T('警報方向', 50), T('寫入保護', 48), R('HART 日期', 47, 'yyyy-mm-dd'), R('輪詢位址', 51, 'General')] },
      { label: '3. 位號與描述', fields: [T('HART 短位號', 43), T('HART 長位號', 44), T('描述', 45), T('訊息', 46), T('HART 位號一致', 54), T('識別時原始位號', 76), T('更名前位號', 79), R('位號指派時間(台灣)', 80, 'yyyy-mm-dd hh:mm:ss.000')] },
      { label: '4. FF（僅 FF 設備）', fields: [T('主 AI Block Tag', 58), T('AI 目標模式', 59), T('XD_SCALE', 61), T('OUT_SCALE', 62), T('L_TYPE', 60), R('FF 感測器校正日期', 69, 'yyyy-mm-dd'), T('FF 型號字串', 27), T('資源區塊 TAG_DESC', 56)] },
      { label: '5. 活動、查核與 CMX', fields: [R('首次出現(台灣)', 85, 'yyyy-mm-dd hh:mm:ss'), R('最後組態(台灣)', 86, 'yyyy-mm-dd hh:mm:ss'), T('最後組態使用者', 87), R('組態事件數', 89, '#,##0'), R('有意義變更數', 93, '#,##0'), R('非經 AMS 重要變更數', 95, '#,##0'), R('待查核項數', 97, '#,##0'), T('最高嚴重度', 98), R('品質分數', 100, '0%'), T('未通過項目', 102), T('CMX 位號', 104), T('CMX 對照狀態', 103), T('待查核摘要', 99, { span: 2 })] },
    ],
    links_title: '6. 快速連結（附筆數）',
    links: [
      { label: '→ 設備總表', sheet: '03', self: true },
      { label: '→ 參數', param: { sheet_col: 109, row_col: 110, count_col: 111 }, none: '→ 參數（無）', fmt: '→ 參數 {n} 筆' },
      { label: '→ 變更（有意義）', sheet: '08', match_col: 2, count_mode: 'prefix#', count_col: 0, fmt: '→ 變更（有意義） {n} 筆', none: '→ 變更（有意義）（無）' },
      { label: '→ 事件', sheet: '10', match_col: 7, count_mode: 'eq', count_col: 7, fmt: '→ 事件 {n} 筆', none: '→ 事件（無）' },
      { label: '→ 待查核', sheet: '07', match_col: 6, count_mode: 'eq', count_col: 6, fmt: '→ 待查核 {n} 筆', none: '→ 待查核（無）' },
      { label: '→ 位號對照', sheet: '06', match_col: 0, count_mode: 'eq', count_col: 0, fmt: '→ 位號對照 {n} 筆', none: '→ 位號對照（無）' },
      { label: '→ FF區塊', sheet: '11', match_col: 1, count_mode: 'eq', count_col: 1, fmt: '→ FF區塊 {n} 筆', none: '→ FF區塊（無）' },
      { label: '→ CMX對照', sheet: '12', match_col: 1, count_mode: 'eq', count_col: 1, fmt: '→ CMX對照 {n} 筆', none: '→ CMX對照（無）' },
    ],
    recent_changes: {
      title: '7. 最近 10 筆有意義變更（來源 08_變更歷程，k=1 最新）', sheet: '08', key_col: 0, k_max: 10,
      columns: [{ label: '時間(台灣)', col: 6, fmt: 'yyyy-mm-dd hh:mm' }, { label: '參數', col: 8 }, { label: '中文名稱', col: 9 }, { label: '舊值 → 新值', cols: [11, 13], join: ' → ' }, { label: '來源判讀', col: 16 }, { label: '使用者', col: 18 }],
    },
    rules: [
      { when: { any: [{ col: 32, eq: '低' }, { col: 33, nonempty: true }] }, targets: [28, 29, 30, 31, 32, 33], style: { bg: '#FCE4D6' } },
      { when: { col: 48, startsWith: '1' }, targets: [48], style: { fc: '#C00000' } },
      { when: { col: 98, eq: '高' }, targets: [98], style: { fc: '#9C0006', bg: '#FFC7CE' } },
      { when: { count_gt: 1 }, targets: ['count'], style: { b: 1, fc: '#C00000' } },
    ],
  };
  const SRC_MODES = ['hide', 'badge', 'full'];
  const SRC_MODE_LABEL = { hide: '隱藏', badge: '徽章', full: '完整' };
  const STORE_MODE = 'card.srcMode';
  const CMP_TEXT = { mismatch: '⚠ 與 DCS 不符', unit_mismatch: '單位不同未比較', unit_unknown: '單位不明未比較', ref_only: '序號不符未比較', ok: '✓ 與 DCS 一致' };
  const cmpCls = (st) => (st === 'mismatch' ? 'bad' : st === 'ok' ? 'ok' : 'soft');
  let uid = 0;

  const fill = (tpl, o) => String(tpl).replace(/\{(\w+)\}/g, (_, k) => (o[k] == null ? '' : String(o[k])));
  /** 站內工作表連結（已跳脫，可直接放進 href="…"）：id 以 encodeURIComponent、r 只接受非負整數（SEC-1） */
  function sheetHref(sid, o) {
    o = o || {};
    const p = [];
    const r = o.r == null ? NaN : Number(o.r);
    if (Number.isInteger(r) && r >= 0) p.push('r=' + r);
    if (o.f) p.push('f=' + encodeURIComponent(JSON.stringify(o.f)));
    return U.esc('#/s/' + encodeURIComponent(String(sid)) + (p.length ? '?' + p.join('&') : ''));
  }
  const lvlOf = (l) => (U.SRC_LVLS.includes(l) ? l : 'raw');

  class CardView {
    constructor(root, meta, route) {
      this.root = root; this.meta = meta; this.id = meta.id;
      this.route = route;
      root.className = 'view card-view';
      root.innerHTML = `<header class="sv-head"><div class="sv-crumb"><span class="mode-badge">查詢卡</span> ${U.esc(meta.group || '')}</div><h1 class="sv-title">${U.esc(meta.name)}</h1></header><div class="loading-box"><div class="spinner"></div><p class="lb-msg">載入查詢卡、位號索引與設備總表…</p><div class="lb-bar"><div></div></div></div>`;
      // 列印：展開 <details>（參數現值除外：展開會觸發非同步載入，列印時來不及畫出）並強制「完整」來源模式
      this._bp = () => {
        this._printing = true; this._opened = [];
        if (this._fillMore) this._fillMore(); // 「完整資料」若還沒展開過，先把延後載入的區段補上
        this.root.querySelectorAll('details:not([open])').forEach((d) => { if (!d.classList.contains('pdet')) { d.open = true; this._opened.push(d); } });
        this.applyMode();
      };
      this._ap = () => { this._printing = false; (this._opened || []).forEach((d) => { d.open = false; }); this._opened = []; this.applyMode(); };
      window.addEventListener('beforeprint', this._bp);
      window.addEventListener('afterprint', this._ap);
      this.load();
    }
    async load() {
      try {
        const specP = D.loadSheet(this.id).catch(() => ({}));
        const [spec] = await Promise.all([specP, AMS.index.load(), AMS.devices.load()]);
        if (this.destroyed) return;
        this.spec = Object.assign({}, DEFAULT, spec || {});
        this.spec.lookup = Object.assign({}, DEFAULT.lookup, (spec && spec.lookup) || {});
        this.spec.lookup.msg = Object.assign({}, DEFAULT.lookup.msg, ((spec && spec.lookup) || {}).msg || {});
        this.spec.lookup.labels = Object.assign({}, DEFAULT.lookup.labels, ((spec && spec.lookup) || {}).labels || {});
        if (!Array.isArray(this.spec.sections) || !this.spec.sections.length) this.spec.sections = DEFAULT.sections;
        if (!Array.isArray(this.spec.links) || !this.spec.links.length) this.spec.links = DEFAULT.links;
        this.spec.recent_changes = Object.assign({}, DEFAULT.recent_changes, (spec && spec.recent_changes) || {});
        if (!Array.isArray(this.spec.rules)) this.spec.rules = DEFAULT.rules;
        this.linkIndex = spec && spec.link_index ? spec.link_index : null;
        this.hasSrc = !!(spec && spec.src_defs);
        this.srcDefs = this.hasSrc ? spec.src_defs : {};
        this.renderShell();
        this.run(this.queryFromRoute(this.route));
      } catch (e) {
        console.error(e);
        const lb = this.root.querySelector('.loading-box');
        if (lb) lb.outerHTML = `<div class="error-box"><h2>無法載入查詢卡</h2><p>${U.esc(e.message)}</p></div>`;
      }
    }
    queryFromRoute(route) {
      if (route && route.query != null) return route.query;
      return ''; // #/card/ 沒有查詢字串 → 查詢首頁
    }
    update(route) { this.route = route; if (this.spec) this.run(this.queryFromRoute(route)); }

    srcLabel(lvl) { return (this.srcDefs[lvl] && this.srcDefs[lvl].label) || U.SRC_LABEL[lvl] || lvl; }

    renderShell() {
      const s = this.spec; const root = this.root;
      const notes = Array.isArray(s.notes) ? s.notes : (s.notes ? [s.notes] : []);
      const home = s.home_link && s.home_link.l ? `<a class="lk soft" href="${U.esc(AMS.linkHref(s.home_link.l))}">${U.esc(s.home_link.t || '⌂ 目錄')}</a>` : '<a class="lk soft" href="#/s/00">⌂ 目錄</a>';
      const srcbar = this.hasSrc ? `<div class="cq-srcbar">
          <span class="cq-srclabel" id="cq-srclabel">來源：</span>
          <div class="seg" role="group" aria-labelledby="cq-srclabel">${SRC_MODES.map((m) => `<button type="button" class="seg-btn" data-mode="${m}" aria-pressed="false">${SRC_MODE_LABEL[m]}</button>`).join('')}</div>
          <span class="src-legend" aria-label="來源分級">${U.SRC_LVLS.map((l) => `<span class="src-chip lvl-${l}" title="${U.esc((this.srcDefs[l] && this.srcDefs[l].desc) || '')}">${U.esc(this.srcLabel(l))}</span>`).join('')}</span>
        </div>` : '';
      root.innerHTML = `
        <header class="sv-head">
          <div class="sv-crumb"><span class="mode-badge">查詢卡</span> ${U.esc(this.meta.group || '')} · ${home}</div>
          <h1 class="sv-title">${U.esc(s.title || this.meta.name)}</h1>
          ${notes.length ? (s.summary ? `<details class="sv-notes"><summary>使用說明</summary><p class="sv-lead">${notes.map((n) => U.esc(n)).join('<br>')}</p></details>` : `<p class="sv-lead">${notes.map((n) => U.esc(n)).join('<br>')}</p>`) : ''}
        </header>
        <div class="card-scroll">
        <form class="cq" role="search" autocomplete="off">
          <label class="cq-label" for="cq-input">${U.esc(s.input && s.input.label || '查詢位號')}</label>
          <div class="cq-field"><input id="cq-input" class="cq-input" type="search" spellcheck="false" autocorrect="off" autocapitalize="characters" enterkeyhint="search" placeholder="${U.esc(s.input && s.input.prompt || '')}" aria-describedby="cq-status"></div>
          <button class="btn primary" type="submit">查詢</button>
        </form>
        ${srcbar}
        <div id="cq-status" class="cq-status" role="status" aria-live="polite"></div>
        <div class="cq-meta"></div>
        <div class="cq-flags" hidden></div>
        <div class="cq-alts" hidden></div>
        <div class="cq-body"></div>
        </div>`;
      this.input = root.querySelector('#cq-input');
      this.scrollEl = root.querySelector('.card-scroll');
      this.bodyEl = root.querySelector('.cq-body');
      const form = root.querySelector('.cq');
      form.addEventListener('submit', (e) => { e.preventDefault(); this.go(this.input.value); });
      this.ac = new AMS.Autocomplete(this.input, Object.assign({}, AMS.tagSuggestSource, {
        onPick: (it) => this.go(it.key),
        onEnter: (t) => this.go(t),
      }));
      root.querySelectorAll('.seg-btn').forEach((b) => b.addEventListener('click', () => { U.store.set(STORE_MODE, b.dataset.mode); this.applyMode(); }));
      // 斷點依卡片容器寬度（不是視窗寬度）：iPad 直向／側欄展開時內容寬可能只有 450–700px
      if ('ResizeObserver' in window) { this.ro = new ResizeObserver(() => this.applyWidth()); this.ro.observe(this.scrollEl); }
      this.applyWidth();
    }
    applyWidth() {
      if (!this.scrollEl || !this.bodyEl) return;
      const bp = (this.spec.src_default && this.spec.src_default.breakpoint) || 640;
      const w = this.scrollEl.clientWidth;
      const narrow = w > 0 && w < bp;
      if (narrow !== this.narrow) { this.narrow = narrow; this.bodyEl.classList.toggle('narrow', narrow); this.applyMode(); }
      else if (!this.modeApplied) this.applyMode();
    }
    currentMode() {
      if (!this.hasSrc) return 'hide';
      if (this._printing) return 'full';
      const st = U.store.get(STORE_MODE, null);
      if (SRC_MODES.includes(st)) return st;
      const d = this.spec.src_default || {};
      return this.narrow ? (d.narrow || 'badge') : (d.wide || 'full');
    }
    applyMode() {
      if (!this.bodyEl) return;
      this.modeApplied = true;
      const m = this.currentMode();
      for (const x of SRC_MODES) this.bodyEl.classList.toggle('src-' + x, x === m);
      this.root.querySelectorAll('.seg-btn').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === m)));
    }
    go(q) {
      q = String(q == null ? '' : q).trim();
      if (U.isMobile() && this.input) this.input.blur(); // 手機：送出後收軟鍵盤，不然摘要被鍵盤蓋住
      if (!q) { this.run(''); return; }
      let k = q;
      try { const rs = AMS.index.resolve(q); if (rs.key) k = rs.key; } catch (e) { /* 索引未載 → 照原字串 */ }
      const h = '#/card/' + encodeURIComponent(k);
      if (location.hash === h) this.run(k); else AMS.router.go(h);
    }

    /* ---------- 查詢鏈 ---------- */
    lookup(q) {
      const L = this.spec.lookup; const M = L.msg;
      const res = { q, key: '', alias: '', count: null, src: '', i3: null, status: '', notfound: false };
      if (q == null || q === '') { res.status = M.empty; res.empty = true; return res; }
      const IX = AMS.index;
      const rs = IX.resolve(q);
      const key = rs.key || IX.norm(q);
      res.key = key; res.how = rs.how;
      if (!key) { res.status = M.empty; res.empty = true; return res; }
      const i5 = rs.key ? IX.first.get(rs.key) : null;
      if (i5 == null) { res.status = M.notfound; res.notfound = true; res.sg = rs.suggestions; return res; }
      const r5 = IX.sheet.rows[i5];
      res.i5 = i5;
      res.alias = U.text(r5[L.alias_col]);
      res.count = U.raw(r5[L.count_col]);
      res.src = U.text(r5[L.src_col]);
      const k = U.text(r5[L.key_col]);
      const DV = AMS.devices;
      res.i3 = res.alias ? (DV.byAlias.get(res.alias) ?? null) : null;
      res.status = (rs.how !== 'exact' && M.found_via ? fill(M.found_via, { q: IX.norm(q), key: k }) : '') + fill(M.found, { src: res.src, key: k });
      if (res.i3 == null) res.status += M.no_device;
      else res.status += fill(M.device, { tag: U.text(DV.sheet.rows[res.i3][L.target_tag_col]) });
      return res;
    }
    run(q) {
      const changed = this.lastQuery !== undefined && this.lastQuery !== q; // 換了位號（卡片內的 chip／相近建議／最近查過）→ 捲回頂端
      this.lastQuery = q;
      // 查詢一律由路由驅動（送出、站內連結、上一頁、網址列貼深連結都會經過這裡）→ 框內文字無條件同步成目前查詢；
      // 以前「框內有焦點就不覆寫」會讓按「上一頁」後卡片換了、框裡還是上一個位號
      const qs = q == null ? '' : String(q);
      if (this.input && this.input.value !== qs) this.input.value = qs;
      const res = (this.res = this.lookup(q));
      if (res.notfound) { // 有相近位號時，狀態列不再叫人去位號索引搜尋，直接說「以下是相近的」
        if (!Array.isArray(res.sg)) { try { res.sg = AMS.index.suggest(res.q, 12); } catch (e) { res.sg = []; } }
        if (res.sg.length && this.spec.lookup.msg.notfound_near) res.status = this.spec.lookup.msg.notfound_near;
      }
      this.aux = null; this.statsReady = false;
      const root = this.root;
      const L = this.spec.lookup;
      if (this.scrollEl) this.scrollEl.classList.toggle('landing', !!res.empty);
      root.querySelector('.cq-status').textContent = res.status;
      root.querySelector('.cq-status').className = 'cq-status' + (res.notfound ? ' bad' : '');
      const row = res.i3 != null ? AMS.devices.sheet.rows[res.i3] : null;
      // alias / count
      const countStyle = this.ruleStyleFor('count', row, res);
      const meta = root.querySelector('.cq-meta');
      if (res.empty || res.notfound) meta.innerHTML = '';
      else {
        meta.innerHTML = `<div class="kv"><span class="k">${U.esc(L.labels.alias)}</span><span class="v strong">${U.esc(res.alias || '')}</span></div>
          <div class="kv"><span class="k">${U.esc(L.labels.count)}</span><span class="v" style="${countStyle}">${res.count == null ? '' : U.esc(U.fmt(res.count))}</span>
          ${typeof res.count === 'number' && res.count > 1 ? `<span class="warn-text">${U.esc(L.msg.multi)}</span>` : ''}</div>`;
      }
      const flagsEl = root.querySelector('.cq-flags');
      flagsEl.hidden = true; flagsEl.innerHTML = '';
      // 其他對應設備
      const alts = root.querySelector('.cq-alts');
      if (typeof res.count === 'number' && res.count > 1) {
        const list = AMS.index.aliasesOf(res.key);
        alts.hidden = false;
        alts.innerHTML = `<span class="muted">此鍵對應的全部設備：</span>` + list.map((a, i) => {
          const i3 = AMS.devices.byAlias.get(a); const tag = i3 != null ? U.text(AMS.devices.sheet.rows[i3][0]) : '';
          return `<a class="chip-btn${i === 0 ? ' on' : ''}" href="#/card/${encodeURIComponent(a)}" title="${U.esc(tag)}">${U.esc(a)}${tag ? ' · ' + U.esc(tag) : ''}${i === 0 ? '（顯示中）' : ''}</a>`;
        }).join('');
      } else { alts.hidden = true; alts.innerHTML = ''; }
      const body = root.querySelector('.cq-body');
      body.innerHTML = '';
      body.classList.toggle('landing', !!res.empty);
      if (changed) { root.scrollTop = 0; if (this.scrollEl) this.scrollEl.scrollTop = 0; }
      if (res.notfound) { body.appendChild(this.renderNotFound(res)); document.title = '查無「' + String(q) + '」 · 設備查詢卡 · AMS'; return; }
      if (res.empty) {
        body.appendChild(this.renderLanding());
        document.title = (this.spec.title || '設備查詢') + ' · AMS';
        if (this.input && !U.isMobile() && document.activeElement !== this.input) this.input.focus();
        return;
      }
      // 區段編號：有 sections_aux 時，附加區段／快速連結／最近變更依實際顯示的區段連續編號（FF 診斷僅 FF 設備）
      const auxList = row ? this.auxSections(row) : [];
      this.nums = null;
      if (Array.isArray(this.spec.sections_aux)) {
        let n = (this.spec.aux && this.spec.aux.number_from) || 5;
        auxList.forEach((sa) => { sa._n = n++; });
        this.nums = { links: n, recent: n + 1 };
      }
      // 有 summary 規格且查到設備：先放「一目了然」摘要，其餘區段收進「完整資料」（<details>，狀態記在 localStorage）
      let host = body;
      const S = this.spec.summary;
      if (S && row) {
        body.appendChild(this.renderSummary(row, res));
        const det = U.h('details', { class: 'cq-more' });
        if (U.store.get('card.moreOpen', false)) det.open = true;
        const sm = U.h('summary', {}, U.h('span', { class: 'csec-h inline' }, S.more_title || '完整資料'), U.h('span', { class: 'muted small' }, ' 點擊展開／收合'));
        sm.addEventListener('click', () => { if (!this._printing) setTimeout(() => U.store.set('card.moreOpen', det.open), 0); });
        det.appendChild(sm);
        host = U.h('div', { class: 'cq-more-body' });
        det.appendChild(host);
        body.appendChild(det);
        this.remember(res, row);
      }
      host.appendChild(this.renderSections(row, res));
      // 關鍵組態現值與最近變更會各抓一張表（變更歷程 247 KB）：有摘要且「完整資料」收合時，展開才載（第一張卡少下載一半以上）
      const slotStats = this.spec.stats && this.spec.stats.sheet ? U.h('div', { class: 'lazy-slot' }) : null;
      const slotRecent = U.h('div', { class: 'lazy-slot' });
      if (slotStats) host.appendChild(slotStats);
      if (auxList.length) host.appendChild(this.renderAux(row, res, auxList));
      host.appendChild(this.renderLinks(row, res));
      host.appendChild(slotRecent);
      host.appendChild(this.renderParams(row, res));
      let filled = false;
      const fillMore = () => {
        if (filled || this.destroyed || this.res !== res) return;
        filled = true;
        if (slotStats) slotStats.replaceWith(this.renderStats(row, res));
        slotRecent.replaceWith(this.renderRecent(row, res));
        this.applyMode();
      };
      this._fillMore = fillMore;
      const det = host === body ? null : host.parentElement;
      if (!det || det.open) fillMore();
      else det.addEventListener('toggle', () => { if (det.open) fillMore(); });
      this.applyMode();
      // 分頁標題以使用者分享的位號為主，alias 附在括號（書籤／歷史紀錄才認得出來；LIVE-5）
      const tag0 = row ? U.text(row[L.target_tag_col]) : '';
      const head = res.empty ? '' : (tag0 || res.key || String(q || ''));
      document.title = [head, res.alias && res.alias !== head ? `（${res.alias}）` : ''].join('') + (head ? ' · ' : '') + '設備查詢卡 · AMS';
    }
    numbered(key, title) { return this.nums && this.nums[key] ? `${this.nums[key]}. ${title}` : title; }

    /** 查無此鍵：05 虛擬捲動表無法用 Ctrl+F 找到畫面外的列 → 直接給建議與「在 05 搜尋」連結（ENG-05） */
    renderNotFound(res) {
      const box = U.h('section', { class: 'csec nf' });
      box.appendChild(U.h('h2', { class: 'csec-h' }, '找不到完全相符的鍵'));
      const inner = U.h('div', { class: 'nf-body' });
      let sg = Array.isArray(res.sg) ? res.sg : null;
      if (!sg) { try { sg = AMS.index.suggest(res.q, 12); } catch (e) { sg = []; } }
      const ixId = (this.spec.lookup && this.spec.lookup.index_sheet) || '05';
      const ixName = D.meta(ixId) ? D.meta(ixId).name : ixId;
      const q = String(res.q == null ? '' : res.q).trim();
      inner.innerHTML = (sg.length
        ? `<p>你是不是要找（含「${U.esc(q)}」的鍵）：</p><div class="nf-chips">${sg.map((it) => `<a class="chip-btn" href="#/card/${encodeURIComponent(it.key)}">${AMS.hilite(it.key, q)}<span class="muted small">${U.esc([it.src, it.alias].filter(Boolean).join(' · '))}</span></a>`).join('')}</div>`
        : '<p class="muted">位號索引中沒有包含這個字串的鍵。</p>')
        + `<p><a class="lk" href="${U.esc('#/s/' + encodeURIComponent(ixId) + '?q=' + encodeURIComponent(q))}">在 ${U.esc(ixName)} 搜尋「${U.esc(q)}」（所有欄位）›</a></p>`;
      box.appendChild(inner);
      return box;
    }

    /* ---------- 條件式格式 ---------- */
    cond(w, row, res) {
      if (!w) return false;
      if (w.any) return w.any.some((x) => this.cond(x, row, res));
      if (w.all) return w.all.every((x) => this.cond(x, row, res));
      if (w.count_gt != null) return typeof res.count === 'number' && res.count > w.count_gt;
      if (!row) return false;
      const v = U.raw(row[w.col]); const t = v == null ? '' : String(v);
      if (w.eq != null) return t === String(w.eq);
      if (w.ne != null) return t !== String(w.ne);
      if (w.startsWith != null) return t.startsWith(String(w.startsWith));
      if (w.contains != null) return t.includes(String(w.contains));
      if (w.nonempty) return t !== '';
      if (w.empty) return t === '';
      if (w.gt != null) return typeof v === 'number' && v > w.gt;
      if (w.lt != null) return typeof v === 'number' && v < w.lt;
      return false;
    }
    ruleStyleFor(target, row, res) {
      const st = {};
      for (const r of this.spec.rules || []) {
        if (!(r.targets || []).some((t) => t === target || String(t) === String(target))) continue;
        if (!this.cond(r.when, row, res)) continue;
        const s = r.style || {};
        for (const k of ['bg', 'fc', 'b', 'i']) if (s[k] != null && st[k] == null) st[k] = s[k]; // 第一個成立者優先
      }
      let css = '';
      const a = U.adaptColors(st.bg, st.fc, U.theme());
      if (a.bg) css += `background:${a.bg};`; if (a.fc) css += `color:${a.fc};`;
      if (st.b) css += 'font-weight:700;'; if (st.i) css += 'font-style:italic;';
      return css;
    }

    /* ---------- 欄位（共用） ---------- */
    fieldValue(f, row) {
      if (!row) return '';
      const cols = Array.isArray(f.col) ? f.col : [f.col];
      if (cols.length > 1 || f.join != null) {
        const vals = cols.map((c) => U.raw(row[c]));
        if (f.blank_if_zero && vals.every((v) => v == null || v === '' || Number(v) === 0)) return '';
        let s = vals.map((v, i) => {
          const t = U.cardValue(v);
          return (f.prefixes && f.prefixes[i] != null && t !== '' ? f.prefixes[i] : '') + t;
        }).join(f.join != null ? f.join : ' ');
        if (f.trim !== false) s = s.replace(/ +/g, ' ').trim();
        return s;
      }
      const raw = U.raw(row[cols[0]]);
      if (raw == null || raw === '') return '';
      const fmt = f.raw && f.fmt && f.fmt !== 'General' ? f.fmt : null;
      return U.cardValue(raw, { fmt, serial: f.serial });
    }
    /** 來源文字中的 {cNN} 以同一列第 NN 欄的值代入（13 表的量程參數／單位參數…） */
    fillSrc(text, row) {
      return String(text || '').replace(/\{c(\d+)\}/g, (_, n) => { const v = row ? U.cardValue(row[Number(n)]) : ''; return v === '' ? '—' : v; });
    }
    /** 協定專用欄位（f.proto＝HART|FF）：設備協定不同且值空白時不顯示 */
    protoSkip(f, row, devRow) {
      const pc = this.spec.protocol_col;
      if (!f.proto || pc == null || !devRow) return false;
      const p = U.text(devRow[pc]);
      return !!p && p !== f.proto && this.fieldValue(f, row) === '';
    }
    /** 規格欄位 → DOM（sections 與 stats 共用）；mode 由 .cq-body 的 class 控制，這裡只產生三種模式都用得到的結構 */
    renderField(f, row, mode, ctx) {
      ctx = ctx || {};
      const val = this.fieldValue(f, row);
      const col0 = Array.isArray(f.col) ? f.col[0] : f.col;
      let label = f.label;
      if (f.label_by && row) {
        const pv = U.text(row[f.label_by.col]);
        label = (f.label_by.map && f.label_by.map[pv]) || f.label_by.default || f.label;
      }
      const head = ctx.columns && ctx.columns[col0];
      const tip = head ? `${ctx.sheetLabel || '03'} 欄：${head.label}` : '';
      return this.fieldEl({
        label, val, tip, span: f.span, cmp: f.cmp,
        css: ctx.noRules ? '' : this.ruleStyleFor(col0, row, this.res),
        num: typeof U.raw(row ? row[col0] : null) === 'number',
        src: f.src ? { lvl: f.src.lvl, text: this.fillSrc(f.src.text, row), detail: f.src.detail } : null,
      }, mode);
    }
    /** o: {label, val, tip, span, css, num, warn, soft, flags:[{t,cls}], cmp, src:{lvl,text,detail:[[k,v]]}} */
    fieldEl(o) {
      const item = U.h('div', { class: 'cf' + (o.span === 2 ? ' span2' : '') + (o.src ? ' has-src' : '') });
      if (o.cmp) item.dataset.cmp = o.cmp;
      item.appendChild(U.h('div', { class: 'cf-k', title: o.tip || null }, o.label));
      const blank = o.val === '' || o.val == null;
      const v = U.h('div', { class: 'cf-v' + (blank ? ' blank' : '') + (o.num && !blank ? ' num' : '') + (o.warn ? ' warn' : '') + (o.soft ? ' soft' : '') });
      if (o.css) v.setAttribute('style', o.css);
      const shown = o.text != null ? o.text : o.val; // o.text：顯示文字與原值不同時（網址類的值顯示短標籤）
      if (!blank && o.href) v.appendChild(U.h('a', { class: 'cf-t doclk', href: o.href, target: '_blank', rel: 'noopener noreferrer', title: o.hrefTitle || '在 Google 雲端硬碟開啟這份文件' }, U.visible(shown, true)));
      else v.appendChild(U.h('span', { class: blank ? 'cf-dash' : 'cf-t' }, blank ? '—' : U.visible(shown, true)));
      for (const fl of o.flags || []) v.appendChild(U.h('span', { class: 'cmp-flag ' + (fl.cls || '') }, fl.t));
      item.appendChild(v);
      if (o.src) {
        const lvl = lvlOf(o.src.lvl); const lab = this.srcLabel(lvl);
        const id = 'cfs' + (++uid);
        const text = String(o.src.text || '');
        const body = text.startsWith(lab + ' · ') ? text.slice(lab.length + 3) : text;
        const btn = U.h('button', { type: 'button', class: 'src-dot lvl-' + lvl, 'aria-expanded': 'false', 'aria-controls': id, title: text, 'aria-label': '來源：' + text },
          U.h('span', { class: 'dot', 'aria-hidden': 'true' }), U.h('span', { class: 'sl' }, lab));
        btn.addEventListener('click', () => { const on = item.classList.toggle('open'); btn.setAttribute('aria-expanded', String(on)); });
        v.appendChild(btn);
        const s = U.h('div', { class: 'cf-src lvl-' + lvl, id });
        s.appendChild(U.h('span', { class: 'src-tag' }, lab));
        s.appendChild(U.h('span', { class: 'src-text' }, body));
        if (o.src.detail && o.src.detail.length) {
          const det = U.h('details', { class: 'src-more' }, U.h('summary', {}, '文件資訊'));
          const dl = U.h('dl', {});
          for (const [k, x] of o.src.detail) { if (x == null || x === '') continue; dl.appendChild(U.h('dt', {}, k)); dl.appendChild(U.h('dd', {}, x instanceof Node ? x : String(x))); }
          det.appendChild(dl);
          s.appendChild(det);
        }
        item.appendChild(s);
      }
      return item;
    }
    colHead() {
      return U.h('div', { class: 'cf-head', 'aria-hidden': 'true' }, U.h('span', {}, '欄位'), U.h('span', {}, '數據'), U.h('span', {}, '來源'));
    }
    renderSections(row) {
      const wrap = U.h('div', { class: 'card-sections' });
      const ctx = { columns: AMS.devices.sheet.columns, sheetLabel: '03' };
      for (const sec of this.spec.sections) {
        const s = U.h('section', { class: 'csec' });
        s.appendChild(U.h('h2', { class: 'csec-h' }, sec.label));
        if (this.hasSrc) s.appendChild(this.colHead());
        const grid = U.h('div', { class: 'cfields' });
        for (const f of sec.fields || []) { if (!this.protoSkip(f, row, row)) grid.appendChild(this.renderField(f, row, this.currentMode(), ctx)); }
        s.appendChild(grid);
        wrap.appendChild(s);
      }
      return wrap;
    }

    /* ---------- 另一張表的關鍵值（spec.stats：{sheet, alias_col, fields:[{label,col,fmt?,src?,cmp?,serial?}]}，依設備別名對到該表的一列） ---------- */
    renderStats(row, res) {
      const st = this.spec.stats;
      const s = U.h('section', { class: 'csec stats' });
      s.appendChild(U.h('h2', { class: 'csec-h' }, st.title || `關鍵組態現值（${D.meta(st.sheet) ? D.meta(st.sheet).name : st.sheet}）`));
      if (this.hasSrc) s.appendChild(this.colHead());
      const grid = U.h('div', { class: 'cfields' });
      s.appendChild(grid);
      if (!row || !res.alias) { grid.innerHTML = '<p class="muted cl-empty">（無對應設備）</p>'; return s; }
      grid.innerHTML = '<p class="muted cl-empty">載入中…</p>';
      const alias = res.alias;
      D.loadSheet(st.sheet).then((j) => {
        if (this.destroyed || this.res.alias !== alias) return;
        const ac = st.alias_col != null ? st.alias_col : (j.columns || []).findIndex((c) => /設備別名|alias/i.test(c.label));
        const i = j.rows.findIndex((r) => U.text(r[ac]) === alias);
        if (i < 0) { grid.innerHTML = `<p class="muted cl-empty">此設備在 ${U.esc(D.meta(st.sheet) ? D.meta(st.sheet).name : st.sheet)} 無資料（沒有參數紀錄）。</p>`; this.statsReady = true; return; }
        const r = j.rows[i];
        grid.innerHTML = '';
        const ctx = { columns: j.columns || [], sheetLabel: st.sheet, noRules: true };
        for (const f of st.fields || []) {
          const ff = Object.assign({ raw: !!f.fmt }, f);
          if (!this.protoSkip(ff, r, row)) grid.appendChild(this.renderField(ff, r, this.currentMode(), ctx));
        }
        const more = U.h('p', { class: 'muted small cf-more' });
        more.innerHTML = `<a class="lk" href="${sheetHref(st.sheet, { r: i })}">在 ${U.esc(D.meta(st.sheet) ? D.meta(st.sheet).name : st.sheet)} 開啟此設備的完整一列 ›</a>`;
        s.appendChild(more);
        this.statsReady = true;
        this.applyCmp();
      }).catch((e) => { grid.innerHTML = `<p class="muted">無法載入：${U.esc(e.message)}</p>`; });
      return s;
    }
    /** DCS 比對結果 → 在 data-cmp 欄位（AMS 量程）旁加 ⚠（aux 與 13 表各自非同步到達，兩邊完成時都呼叫） */
    applyCmp() {
      const cm = this.aux && this.aux.flags && this.aux.flags.cmp;
      if (!cm || !this.bodyEl) return;
      this.bodyEl.querySelectorAll('.cf[data-cmp]').forEach((el) => {
        if (el.dataset.cmpDone) return;
        const k = el.dataset.cmp; const unitOnly = k.endsWith('_unit');
        const stt = cm[unitOnly ? k.slice(0, -5) : k];
        if (!stt || stt === 'ok' || (unitOnly && !/^unit_/.test(stt))) return;
        const v = el.querySelector('.cf-v');
        const src = v.querySelector('.src-dot');
        v.insertBefore(U.h('span', { class: 'cmp-flag ' + cmpCls(stt), title: '見「DCS 比對」區段' }, CMP_TEXT[stt] || stt), src);
        el.dataset.cmpDone = '1';
      });
    }

    /* ---------- 附加資料（card aux：AMS DB 補充＋工程文件比對） ---------- */
    auxSections(row) {
      const list = this.spec.sections_aux;
      if (!Array.isArray(list) || !row) return [];
      const pc = this.spec.protocol_col;
      const isFF = pc != null && U.text(row[pc]) === 'FF';
      return list.filter((sa) => !sa.only_ff || isFF).map((sa) => Object.assign({}, sa));
    }
    renderAux(row, res, list) {
      const wrap = U.h('div', { class: 'card-sections card-aux' });
      const els = {};
      for (const sa of list) {
        const s = U.h('section', { class: 'csec aux aux-' + sa.key });
        const h = U.h('h2', { class: 'csec-h' }, `${sa._n ? sa._n + '. ' : ''}${sa.label}`, U.h('span', { class: 'hflags' }));
        s.appendChild(h);
        if (this.hasSrc && sa.key !== 'compare') s.appendChild(this.colHead());
        const grid = U.h('div', { class: sa.key === 'compare' ? 'cmp-body' : 'cfields' });
        grid.innerHTML = '<p class="muted cl-empty">載入中…</p>';
        s.appendChild(grid);
        if (sa.note) s.appendChild(U.h('p', { class: 'muted small aux-note' }, sa.note));
        wrap.appendChild(s);
        els[sa.key] = { s, h, grid };
      }
      const alias = res.alias;
      const path = this.spec.aux && this.spec.aux.index;
      D.loadAux(alias, path).then(({ ix, aux }) => {
        if (this.destroyed || this.res.alias !== alias) return;
        this.aux = aux; this.auxIx = ix;
        for (const sa of list) {
          const { h, grid } = els[sa.key];
          grid.innerHTML = '';
          try { this.fillAuxSection(sa, aux, ix, grid, h); } catch (e) { console.error(e); grid.innerHTML = `<p class="muted cl-empty">無法顯示：${U.esc(e.message)}</p>`; }
        }
        this.renderFlags(aux);
        this.applyCmp();
      }).catch((e) => {
        for (const sa of list) els[sa.key].grid.innerHTML = `<p class="muted cl-empty">無法載入附加資料：${U.esc(e.message)}</p>`;
      });
      return wrap;
    }
    renderFlags(aux) {
      const el = this.root.querySelector('.cq-flags');
      const f = (aux && aux.flags) || {};
      const out = [];
      if (f.last_change_dcs) out.push(['bad', '⚠ 最後修改＝DCS·外部主機寫入']);
      else if (f.has_dcs_write) out.push(['warn', '曾有 DCS·外部主機寫入']);
      if (f.sync_unrecovered) out.push(['bad', '⚠ 同步失敗後未再成功']);
      const bad = Object.entries(f.cmp || {}).filter(([k, v]) => v === 'mismatch' && !/_(lo|hi)$/.test(k)).map(([k]) => ({ ams: 'AMS 現值', dcdas: 'DCS 控制器組態', dcs_write: 'DCS 寫入事件', terminal: 'DCS 端子表', instlist: '儀器清單', eomr: 'EOMR' }[k] || k));
      if (bad.length) out.push(['bad', '⚠ 量程與 DCS 不符：' + bad.join('、')]);
      // 有摘要時旗標放在摘要標頭（.sum-flags），否則放卡片上方（.cq-flags）
      const target = this.root.querySelector('.sum-flags') || el;
      target.innerHTML = out.map(([c, t]) => `<span class="pill ${c}">${U.esc(t)}</span>`).join('');
      target.hidden = !out.length;
    }
    docDetail(ix, key, extra) {
      const d = key && ix && ix.docs ? ix.docs[key] : null;
      const out = [];
      if (d) {
        out.push(['檔名', d.title]); out.push(['資料夾（工程文件庫根目錄下）', !d.folder || d.folder === '.' ? '（工程文件庫根目錄）' : d.folder]);
        if (d.why) out.push(['選版', d.why]);
        if (d.url) out.push(['Google 雲端硬碟', U.h('a', { class: 'lk', href: d.url, target: '_blank', rel: 'noopener noreferrer' }, '開啟檔案 ↗')]);
      }
      for (const x of extra || []) out.push(x);
      return out;
    }
    /** docindex／docsearch 列的 {rule, alt:[{ref,d,p,why}]} → 來源明細（其他版本／副本各自可點開） */
    rowDetail(ix, ex) {
      const det = this.docDetail(ix, ex.d, [['比對規則', ex.rule]]);
      if (Array.isArray(ex.alt) && ex.alt.length) {
        const box = U.h('span', {});
        ex.alt.forEach((al, i) => {
          const href = this.docHref(ix, al.d);
          const t = al.ref + (al.p && al.p.length ? ' p.' + al.p.join(',') : '') + (al.why ? '（' + al.why + '）' : '');
          if (i) box.appendChild(U.h('span', {}, '；'));
          box.appendChild(href ? U.h('a', { class: 'lk', href, target: '_blank', rel: 'noopener noreferrer', title: this.docTitle(ix, al.d) || '' }, t + ' ↗') : U.h('span', {}, t));
        });
        det.push(['其他版本／副本', box]);
      }
      return det;
    }
    /** index.docs[key].url：文件在 Google 雲端硬碟的連結（build_card_aux --drive-map 補上；沒有就 null） */
    docHref(ix, key) { const d = key && ix && ix.docs ? ix.docs[key] : null; return d && d.url ? d.url : null; }
    docTitle(ix, key) { const d = key && ix && ix.docs ? ix.docs[key] : null; return d && d.title ? '在 Google 雲端硬碟開啟：' + d.title : null; }
    /** 欄位值本身是文件編號（P&ID、邏輯圖、Hook-up 圖、位置圖…）→ index.doc_no 對到「那份文件」：連結開圖本身，不是提到它的來源文件 */
    docNoLink(ix, val) {
      const m = /HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4}/.exec(String(val || ''));
      const key = m && ix && ix.doc_no ? ix.doc_no[m[0]] : null;
      const d = key && ix.docs ? ix.docs[key] : null;
      return d && d.url ? { href: d.url, title: '開啟這份文件：' + d.title, key } : null;
    }
    /** 值有文件連結時的 href／標題／來源明細：值指名的文件優先，否則是值所在的來源文件 */
    valueLink(ix, val, srcKey, detail) {
      const sv = String(val || '');
      if (/^https?:\/\/\S+$/i.test(sv)) { // 值本身是網址（signal-atlas 深連結等）：顯示「站名 › 最後一段」，整段可點，完整網址放來源明細
        let text = sv;
        try { const u = new URL(sv); const segs = (u.hash ? u.hash.replace(/^#\/?/, '') : u.pathname).split('/').filter(Boolean); const site = u.pathname.split('/').filter(Boolean)[0] || u.hostname; text = site + ' › ' + decodeURIComponent(segs[segs.length - 1] || u.hostname); } catch (e) { /* 保留原值 */ }
        detail.push(['連結', U.h('a', { class: 'lk', href: sv, target: '_blank', rel: 'noopener noreferrer' }, sv)]);
        return { href: sv, hrefTitle: '開啟 ' + sv, text };
      }
      const dn = this.docNoLink(ix, val);
      if (dn) {
        const d = ix.docs[dn.key];
        detail.push(['欄位所指文件', U.h('span', {}, d.title + '（' + (d.folder && d.folder !== '.' ? d.folder : '根目錄') + '）', U.h('a', { class: 'lk', href: dn.href, target: '_blank', rel: 'noopener noreferrer' }, ' 開啟 ↗'))]);
        return { href: dn.href, hrefTitle: dn.title };
      }
      if (/HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4}/.test(String(val || ''))) { // 值是文件編號但文件庫裡沒有這份：不連到來源文件（來源仍在「文件資訊」）
        detail.push(['欄位所指文件', '文件庫裡沒有這個編號的檔（來源文件見上列）']);
        return { href: null, hrefTitle: null };
      }
      return { href: this.docHref(ix, srcKey), hrefTitle: this.docTitle(ix, srcKey) };
    }
    searchedList(ix, kind) {
      const seen = new Set(); const out = [];
      for (const s of (ix.searched && ix.searched[kind]) || []) {
        if (!s.used) continue;
        const id = s.ref || (s.doc_id + (s.rev ? '-' + s.rev : ''));
        if (!seen.has(id)) { seen.add(id); out.push({ id, cat: s.category }); }
      }
      return out;
    }
    fillAuxSection(sa, aux, ix, grid, h) {
      const sec = aux && aux.sec ? aux.sec[sa.key] : null;
      const flags = (aux && aux.flags) || {};
      const mode = this.currentMode();
      const empty = (txt) => { grid.appendChild(U.h('p', { class: 'muted cl-empty' }, txt)); };
      if (sa.key === 'compare') { this.fillCompare(aux, grid); return; }
      if (sa.kind) { // 工程文件
        if (!sec) {
          const used = this.searchedList(ix, sa.kind);
          if (sa.kind === 'docindex') {
            const p = U.h('div', { class: 'cl-empty' });
            p.appendChild(U.h('p', { class: 'muted' }, `查無（已比對 ${used.length} 份文件的 PDF 文字層）`));
            const det = U.h('details', { class: 'src-more' }, U.h('summary', {}, '已比對的文件編號'));
            det.appendChild(U.h('p', { class: 'small mono-list' }, used.map((x) => x.id).join('、')));
            p.appendChild(det);
            grid.appendChild(p);
          } else empty(`查無（已比對：${used.map((x) => x.id).join('、') || '—'}）`);
          return;
        }
        if (sec.entries) {
          for (const ent of sec.entries) {
            const sub = U.h('div', { class: 'cf-sub span2' },
              U.h('span', { class: 'src-chip lvl-' + lvlOf(ent.lvl) }, this.srcLabel(lvlOf(ent.lvl))),
              U.h('span', { class: 'sub-h' }, ent.h), ent.rule ? U.h('span', { class: 'muted small' }, ' · 規則 ' + ent.rule) : null,
              ent.note ? U.h('div', { class: 'muted small sub-note' }, ent.note) : null);
            grid.appendChild(sub);
            const detail = this.docDetail(ix, ent.d, [['比對規則', ent.rule], ['備註', ent.note]]);
            for (const r of ent.rows) {
              const st = r[2];
              const flags2 = CMP_TEXT[st] && st !== 'ok' ? [{ t: CMP_TEXT[st], cls: cmpCls(st) }] : [];
              const det = detail.slice(); const lk = this.valueLink(ix, r[1], ent.d, det);
              grid.appendChild(this.fieldEl({ label: r[0], val: U.cardValue(r[1]), warn: st === 'warn', flags: flags2, href: lk.href, hrefTitle: lk.hrefTitle, src: { lvl: ent.lvl, text: ent.src, detail: det } }, mode));
            }
          }
          return;
        }
        for (const r of sec.rows || []) { // docindex／docsearch：每列一份文件（r[4].d → index.docs）
          const ex = r[4] || {};
          grid.appendChild(this.fieldEl({ label: r[0], val: U.cardValue(r[1]), href: this.docHref(ix, ex.d), hrefTitle: this.docTitle(ix, ex.d), src: { lvl: r[2], text: r[3], detail: this.rowDetail(ix, ex) } }, mode));
        }
        return;
      }
      if (!sec || !(sec.rows || []).length) { empty(sa.empty || '（無資料）'); return; }
      if (sa.key === 'change') {
        const hf = h.querySelector('.hflags');
        if (flags.last_change_dcs) hf.appendChild(U.h('span', { class: 'pill bad' }, '⚠ 最後修改＝DCS·外部主機寫入'));
        else if (flags.has_dcs_write) hf.appendChild(U.h('span', { class: 'pill warn' }, '曾有 DCS·外部主機寫入'));
      }
      if (sa.key === 'sync' && flags.sync_unrecovered) h.querySelector('.hflags').appendChild(U.h('span', { class: 'pill bad' }, '⚠ 失敗後未再成功'));
      for (const r of sec.rows) {
        const val = U.cardValue(r[1]);
        const warn = /⚠/.test(val);
        const dcs = sa.key === 'change' && /DCS·外部主機/.test(val);
        grid.appendChild(this.fieldEl({ label: r[0], val, warn: warn || dcs, src: r[3] ? { lvl: r[2], text: r[3] } : null }, mode));
      }
    }
    fillCompare(aux, grid) {
      const list = (aux && aux.compare) || [];
      const sa = (this.spec.sections_aux || []).find((x) => x.key === 'compare') || {};
      if (!list.length) { grid.appendChild(U.h('p', { class: 'muted cl-empty' }, sa.empty || '（無 DCS 基準）')); return; }
      const num = (x) => (x == null ? '' : U.g7(x));
      const srcCell = (o) => {
        const lvl = lvlOf(o.lvl); const lab = this.srcLabel(lvl);
        const t = String(o.src || ''); const body = t.startsWith(lab + ' · ') ? t.slice(lab.length + 3) : t;
        return `<td class="c-src" data-label="來源依據"><div class="c-in"><button type="button" class="src-chip lvl-${lvl}" title="${U.esc(t)}" aria-label="${U.esc('來源：' + t)}">${U.esc(lab)}</button> <span class="src-text">${U.esc(body)}</span></div></td>`;
      };
      const td = (label, inner, cls) => `<td${cls ? ` class="${cls}"` : ''} data-label="${U.esc(label)}"><div class="c-in">${inner}</div></td>`;
      let html = '';
      for (const c of list) {
        const b = c.baseline;
        const bb = Array.isArray(b.bounds) ? b.bounds : ['lo', 'hi'];
        const bnum = (k) => U.esc(num(b[k])) + (b[k] != null && !bb.includes(k) ? ' <span class="muted small nocmp" title="這一端沒有 DCS 寫入，顯示值僅供參考">（不比較）</span>' : '');
        html += `<div class="tbl-scroll"><table class="mini cmp"><caption class="sr-only">${U.esc(c.item)}：DCS 基準比對</caption><thead><tr><th>${U.esc(c.item)}來源</th><th>下限</th><th>上限</th><th>單位</th><th>判定</th><th class="c-src">來源依據</th></tr></thead><tbody>`;
        html += `<tr class="base">${td(c.item + '來源', `<span class="pill base">DCS 基準</span> ${U.esc(b.label || '')}`)}${td('下限', bnum('lo'), 'ar')}${td('上限', bnum('hi'), 'ar')}${td('單位', U.esc(b.unit || '—'))}${td('判定', b.note ? U.esc(b.note) : '—')}${srcCell(b)}</tr>`;
        for (const o of c.others || []) {
          const cls = cmpCls(o.status);
          const ob = Array.isArray(o.bounds) ? o.bounds : null;
          const onum = (k) => U.esc(num(o[k])) + (ob && o[k] != null && !ob.includes(k) ? ' <span class="muted small nocmp" title="這一端沒有 DCS 寫入，顯示值僅供參考">（不比較）</span>' : '');
          html += `<tr class="st-${cls}">${td(c.item + '來源', U.esc(o.label || o.kind))}${td('下限', onum('lo'), 'ar')}${td('上限', onum('hi'), 'ar')}${td('單位', U.esc(o.unit || '—'))}${td('判定', `<span class="cmp-flag ${cls}">${U.esc(CMP_TEXT[o.status] || o.status)}</span>${o.note ? `<div class="muted small">${U.esc(o.note.replace(/^⚠ 與 DCS 不符/, ''))}</div>` : ''}`)}${srcCell(o)}</tr>`;
        }
        html += '</tbody></table></div>';
      }
      grid.innerHTML = html;
      grid.querySelectorAll('.c-src .src-chip').forEach((btn) => btn.addEventListener('click', () => btn.closest('td').classList.toggle('show')));
    }

    /* ---------- 查詢首頁（#/card/ 沒有字串）：說明、範例、最近查過 ---------- */
    recent() { const r = U.store.get('card.recent', []); return Array.isArray(r) ? r.filter((x) => x && x.k) : []; }
    remember(res, row) {
      const k = res.key; if (!k) return;
      const tag = row ? U.text(row[this.spec.lookup.target_tag_col]) : '';
      const list = this.recent().filter((x) => x.k !== k && !(res.alias && x.a === res.alias));
      list.unshift({ k, t: tag && tag !== k ? tag : '', a: res.alias || '' });
      U.store.set('card.recent', list.slice(0, 8));
    }
    renderLanding() {
      const wrap = U.h('div', { class: 'cq-landing' });
      const n = AMS.devices && AMS.devices.sheet ? AMS.devices.sheet.rows.length : 0;
      const wb = D.manifest.workbook || {};
      wrap.appendChild(U.h('h2', { class: 'ld-h' }, '輸入位號，查一台設備'));
      wrap.appendChild(U.h('p', { class: 'ld-p muted' }, `可輸入現行／舊 AMS 位號、識別時位號、HostTag、裝置 ID、設備鍵或別名（大小寫不拘）；打字時會列出建議，按 Enter 或點選即可。${n ? `資料庫共 ${U.int(n)} 台設備` : ''}${wb.source ? `（資料：${wb.source}）` : ''}。`));
      const chips = (title, list, clear) => {
        const box = U.h('div', { class: 'ld-chips' }, U.h('span', { class: 'ld-ct muted small' }, title));
        for (const it of list) {
          box.appendChild(U.h('a', { class: 'chip-btn', href: '#/card/' + encodeURIComponent(it.k) }, U.h('span', { class: 'mono' }, it.k), it.t ? U.h('span', { class: 'small muted' }, ' ' + it.t) : null));
        }
        if (clear) { const b = U.h('button', { type: 'button', class: 'btn xs' }, '清除'); b.addEventListener('click', () => { U.store.set('card.recent', []); box.remove(); }); box.appendChild(b); }
        return box;
      };
      const rec = this.recent();
      if (rec.length) wrap.appendChild(chips('最近查過', rec, true));
      const ex = this.spec.default_query ? [{ k: this.spec.default_query, t: '' }] : [];
      if (ex.length) wrap.appendChild(chips('範例', ex));
      if (this.spec.summary) wrap.appendChild(U.h('p', { class: 'ld-p muted small' }, '查到後最上方先顯示摘要：位號、AMS 與設計規格的廠牌型號、協定版本、量程與單位、警報／跳機設定值、DCS 盤櫃／Case／卡位／點號／端子、P&ID／邏輯圖與文件頁碼；其餘完整資料在下方展開。'));
      return wrap;
    }

    /* ---------- 摘要（一目了然）：03 欄位立即顯示；設備參數統計與 card aux 到達後補上 ---------- */
    renderSummary(row, res) {
      const S = this.spec.summary; const L = this.spec.lookup; const H = S.hero || {};
      const wrap = U.h('section', { class: 'csec sum' });
      const tag = U.text(row[H.tag != null ? H.tag : L.target_tag_col]);
      const hero = U.h('div', { class: 'sum-hero' });
      const tagEl = U.h('div', { class: 'sum-tag' }, U.h('span', { class: 'sum-tagtext' }, tag || res.alias || ''));
      if (tag && navigator.clipboard && navigator.clipboard.writeText) {
        const cb = U.h('button', { type: 'button', class: 'btn xs sum-copy', title: '複製位號' }, '複製');
        cb.addEventListener('click', () => { navigator.clipboard.writeText(tag).then(() => { cb.textContent = '已複製'; setTimeout(() => { cb.textContent = '複製'; }, 1500); }).catch(() => {}); });
        tagEl.appendChild(cb);
      }
      hero.appendChild(tagEl);
      const t = (c) => (c == null ? '' : U.cardValue(row[c]));
      const parts = [[t(H.mfr), t(H.model)].filter(Boolean).join(' '), t(H.proto), t(H.unit)].filter(Boolean);
      hero.appendChild(U.h('div', { class: 'sum-sub' }, parts.map((x) => U.h('span', { class: 'sum-subi' }, x))));
      const svc = U.h('div', { class: 'sum-svc', hidden: true });
      hero.appendChild(svc);
      hero.appendChild(U.h('div', { class: 'sum-flags', hidden: true }));
      wrap.appendChild(hero);
      const groups = U.h('div', { class: 'sum-groups' });
      wrap.appendChild(groups);
      const pend = []; // {el,item} 待資料到達後取代；{grid,group} 整組後填
      const ctx03 = { columns: AMS.devices.sheet.columns, sheetLabel: '03' };
      const pc = this.spec.protocol_col;
      const proto = pc != null ? U.text(row[pc]) : '';
      // group.collapsed：<details> 可收合（預設收起；展開狀態記 localStorage ams.card.sumOpen[key]）；group.after_stock：排在「備品庫存（倉庫）」之後
      const openState = U.store.get('card.sumOpen', {}) || {};
      const after = [];
      for (const g of S.groups || []) {
        let sec;
        if (g.collapsed) {
          const isOpen = openState[g.key] === true;
          sec = U.h('details', { class: 'sum-g sum-' + g.key, open: isOpen });
          sec.appendChild(U.h('summary', { class: 'sum-gh' }, g.label));
          sec.addEventListener('toggle', () => { const st = U.store.get('card.sumOpen', {}) || {}; st[g.key] = sec.open; U.store.set('card.sumOpen', st); });
        } else {
          sec = U.h('section', { class: 'sum-g sum-' + g.key });
          sec.appendChild(U.h('h3', { class: 'sum-gh' }, g.label));
        }
        const grid = U.h('div', { class: g.per_entry ? 'sum-body' : 'cfields sumgrid' });
        sec.appendChild(grid);
        if (g.note) sec.appendChild(U.h('p', { class: 'muted small aux-note' }, g.note));
        if (g.after_stock) after.push(sec); else groups.appendChild(sec);
        if (g.kind || g.per_entry) { grid.innerHTML = '<p class="muted cl-empty">載入中…</p>'; pend.push({ grid, group: g }); continue; }
        for (const it of g.items || []) {
          if (it.proto && proto && proto !== it.proto) continue; // HART／FF 專用列
          if (it.col != null) { const el = this.renderField(it, row, this.currentMode(), ctx03); if (it.big) el.classList.add('big'); grid.appendChild(el); continue; }
          const el = this.fieldEl({ label: it.label, val: '', span: it.span, soft: true });
          el.classList.add('pending'); el.querySelector('.cf-dash').textContent = '…';
          grid.appendChild(el);
          pend.push({ el, item: it });
        }
      }
      // 備品庫存（stock.js；有 stock-config 且已登入才有）：一目了然最後一組，資料到齊後以型號碼對照倉庫
      if (AMS.Stock && AMS.Stock.enabled) {
        const sec = U.h('section', { class: 'sum-g sum-stock' });
        sec.appendChild(U.h('h3', { class: 'sum-gh' }, '備品庫存（倉庫）'));
        const grid = U.h('div', { class: 'sum-body stk-grid' });
        grid.innerHTML = '<p class="muted cl-empty">載入中…</p>';
        sec.appendChild(grid);
        groups.appendChild(sec);
        pend.push({ grid, stock: true, tag });
      }
      for (const sec of after) groups.appendChild(sec); // after_stock 的組（沒有備品庫存時就排最後）
      this.fillSummary(row, res, pend, svc);
      return wrap;
    }
    /** 備品對照用的型號碼：儀器清單「完整型號碼」、EOMR「出廠型號」（去掉 / 後的歧管碼）＋ AMS 型號（家族） */
    stockCtx(row, aux, tag) {
      const H = (this.spec.summary && this.spec.summary.hero) || {};
      const codes = [];
      const secOf = (k) => (aux && aux.sec && aux.sec[k]) || null;
      for (const [kind, key] of [['instlist', '完整型號碼'], ['eomr', '出廠型號']]) {
        for (const ent of ((secOf(kind) || {}).entries || [])) {
          const v = this.rowVal(ent, key); if (!v || v === '—') continue;
          const code = String(v).split('/')[0].trim();
          if (code && !codes.some((c) => c.code === code)) codes.push({ code, src: this.kindLabel(kind) });
        }
      }
      return { tag, alias: this.res.alias, codes, amsModel: H.model != null ? U.cardValue(row[H.model]) : '' };
    }
    rowVal(ent, key) { const r = ((ent && ent.rows) || []).find((x) => x[0] === key); return r ? U.cardValue(r[1]) : ''; }
    rowStatus(ent, key) { const r = ((ent && ent.rows) || []).find((x) => x[0] === key); return r ? r[2] : null; }
    kindLabel(kind) { const kl = (this.auxIx && this.auxIx.kind_label) || {}; return kl[kind] || { dcdas: 'DCS 控制器組態', terminal: 'DCS 端子表', instlist: '儀器清單', eomr: 'EOMR', docindex: '文件索引', docsearch: '文件全文檢索' }[kind] || kind; }
    async fillSummary(row, res, pend, svcEl) {
      const S = this.spec.summary; const alias = res.alias; const st = this.spec.stats;
      let r13 = null; let aux = null; let ix = null;
      const jobs = [];
      if (st && st.sheet && pend.some((p) => p.item && p.item.stats)) {
        jobs.push(D.loadSheet(st.sheet).then((j) => {
          const ac = st.alias_col != null ? st.alias_col : (j.columns || []).findIndex((c) => /設備別名|alias/i.test(c.label));
          const i = j.rows.findIndex((r) => U.text(r[ac]) === alias);
          r13 = i >= 0 ? j.rows[i] : null;
        }).catch(() => {}));
      }
      if (this.spec.aux) jobs.push(D.loadAux(alias, this.spec.aux.index).then((o) => { ix = o.ix; aux = o.aux; }).catch(() => {}));
      await Promise.all(jobs);
      if (this.destroyed || this.res.alias !== alias) return;
      if (ix) { this.auxIx = ix; this.aux = aux; }
      const mode = this.currentMode();
      const secOf = (kind) => (aux && aux.sec && aux.sec[kind]) || null;
      // 多筆文件列時取「主體」：儀器清單略過保護管／感測元件；EOMR 優先序號與 AMS 相符者
      const pickEntry = (kind) => {
        const ents = (secOf(kind) && secOf(kind).entries) || [];
        if (!ents.length) return null;
        if (kind === 'instlist') return ents.find((e) => !/thermowell|element|保護管|熱電偶/i.test(this.rowVal(e, '項目') + ' ' + this.rowVal(e, '儀器種類'))) || ents[0];
        if (kind === 'eomr') return ents.find((e) => this.rowVal(e, '序號與 AMS 相符') === '是') || ents[0];
        return ents[0];
      };
      const H = S.hero || {};
      if (H.service && svcEl) { const v = this.rowVal(pickEntry(H.service.kind), H.service.key); svcEl.textContent = v; svcEl.hidden = !v; }
      for (const p of pend) {
        if (p.stock) { try { AMS.Stock.fillCard(p.grid, this.stockCtx(row, aux, p.tag)); } catch (e) { console.error(e); p.grid.innerHTML = `<p class="muted cl-empty">無法顯示：${U.esc(e.message)}</p>`; } continue; }
        if (p.group) { try { this.fillSumGroup(p.group, p.grid, aux, ix, mode); } catch (e) { console.error(e); p.grid.innerHTML = `<p class="muted cl-empty">無法顯示：${U.esc(e.message)}</p>`; } continue; }
        const it = p.item; let o = null;
        if (it.stats) {
          if (!r13) o = { label: it.label, val: '', soft: true, tip: '此設備在設備參數統計無資料（沒有參數紀錄）' };
          else {
            const s = it.stats;
            const lo = U.cardValue(r13[s.lo]); const hi = U.cardValue(r13[s.hi]); const un = s.unit != null ? U.cardValue(r13[s.unit]) : '';
            const val = lo === '' && hi === '' ? '' : `${lo || '—'} ～ ${hi || '—'}${un ? ' ' + un : ''}`;
            o = { label: it.label, val, cmp: it.cmp, src: it.src ? { lvl: it.src.lvl, text: this.fillSrc(it.src.text, r13) } : null };
          }
        } else if (it.kind) o = this.sumDocItem(it, pickEntry, ix, secOf);
        if (o) { const el = this.fieldEl(o, mode); if (it.big) el.classList.add('big'); p.el.replaceWith(el); }
      }
      this.applyCmp();
    }
    /** 摘要的工程文件欄位：kind＋key（或 keys 陣列，kv=true 時「鍵 值」並列）；找不到時依序用 alt 備援來源（單一或陣列）。
     *  entries 型區段（terminal／instlist／eomr／dcdas）取主體 entry 的列；rows 型區段（docindex／docsearch）以列名對照，每列自帶來源與文件。 */
    sumDocItem(it, pickEntry, ix, secOf) {
      const build = (e, k) => {
        if (!e) return '';
        if (Array.isArray(k)) return k.map((kk) => { const v = this.rowVal(e, kk); return v ? (it.kv ? kk.replace(/^警報 /, '') + ' ' + v : v) : ''; }).filter(Boolean).join(' · ');
        return this.rowVal(e, k);
      };
      const rowsKind = (kind) => { const sec = secOf ? secOf(kind) : null; return sec && !sec.entries && Array.isArray(sec.rows) ? sec.rows : null; };
      const lookup = (kind, key) => {
        const rows = rowsKind(kind);
        if (rows) { // docindex／docsearch：列＝[類別, 值, lvl, 來源, {rule, d}]
          const r = Array.isArray(key) ? null : rows.find((x) => x[0] === key);
          if (!r) return { val: '' };
          const ex = r[4] || {};
          return { val: U.cardValue(r[1]), ent: { lvl: r[2], src: r[3], d: ex.d, rule: ex.rule }, rowsMode: true };
        }
        const ent = pickEntry(kind);
        return { val: build(ent, key), ent };
      };
      let kind = it.kind; let key = it.key; let label = it.label;
      let r = lookup(kind, key);
      if (!r.val && it.alt) {
        for (const alt of Array.isArray(it.alt) ? it.alt : [it.alt]) {
          const r2 = lookup(alt.kind, alt.key);
          if (r2.val) { kind = alt.kind; key = alt.key; r = r2; label = it.label + `（${this.kindLabel(kind)}）`; break; }
        }
      }
      const ent = r.ent; const val = r.val;
      const stt = ent && !r.rowsMode && !Array.isArray(key) ? this.rowStatus(ent, key) : null;
      const flags = CMP_TEXT[stt] && stt !== 'ok' ? [{ t: CMP_TEXT[stt], cls: cmpCls(stt) }] : [];
      const detail = ent ? this.docDetail(ix, ent.d, [['比對規則', ent.rule], ['備註', ent.note]]) : [];
      const lk = ent ? (r.rowsMode ? { href: this.docHref(ix, ent.d), hrefTitle: this.docTitle(ix, ent.d) } : this.valueLink(ix, val, ent.d, detail)) : {};
      const src = ent ? { lvl: ent.lvl, text: ent.src, detail } : null;
      return { label, val, span: it.span, flags, warn: stt === 'warn', src, href: lk.href || null, hrefTitle: lk.hrefTitle || null, soft: !ent, tip: ent ? '' : `查無（${this.kindLabel(kind)}無此位號）` };
    }
    /** 整組依 card aux 區段填入：docindex（每份文件一列）或 per_entry（DCS 端子表每個訊號一塊） */
    fillSumGroup(g, grid, aux, ix, mode) {
      grid.innerHTML = '';
      const sec = (aux && aux.sec && aux.sec[g.kind]) || null;
      const used = ix ? this.searchedList(ix, g.kind) : [];
      if (g.kind === 'docindex' || g.kind === 'docsearch') {
        if (!sec || !(sec.rows || []).length) {
          grid.appendChild(U.h('p', { class: 'muted cl-empty' }, g.kind === 'docsearch' ? `查無（${used.map((x) => x.id).join('、') || '全文索引'}：位號／序號都沒有命中）` : `查無（已比對 ${used.length} 份文件的 PDF 文字層）`));
          return;
        }
        for (const r of sec.rows) { const ex = r[4] || {}; grid.appendChild(this.fieldEl({ label: r[0], val: U.cardValue(r[1]), href: this.docHref(ix, ex.d), hrefTitle: this.docTitle(ix, ex.d), src: { lvl: r[2], text: r[3], detail: this.rowDetail(ix, ex) } }, mode)); }
        return;
      }
      const ents = (sec && sec.entries) || [];
      if (!ents.length) { grid.appendChild(U.h('p', { class: 'muted cl-empty' }, `查無（${this.kindLabel(g.kind)}無此位號；已比對：${used.map((x) => x.id).join('、') || '—'}）`)); return; }
      ents.forEach((ent, k) => {
        const sig = U.h('div', { class: 'sum-sig' });
        const head = U.h('div', { class: 'sum-sigh' });
        if (ents.length > 1) head.appendChild(U.h('span', { class: 'pill plain' }, `訊號 ${k + 1}/${ents.length}`));
        (g.head || []).forEach((hk, i) => { const v = this.rowVal(ent, hk); if (v) head.appendChild(U.h('span', { class: 'sum-sigi' + (i === 0 ? ' key' : ''), title: hk }, v)); });
        sig.appendChild(head);
        const sg = U.h('div', { class: 'cfields sumgrid' });
        const detail = this.docDetail(ix, ent.d, [['比對規則', ent.rule], ['備註', ent.note]]);
        for (const key of g.items || []) {
          const stt = this.rowStatus(ent, key);
          const flags = CMP_TEXT[stt] && stt !== 'ok' ? [{ t: CMP_TEXT[stt], cls: cmpCls(stt) }] : [];
          const v = this.rowVal(ent, key); const det = detail.slice(); const lk = this.valueLink(ix, v, ent.d, det);
          sg.appendChild(this.fieldEl({ label: key, val: v, text: lk.text, flags, href: lk.href, hrefTitle: lk.hrefTitle, src: { lvl: ent.lvl, text: ent.src, detail: det } }, mode));
        }
        sig.appendChild(sg);
        grid.appendChild(sig);
      });
    }

    /* ---------- 快速連結 ---------- */
    renderLinks(row, res) {
      const s = U.h('section', { class: 'csec links' });
      s.appendChild(U.h('h2', { class: 'csec-h' }, this.numbered('links', this.spec.links_title || DEFAULT.links_title)));
      const grid = U.h('div', { class: 'clinks' });
      s.appendChild(grid);
      if (!row) { grid.innerHTML = '<p class="muted cl-empty">（無對應設備）</p>'; return s; }
      const alias = res.alias;
      const pending = [];
      for (const lk of this.spec.links) {
        const cell = U.h('div', { class: 'cl' });
        grid.appendChild(cell);
        if (lk.self) {
          cell.innerHTML = `<a class="lk" href="${sheetHref(lk.sheet || '03', { r: res.i3 })}">${U.esc(lk.label)}</a>`;
          continue;
        }
        if (lk.param) {
          const p = lk.param;
          const sheetName = U.text(row[p.sheet_col]);
          if (!sheetName) { cell.textContent = lk.none || '→ 參數（無）'; cell.classList.add('none'); continue; }
          const sm = D.byName.get(sheetName) || D.meta(sheetName.slice(0, 2));
          const sid = sm ? sm.id : sheetName.slice(0, 2);
          const dg = Number(U.raw(row[p.row_col])); const n = U.raw(row[p.count_col]);
          const r = isFinite(dg) ? dg - this.dataFirstRow(sid) : null;
          cell.innerHTML = `<a class="lk" href="${sheetHref(sid, { r })}">${U.esc(fill(lk.fmt || '→ 參數 {n} 筆', { n: n == null ? '' : String(n) }))}</a>`;
          continue;
        }
        if (!alias) { cell.textContent = ''; continue; }
        const li = this.linkIndex;
        if (li) {
          const e = li[alias] && li[alias][lk.sheet];
          this.fillLink(cell, lk, e || null);
        } else {
          cell.innerHTML = `<span class="muted">${U.esc(lk.label)} …</span>`;
          pending.push([cell, lk]);
        }
      }
      if (pending.length) this.computeLinks(alias, pending);
      return s;
    }
    fillLink(cell, lk, e) {
      if (!e || e[0] == null) { cell.textContent = lk.none || (lk.label + '（無）'); cell.classList.add('none'); return; }
      const r0 = Number(e[0]); const n = Number(e[1]);
      // 超過 1 筆時同時篩選出此設備的全部列（否則只標示第一列，其餘混在全表中；ENG-10）
      let f = null;
      const alias = this.res && this.res.alias;
      if (alias && n > 1) {
        if (lk.count_mode === 'prefix#' && lk.count_col != null) f = { [lk.count_col]: '^' + alias + '#' };
        else if (lk.match_col != null) f = { [lk.match_col]: '=' + alias };
      }
      cell.innerHTML = `<a class="lk" href="${sheetHref(lk.sheet, { r: r0, f })}">${U.esc(fill(lk.fmt || (lk.label + ' {n} 筆'), { n: Number.isFinite(n) ? n : '' }))}</a>`;
    }
    async computeLinks(alias, pending) {
      // 沒有 link_index 時，載入目標表計算（與 Excel MATCH／COUNTIF 同義）
      for (const [cell, lk] of pending) {
        try {
          const j = await D.loadSheet(lk.sheet);
          if (this.destroyed || this.res.alias !== alias) return;
          let r0 = null; let n = 0;
          const mc = lk.match_col; const cc = lk.count_col != null ? lk.count_col : mc;
          const pre = alias + '#';
          j.rows.forEach((row, i) => {
            if (r0 == null && U.text(row[mc]) === alias) r0 = i;
            const t = U.text(row[cc]);
            if (lk.count_mode === 'prefix#' ? t.startsWith(pre) : t === alias) n++;
          });
          this.fillLink(cell, lk, r0 == null ? null : [r0, n]);
        } catch (e) { cell.textContent = lk.label + '（無法載入 ' + lk.sheet + '）'; }
      }
    }
    dataFirstRow(sid) {
      const m = D.meta(sid);
      return (m && m.data_first_row) || 5; // table 模式資料首列＝Excel 第 5 列（CONTRACT v2）
    }

    /* ---------- 最近變更 ---------- */
    renderRecent(row, res) {
      const rc = this.spec.recent_changes;
      const s = U.h('section', { class: 'csec recent' });
      s.appendChild(U.h('h2', { class: 'csec-h' }, this.numbered('recent', rc.title || DEFAULT.recent_changes.title)));
      const body = U.h('div', { class: 'recent-body' });
      s.appendChild(body);
      if (!row || !res.alias) { body.innerHTML = '<p class="muted">（無）</p>'; return s; }
      body.innerHTML = `<p class="muted">載入 ${U.esc(D.meta(rc.sheet) ? D.meta(rc.sheet).name : rc.sheet)}…</p>`;
      const alias = res.alias;
      D.loadSheet(rc.sheet).then((j) => {
        if (this.destroyed || this.res.alias !== alias) return;
        if (!this.recentIdx || this.recentIdx.j !== j) {
          const m = new Map();
          j.rows.forEach((r, i) => {
            const k = U.text(r[rc.key_col]);
            const p = k.lastIndexOf('#');
            if (p <= 0) return;
            const a = k.slice(0, p); const n = Number(k.slice(p + 1));
            if (!m.has(a)) m.set(a, []);
            m.get(a).push([n, i]);
          });
          m.forEach((arr) => arr.sort((x, y) => x[0] - y[0]));
          this.recentIdx = { j, m };
        }
        const list = this.recentIdx.m.get(alias) || [];
        const kmax = rc.k_max || 10;
        const take = list.filter((x) => x[0] >= 1 && x[0] <= kmax);
        const noun = rc.noun || '有意義變更';
        const sheetLabel = D.meta(rc.sheet) ? D.meta(rc.sheet).name : rc.sheet;
        if (!take.length) { body.innerHTML = `<p class="muted">（此設備沒有${U.esc(noun)}）</p>`; return; }
        const cols = rc.columns || DEFAULT.recent_changes.columns;
        // 空白（null／全空白字串）一律顯示「—」，與卡片欄位同規則
        const part = (v) => { v = U.raw(v); if (v == null) return '—'; const t = typeof v === 'number' ? U.cardValue(v) : String(v); return t.trim() === '' ? '—' : t; };
        const cellText = (r, c) => {
          if (c.cols) return c.cols.map((k) => part(r[k])).join(c.join != null ? c.join : ' ');
          const v = U.raw(r[c.col]);
          if (v == null || String(v).trim() === '') return '—';
          if (c.map) return c.map[String(v)] != null ? c.map[String(v)] : String(v);
          return c.fmt ? U.fmt(v, c.fmt) : part(v);
        };
        const hasColSrc = this.hasSrc && cols.some((c) => c.src);
        const thSrc = (c) => {
          if (!hasColSrc || !c.src) return '';
          const lvl = lvlOf(c.src.lvl); const lab = this.srcLabel(lvl);
          return ` <button type="button" class="src-chip th-src lvl-${lvl}" title="${U.esc(c.src.text)}" aria-label="${U.esc('來源：' + c.src.text)}" aria-controls="rc-src-${uid + 1}">${U.esc(lab)}</button>`;
        };
        let html = `<div class="tbl-scroll"><table class="mini"><thead><tr><th>k</th>${cols.map((c) => `<th${c.title ? ` title="${U.esc(c.title)}"` : ''}>${U.esc(c.label)}${thSrc(c)}</th>`).join('')}</tr></thead><tbody>`;
        for (const [k, i] of take) {
          const r = j.rows[i];
          html += `<tr><td class="ac"><a class="lk" href="${sheetHref(rc.sheet, { r: i })}" title="在 ${U.esc(sheetLabel)} 開啟此列">${U.esc(k)}</a></td>${cols.map((c, ci) => {
            const t = U.visible(cellText(r, c), true);
            if (c.map) {
              const hot = c.warn_eq != null && U.text(r[c.col]) === String(c.warn_eq);
              return `<td class="nowrap"><span class="pill ${hot ? 'bad' : 'plain'}">${U.esc(t)}</span></td>`;
            }
            return `<td${ci === 0 ? ' class="nowrap"' : ''}>${U.esc(t)}</td>`;
          }).join('')}</tr>`;
        }
        html += '</tbody></table></div>';
        const more = list.length > kmax ? `共 ${U.int(list.length)} 筆${U.esc(noun)}，顯示最新 ${kmax} 筆。` : `共 ${U.int(list.length)} 筆${U.esc(noun)}。`;
        const ac = this.findAliasCol(j, rc);
        const fl = ac != null ? sheetHref(rc.sheet, { f: { [ac]: '=' + alias } }) : U.esc('#/s/' + encodeURIComponent(rc.sheet) + '?q=' + encodeURIComponent(alias + '#'));
        html += `<p class="muted small">${more} <a class="lk" href="${fl}">在 ${U.esc(sheetLabel)} 查看此設備全部${U.esc(noun)} ›</a></p>`;
        if (hasColSrc) {
          const id = 'rc-src-' + (++uid);
          html += `<dl class="rc-src" id="${id}">${cols.filter((c) => c.src).map((c) => {
            const lvl = lvlOf(c.src.lvl); const lab = this.srcLabel(lvl); const t = String(c.src.text || '');
            return `<dt>${U.esc(c.label)}</dt><dd><span class="src-chip lvl-${lvl}">${U.esc(lab)}</span> ${U.esc(t.startsWith(lab + ' · ') ? t.slice(lab.length + 3) : t)}</dd>`;
          }).join('')}</dl>`;
        }
        body.innerHTML = html;
        body.querySelectorAll('.th-src').forEach((b) => b.addEventListener('click', () => { const on = s.classList.toggle('show-src'); body.querySelectorAll('.th-src').forEach((x) => x.setAttribute('aria-expanded', String(on))); }));
      }).catch((e) => { body.innerHTML = `<p class="muted">無法載入 ${U.esc(D.meta(rc.sheet) ? D.meta(rc.sheet).name : rc.sheet)}：${U.esc(e.message)}</p>`; });
      return s;
    }
    findAliasCol(j, rc) {
      if (rc && rc.alias_col != null) return rc.alias_col;
      const sid = (rc && rc.sheet) || '08';
      const lk = (this.spec.links || []).find((x) => x.sheet === sid && !x.self && !x.param);
      if (lk && lk.match_col != null) return lk.match_col;
      if (j.ui && j.ui.alias_col != null) return j.ui.alias_col;
      const i = (j.columns || []).findIndex((c) => /設備別名/.test(c.label));
      return i >= 0 ? i : null;
    }

    /* ---------- 參數現值 ---------- */
    renderParams(row) {
      const s = U.h('section', { class: 'csec params' });
      const lk = (this.spec.links || []).find((x) => x.param) || DEFAULT.links[1];
      const p = lk.param;
      if (!row) return s;
      const sheetName = U.text(row[p.sheet_col]);
      const dg = Number(U.raw(row[p.row_col])); const n = Number(U.raw(row[p.count_col])) || 0;
      if (!sheetName || !n) {
        s.appendChild(U.h('h2', { class: 'csec-h' }, '參數現值'));
        s.appendChild(U.h('p', { class: 'muted' }, '此設備沒有 HART／FF 參數現值（無組態資料）。'));
        return s;
      }
      const sm = D.byName.get(sheetName) || D.meta(sheetName.slice(0, 2));
      const sid = sm ? sm.id : sheetName.slice(0, 2);
      const g0 = dg - this.dataFirstRow(sid);
      const det = U.h('details', { class: 'pdet' });
      det.appendChild(U.h('summary', {}, U.h('span', { class: 'csec-h inline' }, `參數現值（${sheetName}，${U.int(n)} 筆）`), U.h('span', { class: 'muted small' }, ' 點擊展開；只載入所需的分塊')));
      const box = U.h('div', { class: 'pbox' });
      det.appendChild(box);
      det.addEventListener('toggle', () => { if (det.open && !box.dataset.loaded) { box.dataset.loaded = '1'; this.loadParams(box, sid, g0, n, U.text(row[1])); } });
      s.appendChild(det);
      if (this.state && this.state.paramsOpen) det.open = true;
      return s;
    }
    async loadParams(box, sid, g0, n, alias) {
      box.innerHTML = '<div class="loading-inline"><div class="spinner sm"></div> 載入參數…</div>';
      try {
        let rows; let cols;
        if (D.isChunked(sid)) {
          const ch = D.chunked(sid);
          const k0 = ch.partOf(g0); const k1 = ch.partOf(g0 + n - 1);
          if (k0 == null) await ch.loadAll(); else for (let k = k0; k <= k1; k++) await ch.ensurePart(k);
          rows = ch.rows.slice(g0, g0 + n); cols = ch.sheet.columns;
        } else {
          const j = await D.loadSheet(sid); rows = j.rows.slice(g0, g0 + n); cols = j.columns;
        }
        if (this.destroyed) return;
        const ok = rows.length && rows.every((r) => r && U.text(r[1]) === alias);
        let show = cols.map((c, i) => i).filter((i) => i > 1 && !(cols[i].hidden));
        if (U.isMobile()) {
          // 手機：參數與現值排在最前面、去掉每列都相同的「型號」（已在 1. 識別顯示），否則要橫捲 750px 才看得到值（M9）
          const pri = ['參數', 'FF 標準名稱', '參數(item:member)', '參數 (ParamName 基底 / item:member)', '現值', '解碼值', '解碼值(碼表)', '中文名稱', '參數中文名稱', '最後記錄(台灣)', '最後記錄時間(台灣)'];
          const rank = (i) => { const k = pri.indexOf(cols[i].label); return k < 0 ? pri.length + i : k; };
          show = show.filter((i) => cols[i].label !== '型號').sort((a, b) => rank(a) - rank(b));
        }
        const head = `<div class="ptools"><input type="search" class="pq" placeholder="篩選參數（名稱、中文、值…）" aria-label="篩選參數"><span class="pcount muted"></span>
          <a class="lk" href="${sheetHref(sid, { r: g0, f: { 1: '=' + alias } })}">在 ${U.esc(D.meta(sid) ? D.meta(sid).name : sid)} 開啟（篩選此設備）›</a></div>
          ${ok ? '' : '<p class="warn-text">注意：參數起始列與設備別名不一致，資料可能不同步。</p>'}`;
        box.innerHTML = head + '<div class="tbl-scroll ptable"></div>';
        const tbl = box.querySelector('.ptable');
        const render = (q) => {
          const qq = (q || '').toLowerCase();
          let cnt = 0;
          let html = `<table class="mini"><thead><tr><th>#</th>${show.map((i) => `<th title="${U.esc(cols[i].note || '')}">${U.esc(cols[i].label)}</th>`).join('')}</tr></thead><tbody>`;
          rows.forEach((r, k) => {
            if (!r) return;
            if (qq && !show.some((i) => U.text(r[i]).toLowerCase().includes(qq))) return;
            cnt++;
            html += `<tr><td class="ar muted"><a class="lk soft" href="${sheetHref(sid, { r: g0 + k })}">${k + 1}</a></td>${show.map((i) => {
              const v = r[i]; const raw = U.raw(v);
              const txt = U.isBlank(raw) ? '' : (U.isFltMin(raw) ? '未使用' : U.display(v, cols[i].fmt));
              const ws = typeof raw === 'string' && raw.trim() === '' && raw.length ? ' ws' : '';
              return `<td class="${typeof raw === 'number' ? 'ar' : ''}${ws}">${U.esc(U.visible(txt))}</td>`;
            }).join('')}</tr>`;
          });
          html += '</tbody></table>';
          tbl.innerHTML = html;
          box.querySelector('.pcount').textContent = `${U.int(cnt)} / ${U.int(rows.length)} 筆`;
        };
        render('');
        box.querySelector('.pq').addEventListener('input', U.debounce((e) => render(e.target.value), 200));
      } catch (e) {
        box.innerHTML = `<p class="muted">無法載入參數：${U.esc(e.message)}</p>`;
        delete box.dataset.loaded;
      }
    }
    onTheme() { if (this.spec) this.run(this.lastQuery); }
    destroy() {
      this.destroyed = true;
      if (this.ro) { this.ro.disconnect(); this.ro = null; }
      window.removeEventListener('beforeprint', this._bp);
      window.removeEventListener('afterprint', this._ap);
    }
  }
  AMS.CardView = CardView;
})();
