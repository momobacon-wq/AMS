# -*- coding: utf-8 -*-
r"""tools/db/loc_image.py — 手冊插圖的圖片字（v24）：GE 維護手冊的插圖（3D 圖、照片、示意圖）上的標註寫著 GE 編號，例 GEK121811 大修手冊
Figure 10「Bearing Tunnel Close Out」的 'Proximity Probes (39VS-21/22)'、Figure 11（3D 剖視圖）的 'Vibration sensor on #2B (39V-2B)'——
這些字是點陣圖的一部分，PDF 文字層沒有，loc_ge.py（只讀文字層）找不到。本檔對 IMAGE_PAGES **明列的每一則標註**跑離線 OCR
（rapidocr-onnxruntime，與 pid_ocr.py 同一個引擎）確認圖上真的寫著那個編號，取得字框與辨識信心，寫成 <ge_tags_dir>/loc_image.json；
loc_ge.py 讀它併進位置圖（how='ocr'，卡片上是「OCR 讀圖」、等級推論，排在清單點名的位置圖之後）。

為什麼另寫一支、不在 loc_ge.py 裡 OCR：OCR 要 rapidocr、一頁幾秒，重建（rebuild.py）不該依賴它。照 pid_ocr.py --distill-ge → pid_ocr_ge.json
的先例：OCR 一次，結果帶來源 PDF 的 size／mtime，loc_ge 讀的時候核對，PDF 換了檔就整頁不用（loc_ge stats.image.stale）。
輸出放 GE 對照表的資料夾（paths.GE_TAGS 旁邊，與 wire_curated.json 同處），不進 repo。

== 為什麼明列每一則標註，而不是整頁自動找 ==
  整頁 OCR 的行框會把左右並排的兩則標註連成一行（GEK121811 p.20 兩張 3D 圖中間兩欄：「sensor on #2B」緊貼右欄的「(45FT-20A/B)」，
  p.19 的 '(39V-2A)' 與上一則黏在一起而漏掉），分則也分不準。所以每則標註明列：t＝圖上寫的編號字（或沒寫編號的片語）、w＝搜尋窗
  （頁面 0~1 比例，只框這則標註、不含隔壁欄）、phrase＝整則標註的原文（卡片「圖上標示」照寫：'… cabling (39VS-21/22)' 指的是電纜、
  不是探頭）、pt＝引線指著什麼（看圖寫的）。程式在窗內切行、切字、逐字辨識，**辨識出來的字經 pid_ge.expand_word 對到的編號必須
  包含這則標註的編號**才發布（stats.confirmed）；對不上的不發布、印出來（stats.unconfirmed）。框＝那個字的墨跡外框。
  keys：圖上沒寫編號的標註（Figure 11 的 'Proximity probe'）明列它指的是哪幾個編號、why 寫為什麼（form 'image-untagged'，卡片講明是推論）。
  --survey 另外整頁 OCR，列出窗外讀到、像 GE 編號的字（新圖或漏列的線索；只印不發布）。

== 收哪些頁（普查 2026-11-08）==
  GEK1218xx 系列（孔探 808、燃燒檢查 809、熱通道 810、大修 811，及 ge-scrape 下載的 800／824／825／843）每一頁有圖的都整頁 OCR：
  只有 811 p.19／p.20（#2 軸承通道儀器）與 808 p.14／p.15（IGV／VSV 致動器配置，809 p.31／p.32 是同一張圖）的插圖寫著 GE 編號而且是位置；
  800 p.15 是起動控制閥的控制示意圖（訊號名），不是位置，不收。808 的 DIGITAL POSITIONER 方塊（90EGV-1／2、90ESV-1／2）是示意，
  不是定位器裝在哪裡（它們在 DVP 盤），不列。內文（文字層）提到的編號（811 p.37「remove proximity probes (39VS-21, 39VS-22 …)」）
  是拆裝步驟、不是位置，也不收。

== 輸出 <ge_tags_dir>/loc_image.json（決定性：鍵排序、無時間戳、無本機絕對路徑）==
  {"kind":"loc_image","generated_by","version","engine":{rapidocr, zoom},
   "docs":{文件號:{rel,size,mtime,doc,rev,title,alts}},
   "pages":[{"doc","page","figure","view","hits":[{key, label（辨識出來的字）, t, read, form, phrase, pt, why?, box[x0,y0,x1,y1], conf}]}],
   "stats":{…}}
  box：頁面（這幾頁都是直式 0°）的 0~1 比例、左上與右下。

用法：
  py tools/db/loc_image.py              # 寫 <ge_tags_dir>\loc_image.json
  py tools/db/loc_image.py --survey     # 另外整頁 OCR，印出窗外讀到的 GE 編號形的字
"""
import argparse
import io
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pid_lib as L  # noqa: E402
import pid_index as PI  # noqa: E402
import pid_ge as PG  # noqa: E402
from build_card_aux import ge_cmp  # noqa: E402

GENERATED_BY = 'tools/db/loc_image.py'
VERSION = 1
ZOOM = 4.0
WORD_GAP = 0.45      # 切字：空白 ≥ 幾個行高
LINE_GAP = 1         # 切行：連續幾列沒有墨點就切開（像素）
INK = 140            # 灰階 < 這個值算墨點
MIN_LINE = 0.35      # 比最高的一行矮於這個比例的「行」是表格框線或引線，不辨識
PAD = 0.15           # 送辨識前四周補白（行高的比例）

# 引線指著什麼（pt）：2026-11-08 反方驗證兩個鏡頭（幾何／文字、引線語意）逐則放大看圖寫的。
# Figure 10 的引線都落在封板上的電纜／導管穿出接頭或穿孔（元件本體在封板前方的隧道內，Figure 10 看不到）；圖上沒寫由哪一側看，鐘點以圖面上方為 12 點。
# Figure 11 是兩張 3D 剖視圖（不是照片），機組相反兩側的鏡像視角；標「cabling／conduit」的指電纜或導管。
_PROX = ('圖上這則標註沒有寫編號；Figure 11 右圖另一則寫「Proximity Probes cabling (39VS-21/22)」，同一份手冊 p.37 寫 No. 2 軸承蓋上的近接探頭是 '
         '39VS-21、39VS-22（「in some cases」另有 39VS-23／24，對照表沒有這兩支；#1 軸承的 96VC、39VS-11／12 不在這裡）；左右兩圖可能各畫一支，'
         '也可能是同一支從兩側看，分不出是 21 還是 22')
_F10 = '（Figure 10 的引線指封板上的穿出點；%s）'
IMAGE_PAGES = {
    'GEK121811': {
        'pat': r'_GEK121811_rev[A-Z0-9]+\.pdf$', 'scope': 'G',
        'pages': {
            19: {'figure': 'Figure 10. Bearing Tunnel Close Out',
                 'view': '#2 軸承通道封板正視圖；圖上沒寫由哪一側看，鐘點以圖面上方為 12 點',
                 'callouts': [
                     {'t': '(45FT-21A/B)', 'w': [0.298, 0.5135, 0.381, 0.529], 'phrase': 'Fire detection (45FT-21A/B)',
                      'pt': '封板約 10 點鐘外緣、三角托架上的六角接頭，推論是火警偵測導管穿出封板處' + _F10 % '偵測器本體在隧道內，見 p.20 Figure 11；A／B 分不出'},
                     {'t': '(45FT-20A/B)', 'w': [0.662, 0.5135, 0.744, 0.529], 'phrase': 'Fire detection (45FT-20A/B)',
                      'pt': '封板約 2 點鐘外緣、三角托架上的六角接頭，推論是火警偵測導管穿出封板處' + _F10 % '偵測器本體在隧道內，見 p.20 Figure 11；A／B 分不出'},
                     {'t': '(39V-2B)', 'w': [0.3062, 0.5640, 0.360, 0.579], 'phrase': 'Vibration sensor on #2B (39V-2B)',
                      'pt': '封板約 8 點鐘、三孔一組的右上孔＝電纜穿出封板處' + _F10 % '感測器本體在 #2 軸承蓋頂上，見 p.20 Figure 11；「#2B」是 #2 軸承'},
                     {'t': '(39V-2A)', 'w': [0.688, 0.6855, 0.7425, 0.6995], 'phrase': 'Vibration sensor on #2B (39V-2A)',
                      'pt': '封板約 4 點鐘、白色六角接頭右側的小孔＝電纜穿出封板處' + _F10 % '感測器本體在 #2 軸承蓋頂上，見 p.20 Figure 11；「#2B」是 #2 軸承'},
                     {'t': 'BT-J2-2', 'w': [0.372, 0.6985, 0.420, 0.7095], 'phrase': '#2 Bearing Thermocouples: BT-J2-2',
                      'pt': '封板約 8 點鐘、三孔一組的左上孔＝熱電偶引線穿出封板處' + _F10 % '熱電偶埋在 #2 軸承裡'},
                     {'t': 'BT-J2-1', 'w': [0.372, 0.7105, 0.4175, 0.7225], 'phrase': '#2 Bearing Thermocouples: BT-J2-1',
                      'pt': '封板約 8 點鐘、三孔一組的下方孔＝熱電偶引線穿出封板處' + _F10 % '熱電偶埋在 #2 軸承裡'},
                     {'t': '(39VS-21/22)', 'w': [0.625, 0.7160, 0.706, 0.7300], 'phrase': 'Proximity Probes (39VS-21/22)',
                      'pt': '封板約 4～5 點鐘的白色六角接頭＝兩支探頭的電纜共用的穿出接頭' + _F10 % '探頭本體在 #2 軸承上，見 p.20 Figure 11 的「Proximity probe」'},
                 ]},
            20: {'figure': 'Figure 11. Bearing Tunnel Instrumentation',
                 'view': '#2 軸承通道的兩張 3D 剖視圖（不是照片），機組相反兩側的鏡像視角：左圖 AFT 在左，右圖 AFT 在右',
                 'callouts': [
                     {'t': '(39V-2A)', 'w': [0.5085, 0.1290, 0.556, 0.1395], 'phrase': 'Vibration sensor on #2B (39V-2A)',
                      'pt': '右圖 #2 軸承蓋頂上的黃色速度型振動感測器本體（「#2B」是 #2 軸承）'},
                     {'t': '(45FT-20A/B)', 'w': [0.839, 0.1388, 0.905, 0.1492], 'phrase': 'Fire detection conduit (45FT-20A/B)',
                      'pt': '右圖右上、封板後方的紅色火警偵測導管段（導管，不是偵測器本體）'},
                     {'t': '(45FT-21A/B)', 'w': [0.441, 0.1410, 0.5050, 0.1515], 'phrase': 'Fire detection (45FT-21A/B)',
                      'pt': '左圖 #2 軸承左上方接頭座伸出的兩支桿狀件（外形推論是偵測器本體；A／B 分不出）'},
                     {'t': '(45FT-21A/B)', 'w': [0.120, 0.1640, 0.1815, 0.1760], 'phrase': 'Fire detection conduit (45FT-21A/B)',
                      'pt': '左圖左上、封板後方的紅色火警偵測導管段（導管，不是偵測器本體）'},
                     {'t': '(45FT-20A/B)', 'w': [0.5078, 0.1815, 0.572, 0.1930], 'phrase': 'Fire detection (45FT-20A/B)',
                      'pt': '右圖 #2 軸承右上方接頭座伸出的兩支桿狀件（外形推論是偵測器本體；A／B 分不出）'},
                     {'t': '(39V-2B)', 'w': [0.441, 0.1918, 0.4845, 0.2015], 'phrase': 'Vibration sensor on #2B (39V-2B)',
                      'pt': '左圖 #2 軸承蓋頂上的黃色速度型振動感測器本體（「#2B」是 #2 軸承）'},
                     {'t': 'Proximity probe', 'w': [0.4455, 0.2148, 0.4935, 0.2345], 'phrase': 'Proximity probe',
                      'pt': '左圖 #2 軸承端面上斜裝的近接探頭本體', 'keys': ['GT|39VS-21', 'GT|39VS-22'], 'why': _PROX},
                     {'t': 'Proximity probe', 'w': [0.519, 0.2183, 0.567, 0.2380], 'phrase': 'Proximity probe',
                      'pt': '右圖 #2 軸承端面上斜裝的近接探頭本體', 'keys': ['GT|39VS-21', 'GT|39VS-22'], 'why': _PROX},
                     {'t': '(BT-J2-1/2)', 'w': [0.114, 0.2370, 0.169, 0.2470], 'phrase': '#2 Bearing Thermocouples cabling (BT-J2-1/2)',
                      'pt': '左圖封板上緣左側兩個電纜穿出接頭（熱電偶本體埋在 #2 軸承裡、圖上沒標；-1／-2 分不出）'},
                     {'t': '(39VS-21/22)', 'w': [0.838, 0.2466, 0.902, 0.2568], 'phrase': 'Proximity Probes cabling (39VS-21/22)',
                      'pt': '右圖封板上緣最上面的電纜穿出接頭（電纜，不是探頭本體；本體見同圖「Proximity probe」）'},
                     {'t': '(39V-2A)', 'w': [0.840, 0.2910, 0.885, 0.3012], 'phrase': 'Vibration sensor cabling (39V-2A)',
                      'pt': '右圖封板上、39VS 電纜接頭右下方的電纜穿出接頭（電纜，不是感測器本體）'},
                     {'t': '(39V-2B)', 'w': [0.440, 0.3104, 0.4840, 0.3205], 'phrase': 'Vibration sensor cabling (39V-2B)',
                      'pt': '左圖封板上緣一排接頭中的第二個（電纜穿出處，不是感測器本體）'},
                 ]},
        }},
    'GEK121808': {
        'pat': r'_GEK121808_rev[A-Z0-9]+\.pdf$', 'scope': 'G',
        'pages': {
            14: {'figure': 'Figure 2. IGV configuration from MLI 4088 Schematic',
                 'view': 'IGV 致動器配置示意（MLI 4088 系統示意圖、非比例；FORWARD LOOKING AFT＝由前往後看）',
                 'callouts': [
                     {'t': 'EGV-2', 'w': [0.2515, 0.3207, 0.2770, 0.3283], 'phrase': 'MBC / AE002 / EGV-2（IGV ACTUATOR 574A）',
                      'pt': '沒有引線：標籤緊貼左側那台 IGV 電動致動器——IGV 環左側，連桿約在 9 點鐘'},
                     {'t': 'EGV-1', 'w': [0.8300, 0.7440, 0.8565, 0.7520], 'phrase': 'MBC / AE001 / EGV-1（IGV ACTUATOR 574A）',
                      'pt': '沒有引線：標籤緊貼右側那台 IGV 電動致動器——IGV 環右側，連桿約在 3 點鐘'},
                 ]},
            15: {'figure': 'Figure 3. VSV configuration from MLI 4088 Schematic',
                 'view': 'VSV 致動器配置示意（MLI 4088 系統示意圖、非比例；FORWARD LOOKING AFT＝由前往後看）',
                 'callouts': [
                     {'t': 'ESV-2', 'w': [0.2005, 0.2548, 0.2255, 0.2650], 'phrase': 'MBC / AE004 / ESV-2（VSV ACTUATOR 574A）',
                      'pt': '沒有引線：標籤緊貼左上那台 VSV 電動致動器——經曲柄接左下方的扭力軸'},
                     {'t': 'ESV-1', 'w': [0.8595, 0.6814, 0.8828, 0.6892], 'phrase': 'MBC / AE003 / ESV-1（VSV ACTUATOR 574A）',
                      'pt': '沒有引線：標籤緊貼右下那台 VSV 電動致動器——經曲柄接右上方的扭力軸'},
                 ]},
        }},
}


def r5(v):
    return round(float(v), 5)


def resolve(lib, no, spec):
    """文件號 → 文件庫裡的那一份（copy_flags 沒有旗標的優先、路徑最短）。"""
    pat = re.compile(spec['pat'], re.I)
    cs = [(rel, size, mtime) for rel, size, mtime in lib if pat.search(rel.rsplit('/', 1)[-1])]
    if not cs:
        return None
    pool = [c for c in cs if not L.copy_flags(c[0])] or cs
    rel, size, mtime = min(pool, key=lambda c: (len(c[0]), c[0]))
    m = re.search(r'_rev([A-Z0-9]+)\.pdf$', rel, re.I)
    # 'MBA_MAJOR INSPECTION 7HA03_GEK121811_revA.pdf' → 'MAJOR INSPECTION 7HA03'（系統碼前綴與文件號、版次另有欄位）
    title = re.sub(r'^[A-Z]{3}_|_GEK\d+_rev[A-Z0-9]+$', '', re.sub(r'\.pdf$', '', rel.rsplit('/', 1)[-1], flags=re.I))
    return {'rel': rel, 'size': size, 'mtime': mtime, 'doc': no, 'rev': m.group(1).upper() if m else '', 'title': title, 'alts': len(cs) - 1,
            'scope': spec['scope']}


def runs(mask, gap):
    """一維墨點遮罩 → [(起, 迄)]：連續 ≥ gap 個空白就切開。"""
    out, start, last, blank = [], None, 0, 0
    for i, v in enumerate(mask):
        if v:
            if start is None:
                start = i
            last, blank = i, 0
        elif start is not None:
            blank += 1
            if blank >= gap:
                out.append((start, last + 1))
                start, blank = None, 0
    if start is not None:
        out.append((start, last + 1))
    return out


def window_words(gray, win):
    """搜尋窗（像素 x0,y0,x1,y1）→ [(字框像素, 灰階切圖)]：先切行、再切字。"""
    import numpy as np
    x0, y0, x1, y1 = win
    ink = gray[y0:y1, x0:x1] < INK
    lines = runs(ink.any(axis=1), LINE_GAP)
    if not lines:
        return []
    hmax = max(b - a for a, b in lines)
    out = []
    for a, b in lines:
        h = b - a
        if h < MIN_LINE * hmax:
            continue
        for c, d in runs(ink[a:b].any(axis=0), max(2, int(WORD_GAP * h))):
            sub = ink[a:b, c:d]
            rows = np.nonzero(sub.any(axis=1))[0]
            ty0, ty1 = y0 + a + int(rows[0]), y0 + a + int(rows[-1]) + 1
            bx = (x0 + c, ty0, x0 + d, ty1)
            p = max(2, int(PAD * (ty1 - ty0)))
            crop = gray[max(0, ty0 - p):ty1 + p, max(0, bx[0] - p):bx[2] + p]
            out.append((bx, np.stack([crop] * 3, axis=-1)))
    return out


def norm_phrase(s):
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper())


def read_callouts(eng, page, spec_page, scope, names, ents, st, log):
    import fitz
    import numpy as np
    W, Hp = page.rect.width, page.rect.height
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csGRAY)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    hits = []
    for co in spec_page['callouts']:
        w = co['w']
        win = (int(w[0] * W * ZOOM), int(w[1] * Hp * ZOOM), int(w[2] * W * ZOOM) + 1, int(w[3] * Hp * ZOOM) + 1)
        words = window_words(gray, win)
        rec = eng.text_recognizer([c for _b, c in words])[0] if words else []
        got = [(b, t.strip(), float(s)) for (b, _c), (t, s) in zip(words, rec) if t.strip()]
        if co.get('keys'):                          # 沒寫編號的片語：窗內各行串起來要等於 t
            text = ' '.join(t for _b, t, _s in got)
            if norm_phrase(text) != norm_phrase(co['t']):
                st['unconfirmed'] += 1
                log('!! 未確認：%s p.%s 「%s」窗內讀到「%s」' % (spec_page['figure'], '', co['t'], text))
                continue
            bx = (min(b[0] for b, _t, _s in got), min(b[1] for b, _t, _s in got), max(b[2] for b, _t, _s in got), max(b[3] for b, _t, _s in got))
            conf = min(s for _b, _t, s in got)
            for k in co['keys']:
                if k not in ents:
                    sys.exit('loc_image：明列的編號 %s 不在對照表' % k)
                hits.append({'key': k, 'label': text, 't': co['t'], 'read': '', 'form': 'image-untagged', 'phrase': co['phrase'], 'pt': co.get('pt', ''),
                             'why': co.get('why', ''), 'box': [r5(bx[0] / ZOOM / W), r5(bx[1] / ZOOM / Hp), r5(bx[2] / ZOOM / W), r5(bx[3] / ZOOM / Hp)],
                             'conf': round(conf, 3)})
            st['confirmed'] += 1
            continue
        want = {k for keys, _rd, _f in PG.expand_word(co['t'], scope, names, Counter()) for k in keys}
        if not want:
            sys.exit('loc_image：明列的標註字 %r 對不到對照表的任何編號' % co['t'])
        found = None
        for b, t, s in got:
            reads = PG.expand_word(t, scope, names, Counter())
            ks = {k for keys, _rd, _f in reads for k in keys}
            if want <= ks:
                found = (b, t, s, reads)
                break
        if not found:
            st['unconfirmed'] += 1
            log('!! 未確認：%s「%s」窗內讀到 %s' % (spec_page['figure'], co['t'], [t for _b, t, _s in got]))
            continue
        b, t, s, reads = found
        for keys, rd, form in reads:
            for k in keys:
                if k not in want:
                    continue
                hits.append({'key': k, 'label': t, 't': co['t'], 'read': rd, 'form': 'image-slash' if form == 'text-slash' else 'image',
                             'phrase': co['phrase'], 'pt': co.get('pt', ''),
                             'box': [r5(b[0] / ZOOM / W), r5(b[1] / ZOOM / Hp), r5(b[2] / ZOOM / W), r5(b[3] / ZOOM / Hp)], 'conf': round(s, 3)})
        st['confirmed'] += 1
    hits.sort(key=lambda h: (h['box'][1], h['box'][0], h['key']))
    return hits, gray


def survey(eng, page, gray, hits_windows, scope, names, log):
    """整頁 OCR：窗外讀到、對得到對照表的字 → 印出來（只當線索）。"""
    import numpy as np
    W, Hp = page.rect.width, page.rect.height
    tl = page.get_text('words')
    res, _ = eng(np.stack([gray] * 3, axis=-1))
    n = 0
    for box, text, score in (res or []):
        xs = [p[0] / ZOOM for p in box]
        ys = [p[1] / ZOOM for p in box]
        fx0, fy0, fx1, fy1 = min(xs), min(ys), max(xs), max(ys)
        if any(not (w[2] <= fx0 or fx1 <= w[0] or w[3] <= fy0 or fy1 <= w[1]) for w in tl):
            continue
        for tok in re.findall(r'[A-Z0-9][A-Z0-9\-/,]*[A-Z0-9]', text.upper().replace(' ', '')):
            for keys, _rd, _f in PG.expand_word(tok, scope, names, Counter()):
                cx, cy = (fx0 + fx1) / 2 / W, (fy0 + fy1) / 2 / Hp
                inside = any(w[0] <= cx <= w[2] and w[1] - 0.02 <= cy <= w[3] + 0.02 for w in hits_windows)
                if not inside:
                    n += 1
                    log('   survey：窗外 %s（%.3f, %.3f）「%s」%.2f' % ('、'.join(keys), cx, cy, text, float(score)))
    return n


def build(a, log):
    try:
        from importlib import metadata
        from rapidocr_onnxruntime import RapidOCR
        ver = metadata.version('rapidocr-onnxruntime')
    except Exception:  # noqa: BLE001
        sys.exit('找不到 rapidocr-onnxruntime（py -m pip install rapidocr-onnxruntime）')
    import fitz
    ents, names, _est = PG.load_entries(a.ge_tags)
    lib = L.walk_pdfs(a.library)
    eng = RapidOCR()
    st = Counter()
    docs, pages = {}, []
    for no in sorted(IMAGE_PAGES):
        spec = IMAGE_PAGES[no]
        d = resolve(lib, no, spec)
        if not d:
            log('!! 文件庫裡找不到 %s' % no)
            st['doc_missing'] += 1
            continue
        docs[no] = d
        pdf = fitz.open(os.path.join(a.library, d['rel'].replace('/', os.sep)))
        for pno in sorted(spec['pages']):
            sp = spec['pages'][pno]
            page = pdf[pno - 1]
            if page.rotation:
                sys.exit('loc_image：%s p.%d 有轉向（%d°），這支只處理直式頁' % (no, pno, page.rotation))
            hits, gray = read_callouts(eng, page, sp, spec['scope'], names, ents, st, log)
            pages.append({'doc': no, 'page': pno, 'figure': sp['figure'], 'view': sp.get('view', ''), 'hits': hits})
            log('%s p.%d（%s）：明列 %d 則、確認 %d 處、%d 個編號' % (no, pno, sp['figure'], len(sp['callouts']), len(hits), len({h['key'] for h in hits})))
            if a.survey:
                st['survey_outside'] += survey(eng, page, gray, [c['w'] for c in sp['callouts']], spec['scope'], names, log)
    st['hits'] = sum(len(p['hits']) for p in pages)
    return {'kind': 'loc_image', 'generated_by': GENERATED_BY, 'version': VERSION, 'engine': {'rapidocr': ver, 'zoom': ZOOM},
            'params': {'word_gap': WORD_GAP, 'ink': INK, 'min_line': MIN_LINE},
            'docs': docs, 'pages': pages, 'stats': {k: int(v) for k, v in sorted(st.items())}}


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='手冊插圖的圖片字（見檔頭 docstring）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（唯讀）')
    ap.add_argument('--ge-tags', default=paths.GE_TAGS, help='GE 原廠編號對照表 ge_tags.json')
    ap.add_argument('--out', default=None, help='輸出（預設 GE 對照表同資料夾的 loc_image.json）')
    ap.add_argument('--survey', action='store_true', help='另外整頁 OCR，印出窗外讀到的 GE 編號形的字')
    a = ap.parse_args()
    if not a.ge_tags or not os.path.exists(a.ge_tags):
        sys.exit('找不到 GE 編號對照表：%s' % a.ge_tags)
    out_path = a.out or os.path.join(os.path.dirname(a.ge_tags), 'loc_image.json')
    out = build(a, print)
    n = PI.write_json(out_path, out, 'loc_image.json')
    print('寫出 %s（%d 位元組）；%s' % (out_path, n, out['stats']))
    if out['stats'].get('unconfirmed'):
        sys.exit('有 %d 則明列的標註 OCR 沒有確認（見上面 !! 行），沒有發布' % out['stats']['unconfirmed'])


if __name__ == '__main__':
    main()
