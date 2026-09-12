/* AMS 解析網頁 — card 模式（02_設備查詢卡）：05 索引 → alias → 03 欄位、快速連結、最近變更、參數現值 */
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

  class CardView {
    constructor(root, meta, route) {
      this.root = root; this.meta = meta; this.id = meta.id;
      this.route = route;
      root.className = 'view card-view';
      root.innerHTML = `<header class="sv-head"><div class="sv-crumb"><span class="mode-badge">查詢卡</span> ${U.esc(meta.group || '')}</div><h1 class="sv-title">${U.esc(meta.name)}</h1></header><div class="loading-box"><div class="spinner"></div><p class="lb-msg">載入查詢卡、位號索引與設備總表…</p><div class="lb-bar"><div></div></div></div>`;
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
      return this.lastQuery != null ? this.lastQuery : (this.spec.default_query || DEFAULT.default_query);
    }
    update(route) { this.route = route; if (this.spec) this.run(this.queryFromRoute(route)); }

    renderShell() {
      const s = this.spec; const root = this.root;
      const notes = Array.isArray(s.notes) ? s.notes : (s.notes ? [s.notes] : []);
      const home = s.home_link && s.home_link.l ? `<a class="lk soft" href="${U.esc(AMS.linkHref(s.home_link.l))}">${U.esc(s.home_link.t || '⌂ 目錄')}</a>` : '<a class="lk soft" href="#/s/00">⌂ 目錄</a>';
      root.innerHTML = `
        <header class="sv-head">
          <div class="sv-crumb"><span class="mode-badge">查詢卡</span> ${U.esc(this.meta.group || '')} · ${home}</div>
          <h1 class="sv-title">${U.esc(s.title || this.meta.name)}</h1>
          ${notes.length ? `<p class="sv-lead">${notes.map((n) => U.esc(n)).join('<br>')}</p>` : ''}
        </header>
        <div class="card-scroll">
        <form class="cq" role="search" autocomplete="off">
          <label class="cq-label" for="cq-input">${U.esc(s.input && s.input.label || '查詢位號')}</label>
          <div class="cq-field"><input id="cq-input" class="cq-input" type="search" spellcheck="false" placeholder="${U.esc(s.input && s.input.prompt || '')}" aria-describedby="cq-status"></div>
          <button class="btn primary" type="submit">查詢</button>
        </form>
        <div id="cq-status" class="cq-status" role="status" aria-live="polite"></div>
        <div class="cq-meta"></div>
        <div class="cq-alts" hidden></div>
        <div class="cq-body"></div>
        </div>`;
      this.input = root.querySelector('#cq-input');
      const form = root.querySelector('.cq');
      form.addEventListener('submit', (e) => { e.preventDefault(); this.go(this.input.value); });
      this.ac = new AMS.Autocomplete(this.input, Object.assign({}, AMS.tagSuggestSource, {
        onPick: (it) => this.go(it.key),
        onEnter: (t) => this.go(t),
      }));
    }
    go(q) {
      q = String(q == null ? '' : q).trim();
      if (!q) { this.run(''); return; }
      const h = '#/card/' + encodeURIComponent(q);
      if (location.hash === h) this.run(q); else AMS.router.go(h);
    }

    /* ---------- 查詢鏈 ---------- */
    lookup(q) {
      const L = this.spec.lookup; const M = L.msg;
      const res = { q, key: '', alias: '', count: null, src: '', i3: null, status: '', notfound: false };
      if (q == null || q === '') { res.status = M.empty; res.empty = true; return res; }
      const key = AMS.index.norm(q);
      res.key = key;
      if (!key) { res.status = M.empty; res.empty = true; return res; }
      const IX = AMS.index; const i5 = IX.first.get(key);
      if (i5 == null) { res.status = M.notfound; res.notfound = true; return res; }
      const r5 = IX.sheet.rows[i5];
      res.i5 = i5;
      res.alias = U.text(r5[L.alias_col]);
      res.count = U.raw(r5[L.count_col]);
      res.src = U.text(r5[L.src_col]);
      const k = U.text(r5[L.key_col]);
      const DV = AMS.devices;
      res.i3 = res.alias ? (DV.byAlias.get(res.alias) ?? null) : null;
      res.status = fill(M.found, { src: res.src, key: k });
      if (res.i3 == null) res.status += M.no_device;
      else res.status += fill(M.device, { tag: U.text(DV.sheet.rows[res.i3][L.target_tag_col]) });
      return res;
    }
    run(q) {
      this.lastQuery = q;
      if (this.input && document.activeElement !== this.input) this.input.value = q == null ? '' : q;
      const res = (this.res = this.lookup(q));
      const root = this.root;
      const L = this.spec.lookup;
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
      if (res.notfound) { body.appendChild(this.renderNotFound(res)); document.title = '查無「' + String(q) + '」 · 設備查詢卡 · AMS'; return; }
      if (res.empty) { document.title = '設備查詢卡 · AMS'; return; }
      body.appendChild(this.renderSections(row, res));
      if (this.spec.stats && this.spec.stats.sheet) body.appendChild(this.renderStats(row, res));
      body.appendChild(this.renderLinks(row, res));
      body.appendChild(this.renderRecent(row, res));
      body.appendChild(this.renderParams(row, res));
      // 分頁標題以使用者分享的位號為主，alias 附在括號（書籤／歷史紀錄才認得出來；LIVE-5）
      const tag0 = row ? U.text(row[L.target_tag_col]) : '';
      const head = res.empty ? '' : (tag0 || res.key || String(q || ''));
      document.title = [head, res.alias && res.alias !== head ? `（${res.alias}）` : ''].join('') + (head ? ' · ' : '') + '設備查詢卡 · AMS';
    }

    /** 查無此鍵：05 虛擬捲動表無法用 Ctrl+F 找到畫面外的列 → 直接給建議與「在 05 搜尋」連結（ENG-05） */
    renderNotFound(res) {
      const box = U.h('section', { class: 'csec nf' });
      box.appendChild(U.h('h2', { class: 'csec-h' }, '找不到完全相符的鍵'));
      const inner = U.h('div', { class: 'nf-body' });
      let sg = [];
      try { sg = AMS.index.suggest(res.q, 12); } catch (e) { sg = []; }
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

    /* ---------- 欄位區段 ---------- */
    fieldValue(f, row) {
      if (!row) return '';
      const cols = Array.isArray(f.col) ? f.col : [f.col];
      if (cols.length > 1 || f.join != null) {
        let s = cols.map((c) => { const v = U.raw(row[c]); return v == null ? '' : String(v); }).join(f.join != null ? f.join : ' ');
        if (f.trim !== false) s = s.replace(/ +/g, ' ').trim();
        return s;
      }
      const v = row[cols[0]];
      const raw = U.raw(v);
      if (!f.raw) return raw == null ? '' : (raw === true ? 'TRUE' : raw === false ? 'FALSE' : String(raw));
      if (raw == null || raw === '') return '';
      const fmt = f.fmt && f.fmt !== 'General' ? f.fmt : null;
      if (typeof raw === 'number') return fmt ? U.fmt(raw, fmt) : U.general(raw);
      return fmt ? U.fmt(raw, fmt) : String(raw);
    }
    renderSections(row) {
      const wrap = U.h('div', { class: 'card-sections' });
      for (const sec of this.spec.sections) {
        const s = U.h('section', { class: 'csec' });
        s.appendChild(U.h('h2', { class: 'csec-h' }, sec.label));
        const grid = U.h('div', { class: 'cfields' });
        for (const f of sec.fields || []) {
          const val = this.fieldValue(f, row);
          const col0 = Array.isArray(f.col) ? f.col[0] : f.col;
          const css = this.ruleStyleFor(col0, row, this.res);
          const item = U.h('div', { class: 'cf' + (f.span === 2 ? ' span2' : '') });
          const head03 = AMS.devices.sheet.columns && AMS.devices.sheet.columns[col0];
          const tip = head03 && head03.label !== f.label ? `03 欄：${head03.label}` : (head03 ? `03 欄：${head03.label}` : '');
          item.innerHTML = `<div class="cf-k" title="${U.esc(tip)}">${U.esc(f.label)}</div><div class="cf-v${val === '' ? ' blank' : ''}${f.raw && /^-?[\d,.]+%?$/.test(val) ? ' num' : ''}" style="${css}">${U.esc(U.visible(val, true))}</div>`;
          grid.appendChild(item);
        }
        s.appendChild(grid);
        wrap.appendChild(s);
      }
      return wrap;
    }

    /* ---------- 另一張表的關鍵值（spec.stats：{sheet, alias_col, fields:[{label,col,fmt?}]}，依設備別名對到該表的一列） ---------- */
    renderStats(row, res) {
      const st = this.spec.stats;
      const s = U.h('section', { class: 'csec stats' });
      s.appendChild(U.h('h2', { class: 'csec-h' }, st.title || `關鍵組態現值（${D.meta(st.sheet) ? D.meta(st.sheet).name : st.sheet}）`));
      const grid = U.h('div', { class: 'cfields' });
      s.appendChild(grid);
      if (!row || !res.alias) { grid.innerHTML = '<p class="muted cl-empty">（無對應設備）</p>'; return s; }
      grid.innerHTML = '<p class="muted cl-empty">載入中…</p>';
      const alias = res.alias;
      D.loadSheet(st.sheet).then((j) => {
        if (this.destroyed || this.res.alias !== alias) return;
        const ac = st.alias_col != null ? st.alias_col : (j.columns || []).findIndex((c) => /設備別名|alias/i.test(c.label));
        const i = j.rows.findIndex((r) => U.text(r[ac]) === alias);
        if (i < 0) { grid.innerHTML = `<p class="muted cl-empty">此設備在 ${U.esc(D.meta(st.sheet) ? D.meta(st.sheet).name : st.sheet)} 無資料（沒有參數紀錄）。</p>`; return; }
        const r = j.rows[i];
        grid.innerHTML = '';
        for (const f of st.fields || []) {
          const raw = U.raw(r[f.col]);
          const col = (j.columns || [])[f.col] || {};
          const val = raw == null || raw === '' ? '' : (typeof raw === 'number' ? (f.fmt ? U.fmt(raw, f.fmt) : U.general(raw)) : (f.fmt ? U.fmt(raw, f.fmt) : String(raw)));
          const item = U.h('div', { class: 'cf' + (f.span === 2 ? ' span2' : '') });
          item.innerHTML = `<div class="cf-k" title="${U.esc(col.label || '')}">${U.esc(f.label)}</div><div class="cf-v${val === '' ? ' blank' : ''}${typeof raw === 'number' ? ' num' : ''}">${U.esc(U.visible(val, true))}</div>`;
          grid.appendChild(item);
        }
        const more = U.h('p', { class: 'muted small' });
        more.innerHTML = `<a class="lk" href="${sheetHref(st.sheet, { r: i })}">在 ${U.esc(D.meta(st.sheet) ? D.meta(st.sheet).name : st.sheet)} 開啟此設備的完整一列 ›</a>`;
        s.appendChild(more);
      }).catch((e) => { grid.innerHTML = `<p class="muted">無法載入：${U.esc(e.message)}</p>`; });
      return s;
    }

    /* ---------- 快速連結 ---------- */
    renderLinks(row, res) {
      const s = U.h('section', { class: 'csec links' });
      s.appendChild(U.h('h2', { class: 'csec-h' }, this.spec.links_title || DEFAULT.links_title));
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
      s.appendChild(U.h('h2', { class: 'csec-h' }, rc.title || DEFAULT.recent_changes.title));
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
        const cellText = (r, c) => {
          if (c.cols) return c.cols.map((k) => { const v = U.raw(r[k]); return v == null ? '' : String(v); }).join(c.join != null ? c.join : ' ');
          const v = U.raw(r[c.col]);
          if (v == null) return '';
          return c.fmt ? U.fmt(v, c.fmt) : String(v);
        };
        let html = `<div class="tbl-scroll"><table class="mini"><thead><tr><th>k</th>${cols.map((c) => `<th>${U.esc(c.label)}</th>`).join('')}</tr></thead><tbody>`;
        for (const [k, i] of take) {
          const r = j.rows[i];
          html += `<tr><td class="ac"><a class="lk" href="${sheetHref(rc.sheet, { r: i })}" title="在 08 開啟此列">${U.esc(k)}</a></td>${cols.map((c, ci) => `<td${ci === 0 ? ' class="nowrap"' : ''}>${U.esc(U.visible(cellText(r, c), true))}</td>`).join('')}</tr>`;
        }
        html += '</tbody></table></div>';
        const more = list.length > kmax ? `共 ${U.int(list.length)} 筆${U.esc(noun)}，顯示最新 ${kmax} 筆。` : `共 ${U.int(list.length)} 筆${U.esc(noun)}。`;
        const ac = this.findAliasCol(j, rc);
        const fl = ac != null ? sheetHref(rc.sheet, { f: { [ac]: '=' + alias } }) : U.esc('#/s/' + encodeURIComponent(rc.sheet) + '?q=' + encodeURIComponent(alias + '#'));
        html += `<p class="muted small">${more} <a class="lk" href="${fl}">在 ${U.esc(sheetLabel)} 查看此設備全部${U.esc(noun)} ›</a></p>`;
        body.innerHTML = html;
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
              const txt = U.isBlank(raw) ? '' : U.display(v, cols[i].fmt);
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
    destroy() { this.destroyed = true; }
  }
  AMS.CardView = CardView;
})();
