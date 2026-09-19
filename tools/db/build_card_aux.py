# -*- coding: utf-8 -*-
"""02_設備查詢卡 附加資料（card aux）：合併 AMS DB 補充與工程文件比對結果，依 alias 分塊輸出給前端按需載入。

Usage:  py tools/db/build_card_aux.py <cardwork_dir> docs/db/data [--chunk-kb 300] [--no-stamp]

輸入（<cardwork_dir>，各產生器輸出；不在 repo 內）：
  ams.json       ← tools/db/card_ams_extra.py      （AMS DB：同步、最後修改/DCS 寫入、位號歷程、設備補充、警報、FF 診斷）
  terminal.json  ← tools/db/docmap_terminal.py     （DCS 端子表 HTx-1-IMI01-A0001 IO_Signal）
  instlist.json  ← tools/db/docmap_instlist.py     （儀器清單 BOP/HRSG/GT/ST）
  eomr.json      ← tools/db/docmap_eomr.py         （出廠校正證書 EOMR）
  docindex.json  ← tools/db/docmap_docindex.py     （PDF 文件索引：P&ID、Hook-up、規格表…的頁碼）
另讀 docs/db/data/sheets/03.json（alias 列序）與 13.json（AMS 量程現值，DCS 基準比對用）。

輸出（CONTRACT.md「card aux」）：
  docs/db/data/card/index.json   {version, parts, alias:{alias: 塊號}, src_defs, searched:{kind:[...]}, docs:{key:{...}}, stats}
  docs/db/data/card/aux-NN.json  {part, by_alias:{alias:{sec:{...}, compare:[...], flags:{...}}}}
並重算 manifest.build（含 card/*.json）後重新 stamp docs/db/index.html（tools/db/extract_db.py 的 stamp）。

DCS 基準比對（compare）：量程上/下限的基準＝AMS 事件中該參數最新一次「值有改變」的 Cat28 外部主機寫入（dcs_writes URV/LRV），
沒有則取 DCS 端子表 DEVICE_LO/HI。AMS 現值（13 表 LRV/URV/單位）、DCS 端子表（基準為 DCS 寫入時）、儀器清單、EOMR 逐一比對：
容許 ±0.5% span；單位先換算（°C/°F/K、Pa/kPa/MPa/mbar/bar/psi/mmH2O/inH2O/inHg/mmHg、mm/cm/m/in、%），無法換算 → unit_mismatch。
決定性輸出（無時間戳）；不寫入任何本機絕對路徑（最後以 regex 自檢）。
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
}
KIND_LABEL = {'terminal': 'DCS 端子表', 'instlist': '儀器清單', 'eomr': '出廠證書 EOMR', 'docindex': '文件索引'}
DOC_CAT_ORDER = ['P&ID', 'Hook-up', '規格表', '就地錶規格', '接線圖', '電纜表', '保護箱', '位置圖', '邏輯圖', 'GT I/O 清單']
ABS_PATH_RE = re.compile(r'[A-Za-z]:[\\/]|\\Users\\|/Users/|我的雲端硬碟')


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
    s = s.replace('°', 'deg').replace('º', 'deg').replace('³', '3').replace('²', '2')
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
        if low == core + 'g' and core not in ('mmh2o', 'inh2o', 'inhg', 'mmhg'):
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
    status：ok｜mismatch｜unit_mismatch（兩邊單位都明確但量綱不同/絕壓↔表壓）｜unit_unknown（任一邊單位空白、無法辨識或僅為推定）。
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
    return 'ok', note + '一致（容許 ±0.5% span）', lo, hi


def unit_of_code_str(s):
    """dcs_writes UNIT '12 (kPa)' → 'kPa'。"""
    if not s:
        return None
    m = re.search(r'\(([^()]+)\)\s*$', str(s))
    return m.group(1) if m else str(s)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cardwork')
    ap.add_argument('outdir')
    ap.add_argument('--chunk-kb', type=int, default=300)
    ap.add_argument('--no-stamp', action='store_true')
    a = ap.parse_args()
    cw, outdir = a.cardwork, a.outdir
    import extract_db, encrypt_data
    if encrypt_data.is_encrypted(outdir):  # 已發布的加密資料：先原地解密（結尾會重新加密）
        encrypt_data.decrypt_dir(outdir, encrypt_data.passphrase_and_salt(persist=False)[0])
    for q in glob.glob(os.path.join(outdir, 'card', '*.bin')):
        os.remove(q)
    ams = load(os.path.join(cw, 'ams.json'))
    kinds = {k: load(os.path.join(cw, k + '.json')) for k in ('terminal', 'instlist', 'eomr', 'docindex')}
    s03 = load(os.path.join(outdir, 'sheets', '03.json'))
    s13 = load(os.path.join(outdir, 'sheets', '13.json'))
    aliases = [r[1] for r in s03['rows']]
    proto = {r[1]: r[21] for r in s03['rows']}
    r13 = {r[40]: r for r in s13['rows']}
    docs = build_docs_map(kinds)

    def dkey(kind, e):
        k = '%s|%s|%s' % (kind, e['doc_id'], e.get('rev') or '')
        return k if k in docs else None

    stats = {'devices': len(aliases), 'with_compare': 0, 'compare_status': {}, 'baseline': {'dcs_write': 0, 'terminal': 0},
             'sections': {}}
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
        cmp_mark = {}  # kind -> status（量程欄位旁加 ⚠ 用）

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
                cands.append((0 if f.get('序號與 AMS 相符') == '是' else 1, len(cands), {
                    'lo': num(f['出廠量程下限_num']), 'hi': num(f['出廠量程上限_num']), 'unit': f.get('量程單位') or '', 'src': ent['src'],
                    'lvl': lvl, 'kind': 'eomr', 'ent': ent, 'field': '出廠校正量程（原文）',
                    'pre_note': '' if f.get('序號與 AMS 相符') == '是' else '證書序號與 AMS 不符；'}))
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

        # ---- DCS 基準比對（量程）
        compare = []
        r = r13.get(al)
        ams_cur = None
        if r is not None and num(r[14]) is not None and num(r[15]) is not None:
            ams_cur = {'lo': num(r[14]), 'hi': num(r[15]), 'unit': r[18] or '', 'lvl': 'decoded', 'kind': 'ams',
                       'src': '解碼 · AMS 現值 BlockData %s float32 · 最後記錄 %s' % (r[16] or '?', (r[36] or '')[:16])}
        ams_unit_note = ''
        if r is not None and not (r[18] or '').strip() and r[17] not in (None, ''):
            ams_unit_note = '（AMS 單位碼 %s／參數 %s 未翻譯）' % (g7(num(r[17])) if num(r[17]) is not None else r[17], r[19] or '?')
        if ams_cur is not None:
            ams_cur['unit_note'] = ams_unit_note
        base = None
        if 'URV' in dw or 'LRV' in dw:
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
            if bounds:
                over = any(dw[k][6] for k in ('URV', 'LRV') if k in dw)
                notes = []
                if over:
                    notes.append('之後曾被 AMS 人工改寫')
                if bounds != {'lo', 'hi'}:
                    notes.append('%s無 DCS 寫入，顯示值僅供參考、不比較' % ('下限' if 'lo' not in bounds else '上限'))
                if not unit.strip():
                    notes.append('單位空白' + ams_unit_note)
                base = {'kind': 'dcs_write', 'lvl': 'decoded', 'lo': lo, 'hi': hi, 'unit': unit or '', 'bounds': bounds,
                        'unit_note': '' if 'UNIT' in dw else ams_unit_note,
                        'src': '解碼 · DCS 寫入 (AMS 事件 Cat28 Field change) · ' + '；'.join(parts),
                        'label': 'DCS 寫入 (AMS 事件)', 'note': '；'.join(notes)}
        if base is None and term_primary:
            base = {'kind': 'terminal', 'lvl': term_primary['lvl'], 'lo': term_primary['lo'], 'hi': term_primary['hi'],
                    'unit': term_primary['unit'], 'src': term_primary['src'], 'label': 'DCS 端子表 (DEVICE_LO/HI)', 'note': '',
                    'bounds': {'lo', 'hi'}}
        if base is not None:
            others = []
            cand = []
            if base['kind'] == 'dcs_write' and term_primary:
                cand.append(dict(term_primary, label='DCS 端子表 (DEVICE_LO/HI)'))
            if ams_cur:
                cand.append(dict(ams_cur, label='AMS 現值'))
            if il_primary:
                cand.append(dict(il_primary, label='儀器清單 設計量程'))
            if eo_primary:
                cand.append(dict(eo_primary, label='EOMR 出廠校正量程'))
            for c in cand:
                st, note, lo2, hi2 = compare_range(base, c)
                o = {'kind': c['kind'], 'label': c['label'], 'lvl': c['lvl'], 'src': c['src'], 'lo': c['lo'], 'hi': c['hi'], 'unit': c['unit'],
                     'status': st, 'note': (c.get('pre_note') or '') + note}
                others.append(o)
                cmp_mark[c['kind']] = st
                # 逐端標記（LRV／URV 欄位旁的 ⚠）：只標有列入比較的那一端，不符只標實際不符的那一端
                bad_sides = note.rsplit('不符（', 1)[-1] if st == 'mismatch' else ''
                for k, side in (('lo', '下限'), ('hi', '上限')):
                    if k in base['bounds']:
                        cmp_mark['%s_%s' % (c['kind'], k)] = ('mismatch' if side in bad_sides else 'ok') if st == 'mismatch' else st
                stats['compare_status'][st] = stats['compare_status'].get(st, 0) + 1
                ent = c.get('ent')
                if ent is not None and st != 'ok':  # 在文件 entry 的量程欄位旁標 ⚠
                    fld = c.get('field') or 'DCS 量程 (DEVICE_LO/HI/UNITS)'
                    for row in ent['rows']:
                        if row[0] == fld or (c['kind'] == 'terminal' and row[0].startswith('DCS 量程')):
                            row[2:] = [st]
            b = {k: base[k] for k in ('kind', 'label', 'lvl', 'src', 'lo', 'hi', 'unit', 'note')}
            b['bounds'] = sorted(base['bounds'])
            compare.append({'item': '量程', 'baseline': b, 'others': others})
            stats['with_compare'] += 1
            stats['baseline'][base['kind']] += 1
        # 文件 entry 中量程欄位的 cmp 標記：未比較者去掉 kind 字串，只保留狀態
        for kk in ('terminal', 'instlist', 'eomr'):
            for ent in (sec.get(kk) or {}).get('entries', []):
                for row in ent['rows']:
                    if len(row) > 2 and row[2] not in ('ok', 'mismatch', 'unit_mismatch', 'unit_unknown', 'warn'):
                        del row[2:]
        if cmp_mark:
            flags['cmp'] = cmp_mark
        flags['ff'] = proto.get(al) == 'FF'
        for k in sec:
            stats['sections'][k] = stats['sections'].get(k, 0) + 1
        out[al] = {'sec': sec, 'compare': compare, 'flags': flags}

    # ---- 分塊
    card_dir = os.path.join(outdir, 'card')
    os.makedirs(card_dir, exist_ok=True)
    for p in glob.glob(os.path.join(card_dir, 'aux-*.json')):
        os.remove(p)
    limit = a.chunk_kb * 1024
    parts, cur, cur_b = [], {}, 0
    for al in aliases:
        b = len(dumps(out[al]).encode('utf-8')) + len(al) + 6
        if cur and cur_b + b > limit:
            parts.append(cur); cur, cur_b = {}, 0
        cur[al] = out[al]; cur_b += b
    if cur:
        parts.append(cur)
    width = max(2, len(str(len(parts) - 1)))
    alias_map, sizes = {}, []
    for k, p in enumerate(parts):
        fn = 'aux-%0*d.json' % (width, k)
        data = dumps({'part': k, 'by_alias': p}).encode('utf-8')
        if ABS_PATH_RE.search(data.decode('utf-8')):
            raise SystemExit('absolute local path found in ' + fn)
        open(os.path.join(card_dir, fn), 'wb').write(data)
        sizes.append(len(data))
        for al in p:
            alias_map[al] = k
    searched = {}
    for kind, j in kinds.items():
        keep = ('doc_id', 'rev', 'ref', 'title', 'folder', 'used', 'why') + (('category',) if kind == 'docindex' else ())
        searched[kind] = [{k: s.get(k) for k in keep if k in s} for s in j.get('searched', [])]
    src_stats = {k: {kk: vv for kk, vv in (j.get('stats') or {}).items() if kk in ('aliases_matched', 'rows', 'notes', 'per_category_aliases')} for k, j in kinds.items()}
    src_stats['ams'] = {'notes': (ams.get('stats') or {}).get('notes', []), 'backup_date': ams.get('backup_date')}
    index = {'version': 1, 'parts': len(parts), 'part_width': width, 'files': ['card/aux-%0*d.json' % (width, k) for k in range(len(parts))],
             'alias': alias_map, 'src_defs': SRC_DEFS, 'kind_label': KIND_LABEL, 'doc_cat_order': DOC_CAT_ORDER,
             'searched': searched, 'docs': docs, 'source_stats': src_stats, 'stats': stats,
             'compare_rule': ('DCS 基準＝AMS 事件中該參數最新一次值有改變的 Cat28 外部主機寫入（URV/LRV；只寫入一端時只比較該端，單位用 AMS 單位），'
                              '否則 DCS 端子表 DEVICE_LO/HI；容許 ±0.5% span；單位先換算，量綱不同或明確絕壓↔表壓標「單位不同未比較」，'
                              '任一邊單位空白/無法辨識/僅為推定標「單位不明未比較」')}
    idata = dumps(index)
    if ABS_PATH_RE.search(idata):
        raise SystemExit('absolute local path found in index.json')
    open(os.path.join(card_dir, 'index.json'), 'wb').write(idata.encode('utf-8'))
    print('card aux: %d aliases, %d parts, max %d KB, total %d KB, index %d KB' % (len(alias_map), len(parts), max(sizes) // 1024, sum(sizes) // 1024, len(idata.encode('utf-8')) // 1024))
    print(json.dumps(stats, ensure_ascii=False))

    # ---- manifest build（含 card/*.json）＋ 加密 ＋ stamp
    man_path = os.path.join(outdir, 'manifest.json')
    man = load(man_path)
    man.setdefault('aux', {})['card'] = dict(man.get('aux', {}).get('card') or {}, index='card/index.json', parts=len(parts),
                                            bytes=sum(sizes) + len(idata.encode('utf-8')))
    man['build'] = extract_db.data_build(outdir, man)
    open(man_path, 'wb').write(dumps(man).encode('utf-8'))
    print('manifest build', man['build'])
    encrypt_data.encrypt_dir(outdir, *encrypt_data.passphrase_and_salt())
    if not a.no_stamp:
        docs_db = os.path.dirname(os.path.abspath(outdir))
        extract_db.stamp(docs_db, os.path.join(os.path.dirname(docs_db), 'assets'))


if __name__ == '__main__':
    main()
