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
  out.shape = Object.values(V.index || {}).every((e) => Array.isArray(e) && e.every((x) => Array.isArray(x) && x.length === 2));
  out.n_list = (V.list || []).length;
  for (const [k, e] of Object.entries(V.index || {})) {
    if (e.length > 1 && !out.multi) out.multi = { key: k, n: e.length };
    if (e.some((x) => used.has(x[0] + ':' + x[1]))) continue;
    const rs = IX.resolve(k);
    if (!out.only && rs.how !== 'exact' && rs.how !== 'compact') out.only = k;
  }
  // GE 舊位號／別名（清單列的別名，不是位號本身）：AMS 沒有設備、位號索引完全查不到的那種（VA13-25 型）
  for (const it of V.list || []) {
    if (used.has(it[0] + ':' + it[1])) continue;
    const a = (it[3] || []).find((x) => /^V[A-Z]*\\d*-\\d+$/.test(x) && IX.resolve(x).how === 'none');
    if (a) { out.ge_alias = { alias: a, tag: it[2], zh: it[4] }; break; }
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
            ck('unit valve tag → AMS device card', '氣動閥清單' in st and '對應 AMS 設備' in st and page.locator('.sum-tagtext').count() == 1, (pk['ge'], st))
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
        # ---- GE 舊位號／別名（2026-10-03：查 VA13-25 找不到）：索引一鍵多列、別名 → 閥卡、機組前綴寫法、自動完成、查無頁建議
        ck('valve.index values are [[sid,row],…]; valve.list covers every row', pk.get('shape') and pk.get('n_list', 0) > 900, (pk.get('shape'), pk.get('n_list')))
        ga = pk.get('ge_alias')
        ck('picked a GE-legacy alias with no AMS key', bool(ga), pk)
        if ga:
            for form in (ga['alias'], '90' + ga['alias'], 'G11_90' + ga['alias'], ga['alias'].lower().replace('-', ' ')):
                page.goto(ctx['base'] + '/db/#/card/' + quote(form))
                page.wait_for_selector('.valve-only .sum-sigi.key', timeout=60000)
                tags = page.evaluate("[...document.querySelectorAll('.valve-only .sum-sigi.key')].map(e => e.textContent.trim())")
                ck('alias form %r → valve card of %s' % (form, ga['tag']), ga['tag'] in tags and 'bad' not in (page.get_attribute('.cq-status', 'class') or ''), tags)
            shot(page, ctx, 'pneu_alias')
            # 自動完成（頂列）：打別名前 4 個字／帶機組的寫法 → 下拉有「氣動閥清單」項目
            AC_VALVE = "[...document.querySelectorAll('.ac-hint')].some(e => e.offsetParent && e.textContent.includes('氣動閥清單'))"
            page.goto(ctx['base'] + '/db/#/s/57'); page.wait_for_selector(ROWS, timeout=60000)
            for typed in (ga['alias'][:4], 'G11_90' + ga['alias'][:-1]):
                page.fill('#global-search', ''); page.click('#global-search'); page.keyboard.type(typed, delay=20)
                try:
                    page.wait_for_function(AC_VALVE, timeout=15000); ok = True
                except Exception:
                    ok = False
                ck('autocomplete %r lists 氣動閥清單 items' % typed, ok)
                page.keyboard.press('Escape')
            page.fill('#global-search', '')
        # ---- 以下用 JS 直接問 AMS.valves（資料相依的挑選都在這裡；挑不到就記一筆 FAIL，不默默略過）
        probe = page.evaluate("""async () => {
          const V = await AMS.valves.load(); const IX = AMS.index; const VS = AMS.valves; const o = {};
          const sp = await AMS.data.loadSheet(AMS.data.sheets.find((s) => s.mode === 'card').id);
          // (1) 不是鍵的前綴：位號索引沒有唯一對應、氣動閥清單也沒命中，但有建議 → 查無頁要有閥 chips
          for (const it of V.list) { for (const a of it[3] || []) { const p = a.slice(0, -1);
            if (p.length >= 4 && !VS.hit(V, p, 0) && !IX.resolve(p).key && VS.suggest(V, p, 12).length) { o.nf = p; break; } } if (o.nf) break; }
          // (2) 一鍵多列、列分屬不同機組類別（LCV-3461：GT＋ST）→ 帶機組只剩一列
          for (const [k, e] of Object.entries(V.index)) { if (e.length < 2) continue;
            const us = e.map((x) => (VS.item(V, x[0], x[1]) || [])[6] || []);
            const u0 = us[0].find((u) => us.slice(1).every((o2) => !o2.includes(u)));
            if (u0 && !/[A-Z]{3}\\d\\d[A-Z]{2}\\d{3}/.test(k)) { const h = VS.hit(V, u0 + '_' + k, 0); o.multi = { key: k, n: e.length, unit: u0, got: h ? h.ents.length : 0, via: h && h.via }; break; } }
          // (3) 清單不涵蓋的機組 → via unit-other（不可說成清單位號）
          for (const it of V.list) { const us = it[6] || []; if (!us.length || us.length > 2 || !/^G/.test(us[0])) continue;
            const core = VS.core(it[2]); const u = ['G11', 'G12', 'G21', 'G22', 'G31', 'G32'].find((x) => !us.includes(x));
            if (u && !IX.resolve(u + core).key) { const h = VS.hit(V, u + core, 0); o.other = { q: u + core, via: h && h.via }; break; } }
          // (4) 只打數字機組（11HAD10QN005 型）：AMS 模糊對應到這顆閥自己的設備 → 照舊開 AMS 設備
          for (const [al, list] of Object.entries(V.by_alias)) { const i3 = AMS.devices.byAlias.get(al); if (i3 == null) continue;
            const tag = String(AMS.devices.sheet.rows[i3][0]); if (!/^[GC]\\d\\d[A-Z]{3}\\d\\d[A-Z]{2}\\d{3}$/.test(tag)) continue;
            const q = tag.slice(1); const rs = IX.resolve(q); if (!rs.key || (rs.how !== 'contain' && rs.how !== 'suggest')) continue;
            const r5 = IX.sheet.rows[IX.first.get(rs.key)]; if (String(r5[sp.lookup.alias_col]) !== al) continue;
            o.numunit = { q, tag }; break; }
          // (4b) 姊妹機組：清單列涵蓋 U2、AMS 只有 U1 那台，而位號索引對 U2 位號有模糊對應（HostTag 片段）→ 不可開 U1 的設備
          for (const it of V.list) { const us = it[6] || []; const core = VS.core(it[2]);
            const devs = Object.entries(V.by_alias).filter(([, l]) => l.some((e) => String(e[0]) === String(it[0]) && e[1] === it[1])).map(([, l]) => l[0][2]);
            if (devs.length !== 1) continue;
            const u2 = us.find((u) => u !== devs[0] && IX.resolve(u + core).key && ['contain', 'suggest'].includes(IX.resolve(u + core).how));
            if (u2) { o.sibling = { q: u2 + core, has: devs[0] }; break; } }
          // (5) 備品庫存的 KKS 正規化只認 AMS 位號：氣動閥別名不可被改寫成 Gxx 位號或「n 列」
          const ms = Object.entries(V.index).find(([k, e]) => e.length > 1 && !IX.resolve(k).key && !/[A-Z]{3}\\d\\d[A-Z]{2}\\d{3}/.test(k));
          if (ms) { const src = await AMS.tagSuggestSource.fetch(ms[0]); o.stock = { key: ms[0], leak: src.filter((x) => x.src === '氣動閥清單').length };
            const v = VS.suggest(V, ms[0], 12)[0]; o.rowsTag = v ? { tag: v.tag, rows: v.rows } : null; }
          // (6) manifest 還沒載就呼叫 load()：不可把「沒有」記住
          const keep = AMS.data.sheets; VS._p = null; AMS.data.sheets = [];
          const early = await VS.load(); AMS.data.sheets = keep; const late = await VS.load();
          o.early = early == null; o.late = !!(late && late.index);
          // (7) AMS 建議不被擠掉
          o.amsSlots = (await AMS.searchSuggestSource.fetch('G11HAD')).filter((x) => x.src !== '氣動閥清單').length;
          return o; }""")
        ck('picked a non-key prefix with valve suggestions', bool(probe.get('nf')), probe)
        if probe.get('nf'):
            page.goto(ctx['base'] + '/db/#/card/' + quote(probe['nf']))
            page.wait_for_selector('.csec.nf', timeout=60000)
            ck('not-found: valve chips + links to 57/58', page.locator('.csec.nf .nf-valves a.chip-btn').count() >= 1
               and page.locator('.csec.nf a.lk[href^="#/s/57?q="]').count() == 1 and page.locator('.csec.nf a.lk[href^="#/s/58?q="]').count() == 1, probe['nf'])
        mu = pk.get('multi')
        ck('picked a multi-row key', bool(mu), pk)
        if mu:
            page.goto(ctx['base'] + '/db/#/card/' + quote(mu['key']))
            page.wait_for_selector('.valve-only .sum-sigi.key, .csec.sum .sum-tagtext', timeout=60000); page.wait_for_timeout(500)
            n = page.locator('.valve-only .sum-sig').count() if page.locator('.valve-only').count() else None
            ck('multi-row key shows every row (or its own AMS device)', n is None or n == mu['n'], (mu, n))
        m2 = probe.get('multi')
        ck('unit prefix keeps only rows covering that unit', bool(m2) and m2['via'] == 'unit' and 1 <= m2['got'] < m2['n'], m2)
        ot = probe.get('other')
        ck('uncovered unit → via unit-other', bool(ot) and ot['via'] == 'unit-other', ot)
        if ot and ot['via'] == 'unit-other':
            page.goto(ctx['base'] + '/db/#/card/' + quote(ot['q']))
            page.wait_for_selector('.valve-only .sum-sigi.key', timeout=60000)
            st = page.locator('.cq-status').inner_text()
            ck('uncovered unit: status says the list does not cover it', '只涵蓋' in st and '是氣動閥清單位號' not in st, st)
        nu = probe.get('numunit')
        ck('picked a numeric-unit query', bool(nu), probe)
        if nu:
            page.goto(ctx['base'] + '/db/#/card/' + quote(nu['q']))
            page.wait_for_function(VALVE_READY, timeout=60000)
            ck('numeric-unit KKS still opens its AMS device', page.locator('.valve-only').count() == 0 and page.locator('.sum-tagtext').inner_text() == nu['tag'], nu)
        sb = probe.get('sibling')
        ck('picked a sibling-unit query', bool(sb), probe)
        if sb:
            for form in (sb['q'], sb['q'] + '.PV'):
                page.goto(ctx['base'] + '/db/#/card/' + quote(form))
                page.wait_for_selector('.valve-only .sum-sigi.key', timeout=60000)
                st = page.locator('.cq-status').inner_text()
                ck('sibling unit %r: valve card, not the other unit\'s AMS device' % form, '同型閥在其他機組' in st, st)
        ck('stock KKS source is AMS-only', bool(probe.get('stock')) and probe['stock']['leak'] == 0, probe.get('stock'))
        rt = probe.get('rowsTag')
        ck('multi-row suggestion keeps a real tag (rows is separate)', bool(rt) and (rt.get('rows') or 0) > 1 and '列' not in (rt.get('tag') or ''), rt)
        ck('valves.load() before manifest is not memoized', probe.get('early') and probe.get('late'), (probe.get('early'), probe.get('late')))
        if ga and ga.get('zh'):
            zq = ''.join(re.findall(r'[一-鿿]+', ga['zh'])[:1])[:3]
            n = page.evaluate("(q) => AMS.valves.suggest(AMS.valves.V, q, 12).filter(x => x.m === 'name').length", zq)
            ck('suggest by 中文名', len(zq) >= 2 and n >= 1, zq)
        ck('AMS suggestions keep ≥8 slots', probe.get('amsSlots', 0) >= 8, probe.get('amsSlots'))
        # ---- 打錯字建議（只列出、不自動開）＋表格搜尋不分分隔符
        tp = page.evaluate("""async () => {
          const V = await AMS.valves.load(); const IX = AMS.index; const VS = AMS.valves; const o = {};
          const SW = { 5: 'S', 0: 'O', 1: 'I', 8: 'B', 2: 'Z' };
          const clean = async (t) => !VS.hit(V, t, 0) && !IX.resolve(t).key && !IX.suggest(t, 12).length && !VS.suggest(V, t, 12).length;
          // (a) 氣動閥別名把最後一個易混數字打成字母（VA13-25 → VA13-2S）
          for (const it of V.list) { for (const a of it[3] || []) { const m = /^(.*-.*)([50182])([^50182]*)$/.exec(a);
            if (!m || IX.compact(a).length < 5) continue; const t = m[1] + SW[m[2]] + m[3];
            if (await clean(t)) { o.valve = { typed: t, want: a, got: AMS.fuzzy(V, t, 8).map((x) => x.key), src: (await AMS.searchSuggestSource.fetch(t)).map((x) => x.m + ':' + x.key), stock: (await AMS.tagSuggestSource.fetch(t)).length }; break; } }
            if (o.valve) break; }
          // (b) AMS 位號把一個 0 打成 O
          for (const k of IX.keys) { if (!/^[GC]\\d\\d[A-Z]{3}\\d\\d[A-Z]{2}\\d{3}$/.test(k)) continue; const i = k.lastIndexOf('0'); if (i < 0) continue;
            const t = k.slice(0, i) + 'O' + k.slice(i + 1);
            if (await clean(t)) { o.ams = { typed: t, want: k, got: AMS.fuzzy(V, t, 8).map((x) => x.key) }; break; } }
          // (c) 有開頭相符的建議時不用相近鍵；太短／無關字串沒有相近鍵
          const pre = V.list.map((it) => (it[3] || [])[0]).find((a) => a && IX.compact(a).length >= 5);
          o.pre = pre ? (await AMS.searchSuggestSource.fetch(pre.slice(0, 4))).filter((x) => x.m === 'fuzzy').length : -1;
          o.junk = AMS.fuzzy(V, 'XYZQ9999', 8).length + AMS.fuzzy(V, 'AB1', 8).length;
          // (c2) 四位數／短儀表號不該撈出一堆數字鍵；去分隔符就對得到的鍵列它自己、不列相近鍵；每列只出一筆
          o.noise = AMS.fuzzy(V, '1996', 8).length + AMS.fuzzy(V, 'LS-11', 8).length;
          const ck = IX.keys.find((k) => /^[GC]\d\d[A-Z]{3}\d\d[A-Z]{2}\d{3}$/.test(k));
          if (ck) { const t = ck.slice(0, 3) + '-' + ck.slice(3, 8) + '-' + ck.slice(8); o.sepKey = { typed: t, want: ck, src: (await AMS.searchSuggestSource.fetch(t)).map((x) => (x.m || '') + ':' + x.key) }; }
          const fzAll = []; for (const it of V.list.slice(0, 300)) { const a = (it[3] || [])[0]; if (!a) continue; const r = AMS.fuzzy(V, 'G11_' + a + 'X', 12); const rows = r.filter((x) => x.valve).map((x) => x.valve.join(':')); if (new Set(rows).size !== rows.length) fzAll.push(a); }
          o.dupRows = fzAll.length;
          // (d) 表格搜尋：有分隔符的別名去掉分隔符
          for (const it of V.list) { if (String(it[0]) !== '57') continue; const a = (it[3] || []).find((x) => /[A-Z]/.test(x) && /\\d/.test(x) && /-/.test(x) && IX.compact(x).length >= 5);
            if (a) { o.sep = { alias: a, compact: IX.compact(a) }; break; } }
          return o; }""")
        tv = tp.get('valve')
        ck('typo: picked a mistyped valve alias', bool(tv), tp)
        if tv:
            ck('typo: fuzzy lists the intended alias', tv['want'] in tv['got'], tv)
            ck('typo: dropdown items are marked fuzzy; stock source stays empty', bool(tv['src']) and all(x.startswith('fuzzy:') for x in tv['src']) and tv['stock'] == 0, tv)
            page.goto(ctx['base'] + '/db/#/s/57'); page.wait_for_selector(ROWS, timeout=60000)
            page.fill('#global-search', ''); page.click('#global-search'); page.keyboard.type(tv['typed'], delay=20)
            try:
                page.wait_for_function("[...document.querySelectorAll('.ac-hint')].some(e => e.offsetParent && e.textContent.includes('相近'))", timeout=15000); ok = True
            except Exception:
                ok = False
            ck('typo: autocomplete shows 相近 items', ok, tv['typed'])
            page.keyboard.press('Escape'); page.click('#global-search'); page.keyboard.press('Enter')
            page.wait_for_selector('.csec.nf', timeout=60000)
            chips = page.locator('.csec.nf .nf-fuzzy a.chip-btn .mono').all_inner_texts()
            ck('typo: Enter does not auto-open; not-found page lists the intended key', tv['typed'] in page.evaluate('decodeURIComponent(location.hash)') and tv['want'] in chips, chips)
        ta = tp.get('ams')
        ck('typo: picked a mistyped AMS tag', bool(ta), tp)
        if ta:
            ck('typo: fuzzy lists the intended AMS tag first', bool(ta['got']) and ta['got'][0] == ta['want'], ta)
        ck('typo: no fuzzy items when prefix suggestions exist', tp.get('pre') == 0, tp.get('pre'))
        ck('typo: unrelated / short strings get nothing', tp.get('junk') == 0, tp.get('junk'))
        ck('typo: 4-digit numbers / short instrument tags get no numeric-key noise', tp.get('noise') == 0, tp.get('noise'))
        sk = tp.get('sepKey')
        ck('typo: a key typed with extra separators lists that key itself, not neighbours', bool(sk) and sk['src'] == [':' + sk['want']], sk)
        ck('typo: one suggestion per valve row', tp.get('dupRows') == 0, tp.get('dupRows'))
        sp = tp.get('sep')
        ck('table search: picked an alias with a separator', bool(sp), tp)
        if sp:
            COUNT = "() => { const m = /顯示\\s*([\\d,]+)/.exec(document.body.innerText); return m ? Number(m[1].replace(/,/g, '')) : -1; }"
            n = {}
            for q in (sp['alias'], sp['compact'], sp['alias'].replace('-', ' ').lower()):
                page.goto(ctx['base'] + '/db/#/s/57?q=' + quote(q)); page.wait_for_selector('.tv-q', timeout=60000); page.wait_for_timeout(1200)
                n[q] = page.evaluate(COUNT)
            ck('table search ignores separators (- _ space)', n[sp['alias']] >= 1 and all(v >= n[sp['alias']] for v in n.values()), n)
            page.goto(ctx['base'] + '/db/#/s/57?q=' + quote('zq9zq9')); page.wait_for_selector('.tv-q', timeout=60000); page.wait_for_timeout(800)
            ck('table search: nonsense still finds nothing', page.evaluate(COUNT) in (0, -1), page.evaluate(COUNT))
        ck('no page errors', not errors, errors[:3])
        ck('no console errors/warnings', not console, console[:3])
    with browser(ctx, mobile=True) as (page, errors, console):
        login(page, ctx)
        page.goto(ctx['base'] + '/db/#/s/57'); page.wait_for_selector(ROWS, timeout=60000); page.wait_for_timeout(400)
        w = page.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
        ck('mobile 57: no horizontal page scroll', w['sw'] <= w['cw'], w)
        # 頂列搜尋框：平常看得到至少十來個字；聚焦時其餘按鈕讓位、佔滿整列；離開後復原
        GW = """() => { const g = document.querySelector('#global-search'); const cs = getComputedStyle(g);
          return { text: Math.round(g.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)), vw: innerWidth,
            brand: !!document.querySelector('.brand').offsetParent, over: document.documentElement.scrollWidth > innerWidth }; }"""
        g0 = page.evaluate(GW)
        ck('mobile header search: idle text width ≥ 100px', g0['text'] >= 100 and g0['brand'] and not g0['over'], g0)
        page.click('#global-search'); page.keyboard.type('VA', delay=20); page.wait_for_timeout(700)
        g1 = page.evaluate(GW)
        ck('mobile header search: focused fills the row', g1['text'] >= g1['vw'] - 130 and not g1['brand'] and not g1['over'], g1)
        ck('mobile header search: dropdown opens', page.locator('.ac-hint').count() >= 1)
        shot(page, ctx, 'pneu_mobile_search')
        page.keyboard.press('Escape'); page.fill('#global-search', ''); page.evaluate("document.querySelector('#global-search').blur()"); page.wait_for_timeout(300)
        g2 = page.evaluate(GW)
        ck('mobile header search: restores after blur', g2['brand'] and abs(g2['text'] - g0['text']) <= 2, g2)
        pk = page.evaluate(PICK_JS)
        if pk.get('only'):
            page.goto(ctx['base'] + '/db/#/card/' + quote(pk['only']))
            page.wait_for_function(VALVE_READY, timeout=60000); page.wait_for_timeout(300)
            w = page.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
            ck('mobile valve-only card: no horizontal page scroll', w['sw'] <= w['cw'], w)
            shot(page, ctx, 'pneu_mobile_valve')
        ck('mobile: no page errors', not errors, errors[:3])
    return ck.fails
