# -*- coding: utf-8 -*-
"""氣動閥清單（db 站 57～61；tools/db/pneuvalve_site.py）：
側欄群組＋57 有列、搜尋過濾；AMS 設備卡片的「氣動閥」摘要組（逐格出處、開啟清單列連結）；
帶機組的清單位號（G11…）→ 直接顯示對應的 AMS 設備；只在清單的位號 → 閥卡（不是「查無」）；頂列搜尋同樣；
文件全文檢索組仍在最後（test_card 的不變條件）；手機無橫向捲動；console 零錯誤。測試用位號一律從 02.json valve 規格挑，不寫死。"""
import re
from urllib.parse import quote
from e2e_common import Checks, browser, login, load_card, shot

GROUP = '氣動閥清單'
ROWS = '.tv-win .tr'
VALVE_READY = "document.querySelectorAll('.sum-valve .cf').length >= 5"

PICK_JS = """async () => {
  const cm = AMS.data.sheets.find((s) => s.mode === 'card');
  const sp = await AMS.data.loadSheet(cm.id); const V = sp.valve || {};
  await AMS.index.load(); await AMS.devices.load();
  const IX = AMS.index;
  const out = { n_alias: Object.keys(V.by_alias || {}).length };
  for (const [al, list] of Object.entries(V.by_alias || {})) { if (!out.alias) out.alias = al; if (!out.ge && /GE 舊位號/.test(list[0][3])) out.ge = { alias: al, unit: list[0][2], sid: String(list[0][0]), row: list[0][1] }; }
  if (out.ge) { const j = await AMS.data.loadSheet(out.ge.sid); const tc = j.columns.findIndex((c) => c.label === 'Valve Tag No.'); out.ge.tag = out.ge.unit + String(j.rows[out.ge.row][tc]).slice(3); }
  const used = new Set(); for (const list of Object.values(V.by_alias || {})) for (const e of list) used.add(e[0] + ':' + e[1]);
  for (const [k, e] of Object.entries(V.index || {})) {
    if (used.has(e[0] + ':' + e[1])) continue;
    const rs = IX.resolve(k);
    if (rs.how !== 'exact' && rs.how !== 'compact') { out.only = k; break; }
  }
  return out;
}"""


def count_of(page):
    m = re.search(r'顯示\s*([\d,]+)\s*/\s*總\s*([\d,]+)', page.locator('.tv-count').inner_text())
    return (int(m.group(1).replace(',', '')), int(m.group(2).replace(',', ''))) if m else (None, None)


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        login(page, ctx)
        ck('sidebar: 氣動閥清單 group', page.locator('.sg-h[data-g="%s"]' % GROUP).count() == 1)
        for sid in ('57', '58', '59', '60', '61'):
            ck('sidebar: %s link' % sid, page.locator('.sheet-link[data-id="%s"]' % sid).count() == 1)
        # ---- 57 表格
        page.goto(ctx['base'] + '/db/#/s/57'); page.wait_for_selector(ROWS, timeout=60000); page.wait_for_timeout(400)
        n0, tot = count_of(page)
        ck('57: total rows > 300', (tot or 0) > 300, (n0, tot))
        page.fill('.tv-q', 'MBP01'); page.wait_for_timeout(900)
        n1, _ = count_of(page)
        ck('57 search filters', n1 is not None and 1 <= n1 < tot, (n1, tot))
        ck('57: AMS link cells present', page.locator(ROWS + ' a.lk[href^="#/card/"]').count() >= 1)
        shot(page, ctx, 'pneu_57')
        pk = page.evaluate(PICK_JS)
        ck('valve spec: aliases mapped (>50)', pk.get('n_alias', 0) > 50, pk)
        # ---- AMS 設備卡片：氣動閥摘要組
        if pk.get('alias'):
            load_card(page, ctx, pk['alias'])
            page.wait_for_function(VALVE_READY, timeout=30000)
            v = page.evaluate("""() => { const g = document.querySelector('.sum-valve');
              return { n: g.querySelectorAll('.cf').length, src: g.querySelectorAll('.src-dot').length,
                       row: !!g.querySelector('a.lk[href^="#/s/5"]'), title: g.querySelector('.sum-gh').textContent }; }""")
            ck('card: 氣動閥 group has fields', v['n'] >= 10, v)
            ck('card: fields carry sources', v['src'] >= 5, v)
            ck('card: link to list row', v['row'], v)
            ck('card: after_stock 兩組仍在最後（文件全文檢索 → 圖控 HMI）',
               page.evaluate("(s => !s || s.nextElementSibling === document.querySelector('.sum-hmi'))(document.querySelector('.sum-search'))")
               and page.evaluate("(h => !h || h === h.parentElement.lastElementChild)(document.querySelector('.sum-hmi'))"))
            shot(page, ctx, 'pneu_card')
        # ---- 非氣動閥設備：沒有氣動閥組
        load_card(page, ctx, 'G12HAP70BT001')
        ck('transmitter card: no 氣動閥 group', page.locator('.sum-valve').count() == 0)
        # ---- 帶機組的清單位號 → 對應 AMS 設備
        if pk.get('ge'):
            page.goto(ctx['base'] + '/db/#/card/' + quote(pk['ge']['tag']))
            page.wait_for_function(VALVE_READY, timeout=60000); page.wait_for_timeout(300)
            st = page.locator('.cq-status').inner_text()
            ck('unit valve tag → AMS device card', '氣動閥清單位號' in st and page.locator('.sum-tagtext').count() == 1, (pk['ge'], st))
        # ---- 只在清單的位號 → 閥卡
        ck('picked a valve-only tag', bool(pk.get('only')), pk)
        if pk.get('only'):
            page.goto(ctx['base'] + '/db/#/card/' + quote(pk['only']))
            page.wait_for_selector('.valve-only', timeout=60000)
            page.wait_for_function(VALVE_READY, timeout=30000)
            ck('valve-only: status not bad', 'bad' not in (page.get_attribute('.cq-status', 'class') or ''), page.locator('.cq-status').inner_text())
            ck('valve-only: no 查無 section', page.locator('.csec.nf').count() == 0)
            shot(page, ctx, 'pneu_valve_only')
            # 頂列搜尋：同一個位號
            page.goto(ctx['base'] + '/db/#/s/57'); page.wait_for_selector(ROWS, timeout=60000)
            page.fill('#global-search', pk['only']); page.keyboard.press('Enter')
            page.wait_for_selector('.valve-only', timeout=30000)
            ck('header search: valve-only tag opens valve card', page.evaluate('location.hash').startswith('#/card/'), page.evaluate('location.hash'))
        ck('no page errors', not errors, errors[:3])
        ck('no console errors/warnings', not console, console[:3])
    with browser(ctx, mobile=True) as (page, errors, console):
        login(page, ctx)
        page.goto(ctx['base'] + '/db/#/s/57'); page.wait_for_selector(ROWS, timeout=60000); page.wait_for_timeout(400)
        w = page.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
        ck('mobile 57: no horizontal page scroll', w['sw'] <= w['cw'], w)
        pk = page.evaluate(PICK_JS)
        if pk.get('only'):
            page.goto(ctx['base'] + '/db/#/card/' + quote(pk['only']))
            page.wait_for_function(VALVE_READY, timeout=60000); page.wait_for_timeout(300)
            w = page.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
            ck('mobile valve-only card: no horizontal page scroll', w['sw'] <= w['cw'], w)
            shot(page, ctx, 'pneu_mobile_valve')
        ck('mobile: no page errors', not errors, errors[:3])
    return ck.fails
