# -*- coding: utf-8 -*-
"""Service Worker 與版本偵測：version.json 的 build 變了 → 「資料已更新」橫幅（繞過 5 分鐘節流：page.clock 快轉）；
頁面載入後的 keep 清單會刪掉本站 data/ 底下版本值不在清單內的快取（另一站的 data/ 不動）。"""
import json
from e2e_common import Checks, browser, login

CACHE = 'ams-static-v1'


def cache_has(page, url):
    return page.evaluate("async (u) => { const c = await caches.open('%s'); return !!(await c.match(u)); }" % CACHE, url)


def cache_put(page, url):
    page.evaluate("async (u) => { const c = await caches.open('%s'); await c.put(new Request(u), new Response('{}', { headers: { 'Content-Type': 'application/json' } })); }" % CACHE, url)


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        login(page, ctx)
        page.wait_for_timeout(800)
        # ---- 版本橫幅：假的 version.json（build 變、app 不變）＋ 時鐘快轉 6 分鐘 → visibilitychange 觸發檢查
        cur = page.evaluate("fetch('version.json', {cache: 'no-cache'}).then((r) => r.json())")
        page.clock.install()
        page.route('**/version.json', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'build': 'deadbeef00', 'app': cur.get('app')})))
        page.clock.fast_forward(6 * 60 * 1000)
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        try:
            page.wait_for_selector('.ver-banner', timeout=8000)
            txt = page.locator('.ver-banner').inner_text()
        except Exception:
            txt = ''
        ck('version banner appears after build change', bool(txt), txt)
        ck('banner says data updated (new build)', '資料已更新' in txt, txt[:80])
        ck('banner has reload button', page.locator('.ver-banner button.primary').count() == 1)
        page.locator('.ver-banner .icon-btn').click(); page.wait_for_timeout(100)
        ck('banner dismissible', page.locator('.ver-banner').count() == 0)
        page.unroute('**/version.json')
        # ---- Service Worker 已控制頁面（第一次載入時註冊，reload 後才由它接管）
        page.reload(); page.wait_for_selector('.cq-input', timeout=60000); page.wait_for_timeout(1000)
        controlled = page.evaluate("!!navigator.serviceWorker.controller")
        ck('service worker controls the page', controlled)
        origin = page.evaluate('location.origin')
        stale_db = origin + '/db/data/x.json?v=stale'
        stale_main = origin + '/data/x.json?v=stale'
        cache_put(page, stale_db); cache_put(page, stale_main)
        ck('stale entries planted', cache_has(page, stale_db) and cache_has(page, stale_main))
        page.reload(); page.wait_for_selector('.cq-input', timeout=60000)
        page.wait_for_function("async () => { const c = await caches.open('%s'); return !(await c.match('%s')); }" % (CACHE, stale_db), timeout=15000)
        ck('keep list removed stale db/data entry', not cache_has(page, stale_db))
        ck('other site (main) data entry untouched', cache_has(page, stale_main))
        n = page.evaluate("async () => { const c = await caches.open('%s'); return (await c.keys()).filter((r) => /[?&]v=/.test(r.url)).length; }" % CACHE)
        ck('current versioned files still cached', n >= 5, n)
        page.evaluate("async () => { const c = await caches.open('%s'); await c.delete('%s'); }" % (CACHE, stale_main))
        ck('no page errors', not errors, errors[:3])
        ck('no console errors/warnings', not console, console[:3])
    return ck.fails
