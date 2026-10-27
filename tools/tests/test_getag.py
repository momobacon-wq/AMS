# -*- coding: utf-8 -*-
"""GE 原廠編號（card aux 的 sec.getag＋04 位號索引的來源類型 8）：
搜尋（正式寫法 exact、不打連字號 compact、小寫加空白；頂列搜尋 Enter）開到那台設備；一個編號對到兩台時有切換按鈕；
設備組有「GE 原廠編號」一格（有值、有來源點），非 GE 設備沒有這格（hide_empty）；完整資料區有 GE 原廠編號段；
下拉建議打不帶連字號的前綴也列得出來；備品庫存的位號正規化不收 GE 列（tagSuggestSource 濾掉來源類型 8）；console 零錯誤。
測試用的 GE 編號一律從已發布的 04 挑，不寫死。
GE 編號卡（v8，card/getag.json）：AMS 沒有的 CT-DA-1 打 CTDA1／CTDA-1／小寫、帶機組（G12.CTDA1 只列 G12）、Mark VIe 訊號名、KKS 都開 GE 編號卡；
CTDA10 不中 CTDA1；燃機汽機同編號列兩塊；閥清單也有的編號開閥卡＋下面接 GE 對照；查無頁與下拉建議有 GE 候選（備品庫存沒有）；
頂列 Enter、深連結第一次載入（對照表還在下載）都開得到；手機寬度不橫向捲動。
v10（card/getag-loc.json）：96FG-1A 的 GE 編號卡有 P&ID 圖面位置（燃料氣示意圖 GFD01-D0005-3 第 7 頁左上 A-3，影像與紅框）與圖控畫面位置
（SIL EFFF／FtI／Vent，G11、G12 各一組，標頭寫元件所屬機組）；位置區排在規格之前；帶機組只列那一台；沒有位置的編號寫查無；
換到沒有圖紙的卡時圖紙影像收掉；手機寬度不橫向捲動。
v12（2026-10-27）：GE 清單「位置圖」欄的文件編號各自可點開雲端硬碟（CT-DA-2 的 M0147、M0166 兩個連結）；位置區多「位置圖位置」：
CT-DA-2 在 M0147 與 M0166 第 3 頁的引線標註（M0166 第 4 頁的設備表列不發布）、TT-WR-3B 逗號接續、TT-WS1FI-2 形近字、汽機 KKS 標註。"""
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
        ge_spec(page, ctx, ck)
        ge_loc(page, ctx, ck)
        ck('no page errors', not errors, errors[:3])
        ck('no console errors', not [m for t, m in console if t == 'error'], console[:3])
    with browser(ctx, mobile=True) as (page, errors, console):
        login(page, ctx)
        page.goto(ctx['base'] + '/db/#/card/' + quote(GE_ONLY)); page.wait_for_selector('.ge-only', timeout=60000); page.wait_for_timeout(500)
        ov = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        ck('mobile: GE tag card has no horizontal page scroll', ov[0] <= ov[1], ov)
        shot(page, ctx, 'getag_gecard_mobile')
        page.goto(ctx['base'] + '/db/#/card/' + quote(SPEC_TAG)); page.wait_for_selector('.ge-only .ge-spec', timeout=60000); page.wait_for_timeout(500)
        ov = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        ck('mobile: %s card with spec blocks and related valves has no horizontal page scroll' % SPEC_TAG, ov[0] <= ov[1], ov)
        shot(page, ctx, 'getag_spec_mobile')
        # 影像延後載入（捲到附近才抓）：先捲到 P&ID、再捲到圖控
        page.wait_for_function("(() => { const l = document.querySelector('.ge-only .ge-loc'); return l && !/載入中/.test(l.textContent); })()", timeout=60000)
        page.evaluate("document.querySelector('.ge-loc .ge-pid').scrollIntoView()")
        page.wait_for_function("document.querySelector('.ge-loc .ge-pid img')", timeout=60000)
        page.evaluate("document.querySelector('.ge-loc .ge-hmi').scrollIntoView()")
        page.wait_for_function("document.querySelector('.ge-loc .ge-hmi img')", timeout=60000)
        page.wait_for_timeout(500)
        ov = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
        ck('mobile: %s card with P&ID and HMI images has no horizontal page scroll' % SPEC_TAG, ov[0] <= ov[1], ov)
        shot(page, ctx, 'getag_loc_mobile')
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

# ---- 元件詳細資料與相關閥（CONTRACT v9）：使用者 2026-10-24 指名的 96FG-1A（P1 腔壓力傳送器，AMS 沒有這台）
SPEC_TAG = '96FG-1A'
SPEC_WANT = ('EMERSON', '3051CG5A22A1AK7M5Q4Z1', '-14.2 to 800 psi-g')   # A0102 rev C／rev T 的廠牌、型號、校正範圍（xlsb 第 239 列同值）
SPEC_VALVE = 'VA13-25'      # P1 排氣閥（氣動閥清單也有 → 點了開閥卡）
SPEC_STATE = """() => { const g = document.querySelector('.ge-only'); if (!g) return null; const rel = [...g.querySelectorAll('.ge-rel')];
  const cfs = [...g.querySelectorAll('.ge-spec')].flatMap((h) => { const out = []; let n = h.nextElementSibling; while (n && !n.classList.contains('sum-sigh')) { out.push(...n.querySelectorAll('.cf.has-src')); n = n.nextElementSibling; } return out; });
  return { spec: g.querySelectorAll('.ge-spec').length, text: g.textContent,
    rel: rel.map((r) => ({ label: (r.firstElementChild || {}).textContent || '', items: [...r.querySelectorAll('.ge-rel-i')].map((i) => ({ href: decodeURIComponent((i.querySelector('a') || {}).getAttribute ? i.querySelector('a').getAttribute('href') : ''), lvl: ((i.querySelector('.src-chip') || {}).textContent || ''), text: i.textContent })) })),
    specSrcs: cfs.length, specDrive: cfs.filter((cf) => [...cf.querySelectorAll('.cf-src a')].some((a) => /drive\\.google\\.com/.test(a.href))).length }; }"""
# 功能組區塊（.ge-prot：腔室／管段、保護功能）：標題開頭相符的那一段 → [{fn, roles, tags}]；收合的先打開
PROT_JS = """(head) => { const g = document.querySelector('.ge-below') || document.querySelector('.ge-only'); if (!g) return null;
  const p = [...g.querySelectorAll('.ge-prot')].find((x) => ((x.querySelector('summary') || x.firstElementChild || {}).textContent || '').startsWith(head));
  if (!p) return null; if (p.tagName === 'DETAILS') p.open = true;
  return [...p.querySelectorAll('.ge-prot-i')].map((i) => ({ fn: ((i.querySelector('.ge-prot-h b') || {}).textContent || ''),
    roles: [...i.querySelectorAll('a.chip-btn .muted')].map((x) => x.textContent.trim()).filter(Boolean).length,
    tags: [...i.querySelectorAll('a.chip-btn')].map((a) => decodeURIComponent(a.getAttribute('href')).split('?')[0]) })); }"""
SPEC_PICK_JS = """async () => { const G = await AMS.getag.load(); if (!G) return null; const E = G.j.entries;
  const out = { sp: E.filter((e) => (e.sp || []).length).length, vl: E.filter((e) => (e.vl || []).length).length, vi: E.filter((e) => (e.vi || []).length).length,
    pr: E.filter((e) => (e.pr || []).length).length, pi: E.filter((e) => (e.pi || []).length).length,
    ps: E.filter((e) => (e.ps || []).length).length, pv: E.filter((e) => (e.pv || []).length).length };
  const e = E.find((x) => (x.ams || []).length && (x.sp || []).length); if (e) { out.amsAlias = e.ams[0][0]; out.amsTag = e.ams[0][1]; out.amsGe = e.t; }
  return out; }"""


def ge_spec(page, ctx, ck):
    pk = page.evaluate(SPEC_PICK_JS)
    ck('GE card data has spec blocks, related valves and protection functions (sp／vl／vi／pr／pi)',
       bool(pk) and pk['sp'] >= 1000 and pk['vl'] >= 100 and pk['vi'] >= 50 and pk['pr'] >= 100 and pk['pi'] >= 10 and pk['ps'] >= 50 and pk['pv'] >= 20, pk)
    s = ge_query(page, ctx, SPEC_TAG)
    ck('「%s」→ GE card' % SPEC_TAG, s['ge'] and s['tag'] == SPEC_TAG, (s['tag'], s['status'][:60]))
    sp = page.evaluate(SPEC_STATE)
    ck('%s: spec blocks shown (廠牌／型號／校正範圍)' % SPEC_TAG, bool(sp) and sp['spec'] >= 1 and all(w in sp['text'] for w in SPEC_WANT), sp and [w for w in SPEC_WANT if w not in sp['text']])
    ck('%s: every spec field has a source with a Google Drive link' % SPEC_TAG, bool(sp) and sp['specSrcs'] >= 3 and sp['specDrive'] == sp['specSrcs'], sp and (sp['specDrive'], sp['specSrcs']))
    # 所在腔室（P&ID 137T9782 Sheet 3）：P1 腔＝VS4-4 → VGS-1／VSC-1，排放閥 VA13-25
    po = page.evaluate(PROT_JS, '所在腔室')
    ck('%s: 所在腔室 P1 腔 lists VS4-4, VGS-1 and %s with roles' % (SPEC_TAG, SPEC_VALVE),
       bool(po) and any(x['fn'] == 'P1 腔' and {'#/card/VS4-4', '#/card/VGS-1', '#/card/' + SPEC_VALVE} <= set(x['tags']) and x['roles'] for x in po), po)
    # 參與的保護功能：通風 SIF（P1 腔壓力啟用）跳機時連同 SSOV VS4-4 與 P1 排放閥 VA13-25 動作（308T9574 §15.1）
    pr = page.evaluate(PROT_JS, '參與的保護功能')
    ck('%s: 參與的保護功能 has a function actuating VS4-4 and VA13-25' % SPEC_TAG,
       bool(pr) and any('#/card/VS4-4' in x['tags'] and '#/card/' + SPEC_VALVE in x['tags'] for x in pr), pr and [x['fn'] for x in pr])
    shot(page, ctx, 'getag_spec')
    # 點腔室裡的 VA13-25 → 那顆閥的閥卡（氣動閥清單有），下面接 GE 對照：邊界的腔室 P1 腔列出 96FG-1A，相關儀器有它的極限開關
    page.locator('.ge-prot a.chip-btn[href^="#/card/%s"]' % SPEC_VALVE).first.click()
    page.wait_for_function(SETTLED, timeout=30000); page.wait_for_timeout(800)
    st = page.evaluate(GE_STATE)
    ck('click %s → valve card + GE block below' % SPEC_VALVE, st['valve'] and st['below'], st['status'][:60])
    pv = page.evaluate(PROT_JS, '這顆閥邊界的腔室')
    ck('%s valve card: 邊界的腔室 P1 腔 lists %s' % (SPEC_VALVE, SPEC_TAG), bool(pv) and any('#/card/' + SPEC_TAG in x['tags'] for x in pv), pv)
    vi = page.evaluate("""() => { const g = document.querySelector('.ge-below'); if (!g) return null;
      const r = [...g.querySelectorAll('.ge-rel')].find((x) => /^相關儀器/.test((x.firstElementChild || {}).textContent || ''));
      return r ? [...r.querySelectorAll('a.chip-btn')].map((a) => decodeURIComponent(a.getAttribute('href')).split('?')[0]) : []; }""")
    ck('%s valve card: 相關儀器 lists its limit switch 33VG-8 (KKS -BG02)' % SPEC_VALVE, bool(vi) and '#/card/33VG-8' in vi, vi)
    # AMS 設備卡：完整資料區的 GE 原廠編號段也有規格塊
    if pk and pk.get('amsAlias'):
        load_card(page, ctx, quote(pk['amsAlias']))
        page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1500)
        a = page.evaluate("() => { const s = document.querySelector('.aux-getag'); return s ? s.textContent : null; }")
        ck('AMS device %s (GE %s): full data getag section has a spec block' % (pk['amsTag'], pk['amsGe']), bool(a) and '規格' in a, (a or '')[:80])


# ---- GE 編號卡的 P&ID／圖控位置（CONTRACT v10；card/getag-loc.json）
LOC_PICK_JS = """async (tag) => { const G = await AMS.getag.load(); if (!G || !G.j.loc) return null; const E = G.j.entries;
  const L = await AMS.data.fetchJSON(G.j.loc); const by = L.by_i || {};
  const i = E.findIndex((e) => e.t === tag && e.sc === 'G'); const lo = by[String(i)] || {};
  const pd0 = (lo.pd || [])[0]; const ex = pd0 ? pd0[4] : {};
  const firsts = (lo.hm || []).filter((r) => r[4] && r[4].marks).map((r) => r[4]);
  const none = E.findIndex((e, k) => !e.lc && !(e.ams || []).length && e.sc === 'G' && /^[0-9]{2}[A-Z]{2,}-[0-9]+[A-Z]?$/.test(e.t)
    && (G.keys.get(e._c[0]) || []).length === 1);
  return { lc: E.filter((e) => e.lc).length, n: Object.keys(by).length, pd: E.filter((e, k) => (by[String(k)] || {}).pd).length,
    hm: E.filter((e, k) => (by[String(k)] || {}).hm).length, lcOk: E.every((e, k) => !!e.lc === !!by[String(k)]),
    sheet: ex.s || '', p: ex.p, zone: ex.zone || '', m0: (ex.marks || [])[0] || null, via: ex.via || '',
    hmScreens: firsts.map((x) => x.s + '|' + x.gu + '|' + (x.ctrl || '')), none: none >= 0 ? E[none].t : null }; }"""
SIL_TAG = 'VS4-4'   # 燃料氣 SSOV：製程畫面 4 張＋SIL 畫面 16 張（同一個面板）
LOC_STATE = """() => { const g = document.querySelector('.ge-only:not(.ge-below)'); if (!g) return null; const l = g.querySelector('.ge-loc'); if (!l) return null;
  const pid = l.querySelector('.ge-pid'); const hmi = l.querySelector('.ge-hmi'); const sp = g.querySelector('.ge-spec');
  return { heads: [...l.querySelectorAll('.ge-loc-h')].map((h) => h.textContent.trim()), loading: /載入中/.test(l.textContent),
    before: !sp || !!(l.compareDocumentPosition(sp) & Node.DOCUMENT_POSITION_FOLLOWING),
    pidText: pid.textContent, sheets: [...pid.querySelectorAll('.pid-sheet')].map((b) => (b.querySelector('.pid-head') || b).textContent),
    pidLink: [...pid.querySelectorAll('.pid-bar a')].map((a) => a.href), pidImg: pid.querySelectorAll('img').length, pidMk: pid.querySelectorAll('.hmi-box, .hmi-mk').length,
    hmiText: hmi.textContent, screens: [...hmi.querySelectorAll('.hmi-screen')].map((b) => (b.querySelector('.hmi-head') || b).textContent),
    hmiImg: hmi.querySelectorAll('img').length }; }"""


# 反方驗證 2026-10-25 之後的規則（CONTRACT v10）：圖面標籤與對照表 KKS 對調時以圖上標籤為準、汽機發電機示意圖 EGK01-D0033 有收、
# 排氣熱電偶走逐通道巨集的變數（TTXD1_16 不是 TTXD1_6）、附屬件的圖控位置標「主設備」、短名 CV-2 不再配到蒸汽控制閥面板
LOC_FIX_JS = """async () => { const G = await AMS.getag.load(); const E = G.j.entries; const L = await AMS.data.fetchJSON(G.j.loc); const by = L.by_i || {};
  const lo = (sys, t) => by[String(E.findIndex((e) => e.t === t && e.sys === sys))] || {};
  const firsts = (rows) => (rows || []).filter((r) => r[4] && r[4].marks).map((r) => r[4]);
  const how = (rows) => (rows || []).filter((r) => r[0] === '對應方式').map((r) => String(r[1])).join('｜');
  const gc = firsts(lo('燃機發電機', 'GC-1').pd);
  const tt = lo('燃機', 'TT-XD-16').hm; const ve = firsts(lo('汽機發電機', '39V-4A').pd); const qb = firsts(lo('燃機', '23QB-1').hm);
  return { gcKksOnEg004: gc.filter((x) => x.via === 'kks' && /EG004/.test(x.drawn || '') && /EGJ01-D0004/.test(x.s || '')).length, gcN: gc.length,
    ttHow: how(tt).slice(0, 300), ttN: firsts(tt).length, tt6: /TTXD1_6(?![0-9])/.test(how(tt)),
    veSheet: ve.length ? ve[0].s : '', qbN: qb.length, qbHost: qb.length && qb.every((x) => x.host === 1), cv2: firsts(lo('汽機', 'CV-2').hm).length }; }"""


# v11（2026-10-25）：圖控轉手鏈（71GS-1B 的 a_71gs1b →MOVE_STATUS→ F71SCR3DR；PT-270C 由設計標題升成 63QT3）、
# P&ID 括號線條字 GE 標籤（VA13-15、汽機 FV-24 只有線條字）
LOC_V11_JS = """async () => { const G = await AMS.getag.load(); const E = G.j.entries; const L = await AMS.data.fetchJSON(G.j.loc); const by = L.by_i || {};
  const lo = (sys, t) => by[String(E.findIndex((e) => e.t === t && e.sys === sys))] || {};
  const firsts = (rows) => (rows || []).filter((r) => r[4] && r[4].marks).map((r) => r[4]);
  const how = (rows) => (rows || []).filter((r) => r[0] === '對應方式').map((r) => String(r[1])).join('｜');
  const lvls = (rows) => (rows || []).filter((r) => r[0] === '對應方式').map((r) => r[2]);
  const gs = lo('燃機', '71GS-1B').hm; const pt = lo('汽機', 'PT-270C').hm;
  const va = firsts(lo('燃機', 'VA13-15').pd); const fv = firsts(lo('汽機', 'FV-24').pd);
  return { gsHow: how(gs).slice(0, 400), gsN: firsts(gs).length, ptHow: how(pt).slice(0, 400), ptLvl: lvls(pt),
    va: va.map((x) => x.s + '|' + x.p), fv: fv.map((x) => x.s + '|' + x.p),
    chainN: E.filter((e, k) => (how((by[String(k)] || {}).hm) || '').includes('一對一的搬移')).length }; }"""


# v11：對照表更正檔（hst-docsearch ge_tags_overrides.json，反方驗證後才收）——清單自相矛盾的改正（ZS-211AC 寫成再熱側 MAB11、
# 20VS4-4 誤取閥本體）、文件之間不一致兩個都列（GC-1～4）、只有一份文件寫錯的只記說明（VE45 的 4／5 號軸承錯一號）
FIX_JS = """async () => { const G = await AMS.getag.load(); const E = G.j.entries;
  const f = (sys, t) => E.find((e) => e.t === t && e.sys === sys) || null; const s = (e) => (e ? JSON.stringify(e) : '');
  const zs = s(f('汽機', 'ZS-211AC')); const gc = s(f('燃機發電機', 'GC-1')); const vp = s(f('汽機', 'VP-4X')); const sv = f('燃機', '20VS4-4');
  return { zsKks: zs.includes('MAA11QN001-BG04'), zsFix: zs.includes('對照表更正') && zs.includes('已更正'), zsSig: zs.includes('di_l33cv1_c_st'),
    zsIv: zs.includes('iv1_pos'), gcConf: gc.includes('文件不一致') && gc.includes('EG001'),
    vpNote: vp.includes('不列為別名'), vpAlias: vp.split('其他文件寫的 KKS').slice(1).some((x) => x.split(']')[0].includes('MAD50BG021')), svSvc: sv ? sv.svc : '', svKks: s(sv).includes('QN210-MB01'),
    nFix: E.filter((e) => s(e).includes('"對照表更正"')).length }; }"""


# v12：位置圖（loc_ge.py）——CT-DA-2 兩份位置圖（M0147 清單第一份、M0166 只留第 3 頁的引線標註）、TT-WR-3B 逗號接續（M0150）、
# TT-WS1FI-2 形近字（M0147 寫 TT-WSIF1-2）、汽機以 KKS 本體標在 TZD01-D0002 上的、規格格的文件編號（doc_no）
LD_JS = """async () => { const G = await AMS.getag.load(); const E = G.j.entries; const L = await AMS.data.fetchJSON(G.j.loc); const by = L.by_i || {};
  const at = (sys, t) => by[String(E.findIndex((e) => e.t === t && e.sys === sys))] || {};
  const heads = (rows) => (rows || []).filter((r) => r[4] && r[4].marks).map((r) => r[4]);
  const how = (rows) => (rows || []).filter((r) => r[0] === '對應方式').map((r) => String(r[1])).join('｜');
  const ct = at('燃機', 'CT-DA-2'); const wr = at('燃機', 'TT-WR-3B'); const ws = at('燃機', 'TT-WS1FI-2');
  const st = E.filter((e, k) => e.sc === 'S' && heads((by[String(k)] || {}).ld).some((x) => x.via === 'kks' && !x.note && x.listed));
  const dn = G.j.doc_no || {};
  return { n: E.filter((e, k) => (by[String(k)] || {}).ld).length, cIdx: E.findIndex((e) => e.t === 'CT-DA-2' && e.sys === '燃機'),
    ct: heads(ct.ld).map((x) => x.s + '|' + x.p + '|' + (x.notes || [0]).join('') + '|' + x.listed), ctLdn: ct.ldn || null,
    wr: heads(wr.ld).map((x) => x.s), wrHow: how(wr.ld), ws: heads(ws.ld).map((x) => x.s), wsHow: how(ws.ld), wsLvl: (ws.ld || []).map((r) => r[2]),
    stN: st.length, docNo: Object.keys(dn).length, m147: dn['HT0-1-GZD01-M0147'] || '', m166: dn['HT0-1-GZD01-M0166'] || '',
    url147: ((G.j.docs || {})[dn['HT0-1-GZD01-M0147']] || {}).url || '', url166: ((G.j.docs || {})[dn['HT0-1-GZD01-M0166']] || {}).url || '' }; }"""
LD_TAG = 'CT-DA-2'
LD_STATE = """() => { const g = document.querySelector('.ge-only:not(.ge-below)'); if (!g) return null; const l = g.querySelector('.ge-loc .ge-ld'); if (!l) return null;
  const cf = [...g.querySelectorAll('.ge-spec + .cfields .cf, .cfields .cf')].find((x) => (x.querySelector('.cf-k') || {}).textContent === '位置圖');
  return { loading: /載入中/.test(l.textContent), sheets: [...l.querySelectorAll('.pid-sheet')].map((b) => (b.querySelector('.pid-head') || b).textContent),
    img: l.querySelectorAll('img').length, mk: l.querySelectorAll('.hmi-box, .hmi-mk').length, link: [...l.querySelectorAll('.pid-bar a')].map((a) => a.href),
    locLinks: cf ? [...cf.querySelectorAll('.cf-v a.doclk')].map((a) => [a.textContent, a.href]) : null, locText: cf ? cf.querySelector('.cf-v').textContent : null }; }"""


def ge_ld(page, ctx, ck):
    v = page.evaluate(LD_JS)
    ck('v12 location drawings: ≥ 1000 GE entries have a 位置圖 position', bool(v) and v['n'] >= 1000, v and v['n'])
    ck('CT-DA-2: 位置圖 ① is GZD01-M0147 (first on its list), M0166 p.3 callout is listed, M0166 p.4 table row is not published',
       bool(v) and v['ct'] and 'GZD01-M0147' in v['ct'][0] and any('GZD01-M0166' in x and '|3|' in x for x in v['ct'])
       and not any('GZD01-M0166' in x and '|4|' in x for x in v['ct']) and all(x.endswith('|1') for x in v['ct']) and not v['ctLdn'],
       v and (v['ct'], v['ctLdn']))
    ck('TT-WR-3B: comma-continued label TT-WR-3A,3B,3C on GZD01-M0150', bool(v) and any('GZD01-M0150' in x for x in v['wr']) and '逗號接續' in v['wrHow'],
       v and (v['wr'], v['wrHow'][:80]))
    ck('TT-WS1FI-2: look-alike TT-WSIF1-2 on GZD01-M0147, level inferred', bool(v) and any('GZD01-M0147' in x for x in v['ws']) and '形近字' in v['wsHow']
       and 'inferred' in v['wsLvl'], v and (v['ws'], v['wsHow'][:80]))
    ck('ST: ≥ 100 entries located by bare KKS callouts on their listed drawing (TZD01-D0002)', bool(v) and v['stN'] >= 100, v and v['stN'])
    ck('getag.json doc_no: spec cells\' document numbers resolve (M0147, M0166 → Drive url)', bool(v) and v['docNo'] >= 50 and v['m147'] and v['m166']
       and 'drive.google.com' in v['url147'] and 'drive.google.com' in v['url166'] and v['url147'] != v['url166'], v and (v['docNo'], v['m147'], v['m166']))
    s = ge_query(page, ctx, LD_TAG)
    ck('「%s」→ GE card (location drawing test)' % LD_TAG, s['ge'] and s['tag'] == LD_TAG, s['tag'])
    page.wait_for_function("(() => { const l = document.querySelector('.ge-only .ge-loc .ge-ld'); return l && !/載入中/.test(l.textContent); })()", timeout=60000)
    page.evaluate("document.querySelector('.ge-only .ge-loc .ge-ld').scrollIntoView({ block: 'center' })")   # 位置圖在 P&ID、圖控之下：影像捲到附近才抓
    page.wait_for_function("document.querySelector('.ge-loc .ge-ld img')", timeout=60000)
    page.wait_for_timeout(800)
    st = page.evaluate(LD_STATE)
    ck('%s: 位置圖 cell shows two document numbers, each its own Drive link' % LD_TAG,
       bool(st) and st['locLinks'] and len(st['locLinks']) == 2 and {t for t, _h in st['locLinks']} == {'HT0-1-GZD01-M0147', 'HT0-1-GZD01-M0166'}
       and all('drive.google.com' in h for _t, h in st['locLinks']) and st['locLinks'][0][1] != st['locLinks'][1][1], st and (st['locLinks'], st['locText']))
    ck('%s: 位置圖位置 part lists M0147 first, with a Drive link, a loaded image and marks' % LD_TAG,
       bool(st) and st['sheets'] and 'GZD01-M0147' in st['sheets'][0] and any('GZD01-M0166' in x for x in st['sheets'])
       and any('drive.google.com' in h for h in st['link']) and st['img'] >= 1 and st['mk'] >= 1, st and (st['sheets'][:3], st['img'], st['mk']))
    shot(page, ctx, 'getag_ld')


# v13：接線路徑（wire_ge.py）——汽機 TSI 54 顆：VP-1X 近接探頭（JB 前置器 → TVBA，螺絲號與控制器組態核對）、VP-5XVL 速度型（1TBVIB，
# 接線圖寫 57 而 3500 盤圖寫 47 的矛盾要在卡上）、SEDP-1 直拉、39VS-91 發電機接線箱；非 TSI 的 GE 卡不出這一塊
WP_JS = """async () => { const G = await AMS.getag.load(); const E = G.j.entries; const L = await AMS.data.fetchJSON(G.j.loc); const by = L.by_i || {};
  const at = (t) => (by[String(E.findIndex((e) => e.t === t && e.sc === 'S'))] || {}).wp || null;
  const all = E.map((e, k) => (by[String(k)] || {}).wp).filter(Boolean);
  const vp = at('VP-1X'); const vl = at('VP-5XVL'); const se = at('SEDP-1'); const g9 = at('39VS-91');
  const mv = all.flatMap((w) => (w.t || []).filter((r) => /(TVBA|TTUR|TCSA|TBAI)/.test(r[3])));
  return { n: all.length, vpMode: vp && vp.mode, vpT: vp ? vp.t.map((r) => r.join('|')) : [], vpSum: vp ? vp.sum.map((r) => r[0] + '：' + r[1]) : [],
    vpHops: vp ? vp.rows.filter((r) => r[4] && r[4].marks).map((r) => r[4].hop) : [], vpJb: vp && vp.jb ? vp.jb[1].length : 0,
    vlNotes: vl ? (vl.n || []).map((x) => x[0]).join('｜') : '', vlT: vl ? vl.t.map((r) => r[3]).join('｜') : '',
    seMode: se && se.mode, g9Mode: g9 && g9.mode, mvN: mv.length, mvBad: mv.filter((r) => !['same', 'loc'].includes(r[5])).map((r) => r.join('|')) }; }"""
WP_TAG = 'VP-1X'
WP_STATE = """() => { const g = document.querySelector('.ge-only:not(.ge-below)'); if (!g) return null; const w = g.querySelector('.ge-loc .ge-wire');
  if (!w) return { none: true };
  return { loading: /載入中/.test(w.textContent), sum: w.querySelectorAll('table.wire-sum tbody tr').length, cond: w.querySelectorAll('table.wire-cond tbody tr').length,
    ok: w.querySelectorAll('table.wire-cond tbody td[title]').length, sheets: [...w.querySelectorAll('.pid-sheet')].map((b) => (b.querySelector('.pid-head') || b).textContent),
    img: w.querySelectorAll('.wire-pics img').length, mk: w.querySelectorAll('.wire-pics .hmi-box, .wire-pics .hmi-mk').length,
    link: [...w.querySelectorAll('.pid-bar a')].map((a) => a.href), jb: !!w.querySelector('details.wire-jb'), text: w.textContent.slice(0, 400) }; }"""


def ge_wp(page, ctx, ck):
    v = page.evaluate(WP_JS)
    ck('v13 wiring paths: 54 ST TSI entries carry a 接線路徑', bool(v) and v['n'] == 54, v and v['n'])
    ck('VP-1X: coax path, BK-1 → JB VX-1X -VDC → CA004-1L1A TVBA 04, pin N24V02 checked against the controller config',
       bool(v) and v['vpMode'] == 'coax' and any(x.startswith('BK-1|COAX|VX-1X -VDC|CA004-1L1A TVBA 04|N24V02|same') for x in v['vpT']), v and v['vpT'][:2])
    ck('VP-1X: hops = wiring diagram, JB location, board position, 3500 rack; Mark VIe row names a_39vb1x; JB strip listed',
       bool(v) and v['vpHops'][:1] == ['wire'] and {'jbloc', 'cab', 'rack'} <= set(v['vpHops']) and any(s.startswith('Mark VIe') and 'a_39vb1x' in s for s in v['vpSum'])
       and v['vpJb'] >= 20, v and (v['vpHops'], v['vpJb']))
    ck('VP-5XVL: lands on 1TBVIB (57 as drawn) and the card carries the 57 vs 47 conflict note',
       bool(v) and '1TBVIB 57' in v['vlT'] and '57' in v['vlNotes'] and '47' in v['vlNotes'], v and (v['vlT'], v['vlNotes'][:120]))
    ck('SEDP-1 direct pull, 39VS-91 inside the generator JB', bool(v) and v['seMode'] == 'direct' and v['g9Mode'] == 'jbdev', v and (v['seMode'], v['g9Mode']))
    ck('every conductor landing on a Mark VIe board (TVBA/TTUR/TCSA/TBAI) is checked against the controller screw map (116, none off)',
       bool(v) and v['mvN'] == 116 and not v['mvBad'], v and (v['mvN'], v['mvBad'][:3]))
    s = ge_query(page, ctx, WP_TAG)
    ck('「%s」→ GE card (wiring path test)' % WP_TAG, s['ge'] and s['tag'] == WP_TAG, s['tag'])
    page.wait_for_function("(() => { const l = document.querySelector('.ge-only .ge-loc .ge-wire'); return l && !/載入中/.test(l.textContent); })()", timeout=60000)
    page.evaluate("document.querySelector('.ge-only .ge-loc .ge-wire .wire-pics').scrollIntoView({ block: 'center' })")   # 接線路徑在最下面：影像捲到附近才抓
    page.wait_for_function("document.querySelector('.ge-loc .ge-wire .wire-pics img')", timeout=60000)
    page.wait_for_timeout(800)
    st = page.evaluate(WP_STATE)
    ck('%s: 接線路徑 part shows the hop table, 4 conductors with checks, the wiring sheet first (Drive link, image, marks) and the JB strip' % WP_TAG,
       bool(st) and not st.get('none') and st['sum'] >= 6 and st['cond'] == 4 and st['ok'] >= 3 and st['sheets'] and 'ICE01-D1005' in st['sheets'][0]
       and any('drive.google.com' in h for h in st['link']) and st['img'] >= 1 and st['mk'] >= 1 and st['jb'], st and {k: st[k] for k in st if k != 'text'})
    shot(page, ctx, 'getag_wp')
    s = ge_query(page, ctx, LD_TAG)
    page.wait_for_function("(() => { const l = document.querySelector('.ge-only .ge-loc .ge-ld'); return l && !/載入中/.test(l.textContent); })()", timeout=60000)
    st = page.evaluate(WP_STATE)
    ck('%s (not ST TSI): no 接線路徑 part' % LD_TAG, bool(st) and st.get('none'), st)


def ge_loc(page, ctx, ck):
    ge_ld(page, ctx, ck)
    ge_wp(page, ctx, ck)
    fx2 = page.evaluate(FIX_JS)
    ck('crosswalk fix ZS-211AC: KKS corrected to MAA11QN001-BG04, card says 已更正, signal di_l33cv1_c_st (no longer iv1_pos)',
       bool(fx2) and fx2['zsKks'] and fx2['zsFix'] and fx2['zsSig'] and not fx2['zsIv'], fx2)
    ck('crosswalk fix GC-1: both KKS listed as a document conflict (EG004 list vs EG001 drawing)', bool(fx2) and fx2['gcConf'], fx2 and fx2['gcConf'])
    ck('crosswalk fix VP-4X: VE45 one-bearing shift noted, MAD50BG021 not listed as an alias', bool(fx2) and fx2['vpNote'] and not fx2['vpAlias'],
       fx2 and (fx2['vpNote'], fx2['vpAlias']))
    ck('crosswalk fix 20VS4-4: solenoid KKS QN210-MB01 and service SAFETY SHUTOFF VALVE SOLENOID; ≥ 50 entries carry a 對照表更正 row',
       bool(fx2) and fx2['svKks'] and fx2['svSvc'] == 'SAFETY SHUTOFF VALVE SOLENOID' and fx2['nFix'] >= 50, fx2 and (fx2['svSvc'], fx2['nFix']))
    v11 = page.evaluate(LOC_V11_JS)
    ck('71GS-1B: HMI position via the one-to-one MOVE chain a_71gs1b → F71SCR3DR (card names the block)',
       bool(v11) and v11['gsN'] >= 1 and 'F71SCR3DR' in v11['gsHow'] and 'a_71gs1b' in v11['gsHow'] and 'MOVE' in v11['gsHow'], v11 and v11['gsHow'][:160])
    ck('PT-270C: ST SIL lube oil panel now located through 63QT3 (chain), level not inferred',
       bool(v11) and '63QT3' in v11['ptHow'] and 'hmi' in v11['ptLvl'], v11 and (v11['ptHow'][:120], v11['ptLvl']))
    ck('VA13-15: P&ID on GFD01-D0005-3 p.7 from the bracketed line-text label (OCR, GE-only table)',
       bool(v11) and any('GFD01-D0005-3' in x and x.endswith('|7') for x in v11['va']), v11 and v11['va'])
    ck('ST FV-24: P&ID on TFD01-D0001 (line-text label only)', bool(v11) and any('TFD01-D0001' in x for x in v11['fv']), v11 and v11['fv'])
    ck('chain-located GE entries on the card ≥ 40', bool(v11) and v11['chainN'] >= 40, v11 and v11['chainN'])
    fx = page.evaluate(LOC_FIX_JS)
    ck('GC-1: drawing label wins over the crosswalk KKS (no box on EG004 of EGJ01-D0004, which that drawing labels GC-4)', bool(fx) and fx['gcN'] >= 1 and fx['gcKksOnEg004'] == 0, fx and (fx['gcN'], fx['gcKksOnEg004']))
    ck('TT-XD-16: HMI positions via TTXD1_16 (per-channel macro output), never TTXD1_6', bool(fx) and fx['ttN'] >= 2 and 'TTXD1_16' in fx['ttHow'] and not fx['tt6'], fx and fx['ttHow'][:120])
    ck('39V-4A (ST generator): P&ID on EGK01-D0033 (ST Generator Load Equipment Schematic)', bool(fx) and 'EGK01-D0033' in fx['veSheet'], fx and fx['veSheet'])
    ck('23QB-1 (space heater): every HMI group is flagged as the host device position', bool(fx) and fx['qbN'] >= 1 and fx['qbHost'], fx and (fx['qbN'], fx['qbHost']))
    ck('ST CV-2 (lube oil check valve): no HMI position on the steam control valve panel', bool(fx) and fx['cv2'] == 0, fx and fx['cv2'])
    pk = page.evaluate(LOC_PICK_JS, SPEC_TAG)
    ck('GE location file loaded: entries with P&ID ≥ 2000, with HMI ≥ 500, lc flags match the file',
       bool(pk) and pk['pd'] >= 2000 and pk['hm'] >= 500 and pk['lcOk'] and pk['lc'] == pk['n'], pk and {k: pk[k] for k in ('lc', 'n', 'pd', 'hm', 'lcOk')})
    if not pk:
        return
    # 燃料氣示意圖 137T9782（HT0-1-GFD01-D0005-3）第 7 頁左上：PIT 球泡 MBP70BP001＋(96FG-1A)（主控 2026-10-24 開圖核過：約左 17%／上 11%，圖框 A-3）
    m0 = pk['m0'] or [0, 0]
    ck('%s: P&ID ① is GFD01-D0005-3 p.7 zone A-3, upper left, GE tag + KKS merged' % SPEC_TAG,
       'GFD01-D0005-3' in pk['sheet'] and pk['p'] == 7 and pk['zone'] == 'A-3' and 0.12 < m0[0] < 0.22 and 0.06 < m0[1] < 0.16 and pk['via'] == 'ge+kks',
       {k: pk[k] for k in ('sheet', 'p', 'zone', 'm0', 'via')})
    want = {'gtHA_Gen2_SIL_EFFF_UX.cim|G11|G11S', 'gtHA_Gen2_SIL_EFFF_UX.cim|G12|G12S', 'gtHA_Gen2_SIL_FtI_UX.cim|G11|G11S',
            'gtHA_Gen2_SIL_Vent_UX.cim|G12|G12S'}
    ck('%s: HMI groups SIL EFFF／FtI／Vent per unit, unit = controller\'s unit' % SPEC_TAG, want <= set(pk['hmScreens']), pk['hmScreens'])
    s = ge_query(page, ctx, SPEC_TAG)
    ck('「%s」→ GE card (location test)' % SPEC_TAG, s['ge'] and s['tag'] == SPEC_TAG, s['tag'])
    page.wait_for_function("(() => { const l = document.querySelector('.ge-only .ge-loc'); return l && !/載入中/.test(l.textContent); })()", timeout=60000)
    page.wait_for_function("document.querySelector('.ge-loc .ge-pid img')", timeout=60000)
    page.wait_for_timeout(800)
    st = page.evaluate(LOC_STATE)
    ck('%s: location block has P&ID, HMI and location-drawing parts, placed before the spec blocks' % SPEC_TAG,
       bool(st) and st['heads'] == ['P&ID 圖面位置', '圖控 HMI 畫面位置', '位置圖位置（GE 配置／電纜槽／外型圖）'] and st['before'], st and (st['heads'], st['before']))
    ck('%s: P&ID sheet header names GFD01-D0005 Rev.3, PDF p.7, zone A-3, with a Drive link and a loaded image with marks' % SPEC_TAG,
       bool(st) and st['sheets'] and 'HT0-1-GFD01-D0005' in st['sheets'][0] and '第 7' in st['sheets'][0] and 'A-3' in st['sheets'][0]
       and any('drive.google.com' in h for h in st['pidLink']) and st['pidImg'] >= 1 and st['pidMk'] >= 1,
       st and (st['sheets'][:1], st['pidLink'][:1], st['pidImg'], st['pidMk']))
    ck('%s: HMI blocks show Excess Firing Fuel Flow with 機組 G11（控制器 G11S） and 機組 G12' % SPEC_TAG,
       bool(st) and any('Excess Firing Fuel Flow' in x and '機組 G11（控制器 G11S）' in x for x in st['screens'])
       and any('機組 G12（控制器 G12S）' in x for x in st['screens']) and not any('以選單機組' in x for x in st['screens']),
       st and st['screens'][:4])
    shot(page, ctx, 'getag_loc')
    held = page.evaluate("AMS.data.imagesHeld('card/pid/')")
    ck('%s: P&ID sheet image held (blob)' % SPEC_TAG, any('GFD01-D0005-3' in h for h in held), held)
    # 帶機組：只列那一台的圖控畫面
    s = ge_query(page, ctx, 'G12_' + SPEC_TAG)
    page.wait_for_function("(() => { const l = document.querySelector('.ge-only .ge-loc'); return l && !/載入中/.test(l.textContent); })()", timeout=60000)
    st = page.evaluate(LOC_STATE)
    ck('G12_%s: HMI blocks are all G12, P&ID still shown (sheet not unit-specific)' % SPEC_TAG,
       bool(st) and st['screens'] and all('機組 G12' in x for x in st['screens']) and st['sheets'], st and st['screens'][:3])
    # SIL 各頁共用的「最終元件」面板只列一張（hms）：VS4-4（SSOV）一部機 16 張 SIL 畫面同一個位置；它也在氣動閥清單，GE 對照接在閥卡下面
    ge_query(page, ctx, SIL_TAG)
    page.wait_for_function("(() => { const l = document.querySelector('.ge-below .ge-loc') || document.querySelector('.ge-only .ge-loc'); return l && !/載入中/.test(l.textContent); })()", timeout=60000)
    sl = page.evaluate("""() => { const g = document.querySelector('.ge-below') || document.querySelector('.ge-only'); if (!g) return null; const h = g.querySelector('.ge-hmi');
      return { notes: [...h.querySelectorAll('.aux-note')].map((x) => x.textContent), screens: [...h.querySelectorAll('.hmi-screen .hmi-t')].map((x) => x.textContent) }; }""")
    ck('%s: SIL panel repeated on many SIL screens is listed once per unit with a note naming the others' % SIL_TAG,
       bool(sl) and any('同一個面板也出現在另外' in n for n in sl['notes']) and sum(1 for t in sl['screens'] if t) <= 2 * 6,
       sl and (sl['notes'][:1], len(sl['screens'])))
    # 沒有任何位置的編號：兩塊都寫查無；換到這張卡時上一張的圖紙影像收掉
    if pk.get('none'):
        s = ge_query(page, ctx, pk['none'])
        page.wait_for_function("(() => { const l = document.querySelector('.ge-only .ge-loc'); return l && !/載入中/.test(l.textContent); })()", timeout=60000)
        st = page.evaluate(LOC_STATE)
        ck('%s (no location): both parts say 查無／沒有' % pk['none'], bool(st) and ('查無' in st['pidText'] or '沒有比對' in st['pidText'])
           and ('查無' in st['hmiText'] or '說明提到' in st['hmiText']) and not st['sheets'] and not st['screens'], st and (st['pidText'][:60], st['hmiText'][:60]))
        held = page.evaluate("AMS.data.imagesHeld('card/pid/')")
        ck('switching to a GE card without P&ID releases the sheet images', held == [], held)


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
