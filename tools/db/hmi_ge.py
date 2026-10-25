# -*- coding: utf-8 -*-
r"""tools/db/hmi_ge.py — 圖控 HMI 的 GE 原廠編號定位：GE 編號（96FG-1A…）→ 出現在哪個畫面、畫面上的哪個位置。

為什麼需要：tools/db/hmi_index.py 只索引現行 AMS 位號（KKS），GE 供貨的燃機／汽機元件（P1 腔壓力傳送器 96FG-1A、
極限開關、熱電偶…）在 AMS 裡沒有，所以 hmi.json 的 by_tag 沒有任何 GE 範圍的位號。這些元件在圖控上是以
Mark VIe 訊號名出現的（例 numeric 物件 device='a_96fg1a'、ctrlr='{units}'，畫面變數 UNITS='G11S.'），
本工具把 GE 編號對照表（paths.GE_TAGS，hst-docsearch 的 ge_tags.json）的 logic（控制器限定的 I/O 訊號）
對到畫面物件，輸出 cardwork/hmi_ge.json，給 GE 編號卡標「在圖控的哪一頁、畫面上哪一塊」。

**重用 hmi_index**（不重寫）：Contents（長度前綴字串、物件名 0x8e、屬性包 0x5d、矩形四元組）、expand（{變數} 代入）、
frac_rect（設計座標 28800x16200、y 向上 → 左上原點 0~1）、load_nav（hmi_nav.json 的逐列選單與畫面變數）、dumps、ABS_PATH_RE。
只掃 paths.HMI_SCREENS 根目錄的 .cim（248 個＝操作員能導覽到的畫面；子目錄是元件面板與函式庫，見 hmi_index 檔頭），
每個畫面照 nav 的每一組畫面變數各展開一次（同 hmi_index.scan_screen）。
GE 的規則重用 build_card_aux：load_ge（範圍 _scope）、ge_cmp、PREFIX_CTRL（機組→控制器）、GE_SITE_UNITS。

== 條目與範圍 ==
條目鍵一律 "<system>|<tag>"（例 "GT|96FG-1A"；全表 3,956 筆唯一）。system 以 GT 開頭＝燃機範圍 G（機組 G11、G12），
以 ST 開頭＝汽機範圍 S（S10），其餘（?、?-GEN）不發布、只計數（stats.entries_out_of_scope）。

== 機組語意（GE 卡的機組＝設備所屬機組）==
控制器 → 機組：G11、G11S → G11；G12、G12S → G12；S1、S1S、SAMP1 → S10（build_card_aux.PREFIX_CTRL 反查）。
io／related 命中的機組＝**畫面物件實際參照的控制器**的機組，而且這個「控制器.訊號」必須字面出現在條目的 logic（或 related）裡：
G11S 的命中不會掛到 G12。對照表的 logic 只列 G11（GE 文件只印 G11）而畫面在 G12 上參照同名訊號時**不算命中**，
計入 stats.dropped_sibling_ctrl（build_card_aux.ge_logic 用 signal-atlas 確認 G12 同名變數才在卡上列 G12 訊號；
要比照放寬請改這裡的 SIBLING 規則，這一版刻意不放寬）。
entry.unit＝設備所屬機組；entry.nav_unit＝開這張畫面的選單列 Unit 欄原樣（'G11.'，hmi_shots 執行時截圖 runtime.variants 的鍵）；
entry.menu＝那一列的 Menu Item Name（'G11S'，導覽路徑第二層）。同一張畫面同時畫兩部機時（Plant_Overview），
nav_unit='G11.' 但 unit='G12' 是正確的（物件自己寫 G12 的控制器）。

== 匹配鍵與規則（match）==
  io       物件引用了條目 logic 裡的 I/O 訊號（主要的位置）。
  label    物件的顯示文字（屬性 caption／defaultText／anim\d*Text／tooltipCustomText／desc／label／title，或靜態文字記錄）
           去掉分隔符（build_card_aux.ge_cmp）後等於條目的 tag 或 forms（例 permit_short 的 Caption='96FG-1A'）。也是位置。
           caption 是設計時標題：物件另有 defaultText 且兩者不同時（permit_short「SSOV」的 caption 是 VS4-4），畫面上顯示的是 defaultText，
           這時 caption 不算（stats.label_caption_hidden）。
           **不看** device／Xmt*／物件名（實測 device='BPM1'、XmtA='atid1' 是訊號名湊巧等於 forms；物件名 L20FY2961 的 caption 是 FY-2960）。
  related  只引用條目 related（說明欄提到此編號的其他訊號，例 A96FG1A_TH）——**另列、不是設備位置**；
           同一（畫面, 選單列）已有 io／label 命中的條目，related 不發布。
「控制器＋訊號名」怎麼抓（hmi_index.extract_tags 會在 '.' 斷詞而丟掉控制器，所以這裡自己抓）：
  1. 屬性值經 expand 代入後，找字面的 (G11S|G12S|G11|G12|S1S|S1|SAMP1)\.訊號(\.腳位)*，前面不可是英數、底線或 '.'
     （'E11.G11.xxx' 是 E11 控制器裡的變數，不是 G11 的參照）。實測帶點位的鍵：animTooltip「'{ctrlr}{aliasSignal}.Variable_ID'」、
     addtotrendvars／gotodefvar「{units}a_96fg1a」、anim1「'{ctrlr}{device1}'」、各種 '{ctrlr}{device}.hh_sp' 告警腳位。
  2. 屬性值代入後是裸識別字（無 '.'、無 '{'；例 device='a_96fg1a'）時補「控制器＋值」：控制器取物件自己的 ctrlr
     （'{units}' → 'G11S.'）；物件沒有 ctrlr 屬性時只試**本列選單機組**的控制器（Unit 'G11.' → G11、G11S），
     不用變數組裡別機組的值（GT 畫面的 UNIT2 指向另一部機，拿來試會把 G11 畫面的物件掛到 G12）。
  3. 訊號比對不分大小寫、整詞相等；剝屬性尾碼的方式是「點分段由長到短」試（'a_96fg1a.Variable_ID' → 'a_96fg1a'；
     'FDPHW7.mode.$Raw_Value' → 'FDPHW7'；閥塊 '20VSFG1.OPEN' → '20VSFG1'）。
  4. 畫面變數補 {unit}＝選單列 Unit 欄（只在變數組沒有 unit 鍵時；hmi_dump 同樣做法）：hmi_index 沒代入它，
     'G{unit}…'／'{unit}FDPHW7.abq' 這類參照才解得出來。
label 的機組：(1) 物件 ctrlr 代入後是已知控制器 → 該機組；(2) 物件裡有帶控制器的參照且只指向一個機組 → 該機組；
(3) 都沒有（靜態文字、只寫 caption 的物件）→ 本列選單 Unit 欄的機組，但這張畫面這組變數若同時參照同範圍的另一部機
（另一機組參照數 > 本機組的 10%，例 Plant_Overview G11 11／G12 11）就不認（stats.label_skip_mixed）；Unit 欄不是 G11／G12／S1
（HRSG、BOP、AGC、EMAP…）也不認（stats.label_skip_no_unit）。label 只比同範圍（G：GT、GT-GEN；S：ST、ST-GEN）的條目；
同範圍一個寫法對到多個條目時全列並計入 stats.label_ambiguous_forms。

== 物件與矩形（與 hmi_index 不同之處，實測定讞）==
屬性包是一串緊接的「0x5d 鍵 值 旗標(4 bytes)」；一個物件名（0x8e）之後可能接好幾段屬性包——第一段是物件自己的，
後面的是沒有名字的尾隨物件（SystemLine 線段、文字、群組）。hmi_index.objects() 把它們全併到前一個有名字的物件
（同名鍵保留第一個），矩形取「下一個物件名前的最後一個四元組」＝常常是尾隨物件的矩形。
本工具把每一段屬性包當成一個物件（有名字的物件＝第一段；尾隨段的 {變數} 先查自己、再查所屬有名物件、再查畫面變數），
矩形依序取：
  link      段尾之後、下一段屬性包或下一個物件名之前的第一個「函式庫連結記錄」：'.\tpLibrary\tp_actPt_objects.cim>numeric'
            這類長度前綴字串，字串結尾 +48 bytes 的 4 個 int32＝物件外框（l, t, r, b；y 向上）。HMI畫面_AI版 的 hmi_dump.py
            find_links 同一做法。實測 GT/ST 畫面有點位參照的物件 4,541 個中 1,066 個與 hmi_index 不同，
            畫在 gtHA_Gen2_Gas_Fuel_System G11、ST_Overview S1 執行時截圖上：link 框落在數值欄／閥／按鈕上，
            hmi_index 的框落在後面的文字標題或線段上（例 SIL_EFFF 的 A96FG2B 數值被綁到「P2 Cavity Pressure Sensors」標題）。
  dup       同一窗口內「ff ff ff ff, k(<256), l t r b, l t r b（同一組重複一次）」的記錄（CimEdit 原生物件的外框；hmi_dump 同法）。
  fallback  有名物件的第一段：hmi_index 的 rect；尾隨段：null。
都套 hmi_index 的面積上限（> 畫面 25% 視為背景面板，不給座標）。
靜態文字：'3b 01 00 00 64 00 00 00' 之後 +4 是 (x, y)、+12 是長度前綴字串（hmi_dump 同法），外框取該記錄前 300 bytes 內最後一個 dup 記錄，
沒有就以 (x, y) 當零寬零高的點。

== 輸出 cardwork/hmi_ge.json（決定性：鍵排序、清單排序、無時間戳、無本機絕對路徑，結尾 regex 自檢）==
  {"kind":"hmi_ge","generated_by":"tools/db/hmi_ge.py","version":1,
   "by_ge":{"GT|96FG-1A":[{"screen","unit","ctrl","nav_unit","menu","route":"obj"|"var","match":"io"|"label"|"related",
                            "var","ref","x","y","w","h"}]},
   "stats":{…}}
  route=obj 有座標（找不到外框時 x/y/w/h 為 null）；route=var＝物件模型沒收到的字串（hmi_index 的 var 補漏；無座標，只收字面控制器參照）。
  x/y/w/h 是左上原點的 0~1 比例（frac_rect），可直接乘 hmi_shots 縮圖寬高（canvas 0,0,1920,1080 時）；w 或 h 可為 0（點、線）。
  ctrl＝命中的控制器（label 沒有控制器時為 ''）；var＝io/related 是條目 logic／related 裡的訊號名（原大小寫），label 是畫面上的字。
  去重：同一（畫面, 選單列, 外框, 條目）只留一筆，match 優先序 io > label > related，route obj > var；
  同一（畫面, 選單列, 條目）有 io／label 時 related 全部不發布、有座標的 obj 在時同條目無座標的那筆不發布；最多留 MAX_POS 處。

用法
  py tools/db/hmi_ge.py                                  # 全用 paths.py 的預設，寫 %LOCALAPPDATA%\AMS\cardwork\hmi_ge.json
  py tools/db/hmi_ge.py --out D:\hmi_ge.json --ge D:\ge_tags.json --screens D:\Screens
  py tools/db/hmi_ge.py --verify gtHA_Gen2_SIL_EFFF_UX.cim   # 另印該畫面的命中明細（人工核對用）
"""
import argparse
import bisect
import json
import os
import re
import struct
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import hmi_index as HI  # noqa: E402  （olefile 缺席時它會先結束並提示安裝）
import build_card_aux as BCA  # noqa: E402  （import 沒有副作用：main() 在 __name__ 判斷內）

import olefile  # noqa: E402

VERSION = 1
MAX_POS = 8                                    # 同一（畫面, 選單列, 條目）最多留幾處
MIXED_RATIO = 0.10                             # 同範圍另一部機的參照數 > 本機組的這個比例＝混機組畫面，label 不用 Unit 欄定機組
LINK_NEEDLES = ('.cim>'.encode('utf-16-le'), '.cimrt>'.encode('utf-16-le'))
LINK_BBOX_OFF = 48                             # 連結字串結尾到外框四元組的距離（hmi_dump find_links）
TEXT_MARK = b'\x3b\x01\x00\x00\x64\x00\x00\x00'  # 靜態文字記錄（+4 x、+8 y、+12 長度前綴字串）
DUP_MARK = b'\xff\xff\xff\xff'
TEXT_RECT_BACK = 300                           # 靜態文字的外框記錄最多在 marker 前幾個 byte
RUN_GAP = 8                                    # 屬性項之間（前一項值結尾 → 下一項 0x5d）的間隔 <= 這個值算同一段（實測固定 4＝旗標）
LIST_KEYS = ('addtotrendvars',)               # 逗號清單屬性：裡面對到 GE 訊號（io 或 related）的不同點位（去腳位）>= LIST_MIN 個就整個不看
LIST_MIN = 3                                   # 實測只有 addtotrendvars 會這樣（ST_Turbine_Supervisory 的趨勢按鈕列 21 個振動點）；
                                               # 只算「對到 GE 訊號」的點位：MBC 的 ITDP 指示器趨勢清單列 15 點但只有 ITDP_SEL 是 96TD-1A 的，保留
# 函式庫符號的 CAPTION 不畫在畫面上的兩類（名稱開頭比對，不分大小寫；反方驗證 2026-10-25）：
#   LABEL_SYM_SKIP     一律不算 label：eIGV／eVSV 的 DVP Status 按鈕（CAPTION＝EGV2，按鈕上寫的是 DVP Status）。
#   LABEL_SYM_HIDDEN   數值格 numeric／numericBg、警報燈 digitalInd_alarm*、棒圖 bar*、類比指示 analogInd*：caption 是設計時標題，
#                      多半就是那顆儀器（軸承溫度畫面的 TE-272A、潤滑油畫面的 96QQ-30），但也有複製物件留下的錯標題（SIL_VibProx 上
#                      39VS-91 的警報燈 caption＝39V-1A）。物件引用的訊號屬於**別的** GE 編號時不算；其餘照收，標 via='caption'
#                      （卡片寫「物件的設計標題」，不說畫面上看得到）。tooltip、defaultText 等其他顯示文字不受影響。
LABEL_SYM_SKIP = ('dvp',)
LABEL_SYM_HIDDEN = ('numeric', 'digitalind', 'bar', 'analogind')
LABEL_MIN = 4                                    # label 去分隔符後至少幾個字：CV1／CV2（潤滑油逆止閥 ST|CV-1/2）會撞到蒸汽控制閥面板的標題
# 逐通道巨集的輸出：畫面顯示的是 I/O 訊號經 AI 與排氣溫度補償巨集（EX_TMP_7HA_01：ttxd_n → tc1_n）轉手後的變數，一對一對回 TT-XD-n
# （signal-atlas trace：a_ttxd22 → HW_IN_ET/AI_22 → TTXD_22 → TTXD1_22，反方驗證 2026-10-25 H-M2）。只用於燃機範圍
DERIVED = ((re.compile(r'^TTXD1?_(\d+)$'), 'GT|TT-XD-%d', 'G', '排氣熱電偶經 AI 與排氣溫度補償巨集逐通道轉手後的變數'),)
# 轉手鏈（--chain，2026-10-25 v11）：畫面顯示的是 I/O 訊號經一對一的搬移／類比輸入方塊轉手後的變數（71GS-1B 的 G11.a_71gs1b
# → HardwireInputs/HW_IN_GFC/MOVE_4 → F71SCR3DR）。只走下列方塊的「資料進 → 資料出」腳位（signal-atlas 索引的 pin 表），
# 起點只用條目 logic 裡綁在 I/O 點（io_point）上的原始訊號，最多 CHAIN_DEPTH 跳、取最短路徑（逐層展開）。
# 不走：使用者方塊／巨集（腳位以變數命名、裡面是任意邏輯，例 d_49gcb → L30GCB_TRP_COIL1）、RUNG、選擇器、比較器。
CHAIN_PINS = {'MOVE': ('SRC', 'DEST'), 'MOVE_STATUS': ('SRC', 'DEST'), 'AI_INT': ('IN', 'OUT'), 'AI': ('IN', None)}
#   AI 的輸出腳位以變數名命名（TTXD_22、TTXD_22.BQ）：取方向 O、名稱不含 '.' 的那一個（.BQ／.INH 是品質與抑制位元）
CHAIN_DEPTH = 3
# 轉手鏈與 DERIVED 只是「間接」對到：物件若只是在趨勢清單（addToTrendVars，逗號分隔）裡列了這個變數，而清單另外還有 ≥ 2 個變數，
# 那是 Trend 捷徑按鈕、不是顯示這顆設備的地方（反方驗證 2026-10-25：96GG-1 的 DVAR 在 Overview 的 9 點 Trend 鈕、
# TT-XD-n 在 Exhaust 畫面的 TREND 鈕）。直接的 io 照舊（LIST_MIN 規則）。
TREND_OTHERS_MAX = 1
# 轉手鏈命中的物件，標題寫的是**另一種 GE 編號寫法**時卡上註明（汽機 SIL 振動列標 VX-1X、顯示的是 VP-1X；TE-243-E1 那格標 TE-211-3）：
# 只看像 GE 編號的標題（帶連字號、英數、無逗號空白），而且不是本編號的寫法、也不是它的一段（極限開關 33HV-HDAS-50C 的閥 HV-HDAS-50 不算）
CAP_OTHER_RE = re.compile(r'^(?=.*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+$', re.I)
CHAIN_DIR_OK = ('T', 'U', 'M', 'C', 'G')       # 腳位方向來源：L／H（推斷）、R（不透明巨集回推）、-（未知）不走（dcdas SKILL「誠實標示」）
MATCH_RANK = {'io': 0, 'label': 1, 'related': 2}
ROUTE_RANK = {'obj': 0, 'var': 1}

# 控制器 → 機組（build_card_aux.PREFIX_CTRL 反查；C10 沒有控制器）
CTRL_UNIT = {c: u for u, cs in BCA.PREFIX_CTRL.items() if cs for c in cs}
UNIT_SCOPE = {u: sc for sc, us in BCA.GE_SITE_UNITS.items() for u in us}
_CTRL_ALT = '|'.join(sorted(CTRL_UNIT, key=lambda c: (-len(c), c)))
REF_RE = re.compile(r'(?<![A-Za-z0-9_.])(%s)\.([A-Za-z0-9_$\-]+(?:\.[A-Za-z0-9_$\-]+)*)' % _CTRL_ALT, re.I)   # 訊號名可含 '-'（S1.DT-GGC-67）
BARE_RE = re.compile(r'[A-Za-z0-9_\-]+\Z')
LABEL_KEY_RE = re.compile(r'(caption|defaulttext|anim\d*text|tooltipcustomtext|desc|label|title)\Z', re.I)
CMP_OK_RE = re.compile(r'(?=.*\d)(?=.*[A-Z])')
# 物件屬性挑哪一個當 ref 顯示：點位參照鍵優先（同 hmi_index.REF_KEYS），再短的、再鍵名
REF_KEYS = ('device', 'gotodefvar', 'addtotrendvars', 'aliassignal', 'anim', 'desc', 'varvalue0')


def ctrl_of(s):
    """'G11S.' / 'g11s' → 'G11S'（已知控制器）；不是回 None。"""
    c = str(s or '').strip().rstrip('.').upper()
    return c if c in CTRL_UNIT else None


# ---------------------------------------------------------------- GE 對照表 → 匹配索引
def load_ge_index(path, sibling_index=None):
    """→ (ge, idx)。idx: io/rel {(CTRL, SIG大寫): [(條目鍵, 控制器, 原訊號名)]}、label {(範圍, ge_cmp): {條目鍵}}、
    sib {(CTRL, SIG大寫): {條目鍵}}（logic 只列同設計另一部機時的同名訊號，供 dropped_sibling_ctrl 計數）、
    sibio {(條目鍵, CTRL, SIG大寫)}（--sibling 時由 build_card_aux.ge_logic 經 signal-atlas 確認後補進 io 的姊妹機訊號）。"""
    ge = BCA.load_ge(path, sibling_index) if sibling_index else BCA.load_ge(path)
    if ge is None:
        sys.exit('找不到 GE 編號對照表：%s' % path)
    io, rel, label, sib = defaultdict(list), defaultdict(list), defaultdict(set), defaultdict(set)
    forms, host = {}, set()
    st = Counter()
    keys = set()
    for e in ge['entries']:
        key = '%s|%s' % (e.get('system') or '', e['tag'])
        if key in keys:
            sys.exit('條目鍵重複：%s' % key)
        keys.add(key)
        e['_key'] = key
        sc = e['_scope'] if (e.get('system') or '')[:2] in ('GT', 'ST') else None
        e['_sc'] = sc
        if not sc:
            st['out_of_scope'] += 1
            continue
        st['in_scope_' + sc] += 1
        for fld, tgt in (('logic', io), ('related', rel)):
            for n in e.get(fld) or []:
                c, _, s = str(n).partition('.')
                cu = c.upper()
                if not s or cu not in CTRL_UNIT:
                    st['%s_unknown_ctrl' % fld] += 1
                    continue
                if UNIT_SCOPE.get(CTRL_UNIT[cu]) != sc:
                    st['%s_scope_mismatch' % fld] += 1
                    continue
                tgt[(cu, s.upper())].append((key, cu, s))
        own = {str(n).partition('.')[0].upper() for n in e.get('logic') or []}
        for n in e.get('logic') or []:          # 姊妹機控制器的同名訊號（G11→G12、G11S→G12S）：嚴格規則下不算命中，只計數
            c, _, s = str(n).partition('.')
            m = re.match(r'^([A-Z])(\d\d)(S?)$', c.upper())
            if not m or not s:
                continue
            for u in BCA.GE_SITE_UNITS.get(sc) or ():
                t = u + m.group(3)
                if t != c.upper() and t in CTRL_UNIT and t not in own:
                    sib[(t, s.upper())].add(key)
        forms[key] = sorted({e['tag']} | set(e.get('forms') or []))
        for f in forms[key]:
            g = BCA.ge_cmp(f)
            if len(g) >= LABEL_MIN and CMP_OK_RE.match(g):
                label[(sc, g)].add(key)
        # 附屬件（KKS 帶子件尾碼 -BGnn／-MBnn／-EBnn…）的訊號是從主設備的 KKS 別名繼承來的：畫面上那個物件是主設備（閥、馬達），
        # 不是這個附屬件——via='host'，卡片照實寫（反方驗證 2026-10-25：空間加熱器 23QB-1＝88QB1 泵、極限開關 ZS-203B＝ASV 開位）
        if any((BCA.ge_kks(k) or ('', '', ''))[2] for k in e.get('kks') or []):
            for n, how in (e.get('logic_how') or {}).items():
                c, _, s = str(n).partition('.')
                if how == 'KKS 別名' and s:
                    host.add((key, s.upper()))
    sibio = set()
    if sibling_index:                          # 選用：與 GE 編號卡同一規則（ge_logic：同名變數經 signal-atlas 確認才列）
        if not ge.get('vars'):
            sys.exit('--sibling 需要 signal-atlas 索引：%s' % sibling_index)
        for e in ge['entries']:
            if not e.get('_sc'):
                continue
            lit = set(e.get('logic') or [])
            for u in BCA.GE_SITE_UNITS.get(e['_sc']) or ():
                for n in BCA.ge_logic(e, u, ge)[0]:
                    if n in lit:
                        continue
                    c, _, sg = n.partition('.')
                    io[(c.upper(), sg.upper())].append((e['_key'], c.upper(), sg))
                    sibio.add((e['_key'], c.upper(), sg.upper()))
    for k in io:
        io[k] = sorted(set(io[k]))
    for k in rel:
        rel[k] = sorted(set(rel[k]))
    st['label_ambiguous_forms'] = sum(1 for v in label.values() if len(v) > 1)
    return ge, {'io': io, 'rel': rel, 'label': label, 'sib': sib, 'sibio': sibio, 'stats': st, 'forms': forms, 'host': host, 'keys': keys,
                'chain': {}}


def build_chain(index_path, ge, io, sibio):
    """轉手鏈（見 CHAIN_PINS 的說明）→ ({(CTRL, 變數大寫): [(條目鍵, 控制器, 變數原名, 鏈, 推論起點)]}, 計數)。
    鏈＝[[方塊型別, 方塊路徑, 進, 出], …]；推論起點＝起點是 --sibling 補進來的 G12 同名訊號（卡上照 sibling 標推論）。
    丟掉：寫入者不只一個的變數（chain_multi_writer）、本身就在任何條目 logic／related 裡的變數（chain_own_logic：那是該條目自己的 io）、
    變數名去分隔符後等於**別的**條目寫法的（chain_other_form：96HGT8A 這種本身就是另一個 GE 編號的名字）。"""
    import sqlite3
    st = Counter()
    con = sqlite3.connect('file:%s?mode=ro' % index_path.replace('\\', '/'), uri=True)
    vname, vid = {}, {}
    for i, c, n in con.execute('SELECT id, ctrl, name FROM variable'):
        vname[i] = (c, n)
        vid[(c.upper(), n.upper())] = i
    bound = {r[0] for r in con.execute('SELECT DISTINCT var_id FROM io_point WHERE var_id IS NOT NULL')}
    writers = Counter(dict(con.execute("SELECT var_id, COUNT(*) FROM pin WHERE direction = 'O' AND var_id IS NOT NULL GROUP BY var_id")))
    qm = ','.join('?' * len(CHAIN_PINS))
    blocks = {}
    for bid, bt, path in con.execute('SELECT id, block_type, path FROM block WHERE block_type IN (%s)' % qm, tuple(CHAIN_PINS)):
        blocks[bid] = (bt, path, None, [])
    reads = defaultdict(list)
    for bid, name, d, ds, var in con.execute('SELECT p.block_id, p.name, p.direction, p.dir_source, p.var_id FROM pin p JOIN block b ON b.id = p.block_id '
                                            'WHERE b.block_type IN (%s) AND p.var_id IS NOT NULL ORDER BY p.block_id, p.name' % qm, tuple(CHAIN_PINS)):
        bt, path, _i, outs = blocks[bid]
        pin_in, pin_out = CHAIN_PINS[bt]
        if ds not in CHAIN_DIR_OK:
            continue
        if d == 'I' and name == pin_in:
            reads[var].append(bid)
        elif d == 'O' and (name == pin_out if pin_out else '.' not in name):
            outs.append(var)
    con.close()
    own = set(io)
    for e in ge['entries']:
        for fld in ('logic', 'related'):
            for n in e.get(fld) or []:
                c, _, s = str(n).partition('.')
                own.add((c.upper(), s.upper()))
    form_of = defaultdict(set)
    for e in ge['entries']:
        if e.get('_sc'):
            for f in {e['tag']} | set(e.get('forms') or []):
                form_of[BCA.ge_cmp(f)].add(e['_key'])
    chain = defaultdict(list)
    for (cu, su), lst in sorted(io.items()):
        v0 = vid.get((cu, su))
        if v0 is None or v0 not in bound:
            continue
        seen, frontier = {v0}, [(v0, [])]
        for _depth in range(CHAIN_DEPTH):
            nxt = []
            for v, path in frontier:
                for bid in reads.get(v, ()):
                    bt, bpath, _i, outs = blocks[bid]
                    if len(outs) != 1:
                        st['chain_multi_out'] += 1
                        continue
                    o = outs[0]
                    if o in seen:
                        continue
                    seen.add(o)
                    if writers[o] != 1:
                        st['chain_multi_writer'] += 1
                        continue
                    c, n = vname[o]
                    step = path + [[bt, bpath, vname[v][1], n]]
                    nxt.append((o, step))
                    ok = (c.upper(), n.upper())
                    keys = {k for k, _lc, _ls in lst}
                    if ok in own:
                        st['chain_own_logic'] += 1
                        continue
                    if form_of.get(BCA.ge_cmp(n), set()) - keys:
                        st['chain_other_form'] += 1
                        continue
                    for key, lc, ls in lst:
                        chain[ok].append((key, c, n, step, (key, lc, ls.upper()) in sibio))
            frontier = nxt
    out = {}
    for k, v in chain.items():
        best = {}
        for key, c, n, step, sib in v:                      # 同一個條目同一個變數：取最短（再取非推論）的一條
            cand = (len(step), sib, json.dumps(step))
            if key not in best or cand < best[key][0]:
                best[key] = (cand, (key, c, n, step, sib))
        out[k] = [best[key][1] for key in sorted(best)]
    st['chain_vars'] = len(out)
    st['chain_entries'] = len({x[0] for v in out.values() for x in v})
    return out, st


# ---------------------------------------------------------------- .cim：屬性段、連結外框、重複外框、靜態文字
def read_contents(path):
    of = olefile.OleFileIO(path)
    try:
        names = {'/'.join(s).lower(): s for s in of.listdir()}
        return of.openstream(names['contents']).read() if 'contents' in names else None
    finally:
        of.close()


def lenstr(d, i, allow_empty=False):
    """長度前綴 UTF-16LE 字串，含長字串形式（長度位元組 0xff 之後 2 bytes 才是字元數；hmi_dump.lenstr 同法）。
    hmi_index.Contents.rstr 不收 0xff（超過 254 字的運算式，例 animFaultInd），屬性包會因此斷成兩段，所以這裡另寫。"""
    n = len(d)
    if i < 0 or i >= n:
        return None
    L, h = d[i], 1
    if L == 0xff:
        if i + 3 > n:
            return None
        L, h = int.from_bytes(d[i + 1:i + 3], 'little'), 3
    if L == 0:
        return ('', i + h) if allow_empty else None
    end = i + h + 2 * L
    if end > n:
        return None
    try:
        s = d[i + h:end].decode('utf-16-le')
    except UnicodeDecodeError:
        return None
    if any(ord(ch) < 0x20 and ch not in '\r\n\t' for ch in s):
        return None
    return s, end


def attr_items(c):
    """[(0x5d 位置, 值結尾, 鍵, 值)]：屬性項＝0x5d、鍵（識別字，任意長度）、值（可空、可為長字串）、旗標 4 bytes。
    與 hmi_index.Contents.objects() 不同：收 2 字的鍵（'pv'）與超過 254 字的值，屬性包才不會在這些項斷開。"""
    d, out, p = c.d, [], -1
    while True:
        p = d.find(bytes([HI.ATTR_MARK]), p + 1)
        if p < 0:
            return out
        a = lenstr(d, p + 1, False)
        if not a or not HI.IDENT_RE.match(a[0]):
            continue
        b = lenstr(d, a[1], True)
        if b is None:
            continue
        out.append((p, b[1], a[0], b[0]))
        p = b[1] - 1                                   # 值裡面的 0x5d 不再當成新的一項


def rect_ok(r):
    if not r:
        return None
    l, t, rr, b = r
    if not (0 <= l <= rr <= HI.DESIGN_W + 600 and 0 <= b <= t <= HI.DESIGN_H + 600):
        return None
    if (rr - l) + (t - b) <= 0 or (rr - l) * (t - b) > HI.MAX_RECT_AREA * HI.DESIGN_W * HI.DESIGN_H:
        return None
    return (l, t, rr, b)


def link_records(c):
    """[(字串位置, 外框 or None, 符號名小寫)]：函式庫連結字串（'….cim>符號'）結尾 +48 bytes 的四元組。"""
    d, out = c.d, set()
    for nd in LINK_NEEDLES:
        for m in re.finditer(re.escape(nd), d):
            for back in range(2, 300, 2):
                s0 = m.start() - back - 1
                r = c.rstr(s0, False)
                if r and ('.cim>' in r[0] or '.cimrt>' in r[0]) and r[1] > m.start():
                    q = r[1] + LINK_BBOX_OFF
                    out.add((s0, rect_ok(struct.unpack_from('<4i', d, q)) if q + 16 <= c.n else None,
                             r[0].rpartition('>')[2].lower()))
                    break
    return sorted(out, key=lambda x: x[0])


def dup_records(c):
    """[(位置, 外框)]：'ff ff ff ff, k, l t r b, l t r b'（同一組重複一次）。"""
    d, out, p = c.d, [], -1
    while True:
        p = d.find(DUP_MARK, p + 1)
        if p < 0:
            return out
        q = p + 4
        if q + 36 > c.n:
            continue
        k = struct.unpack_from('<I', d, q)[0]
        a = struct.unpack_from('<8i', d, q + 4)
        if k < 0x100 and a[:4] == a[4:] and any(a[:4]):
            r = rect_ok(a[:4])
            if r:
                out.append((p, r))


def static_texts(c, dups):
    """[(位置, 文字, 外框 or 點)]：靜態文字記錄。外框取 marker 前 TEXT_RECT_BACK bytes 內最後一個 dup 記錄，沒有就用 (x, y) 點。"""
    d, out = c.d, []
    dpos = [x[0] for x in dups]
    for m in re.finditer(re.escape(TEXT_MARK), d):
        q = m.end()
        if q + 13 > c.n:
            continue
        x, y = struct.unpack_from('<2i', d, q + 4)
        r = c.rstr(q + 12, False)
        if not r or not r[0].strip():
            continue
        j = bisect.bisect_left(dpos, m.start()) - 1
        if j >= 0 and m.start() - dpos[j] <= TEXT_RECT_BACK:
            rect = dups[j][1]
        elif 0 <= x <= HI.DESIGN_W and 0 <= y <= HI.DESIGN_H:
            rect = (x, y, x, y)
        else:
            rect = None
        out.append((m.start(), r[0], rect))
    return out


def units_objects(c):
    """畫面 → 物件段清單 [{'obj', 'name', 'sub', 'attrs', 'parent', 'rect', 'rect_src', 'pos'}]（見檔頭「物件與矩形」）。"""
    objs = c.objects()
    items = attr_items(c)
    links = link_records(c)
    lpos = [x[0] for x in links]
    dups = dup_records(c)
    dpos = [x[0] for x in dups]
    # 屬性項分段
    runs = []
    for it in items:
        if runs and it[0] - runs[-1][-1][1] <= RUN_GAP:
            runs[-1].append(it)
        else:
            runs.append([it])
    bounds = [o['nend'] for o in objs]
    offs = [o['off'] for o in objs]
    out = []
    seen_sub = Counter()
    for k, run in enumerate(runs):
        j = bisect.bisect_right(bounds, run[0][0]) - 1
        if j < 0:
            continue                                    # 第一個物件名之前＝畫面層的屬性（不是物件）
        o = objs[j]
        sub = seen_sub[j]
        seen_sub[j] += 1
        rend = run[-1][1]
        nxt_name = offs[j + 1] if j + 1 < len(objs) else c.n
        nxt_run = runs[k + 1][0][0] if k + 1 < len(runs) else c.n
        win_end = min(nxt_name, nxt_run)
        attrs = {}
        for _p, _e, key, val in run:
            attrs.setdefault(key, val)
        rect, src, sym = None, 'null', ''
        a = bisect.bisect_left(lpos, rend)
        if a < len(links) and links[a][0] < win_end and links[a][1]:
            rect, src, sym = links[a][1], 'link', links[a][2]
        else:
            b = bisect.bisect_left(dpos, rend)
            if b < len(dups) and dups[b][0] < win_end:
                rect, src = dups[b][1], 'dup'
            elif sub == 0 and o['rect']:
                rect, src = o['rect'], 'fallback'
        out.append({'obj': j, 'name': o['name'], 'sub': sub, 'attrs': attrs, 'rect': rect, 'rect_src': src, 'pos': run[0][0], 'sym': sym})
    # 有名物件的第一段當 parent（尾隨段代入 {變數} 時先查自己、再查它）
    first = {}
    for u in out:
        if u['sub'] == 0:
            first[u['obj']] = u['attrs']
    for u in out:
        u['parent'] = first.get(u['obj'], {}) if u['sub'] else {}
    return out, dups


# ---------------------------------------------------------------- 主流程
def digits_ok(txt, g, key, idx):
    """畫面字與條目寫法的「數字分段」要相同：去分隔符會把 TTXD1_6（6 號熱電偶）黏成 TTXD16＝TT-XD-16（反方驗證 2026-10-25 H-M3）。"""
    segs = re.findall(r'\d+', txt or '')
    return any(re.findall(r'\d+', f) == segs for f in idx['forms'].get(key, ()) if BCA.ge_cmp(f) == g)


def derived_key(ctrl, sig, idx):
    """DERIVED 規則：畫面變數 → (條目鍵, 說明)；不是就 None。"""
    base = (sig or '').upper().split('.')[0]
    for rx, tpl, sc, why in DERIVED:
        m = rx.match(base)
        if m and UNIT_SCOPE.get(CTRL_UNIT.get(ctrl)) == sc:
            key = tpl % int(m.group(1))
            if key in idx['keys']:
                return key, why
    return None


def trend_bases(res):
    """逗號清單屬性（addToTrendVars）代入後 → 不同的基底變數（去控制器前綴、去 .BQ 這類腳位）。"""
    out = set()
    for x in res.split(','):
        x = re.sub(r'^(?:%s)\.' % _CTRL_ALT, '', x.strip(), flags=re.I)
        if x:
            out.add(x.split('.')[0].upper())
    return out


def match_sig(ctrl, sig, tbl):
    """(控制器, 'a_96fg1a.Variable_ID') → (表裡命中的值清單, 命中的訊號大寫)：點分段由長到短試。"""
    for cand in (sig, sig.split('-', 1)[0]) if '-' in sig else (sig,):   # 'S1.ABC-S1.DEF' 這類運算式：退一步取 '-' 之前
        parts = cand.upper().split('.')
        for L in range(len(parts), 0, -1):
            s = '.'.join(parts[:L])
            v = tbl.get((ctrl, s))
            if v:
                return v, s
    return None, None


def ref_text(k, v, res):
    s = '%s=%s' % (k, v) if res == v else '%s=%s（代入後 %s）' % (k, v, res[:60])
    return s[:120]


def scan_screen(fn, path, ne, idx, stats):
    """一個畫面 → [hit dict]（未去重）。"""
    data = read_contents(path)
    if data is None:
        stats['no_contents'] += 1
        return []
    c = HI.Contents(data)
    uos, dups = units_objects(c)
    texts = static_texts(c, dups)
    io, rel, lab, sib = idx['io'], idx['rel'], idx['label'], idx['sib']
    var_sets = ne['variables'] or [{}]
    units = ne['units'] or ['']
    navs = ne['nav'] or []
    hits = []
    for vi, sv in enumerate(var_sets):
        unit_col = units[vi] if vi < len(units) else ''
        menu = navs[vi][1] if vi < len(navs) and len(navs[vi]) > 1 else ''
        svci = {k.lower(): v for k, v in sv.items()}
        svci.setdefault('unit', unit_col)               # 選單列 Unit 欄＝{unit}（見檔頭「匹配鍵與規則」4）
        row_ctrl = ctrl_of(unit_col)
        row_unit = CTRL_UNIT.get(row_ctrl) if row_ctrl else None
        row_ctrls = tuple(BCA.PREFIX_CTRL.get(row_unit) or ()) if row_unit else ()
        unres = Counter()
        seen_strings = set()
        unit_refs = Counter()                             # 這組變數下各機組被參照幾個物件段（判混機組畫面）
        per_uo = []
        for u in uos:
            aci = {k.lower(): v for k, v in u['parent'].items()}
            aci.update({k.lower(): v for k, v in u['attrs'].items()})
            own_ctrl = ctrl_of(HI.expand(aci['ctrlr'], aci, svci, unres)) if aci.get('ctrlr') else None
            refs = {}                                     # (CTRL, sig) -> (排序鍵, 鍵, 原值, 代入後)
            labels = []
            u['_direct'] = set()                          # 有「不是長趨勢清單」的屬性引用的 (CTRL, SIG)：轉手鏈／DERIVED 只認這些（TREND_OTHERS_MAX）
            for k, v in sorted(u['attrs'].items()):
                if not v:
                    continue
                res = HI.expand(v, aci, svci, unres)
                seen_strings.add(res)
                kl = k.lower()
                rank = (0 if kl.startswith(REF_KEYS) else 1, 0 if '{' not in v else 1, len(v), k)
                cands = [(m.group(1).upper(), m.group(2)) for m in REF_RE.finditer(res)]
                if kl in LIST_KEYS and len({(cc, s.upper().split('.')[0]) for cc, s in cands
                                            if match_sig(cc, s, io)[0] or match_sig(cc, s, rel)[0]}) >= LIST_MIN:
                    stats['list_attrs_skipped'] += 1      # 趨勢清單（Trend 按鈕把整組振動點都列進來）不是各設備的位置
                    cands = []
                if BARE_RE.match(res) and '{' not in res and not LABEL_KEY_RE.match(kl):   # 顯示文字（caption…）只走 label，不當訊號參照
                    for cc in ([own_ctrl] if own_ctrl else (row_ctrls if not aci.get('ctrlr') else ())):
                        cands.append((cc, res))
                long_trend = kl in LIST_KEYS and len(trend_bases(res)) > 1 + TREND_OTHERS_MAX
                for cc, s in cands:
                    if not long_trend:
                        u['_direct'].add((cc, s.upper()))
                    cur = refs.get((cc, s.upper()))
                    if cur is None or rank < cur[0]:
                        refs[(cc, s.upper())] = (rank, k, v, res, s)
                symn = (u.get('sym') or '').rsplit('>', 1)[-1].lower()
                if LABEL_KEY_RE.match(kl) and symn.startswith(LABEL_SYM_SKIP):
                    stats['label_sym_skipped'] += 1
                elif LABEL_KEY_RE.match(kl):
                    g = BCA.ge_cmp(res)
                    if len(g) >= LABEL_MIN and CMP_OK_RE.match(g) and '{' not in res:
                        dt = aci.get('defaulttext')
                        if kl == 'caption' and dt and BCA.ge_cmp(HI.expand(dt, aci, svci, unres)) != g:
                            stats['label_caption_hidden'] += 1   # permit 類：畫面上顯示的是 defaultText（例 SSOV），caption（VS4-4）只是設計時標題
                            continue
                        labels.append((k, v, res, g, kl == 'caption' and symn.startswith(LABEL_SYM_HIDDEN)))
            us = {CTRL_UNIT[cc] for cc, _s in refs if cc in CTRL_UNIT}
            for un in us:
                unit_refs[un] += 1
            per_uo.append((u, own_ctrl, refs, labels, us))
        # 混機組判定（label 的第三條路）
        ctx_unit = row_unit
        if ctx_unit:
            mates = [x for x in BCA.GE_SITE_UNITS.get(UNIT_SCOPE.get(ctx_unit), ()) if x != ctx_unit]
            if any(unit_refs[m] > MIXED_RATIO * max(1, unit_refs[ctx_unit]) for m in mates):
                ctx_unit = None
                stats['mixed_variants'].add('%s|%s' % (fn, unit_col))
        for u, own_ctrl, refs, labels, us in per_uo:
            common = {'screen': fn, 'nav_unit': unit_col, 'menu': menu, 'route': 'obj', 'rect': u['rect'],
                      'rect_src': u['rect_src'], 'uo': (u['obj'], u['sub'])}
            for (cc, su), (_r, k, v, res, s) in sorted(refs.items()):
                for tbl, mt in ((io, 'io'), (rel, 'related')):
                    got, _hit = match_sig(cc, s, tbl)
                    if got:
                        for key, lc, ls in got:
                            h = dict(common, key=key, unit=CTRL_UNIT[lc], ctrl=lc, match=mt, var=ls, ref=ref_text(k, v, res))
                            if mt == 'io' and (key, lc, ls.upper()) in idx['sibio']:
                                h['via'] = 'sibling'
                            if mt == 'io' and (key, ls.upper()) in idx['host']:
                                h['via'] = 'host'
                            hits.append(h)
                        break
                else:
                    trend = (cc, su) not in u['_direct']
                    dk = derived_key(cc, s, idx)
                    if dk and trend:
                        stats['trend_list_skipped'] += 1
                        continue
                    if dk:
                        hits.append(dict(common, key=dk[0], unit=CTRL_UNIT[cc], ctrl=cc, match='io', var=s.split('.')[0], ref=ref_text(k, v, res),
                                         via='derived', why=dk[1]))
                        stats['derived_hits'] += 1
                        continue
                    ch, _hit = match_sig(cc, s, idx['chain'])
                    if ch and (trend or not u['rect']):
                        stats['chain_trend_skipped' if trend else 'chain_no_rect'] += 1   # 沒有物件外框的（畫面層級參數）間接命中不發布
                        continue
                    if ch:
                        for key, lc, ls, step, sb in ch:
                            h = dict(common, key=key, unit=CTRL_UNIT[cc], ctrl=cc, match='io', var=ls, ref=ref_text(k, v, res),
                                     via='chain', chain=step)
                            if sb:
                                h['sib'] = 1
                            own = {BCA.ge_cmp(f) for f in idx['forms'].get(key, ())}
                            cap = next((lres.strip() for _lk, _lv, lres, lg, _hd in labels
                                        if CAP_OTHER_RE.match(lres.strip()) and not any(lg in o or o in lg for o in own)), None)
                            if cap:
                                h['cap'] = cap                     # 這格的標題寫的是別的編號（GE 範本槽位：BT-TA1-7 顯示的是 BT-TA1-6）
                            hits.append(h)
                        stats['chain_hits'] += 1
                        continue
                    sg, _ = match_sig(cc, s, sib)
                    if sg:
                        for key in sorted(sg):
                            stats['dropped_sibling'].add((key, CTRL_UNIT[cc], fn))
            if labels:
                if own_ctrl:
                    lu, how = CTRL_UNIT[own_ctrl], 'ctrlr'
                elif len(us) == 1:
                    lu, how = next(iter(us)), 'refs'
                elif us:
                    lu, how = None, 'refs_multi'
                elif ctx_unit:
                    lu, how = ctx_unit, 'nav'
                else:
                    lu, how = None, ('mixed' if row_unit else 'no_unit')
                ref_keys = set()                          # 這個物件引用的訊號屬於哪些 GE 編號（io／related／DERIVED）
                for (cc, _su), (_r, _k, _v, _res, sg) in refs.items():
                    for tbl in (io, rel):
                        ref_keys |= {x[0] for x in (match_sig(cc, sg, tbl)[0] or ())}
                    dk = derived_key(cc, sg, idx)
                    if dk:
                        ref_keys.add(dk[0])
                    ref_keys |= {x[0] for x in (match_sig(cc, sg, idx['chain'])[0] or ())}
                for k, v, res, g, hidden in labels:
                    if not lu:
                        if lab.get(('G', g)) or lab.get(('S', g)):
                            stats['label_skip_' + how] += 1
                        continue
                    for key in sorted(lab.get((UNIT_SCOPE.get(lu), g)) or ()):
                        if not digits_ok(res, g, key, idx):
                            stats['label_digit_split'] += 1
                            continue
                        if hidden and ref_keys and key not in ref_keys:
                            stats['label_hidden_other'] += 1   # 設計標題寫著它，物件引用的卻是別的編號的訊號（複製物件的錯標題）
                            continue
                        h = dict(common, key=key, unit=lu, ctrl=own_ctrl or '', match='label', var=res.strip(),
                                 ref=ref_text(k, v, res), label_how=how)
                        if hidden:
                            h['via'] = 'caption'
                        hits.append(h)
        # 靜態文字（沒有控制器：只用本列 Unit 欄的機組，混機組畫面不認）
        for pos, txt, rect in texts:
            g = BCA.ge_cmp(txt)
            if len(g) < LABEL_MIN or not CMP_OK_RE.match(g):
                continue
            if not ctx_unit:
                if lab.get(('G', g)) or lab.get(('S', g)):
                    stats['label_skip_' + ('mixed' if row_unit else 'no_unit')] += 1
                continue
            for key in sorted(lab.get((UNIT_SCOPE.get(ctx_unit), g)) or ()):
                if not digits_ok(txt, g, key, idx):
                    stats['label_digit_split'] += 1
                    continue
                hits.append({'screen': fn, 'nav_unit': unit_col, 'menu': menu, 'route': 'obj', 'rect': rect,
                             'rect_src': 'text' if rect and rect[0] != rect[2] else ('point' if rect else 'null'),
                             'uo': ('t', pos), 'key': key, 'unit': ctx_unit, 'ctrl': '', 'match': 'label',
                             'var': txt.strip(), 'ref': ('text=%s' % txt.strip())[:120], 'label_how': 'nav'})
        # route=var：物件模型沒收到的字串（只收字面控制器參照）
        for s in c.all_strings():
            if '{' not in s and not REF_RE.search(s):
                continue
            res = HI.expand(s, {}, svci, unres)
            if res in seen_strings:
                continue
            seen_strings.add(res)
            for m in REF_RE.finditer(res):
                cc = m.group(1).upper()
                for tbl, mt in ((io, 'io'), (rel, 'related')):
                    got, _hit = match_sig(cc, m.group(2), tbl)
                    if got:
                        for key, lc, ls in got:
                            hits.append({'screen': fn, 'nav_unit': unit_col, 'menu': menu, 'route': 'var', 'rect': None,
                                         'rect_src': 'null', 'uo': ('v', 0), 'key': key, 'unit': CTRL_UNIT[lc], 'ctrl': lc,
                                         'match': mt, 'var': ls, 'ref': ('%s' % s)[:120]})
                        break
        for name in unres:
            stats['unresolved'][name] += 1
    return hits


def reduce_hits(hits, stats):
    """去重與排序（見檔頭「輸出」）→ {條目鍵: [entry]}。"""
    groups = defaultdict(list)
    for h in hits:
        groups[(h['key'], h['screen'], h['nav_unit'], h['menu'])].append(h)
    by_ge = defaultdict(list)
    for (key, scr, nu, menu), hs in sorted(groups.items()):
        if any(h['match'] in ('io', 'label') for h in hs):
            n0 = len(hs)
            hs = [h for h in hs if h['match'] != 'related']
            stats['related_suppressed'] += n0 - len(hs)
        best = {}
        for h in hs:
            rk = (h['unit'], h['rect'])
            cand = (MATCH_RANK[h['match']], h.get('via') == 'chain', ROUTE_RANK[h['route']], h['ctrl'], h['var'], h['ref'])
            if rk not in best or cand < best[rk][0]:
                best[rk] = (cand, h)
        rows = [v[1] for v in best.values()]
        if any(h['rect'] for h in rows):                # 有座標的在時，同條目無座標的那筆不發布
            rows = [h for h in rows if h['rect']]
        rows.sort(key=lambda h: (MATCH_RANK[h['match']], ROUTE_RANK[h['route']], h['unit'],
                                 -1 if not h['rect'] else HI.frac_rect(h['rect'])[1],
                                 -1 if not h['rect'] else HI.frac_rect(h['rect'])[0], h['ctrl'], h['var'], h['ref']))
        if len(rows) > MAX_POS:
            stats['positions_truncated'] += len(rows) - MAX_POS
            rows = rows[:MAX_POS]
        for h in rows:
            x, y, w, hh = HI.frac_rect(h['rect'])
            by_ge[key].append({'screen': scr, 'unit': h['unit'], 'ctrl': h['ctrl'], 'nav_unit': nu, 'menu': menu,
                               'route': h['route'], 'match': h['match'], 'var': h['var'], 'ref': h['ref'],
                               'x': x, 'y': y, 'w': w, 'h': hh})
            if h.get('via'):
                by_ge[key][-1]['via'] = h['via']        # sibling（--sibling）、host（附屬件借主設備）、derived（DERIVED 規則）、chain（--chain）
            if h.get('chain'):
                by_ge[key][-1]['chain'] = h['chain']
                if h.get('cap'):
                    by_ge[key][-1]['cap'] = h['cap']
                if h.get('sib'):
                    by_ge[key][-1]['sib'] = 1
            stats['rect_src'][h['rect_src']] += 1
            stats['kept'].append(h)
    for v in by_ge.values():
        v.sort(key=lambda e: (e['screen'], e['unit'], e['nav_unit'], e['menu'], MATCH_RANK[e['match']], ROUTE_RANK[e['route']],
                              -1 if e['y'] is None else e['y'], -1 if e['x'] is None else e['x'], e['ctrl'], e['var'], e['ref']))
    return dict(by_ge)


def main():
    ap = argparse.ArgumentParser(description='圖控 HMI 的 GE 原廠編號定位（見檔頭 docstring）')
    ap.add_argument('--screens', default=paths.HMI_SCREENS, help='Screens 目錄（預設 paths.HMI_SCREENS，唯讀）')
    ap.add_argument('--ge', default=paths.GE_TAGS, help='GE 編號對照表 ge_tags.json（預設 paths.GE_TAGS）')
    ap.add_argument('--nav', default=os.path.join(paths.CARDWORK, 'hmi_nav.json'),
                    help='tools/db/hmi_nav.py 的輸出；不存在就直接讀 CIMNavigationMenuItemsStd.csv（同 hmi_index）')
    ap.add_argument('--out', default=os.path.join(paths.CARDWORK, 'hmi_ge.json'), help='輸出（預設 cardwork/hmi_ge.json）')
    ap.add_argument('--sibling', nargs='?', const=paths.DCDAS_INDEX, default=None, metavar='INDEX.sqlite',
                    help='選用（預設關）：logic 只列 G11 的條目，G12 同名變數經 signal-atlas 索引確認後也算 io（同 GE 編號卡 ge_logic 的規則），'
                         '這些位置帶 via="sibling"；不給路徑就用 paths.DCDAS_INDEX')
    ap.add_argument('--chain', nargs='?', const=paths.DCDAS_INDEX, default=None, metavar='INDEX.sqlite',
                    help='選用（預設關）：畫面引用的是 I/O 訊號經 MOVE／MOVE_STATUS／AI／AI_INT 一對一轉手後的變數時也算位置（via="chain"，見 CHAIN_PINS）；'
                         '不給路徑就用 paths.DCDAS_INDEX')
    ap.add_argument('--verify', metavar='FILE.cim', help='另印該畫面的命中明細')
    a = ap.parse_args()

    if not os.path.isdir(a.screens):
        sys.exit('找不到 Screens 目錄：%s' % a.screens)
    files = sorted(f for f in os.listdir(a.screens) if f.lower().endswith('.cim'))
    ge, idx = load_ge_index(a.ge, a.sibling)
    chain_st = Counter()
    if a.chain:
        if not os.path.exists(a.chain):
            sys.exit('--chain 需要 signal-atlas 索引：%s' % a.chain)
        idx['chain'], chain_st = build_chain(a.chain, ge, idx['io'], idx['sibio'])
        print('轉手鏈：%d 個變數（%d 個條目）；丟掉 多寫入者 %d、本身是條目訊號 %d、名稱是別的編號 %d、多輸出方塊 %d' % (
            chain_st['chain_vars'], chain_st['chain_entries'], chain_st['chain_multi_writer'], chain_st['chain_own_logic'],
            chain_st['chain_other_form'], chain_st['chain_multi_out']))
    nav, nav_src = HI.load_nav(a.screens, a.nav if a.nav else None)
    print('GE 條目 %d（G %d、S %d、範圍外 %d）；io 訊號 %d、related 訊號 %d、label 寫法 %d；畫面變數來源 %s' % (
        len(ge['entries']), idx['stats']['in_scope_G'], idx['stats']['in_scope_S'], idx['stats']['out_of_scope'],
        len(idx['io']), len(idx['rel']), len(idx['label']), nav_src))

    stats = {'unresolved': Counter(), 'no_contents': 0, 'mixed_variants': set(), 'dropped_sibling': set(),
             'related_suppressed': 0, 'positions_truncated': 0, 'rect_src': Counter(), 'kept': [], 'list_attrs_skipped': 0, 'label_caption_hidden': 0,
             'label_sym_skipped': 0, 'label_digit_split': 0, 'derived_hits': 0, 'label_hidden_other': 0, 'chain_hits': 0,
             'trend_list_skipped': 0, 'chain_trend_skipped': 0, 'chain_no_rect': 0}
    stats.update({'label_skip_%s' % k: 0 for k in ('mixed', 'no_unit', 'refs_multi')})
    hits = []
    variants = 0
    for fn in files:
        ne = nav.get(fn) or {'title_en': '', 'title_zh': None, 'nav': [], 'units': [], 'variables': [], 'aliases': []}
        variants += len(ne['variables'] or [{}])
        hits.extend(scan_screen(fn, os.path.join(a.screens, fn), ne, idx, stats))
    by_ge = reduce_hits(hits, stats)

    # ------------------------------------------------------------ stats
    ents = {e['_key']: e for e in ge['entries']}
    insc = [e for e in ge['entries'] if e['_sc']]
    with_logic = [e for e in insc if any(ctrl_of(str(n).partition('.')[0]) for n in e.get('logic') or [])]
    by_match = defaultdict(set)
    by_unit = defaultdict(set)
    for k, v in by_ge.items():
        for x in v:
            by_match[x['match']].add(k)
            if x['match'] != 'related':
                by_unit[x['unit']].add(k)
    located = by_match['io'] | by_match['label']
    kept = stats['kept']
    per_obj = defaultdict(set)
    for h in kept:
        if h['match'] != 'related' and h['route'] == 'obj':
            per_obj[(h['screen'], h['nav_unit'], h['menu'], h['uo'])].add(h['key'])
    multi = Counter(len(v) for v in per_obj.values() if len(v) > 1)
    ent_n = sum(len(v) for v in by_ge.values())
    sys_cnt = Counter(ents[k].get('system') or '' for k in located)
    pct = lambda a_, b_: round(100.0 * a_ / b_, 1) if b_ else 0.0  # noqa: E731
    wl_keys = {e['_key'] for e in with_logic}
    st = {
        'screens_scanned': len(files), 'nav_variants_scanned': variants, 'no_contents': stats['no_contents'],
        'screens_with_hits': len({x['screen'] for v in by_ge.values() for x in v}),
        'screens_with_located': len({x['screen'] for v in by_ge.values() for x in v if x['match'] != 'related'}),
        'entries_total': len(ge['entries']), 'entries_in_scope': {'G': idx['stats']['in_scope_G'], 'S': idx['stats']['in_scope_S']},
        'entries_out_of_scope': idx['stats']['out_of_scope'],
        'entries_with_logic': len(with_logic),
        'entries_located': len(located),                                    # io 或 label（設備位置）
        'entries_located_by_system': dict(sorted(sys_cnt.items())),
        'entries_by_match': {'io': len(by_match['io']), 'label': len(by_match['label']),
                             'label_only': len(by_match['label'] - by_match['io']), 'related_only': len(by_match['related'] - located)},
        'entries_by_unit': {u: len(v) for u, v in sorted(by_unit.items())},
        'with_logic_located_io': len(by_match['io'] & wl_keys),
        'with_logic_located_io_pct': pct(len(by_match['io'] & wl_keys), len(wl_keys)),
        'with_logic_not_on_any_screen': len(wl_keys - located - by_match['related']),
        'positions': ent_n,
        'positions_by_match': dict(sorted(Counter(x['match'] for v in by_ge.values() for x in v).items())),
        'positions_by_route': dict(sorted(Counter(x['route'] for v in by_ge.values() for x in v).items())),
        'positions_no_xy': sum(1 for v in by_ge.values() for x in v if x['x'] is None),
        'positions_zero_size': sum(1 for v in by_ge.values() for x in v if x['x'] is not None and (x['w'] == 0 or x['h'] == 0)),
        'positions_truncated': stats['positions_truncated'],
        'rect_src': dict(sorted(stats['rect_src'].items())),
        'objects_multi_entry': sum(multi.values()), 'objects_multi_entry_hist': {str(k): v for k, v in sorted(multi.items())},
        'objects_multi_entry_max': max(multi) if multi else 0,
        'related_suppressed': stats['related_suppressed'], 'list_attrs_skipped': stats['list_attrs_skipped'],
        'label_caption_hidden': stats['label_caption_hidden'],
        'label_sym_skipped': stats['label_sym_skipped'],
        'label_digit_split': stats['label_digit_split'], 'derived_hits': stats['derived_hits'], 'label_hidden_other': stats['label_hidden_other'],
        'positions_by_via': dict(sorted(Counter(e.get('via') or '' for v in by_ge.values() for e in v).items())),
        'label_ambiguous_forms': idx['stats']['label_ambiguous_forms'],
        'label_skip_mixed': stats['label_skip_mixed'], 'label_skip_no_unit': stats['label_skip_no_unit'],
        'label_skip_refs_multi': stats['label_skip_refs_multi'],
        'mixed_variants': sorted(stats['mixed_variants']),
        'dropped_sibling_ctrl': len({(k, u) for k, u, _f in stats['dropped_sibling']}),
        'dropped_sibling_ctrl_entries': len({k for k, _u, _f in stats['dropped_sibling']}),
        'logic_unknown_ctrl': idx['stats']['logic_unknown_ctrl'], 'logic_scope_mismatch': idx['stats']['logic_scope_mismatch'],
        'related_unknown_ctrl': idx['stats']['related_unknown_ctrl'], 'related_scope_mismatch': idx['stats']['related_scope_mismatch'],
        'unresolved_vars_top10': [[k, v] for k, v in sorted(stats['unresolved'].items(), key=lambda kv: (-kv[1], kv[0]))[:10]],
        'max_pos': MAX_POS, 'mixed_ratio': MIXED_RATIO,
        'sibling_mode': bool(a.sibling), 'positions_sibling': sum(1 for v in by_ge.values() for x in v if x.get('via') == 'sibling'),
        'chain_mode': bool(a.chain), 'chain': dict(sorted(chain_st.items())), 'chain_hits': stats['chain_hits'],
        'trend_list_skipped': stats['trend_list_skipped'], 'chain_trend_skipped': stats['chain_trend_skipped'], 'chain_no_rect': stats['chain_no_rect'],
        'entries_chain_only': len({k for k, v in by_ge.items() if v and all(x.get('via') == 'chain' for x in v if x['match'] != 'related')
                                   and any(x['match'] != 'related' for x in v)}),
        'chain_depth': CHAIN_DEPTH, 'chain_blocks': sorted(CHAIN_PINS),
    }
    out = {'kind': 'hmi_ge', 'generated_by': 'tools/db/hmi_ge.py', 'version': VERSION, 'by_ge': by_ge, 'stats': st}
    txt = HI.dumps(out)
    bad = HI.ABS_PATH_RE.search(txt)
    if bad:
        sys.exit('輸出含本機絕對路徑：%r' % txt[max(0, bad.start() - 60):bad.start() + 60])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8', newline='') as f:
        f.write(txt)
    print('寫出 %s（%.2f MB）' % (os.path.basename(a.out), len(txt.encode('utf-8')) / 1048576.0))
    print('條目有位置（io 或 label）%d：io %d、label %d（只有 label %d）、只有 related %d；分機組 %s' % (
        st['entries_located'], st['entries_by_match']['io'], st['entries_by_match']['label'], st['entries_by_match']['label_only'],
        st['entries_by_match']['related_only'], st['entries_by_unit']))
    print('有 logic 的 %d 筆中 io 命中 %d（%.1f%%）；處 %d（無座標 %d）；矩形來源 %s' % (
        st['entries_with_logic'], st['with_logic_located_io'], st['with_logic_located_io_pct'], st['positions'],
        st['positions_no_xy'], st['rect_src']))
    print('畫面 %d（有命中 %d）；同一物件多條目 %d；姊妹機控制器未收 %d（%d 條目）；label 略過 混機組 %d／無機組 %d／多機組 %d' % (
        st['screens_scanned'], st['screens_with_hits'], st['objects_multi_entry'], st['dropped_sibling_ctrl'],
        st['dropped_sibling_ctrl_entries'], st['label_skip_mixed'], st['label_skip_no_unit'], st['label_skip_refs_multi']))

    if a.verify:
        print('\n=== %s ===' % a.verify)
        for k, v in sorted(by_ge.items()):
            for e in v:
                if e['screen'].lower() == a.verify.lower():
                    print('  %-26s %-4s %-5s %-7s %-4s x=%s y=%s w=%s h=%s  %s | %s' % (
                        k, e['unit'], e['ctrl'], e['match'], e['route'], e['x'], e['y'], e['w'], e['h'], e['var'], e['ref'][:70]))


if __name__ == '__main__':
    main()
