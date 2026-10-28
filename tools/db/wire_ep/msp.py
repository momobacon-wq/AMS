# -*- coding: utf-8 -*-
r"""tools/db/wire_ep/msp.py — 手動同步盤面板（MSP，G1xCCS01UC001／S10CCS01UC001）端子定位：端子排 XDC／XVT／XDI／XDO（v16，給 wire_ge.py 用）。

圖（都是向量、各頁 /Rotate 0）：
  G11  EOMR HT1-1-AQB01-Q1980-0 裡的 GE 226B4841 rev04（GT11 & GT21 MANUAL SYNCH PLATE）：圖號 n → PDF 第 n+8 頁
       （p.12＝sheet 04 LAYOUT (REAR VIEW)、p.18＝sheet 10 TERMINAL DIAGRAM）。sheet 01、04 以外每張都蓋 DRAFT 浮水印；
       正式版 HT0-1-EGJ01-D0071-0（同為 rev04）是掃描圖，sheet 07–10 相同。
  S10  'MK_1080188 C086A LAYOUT AND ELECTRICAL DIAGRAM …'＝GE 226B4843 rev02：圖號 n → PDF 第 n 頁（p.4 背視圖、p.10 端子圖）。
       正式版 rev04＝HT0-1-EGK01-D0048-0（掃描圖，p.8–10＝sheet 07–09）：端子與表相同，但有幾個迴路的來源框不同（REV04_SOURCE）。
  G12  沒有向量圖（HT0-1-EGJ01-D0072-0＝226B4842 rev04 是掃描圖）→ 用 G11 那份當**類比**：D0072 的 sheet 04／07–10 端子排、端子號、
       PAGE/COLUMN 表都與 226B4841 相同，只有 52L1 與 52L3 對調（G12 的線路斷路器是 52L3）。框畫在 G11 的圖上；
       圖上印的字放 extra.signal_drawn，對調後的讀法只寫在 extra.analog_note，不冒充圖上的字。

框的種類：
  strip：背視圖上的端子排名（XDI …）
  term ：背視圖上這一號端子的格子（數向量畫的格子，格數與號碼數不合時 extra.approx＝1）
  row  ：TERMINAL DIAGRAM 表裡這一號的那一列；extra 有 PAGE/COLUMN 參照，與那一欄原理圖上的訊號名、燈／按鈕、來源框（EX／GPP／CUST）。
"""
import copy
import re

try:
    import fitz
except ImportError:          # 只有建索引才用到
    fitz = None

STRIPS = ('XDC', 'XVT', 'XDI', 'XDO')
UNIT_DOC = {'G11': 'epm1', 'G12': 'epm1', 'S10': 'epms'}
ANALOG = {  # 機組 → (框畫在哪一台的圖, 理由, 標籤對調)
    'G12': ('G11',
            'G12 沒有向量的面板圖（HT0-1-EGJ01-D0072-0＝226B4842 rev04 是掃描圖）；它的 sheet 04／07／08／09／10'
            '（PDF p.5／8／9／10／11）端子排、端子號與 PAGE/COLUMN 表都與 G11 的 226B4841 相同，只有 52L1、52L3 對調'
            '（G12 的線路斷路器是 52L3）→ 框畫在 G11 的圖上。',
            {'52L1': '52L3', '52L3': '52L1'}),
}
# S10 的向量檔是 226B4843 rev02；正式版 rev04（掃描圖 HT0-1-EGK01-D0048-0 p.8–10＝sheet 07–09）端子與表相同，
# 但這幾個迴路的來源框不同（逐一看過）；None＝rev04 沒有來源框。表外的迴路兩版相同。
REV04_SOURCE = {
    ('XDI', '23'): None, ('XDI', '24'): None,        # 52L3 TRIPPED   rev02 GPP → rev04 無框
    ('XDI', '29'): None, ('XDI', '30'): None,        # 52L2 TRIPPED   rev02 GPP → rev04 無框
    ('XDI', '31'): 'CUST', ('XDI', '32'): 'CUST',    # 52L1 OPEN      rev02 GPP → rev04 CUST
    ('XDI', '33'): 'CUST', ('XDI', '34'): 'CUST',    # 52L1 CLOSED    rev02 GPP → rev04 CUST
    ('XDI', '35'): None, ('XDI', '36'): None,        # 52L3 CL PERMIT rev02 GPP → rev04 無框
    ('XDI', '37'): None, ('XDI', '38'): None,        # 52L2 CL PERMIT rev02 GPP → rev04 無框
    ('XDO', '25'): None, ('XDO', '26'): None,        # 52L3 CLOSE     rev02 GPP → rev04 無框
    ('XDO', '27'): None, ('XDO', '28'): None,        # 52L2 CLOSE     rev02 GPP → rev04 無框
}
REV_NOTE = ('框的向量檔是 226B4843 rev02；正式版 rev04（HT0-1-EGK01-D0048-0 PDF p.8–10，掃描圖）有幾個迴路的來源框不同，'
            '兩版的來源框都列出（source_rev02／source_rev04），不替任何一版下結論')
NOTES = {
    'G11': 'EOMR HT1-1-AQB01-Q1980-0 裡的 226B4841 rev04 向量檔：sheet 01、04（背視圖）以外都蓋 DRAFT 浮水印；'
           '正式版 HT0-1-EGJ01-D0071-0（同為 rev04，掃描圖）sheet 07–10 相同。',
    'S10': '框的是 226B4843 rev02（Doc Name 135V6580，2022/05/20）；正式版 rev04＝HT0-1-EGK01-D0048-0（掃描圖）。'
           '端子排、端子與表相同，來源框有差（見 source_rev02／source_rev04）。',
}
SRC_BOX = {'EX', 'GPP', 'CUST'}
# 迴路電源：sheet 07（MSP POWER SUPPLY 24 VDC → -XDC 1/2 → MCB -98-1 4A → +24VDC 匯流 → 奇數 XDI → 外部接點（虛線）→ 偶數 XDI → 燈 → -24VDC）
# 與 sheet 09（CONTACT OUTPUT SIGNALS／OUTPUT SIGNALS TO TCP：面板按鈕／選擇開關的接點，面板側不供電）。
CIRCUIT = {
    'XDI': 'MSP 24 VDC（XDC 1+／2-，MCB 98-1 4A）送到外部接點、面板上的燈／帶燈按鈕',
    'XDO': '面板按鈕／選擇開關的乾接點送 TCP；濕點電源在 TCP 側〔推論〕',
}
COLORS = {'GREEN', 'RED', 'WHITE', 'YELLOW', 'BLUE', 'AMBER'}


def _norm_strip(s):
    s = re.sub(r'^[=+\-\s]+', '', str(s or '')).strip().upper()
    return s if s in STRIPS else None


def _norm_term(s):
    m = re.search(r'(\d+)\s*$', str(s or ''))      # '13'、'01'、'XDI 13'、'-XDI:13' → '13'
    return str(int(m.group(1))) if m else None


def _unit(entry):
    u = str(entry.get('unit') or '').upper()
    if u in ('G11', 'G12', 'S10'):
        return u
    m = re.search(r'(G11|G12|S10)', str(entry.get('jb') or (entry.get('wire') or {}).get('jb') or ''))
    return m.group(1) if m else None


def key_of(entry, cond):
    """這條芯 MSP 那一端（一律 JB 端）→ (機組, 端子排, 端子號) 或 None。"""
    unit = _unit(entry)
    strip = _norm_strip(entry.get('jb_tb') or (entry.get('wire') or {}).get('jb_tb'))
    term = _norm_term(cond.get('jb_term', cond.get('jb')))
    if not (unit and strip and term):
        return None
    return (unit, strip, term)


# ---------------------------------------------------------------- 小工具
def _words(page):
    return [(fitz.Rect(w[:4]), w[4]) for w in page.get_text('words')]


def _black_lines(page):
    """黑色直線段 (x0, y0, x1, y1)；長方形拆成四邊。"""
    out = []
    for d in page.get_drawings():
        if d.get('color') not in ((0.0, 0.0, 0.0), (0, 0, 0)):
            continue
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                out.append((min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)))
            elif it[0] == 're':
                r = it[1]
                out += [(r.x0, r.y0, r.x1, r.y0), (r.x0, r.y1, r.x1, r.y1),
                        (r.x0, r.y0, r.x0, r.y1), (r.x1, r.y0, r.x1, r.y1)]
    return out


def _uniq(vals, tol=0.3):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _box(r):
    return [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]


def _sheet_map(doc):
    """圖框印的圖號 → 頁序（0 起）（'PAGE 07 OF 10'／'Page 7 of 10'）。"""
    m = {}
    for i, pg in enumerate(doc):
        ws = [w[4] for w in pg.get_text('words', sort=True)]
        for j in range(len(ws) - 2):
            if ws[j].lower() == 'page' and ws[j + 1].isdigit() and ws[j + 2].lower() == 'of':
                m.setdefault(int(ws[j + 1]), i)
                break
    return m


def _page_by_title(doc, title, need):
    """第一個文字有 title、而且 need 裡至少 3 個字的頁（跳過目錄頁）。"""
    for i, pg in enumerate(doc):
        t = ' '.join(pg.get_text().split()).upper()
        if title in t and len({w[4] for w in pg.get_text('words')} & set(need)) >= 3:
            return i
    return None


# ---------------------------------------------------------------- 背視圖
def _rear_view(page):
    """{端子排: {'label': Rect, 'cells': [Rect…], 'first': n, 'last': n, 'exact'}}"""
    ws = _words(page)
    labels = sorted([(r, t) for r, t in ws if t in STRIPS and r.x0 < page.rect.width / 3],
                    key=lambda rt: rt[0].y0)
    lines = _black_lines(page)
    out = {}
    for i, (lab, name) in enumerate(labels):
        y_next = labels[i + 1][0].y0 if i + 1 < len(labels) else page.rect.height
        nums = sorted([(r, t) for r, t in ws if t.isdigit() and lab.x1 + 8 < r.x0 < lab.x1 + 30
                       and lab.y0 - 2 < r.y0 < y_next], key=lambda rt: rt[0].y0)
        if not nums:
            continue
        first, last = int(nums[0][1]), int(nums[-1][1])
        y_lo, y_hi = lab.y1 - 1.0, nums[-1][0].y1 + 3.0
        ys = _uniq([l[1] for l in lines if abs(l[3] - l[1]) < 0.05 and (l[2] - l[0]) >= 25
                    and lab.x0 - 25 < l[0] and l[2] < lab.x1 + 25 and y_lo <= l[1] <= y_hi])
        xs = [l for l in lines if abs(l[3] - l[1]) < 0.05 and (l[2] - l[0]) >= 25
              and lab.x0 - 25 < l[0] and l[2] < lab.x1 + 25 and y_lo <= l[1] <= y_hi]
        x0 = min(l[0] for l in xs) if xs else lab.x0
        x1 = max(l[2] for l in xs) if xs else lab.x1
        cells = [fitz.Rect(x0, ys[k], x1, ys[k + 1]) for k in range(len(ys) - 1)]
        out[name] = {'label': lab, 'cells': cells, 'first': first, 'last': last,
                     'exact': len(cells) == last - first + 1, 'y_first': nums[0][0], 'y_last': nums[-1][0]}
    return out


# ---------------------------------------------------------------- 端子圖（表）
def _term_table(page):
    """TERMINAL DIAGRAM 頁 → {端子排: {端子號: (列框, 參照字)}}。"""
    ws = _words(page)
    lines = _black_lines(page)
    vlines = [l for l in lines if abs(l[2] - l[0]) < 0.05 and (l[3] - l[1]) > 5]
    hlines = [l for l in lines if abs(l[3] - l[1]) < 0.05 and (l[2] - l[0]) > 5]
    vx = {}
    for l in vlines:
        k = round(l[0], 1)
        vx[k] = vx.get(k, 0) + 1
    cols = sorted(x for x, c in vx.items() if c >= 5)
    out = {}
    for hr, ht in ws:
        s = _norm_strip(ht) if ht.startswith('=+-') else None
        if not s:
            continue
        left = max([x for x in cols if x < hr.x0 - 2], default=None)
        right = min([x for x in cols if x > hr.x1 + 2], default=None)
        if left is None or right is None:
            continue
        div = [x for x in cols if left + 5 < x < right - 5]
        div = div[0] if div else (left + right) / 2
        bottom = max([l[3] for l in vlines if abs(l[0] - left) < 0.2], default=page.rect.height)
        tab = out.setdefault(s, {})
        for r, t in ws:
            if not (t.isdigit() and left < (r.x0 + r.x1) / 2 < div and r.y0 > hr.y1 + 10 and r.y1 < bottom):
                continue
            ym = (r.y0 + r.y1) / 2
            ov = [l[1] for l in hlines if l[0] <= left + 1 and l[2] >= right - 1]
            ya = max([y for y in ov if y < ym], default=None)
            yb = min([y for y in ov if y > ym], default=None)
            if ya is None or yb is None:
                continue
            ref = ' '.join(t2 for r2, t2 in ws if div < (r2.x0 + r2.x1) / 2 < right and ya < (r2.y0 + r2.y1) / 2 < yb)
            tab[str(int(t))] = (fitz.Rect(left, ya, right, yb), ref.strip())
    return out


# ---------------------------------------------------------------- 原理圖那一欄
def _columns(page):
    ruler = sorted([((r.x0 + r.x1) / 2, int(t)) for r, t in _words(page) if t.isdigit() and len(t) == 1 and r.y1 < 32])
    if len(ruler) < 2:
        return None
    (xa, ka), (xb, kb) = ruler[0], ruler[-1]
    pitch = (xb - xa) / (kb - ka)
    return lambda k: (xa + (k - ka) * pitch - pitch / 2, xa + (k - ka) * pitch + pitch / 2)


def _line_from(ws, start, gap=7.0):
    """從 start 往右串同一行的字（字距小於 gap）。"""
    out = [start]
    cur = start
    same = sorted([w for w in ws if abs(w[0].y0 - start[0].y0) < 1.0 and w[0].x0 > start[0].x0], key=lambda w: w[0].x0)
    for w in same:
        if w[0].x0 - cur[0].x1 <= gap:
            out.append(w)
            cur = w
        else:
            break
    return out


def _schematic(page, strip, term, col):
    ws = _words(page)
    colf = _columns(page)
    if colf is None:
        return None
    cx0, cx1 = colf(col)
    anchor = '-' + strip
    anchors = [w for w in ws if w[1] == anchor]

    def anchored(w):
        ym = (w[0].y0 + w[0].y1) / 2
        return any(w[0].x0 - 18 < a[0].x1 < w[0].x0 - 3 and abs((a[0].y0 + a[0].y1) / 2 - ym) < 16 for a in anchors)

    def find(n, near=None):
        cands = [w for w in ws if w[1] == str(n) and w[0].height < 8]
        if near is not None:
            return [w for w in cands if abs(w[0].y0 - near[0].y0) < 1.5 and 20 < w[0].x0 - near[0].x0 < 160] or \
                   [w for w in cands if abs(w[0].x0 - near[0].x0) < 4 and 40 < abs(w[0].y0 - near[0].y0) < 160]
        return [w for w in cands if cx0 - 15 < w[0].x0 < cx1 + 5 and anchored(w)]

    n = int(term)
    hit = find(n)
    if not hit and strip == 'XDO' and n % 2 == 0:          # XDO 偶數端子沒有 '-XDO' 標籤
        mate = find(n - 1) or [w for w in ws if w[1] == str(n - 1) and w[0].height < 8 and anchored(w)]
        for m in mate:
            hit = [w for w in find(n, near=m) if cx0 - 15 < w[0].x0 < cx1 + 5]
            if hit:
                break
    if not hit:
        return None
    me = hit[0]
    info = {'sch_box': _box(me[0])}
    if strip in ('XDI', 'XDC', 'XVT'):                       # 上下一對，訊號名在兩者之間
        mate = [w for w in ws if w[1] == str(n + 1 if n % 2 else n - 1) and abs(w[0].x0 - me[0].x0) < 4 and w[0].height < 8]
        if mate:
            top, bot = sorted([me, mate[0]], key=lambda w: w[0].y0)
            band = [w for w in ws if top[0].y1 < w[0].y0 < bot[0].y0 and me[0].x0 - 3 < w[0].x0 < me[0].x0 + 100]
            src = [w[1] for w in band if w[1] in SRC_BOX and w[0].x0 < me[0].x0 + 40]
            lab = sorted([w for w in band if w[1] not in SRC_BOX], key=lambda w: (w[0].x0 - me[0].x0))
            if lab:
                info['signal'] = ' '.join(w[1] for w in _line_from(ws, lab[0]))
            if src:
                info['source'] = src[0]
            dev = [w for w in ws if w[1].startswith('-') and w[1] != anchor and w[0].y0 > bot[0].y1 + 40
                   and me[0].x0 - 22 < w[0].x1 < me[0].x0 - 3]
            if dev:
                d0 = min(dev, key=lambda w: w[0].y0)
                info['device'] = d0[1]
                col_w = [w[1] for w in ws if w[1] in COLORS and me[0].x0 - 22 < w[0].x1 < me[0].x0 - 3 and 0 < w[0].y0 - d0[0].y0 < 30]
                if col_w:
                    info['lamp_color'] = col_w[0]
    else:                                                    # XDO：左右一對，訊號名在下面
        odd = me if n % 2 else None
        mate = find(n + 1, near=me) if n % 2 else None
        if n % 2 == 0:
            odd_c = [w for w in ws if w[1] == str(n - 1) and w[0].height < 8 and abs(w[0].y0 - me[0].y0) < 1.5 and 20 < me[0].x0 - w[0].x0 < 160]
            odd = odd_c[0] if odd_c else me
            mate = [me]
        x_lo = odd[0].x0 - 25
        x_hi = (mate[0][0].x1 if mate else odd[0].x1 + 60) + 10
        below = sorted([w for w in ws if me[0].y1 + 4 < w[0].y0 < me[0].y1 + 28 and x_lo < (w[0].x0 + w[0].x1) / 2 < x_hi],
                       key=lambda w: (round(w[0].y0), w[0].x0))
        if below:
            info['signal'] = ' '.join(w[1] for w in below if abs(w[0].y0 - below[0][0].y0) < 1.0)
            src = [w[1] for w in ws if w[1] in SRC_BOX and 0 < w[0].y0 - below[0][0].y1 < 30
                   and x_lo < (w[0].x0 + w[0].x1) / 2 < x_hi]
            if src:
                info['source'] = src[0]
        dev = [w for w in ws if w[1].startswith('-') and w[1] != anchor and 0 <= w[0].x0 - me[0].x0 < 15
               and 30 < me[0].y0 - w[0].y1 < 100]
        if dev:
            info['device'] = max(dev, key=lambda w: w[0].y0)[1]
    return info


# ---------------------------------------------------------------- 建索引
def build_index(pdf_paths):
    """pdf_paths：{機組: 路徑}（G11、S10；G12 不建、查的時候借 G11 的）。→ {'strips','terms','doc'}；
    原理圖讀到的來源框照原樣放 extra.source（S10 的 rev02／rev04 在 locate 裡分開）。"""
    idx = {'strips': {}, 'terms': {}, 'doc': {}}
    cache = {}
    for unit, path in pdf_paths.items():
        if path not in cache:
            doc = fitz.open(path)
            rv = _page_by_title(doc, 'LAYOUT (REAR VIEW', STRIPS)
            td = _page_by_title(doc, 'PAGE / COLUMN', ['=+-' + s for s in STRIPS])
            cache[path] = {
                'rv_page': rv, 'td_page': td,
                'rear': _rear_view(doc[rv]) if rv is not None else {},
                'table': _term_table(doc[td]) if td is not None else {},
                'sheets': _sheet_map(doc), 'doc': doc, 'sch': {},
            }
        c = cache[path]
        idx['doc'][unit] = path
        for strip, rv in c['rear'].items():
            idx['strips'][(unit, strip)] = [{'page': c['rv_page'] + 1, 'box': _box(rv['label']), 'text': strip, 'kind': 'strip', 'extra': {}}]
            for k, cell in enumerate(rv['cells']):
                term = str(rv['first'] + k)
                extra = {'cell': k + 1, 'of': len(rv['cells'])}
                if not rv['exact']:
                    extra['approx'] = 1
                idx['terms'].setdefault((unit, strip, term), []).append(
                    {'page': c['rv_page'] + 1, 'box': _box(cell), 'text': f'{strip} {term}', 'kind': 'term', 'extra': extra})
        for strip, rows in c['table'].items():
            for term, (rect, ref) in rows.items():
                extra = {'ref': ref}
                m = re.match(r'/?(\d+)\.(\d)', ref)
                if m:
                    sheet, col = int(m.group(1)), int(m.group(2))
                    pidx = c['sheets'].get(sheet)
                    extra.update({'sheet': sheet, 'column': col})
                    if pidx is not None:
                        ck = (pidx, strip, term, col)
                        if ck not in c['sch']:
                            c['sch'][ck] = _schematic(c['doc'][pidx], strip, term, col)
                        s = dict(c['sch'][ck] or {})
                        s.setdefault('source', None)       # None＝這個迴路沒有 EX／GPP／CUST 框
                        extra['sch_page'] = pidx + 1
                        extra.update(s)
                else:
                    extra['empty'] = 1          # 有這一號端子、面板上沒畫迴路
                if strip in CIRCUIT and not extra.get('empty'):
                    extra['circuit'] = CIRCUIT[strip]
                    if strip == 'XDI':
                        extra['pole'] = '+24VDC 送往接點' if int(term) % 2 else '接點回來接燈'
                idx['terms'].setdefault((unit, strip, term), []).append(
                    {'page': c['td_page'] + 1, 'box': _box(rect), 'text': f'{strip} {term} {ref}'.strip(), 'kind': 'row', 'extra': extra})
    for c in cache.values():
        c['doc'].close()
    return idx


# ---------------------------------------------------------------- 統一介面
def build(paths):
    """paths：{'epm1': G11 的 EOMR, 'epms': S10 的 226B4843}（缺哪份就少哪台）。"""
    have = {u: paths[k] for u, k in UNIT_DOC.items() if u not in ANALOG and paths.get(k)}
    return build_index(have)


def _swap(text, swap):
    pat = re.compile('|'.join(map(re.escape, swap)))
    return pat.sub(lambda m: swap[m.group()], text)


def locate(ix, entry, cond):
    """→ [hit]：背視圖上這一號的格子（主框）＋端子排名（副框）、端子圖表那一列（主框）。
    G12 借 G11 的圖（extra.analog＝'G11'）；S10 的來源框兩版並列。"""
    k = key_of(entry, cond)
    if not k:
        return []
    unit = k[0]
    src_unit, reason, swap = ANALOG.get(unit, (unit, '', {}))
    kk = (src_unit,) + k[1:]
    terms = ix['terms'].get(kk, [])
    common = {}
    if swap:
        common = {'analog': src_unit, 'analog_reason': reason}
    if NOTES.get(src_unit):
        common['doc_note'] = NOTES[src_unit]

    def hit(h, label, primary, x):
        return {'doc_key': UNIT_DOC[unit], 'page': h['page'], 'box': list(h['box']), 'kind': h['kind'], 'label': label,
                'primary': primary, 'extra': dict(x, **common)}
    has_term = any(h['kind'] == 'term' for h in terms)
    out = [hit(h, k[1], not has_term, {}) for h in ix['strips'].get(kk[:2], [])]
    for h in terms:
        x = copy.deepcopy(h['extra'])
        if h['kind'] == 'row':
            if unit == 'S10' and 'source' in x:
                x['source_rev02'] = x.pop('source')
                x['source_rev04'] = REV04_SOURCE.get(k[1:], x['source_rev02'])
                x['rev_note'] = REV_NOTE
            if swap:
                notes = []
                for f in ('signal', 'device'):
                    if x.get(f):
                        drawn = x.pop(f)
                        x[f + '_drawn'] = drawn
                        sw = _swap(drawn, swap)
                        if sw != drawn:
                            notes.append('%s「%s」' % ('訊號' if f == 'signal' else '元件', sw))
                if notes:
                    x['analog_note'] = '%s 上 52L1、52L3 對調：應讀作 %s（圖上印的是 %s 的字）' % (unit, '、'.join(notes), src_unit)
        out.append(hit(h, '%s %s' % k[1:], True, x))
    return out


def missing(ix, entry, cond):
    """找不到端子格／表列時的原因（卡片註記用）；兩種都找得到回 None。"""
    k = key_of(entry, cond)
    if not k:
        if not _unit(entry):
            return 'MSP 只對 G11、G12、S10'
        if not _norm_strip(entry.get('jb_tb') or (entry.get('wire') or {}).get('jb_tb')):
            return 'MSP 端子排名稱不是 XDC／XVT／XDI／XDO（「%s」）' % (entry.get('jb_tb') or '')
        return '端子寫法解析不出（「%s」）' % (cond.get('jb_term') or '').strip()
    src = ANALOG.get(k[0], (k[0],))[0]
    if src not in ix['doc']:
        return '%s 的 MSP 圖不在文件庫' % k[0]
    kinds = {h['kind'] for h in ix['terms'].get((src,) + k[1:], [])}
    why = []
    if 'term' not in kinds:
        why.append('背視圖上沒有 %s %s' % k[1:])
    if 'row' not in kinds:
        why.append('端子圖表沒有 %s %s' % k[1:])
    return '；'.join(why) or None
