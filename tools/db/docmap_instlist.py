# -*- coding: utf-8 -*-
"""docmap_instlist.py — 儀器清單（Instrument List）對 AMS 設備 alias 的文件比對產生器。

用法：
  py tools/db/docmap_instlist.py --root <工程文件庫根目錄> --sheets docs/db/data/sheets --out <cardwork>/instlist.json

來源（xlsx/xls 取值；PDF 只列入 searched，不取值）：
  BOP  HT0-1-ILE01-A11xx-Attachment*.xlsx  （DB 工作表 21 欄）
  HRSG HT0-1-BLD01-A0002-Attachment.xls   （1.PIT…17.TE 分類工作表，數字量程依儲存格格式還原單位）
  GT   HT0-1-GLD01-A0102 End User Template xlsx（R1 RDS-PP 位號 / R2 GE No. / R4 G12 套 G11 範本）
  ST   HT0-1-TLD01-A0104-Attachment*.xlsx （R1 / R3 XX,YY 前綴）
  套裝設備清單（檔名含 Instrument List／儀器清單）：各資料夾皆僅 PDF → searched used=false。

版本選擇（以新版為主）：同文件編號的多份試算表，依
  1) 衍生/個人整理版排除（問題版、Bently 整理、統計結果、E+H 詳細資料…）
  2) 版次序（檔名版次、或內容「列版次」最大值；字母 < 數字）
  3) 同版次：內容非空儲存格較多者（副本 mtime 皆為雲端同步時間，差距僅分鐘，不代表編修先後）
  4) 再同：修改時間最新
輸出不含任何本機絕對路徑；文件以 doc_id + rev + 相對資料夾表示。
"""
import argparse, collections, datetime, json, os, re, sys, warnings

warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import openpyxl
import xlrd

DOCID_RE = re.compile(r'(HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4})')
CAND_RE = re.compile(r'ILE01-A11\d\d|BLD01-A0002|GLD01-A0102|TLD01-A0104|instrument\s*list|儀器清單|儀錶清單', re.I)
DEFAULT_FOLDERS = ['07_I&C', '09_BOP', '01_GT', '03_HRSG', '02_ST', '11_', '05_Condenser', '13_', '04_Generator', '91_']
DERIV_RE = re.compile(r'問題版|Bently|整理|統計|Attachmentf|所有傳送器詳細資料|採買|search for switch', re.I)
NEWER_PDF_NOTE = {
    'HT0-1-BLD01-A0002': ('同號較新版 HT0-1-BLD01-A0002-2 PDF（列版次 G，2026-01-20）僅PDF不取值；'
                          '其修訂紀錄 G = "Updated serial number for PIT list"（2025-12-24），值取自 Rev F xls'),
}
PLACEHOLDER_RE =re.compile(r'^\s*(-{1,3}|—|N\.?\s*A\.?|N/A|none)\s*$', re.I)


# ---------------------------------------------------------------- helpers
def rev_rank(r):
    r = (r or '').strip().upper()
    if not r or r == '-':
        return -1
    if r.isdigit():
        return 100 + int(r)
    if re.fullmatch(r'[A-Z]{1,2}', r):
        return sum((ord(ch) - 64) * (26 ** i) for i, ch in enumerate(reversed(r)))
    return -1


def file_rev(name):
    m = DOCID_RE.search(name)
    if not m:
        m2 = re.search(r'_rev([A-Z0-9]{1,2})\b', name, re.I)
        return m2.group(1).upper() if m2 else ''
    rest = name[m.end():]
    m2 = re.match(r'^[-_ ]+([A-Z0-9]{1,2})(?=[-_ .（(]|$)', rest)
    return m2.group(1) if m2 else ''


def clean(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).replace('\r', '')
    s = '\n'.join(re.sub(r'[ \t]+', ' ', ln).strip() for ln in s.split('\n'))
    s = re.sub(r'\n+', '\n', s).strip()
    s = re.sub(r'(?<=[\d\s])oC\b', '°C', s)
    s = s.replace('ºC', '°C').replace('℃', '°C')
    parts = s.split('\n')
    keep = [p for p in parts if not PLACEHOLDER_RE.match(p)]
    return ' / '.join(keep) if keep else parts[0]


def is_blank(s):
    return (not s) or bool(PLACEHOLDER_RE.match(s))


NUM = r'[-+]?\d[\d,]*(?:\.\d+)?'
RANGE_RE = re.compile(r'^\s*(' + NUM + r')\s*(?:to|~|～|－|–|-)\s*(' + NUM + r')\s*(.*)$', re.I)


def parse_range(txt):
    """回傳 (lo, hi, unit)；取第一段（'/' 或 '[' 之前）。無法解析回 None。"""
    if not txt:
        return None
    first = re.split(r'\s/\s|\[', txt)[0]
    m = RANGE_RE.match(first)
    if not m:
        return None
    try:
        lo = float(m.group(1).replace(',', ''))
        hi = float(m.group(2).replace(',', ''))
    except ValueError:
        return None
    unit = re.sub(r'±\s*' + NUM, '', m.group(3)).strip(' ,;:')
    unit = re.sub(r'\s+', ' ', unit)
    lo = int(lo) if lo.is_integer() else lo
    hi = int(hi) if hi.is_integer() else hi
    return lo, hi, unit


def xls_num_fmt(book, cell):
    """數字儲存格且格式字串含引號文字（"0~"#,##0" KPag"）→ 回傳格式字串；否則 None。"""
    if cell.ctype != xlrd.XL_CELL_NUMBER:
        return None
    fs = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
    return fs if fs and fs != 'General' and '"' in fs else None


def xls_cell_text(book, cell):
    """xlrd 儲存格：數字依格式字串還原（例 "0~"#,##0" KPag" → 0~40,000 KPag）。"""
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        v = cell.value
        fs = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
        if fs and fs != 'General' and '"' in fs:
            out, i = '', 0
            num_done = False
            for tok in re.findall(r'"[^"]*"|[#0,\.]+|General|.', fs):
                if tok.startswith('"'):
                    out += tok[1:-1]
                elif re.fullmatch(r'[#0,\.]+|General', tok) and not num_done:
                    dec = len(tok.split('.')[1]) if '.' in tok else None
                    if tok == 'General' or dec is None:
                        if ',' in tok:
                            out += f'{v:,.0f}'
                        else:
                            out += str(int(v)) if float(v).is_integer() else f'{v:g}'
                    else:
                        out += f'{v:,.{dec}f}' if ',' in tok else f'{v:.{dec}f}'
                    num_done = True
            return clean(out)
        return clean(v)
    return clean(cell.value)


# ---------------------------------------------------------------- discovery
def discover(root, folders):
    files = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isfile(p) and CAND_RE.search(name):
            files.append(name)
    for top in sorted(os.listdir(root)):
        if not os.path.isdir(os.path.join(root, top)):
            continue
        if not any(top.startswith(f) for f in folders):
            continue
        for dp, dns, fns in os.walk(os.path.join(root, top)):
            rel = os.path.relpath(dp, root).replace('\\', '/')
            # 設備 dossier 資料夾（AM10/AM20…）內為捷徑/複本，不列入
            dns[:] = [d for d in dns if not re.fullmatch(r'AM\d\d', d)]
            for fn in fns:
                if CAND_RE.search(fn):
                    files.append(rel + '/' + fn)
    return files


# ---------------------------------------------------------------- parsers
def rows_openpyxl(path, sheet=None):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    title = ws.title
    wb.close()
    return title, rows


def nonempty(rows):
    return sum(1 for r in rows for v in r if v not in (None, '') and not is_blank(clean(v)))


def parse_bop(path):
    title, rows = rows_openpyxl(path)
    hdr = [clean(h) for h in rows[0]]
    col = {h: i for i, h in enumerate(hdr)}

    def g(r, name):
        i = col.get(name)
        return clean(r[i]) if i is not None and i < len(r) else ''
    out = []
    for ri, r in enumerate(rows[1:], 2):
        tagcell = g(r, 'Tag No')
        if not tagcell:
            continue
        rng = g(r, 'Calibration Range')
        sp = []
        if not is_blank(g(r, 'Set Point Trip')):
            sp.append('跳機 ' + g(r, 'Set Point Trip'))
        if not is_blank(g(r, 'Set Point Alarm')):
            sp.append('警報 ' + g(r, 'Set Point Alarm'))
        sysc = ' '.join(x for x in [g(r, 'Elementary System Code'), g(r, 'Elementary system Descrip')] if not is_blank(x))
        f = [
            ('項目', g(r, 'Type Instrument')),
            ('服務說明', g(r, 'Funct description')),
            ('P&ID', g(r, 'P&ID Customer Code')),
            ('系統', sysc),
            ('設計量程（原文）', rng),
        ]
        pr = parse_range(rng)
        if pr:
            f += [('量程下限_num', pr[0]), ('量程上限_num', pr[1]), ('量程單位', pr[2])]
        f += [
            ('警報/跳機設定值', '；'.join(sp)),
            ('儀器種類', g(r, 'Type Instrument')),
            ('廠牌', g(r, 'Make')),
            ('完整型號碼', g(r, 'Manufacturer Model')),
            ('輸出', g(r, 'Output')),
            ('介質', g(r, 'Medium code')),
            ('位置圖', g(r, 'Instr Location Drg. No.')),
            ('室內外', g(r, 'Physical Location')),
            ('支架/保護箱', g(r, 'Stanchion/ Enclosure')),
            ('Hook-up 圖', g(r, 'Hook Up Drg No.')),
            ('備註', g(r, 'Remarks')),
            ('電源', g(r, 'Power Source')),
            ('訊號去向', g(r, 'Source / Destination Cont') or g(r, 'System')),
            ('列版次', g(r, 'Inst List Cust Rev')),
        ]
        out.append({'tags': re.split(r'[\s,;/]+', tagcell.replace('=', ' ').strip()), 'ge': '',
                    'loc': f'{title}!r{ri}', 'fields': f})
    return out


def parse_ge(path):
    """GE End User Template（GT A0102 / ST A0104）。"""
    title, rows = rows_openpyxl(path)
    hdr = [clean(h) for h in rows[0]]
    col = {}
    for i, h in enumerate(hdr):
        col.setdefault(h, i)
    ti = col['RDS-PP TAG No.']
    mli_i = ti + 2  # GE No. 之後的 Hardware MLI 欄（表頭第 2 列）

    def g(r, name):
        i = col.get(name)
        return clean(r[i]) if i is not None and i < len(r) else ''
    out = []
    for ri, r in enumerate(rows, 1):
        if ri <= 2 or len(r) <= ti:
            continue
        tag = clean(r[ti])
        if not re.match(r'^=?[A-Z]{1,2}\d{0,2}[A-Z]{3}\d\d', tag):
            continue
        adj, adjable = g(r, 'Adjusted Range'), g(r, 'Adjustable Range')
        rng = adj if not is_blank(adj) else adjable
        f = [('項目', ''), ('服務說明', g(r, 'SERVICE')), ('P&ID', g(r, 'P&ID')), ('系統', ''),
             ('設計量程（原文）', rng)]
        pr = parse_range(rng)
        if pr:
            f += [('量程下限_num', pr[0]), ('量程上限_num', pr[1]), ('量程單位', pr[2])]
        f += [
            ('警報/跳機設定值', g(r, 'Alarm Set Point')),
            ('儀器種類', ''),
            ('廠牌', g(r, 'MANUFACTURE')),
            ('完整型號碼', g(r, 'MODEL NO.')),
            ('輸出', g(r, 'INPUT')),
            ('介質', ''),
            ('位置圖', g(r, 'LOCATION')),
            ('室內外', ''),
            ('支架/保護箱', ''),
            ('Hook-up 圖', g(r, 'Hook-up Detail')),
            ('備註', g(r, 'Remark')),
            ('可調量程', adjable if not is_blank(adj) else ''),
            ('設計壓力', g(r, 'DESIGN PRESS.')),
            ('設計溫度', g(r, 'DESIGN TEMP.')),
            ('電源', g(r, 'POWER SUPPLY')),
            ('電源位置', g(r, 'POWER SOURCE')),
            ('訊號去向', g(r, 'OUTPUT / DESTINATION')),
            ('RDS-PP 位號', tag.lstrip('=')),
            ('GE 編號', g(r, 'GE No.')),
            ('MLI', clean(r[mli_i]) if mli_i < len(r) else ''),
            ('列版次', g(r, 'Rev No.')),
        ]
        out.append({'tags': [tag.lstrip('=')], 'ge': g(r, 'GE No.'), 'loc': f'{title}!r{ri}', 'fields': f})
    return out


HRSG_MAP = [  # (header 關鍵字（兩列表頭合併、只留 A-Z&），欄位名)；先比對者優先
    ('SERVICE', '服務說明'), ('POWERSOURCELOCATION', '電源位置'), ('LOCATIONDRAWING', '位置圖'), ('LOCATION', '位置圖'),
    ('MODELNO', '完整型號碼'),
    ('MANUFAC', '廠牌'), ('RANGE', '設計量程（原文）'), ('SETPOINTTRIP', '跳機'), ('SETPOINTALARM', '警報'),
    ('CALIBRATIONDATA', '校正資料'), ('INPUTOUTPUT', '輸出'), ('POWERSUPPLY', '電源'),
    ('DESIGNPRESS', '設計壓力/溫度'), ('INSTRUMENTCONNECTION', '製程接口'),
    ('PROCESSCONNECTION', '製程接口'), ('ELECTRICALCONNECTION', '電氣接口'), ('INPUTSOURCE', '訊號來源'),
    ('OUTPUTDESTINATION', '訊號去向'), ('P&I', 'P&ID'), ('EQUIPMENTDRAWING', 'P&ID'), ('HOOKUP', 'Hook-up 圖'),
    ('REMARKS', '備註'), ('RDS-PPTAGNO', '_tag'), ('TAGNO', '_tag'), ('GENO', '_tag'), ('REV', '列版次'),
    ('PURC', None), ('INST-ALLED', None), ('DETE', None), ('ITEM', None),
]


def parse_hrsg_xls(path):
    book = xlrd.open_workbook(path, formatting_info=True)
    out = []
    for s in book.sheets():
        if s.nrows < 5 or s.name in ('Cover', 'Title', 'Index', 'Legend'):
            continue
        # 找表頭：含 SERVICE 的列
        h1 = None
        for r in range(min(8, s.nrows)):
            if any(clean(v).upper() == 'SERVICE' for v in s.row_values(r)):
                h1 = r
                break
        if h1 is None:
            continue
        category = clean(s.cell_value(1, 0)) if s.nrows > 1 else s.name
        heads = []
        for c in range(s.ncols):
            a = clean(s.cell_value(h1, c))
            b = clean(s.cell_value(h1 + 1, c))
            heads.append(re.sub(r'[^A-Z&]', '', (a + b).upper()))
        cmap = {}
        last = None
        for c, h in enumerate(heads):
            name = None
            if h:
                for key, nm in HRSG_MAP:
                    if re.sub(r'[^A-Z&]', '', key) in h:
                        name = nm if nm else '_skip'
                        break
                last = name
            else:
                name = '備註+' if last == '備註' else None
            if name and name != '_skip':
                cmap[c] = name
        tagc = [c for c, n in cmap.items() if n == '_tag']
        if not tagc:
            continue
        tagc = tagc[-1]
        for r in range(h1 + 2, s.nrows):
            tag = clean(s.cell_value(r, tagc)).lstrip('=').strip()
            if not re.match(r'^[A-Z]\d\d[A-Z]{3}\d\d', tag):
                continue
            vals = collections.OrderedDict()
            rng_fmt = None  # RANGE 為數值儲存格、下限與單位只來自整欄數字格式
            for c, nm in cmap.items():
                if nm == '_tag' or c >= s.ncols:
                    continue
                t = xls_cell_text(book, s.cell(r, c))
                if nm == '設計量程（原文）' and 'RANGE' in heads[c] and xls_num_fmt(book, s.cell(r, c)) and not is_blank(t):
                    rng_fmt = (s.cell(r, c).value, xls_num_fmt(book, s.cell(r, c)), t)
                if nm == '備註+':
                    nm = '備註'
                if is_blank(t):
                    continue
                vals[nm] = (vals[nm] + ' ' + t).strip() if nm in vals else t
            rng = vals.get('設計量程（原文）', '')
            sp = []
            if 'SETPOINTTRIPALARM' in ''.join(heads):
                pass
            if vals.get('跳機'):
                sp.append('跳機 ' + vals['跳機'])
            if vals.get('警報'):
                sp.append('警報 ' + vals['警報'])
            pr = parse_range(rng)
            if rng_fmt:
                v0, fs, shown = rng_fmt
                v0 = int(v0) if float(v0).is_integer() else v0
                rng = f'{v0}（數值儲存格，原文無單位；依整欄數字格式 {fs} 顯示為「{shown}」，下限與單位為推定）'
            f = [('項目', category), ('服務說明', vals.get('服務說明', '')), ('P&ID', vals.get('P&ID', '')), ('系統', ''),
                 ('設計量程（原文）', rng)]
            if pr:
                f += [('量程下限_num', pr[0]), ('量程上限_num', pr[1]), ('量程單位', pr[2])]
                if rng_fmt:
                    f += [('量程單位來源', '儲存格數字格式（推定）')]
            f += [('警報/跳機設定值', '；'.join(sp)), ('儀器種類', category), ('廠牌', vals.get('廠牌', '')),
                  ('完整型號碼', vals.get('完整型號碼', '')), ('輸出', vals.get('輸出', '')), ('介質', ''),
                  ('位置圖', vals.get('位置圖', '')), ('室內外', ''), ('支架/保護箱', ''),
                  ('Hook-up 圖', vals.get('Hook-up 圖', '')), ('備註', vals.get('備註', '')),
                  ('校正資料', vals.get('校正資料', '')), ('設計壓力/溫度', vals.get('設計壓力/溫度', '')),
                  ('製程接口', vals.get('製程接口', '')), ('電氣接口', vals.get('電氣接口', '')),
                  ('電源', vals.get('電源', '')), ('訊號去向', vals.get('訊號去向', '')),
                  ('RDS-PP 位號', tag), ('列版次', vals.get('列版次', ''))]
            out.append({'tags': [tag], 'ge': '', 'loc': f'{s.name}!r{r + 1}', 'fields': f})
    # 版次：Title 工作表 Rev.
    rev = ''
    try:
        t = book.sheet_by_name('Title')
        for r in range(t.nrows - 1):
            if clean(t.cell_value(r, 0)) in ('Rev.', 'Rev', 'Rev No'):
                rev = clean(t.cell_value(r + 1, 0))
                break
    except xlrd.biffh.XLRDError:
        pass
    return out, rev


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True, help='工程文件庫根目錄')
    ap.add_argument('--sheets', required=True, help='docs/db/data/sheets')
    ap.add_argument('--out', required=True)
    ap.add_argument('--folders', nargs='*', default=DEFAULT_FOLDERS)
    a = ap.parse_args()
    root = a.root

    # 位號 → alias
    d03 = json.load(open(os.path.join(a.sheets, '03.json'), encoding='utf-8'))
    tag2alias = {}
    for r in d03['rows']:
        t = str(r[0] or '').strip()
        if t and r[1]:
            tag2alias.setdefault(t, r[1])
    idx04 = {}
    p04 = os.path.join(a.sheets, '04.json')
    if os.path.exists(p04):
        for r in json.load(open(p04, encoding='utf-8'))['rows']:
            s = str(r[1] or '').strip()
            if s and r[4] and s not in tag2alias:
                idx04.setdefault(s, (r[4], str(r[2] or '')))

    files = discover(root, a.folders)
    print('candidates', len(files))

    searched = []
    groups = collections.defaultdict(list)  # doc_id -> parseable spreadsheet candidates
    pdf_revs = collections.defaultdict(list)
    pdf_docs = collections.defaultdict(list)  # doc_id -> [(rev, title, folder)]
    for rel in files:
        fn = rel.split('/')[-1]
        folder = '/'.join(rel.split('/')[:-1])
        m = DOCID_RE.search(fn)
        doc_id = m.group(1) if m else ''
        ext = os.path.splitext(fn)[1].lower()
        ent = {'doc_id': doc_id, 'rev': file_rev(fn), 'title': fn, 'folder': folder, 'used': False, 'why': ''}
        if ext == '.pdf':
            if doc_id:
                pdf_revs[doc_id].append(ent['rev'])
                pdf_docs[doc_id].append((ent['rev'], fn, folder))
            ent['why'] = '僅PDF（xlsx 轉出檔）' if '_xlsx_pdf' in folder else '僅PDF'
            searched.append(ent)
            continue
        if ext not in ('.xlsx', '.xlsm', '.xls'):
            ent['why'] = '格式不取值（' + (ext or '無副檔名') + '）'
            searched.append(ent)
            continue
        kind = None
        if re.search(r'ILE01-A11\d\d', fn) and 'Attachment' in fn:
            kind = 'bop'
        elif 'GLD01-A0102' in fn or 'TLD01-A0104' in fn:
            kind = 'ge'
        elif 'BLD01-A0002' in fn and ext == '.xls':
            kind = 'hrsg'
        if not doc_id or not folder:
            ent['why'] = '非正式文件（根目錄彙整表，無文件編號）' if not doc_id else '根目錄彙整表'
            searched.append(ent)
            continue
        if DERIV_RE.search(fn) or kind is None:
            ent['why'] = '衍生/個人整理版（非原件）' if DERIV_RE.search(fn) else '非清單格式'
            searched.append(ent)
            continue
        ent['_kind'] = kind
        ent['_path'] = os.path.join(root, rel)
        groups[doc_id].append(ent)
        searched.append(ent)

    by_alias = collections.defaultdict(list)
    rows_total = 0
    chosen_docs = []
    for doc_id, cands in sorted(groups.items()):
        parsed = []
        for c in cands:
            try:
                if c['_kind'] == 'bop':
                    rows = parse_bop(c['_path'])
                    rrev = max((dict(f)['列版次'] for f in [x['fields'] for x in rows]), key=rev_rank, default='')
                    rev, basis = max([c['rev'], rrev], key=rev_rank), '列版次最大值'
                    if c['rev'] and rev_rank(c['rev']) >= rev_rank(rrev):
                        basis = '檔名版次'
                elif c['_kind'] == 'ge':
                    rows = parse_ge(c['_path'])
                    rev = c['rev'] or max(pdf_revs.get(doc_id, ['']), key=rev_rank)
                    basis = '檔名版次' if c['rev'] else '依同號 PDF 最新版次推定'
                else:
                    rows, trev = parse_hrsg_xls(c['_path'])
                    rev, basis = (c['rev'] or trev), ('檔名版次' if c['rev'] else 'Title 工作表 Rev.')
            except Exception as e:  # noqa
                c['why'] = '讀取失敗 ' + str(e)[:60]
                continue
            ne = sum(1 for x in rows for _, v in x['fields']
                     if v not in ('', None) and not (isinstance(v, str) and is_blank(v)))
            mt = os.path.getmtime(c['_path'])
            parsed.append((rev_rank(rev), ne, mt, c, rows, rev, basis))
        if not parsed:
            continue
        # 使用者規則：版次大者優先；同版次取修改時間最新；再同才比內容多寡。
        # （查核：GT A0102 07_系統清冊 副本與官方 Rev C PDF 列序/內容不符，(2) 與 PDF 一致且較新）
        parsed.sort(key=lambda t: (t[0], t[2], t[1]), reverse=True)
        best = parsed[0]
        _, bne, bmt, bc, brows, brev, bbasis = best
        bc['used'] = True
        bc['rev'] = brev
        bc['why'] = f'選用：版次 {brev}（{bbasis}）'
        if len(parsed) > 1:
            bc['why'] += '；多副本中版次最高、同版次取修改時間最新'
        for rk, ne, mt, c, rows, rev, basis in parsed[1:]:
            c['rev'] = rev
            if rk < best[0]:
                c['why'] = f'被取代（版次 {rev} < {brev}）'
            else:
                c['why'] = f'副本（同版次 {rev}，修改時間較舊；非空欄 {ne} vs 選用 {bne}）'
        # 同號較新版次 PDF（不取值，但要標出）
        newer = [(r, t) for r, t, fo in pdf_docs.get(doc_id, [])
                 if rev_rank(r) > rev_rank(brev) and '_xlsx_pdf' not in fo]
        rev_note = ''
        if newer:
            nr = max(newer, key=lambda x: rev_rank(x[0]))[0]
            if doc_id in NEWER_PDF_NOTE:
                rev_note = NEWER_PDF_NOTE[doc_id]
            else:
                rev_note = (f'同號另有較新版次 {nr} PDF（僅PDF不取值）；值取自附件試算表（列版次最高 {brev}）')
            bc['why'] += '；' + rev_note
        chosen_docs.append((doc_id, bc, brows, brev, rev_note))

    if pdf_revs:
        pass

    # ---- 比對
    for doc_id, c, rows, rev, rev_note in chosen_docs:
        is_gt = 'GLD01-A0102' in doc_id
        is_st = 'TLD01-A0104' in doc_id
        is_hrsg = 'BLD01-A0002' in doc_id
        doc_tags = set(t for x in rows for t in x['tags'])
        copy = os.path.splitext(c['title'])[0].replace(doc_id, '').strip(' -_') or c['title']
        for x in rows:
            rows_total += 1
            hits = []  # (alias, rule, level, note)
            multi = len([t for t in x['tags'] if t]) > 1
            for t in x['tags']:
                if not t:
                    continue
                cands = [(t, 'R5' if multi else 'R1', 'doc', '')]
                if t[:2] == 'YY':
                    cands.append(('S10' + t[2:], 'R3', 'doc', f'YY→S10（{t}）'))
                if t[:2] == 'XX':
                    for u in ('G11', 'G12'):
                        cands.append((u + t[2:], 'R3', 'doc', f'XX→{u}（{t}）'))
                if (is_gt or is_hrsg) and t.startswith('G11'):
                    g12 = 'G12' + t[3:]
                    if g12 not in doc_tags:
                        cands.append((g12, 'R4', 'inferred', f'G12 套用 G11 範本列（文件位號 {t}）'))
                for tt, rule, lvl, note in cands:
                    if tt in tag2alias:
                        hits.append((tag2alias[tt], rule, lvl, note, tt))
                    elif tt in idx04 and rule in ('R1', 'R5', 'R3'):
                        al, src = idx04[tt]
                        hits.append((al, rule, lvl, (note + '；' if note else '') + f'經 04 位號索引（{src}）', tt))
            ge = x['ge']
            if (is_gt or is_st) and ge and not is_blank(ge):
                for g in re.split(r'[\s/]+|\(|\)', ge):
                    g = g.strip()
                    if not g:
                        continue
                    if is_gt:
                        for u, lvl, rule in (('G11', 'doc', 'R2'), ('G12', 'inferred', 'R4')):
                            k = f'{u}_{g}'
                            if k in tag2alias:
                                note = f'GE No. {g} → {k}' + ('（G12 套用 G11 範本）' if u == 'G12' else '')
                                hits.append((tag2alias[k], rule, lvl, note, k))
                    if is_st and f'S10_{g}' in tag2alias:
                        hits.append((tag2alias[f'S10_{g}'], 'R2', 'doc', f'GE No. {g}', f'S10_{g}'))
            seen = set()
            for al, rule, lvl, note, tt in hits:
                if (al, rule) in seen:
                    continue
                seen.add((al, rule))
                fields = [[k, v] for k, v in x['fields'] if not (isinstance(v, str) and is_blank(v))]
                e = {'doc_id': doc_id, 'rev': rev, 'loc': x['loc'], 'rule': rule, 'level': lvl, 'fields': fields,
                     'copy': copy, 'matched_tag': tt}
                if note:
                    e['note'] = note
                if rev_note:
                    e['rev_note'] = rev_note
                by_alias[al].append(e)

    # R4 推論：若同一 alias 已有 doc 級直接命中，移除推論列
    for al in list(by_alias):
        ents = by_alias[al]
        if any(e['level'] == 'doc' for e in ents):
            ents = [e for e in ents if e['level'] != 'inferred']
        order = {'R1': 0, 'R5': 1, 'R2': 2, 'R3': 3, 'R4': 4}
        ents.sort(key=lambda e: (order.get(e['rule'], 9), e['doc_id'], int(re.search(r'r(\d+)$', e['loc']).group(1))))
        by_alias[al] = ents

    for s in searched:
        s.pop('_kind', None)
        s.pop('_path', None)
    searched.sort(key=lambda s: (not s['used'], s['doc_id'] or 'zzz', s['folder'], s['title']))
    lv = collections.Counter(e['level'] for v in by_alias.values() for e in v)
    ru = collections.Counter(e['rule'] for v in by_alias.values() for e in v)
    out = {
        'kind': 'instlist',
        'generated_by': 'tools/db/docmap_instlist.py',
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'searched': searched,
        'by_alias': dict(sorted(by_alias.items())),
        'stats': {
            'aliases_matched': len(by_alias),
            'aliases_doc_level': sum(1 for v in by_alias.values() if any(e['level'] == 'doc' for e in v)),
            'rows': sum(len(v) for v in by_alias.values()),
            'doc_rows_parsed': rows_total,
            'docs_used': [f"{d}-{r}" for d, _, _, r, _ in chosen_docs],
            'by_rule': dict(ru), 'by_level': dict(lv),
            'notes': ('值取自 xlsx/xls；PDF 僅列入 searched。欄位值為佔位符（-、--、N.A.）者省略。'
                      'HRSG BLD01-A0002 xls 為 Rev F（數字量程依儲存格格式還原單位），另有 PDF -2（列版次 G，修訂紀錄僅「Updated serial number for PIT list」）僅PDF不取值。'
                      'BOP A11xx 同號較新版次 PDF 多為封面頁（附件 Excel 未另存），見 entry.rev_note。'
                      '同版次多副本取修改時間最新者。'
                      'GT A0102 僅列 G11（Note: G11=G12=…），G12 以 G11 範本推論 rule=R4 level=inferred；同 alias 若已有文件直接命中則捨棄推論列。'
                      'HRSG xls 亦僅列 G11（Index 註：各機組加前綴），G12 同樣以 R4 推論。'
                      '量程 _num 取原文第一段（GE 文件 °F/psi 在前、括號內為換算值）。'),
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps(out['stats'], ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
