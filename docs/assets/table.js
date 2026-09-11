/* AMS 解析網頁 — table 模式：虛擬捲動、凍結欄、色帶、排序、篩選、facet、欄位選擇、CSV、列詳情、分塊漸進載入 */
'use strict';
(function () {
  const AMS = window.AMS;
  const U = AMS.U;
  const D = AMS.data;
  const DENSITY = { 1: 26, 3: 62 };
  AMS.viewState = AMS.viewState || {};

  const BLANK_TOKEN = '∅';
  const FILTER_HELP = '篩選語法：文字＝包含；=值 完全相符；!值 不包含；^值 開頭；>10、<=5 數值比較；∅ 空白；!∅ 非空白';

  /* ------------------------------------------------------------ 篩選運算式 */
  function numOf(v) {
    if (typeof v === 'number') return v;
    if (typeof v === 'string' && /^\s*-?\d+(\.\d+)?(e[-+]?\d+)?\s*$/i.test(v)) return Number(v);
    return NaN;
  }
  function compileFilter(str) {
    const s = String(str || '').trim();
    if (!s) return null;
    if (s === BLANK_TOKEN || s === '(空白)') return (v) => U.isBlank(U.raw(v));
    if (s === '!' + BLANK_TOKEN || s === '(非空白)') return (v) => !U.isBlank(U.raw(v));
    let m;
    if ((m = /^(>=|<=|>|<|==)\s*(-?\d+(?:\.\d+)?)$/.exec(s))) {
      const op = m[1]; const x = Number(m[2]);
      return (v) => { const n = numOf(U.raw(v)); if (isNaN(n)) return false; return op === '>' ? n > x : op === '<' ? n < x : op === '>=' ? n >= x : op === '<=' ? n <= x : n === x; };
    }
    if (s.length > 1 && s[0] === '"' && s[s.length - 1] === '"') { const t = s.slice(1, -1).toLowerCase(); return (v) => U.text(v).toLowerCase().includes(t); }
    if (s[0] === '=') { const t = s.slice(1).toLowerCase(); return (v) => U.text(v).toLowerCase() === t; }
    if (s[0] === '!') { const t = s.slice(1).toLowerCase(); return (v) => !U.text(v).toLowerCase().includes(t); }
    if (s[0] === '^') { const t = s.slice(1).toLowerCase(); return (v) => U.text(v).toLowerCase().startsWith(t); }
    const t = s.toLowerCase();
    return (v) => U.text(v).toLowerCase().includes(t);
  }
  AMS.compileFilter = compileFilter;

  /* ------------------------------------------------------------ CSV 欄位
   * Excel 開啟 CSV 時會把「002」「00020002」變成數字、「800204e6」變成 8.00E+206、「10/21/2025 14:03」變成日期：
   * 這類識別碼字串輸出為 ="…"（只含數字／字母／日期符號，不會形成有害公式）；「↗」連結欄輸出目標網址（ENG-08） */
  const CSV_PROTECT = [
    /^0\d+$/, // 前導零
    /^\d+[eE][+-]?\d+$/, // 看起來像科學記號（十六進位 item id）
    /^\d{16,}$/, // 超過 15 位數會失真
    /^\d{1,4}([-/])\d{1,2}(?:\1\d{1,4})?(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$/, // 日期（1-2、10/21、2025-10-21 14:03）
    /^\d{1,4}\.\d{1,2}\.\d{1,4}$/, // 日期（2025.10.21）
    /^\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/, // 時間
  ];
  function csvField(v, base) {
    const raw = U.raw(v);
    if (v && typeof v === 'object' && v.l && typeof raw === 'string' && /^[↗→↘]$/.test(raw.trim())) {
      const h = AMS.linkHref(v.l); return h ? U.csvCell(base + h) : '';
    }
    if (typeof raw === 'string' && CSV_PROTECT.some((re) => re.test(raw))) return '"=""' + raw + '"""';
    return U.csvCell(raw);
  }

  /* ------------------------------------------------------------ 排序鍵 */
  const NUMRE = /^\s*-?\d+(\.\d+)?\s*$/;
  function natKey(s) { return s.toLowerCase().replace(/\d+/g, (d) => d.replace(/^0+(?=\d)/, '').padStart(14, '0')); }

  class TableView {
    constructor(root, meta, route) {
      this.root = root; this.meta = meta; this.id = meta.id;
      this.chunked = D.isChunked(this.id);
      this.state = AMS.viewState[this.id] || (AMS.viewState[this.id] = {});
      this.tok = 0; this.destroyed = false;
      this.rs = -1; this.re = -1; this.c0 = -1; this.c1 = -1;
      this.sel = null; this.target = null;
      this.hay = null; this.keyCache = new Map(); this.cssCache = new Map();
      this.pendingRoute = route;
      this.buildShell();
      if (meta._data) { this.synthetic = true; this.init(meta._data); return; }
      this.load();
    }

    /* ---------- 載入 ---------- */
    async load() {
      const route = this.pendingRoute;
      const r = route && route.params.get('r');
      try {
        if (this.chunked) {
          const ch = D.chunked(this.id);
          this.ch = ch;
          let first = 0;
          if (r != null && r !== '') { const k = ch.partOf(Number(r)); if (k != null) first = k; }
          this.showLoading('正在載入第 1 部分…');
          this.unsub = ch.on((ev) => this.onChunk(ev));
          await ch.ensurePart(first);
          if (this.destroyed) return;
          this.init(ch.asJSON());
          this.loadRest(first);
        } else {
          this.showLoading('載入中…');
          const j = await D.loadSheet(this.id, (f) => this.setLoadFrac(f));
          if (this.destroyed) return;
          this.init(j);
        }
      } catch (e) { this.showError(e); }
    }
    /** 其餘分塊：某一塊失敗時其他塊照常載入；結束後若有失敗，載入列改為常駐警告＋重試（ROB-4） */
    loadRest(first) {
      this.loadFailed = false;
      this.updateLoadUI();
      this.ch.loadAll(first).catch((e) => {
        console.error(e);
        if (this.destroyed) return;
        this.loadFailed = true;
        this.updateLoadUI();
        U.toast('部分資料載入失敗：' + (e && e.message), 5000);
      });
    }
    onChunk(ev) {
      if (this.destroyed || !this.data) { if (ev.type === 'progress') this.updateLoadUI(); return; }
      if (ev.type === 'progress' || ev.type === 'error') { this.updateLoadUI(); return; }
      if (ev.type === 'part' || ev.type === 'done') {
        this.data.rows = this.ch.rows;
        this.styles = this.ch.styles.map((s) => U.parseStyleStr(s));
        this.rowStyles = this.ch.rowStyles; this.cellStyles = this.ch.cellStyles; this.bars = this.ch.bars;
        this.rebuildLoaded();
        this.keyCache.clear();
        this.computeZebra();
        this.facetDirty = true;
        this.updateLoadUI();
        this.scheduleRefresh();
      }
    }
    scheduleRefresh() {
      if (this._rt) return;
      this._rt = setTimeout(() => { this._rt = 0; this.refresh({ keepScroll: true }); if (this.facetDirty) { this.facetDirty = false; this.computeFacets(); this.renderHead(); } }, 60);
    }
    rebuildLoaded() {
      if (!this.chunked) { const n = this.data.rows.length; const a = new Int32Array(n); for (let i = 0; i < n; i++) a[i] = i; this.loaded = a; return; }
      const parts = this.ch.parts.filter((p) => p.loaded).sort((a, b) => a.offset - b.offset);
      let n = 0; parts.forEach((p) => { n += p.rows; });
      const a = new Int32Array(n); let k = 0;
      parts.forEach((p) => { for (let i = 0; i < p.rows; i++) a[k++] = p.offset + i; });
      this.loaded = a;
    }

    /* ---------- 初始化 ---------- */
    init(j) {
      this.data = j;
      const cols = (this.cols = j.columns || []);
      this.ncol = cols.length;
      this.total = this.chunked ? (this.ch.total || this.meta.rows || j.rows.length) : j.rows.length;
      if (this.chunked) {
        this.styles = this.ch.styles.map((s) => U.parseStyleStr(s));
        this.rowStyles = this.ch.rowStyles; this.cellStyles = this.ch.cellStyles; this.bars = this.ch.bars;
      } else {
        this.styles = (j.styles || []).map((s) => U.parseStyleStr(s));
        this.rowStyles = new Map((j.row_styles || []).map((e) => [e[0], e[1]]));
        this.cellStyles = new Map();
        (j.cell_styles || []).forEach((e) => this.cellStyles.set(e[0] * this.ncol + e[1], e[2]));
        this.bars = new Map();
        (j.bars || []).forEach((e) => this.bars.set(e[0] * this.ncol + e[1], [e[2], e[3]]));
      }
      this.ui = j.ui || {};
      this.summary = Array.isArray(this.ui.summary_rows) && this.ui.summary_rows.length ? new Set(this.ui.summary_rows) : null;
      this.presets = Array.isArray(this.ui.presets) ? this.ui.presets.filter((p) => p && p.col >= 0 && p.col < (j.columns || []).length) : [];
      this.facets = new Set((this.ui.facets || []).concat(this.ui.facets_extra || []).filter((c) => c >= 0 && c < this.ncol));
      // 欄層級資料橫條（03 CP 等）
      this.colBars = cols.map((c) => (c.bar && typeof c.bar === 'object' ? c.bar : null));
      // 欄層級 bg/fc：深色 bg（需白字）視為表頭色；淺色 bg 視為資料欄底色（如填寫欄 #FFFFE0）
      // （擷取器以 hbg/hfc 表示表頭色時，bg/fc 一律是資料欄層級）
      const hasH = (c) => c.hbg !== undefined || c.hfc !== undefined;
      this.colDataBg = cols.map((c) => (c.data_bg || (hasH(c) ? c.bg || null : (c.bg && U.lum(c.bg) > 0.5 ? c.bg : null))));
      this.colDataFc = cols.map((c) => (c.data_fc || (hasH(c) ? c.fc || null : (c.fc && U.lum(c.fc) < 0.8 ? c.fc : null))));
      this.colHeadBg = cols.map((c) => (c.hbg || c.head_bg || (!hasH(c) && c.bg && U.lum(c.bg) <= 0.5 ? c.bg : null)));
      this.colHeadFc = cols.map((c) => (c.hfc || null));
      this.firstRow = j.data_first_row || this.meta.data_first_row || 5;
      this.order = {};
      const ord = this.ui.order || {};
      for (const k in ord) { const m = new Map(); (ord[k] || []).forEach((v, i) => m.set(String(v), i)); this.order[k] = m; }
      // 欄位顯示狀態
      if (!this.state.hidden) this.state.hidden = cols.map((c, i) => (c.hidden ? i : -1)).filter((i) => i >= 0);
      if (!this.state.widths) this.state.widths = {};
      if (this.state.q == null) this.state.q = '';
      if (!this.state.f) this.state.f = {};
      if (this.state.showFilters == null) this.state.showFilters = !U.isMobile();
      if (this.state.showNotes == null) this.state.showNotes = !U.isMobile() && cols.some((c) => c.note);
      if (!this.state.density) this.state.density = 1;
      this.applyRoute(this.pendingRoute, true);
      this.rebuildLoaded();
      this.computeZebra();
      this.computeFacets();
      this.computeAutoWidths();
      this.renderHeader();
      this.buildTable();
      this.refresh({ first: true });
    }
    applyRoute(route, initial) {
      if (!route) return;
      const p = route.params;
      const has = (k) => p.has(k);
      const r = p.get('r');
      const rn = r != null && /^\s*\d+\s*$/.test(r) ? Number(r) : null; // 只接受非負整數（r=abc、r=-5 → 忽略）
      if (has('q') || has('f') || has('sort') || rn != null) {
        this.state.q = p.get('q') || '';
        let f = {};
        if (has('f')) { try { f = JSON.parse(p.get('f')); } catch (e) { f = {}; } }
        this.state.f = this.cleanFilters(f);
        if (has('sort')) {
          const m = /^(\d+):(a|d)$/.exec(p.get('sort'));
          this.state.sort = m && +m[1] < this.ncol ? { c: +m[1], dir: m[2] === 'd' ? -1 : 1 } : null;
        } else if (!initial) this.state.sort = this.state.sort || null;
      }
      this.target = rn;
      if (this.target != null && this.chunked && this.ch) {
        const k = this.ch.partOf(this.target);
        if (k != null && !this.ch.parts[k].loaded) this.ch.ensurePart(k).catch(() => {});
      }
    }
    /** 網址的 f：只保留「欄號或欄名 → 字串」；其他型別（陣列、數字、物件值、__proto__…）一律丟棄 */
    cleanFilters(f) {
      const out = {};
      if (!f || typeof f !== 'object' || Array.isArray(f)) return out;
      for (const k of Object.keys(f)) {
        const v = f[k];
        if (typeof v !== 'string' && typeof v !== 'number') continue;
        const c = /^\d+$/.test(k) ? Number(k) : this.cols.findIndex((col) => col.label === k); // 欄名鍵：01 KPI 連結用
        if (!(c >= 0 && c < this.ncol)) continue;
        const s = String(v);
        if (s) out[c] = s;
      }
      return out;
    }
    /** 同一工作表內的路由變更（連結跳轉到同表另一列等） */
    update(route) {
      this.pendingRoute = route;
      if (!this.data) return;
      this.applyRoute(route, false);
      this.syncInputs();
      this.refresh({ sync: true });
    }

    computeZebra() {
      const gc = this.ui.group_col;
      if (gc == null || !this.ui.group_zebra) { this.zebra = null; return; }
      const rows = this.data.rows;
      const n = this.total;
      const z = this.zebra && this.zebra.length === n ? this.zebra : new Uint8Array(n);
      let prev; let par = 1; let started = false;
      for (let g = 0; g < n; g++) {
        const r = rows[g];
        if (!r) continue;
        const v = U.text(r[gc]);
        if (!started || v !== prev) { par ^= 1; prev = v; started = true; }
        z[g] = par;
      }
      this.zebra = z;
      this.zebraColor = this.ui.group_zebra;
    }
    computeFacets() {
      this.facetVals = new Map();
      const rows = this.data.rows; const L = this.loaded;
      const pre = this.ui.facet_values || {};
      for (const c of this.facets) {
        const m = new Map();
        const opts = (this.ui.facet_options || {})[c] || (this.ui.facet_options || {})[String(c)];
        const ordr = (this.ui.order || {})[c] || (this.ui.order || {})[String(c)];
        if (Array.isArray(ordr)) ordr.forEach((v) => m.set(String(v), 0));
        const pv = pre[c] || pre[String(c)];
        if (Array.isArray(pv)) pv.forEach((x) => { const v = Array.isArray(x) ? x[0] : x; m.set(v == null ? BLANK_TOKEN : String(v), 0); });
        let blanks = 0;
        const sum = this.summary;
        for (let i = 0; i < L.length; i++) {
          if (sum && sum.has(L[i])) continue; // 小計／總計列不計入 facet 筆數
          const v = rows[L[i]][c];
          if (U.isBlank(U.raw(v))) { blanks++; continue; }
          const t = U.text(v);
          m.set(t, (m.get(t) || 0) + 1);
        }
        if (Array.isArray(opts)) opts.forEach((v) => { if (!m.has(String(v))) m.set(String(v), 0); });
        if (blanks) m.set(BLANK_TOKEN, blanks);
        this.facetVals.set(c, m);
      }
    }

    /* ---------- 版面 ---------- */
    buildShell() {
      const m = this.meta;
      this.root.innerHTML = '';
      this.root.className = 'view table-view';
      this.head = U.h('header', { class: 'sv-head' });
      this.head.innerHTML = `<div class="sv-crumb"><span class="mode-badge">表格</span> ${U.esc(m.group || '')}</div><h1 class="sv-title">${U.esc(m.name)}</h1>`;
      this.body = U.h('div', { class: 'tv-bodywrap' });
      this.root.append(this.head, this.body);
    }
    showLoading(msg) {
      this.body.innerHTML = `<div class="loading-box"><div class="spinner"></div><p class="lb-msg">${U.esc(msg)}</p><div class="lb-bar"><div></div></div></div>`;
    }
    setLoadFrac(f) { const b = this.body.querySelector('.lb-bar > div'); if (b) b.style.width = Math.round(f * 100) + '%'; }
    showError(e) {
      console.error(e);
      const box = U.h('div', { class: 'error-box' });
      box.innerHTML = `<h2>無法載入資料</h2><p>${U.esc(e && e.message || String(e))}</p>`;
      const btn = U.h('button', { class: 'btn', type: 'button', onclick: () => { this.showLoading('重新載入…'); this.load(); } }, '重試');
      box.appendChild(btn);
      if (!this.data) { this.body.innerHTML = ''; this.body.appendChild(box); } else U.toast('部分資料載入失敗：' + (e && e.message));
    }
    renderHeader() {
      const j = this.data; const m = this.meta;
      const h = this.head;
      const title = j.title && j.title !== m.name ? `<div class="sv-subtitle">${U.esc(j.title)}</div>` : '';
      let notes = j.notes || [];
      if (typeof notes === 'string') notes = notes.split('｜');
      const notesHTML = notes.length
        ? `<details class="sv-notes"${this.state.notesOpen ? ' open' : ''}><summary>說明（${notes.length} 則）<span class="np">${U.esc(notes[0])}</span></summary><ul>${notes.map((n) => `<li>${U.esc(n)}</li>`).join('')}</ul></details>` : '';
      const hc = (j.header_cells || []).slice().sort((a, b) => ((a.r || 0) - (b.r || 0)) || ((a.c || 0) - (b.c || 0)));
      const hf = this.headerFacets(hc);
      const hcHTML = hc.length ? `<div class="sv-hcells">${hc.map((x, i) => this.headerCellHTML(x, hf[i])).join('')}</div>` : '';
      h.innerHTML = `<div class="sv-crumb"><span class="mode-badge">表格</span> ${U.esc(m.group || '')}<span class="sv-rows">· ${U.int(this.total)} 列 × ${this.ncol} 欄</span></div>
        <h1 class="sv-title">${U.esc(m.name)}</h1>${title}${hcHTML}${notesHTML}`;
      const det = h.querySelector('.sv-notes');
      if (det) det.addEventListener('toggle', () => { this.state.notesOpen = det.open; });
      if (!this._hcBound) {
        this._hcBound = true;
        // 07「高 155／中 386…」：表頭統計格可點 → 套用該 facet 篩選（ENG-07）
        h.addEventListener('click', (e) => {
          const b = e.target.closest('[data-hf]'); if (!b) return;
          const c = Number(b.dataset.hf); const fv = '=' + b.dataset.hv;
          if (this.state.f[c] === fv) delete this.state.f[c]; else this.state.f[c] = fv;
          this.target = null;
          this.refresh({ user: true }); this.renderHead();
        });
      }
    }
    /** 表頭統計格 → facet：文字格的值全都出現在同一個 facet 欄時，該文字格與緊鄰的數字格可點 */
    headerFacets(hc) {
      const out = hc.map(() => null);
      if (!this.facetVals || !this.facetVals.size) return out;
      const labels = hc.map((x, i) => ({ i, x, t: typeof x.v === 'string' ? x.v.trim() : null })).filter((o) => o.t && !o.x.l);
      if (labels.length < 2) return out;
      let col = null;
      for (const c of this.facets) {
        const m = this.facetVals.get(c);
        if (m && labels.every((o) => m.has(o.t))) { col = c; break; }
      }
      if (col == null) return out;
      labels.forEach((o) => {
        out[o.i] = { c: col, v: o.t };
        const nx = hc[o.i + 1];
        if (nx && typeof U.raw(nx.v) === 'number' && (nx.r || 0) === (o.x.r || 0) && (nx.c || 0) === (o.x.c || 0) + 1) out[o.i + 1] = { c: col, v: o.t };
      });
      return out;
    }
    headerCellHTML(x, hf) {
      let st = x.s;
      if (typeof st === 'number') st = this.styles[st] || (this.data.styles || [])[st];
      st = st ? U.parseStyleStr(st) : null;
      const v = x.v;
      let txt = U.esc(U.visible(U.display(v, x.f)));
      txt = AMS.cellLinkHTML(v && typeof v === 'object' ? v : null, txt, 'lk');
      if (x.l) txt = `<a class="lk" href="${U.esc(AMS.linkHref(x.l))}">${txt}</a>`;
      let css = '';
      if (st) {
        const a = U.adaptColors(st.bg, st.fc, U.theme());
        if (a.bg) css += `background:${a.bg};`; if (a.fc) css += `color:${a.fc};`;
        if (st.b) css += 'font-weight:700;'; if (st.i) css += 'font-style:italic;';
      }
      const cls = `hcell${st && st.bg ? ' has-bg' : ''}`;
      if (hf) {
        const on = this.state.f[hf.c] === '=' + hf.v;
        const lab = this.cols[hf.c] ? this.cols[hf.c].label : '';
        return `<button type="button" class="${cls} hbtn" style="${css}" data-hf="${hf.c}" data-hv="${U.esc(hf.v)}" aria-pressed="${on}" title="${U.esc(`篩選「${lab}」＝ ${hf.v}（再按一次取消）`)}">${txt}</button>`;
      }
      return `<span class="${cls}" style="${css}">${txt}</span>`;
    }

    buildTable() {
      const b = this.body; b.innerHTML = '';
      const j = this.data;
      // 附屬小表（上方）
      if (j.subgrid && j.subgrid_pos === 'above') b.appendChild(this.subgridBlock(true));
      // 工具列
      const tb = (this.toolbar = U.h('div', { class: 'tv-toolbar', role: 'toolbar', 'aria-label': '表格工具' }));
      tb.innerHTML = `
        <div class="tv-search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
          <input type="search" class="tv-q" placeholder="搜尋此表（所有欄位）" aria-label="搜尋此表" spellcheck="false"></div>
        <span class="tv-count" aria-live="polite"></span>
        <span class="tv-load" hidden role="status"><span class="tv-load-txt"></span><span class="tv-load-bar"><i></i></span><button type="button" class="btn xs" data-act="retry" hidden>重試</button></span>
        ${this.presets.length ? `<span class="tv-presets" role="group" aria-label="快速篩選">${this.presets.map((p, i) => `<button type="button" class="btn sm preset" data-act="preset" data-pi="${i}" aria-pressed="false" title="${U.esc(this.presetTip(p))}">${U.esc(p.label)}</button>`).join('')}</span>` : ''}
        <span class="tv-spacer"></span>
        <div class="tv-actions">
          <button type="button" class="btn sm" data-act="filters" aria-pressed="false" title="顯示／隱藏逐欄篩選列">逐欄篩選</button>
          <button type="button" class="btn sm" data-act="notes" aria-pressed="false" title="顯示／隱藏欄位來源註記列（Excel 第 3 列）">來源註記</button>
          <button type="button" class="btn sm" data-act="cols" aria-haspopup="dialog" title="欄位顯示／隱藏">欄位 <span class="tv-colcount"></span></button>
          <button type="button" class="btn sm" data-act="density" title="切換單行／多行列高">多行</button>
          <button type="button" class="btn sm" data-act="clear" title="清除搜尋、篩選與排序">清除</button>
          <button type="button" class="btn sm primary" data-act="csv" title="匯出目前篩選結果（可見欄位）為 CSV">匯出 CSV</button>
        </div>`;
      b.appendChild(tb);
      this.chips = U.h('div', { class: 'tv-chips', hidden: true });
      b.appendChild(this.chips);
      // 捲動區
      const sc = (this.sc = U.h('div', { class: 'tv-scroll', tabindex: '0', role: 'grid', 'aria-label': this.meta.name, 'aria-rowcount': String(this.total) }));
      this.canvas = U.h('div', { class: 'tv-canvas' });
      this.hd = U.h('div', { class: 'tv-head', role: 'rowgroup' });
      this.bd = U.h('div', { class: 'tv-body', role: 'rowgroup' });
      this.win = U.h('div', { class: 'tv-win' });
      this.bd.appendChild(this.win);
      this.empty = U.h('div', { class: 'tv-empty', hidden: true }, '沒有符合條件的列');
      this.canvas.append(this.hd, this.bd, this.empty);
      if (j.subgrid && j.subgrid_pos !== 'above') { this.after = this.subgridBlock(false); this.canvas.appendChild(this.after); }
      sc.appendChild(this.canvas);
      b.appendChild(sc);
      // 事件
      this.qInput = tb.querySelector('.tv-q');
      this.qInput.value = this.state.q || '';
      const onQ = U.debounce(() => { this.state.q = this.qInput.value; this.target = null; this.refresh({ user: true }); }, 250);
      this.qInput.addEventListener('input', onQ);
      tb.addEventListener('click', (e) => { const btn = e.target.closest('button[data-act]'); if (btn) this.action(btn.dataset.act, btn); });
      sc.addEventListener('scroll', () => this.onScroll(), { passive: true });
      this.win.addEventListener('click', (e) => this.onRowClick(e));
      this.hd.addEventListener('click', (e) => this.onHeadClick(e));
      this.hd.addEventListener('input', (e) => this.onFilterInput(e));
      this.hd.addEventListener('change', (e) => this.onFilterInput(e, true));
      this.hd.addEventListener('pointerdown', (e) => this.onResizeStart(e));
      sc.addEventListener('keydown', (e) => this.onKey(e));
      this.ro = new ResizeObserver(() => { this.layoutCols(); this.renderHead(); this.renderRows(true); this.sizeAfter(); });
      this.ro.observe(sc);
      this.chips.addEventListener('click', (e) => {
        const x = e.target.closest('[data-rmf]');
        if (x) { const c = x.dataset.rmf; if (c === 'q') { this.state.q = ''; this.qInput.value = ''; } else delete this.state.f[c]; this.refresh({ user: true }); this.renderHead(); }
      });
      this.syncToolbar();
      this.layoutCols();
      this.renderHead();
      this.updateLoadUI();
    }
    subgridBlock(above) {
      const j = this.data;
      const sg = j.subgrid || {};
      // 標題：subgrid.title，否則取第一個文字儲存格（如 19「側表：測試定義 testdef（轉置）…」、09「方法小計（…）」）
      let title = sg.title || sg.name || '';
      if (!title) {
        for (const row of sg.rows || []) {
          const c = (row.cells || []).find((x) => typeof U.raw(x.v) === 'string' && U.raw(x.v).trim());
          if (c) { title = String(U.raw(c.v)).trim(); break; }
        }
      }
      if (!title) title = '附表';
      // 上方的高附表（19 共 46 列）預設收合，避免把主表擠到畫面外；狀態記在 viewState
      const tall = (sg.max_row || (sg.rows || []).length) > 14;
      const key = above ? 'subOpenA' : 'subOpenB';
      const open = this.state[key] != null ? this.state[key] : !(above && tall);
      const det = U.h('details', { class: 'tv-subgrid' + (above ? ' above' : ' below') + (tall ? ' tall' : ''), open });
      det.addEventListener('toggle', () => { this.state[key] = det.open; });
      det.appendChild(U.h('summary', {}, U.h('span', { class: 'sg-kind' }, above ? '附表（資料表上方）' : '附表（資料表下方）'), ' ', title));
      const wrap = U.h('div', { class: 'tv-subgrid-body' });
      det.appendChild(wrap);
      try { AMS.GridView.renderStatic(j.subgrid, wrap); } catch (e) { wrap.textContent = '附表無法顯示：' + e.message; }
      return det;
    }
    sizeAfter() { if (this.after && this.sc) this.after.style.width = this.sc.clientWidth + 'px'; }
    syncToolbar() {
      const tb = this.toolbar; if (!tb) return;
      const s = this.state;
      const set = (act, on, txt) => { const b = tb.querySelector(`[data-act="${act}"]`); if (b) { b.setAttribute('aria-pressed', on ? 'true' : 'false'); if (txt) b.textContent = txt; } };
      set('filters', s.showFilters); set('notes', s.showNotes);
      set('density', s.density === 3, s.density === 3 ? '單行' : '多行');
      const nb = tb.querySelector('[data-act="notes"]'); if (nb) nb.hidden = !this.cols.some((c) => c.note);
      const hid = new Set(s.hidden);
      const cc = tb.querySelector('.tv-colcount'); if (cc) cc.textContent = `${this.ncol - hid.size}/${this.ncol}`;
    }
    syncInputs() {
      if (this.qInput) this.qInput.value = this.state.q || '';
      this.renderHead();
    }
    updateLoadUI() {
      if (!this.toolbar || !this.chunked) return;
      const el = this.toolbar.querySelector('.tv-load');
      const ch = this.ch;
      const done = ch.allLoaded();
      el.hidden = done;
      const nLoaded = ch.parts.filter((p) => p.loaded).length;
      const failed = this.loadFailed ? ch.failedParts() : [];
      el.classList.toggle('bad', failed.length > 0);
      el.querySelector('.tv-load-txt').textContent = failed.length
        ? `第 ${failed.map((k) => k + 1).join('、')} 部分載入失敗 · 已載入 ${U.int(ch.loadedRows)} / ${U.int(this.total)} 列（篩選、排序、CSV 只含已載入的列）`
        : `載入 ${nLoaded}/${ch.n} 部分 · ${U.int(ch.loadedRows)} / ${U.int(this.total)} 列`;
      el.querySelector('.tv-load-bar > i').style.width = Math.round(ch.progress() * 100) + '%';
      const rb = el.querySelector('[data-act="retry"]'); if (rb) rb.hidden = !failed.length;
      if (done && !this._doneToast) { this._doneToast = true; if (this.data) U.toast(`${this.meta.name}：${U.int(this.total)} 列全部載入完成`); }
    }

    /* ---------- 欄位幾何 ---------- */
    layoutCols() {
      const hid = new Set(this.state.hidden);
      const vcols = (this.vcols = []);
      for (let c = 0; c < this.ncol; c++) if (!hid.has(c)) vcols.push(c);
      const mobile = U.isMobile();
      const fzReq = this.data.freeze_cols || 0;
      let fz = vcols.filter((c) => c < fzReq).length;
      if (mobile) fz = Math.min(fz, 1);
      this.nfz = fz;
      const digits = String(Math.max(1, this.total + (this.firstRow || 5))).length;
      this.gw = Math.max(40, 14 + digits * 7.5);
      const xs = (this.xs = new Float64Array(vcols.length + 1));
      let x = this.gw;
      for (let k = 0; k < vcols.length; k++) { xs[k] = x; x += this.colW(vcols[k]); }
      xs[vcols.length] = x;
      this.W = x;
      this.fzW = this.nfz ? xs[this.nfz] : this.gw;
      this.canvas.style.width = this.W + 'px';
      this.win.style.width = this.W + 'px';
      this.rh = DENSITY[this.state.density] || 26;
      this.sc.style.setProperty('--rh', this.rh + 'px');
      this.sc.classList.toggle('multi', this.state.density === 3);
    }
    colW(c) {
      const w = this.state.widths[c];
      if (w) return w;
      const cw = this.cols[c].w;
      const base = cw ? Math.max(36, cw) : 100;
      const a = this.autoW ? this.autoW[c] : 0;
      return a > base ? a : base;
    }
    /** Excel 欄寬以 Calibri 計，網頁的中文字型較寬：短欄（問題編號 AUD-0001、嚴重度、協定 HART…）依表頭與前 200 列實測加寬，
     *  上限為 Excel 寬 ×1.4（最多 180px）；facet 欄至少 72px 讓下拉看得到值（ENG-04） */
    computeAutoWidths() {
      const cols = this.cols; const rows = this.data.rows; const L = this.loaded;
      let ctx = null;
      try { ctx = document.createElement('canvas').getContext('2d'); } catch (e) { ctx = null; }
      if (!ctx) { this.autoW = null; return; }
      const rs = getComputedStyle(document.documentElement);
      const font = rs.getPropertyValue('--font') || 'sans-serif';
      const mono = rs.getPropertyValue('--mono') || 'monospace';
      const cache = new Map();
      const meas = (f, t) => { const k = f + '' + t; let v = cache.get(k); if (v === undefined) { ctx.font = f; v = ctx.measureText(t).width; cache.set(k, v); } return v; };
      const n = Math.min(L ? L.length : 0, 200);
      const out = new Array(cols.length).fill(0);
      for (let c = 0; c < cols.length; c++) {
        const col = cols[c];
        const base = col.w ? Math.max(36, col.w) : 100;
        const cap = Math.min(Math.max(base * 1.4, base + 24), Math.max(base, 180));
        const hf = `700 12.5px ${font}`;
        const lw = meas(hf, String(col.label || ''));
        const headNeed = Math.min(lw, lw / 2 + 14) + 24; // 表頭最多兩行
        const df = col.mono ? `12px ${mono}` : `13px ${font}`;
        let dataNeed = 0;
        for (let i = 0; i < n; i++) {
          const row = rows[L[i]]; if (!row) continue;
          const v = row[c]; const raw = U.raw(v);
          if (U.isBlank(raw)) continue;
          let t = U.display(v, col.fmt);
          const nl = t.indexOf('\n'); if (nl >= 0) t = t.slice(0, nl);
          if (t.length > 40) continue; // 長文字本來就要截斷／看詳情
          const w = meas(df, t) + 14;
          if (w > dataNeed) dataNeed = w;
        }
        let a = Math.min(cap, Math.ceil(Math.max(headNeed, dataNeed)));
        if (this.facets.has(c)) a = Math.max(a, 72);
        out[c] = a > base ? a : 0;
      }
      this.autoW = out;
    }
    colWindow() {
      const sl = this.sc.scrollLeft; const cw = this.sc.clientWidth || 800;
      const xs = this.xs; const n = this.vcols.length;
      const lo = sl + this.fzW; const hi = sl + cw;
      let a = this.nfz; let b = n - 1;
      // 二分搜尋
      let L = this.nfz; let R = n - 1;
      while (L < R) { const m = (L + R) >> 1; if (xs[m + 1] <= lo) L = m + 1; else R = m; }
      a = Math.max(this.nfz, L - 2);
      L = a; R = n - 1;
      while (L < R) { const m = (L + R + 1) >> 1; if (xs[m] < hi) L = m; else R = m - 1; }
      b = Math.min(n - 1, L + 2);
      if (n === this.nfz) { a = n; b = n - 1; }
      return [a, b];
    }

    /* ---------- 表頭 ---------- */
    bandOf(c) {
      const bands = this.data.bands || [];
      for (let i = 0; i < bands.length; i++) if (c >= bands[i].from && c <= bands[i].to) return i;
      return -1;
    }
    renderHead() {
      if (!this.hd || !this.data) return;
      const [c0, c1] = this.colWindow();
      this.hc0 = c0; this.hc1 = c1;
      const V = this.vcols; const xs = this.xs;
      const bands = this.data.bands || [];
      const theme = U.theme();
      const s = this.state;
      const seg = (from, to, fz) => { // band segments over visible index range
        let out = ''; let k = from;
        while (k <= to) {
          const bi = this.bandOf(V[k]); let e = k;
          while (e + 1 <= to && this.bandOf(V[e + 1]) === bi) e++;
          const w = xs[e + 1] - xs[k];
          const b = bands[bi];
          let css = `width:${w}px;`;
          if (fz) css += `position:sticky;left:${xs[k]}px;z-index:4;`;
          if (b) { const a = U.adaptColors(b.bg, b.fc || '#FFFFFF', 'light'); css += `background:${a.bg};color:${a.fc || '#fff'};`; }
          out += `<div class="th band${fz ? ' fz' : ''}${fz && e === this.nfz - 1 ? ' fz-last' : ''}" style="${css}" title="${b ? U.esc(b.label) : ''}">${b ? U.esc(b.label) : ''}</div>`;
          k = e + 1;
        }
        return out;
      };
      const spacer = (c0 > this.nfz) ? `<div class="sp" style="width:${xs[c0] - xs[this.nfz]}px"></div>` : '';
      const gut = (cls, txt) => `<div class="th gut ${cls}" style="width:${this.gw}px">${txt || ''}</div>`;
      let html = '';
      if (bands.length) html += `<div class="hr hr-band">${gut('', '')}${seg(0, this.nfz - 1, true)}${spacer}${seg(c0, c1, false)}</div>`;
      // 欄名
      const colCell = (k, fz) => {
        const c = V[k]; const col = this.cols[c];
        const b = bands[this.bandOf(c)];
        const hb = this.colHeadBg[c];
        let bg = hb || (b && b.bg) || '#1F4E79'; let fc = this.colHeadFc[c] || (hb && col.fc && U.lum(col.fc) > 0.5 ? col.fc : ((b && b.fc) || '#FFFFFF'));
        const a = U.adaptColors(bg, fc, 'light');
        const srt = s.sort && s.sort.c === c ? (s.sort.dir > 0 ? ' asc' : ' desc') : '';
        const aria = srt ? (s.sort.dir > 0 ? 'ascending' : 'descending') : 'none';
        let css = `width:${this.colW(c)}px;background:${a.bg};color:${a.fc || '#fff'};`;
        if (fz) css += `position:sticky;left:${xs[k]}px;z-index:4;`;
        const tip = col.label + (col.note ? '\n來源：' + col.note : '') + '\n（點擊排序）';
        return `<div class="th col${fz ? ' fz' : ''}${fz && k === this.nfz - 1 ? ' fz-last' : ''}${srt}" role="columnheader" aria-sort="${aria}" data-c="${c}" style="${css}" title="${U.esc(tip)}"><span class="th-l">${U.esc(col.label)}</span><span class="th-s" aria-hidden="true"></span><span class="rsz" data-rsz="${c}" aria-hidden="true"></span></div>`;
      };
      let cells = ''; for (let k = 0; k < this.nfz; k++) cells += colCell(k, true);
      let cells2 = ''; for (let k = c0; k <= c1; k++) cells2 += colCell(k, false);
      html += `<div class="hr hr-col" role="row">${gut('corner" title="Excel 列號', '列')}${cells}${spacer}${cells2}</div>`;
      // 來源註記
      if (s.showNotes) {
        const noteCell = (k, fz) => {
          const c = V[k]; const col = this.cols[c];
          let css = `width:${this.colW(c)}px;`;
          if (fz) css += `position:sticky;left:${xs[k]}px;z-index:4;`;
          return `<div class="th note${fz ? ' fz' : ''}${fz && k === this.nfz - 1 ? ' fz-last' : ''}" style="${css}" title="${U.esc(col.note || '')}">${U.esc(col.note || '')}</div>`;
        };
        let a1 = ''; for (let k = 0; k < this.nfz; k++) a1 += noteCell(k, true);
        let a2 = ''; for (let k = c0; k <= c1; k++) a2 += noteCell(k, false);
        html += `<div class="hr hr-note">${gut('', '')}${a1}${spacer}${a2}</div>`;
      }
      // 篩選列
      if (s.showFilters) {
        const fcell = (k, fz) => {
          const c = V[k]; const col = this.cols[c];
          let css = `width:${this.colW(c)}px;`;
          if (fz) css += `position:sticky;left:${xs[k]}px;z-index:4;`;
          const val = s.f[c] || '';
          let inner;
          if (this.facets.has(c) && this.facetVals) {
            const m = this.facetVals.get(c) || new Map();
            // 有其他篩選時，筆數＝符合「其他」條件的列（排除本欄自己的條件）；0 筆的選項變淡
            const lm = this.facetLive ? this.facetLive.get(c) : null;
            let opts = `<option value="">全部</option>`;
            let found = !val;
            m.forEach((n0, v) => {
              const fv = v === BLANK_TOKEN ? BLANK_TOKEN : '=' + v;
              const sel = val === fv || (val.toLowerCase && val.toLowerCase() === fv.toLowerCase());
              if (sel) found = true;
              const n = lm ? (lm.get(v) || 0) : n0;
              const cnt = lm ? ' (' + U.int(n) + ')' : (n ? ' (' + U.int(n) + ')' : '');
              opts += `<option value="${U.esc(fv)}"${sel ? ' selected' : ''}${lm && !n ? ' class="zero"' : ''}>${U.esc(v === BLANK_TOKEN ? '（空白）' : U.visible(v))}${cnt}</option>`;
            });
            if (!found) opts += `<option value="${U.esc(val)}" selected>條件：${U.esc(val)}</option>`;
            inner = `<select class="fi${val ? ' on' : ''}" data-fc="${c}" aria-label="${U.esc(col.label)} 篩選">${opts}</select>`;
          } else {
            inner = `<input class="fi${val ? ' on' : ''}" data-fc="${c}" type="text" value="${U.esc(val)}" placeholder="篩選…" aria-label="${U.esc(col.label)} 篩選" spellcheck="false">`;
          }
          return `<div class="th filt${fz ? ' fz' : ''}${fz && k === this.nfz - 1 ? ' fz-last' : ''}" style="${css}">${inner}</div>`;
        };
        let a1 = ''; for (let k = 0; k < this.nfz; k++) a1 += fcell(k, true);
        let a2 = ''; for (let k = c0; k <= c1; k++) a2 += fcell(k, false);
        html += `<div class="hr hr-filt">${gut('fhelp', `<button type="button" class="fhelp-btn" data-fhelp aria-label="篩選語法說明" title="${U.esc(FILTER_HELP)}">?</button>`)}${a1}${spacer}${a2}</div>`;
      }
      // 保留焦點
      const act = document.activeElement;
      const focusC = act && act.dataset && act.dataset.fc != null && this.hd.contains(act) ? act.dataset.fc : null;
      const selStart = focusC != null && act.selectionStart != null ? act.selectionStart : null;
      this.hd.innerHTML = html;
      this.hd.style.width = this.W + 'px';
      if (focusC != null) {
        const el = this.hd.querySelector(`[data-fc="${focusC}"]`);
        if (el) { el.focus({ preventScroll: true }); if (selStart != null && el.setSelectionRange) try { el.setSelectionRange(selStart, selStart); } catch (e) { /**/ } }
      }
      this.headH = this.hd.offsetHeight;
      void theme;
    }

    /* ---------- 資料列 ---------- */
    rowNum(g) { return g + (this.firstRow || 5); }
    cellCss(g, c) {
      const rsi = this.rowStyles.size ? this.rowStyles.get(g) : undefined;
      const csi = this.cellStyles.size ? this.cellStyles.get(g * this.ncol + c) : undefined;
      const z = this.zebra && this.zebra[g] ? 1 : 0;
      const key = c + '|' + (rsi ?? '') + '|' + (csi ?? '') + '|' + z;
      let r = this.cssCache.get(key);
      if (r !== undefined) return r;
      const col = this.cols[c];
      let b = col.bold ? 1 : 0; let it = col.italic ? 1 : 0; let un = 0;
      let bg = this.colDataBg[c]; let fc = this.colDataFc[c];
      if (rsi !== undefined) { const s = this.styles[rsi] || {}; if (s.b) b = 1; if (s.i) it = 1; if (s.u) un = 1; if (s.bg) bg = s.bg; if (s.fc) fc = s.fc; }
      if (csi !== undefined) { const s = this.styles[csi] || {}; if (s.b) b = 1; if (s.i) it = 1; if (s.u) un = 1; if (s.bg) bg = s.bg; if (s.fc) fc = s.fc; }
      if (!bg && z) bg = this.zebraColor;
      const a = U.adaptColors(bg, fc, U.theme());
      let css = '';
      if (a.bg) css += `background:${a.bg};`;
      if (a.fc) css += `color:${a.fc};`;
      if (b) css += 'font-weight:700;';
      if (it) css += 'font-style:italic;';
      if (un) css += 'text-decoration:underline;';
      r = css;
      this.cssCache.set(key, r);
      return r;
    }
    rowBg(g) {
      const rsi = this.rowStyles.size ? this.rowStyles.get(g) : undefined;
      let bg = null;
      if (rsi !== undefined) { const s = this.styles[rsi]; if (s && s.bg) bg = s.bg; }
      if (!bg && this.zebra && this.zebra[g]) bg = this.zebraColor;
      if (!bg) return '';
      const a = U.adaptColors(bg, null, U.theme());
      return a.bg ? `--rb:${a.bg};` : '';
    }
    cellHTML(g, c, row, k, fz) {
      const col = this.cols[c];
      const v = row[c];
      const w = this.colW(c);
      const raw = U.raw(v);
      let cls = 'td';
      let align = col.align;
      if (!align) align = typeof raw === 'number' ? 'right' : (typeof raw === 'boolean' ? 'center' : null);
      if (align === 'right') cls += ' ar'; else if (align === 'center') cls += ' ac';
      if (col.mono) cls += ' mono';
      if (fz) cls += ' fz' + (k === this.nfz - 1 ? ' fz-last' : '');
      let css = `width:${w}px;` + (fz ? `left:${this.xs[k]}px;` : '') + this.cellCss(g, c);
      let inner = '';
      let title = '';
      if (!U.isBlank(raw)) {
        let txt = U.display(v, col.fmt);
        if (typeof raw === 'string' && raw.trim() === '') { cls += ' ws'; title = `（${raw.length} 個空白字元）`; }
        const vis = U.visible(txt, this.state.density === 3);
        if (!title && (txt.length * 7.2 > w - 8 || txt.includes('\n'))) title = txt;
        inner = U.esc(vis);
        if (v && typeof v === 'object' && (v.l || v.u)) inner = AMS.cellLinkHTML(v, inner, 'lk');
      }
      // 資料橫條
      let bar = null;
      if (this.bars.size) { const e = this.bars.get(g * this.ncol + c); if (e) bar = e; }
      if (!bar && this.colBars[c] && typeof raw === 'number') {
        const cb = this.colBars[c]; const mn = cb.min ?? 0; const mx = cb.max ?? 1;
        const p = mx > mn ? (raw - mn) / (mx - mn) : 1;
        bar = [U.clamp(p, 0, 1), cb.color || '#638EC6'];
      }
      // Excel 資料橫條（無 x14 擴充）：minLength 10%、maxLength 90% → 長度 = 10% + 80%·p
      if (bar) inner = `<i class="bar" style="width:${(10 + 80 * U.clamp(Number(bar[0]) || 0, 0, 1)).toFixed(1)}%;--bc:${U.esc(bar[1] || '#638EC6')}"></i><span class="bv">${inner}</span>`;
      return `<div class="${cls}" style="${css}" data-c="${c}"${title ? ` title="${U.esc(title)}"` : ''}>${inner}</div>`;
    }
    onScroll() {
      if (this._raf) return;
      this._raf = requestAnimationFrame(() => {
        this._raf = 0;
        const [c0, c1] = this.colWindow();
        if (c0 !== this.hc0 || c1 !== this.hc1) this.renderHead();
        this.renderRows(false);
      });
    }
    renderRows(force) {
      if (!this.view || !this.sc) return;
      const sc = this.sc; const RH = this.rh; const n = this.view.length;
      const st = sc.scrollTop; const vh = sc.clientHeight || 600;
      const headH = this.headH || 0;
      let s = Math.floor(st / RH) - 6; if (s < 0) s = 0;
      let e = Math.ceil((st + vh - headH) / RH) + 6; if (e > n) e = n;
      const [c0, c1] = this.colWindow();
      if (!force && s === this.rs && e === this.re && c0 === this.c0 && c1 === this.c1) return;
      this.rs = s; this.re = e; this.c0 = c0; this.c1 = c1;
      const V = this.vcols; const rows = this.data.rows; const xs = this.xs;
      const spacer = c0 > this.nfz ? `<div class="sp" style="width:${xs[c0] - xs[this.nfz]}px"></div>` : '';
      let html = '';
      for (let k = s; k < e; k++) {
        const g = this.view[k];
        const row = rows[g];
        if (!row) continue;
        let cls = 'tr';
        if (g === this.sel) cls += ' sel';
        if (g === this.target) cls += ' tg';
        html += `<div class="${cls}" role="row" aria-rowindex="${g + 1}" data-g="${g}" style="${this.rowBg(g)}"><div class="td gut" style="width:${this.gw}px">${this.rowNum(g)}</div>`;
        for (let q = 0; q < this.nfz; q++) html += this.cellHTML(g, V[q], row, q, true);
        html += spacer;
        for (let q = c0; q <= c1; q++) html += this.cellHTML(g, V[q], row, q, false);
        html += '</div>';
      }
      this.win.style.transform = `translateY(${s * RH}px)`;
      this.win.innerHTML = html;
    }
    renderAll() {
      this.bd.style.height = this.view.length * this.rh + 'px';
      this.empty.hidden = this.view.length > 0;
      this.renderHead();
      this.renderRows(true);
      this.sizeAfter();
    }

    /* ---------- 篩選／排序管線 ---------- */
    haystack(g) {
      let h = this.hay[g];
      if (h !== undefined) return h;
      const row = this.data.rows[g];
      const sc = this.searchCols;
      let s = '';
      for (let i = 0; i < sc.length; i++) {
        const c = sc[i]; const v = row[c];
        const raw = U.raw(v);
        if (U.isBlank(raw)) continue;
        const t = U.text(v);
        s += t + '\u0001';
        const f = (v && typeof v === 'object' && v.f) || this.cols[c].fmt;
        if (f && typeof raw !== 'string') { const d = U.display(v, this.cols[c].fmt); if (d !== t) s += d + '\u0001'; }
      }
      h = s.toLowerCase();
      this.hay[g] = h;
      return h;
    }
    async refresh(opt) {
      opt = opt || {};
      if (!this.data) return;
      // 使用者操作要寫回網址；若這次 refresh 被分塊到達的 refresh 取代，由最後完成的那次寫入（ENG-09）
      if (opt.user || opt.first || opt.sync) this._needSync = true;
      const tok = ++this.tok;
      const alive = () => tok === this.tok && !this.destroyed;
      const s = this.state;
      const preds = [];
      for (const k in s.f) {
        if (!Object.prototype.hasOwnProperty.call(s.f, k) || !/^\d+$/.test(k)) continue;
        const c = Number(k);
        if (!(c >= 0 && c < this.ncol)) continue;
        let fn = null;
        try { fn = compileFilter(s.f[k]); } catch (e) { fn = null; }
        if (fn) preds.push([c, fn]);
      }
      const q = (s.q || '').trim().toLowerCase();
      if (!this.hay) this.hay = [];
      this.searchCols = Array.isArray(this.ui.search_cols) && this.ui.search_cols.length ? this.ui.search_cols : this.cols.map((c, i) => i);
      const src = this.loaded; const rows = this.data.rows;
      let out;
      const big = src.length > 20000;
      if (big) this.setBusy(true);
      let live = null;
      if (!preds.length && !q) out = src;
      else {
        const buf = new Int32Array(src.length); let n = 0;
        const np = preds.length;
        // facet 筆數依「其他」篩選條件計算（每個 facet 排除自己那欄的條件；ENG-06）
        const fcols = this.facets.size ? Array.from(this.facets) : null;
        if (fcols) live = new Map(fcols.map((c) => [c, new Map()]));
        const sum = this.summary;
        const bump = (c, v) => { const m = live.get(c); const t = U.isBlank(U.raw(v)) ? BLANK_TOKEN : U.text(v); m.set(t, (m.get(t) || 0) + 1); };
        const ok = await U.chunked(src.length, (i) => {
          const g = src[i]; const row = rows[g];
          let fails = 0; let failC = -1;
          for (let p = 0; p < np; p++) {
            if (!preds[p][1](row[preds[p][0]])) { fails++; failC = preds[p][0]; if (!live || fails > 1) break; }
          }
          if (fails > 1 || (fails === 1 && !live)) return;
          if (q && this.haystack(g).indexOf(q) < 0) return;
          if (fails === 0) buf[n++] = g;
          if (live && !(sum && sum.has(g))) {
            if (fails === 0) { for (let x = 0; x < fcols.length; x++) bump(fcols[x], row[fcols[x]]); }
            else if (live.has(failC)) bump(failC, row[failC]);
          }
        }, alive);
        if (!ok) return;
        out = buf.subarray(0, n);
      }
      this.facetLive = live;
      if (s.sort && s.sort.c < this.ncol) {
        const keys = await this.sortKeys(s.sort.c, alive);
        if (!keys) return;
        await U.yieldMain(); if (!alive()) return;
        const { kind, num, str } = keys; const dir = s.sort.dir;
        const arr = Array.from(out);
        const sum = this.summary; // 15 的小計／總計列：排序時固定在最後、維持原順序
        arr.sort((a, b) => {
          if (sum) { const sa = sum.has(a); const sb = sum.has(b); if (sa || sb) return sa && sb ? a - b : sa ? 1 : -1; }
          const ka = kind[a]; const kb = kind[b];
          if (ka !== kb) { if (ka === 2) return 1; if (kb === 2) return -1; return (ka - kb) * dir || a - b; }
          if (ka === 2) return a - b;
          if (ka === 0) { const d = num[a] - num[b]; return d ? d * dir : a - b; }
          const sa = str[a]; const sb = str[b];
          return sa < sb ? -dir : sa > sb ? dir : a - b;
        });
        out = Int32Array.from(arr);
      }
      if (!alive()) return;
      if (big) this.setBusy(false);
      const prevTop = this.sc.scrollTop;
      this.view = out;
      this.updateCount();
      this.renderChips();
      this.bd.style.height = this.view.length * this.rh + 'px';
      this.empty.hidden = this.view.length > 0;
      if (this.target != null) {
        this.scrollToTarget();
      } else if (opt.user) {
        this.sc.scrollTop = 0;
      } else if (opt.first && this.state.scrollTop) {
        this.sc.scrollTop = this.state.scrollTop; this.sc.scrollLeft = this.state.scrollLeft || 0;
      } else if (opt.keepScroll) this.sc.scrollTop = prevTop;
      this.renderAll();
      if (this._needSync) { this._needSync = false; this.syncURL(); }
    }
    setBusy(on) { this.root.classList.toggle('busy', !!on); const c = this.toolbar && this.toolbar.querySelector('.tv-count'); if (c && on) c.textContent = '處理中…'; }
    async sortKeys(c, alive) {
      const ck = this.keyCache.get(c);
      if (ck && ck.n === this.loaded.length) return ck;
      const n = this.total;
      const kind = new Uint8Array(n).fill(2); const num = new Float64Array(n); const str = new Array(n);
      const rows = this.data.rows; const L = this.loaded;
      const om = this.order[c];
      // ui.sort_key {顯示欄: 排序鍵欄}：10「時間(台灣)」含「（占位 1970）」文字，改用 UTC 原值欄排序
      const sk = this.ui.sort_key || {};
      const kc = sk[c] != null ? Number(sk[c]) : (sk[String(c)] != null ? Number(sk[String(c)]) : c);
      const ok = await U.chunked(L.length, (i) => {
        const g = L[i]; const v = U.raw(rows[g][kc >= 0 && kc < this.ncol ? kc : c]);
        if (v === null || v === undefined || v === '') return;
        if (om) { const k = om.get(String(v)); if (k !== undefined) { kind[g] = 0; num[g] = k; return; } kind[g] = 1; str[g] = natKey(String(v)); return; }
        if (typeof v === 'number') { kind[g] = 0; num[g] = v; return; }
        if (typeof v === 'boolean') { kind[g] = 1; str[g] = v ? 'true' : 'false'; return; }
        const s = String(v);
        if (NUMRE.test(s)) { kind[g] = 0; num[g] = Number(s); return; }
        kind[g] = 1; str[g] = natKey(s);
      }, alive);
      if (!ok) return null;
      const r = { kind, num, str, n: L.length };
      this.keyCache.set(c, r);
      return r;
    }
    updateCount() {
      const el = this.toolbar.querySelector('.tv-count');
      const n = this.view.length; const tot = this.total;
      const loadedTxt = this.chunked && this.loaded.length < tot ? `（已載入 ${U.int(this.loaded.length)}）` : '';
      el.innerHTML = `顯示 <b>${U.int(n)}</b> / 總 ${U.int(tot)} 列${loadedTxt}`;
      this.sc.setAttribute('aria-rowcount', String(n));
    }
    /** ui.presets（08「只看有意義」「MOC 審查」）→ 逐欄篩選字串 */
    presetValue(p) { return p.nonempty ? '!' + BLANK_TOKEN : p.empty ? BLANK_TOKEN : p.eq != null ? '=' + p.eq : (p.filter || ''); }
    presetTip(p) { const col = this.cols ? this.cols[p.col] : (this.data.columns || [])[p.col]; return `快速篩選：「${col ? col.label : p.col}」${p.nonempty ? ' 非空白' : p.empty ? ' 空白' : p.eq != null ? ' ＝ ' + p.eq : ''}（再按一次取消）`; }
    syncPresets() {
      if (this.head) this.head.querySelectorAll('[data-hf]').forEach((b) => b.setAttribute('aria-pressed', String(this.state.f[b.dataset.hf] === '=' + b.dataset.hv)));
      if (!this.toolbar || !this.presets.length) return;
      this.toolbar.querySelectorAll('[data-act="preset"]').forEach((b) => { const p = this.presets[Number(b.dataset.pi)]; b.setAttribute('aria-pressed', String(!!p && this.state.f[p.col] === this.presetValue(p))); });
    }
    renderChips() {
      this.syncPresets();
      const s = this.state; const parts = [];
      if (s.q) parts.push(`<span class="chip">搜尋：${U.esc(s.q)}<button type="button" data-rmf="q" aria-label="移除搜尋">×</button></span>`);
      for (const k in s.f) {
        if (!s.f[k] || !Object.prototype.hasOwnProperty.call(s.f, k) || !/^\d+$/.test(k)) continue;
        const col = this.cols[k]; if (!col) continue;
        parts.push(`<span class="chip">${U.esc(col.label)}：${U.esc(s.f[k])}<button type="button" data-rmf="${k}" aria-label="移除 ${U.esc(col.label)} 篩選">×</button></span>`);
      }
      if (s.sort && this.cols[s.sort.c]) parts.push(`<span class="chip soft">排序：${U.esc(this.cols[s.sort.c].label)} ${s.sort.dir > 0 ? '↑' : '↓'}</span>`);
      this.chips.innerHTML = parts.join('');
      this.chips.hidden = !parts.length;
    }
    syncURL() {
      if (this.synthetic) return;
      const s = this.state; const p = new URLSearchParams();
      if (this.target != null) p.set('r', this.target);
      if (s.q) p.set('q', s.q);
      const f = {}; let nf = 0; for (const k in s.f) if (s.f[k] && Object.prototype.hasOwnProperty.call(s.f, k) && /^\d+$/.test(k)) { f[k] = String(s.f[k]); nf++; }
      if (nf) p.set('f', JSON.stringify(f));
      if (s.sort) p.set('sort', s.sort.c + ':' + (s.sort.dir > 0 ? 'a' : 'd'));
      const qs = p.toString();
      AMS.router.replace('#/s/' + encodeURIComponent(this.id) + (qs ? '?' + qs : ''));
    }
    scrollToTarget() {
      const g = this.target;
      const V = this.view; let pos = -1;
      for (let i = 0; i < V.length; i++) if (V[i] === g) { pos = i; break; }
      if (pos < 0) {
        if (this.chunked && !(this.data.rows[g])) return; // 等待分塊
        if (this._targetWarned !== g) { this._targetWarned = g; U.toast('目標列不在目前的篩選結果中'); }
        return;
      }
      const vh = this.sc.clientHeight - (this.headH || 0);
      this.sc.scrollTop = Math.max(0, pos * this.rh - vh / 2 + this.rh);
      if (this._flashed !== g) {
        this._flashed = g;
        this.root.classList.remove('flash'); void this.root.offsetWidth; this.root.classList.add('flash');
      }
    }

    /* ---------- 互動 ---------- */
    action(act, btn) {
      const s = this.state;
      if (act === 'filters') { s.showFilters = !s.showFilters; this.syncToolbar(); this.renderHead(); this.renderRows(true); }
      else if (act === 'notes') { s.showNotes = !s.showNotes; this.syncToolbar(); this.renderHead(); this.renderRows(true); }
      else if (act === 'density') { s.density = s.density === 3 ? 1 : 3; this.syncToolbar(); this.layoutCols(); this.renderAll(); if (this.target != null) this.scrollToTarget(); }
      else if (act === 'clear') { s.q = ''; s.f = {}; s.sort = null; this.target = null; this.qInput.value = ''; this.refresh({ user: true }); }
      else if (act === 'preset') {
        const p = this.presets[Number(btn.dataset.pi)]; if (!p) return;
        const fv = this.presetValue(p);
        if (s.f[p.col] === fv) delete s.f[p.col]; else s.f[p.col] = fv;
        this.target = null; this.refresh({ user: true }); this.renderHead();
      }
      else if (act === 'csv') this.exportCSV(btn);
      else if (act === 'cols') this.openColumnChooser(btn);
      else if (act === 'retry' && this.ch) this.loadRest(null);
    }
    onHeadClick(e) {
      if (e.target.closest('[data-fhelp]')) { U.toast(FILTER_HELP, 7000); return; } // title 在觸控裝置上看不到（M13）
      if (e.target.closest('.rsz') || e.target.closest('.fi')) return;
      if (this._justResized && Date.now() - this._justResized < 400) return;
      const th = e.target.closest('.th.col');
      if (!th) return;
      const c = Number(th.dataset.c);
      const s = this.state;
      if (!s.sort || s.sort.c !== c) s.sort = { c, dir: 1 };
      else if (s.sort.dir === 1) s.sort.dir = -1;
      else s.sort = null;
      this.refresh({ user: true });
    }
    onFilterInput(e, isChange) {
      const el = e.target.closest('.fi');
      if (!el) return;
      if (el.tagName === 'SELECT' && !isChange) return;
      if (el.tagName === 'INPUT' && isChange) return;
      const c = el.dataset.fc;
      const apply = () => {
        const v = el.value;
        if (v) this.state.f[c] = v; else delete this.state.f[c];
        el.classList.toggle('on', !!v);
        this.target = null;
        this.refresh({ user: true });
      };
      if (el.tagName === 'SELECT') apply();
      else { clearTimeout(this._ft); this._ft = setTimeout(apply, 260); }
    }
    onResizeStart(e) {
      const h = e.target.closest('.rsz');
      if (!h) return;
      e.preventDefault(); e.stopPropagation();
      const c = Number(h.dataset.rsz);
      const x0 = e.clientX; const w0 = this.colW(c);
      this.root.classList.add('resizing');
      // 表頭會在拖曳中重繪，所以監聽 window 而非把手本身
      const move = (ev) => {
        const w = U.clamp(Math.round(w0 + ev.clientX - x0), 36, 900);
        this.state.widths[c] = w;
        if (!this._rzr) this._rzr = requestAnimationFrame(() => { this._rzr = 0; this.layoutCols(); this.renderHead(); this.renderRows(true); });
      };
      const up = () => {
        window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up);
        this.root.classList.remove('resizing');
        this._justResized = Date.now();
      };
      window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up);
    }
    onRowClick(e) {
      if (e.target.closest('a')) return; // 連結由路由處理
      const tr = e.target.closest('.tr');
      if (!tr) return;
      const sel = window.getSelection && String(window.getSelection());
      if (sel && sel.length > 2) return; // 使用者正在選取文字
      this.openDetail(Number(tr.dataset.g));
    }
    onKey(e) {
      if (e.target !== this.sc) return;
      if (e.key === 'Enter') {
        const g = this.view[Math.max(0, Math.floor(this.sc.scrollTop / this.rh))];
        if (g != null) this.openDetail(g);
      }
    }
    posOf(g) { const V = this.view; for (let i = 0; i < V.length; i++) if (V[i] === g) return i; return -1; }
    openDetail(g) {
      this.sel = g;
      this.renderRows(true);
      const row = this.data.rows[g];
      if (!row) return;
      const cols = this.cols; const bands = this.data.bands || [];
      const hid = new Set(this.state.hidden);
      const frag = U.h('div', { class: 'dt' });
      const groups = [];
      let cur = null;
      for (let c = 0; c < this.ncol; c++) {
        const bi = this.bandOf(c);
        if (!cur || cur.bi !== bi) { cur = { bi, items: [] }; groups.push(cur); }
        cur.items.push(c);
      }
      const theme = U.theme();
      let aliasFound = null;
      for (const gr of groups) {
        const b = bands[gr.bi];
        const sec = U.h('section', { class: 'dt-sec' });
        if (b) {
          const a = U.adaptColors(b.bg, b.fc || '#fff', 'light');
          sec.appendChild(U.h('h3', { class: 'dt-band', style: { background: a.bg, color: a.fc || '#fff' } }, b.label));
        }
        const dl = U.h('dl', { class: 'dt-dl' });
        for (const c of gr.items) {
          const col = cols[c]; const v = row[c]; const raw = U.raw(v);
          if (!aliasFound && typeof raw === 'string' && AMS.isAlias(raw) && (c === this.ui.alias_col || /別名|alias/i.test(col.label))) aliasFound = raw;
          const dt = U.h('dt', {});
          dt.innerHTML = `${U.esc(col.label)}${hid.has(c) ? ' <span class="tag">隱藏欄</span>' : ''}${col.note ? `<small>${U.esc(col.note)}</small>` : ''}`;
          const dd = U.h('dd', {});
          let css = this.cellCss(g, c);
          if (U.isBlank(raw)) dd.innerHTML = '<span class="muted">（空白）</span>';
          else {
            const disp = U.display(v, col.fmt);
            let html = U.esc(U.visible(disp, true));
            if (v && typeof v === 'object' && (v.l || v.u)) html = AMS.cellLinkHTML(v, html, 'lk');
            let extra = '';
            if (typeof raw === 'string' && raw.trim() === '') extra = `<span class="muted">（${raw.length} 個空白字元）</span>`;
            else if (typeof raw === 'string' && /^\s|\s$/.test(raw)) extra = `<span class="muted">（含前後空白，長度 ${raw.length}）</span>`;
            else if (typeof raw === 'number' && disp !== String(raw)) extra = `<span class="muted">原值 ${U.esc(String(raw))}</span>`;
            if (typeof raw === 'string' && AMS.isAlias(raw)) extra += ` <a class="lk soft" href="#/card/${encodeURIComponent(raw)}">查詢卡 ›</a>`;
            dd.innerHTML = `<span class="dv${col.mono ? ' mono' : ''}" style="${css}">${html}</span>${extra}`;
          }
          dl.append(dt, dd);
        }
        sec.appendChild(dl);
        frag.appendChild(sec);
      }
      // 21／22：附上 20_參數字典 的對應條目（協定＋參數，100% 可對到）
      const proto = { 21: 'HART', 22: 'FF' }[this.id];
      if (proto && D.meta('20') && this.ui.key_col != null) {
        const key = U.text(row[this.ui.key_col]);
        const box = U.h('section', { class: 'dt-sec dt-dict' });
        box.innerHTML = '<h3 class="dt-band" style="background:#7F7F7F;color:#fff">20_參數字典</h3><p class="muted small" style="margin:6px 10px">載入參數字典…</p>';
        frag.insertBefore(box, frag.firstChild);
        AMS.paramDict(proto, key).then((hit) => {
          if (!hit) { box.querySelector('p').textContent = '（參數字典中沒有此參數）'; return; }
          const { j, i } = hit; const r2 = j.rows[i];
          const dl = U.h('dl', { class: 'dt-dl' });
          j.columns.forEach((col, c) => {
            const v = r2[c]; if (U.isBlank(U.raw(v))) return;
            dl.appendChild(U.h('dt', {}, col.label));
            const dd = U.h('dd', {}); dd.textContent = U.visible(U.display(v, col.fmt), true); dl.appendChild(dd);
          });
          box.querySelector('p').outerHTML = `<p class="small" style="margin:6px 10px"><a class="lk" href="#/s/20?r=${i}">在 20_參數字典 開啟此列 ›</a></p>`;
          box.appendChild(dl);
        }).catch(() => { box.querySelector('p').textContent = '（無法載入 20_參數字典）'; });
      }
      const pos = this.posOf(g);
      const tools = U.h('div', { class: 'dt-tools' });
      const copyBtn = U.h('button', { class: 'btn sm', type: 'button', onclick: () => {
        const tsv = cols.map((c, i) => c.label + '\t' + U.text(row[i])).join('\n');
        (navigator.clipboard ? navigator.clipboard.writeText(tsv) : Promise.reject()).then(() => U.toast('已複製此列（欄名＋值）'), () => U.toast('無法存取剪貼簿'));
      } }, '複製此列');
      const linkBtn = U.h('button', { class: 'btn sm', type: 'button', onclick: () => {
        const url = location.href.split('#')[0] + '#/s/' + this.id + '?r=' + g;
        (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(() => U.toast('已複製此列的連結'), () => U.toast(url, 5000));
      } }, '複製連結');
      tools.append(copyBtn);
      if (!this.synthetic) tools.append(linkBtn);
      if (aliasFound) tools.appendChild(U.h('a', { class: 'btn sm primary', href: '#/card/' + encodeURIComponent(aliasFound) }, '開啟設備查詢卡'));
      AMS.detail.open({
        kicker: `${this.meta.name} · 第 ${U.int(this.rowNum(g))} 列${pos >= 0 ? `（目前第 ${U.int(pos + 1)} / ${U.int(this.view.length)}）` : ''}`,
        title: U.text(row[this.ui.key_col != null ? this.ui.key_col : 0]) || U.text(row[0]) || '(空白)',
        tools, body: frag,
        onPrev: pos > 0 ? () => this.openDetail(this.view[pos - 1]) : null,
        onNext: pos >= 0 && pos < this.view.length - 1 ? () => this.openDetail(this.view[pos + 1]) : null,
        onClose: () => { this.sel = null; this.renderRows(true); },
      });
      void theme;
      // 讓選取列保持可見
      if (pos >= 0) {
        const top = pos * this.rh; const st = this.sc.scrollTop; const vh = this.sc.clientHeight - this.headH;
        if (top < st || top > st + vh - this.rh) this.sc.scrollTop = Math.max(0, top - vh / 3);
      }
    }
    openColumnChooser(btn) {
      if (this.pop) { if (this.closePop) this.closePop(); else { this.pop.remove(); this.pop = null; } return; }
      const pop = (this.pop = U.h('div', { class: 'popover colchooser', role: 'dialog', 'aria-label': '欄位顯示／隱藏' }));
      // 所有關閉途徑（點外面、Esc、✕、再按一次「欄位」、離開工作表）共用：一定移除 document 監聽（ROB-2）
      const off = (ev) => {
        if (this.pop !== pop) { document.removeEventListener('pointerdown', off, true); return; }
        if (!pop.contains(ev.target) && ev.target !== btn && !btn.contains(ev.target)) close(false);
      };
      const close = (focusBtn) => {
        pop.remove();
        document.removeEventListener('pointerdown', off, true);
        if (this.pop === pop) { this.pop = null; this.closePop = null; }
        if (focusBtn && btn.isConnected) btn.focus();
      };
      this.closePop = close;
      const s = this.state;
      const bands = this.data.bands || [];
      const render = (filter) => {
        const hid = new Set(s.hidden);
        const f = (filter || '').toLowerCase();
        let html = '';
        let lastB = -2;
        this.cols.forEach((col, c) => {
          if (f && !col.label.toLowerCase().includes(f) && !(col.note || '').toLowerCase().includes(f)) return;
          const bi = this.bandOf(c);
          if (bi !== lastB) { lastB = bi; const b = bands[bi]; html += `<div class="cc-band"${b ? ` style="border-color:${U.esc(b.bg)}"` : ''}>${b ? U.esc(b.label) : '其他'}</div>`; }
          html += `<label class="cc-item"><input type="checkbox" data-cc="${c}"${hid.has(c) ? '' : ' checked'}> <span>${U.esc(col.label)}</span>${col.hidden ? '<span class="tag">預設隱藏</span>' : ''}</label>`;
        });
        list.innerHTML = html || '<p class="muted">無符合欄位</p>';
      };
      pop.innerHTML = `<div class="cc-head"><input type="search" class="cc-q" placeholder="找欄位…" aria-label="找欄位">
        <div class="cc-btns"><button type="button" class="btn xs" data-cca="all">全部顯示</button><button type="button" class="btn xs" data-cca="def">還原預設</button><button type="button" class="btn xs" data-cca="none">全部隱藏</button><button type="button" class="btn xs" data-cca="close" aria-label="關閉">✕</button></div></div>`;
      const list = U.h('div', { class: 'cc-list' });
      pop.appendChild(list);
      render('');
      const apply = () => { this.layoutCols(); this.renderHead(); this.renderRows(true); this.syncToolbar(); };
      pop.addEventListener('change', (e) => {
        const cb = e.target.closest('[data-cc]'); if (!cb) return;
        const c = Number(cb.dataset.cc); const hid = new Set(s.hidden);
        if (cb.checked) hid.delete(c); else hid.add(c);
        if (hid.size >= this.ncol) { hid.delete(c); cb.checked = true; U.toast('至少保留一個欄位'); }
        s.hidden = Array.from(hid); apply();
      });
      pop.addEventListener('click', (e) => {
        const b = e.target.closest('[data-cca]'); if (!b) return;
        const a = b.dataset.cca;
        if (a === 'close') { close(true); return; }
        if (a === 'all') s.hidden = [];
        if (a === 'def') s.hidden = this.cols.map((c, i) => (c.hidden ? i : -1)).filter((i) => i >= 0);
        if (a === 'none') s.hidden = this.cols.map((c, i) => i).filter((i) => i !== 0);
        render(pop.querySelector('.cc-q').value); apply();
      });
      pop.querySelector('.cc-q').addEventListener('input', (e) => render(e.target.value));
      this.root.appendChild(pop);
      if (U.isMobile()) pop.classList.add('sheet'); // 手機：固定在畫面底部的面板（CSS）
      else {
        // 以按鈕右緣對齊，但夾在檢視範圍內（窄視窗時按鈕在左側，右對齊會跑出畫面；M1）
        // 座標以 popover 的定位容器（offsetParent：.app-body 或 modal 面板）為準，不是 .view（桌機時兩者差一個側欄寬）
        const r = btn.getBoundingClientRect(); const rr = this.root.getBoundingClientRect();
        const op = pop.offsetParent || document.documentElement; const orr = op.getBoundingClientRect();
        const pw = pop.offsetWidth;
        let left = r.right - pw; // 視窗座標
        left = Math.max(rr.left + 8, Math.min(left, rr.right - pw - 8));
        pop.style.top = (r.bottom - orr.top + op.scrollTop + 6) + 'px';
        pop.style.left = (left - orr.left + op.scrollLeft) + 'px';
        pop.style.right = 'auto';
      }
      // 只有滑鼠等精確指標才自動聚焦搜尋框（觸控會立刻彈出鍵盤蓋住清單）
      if (window.matchMedia('(pointer: fine)').matches) pop.querySelector('.cc-q').focus();
      setTimeout(() => { if (this.pop === pop) document.addEventListener('pointerdown', off, true); }, 0);
      pop.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(true); } });
    }
    async exportCSV(btn) {
      if (!this.view) return;
      if (this.chunked && !this.ch.allLoaded()) {
        if (!confirm(`此表尚未全部載入（${U.int(this.loaded.length)} / ${U.int(this.total)} 列）。只匯出已載入且符合篩選的列？\n（按「取消」可等載入完成後再匯出）`)) return;
      }
      const cols = this.vcols; const rows = this.data.rows; const V = this.view;
      btn.disabled = true; const old = btn.textContent; btn.textContent = '匯出中…';
      const lines = [cols.map((c) => U.csvCell(this.cols[c].label)).join(',')];
      const base = location.href.split('#')[0];
      await U.chunked(V.length, (i) => {
        const row = rows[V[i]];
        let line = '';
        for (let k = 0; k < cols.length; k++) { if (k) line += ','; line += csvField(row[cols[k]], base); }
        lines.push(line);
      });
      const d = new Date(); const P = (x) => String(x).padStart(2, '0');
      const fn = `${this.meta.name}_${d.getFullYear()}${P(d.getMonth() + 1)}${P(d.getDate())}-${P(d.getHours())}${P(d.getMinutes())}.csv`;
      U.download(fn, '\ufeff' + lines.join('\r\n') + '\r\n');
      btn.disabled = false; btn.textContent = old;
      U.toast(`已匯出 ${U.int(V.length)} 列 × ${cols.length} 欄`);
    }
    onTheme() { this.cssCache.clear(); if (this.data) { this.renderHeader(); this.renderHead(); this.renderRows(true); } }
    destroy() {
      this.destroyed = true; this.tok++;
      if (this.sc) { this.state.scrollTop = this.sc.scrollTop; this.state.scrollLeft = this.sc.scrollLeft; }
      if (this.ro) this.ro.disconnect();
      if (this.unsub) this.unsub();
      if (this.closePop) this.closePop(); else if (this.pop) this.pop.remove();
      if (AMS.detail.isOpen()) AMS.detail.close();
    }
  }
  AMS.TableView = TableView;

  /** 20_參數字典 查詢：(協定, 參數) → {j, i} */
  let dictP = null;
  AMS.paramDict = function (proto, key) {
    if (!dictP) {
      dictP = D.loadSheet('20').then((j) => {
        const m = new Map();
        j.rows.forEach((r, i) => { const k = U.text(r[0]) + '\u0001' + U.text(r[1]); if (!m.has(k)) m.set(k, i); });
        return { j, m };
      });
      dictP.catch(() => { dictP = null; });
    }
    return dictP.then(({ j, m }) => { const i = m.get(proto + '\u0001' + key); return i == null ? null : { j, i }; });
  };
})();
