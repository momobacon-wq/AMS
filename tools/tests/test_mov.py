# -*- coding: utf-8 -*-
"""電動閥清單（v26；db 站 62～68；tools/db/mov_site.py）：
側欄群組＋62 有 823 列、儀資組維護快速篩選 72 列；02.json mov 規格（位號索引、別名、分塊）與分塊內容不帶本機路徑／人名樣式；
電動閥卡（二、三號機）：欄位逐格來源、比照一號機代表位號、同一位置其他機組、signal-atlas 訊號；一號機有接線圖的閥：KKS 編號卡最上面多「電動閥」組；
G21／G22／G31／G32LBC32QN001 不再被 AMS 的模糊對應開成 G12LAF32QN001（深連結與頂列 Enter 都要）；別名（強／文件互相矛盾／定讞 S 機組碼／舊位號）；
只打本體列出各機組；C00LBG10QM412 與 C10LBG10QM412 是兩顆閥；清單沒收的位號說明理由；自動完成；手機無橫向捲動；console 零錯誤。"""
import re
from urllib.parse import quote
from e2e_common import Checks, browser, login, load_card, shot

GROUP = '電動閥清單'
ROWS = '.tv-win .tr'
MOV_READY = "document.querySelectorAll('.sum-mov .cf').length >= 30"

SPEC_JS = """async () => {
  const cm = AMS.data.sheets.find((s) => s.mode === 'card');
  const sp = await AMS.data.loadSheet(cm.id); const M = sp.mov || {};
  const out = { n_index: Object.keys(M.index || {}).length, n_list: (M.list || []).length, n_fields: (M.fields || []).length, files: (M.files || []).length,
    alias: Object.keys(M.alias || {}), out: Object.keys(M.out || {}).length, ge: M.ge || {} };
  const bad = /Users[\\\\/]{1,2}bacon|我的雲端硬碟|@@新機組|scratchpad|\\.claude[\\\\/]|\\([^()"]{1,6}整理\\)|_[^\\s_/\\\\"]{1,4}註解|主控親讀|\\bwf_[0-9a-f]{6,}/;
  out.spec_clean = !bad.test(JSON.stringify(M));
  out.chunks_clean = true; out.chunk_rows = 0;
  for (const f of M.files || []) { const j = await AMS.data.fetchJSON(f); out.chunk_rows += Object.keys(j.by_i || {}).length; if (bad.test(JSON.stringify(j))) { out.chunks_clean = false; out.bad_file = f; } }
  return out;
}"""
CARD_JS = """() => { const g = document.querySelector('.sum-mov'); if (!g) return null;
  return { n: g.querySelectorAll('.cf').length, src: g.querySelectorAll('.src-dot').length, hi: [...g.querySelectorAll('.sum-sigi.key')].map((e) => e.textContent.trim()),
    srcs: [...g.querySelectorAll('.src-dot')].map((b) => b.getAttribute('title') || ''), links: [...g.querySelectorAll('.ge-links a')].map((a) => a.textContent.trim()),
    sigHref: [...g.querySelectorAll('.ge-links a[target=_blank]')].map((a) => a.getAttribute('href')), alias: (g.querySelector('.mov-alias') || {}).textContent || '',
    row: !!g.querySelector('a.lk[href^="#/s/62"]'), status: document.querySelector('.cq-status').textContent, bad: document.querySelector('.cq-status').classList.contains('bad'),
    hero: (document.querySelector('.cq-body .sum-tagtext') || {}).textContent || '', first: (document.querySelector('.sum-groups > .sum-g') || {}).className || '' }; }"""


def count_of(page):
    m = re.search(r'顯示\s*([\d,]+)\s*/\s*總\s*([\d,]+)', page.locator('.tv-count').inner_text())
    return (int(m.group(1).replace(',', '')), int(m.group(2).replace(',', ''))) if m else (None, None)


def open_mov(page, ctx, q):
    page.goto(ctx['base'] + '/db/#/card/' + quote(q))
    page.wait_for_function(MOV_READY, timeout=60000)
    page.wait_for_timeout(300)
    return page.evaluate(CARD_JS)


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        login(page, ctx)
        ck('sidebar: 電動閥清單 group', page.locator('.sg-h[data-g="%s"]' % GROUP).count() == 1)
        for sid in ('62', '63', '64', '65', '66', '67', '68'):
            ck('sidebar: %s link' % sid, page.locator('.sheet-link[data-id="%s"]' % sid).count() == 1)
        # ---- 62 表格：823 列；儀資組維護＝是 72 列
        page.goto(ctx['base'] + '/db/#/s/62'); page.wait_for_selector(ROWS, timeout=60000); page.wait_for_timeout(400)
        n0, tot = count_of(page)
        ck('62: 823 rows (445 v1/v2 + 375 v3 + 3 v3.1)', tot == 823, (n0, tot))
        page.click('button.preset'); page.wait_for_timeout(900)
        n1, _ = count_of(page)
        ck('62: preset 儀資組維護＝是 → 72 rows', n1 == 72, n1)
        ck('62: 查詢卡 link cells', page.locator(ROWS + ' a.lk[href^="#/card/"]').count() >= 1)
        w = page.evaluate("(async () => { const j = await AMS.data.loadSheet('62'); return j.columns[2].w; })()")
        ck('62: 查詢卡 column is narrow (<= 120 px)', isinstance(w, (int, float)) and w <= 120, w)
        shot(page, ctx, 'mov_62')
        for sid, low in (('63', 40), ('64', 72), ('65', 100), ('66', 150), ('67', 30), ('68', 15)):
            page.goto(ctx['base'] + '/db/#/s/' + sid); page.wait_for_selector(ROWS, timeout=60000); page.wait_for_timeout(300)
            _, t = count_of(page)
            ck('%s: has rows (>= %d)' % (sid, low), (t or 0) >= low, t)
        sp = page.evaluate(SPEC_JS)
        ck('02.mov: 823 tags indexed, list 823, 43 card fields', sp['n_index'] == 823 and sp['n_list'] == 823 and sp['n_fields'] == 43, sp)
        ck('02.mov: chunk files cover all 823 rows', sp['chunk_rows'] == 823 and sp['files'] >= 5, (sp['chunk_rows'], sp['files']))
        ck('02.mov: aliases include S10MAC10QM021, G11HBK11QM001, G11LAB90QM003, C00LBG01QM412',
           all(k in sp['alias'] for k in ('S10MAC10QM021', 'G11HBK11QM001', 'G11LAB90QM003', 'C00LBG01QM412')), sp['alias'][:12])
        ck('02.mov: GE MOV-VBV-1／2 mapped', 'MOV-VBV-1' in sp['ge'] and 'MOV-VBV-2' in sp['ge'], sp['ge'])
        ck('02.mov + chunks: no local paths / person-name file / build jargon', sp['spec_clean'] and sp['chunks_clean'], sp.get('bad_file'))
        # ---- 電動閥卡（二號機）：欄位、來源、比照、其他機組、signal-atlas u2
        c = open_mov(page, ctx, 'G21LBA11QM004')
        ck('G21LBA11QM004: MOV card, 43 fields each with a source', c and c['n'] >= 43 and c['src'] >= 43 and c['hero'] == 'G21LBA11QM004', c and (c['n'], c['src'], c['hero']))
        ck('G21LBA11QM004: status not bad, says AMS／wiring only cover unit 1', c and not c['bad'] and '電動閥清單' in c['status'], c and c['status'])
        ck('G21LBA11QM004: cells borrowed from the unit-1 representative say 比照 G11LBA11QM004', c and any('比照 G11LBA11QM004' in s for s in c['srcs']), c and c['srcs'][:6])
        ck('G21LBA11QM004: signal-atlas u2 links (H21)', c and any('/signal-atlas/u2/#/v/H21.' in h for h in c['sigHref']), c and c['sigHref'][:3])
        ck('G21LBA11QM004: other units listed (G11, G12, G22, G31, G32)', c and all(any(t in x for x in c['links']) for t in ('G11LBA11QM004', 'G32LBA11QM004')), c and c['links'])
        ck('G21LBA11QM004: link to the 62 row', c and c['row'])
        shot(page, ctx, 'mov_card_g21')
        # ---- 一號機有接線圖的閥：KKS 編號卡，最上面是電動閥組
        c = open_mov(page, ctx, 'G11LBA11QM004')
        ck('G11LBA11QM004: KKS card keeps P&ID／wiring and the 電動閥 group comes first',
           c and page.locator('.kks-only').count() == 1 and 'sum-mov' in c['first'] and page.locator('.kks-only .sum-pid').count() == 1, c and c['first'])
        ck('G11LBA11QM004: signal-atlas u1 links (H11)', c and any('/signal-atlas/#/v/H11.' in h for h in c['sigHref']), c and c['sigHref'][:3])
        # ---- G2x／G3x LBC32QN001：不可被 HostTag「32QN001」開成 G12LAF32QN001（深連結）
        for t in ('G21LBC32QN001', 'G22LBC32QN001', 'G31LBC32QN001', 'G32LBC32QN001'):
            c = open_mov(page, ctx, t)
            ck('%s (deep link) → its own MOV card, not G12LAF32QN001' % t, c and c['hero'] == t and 'G12LAF32QN001' not in c['status'], c and (c['hero'], c['status'][:80]))
        # 頂列 Enter
        page.goto(ctx['base'] + '/db/#/s/62'); page.wait_for_selector(ROWS, timeout=60000)
        page.fill('#global-search', 'G31LBC32QN001'); page.keyboard.press('Enter')
        page.wait_for_function(MOV_READY, timeout=60000)
        ck('header Enter G31LBC32QN001 → URL keeps the typed tag', page.evaluate('location.hash') == '#/card/G31LBC32QN001', page.evaluate('location.hash'))
        # ---- 別名
        c = open_mov(page, ctx, 'G11HBK11QM001')
        ck('G11HBK11QM001 → KKS card + 電動閥 group of G11HNE11AA001 (alias 強)', c and 'G11HNE11AA001' in c['hi'] and '強' in c['alias'], c and (c['hi'], c['alias'][:60]))
        c = open_mov(page, ctx, 'G21HBK11QM001')
        ck('G21HBK11QM001 (no wiring card) → MOV card of G21HNE11AA001', c and c['hero'] == 'G21HNE11AA001' and 'HNE11AA001' in c['status'], c and (c['hero'], c['status'][:80]))
        c = open_mov(page, ctx, 'G11LAB90QM003')
        ck('G11LAB90QM003 → group of G11LAB91QM003 marked 文件互相矛盾', c and 'G11LAB91QM003' in c['hi'] and '文件互相矛盾' in c['alias'], c and (c['hi'], c['alias'][:60]))
        c = open_mov(page, ctx, 'C00LBG01QM412')
        ck('old number C00LBG01QM412 → C00LBG10QM412 (舊位號; that row has a wiring card → KKS card)', c and c['hero'] == 'C00LBG10QM412' and '舊位號' in c['status'] and page.locator('.kks-only').count() == 1,
           c and (c['hero'], c['status'][:80]))
        c = open_mov(page, ctx, 'C10LBA13QM402-BG001')
        ck('C10LBA13QM402-BG001 → the KKS card of C10LBA13QM402 (not a MOV card saying there is no wiring)', c and c['hero'] == 'C10LBA13QM402' and page.locator('.kks-only').count() == 1, c and (c['hero'], c['status'][:80]))
        c = open_mov(page, ctx, 'G11HNE11AA001')
        ck('G11HNE11AA001: MOV card names the wiring-card spelling G11HBK11QM001 and links it',
           c and '接線圖上寫成 G11HBK11QM001' in c['status'] and page.locator('.mov-only .valve-ams a[href="#/card/G11HBK11QM001"]').count() == 1, c and c['status'][:120])
        # ---- 真空破壞閥：清單寫 C 機組碼、GE／控制器寫 S 或不寫機組碼
        c = open_mov(page, ctx, 'C10MAC10QM021')
        ck('C10MAC10QM021: GE chip MOV-VBV-1 and S1 signals', c and any(x.startswith('MOV-VBV-1') for x in c['links']) and any('/#/v/S1.' in h for h in c['sigHref']), c and c['links'])
        c = open_mov(page, ctx, 'S10MAC10QM021')
        ck('S10MAC10QM021 → GE card with the 電動閥 group', c and page.locator('.ge-only').count() >= 1 and 'C10MAC10QM021' in c['hi'], c and c['hi'])
        c = open_mov(page, ctx, 'S20MAC10QM021')
        ck('S20MAC10QM021 → GE card lists only C20MAC10QM021 with the 定讞 note', c and c['hi'] == ['C20MAC10QM021'] and '定讞' in c['alias'], c and (c['hi'], c['alias'][:40]))
        # ---- 只打本體 → 各機組
        page.goto(ctx['base'] + '/db/#/card/LBA11QM004'); page.wait_for_selector('.mov-only', timeout=60000)
        chips = page.evaluate("[...document.querySelectorAll('.mov-only .valve-ams a')].map(a => a.textContent)")
        ck('core LBA11QM004 → 6 unit chips', len(chips) == 6, chips)
        page.goto(ctx['base'] + '/db/#/card/HBK11QM001'); page.wait_for_selector('.mov-only', timeout=60000)
        chips = page.evaluate("[...document.querySelectorAll('.mov-only .valve-ams a')].map(a => a.textContent)")
        ck('core of the DCS spelling HBK11QM001 → the 6 HNE11AA001 dampers', len(chips) == 6 and all('HNE11AA001' in x for x in chips), chips)
        # ---- 推論等級的別名：KKS 卡上電動閥組排在接線路徑之後
        c = open_mov(page, ctx, 'G11LAE60QM001')
        ck('G11LAE60QM001 (推論) → KKS card with the 電動閥 group after the wiring group',
           c and page.evaluate("(() => { const k = [...document.querySelector('.sum-groups').children]; const w = k.findIndex(e => e.classList.contains('sum-wire')), m = k.findIndex(e => e.classList.contains('sum-mov')); return w >= 0 && m > w; })()"),
           c and c['first'])
        # ---- 出處：比照一號機的扭力設定是推論；兩讀格標「兩讀」；載重表的 xlsx 連結開的是那份 xlsx
        c = open_mov(page, ctx, 'C20GHC35QM002')
        lv = page.evaluate("(() => { const f = [...document.querySelectorAll('.sum-mov .cf')].find(e => e.querySelector('.cf-k').textContent.startsWith('扭力設定 開')); return f ? f.querySelector('.src-dot').className : ''; })()")
        ck('C20GHC35QM002 扭力設定 開 (比照 unit-1 certificate) is badged 推論', 'lvl-inferred' in lv, lv)
        c = open_mov(page, ctx, 'C10GHC70QM001')
        ck('C10GHC70QM001: 兩讀 cell flagged and counted in the header', page.locator('.sum-mov .sum-sigh .pill.warn').count() >= 1 and page.locator('.sum-mov .cmp-flag.warn').count() >= 1,
           page.locator('.sum-mov .sum-sigh').inner_text()[:120])
        c = open_mov(page, ctx, 'G11EKT50QM007')
        t = page.evaluate("(() => { const f = [...document.querySelectorAll('.sum-mov .cf')].find(e => e.querySelector('.cf-k').textContent === '閥門名稱（中文）'); const a = f && f.querySelector('a.doclk'); return a ? a.title : ''; })()")
        ck('G11EKT50QM007 name cites the loadlist xlsx; its link opens that xlsx, not the C0001-3 PDF', ('attachment.xlsx' in t.lower() and 'Protection' not in t) or t == '', t)
        # ---- C00LBG10QM412 與 C10LBG10QM412 是兩顆閥（同一位置的其他機組不互列）
        c = open_mov(page, ctx, 'C00LBG10QM412')
        ck('C00LBG10QM412: other-units list does not include C10LBG10QM412', c and not any('C10LBG10QM412' in x for x in c['links']), c and c['links'])
        c = open_mov(page, ctx, 'C10LBG10QM412')
        ck('C10LBG10QM412: other units are C20／C30, not C00', c and any('C20LBG10QM412' in x for x in c['links']) and not any('C00LBG10QM412' in x for x in c['links']), c and c['links'])
        # ---- 清單沒收的位號：說明理由（也不可被 AMS 的模糊對應開到別台）
        page.goto(ctx['base'] + '/db/#/card/C10LBG22QM402'); page.wait_for_selector('.csec.nf', timeout=60000)
        st = page.locator('.cq-status').inner_text()
        ck('C10LBG22QM402 (deleted, not listed) → status says why', '電動閥清單沒有收' in st and '已刪除' in st, st[:120])
        page.goto(ctx['base'] + '/db/#/card/G11LAB50QM002'); page.wait_for_selector('.csec.nf', timeout=60000)
        st = page.locator('.cq-status').inner_text()
        ck('G11LAB50QM002 (manual valve, not listed) → reason, not the AMS transmitter G11LAB50BP001', '手動閥' in st and 'G11LAB50BP001' not in st, st[:120])
        c = page.goto(ctx['base'] + '/db/#/card/C10LBG21QM432'); page.wait_for_selector('.kks-only', timeout=60000); page.wait_for_timeout(500)
        ck('C10LBG21QM432 (DCS terminal-list KKS card) shows the 沒有收 reason', page.locator('.kks-only .mov-alias').count() == 1 and '沒有收' in page.locator('.kks-only .mov-alias').inner_text())
        # ---- 查無頁：只有電動閥清單有相近的 → 列在最前面
        page.goto(ctx['base'] + '/db/#/card/G21LBA11QM00'); page.wait_for_selector('.csec.nf', timeout=60000)
        ck('partial G21LBA11QM00 → status names 電動閥清單 and its chips come first',
           '電動閥清單' in page.locator('.cq-status').inner_text() and page.evaluate("(() => { const b = document.querySelector('.nf-body'); return !!b && b.firstElementChild && b.firstElementChild.classList.contains('nf-movs'); })()"),
           page.locator('.cq-status').inner_text()[:100])
        # ---- 訊號尾碼
        c = open_mov(page, ctx, 'G21LBA11QM004XB61')
        ck('G21LBA11QM004XB61 → G21LBA11QM004', c and c['hero'] == 'G21LBA11QM004', c and c['hero'])
        # ---- 自動完成
        AC = "[...document.querySelectorAll('.ac-hint')].some(e => e.offsetParent && e.textContent.includes('電動閥清單'))"
        page.goto(ctx['base'] + '/db/#/s/62'); page.wait_for_selector(ROWS, timeout=60000)
        page.fill('#global-search', ''); page.click('#global-search'); page.keyboard.type('G21LBA11', delay=20)
        try:
            page.wait_for_function(AC, timeout=15000); ok = True
        except Exception:
            ok = False
        ck('autocomplete G21LBA11 lists 電動閥清單 items', ok)
        page.keyboard.press('Escape'); page.fill('#global-search', '')
        ck('console: zero errors', not errors, errors[:5])
    # ---- 手機寬度：無橫向捲動
    with browser(ctx, mobile=True) as (page, errors, console):
        login(page, ctx)
        open_mov(page, ctx, 'G22LBA11QM004')
        ck('mobile: MOV card has no horizontal scroll', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'),
           page.evaluate('[document.documentElement.scrollWidth, window.innerWidth]'))
        shot(page, ctx, 'mov_mobile')
        ck('mobile console: zero errors', not errors, errors[:5])
    return ck.fails
