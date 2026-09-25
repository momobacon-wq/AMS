# -*- coding: utf-8 -*-
"""查詢卡：文件全文檢索收合組與雲端硬碟連結、DCS 不符旗標、查無位號、上一頁同步查詢框、帶前後綴／分隔符的輸入、換位號捲回頂端、完整資料延後載入、
資料日期列、分享鈕與點值即複製、最近查過進自動完成與「← 上一個」、多台設備 ?a= 切換、參數連結帶 rn、載入進度回呼、手機版面、Service Worker、console 零錯誤。"""
from e2e_common import Checks, browser, login, load_card, shot

DOC_TAG = 'C10LAB22BP001'      # 有文件全文檢索與雲端硬碟連結
FLAG_TAG = 'G12HAP70BT001'     # 量程與 DCS 不符（端子表／寫入事件），控制器量程相符
NEAR = 'LAB22'                 # 部分字串 → 相近建議
MULTI = '10BT001'              # HostTag 對到 3 台（G12HAD／HAG／LBA10BT001）→ ?a= 切換


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        login(page, ctx)
        # ---- 文件全文檢索：details、預設收合、排在備品庫存之後、內容已載好、Drive 連結
        load_card(page, ctx, DOC_TAG)
        info = page.evaluate("""() => { const s = document.querySelector('.sum-search'); if (!s) return null; const kids = [...s.parentElement.children];
          return { tag: s.tagName, open: s.hasAttribute('open'), idx: kids.indexOf(s), stockIdx: kids.findIndex(e => e.classList.contains('sum-stock')), n: kids.length,
                   cf: s.querySelectorAll('.cf').length, links: [...s.querySelectorAll('a.doclk')].map(a => [a.getAttribute('href'), a.getAttribute('target'), a.getAttribute('rel')]) }; }""")
        ck('docsearch group exists', bool(info))
        if info:
            ck('docsearch is <details>, closed', info['tag'] == 'DETAILS' and not info['open'])
            ck('docsearch after stock and last', info['stockIdx'] >= 0 and info['idx'] > info['stockIdx'] and info['idx'] == info['n'] - 1, (info['idx'], info['stockIdx'], info['n']))
            ck('docsearch filled while closed', info['cf'] > 0 and len(info['links']) > 0)
            ck('drive links well-formed', all(h.startswith('https://drive.google.com/open?id=') and t == '_blank' and 'noopener' in (r or '') for h, t, r in info['links']))
        page.locator('.sum-search > summary').click(); page.wait_for_timeout(200)
        ck('docsearch opens on click', page.evaluate("document.querySelector('.sum-search').open"))
        shot(page, ctx, 'card_docsearch')
        # ---- DCS 旗標：控制器為基準 → ⚠ 只落在端子表／寫入事件
        load_card(page, ctx, FLAG_TAG)
        flags = ' '.join(page.locator('.sum-flags .pill.bad').all_inner_texts())  # 只看紅色 ⚠（黃色「近似」／「多通道」pill 另計）
        ck('DCS mismatch flag present', '量程與 DCS 不符' in flags, flags[:80])
        ck('mismatch names terminal/write, not controller', ('端子表' in flags or '寫入事件' in flags) and '控制器' not in flags, flags[:120])
        ck('docsearch open state remembered', page.evaluate("document.querySelector('.sum-search').open"))
        page.locator('.sum-search > summary').click(); page.wait_for_timeout(200)  # 收回去，別影響別的測試
        # ---- 上一頁／網址列：查詢框跟著路由
        page.fill('#cq-input', DOC_TAG); page.press('#cq-input', 'Enter')
        page.wait_for_function("t => (document.querySelector('.sum-tagtext') || {}).textContent?.trim() === t", arg=DOC_TAG, timeout=60000)
        page.go_back(); page.wait_for_timeout(800)
        ck('back: card shows previous tag', page.evaluate("(document.querySelector('.sum-tagtext') || {}).textContent || ''").strip() == FLAG_TAG)
        ck('back: input synced to route', page.input_value('#cq-input') == FLAG_TAG, page.input_value('#cq-input'))
        page.evaluate("location.hash = '#/card/%s'" % DOC_TAG); page.wait_for_timeout(800)
        ck('hash set: input synced', page.input_value('#cq-input') == DOC_TAG, page.input_value('#cq-input'))
        # ---- 帶分隔符／前後綴的輸入：深連結與查詢框都自動對應到位號
        page.goto(ctx['base'] + '/db/#/card/' + 'G12-HAP70-BT001'); page.wait_for_timeout(800)
        ck('dashed deep link resolves', page.evaluate("(document.querySelector('.sum-tagtext') || {}).textContent || ''").strip() == FLAG_TAG)
        ck('dashed deep link: status says auto-mapped', '自動對應' in page.locator('.cq-status').inner_text())
        page.fill('#cq-input', '1' + FLAG_TAG + '.PV'); page.press('#cq-input', 'Enter'); page.wait_for_timeout(800)
        ck('pasted with prefix/suffix: hash becomes the key', page.evaluate('location.hash') == '#/card/' + FLAG_TAG, page.evaluate('location.hash'))
        # ---- 完整資料收合時不抓變更歷程；展開才抓
        rcs = page.evaluate("(() => { const r = performance.getEntriesByType('resource').map(e => e.name); return r.filter(u => /sheets\\/14\\.json/.test(u)).length; })()")
        ck('collapsed: change-history sheet not fetched', rcs == 0, rcs)
        page.locator('.cq-more > summary').click(); page.wait_for_timeout(1500)
        ck('expanded: recent section rendered', page.locator('.cq-more .csec.recent').count() == 1)
        # ---- 參數現值連結帶 rn=（分塊表只載 r..rn 所在的分塊）
        ck('param quick link carries rn=', page.locator('.cq-more .clinks a[href*="rn="]').count() >= 1)
        page.locator('.cq-more > summary').click(); page.wait_for_timeout(200)
        # ---- 摘要標頭：資料日期列（不印 15 台控制器整串）、分享鈕、複製鈕、點值即複製、標籤去「現值／現行」
        asof = page.locator('.sum-asof').inner_text() if page.locator('.sum-asof').count() else ''
        ck('asof line lists AMS / controller checkout / docsearch dates', 'AMS 資料庫 20' in asof and '控制器 checkout' in asof and '文件索引' in asof, asof[:120])
        ck('asof line is short (no per-controller list)', 0 < len(asof) < 140 and 'BOPE1' not in asof, len(asof))
        ck('share button present', page.locator('.sum-share').count() == 1)
        ck('copy button present regardless of navigator.clipboard', page.locator('.sum-copy').count() == 1)
        page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
        page.locator('.sum-range .sumgrid .cf-v:not(.blank) .cf-t').first.click(); page.wait_for_timeout(300)  # 點值的文字（格子中央可能是來源色點按鈕）
        toast = page.evaluate("(t => t && !t.hidden ? t.textContent : '')(document.querySelector('#toast'))")
        ck('click on a summary value copies it (toast)', toast.startswith('已複製'), toast[:60])
        ck('summary range labels no longer say 現值', page.locator('.sum-range .cf-k', has_text='現值').count() == 0)
        dcsh = page.locator('.sum-dcs .sum-gh').inner_text() if page.locator('.sum-dcs .sum-gh').count() else ''
        ck('summary dcs group label says checkout snapshot', 'checkout' in dcsh and '現行' not in dcsh, dcsh)
        ck('near (warn) flag style defined', page.evaluate("[...document.styleSheets].some(s => { try { return [...s.cssRules].some(r => r.selectorText === '.cmp-flag.warn'); } catch (e) { return false; } })"))
        # ---- 最近查過：框內空白時自動完成列出；「← 上一個」chip 連到上一個位號
        page.click('#cq-input'); page.fill('#cq-input', ''); page.wait_for_timeout(400)
        ck('autocomplete lists recent on empty input', page.locator('.cq .ac-list:not([hidden]) li[data-i]').count() >= 1 and '最近查過' in page.locator('.cq .ac-list').inner_text())
        page.keyboard.press('Escape')
        prev = page.locator('.cq-meta .prev-chip')
        ck('prev chip links to the previously viewed tag', prev.count() == 1 and DOC_TAG in (prev.get_attribute('href') or ''), prev.get_attribute('href') if prev.count() else None)
        # ---- 換位號捲回頂端
        page.evaluate("document.querySelector('.card-view').scrollTop = 600")
        page.evaluate("location.hash = '#/card/%s'" % DOC_TAG); page.wait_for_timeout(800)
        ck('switch tag: scrolled to top', page.evaluate("document.querySelector('.card-view').scrollTop") == 0)
        # ---- 多台設備切換：chips 連 #/card/<鍵>?a=<alias>；切到第二台後 chips 仍在、輸入框與網址主體維持原鍵
        load_card(page, ctx, MULTI)
        chips = page.locator('.cq-alts .chip-btn')
        ck('multi: alt chips listed', chips.count() >= 2, chips.count())
        ck('multi: first chip active, others carry ?a=', chips.count() >= 2 and 'on' in (chips.nth(0).get_attribute('class') or '') and '?a=' in (chips.nth(1).get_attribute('href') or ''))
        tag1 = page.locator('.sum-tagtext').inner_text().strip()
        chips.nth(1).click(); page.wait_for_timeout(900)
        tag2 = page.locator('.sum-tagtext').inner_text().strip()
        ck('multi: switched to second device via ?a=', tag2 != tag1 and '?a=' in page.evaluate('location.hash'), (tag1, tag2))
        ck('multi: chips still shown, second is active', page.locator('.cq-alts .chip-btn').count() >= 2 and 'on' in (page.locator('.cq-alts .chip-btn').nth(1).get_attribute('class') or ''))
        ck('multi: input keeps the original key', page.input_value('#cq-input') == MULTI, page.input_value('#cq-input'))
        ck('multi: status says which device', '第 2 台' in page.locator('.cq-meta').inner_text())
        ck('multi: share url keeps key and ?a=', page.evaluate("(v => v && v.shareUrl ? v.shareUrl(v.res) : '')(AMS.router.current())").endswith('#/card/' + MULTI + '?a=' + page.evaluate("AMS.router.current().res.alias")))
        # ---- 載入進度回呼：已載入（memoized）的索引對後來的呼叫者也回 1
        ck('index.load reports progress to late callers', page.evaluate("new Promise(r => { AMS.index.load(f => r(f)); setTimeout(() => r(-1), 2000); })") == 1)
        # ---- 查無位號：無建議 vs 有相近建議
        page.goto(ctx['base'] + '/db/#/card/XXXX999'); page.wait_for_timeout(600)
        st = page.locator('.cq-status').inner_text()
        ck('not found (no suggestion): message points to index', '查無' in st and page.locator('.nf-chips .chip-btn').count() == 0, st)
        page.goto(ctx['base'] + '/db/#/card/' + NEAR); page.wait_for_timeout(600)
        st = page.locator('.cq-status').inner_text(); nchips = page.locator('.nf-chips .chip-btn').count()
        ck('partial: suggestions listed', nchips >= 1, nchips)
        ck('partial: status says "相近"', '相近' in st and '搜尋部分字串' not in st, st)
        # ---- Service Worker：已註冊、已快取帶 ?v= 的檔
        page.reload(); page.wait_for_selector('.cq-input', timeout=60000); page.wait_for_timeout(500)
        sw = page.evaluate("""async () => { const regs = await navigator.serviceWorker.getRegistrations(); const keys = await caches.keys();
          let n = 0; for (const k of keys) { const c = await caches.open(k); n += (await c.keys()).filter(r => /[?&]v=/.test(r.url)).length; }
          return { regs: regs.length, scope: regs[0] && regs[0].scope, caches: keys, versioned: n, controlled: !!navigator.serviceWorker.controller }; }""")
        ck('service worker registered at site root', sw['regs'] >= 1 and str(sw['scope']).endswith('/') and not str(sw['scope']).endswith('/db/'), sw)
        ck('versioned files cached', sw['versioned'] >= 5, sw['versioned'])
        # ---- 錯誤回報：故意丟一個錯，mock 端點應收到（AMSReport.count 會加 1）
        page.evaluate("setTimeout(() => { throw new Error('e2e test error'); }, 0)"); page.wait_for_timeout(800)
        ck('error reporter counted the error', page.evaluate("window.AMSReport && window.AMSReport.count()") >= 1)
        errors[:] = [e for e in errors if 'e2e test error' not in e]
        ck('no page errors', not errors, errors[:3])
        ck('no console errors/warnings', not console, console[:3])
    # ---- 手機：無橫向捲動、placeholder 說明可輸入的鍵
    with browser(ctx, mobile=True) as (page, errors, console):
        login(page, ctx)
        ck('mobile placeholder explains keys', '位號' in (page.get_attribute('#cq-input', 'placeholder') or ''))
        load_card(page, ctx, FLAG_TAG)
        page.fill('#cq-input', DOC_TAG); page.press('#cq-input', 'Enter'); page.wait_for_timeout(600)
        ck('mobile: keyboard dismissed after Enter (input blurred)', page.evaluate("document.activeElement && document.activeElement.id") != 'cq-input')
        ck('mobile: input has no autocorrect', page.get_attribute('#cq-input', 'autocorrect') == 'off')
        w = page.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
        ck('mobile: no horizontal scroll', w['sw'] <= w['cw'], w)
        shot(page, ctx, 'card_mobile')
        ck('mobile: no page errors', not errors, errors[:3])
    return ck.fails
