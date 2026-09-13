"""docmap_docindex.py -- per-AMS-tag engineering document index (kind="docindex").

For every AMS device (03.json col0 current tag, col1 alias) find the pages of the
engineering PDFs (P&ID, Hook-up, datasheets, protection box, cable schedules,
connection diagrams, logic diagrams, location drawings, GT I/O list) that mention
the tag, using pdftotext text (form feed = page break).

Usage:
  py tools/db/docmap_docindex.py --root <engineering library root>
        --sheets03 docs/db/data/sheets/03.json --cache <txt cache dir>
        --out <cardwork>/docindex.json [--filelist <files.txt>]
        [--pdftotext pdftotext] [--jobs 8]

Cache: <cache>/<md5(relative path with '/')>.txt  (same key as the earlier pdftx.py
run).  PDFs not yet cached are extracted with `pdftotext -layout`.
Nothing is written into the library; output JSON holds only doc numbers,
revisions, folder names relative to the library root and page numbers.

Match rules
  R1  exact tag token (token chars A-Z 0-9 _ -, so G12HAP70BT001 != G12HAP70BT0011)
  R2  GE tags G1x_<GE no.>: bare GE no. (GT I/O list / GE instrument diagrams only)
  R3  KKS tag with unit prefix replaced by XX / YY (GE/ST generic documents)
  R5  R1 hit on a page that also lists the same tag for other units (G22/G32...)
  R6  tag + signal/cable suffix (XQ01, _TE, -WG-001 ...) -- cable docs only
  R7  tag + '_' derived DCS signal (TAG_H, TAG_2L, TAG_VALUE ...) -- logic diagrams only
Versions: same doc number -> highest revision only (numeric > letter, larger wins);
same revision copies -> latest mtime; a newest copy without text layer falls back
to the next candidate (recorded in "searched").  HT1-1-AFF01-Dxxxx and HT0-1-AFF01-Dxxxx
are one family (same GE drawing, HT1 = 2021 letter revs superseded by HT0 re-issue):
HT0 preferred.  Pages of connection diagrams / cable schedules containing "LEGENDS"
are skipped (typical-example tag repeated in every volume).
"""
import argparse, collections, concurrent.futures as cf, hashlib, json, os, re, subprocess, sys

DOCNO = re.compile(r'(HT\d-\d-([A-Z]{3}\d\d)-([A-Z])(\d{4}))(?:-([0-9A-Z]{1,2})(?![0-9A-Za-z]))?')

ORDER = ['P&ID', '規格表', '就地錶規格', 'Hook-up', '保護箱', '位置圖', '電纜表', '接線圖', '邏輯圖', 'GT I/O 清單']
CABLE_CATS = {'電纜表', '接線圖'}
GE_CATS = {'P&ID', 'GT I/O 清單', '規格表'}   # R2/R3 allowed


def classify(sys_code, letter, num, base):
    n = int(num)
    u = base.upper()
    if sys_code == 'AFF01' and letter == 'D' and n >= 2:
        return 'P&ID'
    if sys_code in ('GFD01', 'TFD01') and letter == 'D':
        return 'P&ID'
    if sys_code == 'IIE01' and letter == 'D' and n == 1150:
        return '保護箱'
    if sys_code == 'IIE01' and letter == 'D' and 1100 <= n < 1150:
        return 'Hook-up'
    if sys_code == 'IIE01' and letter == 'S':
        return '就地錶規格' if 'LOCAL GAUGE' in u else '規格表'
    if sys_code == 'ILE01' and letter == 'A' and 1000 <= n < 1100:
        return '電纜表'
    if sys_code == 'ICE01' and letter == 'D' and 1000 <= n < 1100:
        return '接線圖'
    if sys_code == 'IOE01' and letter == 'D' and 2000 <= n < 3000:
        return '邏輯圖'
    if sys_code == 'IIF01' and letter == 'D':
        return '位置圖'
    if sys_code == 'IMI01' and letter == 'A' and n == 2:
        return 'GT I/O 清單'
    return None


def rev_key(rev):
    if not rev:
        return (-1, 0)
    if rev.isdigit():
        return (1, int(rev))
    return (0, sum((ord(c) - 64) * 27 ** i for i, c in enumerate(reversed(rev))))


def title_of(base, docfull, rev):
    t = os.path.splitext(base)[0]
    t = t.replace(docfull + ('-' + rev if rev else ''), '')
    t = re.sub(r'(\s*-?\s*\(\d\))+\s*$', '', t)
    t = re.sub(r'^[\s\-_()（）【】]+|[\s\-_()（）【】]+$', '', t)
    t = re.sub(r'(\s*-?\s*\(\d\))+\s*$', '', t).strip(' -_')
    return t[:120]


def list_pdfs(root, filelist):
    if filelist:
        for line in open(filelist, encoding='utf-8'):
            p = line.strip()
            if p.startswith('./'):
                p = p[2:]
            if p.lower().endswith('.pdf'):
                yield p
    else:
        for dp, dn, fn in os.walk(root):
            for f in fn:
                if f.lower().endswith('.pdf'):
                    yield os.path.relpath(os.path.join(dp, f), root).replace('\\', '/')


R6SUF = re.compile(r'^(?:[ABC]?X[QGB]\d\d|_TE)?(?:-W[A-Z]?(?:-?\d{2,3})?)?$')
TOKEN = re.compile(r'[A-Z0-9][A-Z0-9_\-]{3,}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--sheets03', required=True)
    ap.add_argument('--cache', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--filelist')
    ap.add_argument('--pdftotext', default='pdftotext')
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--maxpages', type=int, default=10)
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)

    # ---- tags
    s03 = json.load(open(a.sheets03, encoding='utf-8'))
    tag2alias = {}
    for r in s03['rows']:
        if r[0] and r[1]:
            tag2alias.setdefault(str(r[0]).strip().upper(), str(r[1]).strip())
    exact = dict(tag2alias)
    lens = sorted({len(t) for t in exact})
    variants = collections.defaultdict(list)   # token -> [(alias, rule, tag)]
    unit_sib = {}                              # tag -> sibling unit tokens (R5)
    for t, al in tag2alias.items():
        m = re.match(r'^([GCS])(\d)(\d)([A-Z]{3}\d\d[A-Z]{2}\d{3}[A-Z]?)$', t)
        if m:
            variants['XX' + m.group(4)].append((al, 'R3', t))
            variants['YY' + m.group(4)].append((al, 'R3', t))
            unit_sib[t] = {m.group(1) + u + m.group(3) + m.group(4) for u in '23' if u != m.group(2)}
        m = re.match(r'^([GS]\d\d)_(.+)$', t)
        if m and len(m.group(2)) >= 5 and m.group(2) not in exact:
            variants[m.group(2)].append((al, 'R2', t))

    # ---- documents
    docs = collections.defaultdict(list)
    for rel in list_pdfs(a.root, a.filelist):
        base = rel.split('/')[-1]
        m = DOCNO.search(base)
        if not m:
            continue
        cat = classify(m.group(2), m.group(3), m.group(4), base)
        if not cat:
            continue
        dn0 = m.group(1)
        # HT1-1-AFF01-Dxxxx (2021 letter revs) are the same GE P&ID sheets later re-issued
        # as HT0-1-AFF01-Dxxxx (same HST/.. drawing no., PRINTED 2022-2026) -> one family.
        fam = 'HT0' + dn0[3:] if m.group(2) == 'AFF01' and dn0[:3] in ('HT0', 'HT1') else dn0
        docs[fam].append({'rel': rel, 'rev': m.group(5) or '', 'cat': cat, 'base': base, 'dn': dn0})
    print('doc numbers', len(docs), 'files', sum(len(v) for v in docs.values()), flush=True)

    def mtime(rel):
        try:
            return os.stat(os.path.join(a.root, rel)).st_mtime
        except OSError:
            return 0

    def text_path(rel):
        return os.path.join(a.cache, hashlib.md5(rel.encode()).hexdigest() + '.txt')

    def ensure_text(rel):
        p = text_path(rel)
        if not os.path.exists(p):
            try:
                subprocess.run([a.pdftotext, '-layout', os.path.join(a.root, rel), p],
                               timeout=600, capture_output=True)
            except Exception:
                pass
        if not os.path.exists(p):
            return None
        return p

    def has_text(p):
        if not p:
            return False
        with open(p, encoding='utf-8', errors='ignore') as fh:
            s = fh.read(200000)
        return len(re.sub(r'\s', '', s)) >= 50

    # order candidates per doc number
    for dn, lst in docs.items():
        for x in lst:
            x['mt'] = mtime(x['rel'])
        lst.sort(key=lambda x: (x['dn'] == dn, rev_key(x['rev']), '舊版' not in x['rel'], x['mt']), reverse=True)

    # extract text for newest candidates first (fallback lazily)
    chosen = {}
    searched = []
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        pending = {dn: 0 for dn in docs}
        while pending:
            futs = {dn: ex.submit(ensure_text, docs[dn][i]['rel']) for dn, i in pending.items()}
            nxt = {}
            for dn, fu in futs.items():
                i = pending[dn]
                p = fu.result()
                if has_text(p):
                    chosen[dn] = (i, p)
                else:
                    docs[dn][i]['notext'] = True
                    if i + 1 < len(docs[dn]):
                        nxt[dn] = i + 1
            pending = nxt
    for dn, lst in sorted(docs.items()):
        ci = chosen.get(dn, (None, None))[0]
        top = lst[0]
        for i, x in enumerate(lst):
            folder = '/'.join(x['rel'].split('/')[:-1])
            ref = lst[ci if ci is not None else 0]
            if i == ci:
                why = '最新版' if (x['rev'], x['dn']) == (top['rev'], top['dn']) else '新版無文字層，改用此版'
                if len([y for y in lst if (y['rev'], y['dn']) == (x['rev'], x['dn'])]) > 1:
                    why += '（同版多副本取修改時間最新）'
                used = True
            elif x.get('notext'):
                why, used = '無文字層（掃描圖）', False
            elif x['dn'] != ref['dn']:
                why, used = f"舊編號版（已由 {ref['dn']} 重發取代）", False
            elif x['rev'] == ref['rev']:
                why, used = '同版副本', False
            elif not x['rev']:
                why, used = '無版次檔（附件/轉檔，未採用）', False
            elif rev_key(x['rev']) < rev_key(ref['rev']):
                why, used = '舊版（被取代）', False
            else:
                why, used = '未檢查', False
            searched.append({'doc_id': x['dn'], 'rev': x['rev'], 'title': title_of(x['base'], x['dn'], x['rev']),
                             'category': x['cat'], 'folder': folder, 'used': used, 'why': why})

    # ---- scan
    hits = collections.defaultdict(lambda: collections.defaultdict(lambda: {'pages': set(), 'rules': set(), 'forms': set()}))
    for dn, (i, p) in sorted(chosen.items()):
        x = docs[dn][i]
        cat = x['cat']
        with open(p, encoding='utf-8', errors='ignore') as fh:
            txt = fh.read().upper()
        pages = txt.split('\f')
        for pno, ptxt in enumerate(pages, 1):
            # connection-diagram LEGENDS sheet: typical example tag (G11HAD10QN002XQ01 ...)
            # repeated in every ICE01 volume incl. units 2/3 -> not a real hit
            if cat in CABLE_CATS and re.search(r'\bLEGENDS\b', ptxt):
                continue
            toks ={m.group().rstrip('-_') for m in TOKEN.finditer(ptxt)}
            for tk in toks:
                if tk in exact:
                    al = exact[tk]
                    h = hits[al][dn]
                    rule = 'R1'
                    sib = unit_sib.get(tk)
                    if sib and sib & toks:
                        rule = 'R5'
                    h['pages'].add(pno); h['rules'].add(rule)
                    continue
                if tk in variants and cat in GE_CATS:
                    for al, rule, tag in variants[tk]:
                        h = hits[al][dn]
                        h['pages'].add(pno); h['rules'].add(rule); h['forms'].add(tk)
                    continue
                if cat == '邏輯圖':
                    # derived DCS signal of the tag on other logic sheets: TAG_H, TAG_2L, TAG_VALUE ...
                    for L in lens:
                        if L >= len(tk):
                            break
                        pre = tk[:L]
                        if pre in exact and tk[L] == '_':
                            h = hits[exact[pre]][dn]
                            h['pages'].add(pno); h['rules'].add('R7'); h['forms'].add(tk)
                    continue
                if cat in CABLE_CATS:
                    for L in lens:
                        if L >= len(tk):
                            break
                        pre = tk[:L]
                        if pre in exact and R6SUF.match(tk[L:]):
                            h = hits[exact[pre]][dn]
                            h['pages'].add(pno); h['rules'].add('R6'); h['forms'].add(tk)
        print('scanned', dn, x['rev'], cat, len(pages), flush=True)

    # ---- legend filter: a tag hit only via R6 in >=4 cable/wiring doc numbers on a
    # single page each is a drawing legend / typical example (e.g. G11HAD10QN002 on
    # p.8/10 of every ICE01 volume incl. units 2/3) -> drop those R6-only entries.
    dropped = 0
    for al, dd in hits.items():
        r6only = [dn for dn, h in dd.items() if h['rules'] == {'R6'} and len(h['pages']) == 1]
        if len(r6only) >= 4:
            for dn in r6only:
                del dd[dn]
                dropped += 1
    hits = {al: dd for al, dd in hits.items() if dd}

    # ---- output
    by_alias = {}
    catcount = collections.Counter()
    rows = 0
    rule_pri = ['R1', 'R5', 'R3', 'R2', 'R6', 'R7']
    for al, dd in hits.items():
        ent = []
        for dn, h in dd.items():
            i, _ = chosen[dn]
            x = docs[dn][i]
            pg = sorted(h['pages'])
            shown = pg[:a.maxpages]
            pstr = ', '.join(map(str, shown)) + (f' …（共 {len(pg)} 頁）' if len(pg) > a.maxpages else '')
            rule = next(r for r in rule_pri if r in h['rules'])
            fields = [['類別', x['cat']], ['文件', f"{x['dn']}-{x['rev']}" if x['rev'] else x['dn']], ['頁', pstr]]
            if h['forms'] and rule != 'R1':
                fields.append(['命中寫法', ', '.join(sorted(h['forms'])[:5])])
            if rule == 'R5':
                fields.append(['備註', '同頁列出其他機組同位號'])
            elif rule in ('R2', 'R3'):
                fields.append(['備註', 'GE/ST 通用編號（不分機組），同編號各機組共用此頁'])
            elif rule == 'R6':
                fields.append(['備註', '以訊號/電纜編號命中'])
            elif rule == 'R7':
                fields.append(['備註', '以 DCS 衍生訊號（位號_H/_L/_VALUE…）命中'])
            fields.append(['頁數_num', len(pg)])
            ent.append({'doc_id': x['dn'], 'rev': x['rev'], 'loc': 'p.' + ','.join(map(str, shown)),
                        'rule': rule, 'level': 'doc', 'fields': fields,
                        '_k': (ORDER.index(x['cat']), x['dn'])})
        ent.sort(key=lambda e: e['_k'])
        for e in ent:
            del e['_k']
        by_alias[al] = ent
        rows += len(ent)
        for c in {e['fields'][0][1] for e in ent}:
            catcount[c] += 1
    out = {
        'kind': 'docindex',
        'generated_by': 'tools/db/docmap_docindex.py',
        'searched': searched,
        'by_alias': dict(sorted(by_alias.items())),
        'stats': {'aliases_matched': len(by_alias), 'aliases_total': len(set(tag2alias.values())),
                  'rows': rows, 'docs_used': len(chosen), 'legend_rows_dropped': dropped,
                  'per_category_aliases': {c: catcount[c] for c in ORDER},
                  'notes': 'PDF 文字層逐頁（\\f）比對；R1 全字、R5 同頁多機組、R3 XX/YY（僅 P&ID/規格表/GT I/O）、'
                           'R2 GE 編號（同上）、R6 訊號/電纜字尾（僅電纜表/接線圖）、R7 位號_衍生訊號（僅邏輯圖）。同文件編號只取最高版次'
                           '（數字版 > 字母版），同版副本取修改時間最新；HT1-1-AFF01 舊編號 P&ID 已由 HT0-1-AFF01 重發取代，只取 HT0；'
                           '接線圖/電纜表的 LEGENDS 圖例頁不計；無文字層的掃描 PDF 無法索引；'
                           'R2/R3 為 GE/ST 不分機組編號，同編號各機組共用。頁碼最多列 ' + str(a.maxpages) + ' 頁。'}
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out['stats'], ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
