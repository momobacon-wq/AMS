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
另讀 docs/db/data/sheets/03.json（alias 列序、位號）與 13.json（AMS 量程現值，DCS 基準比對用），
以及 signal-atlas 的控制器索引 %LOCALAPPDATA%\\dcdas\\index.sqlite（ToolboxST checkout 的 I/O 組態；不進 repo；`--dcdas` 可指定，沒有就略過此來源），
與 tools/db/drive_map.py 的 路徑→Google 雲端硬碟檔案 ID 對照 %LOCALAPPDATA%\\AMS\\drive_map.json（`--drive-map`；有就替 index.docs 每份文件補 url，前端把數值變成連結）。

輸出（CONTRACT.md「card aux」）：
  docs/db/data/card/index.json   {version:2, parts, alias:{alias: 塊號}, src_defs, searched:{kind:[...]}, source_stats, stats, compare_rule}（只留全廠 alias map 等小東西）
  docs/db/data/card/aux-NN.json  {part, by_alias:{alias:{sec:{...}, compare:[...], flags:{...}}}, docs:{key:{...}}, doc_no:{編號: key}}（docs／doc_no 只帶該塊用到的子集）
並重算 manifest.build（含 card/*.json）後重新 stamp docs/db/index.html（tools/db/extract_db.py 的 stamp）。
外部索引（dcdas／docsearch／drive_map）任一缺席且沒給對應 --no-* 旗標時以非 0 結束（rebuild.py 因此中止並走加密回滾），不再靜默略過。

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
sec.dcdas、sec.docsearch（有給時）、compare 與 flags.cmp，並補 Drive url。限制：舊資料沒有 compare 的設備（既無 DCS 寫入也無端子表），儀器清單／EOMR 的量程數值已不可得，
只比 AMS 現值與控制器組態；要完整比對請重跑各產生器後用一般模式。
"""
import os, sys, json, re, math, glob, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))  # tools/encrypt_data.py

FLT_MIN = 1.1754943508222875e-38
SRC_DEFS = {
    'raw': {'label': '原始', 'desc': '直接取 AMS 資料庫某一欄（可經 JOIN）'},
    'decoded': {'label': '解碼', 'desc': '以固定規則換算：時間、字串切段、二進位 int32/float32/UTF-16、FF hex、碼表'},
    'inferred': {'label': '推論', 'desc': '經驗規則、寫死的對照表、外部對照檔或機組範本推論（非資料庫/文件直接記載）'},
    'doc': {'label': '文件', 'desc': '設計文件（DCS 端子表、儀器清單、P&ID、Hook-up…）：「應該是什麼」'},
    'factory': {'label': '出廠', 'desc': '製造商出廠紀錄（EOMR 校正證書）：「出廠時是什麼」'},
    'ctrl': {'label': '控制器', 'desc': '控制器組態 checkout 快照（ToolboxST I/O 組態，經 signal-atlas 索引）：「控制器現在設定是什麼」；各控制器 checkout 日期見來源'},
}
KIND_LABEL = {'dcdas': 'DCS 控制器組態', 'terminal': 'DCS 端子表', 'instlist': '儀器清單', 'eomr': '出廠證書 EOMR', 'docindex': '文件索引', 'docsearch': '文件全文檢索'}
DOCSEARCH_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'docsearch.json')
DRIVE_MAP_DEFAULT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'drive_map.json')
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
    a = ap.parse_args()
    dc = None if a.no_dcdas else load_dcdas(a.dcdas)
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
    if drive is None and not a.no_drive_map:
        missing.append(('drive_map', a.drive_map, '--no-drive-map'))
    if missing:
        for name, path, _flag in missing:
            print('!! 缺 %s（%s）' % (name, path))
        raise SystemExit('!! 缺 %s，若確定要略過請加 %s' % ('／'.join(m[0] for m in missing), '／'.join(m[2] for m in missing)))
    if a.recompare:
        if len(a.paths) != 1:
            ap.error('--recompare 只給 <outdir>')
        recompare(a.paths[0], dc, ds, drive, a.chunk_kb, a.no_stamp)
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
    write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, a.chunk_kb, a.no_stamp)


def recompare(outdir, dc, ds, drive, chunk_kb, no_stamp):
    """讀已發布的 card/*.json：保留各文件區段，重算 sec.dcdas、compare、flags.cmp；有給 docsearch 就換掉 sec.docsearch（限制見檔頭）。"""
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
    write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, chunk_kb, no_stamp)


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


def write_output(outdir, aliases, out, searched, docs, src_stats, stats, dc, drive, chunk_kb, no_stamp):
    """分塊寫 card/aux-NN.json 與 index.json → manifest.build → 加密 → stamp。
    index.json 只留全廠 alias map 與 searched／stats 等小東西；docs（title／folder／why／Drive url）與 doc_no 隨各分塊攜帶該塊用到的子集
    （P3：docs 每筆含 33 字元 Drive ID 不可壓縮，原本全放 index 佔第一張卡下載量近半；前端 D.loadAux 把分塊的 docs／doc_no 併回 ix）。"""
    import extract_db, encrypt_data
    card_dir = os.path.join(outdir, 'card')
    os.makedirs(card_dir, exist_ok=True)
    # ---- index.docs：Drive url 與欄位值的文件編號要先算好，分塊才帶得到
    if dc is not None:
        s, d = dcdas_doc(dc)
        searched = dict(searched, dcdas=[s])
        docs = dict(docs, **d)
        src_stats = dict(src_stats, dcdas={'aliases_matched': stats['sections'].get('dcdas', 0), 'rows': dc['channels'], 'notes': s['why']})
    docs = {k: dict(v) for k, v in docs.items()}
    _n, n_alt = add_drive_urls(docs, drive)
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
    for p in glob.glob(os.path.join(card_dir, 'aux-*.json')):
        os.remove(p)
    for fn, data in blobs:
        open(os.path.join(card_dir, fn), 'wb').write(data)
    stats['docs_unreferenced'] = len(set(docs) - used_keys)  # searched 有列但沒有任何欄位引用的文件（只在 index.searched 出現）
    index = {'version': 2, 'parts': len(parts), 'part_width': width, 'files': ['card/aux-%0*d.json' % (width, k) for k in range(len(parts))],
             'alias': alias_map, 'src_defs': SRC_DEFS, 'kind_label': KIND_LABEL, 'doc_cat_order': DOC_CAT_ORDER,
             'searched': searched, 'source_stats': src_stats, 'stats': stats, 'compare_rule': COMPARE_RULE}
    idata = dumps(index)
    if ABS_PATH_RE.search(idata):
        raise SystemExit('absolute local path found in index.json')
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
