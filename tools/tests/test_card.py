# -*- coding: utf-8 -*-
"""查詢卡：文件全文檢索收合組與雲端硬碟連結、圖控 HMI 畫面縮圖與標記、DCS 不符旗標、查無位號、上一頁同步查詢框、帶前後綴／分隔符的輸入、換位號捲回頂端、完整資料延後載入、
資料日期列、分享鈕與點值即複製、最近查過進自動完成與「← 上一個」、多台設備 ?a= 切換、參數連結帶 rn、載入進度回呼、手機版面、Service Worker、console 零錯誤。"""
from e2e_common import Checks, browser, login, load_card, shot

DOC_TAG = 'C10LAB22BP001'      # 有文件全文檢索與雲端硬碟連結
FLAG_TAG = 'G12HAP70BT001'     # 量程與 DCS 不符（端子表／寫入事件），控制器量程相符
NEAR = 'LAB22'                 # 部分字串 → 相近建議
MULTI = '10BT001'              # HostTag 對到 3 台（G12HAD／HAG／LBA10BT001）→ ?a= 切換
HMI_TAG = 'C10LAB22BF001'      # 圖控：BOP_Feed_Water.cim（選單機組 BOPM1A.），有縮圖與 2 個標記（兩處只差 1.6% 畫面高 → 要靠 ①② 分辨）
HMI_UNIT = 'G12HAP70BT001'     # 圖控：HRSG_Blowdown_UX.cim **以選單機組 H12. 開啟**，而該畫面 H11./H12. 各拍了一張執行時截圖
#                                （primary 是 H11.）→ 用來守住「照 ex.unit 挑 variant」：挑錯就會把 HRSG11 的現值端到 G12 這台的卡上。
#                                2026-10-04 起 43 個被引用的畫面全部有執行時截圖，`.hmi-noimg`（兩種影像都沒有）在現行語料是 0 筆，無法再用資料驗。
HMI_FF = 'G11_90LT-1'          # FF：圖控畫面檔完全查無
HMI_TMPL = '1-LI-CW101-1'      # 曾顯示未代入樣板 aliasSignal={device}（74 列）→ 現在必須是 device=1-LI-CW101-1_XQ01
HMI_MULTI = 'C10LAB40BP001'    # 多點簡寫 caption=…LAB40BP001\002 → 卡片要有白話說明


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        login(page, ctx)
        # ---- 文件全文檢索：details、預設收合、排在備品庫存之後、內容已載好、Drive 連結
        load_card(page, ctx, DOC_TAG)
        info = page.evaluate("""() => { const s = document.querySelector('.sum-search'); if (!s) return null; const kids = [...s.parentElement.children];
          return { tag: s.tagName, open: s.hasAttribute('open'), idx: kids.indexOf(s), stockIdx: kids.findIndex(e => e.classList.contains('sum-stock')),
                   hmiIdx: kids.findIndex(e => e.classList.contains('sum-hmi')), n: kids.length,
                   cf: s.querySelectorAll('.cf').length, links: [...s.querySelectorAll('a.doclk')].map(a => [a.getAttribute('href'), a.getAttribute('target'), a.getAttribute('rel')]) }; }""")
        ck('docsearch group exists', bool(info))
        if info:
            ck('docsearch is <details>, closed', info['tag'] == 'DETAILS' and not info['open'])
            # after_stock 的組依 summary_spec 順序排在備品庫存之後：…→ 文件全文檢索 → 圖控 HMI 畫面（最後一組）
            ck('docsearch after stock, 圖控 HMI last', info['stockIdx'] >= 0 and info['idx'] > info['stockIdx'] and info['hmiIdx'] == info['idx'] + 1 and info['hmiIdx'] == info['n'] - 1,
               (info['idx'], info['stockIdx'], info['hmiIdx'], info['n']))
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
        # ---- 圖控 HMI 畫面位置（CONTRACT.md v5）：摘要組與完整資料都有縮圖＋標記，但影像延後到展開才抓；摘要組整列寬、寬容器時左欄位右縮圖
        page.evaluate('performance.clearResourceTimings()')
        load_card(page, ctx, HMI_TAG)
        # 摘要組的縮圖在渲染時就載：延後到展開才載行不通——點開摘要組會觸發重新渲染並把它恢復成收合，
        # toggle 監聽留在被換掉的舊 <details> 上，縮圖永遠停在 loading（2026-10-03 使用者回報「沒有看到圖控畫面」）。
        # 完整資料區（.cq-more 預設收合、展開是明確動作）仍延後載入，所以同一張圖只抓一次。
        page.wait_for_function("(() => { const i = document.querySelector('.sum-hmi .hmi-img'); return i && i.complete && i.naturalWidth > 0; })()", timeout=30000)
        pre = page.evaluate("""(() => ({ req: performance.getEntriesByType('resource').filter(e => /\\/card\\/hmi\\//.test(e.name)).length,
          sumImg: document.querySelectorAll('.sum-hmi .hmi-img').length, auxImg: document.querySelectorAll('.cq-more .hmi-img').length,
          auxPh: document.querySelectorAll('.cq-more .hmi-frame.loading').length,
          moreOpen: document.querySelector('details.cq-more').open }))()""")
        ck('摘要組渲染時就載縮圖、完整資料區仍延後（同一張圖最多抓 1 次；命中快取時 0 次）',
           pre['req'] <= 1 and pre['sumImg'] >= 1 and pre['auxImg'] == 0 and pre['auxPh'] >= 1 and not pre['moreOpen'], pre)
        page.evaluate("document.querySelector('details.sum-hmi').open = true")
        page.wait_for_function("(() => { const i = document.querySelector('.sum-hmi .hmi-img'); return i && i.complete && i.naturalWidth > 0; })()", timeout=30000)
        sum_hmi = page.inner_text('.sum-hmi')
        ck('摘要圖控組：畫面名稱＋導覽路徑', 'BOP_Feed_Water.cim' in sum_hmi and '›' in sum_hmi, sum_hmi[:80])
        ck('摘要圖控組展開即顯示縮圖與標記', page.locator('.sum-hmi .hmi-img').count() >= 1 and page.locator('.sum-hmi .hmi-mk').count() == 2)
        lay = page.evaluate("""(() => { const g = document.querySelector('.sum-hmi'), s = g.querySelector('.hmi-screen');
          const f = s.querySelector('.hmi-f').getBoundingClientRect(), sh = s.querySelector('.hmi-shot').getBoundingClientRect();
          const im = s.querySelector('img.hmi-img').getBoundingClientRect(), fr = s.querySelector('.hmi-frame').getBoundingClientRect();
          return {gap: Math.round(g.getBoundingClientRect().width - g.parentElement.getBoundingClientRect().width),
                  cols: getComputedStyle(s).gridTemplateColumns, fLeft: Math.round(f.left), shotLeft: Math.round(sh.left), fW: Math.round(f.width),
                  listW: Math.round(g.querySelector('.hmi-list').clientWidth), dw: Math.round(im.width - fr.width),
                  split: s.classList.contains('sum-has-shot'), auxN: document.querySelectorAll('.aux-hmi .hmi-screen').length,
                  auxSplit: document.querySelectorAll('.aux-hmi .hmi-screen.sum-has-shot').length}; })()""")
        ck('摘要圖控組佔整列寬（不是半格，右半不留空）', abs(lay['gap']) <= 1, lay)
        ck('寬容器：左邊欄位、右邊縮圖（容器查詢兩欄，斷點 1150）',
           ' ' in lay['cols'] and lay['shotLeft'] > lay['fLeft'] and lay['listW'] >= 1150 and lay['split'], lay)
        # 左欄不能窄到讓 src-full 的三欄把中文值切成 7 行以上（斷點 900 時左欄只有 374–440px，比不並排還難讀）
        ck('並排時左欄仍讀得下去（≥ 430px）', lay['fW'] >= 430, lay)
        ck('完整資料區不掛 .sum-has-shot（容器查詢只給摘要組）', lay['auxN'] >= 1 and lay['auxSplit'] == 0, lay)
        ck('縮圖貼齊標記框（標記位置才對得上）', abs(lay['dw']) <= 3, lay)
        page.locator('.sum-hmi .hmi-shot').first.click(); page.wait_for_timeout(500)
        ck('摘要縮圖也能點開燈箱（容器查詢祖先不影響）', page.locator('.hmi-lb').count() == 1 and page.locator('.hmi-lb .hmi-mk').count() == 2)
        page.keyboard.press('Escape'); page.wait_for_timeout(300)
        ck('燈箱 Esc 關得掉', page.locator('.hmi-lb').count() == 0)
        page.evaluate("document.querySelector('details.cq-more').open = true")
        page.wait_for_function("document.querySelectorAll('.aux-hmi .hmi-img').length > 0", timeout=30000)
        page.evaluate("document.querySelector('.aux-hmi .hmi-img').scrollIntoView({block:'center'})")
        page.wait_for_function("(() => { const i = document.querySelector('.aux-hmi .hmi-img'); return i && i.complete && i.naturalWidth > 0; })()", timeout=30000)
        img = page.evaluate("(() => { const i = document.querySelector('.aux-hmi .hmi-img'); return {src: i.src.slice(0,5), nw: i.naturalWidth, nh: i.naturalHeight}; })()")
        ck('縮圖以 blob URL 解密載入（CSP img-src 要含 blob:）', img['src'] == 'blob:' and img['nw'] == 1280 and img['nh'] == 720, img)
        marks = page.evaluate("[...document.querySelectorAll('.aux-hmi .hmi-mk')].map(m => m.getAttribute('style'))")
        ck('標記以百分比疊在影像上（沒有燒進影像）', len(marks) == 2 and all('%' in m for m in marks), marks)
        # 多處標記要編號，而且「所在位置」描述的那處＝①（marks[0]，CONTRACT v5）
        nos = page.evaluate("[...document.querySelectorAll('.aux-hmi .hmi-no')].map(e => [e.textContent, e.classList.contains('pri'), e.getAttribute('style')])")
        ck('多處標記有編號 ①②，第一個是 .pri', [n[0] for n in nos] == ['①', '②'] and nos[0][1] and not nos[1][1], nos)
        ck('編號逐個錯開（inline transform 不同）', nos[0][2] != nos[1][2] and 'translate' in nos[0][2], [n[2] for n in nos])
        pos = page.evaluate("""(() => { const cf = [...document.querySelectorAll('.aux-hmi .cf')].find(c => c.querySelector('.cf-k').textContent.includes('所在位置'));
          return cf ? cf.querySelector('.cf-v').textContent : ''; })()""")
        ck('「所在位置」指名圖上標記 ①、並說另有幾處', '圖上標記 ①' in pos and '另有 1 處' in pos and '②' in pos, pos[:120])
        navtxt = page.evaluate("""(() => { const cf = [...document.querySelectorAll('.aux-hmi .cf')].find(c => c.querySelector('.cf-k').textContent.includes('導覽路徑'));
          return cf ? cf.querySelector('.cf-v').textContent : ''; })()""")
        ck('機組寫成「以選單機組 X 開啟」（不是儀器所屬機組）', '以選單機組' in navtxt and '開啟' in navtxt, navtxt[:120])
        ck('畫面標頭也用同樣用詞', '以選單機組' in page.inner_text('.aux-hmi .hmi-head'), page.inner_text('.aux-hmi .hmi-head')[:120])
        page.locator('.aux-hmi .hmi-shot').first.click(); page.wait_for_timeout(500)
        ck('點縮圖開燈箱，標記同步', page.locator('.hmi-lb').count() == 1 and page.locator('.hmi-lb .hmi-mk').count() == 2)
        ck('燈箱 ✕ 不疊在影像上（自己一列）', page.evaluate("getComputedStyle(document.querySelector('.hmi-lb .modal-x')).position") == 'static')
        shot(page, ctx, 'card_hmi_lightbox')
        # 返回鍵：桌機寬度也只關燈箱、留在同一張卡（AMS.overlay.open 的 force）
        h0 = page.evaluate('location.hash')
        page.go_back(); page.wait_for_timeout(600)
        ck('燈箱：返回鍵只關燈箱、留在同一張卡（桌機寬度也要成立）',
           page.locator('.hmi-lb').count() == 0 and page.evaluate('location.hash') == h0,
           (page.evaluate('location.hash'), h0))
        page.locator('.aux-hmi .hmi-shot').first.click(); page.wait_for_timeout(400)
        page.keyboard.press('Escape'); page.wait_for_timeout(300)
        ck('Esc 關燈箱且不留 modal-open', page.locator('.hmi-lb').count() == 0 and not page.evaluate("document.body.classList.contains('modal-open')"))
        # 對應方式：未代入樣板（aliasSignal={device}）必須已被真正的位號取代；多點簡寫要有白話說明
        load_card(page, ctx, HMI_TMPL)
        page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1500)
        ref = page.inner_text('.aux-hmi')
        ck('對應方式不是未代入樣板', '={device}' not in ref and 'device=1-LI-CW101-1' in ref, ref[:200])
        load_card(page, ctx, HMI_MULTI)
        page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1500)
        ck('多點簡寫有白話說明（不是看起來像亂碼）', '多點簡寫' in page.inner_text('.aux-hmi'), page.inner_text('.aux-hmi')[:260])
        load_card(page, ctx, HMI_FF)
        page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1200)
        ff_txt = page.inner_text('.aux-hmi')
        ck('FF 設備：圖控查無並說明原因', 'FF' in ff_txt, ff_txt[:90])
        # 掃描範圍一次講完（不會同一張卡出現 248 與 473 兩個數字卻沒解釋）
        ck('查無文案講清楚掃了哪些、排除了哪些', '248' in ff_txt and '225' in ff_txt and '473' in ff_txt, ff_txt[:220])
        load_card(page, ctx, DOC_TAG)     # 還原「最近查過」的順序（下面的「← 上一個」chip 預期上一台是 DOC_TAG）
        load_card(page, ctx, HMI_UNIT)    # ＝FLAG_TAG：順便把卡片還原成下一段（摘要標頭）預期的那一台
        page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1200)
        page.wait_for_function("document.querySelectorAll('.aux-hmi .hmi-img').length > 0", timeout=30000)
        # 執行時截圖是**逐選單機組各一張**：真的抓進來的必須是這一列選單機組（H12.）那一張，不是 primary（H11.）那一張。
        # 看 D.cache 的鍵（實際抓過的路徑）而不是 performance resource（緩衝區只有 250 筆，換過幾張卡就把舊的擠掉）
        hgot = page.evaluate("[...AMS.data.cache.keys()].filter(k => k.indexOf('card/hmi/') === 0)")
        ck('圖控影像照選單機組挑（不會端出別的機組的現值）',
           any('HRSG_Blowdown_UX__H12' in k for k in hgot) and not any('HRSG_Blowdown_UX__H11' in k for k in hgot), hgot)
        # 只看 hmiSrcText 的產物（img alt）。**不可**退而求其次看 .aux-hmi 的 inner_text：
        # 區段說明（sections_aux 的 note）就印在同一個 .aux-hmi 裡，用 or 串起來會讓這條斷言永遠綠燈、什麼都沒守到
        cap = page.evaluate("(() => { const i = document.querySelector('.aux-hmi img.hmi-img'); return i ? i.alt : ''; })()")
        ck('說明寫出擷取日期、選單機組與「不是即時值」',
           '2026-10-04' in cap and '選單機組 H12.' in cap and '不是即時值' in cap, cap[:160])
        ck('沒有影像的畫面才出現 .hmi-noimg（現行語料 0 筆）', page.locator('.aux-hmi .hmi-noimg').count() == 0)
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
