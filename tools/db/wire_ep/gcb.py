# -*- coding: utf-8 -*-
r"""tools/db/wire_ep/gcb.py — 燃機發電機斷路器（GCB，G1xMSC20XD512）低壓箱端子定位（v16，給 wire_ge.py 用）。

圖：GE Grid FKG1X 接線圖 VS332679EDD01D rev09（HT0-1-EGJ01-D0066）。每台燃機的 GCB 共用一份（圖上沒有 KKS／機組字樣），鍵的機組一律 '*'。
各頁 /Rotate 0；印的頁碼＝PDF 頁碼 − 1。標題欄的圖號分類：LVC_nn 低壓箱配置、TER_-XTnn 端子表、DRW_nn 原理圖。
  term ：LVC_nn 配置圖上這一號端子塊（端子排標籤 → 下一個標籤之間、印著這個號碼的那一塊）——卡片畫這個框
  row  ：TER_-XTnn 端子表裡這一號那一欄（幾乎整頁高；extra 有 Sheet 欄的原理圖參照 DRW_nn.<區>、上下兩側接到哪、電纜、端子型式）
  strip：配置圖的端子排標籤（含 LVC_01 整箱總圖上的小字標籤）與端子表的表名
同一號端子有跨接的好幾個位置都回傳（extra.dup／ndup）。端子排鍵：主低壓箱 +Q10 寫 'XT07'，電阻箱 +Q11 寫 '+Q11-XT02'。
原理圖（DRW）上的端子不框（號碼重複出現、對不到唯一一處）。
"""
import re

try:
    import fitz
except ImportError:          # 只有建索引才用到
    fitz = None

DOC_KEY = 'epgc'
_LABEL = re.compile(r'^-(XT(?:DE|\d+)|B\.V\d+)$')
_REF = re.compile(r'^(DRW_\d+)\.([A-F])(\d)$')
_SHEET = re.compile(r'^(DRW|TER|LVC|COV|CON|SLD|BOM)_\S*$')
_TERM = re.compile(r'(?:\+?(Q1[01])\s*)?-?\s*(XT\s*(?:DE|\d+))\s*[-: ]\s*(\d+)\s*$', re.I)


def _strip_norm(s, loc='+Q10'):
    s = s.upper().replace(' ', '').lstrip('-')
    m = re.match(r'^XT(\d+)$', s)
    if m:
        s = 'XT%02d' % int(m.group(1))
    return s if loc in ('', '+Q10') else '%s-%s' % (loc, s)


def _term_norm(t):
    t = t.strip()
    return str(int(t)) if t.isdigit() else t.upper()


def _spans(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            d = (round(l['dir'][0]), round(l['dir'][1]))
            for s in l['spans']:
                t = s['text'].strip()
                if t:
                    out.append({'r': fitz.Rect(s['bbox']), 't': t, 'dir': d, 'size': s['size']})
    return out


def _titleblock(spans):
    sheet = loc = ''
    pno = []
    for s in spans:
        r = s['r']
        if r.y0 > 805 and r.y1 < 830:
            if r.x0 > 1010 and r.x1 < 1100 and _SHEET.match(s['t']):
                sheet = s['t']
            elif 858 < r.x0 < 950 and s['t'].startswith('+'):
                loc = s['t']
            elif r.x0 > 1105 and s['t'].isdigit():
                pno.append((r.x0, s['t']))
    return sheet, loc, '/'.join(t for _, t in sorted(pno))


def _add(d, k, v):
    d.setdefault(k, []).append(v)


def _box(r):
    return [round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)]


def _layout(pno, spans, sheet, loc, idx):
    labels = [s for s in spans if _LABEL.match(s['t']) and 1.5 < s['size'] < 6]
    nums = [s for s in spans if s['size'] < 3.2 and (s['t'].isdigit() or s['t'] == 'PE')
            and not _LABEL.match(s['t'])]
    for lb in labels:
        r = lb['r']
        xc, yc = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        strip = _strip_norm(lb['t'], loc)
        overview = lb['size'] < 2.0              # LVC_01 整箱總圖：只有標籤（號碼約 0.9 pt）
        _add(idx['strips'], ('*', strip), {'page': pno, 'box': _box(r), 'text': lb['t'], 'kind': 'strip',
                                           'extra': {'view': 'overview' if overview else 'layout',
                                                     'sheet': sheet, 'loc': loc}})
        if overview:
            continue
        vertical = lb['dir'] == (1, 0)          # 標籤橫寫 → 端子往下排
        if vertical:
            cand = [n for n in nums if r.y1 - 0.5 <= n['r'].y0 <= r.y1 + 10 and abs(n['r'].x0 - xc) < 30]
            if not cand:
                continue
            first = min(cand, key=lambda n: (n['r'].y0, abs(n['r'].x0 - xc)))
            stop = min([o['r'].y0 for o in labels if o is not lb and abs((o['r'].x0 + o['r'].x1) / 2 - xc) < 15
                        and o['r'].y0 > r.y1] + [1e9])
            run = sorted([n for n in nums if abs(n['r'].x0 - first['r'].x0) < 1.5 and r.y1 - 0.5 <= n['r'].y0 < stop],
                         key=lambda n: n['r'].y0)
            half = 26 if lb['size'] > 3.5 else 12
            boxes = [fitz.Rect(min(xc - half, n['r'].x0 - 1), n['r'].y0 - 1.1, max(xc + half, n['r'].x1 + 1), n['r'].y1 + 1.1)
                     for n in run]
        else:                                     # 標籤直寫 → 端子往右排
            cand = [n for n in nums if r.x1 - 0.5 <= n['r'].x0 <= r.x1 + 10 and abs(n['r'].y0 - yc) < 30]
            if not cand:
                continue
            first = min(cand, key=lambda n: (n['r'].x0, abs(n['r'].y0 - yc)))
            stop = min([o['r'].x0 for o in labels if o is not lb and abs((o['r'].y0 + o['r'].y1) / 2 - yc) < 15
                        and o['r'].x0 > r.x1] + [1e9])
            run = sorted([n for n in nums if abs(n['r'].y0 - first['r'].y0) < 1.5 and r.x1 - 0.5 <= n['r'].x0 < stop],
                         key=lambda n: n['r'].x0)
            half = 27 if lb['size'] > 3.5 else 12
            boxes = [fitz.Rect(n['r'].x0 - 1.1, min(yc - half, n['r'].y0 - 1), n['r'].x1 + 1.1, max(yc + half, n['r'].y1 + 1))
                     for n in run]
        seen = {}
        for n in run:
            seen[n['t']] = seen.get(n['t'], 0) + 1
        cnt = {}
        for n, bx in zip(run, boxes):
            cnt[n['t']] = cnt.get(n['t'], 0) + 1
            _add(idx['terms'], ('*', strip, _term_norm(n['t'])),
                 {'page': pno, 'box': _box(bx), 'text': n['t'], 'kind': 'term',
                  'extra': {'view': 'layout', 'sheet': sheet, 'loc': loc, 'num_box': _box(n['r']),
                            'dup': cnt[n['t']], 'ndup': seen[n['t']]}})


def _plan(pno, spans, sheet, loc, idx, pp):
    title = [s for s in spans if s['size'] > 14 and s['dir'] == (0, -1) and s['r'].x1 < 100]
    hdr = [s for s in spans if s['t'] == 'number' and s['r'].x1 < 230]
    if not title or not hdr:
        return
    strip = _strip_norm(title[0]['t'], loc)
    _add(idx['strips'], ('*', strip), {'page': pno, 'box': _box(title[0]['r']), 'text': title[0]['t'],
                                       'kind': 'strip', 'extra': {'view': 'plan', 'sheet': sheet, 'loc': loc}})
    ny0, ny1 = hdr[0]['r'].y0 - 3, hdr[0]['r'].y1 + 14
    nums = sorted([s for s in spans if s['dir'] == (0, -1) and s['r'].x0 > 225 and s['r'].y0 >= ny0
                   and s['r'].y1 <= ny1], key=lambda s: s['r'].x0)
    top = min([s['r'].y0 for s in spans if s['t'] in ('Sheet',)] + [40]) - 18
    bot = max([s['r'].y1 for s in spans if s['t'] in ('Type de borne',)] + [760]) + 8
    seen = {}
    for n in nums:
        seen[n['t']] = seen.get(n['t'], 0) + 1
    cnt = {}
    for n in nums:
        cx = (n['r'].x0 + n['r'].x1) / 2
        pitch = (nums[1]['r'].x0 - nums[0]['r'].x0) if len(nums) > 1 else 17.0
        col = sorted([s for s in spans if s is not n and s['dir'] == (0, -1) and abs((s['r'].x0 + s['r'].x1) / 2 - cx) < 6
                      and s['r'].x0 > 225], key=lambda s: s['r'].y0)
        ex = {'view': 'plan', 'sheet': sheet, 'loc': loc, 'printed_page': pp.split('/')[0],
              'num_box': _box(n['r'])}
        for s in col:
            y = s['r'].y0
            if _REF.match(s['t']):
                ex['ref'] = s['t']
            elif s['t'].startswith(('H07', 'NT', 'LIYCY', 'Olflex')) or 'sqmm' in s['t'] or 'mm2' in s['t']:
                ex['cable_top' if y < n['r'].y0 else 'cable_bottom'] = s['t']
            elif y > 700:
                ex['ttype'] = s['t']
            else:
                ex['target_top' if y < n['r'].y0 else 'target_bottom'] = s['t']
        cnt[n['t']] = cnt.get(n['t'], 0) + 1
        ex['dup'], ex['ndup'] = cnt[n['t']], seen[n['t']]
        ex['connected'] = any(k in ex for k in ('ref', 'target_top', 'target_bottom'))  # False＝端子表上是備用
        bx = fitz.Rect(cx - pitch / 2, top, cx + pitch / 2, bot)
        _add(idx['terms'], ('*', strip, _term_norm(n['t'])), {'page': pno, 'box': _box(bx), 'text': n['t'], 'kind': 'row', 'extra': ex})


def build_index(pdf_paths):
    """pdf_paths：{機組或 '*': 路徑}（同一份只讀一次）→ {'strips','terms','doc','analog'}。"""
    idx = {'strips': {}, 'terms': {}, 'doc': {}, 'analog': {}}
    done = {}
    for unit, path in pdf_paths.items():
        idx['doc'][unit] = path
        if path in done:
            continue
        done[path] = True
        doc = fitz.open(path)
        for i, page in enumerate(doc):
            sp = _spans(page)
            sheet, loc, pp = _titleblock(sp)
            if sheet.startswith('LVC_'):
                _layout(i + 1, sp, sheet, loc, idx)
            elif sheet.startswith('TER_'):
                _plan(i + 1, sp, sheet, loc, idx, pp)
        doc.close()
    return idx


def key_of(entry, cond):
    """這條芯 GCB 那一端 → ('*', 端子排, 端子號) 或 None。"""
    end = entry.get('end')
    if end == 'jb' and ('GCB' in entry.get('jb', '') or 'MSC20' in entry.get('jb', '')):
        raw, strip_hint = cond.get('jb_term', ''), entry.get('jb_tb', '')
    elif end == 'panel' and ('GCB' in entry.get('panel', '') or 'MSC20' in entry.get('panel', '')):
        raw = (cond.get('panel_board', '') + ' ' + cond.get('panel_num', '')).strip()
        strip_hint = entry.get('panel_tb', '')
    else:
        return None
    m = _TERM.search(raw)
    if m:
        loc = '+' + m.group(1).upper() if m.group(1) else '+Q10'
        return ('*', _strip_norm(m.group(2), loc), _term_norm(m.group(3)))
    t = raw.split()[-1] if raw.split() else ''
    hint = [h for h in re.split(r'[/,]', strip_hint) if re.search(r'XT', h, re.I)]
    if t.isdigit() and len(hint) == 1:
        return ('*', _strip_norm(hint[0]), _term_norm(t))
    return None


# ---------------------------------------------------------------- 統一介面
def build(paths):
    """paths：{'epgc': 路徑}。"""
    return build_index({'*': paths[DOC_KEY]})


def _hit(page, box, kind, label, primary, extra):
    return {'doc_key': DOC_KEY, 'page': page, 'box': list(box), 'kind': kind, 'label': label, 'primary': primary, 'extra': extra}


def _printed(strip):
    """鍵 → 圖上印的端子排名：'XT07' → '-XT07'、'+Q11-XT02' → '+Q11-XT02'。"""
    return strip if strip.startswith('+') else '-' + strip


def locate(ix, entry, cond):
    """→ [hit]：低壓箱配置圖上的端子塊（主框）、端子表那一欄（副框；沒有端子塊才當主框）、端子排標籤與表名（副框）。"""
    k = key_of(entry, cond)
    if not k:
        return []
    terms = ix['terms'].get(k, [])
    has_term = any(h['kind'] == 'term' for h in terms)
    has_row = any(h['kind'] == 'row' for h in terms)
    lab = '%s %s' % (_printed(k[1]), k[2])
    out = []
    for kind in ('term', 'row'):
        for h in sorted((h for h in terms if h['kind'] == kind), key=lambda h: (h['page'], h['box'][1], h['box'][0])):
            x = h['extra']
            ex = {f: x[f] for f in ('sheet', 'loc', 'printed_page', 'num_box', 'dup', 'ndup', 'ref', 'connected', 'target_top',
                                    'target_bottom', 'cable_top', 'cable_bottom', 'ttype') if x.get(f) is not None}
            ex['generic'] = 1
            out.append(_hit(h['page'], h['box'], kind, lab, kind == 'term' or not has_term, ex))
    for h in ix['strips'].get(k[:2], []):
        x = h['extra']
        prim = not (has_term or has_row) and x['view'] == 'layout'
        out.append(_hit(h['page'], h['box'], 'strip', h['text'], prim,
                        {'part': x['view'], 'sheet': x['sheet'], 'loc': x['loc'], 'generic': 1}))
    return out


def missing(ix, entry, cond):
    """找不到端子塊時的原因（卡片註記用）；找得到回 None。"""
    k = key_of(entry, cond)
    if not k:
        raw = cond.get('jb_term', '') if entry.get('end') == 'jb' else '%s %s' % (cond.get('panel_board', ''), cond.get('panel_num', ''))
        return '端子寫法解析不出（「%s」）' % raw.strip()
    kinds = {h['kind'] for h in ix['terms'].get(k, [])}
    if 'term' in kinds:
        return None
    if 'row' in kinds:
        return '低壓箱配置圖上沒有 %s（只有端子表那一欄）' % ' '.join((_printed(k[1]), k[2]))
    if ix['strips'].get(k[:2]):
        return 'GCB 接線圖的 %s 沒有第 %s 號' % (_printed(k[1]), k[2])
    return 'GCB 接線圖沒有端子排 %s' % _printed(k[1])
