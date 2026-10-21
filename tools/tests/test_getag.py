# -*- coding: utf-8 -*-
"""GE 原廠編號（card aux 的 sec.getag＋04 位號索引的來源類型 8）：
搜尋（正式寫法 exact、不打連字號 compact、小寫加空白；頂列搜尋 Enter）開到那台設備；一個編號對到兩台時有切換按鈕；
設備組有「GE 原廠編號」一格（有值、有來源點），非 GE 設備沒有這格（hide_empty）；完整資料區有 GE 原廠編號段；
下拉建議打不帶連字號的前綴也列得出來；備品庫存的位號正規化不收 GE 列（tagSuggestSource 濾掉來源類型 8）；console 零錯誤。
測試用的 GE 編號一律從已發布的 04 挑，不寫死。
GE 編號卡（v8，card/getag.json）：AMS 沒有的 CT-DA-1 打 CTDA1／CTDA-1／小寫、帶機組（G12.CTDA1 只列 G12）、Mark VIe 訊號名、KKS 都開 GE 編號卡；
CTDA10 不中 CTDA1；燃機汽機同編號列兩塊；閥清單也有的編號開閥卡＋下面接 GE 對照；查無頁與下拉建議有 GE 候選（備品庫存沒有）；
頂列 Enter、深連結第一次載入（對照表還在下載）都開得到；手機寬度不橫向捲動。"""
from urllib.parse import quote
from e2e_common import Checks, browser, login, load_card, shot

NON_GE_TAG = 'G12HAP70BT001'     # HRSG 給水的傳送器：非 GE 供貨，沒有 GE 原廠編號（＝test_card 的 FLAG_TAG）

PICK_JS = """async () => {
  await AMS.index.load();
  const IX = AMS.index; const rows = IX.sheet.rows; const out = {};
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]; if (!/^8 /.test(String(r[IX.srcCol]))) continue;
    const key = String(r[IX.kc]); const n = Number(r[IX.countCol]);
    if (IX.first.get(key) !== i) continue;
    const it = { key, raw: String(r[1]), tag: String(r[IX.tagCol]), alias: String(r[IX.ac]), n };
    if (n === 2 && !out.two && /-/.test(key)) out.two = it;
    if (n === 1 && !out.one && /-/.test(key)) out.one = it;
    out.count = (out.count || 0) + 1;
  }
  return out;
}"""

DEV_GE = """() => { const g = document.querySelector('.sum-dev'); if (!g) return null;
  const cf = [...g.querySelectorAll('.cf')].find((e) => ((e.querySelector('.cf-k') || {}).textContent || '').startsWith('GE 原廠編號'));
  return cf ? { val: (cf.querySelector('.cf-v') || cf).textContent.replace('GE 原廠編號', '').trim(), src: !!cf.querySelector('.src-dot') } : null; }"""


def submit(page, sel, text):
    page.fill(sel, text)
    page.press(sel, 'Enter')
    page.wait_for_timeout(1200)


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        login(page, ctx)
        pk = page.evaluate(PICK_JS)
        ck('04: GE 原廠編號列存在（來源類型 8）', (pk.get('count') or 0) >= 100, pk.get('count'))
        two, one = pk.get('two'), pk.get('one')
        ck('picked a GE key on two devices and one on a single device', bool(two and one), pk)
        if not (two and one):
            return ck.fails
        # ---- 查詢卡輸入：正式寫法、不打連字號、小寫加空白
        for label, q in (('exact', two['raw']), ('compact', two['raw'].replace('-', '')), ('lower+space', ' ' + two['raw'].lower() + ' ')):
            page.goto(ctx['base'] + '/db/#/card/'); page.wait_for_selector('#cq-input', timeout=30000)
            submit(page, '#cq-input', q)
            page.wait_for_function("document.querySelector('.sum-tagtext')", timeout=30000)
            tag = page.evaluate("(document.querySelector('.sum-tagtext') || {}).textContent || ''").strip()
            ck('card input %s「%s」→ %s' % (label, q.strip(), two['tag']), tag == two['tag'], tag)
        ck('two devices: switch chips', page.locator('.cq-alts .chip-btn').count() == 2, page.locator('.cq-alts .chip-btn').count())
        # ---- 設備組的 GE 原廠編號一格
        load_card(page, ctx, quote(two['key']))
        d = page.evaluate(DEV_GE)
        ck('dev group: GE 原廠編號 cell has the value and a source dot', bool(d) and two['raw'] in (d or {}).get('val', '') and d['src'], d)
        # ---- 完整資料區的 GE 原廠編號段
        page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1500)
        a = page.evaluate("""() => { const s = document.querySelector('.aux-getag'); if (!s) return null;
          return { subs: s.querySelectorAll('.cf-sub').length, text: s.textContent }; }""")
        ck('full data: .aux-getag has entries', bool(a) and a['subs'] >= 1 and two['raw'] in a['text'], (a or {}).get('subs'))
        shot(page, ctx, 'getag_card')
        # ---- 單台的編號（多半是汽機 KKS 位號的設備）
        load_card(page, ctx, quote(one['key']))
        tag = page.evaluate("(document.querySelector('.sum-tagtext') || {}).textContent || ''").strip()
        ck('single-device GE key opens %s' % one['tag'], tag == one['tag'], tag)
        ck('single-device GE key: no switch chips', page.locator('.cq-alts .chip-btn').count() == 0)
        # ---- 非 GE 設備沒有這一格
        load_card(page, ctx, NON_GE_TAG)
        ck('non-GE device: no GE 原廠編號 cell (hide_empty)', page.evaluate(DEV_GE) is None)
        ck('non-GE device: no pending cells left', page.locator('.sum-dev .pending').count() == 0)
        # ---- 頂列搜尋
        submit(page, '#global-search', two['raw'].replace('-', ''))
        ck('top search (no hyphens) → #/card/<GE key>', page.evaluate('location.hash') == '#/card/' + quote(two['key']) or
           page.evaluate('decodeURIComponent(location.hash)') == '#/card/' + two['key'], page.evaluate('decodeURIComponent(location.hash)'))
        # ---- 下拉建議：不打連字號的前綴
        pre = two['raw'].replace('-', '')[:-1]
        sg = page.evaluate("async (q) => { await AMS.index.load(); return AMS.index.suggest(q, 12).map((x) => x.key); }", pre)
        ck('suggest: hyphenless prefix lists the GE key', two['key'] in sg, (pre, sg[:6]))
        # ---- 備品庫存：GE 列不進位號正規化
        ts = page.evaluate("async (q) => (await AMS.tagSuggestSource.fetch(q)).map((x) => x.src)", two['raw'])
        ck('tagSuggestSource: no GE rows (source type 8)', not any(str(s).startswith('8 ') for s in ts), ts[:4])
        # GE 鍵沒有機組前綴、排在 AMS 位號前面：要在掃描時就跳過，不可先取前 N 筆再濾（否則打 GE 編號的開頭，AMS 位號全被擠掉）
        gp = two['raw'][:4]
        tk = page.evaluate("async (q) => (await AMS.tagSuggestSource.fetch(q)).map((x) => x.key)", gp)
        ams = page.evaluate("async (q) => { await AMS.index.load(); const I = AMS.index; return I.keys.filter((k) => !I.ge.has(k) && k.includes(I.norm(q))).length; }", gp)
        ck('tagSuggestSource: a GE-number prefix still lists AMS tags', ams == 0 or len(tk) >= min(ams, 12), (gp, len(tk), ams))
        nk = page.evaluate("async (q) => AMS.Stock && AMS.Stock.normKks ? AMS.Stock.normKks(q) : null", two['raw'])
        ck('stock normKks: a two-device GE key is not rewritten to one device', nk is None or not nk.get('found'), nk)
        ge_card(page, ctx, ck)
        ck('no page errors', not errors, errors[:3])
        ck('no console errors', not [m for t, m in console if t == 'error'], console[:3])
    with browser(ctx, mobile=True) as (page, errors, console):
        login(page, ctx)
        page.goto(ctx['base'] + '/db/#/card/' + quote(GE_ONLY)); page.wait_for_selector('.ge-only', timeout=60000); page.wait_for_timeout(500)
        ov = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        ck('mobile: GE tag card has no horizontal page scroll', ov[0] <= ov[1], ov)
        shot(page, ctx, 'getag_gecard_mobile')
        ck('mobile: no page errors', not errors, errors[:3])
    return ck.fails


# ---- GE 編號卡（card/getag.json，CONTRACT v8）：AMS 沒有的元件打 GE 編號／Mark VIe 訊號名／KKS 也查得到
GE_ONLY = 'CT-DA-1'          # 壓氣機排氣溫度熱電偶：AMS 沒有這台（熱電偶接 FF 傳送器 96CTDA-1），使用者 2026-10-22 指名的例子
GE_ONLY_KKS = ('G11MBM01BT025', 'G12MBM01BT025')

# 測試用的其他編號一律從資料挑：fuzzy＝AMS 會模糊對應（包含／唯一建議）到別台的 GE-only 編號（冷開深連結要等對照表）；
# amspre＝04 的 GE 鍵去掉最後一字、AMS 唯一建議正是它（PDT-273 → PDT-273A，照舊直接開）；num＝去分隔符後是純數字設備鍵的 GE 編號（74-1）；
# gone＝最新版清單已無此編號；vsig＝閥清單也有的編號的 Mark VIe 訊號名（含底線）
GE_PICK_JS = """async () => {
  await AMS.index.load(); const G = await AMS.getag.load(); if (!G) return null;
  const IX = AMS.index; const E = G.j.entries; const inAms = (c) => IX.compactMap.has(c);
  const out = { n: E.length, ctda1: (G.keys.get('CTDA1') || []).length, ctda10: G.keys.has('CTDA10'), kksInAms: inAms('G11MBM01BT025'), ctdaInAms: inAms('CTDA1') };
  for (const [c, ids] of G.keys) { if (!out.two && ids.length >= 2 && new Set(ids.map((i) => E[i].sc)).size >= 2 && !inAms(c)) out.two = E[ids[0]].t; }
  const V = await AMS.valves.load();
  for (const [c, ids] of G.keys) { if (!out.valve && V && V.index && V.index[c] && !inAms(c) && ids.some((i) => (E[i].sig || []).some((x) => x.includes('_')))) out.valve = E[ids[0]].t; }
  if (out.valve) { const e = E[G.keys.get(IX.compact(out.valve))[0]]; out.vsig = (e.sig || []).find((x) => x.includes('_')); }
  for (const e of E) {
    if (e.ams) continue;
    const rs = IX.resolve(e.t); const h = AMS.getag.hit(e.t);
    if (!out.fuzzy && rs.key && (rs.how === 'contain' || rs.how === 'suggest') && h && h.via === 'key' && !(V && V.index && V.index[IX.compact(e.t)])) out.fuzzy = e.t;
    if (!out.num && rs.how === 'compact' && /^\\d+$/.test(rs.key) && /[^0-9]/.test(e.t)) out.num = e.t;
    if (!out.gone && e.gone && !inAms(IX.compact(e.t)) && h && h.via === 'key' && h.ids.length === 1) out.gone = e.t;
  }
  for (const k of IX.ge) { const q = k.slice(0, -1); const rs = IX.resolve(q); if (!out.amspre && q.length >= 5 && rs.how === 'suggest' && rs.key === k && IX.aliasesOf(k).length === 1) { out.amspre = q; out.amspreKey = k; } }
  // g12sig＝G12 有 AMS 設備的條目的 Mark VIe 訊號名（含底線），帶 G12. 控制器 → 要開 G12 那台（不可被模糊對應帶到 G11）
  for (const e of E) { const a12 = (e.ams || []).find((x) => /^G12/.test(x[1])); const sg = (e.sig || []).find((x) => x.includes('_'));
    if (!out.g12sig && a12 && sg && (e.ams || []).some((x) => /^G11/.test(x[1]))) { out.g12sig = 'G12.' + sg; out.g12tag = a12[1]; } }
  // vsub＝不在 AMS、不在閥清單的 GE 編號，但字串內含另一顆閥的位號（電磁閥 20VA41-21 ⊃ 閥本體 VA41-21）→ GE 卡
  for (const e of E) { const c = IX.compact(e.t); if (out.vsub || e.ams || inAms(c) || (V && V.index && V.index[c])) continue;
    const vh = V ? AMS.valves.hit(V, e.t, 0) : null; if (vh && /^(contain|token)$/.test(vh.via) && !e._c.includes(vh.k) && AMS.getag.hit(e.t).via === 'key') out.vsub = e.t; }
  // other＝04 的 GE 鍵開到 AMS 設備、另一個範圍有同編號而沒有 AMS 設備（PT-2950）
  for (const k of IX.ge) { const h = AMS.getag.hit(k); if (!out.other && h && h.ids.some((i) => !(E[i].ams || []).length) && h.ids.some((i) => (E[i].ams || []).length)) { out.other = k; out.otherSc = E[h.ids.find((i) => !(E[i].ams || []).length)].sc; } }
  return out;
}"""

GE_STATE = """() => { const g = document.querySelector('.ge-only:not(.ge-below)'); return {
  ge: !!g, tag: ((g && g.querySelector('.sum-tagtext')) || {}).textContent || '', status: (document.querySelector('.cq-status') || {}).textContent || '',
  text: g ? g.textContent : '', boxes: g ? g.querySelectorAll('.sum-sig').length : 0, dots: g ? g.querySelectorAll('.src-dot').length : 0,
  srcs: g ? g.querySelectorAll('.cf.has-src').length : 0,
  drive: g ? [...g.querySelectorAll('.cf.has-src')].filter((cf) => [...cf.querySelectorAll('.cf-src a')].some((a) => /drive\\.google\\.com/.test(a.href))).length : 0,
  atlas: g ? [...g.querySelectorAll('a[href*="signal-atlas/#/v/"]')].map((a) => decodeURIComponent(a.getAttribute('href').split('#/v/')[1])) : [],
  links: g ? [...g.querySelectorAll('.ge-links a.chip-btn')].map((a) => decodeURIComponent(a.getAttribute('href'))) : [],
  amstag: (document.querySelector('.sum-tagtext') || {}).textContent || '', nf: !!document.querySelector('.nf'),
  valve: !!document.querySelector('.valve-only'), below: !!document.querySelector('.ge-below'), nfge: [...document.querySelectorAll('.nf-ge .chip-btn .mono')].map((x) => x.textContent) }; }"""

SETTLED = "document.querySelector('.ge-only, .nf, .sum-tagtext') && !/查詢中/.test((document.querySelector('.cq-status') || {}).textContent || '')"


def ge_query(page, ctx, q):
    page.goto(ctx['base'] + '/db/#/card/'); page.wait_for_selector('#cq-input', timeout=30000)
    submit(page, '#cq-input', q)
    page.wait_for_function(SETTLED, timeout=30000)
    page.wait_for_timeout(300)
    return page.evaluate(GE_STATE)


def ge_cold(page, ctx, q):
    """深連結冷開：換到那個網址再重新整理（對照表還沒下載），等到不再是「查詢中」"""
    page.goto(ctx['base'] + '/db/#/card/' + quote(q)); page.reload()
    page.wait_for_function(SETTLED, timeout=60000); page.wait_for_timeout(300)
    return page.evaluate(GE_STATE)


def ge_card(page, ctx, ck):
    pk = page.evaluate(GE_PICK_JS)
    ck('GE tag card data loaded (card/getag.json)', bool(pk) and pk['n'] >= 3000, pk and pk.get('n'))
    if not pk:
        return
    ck('CT-DA-1 is in the GE table and not an AMS key (precondition)', pk['ctda1'] >= 1 and not pk['ctdaInAms'], pk)
    # ---- 三種寫法、全形都開 GE 編號卡
    for q in ('CTDA1', 'CTDA-1', ' ct-da-1 ', 'ＣＴＤＡ－１'):
        s = ge_query(page, ctx, q)
        ck('「%s」→ GE tag card %s' % (q.strip(), GE_ONLY), s['ge'] and s['tag'] == GE_ONLY and 'GE 原廠編號' in s['status'], (s['tag'], s['status'][:60]))
    s = ge_query(page, ctx, 'CTDA1')
    ck('GE card: both units\' KKS listed', all(k in s['text'] for k in GE_ONLY_KKS), s['text'][:120])
    ck('GE card: English service shown', 'COMPRESSOR DISCHARGE TEMPERATURE' in s['text'])
    ck('GE card: source dots', s['dots'] >= 3, s['dots'])
    ck('GE card: every field\'s source details has its own Google Drive link', s['srcs'] >= 3 and s['drive'] == s['srcs'], (s['drive'], s['srcs']))
    ck('GE card: signal-atlas links for G11 and G12', 'G11.CTDA1' in s['atlas'] and 'G12.CTDA1' in s['atlas'], s['atlas'][:6])
    ck('GE card: related FF transmitter 96CTDA-1 linked', any(x.startswith('#/card/96CTDA-1') for x in s['links']), s['links'][:4])
    shot(page, ctx, 'getag_gecard')
    # ---- 帶機組：只列那一台（不可把 G11 的 KKS／訊號掛在 G12 的查詢上）；廠內寫法 GT12 也算機組
    for q in ('G12.CTDA1', 'GT12_CTDA1'):
        s = ge_query(page, ctx, q)
        ck('「%s」→ GE card with G12 only' % q, s['ge'] and GE_ONLY_KKS[1] in s['text'] and GE_ONLY_KKS[0] not in s['text']
           and s['atlas'] and all(x.startswith('G12') for x in s['atlas']), (s['tag'], s['atlas'][:4]))
    # ---- Mark VIe 訊號名（a_ 前綴，狀態列照原寫法）與 KKS
    s = ge_query(page, ctx, 'G11.a_ctda1.PV')
    ck('「G11.a_ctda1.PV」(signal pasted with .PV) → GE card %s' % GE_ONLY, s['ge'] and s['tag'] == GE_ONLY, (s['tag'], s['status'][:60]))
    if pk.get('g12sig'):
        s = ge_query(page, ctx, pk['g12sig'])
        ck('「%s」(G12 controller signal) → the G12 device %s' % (pk['g12sig'], pk['g12tag']), s['amstag'] == pk['g12tag'], (s['amstag'], s['status'][:80]))
    if pk.get('vsub'):
        s = ge_query(page, ctx, pk['vsub'])
        ck("「%s」(contains another valve's tag) → its own GE card, not the other valve" % pk['vsub'], s['ge'] and s['tag'] == pk['vsub'], (s['tag'], s['valve'], s['status'][:60]))
    if pk.get('other'):
        page.goto(ctx['base'] + '/db/#/card/' + quote(pk['other']) + '?sc=' + pk['otherSc']); page.wait_for_function(SETTLED, timeout=30000); page.wait_for_timeout(300)
        s = page.evaluate(GE_STATE)
        ck("#/card/%s?sc=%s (04 key of the other scope) → this scope's GE card" % (pk['other'], pk['otherSc']), s['ge'], (s['tag'], s['status'][:60]))
        s = ge_cold(page, ctx, pk['other'])
        page.wait_for_function("/也有同編號/.test((document.querySelector('.cq-status') || {}).textContent || '')", timeout=15000)
        ck('cold #/card/%s → AMS card, then the 「另一個範圍也有同編號」 note' % pk['other'], not s['ge'] and bool(s['amstag']))
    s = ge_query(page, ctx, 'G11.a_ctda1')
    ck('「G11.a_ctda1」(Mark VIe signal) → GE card %s, quoted as typed' % GE_ONLY, s['ge'] and s['tag'] == GE_ONLY and '「G11.a_ctda1」' in s['status'], (s['tag'], s['status'][:60]))
    if not pk['kksInAms']:
        s = ge_query(page, ctx, GE_ONLY_KKS[0])
        ck('「%s」(KKS, not in AMS) → GE card %s' % (GE_ONLY_KKS[0], GE_ONLY), s['ge'] and s['tag'] == GE_ONLY, (s['tag'], s['status'][:60]))
    # ---- 邊界：CTDA10 不可中 CTDA1；訊號名夾雜別的字不算
    s = ge_query(page, ctx, 'CTDA10')
    ck('「CTDA10」does not open CT-DA-1', s['tag'] != GE_ONLY, (s['tag'], s['status'][:60]))
    fz = page.evaluate("async () => { await AMS.getag.load(); return AMS.fuzzy(null, 'CDTA1', 8).map((x) => x.key); }")
    ck('typo「CDTA1」→ typo suggestions list CT-DA-1', GE_ONLY in fz, fz[:6])
    s = ge_query(page, ctx, 'XYZ CTDA1')
    ck('「XYZ CTDA1」does not open CT-DA-1', s['tag'] != GE_ONLY, (s['tag'], s['status'][:60]))
    # ---- 燃機、汽機各一筆的同一編號：兩塊都列
    if pk.get('two'):
        s = ge_query(page, ctx, pk['two'])
        ck('GE key in both GT and ST scopes (%s) → two blocks' % pk['two'], s['ge'] and s['boxes'] >= 2, s['boxes'])
    # ---- 氣動閥清單也有的編號：閥卡優先，下面接 GE 對照；打它的 Mark VIe 訊號名也一樣（不可變成沒有閥資料的 GE 卡）
    if pk.get('valve'):
        s = ge_query(page, ctx, pk['valve'])
        ck('GE key also on the valve list (%s) → valve card + GE block below' % pk['valve'], s['valve'] and s['below'], s['status'][:60])
        if pk.get('vsig'):
            s = ge_query(page, ctx, pk['vsig'])
            ck('its signal name (%s) → valve card + GE block below' % pk['vsig'], s['valve'] and s['below'], s['status'][:60])
    # ---- 最新版清單已無此編號：卡上要講
    if pk.get('gone'):
        s = ge_query(page, ctx, pk['gone'])
        ck('removed-from-latest-list number (%s) is flagged' % pk['gone'], s['ge'] and '已無此編號' in s['status'] and '已無此編號' in s['text'], s['status'][:80])
    # ---- 去分隔符後是純數字設備鍵的 GE 編號（74-1 → 741）：開 GE 卡、狀態列交代設備鍵是另一台
    if pk.get('num'):
        s = ge_query(page, ctx, pk['num'])
        ck('「%s」(compact = numeric DeviceKey) → GE card, mentions the DeviceKey' % pk['num'], s['ge'] and '設備鍵' in s['status'], (s['tag'], s['status'][:80]))
    # ---- 打一半：查無頁列出相近的 GE 編號；GE 的候選本身就是 04 的鍵時，AMS 唯一建議照舊直接開
    s = ge_query(page, ctx, 'CTDA')
    ck('「CTDA」→ not-found page lists GE candidates incl. CT-DA-1', GE_ONLY in s['nfge'], s['nfge'][:6])
    if pk.get('amspre'):
        s = ge_query(page, ctx, pk['amspre'])
        ck('「%s」→ still auto-opens the AMS device of %s (unique suggestion)' % (pk['amspre'], pk['amspreKey']), not s['nf'] and not s['ge'] and s['amstag'], (s['amstag'], s['status'][:60]))
    # ---- 下拉建議（查詢卡／頂列）有 GE；備品庫存的位號正規化沒有
    sg = page.evaluate("async (q) => (await AMS.searchSuggestSource.fetch(q)).map((x) => [x.key, x.src])", 'CTDA')
    ck('searchSuggestSource: GE candidates for「CTDA」', [GE_ONLY, 'GE 原廠編號'] in sg, sg[:8])
    ck('searchSuggestSource: at most 12', len(sg) <= 12, len(sg))
    ts = page.evaluate("async (q) => (await AMS.tagSuggestSource.fetch(q)).map((x) => x.src)", 'CTDA')
    ck('tagSuggestSource: no GE tag-card candidates', 'GE 原廠編號' not in ts, ts[:4])
    # ---- 頂列搜尋 Enter
    page.goto(ctx['base'] + '/db/#/card/'); page.wait_for_selector('#cq-input', timeout=30000)
    submit(page, '#global-search', 'CTDA1')
    page.wait_for_selector('.ge-only', timeout=30000)
    ck('top search「CTDA1」→ #/card/CTDA1 + GE card', page.evaluate('decodeURIComponent(location.hash)') == '#/card/CTDA1'
       and page.evaluate(GE_STATE)['tag'] == GE_ONLY, page.evaluate('decodeURIComponent(location.hash)'))
    ck('top search: dropdown closed after Enter', page.evaluate("[...document.querySelectorAll('.ac-list')].every((l) => l.hidden)"))
    # ---- 深連結冷開（對照表還沒下載）：查無類（CT-DA-1）與 AMS 會模糊對應到別台的那一類，都要等對照表再判斷——冷開、熱開同一個結果
    s = ge_cold(page, ctx, 'CTDA-1')
    ck('cold deep link #/card/CTDA-1 → GE card', s['ge'] and s['tag'] == GE_ONLY, (s['tag'], s['status'][:60]))
    if pk.get('fuzzy'):
        s = ge_cold(page, ctx, pk['fuzzy'])
        ck('cold deep link #/card/%s (AMS would fuzzy-match another device) → GE card' % pk['fuzzy'], s['ge'] and s['tag'] == pk['fuzzy'], (s['tag'], s['amstag'], s['status'][:60]))
    # ---- 對照表下載失敗：不卡住，查無頁照常、狀態列講對照表沒載到（另開一個擋掉 Service Worker 的 context：SW 快取裡的檔不經過 page.route）
    c2 = page.context.browser.new_context(service_workers='block', bypass_csp=True, viewport={'width': 1280, 'height': 900})
    try:
        p2 = c2.new_page()
        login(p2, ctx)
        p2.route('**/card/getag.json.bin*', lambda r: r.abort())
        s = ge_cold(p2, ctx, 'CTDA1')
        ck('GE table download fails → 查無 page (no hang) with a note', s['nf'] and '沒載到' in s['status'], s['status'][:80])
    finally:
        c2.close()
