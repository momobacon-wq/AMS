# -*- coding: utf-8 -*-
"""docmap_eomr.py — 出廠製造紀錄 (EOMR) / 原廠校正證書 → 設備查詢卡「出廠」欄位

用法:
  py tools/db/docmap_eomr.py --root <工程文件庫根> --sheets docs/db/data/sheets \
      --sqlite <AmsDb.sqlite> --cache <pdftotext 快取目錄> --out <cardwork>/eomr.json [--workers 4] [--all]

流程:
 1. 在 --root 下找檔名含 EOMR / End of Manufacturing / Calibration Report / Inspection..Test..(Transmitter|Radar)
    的 PDF（預設再以儀器關鍵字過濾；--all 取消過濾）；略過以 "_" 開頭的處理用資料夾（_chunks/_fix/_nbB…）。
 2. 同文件編號取最新版次（數字版 > 字母版；同類比大小）；同版次多副本取修改時間最新者。
 3. pdftotext -layout 抽整份文字（以 \\f 分頁 → p.N 為 PDF 頁序），快取於 --cache。
 4. 解析 Rosemount/Emerson「Calibration Data Sheet」證書頁（Serial No + Permanent/Wire-On Tag）
    與下一頁 Calibration Data（量程、感測器、PASS/FAIL）；另解析彙整表
    「Model Number / Serial Number / Customer Ref / Tag Number」。
 5. 防錯位: 序號後 7 碼 vs AMS final_assembly_number。
    證書頁: 相符→「是」；不符→仍收但標「否（AMS=…）」。彙整表: 只收相符列。
 不輸出 PO / Sales Order；不輸出本機絕對路徑。
"""
import argparse, hashlib, json, os, re, sqlite3, struct, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

NAME_RE = re.compile(r'EOMR|END\s*OF\s*MANUFACTUR|MANUFACTURING\s+REPORT|CALIBRATION\s+REPORT|'
                     r'INSPECTION.{0,20}TEST.{0,30}(TRANSMITTER|RADAR|INSTRUMENT)', re.I)
INSTR_RE = re.compile(r'INSTRUMENT|TRANSMIT|THERMO|FLOW|LEVEL|MEASUR|GAUGE|SWITCH|ANALY|RADAR|CALIBRATION', re.I)
DOC_RE = re.compile(r'^(HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4})-([0-9A-Z]{1,2})[-_ ]')
V = lambda x: x.get('v') if isinstance(x, dict) else x


def rev_key(rev):
    # 數字版次（正式發行）優先於字母版次；同類比大小
    return (1, int(rev), '') if rev.isdigit() else (0, 0, rev)


def load_ams(sheets, sqlite_path):
    j3 = json.load(open(os.path.join(sheets, '03.json'), encoding='utf-8'))
    tag2alias, key2alias, alias2tag = {}, {}, {}
    for r in j3['rows']:
        tag, alias, dk = (str(V(r[0]) or '').strip(), V(r[1]), V(r[2]))
        if not alias:
            continue
        alias2tag[alias] = tag
        if tag:
            tag2alias.setdefault(tag.upper(), alias)
        if dk is not None:
            key2alias[int(dk)] = alias
    idx04 = {}
    p04 = os.path.join(sheets, '04.json')
    if os.path.exists(p04):
        for r in json.load(open(p04, encoding='utf-8'))['rows']:
            k, typ, alias, n = V(r[0]), V(r[2]), V(r[4]), V(r[7])
            if k and alias and n == 1:
                idx04.setdefault(str(k).upper(), (alias, str(typ)))
    fan = {}
    if sqlite_path:
        uri = 'file:' + os.path.abspath(sqlite_path).replace('\\', '/') + '?mode=ro'
        con = sqlite3.connect(uri, uri=True)
        q = ("select b.DeviceKey, d.EventIdDay, d.EventIdFraction, d.ParamData from BlockData d "
             "join Blocks b on b.BlockKey=d.BlockKey where d.ParamName like 'final_assembly_number.%' "
             "and d.ParamDataType=4 order by d.EventIdDay, d.EventIdFraction")
        for dk, _, _, blob in con.execute(q):
            if blob and len(blob) >= 4 and dk in key2alias:
                fan[key2alias[dk]] = struct.unpack('<i', bytes(blob[:4]))[0]  # 取最新
    else:
        for r in json.load(open(os.path.join(sheets, '13.json'), encoding='utf-8'))['rows']:
            a, v = V(r[40]), V(r[30])
            if a and v not in (None, ''):
                fan[a] = int(float(v))
    return tag2alias, idx04, alias2tag, fan


def strip_po(fn):
    # 檔名中的採購單號（10 碼 41/42 開頭，含 -10,70 等行號）不公開
    s = re.sub(r'\.pdf$', '', fn, flags=re.I)
    s = re.sub(r'\(?\s*(PO[\s#_\-]*)?4\d{9}(\s*[-_–]\s*[\d,&\s]+)*(\s*&\s*\d+)*\s*\)?', '', s, flags=re.I)
    s = re.sub(r'\bPO[\s#_\-]*(?=[\s\-–)]|$)', '', s)
    return re.sub(r'\s{2,}', ' ', s).strip(' -–_')


def find_candidates(root, use_all):
    groups = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith('_')]
        for fn in fns:
            if not fn.lower().endswith('.pdf') or not NAME_RE.search(fn):
                continue
            if not use_all and not INSTR_RE.search(fn):
                continue
            full = os.path.join(dp, fn)
            m = DOC_RE.match(fn)
            doc, rev = (m.group(1), m.group(2)) if m else (os.path.splitext(fn)[0], '')
            st = os.stat(full)
            groups.setdefault(doc, []).append(dict(doc_id=doc, rev=rev, full=full, fn=fn,
                                                   folder=os.path.relpath(dp, root).replace('\\', '/'),
                                                   mtime=st.st_mtime, size=st.st_size))
    chosen, searched = [], []
    for doc, lst in sorted(groups.items()):
        lst.sort(key=lambda x: (rev_key(x['rev']), x['mtime']), reverse=True)
        best = lst[0]
        chosen.append(best)
        for x in lst:
            why = '較新版（採用）' if x is best else ('副本' if x['rev'] == best['rev'] else '被取代（舊版次）')
            searched.append(dict(doc_id=doc, rev=x['rev'], title=strip_po(x['fn'])[:160], folder=x['folder'],
                                 used=x is best, why=why, _full=x['full'] if x is best else None))
    return chosen, searched


def extract(pdf, cache):
    st = os.stat(pdf)
    h = hashlib.sha1(f'{os.path.basename(pdf)}|{st.st_size}|{int(st.st_mtime)}'.encode('utf-8')).hexdigest()
    out = os.path.join(cache, h + '.txt')
    if not os.path.exists(out):
        tmp = out + '.tmp'
        try:
            subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', pdf, tmp], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
            os.replace(tmp, out)
        except Exception:
            return None
    return open(out, encoding='utf-8', errors='replace').read().split('\f')


TAG_TOKEN = re.compile(r'^[A-Z0-9][A-Z0-9_\-./]{3,}$')
SER_RE = re.compile(r'Seria[l1I]\s*No\.?\s*[:;]\s*([0-9A-Z]{6,})', re.I)
PERM_RE = re.compile(r'Permanent\s+Tag\s+[Il1]n?formation|Permanent\s+Tag', re.I)
STOP_RE = re.compile(r'Equipment\s+Used|Attached\s+Models|Measurement\s+Data|This\s+(document|is\s+to)\s+certif|'
                     r'Issued\s+Date|Calibration\s+Data', re.I)
RANGE_T = re.compile(r'Sensor\s*1\s+(.+?)\s{2,}(-?[\d,]*\.?\d+)\s*TO\s*(-?[\d,]*\.?\d+)\s+([^\n]+)', re.I)
RANGE_P = re.compile(r'Range\s*:\s*(-?[\d,]*\.?\d+)\s*TO\s*(-?[\d,]*\.?\d+)\s+([^\s]+(?:\s?\([a-z]\))?)', re.I)
UNIT_MAP = {'DEG C': '°C', 'DEG F': '°F', 'DEGC': '°C', 'DEGF': '°F', 'K': 'K', 'KPA': 'kPa', 'MPA': 'MPa',
            'PA': 'Pa', 'BAR': 'bar', 'MBAR': 'mbar', 'PSI': 'psi', 'INH2O': 'inH2O', 'MMH2O': 'mmH2O'}


def num(s):
    try:
        return float(s.replace(',', ''))
    except Exception:
        return None


def norm_sensor(s):
    s = re.sub(r'\s+', ' ', s).strip()
    m = re.search(r'Type\s+([A-Z])\s+T/?C\s+(\d)\s*Wire', s, re.I)
    if m:
        return f'{m.group(1).upper()} 型 T/C {m.group(2)} 線'
    m = re.search(r'(PT\s*-?\s*\d+|RTD).*?(\d)\s*Wire', s, re.I)
    if m:
        return re.sub(r'\s*(\d)\s*Wire', r' \1 線', s.replace('NIST ', ''), flags=re.I)
    return s


def parse_tags(page):
    lines = page.split('\n')
    for i, ln in enumerate(lines):
        if PERM_RE.search(ln):
            toks = []
            for ln2 in lines[i + 1:i + 8]:
                if STOP_RE.search(ln2):
                    break
                for t in ln2.split():
                    t = t.strip().lstrip('=').upper()
                    if TAG_TOKEN.match(t) and re.search(r'\d', t) and re.search(r'[A-Z]', t) \
                            and not re.match(r'^(WIRE-ON|INFORMATION)$', t):
                        toks.append(t)
            return list(dict.fromkeys(toks))
    return []


def parse_cert(pages, i):
    p = pages[i]
    m = SER_RE.search(p)
    if not m or not PERM_RE.search(p):
        return None
    ser = m.group(1).upper()
    g = lambda rx: (re.search(rx, p, re.I) or [None, None])[1]
    rec = dict(serial=ser, page=i + 1, tags=parse_tags(p))
    if re.search(r'Calibration\s+Data\s+Sheet|Calibration\s+Information|Calibration\s+Date', p, re.I):
        rec['ctype'] = '校正證書 (Calibration Data Sheet)'
    elif re.search(r'Hydrostatic', p, re.I):
        rec['ctype'] = '水壓試驗證書 (Hydrostatic)'
    elif re.search(r'Material\s+Certificate', p, re.I):
        rec['ctype'] = '材料證明 (Material CoC)'
    else:
        rec['ctype'] = '其他證書'
    rec['is_cal'] = rec['ctype'].startswith('校正')
    rec['model'] = g(r'Model\s+No\.?\s*:\s*([0-9A-Z][0-9A-Z*./\-]+)')
    rec['devtype'] = g(r'Device\s+Type\s*:\s*(.+?)(?:\s{2,}|$)')
    d = re.search(r'Calibration\s+Date\s*:\s*(\d{1,2})/(\d{1,2})/(\d{4})', p, re.I)
    rec['caldate'] = f'{d.group(3)}-{int(d.group(1)):02d}-{int(d.group(2)):02d}' if d else None
    if not d:
        d = re.search(r'Issued\s+Date\s*:\s*([A-Z][a-z]+ \d{1,2}, \d{4})', p)
        rec['issued'] = d.group(1) if d else None
    f = re.search(r'(' + re.escape(ser) + r'_[A-Z0-9_\-]+)', p)
    rec['certid'] = f.group(1) if f else None
    rec['pages'] = [i + 1]
    rec['result'] = None
    if not rec['is_cal']:
        rec['caldate'] = None
        return rec
    # 量程 / 結果：本頁與後續最多 2 頁（遇到下一張證書即停）
    rng_pages = [i]
    for k in (i + 1, i + 2):
        if k < len(pages):
            q = pages[k]
            if SER_RE.search(q) and PERM_RE.search(q):
                break
            if ser in q or re.search(r'Calibration\s+Data|Measurement\s+Data', q, re.I):
                rng_pages.append(k)
    txt = '\n'.join(pages[k] for k in rng_pages)
    mt, mp = RANGE_T.search(txt), RANGE_P.search(txt)
    if mt:
        rec.update(sensor=norm_sensor(mt.group(1)), lo=mt.group(2), hi=mt.group(3),
                   unit_raw=mt.group(4).strip(), range_raw=f'{mt.group(2)} TO {mt.group(3)} {mt.group(4).strip()}')
    elif mp:
        rec.update(lo=mp.group(1), hi=mp.group(2), unit_raw=mp.group(3).strip(),
                   range_raw=f'{mp.group(1)} TO {mp.group(2)} {mp.group(3).strip()}')
    npass = len(re.findall(r'\bPASS\b', txt, re.I))
    nfail = len(re.findall(r'\bFAIL\b', txt))
    rec['result'] = 'FAIL' if nfail else ('PASS' if npass else None)
    rec['pages'] = [k + 1 for k in rng_pages]
    return rec


KKS_RE = re.compile(r'^[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?$')
TABLE_HDR = re.compile(r'Model\s+Number\s+Serial\s+Number\s+Customer\s+Ref', re.I)


def parse_table(pages, i):
    p = pages[i]
    if not TABLE_HDR.search(p):
        return []
    out = []
    for ln in p.split('\n'):
        parts = re.split(r'\s{2,}', ln.strip())
        if len(parts) == 4 and re.search(r'\d{6,}$', parts[1]) and not TABLE_HDR.search(ln):
            # pdftotext -layout 下 Customer Ref / Tag Number 欄常與 Model/Serial 列錯位（例 p.2311 位號欄抓到頁碼），
            # 只信同一列的 Model+Serial；位號須為 KKS 形式才採用，Customer Ref 不收
            t = parts[3].strip().lstrip('=').upper()
            out.append(dict(model=parts[0], serial=parts[1].upper(),
                            tags=[t] if KKS_RE.match(t) else [], page=i + 1))
    return out


def last7(s):
    m = re.search(r'(\d+)$', s or '')
    return int(m.group(1)[-7:]) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--sheets', required=True)
    ap.add_argument('--sqlite')
    ap.add_argument('--cache', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    tag2alias, idx04, alias2tag, fan = load_ams(a.sheets, a.sqlite)
    fan_rev = {}
    for al, v in fan.items():
        if v:
            fan_rev.setdefault(v, []).append(al)

    chosen, searched = find_candidates(a.root, a.all)
    # 不同文件代碼但同一內容（如 AQA01-T4739-0 與 AQP01-Q4739-A）：先處理版次高者（數字版 > 字母版，再比修改時間），
    # 同序號同優先度時先到者為主來源 → 主來源由版次規則決定，而非檔名字母序
    chosen.sort(key=lambda x: (rev_key(x['rev']), x['mtime']), reverse=True)
    print(f'candidates: {len(chosen)} docs ({len(searched)} files)', file=sys.stderr)
    with ThreadPoolExecutor(a.workers) as ex:
        texts = dict(zip([c['doc_id'] for c in chosen], ex.map(lambda c: extract(c['full'], a.cache), chosen)))

    def map_tag(tags):
        for t in tags:
            if t in tag2alias:
                return tag2alias[t], 'R1', t
        for t in tags:
            if t in idx04:
                al, typ = idx04[t]
                return al, f'R1（04 位號索引：{typ}）', t
        return None, None, None

    entries = {}  # (alias, serial) -> entry
    st = dict(cert_pages=0, cert_mapped=0, cert_match=0, cert_mismatch=0, cert_nofan=0,
              table_rows=0, table_mapped=0, table_match=0, table_rejected=0, serial_only=0)
    sdocs = {s['doc_id']: s for s in searched if s['used']}
    for c in chosen:
        pages = texts.get(c['doc_id'])
        s = sdocs[c['doc_id']]
        s.pop('_full', None)
        if not pages or not any(p.strip() for p in pages):
            s['used'] = False; s['why'] = '無文字層（掃描檔）或抽取失敗'
            continue
        ncert = ntab = 0
        s['pages'] = len(pages)
        s0 = (st['cert_pages'], st['table_rows'])
        for i in range(len(pages)):
            recs = []
            r = parse_cert(pages, i)
            if r:
                r['kind'] = 'cert'; recs.append(r); ncert += 1; st['cert_pages'] += 1
                st['cal_pages'] = st.get('cal_pages', 0) + (1 if r['is_cal'] else 0)
            for t in parse_table(pages, i):
                t['kind'] = 'table'; recs.append(t); ntab += 1; st['table_rows'] += 1
            for r in recs:
                al, rule, tag = map_tag(r['tags'])
                l7 = last7(r['serial'])
                if not al and l7 and len(fan_rev.get(l7, [])) == 1:
                    al, rule, tag = fan_rev[l7][0], 'R1（位號未對上，以序號後 7 碼唯一對到 AMS）', (r['tags'] or ['?'])[0]
                    st['serial_only'] += 1
                if not al:
                    continue
                amsv = fan.get(al)
                if r['kind'] == 'cert':
                    st['cert_mapped'] += 1
                else:
                    st['table_mapped'] += 1
                if amsv and l7 == amsv:
                    match = '是'
                elif amsv:
                    match = f'否（AMS={amsv}）'
                else:
                    match = 'AMS 無序號（final_assembly_number 未寫入）'
                if r['kind'] == 'table':
                    if match != '是':
                        st['table_rejected'] += 1
                        continue
                    st['table_match'] += 1
                else:
                    st['cert_match' if match == '是' else ('cert_mismatch' if amsv else 'cert_nofan')] += 1
                key = (al, last7(r['serial']) or r['serial'])
                prio = 2 if r.get('is_cal') else (1 if r['kind'] == 'cert' else 0)
                prev = entries.get(key)
                if prev and prev['_prio'] >= prio:
                    also = f"{c['doc_id']}-{c['rev']} p.{r['page']}"
                    if prev['doc_id'] != c['doc_id'] and also not in prev['_also']:
                        prev['_also'].append(also)
                    continue
                e = dict(doc_id=c['doc_id'], rev=c['rev'], loc=f"p.{r['page']}", rule=rule,
                         level='factory', _kind=r['kind'], _prio=prio, _also=(prev['_also'] if prev else []),
                         _match=match, _tag=tag, _rec=r)
                if prev and prev['doc_id'] != c['doc_id']:
                    e['_also'].append(f"{prev['doc_id']}-{prev['rev']} {prev['loc']}")
                entries[key] = e
        s['cert_pages'] = st['cert_pages'] - s0[0]
        s['table_rows'] = st['table_rows'] - s0[1]

    by_alias, primary, alsoset = {}, set(), set()
    for (al, _), e in sorted(entries.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        r = e.pop('_rec')
        ser = r['serial']
        unit = r.get('unit_raw')
        f = [['銘牌序號', ser], ['序號與 AMS 相符', e.pop('_match')], ['證書位號', ' / '.join(r['tags']) or '—']]
        e.pop('_prio')
        if r['kind'] == 'cert' and not r.get('is_cal'):
            f += [['證書類型', r['ctype']], ['出廠校正量程（原文）', '—（非校正證書）'],
                  ['證書頁', f"p.{r['page']}" + (f" · {r['certid']}" if r.get('certid') else '')],
                  ['出廠型號', r.get('model') or '—']]
        elif r['kind'] == 'cert':
            f += [['出廠校正量程（原文）', r.get('range_raw') or '—'],
                  ['出廠量程下限_num', num(r['lo']) if r.get('lo') else None],
                  ['出廠量程上限_num', num(r['hi']) if r.get('hi') else None],
                  ['量程單位', (lambda u0: UNIT_MAP.get(u0.upper().replace('(G)', '').strip(), u0))(re.sub(r'@.*$', '', unit).strip())
                   if unit else '—'],
                  ['感測器型式', r.get('sensor') or (r.get('devtype') or '—')],
                  ['校正日期', r.get('caldate') or (f"{r['issued']}（簽發日）" if r.get('issued') else '—')],
                  ['結果', r.get('result') or '未載明'],
                  ['證書頁', (f"p.{'–'.join(str(x) for x in (r['pages'][0], r['pages'][-1]))}" if len(r['pages']) > 1
                             else f"p.{r['page']}") + (f" · {r['certid']}" if r.get('certid') else '')],
                  ['出廠型號', r.get('model') or '—']]
        else:
            if not r['tags']:
                f[2][1] = '—（彙整表位號欄與序號列錯位，未採用；以序號對應）'
            f += [['出廠校正量程（原文）', '—（彙整表，無量程）'], ['證書頁', f"p.{r['page']}（出貨彙整表）"],
                  ['出廠型號', r.get('model') or '—']]
        if f[1][1].startswith('否'):
            others = [x for x in fan_rev.get(last7(ser), []) if x != al]
            f.insert(2, ['序號在 AMS 屬於', '、'.join(f'{alias2tag.get(x)} ({x})' for x in others) if others
                         else '（AMS 無此序號：可能已更換，或 PDF/OCR 誤讀）'])
        primary.add(e['doc_id'])
        alsoset.update(x.split(' ')[0].rsplit('-', 1)[0] for x in e['_also'])
        if e['_also']:
            f.append(['亦見於', '；'.join(e['_also'][:6])])
        e.pop('_also'); e.pop('_tag'); e.pop('_kind')
        e['fields'] = f
        by_alias.setdefault(al, []).append(e)
    # 同一 alias 已有相符證書時，捨棄「非校正證書 + 序號不符」列（多為 OCR 誤讀序號，如 p.163 23S1PG378571）
    for al in list(by_alias):
        v = by_alias[al]
        if any(e['fields'][1][1] == '是' for e in v):
            by_alias[al] = [e for e in v if e['fields'][1][1] == '是' or not any(f[0] == '證書類型' for f in e['fields'])]
    # 同一 alias 多序號時: 相符者在前
    for al in by_alias:
        by_alias[al].sort(key=lambda e: (e['fields'][1][1] != '是', e['doc_id']))

    n_match = sum(1 for v in by_alias.values() if any(e['fields'][1][1] == '是' for e in v))
    out = dict(kind='eomr', generated_by='tools/db/docmap_eomr.py', searched=searched, by_alias=by_alias,
               stats=dict(aliases_matched=len(by_alias), rows=sum(len(v) for v in by_alias.values()),
                          aliases_serial_match=n_match, **st,
                          notes='序號後 7 碼 vs AMS final_assembly_number（SQLite 最新值）；彙整表只收相符列；'
                                '證書頁不符仍收並標示（附「序號在 AMS 屬於」）；不輸出採購單/訂單號；p.N 為 PDF 頁序'))
    for s in searched:
        s.pop('_full', None)
        if s['used'] and s['doc_id'] not in primary:
            s['used'] = False
            if s.get('why', '').startswith('無文字層'):
                pass
            elif s['doc_id'] in alsoset:
                s['why'] = '同序號證書已由其他文件收錄（列於「亦見於」）'
            elif s.get('cert_pages', 0) + s.get('table_rows', 0) == 0:
                s['why'] = '無 Rosemount 證書頁/序號彙整表'
            else:
                s['why'] = '有證書頁，但位號/序號未對上 AMS 設備（或彙整表列序號不符被剔除）'
    out['stats']['docs_used'] = sum(1 for s in searched if s['used'])
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out['stats'], ensure_ascii=False), file=sys.stderr)


if __name__ == '__main__':
    main()
