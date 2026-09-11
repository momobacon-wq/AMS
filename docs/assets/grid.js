/* AMS 解析網頁 — grid 模式：忠實重現版面（欄寬、列高、合併、樣式、溢出、框線、資料橫條）＋ Chart.js 圖表 */
'use strict';
(function () {
  const AMS = window.AMS;
  const U = AMS.U;
  const D = AMS.data;
  const FONT = '"Microsoft JhengHei","PingFang TC","Noto Sans TC",system-ui,sans-serif';
  const PT = 4 / 3; // pt → px
  const CHART_BREAK = 900; // 小於此寬度時圖表改為依區段堆疊

  /* ------------------------------------------------------------ 樣式 */
  const BW = { hair: 1, thin: 1, medium: 2, thick: 3, dashed: 1, dotted: 1, double: 3, mediumDashed: 2, dashDot: 1, mediumDashDot: 2, dashDotDot: 1, mediumDashDotDot: 2, slantDashDot: 2 };
  const BS = { dashed: 'dashed', mediumDashed: 'dashed', dotted: 'dotted', hair: 'dotted', double: 'double', dashDot: 'dashed', dashDotDot: 'dashed', mediumDashDot: 'dashed', mediumDashDotDot: 'dashed', slantDashDot: 'dashed' };
  const SIDES = { t: 'top', top: 'top', b: 'bottom', bottom: 'bottom', l: 'left', left: 'left', r: 'right', right: 'right' };
  function borderDecl(spec, theme) {
    // spec: "thin" | "thin #BFBFBF" | {style,color} → css "1px solid #xxx"
    if (!spec) return null;
    let style = 'thin'; let color = null;
    if (typeof spec === 'object') { style = spec.style || spec.s || 'thin'; color = spec.color || spec.c || null; }
    else {
      const parts = String(spec).trim().split(/[\s:]+/);
      for (const p of parts) { if (/^#?[0-9a-f]{6}$/i.test(p)) color = p[0] === '#' ? p : '#' + p; else if (p) style = p; }
    }
    if (style === 'none') return null;
    const w = BW[style] || 1; const s = BS[style] || 'solid';
    let c = color ? U.normHex(color) : null;
    if (!c) c = theme === 'dark' ? '#8a93a0' : '#7f7f7f';
    else if (theme === 'dark' && U.lum(c) < 0.25) c = '#8a93a0';
    return `${w}px ${s} ${c}`;
  }
  function bordersCss(bd, theme) {
    if (!bd) return '';
    let css = '';
    if (typeof bd === 'string') {
      // "thin" | "thin #BFBFBF" | "l:thick:#BF8F00" | "t:thin:#000;l:thick:#BF8F00"
      const segs = bd.split(/[;,]/).map((x) => x.trim()).filter(Boolean);
      for (const sg of segs) {
        const m = /^(t|b|l|r|top|bottom|left|right)[:=\s](.+)$/i.exec(sg);
        if (m) { const d = borderDecl(m[2], theme); if (d) css += `border-${SIDES[m[1].toLowerCase()]}:${d};`; }
        else { const d = borderDecl(sg, theme); if (d) css += `border:${d};`; }
      }
      return css;
    }
    if (typeof bd === 'object') {
      for (const k in bd) {
        const side = SIDES[k]; if (!side) continue;
        const d = borderDecl(bd[k], theme); if (d) css += `border-${side}:${d};`;
      }
    }
    return css;
  }
  const HA = { left: 'left', center: 'center', centerContinuous: 'center', right: 'right', justify: 'justify', distributed: 'justify', fill: 'left' };
  const VA = { top: 'top', center: 'middle', middle: 'middle', bottom: 'bottom', justify: 'middle', distributed: 'middle' };
  function styleCss(st, theme) {
    if (!st) return { css: '', wrap: false, ha: null };
    let css = '';
    if (st.b) css += 'font-weight:700;';
    if (st.i) css += 'font-style:italic;';
    if (st.u || st.s_) css += 'text-decoration:underline;';
    if (st.strike) css += 'text-decoration:line-through;';
    if (st.sz) css += `font-size:${(st.sz * PT).toFixed(2)}px;`;
    const a = U.adaptColors(st.bg, st.fc, theme);
    if (a.bg) css += `background-color:${a.bg};`;
    if (a.fc) css += `color:${a.fc};`;
    const ha = HA[st.ha] || null;
    if (ha) css += `text-align:${ha};`;
    css += `vertical-align:${VA[st.va] || 'bottom'};`;
    if (st.mono) css += 'font-family:Consolas,"Cascadia Mono","Noto Sans Mono CJK TC","MingLiU",monospace;';
    if (st.ind) css += `padding-left:${4 + st.ind * 9}px;`;
    if (st.rot) css += ''; // 旋轉文字：不支援，維持水平
    css += bordersCss(st.bd, theme);
    return { css, wrap: !!st.wrap, ha, bg: !!a.bg, fc: !!a.fc };
  }

  /* ------------------------------------------------------------ 表格建構 */
  function colNum(x) { // 1-based 欄號；支援 "AB"
    if (typeof x === 'number') return x;
    let n = 0; for (const ch of String(x).toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64);
    return n;
  }
  /**
   * 建立 grid <table>；回傳 {table, trs: Map(r→tr), colLeft(c), maxCol, maxRow, visCols}
   */
  function buildGridTable(g, opt) {
    opt = opt || {};
    const theme = U.theme();
    const styles = g.styles || [];
    const sCache = new Map();
    const sty = (i) => { if (i == null) return null; let r = sCache.get(i); if (!r) { r = styleCss(typeof i === 'object' ? i : styles[i], theme); sCache.set(i, r); } return r; };
    const hiddenCols = new Set((g.hidden_cols || []).map(colNum));
    const hiddenRows = new Set(g.hidden_rows || []);
    const widths = g.col_widths || [];
    let maxCol = widths.length; let maxRow = 0;
    const rowMap = new Map();
    for (const row of g.rows || []) {
      rowMap.set(row.r, row);
      if (row.r > maxRow) maxRow = row.r;
      for (const c of row.cells || []) {
        const e = c.c + Math.max(1, c.cs || 1) - 1 + (c.ov || 0);
        if (e > maxCol) maxCol = e;
        const er = row.r + Math.max(1, c.rs || 1) - 1;
        if (er > maxRow) maxRow = er;
      }
    }
    for (const ch of g.charts || []) {
      const a = ch.anchor || {};
      if (a.to) { if (a.to.c > maxCol) maxCol = a.to.c; if (a.to.r > maxRow) maxRow = a.to.r; }
      if (a.from) { if (a.from.c > maxCol) maxCol = a.from.c; if (a.from.r > maxRow) maxRow = a.from.r; }
    }
    for (const s of g.sections || []) if (s.r > maxRow) maxRow = s.r;
    if (g.max_row && g.max_row > maxRow) maxRow = g.max_row;
    if (g.max_col && g.max_col > maxCol) maxCol = g.max_col;
    if (opt.extraCols) maxCol += opt.extraCols;
    const defW = g.default_col_w || 64;
    const cw = (c) => (hiddenCols.has(c) ? 0 : (widths[c - 1] != null ? widths[c - 1] : defW));
    const left = [0, 0]; // left[c] = x of col c (1-based)
    for (let c = 1; c <= maxCol + 1; c++) left[c + 1] = left[c] + cw(c);
    const gridlines = g.gridlines !== false;
    const table = document.createElement('table');
    table.className = 'gx' + (gridlines ? ' gl' : '');
    let totalW = left[maxCol + 1];
    table.style.width = totalW + 'px';
    let cg = '<colgroup>';
    for (let c = 1; c <= maxCol; c++) if (!hiddenCols.has(c)) cg += `<col style="width:${cw(c)}px">`;
    cg += '</colgroup>';
    const covered = new Map(); // r → Set(c)
    const cover = (r, c) => { let s = covered.get(r); if (!s) covered.set(r, (s = new Set())); s.add(c); };
    let html = cg + '<tbody>';
    const visCount = (c0, c1) => { let n = 0; for (let c = c0; c <= c1; c++) if (!hiddenCols.has(c)) n++; return n; };
    for (let r = 1; r <= maxRow; r++) {
      if (hiddenRows.has(r)) continue;
      const row = rowMap.get(r);
      const cells = new Map();
      if (row) for (const c of row.cells || []) cells.set(c.c, c);
      const cov = covered.get(r);
      let h = row && row.h != null ? row.h : null;
      const empty = !row || !(row.cells && row.cells.length);
      if (h == null && empty && !(cov && cov.size)) h = 20;
      let tr = `<tr data-r="${r}"${h != null ? ` style="height:${h}px"` : ''}${empty ? ' class="er"' : ''}>`;
      for (let c = 1; c <= maxCol; c++) {
        if (cov && cov.has(c)) continue;
        const cell = cells.get(c);
        if (!cell) { if (!hiddenCols.has(c)) tr += '<td></td>'; continue; }
        const cs = Math.max(1, cell.cs || 1); const rs = Math.max(1, cell.rs || 1);
        let ov = cell.ov || 0;
        // 溢出只能延伸到真的空白格
        if (ov) { let k = 0; while (k < ov && !cells.has(c + cs + k) && !(cov && cov.has(c + cs + k)) && c + cs + k <= maxCol) k++; ov = k; }
        const span = cs + ov;
        for (let rr = r; rr < r + rs; rr++) for (let cc = c; cc < c + span; cc++) if (rr !== r || cc !== c) cover(rr, cc);
        const vis = visCount(c, c + span - 1);
        if (!vis || hiddenCols.has(c) && vis === 0) continue;
        tr += cellHTML(cell, sty(cell.s), vis, rs, ov > 0);
        // cover 同列後續欄
        c += span - 1;
      }
      tr += '</tr>';
      html += tr;
    }
    html += '</tbody>';
    table.innerHTML = html;
    const trs = new Map();
    table.querySelectorAll('tr[data-r]').forEach((tr) => trs.set(Number(tr.dataset.r), tr));
    return { table, trs, left, maxCol, maxRow, totalW, rowMap };
  }
  function cellHTML(cell, st, cs, rs, overflow) {
    let v = cell.v;
    let link = cell.l || null; let url = cell.u || null;
    if (v && typeof v === 'object') { if (v.l) link = v.l; if (v.u) url = v.u; }
    const raw = U.raw(v);
    const fmt = cell.f || (v && typeof v === 'object' && v.f) || null;
    let txt = cell.d != null ? String(cell.d) : (U.isBlank(raw) ? '' : U.display(v, fmt));
    let cls = [];
    let css = st ? st.css : 'vertical-align:bottom;';
    if (!st || !st.ha) { if (typeof raw === 'number') cls.push('ar'); else if (typeof raw === 'boolean') cls.push('ac'); }
    const wrap = st && st.wrap;
    cls.push(wrap ? 'wr' : 'nw');
    if (overflow) cls.push('ov');
    let inner = U.esc(U.visible(txt, true));
    if (link) {
      const href = AMS.linkHref(link);
      inner = `<a class="glk${st && st.fc ? ' inh' : ''}" href="${href}">${inner}</a>`;
    } else if (url && /^(https?:|mailto:)/i.test(url)) inner = `<a class="glk" href="${U.esc(url)}" target="_blank" rel="noopener noreferrer">${inner}</a>`;
    if (cell.bar) {
      const p = U.clamp(Number(cell.bar.p) || 0, 0, 1);
      // Excel 資料橫條（無 x14 擴充）：minLength 10%、maxLength 90% → 長度 = 10% + 80%·p
      inner = `<i class="gbar" style="width:${(10 + 80 * p).toFixed(1)}%;--bc:${U.esc(cell.bar.c || '#638EC6')}"></i><span class="bv">${inner}</span>`;
      cls.push('hasbar');
    }
    const title = !wrap && txt.length > 40 ? ` title="${U.esc(txt)}"` : '';
    return `<td data-c="${cell.c}"${cs > 1 ? ` colspan="${cs}"` : ''}${rs > 1 ? ` rowspan="${rs}"` : ''} class="${cls.join(' ')}" style="${css}"${title}>${inner}</td>`;
  }

  /* ------------------------------------------------------------ 圖表 */
  const CH = (AMS.charts = {});
  const dataLabelPlugin = {
    id: 'amsDataLabels',
    afterDatasetsDraw(chart) {
      const dl = chart.options.plugins && chart.options.plugins.amsDataLabels;
      if (!dl || !dl.mode) return;
      const ctx = chart.ctx;
      ctx.save();
      ctx.font = `600 ${dl.size || 11}px ${FONT}`;
      ctx.textBaseline = 'middle';
      const horizontal = chart.options.indexAxis === 'y';
      chart.data.datasets.forEach((ds, di) => {
        const meta = chart.getDatasetMeta(di);
        if (!meta || meta.hidden) return;
        let visTotal = 0;
        if (dl.mode === 'percent') ds.data.forEach((v, i) => { if (chart.getDataVisibility(i)) visTotal += Number(v) || 0; });
        meta.data.forEach((el, i) => {
          const v = ds.data[i];
          if (v == null || !isFinite(v)) return;
          if (dl.mode === 'percent') {
            if (!chart.getDataVisibility(i) || !visTotal) return;
            const p = v / visTotal;
            if (p < (dl.min != null ? dl.min : 0.03)) return;
            const pos = el.tooltipPosition();
            const bg = Array.isArray(ds.backgroundColor) ? ds.backgroundColor[i] : ds.backgroundColor;
            ctx.fillStyle = U.contrastText(bg || '#888');
            ctx.textAlign = 'center';
            ctx.fillText(U.fmt(p, dl.fmt || '0%'), pos.x, pos.y);
          } else {
            const txt = U.fmt(v, dl.fmt || null);
            ctx.fillStyle = dl.color || '#333';
            if (horizontal) { ctx.textAlign = 'left'; ctx.fillText(txt, el.x + 4, el.y); }
            else { ctx.textAlign = 'center'; ctx.fillText(txt, el.x, el.y - 9); }
          }
        });
      });
      ctx.restore();
    },
  };
  // 版面縮放（CSS zoom／transform）時修正滑鼠座標，讓 tooltip／hover 命中正確的圖形
  const zoomFixPlugin = {
    id: 'amsZoomFix',
    beforeEvent(chart, args) {
      const e = args.event; const n = e && e.native;
      if (!n || n.clientX == null) return;
      const cv = chart.canvas; const r = cv.getBoundingClientRect();
      if (!r.width || !cv.clientWidth) return;
      const sx = cv.clientWidth / r.width; const sy = cv.clientHeight / r.height;
      if (Math.abs(sx - 1) < 0.002 && Math.abs(sy - 1) < 0.002) return;
      e.x = (n.clientX - r.left) * sx; e.y = (n.clientY - r.top) * sy;
      args.inChartArea = chart.isPointInArea(e);
    },
  };
  let registered = false;
  function ensureChartJs() {
    if (!window.Chart) return false;
    if (!registered) {
      window.Chart.register(dataLabelPlugin, zoomFixPlugin);
      window.Chart.defaults.font.family = FONT;
      registered = true;
    }
    return true;
  }
  function tickFmt(fmt) { return (v) => (fmt ? U.fmt(v, fmt) : (Math.abs(v) >= 1000 ? U.fmt(v, '#,##0') : U.general(v))); }
  /** chart 規格 → Chart.js 設定 */
  CH.config = function (spec, opt) {
    opt = opt || {};
    const theme = U.theme();
    const txt = theme === 'dark' ? '#cfd6df' : '#404040';
    const gridC = theme === 'dark' ? 'rgba(255,255,255,0.12)' : '#D9D9D9';
    const type0 = spec.type || 'bar';
    const isPie = type0 === 'pie' || type0 === 'doughnut';
    const horizontal = !!spec.horizontal && !isPie;
    const cats = (spec.categories || []).map((c) => (c == null ? '' : String(c)));
    const series = spec.series || [];
    const hasY2 = series.some((s) => s.axis === 'y2');
    const vAx = horizontal ? 'x' : 'y'; const cAx = horizontal ? 'y' : 'x';
    const v2Ax = horizontal ? 'x2' : 'y2';
    const yo = spec.y || {}; const y2o = spec.y2 || {};
    const pctStack = !!spec.percent;
    let values = series.map((s) => (s.values || []).map((v) => (v == null || v === '' ? null : Number(v))));
    if (pctStack) { // 100% 堆疊
      const tot = cats.map((_, i) => values.reduce((a, arr, k) => a + (series[k].axis === 'y2' ? 0 : (arr[i] || 0)), 0));
      values = values.map((arr, k) => (series[k].axis === 'y2' ? arr : arr.map((v, i) => (v == null || !tot[i] ? v : v / tot[i]))));
    }
    const pal = ['#4472C4', '#ED7D31', '#A5A5A5', '#FFC000', '#5B9BD5', '#70AD47', '#264478', '#9E480E'];
    const datasets = series.map((s, k) => {
      const st = s.type === 'line' || (type0 === 'line' && !s.type) || type0 === 'area' ? 'line' : (isPie ? type0 : 'bar');
      const color = s.color || pal[k % pal.length];
      const ds = { label: s.name == null ? '' : String(s.name), data: values[k] };
      if (type0 === 'combo' || series.some((x) => (x.type || type0) !== (s.type || type0))) ds.type = st;
      if (isPie) {
        ds.backgroundColor = s.colors || cats.map((_, i) => pal[i % pal.length]);
        ds.borderColor = s.border || (theme === 'dark' ? '#171c23' : '#FFFFFF');
        ds.borderWidth = 1.5;
        ds.hoverOffset = 4;
      } else if (st === 'line') {
        Object.assign(ds, {
          borderColor: color, backgroundColor: type0 === 'area' ? color + '66' : color,
          borderWidth: s.line_px || 2.25, pointRadius: s.point_radius != null ? s.point_radius : 3, pointHoverRadius: 4,
          tension: 0, fill: type0 === 'area', order: 0, spanGaps: false,
        });
      } else {
        Object.assign(ds, { backgroundColor: color, borderColor: color, borderWidth: 0, order: 1 });
      }
      if (!isPie) ds[horizontal ? 'xAxisID' : 'yAxisID'] = s.axis === 'y2' ? v2Ax : vAx;
      return ds;
    });
    const catFont = spec.cat_font_pt ? Math.round(spec.cat_font_pt * PT) : 12;
    const vfmt = yo.fmt || (pctStack ? '0%' : null);
    const tipFmt = (v, ds) => {
      if (v == null) return '';
      const f = ds && ds.yAxisID === 'y2' ? y2o.fmt : vfmt;
      if (f && /%/.test(f)) return U.fmt(v, '0.0%');
      return Number.isInteger(v) ? U.fmt(v, '#,##0') : U.general(v);
    };
    const narrow = opt.width && opt.width < 520;
    const shortLabel = (s) => { const t = String(s); if (!narrow || t.length <= 14) return t; const i = t.indexOf(' ('); return i > 0 ? t.slice(0, i) : t.slice(0, 14) + '…'; };
    const legendPos = spec.legend === undefined ? 'bottom' : spec.legend;
    const options = {
      responsive: true, maintainAspectRatio: false, animation: opt.animate === false ? false : { duration: 350 },
      indexAxis: horizontal ? 'y' : 'x',
      layout: { padding: { top: 4, right: horizontal && spec.data_labels ? 28 : 8, left: 4, bottom: 2 } },
      plugins: {
        title: { display: !!spec.title, text: spec.title, color: txt, font: { size: 14, weight: '700', family: FONT }, padding: { top: 4, bottom: spec.data_labels && spec.data_labels.mode === 'value' && !horizontal ? 22 : 8 } },
        // 圖例依 Excel 數列順序（Chart.js 預設依 dataset.order 排，會把折線「有意義變更」排到最前面）
        legend: legendPos ? { display: true, position: legendPos, labels: { color: txt, boxWidth: 12, boxHeight: 12, font: { size: 11 }, sort: (a, b) => ((a.datasetIndex || 0) - (b.datasetIndex || 0)) || ((a.index || 0) - (b.index || 0)) } } : { display: false },
        tooltip: {
          callbacks: {
            title: (items) => { if (!items.length) return ''; const i = items[0].dataIndex; const lab = cats[i]; const note = spec.cat_notes && spec.cat_notes[i]; return note ? `${lab} ${note}` : lab; },
            label: (item) => {
              const ds = item.dataset; const v = item.raw;
              if (isPie) { const tot = ds.data.reduce((a, b) => a + (Number(b) || 0), 0); return ` ${cats[item.dataIndex]}：${U.fmt(v, '#,##0')}（${U.fmt(tot ? v / tot : 0, '0.0%')}）`; }
              return ` ${ds.label}：${tipFmt(v, ds)}`;
            },
          },
        },
        amsDataLabels: spec.data_labels ? { mode: spec.data_labels.mode, fmt: spec.data_labels.fmt, color: txt, min: spec.data_labels.min } : null,
      },
    };
    if (isPie) {
      if (type0 === 'doughnut') options.cutout = Math.round((spec.hole != null ? spec.hole : 0.5) * 100) + '%';
    } else {
      const scales = {};
      scales[cAx] = {
        stacked: !!spec.stacked || pctStack, reverse: !!spec.reverse,
        grid: { display: false }, border: { color: gridC },
        ticks: { color: txt, font: { size: catFont }, autoSkip: !horizontal, maxRotation: horizontal ? 0 : 60, callback: function (val) { return shortLabel(this.getLabelForValue(val)); } },
      };
      const axisTitle = (t) => (t ? { display: true, text: t, color: txt, font: { size: 11 } } : { display: false });
      scales[vAx] = {
        stacked: !!spec.stacked || pctStack, beginAtZero: true,
        position: horizontal ? 'bottom' : (yo.position || 'left'),
        grid: { display: yo.grid !== false, color: gridC }, border: { display: true, color: gridC },
        ticks: { color: txt, callback: tickFmt(vfmt) },
        title: axisTitle(yo.title || spec.y_title),
      };
      if (yo.min != null) scales[vAx].min = yo.min;
      if (yo.max != null) scales[vAx].max = yo.max;
      if (yo.step != null) scales[vAx].ticks.stepSize = yo.step;
      if (hasY2) {
        scales[v2Ax] = {
          stacked: false, beginAtZero: true,
          position: horizontal ? 'top' : (y2o.position || 'right'),
          grid: { display: y2o.grid !== false, color: gridC, drawOnChartArea: y2o.grid !== false }, border: { color: gridC },
          ticks: { color: txt, callback: tickFmt(y2o.fmt) },
          title: axisTitle(y2o.title || spec.y2_title),
        };
        if (y2o.min != null) scales[v2Ax].min = y2o.min;
        if (y2o.max != null) scales[v2Ax].max = y2o.max;
        if (y2o.step != null) scales[v2Ax].ticks.stepSize = y2o.step;
      }
      options.scales = scales;
      // Excel 間距寬度 gapWidth（本簿 8 張圖皆 150）：每類別寬 = n 條柱 + gap×柱寬 → categoryPercentage = n／(n＋gap)
      const gap = (spec.gap != null ? Number(spec.gap) : 150) / 100;
      const nBars = spec.stacked || pctStack ? 1 : Math.max(1, series.filter((s) => (s.type || (type0 === 'combo' ? 'bar' : type0)) !== 'line').length);
      options.datasets = { bar: { categoryPercentage: nBars / (nBars + gap), barPercentage: 1 } };
    }
    let ctype = isPie ? type0 : (type0 === 'combo' ? 'bar' : (type0 === 'area' ? 'line' : type0));
    if (!['bar', 'line', 'pie', 'doughnut'].includes(ctype)) ctype = 'bar';
    return { type: ctype, data: { labels: cats, datasets }, options };
  };
  /** 在容器內建立圖表（含標題列的資料來源連結） */
  CH.mount = function (box, spec, opt) {
    box.innerHTML = '';
    box.classList.add('gchart');
    box.setAttribute('role', 'figure');
    box.setAttribute('aria-label', '圖表：' + (spec.title || spec.id || ''));
    const cv = document.createElement('canvas');
    cv.setAttribute('role', 'img');
    cv.setAttribute('aria-label', CH.describe(spec));
    box.appendChild(cv);
    if (spec.src && spec.src.s) {
      const a = U.h('a', { class: 'gchart-src', href: AMS.linkHref(spec.src), title: '資料來源：' + (spec.source || '') }, '資料 ↗');
      box.appendChild(a);
    }
    if (!ensureChartJs()) { box.appendChild(U.h('p', { class: 'muted' }, '（Chart.js 未載入）')); return null; }
    try { return new window.Chart(cv, CH.config(spec, opt)); } catch (e) { console.error(e); box.appendChild(U.h('p', { class: 'muted' }, '圖表繪製失敗：' + e.message)); return null; }
  };
  CH.describe = function (spec) {
    const s = (spec.series || []).map((x) => `${x.name}：${(x.values || []).map((v) => (v == null ? '—' : U.general(v))).join('、')}`).join('；');
    return `${spec.title || ''}。類別：${(spec.categories || []).join('、')}。${s}`;
  };

  /* ------------------------------------------------------------ GridView */
  class GridView {
    constructor(root, meta, route) {
      this.root = root; this.meta = meta; this.id = meta.id; this.charts = [];
      this.state = AMS.viewState[meta.id] || (AMS.viewState[meta.id] = {});
      this.route = route;
      root.className = 'view grid-view';
      root.innerHTML = `<header class="sv-head"><div class="sv-crumb"><span class="mode-badge">版面</span> ${U.esc(meta.group || '')}</div><h1 class="sv-title">${U.esc(meta.name)}</h1></header><div class="loading-box"><div class="spinner"></div><p>載入中…</p><div class="lb-bar"><div></div></div></div>`;
      this.load();
    }
    async load() {
      try {
        const j = await D.loadSheet(this.id, (f) => { const b = this.root.querySelector('.lb-bar > div'); if (b) b.style.width = Math.round(f * 100) + '%'; });
        if (this.destroyed) return;
        this.g = j;
        this.render();
      } catch (e) {
        console.error(e);
        this.root.querySelector('.loading-box').outerHTML = `<div class="error-box"><h2>無法載入資料</h2><p>${U.esc(e.message)}</p></div>`;
      }
    }
    render() {
      const g = this.g; const m = this.meta;
      this.destroyCharts();
      this.updToc = null;
      const secs = (g.sections || []).slice().sort((a, b) => a.r - b.r);
      const notes = Array.isArray(g.notes) ? g.notes : (g.notes ? String(g.notes).split('｜') : []);
      const root = this.root;
      root.innerHTML = '';
      const head = U.h('header', { class: 'sv-head' });
      head.innerHTML = `<div class="sv-crumb"><span class="mode-badge">版面</span> ${U.esc(m.group || '')}${g.charts && g.charts.length ? ` <span class="sv-rows">· ${g.charts.length} 張圖表</span>` : ''}</div>
        <h1 class="sv-title">${U.esc(m.name)}</h1>
        ${notes.length ? `<details class="sv-notes"><summary>說明（${notes.length} 則）<span class="np">${U.esc(notes[0])}</span></summary><ul>${notes.map((n) => `<li>${U.esc(n)}</li>`).join('')}</ul></details>` : ''}`;
      root.appendChild(head);
      const bar = U.h('div', { class: 'gv-bar' });
      if (secs.length) {
        const nav = U.h('nav', { class: 'gv-toc', 'aria-label': '區段目錄' });
        nav.innerHTML = `<span class="gv-toc-l">區段</span>` + secs.map((s) => `<button type="button" class="chip-btn" data-r="${s.r}">${U.esc(s.label)}</button>`).join('');
        nav.addEventListener('click', (e) => { const b = e.target.closest('[data-r]'); if (b) this.scrollToRow(Number(b.dataset.r), true); });
        // 區段按鈕列可水平捲動：尚未捲到底時右緣淡出，提示還有更多區段
        const upd = () => nav.classList.toggle('ovf', nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 2);
        nav.addEventListener('scroll', upd, { passive: true });
        this.updToc = upd;
        requestAnimationFrame(upd);
        bar.appendChild(nav);
      }
      const blocks = this.blocks();
      if (blocks.length) {
        const bsel = U.h('select', { class: 'gv-blocks', 'aria-label': '以可排序／篩選的表格檢視區塊' });
        bsel.appendChild(U.h('option', { value: '' }, '表格檢視…'));
        blocks.forEach((b, i) => bsel.appendChild(U.h('option', { value: String(i) }, b.label)));
        bsel.addEventListener('change', () => { const b = blocks[Number(bsel.value)]; bsel.value = ''; if (b) this.openBlock(b); });
        bar.appendChild(U.h('label', { class: 'gv-zoom', title: '把版面中的一個區塊開成可排序、篩選、匯出 CSV 的表格' }, bsel));
      }
      const zsel = U.h('label', { class: 'gv-zoom' }, '縮放 ');
      const sel = U.h('select', { 'aria-label': '版面縮放' });
      [['auto', '自動'], ['fit', '符合寬度'], ['0.5', '50%'], ['0.75', '75%'], ['0.85', '85%'], ['1', '100%'], ['1.25', '125%']].forEach(([v, t]) => sel.appendChild(U.h('option', { value: v }, t)));
      zsel.appendChild(sel);
      bar.appendChild(zsel);
      root.appendChild(bar);
      if (this.state.zoom == null) this.state.zoom = 'auto';
      sel.value = this.state.zoom;
      sel.addEventListener('change', () => { this.state.zoom = sel.value; this.applyZoom(); });
      const wrap = (this.wrap = U.h('div', { class: 'gv-wrap', tabindex: '0', role: 'region', 'aria-label': m.name + ' 版面' }));
      const inner = (this.inner = U.h('div', { class: 'gv-inner' }));
      wrap.appendChild(inner);
      root.appendChild(wrap);
      const narrow = (this.narrow = (root.clientWidth || window.innerWidth) < CHART_BREAK);
      // 圖表需要的額外欄
      const built = (this.built = buildGridTable(g, {}));
      inner.appendChild(built.table);
      // 圖表寬度可能超過最後一欄
      let needW = built.totalW;
      for (const ch of g.charts || []) {
        const a = ch.anchor && ch.anchor.from; if (!a) continue;
        const w = (ch.size_px && ch.size_px.w) || 480;
        needW = Math.max(needW, (built.left[a.c] || 0) + w + 4);
      }
      inner.style.width = (narrow ? built.totalW : needW) + 'px';
      this.needW = narrow ? built.totalW : needW;
      this.applyZoom();
      this.applyFreeze();
      if (narrow) this.placeChartsInline(); else this.placeChartsAbsolute();
      // 目標列
      const r = this.route && this.route.params.get('r');
      if (r) requestAnimationFrame(() => this.scrollToRow(Number(r), true));
      else if (this.state.scrollTop) { wrap.scrollTop = this.state.scrollTop; wrap.scrollLeft = this.state.scrollLeft || 0; }
      this.ro = new ResizeObserver(U.debounce(() => {
        if (this.updToc) this.updToc();
        const nn = (root.clientWidth || window.innerWidth) < CHART_BREAK;
        if (nn !== this.narrow) { this.state.scrollTop = wrap.scrollTop; this.render(); return; }
        if (this.state.zoom === 'fit' || this.state.zoom === 'auto') { this.applyZoom(); if (!nn) this.positionCharts(); }
        if (!nn) this.positionCharts();
        else this.sizeInlineCharts();
      }, 120));
      this.ro.observe(root);
      this.ro.observe(built.table);
    }
    /** 可轉成表格檢視的區塊：autofilter 範圍、named_tables、subtables */
    blocks() {
      const g = this.g; const out = [];
      const secLabel = (r) => { let best = null; for (const s of g.sections || []) if (s.r <= r && (!best || s.r > best.r)) best = s; return best ? best.label : ''; };
      if (g.autofilter && g.autofilter.r1) {
        const a = g.autofilter;
        out.push({ label: (secLabel(a.r1) || '自動篩選範圍') + '（自動篩選）', header: a.r1, first: a.r1 + 1, last: a.r2, c1: a.c1 || 1, c2: a.c2 || (g.max_col || 1) });
      }
      for (const t of g.named_tables || []) {
        const m = /^([A-Z]+)(\d+):([A-Z]+)(\d+)$/.exec(t.ref || '');
        const c1 = m ? colNum(m[1]) : 1; const c2 = m ? colNum(m[3]) : c1 + (t.cols || 1) - 1;
        out.push({ label: t.name, header: t.header_row, first: t.first, last: t.last, c1, c2, spec: t.spec_row });
      }
      for (const t of g.subtables || []) {
        if (!t.header_row) continue;
        out.push({ label: t.label || t.title || ('第 ' + t.header_row + ' 列起的區塊'), header: t.header_row, first: t.first || t.header_row + 1, last: t.last, c1: t.c1 || 1, c2: t.c2 || (t.c1 || 1) + (t.cols || g.max_col || 1) - 1 });
      }
      return out.filter((b) => b.header && b.first && b.last && b.last >= b.first);
    }
    openBlock(b) {
      const g = this.g; const styles = g.styles || [];
      const rowMap = new Map((g.rows || []).map((r) => [r.r, r]));
      const cellAt = (r, c) => { const row = rowMap.get(r); return row ? (row.cells || []).find((x) => x.c === c) : null; };
      const cols = []; const ncol = b.c2 - b.c1 + 1;
      const wOf = (c) => ((g.col_widths || [])[c - 1] || 64);
      for (let c = b.c1; c <= b.c2; c++) {
        const h = cellAt(b.header, c); const sp = b.spec ? cellAt(b.spec, c) : null;
        let fmt = null;
        for (let r = b.first; r <= b.last && !fmt; r++) { const x = cellAt(r, c); if (x && x.f) fmt = x.f; }
        cols.push({ label: h && h.v != null ? String(U.raw(h.v)) : '欄 ' + c, w: Math.max(50, Math.min(420, wOf(c))), fmt, note: sp && sp.v != null ? String(sp.v) : null });
      }
      const rows = []; const cst = []; const bars = []; const stIdx = new Map(); const stList = [];
      const sidx = (str) => { if (!stIdx.has(str)) { stIdx.set(str, stList.length); stList.push(str); } return stIdx.get(str); };
      const first = b.spec && b.spec >= b.first ? b.spec + 1 : b.first;
      for (let r = first; r <= b.last; r++) {
        const row = new Array(ncol).fill(null);
        for (let c = b.c1; c <= b.c2; c++) {
          const x = cellAt(r, c); if (!x) continue;
          const k = c - b.c1; let v = x.v;
          if (x.l) v = { t: U.raw(v), l: x.l };
          else if (x.f && typeof v === 'number') v = { v, f: x.f };
          row[k] = v;
          const st = x.s != null ? styles[x.s] : null;
          if (st && (st.bg || st.fc || st.b || st.i)) cst.push([rows.length, k, sidx(`${st.b ? 'b' : ''}${st.i ? 'i' : ''}|${st.bg || ''}|${st.fc || ''}`)]);
          if (x.bar) bars.push([rows.length, k, x.bar.p, x.bar.c]);
        }
        if (row.some((v) => v != null)) rows.push(row);
      }
      const id = this.id + '#' + b.header;
      const data = { id, name: `${this.meta.name} · ${b.label}`, mode: 'table', title: b.label,
        notes: [`來源：${this.meta.name} 第 ${b.header} 列（表頭）至第 ${b.last} 列；此為版面區塊的表格檢視（可排序、篩選、匯出 CSV）`],
        bands: [], columns: cols, freeze_cols: 1, rows, styles: stList, cell_styles: cst, row_styles: [], bars, data_first_row: first, ui: { facets: [] } };
      const ov = U.h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': data.name });
      const panel = U.h('div', { class: 'modal-panel' });
      const close = U.h('button', { class: 'icon-btn modal-x', type: 'button', 'aria-label': '關閉表格檢視' }, '✕');
      const root = U.h('div', { class: 'view table-view' });
      panel.append(close, root); ov.appendChild(panel); document.body.appendChild(ov);
      const tv = new AMS.TableView(root, { id, name: data.name, group: this.meta.name, _data: data }, null);
      const done = () => { tv.destroy(); ov.remove(); document.removeEventListener('keydown', onKey, true); };
      const onKey = (e) => { if (e.key === 'Escape' && !AMS.detail.isOpen()) { e.preventDefault(); done(); } };
      close.addEventListener('click', done);
      ov.addEventListener('pointerdown', (e) => { if (e.target === ov) done(); });
      ov.addEventListener('click', (e) => { if (e.target.closest('a[href^="#/"]')) done(); });
      document.addEventListener('keydown', onKey, true);
      close.focus();
    }
    applyZoom() {
      if (!this.inner) return;
      const fit = Math.min(1, Math.max(0.45, ((this.wrap.clientWidth || 800) - 4) / (this.needW || 1)));
      let z;
      if (this.state.zoom === 'fit') z = fit;
      else if (this.state.zoom === 'auto') z = fit >= 0.8 ? fit : 1; // 只差一點就放得下時才縮小，避免文字過小
      else z = Number(this.state.zoom) || 1;
      this.zoom = z;
      this.inner.style.zoom = z === 1 ? '' : String(z);
    }
    applyFreeze() {
      const fr = this.g.freeze_rows || 0; const fc = this.g.freeze_cols || 0;
      if (!fr && !fc) return;
      const trs = this.built.trs;
      let top = 0;
      for (let r = 1; r <= fr; r++) {
        const tr = trs.get(r); if (!tr) continue;
        const h = tr.getBoundingClientRect().height;
        tr.classList.add('frz');
        Array.from(tr.cells).forEach((td) => { td.style.position = 'sticky'; td.style.top = top + 'px'; td.style.zIndex = 3; if (!td.style.backgroundColor) td.style.backgroundColor = 'var(--surface)'; });
        top += h;
      }
      this.freezeH = top;
      if (fc) {
        const x = this.built.left[fc + 1];
        this.built.table.querySelectorAll('tr').forEach((tr) => {
          let c = 1;
          Array.from(tr.cells).forEach((td) => {
            if (c <= fc) { td.style.position = 'sticky'; td.style.left = this.built.left[c] + 'px'; td.style.zIndex = Math.max(2, Number(td.style.zIndex) || 2); if (!td.style.backgroundColor) td.style.backgroundColor = 'var(--surface)'; }
            c += td.colSpan || 1;
          });
        });
        void x;
      }
    }
    chartRect(ch) {
      const b = this.built; const a = ch.anchor || {}; const f = a.from || { r: 1, c: 1 };
      const tr = b.trs.get(f.r);
      const top = tr ? tr.offsetTop : 0;
      const left = b.left[f.c] || 0;
      let w = ch.size_px && ch.size_px.w; let h = ch.size_px && ch.size_px.h;
      if (a.to) {
        const toW = (b.left[a.to.c + 1] || left) - left;
        const trTo = b.trs.get(a.to.r);
        const toH = trTo ? trTo.offsetTop + trTo.offsetHeight - top : 0;
        if (!w) w = toW; else if (toW > 120 && toW < w) w = toW; // 夾到錨點範圍，避免左右圖重疊
        if (!h) h = toH;
      }
      return { left: left + (f.dx || 0), top: top + (f.dy || 0), w: w || 480, h: h || 300 };
    }
    placeChartsAbsolute() {
      const charts = this.g.charts || [];
      if (!charts.length) return;
      const layer = (this.layer = U.h('div', { class: 'gv-charts' }));
      this.inner.appendChild(layer);
      this.chartBoxes = charts.map((ch) => {
        const box = U.h('div', { class: 'gchart abs' });
        layer.appendChild(box);
        return { ch, box };
      });
      this.positionCharts();
      this.chartBoxes.forEach(({ ch, box }) => { const c = CH.mount(box, ch, { width: box.clientWidth }); if (c) this.charts.push(c); });
    }
    positionCharts() {
      if (!this.chartBoxes) return;
      for (const { ch, box } of this.chartBoxes) {
        const r = this.chartRect(ch);
        Object.assign(box.style, { left: r.left + 'px', top: r.top + 'px', width: r.w + 'px', height: r.h + 'px' });
      }
    }
    placeChartsInline() {
      const charts = (this.g.charts || []).slice();
      if (!charts.length) return;
      const secs = (this.g.sections || []).map((s) => s.r).sort((a, b) => a - b);
      const b = this.built;
      // 各圖插在「錨點之後的下一個區段標題」之前（無則放最後）
      const groups = new Map();
      charts.sort((x, y) => String(x.id).localeCompare(String(y.id), 'en', { numeric: true }));
      for (const ch of charts) {
        const ar = ch.anchor && ch.anchor.from ? ch.anchor.from.r : 1;
        let at = null;
        for (const r of secs) if (r > ar) { at = r; break; }
        const key = at == null ? 'end' : at;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(ch);
      }
      // 隱藏圖表錨點範圍內的空白列
      for (const ch of charts) {
        const a = ch.anchor || {}; if (!a.from) continue;
        const r1 = a.to ? a.to.r : a.from.r + Math.ceil(((ch.size_px && ch.size_px.h) || 300) / 20);
        for (let r = a.from.r; r <= r1; r++) { const tr = b.trs.get(r); if (tr && tr.classList.contains('er')) tr.classList.add('er-chart'); }
      }
      const ncols = b.table.querySelector('colgroup').children.length;
      this.inlineBoxes = [];
      groups.forEach((list, key) => {
        const tr = document.createElement('tr');
        tr.className = 'gchart-row';
        const td = document.createElement('td');
        td.colSpan = ncols;
        const holder = U.h('div', { class: 'gchart-stack' });
        td.appendChild(holder); tr.appendChild(td);
        const before = key === 'end' ? null : b.trs.get(key);
        const tbody = b.table.tBodies[0];
        if (before) tbody.insertBefore(tr, before); else tbody.appendChild(tr);
        for (const ch of list) {
          const box = U.h('div', { class: 'gchart inline' });
          const w = (ch.size_px && ch.size_px.w) || 600; const h = (ch.size_px && ch.size_px.h) || 320;
          box.style.aspectRatio = `${w} / ${h}`;
          holder.appendChild(box);
          this.inlineBoxes.push({ ch, box });
        }
      });
      this.sizeInlineCharts();
      this.inlineBoxes.forEach(({ ch, box }) => { const c = CH.mount(box, ch, { width: box.clientWidth }); if (c) this.charts.push(c); });
    }
    sizeInlineCharts() {
      const w = Math.max(260, (this.wrap.clientWidth || 360) - 4);
      this.root.querySelectorAll('.gchart-stack').forEach((el) => { el.style.width = w + 'px'; });
    }
    scrollToRow(r, flash) {
      const b = this.built; if (!b) return;
      let tr = b.trs.get(r);
      if (!tr) { let best = null; b.trs.forEach((t, k) => { if (k >= r && (best == null || k < best)) best = k; }); if (best != null) tr = b.trs.get(best); }
      if (!tr) return;
      this.wrap.scrollTop = Math.max(0, (tr.offsetTop - (this.freezeH || 0)) * (this.zoom || 1) - 8);
      if (flash) {
        b.table.querySelectorAll('tr.flash-row').forEach((x) => x.classList.remove('flash-row'));
        void tr.offsetWidth; tr.classList.add('flash-row');
      }
    }
    update(route) { this.route = route; const r = route.params.get('r'); if (r) this.scrollToRow(Number(r), true); }
    destroyCharts() { this.charts.forEach((c) => { try { c.destroy(); } catch (e) { /**/ } }); this.charts = []; if (this.ro) { this.ro.disconnect(); this.ro = null; } }
    onTheme() { if (this.g) { const st = this.wrap ? this.wrap.scrollTop : 0; this.render(); if (this.wrap) this.wrap.scrollTop = st; } }
    destroy() {
      this.destroyed = true;
      if (this.wrap) { this.state.scrollTop = this.wrap.scrollTop; this.state.scrollLeft = this.wrap.scrollLeft; }
      this.destroyCharts();
    }
  }
  /** 靜態 grid（table 的 subgrid 等），不含圖表與目錄 */
  GridView.renderStatic = function (g, container) {
    const built = buildGridTable(g, {});
    const wrap = U.h('div', { class: 'gv-static' });
    wrap.appendChild(built.table);
    container.appendChild(wrap);
    return built;
  };
  AMS.GridView = GridView;
  AMS.buildGridTable = buildGridTable;
})();
