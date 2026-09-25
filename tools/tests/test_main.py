# -*- coding: utf-8 -*-
"""舊站（docs/，20260910 匯出檔）：兩站共用 table.js／grid.js／card.js，改新站時舊站也要活著——
03 表格帶 ?q= 有列與 facet 下拉、01 摘要六張圖表、點連結儲存格跳到目標表且目標列高亮、手機無橫向捲動。"""
from e2e_common import Checks, browser, login, shot

ROWS = '.tv-win .tr'


def first_link(page):
    """目前畫面（含向右捲動）第一個帶 ?r= 的連結儲存格 href；表格只渲染可見欄，連結欄可能在右側"""
    for _ in range(12):
        h = page.evaluate("(() => { const a = document.querySelector('.tv-win a.lk[href*=\"?r=\"]'); return a ? a.getAttribute('href') : null; })()")
        if h:
            return h
        page.evaluate("(() => { const s = document.querySelector('.tv-scroll'); s.scrollLeft += Math.max(400, s.clientWidth - 100); })()")
        page.wait_for_timeout(250)
    return None


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        login(page, ctx, site='main')
        # ---- 03 帶查詢字串：有列、筆數、facet 下拉
        page.goto(ctx['base'] + '/#/s/03?q=GT11'); page.wait_for_selector(ROWS, timeout=60000); page.wait_for_timeout(400)
        ck('03 ?q=GT11: rows rendered', page.locator(ROWS).count() >= 1, page.locator(ROWS).count())
        ck('03: search box synced from route', page.input_value('.tv-q') == 'GT11', page.input_value('.tv-q'))
        cnt = page.locator('.tv-count').inner_text()
        ck('03: count shows filtered/total', '/' in cnt or '列' in cnt, cnt)
        ck('03: facet dropdown in filter row', page.locator('.hr-filt select.fi').count() >= 1, page.locator('.hr-filt select.fi').count())
        shot(page, ctx, 'main_03')
        # ---- 01 摘要：六張 Chart.js 圖表（CONTRACT v2：chart1–6）
        page.goto(ctx['base'] + '/#/s/01')
        try:
            page.wait_for_function("document.querySelectorAll('.view canvas').length >= 6", timeout=60000)
        except Exception:
            pass
        ncv = page.evaluate("document.querySelectorAll('.view canvas').length")
        ck('01: six chart canvases', ncv == 6, ncv)
        # ---- 連結儲存格 → 目標表 ?r=、目標列高亮（.tg）
        page.goto(ctx['base'] + '/#/s/03'); page.wait_for_selector(ROWS, timeout=60000); page.wait_for_timeout(400)
        href = first_link(page)
        ck('03: a link cell with ?r= found', bool(href), href)
        if href:
            page.click('.tv-win a.lk[href="%s"]' % href)
            page.wait_for_function("h => location.hash.startsWith(h.split('?')[0]) && /[?&]r=\\d+/.test(location.hash)", arg=href, timeout=15000)
            page.wait_for_selector('.tr.tg', timeout=60000); page.wait_for_timeout(300)
            ck('link: route has ?r= and target row highlighted', page.locator('.tr.tg').count() == 1, page.evaluate('location.hash'))
            g = page.evaluate("document.querySelector('.tr.tg').dataset.g")
            ck('link: highlighted row is the r= row', ('r=%s' % g) in page.evaluate('location.hash'), (g, page.evaluate('location.hash')))
            shot(page, ctx, 'main_link_target')
        # ---- 查詢卡（舊站也用 card.js）
        page.goto(ctx['base'] + '/#/card/'); page.wait_for_selector('.cq-input', timeout=60000)
        ck('main: card view loads', page.locator('.cq-input').count() == 1)
        ck('no page errors', not errors, errors[:3])
        ck('no console errors/warnings', not console, console[:3])
    with browser(ctx, mobile=True) as (page, errors, console):
        login(page, ctx, site='main')
        page.goto(ctx['base'] + '/#/s/03'); page.wait_for_selector(ROWS, timeout=60000); page.wait_for_timeout(400)
        w = page.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
        ck('mobile: table page has no horizontal page scroll', w['sw'] <= w['cw'], w)
        shot(page, ctx, 'main_mobile_03')
        ck('mobile: no page errors', not errors, errors[:3])
    return ck.fails
