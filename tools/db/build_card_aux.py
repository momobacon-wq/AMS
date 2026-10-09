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
import os, sys, json, re, math, glob, argparse

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
              'pid': 'P&ID 圖面'}
DOCSEARCH_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'docsearch.json')
DRIVE_MAP_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'drive_map.json')
HMI_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'hmi.json')
HMI_SHOTS_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'hmi_shots')
HMI_NAV_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'hmi_nav.json')
PID_DEFAULT = paths.PID_JSON          # <CARDWORK>\pid.json（tools/db/pid_index.py 的輸出）
PID_SHOTS_DEFAULT = paths.PID_SHOTS   # <CARDWORK>\pid_shots（tools/db/pid_shots.py：<slug>.webp＋index.json）
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


def load_hmi(path, shots_dir, nav_path):
    """tools/db/hmi_index.py 的輸出（位號→畫面與座標）＋ tools/db/hmi_shots.py 的縮圖目錄＋ hmi_nav.py 的逐列選單路徑。
    沒有 hmi.json 就回 None（此來源整段略過）。縮圖目錄缺席時只有畫面名稱與路徑、沒有影像。"""
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


def hmi_write_images(outdir, out, hm, stats):
    """收集 out 裡 sec.hmi 真的用到的畫面 → 寫 card/hmi/<slug>[__<選單機組>].json（{w,h,mime,b64}，走既有 *.json 加密路徑），
    回傳 index.hmi（畫面中繼資料＋檔案清單）。先整個清掉 card/hmi/ 才寫，避免掉出覆蓋範圍的畫面留下孤兒密文。

    影像來源兩種（hmi_shots 的 index.json）：
      執行時截圖（source='runtime capture'）——**逐「選單機組」各一張**，同一張畫面在 HRSG11／HRSG12 的現值不同，
        不可共用；只發布這張卡真的用得到的那幾組，`meta.variants[選單機組]` 給前端挑，`meta.file` 是挑不到時的退路。
      設計時 ThumbNail（EMF）——整個畫面一張，沒有機組之分（值是 ###）。"""
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
          'stats': {'devices': ndev, 'screens': len(screens), 'screens_with_img': sum(1 for m in screens.values() if m.get('img')),
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
                    for m in DOCNO_VAL_RE.finditer(str(r[1] or '')):
                        wanted.setdefault(m.group(1).upper(), set()).add((m.group(2) or '').upper())
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
PID_NOTE_NAME = {1: '圖上註記或表格（儀器清單）裡的文字', 2: '跨圖訊號旗標', 3: '儀用／廠用空氣分配圖上的用氣點', 4: '迴路詳圖（TYPICAL 小圖）裡的標籤'}
PID_NOTE_TEXT = {1: '這一處是圖上註記或表格（儀器清單）裡的文字，不是儀器符號旁的標籤',
                 2: '這一處是跨圖訊號旗標（接往另一張圖的訊號引用），不是儀器本身的位置',
                 3: '這一處是儀用／廠用空氣分配圖上的用氣點（這顆閥的供氣接點），不是閥在製程管線上的位置',
                 4: '這一處在圖紙上的迴路詳圖（TYPICAL 小圖）裡，不是主流程圖上的位置'}
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


def load_pid(path, shots_dir):
    """tools/db/pid_index.py 的輸出（位號→圖紙與圖上座標）＋ tools/db/pid_shots.py 的圖紙影像目錄。
    沒有 pid.json 回 None；pid_shots/index.json 缺席時 `_shots` 是 None——兩者都由 main 的缺檔清單擋下來（非 0 結束、資料目錄沒被動過）。
    **不照抄 hmi 的靜默降級**（hmi_shots 目錄不見時會發布 0 張圖，而每一列還寫著 img:true）。其餘不一致在 pid_check 一次查完。"""
    if not path or not os.path.exists(path):
        return None
    j = load(path)
    if not isinstance(j.get('by_tag'), dict) or not isinstance(j.get('sheets'), dict):
        raise SystemExit('pid.json 格式不對（缺 by_tag／sheets）：' + path)
    j['_shots_dir'] = shots_dir or ''
    j['_shots_index'] = os.path.join(j['_shots_dir'], 'index.json')
    j['_shots'] = load(j['_shots_index']) if os.path.exists(j['_shots_index']) else None
    j['_applied'] = set()   # pid_apply 用過的 by_tag 鍵（沒用到的＝pid.json 有、現行設備總表沒有的位號）
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
        docs[key] = {'title': base, 'folder': folder or '.',
                     'why': 'P&ID 圖面位置：圖上的位置讀自這一份 PDF（%s文件庫裡這份圖的現行最高版次）；連結只開這一份檔本身，'
                            '雲端硬碟對照沒有它時不附連結，不改連其他版次' % (('Rev.%s，' % rev) if rev else '')}
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


def pid_collect(out, pm, stats):
    """收集 out 裡 sec.pid 真的用到的圖紙 → (index.pid, {card/pid/<slug>.json: 內容位元組})。**這裡不寫任何檔**：影像內容先留在記憶體
    （全部約十幾 MB），等 write_output 把分塊與 index 都序列化、自檢過了，才由 pid_write_images 一次清掉舊的 card/pid/ 寫新的
    （2026-10-10 稽核：原本在自檢之前就清空重寫 card/pid/，中途失敗會留下「新影像＋舊 index／舊分塊」）。
    每張圖紙一檔，畫在上面的所有位號共用（標記不燒進影像）。load_pid 已確認每張被引用的圖紙都有影像，所以這裡沒有「沒有影像」的分支。
    no_url 要等 add_drive_urls 之後才知道，由 pid_link_stats 補。"""
    used, ndev, nref = {}, 0, 0
    for al, o in out.items():
        firsts = [r[4] for r in ((o.get('sec') or {}).get('pid') or {}).get('rows') or [] if len(r) > 4 and isinstance(r[4], dict) and r[4].get('s') and 'marks' in r[4]]
        if firsts:
            ndev += 1
            nref += 1 if all(f.get('note') for f in firsts) else 0   # 每張圖上都只有引用（註記／旗標／用氣點／迴路詳圖），沒有任何儀器符號
        for s in {f['s'] for f in firsts}:
            used[s] = used.get(s, 0) + 1
    sheets, blobs, total = {}, {}, 0
    for s in sorted(used):
        sh, shot = pm['sheets'][s], pm['_shots'][s]
        rel = 'card/pid/%s.json' % s
        blobs[rel] = pid_blob(os.path.join(pm['_shots_dir'], shot['file']), shot['w'], shot['h'])
        n = len(blobs[rel])
        sheets[s] = {'doc': sh.get('doc'), 'rev': sh.get('rev'), 'title': sh.get('title') or '', 'name': sh['rel'].rpartition('/')[2],
                     'page': sh['page'], 'pages': sh.get('pages'), 'd': pm['_dkey'][s], 'file': rel, 'w': shot['w'], 'h': shot['h'],
                     'bytes': n, 'rows': used[s], 'ocr': bool(sh.get('ocr'))}
        total += n
    ps = pm.get('stats') or {}
    st = {k: ps[k] for k in PID_STATS_KEEP if k in ps}
    st.update(devices=ndev, devices_ref_only=nref, tags=len(pm['_applied']), tags_unpublished=len(set(pm['by_tag']) - pm['_applied']),
              images=len(blobs), docs=len({m['d'] for m in sheets.values()}))
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
          % (ndev, st['tags'], nref, len(sheets), st['docs'], len(blobs), total // 1024))
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
    """這次發布的圖紙所屬的 PDF → index.docs 的項目（只登記真的有設備引用的；鍵與內容在 load_pid 已算好）。"""
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
    miss = sorted({m['d'] for m in pid_ix['sheets'].values() if not (docs.get(m['d']) or {}).get('url')})
    st = pid_ix.setdefault('stats', {})
    st['no_url'] = sum(1 for m in pid_ix['sheets'].values() if m['d'] in miss)
    st['no_url_docs'] = len(miss)
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
    a = ap.parse_args()
    dc = None if a.no_dcdas else load_dcdas(a.dcdas)
    hm = None if a.no_hmi else load_hmi(a.hmi, a.hmi_shots, a.hmi_nav)
    if a.no_hmi:
        print('hmi: 略過')
    elif hm is None:
        print('hmi: 沒有 %s（此來源略過）' % a.hmi)
    else:
        print('hmi: %s，%d 個畫面、%d 支位號有對應；縮圖 %s'
              % (a.hmi, hm['stats'].get('screens_total', 0), len(hm['by_tag']), hm['_shots_dir'] or '（無，只顯示畫面名稱）'))
    pm = None if a.no_pid else load_pid(a.pid, a.pid_shots)   # 不一致（圖紙鍵／缺影像／影像與 pid.json 不同步）在這裡就以非 0 結束
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
    if missing:
        for name, path, _flag in missing:
            print('!! 缺 %s（%s）' % (name, path))
        raise SystemExit('!! 缺 %s，若確定要略過請加 %s' % ('／'.join(m[0] for m in missing), '／'.join(m[2] for m in missing)))
    if a.recompare:
        if len(a.paths) != 1:
            ap.error('--recompare 只給 <outdir>')
        recompare(a.paths[0], dc, ds, drive, hm, a.no_hmi, a.chunk_kb, a.no_stamp, pm=pm, no_pid=a.no_pid)
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
    write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, hm, a.chunk_kb, a.no_stamp, pm=pm)


def recompare(outdir, dc, ds, drive, hm, no_hmi, chunk_kb, no_stamp, pm=None, no_pid=False):
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
    write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, hm, chunk_kb, no_stamp, keep_hmi=old_hmi, pm=pm, keep_pid=old_pid)


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


def write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, hm, chunk_kb, no_stamp, keep_hmi=None, pm=None, keep_pid=None):
    """分塊寫 card/aux-NN.json 與 index.json → manifest.build → 加密 → stamp。
    index.json 只留全廠 alias map 與 searched／stats 等小東西；docs（title／folder／why／Drive url）與 doc_no 隨各分塊攜帶該塊用到的子集
    （P3：docs 每筆含 33 字元 Drive ID 不可壓縮，原本全放 index 佔第一張卡下載量近半；前端 D.loadAux 把分塊的 docs／doc_no 併回 ix）。"""
    import extract_db, encrypt_data
    card_dir = os.path.join(outdir, 'card')
    os.makedirs(card_dir, exist_ok=True)
    # ---- 圖控畫面影像（card/hmi/<slug>.json，走既有 *.json 加密路徑）；--no-hmi 的 --recompare 保留上次發布的
    if hm is not None:
        hmi_ix = hmi_write_images(outdir, out, hm, stats)
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
        pid_ix, pid_blobs = pid_collect(out, pm, stats)
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
    index = {'version': 2, 'parts': len(parts), 'part_width': width, 'files': ['card/aux-%0*d.json' % (width, k) for k in range(len(parts))],
             'alias': alias_map, 'src_defs': SRC_DEFS, 'kind_label': KIND_LABEL, 'doc_cat_order': DOC_CAT_ORDER,
             'searched': searched, 'source_stats': src_stats, 'stats': stats, 'compare_rule': COMPARE_RULE}
    if hmi_ix is not None:
        index['hmi'] = hmi_ix
    if pid_ix is not None:
        index['pid'] = pid_ix
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
    open(os.path.join(card_dir, 'index.json'), 'wb').write(idata.encode('utf-8'))
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
