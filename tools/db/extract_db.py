# -*- coding: utf-8 -*-
"""AMS database workbook (20260912_AMS資料庫解析) -> static site data for docs/db/ (CONTRACT.md formats).

Usage:  py tools/db/extract_db.py <sheets_final.pkl> docs/db/data
        py tools/db/build_card_aux.py <cardwork_dir> docs/db/data     (02 查詢卡附加資料 card/*.json；重算 build 並重新 stamp)
        py tools/stamp_assets.py docs                                (改了 docs/assets 時：舊站 docs/index.html 的版本戳)

card aux 前置（各產生器輸出放 <cardwork_dir>，不進 repo）：
  py tools/db/card_ams_extra.py <AmsDb.sqlite> <cardwork>/ams.json 2026-09-12 --sheets docs/db/data/sheets
  py tools/db/docmap_terminal.py <文件庫根> docs/db/data/sheets <cardwork>/terminal.json
  py tools/db/docmap_instlist.py --root <文件庫根> --sheets docs/db/data/sheets --out <cardwork>/instlist.json
  py tools/db/docmap_eomr.py --root <文件庫根> --sheets docs/db/data/sheets --sqlite <AmsDb.sqlite> --cache <dir> --out <cardwork>/eomr.json
  py tools/db/docmap_docindex.py --root <文件庫根> --sheets03 docs/db/data/sheets/03.json --cache <txt dir> --out <cardwork>/docindex.json

Input is the post-processed sheet set written by tools/db/build_workbook.py (same sheets, numbers and columns as the
Excel workbook), so the web site and the workbook never disagree.  Writes manifest.json, sheets/<id>.json
(tables; big ones chunked by device/config/revision, ≤ ~8 MB per part), 00/01 as grid pages and 02 as the card spec,
then stamps docs/db/index.html + version.json (same scheme as tools/stamp_assets.py, assets live in ../assets).
Deterministic: no run timestamps inside the data (the build hash is content based).
"""
import os, sys, json, glob, pickle, hashlib, re, math, datetime
import pandas as pd

MAX_PART_BYTES = 7 * 1024 * 1024
ALIAS = '設備別名 (alias)'
GROUP_OF = {  # module key -> sidebar group
    'devices': '設備與位置', 'index': '設備與位置', 'misc': '設備與位置', 'params': '參數', 'events': '事件稽核',
    'alerts': '警報與設定', 'templates': '範本與測試', 'security': '使用者與系統', 'modules': '字典',
}
GROUPS = ['總覽', '設備與位置', '參數', '事件稽核', '警報與設定', '範本與測試', '使用者與系統', '字典']
TAB = {'總覽': '#1F4E79', '設備與位置': '#2E75B6', '參數': '#7F7F7F', '事件稽核': '#C55A11', '警報與設定': '#C00000',
       '範本與測試': '#548235', '使用者與系統': '#7030A0', '字典': '#404040'}
DICT_SHEETS = {'DD型號庫', '代碼對照表', '關鍵語意規則', '資料表字典', '欄位字典', '視圖與程序', '參數字典', '參數解碼摘要', '事件類別碼表', '權限定義字典'}
# tables kept only in the Excel 明細 workbook (too large / reference only for the web)
WEB_EXCLUDE = {'範本參數現值', '全部警報定義'}
# columns dropped from the web copy of a sheet (still in Excel)
WEB_DROP_COLS = {'參數現值': ['AMS 設備位號 (AmsDeviceTag)', '最後記錄時間UTC', '事件分類 (EventCategories)', 'ParamDataType', 'ParamDataSize', 'ParamName 原文'],
                 '事件總帳': ['事件ID換算時間(台灣) 含毫秒', 'ComputerId 原值', 'OtherBufLen', 'MoreDetail 有值']}
SENTINEL_DATES = {(1899, 12, 30), (1900, 1, 1), (1970, 1, 1), (1, 1, 1), (2036, 2, 5), (2036, 2, 7)}
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
BLANK_STRINGS = {'nan', 'None', 'NaT', '<NA>', 'NULL'}


def dumps(o):
    return json.dumps(o, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def write(path, o):
    data = dumps(o).encode('utf-8')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return len(data)


def cell(v):
    """pandas value -> JSON scalar per CONTRACT (dates as 'YYYY-MM-DD HH:MM:SS'; sentinel dates blank)."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    try:
        if not isinstance(v, (str, bytes)) and pd.api.types.is_scalar(v) and pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, pd.Timestamp):
        v = v.to_pydatetime()
    if isinstance(v, datetime.datetime):
        if (v.year, v.month, v.day) in SENTINEL_DATES or v.year < 1900:
            return None
        us = v.microsecond
        if us:
            return v.strftime('%Y-%m-%d %H:%M:%S') + '.%03d' % (us // 1000)
        return v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v, datetime.date):
        return v.strftime('%Y-%m-%d')
    if hasattr(v, 'item') and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except Exception:
            pass
    if isinstance(v, bool):
        return '是' if v else '否'
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    if isinstance(v, str):
        if v in BLANK_STRINGS:
            return None
        return CTRL.sub('', v)
    if isinstance(v, (int,)):
        return v
    if isinstance(v, float):
        return v
    return str(v)


def col_meta(df, c):
    s = df[c]
    label = str(c)
    if pd.api.types.is_datetime64_any_dtype(s):
        typ, align, w = 'date', 'right', 150
    elif pd.api.types.is_bool_dtype(s):
        typ, align, w = 'text', 'center', 60
    elif pd.api.types.is_numeric_dtype(s):
        typ, align, w = 'num', 'right', 80
    else:
        typ, align = 'text', 'left'
        try:
            sample = s.dropna().astype(str).head(300)
            m = max([len(label)] + [min(len(x), 60) for x in sample]) if len(sample) else len(label)
        except Exception:
            m = len(label)
        w = int(min(420, max(60, m * 8 + 16)))
    note = None
    m = re.search(r'\(([^()]*)\)\s*$', label)
    if m:
        note = m.group(1)
    mono = bool(re.search(r'位號|GUID|UID|路徑|Path|Identifier|ID\b|十六進位|參數 \(', label))
    d = {'label': label, 'fmt': None, 'type': typ, 'w': w, 'align': align, 'bg': None}
    if note:
        d['note'] = note
    if mono:
        d['mono'] = True
    return d


def facets_for(df):
    out = []
    for i, c in enumerate(df.columns):
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        nun = s.nunique(dropna=True)
        if 1 < nun <= 40 and len(df) > 20:
            out.append(i)
        if len(out) >= 8:
            break
    return out


def table_json(sid, name, s, df, number, total=None):
    cols = [col_meta(df, c) for c in df.columns]
    rows = [[cell(v) for v in r] for r in df.itertuples(index=False, name=None)]
    notes = [str(x) for x in (s.get('notes') or [])]
    notes.insert(0, f'一列＝{s.get("one_row", "")}｜列數 {(total if total is not None else len(df)):,}｜來源表：{", ".join(s.get("source_tables", []))}')
    fz = 2 if ALIAS in df.columns and list(df.columns).index(ALIAS) <= 1 else 1
    return {
        'id': sid, 'name': f'{number}_{name}', 'mode': 'table', 'title': f'{number}_{name}',
        'notes': notes,
        'header_cells': [{'r': 1, 'c': 1, 'v': {'t': '⌂ 目錄', 'l': {'s': '00', 'r': 1}}}],
        'bands': [{'label': s.get('purpose', name)[:60], 'from': 0, 'to': max(0, len(cols) - 1), 'bg': '#1F4E79', 'fc': '#FFFFFF'}],
        'columns': cols, 'freeze_cols': fz, 'rows': rows, 'styles': [], 'cell_styles': [], 'row_styles': [],
        'ui': {'default_sort': None, 'facets': facets_for(df), 'search_cols': None, 'alias_col': (list(df.columns).index(ALIAS) if ALIAS in df.columns else None),
               'key_col': 0},
    }


def chunk_table(base, df, key_col):
    """Split df into parts aligned on key_col (rows of one key never cross parts). Returns list of (offset, sub_df)."""
    keys = df[key_col].fillna('').astype(str).values
    est = max(1, len(dumps([cell(v) for v in df.iloc[0].tolist()]).encode('utf-8')) + 2) if len(df) else 1
    target = max(2000, MAX_PART_BYTES // est)
    parts = []
    start = 0
    n = len(df)
    while start < n:
        end = min(n, start + target)
        if end < n:
            k = keys[end - 1]
            while end < n and keys[end] == k:
                end += 1
        parts.append((start, df.iloc[start:end]))
        start = end
    return parts


# ---------------------------------------------------------------- grid pages
def grid_00(cfg, entries, title, sub):
    st = []
    def style(**kw):
        st.append(kw); return len(st) - 1
    S_TITLE = style(b=1, fc='#1F4E79', sz=20, va='middle'); S_SUB = style(fc='#595959', sz=10)
    S_H = style(b=1, bg='#1F4E79', fc='#FFFFFF', sz=11); S_K = style(b=1, fc='#1F4E79'); S_V = style(wrap=1)
    S_TH = style(b=1, bg='#DDEBF7'); S_LINK = style(u=1, fc='#0563C1'); S_NUM = style(ha='right')
    rows = []; sections = []
    r = 1
    rows.append({'r': r, 'h': 40, 'cells': [{'c': 1, 'v': '⌂ 目錄', 's': S_LINK, 'l': {'s': '00', 'r': 1}}, {'c': 2, 'v': title, 's': S_TITLE, 'cs': 5}]}); r += 1
    rows.append({'r': r, 'cells': [{'c': 2, 'v': sub, 's': S_SUB, 'cs': 5}]}); r += 2
    def sec(label):
        nonlocal r
        sections.append({'r': r, 'label': label})
        rows.append({'r': r, 'h': 26, 'cells': [{'c': 1, 'v': label, 's': S_H, 'cs': 6}]}); r += 1
    sec('1  資料來源')
    for k, v in cfg.get('sources', []):
        rows.append({'r': r, 'cells': [{'c': 2, 'v': k, 's': S_K}, {'c': 3, 'v': v, 's': S_V, 'cs': 4}]}); r += 1
    r += 1
    sec('2  閱讀須知')
    for i, t in enumerate(cfg.get('reading_notes', []), 1):
        rows.append({'r': r, 'cells': [{'c': 2, 'v': i, 's': S_NUM}, {'c': 3, 'v': t, 's': S_V, 'cs': 4}]}); r += 1
    r += 1
    sec('3  工作表目錄（點名稱跳轉）')
    rows.append({'r': r, 'cells': [{'c': 2, 'v': h, 's': S_TH} for h in ('工作表', '用途', '一列代表', '列數', '欄數', '來源表')] and
                 [{'c': 2 + i, 'v': h, 's': S_TH} for i, h in enumerate(('工作表', '用途', '一列代表', '列數', '欄數', '來源表'))]}); r += 1
    for e in entries:
        rows.append({'r': r, 'cells': [{'c': 2, 'v': e['name'], 's': S_LINK, 'l': {'s': e['id'], 'r': None}}, {'c': 3, 'v': e.get('desc', ''), 's': S_V},
                                       {'c': 4, 'v': e.get('row_unit', ''), 's': S_V}, {'c': 5, 'v': e.get('rows'), 's': S_NUM}, {'c': 6, 'v': e.get('cols'), 's': S_NUM},
                                       {'c': 7, 'v': e.get('sources', ''), 's': S_V}]}); r += 1
    r += 1
    sec('4  各表閱讀註記')
    for e in entries:
        for n_ in e.get('_notes', []):
            rows.append({'r': r, 'cells': [{'c': 2, 'v': e['name'], 's': S_LINK, 'l': {'s': e['id'], 'r': None}}, {'c': 3, 'v': n_, 's': S_V, 'cs': 5}]}); r += 1
    return {'id': '00', 'name': '00_說明', 'mode': 'grid', 'title': title, 'notes': [], 'subtitle': sub,
            'col_widths': [90, 240, 420, 200, 70, 70, 260], 'max_row': r, 'max_col': 7, 'rows': rows, 'styles': st,
            'sections': sections, 'hidden_cols': [], 'hidden_rows': [], 'gridlines': False, 'freeze_rows': 0, 'freeze_cols': 0}


def grid_01(cfg, title, num_of):
    st = []
    def style(**kw):
        st.append(kw); return len(st) - 1
    S_TITLE = style(b=1, fc='#1F4E79', sz=20); S_H = style(b=1, bg='#1F4E79', fc='#FFFFFF', sz=11); S_K = style(b=1, fc='#1F4E79')
    S_V = style(wrap=1); S_TH = style(b=1, bg='#DDEBF7'); S_LINK = style(u=1, fc='#0563C1'); S_NUM = style(ha='right')
    SEV = {'高': style(b=1, bg='#F8CBAD', ha='center'), '中': style(b=1, bg='#FFE699', ha='center'), '低': style(bg='#E2EFDA', ha='center'), '資訊': style(bg='#F2F2F2', ha='center')}
    rows = []; sections = []; r = 1
    rows.append({'r': r, 'h': 40, 'cells': [{'c': 1, 'v': '⌂ 目錄', 's': S_LINK, 'l': {'s': '00', 'r': 1}}, {'c': 2, 'v': title + '：重點發現', 's': S_TITLE, 'cs': 4}]}); r += 2
    sections.append({'r': r, 'label': 'KPI'})
    rows.append({'r': r, 'h': 26, 'cells': [{'c': 1, 'v': '關鍵數字', 's': S_H, 'cs': 5}]}); r += 1
    for k, v in cfg.get('kpis', []):
        rows.append({'r': r, 'cells': [{'c': 2, 'v': k, 's': S_K}, {'c': 3, 'v': v, 's': S_V, 'cs': 3}]}); r += 1
    r += 1
    sections.append({'r': r, 'label': '重點發現'})
    rows.append({'r': r, 'h': 26, 'cells': [{'c': 1, 'v': '重點發現（依嚴重度）', 's': S_H, 'cs': 5}]}); r += 1
    rows.append({'r': r, 'cells': [{'c': 2, 'v': '嚴重度', 's': S_TH}, {'c': 3, 'v': '發現', 's': S_TH}, {'c': 4, 'v': '證據', 's': S_TH}, {'c': 5, 'v': '工作表', 's': S_TH}]}); r += 1
    def sheet_cell(txt):
        m = re.match(r'\s*(\d{2})_(\S+)', str(txt))
        if m and m.group(1) in num_of.values():
            return {'c': 5, 'v': txt, 's': S_LINK, 'l': {'s': m.group(1), 'r': None}}
        return {'c': 5, 'v': txt, 's': S_V}
    for f in cfg.get('top_findings', []):
        rows.append({'r': r, 'cells': [{'c': 2, 'v': f.get('severity', ''), 's': SEV.get(f.get('severity'), S_V)}, {'c': 3, 'v': f.get('text', ''), 's': S_V},
                                       {'c': 4, 'v': f.get('evidence', ''), 's': S_V}, sheet_cell(f.get('sheet', ''))]}); r += 1
    r += 1
    sections.append({'r': r, 'label': '待決事項'})
    rows.append({'r': r, 'h': 26, 'cells': [{'c': 1, 'v': '待決事項（需廠方確認）', 's': S_H, 'cs': 5}]}); r += 1
    for i, q in enumerate(cfg.get('open_questions', []), 1):
        rows.append({'r': r, 'cells': [{'c': 2, 'v': i, 's': S_NUM}, {'c': 3, 'v': q, 's': S_V, 'cs': 3}]}); r += 1
    return {'id': '01', 'name': '01_摘要', 'mode': 'grid', 'title': title + '：重點發現', 'notes': [], 'subtitle': '',
            'col_widths': [90, 90, 520, 420, 220], 'max_row': r, 'max_col': 5, 'rows': rows, 'styles': st,
            'sections': sections, 'hidden_cols': [], 'hidden_rows': [], 'gridlines': False, 'freeze_rows': 0, 'freeze_cols': 0}


# ---------------------------------------------------------------- card spec
# 來源分級（CONTRACT.md「src 契約」）：raw 原始｜decoded 解碼｜inferred 推論｜doc 文件·設計｜factory 出廠
SRC_DEFS = {
    'raw': {'label': '原始', 'desc': '直接取 AMS 資料庫某一欄（可經 JOIN）'},
    'decoded': {'label': '解碼', 'desc': '以固定規則換算：時間、字串切段、二進位 int32/float32/UTF-16、FF hex、碼表'},
    'inferred': {'label': '推論', 'desc': '經驗規則、寫死的對照表、外部對照檔或機組範本推論（非資料庫/文件直接記載）'},
    'doc': {'label': '文件', 'desc': '設計文件（DCS 端子表、儀器清單、P&ID、Hook-up…）：「應該是什麼」'},
    'factory': {'label': '出廠', 'desc': '製造商出廠紀錄（EOMR 校正證書）：「出廠時是什麼」'},
}
SRC_PREFIX = {k: v['label'] for k, v in SRC_DEFS.items()}


def src(lvl, text):
    """欄位來源 {lvl, text}；text 形如「原始 · 表.欄」，可含 {cNN}（同一列第 NN 欄的值，由前端代入）。"""
    assert lvl in SRC_DEFS, lvl
    return {'lvl': lvl, 'text': f'{SRC_PREFIX[lvl]} · {text}'}


def summary_spec(ci3, ci13):
    """「一目了然」摘要（登入後查詢頁最上方）：ci3／ci13 = 欄名前綴 → 03_設備總表／設備參數統計 的欄索引。
    item 來源：col（03 欄）、stats（設備參數統計欄 {lo,hi,unit}）、kind+key(s)（card aux 工程文件區段的列名）、docindex（整段）。
    其餘完整資料（識別、位置、同步、變更、DCS 比對、文件比對、連結、參數現值）放在摘要之後的「完整資料」。"""
    T = lambda label, pre, lvl, text, **kw: dict({'label': label, 'col': ci3(pre), 'src': src(lvl, text)}, **kw)
    K = lambda label, kind, key, **kw: dict({'label': label, 'kind': kind, 'key': key}, **kw)
    return {
        'title': '一目了然',
        'more_title': '完整資料（識別與位號、設備、實體位置、關鍵組態、同步狀態、最後修改、DCS 比對、工程文件、快速連結、參數變更、參數現值）',
        'hero': {'tag': ci3('現行AMS位號'), 'alias': ci3(ALIAS), 'unit': ci3('機組說明'), 'mfr': ci3('製造商 ('), 'model': ci3('型號 ('), 'proto': ci3('協定+版本'),
                 'service': {'kind': 'instlist', 'key': '服務說明'}},
        'groups': [
            {'key': 'dev', 'label': '設備', 'items': [
                T('現行 AMS 位號 (KKS)', '現行AMS位號', 'decoded', 'ExtBlockTags.ExtBlockTag（BlockAsgms EventIdDayOut=49710，清除殘碼）', big=True),
                T('AMS 廠牌／型號', '製造商 (', 'raw', 'Manufacturers.Name + DeviceTypes.Name（Devices.AmsDevRevId → DeviceRevisions → DeviceTypes → MfrProtocols）', col=[ci3('製造商 ('), ci3('型號 (')], join=' '),
                K('設計廠牌（儀器清單）', 'instlist', '廠牌'),
                K('設計完整型號碼（儀器清單）', 'instlist', '完整型號碼'),
                T('AMS 協定＋版本', '協定+版本', 'decoded', 'DeviceProtocols.Name + Devices.ProtocolRevision'),
                K('出廠型號（EOMR）', 'eomr', '出廠型號'),
                K('銘牌序號（EOMR）', 'eomr', '銘牌序號'),
            ]},
            {'key': 'range', 'label': '量程、單位與警報／跳機設定值', 'items': [
                {'label': 'AMS 量程（現值）', 'stats': {'lo': ci13('LRV'), 'hi': ci13('URV'), 'unit': ci13('單位(解碼)')}, 'proto': 'HART', 'cmp': 'ams',
                 'src': src('decoded', 'BlockData {c16} float32 → HART 單位碼表 · 最後記錄 {c36}')},
                {'label': 'AMS FF XD_SCALE（現值）', 'stats': {'lo': ci13('FF XD_SCALE EU0'), 'hi': ci13('FF XD_SCALE EU100'), 'unit': ci13('FF XD_SCALE 單位')}, 'proto': 'FF', 'cmp': 'ams',
                 'src': src('decoded', 'BlockData 80020192 FF hex float32／單位碼（區塊 {c34}）')},
                K('DCS 量程（端子表）', 'terminal', 'DCS 量程 (DEVICE_LO/HI/UNITS)', cmp='terminal'),
                K('設計量程（儀器清單）', 'instlist', '設計量程（原文）', cmp='instlist'),
                K('出廠校正量程（EOMR）', 'eomr', '出廠校正量程（原文）', cmp='eomr'),
                K('警報／跳機設定值（儀器清單）', 'instlist', '警報/跳機設定值'),
                K('DCS 警報設定（端子表）', 'terminal', ['警報 1_HI', '警報 1_LO', '警報 2_HI', '警報 2_LO', '警報 3_HI', '警報 3_LO'], kv=True),
            ]},
            {'key': 'ctrl', 'label': '控制系統（DCS 端子表，設計文件）', 'kind': 'terminal', 'per_entry': True,
             'head': ['訊號名', '說明 DESC', '訊號等級', 'HART'],
             'items': ['系統', '控制器', '位置', '盤櫃 CABINET', 'Case', '卡位 COL_ROW', '點號 POINT', 'PACK_TYPE', '端子 TB_PT_1/2', 'P&ID', '邏輯圖'],
             'note': '端子表為設計文件（GE IO Signal Report），不代表 DCS 現行組態。'},
            {'key': 'draw', 'label': '圖面', 'items': [
                K('P&ID', 'terminal', 'P&ID', alt={'kind': 'instlist', 'key': 'P&ID'}),
                K('邏輯圖', 'terminal', '邏輯圖'),
                K('Hook-up 圖', 'instlist', 'Hook-up 圖'),
                K('位置圖', 'instlist', '位置圖'),
            ]},
            {'key': 'docs', 'label': '文件索引（PDF 頁碼）', 'kind': 'docindex', 'note': 'p.N 為 PDF 頁序；同編號只取最高版次。'},
        ],
    }


def card_spec(final, sheets_by_name, num_of, link_index, web_df):
    def ci(sheet_name, prefix):
        df = web_df.get(sheet_name, sheets_by_name[sheet_name]['df'])
        cols = [str(c) for c in df.columns]
        if prefix in cols:
            return cols.index(prefix)
        for i, c in enumerate(cols):
            if c.startswith(prefix):
                return i
        raise KeyError(f'{sheet_name}: {prefix}')
    T = lambda label, pre, lvl, text, **kw: dict({'label': label, 'col': ci('設備總表', pre), 'src': src(lvl, text)}, **kw)
    D = lambda label, pre, lvl, text: {'label': label, 'col': ci('設備總表', pre), 'raw': True, 'fmt': 'yyyy-mm-dd hh:mm:ss', 'src': src(lvl, text)}
    DL = 'Blocks(BlockIndex=0)→DeviceLocation'
    proto_col = ci('設備總表', '協定 (')
    sections = [
        {'label': '1. 識別與位號', 'fields': [
            T('現行 AMS 位號', '現行AMS位號', 'decoded', 'ExtBlockTags.ExtBlockTag（BlockAsgms EventIdDayOut=49710，清除殘碼）'),
            T('設備別名', ALIAS, 'inferred', '20260910_AMS解析.xlsx 設備別名（以 Devices.AmsDeviceId GUID 對照）'),
            T('設備鍵', '設備鍵', 'raw', 'Devices.DeviceKey'),
            T('識別時裝置位號', '識別時裝置位號', 'decoded', 'Devices.AmsDeviceTag（清除殘碼）'),
            T('現行位號品質', '現行位號品質', 'inferred', '位號品質規則（正規式分類：空白／殘碼／自動時間戳／正常）'),
            T('識別位號品質', '識別位號品質', 'inferred', '位號品質規則（Devices.AmsDeviceTag）'),
            T('位號關係（現行 vs 識別時）', 'AMS位號與識別位號關係', 'inferred', '現行位號與 Devices.AmsDeviceTag 字串比較（相同／後綴／改名）'),
            T('前一個 AMS 位號', '前一個AMS位號', 'decoded', 'BlockAsgms 已結束指派（EventIdDayOut≠49710）最後一筆 → ExtBlockTags'),
            T('位號指派次數', '位號指派次數', 'decoded', 'BlockAsgms 筆數（設備層 BlockKey）'),
            D('現行位號指派時間(台灣)', '現行位號指派時間', 'decoded', 'BlockAsgms.EventIdDayIn/FractionIn → UTC+8'),
            T('現行指派事件', '現行位號指派事件', 'raw', 'EventLog.Description（對上 BlockAsgms EventIdDayIn/FractionIn）', span=2),
            T('指派者', '指派者', 'raw', 'EventLog.UserKey → Users.UserName'),
            D('首次指派時間（自動識別）', '首次識別時間', 'decoded', 'BlockAsgms.EventIdDayIn 最早一筆 → UTC+8（多為 PS.AMS1SVR 自動識別寫入）'),
            T('機組', '機組 (', 'inferred', '位號切字（KKS 規則／前綴 G11/G12/S10/C10/C53）'),
            T('機組說明', '機組說明', 'inferred', '內建機組對照表 UNIT_ZH'),
            T('KKS 系統碼', 'KKS系統碼', 'decoded', '現行位號 KKS 切字（第 2 組）'),
            T('KKS 系統編號', 'KKS系統編號', 'decoded', '現行位號 KKS 切字（第 3 組）'),
            T('KKS 設備碼', 'KKS設備碼', 'decoded', '現行位號 KKS 切字（第 4 組）'),
            T('KKS 流水號', 'KKS流水號', 'decoded', '現行位號 KKS 切字（第 5 組）')]},
        {'label': '2. 設備', 'fields': [
            T('節點種類', '節點種類', 'inferred', 'DeviceLocation.AmsPath 末段 MUX_DEVICE／DeviceProtocols.Name'),
            T('協定＋版本', '協定+版本', 'decoded', 'DeviceProtocols.Name + Devices.ProtocolRevision'),
            T('製造商', '製造商 (', 'raw', 'Devices.AmsDevRevId → DeviceRevisions → DeviceTypes → MfrProtocols → Manufacturers.Name'),
            T('型號', '型號 (', 'raw', 'DeviceTypes.Name'),
            T('型號代碼', '型號代碼', 'raw', 'DeviceTypes.DeviceType'),
            T('設備版本', '設備版本 (', 'raw', 'DeviceRevisions.DeviceRevision'),
            T('主類別', '主類別', 'raw', 'DeviceCategories → MajorDeviceCategories.Name'),
            T('次類別', '次類別', 'raw', 'DeviceCategories → MinorDeviceCategories.Name'),
            T('裝置ID (HART Device ID)', '裝置ID', 'raw', 'Devices.Identifier（HART：Device ID＝HostPath 第 5 段末 6 碼，非銘牌序號；FF：裝置識別字串）',
              label_by={'col': proto_col, 'map': {'FF': '裝置ID (FF 裝置識別字串)'}, 'default': '裝置ID (HART Device ID)'}),
            T('設備 GUID', '設備GUID', 'decoded', 'Devices.AmsDeviceId（轉大寫）')]},
        {'label': '3. 實體位置', 'fields': [
            T('網路名稱', '網路名稱', 'raw', f'{DL}→NetworkInfo.NetworkName'),
            T('網路種類', '網路種類', 'raw', 'NetworkInfo.NetworkKindAsString'),
            T('MUX 位址', 'MUX位址', 'decoded', f'{DL}.AmsPath 第 4 段', proto='HART'),
            T('通道', '通道 (', 'decoded', f'{DL}.AmsPath 第 5 段', proto='HART'),
            T('COM 埠號', 'COM埠號', 'decoded', f'{DL}.HostPath 第 1 段', proto='HART'),
            T('HART 版本', 'HART版本', 'decoded', f'{DL}.HostPath 第 8 段', proto='HART'),
            T('MUX HART UID', 'MUX HART UID', 'decoded', f'{DL}.HostPath 第 4 段', proto='HART'),
            T('裝置 HART UID', '裝置 HART UID', 'decoded', f'{DL}.HostPath 第 5 段', proto='HART'),
            T('FF 連結設備', 'FF連結設備名稱', 'decoded', f'{DL}.AmsPath 第 4 段（6 段路徑）', proto='FF'),
            T('FF Link 編號', 'FF Link編號', 'decoded', f'{DL}.AmsPath 第 5 段 Link #n', proto='FF'),
            T('主機位號 (HostTag)', '主機位號', 'decoded', f'{DL}.HostTag（清除殘碼）'),
            T('識別狀態', '識別狀態', 'decoded', f'{DL}.IdentStatus → AmsUdf_DevBlkIdentStatusAsString'),
            T('AMS 路徑', 'AMS路徑', 'raw', f'{DL}.AmsPath', span=2),
            T('主機路徑', '主機路徑', 'raw', f'{DL}.HostPath', span=2),
            {'label': 'FF R/T/F 區塊數', 'col': [ci('設備總表', 'FF資源區塊數'), ci('設備總表', 'FF轉換區塊數'), ci('設備總表', 'FF功能區塊數')],
             'join': ' / ', 'prefixes': ['R', 'T', 'F'], 'blank_if_zero': True, 'proto': 'FF', 'src': src('decoded', 'Blocks.BlockType 依 R/T/F 計數（BlockIndex>0）')}]},
    ]
    links = [
        {'label': '→ 設備總表', 'sheet': '03', 'self': True},
        {'label': '→ 參數現值', 'param': {'sheet_col': ci('設備總表', '參數現值表'), 'row_col': ci('設備總表', '參數現值起始列'), 'count_col': ci('設備總表', '參數現值筆數')}, 'none': '→ 參數現值（無）', 'fmt': '→ 參數現值 {n} 筆'},
    ]
    for nm, lab in [('設備參數統計', '關鍵組態現值'), ('參數變更歷程', '參數變更'), ('事件總帳', '事件'), ('位號指派歷程', '位號指派歷程'), ('FF區塊清單', 'FF 區塊'),
                    ('同步失敗統計', '同步失敗'), ('刪除裝置事件', '刪除裝置事件'), ('SnapOn裝置檔案資訊', 'SnapOn 檔案'), ('測試定義指派', '測試定義指派'), ('位號跨表對照', '位號跨表對照')]:
        if nm in sheets_by_name and ALIAS in sheets_by_name[nm]['df'].columns:
            links.append({'label': f'→ {lab}', 'sheet': num_of[nm], 'match_col': ci(nm, ALIAS), 'count_mode': 'eq', 'count_col': ci(nm, ALIAS), 'fmt': f'→ {lab} {{n}} 筆', 'none': f'→ {lab}（無）'})
    CAT_DCS = 'Change performed by foreign host'
    rc = {'title': '最近 10 筆參數變更（來源 參數變更歷程，k=1 最新）', 'sheet': num_of['參數變更歷程'], 'key_col': ci('參數變更歷程', '別名#序'), 'k_max': 10, 'noun': '參數變更', 'alias_col': ci('參數變更歷程', ALIAS),
          'columns': [{'label': '變更記錄時間(台灣)', 'col': ci('參數變更歷程', '變更記錄時間(台灣)'), 'fmt': 'yyyy-mm-dd hh:mm',
                       'src': src('decoded', 'EventLog.EventTime（新值那筆 BlockData 的 EventIdDay/Fraction）UTC → +8')},
                      {'label': '參數', 'col': ci('參數變更歷程', '參數 ('), 'src': src('decoded', 'BlockData.ParamName 基底 / item:member')},
                      {'label': '中文名稱', 'col': ci('參數變更歷程', '參數中文名稱'), 'src': src('inferred', '舊工作簿 20_參數字典（機器斷詞對照）')},
                      {'label': '組態類別', 'col': ci('參數變更歷程', '關鍵組態類別'), 'src': src('inferred', '關鍵語意規則 KEY_CONFIG（參數名 → 量程/單位/阻尼…）')},
                      {'label': '前值 → 新值', 'cols': [ci('參數變更歷程', '前值'), ci('參數變更歷程', '新值')], 'join': ' → ',
                       'src': src('decoded', 'BlockData 同 (BlockKey, ParamName) 相鄰兩筆 ValueMode=h 值（依 ParamDataType：int32/float32/OLE 日期/UTF-16LE；FF hex）')},
                      {'label': '類別', 'col': ci('參數變更歷程', '事件分類'), 'map': {CAT_DCS: 'DCS·外部主機', 'Change performed by AMS Device Manager': '人工 AMS'}, 'warn_eq': CAT_DCS,
                       'title': 'EventLog.Category → EventCategories：Cat 28「Change performed by foreign host」＝DCS／外部主機寫入；其他＝AMS 人工',
                       'src': src('raw', 'EventLog.Category → EventCategories.Description（Cat 28＝DCS·外部主機，其他＝人工 AMS）')},
                      {'label': '事件', 'col': ci('參數變更歷程', '事件說明'), 'src': src('raw', 'EventLog.Description')},
                      {'label': '使用者', 'col': ci('參數變更歷程', '使用者 ('), 'src': src('raw', 'EventLog.UserKey → Users.UserName')}]}
    rules = [
        {'when': {'col': ci('設備總表', '識別狀態碼'), 'eq': '0'}, 'targets': [ci('設備總表', '識別狀態')], 'style': {'fc': '#9C0006', 'bg': '#FFC7CE'}},
        {'when': {'col': ci('設備總表', '現行位號品質'), 'ne': '正常'}, 'targets': [ci('設備總表', '現行位號品質')], 'style': {'bg': '#FCE4D6'}},
        {'when': {'count_gt': 1}, 'targets': ['count'], 'style': {'b': 1, 'fc': '#C00000'}},
    ]
    S = lambda label, pre, lvl, text, **kw: dict({'label': label, 'col': ci('設備參數統計', pre), 'src': src(lvl, text)}, **kw)
    stats_fields = [
        S('參數數', '參數數', 'decoded', 'BlockData 參數基底數（每參數最新一筆）'),
        S('變更次數', '變更次數', 'decoded', 'BlockData 同參數相鄰 ValueMode=h 值不同的次數'),
        S('LRV 量程下限', 'LRV', 'decoded', 'BlockData（{c16} 對應下限參數）float32 · 最後記錄 {c36}', cmp='ams_lo', flt=True, proto='HART'),
        S('URV 量程上限', 'URV', 'decoded', 'BlockData {c16} float32 · 最後記錄 {c36}', cmp='ams_hi', flt=True, proto='HART'),
        S('量程參數', '量程參數', 'decoded', 'BlockData.ParamName 基底（KEY_CONFIG 候選字母序第一個）', proto='HART'),
        S('單位', '單位(解碼)', 'decoded', 'BlockData {c19}={c17} → HART 單位碼表', cmp='ams_unit', proto='HART'),
        S('阻尼 (s)', '阻尼(s)', 'decoded', 'BlockData {c21} float32', flt=True, proto='HART'),
        S('寫入保護', '寫入保護', 'decoded', 'BlockData write_protect={c25} → 碼表', proto='HART'),
        S('轉換函數', '轉換函數', 'decoded', 'BlockData transfer_function={c27} → 碼表', proto='HART'),
        S('輪詢位址', '輪詢位址', 'decoded', 'BlockData polling_address int32', proto='HART'),
        S('銘牌序號', '最終組裝號', 'decoded', 'BlockData final_assembly_number int32（Rosemount＝銘牌序號後 7 碼；0＝未寫入）', serial=True, proto='HART'),
        S('描述 (descriptor)', '描述 (', 'decoded', 'BlockData descriptor UTF-16LE', proto='HART'),
        S('訊息 (message)', '訊息 (', 'decoded', 'BlockData message UTF-16LE', proto='HART'),
        S('HART 日期', 'HART 日期', 'decoded', 'BlockData date OLE 日期', proto='HART'),
        S('FF XD_SCALE EU0', 'FF XD_SCALE EU0', 'decoded', 'BlockData 80020192:02 FF hex float32（區塊 {c34}）', flt=True, proto='FF'),
        S('FF XD_SCALE EU100', 'FF XD_SCALE EU100', 'decoded', 'BlockData 80020192:01 FF hex float32（區塊 {c34}）', flt=True, proto='FF'),
        S('FF XD_SCALE 單位', 'FF XD_SCALE 單位', 'decoded', 'BlockData 80020192:03 FF 單位碼 → 碼表（區塊 {c34}）', proto='FF'),
        S('首次記錄(台灣)', '首次記錄', 'decoded', 'BlockData 最早 EventIdDay/Fraction → UTC+8'),
        S('最後記錄(台灣)', '最後記錄', 'decoded', 'BlockData 最新 EventIdDay/Fraction → UTC+8'),
        S('最後事件說明', '最後事件說明', 'raw', 'EventLog.Description（最後記錄事件）'),
        S('最後使用者', '最後使用者', 'raw', 'EventLog.UserKey → Users.UserName（最後記錄事件）'),
    ]
    sections_aux = [
        {'key': 'sync', 'label': '維護狀態（AMS 同步）', 'empty': '（無同步紀錄）'},
        {'key': 'change', 'label': '最後修改（人工 AMS／DCS·外部主機寫入）', 'empty': '（排除動態值後，無參數修改紀錄）',
         'note': '依 BlockData 相鄰值不同判定；排除 pv_value、OperatingHours 等動態/計數值與 7 位有效數字相同的浮點殘差，故可能與 14_參數變更歷程 略有不同。Cat 28「Change performed by foreign host」＝DCS／外部主機寫入。'},
        {'key': 'compare', 'label': 'DCS 比對（量程；以 DCS 為主）', 'empty': '（無 DCS 基準：DCS 端子表查無此位號，AMS 事件也無 Cat28 量程寫入）',
         'note': '基準＝AMS 事件中最新一次 Cat28 外部主機寫入的量程（標「DCS 寫入 (AMS 事件)」；只寫入上限或下限時只比較該端，另一端顯示值僅供參考），否則 DCS 端子表 DEVICE_LO/HI。其他來源與基準差超過 ±0.5% span 標「⚠ 與 DCS 不符」；單位先換算，量綱不同或明確絕壓↔表壓標「單位不同未比較」，任一邊單位空白、無法辨識或僅為推定標「單位不明未比較」。端子表為設計文件，非 DCS 現行組態。'},
        {'key': 'ff', 'label': 'FF 診斷（僅 FF 設備）', 'only_ff': True, 'empty': '（此 FF 設備在 AMS 無 FF 參數紀錄）', 'note': 'WRITE_LOCK 依 FF 規範 1＝未鎖定、2＝鎖定。'},
        {'key': 'terminal', 'label': '控制系統（DCS 端子表，設計文件）', 'kind': 'terminal', 'note': '端子表為設計文件（GE IO Signal Report），不代表 DCS 現行組態。'},
        {'key': 'instlist', 'label': '設計規格（儀器清單）', 'kind': 'instlist'},
        {'key': 'eomr', 'label': '出廠紀錄（EOMR 校正證書）', 'kind': 'eomr', 'note': '目前只解析 Rosemount/Emerson 格式證書；銘牌序號後 7 碼與 AMS final_assembly_number 比對。'},
        {'key': 'docindex', 'label': '文件索引（PDF 頁碼）', 'kind': 'docindex', 'note': 'PDF 文字層逐頁比對；p.N 為 PDF 頁序。R2/R3 為 GE/ST 不分機組編號（同編號各機組共用此頁）。'},
        {'key': 'ident', 'label': '位號歷程補充（刪除重建／方法執行）', 'empty': '（無刪除重建或方法執行紀錄）'},
        {'key': 'alarm', 'label': '類比輸出警報與飽和電流', 'empty': '（無警報／飽和電流參數）'},
        {'key': 'device', 'label': '設備補充（銘牌序號／版次）', 'empty': '（無參數紀錄）'},
    ]
    return {
        'id': '02', 'name': '02_設備查詢卡', 'mode': 'card', 'title': '設備查詢',
        'summary': summary_spec(lambda p: ci('設備總表', p), lambda p: ci('設備參數統計', p)),
        'notes': ['輸入目前/舊 AMS 位號、識別時位號、HostTag、裝置ID、設備鍵、設備 GUID 或別名（大小寫不拘），按 Enter。字串經 04_位號索引 換成別名，再從 03_設備總表、設備參數統計、參數變更歷程、AMS DB 補充與工程文件比對（card aux）取值。',
                  '「來源：隱藏｜徽章｜完整」切換每個欄位的資料來源：原始（灰）＝DB 欄、解碼（藍）＝固定規則換算、推論（橙）＝經驗規則/對照表、文件（綠）＝設計文件、出廠（深綠）＝EOMR。'],
        'default_query': final.get('default_query', 'G12HAP70BT001'),
        'input': {'label': '查詢位號', 'prompt': '位號／舊位號／識別時位號／HostTag／裝置ID／設備鍵／別名', 'suggest': {'sheet': '04', 'col': 0, 'hint_cols': [2, 4]}},
        'lookup': {'index_sheet': '04', 'key_col': 0, 'src_col': 2, 'alias_col': 4, 'count_col': 7, 'target_sheet': '03', 'target_alias_col': 1, 'target_tag_col': 0,
                   'normalize': "remove '=' ; collapse spaces ; trim ; upper",
                   'msg': {'empty': '請輸入位號…', 'notfound': '查無此字串：請到『04_位號索引』搜尋部分字串', 'found': '來源：{src}［鍵 {key}］',
                           'no_device': '（無對應設備）', 'device': ' → 目前位號 {tag}', 'multi': '只顯示優先序最高的一台'},
                   'labels': {'alias': '設備別名 alias', 'count': '此字串對應設備數'}},
        'sections': sections,
        'links_title': '快速連結（附筆數；點擊跳到該表並篩選此設備）', 'links': links,
        'recent_changes': rc, 'rules': rules, 'link_index': link_index,
        'home_link': {'t': '⌂ 目錄', 'l': {'s': '00', 'r': 1}},
        'src_defs': SRC_DEFS, 'src_default': {'wide': 'full', 'narrow': 'badge', 'breakpoint': 640},
        'protocol_col': proto_col,
        'stats': {'title': '4. 關鍵組態現值（設備參數統計：量程／單位／阻尼／寫入保護…）', 'sheet': num_of['設備參數統計'], 'alias_col': ci('設備參數統計', ALIAS),
                  'fields': stats_fields},
        'aux': {'index': 'card/index.json', 'number_from': 5},
        'sections_aux': sections_aux,
    }


def data_build(outdir, manifest):
    """資料建置雜湊：sheets/*.json＋card/*.json＋不含 build 的 manifest（決定性）。無 card/ 時與舊算法相同。"""
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(outdir, 'sheets', '*.json'))) + sorted(glob.glob(os.path.join(outdir, 'card', '*.json'))):
        rel = os.path.relpath(p, outdir).replace('\\', '/')
        name = os.path.basename(p) if rel.startswith('sheets/') else rel
        h.update(name.encode('utf-8') + b'\0'); h.update(open(p, 'rb').read())
    man = {k: v for k, v in manifest.items() if k != 'build'}
    h.update(json.dumps(man, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    return h.hexdigest()[:10]


# ---------------------------------------------------------------- main
def main(pkl, outdir):
    final = pickle.load(open(pkl, 'rb'))
    cfg = final['cfg']; title = final['title']
    ordered = final['ordered']
    sheets_by_name = {s['name']: s for _, s in ordered}
    num_of = {s['name']: num for num, s in ordered}
    for p in glob.glob(os.path.join(outdir, 'sheets', '*.json')):
        os.remove(p)
    os.makedirs(os.path.join(outdir, 'sheets'), exist_ok=True)
    manifest_sheets = []
    entries = []
    # link_index for the card: alias -> {sheetId: [firstRow, count]}
    link_index = {}
    def add_link_index(sid, df):
        if ALIAS not in df.columns:
            return
        a = df[ALIAS].fillna('').astype(str).values
        first = {}; cnt = {}
        for i, v in enumerate(a):
            if not v: continue
            if v not in first: first[v] = i
            cnt[v] = cnt.get(v, 0) + 1
        for v in first:
            link_index.setdefault(v, {})[sid] = [first[v], cnt[v]]

    excluded = []
    web_df = {}
    for number, s in ordered:
        df = s['df']; name = s['name']; sid = number
        if name in WEB_EXCLUDE:
            excluded.append((f'{number}_{name}', len(df), s.get('purpose', '')))
            print(f'{sid} {name}: excluded from the web ({len(df)} rows; Excel 明細 only)', flush=True)
            continue
        drop = [c for c in WEB_DROP_COLS.get(name, []) if c in df.columns]
        if drop:
            df = df.drop(columns=drop)
        web_df[name] = df
        group = '字典' if name in DICT_SHEETS else GROUP_OF.get(s.get('module'), '其他')
        key_col = ALIAS if ALIAS in df.columns else None
        est_bytes = len(df) * (len(df.columns) * 14 + 4) if len(df) else 0
        files = []; total = 0
        if est_bytes > MAX_PART_BYTES and key_col:
            parts = chunk_table(sid, df, key_col)
            offsets = []
            for k, (off, sub) in enumerate(parts):
                j = table_json(sid, name, s, sub, number, total=len(df))
                j['part'] = {'index': k, 'of': len(parts), 'row_offset': off}
                fn = f'sheets/{sid}-{k:03d}.json'
                total += write(os.path.join(outdir, fn), j); files.append(fn); offsets.append(off)
            entry = {'part_offsets': offsets}
        else:
            j = table_json(sid, name, s, df, number)
            fn = f'sheets/{sid}.json'
            total += write(os.path.join(outdir, fn), j); files.append(fn)
            entry = {}
        add_link_index(sid, df)
        entry.update({'id': sid, 'name': f'{number}_{name}', 'short': name, 'group': group, 'mode': 'table', 'rows': len(df), 'cols': len(df.columns),
                      'files': files, 'bytes': total, 'desc': s.get('purpose', ''), 'row_unit': s.get('one_row', ''), 'sources': ', '.join(s.get('source_tables', [])),
                      'toc_rows': len(df), 'tab_color': TAB.get(group, '#404040'), 'data_first_row': 4})
        entry['_notes'] = [str(x) for x in (s.get('notes') or [])]
        manifest_sheets.append(entry)
        print(f'{sid} {name}: {len(df)} rows, {len(files)} file(s), {total // 1024} KB', flush=True)

    # card + grids
    card = card_spec(final, sheets_by_name, num_of, link_index, web_df)
    b02 = write(os.path.join(outdir, 'sheets/02.json'), card)
    sub = f'資料來源 20260912.ams_bckup（SQL Server 備份，AmsDb）｜105 表 1,170,089 列 → 本站 {len(manifest_sheets) + 3} 頁'
    cfg = dict(cfg)
    cfg['sources'] = list(cfg.get('sources', [])) + [['未收錄於網站', '；'.join(f'{n}（{r:,} 列）' for n, r, _ in excluded) + '：只在 Excel 明細活頁簿 20260912_AMS資料庫解析_明細.xlsx；參數現值/事件總帳的少數技術欄（UTC 文字、原始型別碼、ParamName 原文等）亦只在 Excel']]
    head_toc = [
        {'id': '00', 'name': '00_說明', 'desc': '來源、閱讀須知、工作表目錄與各表註記', 'row_unit': '版面', 'rows': None, 'cols': None, 'sources': ''},
        {'id': '01', 'name': '01_摘要', 'desc': '關鍵數字、重點發現（依嚴重度）、待決事項', 'row_unit': '版面', 'rows': None, 'cols': None, 'sources': ''},
        {'id': '02', 'name': '02_設備查詢卡', 'desc': '輸入任何位號字串（目前/舊位號、識別時位號、HostTag、裝置ID、設備鍵、GUID、別名）即顯示單台設備：識別、位置、關鍵組態、同步狀態、DCS 比對、工程文件（端子表／儀器清單／EOMR／文件索引）、最近變更與連結；每欄附資料來源', 'row_unit': '版面（查詢卡）', 'rows': None, 'cols': None, 'sources': '04、03、設備參數統計、參數變更歷程、card aux'},
    ]
    entries_public = head_toc + [{k: v for k, v in e.items()} for e in manifest_sheets]
    g00 = grid_00(cfg, entries_public, title, sub)
    g01 = grid_01(cfg, title, num_of)
    b00 = write(os.path.join(outdir, 'sheets/00.json'), g00)
    b01 = write(os.path.join(outdir, 'sheets/01.json'), g01)
    for e in manifest_sheets:
        e.pop('_notes', None)
    head = [
        {'id': '00', 'name': '00_說明', 'short': '說明', 'group': '總覽', 'mode': 'grid', 'rows': g00['max_row'], 'cols': 7, 'files': ['sheets/00.json'], 'bytes': b00,
         'desc': '來源、閱讀須知、工作表目錄與各表註記', 'row_unit': '版面', 'sources': 'order.json', 'toc_rows': g00['max_row'], 'tab_color': TAB['總覽']},
        {'id': '01', 'name': '01_摘要', 'short': '摘要', 'group': '總覽', 'mode': 'grid', 'rows': g01['max_row'], 'cols': 5, 'files': ['sheets/01.json'], 'bytes': b01,
         'desc': '關鍵數字、重點發現（依嚴重度）、待決事項', 'row_unit': '版面', 'sources': '多代理解讀與稽核結果', 'toc_rows': g01['max_row'], 'tab_color': TAB['總覽']},
        {'id': '02', 'name': '02_設備查詢卡', 'short': '設備查詢卡', 'group': '總覽', 'mode': 'card', 'rows': 0, 'cols': 0, 'files': ['sheets/02.json'], 'bytes': b02,
         'desc': '輸入任何位號字串即顯示單台設備：識別、位置、關鍵組態、最近變更、事件與連結', 'row_unit': '版面（查詢卡）', 'sources': '04、03、設備參數統計、參數變更歷程', 'toc_rows': 0, 'tab_color': TAB['總覽']},
    ]
    manifest = {
        'workbook': {'title': title, 'subtitle': sub, 'summary_title': title + '：重點發現', 'summary_subtitle': sub,
                     'source': '20260912.ams_bckup', 'built': cfg.get('built', ''), 'xlsx': '20260912_AMS資料庫解析.xlsx',
                     'related': [{'label': '20260910 匯出檔解析（前一版網站）', 'href': '../'}]},
        'groups': GROUPS,
        'sheets': head + manifest_sheets,
        'search': {'index_sheet': '04', 'key_col': 0, 'alias_col': 4, 'count_col': 7, 'src_col': 2, 'tag_col': 3},
        'default_sheet': '00',
        'landing': 'card',  # 沒有網址片段時直接開設備查詢（登入後即查詢頁）
    }
    aux_card = {'index': 'card/index.json', 'desc': '02_設備查詢卡附加資料：AMS DB 補充（同步、最後修改/DCS 寫入、FF 診斷、版次、警報）與工程文件比對（DCS 端子表、儀器清單、EOMR、文件索引）＋DCS 基準量程比對；依 alias 分塊按需載入。產生：tools/db/build_card_aux.py'}
    ix_path = os.path.join(outdir, 'card', 'index.json')
    if os.path.exists(ix_path):
        ix = json.load(open(ix_path, encoding='utf-8'))
        aux_card['parts'] = ix.get('parts')
        aux_card['bytes'] = sum(os.path.getsize(q) for q in glob.glob(os.path.join(outdir, 'card', '*.json')))
    manifest['aux'] = {'card': aux_card}
    # build hash (content based; includes card/*.json when present)
    manifest['build'] = data_build(outdir, manifest)
    write(os.path.join(outdir, 'manifest.json'), manifest)
    print('manifest sheets:', len(manifest['sheets']), 'build', manifest['build'])
    return manifest


def stamp(docs_db, assets_dir):
    """Version-stamp docs/db/index.html (assets live in ../assets) and write docs/db/version.json."""
    man = json.load(open(os.path.join(docs_db, 'data', 'manifest.json'), encoding='utf-8'))
    build = man['build']
    fh = {}
    for p in sorted(glob.glob(os.path.join(assets_dir, '*.js')) + glob.glob(os.path.join(assets_dir, '*.css'))):
        fh[os.path.basename(p)] = hashlib.sha256(open(p, 'rb').read()).hexdigest()[:10]
    app = hashlib.sha256(''.join('%s=%s;' % kv for kv in sorted(fh.items())).encode('utf-8')).hexdigest()[:10]
    ix = os.path.join(docs_db, 'index.html')
    html = open(ix, encoding='utf-8').read()
    def ref(m):
        name = m.group(2)
        return m.group(1) + '../assets/' + name + ('?v=' + fh[name] if name in fh else '') + m.group(4)
    html = re.sub(r'((?:src|href)=")\.\./assets/([\w.-]+\.(?:js|css))(\?v=[0-9a-zA-Z]*)?(")', ref, html)
    html = re.sub(r'<meta name="ams-build"[^>]*>', '<meta name="ams-build" content="%s" data-app="%s" data-chart="%s">' % (build, app, fh.get('chart.umd.min.js', '')), html)
    html = re.sub(r'(<link rel="preload" href=")data/manifest\.json(\?v=[0-9a-zA-Z]*)?(")', r'\g<1>data/manifest.json?v=%s\g<3>' % build, html)
    open(ix, 'w', encoding='utf-8', newline='\n').write(html)
    open(os.path.join(docs_db, 'version.json'), 'w', encoding='utf-8', newline='\n').write(json.dumps({'build': build, 'app': app}, separators=(',', ':')))
    print('stamped', build, app)


if __name__ == '__main__':
    pkl, outdir = sys.argv[1], sys.argv[2]
    main(pkl, outdir)
    docs_db = os.path.dirname(os.path.abspath(outdir))
    stamp(docs_db, os.path.join(os.path.dirname(docs_db), 'assets'))
