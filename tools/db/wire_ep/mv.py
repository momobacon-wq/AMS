# -*- coding: utf-8 -*-
r"""tools/db/wire_ep/mv.py — LCI（SFC）中壓開關盤（MBJ10UC200）與 52ET LCI／激磁斷路器（MKC10QA101）的隔間定位（v16，給 wire_ge.py 用）。

只到隔間（-A01／-A02／-A03），不到端子（Casagrande 配置圖）：
  G11MBJ10UC200 → HT0-1-EGJ01-D0037（GTG#11/21/31：-A01 -A02 -A03）
  G12MBJ10UC200 → HT0-1-EGJ01-D0052（GTG#12/22/32：只有 -A01 -A02，沒有 -A03）
  G1xMKC10QA101 → HT0-1-EGJ01-D0035（每台 GTG 共用：'(*) 1 FOR GTG#11, 2 FOR GTG#12 …'）
圖由箱子（JB 或盤那一端）的 KKS 決定，不看路徑的機組。
鍵：(機組或 '*', 'MBJ10UC200/A01', '')；沒寫隔間的用整面盤 (機組, 'MBJ10UC200', '')；52ET 是 ('*', 'MKC10QA101/A03', '')。
各頁 /Rotate 0，框＝未轉 PDF 座標。
端子層級日後可做：D0051 p.43（sheet 710 'UNIT -A03 - TERMINAL BOARDS'）把 -X1 1..65 畫成格子，D0053／D0054 是 G11／G12 的端子圖，
  但號碼是向量外框字（每頁只有標題約 27 個字），要 OCR 或數格子再看圖核對；這一版沒做。
"""
import re

try:
    import fitz
except ImportError:          # 只有建索引才用到
    fitz = None

LBL = re.compile(r'^-A0\d$')
KKS = re.compile(r'(G1[12])(MBJ10UC200|MKC10QA101)')
UNIT_DOC = {'G11': 'epv1', 'G12': 'epv2', '*': 'epbr'}


def _r(b):
    return [round(float(v), 1) for v in b]


def _vlines(page, minlen=150):
    V = []
    for d in page.get_drawings():
        for it in d['items']:
            segs = []
            if it[0] == 'l':
                segs = [(it[1], it[2])]
            elif it[0] == 'qu':
                segs = [(it[1].ul, it[1].ll), (it[1].ur, it[1].lr)]
            elif it[0] == 're':
                segs = [(it[1].tl, it[1].bl), (it[1].tr, it[1].br)]
            for p, q in segs:
                if abs(p.x - q.x) < .3 and abs(p.y - q.y) >= minlen:
                    V.append((p.x, min(p.y, q.y), max(p.y, q.y)))
    return V


def _quads(page, minside=60):
    out = []
    for d in page.get_drawings():
        for it in d['items']:
            r = it[1].rect if it[0] == 'qu' else (it[1] if it[0] == 're' else None)
            if r is not None and r.width >= minside and r.height >= minside:
                out.append(fitz.Rect(r))
    return out


def _page_kind(text, labels):
    t = re.sub(r'\s+', ' ', text.upper())
    if not labels:
        return None
    if 'LOW VOLTAGE BOX' in t:
        return 'lvbox'
    if 'INTERNAL FRONT VIEW' in t:
        return 'internal'
    if 'FRONT VIEW' in t:
        return 'front'
    return None


def _lvbox(page, labels):
    """低壓箱頁（p.6）：右上角碰到標籤的那個門框。"""
    quads = _quads(page)
    out = {}
    for w in labels:
        c = [q for q in quads if 0 <= w[0] - q.x1 < 10 and abs(q.y0 - w[1]) < 6]
        out[w[4]] = max(c, key=lambda q: q.get_area()) if c else None
    return out


def _columns(page, labels):
    """正視圖／內部正視圖：標籤中心左右兩條長豎線之間那一欄。"""
    V = _vlines(page)
    cxs = [(w[0] + w[2]) / 2 for w in labels]
    span = [v for v in V if min(cxs) - 150 <= v[0] <= max(cxs) + 150]
    if not span:
        return {w[4]: None for w in labels}
    top = min(v[1] for v in span)
    out = {}
    for w, cx in zip(labels, cxs):
        lf = [v for v in span if cx - 100 < v[0] < cx - 10]
        rt = [v for v in span if cx + 10 < v[0] < cx + 100]
        if not (lf and rt):
            out[w[4]] = None
            continue
        L = max(lf, key=lambda v: (v[0], v[2]))
        R = min(rt, key=lambda v: (v[0], -v[2]))
        out[w[4]] = fitz.Rect(L[0], top, R[0], max(L[2], R[2]))
    return out


def _table_cols(page, labels):
    """52ET 正視圖：標籤在視圖下方的表裡，取標籤正上方的那個門框。"""
    quads = _quads(page)
    out = {}
    for w in labels:
        cx = (w[0] + w[2]) / 2
        c = [q for q in quads if q.x0 < cx < q.x1 and q.y1 < w[1] and w[1] - q.y1 < 150 and q.width < 200]
        out[w[4]] = max(c, key=lambda q: q.get_area()) if c else None
    return out


def _index_doc(path, unit, equip, strips):
    doc = fitz.open(path)
    for pno in range(doc.page_count):
        pg = doc[pno]
        words = pg.get_text('words')
        labels = [w for w in words if LBL.match(w[4])]
        kind = _page_kind(pg.get_text(), labels)
        if not kind:
            continue
        if equip == 'MKC10QA101':
            if kind != 'front':
                continue
            rects = _table_cols(pg, labels)
        elif kind == 'lvbox':
            rects = _lvbox(pg, labels)
        else:
            rects = _columns(pg, labels)
        whole = None
        for w in labels:
            comp = w[4].lstrip('-')
            r = rects.get(w[4])
            lab = fitz.Rect(w[:4])
            near = r is not None and (lab + (-20, -20, 20, 20)).intersects(r)
            box = (lab | r) if near else (r if r is not None else lab)   # 離得遠的標籤（表裡、欄頭）只記在 extra
            whole = box if whole is None else whole | box
            strips.setdefault((unit, f'{equip}/{comp}'), []).append({
                'page': pno + 1, 'box': _r(box), 'text': w[4], 'kind': 'strip',
                'extra': {'view': kind, 'part': 'compartment' if r else 'label',
                          'label': _r(w[:4]), 'rect': _r(r) if r else None}})
        if whole is not None and kind in ('front', 'lvbox'):
            strips.setdefault((unit, equip), []).append({
                'page': pno + 1, 'box': _r(whole), 'text': equip, 'kind': 'strip',
                'extra': {'view': kind, 'part': 'panel'}})
    doc.close()


def build_index(pdf_paths):
    """pdf_paths：{'G11': D0037, 'G12': D0052, '*': D0035}（缺哪份就少哪個）。"""
    strips = {}
    for unit, path in pdf_paths.items():
        equip = 'MKC10QA101' if unit == '*' else 'MBJ10UC200'
        _index_doc(path, unit, equip, strips)
    return {'strips': strips, 'terms': {}, 'doc': dict(pdf_paths), 'analog': {}}


def _parse(entry, cond):
    end = entry.get('end', 'jb')
    w = entry.get('wire') or {}
    if end == 'panel':
        name = w.get('panel') or entry.get('panel') or ''
        tbs = [cond.get('panel_board') or cond.get('board') or '', w.get('panel_tb') or entry.get('panel_tb') or '']
    else:
        name = w.get('jb') or entry.get('jb') or ''
        tbs = [cond.get('jb_term') or cond.get('jb') or '', w.get('jb_tb') or entry.get('jb_tb') or '']
    m = KKS.search(name.upper().replace(' ', ''))
    if not m:
        return None, '箱名沒有 MBJ10UC200／MKC10QA101 的 KKS（「%s」）' % name
    unit = '*' if m.group(2) == 'MKC10QA101' else m.group(1)
    for t in tbs:
        c = re.search(r'A0(\d)', t.upper())
        if c:
            return (unit, f'{m.group(2)}/A0{c.group(1)}', ''), '隔間取自「%s」' % t
    return (unit, m.group(2), ''), '接線圖沒寫隔間（%s）：框整面盤' % '、'.join(t for t in tbs if t)


def key_of(entry, cond):
    return _parse(entry, cond)[0]


# ---------------------------------------------------------------- 統一介面
def build(paths):
    """paths：{'epv1': D0037, 'epv2': D0052, 'epbr': D0035}。"""
    return build_index({u: paths[k] for u, k in UNIT_DOC.items() if paths.get(k)})


def locate(ix, entry, cond):
    """→ [hit]（kind 'cmp'）：每一張視圖上這個隔間的框（都是主框）；沒寫隔間的框整面盤（extra.whole＝1）。"""
    k, note = _parse(entry, cond)
    if not k:
        return []
    whole = '/' not in k[1]
    out = []
    for h in ix['strips'].get(k[:2], []):
        x = h['extra']
        ex = {'view': x['view'], 'part': x['part']}
        if x.get('label'):
            ex['label_box'] = x['label']
        if x.get('rect'):
            ex['rect'] = x['rect']
        if whole:
            ex['whole'] = 1
            ex['note'] = note
        if k[0] == '*':
            ex['generic'] = 1
        out.append({'doc_key': UNIT_DOC[k[0]], 'page': h['page'], 'box': list(h['box']), 'kind': 'cmp', 'label': h['text'],
                    'primary': True, 'extra': ex})
    return out


def missing(ix, entry, cond):
    """找不到隔間時的原因（卡片註記用）；找得到回 None（框整面盤時也回 None，原因在 extra.note）。"""
    k, note = _parse(entry, cond)
    if not k:
        return note
    if ix['strips'].get(k[:2]):
        return None
    if k[0] not in ix['doc']:
        return '%s 的配置圖不在文件庫' % ('52ET' if k[0] == '*' else k[0])
    return '配置圖上沒有隔間 -%s' % k[1].split('/')[-1] if '/' in k[1] else '配置圖上找不到整面盤'
