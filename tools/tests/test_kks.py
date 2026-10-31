# -*- coding: utf-8 -*-
"""接線路徑的 KKS 版（v17，CONTRACT.md「v17」）：GE 編號卡的接線路徑、迴路圖比照到「沒有 GE 編號、只有 KKS」的元件。
資料：card/index.json 的 wire（AMS 設備卡的接線路徑塊 card/wire-NN.json，與 aux 分塊同一個編號）與 kkstag（KKS 編號卡 card/kkstag.json＋kkstag-loc-NN.json）。
AMS 設備卡：G12HAP70BT001（HRSG 給水的傳送器，BOP 接線圖 D1003）摘要多「接線路徑」組——接線圖、電纜表、控制盤 G12CCH02UC201（H12 RIO），
盤端子 CA007-1A5B 29／30 以 H12 的組態核對（SHRA，✓）；迴路圖一張、編號 LP-G12HAP70BT001。沒有接線路徑的 AMS 設備不出這一組。
KKS 編號卡：AMS 沒有的 G11LAE12QM004（HP 末級減溫隔離閥，D1003 p.301 直拉到 H11 RIO）打設備 KKS、訊號 KKS（…XB61）、小寫都開得到；
頂列 Enter 也開到它；打一半的 KKS 在查無頁列出 KKS 候選；本身是 GE 元件的 AMS 設備，接線路徑塊帶 GE 編號卡的路徑與連到 GE 卡的說明；手機寬度不橫向捲動；console 零錯誤。
v18 迴路圖：「⤢ 放大檢視」開燈箱（Esc 關、焦點回按鈕；點藍字第二行，說明列是整段「變數＋說明」、同一段一起標色、圖區高度不變；
手機開啟就看得到字、兩指放大定點不動、點字看全文、✕ 關）；G11LAE12QN001 的 Mark VIe 變數名不截、底下有藍字的組態說明與訊號 KKS；
G11LAB65QM021 的長變數把 Mark VIe 欄放寬、接線圖說明不截在 160 字；G11MSA30GH001 跨兩片卡、同名通道照板位對變數；FF 元件 96AT-TC-1A 也有藍字說明。"""
from e2e_common import Checks, browser, login, load_card, shot

AMS_TAG = 'G12HAP70BT001'
KKS_TAG = 'G11LAE12QM004'

DATA_JS = """async () => { const ix = await AMS.data.fetchJSON('card/index.json');
  const w = ix.wire || {}; const k = ix.kkstag || {};
  const K = await AMS.kkstag.load(); const E = K ? K.j.entries : [];
  const i = E.findIndex((e) => e.t === '%s'); const loc = i >= 0 ? await AMS.kkstag.loadLoc(i) : {};
  const lo = loc.lo || {}; const wp = lo.wp || null;
  const al = AMS.index.first.get('%s') != null ? String(AMS.index.sheet.rows[AMS.index.first.get('%s')][AMS.index.ac]) : '';
  const aw = al ? await AMS.data.loadWire(al) : {}; const a = (aw.w || {}).wp || null;
  const ge = []; for (const f of (w.files || []).filter(Boolean)) { const j = await AMS.data.fetchJSON(f); for (const [al2, v] of Object.entries(j.by_alias || {})) if (v.ge && ge.length < 3) ge.push(al2 + '|' + v.ge + '|' + (v.wp && v.wp.u)); }
  const sumOf = (x, key) => (x ? x.sum.filter((r) => r[0] === key).map((r) => r[1]).join('｜') : '');
  return { wireFiles: (w.files || []).filter(Boolean).length, wireAliases: w.aliases || 0, kkN: k.n || 0, kkFiles: (k.files || []).length, entries: E.length,
    hit: i, mode: wp && wp.mode, u: wp && wp.u, ct: wp && wp.ct, no: wp && wp.d ? wp.d.no : '', kk: wp && wp.d ? (wp.d.kk || '') : '', pk: wp && wp.d ? wp.d.pk : '',
    panel: sumOf(wp, '電子室盤'), mv: sumOf(wp, 'Mark VIe'), room: sumOf(wp, '電纜與房間'), ok: wp ? wp.t.filter((r) => r[5] === 'same').length : 0, t: wp ? wp.t.length : 0,
    hops: wp ? wp.rows.filter((r) => r[4] && r[4].marks).map((r) => r[4].hop) : [],
    al, aMode: a && a.mode, aU: a && a.u, aNo: a && a.d ? a.d.no : '', aPanel: sumOf(a, '電子室盤'), aMv: sumOf(a, 'Mark VIe'), aT: a ? a.t.map((r) => r.slice(0, 6).join('|')) : [],
    aHops: a ? a.rows.filter((r) => r[4] && r[4].marks).map((r) => r[4].hop) : [], ge }; }""" % (KKS_TAG, AMS_TAG, AMS_TAG)

PATHS_OF = """async (tag) => { const IX = AMS.index; const r = IX.first.get(tag); let o = null, src = '';
  if (r != null) { const aw = await AMS.data.loadWire(String(IX.sheet.rows[r][IX.ac])); o = aw.w || null; src = 'ams'; }
  else { const K = await AMS.kkstag.load(); const i = K ? K.j.entries.findIndex((e) => e.t === tag) : -1;
    if (i >= 0) { o = (await AMS.kkstag.loadLoc(i)).lo || null; src = 'kks'; } }
  const ps = o ? (o.wp ? [o.wp] : []).concat(o.wpx || []) : [];
  return { src, n: ps.length, pid: o && o.pd ? o.pd.length : 0, hmi: o && o.hm ? o.hm.length : 0,
    paths: ps.map((p) => ({ mode: p.mode, u: p.u, ct: p.ct || '', sum: p.sum.map((x) => x[0] + '：' + x[1]), notes: (p.n || []).map((x) => x[0]),
      hops: p.rows.filter((x) => x[4] && x[4].marks).map((x) => x[4].hop), t: p.t.map((x) => x.slice(0, 6).join('|')) })) }; }"""

WIRE_STATE = """(sel) => { const g = document.querySelector(sel); if (!g) return null;
  return { loading: /載入中/.test(g.textContent), paths: g.querySelectorAll('.wire-path').length, sum: g.querySelectorAll('table.wire-sum tbody tr').length,
    cond: g.querySelectorAll('table.wire-cond tbody tr').length, loop: g.querySelectorAll('details.wire-loop').length, svg: g.querySelectorAll('svg.loop-svg').length,
    img: g.querySelectorAll('.wire-pics img').length, sheets: g.querySelectorAll('.pid-sheet').length, note: (g.querySelector('.aux-note') || {}).textContent || '',
    loopTxt: [...g.querySelectorAll('svg.loop-svg text')].map((t) => t.textContent).join(' ').slice(0, 3000), text: g.textContent.slice(0, 600) }; }"""


# v18 迴路圖燈箱：狀態、兩指開合（相距 80px 拉到 240px）、點一下圖上的一段字
LOOP_LB = """() => { const ov = document.querySelector('.loop-lb'); if (!ov) return null; const st = ov.querySelector('.loop-stage'); const pk = ov.querySelector('.loop-pick');
  return { svg: ov.querySelectorAll('svg.loop-svg').length, w: st ? parseFloat(st.style.width) || 0 : 0, z: (ov.querySelector('.pid-zoomv') || {}).textContent || '',
    pick: pk && !pk.classList.contains('hint') ? pk.textContent : '', vh: ov.querySelector('.loop-view').clientHeight, open: document.body.classList.contains('modal-open') }; }"""
PINCH = """async () => { const v = document.querySelector('.loop-lb .loop-view'); const st = v.querySelector('.loop-stage'); const r = v.getBoundingClientRect();
  const cx = r.left + r.width * 0.8; const cy = r.top + r.height / 2;   // 兩指中點在右側：手指底下那一點（圖上的位置 a）放大前後要不動
  const at = () => (cx - r.left - v.clientLeft - parseFloat(st.style.left)) / parseFloat(st.style.width);
  const a0 = at();
  const ev = (type, id, x) => v.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: 'touch', isPrimary: id === 1, clientX: x, clientY: cy, bubbles: true }));
  ev('pointerdown', 1, cx - 40); ev('pointerdown', 2, cx + 40);
  for (let k = 1; k <= 4; k++) { ev('pointermove', 1, cx - 40 - 20 * k); ev('pointermove', 2, cx + 40 + 20 * k); }
  ev('pointerup', 1, cx - 120); ev('pointerup', 2, cx + 120);
  await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
  return { a0, a1: at() }; }"""
TAP_TEXT = """() => { const v = document.querySelector('.loop-lb .loop-view'); const vr = v.getBoundingClientRect();
  const t = [...v.querySelectorAll('svg text')].find((el) => { const r = el.getBoundingClientRect(); const x = r.left + r.width / 2; const y = r.top + r.height / 2;   // 字的中心在畫面內
    return r.width > 6 && x > vr.left && x < vr.right && y > vr.top && y < vr.bottom && document.elementFromPoint(x, y) === el; });
  if (!t) return ''; const r = t.getBoundingClientRect(); const x = r.left + r.width / 2; const y = r.top + r.height / 2;
  for (const type of ['pointerdown', 'pointerup']) v.dispatchEvent(new PointerEvent(type, { pointerId: 5, pointerType: 'touch', isPrimary: true, clientX: x, clientY: y, bubbles: true }));
  const ti = t.querySelector('title'); return t.getAttribute('data-full') || (ti ? ti.textContent : t.textContent); }"""
# 點藍字說明的第二行（換行的那一段）：說明列要是整段（Mark VIe 列＋說明），同一段的每一行都標色，圖區高度不變
TAP_DESC2 = """() => { const v = document.querySelector('.loop-lb .loop-view'); const vr = v.getBoundingClientRect();
  const ds = [...v.querySelectorAll('svg text.lp-d[data-full]')];
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.top > vr.top && r.bottom < vr.bottom && r.left > vr.left && r.right < vr.right; };
  const t = ds.find((el, i) => i > 0 && ds[i - 1].getAttribute('data-full') === el.getAttribute('data-full') && vis(el)); if (!t) return null;
  const r = t.getBoundingClientRect(); const x = r.left + r.width / 2; const y = r.top + r.height / 2; const h0 = v.clientHeight;
  for (const type of ['pointerdown', 'pointerup']) v.dispatchEvent(new PointerEvent(type, { pointerId: 7, pointerType: 'mouse', button: 0, isPrimary: true, clientX: x, clientY: y, bubbles: true }));
  return { line: t.textContent, pick: document.querySelector('.loop-lb .loop-pick').textContent, h0, h1: v.clientHeight, hl: v.querySelectorAll('text.lp-pick').length }; }"""
LOOP_TXT = """() => { const s = [...document.querySelectorAll('svg.loop-svg')];
  return { rows: s.flatMap((x) => [...x.querySelectorAll('text.lp-m.xs')].map((t) => t.textContent)), desc: s.flatMap((x) => [...x.querySelectorAll('text.lp-d')].map((t) => t.textContent)),
    w: s.map((x) => x.viewBox.baseVal.width), txt: s.map((x) => [...x.querySelectorAll('text')].map((t) => t.textContent).join(' ')).join('｜') }; }"""


def wait_wire(page, sel, ms=30000):
    page.wait_for_function("(s) => { const g = document.querySelector(s); return !g || !/載入中/.test(g.textContent); }", arg=sel, timeout=ms)
    page.wait_for_timeout(600)
    return page.evaluate(WIRE_STATE, sel)


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        login(page, ctx)
        page.wait_for_function('AMS.index && AMS.kkstag', timeout=30000)
        page.evaluate('AMS.index.load()')
        v = page.evaluate(DATA_JS)
        ck('index.wire：AMS 設備卡的接線路徑塊有 700 台以上、分成好幾個檔；index.kkstag：KKS 編號卡 1,000 個以上條目、接線路徑分檔',
           bool(v) and v['wireAliases'] >= 700 and v['wireFiles'] >= 5 and v['kkN'] >= 1000 and v['kkFiles'] >= 4 and v['entries'] == v['kkN'],
           v and (v['wireAliases'], v['wireFiles'], v['kkN'], v['kkFiles']))
        ck('KKS 編號卡 %s：直拉（direct）、機組 G11、控制器 H11、迴路圖編號 LP-%s（好幾條時加 -Pn）、d.kk 空（KKS 不重複印）' % (KKS_TAG, KKS_TAG),
           bool(v) and v['hit'] >= 0 and v['mode'] == 'direct' and v['u'] == 'G11' and v['ct'] == 'H11' and v['no'].startswith('LP-' + KKS_TAG) and v['kk'] == '',
           v and (v['hit'], v['mode'], v['u'], v['ct'], v['no'], v['kk']))
        ck('%s：電子室盤是 G11CCH02UC201（H11 RIO，U1 ANNEX BUILDING）、盤端子以 H11 的組態核對 ✓ 至少 8 芯、電纜表有房間、接線圖是第一跳' % KKS_TAG,
           bool(v) and 'G11CCH02UC201' in v['panel'] and 'ANNEX' in v['panel'] and 'H11' in v['mv'] and v['ok'] >= 8 and v['room'] != '' and v['hops'][:1] == ['wire'],
           v and (v['panel'], v['mv'][:120], v['ok'], v['t'], v['room'][:80], v['hops']))
        ck('AMS 設備 %s：接線路徑塊有路徑（G12、BOP 接線圖）；盤 G12CCH02UC201、Mark VIe 列寫 H12；CA007-1A5B 29／30 核對 ✓；迴路圖編號 LP-%s' % (AMS_TAG, AMS_TAG),
           bool(v) and v['al'] != '' and v['aU'] == 'G12' and 'G12CCH02UC201' in v['aPanel'] and 'H12' in v['aMv']
           and any('CA007-1A5B' in x and x.endswith('|same') for x in v['aT']) and v['aNo'] == 'LP-' + AMS_TAG,
           v and (v['al'], v['aU'], v['aPanel'][:80], v['aMv'][:100], v['aT'][:3], v['aNo']))
        ck('本身是 GE 元件的 AMS 設備：接線路徑塊帶 GE 編號卡的路徑（ge＝GE 編號）', bool(v) and len(v['ge']) >= 1, v and v['ge'])
        # ---- 第二輪查核後補的：溫度兩段頁、MCC 格、別台機組的接線箱、盤側沒畫標籤、KKS 卡的 P&ID／圖控
        tt = page.evaluate(PATHS_OF, 'C00LBG30BT401')
        p0 = (tt or {}).get('paths') or [{}]
        sm = ' ／ '.join(p0[0].get('sum') or [])
        ck('溫度兩段頁 C00LBG30BT401（D1003 p.911）：多「熱電偶 → 傳送器」列（_TE 補償導線 TC TYPE E、3(+)／2(-)）、下一列是「傳送器 → 盤」、盤是 C00CCF01UC0015',
           '熱電偶 → 傳送器：C00LBG30BT401_TE' in sm and 'C00LBG30BT401_TE-WG-001' in sm and 'TC TYPE E' in sm and '3(+)' in sm and '傳送器 → 盤：' in sm
           and 'C00CCF01UC0015' in sm, sm[:400])
        al = page.evaluate(PATHS_OF, 'C00LBG40BT411')
        lo = page.evaluate(PATHS_OF, 'C00LBG30BT411')
        ck('溫度兩段頁上下段 KKS 不一致（p.916：上段 C00LBG40BT411、下段 C00LBG30BT411，後者另有 p.912 的路徑）：路徑列在上段的 KKS、註記寫明下段寫的；下段的 KKS 仍開得到自己的路徑',
           bool(al) and al['n'] >= 1 and any('C00LBG30BT411 另有自己的接線路徑' in n and '路徑列在 C00LBG40BT411' in n for p in al['paths'] for n in p['notes'])
           and bool(lo) and lo['n'] >= 1,
           (al and [p['notes'][:1] for p in al['paths']], lo and lo['n']))
        mc = page.evaluate(PATHS_OF, 'G11HSD12CQ101')
        sm = ' ／ '.join(x for p in (mc or {}).get('paths') or [] for x in p['sum'])
        ck('MCC 格（D1001 p.65 MCC/SWGR NO.: =G11BFB30_A1_A1E）：接線箱列是 G11BFB30_A1_A1E、盤面配置圖框出 A1E 格、格內 KKS 相同；沒有「NO.:」字頭',
           'G11BFB30_A1_A1E' in sm and '框出 A1E 格' in sm and 'NO.:' not in sm and any('mcc' in p['hops'] for p in mc['paths']), sm[:300])
        xj = page.evaluate(PATHS_OF, 'G12QJE11BW001')
        ck('G12 的設備接在 G11 的接線箱（G11QJE10UC151，D1003 p.810）：接線箱位置圖有框（jbloc）', bool(xj) and any('jbloc' in p['hops'] for p in xj['paths']),
           xj and [p['hops'] for p in xj['paths']])
        nl = page.evaluate(PATHS_OF, 'C10LCM10BL002')
        ck('盤側沒畫芯色標籤的一段（D1003 p.727 → CA017-1C4B 9／10）：照順序配到盤端子並以組態核對 ✓',
           bool(nl) and any('CA017-1C4B SHRA 9|' in x and x.endswith('|same') for p in nl['paths'] for x in p['t']), nl and [p['t'] for p in nl['paths']])
        # ---- 報告查核（第三輪）後補的：儀表架標高 'D nnn'、電纜表設備欄 'LCC' 之後的房間欄、PDF 版次較舊、MCC 排名不同
        rk = page.evaluate(PATHS_OF, 'C10LCM11BT001')
        sm = ' ／ '.join(x for p in (rk or {}).get('paths') or [] for x in p['sum'])
        ck('儀表架位置標籤的標高寫 D（位置圖 D0004 p.3 C10LCM11GZ001 \'E 4359570 N 4093841 D 2102\'）：座標帶標高、不多收鄰架的座標',
           'E 4359570 N 4093841 D 2102' in sm, sm[:300])
        lc = page.evaluate(PATHS_OF, 'G11MST10EW001')
        sm = ' ／ '.join(x for p in (lc or {}).get('paths') or [] for x in p['sum'])
        ck('電纜表設備欄 \'G11MST10 LCC\'（A1002 p.10）之後的房間欄仍是房間碼 101UBA20R001（不是 \'U1\'）', '101UBA20R001' in sm and 'G11MST10 LCC' in sm, sm[:300])
        xl = page.evaluate(PATHS_OF, 'G11EKT50BF001')
        ck('接線圖的電纜號不在電纜表 PDF（rev 0）、在較新的 xlsx（rev 1）：註記說 PDF 版次較舊（不是兩份文件不一致）',
           bool(xl) and any('C10PBH00UC151-WG-300' in n and '較新的電纜表 xlsx' in n for p in xl['paths'] for n in p['notes']),
           xl and [p['notes'][:2] for p in xl['paths']])
        mx = page.evaluate(PATHS_OF, 'C10LCC20GP001')
        ck('MCC 排名與幹線電纜號的排不同（D1003 p.577 C10BAC30_15_1 ↔ 電纜表 C10BCA30_6_1）：有註記',
           bool(mx) and any('C10BAC30_15_1' in n and 'C10BCA30_6_1' in n for p in mx['paths'] for n in p['notes']), mx and [p['notes'][:2] for p in mx['paths']])
        kp = page.evaluate(PATHS_OF, KKS_TAG)
        ck('KKS 編號卡 %s 也有 P&ID 位置與圖控畫面位置' % KKS_TAG, bool(kp) and kp['src'] == 'kks' and kp['pid'] >= 1 and kp['hmi'] >= 1, kp and (kp['src'], kp['pid'], kp['hmi']))
        # ---- AMS 設備卡：摘要的「接線路徑」組
        load_card(page, ctx, AMS_TAG)
        page.wait_for_selector('.sum-wire', timeout=30000)
        s = wait_wire(page, '.sum-wire')
        ck('AMS 設備卡 %s：摘要有「接線路徑」組——每一跳的表、每條芯、迴路圖（SVG）、接線圖影像' % AMS_TAG,
           bool(s) and s['paths'] >= 1 and s['sum'] >= 4 and s['cond'] >= 2 and s['loop'] >= 1 and s['svg'] >= 1 and s['sheets'] >= 1,
           s and {k: s[k] for k in ('paths', 'sum', 'cond', 'loop', 'svg', 'img', 'sheets')})
        ck('迴路圖的字有本台 KKS 與 H12 的盤', bool(s) and AMS_TAG in s['loopTxt'] and 'G12CCH02UC201' in s['loopTxt'], s and s['loopTxt'][:200])
        order = page.evaluate("() => [...document.querySelectorAll('.sum-groups > .sum-g')].map((g) => [...g.classList].find((c) => c.startsWith('sum-') && c !== 'sum-g'))")
        ck('「接線路徑」組排在全文檢索之前、圖控 HMI 之後', 'sum-wire' in order and 'sum-search' in order and order.index('sum-wire') < order.index('sum-search')
           and ('sum-hmi' not in order or order.index('sum-hmi') < order.index('sum-wire')), order)
        # ---- v18：迴路圖放大檢視（桌機：按鈕開、Esc 關、焦點回到按鈕）
        page.click('.sum-wire .loop-zoom-btn')
        page.wait_for_selector('.loop-lb svg.loop-svg', timeout=5000)
        lb = page.evaluate(LOOP_LB)
        ck('迴路圖「⤢ 放大檢視」開燈箱：裡面是這張 SVG、有縮放比例', bool(lb) and lb['svg'] == 1 and lb['w'] > 0 and lb['z'].endswith('%') and lb['open'], lb)
        page.keyboard.press('Escape')
        page.wait_for_timeout(400)
        ck('Esc 關掉迴路圖燈箱、焦點回到放大鈕',
           page.evaluate("() => !document.querySelector('.loop-lb') && !document.body.classList.contains('modal-open') && !!document.activeElement && document.activeElement.classList.contains('loop-zoom-btn')"))
        # ---- v18：字不截斷、訊號說明（使用者 2026-10-31 的例子 G11LAE12QN001：Mark VIe 變數原本截成 di_HpStmTermAttTempCvOpe…）
        for q in ('G11LAE12QN001', 'G11LAB65QM021'):
            page.goto(ctx['base'] + '/db/#/card/' + q)
            page.wait_for_selector('.sum-wire', timeout=30000)
            wait_wire(page, '.sum-wire')
            lt = page.evaluate(LOOP_TXT)
            if q == 'G11LAE12QN001':
                ck('G11LAE12QN001 迴路圖：Mark VIe 列的變數名完整（di_HpStmTermAttTempCvOpen、沒有 …）、底下藍字是組態說明與訊號 KKS',
                   'Pos23 | Contact23 | di_HpStmTermAttTempCvOpen' in lt['rows'] and not any(x.endswith('…') for x in lt['rows'])
                   and 'HP Terminal Attemperator Control Valve Open（G11LAE12QN001XG01）' in lt['desc'], (lt['rows'][:4], lt['desc'][:4]))
            else:
                ck('G11LAB65QM021 迴路圖：長變數 di_LpEconRecircFullEconOutIsoVlv_AltClosed 完整、Mark VIe 欄放寬（圖寬 > 1120）；接線圖說明超過 160 字的部分也在',
                   any(x.endswith('di_LpEconRecircFullEconOutIsoVlv_AltClosed') for x in lt['rows']) and max(lt['w'] or [0]) > 1120
                   and '=G11LAB65QM021XB62' in lt['txt'], (lt['rows'][:3], lt['w']))
                page.click('.sum-wire .loop-zoom-btn')
                page.wait_for_selector('.loop-lb svg.loop-svg', timeout=5000)
                page.wait_for_timeout(300)
                td = page.evaluate(TAP_DESC2)
                ck('燈箱點藍字說明的第二行：說明列是整段（螺絲 | 通道 | 變數＋說明＋訊號 KKS），同一段的每一行都標色，圖區高度不變（說明列固定高）',
                   bool(td) and ' | ' in td['pick'] and 'LpEconRecirc' in td['pick'] and '（G11LAB65QM021X' in td['pick'] and td['line'] in td['pick']
                   and td['hl'] >= 2 and td['h0'] == td['h1'], td)
                page.keyboard.press('Escape')
                page.wait_for_timeout(300)
        page.goto(ctx['base'] + '/db/#/card/G11MSA30GH001')
        page.wait_for_selector('.sum-wire', timeout=30000)
        wait_wire(page, '.sum-wire')
        lt = page.evaluate(LOOP_TXT)
        ck('G11MSA30GH001：同一條路徑跨 2A4B、2A5A 兩片卡、通道都叫 Contact02——Mark VIe 列照板位對變數（2A5A 那一列是 AXG52、2A4B 那一列是 AXG01），框頂列出 PDIA-57、PDIA-58',
           'Pos02 | Contact02 | G11MSA30GH001AXG52' in lt['rows'] and 'Pos02 | Contact02 | G11MSA30GH001AXG01' in lt['rows'] and 'PDIA-57' in lt['txt'] and 'PDIA-58' in lt['txt'],
           (lt['rows'][:4], lt['txt'][:200]))
        page.goto(ctx['base'] + '/db/#/card/96AT-TC-1A')
        page.wait_for_selector('svg.loop-svg', state='attached', timeout=60000)   # AMS 有這台（GE 元件的 AMS 設備卡帶 GE 路徑）或 GE 編號卡，哪一種都行
        page.wait_for_timeout(500)
        lt = page.evaluate(LOOP_TXT)
        ck('FF 元件 96AT-TC-1A：Mark VIe 框頂的段變數底下有藍字組態說明', len(lt['desc']) >= 1 and 'FF_IN_S23' in lt['txt'], (lt['desc'][:3], lt['txt'][:200]))
        # 沒有接線路徑的 AMS 設備（JK 開頭的 HART 多工器模組）：不出這一組
        jk = page.evaluate("() => { const rows = AMS.index.sheet.rows; for (const r of rows) { const k = String(r[AMS.index.kc]); if (/^JK/.test(k)) return k; } return ''; }")
        if jk:
            load_card(page, ctx, jk)
            page.wait_for_timeout(2500)
            ck('沒有接線路徑的 AMS 設備（%s）不出「接線路徑」組' % jk, page.evaluate("() => !document.querySelector('.sum-wire')"))
        # ---- KKS 編號卡：設備 KKS、訊號 KKS、小寫
        for label, q in (('device', KKS_TAG), ('signal', KKS_TAG + 'XB61'), ('lower', KKS_TAG.lower())):
            page.goto(ctx['base'] + '/db/#/card/' + q)
            page.wait_for_selector('.kks-only', timeout=30000)
            k = wait_wire(page, '.kks-only .sum-wire')
            st = page.evaluate("() => document.querySelector('.cq-status').textContent")
            ck('KKS 編號卡（%s：%s）：標頭是 %s、有接線路徑與迴路圖，狀態列說明 AMS 沒有這個設備' % (label, q, KKS_TAG),
               bool(k) and page.evaluate("() => document.querySelector('.kks-only .sum-tagtext').textContent") == KKS_TAG and k['paths'] >= 1 and k['svg'] >= 1
               and 'AMS 資料庫沒有' in st and (label != 'signal' or '訊號 KKS' in st), (k and {x: k[x] for x in ('paths', 'svg', 'sum', 'cond')}, st[:120]))
        shot(page, ctx, 'kks_card')
        # ---- 頂列 Enter
        page.goto(ctx['base'] + '/db/#/card/')
        page.wait_for_selector('#global-search', timeout=30000)
        page.fill('#global-search', KKS_TAG)
        page.press('#global-search', 'Enter')
        page.wait_for_selector('.kks-only', timeout=30000)
        ck('頂列搜尋 Enter %s → KKS 編號卡（網址不改寫成 AMS 的模糊對應）' % KKS_TAG, KKS_TAG in page.url, page.url)
        # ---- 打一半的 KKS：查無頁列 KKS 候選
        page.goto(ctx['base'] + '/db/#/card/' + KKS_TAG[:-2])
        page.wait_for_timeout(2500)
        ck('打一半（%s）：查無頁列「接線圖上的 KKS」候選' % KKS_TAG[:-2],
           page.evaluate("(t) => [...document.querySelectorAll('.nf-kks a')].some((a) => a.textContent.includes(t))", KKS_TAG), page.evaluate("() => (document.querySelector('.nf') || {}).textContent || ''")[:200])
        ck('console 零錯誤', not errors and not [m for m in console if m[0] == 'error'], (errors, console[:3]))
    with browser(ctx, mobile=True) as (page, errors, _console):
        login(page, ctx)
        page.goto(ctx['base'] + '/db/#/card/' + KKS_TAG)
        page.wait_for_selector('.kks-only', timeout=30000)
        wait_wire(page, '.kks-only .sum-wire')
        sw = page.evaluate('() => [document.documentElement.scrollWidth, window.innerWidth]')
        ck('手機寬度：KKS 編號卡不橫向捲動', sw[0] <= sw[1] + 1, sw)
        # ---- v18：手機的迴路圖燈箱——點字看全文（說明列固定高）、開啟就看得到字、兩指放大定點不動、✕ 關
        page.click('.kks-only .sum-wire .loop-zoom-btn')
        page.wait_for_selector('.loop-lb svg.loop-svg', timeout=5000)
        page.wait_for_timeout(200)
        a0 = page.evaluate(LOOP_LB)
        tt = page.evaluate(TAP_TEXT)   # 開啟倍率下點一段字（放大後畫面可能只剩電線）
        page.wait_for_timeout(200)
        a2 = page.evaluate(LOOP_LB)
        ck('手機：點一下圖上的字，說明列顯示那段字的全文，圖區高度不變', bool(tt) and bool(a2) and a2['pick'] == tt.strip() and a2['vh'] == a0['vh'],
           (tt[:80], a2 and a2['pick'][:80], a0 and a0['vh'], a2 and a2['vh']))
        page.wait_for_timeout(400)
        pz = page.evaluate(PINCH)
        page.wait_for_timeout(300)
        a1 = page.evaluate(LOOP_LB)
        ck('手機直拿：迴路圖燈箱開啟就看得到字（高度塞滿、倍率 ≥ 50%，不是 31% 的全圖），兩指拉開放大（舞台變寬 1.8 倍以上），手指底下那一點不動',
           bool(a0) and bool(a1) and int(a0['z'].rstrip('%') or 0) >= 50 and a1['w'] > a0['w'] * 1.8 and bool(pz) and abs(pz['a1'] - pz['a0']) < 0.02, (a0, a1, pz))
        page.click('.loop-lb .modal-x')
        page.wait_for_timeout(300)
        ck('手機：✕ 關掉迴路圖燈箱', page.evaluate("() => !document.querySelector('.loop-lb')"))
        ck('手機：沒有 JS 錯誤', not errors, errors)
    return ck.fails
