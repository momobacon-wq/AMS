# -*- coding: utf-8 -*-
"""查詢卡：文件全文檢索收合組與雲端硬碟連結、圖控 HMI 畫面縮圖與標記、DCS 不符旗標、查無位號、上一頁同步查詢框、帶前後綴／分隔符的輸入、換位號捲回頂端、完整資料延後載入、
資料日期列、分享鈕與點值即複製、最近查過進自動完成與「← 上一個」、多台設備 ?a= 切換、參數連結帶 rn、載入進度回呼、手機版面、Service Worker、console 零錯誤。
P&ID 圖面位置（圖紙標頭、細部視窗對準標記、小地圖、縮放燈箱、延後載入、多張圖紙收合、查無、手機、照 CSP 執行）接在圖控那一段之後；
2026-10-10 稽核後加：標記 ① 的絕對座標、引用（註記／旗標／用氣點／迴路詳圖）講明不是儀器符號、紅字看整張圖最低的辨識信心並點名、
ocr-fix、JK 位號「不在比對範圍」、編號牌讀得出來、圖紙影像的記憶體釋放（換卡／雙胞胎共用／離開）、圖上的字只當文字插入。
建置端的文案與關卡另有不開瀏覽器的 test_pid_wording.py。"""
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
HMI_MANY = 'C10MAG10BL001'     # 14 組（畫面, 選單機組）＝全廠最多：摘要組只先展開第一張（card.js HMI_FOLD=3）
PID_TYP = 'G12HSD10QN101'      # P&ID：HT0-1-KND01-D0027 Rev.4 PDF 第 2 頁，圖上畫的是 =G11HSD10QN101（以 G11 繪製的典型圖），位置由 OCR 讀出（線條字）
PID_MANY = 'C10LCB40BT001'     # P&ID：畫在 2 張圖紙上（第 2 張預設收合），其中一張有多處標記 → 收合、展開才抓、①②… 編號、「下一處」
PID_NONE = '1-LI-CW101-1'      # P&ID：現行圖面查無（＝HMI_TMPL）
# PID_TYP 的標記 ① 在圖紙上的**絕對**位置（SPEC 第 10 節的例子：D0027 Rev.4 PDF 第 2 頁轉正後，=G11HSD10QN101 那幾個字的中心）。
# 其餘幾何檢查都只拿畫面與資料自己的 marks[0] 互比——pid_index／pid_shots 的轉正角或座標換算錯了，那些檢查照樣全綠；這一筆釘死它。
PID_PIN = ('HT0-1-KND01-D0027-4_1030bef1__p2', 0.4666, 0.7083, 0.003)
PID_TWIN = 'G12HSD10BF101'     # 與 PID_TYP 畫在同一張圖紙（D0027 第 2 頁）上的另一台設備 → 兩台互換時圖紙影像不必重抓
PID_JK = 'JK0N0G9-1N3A'        # JK 開頭的 HART 多工器模組：沒有列入 P&ID 比對，卡片要說「不在比對範圍」，不是「查無」
# 引用（不是儀器符號的位置；build_card_aux 的 note 代碼）各一種：依序找「資料裡真的有一張圖紙的 ① 是這一種」的第一台來驗。
# 位號取自 2026-10-10 稽核的清單；pid_index 再改分類時前面的候選可能不成立，所以各放幾台——全部落空才算失敗（那時要換候選）。
PID_REF_TAGS = {1: ['C10LAC50BT029', 'C10LAC70BT044', 'G12_90VA41-2', 'G11_90VA41-2'],        # 儀器清單的一列／圖上註記
                2: ['G12HAP61BL001', 'C10LCB40BT001', 'C10MAG10BL001', 'G11HAP61BL001'],       # 跨圖訊號旗標
                3: ['G11HAD10QN006', 'G12HAD10QN006', 'G11LAB65QN003', 'C10LAF31QN001'],       # 空氣分配圖的用氣點
                4: ['C10LAC50BP005']}                                                          # 迴路詳圖（TYPICAL 小圖）
PID_REF_SAYS = {1: ('註記／表格', '不是儀器符號旁的標籤'), 2: ('跨圖訊號旗標', '不是儀器本身的位置'),
                3: ('用氣點', '不是閥在製程管線上的位置'), 4: ('迴路詳圖', '不是主流程圖上的位置')}   # (標頭短籤要有的字, 「圖上標示」整句要有的字)
PID_LOW_TAGS = ['C10LAC50BT021', 'C10LAC50BT009', 'G11HAD10QN002', 'G11HAD10QN008', 'C10LAC70BT044']   # 有一張圖紙的 OCR 辨識信心低於 0.8（conf_min）
from e2e_common import CARD_READY  # noqa: E402  （檔尾「照 CSP 執行」那一段要自己輪詢，不能用 load_card 的 wait_for_function）
# P&ID 圖紙影像的請求數、細部視窗「影像已載入」、幾何量測（sel＝.sum-pid／.aux-pid／.pid-lb／某一塊圖紙）
PID_REQ = "performance.getEntriesByType('resource').filter(e => /\\/card\\/pid\\//.test(e.name)).length"
PID_IMG = ("(() => { const v = document.querySelector('%s .pid-view'); const i = v && v.querySelector('.pid-stage img.pid-img');"
           " return !!(v && !v.classList.contains('loading') && i && i.complete && i.naturalWidth > 0); })()")
PID_GEOM = """(sel) => { const root = document.querySelector(sel); const q = (s) => root.querySelector(s);
  const view = q('.pid-view'), stage = q('.pid-stage'), img = q('.pid-stage img.pid-img'), pri = q('.pid-stage .hmi-box.pri') || q('.pid-stage .hmi-mk.pri');
  const mini = q('.pid-mini'), rect = q('.pid-rect'), dot = q('.pid-dot.pri');
  const v = view.getBoundingClientRect(), s = stage.getBoundingClientRect(), m = pri.getBoundingClientRect(), cs = getComputedStyle(pri);
  const vl = v.left + view.clientLeft, vt = v.top + view.clientTop, vw = view.clientWidth, vh = view.clientHeight;   // 視窗內緣（不含邊框）
  const cx = m.left + m.width / 2, cy = m.top + m.height / 2;
  const o = { req: REQ, imgs: root.querySelectorAll('img.pid-img').length, src: img ? img.src.slice(0, 5) : '', nat: img ? [img.naturalWidth, img.naturalHeight] : null, alt: img ? img.alt : '',
    k: parseFloat(getComputedStyle(view).getPropertyValue('--pid-k')) || null, vw, vh, sw: s.width, sh: s.height, sl: s.left - vl, st: s.top - vt,
    tf: getComputedStyle(stage).transform, inside: cx > vl && cx < vl + vw && cy > vt && cy < vt + vh, dx: cx - (vl + vw / 2), dy: cy - (vt + vh / 2),
    edgeX: Math.abs(s.left - vl) < 1.5 || Math.abs(s.right - (vl + vw)) < 1.5, edgeY: Math.abs(s.top - vt) < 1.5 || Math.abs(s.bottom - (vt + vh)) < 1.5,
    fx: (cx - s.left) / s.width, fy: (cy - s.top) / s.height, style: pri.getAttribute('style') || '', boxed: pri.classList.contains('hmi-box'),
    bg: cs.backgroundColor, bw: cs.borderTopWidth, rings: stage.querySelectorAll('.hmi-mk').length, mw: m.width, mh: m.height,
    miniW: mini ? mini.clientWidth : 0, miniH: mini ? mini.clientHeight : 0, dot: null, rect: null, rectIn: false, dotInRect: false };
  if (mini && dot && mini.clientWidth) { const mn = mini.getBoundingClientRect(), d = dot.getBoundingClientRect(); const dx = d.left + d.width / 2, dy = d.top + d.height / 2;
    o.dot = [(dx - mn.left - mini.clientLeft) / mini.clientWidth, (dy - mn.top - mini.clientTop) / mini.clientHeight];
    if (rect && !rect.hidden) { const r = rect.getBoundingClientRect(); o.rect = [r.width / mini.clientWidth, r.height / mini.clientHeight];
      o.rectIn = r.left >= mn.left - 1 && r.top >= mn.top - 1 && r.right <= mn.right + 1 && r.bottom <= mn.bottom + 1;
      o.dotInRect = dx >= r.left && dx <= r.right && dy >= r.top && dy <= r.bottom; } }
  return o; }""".replace('REQ', PID_REQ)


def pid_typ(page, ctx, ck):
    """P&ID 圖面位置，典型的一台（PID_TYP）：摘要組排在圖控 HMI 之前、整列寬；圖紙＝標頭＋PDF 連結＋「細部視窗＋小地圖」，點開是可縮放
    拖曳的燈箱；圖紙影像捲到才抓（一張 26–300 KB 的密文、解碼後 16–30 MB）；完整資料區另有五個欄位。回傳這份資料有沒有 P&ID 組。"""
    page.evaluate('performance.clearResourceTimings()')
    load_card(page, ctx, PID_TYP)
    g = page.evaluate("""() => { const s = document.querySelector('.sum-pid'); if (!s) return null; const kids = [...s.parentElement.children];
      const caps = [...s.querySelectorAll('.hmi-head .hmi-cap')], a = s.querySelector('.pid-bar a');
      return { tag: s.tagName, idx: kids.indexOf(s), hmiIdx: kids.findIndex(e => e.classList.contains('sum-hmi')),
               gap: Math.round(s.getBoundingClientRect().width - s.parentElement.getBoundingClientRect().width),
               top: Math.round(s.getBoundingClientRect().top), vh: innerHeight, req: %s,
               img: s.querySelectorAll('img.pid-img').length, ph: s.querySelectorAll('.pid-view.loading').length,
               head: (s.querySelector('.hmi-head') || {}).innerText || '', cap: caps.map(e => e.textContent).join('·'), warn: caps.length ? caps.some(e => e.classList.contains('warn')) : null,
               link: a ? [a.getAttribute('href'), a.getAttribute('target'), a.getAttribute('rel'), a.textContent] : null,
               bar: (s.querySelector('.pid-bar') || {}).innerText || '', cf: s.querySelectorAll('.cf').length, blocks: s.querySelectorAll('.pid-sheet').length }; }""" % PID_REQ)
    ck('P&ID 摘要組存在、不收合（<section>）、緊接在圖控 HMI 之前', bool(g) and g['tag'] == 'SECTION' and g['hmiIdx'] >= 0 and g['idx'] == g['hmiIdx'] - 1,
       g and (g['tag'], g['idx'], g['hmiIdx']))
    if not g:
        return False   # 這份資料沒有 P&ID（02.json 沒有 pid 組）：P&ID 的檢查全部做不了，只記上面這一筆
    if not g['blocks']:   # 有 P&ID 資料，但這一台查無（例如 OCR 對照表還沒做到這張圖）：這個函式其餘的檢查跳過，多張圖紙／查無那幾段照跑
        ck('P&ID：測試位號 %s 有圖紙區塊（沒有的話典型圖／幾何／燈箱這一段跳過）' % PID_TYP, False, g['bar'] or (g['cf'], g['blocks']))
        return True
    if g:
        ck('P&ID 摘要組佔整列寬（不是半格）', abs(g['gap']) <= 1, g['gap'])
        ck('P&ID 標頭：圖號＋版次、PDF 頁次、圖上實際畫的字', all(x in g['head'] for x in ('HT0-1-KND01-D0027', 'Rev.', 'PDF 第 2', '=G11HSD10QN101')), g['head'][:200])
        ck('圖上畫的是另一台（典型圖）＋OCR 定位都寫在短籤，而且不是紅字（那是圖面的畫法，不是錯誤）',
           '典型圖' in g['cap'] and 'OCR' in g['cap'] and g['warn'] is False, (g['cap'], g['warn']))
        ck('P&ID 的 PDF 連結開雲端硬碟（新分頁、noopener），旁邊講明影像不是正本',
           bool(g['link']) and g['link'][0].startswith('https://drive.google.com/open?id=') and g['link'][1] == '_blank' and 'noopener' in (g['link'][2] or '')
           and '開啟 PDF' in g['link'][3] and 'PDF 正本為準' in g['bar'], (g['link'], g['bar'][:80]))
        ck('P&ID 摘要組只有標頭＋連結＋影像（五個欄位與逐格來源在完整資料區）', g['cf'] == 0 and g['blocks'] == 1, (g['cf'], g['blocks']))
        ck('P&ID 圖紙影像不在開卡時抓（這一組還在第一屏以下：0 次請求、只有佔位框）',
           g['top'] > g['vh'] and g['req'] == 0 and g['img'] == 0 and g['ph'] == 1, (g['top'], g['vh'], g['req'], g['img'], g['ph']))
    page.evaluate("document.querySelector('.sum-pid').scrollIntoView({block: 'center'})")
    page.wait_for_function(PID_IMG % '.sum-pid', timeout=30000); page.wait_for_timeout(400)   # 400ms：ResizeObserver 把小地圖的藍框算好
    ex = page.evaluate("""(() => { const v = AMS.router.current(); const e = v.aux.sec.pid.rows[0][4]; const s = v.auxIx.pid.sheets[e.s] || {};
      return { s: e.s, m: e.marks, w: s.w, h: s.h, file: s.file, d: e.d, doc: s.doc, rev: s.rev, p: e.p }; })()""")
    geo = page.evaluate(PID_GEOM, '.sum-pid')
    ck('標記 ① 的絕對位置（%s：左 %.4f、上 %.4f，容差 ±%.3f）——轉正角或座標換算錯了這一筆會紅' % PID_PIN,
       ex['s'] == PID_PIN[0] and abs(ex['m'][0][0] - PID_PIN[1]) <= PID_PIN[3] and abs(ex['m'][0][1] - PID_PIN[2]) <= PID_PIN[3], (ex['s'], ex['m'][0]))
    ck('捲到才抓：圖紙影像正好 1 次請求（細部視窗與小地圖共用同一張）', geo['req'] == 1 and geo['imgs'] == 2, (geo['req'], geo['imgs']))
    ck('圖紙影像以 blob URL 解密載入，長寬與 index.pid.sheets 相符', geo['src'] == 'blob:' and geo['nat'] == [ex['w'], ex['h']] and ex['file'] == 'card/pid/' + ex['s'] + '.json',
       (geo['src'], geo['nat'], ex['w'], ex['h'], ex['file']))
    ck('細部視窗的比例＝--pid-k（舞台寬 ÷ 影像寬），而且夠大（≥ 0.75：圖上的字要讀得到）',
       bool(geo['k']) and geo['k'] >= 0.75 and abs(geo['sw'] / ex['w'] - geo['k']) < 0.005, (geo['k'], geo['sw'], ex['w']))
    # 幾何：標記 ① 的中心要在細部視窗裡、而且對準正中央；位號靠圖紙邊緣時舞台貼齊視窗邊（那一個方向就不在中央）
    ck('標記 ① 在細部視窗內，對準正中央（差 ≤ 12px；靠圖邊時改看舞台貼齊視窗邊）',
       geo['inside'] and (abs(geo['dx']) <= 12 or geo['edgeX']) and (abs(geo['dy']) <= 12 or geo['edgeY']), (geo['dx'], geo['dy'], geo['edgeX'], geo['edgeY']))
    ck('標記以百分比疊在舞台上，位置＝資料的 marks[0]', abs(geo['fx'] - ex['m'][0][0]) < 0.002 and abs(geo['fy'] - ex['m'][0][1]) < 0.002 and '%' in geo['style'],
       (geo['fx'], geo['fy'], ex['m'][0], geo['style']))
    ck('有框的標記只畫外框線：不填色、沒有中心圈，框線在字框外面（位號那幾個字要讀得到）',
       geo['boxed'] and geo['bg'] in ('rgba(0, 0, 0, 0)', 'transparent') and geo['rings'] == 0
       and geo['mw'] >= ex['m'][0][2] * geo['sw'] + 8 and geo['mh'] >= ex['m'][0][3] * geo['sh'] + 6, (geo['bg'], geo['rings'], geo['mw'], geo['mh']))
    ck('小地圖的紅圈在同一個比例位置（差 ≤ 2px）', geo['dot'] is not None and abs(geo['dot'][0] - ex['m'][0][0]) * geo['miniW'] <= 2 and abs(geo['dot'][1] - ex['m'][0][1]) * geo['miniH'] <= 2,
       (geo['dot'], ex['m'][0][:2]))
    ck('小地圖的藍框＝細部視窗的範圍：在小地圖內、框住紅圈、大小對得上', geo['rectIn'] and geo['dotInRect']
       and abs(geo['rect'][0] - geo['vw'] / geo['sw']) < 0.02 and abs(geo['rect'][1] - geo['vh'] / geo['sh']) < 0.02, (geo['rect'], geo['vw'] / geo['sw'], geo['vh'] / geo['sh']))
    ck('圖紙影像的 alt 寫出版次、PDF 頁次、圖上標示、對應方式與「以 PDF 正本為準」',
       all(x in geo['alt'] for x in ('Rev.', 'PDF 第 2 頁', '=G11HSD10QN101', '典型圖', 'OCR', 'PDF 正本為準')), geo['alt'][:240])
    shot(page, ctx, 'card_pid')
    # 燈箱：開啟時對準標記、一個影像像素一個 CSS 像素；滾輪以游標為定點縮放（改舞台寬，不是 transform: scale）、拖曳平移、全圖、回到標記
    page.locator('.sum-pid .pid-shot').first.click()
    page.wait_for_function(PID_IMG % '.pid-lb', timeout=30000); page.wait_for_timeout(300)
    lb = page.evaluate(PID_GEOM, '.pid-lb')
    ck('點細部視窗開 P&ID 燈箱：對準標記 ①（差 ≤ 12px）、原尺寸、不再抓一次影像',
       page.locator('.hmi-lb.pid-lb').count() == 1 and (abs(lb['dx']) <= 12 or lb['edgeX']) and (abs(lb['dy']) <= 12 or lb['edgeY'])
       and abs(lb['sw'] / ex['w'] - 1) < 0.01 and lb['req'] == 1,
       (lb['dx'], lb['dy'], lb['sw'], lb['req']))
    ck('P&ID 燈箱的 ✕ 不疊在圖上（在工具列裡）、工具列有 − ＋ 全圖 回到標記',
       page.evaluate("getComputedStyle(document.querySelector('.pid-lb .modal-x')).position") == 'static'
       and page.evaluate("[...document.querySelectorAll('.pid-lb .pid-tools button[data-z]')].map(b => b.dataset.z).join(',')") == 'out,in,fit,mark')
    vb = page.evaluate("(() => { const r = document.querySelector('.pid-lb .pid-view').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
    px, py = vb[0] + 150, vb[1] + 80
    pt = "(([x, y]) => { const s = document.querySelector('.pid-lb .pid-stage').getBoundingClientRect(); return [(x - s.left) / s.width, (y - s.top) / s.height, s.width]; })"
    page.mouse.move(px, py)
    p0 = page.evaluate(pt, [px, py])
    page.mouse.wheel(0, -300); page.wait_for_timeout(400)
    p1 = page.evaluate(pt, [px, py]); z1 = page.evaluate(PID_GEOM, '.pid-lb')
    ck('滾輪放大：舞台變寬，游標底下的圖紙位置不動（差 ≤ 2px）',
       p1[2] > p0[2] * 1.2 and abs(p1[0] - p0[0]) * p1[2] <= 2 and abs(p1[1] - p0[1]) * p1[2] * ex['h'] / ex['w'] <= 2, (p0, p1))
    ck('放大是改舞台的寬度（不是 transform: scale）：框線粗細不變、框跟著字變大',
       z1['tf'] == 'none' and z1['bw'] == lb['bw'] and z1['mw'] > lb['mw'] * 1.2, (z1['tf'], z1['bw'], lb['bw'], z1['mw'], lb['mw']))
    page.mouse.move(vb[0], vb[1]); page.mouse.down(); page.mouse.move(vb[0] + 120, vb[1] + 70, steps=5); page.mouse.up(); page.wait_for_timeout(300)
    d1 = page.evaluate(PID_GEOM, '.pid-lb')
    ck('拖曳平移：舞台跟著移動（120, 70），燈箱沒有被關掉',
       abs((d1['sl'] - z1['sl']) - 120) <= 2 and abs((d1['st'] - z1['st']) - 70) <= 2 and page.locator('.pid-lb').count() == 1, (d1['sl'] - z1['sl'], d1['st'] - z1['st']))
    page.locator('.pid-lb button[data-z="fit"]').click(); page.wait_for_timeout(300)
    f1 = page.evaluate(PID_GEOM, '.pid-lb')
    ck('「全圖」：整張圖紙縮進視窗、標記還在圖上，小地圖收起來', f1['sw'] <= f1['vw'] + 1 and f1['sh'] <= f1['vh'] + 1 and f1['inside'] and f1['miniW'] == 0,
       (f1['sw'], f1['vw'], f1['sh'], f1['vh'], f1['miniW']))
    page.locator('.pid-lb button[data-z="mark"]').click(); page.wait_for_timeout(300)
    m1 = page.evaluate(PID_GEOM, '.pid-lb')
    ck('「回到標記」：回到原尺寸並對準標記', (abs(m1['dx']) <= 12 or m1['edgeX']) and (abs(m1['dy']) <= 12 or m1['edgeY']) and abs(m1['sw'] / ex['w'] - 1) < 0.01,
       (m1['dx'], m1['dy'], m1['sw']))
    shot(page, ctx, 'card_pid_lightbox')
    page.keyboard.press('Escape'); page.wait_for_timeout(300)
    ck('P&ID 燈箱 Esc 關得掉、不留 modal-open', page.locator('.pid-lb').count() == 0 and not page.evaluate("document.body.classList.contains('modal-open')"))
    h0 = page.evaluate('location.hash')
    page.locator('.sum-pid .pid-shot').first.click(); page.wait_for_timeout(400)
    page.go_back(); page.wait_for_timeout(600)
    ck('P&ID 燈箱：返回鍵只關燈箱、留在同一張卡', page.locator('.pid-lb').count() == 0 and page.evaluate('location.hash') == h0, (page.evaluate('location.hash'), h0))
    # 完整資料區：同一塊圖紙（同一張影像，不再抓）＋五個欄位與逐格來源；第一列連到同一份 PDF
    page.evaluate("document.querySelector('details.cq-more').open = true")
    page.evaluate("document.querySelector('.aux-pid').scrollIntoView({block: 'start'})")
    page.wait_for_function(PID_IMG % '.aux-pid', timeout=30000); page.wait_for_timeout(300)
    aux = page.evaluate("""(() => { const a = document.querySelector('.aux-pid');
      return { labels: [...a.querySelectorAll('.hmi-f .cf .cf-k')].map(e => e.textContent), src: a.querySelectorAll('.hmi-f .src-dot').length,
               href: (a.querySelector('.hmi-f .cf a.doclk') || {}).href || '', bar: (a.querySelector('.pid-bar a') || {}).href || '',
               note: (a.querySelector('.aux-note') || {}).textContent || '', req: %s }; })()""" % PID_REQ)
    ag = page.evaluate(PID_GEOM, '.aux-pid')
    ck('完整資料區有同一塊圖紙（標記照樣對準），影像沒有再抓一次', ag['inside'] and (abs(ag['dx']) <= 12 or ag['edgeX']) and (abs(ag['dy']) <= 12 or ag['edgeY']) and aux['req'] == 1,
       (ag['dx'], ag['dy'], aux['req']))
    ck('完整資料區有五個欄位與逐格來源', aux['labels'] == ['P&ID 圖面', '圖面頁次', '所在位置', '圖上標示', '對應方式'] and aux['src'] == 5, (aux['labels'], aux['src']))
    ck('「P&ID 圖面」那一列與「開啟 PDF」連到同一份雲端硬碟檔', aux['href'].startswith('https://drive.google.com/open?id=') and aux['href'] == aux['bar'], (aux['href'], aux['bar']))
    ck('區段說明講明影像不是正本、圖上標示可能是另一台、文字層與 OCR 的差別', all(x in aux['note'] for x in ('PDF 為準', '典型圖', 'OCR')), aux['note'][:120])
    # 說明文字現行語料走不到的路徑（OCR 辨識信心偏低才用紅字；pid_index 的門檻是 0.75），直接打 prototype 守住
    low = page.evaluate("""(() => { const P = AMS.CardView.prototype; const e = {drawn: '=G11XXX10BT001', unit: 'G11', rel: 'typical', how: 'ocr', conf: 0.76};
      return { low: P.pidLowConf(e), ok: P.pidLowConf(Object.assign({}, e, {conf: 0.93})), txt: P.pidLowConf({how: 'text'}),
               cap: P.pidCapText({}, e), src: P.pidSrcText({rev: '4', page: 2, pages: 3}, e, {}) }; })()""")
    ck('OCR 辨識信心偏低（< 0.8）才出聲：短籤與說明都有 ⚠ 與信心值', low['low'] is True and low['ok'] is False and low['txt'] is False
       and '⚠' in low['cap'] and '0.76' in low['cap'] and '⚠' in low['src'] and 'PDF 正本為準' in low['src'], low)
    return True


def pid_wording(page, ctx, ck):
    """標頭短籤的說法（card.js pidCapBits／pidLow／pidRefCode／pidRefOthers／pidSrcText）直接打 prototype：每一種情形都釘住，不靠現行資料剛好有。
    引用（note 1～4）講明不是儀器符號；紅字看整張圖最低的辨識信心並點名是哪幾處；ocr-fix 講字元經校正；圖上的字一律當文字插入。"""
    w = page.evaluate("""(() => { const P = AMS.CardView.prototype; const M = (n) => Array.from({length: n}, (_, i) => [0.1 * (i + 1), 0.5, 0.02, 0.004]);
      const bits = (e) => P.pidCapBits(e);
      const o = { ref: {}, };
      for (const c of [1, 2, 3, 4, 9]) o.ref[c] = bits({drawn: 'X', rel: 'exact', how: 'text', note: c, notes: [c], marks: M(1)}).ref;
      o.sym = bits({drawn: 'X', rel: 'exact', how: 'text', marks: M(1)});
      o.mixed = bits({drawn: 'X', rel: 'typical', unit: 'G11', how: 'text', note: 1, notes: [3, 2], marks: M(2)}).ref;      // 幾處種類不同：note 只給 1，要以 notes[0] 為準
      o.legacy = bits({drawn: 'X', rel: 'exact', how: 'text', note: 1, marks: M(1)}).ref;                                    // 舊資料沒有 notes
      o.others = P.pidRefOthers({notes: [0, 2, 2, 1], marks: M(4)}); o.othersNone = P.pidRefOthers({notes: [2, 2], note: 2, marks: M(2)}) + P.pidRefOthers({marks: M(2)});
      const l3 = {drawn: 'X', rel: 'exact', how: 'ocr', conf: 0.881, conf_min: 0.772, confs: [0.881, 0.846, 0.772], marks: M(3)};
      o.low3 = { low: P.pidLow(l3), how: bits(l3).how, flag: P.pidLowConf(l3), src: P.pidSrcText({page: 5}, l3, {}) };
      const lt = {drawn: 'X', rel: 'exact', how: 'text', conf_min: 0.798, confs: [null, 0.798], marks: M(2)};
      o.lowText = { low: P.pidLow(lt), how: bits(lt).how, flag: P.pidLowConf(lt) };
      const ok3 = {drawn: 'X', rel: 'exact', how: 'ocr', conf: 0.95, conf_min: 0.81, confs: [0.95, 0.81, null], marks: M(3)};
      o.ok3 = { low: P.pidLow(ok3), how: bits(ok3).how, flag: P.pidLowConf(ok3) };
      o.oldMin = P.pidLow({how: 'text', conf_min: 0.7, marks: M(2)});                                                        // 只有 conf_min、沒有 confs：知道偏低、不知道是哪幾處
      const fx = {drawn: 'C10LAC50BP005', rel: 'exact', how: 'ocr', conf: 0.821, conf_min: 0.821, confs: [0.821], fix: 1, raw: 'C1OLAC50BPO05', marks: M(1)};
      o.fix = bits(fx);
      o.ocr = bits({drawn: '=G11X', rel: 'typical', unit: 'G11', how: 'ocr', conf: 0.912, conf_min: 0.912, confs: [0.912], marks: M(1)}).drawn;
      o.odd = bits({drawn: 'C10LAC50 BT044B', rel: 'exact', how: 'text', odd: 1, marks: M(1)}).drawn;
      o.train = bits({drawn: 'C10LAC50 BT022', rel: 'train', unit: 'LAC50', how: 'ocr', conf: 0.82, confs: [0.82], conf_min: 0.82, marks: M(1)}).drawn;
      o.conf = [P.pidConf(0.798), P.pidConf(0.7812), P.pidConf(0.912), P.pidConf(0.8)];
      // 圖上的字是資料：帶 HTML 的標籤要原樣顯示成文字，不能變成元素（整塊走 fillPid；圖紙鍵不存在 → 只有標頭與連結列，不抓圖）
      window.__pidx = 0; const bad = '<img src=x onerror="window.__pidx=1"><b>B</b>';
      const grid = document.createElement('div'); const v = AMS.router.current();
      v.fillPid({rows: [['P&ID 圖面', bad, 'doc', bad, {s: 'nope', g: 0, d: 'nope', p: 2, img: true, marks: M(2), drawn: bad, unit: bad, rel: 'typical', how: 'ocr', conf: 0.5, confs: [0.5, null], conf_min: 0.5, zone: bad, notes: [0, 2]}],
        ['圖上標示', bad, 'doc', bad, {s: 'nope', g: 0}], ['對應方式', bad, 'doc', bad, {s: 'nope', g: 0}]]}, v.auxIx, grid, v.currentMode(), false);
      o.xss = { imgs: grid.querySelectorAll('img, b').length, text: grid.textContent.indexOf('<img src=x') >= 0, cap: (grid.querySelector('.hmi-cap') || {}).textContent || '',
                title: (grid.querySelector('.hmi-cap') || {}).title || '', flag: window.__pidx };
      return o; })()""")
    ck('引用的標頭短籤：四種各有自己的說法，都講明不是儀器符號／不是儀器的位置；認不得的代碼也照樣出聲',
       all(k in w['ref'][str(c)] for c, k in ((1, '註記／表格'), (2, '跨圖訊號旗標'), (3, '用氣點'), (4, '迴路詳圖'))) and all('不是' in w['ref'][str(c)] for c in (1, 2, 3, 4, 9))
       and w['sym']['ref'] == '' and w['sym']['drawn'] == '圖上畫的是 X（就是本台）', (w['ref'], w['sym']))
    ck('同一張圖上幾處的種類不同（note 只會是 1）：短籤照 ① 自己的種類講（notes[0]）；舊資料沒有 notes 時看 note',
       '用氣點' in w['mixed'] and '註記' not in w['mixed'] and '註記／表格' in w['legacy'], (w['mixed'], w['legacy']))
    ck('① 是儀器符號、其餘幾處是引用：連結列點名是哪幾處、各是什麼；整張都是引用或沒有 notes 時不加這半句',
       '②③' in w['others'] and '跨圖訊號旗標' in w['others'] and '④' in w['others'] and '註記／表格' in w['others'] and '不是儀器符號' in w['others'] and w['othersNone'] == '', w['others'])
    ck('紅字看整張圖最低的辨識信心：① 0.88 沒問題、③ 0.77 偏低 → 出聲，而且點名 ③ 與它的信心值',
       w['low3']['low'] == [2] and w['low3']['flag'] is True and '⚠' in w['low3']['how'] and '① 0.88' in w['low3']['how'] and '③ 0.77 偏低' in w['low3']['how']
       and '圖上 ③' in w['low3']['src'], w['low3'])
    ck('① 是文字層、② 是偏低的 OCR：照樣出聲並點名 ②；0.798 不印成 0.80',
       w['lowText']['low'] == [1] and w['lowText']['flag'] is True and w['lowText']['how'].startswith('⚠ PDF 文字層') and '② 0.798 偏低' in w['lowText']['how'], w['lowText'])
    ck('各處都不低於 0.8：不出聲；只有 conf_min 的舊資料知道偏低但不亂指是哪一處', w['ok3']['low'] == [] and w['ok3']['flag'] is False and '⚠' not in w['ok3']['how'] and w['oldMin'] == [-1], (w['ok3'], w['oldMin']))
    ck('辨識信心的寫法：兩位小數，四捨五入後看不出低於門檻的多寫一位', w['conf'] == ['0.798', '0.78', '0.91', '0.80'], w['conf'])
    ck('ocr-fix：短籤講「OCR 校正後是…」與「字元經校正」，不當成圖上讀到的字', w['fix']['drawn'].startswith('OCR 校正後是 C10LAC50BP005') and '字元經校正' in w['fix']['how'] and '⚠' not in w['fix']['how'], w['fix'])
    ck('OCR 讀到的字講明是讀到的；同型各台寫出圖上畫的是哪一台；對不起來的 exact 不寫「就是本台」',
       w['ocr'].startswith('OCR 讀到的是 =G11X') and 'LAC50' in w['train'] and '同型各台' in w['train'] and '就是本台' not in w['odd'] and '請對照圖面' in w['odd'], (w['ocr'], w['train'], w['odd']))
    ck('圖上的字一律當文字插入：帶 HTML 的標籤不會變成元素、也不會執行', w['xss']['imgs'] == 0 and w['xss']['text'] and w['xss']['flag'] == 0 and '<img src=x' in w['xss']['cap'] and '<img src=x' in w['xss']['title'], w['xss'])


def pid_refs(page, ctx, ck):
    """現行資料裡的引用（note 1～4）各驗一台：那一張圖紙的標頭有粗體短籤講明這一處是什麼（不是紅字）、「圖上標示」「所在位置」的整句也講；
    整台設備每一張圖都只有引用時，最上面先說圖上沒有找到儀器符號。候選位號見 PID_REF_TAGS（資料變了、全部落空才失敗）。"""
    probe = """(code) => { const v = AMS.router.current(); const rows = (((v.aux || {}).sec || {}).pid || {}).rows || [];
      const heads = rows.filter(r => r[4] && r[4].marks).map(r => r[4]); const refOf = (e) => (Array.isArray(e.notes) && e.notes.length ? e.notes[0] : (e.note || 0));
      const gi = heads.findIndex(e => refOf(e) === code && !!e.note); if (gi < 0) return { gi, n: heads.length, codes: heads.map(refOf) };
      const blk = document.querySelectorAll('.sum-pid .pid-sheet')[gi]; const ref = blk && blk.querySelector('.hmi-head .pid-ref');
      const row = (k) => { const r = rows.find(r => r[4] && r[4].g === heads[gi].g && r[0] === k); return r ? String(r[1]) : ''; };
      return { gi, n: heads.length, allRef: heads.every(e => refOf(e) > 0), ref: ref ? ref.textContent : '', warn: ref ? ref.classList.contains('warn') : null,
               weight: ref ? parseInt(getComputedStyle(ref).fontWeight, 10) : 0, tip: ref ? ref.title : '', label: row('圖上標示'), pos: row('所在位置'),
               nosym: (document.querySelector('.sum-pid .pid-nosym') || {}).textContent || '', firstIsSym: refOf(heads[0]) === 0 }; }"""
    for code in sorted(PID_REF_TAGS):
        got, tag = None, None
        for tag in PID_REF_TAGS[code]:
            load_card(page, ctx, tag)
            got = page.evaluate(probe, code)
            if got['gi'] >= 0:
                break
        short, full = PID_REF_SAYS[code]
        if not got or got['gi'] < 0:
            ck('P&ID 引用代碼 %d：候選位號 %s 裡沒有一台的圖紙是這一種（資料變了就要換 PID_REF_TAGS）' % (code, '、'.join(PID_REF_TAGS[code])), False, got)
            continue
        ck('P&ID 引用代碼 %d（%s 第 %d 張圖紙）：標頭有粗體短籤講明「%s…不是…」，不是紅字' % (code, tag, got['gi'] + 1, short),
           short in got['ref'] and '不是' in got['ref'] and got['warn'] is False and got['weight'] >= 600, (got['ref'], got['warn'], got['weight']))
        ck('P&ID 引用代碼 %d（%s）：「圖上標示」整句講明這一處是什麼、「所在位置」講明不是儀器符號的位置，短籤的提示帶著整句' % (code, tag),
           full in got['label'] and '不是儀器符號的位置' in got['pos'] and full in got['tip'], (got['label'][-90:], got['pos'][-40:]))
        if got['allRef']:
            ck('P&ID 引用代碼 %d（%s）：整台設備只找到引用 → 最上面先說這次比對沒有讀到儀器符號（不說「圖上沒有」），整句也說' % (code, tag),
               '沒有讀到這支位號的儀器符號' in got['nosym'] and '不代表圖上沒有畫' in got['nosym'] and '沒有讀到這支位號的儀器符號' in got['label'],
               (got['nosym'][:40], got['label'][-40:]))
        else:
            ck('P&ID 引用代碼 %d（%s）：別張圖紙有儀器符號 → 有符號的那一張排第一、不印「沒有找到儀器符號」，整句指到另一張圖紙' % (code, tag),
               got['nosym'] == '' and got['firstIsSym'] and '另一張圖紙' in got['label'], (got['nosym'][:40], got['firstIsSym'], got['label'][-40:]))


def pid_lowconf(page, ctx, ck):
    """現行資料裡 OCR 辨識信心偏低的一張圖紙（extra.conf_min < 0.8）：標頭那一段是紅字、點名偏低的是哪幾處；同一張卡上其餘圖紙不紅。"""
    probe = """(() => { const v = AMS.router.current(); const rows = (((v.aux || {}).sec || {}).pid || {}).rows || []; const heads = rows.filter(r => r[4] && r[4].marks).map(r => r[4]);
      const blocks = [...document.querySelectorAll('.sum-pid .pid-sheet')];
      return heads.map((e, i) => { const h = blocks[i] && blocks[i].querySelector('.hmi-head .pid-how');
        return { min: typeof e.conf_min === 'number' ? e.conf_min : null, confs: e.confs || null, n: (e.marks || []).length, how: h ? h.textContent : '', warn: h ? h.classList.contains('warn') : null,
                 color: h ? getComputedStyle(h).color : '', muted: getComputedStyle(blocks[i].querySelector('.hmi-head .hmi-unit') || blocks[i]).color }; }); })()"""
    got, tag = [], None
    for tag in PID_LOW_TAGS:
        load_card(page, ctx, tag)
        got = page.evaluate(probe)
        if any(g['min'] is not None and g['min'] < 0.8 for g in got):
            break
    lows = [g for g in got if g['min'] is not None and g['min'] < 0.8]
    if not lows:
        ck('P&ID 辨識信心偏低：候選位號 %s 裡沒有一台有 conf_min < 0.8 的圖紙（資料變了就要換 PID_LOW_TAGS）' % '、'.join(PID_LOW_TAGS), False, got)
        return
    g = lows[0]
    idx = [i for i, c in enumerate(g['confs'] or []) if isinstance(c, (int, float)) and c < 0.8]
    named = all('①②③④⑤⑥⑦⑧'[i] in g['how'] for i in idx) if g['n'] > 1 else True
    ck('P&ID 辨識信心偏低（%s，conf_min %.3f）：標頭那一段是紅字，有 ⚠ 與「偏低」，多處標記時點名是哪幾處' % (tag, g['min']),
       g['warn'] is True and '⚠' in g['how'] and '偏低' in g['how'] and bool(idx) and named and g['color'] != g['muted'], g)
    ck('同一張卡上：紅字只給 conf_min < 0.8 的圖紙，其餘（文字層、信心夠的 OCR）不紅',
       all((x['warn'] is True) == (x['min'] is not None and x['min'] < 0.8) for x in got), [(x['min'], x['warn']) for x in got])


def pid_jk(page, ctx, ck):
    """JK 開頭的位號（HART 多工器模組）沒有列入 P&ID 比對：摘要與完整資料都說「不在比對範圍」，不是「查無」。"""
    load_card(page, ctx, PID_JK)
    if page.locator('.sum-pid').count() == 0:
        ck('P&ID：JK 位號 %s 的卡片有 P&ID 摘要組（查不到這一台就要換 PID_JK）' % PID_JK, False, page.locator('.cq-status').inner_text()[:80])
        return
    page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1200)
    s = page.inner_text('.sum-pid .cl-empty'); a = page.inner_text('.aux-pid .cl-empty') if page.locator('.aux-pid .cl-empty').count() else ''
    ck('JK 位號：摘要說「不在 P&ID 比對範圍」而且講 JK，不寫「查無」；短短一句', '不在 P&ID 比對範圍' in s and 'JK' in s and '查無' not in s and len(s) <= 60, s)
    ck('JK 位號：完整資料區也說不在比對範圍、不寫「查無」', '不在 P&ID 比對範圍' in a and '查無' not in a, a)


def pid_many(page, ctx, ck):
    """畫在多張圖紙上的設備（PID_MANY）：只先展開第一張（card.js PID_FOLD=1），其餘每塊收成 <details>，展開才抓那一張；多處標記的編號與「下一處」"""
    page.evaluate('performance.clearResourceTimings()')
    load_card(page, ctx, PID_MANY)
    page.evaluate("document.querySelector('.sum-pid').scrollIntoView({block: 'center'})")
    page.wait_for_function(PID_IMG % '.sum-pid', timeout=30000); page.wait_for_timeout(300)
    many = page.evaluate("""(() => { const s = document.querySelector('.sum-pid'); const d = [...s.querySelectorAll('details.pid-sheet')];
      return { n: d.length, all: s.querySelectorAll('.pid-sheet').length, open: d.filter(x => x.open).length, first: d.length ? d[0].open : null,
               loaded: s.querySelectorAll('.pid-view:not(.loading) img.pid-img').length, req: %s,
               note: (s.querySelector('.aux-note') || {}).textContent || '',
               marks: (AMS.router.current().aux.sec.pid.rows || []).filter(r => r[4] && r[4].marks).map(r => r[4].marks.length) }; })()""" % PID_REQ)
    ck('畫在多張圖紙上：每塊都是 <details>、只有第一張展開，影像也只抓第一張',
       many['n'] >= 2 and many['n'] == many['all'] == len(many['marks']) and many['open'] == 1 and many['first'] and many['loaded'] == 1 and many['req'] == 1, many)
    ck('有一句話說明為什麼只展開第一張（P&ID）', '先展開第 1 張' in many['note'] and str(many['n']) in many['note'], many['note'][:90])
    # 延後載入：第 2 張預設收合，點圖號那一列才展開、才抓那一張
    if many['n'] >= 2:
        blk2 = '.sum-pid details.pid-sheet:nth-of-type(2)'
        page.locator(blk2 + ' > summary.hmi-head').click()
        page.wait_for_function(PID_IMG % blk2, timeout=30000); page.wait_for_timeout(300)
        ck('點圖號那一列才展開並抓那一張（延後載入有效）',
           page.evaluate("document.querySelectorAll('.sum-pid .pid-view:not(.loading) img.pid-img').length") == 2 and page.evaluate(PID_REQ) == 2, page.evaluate(PID_REQ))
    # 多處標記的那一張圖紙：哪一張都可以（符號標籤所在的圖紙排第一，所以 2026-10-10 之後多半是展開著的第 1 張；之前是收合的第 2 張）
    gi = next((i for i, n in enumerate(many['marks']) if n > 1), -1)
    ck('測試位號仍有一張「多處標記」的圖紙（資料變了就要換 PID_MANY）', gi >= 0, many['marks'])
    if gi >= 0:
        blk = '.sum-pid details.pid-sheet:nth-of-type(%d)' % (gi + 1)
        if gi >= 2:   # 第 3 張以後的還收著：展開它
            page.locator(blk + ' > summary.hmi-head').click()
        page.wait_for_function(PID_IMG % blk, timeout=30000); page.wait_for_timeout(300)
        nos = page.evaluate("""(b => { const s = document.querySelector(b + ' .pid-stage'); const no = s.querySelector('.hmi-no'); const cs = no ? getComputedStyle(no) : null;
          return { nos: [...s.querySelectorAll('.hmi-no')].map(e => [e.textContent, e.classList.contains('pri')]),
                   boxes: [...s.querySelectorAll('.hmi-box, .hmi-mk')].map(e => e.classList.contains('pri')),
                   font: cs ? [parseFloat(cs.fontSize), cs.fontFamily, no.getBoundingClientRect().width, no.getBoundingClientRect().height] : null,
                   dots: document.querySelectorAll(b + ' .pid-mini .pid-dot').length, bar: document.querySelector(b + ' .pid-bar').innerText }; })""", blk)
        n = many['marks'][gi]
        ck('多處標記有編號 1、2…（一般數字），只有第一個是 .pri；小地圖每處一個紅圈；連結列講有幾處（文字裡照舊寫 ①②…）',
           [x[0] for x in nos['nos']] == [str(k + 1) for k in range(n)] and nos['nos'][0][1] and not any(x[1] for x in nos['nos'][1:])
           and nos['boxes'] == [True] + [False] * (n - 1) and nos['dots'] == n and ('有 %d 處' % n) in nos['bar'] and '①②' in nos['bar'], nos)
        # 編號牌讀不讀得出來（2026-10-10 稽核：11.5px 等寬粗體的圓圈數字在紅底上糊成一團）：字夠大、不是等寬字、牌子夠大
        ck('圖紙上的編號牌讀得出來：≥ 13px、不是等寬字、牌面 ≥ 18px',
           bool(nos['font']) and nos['font'][0] >= 13 and 'mono' not in nos['font'][1].lower() and nos['font'][2] >= 18 and nos['font'][3] >= 18, nos['font'])
        refs = page.evaluate("(g => { const e = AMS.router.current().aux.sec.pid.rows.filter(r => r[4] && r[4].marks)[g][4]; return e.notes || null; })", gi)
        if refs and refs[0] == 0 and any(refs[1:]):
            ck('① 是儀器符號、其餘幾處裡有引用：連結列點名是哪幾處、講明不是儀器符號', '不是儀器符號' in nos['bar'] and '是' in nos['bar'].split('細部對準 ①')[-1], nos['bar'])
        mg = page.evaluate(PID_GEOM, blk)
        ck('多處標記時細部視窗對準的是 ①', mg['inside'] and (abs(mg['dx']) <= 12 or mg['edgeX']) and (abs(mg['dy']) <= 12 or mg['edgeY']), (mg['dx'], mg['dy']))
        page.locator(blk + ' .pid-shot').click()
        page.wait_for_function(PID_IMG % '.pid-lb', timeout=30000); page.wait_for_timeout(300)
        nb = page.locator('.pid-lb button[data-z="next"]')
        ck('多處標記的燈箱有「下一處」', nb.count() == 1 and '②' in nb.inner_text(), nb.inner_text() if nb.count() else None)
        nb.click(); page.wait_for_timeout(300)
        n2 = page.evaluate("""(() => { const lb = document.querySelector('.pid-lb'), v = lb.querySelector('.pid-view').getBoundingClientRect();
          const b = lb.querySelectorAll('.pid-stage .hmi-box, .pid-stage .hmi-mk')[1].getBoundingClientRect(), s = lb.querySelector('.pid-stage').getBoundingClientRect();
          return { dx: b.left + b.width / 2 - (v.left + v.width / 2), dy: b.top + b.height / 2 - (v.top + v.height / 2),
                   edgeX: Math.abs(s.left - v.left) < 2 || Math.abs(s.right - v.right) < 2, edgeY: Math.abs(s.top - v.top) < 2 || Math.abs(s.bottom - v.bottom) < 2 }; })()""")
        ck('「下一處」把視窗移到標記 ②', (abs(n2['dx']) <= 12 or n2['edgeX']) and (abs(n2['dy']) <= 12 or n2['edgeY']), n2)
        page.keyboard.press('Escape'); page.wait_for_timeout(300)


def pid_none_leave(page, ctx, ck):
    """查無（PID_NONE）：摘要只印一句短的；完整資料區講比對範圍，數字取自 index.pid.stats（不寫死）；不抓任何圖紙。
    最後離開查詢卡：圖紙的 blob URL 與影像 JSON 一起收掉（core.js revokeHmiImages 同時清 card/hmi/ 與 card/pid/）——結束時停在 #/s/00。"""
    page.evaluate('performance.clearResourceTimings()')
    load_card(page, ctx, PID_NONE)
    page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1200)
    sum_none = page.inner_text('.sum-pid .cl-empty')
    ck('P&ID 查無：摘要只印一句短的', sum_none.strip() == '查無（現行 P&ID 圖面上找不到這個位號）' and len(sum_none) <= 30, sum_none)
    aux_none = page.inner_text('.aux-pid .cl-empty')
    pst = page.evaluate("AMS.router.current().auxIx.pid.stats")
    ck('P&ID 查無：完整資料區講比對範圍，數字取自 index.pid.stats（圖面份數、頁數、找得到的位號數）',
       aux_none.startswith('查無') and all(str(pst[k]) in aux_none for k in ('drawings', 'pages', 'located')), aux_none[:200])
    ck('P&ID 查無時不抓任何圖紙影像、也沒有圖紙區塊', page.evaluate(PID_REQ) == 0 and page.locator('.sum-pid .pid-sheet, .aux-pid .pid-sheet').count() == 0)
    # 記憶體：圖紙影像的 base64 JSON 在 blob 建好之後就不留在 D.cache（一張可達 400 KB）；換到用不到那張圖的設備時 blob 也收掉；
    # 下一台設備畫在同一張圖紙上時不重抓；離開查詢卡全部收掉。握著哪些 blob 看 AMS.data.imagesHeld()（core.js）。
    held_js = "({ blobs: AMS.data.imagesHeld('card/pid/'), json: [...AMS.data.cache.keys()].filter(k => k.indexOf('card/pid/') === 0) })"
    load_card(page, ctx, PID_MANY)
    page.evaluate("document.querySelector('.sum-pid').scrollIntoView({block: 'center'})")
    page.wait_for_function(PID_IMG % '.sum-pid', timeout=30000); page.wait_for_timeout(200)
    h1 = page.evaluate(held_js)
    ck('圖紙影像載入後：握著 1 個 blob，影像 JSON（base64）已經不在 D.cache', len(h1['blobs']) == 1 and not h1['json'], h1)
    load_card(page, ctx, PID_NONE); page.wait_for_timeout(300)
    h2 = page.evaluate(held_js)
    ck('換到沒有 P&ID 的設備：上一台的圖紙 blob 收掉', not h2['blobs'] and not h2['json'], h2)
    load_card(page, ctx, PID_TWIN)
    twin = page.evaluate("""(() => { const v = AMS.router.current(); const r = (((v.aux || {}).sec || {}).pid || {}).rows || []; const e = r.length ? r[0][4] : null;
      return e ? ((v.auxIx.pid.sheets[e.s] || {}).file || null) : null; })()""")
    if page.locator('.sum-pid .pid-sheet').count() and twin:
        page.evaluate("document.querySelector('.sum-pid').scrollIntoView({block: 'center'})")
        page.wait_for_function(PID_IMG % '.sum-pid', timeout=30000)
        page.evaluate('performance.clearResourceTimings()')
        load_card(page, ctx, PID_TYP)
        same = page.evaluate("(f => { const v = AMS.router.current(); const e = v.aux.sec.pid.rows[0][4]; return (v.auxIx.pid.sheets[e.s] || {}).file === f; })", twin)
        page.evaluate("document.querySelector('.sum-pid').scrollIntoView({block: 'center'})")
        page.wait_for_function(PID_IMG % '.sum-pid', timeout=30000); page.wait_for_timeout(200)
        h3 = page.evaluate(held_js)
        ck('兩台設備（%s → %s）畫在同一張圖紙上：換卡不重抓那張圖（0 次請求）、blob 還是那 1 個' % (PID_TWIN, PID_TYP),
           same and page.evaluate(PID_REQ) == 0 and h3['blobs'] == [twin] and not h3['json'], (same, page.evaluate(PID_REQ), h3))
    else:
        ck('P&ID：%s 有圖紙區塊（「同一張圖紙不重抓」那一筆要它；沒有就要換 PID_TWIN）' % PID_TWIN, False)
        load_card(page, ctx, PID_TYP)
        page.evaluate("document.querySelector('.sum-pid').scrollIntoView({block: 'center'})")
        page.wait_for_function(PID_IMG % '.sum-pid', timeout=30000)
    held = len(page.evaluate("AMS.data.imagesHeld('card/pid/')"))
    page.evaluate("location.hash = '#/s/00'"); page.wait_for_timeout(800)
    left = page.evaluate("[...AMS.data.cache.keys()].filter(k => k.indexOf('card/pid/') === 0 || k.indexOf('card/hmi/') === 0).concat(AMS.data.imagesHeld())")
    ck('離開查詢卡：圖紙與圖控畫面的 blob、影像 JSON 都不留', held >= 1 and not left and page.locator('.card-view').count() == 0, (held, left))


def pid_desktop(page, ctx, ck):
    """P&ID 圖面位置（CONTRACT.md「P&ID 圖面位置」）的桌機檢查。結束時停在別的頁面（#/s/00），呼叫端要自己把卡片載回來。"""
    if pid_typ(page, ctx, ck):
        pid_wording(page, ctx, ck)
        pid_many(page, ctx, ck)
        pid_refs(page, ctx, ck)
        pid_lowconf(page, ctx, ck)
        pid_jk(page, ctx, ck)
        pid_none_leave(page, ctx, ck)


def pid_mobile(page, ctx, ck, console):
    """手機：P&ID 圖紙（窄版面：小地圖疊在細部視窗角落、不蓋到標記；無橫向捲動；燈箱雙指開合縮放）"""
    n0 = len(console)
    load_card(page, ctx, PID_TYP)
    if page.locator('.sum-pid').count() == 0:
        ck('mobile: P&ID 摘要組存在（這份資料沒有 P&ID 的話這一段跳過）', False)
        return
    if page.locator('.sum-pid .pid-sheet').count() == 0:   # 這一台查無（見 pid_typ）：改用 PID_MANY 的第一張圖紙，手機版面的檢查照跑
        ck('mobile: P&ID 測試位號 %s 有圖紙區塊（沒有就改用 %s）' % (PID_TYP, PID_MANY), False)
        load_card(page, ctx, PID_MANY)
    page.evaluate("document.querySelector('.sum-pid').scrollIntoView({block: 'center'})")
    page.wait_for_function(PID_IMG % '.sum-pid', timeout=30000); page.wait_for_timeout(400)
    mg = page.evaluate(PID_GEOM, '.sum-pid')
    mo = page.evaluate("""(() => { const s = document.querySelector('.sum-pid'); const R = (e) => e.getBoundingClientRect();
      const v = R(s.querySelector('.pid-view')), mn = R(s.querySelector('.pid-mini')), b = R(s.querySelector('.pid-stage .hmi-box.pri, .pid-stage .hmi-mk.pri')), z = R(s.querySelector('.pid-view > .hmi-zoom'));
      const hit = (a, c) => !(a.right <= c.left || c.right <= a.left || a.bottom <= c.top || c.bottom <= a.top);
      return { narrow: !!document.querySelector('.cq-body.narrow'), miniIn: mn.width > 60 && mn.left >= v.left && mn.right <= v.right && mn.top >= v.top && mn.bottom <= v.bottom,
               miniOnMark: hit(mn, b), zoomOnMini: hit(z, mn), zoomOnMark: hit(z, b),
               sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }; })()""")
    ck('mobile: P&ID 細部視窗對準標記 ①（窄版面，差 ≤ 12px）', mo['narrow'] and mg['inside'] and (abs(mg['dx']) <= 12 or mg['edgeX']) and (abs(mg['dy']) <= 12 or mg['edgeY']),
       (mo['narrow'], mg['dx'], mg['dy']))
    ck('mobile: 小地圖疊在細部視窗的角落，不蓋到標記，「放大」也不跟兩者重疊', mo['miniIn'] and not mo['miniOnMark'] and not mo['zoomOnMini'] and not mo['zoomOnMark'], mo)
    ck('mobile: P&ID 卡片無橫向捲動', mo['sw'] <= mo['cw'], (mo['sw'], mo['cw']))
    shot(page, ctx, 'card_pid_mobile')
    page.locator('.sum-pid .pid-shot').first.tap()
    page.wait_for_function(PID_IMG % '.pid-lb', timeout=30000); page.wait_for_timeout(300)
    l0 = page.evaluate(PID_GEOM, '.pid-lb')
    ck('mobile: 點一下開 P&ID 燈箱，對準標記', (abs(l0['dx']) <= 12 or l0['edgeX']) and (abs(l0['dy']) <= 12 or l0['edgeY']), (l0['dx'], l0['dy'], l0['edgeX'], l0['edgeY']))
    op = page.evaluate("(() => { const bg = (s) => getComputedStyle(document.querySelector(s)).backgroundColor; return [bg('.pid-lb'), bg('.pid-lb .pid-tools')]; })()")
    ck('mobile: 燈箱背景與工具列完全不透明（底下頁面的字不能從工具列那一帶透上來）', all(c.startswith('rgb(') for c in op), op)
    vb = page.evaluate("(() => { const r = document.querySelector('.pid-lb .pid-view').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2 + 80]; })()")
    cdp = page.context.new_cdp_session(page)

    def touch(kind, pts):
        cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [{'x': x, 'y': y, 'id': i} for i, (x, y) in enumerate(pts)]})
    touch('touchStart', [(vb[0] - 30, vb[1]), (vb[0] + 30, vb[1])])
    for d in range(40, 101, 12):
        touch('touchMove', [(vb[0] - d, vb[1]), (vb[0] + d, vb[1])]); page.wait_for_timeout(30)
    touch('touchEnd', []); page.wait_for_timeout(300)
    l1 = page.evaluate(PID_GEOM, '.pid-lb')
    pz = page.evaluate("({ vv: window.visualViewport ? window.visualViewport.scale : 1, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth })")
    ck('mobile: 燈箱雙指開合放大的是圖紙（舞台變寬），不是整個頁面；框線粗細不變',
       l1['sw'] > l0['sw'] * 1.5 and pz['vv'] == 1 and l1['bw'] == l0['bw'] and page.locator('.pid-lb').count() == 1, (l0['sw'], l1['sw'], pz['vv']))
    ck('mobile: 燈箱開著也沒有橫向捲動', pz['sw'] <= pz['cw'], pz)
    page.locator('.pid-lb .modal-x').tap(); page.wait_for_timeout(300)
    ck('mobile: ✕ 關得掉 P&ID 燈箱', page.locator('.pid-lb').count() == 0 and not page.evaluate("document.body.classList.contains('modal-open')"))
    ck('mobile: P&ID 這一段沒有 console 錯誤／警告', not console[n0:], console[n0:][:3])


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
            # after_stock 的組（文件全文檢索）排在備品庫存之後且是最後一組；圖控 HMI 2026-10-05 起改排在備品庫存**之前**（使用者要求）
            ck('docsearch after stock（最後一組），圖控 HMI 緊接在備品庫存之前',
               info['stockIdx'] >= 0 and info['idx'] > info['stockIdx'] and info['idx'] == info['n'] - 1 and info['hmiIdx'] == info['stockIdx'] - 1,
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
        # ---- 圖控 HMI 畫面位置（CONTRACT.md v5）：摘要組（2026-10-05 起不收合、排在備品庫存之前、只有畫面標頭＋影像）與完整資料區都有縮圖＋標記
        page.evaluate('performance.clearResourceTimings()')
        load_card(page, ctx, HMI_TAG)
        # 摘要組的縮圖在渲染時就載（完整資料區 .cq-more 預設收合、展開是明確動作，仍延後載入，所以同一張圖只抓一次）。
        page.wait_for_function("(() => { const i = document.querySelector('.sum-hmi .hmi-img'); return i && i.complete && i.naturalWidth > 0; })()", timeout=30000)
        pre = page.evaluate("""(() => ({ req: performance.getEntriesByType('resource').filter(e => /\\/card\\/hmi\\//.test(e.name)).length,
          sumImg: document.querySelectorAll('.sum-hmi .hmi-img').length, auxImg: document.querySelectorAll('.cq-more .hmi-img').length,
          auxPh: document.querySelectorAll('.cq-more .hmi-frame.loading').length,
          moreOpen: document.querySelector('details.cq-more').open }))()""")
        ck('摘要組渲染時就載縮圖、完整資料區仍延後（同一張圖最多抓 1 次；命中快取時 0 次）',
           pre['req'] <= 1 and pre['sumImg'] >= 1 and pre['auxImg'] == 0 and pre['auxPh'] >= 1 and not pre['moreOpen'], pre)
        sum_hmi = page.inner_text('.sum-hmi')
        ck('摘要圖控組不收合（一開卡就看到圖，不是 <details>）',
           page.evaluate("(() => { const g = document.querySelector('.sum-hmi'); return g ? g.tagName : ''; })()") == 'SECTION')
        ck('摘要圖控組：畫面名稱＋導覽路徑', 'BOP_Feed_Water.cim' in sum_hmi and '›' in sum_hmi, sum_hmi[:80])
        ck('摘要圖控組顯示縮圖與標記', page.locator('.sum-hmi .hmi-img').count() >= 1 and page.locator('.sum-hmi .hmi-mk').count() == 2)
        # 版面精簡（2026-10-05 使用者要求）：摘要只留標頭＋圖，「所在位置／對應方式」與那段來源說明都只留在完整資料區
        # 一格都不能留（.cf）：'所在位置' 不可用文字判定——多處標記的 .sr-only 本來就會提到那一列在完整資料區哪裡
        ck('摘要圖控組不再印欄位與來源說明（只有標頭＋影像）',
           page.locator('.sum-hmi .hmi-f').count() == 0 and page.locator('.sum-hmi .cf').count() == 0
           and page.locator('.sum-hmi .aux-note').count() == 0 and '對應方式' not in sum_hmi, sum_hmi[:160])
        cap = page.inner_text('.sum-hmi .hmi-cap')
        ck('標頭短籤仍寫出擷取日期與「非即時值」（說明拿掉之後只剩這裡在講）', '2026-10-04' in cap and '非即時值' in cap, cap)
        lay = page.evaluate("""(() => { const g = document.querySelector('.sum-hmi'), s = g.querySelector('.hmi-screen');
          const im = s.querySelector('img.hmi-img').getBoundingClientRect(), fr = s.querySelector('.hmi-frame').getBoundingClientRect();
          return {gap: Math.round(g.getBoundingClientRect().width - g.parentElement.getBoundingClientRect().width),
                  imW: Math.round(im.width), dw: Math.round(im.width - fr.width),
                  auxN: document.querySelectorAll('.aux-hmi .hmi-screen').length,
                  auxF: document.querySelectorAll('.aux-hmi .hmi-f .cf').length,
                  auxSrc: document.querySelectorAll('.aux-hmi .hmi-f .src-dot').length}; })()""")
        ck('摘要圖控組佔整列寬（不是半格，右半不留空）', abs(lay['gap']) <= 1, lay)
        ck('摘要縮圖夠大（≥ 600px 寬，不是原本右半欄的小圖）', lay['imW'] >= 600, lay)
        # 數到真正的格子與來源點，不是只數 .hmi-f 這個容器（每塊畫面一個，永遠 >= 1 等於什麼都沒守到）
        ck('完整資料區仍有四個欄位與逐格來源', lay['auxN'] >= 1 and lay['auxF'] >= 4 and lay['auxSrc'] >= 1, lay)
        ck('縮圖貼齊標記框（標記位置才對得上）', abs(lay['dw']) <= 3, lay)
        ck('3 張以內不折疊（這台 1 張，整塊是 <div> 直接展開）', page.locator('.sum-hmi details.hmi-screen').count() == 0)
        # hmiCapText 另外兩條路徑現行語料走不到（43 個畫面全有執行時截圖、1298 組 0 次退回），直接打 prototype 守住文案
        cap_d = page.evaluate("AMS.CardView.prototype.hmiCapText({source: 'ThumbNail EMF'}, {})")
        ck('設計時影像的短籤講明是設計時、值是 ###', cap_d == '設計時影像（值＝###）', cap_d)
        cap_m = page.evaluate("AMS.CardView.prototype.hmiCapText({source: 'runtime', captured: '2026-10-04'}, {unit: 'H11.', mismatch: 'H12.'})")
        ck('挑不到本列機組時短籤要出聲（⚠＋是哪一組＋缺哪一組）',
           all(x in cap_m for x in ('⚠', '2026-10-04', '非即時值', 'H11.', '沒有 H12.')), cap_m)
        warn_css = page.evaluate("""(() => { let n = 0; for (const ss of document.styleSheets) { try {
          for (const r of ss.cssRules) if (r.selectorText && r.selectorText.includes('.hmi-cap.warn')) n++; } catch (e) {} } return n; })()""")
        ck('.hmi-cap.warn 有紅字樣式（出聲要看得出來）', warn_css >= 1, warn_css)
        page.locator('.sum-hmi .hmi-shot').first.click(); page.wait_for_timeout(500)
        ck('摘要縮圖也能點開燈箱', page.locator('.hmi-lb').count() == 1 and page.locator('.hmi-lb .hmi-mk').count() == 2)
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
        # 畫面多的卡只先展開第一張（2026-10-05 使用者指定「超過 3 張」）：其餘收成 <details>，影像跟著延後到展開才抓
        page.evaluate('performance.clearResourceTimings()')
        load_card(page, ctx, HMI_MANY)
        page.wait_for_function("(() => { const i = document.querySelector('.sum-hmi .hmi-img'); return i && i.complete && i.naturalWidth > 0; })()", timeout=30000)
        many = page.evaluate("""(() => ({ n: document.querySelectorAll('.sum-hmi details.hmi-screen').length,
          open: document.querySelectorAll('.sum-hmi details.hmi-screen[open]').length,
          img: document.querySelectorAll('.sum-hmi .hmi-img').length,
          req: performance.getEntriesByType('resource').filter(e => /\/card\/hmi\//.test(e.name)).length,
          note: (document.querySelector('.sum-hmi .aux-note') || {}).textContent || '' }))()""")
        ck('超過 3 張：每塊畫面都是 <details>、只有第一張展開，影像也只抓第一張',
           many['n'] >= 4 and many['open'] == 1 and many['img'] == 1 and many['req'] <= 1, many)
        ck('有一句話說明為什麼只展開第一張', '先展開第 1 張' in many['note'], many['note'][:90])
        page.locator('.sum-hmi details.hmi-screen:not([open]) > summary.hmi-head').first.click()
        page.wait_for_function("document.querySelectorAll('.sum-hmi .hmi-img').length >= 2", timeout=30000)
        ck('點畫面標題才展開並抓那一張（延後載入有效）', page.locator('.sum-hmi .hmi-img').count() == 2)
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
        # 摘要組不收合又緊貼備品庫存：沒有圖控畫面的設備只能印一句短的，掃描範圍留在完整資料區（2026-10-05 版面精簡）
        sum_ff = page.inner_text('.sum-hmi .cl-empty')
        ck('摘要的查無只印一句短的（掃描範圍留給完整資料）',
           len(sum_ff) <= 30 and '248' not in sum_ff and '473' not in sum_ff, (len(sum_ff), sum_ff))
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
        # ---- P&ID 圖面位置：檢查內容在上面的 pid_desktop()（位置、延後載入、幾何、燈箱、多張圖紙、查無）
        pid_desktop(page, ctx, ck)
        load_card(page, ctx, DOC_TAG)     # 還原成 P&ID 這一段之前的狀態：最近查過的順序（上一台＝DOC_TAG）、目前是 HMI_UNIT（＝FLAG_TAG）這張卡、完整資料展開
        load_card(page, ctx, HMI_UNIT)
        page.evaluate("document.querySelector('details.cq-more').open = true"); page.wait_for_timeout(1200)
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
        pid_mobile(page, ctx, ck, console)   # ---- 手機：P&ID 圖紙（檢查內容在上面的 pid_mobile()）
        ck('mobile: no page errors', not errors, errors[:3])
    # ---- 照網站的 CSP 執行（其餘測試都以 bypass_csp 略過 CSP，所以抓不到 CSP 違規）：圖控與 P&ID 的影像都是 blob URL、
    #      標記與舞台用行內 style 定位，在 index.html 的 CSP（img-src blob:、style-src 'unsafe-inline'、script-src 'self'）下必須照樣顯示。
    #      CSP 生效時 wait_for_function(字串) 會被 'unsafe-eval' 擋下，所以這一段用 page.evaluate 輪詢。
    with browser(ctx, csp=True) as (page, errors, console):
        def poll(expr, secs=60):
            for _ in range(int(secs * 10)):
                if page.evaluate('!!(' + expr + ')'):
                    return True
                page.wait_for_timeout(100)
            return False
        login(page, ctx)
        ck('CSP: index.html 帶 CSP，而且這個瀏覽器環境有照著擋（行內 script 不執行）', page.evaluate("""(() => {
          const m = document.querySelector('meta[http-equiv="Content-Security-Policy"]'); if (!m || !/img-src[^;]*blob:/.test(m.content)) return false;
          const s = document.createElement('script'); s.textContent = 'window.__cspInline = 1'; document.head.appendChild(s); s.remove(); return window.__cspInline !== 1; })()"""))
        page.wait_for_timeout(200)
        console[:] = [c for c in console if 'inline script' not in c[1]]   # 上面那一下故意踩 CSP 的訊息；其餘一則都不能有
        page.goto(ctx['base'] + '/db/#/card/' + HMI_TAG)     # 這一台同時有圖控畫面與 P&ID 圖紙
        ck('CSP: 查詢卡照常載入', poll(CARD_READY))
        ck('CSP: 圖控縮圖在 CSP 下照樣顯示', poll("(() => { const i = document.querySelector('.sum-hmi .hmi-img'); return i && i.complete && i.naturalWidth > 0; })()", 30))
        has_pid = page.locator('.sum-pid .pid-sheet').count() > 0
        ck('CSP: 這一台有 P&ID 圖紙區塊（沒有的話下面三筆跳過）', has_pid)
        if has_pid:
            page.evaluate("document.querySelector('.sum-pid').scrollIntoView({block: 'center'})")
            ck('CSP: P&ID 圖紙在 CSP 下照樣顯示（blob 影像）', poll(PID_IMG % '.sum-pid', 30))
            page.wait_for_timeout(400)
            cg = page.evaluate(PID_GEOM, '.sum-pid')
            ck('CSP: 行內 style 的定位有生效（標記在細部視窗內、對準中央或貼邊；小地圖藍框算得出來）',
               cg['inside'] and (abs(cg['dx']) <= 12 or cg['edgeX']) and (abs(cg['dy']) <= 12 or cg['edgeY']) and cg['rectIn'] and cg['dotInRect'], (cg['dx'], cg['dy'], cg['edgeX'], cg['edgeY'], cg['rect']))
            page.locator('.sum-pid .pid-shot').first.click()
            ck('CSP: P&ID 燈箱開得起來', poll(PID_IMG % '.pid-lb', 30))
            page.keyboard.press('Escape'); page.wait_for_timeout(300)
        ck('CSP: no page errors', not errors, errors[:3])
        ck('CSP: 沒有 CSP 違規或其他 console 錯誤／警告', not console, console[:3])
    return ck.fails
