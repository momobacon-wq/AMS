# -*- coding: utf-8 -*-
"""GE 原廠編號（card aux 的 sec.getag＋04 位號索引的來源類型 8）：
搜尋（正式寫法 exact、不打連字號 compact、小寫加空白；頂列搜尋 Enter）開到那台設備；一個編號對到兩台時有切換按鈕；
設備組有「GE 原廠編號」一格（有值、有來源點），非 GE 設備沒有這格（hide_empty）；完整資料區有 GE 原廠編號段；
下拉建議打不帶連字號的前綴也列得出來；備品庫存的位號正規化不收 GE 列（tagSuggestSource 濾掉來源類型 8）；console 零錯誤。
測試用的 GE 編號一律從已發布的 04 挑，不寫死。"""
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
        ck('no page errors', not errors, errors[:3])
        ck('no console errors', not [m for t, m in console if t == 'error'], console[:3])
    return ck.fails
