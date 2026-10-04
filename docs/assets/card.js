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
        multi_pick: '顯示第 {i} 台（共 {n} 台）',
        prev: '← 上一個',
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
  // near＝同單位但數值不完全相同（±0.5% span 內）：黃色「請確認」，不併入紅色 ⚠
  const CMP_TEXT = { mismatch: '⚠ 與 DCS 不符', near: '≈ 近似（請確認）', unit_mismatch: '單位不同未比較', unit_unknown: '單位不明未比較', ref_only: '序號不符未比較', ok: '✓ 與 DCS 一致' };
  const cmpCls = (st) => (st === 'mismatch' ? 'bad' : st === 'near' ? 'warn' : st === 'ok' ? 'ok' : 'soft');
  const CMP_KIND = { ams: 'AMS 量程（資料庫快照）', dcdas: 'DCS 控制器組態', dcdas_ch: '控制器組態（其他通道）', dcs_write: 'DCS 寫入事件', terminal: 'DCS 端子表', instlist: '儀器清單', eomr: 'EOMR' };
  let uid = 0;

  const fill = (tpl, o) => String(tpl).replace(/\{(\w+)\}/g, (_, k) => (o[k] == null ? '' : String(o[k])));
  /** 複製文字：navigator.clipboard 不存在（http 區網 IP）或被拒時，退回暫時 textarea＋execCommand('copy')；回傳是否成功 */
  async function copyText(s) {
    s = String(s == null ? '' : s);
    if (navigator.clipboard && navigator.clipboard.writeText) { try { await navigator.clipboard.writeText(s); return true; } catch (e) { /* 退路 */ } }
    try {
      const ta = document.createElement('textarea');
      ta.value = s; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;pointer-events:none';
      document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, s.length);
      const ok = document.execCommand('copy'); ta.remove(); return !!ok;
    } catch (e) { return false; }
  }
  AMS.copyText = copyText;
  /** 站內工作表連結（已跳脫，可直接放進 href="…"）：id 以 encodeURIComponent、r／rn 只接受非負整數（SEC-1）；rn＝此設備的最後一列（分塊表只載 r..rn 所在的分塊） */
  function sheetHref(sid, o) {
    o = o || {};
    const p = [];
    const r = o.r == null ? NaN : Number(o.r);
    if (Number.isInteger(r) && r >= 0) p.push('r=' + r);
    const rn = o.rn == null ? NaN : Number(o.rn);
    if (Number.isInteger(r) && r >= 0 && Number.isInteger(rn) && rn >= r) p.push('rn=' + rn);
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
        // 進度條：三份（查詢卡規格、位號索引、設備總表）各自的下載進度平均寫進 .lb-bar；全部下載完（0.98）到解密完成前改字
        const fr = [0, 0, 0];
        const upd = () => {
          const b = this.root.querySelector('.lb-bar > div'); if (!b) return;
          b.style.width = Math.round((fr[0] + fr[1] + fr[2]) / 3 * 100) + '%';
          const m = this.root.querySelector('.lb-msg');
          if (m && fr.every((x) => x >= 0.98)) m.textContent = D.enc() ? '解密中…' : '整理資料…';
        };
        const specP = D.loadSheet(this.id, (f) => { fr[0] = f; upd(); }).catch(() => ({}));
        const [spec] = await Promise.all([specP, AMS.index.load((f) => { fr[1] = f; upd(); }), AMS.devices.load((f) => { fr[2] = f; upd(); })]);
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
      this.ac = new AMS.Autocomplete(this.input, Object.assign({}, AMS.searchSuggestSource || AMS.tagSuggestSource, {
        emptyItems: () => CardView.recentItems(), // 聚焦或清空時列「最近查過」
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
      // 氣動閥清單位號（AMS 沒有）優先於「包含／唯一建議」的模糊對應：不然閥位號會被悄悄換成某個不相干的 AMS 鍵
      try { const rs = AMS.index.resolve(q); if (rs.key && (rs.how === 'exact' || rs.how === 'compact' || !this.valveBlocksFuzzy(q, rs))) k = rs.key; } catch (e) { /* 索引未載 → 照原字串 */ }
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
      let fuzzyBlocked = false;
      if (rs.how !== 'exact' && rs.how !== 'compact') {
        const vr = this.valveLookup(q, res, rs); if (vr) return vr;
        fuzzyBlocked = !!rs.key && !this.valveHit(q, rs) && this.valveBlocksFuzzy(q, rs);
      }
      const i5 = rs.key && !fuzzyBlocked ? IX.first.get(rs.key) : null;
      if (i5 == null) {
        res.status = M.notfound; res.notfound = true; res.sg = rs.suggestions;
        if (fuzzyBlocked) { // AMS 的模糊候選仍列在最前面（只是不自動開）
          const r0 = IX.sheet.rows[IX.first.get(rs.key)];
          const it0 = { key: rs.key, src: U.text(r0[L.src_col]), alias: U.text(r0[L.alias_col]) };
          res.sg = [it0].concat(IX.suggest(q, 12).filter((x) => x.key !== rs.key)).slice(0, 12);
          res.key = IX.norm(q);
        }
        return res;
      }
      const r5 = IX.sheet.rows[i5];
      res.i5 = i5;
      res.alias = U.text(r5[L.alias_col]);
      res.count = U.raw(r5[L.count_col]);
      res.src = U.text(r5[L.src_col]);
      const k = U.text(r5[L.key_col]);
      const DV = AMS.devices;
      // 同一鍵對到多台：#/card/<鍵>?a=<alias> 指定顯示哪一台（輸入框、網址主體、其他設備 chips 都維持原查詢鍵）
      const want = this.route && this.route.params ? this.route.params.get('a') : null;
      if (want && typeof res.count === 'number' && res.count > 1) {
        const list = IX.aliasesOf(k);
        const pos = list.indexOf(want);
        if (pos > 0) { res.alias = want; res.pick = pos; res.alts = list; }
      }
      res.i3 = res.alias ? (DV.byAlias.get(res.alias) ?? null) : null;
      res.status = (rs.how !== 'exact' && M.found_via ? fill(M.found_via, { q: IX.norm(q), key: k }) : '') + fill(M.found, { src: res.src, key: k });
      if (res.i3 == null) res.status += M.no_device;
      else res.status += fill(M.device, { tag: U.text(DV.sheet.rows[res.i3][L.target_tag_col]) });
      return res;
    }
    run(q) {
      const sig = String(q == null ? '' : q) + '|' + ((this.route && this.route.params && this.route.params.get('a')) || '');
      const changed = this.lastSig !== undefined && this.lastSig !== sig; // 換了位號或切到另一台（卡片內的 chip／相近建議／最近查過）→ 捲回頂端
      this.lastQuery = q; this.lastSig = sig;
      // 查詢一律由路由驅動（送出、站內連結、上一頁、網址列貼深連結都會經過這裡）→ 框內文字無條件同步成目前查詢；
      // 以前「框內有焦點就不覆寫」會讓按「上一頁」後卡片換了、框裡還是上一個位號
      const qs = q == null ? '' : String(q);
      if (this.input && this.input.value !== qs) this.input.value = qs;
      const res = (this.res = this.lookup(q));
      if (res.notfound && !res.valve) { // 有相近位號時，狀態列不再叫人去位號索引搜尋，直接說「以下是相近的」
        if (!Array.isArray(res.sg)) { try { res.sg = AMS.index.suggest(res.q, 12); } catch (e) { res.sg = []; } }
        try { res.vsg = AMS.valves.suggest(this.spec.valve, res.q, 12); } catch (e) { res.vsg = []; }
        res.fz = [];
        if (!res.sg.length && !res.vsg.length && AMS.fuzzy) { try { res.fz = AMS.fuzzy(this.spec.valve || null, res.q, 8); } catch (e) { res.fz = []; } }
        if ((res.sg.length || res.vsg.length) && this.spec.lookup.msg.notfound_near) res.status = this.spec.lookup.msg.notfound_near;
        else if (res.fz.length) res.status = '找不到這個字串，可能打錯字：相近的鍵列在下方。';
        else if (this.spec.valve) res.status += '；氣動閥可到側欄「氣動閥清單」（57／58）搜尋，GE 舊位號在 Legacy/GE Tag 欄';
      }
      this.aux = null; this.statsReady = false;
      const root = this.root;
      const L = this.spec.lookup;
      if (this.scrollEl) this.scrollEl.classList.toggle('landing', !!res.empty);
      root.querySelector('.cq-status').textContent = res.status;
      root.querySelector('.cq-status').className = 'cq-status' + (res.notfound && !res.valve ? ' bad' : '');
      const row = res.i3 != null ? AMS.devices.sheet.rows[res.i3] : null;
      // alias / count
      const countStyle = this.ruleStyleFor('count', row, res);
      const meta = root.querySelector('.cq-meta');
      if (res.empty || res.notfound) meta.innerHTML = '';
      else {
        const multiMsg = typeof res.count === 'number' && res.count > 1 ? (res.pick ? fill(L.msg.multi_pick, { i: res.pick + 1, n: res.count }) : L.msg.multi) : '';
        // 「← 上一個」：最近查過裡第一個不是目前設備的（查 A → 查 B → 一鍵回 A 對照）
        const prev = this.recent().find((x) => x.k !== res.key && !(res.alias && x.a === res.alias));
        meta.innerHTML = `<div class="kv"><span class="k">${U.esc(L.labels.alias)}</span><span class="v strong">${U.esc(res.alias || '')}</span></div>
          <div class="kv"><span class="k">${U.esc(L.labels.count)}</span><span class="v" style="${countStyle}">${res.count == null ? '' : U.esc(U.fmt(res.count))}</span>
          ${multiMsg ? `<span class="warn-text">${U.esc(multiMsg)}</span>` : ''}</div>
          ${prev ? `<a class="chip-btn prev-chip" href="${U.esc('#/card/' + encodeURIComponent(prev.k) + (prev.q || ''))}" title="上一個查過的位號">${U.esc(L.msg.prev || '← 上一個')}：<span class="mono">${U.esc(prev.t || prev.k)}</span></a>` : ''}`;
      }
      const flagsEl = root.querySelector('.cq-flags');
      flagsEl.hidden = true; flagsEl.innerHTML = '';
      // 其他對應設備：chip 連到 #/card/<原鍵>?a=<alias>（第一台就是原鍵本身），位號在前、alias 在後；切換後 chips 仍在、分享連結保留原位號
      const alts = root.querySelector('.cq-alts');
      if (typeof res.count === 'number' && res.count > 1) {
        const list = res.alts || AMS.index.aliasesOf(res.key);
        alts.hidden = false;
        alts.innerHTML = `<span class="muted">此鍵對應的全部設備：</span>` + list.map((a, i) => {
          const i3 = AMS.devices.byAlias.get(a); const tag = i3 != null ? U.text(AMS.devices.sheet.rows[i3][0]) : '';
          const on = res.alias ? a === res.alias : i === 0;
          const href = '#/card/' + encodeURIComponent(res.key) + (i === 0 ? '' : '?a=' + encodeURIComponent(a));
          return `<a class="chip-btn${on ? ' on' : ''}" href="${U.esc(href)}" title="${U.esc(a)}"><span class="mono">${U.esc(tag || a)}</span>${tag ? `<span class="muted small"> ${U.esc(a)}</span>` : ''}${on ? '（顯示中）' : ''}</a>`;
        }).join('');
      } else { alts.hidden = true; alts.innerHTML = ''; }
      const body = root.querySelector('.cq-body');
      body.innerHTML = '';
      body.classList.toggle('landing', !!res.empty);
      if (changed) { root.scrollTop = 0; if (this.scrollEl) this.scrollEl.scrollTop = 0; }
      if (res.valve) {
        body.appendChild(this.renderValveOnly(res));
        if (res.valve.via === 'weak' || res.valve.c.length < 5) {
          let sg = []; try { sg = AMS.index.suggest(res.q, 12); } catch (e) { sg = []; }
          if (sg.length) {
            const box = U.h('section', { class: 'csec nf-also' }, U.h('h2', { class: 'csec-h' }, 'AMS 位號索引裡含這個字串的鍵'));
            const ch = U.h('div', { class: 'nf-chips' });
            for (const it of sg) ch.appendChild(U.h('a', { class: 'chip-btn', href: '#/card/' + encodeURIComponent(it.key) }, U.h('span', { class: 'mono' }, it.key), U.h('span', { class: 'muted small' }, ' ' + [it.src, it.alias].filter(Boolean).join(' · '))));
            box.appendChild(ch); body.appendChild(box);
          }
        }
        document.title = String(q) + '（氣動閥清單） · 設備查詢卡 · AMS'; return;
      }
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

    /* ---------- 氣動閥清單（02.json valve；tools/db/pneuvalve_site.py） ---------- */
    /** 輸入字串 → 氣動閥清單命中 {ents:[{sid,row}], unit, c, via}（AMS.valves.hit：清單位號、展開位號、去機組核心、GE 舊位號、
     *  Mark VIe 器件名、GE KKS、附件位號；去附件後綴／機組前綴後再查；rs＝IX.resolve 的結果，AMS 的「包含」命中較長時讓 AMS） */
    valveHit(q, rs) { return AMS.valves.hit(this.spec && this.spec.valve, q, AMS.valves.amsLen(rs)); }
    /** 命中的清單列對到的 AMS 設備：[{alias, unit, tag, how, cmp, cmpText, note}]（多列聯集、去重、依機組排序） */
    valveAliases(vh) {
      const V = this.spec.valve;
      if (!this._vrev) {
        this._vrev = new Map();
        for (const [al, list] of Object.entries(V.by_alias || {})) {
          for (const e of list) {
            const k = e[0] + ':' + e[1]; const i3 = AMS.devices.byAlias.get(al);
            const tag = i3 != null ? U.text(AMS.devices.sheet.rows[i3][0]) : al;
            if (!this._vrev.has(k)) this._vrev.set(k, []);
            this._vrev.get(k).push({ alias: al, unit: e[2], tag, how: e[3], cmp: e[4], cmpText: e[5], note: e[6] });
          }
        }
      }
      const out = []; const seen = new Set();
      for (const e of vh.ents) for (const x of this._vrev.get(e.sid + ':' + e.row) || []) if (!seen.has(x.alias)) { seen.add(x.alias); out.push(x); }
      return out.sort((a, b) => (a.unit < b.unit ? -1 : a.unit > b.unit ? 1 : 0));
    }
    /** 命中的鍵（vh.k）是哪一個別名：回傳清單列別名的顯示字串（VA13-25、20SSV-3B、11LBF54AA004）；命中的是位號／展開位號／核心 → '' */
    valveAliasText(vh) {
      const V = this.spec.valve; const IX = AMS.index; const k = vh.k || vh.c;
      for (const e of vh.ents) {
        const it = AMS.valves.item(V, e.sid, e.row);
        if (!it) continue;
        const T = IX.compact(it[2]); const core = AMS.valves.core(it[2]);
        if (k === T || k === core || k === 'XX' + core || k === 'YY' + core || (/^[GCS]\d\d/.test(k) && k.slice(3) === core)) return '';
        const a = (it[3] || []).find((x) => { const a1 = IX.compact(x); return a1 === k || '90' + a1 === k || (k.length >= 4 && a1.endsWith(k)); });
        if (a) return a;
      }
      return '';
    }
    /** 此 AMS 設備對到的清單列（摘要「氣動閥」組） */
    valveEntries(alias) {
      const V = this.spec.valve; const list = V && V.by_alias && alias ? V.by_alias[alias] : null;
      return (list || []).map((e) => ({ sid: String(e[0]), row: e[1], unit: e[2], how: e[3], cmp: e[4], cmpText: e[5], note: e[6] }));
    }
    /** AMS 位號索引沒有完全相符、而氣動閥清單有：
     *  - AMS 的模糊對應（包含／唯一建議）指到的正是這顆閥自己的 AMS 設備（11HAD10QN005 → G11HAD10QN005；只有一台的核心）→ 讓 AMS 照舊開那台；
     *  - 輸入帶機組（G11…）且該機組恰有一台 AMS 設備 → 顯示那台；
     *  - 否則顯示閥卡（一鍵對多列時每列一塊）。狀態列說明經由哪一種識別碼對到。 */
    valveLookup(q, res, rs) {
      const vh = this.valveHit(q, rs); if (!vh) return null;
      const IX = AMS.index; const M = this.spec.lookup.msg; const V = this.spec.valve;
      const als = this.valveAliases(vh);
      // 使用者打的機組：G11…（整串或去前綴）→ 'G11'；只打數字（11HAD10QN005、…QN005.PV 這類「包含」命中）→ 取鍵前面的兩位數 '11'
      let unit = vh.unit || '';
      if (!unit) {
        const um = /^[GCS]\d\d(?=[A-Z])/.exec(vh.k || vh.c); // 命中的鍵本身帶機組（展開位號 G12HAD10QN001，含貼上 .PV 的「包含」命中）
        if (um) unit = um[0];
        else if (vh.k && vh.c !== vh.k) { const pm = /([GCS])?(\d\d)$/.exec(vh.c.slice(0, vh.c.indexOf(vh.k))); if (pm) unit = (pm[1] || '') + pm[2]; }
      }
      const unitOf = (x) => (unit.length === 3 ? x.unit === unit : x.unit.slice(1) === unit);
      if (rs && rs.key && (rs.how === 'contain' || rs.how === 'suggest') && vh.via !== 'unit-other') {
        const i5 = IX.first.get(rs.key);
        const al = i5 != null ? U.text(IX.sheet.rows[i5][this.spec.lookup.alias_col]) : '';
        const dev = al ? als.find((x) => x.alias === al) : null;
        // 讓給 AMS 的條件：那台就是這顆閥自己的設備，而且機組與使用者打的一致（沒打機組時：只有一台，或不是整串命中）
        if (dev && (unit ? unitOf(dev) : (vh.via !== 'key' || als.length === 1))) return null;
      }
      const mine = unit && vh.via !== 'unit-other' ? als.filter(unitOf) : [];
      const aliasTxt = this.valveAliasText(vh);
      const first = AMS.valves.item(V, vh.ents[0].sid, vh.ents[0].row);
      const listTag = first ? first[2] : '';
      const covs = []; for (const e of vh.ents) for (const u of ((AMS.valves.item(V, e.sid, e.row) || [])[6] || [])) if (!covs.includes(u)) covs.push(u);
      const cover = covs.join('、');
      let what;
      if (vh.via === 'weak') what = '廠商代號（多顆閥共用，不是 GE 舊位號）';
      else if (vh.via === 'contain' || vh.via === 'token') what = `內含「${aliasTxt || vh.k}」的字串（${aliasTxt ? 'GE 舊位號／別名' : '氣動閥清單位號'}）`;
      else if (vh.via === 'suffix') what = `「${aliasTxt || listTag}」加附件後綴`;
      else if (vh.via === 'unit-other') what = `去掉機組「${vh.unit}」後對到氣動閥清單的「${aliasTxt || listTag}」，但清單${vh.ents.length > 1 ? '這 ' + vh.ents.length + ' 列' : '這一列'}只涵蓋 ${cover || '其他機組'}（沒有 ${vh.unit}），以下是同型閥的資料`;
      else if (aliasTxt) what = AMS.index.compact(aliasTxt) === vh.c ? ' GE 舊位號／別名' : `「${aliasTxt}」的另一種寫法（GE 舊位號／別名）`;
      else what = AMS.index.compact(listTag) === vh.c ? '氣動閥清單位號' : `氣動閥清單「${listTag}」的另一種寫法`;
      if (mine.length === 1 && !this._inValve) {
        this._inValve = true;
        let r2; try { r2 = this.lookup(mine[0].alias); } finally { this._inValve = false; }
        if (r2 && !r2.notfound) { r2.status = fill(M.valve_via || '「{q}」是{what}，對應 AMS 設備 {tag}（{how}）。', { q: IX.norm(q), what, tag: mine[0].tag, how: mine[0].how }) + r2.status; return r2; }
      }
      vh.alias = aliasTxt; vh.listTag = listTag; vh.exactTag = !aliasTxt && vh.via === 'key' && AMS.index.compact(listTag) === vh.c;
      res.valve = vh; res.valveAls = als; res.notfound = true; res.key = IX.norm(q);
      const n = vh.ents.length;
      const other = vh.via === 'unit-other' || (unit && !mine.length && als.length);
      res.valveOther = !!other;
      res.status = fill(vh.via === 'unit-other' ? '「{q}」：{what}' : '「{q}」是{what}', { q: vh.exactTag ? listTag : IX.norm(q), what }) + (n > 1 ? `，清單裡有 ${n} 列用到它（都列在下面）` : '')
        + (vh.via === 'weak' ? '；這幾顆閥在 AMS 沒有設備，AMS 位號索引裡含這個字串的鍵（若有）列在閥卡下方。' : als.length ? (other ? `；AMS 資料庫沒有 ${vh.unit || unit} 這台，同型閥在其他機組的設備見下方。` : '；同一閥在 AMS 資料庫的設備見下方。')
          : '；AMS 資料庫沒有對應設備（開關閥／非 HART·FF 智慧定位器，或機組不在本庫）。');
      return res;
    }
    /** 位號索引的模糊對應（包含／唯一建議）要不要採用：氣動閥清單有命中 → 不採用（交給 valveLookup）；
     *  清單有「開頭相符」的候選、而且不是 AMS 那台自己的閥 → 也不採用（C10MAJ60QM06 不該悄悄開 C10MAJ60BP006；G11_90VA13 不該直接開 VA13T-1），改列兩邊的候選 */
    valveBlocksFuzzy(q, rs) {
      const V = this.spec && this.spec.valve; if (!V) return false;
      if (this.valveHit(q, rs)) return true;
      const IX = AMS.index;
      const i5 = rs && rs.key ? IX.first.get(rs.key) : null;
      const al = i5 != null ? U.text(IX.sheet.rows[i5][this.spec.lookup.alias_col]) : '';
      return AMS.valves.suggest(V, q, 12).some((it) => it.m === 'pre' && !((V.by_alias || {})[al] || []).some((e) => String(e[0]) === String(it.valve[0]) && e[1] === it.valve[1]));
    }
    /** 只在氣動閥清單的位號：閥規格（逐格出處）＋同一閥在 AMS 的設備 */
    renderValveOnly(res) {
      const V = this.spec.valve;
      const wrap = U.h('section', { class: 'csec sum valve-only' });
      const hero = U.h('div', { class: 'sum-hero' });
      const vv = res.valve;
      hero.appendChild(U.h('div', { class: 'sum-tag' }, U.h('span', { class: 'sum-tagtext' }, vv.exactTag ? vv.listTag : String(res.key)))); // 清單位號保留原寫法（Gxx／Sx0 的小寫 x＝多機組）
      const viaLab = vv.exactTag ? '氣動閥清單位號' : vv.via === 'weak' ? '廠商代號（清單位號見下）' : (vv.alias ? 'GE 舊位號／別名 ' + vv.alias + '（清單位號見下）' : '對應氣動閥清單（清單位號見下）');
      hero.appendChild(U.h('div', { class: 'sum-sub' }, U.h('span', { class: 'sum-subi' }, viaLab), vv.ents.length > 1 ? U.h('span', { class: 'sum-subi' }, `清單裡有 ${vv.ents.length} 列`) : null, U.h('span', { class: 'sum-subi' }, res.valveAls.length ? (res.valveOther ? '此機組不在 AMS 資料庫' : 'AMS 設備見下方') : '不在 AMS 資料庫')));
      if (res.valveAls.length) {
        const ch = U.h('div', { class: 'nf-chips valve-ams' }, U.h('span', { class: 'muted small' }, res.valveOther ? '同型閥在其他機組的 AMS 設備：' : '同一閥在 AMS 的設備：'));
        for (const x of res.valveAls) ch.appendChild(U.h('a', { class: 'chip-btn', href: '#/card/' + encodeURIComponent(x.alias), title: x.how }, U.h('span', { class: 'mono' }, x.tag), U.h('span', { class: 'muted small' }, ' ' + x.unit + ' · ' + x.alias)));
        hero.appendChild(ch);
      }
      wrap.appendChild(hero);
      const groups = U.h('div', { class: 'sum-groups' });
      const sec = U.h('section', { class: 'sum-g sum-valve' });
      const g = ((this.spec.summary && this.spec.summary.groups) || []).find((x) => x.valve) || {};
      sec.appendChild(U.h('h3', { class: 'sum-gh' }, g.label || ('氣動閥（' + (V.list_name || '氣動閥清單') + '）')));
      const grid = U.h('div', { class: 'sum-body' });
      grid.innerHTML = '<p class="muted cl-empty">載入中…</p>';
      sec.appendChild(grid);
      if (g.note) sec.appendChild(U.h('p', { class: 'muted small aux-note' }, g.note));
      groups.appendChild(sec);
      wrap.appendChild(groups);
      this.fillValveGroup(grid, res.valve.ents, res);
      return wrap;
    }
    /** 氣動閥組：載入 57／58（valve_src 逐格出處＋valve_docs 雲端連結）後逐欄顯示；ents＝[{sid,row,unit?,how?,cmp?,cmpText?,note?}] */
    async fillValveGroup(grid, ents, res) {
      const V = this.spec.valve; const mode = this.currentMode();
      try {
        const js = {};
        for (const e of ents) if (!js[e.sid]) js[e.sid] = await D.loadSheet(e.sid);
        if (this.destroyed || this.res !== res) return;
        grid.innerHTML = '';
        ents.forEach((e, k) => {
          const j = js[e.sid]; const cols = j.columns.map((c) => c.label); const row = j.rows[e.row] || [];
          const ix = { docs: j.valve_docs || {} };
          const srcs = (j.valve_src || {})[String(e.row)] || {};
          const tag = U.text(row[cols.indexOf('Valve Tag No.')]);
          const name = (D.meta(e.sid) || {}).name || e.sid;
          const box = U.h('div', { class: 'sum-sig' });
          const head = U.h('div', { class: 'sum-sigh' });
          if (ents.length > 1) head.appendChild(U.h('span', { class: 'pill plain' }, `閥 ${k + 1}/${ents.length}`));
          head.appendChild(U.h('span', { class: 'sum-sigi key mono', title: '氣動閥清單位號' }, tag));
          if (e.unit) head.appendChild(U.h('span', { class: 'sum-sigi', title: '此設備所在機組' }, '本卡＝' + e.unit));
          if (e.cmp === 'mismatch') head.appendChild(U.h('span', { class: 'pill bad' }, '⚠ 定位器廠牌與 AMS 不符'));
          const nTwo = Object.values(srcs).filter((s) => s && s[3]).length;
          if (nTwo) head.appendChild(U.h('span', { class: 'pill warn', title: '兩份一手文件讀法不同的格（點來源看 A／B 讀法）' }, `兩讀 ${nTwo} 格`));
          head.appendChild(U.h('a', { class: 'lk small', href: '#/s/' + encodeURIComponent(e.sid) + '?r=' + e.row }, `在 ${name} 開啟此列（全部欄位）›`));
          box.appendChild(head);
          const sg = U.h('div', { class: 'cfields sumgrid' });
          if (e.how) sg.appendChild(this.fieldEl({ label: 'AMS 對照', val: e.how + (e.note ? '；' + e.note : ''), src: { lvl: 'inferred', text: '推論 · 閥位號（xx／x0 依涵蓋機組展開）或 GE 舊位號 ↔ AMS 位號索引；多代理逐筆驗證（pneuvalve_site.py）' } }, mode));
          if (e.cmp) {
            const fl = e.cmp === 'mismatch' ? [{ t: '⚠ 不符', cls: 'bad' }] : e.cmp === 'absent' ? [{ t: '清單寫無定位器', cls: 'warn' }] : e.cmp === 'ok' ? [{ t: '✓ 一致', cls: 'ok' }] : [];
            sg.appendChild(this.fieldEl({ label: '定位器（清單 ↔ AMS）', val: e.cmpText, warn: e.cmp === 'mismatch', flags: fl, src: { lvl: 'inferred', text: '推論 · 清單「Positioner 定位器」欄 vs AMS 製造商＋型號，比廠牌家族；以現場銘牌為準' } }, mode));
          }
          for (const [lab, col] of V.fields || []) {
            const ci = cols.indexOf(col); if (ci < 0) continue;
            const val = U.cardValue(row[ci]);
            const s = srcs[col];
            const soft = /^(查無|待查|N\/A)/.test(String(val));
            const detail = s ? this.docDetail(ix, s[2], []) : [];
            const flags = [];
            if (s && s[3]) {
              const t = s[3]; flags.push({ t: '兩讀', cls: 'warn' });
              detail.push(['讀法 A', `${t[0] || '—'}（${t[1] || '出處未記'}）`]); detail.push(['讀法 B', `${t[2] || '—'}（${t[3] || '出處未記'}）`]);
              if (t[4]) detail.push(['表內採用', t[4]]);
              if (t[5]) detail.push(['備註', t[5]]);
            }
            const href = s && s[2] ? this.docHref(ix, s[2]) : null;
            sg.appendChild(this.fieldEl({ label: lab, val, soft, flags, href, hrefTitle: href ? this.docTitle(ix, s[2]) : null, src: s ? { lvl: s[0], text: s[1], detail } : null }, mode));
          }
          box.appendChild(sg);
          grid.appendChild(box);
        });
        if (V.list_url) grid.appendChild(U.h('p', { class: 'muted small aux-note' }, '正本（可編輯）：', U.h('a', { class: 'lk', href: V.list_url, target: '_blank', rel: 'noopener noreferrer' }, (V.list_name || 'Google 試算表') + ' ↗')));
        this.applyMode();
      } catch (err) { console.error(err); grid.innerHTML = `<p class="muted cl-empty">無法載入氣動閥清單：${U.esc(err.message)}</p>`; }
    }

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
        ? `<p>你是不是要找（含「${U.esc(q)}」的鍵）：</p><div class="nf-chips">${sg.map((it) => `<a class="chip-btn" href="#/card/${encodeURIComponent(it.key)}"><span class="mono">${AMS.hilite(it.key, q)}</span><span class="muted small">${U.esc([it.src, it.alias].filter(Boolean).join(' · '))}</span></a>`).join('')}</div>`
        : '<p class="muted">位號索引中沒有包含這個字串的鍵。</p>')
        + `<p><a class="lk" href="${U.esc('#/s/' + encodeURIComponent(ixId) + '?q=' + encodeURIComponent(q))}">在 ${U.esc(ixName)} 搜尋「${U.esc(q)}」（所有欄位）›</a></p>`;
      // 氣動閥清單裡相近的閥（位號／GE 舊位號／名稱包含輸入字串）＋到 57／58 全欄位搜尋
      const V = this.spec.valve;
      if (V) {
        const vs = Array.isArray(res.vsg) ? res.vsg : AMS.valves.suggest(V, q, 12);
        if (vs.length) {
          const blk = U.h('div', { class: 'nf-valves' }, U.h('p', {}, '氣動閥清單中相近的閥：'));
          const ch = U.h('div', { class: 'nf-chips' });
          for (const it of vs) ch.appendChild(U.h('a', { class: 'chip-btn', href: '#/card/' + encodeURIComponent(it.key) }, U.h('span', { class: 'mono' }, it.key), U.h('span', { class: 'muted small' }, ' ' + [it.rows > 1 ? it.rows + ' 列' : it.tag, it.alias].filter(Boolean).join(' · '))));
          blk.appendChild(ch); inner.appendChild(blk);
        }
        for (const sid of Object.keys(V.sheets || {})) inner.appendChild(U.h('p', {}, U.h('a', { class: 'lk', href: '#/s/' + encodeURIComponent(sid) + '?q=' + encodeURIComponent(q) }, `在 ${V.sheets[sid]} 搜尋「${q}」（所有欄位）›`)));
      }
      // 兩邊都沒有包含這個字串的鍵：列打錯字的相近鍵（S/5、O/0 這類易混字元、差一兩個字）。只列出，不自動開
      if (!sg.length && !inner.querySelector('.nf-valves') && AMS.fuzzy) {
        let fz = Array.isArray(res.fz) ? res.fz : null;
        if (!fz) { try { fz = AMS.fuzzy(V || null, q, 8); } catch (e) { fz = []; } }
        if (fz.length) {
          const blk = U.h('div', { class: 'nf-fuzzy' }, U.h('p', {}, '是不是打錯字？相近的鍵：'));
          const ch = U.h('div', { class: 'nf-chips' });
          for (const it of fz) ch.appendChild(U.h('a', { class: 'chip-btn', href: '#/card/' + encodeURIComponent(it.key) }, U.h('span', { class: 'mono' }, it.key), U.h('span', { class: 'muted small' }, ' ' + [it.src, it.tag && it.tag !== it.key ? it.tag : '', it.alias].filter(Boolean).join(' · '))));
          blk.appendChild(ch); inner.insertBefore(blk, inner.firstChild);
        }
      }
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
      if (!blank) v.dataset.copy = String(o.val); // 摘要格點一下複製用的原值（網址類複製完整網址，不是短標籤）
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
      const cmpKinds = (st) => Object.entries(f.cmp || {}).filter(([k, v]) => v === st && !/_(lo|hi)$/.test(k) && k !== 'dcdas_multi').map(([k]) => CMP_KIND[k] || k);
      const bad = cmpKinds('mismatch');
      if (bad.length) out.push(['bad', '⚠ 量程與 DCS 不符：' + bad.join('、')]);
      const near = cmpKinds('near'); // 同單位、±0.5% span 內但不完全相同：黃色，不併入紅色 ⚠
      if (near.length) out.push(['warn', '≈ 量程近似（請確認）：' + near.join('、')]);
      if (f.cmp && f.cmp.dcdas_multi === 'warn') { // 同位號多個類比通道、各通道量程不一（build_card_aux）
        const n = aux && aux.sec && aux.sec.dcdas && Array.isArray(aux.sec.dcdas.entries) ? aux.sec.dcdas.entries.length : 0;
        out.push(['warn', '控制器多通道量程不一' + (n > 1 ? `（${n} 個通道）` : '')]);
      }
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
        if (d.url && d.url_note) out.push(['Google 雲端硬碟（版次不同）', U.h('span', {}, d.url_note + ' → ', U.h('a', { class: 'lk', href: d.url, target: '_blank', rel: 'noopener noreferrer' }, '開啟 ↗'))]); // 雲端只找到同編號別版次（build_card_aux url_note）
        else if (d.url) out.push(['Google 雲端硬碟', U.h('a', { class: 'lk', href: d.url, target: '_blank', rel: 'noopener noreferrer' }, '開啟檔案 ↗')]);
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
    docTitle(ix, key) { const d = key && ix && ix.docs ? ix.docs[key] : null; return d && d.title ? '在 Google 雲端硬碟開啟：' + d.title + (d.url_note ? '（' + d.url_note + '）' : '') : null; }
    /** 欄位值本身是文件編號（P&ID、邏輯圖、Hook-up 圖、位置圖…）→ index.doc_no 對到「那份文件」：連結開圖本身，不是提到它的來源文件 */
    docNoLink(ix, val) {
      const m = /HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4}/.exec(String(val || ''));
      const key = m && ix && ix.doc_no ? ix.doc_no[m[0]] : null;
      const d = key && ix.docs ? ix.docs[key] : null;
      return d && d.url ? { href: d.url, title: '開啟這份文件：' + d.title + (d.url_note ? '（' + d.url_note + '）' : ''), key } : null;
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
      if (sa.kind === 'hmi') { this.fillHmi(sec, ix, grid, mode, false); return; }   // false＝完整資料區段（整列寬的大圖，不掛 .sum-has-shot）
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
    /** 最近查過（localStorage ams.card.recent，最多 8 筆 {k 查詢鍵, t 位號, a alias}）；靜態方法給頂列搜尋的自動完成共用 */
    static recent() { const r = U.store.get('card.recent', []); return Array.isArray(r) ? r.filter((x) => x && x.k) : []; }
    static recentItems() { return CardView.recent().map((x) => ({ key: x.k, tag: x.t, alias: x.a, src: '最近查過' })); }
    recent() { return CardView.recent(); }
    remember(res, row) {
      const k = res.key; if (!k) return;
      const tag = row ? U.text(row[this.spec.lookup.target_tag_col]) : '';
      const list = this.recent().filter((x) => x.k !== k && !(res.alias && x.a === res.alias));
      // q：同一鍵對到多台且不是第一台時記 ?a=，最近查過／上一個 chip 才回得到同一台
      list.unshift({ k, t: tag && tag !== k ? tag : '', a: res.alias || '', q: res.pick ? '?a=' + encodeURIComponent(res.alias) : '' });
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
          // 主文字位號優先（原查詢是舊位號／HostTag 時，工程師認的是目前位號）；查詢鍵不同時附在後面
          box.appendChild(U.h('a', { class: 'chip-btn', href: '#/card/' + encodeURIComponent(it.k) + (it.q || '') }, U.h('span', { class: 'mono' }, it.t || it.k), it.t && it.t !== it.k ? U.h('span', { class: 'small muted' }, ' ' + it.k) : null));
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
      if (tag) { // 複製鈕不再以 navigator.clipboard 存在為條件（copyText 有 execCommand 退路）
        const cb = U.h('button', { type: 'button', class: 'btn xs sum-copy', title: '複製位號' }, '複製');
        cb.addEventListener('click', () => { copyText(tag).then((ok) => { cb.textContent = ok ? '已複製' : '無法複製'; setTimeout(() => { cb.textContent = '複製'; }, 1500); }); });
        tagEl.appendChild(cb);
      }
      // 分享：連結一律是位號式（#/card/<查詢鍵>；多台時加 ?a=<alias> 指定這一台）；navigator.share 沒有就複製連結
      const sb = U.h('button', { type: 'button', class: 'btn xs sum-share', title: '分享此設備的連結' }, '分享');
      sb.addEventListener('click', () => {
        const url = this.shareUrl(res);
        if (navigator.share) navigator.share({ title: document.title, url }).catch(() => {});
        else copyText(url).then((ok) => U.toast(ok ? '已複製連結：' + url : '無法複製，請手動複製網址列'));
      });
      tagEl.appendChild(sb);
      hero.appendChild(tagEl);
      const t = (c) => (c == null ? '' : U.cardValue(row[c]));
      const parts = [[t(H.mfr), t(H.model)].filter(Boolean).join(' '), t(H.proto), t(H.unit)].filter(Boolean);
      hero.appendChild(U.h('div', { class: 'sum-sub' }, parts.map((x) => U.h('span', { class: 'sum-subi' }, x))));
      const svc = U.h('div', { class: 'sum-svc', hidden: true });
      hero.appendChild(svc);
      hero.appendChild(U.h('div', { class: 'sum-flags', hidden: true }));
      // 資料日期列：AMS 資料庫快照（manifest）｜控制器 checkout 區間｜文件索引日期（card/index.json 到達後補齊）
      const asof = U.h('div', { class: 'sum-asof muted small' });
      this.asofEl = asof; this.setAsof(this.auxIx || null);
      hero.appendChild(asof);
      wrap.appendChild(hero);
      // 摘要格的值點一下即複製（只在 .sumgrid：一格一值、字大；連結／按鈕／來源展開不攔、拖曳選字不攔）
      wrap.addEventListener('click', (e) => {
        if (e.target.closest('a, button, summary, .cf-src')) return;
        const v = e.target.closest('.sumgrid .cf-v'); if (!v) return;
        const sel = window.getSelection ? String(window.getSelection()) : '';
        if (sel.trim()) return;
        const txt = v.dataset.copy != null ? v.dataset.copy : (v.querySelector('.cf-t') || {}).textContent;
        if (!txt || !String(txt).trim()) return;
        copyText(txt).then((ok) => U.toast(ok ? '已複製：' + txt : '無法複製'));
      });
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
        const vEnts = g.valve ? this.valveEntries(res.alias) : null;
        if (g.valve && !vEnts.length) continue; // 氣動閥組只給對到氣動閥清單的設備
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
        if (g.valve) { grid.className = 'sum-body'; grid.innerHTML = '<p class="muted cl-empty">載入中…</p>'; this.fillValveGroup(grid, vEnts, res); continue; }
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
    /** 分享用網址：#/card/<查詢鍵>，同一鍵對到多台時加 ?a=<alias>（對方打開就是這一台，chips 也還在） */
    shareUrl(res) {
      const u = new URL(location.href);
      u.hash = '#/card/' + encodeURIComponent(res.key) + (typeof res.count === 'number' && res.count > 1 && res.alias ? '?a=' + encodeURIComponent(res.alias) : '');
      return u.href;
    }
    /** 摘要標頭的資料日期列（D1）：不新增規格鍵，直接讀 manifest.workbook.source 的 yyyymmdd 與 card/index.json 的 source_stats／searched */
    asofText(ix) {
      const parts = [];
      const wb = (D.manifest && D.manifest.workbook) || {};
      const m = /(\d{4})(\d{2})(\d{2})/.exec(String(wb.source || ''));
      let ams = m ? `${m[1]}-${m[2]}-${m[3]}` : '';
      const ss = ix && ix.source_stats;
      if (ss && ss.ams && ss.ams.backup_date) ams = String(ss.ams.backup_date);
      if (ams) parts.push('AMS 資料庫 ' + ams);
      const first = (k) => (ix && ix.searched && Array.isArray(ix.searched[k]) && ix.searched[k][0]) || null;
      const dc = first('dcdas');
      if (dc) { // ref＝「控制器 checkout 2025-12-11～2026-09-18（signal-atlas 索引 …）」；沒有 ref 就從 rev（15 台控制器的 checkout 列表）取最早～最晚，不印整串
        const dates = (String(dc.rev || '').match(/\d{4}-\d{2}-\d{2}/g) || []).sort();
        const span = dates.length ? (dates[0] === dates[dates.length - 1] ? dates[0] : dates[0] + '～' + dates[dates.length - 1]) : '';
        const ref = dc.ref ? String(dc.ref).replace(/[（(].*$/, '').trim() : '';
        if (ref || span) parts.push(ref || '控制器 checkout ' + span);
      }
      const ds = first('docsearch');
      if (ds && ds.rev) parts.push('文件索引 ' + ds.rev);
      return parts.length ? '資料：' + parts.join('｜') : '';
    }
    setAsof(ix) { if (!this.asofEl) return; const t = this.asofText(ix); this.asofEl.textContent = t; this.asofEl.hidden = !t; }
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
    kindLabel(kind) { const kl = (this.auxIx && this.auxIx.kind_label) || {}; return kl[kind] || { dcdas: 'DCS 控制器組態', dcdas_ch: '控制器組態（其他通道）', terminal: 'DCS 端子表', instlist: '儀器清單', eomr: 'EOMR', docindex: '文件索引', docsearch: '文件全文檢索', hmi: '圖控 HMI 畫面' }[kind] || kind; }
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
      if (ix) { this.auxIx = ix; this.aux = aux; this.setAsof(ix); }
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
      if (g.kind === 'hmi') { this.fillHmi(sec, ix, grid, mode, true); return; }   // true＝摘要組（寬容器時左欄位右縮圖）
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

    /** 圖控 HMI 畫面位置（card aux `sec.hmi`，CONTRACT.md「圖控 HMI 畫面位置」）：
     *  rows 每（畫面, 選單機組）一組 4 列（圖控畫面／導覽路徑／所在位置／對應方式），以 extra.g 分組，
     *  第一列的 extra 帶 nav／img／marks。摘要組與完整資料區段都有縮圖＋紅圈（標記以百分比疊上去，不燒進影像，
     *  所以同一張圖可給多個位號共用）；`inSum` 只決定版面——摘要組的畫面塊掛 `.sum-has-shot`，寬容器（容器查詢 ≥ 1150px）時
     *  左欄四個欄位、右欄縮圖；完整資料區段維持整列寬的大圖。影像本身延後到祖先 <details> 展開才抓（whenDetailsOpen）。 */
    fillHmi(sec, ix, grid, mode, inSum) {
      grid.innerHTML = '';
      grid.classList.remove('cfields', 'sumgrid');   // 每個畫面一塊（內含自己的 .cfields），不是一格一欄
      grid.classList.add('hmi-body');
      const hx = (ix && ix.hmi) || {};
      const rows = (sec && sec.rows) || [];
      if (!rows.length) {
        const ff = !!(this.aux && this.aux.flags && this.aux.flags.ff);
        const st = (hx.stats) || {};
        const n = st.screens_total || 0;
        // 掃描範圍要一次講完，不然同一張卡會出現「已掃 248」與來源說明的「473 個 .cim」兩個數字（CONTRACT v5）
        const scope = n ? `已掃 ${n} 個操作員畫面` + (st.excluded
          ? `，另 ${st.excluded} 個子目錄元件面板／函式庫${st.excluded_scanned ? '也掃過字串' : '未列入索引'}（共 ${st.screens_all || (n + st.excluded)} 個 .cim）` : '') : '';
        grid.appendChild(U.h('p', { class: 'muted cl-empty' }, ff
          ? `查無（FF 訊號不在控制器 I/O 索引，位號字串也不出現在任何圖控畫面檔${scope ? '；' + scope : ''}）`
          : `查無（${scope ? scope + '：' : ''}這些畫面都沒有引用此位號）`));
        return;
      }
      const list = U.h('div', { class: 'hmi-list' });
      const loaders = [];   // 每張縮圖的影像載入函式；收合中先不跑（見下方 whenDetailsOpen）
      const groups = [];
      for (const r of rows) {
        const ex = (r.length > 4 && r[4]) || {};
        const g = groups.length && groups[groups.length - 1].g === ex.g ? groups[groups.length - 1] : null;
        if (g) g.rows.push(r);
        else groups.push({ g: ex.g, head: ex, rows: [r] });
      }
      for (const grp of groups) {
        const ex = grp.head;
        const title = U.cardValue(grp.rows[0][1]);
        const meta = (hx.screens && hx.screens[ex.s]) || {};
        const navTxt = (ex.nav || []).map((p) => p.filter(Boolean).join(' › ')).join('；');
        const block = U.h('div', { class: 'hmi-screen' });
        // ex.unit 是「開啟這張畫面的那一列選單項的機組欄」，不是儀器所屬機組（同一張畫面會被兩列選單以兩組畫面變數開啟）；
        // ex.nav_all=1 代表選單列與這台儀器對不起來，列出的是該畫面全部選單列（審查意見 8／10a）
        const head = U.h('div', { class: 'hmi-head' },
          U.h('span', { class: 'hmi-t' }, title),
          navTxt ? U.h('span', { class: 'hmi-nav' }, navTxt) : null,
          ex.nav_all ? U.h('span', { class: 'hmi-allnav', title: '這張畫面的全部選單列（無法判定這台儀器是從哪一列開啟）' }, '（此畫面全部選單列）') : null,
          ex.unit ? U.h('span', { class: 'hmi-unit', title: '開啟這張畫面的選單項所屬機組，不是這台儀器所屬機組' }, '以選單機組 ' + ex.unit + ' 開啟') : null,
          U.h('span', { class: 'hmi-file mono' }, ex.s));
        block.appendChild(head);
        // sum-has-shot：摘要組裡有縮圖的區塊才在寬容器下左右並排（左欄位右縮圖，app.css 的 @container hmilist）。
        // class 只在摘要路徑掛：完整資料區沒有宣告 container-name 的祖先，掛了目前無害但是日後的陷阱。
        if (ex.img && meta.file) {
          // 摘要組：渲染時就載圖。延後到展開才載行不通——點開摘要組會觸發重新渲染並把它恢復成收合，
          // toggle 監聽留在被換掉的舊 <details> 上，縮圖永遠停在 loading（2026-10-03 使用者回報「沒有看到圖控畫面」）。
          // 完整資料區（.cq-more）仍延後：那一區預設收合，展開是明確動作，不會被重新渲染重置。
          if (inSum) block.classList.add('sum-has-shot');
          block.appendChild(this.hmiShot(meta, ex, title, inSum ? null : loaders));
        } else block.appendChild(U.h('p', { class: 'muted small hmi-noimg' }, '此畫面檔未內含設計時影像（.cim 沒有 ThumbNail 串流），只能顯示畫面名稱與導覽路徑。'));
        const fields = U.h('div', { class: 'cfields hmi-f' });
        for (const r of grp.rows) {
          fields.appendChild(this.fieldEl({ label: r[0], val: U.cardValue(r[1]), span: r[0] === '導覽路徑' || r[0] === '對應方式' ? 2 : undefined,
            src: r[3] ? { lvl: r[2], text: r[3] } : null }, mode));
        }
        block.appendChild(fields);
        list.appendChild(block);
      }
      grid.appendChild(list);
      // 收合中不抓影像：摘要組與完整資料區段都是「卡片一渲染就填好」（不是展開才填），而每張畫面影像是 70–105 KB 的密文
      // （抓 → AES-GCM 解密 → gunzip → base64 → blob）。同 line 346「完整資料收合時不載變更歷程」的作法，等真的展開再載。
      this.whenDetailsOpen(grid, () => loaders.forEach((f) => f()));
      const noimg = groups.filter((g) => !g.head.img).length;
      if (noimg && groups.length > noimg) grid.appendChild(U.h('p', { class: 'muted small aux-note' }, `其中 ${noimg} 個畫面檔未內含設計時影像。`));
    }
    /** el 位在收合的 <details>（摘要組預設收起、完整資料區 .cq-more）內時，等祖先全部展開才跑 load，而且只跑一次；
     *  都已經展開就立刻跑。注意 beforeprint 會強制展開全部 <details>，但 load 是非同步的，沒展開過的組第一次列印
     *  可能只印到 .hmi-frame.loading 佔位框（與「參數現值」同一個已知取捨；佔位文字在列印時會說明原因）。 */
    whenDetailsOpen(el, load) {
      // 以「元素真的可見」當觸發，不靠祖先 <details> 的 toggle 事件鏈：摘要組的 grid 在 fillSumGroup 當下
      // 的祖先鏈不保證已經接上（2026-10-03 實測摘要組展開後 toggle never fired，縮圖永遠停在 loading）。
      let done = false;
      let io = null;
      const run = () => { if (done || this.destroyed) return; done = true; if (io) io.disconnect(); load(); };
      const closed = () => {
        for (let d = el.closest('details'); d; d = d.parentElement ? d.parentElement.closest('details') : null) if (!d.open) return true;
        return false;
      };
      const visible = () => el.getClientRects().length > 0 && !closed();
      if (visible()) { run(); return; }
      if (typeof IntersectionObserver === 'function') {
        io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting || e.boundingClientRect.height > 0)) run(); });
        io.observe(el);
      }
      for (let d = el.closest('details'); d; d = d.parentElement ? d.parentElement.closest('details') : null) {
        d.addEventListener('toggle', () => { if (visible()) run(); });
      }
      window.addEventListener('beforeprint', run, { once: true });   // 列印一定要有圖
    }
    /** 一張畫面縮圖＋標記（按鈕：點開燈箱放大）。影像 JSON 解密後轉 blob URL（core.js D.loadHmiImage）。
     *  loaders 有給就把載入函式推進去（由 whenDetailsOpen 在展開後才跑），沒給就立刻載。 */
    hmiShot(meta, ex, title, loaders) {
      const btn = U.h('button', { type: 'button', class: 'hmi-shot', 'aria-label': '放大畫面：' + title, title: '點擊放大' });
      const frame = this.hmiFrame(meta, ex);
      btn.appendChild(frame);
      btn.appendChild(U.h('span', { class: 'hmi-zoom', 'aria-hidden': 'true' }, '⤢ 放大'));
      const load = () => D.loadHmiImage(meta.file).then((o) => {
        if (this.destroyed) return;
        const img = U.h('img', { class: 'hmi-img', src: o.url, alt: title + ' 畫面縮圖（設計時影像）', decoding: 'async', width: o.w || null, height: o.h || null });
        frame.insertBefore(img, frame.firstChild);
        frame.classList.remove('loading');
      }).catch((e) => { if (!this.destroyed) { frame.classList.remove('loading'); frame.appendChild(U.h('span', { class: 'muted small hmi-err' }, '無法載入畫面影像：' + ((e && e.message) || e))); } });
      if (loaders) loaders.push(load); else load();
      btn.addEventListener('click', () => this.openHmiLightbox(meta, ex, title));
      return btn;
    }
    /** 影像容器：標記以百分比絕對定位（放大時自動同步縮放）；框寬／高為 0 的（直線、文字錨點）只標點不畫框。
     *  多處時每個標記旁邊掛編號 ①②③（marks[0]＝「所在位置」那列描述的那處，見 index.hmi.note）：
     *  同一位號的兩處常常只差幾個像素，沒有編號使用者看不出有兩個圈，也對不上「另有 N 處」。 */
    hmiFrame(meta, ex) {
      const frame = U.h('span', { class: 'hmi-frame loading' });
      const w = Number(meta.w) || 1280; const h = Number(meta.h) || 720;
      frame.style.aspectRatio = w + ' / ' + h;
      const marks = ex.marks || [];
      const CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫';
      marks.forEach((m, i) => {
        const cx = (Number(m[0]) * 100).toFixed(3); const cy = (Number(m[1]) * 100).toFixed(3);
        const mw = Number(m[2]) || 0; const mh = Number(m[3]) || 0;
        const pri = i === 0 ? ' pri' : '';
        if (mw > 0 && mh > 0) {
          frame.appendChild(U.h('span', { class: 'hmi-box' + pri, 'aria-hidden': 'true',
            style: `left:${((Number(m[0]) - mw / 2) * 100).toFixed(3)}%;top:${((Number(m[1]) - mh / 2) * 100).toFixed(3)}%;width:${(mw * 100).toFixed(3)}%;height:${(mh * 100).toFixed(3)}%` }));
        }
        frame.appendChild(U.h('span', { class: 'hmi-mk' + pri, 'aria-hidden': 'true', style: `left:${cx}%;top:${cy}%` }));
        if (marks.length > 1) {
          // 編號擺在圈「旁邊」，而且逐個錯開（第 1 個右上、第 2 個右下…）：兩個圈幾乎重疊時編號才不會也疊在一起
          frame.appendChild(U.h('span', { class: 'hmi-no' + pri, 'aria-hidden': 'true',
            style: `left:${cx}%;top:${cy}%;transform:translate(10px,${(i % 2 ? 1 : -1) * (130 + Math.floor(i / 2) * 115)}%)` },
            CIRCLED[i] || String(i + 1)));
        }
      });
      if (marks.length > 1) frame.appendChild(U.h('span', { class: 'sr-only' }, `此位號在這張畫面有 ${marks.length} 處標記，標記 ① 是「所在位置」那列描述的那處。`));
      return frame;
    }
    /** 放大：全螢幕疊層（Esc／點背景／✕ 關閉、手機返回鍵也關；標記同步縮放，因為是百分比定位）。 */
    openHmiLightbox(meta, ex, title) {
      const ov = U.h('div', { class: 'modal hmi-lb', role: 'dialog', 'aria-modal': 'true', 'aria-label': '畫面放大：' + title });
      const panel = U.h('div', { class: 'hmi-lb-panel' });
      const close = U.h('button', { class: 'icon-btn modal-x', type: 'button', 'aria-label': '關閉放大檢視' }, '✕');
      const cap = U.h('div', { class: 'hmi-lb-cap' }, U.h('span', { class: 'hmi-t' }, title),
        U.h('span', { class: 'hmi-file mono' }, ex.s),
        U.h('span', { class: 'muted small' }, '設計時影像（值顯示為 ###）；紅圈＝此位號的物件位置'
          + ((ex.marks || []).length > 1 ? `，共 ${ex.marks.length} 處，① 是「所在位置」那列描述的那處` : '')));
      const frame = this.hmiFrame(meta, ex);
      frame.classList.add('big');
      const ar = (Number(meta.w) || 1280) / (Number(meta.h) || 720);
      frame.style.maxWidth = `min(100%, calc((100dvh - 152px) * ${ar.toFixed(4)}))`;   // 108px 說明列 ＋ ✕ 自己那一列
      panel.append(close, frame, cap);
      ov.appendChild(panel);
      document.body.appendChild(ov);
      document.body.classList.add('modal-open');
      D.loadHmiImage(meta.file).then((o) => {
        const img = U.h('img', { class: 'hmi-img', src: o.url, alt: title + ' 畫面（設計時影像）' });
        frame.insertBefore(img, frame.firstChild);
        frame.classList.remove('loading');
      }).catch(() => { frame.classList.remove('loading'); });
      let closed = false; let tok = null;
      const done = (fromHistory) => {
        if (closed) return;
        closed = true;
        ov.remove();
        document.removeEventListener('keydown', onKey, true);
        window.removeEventListener('hashchange', onHash);
        if (!document.querySelector('.modal')) document.body.classList.remove('modal-open');
        if (!fromHistory) AMS.overlay.done(tok);
      };
      const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); done(false); } };
      const onHash = () => done(false);
      close.addEventListener('click', () => done(false));
      ov.addEventListener('pointerdown', (e) => { if (e.target === ov || e.target === panel) done(false); });
      ov.addEventListener('ams-close', () => done(false));
      document.addEventListener('keydown', onKey, true);
      window.addEventListener('hashchange', onHash);
      tok = AMS.overlay.open('modal', () => done(true), true);   // force：平板／桌機按返回鍵也只關燈箱，不離開這張卡
      close.focus();
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
          const rn = r != null && Number(n) > 0 ? r + Number(n) - 1 : null; // 此設備的最後一列：分塊表只載需要的分塊（table.js）
          cell.innerHTML = `<a class="lk" href="${sheetHref(sid, { r, rn })}">${U.esc(fill(lk.fmt || '→ 參數 {n} 筆', { n: n == null ? '' : String(n) }))}</a>`;
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
          <a class="lk" href="${sheetHref(sid, { r: g0, rn: g0 + n - 1, f: { 1: '=' + alias } })}">在 ${U.esc(D.meta(sid) ? D.meta(sid).name : sid)} 開啟（篩選此設備）›</a></div>
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
      U.$$('.hmi-lb').forEach((m) => m.dispatchEvent(new CustomEvent('ams-close')));
      if (D.revokeHmiImages) D.revokeHmiImages();   // 圖控縮圖的 blob URL 與影像 JSON 快取
      if (this.ro) { this.ro.disconnect(); this.ro = null; }
      window.removeEventListener('beforeprint', this._bp);
      window.removeEventListener('afterprint', this._ap);
    }
  }
  AMS.CardView = CardView;
})();
