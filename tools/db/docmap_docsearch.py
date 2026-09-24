# -*- coding: utf-8 -*-
"""docmap_docsearch.py — 文件全文檢索（hst-docsearch 的 FTS 索引）→ 設備查詢卡 kind="docsearch"

  py tools/db/docmap_docsearch.py --data docs/db/data --out %LOCALAPPDATA%/AMS/cardwork/docsearch.json
        [--fts C:/Users/<me>/hst_docsearch/hst_fts.db] [--library <文件庫根>] [--drive-map %LOCALAPPDATA%/AMS/drive_map.json]
        [--tags G12HAP66BP001,C10LAB22BP001] [--limit N]

輸入：解密後的 docs/db/data（sheets/03.json 取位號／別名／廠牌／型號；card/aux-*.json 的 sec.device 取 AMS 裡的序號參數）、
hst-docsearch 建的 SQLite FTS5 索引（頁級：docs(path, cache, trust) + pages(text)；trust 3=文字層、2=PyMuPDF、1=OCR）、
drive_map.py 的 路徑→Drive 檔案 ID 對照（有才補 url）。

每台設備搜：現行位號（品質「正常」者；GE 位號 G11_90LT-1 另搜 90LT-1）＋ AMS 序號參數（final_assembly_number、
*SerialNumber…；純數字至少 7 碼）。命中頁再用邊界正則確認（trigram 是子字串比對：90LT-1 會命中 90LT-10）；
位號不採 OCR 命中（hst-docsearch pitfalls #1：KKS 經 OCR 命中率 0/132），序號允許 OCR 但標「需開原圖確認」。
排除：AMS/（本站自己的匯出）、副本（_舊版／_fix*／_chunks／AM10 dossier 夾／_xlsx_pdf／所有線路圖）、根目錄「組合 N.pdf」合訂本。
同文件編號只留最高版次（數字 > 字母）；每類別最多 2 份、每台最多 16 列。

輸出列（sec.docsearch.rows）：[類別, "文件-版次 p.N｜命中行", lvl, 來源字串, {rule, d, hit, pages, term}]；
另由命中行／命中頁抽出的推定值（規則寫在 rule）：序號命中（文件）、出廠型號（文件）、型號（文件）、廠牌（文件）、量程（文件）、量程（邏輯圖）。
docs["docsearch|<文件編號>|<版次>"] = {title, folder, url?}；不含本機絕對路徑。
"""
import argparse
import collections
import datetime
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_card_aux import unit_info  # noqa: E402  單位量綱（T/P/L/%）辨識，與 DCS 比對同一套
SKILL_CFG = os.path.join(os.path.expanduser('~'), '.claude', 'skills', 'hst-docsearch', 'config.json')
DEFAULT_DRIVE_MAP = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'drive_map.json')
DEFAULT_OUT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'docsearch.json')

DOCNO_RE = re.compile(r'(HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4})(?:-([0-9A-Z]{1,2})(?![0-9A-Za-z]))?', re.I)
TAG_OK_RE = re.compile(r'^[A-Z0-9][A-Z0-9_\-]{4,}$')
GE_TAG_RE = re.compile(r'^G1[12]_(\d{2}[A-Z]{2,}[A-Z0-9\-]*)$')
COPY_RE = re.compile(r'(^|/)(_舊版|_fix[^/]*|_chunks|_nb[^/]*|_缺漏補齊[^/]*|_xlsx_pdf|am10|am20|am30|所有線路圖)/', re.I)
DOSSIER_RE = re.compile(r'/(?:[a-z0-9]{3})?[a-z]{3}[a-z0-9]{2}[a-z]{2}\d{3}[^/]*/\d{2}_[^/]+/[^/]+$', re.I)
OFFICE_EXT = ('.xlsx', '.xls', '.xlsm', '.docx', '.doc', '.pptx', '.ppt')
TRUST_TAG = {3: '文字層', 2: 'PyMuPDF', 1: 'OCR'}

# 類別：依檔名（大寫）＋資料夾判斷，前面的先中
CATS = [
    ('儀器清單', re.compile(r'INSTRUMENT\s*LIST|儀器清單|儀錶清單|ILE01-A11\d\d|GLD01-A0102|BLD01-A0002|TLD01-A0104|TCM01-A16|DEVICE SUMMARY|INSTRUMENT INDEX')),
    ('出廠證書／EOMR', re.compile(r'EOMR|END\s*OF\s*MANUFACTUR|MANUFACTURING\s+REPORT|CALIBRATION|AQB01-Q|AQA01-[TQ]|AQP01-Q|CERTIFICATE|INSPECTION.{0,20}TEST')),
    ('規格表', re.compile(r'DATA\s*SHEET|DATASHEET|SPECIFICATION|規格|-S\d{4}(?:-|\b)|\bSPEC\b')),
    ('DCS 端子表', re.compile(r'IMI01-A0001|TERMINAL ASSIGNMENT|IO SIGNAL')),
    ('P&ID', re.compile(r'P&(?:AMP;)?ID|\bPID\b|流程圖|AFF01-D00')),
    ('Hook-up', re.compile(r'HOOK[\s\-]?UP|IIE01-D11')),
    ('位置圖', re.compile(r'LOCATION\s*(?:PLAN|DRAWING|LAYOUT)|位置圖|IIF01-D|III01-D5')),
    ('邏輯圖', re.compile(r'LOGIC|邏輯|IOE01-D2|IAI01-D00')),
    ('接線圖／迴路圖', re.compile(r'WIRING|CONNECTION DIAGRAM|\bLOOP\b|迴路|接線圖|ICE01-D|ICI01-D')),
    ('電纜表', re.compile(r'CABLE\s*(?:SCHEDULE|LIST)|電纜|ILE01-A10|EWE01-A')),
    ('操作說明', re.compile(r'OPERATING DESCRIPTION|OPERATION AND MAINTENANCE|FUNCTIONAL DESCRIPTION|O&M|操作|說明書|ADM01-M|TDM01-A|COMMISSIONING')),
    ('手冊', re.compile(r'MANUAL|GEK\d|手冊|INSTRUCTION')),
    ('Open Item／查修', re.compile(r'OPEN ITEM|跳機|查修|事故|PUNCH')),
]
CAT_ORDER = [c for c, _ in CATS] + ['教材', '其他']
CAT_MAX = {'教材': 1, '其他': 1}
TRAIN_RE = re.compile(r'^(92_|受訓資料)|TRAINING|訓練|簡報', re.I)
FACTORY_CATS = {'出廠證書／EOMR'}

# 廠牌推定要與 AMS 製造商一致（同集團視為一致）：清單 PDF 的文字層常把上下列併在一行，別把鄰列的廠牌當成這台的
VENDOR_GROUPS = [
    {'rosemount', 'emerson', 'fisher', 'micro motion', 'daniel', 'topworx', 'metso', 'neles'},
    {'endress+hauser', 'endress hauser', 'e+h'},
    {'ge', 'bently nevada', 'masoneilan', 'druck', 'baker hughes', 'panametrics'},
    {'abb'}, {'yokogawa'}, {'siemens'}, {'vega', 'vega grieshaber kg'}, {'honeywell', 'honeywell analytics'}, {'wika'}, {'krohne'},
    {'foxboro'}, {'flowserve'}, {'ytc'}, {'pr electronics'}, {'magnetrol'}, {'samson'}, {'azbil'}, {'fuji'}, {'swan'}, {'hach'}, {'mettler'},
]


def vendor_norm(v):
    v = re.sub(r'\s*\+\s*', '+', (v or '').lower().strip())
    v = re.sub(r'\s+', ' ', v)
    return v


def vendor_consistent(found, ams_mfr):
    """AMS 製造商空白 → 接受；否則要同一集團。"""
    if not ams_mfr:
        return True
    f, a = vendor_norm(found), vendor_norm(ams_mfr)
    if f == a or f in a or a in f:
        return True
    for g in VENDOR_GROUPS:
        if any(f == x or f.startswith(x) for x in g) and any(a == x or a.startswith(x) for x in g):
            return True
    return False


VENDOR_RE = re.compile(r'\b(Rosemount|Emerson|Endress\s*\+?\s*Hauser|E\+H|ABB|Yokogawa|Siemens|Fisher|Masoneilan|VEGA|Honeywell|WIKA|Krohne|Foxboro|Bently\s*Nevada|TopWorx|Metso|Flowserve|YTC|PR\s*Electronics|Magnetrol|Dwyer|Ashcroft|Brooks|Mettler|Hach|Swan|Panametrics|Samson|Azbil|Fuji|Micro\s*Motion|Daniel|Neles|Baker\s*Hughes|Druck|GE)\b', re.I)
UNIT = r'(?:kPa\(?[gaGA]?\)?|kPag|kPaa|kPa|MPa\(?[gaGA]?\)?|MPag|MPaa|MPa|mbar[ga]?|bar[ga]?|psi-?[ga]?|psi|mmH2O|mmH₂O|mmWC|mmWG|mH2O|inH2O|inWC|°C|℃|degC|deg C|°F|%|m3/h|m³/h|t/h|kg/s|kg/h|L/min|l/min|Nm3/h|Nm³/h|ppm|pH|[µu]S/cm|mS/cm|mm|cm|m)'
RANGE_RE = re.compile(r'(?<![A-Za-z0-9.])(-?\d+(?:[.,]\d+)?)\s*(?:~|～|to|TO|–|—|-|\.\.)\s*(-?\d+(?:[.,]\d+)?)\s*(' + UNIT + r')(?![A-Za-z])', re.I)
RANGE_DOTS_RE = re.compile(r'(?<![A-Za-z0-9.])(-?\d+(?:\.\d+)?)\.\.(-?\d+(?:\.\d+)?)\s*([^\s|]{1,8})')


def rev_key(rev):
    rev = (rev or '').upper()
    if not rev:
        return (0, 0, '')
    return (2, int(rev), '') if rev.isdigit() else (1, 0, rev)


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


class Library:
    """文件庫根目錄：真實大小寫的相對路徑（索引裡有 9,848 個路徑被小寫化）、Drive ID。"""

    def __init__(self, root, drive_map):
        self.root = root.replace('\\', '/').rstrip('/')
        self.real = {}
        for dp, dn, fn in os.walk(self.root):
            rel_dir = dp.replace('\\', '/')[len(self.root):].lstrip('/')
            for f in fn:
                rel = (rel_dir + '/' if rel_dir else '') + f
                self.real[rel.lower()] = rel
        self.drive = (drive_map or {}).get('files') or {}
        self.drive_root = (drive_map or {}).get('root')

    def rel(self, path):
        p = path.replace('\\', '/')
        if p[:3].lower() == '/c/':
            p = 'C:/' + p[3:]
        low = p.lower()
        if low.startswith(self.root.lower() + '/'):
            r = p[len(self.root) + 1:]
        else:
            r = p
        return self.real.get(r.lower(), r)

    def url(self, rel):
        fid = self.drive.get(rel.lower())
        return 'https://drive.google.com/open?id=%s' % fid if fid else None


def is_copy(rel):
    r = '/' + rel.replace('\\', '/')
    if COPY_RE.search(r):
        return True
    if DOSSIER_RE.search(r):
        return True
    base = os.path.basename(r)
    return bool(re.match(r'組合\s*\d*\.pdf$', base, re.I)) or '_dup' in base.lower()


def category(rel):
    base = os.path.basename(rel).upper()
    folder = os.path.dirname(rel).upper()
    if TRAIN_RE.search(rel.split('/')[0]) or TRAIN_RE.search(base):
        return '教材'
    for cat, rx in CATS:
        if rx.search(base):
            return cat
    for cat, rx in CATS:  # 再看資料夾（P&ID 常只在資料夾名「02_流程圖」）
        if cat in ('P&ID', '邏輯圖', 'Hook-up', '位置圖', '接線圖／迴路圖', '出廠證書／EOMR', '儀器清單') and rx.search(folder):
            return cat
    return '其他'


def doc_ref(rel):
    base = os.path.basename(rel)
    m = DOCNO_RE.search(base)
    if m:
        return (m.group(1).upper(), (m.group(2) or '').upper(), m.group(1).upper() + ('-' + m.group(2).upper() if m.group(2) else ''))
    stem = os.path.splitext(base)[0]
    return (None, '', stem[:70])


def excerpt(text, rx, width=150):
    m = rx.search(text)
    if not m:
        return '', False
    a = text.rfind('\n', 0, m.start()) + 1
    b = text.find('\n', m.end())
    b = len(text) if b < 0 else b
    line = re.sub(r'\s+', ' ', text[a:b]).strip().replace('\ufffd', '°')
    if len(line) > width:
        pos = line.find(m.group(0)) if m.group(0) in line else 0
        s = max(0, pos - width // 3)
        line = ('…' if s else '') + line[s:s + width] + '…'
    return line, True


def model_core(model):
    for tok in re.split(r'[\s,/()]+', model or ''):
        t = re.sub(r'[^A-Za-z0-9]', '', tok)
        if re.search(r'\d', t) and len(t) >= 3 and t.lower() not in ('rev10', 'rev7', 'rev5'):
            return t
    return ''


def find_model(text, core, tag):
    if not core:
        return ''
    rx = re.compile(r'(?<![A-Za-z0-9])' + re.escape(core) + r'[A-Za-z0-9][A-Za-z0-9\-/.]{2,}(?![A-Za-z0-9])', re.I)
    best = ''
    for m in rx.finditer(text):
        v = m.group(0).rstrip('.-/')
        if v.upper() == tag.upper() or len(v) > 60:
            continue
        if len(v) > len(best):
            best = v
    return best


def find_range(line, ams_unit=None):
    """命中行內的「下限～上限 單位」（最多 3 組）；AMS 單位量綱已知時，量綱不同的（例如鄰列的溫度）不採。"""
    found = [(m.group(1), m.group(2), m.group(3)) for m in RANGE_RE.finditer(line)]
    if not found:
        found = [(m.group(1), m.group(2), m.group(3).replace('\ufffd', '°')) for m in RANGE_DOTS_RE.finditer(line)]
    ai = unit_info(ams_unit) if ams_unit else None
    out = []
    for lo, hi, u in found:
        ui = unit_info(u)
        if ai and ui and ai[0] != ui[0]:
            continue
        v = '%s ～ %s %s' % (lo, hi, u)
        if v not in out:
            out.append(v)
    return '；'.join(out[:3])


class Searcher:
    SQL = ('SELECT d.path, d.trust, p.page, p.rowid FROM pages_fts JOIN pages p ON p.rowid = pages_fts.rowid '
           'JOIN docs d ON d.doc_id = p.doc_id WHERE pages_fts MATCH ? ORDER BY d.trust DESC LIMIT 4000')

    def __init__(self, fts, lib):
        self.db = sqlite3.connect('file:%s?mode=ro' % fts.replace('\\', '/'), uri=True)
        self.lib = lib
        st = self.db.execute("SELECT v FROM meta WHERE k='status'").fetchone()
        if not st or st[0] != 'complete':
            raise SystemExit('FTS 索引未建置完成（meta.status=%s）' % (st and st[0]))
        self.n_docs = self.db.execute('SELECT count(*) FROM docs').fetchone()[0]
        self.n_pages = self.db.execute('SELECT count(*) FROM pages').fetchone()[0]
        self.built = datetime.datetime.fromtimestamp(os.path.getmtime(fts)).strftime('%Y-%m-%d')
        self._text = {}

    def text(self, rowid):
        t = self._text.get(rowid)
        if t is None:
            r = self.db.execute('SELECT text FROM pages WHERE rowid=?', (rowid,)).fetchone()
            t = r[0] if r else ''
            if len(self._text) > 4000:
                self._text.clear()
            self._text[rowid] = t
        return t

    def search(self, term, kind):
        """回傳 {rel: {'trust', 'pages': [(page, rowid, exact)], 'n'}}（已排除副本／AMS 匯出，已做邊界確認）。"""
        q = '"' + term.replace('"', '""') + '"'
        rows = self.db.execute(self.SQL, (q,)).fetchall()
        esc = re.escape(term)
        exact_rx = re.compile(r'(?<![A-Za-z0-9])' + esc + r'(?![A-Za-z0-9_\-])', re.I)
        loose_rx = re.compile(r'(?<![A-Za-z0-9])' + esc + (r'(?![0-9])' if kind == 'tag' else r'(?![A-Za-z0-9])'), re.I)
        out = {}
        for path, trust, page, rowid in rows:
            if kind == 'tag' and trust < 2:
                continue
            rel = self.lib.rel(path)
            low = rel.lower()
            if low.startswith('ams/') or is_copy(rel):
                continue
            txt = self.text(rowid)
            if not loose_rx.search(txt):
                continue
            exact = bool(exact_rx.search(txt))
            rec = out.setdefault(rel, {'trust': 0, 'pages': [], 'n': 0})
            rec['n'] += 1
            rec['trust'] = max(rec['trust'], trust)
            if len(rec['pages']) < 6:
                rec['pages'].append((page, rowid, exact))
        return out, exact_rx, loose_rx


def dedupe_versions(hits):
    """同文件編號只留最高版次；無編號者以檔名（去 noKKS_／(1)）去重，留路徑短者。"""
    best = {}
    for rel, rec in hits.items():
        doc_id, rev, ref = doc_ref(rel)
        base = os.path.basename(rel)
        nokks = base.lower().startswith('nokks_')
        if doc_id:
            key = doc_id
            score = (1, rev_key(rev), rec['trust'], -len(rel))
        else:
            key = re.sub(r'^nokks_|\s*\(\d+\)(?=\.)|_rev[0-9a-z\-]*(?=\.)', '', base.lower())
            score = (0, (0, 0, ''), rec['trust'], -len(rel))
        if key not in best or score > best[key][0]:
            best[key] = (score, rel, rec)
    # noKKS_<標題>（GE 原件的人工分類副本）：同標題已有帶文件編號的檔就不重複列
    titled = {norm_title(rel) for _, rel, _ in best.values() if doc_ref(rel)[0]}
    return {rel: rec for _, rel, rec in best.values() if not (os.path.basename(rel).lower().startswith('nokks_') and norm_title(rel) in titled)}


def norm_title(rel):
    stem = os.path.splitext(os.path.basename(rel))[0]
    stem = DOCNO_RE.sub('', stem)
    stem = re.sub(r'^nokks_|_rev[0-9a-z\-]*$|\s*\(\d+\)$', '', stem, flags=re.I)
    return re.sub(r'[^a-z0-9]', '', stem.lower())[:28]


def serial_terms(dev_rows):
    out = []
    for k, v in dev_rows:
        if '序號' not in k or '相符' in k or '(值 0/空)' in k:
            continue
        v = str(v or '').strip()
        if not v or v.startswith('未寫入') or v in ('—', '- none -', '0') or ' ' in v:
            continue
        if not re.fullmatch(r'[A-Za-z0-9\-]{6,}', v) or not re.search(r'\d', v):
            continue
        if v.isdigit() and len(v) < 7:
            continue
        if v not in [x[1] for x in out]:
            out.append((k, v))
    out.sort(key=lambda x: 0 if 'final_assembly' in x[0] else 1)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--data', default=os.path.join('docs', 'db', 'data'))
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--fts')
    ap.add_argument('--library')
    ap.add_argument('--drive-map', default=DEFAULT_DRIVE_MAP)
    ap.add_argument('--tags', help='只跑這些位號（逗號分隔，除錯用）')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--max-rows', type=int, default=16)
    a = ap.parse_args()
    cfg = load(SKILL_CFG) if os.path.exists(SKILL_CFG) else {}
    fts = a.fts or cfg.get('fts_db')
    root = a.library or cfg.get('library_root')
    if not fts or not os.path.exists(fts):
        raise SystemExit('沒有 FTS 索引：--fts 或 hst-docsearch config.json 的 fts_db')
    if not root or not os.path.isdir(root):
        raise SystemExit('沒有文件庫根目錄：--library 或 config.json 的 library_root')
    sheets = os.path.join(a.data, 'sheets')
    if not os.path.exists(os.path.join(sheets, '03.json')):
        raise SystemExit('沒有明文 03.json：先 py tools/encrypt_data.py %s --decrypt' % a.data)
    drive = load(a.drive_map) if os.path.exists(a.drive_map) else None
    if drive is None:
        print('drive_map 不存在（%s）：不補 url；先跑 py tools/db/drive_map.py' % a.drive_map)
    t0 = time.time()
    lib = Library(root, drive)
    print('文件庫 %d 個檔（真實路徑對照 %.1fs）' % (len(lib.real), time.time() - t0))
    S = Searcher(fts, lib)
    print('FTS 索引 %s：%d 檔 %d 頁' % (S.built, S.n_docs, S.n_pages))

    s03 = load(os.path.join(sheets, '03.json'))
    unit_of = {}
    p13 = os.path.join(sheets, '13.json')
    if os.path.exists(p13):
        for r in load(p13)['rows']:
            unit_of[r[40]] = str(r[18] or '').strip()   # 設備參數統計：col40 alias、col18 單位(解碼)
    devices = []
    for r in s03['rows']:
        devices.append({'tag': str(r[0] or '').strip(), 'alias': r[1], 'quality': str(r[4] or ''), 'proto': str(r[21] or ''),
                        'mfr': str(r[24] or ''), 'model': str(r[26] or ''), 'unit': unit_of.get(r[1], '')})
    dev_rows = {}
    ix_path = os.path.join(a.data, 'card', 'index.json')
    if os.path.exists(ix_path):
        for fn in load(ix_path)['files']:
            for al, d in load(os.path.join(a.data, fn))['by_alias'].items():
                dev_rows[al] = [(x[0], x[1]) for x in ((d.get('sec') or {}).get('device') or {}).get('rows', [])]
    only = set(x.strip() for x in a.tags.split(',')) if a.tags else None
    if only:
        devices = [d for d in devices if d['tag'] in only]
    if a.limit:
        devices = devices[:a.limit]

    docs, by_alias = {}, {}
    stats = collections.Counter()
    cat_stats = collections.Counter()
    t0 = time.time()
    for i, dev in enumerate(devices):
        tag = dev['tag']
        terms = []
        param_of = {}
        if dev['quality'] == '正常' and TAG_OK_RE.match(tag):
            terms.append(('tag', tag))
            m = GE_TAG_RE.match(tag)
            if m:
                terms.append(('tag', m.group(1)))
        for k, v in serial_terms(dev_rows.get(dev['alias'], [])):
            terms.append(('serial', v))
            param_of[v] = re.sub(r'^序號參數 |^銘牌序號 \(|\)$', '', k)
        if not terms:
            stats['no_terms'] += 1
            continue
        core = model_core(dev['model'])
        per_cat = collections.defaultdict(list)   # cat -> [(rank, rel, rec, term, kind)]
        for kind, term in terms:
            hits, exact_rx, loose_rx = S.search(term, kind)
            for rel, rec in dedupe_versions(hits).items():
                cat = category(rel)
                doc_id, rev, ref = doc_ref(rel)
                any_exact = any(e for _, _, e in rec['pages'])
                rank = (0 if any_exact else 1, -rec['trust'], 0 if doc_id else 1, [-x for x in rev_key(rev)[:2]], -rec['n'], len(rel))
                per_cat[cat].append((rank, rel, rec, term, kind, exact_rx, loose_rx))
        rows, extracted, seen_rel = [], {}, set()
        for cat in CAT_ORDER:
            lst = sorted(per_cat.get(cat, []), key=lambda x: x[0])
            n_keep = CAT_MAX.get(cat, 2)
            for rank, rel, rec, term, kind, exact_rx, loose_rx in lst:
                if n_keep <= 0 or len(rows) >= a.max_rows:
                    break
                if rel in seen_rel:
                    continue
                seen_rel.add(rel)
                n_keep -= 1
                doc_id, rev, ref = doc_ref(rel)
                pages = sorted({p for p, _, _ in rec['pages'] if p}, key=int)[:6]
                # 命中行：優先取「完整位號」命中的頁
                pg = sorted(rec['pages'], key=lambda x: (0 if x[2] else 1, x[0] or 0))[0]
                txt = S.text(pg[1])
                line, _ = excerpt(txt, exact_rx if pg[2] else loose_rx)
                is_office = rel.lower().endswith(OFFICE_EXT)
                ptxt = '' if is_office or not pages else ' p.' + ','.join(str(p) for p in pages)
                key = 'docsearch|%s|%s' % (doc_id, rev) if doc_id else 'docsearch|%s|' % hashlib.sha1(rel.lower().encode('utf-8')).hexdigest()[:12]
                if key not in docs:
                    d = {'title': os.path.basename(rel), 'folder': os.path.dirname(rel) or '.', 'category': cat, 'trust': TRUST_TAG.get(rec['trust'], '?')}
                    u = lib.url(rel)
                    if u:
                        d['url'] = u
                    docs[key] = d
                lvl = 'factory' if cat in FACTORY_CATS else 'doc'
                hit = ('序號 ' + term) if kind == 'serial' else ('位號' if pg[2] else '位號+字尾（訊號／電纜編號）')
                warn = '；OCR 命中，需開原圖確認' if rec['trust'] < 2 else ('；PyMuPDF 抽字' if rec['trust'] == 2 else '')
                src = '%s · %s%s（全文檢索：%s%s）' % ('出廠' if lvl == 'factory' else '文件', ref, ptxt, hit, warn)
                val = '%s%s｜%s' % (ref, ptxt, line) if line else '%s%s' % (ref, ptxt)
                rows.append([cat, val, lvl, src, {'rule': 'FTS', 'd': key, 'hit': hit, 'pages': pages, 'term': term}])
                cat_stats[cat] += 1
                # ---- 推定值
                if kind == 'serial' and '序號命中（文件）' not in extracted and cat not in ('教材', '其他'):
                    extracted['序號命中（文件）'] = ['%s（AMS %s）' % (term, param_of.get(term, '序號')), lvl,
                                              '%s · %s%s（AMS 序號參數 %s 的值出現在此頁；%s）' % ('出廠' if lvl == 'factory' else '文件', ref, ptxt, param_of.get(term, '序號'), TRUST_TAG.get(rec['trust'], '?')), key, 'FTS-序號']
                    mdl = find_model(txt, core, tag)
                    if mdl and cat in FACTORY_CATS:
                        extracted['出廠型號（文件）'] = [mdl, lvl, '%s · %s%s（序號頁內以 AMS 型號「%s」開頭的字串）' % ('出廠', ref, ptxt, core), key, 'FTS-序號頁型號']
                if kind == 'tag' and cat in ('儀器清單', '規格表') and line:
                    if '型號（文件）' not in extracted:
                        mdl = find_model(line, core, tag)
                        if mdl:
                            extracted['型號（文件）'] = [mdl, lvl, '文件 · %s%s（命中行內以 AMS 型號「%s」開頭的字串）' % (ref, ptxt, core), key, 'FTS-命中行型號']
                    if '廠牌（文件）' not in extracted:
                        vm = VENDOR_RE.search(line)
                        if vm and vendor_consistent(vm.group(1), dev['mfr']):
                            extracted['廠牌（文件）'] = [vm.group(1), lvl, '文件 · %s%s（命中行內的廠牌名，與 AMS 製造商同集團）' % (ref, ptxt), key, 'FTS-命中行廠牌']
                        elif vm:
                            stats['vendor_rejected'] += 1
                    if '量程（文件）' not in extracted:
                        rg = find_range(line, dev['unit'])
                        if rg:
                            extracted['量程（文件）'] = [rg, lvl, '文件 · %s%s（命中行內「下限～上限 單位」，量綱與 AMS 單位相同；%s）' % (ref, ptxt, cat), key, 'FTS-命中行量程']
                if kind == 'tag' and cat == '邏輯圖' and line and '量程（邏輯圖）' not in extracted:
                    rg = find_range(line, dev['unit'])
                    if rg:
                        extracted['量程（邏輯圖）'] = [rg, lvl, '文件 · %s%s（邏輯圖 AI 方塊的量程「lo..hi 單位」）' % (ref, ptxt), key, 'FTS-邏輯圖量程']
        for k, (v, lvl, src, key, rule) in extracted.items():
            rows.append([k, v, lvl, src, {'rule': rule, 'd': key}])
            stats['x:' + k] += 1
        if rows:
            by_alias[dev['alias']] = {'rows': rows, 'terms': [t for _, t in terms]}
            stats['matched'] += 1
        else:
            stats['none'] += 1
        if (i + 1) % 100 == 0:
            print('  %d/%d  %.0fs' % (i + 1, len(devices), time.time() - t0), flush=True)
    for rec in docs.values():
        rec.pop('trust', None)
    out = {
        'generator': 'tools/db/docmap_docsearch.py', 'built': datetime.datetime.now().isoformat(timespec='seconds'),
        'index': {'built': S.built, 'docs': S.n_docs, 'pages': S.n_pages},
        'searched': [{'doc_id': 'hst-docsearch', 'rev': S.built, 'ref': 'hst-docsearch 索引 %s（%d 檔／%d 頁）' % (S.built, S.n_docs, S.n_pages),
                      'title': 'hst_fts.db（SQLite FTS5，頁級）', 'folder': '', 'used': True,
                      'why': '搜現行位號＋AMS 序號參數；位號不採 OCR 命中；排除本站匯出、副本夾、合訂本；同編號取最高版次；每類別 2 份、每台 %d 列' % a.max_rows}],
        'docs': docs, 'by_alias': by_alias,
        'stats': {'devices': len(devices), 'aliases_matched': stats['matched'], 'no_terms': stats['no_terms'], 'none': stats['none'],
                  'rows': sum(len(v['rows']) for v in by_alias.values()), 'docs': len(docs), 'with_url': sum(1 for d in docs.values() if d.get('url')),
                  'per_category': dict(cat_stats), 'extracted': {k[2:]: v for k, v in stats.items() if k.startswith('x:')}, 'vendor_rejected': stats['vendor_rejected'],
                  'notes': ['位號經 OCR 的命中不採用（hst-docsearch pitfalls #1）', '推定值（型號／廠牌／量程／序號）由命中行或命中頁以規則抽出，僅供對照，不列入 DCS 比對',
                            '廠牌推定須與 AMS 製造商同集團、量程推定須與 AMS 單位同量綱（清單 PDF 文字層常把鄰列併在一行）']},
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    data = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    if re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]|\\Users\\|/Users/|我的雲端硬碟', data):
        raise SystemExit('輸出含本機絕對路徑，中止')
    with open(a.out, 'wb') as f:
        f.write(data.encode('utf-8'))
    print('docsearch: %d 台有命中／%d（無搜尋詞 %d、無命中 %d），%d 列，%d 份文件（%d 有 Drive 連結），%.0fs → %s' % (
        stats['matched'], len(devices), stats['no_terms'], stats['none'], out['stats']['rows'], len(docs), out['stats']['with_url'], time.time() - t0, a.out))
    print(json.dumps(out['stats'], ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
