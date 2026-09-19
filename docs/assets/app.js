/* AMS 解析網頁 — 啟動、路由、側欄、主題、全域搜尋 */
'use strict';
(function () {
  const AMS = window.AMS;
  const U = AMS.U;
  const D = AMS.data;
  const MODE_ICON = { table: '▦', grid: '▤', card: '◧' };
  const MODE_LABEL = { table: '表格', grid: '版面', card: '查詢卡' };

  /* ------------------------------------------------------------ 路由 */
  const R = (AMS.router = {});
  let current = null; // {view, id, instance}
  let ignoreHash = null;
  R.parse = function (hash) {
    const h = (hash || '').replace(/^#/, '');
    let m;
    if ((m = /^\/s\/([^?]+)(?:\?(.*))?$/.exec(h))) {
      let id = m[1];
      try { id = decodeURIComponent(id); } catch (e) { /* 截斷的 %XX：保留原字串 → 找不到工作表 */ }
      return { view: 'sheet', id, params: new URLSearchParams(m[2] || '') };
    }
    if ((m = /^\/card\/?(.*)$/.exec(h))) {
      let q = m[1];
      try { q = decodeURIComponent(q); } catch (e) { /* 保留原字串 */ }
      return { view: 'card', query: m[1] === '' ? null : q, params: new URLSearchParams() };
    }
    return null;
  };
  R.current = () => (current ? current.instance : null); // 目前的檢視（除錯／自動化測試用）
  R.go = function (hash) {
    if (location.hash === hash) { route(); return; }
    // 手機覆蓋層開著（其歷史是同網址的一筆）：以 replace 取代它，返回鍵才會回到原工作表
    if (AMS.overlay.live()) { AMS.overlay.forgetAll(); location.replace(hash); return; }
    location.hash = hash;
  };
  R.replace = function (hash) {
    if (location.hash === hash) return;
    ignoreHash = hash;
    try { history.replaceState(history.state, '', hash); } catch (e) { location.replace(hash); }
    setTimeout(() => { if (ignoreHash === hash) ignoreHash = null; }, 0);
  };
  function cardSheetId() {
    const s = (D.sheets || []).find((x) => x.mode === 'card');
    return s ? s.id : '02';
  }
  function route() {
    try { routeInner(); } catch (e) {
      console.error(e);
      const root = U.$('#view');
      root.className = 'view';
      root.innerHTML = `<div class="error-box"><h2>無法開啟此網址</h2><p>${U.esc(e && e.message || String(e))}</p><p><a class="lk" href="#/s/00">回到 00_說明</a></p></div>`;
    }
    maybeCheckVersion();
  }
  function routeInner() {
    if (ignoreHash && location.hash === ignoreHash) { ignoreHash = null; return; }
    // 路由變更一律關閉浮在上面的區塊表格（瀏覽器返回、點連結、全域搜尋…）
    U.$$('.modal').forEach((m) => m.dispatchEvent(new CustomEvent('ams-close')));
    let rt = R.parse(location.hash);
    if (!rt) {
      // manifest.landing = 'card'：沒有網址片段時直接開設備查詢（登入後即查詢頁）
      if (D.manifest && D.manifest.landing === 'card' && D.sheets.some((s) => s.mode === 'card')) { location.replace('#/card/'); return; }
      const first = (D.manifest && D.manifest.default_sheet) || (D.sheets[0] && D.sheets[0].id) || '00';
      location.replace('#/s/' + first);
      return;
    }
    let id = rt.view === 'card' ? cardSheetId() : rt.id;
    let meta = D.meta(id);
    if (!meta) {
      // 允許用完整名稱或兩碼數字
      const byName = D.byName.get(id) || D.sheets.find((s) => s.id === String(id).padStart(2, '0'));
      if (byName) { meta = byName; id = byName.id; }
    }
    if (!meta) { showNotFound(id); return; }
    if (meta.mode === 'card' && rt.view === 'sheet') rt = { view: 'card', query: rt.params.get('q'), params: rt.params };
    const key = meta.mode + ':' + id;
    if (current && current.key === key && current.instance.update) {
      current.instance.update(rt);
    } else {
      if (current && current.instance.destroy) current.instance.destroy();
      if (AMS.detail.isOpen()) AMS.detail.close();
      const root = U.$('#view');
      root.innerHTML = '';
      root.scrollTop = 0;
      const Ctor = meta.mode === 'grid' ? AMS.GridView : meta.mode === 'card' ? AMS.CardView : AMS.TableView;
      current = { key, id, instance: new Ctor(root, meta, rt) };
    }
    setActive(id);
    if (meta.mode !== 'card') document.title = `${meta.name} · ${(D.manifest.workbook && D.manifest.workbook.title) || 'AMS 解析'}`;
    closeDrawer();
  }
  function showNotFound(id) {
    const root = U.$('#view');
    if (current && current.instance.destroy) current.instance.destroy();
    current = null;
    root.className = 'view';
    root.innerHTML = `<div class="error-box"><h2>找不到工作表「${U.esc(id)}」</h2><p><a class="lk" href="#/s/00">回到 00_說明</a></p></div>`;
  }

  /* ------------------------------------------------------------ 側欄 */
  function buildSidebar() {
    const nav = U.$('#sheet-nav');
    const groups = [];
    const gm = new Map();
    for (const g of D.manifest.groups || []) { if (!gm.has(g)) { gm.set(g, []); groups.push(g); } }
    for (const s of D.sheets) {
      const g = s.group || '其他';
      if (!gm.has(g)) { gm.set(g, []); groups.push(g); }
      gm.get(g).push(s);
    }
    for (let i = groups.length - 1; i >= 0; i--) if (!gm.get(groups[i]).length) groups.splice(i, 1);
    const collapsed = new Set(U.store.get('collapsedGroups', []));
    nav.innerHTML = groups.map((g) => {
      const items = gm.get(g).map((s) => {
        const short = s.short || s.name.replace(/^\d+_/, '');
        const rc = s.toc_rows != null ? s.toc_rows : s.rows;
        const rows = rc != null && (s.mode !== 'card' || rc) ? U.int(rc) : '';
        const tip = [s.name, (MODE_LABEL[s.mode] || s.mode) + (s.rows != null && s.mode === 'table' ? '・' + U.int(s.rows) + ' 列' : ''), s.row_unit ? '一列代表：' + s.row_unit : '', s.desc || '', s.sources ? '來源：' + s.sources : ''].filter(Boolean).join('\n');
        const tab = s.tab_color ? ` style="--tab:${U.esc(s.tab_color)}"` : '';
        return `<li><a class="sheet-link${s.tab_color ? ' has-tab' : ''}" href="#/s/${encodeURIComponent(s.id)}" data-id="${U.esc(s.id)}" title="${U.esc(tip)}"${tab}>
          <span class="sl-id">${U.esc(s.id)}</span><span class="sl-name">${U.esc(short)}</span>
          <span class="sl-mode" aria-label="${U.esc(MODE_LABEL[s.mode] || '')}">${MODE_ICON[s.mode] || ''}</span><span class="sl-rows">${rows}</span></a></li>`;
      }).join('');
      const isC = collapsed.has(g);
      return `<div class="sg${isC ? ' collapsed' : ''}"><button type="button" class="sg-h" aria-expanded="${!isC}" data-g="${U.esc(g)}"><span class="caret" aria-hidden="true">▾</span>${U.esc(g)}<span class="sg-n">${gm.get(g).length}</span></button><ul class="sg-list">${items}</ul></div>`;
    }).join('');
    nav.addEventListener('click', (e) => {
      const b = e.target.closest('.sg-h');
      if (!b) return;
      const sg = b.parentElement; sg.classList.toggle('collapsed');
      const on = sg.classList.contains('collapsed');
      b.setAttribute('aria-expanded', String(!on));
      const set = new Set(U.store.get('collapsedGroups', []));
      if (on) set.add(b.dataset.g); else set.delete(b.dataset.g);
      U.store.set('collapsedGroups', Array.from(set));
    });
    U.$('#sheet-count').textContent = `${D.sheets.length} 張`;
    const wb = D.manifest.workbook || {};
    const rel = Array.isArray(wb.related) ? wb.related.filter((x) => x && x.label && typeof x.href === 'string' && /^(\.\.?\/|[\w-]+\/)/.test(x.href)) : [];
    U.$('#sidebar-foot').innerHTML = `${wb.xlsx ? `來源：${U.esc(wb.xlsx)}<br>` : ''}${wb.source ? `資料：${U.esc(wb.source)}<br>` : ''}${wb.built ? `建置：${U.esc(wb.built)}` : ''}${rel.length ? '<br>' + rel.map((x) => `<a class="lk" href="${U.esc(x.href)}">${U.esc(x.label)} ›</a>`).join('<br>') : ''}`;
  }
  function setActive(id) {
    U.$$('.sheet-link').forEach((a) => {
      const on = a.dataset.id === id;
      a.classList.toggle('active', on);
      if (on) { a.setAttribute('aria-current', 'page'); const sg = a.closest('.sg'); if (sg && sg.classList.contains('collapsed')) sg.classList.remove('collapsed'); }
      else a.removeAttribute('aria-current');
    });
    const act = U.$('.sheet-link.active');
    if (act && act.scrollIntoViewIfNeeded) act.scrollIntoViewIfNeeded(false);
  }
  let drawerTok = null;
  function openDrawer() {
    document.body.classList.add('drawer-open'); U.$('#scrim').hidden = false; U.$('#btn-menu').setAttribute('aria-expanded', 'true');
    const a = U.$('.sheet-link.active') || U.$('.sheet-link'); if (a) a.focus();
    drawerTok = AMS.overlay.open('drawer', () => closeDrawer());
  }
  function closeDrawer() {
    if (!document.body.classList.contains('drawer-open')) return;
    document.body.classList.remove('drawer-open'); U.$('#scrim').hidden = true; U.$('#btn-menu').setAttribute('aria-expanded', 'false');
    const t = drawerTok; drawerTok = null; AMS.overlay.done(t);
  }

  /* ------------------------------------------------------------ 新版本偵測（開著的分頁不會自己換 manifest） */
  let lastVerCheck = Date.now();
  let verBanner = null;
  function maybeCheckVersion(force) {
    if (!D.appVersion && !D.pageBuild) return; // 未經 stamp 的開發版
    const now = Date.now();
    if (!force && now - lastVerCheck < 5 * 60 * 1000) return;
    lastVerCheck = now;
    fetch('version.json', { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null)).then((v) => {
      if (!v || verBanner) return;
      const dataChanged = v.build && D.manifest && D.manifest.build && v.build !== D.manifest.build;
      const appChanged = v.app && D.appVersion && v.app !== D.appVersion;
      if (!dataChanged && !appChanged) return;
      verBanner = U.h('div', { class: 'ver-banner', role: 'status' },
        U.h('span', {}, dataChanged ? '資料已更新（新的建置），請重新整理以免新舊資料混用。' : '網頁已更新，請重新整理。'),
        U.h('button', { type: 'button', class: 'btn sm primary', onclick: () => location.reload() }, '重新整理'),
        U.h('button', { type: 'button', class: 'icon-btn', 'aria-label': '稍後', onclick: () => { verBanner.remove(); } }, '✕'));
      document.body.appendChild(verBanner);
    }).catch(() => {});
  }

  /* ------------------------------------------------------------ 主題 */
  function setTheme(t, persist) {
    document.documentElement.setAttribute('data-theme', t);
    if (persist) { try { localStorage.setItem('ams.theme', t); } catch (e) { /* 私密模式 */ } }
    const btn = U.$('#btn-theme');
    if (btn) btn.setAttribute('aria-pressed', String(t === 'dark'));
    if (current && current.instance.onTheme) current.instance.onTheme();
  }

  /* ------------------------------------------------------------ 圖例（00_說明 的色彩對照） */
  async function toggleLegend() {
    const pop = U.$('#legend-pop'); const btn = U.$('#btn-legend');
    if (!pop.hidden) { pop.hidden = true; btn.setAttribute('aria-expanded', 'false'); return; }
    pop.hidden = false; btn.setAttribute('aria-expanded', 'true');
    pop.innerHTML = '<div class="lg-head"><b>圖例</b><span class="muted small">資料來源：00_說明「6 圖例」</span><button type="button" class="icon-btn lg-x" aria-label="關閉圖例">✕</button></div><div class="lg-body"><p class="muted">載入中…</p></div>';
    pop.querySelector('.lg-x').addEventListener('click', () => { pop.hidden = true; btn.setAttribute('aria-expanded', 'false'); btn.focus(); });
    try {
      const j = await D.loadSheet('00');
      const items = j.legend || [];
      if (!items.length) { pop.querySelector('.lg-body').innerHTML = '<p class="muted">（00_說明 沒有圖例資料）</p>'; return; }
      const groups = [];
      const gm = new Map();
      for (const it of items) { const g = it.group || ''; if (!gm.has(g)) { gm.set(g, []); groups.push(g); } gm.get(g).push(it); }
      const theme = U.theme();
      pop.querySelector('.lg-body').innerHTML = groups.map((g) => `<section><h4>${U.esc(g)}</h4><ul>${gm.get(g).map((it) => {
        const a = U.adaptColors(it.bg, it.fc, theme);
        let css = ''; if (a.bg) css += `background:${a.bg};`; if (a.fc) css += `color:${a.fc};`; if (it.b) css += 'font-weight:700;'; if (it.i) css += 'font-style:italic;'; if (it.u) css += 'text-decoration:underline;';
        return `<li><span class="lg-sw${it.bg ? '' : ' nobg'}" style="${css}">${U.esc(it.label)}</span><span class="lg-d">${U.esc(it.desc || '')}</span></li>`;
      }).join('')}</ul></section>`).join('') + '<p class="small"><a class="lk" href="#/s/00?r=63">在 00_說明 查看完整圖例 ›</a></p>';
    } catch (e) { pop.querySelector('.lg-body').innerHTML = `<p class="muted">無法載入：${U.esc(e.message)}</p>`; }
  }

  /* ------------------------------------------------------------ 啟動 */
  async function boot() {
    // 登入閘門（assets/auth.js；auth-config.json 的 endpoint 空白時直接通過）
    if (window.AMSAuth && window.AMSAuth.ready) { try { await window.AMSAuth.ready(); } catch (e) { console.error('auth', e); } }
    U.$('#btn-menu').addEventListener('click', () => (document.body.classList.contains('drawer-open') ? closeDrawer() : openDrawer()));
    U.$('#scrim').addEventListener('click', closeDrawer);
    U.$('#btn-collapse').addEventListener('click', () => {
      const on = document.body.classList.toggle('sidebar-collapsed');
      U.$('#btn-collapse').setAttribute('aria-expanded', String(!on));
      U.store.set('sidebarCollapsed', on);
      window.dispatchEvent(new Event('resize'));
    });
    U.$('#btn-theme').addEventListener('click', () => setTheme(U.theme() === 'dark' ? 'light' : 'dark', true));
    U.$('#btn-legend').addEventListener('click', toggleLegend);
    document.addEventListener('pointerdown', (e) => { const p = U.$('#legend-pop'); if (!p.hidden && !p.contains(e.target) && !U.$('#btn-legend').contains(e.target)) { p.hidden = true; U.$('#btn-legend').setAttribute('aria-expanded', 'false'); } });
    U.$('#legend-pop').addEventListener('keydown', (e) => { if (e.key === 'Escape') { U.$('#legend-pop').hidden = true; U.$('#btn-legend').setAttribute('aria-expanded', 'false'); U.$('#btn-legend').focus(); } });
    U.$('#legend-pop').addEventListener('click', (e) => { if (e.target.closest('a')) { U.$('#legend-pop').hidden = true; } });
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onMq = () => { let saved = null; try { saved = localStorage.getItem('ams.theme'); } catch (e) { /**/ } if (!saved) setTheme(mq.matches ? 'dark' : 'light', false); };
    if (mq.addEventListener) mq.addEventListener('change', onMq);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && document.body.classList.contains('drawer-open')) closeDrawer();
      if (e.key === 'Escape' && !U.$('#legend-pop').hidden) { U.$('#legend-pop').hidden = true; U.$('#btn-legend').setAttribute('aria-expanded', 'false'); }
      if ((e.key === '/' || (e.key === 'k' && (e.ctrlKey || e.metaKey))) && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); U.$('#global-search').focus(); }
    });
    // 再點一次「目前網址」的連結（如 24 的區塊連結、同一列的 ↗）時 hash 不變、不會觸發 hashchange → 手動重新套用路由（重新捲動）
    document.addEventListener('click', (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest && e.target.closest('a[href^="#/"]');
      if (a && a.getAttribute('href') === location.hash) { e.preventDefault(); route(); }
    });
    // 全域搜尋 → 設備查詢卡
    const gs = U.$('#global-search');
    if (U.isMobile()) gs.placeholder = '搜尋位號／alias…'; // 360px 寬時完整提示會被截斷
    new AMS.Autocomplete(gs, Object.assign({}, AMS.tagSuggestSource, {
      onPick: (it) => { gs.value = ''; gs.blur(); R.go('#/card/' + encodeURIComponent(it.key)); },
      onEnter: async (t) => {
        if (!t.trim()) return;
        let key = t;
        // 沒有完全相符的鍵、但只有一個建議時，直接開那一個（例：輸入 HAP70BT00 只對到一台）
        try {
          const IX = AMS.index; await IX.load();
          if (!IX.first.has(IX.norm(t))) { const sg = IX.suggest(t, 2); if (sg.length === 1) key = sg[0].key; }
        } catch (e) { /* 索引載入失敗 → 照原字串查詢 */ }
        gs.blur(); R.go('#/card/' + encodeURIComponent(key)); gs.value = '';
      },
    }));
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') maybeCheckVersion(); });
    try {
      await D.loadManifest();
    } catch (e) {
      U.$('#view').innerHTML = `<div class="error-box"><h2>無法載入 manifest.json</h2><p>${U.esc(e.message)}</p><p class="muted">資料目錄：<code>${U.esc(D.base)}</code>（可用 <code>?data=路徑/</code> 指定）</p></div>`;
      return;
    }
    // 側欄：有記住的偏好就照偏好；否則查詢優先的站台（landing=card）桌機預設收合，讓查詢頁乾淨
    const sc = U.store.get('sidebarCollapsed', null);
    if (sc == null ? (D.manifest.landing === 'card' && !U.isMobile()) : !!sc) { document.body.classList.add('sidebar-collapsed'); U.$('#btn-collapse').setAttribute('aria-expanded', 'false'); }
    const wb = D.manifest.workbook || {};
    if (wb.title) { U.$('#wb-title').textContent = wb.title; }
    if (wb.subtitle) { U.$('#wb-subtitle').textContent = wb.subtitle; U.$('#wb-subtitle').title = wb.subtitle; }
    buildSidebar();
    window.addEventListener('hashchange', route);
    route();
    lastVerCheck = Date.now();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
