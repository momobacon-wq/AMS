# -*- coding: utf-8 -*-
"""mov_site.py — 把「AUMA 電動閥 MOV LIST」（v3.5 起；本機 xlsx，Google 雲端硬碟上那一份）併進 docs/db 站（v26）。

  py tools/db/mov_site.py docs/db/data                 # 資料加密中 → 自動解密、套用、重算 build、加密（stamp 交給 rebuild.py）
  py tools/db/mov_site.py docs/db/data --keep-plain    # 只套用、不加密
  options: --xlsx X（預設 paths.MOV_XLSX）  --no-drive-map  --dcdas I（一號機索引）  --dcdas-u2 I（二號機索引）  --ge-tags J

做的事（冪等；重跑先移除上一次加入的東西）：
- 側欄群組「電動閥清單」：62 電動閥主表（823 列）、63 儀資組備品採購清單、64 儀資組備品逐台、65 電動閥兩讀並列、66 電動閥推翻紀錄、
  67 未入表與別名、68 AUMA 備品件號對照；00_說明 目錄與閱讀註記、manifest、頁數。
- 查詢卡：02.json `mov`（位號索引、別名、建議清單、未入表）＋ card/mov-NN.json（每 PER 列一檔：卡上欄位與逐格出處、signal-atlas 訊號、
  GE 編號、氣動閥清單刪除紀錄的回指；開卡才載），檔名登記在 card/index.json `mov.files`（verify_encrypted 認得）。
- 逐格出處依序：逐格查證明細該格（文件、PDF 頁、印刷頁、原文、裁決、證據等級）→ 本列的「…文件來源」欄 → 同組代表位號的那一格
  （只在兩台的值去掉機組碼後相同時；不同就不借）→ 本列主要資料來源 → 未記。儀資組 72 台的位置回授、序號、控制單元與位置回授備品件號
  以「儀資組備品_逐台」為準（試算表自己寫的：比主表新）。
必須在 pneuvalve_site 之後跑（00 目錄、群組都接在氣動閥清單後面）；rebuild.py 已把它接在兩條路徑的最後，--only-pneuvalve 之後也會跑。

輸入檢查都在動資料目錄之前：xlsx、必要分頁、表頭列、位號不重複——任何一項不對就中止，網站資料不變。
"""
import argparse
import collections
import glob
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import encrypt_data  # noqa: E402
import extract_db  # noqa: E402
import paths  # noqa: E402
import pneuvalve_site as PV  # noqa: E402
from site_terms import T  # noqa: E402

GROUP = '電動閥清單'
AFTER_GROUPS = ('氣動閥清單', '設備與位置')
TAB_COLOR = '#1F6E8C'
SHEETS = collections.OrderedDict([('62', '電動閥主表'), ('63', '儀資組備品採購清單'), ('64', '儀資組備品逐台'), ('65', '電動閥兩讀並列'),
                                  ('66', '電動閥推翻紀錄'), ('67', '未入表與別名'), ('68', 'AUMA備品件號對照')])
IDS = list(SHEETS)
LIST_URL = T('https://docs.google.com/spreadsheets/d/⟦MOV_LIST_ID⟧/edit')
CHUNK_FMT = 'card/mov-%02d.json'
PER = 100
TAG = 'Valve Tag No.'
SIG_BASE = {'u1': 'https://momobacon-wq.github.io/signal-atlas/#/v/', 'u2': 'https://momobacon-wq.github.io/signal-atlas/u2/#/v/'}
UNIT_SITE = {'G11': 'u1', 'G12': 'u1', 'C10': 'u1', 'C00': 'u1', 'G21': 'u2', 'G22': 'u2', 'C20': 'u2'}
REQ = ['MOV LIST', '逐格查證明細', '儀資組備品採購清單', '儀資組備品_逐台', '儀資組維護_含待確認', 'v3待確認_未入表', '備品件號對照_查證', '查證圖例']

# 查詢卡欄位：(分組, 標籤, MOV LIST 的 Excel 欄號)
FIELDS = [
    ('識別與分類', '閥門名稱（中文）', 4), ('識別與分類', '閥門名稱 (EN)', 3), ('識別與分類', '系統', 5), ('識別與分類', '控制分類', 7),
    ('識別與分類', '動作型態', 8), ('識別與分類', '閉迴路閥位分級', 70), ('識別與分類', '儀資組維護', 71),
    ('執行器', '執行器型號', 9), ('執行器', '控制頭', 10), ('執行器', '減速機／傳動機構', 11), ('執行器', '輸出法蘭', 12), ('執行器', '防爆等級', 13),
    ('閥體', '閥型', 24), ('閥體', '閥瓣型式', 25), ('閥體', '閥體廠牌', 26), ('閥體', '口徑 (DN)', 27), ('閥體', '壓力等級', 28),
    ('閥體', '設計壓力 (MPaG)', 29), ('閥體', '設計溫度 (℃)', 30),
    ('動作與控制', '馬達功率 (kW)', 31), ('動作與控制', '開啟時間 (s)', 32), ('動作與控制', '關閉時間 (s)', 33), ('動作與控制', '位置回授', 35),
    ('動作與控制', '中間位置', 36), ('動作與控制', '控制指令', 37),
    ('動作與控制', '停止方式（限位／扭力）／閥座', 34),   # 正本 Seating Type 欄：多數寫執行器在開／關端是限位還是扭力停，少數寫閥座材質
    ('電源與扭力', '電源盤（MCC）', 38), ('電源與扭力', '扭力設定 開 (N·m)', 39), ('電源與扭力', '扭力設定 關 (N·m)', 40),
    ('電源與扭力', '閥需求扭力 (N·m)', 41), ('電源與扭力', '執行器扭力 (N·m)', 42),
    ('圖面與序號', 'P&ID', 43), ('圖面與序號', '序號 (Works No.)', 44),
    ('備品件號', '控制單元 備品件號', 14), ('備品件號', '控制單元 物料編號', 15), ('備品件號', '開關（單）備品件號', 16), ('備品件號', '開關（單）物料編號', 17),
    ('備品件號', '開關（Tandem）備品件號', 18), ('備品件號', '開關（Tandem）物料編號', 19), ('備品件號', 'RWG 板 備品件號', 20),
    ('備品件號', 'RWG 板 物料編號', 21), ('備品件號', '減速齒輪 備品件號', 22), ('備品件號', '減速齒輪 物料編號', 23),
]
# 值欄 → 本列的「…文件來源(2026-10-18查證)」欄（Excel 欄號；65／66 表頭文字相同，一律以位置取）
SRC_COL = {9: 49, 10: 50, 11: 51, 12: 52, 13: 53, 14: 54, 15: 54, 16: 55, 17: 55, 18: 56, 19: 56, 20: 57, 21: 57, 22: 58, 23: 58,
           31: 59, 32: 60, 33: 61, 35: 62, 36: 63, 37: 64, 39: 65, 40: 66, 42: 67, 44: 68}
# 62 主表輸出的 Excel 欄（其餘不輸出：46 備註與 49–69 逐格來源／查證摘要留在正本，48 供證筆記本是建置用）
MAIN_COLS = list(range(1, 45)) + [70, 71, 72, 73, 47, 45]
# 儀資組 72 台：逐台分頁比主表新的欄（主表 Excel 欄 → 逐台 欄號 1-based）
UNIT_OVR = {35: 8, 44: 11, 14: 13, 20: 14}
UNIT_EXTRA = [('儀資組備品', '接線圖代碼', 9), ('儀資組備品', '馬達型號', 10), ('儀資組備品', '序號來源', 12),
              ('儀資組備品', '要抄銘牌的項目', 15), ('儀資組備品', '其他要現場看的／兩讀', 16)]
BANDS = [('識別', 1), ('名稱與分類', 3), ('執行器', 9), ('備品件號', 14), ('閥體', 24), ('動作與控制', 31), ('電源與扭力', 38),
         ('圖面與序號', 43), ('閉迴路分級（Mark VIe 程式碼）', 70), ('來源', 47)]
BAND_COLORS = ['#1F4E79', '#2E75B6', '#1F6E8C', '#7F7F7F', '#548235', '#8B5A00', '#7030A0', '#404040', '#C55A11', '#404040']

# ------------------------------------------------------------------ 清洗（讀進來就做：出處欄、逐格明細的原文都經過這裡）
TRAIN_FILE_RE = re.compile(r'(?:受訓資料[\\/])?MOV LIST 2020_04_22\S*?\.xlsx')   # 林口電廠 2020 年備品清單（檔名帶整理者，不出貨）
TRAIN_LABEL = '林口電廠 MOV LIST 備品清單（2020-04-22 整理本）'
GESCRAPE_RE = re.compile(r'ge-scrape[\\/](?:[^\\/\s；;，,]+[\\/])*')
REPORT_RE = re.compile(r'(?:@@新機組資料備份[\\/])?claude[\\/][^\s；;，,）)」]+\.md')
WORKFLOW_RE = re.compile(r'\s*[(（]?\bwf_[0-9a-f]{6,}[^)）\s]*[)）]?|\bsession [0-9a-f]{8}\w*')
# NotebookLM 時期的筆記本註記：「(SCR煙氣分析NB)」「(03_HRSG(4)NB)」（括號可巢狀一層、NB 前面常緊貼中文）、「[回驗✓:… NB]」、「08_配管_閥門_part1 NB → 」
NB_PAREN_RE = re.compile(r'\s*[(（](?:[^()（）]|[(（][^()（）]*[)）]){0,120}?(?:NotebookLM|(?<![A-Za-z])NB(?![A-Za-z])|口供|筆記本)[^()（）]{0,40}?[)）]'
                         r'|\s*\[[^\[\]]{0,160}?(?:NotebookLM|(?<![A-Za-z])NB(?![A-Za-z])|口供)[^\[\]]{0,160}?\]'
                         r'|[^；;→\n]{0,60}?(?<![A-Za-z])NB\s*→\s*')
NB_RE = re.compile(r'NotebookLM|(?<![A-Za-z])NB(?![A-Za-z])|口供|筆記本')
UNITSTR_RE = re.compile(r'〔機組碼由[^〕]*〕')
# 出貨前最後一道：寫出的 JSON 任何一處命中就中止（名字樣式＝「(XX整理)」「_X註解」，不把人名寫進程式）
FORBID_RE = re.compile(r'[(（][^()（）"]{1,6}整理[)）]|_[^\s_/\\"]{1,4}註解|MOV LIST 2020\s*[(（][^()（）\s]{1,6}[)）]|scratchpad|Temp[\\/]{1,2}claude|\.claude[\\/]|'
                       r'claude[\\/]{1,2}[^"\s]*\.md|主控親讀|\bwf_[0-9a-f]{6,}|session [0-9a-f]{8}')


def scrub(s):
    if not isinstance(s, str):
        return s
    s = PV.scrub_local(s)
    s = TRAIN_FILE_RE.sub(TRAIN_LABEL, s)
    s = GESCRAPE_RE.sub('', s)
    s = REPORT_RE.sub('內部查證報告', s)
    s = s.replace('（主控親讀）', '（親讀原文）').replace('主控親讀', '親讀原文')
    s = WORKFLOW_RE.sub('', s)
    return s


def nb_strip(s):
    """NotebookLM 時期的筆記本註記拿掉（只拿註記本身：文件名、分隔符照原樣；拿完是空字串才回 None）。
    以前整段（；分隔）丟掉，會連同一段裡的文件編號一起丟（驗證：45 欄 78 列少了文件、12 列變空白）。"""
    if not isinstance(s, str):
        return s
    out = NB_PAREN_RE.sub('', s).strip()
    out = re.sub(r'\s*/\s*(?=$|[；;])', '', out)          # 「A / B」兩邊註記拿掉後殘留的斜線
    return out or None


def clean(v):
    v = PV.clean(scrub(v) if isinstance(v, str) else v)
    return v


def compact(s):
    return PV.compact(s)


def norm_val(v):
    """比照判斷用：去掉〔機組碼由…〕、機組前綴、空白。"""
    s = UNITSTR_RE.sub('', str(v or ''))
    s = re.sub(r'\b[CGS]\d\d(?=[A-Z]{3}\d\d)', '', s)
    return re.sub(r'\s+', '', s)


# ------------------------------------------------------------------ 讀檔
def read_book(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        out[ws.title] = [[scrub(v) if isinstance(v, str) else v for v in r] for r in ws.iter_rows(values_only=True)]
    return out


def find_header(rows, col, text, within=12):
    for i, r in enumerate(rows[:within]):
        if len(r) > col and str(r[col] or '').strip() == text:
            return i
    raise SystemExit('!! 找不到表頭（第 %d 欄「%s」，前 %d 列內）' % (col + 1, text, within))


def table(rows, hi, stop_blank=True):
    hdr = [str(h).strip() if h is not None else '' for h in rows[hi]]
    while hdr and not hdr[-1]:
        hdr.pop()
    out, tail = [], []
    for r in rows[hi + 1:]:
        r = list(r[:len(hdr)]) + [None] * (len(hdr) - len(r))
        if not any(v not in (None, '') for v in r):
            if stop_blank and out:
                stop_blank = 'done'
            continue
        if stop_blank == 'done':
            tail.append(r)
        else:
            out.append(r)
    return hdr, out, tail


def load_inputs(path):
    """讀 xlsx 並檢查（任何一項不對就中止——還沒動資料目錄）。"""
    if not path or not os.path.exists(path):
        raise SystemExit('!! 找不到電動閥清單 xlsx：%s（--xlsx 或環境變數 AMS_MOV_XLSX）' % path)
    bk = read_book(path)
    miss = [s for s in REQ if s not in bk]
    if miss:
        raise SystemExit('!! xlsx 缺分頁：%s' % '、'.join(miss))
    W = {}
    rows = bk['MOV LIST']
    hi = find_header(rows, 1, TAG)
    hdr = [str(h) if h is not None else '' for h in rows[hi]]
    data = [list(r[:len(hdr)]) + [None] * (len(hdr) - len(r)) for r in rows[hi + 1:] if any(v not in (None, '') for v in r)]
    if len(hdr) < 73:
        raise SystemExit('!! MOV LIST 表頭只有 %d 欄（預期 73）' % len(hdr))
    tags = [str(r[1] or '').strip() for r in data]
    if not all(re.fullmatch(r'[CG]\d\d[A-Z]{3}\d\d[A-Z]{2}\d{3}', t) for t in tags):
        bad = [t for t in tags if not re.fullmatch(r'[CG]\d\d[A-Z]{3}\d\d[A-Z]{2}\d{3}', t)]
        raise SystemExit('!! MOV LIST 有不是 13 碼 KKS 的位號：%s' % '、'.join(bad[:10]))
    if len(set(tags)) != len(tags):
        dup = [t for t, n in collections.Counter(tags).items() if n > 1]
        raise SystemExit('!! MOV LIST 位號重複：%s' % '、'.join(dup[:10]))
    W['hdr'], W['rows'], W['tags'] = hdr, data, tags
    W['pos'] = {t: i for i, t in enumerate(tags)}
    ev = bk['逐格查證明細']
    if str(ev[0][0]).strip() != 'Tag':
        raise SystemExit('!! 逐格查證明細第 1 列不是表頭（Tag…）')
    eh = [str(h) for h in ev[0]]
    E = {}
    for r in ev[1:]:
        if not r or not r[0]:
            continue
        d = dict(zip(eh, r))
        k = (str(d['Tag']).strip(), int(d['col']))
        if k in E:
            raise SystemExit('!! 逐格查證明細 (Tag, col) 重複：%s' % (k,))
        E[k] = d
    W['eh'], W['ev'] = eh, E
    for key, sheet, col, text in (('buy', '儀資組備品採購清單', 0, '項次'), ('unit', '儀資組備品_逐台', 1, TAG), ('maint', '儀資組維護_含待確認', 1, TAG),
                                  ('out', 'v3待確認_未入表', 0, '位號'), ('parts', '備品件號對照_查證', 0, '機型 family')):
        rws = bk[sheet]
        h = find_header(rws, col, text)
        hd, body, tail = table(rws, h)
        W[key] = {'pre': [r for r in rws[:h] if any(v not in (None, '') for v in r)], 'hdr': hd, 'rows': body, 'tail': tail}
    W['legend'] = [r for r in bk['查證圖例'][1:] if r and r[0]]
    W['tier_text'] = [str(r[0]) for r in bk.get('閉迴路分級說明', []) if r and r[0]]
    return W


# ------------------------------------------------------------------ 文件 → 雲端連結
class Docs:
    def __init__(self, drive):
        self.drive = drive
        self.docs = {}
        self.by_base = collections.defaultdict(list)
        if drive:
            for rel in drive['files']:
                if PV_COPY(rel):
                    continue
                self.by_base[rel.rpartition('/')[2]].append(rel)
        self.wanted = {}

    def key(self, text):
        """出處字串（第一份文件）→ docs key 或 None。
        有副檔名的（…pdf／xlsx／xls…）：取到副檔名為止（後面的「（Overall Electrical Loadlist）」「xlsx 第N列」是說明），文件庫相對路徑整串對，
        只有檔名時檔名在文件庫唯一才對；對不到就不給連結——**不再退回文件編號**：HT0-1-EQE01-C0001-Attachment.xlsx 退回編號會開到同編號的另一份
        （Protection Coordination Study PDF；驗證 2026-11-17：1,477 格開錯）。沒有副檔名的才以 HT 文件編號解析（resolve_wanted）。"""
        if not text or not self.drive:
            return None
        first = re.split(r'[；;]| ∥ | ／ |＋', str(text))[0].strip()
        first = re.sub(r'\s+PDF\s*p\..*$', '', first).strip()
        m = re.match(r'(.*?\.(?:pdf|xlsx|xlsm|xls|docx|doc|csv|txt))(?![A-Za-z0-9])', first, re.I)
        if m:
            files = self.drive['files']
            rel = m.group(1).replace('\\', '/').strip('/').strip()
            fid = files.get(rel.lower())
            if not fid:
                c = self.by_base.get(rel.rpartition('/')[2].lower(), [])
                if len(c) == 1:
                    rel, fid = c[0], files[c[0]]
            if not fid:
                return None
            k = 'file|' + rel.lower()
            if k not in self.docs:
                fo, _, base = rel.rpartition('/')
                self.docs[k] = {'title': base, 'folder': fo or '.', 'url': 'https://drive.google.com/open?id=%s' % fid}
            return k
        nos = PV.DOCNO_RE.findall(first.upper())
        if len({n for n, _r in nos}) != 1 or 'ATTACHMENT' in first.upper():   # 一段裡有兩份以上文件（EKU／EKB 數據表）就不猜是哪一份
            return None
        no, rev = nos[0]
        self.wanted.setdefault(no, set()).add(rev or '')
        return 'no|' + no

    def finish(self):
        """HT 文件編號 → 文件庫那一份（build_card_aux.resolve_wanted 同規則）；回傳 {'no|編號': docs key}。"""
        if not self.drive or not self.wanted:
            return {}
        import build_card_aux
        got = build_card_aux.resolve_wanted(self.wanted, self.docs, self.drive)
        return {'no|' + no: k for no, k in got.items()}


def PV_COPY(rel):
    import build_card_aux
    return bool(build_card_aux.COPY_PATH_RE.search('/' + rel))


# ------------------------------------------------------------------ 逐格出處
FACTORY_RE = re.compile(r'AQ[ABPC]01-[QT]\d{4}|EOMR|End of Manufacturing|出廠|3\.1 證書|EN ?10204', re.I)


def doc_label(doc):
    """出處文件欄 → 卡上顯示的文件名：只看第一份（∥／；之前）；是帶副檔名的路徑才取檔名，描述文字（內含 GE 圖號的斜線）照原樣。"""
    d = re.split(r'[；;]| ∥ ', str(doc or '').strip())[0].strip()
    if not d or d.startswith('查證範圍'):
        return d
    m = re.match(r'(.*?\.(?:pdf|xlsx|xlsm|xls|docx|doc|csv|txt))(?![A-Za-z0-9])(.*)$', d, re.I)
    if m and '/' in m.group(1).replace('\\', '/'):
        return m.group(1).replace('\\', '/').rpartition('/')[2] + m.group(2)
    return d


def ev_src(ev, D, via=None):
    """逐格查證明細的一列 → [lvl, text, docKey, two, detail]。裁決＝比照（照另一台的證書／文件）一律標推論，不是本機的出廠證據。"""
    g = lambda k: ev.get(k) if ev.get(k) not in (None, '') else None   # noqa: E731
    verdict, level, doc = g('裁決') or '', g('證據等級') or '', g('文件')
    pdf, prn, quote, seen, chk, alt = g('PDF頁'), g('印刷頁/Sheet'), g('原文引句'), g('看過圖'), g('驗證員'), g('其他證據(互證/異值)')
    lvl = 'inferred' if (via or verdict == '比照') else ('factory' if doc and FACTORY_RE.search(str(doc)) else 'doc')
    lab = extract_db.SRC_PREFIX[lvl]
    where = doc_label(doc)
    if pdf:
        where += ' PDF p.%s' % pdf
    if prn and str(prn) != str(pdf):
        where += '（%s）' % prn
    if len(where) > 170:                       # 很長的頁碼（IO_Signal 列號清單）不可把裁決、等級擠出卡上的字數
        where = where[:170] + '…'
    bits = [b for b in (verdict, level and '證據等級 ' + level, '看過圖' if seen == 'Y' else '', chk and '驗證 ' + str(chk)) if b]
    head = ('比照 %s：' % via) if via else ''
    text = '%s · %s%s%s' % (lab, head, where or '查證範圍內的文件都不載', ('；' + '、'.join(bits)) if bits else '')
    detail = []
    if quote:
        detail.append(['原文', str(quote)[:500]])
    if pdf and len(str(pdf)) > 60:
        detail.append(['PDF 頁（全文）', str(pdf)[:400]])
    two = None
    if verdict == '兩讀':
        two = str(alt)[:500] if alt else '兩種讀法並列在值裡（∥ 前後）'
    elif alt:
        detail.append(['其他證據', str(alt)[:400]])
    return [lvl, text, D.key(doc), two, detail or None]


def cell_src(i, c, W, D, rep_of, ev_by_tag):
    """第 i 列（0-based）Excel 欄 c 的出處。"""
    r = W['rows'][i]; tag = W['tags'][i]; E = W['ev']; pos = W['pos']; j = c - 1
    v = r[j]
    ev = E.get((tag, j))
    if ev:
        return ev_src(ev, D)

    def borrow(rep):
        """代表位號 rep 的那一格查證列——只在兩台的值去掉機組碼後相同時才借（不同就是本機自己的值，不能掛別人的原文）"""
        if not rep or rep == tag or rep not in pos:
            return None
        rv = E.get((rep, j))
        return rv if rv is not None and norm_val(v) == norm_val(W['rows'][pos[rep]][j]) else None
    sc = SRC_COL.get(c)
    st = r[sc - 1] if sc else None
    st = None if st in (None, '', '—', '-') else str(st)
    if st:
        m = re.match(r'比照一號機\s*([CG]\d\d[A-Z]{3}\d\d[A-Z]{2}\d{3})\s*[：:]\s*(.*)$', st)
        if m:
            rv = borrow(m.group(1))
            return ev_src(rv, D, via=m.group(1)) if rv else ['inferred', '推論 · 比照 %s：%s' % (m.group(1), m.group(2)[:300]), D.key(m.group(2)), None, None]
        lvl = 'factory' if FACTORY_RE.search(st) else 'doc'
        return [lvl, '%s · %s（本列的文件來源欄，2026-10-18 查證）' % (extract_db.SRC_PREFIX[lvl], st[:300]), D.key(re.sub(r'^\[[^\]]*\]\s*', '', st)), None, None]
    rv = borrow(rep_of.get(tag))
    if rv:
        return ev_src(rv, D, via=rep_of[tag])
    main = r[46]
    if main:
        lvl = 'factory' if FACTORY_RE.search(str(main)) else 'doc'
        docs = nb_strip(r[44]) if r[44] else None
        # 列層級的出處常一次列好幾份文件：只有恰好一份時才給連結（EKB 列第一份是 EKU 的數據表——猜第一份會開錯）
        n_docs = len({n for n, _r in PV.DOCNO_RE.findall(str(docs or '').upper())}) + len(re.findall(r'\.(?:pdf|xlsx|xlsm|xls|docx|doc)\b', str(docs or ''), re.I))
        return [lvl, '%s · 本列主要資料來源：%s%s' % (extract_db.SRC_PREFIX[lvl], str(main)[:200], ('；出處文件 ' + str(docs)[:200]) if docs else ''),
                D.key(docs) if docs and n_docs == 1 else None, None, None]
    return ['doc', '文件 · 本列未記出處', None, None, None]


def tier_src(r, c):
    basis = clean(r[71]) or ''
    lev = str(r[72] or '')
    lvl = 'ctrl' if lev.startswith('定讞') and '比照' not in lev else 'inferred'   # 三號機「定讞；比照」＝比照一、二號機的程式碼，不是本機的
    return [lvl, '%s · 程式碼依據（2026-10-25 依當時的 checkout 寫的，行號可能已與現行索引不同）：%s；分級證據等級 %s'
            % (extract_db.SRC_PREFIX[lvl], str(basis)[:400], lev or '未記'), None, None, None]


# ------------------------------------------------------------------ signal-atlas
KIND = {'Contact': 'DI', 'Relay': 'DO', 'AnalogInput': 'AI', 'AnalogOutput': 'AO'}


def sig_index(path):
    if not path or not os.path.exists(path):
        return None
    c = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    out = collections.defaultdict(list)
    for ctrl, pt, dt, st, vn, vd in c.execute('select p.ctrl, p.name, p.device_tag, p.signal_type, v.name, v.description from io_point p '
                                               'join variable v on v.id = p.var_id where p.device_tag is not null and p.device_tag <> ""'):
        out[str(dt).strip().upper()].append((ctrl, pt, KIND.get(st, st or ''), vn, (vd or '').split('\n')[0][:80]))
    c.close()
    return out


def sigs_for(tag, unit, aliases, idx):
    """→ [[site, ctrl, var, kind, point, desc, how]]（DO、DI、AI、AO 依序，最多 10 筆）"""
    site = UNIT_SITE.get(unit)
    if not site or not idx.get(site):
        return []
    I = idx[site]
    got = []
    for dt, how in [(tag, '')] + aliases:
        for x in I.get(dt.upper(), []):
            if not any(g[1] == x[0] and g[2] == x[3] for g in got):
                got.append([site, x[0], x[3], x[2], x[1], x[4], how])
    order = {'DO': 0, 'DI': 1, 'AI': 2, 'AO': 3}
    got.sort(key=lambda g: (order.get(g[3], 9), g[1], g[4]))
    return got[:10]


# ------------------------------------------------------------------ 別名（文件寫法不同的同一顆閥）
def build_aliases(W, ge):
    """→ (alias {compact: [[row, grade, note], …]}, dev_alias {row: [(device_tag, how)]}, ge_of {row: [GE 編號…]})"""
    tags = W['tags']; rows = W['rows']; pos = {t: i for i, t in enumerate(tags)}
    alias = collections.defaultdict(list); dev = collections.defaultdict(list); ge_of = collections.defaultdict(list)

    def add(key, i, grade, note):
        k = compact(key)
        if k in {compact(t) for t in tags}:
            return            # 本身就是清單另一列的位號：不搶（例：偶數機的 LAB90 本來就列）
        if not any(x[0] == i for x in alias[k]):
            alias[k].append([i, grade, note])
    n = collections.Counter()
    for i, t in enumerate(tags):
        u, core = t[:3], t[3:]
        basis = str(rows[i][71] or '')
        if core == 'HNE11AA001':
            k = u + 'HBK11QM001'
            if 'HBK11QM001' in basis or u[1] == '3':
                add(k, i, '強', '控制器與氣動閥清單 v2.6 刪除紀錄都用 %s 這個位號（清單「程式碼依據」欄：在 DCS 用 HBK11QM001）；%s 是另一顆（密封空氣），不是別名' % (k, u + 'HBK11QM011'))
                dev[i].append((k, '控制器用 %s' % k)); n['HNE11'] += 1
        elif core in ('LAB91QM003', 'LAB91QM004') and int(u[2]) % 2 == 1:
            k = u + 'LAB90' + core[5:]
            add(k, i, '文件互相矛盾', '清單依 EM25 負載表把奇數機改成 LAB91（2026-08-18）；控制器與一號機接線圖仍寫 %s——兩份文件不一致，本站兩個位號都收、不替文件選' % k)
            dev[i].append((k, '控制器用 %s（與清單寫法不同）' % k)); n['LAB91'] += 1
        elif core == 'LAE60QM002':
            k = u + 'LAE60QM001'
            add(k, i, '推論', '清單自評「LAE60QM001 是 QM002 的別名，待現場銘牌」（v3待確認_未入表）；接線圖上 %s 的說明是 SOV，也可能是另一顆' % k)
            dev[i].append((k, '推論：%s 可能是同一顆' % k)); n['LAE60'] += 1
        elif re.fullmatch(r'PAA[1-4]0MB001', core) and u[0] == 'C':
            k = u + core[:5] + 'QM001'
            add(k, i, '清單定讞', '清單「說明與殘差」：D1806 把碎屑排放閥寫作 PAA…QM001，與本列 MB001 是同一設備的文件別名'); n['PAA'] += 1
    # GE 對照表：KKS 本體相同的 GE 編號（同一設計各機組同一個 GE 編號）。汽機範圍的 GE 文件寫 S 機組碼（S10MAC10QM021），
    # 本清單寫 C 機組碼（C10MAC10QM021）：S 寫法另收為別名（定讞：GE 對照表、控制器 I/O、氣動閥清單刪除紀錄三方都寫 S／無機組碼）
    by_core = collections.defaultdict(list)
    for i, t in enumerate(tags):
        by_core[t[3:]].append(i)
    for e in (ge or {}).get('entries', []):
        letter = 'S' if str(e.get('system') or '').startswith('ST') else 'G'     # GE 對照表的 KKS 多半不帶機組碼；範圍 ST → S 機組碼
        kks = set(e.get('kks') or []) | {x.get('kks') for x in e.get('items') or [] if x.get('kks')}
        for kk in sorted(k for k in kks if k):
            m = re.fullmatch(r'(?:([GSC])\d\d)?([A-Z]{3}\d\d[A-Z]{2}\d{3})', str(kk).upper())
            if not m:
                continue
            core = m.group(2)
            for i in by_core.get(core, []):
                t = tags[i]
                if not (t[0] == letter or (letter == 'S' and t[0] == 'C' and t[1:3] in ('10', '20', '30'))):
                    continue
                if e['tag'] not in ge_of[i]:
                    ge_of[i].append(e['tag'])
                if letter == 'S' and t[0] == 'C':
                    s_tag = 'S' + t[1:3] + core
                    add(s_tag, i, '定讞', 'GE 對照表 %s、控制器 I/O 與氣動閥清單刪除紀錄都寫 S 機組碼或不寫機組碼（%s）；本清單寫 %s' % (e['tag'], s_tag, t))
                    dev[i].append((core, '控制器 I/O 寫無機組碼的 %s' % core))
                    dev[i].append((core + '-MA01', '控制器 I/O 寫 %s-MA01' % core))
                    n['GE-S'] += 1
    for i in list(dev):
        seen = set(); dev[i] = [x for x in dev[i] if not (x[0] in seen or seen.add(x[0]))]
    return dict(alias), dict(dev), dict(ge_of), dict(n)


def out_of_list(W):
    """v3待確認_未入表 → (alias 增補 [(key, row, grade, note)], out {compact: 說明})"""
    tags = W['tags']; pos = {t: i for i, t in enumerate(tags)}
    hd = W['out']['hdr']; add, out = [], {}
    for r in W['out']['rows']:
        d = dict(zip(hd, r))
        raw, verdict, why, sug = str(d.get('位號') or ''), str(d.get('判定') or ''), str(d.get('理由/證據') or ''), str(d.get('建議') or '')
        m = re.match(r'\s*((?:[CG]\d\d/)*[CG]\d\d)\s*([A-Z]{3}\d\d[A-Z]{2}\d{3})', raw)
        keys = [u + m.group(2) for u in m.group(1).split('/')] if m else [raw]
        if 'G2x/G3x' in raw and m:
            keys += [u + m.group(2) for u in ('G21', 'G22', 'G31', 'G32') if u + m.group(2) not in keys]
        tgt = re.search(r'([CG]\d\d[A-Z]{3}\d\d[A-Z]{2}\d{3})', sug if '舊號' in sug else why if '代表' in why else '')
        for k in keys:
            if tgt and tgt.group(1) in pos and k != tgt.group(1):
                add.append((k, pos[tgt.group(1)], '舊位號' if '舊號' in sug else '併入代表', '%s：%s（v3待確認_未入表）' % (verdict, sug or why[:120])))
            elif '別名' not in verdict:
                cut = lambda s, n: s if len(s) <= n else s[:n].rstrip() + '…'   # noqa: E731
                out[compact(k)] = '電動閥清單沒有收 %s：%s；%s%s（全文見 67 頁）' % (k, verdict, cut(why, 260), ('；建議：' + cut(sug, 140)) if sug else '')
    return add, out


# ------------------------------------------------------------------ 輸出
def col_meta(label, values, hidden=False):
    d = PV.col_meta(label.replace('\n', ' '), values)
    d['label'] = label
    if re.search(r'Tag|位號', label):
        d['mono'] = True
    if hidden:
        d['hidden'] = True
    return d


def table_json(sid, short, title, hdr, rows, notes, bands=None, facets=(), key_col=0, ui_extra=None, hidden=()):
    cols = [col_meta(h, [(r[j]['t'] if isinstance(r[j], dict) else r[j]) for r in rows], h in hidden) for j, h in enumerate(hdr)]   # 連結格以顯示字算寬
    fac = [hdr.index(c) for c in facets if c in hdr and 1 < len({str(r[hdr.index(c)]) for r in rows}) <= 40 and len(rows) > 20]
    if not bands:
        bands = [{'label': title[:60], 'from': 0, 'to': max(0, len(cols) - 1), 'bg': '#1F6E8C', 'fc': '#FFFFFF'}]
    ui = {'default_sort': None, 'facets': fac, 'search_cols': None, 'alias_col': None, 'key_col': key_col}
    ui.update(ui_extra or {})
    return {'id': sid, 'name': '%s_%s' % (sid, short), 'mode': 'table', 'title': '%s_%s' % (sid, short), 'notes': notes,
            'header_cells': [{'r': 1, 'c': 1, 'v': {'t': '⌂ 目錄', 'l': {'s': '00', 'r': 1}}}], 'bands': bands, 'columns': cols,
            'freeze_cols': 2 if key_col <= 1 else 1, 'rows': rows, 'styles': [], 'cell_styles': [], 'row_styles': [], 'ui': ui}


def remove_previous(data, man):
    for sid in IDS:
        p = os.path.join(data, 'sheets', sid + '.json')
        if os.path.exists(p):
            os.remove(p)
    for p in glob.glob(os.path.join(data, 'card', 'mov-*.json')):
        os.remove(p)
    man['sheets'] = [s for s in man['sheets'] if s['id'] not in IDS]
    man['groups'] = [g for g in man.get('groups', []) if g != GROUP]


def patch_00(data, entries):
    """00_說明：目錄列接在目錄最後、閱讀註記接在最後（同 pneuvalve_site.patch_00，認的是本模組的頁）。"""
    p = os.path.join(data, 'sheets', '00.json')
    g = PV.load_json(p)
    ours = set(IDS)

    def links_ours(row):
        return any(isinstance(c, dict) and isinstance(c.get('l'), dict) and c['l'].get('s') in ours for c in row.get('cells', []))
    removed = sorted(r['r'] for r in g['rows'] if links_ours(r))
    up = lambda r0: r0 - sum(1 for x in removed if x < r0)   # noqa: E731
    rows = [dict(row, r=up(row['r'])) for row in sorted(g['rows'], key=lambda x: x['r']) if not links_ours(row)]
    g['sections'] = [dict(s, r=up(s['r'])) for s in g['sections']]
    sec4 = next(s for s in g['sections'] if s['label'].startswith('4'))
    toc_rows = [r for r in rows if r['r'] < sec4['r'] and any(isinstance(c, dict) and c.get('c') == 2 and isinstance(c.get('l'), dict) for c in r['cells'])]
    ins = max(r['r'] for r in toc_rows) + 1
    st = {c['c']: c.get('s') for c in toc_rows[-1]['cells']}
    new = []
    for k, e in enumerate(entries):
        new.append({'r': ins + k, 'cells': [{'c': 2, 'v': e['name'], 's': st.get(2), 'l': {'s': e['id'], 'r': None}}, {'c': 3, 'v': e['desc'], 's': st.get(3)},
                                            {'c': 4, 'v': e['row_unit'], 's': st.get(4)}, {'c': 5, 'v': e['rows'], 's': st.get(5)}, {'c': 6, 'v': e['cols'], 's': st.get(6)},
                                            {'c': 7, 'v': e['sources'], 's': st.get(7)}]})
    n = len(new)
    rows = [dict(r, r=r['r'] + n) if r['r'] >= ins else r for r in rows]
    g['sections'] = [dict(s, r=s['r'] + n) if s['r'] >= ins else s for s in g['sections']]
    last = max(r['r'] for r in rows)
    note_style = None
    for r in rows:
        for c in r['cells']:
            if c.get('c') == 3 and c.get('cs') == 5:
                note_style = c.get('s')
    tail, rr = [], last + 1
    for e in entries:
        for t in e['_notes']:
            tail.append({'r': rr, 'cells': [{'c': 2, 'v': e['name'], 's': st.get(2), 'l': {'s': e['id'], 'r': None}}, {'c': 3, 'v': t, 's': note_style, 'cs': 5}]})
            rr += 1
    g['rows'] = sorted(rows + new + tail, key=lambda x: x['r'])
    g['max_row'] = max(r['r'] for r in g['rows']) + 1
    extract_db.write(p, g)
    return g['max_row']


def version_of(path):
    m = re.search(r'_v(\d+(?:\.\d+)*)', os.path.basename(path))
    return m.group(1) if m else ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data')
    ap.add_argument('--xlsx', default=paths.MOV_XLSX)
    ap.add_argument('--drive-map', default=paths.DRIVE_MAP)
    ap.add_argument('--no-drive-map', action='store_true')
    ap.add_argument('--dcdas', default=paths.DCDAS_INDEX)
    ap.add_argument('--dcdas-u2', default=paths.DCDAS_INDEX_U2)
    ap.add_argument('--ge-tags', default=paths.GE_TAGS)
    ap.add_argument('--keep-plain', action='store_true')
    a = ap.parse_args()
    W = load_inputs(a.xlsx)          # 先檢查輸入：不對就中止，資料目錄還沒動
    data = a.data
    was_enc = encrypt_data.is_encrypted(data)
    if was_enc:
        encrypt_data.decrypt_dir(data, encrypt_data.passphrase_and_salt(persist=False)[0])
    try:
        run(a, data, W)
    except BaseException:
        if was_enc and not a.keep_plain:
            encrypt_data.encrypt_dir(data, *encrypt_data.passphrase_and_salt())
            print('!! 失敗：已把資料加密回去（manifest.build 未變）')
        raise
    if not a.keep_plain:
        encrypt_data.encrypt_dir(data, *encrypt_data.passphrase_and_salt())


def run(a, data, W):
    drive = None
    if not a.no_drive_map:
        import build_card_aux
        drive = build_card_aux.load_drive_map(a.drive_map)
        if not drive:
            raise SystemExit('!! 缺 drive_map（%s），若確定不要雲端連結請加 --no-drive-map' % a.drive_map)
    ver = version_of(a.xlsx)
    list_name = 'AUMA 電動閥 MOV LIST v%s' % ver if ver else 'AUMA 電動閥 MOV LIST'
    man_path = os.path.join(data, 'manifest.json')
    man = PV.load_json(man_path)
    ge =PV.load_json(a.ge_tags) if a.ge_tags and os.path.exists(a.ge_tags) else None
    sidx = {'u1': sig_index(a.dcdas), 'u2': sig_index(a.dcdas_u2)}
    print('signal-atlas 索引：一號機 %s、二號機 %s；GE 對照表 %s' % ('有' if sidx['u1'] else '無', '有' if sidx['u2'] else '無', '有' if ge else '無'))
    remove_previous(data, man)
    hdr, rows, tags = W['hdr'], W['rows'], W['tags']
    pos = {t: i for i, t in enumerate(tags)}
    E = W['ev']
    D = Docs(drive)

    # 代表位號：同一 gid 裡查證列最多的那一台
    by_gid = collections.defaultdict(collections.Counter)
    for (t, _c), ev in E.items():
        by_gid[str(ev.get('gid'))][t] += 1
    rep_of = {}
    for gid, cnt in by_gid.items():
        rep = cnt.most_common(1)[0][0]
        for t in cnt:
            rep_of[t] = rep
    n_ev_mismatch = sum(1 for (t, c), ev in E.items() if t in pos and str(PV.clean(ev.get('查證後值')) or '') != str(PV.clean(rows[pos[t]][c]) or ''))
    missing_tags = [t for t in {k[0] for k in E} if t not in pos]
    print('逐格查證明細 %d 列、%d 組；值與主表不同 %d 格；主表沒有的位號 %d' % (len(E), len(by_gid), n_ev_mismatch, len(missing_tags)))

    # 儀資組：逐台（較新）與維護（使用者裁定說明；那 18 台在分隔列之後，所以 rows＋tail）
    urows = W['unit']['rows']
    unit_by = {str(r[1]).strip(): r for r in urows if r[1] and str(r[1]).strip() in pos}
    mrows = W['maint']['rows'] + W['maint']['tail']
    rule_by = {str(r[1]).strip(): clean(r[12]) for r in mrows if r[1] and str(r[1]).strip() in pos and len(r) > 12 and r[12]}
    print('儀資組逐台 %d 台；裁定說明 %d 台' % (len(unit_by), len(rule_by)))
    alias, dev_alias, ge_of, astat = build_aliases(W, ge)
    add, out = out_of_list(W)
    for k, i, grade, note in add:
        lst = alias.setdefault(compact(k), [])
        if not any(x[0] == i for x in lst):
            lst.append([i, grade, note])
    print('別名：%s；GE 對照 %d 列；未入表 %d 個鍵' % (dict(astat, other=len(add)), len(ge_of), len(out)))

    # 氣動閥清單 61 刪除紀錄（類別含「電動」）→ 回指
    d61 = {}
    p61 = os.path.join(data, 'sheets', '61.json')
    if os.path.exists(p61):
        s61 = PV.load_json(p61)
        h61 = [c['label'] for c in s61['columns']]
        ti = h61.index(TAG) if TAG in h61 else 0
        ci = next((k for k, h in enumerate(h61) if '類別' in h), None)
        ri = next((k for k, h in enumerate(h61) if '理由' in h), None)
        vi = h61.index('涵蓋機組') if '涵蓋機組' in h61 else None
        for k, r in enumerate(s61['rows']):
            if ci is None or '電動' not in str(r[ci] or ''):
                continue
            for _u, t in PV.expand_units(r[ti], r[vi] if vi is not None else None):
                if t in pos:
                    d61[pos[t]] = [k, str(r[ri] or '')[:200] if ri is not None else '']
    print('氣動閥清單刪除紀錄（電動）回指 %d 列' % len(d61))

    # ---- 62 主表
    hidden_cols = {hdr[44]}
    out_hdr = [hdr[c - 1] for c in MAIN_COLS[:2]] + ['查詢卡'] + [hdr[c - 1] for c in MAIN_COLS[2:46]] + ['儀資組裁定說明'] + [hdr[c - 1] for c in MAIN_COLS[46:]]
    out_rows = []
    for i, r in enumerate(rows):
        vals = [clean(r[c - 1]) for c in MAIN_COLS]
        vals[-1] = nb_strip(vals[-1]) if vals[-1] else None          # 45 出處文件：去掉 NotebookLM 筆記本名
        vals[-2] = nb_strip(vals[-2]) if vals[-2] else None          # 47 主要資料來源
        rr = vals[:2] + [{'t': '開卡', 'l': {'s': '02', 'q': tags[i]}}] + vals[2:46] + [rule_by.get(tags[i])] + vals[46:]
        out_rows.append(rr)
    bands = []
    for k, (lab, c) in enumerate(BANDS):
        s = out_hdr.index(hdr[c - 1])
        e = (out_hdr.index(hdr[BANDS[k + 1][1] - 1]) - 1) if k + 1 < len(BANDS) else len(out_hdr) - 1
        bands.append({'label': lab, 'from': 0 if k == 0 else s, 'to': e, 'bg': BAND_COLORS[k], 'fc': '#FFFFFF'})
    tier_tbl = [t for t in W['tier_text'] if '｜' in t][:12]
    notes62 = ['一列＝一台 AUMA 電動閥（一個機組一個位號，已展開）｜%d 列｜來源：「%s」分頁「MOV LIST」（Google 雲端硬碟上的 xlsx）' % (len(rows), list_name),
               '正本（可編輯）：' + LIST_URL,
               '格內的 g001～g111 是查證時的同型閥組編號（同一組六部機比照代表位號）；v3: 開頭的是 v3 新增列的同型組。',
               '台數：%d＝v1／v2（2026-08）的 445 台＋v3（2026-10-18）清單外 AUMA 375 台＋v3.1 的 C10／C20／C30GMM30QM401 3 台；正本第一列標題的「445 台」是 v2 的數字，沒有跟著改。' % len(rows),
               '格內慣例：「查無（理由）」＝查過的文件都不載；「查無→查: 文件」＝要再查哪份；「不適用」＝這種設計沒有這個件；「∥」＝兩份文件讀法不同（見 65）；'
               '「[比照一號機設計值]」「〔機組碼由 G11 換算為 G12〕」＝二、三號機照一號機代表位號的值（序號、扭力設定逐台，不比照）。',
               '逐格出處（文件、PDF 頁、原文、裁決、證據等級）在查詢卡「電動閥」組逐格列出，可開雲端文件；正本的「備註」「…文件來源」等欄不在本頁。',
               '閉迴路閥位分級（2026-10-25，依一、二號機 Mark VIe 程式碼；三號機沒有程式碼，比照一號機）：' + ('；'.join(t.replace('｜', ' ') for t in tier_tbl) if tier_tbl else '見正本「閉迴路分級說明」分頁'),
               '「程式碼依據」欄的 file:line 是 2026-10-25 依當時 checkout 寫的；控制器索引之後換過 checkout，行號可能對不上——查詢卡改用訊號名連 signal-atlas。',
               '查證圖例（裁決）：' + '；'.join('%s＝%s' % (str(x[0]), str(x[1])) for x in W['legend'] if len(x) > 1 and x[1])]
    tj62 = table_json('62', SHEETS['62'], 'MOV LIST', out_hdr, out_rows, notes62, bands=bands, facets=[hdr[5], hdr[6], hdr[7], hdr[69], hdr[70]], key_col=1, hidden=hidden_cols,
                      ui_extra={'presets': [{'label': '儀資組維護＝是', 'col': out_hdr.index(hdr[70]), 'eq': '是'}]})
    entries = [{'id': '62', 'tj': tj62, 'rows': len(out_rows), 'cols': len(out_hdr),
                'desc': '%s：執行器／控制頭／減速機／閥體／馬達／扭力／位置回授／電源盤／備品件號，閉迴路分級與儀資組維護範圍；逐格出處在查詢卡' % list_name,
                'row_unit': '一台電動閥（一個機組一個位號）', '_notes': notes62[:1] + notes62[3:4]}]

    # ---- 63 採購清單、64 逐台、67 未入表、68 件號對照
    def plain(rows_):
        return [[clean(v) for v in r] for r in rows_]
    b = W['buy']
    pre63 = [clean(str(r[0])) for r in b['pre'] if r and r[0]]
    tail63 = [clean(' '.join(str(x) for x in r if x not in (None, ''))) for r in b['tail']]
    notes63 = ['一列＝一項備品（儀資組維護「是」72 台用）｜%d 項｜來源：「%s」分頁「儀資組備品採購清單」' % (len(b['rows']), list_name), '正本：' + LIST_URL] + pre63 + tail63
    entries.append({'id': '63', 'tj': table_json('63', SHEETS['63'], '儀資組備品採購清單', b['hdr'], plain(b['rows']), notes63, facets=['層別'], key_col=0),
                    'rows': len(b['rows']), 'cols': len(b['hdr']), 'desc': '儀資組 AUMA 電動閥備品採購清單：品名、AUMA 件號、適用位號族、裝用總數、建議採購量與算法、物料編號、證據等級與出處',
                    'row_unit': '一項備品', '_notes': []})
    u = W['unit']
    notes64 = ['一列＝儀資組維護「是」的一台｜%d 台｜來源：「%s」分頁「儀資組備品_逐台」' % (len(u['rows']), list_name), '正本：' + LIST_URL] + \
              [clean(str(r[0])) for r in u['pre'] if r and r[0]] + ['這一頁的位置回授、序號／訂單號、控制單元與位置回授備品件號比 62 主表新（2026-11-13 重查）；查詢卡以這一頁為準。']
    entries.append({'id': '64', 'tj': table_json('64', SHEETS['64'], '儀資組備品_逐台', u['hdr'], plain(u['rows']), notes64, facets=['分級'], key_col=1),
                    'rows': len(u['rows']), 'cols': len(u['hdr']), 'desc': '儀資組 72 台逐台備品對照：執行器、控制頭、位置回授、接線圖代碼、馬達、序號／AUMA 訂單號、備品件號與要抄銘牌的項目',
                    'row_unit': '一台電動閥（儀資組維護）', '_notes': []})
    # 65／66：逐格查證明細的兩讀、推翻
    keep = ['Tag', '欄位', '查證後值', '裁決', '證據等級', '文件', 'PDF頁', '印刷頁/Sheet', '原文引句', '看過圖', '驗證員', '其他證據(互證/異值)']
    for sid, verdict, extra in (('65', '兩讀', []), ('66', '推翻', ['原值(v1)'])):
        hh = keep[:2] + extra + keep[2:]
        rr = []
        for (t, c), ev in sorted(E.items(), key=lambda kv: (pos.get(kv[0][0], 9999), kv[0][1])):
            if str(ev.get('裁決')) != verdict:
                continue
            row = [clean(ev.get(h)) for h in hh]
            if '原值(v1)' in hh:
                k = hh.index('原值(v1)')
                row[k] = nb_strip(row[k]) if isinstance(row[k], str) else row[k]
            rr.append(row)
        desc = {'65': '兩份一手文件對同一格讀法不同（不硬裁、要現場銘牌）：那一格的值、文件、頁、原文與另一讀法',
                '66': '2026-10-18 逐格查證以一手文件推翻 v1 原值的格：原值、新值、文件、頁與原文'}[sid]
        notes = ['一列＝一個（位號, 欄位）｜%d 格｜來源：「%s」分頁「逐格查證明細」裁決＝%s' % (len(rr), list_name, verdict), '正本：' + LIST_URL]
        entries.append({'id': sid, 'tj': table_json(sid, SHEETS[sid], verdict, hh, rr, notes, facets=['欄位', '證據等級'], key_col=0),
                        'rows': len(rr), 'cols': len(hh), 'desc': desc, 'row_unit': '一個（位號, 欄位）', '_notes': []})
    o = W['out']
    al_rows = []
    for k, lst in sorted(alias.items()):
        for i, grade, note in lst:
            al_rows.append([k, '別名（%s）→ %s' % (grade, tags[i]), note, '打這個位號會開 %s 的電動閥資料' % tags[i]])
    h67 = list(o['hdr'])
    rows67 = plain(o['rows']) + al_rows
    notes67 = ['一列＝一個清單沒有另列的位號：正本「v3待確認_未入表」的 %d 列（舊號、併入代表、已刪除、備品、手動閥）＋本站整理的別名 %d 個（文件寫法不同的同一顆閥，各列證據等級）'
               % (len(o['rows']), len(al_rows)), '正本：' + LIST_URL,
               '別名的等級：定讞＝三份以上文件一致；強＝清單與另一份清單一致；文件互相矛盾＝兩份文件不一致、本站不替文件選；推論＝清單自評待現場；舊位號／併入代表＝正本自己的裁定。']
    entries.append({'id': '67', 'tj': table_json('67', SHEETS['67'], '未入表與別名', h67, rows67, notes67, key_col=0),
                    'rows': len(rows67), 'cols': len(h67), 'desc': '電動閥清單沒有另列的位號（舊號、併入、已刪除、備品、手動閥）與文件寫法不同的同一顆閥（別名），各附理由與證據等級',
                    'row_unit': '一個位號', '_notes': []})
    p = W['parts']
    notes68 = ['一列＝一個 AUMA 備品件號家族｜%d 列｜來源：「%s」分頁「備品件號對照_查證」第一段（取代舊的「AUMA備品件號」分頁：馬達是 070.0、A1.0… 是圖例代號不是件號）'
               % (len(p['rows']), list_name), '正本：' + LIST_URL]
    # 同一分頁後面幾段（舊「AUMA備品件號」逐列核對、559.0-1 品名版次對照、爆炸圖判讀…）不成表，逐列放進說明
    notes68 += [clean('｜'.join(str(x) for x in r if x not in (None, ''))) for r in p['tail'] if any(x not in (None, '') for x in r)]
    entries.append({'id': '68', 'tj': table_json('68', SHEETS['68'], '備品件號對照_查證', p['hdr'], plain(p['rows']), notes68, key_col=0),
                    'rows': len(p['rows']), 'cols': len(p['hdr']), 'desc': 'AUMA 備品件號對照（機型家族 → 零件 → 件號、是否含開關、適用條件、出處頁）',
                    'row_unit': '一個件號家族', '_notes': []})

    # ---- 查詢卡：每列的欄位值與出處（card/mov-NN.json）
    #   by_i[列] = {v: [值…]（與 02.mov.fields 同順序）, s: [出處序號…]（指向該檔的 src；-1＝無）, xf: [[分組, 標籤, 值, 出處序號]]（儀資組逐台的欄）,
    #              sig: [[site, ctrl, var, kind, point, desc, how]], x: {ge, d61, rep}}；src＝[lvl, text, docKey, two, detail]（同一檔內去重）
    #   分塊以「去機組本體」分組（同一個位置的六部機落在同一檔：比照代表位號的出處只存一次）；列 → 分塊號記在 02.mov.list 的第 4 欄
    TXT_MAX, DET_MAX = 260, 320
    sig_n = collections.Counter()
    card_rows = {}
    for i, r in enumerate(rows):
        t = tags[i]; unit = t[:3]
        uo = unit_by.get(t)
        vals, srcs = [], []
        for grp, lab, c in FIELDS:
            v = clean(r[c - 1])
            if c in (70, 71):
                s = tier_src(r, c)
                if c == 71 and rule_by.get(t):
                    s[4] = [['裁定說明', rule_by[t][:DET_MAX]]]
            elif uo is not None and c in UNIT_OVR and clean(uo[UNIT_OVR[c] - 1]) not in (None, ''):
                nv = clean(uo[UNIT_OVR[c] - 1])
                srcno = clean(uo[11]) if c == 44 else None
                ev0 = W['ev'].get((t, c - 1))      # 主表這一格若是兩讀，換成逐台的值之後仍要標兩讀
                two0 = ((str(ev0.get('其他證據(互證/異值)') or '') or '兩種讀法見主表此欄')[:DET_MAX] if ev0 and str(ev0.get('裁決')) == '兩讀' else None)
                s = ['doc', '文件 · 儀資組備品_逐台（v3.5 重查，較主表新）%s%s' % (('：' + str(srcno)[:160]) if srcno else '',
                                                                        '' if norm_val(nv) == norm_val(v) else '；主表此欄：「%s」' % str(v or '')[:100]),
                     D.key(srcno) if srcno else None, two0, None]
                v = nv
            else:
                s = cell_src(i, c, W, D, rep_of, None)
            vals.append(v)
            srcs.append(s)
        xf = []
        if uo is not None:
            for grp, lab, k in UNIT_EXTRA:
                v = clean(uo[k - 1])
                if v not in (None, ''):
                    xf.append([grp, lab, v, ['doc', '文件 · 儀資組備品_逐台（v3.5）', None, None, None]])
        sg = sigs_for(t, unit, dev_alias.get(i, []), sidx)
        sig_n[('有' if sg else ('無索引' if not UNIT_SITE.get(unit) else '查無'))] += 1
        x = {}
        if ge_of.get(i):
            x['ge'] = ge_of[i]
        if i in d61:
            x['d61'] = d61[i]
        if rep_of.get(t) and rep_of[t] != t:
            x['rep'] = rep_of[t]
        card_rows[i] = {'v': vals, 's': srcs, 'xf': xf, 'sig': sg, 'x': x}
    print('signal-atlas 訊號：%s' % dict(sig_n))

    # 文件編號 → 雲端；src 的 docKey 換成 docs 的鍵、截長
    no_map = D.finish()

    def fix(s):
        if s is None:
            return None
        s = list(s)
        if s[2] and s[2].startswith('no|'):
            s[2] = no_map.get(s[2])
        if s[2] and s[2] not in D.docs:
            s[2] = None
        s[1] = str(s[1])[:TXT_MAX]
        if s[3]:
            s[3] = str(s[3])[:DET_MAX]
        if s[4]:
            s[4] = [[k, str(v)[:DET_MAX]] for k, v in s[4]]
        while s and s[-1] is None:
            s.pop()
        return s
    # 分塊：依去機組本體排序後每 PER 列一檔（同本體不拆開）
    order = sorted(range(len(rows)), key=lambda i: (tags[i][3:], tags[i][:3]))
    chunk_of, k, n_in = {}, 0, 0
    for idx, i in enumerate(order):
        if n_in >= PER and tags[i][3:] != tags[order[idx - 1]][3:]:
            k += 1; n_in = 0
        chunk_of[i] = k; n_in += 1
    files = []; n_b = 0; n_src = n_ref = 0
    for kk in range(k + 1):
        pool, at, used, by_i = [], {}, {}, {}
        for i in [i for i in order if chunk_of[i] == kk]:
            cr = card_rows[i]
            ids = []
            for s in cr['s'] + [x_[3] for x_ in cr['xf']]:
                s = fix(s)
                if not s:
                    ids.append(-1); continue
                key = json.dumps(s, ensure_ascii=False, sort_keys=False)
                if key not in at:
                    at[key] = len(pool); pool.append(s)
                    if len(s) > 2 and s[2]:
                        dd = D.docs[s[2]]
                        used[s[2]] = {q: dd[q] for q in ('title', 'folder', 'why', 'url', 'url_note') if dd.get(q)}
                ids.append(at[key]); n_ref += 1
            nf = len(FIELDS)
            row = {'v': cr['v'], 's': ids[:nf]}
            if cr['xf']:
                row['xf'] = [[g_, l_, v_, ids[nf + q]] for q, (g_, l_, v_, _s) in enumerate(cr['xf'])]
            if cr['sig']:
                row['sig'] = cr['sig']
            if cr['x']:
                row['x'] = cr['x']
            by_i[str(i)] = row
        n_src += len(pool)
        fn = CHUNK_FMT % kk
        n_b += extract_db.write(os.path.join(data, *fn.split('/')), {'version': 1, 'by_i': by_i, 'src': pool, 'docs': used})
        files.append(fn)
    lst = []
    for i, r in enumerate(rows):
        zh = PV.name_clean(clean(r[3]) or '') or PV.name_clean(clean(r[2]) or '')
        lst.append([i, tags[i], (zh or '')[:30], chunk_of[i]])
    print('查詢卡分塊 %d 個（%d KB，出處 %d 種、引用 %d 次）；雲端文件 %d 份（文件編號解析 %d）'
          % (len(files), n_b // 1024, n_src, n_ref, len(D.docs), len(no_map)))

    # ---- 寫 62–68、manifest、00
    for e in entries:
        fn = 'sheets/%s.json' % e['id']
        e['name'] = '%s_%s' % (e['id'], SHEETS[e['id']])
        e['short'] = SHEETS[e['id']]
        e['sources'] = list_name + '（雲端硬碟 xlsx）'
        nbytes = extract_db.write(os.path.join(data, fn), e['tj'])
        man['sheets'].append({'id': e['id'], 'name': e['name'], 'short': e['short'], 'group': GROUP, 'mode': 'table', 'rows': e['rows'], 'cols': e['cols'],
                              'files': [fn], 'bytes': nbytes, 'desc': e['desc'], 'row_unit': e['row_unit'], 'sources': e['sources'],
                              'toc_rows': e['rows'], 'tab_color': TAB_COLOR, 'data_first_row': 4})
    gs = [g for g in man.get('groups', []) if g != GROUP]
    after = next((g for g in AFTER_GROUPS if g in gs), None)
    gs.insert(gs.index(after) + 1 if after else len(gs), GROUP)
    man['groups'] = gs
    mr = patch_00(data, entries)
    for s in man['sheets']:
        if s['id'] == '00':
            s['rows'] = s['toc_rows'] = mr
            s['bytes'] = os.path.getsize(os.path.join(data, 'sheets', '00.json'))
    PV.set_page_count(man, data)

    # ---- 02：查詢卡規格
    s02p = os.path.join(data, 'sheets', '02.json')
    s02 = PV.load_json(s02p)
    s02['mov'] = {
        'v': 1, 'sheet': '62', 'sheets': {sid: '%s_%s' % (sid, SHEETS[sid]) for sid in IDS},
        'label': '電動閥（%s）' % list_name,
        'note': '清單是全廠 AUMA 電動閥的規格與備品整理：每格可點來源看是哪份文件哪一頁；二、三號機多數格比照一號機代表位號（卡上註明）。正本是雲端硬碟上的 xlsx。',
        'list_name': list_name, 'list_url': LIST_URL, 'per': PER, 'files': files,   # files：verify_encrypted 由這裡認得分塊不是孤兒
        'index': {compact(t): i for i, t in enumerate(tags)},
        'alias': {k: v for k, v in sorted(alias.items())},
        'fields': [[grp, lab] for grp, lab, _c in FIELDS],      # 卡上欄位（分組, 標籤）；分塊的 v／s 與它同順序
        'list': lst, 'out': out,                                 # list＝[列, 位號, 中文名, 分塊號]；out＝清單沒收的位號 → 說明
        'ge': {g: sorted(i for i, gs in ge_of.items() if g in gs) for g in sorted({g for gs in ge_of.values() for g in gs})},   # GE 編號 → 列（GE 編號卡接這一組）
        'sig_base': SIG_BASE,
    }
    extract_db.write(s02p, s02)

    # ---- 自檢：本機路徑（同 verify_encrypted）＋本模組的禁字（人名樣式、建置用路徑與術語）——只查本模組寫出的內容
    #      （00 與 02 是共用檔：00 只查本模組加的目錄列與註記，02 只查 mov 那一段；其他模組原有的內容不歸這裡管）
    mine = [('sheets/%s.json' % s, open(os.path.join(data, 'sheets', s + '.json'), encoding='utf-8').read()) for s in IDS]
    mine += [(f, open(os.path.join(data, *f.split('/')), encoding='utf-8').read()) for f in files]
    mine.append(('sheets/02.json mov', json.dumps(s02['mov'], ensure_ascii=False)))
    mine.append(('sheets/00.json（本模組的列）', json.dumps([[e['name'], e['desc'], e['row_unit'], e['sources'], e['_notes']] for e in entries], ensure_ascii=False)))
    nb_hits = collections.Counter()
    for rel, txt in mine:
        for rx, what in ((PV.LOCAL_RE, '本機路徑'), (FORBID_RE, '不出貨的字串')):
            m = rx.search(txt)
            if m:
                raise SystemExit('!! %s 含%s：…%s…' % (rel, what, txt[max(0, m.start() - 60):m.end() + 40]))
        nb_hits[rel] = len(NB_RE.findall(txt))
    if sum(nb_hits.values()):
        print('  注意：仍提到 NotebookLM／NB 的地方（工具名，不擋）：%s' % {k: v for k, v in nb_hits.items() if v})
    man['build'] = extract_db.data_build(data, man)
    extract_db.write(man_path, man)
    print('電動閥清單：%d 台（%s）；62–68 共 %d 頁；位號索引 %d 鍵、別名 %d 鍵、未入表 %d；build %s'
          % (len(rows), list_name, len(IDS), len(tags), len(alias), len(out), man['build']))


if __name__ == '__main__':
    main()
