# -*- coding: utf-8 -*-
"""備品庫存（mock 後端 tools/stock/mock_stock.py）：查詢卡有備品列 → 領取 1 顆（位號自動帶入）→ #/stock/ 該料號數量 −1 → 紀錄有該位號；
stockToken 錯誤時回「未授權」（mock 依 run_e2e 給的 AMS_MOCK_STOCK_TOKEN 比對；密語輪替後忘了換 Worker 的 STOCK_TOKEN 就是這個症狀）。
只走穩定路徑（領取 → 數量 → 紀錄 → 未授權），不綁 stale／低量 toast 等會變動的 UI 細節。"""
import json
import urllib.request
from e2e_common import Checks, browser, login, load_card, shot

TAG = 'D01062'  # tools/stock/README：儀器清單有完整型號碼、mock_inventory 有同型號備品的設備（別名也能當查詢鍵）
STOCK_ROW_READY = "document.querySelector('.sum-stock .stk-row') || document.querySelector('.sum-stock .stk-err') || document.querySelector('.sum-stock .cl-empty:not(:empty)')"


def qty_of(page, scope, pn):
    """該料號列 .stk-qty 的數字（後面可能跟「低」「缺」小字，只取第一個文字節點）"""
    return page.evaluate("""([scope, pn]) => { const tr = document.querySelector(scope + ' .stk-row[data-pn="' + pn + '"]'); if (!tr) return null;
      const q = tr.querySelector('.stk-qty'); return q ? parseInt(q.childNodes[0].textContent, 10) : null; }""", [scope, pn])


def run(ctx):
    ck = Checks()
    urllib.request.urlopen(urllib.request.Request(ctx['base'] + '/mock-stock-reset', data=b'{}', method='POST'), timeout=5).read()
    with browser(ctx) as (page, errors, console):
        login(page, ctx)
        load_card(page, ctx, TAG)
        page.wait_for_function(STOCK_ROW_READY, timeout=30000); page.wait_for_timeout(200)
        tag = page.evaluate("(document.querySelector('.sum-tagtext') || {}).textContent || ''").strip()
        rows = page.locator('.sum-stock .stk-row')
        ck('card shows stock rows', rows.count() >= 1, page.locator('.sum-stock').inner_text()[:120])
        if not rows.count():
            return ck.fails
        # 第一列可領（庫存 > 0）的料號
        row = page.locator('.sum-stock .stk-row', has=page.locator('button:has-text("領取"):not([disabled])')).first
        pn = row.get_attribute('data-pn')
        q0 = qty_of(page, '.sum-stock', pn)
        ck('found a takeable part', bool(pn) and q0 is not None and q0 > 0, (pn, q0))
        row.locator('button:has-text("領取")').click()
        page.wait_for_selector('#stk-gate', timeout=5000)
        ck('txn dialog: qty defaults to 1', page.input_value('#stk-gate .stk-n') == '1')
        kks = page.locator('#stk-gate input[placeholder*="KKS"]')
        ck('txn dialog: KKS auto-filled with the card tag', kks.count() == 1 and kks.input_value().strip().upper() == tag.upper(), (kks.input_value() if kks.count() else None, tag))
        shot(page, ctx, 'stock_txn')
        page.click('#stk-gate button[type="submit"]')
        page.wait_for_selector('#stk-gate', state='detached', timeout=15000)
        page.wait_for_timeout(500)
        # 卡片就地更新（fillCard 重抓）：數量 −1
        page.wait_for_function("([pn, q]) => { const tr = document.querySelector('.sum-stock .stk-row[data-pn=\"' + pn + '\"]'); return tr && parseInt(tr.querySelector('.stk-qty').childNodes[0].textContent, 10) === q; }",
                               arg=[pn, q0 - 1], timeout=15000)
        ck('card: qty decreased by 1', qty_of(page, '.sum-stock', pn) == q0 - 1, qty_of(page, '.sum-stock', pn))
        # #/stock/ 總表：同一料號數量 −1；紀錄分頁有這筆（位號、料號、領取）
        # 選擇器限定在總表的 .stk-body（卡片的備品表也有 .stk-wrap，切換路由的瞬間會先命中舊的）
        # 總表可能預設只列低量／缺貨（有 lowCount 時），所以一律點「全部」再搜尋該料號
        page.goto(ctx['base'] + '/db/#/stock/'); page.wait_for_selector('.stk-body .stk-wrap .stk-row', timeout=30000); page.wait_for_timeout(200)
        if page.locator('.stk-filters .chip-btn[data-f="all"]').count():
            page.click('.stk-filters .chip-btn[data-f="all"]')
        page.fill('.stk-q', pn); page.wait_for_selector('.stk-body .stk-row[data-pn="%s"]' % pn, timeout=10000); page.wait_for_timeout(200)
        ck('stock page: qty is q0-1', qty_of(page, '.stk-body', pn) == q0 - 1, qty_of(page, '.stk-body', pn))
        page.fill('.stk-q', '')
        page.click('.seg-btn[data-tab="log"]'); page.wait_for_selector('.stk-body tr.stk-log', timeout=30000)
        hit = page.locator('.stk-body tr.stk-log', has_text=pn).filter(has_text=tag)
        ck('ledger row has KKS + part + 領取', hit.count() >= 1 and '領取' in hit.first.inner_text(), hit.first.inner_text()[:120] if hit.count() else 'no row')
        shot(page, ctx, 'stock_ledger')
        ck('no page errors', not errors, errors[:3])
        ck('no console errors/warnings', not console, console[:3])
        # 錯的 stockToken → 未授權（mock 比對 AMS_MOCK_STOCK_TOKEN；沒設時 mock 只檢查非空，這段就只能驗「有回應」）
        def bad_token(route, request):
            try:
                body = json.loads(request.post_data or '{}'); body['stockToken'] = 'wrong-token'
                route.continue_(post_data=json.dumps(body))
            except Exception:
                route.continue_()
        page.route('**/mock-stock', bad_token)
        page.click('.seg-btn[data-tab="inv"]'); page.click('.stk-reload')
        page.wait_for_selector('.stk-body .stk-err', timeout=15000)
        msg = page.locator('.stk-body .stk-err').inner_text()
        ck('wrong stockToken → 未授權', '未授權' in msg, msg[:100])
        page.unroute('**/mock-stock')
    return ck.fails
