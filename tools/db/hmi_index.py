# -*- coding: utf-8 -*-
r"""tools/db/hmi_index.py — 圖控 HMI 位號定位索引：現行 AMS 位號 → 出現在哪個畫面、畫面上的哪個位置。

為什麼需要：AMS 查詢卡現在只講「這台儀器是什麼」，操作員還想知道「它在圖控的哪一頁、畫面上哪一塊」。
本工具把 GE CIMPLICITY／ActivePoint 的 .cim 畫面檔拆開，把畫面物件參照的點位解析成完整 KKS 位號，
再把物件的設計座標換算成 0~1 的畫面比例，配合 tools/db/hmi_shots.py 的畫面縮圖就能直接標點。

== .cim 檔格式（本工具逆向出來的部分；Screens 下所有檔唯讀，不改）==
.cim 是 OLE 複合文件（olefile 可讀），串流（名稱大小寫不一，比對一律 lower()）：
  Contents           物件定義（本工具的主要輸入）
  Compiled/Objects   編譯後的顯示清單（未使用）
  PointsList         畫面用到的 CIMPLICITY 專案前綴清單（XML）
  ThumbNail          設計時全畫面 EMF（hmi_shots.py 用）
Contents 內的字串是「長度位元組（字元數）＋ UTF-16LE」。物件的記錄大致是
    0x8e <長度><物件名> … 0x5d<長度><鍵> <長度><值> … <left:int32><top:int32><right:int32><bottom:int32>
  * 0x8e 是物件名的前導位元組（實測 248 個根目錄畫面裡的物件名一律 0x8e）。
  * 屬性包每一項的前導位元組是 0x5d，之後接「鍵（識別字）＋值（可為空字串）」。
  * 矩形四個 int32 是 (left, top, right, bottom)，**y 軸向上**（top 的數值大於 bottom）。
    已知鍵名：device / ctrlr / aliasSignal / gotodefvar / addtotrendvars / caption / dv_type / flex_deviceNN / anim* / tooltip*。

== 矩形綁定：矩形在記錄的「尾端」，不是開頭（本次修正的錯誤）==
矩形四元組緊貼在**下一個**物件名的 0x8e 之前 16 bytes，所以它屬於**前一個**物件。
先前綁成「物件名之前最後一個四元組」會讓全部物件的座標整體錯位一個物件。
定讞證據（BOP_Phosphate_Dosing_System.cim，左右兩塊鏡像面板，標題分別是
「Phosphate Dosing System Unit 11」(x=3340) 與「… Unit 12」(x=16116)）：
  物件 68 device=G{GUNIT1_NO}QCC60BL602_XQ01（11 號機液位計 bargraph）
  物件 69 ObjectName17   caption=G{GUNIT1_NO}QCC60BL602（11 號機的直書註記）
  物件 70 device=G{GUNIT2_NO}QCC60BL602_XQ01（12 號機）
  物件 71 ObjectName18   caption=G{GUNIT2_NO}QCC60BL602（12 號機）
  串流裡的矩形：…178349(l=6342) [名69] 179082(l=6442) [名70] 186875(l=19222) [名71] 187608(l=19322)…
  舊綁定 → 68 得 l=19073（右，12 號機側）、70 得 l=6442（左，11 號機側）＝左右互換；
  新綁定 → 68/69 得 l=6342/6442（左），70/71 得 l=19222/19322（右），且兩兩相差固定 12880＝面板鏡像位移。
同一支腳本對全部 248 個畫面跑「機組1／機組2 物件應分居兩半」的鏡像測試，新綁定也較舊綁定乾淨
（例 BOPE_MV_G11BKB20_1.cim 29/57 → 51/57、HRSG_Stack_Damper_UX.cim 6/10 → 9/10）。

== 座標基準（實測定讞，推翻先前 25600x14400 的推測）==
設計座標是 **28800 x 16200**（twips：1920x1080 裝置像素，每像素 15 twips；28800/16200 = 16:9）。
驗證方式：把 ThumbNail EMF 渲染成 1920x1080 PNG（tools/db/hmi_shots.py，canvas 固定 0,0,1920,1080，
所以 0~1 比例可直接乘上縮圖寬高），再把本工具的矩形畫框疊上去，框線與畫面上的控制項逐一吻合。
獨立佐證：tools/db/hmi_nav.py 另一條路徑（文字記錄長度位元組前的兩個 int32）抽出的標題座標
(3340, 12842)「Phosphate Dosing System Unit 11」換算 px (223, 224)，與縮圖上標題文字的位置相符。
先前「25600 常數」是讀偏一個位元組的 (315,100) 旗標對（3b 01 00 00 64 00 00 00）造成的錯覺。
輸出的 x/y/w/h 一律換成 0~1 比例、**左上為原點**（y 已翻轉），所以可以直接乘上縮圖的寬高。

== 位號怎麼解析出來 ==
參照字串長這樣：'{UNIT}C{UNIT_NO}LAC50KC100'、'{ctrlr}{device}'、'G{GUNIT1_NO}AXC10UC901XB78'。
兩層代入（最多 6 層，取到不動點為止）：
  1. 物件自身屬性包（{device}／{ctrlr}／{aliasSignal}… 就是同一個物件的屬性值；鍵名比對不分大小寫）
  2. 畫面變數（tools/db/hmi_nav.py 從 navigation/CIMNavigationMenuItemsStd.csv 整理的每列選單項目各一組；
     同一畫面被不同選單項目以不同變數組開啟（多機組）時**每組各展開一次**，各自產生一組位號）
代不出來的 {變數} 留在字串裡（當成分隔符），並計入 stats.unresolved_vars。
再從結果字串切出詞（分隔符＝非 [A-Za-z0-9_-]），取「最長且落在 AMS 現行位號集合內的前綴」，
前綴後面必須是字串結尾或 _ / -（所以 C10LAB22BF001_XQ01 → C10LAB22BF001，但 G11_90LT-12 不會誤判成 G11_90LT-1）；
另外再試一次「機組前綴＋詞」（選單列的 Unit 欄與畫面變數裡形如 G11／G12／C10／H11 的值），
對應 '{UNIT_NO}HSD10BF101' 這種點位名不帶機組前綴的寫法。

多點簡寫 `\NNN`：一個物件同時掛好幾支同群組的量測時，寫成 '{UNIT_NO}LBA11BP011\012\013'
（＝ …BP011、…BP012、…BP013，三取二壓力變送器）或 '{UNIT_NO}HAP70BT001\002'。
每一段數字取代基底字串的末 N 個字元，展開成多個位號（共用同一個物件座標）。

== 四條來源（entry.route）==
  obj      .cim 物件屬性包 → 兩層代入（**有座標**，少數物件記錄沒帶矩形則 x/y/w/h 為 null）
  var      .cim Contents 裡沒被物件模型收進去的字串（補漏；無座標）
  pointdb  navigation/tp_actPt_navPointSearchDbStd.csv（17,737 列「點位,機組,畫面檔」；無座標）
  dcdas    控制器索引的 hmi_point 表（source='display_screen'，由 variable.display_screen 經 io_point.device_tag／
           connection 解析而來；索引沒有 hmi_point 時退用 variable ⋈ io_point 自己解）（無座標）
只收**現行 AMS 位號**（BlockAsgms.EventIdDayOut=49710 的指派、Blocks.BlockIndex=0、ExtBlockTags，清掉非可列印殘碼），
含 JK*（HART MUX 模組）會另計但不列入覆蓋率母數。

== 掃描範圍（報告數字別再寫成「473 個 .cim」）==
Screens 目錄遞迴有 473 個 .cim，但**索引只建根目錄的 248 個**＝操作員能從選單導覽到的畫面。
其餘 225 個在子目錄（customFaceplate 157／tpFpFaceplate 47／customLibrary 17／navigation 2／utilities 1／help 1）
＝元件面板與函式庫範本，沒有選單列也沒有畫面變數，座標沒有「畫面上哪裡」可言，所以不列入索引。
為了讓「這支位號不在圖控畫面裡」有證據，scan_excluded() 仍會把這 225 個檔的字串逐條用同一套 extract_tags 掃過，
結果寫進 stats.excluded_scan——卡片與 CONTRACT 的數字一律取自這裡，不要自己寫死。
實測（2026-10-03）：完整 AMS 位號命中 12 支（1-LI-CW101-1/2/3、C10LCB40BP001/BT001、C10MAG10/11/20/21 系列），
**這 12 支全部已由根目錄畫面涵蓋**，所以排除子目錄沒有漏掉任何一台；FF 位號 0 命中。

用法
  py tools/db/hmi_index.py                                   # 全用 paths.py 的預設，寫 %LOCALAPPDATA%\AMS\cardwork\hmi.json
  py tools/db/hmi_index.py --screens D:\Screens --out D:\hmi.json
  py tools/db/hmi_index.py --no-dcdas --no-shots
  py tools/db/hmi_index.py --verify BOP_Feed_Water.cim       # 另印該畫面解析到的物件／位號／座標（人工核對用）

輸出（契約見任務說明；決定性：鍵排序、清單排序、無時間戳、無本機絕對路徑，結尾以 regex 自檢）
  {"kind":"hmi","generated_by":"tools/db/hmi_index.py","screens":{…},"by_tag":{…},"stats":{…}}
  screens[*].units 是去重排序過的機組清單（**不與 nav 逐列對齊**；要逐列對齊請看 hmi_nav.json 的 units／variables）。
  by_tag[*].w 可能是 0（直線、文字錨點就是零寬或零高），前端遇到 0 要畫成點／細線，不要畫成看不見的框。
  by_tag[*].unit 是「用哪一列選單（哪一組畫面變數）開這張畫面」，**不是這台儀器屬於哪一機組**。
    同時畫兩部機的畫面（BOP_Blowdown_Recovery_System.cim、Plant_Overview_UX.cim…）會出現
    unit=H11. 但位號是 G12… 的 entry，那是正確的（物件自己寫 device=G{GUNIT2_NO}…）。
    前端要顯示機組請用位號本身的前綴，不要用這個欄位。
  by_tag[*].x/y 是**左上為原點**的 0~1 比例，可直接乘上 hmi_shots 縮圖的寬高
    （實測 109 張根目錄縮圖的畫布一律 0,0,1920,1080，與設計座標同比例；子目錄面板縮圖不在 screens 裡）。
"""
import argparse
import csv
import io
import json
import os
import re
import sqlite3
import struct
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

try:
    import olefile
except ImportError:
    sys.exit('缺 olefile：py -m pip install olefile')

DESIGN_W, DESIGN_H = 28800, 16200      # 設計座標（twips；1920x1080 × 15）。見檔頭「座標基準」
OBJ_MARK = 0x8e                        # 物件名前導位元組
ATTR_MARK = 0x5d                       # 屬性鍵前導位元組
MAX_EXPAND = 6                         # {變數} 代入的最大層數
MAX_POS_PER_SCREEN = 8                 # 同一位號在同一畫面最多留幾個位置
MAX_RECT_DIST = 400                    # 矩形離物件名最多幾個 byte（實測 99.2% 落在 400 內；再遠就是別人的矩形，寧可留 null）
MAX_RECT_AREA = 0.25                   # 矩形佔畫面面積上限（超過＝背景面板被誤認，實測全廠只有 2 個物件踩到）
OPEN_DAY = 49710                       # BlockAsgms.EventIdDayOut 哨兵＝現行指派
POINT_CSV = ('navigation', 'tp_actPt_navPointSearchDbStd.csv')

VAR_RE = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')
MULTI_RE = re.compile(r'([A-Za-z0-9_\-]*[A-Za-z0-9])((?:\\\d+)+)')   # 多點簡寫 BASE\NNN\NNN
UNITPFX_RE = re.compile(r'[A-Z]\d{2}\Z')
LITERAL_RE = re.compile(r'[A-Za-z]\d{2}[A-Za-z]')                    # 值裡有「字母+兩位數字+字母」＝看起來自帶位號字樣
IDENT_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
TOKEN_SPLIT = re.compile(r'[^A-Za-z0-9_\-]+')
BAD_CHR_RE = re.compile(r'[^\x20-\x7e]')
ALNUM_RE = re.compile(r'[A-Za-z0-9]')
TAIL_JUNK_RE = re.compile(r'\s{2,}\S{1,2}$')
XQ_RE = re.compile(r'^(.+?)XQ\d{2}$')
ABS_PATH_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|\\Users\\|/Users/|我的雲端硬碟')
# 這些屬性值是運算式／樣式，不是點位參照；掃描成本不高所以仍會掃，只是不當 ref 代表
REF_KEYS = ('device', 'gotodefvar', 'addtotrendvars', 'aliassignal', 'anim', 'desc', 'varvalue0')


def dumps(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def read_text(path):
    with open(path, 'rb') as f:
        b = f.read()
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode('latin-1')


def norm_name(n):
    """檔名正規化（跨索引對檔名用）：去目錄、去 .cim、去尾綴 _UX、去非英數、小寫。"""
    n = os.path.basename((n or '').strip())
    n = re.sub(r'\.cim$', '', n, flags=re.I)
    n = re.sub(r'_UX$', '', n, flags=re.I)
    return re.sub(r'[^a-z0-9]', '', n.lower())


def clean_tag(t):
    """AMS 位號清殘碼（與 tools/db/sheets_devices.clean_tag 同規則）。"""
    s = BAD_CHR_RE.sub('', str(t or ''))
    return TAIL_JUNK_RE.sub('', s).strip()


# ---------------------------------------------------------------- .cim Contents 解析
class Contents(object):
    """Contents 串流的字串／物件／矩形解析（格式說明見檔頭）。"""

    def __init__(self, data):
        self.d = data
        self.n = len(data)

    def rstr(self, i, allow_empty=True):
        """位置 i 的「長度位元組＋UTF-16LE」字串 → (文字, 下一個位置)；不是字串回 None。"""
        d, n = self.d, self.n
        if i >= n:
            return None
        L = d[i]
        if L == 0xff:
            return None
        if L == 0:
            return ('', i + 1) if allow_empty else None
        end = i + 1 + 2 * L
        if end > n:
            return None
        try:
            s = d[i + 1:end].decode('utf-16-le')
        except UnicodeDecodeError:
            return None
        if any(ord(c) < 0x20 for c in s):
            return None
        return s, end

    def rects(self):
        """所有「看起來像矩形」的 int32 四元組 → [(offset, (l, t, r, b)), …]（offset 遞增）。
        門檻刻意保守：左/下 >= 10 可擋掉 (1,315,100,18)、(0,511,256,0) 這類旗標位元組被讀成矩形；
        寬或高允許為 0（垂直線、文字錨點就是這樣），但兩者相加要 >= 60。"""
        out = []
        d = self.d
        for i in range(0, self.n - 16):
            l, t, r, b = struct.unpack_from('<4i', d, i)
            if (10 <= l <= r <= DESIGN_W + 600 and 10 <= b <= t <= DESIGN_H + 600
                    and (r - l) + (t - b) >= 60):
                out.append((i, (l, t, r, b)))
        return out

    def objects(self):
        """[{'off', 'name', 'attrs', 'rect'}]，照串流順序。
        rect＝該物件名之前、上一個物件名之後的最後一個合格四元組（多數物件就貼在名字前面 16 bytes，
        有 caption 等欄位時會隔開一段；第一次出現的物件類別會多一段類別宣告，可能完全沒有矩形）。"""
        d, n = self.d, self.n
        objs = []
        i = 0
        while i < n - 3:
            if d[i] == OBJ_MARK:
                r = self.rstr(i + 1, False)
                if r and len(r[0]) <= 64:
                    objs.append({'off': i, 'nend': r[1], 'name': r[0], 'attrs': {}, 'rect': None})
                    i = r[1]
                    continue
            i += 1
        # 屬性：每一項掛到「名字結束位置 <= 該項位置」的最後一個物件
        bounds = [o['nend'] for o in objs]
        import bisect
        p = -1
        while True:
            p = d.find(bytes([ATTR_MARK]), p + 1)
            if p < 0:
                break
            a = self.rstr(p + 1, False)
            if not a or len(a[0]) < 3 or not IDENT_RE.match(a[0]):
                continue
            key, q = a
            b = self.rstr(q, True)
            if b is None:
                continue
            j = bisect.bisect_right(bounds, p) - 1
            if j >= 0:
                objs[j]['attrs'].setdefault(key, b[0])
        # 矩形：在物件記錄的**尾端**，也就是「本物件名之後、下一個物件名之前」的最後一個合格四元組
        # （下一個物件名前 16 bytes 就是它）。最後一個物件沒有「下一個名字」，改以串流結尾當界線。
        # 這條綁定是實測定讞的，見檔頭「矩形綁定」——綁成「物件名之前」會整體錯位一個物件。
        rs = self.rects()
        roff = [x[0] for x in rs]
        for i, o in enumerate(objs):
            end = objs[i + 1]['off'] if i + 1 < len(objs) else n
            lo = bisect.bisect_left(roff, max(o['nend'], end - MAX_RECT_DIST))
            hi = bisect.bisect_right(roff, end - 16)
            if hi > lo:
                l, t, r, b = rs[hi - 1][1]
                # 超過畫面 1/4 面積的多半是背景面板（RoundRec 這類物件本工具不單獨認），不當成某台儀器的位置
                if (r - l) * (t - b) <= MAX_RECT_AREA * DESIGN_W * DESIGN_H:
                    o['rect'] = (l, t, r, b)
        return objs

    def all_strings(self):
        """串流內所有長度前綴字串（route=var 的補漏掃描用）。"""
        out = []
        i = 1
        while i < self.n - 1:
            r = self.rstr(i, False)
            if r and len(r[0]) >= 5:
                out.append(r[0])
                i = r[1]
            else:
                i += 1
        return out


def frac_rect(rect):
    """設計座標 (l, t, r, b)（y 軸向上）→ 左上為原點的 0~1 比例 (x, y, w, h)，各取 5 位小數。"""
    if not rect:
        return None, None, None, None
    l, t, r, b = rect
    x = l / float(DESIGN_W)
    y = (DESIGN_H - t) / float(DESIGN_H)
    w = (r - l) / float(DESIGN_W)
    h = (t - b) / float(DESIGN_H)
    cl = lambda v: round(min(1.0, max(0.0, v)), 5)  # noqa: E731
    return cl(x), cl(y), cl(w), cl(h)


# ---------------------------------------------------------------- {變數} 代入
def expand(s, attrs_ci, screen_vars_ci, unresolved):
    """'{UNIT}C{UNIT_NO}LAC50KC100' → 'G11.C10LAC50KC100'。
    代入順序：物件自身屬性 → 畫面變數（都不分大小寫）。代不出來的留原樣並記進 unresolved。"""
    for _ in range(MAX_EXPAND):
        if '{' not in s:
            break
        hit = [False]

        def sub(m):
            k = m.group(1).lower()
            v = attrs_ci.get(k)
            if v is None:
                v = screen_vars_ci.get(k)
            if v is None:
                unresolved[m.group(1)] += 1
                return m.group(0)
            hit[0] = True
            return v
        s2 = VAR_RE.sub(sub, s)
        if s2 == s or not hit[0]:
            return s2
        s = s2
    return s


def expand_multi(s):
    r"""多點簡寫展開：'G11LBB31BP001\002\003' → 'G11LBB31BP001 G11LBB31BP002 G11LBB31BP003'。
    每段數字取代基底的末 N 個字元；`.\tpLibrary\…` 這種路徑不受影響（反斜線後面不是數字）。"""
    if '\\' not in s:
        return s

    def rep(m):
        base, tail = m.group(1), m.group(2)
        parts = [base]
        for seg in tail.split('\\')[1:]:
            if 0 < len(seg) < len(base):
                parts.append(base[:-len(seg)] + seg)
        return ' '.join(parts)
    return MULTI_RE.sub(rep, s)


def extract_tags(s, tagset, unit_prefixes):
    """解析後字串 → 命中的 AMS 位號集合（規則見檔頭）。unit_prefixes 可給 str 或可迭代。"""
    out = set()
    if not s:
        return out
    if isinstance(unit_prefixes, str):
        unit_prefixes = (unit_prefixes,) if unit_prefixes else ()
    pfx = tuple(p for p in unit_prefixes if p)
    for tok in TOKEN_SPLIT.split(expand_multi(s)):
        if len(tok) < 5:
            continue
        T = tok.upper()
        cands = [T]
        if len(T) >= 8:
            cands.extend(p + T for p in pfx)
        for cand in cands:
            L = len(cand)
            while L >= 6:
                sub = cand[:L]
                if sub in tagset and (L == len(cand) or cand[L] in '_-'):
                    out.add(sub)
                    break
                L -= 1
    return out


# ---------------------------------------------------------------- AMS 位號集合
def load_ams(sqlite_path):
    """現行 AMS 位號 → 協定（HART／FF）。BlockAsgms.EventIdDayOut=49710、Blocks.BlockIndex=0。"""
    con = sqlite3.connect('file:%s?mode=ro' % sqlite_path.replace('\\', '/'), uri=True)
    rows = con.execute("""
        SELECT t.ExtBlockTag, p.Name
        FROM BlockAsgms a
        JOIN Blocks b ON b.BlockKey = a.BlockKey AND b.BlockIndex = 0
        JOIN ExtBlockTags t ON t.ExtBlockTagKey = a.ExtBlockTagKey
        JOIN Devices d ON d.DeviceKey = b.DeviceKey
        JOIN DeviceRevisions r ON r.AmsDevRevId = d.AmsDevRevId
        JOIN DeviceTypes dt ON dt.AmsDevTypeId = r.AmsDevTypeId
        JOIN MfrProtocols mp ON mp.MfrProtocolId = dt.MfrProtocolId
        JOIN DeviceProtocols p ON p.ProtocolId = mp.ProtocolId
        WHERE a.EventIdDayOut = ? AND b.DeviceKey >= 0
    """, (OPEN_DAY,)).fetchall()
    con.close()
    tags = {}
    for t, proto in rows:
        ct = clean_tag(t).upper()
        if ct:
            tags[ct] = proto or ''
    return tags


# ---------------------------------------------------------------- 畫面變數（hmi_nav.json，沒有就自己讀 CSV）
def load_nav(screens_dir, nav_json):
    """→ {檔名.cim: {'title_en','title_zh','nav':[[…]],'units':[…],'variables':[{…}],'aliases':[…]}}"""
    if nav_json and os.path.exists(nav_json):
        with open(nav_json, encoding='utf-8') as f:
            raw = json.load(f)
        out = {}
        for fn, v in raw.items():
            out[fn] = {'title_en': v.get('title_en') or '', 'title_zh': v.get('title_zh'),
                       'nav': v.get('nav') or [], 'units': v.get('units') or [],
                       'variables': v.get('variables') or [], 'aliases': list(v.get('file_aliases') or [])}
        return out, 'hmi_nav.json'
    # 退路：直接讀選單 CSV（title 只能用檔名）
    out = {}
    p = os.path.join(screens_dir, 'navigation', 'CIMNavigationMenuItemsStd.csv')
    for row in csv.DictReader(io.StringIO(read_text(p))):
        fn = (row.get('Cim Screen FileName') or '').strip()
        if not fn:
            continue
        e = out.setdefault(fn, {'title_en': '', 'title_zh': None, 'nav': [], 'units': [], 'variables': [], 'aliases': []})
        e['nav'].append([(row.get(k) or '').strip() for k in ('Block Name', 'Menu Item Name', 'Sub Menu Item Name', 'Item Name')])
        e['units'].append((row.get('Unit') or '').strip())
        parts = [x for x in (row.get('ScreenVariables') or '').split(';')]
        e['variables'].append({parts[i].strip(): parts[i + 1].strip() for i in range(0, len(parts) - 1, 2) if parts[i].strip()})
        if not e['title_en']:
            e['title_en'] = (row.get('Item Name') or '').strip()
    return out, 'CIMNavigationMenuItemsStd.csv'


# ---------------------------------------------------------------- 主流程
def scan_screen(path, nav_entry, tagset, stats):
    """一個 .cim → ([(tag, route, rect, ref, unit)], 物件統計)。"""
    try:
        of = olefile.OleFileIO(path)
    except Exception as e:                                   # noqa: BLE001
        stats['open_fail'].append('%s: %s' % (os.path.basename(path), e))
        return [], None
    try:
        names = {'/'.join(s).lower(): s for s in of.listdir()}
        if 'contents' not in names:
            stats['no_contents'] += 1
            return [], None
        data = of.openstream(names['contents']).read()
    finally:
        of.close()

    c = Contents(data)
    objs = c.objects()
    attr_keys = {k.lower() for o in objs for k in o['attrs']}   # 本畫面所有物件用過的屬性鍵（分辨未解析變數是哪一種）
    # 每列選單項目一組畫面變數；沒進選單的畫面用一組空變數（只能解出字面位號）
    var_sets = nav_entry['variables'] or [{}]
    units = nav_entry['units'] or ['']
    hits = []
    seen_strings = set()
    unres = Counter()
    for idx, sv in enumerate(var_sets):
        unit = units[idx] if idx < len(units) else ''
        # 機組前綴候選：選單列的 Unit 欄，加上畫面變數裡形如 G11／G12／C10／H11 的值
        uprefix = sorted({p for p in ([unit.rstrip('.').upper()] + [str(v).rstrip('.').upper() for v in sv.values()])
                          if UNITPFX_RE.match(p or '')})
        svci = {k.lower(): v for k, v in sv.items()}
        for o in objs:
            attrs = o['attrs']
            aci = {k.lower(): v for k, v in attrs.items()}
            found = {}
            for k, v in sorted(attrs.items()):
                if not v or len(v) < 5:
                    continue
                res = expand(v, aci, svci, unres)
                seen_strings.add(res)
                stripped = VAR_RE.sub('', v)
                # 整個值都是 {變數}（例 aliasSignal={device}）＝顯示給人看零資訊，排最後；其次才是「值本身帶位號字樣」
                tmpl = 0 if ALNUM_RE.search(stripped) else 1
                lit = 0 if LITERAL_RE.search(stripped) else 1
                for t in extract_tags(res, tagset, uprefix):
                    cur = found.get(t)
                    cand = (tmpl, lit, 0 if k.lower() in REF_KEYS else 1, len(v), k, v, res)
                    if cur is None or cand < cur:
                        found[t] = cand
            for t, (tmpl, _, _, _, k, v, res) in sorted(found.items()):
                # 只剩純樣板值可挑時（該物件沒有任何自帶位號字樣的屬性）補上代入後的結果，卡片才看得出是哪支位號對上的
                ref = '%s=%s' % (k, v) if not tmpl else '%s=%s（代入後 %s）' % (k, v, res[:60])
                hits.append((t, 'obj', o['rect'], ref, unit))
        # route=var：物件模型沒收到的字串補漏。
        # **機組前綴只用本列自己的 Unit**，不像 route=obj 那樣把整列變數裡所有像機組號的值都拿來試：
        # 這條路徑沒有物件屬性可以定機組，一列同時帶 G11 與 G12 時會把 'G{GUNIT_NO}HAP70BP001'
        # 同時生成 G11／G12 兩支，掛到錯的 unit 上（實測 HRSG_Blowdown_UX.cim 就是這樣）。
        own = (unit or '').rstrip('.').upper()
        own_pfx = (own,) if UNITPFX_RE.match(own) else ()
        for s in c.all_strings():
            if '{' not in s and not re.search(r'[A-Za-z]\d', s):
                continue
            res = expand(s, {}, svci, unres)
            if res in seen_strings:
                continue
            for t in extract_tags(res, tagset, own_pfx):
                hits.append((t, 'var', None, s, unit))
    # 未解析的 {變數}：每個畫面各記一次。分兩類——
    #   attr  本畫面別的物件有這個屬性鍵（元件引用上層群組／父物件的屬性，不是畫面變數缺了）
    #   var   畫面變數真的沒有這個鍵（選單列沒帶、或這個畫面沒進選單）
    for name in unres:
        stats['unresolved_attr' if name.lower() in attr_keys else 'unresolved_var'][name] += 1
    return hits, {'objects': len(objs), 'objects_with_rect': sum(1 for o in objs if o['rect']),
                  'objects_with_attrs': sum(1 for o in objs if o['attrs'])}


def load_pointdb(screens_dir, resolve_screen, tagset, stats):
    """tp_actPt_navPointSearchDbStd.csv → [(tag, screen, unit)]（無座標）。"""
    p = os.path.join(screens_dir, *POINT_CSV)
    out = []
    if not os.path.exists(p):
        return out
    for ln in read_text(p).splitlines():
        parts = [x.strip() for x in ln.split(',')]
        if len(parts) < 3 or not parts[2].lower().endswith('.cim'):
            continue
        point, unit, scr = parts[0], parts[1], parts[2]
        fn = resolve_screen(scr)
        if not fn:
            stats['unresolved_screens']['pointdb'][scr] += 1
            continue
        for t in extract_tags(point, tagset, unit.rstrip('.').upper()):
            out.append((t, fn, point, unit))
    return out


def load_dcdas_screens(dcdas_path, resolve_screen, tagset, stats):
    """控制器索引 → [(tag, screen, ref, unit)]（無座標；unit＝hmi_point.unit_prefix，與選單列的 Unit 欄同格式『BOPM1B.』）。
    優先用 signal-atlas 已經解好的 hmi_point 表（只取 source='display_screen'，navcsv 那一半本工具自己讀 CSV）；
    沒有該表的舊索引就退用 variable ⋈ io_point 自己解。"""
    out = []
    if not dcdas_path or not os.path.exists(dcdas_path):
        return out
    con = sqlite3.connect('file:%s?mode=ro' % dcdas_path.replace('\\', '/'), uri=True)
    has_hmi_point = bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hmi_point'").fetchone())
    if has_hmi_point:
        rows = con.execute("SELECT full_point, COALESCE(unit_prefix, ''), screen FROM hmi_point WHERE source = 'display_screen'").fetchall()
        con.close()
        for fp, up, scr in rows:
            fn = resolve_screen(scr)
            if not fn:
                stats['unresolved_screens']['dcdas'][scr] += 1
                continue
            for t in sorted(extract_tags(fp, tagset, up.rstrip('.').upper())):
                out.append((t, fn, fp, up))
        return out
    rows = con.execute("""
        SELECT v.display_screen, v.name, COALESCE(v.description, ''), COALESCE(p.device_tag, ''), COALESCE(p.connection, '')
        FROM variable v LEFT JOIN io_point p ON p.var_id = v.id
        WHERE COALESCE(v.display_screen, '') <> ''
    """).fetchall()
    con.close()
    for scr, name, desc, dtag, conn in rows:
        fn = resolve_screen(scr)
        if not fn:
            stats['unresolved_screens']['dcdas'][scr] += 1
            continue
        cands = []
        if dtag:
            cands.append(dtag)
        if conn:
            m = XQ_RE.match(conn.upper())
            cands.append(m.group(1) if m else conn)
        cands.append(name)
        if desc:
            cands.append(desc)
        for src in cands:
            ts = extract_tags(src, tagset, '')
            if ts:
                for t in sorted(ts):
                    out.append((t, fn, src, ''))      # 舊索引（無 hmi_point 表）沒有 unit_prefix 可帶
                break
    return out


def scan_excluded(screens_dir, root_files, tagset, tags_all, unit_prefixes):
    """根目錄以外的 .cim 也逐檔掃過字串，但**不進索引**，只回統計。

    子目錄裡的是元件面板與函式庫範本（customFaceplate／tpFpFaceplate／customLibrary／utilities／help／navigation），
    不是操作員可以導覽到的畫面，沒有選單列也沒有畫面變數，標了座標也沒地方給人看。要說「某支位號不在圖控畫面裡」
    就得有證據說這 225 個檔也看過了——這個函式就是那份證據（卡片與 CONTRACT 的數字都取自它，不是口頭聲明）。
    注意結果不保證是 0：實測有 12 支位號出現在元件面板的字串裡，重點是**這些位號是否已由根目錄畫面涵蓋**
    （實測 12/12 都有），有涵蓋才代表排除子目錄沒有漏人。

    回傳 {'files', 'dirs', 'strings', 'tag_hits', 'tags', 'ff_hits', 'ff_tags'}；位號比對用與索引相同的
    extract_tags（含「機組前綴＋詞」那條，所以點位名不帶機組前綴的寫法也算命中）。"""
    pfx = sorted({p for p in unit_prefixes if p})
    res = {'files': 0, 'dirs': {}, 'strings': 0, 'tag_hits': 0, 'tags': [], 'ff_hits': 0, 'ff_tags': []}
    hit = set()
    for dp, _dn, fns in os.walk(screens_dir):
        rel = os.path.relpath(dp, screens_dir).replace('\\', '/')
        if rel == '.':
            continue
        for fn in sorted(fns):
            if not fn.lower().endswith('.cim'):
                continue
            res['files'] += 1
            res['dirs'][rel] = res['dirs'].get(rel, 0) + 1
            try:
                of = olefile.OleFileIO(os.path.join(dp, fn))
            except Exception:                                 # noqa: BLE001
                continue
            try:
                names = {'/'.join(s).lower(): s for s in of.listdir()}
                if 'contents' not in names:
                    continue
                data = of.openstream(names['contents']).read()
            finally:
                of.close()
            for s in Contents(data).all_strings():
                res['strings'] += 1
                hit |= extract_tags(s, tagset, pfx)
    res['tags'] = sorted(hit)
    res['tag_hits'] = len(hit)
    res['ff_tags'] = sorted(t for t in hit if tags_all.get(t) == 'FF')
    res['ff_hits'] = len(res['ff_tags'])
    res['screens_root'] = len(root_files)
    res['screens_all'] = len(root_files) + res['files']
    return res


def main():
    ap = argparse.ArgumentParser(description='圖控 HMI 位號定位索引（見檔頭 docstring）')
    ap.add_argument('--screens', default=paths.HMI_SCREENS, help='Screens 目錄（預設 paths.HMI_SCREENS）')
    ap.add_argument('--sqlite', default=paths.AMS_SQLITE, help='AmsDb.sqlite（預設 paths.AMS_SQLITE）')
    ap.add_argument('--dcdas', default=paths.DCDAS_INDEX, help='signal-atlas 索引（預設 paths.DCDAS_INDEX）')
    ap.add_argument('--no-dcdas', action='store_true')
    ap.add_argument('--nav', default=os.path.join(paths.CARDWORK, 'hmi_nav.json'),
                    help='tools/db/hmi_nav.py 的輸出；不存在就直接讀 CIMNavigationMenuItemsStd.csv')
    ap.add_argument('--shots', default=paths.HMI_SHOTS, help='tools/db/hmi_shots.py 的輸出目錄（取 index.json 填 screens.img）')
    ap.add_argument('--no-shots', action='store_true')
    ap.add_argument('--no-excluded-scan', action='store_true',
                    help='不掃子目錄的元件面板／函式庫 .cim（省約 20 秒，但 stats.excluded_scan 會是 null，'
                         '卡片與 CONTRACT 的「另 N 個子目錄檔也掃過、命中者皆已由根目錄涵蓋」就沒有證據）')
    ap.add_argument('--out', default=paths.HMI_JSON, help='輸出 hmi.json（預設 paths.HMI_JSON）')
    ap.add_argument('--verify', metavar='FILE.cim', help='另印該畫面的物件／位號／座標明細')
    a = ap.parse_args()

    screens_dir = a.screens
    if not os.path.isdir(screens_dir):
        sys.exit('找不到 Screens 目錄：%s' % screens_dir)
    files = sorted(f for f in os.listdir(screens_dir) if f.lower().endswith('.cim'))
    sub = sum(len([f for f in fs if f.lower().endswith('.cim')]) for _, _, fs in os.walk(screens_dir)) - len(files)

    tags_all = load_ams(a.sqlite)
    tagset = set(tags_all)
    non_jk = {t for t in tagset if not t.startswith('JK')}
    print('AMS 現行位號 %d（JK* %d，母數 %d；HART %d／FF %d）' % (
        len(tagset), len(tagset) - len(non_jk), len(non_jk),
        sum(1 for t in non_jk if tags_all[t] == 'HART'), sum(1 for t in non_jk if tags_all[t] == 'FF')))

    nav, nav_src = load_nav(screens_dir, None if not a.nav else a.nav)
    print('畫面變數來源：%s（%d 個畫面有選單列）' % (nav_src, sum(1 for v in nav.values() if v['nav'])))

    shots = {}
    if not a.no_shots:
        sp = os.path.join(a.shots, 'index.json')
        if os.path.exists(sp):
            with open(sp, encoding='utf-8') as f:
                shots = json.load(f)

    # 檔名解析（別的索引 → 磁碟上的檔名）
    by_norm = defaultdict(set)
    for f in files:
        by_norm[norm_name(f)].add(f)
    alias_map = {}
    for fn, v in nav.items():
        for al in v.get('aliases') or []:
            alias_map[al.lower()] = fn
    lower = {f.lower(): f for f in files}

    def resolve_screen(n):
        if not n:
            return None
        b = os.path.basename(n.strip())
        if b in lower.values():
            return b
        if b.lower() in lower:
            return lower[b.lower()]
        if b.lower() in alias_map:
            return alias_map[b.lower()]
        c = by_norm.get(norm_name(b))
        return sorted(c)[0] if c and len(c) == 1 else None

    standalone = defaultdict(set)        # 各來源「自己找到幾台」（還沒做同畫面去重），給人跟各索引的原始數字對帳
    stats = {'unresolved_var': Counter(), 'unresolved_attr': Counter(), 'open_fail': [], 'no_contents': 0,
             'unresolved_screens': {'pointdb': Counter(), 'dcdas': Counter()}}
    entries = defaultdict(list)          # tag -> [entry]
    obj_tot = Counter()
    screens_out = {}
    for fn in files:
        ne = nav.get(fn) or {'title_en': '', 'title_zh': None, 'nav': [], 'units': [], 'variables': [], 'aliases': []}
        hits, ost = scan_screen(os.path.join(screens_dir, fn), ne, tagset, stats)
        if ost:
            for k, v in ost.items():
                obj_tot[k] += v
        pos = defaultdict(set)           # (tag, unit) -> {rect}
        best = {}
        for t, route, rect, ref, unit in hits:
            standalone[route].add(t)
            key = (t, unit)
            if rect:
                pos[key].add(rect)
            cur = best.get(key)
            rank = 0 if route == 'obj' else 1
            if cur is None or rank < cur[0]:
                best[key] = (rank, route, ref)
        for (t, unit), (_, route, ref) in best.items():
            rects = sorted(pos[(t, unit)])[:MAX_POS_PER_SCREEN] or [None]
            for rect in rects:
                x, y, w, h = frac_rect(rect)
                entries[t].append({'screen': fn, 'route': route, 'x': x, 'y': y, 'w': w, 'h': h, 'ref': ref, 'unit': unit})
        sh = shots.get(fn) or {}
        screens_out[fn] = {'title_en': ne['title_en'] or re.sub(r'_UX$', '', fn[:-4]).replace('_', ' '),
                           'title_zh': ne['title_zh'], 'nav': ne['nav'],
                           'units': sorted({u for u in ne['units'] if u}),
                           # img_canvas＝縮圖的畫布矩形 [l,t,w,h]（hmi_shots 的 index.json）。
                           # x/y 比例只有在畫布＝[0,0,1920,1080] 時才能直接乘縮圖寬高；
                           # 前端要自己檢查，不要假設（hmi_shots 對小面板會改用 bounds 當畫布）。
                           'img': sh.get('file'), 'img_canvas': sh.get('canvas'),
                           'img_w': sh.get('w'), 'img_h': sh.get('h'), 'w': DESIGN_W, 'h': DESIGN_H}

    have = {t: {(e['screen'], e['unit']) for e in v} for t, v in entries.items()}
    for t, fn, point, unit in load_pointdb(screens_dir, resolve_screen, tagset, stats):
        standalone['pointdb'].add(t)
        if (fn, unit) in have.get(t, ()) or any(e['screen'] == fn for e in entries.get(t, ())):
            continue
        entries[t].append({'screen': fn, 'route': 'pointdb', 'x': None, 'y': None, 'w': None, 'h': None, 'ref': point, 'unit': unit})
        have.setdefault(t, set()).add((fn, unit))
    if not a.no_dcdas:
        for t, fn, ref, unit in load_dcdas_screens(a.dcdas, resolve_screen, tagset, stats):
            standalone['dcdas'].add(t)
            if any(e['screen'] == fn for e in entries.get(t, ())):
                continue
            entries[t].append({'screen': fn, 'route': 'dcdas', 'x': None, 'y': None, 'w': None, 'h': None, 'ref': ref, 'unit': unit})
            have.setdefault(t, set()).add((fn, unit))

    # 子目錄（元件面板／函式庫）的 .cim：不進索引，但掃過字串留下「0 命中」的證據（scan_excluded 的 docstring）
    excl = None
    if not a.no_excluded_scan and sub:
        all_pfx = {str(u).rstrip('.').upper() for v in nav.values() for u in (v.get('units') or []) if u}
        all_pfx |= {str(x).rstrip('.').upper() for v in nav.values() for sv in (v.get('variables') or []) for x in sv.values()}
        excl = scan_excluded(screens_dir, files, tagset, tags_all, {p for p in all_pfx if UNITPFX_RE.match(p or '')})
        print('子目錄 %d 個 .cim（%s）也掃過：%d 條字串、AMS 位號命中 %d（FF %d）→ 不列入索引'
              % (excl['files'], '／'.join('%s %d' % (k, v) for k, v in sorted(excl['dirs'].items(), key=lambda kv: -kv[1])),
                 excl['strings'], excl['tag_hits'], excl['ff_hits']))

    by_tag = {}
    for t, v in entries.items():
        v.sort(key=lambda e: (e['screen'], e['unit'], e['route'], -1 if e['x'] is None else e['x'], -1 if e['y'] is None else e['y'], e['ref']))
        by_tag[t] = v

    # ------------------------------------------------------------ stats
    def cov(pred):
        return sum(1 for t in non_jk if pred(t))
    covered = {t for t in by_tag if t in non_jk}
    with_xy = {t for t in covered if any(e['x'] is not None for e in by_tag[t])}
    route_tags = defaultdict(set)
    for t in covered:
        for e in by_tag[t]:
            route_tags[e['route']].add(t)
    hart = {t for t in non_jk if tags_all[t] == 'HART'}
    ff = {t for t in non_jk if tags_all[t] == 'FF'}
    pct = lambda a_, b_: round(100.0 * a_ / b_, 1) if b_ else 0.0  # noqa: E731
    stats_out = {
        'ams_tags_total': len(tagset), 'ams_tags_jk': len(tagset) - len(non_jk), 'ams_tags_base': len(non_jk),
        'covered': len(covered), 'covered_pct': pct(len(covered), len(non_jk)),
        'covered_hart': len(covered & hart), 'covered_hart_pct': pct(len(covered & hart), len(hart)), 'hart_total': len(hart),
        'covered_ff': len(covered & ff), 'covered_ff_pct': pct(len(covered & ff), len(ff)), 'ff_total': len(ff),
        'covered_jk': len([t for t in by_tag if t.startswith('JK')]),
        'uncovered': len(non_jk) - len(covered), 'uncovered_hart': len(hart - covered), 'uncovered_ff': len(ff - covered),
        'with_xy': len(with_xy), 'with_xy_pct': pct(len(with_xy), len(non_jk)),
        'with_xy_of_covered_pct': pct(len(with_xy), len(covered)),
        # by_route＝同一位號同一畫面已去重後，各 route 實際留下幾台（obj 有座標，優先留）
        # by_route_standalone＝各來源自己找到幾台（未去重），用來跟各索引的原始數字對帳
        'by_route': {k: len(v) for k, v in sorted(route_tags.items())},
        'by_route_standalone': {k: len(v & non_jk) for k, v in sorted(standalone.items())},
        'entries': sum(len(v) for v in by_tag.values()),
        'entries_with_xy': sum(1 for v in by_tag.values() for e in v if e['x'] is not None),
        'screens_total': len(files), 'screens_subdir_skipped': sub, 'screens_all': len(files) + sub,
        # 子目錄的元件面板／函式庫 .cim：掃過字串但不進索引（scan_excluded）；
        # 命中的位號若全部已由根目錄畫面涵蓋，才能說「全部 .cim 都查過、排除子目錄沒有漏人」
        'excluded_scan': excl,
        'screens_with_tags': len({e['screen'] for v in by_tag.values() for e in v}),
        'screens_with_img': sum(1 for v in screens_out.values() if v['img']),
        'objects': obj_tot.get('objects', 0), 'objects_with_rect': obj_tot.get('objects_with_rect', 0),
        'objects_with_attrs': obj_tot.get('objects_with_attrs', 0),
        # 未解析 {變數}：[名稱, 有幾個畫面解不出來]。var＝畫面變數真的缺；attr＝元件引用父物件屬性（正常現象）
        'unresolved_vars_top10': [[k, v] for k, v in stats['unresolved_var'].most_common(10)],
        'unresolved_vars_distinct': len(stats['unresolved_var']),
        'unresolved_attrs_top10': [[k, v] for k, v in stats['unresolved_attr'].most_common(10)],
        'unresolved_attrs_distinct': len(stats['unresolved_attr']),
        'unresolved_screens': {k: [[n, c] for n, c in sorted(v.items())] for k, v in stats['unresolved_screens'].items()},
        'open_fail': sorted(stats['open_fail']), 'no_contents': stats['no_contents'],
        'design_w': DESIGN_W, 'design_h': DESIGN_H,
    }
    out = {'kind': 'hmi', 'generated_by': 'tools/db/hmi_index.py', 'screens': screens_out, 'by_tag': by_tag, 'stats': stats_out}
    txt = dumps(out)
    bad = ABS_PATH_RE.search(txt)
    if bad:
        sys.exit('輸出含本機絕對路徑：%r' % txt[max(0, bad.start() - 60):bad.start() + 60])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(txt)
    print('寫出 %s（%.1f MB）' % (os.path.basename(a.out), len(txt.encode('utf-8')) / 1048576.0))
    print('覆蓋 %d/%d (%.1f%%)：HART %d/%d、FF %d/%d；有座標 %d（佔覆蓋 %.1f%%）' % (
        stats_out['covered'], stats_out['ams_tags_base'], stats_out['covered_pct'],
        stats_out['covered_hart'], stats_out['hart_total'], stats_out['covered_ff'], stats_out['ff_total'],
        stats_out['with_xy'], stats_out['with_xy_of_covered_pct']))
    print('各 route 台數（去重後）：%s；各來源單獨：%s' % (stats_out['by_route'], stats_out['by_route_standalone']))
    print('畫面 %d（有位號 %d、有縮圖 %d）；物件 %d（有矩形 %d）' % (
        stats_out['screens_total'], stats_out['screens_with_tags'], stats_out['screens_with_img'],
        stats_out['objects'], stats_out['objects_with_rect']))
    print('未解析變數 top10：%s' % stats_out['unresolved_vars_top10'])

    if a.verify:
        fn = resolve_screen(a.verify) or a.verify
        print('\n=== %s ===' % fn)
        for t, v in sorted(by_tag.items()):
            for e in v:
                if e['screen'] == fn:
                    print('  %-22s %-7s x=%s y=%s w=%s h=%s  %s' % (t, e['route'], e['x'], e['y'], e['w'], e['h'], e['ref'][:60]))


if __name__ == '__main__':
    main()
