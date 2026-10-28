# -*- coding: utf-8 -*-
r"""tools/db/wire_ep/gpp_st.py — 汽機發電機保護盤（GPP MAIN S10MKY40UC001／GPP AUX S10MKY40UC002）端子排定位（v16，給 wire_ge.py 用）。

圖：STG GPP Equipment Arrangement（HT0-1-EGK01-D0018＝GE 140T1267／GPDP000460；GE GPDP 範本）。只對 S10（不是類比）。
  配置圖頁：MAIN／AUX SUBPANEL VIEW、LEFT／RIGHT SIDE VIEW 上 'TBBAK (50)' 這種標籤（端子排名＋塊數）。
  端子表頁：'TERMINAL BLOCK ARRNAGEMENT'（原圖拼錯）的表 TERMINAL NO. | LOCATION | DESCRIPTION；
            LOCATION＝原理圖 頁區.欄（/10B.3）、DESCRIPTION＝線號（(803B)）。
幾何一律在轉正後的顯示座標算，存的框一律是未轉的 PDF 座標（＝page.get_text('words')）。AUX 段的端子排帶 '(A)'。
已知圖面怪處（定位不受影響）：p.94 TBBAK／TBBUSP 表印 36、38、37、39（38 在 37 上面）→ 只認印的號碼、不認列序；
  TBVT 表 28 列（1–16、19–30，沒有 17、18），標籤卻寫 TBVT (30)；印的頁碼＝PDF 頁碼 − 1。
"""
import re
import statistics

try:
    import fitz
except ImportError:          # 只有建索引才用到
    fitz = None

DOC_KEY = 'epgs'
STRIP_RE = re.compile(r'^TB[A-Z0-9]+(?:\(A\))?$')
COUNT_RE = re.compile(r'^\(\d+\)$')
TERM_RE = re.compile(r"^(?:(MAIN|AUX)\s*-\s*)?(?:-?\s*(TB[A-Z0-9]+(?:\(A\))?)[\s\-']*)?0*(\d+)$")
GPP_RE = re.compile(r'MKY40UC00[12]|\bGPP\b', re.I)
UNITS = ('S10',)                       # 這份圖畫的機組（不是類比）


def _norm_strip(s):
    s = (s or '').upper().replace(' ', '').lstrip('-')
    return re.sub(r'^(MAIN|AUX)-', '', s)


def _norm_term(t):
    t = (t or '').strip()
    return (t.lstrip('0') or '0') if t.isdigit() else None


def _g(d, *keys):
    """keys 裡第一個非空的值，先找 d、再找 d['wire']（新基準的形狀）。"""
    for k in keys:
        for src in (d, d.get('wire') or {}):
            v = src.get(k)
            if v not in (None, ''):
                return v
    return ''


def key_of(entry, cond):
    """這條芯 GPP 那一端 → (機組, 端子排, 端子號) 或 None。"""
    unit = entry.get('unit')
    if unit not in UNITS:
        return None
    end = entry.get('end')
    if end == 'jb':
        who, field = _g(entry, 'jb'), _g(entry, 'jb_tb')
        raw = cond.get('jb_term', cond.get('jb', ''))
    elif end == 'panel':
        who = _g(entry, 'panel')
        field = cond.get('panel_board') or cond.get('board') or _g(entry, 'panel_tb')
        raw = cond.get('panel_num', cond.get('num', ''))
    else:
        return None
    if not GPP_RE.search(who or ''):
        return None
    m = TERM_RE.match((raw or '').strip().upper())
    if not m:
        return None
    strip = m.group(2) or ('' if '/' in field else field)   # 標頭寫 '-TBTCD/TBBUSP/TBBAK' 時要用端子格自己的名稱
    strip = _norm_strip(strip)
    if not STRIP_RE.match(strip):
        return None
    return (unit, strip, _norm_term(m.group(3)))


# ---------------------------------------------------------------- 建索引
def _vwords(page):
    """字的顯示座標框（套完 /Rotate）與未轉座標框。"""
    m = page.rotation_matrix
    out = []
    for w in page.get_text('words'):
        r = fitz.Rect(w[:4])
        v = r * m
        v.normalize()
        out.append({'t': w[4], 'v': v, 'u': r})
    return out


def _ubox(rects):
    r = fitz.Rect(rects[0])
    for x in rects[1:]:
        r |= x
    return [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]


def _page_meta(ws):
    """圖框印的 'Page N of M' 與標題欄 SHEET 欄的值。"""
    meta = {}
    for i, w in enumerate(ws):
        if w['t'] == 'Page' and i + 1 < len(ws) and ws[i + 1]['t'].isdigit():
            meta.setdefault('printed_page', ws[i + 1]['t'])
    sh = [w for w in ws if w['t'] == 'SHEET' and w['v'].y0 > 600]
    if sh:
        s = sh[-1]['v']
        sx = (s.x0 + s.x1) / 2
        below = [w for w in ws if s.y1 - 1 < w['v'].y0 < s.y1 + 8 and abs((w['v'].x0 + w['v'].x1) / 2 - sx) < 25]
        if below:                                     # 'SHEET' 正下方最近的那個字（不是旁邊的 SIZE 字母）
            meta['sheet'] = min(below, key=lambda w: abs((w['v'].x0 + w['v'].x1) / 2 - sx))['t']
    return meta


def _tables(page, ws, inv, meta, pno, strips, terms, unit):
    heads = [w for w in ws if w['t'] == 'TERMINAL']
    tables = []
    for h in heads:
        hv = h['v']
        loc = [w for w in ws if w['t'] == 'LOCATION' and abs(w['v'].y0 - hv.y0 - 4) < 6 and 0 < w['v'].x0 - hv.x1 < 40]
        des = [w for w in ws if w['t'] == 'DESCRIPTION' and abs(w['v'].y0 - hv.y0 - 4) < 6 and 0 < w['v'].x0 - hv.x1 < 110]
        ttl = [w for w in ws if STRIP_RE.match(w['t']) and 0 < hv.y0 - w['v'].y1 < 20
               and hv.x0 - 10 < (w['v'].x0 + w['v'].x1) / 2 < hv.x1 + 40]
        if loc and des and ttl:
            tables.append({'title': ttl[0], 'head': h, 'loc': loc[0]['v'], 'des': des[0]['v']})
    if not tables:
        return 0
    cells = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 're':
                c = it[1] * page.rotation_matrix
                c.normalize()
                if 8 < c.height < 30:
                    cells.append(c)
    for t in tables:
        hv, lv, dv = t['head']['v'], t['loc'], t['des']
        x0, x1 = hv.x0 - 12, dv.x1 + 14
        name = _norm_strip(t['title']['t'])
        # 同一欄下一張表的表頭＝這張表的下界
        below = [o['head']['v'].y0 for o in tables if o is not t and abs(o['head']['v'].x0 - hv.x0) < 30 and o['head']['v'].y0 > hv.y0]
        ylim = min(below) - 15 if below else 720
        col = [w for w in ws if hv.y1 + 4 < w['v'].y0 < ylim]
        nums = [w for w in col if w['t'].isdigit() and hv.x0 - 6 < (w['v'].x0 + w['v'].x1) / 2 < lv.x0 - 2]
        if not nums:
            continue
        nums.sort(key=lambda w: w['v'].y0)
        pitch = statistics.median([b['v'].y0 - a['v'].y0 for a, b in zip(nums, nums[1:])] or [16.2])
        table_rects = [t['title']['u'], t['head']['u']]          # 表名＋表頭＋每一列，逐列擴大
        strips.setdefault((unit, name), []).append({
            'page': pno, 'box': None, 'text': t['title']['t'], 'kind': 'strip',
            'extra': {'src': 'table', 'rows': len(nums), **meta}})
        for n in nums:
            nv = n['v']
            cy = nv.y0 + 4 + 4.6                       # 列的中線（LOCATION／DESCRIPTION 的字低 4 pt）
            row = [c for c in cells if c.y0 - 1 < cy < c.y1 + 1 and x0 < c.x0 + 1 and c.x1 - 1 < x1]
            if row:
                rv = fitz.Rect(min(c.x0 for c in row), min(c.y0 for c in row), max(c.x1 for c in row), max(c.y1 for c in row))
            else:
                rv = fitz.Rect(hv.x0 - 10, nv.y0 + 1, dv.x1 + 4, nv.y0 + 1 + pitch)
            l = [w for w in col if lv.x0 - 12 < (w['v'].x0 + w['v'].x1) / 2 < dv.x0 - 3 and rv.y0 - 1 < (w['v'].y0 + w['v'].y1) / 2 < rv.y1 + 1]
            d_ = [w for w in col if dv.x0 - 3 < (w['v'].x0 + w['v'].x1) / 2 < x1 and rv.y0 - 1 < (w['v'].y0 + w['v'].y1) / 2 < rv.y1 + 1]
            locs = ' '.join(w['t'] for w in sorted(l, key=lambda w: w['v'].x0))
            desc = ' '.join(w['t'] for w in sorted(d_, key=lambda w: w['v'].x0))
            ub = rv * inv
            ub.normalize()
            table_rects.append(ub)
            terms.setdefault((unit, name, _norm_term(n['t'])), []).append({
                'page': pno, 'box': _ubox([ub]), 'text': f"{n['t']} {locs} {desc}".strip(), 'kind': 'row',
                'extra': {'num': n['t'], 'location': locs, 'wire': desc.strip('()'), 'spare': not (locs or desc),
                          'num_box': _ubox([n['u']]), 'row_from': 'cell' if row else 'pitch', **meta}})
        strips[(unit, name)][-1]['box'] = _ubox(table_rects)
    return len(tables)


def _segments(page):
    """顯示座標的線段：(a, b, 線寬)；字形大小的筆畫不收。"""
    m = page.rotation_matrix
    out = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1] * m, it[2] * m
                if abs(a - b) > 4:
                    out.append((a, b, round(d.get('width') or 0, 2)))
    return out


def _leader_tip(segs, label_v):
    """配置圖標籤旁起頭的引線（水平短線或直接斜線）一路接到軌道上的末端 → 顯示座標的點或 None。"""
    best, cur = None, None
    for s in segs:
        a, b, _ = s
        for near, far in ((a, b), (b, a)):
            if not (label_v.y0 - 2 <= near.y <= label_v.y1 + 2):
                continue
            gap = label_v.x0 - near.x if far.x < near.x else near.x - label_v.x1
            if -1 < gap < 30 and abs(far.x - near.x) > 3 and (best is None or gap < best[0]):
                best, cur = (gap, s), far
    if not best:
        return None
    used, width = {id(best[1])}, best[1][2]
    for _ in range(3):                                # 短線 → 斜線（→ 箭頭）；只接同一枝筆
        nxt = [(s, s[1] if abs(s[0] - cur) < 1.5 else s[0]) for s in segs
               if id(s) not in used and s[2] == width and (abs(s[0] - cur) < 1.5 or abs(s[1] - cur) < 1.5)]
        if not nxt:
            break
        s, cur = max(nxt, key=lambda t: abs(t[0][0] - t[0][1]))
        used.add(id(s))
    return cur


def _layout(page, ws, inv, pno, meta, strips, unit, a_names):
    labels = []
    for i, w in enumerate(ws):
        if STRIP_RE.match(w['t']):
            cnt = [c for c in ws if COUNT_RE.match(c['t']) and abs(c['v'].y0 - w['v'].y0) < 3 and 0 <= c['v'].x0 - w['v'].x1 < 8]
            if cnt:
                labels.append((w, cnt[0]))
    if not labels:
        return 0
    views = []                                        # (x 中心, 是否 AUX, 視圖名)
    for w in ws:
        if w['t'] != 'VIEW':
            continue
        line = [o for o in ws if abs(o['v'].y0 - w['v'].y0) < 3 and -130 < o['v'].x0 - w['v'].x0 < 1]
        under = [o for o in ws if o['t'] == '(A)' and 0 < o['v'].y0 - w['v'].y0 < 25 and min(o['v'].x0 for o in line) - 5 < o['v'].x0 < w['v'].x1]
        cap = ' '.join(o['t'] for o in sorted(line, key=lambda o: o['v'].x0))
        if 'SIDE' in cap or 'SUBPANEL' in cap:
            xc = (min(o['v'].x0 for o in line) + w['v'].x1) / 2
            views.append((xc, bool(under) or 'AUX' in cap, cap + (' (A)' if under else '')))
    segs = _segments(page)
    for w, c in labels:
        xc = (w['v'].x0 + c['v'].x1) / 2
        view = min(views, key=lambda v: abs(v[0] - xc)) if views else (0, False, '')
        name = _norm_strip(w['t'])
        if view[1] and not name.endswith('(A)') and name + '(A)' in a_names:
            name += '(A)'        # AUX 段的標籤印的是不帶 (A) 的名稱；端子表與原理圖寫 X(A)
        ex = {'view': view[2], 'aux': view[1], 'count': int(c['t'].strip('()')), **meta}
        hits = strips.setdefault((unit, name), [])
        hits.append({'page': pno, 'box': _ubox([w['u'], c['u']]), 'text': f"{w['t']} {c['t']}", 'kind': 'strip',
                     'extra': {'src': 'layout', 'label': w['t'], **ex}})
        tip = _leader_tip(segs, w['v'] | c['v'])
        if tip is not None:
            tb = fitz.Rect(tip.x - 5, tip.y - 5, tip.x + 5, tip.y + 5) * inv
            tb.normalize()
            hits.append({'page': pno, 'box': _ubox([tb]), 'text': f"{w['t']} leader tip", 'kind': 'strip',
                         'extra': {'src': 'leader_tip', 'label': w['t'], **ex}})
    return len(labels)


def _link_schematic(pages, terms, unit):
    """LOCATION '/10B.3'＝原理圖 10B 頁第 3 區：extra.loc_page＝標題欄 SHEET 是 10B 的那一頁（原理圖上線號的框不收）。"""
    smap = {}
    for pno, _, ws in pages:
        sh = _page_meta(ws).get('sheet')
        if sh:
            smap.setdefault(sh, pno)
    for (u, strip, term), hits in terms.items():
        if u != unit:
            continue
        for h in hits:
            loc = h['extra'].get('location', '')
            pg = smap.get(loc.strip('/').split('.')[0]) if loc else None
            if pg:
                h['extra']['loc_page'] = pg


def build_index(pdf_paths):
    """pdf_paths：{機組: 路徑} → {'strips','terms','doc','analog'}。"""
    strips, terms, doc_map, analog = {}, {}, {}, {}
    for unit, path in pdf_paths.items():
        doc_map[unit] = path
        if unit not in UNITS:
            analog[unit] = '這份圖畫的是 %s；%s 的框是類比' % ('、'.join(UNITS), unit)
        doc = fitz.open(path)
        pages = [(i + 1, p, _vwords(p)) for i, p in enumerate(doc)]
        a_names = {w['t'] for _, _, ws in pages for w in ws if w['t'].endswith('(A)') and STRIP_RE.match(w['t'])}
        for pno, page, ws in pages:
            if not any(STRIP_RE.match(w['t']) for w in ws):
                continue
            meta = _page_meta(ws)
            inv = ~page.rotation_matrix
            if not _tables(page, ws, inv, meta, pno, strips, terms, unit):
                _layout(page, ws, inv, pno, meta, strips, unit, a_names)
        _link_schematic(pages, terms, unit)
        doc.close()
    order = {'layout': 0, 'leader_tip': 1, 'table': 2}  # 配置圖標籤、它的引線末端、端子表
    for v in strips.values():
        v.sort(key=lambda h: (order.get(h['extra'].get('src'), 3), h['page']))
    return {'strips': strips, 'terms': terms, 'doc': doc_map, 'analog': analog}


# ---------------------------------------------------------------- 統一介面
def build(paths):
    """paths：{'epgs': 路徑}。"""
    return build_index({'S10': paths[DOC_KEY]})


def _hit(page, box, kind, label, primary, extra):
    return {'doc_key': DOC_KEY, 'page': page, 'box': list(box), 'kind': kind, 'label': label, 'primary': primary, 'extra': extra}


def _inside(a, b, tol=1.0):
    return a[0] >= b[0] - tol and a[1] >= b[1] - tol and a[2] <= b[2] + tol and a[3] <= b[3] + tol


def locate(ix, entry, cond):
    """→ [hit]：配置圖標籤（主框）＋引線末端（副框）、端子表那一列（主框）＋含這一列的那張表的範圍（副框）。
    一個端子排拆在兩張表（同頁兩欄）時只留含這一列的那一張。"""
    k = key_of(entry, cond)
    if not k:
        return []
    rows = ix['terms'].get(k, [])
    out = []
    for h in rows:
        x = h['extra']
        out.append(_hit(h['page'], h['box'], 'row', '%s %s' % (k[1], x['num']), True,
                        {'sheet': x.get('sheet'), 'printed_page': x.get('printed_page'), 'location': x['location'],
                         'wire': x['wire'], 'blank': 1 if x['spare'] else 0, 'num_box': x['num_box'],
                         'row_from': x['row_from'], 'loc_page': x.get('loc_page')}))
    for h in ix['strips'].get(k[:2], []):
        x = h['extra']
        ex = {'sheet': x.get('sheet'), 'printed_page': x.get('printed_page')}
        if x['src'] == 'table':
            if rows and not any(_inside(r['box'], h['box']) for r in rows):
                continue
            out.append(_hit(h['page'], h['box'], 'strip', h['text'], not any(r['page'] == h['page'] for r in rows),
                            dict(ex, part='table', rows=x['rows'])))
        elif x['src'] == 'layout':
            out.append(_hit(h['page'], h['box'], 'strip', h['text'], True,
                            dict(ex, part='label', view=x['view'], count=x['count'])))
        else:
            out.append(_hit(h['page'], h['box'], 'strip', x['label'], False, dict(ex, part='tip', view=x['view'])))
    return out


def missing(ix, entry, cond):
    """找不到端子那一列時的原因（卡片註記用）；找得到回 None。"""
    k = key_of(entry, cond)
    if not k:
        if entry.get('unit') not in UNITS:
            return 'HT0-1-EGK01-D0018 只畫汽機發電機的 GPP'
        if entry.get('end') == 'panel' and not (cond.get('panel_board') or entry.get('panel_tb')):
            return '接線圖這一端沒有寫端子排名稱'
        raw = cond.get('jb_term', '') if entry.get('end') == 'jb' else cond.get('panel_num', '')
        return '端子寫法解析不出（「%s」）' % (raw or '').strip()
    if ix['terms'].get(k):
        return None
    if ix['strips'].get(k[:2]):
        return 'GPP 端子表 %s 沒有第 %s 號（接線圖與 D0018 不符）' % (k[1], k[2])
    return 'D0018 沒有端子排 %s' % k[1]
