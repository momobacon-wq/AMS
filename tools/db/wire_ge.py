# -*- coding: utf-8 -*-
r"""tools/db/wire_ge.py — 接線路徑（GE 原廠編號版，v13）：汽機 TSI 偵測元件（VP-1X、ZP-201A、VP-1XVL…）→ 現場電纜 → 接線箱（JB）端子
→ 幹線電纜與芯色 → 電子室盤的端子板與端子 → Mark VIe I/O 點；每一跳附圖面上的位置（接線圖那一頁、JB 平面位置、盤內板位、3500 盤）。

為什麼需要：查詢卡的 GE 編號卡已有 P&ID、圖控、位置圖（探頭裝在軸承座哪裡）；現場要追一條振動訊號，還得知道它進哪個接線箱、
接在箱內哪幾個端子、幹線幾芯什麼顏色、落在電子室哪一面盤哪一片端子板的哪幾顆螺絲。這些散在四份圖：EPC 的儀控電纜接線圖
（每頁＝一個 JB 對一個盤）、GE 的汽機房儀器與 JB 位置圖、GE 的盤面配置、Bently 3500 盤圖；本檔把它們串成一條路徑。

== 範圍 ==
  汽機 TSI：GE TSI 訂購圖 HT0-1-TZD01-M0348（GE 137T9953）的八類 46 顆（相對振動 VP-nX/Y、軸承座速度 VP-nXVL/YVL、偏心 EP、
  軸向位置 ZP-201A～C、鍵相 RP-1、殼脹 SEDP、差脹 DEDP／REDP、轉速 ST-201／202），加 Bently 3500 盤（ST1 VMS PANEL）同時收的
  發電機 #6／#7 軸承 8 顆（39VS-91／92／101／102、39V-4A／4B／5A／5B）＝TSI_RE。本站是 1 號機（S10）：只讀一號機的接線圖。
  其他汽機儀器不收：接線圖其他頁的範本變化（兩層 TE→變送器、盤對盤、同頁多個 JB 子圖）沒有逐頁驗證過，錯一個端子號會害人拆錯線。

== 文件 ==
  接線圖 HT1-1-ICE01-D1005（CTCI，文件庫現行最高版次；排除副本／舊版／彙編；_xlsx_pdf 的轉檔是試算表逐列傾印、不是圖，不用）。
    試算表附件（*-Attachment*.xlsx）版次較舊、而且照列對齊會錯配（COAX 型 JB 欄 4 芯、盤欄 3 芯），一律讀 PDF。
  JB 位置 JBLOC_DOC、盤面配置 CAB_DOC（GE 137T8654AL：興達專案版，板位與控制器組態逐片吻合；另一份 259G9077AL 把 TVBA 畫在側板，不用）、
  3500 盤圖（檔名沒有 HT 編號：檔名含 CABINET DESIGN DRAWING、第 1 頁印 GE 圖號 VMS_GE_NO 與 'ST-VMP'）。
  文字層快取另放 TEXT_CACHE（pid_lib 的共用快取每份只抽 80 頁，接線圖 420 頁）。

== 接線圖一頁的解析（parse_page）==
  整本由同一個試算表範本產生，欄位 x 固定（BAND，顯示座標）。四種畫法：
    'coax'  近接探頭：現場 →同軸延長線→ JB 入線格 'VX-1X COAX' → 箱內前置器的端子格（-VDC／SIG|OUT／COM／SH）→ 幹線 → 盤；
    'tb'    現場端子 +／-／SH →現場電纜→ JB 入線芯色 → JB 端子排（23／24／25）→ 幹線 → 盤；
    'jbdev' 元件畫在 JB 欄裡（發電機 JB-164／JB-163 的 39VS-91：箱內前置器或 -TBB 1～6），沒有現場電纜；
    'direct'現場端子 → 一條電纜直拉到盤（SEDP-1 → TBAI），沒有 JB。
  端子格（cells_of）＝一欄裡由上到下的字，遇到功能名／端子號（KEY_RE）那一行就收成一格。芯色標籤配端子格用 order_match（DP，保持上下順序、
  一格最多一個標籤）：標籤的 y 不一定在自己那格的上緣（VP-1YVL 的 WH-2 畫在 26、27 兩格之間），但順序不會亂。
  前置器區塊以 JB 入線格 'VX-1X COAX' 的中心分段（端子格印的名字可能是筆誤：ZPX-201B／C 的 SH 格印成 'ZPX-201A SH'，VP-5Y 的 SH 格印 'VP-5X SH'，
  以格子所在的區塊為準並自動註記）。**盤側一律用芯色標籤字對接**（同一條幹線內唯一），不照列對齊：COAX 型的 SH 芯在盤側不落端子。
  元件身分：現場群組的說明格裡的 GE 編號（整詞相等），說明格只寫 KKS 時以 KKS 對。

== 其他幾跳 ==
  Mark VIe（dcdas_index）：盤端子（板位, 板名, 端子號）＝signal-atlas 索引 io_screw 的（position_r, 板名, 螺絲號）；同一顆螺絲可能掛在幾個點上
    （TCSA 的 PR2H 同時列在 PulseRate1／2），取 DeviceTag 與這個元件相關的那個（io_relates：同 KKS、GE 編號，'MAD20BS001/2/3'、'ST-202A,B,C'
    這種合寫也展開；'loc'＝同一位置、量測碼不同，例 LVDT 電源點 MAD10CY004_PWR）。對不上（diff）或沒有螺絲（none）都進 flags。
  接線箱位置（jb_locate）：JB 位置圖上 JB KKS 下一行是座標（'E nnnnnnn N nnnnnnn U nnnnn'）的那個標籤（JB TABLE 那一份不是）；沿標籤框出發的藍色引線
    一段段走到底，線尾附近的紅線小長方形就是 JB 符號（找不到就只框標籤）。
  盤內板位（board_box）：板名 '1L1A' 是線條字，框由背板的欄標籤（'1L'）與列標籤（'1A'～'1B'）推算，是約略範圍（卡上講明）。
  3500：p.10 盤內配置的 '1TBVIB, SIGNAL…' 標註（落在 1TBVIB 的元件才有）；槽位表（RACK n LAYOUT）KKS 那一格 → 槽＝同欄的 SLOT 表頭、通道＝同列的 CHn。
  註記：自動的（幹線電纜號的前綴不是這個 JB 也不是盤的 KKS；端子格印的名字與前置器不同）＋人工查證的 wire_notes.json
    （ge_tags.json 同目錄，不進 repo：文件互相矛盾，例 VP-5XVL 接線圖寫 1TBVIB 57、3500 盤圖寫 47）。

== 輸出 cardwork/wire_ge.json（決定性：鍵排序、無時間戳、無本機絕對路徑）==
  {"kind":"wire_ge","generated_by","version","unit":"S10","docs":{wire|jbloc|cab|vms: {doc, rel, rev, title, alts} 或 {why}},
   "sheets":{slug: 與 loc_ge／pid_ge 同一套欄位，kind 'wire'（接線圖）或 'loc'（其餘三份）},
   "by_ge":{"<system>|<tag>": [{sheet, x, y, w, h, label, rel 'neutral', how 'text', form 'text', note 0, via 'ge', units, listed 0, hop}]}  ← pid_shots 出圖、build_card_aux 畫框
   "paths":{鍵: {unit, tag, kks, mode, wire{page, sheet, of, drawn, marks, field_cable, field_spec, field_tb, jb, jb_kks, jb_desc, jb_tb, prox,
                 trunk, trunk_spec, panel, panel_tb, panel_desc}, cond[{core, field, field_core, jb_in, jb, pos, board, num, io?, pin?, pt?}],
                 io[[控制器, 模組, 板位, 板名, 點, 變數, DeviceTag, 關係]], hops[[跳, 圖紙鍵]], jbloc?{coords, sym}, cab?{pos, approx}, rack?{rack, slot, ch},
                 notes[[文字, 出處]], flags[]}},
   "jbs":{JB 名: {kks, pages, strip[[JB 端子, 芯, 元件, 盤端子, 幹線, JB 入線, 現場端子]], loc}}, "stats":{…}}

用法：
  py tools/db/wire_ge.py                                   # 寫 <CARDWORK>\wire_ge.json（rebuild.py 自動跑，在 pid_shots 之前）
  py tools/db/wire_ge.py --verify "ST|VP-1X" "ST|VP-5XVL"   # 另印這些條目的每一跳並畫疊框圖到 --verify-dir
  py tools/db/wire_ge.py --debug-pages 301,302             # 只印這幾頁接線圖的解析結果，不寫檔
"""
import argparse
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pid_lib as L  # noqa: E402
import pid_index as PI  # noqa: E402
from build_card_aux import ge_cmp  # noqa: E402

GENERATED_BY = 'tools/db/wire_ge.py'
VERSION = 1

# ---- 範圍：汽機 TSI（GE TSI 訂購圖 TZD01-M0348＝GE 137T9953 的八類 46 顆，加 Bently 3500 盤同時收的發電機 #6／#7 軸承 8 顆）
TSI_RE = {'ST': re.compile(r'^(?:VP-[1-5][XY](?:VL)?|EP-[1-4]|ZP-201[ABC]|RP-1|DEDP-[1-8]|REDP-1[AB]|SEDP-[12]|ST-20[12][ABC])$'),
          'ST-GEN': re.compile(r'^(?:39VS-(?:91|92|101|102)|39V-[45][AB])$')}
WIRE_DOC = 'ICE01-D1005'          # 一號機 ST 儀控電纜接線圖（HT1-1-ICE01-D1005，CTCI；每頁＝一個 JB／盤 對 一個盤）
WIRE_UNIT = 'HT1'                 # 本站＝1 號機（build_card_aux.GE_SITE_UNITS 'S'＝S10）

# ---- 接線圖的欄帶（顯示座標＝套完 /Rotate 的 A3 橫式 1191×842 pt；整本由同一個試算表範本產生，欄位 x 固定）
BAND = {'fdesc': (130, 216), 'fterm': (216, 238), 'fcore': (238, 262), 'fcab': (262, 354), 'jbin': (354, 376), 'jbterm': (376, 399),
        'jbcore': (399, 428), 'trunk': (428, 552), 'pcore': (552, 584), 'pterm': (584, 632), 'pdesc': (632, 745)}
DRAW_Y = (95, 560)                # 圖區（標頭以下、IS／OS 接地列以上；標題欄與 REV 欄在 x > 745）
CORE_RE = re.compile(r'^(BK|WH|RD|BU|BL|GN|YE|YL|OR|BR|BN|GY|VT|PK|SH)(?:-(\d+))?$')
CAB_RE = re.compile(r'-WG-\d+$')
KKS_RE = re.compile(r'^[SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}$')
SITE_UNIT, SITE_PREFIX = 'S10', 'S10'
JBLOC_DOC = 'HT1-1-IIF01-D0004'   # 一號機汽機房儀器與 JB 位置圖（GE 1GP044116；p.5 FFL +15.60 m 平面標出各 JB 與廠區座標）
CAB_DOC = 'HT0-1-TZD01-M0213'     # ST 控制盤盤面配置（GE 137T8654AL，註明 TPC HSINTA、S10/S20/S30CCM01UC201；板位與控制器組態逐片吻合）
VMS_FILE_RE = re.compile(r'CABINET DESIGN DRAWING', re.I)   # Bently 3500 盤（ST1 VMS PANEL）盤圖：檔名沒有 HT 編號
VMS_GE_NO = '120V8111'
VMS_BOARD = '1TBVIB'
MARKVIE_BOARDS = ('TVBA', 'TTUR', 'TCSA', 'TBAI', 'SHRA')
DCDAS_CTRLS = ('S1', 'S1S')       # 本站汽機控制器（一般／安全）
JB_TOUCH = 4.0                    # JB 位置圖：藍色引線的起點離標籤框 ≤ 這個距離（pt）
JB_HOPS = 6                       # 引線最多接幾段（先垂直再水平的折線）
JB_SYM_NEAR = 14.0                # JB 符號（紅線小長方形）的線段離箭頭的最大距離（pt，|dx|＋|dy|）


def r5(v):
    return round(float(v), 5)


# ================================================================ 接線圖一頁
def disp_words(pg):
    """文字層快取的一頁 → [{t, x0, y0, x1, y1, raw}]（顯示座標；raw＝未旋轉座標，給 to_upright_frac）。浮水印 'As Built' 不收。"""
    a, b, c, d, e, f = pg['rm']
    out = []
    for w in pg['words']:
        xs = (w[0] * a + w[1] * c + e, w[2] * a + w[3] * c + e)
        ys = (w[0] * b + w[1] * d + f, w[2] * b + w[3] * d + f)
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        if w[4] in ('As', 'Built') and y1 - y0 > 30:
            continue
        out.append({'t': w[4], 'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'raw': tuple(w[:4])})
    return out


def inb(w, band):
    lo, hi = BAND[band]
    return lo <= (w['x0'] + w['x1']) / 2.0 < hi


def lines_of(ws, tol=3.0):
    """同一行（y 差 ≤ tol）的字併成一行，由上到下 → [[字…]…]（行內由左到右）。"""
    out = []
    for w in sorted(ws, key=lambda w: (w['y0'], w['x0'])):
        if out and abs(out[-1][0]['y0'] - w['y0']) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(l, key=lambda w: w['x0']) for l in out]


def text_of(ws):
    return ' '.join(' '.join(w['t'] for w in l) for l in lines_of(ws))


def sheet_no(words):
    """圖框右下 '295 OF 414' → (295, 414)；找不到 (None, None)。"""
    for i, w in enumerate(words):
        if w['t'] == 'OF' and 0 < i < len(words) - 1 and words[i - 1]['t'].isdigit() and words[i + 1]['t'].isdigit() and w['x0'] > 745:
            return int(words[i - 1]['t']), int(words[i + 1]['t'])
    return None, None


HDR_JB_RE = re.compile(r'^(?:JUNCTION BOX/PANEL|JUNCTION BOX|BOX/PANEL|INSTRUMENT NO\.?)\s*:?\s*(.*)$')
HDR_TB_RE = re.compile(r'^TERMINAL NO\.?\s*:?\s*(.*)$')
HDR_PANEL_RE = re.compile(r'^PANEL\.?\s*:?\s*(.*)$')


def header(ws, y_top):
    """圖區上方的標頭 → {jb, jb_desc, jb_tb, panel, panel_tb, field_tb}（同一行左右兩段先切開；JB 端子排名在 x ≥ 300 的
    'TERMINAL NO.'，現場端子格的在左邊）。"""
    top = [w for w in ws if DRAW_Y[0] < w['y0'] < y_top and w['x1'] < 745]
    h = {'jb': '', 'jb_desc': '', 'jb_tb': '', 'panel': '', 'panel_tb': '', 'field_tb': ''}
    sgs = []
    for sg in segs_of(top):                               # 'GENERATOR JBX (BEARING)  TERMINAL NO. : -TBB' 間距不夠大：在 TERMINAL 前再切一刀
        k = next((i for i, w in enumerate(sg) if i and w['t'] == 'TERMINAL'), None)
        sgs += [sg[:k], sg[k:]] if k else [sg]
    for sg in sgs:
        t = ' '.join(w['t'] for w in sg)
        x = sg[0]['x0']
        m = HDR_TB_RE.match(t)
        if m:
            k = 'panel_tb' if x >= 560 else ('jb_tb' if x >= 300 else 'field_tb')
            h[k] = m.group(1).strip(' :-') if k == 'field_tb' else m.group(1).strip(' :')
            continue
        m = HDR_PANEL_RE.match(t)
        if m and x >= 560:
            h['panel'] = m.group(1).strip(' :')
            continue
        m = HDR_JB_RE.match(t) or (HDR_PANEL_RE.match(t) if x < 560 else None)
        if m:
            h['jb'] = m.group(1).strip(' :')
            continue
        if x < 560 and t not in ('FIELD', 'JUNCTION BOX/PANEL', 'PANEL') and not h['jb_desc']:
            h['jb_desc'] = t
    return h


KEY_RE = re.compile(r'^(?:-\s?VDC|VDC|SIG|OUT|OUTPUT|COM|SH|\+B|-A|\+|-|COAX|\d{1,3})$')   # 端子格的最後一行（功能名或端子號）
CELL_GAP = 7.5                    # 同一格內相鄰兩行的間距 ≤ 這個值（pt）；格與格之間 ≥ 8.5
SKIP_COST = 30.0                  # 標籤配不到格子的代價（pt）


def segs_of(ws, gap=25.0):
    """一行再依水平空隙切段（同一 y 上左右兩個標頭 'TERMINAL NO.'、'TERMINAL NO. TB1' 分開）→ [[字…]…]。"""
    out = []
    for l in lines_of(ws):
        cur = [l[0]]
        for w in l[1:]:
            if w['x0'] - cur[-1]['x1'] > gap:
                out.append(cur)
                cur = [w]
            else:
                cur.append(w)
        out.append(cur)
    return out


def cells_of(ws, band, y_top, single=False):
    """一個欄帶裡的端子格：字按行併好，由上到下；上一行是「功能名／端子號」（KEY_RE）或與上一行距離 > CELL_GAP 就另起一格
    （'VX-1X'＋'-VDC'＝一格；'CA004-1L1A'＋'TVBA'＋'04'＝一格；'23'＝一格）。single＝每行自成一格（現場端子 '+'／'-'／'SH'）。
    → [{'t': 整格文字, 'lines': [行文字…], 'y': 第一行 y0, 'w': [字…]}]。"""
    ls = lines_of([w for w in ws if inb(w, band) and w['y0'] > y_top])
    out, cur = [], []
    for l in ls:
        if cur and (single or l[0]['y0'] - cur[-1][0]['y0'] > CELL_GAP or KEY_RE.match(' '.join(w['t'] for w in cur[-1]))):
            out.append(cur)
            cur = []
        cur.append(l)
    if cur:
        out.append(cur)
    return [{'t': ' '.join(' '.join(w['t'] for w in l) for l in c), 'lines': [' '.join(w['t'] for w in l) for l in c], 'y': c[0][0]['y0'],
             'w': [w for l in c for w in l]} for c in out]


def order_match(labels, cells):
    """標籤（芯色）配端子格：兩邊都由上到下、保持順序、一格最多一個標籤，總距離最小（DP）。標籤的 y 不一定落在自己那格的上緣
    （VP-1YVL 的 WH-2 畫在 26、27 兩格之間），但上下順序不會亂。→ {標籤序: 格序}；配不到的標籤不在結果裡。"""
    n, m = len(labels), len(cells)
    inf = float('inf')
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    bk = [[None] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        dp[0][j] = 0.0
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + SKIP_COST
        bk[i][0] = 'L'
        for j in range(1, m + 1):
            best, how = dp[i][j - 1], 'C'                                          # 這一格空著（備用端子）
            c = dp[i - 1][j - 1] + abs(labels[i - 1]['y0'] - cells[j - 1]['y'])
            if c < best:
                best, how = c, 'M'
            if dp[i - 1][j] + SKIP_COST < best:                                    # 這個標籤沒有格子
                best, how = dp[i - 1][j] + SKIP_COST, 'L'
            dp[i][j], bk[i][j] = best, how
    out, i, j = {}, n, m
    while i > 0:
        how = bk[i][j]
        if how == 'M':
            out[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif how == 'C':
            j -= 1
        else:
            i -= 1
    return out


def ranges(centers, lo, hi):
    """由上到下的中心 y → 每段的 (下界, 上界)（相鄰中心的中點切開）。"""
    cs = sorted(centers)
    return [((cs[i - 1] + c) / 2.0 if i else lo, (cs[i + 1] + c) / 2.0 if i + 1 < len(cs) else hi) for i, c in enumerate(cs)]


def parse_page(pg):
    """接線圖一頁 → {'sheet', 'of', 'h', 'mode', 'groups', 'trunks', 'rows', 'pdesc', 'flags'}；不是接線圖的頁回 None。
    四種畫法（同一個試算表範本）：
      'coax'  ：現場探頭 →同軸延長線→ JB 入線格 'VX-1X COAX' → JB 內前置器的端子格（-VDC／SIG|OUT／COM／SH）→ 幹線 → 盤；
      'tb'    ：現場端子（+／-／SH）→現場電纜→ JB 入線芯色 → JB 端子排（23／24／25）→ 幹線 → 盤；
      'jbdev' ：元件畫在 JB 欄裡（發電機 JB-164 的 39VS-91：JB 內的前置器端子或 -TBB 1～6）→ 幹線 → 盤，沒有現場電纜；
      'direct'：現場端子 → 一條電纜直拉到盤（SEDP-1 → TBAI）。
    rows＝每一條芯一列：core（出線芯色標籤）、jb_cell、jb_in、prox、field_core、field_cell、group、trunk、panel_cell。
    端子格與芯色標籤用 order_match 配（保持上下順序）；盤側一律用「芯色標籤字」對接（同一條幹線內標籤唯一），不用 y 對接：
    COAX 型的 SH 芯在盤側不落端子，兩邊列數不同（舊試算表照列對齊就把 VP-1Y 的 TVBA 01 錯配給 VP-1X）。"""
    ws = disp_words(pg)
    sno, of = sheet_no(ws)
    if not any(w['t'] == 'FIELD' for w in ws) or not sno:
        return None
    draw = [w for w in ws if DRAW_Y[0] < w['y0'] < DRAW_Y[1] and w['x1'] < 745]
    cores = [w for w in draw if CORE_RE.match(w['t'])]
    if not cores:
        return {'sheet': sno, 'of': of, 'h': {}, 'mode': '', 'groups': [], 'trunks': [], 'rows': [], 'pdesc': '', 'flags': ['no_cores']}
    y_top = min(w['y0'] for w in cores) - 1.5
    h = header(ws, y_top)
    flags = []
    jbo = sorted([w for w in cores if inb(w, 'jbcore') and '-' in w['t']], key=lambda w: w['y0'])
    fcab = sorted([w for w in draw if CAB_RE.search(w['t']) and inb(w, 'fcab')], key=lambda w: w['y0'])
    jbin_txt = []
    if jbo:
        jbin_txt = sorted([w for w in draw if inb(w, 'jbin') and w['t'] == 'COAX'], key=lambda w: w['y0'])
        mode = 'coax' if jbin_txt else ('tb' if fcab else 'jbdev')
    else:
        mode = 'direct'
        fcab = sorted([w for w in draw if CAB_RE.search(w['t']) and w['x0'] >= BAND['fcab'][0] and w['x1'] <= BAND['pcore'][0]], key=lambda w: w['y0'])
    # ---- 現場群組（一個群組＝一個元件框）：有現場電纜的以電纜號的 y 分段；jbdev 以元件說明文字塊分段
    groups = []
    if mode == 'jbdev':
        dw = [w for w in draw if BAND['fterm'][0] <= w['x0'] and w['x1'] <= BAND['jbterm'][0] + 2 and w['y0'] > y_top]
        blocks = []
        for l in lines_of(dw):
            if blocks and l[0]['y0'] - blocks[-1][-1][0]['y0'] <= 12:
                blocks[-1].append(l)
            else:
                blocks.append([l])
        cen = [(b[0][0]['y0'] + b[-1][0]['y1']) / 2.0 for b in blocks]
        for (lo, hi), b in zip(ranges(cen, y_top, DRAW_Y[1]), blocks):
            groups.append({'cable': '', 'cable_w': None, 'spec': '', 'lo': lo, 'hi': hi, 'desc': ' '.join(' '.join(w['t'] for w in l) for l in b),
                           'desc_w': [w for l in b for w in l]})
    else:
        for (lo, hi), c in zip(ranges([w['y0'] for w in fcab], y_top, DRAW_Y[1]), fcab):
            spec = [w for w in draw if abs((w['x0'] + w['x1']) / 2.0 - (c['x0'] + c['x1']) / 2.0) < 60 and c['y1'] - 1 < w['y0'] < c['y1'] + 9
                    and not CAB_RE.search(w['t']) and (mode == 'direct' or inb(w, 'fcab'))]
            desc = [w for w in draw if inb(w, 'fdesc') and lo <= w['y0'] < hi]
            groups.append({'cable': c['t'], 'cable_w': c, 'spec': text_of(spec), 'lo': lo, 'hi': hi, 'desc': text_of(desc), 'desc_w': desc})
    grp_at = lambda y: next((k for k, g in enumerate(groups) if g['lo'] <= y < g['hi']), None)   # noqa: E731
    # ---- 幹線：trunk 欄的電纜號（直拉頁沒有）；不只一條時以 y 中點分段
    tr = sorted([w for w in draw if inb(w, 'trunk') and CAB_RE.search(w['t'])], key=lambda w: w['y0']) if mode != 'direct' else []
    trunks = []
    for (lo, hi), t in zip(ranges([w['y0'] for w in tr], y_top, DRAW_Y[1]), tr):
        spec = [w for w in draw if inb(w, 'trunk') and t['y1'] - 1 < w['y0'] < t['y1'] + 9 and not CAB_RE.search(w['t'])]
        trunks.append({'cable': t['t'], 'cable_w': t, 'spec': text_of(spec), 'lo': lo, 'hi': hi})
    if len(trunks) > 1:
        flags.append('multi_trunk')
    # ---- 盤側：芯色標籤配盤端子格
    pl = sorted([w for w in cores if inb(w, 'pcore') and '-' in w['t']], key=lambda w: w['y0'])
    pcells = cells_of(draw, 'pterm', y_top)
    pm = order_match(pl, pcells)
    rows = []
    if mode == 'direct':
        fl = sorted([w for w in cores if inb(w, 'fcore')], key=lambda w: w['y0'])
        fcells = cells_of(draw, 'fterm', y_top, single=True)
        fm = order_match(fl, fcells)
        for i, a in enumerate(fl):
            rows.append({'core': a['t'], 'core_w': a, 'group': grp_at(a['y0']), 'field_cell': fcells[fm[i]] if i in fm else None})
    else:
        jcells = cells_of(draw, 'jbterm', y_top)
        jm = order_match(jbo, jcells)
        names, br, gm = [], [], {}
        in_of_cell, fl, fcells, fm = {}, [], [], {}
        if mode == 'coax':          # 前置器區塊：JB 入線格 'VX-1X COAX' 的中心分段；區塊依順序對到現場群組（同一條水平線）
            for w in jbin_txt:
                nm = [x for x in draw if inb(x, 'jbin') and x['t'] != 'COAX' and 0 < w['y0'] - x['y0'] <= 9]
                names.append(nm[0]['t'] if nm else '')
            br = ranges([w['y0'] for w in jbin_txt], y_top, DRAW_Y[1])
            gm = order_match(jbin_txt, [{'y': g['cable_w']['y0']} for g in groups])
            if len(gm) != len(jbin_txt) or len(jbin_txt) != len(groups):
                flags.append('coax_block_group_mismatch')
        elif mode == 'tb':
            jin = sorted([w for w in cores if inb(w, 'jbin') and '-' not in w['t']], key=lambda w: w['y0'])
            im = order_match(jin, jcells)
            in_of_cell = {j: jin[i] for i, j in im.items()}
            fl = sorted([w for w in cores if inb(w, 'fcore') and '-' not in w['t']], key=lambda w: w['y0'])
            fcells = cells_of(draw, 'fterm', y_top, single=True)
            fm = order_match(fl, fcells)
        for i, a in enumerate(jbo):
            j = jm.get(i)
            c = jcells[j] if j is not None else None
            r = {'core': a['t'], 'core_w': a, 'jb_cell': c}
            if c is None:
                flags.append('jb_label_unmatched:%s' % a['t'])
            elif mode == 'coax':
                k = next((n for n, (lo, hi) in enumerate(br) if lo <= c['y'] + 4 < hi), None)
                if k is not None:
                    r['jb_in'] = '%s COAX' % names[k]
                    r['prox'] = names[k]
                    r['group'] = gm.get(k)
                    r['field_cell'] = {'t': 'COAX', 'w': []}
            elif mode == 'tb':
                x = in_of_cell.get(j)
                if x is not None:
                    r['jb_in'] = x['t']
                    f = [k for k, w in enumerate(fl) if w['t'] == x['t'] and abs(w['y0'] - x['y0']) <= 4.0]
                    if f:
                        r['field_core'] = fl[f[0]]['t']
                        r['field_cell'] = fcells[fm[f[0]]] if f[0] in fm else None
                    r['group'] = grp_at(x['y0'])
            else:
                r['group'] = grp_at(c['y'] + 4)
            r['trunk'] = next((k for k, t in enumerate(trunks) if t['lo'] <= a['y0'] < t['hi']), None)
            rows.append(r)
    # 盤側對接：同一條幹線（或直拉電纜）內，出線標籤字 ＝ 盤側標籤字；重複的標籤（多條幹線）依出現順序配
    used = set()
    for r in rows:
        cand = [i for i, w in enumerate(pl) if w['t'] == r['core'] and i not in used]
        if len(trunks) > 1 and r.get('trunk') is not None:
            t = trunks[r['trunk']]
            cand = [i for i in cand if t['lo'] - 30 <= pl[i]['y0'] < t['hi'] + 30] or cand
        if cand:
            used.add(cand[0])
            r['pcore_w'] = pl[cand[0]]
            r['panel_cell'] = pcells[pm[cand[0]]] if cand[0] in pm else None
        else:
            r['panel_cell'] = None
        if r['panel_cell'] is None and not r['core'].startswith('SH'):
            flags.append('panel_unmatched:%s' % r['core'])
    pdesc = [w for w in ws if inb(w, 'pdesc') and y_top < w['y0'] < DRAW_Y[1]]
    return {'sheet': sno, 'of': of, 'h': h, 'mode': mode, 'groups': groups, 'trunks': trunks, 'rows': rows, 'pdesc': text_of(pdesc),
            'flags': sorted(set(flags))}


def split_term(toks):
    """盤端子格的各行（['CA004-1L1A', 'TVBA', '04']；有的格兩行併在同一行 'CA004-1L2A TVBA'）→ (板位, 板名, 端子)；
    ['1TBVIB', '23'] → ('', '1TBVIB', '23')。"""
    toks = ' '.join(t for t in toks if t).split()
    num = toks[-1] if toks and re.fullmatch(r'\d{1,3}|[A-Z]{1,2}\d{0,2}', toks[-1]) else ''
    rest = toks[:-1] if num else toks
    pos = next((t for t in rest if re.fullmatch(r'(?:CA\d{3}-)?\d[A-Z]\d[A-Z]', t)), '')
    board = ' '.join(t for t in rest if t != pos)
    return pos, board, num


SKIP_FLAGS = ('old', 'copy_path', 'collection', 'dossier')
TEXT_CACHE = os.path.join(paths.AMS_LOCAL, 'wiretext')   # 接線圖 400 多頁：pid_lib 的共用快取每份只抽 MAX_TEXT_PAGES（80）頁，另放一個目錄、抽整本
TEXT_MAX_PAGES = 2000


def load_full_text(root, d, cache_dir):
    """整本的文字層快取（pid_lib.load_text，暫時放寬 MAX_TEXT_PAGES；快取目錄與 P&ID 的分開，兩邊的頁數上限不會混）。"""
    old = L.MAX_TEXT_PAGES
    L.MAX_TEXT_PAGES = TEXT_MAX_PAGES
    try:
        tx = L.load_text(root, d['rel'], d['size'], d['mtime'], cache_dir)
    finally:
        L.MAX_TEXT_PAGES = old
    if len(tx['pg']) != tx['pages']:
        sys.exit('%s 的文字層只抽到 %d／%d 頁（%s）' % (d['rel'], len(tx['pg']), tx['pages'], tx.get('err')))
    return tx


def resolve_doc(lib, full):
    """完整文件號（'HT1-1-ICE01-D1005'）→ 文件庫裡最新版的那份 PDF {doc, rel, size, mtime, rev, title, alts} 或 {why}
    （規則同 loc_ge.resolve_docs：排除副本／舊版／彙編／dossier，取最高版次，同版取檔名不像重複下載、路徑短的）。"""
    cs = []
    for rel, size, mtime in lib:
        dn = L.docno(rel.rsplit('/', 1)[-1])
        if dn and dn[0].upper() == full.upper():
            cs.append((rel, size, mtime, dn))
    if not cs:
        return {'why': '文件庫裡沒有檔名含這個文件號的 PDF'}
    pool = [c for c in cs if not set(L.copy_flags(c[0])) & set(SKIP_FLAGS)] or cs
    top = max(L.rev_rank(c[3][6]) for c in pool)
    rel, size, mtime, dn = min((c for c in pool if L.rev_rank(c[3][6]) == top), key=lambda c: ('dupname' in L.copy_flags(c[0]), len(c[0]), c[0]))
    doc, rev, _stem, title = L.ident(rel)
    return {'doc': doc or dn[0].upper(), 'rel': rel, 'size': size, 'mtime': mtime, 'rev': rev or '', 'title': title, 'alts': len(cs) - 1}


def tsi_entries(path):
    """ge_tags.json → {鍵 'ST|VP-1X': {tag, kks, forms}}（TSI_RE 範圍內的條目）與 {(ge_cmp 寫法): 鍵}。"""
    with open(path, encoding='utf-8') as f:
        j = json.load(f)
    ents, names = {}, {}
    for e in j['entries']:
        sysc = e.get('system') or ''
        rx = TSI_RE.get(sysc)
        if not rx or not rx.match(e['tag']):
            continue
        k = '%s|%s' % (sysc, e['tag'])
        forms = sorted({f for f in [e['tag']] + list(e.get('forms') or []) if f})
        ents[k] = {'tag': e['tag'], 'system': sysc, 'kks': list(e.get('kks') or []), 'forms': forms}
        for f in forms:
            names.setdefault(ge_cmp(f), set()).add(k)
    return ents, names


def group_keys(g, names, ents):
    """現場群組的說明格（'VIBRATION PROBE BEARING NO.1 X AXIS VP-1X/S10MAD10BG021'）→ 對到的 TSI 條目鍵（GE 編號整詞相等；
    說明格只寫 KKS 時以 KKS 對）。"""
    toks = [t for w in g['desc_w'] for t in re.split(r'[/\s]+', w['t']) if t]
    ks = set()
    for t in toks:
        for k in names.get(ge_cmp(t), ()):
            ks.add(k)
    if not ks:
        kk = {t for t in toks if KKS_RE.match(t)}
        ks = {k for k, e in ents.items() if set(e['kks']) & kk}
    return sorted(ks)


def ctext(c):
    return c.get('t', '') if c else ''


def resolve_vms(lib, root, cache):
    """Bently 3500 盤（ST1 VMS PANEL）的盤圖：檔名沒有 HT 編號（'noKKS_CABINET DESIGN DRAWING_rev-.pdf'，兩個資料夾各一份），
    以檔名＋第 1 頁印著 GE 圖號 VMS_GE_NO 與 'ST-VMP' 認定；排除副本後取路徑最短的。"""
    cs = []
    for rel, size, mtime in lib:
        if VMS_FILE_RE.search(rel.rsplit('/', 1)[-1]):
            cs.append((rel, size, mtime))
    pool = [c for c in cs if not set(L.copy_flags(c[0])) & set(SKIP_FLAGS)] or cs
    ok = []
    for rel, size, mtime in sorted(pool, key=lambda c: (len(c[0]), c[0])):
        tx = load_full_text(root, {'rel': rel, 'size': size, 'mtime': mtime}, cache)
        t1 = ' '.join(w[4] for w in tx['pg'][0]['words']) if tx['pg'] else ''
        if VMS_GE_NO in t1 and 'ST-VMP' in t1:
            ok.append((rel, size, mtime))
    if not ok:
        return {'why': '文件庫裡找不到 Bently 3500 盤圖（檔名含 CABINET DESIGN DRAWING、第 1 頁印 %s）' % VMS_GE_NO}
    rel, size, mtime = ok[0]
    return {'doc': '', 'rel': rel, 'size': size, 'mtime': mtime, 'rev': '', 'title': 'Bently Nevada 3500 盤圖（GE %s）' % VMS_GE_NO, 'alts': len(cs) - 1}


def frac_disp(pg, box, R):
    """顯示座標的框 (x0, y0, x1, y1) → 轉正後整張圖的 0~1 比例（pid_lib.to_upright_frac 的後半段；R 以顯示空間為準）。"""
    W, H = pg['w'], pg['h']
    x0, y0, x1, y1 = box[0] / W, box[1] / H, box[2] / W, box[3] / H
    fr = {0: (x0, y0, x1, y1), 90: (1 - y1, x0, 1 - y0, x1), 180: (1 - x1, 1 - y1, 1 - x0, 1 - y0), 270: (y0, 1 - x1, y1, 1 - x0)}[R]
    return tuple(min(max(v, 0.0), 1.0) for v in fr)


def ubox(ws, pad=1.5):
    """一組字（顯示座標）的聯集框，四邊外擴 pad pt。"""
    return (min(w['x0'] for w in ws) - pad, min(w['y0'] for w in ws) - pad, max(w['x1'] for w in ws) + pad, max(w['y1'] for w in ws) + pad)


def mark_of(pg, R, box):
    """顯示座標的框 → marks 的一格 [左, 上, 寬, 高]（0~1，四捨五入 5 位）。"""
    f = frac_disp(pg, box, R)
    return [r5(f[0]), r5(f[1]), r5(f[2] - f[0]), r5(f[3] - f[1])]


def jb_locate(pdf_abs, pg, R, pno, kks):
    """接線箱平面位置圖（IIF01-D0004）上這個 JB 的標籤（JB 的 KKS，下一行是廠區座標 'E … N … U …'）與它的符號：
    標籤 → 從標籤框出發的藍色引線（折線一段段接下去）→ 線尾附近的紅線小長方形（JB 符號，圖例 'JUNCTION BOX'）。
    同一頁右下的 JB TABLE 也印著 KKS，但下一行不是座標 → 不收。→ {label, coords, sym（顯示座標的框或 None）} 或 None。"""
    ws = disp_words(pg)
    for w in ws:
        if w['t'] != kks:
            continue
        nxt = sorted([x for x in ws if 0 < x['y0'] - w['y0'] <= 14 and abs(x['x0'] - w['x0']) <= 4], key=lambda x: x['y0'])
        line = [x for x in ws if nxt and abs(x['y0'] - nxt[0]['y0']) <= 2 and x['x0'] >= w['x0'] - 4 and x['x0'] - w['x1'] < 120]
        txt = ' '.join(x['t'] for x in sorted(line, key=lambda x: x['x0']))
        if not re.match(r'^E\s?\d{6,}', txt):
            continue
        lab = ubox([w] + line)
        sym = None
        try:
            import fitz
            doc = fitz.open(pdf_abs)
            page = doc[pno - 1]
            M = page.rotation_matrix
            items = page.get_drawings()
            doc.close()
            segs, red = [], []
            for it in items:
                col = tuple(round(c, 2) for c in (it.get('color') or ()))
                if col == (0.0, 0.0, 1.0) and not it.get('fill'):
                    for x in it['items']:
                        if x[0] == 'l':
                            segs.append((x[1] * M, x[2] * M))
                elif col == (1.0, 0.0, 0.0):
                    r = it['rect'] * M
                    if r.width <= 30 and r.height <= 30:
                        red.append(r)    # JB 符號是紅線畫的小長方形（一段一段的 'l'，不是 rect 物件）
            # 沿著藍色引線走：起點是碰到標籤框的那一端，接上的下一段的另一端……走到底就是 JB 符號
            box = fitz.Rect(lab) + (-JB_TOUCH, -JB_TOUCH, JB_TOUCH, JB_TOUCH)
            ends = []
            for i, (p1, p2) in enumerate(segs):
                for a_, b_ in ((p1, p2), (p2, p1)):
                    if box.contains(a_) and not box.contains(b_):
                        ends.append((i, b_))
            best = None
            for i0, tip in ends:
                used = {i0}                                  # 走過的線段不再走（不然會在同一段上來回）
                for _hop in range(JB_HOPS):
                    nxt = [(i, b_) for i, (p1, p2) in enumerate(segs) if i not in used for a_, b_ in ((p1, p2), (p2, p1))
                           if abs(a_.x - tip.x) + abs(a_.y - tip.y) < 1.5 and abs(b_.x - tip.x) + abs(b_.y - tip.y) > 1.5 and not box.contains(b_)]
                    if not nxt:
                        break
                    i, tip = max(nxt, key=lambda t: abs(t[1].x - tip.x) + abs(t[1].y - tip.y))
                    used.add(i)
                q = [x for x in red if abs((x.x0 + x.x1) / 2.0 - tip.x) + abs((x.y0 + x.y1) / 2.0 - tip.y) < JB_SYM_NEAR]
                if q and best is None:
                    best = q
            if best:
                sym = (min(x.x0 for x in best) - 3, min(x.y0 for x in best) - 3, max(x.x1 for x in best) + 3, max(x.y1 for x in best) + 3)
        except Exception:                                  # noqa: BLE001 — 找不到符號就只框標籤
            sym = None
        return {'label': lab, 'coords': txt, 'sym': sym}
    return None


def board_box(pg, pos):
    """GE 盤面配置圖（M0213 'CA004 BACK PANEL'）上板位 '1L1A' 的大約範圍：欄標籤 '1L'（頁面上緣）的 x、列標籤 '1A' 到 '1B'（左邊一排）的 y。
    板名 '1L1A' 本身是線條字（不在文字層），所以框是由欄、列標籤推算的範圍（卡上講明「約略」）。→ 顯示座標的框或 None。"""
    m = re.match(r'^(\d[A-Z])(\d)([A-Z])$', pos)
    if not m:
        return None
    ws = disp_words(pg)
    cols = [w for w in ws if re.fullmatch(r'\d[A-Z]', w['t']) and w['y0'] < 150]
    if not cols:
        return None
    cx0 = min(w['x0'] for w in cols)
    rows = {w['t']: w for w in ws if re.fullmatch(r'[1-5][AB]', w['t']) and w['x1'] < cx0 - 40 and w['y0'] > 150}
    col = next((w for w in cols if w['t'] == m.group(1)), None)
    ra, rb = rows.get(m.group(2) + 'A'), rows.get(m.group(2) + 'B')
    if not col or not ra or not rb:
        return None
    c = (col['x0'] + col['x1']) / 2.0
    others = [abs((w['x0'] + w['x1']) / 2.0 - c) for w in cols if w is not col]
    half = 0.45 * min(others) if others else 85.0
    ya, yb = (ra['y0'] + ra['y1']) / 2.0, (rb['y0'] + rb['y1']) / 2.0
    pitch = max(yb - ya, 20.0)
    return (c - half, ya - 0.6 * pitch, c + half, yb + 0.6 * pitch)


def find_page(tx, pred):
    """文字層快取裡第一個符合 pred(該頁全部字的集合) 的頁碼（1 起算）；沒有 None。"""
    for i, pg in enumerate(tx['pg'], 1):
        if pred({w[4] for w in pg['words']}, pg):
            return i
    return None


def rack_cell(pg, core):
    """Bently 3500 機架配置圖（'RACK n LAYOUT'）的槽位表：KKS 那一格 → (框, 機架, 槽, 通道)。
    槽＝同一欄上方最近的 'SLOT n' 表頭；通道＝同一列左邊的 'CHn'。"""
    ws = disp_words(pg)
    hit = [w for w in ws if w['t'] == core]
    if not hit:
        return None
    w = hit[0]
    cxw = (w['x0'] + w['x1']) / 2.0
    heads = []
    for i, x in enumerate(ws):
        if x['t'] == 'SLOT':
            n = [y for y in ws if y['t'].isdigit() and abs(y['y0'] - x['y0']) <= 2 and 0 <= y['x0'] - x['x1'] <= 8]
            if n and x['y0'] < w['y0']:
                heads.append((x, n[0]))
    heads = [h for h in heads if abs((h[0]['x0'] + h[1]['x1']) / 2.0 - cxw) < 40]
    slot = max(heads, key=lambda h: h[0]['y0'])[1]['t'] if heads else ''
    ch = [x for x in ws if re.fullmatch(r'CH\d', x['t']) and abs(x['y0'] - w['y0']) <= 2.5 and x['x1'] < w['x0']]
    racks = [(x['y1'] - x['y0'], y['t']) for x in ws if x['t'] == 'RACK' for y in ws
             if y['t'].isdigit() and abs(y['y0'] - x['y0']) <= 3 and 0 <= y['x0'] - x['x1'] <= 15]
    rk = max(racks)[1] if racks else ''                    # 頁面大標題 'RACK 1'（字最大的那一個）
    return {'box': ubox([w], 2.0), 'rack': rk, 'slot': slot, 'ch': ch[0]['t'][2:] if ch else ''}


def dcdas_index(path):
    """signal-atlas 控制器索引 → {(板位, 板名, 螺絲號): [(控制器, 模組, 點, 腳名, 變數, device_tag)…]}，與 {(控制器, 模組, 板位, device_tag): [(點, 變數)…]}。
    只收本站汽機的控制器（DCDAS_CTRLS）。沒有索引回 (None, None)。"""
    if not path or not os.path.exists(path):
        return None, None
    import sqlite3
    c = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    q = ('select p.ctrl, m.name, b.position_r, b.name, p.name, s.name, s.number, v.name, p.device_tag from io_point p '
         'join io_module m on m.id = p.module_id join io_board b on b.id = p.board_id left join io_screw s on s.point_id = p.id '
         'left join variable v on v.id = p.var_id where p.ctrl in (%s)' % ','.join('?' * len(DCDAS_CTRLS)))
    by_screw, by_dev = {}, defaultdict(list)
    for ctrl, mod, pos, board, pt, sn, num, var, dt in c.execute(q, DCDAS_CTRLS):
        if num is not None:                               # 同一顆螺絲可能掛在好幾個點上（TCSA 的 PR2H 同時列在 PulseRate1、PulseRate2）
            by_screw.setdefault((pos, board, int(num)), []).append((ctrl, mod, pt, sn, var or '', dt or ''))
        if dt:
            k = (ctrl, mod, pos, dt)
            if (pt, var or '') not in by_dev[k]:
                by_dev[k].append((pt, var or ''))
    c.close()
    return by_screw, by_dev


def io_relates(dt, tag, kks):
    """控制器 I/O 點的 DeviceTag 與這個元件的關係：'same'（同一個 KKS 或 GE 編號，'ST-202A,B,C' 這種逗號合寫也算）、
    'loc'（同一個位置、量測碼不同：LVDT 的電源點 MAD10CY004_PWR 與訊號點 MAD10BG004）、''（不相干）。"""
    d = (dt or '').upper()
    core = re.sub(r'^[A-Z]\d\d', '', kks.upper()) if kks else ''
    for part in re.split(r'[\s,]+', d):
        segs = part.split('/')                            # 'MAD20BS001/2/3'＝BS001、BS002、BS003（後面幾段取代結尾）
        full = [segs[0]] + [segs[0][:len(segs[0]) - len(x)] + x for x in segs[1:] if x.isdigit() and len(x) < len(segs[0])]
        if core and any(core in re.sub(r'[^A-Z0-9]', '', f) for f in full):
            return 'same'
    m = re.match(r'^(.*?)([A-Z0-9]+)$', tag.upper())
    for part in re.split(r'[\s/]+', d):
        if part == tag.upper():
            return 'same'
        segs = part.split(',')
        if len(segs) > 1 and m:
            base = segs[0]
            stem = re.sub(r'[A-Z]$', '', base)
            if tag.upper() == base or any(tag.upper() == stem + s for s in segs[1:]):
                return 'same'
    mk = re.match(r'^([A-Z]{3}\d\d)[A-Z]{2}(\d{3})$', core)
    if mk and re.search(mk.group(1) + r'[A-Z]{2}' + mk.group(2), d):
        return 'loc'
    return ''


def load_notes(path, log):
    """接線路徑的人工註記（文件互相矛盾、圖面筆誤…；查證後寫進 ge_tags_dir 的 wire_notes.json，不進 repo）→ {GE 鍵: [[文字, 出處]…]}。"""
    if not path or not os.path.exists(path):
        log('（沒有 %s：卡片不帶人工註記）' % path)
        return {}
    with open(path, encoding='utf-8') as f:
        j = json.load(f)
    out = defaultdict(list)
    for n in j.get('notes') or []:
        for k in n.get('keys') or []:
            out[k].append([n['text'], n.get('src') or ''])
    return dict(out)


def sheet_rec(d, pg, pno, n_pages, R, method, kind, tags):
    """sheets 的一筆（＝loc_ge／pid_ge 同一套欄位與算法）。"""
    w_pt, h_pt = L.upright_size(pg, R)
    return {'rel': d['rel'], 'file': d['rel'].rsplit('/', 1)[-1], 'doc': d.get('doc') or '', 'rev': d.get('rev') or '', 'title': d.get('title') or '',
            'page': pno, 'pages': n_pages, 'rot': R, 'rot_method': method, 'w_pt': round(w_pt, 1), 'h_pt': round(h_pt, 1),
            'label_pt': L.label_height_pt(pg['words']), 'grid': L.detect_grid(L.border_labels(pg, R)), 'words': len(pg['words']), 'ocr': False,
            'tags': tags, 'src': {'size': d['size'], 'mtime': d['mtime']}, 'kind': kind}


def build(a, log):
    t0 = time.time()
    ents, names = tsi_entries(a.ge_tags)
    lib = L.walk_pdfs(a.library)
    docs = {'wire': resolve_doc(lib, '%s-1-%s' % (WIRE_UNIT, WIRE_DOC)), 'jbloc': resolve_doc(lib, JBLOC_DOC), 'cab': resolve_doc(lib, CAB_DOC)}
    docs['vms'] = resolve_vms(lib, a.library, a.text_cache)
    for k, d in docs.items():
        log('%s：%s' % (k, d.get('rel') or d.get('why')))
    if not docs['wire'].get('rel'):
        sys.exit('找不到接線圖 %s-1-%s' % (WIRE_UNIT, WIRE_DOC))
    tx = {k: load_full_text(a.library, d, a.text_cache) for k, d in docs.items() if d.get('rel')}
    st = Counter()
    rec = {}                      # GE 鍵 → 路徑
    jbs = defaultdict(lambda: {'kks': '', 'pages': [], 'strip': []})
    used_sheets = {}              # (文件別, 頁) → (R, method, kind)
    R_of = {}

    def page_R(kind, pno):
        pg = tx[kind]['pg'][pno - 1]
        if (kind, pno) not in R_of:
            info = L.upright_rotation_info(pg)
            R_of[(kind, pno)] = (info['R'] if info['R'] is not None else 0, info['method'] or 'default')
        return R_of[(kind, pno)]

    # ---- 1. 接線圖：每一頁解析，現場群組對到 TSI 條目的收下
    for pno, pg in enumerate(tx['wire']['pg'], 1):
        p = parse_page(pg)
        if not p or not p['rows']:
            continue
        st['wire_pages'] += 1
        for gi, g in enumerate(p['groups']):
            ks = group_keys(g, names, ents)
            if not ks:
                continue
            rows = [r for r in p['rows'] if r.get('group') == gi]
            if not rows:
                st['group_without_rows'] += 1
                continue
            R, method = page_R('wire', pno)
            for k in ks:
                if k in rec:
                    st['dup_pages'] += 1
                    rec[k]['flags'].append('also_on_p%d' % pno)
                    continue
                e = ents[k]
                kks = next((x for x in e['kks'] if x.startswith(SITE_PREFIX)), e['kks'][0] if e['kks'] else '')
                h = p['h']
                jb_name = h.get('jb', '') if p['mode'] != 'direct' else ''
                jbk = re.search(r'[SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}', jb_name)
                tr = p['trunks'][rows[0]['trunk']] if p['trunks'] and rows[0].get('trunk') is not None else None
                pm = re.match(r'^(\S+)\s+(.*?)\s+(\S.*\(\s*E-\d+\s*\)|\S.*)$', p['pdesc'] or '')
                cond = []
                for r in rows:
                    pos, board, num = split_term(r['panel_cell']['lines'] if r.get('panel_cell') else [])
                    cond.append({'core': r['core'], 'field': ctext(r.get('field_cell')), 'field_core': r.get('field_core', ''), 'jb_in': r.get('jb_in', ''),
                                 'jb': ctext(r.get('jb_cell')), 'pos': pos, 'board': board, 'num': num})
                dev_ws = [w for w in g['desc_w']]
                jb_ws = [w for r in rows for w in ((r.get('jb_cell') or {}).get('w') or [])]
                pn_ws = [w for r in rows for w in ((r.get('panel_cell') or {}).get('w') or [])]
                marks = []
                for ws_ in (jb_ws or ([w for r in rows for w in ((r.get('field_cell') or {}).get('w') or [])]), pn_ws, dev_ws):
                    if ws_:
                        marks.append(mark_of(pg, R, ubox(ws_)))
                flags = list(p['flags'])
                prox = rows[0].get('prox', '')
                rec[k] = {
                    'unit': SITE_UNIT, 'tag': e['tag'], 'kks': kks, 'mode': p['mode'],
                    'wire': {'page': pno, 'sheet': p['sheet'], 'of': p['of'], 'drawn': g['desc'], 'marks': marks,
                             'field_cable': g['cable'], 'field_spec': g['spec'], 'field_tb': h.get('field_tb', ''),
                             'jb': jb_name, 'jb_kks': jbk.group(0) if jbk else '', 'jb_desc': h.get('jb_desc', ''), 'jb_tb': h.get('jb_tb', ''), 'prox': prox,
                             'trunk': tr['cable'] if tr else '', 'trunk_spec': tr['spec'] if tr else '',
                             'panel': h.get('panel', ''), 'panel_tb': h.get('panel_tb', ''), 'panel_desc': p['pdesc']},
                    'cond': cond, 'flags': flags, 'notes': []}
                w = rec[k]['wire']
                # 自動註記：幹線電纜號的前綴不是這個 JB 的 KKS；JB 端子格印的名字與前置器區塊不同（圖面筆誤）
                pk = re.findall(r'[SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}', w['panel'] + ' ' + (p['pdesc'] or ''))
                if w['trunk'] and w['jb_kks'] and not w['trunk'].startswith(w['jb_kks']) and not any(w['trunk'].startswith(x) for x in pk):
                    tp = re.match(r'^([SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})', w['trunk'])
                    rec[k]['notes'].append(['幹線電纜號 %s 的前綴是另一個 KKS（%s），不是這個接線箱（%s）也不是盤：電纜的這一端可能另經一個接線箱，'
                                            '請以現場電纜標示確認' % (w['trunk'], tp.group(1) if tp else '?', w['jb_kks']), '接線圖 第 %d 頁' % pno])
                cells = [c2 for r in rows for c2 in [r.get('jb_cell') or {}] if len(c2.get('lines') or []) > 1]
                odd = [c2['t'] for c2 in cells if prox and c2['lines'][0] != prox]
                if odd and len(odd) == len(cells):
                    by = {}
                    for c2 in cells:
                        by.setdefault(c2['lines'][0], []).append(' '.join(c2['lines'][1:]))
                    nm = '、'.join(n if len(by) == 1 else '%s（%s）' % (n, '／'.join(v)) for n, v in by.items())
                    rec[k]['notes'].append(['圖上這一組端子格印的是 %s，不是前置器 %s（以端子格所在的區塊為準）' % (nm, prox), '接線圖 第 %d 頁' % pno])
                elif odd:
                    rec[k]['notes'].append(['圖上「%s」這一格印的名字不是前置器 %s（圖面筆誤；以端子格所在的區塊為準，同組其他格印 %s）'
                                            % ('、'.join(odd), prox, prox), '接線圖 第 %d 頁' % pno])
                if w['jb']:
                    jb = jbs[w['jb']]
                    jb['kks'] = w['jb_kks']
                    if pno not in jb['pages']:
                        jb['pages'].append(pno)
                    for c in cond:
                        jb['strip'].append([c['jb'], c['core'], e['tag'], ' '.join(x for x in (c['pos'], c['board'], c['num']) if x), w['trunk'], c['jb_in'], c['field']])
                used_sheets[('wire', pno)] = 'wire'
    log('接線圖：%d 頁、TSI 條目 %d／%d' % (st['wire_pages'], len(rec), len(ents)))
    # ---- 2. 控制器 I/O（signal-atlas 索引；本站一號機）：盤端子（板位, 板名, 端子號）→ I/O 點；DeviceTag 必須是這個元件（或同位置的電源點）
    by_screw, by_dev = dcdas_index(a.dcdas)
    if by_screw is None:
        log('（沒有 signal-atlas 索引：不核對 I/O 點）')
    for k, r in rec.items():
        r['io'] = []
        for c in r['cond']:
            if c['board'] not in MARKVIE_BOARDS:
                continue
            st['io_conductors'] += 1
            if by_screw is None:
                c['io'] = 'none'
                continue
            cands = by_screw.get((c['pos'].split('-')[-1], c['board'], int(c['num'])), []) if c['num'].isdigit() else []
            if not cands:
                c['io'] = 'none'
                st['io_missing'] += 1
                r['flags'].append('io_missing:%s' % c['core'])
                continue
            rank = {'same': 0, 'loc': 1, '': 2}
            ctrl, mod, pt, sn, var, dt = min(cands, key=lambda h: rank[io_relates(h[5], r['tag'], r['kks'])])
            rel = io_relates(dt, r['tag'], r['kks'])
            c['io'] = rel or 'diff'
            c['pin'] = sn
            c['pt'] = pt
            st['io_' + (rel or 'diff')] += 1
            if not rel:
                r['flags'].append('io_diff:%s→%s' % (c['core'], dt))
            ent = [ctrl, mod, c['pos'].split('-')[-1], c['board'], pt, var, dt, rel or 'diff']
            if ent not in r['io']:
                r['io'].append(ent)
        # 同一個模組、同一個 DeviceTag 的其他點（TVBA 的 VIB2＝振動值、GAP2_VIB2＝間隙電壓；螺絲只掛在其中一個點上）
        extra = []
        for ctrl, mod, pos, board, pt, var, dt, rel in r['io']:
            for pt2, var2 in by_dev.get((ctrl, mod, pos, dt), []) if by_dev else []:
                if pt2 != pt and [ctrl, mod, pos, board, pt2, var2, dt, rel] not in r['io'] + extra:
                    extra.append([ctrl, mod, pos, board, pt2, var2, dt, rel])
        r['io'] = sorted(r['io'] + extra, key=lambda x: (x[0], x[1], x[4]))
    # ---- 3. 接線箱平面位置（一號機汽機房儀器與 JB 位置圖）
    jb_where = {}
    if 'jbloc' in tx:
        abs_p = os.path.join(a.library, docs['jbloc']['rel'].replace('/', os.sep))
        for jb, v in jbs.items():
            if not v['kks']:
                continue
            for pno, pg in enumerate(tx['jbloc']['pg'], 1):
                if not any(w[4] == v['kks'] for w in pg['words']):
                    continue
                R, _m = page_R('jbloc', pno)
                hit = jb_locate(abs_p, pg, R, pno, v['kks'])
                if hit:
                    marks = ([mark_of(pg, R, hit['sym'])] if hit['sym'] else []) + [mark_of(pg, R, hit['label'])]
                    jb_where[jb] = {'page': pno, 'marks': marks, 'coords': hit['coords'], 'sym': 1 if hit['sym'] else 0, 'drawn': v['kks']}
                    used_sheets[('jbloc', pno)] = 'loc'
                    st['jb_located'] += 1
                    break
    # ---- 4. 電子室盤內：Mark VIe 板位（GE 盤面配置圖）、Bently 3500 盤的 1TBVIB 端子與機架槽位
    cab_where = {}
    if 'cab' in tx:
        for r in rec.values():
            for c in r['cond']:
                if c['board'] in MARKVIE_BOARDS and c['pos'] and c['pos'] not in cab_where:
                    m = re.match(r'^(CA\d{3})-(\w+)$', c['pos'])
                    if not m:
                        continue
                    want = '%s BACK PANEL' % m.group(1)
                    pno = find_page(tx['cab'], lambda s, pg, want=want: ' '.join(w[4] for w in pg['words']).find(want) >= 0)
                    if not pno:
                        continue
                    pg = tx['cab']['pg'][pno - 1]
                    R, _m = page_R('cab', pno)
                    box = board_box(pg, m.group(2))
                    if box:
                        cab_where[c['pos']] = {'page': pno, 'marks': [mark_of(pg, R, box)], 'drawn': '%s %s' % (want, m.group(2))}
                        used_sheets[('cab', pno)] = 'loc'
    vms_where, rack_where = None, {}
    if 'vms' in tx:
        pno = find_page(tx['vms'], lambda s, pg: '1TBVIB,' in s and 'SIGNAL' in s)   # 盤內配置 SECTION B-B：'1TBVIB, SIGNAL … TERMINALS ON ISOLATED DIN RAIL'
        if pno:
            pg = tx['vms']['pg'][pno - 1]
            R, _m = page_R('vms', pno)
            ws = disp_words(pg)
            w = next(x for x in ws if x['t'] == '1TBVIB,')
            line = [x for x in ws if -2 <= x['y0'] - w['y0'] <= 26 and -40 <= x['x0'] - w['x0'] < 110 and x['x1'] < w['x0'] + 130]   # 標註三行
            vms_where = {'page': pno, 'marks': [mark_of(pg, R, ubox(line))], 'drawn': '1TBVIB, SIGNAL TERMINALS'}
            used_sheets[('vms', pno)] = 'loc'
        for k, r in rec.items():
            core = re.sub(r'^[A-Z]\d\d', '', r['kks'])
            for pno, pg in enumerate(tx['vms']['pg'], 1):
                if not any(w[4] == core for w in pg['words']):
                    continue
                if sum(1 for w in pg['words'] if w[4] == 'SLOT') < 10 or not any(w[4] == 'CH1' for w in pg['words']):
                    continue                                  # 只看機架槽位表那兩頁（RACK 1／RACK 2 LAYOUT），訊號接線頁不算
                R, _m = page_R('vms', pno)
                hit = rack_cell(pg, core)
                if hit:
                    rack_where[k] = {'page': pno, 'marks': [mark_of(pg, R, hit['box'])], 'rack': hit['rack'], 'slot': hit['slot'], 'ch': hit['ch'], 'drawn': core}
                    used_sheets[('vms', pno)] = 'loc'
                    break
    notes = load_notes(a.notes, log)
    # ---- 5. sheets、by_ge（pid_shots 與 build_card_aux 的圖紙檢查用）、paths
    slug = {}
    sheets_out = {}
    for (kind, pno), sk in sorted(used_sheets.items()):
        d = docs[kind]
        s = L.slug(d['rel'], pno)
        slug[(kind, pno)] = s
        R, method = page_R(kind, pno)
        sheets_out[s] = sheet_rec(d, tx[kind]['pg'][pno - 1], pno, tx[kind]['pages'], R, method, 'wire' if kind == 'wire' else 'loc', 0)
    if len(set(slug.values())) != len(slug):
        sys.exit('slug 撞號（不同圖紙得到同一個鍵）')
    by_ge, paths_out = {}, {}
    tags_on = Counter()
    for k, r in sorted(rec.items()):
        hops = []
        hops.append(['wire', slug[('wire', r['wire']['page'])], r['wire']['marks'], r['wire']['drawn']])
        jw = jb_where.get(r['wire']['jb'])
        if jw:
            hops.append(['jbloc', slug[('jbloc', jw['page'])], jw['marks'], jw['drawn']])
        pos = next((c['pos'] for c in r['cond'] if c['board'] in MARKVIE_BOARDS and c['pos'] in cab_where), None)
        if pos:
            cw = cab_where[pos]
            hops.append(['cab', slug[('cab', cw['page'])], cw['marks'], cw['drawn']])
        if vms_where and any(c['board'] == VMS_BOARD for c in r['cond']):
            hops.append(['vms', slug[('vms', vms_where['page'])], vms_where['marks'], vms_where['drawn']])
        rw = rack_where.get(k)
        if rw:
            hops.append(['rack', slug[('vms', rw['page'])], rw['marks'], rw['drawn']])
        hits = []
        for kind, s, marks, drawn in hops:
            tags_on[s] += 1
            for m in marks:
                hits.append({'sheet': s, 'x': m[0], 'y': m[1], 'w': m[2], 'h': m[3], 'label': drawn, 'rel': 'neutral', 'drawn_as': '', 'how': 'text',
                             'form': 'text', 'note': 0, 'via': 'ge', 'units': [SITE_UNIT], 'listed': 0, 'hop': kind})
        by_ge[k] = hits
        out = {k2: v for k2, v in r.items() if k2 not in ('flags',)}
        out['flags'] = sorted(set(r['flags']))
        out['hops'] = [[kind, s] for kind, s, _m, _d in hops]
        if jw:
            out['jbloc'] = {'coords': jw['coords'], 'sym': jw['sym']}
        if pos:
            out['cab'] = {'pos': pos, 'approx': 1}
        if rw:
            out['rack'] = {'rack': rw['rack'], 'slot': rw['slot'], 'ch': rw['ch']}
        cur = notes.get(k, [])
        tp = re.match(r'^([SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})', r['wire']['trunk'] or '')
        auto = [n for n in r['notes'] if not (n[0].startswith('幹線電纜號') and tp and any(tp.group(1) in c[0] for c in cur))]   # 人工註記已講清楚的不重複
        out['notes'] = auto + cur
        paths_out[k] = out
    for s in sheets_out:
        sheets_out[s]['tags'] = tags_on[s]
    jbs_out = {}
    for jb, v in sorted(jbs.items()):
        jbs_out[jb] = {'kks': v['kks'], 'pages': v['pages'], 'strip': v['strip'], 'loc': 1 if jb in jb_where else 0}   # 照圖上的順序（頁序、由上到下）
    docs_out = {k: ({k2: d[k2] for k2 in ('doc', 'rel', 'rev', 'title', 'alts') if k2 in d and d[k2] not in (None, '')} if d.get('rel') else {'why': d['why']})
                for k, d in docs.items()}
    stats = {'tsi_entries': len(ents), 'located': len(rec), 'missing': sorted(set(ents) - set(rec)), 'jbs': len(jbs_out),
             'jb_located': sum(1 for v in jbs_out.values() if v['loc']), 'boards_located': len(cab_where), 'rack_located': len(rack_where),
             'sheets': len(sheets_out), 'scan': {k2: int(v) for k2, v in sorted(st.items())},
             'flags': dict(sorted(Counter(f.split(':')[0] for r in paths_out.values() for f in r['flags']).items())),
             'by_mode': dict(sorted(Counter(r['mode'] for r in paths_out.values()).items())),
             'notes': sum(len(r['notes']) for r in paths_out.values())}
    out = {'kind': 'wire_ge', 'generated_by': GENERATED_BY, 'version': VERSION, 'unit': SITE_UNIT, 'docs': docs_out, 'sheets': sheets_out,
           'by_ge': by_ge, 'paths': paths_out, 'jbs': jbs_out, 'stats': stats}
    log('耗時 %.1f 秒' % (time.time() - t0))
    return out


def verify(out, root, keys, vdir, log):
    """這些條目的每一跳：印出內容，並把框疊在轉正後的整張圖上（紅框）另存 PNG——人工讀圖核對用。"""
    import fitz
    os.makedirs(vdir, exist_ok=True)
    for k in keys:
        r = out['paths'].get(k)
        if not r:
            log('%s：沒有接線路徑' % k)
            continue
        log('== %s %s mode=%s p.%s（Sheet %s）flags=%s' % (k, r['kks'], r['mode'], r['wire']['page'], r['wire']['sheet'], r['flags']))
        for c in r['cond']:
            log('   %-5s 現場 %-5s JB %-16s → %s %s %s  io=%s %s' % (c['core'], c['field'], c['jb'], c['pos'], c['board'], c['num'], c.get('io', ''), c.get('pin', '')))
        for x in r.get('io') or []:
            log('   I/O %s' % ' '.join(str(v) for v in x))
        for n in r['notes']:
            log('   註：%s〔%s〕' % (n[0], n[1]))
        for kind, s in r['hops']:
            sh = out['sheets'][s]
            doc = fitz.open(os.path.join(root, sh['rel'].replace('/', os.sep)))
            pix = L.render_upright(doc[sh['page'] - 1], sh['rot'], long_px=2400)
            doc.close()
            from PIL import Image, ImageDraw
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples) if pix.n == 3 else Image.frombytes('L', (pix.width, pix.height), pix.samples).convert('RGB')
            dr = ImageDraw.Draw(im)
            for h in out['by_ge'][k]:
                if h['sheet'] != s:
                    continue
                x0, y0 = h['x'] * im.width, h['y'] * im.height
                dr.rectangle([x0, y0, x0 + h['w'] * im.width, y0 + h['h'] * im.height], outline=(255, 0, 0), width=4)
            fn = os.path.join(vdir, '%s_%s.png' % (re.sub(r'[^A-Za-z0-9_-]', '_', k), kind))
            im.save(fn)
            log('   %s → %s' % (kind, fn))


def debug(a):
    lib = L.walk_pdfs(a.library)
    d = resolve_doc(lib, '%s-1-%s' % (WIRE_UNIT, WIRE_DOC))
    print(d)
    ents, names = tsi_entries(a.ge_tags)
    print('TSI 條目 %d' % len(ents))
    tx = load_full_text(a.library, d, a.text_cache)
    pages = [int(x) for x in a.debug_pages.split(',')] if a.debug_pages else range(1, tx['pages'] + 1)
    found = defaultdict(list)
    for pno in pages:
        pg = tx['pg'][pno - 1]
        p = parse_page(pg)
        if not p or not p['rows']:
            continue
        for gi, g in enumerate(p['groups']):
            ks = group_keys(g, names, ents)
            if not ks:
                continue
            rows = [r for r in p['rows'] if r.get('group') == gi]
            for k in ks:
                found[k].append(pno)
            print('p.%d sh %s %s | %s | jb=%s (%s) tb=%s | panel=%s tb=%s | fcab=%s %s' % (pno, p['sheet'], p['mode'], '/'.join(ks), p['h'].get('jb'), p['h'].get('jb_desc'),
                  p['h'].get('jb_tb'), p['h'].get('panel'), p['h'].get('panel_tb'), g['cable'], g['spec']))
            for r in rows:
                tr = p['trunks'][r['trunk']]['cable'] + ' ' + p['trunks'][r['trunk']]['spec'] if r.get('trunk') is not None and p['trunks'] else ''
                print('     %-5s fc=%-5s fcell=%-5s jbin=%-14s jb=%-16s trunk=%s → %s' % (r['core'], r.get('field_core', ''), ctext(r.get('field_cell')), r.get('jb_in', ''),
                      ctext(r.get('jb_cell')), tr, ctext(r.get('panel_cell'))))
        if p['flags']:
            print('     flags', p['flags'])
        orphan = [r['core'] for r in p['rows'] if r.get('group') is None]
        if orphan and any(group_keys(g, names, ents) for g in p['groups']):
            print('     orphan rows', orphan)
    print('找到 %d／%d' % (len(found), len(ents)), '沒找到：', sorted(set(ents) - set(found)))
    print('多頁：', {k: v for k, v in found.items() if len(set(v)) > 1})


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='接線路徑（GE 原廠編號版；見檔頭 docstring）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（預設 paths.LIBRARY_ROOT；唯讀）')
    ap.add_argument('--ge-tags', default=paths.GE_TAGS, help='GE 原廠編號對照表 ge_tags.json（預設 paths.GE_TAGS）')
    ap.add_argument('--notes', default=os.path.join(os.path.dirname(paths.GE_TAGS or '.'), 'wire_notes.json'),
                    help='人工註記（預設 ge_tags.json 同目錄的 wire_notes.json；不進 repo）')
    ap.add_argument('--dcdas', default=paths.DCDAS_INDEX, help='signal-atlas 控制器索引（預設 paths.DCDAS_INDEX）；不存在就不核對 I/O 點')
    ap.add_argument('--text-cache', default=TEXT_CACHE, help='文字層字框快取目錄（預設 <AMS_LOCAL>\\wiretext，整本）')
    ap.add_argument('--out', default=os.path.join(paths.CARDWORK, 'wire_ge.json'), help='輸出（預設 <CARDWORK>\\wire_ge.json）')
    ap.add_argument('--verify', metavar='KEY', nargs='+', help='另印這些條目（"ST|VP-1X"）的每一跳並畫疊框圖')
    ap.add_argument('--verify-dir', default=os.path.join(paths.AMS_LOCAL, 'wireverify_ge'), help='疊框圖輸出目錄')
    ap.add_argument('--debug-pages', default='', help='只印這幾頁接線圖的解析結果（逗號分隔的 PDF 頁碼），不寫檔')
    a = ap.parse_args()
    if not os.path.isdir(a.library):
        sys.exit('找不到文件庫：%s' % a.library)
    if not a.ge_tags or not os.path.exists(a.ge_tags):
        sys.exit('找不到 GE 編號對照表：%s' % a.ge_tags)
    if a.debug_pages:
        debug(a)
        return
    out = build(a, print)
    n = PI.write_json(a.out, out, 'wire_ge.json')
    st = out['stats']
    print('寫出 %s（%.2f MB）' % (os.path.basename(a.out), n / 1048576.0))
    print('TSI 條目 %d，有接線路徑 %d；沒有：%s' % (st['tsi_entries'], st['located'], st['missing']))
    print('畫法 %s；接線箱 %d（平面位置 %d）；盤內板位 %d；3500 槽位 %d；圖紙 %d 張；註記 %d' % (
        st['by_mode'], st['jbs'], st['jb_located'], st['boards_located'], st['rack_located'], st['sheets'], st['notes']))
    print('I/O 核對 %s' % {k: v for k, v in st['scan'].items() if k.startswith('io_')})
    print('旗標 %s' % st['flags'])
    if a.verify:
        verify(out, a.library, a.verify, a.verify_dir, print)


if __name__ == '__main__':
    main()
