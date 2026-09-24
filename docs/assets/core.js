/* AMS 解析網頁 — 核心：工具、格式化、色彩、資料載入、列詳情、自動完成
 * vanilla ES2020，無 build step。所有模組掛在 window.AMS 之下。 */
'use strict';
(function () {
  const AMS = (window.AMS = window.AMS || {});
  const U = (AMS.U = {});

  /* ------------------------------------------------------------------ 基本工具 */
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  U.esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESC[c]);
  U.$ = (sel, root) => (root || document).querySelector(sel);
  U.$$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  U.h = function (tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        const v = attrs[k];
        if (v == null || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
        else if (k === 'html') el.innerHTML = v;
        else if (k === 'text') el.textContent = v;
        else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? '' : v);
      }
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      el.appendChild(typeof kid === 'string' || typeof kid === 'number' ? document.createTextNode(String(kid)) : kid);
    }
    return el;
  };
  U.debounce = function (fn, ms) {
    let t = 0;
    const d = function (...a) { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), ms); };
    d.cancel = () => clearTimeout(t);
    return d;
  };
  U.store = {
    get(k, d) { try { const v = localStorage.getItem('ams.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('ams.' + k, JSON.stringify(v)); } catch (e) { /* 私密模式等 */ } },
  };
  U.int = (n) => (n == null || n === '' ? '' : Number(n).toLocaleString('en-US'));
  // 手機：窄螢幕，或「矮的觸控螢幕」（手機橫放 844×390 等）— 與 app.css 的 @media 條件一致
  U.MOBILE_MQ = '(max-width: 720px), (pointer: coarse) and (max-height: 500px)';
  U.isMobile = () => window.matchMedia(U.MOBILE_MQ).matches;
  U.isTouch = () => window.matchMedia('(pointer: coarse)').matches;
  U.num = (v, d) => { const n = Number(v); return Number.isFinite(n) ? n : (d === undefined ? 0 : d); }; // 寫入標記前一律轉數字
  U.clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  // 讓出主執行緒（MessageChannel 比 setTimeout(0) 快）
  const mc = new MessageChannel();
  const mcq = [];
  mc.port1.onmessage = () => { const f = mcq.shift(); if (f) f(); };
  U.yieldMain = () => new Promise((res) => { mcq.push(res); mc.port2.postMessage(0); });

  /** 分段處理：每段約 budget ms 後讓出主執行緒；token() 回傳 false 時中止 */
  U.chunked = async function (n, fn, alive, budget) {
    budget = budget || 12;
    let i = 0;
    while (i < n) {
      const t0 = performance.now();
      while (i < n) {
        fn(i++);
        if ((i & 255) === 0 && performance.now() - t0 > budget) break;
      }
      if (i < n) {
        await U.yieldMain();
        if (alive && !alive()) return false;
      }
    }
    return true;
  };

  /* ------------------------------------------------------------------ 儲存格值 */
  // 儲存格表示法：純值 | {t,l:{s,r}} 連結 | {t,u} 外部連結 | {v,f} 帶格式
  U.raw = function (c) {
    if (c !== null && typeof c === 'object') {
      if ('t' in c) return c.t;
      if ('v' in c) return c.v;
      return null;
    }
    return c;
  };
  U.isBlank = (v) => v === null || v === undefined || v === '';
  U.text = function (c) { // 供搜尋／CSV 的文字
    const v = U.raw(c);
    if (v === null || v === undefined) return '';
    if (v === true) return 'TRUE';
    if (v === false) return 'FALSE';
    return String(v);
  };
  // 顯示用：把控制字元可視化、換行以 ↵ 表示（單列儲存格）
  U.visible = function (s, keepNewline) {
    s = String(s);
    if (!/[\u0000-\u001f\u007f]/.test(s)) return s;
    return s.replace(/[\u0000-\u001f\u007f]/g, (ch) => {
      if (ch === '\n') return keepNewline ? '\n' : ' ↵ ';
      if (ch === '\t') return keepNewline ? '\t' : '⇥';
      if (ch === '\r') return keepNewline ? '' : '';
      if (ch === '\u007f') return '␡';
      return String.fromCharCode(0x2400 + ch.charCodeAt(0));
    });
  };

  /* ------------------------------------------------------------------ 查詢卡：值處理與來源分級 */
  // float32 FLT_MIN（1.1754943508222875e-38）＝裝置「未使用」哨兵；float32 殘差（10000.0009765625）以 7 位有效數字顯示
  U.isFltMin = (v) => typeof v === 'number' && v !== 0 && Math.abs(v) < 1e-30;
  U.g7 = function (v) {
    if (typeof v !== 'number' || !Number.isFinite(v)) return String(v);
    if (Number.isInteger(v) && Math.abs(v) < 1e15) return String(v);
    const n = Number(v.toPrecision(7));
    return Math.abs(n) >= 1e-6 || n === 0 ? String(n) : n.toExponential();
  };
  /** 查詢卡欄位值 → 顯示文字；'' 表示空白（CSS 顯示「—」）。opt: {serial: 0→未寫入, fmt: Excel 格式碼} */
  U.cardValue = function (v, opt) {
    opt = opt || {};
    v = U.raw(v);
    if (v === null || v === undefined) return '';
    if (typeof v === 'number') {
      if (U.isFltMin(v)) return '未使用';
      if (opt.serial && v === 0) return '未寫入';
      if (opt.fmt && opt.fmt !== 'General') return U.fmt(v, opt.fmt);
      return U.g7(v);
    }
    if (v === true) return 'TRUE';
    if (v === false) return 'FALSE';
    const s = String(v);
    if (s.trim() === '') return ''; // 全空白字串（descriptor／message 常見）
    if (/^-?1\.17549435\d*e-38$/i.test(s.trim())) return '未使用';
    if (opt.serial && /^0+(\.0+)?$/.test(s.trim())) return '未寫入';
    return opt.fmt && opt.fmt !== 'General' ? U.fmt(s, opt.fmt) : s;
  };
  U.SRC_LVLS = ['raw', 'decoded', 'inferred', 'doc', 'factory', 'ctrl'];
  U.SRC_LABEL = { raw: '原始', decoded: '解碼', inferred: '推論', doc: '文件', factory: '出廠', ctrl: '控制器' };

  /* ------------------------------------------------------------------ Excel 數字格式子集 */
  const fmtCache = new Map();
  function splitSections(fmt) {
    const out = []; let cur = ''; let q = false;
    for (let i = 0; i < fmt.length; i++) {
      const ch = fmt[i];
      if (ch === '"') q = !q;
      if (ch === '\\' && !q) { cur += ch + (fmt[i + 1] || ''); i++; continue; }
      if (ch === ';' && !q) { out.push(cur); cur = ''; continue; }
      cur += ch;
    }
    out.push(cur);
    return out;
  }
  function isDateFmt(f) {
    const s = f.replace(/"[^"]*"/g, '').replace(/\\./g, '').replace(/\[[^\]]*\]/g, '');
    return /[yd]/i.test(s) || /h/i.test(s) || (/s/i.test(s) && /[:]/.test(s)) || /^m+$/i.test(s.trim());
  }
  function compileNum(sec) {
    // 移除 [顏色]、[$-404] 等；_x 填空；* 重複
    let s = sec.replace(/\[[^\]]*\]/g, '').replace(/_./g, '').replace(/\*./g, '');
    const m = s.match(/[#0?,]*[0#?](?:[#0?,]*)(?:\.[0#?]*)?|\.[0#?]+/);
    if (!m) {
      const lit = s.replace(/"([^"]*)"/g, '$1').replace(/\\(.)/g, '$1');
      return { literal: lit };
    }
    const core = m[0];
    const lit = (x) => x.replace(/"([^"]*)"/g, '$1').replace(/\\(.)/g, '$1');
    const pre = lit(s.slice(0, m.index));
    const suf = lit(s.slice(m.index + core.length));
    const dot = core.indexOf('.');
    const intPart = dot >= 0 ? core.slice(0, dot) : core;
    const dec = dot >= 0 ? core.slice(dot + 1) : '';
    // 整數部分尾端的逗號＝除以千
    let scale = 1; let ip = intPart;
    while (ip.endsWith(',')) { scale *= 1000; ip = ip.slice(0, -1); }
    const pct = (pre + suf).split('%').length - 1;
    return {
      pre, suf,
      thousands: ip.includes(','),
      maxDec: dec.length,
      minDec: (dec.match(/0/g) || []).length,
      minInt: (ip.match(/0/g) || []).length,
      pct, scale,
    };
  }
  function getFmt(fmt) {
    let c = fmtCache.get(fmt);
    if (c) return c;
    const f = String(fmt).trim();
    if (!f || /^general$/i.test(f) || f === '@') c = { general: true };
    else {
      const secs = splitSections(f);
      if (isDateFmt(secs[0])) c = { date: secs[0] };
      else c = { secs: secs.map(compileNum) };
    }
    fmtCache.set(fmt, c);
    return c;
  }
  function addThousands(s) {
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  U.general = function (v) {
    if (!isFinite(v)) return String(v);
    if (Number.isInteger(v) && Math.abs(v) < 1e11) return String(v);
    const a = Math.abs(v);
    if (a !== 0 && (a >= 1e11 || a < 1e-9)) {
      return v.toExponential(5).replace(/\.?0+e/, 'e').toUpperCase().replace(/E([+-])(\d)$/, 'E$10$2');
    }
    let s = String(Number(v.toPrecision(10)));
    if (/e/i.test(s)) s = v.toFixed(10).replace(/\.?0+$/, '');
    return s;
  };
  function fmtNumSec(v, c) {
    if (c.literal !== undefined) return c.literal;
    let x = v * Math.pow(100, c.pct) / c.scale;
    const neg = x < 0; x = Math.abs(x);
    let s = x.toFixed(c.maxDec);
    if (c.maxDec > c.minDec) { // 去掉 # 位的尾端 0
      const [i, d = ''] = s.split('.');
      let dd = d;
      while (dd.length > c.minDec && dd.endsWith('0')) dd = dd.slice(0, -1);
      s = dd ? i + '.' + dd : i;
    }
    let [ip, dp] = s.split('.');
    if (c.minInt === 0 && ip === '0' && dp) ip = '';
    else if (ip.length < c.minInt) ip = ip.padStart(c.minInt, '0');
    if (c.thousands) ip = addThousands(ip);
    s = dp !== undefined ? ip + '.' + dp : ip;
    const isZero = /^[0.,]*$/.test(s);
    return (neg && !isZero ? '-' : '') + c.pre + s + c.suf;
  }
  // 日期字串 "YYYY-MM-DD[ HH:MM[:SS[.fff]]]" → 依格式碼輸出
  const DRE = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?$/;
  function fmtDateStr(str, f) {
    const m = DRE.exec(str);
    if (!m) return null;
    let [, Y, M, D, h = '0', mi = '0', s = '0', frac = ''] = m;
    const toks = [];
    const re = /(yyyy|yy|mmmm|mmm|mm|m|dddd|ddd|dd|d|hh|h|ss|s|\.0+|am\/pm|a\/p|"[^"]*"|\\.|.)/gi;
    let t;
    while ((t = re.exec(f))) toks.push(t[1]);
    const fracTok = toks.find((x) => /^\.0+$/.test(x));
    const hasSec = toks.some((x) => /^ss?$/i.test(x));
    let ms = Number(('0.' + (frac || '0')));
    let dt = Date.UTC(+Y, +M - 1, +D, +h, +mi, +s);
    if (!fracTok && hasSec && ms >= 0.5) dt += 1000; // Excel 顯示秒時四捨五入
    if (fracTok) { // 依小數位數四捨五入
      const n = fracTok.length - 1;
      const r = Math.round(ms * Math.pow(10, n));
      if (r >= Math.pow(10, n)) { dt += 1000; ms = 0; } else ms = r / Math.pow(10, n);
    }
    const d = new Date(dt);
    const P = (x, n) => String(x).padStart(n || 2, '0');
    const parts = { Y: d.getUTCFullYear(), M: d.getUTCMonth() + 1, D: d.getUTCDate(), h: d.getUTCHours(), m: d.getUTCMinutes(), s: d.getUTCSeconds() };
    const ampm = toks.some((x) => /^am\/pm$|^a\/p$/i.test(x));
    let out = '';
    for (let i = 0; i < toks.length; i++) {
      const k = toks[i]; const kl = k.toLowerCase();
      // m/mm 在 h 之後或 s 之前 → 分
      const isMin = (kl === 'm' || kl === 'mm') && (() => {
        for (let j = i - 1; j >= 0; j--) { const p = toks[j].toLowerCase(); if (/^h+$/.test(p)) return true; if (/^[ymd]+$/.test(p)) break; }
        for (let j = i + 1; j < toks.length; j++) { const p = toks[j].toLowerCase(); if (/^s+$/.test(p)) return true; if (/^[ymdh]+$/.test(p)) break; }
        return false;
      })();
      if (kl === 'yyyy') out += parts.Y;
      else if (kl === 'yy') out += P(parts.Y % 100);
      else if (isMin) out += kl === 'mm' ? P(parts.m) : parts.m;
      else if (kl === 'mmmm' || kl === 'mmm') out += parts.M + '月';
      else if (kl === 'mm') out += P(parts.M);
      else if (kl === 'm') out += parts.M;
      else if (kl === 'dddd' || kl === 'ddd') out += '日一二三四五六'[d.getUTCDay()];
      else if (kl === 'dd') out += P(parts.D);
      else if (kl === 'd') out += parts.D;
      else if (kl === 'hh') out += P(ampm ? (parts.h % 12 || 12) : parts.h);
      else if (kl === 'h') out += ampm ? (parts.h % 12 || 12) : parts.h;
      else if (kl === 'ss') out += P(parts.s);
      else if (kl === 's') out += parts.s;
      else if (/^\.0+$/.test(k)) out += '.' + String(Math.round(ms * Math.pow(10, k.length - 1))).padStart(k.length - 1, '0');
      else if (kl === 'am/pm') out += parts.h < 12 ? 'AM' : 'PM';
      else if (kl === 'a/p') out += parts.h < 12 ? 'A' : 'P';
      else if (k[0] === '"') out += k.slice(1, -1);
      else if (k[0] === '\\') out += k.slice(1);
      else out += k;
    }
    return out;
  }
  function serialToStr(v) { // Excel 序列值 → 日期字串（1900 系統）
    const ms = Math.round((v - 25569) * 86400000);
    const d = new Date(ms);
    if (isNaN(d)) return null;
    const P = (x, n) => String(x).padStart(n || 2, '0');
    return `${d.getUTCFullYear()}-${P(d.getUTCMonth() + 1)}-${P(d.getUTCDate())} ${P(d.getUTCHours())}:${P(d.getUTCMinutes())}:${P(d.getUTCSeconds())}.${P(d.getUTCMilliseconds(), 3)}`;
  }
  /** 依 Excel 格式碼格式化單一值 */
  U.fmt = function (v, fmt) {
    if (v === null || v === undefined) return '';
    if (v === true) return 'TRUE';
    if (v === false) return 'FALSE';
    if (typeof v === 'number') {
      if (!fmt) return U.general(v);
      const c = getFmt(fmt);
      if (c.general) return U.general(v);
      if (c.date) { const s = serialToStr(v); const r = s && fmtDateStr(s, c.date); return r == null ? U.general(v) : r; }
      const secs = c.secs;
      if (v < 0 && secs.length > 1) return fmtNumSec(-v, secs[1]).replace(/^-/, '');
      if (v === 0 && secs.length > 2) return fmtNumSec(v, secs[2]);
      return fmtNumSec(v, secs[0]);
    }
    const s = String(v);
    if (fmt) {
      const c = getFmt(fmt);
      if (c.date) { const r = fmtDateStr(s, c.date); if (r != null) return r; }
    }
    return s;
  };
  /** 儲存格顯示文字（含連結物件、{v,f}） */
  U.display = function (c, colFmt) {
    if (c !== null && typeof c === 'object') {
      const f = c.f || colFmt;
      if ('t' in c) return U.fmt(c.t, typeof c.t === 'number' ? f : null);
      if ('v' in c) return U.fmt(c.v, f);
      return '';
    }
    return U.fmt(c, colFmt);
  };
  U.isNumFmtPct = (fmt) => !!fmt && /%/.test(fmt);

  /* ------------------------------------------------------------------ 色彩／主題 */
  U.theme = () => document.documentElement.getAttribute('data-theme') || 'light';
  function hexToRgb(h) {
    h = String(h || '').replace('#', '').trim();
    if (h.length === 8) h = h.slice(2);
    if (h.length === 3) h = h.split('').map((x) => x + x).join('');
    if (!/^[0-9a-f]{6}$/i.test(h)) return null;
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  U.hexToRgb = hexToRgb;
  const toHex = (rgb) => '#' + rgb.map((x) => Math.round(U.clamp(x, 0, 255)).toString(16).padStart(2, '0')).join('');
  function lum(rgb) {
    const a = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
  }
  U.lum = (hex) => { const r = hexToRgb(hex); return r ? lum(r) : 1; };
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  U.normHex = (h) => { const r = hexToRgb(h); return r ? toHex(r) : null; };
  const DARK_SURFACE = [23, 28, 35];
  const adaptCache = new Map();
  /** 回傳在目前主題下適合的 {bg, fc}；保留 Excel 顏色語意 */
  U.adaptColors = function (bg, fc, theme) {
    const key = theme + '|' + bg + '|' + fc;
    let r = adaptCache.get(key);
    if (r) return r;
    const b = bg ? hexToRgb(bg) : null;
    const f = fc ? hexToRgb(fc) : null;
    r = { bg: b ? toHex(b) : null, fc: f ? toHex(f) : null };
    if (theme === 'dark') {
      if (b) {
        const L = lum(b);
        const sat = Math.max(...b) - Math.min(...b);
        if (L > 0.86 && sat < 24) { // 近白色的「紙」底色 → 深色版淡色
          r.bg = toHex(mix(b, DARK_SURFACE, 0.9));
          if (!f) r.fc = null;
          else if (lum(f) < 0.3) r.fc = lightenFg(f);
        } else if (!f) r.fc = L > 0.18 ? '#1b1f24' : '#ffffff'; // 0.18＝黑白字對比相等的交界（同 Excel 自動字色的效果）
      } else if (f) {
        r.fc = lightenFg(f);
      }
    } else if (b && !f) {
      // 淺色主題：深色底色時自動用白字
      if (lum(b) < 0.18) r.fc = '#ffffff';
    }
    // 最低對比 3:1：Excel 的淡灰字（#A6A6A6）疊在條件式底色（#F8CBAD、色階藍…）上幾乎看不見。
    // 只在「字比底暗」時把字往黑色調整到 3:1（仍是灰／原色相，保留「淡化」的語意）；淺字配中間調底色不動。
    if (r.fc) {
      const bgc = r.bg ? hexToRgb(r.bg) : (theme === 'dark' ? DARK_SURFACE : [255, 255, 255]);
      const f0 = hexToRgb(r.fc); const Lb = lum(bgc);
      const cr = (a, c) => (Math.max(a, c) + 0.05) / (Math.min(a, c) + 0.05);
      if (lum(f0) <= Lb && cr(lum(f0), Lb) < 3) {
        let t = 0; let c = f0;
        while (cr(lum(c), Lb) < 3 && t < 1) { t += 0.04; c = mix(f0, [0, 0, 0], t); }
        r.fc = toHex(c);
      } else if (theme === 'dark' && lum(f0) > Lb && cr(lum(f0), Lb) < 3 && Lb < 0.1) {
        let t = 0; let c = f0;
        while (cr(lum(c), Lb) < 3 && t < 1) { t += 0.04; c = mix(f0, [255, 255, 255], t); }
        r.fc = toHex(c);
      }
    }
    adaptCache.set(key, r);
    return r;
  };
  function lightenFg(f) {
    const neutral = Math.max(...f) - Math.min(...f) < 12;
    if (neutral) { // 灰字：反轉灰階語意（淡＝不重要）
      const L = f[0] / 255;
      const v = Math.round((0.92 - L * 0.55) * 255);
      return toHex([v, v, v]);
    }
    let c = f; let t = 0;
    while (lum(c) < 0.32 && t < 0.9) { t += 0.1; c = mix(f, [255, 255, 255], t); }
    return toHex(c);
  }
  U.contrastText = (bg) => (U.lum(bg) > 0.4 ? '#111' : '#fff');

  /** "flags|bg|fc" → {b,i,u,bg,fc} */
  U.parseStyleStr = function (s) {
    if (s && typeof s === 'object') return s;
    const [flags = '', bg = '', fc = ''] = String(s || '').split('|');
    return { b: flags.includes('b') ? 1 : 0, i: flags.includes('i') ? 1 : 0, u: flags.includes('u') ? 1 : 0, bg: bg || null, fc: fc || null };
  };

  /* ------------------------------------------------------------------ Toast / 進度條 */
  let toastT = 0;
  U.toast = function (msg, ms) {
    const t = U.$('#toast');
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, ms || 2600);
  };
  const busy = new Map();
  U.progress = function (key, frac) { // frac: 0..1，null＝完成
    if (frac == null) busy.delete(key); else busy.set(key, frac);
    const bar = U.$('#topbar-progress');
    if (!busy.size) { bar.hidden = true; return; }
    let s = 0; busy.forEach((v) => { s += v; });
    bar.hidden = false;
    bar.firstElementChild.style.width = Math.max(4, (s / busy.size) * 100) + '%';
  };

  /* ------------------------------------------------------------------ 下載 */
  U.download = function (filename, text, mime) {
    const blob = new Blob([text], { type: mime || 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = U.h('a', { href: url, download: filename });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  };
  U.csvCell = function (v) {
    if (v === null || v === undefined) return '';
    let s = (v === true) ? 'TRUE' : (v === false) ? 'FALSE' : String(v);
    if (typeof v === 'string' && /^[=+\-@]/.test(s)) s = "'" + s; // 公式注入防護
    if (/[",\r\n]/.test(s) || /^\s|\s$/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
    return s;
  };

  /* ------------------------------------------------------------------ 資料載入 */
  const D = (AMS.data = {});
  (function initBase() {
    const qs = new URLSearchParams(location.search);
    let b = qs.get('data') || 'data/';
    // ?data= 只接受同源的相對路徑（拒絕 data:、blob:、//host、https://他站）：避免以假資料在本站網址下執行／冒充內容
    try {
      const u = new URL(b, location.href);
      if (u.origin !== location.origin || !/^https?:$/.test(u.protocol) || /^[a-z][a-z0-9+.-]*:|^\/\//i.test(b)) b = 'data/';
    } catch (e) { b = 'data/'; }
    if (!b.endsWith('/')) b += '/';
    D.base = b;
    // 版本戳記（tools/stamp_assets.py 寫入 index.html）：manifest 以建置雜湊為快取鍵
    const mv = document.querySelector('meta[name="ams-build"]');
    D.pageBuild = mv ? mv.getAttribute('content') || '' : '';
    D.appVersion = mv ? mv.getAttribute('data-app') || '' : '';
    D.chartVersion = mv ? mv.getAttribute('data-chart') || '' : '';
  })();
  D.cache = new Map(); // path → Promise<json>

  /* ---- 加密資料（tools/encrypt_data.py；CONTRACT.md「加密與封裝」）：data/meta.json 明文，其餘 <rel>.bin
   *   = 12B IV ‖ AES-256-GCM(gzip(JSON))，AAD＝相對路徑；金鑰＝PBKDF2-SHA256(密語, salt, 200000)。
   *   meta.json 404 或 enc:0 → 明文（本機開發／mock）。記住的金鑰存 localStorage ams.key（與 signal-atlas 同源，勿用 atlas.key）。 */
  D.encMeta = null;          // {enc,gzip,build,kdf,check}
  D.key = null;           // AES-GCM CryptoKey（解鎖後）
  const KEY_STORE = 'ams.key';
  const utf8 = (s) => new TextEncoder().encode(s);
  const b64enc = (u8) => { let s = ''; for (const c of u8) s += String.fromCharCode(c); return btoa(s); };
  const b64dec = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  D.enc = () => !!(D.encMeta && D.encMeta.enc);
  D.cryptoOK = () => !!(window.crypto && crypto.subtle && typeof crypto.subtle.deriveKey === 'function' && window.DecompressionStream && window.TextDecoder);
  D.loadMeta = async function () {
    let r;
    try { r = await fetch(D.base + 'meta.json' + (D.pageBuild ? '?v=' + encodeURIComponent(D.pageBuild) : '')); }
    catch (e) { throw new Error('無法連線：' + D.base + 'meta.json'); }
    if (r.status === 404) { D.encMeta = { enc: 0 }; return D.encMeta; }
    if (!r.ok) throw new Error('meta.json HTTP ' + r.status);
    D.encMeta = await r.json();
    if (D.encMeta.enc && (!D.encMeta.kdf || !D.encMeta.check)) throw new Error('meta.json 缺少 kdf/check');
    if (D.encMeta.build) D.pageBuild = D.encMeta.build; // manifest.json.bin 的 ?v= 以資料建置為準
    return D.encMeta;
  };
  async function decryptJSON(buf, rel) {
    let plain;
    try {
      plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: buf.subarray(0, 12), additionalData: utf8(rel) }, D.key, buf.subarray(12));
    } catch (e) { throw new Error('解密失敗：' + rel + '（密語或資料版本不符，請按「清除密語」後重新輸入）'); }
    const ab = D.encMeta.gzip === 0 ? plain : await new Response(new Blob([plain]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
    return JSON.parse(new TextDecoder('utf-8').decode(ab));
  }
  /** 實際網址：資料檔加上 ?v=<manifest.build>，同一建置的檔案才會共用快取；加密版檔名加 .bin */
  D.url = function (path) {
    const file = D.enc() ? path + '.bin' : path;
    if (path === 'manifest.json') return D.base + file + (D.pageBuild ? '?v=' + encodeURIComponent(D.pageBuild) : '');
    const v = D.manifest && D.manifest.build;
    return D.base + file + (v ? (file.includes('?') ? '&' : '?') + 'v=' + encodeURIComponent(v) : '');
  };
  D.fetchJSON = function (path, onProgress, estBytes) {
    if (D.cache.has(path)) return D.cache.get(path);
    const p = (async () => {
      const url = D.url(path);
      let res;
      // 沒有版本戳記的 manifest 一律向伺服器確認（304 很便宜），避免分塊清單與資料檔來自不同建置
      const cacheMode = path === 'manifest.json' && !D.pageBuild ? 'no-cache' : 'default';
      try { res = await fetch(url, { cache: cacheMode }); } catch (e) { throw new Error('無法連線：' + url); }
      if (!res.ok) throw new Error(`HTTP ${res.status}：${url}`);
      const encd = D.enc();
      let buf;
      if (!res.body || !onProgress) {
        if (!encd) { const j = await res.json(); if (onProgress) onProgress(1); return j; }
        buf = new Uint8Array(await res.arrayBuffer());
      } else {
        const ce = res.headers.get('content-encoding');
        let total = Number(res.headers.get('content-length')) || 0;
        if (ce && ce !== 'identity') total = 0; // 壓縮後長度不能當分母
        if (!total && estBytes && !encd) total = estBytes; // 密文已 gzip，content-length 就是精確值；估計值是明文大小不適用
        const reader = res.body.getReader();
        const chunks = []; let got = 0;
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value); got += value.length;
          if (total) onProgress(Math.min(0.98, got / total));
        }
        buf = new Uint8Array(got); let o = 0;
        for (const c of chunks) { buf.set(c, o); o += c.length; }
      }
      const j = encd ? await decryptJSON(buf, path) : JSON.parse(new TextDecoder('utf-8').decode(buf));
      if (onProgress) onProgress(1);
      return j;
    })();
    D.cache.set(path, p);
    p.catch(() => D.cache.delete(path));
    return p;
  };
  D.loadManifest = async function () {
    const m = await D.fetchJSON('manifest.json');
    D.manifest = m;
    D.sheets = m.sheets || [];
    D.byId = new Map(D.sheets.map((s) => [s.id, s]));
    D.byName = new Map(D.sheets.map((s) => [s.name, s]));
    return m;
  };
  D.meta = (id) => D.byId && D.byId.get(String(id));
  D.isChunked = (id) => { const s = D.meta(id); return !!(s && s.files && s.files.length > 1); };
  D.estBytes = (s) => (s && s.bytes ? Math.round(s.bytes / Math.max(1, (s.files || [1]).length)) : 0);

  /** 單檔工作表 */
  D.loadSheet = function (id, onProgress) {
    const s = D.meta(id);
    if (!s) return Promise.reject(new Error('找不到工作表 ' + id));
    if (D.isChunked(id)) return D.chunked(id).loadAll().then((c) => c.asJSON());
    const key = 'sheet:' + id;
    const pr = D.fetchJSON(s.files[0], (f) => { U.progress(key, f); onProgress && onProgress(f); }, D.estBytes(s));
    pr.then(() => U.progress(key, null), () => U.progress(key, null));
    return pr;
  };

  /* 查詢卡附加資料（card aux，CONTRACT.md）：index.json 一次、aux-NN.json 依 alias 按需載入 */
  D.loadAuxIndex = function (path) {
    const p = path || (D.manifest && D.manifest.aux && D.manifest.aux.card && D.manifest.aux.card.index) || 'card/index.json';
    return D.fetchJSON(p);
  };
  /** alias → {sec, compare, flags}（無資料回 null）；index 不存在時 reject */
  D.loadAux = async function (alias, path) {
    const ix = await D.loadAuxIndex(path);
    const k = ix && ix.alias ? ix.alias[alias] : undefined;
    if (k == null) return { ix, aux: null };
    const f = (ix.files && ix.files[k]) || ('card/aux-' + String(k).padStart(ix.part_width || 2, '0') + '.json');
    const j = await D.fetchJSON(f);
    return { ix, aux: (j.by_alias && j.by_alias[alias]) || null };
  };

  /* ------------------------------------------------------------------ 密語 → 金鑰（PBKDF2-HMAC-SHA-256 → AES-256-GCM） */
  async function verifyKey(key) {
    try {
      const buf = b64dec(D.encMeta.check);
      const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: buf.subarray(0, 12), additionalData: utf8('check') }, key, buf.subarray(12));
      return new TextDecoder().decode(pt) === 'ams-ok';
    } catch (e) { return false; }
  }
  async function deriveKey(pass) {
    const kdf = D.encMeta.kdf;
    const km = await crypto.subtle.importKey('raw', utf8(pass), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: kdf.hash || 'SHA-256', salt: b64dec(kdf.salt), iterations: Number(kdf.iter) || 200000 }, km,
      { name: 'AES-GCM', length: 256 }, true, ['decrypt']);
  }
  D.forgetKey = function () { try { localStorage.removeItem(KEY_STORE); } catch (e) { /* ignore */ } location.reload(); };
  /** 解鎖：先試 localStorage 記住的金鑰，否則顯示密語視窗；resolve 後 D.key 可用 */
  D.unlock = async function () {
    let stored = null;
    try { stored = localStorage.getItem(KEY_STORE); } catch (e) { /* 私密模式 */ }
    if (stored) {
      try {
        const key = await crypto.subtle.importKey('raw', b64dec(stored), { name: 'AES-GCM' }, true, ['decrypt']);
        if (await verifyKey(key)) { D.key = key; return; }
      } catch (e) { /* 壞掉的儲存值 */ }
      try { localStorage.removeItem(KEY_STORE); } catch (e) { /* ignore */ }
    }
    await new Promise((resolve) => showKeyModal(resolve));
  };
  function showKeyModal(resolve) {
    const input = U.h('input', { id: 'key-pass', name: 'passphrase', type: 'password', autocomplete: 'current-password', autocapitalize: 'off', spellcheck: 'false', required: true, placeholder: '密語' });
    const remember = U.h('input', { id: 'key-remember', type: 'checkbox', checked: true });
    const msg = U.h('div', { class: 'auth-msg', role: 'status', 'aria-live': 'polite' });
    const btn = U.h('button', { id: 'key-submit', class: 'btn primary auth-btn', type: 'submit' }, '解鎖');
    const form = U.h('form', { class: 'auth-card key-card', autocomplete: 'on', novalidate: true },
      U.h('div', { class: 'auth-brand' }, U.h('span', { class: 'brand-mark', 'aria-hidden': 'true' }, 'AMS'),
        U.h('div', null, U.h('h1', { id: 'key-title' }, '輸入密語'), U.h('p', { class: 'auth-sub' }, '本站資料已加密，輸入密語後才會在你的裝置上解密顯示。'))),
      U.h('label', { class: 'auth-field' }, U.h('span', {}, '密語'), input),
      U.h('label', { class: 'key-remember' }, remember, ' 記住此裝置（金鑰存在此瀏覽器，不再詢問）'),
      msg, btn,
      U.h('p', { class: 'auth-foot' }, '密語請向站台管理者索取'));
    const overlay = U.h('div', { id: 'key-gate', class: 'auth-gate key-gate', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'key-title' }, form);
    let busy = false;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (busy) return;
      const pass = input.value;
      if (!pass) { msg.textContent = '請輸入密語。'; msg.className = 'auth-msg bad'; input.focus(); return; }
      busy = true; btn.disabled = true; msg.textContent = '驗證中…'; msg.className = 'auth-msg';
      try {
        const key = await deriveKey(pass);
        if (await verifyKey(key)) {
          D.key = key;
          if (remember.checked) { try { localStorage.setItem(KEY_STORE, b64enc(new Uint8Array(await crypto.subtle.exportKey('raw', key)))); } catch (e2) { /* ignore */ } }
          overlay.remove(); document.body.classList.remove('auth-locked');
          resolve();
          return;
        }
        msg.textContent = '密語不正確'; msg.className = 'auth-msg bad'; input.select();
      } catch (err) {
        msg.textContent = '無法驗證：' + ((err && err.message) || err); msg.className = 'auth-msg bad';
      } finally { busy = false; btn.disabled = false; }
    });
    document.body.appendChild(overlay);
    document.body.classList.add('auth-locked');
    setTimeout(() => input.focus(), 0);
  }

  /* 分塊表：依序載入；可先載入指定部分 */
  const chunkedMap = new Map();
  D.chunked = function (id) {
    let c = chunkedMap.get(id);
    if (!c) { c = new Chunked(D.meta(id)); chunkedMap.set(id, c); }
    return c;
  };
  class Chunked {
    constructor(meta) {
      this.meta = meta; this.id = meta.id;
      this.files = meta.files;
      this.n = this.files.length;
      this.total = meta.rows || 0;
      this.offsets = Array.isArray(meta.part_offsets) && meta.part_offsets.length === this.n ? meta.part_offsets.slice() : null;
      this.parts = this.files.map((f, k) => ({ k, file: f, loaded: false, promise: null, rows: 0, offset: this.offsets ? this.offsets[k] : null, frac: 0 }));
      this.rows = []; // 全域索引（稀疏）
      this.loadedRows = 0;
      this.sheet = null; // 第一個到達的部分之中繼資料
      this.styleIdx = new Map(); // 樣式字串 → 全域索引
      this.styles = [];
      this.rowStyles = new Map();
      this.cellStyles = new Map();
      this.bars = new Map();
      this.listeners = new Set();
      this.allPromise = null;
    }
    on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
    emit(ev) { this.listeners.forEach((fn) => { try { fn(ev); } catch (e) { console.error(e); } }); }
    partOf(g) { // 全域索引 → 部分
      if (!this.offsets) return null;
      let k = 0;
      for (let i = 0; i < this.offsets.length; i++) if (this.offsets[i] <= g) k = i;
      return k;
    }
    progress() {
      let s = 0; this.parts.forEach((p) => { s += p.loaded ? 1 : p.frac; });
      return s / this.n;
    }
    ensurePart(k) {
      const p = this.parts[k];
      if (!p) return Promise.reject(new Error('無此分塊 ' + k));
      if (p.promise) return p.promise;
      const key = 'chunk:' + this.id + ':' + k;
      p.promise = D.fetchJSON(p.file, (f) => { p.frac = f; U.progress(key, f); this.emit({ type: 'progress' }); }, D.estBytes(this.meta))
        .then((j) => {
          U.progress(key, null);
          this.ingest(k, j);
          D.cache.delete(p.file); // 資料已併入，釋放原始 JSON
          return this;
        }, (e) => { U.progress(key, null); p.promise = null; throw e; });
      return p.promise;
    }
    ingest(k, j) {
      const p = this.parts[k];
      const part = j.part || {};
      let off = part.row_offset;
      if (off == null) off = p.offset;
      if (off == null) { // 沒有 offsets 時需依序
        off = 0; for (let i = 0; i < k; i++) off += this.parts[i].rows;
      }
      p.offset = off; p.rows = j.rows.length; p.loaded = true;
      if (!this.sheet) {
        this.sheet = Object.assign({}, j); delete this.sheet.rows;
        delete this.sheet.row_styles; delete this.sheet.cell_styles; delete this.sheet.bars; delete this.sheet.styles;
      }
      if (!this.total || this.total < off + j.rows.length) this.total = Math.max(this.total, off + j.rows.length);
      const rows = j.rows;
      for (let i = 0; i < rows.length; i++) this.rows[off + i] = rows[i];
      this.loadedRows += rows.length;
      // 樣式：各部分的樣式表可能不同 → 併入全域表
      const map = (j.styles || []).map((s) => {
        const key = typeof s === 'string' ? s : JSON.stringify(s);
        let gi = this.styleIdx.get(key);
        if (gi === undefined) { gi = this.styles.length; this.styles.push(s); this.styleIdx.set(key, gi); }
        return gi;
      });
      // 索引是區域（相對本部分）還是全域：若最大索引 ≥ 本部分列數 → 全域
      const maxIdx = (arr) => { let m = -1; if (arr) for (const e of arr) if (e[0] > m) m = e[0]; return m; };
      const localBase = (arr) => (maxIdx(arr) >= rows.length ? 0 : off);
      if (j.row_styles) { const b = localBase(j.row_styles); for (const [r, s] of j.row_styles) this.rowStyles.set(b + r, map[s] ?? s); }
      if (j.cell_styles) { const b = localBase(j.cell_styles); const nc = (j.columns || this.sheet.columns).length; for (const [r, c, s] of j.cell_styles) this.cellStyles.set((b + r) * nc + c, map[s] ?? s); }
      if (j.bars) { const b = localBase(j.bars); const nc = (j.columns || this.sheet.columns).length; for (const [r, c, pp, col] of j.bars) this.bars.set((b + r) * nc + c, [pp, col]); }
      if (this.offsets == null) {
        // 推得 offsets（依序載入時）
      }
      this.emit({ type: 'part', k, offset: off, count: rows.length });
    }
    loadAll(first) {
      if (this.allPromise && first == null) return this.allPromise;
      const order = [];
      if (first != null && first >= 0 && first < this.n) order.push(first);
      for (let k = 0; k < this.n; k++) if (k !== first) order.push(k);
      const run = (async () => {
        // 沒有 offsets 時必須依序載入（此時一個部分失敗就無法算出後面的列位置 → 停止）
        const seq = !this.offsets;
        if (seq) order.sort((a, b) => a - b);
        const failed = [];
        for (const k of order) {
          try { await this.ensurePart(k); } catch (e) {
            failed.push({ k, e });
            this.emit({ type: 'error', k, error: e });
            if (seq) break;
          }
        }
        if (failed.length) {
          const err = new Error(`第 ${failed.map((x) => x.k + 1).join('、')} 部分載入失敗：${failed[0].e && failed[0].e.message}`);
          err.parts = failed.map((x) => x.k);
          throw err;
        }
        this.emit({ type: 'done' });
        return this;
      })();
      if (!this.allPromise) this.allPromise = run;
      // 失敗後清掉快取的 promise，讓「重試」真的重新抓取
      run.catch(() => { if (this.allPromise === run) this.allPromise = null; });
      return run;
    }
    failedParts() { return this.parts.filter((p) => !p.loaded && !p.promise).map((p) => p.k); }
    allLoaded() { return this.parts.every((p) => p.loaded); }
    asJSON() {
      return Object.assign({}, this.sheet, { rows: this.rows, styles: this.styles });
    }
  }
  D.Chunked = Chunked;

  /* ------------------------------------------------------------------ 位號索引（05）與設備總表（03） */
  const IX = (AMS.index = {});
  IX.norm = (q) => String(q == null ? '' : q).replace(/=/g, '').replace(/\s+/g, ' ').trim().toUpperCase();
  IX.load = function () {
    if (IX._p) return IX._p;
    IX._p = (async () => {
      const cfg = (D.manifest && D.manifest.search) || {};
      const sid = cfg.index_sheet || '05';
      const j = await D.loadSheet(sid);
      const kc = cfg.key_col ?? 0; const ac = cfg.alias_col ?? 4;
      IX.sheet = j; IX.sid = sid; IX.kc = kc; IX.ac = ac;
      IX.srcCol = cfg.src_col ?? 2; IX.tagCol = cfg.tag_col ?? 3; IX.countCol = cfg.count_col ?? 7;
      const first = new Map(); const keys = [];
      j.rows.forEach((r, i) => {
        const k = U.text(r[kc]);
        if (!first.has(k)) { first.set(k, i); keys.push(k); }
      });
      IX.first = first; IX.keys = keys;
      return IX;
    })();
    IX._p.catch(() => { IX._p = null; });
    return IX._p;
  };
  IX.aliasesOf = function (key) { // 同一鍵的所有 alias（去重，依出現順序）
    const out = []; const seen = new Set();
    const i0 = IX.first.get(key);
    if (i0 == null) return out;
    const rows = IX.sheet.rows;
    for (let i = i0; i < rows.length && U.text(rows[i][IX.kc]) === key; i++) {
      const a = U.text(rows[i][IX.ac]);
      if (a && !seen.has(a)) { seen.add(a); out.push(a); }
    }
    // 保險：若 05 不是依鍵排序
    if (out.length <= 1) {
      rows.forEach((r) => { if (U.text(r[IX.kc]) === key) { const a = U.text(r[IX.ac]); if (a && !seen.has(a)) { seen.add(a); out.push(a); } } });
    }
    return out;
  };
  IX.suggest = function (q, limit) {
    limit = limit || 12;
    const n = IX.norm(q);
    if (!n) return [];
    const ex = []; const pre = []; const sub = [];
    for (const k of IX.keys) {
      if (k === n) ex.push(k);
      else if (k.startsWith(n)) { if (pre.length < limit) pre.push(k); }
      else if (sub.length < limit && k.includes(n)) sub.push(k);
      if (pre.length >= limit && sub.length >= limit && ex.length) break;
    }
    return ex.concat(pre, sub).slice(0, limit).map((k) => {
      const r = IX.sheet.rows[IX.first.get(k)];
      return { key: k, src: U.text(r[IX.srcCol]), alias: U.text(r[IX.ac]), tag: U.text(r[IX.tagCol]), n: U.raw(r[IX.countCol]) };
    });
  };
  const DV = (AMS.devices = {});
  DV.load = function () {
    if (DV._p) return DV._p;
    DV._p = (async () => {
      const j = await D.loadSheet('03');
      DV.sheet = j;
      DV.byAlias = new Map();
      j.rows.forEach((r, i) => { const a = U.text(r[1]); if (a && !DV.byAlias.has(a)) DV.byAlias.set(a, i); });
      return DV;
    })();
    DV._p.catch(() => { DV._p = null; });
    return DV._p;
  };

  /* ------------------------------------------------------------------ 連結 */
  /** 連結物件 {s, r, f?} → 站內網址（r 一律轉成非負整數；f 為逐欄篩選，鍵可為欄號或欄名） */
  AMS.linkHref = function (l) {
    if (!l) return null;
    const s = String(l.s);
    const m = D.meta(s);
    if (m && m.mode === 'card') return '#/card/' + (l.q ? encodeURIComponent(String(l.q)) : '');
    const p = [];
    const r = l.r === null || l.r === undefined || l.r === '' ? NaN : Number(l.r);
    if (Number.isInteger(r) && r >= 0) p.push('r=' + r);
    if (l.f && typeof l.f === 'object' && !Array.isArray(l.f)) p.push('f=' + encodeURIComponent(JSON.stringify(l.f)));
    // 沒有目標列的表格連結：明確重設搜尋／篩選（否則會沿用上次造訪時的篩選，落地畫面與連結的說明矛盾）
    if (!p.length && m && m.mode === 'table') p.push('q=');
    return '#/s/' + encodeURIComponent(s) + (p.length ? '?' + p.join('&') : '');
  };
  AMS.cellLinkHTML = function (c, text, cls) {
    if (c && typeof c === 'object') {
      if (c.l) { const href = AMS.linkHref(c.l); return `<a class="${cls || 'lk'}" href="${U.esc(href)}">${text}</a>`; }
      if (c.u && /^(https?:|mailto:)/i.test(c.u)) return `<a class="${cls || 'lk'}" href="${U.esc(c.u)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
    }
    return text;
  };
  AMS.isAlias = (s) => /^D\d{5}$/.test(String(s));

  /* ------------------------------------------------------------------ 覆蓋層與「上一頁」（僅手機）
   * 手機上全螢幕的列詳情、抽屜、區塊表格看起來像另一頁：開啟時推入一筆同網址的歷史，
   * 按 Android 返回鍵（popstate）就關閉覆蓋層，而不是離開這張工作表。桌機不改變歷史。 */
  const OV = (AMS.overlay = { stack: [], skip: 0, pending: 0 });
  OV.open = function (name, close) {
    if (!U.isMobile()) return null;
    const tok = { name, close, live: true };
    try { history.pushState({ amsOv: name }, '', location.href); } catch (e) { return null; }
    OV.stack.push(tok);
    return tok;
  };
  const drop = (tok) => { tok.live = false; const i = OV.stack.indexOf(tok); if (i >= 0) OV.stack.splice(i, 1); };
  /** 由介面關閉（✕、Esc、遮罩）：退回推入的那筆歷史（同一輪的多個關閉合併成一次 history.go） */
  OV.done = function (tok) {
    if (!tok || !tok.live) return;
    drop(tok);
    OV.pending++;
    if (OV.pending === 1) {
      queueMicrotask(() => {
        const n = OV.pending; OV.pending = 0;
        if (!(history.state && history.state.amsOv)) return;
        OV.skip++;
        history.go(-n);
      });
    }
  };
  /** 由站內導覽接手：不退回，改以 location.replace 覆蓋掉那筆同網址歷史 */
  OV.forgetAll = function () { OV.stack.slice().forEach(drop); };
  OV.live = () => OV.stack.length > 0;
  window.addEventListener('popstate', () => {
    if (OV.skip) { OV.skip--; return; }
    const tok = OV.stack.pop();
    if (tok && tok.live) { tok.live = false; try { tok.close(); } catch (e) { console.error(e); } }
  });
  // 覆蓋層開著時點站內連結：用 replace 取代同網址的覆蓋層歷史，返回鍵才會回到原工作表
  document.addEventListener('click', (e) => {
    if (!OV.live() || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest && e.target.closest('a[href^="#/"]');
    if (!a || a.target) return;
    const href = a.getAttribute('href');
    if (href === location.hash) return; // 同網址：交給 app.js 重新套用路由
    e.preventDefault();
    OV.forgetAll();
    location.replace(href);
  }, true);

  /* ------------------------------------------------------------------ 列詳情側板 */
  const DT = (AMS.detail = {});
  DT.open = function (opt) {
    // opt: {kicker, title, tools(html|node), body(node|html), onPrev, onNext}
    const el = U.$('#detail');
    U.$('#detail-kicker').textContent = opt.kicker || '';
    U.$('#detail-h').textContent = opt.title || '';
    const tools = U.$('#detail-tools'); tools.innerHTML = '';
    if (opt.tools) { if (typeof opt.tools === 'string') tools.innerHTML = opt.tools; else tools.appendChild(opt.tools); }
    tools.hidden = !opt.tools;
    const body = U.$('#detail-body'); body.innerHTML = '';
    if (typeof opt.body === 'string') body.innerHTML = opt.body; else if (opt.body) body.appendChild(opt.body);
    body.scrollTop = 0;
    DT.onPrev = opt.onPrev; DT.onNext = opt.onNext; DT.onClose = opt.onClose;
    U.$('#detail-prev').disabled = !opt.onPrev; U.$('#detail-next').disabled = !opt.onNext;
    const wasHidden = el.hidden;
    el.hidden = false;
    document.body.classList.add('detail-open');
    if (wasHidden) {
      DT.returnFocus = document.activeElement;
      requestAnimationFrame(() => U.$('#detail-close').focus({ preventScroll: true }));
      DT.tok = OV.open('detail', () => DT.close());
    }
  };
  DT.close = function () {
    const el = U.$('#detail');
    if (el.hidden) return;
    el.hidden = true;
    document.body.classList.remove('detail-open');
    const tok = DT.tok; DT.tok = null; OV.done(tok);
    const f = DT.onClose; DT.onClose = null;
    if (f) f();
    if (DT.returnFocus && DT.returnFocus.focus) try { DT.returnFocus.focus({ preventScroll: true }); } catch (e) { /**/ }
  };
  DT.isOpen = () => !U.$('#detail').hidden;
  document.addEventListener('DOMContentLoaded', () => {
    U.$('#detail-close').addEventListener('click', DT.close);
    U.$('#detail-prev').addEventListener('click', () => DT.onPrev && DT.onPrev());
    U.$('#detail-next').addEventListener('click', () => DT.onNext && DT.onNext());
    U.$('#detail').addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); DT.close(); }
      else if ((e.key === 'ArrowUp' || e.key === 'k') && DT.onPrev && !/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) { e.preventDefault(); DT.onPrev(); }
      else if ((e.key === 'ArrowDown' || e.key === 'j') && DT.onNext && !/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) { e.preventDefault(); DT.onNext(); }
    });
    U.$('#detail').addEventListener('click', (e) => {
      const a = e.target.closest('a[href^="#/"]');
      if (a && U.isMobile()) DT.close();
    });
  });

  /* ------------------------------------------------------------------ 自動完成（ARIA combobox） */
  let acSeq = 0;
  class Autocomplete {
    /** opts: {fetch(q) → Promise<items>|items, render(item,q) → html, onPick(item), onEnter(text), prepare() → Promise} */
    constructor(input, opts) {
      this.input = input; this.o = opts; this.items = []; this.active = -1;
      this.id = 'ac-' + (++acSeq);
      this.list = U.h('ul', { class: 'ac-list', role: 'listbox', id: this.id, hidden: true });
      const wrap = input.parentElement;
      wrap.classList.add('ac-wrap');
      wrap.appendChild(this.list);
      input.setAttribute('role', 'combobox');
      input.setAttribute('aria-autocomplete', 'list');
      input.setAttribute('aria-expanded', 'false');
      input.setAttribute('aria-controls', this.id);
      this.upd = U.debounce(() => this.update(), 90);
      input.addEventListener('input', () => this.upd());
      input.addEventListener('focus', () => { if (this.o.prepare) this.o.prepare(); if (input.value) this.upd(); });
      input.addEventListener('keydown', (e) => this.key(e));
      input.addEventListener('blur', () => setTimeout(() => this.hide(), 160));
      this.list.addEventListener('mousedown', (e) => e.preventDefault());
      this.list.addEventListener('click', (e) => {
        const li = e.target.closest('li[data-i]');
        if (li) this.pick(+li.dataset.i);
      });
    }
    async update() {
      const q = this.input.value;
      if (!q.trim()) { this.hide(); return; }
      let items;
      try { items = await this.o.fetch(q); } catch (e) { items = []; }
      if (q !== this.input.value) return;
      this.items = items || []; this.active = -1;
      if (!this.items.length) {
        this.list.innerHTML = `<li class="ac-empty" role="option" aria-disabled="true">${this.o.emptyText || '無符合的鍵'}</li>`;
      } else {
        this.list.innerHTML = this.items.map((it, i) => `<li role="option" id="${this.id}-${i}" data-i="${i}" aria-selected="false">${this.o.render(it, q)}</li>`).join('');
      }
      this.show();
    }
    show() { this.list.hidden = false; this.input.setAttribute('aria-expanded', 'true'); }
    hide() { this.list.hidden = true; this.input.setAttribute('aria-expanded', 'false'); this.input.removeAttribute('aria-activedescendant'); }
    setActive(i) {
      const lis = this.list.querySelectorAll('li[data-i]');
      if (!lis.length) return;
      this.active = (i + lis.length) % lis.length;
      lis.forEach((li, k) => { li.setAttribute('aria-selected', k === this.active ? 'true' : 'false'); });
      const li = lis[this.active];
      this.input.setAttribute('aria-activedescendant', li.id);
      li.scrollIntoView({ block: 'nearest' });
    }
    key(e) {
      const open = !this.list.hidden;
      if (e.key === 'ArrowDown') { e.preventDefault(); if (!open) this.update(); else this.setActive(this.active + 1); }
      else if (e.key === 'ArrowUp') { if (open) { e.preventDefault(); this.setActive(this.active - 1); } }
      else if (e.key === 'Enter') {
        e.preventDefault();
        if (open && this.active >= 0) this.pick(this.active);
        else { this.hide(); this.o.onEnter && this.o.onEnter(this.input.value); }
      } else if (e.key === 'Escape') { if (open) { e.preventDefault(); this.hide(); } }
    }
    pick(i) {
      const it = this.items[i]; if (!it) return;
      // 點選時焦點仍留在輸入框（mousedown 已 preventDefault），呼叫端「焦點在框內就不改值」的保護會讓框內留著打到一半的字 → 這裡先帶入
      if (it.key != null) this.input.value = String(it.key);
      this.hide(); this.o.onPick(it);
    }
  }
  AMS.Autocomplete = Autocomplete;
  AMS.hilite = function (text, q) {
    const t = String(text); const n = IX.norm(q);
    const i = n ? t.toUpperCase().indexOf(n) : -1;
    if (i < 0) return U.esc(t);
    return U.esc(t.slice(0, i)) + '<mark>' + U.esc(t.slice(i, i + n.length)) + '</mark>' + U.esc(t.slice(i + n.length));
  };
  AMS.tagSuggestSource = {
    prepare: () => IX.load().catch(() => {}),
    fetch: async (q) => { await IX.load(); return IX.suggest(q, 12); },
    render: (it, q) => `<span class="ac-key">${AMS.hilite(it.key, q)}</span><span class="ac-hint">${U.esc(it.src || '')}${it.alias ? ' · ' + U.esc(it.alias) : ''}${it.tag && it.tag !== it.key ? ' · ' + U.esc(it.tag) : ''}${it.n > 1 ? ` · <b class="warn">${it.n} 台</b>` : ''}</span>`,
  };
})();
