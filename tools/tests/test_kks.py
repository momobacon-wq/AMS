# -*- coding: utf-8 -*-
"""接線路徑的 KKS 版（v17，CONTRACT.md「v17」）：GE 編號卡的接線路徑、迴路圖比照到「沒有 GE 編號、只有 KKS」的元件。
資料：card/index.json 的 wire（AMS 設備卡的接線路徑塊 card/wire-NN.json，與 aux 分塊同一個編號）與 kkstag（KKS 編號卡 card/kkstag.json＋kkstag-loc-NN.json）。
AMS 設備卡：G12HAP70BT001（HRSG 給水的傳送器，BOP 接線圖 D1003）摘要多「接線路徑」組——接線圖、電纜表、控制盤 G12CCH02UC201（H12 RIO），
盤端子 CA007-1A5B 29／30 以 H12 的組態核對（SHRA，✓）；迴路圖一張、編號 LP-G12HAP70BT001。沒有接線路徑的 AMS 設備不出這一組。
KKS 編號卡：AMS 沒有的 G11LAE12QM004（HP 末級減溫隔離閥，D1003 p.301 直拉到 H11 RIO）打設備 KKS、訊號 KKS（…XB61）、小寫都開得到；
頂列 Enter 也開到它；打一半的 KKS 在查無頁列出 KKS 候選；本身是 GE 元件的 AMS 設備，接線路徑塊帶 GE 編號卡的路徑與連到 GE 卡的說明；手機寬度不橫向捲動；console 零錯誤。
v18 迴路圖：「⤢ 放大檢視」開燈箱（Esc 關、焦點回按鈕；點藍字第二行，說明列是整段「變數＋說明」、同一段一起標色、圖區高度不變；
手機開啟就看得到字、兩指放大定點不動、點字看全文、✕ 關）；G11LAE12QN001 的 Mark VIe 變數名不截、底下有藍字的組態說明與訊號 KKS；
v19：G11LAE12QN001 兩條路徑併成一張迴路圖（5 個訊號都在同一張、兩段段頭、預設展開）、頂端「端子表 5 個訊號，迴路圖畫出 5 個」；G11HBK11QM011 有路徑但缺點：列出缺的訊號與原因；
沒有路徑的 AMS 設備（1-LI-CW101-1）也出這一組；解析更正：G11LAE12QM402 的 XB61、G11HBK11UC102 的 47／48、新增的 C10BBT10EW001 p.144、G11HBK11UC101；
氣動閥清單先接走的 G11MAN30QN001（設備與訊號 KKS 都開閥卡）下面接接線路徑；GE 卡 S10MAX31GP003 有路徑、不寫查無；只在端子表上的元件（1-CSC-CW011-1、訊號 1-LI-CW091-1AXQ01）開只有端子表比對的卡；
帶字母尾碼的訊號（G11MSA30GH001A…）併回設備計數。
G11LAB65QM021 的長變數把 Mark VIe 欄放寬、接線圖說明不截在 160 字；G11MSA30GH001 跨兩片卡、同名通道照板位對變數；FF 元件 96AT-TC-1A 也有藍字說明。
v20：BOP 震動監測盤（Bently 3500）那一跳——CEP 感測器 C10LCC10BS001 寫 RACK 3 SLOT 13 CH1 與同通道的繼電器／記錄器、繼電器 C10LCC10BS101 寫 Relay Logic 與來源感測器、
迴路圖把繼電器畫在盤框裡；FWP 的機架叫 Rack13；SWP 兩台共用的 SLOT 15；端子排名漏印的芯照同組補上並註記；空壓機的繼電器有註記；CWP 傳送器的其他編號查得到。
v21：Bently 3500 通道圖——C10LCC10BS001 的卡上一張圖畫完感測器 → 盤內 3500（監測器、組態表那一列、繼電器模組與 Relay Logic、記錄器 4–20 mA）
→ 繼電器接點 → WSC1 PDIA-42、4–20 mA → WSC1 PHRA-78（四段、預設展開，本卡那一段標「本卡」，單條迴路圖收合）；繼電器、記錄器的卡是同一張圖；
FWP 推力（BG009）寫 Alert L／H、Danger LL／HH 與 ZPV；SWP BS009 補上的 TB1 104 也在盤內段；空壓機與 GE 卡沒有這張圖；摘要多「3500 組態」列與組態表那一跳（vcfg）。
v22：FWP 泵廠文件——打泵廠位號（C10LAC50CZ001、C10LAC60CS021A、C10LAC70BG005A）開到接線圖那張卡、狀態列說是另一個編號；摘要多「泵廠儀表清單」列；
①那一段把前置器畫在接線箱裡（探頭經同軸／延長線）；盤內段印探頭與前置器；推力卡的註記寫三份設定值不同與 CZ001。"""
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
      hops: p.rows.filter((x) => x[4] && x[4].marks).map((x) => x[4].hop), t: p.t.map((x) => x.slice(0, 6).join('|')),
      pos: p.rows.filter((x) => x[0] === '所在位置').map((x) => x[1]) })) }; }"""

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


LOOP_ALL = """() => { const d = [...document.querySelectorAll('details.wire-loop')]; const s = d[0] && d[0].querySelector('.loop-fig > svg');
  return { n: d.length, open: d[0] ? d[0].open : false, sum: d[0] ? d[0].querySelector('summary').textContent : '', svg: document.querySelectorAll('.loop-fig > svg').length, inner: s ? s.querySelectorAll('svg').length : 0,
    heads: s ? [...s.querySelectorAll('text.lp-secth')].map((t) => t.textContent) : [], txt: s ? [...s.querySelectorAll('text')].map((t) => t.textContent).join(' ') : '',
    cov: (document.querySelector('.wire-cov-h') || {}).textContent || '', gaps: [...document.querySelectorAll('.wire-gap tbody tr')].map((r) => r.textContent) }; }"""


CHAIN = """() => { const d = document.querySelector('details.wire-chain'); if (!d) return null; const s = d.querySelector('.loop-fig > svg');
  const tx = s ? [...s.querySelectorAll('text')] : []; const inn = s ? [...s.querySelectorAll(':scope > svg')] : [];
  const tt = (el) => (el ? [...el.querySelectorAll('text')].map((t) => t.getAttribute('data-full') || t.textContent).join(' ') : '');
  return { open: d.open, sum: d.querySelector('summary').textContent, inner: s ? s.querySelectorAll('svg').length : 0,
    heads: s ? [...s.querySelectorAll('text.lp-secth')].map((t) => t.getAttribute('data-full') || t.textContent) : [],
    txt: tx.map((t) => t.getAttribute('data-full') || t.textContent).join(' '), br: tt(inn[1]), loopOpen: [...document.querySelectorAll('details.wire-loop')].map((x) => x.open) }; }"""


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
        # ---- v19：一台一張迴路圖（使用者 2026-10-31 的例子：卡上 5 個訊號，第一張圖只畫 3 個，XQ23、XQ02 在收合的第二張）；端子表逐點對接線路徑
        page.goto(ctx['base'] + '/db/#/card/G11LAE12QN001')
        page.wait_for_selector('.sum-wire', timeout=30000)
        wait_wire(page, '.sum-wire')
        la = page.evaluate(LOOP_ALL)
        ck('G11LAE12QN001：兩條路徑併成一張迴路圖（一個 details、預設展開、兩個內層 svg、兩段段頭），5 個訊號都在同一張',
           la['n'] == 1 and la['open'] and la['svg'] == 1 and la['inner'] == 2 and len(la['heads']) == 2
           and all('G11LAE12QN001' + x in la['txt'] for x in ('XG01', 'XG02', 'XB62', 'XQ23', 'XQ02')), {k: la[k] for k in ('n', 'open', 'svg', 'inner', 'heads', 'sum')})
        ck('G11LAE12QN001：接線路徑最上面寫「端子表 5 個訊號，迴路圖畫出 5 個」', la['cov'].startswith('端子表 5 個訊號，迴路圖畫出 5 個') and not la['gaps'], la['cov'])
        page.click('.sum-wire .loop-zoom-btn')
        page.wait_for_selector('.loop-lb svg.loop-svg', timeout=5000)
        page.wait_for_timeout(300)
        lb = page.evaluate(LOOP_LB)
        ck('併成一張的圖也能開燈箱：只有外層一張（內層不算）、有縮放比例', bool(lb) and lb['svg'] == 1 and lb['z'].endswith('%'), lb)
        page.keyboard.press('Escape')
        page.wait_for_timeout(300)
        page.goto(ctx['base'] + '/db/#/card/G11HBK11QM011')
        page.wait_for_selector('.wire-cov', timeout=30000)
        la = page.evaluate(LOOP_ALL)
        ck('G11HBK11QM011：端子表 7 個、接線圖少 2 個：逐列列出訊號與原因（XB87、XB20），不畫進迴路圖',
           '接線圖沒有畫' in la['cov'] and len(la['gaps']) == 2 and any('G11HBK11QM011XB87' in x for x in la['gaps']) and 'XB87' not in la['txt'], (la['cov'], la['gaps'][:2]))
        page.goto(ctx['base'] + '/db/#/card/1-LI-CW101-1')
        page.wait_for_selector('.wire-cov', timeout=30000)
        la = page.evaluate(LOOP_ALL)
        ck('1-LI-CW101-1（AMS 設備、接線圖沒有路徑）：接線路徑組還在，寫端子表的訊號與原因，沒有迴路圖', la['svg'] == 0 and len(la['gaps']) >= 1 and '接線圖沒有畫' in la['cov'], (la['cov'], la['gaps'][:1]))
        for q_ in ('G11MAN30QN001', 'G11MAN30QN001XQ23'):
            page.goto(ctx['base'] + '/db/#/card/' + q_)
            page.wait_for_selector('.kks-wire .wire-cov', timeout=30000)
            la = page.evaluate(LOOP_ALL)
            ck('%s：氣動閥清單先接走，閥卡下面仍有接線路徑與併成一張的迴路圖' % q_, page.evaluate("() => !!document.querySelector('.valve-only')") and la['svg'] == 1 and la['inner'] == 4 and la['cov'].startswith('端子表 7 個訊號'), (la['sum'], la['cov']))
        page.goto(ctx['base'] + '/db/#/card/S10MAX31GP003')
        page.wait_for_selector('.kks-wire svg.loop-svg', state='attached', timeout=30000)
        page.wait_for_timeout(1200)
        ck('S10MAX31GP003（GE 卡）：有接線路徑時不寫「查無」', '查無：一號機兩份儀控電纜接線圖' not in page.evaluate("() => document.body.textContent"))
        for q_ in ('1-CSC-CW011-1', '1-LI-CW091-1AXQ01'):
            page.goto(ctx['base'] + '/db/#/card/' + q_)
            page.wait_for_selector('.kks-only .wire-cov', timeout=30000)
            la = page.evaluate(LOOP_ALL)
            ck('%s（只在端子表上、位號不是 KKS）：開卡，列訊號與原因，沒有 P&ID、圖控「查無」' % q_, la['svg'] == 0 and len(la['gaps']) >= 1 and page.evaluate("() => !document.querySelector('.sum-pid') && !document.querySelector('.sum-hmi')"), (la['cov'], la['gaps'][:1]))
        page.goto(ctx['base'] + '/db/#/card/G11MSA30GH001')
        page.wait_for_selector('.wire-cov', timeout=30000)
        la = page.evaluate(LOOP_ALL)
        ck('G11MSA30GH001：端子表帶字母尾碼的訊號（…001A、B、C）併回設備計數', la['cov'].startswith('端子表 7 個訊號，迴路圖畫出 7 個'), la['cov'])
        fix = page.evaluate("""async () => { const K = await AMS.kkstag.load(); const E = K ? K.j.entries : []; const of = async (t) => { const i = E.findIndex((e) => e.t === t); return i >= 0 ? (await AMS.kkstag.loadLoc(i)).lo : null; };
          const a = await of('G11HBK11UC102'); const b = await of('G11LAE12QM402'); const c = await of('C10LCC10BS004'); const d = await of('G11HBK11UC101');
          return { a: a ? a.wp.t.map((r) => r[3]) : null, b: b ? [b.wp].concat(b.wpx || []).flatMap((w) => w.d.sl || []) : null, c: !!(c && c.wp), d: !!(d && d.wp) }; }""")
        ck('解析更正：G11HBK11UC102 第二組芯在 47／48（D1003 p.635 原本錯一列）；G11LAE12QM402 有 XB61（p.297 訊號 KKS 斷兩行）；C10LCC10BS004、G11HBK11UC101 有路徑',
           bool(fix['a']) and any('47' in str(x) for x in fix['a']) and any('48' in str(x) for x in fix['a']) and bool(fix['b']) and 'G11LAE12QM402XB61' in fix['b'] and fix['c'] and fix['d'], fix)
        page.goto(ctx['base'] + '/db/#/card/G11MSA30GH001')
        page.wait_for_selector('.sum-wire', timeout=30000)
        wait_wire(page, '.sum-wire')
        lt = page.evaluate(LOOP_TXT)
        ck('G11MSA30GH001：同一條路徑跨 2A4B、2A5A 兩片卡、通道都叫 Contact02——Mark VIe 列照板位對變數（2A5A 那一列是 AXG52、2A4B 那一列是 AXG01），框頂列出 PDIA-57、PDIA-58',
           'Pos02 | Contact02 | G11MSA30GH001AXG52' in lt['rows'] and 'Pos02 | Contact02 | G11MSA30GH001AXG01' in lt['rows'] and 'PDIA-57' in lt['txt'] and 'PDIA-58' in lt['txt'],
           (lt['rows'][:4], lt['txt'][:200]))
        # ---- v20：BOP 震動監測盤（Bently 3500）：感測器 → 3500 → 繼電器／記錄器 → 控制盤，三種卡互相列出
        def summ(t):
            o = page.evaluate(PATHS_OF, t) or {}
            return ' ／ '.join(x for p in o.get('paths') or [] for x in p['sum'] + ['所在位置：' + y for y in p.get('pos') or []]), [h for p in o.get('paths') or [] for h in p['hops']], [n for p in o.get('paths') or [] for n in p['notes']]
        sm, hp, _n = summ('C10LCC10BS001')
        ck('CEP 感測器 C10LCC10BS001：Bently 3500 列 RACK 3 SLOT 13 CH1、3500/42M、TB1 13＝PWR、組態叫 Rack15；「3500 輸出」列繼電器 C10LCC10BS101（S13C01P01A2）與記錄器 C10LCC10BS201；圖紙有 3500 盤端子與機架槽位',
           'Bently 3500：RACK 3 SLOT 13 CH1：3500/42M-09-00（監測器）' in sm and 'TB1 13＝PWR、14＝COM、15＝SIG' in sm and 'Rack15' in sm and '繼電器 C10LCC10BS101' in sm
           and 'S13C01P01A2' in sm and '記錄器 4–20 mA C10LCC10BS201' in sm and '接到 Bently 3500 監測盤' in sm and 'vmsb' in hp and 'rack' in hp
           and '所在位置：① 這幾條芯旁的標籤（R機架-S槽-CH通道-功能／端子排-端子）' in sm and '1TBVIB' not in sm, (sm[-700:], hp))
        sm, hp, _n = summ('C10LCC10BS021')
        ck('CEP 鍵相 C10LCC10BS021（只有記錄器輸出、沒有繼電器）：Mark VIe 列只寫 4–20 mA 記錄器輸出', '3500 再用4–20 mA 記錄器輸出送控制器' in sm and '繼電器接點與' not in sm, sm[-400:])
        sm, hp, _n = summ('C10LCC10BS101')
        ck('CEP 繼電器 C10LCC10BS101：「盤內 3500」取代「元件畫在端子排旁」、2TBRLY 1＝ARM／2＝NO；「3500 來源」寫 S13C01P01A2 與感測器 C10LCC10BS001（Alarm 2＝Danger 引 User Guide、簽名 Relay Logic Report 的 Alarm Status HH）；圖紙多 3500 組態（vlog）',
           '盤內 3500：C10LCC10BS101 是 VMS 盤 C10CCD01UC202 裡 Bently 3500/33-01-00（繼電器模組）的繼電器接點' in sm and '2TBRLY 1＝ARM、2＝NO' in sm
           and 'S13C01P01A2' in sm and 'SLOT 13 CH1 接的感測器是 C10LCC10BS001' in sm and 'Alarm 2＝Danger' in sm and 'Alarm Status 是「HH」' in sm and '的端子排旁' not in sm and 'vlog' in hp
           and '震動監測盤：C10CCD01UC202' in sm and '接線箱：' not in sm and '所在位置：① 組態表上這顆繼電器那一列（KKS 與 Relay Logic）' in sm, (sm[:700], hp))
        sm, hp, _n = summ('C10LCC10BS201')
        ck('CEP 記錄器 C10LCC10BS201：「3500 來源」是 SLOT 13 CH1 的記錄器輸出、感測器 C10LCC10BS001；TB3 9＝COM、10＝REC',
           '記錄器輸出（4–20 mA）' in sm and 'SLOT 13 CH1 接的感測器是 C10LCC10BS001' in sm and 'TB3 9＝COM、10＝REC' in sm, sm[-500:])
        sm, hp, _n = summ('C10LAC50BG101')
        ck('FWP 繼電器 C10LAC50BG101：FWP 盤 C10CCD01UC201、RACK 1 SLOT 4 CH1、S11C01P01A2 → 感測器 C10LAC50BG001、組態叫 Rack13',
           'C10CCD01UC201' in sm and 'RACK 1 SLOT 4 CH1' in sm and 'S11C01P01A2' in sm and 'C10LAC50BG001' in sm and 'Rack13' in sm, sm[-500:])
        sm, hp, nt = summ('C10PHC20BS009')
        ck('SWP 2 馬達 NDE Z（C10PHC20BS009）：兩台共用的 3500/42M SLOT 15 CH3；接線圖漏印端子排名的 TB1 104＝COM 照同組補上、有註記',
           'RACK 4 SLOT 15 CH3' in sm and '104＝COM' in sm and 'TB12' not in sm.split('Bently 3500')[0] and any('印成「TB12 104」' in n for n in nt), (sm[-400:], nt[:2]))
        _s, _h, nt = summ('C10LAC50BG109')
        _s2, _h2, nt2 = summ('C10PHC10BS003')
        ck('註記：FWP 推力繼電器 C10LAC50BG109 的 Alarm Status 是 LL or HH or Not OK、繼電器常態 NE；SWP C10PHC10BS003 的方位說明兩份文件不同',
           any('LL or HH or Not OK' in n for n in nt) and any('NE（平常激磁）' in n for n in nt) and any('說明兩份文件不同' in n and 'VIB PMP DE X-AXIS' in n for n in nt2), (nt[:3], nt2[:2]))
        _s, _h, nt = summ('C00QEA11BS611')
        ck('空壓機繼電器 C00QEA11BS611：註記寫在空壓機馬達震動監測盤 C00CCD01UC201（RACK 5／Rack17）、接線圖盤號寫錯；也真的沒畫 3500 那一跳（不會誤接到 FWP 盤的通道）',
           any('C00CCD01UC201' in n and 'Rack17' in n and '不畫 3500' in n for n in nt) and not {'vmsb', 'rack', 'vlog'} & set(_h)
           and 'Bently 3500：' not in _s and '3500 來源' not in _s, (nt[:1], _h))
        page.goto(ctx['base'] + '/db/#/card/C10LCC10BS101')
        page.wait_for_selector('.kks-only .sum-wire', timeout=30000)
        wait_wire(page, '.kks-only .sum-wire')
        # v21：卡上另有 3500 通道圖（裡面的感測器那一段本來就寫「畫在端子排旁」）：這一項只看這張卡自己的迴路圖
        lt = {'txt': page.evaluate("() => [...document.querySelectorAll('details.wire-loop svg.loop-svg text')].map((t) => t.textContent).join(' ')")}
        tx = lt['txt'].replace(' ', '')
        ck('C10LCC10BS101 迴路圖：繼電器畫在 VMS 盤框裡（「是 Bently 3500/33 … 的接點」、RACK 3 SLOT 4 CH1、來源 C10LCC10BS001），不寫「元件畫在端子排旁」',
           'C10LCC10BS101是Bently3500/33-01-00（繼電器模組）的繼電器接點' in tx and 'RACK3SLOT4CH1' in tx and '這個通道的感測器是C10LCC10BS001' in tx and '畫在端子排旁' not in tx
           and '震動監測盤VMSPANEL' in tx, lt['txt'][:400])
        page.goto(ctx['base'] + '/db/#/card/C10LCC10BS001')
        page.wait_for_selector('.kks-only .sum-wire', timeout=30000)
        wait_wire(page, '.kks-only .sum-wire')
        lt = {'txt': page.evaluate("() => [...document.querySelectorAll('details.wire-loop svg.loop-svg text')].map((t) => t.textContent).join(' ')")}   # v21：只看這張卡自己的迴路圖
        ck('C10LCC10BS001 迴路圖：Mark VIe 欄寫接到 3500 監測盤與 RACK 3 SLOT 13 CH1', 'Bently3500RACK3SLOT13CH1' in lt['txt'].replace(' ', ''), lt['txt'][-400:])
        # ---- v21：Bently 3500 通道圖（感測器 → 盤內 3500 → 繼電器接點／4–20 mA → Mark VIe）
        ch = page.evaluate(CHAIN) or {}
        tx = (ch.get('txt') or '').replace(' ', '').replace('\u3000', '')
        br = (ch.get('br') or '').replace(' ', '').replace('\u3000', '')   # 只看第 2 段（盤內段）：其他段也有 p.32、TB3 10 之類的字
        hd = ch.get('heads') or []
        ck('C10LCC10BS001 通道圖：預設展開、四段（感測器、盤內 3500、繼電器、記錄器），段頭依序 ①～④、本卡是第 1 段；這張卡的單條迴路圖收合',
           ch.get('open') and ch.get('inner') == 4 and len(hd) == 4 and hd[0].startswith('① 感測器 C10LCC10BS001') and '（本卡）' in hd[0]
           and hd[1].startswith('② 震動監測盤內 Bently 3500：RACK 3 SLOT 13 CH1') and hd[2].startswith('③ 繼電器接點 C10LCC10BS101') and hd[3].startswith('④ 4–20 mA 記錄器輸出 C10LCC10BS201')
           and '本卡是第 1 段' in ch.get('sum', '') and ch.get('loopOpen') == [False], (hd, ch.get('sum'), ch.get('loopOpen')))
        ck('C10LCC10BS001 盤內段：3500/42M SLOT 13 CH1 與組態表那一列（Acceleration 2、330400、0～25.4 mm/s pk、Alert H 4.5、Danger HH 7.1、閂鎖、延時 30 秒）、出處打字 p.32 與簽名 p.510',
           'SLOT13CH1監測器' in br and '3500/42M-09-00' in br and 'p.510（簽名Rev-' in br and 'Alert30、Danger30.00（秒）' in br and 'Acceleration2' in tx and '330400StdIntegralAcceleration' in tx and '量程：0～25.4mm/spk' in tx
           and 'Alert：H4.5mm/spk' in tx and 'Danger：HH7.1mm/spk' in tx and 'Alert閂鎖' in tx and 'NotOK不閂鎖' in tx and 'Alert30、Danger30.00' in tx and 'p.32' in tx, tx[:600])
        ck('C10LCC10BS001 盤內段：繼電器模組 SLOT 4 CH1（Relay Logic S13C01P01A2、簽名報告 Alarm Status HH、NE／Closed）→ 2TBRLY 1／2 → WSC1 PDIA-42 Contact24（平常＝1）；記錄器（照滿量程比例，引 User Guide）→ TB3 10／9 → WSC1 PHRA-78 AnalogInput05（0～25.4 mm/s，與 3500 量程相同 ✓）',
           'SLOT4CH1繼電器模組' in br and 'RelayLogicS13C01P01A2' in br and 'AlarmStatusHH（p.511）' in br and '常態NE（常激磁）、接點Closed' in br and '2TBRLY1' in br and '2TBRLY2' in br
           and 'WSC1PDIA-42Contact24：C10LCC10BS101XG03' in br and '平常＝1、動作＝0' in br and 'TB310' in br and 'TB39' in br and '（照滿量程比例）' in br and 'HT1-1-AQB01-Q1851' in br
           and 'WSC1PHRA-78AnalogInput05：C10LCC10BS201XQ01' in br and '與3500量程相同✓' in br and '130432-01' in br and '【推論】' in br, br[-900:])
        for t_, n_ in (('C10LCC10BS101', 3), ('C10LCC10BS201', 4)):
            page.goto(ctx['base'] + '/db/#/card/' + t_)
            page.wait_for_selector('.kks-only .sum-wire', timeout=30000)
            wait_wire(page, '.kks-only .sum-wire')
            c2 = page.evaluate(CHAIN) or {}
            h2 = c2.get('heads') or []
            ck('%s：同一張通道圖（四段、本卡是第 %d 段、段頭標「本卡」）' % (t_, n_), c2.get('inner') == 4 and len(h2) == 4 and '（本卡）' in h2[n_ - 1] and ('本卡是第 %d 段' % n_) in c2.get('sum', '')
               and sum('（本卡）' in h for h in h2) == 1, (h2, c2.get('sum')))
        sm, hp, _n = summ('C10LCC10BS001')
        ck('C10LCC10BS001 摘要：「3500 組態」列（Alert H 4.5、Danger HH 7.1、Rack15 SLOT 13 CH1、打字版 Rev B 與簽名的出廠版逐列相同、延時是秒）、圖紙多組態表那一跳（vcfg）',
           '3500 組態：' in sm and 'Alert H 4.5、Danger HH 7.1（mm/s pk）' in sm and 'Rack15 SLOT 13 CH1' in sm and 'Rev B' in sm and '簽名的出廠版 Rev -（第 510 頁' in sm
           and '數值相同' in sm and 'Alert 30、Danger 30.00（秒' in sm and 'vcfg' in hp, sm[-700:])
        page.goto(ctx['base'] + '/db/#/card/C10LAC50BG009')
        page.wait_for_selector('.sum-wire', timeout=30000)
        wait_wire(page, '.sum-wire')
        c3 = page.evaluate(CHAIN) or {}
        t3 = (c3.get('txt') or '').replace(' ', '')
        ck('FWP 推力 C10LAC50BG009 通道圖：Thrust Position、Alert L -0.30／H 0.60、Danger LL -0.60／HH 0.80（mm）、ZPV、正方向 Toward Probe；推力繼電器 BG109 的箭頭寫 LL／HH＋Not OK、註記兩版不同',
           'ThrustPosition' in t3 and 'Alert：L-0.30、H0.60mm' in t3 and 'Danger：LL-0.60、HH0.80mm' in t3 and 'ZPV' in t3 and '正方向：TowardProbe' in t3
           and 'LL／HH' in t3 and '＋NotOK' in t3 and '簽名報告多了LL與NotOK' in t3, t3[:700])
        for t_, want, why in (('C10LAC50BG001', ('≠3500滿量程0～150µmpp⚠', '實際的2倍'), 'FWP 泵端徑向 C10LAC50BG001：Mark VIe 4–20 mA 量程 0～300 µm 與 3500 滿量程 0～150 µm pp 不同，標紅、註記 2 倍，段頭有 ⚠'),
                              ('C10LAC50BS021', ('H3500rpm（簽名的出廠版劃掉', 'NOSETPOINTSFORTACHOMETER', '照量程比例【推論】'), 'FWP 轉速 C10LAC50BS021：打字版的 Alert H 3500 等三格標紅、註記簽名版劃掉（NO SETPOINTS FOR TACHOMETER）；3500/50 的記錄器量程標推論'),
                              ('C10LCC10BS021', ('警報值：組態表沒有設定值', '照量程比例【推論】'), 'CEP 鍵相轉速 C10LCC10BS021：沒有警報值的通道寫「沒有設定值」')):
            page.goto(ctx['base'] + '/db/#/card/' + t_)
            page.wait_for_selector('.sum-wire', timeout=30000)
            wait_wire(page, '.sum-wire')
            c5 = page.evaluate(CHAIN) or {}
            t5 = (c5.get('txt') or '').replace(' ', '').replace('\u3000', '')
            ok5 = all(w in t5 for w in want)
            if t_ == 'C10LAC50BG001':
                ok5 = ok5 and '⚠' in ((c5.get('heads') or ['', ''])[1]) and '⚠' in c5.get('sum', '')
            if t_ == 'C10LCC10BS021':   # 鍵相轉速：只有記錄器輸出，三段（感測器、盤內、記錄器）；沒有警報值就不列閂鎖
                b5 = (c5.get('br') or '').replace(' ', '').replace('\u3000', '')
                ok5 = ok5 and c5.get('inner') == 3 and '閂鎖：' not in b5 and '③4–20mA記錄器輸出C10LCC10BS221' in ''.join(c5.get('heads') or []).replace(' ', '')
            ck(why, ok5, ([w for w in want if w not in t5], t5[:500]))
        page.goto(ctx['base'] + '/db/#/card/C10PHC20BS009')
        page.wait_for_selector('.sum-wire', timeout=30000)
        wait_wire(page, '.sum-wire')
        c4 = page.evaluate(CHAIN) or {}
        ck('SWP C10PHC20BS009 通道圖：盤內段的感測器進盤端子有照同組補上的 TB1 104', 'TB1104' in (c4.get('txt') or '').replace(' ', ''), (c4.get('txt') or '')[:400])
        page.goto(ctx['base'] + '/db/#/card/C00QEA11BS611')
        page.wait_for_selector('.kks-only .sum-wire', timeout=30000)
        wait_wire(page, '.kks-only .sum-wire')
        ck('空壓機 C00QEA11BS611：沒有 3500 通道圖（那一面盤沒有盤圖）', page.evaluate("() => !document.querySelector('details.wire-chain')"))
        page.goto(ctx['base'] + '/db/#/card/96AT-TC-1A')
        page.wait_for_selector('svg.loop-svg', state='attached', timeout=60000)
        page.wait_for_timeout(800)
        ck('GE 元件 96AT-TC-1A：沒有 3500 通道圖', page.evaluate("() => !document.querySelector('details.wire-chain')"))
        # ---- v22：FWP 泵廠文件（A1221 儀表清單、D1212 泵廠接線圖）
        for q_, dev, word in (('C10LAC50CZ001', 'C10LAC50BG009', '另一個編號'), ('C10LAC60CS021A', 'C10LAC60BS021', '這個通道的探頭'), ('c10lac70bg005a', 'C10LAC70BG005', '這個通道的探頭'),
                              ('C10LAC70CS021', 'C10LAC70BS021', '另一個編號'), ('C10LAC50BG009A', 'C10LAC50BG009', '這個通道的探頭')):
            page.goto(ctx['base'] + '/db/#/card/' + q_)
            page.wait_for_selector('.kks-only .sum-wire', timeout=30000)
            wait_wire(page, '.kks-only .sum-wire')
            st = page.evaluate("() => document.querySelector('.cq-status').textContent")
            ck('%s：開 %s 的卡，狀態列說「%s」（泵廠儀表清單的位號）' % (q_, dev, word),
               page.evaluate("() => document.querySelector('.kks-only .sum-tagtext').textContent") == dev and word in st and '泵廠' in st, st[:200])
        page.goto(ctx['base'] + '/db/#/card/C10LAC50CZ001XQ01')
        page.wait_for_timeout(2500)
        ck('泵廠位號加上自己編的訊號尾碼（C10LAC50CZ001XQ01）不開卡', page.evaluate("() => !document.querySelector('.kks-only')"))
        sm, hp, nt = summ('C10LAC50BG001')
        ck('C10LAC50BG001 摘要：「泵廠儀表清單」列（探頭 BG001A 與型號、經延長線 C10LAC-1-0007、前置器 330180-51-TW 在接線箱 UC102、0-150、H 72.3／HH 96.4 與 3500 的 72／96 並列）',
           '泵廠儀表清單：探頭 C10LAC50BG001A（Bently Nevada 21000-A28-B05-C15-D060-E04-F01' in sm and '經鎧裝延長線 C10LAC-1-0007' in sm and '330180-51-TW' in sm
           and 'C10LAC50UC102' in sm and 'H =72.3 μmpp / HH = 96.4 μmpp（3500 組態是 Alert H 72、Danger HH 96' in sm
           and '泵廠資料表 S1226 第 40 頁：位號 C10LAC50BG001A' in sm and '330130-045-01-TW，4.5 m' in sm, sm[:1200])
        ck('C10LAC50BG001 註記：接線箱裡的接法兩份圖不同（D1003 端子 7／8／9、泵廠圖客戶電纜直接接前置器）', any('接線箱 C10LAC50UC102 裡的接法兩份圖不同' in n and '7／8／9' in n for n in nt), nt[-2:])
        page.goto(ctx['base'] + '/db/#/card/C10LAC50BG001')
        page.wait_for_selector('.kks-only .sum-wire', timeout=30000)
        wait_wire(page, '.kks-only .sum-wire')
        own = page.evaluate("() => [...document.querySelectorAll('details.wire-loop svg.loop-svg text')].map((t) => t.getAttribute('data-full') || t.textContent).join(' ')").replace(' ', '')
        geo = page.evaluate("""() => { const s = document.querySelector('details.wire-loop svg.loop-svg'); if (!s) return null;
          const n = (q) => [...s.querySelectorAll(q)];
          const px = n('rect.lp-px').map((r) => +r.getAttribute('x')); const cx = n('line.lp-coax').map((l) => [+l.getAttribute('x1'), +l.getAttribute('x2')]);
          const bub = s.querySelector('circle.lp-bub'); const cap = n('text').find((t) => /^探頭 /.test(t.textContent));
          return { px, cx, bub: bub ? +bub.getAttribute('cx') : null, cap: cap ? cap.textContent : '', capx: cap ? +cap.getAttribute('x') : null }; }""") or {}
        c6 = page.evaluate(CHAIN) or {}
        b6 = (c6.get('br') or '').replace(' ', '')
        ck('C10LAC50BG001 ①迴路圖：接線箱框裡有前置器的灰底框（x 在接線箱區 250～500）、圓圈到前置器是一條同軸線、圓圈底下寫「探頭 C10LAC50BG001A」；前置器說明有型號與延長線；盤內段左欄印「感測器（泵廠儀表清單）」',
           any(190 <= x <= 300 for x in geo.get('px') or []) and any(a <= 100 and b >= 190 for a, b in geo.get('cx') or []) and geo.get('cap') == '探頭 C10LAC50BG001A'
           and 'C10LAC50BG001：BentlyNevada330180-51-TW' in own and '鎧裝延長線C10LAC-1-0007' in own and '感測器（泵廠儀表清單）' in b6 and '探頭C10LAC50BG001A' in b6, (geo, own[:300], b6[:200]))
        page.goto(ctx['base'] + '/db/#/card/C10LAC50BG009')
        page.wait_for_selector('.kks-only .sum-wire', timeout=30000)
        wait_wire(page, '.kks-only .sum-wire')
        b7 = ((page.evaluate(CHAIN) or {}).get('br') or '').replace(' ', '')
        ck('C10LAC50BG009 盤內段：同一片監測器（SLOT 15）還帶 FWP2 的推力 CH3 C10LAC60BG009', '同一片監測器還帶別台設備的通道：CH3C10LAC60BG009' in b7, b7[:600])
        page.goto(ctx['base'] + '/db/#/card/C10LAC50BG104')
        page.wait_for_selector('.kks-only .sum-wire', timeout=30000)
        wait_wire(page, '.kks-only .sum-wire')
        b8 = ((page.evaluate(CHAIN) or {}).get('br') or '').replace(' ', '')
        ck('C10LAC50BG104 盤內段：同一片 PDIA-22（Simplex）還接三台泵的其他 3500 輸出', '同一片PDIA-22（Simplex）還接' in b8 and 'C10LAC60' in b8 and 'C10LAC70' in b8, b8[-700:])
        _s, _h, nt = summ('C10LAC70BG009')
        ck('C10LAC70BG009 註記：推力設定值（泵廠與 Mark VIe 相同、3500 負方向較早，Variables.xml:18216～18223）與泵廠位號 CZ001',
           any('兩份相同' in n and '負方向較早' in n for n in nt) and any('C10LAC70CZ001' in n for n in nt), nt[-3:])
        _s, _h, nt = summ('C10LAC50BG201')
        ck('C10LAC50BG201 註記：Mark VIe 警報常數 H 72.3／HH 96.4（0～300 µm）對 3500 滿量程 150：實際的 2 倍、約 36.1／48.2 µm pp',
           any('H 72.3、HH 96.4' in n and '實際的 2 倍' in n and '36.1／48.2' in n for n in nt), nt[-2:])
        # ---- v20：CWP 馬達震動（只在端子表上）：傳送器位號、DCDAS I/O 表的編號、GE 的 RDS-PP 碼都開到 1-VI-CW011-n 那張卡
        for q_, dev in (('1-VT-CW011-1AE', '1-VI-CW011-1'), ('C10PAC12BS101', '1-VI-CW011-2'), ('1-vi-cw011-3ad', '1-VI-CW011-3'), ('C10PAC11BS101XQ01', '1-VI-CW011-1')):
            page.goto(ctx['base'] + '/db/#/card/' + q_)
            page.wait_for_selector('.kks-only .wire-cov', timeout=30000)
            st = page.evaluate("() => document.querySelector('.cq-status').textContent")
            cv = page.evaluate("() => document.querySelector('.wire-cov').textContent")
            ck('%s：開 %s 的卡（狀態列說是另一個編號）、卡上列其他編號與原因（電纜 =C10PAC…-VETB-WG-R601、端子箱 VE1～VE4）' % (q_, dev),
               page.evaluate("() => document.querySelector('.kks-only .sum-tagtext').textContent") == dev and '其他編號裡' in st and '其他編號：' in cv
               and 'VETB-WG-R601' in cv and 'VE1' in cv, (st[:160], cv[:300]))
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
