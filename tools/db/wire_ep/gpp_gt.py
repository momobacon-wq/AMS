# -*- coding: utf-8 -*-
r"""tools/db/wire_ep/gpp_gt.py — 燃機發電機保護盤（GPP MAIN G1xMKY40UC001／GPP-AUX G1xMKY40UC002）端子排定位（v16，給 wire_ge.py 用）。

圖：GE 140T1264 GPP Equipment Arrangement（HT0-1-EGJ01-D0023）。六台燃機發電機共用一份（p.2 標題頁 GENERATOR NO. GG10775 … GG10780），
  所以鍵的機組一律 '*'，不是類比。內容頁都是 /Rotate 90：幾何在轉正後的顯示座標算，回傳的框一律是**未轉的 PDF 座標**（＝page.get_text('words')）。
  strip：配置圖 12B／12D／12DA（標題 'GPP GENERAL ARRANGEMENT'）上的端子排標籤；extra.tip_box＝引線箭頭尖、extra.seg_box＝端子排本身
         （側視圖：兩個端座之間那一段軌道；子盤視圖：標籤正下方那一排端子塊）。BAY-3 (A) 是 AUX 盤，標籤沒印 (A)，這裡補上。
  row  ：端子表 13A–13E（標題 'TERMINAL BLOCK ARRNAGEMENT'，原圖拼錯）每一號端子一列（端子號／LOCATION／DESCRIPTION 三格）；
         extra 有 LOCATION（原理圖 頁區.欄）、DESCRIPTION（＝線號）、表頭、LOCATION 那一頁的 PDF 頁碼。
配置圖不印端子號（側視圖畫的端子塊數也和表不符：TBBAK 畫 47 塊、表 50 號），端子層級的框只來自端子表。
"""
import re

try:
    import fitz
except ImportError:          # 只有建索引才用到；沒裝 PyMuPDF 時 import 本套件不出錯
    fitz = None

DOC_KEY = 'epgg'
_STRIP_RE = re.compile(r'^TB[A-Z0-9]+(?:\(A\))?$')
_TERM_RE = re.compile(r'^\s*(?:(MAIN|AUX)-)?-?(TB[A-Z0-9]+(?:\(A\))?)\s*-?\s*(\d+)\s*$')


def _norm_strip(s):
    """'AUX-TBCT(A)' → 'TBCT(A)'、'MAIN-TBBAK' → 'TBBAK'；AUX 前綴＝(A)。"""
    s = (s or '').upper().replace(' ', '')
    m = re.match(r'^(?:(MAIN|AUX)-)?-?(TB[A-Z0-9]+(?:\(A\))?)$', s)
    if not m:
        return None
    strip = m.group(2)
    if m.group(1) == 'AUX' and not strip.endswith('(A)'):
        strip += '(A)'
    return strip


def _box(vrect, page):
    """顯示座標的框 → 未轉 PDF 座標，四捨五入到 0.01。"""
    r = (fitz.Rect(vrect) * ~page.rotation_matrix).normalize()
    return [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]


def _words(page):
    M = page.rotation_matrix
    return [(fitz.Rect(w[:4]) * M, w[4]) for w in page.get_text('words')]


def _title(words, page):
    """標題欄文字與圖號（標題欄＝未轉座標 x > 730、y < 420）。"""
    inv = ~page.rotation_matrix
    t, sheet = [], ''
    for r, s in words:
        u = r * inv
        if u.x0 > 735 and u.y1 < 400 and u.y0 > 150:
            t.append(s)
        if u.x0 > 758 and u.x1 < 776 and u.y1 < 58 and re.match(r'^\d\d[A-Z]{0,2}$', s):
            sheet = s
    return ' '.join(t), sheet


def _table_rows(page, words, drw):
    """這一頁每一張端子表的每一列 → (表頭, (端子號框, 端子號), (端子格, LOCATION 格, DESCRIPTION 格), inside)；inside(格)＝中心在格內的字。"""
    M = page.rotation_matrix
    cells = []
    for d in drw:
        for it in d['items']:
            if it[0] == 're':
                r = (it[1] * M).normalize()
                if 12 < r.height < 20 and 30 < r.width < 70:
                    cells.append(r)

    def inside(c):
        return [(r, s) for r, s in words if c.contains(fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))]
    # 同一列相鄰的三格串成（端子、LOCATION、DESCRIPTION）
    cells.sort(key=lambda c: (round(c.y0, 1), c.x0))
    rows = []
    for c in cells:
        nxt = [d for d in cells if abs(d.y0 - c.y0) < .3 and abs(d.x0 - c.x1) < .5]
        if not nxt:
            continue
        nxt2 = [e for e in cells if abs(e.y0 - c.y0) < .3 and abs(e.x0 - nxt[0].x1) < .5]
        prev = [d for d in cells if abs(d.y0 - c.y0) < .3 and abs(d.x1 - c.x0) < .5]
        if nxt2 and not prev:
            rows.append((c, nxt[0], nxt2[0]))
    # 每一欄由上往下走；遇到 TERMINAL 表頭列就換一張表
    cols = {}
    for t in rows:
        cols.setdefault(round(t[0].x0), []).append(t)
    for col in cols.values():
        col.sort(key=lambda t: t[0].y0)
        header = None
        for t in col:
            txt = [s for _, s in inside(t[0])]
            if 'TERMINAL' in txt:
                span = (t[0].x0 - 5, t[2].x1)
                cand = [(r, s) for r, s in words if _STRIP_RE.match(s)
                        and span[0] <= (r.x0 + r.x1) / 2 <= span[1]
                        and t[0].y0 - 22 <= r.y1 <= t[0].y0 + 1]
                header = max(cand, key=lambda w: w[0].y1)[1] if cand else None
                continue
            nums = [(r, s) for r, s in inside(t[0]) if s.isdigit()]
            if header and nums:
                yield header, nums[0], t, inside


def _leader(page, label, drw):
    """配置圖標籤拉出去的引線 → (起點, 箭頭尖) 或 None。"""
    M = page.rotation_matrix
    best = None
    for d in drw:
        for it in d['items']:
            if it[0] != 'l':
                continue
            for u, v in ((it[1] * M, it[2] * M), (it[2] * M, it[1] * M)):
                gap = label.x0 - u.x if u.x < label.x0 else u.x - label.x1
                away = (v.x < u.x) if u.x < label.x0 else (v.x > u.x)
                if (0 <= gap < 25 and label.y0 - 6 < u.y < label.y1 + 6 and away
                        and abs(v.x - u.x) > 30 and abs(v.y - u.y) > 2):
                    if best is None or gap < best[0]:
                        best = (gap, u, v)
    return best and (best[1], best[2])


def _rail_segment(page, tip, drw):
    """側視圖：箭頭尖所在、上下兩個端座之間的那一段軌道。
    端子塊是細長方形（12D 約 13.9×3、12DA 約 12.4×2.6），端座是同樣的方形寬約 1.16 倍（塊數與端子表不符，只取範圍）。"""
    M = page.rotation_matrix
    rs = [(it[1] * M).normalize() for d in drw for it in d['items'] if it[0] == 're']
    rs = [r for r in rs if 2 < r.height < 4.5 and 10 < r.width < 20]
    near = [b for b in rs if max(b.x0 - tip.x, tip.x - b.x1, 0) < 10 and abs((b.y0 + b.y1) / 2 - tip.y) < 4]
    if not near:
        return None
    cx = (near[0].x0 + near[0].x1) / 2
    col = [b for b in rs if abs((b.x0 + b.x1) / 2 - cx) < 1.5]
    widths = [round(b.width, 1) for b in col]
    w = max(set(widths), key=widths.count)
    col = [b for b in col if 1.1 * w < b.width < 1.25 * w]
    above = [b for b in col if b.y1 <= tip.y + 1.5]
    below = [b for b in col if b.y0 >= tip.y - 1.5]
    if not above or not below:
        return None
    top = max(above, key=lambda b: b.y1)
    bot = min(below, key=lambda b: b.y0)
    return fitz.Rect(top.x0, top.y0, top.x1, bot.y1)


def _subpanel_strip(page, label, drw):
    """子盤視圖：標籤正下方那一排端子塊（分隔筆畫間距約 2.9 pt）。"""
    M = page.rotation_matrix
    band = fitz.Rect(label.x0 - 80, label.y1, label.x1 + 80, label.y1 + 22)
    xs = []
    for d in drw:
        r = d['rect'] * M
        if band.contains(r) and r.height > 10 and r.width < 4:
            xs.append((r.x0, r.x1, r.y0, r.y1))
    if not xs:
        return None
    xs.sort()
    groups, cur = [], [xs[0]]
    for x in xs[1:]:
        if x[0] - max(c[1] for c in cur) > 3.1:
            groups.append(cur)
            cur = []
        cur.append(x)
    groups.append(cur)
    cx = (label.x0 + label.x1) / 2
    for g in groups:
        x0, x1 = min(c[0] for c in g), max(c[1] for c in g)
        if x0 - 3 <= cx <= x1 + 3:
            return fitz.Rect(x0, min(c[2] for c in g), x1, max(c[3] for c in g))
    return None


def build_index(pdf_paths):
    """pdf_paths：{機組或 '*': 路徑}；幾個機組給同一份 140T1264 也可以（只開一次）。→ {'strips','terms','doc','analog'}。"""
    strips, terms = {}, {}
    for path in sorted(set(pdf_paths.values())):
        doc = fitz.open(path)
        pages = []
        sheet_page = {}
        for page in doc:
            w = _words(page)
            title, sheet = _title(w, page)
            if sheet:
                sheet_page.setdefault(sheet, page.number + 1)
            pages.append((page, w, title, sheet))
        for page, words, title, sheet in pages:
            pno = page.number + 1
            if 'TERMINAL BLOCK ARRNAGEMENT' in title or 'TERMINAL BLOCK ARRANGEMENT' in title:
                for header, (nr, ns), t, inside in _table_rows(page, words, page.get_drawings()):
                    loc = ' '.join(s for _, s in inside(t[1]))
                    wire = ' '.join(s for _, s in inside(t[2]))
                    m = re.match(r'^/(\d\d[A-Z]{0,2})\.\d$', loc)
                    terms.setdefault(('*', header, str(int(ns))), []).append({
                        'page': pno, 'box': _box(fitz.Rect(t[0]) | t[2], page),
                        'text': f'{header} {ns} {loc} {wire}'.strip(), 'kind': 'row',
                        'extra': {'table': header, 'num': ns, 'sheet': sheet, 'location': loc, 'wire': wire,
                                  'blank': not (loc or wire), 'num_box': _box(nr, page),
                                  'loc_page': sheet_page.get(m.group(1)) if m else None}})
            elif 'GPP GENERAL ARRANGEMENT' in title:
                bays = [(r, s) for r, s in words if re.match(r'^BAY-\d$', s)]
                drw = page.get_drawings()
                for r, s in words:
                    if not _STRIP_RE.match(s) or not bays:
                        continue
                    cx = (r.x0 + r.x1) / 2
                    bay = min(bays, key=lambda b: abs((b[0].x0 + b[0].x1) / 2 - cx))[1]
                    strip = s + '(A)' if bay == 'BAY-3' and not s.endswith('(A)') else s
                    extra = {'bay': bay + (' (A)' if bay == 'BAY-3' else ''), 'sheet': sheet, 'label': s}
                    lead = _leader(page, r, drw)
                    if lead:
                        u, v = lead
                        extra['tip_box'] = _box(fitz.Rect(v.x - 6, v.y - 6, v.x + 6, v.y + 6), page)
                        seg = _rail_segment(page, v, drw)
                    else:
                        seg = _subpanel_strip(page, r, drw)
                    if seg:
                        extra['seg_box'] = _box(seg, page)
                    strips.setdefault(('*', strip), []).append({
                        'page': pno, 'box': _box(r, page), 'text': s, 'kind': 'strip', 'extra': extra})
        doc.close()
    doc_map = dict(pdf_paths)
    if len(set(pdf_paths.values())) == 1:          # 同一份圖給每台燃機：鍵用 '*'
        doc_map.setdefault('*', next(iter(pdf_paths.values())))
    return {'strips': strips, 'terms': terms, 'doc': doc_map, 'analog': {}}


def key_of(entry, cond):
    """這條芯 GPP 那一端 → ('*', 端子排, 端子號) 或 None。"""
    unit = entry.get('unit', '')
    if not re.match(r'^G\d\d$', unit):       # 140T1264 只畫燃機的 GPP
        return None
    if entry.get('end') == 'jb':
        raw = cond.get('jb_term', '')
        m = _TERM_RE.match(raw.upper())
        if m:
            strip = _norm_strip((m.group(1) + '-' if m.group(1) else '') + m.group(2))
            num = m.group(3)
        elif raw.strip().isdigit():
            strip, num = _norm_strip(entry.get('jb_tb', '')), raw.strip()
        else:
            return None
    else:
        strip = _norm_strip(cond.get('panel_board') or cond.get('panel_tb') or entry.get('panel_tb'))
        num = (cond.get('panel_num') or '').strip()
        if not num.isdigit():
            return None
    if not strip:
        return None
    return ('*', strip, str(int(num)))


# ---------------------------------------------------------------- 統一介面
def build(paths):
    """paths：{'epgg': 路徑}。"""
    return build_index({'*': paths[DOC_KEY]})


def _hit(page, box, kind, label, primary, extra):
    return {'doc_key': DOC_KEY, 'page': page, 'box': list(box), 'kind': kind, 'label': label, 'primary': primary, 'extra': extra}


def locate(ix, entry, cond):
    """→ [hit]：配置圖上端子排的範圍（主框；找不到範圍才用標籤）＋同頁的標籤（副框）、端子表那一列（主框）。"""
    k = key_of(entry, cond)
    if not k:
        return []
    out = []
    for h in ix['strips'].get(k[:2], []):
        x = h['extra']
        ex = {'bay': x['bay'], 'sheet': x['sheet'], 'generic': 1}
        if x.get('tip_box'):
            ex['tip_box'] = x['tip_box']
        if x.get('seg_box'):
            out.append(_hit(h['page'], x['seg_box'], 'strip', x['label'], True, dict(ex, part='extent')))
            out.append(_hit(h['page'], h['box'], 'strip', x['label'], False, dict(ex, part='label')))
        else:
            out.append(_hit(h['page'], h['box'], 'strip', x['label'], True, dict(ex, part='label')))
    for h in ix['terms'].get(k, []):
        x = h['extra']
        out.append(_hit(h['page'], h['box'], 'row', '%s %s' % (x['table'], x['num']), True,
                        {'table': x['table'], 'sheet': x['sheet'], 'location': x['location'], 'wire': x['wire'].strip('()'),
                         'blank': 1 if x['blank'] else 0, 'num_box': x['num_box'], 'loc_page': x['loc_page'], 'generic': 1}))
    return out


def missing(ix, entry, cond):
    """找不到時的原因（卡片註記用）；找得到回 None。"""
    k = key_of(entry, cond)
    if not k:
        if not re.match(r'^G\d\d$', entry.get('unit', '')):
            return '140T1264 只畫燃機發電機的 GPP'
        raw = cond.get('jb_term', '') if entry.get('end') == 'jb' else '%s %s' % (cond.get('panel_board') or entry.get('panel_tb') or '', cond.get('panel_num', ''))
        return '端子寫法解析不出（「%s」）' % raw.strip()
    if ix['terms'].get(k):
        return None
    if any(s == k[1] for (_, s, _) in ix['terms']):
        return 'GPP 端子表 %s 沒有第 %s 號（接線圖與 140T1264 不符）' % (k[1], k[2])
    if ix['strips'].get(k[:2]):
        return 'GPP 端子排 %s 沒有端子表（只框配置圖上的端子排）' % k[1]
    return '140T1264 沒有端子排 %s' % k[1]
