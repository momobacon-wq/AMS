# -*- coding: utf-8 -*-
r"""tools/db/wire_ge.py — 接線路徑（GE 原廠編號版；v13 汽機 TSI，v14 一號機全部）：偵測元件 → 現場電纜 → 接線箱（JB）端子 → 幹線電纜與芯色
→ 電子室盤的端子板與端子 → Mark VIe I/O 點；每一跳附圖面上的位置（接線圖那一頁、GE 接線表那幾列、JB 位置、電纜表那一列、盤內板位、3500 盤）。

為什麼需要：查詢卡的 GE 編號卡已有 P&ID、圖控、位置圖（元件裝在哪裡）；現場要追一條訊號，還得知道它進哪個接線箱、接在箱內哪幾個端子、
幹線幾芯什麼顏色、落在電子室哪一面盤哪一片端子板的哪幾顆螺絲。這些散在好幾份圖：EPC 的儀控電纜接線圖（每頁＝一個 JB 對一個盤）、GE 的燃機接線表、
JB 位置圖、電纜表、GE 的盤面配置、Bently 3500 盤圖；本檔把它們串成一條路徑，一顆元件可以有好幾條（兩台燃機、多組接點、電源＋訊號）。

== 範圍（v14）==
  GE 編號對照表（ge_tags.json）的全部條目，凡是出現在一號機兩份儀控電纜接線圖上的：汽機 HT1-1-ICE01-D1005（只對 ST／ST-GEN 條目）、
  燃機 HT1-1-ICE01-D1004（GT-11／GT-12 兩半本，只對 GT／GT-GEN 條目；DT-GSC、FY-2960、33GC、96HGF-7A 兩邊都有同名條目）。
  加上 GE 138T5502（燃機元件 → 撬上 JB 端子）以端子號接上來的、FF 元件接到段幹線的。TSI_RE＝v13 那 54 顆（回歸檢查用：v14 對它們的輸出不變，只多了電纜表那一跳）。
  機組一律看盤／JB／幹線的 KKS 前綴（S10、G11、G12），不看圖框標題（燃機圖尾段 p.847 標 GT-11、內容是 G12）。

== 文件 ==
  接線圖：汽機 D1005（固定欄帶 BAND，parse_page）、燃機 D1004（向量框線，wire_gt.py）。燃機撬上：GE 138T5502 Rev M（HT0-1-GID01-D0003，wire_gt.parse_conn）。
  JB 位置：汽機 HT1-1-IIF01-D0004（沿藍色引線找紅框）、燃機 GE 137T6223（HT0-1-GAD01-D0001：p.11 JB 表座標、p.12 等角圖標籤）。
  電纜表：HT1-1-ILE01-A1005（汽機）、A1004（燃機）——每條幹線兩端的房間碼、說明、設備、型式、長度。
  盤面配置：汽機 HT0-1-TZD01-M0213（GE 137T8654AL）、燃機 HT0-1-GID01-A1002（GE 137T7182AL），背板與左右側板。3500 盤圖（GE 120V8111）。
  文字層快取另放 TEXT_CACHE（pid_lib 的共用快取每份只抽 80 頁；燃機接線圖 855 頁），燃機接線圖的向量框線也快取在那裡（frames_*.json）。

== 接線圖一頁的解析 ==
  汽機（parse_page）：整本由同一個試算表範本產生，欄位 x 固定（BAND）。四種畫法 coax（同軸 → 箱內前置器）、tb（現場端子 → 箱內端子排）、
    jbdev（元件畫在 JB 欄裡：閥體接線盒、skid JB、MCC、發電機 JB）、direct（直拉到盤）。端子格（cells_of）與芯色標籤用 order_match（DP，保持上下順序）。
    v14 修正：盤標頭 x≈553 的頁（門檻 PANEL_X）、整欄不帶號的芯色（3C／5C 電纜的 BR／BL…，pick_cores）、入線芯色帶號的雙支熱電偶、MCC/SWGR. 標頭。
  燃機（wire_gt.parse_page）：欄位由向量框線定（表頭 FIELD 字給位移），每條芯以接線短線定位，一頁可以有好幾個子圖；畫法 jbdev／direct／ff（FF 段幹線）／link（盤對盤，不收）。
  **盤側對接**：同一條幹線內，出線標籤序列 ↔ 盤側標籤序列做 LCS（標籤相同才對上）；夾在兩個對上的中間、數量相同的照順序補配並註記（標籤筆誤：
    D1005 p.348 盤側印 RD-2 應為 RD-1、D1004 p.386／805 WH-3 對 WH-2）。SH 另外照標籤配（COAX 型的 SH 盤側不落端子）。
  元件身分（identify）：說明格裡的 GE 編號整詞相等（合寫 'TE-203A/B/C' 展開；括號被斷行切開的接回）；沒有就看 KKS；都沒有就由盤端子反查控制器 DeviceTag（via 'io'，
    那顆螺絲在組態裡只對到一個點才算）。一個說明格寫了好幾顆時，落在 Mark VIe 的芯照組態 DeviceTag 分給各顆。

== 其他幾跳 ==
  GE 138T5502（燃機）：（JB, 端子排, 端子）接上 D1004 的 JB 端子格；說明格有寫這顆的路徑多「元件端子 → JB 端子」一跳，說明格寫整區或別名的另開一條（via 'conn'）。
    FF 元件（JB 欄是 FBSP-GT-n 段保護器）接到 D1004 的 FF 段幹線（'ff' 子圖）→ FFPCn Sm；控制器以 FF_IN_S(8(n−1)+m) 段裡有沒有這顆的變數核對（ff_index）。
  Mark VIe（io_index／io_lookup／io_rel）：盤端子（櫃-板位, 板名, TB, 螺絲號）＝signal-atlas 索引 io_screw（io_module.cabinet、io_board.position_r、板名、note、螺絲號）；
    TDBT 兩排螺絲號重疊要分 TB1（繼電器）／TB2（接點）；圖上寫 TBTC 而組態是 STTC 的換算通道（⌈n/2⌉）。關係：✓ same／logic／equip／loc／suffix、
    ≈ alias（名稱寫法不同）、✗ other（組態掛的是另一個 GE 編號）／spare（備用點）；✗／≈ 自動註記，不替任何一方選邊。
  接線箱位置：汽機 jb_locate（標籤 → 藍色引線 → 紅框符號）；燃機 gtjb_locate（JB 表那一列＋等角圖標籤）。盤內板位（board_box、cab_page）：欄、列標籤推算的約略範圍。
  電纜表（cable_schedule）：幹線（直拉頁是那一條電纜）那一列的兩端房間。3500：1TBVIB 標註與機架槽位表（汽機 TSI）。
  註記：自動的＋人工查證的 wire_notes.json（ge_tags.json 同目錄，不進 repo；鍵可以帶 '@G11' 只套用到那一台）。

== 輸出 cardwork/wire_ge.json（v2；決定性：鍵排序、無時間戳、無本機絕對路徑）==
  {"kind":"wire_ge","generated_by","version":2,"units":["S10","G11","G12"],"docs":{…},"sheets":{slug: 與 loc_ge／pid_ge 同一套欄位，kind 'wire' 或 'loc'},
   "by_ge":{"<system>|<tag>": [{sheet, x, y, w, h, label, rel 'neutral', how 'text', form 'text', note 0, via 'ge', units, listed 0, hop, pi（路徑序）}]},
   "paths":{鍵: [{unit, tag, kks, mode, via, doc, wire{…}, cond[{core, field, field_core, jb_in, jb, pos, board, tb, num, fix, io?, pin?, pt?, how?}], io[…],
                 field?[[元件端子, 芯色, 電纜, 中間元件, JB, 端子, JB 所在, 版次]…], conn?[[頁, 框]…], ff?{seg, port, loc, dev, members, s, vars, other_s},
                 room?{cable, r1, r1d, d1, r2, r2d, d2, type, len}, hops[[跳, 圖紙鍵]], jbloc?, gtjb?, cab?, rack?, notes, flags}…]},
   "jbs":{"機組|JB 名": {unit, jb, kks, desc, pages, strip[[JB 端子, 芯, 元件, 盤端子, 幹線, JB 入線, 現場端子, GE 鍵]], loc}}, "ff":{…}, "stats":{…}}

用法：
  py tools/db/wire_ge.py                                   # 寫 <CARDWORK>\wire_ge.json（rebuild.py 自動跑，在 pid_shots 之前）
  py tools/db/wire_ge.py --verify "ST|VP-1X" "GT|96CD-2A"   # 另印這些條目的每一條路徑、每一跳並畫疊框圖到 --verify-dir
  py tools/db/wire_ge.py --debug-doc wiregt --debug-pages 10,380   # 只印這幾頁接線圖的解析結果與對到的 GE 鍵，不寫檔
"""
import argparse
import copy
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
import wire_gt as WG  # noqa: E402
import wire_sig as WS  # noqa: E402
import wire_ep as WE  # noqa: E402
from build_card_aux import ge_cmp  # noqa: E402

GENERATED_BY = 'tools/db/wire_ge.py'
VERSION = 2

# ---- 範圍：汽機 TSI（GE TSI 訂購圖 TZD01-M0348＝GE 137T9953 的八類 46 顆，加 Bently 3500 盤同時收的發電機 #6／#7 軸承 8 顆）
TSI_RE = {'ST': re.compile(r'^(?:VP-[1-5][XY](?:VL)?|EP-[1-4]|ZP-201[ABC]|RP-1|DEDP-[1-8]|REDP-1[AB]|SEDP-[12]|ST-20[12][ABC])$'),
          'ST-GEN': re.compile(r'^(?:39VS-(?:91|92|101|102)|39V-[45][AB])$')}
WIRE_DOC = 'ICE01-D1005'          # 一號機 ST 儀控電纜接線圖（HT1-1-ICE01-D1005，CTCI；每頁＝一個 JB／盤 對 一個盤）
WIRE_UNIT = 'HT1'                 # 本站＝1 號機（build_card_aux.GE_SITE_UNITS 'S'＝S10）

# ---- 接線圖的欄帶（顯示座標＝套完 /Rotate 的 A3 橫式 1191×842 pt；整本由同一個試算表範本產生，欄位 x 固定）
BAND = {'fdesc': (130, 216), 'fterm': (216, 238), 'fcore': (238, 262), 'fcab': (262, 354), 'jbin': (354, 376), 'jbterm': (376, 399),
        'jbcore': (399, 428), 'trunk': (428, 552), 'pcore': (552, 584), 'pterm': (584, 632), 'pdesc': (632, 745)}
DRAW_Y = (95, 560)                # 圖區（標頭以下、IS／OS 接地列以上；標題欄與 REV 欄在 x > 745）
DRAW_X = 745.0                    # 圖區右界（v17：HRSG／BOP 接線圖的範本在 890，wire_epc.use_layout 逐頁換掉）
FIELD_REQUIRED = True             # 接線頁一定有 'FIELD' 欄名（v17：電氣 I&C 接線圖的左欄名是 MCC 的 KKS，wire_epc 關掉）
CORE_RE = re.compile(r'^(BK|WH|RD|BU|BL|GN|YE|YL|OR|BR|BN|GY|VT|PK|PU|SH|GND)(?:-(\d+))?$')
CAB_RE = re.compile(r'-WG-\d+$')
CAB_ROW_RE = re.compile(r'-WG-?\d+$')                # 電纜表的列起點：刪除線的舊列有 'G12CCJ01UC201-WG008'（少一個連字號），也要算一列，否則併進下一列
KKS_RE = re.compile(r'^[SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}$')
SITE_UNIT, SITE_PREFIX = 'S10', 'S10'
JBLOC_DOC = 'HT1-1-IIF01-D0004'   # 一號機汽機房儀器與 JB 位置圖（GE 1GP044116；p.5 FFL +15.60 m 平面標出各 JB 與廠區座標）
CAB_DOC = 'HT0-1-TZD01-M0213'     # ST 控制盤盤面配置（GE 137T8654AL，註明 TPC HSINTA、S10/S20/S30CCM01UC201；板位與控制器組態逐片吻合）
VMS_FILE_RE = re.compile(r'CABINET DESIGN DRAWING', re.I)   # Bently 3500 盤（ST1 VMS PANEL）盤圖：檔名沒有 HT 編號
VMS_GE_NO = '120V8111'
VMS_BOARD = '1TBVIB'
MARKVIE_BOARDS = ('TVBA', 'TTUR', 'TCSA', 'TBAI', 'SHRA', 'TDBT', 'TRLY', 'STTC', 'SCSA', 'STAI', 'STAO', 'SRTD', 'TSVC', 'TRPG', 'TBCI', 'SDII', 'TCDM', 'SPID',
                  'STCI', 'SRLY')   # TCDM＝燃燒動態（96KP）、SPID＝CANopen（90VGC）；STCI／SRLY＝HRSG、BOP 控制器的接點輸入／繼電器（v17）
UNIT_CTRLS = {'S10': ('S1', 'S1S'), 'G11': ('G11', 'G11S'), 'G12': ('G12', 'G12S')}   # 本站（1 號機）各機組的控制器（一般／安全）
SITE_UNITS = ('S10', 'G11', 'G12')
WIRE_GT_DOC = 'HT1-1-ICE01-D1004'  # 一號機燃機儀控電纜接線圖（CTCI；GT-11／GT-12 兩半本，wire_gt.py 解析）
CAB_GT_DOC = 'HT0-1-GID01-A1002'   # GT 控制盤盤面配置（GE 137T7182AL；與汽機 M0213 同一版型）
CS_DOCS = {'S10': 'HT1-1-ILE01-A1005', 'G11': 'HT1-1-ILE01-A1004', 'G12': 'HT1-1-ILE01-A1004'}   # 一號機 ST／GT 儀控電纜表：每條電纜兩端的房間碼、設備、型式、長度
GTJB_DOC = 'HT0-1-GAD01-D0001'     # GE 137T6223 O/L MECHANICAL GT & GENERATOR：p.11 撬上 JB 位置表（X／Y／Z 燃機座標）、p.12 等角圖上的 JB 標籤
JBDOCS = (   # v14：其餘接線箱所在的設備圖（GE／廠商的外形圖、配置圖）：只標出箱子在設備上的位置、沒有廠區座標；箱名或 KKS 在文字層，框的是圖上的標籤
    ('HT0-1-EGJ01-D0012', ('G11', 'G12'), '燃機發電機電氣外形圖', 'IDENTIFICATION'),   # 第四欄：有這個字的頁跳過（發電機外形圖的尺寸表也寫箱名，要框視圖上的標籤）
    ('HT0-1-EGK01-D0009', ('S10',), '汽機發電機電氣外形圖', 'IDENTIFICATION'),
    ('HT0-1-EGJ01-D0020', ('G11', 'G12'), '燃機發電機氫氣封油盤外形圖', ''),
    ('HT0-1-EGK01-D0011', ('S10',), '汽機發電機氫氣封油盤外形圖', ''),
    ('HT0-1-EGJ01-D0017', ('G11', 'G12', 'S10'), '發電機氣體乾燥器外形圖', ''),
    ('HT0-1-EGJ01-D0050', ('G11', 'G12'), '燃機發電機氫氣抽氣偵測系統圖', ''),
    ('HT0-1-EGK01-D0045', ('S10',), '汽機發電機氫氣抽氣偵測系統圖', ''),
    ('HT0-1-EGJ01-D0070', ('G11', 'G12'), '燃機發電機集電環室氫氣偵測組立圖', ''),
    ('HT0-1-EGK01-D0046', ('S10',), '汽機發電機集電環室氫氣偵測組立圖', ''),
    ('HT0-1-TZD01-D0002', ('S10',), '汽機控制接線位置圖（MLI VE02）', ''),
    ('HT0-1-TAD01-D0004', ('S10',), '汽機潤滑／液壓油箱配置圖（MLI VR20）', ''),
    ('HT0-1-GZD01-M1203', ('G11', 'G12'), '燃機細水霧撬內部配置圖', ''),
)
GEN_OUTLINE = {'G11': 'HT0-1-EGJ01-D0012', 'G12': 'HT0-1-EGJ01-D0012', 'S10': 'HT0-1-EGK01-D0009'}   # 發電機接線箱（KKS MKA10XG…）沒畫在這張上 → 註記
GEN_WIRING = {'G11': 'HT0-1-EGJ01-M0109', 'G12': 'HT0-1-EGJ01-M0109'}
VMS_GT_DOC = 'HT1-1-AQB01-Q1850'   # v16：燃機 Bently 3500 盤（GT-VMP）的製造完成報告，附 Rev D 盤圖的 3500 接線表（G11 的 RACK 1；G12 的 RACK 2 那幾頁只有文字層、不框）
DEV_TB_RE = re.compile(r'CHARGE AMP|PROXIMIT|^TB PROX_')   # v16：GE 138T5502「接線箱端子排」欄寫的是箱內的中間設備（電荷放大器、前置器），不是端子排   # v15：GE 燃機發電機接線圖（H6／H8）——元件表列了外形圖沒畫的箱子（JB-5D＝MKA01 GD005D ACCELEROMETERS），註記一併指出
MCC_DOCS = (   # v15：480 V MCC／PC 的盤面配置圖（GE EP24 EQUIPMENT ARRANGEMENT，各機組一份）；檔名沒有文件號（'noKKS_… _revQ.pdf'），照檔名標題找、取最高版次
    ('G11', 'EQUIPMENT ARRANGEMENT - 480V MOTOR CONTROL CENTER FOR UNIT 1 GT1'),
    ('G12', 'EQUIPMENT ARRANGEMENT - 480V MOTOR CONTROL CENTER FOR UNIT 1 GT2'),
    ('S10', 'EQUIPMENT ARRANGEMENT - 480V MOTOR CONTROL CENTER FOR UNIT 1 ST'),
    ('G11', 'EQUIPMENT ARRANGEMENT - 480V POWER CENTER (G11BFA10, G11BGA10)'),
    ('G12', 'EQUIPMENT ARRANGEMENT - 480V POWER CENTER (G12BFA10, G12BGA10)'),
    ('S10', 'EQUIPMENT ARRANGEMENT - 480V POWER CENTER (S10BFA10, S10BGA10)'),
)
MCC_RE = re.compile(r'([GS]\d{2}B[FGK][AB]\d0)[_-](NP\d-\d|A\d{1,2}[A-H]|\d{1,2}[A-F])\b')   # 接線圖「接線箱」欄：'G11BGB10_A1C'、'…PC-GT111/G11BFA10_2D'、'S10BGB10-A2A'、'G11BKB20_NP3-3'
MCC_EPC_RE = re.compile(r'\b([GSC]\d{2}B[FGK][AB]\d0)_(A\d{1,2})_(A\d{1,2}[A-H])\b')   # v17 HRSG／BOP 接線圖的 MCC 格：'G11BFB30_A1_A1E'（排_欄_格）
MCC_LAB_RE = re.compile(r'^(?:A\d{1,2}[A-H]|\d{1,2}[A-F]|NP\d-\d)$')                 # 正視圖上的格位標籤（格子左下角）；'A1'（欄頭、單元號）、'A3'（圖紙尺寸）沒有尾字母，不算
MCC_NAME_RE = re.compile(r'\b(E?MCC|PC)[\s-]*(GT|ST)[\s-]*(\d{2,3})\b')         # 排的名稱：'MCC GT-112'、'(MCC GT112)'、'EMCC-ST-10'、'PC-GT122' → 'MCC-GT112'
MCC_KKS_RE = re.compile(r'[GSC]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?(?:-[A-Z]{1,2}\d{2})?')
ROOM_RE = re.compile(r'^\d{2,3}[A-Z]{3}\d{2}R\d{3}$')
DEV_RE = re.compile(r'^(?:[CGS]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{2,3}[A-Z0-9_-]*|[CGS]\d{2}[A-Z]{3}\d{2}(?:[_-][A-Z0-9_-]+)?)$')   # 'S10BPA10'（系統層的盤碼）也算
CONN_DOC = 'HT0-1-GID01-D0003'     # GE 138T5502 Turbine Connection Diagram（MLI 0401，Rev M AS-BUILT）：燃機元件 → 撬上 JB 端子，一芯一列
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
    """圖框右下 '295 OF 414'（BOP 接線圖寫 '293 of 975'）→ (295, 414)；找不到 (None, None)。"""
    for i, w in enumerate(words):
        if w['t'].upper() == 'OF' and 0 < i < len(words) - 1 and words[i - 1]['t'].isdigit() and words[i + 1]['t'].isdigit() and w['x0'] > 745:
            return int(words[i - 1]['t']), int(words[i + 1]['t'])
    return None, None


HDR_JB_RE = re.compile(r'^(?:JUNCTION BOX/PANEL|JUNCTION BOX|BOX/PANEL|INSTRUMENT NO\.?|MCC/SWGR\.?)\s*\.?\s*:?\s*(.*)$')
PANEL_X = 520.0                   # 盤欄標頭的 x 門檻（D1005 的 'PANEL :ST TCP' 有的在 584、有的在 553；JB 欄標頭在 x < 400）
HDR_TB_RE = re.compile(r'^TERMINAL NO\.?\s*:?\s*(.*)$')
HDR_PANEL_RE = re.compile(r'^PANEL\.?\s*:?\s*(.*)$')


def header(ws, y_top):
    """圖區上方的標頭 → {jb, jb_desc, jb_tb, panel, panel_tb, field_tb}（同一行左右兩段先切開；JB 端子排名在 x ≥ 300 的
    'TERMINAL NO.'，現場端子格的在左邊）。"""
    top = [w for w in ws if DRAW_Y[0] < w['y0'] < y_top and w['x1'] < DRAW_X]
    h = {'jb': '', 'jb_desc': '', 'jb_tb': '', 'panel': '', 'panel_tb': '', 'field_tb': ''}
    sgs = []
    for sg in segs_of(top):                               # 'GENERATOR JBX (BEARING)  TERMINAL NO. : -TBB' 間距不夠大：在 TERMINAL 前再切一刀
        k = next((i for i, w in enumerate(sg) if i and w['t'] == 'TERMINAL' and i + 1 < len(sg) and sg[i + 1]['t'].upper().startswith('NO')), None)
        sgs += [sg[:k], sg[k:]] if k else [sg]
    for sg in sgs:
        t = ' '.join(w['t'] for w in sg)
        x = sg[0]['x0']
        m = HDR_TB_RE.match(t)
        if m:
            k = 'panel_tb' if x >= PANEL_X else ('jb_tb' if x >= 300 else 'field_tb')
            h[k] = m.group(1).strip(' :-') if k == 'field_tb' else m.group(1).strip(' :')
            continue
        m = HDR_PANEL_RE.match(t)
        if m and x >= PANEL_X:
            h['panel'] = m.group(1).strip(' :')
            continue
        m = HDR_JB_RE.match(t) or (HDR_PANEL_RE.match(t) if x < PANEL_X else None)
        if m:
            h['jb'] = m.group(1).strip(' :').lstrip('.: ')
            continue
        if x < PANEL_X and t not in ('FIELD', 'JUNCTION BOX/PANEL', 'PANEL') and not h['jb_desc']:
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


def pick_cores(ws):
    """一欄的芯色標籤（由上到下）：有帶號的（BK-1）就只收帶號的；整欄都不帶號（3C 電纜 BR／BL、5C 的 BK／BL／BR／GY）才收不帶號的
    （v13 只收帶號的：無編號芯色的 57 頁整頁 0 列、18 頁盤側對不到）。"""
    num = [w for w in ws if '-' in w['t']]
    return sorted(num or ws, key=lambda w: w['y0'])


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
    if (FIELD_REQUIRED and not any(w['t'] == 'FIELD' for w in ws)) or not sno:
        return None
    draw = [w for w in ws if DRAW_Y[0] < w['y0'] < DRAW_Y[1] and w['x1'] < DRAW_X]
    cores = [w for w in draw if CORE_RE.match(w['t'])]
    if not cores:
        return {'sheet': sno, 'of': of, 'h': {}, 'mode': '', 'groups': [], 'trunks': [], 'rows': [], 'pdesc': '', 'flags': ['no_cores']}
    yc = [w for w in cores if inb(w, 'fcore') or inb(w, 'jbcore') or inb(w, 'pcore')] or cores   # 只看芯色欄：p.215 標頭說明「NEUTRAL GND ENCL HEATER」的 GND 不是芯（v16）
    y_top = min(w['y0'] for w in yc) - 1.5
    h = header(ws, y_top)
    flags = []
    jbo = pick_cores([w for w in cores if inb(w, 'jbcore')])
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
    pl = pick_cores([w for w in cores if inb(w, 'pcore')])
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
        used_f = set()
        if mode == 'coax':          # 前置器區塊：JB 入線格 'VX-1X COAX' 的中心分段；區塊依順序對到現場群組（同一條水平線）
            for w in jbin_txt:
                nm = [x for x in draw if inb(x, 'jbin') and x['t'] != 'COAX' and 0 < w['y0'] - x['y0'] <= 9]
                names.append(nm[0]['t'] if nm else '')
            br = ranges([w['y0'] for w in jbin_txt], y_top, DRAW_Y[1])
            gm = order_match(jbin_txt, [{'y': g['cable_w']['y0']} for g in groups])
            if len(gm) != len(jbin_txt) or len(jbin_txt) != len(groups):
                flags.append('coax_block_group_mismatch')
        elif mode == 'tb':
            jin = sorted([w for w in cores if inb(w, 'jbin')], key=lambda w: w['y0'])   # 入線芯色可以帶號（雙支 TC 的 YE-1／RD-1）
            im = order_match(jin, jcells)
            in_of_cell = {j: jin[i] for i, j in im.items()}
            fl = sorted([w for w in cores if inb(w, 'fcore')], key=lambda w: w['y0'])
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
                    if not f and grp_at(x['y0']) is not None:     # 雙支熱電偶：入線芯色 YE-1 畫得比現場的 YE-1 高；同一條現場電纜裡同字的那一個
                        g0 = grp_at(x['y0'])
                        f = sorted([k for k, w in enumerate(fl) if w['t'] == x['t'] and grp_at(w['y0']) == g0 and k not in used_f],
                                   key=lambda k: abs(fl[k]['y0'] - x['y0']))
                    if f:
                        used_f.add(f[0])
                        r['field_core'] = fl[f[0]]['t']
                        r['field_cell'] = fcells[fm[f[0]]] if f[0] in fm else None
                    r['group'] = grp_at(x['y0'])
            else:
                r['group'] = grp_at(c['y'] + 4)
            r['trunk'] = next((k for k, t in enumerate(trunks) if t['lo'] <= a['y0'] < t['hi']), None)
            rows.append(r)
    # 盤側對接：同一條幹線（或直拉電纜）內，出線標籤序列 ↔ 盤側標籤序列做 LCS（標籤相同才對上，順序不亂）；夾在兩個對上的中間、
    # 數量相同的照順序補配並旗標 label_typo（圖面標籤筆誤：p.348 盤側印 RD-2 應為 RD-1、p.18 WH-8 應為 WH-4、p.99 現場 BK-1 對盤側 BK）。
    # v13 是「找第一個同字的標籤」：筆誤時會靜默配到別條芯（p.348 TE-260H 配到 TE-260B 的負極）。SH 另外只照標籤配（COAX 型的 SH 盤側不落端子）。
    used = set()
    for ti in (range(len(trunks)) if len(trunks) > 1 else [None]):
        rr = [r for r in rows if ti is None or r.get('trunk') == ti]
        if ti is None:
            pp = list(range(len(pl)))
        else:
            t = trunks[ti]
            pp = [i for i in range(len(pl)) if t['lo'] - 30 <= pl[i]['y0'] < t['hi'] + 30 and i not in used] or [i for i in range(len(pl)) if i not in used]
        for sh in (False, True):
            ra = [r for r in rr if r['core'].startswith('SH') == sh]
            pb = [i for i in pp if pl[i]['t'].startswith('SH') == sh and i not in used]
            for i, j, how in WG.lcs_pair([r['core'] for r in ra], [pl[k]['t'] for k in pb]):
                if sh and how == 'gap':
                    continue
                r, k = ra[i], pb[j]
                used.add(k)
                r['pcore_w'] = pl[k]
                r['panel_cell'] = pcells[pm[k]] if k in pm else None
                if how == 'gap':
                    r['ptypo'] = pl[k]['t']
                    flags.append('label_typo:%s→%s' % (r['core'], pl[k]['t']))
    for r in rows:
        r.setdefault('panel_cell', None)
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


TERM_BOARD_FIX = {'TBDT': 'TDBT', 'DBT': 'TDBT'}     # 接線圖上 TDBT 的筆誤（D1005 p.170、p.198；D1004 p.95／515、p.846）


def term_parts(toks, hdr_tb=''):
    """盤端子格的各行 → {'pos', 'board', 'tb', 'num', 'fix'}（v14；v13 的 split_term 只拆 pos／board／num，TB 混在板名裡）：
      'CA004-1L1A','TVBA','04' → CA004-1L1A／TVBA／''／04；'CA001-1A4A','TDBT TB1','18' → CA001-1A4A／TDBT／TB1／18；
      'CA004','1M3A TCSA','69'、'CA001 -1E1A' → 板位接回 'CA004-1M3A'、'CA001-1E1A'；'TDBT TB2-31'（圖例寫法）→ TB2／31；
      'CA002','FFPC3 S5','73' → CA002／FFPC3／S5／73（FF 電源調節器第 5 段）；'CA003-FIELD TB-','8+' → CA003／FIELD TB／''／8+；
      '1TBVIB','23' → ''／1TBVIB／''／23；'MAIN-TBCT','71'、'EWV BB 1 CH1','17' → 板名照寫（不是 Mark VIe）。
    'TBDT'／'DBT' 是 TDBT 的筆誤（fix＝原字）；TDBT 圖上沒寫 TB 時用盤表頭的 'TERMINAL NO. TB2'（fix＝'hdr_tb'）。"""
    t = ' '.join(x for x in toks if x)
    t = re.sub(r'\b(CA\d{3})\s*-?\s*(?=\d[A-Z]\d[A-Z]\b)', r'\1-', t)
    t = re.sub(r'\bTB(\d)-\s*(\d{1,3})\b', r'TB\1 \2', t)
    t = re.sub(r'\b((?:CA\d{3}-)?\d[A-Z]\d[A-Z])-(?=\s)', r'\1', t)   # 'CA001-1C1A- TBDT-TB2 21'（燃機 p.426）→ 'CA001-1C1A TBDT TB2 21'
    t = re.sub(r'\b(TBDT|TDBT)-(TB\d)\b', r'\1 \2', t)      # 'WCSA-TB1'（TCSA 的子端子排）不拆
    t = re.sub(r'(?<=\S)-\s+(?=\S+$)', ' ', t).strip()
    t = re.sub(r'\s+-$', '', t)
    t = re.sub(r'^(-?XT\d{1,3})-(\d{1,3})$', r'\1 \2', t)   # GCB 低壓箱的格子 '-XT07-15'（燃機 p.18、19、24、439）→ 端子排 -XT07、端子 15（v16）
    tk = t.split()
    num = tk[-1] if tk and re.fullmatch(r'\d{1,3}[A-Z]?[+-]?|[A-Z]{1,2}\d{0,2}[+-]?|GND|SHD?', tk[-1]) else ''
    rest = tk[:-1] if num else tk
    fix = ''
    m = re.match(r'^(CA\d{3})\s+(FFPC\d)\s+(S\d)$', ' '.join(rest))
    if m:
        return {'pos': m.group(1), 'board': m.group(2), 'tb': m.group(3), 'num': num, 'fix': ''}
    m = re.match(r'^(CA\d{3})-?\s*(FIELD TB)\b', ' '.join(rest))
    if m:
        return {'pos': m.group(1), 'board': m.group(2), 'tb': '', 'num': num, 'fix': ''}
    m = re.match(r'^(CA\d{3})-?\s*(?:(TB\d)\s+)?ESTOP$', ' '.join(rest))   # 'CA004-TB1 ESTOP'、'CA004- TB2 ESTOP'：盤內緊急停機端子排
    if m:
        return {'pos': m.group(1), 'board': 'ESTOP', 'tb': m.group(2) or '', 'num': num, 'fix': ''}
    pos = next((x for x in rest if re.fullmatch(r'(?:CA\d{3}-)?\d[A-Z]\d[A-Z]', x)), '')
    tb = next((x for x in rest if x != pos and re.fullmatch(r'(?:[A-Z]{4}-)?TB\d', x)), '')
    board = ' '.join(x for x in rest if x not in (pos, tb))
    if board in TERM_BOARD_FIX:
        fix, board = board, TERM_BOARD_FIX[board]
    ht = re.sub(r'^[-\s:]+', '', hdr_tb or '').strip()
    if board == 'TDBT' and not tb and re.fullmatch(r'TB\d', ht):
        tb, fix = ht, 'hdr_tb'
    if not board and not pos and num and ht and not re.fullmatch(r'TB\d|\*', ht):
        board, fix = ht, 'hdr_board'                     # 格子只寫號碼、端子排名寫在盤表頭（燃機 p.435 'TERMINAL NO.: -XT07'）
    return {'pos': pos, 'board': board, 'tb': tb, 'num': num, 'fix': fix}


def cab_page(tx, cab, col):
    """GE 盤面配置圖裡畫著櫃 cab 欄 col（'1L'）的那一頁 → (頁, 'BACK PANEL'／'LEFT SIDE PANEL'／'RIGHT SIDE PANEL')：
    頁上有 '<cab> <面>' 這個標題、上緣有這個欄標籤；背板優先（v13 只找背板，側板上的板位框不到）。找不到 (None, '')。"""
    best = None
    for i, pg in enumerate(tx['pg'], 1):
        t = ' '.join(w[4] for w in pg['words'])
        for rank, side in enumerate(('BACK PANEL', 'LEFT SIDE PANEL', 'RIGHT SIDE PANEL')):
            if '%s %s' % (cab, side) in t and (best is None or rank < best[0]):
                lab = [w for w in disp_words(pg) if re.fullmatch(r'\d[A-Z]', w['t'])]
                if lab and any(w['t'] == col and w['y0'] < min(x['y0'] for x in lab) + 10 for w in lab):
                    best = (rank, i, side)
    return (best[1], best[2]) if best else (None, '')


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


def all_entries(path):
    """ge_tags.json → (ents, names, kks_of, logic_of)（v14：全部條目，不只 TSI）：
    ents＝{鍵 '<system>|<GE 編號>': {tag, system, kks, forms, logic, tsi}}（tsi＝TSI_RE 範圍內＝v13 那 54 顆）；
    names＝{system: {ge_cmp(寫法): {鍵}}}（寫法要含數字、至少 3 個字元：說明格裡的一般英文字不會誤中）；
    kks_of＝{system: {KKS 本體: {鍵}}}（kks_core）；logic_of＝{(控制器, 變數小寫): {鍵}}（對照表的 Mark VIe 訊號）。"""
    with open(path, encoding='utf-8') as f:
        j = json.load(f)
    ents, names, kks_of, logic_of = {}, defaultdict(dict), defaultdict(dict), defaultdict(set)
    for e in j['entries']:
        sysc = e.get('system') or ''
        k = '%s|%s' % (sysc, e['tag'])
        forms = sorted({f for f in [e['tag']] + list(e.get('forms') or []) if f})
        rx = TSI_RE.get(sysc)
        ents[k] = {'tag': e['tag'], 'system': sysc, 'kks': list(e.get('kks') or []), 'forms': forms, 'logic': list(e.get('logic') or []),
                   'linked': sorted({x['tag'] for x in e.get('linked') or [] if x.get('tag')}), 'tsi': 1 if rx and rx.match(e['tag']) else 0}
        for f in forms:
            c = ge_cmp(f)
            if len(c) >= 3 and re.search(r'\d', c):
                names[sysc].setdefault(c, set()).add(k)
        for x in ents[k]['kks']:
            if kks_core(x):
                kks_of[sysc].setdefault(kks_core(x), set()).add(k)
        for x in ents[k]['logic']:
            ctl, _, var = x.partition('.')
            logic_of[(ctl, var.lower())].add(k)
    return ents, dict(names), dict(kks_of), dict(logic_of)


def kks_core(k):
    """KKS → 本體（大寫、去掉空白與連字號、去掉機組前綴 S10／G11 與 XX／YY）：'S10MAA11QM001-BG02' → 'MAA11QM001BG02'；不是 KKS 形狀回 ''。"""
    c = ge_cmp(k)
    c = re.sub(r'^(?:[GS]\d{2}|XX|YY)(?=[A-Z]{3}\d{2}[A-Z]{2}\d{3})', '', c)
    return c if re.match(r'^[A-Z]{3}\d{2}[A-Z]{2}\d{3}', c) else ''


def kks_for(e, unit):
    """條目在這台機組的 KKS：有這台前綴的那一個；只有 XX／YY 或沒有前綴的換成這台的前綴；都沒有回 ''（v13：汽機條目本來就帶 S10）。"""
    ks = e['kks']
    hit = next((x for x in ks if x.startswith(unit)), None)
    if hit:
        return hit
    for x in ks:
        c = kks_core(x)
        if c:
            return unit + c
    return ks[0] if ks else ''


TOK_SPLIT = re.compile(r'[\s/()\[\],;]+')
KKS_ANY = re.compile(r'^[SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}(?:[-_][A-Z0-9]+)?$')
KKS_BARE = re.compile(r'^[A-Z]{3}\d{2}[A-Z]{2}\d{3}(?:[-_][A-Z0-9]+)?$')   # 說明格裡不帶機組前綴的 KKS（'POSITION OPEN … LBH31QM001-BG02'）


def desc_tokens(ws, paren=False):
    """說明格的字 → [(候選字串, y 中心)]（paren＝True 時是 [(字串, y, 在不在括號裡)]）：整字（去掉括號）＋以 / ( ) [ ] , 拆開的片段；
    結尾是 '-' 的字與下一個字相接（'(23WR-'＋'1A))' → '23WR-1A'；括號被斷行切開）。"""
    seq = [w for l in lines_of(ws) for w in l]
    out, i, depth = [], 0, 0
    while i < len(seq):
        t, y = seq[i]['t'], (seq[i]['y0'] + seq[i]['y1']) / 2.0
        while t.endswith('-') and len(t.strip('()[]-')) > 1 and i + 1 < len(seq):
            i += 1
            t += seq[i]['t']
        inp = depth > 0 or t.startswith('(') or t.count(')') > t.count('(')   # 圖上漏了左括號的（'Stop command 23HT- 3A/3B/OFF)'）也算
        depth = max(0, depth + t.count('(') - t.count(')'))
        cand = [t.strip('()[],;:.')] + [x for x in TOK_SPLIT.split(t) if x and x != t]
        if '/' in t or ',' in t:
            cand += dt_parts(t.strip('()[],;:.'))           # 'TE-203A/B/C' → TE-203A／TE-203B／TE-203C
        out += [(x, y, inp) for x in cand]
        i += 1
    return out if paren else [(x, y) for x, y, _p in out]


def identify(g, sysset, names, kks_of):
    """元件框（說明格）→ {鍵: (via, y)}：via＝'ge'（GE 編號整詞相等，不分大小寫與符號）；沒有 GE 編號才看 KKS（'kks'，本體相等）。
    只收這份接線圖的系統（汽機圖 ST／ST-GEN、燃機圖 GT／GT-GEN：DT-GSC、FY-2960、33GC、96HGF-7A 兩邊都有同名條目）。"""
    hits, inparen = {}, set()
    toks = desc_tokens(g['desc_w'], paren=True)
    for t, y, inp in toks:
        c = ge_cmp(t)
        for s in sysset:
            for k in (names.get(s) or {}).get(c, ()):
                hits.setdefault(k, ('ge', y))
                if inp:
                    inparen.add(k)
    if inparen:                                          # 說明格有括號編號時以括號裡的為準：'52G BREAKER AUXILLARY CONTACT FOR 52GX-1/2 RELAYS (52G/AUX)' 只是 52G/AUX；
        pc = [ge_cmp(k.split('|', 1)[1]) for k in inparen]   # 括號外的若是括號內那顆的本體（閥 HV-HDAS-50 ↔ 限位開關 33HVHDAS-50C）照留
        hits = {k: v for k, v in hits.items() if k in inparen or any(len(ge_cmp(k.split('|', 1)[1])) >= 4 and ge_cmp(k.split('|', 1)[1]) in c for c in pc)}
    toks = [(t, y) for t, y, _p in toks]
    if not hits:
        for t, y in toks:
            if KKS_ANY.match(t):
                for s in sysset:
                    for k in (kks_of.get(s) or {}).get(kks_core(t), ()):
                        hits.setdefault(k, ('kks', y))
    return hits


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


def disp_box(pg, b):
    """未旋轉座標的框（fitz get_text('words') 那一套：偵察結果、電氣盤配置圖定位用）→ 顯示座標（disp_words 那一套）。"""
    a, b_, c, d, e, f = pg['rm']
    pts = [(x, y) for x in (b[0], b[2]) for y in (b[1], b[3])]
    xs = [x * a + y * c + e for x, y in pts]
    ys = [x * b_ + y * d + f for x, y in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def mark_of(pg, R, box):
    """顯示座標的框 → marks 的一格 [左, 上, 寬, 高]（0~1，四捨五入 5 位）。"""
    f = frac_disp(pg, box, R)
    return [r5(f[0]), r5(f[1]), r5(f[2] - f[0]), r5(f[3] - f[1])]


def loc_label(ws, w):
    """位置圖上一個字 w 是不是位置標籤（下一行是廠區座標 'E … N … U …'）→ (標籤框, 座標字串) 或 None（v17 從 jb_locate 拆出來，wire_epc 也用）。
    同一頁右下的 JB TABLE 也印著 KKS，但下一行不是座標 → 不算。"""
    nxt = sorted([x for x in ws if 0 < x['y0'] - w['y0'] <= 14 and abs(x['x0'] - w['x0']) <= 4], key=lambda x: x['y0'])
    line = [x for x in ws if nxt and abs(x['y0'] - nxt[0]['y0']) <= 2 and x['x0'] >= w['x0'] - 4 and x['x0'] - w['x1'] < 120]
    txt = ' '.join(x['t'] for x in sorted(line, key=lambda x: x['x0']))
    if not re.match(r'^E\s?\d{6,}', txt):
        return None
    return ubox([w] + line), txt


def jb_segments(pdf_abs, pno):
    """位置圖那一頁的藍色引線段與紅線小長方形（JB 符號）→ (segs, red)，顯示座標（v17 從 jb_locate 拆出來，wire_epc 逐頁快取）。"""
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
    return segs, red


def jb_walk(lab, segs, red):
    """標籤框 → 從標籤框出發的藍色引線（折線一段段接下去）→ 線尾附近的紅線小長方形 → 符號框（顯示座標）或 None。"""
    import fitz
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
        return (min(x.x0 for x in best) - 3, min(x.y0 for x in best) - 3, max(x.x1 for x in best) + 3, max(x.y1 for x in best) + 3)
    return None


def jb_locate(pdf_abs, pg, R, pno, kks):
    """接線箱平面位置圖（IIF01-D0004）上這個 JB 的標籤（JB 的 KKS，下一行是廠區座標 'E … N … U …'）與它的符號：
    標籤 → 從標籤框出發的藍色引線（折線一段段接下去）→ 線尾附近的紅線小長方形（JB 符號，圖例 'JUNCTION BOX'）。
    同一頁右下的 JB TABLE 也印著 KKS，但下一行不是座標 → 不收。→ {label, coords, sym（顯示座標的框或 None）} 或 None。"""
    ws = disp_words(pg)
    for w in ws:
        if w['t'] != kks:
            continue
        hit = loc_label(ws, w)
        if not hit:
            continue
        lab, txt = hit
        try:
            sym = jb_walk(lab, *jb_segments(pdf_abs, pno))
        except Exception:                                  # noqa: BLE001 — 找不到符號就只框標籤
            sym = None
        return {'label': lab, 'coords': txt, 'sym': sym}
    return None


def cable_schedule(tx):
    """儀控電纜表（HT1-1-ILE01-A1004／A1005，GE 範本、一列一條電纜）→ {電纜號: {r1, r1d, d1, r2, r2d, d2, type, len, page, box}}：
    r＝房間碼（'101UBA20R001'）、rd＝房間說明（'GT ELECTRICAL BUILDING(E-305)'、'ST Hall 8.8Mtr'）、d＝設備（盤／JB／MCC 的碼）。兩份表的欄位 x 不同：
    房間與設備不靠欄位位置，由房間碼、設備碼的字形與 ATEX 欄（'NA'）切開；型式（Cable Type）與長度（Designed Length）照這一頁表頭的欄位。
    一列＝SL.No 那一行上下各半個列距（多行的格子垂直置中）；電纜號印成兩個字的（'G11MBY01XD109' '-WG-003'）先接回。"""
    out = {}
    for pno, pg in enumerate(tx['pg'], 1):
        ws0 = disp_words(pg)
        ws, skip = [], set()
        srt = sorted(ws0, key=lambda w: (round(w['y0']), w['x0']))
        for i_, w in enumerate(srt):
            if i_ in skip:
                continue
            nx = srt[i_ + 1] if i_ + 1 < len(srt) else None
            if nx and re.fullmatch(r'[CGS]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?', w['t']) and re.fullmatch(r'-?WG-\d+', nx['t']) \
                    and abs(nx['y0'] - w['y0']) < 2 and nx['x0'] - w['x1'] < 12:
                ws.append(dict(w, t=w['t'] + '-' + nx['t'].lstrip('-'), x1=nx['x1']))
                skip.add(i_ + 1)
            else:
                ws.append(w)
        hx = {}
        for w in ws:
            if w['y0'] < 60 or not hx.get('_y') or abs(w['y0'] - hx['_y']) < 4:
                if w['t'] in ('Type', 'OD', 'Designed', 'Routing') and w['t'] not in hx:
                    hx[w['t']], hx['_y'] = w['x0'], w['y0']
        revx = max((w['x0'] for w in ws if w['t'] == 'Revision'), default=None)   # 最右邊的 Revision 欄寫 '#1'／'#2' 的列是刪除線（已刪除）的列
        starts = sorted([w for w in ws if w['t'].isdigit() and w['x0'] < 50 and any(CAB_ROW_RE.search(x['t']) and abs(x['y0'] - w['y0']) < 2 and x['x0'] < 100 for x in ws)],
                        key=lambda w: w['y0'])
        for i, sw in enumerate(starts):
            gap_up = (sw['y0'] - starts[i - 1]['y0']) / 2.0 if i else ((starts[i + 1]['y0'] - sw['y0']) / 2.0 if i + 1 < len(starts) else 6.0)
            gap_dn = (starts[i + 1]['y0'] - sw['y0']) / 2.0 if i + 1 < len(starts) else gap_up
            y0, y1 = sw['y0'] - gap_up, sw['y0'] + gap_dn
            rw = sorted([w for w in ws if y0 <= (w['y0'] + w['y1']) / 2.0 < y1], key=lambda w: (round(w['y0']), w['x0']))
            cab = next((w for w in rw if CAB_ROW_RE.search(w['t']) and w['x0'] < 100 and abs(w['y0'] - sw['y0']) < 2), None)
            if not cab or not CAB_RE.search(cab['t']):
                continue
            first = sorted([w for w in rw if abs(w['y0'] - sw['y0']) < 2], key=lambda w: w['x0'])
            devs = [w for w in first if DEV_RE.match(w['t']) and not CAB_RE.search(w['t'])]
            rec = {'page': pno, 'box': [min(w['x0'] for w in rw) - 1, y0, max(w['x1'] for w in rw) + 1, y1]}
            if revx is not None and any(re.fullmatch(r'#\d+', w['t']) and w['x0'] >= revx - 15 for w in rw):
                rec['del'] = True
            r1 = next((w for w in first if ROOM_RE.match(w['t']) and w['x0'] > cab['x1']), None)
            d1 = next((d for d in devs if r1 and d['x0'] > r1['x1']), None)
            a1 = next((w for w in first if w['t'] == 'NA' and d1 and w['x0'] > d1['x1']), None)
            d2 = next((d for d in devs if a1 and d['x0'] > a1['x1']), None)
            r2 = next((w for w in first if ROOM_RE.match(w['t']) and a1 and w['x0'] > a1['x1'] and (not d2 or w['x0'] < d2['x0'])), None)

            def span(lo, hi):
                ws_ = [w for w in rw if lo < w['x0'] < hi - 1]
                return re.sub(r'\(\s*E-\s*', '(E-', ' '.join(w['t'] for w in ws_)).replace(' )', ')').strip()
            if r1 and d1:
                rec.update({'r1': r1['t'], 'r1d': span(r1['x1'], d1['x0']), 'd1': d1['t']})
            if a1 and d2:
                rec.update({'r2': r2['t'] if r2 else '', 'r2d': span((r2 or a1)['x1'], d2['x0']), 'd2': d2['t']})
            elif d1:                                              # 起端 ATEX 欄空白：設備說明與對端房間說明之間以最大的空隙分開
                d2 = next((d for d in devs if d['x0'] > d1['x1']), None)
                mid = [w for w in first if d1['x1'] < w['x0'] < (d2['x0'] if d2 else 1e9) and w['t'] != 'NA']
                if d2 and len(mid) >= 2:
                    gi = max(range(1, len(mid)), key=lambda i: mid[i]['x0'] - mid[i - 1]['x1'])
                    r2 = next((w for w in mid[gi:] if ROOM_RE.match(w['t'])), None)
                    rec.update({'r2': r2['t'] if r2 else '', 'r2d': span((r2 or mid[gi - 1])['x1'], d2['x0']), 'd2': d2['t']})
            for k_ in ('r1d', 'r2d'):
                if k_ in rec:
                    rec[k_] = re.sub(r'^(?:-\s*)+', '', rec[k_]).strip()      # 房間碼寫 '-' 的列
            if hx.get('Type') and hx.get('OD'):                    # 型式＝表頭 'Cable Type' 欄（可能折兩行：'01P-18 AWG - FFB Cable'／'Type A'）
                tt = [w for w in rw if hx['Type'] - 16 <= w['x0'] < hx['OD'] - 3]
                rec['type'] = re.sub(r'\s+', ' ', ' '.join(w['t'] for w in sorted(tt, key=lambda w: (round(w['y0']), w['x0'])))).strip()
            if hx.get('Designed'):                                 # 長度＝表頭 'Designed Length' 欄（'53'、'155+350'）
                ll = [w for w in first if hx['Designed'] - 10 <= w['x0'] < hx['Designed'] + 40 and re.fullmatch(r'[\d.+]+', w['t'])]
                if ll:
                    rec['len'] = ll[0]['t']
            if not (rec.get('del') and cab['t'] in out and not out[cab['t']].get('del')):   # 同號的現行列優先
                out[cab['t']] = rec
    return out


def gtjb_locate(tx, name, kks=''):
    """GE 137T6223 上燃機撬上 JB 的位置：JB 表那一列（JB 名、XX 碼、X／Y／Z 燃機座標 in [mm]）與等角圖上的 JB 標籤。
    JB 表的列要同一列有三組座標（同一頁的剖面圖、改版說明也寫著 JB 名，p.11 SECTION B-B 的 'JB2T'、p.4 的 'JB10A & JB20RA'）；
    接線圖的 JB 有 KKS 時，表上那一列的 XX 碼本體要相同（JB637C-WL1 是 XBM01XD102，表上的 JB637C 是 XD101，不借）。
    等角圖＝沒有 JB 表的那一頁上的標籤（字少的頁）。→ {'table': (頁, 框, 座標文字) 或 None, 'iso': (頁, 框) 或 None}；都沒有回 None。"""
    nm = jb_short_base(name)
    core = kks_core(kks) if kks else ''
    res = {'table': None, 'iso': None}
    for pno, pg in enumerate(tx['pg'], 1):
        ws = disp_words(pg)
        hits = [w for w in ws if w['t'] == nm]
        if not hits:
            continue
        is_table = any(w['t'] == 'RDS-PP' for w in ws)
        if is_table and not res['table']:
            for w in hits:
                row = [x for x in ws if -14 <= x['y0'] - w['y0'] <= 14 and x['x0'] >= w['x0'] - 120 and x['x0'] < w['x0'] + 1100]
                nums = sorted([x for x in row if re.fullmatch(r'-?\d+\.\d+', x['t'])], key=lambda x: x['x0'])
                mm = sorted([x for x in row if re.fullmatch(r'\[-?\d+\.\d+\]', x['t'])], key=lambda x: x['x0'])
                xx = [x['t'] for x in row if re.fullmatch(r'XX[A-Z]{3}\d{2}[A-Z]{2}\d{3}', x['t'])]
                if len(nums) < 3 or len(mm) < 3:
                    continue
                if core and xx and not any(kks_core(x) == core for x in xx):
                    continue
                coords = '、'.join('%s %s in %s mm' % (ax, a['t'], b['t']) for ax, a, b in zip('XYZ', nums, mm))
                res['table'] = (pno, ubox([w] + nums[:3] + mm[:3], 3.0), coords)
                break
        elif not is_table and not res['iso'] and len(ws) < 600 and not (name and '-' in WG.jb_short(name) and nm != WG.jb_short(name)):
            res['iso'] = (pno, ubox([hits[0]], 4.0))
    return res if (res['table'] or res['iso']) else None


def gtjb_rows(tx):
    """GE 137T6223 JB 表的每一列 → [(頁, 箱名, KKS 本體, 'XX…' 原字)]（v14：給箱名與 KKS 交叉不一致的註記）。
    同一列＝XX 碼左邊、上下差 ≤ 5 pt 最近的那個字（列距約 22 pt；箱名欄寫的不是 JB 開頭的（'96TD-1A'）不收，免得借到上一列的箱名）。"""
    out = []
    for pno, pg in enumerate(tx['pg'], 1):
        ws = disp_words(pg)
        if not any(w['t'] == 'RDS-PP' for w in ws):
            continue
        for x in ws:
            if re.fullmatch(r'XX[A-Z]{3}\d{2}[A-Z]{2}\d{3}', x['t']):
                left = [y for y in ws if abs(y['y0'] - x['y0']) <= 5 and y['x1'] <= x['x0'] and x['x0'] - y['x1'] < 400]
                if left:
                    nm = max(left, key=lambda y: y['x1'])['t']
                    if re.fullmatch(r'JB\w+', nm):
                        out.append((pno, nm, kks_core(x['t']), x['t']))
    return out


def gtjb_conflicts(rows, name, kks, has_coords):
    """接線圖的 JB（箱名＋KKS）與 137T6223 JB 表交叉比對 → [(文字, 頁)]，只列出來、不判定座標屬於哪個箱子：
    表上 KKS 相同那一列的箱名不同（JB20RA 那一列是 XXCKB01XD102，接線圖與 GE 139T1903 把 CKB01XD102 叫 JB-529B）、
    或同名那一列的 KKS 不同；這個箱子已經用自己的同名同 KKS 那一列（has_coords）時，另一列同 KKS 的是表內重複（JB169B／JB34C 都是 XXMBY01XD109）。"""
    nm, core = WG.jb_short(name), kks_core(kks) if kks else ''
    if not nm or not core:
        return []
    out = []
    for pno, rn, rc, raw in rows:
        if rc == core and rn != nm:
            if has_coords:
                out.append(('GE 137T6223 的 JB 表上，KKS %s 有兩列：%s（卡上的座標取這一列）與 %s：表內同一個 KKS 給了兩個箱子，請以現場箱上的名牌為準'
                            % (raw, nm, rn), pno))
            else:
                out.append(('GE 137T6223 的 JB 表上，KKS %s 那一列的箱名是 %s，接線圖的 %s 也是這個 KKS：兩份文件把同一個 KKS 給了不同的箱名，'
                            '那一列的座標是哪一個箱子的不能判定，卡上不採用；請以現場箱上的名牌為準' % (raw, rn, nm), pno))
        elif rn == nm and rc != core and not has_coords:
            out.append(('GE 137T6223 的 JB 表上，%s 那一列的 KKS 是 %s，接線圖的 %s 是 %s：同名不同 KKS，'
                        '那一列的座標是哪一個箱子的不能判定，卡上不採用；請以現場箱上的名牌為準' % (rn, raw, nm, kks), pno))
    return out


def jb_norm(t):
    """圖上的箱名 → 比對用的寫法：'JB/16A-ABOVE'、'JB-5C'、'JB016A'、'(MAV01GD001)'、'JBX001,' → 'JB16A'、'JB5C'、'JB16A'、'MAV01GD001'、'JBX1'。"""
    t = re.sub(r'-(?:ABOVE|BELOW)$', '', (t or '').upper().strip('()[],.:;'))
    t = re.sub(r'[-/ ]', '', t)
    m = re.match(r'^(JB[RX]?)0*(\d.*)$', t)
    return m.group(1) + m.group(2) if m else t


def same_line(ws, w):
    """w 所在的那一行（同一條基線、字距 ≤ 2.5 個字高接下去的字）→ (左邊的字, 右邊的字)，各照離 w 的遠近排。"""
    h = max(w['y1'] - w['y0'], 1.0)
    row = sorted([x for x in ws if x is not w and abs(x['y0'] - w['y0']) <= 0.25 * h and abs(x['y1'] - w['y1']) <= 0.25 * h], key=lambda x: x['x0'])
    left, right, edge = [], [], w['x0']
    for x in sorted([x for x in row if x['x1'] <= w['x0'] + 1], key=lambda x: -x['x1']):
        if edge - x['x1'] > 2.5 * h:
            break
        left.append(x)
        edge = x['x0']
    edge = w['x1']
    for x in [x for x in row if x['x0'] >= w['x1'] - 1]:
        if x['x0'] - edge > 2.5 * h:
            break
        right.append(x)
        edge = x['x1']
    return left, right


def jb_label_ok(ws, w):
    """設備圖上的這個字是不是「標在箱子上」的標籤（v14 看圖查核後）：一般註記的句子（左邊 ≥ 5 個字或右邊 ≥ 3 個字：'… QTY 1, JBX001, CONTROL PANEL …'、
    'MAIN CONTROL PANEL JBR-6 WILL DEPEND ON …'）、TABLE 1 元件表的列（右邊接著說明 'JUNCTION BOX LEL PANEL …'，或同一欄上方有表頭）、
    走線說明（'TO JB-MAD50GD010 (HIDDEN)'，常疊成上下三行）都不算。"""
    left, right = same_line(ws, w)
    if len(left) >= 5 or len(right) >= 3:
        return False
    h = max(w['y1'] - w['y0'], 1.0)
    above = [x for x in ws if 0 < w['y0'] - x['y0'] <= 1.6 * h and x['x0'] < w['x1'] and x['x1'] > w['x0']]   # 走線說明常疊成三行：'TO' / 'JB-…' / '(HIDDEN)'
    below = [x for x in ws if 0 < x['y0'] - w['y0'] <= 1.6 * h and x['x0'] < w['x1'] and x['x1'] > w['x0']]
    if any(x['t'].upper() in ('TO', 'FROM') for x in ([left[0]] if left else []) + above):
        return False
    if any(x['t'].upper().strip(':.') in ('DESCRIPTION', 'TAG', 'TABLE') and 0 < w['y0'] - x['y0'] <= 25 * h and abs(x['x0'] - w['x0']) <= 200 for x in ws):
        return False        # 元件表（TABLE 1 'DEVICE TAG／DESCRIPTION'）的列：表頭在同一欄上方
    return not any('HIDDEN' in x['t'].upper() for x in right + below)


def jbdoc_locate(tx, skip, name, kks):
    """接線箱在設備圖（JBDOCS）上的標籤（v14）：先找 KKS 寫法（'JB-MAD20GD010'、封油盤標示的 'MKW15UC110'），沒有才找箱名（'JB-5C'、'JB/10A'、'JBR-7A'）——
    VE02 上 'JB/2' 這種短號在別的圖是另一個箱子，KKS 寫法比較準；KKS 找到的那一頁上，不是短號（'JB2'、'JB21'）的箱名也一起框。跳過有 skip 這個字的頁；
    註記句子、元件表的列、走線說明裡的不算（`jb_label_ok`），一頁只剩這些的就往下一頁找。
    → (頁, [框…（最多 4 個）], 圖上寫法, 'kks'／'name', 標籤旁圖上寫的 KKS 或 '') 或 None。"""
    names = {jb_norm(m.group(0)) for m in re.finditer(r'JB[RX]?[-/ ]?\d+[A-Z]?', (name or '').upper())}
    core = kks_core(kks) if kks else ''
    for by, want in (('kks', {core, 'JB' + core} if core else set()), ('name', names)):
        for pno, pg in (enumerate(tx['pg'], 1) if want else ()):
            ws = disp_words(pg)
            if skip and any(w['t'] == skip for w in ws):
                continue
            hits = [w for w in ws if jb_norm(w['t']) in want and jb_label_ok(ws, w)]
            if hits:
                if by == 'kks':
                    hits += [w for w in ws if jb_norm(w['t']) in names and not re.fullmatch(r'JB\d{1,2}', jb_norm(w['t'])) and jb_label_ok(ws, w)]
                kd = ''
                if by == 'name':   # 箱名標籤下方兩行內寫的 KKS（'JB21' 下一行 '(MAV01GD001)'、'JB-529A … CKB01XD103'）：與接線圖的不同時註記
                    w0 = hits[0]
                    h = max(w0['y1'] - w0['y0'], 1.0)
                    near = sorted([x for x in ws if 0 < x['y0'] - w0['y0'] <= 4.5 * h and abs(x['x0'] - w0['x0']) <= 6 * h
                                   and re.fullmatch(r'(?:[GS]\d{2}|XX)?[A-Z]{3}\d{2}[GUX][A-Z]\d{3}[A-Z]?', x['t'].strip('()[],.:;'))], key=lambda x: x['y0'])
                    # 只認箱子本身的 KKS 形（設備碼 G*／U*／X*：GD、UC、XD、XG…）；VE02 箱名下面列的是箱內元件（MAB12QN001-BG01），不算
                    kd = near[0]['t'].strip('()[],.:;') if near else ''
                return pno, [ubox([w], 3.0) for w in hits[:4]], hits[0]['t'].rstrip(',;:.'), by, kd
    return None


def kks_drawn_core(t):
    """字串裡第一個 KKS 的本體（去機組前綴與 XX，保留尾字母）：'JB512A/G11MKC10XG512A' → 'MKC10XG512A'、'(MAV01GD001)' → 'MAV01GD001'；沒有回 ''。"""
    m = re.search(r'(?:[GSC]\d{2}|XX)?([A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?)\b', (t or '').upper())
    return m.group(1) if m else ''


def jbdoc_names(tx, skip):
    """發電機外形圖視圖頁上畫出的接線箱名（'JB-5C'…；給「接線圖的箱子不在這張圖上」的註記）→ (排序後的箱名, [頁…])。"""
    got, pgs = set(), []
    for pno, pg in enumerate(tx['pg'], 1):
        ws = disp_words(pg)
        if skip and any(w['t'] == skip for w in ws):
            continue
        hs = {w['t'] for w in ws if re.fullmatch(r'JB-\d+[A-Z]?', w['t'])}
        if hs:
            got |= hs
            pgs.append(pno)
    return sorted(got, key=lambda t: (len(t), t)), pgs


def jb_short_base(name):
    """'JB1T/G11MBY01XD102' → 'JB1T'；'JB637C-WL1/…' → 'JB637C'（137T6223 只列到箱子本體）。"""
    n = WG.jb_short(name)
    return n.split('-')[0] if re.match(r'^JB\d+[A-Z]?-', n) else n


def resolve_title(lib, title):
    """檔名沒有文件號的圖（'noKKS_EQUIPMENT ARRANGEMENT - 480V MOTOR CONTROL CENTER FOR UNIT 1 GT1_revQ.pdf'）：檔名標題（去 'noKKS_' 與 '_rev…'）
    與 title 相同（不分大小寫）的 PDF 取最高版次（規則同 resolve_doc：排除副本旗標，同版取不像重複下載、路徑短的）→ {doc, rel, size, mtime, rev, title, alts} 或 {why}。"""
    cs = []
    for rel, size, mtime in lib:
        m = re.match(r'^(?:noKKS_)?(.*?)_rev([A-Z0-9]{1,3})\.*\.pdf$', rel.rsplit('/', 1)[-1], re.I)
        if m and m.group(1).strip().upper() == title.upper():
            cs.append((rel, size, mtime, m.group(2).upper()))
    if not cs:
        return {'why': '文件庫裡沒有檔名是「%s」的 PDF' % title}
    pool = [c for c in cs if not set(L.copy_flags(c[0])) & set(SKIP_FLAGS)] or cs
    top = max(L.rev_rank(c[3]) for c in pool)
    rel, size, mtime, rev = min((c for c in pool if L.rev_rank(c[3]) == top), key=lambda c: ('dupname' in L.copy_flags(c[0]), len(c[0]), c[0]))
    return {'doc': '', 'rel': rel, 'size': size, 'mtime': mtime, 'rev': rev, 'title': '', 'alts': len(cs) - 1}


def mcc_segments(pdf_abs, pno):
    """這一頁的框線（顯示座標）→ (水平線 [(y, x0, x1)…], 垂直線 [(x, y0, y1)…])：只收有顏色、線寬 > 0 的（寬 0 的是盤內單線圖的走線，會穿過格子）；
    'l' 直線、're' 長方形、'qu' 四邊形都拆成邊；長度 < 4 pt 的不收。"""
    import fitz
    doc = fitz.open(pdf_abs)
    try:
        page = doc[pno - 1]
        M = page.rotation_matrix
        hs, vs = [], []
        for it in page.get_drawings():
            if not it.get('color') or not (it.get('width') or 0) > 0:
                continue
            for x in it['items']:
                if x[0] == 'l':
                    sg = [(x[1], x[2])]
                elif x[0] == 're':
                    r_ = x[1]
                    sg = [(r_.tl, r_.tr), (r_.tr, r_.br), (r_.br, r_.bl), (r_.bl, r_.tl)]
                elif x[0] == 'qu':
                    q = x[1]
                    sg = [(q.ul, q.ur), (q.ur, q.lr), (q.lr, q.ll), (q.ll, q.ul)]
                else:
                    continue
                for a_, b_ in sg:
                    a_, b_ = a_ * M, b_ * M
                    if abs(a_.y - b_.y) < 0.6 and abs(a_.x - b_.x) >= 4:
                        hs.append(((a_.y + b_.y) / 2.0, min(a_.x, b_.x), max(a_.x, b_.x)))
                    elif abs(a_.x - b_.x) < 0.6 and abs(a_.y - b_.y) >= 4:
                        vs.append(((a_.x + b_.x) / 2.0, min(a_.y, b_.y), max(a_.y, b_.y)))
        return hs, vs
    finally:
        doc.close()


def mcc_name(t):
    """排的名稱正規化（MCC_NAME_RE）：'480 V AC MCC GT-112' → 'MCC-GT112'；沒有回 ''。"""
    m = MCC_NAME_RE.search((t or '').upper())
    return '%s-%s%s' % (m.group(1), m.group(2), m.group(3)) if m else ''


def mcc_pages(tx):
    """盤面配置圖一份 → {排（'G11BFB10'）: (頁, 標題框或 None, 圖上的排名稱 'MCC-GT111'／'PC-GT122' 或 '')}：只看有 'FRONT VIEW' 圖名的頁。排名靠正視圖上方的大字標題（'G11BFB10 (MCC GT111)'、
    'G11BKB20 ESSENTIAL MCC …'，字高 ≥ 8 pt；圖框右下標題欄的同名小字不算）或 PC 的 '(G11BFA10)'；都沒有（ST 的 EMCC 標題是線條字）才看這一頁斷路器
    編號（'S10BKB10QA401'）最多的那一排（≥ 3 個）。同一頁兩排（GT 的 BFB10＋BGB10）各記各的標題框，格位標籤歸給水平距離最近的標題。
    同一排出現在好幾頁時取格位標籤最多的那一頁。"""
    best = {}
    for pno, pg in enumerate(tx['pg'], 1):
        ws = disp_words(pg)
        if not any(w['t'] == 'FRONT' and any(x['t'] == 'VIEW' and 0 < x['x0'] - w['x1'] < 12 and abs(x['y0'] - w['y0']) < 2 for x in ws) for w in ws):
            continue
        titles = [(w['t'], w) for w in ws if re.fullmatch(r'[GS]\d{2}B[FGK]B\d0', w['t']) and w['y1'] - w['y0'] >= 8]
        titles += [(m.group(1), w) for w in ws for m in [re.fullmatch(r'\(([GS]\d{2}B[FGK]A\d0)\)', w['t'])] if m]
        if not titles:
            c = Counter(m.group(1) for w in ws for m in [re.match(r'([GS]\d{2}B[FGK][AB]\d0)QA\d', w['t'])] if m)
            if c and c.most_common(1)[0][1] >= 3:
                titles = [(c.most_common(1)[0][0], None)]
        if not titles:
            continue
        labs = [w for w in ws if MCC_LAB_RE.match(w['t'])]
        for name, tw in titles:
            n = sum(1 for w in labs if mcc_owner(titles, w) == name)
            if n and (name not in best or n > best[name][2]):
                nm = ''
                if tw and tw['t'].startswith('('):   # PC：'(G11BFA10)' 附近的 'PC-GT111'
                    pcs = [w for w in ws if re.fullmatch(r'PC-(?:GT|ST)\d{2,3}', w['t'])]
                    if pcs:
                        nm = mcc_name(min(pcs, key=lambda w: abs(w['x0'] - tw['x0']) + abs(w['y0'] - tw['y0']))['t'])
                elif tw:                             # MCC：標題同一行後面的 '(MCC GT111)'、'ESSENTIAL MCC (EMCC GT11)'
                    nm = mcc_name(' '.join(w['t'] for w in sorted([w for w in ws if abs(w['y0'] - tw['y0']) < 2 and tw['x0'] <= w['x0'] <= tw['x1'] + 260],
                                                                  key=lambda w: w['x0'])))
                best[name] = (pno, tw, n, nm)
    return {k: (v[0], v[1], v[3]) for k, v in best.items()}


def mcc_owner(titles, w):
    """格位標籤歸給哪一排：只有一排就是它；兩排以上取標題中心水平距離最近的。"""
    if len(titles) == 1:
        return titles[0][0]
    cx = (w['x0'] + w['x1']) / 2.0
    return min(titles, key=lambda t: abs((t[1]['x0'] + t[1]['x1']) / 2.0 - cx) if t[1] else 1e9)[0]


def mcc_cell(hs, vs, w):
    """格位標籤（格子左下角）→ 這一格的框 (x0, y0, x1, y1)（顯示座標）或 None：左＝標籤左邊最近、跨過標籤高度的垂直線；下＝標籤下方最近、跨過標籤的水平線；
    右＝標籤右邊最近的垂直線（MCC 是門板線，右邊 10 pt 的配線槽不算）；上＝標籤上方最近、橫跨這一格八成寬的水平線（格內的小元件符號不算）。"""
    cx, cy = (w['x0'] + w['x1']) / 2.0, (w['y0'] + w['y1']) / 2.0
    lefts = [x for x, y0, y1 in vs if w['x0'] - 8 <= x <= w['x0'] + 0.8 and y0 - 1 <= cy <= y1 + 1]
    bots = [y for y, x0, x1 in hs if w['y1'] - 0.8 <= y <= w['y1'] + 8 and x0 - 1 <= cx <= x1 + 1]
    if not lefts or not bots:
        return None
    x0, y1 = max(lefts), min(bots)
    rights = [x for x, ya, yb in vs if w['x1'] + 4 <= x <= x0 + 140 and ya - 1 <= cy <= yb + 1]
    if not rights:
        return None
    x1 = min(rights)
    wd = x1 - x0
    tops = [y for y, xa, xb in hs if y1 - 160 <= y <= w['y0'] - 3 and xa <= x0 + 0.2 * wd and xb >= x1 - 0.2 * wd]
    if not tops:
        return None
    return (x0, max(tops), x1, y1)


def mcc_np(hs, vs, ws, lineup_ws, tw, a, b):
    """EMCC 的 NP 區（'NP3-3'）：正視圖上只有各區頂上的 'NP3-1' 是文字，小格的銘牌是線條字——區＝'NPa-1' 字左右的垂直線，
    小格＝區內橫跨八成寬的水平線由上往下數第 b 格（照順序推，框標 approx）；另框 NP 表（'NP NO.' 那一欄）上 'NPa-b' 那一列。
    → (區內小格的框或 None, 表上那一列的框或 None, 表上那一列的說明字)。"""
    head = 'NP%d-1' % a
    nphdr = [w for w in ws if w['t'] == 'NP' and any(x['t'] == 'NO.' and 0 < x['x0'] - w['x1'] < 10 and abs(x['y0'] - w['y0']) < 2 for x in ws)]
    in_tab = lambda w: any(abs(w['x0'] - h['x0']) <= 8 and w['y0'] > h['y0'] for h in nphdr)   # noqa: E731
    heads = [w for w in lineup_ws if w['t'] == head and not in_tab(w)]
    cell = None
    if heads:
        h = heads[0] if not tw else min(heads, key=lambda w: abs(w['y0'] - tw['y1']))
        hy = (h['y0'] + h['y1']) / 2.0
        ls = [x for x, y0, y1 in vs if x <= h['x0'] and y0 <= hy + 30 <= y1 and y1 - y0 >= 60]   # 整區高的線（'NP1-1' 字外面的銘牌小框不算）
        rs = [x for x, y0, y1 in vs if x >= h['x1'] and y0 <= hy + 30 <= y1 and y1 - y0 >= 60]
        if ls and rs:
            x0, x1 = max(ls), min(rs)
            ys = sorted(y for y, xa, xb in hs if y >= h['y0'] - 12 and xa <= x0 + 3 and xb >= x1 - 3)   # 小格隔板從區的左緣拉到右緣（格內 C650 等元件框不算）
            sep = []
            for y in ys:
                if not sep or y - sep[-1] > 1.5:
                    sep.append(y)
            if len(sep) > b:
                cell = (x0, sep[b - 1], x1, sep[b])
    row, txt = None, ''
    tab = sorted([w for w in ws if MCC_LAB_RE.match(w['t']) and w['t'].startswith('NP') and in_tab(w)], key=lambda w: w['y0'])
    me = [w for w in tab if w['t'] == 'NP%d-%d' % (a, b)]
    if me:   # 表格的格子：左右＝表格的垂直框線（右邊是 DESCRIPTION 欄的右框），上下＝橫跨整張表的水平線（表格右邊緊鄰 TOP VIEW，不用字的範圍推）
        w = me[0]
        yc = (w['y0'] + w['y1']) / 2.0
        hdr = next((h for h in nphdr if abs(h['x0'] - w['x0']) <= 8), None)
        desc = [x for x in ws if hdr and x['t'] == 'DESCRIPTION' and abs(x['y0'] - hdr['y0']) < 3]
        ls = [x for x, y0, y1 in vs if x <= w['x0'] + 0.5 and y0 - 1 <= yc <= y1 + 1]
        rs = [x for x, y0, y1 in vs if desc and x >= desc[0]['x1'] and y0 - 1 <= yc <= y1 + 1]
        if ls and rs:
            x0, x1 = max(ls), min(rs)
            ts = [y for y, xa, xb in hs if y <= w['y0'] + 0.5 and xa <= x0 + 3 and xb >= x1 - 3]
            bs = [y for y, xa, xb in hs if y >= w['y1'] - 0.5 and xa <= x0 + 3 and xb >= x1 - 3]
            if ts and bs:
                row = (x0, max(ts), x1, min(bs))
                txt = text_of([x for x in ws if x is not w and row[0] <= (x['x0'] + x['x1']) / 2.0 <= row[2] and row[1] <= (x['y0'] + x['y1']) / 2.0 <= row[3]])
    return cell, row, txt


def mcc_content(ws, box, lab):
    """格內的字（去掉格位標籤；重複印的粗體字只留一個；'S10MAV01GQ007' 下一個字 '-MA01' 接回去）→ (說明字串, [KKS…])。"""
    inside = [w for w in ws if box[0] <= (w['x0'] + w['x1']) / 2.0 <= box[2] and box[1] <= (w['y0'] + w['y1']) / 2.0 <= box[3] and w is not lab]
    seen, keep = set(), []
    for w in inside:
        k = (w['t'], round(w['x0']), round(w['y0']))
        if k not in seen:
            seen.add(k)
            keep.append(w)
    t = re.sub(r'(\b[GSC]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?)\s+(-[A-Z]{1,2}\d{2})\b', r'\1\2', text_of(keep))
    return t, list(dict.fromkeys(m.group(0) for m in MCC_KKS_RE.finditer(t)))


def shield_bars(ws):
    """接線圖一頁盤欄底部的屏蔽排說明（兩份接線圖的範本：'IS' 右下是 'B' 排、'OS' 右下是 'A' 排，OS 那一排接到接地符號）→ {'IS': 'B', 'OS': 'A'} 或 {}。
    各芯的屏蔽線（SH-n）畫到盤欄、沒有端子號＝接在盤內的 IS 屏蔽排；電纜的總屏蔽（OS）接 A 排再接地。左上角圖號欄的 'IS' 旁邊沒有這兩個字母，不算。"""
    def letter(w, want):
        c = [x for x in ws if x['t'] == want and 4 < x['x0'] - w['x1'] < 90 and -6 < x['y0'] - w['y0'] < 30]
        return min(c, key=lambda x: (x['x0'] - w['x1']) + abs(x['y0'] - w['y0'])) if c else None
    for i_ in (w for w in ws if w['t'] == 'IS'):
        b_ = letter(i_, 'B')
        o_ = [w for w in ws if w['t'] == 'OS' and 0 < w['y0'] - i_['y0'] < 40 and abs(w['x0'] - i_['x0']) < 8]
        if b_ and o_ and letter(o_[0], 'A'):
            return {'IS': 'B', 'OS': 'A'}
    return {}


def mcc_match(codes, txt, lineup, kkss, own=''):
    """格內寫的 KKS 與接線圖這個元件的 KKS 比一比（不判定誰對）：same＝與這個元件自己的 KKS（own）本體相同（去機組前綴，'-MA01' 馬達字尾不看）；
    same_rel＝與接線圖說明格寫的、或說明格點名的設備的 KKS 相同（同一個啟動器的另一個元件、馬達的接點），這個元件自己的 KKS 沒有寫在格內；system＝系統碼（前 5 碼）相同；
    breaker＝只寫了這一排自己的斷路器編號（'G11BFB10QA402'），沒有負載的 KKS 可比；space＝格內寫 SPACE／SPARE；diff＝寫了別的設備；none＝沒有字；
    nokks＝接線圖這一條沒有 KKS 可比（馬達的 Available／Run 接點等，說明格也沒有點名認得的 GE 編號）。"""
    load = [c for c in codes if not c.startswith(lineup)]
    pc = {kks_core(k)[:10] for k in kkss if kks_core(k)}
    if not pc:
        return 'space' if re.search(r'\bSPA(?:CE|RE)\b', txt) else 'nokks'
    lc = [kks_core(c.split('-')[0])[:10] for c in load]
    oc = kks_core(own)[:10] if own and kks_core(own) else ''
    if oc and oc in lc:
        return 'same'
    if any(c in pc for c in lc):
        return 'same_rel'
    if any(c[:5] in {x[:5] for x in pc} for c in lc):
        return 'system'
    if load:
        return 'diff'
    if codes:
        return 'breaker'
    if re.search(r'\bSPA(?:CE|RE)\b', txt):
        return 'space'
    return 'none'


def board_box(pg, pos, split=False):
    """GE 盤面配置圖（M0213 'CA004 BACK PANEL'）上板位 '1L1A' 的大約範圍：欄標籤 '1L'（頁面上緣）的 x、列標籤 '1A' 到 '1B'（左邊一排）的 y。
    板名 '1L1A' 本身是線條字（不在文字層），所以框是由欄、列標籤推算的範圍（卡上講明「約略」）。split＝這一層的 A、B 兩列是兩片板
    （組態裡 xNyA 與 xNyB 都有：STTC、SCSA、STAI 一列一片），只框這一片那一半；TDBT 這種一片跨兩列的框整層。→ 顯示座標的框或 None。"""
    m = re.match(r'^(\d[A-Z])(\d)([A-Z])$', pos)
    if not m:
        return None
    ws = disp_words(pg)
    lab = [w for w in ws if re.fullmatch(r'\d[A-Z]', w['t'])]
    if not lab:
        return None
    ytop = min(w['y0'] for w in lab) + 10        # 欄標籤＝最上面那一排（汽機 M0213 在 y≈100、燃機 137T7182AL 在 y≈158），以下是列標籤
    cols = [w for w in lab if w['y0'] < ytop]
    if not cols:
        return None
    cx0 = min(w['x0'] for w in cols)
    rows = {}
    for w in sorted([w for w in ws if re.fullmatch(r'[1-5][AB]', w['t']) and cx0 - 300 < w['x1'] < cx0 - 40 and w['y0'] > ytop], key=lambda w: w['x0']):
        rows[w['t']] = w                         # 同一頁別的視圖也有列標籤（燃機 137T7182AL 左邊 x≈150）：只收緊靠欄標籤左側那一排，取最靠右的
    col = next((w for w in cols if w['t'] == m.group(1)), None)
    ra, rb = rows.get(m.group(2) + 'A'), rows.get(m.group(2) + 'B')
    if not col or not ra or not rb:
        return None
    c = (col['x0'] + col['x1']) / 2.0
    others = [abs((w['x0'] + w['x1']) / 2.0 - c) for w in cols if w is not col]
    half = 0.45 * min(others) if others else 85.0
    ya, yb = (ra['y0'] + ra['y1']) / 2.0, (rb['y0'] + rb['y1']) / 2.0
    pitch = max(yb - ya, 20.0)
    box = (c - half, ya - 0.6 * pitch, c + half, yb + 0.6 * pitch)
    if split:
        mid = (ya + yb) / 2.0
        box = (box[0], box[1], box[2], mid) if m.group(3) == 'A' else (box[0], mid, box[2], box[3])
    if yb <= ya or box[0] < 0 or box[1] < 0 or box[2] > pg['w'] + 1 or box[3] > max(pg['w'], pg['h']) + 1:
        return None
    return box


def boards_index(path):
    """signal-atlas 控制器索引 → {(機組, 板位)}：組態裡有的端子板（給 board_box 判斷同一層 A／B 是不是兩片板）。沒有索引回空集合。"""
    if not path or not os.path.exists(path):
        return set()
    import sqlite3
    unit_of = {c: u for u, v in UNIT_CTRLS.items() for c in v}
    c = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    out = {(unit_of[ctrl], pos) for ctrl, pos in c.execute('select m.ctrl, b.position_r from io_board b join io_module m on m.id = b.module_id where m.ctrl in (%s)'
                                                            % ','.join('?' * len(unit_of)), list(unit_of)) if pos and '-' not in pos}
    c.close()
    return out


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


def io_index(path):
    """signal-atlas 控制器索引 → (by_screw, by_dev)（v14：一號機三台的控制器，UNIT_CTRLS）：
    by_screw＝{(機組, 櫃, 板位, 板名, 螺絲號): [{ctrl, mod, pt, sn, var, dt, tb}…]}——只收控制器自己的板（position_r 不含 '-'；
      G11 底下借列的 G11S 板 'CA002-1H1A' 是同一片板的第二份）；櫃號不是 CAnnn 的記成 ''（S1S 的 io_module.cabinet 是 'Group'）；tb＝io_screw.note 的端子排（TDBT 'TB1'＝繼電器／'TB2'＝接點，
      兩排螺絲號都從 1 起、會重號；SCSA 'SCSA-TB1'；TCSA 'TCSA-TB4'、'WCSA-TB1'；PulseRate 的 note 是組態字串、不是端子排）；
    by_dev＝{(控制器, 模組, 板位, DeviceTag): [(點, 變數)…]}。沒有索引回 (None, None)。"""
    if not path or not os.path.exists(path):
        return None, None
    import sqlite3
    ctrls = [c for v in UNIT_CTRLS.values() for c in v]
    unit_of = {c: u for u, v in UNIT_CTRLS.items() for c in v}
    c = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    q = ('select p.ctrl, m.name, m.cabinet, b.position_r, b.name, p.name, s.name, s.number, s.note, v.name, p.device_tag from io_point p '
         'join io_module m on m.id = p.module_id join io_board b on b.id = p.board_id left join io_screw s on s.point_id = p.id '
         'left join variable v on v.id = p.var_id where p.ctrl in (%s)' % ','.join('?' * len(ctrls)))
    by_screw, by_dev = {}, defaultdict(list)
    for ctrl, mod, cab, pos, board, pt, sn, num, note, var, dt in c.execute(q, ctrls):
        if not pos or '-' in pos:
            continue
        if num is not None:                               # 同一顆螺絲可能掛在好幾個點上（TCSA 的 PR2H 同時列在 PulseRate1、PulseRate2）
            m = re.match(r'^(?:([A-Z]{4})-)?TB(\d)$', note or '')
            tb = ('TB' + m.group(2) if not m.group(1) or m.group(1) == board else '%s-TB%s' % (m.group(1), m.group(2))) if m else ''
            by_screw.setdefault((unit_of[ctrl], cab if re.fullmatch(r'CA\d{3}', cab or '') else '', pos, board, int(num)), []).append(
                {'ctrl': ctrl, 'mod': mod, 'pt': pt, 'sn': sn, 'var': var or '', 'dt': dt or '', 'tb': tb})
        if dt:
            k = (ctrl, mod, pos, dt)
            if (pt, var or '') not in by_dev[k]:
                by_dev[k].append((pt, var or ''))
    c.close()
    return by_screw, by_dev


def ff_index(path):
    """signal-atlas 控制器索引 → {(機組, 全域段號 S): [變數名…]}：FF 元件的變數宣告在 'FFBInputs_7HA03.FF_IN_S28.FF_AI_11.…'（FF_OUT 同），
    S＝8(n−1)+m 就是接線圖上 FFPCn 的第 m 段（GE H1 元件報告 'FFPC4-S4-S28' 這種寫法直接寫出）。沒有索引回 None。"""
    if not path or not os.path.exists(path):
        return None
    import sqlite3
    unit_of = {c: u for u, v in UNIT_CTRLS.items() for c in v}
    c = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    out = defaultdict(list)
    q = "select ctrl, name, decl_connection from variable where (decl_connection like '%%FF_IN_S%%' or decl_connection like '%%FF_OUT_S%%') and ctrl in (%s)" \
        % ','.join('?' * len(unit_of))
    for ctrl, name, dc in c.execute(q, list(unit_of)):
        m = re.search(r'\bFF_(?:IN|OUT)_S(\d+)\b', dc or '')
        if m:
            out[(unit_of[ctrl], int(m.group(1)))].append(name)
    c.close()
    return dict(out)


def norm_tb(board, tb):
    """接線圖盤端子格的端子排 → 與 io_index 的 tb 同一種寫法（'SCSA-TB1' 在 SCSA 板上＝'TB1'）。"""
    m = re.match(r'^(?:([A-Z]{4})-)?TB(\d)$', tb or '')
    if not m:
        return ''
    return 'TB' + m.group(2) if not m.group(1) or m.group(1) == board else '%s-TB%s' % (m.group(1), m.group(2))


def io_lookup(by_screw, unit, c):
    """一條芯的盤端子（term_parts 的 pos／board／tb／num）→ (候選點, how)。how＝''（照圖上的板名與螺絲號）、'tbtc'（圖上寫 TBTC、組態在同一板位是
    STTC：TBTC 每通道 2 顆螺絲，換算通道 ch＝⌈n/2⌉ 再取 STTC 該通道的 P／N 腳；GE 燃機圖 p.202、p.622 的寫法，A2 驗過 14／14 對）、
    'tb_mismatch'（圖上寫的 TB 與組態不同，候選照列給人看）。"""
    m = re.match(r'^(CA\d{3})-(\w+)$', c['pos'])
    cab, pos = m.groups() if m else ('', c['pos'])
    if not pos or not c['num'].isdigit():
        return [], ''
    n = int(c['num'])
    cands = by_screw.get((unit, cab, pos, c['board'], n), []) or by_screw.get((unit, '', pos, c['board'], n), [])   # S1S 的櫃號在索引裡是 'Group'
    if not cands and not cab:
        cands = [h for k, v in by_screw.items() if k[0] == unit and k[2] == pos and k[3] == c['board'] and k[4] == n for h in v]
    tb = norm_tb(c['board'], c.get('tb'))
    if cands and tb and any(h['tb'] for h in cands):
        f = [h for h in cands if h['tb'] == tb]
        if not f:
            return cands, 'tb_mismatch'
        cands = f
    if not cands and c['board'] == 'TBTC':
        ch = (n + 1) // 2
        pin = 'TC%02d%s' % (ch, 'P' if n % 2 else 'N')
        cands = [h for k, v in by_screw.items() if k[0] == unit and (not cab or k[1] == cab) and k[2] == pos and k[3] == 'STTC' for h in v
                 if h['sn'] == pin]
        if cands:
            return cands, 'tbtc'
    return cands, ''


def end_toks(v):
    """接線箱／MCC 格的寫法 → (前 8 碼, 其餘各段)：'C10BBA10-5_2'、'C10BBA10_5-2' → ('C10BBA10', ['5', '2'])；'S10BGA10_2_2C' → ('S10BGA10', ['2', '2C'])。"""
    v = (v or '').strip().lstrip('=- ').upper()
    return v[:8], [t for t in re.split(r'[-_\s]+', re.sub(r'\([A-Z]+\)$', '', v[8:])) if t]   # 'G12BGA10-1B(Rear)'＝1B


def same_end(a, b):
    """v17：接線圖與電纜表寫的同一端是不是同一個（分隔字元不計；一邊只寫格、另一邊寫欄＋格算同一個：'S10BGA10_2_2C' ↔ 'S10BGA10_2C'）。
    HRSG MCC 的 'G12BKB30_A9_A2D'：格位是最後一段 A2D，中間的 A9 是盤面配置圖那一格裡寫的單元標籤（電纜表寫成 A2_A2D），只比格位。"""
    (la, ta), (lb, tb) = end_toks(a), end_toks(b)
    if la != lb:
        return False
    if ta and tb and re.fullmatch(r'A\d{1,2}[A-H]', ta[-1]) and re.fullmatch(r'A\d{1,2}[A-H]', tb[-1]):
        return ta[-1] == tb[-1]
    n = min(len(ta), len(tb))
    return ta[len(ta) - n:] == tb[len(tb) - n:]          # 一邊只寫排（'G11MSA30'、'C00BQV10'）＝沒有可比的


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


def dt_parts(dt):
    """組態 DeviceTag → 比對用的各段（大寫）：'MAD10BG021/VP-1X' → 兩段；'77NH-1,2,3' → 77NH-1／77NH-2／77NH-3；'23HT-3A/3B/ON' → 23HT-3A／23HT-3B／23HT-3ON
    （後面幾段取代結尾）；'74-2(A)' → 74-2（括號裡的單一字母是接點別）。"""
    out = []
    for part in re.split(r'\s+', re.sub(r'-\s+', '-', (dt or '').strip().upper())):
        part = re.sub(r'\([A-Z]\)$', '', part)
        for sep in (',', '/'):
            segs = [x for x in part.split(sep) if x]
            if len(segs) > 1 and all(len(x) < len(segs[0]) for x in segs[1:]):
                out += [segs[0]] + [segs[0][:len(segs[0]) - len(x)] + x for x in segs[1:]]
                break
        else:
            out += [x for x in re.split(r'[,/]', part) if x]
        out.append(part)
    return [x for x in out if x]


def io_rel(h, e, kks, dkks=(), other=None):
    """控制器 I/O 點與這個元件的關係（v14 擴充；v13 只有 same／loc）：
      ✓ 'same'（同 KKS、同 GE 編號，或 DeviceTag 是 GE 編號的一段：圖 74/86G-1A、組態 86G-1A）、'logic'（對照表的 Mark VIe 訊號就是這個點的變數，
        或變數名含 GE 編號：d_20fy2960_o）、'equip'（DeviceTag 是同一個設備的 KKS——對照表的或圖上寫在 GE 編號旁的：MAV01AP003 與 72EBOP）、
        'loc'（同位置不同量測碼：LVDT 電源點）、'suffix'（4WW ↔ 4WW-1、PAL-3462 ↔ PAL-3462C）；
      ≈ 'alias'（DeviceTag 不是對照表裡的別顆 GE 編號，或數字相同字母不同：30DRYFAULT ↔ 30DRY-FLT、ME-2996 ↔ MIC-2996——可能是同一顆的另一種寫法）；
      ✗ 'other'（DeviceTag 是對照表裡的另一個 GE 編號，數字也不同：23WR-1B 的螺絲在組態是 23WR-3A）、'spare'（這顆螺絲的點沒有變數也沒有 DeviceTag：組態裡是備用點）。
    other＝函式（DeviceTag 一段 → 對照表裡的鍵集合），沒有就不分 alias／other。"""
    dt = re.sub(r'-\s+', '-', h['dt'] or '')            # 組態 DeviceTag 'MAV01AP003- MA01'（連字號後多一個空白）
    if e.get('system') == 'KKS':                          # v17：KKS 編號（BOP 控制器同時管 G11／G12／S10 的同名設備，比本體會把別台的點判成同一個）
        full = [m_.group(0) for m_ in re.finditer(r'(?<![A-Z0-9])[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}', ('%s %s' % (dt, h['var'] or '')).upper())]
        me = e['tag'].upper()
        if any(f == me for f in full):
            return 'same' if me in dt.upper() else 'logic'   # DeviceTag 是母設備（EW001）、變數是 G11MST10EW005XB01：變數就是這個設備的點
        if any(f[3:] == me[3:] and f[:3] != me[:3] for f in full):
            return 'unit'                                 # 只差機組碼（S10BGB10EG001 ↔ 組態 G11BGB10EG001）
    rel = io_relates(dt, e['tag'], re.sub(r'[\s-]', '', kks or ''))   # KKS 帶連字號（MAB12QN001-MB01）時 io_relates 永遠對不上
    if rel == 'same':
        return rel
    forms = {ge_cmp(f) for f in e['forms']}
    parts = dt_parts(dt)
    if any(ge_cmp(x) in forms for x in parts):
        return 'same'
    kfull = {kks_core(x) for x in list(e['kks']) + [kks] if kks_core(x)}
    if any(kks_core(x) in kfull for x in parts if kks_core(x)):
        return 'same'                                     # 合寫的 KKS 展開後相同（'MAV01EB011,12,13' 一個指令同時給 HTR-1／2／3）
    tparts = {ge_cmp(x) for x in e['tag'].split('/') if len(ge_cmp(x)) >= 3}
    if len(tparts) > 1 and any(ge_cmp(x) in tparts for x in parts):
        return 'same'
    if any(ge_cmp(x) in {ge_cmp(t_) for t_ in e.get('linked') or ()} for x in parts):
        return 'equip'                                    # 對照表連在一起的同一條量測鏈（傳送器 96CT-IF-1R ↔ 熱電偶 CT-IF-1）
    if h['var'] and ('%s.%s' % (h['ctrl'], h['var'])).lower() in {x.lower() for x in e['logic']}:
        return 'logic'
    tc = ge_cmp(e['tag'])
    if other is not None and dt and h['var'] and len(tc) >= 4 and tc in ge_cmp(h['var']):
        # v16：變數名含這個編號、DeviceTag 卻是對照表上數字不同的別顆（汽機 52L2／52L3 CLOSE 的變數名與 DeviceTag 交叉）→ 先判 ✗，不讓變數名蓋掉
        owners = {k for x in parts + [dt.upper()] for k in other(x)} - {'%s|%s' % (e['system'], e['tag'])}   # DeviceTag 有空白（'52L2 CLOSE'）時整串也比
        fam = [k for k in owners if min(len(ge_cmp(k.split('|', 1)[1])), len(tc)) >= 3
               and (ge_cmp(k.split('|', 1)[1]) in tc or tc in ge_cmp(k.split('|', 1)[1]))]
        dig = re.sub(r'\D', '', e['tag'])
        if owners and not fam and all(re.sub(r'\D', '', k.split('|', 1)[1]) != dig for k in owners):
            return 'other'
    if h['var'] and len(tc) >= 4 and re.search(r'\d', tc) and tc in ge_cmp(h['var']):
        return 'logic'
    full = {kks_core(x) for x in list(e['kks']) + [kks] + list(dkks) if len(kks_core(x)) >= 10}
    for x in parts:
        c = kks_core(x)
        if len(c) >= 10 and any(c[:10] == f[:10] and (len(c) == 10 or len(f) == 10 or c == f) for f in full):
            return 'equip'                                # 同一個設備（KKS 前 10 碼）；兩邊都有尾碼又不同（MAB10BT005A／B、-MB01／-MB02）是兄弟元件，不算
    if rel:
        return rel
    t = e['tag'].upper()
    tps = [t] + [x for x in t.split('/') if len(ge_cmp(x)) >= 3 and x != t]
    for x in parts:
        for tp in tps:
            if x == tp + '-1' or tp == x + '-1' or (x.startswith(tp) and re.fullmatch(r'-?[A-Z]|-\d', x[len(tp):])) \
                    or (tp.startswith(x) and re.fullmatch(r'-?[A-Z]', tp[len(x):])):
                return 'suffix'                           # 4WW ↔ 4WW-1、PAL-3462 ↔ PAL-3462C、74/86AT-A ↔ 86AT
    if not dt and not h['var']:
        return 'spare'
    if other is not None:
        me, tc = '%s|%s' % (e['system'], e['tag']), ge_cmp(e['tag'])
        owners = {k for x in parts for k in other(x)} - {me}
        fam = [k for k in owners if min(len(ge_cmp(k.split('|', 1)[1])), len(tc)) >= 3
               and (ge_cmp(k.split('|', 1)[1]) in tc or tc in ge_cmp(k.split('|', 1)[1]))]
        if fam and len(fam) == len(owners):
            return 'equip'                                # DeviceTag 屬於同一個設備家族（ESOP ↔ ESOP-27ST、CT-IF-1 ↔ 96CT-IF-1R）
        dig = re.sub(r'\D', '', e['tag'])
        for x in parts:
            ks = other(x)
            if ks and not any(re.sub(r'\D', '', k.split('|', 1)[1]) == dig for k in ks):
                return 'other'
    return 'alias'


IO_RANK = {'same': 0, 'logic': 1, 'equip': 2, 'loc': 2, 'suffix': 3, 'alias': 5, 'other': 6, 'unit': 6, 'spare': 7}   # unit（v17）：只差機組碼
IO_OK = ('same', 'logic', 'equip', 'loc', 'suffix')   # 卡上打 ✓ 的關係；alias＝≈；other／spare＝✗


def load_notes(path, log):
    """接線路徑的人工註記（文件互相矛盾、圖面筆誤…；查證後寫進 ge_tags_dir 的 wire_notes.json，不進 repo）→ {GE 鍵: [[文字, 出處]…]}。
    鍵可以加 '@G12'（只掛這一台）或 '@p111'（只掛接線圖第 111 頁那一條）。"""
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


def load_curated(path, log):
    """v16 人工查證資料（ge_tags_dir 的 wire_curated.json，不進 repo）：mid＝現場元件與接線箱端子之間的中間設備、branch＝Bently 3500 並聯分支、
    signal＝Mark VIe 各點的訊號型式與迴路供電規則（每條附手冊或圖面出處）。沒有這個檔就三樣都不做。"""
    if not path or not os.path.exists(path):
        log('（沒有 %s：迴路圖不畫中間設備與 3500 分支，也不判訊號型式與供電）' % path)
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def sheet_rec(d, pg, pno, n_pages, R, method, kind, tags):
    """sheets 的一筆（＝loc_ge／pid_ge 同一套欄位與算法）。"""
    w_pt, h_pt = L.upright_size(pg, R)
    return {'rel': d['rel'], 'file': d['rel'].rsplit('/', 1)[-1], 'doc': d.get('doc') or '', 'rev': d.get('rev') or '', 'title': d.get('title') or '',
            'page': pno, 'pages': n_pages, 'rot': R, 'rot_method': method, 'w_pt': round(w_pt, 1), 'h_pt': round(h_pt, 1),
            'label_pt': L.label_height_pt(pg['words']), 'grid': L.detect_grid(L.border_labels(pg, R)), 'words': len(pg['words']), 'ocr': False,
            'tags': tags, 'src': {'size': d['size'], 'mtime': d['mtime']}, 'kind': kind}


def build(a, log):
    t0 = time.time()
    kks = bool(getattr(a, 'kks', False))   # v17：KKS 版（wire_kks.py 呼叫）——接線圖上沒有 GE 編號、只有 KKS 的元件；GE 版（False）的輸出不變
    if kks:
        import wire_epc as WP
    KP = r'[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}' if kks else r'[SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}'   # 盤／JB 的 KKS（KKS 版多 C10、C00 的共用盤與 JB）
    epc_kinds = {kd_ for kd_, _dn, _zh in WP.EPC_DOCS} if kks else set()
    uord = lambda u: (SITE_UNITS.index(u) if u in SITE_UNITS else len(SITE_UNITS), u)   # noqa: E731  機組排序（KKS 版多 C10、C00…）
    ents, names, kks_of, logic_of = all_entries(a.ge_tags)
    cura = load_curated(a.curated, log)
    lib = L.walk_pdfs(a.library)
    docs = {'wire': resolve_doc(lib, '%s-1-%s' % (WIRE_UNIT, WIRE_DOC)), 'wiregt': resolve_doc(lib, WIRE_GT_DOC),
            'jbloc': resolve_doc(lib, JBLOC_DOC), 'cab': resolve_doc(lib, CAB_DOC), 'cabgt': resolve_doc(lib, CAB_GT_DOC), 'conn': resolve_doc(lib, CONN_DOC),
            'gtjb': resolve_doc(lib, GTJB_DOC), 'csst': resolve_doc(lib, CS_DOCS['S10']), 'csgt': resolve_doc(lib, CS_DOCS['G11'])}
    for i, jd_ in enumerate(JBDOCS):
        docs['jd%d' % i] = resolve_doc(lib, jd_[0])
    for i, (u_, title_) in enumerate(MCC_DOCS):
        docs['mc%d' % i] = resolve_title(lib, title_)
    docs['genwd'] = resolve_doc(lib, GEN_WIRING['G11'])
    docs['vmsgt'] = resolve_doc(lib, VMS_GT_DOC)
    for dk, how, val in WE.doc_specs():   # v16：其餘電氣盤的配置圖（GPP、手動同步盤、GCB、UAT、LCI 中壓盤／52ET）
        docs[dk] = resolve_doc(lib, val) if how == 'docno' else WE.resolve_fragment(lib, val, L.copy_flags, L.rev_rank)
    docs['vms'] = resolve_vms(lib, a.library, a.text_cache)
    if kks:                               # v17：HRSG／電氣 I&C／BOP 接線圖、三份電纜表、一號機儀器與接線箱位置圖（IIF01）
        for kd_, dn_, _zh in WP.EPC_DOCS:
            docs[kd_] = resolve_doc(lib, dn_)
        for kd_, dn_ in WP.CS_DOCS:
            docs[kd_] = resolve_doc(lib, dn_)
        for kd_, dn_, _zh in WP.LOC_DOCS:
            docs.setdefault(kd_, resolve_doc(lib, dn_))
    for k, d in docs.items():
        log('%s：%s' % (k, d.get('rel') or d.get('why')))
    if not docs['wire'].get('rel'):
        sys.exit('找不到接線圖 %s-1-%s' % (WIRE_UNIT, WIRE_DOC))
    tx = {k: load_full_text(a.library, d, a.text_cache) for k, d in docs.items() if d.get('rel')}
    by_screw, by_dev = io_index(a.dcdas)
    boards = boards_index(a.dcdas)
    epc_ix = WP.io_index(a.dcdas) if kks else None   # v17：HRSG、BOP 的控制器（盤端子格沒有板名，鍵不含板名）
    if epc_ix:
        by_dev.update(epc_ix['by_dev'])
    # 組態裡「這個編號實際在哪顆螺絲」：圖面畫的螺絲在組態是別顆或備用點時，找出這個編號真正的點（先用字串粗篩，再用 io_rel 確認）
    where_idx = defaultdict(list)
    for (u_, cab_, pos_, board_, num_), hs_ in (by_screw or {}).items():
        for h_ in hs_:
            where_idx[u_].append(((ge_cmp(h_['dt']) + ' ' + ge_cmp(h_['var'])), (cab_, pos_, board_, num_), h_))
    for (ctl_, cab_, pos_, num_), hs_ in ((epc_ix or {}).get('by_pos') or {}).items():   # v17：鍵是控制器
        for h_ in hs_:
            where_idx[ctl_].append(((ge_cmp(h_['dt']) + ' ' + ge_cmp(h_['var'])), (cab_, pos_, h_['board'], num_), h_))

    def io_where(unit, e, kks):
        tc, kc = ge_cmp(e['tag']), kks_core(kks)[:10] if kks else ''
        found = defaultdict(list)
        for s_, key_, h_ in where_idx.get(unit, ()):
            if (len(tc) >= 3 and tc in s_) or (kc and kc in s_):
                if io_rel(h_, e, kks) in ('same', 'logic'):
                    found[(key_[0], key_[1], key_[2], h_['tb'])].append(key_[3])
        return ['%s %s%s 螺絲 %s（%s）' % ('%s-%s' % (k_[0], k_[1]) if k_[0] else k_[1], k_[2], ' ' + k_[3] if k_[3] else '', '／'.join(str(n) for n in sorted(set(v))),
                                       '、'.join(sorted({h_['pt'] for s_, key_, h_ in where_idx.get(unit, ()) if (key_[0], key_[1], key_[2], h_['tb']) == k_ and key_[3] in v})))
                for k_, v in sorted(found.items())][:4]
    if by_screw is None:
        log('（沒有 signal-atlas 索引：不核對 I/O 點，也不能由盤端子反查元件）')
    st = Counter()
    recs = defaultdict(list)      # GE 鍵 → [路徑…]（v14：一顆元件可以有好幾條路徑——兩台燃機、多組接點、電源＋訊號）
    jbs = {}                      # '機組|JB 名' → {unit, jb, kks, pages, strip}
    ffsegs = {}                   # (機組, 段名) → FF 段幹線（燃機圖的 'ff' 子圖）
    used_sheets = {}              # (文件別, 頁) → 'wire'／'loc'
    R_of = {}
    gtidx = defaultdict(dict)     # 機組 → {JB 短名: [(端子排, 端子, 頁, pg, R, 子圖, 群組序, 列)…]}（燃機圖）
    strip_ref = {}                # id(列) → (接線箱鍵, 端子排列表的列序)

    def page_R(kind, pno):
        pg = tx[kind]['pg'][pno - 1]
        if (kind, pno) not in R_of:
            info = L.upright_rotation_info(pg)
            R_of[(kind, pno)] = (info['R'] if info['R'] is not None else 0, info['method'] or 'default')
        return R_of[(kind, pno)]

    def io_keys(rows, unit, sysset):
        """盤端子 → 控制器 DeviceTag／變數 → GE 鍵（說明格沒有 GE 編號、也沒有 KKS 時的反查）：落在 Mark VIe 的芯有一半以上指到同一個鍵才算。"""
        votes, live = Counter(), 0
        for r in rows:
            c = r['term']
            if c['board'] not in MARKVIE_BOARDS or by_screw is None:
                continue
            live += 1
            hs, how = io_lookup(by_screw, unit, c)
            if how == 'tb_mismatch' or len({h['dt'] for h in hs}) != 1:      # 同一顆螺絲對到不只一個 DeviceTag（TCSA 兩排同號）就不拿來反查
                continue
            ks = set()
            for h in hs:
                for part in dt_parts(h['dt']):
                    for s in sysset:
                        ks |= (names.get(s) or {}).get(ge_cmp(part), set())
                        ks |= (kks_of.get(s) or {}).get(kks_core(part), set()) if kks_core(part) else set()
                ks |= {k for k in logic_of.get((h['ctrl'], (h['var'] or '').lower()), ()) if ents[k]['system'] in sysset}
            for k in ks:
                votes[k] += 1
        return {k: ('io', 0.0) for k, v in votes.items() if live and v * 2 >= live}

    def other_keys(kind):
        if kks:                                    # v17：DeviceTag 是另一個設備的 KKS → 那個設備
            return lambda x: {'KKS|%s' % d_ for d_ in [WP.dev_of(x)[0]] if d_}
        sysset = ('ST', 'ST-GEN') if kind == 'wire' else ('GT', 'GT-GEN')
        return lambda x: {k for s_ in sysset for k in (names.get(s_) or {}).get(ge_cmp(x), ())} | \
            ({k for s_ in sysset for k in (kks_of.get(s_) or {}).get(kks_core(x), ())} if kks_core(x) else set())

    def kks_ent(dev):
        """v17：設備 KKS → 鍵 'KKS|<KKS>'（條目照 all_entries 的欄位補一筆）。"""
        k = 'KKS|%s' % dev
        if k not in ents:
            ents[k] = {'tag': dev, 'system': 'KKS', 'kks': [dev], 'forms': [dev], 'logic': [], 'linked': [], 'tsi': 0}
        return k

    def kks_keys(kind, p, unit, sysset, keyrows, via_of):
        """v17：一個子圖 → 鍵 'KKS|<設備 KKS>' 的芯。HRSG／電氣 I&C／BOP 圖：每條芯所在訊號格的設備（wire_epc.row_signals）；
        燃機／汽機圖：說明格認得 GE 編號、或盤端子反查得到 GE 編號的框不收（那是 GE 編號卡的路徑），其餘框裡寫的 KKS（不帶機組碼的補上這一台的）。"""
        if kind not in ('wire', 'wiregt'):
            for r in p['rows']:
                if r.get('dev') and r.get('group') is not None:
                    k = kks_ent(r['dev'])
                    keyrows[k].append((r['group'], r))
                    via_of.setdefault(k, 'sig' if r.get('sig') else 'kks')
            return
        for gi, g in enumerate(p['groups']):
            rows = [r for r in p['rows'] if r.get('group') == gi]
            if not rows or identify(g, sysset, names, kks_of) or io_keys(rows, unit, sysset):
                continue
            devs = []
            for t, y in desc_tokens(g['desc_w']):
                d_ = WP.dev_of(t)[0] or (unit + t[:10] if KKS_BARE.match(t) else None)
                if d_ and d_[:3] == unit and not any(kks_core(d_) in (kks_of.get(s_) or {}) for s_ in kks_of) and (d_, y) not in devs:
                    devs.append((d_, y))
            if not devs:
                continue
            for r in rows:
                c_ = r.get('jb_cell') or r.get('field_cell') or {}
                ry_ = c_.get('y', r['core_w']['y0'] if r.get('core_w') else 0) + 4
                d_ = min(devs, key=lambda dv: abs(dv[1] - ry_))[0]
                k = kks_ent(d_)
                keyrows[k].append((gi, r))
                via_of.setdefault(k, 'kks')

    def add_path(kind, pno, pg, R, p, unit, k, grs, via):
        """一個子圖裡屬於鍵 k 的芯（grs＝[(群組序, 列)…]）→ 一條路徑（同機組、同一頁同一子圖已經有的就回那一條）。"""
        h = p['h']
        rows = [r for _gi, r in grs]
        pdesc = p['pdesc']
        if kks and kind in epc_kinds:             # v17：一頁好幾個接線箱／端子排／盤框時，取這條路徑第一條芯上面最近的那一組、盤端子所在的那一框
            h = dict(h)
            y1_ = min((r['core_w']['y0'] for r in rows if r.get('core_w')), default=None)
            for key_, cs_ in (p.get('hdr_cands') or {}).items():
                cs_ = [c_ for c_ in cs_ if c_[1]]
                up_ = [c_ for c_ in cs_ if y1_ is not None and c_[0] < y1_ + 2]
                if key_ in ('jb', 'jb_tb') and len(cs_) > 1 and up_:
                    h[key_] = max(up_)[1]
            pb_ = Counter(r.get('pbox') for r in rows if r.get('pbox') is not None)
            blk_ = (p.get('panels') or {}).get(pb_.most_common(1)[0][0]) if pb_ else None
            if blk_:
                pdesc = blk_['desc']
                h['panel'] = blk_['kks'] or h.get('panel', '')
        jb_name = h.get('jb', '') if p['mode'] != 'direct' else ''
        jbk = re.search(KP, jb_name)
        pk = re.findall(KP, (h.get('panel') or '') + ' ' + (pdesc or ''))
        e = ents[k]
        gis = sorted({gi for gi, _r in grs})
        g = p['groups'][gis[0]]
        tr = p['trunks'][rows[0]['trunk']] if p['trunks'] and rows[0].get('trunk') is not None else None
        cond = []
        for r in rows:
            c = dict(r['term'])
            c.update({'core': r['core'], 'field': ctext(r.get('field_cell')), 'field_core': r.get('field_core', ''), 'jb_in': r.get('jb_in', ''),
                      'jb': ctext(r.get('jb_cell'))})
            if r.get('ptypo'):
                c['ptypo'] = r['ptypo']
            if r.get('sig'):
                c['sig'] = r['sig']                    # v17：這條芯所在訊號格的訊號 KKS（HRSG／BOP 圖）
            cond.append(c)
        dev_ws = [w for gi in gis for w in p['groups'][gi]['desc_w']]
        jb_ws = [w for r in rows for w in ((r.get('jb_cell') or {}).get('w') or [])]
        pn_ws = [w for r in rows for w in ((r.get('panel_cell') or {}).get('w') or [])]
        marks = []
        for ws_ in (jb_ws or ([w for r in rows for w in ((r.get('field_cell') or {}).get('w') or [])]), pn_ws, dev_ws):
            if ws_:
                marks.append(mark_of(pg, R, ubox(ws_)))
        epc_ = kks and kind in epc_kinds
        drawn_ = ' / '.join(p['groups'][gi]['desc'] for gi in gis)
        if epc_:                                  # v17：只收這幾條芯所在的訊號格（加它們上面的標頭行），不收同一群組裡別的設備的格子
            hl_ = [r['hdr'][2] for r in rows if r.get('hdr') and r['hdr'][2]]
            bx_ = [r['sbox'] for r in rows if r.get('sbox')]
            drawn_ = ' / '.join(dict.fromkeys([h_ for h_ in hl_ if not any(h_ in b_ for b_ in bx_)] + bx_)) or drawn_
        path = {
            'unit': unit, 'tag': e['tag'], 'kks': kks_for(e, unit), 'mode': p['mode'], 'via': via, 'doc': kind,
            'wire': {'page': pno, 'sheet': p['sheet'], 'of': p['of'], 'drawn': drawn_, 'marks': marks,
                     'field_cable': g['cable'], 'field_spec': g['spec'], 'field_tb': h.get('field_tb', ''),
                     'jb': jb_name, 'jb_kks': jbk.group(0) if jbk else '', 'jb_desc': h.get('jb_desc', ''), 'jb_tb': h.get('jb_tb', ''),
                     'prox': rows[0].get('prox', ''), 'trunk': tr['cable'] if tr else '', 'trunk_spec': tr['spec'] if tr else '',
                     'panel': h.get('panel', ''), 'panel_tb': h.get('panel_tb', ''), 'panel_desc': pdesc},
            'cond': cond, 'flags': list(p['flags']), 'notes': []}
        if kks and kind in epc_kinds:             # v17：一頁的旗標（label_typo:WH-1→…、panel_nolabel:BK-11）只留這條路徑自己的芯
            mine_ = {r['core'] for r in rows}
            path['flags'] = [f_ for f_ in path['flags'] if ':' not in f_ or re.split(r'[:→]', f_)[1] in mine_]
            pkk_ = re.search(r'[A-Z]?\d{2}C[A-Z]{2}\d{2}UC\d{3,4}', h.get('panel') or '')
            if pkk_ and pkk_.group(0) != h.get('panel'):
                path['wire']['panel'] = pkk_.group(0)   # 'BOPE1_CNTRL/ C10CCF01UC006' → 盤 KKS（盤名在盤欄說明裡）
        if p.get('sub'):
            path['wire']['sub'] = p['sub']
        if kks:                                   # v17：元件說明（框標頭 KKS 後面的字，沒有就用第一個訊號格的說明）給 KKS 編號卡
            path['dsc'] = next((r['hdr'][1] for r in rows if r.get('hdr') and r['hdr'][0] == e['tag'] and r['hdr'][1]), '') if epc_ else \
                next((p['groups'][gi].get('hdr_desc') for gi in gis if p['groups'][gi].get('hdr_desc') and p['groups'][gi].get('hdr_dev') == e['tag']), '')
            path['dsc'] = path['dsc'] or WP.device_desc([r.get('sbox') or r.get('sdesc') or '' for r in rows])
        hd_ = sorted(({r['hdr'][0] for r in rows if r.get('hdr')} if epc_ else {p['groups'][gi].get('hdr_dev') for gi in gis}) - {None, '', e['tag']})
        if kks and hd_:                           # v17：元件框的標頭與訊號格寫的設備不同（D1003 p.15：標頭 C10LAF31QM004、訊號格 =G11HAC31QM506XB61）
            fc_ = re.match(r'^([A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})-W', g['cable'] or '')
            ev_ = '；這一條的現場電纜號 %s 的前綴也是 %s' % (g['cable'], fc_.group(1)) if fc_ and fc_.group(1) in hd_ else ''
            path['notes'].append(['接線圖這一框的標頭寫 %s，這幾條芯所在的訊號格寫 %s：兩者不一致%s。路徑先照訊號格歸（標頭可能是所屬的主設備，'
                                  '也可能是圖面複製時沒改），請以現場標示確認' % ('、'.join(hd_), e['tag'], ev_), '接線圖 第 %d 頁（文字層）' % pno])
        if epc_:
            fcs_ = list(dict.fromkeys((p['groups'][gi]['cable'], p['groups'][gi]['spec']) for gi in sorted({r['group'] for r in rows if r.get('group') is not None})
                                      if p['groups'][gi]['cable']))
            if len(fcs_) > 1:                     # v17：一個設備的訊號分走幾條現場電纜（G12LBA10FL002 p.178：XG02、XB61、XB62 各一條 1P）
                path['wire']['field_cables'] = [list(x) for x in fcs_]
            trs_ = list(dict.fromkeys((p['trunks'][r['trunk']]['cable'], p['trunks'][r['trunk']]['spec']) for r in rows
                                      if p['trunks'] and r.get('trunk') is not None))
            if len(trs_) > 1:                     # 也分走幾條幹線（C10MAJ30QM003 p.375：XG02 在 WG-003、XB61 在 WD-004）
                path['wire']['trunks'] = [list(x) for x in trs_]
            ss_ = p.get('sensors') or []
            devs_ = {r.get('dev') for r in rows} - {None}
            s_ = next((x for x in ss_ if x['tt'] in devs_ or x['te'].split('_')[0] in devs_), None)
            pos_ = False
            if not s_ and len(ss_) == 1 and len({r.get('dev') for r in p['rows'] if r.get('dev')}) == 1:
                s_, pos_ = ss_[0], True           # 同一頁只有一組：照位置配（上下段寫的 KKS 不一致，D1003 p.917）
            if s_:
                path['wire']['sensor'] = dict({k_: s_[k_] for k_ in ('te', 'te_desc', 'cable', 'spec', 'tt', 'tt_desc', 'cond')}, **({'by': 'pos'} if pos_ else {}))
                path['wire']['marks'].append(mark_of(pg, R, s_['box']))
                if pos_:
                    path['notes'].append(['接線圖上段（熱電偶 → 傳送器）寫 %s，下段（傳送器 → 盤）的訊號格寫 %s：同一頁只有這一組，照位置接在一起；'
                                          '兩段的 KKS 不一致（圖面筆誤或編號改過），請以現場銘牌確認' % (s_['tt'] or s_['te'], e['tag']), '接線圖 第 %d 頁（文字層）' % pno])
                elif s_['tt'] and s_['tt'] != e['tag']:   # 上段傳送器框寫的 KKS 與熱電偶、下段不同（D1003 p.671、p.698）
                    path['notes'].append(['接線圖上段的傳送器框寫 %s，同一組的熱電偶（%s）與下段訊號格寫 %s：兩者不一致，請以現場銘牌確認'
                                          % (s_['tt'], s_['te'] or '—', e['tag']), '接線圖 第 %d 頁（文字層）' % pno])
            pnk_ = [x for x in dict.fromkeys(re.findall(r'[A-Z]?\d{2}C[A-Z]{2}\d{2}UC\d{3,4}', p['pdesc'] or ''))]
            if not p.get('panels') and p['h'].get('panel') and pnk_ and re.match(r'[A-Z]?\d{2}C[A-Z]{2}\d{2}UC\d{3,4}$', p['h']['panel']) \
                    and p['h']['panel'] not in pnk_:     # 只有一個盤框時，標頭與框裡寫的不同：盤取框裡寫的（電纜表與控制器組態都照框），註記兩者
                path['wire']['panel'] = pnk_[0]
                path['notes'].append(['接線圖盤欄的標頭寫 PANEL: %s，盤框裡的說明寫 %s：兩者不一致（路徑照盤框），請以現場盤名確認' % (p['h']['panel'], p['pdesc']),
                                      '接線圖 第 %d 頁（文字層）' % pno])
        sd_ = sorted({r.get('sigdev') for r in rows if r.get('sigdev')})
        if kks and sd_:
            path['notes'].append(['這幾條芯所在的訊號格寫 %s，但這一框的標頭與現場電纜號都寫 %s：路徑照標頭與電纜號（訊號格多半是複製時沒改），請以現場標示確認'
                                  % ('、'.join(sd_), e['tag']), '接線圖 第 %d 頁（文字層）' % pno])
        dc_ = p.get('dup_cells') or {}
        dd_ = sorted({k_ for r in rows for k_ in [re.sub(r'\s+', '', ctext(r.get('panel_cell')))] if k_ in dc_})
        if kks and dd_:
            path['notes'].append(['接線圖把同一顆盤端子畫給兩條芯：%s——圖面筆誤或其中一個接法沒畫對，請以現場核對'
                                  % '；'.join('%s（%s）' % (k_, '、'.join(dc_[k_])) for k_ in dd_), '接線圖 第 %d 頁（文字層）' % pno])
        if kks and kind in ('wire', 'wiregt'):   # v17：燃機／汽機圖上只有 KKS 的框：訊號格寫的是不帶機組碼的 'MAL40QM001-BG01'、'MAX31GP004_AVAIL'
            body_ = e['tag'][3:]
            tk_ = [(t_, y_) for gi in gis for t_, y_ in desc_tokens(p['groups'][gi]['desc_w'])
                   if re.fullmatch(r'(?:[A-Z]\d{2})?%s[-_][A-Z0-9]{2,8}' % body_, t_)]
            if tk_:
                for c_, r_ in zip(cond, rows):
                    c0_ = r_.get('jb_cell') or r_.get('field_cell') or {}
                    ry_ = c0_.get('y', r_['core_w']['y0'] if r_.get('core_w') else 0)
                    t_ = min(tk_, key=lambda x: abs(x[1] - ry_))[0]
                    c_.setdefault('sig', t_ if re.match(r'[A-Z]\d{2}%s' % body_, t_) else unit + t_)
        dk = sorted({kks_core(t) for gi in gis for t, _y in desc_tokens(p['groups'][gi]['desc_w']) if (KKS_ANY.match(t) or KKS_BARE.match(t) or (kks and WP.dev_of(t)[0])) and kks_core(t)})
        if dk:
            path['dkks'] = dk                    # 圖上寫在元件旁的 KKS（本體）：核對螺絲時當作同一設備的證據
        w = path['wire']
        # 自動註記（v13）：幹線電纜號的前綴不是這個 JB 的 KKS；JB 端子格印的名字與前置器區塊不同（圖面筆誤）
        tpre = w['trunk'].split('-WG')[0]                # 'S10BPA10-WG-001' 是系統層的電纜號（JB S10BPA10UC101 的系統碼），不算另一個 KKS
        if w['trunk'] and w['jb_kks'] and not w['trunk'].startswith(w['jb_kks']) and not any(w['trunk'].startswith(x) for x in pk) and \
                not w['jb_kks'].startswith(tpre) and not (kks and w['trunk'].startswith(e['tag'])):
            tp = re.match(r'^([SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})', w['trunk'])
            path['notes'].append([('幹線電纜號 %s 的前綴是另一個 KKS（%s），接線圖這一框的接線箱寫 %s：兩者不一致（可能另經一個接線箱，也可能是其中一個編號寫錯），'
                                   '請以現場電纜標示確認' if kks else
                                   '幹線電纜號 %s 的前綴是另一個 KKS（%s），不是這個接線箱（%s）也不是盤：電纜的這一端可能另經一個接線箱，'
                                   '請以現場電纜標示確認') % (w['trunk'], tp.group(1) if tp else tpre, w['jb_kks']), '接線圖 第 %d 頁' % pno])
        prox = w['prox']
        cells = [c2 for r in rows for c2 in [r.get('jb_cell') or {}] if len(c2.get('lines') or []) > 1]
        odd = [c2['t'] for c2 in cells if prox and c2['lines'][0] != prox]
        if odd and len(odd) == len(cells):
            by = {}
            for c2 in cells:
                by.setdefault(c2['lines'][0], []).append(' '.join(c2['lines'][1:]))
            nm = '、'.join(n if len(by) == 1 else '%s（%s）' % (n, '／'.join(v)) for n, v in by.items())
            path['notes'].append(['圖上這一組端子格印的是 %s，不是前置器 %s（以端子格所在的區塊為準）' % (nm, prox), '接線圖 第 %d 頁' % pno])
        elif odd:
            path['notes'].append(['圖上「%s」這一格印的名字不是前置器 %s（圖面筆誤；以端子格所在的區塊為準，同組其他格印 %s）'
                                  % ('、'.join(odd), prox, prox), '接線圖 第 %d 頁' % pno])
        # v14 自動註記：芯色標籤 JB 側與盤側不同（照順序配）；盤端子板名筆誤
        ty = ['%s（盤側印 %s）' % (c['core'], c['ptypo']) for c in cond if c.get('ptypo')]
        if ty:
            path['notes'].append(['圖上芯色標籤兩端不一致：%s——照%s裡的上下順序對到盤端子（多半是圖面筆誤，沒有逐一查證）' % ('、'.join(ty), '電纜' if p['mode'] == 'direct' else '幹線')
                                  if kks else '圖上芯色標籤兩端不一致：%s——照幹線裡的上下順序對到盤端子（圖面筆誤）' % '、'.join(ty), '接線圖 第 %d 頁' % pno])
        fx = sorted({c['fix'] for c in cond if c.get('fix') and c['fix'] not in ('hdr_tb', 'hdr_board')})
        if fx:
            path['notes'].append(['盤端子格把板名寫成 %s，就是 TDBT（圖面筆誤）' % '、'.join(fx), '接線圖 第 %d 頁' % pno])
        if kind == 'wiregt':
            path['_terms'] = {(WG.jb_short(h.get('jb', '')).upper(),) + WG.term_key(((r.get('jb_cell') or r.get('field_cell') or {}).get('t', '')), h.get('jb_tb', ''))
                              for r in rows}
        old = [x for x in recs[k] if x['unit'] == unit and x['doc'] == kind and x['wire']['page'] == pno and x['wire'].get('sub', 0) == p.get('sub', 0)]
        if old:
            return old[0]
        recs[k].append(path)
        used_sheets[(kind, pno)] = 'wire'
        return path

    # ---- 1. 接線圖：汽機 D1005（parse_page）與燃機 D1004（wire_gt.parse_page，一頁可有幾個子圖）；v17 KKS 版另加 HRSG／電氣 I&C／BOP（wire_epc）
    wkinds = [('wire', ('ST', 'ST-GEN'), 'S'), ('wiregt', ('GT', 'GT-GEN'), 'G')] + ([(kd_, (), '') for kd_, _dn, _zh in WP.EPC_DOCS] if kks else [])
    for kind, sysset, ufam in wkinds:
        if kind not in tx:
            continue
        d = docs[kind]
        frames = WG.load_frames(os.path.join(a.library, d['rel'].replace('/', os.sep)), d['rel'], d['size'], d['mtime'], a.text_cache,
                                range(1, tx[kind]['pages'] + 1)) if kind == 'wiregt' or kind in epc_kinds else None   # v17：HRSG／BOP 圖用框線切訊號格
        for pno, pg in enumerate(tx[kind]['pg'], 1):
            if kind == 'wire':
                p = parse_page(pg)
                subs = [dict(p, unit=SITE_UNIT, sub=0)] if p and p['rows'] else []
            elif kind == 'wiregt':
                subs = WG.parse_page(disp_words(pg), frames[pno])
                for s_ in subs:
                    st['gt_sub_' + (s_.get('mode') or 'none')] += 1
                    if not s_.get('mode'):
                        st['gt_flag_' + (s_['flags'] or ['?'])[0]] += 1
                subs = [s_ for s_ in subs if s_.get('rows') and s_.get('mode') not in ('', 'link')]
            else:                                   # v17：HRSG／電氣 I&C／BOP（wire_epc；機組看每條芯的設備 KKS）
                p = WP.parse_page(pg, frames[pno] if frames else None)
                subs = [dict(p, unit='', sub=0)] if p and p['rows'] else []
            for p in subs:
                unit = p.get('unit') or ''
                if ufam and (unit not in SITE_UNITS or unit[0] != ufam):
                    st['%s_other_unit' % kind] += 1
                    continue
                st['%s_subs' % kind] += 1
                R, _method = page_R(kind, pno)
                h = p['h']
                for r in p['rows']:
                    r['term'] = term_parts(r['panel_cell']['lines'] if r.get('panel_cell') else [], h.get('panel_tb', ''))
                jb_name = h.get('jb', '') if p['mode'] != 'direct' else ''
                jbk = re.search(KP, jb_name)
                pk = re.findall(KP, (h.get('panel') or '') + ' ' + (p['pdesc'] or ''))
                # FF 段（燃機圖）：不是元件；記下段的幹線，FF 元件的路徑由 GE 的 H1 元件報告接上（ff_paths）
                if p['mode'] == 'ff':
                    for gi, g in enumerate(p['groups']):
                        m = re.search(r'\((FBSP-[A-Z]+-\d+|11DT-\d)\)', g['desc']) or re.search(r'(FBSP-[A-Z]+-\d+)', g['desc'])
                        if m:
                            rows = [r for r in p['rows'] if r.get('group') == gi]
                            ffsegs[(unit, m.group(1))] = {'page': pno, 'kind': kind, 'sub': p['sub'], 'p': p, 'rows': rows, 'g': g, 'R': R}
                # 元件身分：說明格的 GE 編號（或 KKS）；都沒有就由盤端子反查控制器
                keyrows = defaultdict(list)
                via_of = {}
                if kks:                              # v17：KKS 版的身分（kks_keys）；GE 編號的框不收
                    kks_keys(kind, p, unit, sysset, keyrows, via_of)
                for gi, g in enumerate(p['groups'] if not kks else ()):
                    rows = [r for r in p['rows'] if r.get('group') == gi]
                    if not rows:
                        st['group_without_rows'] += 1
                        continue
                    ids = identify(g, sysset, names, kks_of) or io_keys(rows, unit, sysset)
                    if not ids:
                        st['group_unidentified'] += 1
                        continue
                    # 一個說明格寫了好幾個元件（'TE-203A/B/C'、同一條電纜的幾組接點）：落在 Mark VIe 的芯，組態的 DeviceTag 指到其中哪一顆就歸那一顆；
                    # 組態沒說的芯，汽機圖歸給說明文字最近的那一個、燃機圖（一個元件框）歸給全部
                    owner = {}
                    if len(ids) > 1 and by_screw is not None and not any(ents[k]['tsi'] for k in ids):
                        for r in rows:
                            if r['term']['board'] not in MARKVIE_BOARDS:
                                continue
                            hs, _how = io_lookup(by_screw, unit, r['term'])
                            ok = {k for k in ids for h in hs if io_rel(h, ents[k], kks_for(ents[k], unit)) in ('same', 'logic')}
                            if len(ok) == 1:
                                owner[id(r)] = ok.pop()
                    lone = [k for k in ids if k not in set(owner.values())]
                    if owner and len(lone) == 1:                  # 只剩一顆沒分到芯（對照表的 KKS 寫錯、組態認不出它：TE-205C）→ 沒有歸屬的芯都給它
                        for r in rows:
                            owner.setdefault(id(r), lone[0])
                    ys = sorted({round(v[1]) for v in ids.values()})
                    split = kind == 'wire' and len(ids) > 1 and len(ys) > 1 and ys[-1] - ys[0] > 8 and not any(ents[k]['tsi'] for k in ids)

                    def ry(r):
                        c = r.get('jb_cell') or r.get('field_cell') or {}
                        return c.get('y', r['core_w']['y0'] if r.get('core_w') else 0) + 4
                    def same_dev(a, b):                          # 對照表同一顆有兩筆：寫法去符號相同（TE-243-E1／TE-243E-1）或 KKS 相同（96FM-4／96FM-4(TCP)）
                        if ge_cmp(ents[a]['tag']) == ge_cmp(ents[b]['tag']):
                            return True
                        ka = {kks_core(x) for x in ents[a]['kks']} - {''}
                        return bool(ka & ({kks_core(x) for x in ents[b]['kks']} - {''}))
                    for k, (via, y) in sorted(ids.items()):
                        mine = [r for r in rows if owner.get(id(r), k) == k or same_dev(owner[id(r)], k)]
                        if split:
                            mine = [r for r in mine if id(r) in owner or min(ids.items(), key=lambda kv: abs(kv[1][1] - ry(r)))[0] == k]
                        if mine:
                            keyrows[k] += [(gi, r) for r in mine]
                            via_of.setdefault(k, via)
                for k, grs in keyrows.items():
                    add_path(kind, pno, pg, R, p, unit or ents[k]['tag'][:3], k, grs, via_of[k])
                # 燃機：每一條芯的 JB 端子（GE 138T5502 以 JB／端子排／端子接上來）
                if kind == 'wiregt' and p['mode'] in ('jbdev', 'direct'):
                    jn = WG.jb_short(h.get('jb', '')).upper()
                    for r in p['rows']:
                        cell = r.get('jb_cell') or r.get('field_cell')
                        if cell and r.get('group') is not None:
                            tb_, term_ = WG.term_key(cell['t'], h.get('jb_tb', ''))
                            gtidx[unit].setdefault(jn, []).append((tb_, term_, pno, pg, R, p, r['group'], r))
                # 接線箱端子排（這個子圖的每一條芯，不論認不認得元件）：「接線箱內 TB 接法」
                if jb_name:
                    ju = unit or (jbk.group(0)[:3] if jbk else '')    # v17：HRSG／BOP 圖的 JB 看箱子 KKS 的機組碼
                    jk = '%s|%s' % (ju, jb_name)
                    jb = jbs.setdefault(jk, {'unit': ju, 'jb': jb_name, 'kks': jbk.group(0) if jbk else '', 'desc': h.get('jb_desc', ''), 'pages': [], 'strip': []})
                    if pno not in jb['pages']:
                        jb['pages'].append(pno)
                    key_of_row = {id(r): k for k, grs in keyrows.items() for _gi, r in grs}
                    for r in p['rows']:
                        k = key_of_row.get(id(r), '')
                        g = p['groups'][r['group']] if r.get('group') is not None else None
                        lab = ents[k]['tag'] if k else (re.sub(r'\s+', ' ', g['desc'])[:60] if g else '')
                        c = r['term']
                        tr = p['trunks'][r['trunk']]['cable'] if p['trunks'] and r.get('trunk') is not None else ''
                        strip_ref[id(r)] = (jk, len(jb['strip']))
                        jb['strip'].append([ctext(r.get('jb_cell')), r['core'], lab, ' '.join(x for x in (c['pos'], c['board'], c['tb'], c['num']) if x),
                                            tr, r.get('jb_in', ''), ctext(r.get('field_cell')), k])
    # ---- 1b. 燃機元件 → 撬上 JB 端子：GE 138T5502（Turbine Connection Diagram，Rev M AS-BUILT）一芯一列，以（JB, 端子排, 端子）接上 D1004 的 JB 端子格。
    #      說明格有寫這顆的路徑多一跳「元件端子 → JB 端子」；說明格寫的是整區（'(45FT-1A/2A/3A/4A)'）或別名的，靠端子號接上另開一條（via 'conn'）。
    #      FF 元件（JB 欄是 FBSP-GT-n 段保護器）：接上燃機圖的 FF 段幹線（'ff' 子圖）→ FFPCn Sm，控制器以 FF_IN_S(8(n−1)+m) 核對。
    conn_rows, conn_st = [], Counter()
    if 'conn' in tx and not kks:
        conn_rows = WG.parse_conn(os.path.join(a.library, docs['conn']['rel'].replace('/', os.sep)))
        bykey = defaultdict(list)
        for cr in conn_rows:
            for k in sorted({k for s_ in ('GT', 'GT-GEN') for k in (names.get(s_) or {}).get(ge_cmp(cr['ge']), ())}):
                bykey[k].append(cr)
        conn_st['rows'], conn_st['keys'] = len(conn_rows), len(bykey)
        for k, crs in sorted(bykey.items()):
            hw = [cr for cr in crs if not (cr.get('jb') or '').startswith('FBSP-')]
            ffr = [cr for cr in crs if (cr.get('jb') or '').startswith('FBSP-')]
            for unit in ('G11', 'G12'):
                hits, ctx, used_cr = defaultdict(list), {}, defaultdict(list)
                for cr in hw:
                    jtb = cr.get('jb_tb') or ''
                    tb5, t5 = WG.term_key(('%s %s' % (jtb, cr.get('jb_term') or '')) if re.fullmatch(r'TB[A-Z0-9]*', jtb) else (cr.get('jb_term') or ''))
                    for jn, lst in gtidx[unit].items():
                        if not WG.jb_same(jn, cr.get('jb') or ''):
                            continue
                        for tb_, term_, pno, pg, R, p, gi, r in lst:
                            if term_ == t5 and (not tb_ or not tb5 or tb_ == tb5):
                                kk = (pno, p.get('sub', 0))
                                if (gi, r) not in hits[kk]:
                                    hits[kk].append((gi, r))
                                ctx[kk] = (pno, pg, R, p)
                                if cr not in used_cr[kk]:
                                    used_cr[kk].append(cr)
                def tkey(r):
                    c_ = r.get('jb_cell') or r.get('field_cell') or {}
                    return WG.term_key(c_.get('t', ''), ctx_h.get('jb_tb', ''))
                out_brd = ('STAO', 'TBAO')
                order = sorted(hits.items(), key=lambda it: (any(r['term']['board'] in out_brd for _gi, r in it[1]), it[0]))
                for kk, grs in order:
                    pno, pg, R, p = ctx[kk]
                    ctx_h = p['h']
                    terms = {(WG.jb_short(p['h'].get('jb', '')).upper(),) + tkey(r) for _gi, r in grs}
                    prev = [x for x in recs[k] if x['unit'] == unit and x.get('_terms') and terms <= x['_terms'] and
                            (x['wire']['page'], x['wire'].get('sub', 0)) != kk]
                    if prev:
                        cells = '、'.join(sorted({' '.join(t[1:]) for t in terms}))
                        dest = '、'.join(sorted({' '.join(x for x in (r['term']['pos'], r['term']['board'], r['term']['tb'], r['term']['num']) if x) for _gi, r in grs} - {''}))
                        for x in prev:
                            x['notes'].append(['接線圖另一頁（第 %d 頁「%s」）把這顆的同一組接線箱端子（%s）畫到 %s：同一組端子有兩個去處，兩頁互相矛盾，請以現場核對'
                                               % (pno, re.sub(r'\s+', ' ', ' / '.join(p['groups'][gi]['desc'] for gi in sorted({gi for gi, _r in grs})))[:80], cells, dest),
                                               '接線圖 第 %d 頁、第 %d 頁' % (x['wire']['page'], pno)])
                        conn_st['joined_dup_note'] += 1
                        continue
                    n0 = len(recs[k])
                    path = add_path('wiregt', pno, pg, R, p, unit, k, grs, 'conn')
                    path['_terms'] = path.get('_terms', set()) | terms
                    conn_st['joined_new' if len(recs[k]) > n0 else 'joined_existing'] += 1
                    for r in [r for _gi, r in grs]:
                        if id(r) in strip_ref:
                            jk, ix = strip_ref[id(r)]
                            if not jbs[jk]['strip'][ix][7]:
                                jbs[jk]['strip'][ix][2], jbs[jk]['strip'][ix][7] = ents[k]['tag'], k
                    path['field'] = [[cr.get('devterm', ''), (cr.get('wire') or '').rpartition('/')[2], cr.get('cable', ''),
                                      ' '.join(x for x in (cr.get('ijb', ''), cr.get('ijb_tb', ''), cr.get('ijb_term', '')) if x and x not in ('N/A', '-')),
                                      cr.get('jb', ''), ' '.join(x for x in (cr.get('jb_tb', ''), cr.get('jb_term', '')) if x and x != 'N/A'), cr.get('jb_loc', ''),
                                      cr.get('rev', '')] for cr in hw if any(WG.jb_same(t[0], cr.get('jb') or '') for t in terms)]
                    path['conn'] = [[cr['_p'], cr['_box']] for cr in hw if any(WG.jb_same(t[0], cr.get('jb') or '') for t in terms)]
                if hw and not hits:
                    conn_st['hw_unjoined'] += 1
                    # v16：GE 表落在箱內中間設備的進線端（96KP 電荷放大器 5／8、前置器），接線圖的 JB 端子格是它的出線端（09／12、-24VDC）——端子號接不上，
                    #      改以「接線箱＋這個編號」接到這一台唯一的那條路徑：現場那一跳照 GE 表列，中間設備本身見 wire_curated.json 的 mid
                    dev = [cr for cr in hw if DEV_TB_RE.search(cr.get('jb_tb') or '')]
                    tg = [x for x in recs.get(k, []) if x['unit'] == unit and not x.get('field') and dev and WG.jb_same(x['wire']['jb'], dev[0].get('jb') or '')]
                    if len(tg) == 1:
                        rows_ = [cr for cr in hw if WG.jb_same(tg[0]['wire']['jb'], cr.get('jb') or '')]
                        tg[0]['field'] = [[cr.get('devterm', ''), (cr.get('wire') or '').rpartition('/')[2], cr.get('cable', ''),
                                           ' '.join(x for x in (cr.get('ijb', ''), cr.get('ijb_tb', ''), cr.get('ijb_term', '')) if x and x not in ('N/A', '-')),
                                           cr.get('jb', ''), ' '.join(x for x in (cr.get('jb_tb', ''), cr.get('jb_term', '')) if x and x != 'N/A'), cr.get('jb_loc', ''),
                                           cr.get('rev', '')] for cr in rows_]
                        tg[0]['conn'] = [[cr['_p'], cr['_box']] for cr in rows_]
                        conn_st['joined_dev'] += 1
                if ffr:
                    seg = ffr[0]['jb']
                    fs = ffsegs.get((unit, seg))
                    if not fs:
                        conn_st['ff_no_segment'] += 1
                        continue
                    grs = [(r['group'], r) for r in fs['rows']]
                    path = add_path('wiregt', fs['page'], tx['wiregt']['pg'][fs['page'] - 1], fs['R'], fs['p'], unit, k, grs, 'conn')
                    conn_st['ff_paths'] += 1
                    dev = next((cr.get('ijb') for cr in ffr if cr.get('ijb') not in (None, '', 'N/A', '-')), '')
                    path['ff'] = {'seg': seg, 'port': ffr[0].get('jb_tb', ''), 'loc': ffr[0].get('jb_loc', ''), 'dev': dev,
                                  'members': sorted({ents[k2]['tag'] for k2, crs2 in bykey.items() for cr2 in crs2 if cr2.get('jb') == seg})}
                    path['field'] = [[cr.get('devterm', ''), (cr.get('wire') or '').rpartition('/')[2], cr.get('cable', ''),
                                      ' '.join(x for x in (cr.get('ijb', ''), cr.get('ijb_tb', ''), cr.get('ijb_term', '')) if x and x not in ('N/A', '-')),
                                      cr.get('jb', ''), ' '.join(x for x in (cr.get('jb_tb', ''), cr.get('jb_term', '')) if x and x != 'N/A'), cr.get('jb_loc', ''),
                                      cr.get('rev', '')] for cr in ffr]
                    path['conn'] = [[cr['_p'], cr['_box']] for cr in ffr]
        seg_members = defaultdict(set)
        for k2, crs2 in bykey.items():
            for cr2 in crs2:
                if (cr2.get('jb') or '').startswith('FBSP-'):
                    seg_members[cr2['jb']].add(ents[k2]['tag'])
        for k2, plist in recs.items():                     # 段保護器本身的路徑（說明格寫 '(FBSP-GT-16)'）：列同一段的元件
            if ents[k2]['tag'].startswith('FBSP-'):
                for r in plist:
                    if r['mode'] == 'ff' and ents[k2]['tag'] in seg_members:
                        r['ff'] = {'members': sorted(seg_members[ents[k2]['tag']]), 'self': 1}
        log('GE 138T5502：%d 列、%d 個 GE 編號；%s' % (len(conn_rows), len(bykey), dict(conn_st)))
    # ---- 1c. 接線圖誤印、改掛到正確編號（v16，wire_curated.json 的 rekey）：D1004 p.257 JB-5D TBC 15／16 那一格寫「(39VE-1R)」，
    #      GE 發電機接線圖 p.9 是 39VE-13R——那一頁的路徑搬到 39VE-13R（註記跟著搬），39VE-1R 只留自己 p.256 那一條
    for rk in (cura.get('rekey') or []) if not kks else []:
        if rk['from'] not in recs or rk['to'] not in ents:
            continue
        mv_ = [r for r in recs[rk['from']] if r['wire']['page'] in rk['pages']]
        if not mv_:
            continue
        recs[rk['from']] = [r for r in recs[rk['from']] if r['wire']['page'] not in rk['pages']]
        if not recs[rk['from']]:
            del recs[rk['from']]
        e2 = ents[rk['to']]
        for r in mv_:
            r['tag'], r['kks'] = e2['tag'], kks_for(e2, r['unit'])
            r['notes'].append(list(rk['note']))
            recs[rk['to']].append(r)
            st['rekeyed'] += 1
    log('接線圖：汽機 %d 個子圖、燃機 %d 個子圖；有路徑的%s %d（TSI %d／%d）' % (
        st['wire_subs'], st['wiregt_subs'], ' KKS 元件' if kks else ' GE 編號', len(recs), sum(1 for k in recs if ents[k]['tsi']), sum(1 for e in ents.values() if e['tsi'])))
    if kks:   # v17：溫度兩段頁上段（熱電偶、傳送器框）寫的 KKS 與下段訊號格不同（D1003 p.916 C00LBG40BT411 ↔ C00LBG30BT411）：兩個編號都列這條路徑
        for k in list(recs):
            for r in list(recs[k]):
                sn_ = r['wire'].get('sensor') or {}
                alt_ = sn_.get('tt') or ''
                # 只在照位置配（上段與下段寫的不同）、而且上段的熱電偶與傳送器框寫同一個 KKS 時才另列；上段傳送器框自己寫錯的（p.698
                # C10MAG10BT004_TE → 'C10LBH30BT402'）不列
                if sn_.get('by') != 'pos' or not re.fullmatch(r'[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}', alt_) or alt_ == r['tag'] \
                        or (sn_.get('te') or '').split('_')[0] != alt_:
                    continue
                k2 = kks_ent(alt_)
                if any(x['doc'] == r['doc'] and x['wire']['page'] == r['wire']['page'] for x in recs.get(k2, [])):
                    continue
                other_ = sorted({x['wire']['page'] for x in recs[k] if x is not r})
                r2 = copy.deepcopy(r)
                r2.update(tag=alt_, kks=alt_, via='sensor')
                r2['notes'] = [n_ for n_ in r2['notes'] if not n_[0].startswith('接線圖上段（熱電偶 → 傳送器）寫')]
                if other_ and (r['wire']['field_cable'] or '').startswith(alt_ + '-W'):
                    # 下段訊號格寫的設備另有自己的路徑（p.912），這一頁的熱電偶、傳送器框、電纜號都寫 alt_：這一頁只列在 alt_ 底下
                    r2['notes'].insert(0, ['接線圖這一頁下段的訊號格寫 %s，但上段的熱電偶、傳送器框與這一段的電纜號 %s 都寫 %s；%s 另有自己的接線路徑'
                                           '（接線圖 第 %s 頁）：這一頁的訊號格多半是複製時沒改，路徑列在 %s，請以現場銘牌確認'
                                           % (r['tag'], r['wire']['field_cable'], alt_, r['tag'], '、'.join(str(x) for x in other_), alt_),
                                           '接線圖 第 %d 頁（文字層）' % r['wire']['page']])
                    recs[k].remove(r)
                    st['kks_sensor_moved'] += 1
                else:
                    r2['notes'].insert(0, ['這條路徑在接線圖上段（熱電偶 → 傳送器）寫 %s、下段訊號格寫 %s：兩個編號都列（同一條路徑）' % (alt_, r['tag']),
                                           '接線圖 第 %d 頁（文字層）' % r['wire']['page']])
                    st['kks_sensor_alias'] += 1
                recs[k2].append(r2)
        for k in [k for k in recs if not recs[k]]:
            del recs[k]
    # ---- 2. 控制器 I/O：盤端子（櫃-板位, 板名, TB, 螺絲）→ I/O 點；DeviceTag／變數必須是這個元件（或同位置的電源點）
    ffvars = ff_index(a.dcdas)
    if epc_ix:                                # v17：HRSG／BOP 的盤端子 → 索引的（控制器, 櫃）；芯的板名照索引補上
        st['epc_cab_pairs'] = len(WP.assign_cab(recs, epc_ix, epc_kinds))

    def lookup(r, c):
        return WP.io_lookup(epc_ix, r, c) if r.get('_cab') is not None else io_lookup(by_screw, r['unit'], c)
    for k, plist in recs.items():
        e = ents[k]
        for r in plist:
            r['io'] = []
            if r['mode'] == 'ff' and ffvars is not None and (r.get('ff') or {}).get('seg'):   # 段保護器（FBSP-GT-n）本身不核對變數，只列同段元件
                c0 = next((c for c in r['cond'] if re.fullmatch(r'FFPC\d', c['board']) and re.fullmatch(r'S\d', c['tb'])), None)
                if c0:
                    sn = 8 * (int(c0['board'][4:]) - 1) + int(c0['tb'][1:])
                    tc_, dc_ = ge_cmp(e['tag']), ge_cmp((r.get('ff') or {}).get('dev', ''))
                    want = [x for x in (tc_,) if len(x) >= 4]
                    mine = [v for v in ffvars.get((r['unit'], sn), ()) if any(x in ge_cmp(v) for x in want)]
                    devv = [v for v in ffvars.get((r['unit'], sn), ()) if len(dc_) >= 4 and dc_ in ge_cmp(v)] if not mine else []
                    elsewhere = sorted({s_ for (u_, s_), vs in ffvars.items() if u_ == r['unit'] and s_ != sn for v in vs
                                        if any(x in ge_cmp(v) for x in want + ([dc_] if len(dc_) >= 4 else []))})
                    r.setdefault('ff', {}).update({'s': sn, 'vars': sorted(mine)[:6], 'dev_vars': sorted(devv)[:3], 'other_s': elsewhere if not (mine or devv) else []})
                    st['ff_' + ('same' if mine else 'dev' if devv else 'other' if elsewhere else 'none')] += 1
                    if not (mine or devv) and elsewhere:
                        r['notes'].append(['接線圖把這一段接到 %s %s（＝FF_IN_S%d），控制器組態裡這顆的 FF 變數卻在 FF_IN_S%s：圖面與組態不一致，請以現場核對'
                                           % (c0['board'], c0['tb'], sn, '、S'.join(str(x) for x in elsewhere)), '接線圖 第 %d 頁；signal-atlas 控制器索引' % r['wire']['page']])
            for c in r['cond']:
                if c['board'] not in MARKVIE_BOARDS + ('TBTC',) and not (r.get('_cab') is not None and WP.ca_parts(c)):
                    continue
                st['io_conductors'] += 1
                if by_screw is None:
                    c['io'] = 'none'
                    continue
                cands, how = lookup(r, c)
                if not cands:
                    c['io'] = 'none'
                    st['io_missing'] += 1
                    r['flags'].append('io_missing:%s' % c['core'])
                    continue
                rel_of = lambda h: io_rel(h, e, r['kks'], r.get('dkks') or (), other_keys(r['doc']))   # noqa: E731
                best = min(cands, key=lambda h: IO_RANK[rel_of(h)])
                rel = rel_of(best)
                c['io'] = rel
                c['pin'] = best['sn']
                c['pt'] = best['pt']
                if how:
                    c['how'] = how
                st['io_' + rel] += 1
                if rel not in IO_OK:
                    r['flags'].append('io_%s:%s→%s' % (rel, c['core'], best['dt'] or best['var'] or best['pt']))
                ent = [best['ctrl'], best['mod'], c['pos'].split('-')[-1], c['board'] if how != 'tbtc' else 'STTC', best['pt'], best['var'], best['dt'], rel]
                if ent not in r['io']:
                    r['io'].append(ent)
            # 同一個模組、同一個 DeviceTag 的其他點（TVBA 的 VIB2＝振動值、GAP2_VIB2＝間隙電壓；螺絲只掛在其中一個點上）
            extra = []
            for ctrl, mod, pos, board, pt, var, dt, rel in ([] if kks else r['io']):   # v17：KKS 的 DeviceTag 是設備層，同板其他點多半畫在別頁
                if board in ('TDBT', 'TRLY', 'TBCI', 'SDII'):
                    continue
                for pt2, var2 in by_dev.get((ctrl, mod, pos, dt), []) if by_dev else []:
                    if pt2 != pt and [ctrl, mod, pos, board, pt2, var2, dt, rel] not in r['io'] + extra:
                        extra.append([ctrl, mod, pos, board, pt2, var2, dt, rel])
            r['io'] = sorted(r['io'] + extra, key=lambda x: (x[0], x[1], x[4]))
            if kks:   # v17：DeviceTag 是同一個設備，但組態變數名寫的訊號與接線圖這一格的訊號不同（S10MST10QC601：圖 XB12A、組態 XB11C）
                sm_ = []
                for c in r['cond']:
                    v_ = next((x[5] for x in r['io'] if x[4] == c.get('pt') and x[2] == (c['pos'] or '').split('-')[-1]), '') or ''
                    mv_ = re.search(r'%s([A-Z]?X[A-Z]\d{2}[A-Z]?)' % re.escape(e['tag']), v_)
                    if c.get('sig') and mv_ and c['sig'][len(e['tag']):] and mv_.group(1) != c['sig'][len(e['tag']):]:
                        t_ = (c['pos'], c['num'], c['sig'][len(e['tag']):], mv_.group(1))
                        if t_ not in sm_:
                            sm_.append(t_)
                if sm_:
                    r['_sigmm'] = sm_                     # 第二輪（2 結尾）才決定要不要註記：同一種對法出現在 3 個以上設備＝兩份文件的編號慣例不同
            if kks and not r.get('ctl') and r['io']:   # v17：燃機／汽機圖上只有 KKS 的框：控制器取核對到的點（G11、S1…）
                r['ctl'] = Counter(x[0] for x in r['io']).most_common(1)[0][0]
            if r.get('_cab') == {} and any(WP.ca_parts(c) for c in r['cond']):   # v17：盤的控制器不在索引（一號機 checkout 沒有 BOPCM1、DWTC2）
                r['notes'].append(['這面盤（%s）的控制器 I/O 組態不在 signal-atlas 控制器索引（一號機 checkout 沒有這台控制器），盤端子無法與組態核對'
                                   % (r['wire']['panel'] or r['wire']['panel_desc'])[:60], 'signal-atlas 控制器索引'])
            # 圖面與控制器組態對不上的芯：列成註記（不替任何一方選邊）
            for kind_, txt in (('other', '接線圖畫的盤端子，在控制器組態裡掛的是另一個 GE 編號：%s——可能是同一顆的不同編號，也可能是圖面與組態不一致（圖面筆誤或現場改過線），請以現場核對'),
                               ('unit', '接線圖畫的盤端子，在控制器組態裡掛的是另一台機組的同一種設備（KKS 只差機組碼）：%s——可能是圖面或組態的機組碼寫錯，也可能現場改過線，請以現場核對'),
                               ('spare', '接線圖畫的盤端子，在控制器組態裡是沒有變數、沒有 DeviceTag 的備用點：%s——組態可能把這個訊號接在別的螺絲，請以現場核對'),
                               ('alias', '接線圖畫的盤端子，在控制器組態裡的名稱與圖上的編號寫法不同：%s——可能是同一顆的別名，也可能不是，沒有逐一查證')):
                dts = []
                for c in [c for c in r['cond'] if c.get('io') == kind_]:
                    hs, _how = lookup(r, c)
                    h = next((h for h in hs if h['pt'] == c.get('pt')), hs[0] if hs else None)
                    if h:
                        t_ = '%s %s（%s %s → %s）' % (' '.join(x for x in (c['pos'], c['board'], c['tb'], c['num']) if x), c['core'], h['pt'], h['var'] or '沒有變數',
                                                    h['dt'] or '沒有 DeviceTag')
                        if t_ not in dts:
                            dts.append(t_)
                if dts:
                    r['notes'].append([(txt.replace('另一個 GE 編號', '另一個設備（KKS）').replace('可能是同一顆的不同編號，也可能是圖面與組態不一致（圖面筆誤或現場改過線）',
                                                                                         '圖面與組態不一致（圖面筆誤、組態配錯，或現場改過線）') if kks else txt) % '；'.join(dts),
                                       '接線圖 第 %d 頁；signal-atlas 控制器索引' % r['wire']['page']])
            if any(c.get('io') in ('other', 'spare', 'unit') for c in r['cond']):
                where = io_where(r.get('ctl') or r['unit'], e, r['kks'])
                want_ = sorted({c['sig'][len(e['tag']):] for c in r['cond'] if kks and c.get('io') in ('other', 'spare', 'unit') and c.get('sig')} - {''})
                if where and want_:      # v17：只列這幾條芯的訊號（變數名帶 KKS 的控制器才分得出）；這個設備別的訊號的點不算「接在別的螺絲」
                    vs_ = [h_['var'] for _s, _k, h_ in where_idx.get(r.get('ctl') or r['unit'], ()) if e['tag'] in (h_['var'] or '').upper()]
                    hit_ = [x_ for x_ in vs_ if any(e['tag'] + w_ in x_.upper() for w_ in want_)]
                    if vs_ and not hit_:
                        r['notes'].append(['控制器組態裡沒有這幾條芯的訊號（%s）的點；這個設備在組態裡的其他點：%s' % ('、'.join(e['tag'] + w_ for w_ in want_), '；'.join(where)),
                                           'signal-atlas 控制器索引'])
                        where = []
                if where:
                    r['notes'].append(['控制器組態裡這個編號的點在：%s' % '；'.join(where), 'signal-atlas 控制器索引'])
            if any(c.get('how') == 'tbtc' for c in r['cond']):
                tt = ['%s %s → STTC 螺絲 %s' % (c['pos'], c['num'], c['pin']) for c in r['cond'] if c.get('how') == 'tbtc']
                r['notes'].append(['圖上寫 TBTC（每通道 2 顆螺絲的編法），控制器組態在這個板位是 STTC（每通道 3 顆，含屏蔽）：換算通道後是 %s。'
                                   '通道對得上、螺絲號不同，現場實際接在哪一顆請以盤內實物為準' % '、'.join(tt), '接線圖 第 %d 頁；signal-atlas 控制器索引' % r['wire']['page']])
    if kks:   # v17：訊號編號圖／組態不同——同一種對法（圖 XB31 ↔ 組態 XB01，每一台斷路器都這樣）出現在 3 個以上設備的是編號慣例，不註記
        pdev_ = defaultdict(set)
        for k, plist in recs.items():
            for r in plist:
                for t_ in r.get('_sigmm') or ():
                    pdev_[(t_[2], t_[3])].add(r['tag'])
        conv_ = {pr_ for pr_, ds_ in pdev_.items() if len(ds_) >= 3}
        st['sig_code_convention_pairs'] = len(conv_)
        st['sig_code_convention_devices'] = len({d_ for pr_ in conv_ for d_ in pdev_[pr_]})
        for k, plist in recs.items():
            for r in plist:
                sm_ = [t_ for t_ in r.pop('_sigmm', None) or () if (t_[2], t_[3]) not in conv_]
                if sm_:
                    st['sig_code_mismatch_paths'] += 1
                    r['notes'].append(['接線圖這幾條芯所在訊號格的訊號編號，與控制器組態同一顆螺絲的變數不同（設備相同）：%s——可能只是兩份文件的訊號編號寫法不同，'
                                       '也可能接到別的訊號，沒有逐一查證，請以現場核對' % '；'.join('%s %s：圖 %s、組態 %s' % t_ for t_ in sm_),
                                       '接線圖 第 %d 頁；signal-atlas 控制器索引' % r['wire']['page']])
    # ---- 2b. 訊號型式與迴路供電（v16，wire_sig＋wire_curated.json 的 signal）：每個 Mark VIe 點照接線判（接了 P24V＋20mA＝兩線式…），
    #      ToolboxST 的跳線、選項欄位與接線不一致的另列一則註記（一條路徑一則），不替任何一方選邊
    sg_ = cura.get('signal') or {}
    if sg_.get('rules') and a.dcdas and os.path.exists(a.dcdas):
        import sqlite3
        con = sqlite3.connect('file:%s?mode=ro' % a.dcdas.replace('\\', '/'), uri=True)
        U = WS.union(recs, con)
        for k, plist in recs.items():
            for i, r in enumerate(plist):
                rows_, cfs = [], []
                for x in WS.contexts(r, con, '%s#%d' % (k, i)):
                    res = WS.classify(x, sg_['rules'], sg_.get('meta') or {}, U)
                    if not res:
                        continue
                    st['sig_' + (res['g'] or '?')] += 1
                    rows_.append([x['pt'], res['sig'], res['pow'], res['g'], res['flag'], res['cf'][:3], res['cite'], res['nt'][:2],
                                  res['rule'].endswith('_ONLY') or res['rule'] in WS.PARTIAL_RULES])
                    cfs += ['%s：%s' % (x['pt'], c_) for c_ in res['cf']]
                if rows_:
                    r['sig'] = [x_[:8] for x_ in sorted(rows_, key=lambda x_: x_[8])]   # 主要訊號排前面（借用電源端子、只對上一芯的排後面；看規則代號，不看句子）
                if cfs:
                    st['sig_conflict_paths'] += 1
                    r['notes'].append(['控制器組態（ToolboxST）的跳線或選項欄位與接線不一致——迴路圖的訊號型式與供電照接線判，組態寫法另列、不替任何一方選邊，'
                                       '跳線實際插在哪裡請以現場為準：' + '；'.join(cfs[:4]) + (('（另 %d 則）' % (len(cfs) - 4)) if len(cfs) > 4 else ''),
                                       'signal-atlas 控制器索引（I/O 組態的跳線與選項欄位）；Mark VIe 端子板手冊（迴路圖訊號欄附頁碼）'])
        con.close()
    # ---- 3. 接線箱平面位置（汽機：一號機汽機房儀器與 JB 位置圖）
    jb_where = {}
    if 'jbloc' in tx:
        abs_p = os.path.join(a.library, docs['jbloc']['rel'].replace('/', os.sep))
        for jk, v in jbs.items():
            if not v['kks'] or v['unit'] != 'S10':
                continue
            for pno, pg in enumerate(tx['jbloc']['pg'], 1):
                if not any(w[4] == v['kks'] for w in pg['words']):
                    continue
                R, _m = page_R('jbloc', pno)
                hit = jb_locate(abs_p, pg, R, pno, v['kks'])
                if hit:
                    marks = ([mark_of(pg, R, hit['sym'])] if hit['sym'] else []) + [mark_of(pg, R, hit['label'])]
                    jb_where[jk] = {'page': pno, 'marks': marks, 'coords': hit['coords'], 'sym': 1 if hit['sym'] else 0, 'drawn': v['kks']}
                    used_sheets[('jbloc', pno)] = 'loc'
                    st['jb_located'] += 1
                    break
    # ---- 3a. v17 KKS 版：一號機儀器與接線箱位置圖（IIF01-D0001～D0008）的位置標籤（KKS 下一行是廠區座標）：接線箱、元件本身
    loc_ix, inst_ix = {}, {}
    if kks:
        for kd_, _dn, _zh in WP.LOC_DOCS:
            if kd_ in tx:
                lab_, ins_ = WP.loc_labels(os.path.join(a.library, docs[kd_]['rel'].replace('/', os.sep)), tx[kd_])
                for k_, hs_ in lab_.items():
                    loc_ix.setdefault(k_, []).extend((kd_, h_) for h_ in hs_)
                for k_, v_ in ins_.items():
                    inst_ix.setdefault(k_, (kd_, v_))
        for jk, v in jbs.items():
            if jk in jb_where or not v['kks'] or v['kks'] not in loc_ix:
                continue
            kd_, hit = loc_ix[v['kks']][0]
            pg = tx[kd_]['pg'][hit['page'] - 1]
            R, _m = page_R(kd_, hit['page'])
            marks = ([mark_of(pg, R, hit['sym'])] if hit['sym'] else []) + [mark_of(pg, R, hit['label'])]
            jb_where[jk] = {'page': hit['page'], 'marks': marks, 'coords': hit['coords'], 'sym': 1 if hit['sym'] else 0, 'drawn': v['kks'], 'kind': kd_}
            used_sheets[(kd_, hit['page'])] = 'loc'
            st['jb_located'] += 1
        for plist in recs.values():                 # 別台機組的設備接在這個接線箱（G12QJE11BW001 → G11QJE10UC151）：路徑的鍵是設備的機組
            for r in plist:
                jk2 = '%s|%s' % (r['unit'], r['wire']['jb'])
                jk1 = '%s|%s' % (r['wire'].get('jb_kks', '')[:3], r['wire']['jb'])
                if jk2 not in jb_where and jk1 in jb_where:
                    jb_where[jk2] = jb_where[jk1]
        for plist in recs.values():                 # 元件本身：平面上有自己的標籤，或儀器清單表寫它裝在哪個儀表架（GZ）、儀表架的標籤
            for r in plist:
                hs_ = loc_ix.get(r['tag'])
                iv_ = inst_ix.get(r['tag'])
                if not hs_ and iv_ and loc_ix.get(iv_[1]['rack']):
                    kd_, h_ = loc_ix[iv_[1]['rack']][0]
                    hs_ = [(kd_, dict(h_, rack=iv_[1]['rack'], lst=(iv_[0], iv_[1]['page'], [iv_[1]['tag_box'], iv_[1]['rack_box']])))]
                if hs_:
                    r['_devloc'] = hs_[0]
                    used_sheets[(hs_[0][0], hs_[0][1]['page'])] = 'loc'
                    if hs_[0][1].get('lst'):
                        used_sheets[(hs_[0][1]['lst'][0], hs_[0][1]['lst'][1])] = 'loc'
                    st['devloc'] += 1
    # ---- 3b. 燃機撬上 JB（GE 137T6223 p.11 位置表、p.12 等角圖）；每條幹線（直拉頁是那一條電纜）在電纜表的那一列：兩端的房間
    gtjb_where = {}
    if 'gtjb' in tx:
        for jk, v in jbs.items():
            if v['unit'] in ('G11', 'G12'):
                hit = gtjb_locate(tx['gtjb'], v['jb'], v['kks'])
                if hit:
                    gtjb_where[jk] = hit
                    for kk in ('table', 'iso'):
                        if hit[kk]:
                            used_sheets[('gtjb', hit[kk][0])] = 'loc'
    # ---- 3c. 其餘接線箱：設備圖（JBDOCS）上的箱名或 KKS 標籤（v14；沒有廠區座標，只是箱子在設備上的位置）
    jbdoc_where = {}
    for jk, v in jbs.items():
        if jk in jb_where or jk in gtjb_where:
            continue
        for i, (dn, us, zh, skip) in enumerate(JBDOCS):
            kd = 'jd%d' % i
            if v['unit'] not in us or kd not in tx:
                continue
            hit = jbdoc_locate(tx[kd], skip, v['jb'], v['kks'])
            wk = kks_drawn_core(v['jb'] + ' ' + (v['kks'] or ''))   # 接線圖的箱子 KKS 本體（含尾字母：'G11MKC10XG512A'；jbs 的 kks 只取到三位數）
            if hit:
                pno, boxes, drawn, by, kks_drawn = hit
                R, _m = page_R(kd, pno)
                jbdoc_where[jk] = {'kind': kd, 'page': pno, 'marks': [mark_of(tx[kd]['pg'][pno - 1], R, b_) for b_ in boxes], 'drawn': drawn, 'by': by,
                                   'doc': dn, 'zh': zh, 'kks_drawn': kks_drawn if kks_drawn and wk and kks_drawn_core(kks_drawn) != wk else ''}
                used_sheets[(kd, pno)] = 'loc'
                st['jb_doc'] += 1
                break
    gt_rows = gtjb_rows(tx['gtjb']) if 'gtjb' in tx else []
    gen_names = {}
    for u_, dn in GEN_OUTLINE.items():
        i = next(i for i, jd_ in enumerate(JBDOCS) if jd_[0] == dn)
        if 'jd%d' % i in tx:
            gen_names[u_] = (dn, JBDOCS[i][2]) + jbdoc_names(tx['jd%d' % i], JBDOCS[i][3])
    for plist in recs.values():
        for r in plist:
            jk = '%s|%s' % (r['unit'], r['wire']['jb'])
            g = gen_names.get(r['unit'])
            if g and g[2] and 'MKA10XG' in r['wire']['jb'] and jk not in jb_where and jk not in gtjb_where and jk not in jbdoc_where:
                nm_ = jb_short_base(r['wire']['jb'])
                wpg_ = [i_ for i_, pg_ in enumerate(tx['genwd']['pg'], 1) if any(w_[4] == nm_ for w_ in pg_['words'])] if 'genwd' in tx and r['unit'] in GEN_WIRING else []
                r['notes'].append(['接線圖的接線箱 %s 不在%s（%s）上：圖上畫出的發電機接線箱只有 %s%s。箱子實際在發電機上的哪裡，請以現場為準'
                                   % (nm_, g[1], g[0], '、'.join(g[2]),
                                      ('；GE 燃機發電機接線圖（%s）第 %s 頁的元件表有 %s（箱子存在，這兩份圖都沒有畫出位置）' % (GEN_WIRING[r['unit']], '、'.join(str(x) for x in wpg_), nm_))
                                      if wpg_ else '；兩份文件不一致'),
                                   '%s 第 %s 頁（文字層）%s' % (g[0], '、'.join(str(x) for x in g[3]), ('；%s 第 %s 頁（文字層）' % (GEN_WIRING[r['unit']], '、'.join(str(x) for x in wpg_))) if wpg_ else '')])
            jd_ = jbdoc_where.get(jk)
            if jd_ and jd_['kks_drawn']:
                r['notes'].append(['%s（%s）上這個箱子（圖上寫 %s）旁邊標的 KKS 是 %s，接線圖寫 %s：箱名相同、KKS 寫法不同，沒有逐一查證是不是同一個箱子'
                                   % (jd_['zh'], jd_['doc'], jd_['drawn'], jd_['kks_drawn'], r['wire']['jb']),
                                   '%s 第 %s 頁（文字層）；接線圖 第 %d 頁' % (jd_['doc'], jd_['page'], r['wire']['page'])])
            if r['unit'] in ('G11', 'G12') and gt_rows and jk in jbs:
                for t_, pno_ in gtjb_conflicts(gt_rows, r['wire']['jb'], jbs[jk]['kks'], bool(jk in gtjb_where and gtjb_where[jk]['table'])):
                    r['notes'].append([t_, '%s 第 %s 頁（文字層）；接線圖 第 %d 頁' % (GTJB_DOC, pno_, r['wire']['page'])])
    # ---- 3c2. 盤欄底部的屏蔽排（v15，迴路圖用）；接線圖說明格寫的 KKS 與 GE 編號對照表不同（v15，註記）
    sb_cache = {}
    for k_, plist in recs.items():
        for r in plist:
            pk_ = (r['doc'], r['wire']['page'])
            if pk_ not in sb_cache:
                sb_cache[pk_] = shield_bars(disp_words(tx[r['doc']]['pg'][r['wire']['page'] - 1]))
            if sb_cache[pk_]:
                r['shield'] = sb_cache[pk_]
                st['shield_bar'] += 1
            ks_ = sorted({m_.group(0) for m_ in re.finditer(r'[GS]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?(?![A-Z0-9])', r['wire']['drawn'] or '')})
            dup = sorted(c_ for c_, v_ in Counter(c['core'] for c in r['cond'] if c['core'] and (not kks or re.search(r'-\d', c['core']))).items()
                         if v_ > 1) if not (kks and r['wire'].get('trunks')) else []   # v17：不帶號的 'SH' 每對都一樣、分走幾條幹線的各自從 1 編
            if dup:   # 同一條電纜兩條芯標同一個芯色號（圖面筆誤）：盤側照上下順序對接（v15，迴路圖查核時看到 86WWX 的 BK-3）
                st['dup_core'] += 1
                r['notes'].append(['接線圖上這一條電纜有兩條芯都標 %s（圖面筆誤或漏改）；盤側照上下順序對接，請以現場芯線標示為準' % '、'.join(dup),
                                   '接線圖 第 %d 頁（文字層）' % r['wire']['page']])
            if kks:
                continue                                 # v17：KKS 版的元件就是照圖上的 KKS 認的，不另比對照表
            # 緊貼這個編號寫的 KKS（'TE-201V/ S10MAA11BT863'、'S10MAB10BT005C (TE-205C)'）優先；一格寫好幾顆時只認緊貼的那個
            tg_ = re.escape(r['tag'].lstrip('-'))
            kp_ = r'[GS]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?(?![A-Z0-9])'
            adj_ = sorted({m_.group(1) for m_ in re.finditer(r'(%s)\s*\(\s*%s\s*\)' % (kp_, tg_), r['wire']['drawn'] or '')}
                          | {m_.group(1) for m_ in re.finditer(r'(?<![A-Z0-9-])%s\s*/\s*(%s)' % (tg_, kp_), r['wire']['drawn'] or '')})
            ks_ = adj_ or ks_
            if r['kks'] and len(ks_) == 1 and kks_core(ks_[0])[:10] != kks_core(r['kks'])[:10]:
                r['kks_drawn'] = ks_[0]
                st['kks_drawn_diff'] += 1
                hd_ = re.fullmatch(r'(?:PANEL:\s*)?\S+\s*/\s*\S+', (r['wire']['drawn'] or '').strip())   # 說明只有「編號/KKS」一行＝元件自己那一格的標頭
                where_ = '接線箱／盤欄標頭（%s）' % r['wire']['drawn'].strip() if hd_ else '說明格'
                sysc_ = ents[k_]['system']
                oth_ = sorted(ents[k2]['tag'] for k2 in kks_of.get(sysc_, {}).get(kks_core(ks_[0]), ()) if k2 != k_)   # 對照表上 KKS 就是接線圖這個寫法的別的編號
                r['notes'].append(['接線圖%s寫這個元件的 KKS 是 %s，GE 編號對照表是 %s%s：兩份文件不一致，沒有逐一查證，請以現場銘牌為準'
                                   % (where_, ks_[0], r['kks'], ('；對照表上 KKS 是 %s 的是 %s' % (ks_[0], '、'.join(oth_[:4]))) if oth_ else ''),
                                   '接線圖 第 %d 頁（文字層）；GE 編號對照表' % r['wire']['page']])
    # ---- 3d. 電氣盤格位（v15）：接線圖「接線箱」欄其實是 480 V MCC／PC 的格（'G11BGB10_A1C'）→ GE EP24 盤面配置圖正視圖上框出那一格
    mcc_idx, mcc_seg, mcc_where = {}, {}, {}
    wnames = defaultdict(set)   # 接線圖上每一排寫過的名稱（同一份接線圖別頁寫法不同時，註記一併指出）
    for plist in recs.values():
        for r in plist:
            m = MCC_RE.search(r['wire']['jb'] + ' ' + (r['wire']['jb_desc'] or ''))
            if m and mcc_name(r['wire']['jb'] + ' ' + (r['wire']['jb_desc'] or '')):
                wnames[m.group(1)].add(mcc_name(r['wire']['jb'] + ' ' + (r['wire']['jb_desc'] or '')))
    for i, (u_, title_) in enumerate(MCC_DOCS):
        kd = 'mc%d' % i
        if kd in tx:
            for lu, (pno, tw, nm) in mcc_pages(tx[kd]).items():
                mcc_idx.setdefault(lu, (kd, pno, tw, nm))
    for k_, plist in recs.items():
        for r in plist:
            jk = '%s|%s' % (r['unit'], r['wire']['jb'])
            if r['mode'] in ('direct', 'ff') or jk in jb_where or jk in gtjb_where or jk in jbdoc_where:
                continue
            m = MCC_RE.search(r['wire']['jb'] + ' ' + (r['wire']['jb_desc'] or ''))
            m2 = MCC_EPC_RE.search(r['wire']['jb']) if kks and not m else None
            if not m and not m2:
                continue
            lu, cub = (m.group(1), m.group(2)) if m else (m2.group(1), m2.group(3))
            # 比對用的 KKS：這個元件的、接線圖說明格寫的；說明格點名的 GE 編號（'(88QA-1) Lube Oil Pump 1 Motor - Available (30QA1)' 的 88QA-1）也換成它的 KKS
            nm = names.get(ents[k_]['system'], {})
            par = {k2 for t_ in TOK_SPLIT.split(r['wire']['drawn'] or '') if t_ for k2 in nm.get(ge_cmp(t_), ()) if k2 != k_}
            kkss = [r['kks']] + list(r.get('dkks') or []) + [x.group(0) for x in MCC_KKS_RE.finditer(r['wire']['drawn'] or '')] + \
                [kks_for(ents[k2], r['unit']) for k2 in sorted(par)]
            if lu not in mcc_idx:
                st['mcc_nodoc'] += 1
                continue
            kd, pno, tw, dname = mcc_idx[lu]
            wname = mcc_name(r['wire']['jb'] + ' ' + (r['wire']['jb_desc'] or ''))
            if dname and wname and dname != wname:
                st['mcc_name_diff'] += 1
                r['notes'].append(['接線圖把這一排寫成 %s（%s），盤面配置圖上 %s 的名稱是 %s：排的 KKS 與格位相同、名稱不同%s（以盤上銘牌為準）'
                                   % (wname, lu, lu, dname, '；同一份接線圖別的頁也把 %s 寫成 %s' % (lu, dname) if dname in wnames.get(lu, ()) else ''),
                                   '%s 第 %d 頁（文字層）；接線圖 第 %d 頁' % (docs[kd]['rel'].rsplit('/', 1)[-1], pno, r['wire']['page'])])
            key = (lu, cub)
            if key not in mcc_where:
                pg = tx[kd]['pg'][pno - 1]
                if (kd, pno) not in mcc_seg:
                    mcc_seg[(kd, pno)] = mcc_segments(os.path.join(a.library, docs[kd]['rel'].replace('/', os.sep)), pno)
                hs, vs = mcc_seg[(kd, pno)]
                ws = disp_words(pg)
                titles = [(lu, tw)] if tw else [(lu, None)]
                if tw:   # 同一頁的其他排（GT 的 BFB10＋BGB10 並排）也要拿來分標籤
                    titles += [(k2, v2[2]) for k2, v2 in mcc_idx.items() if k2 != lu and v2[0] == kd and v2[1] == pno and v2[2]]
                mine = [w for w in ws if MCC_LAB_RE.match(w['t']) and mcc_owner(titles, w) == lu]
                R, _m = page_R(kd, pno)
                hit = None
                mm = re.fullmatch(r'NP(\d)-(\d)', cub)
                if mm:
                    cell, row, txt = mcc_np(hs, vs, ws, mine, tw, int(mm.group(1)), int(mm.group(2)))
                    if cell or row:
                        codes = list(dict.fromkeys(x.group(0) for x in MCC_KKS_RE.finditer(txt)))
                        hit = {'boxes': [b_ for b_ in (cell, row) if b_], 'content': txt, 'codes': codes, 'approx': 1, 'np': 1 if row else 0}
                else:
                    labs = [w for w in mine if w['t'] == cub]
                    if labs:
                        cell = mcc_cell(hs, vs, labs[0])
                        if cell:
                            txt, codes = mcc_content(ws, cell, labs[0])
                            hit = {'boxes': [cell], 'content': txt, 'codes': codes, 'approx': 0}
                        else:   # 框線找不齊：只框標籤（不推算格子範圍）
                            hit = {'boxes': [ubox([labs[0]], 3.0)], 'content': '', 'codes': [], 'approx': 1, 'label_only': 1}
                if hit:
                    hit.update(kind=kd, page=pno, marks=[mark_of(pg, R, b_) for b_ in hit['boxes']], lineup=lu, cub=cub)
                    used_sheets[(kd, pno)] = 'loc'
                    st['mcc_cells'] += 1
                mcc_where[key] = hit
            hit = mcc_where[key]
            if not hit:
                st['mcc_nolabel'] += 1
                r['notes'].append(['接線圖寫這個元件接在 %s 的 %s 格；盤面配置圖（%s）%s 的正視圖上沒有讀到 %s 這一格：兩份文件不一致，或格位標籤是線條字（不在文字層），請以現場盤面為準'
                                   % (lu, cub, docs[kd]['rel'].rsplit('/', 1)[-1], lu, cub),
                                   '%s 第 %d 頁（文字層）；接線圖 第 %d 頁' % (docs[kd]['rel'].rsplit('/', 1)[-1], pno, r['wire']['page'])])
                continue
            mt = mcc_match(hit['codes'], hit['content'], lu, kkss, r['kks']) if not hit.get('label_only') else 'none'
            r['mcc'] = {'kind': hit['kind'], 'page': hit['page'], 'lineup': lu, 'cub': cub, 'content': hit['content'][:160], 'match': mt,
                        'approx': hit['approx'], 'np': hit.get('np', 0)}
            st['mcc_' + mt] += 1
            fn = docs[hit['kind']]['rel'].rsplit('/', 1)[-1]
            src_ = '%s 第 %d 頁（文字層）；接線圖 第 %d 頁' % (fn, hit['page'], r['wire']['page'])
            if mt == 'space':
                r['notes'].append(['盤面配置圖上 %s 的 %s 格寫的是「%s」（備用），接線圖把這個元件接到這一格：兩份文件不一致，請以現場盤面為準' % (lu, cub, hit['content'][:60]), src_])
            elif mt == 'diff':
                r['notes'].append(['盤面配置圖上 %s 的 %s 格寫的是 %s，接線圖接到這一格的元件 KKS 是 %s：KKS 不同。可能是同一台設備的另一個元件（加熱器、輔助接點），'
                                   '也可能兩份文件不一致；沒有逐一查證，請以現場盤面為準'
                                   % (lu, cub, '、'.join(c for c in hit['codes'] if not c.startswith(lu))[:80], r['kks'] or '（接線圖沒有寫）'), src_])
    # ---- 3e. 其餘電氣盤的端子排（v16，wire_ep）：接線圖的「接線箱」或盤那一端是 GPP、手動同步盤、GCB 低壓箱、UAT 就地箱的，框到那一號端子
    #      （配置圖上的端子排、端子表那一列）；LCI 中壓盤與 52ET 只到隔間。兩端都是電氣盤的（UAT → GPP-AUX）兩端各一組。
    #      GPP 燃機、GCB、UAT、52ET 的圖各台共用一份（不是本台竣工）；G12 的手動同步盤沒有向量圖，框在 G11 的圖上（類比）
    ep_paths = {dk: os.path.join(a.library, docs[dk]['rel'].replace('/', os.sep)) for dk, _h, _v in WE.doc_specs() if docs.get(dk, {}).get('rel')}
    t_ep = time.time()
    ep_ix = WE.build_indexes(ep_paths) if ep_paths else {}
    log('電氣盤配置圖索引 %.1f 秒：%s' % (time.time() - t_ep, '、'.join('%s %s' % (g_, '有' if v_ else '缺圖') for g_, v_ in ep_ix.items())))
    ep_where = {}
    for k, plist in recs.items():
        for i, r in enumerate(plist):
            w = r['wire']
            for end, txt in (('jb', '%s %s %s' % (w['jb'], w['jb_desc'] or '', w.get('jb_kks') or '')), ('panel', '%s %s' % (w['panel'], w['panel_desc'] or ''))):
                grp = WE.group_of(r['unit'], txt)
                if not grp or not ep_ix.get(grp):
                    continue
                cc = [{'core': c['core'], 'jb_term': c['jb'], 'panel_board': c['board'], 'panel_tb': c['tb'], 'panel_num': c['num']} for c in r['cond']]
                ent = {'unit': r['unit'], 'end': end, 'jb': w['jb'], 'jb_desc': w['jb_desc'], 'jb_tb': w['jb_tb'], 'panel': w['panel'], 'panel_tb': w['panel_tb'], 'cond': cc}
                marks, labs, rows_, miss, flags_, n_in, n_ok, lkind, lbox = {}, {}, [], [], {}, 0, 0, {}, Counter()
                for c_ in cc:
                    if not (c_['jb_term'] if end == 'jb' else c_['panel_num']):   # 這一端沒畫端子的芯（屏蔽）不算
                        continue
                    n_in += 1
                    hs = WE.locate(ep_ix, grp, ent, c_)
                    if not hs:
                        why = WE.missing(ep_ix, grp, ent, c_)
                        if why:
                            miss.append('%s（%s）' % (c_['core'], why))
                        continue
                    n_ok += 1
                    for h in hs:
                        ex = h.get('extra') or {}
                        for f_ in ('analog', 'generic', 'approx', 'whole'):
                            if ex.get(f_):
                                flags_[f_] = ex[f_]
                        if h['kind'] == 'row' and (ex.get('location') or ex.get('wire')):
                            rw_ = [h.get('label', ''), ex.get('location') or '', ex.get('wire') or '']
                            if rw_ not in rows_:
                                rows_.append(rw_)
                        if not h.get('primary'):
                            continue
                        key_ = (h['doc_key'], h['page'])
                        bx_ = tuple(round(v, 1) for v in h['box'])
                        if bx_ not in marks.setdefault(key_, []):
                            marks[key_].append(bx_)
                            if h.get('label') and h['kind'] != 'strip':
                                lbox[(key_, h['label'])] += 1         # 同一頁同一號框了幾格（並接的端子塊）
                        if h.get('label') and h['label'] not in labs.setdefault(key_, []):
                            labs[key_].append(h['label'])
                            lkind.setdefault(h['label'], h['kind'])
                if not n_in:
                    continue
                st['ep_%s_%s' % (grp, end)] += 1
                st['ep_conductors'] += n_in
                st['ep_located'] += n_ok
                hop_ = []
                for (dk, pp), bxs in sorted(marks.items()):
                    pg = tx[dk]['pg'][pp - 1]
                    R, _m = page_R(dk, pp)
                    hop_.append([dk, pp, [mark_of(pg, R, disp_box(pg, b_)) for b_ in bxs[:24]], ' '.join(labs.get((dk, pp), []))[:80]])
                    used_sheets[(dk, pp)] = 'loc'
                ep_where.setdefault((k, i), []).extend(hop_)
                gd = WE.GROUPS[grp]
                dks = list(dict.fromkeys(dk for (dk, _pp) in sorted(marks)))
                shared = any(WE.DOCS[dk][2] for dk in dks)   # 一份圖多台共用（燃機／汽機 GPP、GCB、UAT、LCI 中壓盤、52ET）：不是本台竣工
                alls = list(dict.fromkeys(x for v in labs.values() for x in v))
                terms = [x for x in alls if lkind.get(x) != 'strip']
                strips = []                                  # 配置圖上的端子排標籤（不是端子）：'TBTCD (26)' 的 (26) 是點數
                for x in alls:
                    if lkind.get(x) == 'strip':
                        y = re.sub(r'\s*\((\d+)\)$', r'（共 \1 點）', x)
                        if grp == 'gpp_gt' and '(A)' not in x and any(x.split()[0] + '(A)' in t for t in terms):
                            y += '（AUX 盤，配置圖標籤沒印 (A)）'
                        strips.append(y)
                r.setdefault('ep', []).append({'end': end, 'grp': grp, 'zh': gd['zh'], 'lv': gd['level'], 'doc': '、'.join(WE.DOCS[dk][3] for dk in dks) or WE.DESC[grp][0],
                                               'how': WE.DESC[grp][1], 'pages': sorted({pp for (_dk, pp) in marks}),
                                               'labs': terms[:40], 'strips': strips[:8], 'n': n_in, 'ok': n_ok, 'rows': rows_[:40],
                                               'multi': sorted({lb for (_kp, lb), c_ in lbox.items() if c_ > 1})[:8],
                                               'dn': '；'.join(dict.fromkeys(WE.DOC_NOTE[dk] for dk in dks if WE.DOC_NOTE.get(dk))),
                                               'shared': 1 if shared else 0, 'analog': flags_.get('analog') or '', 'approx': 1 if flags_.get('approx') else 0,
                                               'whole': 1 if flags_.get('whole') else 0,
                                               'rel': 'typical' if flags_.get('analog') else 'neutral' if shared else 'exact'})
                if miss:
                    st['ep_missing'] += len(miss)
                    r['notes'].append(['接線圖把這條接到%s的端子，%s上沒有找到：%s。兩份文件不一致，或圖面寫法不同，請以現場核對'
                                       % (gd['zh'], WE.DESC[grp][0].split('（')[0], '；'.join(miss[:4])), '%s；接線圖 第 %d 頁' % (WE.DESC[grp][0], w['page'])])
    cs = {u: cable_schedule(tx[ck]) for u, ck in (('S10', 'csst'), ('G11', 'csgt')) if ck in tx}
    cs['G12'] = cs.get('G11', {})
    cs_epc = [(ck_, WP.cable_schedule(tx[ck_])) for ck_, _dn in WP.CS_DOCS if ck_ in tx] if kks else []   # v17：A1001／A1002／A1003
    cs_x = WP.cable_xlsx(a.library, log) if kks else None   # v17：A1003 的 xlsx（rev 1 比 PDF 新）——PDF 上查無的電纜號再查它
    cs_ck = {}
    cs_hit = {}
    for k, plist in recs.items():
        for r in plist:
            w = r['wire']
            cab = w['trunk'] or w['field_cable']
            row, ck_ = cs.get(r['unit'], {}).get(cab), ('csst' if r['unit'] == 'S10' else 'csgt')
            if r['doc'] in epc_kinds:                  # v17：HRSG／電氣 I&C／BOP 的電纜在 A1001／A1002／A1003（照順序找）
                row, ck_ = next(((t_[cab], k_) for k_, t_ in cs_epc if cab in t_), (None, None))
            if row and row.get('del'):
                r['notes'].append(['接線圖的電纜號 %s 在電纜表上是刪除線的列（修訂欄寫 #，已刪除）：兩份文件不一致，請以現場電纜標示為準' % cab,
                                   '接線圖 第 %d 頁；電纜表 第 %d 頁' % (w['page'], row['page'])])
            elif row:
                cs_hit[(r['unit'], cab)] = row
                used_sheets[(ck_, row['page'])] = 'loc'
                cs_ck[(r['unit'], cab)] = ck_
                r['room'] = {k2: row.get(k2, '') for k2 in ('r1', 'r1d', 'd1', 'r2', 'r2d', 'd2', 'type', 'len') + (('d1d', 'd2d') if r['doc'] in epc_kinds else ())}
                r['room']['cable'] = cab
                if r['doc'] in epc_kinds and w['trunk']:   # v17：接線圖的接線箱（MCC 格）與電纜表這條幹線那一端寫的不同（D1001 p.203 A9_A2D ↔ A2_A2D）
                    ends_ = [row.get('d1', ''), row.get('d2', '')]
                    pre_ = cab.split('-W')[0].upper()
                    chk_ = []
                    if w['jb'] and end_toks(w['jb'])[0].startswith(pre_[:8]) and len(pre_) <= 13 and \
                            (not w['jb_kks'] or w['trunk'].startswith(w['jb_kks'])):   # 幹線電纜號是這個接線箱／這一排的（不是就有「前綴是另一個 KKS」那句）
                        chk_.append(('接線箱／MCC 格', w['jb']))
                    elif w['jb'] and len(pre_) <= 13 and re.fullmatch(r'[A-Z]\d{2}[A-Z]{3}\d{2}[-_].+', w['jb'].strip().lstrip('=- ')) and \
                            re.fullmatch(r'[A-Z]\d{2}[A-Z]{3}\d{2}', pre_[:8]) and not end_toks(w['jb'])[0].startswith(pre_[:8]) and \
                            any(x_ and re.fullmatch(r'[A-Z]\d{2}[A-Z]{3}\d{2}[-_].+', x_.strip()) and end_toks(x_)[0] == pre_[:8] for x_ in ends_):
                        chk_.append(('接線箱／MCC 格', w['jb']))   # 接線圖寫的排與幹線電纜號的排不同（D1003 p.577 C10BAC30_15_1、幹線 C10BCA30-WG-301、電纜表 C10BCA30_6_1）
                    if w['panel'] and not any(x_ and x_.upper() in (w['panel_desc'] or '').upper() for x_ in ends_):
                        chk_.append(('盤', w['panel']))
                    for nm_, v_ in chk_:
                        if re.fullmatch(r'[-=]?[A-Z0-9_()-]{8,}', v_) and not any(same_end(v_, x_) for x_ in ends_ if x_):
                            r['notes'].append(['接線圖寫這條幹線的%s是 %s，電纜表 %s 那一列兩端寫 %s ↔ %s：兩份文件不一致，請以現場標示為準'
                                               % (nm_, v_, cab, row.get('d1', ''), row.get('d2', '')), '接線圖 第 %d 頁；電纜表 第 %d 頁' % (w['page'], row['page'])])
                        elif nm_ != '盤':
                            x_ = next((x_ for x_ in ends_ if x_ and same_end(v_, x_) and end_toks(v_) != end_toks(x_) and len(end_toks(v_)[1]) == len(end_toks(x_)[1])), '')
                            if x_:   # 'G12BKB30_A9_A2D' ↔ 'G12BKB30_A2_A2D'：格位相同，中間那一段（盤面配置圖那一格裡寫的單元標籤）不同
                                r['notes'].append(['接線圖寫 MCC 格 %s，電纜表 %s 那一列寫 %s：格位（%s）相同，中間那一段寫法不同（只列出，沒有查證哪一份對）'
                                                   % (v_, cab, x_, end_toks(v_)[1][-1]), '接線圖 第 %d 頁；電纜表 第 %d 頁' % (w['page'], row['page'])])
                spec = w['trunk_spec'] if w['trunk'] else w['field_spec']
                sig_ = lambda t: [(int(m_.group(1)), m_.group(2), int(m_.group(3))) for m_ in re.finditer(r'(\d+)([A-Z]{1,2})-(\d+)', t or '')]   # noqa: E731  '4T-18'＝'04T-18'
                a_, b_ = sig_(spec), sig_(row.get('type'))
                pkk_ = re.search(r'[A-Z]?\d{2}C[A-Z]{2}\d{2}UC\d{3,4}', '%s %s' % (w['panel'], w['panel_desc']))
                mine_ = [x_ for x_ in (w['jb'], w.get('jb_kks', ''), r['tag'], pkk_.group(0) if pkk_ else w['panel']) if x_]
                hit_ = lambda e_: any(same_end(x_, e_) or e_.startswith(x_) or x_.startswith(e_) or end_toks(x_)[0] == end_toks(e_)[0]   # noqa: E731
                                      for x_ in mine_)
                if r['doc'] in epc_kinds and cab.split('-W')[0] == r['tag'] and row.get('d1') and row.get('d2') and not (hit_(row['d1']) and hit_(row['d2'])) \
                        and not any('這條幹線的' in n_[0] for n_ in r['notes']):
                    # v17：元件自己的電纜，電纜表上另一端不是接線圖畫的那一端（D1003 p.289 G12LCB31QN002：重複的一頁把 -WG-002 印成 -WG-001）
                    r['notes'].append(['接線圖的電纜號 %s 在電纜表上接的是 %s ↔ %s，接線圖畫的是 %s：兩份文件不一致（可能是電纜號寫錯，也可能是其中一份的另一端），請以現場電纜標示為準'
                                       % (cab, row['d1'], row['d2'], ' ↔ '.join(x_ for x_ in (w['jb'] or r['tag'], w['panel']) if x_)),
                                       '接線圖 第 %d 頁；電纜表 第 %d 頁' % (w['page'], row['page'])])
                elif a_ and b_ and a_[0] != b_[0]:
                    r['notes'].append(['接線圖寫電纜 %s 是 %s，電纜表寫 %s：兩份文件的芯數／線規不一致，請以現場電纜標示為準' % (cab, spec, row['type']),
                                       '接線圖 第 %d 頁；電纜表 第 %d 頁' % (w['page'], row['page'])])
            elif cab and (cs.get(r['unit']) if r['doc'] not in epc_kinds else cs_epc):
                pre = cab.split('-WG-')[0]
                pool_ = cs[r['unit']] if r['doc'] not in epc_kinds else {c_: v_ for _k, t_ in cs_epc for c_, v_ in t_.items()}
                sib = sorted(c_ for c_, v_ in pool_.items() if c_.startswith(pre + '-WG-') and not v_.get('del'))
                xr_ = (cs_x['rows'].get(cab) if cs_x and r['doc'] in epc_kinds else None)
                tp_ = (WP.cs_text_page(tx[ck_], cab) if kks and r['doc'] not in epc_kinds and ck_ in tx else None)
                if xr_:                                        # v17：PDF（rev 0）沒有、較新的 xlsx 有——版次差，不是兩份文件不一致
                    st['cs_xlsx_only'] += 1
                    r['notes'].append(['接線圖的電纜號 %s 不在電纜表 PDF 上，但在文件庫較新的電纜表 xlsx（%s rev %s，%s）第 %s 列：%s ↔ %s、%s、%s m——電纜表 PDF 的版次較舊，'
                                       '這條電纜的房間與長度請看 xlsx' % (cab, WP.CS_XLSX, cs_x['rev'], cs_x['date'], xr_['sr'] or '?', xr_['d1'] or '?', xr_['d2'] or '?',
                                                                    xr_['type'] or '?', xr_['len'] or '?'),
                                       '接線圖 第 %d 頁；電纜表 xlsx %s' % (w['page'], cs_x['rel'].rsplit('/', 1)[-1])])
                elif tp_:                                      # v17：電纜表的文字裡有，但那一列沒有解析出來（A1005 p.7 最後一列在頁底被裁切）
                    st['cs_text_only'] += 1
                    r['notes'].append(['接線圖的電纜號 %s 在電纜表第 %d 頁的文字裡有，但那一列程式讀不到（例如在頁底被裁切），卡上沒有帶出房間與長度；'
                                       '這不是兩份文件不一致' % (cab, tp_), '接線圖 第 %d 頁；電纜表 第 %d 頁' % (w['page'], tp_)])
                elif sib and pre not in w['panel']:            # 前綴是盤（G11CCJ01UC201）時「同一個設備的電纜」不成立
                    r['notes'].append(['接線圖的電纜號 %s 在電纜表上查無；電纜表上同一個設備的電纜是 %s：兩份文件的電纜號不一致' % (cab, '、'.join(sib[:4])),
                                       '接線圖 第 %d 頁；電纜表' % w['page']])
    for k, plist in recs.items():                 # v17：溫度兩段頁上段的補償導線（'…_TE-WG-001'）也查電纜表
        for r in plist:
            sn_ = r['wire'].get('sensor')
            if sn_ and sn_.get('cable'):
                row, ck_ = next(((t_[sn_['cable']], k_) for k_, t_ in cs_epc if sn_['cable'] in t_), (None, None))
                if row:
                    sn_['cs'] = dict({k2: row.get(k2, '') for k2 in ('type', 'len', 'r1d', 'r2d')}, page=row['page'], doc=docs[ck_]['rel'].rsplit('/', 1)[-1])
    # ---- 4. 電子室盤內：Mark VIe 板位（GE 盤面配置圖：汽機 M0213、燃機 137T7182AL）、Bently 3500 盤的 1TBVIB 端子與機架槽位
    cab_where = {}
    for k, plist in recs.items():
        for r in plist:
            ck = 'cab' if r['unit'] == 'S10' else 'cabgt'
            if ck not in tx or r.get('_cab') is not None:   # v17：HRSG／BOP 盤不是 GE 的控制盤
                continue
            for c in r['cond']:
                if c['board'] in MARKVIE_BOARDS + ('TBTC',) and c['pos'] and (ck, c['pos']) not in cab_where:
                    m = re.match(r'^(CA\d{3})-(\d[A-Z])(\d[A-Z])$', c['pos'])
                    if not m:
                        continue
                    pno, side = cab_page(tx[ck], m.group(1), m.group(2))
                    cab_where[(ck, c['pos'])] = None
                    if not pno:
                        continue
                    pg = tx[ck]['pg'][pno - 1]
                    R, _m = page_R(ck, pno)
                    bp = m.group(2) + m.group(3)
                    sib = bp[:3] + ('B' if bp[3] == 'A' else 'A')
                    split = ((r['unit'], sib) in boards and (r['unit'], bp) in boards) or c['board'].startswith('S')   # S 開頭（STTC、SPID…）是半高的精簡型端子板
                    box = board_box(pg, bp, split=split)
                    if box:
                        cab_where[(ck, c['pos'])] = {'page': pno, 'kind': ck, 'marks': [mark_of(pg, R, box)], 'drawn': '%s %s %s' % (m.group(1), side, m.group(2) + m.group(3)),
                                                     'side': side}
                        used_sheets[(ck, pno)] = 'loc'
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
        rack_pages = [i for i, pg in enumerate(tx['vms']['pg'], 1)
                      if sum(1 for w in pg['words'] if w[4] == 'SLOT') >= 10 and any(w[4] == 'CH1' for w in pg['words'])]   # 只看機架槽位表（RACK 1／RACK 2 LAYOUT）
        for k, plist in recs.items():
            for i, r in enumerate(plist):
                if r['unit'] != 'S10':
                    continue
                core = re.sub(r'^[A-Z]\d\d', '', r['kks'])
                for pno in rack_pages:
                    pg = tx['vms']['pg'][pno - 1]
                    if not any(w[4] == core for w in pg['words']):
                        continue
                    R, _m = page_R('vms', pno)
                    hit = rack_cell(pg, core)
                    if hit:
                        rack_where[(k, i)] = {'page': pno, 'marks': [mark_of(pg, R, hit['box'])], 'rack': hit['rack'], 'slot': hit['slot'], 'ch': hit['ch'], 'drawn': core}
                        used_sheets[('vms', pno)] = 'loc'
                        break
    # ---- 4b. Bently 3500 並聯分支（v16，wire_curated.json 的 branch）：Mark VIe 先收到訊號、3500 收 TVBA 的緩衝輸出（JA1／JB1／JC1／JD1 排線）；
    #      1TBVIB 速度型只有 3500 收；SEDP 是 Mark VIe 轉送 4–20 mA。燃機的機架槽位這一版才有（GT-VMP Rev D 的 RDS-PP 欄，G11→RACK 1、G12→RACK 2）；
    #      'RP-1 (Jumpered)' 是送 GHM 的鍵相、不進 3500，原本照標籤掛上的槽位拿掉。框在 3500 接線表那一頁（機架槽位表已經是 rack 那一跳）
    bnw_where = {}
    br_ = cura.get('branch') or {}
    rack_pg = set(rack_pages) if 'vms' in tx else set()
    for k, plist in recs.items():
        b = br_.get(k)
        if not b:
            continue
        for i, r in enumerate(plist):
            if b.get('kind') == 'ghm':
                if rack_where.pop((k, i), None):
                    st['rack_dropped'] += 1
                r['bx'] = {'kind': 'ghm', 'lab': b.get('branch_label_zh') or ''}
                r['notes'].append([b.get('caution_zh') or b.get('branch_label_zh') or '', '；'.join(re.sub(r'^【[^】]*】', '', c_)[:140] for c_ in (b.get('cite') or [])[:2])])
                continue
            bu = (b.get('by_unit') or {}).get(r['unit']) or {}
            lab = b.get('branch_label_zh') or ''
            if bu.get('controller'):
                lab = lab.replace('G11S／G12S', bu['controller'])
            if bu.get('rack'):
                lab = lab.replace('RACK 1（G11）／RACK 2（G12）', 'RACK %s' % bu['rack'])
            alt, aw = b.get('ch_if_pr_order'), 'pr' if b.get('ch_if_pr_order') else ''
            if not alt and b.get('bently_vs_markvie') == 'legacy_column_conflict_rds_agrees' and b.get('bently_legacy_row'):   # 燃機：Legacy Tag 欄的另一種讀法
                alt, aw = {'rack': b.get('rack') or bu.get('rack'), 'slot': b.get('slot'), 'ch': str(b['bently_legacy_row'])}, 'legacy'
            me = re.search(r'(ETB \d+)\s*\([^)]*\)\s*(CH\d)', lab)
            via = ('經 %s %s' % (me.group(1), me.group(2))) if me else ''
            if b.get('shra'):
                via = '來源 %s → VMS 盤 1TBVIB %s' % (b['shra'], b.get('vms_tb') or '')
            r['bx'] = {k2: v for k2, v in (('kind', b.get('kind')), ('lab', lab), ('conn', b.get('connector')), ('mod', b.get('module')),
                                            ('rack', b.get('rack') or bu.get('rack')), ('slot', b.get('slot')), ('ch', b.get('ch')), ('alt', alt), ('aw', aw),
                                            ('g', b.get('grade')), ('cf', b.get('bently_vs_markvie')), ('via', via),
                                            ('panel', b.get('panel') or ('ST1 VMS 盤 S10CCD01UC201' if r['unit'] == 'S10' else '')),
                                            ('cite', [re.sub(r'^【[^】]*】', '', c_) for c_ in (b.get('cite') or [])[:2]])) if v}
            st['bx_paths'] += 1
            for bo in b.get('boxes') or []:
                kd = next((kk for kk in ('vms', 'vmsgt') if kk in tx and docs[kk].get('rel') == bo.get('doc')), None)
                if not kd or (kd == 'vms' and bo['page'] in rack_pg) or (kd == 'vmsgt' and r['unit'] != 'G11'):
                    continue
                pg = tx[kd]['pg'][bo['page'] - 1]
                R, _m = page_R(kd, bo['page'])
                bnw_where.setdefault((k, i), {}).setdefault((kd, bo['page']), []).append(mark_of(pg, R, disp_box(pg, bo['bbox'])))
                used_sheets[(kd, bo['page'])] = 'loc'
    # ---- 4c. 中間設備（v16，wire_curated.json 的 mid）：96KP 的電荷放大器、乾燥器的安全柵與 PLC、發電機上的 JB-164／163、JB87 的 DVP、前置器、光電轉換模組…
    mid_of = {kk: m for m in cura.get('mid') or [] for kk in m.get('keys') or []}
    for k, plist in recs.items():
        m = mid_of.get(k)
        for r in plist if m else []:
            if r['unit'] not in (m.get('units') or [r['unit']]):
                continue
            r['mid'] = {'chain': m['chain'], 'gap': m.get('gap', ''), 'one': m.get('one', 0), 'ns': m.get('ns', 0)}   # ns：屏蔽不從元件拉（同軸／盤內接地／兩段不連）
            for n_ in m.get('notes') or []:
                if list(n_) not in r['notes']:
                    r['notes'].append(list(n_))
            st['mid_paths'] += 1
    notes = load_notes(a.notes, log)
    # ---- 5. sheets、by_ge（pid_shots 與 build_card_aux 的圖紙檢查用）、paths
    slug = {}
    sheets_out = {}
    for r in [r for v in recs.values() for r in v if r.get('conn')]:
        for p_, b in r['conn']:
            used_sheets[('conn', p_)] = 'loc'
    for (kind, pno), sk in sorted(used_sheets.items()):
        d = docs[kind]
        s = L.slug(d['rel'], pno)
        slug[(kind, pno)] = s
        R, method = page_R(kind, pno)
        sheets_out[s] = sheet_rec(d, tx[kind]['pg'][pno - 1], pno, tx[kind]['pages'], R, method, 'wire' if kind in ('wire', 'wiregt') or kind in epc_kinds else 'loc', 0)
    if len(set(slug.values())) != len(slug):
        sys.exit('slug 撞號（不同圖紙得到同一個鍵）')
    by_ge, paths_out = {}, {}
    tags_on = Counter()
    for k in sorted(recs):
        plist = sorted(recs[k], key=lambda r: (uord(r['unit']), r['doc'] != 'wire', r['wire']['page'], r['wire'].get('sub', 0)))
        hits, outs = [], []
        for pi, r in enumerate(plist):
            hops = []
            for cp in sorted({p_ for p_, b in r.get('conn') or []}):
                pgc = tx['conn']['pg'][cp - 1]
                Rc, _m = page_R('conn', cp)
                hops.append(['conn', slug[('conn', cp)], [mark_of(pgc, Rc, b) for p_, b in r['conn'] if p_ == cp], r['tag']])
            dl_ = r.get('_devloc')
            if dl_:                                    # v17：元件本身在一號機儀器位置圖（IIF01）上的位置標籤
                pg_ = tx[dl_[0]]['pg'][dl_[1]['page'] - 1]
                R_, _m = page_R(dl_[0], dl_[1]['page'])
                mk_ = ([mark_of(pg_, R_, dl_[1]['sym'])] if dl_[1]['sym'] else []) + [mark_of(pg_, R_, dl_[1]['label'])]
                ls_ = dl_[1].get('lst')                  # 經儀表架：儀器清單表那一列（儀器、儀表架兩格）
                if ls_ and (ls_[0], ls_[1]) == (dl_[0], dl_[1]['page']):
                    mk_ += [mark_of(pg_, R_, b_) for b_ in ls_[2]]
                elif ls_:
                    pgl_ = tx[ls_[0]]['pg'][ls_[1] - 1]
                    Rl_, _m = page_R(ls_[0], ls_[1])
                    hops.append(['devlist', slug[(ls_[0], ls_[1])], [mark_of(pgl_, Rl_, b_) for b_ in ls_[2]], r['tag']])
                hops.append(['devloc', slug[(dl_[0], dl_[1]['page'])], mk_, dl_[1].get('rack') or r['tag']])
            hops.append(['wire', slug[(r['doc'], r['wire']['page'])], r['wire']['marks'], r['wire']['drawn']])
            jw = jb_where.get('%s|%s' % (r['unit'], r['wire']['jb']))
            if jw:
                hops.append(['jbloc', slug[(jw.get('kind', 'jbloc'), jw['page'])], jw['marks'], jw['drawn']])
            gw = gtjb_where.get('%s|%s' % (r['unit'], r['wire']['jb']))
            if gw:
                for kk, kind_ in (('iso', 'gtjb'), ('table', 'gtjbt')):
                    if gw[kk]:
                        pg_ = tx['gtjb']['pg'][gw[kk][0] - 1]
                        R_, _m = page_R('gtjb', gw[kk][0])
                        hops.append([kind_, slug[('gtjb', gw[kk][0])], [mark_of(pg_, R_, gw[kk][1])], jb_short_base(r['wire']['jb'])])
            jd = jbdoc_where.get('%s|%s' % (r['unit'], r['wire']['jb']))
            if jd:
                hops.append(['jbdoc', slug[(jd['kind'], jd['page'])], jd['marks'], jd['drawn']])
            mc = r.get('mcc')
            if mc:
                mw = mcc_where[(mc['lineup'], mc['cub'])]
                hops.append(['mcc', slug[(mc['kind'], mc['page'])], mw['marks'], '%s %s' % (mc['lineup'], mc['cub'])])
            for dk, pp, mk, drawn in ep_where.get((k, recs[k].index(r)), []):
                hops.append(['epnl', slug[(dk, pp)], mk, drawn])
            csr = cs_hit.get((r['unit'], r['wire']['trunk'] or r['wire']['field_cable']))
            if csr:
                ck = cs_ck.get((r['unit'], r['wire']['trunk'] or r['wire']['field_cable']), 'csst' if r['unit'] == 'S10' else 'csgt')
                pg_ = tx[ck]['pg'][csr['page'] - 1]
                R_, _m = page_R(ck, csr['page'])
                hops.append(['cs', slug[(ck, csr['page'])], [mark_of(pg_, R_, csr['box'])], r['wire']['trunk'] or r['wire']['field_cable']])
            ck = 'cab' if r['unit'] == 'S10' else 'cabgt'
            pos = next((c['pos'] for c in r['cond'] if c['board'] in MARKVIE_BOARDS + ('TBTC',) and cab_where.get((ck, c['pos']))), None) \
                if r.get('_cab') is None else None
            if pos:
                cw = cab_where[(ck, pos)]
                hops.append(['cab', slug[(ck, cw['page'])], cw['marks'], cw['drawn']])
            if vms_where and r['unit'] == 'S10' and any(c['board'] == VMS_BOARD for c in r['cond']):
                hops.append(['vms', slug[('vms', vms_where['page'])], vms_where['marks'], vms_where['drawn']])
            rw = rack_where.get((k, recs[k].index(r)))
            if rw:
                hops.append(['rack', slug[('vms', rw['page'])], rw['marks'], rw['drawn']])
            for (kd, pp), mk in sorted((bnw_where.get((k, recs[k].index(r))) or {}).items()):
                hops.append(['bnw', slug[(kd, pp)], mk, '3500 接線表'])
            for kind, s, marks, drawn in hops:
                tags_on[s] += 1
                for m in marks:
                    hits.append({'sheet': s, 'x': m[0], 'y': m[1], 'w': m[2], 'h': m[3], 'label': drawn, 'rel': 'neutral', 'drawn_as': '', 'how': 'text',
                                 'form': 'text', 'note': 0, 'via': 'ge', 'units': [r['unit']], 'listed': 0, 'hop': kind, 'pi': pi})
            out = {k2: v for k2, v in r.items() if k2 != 'flags' and not k2.startswith('_')}
            out['flags'] = sorted(set(r['flags']))
            out['hops'] = [[kind, s] for kind, s, _m, _d in hops]
            if jw:
                out['jbloc'] = {'coords': jw['coords'], 'sym': jw['sym']}
                if jw.get('kind'):
                    out['jbloc']['kind'] = jw['kind']
            if dl_:
                out['devloc'] = {'kind': dl_[0], 'coords': dl_[1]['coords'], 'sym': 1 if dl_[1]['sym'] else 0}
                if dl_[1].get('rack'):
                    out['devloc']['rack'] = dl_[1]['rack']
            if gw:
                out['gtjb'] = {'name': jb_short_base(r['wire']['jb']), 'coords': gw['table'][2] if gw['table'] else '', 'iso': 1 if gw['iso'] else 0}
            if jd:
                out['jbdoc'] = {'doc': jd['doc'], 'zh': jd['zh'], 'by': jd['by'], 'drawn': jd['drawn']}
            if mc:
                out['mcc'] = {k2: mc[k2] for k2 in ('lineup', 'cub', 'content', 'match', 'approx', 'np')}
            if pos:
                out['cab'] = {'pos': pos, 'approx': 1}
                if cw.get('side') and cw['side'] != 'BACK PANEL':
                    out['cab']['side'] = cw['side']
            if rw:
                out['rack'] = {'rack': rw['rack'], 'slot': rw['slot'], 'ch': rw['ch']}
            elif (r.get('bx') or {}).get('rack') and r['bx'].get('slot'):   # 燃機（v16）：槽位取自 GT-VMP 盤圖的接線表，沒有 rack 那一跳
                out['rack'] = {'rack': r['bx']['rack'], 'slot': r['bx']['slot'], 'ch': r['bx'].get('ch', ''), 'by': 'bx'}
            cur = notes.get(k, []) + notes.get('%s@%s' % (k, r['unit']), []) + notes.get('%s@p%s' % (k, r['wire']['page']), [])   # '鍵@p111'＝只掛在接線圖那一頁的路徑（v16）
            tp = re.match(r'^([SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})', r['wire']['trunk'] or '')
            auto = [n for n in r['notes'] if not (n[0].startswith('幹線電纜號') and tp and any(tp.group(1) in c[0] for c in cur))]   # 人工註記已講清楚的不重複
            b_ = br_.get(k) or {}
            bxc = b_.get('caution_zh') if (r.get('bx') or {}).get('kind') not in (None, 'ghm') else ''
            if bxc and r['unit'] == 'G12':
                bxc = bxc.replace('G11S YVIB', 'G12S YVIB').replace('一號機 Mark VIe 組態是', '一號機 G12 的 Mark VIe 組態是')
            if bxc and not any(c[0][:20] == bxc[:20] for c in cur) and not (b_.get('bently_vs_markvie') == 'conflict' and any('Bently' in c[0] for c in cur)):
                auto.append([bxc, '；'.join(re.sub(r'^【[^】]*】', '', c_)[:140] for c_ in (b_.get('cite') or [])[:2])])   # 3500 分支的警語：人工註記沒講過的才加
            out['notes'] = auto + cur
            outs.append(out)
        by_ge[k] = hits
        paths_out[k] = outs
    for s in sheets_out:
        sheets_out[s]['tags'] = tags_on[s]
    jbs_out = {}
    for jk, v in sorted(jbs.items()):
        jbs_out[jk] = {'unit': v['unit'], 'jb': v['jb'], 'kks': v['kks'], 'desc': v['desc'], 'pages': v['pages'], 'strip': v['strip'],
                       'loc': 1 if jk in jb_where else 0}   # 照圖上的順序（頁序、由上到下）
    ff_out = {}
    for (unit, seg), v in sorted(ffsegs.items()):
        ff_out['%s|%s' % (unit, seg)] = {'page': v['page'], 'jb': v['p']['h'].get('jb', ''), 'trunk': (v['p']['trunks'] or [{}])[0].get('cable', ''),
                                         'trunk_spec': (v['p']['trunks'] or [{}])[0].get('spec', ''),
                                         'cond': [[ctext(r.get('jb_cell')), r['core'], ' '.join(x for x in (r['term']['pos'], r['term']['board'], r['term']['tb'], r['term']['num']) if x)]
                                                  for r in v['rows']]}
    docs_out = {k: ({k2: d[k2] for k2 in ('doc', 'rel', 'rev', 'title', 'alts') if k2 in d and d[k2] not in (None, '')} if d.get('rel') else {'why': d['why']})
                for k, d in docs.items()}
    allp = [r for v in paths_out.values() for r in v]
    stats = {'entries': len(ents) if not kks else sum(1 for k_ in ents if k_.startswith('KKS|')), 'located': len(recs), 'paths': len(allp),
             'by_system': dict(sorted(Counter(ents[k]['system'] for k in recs).items())),
             'by_unit': dict(sorted(Counter(r['unit'] for r in allp).items())),
             'tsi_entries': sum(1 for e in ents.values() if e['tsi']), 'tsi_located': sum(1 for k in recs if ents[k]['tsi']),
             'tsi_missing': sorted(k for k, e in ents.items() if e['tsi'] and k not in recs),
             'by_via': dict(sorted(Counter(r['via'] for r in allp).items())),
             'jbs': len(jbs_out), 'jb_located': sum(1 for v in jbs_out.values() if v['loc']), 'jb_doc': len(jbdoc_where),
             'mcc_cells': sum(1 for v in mcc_where.values() if v), 'mcc_paths': sum(1 for r in allp if r.get('mcc')),
             'boards_located': sum(1 for v in cab_where.values() if v), 'boards_missing': sorted('%s %s' % kk for kk, v in cab_where.items() if not v),
             'rack_located': len(rack_where), 'ff_segments': len(ff_out),
             'ep_paths': sum(1 for r in allp if r.get('ep')), 'ep_jb_paths': sum(1 for r in allp if any(x['end'] == 'jb' for x in r.get('ep') or [])),
             'ep_panel_paths': sum(1 for r in allp if any(x['end'] == 'panel' for x in r.get('ep') or [])),
             'mid_paths': sum(1 for r in allp if r.get('mid')), 'bx_paths': sum(1 for r in allp if r.get('bx')), 'sig_paths': sum(1 for r in allp if r.get('sig')),
             'field_dev_paths': sum(1 for r in allp if r.get('field') and any(DEV_TB_RE.search(f_[5] or '') for f_ in r['field'])),
             'sheets': len(sheets_out), 'scan': {k2: int(v) for k2, v in sorted(st.items())},
             'flags': dict(sorted(Counter(f.split(':')[0] for r in allp for f in r['flags']).items())),
             'by_mode': dict(sorted(Counter(r['mode'] for r in allp).items())),
             'notes': sum(len(r['notes']) for r in allp)}
    if kks:                                       # v17
        stats.update({'by_doc': dict(sorted(Counter(r['doc'] for r in allp).items())), 'by_ctl': dict(sorted(Counter(r.get('ctl') or '' for r in allp).items())),
                      'devloc_paths': sum(1 for r in allp if r.get('devloc')), 'room_paths': sum(1 for r in allp if r.get('room'))})
    out = {'kind': 'wire_kks' if kks else 'wire_ge', 'generated_by': GENERATED_BY, 'version': VERSION,
           'units': list(SITE_UNITS) if not kks else sorted({r['unit'] for r in allp}, key=uord), 'docs': docs_out, 'sheets': sheets_out,
           'by_ge': by_ge, 'paths': paths_out, 'jbs': jbs_out, 'ff': ff_out, 'stats': stats}
    log('耗時 %.1f 秒' % (time.time() - t0))
    return out


def verify(out, root, keys, vdir, log):
    """這些條目的每一條路徑、每一跳：印出內容，並把框疊在轉正後的整張圖上（紅框）另存 PNG——人工讀圖核對用。"""
    import fitz
    from PIL import Image, ImageDraw
    os.makedirs(vdir, exist_ok=True)
    for k in keys:
        plist = out['paths'].get(k) or []
        if not plist:
            log('%s：沒有接線路徑' % k)
            continue
        for pi, r in enumerate(plist):
            log('== %s #%d %s %s mode=%s via=%s p.%s（Sheet %s）flags=%s' % (k, pi, r['unit'], r['kks'], r['mode'], r.get('via'), r['wire']['page'], r['wire']['sheet'], r['flags']))
            log('   JB %s（%s）TB %s｜幹線 %s %s｜盤 %s' % (r['wire']['jb'], r['wire']['jb_desc'], r['wire']['jb_tb'], r['wire']['trunk'], r['wire']['trunk_spec'], r['wire']['panel']))
            for c in r['cond']:
                log('   %-5s 現場 %-8s JB %-16s → %s %s %s %s  io=%s %s %s' % (c['core'], c['field'], c['jb'], c['pos'], c['board'], c.get('tb', ''), c['num'],
                                                                         c.get('io', ''), c.get('pin', ''), c.get('how', '')))
            for x in r.get('io') or []:
                log('   I/O %s' % ' '.join(str(v) for v in x))
            for n in r['notes']:
                log('   註：%s〔%s〕' % (n[0], n[1]))
            for kind, s in r['hops']:
                sh = out['sheets'][s]
                doc = fitz.open(os.path.join(root, sh['rel'].replace('/', os.sep)))
                pix = L.render_upright(doc[sh['page'] - 1], sh['rot'], long_px=2400)
                doc.close()
                im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples) if pix.n == 3 else Image.frombytes('L', (pix.width, pix.height), pix.samples).convert('RGB')
                dr = ImageDraw.Draw(im)
                for h in out['by_ge'][k]:
                    if h['sheet'] != s or h.get('pi', 0) != pi:
                        continue
                    x0, y0 = h['x'] * im.width, h['y'] * im.height
                    dr.rectangle([x0, y0, x0 + h['w'] * im.width, y0 + h['h'] * im.height], outline=(255, 0, 0), width=4)
                fn = os.path.join(vdir, '%s_%d_%s.png' % (re.sub(r'[^A-Za-z0-9_-]', '_', k), pi, kind))
                im.save(fn)
                log('   %s → %s' % (kind, fn))


def debug(a):
    """只印這幾頁接線圖（--debug-doc wire／wiregt）的解析結果與對到的 GE 鍵，不寫檔。"""
    lib = L.walk_pdfs(a.library)
    kind = a.debug_doc
    d = resolve_doc(lib, '%s-1-%s' % (WIRE_UNIT, WIRE_DOC) if kind == 'wire' else WIRE_GT_DOC)
    print(d.get('rel'))
    ents, names, kks_of, _logic = all_entries(a.ge_tags)
    sysset = ('ST', 'ST-GEN') if kind == 'wire' else ('GT', 'GT-GEN')
    tx = load_full_text(a.library, d, a.text_cache)
    pages = [int(x) for x in a.debug_pages.split(',')]
    frames = WG.load_frames(os.path.join(a.library, d['rel'].replace('/', os.sep)), d['rel'], d['size'], d['mtime'], a.text_cache, pages) if kind == 'wiregt' else None
    for pno in pages:
        pg = tx['pg'][pno - 1]
        subs = ([parse_page(pg)] if kind == 'wire' else WG.parse_page(disp_words(pg), frames[pno]))
        for p in subs:
            if not p or not p.get('rows'):
                print('p.%d：%s' % (pno, (p or {}).get('flags')))
                continue
            print('p.%d sub%s %s unit=%s jb=%s (%s) tb=%s | panel=%s tb=%s | flags=%s' % (pno, p.get('sub', 0), p['mode'], p.get('unit', SITE_UNIT), p['h'].get('jb'),
                  p['h'].get('jb_desc'), p['h'].get('jb_tb'), p['h'].get('panel'), p['h'].get('panel_tb'), p['flags']))
            for gi, g in enumerate(p['groups']):
                ids = identify(g, sysset, names, kks_of)
                print('   G%d %s → %s' % (gi, g['desc'][:100], sorted(ids)))
                for r in [r for r in p['rows'] if r.get('group') == gi]:
                    t = term_parts(r['panel_cell']['lines'] if r.get('panel_cell') else [], p['h'].get('panel_tb', ''))
                    print('     %-5s fld=%-8s jb=%-16s → %s' % (r['core'], ctext(r.get('field_cell')), ctext(r.get('jb_cell')), t))


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='接線路徑（GE 原廠編號版；見檔頭 docstring）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（預設 paths.LIBRARY_ROOT；唯讀）')
    ap.add_argument('--ge-tags', default=paths.GE_TAGS, help='GE 原廠編號對照表 ge_tags.json（預設 paths.GE_TAGS）')
    ap.add_argument('--notes', default=os.path.join(os.path.dirname(paths.GE_TAGS or '.'), 'wire_notes.json'),
                    help='人工註記（預設 ge_tags.json 同目錄的 wire_notes.json；不進 repo）')
    ap.add_argument('--curated', default=os.path.join(os.path.dirname(paths.GE_TAGS or '.'), 'wire_curated.json'),
                    help='v16 人工查證資料（中間設備、3500 並聯分支、訊號型式與供電規則；ge_tags_dir 的 wire_curated.json，不進 repo；沒有就不做）')
    ap.add_argument('--dcdas', default=paths.DCDAS_INDEX, help='signal-atlas 控制器索引（預設 paths.DCDAS_INDEX）；不存在就不核對 I/O 點')
    ap.add_argument('--text-cache', default=TEXT_CACHE, help='文字層字框快取目錄（預設 <AMS_LOCAL>\\wiretext，整本）')
    ap.add_argument('--out', default=os.path.join(paths.CARDWORK, 'wire_ge.json'), help='輸出（預設 <CARDWORK>\\wire_ge.json）')
    ap.add_argument('--verify', metavar='KEY', nargs='+', help='另印這些條目（"ST|VP-1X"、"GT|96CD-2A"）的每一條路徑、每一跳並畫疊框圖')
    ap.add_argument('--verify-dir', default=os.path.join(paths.AMS_LOCAL, 'wireverify_ge'), help='疊框圖輸出目錄')
    ap.add_argument('--debug-pages', default='', help='只印這幾頁接線圖的解析結果（逗號分隔的 PDF 頁碼），不寫檔')
    ap.add_argument('--debug-doc', default='wire', choices=('wire', 'wiregt'), help='--debug-pages 看哪一份：wire＝汽機 D1005、wiregt＝燃機 D1004')
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
    print('GE 編號 %d 個有接線路徑（%d 條路徑；%s；機組 %s）；TSI %d／%d，沒有：%s' % (
        st['located'], st['paths'], st['by_system'], st['by_unit'], st['tsi_located'], st['tsi_entries'], st['tsi_missing']))
    print('畫法 %s；身分 %s；接線箱 %d（平面位置 %d）；盤內板位 %d（找不到 %d）；3500 槽位 %d；FF 段 %d；圖紙 %d 張；註記 %d' % (
        st['by_mode'], st['by_via'], st['jbs'], st['jb_located'], st['boards_located'], len(st['boards_missing']), st['rack_located'], st['ff_segments'],
        st['sheets'], st['notes']))
    print('I/O 核對 %s' % {k: v for k, v in st['scan'].items() if k.startswith('io_')})
    print('旗標 %s' % st['flags'])
    if a.verify:
        verify(out, a.library, a.verify, a.verify_dir, print)


if __name__ == '__main__':
    main()
