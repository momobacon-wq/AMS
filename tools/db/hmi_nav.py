# -*- coding: utf-8 -*-
r"""tools/db/hmi_nav.py — 圖控 HMI 畫面（GE CIMPLICITY／ActivePoint .cim）的「畫面身分證」：
每個畫面檔的標題、導覽選單路徑、機組、畫面變數、別名（給其他索引對得上的檔名拼法）與畫面上的標題文字。

為什麼需要：AMS 查詢卡要寫「這台儀器出現在哪個圖控畫面」，而各索引給的是檔名
（dcdas variable.display_screen、tp_actPt_navPointSearchDbStd.csv、物件屬性包）。
檔名對人沒有意義，而且各索引的拼法不一致（大小寫、有無 _UX、gtHA_Gen2 vs GTHA_GEN2…），
所以先把「檔名 → 人看得懂的名字＋選單路徑＋別名」整理成一份對照。

資料來源（皆唯讀，不改 Screens 下任何檔）
  1. navigation/CIMNavigationMenuItemsStd.csv   301 列＝導覽選單項目：Block / Menu / Sub Menu / Item Name /
     畫面檔名 / Unit / ScreenVariables（「鍵;值;鍵;值…」）。202 個畫面檔，同一畫面會被不同選單項目
     以不同變數組開啟（多機組），所以 nav／units／variables 三個陣列**逐列對齊、照 CSV 原順序**，不去重。
  2. logs/tp_actPt_navSetupIdentifiersStd.csv   358 列＝同一棵選單樹（含 IsMenu=True 的節點），用 NodeKey／ParentKey
     往上走就能重建階層；重建結果與該列的 M1..M4 欄位逐一相符（已交叉驗證），且 301 列的 Variables 與 (1) 的
     ScreenVariables 完全一致。比 (1) 多一個 StartupHome.cim——它直接掛在 Block1 下的 'HomeScrButton' 節點，
     那是**開機首頁按鈕的物件名、不是操作員看到的畫面名**，所以它的 title_conf 降為 low（詳見下方）。
     本工具只用它補 (1) 沒有的列。
  3. .cim 的 Contents 串流                      畫面上的文字。字串是「長度位元組＋UTF-16LE」；緊接在長度位元組前的
     兩個 int32 就是該文字物件的 (x, y)（設計座標，y 軸向上；全畫面約 25600x14400，與 hmi_shots.py 的
     1920x1080 裝置座標成比例——此比例由 tools/db/hmi_shots.py／任務 B 實測，本工具只照原值輸出）。
     取 y 在畫面頂部帶狀區（>= TOP_Y）的文字當「畫面上的標題候選」captions；左上角那一條（x <= LEFT_X）
     才有機會升格成 caption_en。
  4. languageTranslation/*.clm（LanguageMapper.clm 2,936 筆、tp_actPt_translateFp.clm 557 筆、
     tp_actPt_translateObjects.clm 77 筆）是 CIMPLICITY 的 XML 對照檔：<G K="英文"><T V="譯文"/></G>，
     語言由 <LgLst> 宣告。**這三個檔只有西班牙文（LCID 1547/3082）、日文（1057）、法文（1036），沒有中文**，
     所以 title_zh 一律 null（寧缺勿杜撰）。日文那 222 筆是漢字（例「燃料ガスシステム」「系統遮断器」）
     看起來像中文，但不是中文，不可當中文標題用。另以「對齊後的長度前綴字串」掃過 473 個 .cim，
     沒有任何一個含真正的中文字（詳見 --check 的輸出）。

標題怎麼定（title_src 會註明；title_conf 'high' 只給操作員選單 (1) 的名字，ident 樹獨有的降 low）
  nav       導覽選單的 Item Name（出現次數最多的那個）——操作員在圖控選單上看到的名字，優先採用。
  caption   不在選單裡的畫面，退而用畫面左上角的標題文字。
  filename  兩者都沒有，用檔名去底線美化（最低可信度）。
caption_en 只在下列情形才從 captions 升格（避免把複合畫面的第一塊面板標題當成整個畫面的標題）：
  (a) 頂部帶狀區裡只有一條靠左（x <= LEFT_X）的文字；或
  (b) 該文字正規化後與 Item Name 或檔名相符。
其餘情況 caption_en = null，但完整的 captions 清單（含座標）仍保留——那些是各面板的標題，
可以用來說「這台設備在畫面的哪一塊」。

用法
  py tools/db/hmi_nav.py                                  # 預設讀 paths.HMI_SCREENS，寫 %LOCALAPPDATA%\AMS\cardwork\hmi_nav.json
  py tools/db/hmi_nav.py --screens D:\Screens --out D:\hmi_nav.json
  py tools/db/hmi_nav.py --no-dcdas                       # 不讀控制器索引（alt_names 就少了 dcdas 那邊的檔名拼法）
  py tools/db/hmi_nav.py --check                          # 另外印：各索引檔名對得上幾個、.cim 中文掃描結果、3 個實例

輸出 {"<檔名.cim>": {...}}（只收 Screens 根目錄的 248 個畫面檔；子目錄的 225 個是元件庫與面板
  customFaceplate／tpFpFaceplate／customLibrary／navigation／help／utilities，不是可導覽的畫面，故排除）
  title_en     str        人看得懂的英文名（選單上的 Item Name 為優先）
  label        str        拿去顯示的名字：title_en 若被多個畫面共用（Overview、Protection…）就冠上選單名，例 'G11/G12 Overview'
  title_zh     null       中文（來源裡沒有中文，一律 null）
  title_src    str        'nav' | 'caption' | 'filename'
  title_conf   str        'high'（選單名）| 'medium'（畫面文字且與檔名對得上）| 'low'（畫面文字對不上檔名，或只能用檔名）
  nav          [[Block, Menu, SubMenu, Item], …]   逐列；沒進選單的畫面是 []
  units        [str, …]                            與 nav 逐列對齊（保留原樣的結尾點，例 'G11.'）
  variables    [{鍵:值, …}, …]                      與 nav 逐列對齊（ScreenVariables 展開）
  nav_src      [str, …]                            與 nav 逐列對齊：'navcsv' | 'identcsv'
  alt_names    [str, …]                            其他人看得懂的名字（別的 Item Name、caption、檔名美化）
  file_aliases [str, …]                            別的索引裡用到、指向本畫面的檔名拼法（dcdas／point CSV／大小寫變體）
  alias_tier   {別名: 'case'|'norm'|'loose'}        該別名是怎麼對上的：case 只差大小寫＝確定；norm 差 _UX／標點＝很可能；
                                                   loose 還差世代字 gen2＝**推論**（13 筆，查詢卡要標示，別當定讞）
  captions     [[x, y, text], …]                   畫面頂部帶狀區的文字（設計座標，y 軸向上），串流順序
  caption_en   str|null                            升格後的畫面標題文字
  thumbnail    bool                                有沒有 ThumbNail 串流（hmi_shots.py 能不能渲染）
  bytes        int                                 檔案大小
決定性輸出（鍵排序、無建置時間戳），且不寫入任何本機絕對路徑（結尾以 regex 自檢）。
"""
import argparse
import csv
import glob
import io
import json
import os
import re
import sqlite3
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

try:
    import olefile
except ImportError:
    sys.exit('缺 olefile：py -m pip install olefile')

NAV_CSV = ('navigation', 'CIMNavigationMenuItemsStd.csv')
IDENT_CSV = ('logs', 'tp_actPt_navSetupIdentifiersStd.csv')
POINT_CSV = ('navigation', 'tp_actPt_navPointSearchDbStd.csv')
CLM_DIR = 'languageTranslation'

# 設計座標（y 軸向上）＝ 28800 x 16200 twips（1920x1080 裝置像素 × 15），見 hmi_index.py 檔頭。
# 這裡只用來圈「頂部帶狀區」不做換算，但舊值 25600/14400 會把右側 11%、頂部 11% 的文字整個排除掉。
DESIGN_W, DESIGN_H = 28800, 16200
# y >= 這個值算畫面頂部帶狀區＝上緣約 29%。**不要改小**：實測畫面標題落在 y≈12842（上緣 20.7%），
# 若照「上緣 20%」設成 12960，209 個畫面的 captions 會整個清空、標題抓不到。
TOP_Y = 11500
LEFT_X = 4200                       # x <= 這個值算靠左（實測畫面標題幾乎都落在 x≈3340）
CAPTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 &/()\-\.,#'%]{2,58}$")
ABS_PATH_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|\\Users\\|/Users/|我的雲端硬碟')
CJK_RE = re.compile(r'[\u4e00-\u9fff]')
# 這些英文字串長得像標題但其實是元件/狀態文字，不當 caption 候選
CAPTION_STOP = {'alarm icon', 'custom tooltip', 'overview', 'auto', 'manual', 'standby', 'reset', 'close', 'open',
                'trend', 'help', 'home', 'back', 'print', 'exit', 'on', 'off'}


def dumps(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def read_text(path):
    """Screens 下的 csv 都是單位元組（ASCII/UTF-8，部分有 BOM）；cp1252 兜底。"""
    with open(path, 'rb') as f:
        b = f.read()
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode('latin-1')


def norm_name(n):
    """檔名正規化：去目錄、去 .cim、去尾綴 _UX、去非英數、小寫。"""
    n = os.path.basename((n or '').strip())
    n = re.sub(r'\.cim$', '', n, flags=re.I)
    n = re.sub(r'_UX$', '', n, flags=re.I)
    return re.sub(r'[^a-z0-9]', '', n.lower())


def norm_loose(n):
    """再寬一級：連 gen2 這個世代字也去掉（dcdas 有 gtHA_SIL_* 對 disk gtHA_Gen2_SIL_*）。"""
    return norm_name(n).replace('gen2', '')


def alias_tier(alias, key):
    """別名是「怎麼」對上磁碟檔名的——下游（查詢卡）要據此標示可信度，不要把推論當定讞。
    case  只差大小寫（HRSG_Reheater_UX.CIM）                     → 等同確定
    norm  差 _UX 尾綴／標點（ST_Control.cim ↔ ST_Control_UX.cim） → 很可能，但沒有文件直接證明
    loose 還差世代字 gen2（gtHA_SIL_EFFF_UX ↔ gtHA_Gen2_SIL_EFFF_UX）→ 推論，可能是別廠／舊版畫面
    """
    if alias.lower() == key.lower():
        return 'case'
    if norm_name(alias) == norm_name(key):
        return 'norm'
    return 'loose'


def norm_label(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def pretty_stem(fn):
    s = re.sub(r'\.cim$', '', fn, flags=re.I)
    s = re.sub(r'_UX$', '', s)
    return re.sub(r'\s+', ' ', s.replace('_', ' ')).strip()


# ---------------------------------------------------------------- .cim 解析
def cim_streams(path):
    of = olefile.OleFileIO(path)
    try:
        names = {'/'.join(s).lower(): s for s in of.listdir()}
        data = of.openstream(names['contents']).read() if 'contents' in names else b''
        return data, ('thumbnail' in names)
    finally:
        of.close()


def lp_ascii_strings(data, minlen=3):
    """Contents 內「長度位元組 + UTF-16LE」的純 ASCII 字串：先抓 UTF-16LE ASCII 連續段，
    再要求前一個位元組等於字元數（長度前綴）才算一條，避免切錯邊界。"""
    runs = []
    i, n = 0, len(data)
    cur, start = [], 0
    while i + 1 < n:
        if data[i + 1] == 0 and 32 <= data[i] < 127:
            if not cur:
                start = i
            cur.append(chr(data[i]))
            i += 2
        else:
            if len(cur) >= minlen:
                runs.append((start, ''.join(cur)))
            cur = []
            i += 1
    if len(cur) >= minlen:
        runs.append((start, ''.join(cur)))
    return [(st, s) for st, s in runs if st >= 1 and data[st - 1] == len(s)]


def top_captions(data):
    """頂部帶狀區的文字物件：長度位元組前的兩個 int32 就是 (x, y)。回傳 [[x, y, text], …] 串流順序。"""
    out, seen = [], set()
    for st, s in lp_ascii_strings(data, minlen=3):
        if st < 9 or not CAPTION_RE.match(s):
            continue
        x, y = struct.unpack_from('<ii', data, st - 9)
        if not (0 <= x <= DESIGN_W and TOP_Y <= y <= DESIGN_H):
            continue
        if s.strip().lower() in CAPTION_STOP:
            continue
        key = (x, y, s)
        if key in seen:
            continue
        seen.add(key)
        out.append([x, y, s.strip()])
    return out


def _plausible_char(cu):
    """一個 UTF-16 碼元看起來像不像「畫面上會出現的字」。
    排除 0x2000–0x2fff 等範圍很重要：ASCII 兩個空白等偶合位元組偏移一位元組後正好落在那裡，
    不排掉的話整份檔案都會被誤判成含中日文（例 '倀爀漀琀攀挀琀椀漀渀' 其實是 'Protection' 偏移一位元組）。"""
    return (0x20 <= cu < 0x7f or 0x4e00 <= cu <= 0x9fff or 0x3000 <= cu <= 0x30ff
            or 0xff01 <= cu <= 0xff60 or cu in (0xb0, 0xb1, 0xb2, 0xb3, 0xd7, 0xe1, 0xe9, 0xed, 0xf1, 0xf3, 0xfa, 0xfc))


def cim_has_cjk(data):
    """對齊掃描：長度前綴字串（允許非 ASCII BMP 字元、結尾要跟著 00 00）裡有沒有真正的中文字。
    回傳命中的 (offset, text) 清單——實測 473 個 .cim 全部為 0。"""
    hits = []
    n = len(data)
    i = 1
    while i < n - 1:
        L = data[i - 1]
        if 2 <= L <= 200 and i + 2 * L + 2 <= n and data[i + 2 * L] == 0 and data[i + 2 * L + 1] == 0:
            chars, good = [], True
            for k in range(L):
                cu = data[i + 2 * k] | (data[i + 2 * k + 1] << 8)
                if not _plausible_char(cu):
                    good = False
                    break
                chars.append(chr(cu))
            if good:
                t = ''.join(chars)
                # 偏移一位元組誤讀的特徵：該「中文字」的碼元有一個位元組是 0x00（例 'Protection' 的 'P\0' →
                # U+5000 '倀'）。真正的中文字兩個位元組都不是 0（例 系 U+7CFB）。要兩個以上才算，排除隨機二進位。
                solid = [c for c in t if CJK_RE.match(c) and (ord(c) & 0xff) and (ord(c) >> 8)]
                if len(solid) >= 2:
                    hits.append((i, t))
                i += 2 * L + 2
                continue
        i += 1
    return hits


# ---------------------------------------------------------------- 選單 CSV
def parse_vars(s):
    """ScreenVariables「鍵;值;鍵;值…」→ dict。奇數個 token（結尾多一個 ;）時最後一個鍵給空值。"""
    toks = [t for t in (s or '').split(';')]
    if toks and toks[-1] == '':
        toks.pop()
    d = {}
    for k in range(0, len(toks), 2):
        key = toks[k].strip()
        if not key:
            continue
        d[key] = toks[k + 1].strip() if k + 1 < len(toks) else ''
    return d


def load_nav(screens):
    rows = list(csv.DictReader(io.StringIO(read_text(os.path.join(screens, *NAV_CSV)))))
    out = []
    for r in rows:
        fn = (r.get('Cim Screen FileName') or '').strip()
        if not fn:
            continue
        out.append({'file': fn,
                    'path': [(r.get('Block Name') or '').strip(), (r.get('Menu Item Name') or '').strip(),
                             (r.get('Sub Menu Item Name') or '').strip(), (r.get('Item Name') or '').strip()],
                    'unit': (r.get('Unit') or '').strip(),
                    'vars': parse_vars(r.get('ScreenVariables')),
                    'src': 'navcsv'})
    return out


def load_ident(screens):
    """用 NodeKey/ParentKey 重建階層；只回傳有 NavFileName 的葉節點。"""
    rows = list(csv.DictReader(io.StringIO(read_text(os.path.join(screens, *IDENT_CSV)))))
    by_key = {}
    for r in rows:
        try:
            by_key[int(r['NodeKey'])] = r
        except (KeyError, TypeError, ValueError):
            continue
    out = []
    for r in rows:
        fn = (r.get('NavFileName') or '').strip()
        if not fn:
            continue
        chain, cur, guard = [], r, 0
        while cur is not None and guard < 12:
            chain.append((cur.get('Item Name') or '').strip())
            try:
                pk = int(cur.get('ParentKey'))
            except (TypeError, ValueError):
                break
            cur = by_key.get(pk)
            guard += 1
        chain.reverse()                      # [Block, Menu, (SubMenu), …, Item]
        # 一律「葉節點放最後一格」：4 層剛好，3 層沒有 SubMenu，2 層（直掛在 Block 下的按鈕，
        # 例 StartupHome.cim 的 HomeScrButton）連 Menu 都沒有，>4 層把中間層併進 SubMenu 格，
        # 不可以用 [:4] 截掉——那會把真正的項目名丟掉。
        if len(chain) >= 4:
            path = [chain[0], chain[1], '/'.join(chain[2:-1]), chain[-1]]
        elif len(chain) == 3:
            path = [chain[0], chain[1], '', chain[2]]
        elif len(chain) == 2:
            path = [chain[0], '', '', chain[1]]
        else:
            path = ['', '', '', chain[0] if chain else '']
        out.append({'file': fn, 'path': path, 'unit': (r.get('NavUnit') or '').strip(),
                    'vars': parse_vars(r.get('Variables')), 'src': 'identcsv'})
    return out


def load_point_screens(screens):
    """tp_actPt_navPointSearchDbStd.csv：每列「點位,機組,畫面檔」。只取畫面檔名集合。"""
    p = os.path.join(screens, *POINT_CSV)
    if not os.path.exists(p):
        return set()
    names = set()
    for ln in read_text(p).splitlines()[1:]:
        for q in ln.split(','):
            q = q.strip()
            if q.lower().endswith('.cim'):
                names.add(q)
    return names


def load_dcdas_screens(index_path):
    if not index_path or not os.path.exists(index_path):
        return set()
    con = sqlite3.connect('file:%s?mode=ro' % index_path.replace('\\', '/'), uri=True)
    try:
        q = "select distinct display_screen from variable where display_screen is not null and display_screen<>''"
        return {r[0].strip() for r in con.execute(q) if r[0] and r[0].strip().lower().endswith('.cim')}
    finally:
        con.close()


def load_clm_langs(screens):
    """各 .clm 宣告了哪些語言（判斷有沒有中文對照）。"""
    out = {}
    for p in sorted(glob.glob(os.path.join(screens, CLM_DIR, '*.clm'))):
        try:
            root = ET.fromstring(read_text(p))
        except ET.ParseError as e:
            out[os.path.basename(p)] = {'error': str(e)}
            continue
        langs = [{'lcid': lg.get('LCID'), 'name': lg.get('Name')} for lg in root.iter('Lg')]
        n_cjk = sum(1 for g in root.iter('G') for t in g.findall('T') if CJK_RE.search(t.get('V') or ''))
        out[os.path.basename(p)] = {'langs': langs, 'entries': len(list(root.iter('G'))), 'entries_with_cjk': n_cjk}
    return out


# ---------------------------------------------------------------- 主流程
def build(screens, dcdas_index, want_cjk_scan=False):
    files = sorted(glob.glob(os.path.join(screens, '*.[cC][iI][mM]')), key=lambda p: os.path.basename(p).lower())
    disk = [os.path.basename(p) for p in files]
    by_norm, by_loose = defaultdict(set), defaultdict(set)
    for fn in disk:
        by_norm[norm_name(fn)].add(fn)
        by_loose[norm_loose(fn)].add(fn)

    def resolve(name):
        """外部索引的檔名拼法 → 磁碟上的檔名（唯一解才算）。回傳 (檔名, 比對層級) 或 (None, 原因)。"""
        nm = (name or '').strip()
        if not nm:
            return None, 'empty'
        if nm in set(disk):
            return nm, 'exact'
        c = by_norm.get(norm_name(nm), set())
        if len(c) == 1:
            return next(iter(c)), 'norm'
        if len(c) > 1:
            return None, 'ambiguous'
        c = by_loose.get(norm_loose(nm), set())
        if len(c) == 1:
            return next(iter(c)), 'loose'
        return None, 'ambiguous' if c else 'missing'

    nav_rows = load_nav(screens)
    ident_rows = load_ident(screens)
    # ident 只用來補 nav CSV 沒有的（同 檔名+路徑+機組 視為同一列）
    have = {(r['file'], tuple(r['path']), r['unit']) for r in nav_rows}
    extra = [r for r in ident_rows if (r['file'], tuple(r['path']), r['unit']) not in have]
    rows = nav_rows + extra

    rows_by_file = defaultdict(list)
    unresolved_nav = []
    for r in rows:
        key, how = resolve(r['file'])
        if key is None:
            unresolved_nav.append((r['file'], how))
            continue
        rows_by_file[key].append(r)

    # 別的索引用到的檔名拼法 → file_aliases（並記下每個別名是怎麼對上的，見 alias_tier）
    aliases = defaultdict(dict)
    ext_stat = {}
    for label, names in (('point_csv', load_point_screens(screens)), ('dcdas', load_dcdas_screens(dcdas_index))):
        hit, miss, tiers = 0, [], Counter()
        for nm in sorted(names):
            key, how = resolve(nm)
            if key is None:
                miss.append(nm)
                continue
            hit += 1
            tiers[how] += 1
            if nm != key:
                aliases[key][nm] = alias_tier(nm, key)
        ext_stat[label] = {'total': len(names), 'resolved': hit, 'tiers': dict(tiers), 'unresolved': sorted(miss)}

    # Item Name 常常只是「Overview」「Protection」這種在多個畫面重複的字，單獨拿出來當名字分不出是誰的，
    # 所以先算每個 Item Name 被幾個畫面用到，重複的就在前面冠上選單名（例 G11/G12 Overview）。
    item_owners = defaultdict(set)
    for key, rs in rows_by_file.items():
        for r in rs:
            if r['path'][3]:
                item_owners[r['path'][3]].add(key)

    out = {}
    cjk_hits = {}
    for p, fn in zip(files, disk):
        data, thumb = cim_streams(p)
        caps = top_captions(data)
        if want_cjk_scan:
            h = cim_has_cjk(data)
            if h:
                cjk_hits[fn] = h[:5]

        mine = rows_by_file.get(fn, [])
        items = [r['path'][3] for r in mine if r['path'][3]]
        title_en, title_src = None, None
        if items:
            title_en = Counter(items).most_common(1)[0][0]
            title_src = 'nav'

        # caption 升格：唯一靠左的頂部文字，或與 Item Name／檔名相符
        left = [c for c in caps if c[0] <= LEFT_X]
        caption_en = None
        if len(left) == 1:
            caption_en = left[0][2]
        else:
            want = {norm_label(title_en or ''), norm_name(fn)} - {''}
            for c in caps:
                nl = norm_label(c[2])
                if nl and any(w and (w in nl or nl in w) for w in want):
                    caption_en = c[2]
                    break
        if title_en is None:
            if caption_en:
                title_en, title_src = caption_en, 'caption'
            else:
                title_en, title_src = pretty_stem(fn), 'filename'
        # 可信度：選單名最可信；畫面文字要跟檔名對得上才算中等（'GTyy'、'LU001'、'RUNBACKS' 這種就是 low）
        if title_src == 'nav':
            # 只有 CIMNavigationMenuItemsStd.csv（＝操作員真的在圖控選單上看到的那棵樹）才算 high。
            # 只出現在 ident 樹的（目前只有 StartupHome.cim 的 'HomeScrButton'）是節點／按鈕的物件名，
            # 不是操作員看到的畫面名，所以降為 low。
            title_conf = 'high' if any(r['src'] == 'navcsv' for r in mine) else 'low'
        elif title_src == 'caption':
            stem_toks = {t for t in re.split(r'[_\s]+', re.sub(r'\.cim$|_UX$', '', fn, flags=re.I)) if len(t) > 2}
            nl = norm_label(title_en)
            title_conf = 'medium' if any(norm_label(t) in nl for t in stem_toks) else 'low'
        else:
            title_conf = 'low'

        # label：拿去顯示在查詢卡上的名字。Item Name 若被多個畫面共用就冠上選單名（多機組會變成 G11/G12 Overview）
        label = title_en
        if title_src == 'nav' and len(item_owners.get(title_en, ())) > 1:
            menus, subs = [], []
            for r in mine:
                if r['path'][3] != title_en:
                    continue
                if r['path'][1] and r['path'][1] not in menus:
                    menus.append(r['path'][1])
                if r['path'][2] and r['path'][2] not in subs:
                    subs.append(r['path'][2])
            head = '/'.join(menus) if menus else ''
            mid = '/'.join(subs) if subs else ''
            label = ' '.join(x for x in (head, mid, title_en) if x)

        alt = {i for i in items if i != title_en}
        if caption_en and caption_en != title_en:
            alt.add(caption_en)
        ps = pretty_stem(fn)
        if norm_label(ps) != norm_label(title_en):
            alt.add(ps)
        fal = {a: t for a, t in aliases.get(fn, {}).items() if a != fn}

        out[fn] = {
            'title_en': title_en,
            'title_zh': None,
            'label': label,
            'title_src': title_src,
            'title_conf': title_conf,
            'nav': [r['path'] for r in mine],
            'units': [r['unit'] for r in mine],
            'variables': [r['vars'] for r in mine],
            'nav_src': [r['src'] for r in mine],
            'alt_names': sorted(alt),
            'file_aliases': sorted(fal),
            'alias_tier': dict(sorted(fal.items())),
            'captions': caps,
            'caption_en': caption_en,
            'thumbnail': thumb,
            'bytes': os.path.getsize(p),
        }

    stats = {
        'screens': len(out),
        'with_nav': sum(1 for v in out.values() if v['nav']),
        # with_menu 才是「操作員選單上點得到」的數；with_nav 多算了只在 ident 樹的 StartupHome.cim
        'with_menu': sum(1 for v in out.values() if 'navcsv' in v['nav_src']),
        'alias_tier': dict(Counter(t for v in out.values() for t in v['alias_tier'].values())),
        'nav_rows': sum(len(v['nav']) for v in out.values()),
        'title_src': dict(Counter(v['title_src'] for v in out.values())),
        'title_conf': dict(Counter(v['title_conf'] for v in out.values())),
        'with_caption': sum(1 for v in out.values() if v['caption_en']),
        'with_captions_list': sum(1 for v in out.values() if v['captions']),
        'with_thumbnail': sum(1 for v in out.values() if v['thumbnail']),
        'with_title_zh': sum(1 for v in out.values() if v['title_zh']),
        'multi_row_screens': sum(1 for v in out.values() if len(v['nav']) > 1),
        'unresolved_nav_rows': unresolved_nav,
        'external': ext_stat,
        'clm': load_clm_langs(screens),
    }
    if want_cjk_scan:
        # 「沒有中文」要對全部 473 個 .cim 成立，不能只掃根目錄那 248 個：
        # 子目錄（customFaceplate／tpFpFaceplate／customLibrary…）的 225 個也要掃。
        sub = [p for p in sorted(glob.glob(os.path.join(screens, '**', '*.[cC][iI][mM]'), recursive=True))
               if os.path.dirname(p) != os.path.normpath(screens)]
        for p in sub:
            h = cim_has_cjk(cim_streams(p)[0])
            if h:
                cjk_hits[os.path.relpath(p, screens)] = h[:5]
        stats['cim_cjk_candidates'] = cjk_hits
        stats['cim_cjk_scanned'] = len(files) + len(sub)
    return out, stats


def main(argv=None):
    try:                                     # 本機 console 是 cp950，不轉就印成亂碼（同 hmi_shots.py）
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description='圖控 HMI 畫面導覽資訊（標題／選單路徑／機組／畫面變數／別名）')
    ap.add_argument('--screens', default=paths.HMI_SCREENS, help='Screens 目錄（預設 paths.HMI_SCREENS）')
    ap.add_argument('--out', default=os.path.join(paths.CARDWORK, 'hmi_nav.json'))
    ap.add_argument('--dcdas', default=paths.DCDAS_INDEX, help='控制器索引 index.sqlite（取 display_screen 的檔名拼法）')
    ap.add_argument('--no-dcdas', action='store_true')
    ap.add_argument('--check', action='store_true', help='另印：.cim 中文掃描、各索引檔名對應率、3 個實例')
    a = ap.parse_args(argv)

    if not os.path.isdir(a.screens):
        sys.exit('找不到 Screens 目錄：%s' % a.screens)
    dcdas = '' if a.no_dcdas else a.dcdas
    if dcdas and not os.path.exists(dcdas):
        sys.exit('找不到控制器索引 %s（不需要就加 --no-dcdas）' % dcdas)

    out, stats = build(a.screens, dcdas, want_cjk_scan=a.check)
    body = dumps(out)
    bad = ABS_PATH_RE.search(body)
    if bad:
        sys.exit('輸出含本機絕對路徑，請修正：%r' % body[max(0, bad.start() - 60):bad.end() + 60])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(body)

    print('畫面 %d 個（Screens 根目錄 .cim）→ %s  %.0f KB' % (stats['screens'], a.out, len(body) / 1024))
    print('  有選單路徑 %d（其中操作員選單 %d，另 %d 只在 ident 樹）  選單列 %d；同畫面多列 %d' % (
        stats['with_nav'], stats['with_menu'], stats['with_nav'] - stats['with_menu'],
        stats['nav_rows'], stats['multi_row_screens']))
    print('  標題來源 %s  可信度 %s  別名分級 %s' % (stats['title_src'], stats['title_conf'], stats['alias_tier']))
    print('  caption 升格 %d／有頂部文字 %d　有 ThumbNail %d　有中文標題 %d' % (
        stats['with_caption'], stats['with_captions_list'], stats['with_thumbnail'], stats['with_title_zh']))
    for k, v in stats['external'].items():
        print('  %s 檔名：%d 個，對上 %d（%s），對不上 %d' % (k, v['total'], v['resolved'], v['tiers'], len(v['unresolved'])))
    if stats['unresolved_nav_rows']:
        print('  選單列指向磁碟上沒有的畫面：%s' % stats['unresolved_nav_rows'])

    if a.check:
        print('\n--- .clm 語言宣告（有沒有中文對照）---')
        for fn, info in stats['clm'].items():
            print('  %-32s %s  條目 %s  含 CJK 譯文 %s' % (fn, info.get('langs'), info.get('entries'), info.get('entries_with_cjk')))
        print('--- .cim 中文掃描（對齊後的長度前綴字串）---')
        if not stats.get('cim_cjk_candidates'):
            print('  已掃 %d 個 .cim（根目錄 %d ＋ 子目錄元件庫），0 個含中文字' % (stats['cim_cjk_scanned'], stats['screens']))
        else:
            for fn, h in list(stats['cim_cjk_candidates'].items())[:20]:
                print('  %s %s' % (fn, h))
        for v in stats['external'].values():
            if v['unresolved']:
                print('--- 對不上的檔名（%d）---\n  %s' % (len(v['unresolved']), '; '.join(v['unresolved'])))
        print('--- 別名分級（loose＝推論，查詢卡要標示）---')
        for lvl in ('loose', 'norm'):
            got = ['%s ← %s' % (fn, a) for fn, v in sorted(out.items()) for a, t in sorted(v['alias_tier'].items()) if t == lvl]
            print('  %s（%d）：%s' % (lvl, len(got), '; '.join(got) if lvl == 'loose' else '; '.join(got[:4]) + ' …'))
        print('\n--- 3 個實例 ---')
        for fn in ('BOP_Feed_Water.cim', 'gtHA_Gen2_Overview_UX.cim', 'BOPE_UPS_GT1.cim'):
            if fn in out:
                d = dict(out[fn])
                d['variables'] = ['（%d 組）' % len(d['variables'])] if len(d['variables']) > 2 else d['variables']
                d['captions'] = d['captions'][:4]
                print('%s\n  %s' % (fn, dumps(d)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
