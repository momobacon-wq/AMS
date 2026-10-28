# -*- coding: utf-8 -*-
"""02_設備查詢卡 附加資料（card aux）：合併 AMS DB 補充與工程文件比對結果，依 alias 分塊輸出給前端按需載入。

Usage:  py tools/db/build_card_aux.py <cardwork_dir> docs/db/data [--chunk-kb 300] [--no-stamp] [--dcdas <index.sqlite>|--no-dcdas]
                                      [--docsearch <docsearch.json>|--no-docsearch] [--drive-map <drive_map.json>|--no-drive-map]
        py tools/db/build_card_aux.py --recompare docs/db/data [--dcdas …] [--docsearch …]
        （cardwork 不在手邊：讀已發布的 card/*.json 只重算 DCS 比對；有給 docsearch.json 就換掉 sec.docsearch，有 drive_map 就補 url）

輸入（<cardwork_dir>，各產生器輸出；不在 repo 內）：
  ams.json       ← tools/db/card_ams_extra.py      （AMS DB：同步、最後修改/DCS 寫入、位號歷程、設備補充、警報、FF 診斷）
  terminal.json  ← tools/db/docmap_terminal.py     （DCS 端子表 HTx-1-IMI01-A0001 IO_Signal）
  instlist.json  ← tools/db/docmap_instlist.py     （儀器清單 BOP/HRSG/GT/ST）
  eomr.json      ← tools/db/docmap_eomr.py         （出廠校正證書 EOMR）
  docindex.json  ← tools/db/docmap_docindex.py     （PDF 文件索引：P&ID、Hook-up、規格表…的頁碼）
  docsearch.json ← tools/db/docmap_docsearch.py    （文件全文檢索：hst-docsearch FTS 索引以位號／序號命中的文件與頁碼；
                                                    預設讀 %LOCALAPPDATA%\\AMS\\cardwork\\docsearch.json，`--docsearch` 可指定、`--no-docsearch` 略過；兩種模式都收）
  hmi.json       ← tools/db/hmi_index.py           （圖控 HMI 畫面位置：位號 → 畫面檔＋畫面上的 0~1 座標；`--hmi`／`--no-hmi`）
  hmi_shots/     ← tools/db/hmi_shots.py           （畫面縮圖 webp＋index.json；`--hmi-shots`，缺席時只有畫面名稱沒有影像）
  hmi_nav.json   ← tools/db/hmi_nav.py             （逐列選單路徑／畫面標題；`--hmi-nav`，用來挑「以這台的機組開啟」的那一列導覽路徑）
  pid.json       ← tools/db/pid_index.py           （P&ID 圖面位置：位號 → 圖紙（PDF＋頁）＋轉正後圖面上的 0~1 座標；`--pid`／`--no-pid`，預設 paths.PID_JSON）
  pid_shots/     ← tools/db/pid_shots.py           （被引用的圖紙影像 <slug>.webp＋index.json；`--pid-shots`，預設 paths.PID_SHOTS。
                                                    **缺 index.json 或任何一張被引用的圖紙沒有影像都以非 0 結束**，不像 hmi_shots 缺席時靜默降級）
P&ID 圖面位置（CONTRACT.md「P&ID 圖面位置」）：每台產生 `sec.pid = {rows: [[欄位, 值, lvl, 來源字串, extra]]}`，每張圖紙一組 5 列
（P&ID 圖面／圖面頁次／所在位置／圖上標示／對應方式），組的順序照 pid.json；lvl＝`doc`（文字層命中且圖上就是本台或不分機組）或 `inferred`
（典型圖／迴路／同型各台，以及所有 OCR 命中）。每列 extra 帶 {s: 圖紙鍵, g: 組號}，第一列再帶 d（index.docs 的鍵＝這張圖自己的那份 PDF）、
p／n（PDF 頁次／總頁數）、img、marks（[中心 x, 中心 y, 框寬, 框高]，轉正後影像的 0~1 比例，marks[0]＝「所在位置」描述的那處）、
drawn（圖上畫的字）、unit（圖上畫的機組）、rel、how、conf（OCR 才有）、zone。圖紙影像包成 `card/pid/<slug>.json`＝`{w,h,mime,b64}`
（每張圖紙一檔，所有畫在上面的位號共用；分塊與 index 都通過自檢之後才清空 card/pid/ 重寫），清單與圖紙中繼資料放 `card/index.json` 的 `pid`（`files` 給 verify_encrypted 認）。
2026-10-10 六組獨立稽核之後（位置都對，錯在「這一處算什麼」）：
  * pid.json 每筆命中的 note 是代碼——0 儀器符號旁的標籤、1 圖上註記或表格（儀器清單）、2 跨圖訊號旗標、3 空氣分配圖的用氣點、4 迴路詳圖（TYPICAL 小圖）。
    1～4 是「引用」，不是儀器符號的位置：排在符號標籤之後；「所在位置」「圖上標示」兩列與第一列 extra 的 note／notes 都講明（pid_rows）。
    一支位號在任何一張圖上都沒有符號標籤時直說「圖上沒有找到這支位號的儀器符號」。
  * 「與本台位號相同」只在圖上的字正規化後真的等於位號時才寫；ocr-fix（相近字元校正後才對上）改寫 OCR 原本讀成什麼（hit 的 raw）。
  * OCR 的紅字警語看整張圖各處標記的最低辨識信心（extra.conf_min／confs），不是只看 ①。
  * 載入時多一道關卡（pid_shared_boxes）：同一張圖的同一個標籤被兩支不相干的位號認領（不是機組雙胞胎、`_01` 重複名稱、同型各台或合寫的標籤）
    就以非 0 結束——那代表 pid_index 把別的儀器算了進來（實例：S10MAV01BP272／BP272C 互掛），建置機分不出誰對，不發布。
每份 PDF 以自己的文件庫相對路徑登記進 index.docs（`pid|<編號>|<版次>`），Drive 連結**只給這一份檔本身**：drive_map 沒有它就不附連結並計入
`stats.pid.no_url`（不改連其他版次——位置是從這一版讀出來的）。
圖控 HMI（CONTRACT.md「圖控 HMI 畫面位置」）：每台產生 `sec.hmi = {rows: [[欄位, 值, lvl='hmi', 來源字串, extra]]}`，每個（畫面, 選單機組）一組 4 列
（圖控畫面／導覽路徑／所在位置／對應方式），第一列的 extra 帶 nav、img、marks（[中心 x, 中心 y, 框寬, 框高]，0~1 比例、左上為原點）；
有設備對應到又有影像的畫面，縮圖包成 `card/hmi/<畫面名>[__<選單機組>].json`＝`{w,h,mime,b64}`（**走既有 *.json 加密路徑，不另造加密**；
執行時截圖逐選單機組各一檔、設計時 ThumbNail 整個畫面一檔），
清單與畫面中繼資料放 `card/index.json` 的 `hmi`（含 `files`，verify_encrypted 以它認得這些密文不是孤兒）。

另讀 docs/db/data/sheets/03.json（alias 列序、位號）與 13.json（AMS 量程現值，DCS 基準比對用），
以及 signal-atlas 的控制器索引 %LOCALAPPDATA%\\dcdas\\index.sqlite（ToolboxST checkout 的 I/O 組態；不進 repo；`--dcdas` 可指定，沒有就略過此來源），
與 tools/db/drive_map.py 的 路徑→Google 雲端硬碟檔案 ID 對照 %LOCALAPPDATA%\\AMS\\drive_map.json（`--drive-map`；有就替 index.docs 每份文件補 url，前端把數值變成連結）。

輸出（CONTRACT.md「card aux」）：
  docs/db/data/card/index.json   {version:2, parts, alias:{alias: 塊號}, src_defs, searched:{kind:[...]}, source_stats, stats, compare_rule}（只留全廠 alias map 等小東西）
  docs/db/data/card/aux-NN.json  {part, by_alias:{alias:{sec:{...}, compare:[...], flags:{...}}}, docs:{key:{...}}, doc_no:{編號: key}}（docs／doc_no 只帶該塊用到的子集）
並重算 manifest.build（含 card/*.json）後重新 stamp docs/db/index.html（tools/db/extract_db.py 的 stamp）。
外部索引（dcdas／docsearch／hmi／pid／drive_map）任一缺席且沒給對應 --no-* 旗標時以非 0 結束（rebuild.py 因此中止並走加密回滾），不再靜默略過；
這個檢查在動到資料目錄之前（pid 另外核對圖紙鍵、影像檔與 pid_shots 是否同步，見 load_pid）。

DCS 基準比對（compare）：量程上/下限的基準依序＝(1) 控制器現行 I/O 組態（dcdas：該位號類比輸入通道的 Low/High Value，sec.dcdas）
→ (2) AMS 事件中該參數最新一次「值有改變」的 Cat28 外部主機寫入（dcs_writes URV/LRV；只有寫入事件晚於該控制器 checkout 日期
（dcdas controller.last_mod，索引建立日只是備援）、或沒有控制器資料時才當基準）
→ (3) DCS 端子表 DEVICE_LO/HI（設計文件）。（2026-09-24 調整：G12HAP70BT001 的 DCS 寫入 160 之後被人工改回 200、控制器也是 200，
寫入事件只是歷史，不該讓一致的來源被標 ⚠。）
同位號對到多個類比輸入通道時，基準優先取控制器與位號機組前綴一致者；各通道量程不一時其餘通道各列一列 others kind='dcdas_ch'、flags.cmp.dcdas_multi='warn'。
其餘來源——AMS 現值（13 表 LRV/URV/單位）、DCS 寫入事件（只比寫入的那一端）、端子表、儀器清單、EOMR——逐一與基準比對：
同單位者 7 位有效數字完全相同才 ok，差在 ±0.5% span 內為 near（≈ 近似，請確認），其餘 mismatch；需換算單位者（°C/°F/K、Pa/kPa/MPa/mbar/bar/psi/mmH2O/inH2O/inHg/mmHg、
mm/cm/m/in、%）維持 ±0.5% span 內為 ok（文件常寫圓整值），無法換算 → unit_mismatch。
EOMR 證書「序號與 AMS 相符」＝否（非本台）者不比較，只在 compare.others 列一筆 status='ref_only' 供參考；AMS 未寫入序號者仍比對但註明無法確認為同一台。
全廠比對（write_output 結尾會印「AMS 現值 vs 控制器組態：完全相同／近似／不符」三段）：2026-09-26 重算，有控制器基準且 AMS 有現值的 1,240 台中
完全相同 1,128（91%）、近似 22（2%）、不符 53（4%）、單位不明／不同未比較 37；端子表有 37% 與控制器不同（所以端子表降為第 3 順位）。
決定性輸出（無時間戳）；不寫入任何本機絕對路徑（最後以 regex 自檢）。

--recompare：cardwork（ams/terminal/instlist/eomr/docindex.json）已不在手邊時，讀已發布的 card/*.json，保留各文件區段，只重算
sec.dcdas、sec.docsearch（有給時）、sec.hmi 與畫面影像（有給時；`--no-hmi` 保留上次發布的）、sec.pid 與圖紙影像（有給時；`--no-pid` 保留上次發布的
sec.pid／index.pid／card/pid/*.json／stats.pid）、compare 與 flags.cmp，並補 Drive url。限制：舊資料沒有 compare 的設備（既無 DCS 寫入也無端子表），儀器清單／EOMR 的量程數值已不可得，
只比 AMS 現值與控制器組態；要完整比對請重跑各產生器後用一般模式。
"""
import os, sys, json, re, math, glob, argparse, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))  # tools/encrypt_data.py
import paths  # noqa: E402  （tools/db/paths.py：PID_JSON／PID_SHOTS 的預設值，AMS_CARDWORK 可覆寫；import 沒有副作用）

FLT_MIN = 1.1754943508222875e-38
SRC_DEFS = {
    'raw': {'label': '原始', 'desc': '直接取 AMS 資料庫某一欄（可經 JOIN）'},
    'decoded': {'label': '解碼', 'desc': '以固定規則換算：時間、字串切段、二進位 int32/float32/UTF-16、FF hex、碼表'},
    'inferred': {'label': '推論', 'desc': '經驗規則、寫死的對照表、外部對照檔或機組範本推論（非資料庫/文件直接記載）'},
    'doc': {'label': '文件', 'desc': '設計文件（DCS 端子表、儀器清單、P&ID、Hook-up…）：「應該是什麼」'},
    'factory': {'label': '出廠', 'desc': '製造商出廠紀錄（EOMR 校正證書）：「出廠時是什麼」'},
    'ctrl': {'label': '控制器', 'desc': '控制器組態 checkout 快照（ToolboxST I/O 組態，經 signal-atlas 索引）：「控制器現在設定是什麼」；各控制器 checkout 日期見來源'},
    'hmi': {'label': '圖控', 'desc': '圖控 HMI 畫面檔（GE CIMPLICITY／ActivePoint .cim，唯讀原檔）解析：這台儀器畫在哪一頁、畫面上哪個位置'},
}
KIND_LABEL = {'dcdas': 'DCS 控制器組態', 'terminal': 'DCS 端子表', 'instlist': '儀器清單', 'eomr': '出廠證書 EOMR', 'docindex': '文件索引', 'docsearch': '文件全文檢索', 'hmi': '圖控 HMI 畫面',
              'pid': 'P&ID 圖面', 'getag': 'GE 原廠編號'}
DOCSEARCH_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'docsearch.json')
DRIVE_MAP_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'drive_map.json')
HMI_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'hmi.json')
HMI_SHOTS_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'hmi_shots')
HMI_NAV_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'hmi_nav.json')
PID_DEFAULT = paths.PID_JSON          # <CARDWORK>\pid.json（tools/db/pid_index.py 的輸出）
PID_SHOTS_DEFAULT = paths.PID_SHOTS   # <CARDWORK>\pid_shots（tools/db/pid_shots.py：<slug>.webp＋index.json）
PID_GE_DEFAULT = os.path.join(os.path.dirname(paths.PID_JSON), 'pid_ge.json')   # tools/db/pid_ge.py：GE 原廠編號 → 圖紙與圖上座標（v10）
LOC_GE_DEFAULT = os.path.join(os.path.dirname(paths.PID_JSON), 'loc_ge.json')   # tools/db/loc_ge.py：GE 原廠編號 → 位置圖（配置／電纜槽／外型圖）與圖上座標（v12）
WIRE_GE_DEFAULT = os.path.join(paths.CARDWORK, 'wire_ge.json')   # tools/db/wire_ge.py：汽機 TSI 的接線路徑（接線圖端子、接線箱位置、盤內板位、3500 盤，v13）
HMI_GE_DEFAULT = os.path.join(paths.CARDWORK, 'hmi_ge.json')   # tools/db/hmi_ge.py：GE 原廠編號 → 圖控畫面與座標
DOC_CAT_ORDER = ['P&ID', 'Hook-up', '規格表', '就地錶規格', '接線圖', '電纜表', '保護箱', '位置圖', '邏輯圖', 'GT I/O 清單']
ABS_PATH_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|\\Users\\|/Users/|我的雲端硬碟')  # 磁碟機路徑（https:// 不算）


def dumps(o):
    return json.dumps(o, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


# ------------------------------------------------------------------ 數值／單位
def num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = str(v).strip().replace(',', '')
        m = re.match(r'^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$', s)
        if not m:
            return None
        x = float(s)
    if math.isnan(x) or math.isinf(x):
        return None
    if x != 0 and abs(x) < 1e-30:  # FLT_MIN 哨兵＝未使用
        return None
    return x


def g7(x):
    """float32 殘差以 7 位有效數字顯示（10000.0009765625 → 10000）。"""
    if x is None:
        return ''
    s = '%.7g' % x
    if 'e' in s:
        return s
    return s


PRESS = {'pa': 0.001, 'kpa': 1.0, 'mpa': 1000.0, 'mbar': 0.1, 'bar': 100.0, 'psi': 6.894757, 'mmh2o': 0.00980665,
         'inh2o': 0.24884, 'inhg': 3.38639, 'mmhg': 0.133322, 'kg/cm2': 98.0665}
LENGTH = {'mm': 0.001, 'cm': 0.01, 'm': 1.0, 'in': 0.0254, 'ft': 0.3048}


def unit_info(u):
    """單位字串 → (dim, core, qual)；dim ∈ T/P/L/%/other；qual ∈ ''/g/a/d。無法辨識回 None。"""
    if u is None:
        return None
    s = str(u).strip()
    if not s or s in ('未使用', '—', '-'):
        return None
    if re.search(r'[一-鿿]', s):  # 13 表「攝氏度 °C」：取最後一段
        s = s.split()[-1] if ' ' in s else re.sub(r'[一-鿿/]+', '', s)
    s = s.replace('°', 'deg').replace('º', 'deg').replace('³', '3').replace('²', '2').replace('₂', '2')
    low = s.lower().replace(' ', '')
    low = re.sub(r'\((?:68degf|20degc|4degc|0degc|60degf)\)|@\d+degc', '', low)
    qual = ''
    m = re.match(r'^(.*?)(?:\((g|a|d)\)|-(g|a|d))$', low)
    if m:
        low, qual = m.group(1), (m.group(2) or m.group(3))
    if low in ('degc', 'c', 'deg.c', 'degreec', 'degc.'):
        return ('T', 'c', '')
    if low in ('degf', 'f'):
        return ('T', 'f', '')
    if low in ('k', 'degk', 'kelvin'):
        return ('T', 'k', '')
    if low in ('%', 'percent', 'pct'):
        return ('%', '%', '')
    if low in ('%lel',):
        return ('other', '%lel', '')
    for core in sorted(PRESS, key=len, reverse=True):
        if low == core:
            return ('P', core, qual)
        if low == core + 'g' and core not in ('inhg', 'mmhg'):  # kPag、psig、inH2Og（控制器 format spec 寫法）
            return ('P', core, 'g')
        if low == core + 'a' and core not in ('mmh2o', 'inh2o', 'inhg', 'mmhg', 'kg/cm2'):
            return ('P', core, 'a')
        if low == core + 'd':
            return ('P', core, 'd')
    if low in LENGTH:
        return ('L', low, '')
    low = low.replace('hr', 'h')
    return ('other', low, qual)


def to_base(v, info):
    dim, core, _ = info
    if dim == 'T':
        return v if core == 'c' else ((v - 32.0) * 5.0 / 9.0 if core == 'f' else v - 273.15)
    if dim == 'P':
        return v * PRESS[core]
    if dim == 'L':
        return v * LENGTH[core]
    return v


def from_base(v, info):
    dim, core, _ = info
    if dim == 'T':
        return v if core == 'c' else (v * 9.0 / 5.0 + 32.0 if core == 'f' else v + 273.15)
    if dim == 'P':
        return v / PRESS[core]
    if dim == 'L':
        return v / LENGTH[core]
    return v


ATM_KPA = 101.325


def compare_range(base, other):
    """回傳 (status, note, lo_conv, hi_conv)。
    status：ok｜near（同單位、數值不同但差在 ±0.5% span 內：請確認）｜mismatch｜unit_mismatch（兩邊單位都明確但量綱不同/絕壓↔表壓）
    ｜unit_unknown（任一邊單位空白、無法辨識或僅為推定）。
    同單位（不需換算）時只有 7 位有效數字完全相同才算 ok——量程差異只會是 float32 殘差或真的有人改過，URV 1000 vs 996 不該顯示 ✓；
    需換算的（psi↔kPa、°F↔°C）文件常寫圓整值，維持 ±0.5% span 內為 ok。
    base['bounds']：要比較的端（{'lo','hi'} 的子集；DCS 只寫入一端時另一端不比較）。"""
    if other.get('unit_presumed'):
        return 'unit_unknown', '此來源量程為數值儲存格，原文無單位（單位僅來自儲存格數字格式，推定），未比較', None, None
    bi, oi = unit_info(base['unit']), unit_info(other['unit'])
    if bi is None:
        return 'unit_unknown', 'DCS 基準單位空白或無法辨識%s，未比較' % (base.get('unit_note') or ''), None, None
    if oi is None:
        return 'unit_unknown', '此來源單位空白或無法辨識%s，未比較' % (other.get('unit_note') or ''), None, None
    if bi[0] != oi[0] or (bi[0] == 'other' and bi[1] != oi[1]):
        return 'unit_mismatch', '單位不同（%s ↔ %s），無法換算，未比較' % (base['unit'], other['unit']), None, None
    if {bi[2], oi[2]} >= {'a', 'g'} or {bi[2], oi[2]} >= {'a', 'd'}:  # 只有明確標示「絕對壓 vs 表壓/差壓」才不比；未標示者視為相容
        return 'unit_mismatch', '絕對壓／表壓不同（%s ↔ %s），未比較' % (base['unit'], other['unit']), None, None
    bounds = base.get('bounds') or {'lo', 'hi'}
    lo = from_base(to_base(other['lo'], oi), bi) if other['lo'] is not None else None
    hi = from_base(to_base(other['hi'], oi), bi) if other['hi'] is not None else None
    span = abs((base['hi'] or 0) - (base['lo'] or 0))
    tol = max(span * 0.005, 1e-9)

    def bad_of(l, h, t):
        b = []
        if 'lo' in bounds and l is not None and base['lo'] is not None and abs(l - base['lo']) > t:
            b.append('下限')
        if 'hi' in bounds and h is not None and base['hi'] is not None and abs(h - base['hi']) > t:
            b.append('上限')
        return b
    bad = bad_of(lo, hi, tol)
    conv = (bi[:2] != oi[:2])
    note = ('換算為 %s：%s ~ %s；' % (base['unit'], g7(lo), g7(hi)) if conv else '')
    if bounds != {'lo', 'hi'}:
        note += '僅比較%s（另一端無 DCS 寫入）；' % ('上限' if 'hi' in bounds else '下限')
    if lo is not None and hi is not None and base['lo'] is not None and base['hi'] is not None and (lo > hi) != (base['lo'] > base['hi']):
        note += '上下限方向相反（反向量程）；'
    if bad and bi[0] == 'P' and 'a' in (bi[2], oi[2]) and not (bi[2] and oi[2]):
        # 一邊明確絕壓、另一邊未標示：若差約 1 atm 即可對上，判定為絕壓↔表壓表示法不同（不當作量程不符）
        shift = ATM_KPA / to_base(1.0, bi)  # 1 atm 以基準單位表示（壓力 to_base＝kPa）
        sgn = 1.0 if oi[2] != 'a' else -1.0  # 另一邊為表壓 → 加 1 atm 成絕壓
        l2 = lo + sgn * shift if lo is not None else None
        h2 = hi + sgn * shift if hi is not None else None
        tol2 = max(span * 0.02, 2.0 / to_base(1.0, bi))
        if not bad_of(l2, h2, tol2):
            return 'unit_mismatch', note + '疑似絕壓↔表壓表示不同（%s ↔ %s；差 1 atm 後換算 %s ~ %s 與基準相符），未比較' % (
                base['unit'], other['unit'], g7(l2), g7(h2)), None, None
    if bad:
        return 'mismatch', note + '⚠ 與 DCS 不符（%s，容許 ±0.5%% span）' % '、'.join(bad), lo, hi
    if not conv:
        # 同單位：精確相等（7 位有效數字）才 ok；差在容差內另立 near（前端黃色「≈ 近似（請確認）」），逐端標記依 note 括號內的端
        near = []
        for k, side, v in (('lo', '下限', lo), ('hi', '上限', hi)):
            if k in bounds and v is not None and base[k] is not None and g7(v) != g7(base[k]):
                near.append('%s %s vs %s' % (side, g7(v), g7(base[k])))
        if near:
            return 'near', note + '≈ 近似（%s；同單位但數值不同，差在 ±0.5%% span 內，請確認）' % '、'.join(near), lo, hi
        return 'ok', note + '一致（同單位，數值相同）', lo, hi
    return 'ok', note + '一致（換算後在 ±0.5% span 內）', lo, hi


def unit_of_code_str(s):
    """dcs_writes UNIT '12 (kPa)' → 'kPa'。"""
    if not s:
        return None
    m = re.search(r'\(([^()]+)\)\s*$', str(s))
    return m.group(1) if m else str(s)


# ------------------------------------------------------------------ dcdas：控制器 I/O 組態（signal-atlas 索引，本機 SQLite）
DCDAS_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA') or '', 'dcdas', 'index.sqlite')
DCDAS_FIELD = 'DCS AI 量程 (Low/High Value)'
PREFIX_CTRL = {'S10': ('S1', 'S1S', 'SAMP1'), 'G11': ('G11', 'G11S'), 'G12': ('G12', 'G12S'), 'C10': None}  # 控制器內 DeviceTag 不帶機組前綴
DCDAS_SQL = """select p.ctrl, p.name, p.connection, p.device_tag, p.input_type, p.low_value, p.high_value, p.params_json,
  m.name, m.cabinet, v.units, f.units, v.description
  from io_point p left join io_module m on m.id = p.module_id
  left join variable v on v.id = p.var_id left join format_spec f on f.name = v.format_spec
  where p.signal_type = 'AnalogInput' and p.high_value is not null and coalesce(p.input_type, '') != 'Unused'
    and (coalesce(p.device_tag, '') != '' or coalesce(p.connection, '') != '')
  order by p.ctrl, m.name, p.name"""


def load_dcdas(path):
    """signal-atlas 索引 → 類比輸入通道表（依 DeviceTag／訊號名索引）；檔案不存在回 None（比對就沒有這個來源）。"""
    if not path or not os.path.exists(path):
        return None
    import sqlite3
    c = sqlite3.connect(path)
    meta = dict(c.execute('select key, value from meta').fetchall())
    ctrls = [r[0] for r in c.execute('select name from controller order by name')]
    last_mod = {r[0]: (r[1] or '')[:10] for r in c.execute('select name, last_mod from controller')}  # 各控制器實際 checkout 日
    by_tag, by_conn, n = {}, {}, 0
    for (ctrl, pt, conn, dtag, itype, lo, hi, pj, mod, cab, vunits, funits, desc) in c.execute(DCDAS_SQL):
        x = {'ctrl': ctrl, 'pt': pt, 'conn': (conn or '').strip(), 'dtag': (dtag or '').strip(), 'itype': itype or '', 'lo': lo, 'hi': hi,
             'hart': '"Hart_Enable":"Enable"' in (pj or ''), 'mod': mod or '', 'cab': cab or '', 'units': (vunits or funits or '').strip(), 'desc': desc or ''}
        n += 1
        if x['dtag']:
            by_tag.setdefault(x['dtag'].upper(), []).append(x)
        m = re.match(r'^([A-Z0-9_-]+?)XQ\d{2}$', x['conn'].upper())
        if m:
            by_conn.setdefault(m.group(1), []).append(x)
    c.close()
    built = (meta.get('built_at') or '')[:10]
    return {'by_tag': by_tag, 'by_conn': by_conn, 'built_at': built, 'toolbox': meta.get('toolbox_version') or '', 'controllers': ctrls,
            'last_mod': last_mod, 'channels': n, 'doc_key': 'dcdas|signal-atlas|%s' % built}


def match_dcdas(tag, dc):
    """AMS 位號 → 控制器類比輸入通道：DeviceTag 相同 → 訊號名＝位號+XQnn → DeviceTag 去機組前綴（S10→S1/S1S/SAMP1、G11/G12 燃氣機）。"""
    t = re.sub(r'\s+', '', str(tag or '')).upper()
    if not dc or not t:
        return [], ''
    if t in dc['by_tag']:
        return dc['by_tag'][t], 'DeviceTag 相同'
    if t in dc['by_conn']:
        return dc['by_conn'][t], '訊號名＝位號+XQnn'
    m = re.match(r'^(S10|G11|G12|C10)_?(.+)$', t)
    if m:
        ctrls = PREFIX_CTRL[m.group(1)]
        cands = [x for x in dc['by_tag'].get(m.group(2), []) if ctrls is None or x['ctrl'] in ctrls]
        if cands:
            return cands, 'DeviceTag 相同（去機組前綴 %s）' % m.group(1)
    return [], ''


def tag_ctrls(tag):
    """位號的機組前綴 → 該機組的控制器名（PREFIX_CTRL）；C10（共用）或無前綴回 None（不限控制器）。"""
    m = re.match(r'^(S10|G11|G12|C10)', re.sub(r'\s+', '', str(tag or '')).upper())
    return PREFIX_CTRL.get(m.group(1)) if m else None


def dcdas_entries(tag, dc):
    """→ (entries, primary)：每個類比輸入通道一筆 entry（sec.dcdas）；primary＝DCS 基準候選：有 Low/High 的通道中，優先取控制器與位號機組
    前綴一致者（同一 DeviceTag 可能同時接在 G11／G12／S1 多個控制器），否則依索引排序取第一個。
    同位號多通道而各通道 (Low, High, 單位) 不全相同時（本機索引實查 19 個位號：96CD-1A/1B/1C 各 4 通道 2 種量程、C10BBT10EW001 同控制器 11 通道 4 種量程），
    primary['multi'] 列其餘量程不同的通道（build_compare 各自列成 others kind 'dcdas_ch'、flags.cmp.dcdas_multi='warn'）；多點溫度元件多量程可能是正常設計，
    所以只出黃色提示，不當故障。"""
    recs, how = match_dcdas(tag, dc)
    ents, primary = [], None
    ctrls = tag_ctrls(tag)
    cands = []  # 有 Low/High 的通道（DCS 基準候選）
    for x in recs:
        rng = ('%s – %s %s' % (g7(x['lo']), g7(x['hi']), x['units'])).strip()
        rows = [['控制器', x['ctrl']], ['I/O 模組', x['mod'] + ('（機櫃 %s）' % x['cab'] if x['cab'] else '')], ['通道', x['pt']],
                ['訊號名', x['conn']], ['裝置位號 (DeviceTag)', x['dtag']], ['輸入型式', x['itype']], ['HART 通道', '啟用' if x['hart'] else '停用'],
                [DCDAS_FIELD, rng, 'dcdas'], ['訊號說明', x['desc']]]
        if x['conn']:
            rows.append(['signal-atlas 深連結', 'https://momobacon-wq.github.io/signal-atlas/#/v/%s.%s' % (x['ctrl'], x['conn'])])
        co = (dc.get('last_mod') or {}).get(x['ctrl']) or ''  # 該控制器 checkout 日（索引建立日另列）
        ent = {'h': '%s · %s' % (x['ctrl'], x['conn'] or x['pt']), 'lvl': 'ctrl', 'rule': how, 'rows': rows, 'd': dc['doc_key'],
               'src': '控制器 · %s checkout %s（signal-atlas 索引 %s）· %s %s' % (x['ctrl'], co or '?', dc['built_at'], x['mod'], x['pt'])}
        ents.append(ent)
        if x['lo'] is not None and x['hi'] is not None:
            cands.append({'lo': x['lo'], 'hi': x['hi'], 'unit': x['units'], 'src': ent['src'], 'lvl': 'ctrl', 'kind': 'dcdas', 'ent': ent, 'field': DCDAS_FIELD,
                          'built_at': dc['built_at'], 'checkout_at': co, 'ctrl': x['ctrl'], 'pt': x['pt'], 'conn': x['conn']})
    if cands:
        # 基準：同機組控制器優先，其次單位有寫的（G11 的 AnalogInput06_R 單位空白、G11S 的 a_96ht1a 寫 %：取後者才比得到）；其餘依索引排序
        primary = sorted(cands, key=lambda c: (0 if ctrls and c['ctrl'] in ctrls else 1, 0 if unit_info(c['unit']) else 1, cands.index(c)))[0]

        def differs(c):
            if (g7(c['lo']), g7(c['hi'])) != (g7(primary['lo']), g7(primary['hi'])):
                return True
            ua, ub = unit_info(c['unit']), unit_info(primary['unit'])
            return bool(ua and ub and ua != ub)  # 單位空白不算不同（只是沒寫）
        others = [c for c in cands if c is not primary and differs(c)]
        if others:
            primary['multi'] = others
            primary['multi_note'] = '同位號有 %d 個類比輸入通道，其中 %d 個量程與基準不同（基準取 %s %s；其餘各列一列）' % (
                len(cands), len(others), primary['ctrl'], primary['conn'] or primary['pt'])
    return ents, primary


def dcdas_doc(dc):
    """index.searched['dcdas'] 的一筆與 index.docs 的一項：把索引當一份「文件」描述（不含本機路徑）。"""
    lm = dc.get('last_mod') or {}
    co_list = '、'.join('%s %s' % (k, lm.get(k) or '?') for k in dc['controllers'])
    co_span = ('%s～%s' % (min(v for v in lm.values() if v), max(v for v in lm.values() if v))) if any(lm.values()) else '?'
    why = ('各控制器 checkout 日期（比對基準用）：%s；索引建立 %s（ToolboxST %s）。只涵蓋類比輸入通道（4-20 mA）的 Low/High Value；'
           'FF 設備與 HART 多工器本體不在 I/O 索引。位號對照：DeviceTag 相同 → 訊號名＝位號+XQnn → DeviceTag 去機組前綴。'
           '索引是 checkout 快照，不是控制器即時狀態。'
           % (co_list, dc['built_at'], dc['toolbox']))
    s = {'doc_id': 'signal-atlas', 'rev': co_list, 'ref': '控制器 checkout %s（signal-atlas 索引 %s）' % (co_span, dc['built_at']),
         'title': 'signal-atlas 訊號索引（ToolboxST checkout I/O 組態）', 'folder': '（本機索引 %LOCALAPPDATA%\\dcdas，不在工程文件庫）', 'used': True, 'why': why}
    return s, {dc['doc_key']: {'title': s['title'], 'folder': s['folder'], 'why': why}}


# ------------------------------------------------------------------ getag：GE 原廠設備編號（hst-docsearch 的 ge_tags 對照表，本機 JSON）
# 對照表是從 GE Device Summary（儀器／閥／負載／設備／配管清單）、型錄總表、Mark VIe I/O 清單等文件抽出的「GE 編號（Legacy Tag）↔ KKS」，
# 每筆帶出處（文件庫相對路徑＋頁／列）。AMS 位號有兩種寫法對得到它：GE 名稱（G11_96PG-5B）與 KKS（S10LBA12BP003）。
GE_DEFAULT = paths.GE_TAGS
GE_SRC = '8 GE 原廠編號（GE 文件）'   # 04 位號索引的來源類型：排在 0～7 之後；只有對到 AMS 設備的 GE 編號才加
GE_KKS_RE = re.compile(r'^([A-Z]\d{2}|XX|YY)?([A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]??)([A-Z]{1,2}\d{2})?$')   # 比對前已去分隔符；XX＝燃機通用、YY＝汽機通用
GE_SUFFIX = {'KH': '定位器', 'MB': '電磁閥', 'BG': '極限開關', 'BL': '液位探棒', 'MA': '馬達'}
GE_SYSTEM = {'GT': '燃機', 'ST': '汽機', 'GT-GEN': '燃機發電機', 'ST-GEN': '汽機發電機'}
GE_RELATED_MAX = 4      # 同 KKS 本體的其他 GE 編號最多列幾筆
GE_SHARED_MAX = 3       # 一個本體被超過這麼多個 GE 編號共用（盤箱、多點溫度元件）就不列「相關」


def ge_cmp(s):
    return re.sub(r'[^A-Z0-9]', '', str(s or '').upper())


def ge_kks(k):
    """'XXMBV01GP001-MA01' → ('XX', 'MBV01GP001', 'MA01')；不是 KKS 形狀回 None。"""
    m = GE_KKS_RE.match(ge_cmp(k))
    return (m.group(1) or '', m.group(2), m.group(3) or '') if m else None


def ge_scope(e):
    """'G'（燃機範圍）／'S'（汽機範圍）：先看對照表的 system，再看 KKS 前綴。GE 編號只在一部機台內唯一（燃機、汽機各有一顆 45HG-CB-7A）。"""
    s = e.get('system') or ''
    if s.startswith('GT'):
        return 'G'
    if s.startswith('ST'):
        return 'S'
    for k in e.get('kks') or []:
        p = ge_kks(k)
        if p and p[0]:
            return 'G' if p[0] == 'XX' or p[0].startswith('G') else 'S' if p[0] == 'YY' or p[0].startswith('S') else None
    return None


def ge_unit_kks(k, unit):
    """對照表的 KKS 換成這台的機組前綴：GT 清單只印 G11（G11=G12=…）、GE 原版清單印 XX／YY。看不出前綴就原樣。"""
    k = re.sub(r'\s+', '', str(k or ''))
    m = re.match(r'^(XX|YY|[GS]\d\d)(?=[A-Z]{3}\d\d)', k)
    if m and unit and m.group(1) != unit and (m.group(1) in ('XX', 'YY') or m.group(1)[0] == unit[0]):
        return unit + k[len(m.group(1)):]
    return k


def ge_doc_key(doc):
    return 'ge|%s|' % hashlib.sha1(str(doc or '').encode('utf-8')).hexdigest()[:12]


def ge_ff_only(e):
    """條目只出自 Mark VIe I/O 清單的 FF H1 裝置報告：那份報告的「說明」欄其實是裝置型號（848 Fieldbus Temperature Device、Logix 3840）。"""
    srcs = e.get('src') or []
    return bool(srcs) and all('IMI01-A0002' in (s.get('doc') or '') for s in srcs) and 'FFB Segments' in (e.get('note') or '')


def load_ge(path, dcdas_path=None):
    """ge_tags.json → 名稱索引 (範圍, 去分隔符的 GE 編號) 與 KKS 本體索引 (範圍, 本體)；檔案不存在回 None。
    另讀 signal-atlas 索引的變數名（vars）：對照表的 Mark VIe 訊號常只列 G11（GE 文件只印 G11 的 KKS），G12 那台要確認 G12 有同名變數才列。"""
    if not path or not os.path.exists(path):
        return None
    j = load(path)
    if not isinstance(j.get('entries'), list):
        raise SystemExit('!! %s 不是 GE 編號對照表（缺 entries）' % path)
    name, body = {}, {}
    for i, e in enumerate(j['entries']):
        e['_i'], e['_scope'] = i, ge_scope(e)
        for f in {e.get('tag') or ''} | set(e.get('forms') or []):
            if f:
                name.setdefault((e['_scope'], ge_cmp(f)), {})[i] = e
        for k in e.get('kks') or []:
            p = ge_kks(k)
            if p:
                body.setdefault((e['_scope'], p[1]), {})[i] = (e, k, p[2])
    vars_ = None
    if dcdas_path and os.path.exists(dcdas_path):
        import sqlite3
        c = sqlite3.connect('file:%s?mode=ro' % dcdas_path, uri=True)
        vars_ = {('%s.%s' % (ct, nm)).upper() for ct, nm in c.execute("select ctrl, name from variable where ctrl like 'G%' or ctrl like 'S%'")}
        c.close()
    return {'entries': j['entries'], 'name': {k: list(v.values()) for k, v in name.items()},
            'body': {k: list(v.values()) for k, v in body.items()}, 'built_at': str(j.get('built_at') or ''),
            'n_rows': j.get('n_rows') or 0, 'n_docs': len(j.get('sources') or []), 'docs': {}, 'vars': vars_, 'own': set(),
            'spec_fields': j.get('spec_fields') or {}}


def ge_match(tag, ge):
    """AMS 位號 → ([(條目, 規則, lvl, 子件尾碼)]（主條目排第一）, 機組前綴)。
    G11_96PG-5B 這類以 GE 名稱命名的位號比名稱（去機組前綴、去尾端 _01 這類 AMS 同位號的另一筆設備紀錄）；對不到而以 90 開頭時去 90 再比
    （定位器 90VAST-11 在對照表只有閥本體 VAST-11，lvl 降為推論）。KKS 寫法的位號（不帶子件尾碼）比 KKS 本體（對照表那邊去機組前綴與子件尾碼），
    範圍要相同：G11LBA10BT001（HRSG）與汽機的 TE-227-1（LBA10BT001）是兩台不同的設備。汽機的 GE 名稱寫法位號（S10_…）現在 AMS 沒有，未支援。"""
    t = re.sub(r'\s+', '', str(tag or '')).upper()
    if not ge or not t:
        return [], ''
    m = re.match(r'^(G\d\d)_(.+?)(_0\d)?$', t)
    if m:
        unit, nm, dup = m.group(1), m.group(2), m.group(3)
        hits = ge['name'].get(('G', ge_cmp(nm)))
        if hits:
            why = 'AMS 位號＝%s_＋GE 編號' % unit + ('（尾端 %s 是 AMS 同位號的另一筆設備紀錄）' % dup if dup else '')
            return [(e, why, 'doc', '') for e in hits], unit
        if nm.startswith('90'):
            hits = ge['name'].get(('G', ge_cmp(nm[2:])))
            if hits:
                why = 'AMS 位號去 %s_ 與 90 字頭後＝GE 編號（對照表沒有 %s 這個編號，以閥本體代表）' % (unit, nm)
                return [(e, why, 'inferred', '') for e in hits], unit
        return [], unit
    p = ge_kks(t)
    if p and p[0] and not p[2]:
        unit = p[0]
        sc = 'G' if unit.startswith('G') else 'S' if unit.startswith('S') else None
        hits = sorted(ge['body'].get((sc, p[1])) or [], key=lambda x: (x[2] != '', x[0]['_i'])) if sc else []
        return [(e, 'KKS 本體相同（去機組前綴；對照表寫 %s）' % k, 'doc', suf) for e, k, suf in hits], unit
    return [], ''


def ge_prepass(ge, tags):
    """先對全部位號比一次：記下「本身就是某台 AMS 設備主條目」的條目（ge['own']），列相關編號時跳過——那台有自己的卡
    （96PGT-3B、3C 是三台不同的傳送器，舊版文件把 KKS 寫重了，不可說成同一套設備）。"""
    if ge is None:
        return
    for t in tags:
        for e, _w, _l, _s in ge_match(t, ge)[0]:
            ge['own'].add(e['_i'])


def ge_logic(e, unit, ge):
    """→ (訊號清單, 註記)：只列本台機組控制器的訊號；對照表只列同設計的姊妹機組（GE 文件只印 G11 的 KKS，所以 KKS 別名只連到 G11）時，
    換成本台控制器、而且 signal-atlas 索引裡確實有這個變數才列；確認不了就不列（不可把 G11 的訊號掛在 G12 的卡上）。"""
    ctrls = PREFIX_CTRL.get(unit) or ()
    logic = e.get('logic') or []
    mine = [n for n in logic if n.split('.', 1)[0] in ctrls]
    if mine or not ctrls or not ge.get('vars'):
        return mine, ''
    out = []
    for n in logic:
        c, _, nm = n.partition('.')
        m = re.match(r'^([A-Z])\d\d(S?)$', c)
        tgt = next((t for t in ctrls if m and re.match(r'^%s\d\d%s$' % (m.group(1), m.group(2)), t)), None)
        if tgt and ('%s.%s' % (tgt, nm)).upper() in ge['vars'] and '%s.%s' % (tgt, nm) not in out:
            out.append('%s.%s' % (tgt, nm))
    return out, ('對照表只列同設計的 %s，本台同名變數經 signal-atlas 索引確認' % '、'.join(sorted({n.split('.', 1)[0] for n in logic})) if out else '')


def ge_entry(e, rule, lvl, unit, suf, ge):
    s0 = (e.get('src') or [{}])[0]
    sysname = GE_SYSTEM.get(e.get('system') or '', e.get('system') or '')
    role = GE_SUFFIX.get(re.sub(r'\d', '', suf or ''), '')
    ff = ge_ff_only(e)
    rows = [['GE 編號', e['tag']]]
    items = e.get('items') or []
    if len(items) > 1:
        for it in items:
            rows.append(['GE 說明（%s）' % ge_unit_kks(it.get('kks'), unit), it.get('service') or ''])
    elif e.get('service'):
        rows.append(['GE 裝置類型（FF H1 Device Name）' if ff else 'GE 說明 (Service)', e['service']])
    kks = [ge_unit_kks(k, unit) for k in e.get('kks') or []]
    if kks:
        rows.append(['KKS（GE 文件）', ' / '.join(kks)])
    if role:
        rows.append(['子件', '%s（KKS 尾碼 -%s）' % (role, suf)])
    if sysname:
        rows.append(['範圍', sysname])
    if e.get('mli'):
        rows.append(['MLI', e['mli']])
    lg, lnote = ge_logic(e, unit, ge)
    if lg:
        rows.append(['Mark VIe 訊號', '、'.join(lg[:8]) + (' …' if len(lg) > 8 else '') + ('（%s）' % lnote if lnote else '')])
    for x in (e.get('linked') or [])[:4]:
        rows.append(['相關裝置', '%s（%s）' % (x.get('tag'), x.get('rel'))])
    if e.get('old_kks'):
        rows.append(['其他文件寫的 KKS（照原文）', '；'.join('%s（%s）' % (o.get('kks'), o.get('src')) for o in e['old_kks'][:3])])
    if e.get('conflict'):
        rows.append(['文件不一致', e['conflict']])
    if e.get('fix'):
        rows.append(['對照表更正', '%s（%s；信心%s）' % (e['fix'].get('text') or '', {'correction': '已更正', 'link': '補連訊號'}.get(
            e['fix'].get('kind'), '文件之間不一致，兩個都列'), e['fix'].get('confidence') or '未標')])
    more = (e.get('src') or [])[1:]
    if more:
        rows.append(['其他出處', '；'.join('%s %s' % (os.path.basename(s.get('doc') or ''), s.get('loc') or '') for s in more[:4])
                     + ('（另 %d 處）' % (len(more) - 4) if len(more) > 4 else '')])
    d = None
    if s0.get('doc'):
        d = ge_doc_key(s0['doc'])
        fo, _, ti = s0['doc'].replace('\\', '/').rpartition('/')
        ge['docs'][d] = {'title': ti, 'folder': fo, 'why': 'GE 原廠編號對照表的出處（%s）' % (s0.get('rev') or '版次未標')}
    svc = '' if ff else ((items[0].get('service') if len(items) == 1 else e.get('service')) or '')
    ent = {'h': '%s%s' % (e['tag'], (' · ' + svc[:48]) if svc else ''), 'lvl': lvl, 'rule': rule, 'rows': rows,
           'src': '%s · %s %s' % (SRC_DEFS[lvl]['label'], os.path.basename(s0.get('doc') or ''), s0.get('loc') or '')}
    if d:
        ent['d'] = d
    return ent


GE_SPEC_RULE = ('GE 清單逐列抽出的元件詳細資料（廠牌、型號、量程、設定值、P&ID…）：一份文件一塊；後面的塊不重列前面相同的值，'
                '同一份清單的舊版只補新版沒有的欄。PDF 依文字座標分欄、xlsx 讀儲存格，各組經獨立核對者開圖或讀儲存格抽查；引用前以原文件為準')
GE_REL_MAX = 12   # 相關閥／相關儀器最多列幾筆（卡上與完整資料區）
GE_PROT_RULE = ('GE 燃機控制規格書 308T9574／安全迴路方塊圖 308T9382、汽機方塊圖 316T9333、燃料氣 P&ID 137T9782 逐段讀出的「功能組」：'
                '保護功能＝哪些儀器觸發或啟用它、它動作哪些閥（common actuators 依規格書 §4.1 展開）；腔室／管段＝P&ID 上儀器所在的一段與它的上下游閥、排放閥；'
                '經反方逐組開圖核對')


def ge_spec_blocks(e, ge):
    """條目的 spec（hst-docsearch ge_details.py 併進 ge_tags.json）→ 卡片格式的塊 [{h, lvl, rule, rows, src, d}]；出處文件登記進 ge['docs']。"""
    labels = ge.get('spec_fields') or {}
    out = []
    for b in e.get('spec') or []:
        rows = [[labels.get(k, k), v] for k, v in b.get('f') or []]
        if b.get('via'):
            rows.append(['對照方式', b['via']])
        if not rows:
            continue
        d = ge_doc_key(b.get('doc'))
        fo, _, ti = str(b.get('doc') or '').replace('\\', '/').rpartition('/')
        ge['docs'].setdefault(d, {'title': ti, 'folder': fo, 'why': 'GE 元件詳細資料的出處（%s）' % (b.get('rev') or '版次未標')})
        out.append({'h': '%s%s' % (b.get('label') or ti, '（舊版，只補新版沒有的欄）' if b.get('old') else ''), 'lvl': 'doc',
                    'rule': '%s；這一塊：%s' % (GE_SPEC_RULE, b.get('evidence') or ''), 'rows': rows,
                    'src': '%s · %s %s' % (SRC_DEFS['doc']['label'], ti, b.get('loc') or ''), 'd': d})
    return out


def ge_rel_doc(ge, doc, why):
    """關係／保護功能的出處文件登記進 ge['docs']（前端用它開雲端連結）→ 文件鍵；ge 為 None 或沒有出處時回 ''"""
    if ge is None or not doc:
        return ''
    d = ge_doc_key(doc)
    fo, _, ti = str(doc).replace('\\', '/').rpartition('/')
    ge['docs'].setdefault(d, {'title': ti, 'folder': fo, 'why': why})
    return d


def ge_rel_rows(e, key, ge=None):
    """相關閥（key='valves'）／相關儀器（'instruments'）→ [[GE 編號, 關係種類, 說明, lvl, 出處文字, 出處文件鍵]]"""
    out = []
    for x in (e.get(key) or [])[:GE_REL_MAX]:
        src = ('%s %s' % (os.path.basename(x.get('doc') or ''), x.get('loc') or '')).strip()
        out.append([x.get('tag') or '', x.get('kind') or '', x.get('rel') or '', x.get('lvl') or 'doc', src,
                    ge_rel_doc(ge, x.get('doc'), 'GE 元件關係（相關閥／儀器）的出處')])
    return out


def ge_prot_rows(e, key, ge=None):
    """功能組（key='prot'：這顆儀器參與的保護功能與它動作的閥；'prot_in'：會動作這顆閥的保護功能與觸發它的儀器；
    'pos'：儀器所在的腔室／管段與邊界閥；'pos_in'：這顆閥邊界的腔室／管段與其中的儀器）
    → [[功能名, 本顆的角色, 說明, [[GE 編號, 角色], …], 出處文字, 出處文件鍵]]（同一組只一筆）"""
    out = []
    for x in e.get(key) or []:
        lst = x.get('valves') if key in ('prot', 'pos') else x.get('sensors')
        src = ('%s %s' % (os.path.basename(x.get('doc') or ''), x.get('loc') or '')).strip()
        out.append([x.get('fn') or '', x.get('role') or '', x.get('rel') or '', [[t, r] for t, r in lst or []], src,
                    ge_rel_doc(ge, x.get('doc'), 'GE 保護功能（控制規格書／方塊圖／P&ID）的出處')])
    return out


def ge_entries(tag, ge):
    """→ (entries, 主條目的 GE 編號)。主條目在前（前端摘要格取 entries[0]），之後是現行 KKS 本體相同的其他 GE 編號（lvl 推論）：
    只看現行 KKS（舊版文件的 KKS 可能是誤植）、跳過本身就是另一台 AMS 設備主條目的編號（ge['own']，那台有自己的卡）。"""
    hits, unit = ge_match(tag, ge)
    if not hits:
        return [], []
    ents, seen, prim, extra = [], set(), [], []
    for e, why, lvl, suf in hits:
        if e['_i'] not in seen:
            seen.add(e['_i'])
            ents.append(ge_entry(e, why, lvl, unit, suf, ge))
            prim.append(e['tag'])
            for b in ge_spec_blocks(e, ge):   # 規格塊與相關閥：排在對照條目之後（摘要格只取 entries[0]）
                extra.append(dict(b, h='%s 規格 · %s' % (e['tag'], b['h'])))
            for key, what in (('valves', '相關閥'), ('instruments', '相關儀器')):
                rr = ge_rel_rows(e, key)
                if rr:
                    extra.append({'h': '%s %s（GE 文件）' % (e['tag'], what), 'lvl': 'doc' if all(r[3] == 'doc' for r in rr) else 'inferred',
                                  'rule': 'KKS 子件尾碼、閥清單 Solenoid Tag 欄、P&ID 腔室邊界讀出的關係；說明欄寫明的對應是推論',
                                  'rows': [[what, '%s〔%s〕%s%s' % (r[0], r[1], r[2], '（推論）' if r[3] == 'inferred' else '') + ('（%s）' % r[4] if r[4] else '')] for r in rr],
                                  'src': '%s · GE 原廠編號對照表的關係欄' % SRC_DEFS['doc']['label']})
            for key, what in (('pos', '所在腔室／管段'), ('pos_in', '邊界的腔室／管段'), ('prot', '參與的保護功能'), ('prot_in', '會動作這顆閥的保護功能')):
                pr = ge_prot_rows(e, key)
                if pr:
                    extra.append({'h': '%s %s（GE %s）' % (e['tag'], what, 'P&ID' if key.startswith('pos') else '控制規格書／方塊圖'), 'lvl': 'doc', 'rule': GE_PROT_RULE,
                                  'rows': [[r[0], '%s%s：%s%s（%s）' % ('本顆＝%s；' % r[1] if r[1] else '',
                                            {'pos': '邊界閥', 'pos_in': '腔內儀器', 'prot': '動作', 'prot_in': '觸發／條件'}[key],
                                            '、'.join(t for t, _r in r[3][:16]) + (' 等 %d 個' % len(r[3]) if len(r[3]) > 16 else ''),
                                            '。' + r[2] if r[2] else '', r[4])] for r in pr],
                                  'src': '%s · GE 原廠編號對照表的保護功能欄' % SRC_DEFS['doc']['label']})
    rel = []
    for e, _why, _lvl, _suf in hits:
        for k in e.get('kks') or []:
            p = ge_kks(k)
            group = ge['body'].get((e['_scope'], p[1])) if p else None
            if not group or len(group) > GE_SHARED_MAX:
                continue
            for e2, _k2, suf2 in group:
                if e2['_i'] not in seen and e2['_i'] not in ge['own'] and len(rel) < GE_RELATED_MAX:
                    seen.add(e2['_i'])
                    rel.append(ge_entry(e2, '與 %s 在 GE 文件中共用同一個 KKS 本體（%s）的另一個編號：常是同一套設備（閥本體、定位器、電磁閥）'
                                            '或同一盒的另一顆，也可能是文件誤植；以出處為準' % (e['tag'], p[1]), 'inferred', unit, suf2, ge))
    return ents + extra + rel, prim


def ge_apply(sec, ge, tag, by_tag, al):
    """sec.getag（以現行 AMS 位號對照）；主條目的 GE 編號記進 by_tag（{GE 編號: [alias…]}，給 04 位號索引）。"""
    if ge is None:
        return
    ents, prim = ge_entries(tag, ge)
    if ents:
        sec['getag'] = {'entries': ents}
        for t in prim:
            by_tag.setdefault(t, []).append(al)
        for e, why, _lvl, _suf in ge_match(tag, ge)[0]:   # GE 編號卡（card/getag.json）的「AMS 設備」：這個條目是哪幾台 AMS 設備的主條目
            ge.setdefault('ams_of', {}).setdefault(e['_i'], []).append([al, tag, why])


def ge_doc(ge, stats):
    """index.searched['getag'] 的一筆：對照表本身（不含本機路徑）。"""
    why = ('GE 原廠設備編號（Legacy Tag／GE No.）↔ KKS 對照表，建於 %s：%d 列原列、%d 份 GE 文件（Device Summary 儀器／閥／負載／設備／配管清單各版、'
           '型錄總表、Mark VIe I/O 清單、Interconnection、發電機接線圖），各組經反方抽查。對照方式：AMS 位號是 GE 名稱寫法（G11_96PG-5B）比名稱，'
           'KKS 寫法（S10LBA12BP003）比 KKS 本體（去機組前綴與子件尾碼），燃機與汽機範圍分開。HRSG／BOP 等非 GE 供貨的設備沒有 GE 編號。'
           '本站對到 %d 台。' % (ge['built_at'], ge['n_rows'], ge['n_docs'], stats['sections'].get('getag', 0)))
    return {'doc_id': 'ge-tags', 'rev': ge['built_at'], 'ref': 'GE 原廠設備編號對照表 %s' % ge['built_at'],
            'title': 'GE 原廠設備編號對照表（hst-docsearch ge_tags）', 'folder': '（本機對照表，不在工程文件庫）', 'used': True, 'why': why}


GE_CARD_FILE = 'card/getag.json'
GE_LOC_FILE = 'card/getag-loc.json'   # GE 編號卡的 P&ID／圖控位置（v10）：約 6 MB 明文，另成一檔，開 GE 編號卡才下載（getag.json 在查詢時就要載）
GE_SITE_UNITS = {'G': ('G11', 'G12'), 'S': ('S10',)}   # 本站（1 號機）的機組：GE 編號卡逐機組列 KKS 與 Mark VIe 訊號
GE_CARD_RULE = 'GE 原廠編號對照表：GE 各版設備清單、型錄總表、Mark VIe I/O 清單等文件逐列抽出（GE 編號 ↔ KKS ↔ 說明），以出處為準'
GE_UNIT_RULE = 'KKS 前綴換成本台機組（清單印 G11 或 XX／YY）；Mark VIe 訊號只列本台控制器，對照表只列 G11 時要 signal-atlas 索引確認本台有同名變數才列'


GE_GONE_RE = re.compile(r'GE 編號＝|閥本體|舊 ?KKS|KKS 不同')   # 「最新版已無此編號」的備註裡，值得一起列出的分句


def ge_gone(e):
    """對照表 note 記「最新版 GE 清單已無此編號」的條目 → 卡上「文件狀態」那一列（第一分句＋指向現行編號／閥本體／舊 KKS 的分句）；不是就 ''。"""
    segs = [x.strip() for x in str(e.get('note') or '').split('；') if x.strip()]
    if not any('已無此編號' in x for x in segs):
        return ''
    keep = [x for x in segs if '已無此編號' in x] + [x for x in segs if '已無此編號' not in x and GE_GONE_RE.search(x)]
    return '；'.join(keep) + '（舊版文件才有這個編號，引用前先查最新版）'


def ge_card_data(ge, loc=None, pm=None):
    """card/getag.json：整份對照表給查詢卡的「GE 編號卡」——AMS 沒有這台設備時（熱電偶 CT-DA-1、限位開關…），
    打 GE 編號、Mark VIe 訊號名或 KKS 也查得到是哪個元件。每個條目照 ge_entry 逐機組產生（ge_unit_kks／ge_logic 的規則不變：
    不可把 G11 的訊號掛在 G12），各機組都相同的列併成共同的一塊（c），不同的（KKS、Mark VIe 訊號）分機組列（u）。
    出處文件另成一份 docs（不併進 index.docs：那裡只放卡片用到的文件），回傳 (資料, docs, 位置檔)。
    loc＝ge_loc_build 的第一個回傳值（v10：pd＝P&ID 圖面位置、hm＝圖控畫面位置、hmx＝每部機超過上限的畫面名、hr＝只有相關訊號的畫面）；
    這些列不放在 getag.json，另成 card/getag-loc.json（{by_i: {條目序號: {pd, hm, hmx, hr}}}），條目只帶 lc＝1；
    pd 用到的圖紙所屬 PDF（pid|…）登記進這份 docs，雲端連結照 pid_own_urls_only 的規則只連那一份檔。"""
    saved, ge['docs'] = ge['docs'], {}
    locs = {}   # {條目序號（字串）: {pd, hm, hmx, hr}} → card/getag-loc.json
    ams_of = ge.get('ams_of') or {}
    by_name = {}   # (範圍, 去分隔符的寫法) → 條目：相關裝置的連結要對到真的條目
    for e in ge['entries']:
        for f in {e['tag']} | set(e.get('forms') or []):
            by_name.setdefault((e['_scope'], ge_cmp(f)), e)
    ents = []
    for e in ge['entries']:
        units = GE_SITE_UNITS.get(e['_scope']) or ('',)
        per = [(u, ge_entry(e, GE_CARD_RULE, 'doc', u, '', ge)) for u in units]
        first = per[0][1]
        common = [r for r in first['rows'] if all(r in x['rows'] for _u, x in per[1:]) and r[0] != '相關裝置']   # 相關裝置改成連結 chips（ln）
        if not e['_scope']:   # 對照表的 system 是 ?／?-GEN
            common = [['範圍', '不明（GE 文件沒寫是燃機或汽機）'] if r[0] == '範圍' else r for r in common]
        gone = ge_gone(e)
        if gone:   # 放在一般欄位之後、其他出處之前（放第二列會把「GE 編號」擠成單獨一列）
            at = next((k for k, r in enumerate(common) if r[0] in ('其他文件寫的 KKS（照原文）', '文件不一致', '其他出處')), len(common))
            common.insert(at, ['文件狀態', gone])
        c = {k: v for k, v in first.items() if k not in ('rule', 'h')}   # 規則文字每筆一樣：放檔頭 rule（前端補回）；標題前端自己組
        c['rows'] = common
        u = []   # [[機組, 只有這台不同的列]]：出處（lvl／src／d）與共同那塊相同，規則文字在檔頭 rule_unit
        for un, x in per:
            rows = [r for r in x['rows'] if r not in common and r[0] != '相關裝置']
            if rows and un:
                u.append([un, rows])
        own = [x[0] for x in ams_of.get(e['_i']) or []]
        sib, tw = [], []
        for k in e.get('kks') or []:   # 共用同一個現行 KKS 本體的其他編號（閥本體／定位器／電磁閥…）；盤箱、多點溫度元件（> GE_SHARED_MAX）不列
            p = ge_kks(k)
            group = ge['body'].get((e['_scope'], p[1])) if p else None
            if group and len(group) <= GE_SHARED_MAX:
                for e2, _k2, _s2 in group:
                    if e2['_i'] == e['_i']:
                        continue
                    if e2['tag'] not in sib:
                        sib.append(e2['tag'])
                    for al, tag, _why in ams_of.get(e2['_i']) or []:   # 同一 KKS 的另一個編號是 AMS 設備（改過編號的同一顆傳送器常見）
                        if al not in own and al not in [x[0] for x in tw]:
                            tw.append([al, tag, e2['tag']])
        ln = []
        for x in (e.get('linked') or [])[:12]:   # 連結對到真的條目才給（FF 通道名帶 A／B 通道字母：DTGSC1A → DT-GSC-1）
            t = x.get('tag') or ''
            hit = by_name.get((e['_scope'], ge_cmp(t))) or by_name.get((e['_scope'], re.sub(r'[A-Z]$', '', ge_cmp(t))))
            ln.append([t, x.get('rel') or '', hit['tag'] if hit else ''])
        cur = {p[1] for p in map(ge_kks, e.get('kks') or []) if p}
        okb = list(dict.fromkeys(p[1] for p in (ge_kks(o.get('kks')) for o in e.get('old_kks') or []) if p and p[1] not in cur))
        sig = list(dict.fromkeys(n.split('.', 1)[1] for n in e.get('logic') or [] if '.' in n))   # 訊號名（不帶控制器）→ 搜尋鍵
        lg = {un: x for un in units if un for x in [ge_logic(e, un, ge)[0]] if x}   # 各機組可連 signal-atlas 的訊號（同 ge_entry 的規則）
        o = {'t': e['tag'], 'f': [f for f in dict.fromkeys(e.get('forms') or []) if ge_cmp(f) != ge_cmp(e['tag'])], 'sc': e['_scope'] or '',
             'sys': GE_SYSTEM.get(e.get('system') or '', ''), 'svc': '' if ge_ff_only(e) else (e.get('service') or ''), 'c': c}
        sp = [{k: v for k, v in b.items() if k != 'rule'} for b in ge_spec_blocks(e, ge)]   # 規則文字每塊一樣：放檔頭 rule_spec
        for b, b0 in zip(sp, [b0 for b0 in e.get('spec') or [] if b0.get('f') or b0.get('via')]):
            b['ev'] = b0.get('evidence') or ''
        vl, vi = ge_rel_rows(e, 'valves', ge), ge_rel_rows(e, 'instruments', ge)
        pr, pi = ge_prot_rows(e, 'prot', ge), ge_prot_rows(e, 'prot_in', ge)
        ps, pv = ge_prot_rows(e, 'pos', ge), ge_prot_rows(e, 'pos_in', ge)
        for k, v in (('u', u), ('gone', 1 if gone else 0), ('ams', ams_of.get(e['_i'])), ('tw', tw), ('ln', ln), ('sib', sib[:GE_RELATED_MAX]),
                     ('sig', sig), ('lg', lg), ('kb', sorted(cur)), ('okb', okb), ('sp', sp), ('vl', vl), ('vi', vi), ('pr', pr), ('pi', pi), ('ps', ps), ('pv', pv)):
            if v:
                o[k] = v
        lo = {k: v for k, v in ((loc or {}).get(e['_i']) or {}).items() if k in ('pd', 'hm', 'hmx', 'hr', 'hms', 'ld', 'ldn', 'wp', 'wpx', 'wpn', 'wpr') and v}
        if lo:
            o['lc'] = 1   # 這個條目在 getag-loc.json 有位置列（前端沒有這個旗標就不下載那個檔）
            locs[str(len(ents))] = lo
        for r in (lo.get('pd') or []) + (lo.get('ld') or []) + [x for c in ([lo['wp']] if lo.get('wp') else []) + (lo.get('wpx') or []) for x in c.get('rows') or []]:
            d = r[4].get('d') if len(r) > 4 and isinstance(r[4], dict) else None
            if d and pm is not None and d in (pm.get('_docs') or {}):
                ge['docs'].setdefault(d, dict(pm['_docs'][d]))
        ents.append(o)
    docs, ge['docs'] = ge['docs'], saved
    data = {'version': 1, 'built_at': ge['built_at'], 'n': len(ents), 'units': {k: list(v) for k, v in GE_SITE_UNITS.items()},
            'rule': GE_CARD_RULE, 'rule_unit': GE_UNIT_RULE, 'rule_spec': GE_SPEC_RULE, 'rule_prot': GE_PROT_RULE, 'rule_loc': GE_LOC_RULE, 'rule_wire': GE_WIRE_RULE,
            'hmi_max': GE_HMI_MAX, 'entries': ents}
    if locs:
        data['loc'] = GE_LOC_FILE
    return data, docs, ({'version': 1, 'built_at': ge['built_at'], 'by_i': locs} if locs else None)


def ge_index_plan(outdir, by_tag):
    """04 位號索引加「GE 編號 → 設備」列（來源類型 GE_SRC）的新內容——只算、不寫：write_output 等分塊與 index 都自檢過才寫檔。
    by_tag＝{GE 編號: [alias, …]}。先拿掉上次加的列（冪等）；鍵與 04 既有鍵相同、或去分隔符後相同（core.js compactMap 先到先得，會搶走既有鍵）的跳過並列出；
    穩定排序只用 (鍵, 是否 GE 列, GE 列的目前位號)——既有列保持 sheets_index 給的順序，同一 GE 鍵內 G11 在 G12 前（搜尋預設開 G11 那台）。
    列數改寫在 04 說明、00 目錄、manifest。回傳 (加入的列數, 加入的鍵數, 跳過的鍵, [(路徑, 位元組)…]，manifest 物件)。"""
    p = os.path.join(outdir, 'sheets', '04.json')
    s04 = load(p)
    rows = [r for r in s04['rows'] if r[2] != GE_SRC]
    have = {r[0] for r in rows}
    have_c = {ge_cmp(k) for k in have}
    by_alias = {r[4]: r for r in rows if str(r[2]).startswith('1 ')}   # 1 設備別名：每台一列，帶目前位號、DeviceKey、型號
    new, keys, skipped = [], 0, []
    for tag, aliases in sorted(by_tag.items()):
        key = re.sub(r'\s+', ' ', tag.replace('=', '')).strip().upper()
        if not key:
            continue
        if key in have or ge_cmp(key) in have_c:
            skipped.append(key)
            continue
        als = [al for al in dict.fromkeys(aliases) if al in by_alias]
        for al in als:
            b = by_alias[al]
            new.append([key, tag, GE_SRC, b[3], al, b[5], b[6], len(als)])
        keys += 1 if als else 0
    rows += new
    rows.sort(key=lambda r: (r[0], r[2] == GE_SRC, r[3] if r[2] == GE_SRC else ''))
    s04['rows'] = rows
    n = len(rows)
    s04['notes'] = [re.sub(r'列數 [\d,]+', '列數 {:,}'.format(n), x, count=1) if k == 0 else x for k, x in enumerate(s04.get('notes') or [])]
    note = ('GE 原廠編號（來源類型 8）：GE 文件的設備編號（例 96PG-5B）→ 對到的 AMS 設備；只收對到設備的編號，對照方式見查詢卡「GE 原廠編號」段。'
            '這類列的「此字串對應設備數」>1 多半是 G11、G12 兩台（或 AMS 同位號的另一筆設備紀錄），不是歧義')
    s04['notes'] = [x for x in s04['notes'] if not x.startswith('GE 原廠編號（來源類型 8）')] + ([note] if new else [])
    b04 = dumps(s04).encode('utf-8')
    s00p = os.path.join(outdir, 'sheets', '00.json')
    s00 = load(s00p)
    for row in s00.get('rows') or []:
        cells = row.get('cells') or []
        if any(isinstance(c.get('l'), dict) and c['l'].get('s') == '04' for c in cells):
            for c in cells:
                if c.get('c') == 5 and isinstance(c.get('v'), int):
                    c['v'] = n
    b00 = dumps(s00).encode('utf-8')
    man = load(os.path.join(outdir, 'manifest.json'))
    for s in man['sheets']:
        if s['id'] == '04':
            s['rows'] = s['toc_rows'] = n
            s['bytes'] = len(b04)
        elif s['id'] == '00':
            s['bytes'] = len(b00)
    return len(new), keys, skipped, [(p, b04), (s00p, b00)], man


# ------------------------------------------------------------------ 文件全文檢索（docsearch）與 Drive 連結
def load_docsearch(path):
    """tools/db/docmap_docsearch.py 的輸出；沒有就 None（此來源略過）。"""
    if not path or not os.path.exists(path):
        return None
    j = load(path)
    if 'by_alias' not in j or 'docs' not in j:
        raise SystemExit('docsearch.json 格式不對：' + path)
    return j


def docsearch_apply(sec, ds, al):
    x = ds['by_alias'].get(al) if ds else None
    if x and x.get('rows'):
        sec['docsearch'] = {'rows': x['rows']}


def docsearch_index(ds, searched, docs, src_stats):
    """把 docsearch 的 searched／docs／stats 併進 index（舊的 docsearch 項先清掉）。"""
    searched = {k: v for k, v in searched.items() if k != 'docsearch'}
    docs = {k: v for k, v in docs.items() if not k.startswith('docsearch|')}
    src_stats = {k: v for k, v in src_stats.items() if k != 'docsearch'}
    if ds:
        searched['docsearch'] = ds['searched']
        docs.update(ds['docs'])
        st = ds.get('stats') or {}
        src_stats['docsearch'] = {k: st.get(k) for k in ('aliases_matched', 'rows', 'docs', 'with_url', 'per_category', 'extracted', 'notes') if k in st}
        src_stats['docsearch']['index'] = ds.get('index')
    return searched, docs, src_stats


# ------------------------------------------------------------------ 圖控 HMI 畫面位置（hmi）
HMI_ROUTE = {'obj': '物件參照', 'var': '畫面字串', 'pointdb': '點位索引', 'dcdas': '控制器 display_screen'}
HMI_ROUTE_WHY = {
    'obj': '畫面檔物件的屬性包（device／caption／aliasSignal…）代入畫面變數後切出位號，並帶該物件的矩形座標',
    'var': '畫面檔字串裡沒被物件模型收進去的點位字串（補漏，無座標）',
    'pointdb': 'navigation/tp_actPt_navPointSearchDbStd.csv 的「點位,機組,畫面檔」（無座標）',
    'dcdas': '控制器索引的 variable.display_screen（無座標）',
}
HMI_ROUTE_SRC = {'obj': '.cim 物件屬性包＋選單變數代入', 'var': '.cim 字串補漏', 'pointdb': 'navPointSearchDbStd.csv',
                 'dcdas': '控制器 variable.display_screen'}   # 逐列的短來源字串（完整說明在 index.searched.hmi[0].why）
HMI_SLUG_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$')
HMI_MULTI_RE = re.compile(r'([A-Za-z0-9_\-]*[A-Za-z0-9])((?:\\\d+)+)')   # 多點簡寫 BASE\NNN\NNN（與 hmi_index.MULTI_RE 同）
HMI_CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫'   # 同一張畫面上多個標記的編號（card.js 的 .hmi-mk 用同一組字）


def load_hmi(path, shots_dir, nav_path, ge_path=None):
    """tools/db/hmi_index.py 的輸出（位號→畫面與座標）＋ tools/db/hmi_shots.py 的縮圖目錄＋ hmi_nav.py 的逐列選單路徑。
    沒有 hmi.json 就回 None（此來源整段略過）。縮圖目錄缺席時只有畫面名稱與路徑、沒有影像。
    ge_path＝tools/db/hmi_ge.py 的輸出（GE 原廠編號的圖控位置，v10）：有就放進 `_ge`（{條目鍵: [命中…]}），給 GE 編號卡用；
    AMS 設備的 sec.hmi 一個字都不受影響（hmi_rows 只讀 by_tag）。"""
    if not path or not os.path.exists(path):
        return None
    j = load(path)
    if 'by_tag' not in j or 'screens' not in j:
        raise SystemExit('hmi.json 格式不對（缺 by_tag／screens）：' + path)
    j['_shots_dir'] = shots_dir if shots_dir and os.path.isdir(shots_dir) else None
    j['_shots'] = {}
    if j['_shots_dir']:
        ip = os.path.join(j['_shots_dir'], 'index.json')
        if os.path.exists(ip):
            j['_shots'] = {k.lower(): v for k, v in load(ip).items()}
    # hmi_nav.json 的 nav／units 是「逐列對齊」的（hmi.json 的 screens[].units 已去重排序，不能逐列對應）
    j['_nav'] = {k.lower(): v for k, v in load(nav_path).items()} if nav_path and os.path.exists(nav_path) else {}
    j['_ge'] = None
    if ge_path and os.path.exists(ge_path):
        g = load(ge_path)
        if g.get('kind') != 'hmi_ge' or not isinstance(g.get('by_ge'), dict):
            raise SystemExit('hmi_ge.json 格式不對（kind／by_ge）：' + ge_path)
        bad = sorted({h.get('screen') for v in g['by_ge'].values() for h in v if h.get('screen') not in j['screens']})
        if bad:
            raise SystemExit('hmi_ge.json 引用了 hmi.json 沒有的畫面 %s——兩支產生器讀的不是同一批畫面檔，先重跑 hmi_index.py 與 hmi_ge.py' % bad[:5])
        j['_ge'], j['_ge_stats'] = g['by_ge'], g.get('stats') or {}
    return j


def hmi_slug(screen_key):
    """畫面檔名 → card/hmi/<slug>.json 的檔名（去掉 .cim；只允許安全字元，否則以 sha1 代替）。"""
    base = re.sub(r'\.cim$', '', screen_key, flags=re.I).replace('/', '__')
    if not HMI_SLUG_RE.match(base):
        import hashlib
        base = 'x' + hashlib.sha1(screen_key.encode('utf-8')).hexdigest()[:12]
    return base


def hmi_unit_slug(unit):
    """選單機組 'H11.' → 'H11'（檔名用；與 hmi_shots.unit_slug 同規則）。"""
    return re.sub(r'[^0-9A-Za-z._-]+', '_', (unit or '').rstrip('.')) or 'x'


def hmi_nav_rows(hm, key, unit):
    """該畫面的選單路徑：優先取「以這一列選單（機組 unit）開啟」的那一列，否則全部列。
    回傳 ([路徑陣列…], exact)；exact=False 代表不是這台儀器那一列（只能列出全部）。"""
    nv = hm['_nav'].get(key.lower()) or hm['screens'].get(key) or {}
    nav = nv.get('nav') or []
    units = nv.get('units') or []
    if unit and len(units) == len(nav):
        hit = [nav[i] for i in range(len(nav)) if units[i] == unit]
        if hit:
            return hit, True
    return nav, False


def hmi_screen_name(hm, key):
    """畫面名稱（中文標題優先，附英文）與畫面上標題。來源裡沒有中文（hmi_nav.py 已查證：
    languageTranslation 只有西／日／法文，473 個 .cim 的字串 0 個含中文），所以 zh 目前一律 None。"""
    sc = hm['screens'].get(key) or {}
    nv = hm['_nav'].get(key.lower()) or {}
    zh = sc.get('title_zh') or nv.get('title_zh')
    en = nv.get('label') or sc.get('title_en') or nv.get('title_en') or re.sub(r'\.cim$', '', key, flags=re.I)
    cap = nv.get('caption_en')
    name = ('%s（%s）' % (zh, en)) if zh and en and zh != en else (zh or en)
    if cap and cap.lower() != str(en).lower():
        name += '（畫面上標題「%s」）' % cap
    return name, zh, en, cap


def hmi_marks(ents):
    """同一畫面上這支位號的所有標記 → [[中心 x, 中心 y, 框寬, 框高]]（0~1 比例、左上為原點）。
    框寬／高為 0＝只標點不畫框（直線、文字錨點；hmi_index 的 w／h 有 60 筆為 0，其中 2 筆橫跨畫面三成以上）。
    同一畫面同時有「有框」與「線狀」標記時只留有框的。"""
    boxed, lines = [], []
    for e in ents:
        x, y = e.get('x'), e.get('y')
        if x is None or y is None:
            continue
        w = float(e.get('w') or 0.0)
        h = float(e.get('h') or 0.0)
        c = [round(float(x) + w / 2.0, 5), round(float(y) + h / 2.0, 5)]
        if w > 0 and h > 0:
            boxed.append(c + [round(w, 5), round(h, 5)])
        else:
            lines.append(c + [0, 0])       # 直線／文字錨點（hmi_index 的 w／h 有 60 筆為 0）：只標中點
    use = sorted({tuple(m) for m in (boxed or lines)})
    # **第一筆＝「所在位置」文字描述的那處**（面積最大者）：前端照陣列順序編號，文字與圖上的 ① 才對得起來
    use.sort(key=lambda m: (-(m[2] * m[3]), m[1], m[0]))
    return [list(t) for t in use]


def hmi_pos_text(marks):
    """標記 → 人看得懂的位置：「畫面左 54%／上 44%（約佔畫面寬 7%、高 4%）」。沒有座標時空字串。
    marks[0] 是 hmi_marks 排好的主標記，前端在圖上把它編成 ①，所以多處時要把編號講清楚（審查意見 3）。"""
    if not marks:
        return ''
    primary = marks[0]
    t = '畫面左 %d%%／上 %d%%' % (round(primary[0] * 100), round(primary[1] * 100))
    if primary[2] > 0 and primary[3] > 0:
        t += '（約佔畫面寬 %d%%、高 %d%%）' % (max(1, round(primary[2] * 100)), max(1, round(primary[3] * 100)))
    if len(marks) > 1:
        t += ('＝圖上標記 ①；這支位號在同一張畫面另有 %d 處（圖上 %s），位置可能幾乎重疊'
              % (len(marks) - 1, '、'.join('%s' % HMI_CIRCLED[i] for i in range(1, min(len(marks), len(HMI_CIRCLED))))))
    return t


HMI_VAR_RE = re.compile(r'\{[A-Za-z_][A-Za-z0-9_]*\}')


def hmi_ref_is_template(ref):
    """`aliasSignal={device}` 這種「`=` 右邊整個是 {變數}」的參照：對操作員零資訊，挑 ref 時排到最後。"""
    v = (ref or '').split('=', 1)[-1]
    return 0 if re.search(r'[A-Za-z0-9]', HMI_VAR_RE.sub('', v)) else 1


def hmi_ref_text(ref):
    """「對應方式」顯示用的參照字串：CIMPLICITY 多點簡寫 `\\NNN` 原封不動看起來像亂碼，補一句白話
    （hmi_index 已把手足位號各自展開進索引，這裡只是說明，不影響資料）。"""
    if not ref:
        return ''
    m = HMI_MULTI_RE.search(ref)
    if not m:
        return ref
    base, tail = m.group(1), m.group(2)
    sibs = [base]
    for seg in tail.split('\\')[1:]:
        if 0 < len(seg) < len(base):
            sibs.append(base[:-len(seg)] + seg)
    if len(sibs) < 2:
        return ref
    return '%s　（結尾的「%s」是圖控的多點簡寫＝同一個物件掛 %s 共 %d 支，每一支都另有自己的索引）' % (
        ref, tail, '、'.join(s.split('}')[-1] for s in sibs), len(sibs))


def hmi_rows(hm, tag):
    """一台設備的 sec.hmi.rows：每個（畫面, 選單機組）一組 4 列（畫面／導覽路徑／所在位置／對應方式）。
    第一列的 extra 帶整組顯示需要的東西（nav、img、marks…），其餘列只帶 {s, g} 供前端分組。"""
    ents = (hm['by_tag'].get(tag) or []) if tag else []
    if not ents:
        return []
    groups = {}
    for e in ents:
        groups.setdefault((e['screen'], e.get('unit') or ''), []).append(e)
    rows = []
    for gi, (gk, ge) in enumerate(sorted(groups.items())):
        key, unit = gk
        sc = hm['screens'].get(key) or {}
        name, zh, en, cap = hmi_screen_name(hm, key)
        nav, exact = hmi_nav_rows(hm, key, unit)
        marks = hmi_marks(ge)
        routes = sorted({e['route'] for e in ge})
        # 挑「對應方式」要顯示的參照字串：物件參照優先，再排掉只剩 {變數} 的樣板（hmi_index 已先一步避開，這裡是第二道）
        ref = next((e.get('ref') for e in sorted(
            ge, key=lambda x: (x['route'] != 'obj', hmi_ref_is_template(x.get('ref')),
                               x['route'], x.get('ref') or '')) if e.get('ref')), None)
        # 有沒有影像：hmi.json 的 img 來自 hmi_shots 的 index.json，但 --skip-hmi 時兩者可能不同步，所以也看縮圖索引
        img = bool(sc.get('img') or (hm['_shots'].get(key.lower()) or {}).get('file'))
        pre = src_prefix('hmi')
        src = '%s · 畫面檔 %s' % (pre, key)
        base = {'s': key, 'g': gi}
        first = dict(base, nav=nav, img=img, marks=marks, routes=routes)
        if unit:
            first['unit'] = unit
        if not exact and len(nav) > 1:
            first['nav_all'] = 1   # 選單列與這台儀器的機組對不起來：nav 是該畫面全部選單列
        if ref:
            first['ref'] = ref
        rows.append(['圖控畫面', name, 'hmi', src, first])
        navtxt = '；'.join(' › '.join(x for x in r if x) for r in nav) or '（不在操作員導覽選單上）'
        # unit＝「開啟這張畫面的那一列選單項的機組欄」，**不是**這台儀器所屬機組（同一張畫面會被兩列選單以兩組
        # 畫面變數開啟，69 台因此在同一張畫面出現兩次、紅框完全相同）。用詞必須寫成「以…選單開啟」。
        rows.append(['導覽路徑', navtxt + (('　·　以選單機組 %s 開啟' % unit) if unit else ''), 'hmi',
                     '%s · 選單樹 CIMNavigationMenuItemsStd.csv%s' % (pre, '' if exact else '（此畫面全部選單列）'), dict(base)])
        pos = hmi_pos_text(marks)
        rows.append(['所在位置', pos or '（此對應方式沒有畫面座標）', 'hmi',
                     ('%s · 物件矩形（設計座標 %s×%s twips，y 軸向上，已換成左上原點 0~1 比例）'
                      % (pre, hm['stats'].get('design_w'), hm['stats'].get('design_h'))) if pos
                     else '%s · 此對應方式只知道「在這張畫面」，沒有座標' % pre, dict(base)])
        rows.append(['對應方式', '／'.join(HMI_ROUTE.get(r, r) for r in routes) + (('：%s' % hmi_ref_text(ref)) if ref else ''), 'hmi',
                     '%s · %s' % (pre, '／'.join(HMI_ROUTE_SRC.get(r, r) for r in routes)), dict(base)])
    return rows


def hmi_apply(sec, hm, tag):
    rows = hmi_rows(hm, tag) if hm else []
    if rows:
        sec['hmi'] = {'rows': rows}


def hmi_write_images(outdir, out, hm, stats, ge_used=None):
    """收集 out 裡 sec.hmi 真的用到的畫面 → 寫 card/hmi/<slug>[__<選單機組>].json（{w,h,mime,b64}，走既有 *.json 加密路徑），
    回傳 index.hmi（畫面中繼資料＋檔案清單）。先整個清掉 card/hmi/ 才寫，避免掉出覆蓋範圍的畫面留下孤兒密文。

    影像來源兩種（hmi_shots 的 index.json）：
      執行時截圖（source='runtime capture'）——**逐「選單機組」各一張**，同一張畫面在 HRSG11／HRSG12 的現值不同，
        不可共用；只發布這張卡真的用得到的那幾組，`meta.variants[選單機組]` 給前端挑，`meta.file` 是挑不到時的退路。
      設計時 ThumbNail（EMF）——整個畫面一張，沒有機組之分（值是 ###）。
    ge_used＝GE 編號卡（card/getag.json 的 hm 列）用到的 {畫面: {'rows', 'units'}}（ge_loc_build）：一起發布，與 AMS 設備共用同一個檔；
    stats 的 devices 仍只算 AMS 設備，GE 另記 ge_screens。"""
    import base64
    import shutil
    hdir = os.path.join(outdir, 'card', 'hmi')
    if os.path.isdir(hdir):
        shutil.rmtree(hdir)
    if hm is None:
        return None
    used, ndev = {}, 0
    for al, o in out.items():
        rs = ((o.get('sec') or {}).get('hmi') or {}).get('rows') or []
        if rs:
            ndev += 1
        for r in rs:
            ex = r[4] if len(r) > 4 else None
            if isinstance(ex, dict) and ex.get('s'):
                u = used.setdefault(ex['s'], {'rows': 0, 'units': set()})
                u['rows'] += 1
                if ex.get('unit'):
                    u['units'].add(ex['unit'])
    n_ams = len(used)
    for key, g in sorted((ge_used or {}).items()):
        u = used.setdefault(key, {'rows': 0, 'units': set()})
        u['ge'] = g['rows']
        u['units'] |= set(g['units'])
    screens, files, total, nrt = {}, [], 0, 0
    if used:
        os.makedirs(hdir, exist_ok=True)

    def put(rel, path, w, h):
        """縮圖檔 → card/hmi/<rel>（{w,h,mime,b64}；走既有 *.json 加密路徑）；回傳寫出的位元組數。"""
        b = open(path, 'rb').read()
        data = dumps({'w': w, 'h': h, 'mime': 'image/webp' if path.lower().endswith('.webp') else 'image/png',
                      'b64': base64.b64encode(b).decode('ascii')}).encode('utf-8')
        with open(os.path.join(outdir, rel), 'wb') as f:
            f.write(data)
        return len(data)

    for key in sorted(used):
        sc = hm['screens'].get(key) or {}
        name, zh, en, cap = hmi_screen_name(hm, key)
        nv = hm['_nav'].get(key.lower()) or {}
        meta = {'title': name, 'en': en, 'nav': nv.get('nav') or sc.get('nav') or [], 'img': False, 'rows': used[key]['rows']}
        if used[key].get('ge'):
            meta['ge'] = used[key]['ge']   # GE 編號卡用到這張畫面的列數（v10）
        if zh:
            meta['zh'] = zh
        if cap:
            meta['caption'] = cap
        shot = hm['_shots'].get(key.lower()) or {}
        rt = shot.get('runtime') or {}
        # 只發布這張卡用得到的（畫面, 選單機組）；沒有 unit 的列（route 不帶機組）退回 primary
        want = [u for u in sorted((used[key]['units'] | {rt.get('primary')}) & set(rt.get('variants') or {}))] if rt else []
        variants = {}
        for u in want:
            v = rt['variants'][u]
            src = os.path.join(hm['_shots_dir'], v['file']) if hm['_shots_dir'] else None
            if not (src and os.path.exists(src)):
                continue
            rel = 'card/hmi/%s__%s.json' % (hmi_slug(key), hmi_unit_slug(u))
            n = put(rel, src, v['w'], v['h'])
            variants[u] = {'file': rel, 'w': v['w'], 'h': v['h'], 'bytes': n}
            files.append(rel)
            total += n
        if variants:
            fu = rt['primary'] if rt.get('primary') in variants else sorted(variants)[0]
            first = variants[fu]
            # 'unit' ＝ meta.file 那張是哪一組：前端挑不到這一列的機組而退回 meta.file 時，
            # 說明列要能寫「這張是 X 的畫面，沒有 Y 的截圖」，不能讓使用者以為看到的是自己那一組的現值
            meta.update({'img': True, 'source': 'runtime', 'captured': rt.get('captured'), 'variants': variants,
                         'unit': fu, 'file': first['file'], 'w': first['w'], 'h': first['h'], 'bytes': first['bytes']})
            nrt += 1
        else:
            emf = shot.get('emf') or (shot if shot.get('source') != 'runtime capture' else {})
            fn = emf.get('file')
            src = os.path.join(hm['_shots_dir'], fn) if (fn and hm['_shots_dir']) else None
            if src and os.path.exists(src):
                w, h = emf.get('w'), emf.get('h')
                rel = 'card/hmi/%s.json' % hmi_slug(key)
                n = put(rel, src, w, h)
                meta.update({'img': True, 'source': 'emf', 'file': rel, 'w': w, 'h': h, 'bytes': n})
                files.append(rel)
                total += n
        screens[key] = meta
    hs = hm['stats']
    captured = next((m.get('captured') for m in screens.values() if m.get('captured')), None)
    ix = {'screens': screens, 'files': sorted(files), 'bytes': total, 'captured': captured,
          'design': [hs.get('design_w'), hs.get('design_h')], 'canvas': [1920, 1080],
          'note': ('x／y 是 0~1 的畫面比例、左上為原點，可直接乘縮圖寬高；marks 每筆＝[中心 x, 中心 y, 框寬, 框高]，'
                   '框寬／高為 0 時只標點不畫框，**marks[0] 就是「所在位置」文字描述的那處**（前端照陣列順序編 ①②③）。'
                   '畫面影像兩種來源，看 screens[].source：runtime＝%s 在機組上拍的執行時畫面（原畫面 1920×1080＝標記的座標系，'
                   '發布的是縮成寬 1280 的 WebP；**逐選單機組各一張**，用 screens[].variants[選單機組] 挑；畫面上的數值是當時的現值，不是即時值）；'
                   'emf＝.cim 內含的設計時 ThumbNail，沒有執行時截圖的畫面才用，數值顯示成 ### 、部分標題是 CAPTION 佔位，'
                   '左側導覽抽屜／左上角錶框／選單列／Loading 提示原本是所有選單項疊在一起，已在產圖時塗成空面板。'
                   'stats.screens_total＝建索引的根目錄畫面數；screens_all＝Screens 遞迴全部 .cim；'
                   'excluded＝子目錄的元件面板／函式庫（不建索引，但字串掃過，見 searched.hmi[0].why）。'
                   % (captured or '使用者')),
          'stats': {'devices': ndev, 'screens': len(screens), 'screens_ams': n_ams, 'ge_screens': sum(1 for m in screens.values() if m.get('ge')),
                    'screens_with_img': sum(1 for m in screens.values() if m.get('img')),
                    'files': len(files), 'screens_runtime': nrt,
                    'covered': hs.get('covered'), 'covered_pct': hs.get('covered_pct'),
                    'ams_tags_base': hs.get('ams_tags_base'), 'covered_ff': hs.get('covered_ff'), 'ff_total': hs.get('ff_total'),
                    'entries': hs.get('entries'), 'entries_with_xy': hs.get('entries_with_xy'),
                    'screens_total': hs.get('screens_total'), 'screens_with_tags': hs.get('screens_with_tags'),
                    # 卡片「查無」那句要講清楚掃了幾個、排除了幾個，不然同一張卡會出現 248 與 473 兩個數字
                    'screens_all': hs.get('screens_all') or ((hs.get('screens_total') or 0) + (hs.get('screens_subdir_skipped') or 0)),
                    'excluded': hs.get('screens_subdir_skipped') or 0,
                    'excluded_scanned': 1 if (hs.get('excluded_scan') or {}) else 0,
                    'excluded_tag_hits': (hs.get('excluded_scan') or {}).get('tag_hits'),
                    'excluded_ff_hits': (hs.get('excluded_scan') or {}).get('ff_hits')}}
    stats['hmi'] = dict(ix['stats'], bytes=total)
    nimg = sum(1 for m in screens.values() if m.get('img'))
    print('hmi: %d 台設備有畫面對應，%d 個畫面有影像（%d 個用 %s 的執行時截圖、%d 個用設計時 ThumbNail）；'
          '發布 %d 個影像檔共 %d KB；%d 個畫面兩種影像都沒有，只能顯示名稱'
          % (ndev, nimg, nrt, captured or '執行時', nimg - nrt, len(files), total // 1024, len(screens) - nimg))
    return ix


def hmi_excluded_text(hm):
    """「子目錄那些 .cim 怎麼辦」的一句話，數字一律取自 hmi_index 的 stats.excluded_scan（不是口頭聲明）。
    沒跑掃描（--no-excluded-scan）時就只說排除、不聲稱 0 命中。"""
    hs = hm['stats']
    ex = hs.get('excluded_scan') or {}
    sub = hs.get('screens_subdir_skipped') or 0
    if not sub:
        return ''
    if not ex:
        return '另 %d 個在子目錄（元件面板與函式庫範本，沒有選單列也沒有畫面變數）不列入索引；' % sub
    dirs = '／'.join('%s %d' % (k, v) for k, v in sorted((ex.get('dirs') or {}).items(), key=lambda kv: -kv[1])[:3])
    tags = ex.get('tags') or []
    extra = [t for t in tags if t not in hm['by_tag']]
    if not tags:
        found = 'AMS 位號 0 命中'
    elif not extra:
        found = 'AMS 位號 %d 支命中，但這 %d 支都已經由根目錄畫面涵蓋（沒有因此漏掉任何一台）' % (len(tags), len(tags))
    else:
        found = 'AMS 位號 %d 支命中，其中 %d 支只出現在這些元件面板裡（%s）' % (len(tags), len(extra), '、'.join(extra[:5]))
    return ('另 %d 個在子目錄（%s）＝元件面板與函式庫範本，沒有選單列也沒有畫面變數，不列入索引，但字串已逐條掃過：'
            '%s、FF 位號 %d 命中（共 %d 個 .cim 都查過）；'
            % (sub, dirs, found, ex.get('ff_hits') or 0, ex.get('screens_all') or (sub + (hs.get('screens_total') or 0))))


def hmi_doc(hm):
    """index.searched['hmi'] 的一筆：把圖控畫面檔目錄當一份「文件」描述（不含本機絕對路徑、沒有 Drive 連結）。"""
    hs = hm['stats']
    why = ('GE CIMPLICITY／ActivePoint 的 .cim 畫面檔（唯讀原檔，未修改）：物件屬性包＋選單變數解析出位號，'
           '物件矩形換算成畫面比例；畫面影像優先用使用者在機組上拍的執行時截圖（逐選單機組各一張），'
           '沒拍到的畫面才退回 .cim 內含的設計時 ThumbNail（EMF，值顯示成 ###）。'
           '索引建在 Screens 根目錄的 %s 個畫面（操作員能從選單導覽到的）；%s'
           '覆蓋 %s/%s 台（%s%%）；FF 設備 %s/%s。畫面 %s 個（其中 %s 個畫面引用到 AMS 位號）。'
           % (hs.get('screens_total'), hmi_excluded_text(hm),
              hs.get('covered'), hs.get('ams_tags_base'), hs.get('covered_pct'), hs.get('covered_ff'),
              hs.get('ff_total'), hs.get('screens_total'), hs.get('screens_with_tags')))
    return {'doc_id': 'hmi-screens', 'rev': '%s 個畫面檔' % hs.get('screens_total'),
            'ref': '圖控畫面檔（CIMPLICITY／ActivePoint .cim，根目錄 %s 個）' % hs.get('screens_total'),
            'title': '圖控 HMI 畫面檔（GE CIMPLICITY／ActivePoint）', 'folder': 'AMS/Screens（圖控畫面檔目錄，唯讀）',
            'used': True, 'why': why}


def load_drive_map(path):
    if not path or not os.path.exists(path):
        return None
    m = load(path)
    return m if isinstance(m.get('files'), dict) else None


def add_drive_urls(docs, drive):
    """index.docs 每份文件以「資料夾/檔名」（小寫）對照 drive_map → url（Google 雲端硬碟）。回傳 (有 url 的份數, 其中連到別版次的份數)。
    title 不是檔名時（docindex 的 title 是文件標題；eomr 少了副檔名）退而以 key 的 文件編號-版次 在同資料夾找檔名開頭相符的檔；
    只對到文件編號、版次不同的（同資料夾恰有一份）仍給 url 但加 url_note「雲端只找到 <檔名>（版次與本站資料來源 X 不同）」，
    前端把它列在「Google 雲端硬碟（版次不同：檔名）」，工程師才不會以為點開的就是本站引用的那一版。"""
    if not drive:
        return sum(1 for d in docs.values() if d.get('url')), sum(1 for d in docs.values() if d.get('url') and d.get('url_note'))
    files = drive['files']
    by_folder = {}
    for rel in files:
        fo, _, base = rel.rpartition('/')
        by_folder.setdefault(fo, []).append(base)
    n = n_alt = 0
    for key, d in docs.items():
        if not d.get('url'):
            d.pop('url_note', None)
            folder = (d.get('folder') or '').strip('/')
            folder = '' if folder == '.' else folder
            title = (d.get('title') or '').lower()
            rel = ((folder + '/') if folder else '') + title
            fid = files.get(rel.lower())
            if not fid:
                cands = []
                names = by_folder.get(folder.lower(), [])
                parts = key.split('|')
                doc_id = parts[1].lower() if len(parts) > 1 and parts[1] and parts[1][:2].lower() == 'ht' else ''
                rev = parts[2].lower() if len(parts) > 2 else ''
                for base in names:
                    if title and base in (title + '.pdf', title + '.xlsx', title + '.xls'):
                        cands.append((0, len(base), base))            # 標題就是檔名（少了副檔名）
                    elif doc_id and rev and re.match(re.escape(doc_id + '-' + rev) + r'(?![0-9a-z])', base):
                        cands.append((1 if '(1)' not in base else 2, len(base), base))   # 文件編號-版次 開頭
                    elif doc_id and base.startswith(doc_id + '-'):
                        cands.append((5 if '(1)' not in base else 6, len(base), base))   # 只對到文件編號（版次不同或不明）
                if cands:
                    cands.sort()
                    if cands[0][0] < 5 or len([c for c in cands if c[0] >= 5]) == 1:
                        base = cands[0][2]
                        fid = files.get(((folder.lower() + '/') if folder else '') + base)
                        if fid and cands[0][0] >= 5:  # 別版次（或版次不明）的同編號檔：仍給連結但標明
                            fm = re.match(re.escape(doc_id) + r'-([0-9a-z]{1,2})(?![0-9a-z])', base)
                            if fm and rev:
                                d['url_note'] = '雲端只找到 %s（版次 %s，與本站資料來源的版次 %s 不同）' % (base, fm.group(1).upper(), rev.upper())
                            else:
                                d['url_note'] = '雲端只找到 %s（檔名版次不明，未必是本站資料來源的版次 %s）' % (base, rev.upper() or '?')
            if fid:
                d['url'] = 'https://drive.google.com/open?id=%s' % fid
        if d.get('url'):
            n += 1
            if d.get('url_note'):
                n_alt += 1
    return n, n_alt


DOCNO_VAL_RE = re.compile(r'(HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4})(?:-([0-9A-Z]{1,2})(?![0-9A-Za-z]))?')
COPY_PATH_RE = re.compile(r'(^|/)(_舊版|_fix[^/]*|_chunks|_nb[^/]*|_缺漏補齊[^/]*|_xlsx_pdf|am10|am20|am30|所有線路圖)/|'
                          r'/(?:[a-z0-9]{3})?[a-z]{3}[a-z0-9]{2}[a-z]{2}\d{3}[^/]*/\d{2}_[^/]+/[^/]+$', re.I)


def _rev_key(rev):
    rev = (rev or '').upper()
    return (2, int(rev), '') if rev.isdigit() else ((1, 0, rev) if rev else (0, 0, ''))


def resolve_doc_numbers(out, docs, drive):
    """欄位值本身就是文件編號時（端子表／儀器清單的 P&ID、邏輯圖、Hook-up 圖、位置圖、EOMR「亦見於」…），
    把編號對到文件庫裡「那份文件」（檔名以編號開頭；有指定版次取該版，否則取最高版次，數字 > 字母；PDF 優先、排除副本夾）：
    docs['file|<編號>|<版次>'] = {title, folder, url}，index.doc_no = {編號: key}。前端讓這些值直接開那份圖，而不是提到它的來源文件。"""
    if not drive:
        return {}
    wanted = {}
    for al, o in out.items():
        for kind, sec in (o.get('sec') or {}).items():
            for ent in sec.get('entries') or []:
                for r in ent.get('rows') or []:
                    docno_wanted(r[1], wanted)
    return resolve_wanted(wanted, docs, drive)


def docno_wanted(val, wanted):
    """欄位值裡的每個文件編號（一格可能寫好幾個：GE 清單的位置圖「HT0-1-GZD01-M0147 HT0-1-GZD01-M0166」）→ wanted[編號] 加上指定的版次。"""
    for m in DOCNO_VAL_RE.finditer(str(val or '')):
        wanted.setdefault(m.group(1).upper(), set()).add((m.group(2) or '').upper())


def resolve_wanted(wanted, docs, drive):
    """{編號: {指定版次…}} → docs 補 file|編號|版次、回傳 {編號: key}（resolve_doc_numbers 的規則；GE 編號卡 ge_doc_numbers 也用）。"""
    by_no = {}
    for rel in drive['files']:
        if COPY_PATH_RE.search('/' + rel):
            continue
        base = rel.rpartition('/')[2]
        m = DOCNO_VAL_RE.match(base.upper())
        if m:
            by_no.setdefault(m.group(1), []).append((rel, (m.group(2) or '').upper()))
    doc_no = {}
    for no, revs in wanted.items():
        cands = by_no.get(no)
        if not cands:
            continue
        want = {r for r in revs if r}

        def score(c):
            rel, rev = c
            base = rel.rpartition('/')[2]
            return (0 if rev in want else 1, tuple(-x if isinstance(x, int) else x for x in _rev_key(rev)[:2]),
                    0 if base.endswith('.pdf') else 1, 1 if '(1)' in base or '(2)' in base else 0, len(rel))
        rel, rev = sorted(cands, key=score)[0]
        key = 'file|%s|%s' % (no, rev)
        if key not in docs:
            fo, _, base = rel.rpartition('/')
            if rev in want:
                why = '欄位值的文件編號對檔名（指定版次）'
            elif want:
                why = '欄位值的文件編號對檔名：指定版次 %s 不在雲端，改開最高版次 %s' % ('／'.join(sorted(want)), rev or '?')
            else:
                why = '欄位值的文件編號對檔名（未指定版次，取最高版次）'
            docs[key] = {'title': base, 'folder': fo or '.', 'why': why, 'url': 'https://drive.google.com/open?id=%s' % drive['files'][rel]}
        doc_no[no] = key
    return doc_no


GE_MULTI_DOC_RE = re.compile(r'^(其他出處|文件不一致|文件狀態|其他文件寫的 KKS)')


def ge_doc_numbers(gcard, gcdocs, drive, old=None):
    """GE 編號卡（v12）：規格塊與共同列裡寫的文件編號（位置圖 GZD01-M0166、P&ID GFD01-D0001、Hook-up…）→ gcdocs 補 file|…、回傳 doc_no，
    前端 valueLink 讓這些值直接開那份圖（同 AMS 設備卡的 index.doc_no）。--no-drive-map 時沿用上一份 getag.json 的 doc_no 與 file|… 文件。
    GE 自己的圖號（307T1798、137T9778_1）不是 HT 編號，不在這裡處理。"""
    if not drive:
        old = old or {}
        keep = {no: k for no, k in (old.get('doc_no') or {}).items() if k in (old.get('docs') or {})}
        for k in set(keep.values()):
            gcdocs.setdefault(k, dict(old['docs'][k]))
        return keep
    wanted = {}
    for x in gcard['entries']:
        for r in (x.get('c') or {}).get('rows') or []:
            if not GE_MULTI_DOC_RE.match(r[0]):   # 列了好幾份出處檔名的格：前端不把值當文件編號（card.js MULTI_DOC）
                docno_wanted(r[1], wanted)
        for b in x.get('sp') or []:
            for r in b.get('rows') or []:
                docno_wanted(r[1], wanted)
    return resolve_wanted(wanted, gcdocs, drive)


# ------------------------------------------------------------------ P&ID 圖面位置（pid）
# 與圖控 HMI 那一段平行、各自獨立：hmi_* 函式一個字都不動（圖控輸出必須位元組不變），這裡另寫 pid_*。
PID_RELS = ('exact', 'neutral', 'typical', 'loop', 'train')   # 圖上畫的東西為什麼算這一台（pid_index 每支位號只留最好的一級）
# 標籤在圖上拆成幾段寫、合併後才對上的（pid_lib 的 form；OCR 命中是 ocr／ocr-stacked／ocr-inline，去掉 ocr- 後查同一張表；
# ocr-fix＝OCR 把相近字元讀錯、校正後才對上，另外處理：要把原本讀到的字（hit 的 raw）講出來，見 pid_fix_text）
PID_FORM_TEXT = {'stacked': '上下兩行拆寫合併', 'prefixed': '機組前綴與位號分開寫，合併後對上', 'inline': '同一行分兩段寫，合併後對上'}
# hit 的 note：0＝儀器符號旁的標籤；1～4＝圖上「提到」這支位號的地方（引用），**不是儀器符號的位置**——2026-10-10 六組獨立稽核的裁決
# （位置都對，錯在「這一處算什麼」：跨圖旗標、空氣分配圖的用氣點、儀器清單的一列，都曾被當成儀器本身的位置寫上卡片）。
# PID_NOTE_NAME＝這一處是什麼（短，給「所在位置」與多處標記的說明用）；PID_NOTE_TEXT＝「圖上標示」那一列的整句。
# 認不得的代碼（將來 pid_index 再加新的一類）一律當 1 的說法的上位講法「不是儀器符號旁的標籤」，不會被當成符號。
PID_NOTE_NAME = {1: '圖上註記或表格（儀器清單）裡的文字', 2: '跨圖訊號旗標', 3: '儀用／廠用空氣分配圖上的用氣點', 4: '迴路詳圖（TYPICAL 小圖）裡的標籤',
                 5: '位置圖上設備表（DEVICE TAG／BILL OF MATERIAL…）的一列'}
PID_NOTE_TEXT = {1: '這一處是圖上註記或表格（儀器清單）裡的文字，不是儀器符號旁的標籤',
                 2: '這一處是跨圖訊號旗標（接往另一張圖的訊號引用），不是儀器本身的位置',
                 3: '這一處是儀用／廠用空氣分配圖上的用氣點（這顆閥的供氣接點），不是閥在製程管線上的位置',
                 4: '這一處在圖紙上的迴路詳圖（TYPICAL 小圖）裡，不是主流程圖上的位置',
                 5: '這一處是位置圖上設備表（DEVICE TAG／BILL OF MATERIAL…）的一列，不是圖上指著元件本體的位置'}   # v12：loc_ge.py
PID_NOTE_OTHER = ('圖上提到這支位號的地方', '這一處只是圖上提到這支位號的地方，不是儀器符號旁的標籤')   # 認不得的 note 代碼：(NAME, TEXT)
PID_LOOKALIKE = '相近字元（0／O、8／B…）'   # ocr-fix 的校正是哪一種（pid_lib 的 look-alike 修正表）；卡片上要講明「讀到的字被改過」
PID_CONF_LOW = 0.8   # 前端把 OCR 辨識信心標成紅字的門檻（card.js PID_LOW）；這裡只用來決定信心值印幾位小數，紅不紅由前端看 extra.confs 決定
# pid.json stats 裡原樣帶進 index.pid.stats 的鍵（掃描範圍與定位結果；卡片「查無」那句的數字一律取自這裡，不寫死）。
# 只帶純數字／小字典：superseded_only（附位號樣本）、corpus、limits 這些除錯用的大塊不進站
PID_STATS_KEEP = ('fixture', 'ams_tags', 'ams_tags_base', 'located', 'located_pct', 'located_symbol', 'located_note_only', 'not_located',
                  'by_proto', 'proto_total', 'by_rel', 'by_how', 'tags_with_ocr_hit', 'drawings', 'pages', 'pages_cover', 'pages_sheet',
                  'pages_text', 'pages_sparse', 'pages_ocr', 'sheets_referenced', 'drawings_referenced', 'dropped', 'ocr_map',
                  'located_ref_only', 'hits_by_note')   # 2026-10-10 起 pid_index 多給的兩個小字典（只有引用的位號數／各 note 代碼的命中數）
PID_SUFFIX_WHY = '；雲端上的檔名沒有結尾的「 (N)」（那是雲端硬碟桌面版替本機檔名加的尾碼），是同一份檔'


def pid_slug(rel, page):
    """圖紙鍵＝`<文件編號-版次｜x>_<sha1(文件庫相對路徑)[:8]>__p<PDF 頁次>`（例 HT0-1-KND01-D0027-4_1030bef1__p2）。
    一律帶路徑雜湊：同一組 編號＋版次 在文件庫裡不只一個檔，檔名也常有空白／&／括號／中文，不能直接當檔名。
    pid.json 的 sheets 鍵、sec.pid 的 extra.s、index.pid.sheets 的鍵、pid_shots/index.json 的鍵、card/pid/<slug>.json 都是它。"""
    import hashlib
    m = DOCNO_VAL_RE.search(rel.rpartition('/')[2].upper())
    stem = (m.group(1) + (('-' + m.group(2)) if m.group(2) else '')) if m else 'x'
    return '%s_%s__p%d' % (stem, hashlib.sha1(rel.encode('utf-8')).hexdigest()[:8], page)


def pid_webp_size(path):
    """WebP 檔頭 → (寬, 高)；不是 WebP 或讀不出來回 None。只讀前 30 位元組、不用 PIL（核對 pid_shots/index.json 寫的寬高是不是真的）。"""
    with open(path, 'rb') as f:
        b = f.read(30)
    if len(b) < 30 or b[:4] != b'RIFF' or b[8:12] != b'WEBP':
        return None
    kind = b[12:16]
    if kind == b'VP8L' and b[20] == 0x2f:          # 無損：14 bit 寬-1、14 bit 高-1
        v = int.from_bytes(b[21:25], 'little')
        return (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1
    if kind == b'VP8X':                            # 延伸格式：24 bit 畫布寬-1、高-1
        return int.from_bytes(b[24:27], 'little') + 1, int.from_bytes(b[27:30], 'little') + 1
    if kind == b'VP8 ' and b[23:26] == b'\x9d\x01\x2a':   # 有損
        return int.from_bytes(b[26:28], 'little') & 0x3FFF, int.from_bytes(b[28:30], 'little') & 0x3FFF
    return None


def pid_src_key(src):
    """來源 PDF 的身分（大小＋修改時間，秒）；pid.json 的 sheets[].src 與 pid_shots/index.json 的 src 用它比。"""
    try:
        return int(src['size']), int(src['mtime'])
    except (KeyError, TypeError, ValueError):
        return None


def load_pid(path, shots_dir, ge_path=None, loc_path=None, wire_path=None):
    """tools/db/pid_index.py 的輸出（位號→圖紙與圖上座標）＋ tools/db/pid_shots.py 的圖紙影像目錄。
    沒有 pid.json 回 None；pid_shots/index.json 缺席時 `_shots` 是 None——兩者都由 main 的缺檔清單擋下來（非 0 結束、資料目錄沒被動過）。
    **不照抄 hmi 的靜默降級**（hmi_shots 目錄不見時會發布 0 張圖，而每一列還寫著 img:true）。其餘不一致在 pid_check 一次查完。
    ge_path＝tools/db/pid_ge.py 的輸出（GE 原廠編號的圖面位置，v10）：by_ge 放進 `_ge`，它引用的圖紙併進 sheets（pid.json 沒有的才加，
    同一個 slug 兩邊的 rel／page／rot／來源 PDF 必須相同，否則兩邊的標記會落在不同的影像座標上）；pid_check 連它一起查。
    AMS 設備的 sec.pid 不受影響（pid_rows 只讀 by_tag）。
    loc_path＝tools/db/loc_ge.py 的輸出（GE 編號在位置圖上的位置，v12）：同樣的併法，by_ge 放進 `_lg`、它的圖紙記進 `_loc`（pid_doc_keys 的說明文字不同），
    docs＝位置圖文件號 → 文件庫裡的那一份檔（或找不到的原因）放進 `_lg_docs`。
    wire_path＝tools/db/wire_ge.py 的輸出（GE 編號的接線路徑，v13 汽機 TSI、v14 一號機全部）：by_ge（框）放進 `_wg`、圖紙記進 `_wire`、paths／jbs 放進 `_wg_paths`／`_wg_jbs`。"""
    if not path or not os.path.exists(path):
        return None
    j = load(path)
    if not isinstance(j.get('by_tag'), dict) or not isinstance(j.get('sheets'), dict):
        raise SystemExit('pid.json 格式不對（缺 by_tag／sheets）：' + path)
    j['_shots_dir'] = shots_dir or ''
    j['_shots_index'] = os.path.join(j['_shots_dir'], 'index.json')
    j['_shots'] = load(j['_shots_index']) if os.path.exists(j['_shots_index']) else None
    j['_applied'] = set()   # pid_apply 用過的 by_tag 鍵（沒用到的＝pid.json 有、現行設備總表沒有的位號）
    j['_ge'], j['_ge_only'], j['_lg'], j['_loc'], j['_lg_docs'] = None, set(), None, set(), {}
    j['_wg'], j['_wire'], j['_wg_paths'], j['_wg_jbs'] = None, set(), {}, {}
    for kind, gp, fn in (('pid_ge', ge_path, 'pid_ge.json'), ('loc_ge', loc_path, 'loc_ge.json'), ('wire_ge', wire_path, 'wire_ge.json')):
        if not gp or not os.path.exists(gp):
            continue
        g = load(gp)
        if g.get('kind') != kind or not isinstance(g.get('by_ge'), dict) or not isinstance(g.get('sheets'), dict):
            raise SystemExit('%s 格式不對（kind／by_ge／sheets）：%s' % (fn, gp))
        for s in sorted({h.get('sheet') for v in g['by_ge'].values() for h in v if isinstance(h, dict)}):
            gs = g['sheets'].get(s)
            if gs is None:
                raise SystemExit('%s 的 by_ge 引用了 sheets 裡沒有的圖紙 %s' % (fn, s))
            if s in j['sheets']:
                diff = [k for k in ('rel', 'page', 'rot', 'src') if j['sheets'][s].get(k) != gs.get(k)]
                if diff:
                    raise SystemExit('%s 與 pid.json／pid_ge.json 的同一張圖紙 %s 記錄不同（%s）：產生器讀的不是同一版圖，先重跑 pid_index.py、pid_ge.py、loc_ge.py、wire_ge.py、pid_shots.py'
                                     % (fn, s, '、'.join(diff)))
            else:
                j['sheets'][s] = gs
                j['_ge_only'].add(s)
            if kind == 'loc_ge':
                j['_loc'].add(s)
            elif kind == 'wire_ge':
                j['_wire'].add(s)
        if kind == 'pid_ge':
            j['_ge'], j['_ge_stats'] = g['by_ge'], g.get('stats') or {}
        elif kind == 'loc_ge':
            j['_lg'], j['_lg_stats'], j['_lg_docs'] = g['by_ge'], g.get('stats') or {}, g.get('docs') or {}
        else:
            j['_wg'], j['_wg_stats'], j['_wg_paths'], j['_wg_jbs'] = g['by_ge'], g.get('stats') or {}, g.get('paths') or {}, g.get('jbs') or {}
    if j['_shots'] is not None:
        pid_check(j, path)
        pid_odd_labels(j)
        j['_dkey'], j['_docs'] = pid_doc_keys(j)
    return j


def pid_claim_key(tag, e):
    """pid_check「同一個框被幾支位號認領」那一關用的身分鍵：兩支位號的鍵相同＝它們本來就該指著同一個標籤。
    位號去掉 AMS 自己加的結尾（`_01`／`_`，圖上沒有）、機組數字抹平（同一個字母的 G11／G12 共用典型圖與不分機組的圖）；
    rel=train 的把自己的系列代碼換成圖上畫的那一台（drawn_as＝LCC10／LAC50：C10LCC20BT012 → C10LCC10BT012，與被畫出來的那一台同鍵）。
    回 None＝這筆是「照規則借用別人位置」而這裡無從核對的（迴路對應 loop；train 的 drawn_as 套不進位號），不參加比較。
    （稽核用的 verify/review-site/shared.py 把 G1[12] 與 C10L(AC|CC)n0 寫死；這裡改由命中自己的 rel／drawn_as 推，換了系統也適用。）"""
    t = re.sub(r'(_01|_)$', '', pid_norm(tag))
    if e.get('rel') == 'loop':
        return None
    if e.get('rel') == 'train':
        da = pid_norm(e.get('drawn_as'))
        m = re.match(r'^([A-Z]+)(\d+)$', da)
        t2 = re.sub(re.escape(m.group(1)) + r'\d{%d}' % len(m.group(2)), da, t, count=1) if m else t
        if da not in t2:
            return None
        t = t2
    return re.sub(r'^([A-Z])\d\d(?=[A-Z_])_?', r'\1##', t)


def pid_shared_boxes(by_tag):
    """同一張圖紙上的同一個框（左上角座標取到小數 4 位）被兩支以上的位號認領、而且它們不是同一個東西的不同稱呼 → 回傳問題清單。
    正當的共用只有三種：(1) 機組雙胞胎（G11／G12 的典型圖與不分機組的圖）與 AMS 的 `_01`／`_` 重複名稱；(2) 圖面註明適用於同型各台
    （rel=train，鍵已換成圖上畫的那一台）；(3) 標籤本身就合寫了幾支位號（`…BL001/2/3`、`C10PHC10/20`、`G11/12…`：斜線後面接數字）。
    其餘＝pid_index 把別人的標籤算給了這支位號（2026-10-10 稽核的實例：S10MAV01BP272（PDIT）與 S10MAV01BP272C（PT）互相掛在對方的
    標籤上，兩張卡各秀出兩個儀器；A／B 元件尾碼的標籤被算成本體也是同一類）。這種資料寧可不發布：卡片會把別的儀器指給使用者看。"""
    at = {}
    for tag, ents in by_tag.items():
        for e in ents if isinstance(ents, list) else []:
            try:
                k = (e['sheet'], round(float(e['x']), 4), round(float(e['y']), 4))
            except (KeyError, TypeError, ValueError):
                continue   # 座標不對的由 pid_check 另外報
            at.setdefault(k, []).append((tag, e))
    bad = []
    for k in sorted(at):
        lst = at[k]
        if len({t for t, _ in lst}) < 2:
            continue
        keys = {}
        for t, e in lst:
            ck = pid_claim_key(t, e)
            if ck is not None:
                keys.setdefault(ck, (t, e))
        if len(keys) < 2 or any(re.search(r'/\d', e.get('label') or '') for _, e in lst):
            continue
        who = '、'.join('%s（圖上標示 %s，%s）' % (t, (e.get('label') or '').strip() or '?', e.get('rel')) for t, e in sorted(keys.values(), key=lambda v: v[0]))
        bad.append('圖紙 %s 左 %.1f%%／上 %.1f%% 的同一個標籤被 %d 支不同的位號認領：%s——它們不是機組雙胞胎、`_01` 重複名稱或合寫的標籤，'
                   '其中至少一支是 pid_index 把別的儀器的標籤算了進來' % (k[0], k[1] * 100, k[2] * 100, len(keys), who))
    return bad


def pid_check(pm, path):
    """pid.json ↔ pid_shots 的一致性，在動資料目錄之前一次查完；有任何一項不對就列出來並以非 0 結束（**不是**默默發布成 img:false）。
    查：by_tag 引用的圖紙都在 sheets；圖紙鍵合乎檔名規則、等於 pid_slug(rel, page)、不分大小寫也不重複（建置機是 Windows，Pages 分大小寫）；
    rel 是文件庫相對路徑；每張被引用的圖紙在 pid_shots/index.json 有一筆、檔案在、是 WebP 且寬高與索引相同、轉正角度（rot）與來源 PDF
    （大小＋修改時間）和 pid.json 相同——不同代表影像是用另一版 PDF 或另一個角度畫的，標記會整批落在錯的地方；每筆命中的 rel／how 合法、
    框的中心在圖內；同一個框沒有被兩支不相干的位號認領（pid_shared_boxes：那代表 pid_index 把別的儀器算了進來，建置機無從判斷誰對，
    只能擋下來）。沒被任何位號引用的圖紙不查也不發布。"""
    sheets, shots, bad, used = pm['sheets'], pm['_shots'], [], {}
    for tag, ents in pm['by_tag'].items():
        for e in ents if isinstance(ents, list) else [{}]:
            s = e.get('sheet')
            if s not in sheets:
                bad.append('位號 %s 引用了 sheets 裡沒有的圖紙 %s' % (tag, s)); continue
            used.setdefault(s, tag)
            if e.get('rel') not in PID_RELS or e.get('how') not in ('text', 'ocr'):
                bad.append('位號 %s @ %s：rel／how 不認得（%s／%s）' % (tag, s, e.get('rel'), e.get('how')))
            if not (e.get('note') in (None, 0) or (isinstance(e.get('note'), int) and not isinstance(e.get('note'), bool) and e['note'] > 0)):
                bad.append('位號 %s @ %s：note 必須是 0（符號標籤）或正整數的引用代碼（%r）' % (tag, s, e.get('note')))
            try:
                x, y, w, h = float(e['x']), float(e['y']), float(e.get('w') or 0), float(e.get('h') or 0)
                inside = w >= 0 and h >= 0 and 0 <= x + w / 2.0 <= 1 and 0 <= y + h / 2.0 <= 1
            except (KeyError, TypeError, ValueError):
                inside = False
            if not inside:
                bad.append('位號 %s @ %s：座標不是圖內的 0~1 比例（x／y／w／h＝%s／%s／%s／%s）' % (tag, s, e.get('x'), e.get('y'), e.get('w'), e.get('h')))
    bad += pid_shared_boxes(pm['by_tag'])
    # GE 原廠編號（v10：P&ID；v12：位置圖）：同樣的檢查，但共用框是常態（閥本體／定位器／電磁閥共用 KKS），不查 pid_shared_boxes
    for key, ents in [kv for src in ('_ge', '_lg', '_wg') for kv in (pm.get(src) or {}).items()]:
        for e in ents if isinstance(ents, list) else [{}]:
            s = e.get('sheet')
            if s not in sheets:
                bad.append('GE 編號 %s 引用了 sheets 裡沒有的圖紙 %s' % (key, s)); continue
            used.setdefault(s, key)
            if e.get('rel') not in PID_RELS or e.get('how') not in ('text', 'ocr') or e.get('via') not in GE_PID_VIA:
                bad.append('GE 編號 %s @ %s：rel／how／via 不認得（%s／%s／%s）' % (key, s, e.get('rel'), e.get('how'), e.get('via')))
            if not (isinstance(e.get('note'), int) and not isinstance(e.get('note'), bool) and e['note'] >= 0):
                bad.append('GE 編號 %s @ %s：note 必須是 0 或正整數（%r）' % (key, s, e.get('note')))
            try:
                x, y, w, h = float(e['x']), float(e['y']), float(e.get('w') or 0), float(e.get('h') or 0)
                inside = w >= 0 and h >= 0 and 0 <= x + w / 2.0 <= 1 and 0 <= y + h / 2.0 <= 1
            except (KeyError, TypeError, ValueError):
                inside = False
            if not inside:
                bad.append('GE 編號 %s @ %s：座標不是圖內的 0~1 比例' % (key, s))
    low = {}
    for s in sorted(used):
        sh = sheets[s]
        rel, page = sh.get('rel'), sh.get('page')
        if not HMI_SLUG_RE.match(s):
            bad.append('圖紙鍵 %r 不能當檔名（只准 A-Z a-z 0-9 _ . -）' % s); continue
        if not isinstance(rel, str) or not rel or rel.startswith('/') or '\\' in rel or ABS_PATH_RE.search(rel) or not isinstance(page, int):
            bad.append('圖紙 %s：rel 必須是文件庫相對路徑（posix）、page 必須是整數（rel＝%r，page＝%r）' % (s, rel, page)); continue
        if pid_slug(rel, page) != s:
            bad.append('圖紙鍵 %s 不等於 pid_slug(rel, page)＝%s' % (s, pid_slug(rel, page)))
        if s.lower() in low:
            bad.append('圖紙鍵 %s 與 %s 只差大小寫' % (s, low[s.lower()]))
        low[s.lower()] = s
        where = '%s 第 %s 頁，例如位號 %s' % (rel.rpartition('/')[2], page, used[s])
        shot = shots.get(s)
        fn = shot.get('file') if isinstance(shot, dict) else None
        if not fn or os.path.basename(fn) != fn or not os.path.isfile(os.path.join(pm['_shots_dir'], fn)):
            bad.append('圖紙 %s（%s）沒有影像：pid_shots/index.json %s' % (s, where, '沒有這一筆' if not fn else '寫的檔 %s 不在' % fn)); continue
        wh = pid_webp_size(os.path.join(pm['_shots_dir'], fn))
        if wh is None or wh != (shot.get('w'), shot.get('h')):
            bad.append('圖紙 %s：%s %s，pid_shots/index.json 寫 %s×%s' % (s, fn, '不是 WebP' if wh is None else '實際 %d×%d' % wh, shot.get('w'), shot.get('h')))
        if 'rot' in shot and 'rot' in sh and shot['rot'] != sh['rot']:
            bad.append('圖紙 %s（%s）：影像的轉正角度 %s 與 pid.json 的 %s 不同' % (s, where, shot['rot'], sh['rot']))
        if 'src' in shot and 'src' in sh and pid_src_key(shot['src']) != pid_src_key(sh['src']):
            bad.append('圖紙 %s（%s）：影像與 pid.json 讀的不是同一版 PDF（大小／修改時間 %s ↔ %s）' % (s, where, shot['src'], sh['src']))
    if bad:
        for b in bad[:20]:
            print('!! pid: ' + b)
        if len(bad) > 20:
            print('!! pid: …另 %d 處' % (len(bad) - 20))
        raise SystemExit('!! pid.json（%s）與 pid_shots（%s）有 %d 處不一致——先重跑 tools/db/pid_index.py、tools/db/pid_shots.py'
                         '（「同一個標籤被幾支不同的位號認領」重跑也一樣的話，要修 pid_index 的比對規則）；'
                         '只想沿用上次發布的 P&ID 圖面位置請加 --no-pid' % (path, pm['_shots_dir'], len(bad)))
    pm['_used'] = sorted(used)


def pid_doc_keys(pm):
    """被引用的圖紙 → index.docs 的鍵與內容；回傳 ({圖紙鍵: docs 鍵}, {docs 鍵: {title, folder, why}})。
    同一份 PDF 的各頁共用一筆：`pid|<文件編號>|<版次>`；檔名沒有 HT 編號的用 `pid|<sha1(相對路徑)前 12 碼>|`（docsearch 的先例）；
    萬一兩個不同的檔是同一組 編號＋版次，路徑排序在後的那個也退用 sha1 鍵（不能兩份檔擠同一個鍵）。
    title＝真正的檔名、folder＝文件庫相對資料夾 → add_drive_urls 以「資料夾/檔名」精確對到這一份檔的 Drive ID。"""
    import hashlib
    by_rel = {}
    for s in pm['_used']:
        by_rel.setdefault(pm['sheets'][s]['rel'], []).append(s)
    key_of, docs = {}, {}
    for rel in sorted(by_rel):
        sh = pm['sheets'][by_rel[rel][0]]
        doc, rev = sh.get('doc') or '', sh.get('rev') or ''
        key = ('pid|%s|%s' % (doc, rev)) if doc else ''
        if not key or key in docs:
            key = 'pid|%s|' % hashlib.sha1(rel.encode('utf-8')).hexdigest()[:12]
        folder, _, base = rel.rpartition('/')
        what = ('接線路徑（接線圖、接線箱位置圖、盤面配置、3500 盤圖）' if all(s in (pm.get('_wire') or ()) for s in by_rel[rel])
                else '位置圖位置（GE 配置／電纜槽／導管／外型圖）' if all(s in (pm.get('_loc') or ()) for s in by_rel[rel]) else 'P&ID 圖面位置')
        docs[key] = {'title': base, 'folder': folder or '.',
                     'why': '%s：圖上的位置讀自這一份 PDF（%s文件庫裡這份圖的現行最高版次）；連結只開這一份檔本身，'
                            '雲端硬碟對照沒有它時不附連結，不改連其他版次' % (what, ('Rev.%s，' % rev) if rev else '')}
        for s in by_rel[rel]:
            key_of[s] = key
    return key_of, docs


def pid_tag_unit(tag):
    """位號開頭的機組碼（G11／G12／S10／C10…；GE 名稱 G11_96FG-1 也是 G11）；沒有（1-PI-CW014-1 這類）回空字串。"""
    m = re.match(r'^([A-Z]\d\d)(?=[A-Z_])', (tag or '').strip().upper())
    return m.group(1) if m else ''


def pid_drawn_unit(tag, drawn_as, label=''):
    """圖上畫的機組／系列：'G11' 照用；圖上只寫機組數字（'11'）時補上本台位號的機組字母 → 'G11'
    （pid_index 的規則：圖上沒寫字母的，字母一定與本台相同才算命中）；'LCC10'、空字串原樣。
    drawn_as 就是整個標籤時（迴路對應：圖上是 1-PIT-CW014-1）不算機組，回空字串——那串字已經在 drawn 裡。"""
    da = (drawn_as or '').strip()
    own = pid_tag_unit(tag)
    if da and pid_norm(da) == pid_norm(label):
        return ''
    return (own[0] + da) if (own and re.match(r'^\d\d$', da)) else da


def pid_norm(s):
    """比「圖上的字」與位號是不是同一串：去掉空白、= 與括號，不分大小寫。"""
    return re.sub(r'[\s=()\[\]（）]', '', s or '').upper()


def pid_sheet_name(sh):
    """「P&ID 圖面」那一列的值：`HT0-1-KND01-D0027 Rev.4　HRSG SCR System P&ID`；檔名沒有 HT 編號的用去掉 .pdf 的檔名。"""
    doc, rev, title = sh.get('doc'), sh.get('rev'), (sh.get('title') or '').strip()
    if not doc:
        return re.sub(r'\.pdf$', '', sh['rel'].rpartition('/')[2], flags=re.I)
    return doc + ((' Rev.%s' % rev) if rev not in (None, '') else '') + (('　' + title) if title else '')


def pid_note(e):
    """命中的 note 代碼：0＝儀器符號旁的標籤；1～4＝引用（PID_NOTE_NAME）。缺席／None／0 都是 0；不是整數的真值（舊資料的 True）當 1。"""
    n = e.get('note')
    if not n:
        return 0
    return n if isinstance(n, int) and not isinstance(n, bool) else 1


def pid_label_clean(lab):
    """圖上的字去掉不屬於標籤的碎屑：句尾的標點／斜線，與成不了對的括號（註記句子裡切出來的 `(90VA41-2`、`90VA41-21).`）。
    成對的括號照留（GE 圖面的 `(90LT-1)` 就是那樣畫的）。"""
    s = re.sub(r'[\s.,;:/、，。；：]+$', '', (lab or '').strip())
    for a, b in ('()', '[]', '（）'):
        if s.count(a) != s.count(b):
            s = s.replace(a, '').replace(b, '')
    return s.strip()


def pid_label_is_tag(tag, lab):
    """rel=exact 的圖上標示是不是「說得出差在哪裡」的本台位號：正規化後與位號相同、只省略機組字母、只少了 AMS 位號結尾的 `_01`／`_`，
    或是合寫幾支位號的標籤（斜線後面接數字）。其餘（多了元件尾碼、黏了別的字）回 False——卡片上不會替它寫「就是本台位號」。"""
    nl, nt = pid_norm(pid_label_clean(lab)), pid_norm(tag)
    bare = re.sub(r'(_01|_)$', '', nt)
    ok = {nt, bare} | ({nt[1:], bare[1:]} if pid_tag_unit(tag) else set())
    return nl in ok or bool(re.search(r'/\d', lab or ''))


def pid_odd_labels(pm):
    """rel=exact、圖上標示卻說不出與位號差在哪裡的命中（pid_label_is_tag 為 False）→ 印出來（不擋建置：卡片會寫「請對照圖面確認」）。
    pid_index 照 2026-10-10 的裁決（尾碼必須相同、OCR 標籤要拆乾淨）輸出時這裡是 0 筆；不是 0 就代表產生器那一端又放了東西進來。"""
    odd = sorted((t, (e.get('label') or '').strip()) for t, ents in pm['by_tag'].items() for e in ents if e.get('rel') == 'exact' and not pid_label_is_tag(t, e.get('label')))
    if odd:
        print('!! pid: %d 筆「圖上就是本台」（rel=exact）的命中，圖上標示與位號對不起來（卡片上會寫「請對照圖面確認」，不寫「就是本台位號」）：%s%s'
              % (len(odd), '、'.join('%s←%s' % o for o in odd[:8]), '…' if len(odd) > 8 else ''))
    return len(odd)


def pid_marks(ents):
    """同一張圖紙上這支位號的各處 → (hits, marks)，兩者一一對應：marks[i]＝[中心 x, 中心 y, 框寬, 框高]（轉正後影像的 0~1 比例、左上為原點；
    pid.json 給的是左上角＋寬高，這裡換成與圖控 marks 相同的「中心＋寬高」）。順序照 pid.json，但儀器符號旁的標籤（note=0）排在
    引用（note=1～4：註記／表格、跨圖旗標、用氣點、迴路詳圖）之前——**marks[0] 就是「所在位置」描述的那處**；完全重疊的只留第一筆。"""
    use, marks, seen = [], [], set()
    for e in sorted(ents, key=lambda e: 1 if pid_note(e) else 0):   # sorted 是穩定排序：同級維持 pid.json 的順序
        w, h = float(e.get('w') or 0), float(e.get('h') or 0)
        m = (round(float(e['x']) + w / 2.0, 5), round(float(e['y']) + h / 2.0, 5), round(w, 5), round(h, 5))
        if m in seen:
            continue
        seen.add(m)
        use.append(e)
        marks.append(list(m))
    return use, marks


def pid_circled(idx):
    return '、'.join(HMI_CIRCLED[i] for i in idx if i < len(HMI_CIRCLED))


def pid_ref_groups(use, idx):
    """idx 這幾處裡的引用（note≠0）依代碼分組 → [(代碼, [第幾處…])]，照各組第一處在圖上的編號排（① 所屬的那一種先講）。"""
    by = {}
    for i in idx:
        c = pid_note(use[i])
        if c:
            by.setdefault(c, []).append(i)
    return sorted(by.items(), key=lambda kv: kv[1][0])


def pid_pos_text(use, marks):
    """「所在位置」：`圖面左 47%／上 71%（圖框分區 C-5）`；圖框分區讀得到才寫，zone_near＝標籤落在分區格線外、取最近的一格 → 寫「約」。
    同一張圖多處時把 ① 講清楚（前端照 marks 的順序編號）。**不是儀器符號的地方一定講出來**：① 是符號標籤時列出其餘幾處裡哪幾處是哪一種引用；
    這張圖上每一處都是引用時（符號標籤一定排在前面，所以 ① 是引用＝整張都是），直接說這個位置不是儀器符號的位置。"""
    p, e, n = marks[0], use[0], len(marks)
    t = '圖面左 %d%%／上 %d%%' % (round(p[0] * 100), round(p[1] * 100))
    if e.get('zone'):
        t += '（圖框分區%s%s）' % ('約 ' if e.get('zone_near') else ' ', e['zone'])
    if n > 1:
        t += '＝圖上標記 ①；這支位號在同一張圖另有 %d 處（圖上 %s）' % (n - 1, pid_circled(range(1, n)))

    def kinds(groups):
        return '，'.join('%s 是%s' % (pid_circled(ix), PID_NOTE_NAME.get(c, PID_NOTE_OTHER[0])) for c, ix in groups)
    if not pid_note(e):
        refs = pid_ref_groups(use, range(1, n))
        if refs:
            t += '，其中 %s（不是儀器符號的位置）' % kinds(refs)
    else:
        refs = pid_ref_groups(use, range(n))
        if len(refs) > 1:
            t += '；%s，都不是儀器符號的位置' % kinds(refs)
        else:
            t += '；%s是%s，不是儀器符號的位置' % ('這一處' if n == 1 else '這 %d 處都' % n, PID_NOTE_NAME.get(refs[0][0], PID_NOTE_OTHER[0]))
    return t


def pid_fix_text(e, own=True):
    """ocr-fix（OCR 把相近字元讀錯、校正後才對上）要在卡片上講明，不能把校正後的字當成圖上讀到的字：寫出 OCR 原本讀到的那一串（hit 的 raw）。
    own＝校正後對上的是本台位號（rel=exact）；否則對上的是圖上那一串字（典型圖／同型各台）。舊資料沒有 raw 時只說有校正。"""
    raw = (e.get('raw') or '').strip()
    tail = '校正後才對上本台位號' if own else '校正後才是這串字'
    return ('OCR 讀成「%s」，%s%s' % (raw, PID_LOOKALIKE, tail)) if raw else ('OCR 讀到的字有%s讀錯，%s' % (PID_LOOKALIKE, tail))


def pid_label_text(tag, use, has_symbol=True):
    """「圖上標示」：圖上實際畫的字＋它為什麼算這一台（rel）。這句話是整個功能最容易讓人誤會的地方——G12 的卡片上出現 =G11… 不是錯，
    必須用白話講清楚：
      exact   圖上畫的就是本台（寫法可能省略機組字母、沒有 AMS 位號結尾的 _01、或幾支位號合寫成一個標籤）
      typical 圖是以另一台機組畫的典型圖，本台取同一位置
      neutral 圖面不分機組（GE／汽機的編號不帶機組），各機組共用
      loop    圖上是同一迴路編號的另一個儀器（功能代號不同，例如傳送器 PIT ↔ AMS 的 PI）
      train   圖上畫的是同型的另一台（圖面註明適用同型各台）
    2026-10-10 稽核後的規矩：
      * 「與本台位號相同」只在**正規化後的字串真的等於位號**時才寫；而且 ocr-fix 不寫這一句——那串字是校正出來的，改寫 OCR 原本讀成什麼。
      * OCR 讀到的字前面標「OCR 讀到的字：」（它是辨識結果，不是從 PDF 裡取出來的字）。
      * ① 是引用（note 1～4）時在句尾講明這一處是什麼、不是儀器符號；has_symbol＝這支位號在任何一張圖上有沒有符號標籤——
        都沒有就直說「圖上沒有找到這支位號的儀器符號」，有的話指到另一張圖紙。
      * 其餘幾處的字與 ① 不同時（去掉空白後仍不同）逐處寫出是 ②③ 哪幾處；只差空白／換行的不算另一種寫法。"""
    e = use[0]
    lab = pid_label_clean(e.get('label'))
    rel, own, du = e.get('rel'), pid_tag_unit(tag), pid_drawn_unit(tag, e.get('drawn_as'), lab)
    fix = e.get('form') == 'ocr-fix'
    nl, nt = pid_norm(lab), pid_norm(tag)
    bare = re.sub(r'(_01|_)$', '', nt)   # AMS 位號結尾的 `_01`／`_`（AMS 裡的重複名稱），圖上沒有
    if rel == 'exact':
        if nl == nt:
            why = '' if fix else '與本台位號相同'
        elif own and nl == nt[1:]:
            why = '就是本台位號，圖上省略機組字母 %s' % own[0]
        elif bare != nt and nl in ((bare, bare[1:]) if own else (bare,)):
            why = '就是本台位號，圖上沒有 AMS 位號結尾的「%s」%s' % (nt[len(bare):], ('，也省略機組字母 %s' % own[0]) if nl != bare else '')
        elif re.search(r'/\d', lab):
            why = '圖上把幾支位號合寫成一個標籤，本台是其中一支'
        else:   # 說不出差在哪裡的不替它背書（稽核抓到的 A／B 元件尾碼標籤就是從這裡被寫成「就是本台位號」；pid_odd_labels 會把這種命中印出來）
            why = 'pid_index 判定是本台位號，但圖上的寫法與位號不完全相同，請對照圖面確認'
    elif rel == 'typical':
        why = ('這張是以 %s 繪製的典型圖，本台 %s 取同一位置' % (du, own)) if (du and own) else '這張是以另一台機組繪製的典型圖，本台取同一位置'
    elif rel == 'neutral':
        why = ('圖上的機組寫成 %s；' % du if du else '') + '這張圖不分機組，各機組共用'
    elif rel == 'loop':
        why = '同一迴路的儀器，與本台位號 %s 只差功能代號，依迴路編號對應' % tag
    else:   # train
        # 兩張同型圖的依據不同：TCM01-D1114 是圖上的一句註記，TDM01-D1205 是封面項目清單＋儀器清單把各台並列——句子要兩種都說得通，
        # 所以不寫「圖面註明」；並比照典型圖那一句講明本台取同一位置
        m = re.match(r'^[A-Z]\d\d([A-Z]{3}\d\d)', nt)
        mine = m.group(1) if (m and du and m.group(1) != du) else ''
        why = ('這份圖只畫 %s 一台，圖面把同型各台並列為同一張圖適用，本台%s取同一位置' % (du, (' %s ' % mine) if mine else '')) if du \
            else '這份圖只畫同型的其中一台，圖面把同型各台並列為同一張圖適用，本台取同一位置'
    if fix:
        why = '；'.join(x for x in (why, pid_fix_text(e, rel == 'exact')) if x)
    t = '%s%s（%s）' % ('OCR 讀到的字：' if (e.get('how') == 'ocr' and not fix) else '', lab or '（圖上的字沒有記錄）', why)
    others = {}
    for i, x in enumerate(use[1:], 1):
        l2 = pid_label_clean(x.get('label'))
        n2 = pid_norm(l2)
        if not l2 or n2 == nl:
            continue
        if x.get('rel') == 'exact' and not pid_label_is_tag(tag, l2):
            continue   # 防呆：幾個標籤黏成一串、後面黏了別的字（管徑…）或帶元件尾碼的讀取不是「本台的另一種寫法」（pid_index 應該已經拆開／濾掉）
        others.setdefault(n2, (l2, []))[1].append(i)
    if others:
        t += '；' + '，'.join('圖上 %s 寫成 %s' % (pid_circled(ix), l2) for l2, ix in others.values())
    c = pid_note(e)
    if c:
        t += '；' + PID_NOTE_TEXT.get(c, PID_NOTE_OTHER[1])
        # 「沒有讀到」不等於「圖上沒有畫」（2026-10-10 稽核：C10LAC50BT029 的球泡明明畫在圖上，只是 OCR 沒讀到）——不可以寫成「圖上沒有」
        t += '；儀器符號畫在這台設備的另一張圖紙上' if has_symbol else '；這次比對（PDF 文字層＋OCR）沒有讀到這支位號的儀器符號，不代表圖上沒有畫，請開 PDF 確認'
    return t


def pid_ocr_where(e, sh):
    """OCR 命中為什麼不在文字層（「對應方式」括號裡的第一句）。圖紙的 words（pid_index 記的文字層字數）是 0＝整頁沒有文字層
    （掃描影像或全是線條字，TDM01-D1205 就是嵌入的點陣圖）：這時不能說「線條字」。儀器清單／註記的那幾列（note=1）也不說線條字，
    只說那一頁（那一處）的清單不在文字層。其餘＝文字層有別的字、偏偏位號是線條畫出來的（KND01-D0027 那一類）。"""
    w = (sh or {}).get('words')
    no_layer = isinstance(w, int) and not isinstance(w, bool) and w == 0
    if pid_note(e) == 1:
        return '這一頁的清單／註記沒有 PDF 文字層' if no_layer else '這一處的清單／註記文字不在 PDF 文字層'
    if no_layer:
        return '這一頁沒有 PDF 文字層，圖上的字是影像或線條畫出來的'
    return '圖上的位號是線條字，不在 PDF 文字層'


def pid_how_text(use, sh=None):
    """「對應方式」：位置是怎麼找到的。PDF 文字層（拆寫的說明怎麼合併）；OCR 讀圖＝位號不在文字層（為什麼不在見 pid_ocr_where），附辨識信心；
    ocr-fix 另外講明 OCR 原本讀成什麼、校正了相近字元（pid_fix_text）。同一張圖各處的來源不同時（文字層為準，OCR 只補文字層沒有的地方）
    逐一標出是 ①②③ 哪幾處，各處的辨識信心與有沒有校正也逐處寫。"""
    def conf(x):   # 兩位小數；四捨五入後看不出「低於紅字門檻」的（0.798 → 0.80）多寫一位，與前端 card.js pidConf 同一個規則
        c = x.get('conf')
        if not isinstance(c, (int, float)) or isinstance(c, bool):
            return ''
        s = '%.2f' % c
        return ('%.3f' % c) if (c < PID_CONF_LOW <= float(s)) else s
    e, many = use[0], len(use) > 1
    ocr = [i for i, x in enumerate(use) if x.get('how') == 'ocr']
    txt = [i for i, x in enumerate(use) if x.get('how') != 'ocr']
    form = e.get('form') or ''
    split = PID_FORM_TEXT.get(re.sub(r'^ocr-', '', form))

    def confs(idx):   # 「辨識信心 0.93」；多處時「辨識信心 ① 0.95、② 0.81」
        cs = ['%s%s' % ((HMI_CIRCLED[i] + ' ') if many and i < len(HMI_CIRCLED) else '', conf(use[i])) for i in idx if conf(use[i])]
        return ('辨識信心 ' + '、'.join(cs)) if cs else ''

    def fixes(idx):   # ① 以外經過校正的那幾處
        fx = [i for i in idx if use[i].get('form') == 'ocr-fix']
        raws = [(use[i].get('raw') or '').strip() for i in fx]
        if not fx:
            return ''
        return '圖上 %s 的字經過%s校正%s' % (pid_circled(fx), PID_LOOKALIKE, ('（OCR 讀成%s）' % '、'.join('「%s」' % r for r in raws)) if all(raws) else '')
    if e.get('how') == 'ocr':
        bits = [pid_ocr_where(e, sh)] + ([split] if split else [])
        if form == 'ocr-fix':
            bits.append(pid_fix_text(e, e.get('rel') == 'exact'))
        bits += [confs(ocr)] if confs(ocr) else []
        t = 'OCR 讀圖（%s）' % '；'.join(bits)
        if fixes(ocr[1:]):
            t += '；' + fixes(ocr[1:])
        if txt:
            t += '；圖上 %s 在 PDF 文字層' % pid_circled(txt)
        return t
    t = 'PDF 文字層' + (('（%s）' % split) if split else '')
    if ocr:
        t += '；圖上 %s 是 OCR 讀圖（%s）' % (pid_circled(ocr), '；'.join([pid_ocr_where(use[ocr[0]], sh)] + ([confs(ocr)] if confs(ocr) else [])))
        if fixes(ocr):
            t += '；' + fixes(ocr)
    return t


def pid_rows(pm, tag):
    """一台設備的 sec.pid.rows：每張圖紙一組 5 列（P&ID 圖面／圖面頁次／所在位置／圖上標示／對應方式），組的順序＝pid.json 裡各圖紙
    第一次出現的順序（pid_index 已照「符號標籤優先、再依文件編號與頁次」排好）。第一列的 extra 帶整組顯示需要的東西，其餘列只帶 {s, g}。
    lvl：文字層命中而且圖上就是本台或圖面不分機組 → doc；典型圖／迴路／同型各台，以及所有 OCR 命中 → inferred（以 ① 那一處為準）。
    FF 設備沒有特別的說法：和圖控不同，FF 訊號在 P&ID 上照樣畫得到。
    第一列 extra 裡與「這一處算什麼」「讀得準不準」有關的鍵（前端的標頭短籤與紅字只看這幾個，整句在「圖上標示」「對應方式」兩列）：
      note      這張圖上**每一處**都是引用時才有：各處代碼相同＝那個代碼（1～4），不同＝1。沒有這個鍵＝① 是儀器符號旁的標籤。
      notes     逐處的代碼（與 marks 一一對應；0＝符號標籤）。這張圖上有任何一處是引用才帶。前端以 notes[0] 講 ① 是什麼
                （各處代碼不同時 note 只能給 1，講不準 ① 是哪一種）。
      conf      ① 的 OCR 辨識信心（① 是 OCR 才有；舊鍵，留著）。
      conf_min  這張圖上所有 OCR 標記裡最低的辨識信心（有任何一處是 OCR 才有）——紅字警語看它，不是只看 ①。
      confs     逐處的辨識信心（與 marks 一一對應；文字層的那幾處是 null）。有任何一處是 OCR 才帶；前端用它講「是 ②③ 哪幾處偏低」。
      fix／raw  ① 是 ocr-fix（相近字元校正後才對上）＝fix: 1；raw＝OCR 原本讀到的字（pid.json 有給才帶）。
      odd       ① 是 rel=exact 而圖上的字與位號對不起來（pid_label_is_tag 為 False；產生器照裁決輸出時不會有）＝1：前端標頭不寫「就是本台」。"""
    t = (tag or '').strip()
    key = t if t in pm['by_tag'] else t.upper()
    ents = (pm['by_tag'].get(key) or []) if t else []
    if not ents:
        return []
    pm['_applied'].add(key)
    has_symbol = any(not pid_note(e) for e in ents)   # 這支位號在任何一張圖上有沒有儀器符號旁的標籤
    order, groups = [], {}
    for e in ents:
        if e['sheet'] not in groups:
            groups[e['sheet']] = []
            order.append(e['sheet'])
        groups[e['sheet']].append(e)
    rows = []
    for gi, s in enumerate(order):
        sh = pm['sheets'][s]
        use, marks = pid_marks(groups[s])
        e = use[0]
        lvl = 'doc' if (e['how'] == 'text' and e['rel'] in ('exact', 'neutral')) else 'inferred'
        src = '%s · %s 第 %s 頁' % (src_prefix(lvl), sh['rel'].rpartition('/')[2], sh['page'])
        base = {'s': s, 'g': gi}
        first = dict(base, d=pm['_dkey'][s], p=sh['page'])
        if isinstance(sh.get('pages'), int):
            first['n'] = sh['pages']
        lab = pid_label_clean(e.get('label'))
        first.update(img=True, marks=marks, drawn=lab, unit=pid_drawn_unit(t, e.get('drawn_as'), lab), rel=e['rel'], how=e['how'])
        if e['rel'] == 'exact' and not pid_label_is_tag(t, e.get('label')):
            first['odd'] = 1   # rel=exact 而圖上的字與位號對不起來（pid_odd_labels 會印出來）：前端標頭不寫「就是本台」
        confs = [x['conf'] if (x.get('how') == 'ocr' and isinstance(x.get('conf'), (int, float)) and not isinstance(x.get('conf'), bool)) else None for x in use]
        if confs[0] is not None:
            first['conf'] = confs[0]
        if any(c is not None for c in confs):
            first['conf_min'] = min(c for c in confs if c is not None)
            first['confs'] = confs
        if e.get('form') == 'ocr-fix':
            first['fix'] = 1
            if (e.get('raw') or '').strip():
                first['raw'] = e['raw'].strip()
        if e.get('zone'):
            first['zone'] = e['zone']
            if e.get('zone_near'):
                first['zone_near'] = 1
        codes = [pid_note(x) for x in use]
        if all(codes):
            first['note'] = codes[0] if len(set(codes)) == 1 else 1   # 這張圖上每一處都是引用，沒有符號標籤
        if any(codes):
            first['notes'] = codes
        rows.append(['P&ID 圖面', pid_sheet_name(sh), lvl, src, first])
        rows.append(['圖面頁次', 'PDF 第 %s 頁%s' % (sh['page'], ('（共 %s 頁）' % sh['pages']) if isinstance(sh.get('pages'), int) else ''), lvl, src, dict(base)])
        rows.append(['所在位置', pid_pos_text(use, marks), lvl, src, dict(base)])
        rows.append(['圖上標示', pid_label_text(t, use, has_symbol), lvl, src, dict(base)])
        rows.append(['對應方式', pid_how_text(use, sh), lvl, src, dict(base)])
    return rows


def pid_apply(sec, pm, tag):
    rows = pid_rows(pm, tag) if pm else []
    if rows:
        sec['pid'] = {'rows': rows}


def pid_blob(path, w, h):
    """圖紙影像檔 → card/pid/<slug>.json 的內容（{w,h,mime,b64} 的位元組；走既有 *.json 加密路徑，與 card/hmi 同一種包法）。"""
    import base64
    return dumps({'w': w, 'h': h, 'mime': 'image/webp', 'b64': base64.b64encode(open(path, 'rb').read()).decode('ascii')}).encode('utf-8')


def pid_collect(out, pm, stats, ge_used=None):
    """收集 out 裡 sec.pid 真的用到的圖紙 → (index.pid, {card/pid/<slug>.json: 內容位元組})。**這裡不寫任何檔**：影像內容先留在記憶體
    （全部約十幾 MB），等 write_output 把分塊與 index 都序列化、自檢過了，才由 pid_write_images 一次清掉舊的 card/pid/ 寫新的
    （2026-10-10 稽核：原本在自檢之前就清空重寫 card/pid/，中途失敗會留下「新影像＋舊 index／舊分塊」）。
    每張圖紙一檔，畫在上面的所有位號共用（標記不燒進影像）。load_pid 已確認每張被引用的圖紙都有影像，所以這裡沒有「沒有影像」的分支。
    no_url 要等 add_drive_urls 之後才知道，由 pid_link_stats 補。
    ge_used＝GE 編號卡（card/getag.json 的 pd 列）用到的 {圖紙鍵: 條目數}（ge_loc_build）：影像一起發布、與 AMS 設備共用同一個檔；
    sheets[].rows 仍只算 AMS 設備（GE 另記 ge），stats 的 images／docs 只算 AMS 設備用到的，GE 另記 ge_*（pid_doc 那句話的數字不變）。"""
    used, ndev, nref = {}, 0, 0
    for al, o in out.items():
        firsts = [r[4] for r in ((o.get('sec') or {}).get('pid') or {}).get('rows') or [] if len(r) > 4 and isinstance(r[4], dict) and r[4].get('s') and 'marks' in r[4]]
        if firsts:
            ndev += 1
            nref += 1 if all(f.get('note') for f in firsts) else 0   # 每張圖上都只有引用（註記／旗標／用氣點／迴路詳圖），沒有任何儀器符號
        for s in {f['s'] for f in firsts}:
            used[s] = used.get(s, 0) + 1
    ge_used = ge_used or {}
    sheets, blobs, total = {}, {}, 0
    for s in sorted(set(used) | set(ge_used)):
        sh, shot = pm['sheets'][s], pm['_shots'][s]
        rel = 'card/pid/%s.json' % s
        blobs[rel] = pid_blob(os.path.join(pm['_shots_dir'], shot['file']), shot['w'], shot['h'])
        n = len(blobs[rel])
        sheets[s] = {'doc': sh.get('doc'), 'rev': sh.get('rev'), 'title': sh.get('title') or '', 'name': sh['rel'].rpartition('/')[2],
                     'page': sh['page'], 'pages': sh.get('pages'), 'd': pm['_dkey'][s], 'file': rel, 'w': shot['w'], 'h': shot['h'],
                     'bytes': n, 'rows': used.get(s, 0), 'ocr': bool(sh.get('ocr'))}
        if ge_used.get(s):
            sheets[s]['ge'] = ge_used[s]   # GE 編號卡有幾個條目畫在這張圖紙上（v10）
        if s in (pm.get('_loc') or ()):
            sheets[s]['loc'] = 1           # 位置圖（v12，loc_ge.py）：不是 P&ID
        if s in (pm.get('_wire') or ()):
            sheets[s]['wire'] = 1          # 接線路徑的圖（v13，wire_ge.py）：接線圖、接線箱位置圖、盤面配置、3500 盤圖
        total += n
    ps = pm.get('stats') or {}
    st = {k: ps[k] for k in PID_STATS_KEEP if k in ps}
    st.update(devices=ndev, devices_ref_only=nref, tags=len(pm['_applied']), tags_unpublished=len(set(pm['by_tag']) - pm['_applied']),
              images=len(used), docs=len({m['d'] for m in sheets.values() if m['rows']}))
    if ge_used:
        loc = set(pm.get('_loc') or ()) & set(ge_used)   # 位置圖（v12）另計，ge_* 只算 P&ID（數字與 v10／v11 同義）
        wire = set(pm.get('_wire') or ()) & set(ge_used) - loc   # 接線路徑的圖（v13）另計
        gp = set(ge_used) - loc - wire
        st.update(ge_entries=(pm.get('_ge_n') or 0), ge_sheets=len(gp), ge_only_sheets=len(gp - set(used)),
                  ge_docs=len({sheets[s]['d'] for s in gp}))
        if loc:
            st.update(ld_sheets=len(loc), ld_docs=len({sheets[s]['d'] for s in loc}))
        if wire:
            st.update(wp_sheets=len(wire), wp_docs=len({sheets[s]['d'] for s in wire}))
    ix = {'sheets': sheets, 'files': sorted(blobs), 'bytes': total,
          'note': ('圖紙影像＝文件庫裡這份 P&ID 現行最高版次 PDF 的那一頁，轉正後的整張圖（灰階 WebP；每張圖紙一檔，畫在上面的位號共用）。'
                   '影像只供定位，不是正本：內容以雲端硬碟的 PDF 為準（sheets[].d → docs 的 url；drive_map 沒有那一份檔時沒有 url，stats.no_url 計數）。'
                   'marks 每筆＝[中心 x, 中心 y, 框寬, 框高]，是轉正後影像的 0~1 比例、左上為原點，可直接乘 sheets[].w／h；標記沒有畫進影像，'
                   '由前端以百分比疊上去；**marks[0] 就是「所在位置」文字描述的那處**（儀器符號旁的標籤排在引用之前；前端照陣列順序編號）。'
                   'extra.rel：exact＝圖上畫的就是本台；neutral＝圖面不分機組（位號不帶機組）；typical＝圖上畫的是另一台機組（典型圖），本台取同一位置；'
                   'loop＝同一迴路編號、功能代號不同；train＝圖面註明適用於同型各台。extra.unit＝圖上畫的機組（只寫數字的已補上機組字母）、'
                   'extra.drawn＝圖上畫的字（去掉句尾標點與不成對的括號）。extra.how：text＝PDF 文字層；ocr＝位號不在文字層，由 OCR 讀出。'
                   '引用（不是儀器符號的位置）：extra.notes＝逐處的代碼，與 marks 一一對應——0 儀器符號旁的標籤、1 圖上註記或表格（儀器清單）裡的文字、'
                   '2 跨圖訊號旗標、3 儀用／廠用空氣分配圖上的用氣點、4 迴路詳圖（TYPICAL 小圖）；這張圖上有任何一處是引用才帶。'
                   'extra.note＝這張圖上每一處都是引用時才有（代碼都相同＝那個代碼，不同＝1）。'
                   'OCR：extra.conf＝① 的辨識信心、conf_min＝這張圖上各處 OCR 標記的最低辨識信心、confs＝逐處的辨識信心（文字層的是 null）；'
                   'extra.fix＝① 的字經過相近字元校正才對上（ocr-fix），raw＝OCR 原本讀到的字；extra.odd＝rel 是 exact 而圖上的字與位號對不起來（請對照圖面）。'
                   'lvl：文字層而且 exact／neutral 才是 doc，其餘（典型圖／迴路／同型各台、所有 OCR）一律 inferred。'
                   'sheets[].rows＝有幾台設備畫在這張圖上、ocr＝這一頁用到 OCR 結果。stats 的 drawings／pages／pages_text／pages_ocr／located 是 pid_index '
                   '的掃描範圍與定位結果，devices／tags／images／docs／no_url 是這次實際發布的數字（devices_ref_only＝每張圖上都只有引用、沒有儀器符號的'
                   '設備數；tags_unpublished＝pid.json 有、現行設備總表沒有的位號）。'),
          'stats': st}
    stats['pid'] = dict(st, bytes=total)
    print('pid: %d 台設備有 P&ID 圖面位置（%d 支位號；其中 %d 台只找到引用、沒有儀器符號），畫在 %d 張圖紙上（%d 份 PDF）；發布 %d 個影像檔共 %d KB'
          % (ndev, st['tags'], nref, len(used), st['docs'], len(blobs), total // 1024))
    if ge_used:
        print('pid: GE 編號卡 %d 個條目有 P&ID 圖面位置，畫在 %d 張圖紙上（其中 %d 張只有 GE 編號用到）' % (st['ge_entries'], st['ge_sheets'], st['ge_only_sheets']))
        if st.get('ld_sheets'):
            print('pid: GE 編號卡的位置圖 %d 張（%d 份 PDF），影像與 P&ID 圖紙同一個目錄' % (st['ld_sheets'], st['ld_docs']))
    if st['tags_unpublished']:
        miss = sorted(set(pm['by_tag']) - pm['_applied'])
        print('pid: pid.json 有 %d 支位號不在現行設備總表（03），沒有發布：%s%s' % (len(miss), '、'.join(miss[:8]), '…' if len(miss) > 8 else ''))
    if ps.get('fixture'):
        print('!! pid: 這份 pid.json 是測試用 fixture（stats.fixture），不是 tools/db/pid_index.py 的正式輸出——只能在測試用的副本上建置，不可發布')
    return ix, blobs


def pid_write_images(outdir, blobs):
    """整個清掉 card/pid/ 再寫 blobs（pid_collect 的第二個回傳值；空的＝只清）。掉出覆蓋範圍的圖紙不會留下孤兒密文。
    write_output 在分塊與 index 都通過自檢之後、緊接著寫分塊的地方呼叫——在那之前失敗，資料目錄裡的 card/pid/ 原封不動。"""
    import shutil
    pdir = os.path.join(outdir, 'card', 'pid')
    if os.path.isdir(pdir):
        shutil.rmtree(pdir)
    if blobs:
        os.makedirs(pdir, exist_ok=True)
    for rel in sorted(blobs):
        with open(os.path.join(outdir, rel), 'wb') as f:
            f.write(blobs[rel])


def pid_docs(pm, pid_ix):
    """這次發布的圖紙所屬的 PDF → index.docs 的項目（只登記真的有設備引用的；鍵與內容在 load_pid 已算好）。
    GE 編號卡用到的也登記（v10）：Drive url 與 pid_own_urls_only 的規則一樣套；卡片的 docs 子集另由 ge_card_data 帶進 getag.json。"""
    return {k: dict(pm['_docs'][k]) for k in sorted({m['d'] for m in pid_ix['sheets'].values()})}


def pid_own_urls_only(docs, drive):
    """`pid|…` 的文件只准連到「自己那一份檔」（資料夾/檔名 完全相同）。add_drive_urls 精確對不到時會退而找同資料夾、同編號的別份檔，
    甚至別版次（加 url_note）——對一般文件是好事，對 P&ID 圖面位置不行：座標是從這一版讀出來的，連到別版就可能指著不對的地方
    （文件庫的新版次還沒進 drive_map 時就會發生）。所以對這些鍵重新以精確路徑決定 url：對得到就用它，對不到就拿掉（卡片不附連結，
    stats.pid.no_url 計數）。回傳因此少掉的「帶 url_note 的連結」份數（呼叫端用來修正 n_alt）。沒有 drive_map 時不動（留著上次精確對到的）。

    唯一的例外是「同一份檔的本機檔名」：雲端硬碟桌面版會替同資料夾裡撞名的項目在**本機檔名**尾端加「 (1)」，雲端上的檔名並沒有
    （2026-10-08 實查 DriveFS 中繼資料：`…FG21 (1).pdf` 在該資料夾只對應一個未刪除的雲端項目 `…FG21.pdf`，本機也只有帶尾碼的那一個檔）。
    精確路徑對不到時，只再試「同資料夾、去掉副檔名前那個『 (數字)』」這一個名字——仍是同一份檔，不是別的版次或別的分冊；
    對到的在 why 補一句說明並印出來。"""
    if not drive:
        return 0
    files, n_alt, via_suffix = drive['files'], 0, []
    for key, d in docs.items():
        if not key.startswith('pid|'):
            continue
        folder = (d.get('folder') or '').strip('/')
        pre = '' if folder in ('', '.') else folder + '/'
        title = d.get('title') or ''
        fid = files.get((pre + title).lower())
        if not fid:
            plain = re.sub(r' \(\d+\)(?=\.[^.]+$)', '', title)
            fid = files.get((pre + plain).lower()) if plain != title else None
            if fid:
                via_suffix.append(title)
                if PID_SUFFIX_WHY not in (d.get('why') or ''):
                    d['why'] = (d.get('why') or '') + PID_SUFFIX_WHY
        if d.get('url') and d.get('url_note'):
            n_alt += 1
        d.pop('url', None)
        d.pop('url_note', None)
        if fid:
            d['url'] = 'https://drive.google.com/open?id=%s' % fid
    if via_suffix:
        print('pid: %d 份 PDF 的本機檔名多了雲端硬碟桌面版加的尾碼「 (N)」，以去掉尾碼的檔名對到雲端上的同一份檔：%s%s'
              % (len(via_suffix), '、'.join(sorted(via_suffix)[:6]), '…' if len(via_suffix) > 6 else ''))
    return n_alt


def pid_link_stats(pid_ix, docs, stats):
    """add_drive_urls 之後才知道哪些圖紙的 PDF 有雲端硬碟連結：no_url＝沒有連結的圖紙張數、no_url_docs＝PDF 份數，寫進 index.pid.stats
    與 stats.pid，並印出來（不可默默少掉連結）。回傳沒有連結的檔名清單。"""
    ams = [m for m in pid_ix['sheets'].values() if m.get('rows', 1)]   # GE 編號卡才用到的圖紙（rows 0）另計 ge_no_url，AMS 的數字不變
    miss = sorted({m['d'] for m in ams if not (docs.get(m['d']) or {}).get('url')})
    st = pid_ix.setdefault('stats', {})
    st['no_url'] = sum(1 for m in ams if m['d'] in miss)
    st['no_url_docs'] = len(miss)
    gmiss = sorted({m['d'] for m in pid_ix['sheets'].values() if m.get('ge') and not (docs.get(m['d']) or {}).get('url')})
    if any(m.get('ge') for m in pid_ix['sheets'].values()):
        st['ge_no_url'] = sum(1 for m in pid_ix['sheets'].values() if m.get('ge') and m['d'] in gmiss)
    stats['pid'] = dict(st, bytes=pid_ix.get('bytes'))
    names = [(docs.get(k) or {}).get('title') or k for k in miss]
    print('pid: %d 張圖紙（%d 份 PDF）沒有雲端硬碟連結（drive_map 裡沒有那一份檔；卡片上不附「開啟 PDF」）%s'
          % (st['no_url'], len(miss), ('：' + '、'.join(names[:10]) + ('…' if len(names) > 10 else '')) if names else ''))
    return names


def pid_doc(st):
    """index.searched['pid'] 的一筆：把「文件庫現行的 P&ID 圖面」整批當一份文件描述（不含本機路徑；每張圖紙自己的 PDF 另有 docs 項目與連結）。
    數字全部取自 st＝stats.pid（pid_index 的掃描範圍＋這次發布的實際數字），不讀 pid.json——所以 --no-pid 保留上次發布的資料時也能重寫。"""
    def g(k):
        return st.get(k) if st.get(k) is not None else '?'

    def n(k):   # 是數字才回（缺鍵、舊資料 → None，那一句就不寫）
        v = st.get(k)
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    # 文字層與 OCR 各比對了多少頁（2026-10-10 稽核：原本寫「圖上位號是線條字的頁面再以離線 OCR 補（N 頁用到 OCR 結果）」，
    # 實際上是**每一張圖紙頁都做過 OCR**（pages_ocr），其中 pages_sparse 頁文字層幾乎沒有字、位號只在 OCR 結果裡）。數字全取自 stats，缺哪個就不講那一段
    how = []
    if n('pages_cover'):
        how.append('其中 %d 頁是封面、目錄等非圖紙頁' % n('pages_cover'))
    if n('pages_text') is not None:
        how.append('%d 頁有 PDF 文字層可比對' % n('pages_text'))
    if n('pages_ocr'):
        sheet_pages = n('pages_sheet') if n('pages_sheet') is not None else ((n('pages') - (n('pages_cover') or 0)) if n('pages') is not None else None)
        how.append((('所有圖紙頁都做過離線 OCR（%d 頁）' if sheet_pages == n('pages_ocr') else '%d 頁做過離線 OCR') % n('pages_ocr'))
                   + (('，其中 %d 頁的位號只在 OCR 結果裡（那幾頁沒有可用的文字層）' % n('pages_sparse')) if n('pages_sparse') else ''))
    elif n('pages_ocr') == 0:
        how.append('還沒有離線 OCR 的結果（位號不在文字層的圖面找不到）')
    why = ('工程文件庫現行的 P&ID／流程圖 PDF（每份圖只取最高版次，舊版次圖面上的位置不採用；二、三號機組專用的圖面不列入），共 %s 份 %s 頁%s。'
           '在圖上找到 %s/%s 支現行 AMS 位號；這次發布 %s 台設備、%s 張圖紙影像（%s 份 PDF）%s。'
           '機組歸屬：圖上就是本台 > 圖面不分機組 > 以另一台機組繪製的典型圖 > 同一迴路編號／圖面註明適用於同型各台，每支位號只發布最好的那一級'
           '（以儀器符號旁的標籤為準；圖上註記與表格、跨圖訊號旗標、空氣分配圖的用氣點、迴路詳圖只是引用，照實標出、不當成儀器的位置）；'
           '共用（C10）與各機組（G11／G12）的位號不互相套用。%s'
           % (g('drawings'), g('pages'), ('：' + '；'.join(how)) if how else '', g('located'), g('ams_tags_base'), g('devices'), g('images'), g('docs'),
              ('，其中 %d 台只找到引用、沒有找到儀器符號' % n('devices_ref_only')) if n('devices_ref_only') else '',
              ('%s 張圖紙的 PDF 在雲端硬碟對照（drive_map）裡找不到那一份檔，卡片上不附連結。' % st['no_url']) if st.get('no_url') else ''))
    return {'doc_id': 'pid-drawings', 'rev': '%s 份圖面' % g('drawings'),
            'ref': '現行 P&ID 圖面（%s 份 %s 頁，PDF 文字層%s）' % (g('drawings'), g('pages'), '＋OCR' if st.get('pages_ocr') else ''),
            'title': 'P&ID 圖面（工程文件庫現行版次）', 'folder': '工程文件庫各系統的圖面資料夾（唯讀；每張圖紙所屬的 PDF 另有自己的連結）',
            'used': True, 'why': why}


# ------------------------------------------------------------------ GE 原廠編號的 P&ID 圖面與圖控 HMI 位置（v10）
# 來源：tools/db/pid_ge.py（pid_ge.json：GE 示意圖上括號裡的 GE 編號標籤＋對照表 KKS 的球泡，同一處併成一個標記）與 tools/db/hmi_ge.py
# （hmi_ge.json：畫面物件引用這個編號的 Mark VIe I/O 訊號，或畫面上寫著這個編號）。列的格式與 AMS 設備的 sec.pid／sec.hmi 完全相同，
# 前端直接交給 fillPid／fillHmi（細部視窗、小地圖、燈箱、縮圖共用）；GE 才有的意思放在第一列 extra 的 via／shared／gu／ctrl。
GE_PID_VIA = ('ge', 'kks', 'ge+kks')
GE_PID_VIA_TEXT = {'ge+kks': '圖上的 GE 編號標籤與它的 KKS 在同一處', 'ge': '圖上寫的 GE 編號標籤',
                   'kks': '這一處只寫 KKS、沒寫 GE 編號，依對照表的 KKS 對到這個編號'}
GE_PID_FORM_TEXT = {'text-slash': '斜線合寫的編號（例 39VE-7R/T）展開後對上', 'stacked-sub': 'KKS 本體與子件尾碼上下兩行拆寫，合併後對上',
                    'ocr-stacked': 'KKS 上下兩行拆寫，合併後對上'}
GE_HMI_MAX = 6   # 每個 GE 條目、每部機組最多列幾張圖控畫面（SIL 各頁共用「最終元件」面板：VS4-4 一部機就有 25 張）；其餘只列畫面名（hmx）
GE_HMI_SIL = re.compile(r'_SIL_', re.I)   # SIL 畫面排在製程畫面之後（同一個面板在十幾張 SIL 畫面重複）
GE_LOC_RULE = ('GE 原廠編號的位置：P&ID 取自工程文件庫現行 GE 示意圖／P&ID（PDF 文字層＋離線 OCR；括號裡的 GE 編號標籤與對照表 KKS 的球泡，'
               '同一處併成一個標記）；圖控取自 Screens 根目錄的 .cim（物件引用這個編號的 Mark VIe I/O 訊號，或畫面上寫著這個編號）；'
               '位置圖取自 GE 清單「位置圖」欄列的圖（配置／電纜槽／導管／外型圖，文件庫現行最高版次的 PDF 文字層：圖上的 GE 編號或 KKS）')
GE_LD_VIA_TEXT = {'ge': '圖上寫的 GE 編號', 'kks': '圖上只寫 KKS（不帶機組）、沒寫 GE 編號，依對照表的 KKS 對到這個編號'}
GE_LD_FORM_TEXT = {'text-slash': '斜線合寫的編號（例 96PG-5A/B/C）展開後對上', 'text-comma': '逗號接續的編號（例「TT-WR-3A,3B,3C」）展開後對上',
                   'text-lookalike': '圖上的字與清單寫法差一個形近字（I／1、O／0，例 TT-WSIF1-2＝TT-WS1FI-2、F0-2921＝FO-2921）；全範圍只對到這一個編號才收'}
GE_LD_STATE = {'nofile': '文件庫裡找不到這份圖', 'noscope': '這份圖的範圍（燃機／汽機）與這個編號不同，沒有比對',
               'miss': '圖上（PDF 文字層）沒有讀到這個編號或它的 KKS', 'hit': '有位置', 'cap': '有位置，但超過每個編號的張數上限沒有列出'}


def ge_loc_key(e):
    """GE 條目在 pid_ge.json／hmi_ge.json 的鍵＝「<system>|<GE 編號>」（system 照對照表原樣：GT／ST／GT-GEN／ST-GEN）。"""
    return '%s|%s' % (e.get('system') or '', e['tag'])


def ge_pid_label_text(use, scope, has_symbol):
    """GE 卡「圖上標示」：圖上的字＋它為什麼是這一顆（GE 編號標籤／KKS／共用 KKS）＋這一處是不是儀器符號。"""
    e = use[0]
    lab = pid_label_clean(e.get('label'))
    why = [GE_PID_VIA_TEXT.get(e.get('via'), '')]
    units = sorted({u for x in use for u in x.get('units') or []})
    if e.get('rel') == 'exact' and units:
        why.append('圖上寫的是 %s 的 KKS（全名帶機組）' % '／'.join(units))
    elif e.get('rel') == 'neutral':
        why.append('圖面不分機組（GE 編號與 KKS 都不帶機組），各機組共用')
    if e.get('shared'):
        why.append('這個 KKS 也是 %s 的 KKS（同一套設備的閥本體、定位器、電磁閥、極限開關常共用一個 KKS），標的是共用的那個位置，屬推論'
                   % '、'.join(e['shared'][:6]) + (' 等' if len(e['shared']) > 6 else ''))
    t = '%s%s（%s）' % ('OCR 讀到的字：' if e.get('how') == 'ocr' else '', lab or '（圖上的字沒有記錄）', '；'.join(w for w in why if w))
    c = pid_note(e)
    if c:
        t += '；' + PID_NOTE_TEXT.get(c, PID_NOTE_OTHER[1]).replace('這支位號', '這個編號')
        t += '；儀器符號畫在另一張圖紙上' if has_symbol else '；這次比對（PDF 文字層＋OCR）沒有讀到這個編號的儀器符號，不代表圖上沒有畫，請開 PDF 確認'
    return t


def ge_pid_rows(pm, ents, scope, kks=()):
    """一個 GE 條目的 P&ID 列（與 pid_rows 同格式：每張圖紙一組 5 列，第一列 extra 帶 s／d／p／n／img／marks／drawn／rel／how…）。
    同一張圖上只有某一部機的命中（BOP 圖分別印 G11／G12 的 KKS）各成一組，extra.gu＝那幾部機，前端依輸入的機組篩；
    不分機組的不帶 gu。lvl：文字層而且不是共用 KKS → doc；OCR 或共用 KKS → inferred。"""
    site = set(GE_SITE_UNITS.get(scope) or ())
    subs = {p[2] for p in map(ge_kks, kks or ()) if p and p[2]}   # 條目 KKS 的子件尾碼（BG04、MB01…）：圖上的字沒有它＝框的是主設備
    order, groups = [], {}
    for e in ents:
        k = (e['sheet'], tuple(sorted(e.get('units') or ())))
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(e)
    has_symbol = any(not pid_note(e) for e in ents)
    rows = []
    for gi, k in enumerate(order):
        s, units = k
        sh = pm['sheets'][s]
        use, marks = pid_marks(groups[k])
        e = use[0]
        lvl = 'doc' if (e['how'] == 'text' and not any(x.get('shared') for x in use)) else 'inferred'
        src = '%s · %s 第 %s 頁' % (src_prefix(lvl), sh['rel'].rpartition('/')[2], sh['page'])
        base = {'s': s, 'g': gi}
        first = dict(base, d=pm['_dkey'][s], p=sh['page'])
        if isinstance(sh.get('pages'), int):
            first['n'] = sh['pages']
        lab = pid_label_clean(e.get('label'))
        first.update(img=True, marks=marks, drawn=lab, unit='', rel=e['rel'], how=e['how'], via=e.get('via'))
        if units and set(units) != site:
            first['gu'] = list(units)
        if e.get('shared'):
            first['shared'] = e['shared'][:8]
        if e.get('via') == 'kks' and subs and not any(sf in ge_cmp(e.get('label')) for sf in subs):
            first['on_body'] = 1
        confs = [x['conf'] if (x.get('how') == 'ocr' and isinstance(x.get('conf'), (int, float)) and not isinstance(x.get('conf'), bool)) else None for x in use]
        if confs[0] is not None:
            first['conf'] = confs[0]
        if any(c is not None for c in confs):
            first['conf_min'] = min(c for c in confs if c is not None)
            first['confs'] = confs
        if e.get('zone'):
            first['zone'] = e['zone']
            if e.get('zone_near'):
                first['zone_near'] = 1
        codes = [pid_note(x) for x in use]
        if all(codes):
            first['note'] = codes[0] if len(set(codes)) == 1 else 1
        if any(codes):
            first['notes'] = codes
        how = pid_how_text(use, sh)
        ft = GE_PID_FORM_TEXT.get(e.get('form') or '')
        if ft:
            how += '；' + ft
        rows.append(['P&ID 圖面', pid_sheet_name(sh), lvl, src, first])
        rows.append(['圖面頁次', 'PDF 第 %s 頁%s' % (sh['page'], ('（共 %s 頁）' % sh['pages']) if isinstance(sh.get('pages'), int) else ''), lvl, src, dict(base)])
        rows.append(['所在位置', pid_pos_text(use, marks).replace('這支位號', '這個編號'), lvl, src, dict(base)])
        lab_t = ge_pid_label_text(use, scope, has_symbol)
        if first.get('on_body'):
            lab_t += '；框的是主設備（閥本體、馬達）：這個編號是它的附屬件（KKS 帶子件尾碼 %s），這張圖上沒有單獨畫' % '／'.join(sorted(subs))
        rows.append(['圖上標示', lab_t, lvl, src, dict(base)])
        rows.append(['對應方式', how, lvl, src, dict(base)])
    return rows


def ge_ld_rows(pm, ents, scope, kks=()):
    """一個 GE 條目的位置圖列（v12；格式同 ge_pid_rows：每張圖紙一組 5 列，第一列 extra 帶 s／d／p／n／img／marks／drawn／rel／how／via，
    另有 listed＝GE 清單的「位置圖」欄有列這份圖（0＝沒列、圖上卻寫著這個編號））。
    lvl：文字層、清單有列、圖上指著元件（note 0）、不是共用 KKS → doc；其餘（清單沒列、只在設備表、共用 KKS）→ inferred。"""
    order, groups = [], {}
    for e in ents:
        if e['sheet'] not in groups:
            groups[e['sheet']] = []
            order.append(e['sheet'])
        groups[e['sheet']].append(e)
    has_callout = any(not pid_note(e) for e in ents)
    rows = []
    for gi, s in enumerate(order):
        sh = pm['sheets'][s]
        use, marks = pid_marks(groups[s])
        e = use[0]
        listed = any(x.get('listed') for x in use)
        body = e.get('form') == 'body'
        lvl = 'doc' if (e['how'] == 'text' and not pid_note(e) and not e.get('shared') and e.get('form') != 'text-lookalike') else 'inferred'
        src = '%s · %s 第 %s 頁' % (src_prefix(lvl), sh['rel'].rpartition('/')[2], sh['page'])
        base = {'s': s, 'g': gi}
        first = dict(base, d=pm['_dkey'][s], p=sh['page'])
        if isinstance(sh.get('pages'), int):
            first['n'] = sh['pages']
        lab = pid_label_clean(e.get('label'))
        first.update(img=True, marks=marks, drawn=lab, unit='', rel=e['rel'], how=e['how'], via=e.get('via'), listed=1 if listed else 0)
        if e.get('shared') and not body:
            first['shared'] = e['shared'][:8]
        if body:
            first['on_body'] = 1   # 圖上沒有單獨畫這個編號：框的是共用 KKS 本體的主設備（前端標頭「※ 框的是主設備」）
        if e.get('zone'):
            first['zone'] = e['zone']
            if e.get('zone_near'):
                first['zone_near'] = 1
        codes = [pid_note(x) for x in use]
        if all(codes):
            first['note'] = codes[0] if len(set(codes)) == 1 else 1
        if any(codes):
            first['notes'] = codes
        why = ['' if body else GE_LD_VIA_TEXT.get(e.get('via'), ''), 'GE 圖不分機組，各機組共用' if e.get('rel') == 'neutral' else '']
        if body:
            why.append('圖上沒有單獨畫這個編號；框的是與它共用 KKS 本體的主設備 %s（閥本體、馬達），屬推論' % '、'.join(e.get('shared') or []))
        elif e.get('form') == 'alias':
            why.append('圖上寫的是 %s：與這個編號的 KKS 完全相同、寫法相近（括號寫法或改過號），推論是同一顆' % '、'.join(e.get('shared') or []))
        elif e.get('stack'):
            why.append('KKS 與 GE 編號上下兩行疊寫，併成一個框')
        if e.get('shared') and not body and e.get('form') != 'alias':
            why.append('這個 KKS 也是 %s 的 KKS，標的是共用的那個位置，屬推論' % ('、'.join(e['shared'][:6]) + (' 等' if len(e['shared']) > 6 else '')))
        lab_t = '%s（%s）' % (lab or '（圖上的字沒有記錄）', '；'.join(w for w in why if w))
        c = pid_note(e)
        if c:
            lab_t += '；' + PID_NOTE_TEXT.get(c, PID_NOTE_OTHER[1]).replace('這支位號', '這個編號')
            lab_t += '；圖上指著元件的標註在另一張位置圖' if has_callout else '；這次比對（PDF 文字層）沒有讀到指著元件的引線標註，請開 PDF 看設備表所屬的視圖'
        how = 'PDF 文字層'
        ft = GE_LD_FORM_TEXT.get(e.get('form') or '')
        if ft:
            how += '（%s）' % ft
        how += ('；GE 清單的「位置圖」欄列了這份圖（%s）' % (sh.get('doc') or '') if listed
                else '；GE 清單的「位置圖」欄沒有列這份圖（%s），圖上寫著這個編號' % (sh.get('doc') or ''))
        if sh.get('tap'):
            how += '；這是壓力量測的配置圖：引線有的指傳送器本體，有的指取壓點、根閥或導壓管，請對照圖面'
        rows.append(['位置圖', pid_sheet_name(sh), lvl, src, first])
        rows.append(['圖面頁次', 'PDF 第 %s 頁%s' % (sh['page'], ('（共 %s 頁）' % sh['pages']) if isinstance(sh.get('pages'), int) else ''), lvl, src, dict(base)])
        rows.append(['所在位置', pid_pos_text(use, marks).replace('這支位號', '這個編號'), lvl, src, dict(base)])
        rows.append(['圖上標示', lab_t, lvl, src, dict(base)])
        rows.append(['對應方式', how, lvl, src, dict(base)])
    return rows


GE_WIRE_HOP = {'conn': 'GE 接線表（元件 → 撬上接線箱）', 'wire': '接線圖', 'jbloc': '接線箱位置', 'gtjb': '撬上接線箱位置（GE 外形等角圖）',
               'gtjbt': '撬上接線箱座標（GE 外形圖的 JB 表）', 'jbdoc': '接線箱所在的設備圖', 'mcc': '電氣盤格位（GE EP24 盤面配置圖）', 'cs': '電纜表',
               'cab': '盤內板位', 'vms': '3500 盤端子', 'rack': '3500 機架槽位', 'bnw': '3500 接線表（Bently 盤圖）',
               'epnl': '電氣盤端子排（設備配置圖）'}
GE_WIRE_REL = {'conn': 'neutral', 'wire': 'exact', 'jbloc': 'exact', 'gtjb': 'neutral', 'gtjbt': 'neutral', 'jbdoc': 'neutral', 'mcc': 'exact', 'cs': 'exact',
               'cab': 'neutral', 'vms': 'neutral', 'rack': 'neutral', 'bnw': 'neutral', 'epnl': 'neutral'}   # 一號機專屬的圖（接線圖、JB 位置圖、電纜表、各機組一份的 MCC／PC 盤面配置）＝就是本台；
#                                                                           GE 的表與控制盤盤面配置、Bently 盤圖各機組共用一份
GE_WIRE_MCC_RE = re.compile(r'[GS]\d{2}B[FGK][AB]\d0[_-](NP\d-\d|A\d{1,2}[A-H]|\d{1,2}[A-F])\b')   # 480 V MCC／PC 的格位（同 wire_ge.MCC_RE；'S10BGB10-A2A' 用連字號）
GE_WIRE_MCC_MATCH = {'same': '格內寫的 %s 與這個元件的 KKS 相同', 'same_rel': '格內寫的 %s 與接線圖說明格寫的設備 KKS 相同（這個元件自己的 KKS 沒有寫在這一格）',
                     'system': '格內寫 %s，與這個元件的 KKS 同系統、設備號不同',
                     'breaker': '格內只寫這一格的斷路器編號 %s，沒有負載的 KKS 可以比對', 'nokks': '格內寫 %s；接線圖這一條沒有 KKS 可以比對',
                     'diff': '格內寫 %s，與這個元件的 KKS 不同（見註記）', 'space': '格內寫「%s」（備用，見註記）', 'none': '格內沒有讀到設備編號%s'}
GE_WIRE_RULE = ('接線路徑（v14）：現場→接線箱→電子室盤的每一條芯，取自一號機兩份儀控電纜接線圖（汽機 HT1-1-ICE01-D1005、燃機 HT1-1-ICE01-D1004，'
                '現行最高版次 PDF 的文字層與向量框線；盤側以芯色標籤序列對接，標籤筆誤照順序補配並註記）；燃機撬上的「元件 → 接線箱端子」取自 '
                'GE 138T5502 Turbine Connection Diagram（HT0-1-GID01-D0003，Rev M AS-BUILT），以接線箱／端子排／端子號接上接線圖；'
                'Foundation Fieldbus 元件接到它所在的段幹線，以控制器組態的 FF_IN_S 段號核對；盤端子落在 Mark VIe 端子板的，以 signal-atlas 控制器索引的螺絲號'
                '（含 TDBT 的 TB1／TB2）核對是不是這顆元件（✓ 同一顆、≈ 名稱寫法不同、✗ 組態掛的是別顆或備用點）；接線箱位置取自汽機房儀器與 JB 位置圖'
                '（HT1-1-IIF01-D0004）、GE 燃機外形圖（HT0-1-GAD01-D0001），兩份都沒有的箱子取自 GE／廠商的設備外形與配置圖（發電機電氣外形圖、氫氣封油盤、'
                '乾燥器、氫氣偵測、汽機 VE02 控制接線位置圖、VR20 油箱、細水霧撬：只有箱子在設備上的位置，沒有廠區座標）；接線圖「接線箱」欄其實是 MCC、GPP、MSP 等'
                '電氣盤的，寫明不是接線箱並附格位，480 V MCC／PC 的格位（v15）框在 GE EP24 盤面配置圖（EQUIPMENT ARRANGEMENT，各機組一份）正視圖上那一格，'
                '並把格內寫的 KKS 與元件比對；沒有位置圖的附電纜表上那一端的房間；房間取自一號機儀控電纜表（HT1-1-ILE01-A1004／A1005），盤內板位取自 GE 盤面配置'
                '（汽機 HT0-1-TZD01-M0213、燃機 HT0-1-GID01-A1002），3500 盤端子與機架槽位取自 Bently 3500 盤圖（GE 120V8111）；'
                '文件互相矛盾的地方列在註記，不替任何一方選邊')
GE_WIRE_MODE = {'coax': '近接探頭：同軸延長線接到接線箱裡的前置器', 'tb': '現場端子經電纜接到接線箱端子排',
                'jbdev': '元件畫在接線箱裡（撬上接線箱、閥體接線盒、發電機 JB、MCC 或本地盤）：箱內端子 → 幹線 → 盤',
                'direct': '電纜從現場直拉到盤，中間沒有接線箱',
                'ff': 'Foundation Fieldbus：元件 → 段保護器的埠 → 段幹線（好幾顆元件共用）→ 電子室盤的 FF 電源調節器 → 控制器的 FF 變數'}
GE_WIRE_OK = ('same', 'logic', 'equip', 'loc', 'suffix')
GE_WIRE_MV = ('TVBA', 'TTUR', 'TCSA', 'TBAI', 'SHRA', 'TDBT', 'TRLY', 'STTC', 'SCSA', 'STAI', 'STAO', 'SRTD', 'TSVC', 'TRPG', 'TBCI', 'SDII', 'TBTC', 'TCDM', 'SPID')   # Mark VIe 端子板（wire_ge.MARKVIE_BOARDS＋圖上的 TBTC）


def ge_wire_join(xs):
    """端子號、芯色清單 → 'A／B／C'（去掉空的、照原順序、不重複）。"""
    out = []
    for x in xs:
        if x and x not in out:
            out.append(x)
    return '／'.join(out)


def ge_wire_room(desc, panel_kks):
    """接線圖盤欄的說明 'S10CCM01UC201 ST TCP ST ELECTRONIC EQUIPMENT BUILDING EER ( E-402)'、'G11CCJ01UC201 GT TCP GT ELECTRICAL BUILDING(E-305)' → (盤名, 房間)。"""
    d = re.sub(r'\s+', ' ', desc or '').strip()
    if panel_kks and d.startswith(panel_kks):
        d = d[len(panel_kks):].strip()
    m = re.search(r'\b((?:GT|ST)\s+(?:ELECTRONIC|ELECTRICAL)\b.*|MAIN\s+CONTROL\s+BUILD.*|(?:GT|ST)\s+(?:HALL|OUTDOOR)\b.*)$', d)
    room = re.sub(r'\(\s*', '(', re.sub(r'\s*\)', ')', m.group(1))).strip() if m else ''
    room = re.sub(r'\(E-\s*(\d+)\)+', r'(E-\1)', room).replace('BUILDIG', 'BUILDIG〔原文〕')
    name = d[:m.start()].strip() if m else d
    return name, room


GE_WIRE_PANEL_RE = re.compile(r'\b[GSC]\d{2}(?:B[FGHJK][AB]\d{2}|MKY|CCS|CCD|CBJ|MSC|MBJ10UC|MKC10QA)|C\d0B[BC]T10|MCC|POWER CENTER|STARTER|CUBICLE|CONSOLE|PANEL|\bGPP\b|\bMSP\b|\bGCB\b|\bUAT\b')   # 電氣盤／設備（名稱 JB 開頭的不算）


def ge_wire_ep_txt(e):
    """其餘電氣盤的一端（wire_ge 的 paths[k].ep 一筆）→ 「〈圖〉第 N 頁 框端子排 …；框端子 …（n 芯都找到）；端子表：…；〈版次狀態〉」（v16）。
    端子排標籤（配置圖上的 'TBTCD（共 26 點）'）與端子分開寫；同一號有幾格並接的註明框整組；全部列出（不截斷）。"""
    if not e:
        return ''
    rows = '、'.join(' '.join(x for x in r_ if x) for r_ in (e.get('rows') or []))
    n, ok = e.get('n', 0), e.get('ok', 0)
    cnt = ('%d 芯都找到' % n) if ok == n else ('%d 芯中 %d 芯找到' % (n, ok))
    if e.get('whole'):
        what = '框出整面盤（接線圖只寫端子排，沒寫在哪個隔間）'
    else:
        what = '；'.join(x for x in (('框端子排 %s' % '、'.join(e['strips'])) if e.get('strips') else '',
                                     ('框%s %s' % ('隔間' if e.get('lv') == 'cmp' else '端子', '、'.join(e.get('labs') or []))) if e.get('labs') else '') if x)
    dn = e.get('dn') or ''
    out = '%s 第 %s 頁 %s（%s）' % (e['doc'], '、'.join(str(x) for x in e.get('pages') or []), what, cnt)
    if e.get('multi'):
        out += '；%s 是同一號幾格並接，框整組（電纜落在哪一格圖上沒標）' % '、'.join(e['multi'])
    if rows:
        out += '；端子表：' + rows
    if e.get('analog'):
        out += '；本台沒有向量圖，框在 %s 的圖上（類比：圖上畫的是另一台，本台取同一位置%s）' % (
            e['analog'], '；本台 52L1、52L3 對調，本台正式圖 HT0-1-EGJ01-D0072（226B4842，掃描圖）' if e.get('grp') == 'msp' else '')
    elif e.get('shared') and '共用' not in dn and '竣工' not in dn:
        out += '；這份圖各台共用一份，不是本台竣工'
    if dn:
        out += '；' + dn
    return out


def ge_wire_jbt(t):
    """接線圖端子格的寫法整理：\"-TBTCD '01\" → 'TBTCD 01'（撇號是圖面殘字）。"""
    return re.sub(r"^-?([A-Z][\w()]*)\s*'(\d+)$", r'\1 \2', t or '')


def ge_wire_own_tb(cond):
    """端子格自己帶端子排名（'TB2 27'、'A03-X1 27'、\"-TBTCD '01\"）→ True：表頭的端子排名（可能抄錯，如 UAT 那頁的 TB06）就不再加在前面。"""
    cs = [c['jb'] for c in cond if c.get('jb')]
    return bool(cs) and all(re.match(r"^-?[A-Z][\w()/-]*[\s']+'?\d", x) for x in cs)


def ge_wire_recv(r):
    """電氣盤這一端是受控端（指示燈、合閘迴路）、接點在另一端 → 另一端的說明；不是 → ''。
    Mark VIe 繼電器輸出（訊號列是「繼電器…輸出」）或手動同步盤的 XDI（燈的輸入）都是這種。"""
    rel = [x[0] for x in r.get('sig') or [] if str(x[1]).startswith('繼電器')]
    if rel:
        return '控制盤 Mark VIe 繼電器輸出 %s' % '、'.join(dict.fromkeys(rel))
    ej = next((x for x in r.get('ep') or [] if x['end'] == 'jb'), None)
    w = r.get('wire') or {}
    if ej and ej.get('grp') == 'msp' and (str(w.get('jb_tb', '')).startswith('XDI') or any(str(c.get('jb', '')).startswith('XDI') for c in r.get('cond') or [])):
        return '電纜另一端 %s 的接點' % (' '.join((w.get('panel_desc') or w.get('panel') or '?').split()[:3]))
    return ''


def ge_wire_bsrc(sh):
    """3500 盤圖那一頁的出處：兩份同名檔（汽機、燃機的 noKKS_CABINET DESIGN DRAWING_rev-）要帶資料夾。"""
    rel = sh.get('rel', '')
    return 'PDF 文字層 · %s／%s 第 %s 頁' % (rel.split('/')[0], rel.rpartition('/')[2], sh.get('page', '?'))


def ge_wire_rooms(r, w):
    """電纜表一列兩端的房間 →（接線箱或現場那一端, 盤那一端），各為 '房間說明（房間碼）' 或 ''。
    電纜表一列兩端各有房間碼、房間說明、設備碼；設備碼含接線箱 KKS 的那一端就是接線箱（多半是第二端），否則取第二端（第一端多半是電子室盤）。"""
    rm = r.get('room') or {}
    jk = re.findall(r'[GSC]\d{2}[A-Z]{3}\d{2}(?:[A-Z]{2}\d{2,3}[A-Z]?|_\w+)?', w['jb'] + ' ' + (w.get('jb_desc') or ''))
    e = '1' if jk and jk[0] in (rm.get('d1') or '') and jk[0] not in (rm.get('d2') or '') else '2'

    def end(k):
        rd, rc = (rm.get('r%sd' % k) or '').replace('BUILDIG', 'BUILDIG〔原文〕'), rm.get('r' + k) or ''
        return ('%s（%s）' % (rd or '—', rc)) if rc else rd
    return end(e), end('2' if e == '1' else '1')


def ge_wire_jb_room(r, w):
    """接線箱（或現場盤）那一端在電纜表上的房間（v14）→ '房間說明（房間碼）' 或 ''（ge_wire_rooms 的第一個）。"""
    return ge_wire_rooms(r, w)[0]


def ge_wire_loop(r, w, pk, pname, room, where, jls):
    """迴路圖（v15，card.js fillLoop 畫成 ISA-5.4 式單線圖）要的分開欄位：sum 是給人讀的句子，迴路圖要一格一格的值（空的不輸出）——
    kk＝本台 KKS；ds＝接線圖上的說明；fc／fs＝現場電纜與規格；jb／jd／jt／px＝接線箱、說明、端子排、前置器；jl＝接線箱位置（短句）；
    tc／ts／tl＝幹線、規格、長度 m（電纜表）；rf／rp＝電纜表上接線箱（或現場）那一端、盤那一端的房間；pk／pn／pr＝盤 KKS、盤名、盤所在房間；
    cp＝盤內位置（板位、背板／側板、板名）；io＝[[控制器, I/O 模組, 板位, 板名, 點, 變數, 核對]…]；ff＝[段, 埠, FF_IN_S 段號, [變數…]]（FF 元件）；
    fm＝[元件…]（這一條是 FF 段保護器本身：接在這一段的元件）；pg＝[接線圖 PDF 頁, Sheet, 共幾張]；
    sb＝[IS 屏蔽排, OS 屏蔽排]（接線圖盤欄底部的說明：各芯屏蔽接 IS 排、電纜總屏蔽接 OS 排再接地）；kw＝接線圖說明格寫的 KKS（與 kk 不同時）；
    v16：md＝中間設備 [[在哪（jb 箱內／field 另一個箱子／self 這個編號本身在箱內／pre 上游）, 名稱, 說明, 進線端, 出線端, 等級]…]、mg＝沒有圖的那一段、m1＝只有一條光纖進線；
    bx＝3500 並聯分支 [種類, 機架, 槽, 通道, 模組, 接頭, 另一種讀法, 等級]；sg＝訊號型式與供電 [[點, 訊號, 供電, 等級]…]。"""
    rf, rp = ge_wire_rooms(r, w)
    rm = r.get('room') or {}
    d = {'kk': r.get('kks') or '', 'ds': ' / '.join(dict.fromkeys((w.get('drawn') or '').split(' / ')))[:160], 'fc': w['field_cable'], 'fs': w['field_spec'],
         'jb': w['jb'], 'jd': w['jb_desc'], 'jt': '' if w['jb_tb'] == '*' or r['mode'] == 'direct' or ge_wire_own_tb(r['cond']) else w['jb_tb'], 'px': w['prox'], 'jl': jls, 'tc': w['trunk'], 'ts': w['trunk_spec'], 'tl': rm.get('len') or '',
         'rf': rf, 'rp': rp, 'pk': pk, 'pn': pname, 'pr': room, 'cp': where,
         'io': [list(x[:6]) + [x[7] if len(x) > 7 else ''] for x in r.get('io') or []], 'pg': [w['page'], w['sheet'], w['of']],
         'sb': [r['shield']['IS'], r['shield']['OS']] if r.get('shield') else [], 'kw': r.get('kks_drawn') or ''}
    md = r.get('mid') or {}
    if md.get('chain'):
        d['md'] = [[c.get('at', ''), c.get('n', ''), c.get('s', ''), c.get('i', ''), c.get('o', ''), c.get('g', '')] for c in md['chain']]
        d['mg'] = md.get('gap') or ''
        d['m1'] = md.get('one') if md.get('one') in ('coax', 'fiber') else (1 if md.get('one') else 0)   # 現場 → 中間設備只有一條線（同軸／光纖）
        if md.get('ns'):
            d['ns'] = 1                                                   # 屏蔽不從元件拉（同軸、盤內接地、GE 段與幹線兩段不連）
    bx = r.get('bx') or {}
    if bx.get('kind') and bx['kind'] != 'ghm':
        alt = bx.get('alt') or {}
        d['bx'] = [bx['kind'], bx.get('rack') or '', bx.get('slot') or '', bx.get('ch') or '', bx.get('mod') or '', bx.get('conn') or '',
                   ('RACK %s SLOT %s CH%s' % (alt.get('rack', '?'), alt.get('slot', '?'), alt.get('ch', '?'))) if alt else '', bx.get('g') or '',
                   bx.get('via') or '', re.sub(r'（[^）]*）$', '', bx.get('panel') or ''), bx.get('aw') or '']
    if r.get('sig'):
        d['sg'] = [x[:4] for x in r['sig'][:4]]
    ff = r.get('ff') or {}
    if r['mode'] == 'ff' and ff.get('seg'):
        d['ff'] = [ff['seg'], ff.get('port') or '', ff.get('s') or '', ff.get('vars') or ff.get('dev_vars') or []]
        oth = [x for x in ff.get('members') or [] if x != r.get('tag')]
        if oth:
            d['fsm'] = oth[:10]                                           # 同一段的其他元件（ISA-5.4：與其他迴路的關聯）
    elif r['mode'] == 'ff' and ff.get('members'):
        d['fm'] = ff['members'][:16]
    return {k: v for k, v in d.items() if v not in ('', [], None)}


def ge_wire_card(pm, key, r, pi=0, multi=False, lno=''):
    """wire_ge.json 的 paths[key][pi] → GE 卡「接線路徑」的一條路徑（v13 起；v14 一個編號可以有好幾條：兩台燃機、多組接點）：
    u＝機組；sum＝每一跳一列 [跳, 內容, lvl, 出處]；t＝每條芯一列 [芯（幹線芯色）, 現場端子, 接線箱端子, 盤端子, Mark VIe 腳位, 核對, 盤端子號, 組態的點]；
    d＝迴路圖（v15）的分開欄位（ge_wire_loop）；lno＝迴路圖編號（v16，ge_wire_cards 依機組編）；
    f＝現場那一跳（燃機：GE 138T5502 一芯一列）[[元件端子, 芯色, 電纜, 中間元件, 接線箱, 端子, 接線箱所在, 版次]…]；
    rows＝各跳的圖（與 ge_pid_rows 同格式：每張圖紙 5 列，第一列 extra 帶 s／d／p／n／img／marks／drawn／rel／how／via／hop）；
    n＝註記 [[文字, 出處]]（文件互相矛盾、圖面筆誤：wire_ge 自動找的＋wire_notes.json 人工查證的）；
    jb＝[接線箱, [[JB 端子, 芯, 元件, 盤端子, 是不是 GE 編號]…]]（同一個接線箱的整排端子，照圖上的順序）；mode＝畫法（GE_WIRE_MODE）。"""
    w, sheets = r['wire'], pm['sheets']
    hits = [h for h in (pm.get('_wg') or {}).get(key) or [] if h.get('pi', 0) == pi]
    s_wire = next((s for k, s in r['hops'] if k == 'wire'), None)
    sw = sheets.get(s_wire) or {}
    wsrc = 'PDF 文字層 · %s 第 %s 頁（Sheet %s OF %s）' % (sw.get('rel', '').rpartition('/')[2], w['page'], w['sheet'], w['of'])
    cond = r['cond']
    live = [c for c in cond if c['num']]
    pk = re.findall(r'[SG]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}', w['panel'] + ' ' + w['panel_desc'])
    pname, room = ge_wire_room(w['panel_desc'], pk[0] if pk else '')
    s_rows = []
    pan_jb = r['mode'] not in ('direct', 'ff') and not re.match(r'\s*JB', w['jb']) and bool(GE_WIRE_PANEL_RE.search(w['jb'] + ' ' + (w['jb_desc'] or '')))
    recv = ge_wire_recv(r) if pan_jb else ''
    own_tb = ge_wire_own_tb(cond)
    fld = r.get('field') or []
    if fld:
        s_conn = next((s for k, s in r['hops'] if k == 'conn'), None)
        csrc = 'PDF 文字層 · %s 第 %s 頁' % ((sheets.get(s_conn) or {}).get('rel', '').rpartition('/')[2], (sheets.get(s_conn) or {}).get('page', '?'))
        mid = ge_wire_join(x[3] for x in fld)
        dash = [x[0] for x in fld if x[5] in ('- -', '-', '')]
        txt = '元件端子 %s → 電纜 %s → %s%s 端子 %s%s%s' % (
            ge_wire_join(x[0] for x in fld), ge_wire_join(x[2] for x in fld), ('經 %s → ' % mid) if mid else '', ge_wire_join(x[4] for x in fld),
            ge_wire_join(x[5] for x in fld if x[5] not in ('- -', '-')), ('（%s 在 GE 表上沒有端子（-））' % ge_wire_join(dash)) if dash and len(dash) < len(fld) else '',
            ('（GE 表的位置欄：%s）' % ge_wire_join(x[6] for x in fld)) if any(x[6] for x in fld) else '')
        s_rows.append(['現場 → 接線箱（GE 接線表）', txt, 'doc', csrc])
    if r['mode'] == 'ff':
        ff = r.get('ff') or {}
        if ff.get('seg'):
            s_rows.append(['FF 段', '%s 的 %s 埠%s；同一段的元件：%s' % (ff['seg'], ff.get('port') or '?', ('（段保護器在 %s）' % ff['loc']) if ff.get('loc') else '',
                                                               '、'.join(ff.get('members') or []) or '—'), 'doc', wsrc])
        elif ff.get('members'):
            s_rows.append(['FF 段', '這是 FF 段保護器；接在這一段的元件：%s' % '、'.join(ff['members']), 'doc', wsrc])
        s_rows.append(['段幹線', '%s（%s）→ %s %s' % (w['trunk'], w['trunk_spec'], w['jb'], w['jb_desc']), 'doc', wsrc])
    elif r['mode'] == 'coax':
        s_rows.append(['現場 → 接線箱', '探頭 → 同軸延長線 %s（%s）→ 接線箱裡的前置器 %s' % (w['field_cable'], w['field_spec'].replace(' COAX', '').strip() or '同軸電纜', w['prox'] or '?'), 'doc', wsrc])
    elif r['mode'] == 'tb':
        s_rows.append(['現場 → 接線箱', '現場端子 %s → 電纜 %s（%s）→ 接線箱端子排 %s' % (ge_wire_join(c['field'] for c in cond), w['field_cable'], w['field_spec'], w['jb_tb'] or '?'), 'doc', wsrc])
    elif r['mode'] == 'jbdev':
        nm_ = w['jb'] + (('（%s）' % w['jb_desc']) if w['jb_desc'] else '')
        if pan_jb and recv:
            s_rows.append(['現場 → 電氣盤', '%s 盤內是受控端（指示燈、合閘迴路等），接點在另一端（%s）；兩端之間沒有現場電纜' % (nm_, recv), 'doc', wsrc])
        elif pan_jb:
            s_rows.append(['現場 → 電氣盤', '元件（接點）在 %s 盤內，沒有現場電纜' % nm_, 'doc', wsrc])
        elif r.get('unit', 'S10') == 'S10' or not fld:
            s_rows.append(['現場 → 接線箱', '接線圖只把元件畫在 %s 的端子排旁，沒有標元件到箱子的電纜號（這一段請看現場；元件可能在箱內，也可能在箱外就近）' % nm_, 'doc', wsrc])
    else:
        s_rows.append(['現場 → 盤', '現場端子 %s → 電纜 %s（%s）直拉到盤，中間沒有接線箱' % (ge_wire_join(c['field'] for c in cond), w['field_cable'], w['field_spec']), 'doc', wsrc])
    if r['mode'] not in ('direct', 'ff'):
        jl = r.get('jbloc')
        sj = next((s for k, s in r['hops'] if k == 'jbloc'), None)
        gj = r.get('gtjb')
        jd = r.get('jbdoc')
        sd = next((s for k, s in r['hops'] if k == 'jbdoc'), None)
        jd_txt = ('%s %s 第 %s 頁有畫（圖上寫 %s；這張圖只標出箱子在設備上的位置，沒有廠區座標）' % (jd['zh'], sheets[sd].get('doc') or jd['doc'], sheets[sd]['page'], jd['drawn'])
                  if jd and sd else '')
        if jl and sj:
            jb_txt = w['jb'] + '：汽機房儀器與 JB 位置圖 %s 第 %s 頁有畫，圖上座標 %s' % (sheets[sj].get('doc') or '', sheets[sj]['page'], jl['coords'])
        elif gj:
            jb_txt = w['jb'] + '：GE 燃機外形圖 137T6223 有 %s%s' % (gj['name'], ('（JB 表：%s，燃機座標）' % gj['coords']) if gj.get('coords') else '') + \
                ('；%s' % jd_txt if jd_txt else '')
        elif jd_txt:
            jb_txt = w['jb'] + '：' + jd_txt
        else:
            jr = ge_wire_jb_room(r, w)
            nm = w['jb'] + ('（%s）' % w['jb_desc'] if w['jb_desc'] else '')
            cub = GE_WIRE_MCC_RE.search(w['jb']) or re.search(r'_([A-Z]+\d+[A-Z]?(?:-\d+)?)\b', w['jb'])
            if not re.match(r'\s*JB', w['jb']) and GE_WIRE_PANEL_RE.search(w['jb'] + ' ' + (w['jb_desc'] or '')):
                mc = r.get('mcc')
                smc = next((s for k, s in r['hops'] if k == 'mcc'), None)
                mtx = ''
                if mc and smc:
                    codes = re.findall(r'[GSC]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?(?:-[A-Z]{1,2}\d{2})?(?:/\d)?', mc['content'])
                    show = '、'.join(codes[:3]) if codes else (mc['content'][:40] if mc['match'] == 'space' else '')
                    mtx = '；盤面配置圖 %s 第 %s 頁 %s 正視圖上框出 %s 格%s，%s' % (
                        sheets[smc]['rel'].rpartition('/')[2].replace('.pdf', ''), sheets[smc]['page'], mc['lineup'], mc['cub'],
                        '（NP 區小格的銘牌是線條字：照區內隔板由上往下數推算，另框 NP 表那一列）' if mc.get('np') else '',
                        GE_WIRE_MCC_MATCH.get(mc['match'], '%s') % show)
                ej = next((x for x in r.get('ep') or [] if x['end'] == 'jb'), None)   # v16：GPP、手動同步盤、GCB、UAT、LCI 中壓盤／52ET 框到端子（或隔間）
                if ej and not mtx:
                    mtx = '；' + ge_wire_ep_txt(ej)
                jb_txt = nm + '：電氣盤（不是接線箱），接線箱位置圖上不畫' + ('；第 %s 格' % cub.group(1) if cub else '') + mtx + ('；電纜表上在 %s' % jr if jr else '')
            else:
                jb_txt = nm + ('（汽機房儀器與 JB 位置圖上沒有這個接線箱' if r.get('unit', 'S10') == 'S10' else '（GE 燃機外形圖的 JB 表上沒有這個箱子') + \
                    ('；電纜表上在 %s）' % jr if jr else '）')
        s_rows.append(['電氣盤' if pan_jb else '接線箱', jb_txt, 'doc', wsrc])
        inside = ('前置器 %s 的端子 %s' % (w['prox'], ge_wire_join(c['jb'].replace(w['prox'], '').strip() for c in cond)) if r['mode'] == 'coax' and w['prox']
                  else '端子 %s%s' % ((w['jb_tb'] + ' ') if w['jb_tb'] and not own_tb else '', ge_wire_join(ge_wire_jbt(c['jb']) for c in cond)))
        if own_tb and w['jb_tb'] and not all(any(ge_wire_jbt(c['jb']).startswith(h_.lstrip('-')) for h_ in w['jb_tb'].split('/') if h_.strip('-'))
                                             for c in cond if c['jb']):   # 表頭 '-TBTCD/TBBUSP/TBBAK' 列了幾排：格子的排在其中就不加這句
            inside += '（接線圖表頭寫 %s，格子自己寫的端子排不同，照格子）' % w['jb_tb']
        s_rows.append(['盤內端子' if pan_jb else '接線箱內端子', inside, 'doc', wsrc])
        s_rows.append(['幹線', '%s（%s），芯 %s' % (w['trunk'], w['trunk_spec'], ge_wire_join(c['core'] for c in live)), 'doc', wsrc])
    jls = ''   # 迴路圖（v15）的接線箱位置短句（FF 的段保護器也要）
    if r['mode'] != 'direct':
        jl, gj, jd = r.get('jbloc'), r.get('gtjb'), r.get('jbdoc')
        sj = next((s for k, s in r['hops'] if k == 'jbloc'), None)
        sd = next((s for k, s in r['hops'] if k == 'jbdoc'), None)
        if jl and sj:
            jls = '汽機 JB 位置圖 %s p.%s：%s' % (sheets[sj].get('doc') or '', sheets[sj]['page'], jl['coords'])
        elif gj:
            jls = 'GE 137T6223 %s%s' % (gj['name'], ('：' + gj['coords']) if gj.get('coords') else '（等角圖標籤，沒有座標）')
        elif jd and sd:
            jls = '%s %s p.%s（設備上的位置，沒有廠區座標）' % (jd['zh'], sheets[sd].get('doc') or jd['doc'], sheets[sd]['page'])
        else:
            jr = ge_wire_jb_room(r, w)
            pan = not re.match(r'\s*JB', w['jb']) and GE_WIRE_PANEL_RE.search(w['jb'] + ' ' + (w['jb_desc'] or ''))
            cub = GE_WIRE_MCC_RE.search(w['jb']) or re.search(r'_([A-Z]+\d+[A-Z]?(?:-\d+)?)\b', w['jb'])
            smc = next((s for k, s in r['hops'] if k == 'mcc'), None)
            ej = next((x for x in r.get('ep') or [] if x['end'] == 'jb'), None)
            jls = (('電氣盤（不是接線箱）' + ('第 %s 格' % cub.group(1) if cub else '') + ('；盤面配置圖 p.%s 有框' % sheets[smc]['page'] if smc else '')
                    + (('；%s p.%s 框出%s%s' % (ej['doc'], '、'.join(str(x) for x in ej['pages']), '隔間' if ej.get('lv') == 'cmp' else '端子',
                                                '（本台沒有向量圖，類比 %s 的圖）' % ej['analog'] if ej.get('analog') else '')) if ej and not smc else ''))
                   if pan else '沒有位置圖') + ('；電纜表房間 %s' % jr if jr else '')
    rm = r.get('room')
    if rm:
        s_cs = next((s for k, s in r['hops'] if k == 'cs'), None)
        ends = [x for x in (('%s（%s）' % (rm.get('r2d') or '—', rm['r2']) if rm.get('r2') else rm.get('r2d')),
                            ('%s（%s）' % (rm.get('r1d') or '—', rm['r1']) if rm.get('r1') else rm.get('r1d'))) if x]
        e1, e2 = re.search(r'E-\s*\d+', room or ''), re.search(r'E-\s*\d+', ge_wire_rooms(r, w)[1])
        rcav = ('；接線圖盤欄寫 %s、電纜表這一列盤那一端寫 %s，請以現場門牌為準' % (e1.group(0), e2.group(0))
                if e1 and e2 and re.sub(r'\s', '', e1.group(0)) != re.sub(r'\s', '', e2.group(0)) else '')
        s_rows.append(['電纜與房間', '電纜表的 %s%s：%s%s' % (rm['cable'], ('（%s%s）' % (rm.get('type') or '', ('，%s m' % rm['len']) if rm.get('len') else '')) if rm.get('type') or rm.get('len') else '',
                                                      ' ↔ '.join(ends) or '—', rcav), 'doc',
                       'PDF 文字層 · %s 第 %s 頁' % ((sheets.get(s_cs) or {}).get('rel', '').rpartition('/')[2], (sheets.get(s_cs) or {}).get('page', '?'))])
    pos = ge_wire_join(c['pos'] for c in live)
    board = ge_wire_join(c['board'] for c in live)
    m = re.match(r'^(CA\d{3})-(\w+)$', pos)
    face = {'LEFT SIDE PANEL': '左側板', 'RIGHT SIDE PANEL': '右側板'}.get((r.get('cab') or {}).get('side', ''), '背板')
    where = ('%s %s %s %s' % (m.group(1), face, m.group(2), board)) if m else board
    ep_ = next((x for x in r.get('ep') or [] if x['end'] == 'panel'), None)   # v16：盤那一端也是電氣盤（UAT → GPP-AUX）
    po = bool(ep_) or (not any(c['board'] in GE_WIRE_MV for c in live) and bool(GE_WIRE_PANEL_RE.search(w['panel'] + ' ' + w['panel_desc']))
                       and not re.search(r'\bCC[A-Z]\d\dUC2\d\d|\bTCP\b', w['panel'] + ' ' + w['panel_desc'])) \
        or (not any(c['board'] in GE_WIRE_MV for c in live) and bool(re.search(r'CABINET|\bMKA10UC', w['panel'] + ' ' + w['panel_desc'])))   # 終點不是控制盤 TCP（電氣盤、GHM 櫃、VMS 盤）
    bds = list(dict.fromkeys(c['board'] for c in live if c['board']))
    terms = ('、'.join('%s 端子 %s' % (b_, ge_wire_join(c['num'] for c in live if c['board'] == b_)) for b_ in bds) if len(bds) > 1 and not m
             else '%s 端子 %s' % (where, ge_wire_join(c['num'] for c in live)))
    s_rows.append(['終點盤' if po else '電子室盤', '%s%s%s：%s%s' % (pk[0] + ' ' if pk else '', pname, ('（%s）' % room) if room else '', terms,
                                                         ('；' + ge_wire_ep_txt(ep_)) if ep_ else ''), 'doc', wsrc])
    io = r.get('io') or []
    ff = r.get('ff') or {}
    if r['mode'] == 'ff' and ff.get('seg'):
        if ff.get('vars'):
            s_rows.append(['Mark VIe', '控制器組態 FF_IN_S%s 段裡有這顆的變數：%s' % (ff['s'], '、'.join(ff['vars'])), 'ctrl', 'signal-atlas 控制器索引（變數宣告的 FF 段）'])
        elif ff.get('dev_vars'):
            s_rows.append(['Mark VIe', '控制器組態 FF_IN_S%s 段裡有中間傳送器 %s 的變數（%s）；這顆元件自己的變數名沒有讀到' % (ff['s'], ff.get('dev') or '?', '、'.join(ff['dev_vars'])),
                           'ctrl', 'signal-atlas 控制器索引（變數宣告的 FF 段）'])
        elif ff.get('other_s'):
            s_rows.append(['Mark VIe', '接線圖的段＝FF_IN_S%s，控制器組態裡這顆的變數在 FF_IN_S%s（見註記）' % (ff['s'], '、S'.join(str(x) for x in ff['other_s'])), 'ctrl',
                           'signal-atlas 控制器索引（變數宣告的 FF 段）'])
        else:
            s_rows.append(['Mark VIe', '接線圖的段＝FF_IN_S%s；控制器索引裡沒有找到這顆的 FF 變數（FF 元件沒有端子螺絲可核）' % ff.get('s', '?'), 'inferred', 'signal-atlas 控制器索引'])
    elif io:
        pins = ge_wire_join('%s＝%s' % (c['num'], c['pin']) for c in live if c.get('pin'))
        txt = '；'.join('%s %s（%s %s）%s → %s%s' % (x[0], x[1], x[3], x[2], x[4], x[5] or '（沒有變數）', '（同位置的電源點 %s）' % x[6] if x[7] == 'loc' else '')
                       for x in io)
        s_rows.append(['Mark VIe', txt + ('；端子 %s' % pins if pins else ''), 'ctrl', 'signal-atlas 控制器索引（ToolboxST I/O 組態，螺絲號）'])
    elif any(c['board'] == 'SPID' for c in live):
        s_rows.append(['Mark VIe', '盤端子落在 SPID（CANopen 通訊板）：組態裡這類板沒有螺絲點，訊號是 CANopen 輸入／輸出變數，沒有逐螺絲核對', 'inferred', 'signal-atlas 控制器索引'])
    elif any(c['board'] in GE_WIRE_MV for c in live):
        s_rows.append(['Mark VIe', '盤端子落在 Mark VIe 端子板，但控制器索引沒有對到這些螺絲', 'inferred', 'signal-atlas 控制器索引'])
    elif any(c['board'] == '1TBVIB' for c in live):
        s_rows.append(['Mark VIe', '不進 Mark VIe：接到 Bently 3500 監測盤（VMS 盤）', 'doc', wsrc])
    elif r['mode'] == 'ff':
        s_rows.append(['Mark VIe', 'FF 段幹線：接到 %s 的 FFPC 端子（%s；FFPC 推定是該段的電源調節端子【推論】，圖面沒有定義）；段上各元件的控制器 FF 變數在各元件的卡上（FF 沒有螺絲可核）'
                       % (pname or (pk[0] if pk else '') or w['panel'] or '盤', ge_wire_join(' '.join(x for x in (c['pos'], c['board'], c.get('tb', '')) if x) for c in live) or '—'),
                       'inferred', wsrc])
    else:
        s_rows.append(['Mark VIe', '不進 Mark VIe：終點是 %s，沒有控制器螺絲可核' % (pname or (pk[0] if pk else '') or w['panel'] or '別的盤'), 'doc', wsrc])
    rk = r.get('rack')
    sb_ = next((s for k, s in r['hops'] if k == 'bnw'), None)
    if rk:
        sr = next((s for k, s in r['hops'] if k == 'rack'), None)
        if rk.get('by') == 'bx':   # 燃機（v16）：GT-VMP Rev D 盤圖接線表的 RDS-PP 欄（＝Mark VIe 通道順序）
            s_rows.append(['Bently 3500', 'RACK %s SLOT %s CH%s（燃機 3500 盤 GT-VMP Rev D 接線表的 RDS-PP 欄；G11 是 RACK 1、G12 是 RACK 2）' % (rk['rack'] or '?', rk['slot'] or '?', rk['ch'] or '?'),
                           'doc', ge_wire_bsrc(sheets[sb_]) if sb_ else ('燃機 3500 盤 EOMR HT1-1-AQB01-Q1850（GE 120V8110 Rev D）PDF p.54～55（RACK 2 接線）、p.42（RACK 2 槽位表）'
                                                                          if r.get('unit') == 'G12' else '燃機 3500 盤 EOMR HT1-1-AQB01-Q1850（GE 120V8110 Rev D）PDF p.41（RACK 1 槽位表）')])
        else:
            s_rows.append(['Bently 3500', 'RACK %s SLOT %s CH%s（3500 盤圖的槽位表）' % (rk['rack'] or '?', rk['slot'] or '?', rk['ch'] or '?'), 'doc',
                           ge_wire_bsrc(sheets[sr]) if sr else '3500 盤圖'])
    bx = r.get('bx') or {}
    if bx.get('lab'):   # v16：3500 怎麼收到這個訊號（並聯分支）；接頭第 n 通道＝ETB／3500 第 n 通道是推論（ET 電纜腳位沒有圖）
        alt = bx.get('alt') or {}
        lg = ('；另一種讀法：Bently 盤圖的 Legacy Tag 欄把它寫在 SLOT %s CH%s——若 3500 組態照 Legacy 欄命名，3500 畫面上這個名稱會是別支探頭' % (alt.get('slot', '?'), alt.get('ch', '?'))
              if bx.get('aw') == 'legacy' else '')
        s_rows.append(['3500 分支', bx['lab'] + lg + ('【%s】' % bx['g'] if bx.get('g') else ''), 'inferred' if '推論' in (bx.get('g') or '') else 'doc',
                       ge_wire_bsrc(sheets[sb_]) if sb_ else ('；'.join(bx.get('cite') or []) or 'Bently 3500 盤圖（GE 120V8111／CB01-BNX-120014477）')])
    md = r.get('mid') or {}
    if md.get('chain'):   # v16：現場元件與接線箱端子之間的中間設備
        txt = '；'.join('%s%s：%s%s%s【%s】' % (c.get('n', ''), ('（%s）' % c['s']) if c.get('s') else '', c.get('i', ''), ' → ' if c.get('i') and c.get('o') else '', c.get('o', ''), c.get('g', ''))
                       for c in md['chain'])
        at_ = (0 if all(c.get('at') == 'pre' for c in md['chain'])
               else next((i_ + 1 for i_ in range(len(s_rows) - 1, -1, -1) if s_rows[i_][0].startswith('現場')), 0))   # 照訊號路徑排：上游元件在最前、其餘接在「現場 → …」之後
        s_rows.insert(at_, ['中間設備', txt + (('；沒有圖的部分：%s' % md['gap']) if md.get('gap') else ''),
                                        'inferred' if any('推論' in (c.get('g') or '') and '定讞' not in (c.get('g') or '') for c in md['chain']) else 'doc',
                                        '；'.join(dict.fromkeys(c.get('src', '') for c in md['chain'] if c.get('src')))])
    sgs = (r.get('sig') or [])[:4]
    for x in sgs:   # v16：訊號型式與迴路供電（照接線判；組態寫法不一致的另列註記；規則附註接在後面）
        s_rows.append(['訊號與供電' + (('（%s）' % x[0]) if len(sgs) > 1 and x[0] else ''),
                       '%s：%s；%s【%s】%s' % (x[0] or 'FF 段', x[1], x[2], x[3], ''.join('；' + y for y in (x[7] if len(x) > 7 else []) or [])),
                       {'組態': 'ctrl', '文字層': 'doc'}.get(x[3], 'inferred'),
                       ('、'.join(x[6]) if len(x) > 6 and x[6] else 'Mark VIe 端子板手冊') + '；signal-atlas 控制器索引（I/O 組態）'])
    t = []
    for c in cond:
        fl = c['field'] + (('（%s）' % c['field_core']) if c['field_core'] else '')
        pt = ' '.join(x for x in (c['pos'], c['board'], c.get('tb', ''), c['num']) if x) or (
            ('（盤側沒畫端子；這一頁盤欄底部印「IS → %s 排、OS → %s 排接地」）' % (r['shield']['IS'], r['shield']['OS']) if r.get('shield') else '（盤側不落端子）')
            if c['core'].startswith('SH') else '（沒有讀到）')
        t.append([c['core'], fl, ge_wire_jbt(c['jb']), pt, c.get('pin') or '', c.get('io') or '', c['num'], c.get('pt') or ''])
    rows = []
    for gi, (kind, s) in enumerate(r['hops']):
        sh = sheets[s]
        hs = [h for h in hits if h['sheet'] == s and h.get('hop') == kind]
        marks = [[round(h['x'] + h['w'] / 2.0, 5), round(h['y'] + h['h'] / 2.0, 5), round(h['w'], 5), round(h['h'], 5)] for h in hs]
        lab = (hs[0].get('label') if hs else '') or ''
        src = 'PDF 文字層 · %s 第 %s 頁' % (sh['rel'].rpartition('/')[2], sh['page'])
        base = {'s': s, 'g': gi}
        first = dict(base, d=pm['_dkey'][s], p=sh['page'], img=True, marks=marks, drawn=lab, unit='', rel=GE_WIRE_REL[kind], how='text', via='ge', hop=kind)
        if isinstance(sh.get('pages'), int):
            first['n'] = sh['pages']
        if kind == 'wire':
            pos_t = '① 接線箱端子（%s）、② 盤端子（%s）、③ 元件框' % (ge_wire_join(c['jb'] for c in cond), ge_wire_join(' '.join(x for x in (c['board'], c['num']) if x) for c in live)) \
                if r['mode'] != 'direct' else '① 現場端子、② 盤端子、③ 元件框'
            how = 'PDF 文字層；接線圖由試算表範本產生、欄位固定，芯色標籤配端子格保持上下順序，盤側以芯色標籤對接（不照列對齊）' if r.get('doc', 'wire') == 'wire' \
                else 'PDF 文字層＋向量框線（欄位由框線定位；每條芯以接線短線定位），盤側以芯色標籤序列對接'
        elif kind == 'jbloc':
            pos_t = '① 接線箱符號、② 標籤（KKS 與座標）' if len(marks) > 1 else '① 標籤（KKS 與座標；圖上的符號在引線另一端）'
            how = 'PDF 文字層找到標籤，再沿藍色引線找到紅色接線箱符號'
        elif kind == 'gtjb':
            pos_t = '① 等角圖上的 %s 標籤（引線指向箱子）' % lab
            how = 'PDF 文字層（GE 137T6223 O/L MECHANICAL GT & GENERATOR；各台燃機共用一份）'
        elif kind == 'gtjbt':
            pos_t = '① JB 表上 %s 那一列（X／Y／Z 燃機座標，in [mm]）' % lab
            how = 'PDF 文字層'
        elif kind == 'mcc':
            mc = r.get('mcc') or {}
            if mc.get('np'):
                pos_t = '① %s 正視圖上 NP 區的第 %s 格（推算）、② 左上 NP 表上 %s 那一列' % (mc.get('lineup', ''), mc.get('cub', '')[-1:], mc.get('cub', ''))
                how = ('PDF 文字層＋向量框線：NP 區頂上的 NP%s-1 是文字，小格的銘牌是線條字（不在文字層），照區內從左緣拉到右緣的隔板由上往下數第 %s 格（推算）；'
                       'NP 表那一列是文字層；GE EP24 盤面配置圖各機組一份（檔名沒有文件號，照檔名找最高版次）' % (mc.get('cub', '')[2:3], mc.get('cub', '')[-1:]))
            else:
                pos_t = '① %s 正視圖上 %s 這一格（格位標籤寫在格子左下角）' % (mc.get('lineup', ''), mc.get('cub', ''))
                how = ('PDF 文字層找到格位標籤，再用向量框線定出這一格（MCC 框門板範圍，右邊的配線槽不算）；GE EP24 盤面配置圖各機組一份'
                       '（檔名沒有文件號，照檔名找最高版次）；格內寫的 KKS 與這個元件比對（不判定誰對）')
        elif kind == 'jbdoc':
            pos_t = '① 圖上的箱名或 KKS 標籤 %s（同一頁出現幾次就框幾個，最多 4 個）' % lab
            how = 'PDF 文字層：先找接線箱的 KKS 寫法，沒有才找箱名（短號在別張圖可能是另一個箱子）；這張圖沒有廠區座標'
        elif kind == 'conn':
            pos_t = '① GE 接線表上這顆元件的每一芯（一芯一列）'
            how = 'PDF 文字層（表格欄位由表頭下緣的格線定位）；以接線箱／端子排／端子號接上接線圖'
        elif kind == 'cs':
            pos_t = '① 電纜表上 %s 那一列（兩端的房間、設備、型式、長度）' % lab
            how = 'PDF 文字層'
        elif kind == 'cab':
            pos_t = '① 板位 %s 的約略範圍' % pos
            how = '板名是圖上的線條字（不在文字層）：框由背板的欄、列標籤推算，是約略範圍'
        elif kind == 'vms':
            pos_t = '① 1TBVIB 現場訊號端子（DIN 軌）的標註'
            how = 'PDF 文字層'
        elif kind == 'epnl':
            e_ = next((x for x in r.get('ep') or [] if sh['page'] in (x.get('pages') or [])), None) or {}
            pos_t = '① %s%s（%s那一端）' % ('隔間 ' if e_.get('lv') == 'cmp' else '端子排與端子表那一列 ', lab, '接線箱' if e_.get('end') == 'jb' else '盤')
            how = 'PDF 文字層＋向量框線：%s；%s%s' % (e_.get('how', ''), e_.get('doc', ''), ('；' + e_['dn']) if e_.get('dn') else '')
            if e_.get('rel'):
                first['rel'] = e_['rel']
        elif kind == 'bnw':
            pos_t = '① 3500 接線表上這一條的列與機架槽位標題（Mark VIe TVBA 緩衝輸出 → ET 排線 → 3500 模組）'
            how = ('PDF 文字層（Bently 盤圖的「To Mark VIe」接線表；燃機是 GT-VMP 製造完成報告裡的 Rev D 盤圖，只框 G11 的 RACK 1 那幾頁）；'
                   '接頭內第 n 通道＝3500 CHn 是推論（ET 排線的腳位沒有圖）')
        else:
            pos_t = '① 槽位表上這顆元件 KKS 那一格'
            how = 'PDF 文字層（槽＝同一欄的 SLOT 表頭、通道＝同一列的 CH）'
        if kind in ('bnw', 'rack'):
            src = ge_wire_bsrc(sh)
        ep_h = (next((x for x in r.get('ep') or [] if sh['page'] in (x.get('pages') or [])), None) or {}) if kind == 'epnl' else {}
        hop_n = '電氣盤配置圖（只到隔間）' if ep_h.get('lv') == 'cmp' else GE_WIRE_HOP[kind]
        rows.append([hop_n, pid_sheet_name(sh), 'inferred' if ep_h.get('analog') else 'doc', src, first])   # 框在別台的圖上（類比）＝推論
        rows.append(['圖面頁次', 'PDF 第 %s 頁%s' % (sh['page'], ('（共 %s 頁）' % sh['pages']) if isinstance(sh.get('pages'), int) else ''), 'doc', src, dict(base)])
        rows.append(['所在位置', pos_t, 'doc', src, dict(base)])
        rows.append(['圖上標示', lab, 'doc', src, dict(base)])
        rows.append(['對應方式', how, 'doc', src, dict(base)])
    dl = ge_wire_loop(r, w, pk[0] if pk else '', pname, room, where, jls)
    if lno:
        dl['no'] = lno
    if po:
        dl['po'] = 1                       # 迴路圖第四欄：對方電氣盤（不是電子室控制盤）
    if pan_jb:
        dl['jr'] = recv or 'contact'       # 迴路圖第二欄：受控端（接點在另一端）或接點在盤內
    if sw.get('doc'):
        dl['wd'] = sw['doc'] + (' Rev.%s' % sw['rev'] if sw.get('rev') else '')
    out = {'mode': r['mode'], 'sum': s_rows, 't': t, 'rows': rows, 'u': r.get('unit', 'S10'), 'd': dl}
    if fld:
        out['f'] = fld
    if r.get('notes'):
        out['n'] = r['notes']
    jbs = pm.get('_wg_jbs') or {}
    jb = (jbs.get('%s|%s' % (r.get('unit', 'S10'), w['jb'])) or jbs.get(w['jb'])) if w['jb'] else None
    if jb and jb.get('strip'):
        out['jb'] = [w['jb'], [x[:4] + [1 if (len(x) > 7 and x[7]) or (len(x) <= 7) else 0] for x in jb['strip']]]
    return out


def ge_wire_cards(pm, key, units):
    """這個編號在本站機組（units）的每一條接線路徑 → [卡片資料…]（wire_ge.json v2 的 paths[key] 是清單；v1 是單一條）。"""
    plist = (pm.get('_wg_paths') or {}).get(key) or []
    if isinstance(plist, dict):
        plist = [plist]
    sel = [(pi, r) for pi, r in enumerate(plist) if not units or r.get('unit', 'S10') in units]
    per, seen, out = {}, {}, []
    for _pi, r in sel:
        per[r.get('unit', 'S10')] = per.get(r.get('unit', 'S10'), 0) + 1
    for pi, r in sel:   # 迴路圖編號（v16）：LP-機組-GE 編號（照寫，不改標點：'52ET/CLOSED' 與 '52ET_CLOSED' 是對照表上兩筆）；同一台有好幾條才加 -P 序號
        u = r.get('unit', 'S10')
        seen[u] = seen.get(u, 0) + 1
        lno = 'LP-%s-%s%s' % (u, key.split('|', 1)[-1], ('-P%d' % seen[u]) if per[u] > 1 else '')
        c = ge_wire_card(pm, key, r, pi, len(plist) > 1, lno)
        if per[u] > 1:
            c['d']['nn'] = per[u]          # 這一台這個編號共幾條（標題欄「-P2（共 4 條）」）
        out.append(c)
    return out


GE_CTRL_UNIT = {'G11': 'G11', 'G11S': 'G11', 'G12': 'G12', 'G12S': 'G12', 'S1': 'S10', 'S1S': 'S10'}


def ge_wire_xref(pm, e, key, units):
    """沒有路徑、但 Mark VIe 訊號接在實體螺絲上的編號：接線圖上那組螺絲畫在哪個編號的路徑底下（v14）→
    [[機組, 控制器.變數, 板位 板名 點名, 那個 GE 編號, 接線圖頁]…]（每台機組最多 4 筆）。
    來源是各路徑核對螺絲時記下的組態點（paths[k].io：[控制器, 模組, 板位, 板名, 點, 變數, DeviceTag, 關係]），不另查索引；
    常見的是同一台設備的另一組接點（'23HG-1/2 /AVAIL' → 23HG-1）、別名（MIC-2996 → ME-2996）、或圖面與組態不一致——只指出位置，不判定是不是同一顆。"""
    rev = pm.get('_wg_rev')
    if rev is None:
        rev = pm['_wg_rev'] = {}
        for k, pl in (pm.get('_wg_paths') or {}).items():
            for pi, r in enumerate(pl if isinstance(pl, list) else [pl]):
                for x in r.get('io') or []:
                    if len(x) >= 6 and x[5]:
                        rev.setdefault((x[0], str(x[5]).lower()), []).append((k, pi, r))
    out, seen = [], set()
    for lg in e.get('logic') or []:
        ct, _d, var = str(lg).partition('.')
        un = GE_CTRL_UNIT.get(ct, '')
        if not var or (units and un not in units):
            continue
        for k, pi, r in rev.get((ct, var.lower()), ()):
            if k == key:
                continue
            for x in r.get('io') or []:
                if x[0] == ct and str(x[5]).lower() == var.lower():
                    pg = (r.get('wire') or {}).get('page')
                    sig = (un, k, pg, x[2], x[3], x[4])
                    if sig not in seen:
                        seen.add(sig)
                        out.append([un, '%s.%s' % (ct, x[5]), ' '.join(v for v in (x[2], x[3], x[4]) if v), k.split('|', 1)[-1], pg])
    out.sort(key=lambda v: (v[0], v[4] or 0, v[3]))
    keep, per = [], {}
    for v in out:                                        # 每台機組最多 4 筆（卡上只列本台）
        per[v[0]] = per.get(v[0], 0) + 1
        if per[v[0]] <= 4:
            keep.append(v)
    return keep


GE_LD_NO_RE = re.compile(r'(?:HT\d-\d-)?([A-Z]{3}\d\d-[A-Z]\d{4})|(?<![0-9A-Z])(\d{3}T\d{4})(?![0-9])')


def ge_ld_listed(e):
    """條目的 GE 清單「位置圖」欄（spec 各塊的 location）列的文件號（去 HT 前綴：'GZD01-M0166'；GE 圖號 307T1798 原樣），照出現順序、不重複。"""
    out = []
    for b in e.get('spec') or []:
        for k, v in b.get('f') or []:
            if k == 'location':
                for m in GE_LD_NO_RE.finditer(str(v or '').upper()):
                    no = m.group(1) or m.group(2)
                    if no not in out:
                        out.append(no)
    return out


GE_CHAIN_BLOCK = {'MOVE': '搬移方塊 MOVE', 'MOVE_STATUS': '搬移方塊 MOVE_STATUS', 'AI': '類比輸入方塊 AI', 'AI_INT': '類比輸入方塊 AI_INT'}


def ge_chain_text(chain):
    """hmi_ge 的轉手鏈 [[方塊型別, 方塊路徑, 進, 出], …] → 'a_71gs1b →搬移方塊 MOVE_STATUS（HardwireInputs/HW_IN_GFC/MOVE_4）→ F71SCR3DR'。"""
    if not chain:
        return ''
    return chain[0][2] + ''.join(' →%s（%s）→ %s' % (GE_CHAIN_BLOCK.get(bt, bt), path, out) for bt, path, _i, out in chain)


def ge_hmi_how(ents):
    """GE 卡圖控「對應方式」：這一組（畫面, 機組）裡各處是怎麼對到的（I/O 訊號／畫面文字／姊妹機同名訊號），同樣的只講一次。"""
    bits = []
    for e in sorted(ents, key=lambda x: (x['match'] != 'io', x.get('via') == 'sibling', x.get('ctrl') or '', x.get('var') or '')):
        if e['match'] == 'label' and e.get('via') == 'caption':
            b = ('物件的設計標題寫著「%s」（數值格、警報燈、棒圖的標題不一定畫在畫面上；物件引用的訊號沒有對到別的編號）'
                 % (e.get('var') or '').strip())
        elif e['match'] == 'label':
            b = '畫面上寫著「%s」（文字標示）' % (e.get('var') or '').strip()
        elif e.get('via') == 'host':
            b = ('物件引用的是主設備的訊號 %s.%s：這個編號是它的附屬件（極限開關、電磁閥、加熱器之類），畫面上沒有自己的物件，'
                 '位置是主設備的（對照表的訊號由 KKS 本體繼承而來）' % (e.get('ctrl'), e.get('var')))
        elif e.get('via') == 'derived':
            b = '物件引用 %s.%s：這支熱電偶經 AI 與排氣溫度補償巨集逐通道轉手後的值（與這個編號一對一）' % (e.get('ctrl'), e.get('var'))
        elif e.get('via') == 'chain':
            b = ('物件引用 %s.%s：這是本編號的 I/O 訊號經一對一的搬移／類比輸入方塊轉手後的變數（%s；signal-atlas 控制器索引）'
                 % (e.get('ctrl'), e.get('var'), ge_chain_text(e.get('chain'))))
            if e.get('sib'):
                b += '；起點是 G12 的同名訊號（對照表只列 G11，比照 G11 推論）'
            if e.get('cap'):
                b += '；物件屬性裡的標題寫「%s」（與本編號的寫法不同：可能是 GE 範本的槽位編號，或複製物件留下的標題；以訊號為準）' % e['cap']
        elif e.get('via') == 'sibling':
            b = ('物件引用 %s.%s：對照表只列 G11 的訊號，signal-atlas 確認 %s 有同名變數，推論是本台的同一顆（與 GE 卡「Mark VIe 訊號」同一個規則）'
                 % (e.get('ctrl'), e.get('var'), e.get('ctrl')))
        else:
            b = '物件引用這個編號的 Mark VIe I/O 訊號 %s.%s' % (e.get('ctrl'), e.get('var'))
        if b not in bits:
            bits.append(b)
    ref = next((e.get('ref') for e in ents if e['match'] == 'io' and e.get('ref')), None)
    return '；'.join(bits) + (('（%s）' % ref) if ref else '')


def ge_hmi_rows(hm, hits, scope):
    """一個 GE 條目的圖控列（與 hmi_rows 同格式：每個（畫面, 機組）一組 4 列）→ (rows, more, related, same)。
    只收 io／label（設備的位置）；related（只引用說明提到這個編號的別的訊號）不當位置，條目沒有任何位置時才列成 related＝[[機組, 畫面名, 訊號]]。
    排序：機組 → 製程畫面在 SIL 畫面之前 → 畫面名；每部機最多 GE_HMI_MAX 張，其餘的畫面名放 more＝[[機組, [畫面名…]]]。
    第一列 extra：unit＝開這張畫面的選單列 Unit 欄（hmiPick 用它挑 G11／G12 的執行時截圖），gu＝這個編號所屬的機組，ctrl＝物件引用的控制器。"""
    loc = [h for h in hits if h.get('match') in ('io', 'label')]
    groups = {}
    for h in loc:
        groups.setdefault((h['unit'], h['screen'], h.get('nav_unit') or ''), []).append(h)
    order = sorted(groups, key=lambda k: (k[0], 1 if GE_HMI_SIL.search(k[1]) else 0, k[1].lower(), k[2]))
    # 同一部機、同一張畫面從兩個選單列都進得去（S10 的訊號畫在 HRSG11／HRSG12 兩頁同一張畫面）且標記相同：只留第一列
    # SIL 各頁共用「最終元件」面板（VS4-4 一部機 16 張、95SG-1 15 張，標記座標逐字相同）：只留一張代表（有 SIL_Overview 就用它），
    # 其餘畫面名放 same＝[[機組, 代表畫面名, [其他畫面名…]]]，不佔 GE_HMI_MAX 的名額（反方驗證 2026-10-25 的建議）
    sig = lambda k: tuple(tuple(round(v, 3) for v in m) for m in hmi_marks(groups[k]))   # noqa: E731
    seen, keep, same = set(), [], {}
    for k in order:
        if (k[0], k[1], sig(k)) in seen:
            continue
        seen.add((k[0], k[1], sig(k)))
        keep.append(k)
    sil = {}
    for k in keep:
        if GE_HMI_SIL.search(k[1]):
            sil.setdefault((k[0], sig(k)), []).append(k)
    drop = set()
    for (un, _s), ks in sorted(sil.items()):
        if len(ks) < 2:
            continue
        rep = next((k for k in ks if 'sil_overview' in k[1].lower()), ks[0])
        others = [k for k in ks if k != rep]
        drop.update(others)
        same.setdefault((un, rep[1]), []).extend(hmi_screen_name(hm, k[1])[2] or k[1] for k in others)
    order = [k for k in keep if k not in drop]
    rows, more, per = [], {}, {}
    gi = 0
    for k in order:
        un, key, nu = k
        name, _zh, en, _cap = hmi_screen_name(hm, key)
        if per.get(un, 0) >= GE_HMI_MAX:
            more.setdefault(un, []).append(en or name)
            continue
        per[un] = per.get(un, 0) + 1
        ents = groups[k]
        sc = hm['screens'].get(key) or {}
        nav, exact = hmi_nav_rows(hm, key, nu)
        marks = hmi_marks(ents)
        routes = sorted({e.get('route') or 'obj' for e in ents})
        img = bool(sc.get('img') or (hm['_shots'].get(key.lower()) or {}).get('file'))
        lvl = 'inferred' if all(e.get('via') in ('sibling', 'host', 'caption') or e.get('sib') for e in ents) else 'hmi'
        pre = src_prefix(lvl)
        src = '%s · 畫面檔 %s' % (pre, key)
        base = {'s': key, 'g': gi}
        ctrls = sorted({e.get('ctrl') for e in ents if e.get('ctrl')})
        first = dict(base, nav=nav, img=img, marks=marks, routes=routes, gu=un)
        if nu:
            first['unit'] = nu
        if ctrls:
            first['ctrl'] = '／'.join(ctrls)
        if all(e.get('via') == 'host' for e in ents):
            first['host'] = 1   # 位置是主設備的（附屬件沒有自己的畫面物件）：標頭寫明
        if not exact and len(nav) > 1:
            first['nav_all'] = 1
        rows.append(['圖控畫面', name, lvl, src, first])
        navtxt = '；'.join(' › '.join(x for x in r if x) for r in nav) or '（不在操作員導覽選單上）'
        rows.append(['導覽路徑', navtxt + (('　·　以選單機組 %s 開啟' % nu) if nu else ''), lvl,
                     '%s · 選單樹 CIMNavigationMenuItemsStd.csv%s' % (pre, '' if exact else '（此畫面全部選單列）'), dict(base)])
        pos = hmi_pos_text(marks).replace('這支位號', '這個編號')
        rows.append(['所在位置', pos or '（此對應方式沒有畫面座標）', lvl,
                     ('%s · 物件矩形（設計座標 %s×%s twips，y 軸向上，已換成左上原點 0~1 比例）'
                      % (pre, hm['stats'].get('design_w'), hm['stats'].get('design_h'))) if pos
                     else '%s · 此對應方式只知道「在這張畫面」，沒有座標' % pre, dict(base)])
        rows.append(['對應方式', ge_hmi_how(ents), lvl, '%s · 畫面物件的屬性包（device／ctrlr／caption…）與 GE 原廠編號對照表的 Mark VIe 訊號' % pre, dict(base)])
        gi += 1
    related = []
    if not rows:
        for h in sorted((h for h in hits if h.get('match') == 'related'), key=lambda h: (h['unit'], h['screen'], h.get('var') or '')):
            x = [h['unit'], hmi_screen_name(hm, h['screen'])[2] or h['screen'], '%s.%s' % (h.get('ctrl'), h.get('var'))]
            if x not in related:
                related.append(x)
    same_out = [[un, hmi_screen_name(hm, key)[2] or key, sorted(v)] for (un, key), v in sorted(same.items())]
    return rows, [[u, v] for u, v in sorted(more.items())], related[:12], same_out


def ge_loc_build(ge, pm, hm, old_card=None):
    """每個 GE 條目的位置列 → ({條目序號 _i: {'pd', 'hm', 'hmx', 'hr'}}, pid 用到的 {圖紙鍵: 條目數}, hmi 用到的 {畫面: {'rows', 'units'}})。
    pm／hm 是 None（--no-pid／--no-hmi 保留上次發布的）時，該類沿用上一份 getag.json（old_card）的列，影像也是上次發布的、原地留著。"""
    loc, pid_used, hmi_used = {}, {}, {}
    if ge is None:
        return loc, pid_used, hmi_used
    lg_docs = (pm or {}).get('_lg_docs') or {}
    old = {}
    if old_card:
        for x in old_card.get('entries') or []:
            old[(x.get('sc') or '', x.get('t'))] = x
    n_pd = 0
    for e in ge['entries']:
        key, scope = ge_loc_key(e), e.get('_scope') or ''
        o = {}
        if pm is not None:
            ents = (pm.get('_ge') or {}).get(key) or []
            if ents and scope:
                o['pd'] = ge_pid_rows(pm, ents, scope, e.get('kks') or ())
                n_pd += 1
                for r in o['pd']:
                    if len(r) > 4 and 'marks' in r[4]:
                        pid_used[r[4]['s']] = pid_used.get(r[4]['s'], 0) + 1
        elif (scope, e['tag']) in old and old[(scope, e['tag'])].get('pd'):
            o['pd'] = old[(scope, e['tag'])]['pd']
        # 位置圖（v12）：ld＝位置列；ldn＝GE 清單列的每一份位置圖的狀態 [[文件號, 狀態]]（GE_LD_STATE），有任何一份沒有位置才帶
        if pm is not None and pm.get('_lg') is not None:
            ents = pm['_lg'].get(key) or []
            if ents and scope:
                o['ld'] = ge_ld_rows(pm, ents, scope, e.get('kks') or ())
                for r in o['ld']:
                    if len(r) > 4 and 'marks' in r[4]:
                        pid_used[r[4]['s']] = pid_used.get(r[4]['s'], 0) + 1
            hit_docs = {(pm['sheets'][x['sheet']].get('doc') or '') for x in ents}
            shown = {(pm['sheets'][r[4]['s']].get('doc') or '') for r in o.get('ld') or [] if len(r) > 4 and 'marks' in r[4]}
            st = []
            for no in ge_ld_listed(e):
                info = lg_docs.get(no) or {}
                full = info.get('doc') or ''
                if not info.get('rel'):
                    st.append([no, 'nofile'])
                elif scope and info.get('scope') and info['scope'] != scope:
                    st.append([no, 'noscope'])
                elif full in shown:
                    st.append([no, 'hit'])
                elif full in hit_docs:
                    st.append([no, 'cap'])
                else:
                    st.append([no, 'miss'])
            if st and any(x[1] != 'hit' for x in st):
                o['ldn'] = st
        elif pm is None and (scope, e['tag']) in old:
            for k2 in ('ld', 'ldn'):
                if old[(scope, e['tag'])].get(k2):
                    o[k2] = old[(scope, e['tag'])][k2]
        # 接線路徑（v13 起；v14 全部 GE 編號）：wp＝第一條路徑 {u, mode, sum, t, f, rows, n, jb}（ge_wire_card）、wpx＝其餘路徑（兩台燃機、多組接點）；
        # 沒有路徑但有 Mark VIe 訊號的編號帶 wpn＝1（卡上說查過哪些圖、沒有讀到），其餘（閥本體、孔板…）不出這一塊
        if pm is not None and pm.get('_wg') is not None:
            cards = ge_wire_cards(pm, key, GE_SITE_UNITS.get(scope) or ()) if scope and key in (pm.get('_wg_paths') or {}) else []
            if cards:
                o['wp'] = cards[0]
                if len(cards) > 1:
                    o['wpx'] = cards[1:]
                for c in cards:
                    for r in c['rows']:
                        if len(r) > 4 and 'marks' in r[4]:
                            pid_used[r[4]['s']] = pid_used.get(r[4]['s'], 0) + 1
            elif scope and e.get('logic'):
                o['wpn'] = 1
                xr = ge_wire_xref(pm, e, key, GE_SITE_UNITS.get(scope) or ())
                if xr:
                    o['wpr'] = xr
        elif pm is None and (scope, e['tag']) in old:
            for k2 in ('wp', 'wpx', 'wpn', 'wpr'):
                if old[(scope, e['tag'])].get(k2):
                    o[k2] = old[(scope, e['tag'])][k2]
        if hm is not None:
            hits = (hm.get('_ge') or {}).get(key) or []
            if hits and scope:
                rows, more, rel, same = ge_hmi_rows(hm, hits, scope)
                for k2, v in (('hm', rows), ('hmx', more), ('hr', rel), ('hms', same)):
                    if v:
                        o[k2] = v
                for r in rows:
                    ex = r[4] if len(r) > 4 else None
                    if isinstance(ex, dict) and 'marks' in ex:
                        u = hmi_used.setdefault(ex['s'], {'rows': 0, 'units': set()})
                        u['rows'] += 1
                        if ex.get('unit'):
                            u['units'].add(ex['unit'])
        elif (scope, e['tag']) in old:
            for k2 in ('hm', 'hmx', 'hr', 'hms'):
                if old[(scope, e['tag'])].get(k2):
                    o[k2] = old[(scope, e['tag'])][k2]
        if o:
            loc[e['_i']] = o
    if pm is not None:
        pm['_ge_n'] = n_pd
    return loc, pid_used, hmi_used


# ------------------------------------------------------------------ DCS 基準比對
BASE_LABEL = {'dcdas': 'DCS 控制器組態 (AI Low/High Value)', 'terminal': 'DCS 端子表 (DEVICE_LO/HI)'}
CMP_STATUSES = ('ok', 'near', 'mismatch', 'unit_mismatch', 'unit_unknown', 'ref_only')  # near＝同單位數值不同但在容差內（請確認）；ref_only＝EOMR 序號不符（非本台），只列參考未比較


def ams_current(r):
    """13 表列 → (AMS 現值 {lo, hi, unit, …} 或 None, 單位未翻譯註記)。"""
    ams_cur = None
    if r is not None and num(r[14]) is not None and num(r[15]) is not None:
        ams_cur = {'lo': num(r[14]), 'hi': num(r[15]), 'unit': r[18] or '', 'lvl': 'decoded', 'kind': 'ams',
                   'src': '解碼 · AMS 現值 BlockData %s float32 · 最後記錄 %s' % (r[16] or '?', (r[36] or '')[:16])}
    ams_unit_note = ''
    if r is not None and not (r[18] or '').strip() and r[17] not in (None, ''):
        ams_unit_note = '（AMS 單位碼 %s／參數 %s 未翻譯）' % (g7(num(r[17])) if num(r[17]) is not None else r[17], r[19] or '?')
    if ams_cur is not None:
        ams_cur['unit_note'] = ams_unit_note
    return ams_cur, ams_unit_note


def dcs_write_base(dw, r, term_primary, ams_cur, ams_unit_note):
    """AMS 事件中 Cat28 外部主機寫入的 URV/LRV → DCS 寫入來源（沒有控制器資料、或寫入晚於該控制器 checkout 日期時當基準）；沒有回 None。"""
    if not ('URV' in dw or 'LRV' in dw):
        return None
    parts = []
    bounds = set()

    def bound(key, term_v, ams_v):
        side = '下限' if key == 'LRV' else '上限'
        if key in dw and num(dw[key][0]) is not None:
            w = dw[key]
            parts.append('%s %s→%s @%s %s·%s' % (w[5].split('.')[0], w[4], w[0], w[1][:16], w[2], w[3]))
            bounds.add('lo' if key == 'LRV' else 'hi')
            return num(w[0])
        # 這一端沒有 DCS 寫入：顯示端子表（或 AMS 現值）供參考，不列入比較
        if term_v is not None:
            parts.append('%s 未見 DCS 寫入（顯示 DCS 端子表值，僅供參考、不比較）' % side)
            return term_v
        if ams_v is not None:
            parts.append('%s 未見 DCS 寫入（顯示 AMS 現值，僅供參考、不比較）' % side)
            return ams_v
        parts.append('%s 未見 DCS 寫入' % side)
        return None
    lo = bound('LRV', term_primary and term_primary['lo'], ams_cur and ams_cur['lo'])
    hi = bound('URV', term_primary and term_primary['hi'], ams_cur and ams_cur['hi'])
    # DCS 寫入值是 AMS 參數值 → 單位用 AMS 單位（UNIT 寫入 > AMS 現值單位）；AMS 單位空白時留空，不借端子表單位
    unit = unit_of_code_str(dw['UNIT'][0]) if 'UNIT' in dw else ((r[18] if r is not None else '') or '')
    if not bounds:
        return None
    over = any(dw[k][6] for k in ('URV', 'LRV') if k in dw)
    notes = []
    if over:
        notes.append('之後曾被 AMS 人工改寫')
    if bounds != {'lo', 'hi'}:
        notes.append('%s無 DCS 寫入，顯示值僅供參考、不比較' % ('下限' if 'lo' not in bounds else '上限'))
    if not unit.strip():
        notes.append('單位空白' + ams_unit_note)
    return {'kind': 'dcs_write', 'lvl': 'decoded', 'lo': lo, 'hi': hi, 'unit': unit or '', 'bounds': bounds,
            'unit_note': '' if 'UNIT' in dw else ams_unit_note,
            'src': '解碼 · DCS 寫入 (AMS 事件 Cat28 Field change) · ' + '；'.join(parts),
            'label': 'DCS 寫入 (AMS 事件)', 'note': '；'.join(notes)}


CMP_NOTE_PREFIXES = ('換算為 ', '僅比較', '一致（', '≈ 近似', '⚠ 與 DCS', '上下限方向相反', '疑似絕壓', 'DCS 基準單位', '此來源', '單位不同（', '絕對壓／表壓')  # compare_range 的 note 段


def dcs_write_date(dw_base):
    """DCS 寫入來源字串裡最新的寫入日期（@YYYY-MM-DD）；沒有回 ''。"""
    return max(re.findall(r'@(\d{4}-\d{2}-\d{2})', dw_base.get('src') or ''), default='')


def build_compare(base, dc_primary, term_primary, ams_cur, il_primary, eo_primary, stats, eo_ref=None):
    """基準順序：控制器 I/O 組態 (dcdas) > DCS 寫入 (AMS 事件；只有寫入晚於該控制器 checkout 日期、或沒有控制器資料時) > DCS 端子表（設計文件）。
    eo_ref＝序號與 AMS 不符（非本台）的 EOMR 證書：只在 others 列一筆 status='ref_only'，不比較、不寫 cmp_mark。
    dc_primary['multi']（同位號其餘量程不同的控制器通道）：各自與基準比對後列成 others kind 'dcdas_ch'（label「控制器組態 · <ctrl> <通道>」），
    不寫 cmp_mark['dcdas']，改寫 cmp_mark['dcdas_multi']='warn'（前端黃色 pill「控制器多通道量程不一」）。
    回傳 (compare, cmp_mark)；不符／未比較時也在該來源 entry 的量程欄位（rows[i][2]）標狀態。"""
    dw = base if base is not None and base.get('kind') == 'dcs_write' else None
    if dc_primary and dw:
        # 統計：改用 checkout 日（而非索引建立日）判定後，基準是否因此不同
        wd = dcs_write_date(dw)
        if (wd <= (dc_primary.get('checkout_at') or dc_primary.get('built_at') or '')) != (wd <= (dc_primary.get('built_at') or '')):
            stats['baseline_changed_by_checkout'] = stats.get('baseline_changed_by_checkout', 0) + 1
    if dc_primary and (dw is None or dcs_write_date(dw) <= (dc_primary.get('checkout_at') or dc_primary.get('built_at') or '')):
        note = ('曾有 DCS 寫入事件（%s，見下列「DCS 寫入 (AMS 事件)」）；控制器 %s checkout %s（索引 %s）較新，以控制器為準'
                % (dcs_write_date(dw), dc_primary.get('ctrl') or '?', dc_primary.get('checkout_at') or '?', dc_primary.get('built_at'))) if dw else ''
        if dc_primary.get('multi_note'):
            note = '；'.join(x for x in (note, dc_primary['multi_note']) if x)
        base = dict(dc_primary, label=BASE_LABEL['dcdas'], note=note, bounds={'lo', 'hi'})
    elif base is None and term_primary:
        base = dict(term_primary, label=BASE_LABEL['terminal'], note='', bounds={'lo', 'hi'})
    compare, cmp_mark = [], {}
    if base is None:
        return compare, cmp_mark
    others = []
    cand = []
    if base['kind'] != 'dcdas' and dc_primary:
        cand.append(dict(dc_primary, label=BASE_LABEL['dcdas']))
    if base['kind'] != 'dcs_write' and dw:
        cand.append(dict(dw, label=dw['label'], pre_note=(dw.get('note') + '；') if dw.get('note') else ''))
    if base['kind'] != 'terminal' and term_primary:
        cand.append(dict(term_primary, label=BASE_LABEL['terminal']))
    if ams_cur:
        cand.append(dict(ams_cur, label='AMS 現值'))
    if il_primary:
        cand.append(dict(il_primary, label='儀器清單 設計量程'))
    if eo_primary:
        cand.append(dict(eo_primary, label='EOMR 出廠校正量程'))
    for ch in (dc_primary or {}).get('multi') or []:  # 同位號其餘量程不同的控制器通道：各列一列（kind dcdas_ch），不影響 cmp_mark['dcdas']
        cand.append(dict(ch, kind='dcdas_ch', label='控制器組態 · %s %s' % (ch['ctrl'], ch['conn'] or ch['pt']), pre_note='同位號另一通道；'))
    for c in cand:
        # DCS 寫入事件當一般來源時只比它寫入的那一端（另一端顯示值只是參考）
        cb = dict(base, bounds=set(base['bounds']) & set(c['bounds'])) if c['kind'] == 'dcs_write' and c.get('bounds') else base
        st, note, lo2, hi2 = compare_range(cb, c)
        o = {'kind': c['kind'], 'label': c['label'], 'lvl': c['lvl'], 'src': c['src'], 'lo': c['lo'], 'hi': c['hi'], 'unit': c['unit'],
             'status': st, 'note': (c.get('pre_note') or '') + note}
        if c['kind'] == 'dcs_write':
            o['bounds'] = sorted(c['bounds'])
        others.append(o)
        stats['compare_status'][st] = stats['compare_status'].get(st, 0) + 1
        if c['kind'] == 'ams' and base['kind'] == 'dcdas':  # 全廠統計：AMS 現值 vs 控制器組態（完全相同／近似／不符／未比較）
            k3 = st if st in ('ok', 'near', 'mismatch') else 'not_compared'
            stats['ams_vs_dcdas'][k3] = stats['ams_vs_dcdas'].get(k3, 0) + 1
        ent = c.get('ent')
        if c['kind'] == 'dcdas_ch':
            if ent is not None and st != 'ok':  # 該通道 entry 的量程欄位標黃（多通道量程不一，非故障判定）
                for row in ent['rows']:
                    if row[0] == DCDAS_FIELD:
                        row[2:] = ['warn']
            continue
        cmp_mark[c['kind']] = st
        # 逐端標記（LRV／URV 欄位旁的 ⚠／≈）：只標有列入比較的那一端，不符／近似只標實際不同的那一端
        bad_sides = note.rsplit('不符（', 1)[-1] if st == 'mismatch' else (note.rsplit('≈ 近似（', 1)[-1] if st == 'near' else '')
        for k, side in (('lo', '下限'), ('hi', '上限')):
            if k in cb['bounds']:
                cmp_mark['%s_%s' % (c['kind'], k)] = (st if side in bad_sides else 'ok') if st in ('mismatch', 'near') else st
        if ent is not None and st != 'ok':  # 在文件／控制器 entry 的量程欄位旁標 ⚠
            fld = c.get('field') or 'DCS 量程 (DEVICE_LO/HI/UNITS)'
            for row in ent['rows']:
                if row[0] == fld or (c['kind'] == 'terminal' and row[0].startswith('DCS 量程')):
                    row[2:] = [st]
    if (dc_primary or {}).get('multi'):
        cmp_mark['dcdas_multi'] = 'warn'
        stats['dcdas_multi'] += 1
    if eo_ref:  # 序號不符的證書：非本台，只列參考、不比較、不標 ⚠
        others.append({'kind': 'eomr', 'label': 'EOMR 出廠校正量程', 'lvl': eo_ref['lvl'], 'src': eo_ref['src'], 'lo': eo_ref['lo'], 'hi': eo_ref['hi'],
                       'unit': eo_ref['unit'], 'status': 'ref_only', 'note': '證書序號與 AMS 不符（非本台），僅供參考、未比較'})
        stats['compare_status']['ref_only'] = stats['compare_status'].get('ref_only', 0) + 1
    b = {k: base[k] for k in ('kind', 'label', 'lvl', 'src', 'lo', 'hi', 'unit', 'note')}
    b['bounds'] = sorted(base['bounds'])
    compare.append({'item': '量程', 'baseline': b, 'others': others})
    stats['with_compare'] += 1
    stats['baseline'][base['kind']] = stats['baseline'].get(base['kind'], 0) + 1
    return compare, cmp_mark


def strip_marks(sec):
    """文件／控制器 entry 中量程欄位的 cmp 標記：未比較者去掉 kind 字串，只保留狀態（--recompare 也用它清掉舊狀態）。"""
    for kk in ('dcdas', 'terminal', 'instlist', 'eomr'):
        for ent in (sec.get(kk) or {}).get('entries', []):
            for row in ent['rows']:
                if len(row) > 2 and row[2] not in CMP_STATUSES + ('warn',):
                    del row[2:]


def new_stats(aliases):
    return {'devices': len(aliases), 'with_compare': 0, 'compare_status': {}, 'baseline': {'dcs_write': 0, 'dcdas': 0, 'terminal': 0},
            'baseline_changed_by_checkout': 0, 'dcdas_multi': 0, 'ams_vs_dcdas': {}, 'sections': {}}


COMPARE_RULE = ('DCS 基準依序＝(1) 控制器現行 I/O 組態（signal-atlas 索引：該位號類比輸入通道的 Low/High Value）'
                '→ (2) AMS 事件中該參數最新一次值有改變的 Cat28 外部主機寫入（URV/LRV；只寫入一端時只比較該端，單位用 AMS 單位；'
                '只有寫入晚於該控制器 checkout 日期或沒有控制器資料時才當基準，否則列為一般來源）→ (3) DCS 端子表 DEVICE_LO/HI（設計文件）；'
                '同單位者數值完全相同才「一致」，差在 ±0.5% span 內標「≈ 近似（請確認）」；需換算單位者（°C↔°F、psi↔kPa…）換算後在 ±0.5% span 內即「一致」；'
                '量綱不同或明確絕壓↔表壓標「單位不同未比較」，任一邊單位空白/無法辨識/僅為推定標「單位不明未比較」；'
                'EOMR 證書序號與 AMS 不符者（非本台）只列參考（ref_only）不比較，AMS 未寫入序號者仍比對但註明無法確認為同一台；'
                '同位號多個控制器通道時基準取同機組控制器，各通道量程不一時其餘通道各列一列並標「控制器多通道量程不一」')


# ------------------------------------------------------------------ 文件 entry → 顯示
def fdict(e):
    return {k: v for k, v in e.get('fields', [])}


def doc_ref(e):
    if e.get('ref'):  # 產生器已給完整顯示字串（例：HT1-1-IMI01-A0001-H（推定）、HT3-1-IMI01-A0001（IO Rev3，版次字母不明））
        return e['ref']
    rev = e.get('rev')
    return '%s-%s' % (e['doc_id'], rev if rev not in (None, '') else '?')


def entry_lvl(e, default):
    lv = e.get('level') or default
    return lv if lv in SRC_DEFS else default


def src_prefix(lvl):
    return SRC_DEFS[lvl]['label']


def build_docs_map(kinds):
    """searched 中 used=true 的文件 → docs key（kind|doc_id|rev），前端展開來源時顯示資料夾／檔名／選版理由。"""
    docs = {}
    for kind, j in kinds.items():
        for s in j.get('searched', []):
            if not s.get('used'):
                continue
            key = '%s|%s|%s' % (kind, s.get('doc_id'), s.get('rev') or '')
            if key in docs:
                continue
            d = {'title': s.get('title', ''), 'folder': s.get('folder', ''), 'why': s.get('why', '')}
            if s.get('category'):
                d['category'] = s['category']
            docs[key] = d
    return docs


def open_outdir(outdir):
    """已發布的加密資料：先原地解密（結尾會重新加密）；清掉舊的 card/*.bin。"""
    import encrypt_data
    if encrypt_data.is_encrypted(outdir):
        encrypt_data.decrypt_dir(outdir, encrypt_data.passphrase_and_salt(persist=False)[0])
    for q in glob.glob(os.path.join(outdir, 'card', '*.bin')):
        os.remove(q)


def load_sheets(outdir):
    s03 = load(os.path.join(outdir, 'sheets', '03.json'))
    s13 = load(os.path.join(outdir, 'sheets', '13.json'))
    aliases = [r[1] for r in s03['rows']]
    proto = {r[1]: r[21] for r in s03['rows']}
    tag_of = {r[1]: (r[0] or '').strip() for r in s03['rows']}
    r13 = {r[40]: r for r in s13['rows']}
    return aliases, proto, tag_of, r13


def main():
    ap = argparse.ArgumentParser(description='02_設備查詢卡 card aux 產生器（見檔頭 docstring）')
    ap.add_argument('paths', nargs='+', metavar='PATH', help='<cardwork_dir> <outdir>；--recompare 時只給 <outdir>')
    ap.add_argument('--chunk-kb', type=int, default=300)
    ap.add_argument('--no-stamp', action='store_true')
    ap.add_argument('--dcdas', default=DCDAS_DEFAULT, help='signal-atlas 索引 SQLite（預設 %%LOCALAPPDATA%%\\dcdas\\index.sqlite；不存在就略過此來源）')
    ap.add_argument('--no-dcdas', action='store_true', help='不用控制器 I/O 組態當來源')
    ap.add_argument('--recompare', action='store_true', help='cardwork 不在手邊：讀已發布的 card/*.json，只重算 sec.dcdas／compare／flags.cmp')
    ap.add_argument('--docsearch', default=DOCSEARCH_DEFAULT, help='docmap_docsearch.py 的輸出（預設 %%LOCALAPPDATA%%\\AMS\\cardwork\\docsearch.json；不存在就略過）')
    ap.add_argument('--no-docsearch', action='store_true', help='不收文件全文檢索（--recompare 時保留舊的 sec.docsearch）')
    ap.add_argument('--drive-map', default=DRIVE_MAP_DEFAULT, help='drive_map.py 的輸出（預設 %%LOCALAPPDATA%%\\AMS\\drive_map.json；不存在就不補 url）')
    ap.add_argument('--no-drive-map', action='store_true')
    ap.add_argument('--hmi', default=HMI_DEFAULT, help='hmi_index.py 的輸出（預設 %%LOCALAPPDATA%%\\AMS\\cardwork\\hmi.json）')
    ap.add_argument('--hmi-shots', default=HMI_SHOTS_DEFAULT, help='hmi_shots.py 的畫面縮圖目錄（預設 …\\cardwork\\hmi_shots；缺席時只有畫面名稱沒有影像）')
    ap.add_argument('--hmi-nav', default=HMI_NAV_DEFAULT, help='hmi_nav.py 的輸出（逐列選單路徑；預設 …\\cardwork\\hmi_nav.json）')
    ap.add_argument('--no-hmi', action='store_true', help='不收圖控 HMI 畫面位置（--recompare 時保留舊的 sec.hmi 與影像）')
    ap.add_argument('--pid', default=PID_DEFAULT, help='pid_index.py 的輸出（預設 paths.PID_JSON＝<CARDWORK>\\pid.json）')
    ap.add_argument('--pid-shots', default=PID_SHOTS_DEFAULT, help='pid_shots.py 的圖紙影像目錄（預設 paths.PID_SHOTS；缺 index.json 或缺任何一張被引用的圖紙都以非 0 結束）')
    ap.add_argument('--no-pid', action='store_true', help='不收 P&ID 圖面位置（--recompare 時保留舊的 sec.pid、index.pid 與 card/pid 影像）')
    ap.add_argument('--pid-ge', default=PID_GE_DEFAULT, help='pid_ge.py 的輸出（GE 原廠編號的 P&ID 圖面位置；預設 <CARDWORK>\\pid_ge.json）')
    ap.add_argument('--hmi-ge', default=HMI_GE_DEFAULT, help='hmi_ge.py 的輸出（GE 原廠編號的圖控畫面位置；預設 <CARDWORK>\\hmi_ge.json）')
    ap.add_argument('--loc-ge', default=LOC_GE_DEFAULT, help='loc_ge.py 的輸出（GE 原廠編號的位置圖位置，v12；預設 <CARDWORK>\\loc_ge.json）')
    ap.add_argument('--wire-ge', default=WIRE_GE_DEFAULT, help='wire_ge.py 的輸出（汽機 TSI 的接線路徑，v13；預設 <CARDWORK>\\wire_ge.json）')
    ap.add_argument('--no-ge-loc', action='store_true', help='GE 編號卡不放 P&ID／圖控／位置圖位置與接線路徑（不讀 pid_ge.json、hmi_ge.json、loc_ge.json、wire_ge.json）')
    ap.add_argument('--ge-tags', default=GE_DEFAULT, help='GE 原廠設備編號對照表 ge_tags.json（預設 paths.GE_TAGS＝hst-docsearch config.json 的 ge_tags_dir）')
    ap.add_argument('--no-ge', action='store_true', help='不收 GE 原廠編號（--recompare 時保留舊的 sec.getag 與 04 位號索引的 GE 列）')
    a = ap.parse_args()
    ge = None if a.no_ge else load_ge(a.ge_tags, None if a.no_dcdas else a.dcdas)
    print('getag: %s' % ('略過' if a.no_ge else ('沒有 %s' % a.ge_tags) if ge is None else
                         '%s，%d 筆 GE 編號（對照表建於 %s）' % (a.ge_tags, len(ge['entries']), ge['built_at'])))
    dc = None if a.no_dcdas else load_dcdas(a.dcdas)
    ge_loc_on = ge is not None and not a.no_ge_loc
    hm = None if a.no_hmi else load_hmi(a.hmi, a.hmi_shots, a.hmi_nav, a.hmi_ge if ge_loc_on else None)
    if a.no_hmi:
        print('hmi: 略過')
    elif hm is None:
        print('hmi: 沒有 %s（此來源略過）' % a.hmi)
    else:
        print('hmi: %s，%d 個畫面、%d 支位號有對應；縮圖 %s'
              % (a.hmi, hm['stats'].get('screens_total', 0), len(hm['by_tag']), hm['_shots_dir'] or '（無，只顯示畫面名稱）'))
    pm = None if a.no_pid else load_pid(a.pid, a.pid_shots, a.pid_ge if ge_loc_on else None, a.loc_ge if ge_loc_on else None,
                                        a.wire_ge if ge_loc_on else None)   # 不一致（圖紙鍵／缺影像／影像與 pid.json 不同步）在這裡就以非 0 結束
    if a.no_pid:
        print('pid: 略過')
    elif pm is None:
        print('pid: 沒有 %s' % a.pid)
    elif pm['_shots'] is None:
        print('pid: %s，但沒有圖紙影像索引 %s' % (a.pid, pm['_shots_index']))
    else:
        print('pid: %s，%d 支位號有圖面位置、引用 %d 張圖紙；圖紙影像 %s' % (a.pid, len(pm['by_tag']), len(pm['_used']), pm['_shots_dir']))
    ds = None if a.no_docsearch else load_docsearch(a.docsearch)
    if a.no_docsearch:
        print('docsearch: 略過')
    elif ds is None:
        print('docsearch: 沒有 %s（此來源略過）' % a.docsearch)
    else:
        print('docsearch: %s，索引 %s，%d 台有命中' % (a.docsearch, (ds.get('index') or {}).get('built'), (ds.get('stats') or {}).get('aliases_matched', 0)))
    drive = None if a.no_drive_map else load_drive_map(a.drive_map)
    print('drive_map: %s' % ('略過' if a.no_drive_map else ('沒有 %s（不補 url）' % a.drive_map) if drive is None else '%s，%d 個檔' % (a.drive_map, len(drive['files']))))
    if dc is None:
        print('dcdas: 沒有控制器索引（%s），DCS 基準只用 DCS 寫入／端子表' % ('--no-dcdas' if a.no_dcdas else a.dcdas))
    else:
        print('dcdas: 索引 %s，%d 個類比輸入通道，控制器 %s' % (dc['built_at'], dc['channels'], ' '.join(dc['controllers'])))
    # 外部索引缺席不再靜默略過：少了它查詢卡整個「控制器組態」／「文件全文檢索」區段或所有 Drive 連結會消失，而 build 雜湊照樣一致、
    # verify_encrypted 也不會報；確定要略過的人自己加 --no-*，rebuild.py 因此中止並走加密回滾
    missing = []
    if dc is None and not a.no_dcdas:
        missing.append(('dcdas', a.dcdas, '--no-dcdas'))
    if ds is None and not a.no_docsearch:
        missing.append(('docsearch', a.docsearch, '--no-docsearch'))
    if hm is None and not a.no_hmi:
        missing.append(('hmi', a.hmi, '--no-hmi'))
    if pm is None and not a.no_pid:
        missing.append(('pid', a.pid, '--no-pid'))
    elif pm is not None and pm['_shots'] is None:   # pid.json 在、圖紙影像索引不在：不可降級成「只有文字沒有圖」
        missing.append(('pid_shots', pm['_shots_index'], '--no-pid'))
    if drive is None and not a.no_drive_map:
        missing.append(('drive_map', a.drive_map, '--no-drive-map'))
    if ge is None and not a.no_ge:
        missing.append(('ge_tags', a.ge_tags or '（paths.GE_TAGS 未設定）', '--no-ge'))
    # GE 編號卡的位置（v10）：對照表、pid.json／hmi.json 都在而定位結果不在 → 不可默默發布成「沒有位置」
    if ge_loc_on and pm is not None and pm.get('_ge') is None:
        missing.append(('pid_ge', a.pid_ge, '--no-ge-loc'))
    if ge_loc_on and pm is not None and pm.get('_lg') is None:
        missing.append(('loc_ge', a.loc_ge, '--no-ge-loc'))
    if ge_loc_on and pm is not None and pm.get('_wg') is None:
        missing.append(('wire_ge', a.wire_ge, '--no-ge-loc'))
    if ge_loc_on and hm is not None and hm.get('_ge') is None:
        missing.append(('hmi_ge', a.hmi_ge, '--no-ge-loc'))
    if missing:
        for name, path, _flag in missing:
            print('!! 缺 %s（%s）' % (name, path))
        raise SystemExit('!! 缺 %s，若確定要略過請加 %s' % ('／'.join(m[0] for m in missing), '／'.join(m[2] for m in missing)))
    if a.recompare:
        if len(a.paths) != 1:
            ap.error('--recompare 只給 <outdir>')
        recompare(a.paths[0], dc, ds, drive, hm, a.no_hmi, a.chunk_kb, a.no_stamp, pm=pm, no_pid=a.no_pid, ge=ge, no_ge=a.no_ge)
        return
    if len(a.paths) != 2:
        ap.error('需要 <cardwork_dir> <outdir>')
    cw, outdir = a.paths
    open_outdir(outdir)
    ams = load(os.path.join(cw, 'ams.json'))
    kinds = {k: load(os.path.join(cw, k + '.json')) for k in ('terminal', 'instlist', 'eomr', 'docindex')}
    aliases, proto, tag_of, r13 = load_sheets(outdir)
    docs = build_docs_map(kinds)

    def dkey(kind, e):
        k = '%s|%s|%s' % (kind, e['doc_id'], e.get('rev') or '')
        return k if k in docs else None

    stats = new_stats(aliases)
    out = {}
    ge_by_tag = {}
    ge_prepass(ge, [tag_of.get(al, '') for al in aliases])
    for al in aliases:
        A = ams['by_alias'].get(al) or {}
        sec = {}
        for g in ('sync', 'change', 'ident', 'device', 'alarm', 'ff'):
            if A.get(g):
                sec[g] = {'rows': [list(r) for r in A[g]]}
        flags = dict(A.get('flags') or {})
        dw = A.get('dcs_writes') or {}
        if dw:
            flags['dcs_write_keys'] = sorted(dw.keys())

        # ---- terminal
        T = kinds['terminal']['by_alias'].get(al) or []
        term_entries = []
        term_primary = None
        for e in T:
            f = fdict(e)
            lvl = entry_lvl(e, 'doc')
            rows = []
            lo, hi, un = f.get('DCS量程下限_num'), f.get('DCS量程上限_num'), f.get('DCS 單位')
            for k, v in e.get('fields', []):
                if k.endswith('_num') or k in ('DCS 量程下限', 'DCS 量程上限', 'DCS 單位'):
                    continue
                rows.append([k, v])
                if k == '訊號等級' and (f.get('DCS 量程下限') is not None or f.get('DCS 量程上限') is not None):
                    rows.append(['DCS 量程 (DEVICE_LO/HI/UNITS)', '%s – %s %s' % (f.get('DCS 量程下限', ''), f.get('DCS 量程上限', ''), un or ''), 'terminal'])
            if not any(r[0].startswith('DCS 量程') for r in rows) and (f.get('DCS 量程下限') is not None or f.get('DCS 量程上限') is not None):
                rows.insert(0, ['DCS 量程 (DEVICE_LO/HI/UNITS)', '%s – %s %s' % (f.get('DCS 量程下限', ''), f.get('DCS 量程上限', ''), un or ''), 'terminal'])
            ent = {'h': '%s · %s' % (doc_ref(e), e.get('loc', '')), 'lvl': lvl,
                   'src': '%s · %s %s' % (src_prefix(lvl), doc_ref(e), e.get('loc', '')), 'rule': e.get('rule'), 'rows': rows}
            dk = dkey('terminal', e)
            if dk:
                ent['d'] = dk
            term_entries.append(ent)
            if term_primary is None and num(lo) is not None and num(hi) is not None:
                term_primary = {'lo': num(lo), 'hi': num(hi), 'unit': un or '', 'src': ent['src'], 'lvl': lvl, 'kind': 'terminal', 'ent': ent}
        if term_entries:
            sec['terminal'] = {'entries': term_entries}

        # ---- instlist
        I = kinds['instlist']['by_alias'].get(al) or []
        il_entries = []
        il_primary = None
        # 主體列：有量程 _num 且不是保護管/感測元件（熱電偶 -40-800 °C 不可拿去比 DCS）
        def is_body(f):
            it = str(f.get('項目') or f.get('儀器種類') or '')
            return not re.search(r'thermowell|element|保護管|熱電偶', it, re.I)
        for e in I:
            f = fdict(e)
            lvl = entry_lvl(e, 'doc')
            pre = src_prefix(lvl)
            rows = []
            for k, v in e.get('fields', []):
                if k.endswith('_num') or k == '量程單位':
                    continue
                rows.append([k, v])
            ent = {'h': '%s · %s%s' % (doc_ref(e), e.get('loc', ''), ('（%s）' % e['copy']) if e.get('copy') else ''), 'lvl': lvl,
                   'src': '%s · %s %s' % (pre, doc_ref(e), e.get('loc', '')), 'rule': e.get('rule'), 'rows': rows}
            notes = [x for x in (e.get('note'), e.get('rev_note')) if x]
            if notes:
                ent['note'] = '；'.join(notes)
            dk = dkey('instlist', e)
            if dk:
                ent['d'] = dk
            il_entries.append(ent)
            if il_primary is None and num(f.get('量程下限_num')) is not None and num(f.get('量程上限_num')) is not None and is_body(f):
                presumed = bool(f.get('量程單位來源'))
                il_primary = {'lo': num(f['量程下限_num']), 'hi': num(f['量程上限_num']),
                              'unit': (f.get('量程單位') or '') + ('（推定）' if presumed and f.get('量程單位') else ''), 'src': ent['src'],
                              'lvl': lvl, 'kind': 'instlist', 'ent': ent, 'field': '設計量程（原文）', 'unit_presumed': presumed}
        if il_entries:
            sec['instlist'] = {'entries': il_entries}

        # ---- eomr
        E = kinds['eomr']['by_alias'].get(al) or []
        eo_entries = []
        eo_primary = None
        eo_ref = None  # 序號與 AMS 不符（非本台）的證書：只列參考
        cands = []
        for e in E:
            f = fdict(e)
            lvl = entry_lvl(e, 'factory')
            rows = []
            for k, v in e.get('fields', []):
                if k.endswith('_num') or k == '量程單位':
                    continue
                r = [k, v]
                if k == '序號與 AMS 相符' and str(v) != '是':
                    r.append('warn')
                rows.append(r)
            ent = {'h': '%s · %s' % (doc_ref(e), e.get('loc', '')), 'lvl': lvl,
                   'src': '%s · %s %s' % (src_prefix(lvl), doc_ref(e), e.get('loc', '')), 'rule': e.get('rule'), 'rows': rows}
            dk = dkey('eomr', e)
            if dk:
                ent['d'] = dk
            eo_entries.append(ent)
            if num(f.get('出廠量程下限_num')) is not None and num(f.get('出廠量程上限_num')) is not None:
                mt = str(f.get('序號與 AMS 相符') or '')  # docmap_eomr：'是'｜'否（AMS=…）'｜'AMS 無序號（…）'
                q = {'lo': num(f['出廠量程下限_num']), 'hi': num(f['出廠量程上限_num']), 'unit': f.get('量程單位') or '', 'src': ent['src'],
                     'lvl': lvl, 'kind': 'eomr', 'ent': ent, 'field': '出廠校正量程（原文）'}
                if mt.startswith('否'):  # 序號不符＝非本台：不進候選，只列參考
                    if eo_ref is None:
                        eo_ref = q
                else:
                    cands.append((0 if mt == '是' else 1, len(cands), dict(q, pre_note='' if mt == '是' else 'AMS 未寫入序號，無法確認為同一台；')))
        if cands:
            eo_primary = sorted(cands, key=lambda x: (x[0], x[1]))[0][2]
        if eo_entries:
            sec['eomr'] = {'entries': eo_entries}

        # ---- docindex
        X = kinds['docindex']['by_alias'].get(al) or []
        if X:
            rows = []
            def ck(e):
                c = fdict(e).get('類別', '')
                return (DOC_CAT_ORDER.index(c) if c in DOC_CAT_ORDER else 99, c, e['doc_id'])
            for e in sorted(X, key=ck):
                f = fdict(e)
                lvl = entry_lvl(e, 'doc')
                val = '%s · p.%s' % (f.get('文件') or doc_ref(e), f.get('頁', ''))
                extra = [x for x in (('命中寫法 ' + f['命中寫法']) if f.get('命中寫法') else None, f.get('備註')) if x]
                if extra:
                    val += '（%s）' % '；'.join(extra)
                row = [f.get('類別', ''), val, lvl, '%s · %s %s' % (src_prefix(lvl), f.get('文件') or doc_ref(e), e.get('loc', '')),
                       {'rule': e.get('rule')}]
                dk = dkey('docindex', e)
                if dk:
                    row[4]['d'] = dk
                rows.append(row)
            sec['docindex'] = {'rows': rows}

        # ---- docsearch（文件全文檢索）
        docsearch_apply(sec, ds, al)
        # ---- hmi（圖控畫面位置；以現行 AMS 位號對照，不是 alias）
        hmi_apply(sec, hm, tag_of.get(al, ''))
        # ---- pid（P&ID 圖面位置；同樣以現行 AMS 位號對照）
        pid_apply(sec, pm, tag_of.get(al, ''))
        # ---- getag（GE 原廠編號；以現行 AMS 位號對照 ge_tags 對照表）
        ge_apply(sec, ge, tag_of.get(al, ''), ge_by_tag, al)

        # ---- dcdas（控制器 I/O 組態）
        dc_entries, dc_primary = dcdas_entries(tag_of.get(al, ''), dc)
        if dc_entries:
            sec['dcdas'] = {'entries': dc_entries}

        # ---- DCS 基準比對（量程）
        r = r13.get(al)
        ams_cur, ams_unit_note = ams_current(r)
        compare, cmp_mark = build_compare(dcs_write_base(dw, r, term_primary, ams_cur, ams_unit_note), dc_primary, term_primary,
                                          ams_cur, il_primary, eo_primary, stats, eo_ref)
        strip_marks(sec)
        if cmp_mark:
            flags['cmp'] = cmp_mark
        flags['ff'] = proto.get(al) == 'FF'
        for k in sec:
            stats['sections'][k] = stats['sections'].get(k, 0) + 1
        out[al] = {'sec': sec, 'compare': compare, 'flags': flags}

    searched = {}
    for kind, j in kinds.items():
        keep = ('doc_id', 'rev', 'ref', 'title', 'folder', 'used', 'why') + (('category',) if kind == 'docindex' else ())
        searched[kind] = [{k: s.get(k) for k in keep if k in s} for s in j.get('searched', [])]
    src_stats = {k: {kk: vv for kk, vv in (j.get('stats') or {}).items() if kk in ('aliases_matched', 'rows', 'notes', 'per_category_aliases')} for k, j in kinds.items()}
    src_stats['ams'] = {'notes': (ams.get('stats') or {}).get('notes', []), 'backup_date': ams.get('backup_date')}
    searched, docs, src_stats = docsearch_index(ds, searched, docs, src_stats)
    write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, hm, a.chunk_kb, a.no_stamp, pm=pm, ge=ge, ge_by_tag=ge_by_tag)


def recompare(outdir, dc, ds, drive, hm, no_hmi, chunk_kb, no_stamp, pm=None, no_pid=False, ge=None, no_ge=False):
    """讀已發布的 card/*.json：保留各文件區段，重算 sec.dcdas、compare、flags.cmp；有給 docsearch 就換掉 sec.docsearch、
    有給 hmi 就換掉 sec.hmi 並重寫 card/hmi/*.json（--no-hmi 保留舊的；限制見檔頭）；有給 pid 就換掉 sec.pid 並重寫 card/pid/*.json
    （--no-pid 保留舊的 sec.pid、index.pid、影像與 stats.pid）。"""
    open_outdir(outdir)
    card_dir = os.path.join(outdir, 'card')
    index = load(os.path.join(card_dir, 'index.json'))
    old, old_docs = {}, {}
    for fn in index['files']:
        j = load(os.path.join(outdir, fn))
        old.update(j['by_alias'])
        old_docs.update(j.get('docs') or {})  # 新版 index 只留 alias map，docs 隨分塊攜帶（P3）；舊版分塊沒有這鍵
    aliases, proto, tag_of, r13 = load_sheets(outdir)
    stats = new_stats(aliases)
    out = {}
    n_lost = 0
    ge_by_tag = {}
    ge_prepass(ge, [tag_of.get(al, '') for al in aliases])
    for al in aliases:
        o = old.get(al) or {'sec': {}, 'compare': [], 'flags': {}}
        sec = o.get('sec') or {}
        sec.pop('dcdas', None)
        if ds is not None:
            sec.pop('docsearch', None)
            docsearch_apply(sec, ds, al)
        if hm is not None:
            sec.pop('hmi', None)
            hmi_apply(sec, hm, tag_of.get(al, ''))
        if pm is not None:
            sec.pop('pid', None)
            pid_apply(sec, pm, tag_of.get(al, ''))
        elif 'pid' in sec:   # --no-pid：內容原封不動，但放回與重算時相同的鍵序（否則 docsearch／hmi 被重新附加後 pid 會跑到它們前面，
            sec['pid'] = sec.pop('pid')   # 同樣的資料產出不同的位元組與 build 雜湊）
        if ge is not None:
            sec.pop('getag', None)
            ge_apply(sec, ge, tag_of.get(al, ''), ge_by_tag, al)
        elif 'getag' in sec:   # --no-ge：同上，原封不動但鍵序與重算時相同
            sec['getag'] = sec.pop('getag')
        for kk in ('terminal', 'instlist', 'eomr'):  # 去掉舊的比對狀態
            for ent in (sec.get(kk) or {}).get('entries', []):
                for row in ent['rows']:
                    if len(row) > 2 and row[2] in CMP_STATUSES:
                        del row[2:]
        oc = o.get('compare') or []
        base_dcs, prim, eo_ref = None, {}, None

        def eomr_serial(x):
            """舊 others 列 → 該證書 entry 的「序號與 AMS 相符」欄值（依 src 找 entry）；找不到回 ''。"""
            ent = next((e for e in (sec.get('eomr') or {}).get('entries', []) if e.get('src') == x.get('src')), None)
            for row in (ent or {}).get('rows') or []:
                if row[0] == '序號與 AMS 相符':
                    return str(row[1] or '')
            return ''
        if oc:
            b = oc[0]['baseline']
            if b['kind'] == 'dcs_write':
                base_dcs = dict(b, bounds=set(b.get('bounds') or ['lo', 'hi']))
            elif b['kind'] in ('terminal', 'dcdas'):
                prim[b['kind']] = b
            for x in oc[0].get('others') or []:
                if x['kind'] == 'eomr':
                    mt = eomr_serial(x)
                    note = x.get('note') or ''
                    # 序號不符（非本台）：entry 欄值以「否」開頭；沒有 entry 可查時看舊 note 前綴／status
                    is_ref = mt.startswith('否') if mt else (x.get('status') == 'ref_only' or note.startswith('證書序號與 AMS 不符'))
                    if is_ref:
                        if eo_ref is None and x.get('lo') is not None and x.get('hi') is not None:
                            eo_ref = {'lo': x['lo'], 'hi': x['hi'], 'unit': x.get('unit') or '', 'src': x.get('src'), 'lvl': x.get('lvl') or 'factory', 'kind': 'eomr'}
                    elif 'eomr' not in prim:
                        prim['eomr'] = x
                elif x['kind'] in ('terminal', 'instlist'):
                    prim[x['kind']] = x
                elif x['kind'] == 'dcs_write':  # 舊資料把寫入事件列為一般來源：還原成 DCS 寫入來源（note 去掉 compare_range 產生的段，含「換算為」，否則每次重算累積）
                    base_dcs = dict(x, bounds=set(x.get('bounds') or ['lo', 'hi']),
                                    note='；'.join(seg for seg in (x.get('note') or '').split('；') if seg and not seg.startswith(CMP_NOTE_PREFIXES)))

        def primary(kind, field):
            p = prim.get(kind)
            if not p or p.get('lo') is None or p.get('hi') is None:
                return None
            ent = next((e for e in (sec.get(kind) or {}).get('entries', []) if e.get('src') == p.get('src')), None)
            q = {'lo': p['lo'], 'hi': p['hi'], 'unit': p.get('unit') or '', 'src': p.get('src'), 'lvl': p.get('lvl') or 'doc', 'kind': kind, 'ent': ent}
            if field:
                q['field'] = field
            note = p.get('note') or ''
            if kind == 'instlist' and note.startswith('此來源量程為數值儲存格'):
                q['unit_presumed'] = True
            if kind == 'eomr':
                mt = eomr_serial(p)  # entry 欄值優先；找不到 entry 時看舊 note 前綴（舊資料兩種情形都寫「證書序號與 AMS 不符」）
                no_serial = mt.startswith('AMS 無序號') if mt else note.startswith(('AMS 未寫入序號', '證書序號與 AMS 不符'))
                if no_serial:
                    q['pre_note'] = 'AMS 未寫入序號，無法確認為同一台；'
            return q
        term_primary = primary('terminal', None)
        il_primary = primary('instlist', '設計量程（原文）')
        eo_primary = primary('eomr', '出廠校正量程（原文）')
        ams_cur, ams_unit_note = ams_current(r13.get(al))
        if base_dcs is not None and not (base_dcs.get('unit') or '').strip() and ams_cur and ams_cur['unit'].strip():
            # 13 表單位補譯後（E+H 列舉）：DCS 寫入基準的單位規則＝AMS 單位
            base_dcs['unit'] = ams_cur['unit']
            base_dcs['unit_note'] = ''
            base_dcs['note'] = '；'.join(x for x in (base_dcs.get('note') or '').split('；') if x and not x.startswith('單位空白'))
        dc_entries, dc_primary = dcdas_entries(tag_of.get(al, ''), dc)
        if dc_entries:
            sec['dcdas'] = {'entries': dc_entries}
        if not oc and dc_primary and any(sec.get(k) for k in ('instlist', 'eomr')):
            n_lost += 1  # 新有基準、但舊資料沒有 compare 可借儀器清單／EOMR 數值
        compare, cmp_mark = build_compare(base_dcs, dc_primary, term_primary, ams_cur, il_primary, eo_primary, stats, eo_ref)
        strip_marks(sec)
        flags = dict(o.get('flags') or {})
        flags.pop('cmp', None)
        if cmp_mark:
            flags['cmp'] = cmp_mark
        flags['ff'] = proto.get(al) == 'FF'
        for k in sec:
            stats['sections'][k] = stats['sections'].get(k, 0) + 1
        out[al] = {'sec': sec, 'compare': compare, 'flags': flags}
    stats['recompare_note'] = '由已發布 card aux 重算（cardwork 不在手邊）；%d 台舊資料無 compare、其儀器清單／EOMR 量程未列入比對' % n_lost
    searched = {k: v for k, v in (index.get('searched') or {}).items() if k != 'dcdas'}
    docs = {k: v for k, v in dict(old_docs, **(index.get('docs') or {})).items() if not k.startswith('dcdas|')}
    src_stats = {k: v for k, v in (index.get('source_stats') or {}).items() if k != 'dcdas'}
    if hm is None and no_hmi:   # 保留上次發布的 hmi（sec.hmi 已在 old 裡；影像與 index.hmi 原地留著）
        old_hmi = index.get('hmi')
    else:
        old_hmi = None
    # --no-pid：保留上次發布的 P&ID 圖面位置（sec.pid 已在 old 裡；card/pid/*.json 與 index.pid 原地留著，docs 的 pid|… 也留著）
    old_pid = index.get('pid') if (pm is None and no_pid) else None
    if ds is not None:
        searched, docs, src_stats = docsearch_index(ds, searched, docs, src_stats)
    if drive is not None:
        # 有 drive_map 就重新對照：去掉上次補的 url／url_note（各文件產生器本來不給 url；docsearch 的 url 是 docmap_docsearch 給的，保留），
        # 「file|編號|版次」（欄位值的文件編號）整批重算，才能反映 drive_map 更新與 url_note／why 文字
        docs = {k: dict(v) for k, v in docs.items() if not k.startswith('file|')}
        for k, v in docs.items():
            if k.split('|')[0] in ('terminal', 'instlist', 'eomr', 'docindex'):
                v.pop('url', None)
                v.pop('url_note', None)
    write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, hm, chunk_kb, no_stamp, keep_hmi=old_hmi, pm=pm, keep_pid=old_pid,
                 ge=ge, ge_by_tag=ge_by_tag, keep_ge=(ge is None and no_ge), keep_ge_stats=(index.get('stats') or {}).get('getag'),
                 keep_ge_ix=index.get('getag'))


def doc_keys_used(o, acc):
    """遞迴收集分塊 JSON 裡所有鍵名 'd' 的字串（entries[].d、docindex／docsearch 列的 {d}、alt[].d、dcdas 的 doc_key）→ 該分塊用到的 docs key。"""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == 'd' and isinstance(v, str):
                acc.add(v)
            else:
                doc_keys_used(v, acc)
    elif isinstance(o, list):
        for v in o:
            doc_keys_used(v, acc)
    return acc


def chunk_docs(p, docs, doc_no):
    """一個分塊要隨身攜帶的 docs／doc_no 子集：'d' 指到的文件＋分塊文字裡出現的文件編號（前端 docNoLink 對任何欄位值都套 DOCNO 正規式，
    所以用整塊文字掃，寧多勿少）。"""
    keys = doc_keys_used(p, set())
    sub_no = {}
    for m in DOCNO_VAL_RE.finditer(dumps(p)):
        no = m.group(1).upper()
        if no in doc_no:
            sub_no[no] = doc_no[no]
            keys.add(doc_no[no])
    return {k: docs[k] for k in sorted(keys) if k in docs}, sub_no


def write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, hm, chunk_kb, no_stamp, keep_hmi=None, pm=None, keep_pid=None,
                 ge=None, ge_by_tag=None, keep_ge=False, keep_ge_stats=None, keep_ge_ix=None):
    """分塊寫 card/aux-NN.json 與 index.json → manifest.build → 加密 → stamp。
    index.json 只留全廠 alias map 與 searched／stats 等小東西；docs（title／folder／why／Drive url）與 doc_no 隨各分塊攜帶該塊用到的子集
    （P3：docs 每筆含 33 字元 Drive ID 不可壓縮，原本全放 index 佔第一張卡下載量近半；前端 D.loadAux 把分塊的 docs／doc_no 併回 ix）。
    GE 編號卡的資料（card/getag.json，index.getag）：有對照表就重寫；--no-ge 的 --recompare（keep_ge）原檔與 index.getag 都留著；
    兩者皆非就刪掉，不留沒人引用的密文。"""
    import extract_db, encrypt_data
    card_dir = os.path.join(outdir, 'card')
    os.makedirs(card_dir, exist_ok=True)
    ge_card_path = os.path.join(outdir, *GE_CARD_FILE.split('/'))
    # ---- GE 原廠編號的 P&ID／圖控位置（v10）：要先算，才知道 card/pid、card/hmi 還要多發布哪幾張（--no-pid／--no-hmi 時沿用上一份 getag.json 的列）
    ge_loc_path = os.path.join(outdir, *GE_LOC_FILE.split('/'))
    old_card = None
    if ge is not None and (pm is None or hm is None) and os.path.exists(ge_card_path):
        old_card = load(ge_card_path)
        if os.path.exists(ge_loc_path):   # 位置列在另一檔：照條目序號接回去，ge_loc_build 才能以（範圍, 編號）沿用
            bi = load(ge_loc_path).get('by_i') or {}
            for i, x in enumerate(old_card.get('entries') or []):
                x.update(bi.get(str(i)) or {})
    ge_loc, ge_pid_used, ge_hmi_used = ge_loc_build(ge, pm, hm, old_card)
    if ge is not None:
        ld_sheets = {r[4]['s'] for v in ge_loc.values() for r in v.get('ld') or [] if len(r) > 4 and 'marks' in r[4]}
        wp_all = [c for v in ge_loc.values() for c in ([v['wp']] if v.get('wp') else []) + (v.get('wpx') or [])]
        wp_sheets = {r[4]['s'] for c in wp_all for r in c.get('rows') or [] if len(r) > 4 and 'marks' in r[4]}
        stats['getag_loc'] = {'pid_entries': sum(1 for v in ge_loc.values() if v.get('pd')), 'hmi_entries': sum(1 for v in ge_loc.values() if v.get('hm')),
                              'hmi_related_only': sum(1 for v in ge_loc.values() if v.get('hr') and not v.get('hm')),
                              'pid_sheets': len(set(ge_pid_used) - ld_sheets - wp_sheets), 'hmi_screens': len(ge_hmi_used),
                              'ld_entries': sum(1 for v in ge_loc.values() if v.get('ld')), 'ld_sheets': len(ld_sheets),
                              'ld_listed_missing': sum(1 for v in ge_loc.values() if v.get('ldn')),
                              'wp_entries': sum(1 for v in ge_loc.values() if v.get('wp')), 'wp_paths': len(wp_all), 'wp_sheets': len(wp_sheets),
                              'wp_notes': sum(len(c.get('n') or []) for c in wp_all), 'wp_none': sum(1 for v in ge_loc.values() if v.get('wpn')),
                              'wp_xref': sum(1 for v in ge_loc.values() if v.get('wpr'))}
        print('getag: GE 編號卡 %(pid_entries)d 個編號有 P&ID 圖面位置（%(pid_sheets)d 張圖紙）、%(hmi_entries)d 個有圖控畫面位置（%(hmi_screens)d 個畫面）、'
              '%(ld_entries)d 個有位置圖位置（%(ld_sheets)d 張圖紙；%(ld_listed_missing)d 個編號的清單位置圖至少一份沒有位置）、'
              '%(wp_entries)d 個有接線路徑（%(wp_paths)d 條、%(wp_sheets)d 張圖紙、%(wp_notes)d 則註記；有 Mark VIe 訊號但沒有路徑 %(wp_none)d 個，其中 %(wp_xref)d 個的組態螺絲畫在別的編號底下）' % stats['getag_loc'])
    # ---- 圖控畫面影像（card/hmi/<slug>.json，走既有 *.json 加密路徑）；--no-hmi 的 --recompare 保留上次發布的
    if hm is not None:
        hmi_ix = hmi_write_images(outdir, out, hm, stats, ge_hmi_used)
        hs = hmi_doc(hm)
        searched = dict(searched, hmi=[hs])
        src_stats = dict(src_stats, hmi=dict(stats.get('hmi') or {}, notes=hs['why']))
    else:
        hmi_ix = keep_hmi
        if keep_hmi is None:   # 這次沒有 hmi 來源也沒有舊資料可留：清掉 card/hmi/，不要留下沒人引用的密文
            hmi_write_images(outdir, out, None, stats)
            searched = {k: v for k, v in searched.items() if k != 'hmi'}
            src_stats = {k: v for k, v in src_stats.items() if k != 'hmi'}
    # ---- P&ID 圖紙影像（card/pid/<slug>.json，同樣走 *.json 加密路徑）＋每份 PDF 登記進 docs（要在 add_drive_urls 之前，才對得到 Drive url）；
    #      --no-pid 的 --recompare 保留上次發布的（index.pid、影像、docs 的 pid|…、stats.pid 都不動）
    #      影像這時只收集在記憶體（pid_blobs）；card/pid/ 要等下面分塊與 index 都通過自檢才動（None＝保留上次發布的，不動 card/pid/）
    pid_blobs = None
    if pm is not None:
        pid_ix, pid_blobs = pid_collect(out, pm, stats, ge_pid_used)
        docs = dict({k: v for k, v in docs.items() if not k.startswith('pid|')}, **pid_docs(pm, pid_ix))   # 先清掉上次的 pid|…（圖面換版後舊鍵不可留）
    else:
        pid_ix = keep_pid
        if keep_pid is None:   # 這次沒有 pid 來源也沒有舊資料可留：清掉 card/pid/ 與相關項目，不要留下沒人引用的密文
            pid_blobs = {}
            searched = {k: v for k, v in searched.items() if k != 'pid'}
            src_stats = {k: v for k, v in src_stats.items() if k != 'pid'}
            docs = {k: v for k, v in docs.items() if not k.startswith('pid|')}
        else:
            stats['pid'] = dict(keep_pid.get('stats') or {}, bytes=keep_pid.get('bytes'))   # 圖控的保留分支會掉 stats.hmi，這裡不重蹈
            print('pid: 保留上次發布的 P&ID 圖面位置（--no-pid）：%d 張圖紙影像' % len(keep_pid.get('files') or []))
    # ---- index.docs：Drive url 與欄位值的文件編號要先算好，分塊才帶得到
    if dc is not None:
        s, d = dcdas_doc(dc)
        searched = dict(searched, dcdas=[s])
        docs = dict(docs, **d)
        src_stats = dict(src_stats, dcdas={'aliases_matched': stats['sections'].get('dcdas', 0), 'rows': dc['channels'], 'notes': s['why']})
    # ---- GE 原廠編號：出處文件登記進 docs（add_drive_urls 才補得到 url）；searched／source_stats 的 getag 一律「拿掉再附加在最後」，
    #      重算與 --no-ge 保留兩條路的鍵序才會相同。--no-ge 的 --recompare（keep_ge）保留上次發布的 sec.getag（已在 old 裡）、docs 的 ge|…、
    #      04 的 GE 列與 stats.getag。--no-drive-map 時 ge|… 沿用上次補的 url（其他類別的文件也是保留舊 url）
    if ge is not None:
        gs = ge_doc(ge, stats)
        gdocs = {k: dict(v) for k, v in ge['docs'].items()}
        if drive is None:
            for k, v in gdocs.items():
                for f in ('url', 'url_note'):
                    if (docs.get(k) or {}).get(f):
                        v[f] = docs[k][f]
        docs = dict({k: v for k, v in docs.items() if not k.startswith('ge|')}, **gdocs)
        searched = dict({k: v for k, v in searched.items() if k != 'getag'}, getag=[gs])
        src_stats = dict({k: v for k, v in src_stats.items() if k != 'getag'},
                         getag={'aliases_matched': stats['sections'].get('getag', 0), 'rows': ge['n_rows'], 'notes': gs['why']})
    elif keep_ge:
        if 'getag' in searched:
            searched = dict({k: v for k, v in searched.items() if k != 'getag'}, getag=searched['getag'])
        if 'getag' in src_stats:
            src_stats = dict({k: v for k, v in src_stats.items() if k != 'getag'}, getag=src_stats['getag'])
    else:
        docs = {k: v for k, v in docs.items() if not k.startswith('ge|')}
        searched = {k: v for k, v in searched.items() if k != 'getag'}
        src_stats = {k: v for k, v in src_stats.items() if k != 'getag'}
    # ---- GE 編號卡（card/getag.json）：整份對照表，出處文件自成一份 docs、自己補 Drive url（--no-drive-map 時沿用上一份的 url）。
    #      這裡只序列化與自檢，等分塊與 index 都通過才寫檔
    ge_card = None   # (位元組, index.getag)；None＝不動（keep_ge）或刪掉（沒有對照表）
    if ge is not None:
        gcard, gcdocs, gloc = ge_card_data(ge, ge_loc, pm)
        if drive is None:   # 沿用上一份 getag.json 的 url；第一次（v7 升上來、還沒有 getag.json）退而用卡片 docs 的 ge|…，再以「資料夾／檔名」比其他類別的文件
            old_gd = dict(docs, **(load(ge_card_path).get('docs') or {})) if os.path.exists(ge_card_path) else docs
            by_path = {((d.get('folder') or '').lower(), (d.get('title') or '').lower()): d for d in docs.values() if d.get('url')}
            for k, v in gcdocs.items():
                src = old_gd.get(k) or by_path.get(((v.get('folder') or '').lower(), (v.get('title') or '').lower())) or {}
                for f in ('url', 'url_note'):
                    if src.get(f):
                        v[f] = src[f]
            miss = sum(1 for v in gcdocs.values() if not v.get('url'))
            if miss:
                print('getag: !! --no-drive-map 而上一份 GE 編號卡不在：%d 份出處文件沒有雲端硬碟連結（下次有 drive_map 的建置會補上）' % miss)
        n_gurl, _n_galt = add_drive_urls(gcdocs, drive)
        if drive is not None:
            pid_own_urls_only(gcdocs, drive)   # P&ID 圖紙的 PDF 只連自己那一份檔（同 AMS 設備卡）
        # 規格塊裡的文件編號（位置圖、P&ID、Hook-up）→ 那份檔本身（v12）；會再加 file|… 的文件（都有 url），所以 url 份數在這之後才算
        gdoc_no = ge_doc_numbers(gcard, gcdocs, drive, load(ge_card_path) if drive is None and os.path.exists(ge_card_path) else None)
        n_gurl = sum(1 for v in gcdocs.values() if v.get('url'))
        gcard['docs'] = gcdocs
        if gdoc_no:
            gcard['doc_no'] = gdoc_no
        stats['getag_doc_no'] = len(gdoc_no)
        print('getag: 規格欄位裡的文件編號可開圖 %d 個' % len(gdoc_no))
        # 沒有 AMS 設備的 GE 編號，去分隔符後若與 04 的鍵相同（74-1 → 設備鍵 741），打那個字串會先開 AMS 那一台：印出來（前端對純數字的設備鍵另有處理）
        k04 = {ge_cmp(r[0]) for r in load(os.path.join(outdir, 'sheets', '04.json'))['rows'] if r[2] != GE_SRC}
        hide = sorted({x['t'] for x in gcard['entries'] if not x.get('ams') and ge_cmp(x['t']) in k04})
        if hide:
            print('getag: !! %d 個 GE 編號去分隔符後與 04 既有鍵相同（前端以 04 為先，純數字的設備鍵除外）：%s' % (len(hide), '、'.join(hide[:20])))
        gdata = dumps(gcard).encode('utf-8')
        if ABS_PATH_RE.search(gdata.decode('utf-8')):
            raise SystemExit('absolute local path found in ' + GE_CARD_FILE)
        ldata = dumps(gloc).encode('utf-8') if gloc else None
        if ldata and ABS_PATH_RE.search(ldata.decode('utf-8')):
            raise SystemExit('absolute local path found in ' + GE_LOC_FILE)
        ge_card = (gdata, {'version': 1, 'files': [GE_CARD_FILE] + ([GE_LOC_FILE] if ldata else []), 'built_at': ge['built_at'], 'n': gcard['n'],
                           'docs': len(gcdocs), 'docs_with_url': n_gurl, 'shadowed': len(hide), 'bytes': len(gdata),
                           'loc_entries': len(gloc['by_i']) if gloc else 0, 'loc_bytes': len(ldata) if ldata else 0}, ldata)
        print('getag: GE 編號卡 %d 個編號、%d 份出處文件（%d 份有雲端硬碟連結）、%d KB；位置檔 %d 個編號、%d KB'
              % (gcard['n'], len(gcdocs), n_gurl, len(gdata) // 1024, ge_card[1]['loc_entries'], ge_card[1]['loc_bytes'] // 1024))
    docs = {k: dict(v) for k, v in docs.items()}
    _n, n_alt = add_drive_urls(docs, drive)
    n_alt -= pid_own_urls_only(docs, drive)   # P&ID 圖紙的 PDF 只連自己那一份檔；退而求其次連到別版次的拿掉
    if pid_ix is not None:
        # no_url 現在才算得出來；searched／source_stats 的 pid 一律「拿掉再附加在最後」，重算與 --no-pid 保留兩條路的鍵序才會相同。
        # 那一筆說明文字只由 stats 產生，所以保留的那條路也重寫一次（drive_map 更新後 no_url 會變，文字要跟著數字走）
        pid_link_stats(pid_ix, docs, stats)
        ps = pid_doc(stats['pid'])
        searched = dict({k: v for k, v in searched.items() if k != 'pid'}, pid=[ps])
        src_stats = dict({k: v for k, v in src_stats.items() if k != 'pid'}, pid=dict(stats['pid'], notes=ps['why']))
    doc_no = resolve_doc_numbers(out, docs, drive)  # 會再加 file|編號|版次 的文件（都有 url），所以 url 份數在這之後才算
    n_url = sum(1 for d in docs.values() if d.get('url'))
    stats['docs'] = len(docs)
    stats['docs_with_url'] = n_url
    stats['docs_with_url_altrev'] = n_alt
    stats['doc_no_resolved'] = len(doc_no)
    stats['near'] = stats['compare_status'].get('near', 0)
    print('docs: %d 份文件，%d 份有 Google 雲端硬碟連結（其中 %d 份連到別版次，帶 url_note）；欄位值的文件編號可開圖 %d 個' % (len(docs), n_url, n_alt, len(doc_no)))
    # ---- 分塊（依 03 列序，每塊 ≤ 約 chunk_kb）
    limit = chunk_kb * 1024
    parts, cur, cur_b = [], {}, 0
    for al in aliases:
        b = len(dumps(out[al]).encode('utf-8')) + len(al) + 6
        if cur and cur_b + b > limit:
            parts.append(cur); cur, cur_b = {}, 0
        cur[al] = out[al]; cur_b += b
    if cur:
        parts.append(cur)
    width = max(2, len(str(len(parts) - 1)))
    alias_map, sizes, blobs, used_keys = {}, [], [], set()
    for k, p in enumerate(parts):  # 先全部序列化並自檢，確定沒問題才刪舊檔寫新檔
        fn = 'aux-%0*d.json' % (width, k)
        sub_docs, sub_no = chunk_docs(p, docs, doc_no)
        used_keys.update(sub_docs)
        data = dumps({'part': k, 'by_alias': p, 'docs': sub_docs, 'doc_no': sub_no}).encode('utf-8')
        if ABS_PATH_RE.search(data.decode('utf-8')):
            raise SystemExit('absolute local path found in ' + fn)
        blobs.append((fn, data))
        sizes.append(len(data))
        for al in p:
            alias_map[al] = k
    stats['docs_unreferenced'] = len(set(docs) - used_keys)  # searched 有列但沒有任何欄位引用的文件（只在 index.searched 出現）
    # ---- 04 位號索引的 GE 編號列：這裡只算（含 stats.getag，要進 index），等分塊與 index 自檢過、card/ 寫完才寫 04／00／manifest。
    #      --no-ge 保留時不動；沒有對照表又不保留時清掉上次加的列
    ge_plan = None
    if not keep_ge:
        n_rows, n_keys, skipped, writes, man_new = ge_index_plan(outdir, (ge_by_tag or {}) if ge is not None else {})
        ge_plan = (writes, man_new)
        if ge is not None:
            stats['getag'] = {'aliases': stats['sections'].get('getag', 0), 'ge_keys': n_keys, 'index_rows': n_rows, 'skipped_keys': len(skipped),
                              'card_entries': ge_card[1]['n'] if ge_card else 0}
            print('getag: %d 台有 GE 原廠編號；04 位號索引加 %d 列（%d 個 GE 編號）' % (stats['sections'].get('getag', 0), n_rows, n_keys))
            if skipped:
                print('getag: !! %d 個 GE 編號與 04 既有鍵相同（或去分隔符後相同）而沒加進位號索引：%s' % (len(skipped), '、'.join(skipped[:20])))
    elif keep_ge_stats:   # --no-ge 保留：與重算時同一個位置寫回（鍵序相同，build 雜湊才不會因走哪條路而變）
        stats['getag'] = keep_ge_stats
    index = {'version': 2, 'parts': len(parts), 'part_width': width, 'files': ['card/aux-%0*d.json' % (width, k) for k in range(len(parts))],
             'alias': alias_map, 'src_defs': SRC_DEFS, 'kind_label': KIND_LABEL, 'doc_cat_order': DOC_CAT_ORDER,
             'searched': searched, 'source_stats': src_stats, 'stats': stats, 'compare_rule': COMPARE_RULE}
    if hmi_ix is not None:
        index['hmi'] = hmi_ix
    if pid_ix is not None:
        index['pid'] = pid_ix
    if ge_card is not None:
        index['getag'] = ge_card[1]
    elif keep_ge and keep_ge_ix and os.path.exists(ge_card_path):
        index['getag'] = keep_ge_ix
    idata = dumps(index)
    if ABS_PATH_RE.search(idata):
        raise SystemExit('absolute local path found in index.json')
    # ---- 到這裡分塊與 index 都序列化、自檢過了，才動資料目錄裡的 card/：舊分塊、P&ID 圖紙影像、index 接連換掉。
    #      （2026-10-10 稽核：原本 card/pid/ 在最前面就清空重寫、index 的自檢排在寫完分塊之後——中途失敗會留下新舊混雜的 card/。
    #       圖控的 card/hmi/ 仍由上面的 hmi_write_images 先寫：那一段照舊不動。）
    for p in glob.glob(os.path.join(card_dir, 'aux-*.json')):
        os.remove(p)
    for fn, data in blobs:
        open(os.path.join(card_dir, fn), 'wb').write(data)
    if pid_blobs is not None:
        pid_write_images(outdir, pid_blobs)
    if ge_card is not None:
        open(ge_card_path, 'wb').write(ge_card[0])
        if ge_card[2]:
            open(ge_loc_path, 'wb').write(ge_card[2])
        elif os.path.exists(ge_loc_path):
            os.remove(ge_loc_path)
    elif 'getag' not in index:
        for gp in (ge_card_path, ge_loc_path):
            if os.path.exists(gp):
                os.remove(gp)
    open(os.path.join(card_dir, 'index.json'), 'wb').write(idata.encode('utf-8'))
    if ge_plan is not None:
        for path, data in ge_plan[0]:
            open(path, 'wb').write(data)
        open(os.path.join(outdir, 'manifest.json'), 'wb').write(dumps(ge_plan[1]).encode('utf-8'))
    print('card aux: %d aliases, %d parts, max %d KB, total %d KB, index %d KB' % (len(alias_map), len(parts), max(sizes) // 1024, sum(sizes) // 1024, len(idata.encode('utf-8')) // 1024))
    print(json.dumps(stats, ensure_ascii=False))
    cs = stats['compare_status']
    print('compare: 近似（near，同單位差在容差內）%d 筆；EOMR 序號不符只列參考（ref_only）%d 筆；控制器多通道量程不一（dcdas_multi）%d 台；'
          '改以控制器 checkout 日判定後基準不同 %d 筆；Drive 連結連到別版次 %d 份'
          % (cs.get('near', 0), cs.get('ref_only', 0), stats.get('dcdas_multi', 0), stats.get('baseline_changed_by_checkout', 0), n_alt))
    av = stats.get('ams_vs_dcdas') or {}
    tot = sum(av.values())
    if tot:
        print('AMS 現值 vs 控制器組態：完全相同 %d（%.0f%%）、近似 %d（%.0f%%）、不符 %d（%.0f%%）、未比較 %d，共 %d 台'
              % (av.get('ok', 0), 100.0 * av.get('ok', 0) / tot, av.get('near', 0), 100.0 * av.get('near', 0) / tot,
                 av.get('mismatch', 0), 100.0 * av.get('mismatch', 0) / tot, av.get('not_compared', 0), tot))

    # ---- manifest build（含 card/*.json）＋ 加密 ＋ stamp
    man_path = os.path.join(outdir, 'manifest.json')
    man = load(man_path)
    man.setdefault('aux', {})['card'] = dict(man.get('aux', {}).get('card') or {}, index='card/index.json', parts=len(parts),
                                            bytes=sum(sizes) + len(idata.encode('utf-8')))
    man['build'] = extract_db.data_build(outdir, man)
    open(man_path, 'wb').write(dumps(man).encode('utf-8'))
    print('manifest build', man['build'])
    encrypt_data.encrypt_dir(outdir, *encrypt_data.passphrase_and_salt())
    if not no_stamp:
        docs_db = os.path.dirname(os.path.abspath(outdir))
        extract_db.stamp(docs_db, os.path.join(os.path.dirname(docs_db), 'assets'))


if __name__ == '__main__':
    main()
