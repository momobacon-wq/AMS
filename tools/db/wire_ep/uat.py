# -*- coding: utf-8 -*-
r"""tools/db/wire_ep/uat.py — 廠用變壓器（UAT，C10BBT10／C10BCT10）就地控制箱端子定位（v16，給 wire_ge.py 用）。

圖：Fortune 21A3D3014 rev 5 As Built（HT0-1-ETE01-D1030，檔名與標題欄寫 UNIT MAIN TRANSFORMER，p.3 銘牌表證明內容是 UAT）。
  六台 UAT 共用一份（p.3 NAMEPLATE 表：Unit 1 UAT11 C10BBT10、UAT12 C10BCT10 … Unit 3 UAT32 C30BCT10），鍵的機組一律 '*'。
用到的三張（照標題找，頁碼只是找不到時的備案）：
  layout "(LOCAL CONTROL CABINET LAYOUT)"     p.3  → 各剖面上的端子排標籤（＋端子排外框）
  ct     "(CTs WIRING CONNECTION)"            p.19 → TBA…TBQ、TBHT／TBXT／TBYT 的 1…6 號格
  tb     "(CONTROL CABINET TERMINAL BLOCKS)"  p.21 → TB1…TB10 的格
各頁 /Rotate 0，框＝未轉 PDF 座標。
接線圖上的筆誤照兄弟芯修：GE 接線圖印 'TB 29'（夾在 TB2 28 與 TB2 30 之間）→ 讀作 TB2 29（p.12 63DT → GPP3／GPP4 → TB2 29／30）。
"""
import re

try:
    import fitz
except ImportError:          # 只有建索引才用到
    fitz = None

DOC_KEY = 'epua'
STRIP_RE = re.compile(r'^TB(?:[A-Z]{1,2}|\d{1,2})$')
TITLES = {'layout': ('LOCAL CONTROL CABINET LAYOUT', 3),
          'ct': ('CTS WIRING CONNECTION', 19),
          'tb': ('CONTROL CABINET TERMINAL BLOCKS', 21)}
UAT_JB = re.compile(r'\bUAT\b|C[123]0BCT10|C[123]0BBT10')


def _norm_strip(s):
    s = re.sub(r'[\s\-_]', '', (s or '').upper())
    m = re.match(r'^TB0*(\d+)$', s)
    return 'TB' + m.group(1) if m else s


def _norm_term(t):
    t = (t or '').strip().upper()
    return str(int(t)) if t.isdigit() else t


def _r(b):
    return [round(float(v), 1) for v in b]


def _find_pages(doc):
    out = {}
    for key, (needle, fallback) in TITLES.items():
        hit = [i for i in range(doc.page_count)
               if needle in re.sub(r'\s+', ' ', doc[i].get_text().upper())]
        out[key] = hit[0] if hit else fallback - 1
    return out


def _lines(page):
    """水平 (y, x0, x1) 與垂直 (x, y0, y1) 線段。"""
    H, V = [], []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                p, q = it[1], it[2]
                if abs(p.y - q.y) < 0.3:
                    H.append((p.y, min(p.x, q.x), max(p.x, q.x)))
                elif abs(p.x - q.x) < 0.3:
                    V.append((p.x, min(p.y, q.y), max(p.y, q.y)))
            elif it[0] == 're':
                r = it[1]
                H += [(r.y0, r.x0, r.x1), (r.y1, r.x0, r.x1)]
                V += [(r.x0, r.y0, r.y1), (r.x1, r.y0, r.y1)]
    return H, V


def _cell(wb, H, V):
    """號碼字 → 包住它的那一格，沒有回 None。"""
    cx, cy = (wb[0] + wb[2]) / 2, (wb[1] + wb[3]) / 2
    up = [(y, a, b) for y, a, b in H if a - .5 <= cx <= b + .5 and y <= wb[1] + 1.5 and cy - y < 16]
    dn = [(y, a, b) for y, a, b in H if a - .5 <= cx <= b + .5 and y >= wb[3] - 1.5 and y - cy < 16]
    if not (up and dn):
        return None
    top, bot = max(up), min(dn)
    # 格寬＝上下兩條邊的範圍（格內的直向跨接片不算）
    x0, x1 = max(top[1], bot[1]), min(top[2], bot[2])
    walls = [x for x, a, b in V if a <= top[0] + 1 and b >= bot[0] - 1 and (abs(x - x0) < 1 or abs(x - x1) < 1)]
    if len(walls) < 2:
        return None
    box = (x0, top[0], x1, bot[0])
    w, h = box[2] - box[0], box[3] - box[1]
    return box if 20 <= w <= 70 and 6 <= h <= 20 else None


def _side_label(words, box, side):
    cy = (box[1] + box[3]) / 2
    cand = []
    for w in words:
        if (w[3] - w[1]) > (w[2] - w[0]) or not re.search(r'[A-Z0-9]', w[4]):
            continue                   # 直寫的說明（'[TO CTB]'、'TO : GPP'）與標點
        wy = (w[1] + w[3]) / 2
        if abs(wy - cy) > (box[3] - box[1]) * 0.6:
            continue
        gap = box[0] - w[2] if side == 'left' else w[0] - box[2]
        if 0 <= gap <= 30:
            cand.append((gap, w[4]))
    return min(cand)[1] if cand else ''


def _tb_sheet(page, pno, sheet_kind, strips, terms):
    words = page.get_text('words')
    H, V = _lines(page)
    labels = [w for w in words if STRIP_RE.match(w[4])]
    cells = {}
    for w in words:
        if not w[4].isdigit():
            continue
        box = _cell(w[:4], H, V)
        if not box:
            continue
        above = [l for l in labels if box[0] - 2 <= (l[0] + l[2]) / 2 <= box[2] + 2 and l[3] <= box[1] + 1]
        if not above:
            continue
        lab = max(above, key=lambda l: l[3])
        s, t = _norm_strip(lab[4]), _norm_term(w[4])
        if (s, t) in cells:          # 同一號出現兩次取最上面那個
            continue
        cells[(s, t)] = box
        terms.setdefault(('*', s, t), []).append({
            'page': pno + 1, 'box': _r(box), 'text': f'{lab[4]} {w[4]}', 'kind': 'row',
            'extra': {'sheet': sheet_kind, 'left': _side_label(words, box, 'left'),
                      'right': _side_label(words, box, 'right')}})
    for lab in labels:
        s = _norm_strip(lab[4])
        boxes = [b for (ss, _), b in cells.items() if ss == s]
        if not boxes:
            continue
        u = fitz.Rect(lab[:4])
        for b in boxes:
            u |= fitz.Rect(b)
        strips.setdefault(('*', s), []).append({
            'page': pno + 1, 'box': _r(u), 'text': lab[4], 'kind': 'strip',
            'extra': {'sheet': sheet_kind, 'part': 'block', 'terminals': len(boxes)}})


def _sections(words):
    """配置圖下緣的剖面名：[(名稱, x 中心, y0)]。"""
    out = []
    for i, w in enumerate(words):
        if w[4] in ('SECTION', 'VIEW') and i > 0:
            prev = words[i - 1]
            if prev[5:7] == w[5:7]:
                out.append((prev[4].replace("'", '') + ' ' + w[4], (prev[0] + w[2]) / 2, w[1]))
    return out


def _parts_spec(words):
    """零件表的 'TERMINAL BLOCK' 列：端子排 → 規格字（'600V 30A,40P'）。"""
    spec, last = {}, (None, -99)
    for w in sorted(words, key=lambda x: (x[1], x[0])):
        names = []
        if re.match(r'^TB\w*\.\.\.TB\w*$', w[4]):
            a, b = w[4].split('...')
            ma, mb = re.match(r'TB(\d+)', a), re.match(r'TB(\d+)', b)
            if ma and mb:
                names = ['TB%d' % k for k in range(int(ma.group(1)), int(mb.group(1)) + 1)]
        elif re.match(r'^TB[\w;]*$', w[4]):
            names = [n for n in w[4].split(';') if STRIP_RE.match(n)]
        if not names:
            continue
        row = [x for x in words if abs((x[1] + x[3]) / 2 - (w[1] + w[3]) / 2) < 4 and x[0] > w[2]]
        txt = ' '.join(x[4] for x in sorted(row, key=lambda x: x[0]))
        m = re.search(r'\d+V\s*\d+A,?\s*\d+P', txt)
        if 'TERMINAL' in txt and m:
            last = (m.group(0), w[1])
        elif ';' not in w[4] or w[1] - last[1] > 25 or not last[0]:
            continue                     # 不是零件表的列（例如配置圖標籤）
        for n in names:
            spec[n] = last[0]
    return spec


def _layout(page, pno, strips):
    words = page.get_text('words')
    secs = [s for s in _sections(words) if s[2] > page.rect.height * 0.75]
    spec = _parts_spec(words)
    if not secs:
        return
    top = min(s[2] for s in secs) - 330          # 剖面圖在剖面名上方
    segs = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                p, q = it[1], it[2]
                segs.append((min(p.x, q.x), min(p.y, q.y), max(p.x, q.x), max(p.y, q.y)))
            elif it[0] == 're':
                segs.append(tuple(it[1]))
    labs = [w for w in words if STRIP_RE.match(w[4]) and w[1] >= top]
    for w in labs:
        cx = (w[0] + w[2]) / 2
        below = [l[1] for l in labs if abs((l[0] + l[2]) / 2 - cx) < 12 and l[1] > w[3]]
        ylim = min(below) - 0.5 if below else w[3] + 230
        sec = min(secs, key=lambda s: abs(s[1] - cx))[0]
        s = _norm_strip(w[4])
        hit = {'page': pno + 1, 'box': _r(w[:4]), 'text': w[4], 'kind': 'strip',
               'extra': {'sheet': 'layout', 'part': 'label', 'section': sec, 'spec': spec.get(s, '')}}
        body = _body(w, segs, ylim)
        if body:
            hit['extra']['body'] = _r(body)
            hit['box'] = _r(fitz.Rect(w[:4]) | body)
        strips.setdefault(('*', s), []).append(hit)


def _touch(a, b, t):
    return a[0] - t <= b[2] and b[0] - t <= a[2] and a[1] - t <= b[3] and b[1] - t <= a[3]


def _body(w, segs, ylim):
    """標籤旁／下方畫的端子排外框（相連的短筆畫）。segs 是 (x0,y0,x1,y1)：fitz.Rect 聯集會丟掉寬 0 的線。"""
    x0, y0, x1, y1 = w[:4]
    xlo, xhi = x0 - 6, x1 + 40
    seed = (x0 - 1, y1 - 3, x1 + 12, y1 + 6)
    pool = [r for r in segs if max(r[2] - r[0], r[3] - r[1]) <= 12 and r[0] >= xlo and r[2] <= xhi
            and r[1] >= y0 - 2 and r[3] <= ylim]   # 不往標籤上方、不伸進下一條端子排
    left = [r for r in pool if not (_touch(r, seed, .3) and r[2] - r[0] < 12)]
    clus = [r for r in pool if _touch(r, seed, .3) and r[2] - r[0] < 12]
    if not clus:
        return None
    bb = [min(r[0] for r in clus), min(r[1] for r in clus), max(r[2] for r in clus), max(r[3] for r in clus)]
    got = list(clus)
    while True:
        grow = [r for r in left if _touch(r, bb, .6)]
        if not grow:
            break
        got += grow
        left = [r for r in left if not _touch(r, bb, .6)]
        bb = [min([bb[0]] + [r[0] for r in grow]), min([bb[1]] + [r[1] for r in grow]),
              max([bb[2]] + [r[2] for r in grow]), max([bb[3]] + [r[3] for r in grow])]
        if bb[3] - bb[1] > 220:
            return None
    # 去掉零星箭頭與板邊：只留佔 95 % 筆畫的那一段 x
    xc = sorted((r[0] + r[2]) / 2 for r in got)
    lo, hi = xc[int(len(xc) * .025)], xc[min(len(xc) - 1, int(len(xc) * .975))]
    core = [r for r in got if lo - .5 <= (r[0] + r[2]) / 2 <= hi + .5]
    bb = [min(r[0] for r in core), min(r[1] for r in core), max(r[2] for r in core), max(r[3] for r in core)]
    if bb[2] - bb[0] < 4 or bb[3] - bb[1] < 6 or bb[2] - bb[0] > 30:
        return None
    return fitz.Rect(bb)


def build_index(pdf_paths):
    """pdf_paths：{'*': 路徑}（或 {'G11': 路徑, …}，取第一份當 '*'）。"""
    path = pdf_paths.get('*') or next(iter(pdf_paths.values()))
    doc = fitz.open(path)
    pages = _find_pages(doc)
    strips, terms = {}, {}
    _layout(doc[pages['layout']], pages['layout'], strips)
    _tb_sheet(doc[pages['ct']], pages['ct'], 'ct', strips, terms)
    _tb_sheet(doc[pages['tb']], pages['tb'], 'tb', strips, terms)
    doc.close()
    return {'strips': strips, 'terms': terms, 'doc': {'*': path}, 'analog': {},
            'pages': {k: v + 1 for k, v in pages.items()}}


def _jb_of(entry):
    w = entry.get('wire') or {}
    return w.get('jb') or entry.get('jb') or '', w.get('jb_tb') or entry.get('jb_tb') or ''


def _split(raw):
    m = re.match(r'^\s*(TB[A-Z]{0,2}\d{0,2})\s*[- ]?\s*(\d+)\s*$', (raw or '').upper())
    return (m.group(1), m.group(2)) if m else (None, None)


def _parse(entry, cond):
    """→ (鍵或 None, 註記)；註記說明筆誤修正或缺端子排名。"""
    jb, jb_tb = _jb_of(entry)
    if entry.get('end', 'jb') != 'jb' or not UAT_JB.search(jb.upper()):
        return None, '不是 UAT 就地箱（只認 JB 端）'
    raw = cond.get('jb_term', cond.get('jb', '')) or ''
    if raw.strip().isdigit():
        if not jb_tb:
            return None, '只有端子號、接線圖標頭也沒寫端子排'
        return ('*', _norm_strip(jb_tb), _norm_term(raw)), '端子排取自標頭 ' + jb_tb
    strip, term = _split(raw)
    if not strip:
        return None, '端子寫法解析不出（「%s」）' % raw.strip()
    if strip == 'TB':                  # GE 接線圖 'TB 29' 筆誤：用兄弟芯的端子排
        sib = [_split(c.get('jb_term', c.get('jb', '')))[0] for c in entry.get('cond', [])]
        sib = [s for s in sib if s and s != 'TB']
        if sib and len(set(sib)) == 1:
            return ('*', _norm_strip(sib[0]), _norm_term(term)), '筆誤：「%s」照同一條電纜其他芯讀作 %s %s' % (raw, sib[0], term)
        return None, '「%s」少了端子排號' % raw
    return ('*', _norm_strip(strip), _norm_term(term)), ''


def key_of(entry, cond):
    return _parse(entry, cond)[0]


# ---------------------------------------------------------------- 統一介面
def build(paths):
    """paths：{'epua': 路徑}。"""
    return build_index({'*': paths[DOC_KEY]})


def _hit(page, box, kind, label, primary, extra):
    return {'doc_key': DOC_KEY, 'page': page, 'box': list(box), 'kind': kind, 'label': label, 'primary': primary, 'extra': extra}


def locate(ix, entry, cond):
    """→ [hit]：端子圖上這一號的格子（主框）＋同頁這條端子排的範圍（副框）、配置圖上的端子排（主框，標籤＋外框）。"""
    k, note = _parse(entry, cond)
    if not k:
        return []
    rows = ix['terms'].get(k, [])
    out = []
    for h in rows:
        x = h['extra']
        ex = {'sheet': x['sheet'], 'left': x['left'], 'right': x['right'], 'generic': 1}
        if note:
            ex['parse_note'] = note
        out.append(_hit(h['page'], h['box'], 'row', h['text'], True, ex))
    for h in ix['strips'].get(k[:2], []):
        x = h['extra']
        ex = {'sheet': x['sheet'], 'part': x['part'], 'generic': 1}
        for f in ('section', 'spec', 'body', 'terminals'):
            if x.get(f):
                ex[f] = x[f]
        prim = x['part'] == 'label' or not any(r['page'] == h['page'] for r in rows)
        out.append(_hit(h['page'], h['box'], 'strip', h['text'], prim, ex))
    return out


def missing(ix, entry, cond):
    """找不到端子格時的原因（卡片註記用）；找得到回 None。"""
    k, note = _parse(entry, cond)
    if not k:
        return note
    if ix['terms'].get(k):
        return None
    if ix['strips'].get(k[:2]):
        return 'UAT 端子圖上 %s 沒有第 %s 號' % k[1:]
    return 'UAT 就地箱圖沒有端子排 %s' % k[1]
