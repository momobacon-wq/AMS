# -*- coding: utf-8 -*-
r"""tools/db/wire_gt.py — 燃機儀控電纜接線圖（一號機 HT1-1-ICE01-D1004，CTCI）一頁 → 子圖（v14，給 wire_ge.py 用）。

這份圖與汽機的 HT1-1-ICE01-D1005 同一家、同一類試算表範本，但欄位位置不同，而且兩半本整頁平移：
  GT-11 半本（約 p.9–429）表頭 FIELD 在 x≈188；GT-12 半本（約 p.430–846）與後補頁（p.847–855）在 x≈204，表頭的 y 逐頁浮動。
  圖框標題的機組字樣不可信（p.847 標 GT-11、內容是 G12；p.850 是汽機），機組一律由盤／JB／幹線的 KKS 前綴判定（unit_of）。
所以欄位不用固定欄帶，改用**向量框線**：表頭 FIELD 字給粗位移 dx，再在參考位置 REF＋dx ±COL_TOL 找六條豎線
  L0 說明欄左緣、L1 JB 端子欄左緣、L2 JB 端子欄右緣、P0 盤端子欄左緣、P1 盤端子欄右緣、P2 盤框右緣。
橫線分出格子：元件框＝從 L0 橫到 L2；JB 端子格＝L1→L2；盤端子格＝P0→P1（或 P2）。
**每一條芯以它的接線短線（stub）定位**：JB 側 L2→JB 匯流豎線、盤側 盤匯流豎線→P0 各一小段橫線；芯色標籤畫在短線上方。
JB 側的芯與盤側的芯以芯色標籤做 LCS 序列對齊，標籤對不上的夾在兩個對上的中間時照順序補配並旗標（label_typo）：
  盤側不畫 SH（列數不同）、同一條幹線芯色會重複（p.10 兩個 BK-3）或印錯（p.386、p.805 JB 側 WH-3 對盤側 WH-2），所以不能照 y、也不能只信標籤字。
一頁可以疊好幾個子圖（p.413、p.145、p.846）：圖區中段再出現 JB 欄的表頭（JUNCTION BOX/PANEL:／MCC NO.:／PANEL :／FIELD…）就另起一段，
  盤表頭只在頂端、盤框是整頁共用的長框。

畫法（mode）：
  'jbdev'  元件畫在 JB 欄的框裡（Case-II，圖例 p.8）：沒有現場電纜，JB 端子 → 幹線 → 盤；
  'direct' JB 欄寫的就是元件自己（TERMINAL NO. '-Direct'，或標頭直接是元件位號）：元件端子 → 一條電纜直拉到盤；
  'ff'     Foundation Fieldbus 段的幹線（'GT SEGMENT -7 (FBSP-GT-7)'，JB 端子 SIG+／SIG-／SH，盤 'CA002 FFPC3 S5 73'）：不是個別元件；
  'link'   盤對盤的通訊／接頭線（表頭 'PANEL.:'）：不是元件，不收。
兩層的熱電偶頁（表頭 FIELD 在 JB 欄的位置，p.395–400、412、814–819、833）不在這一版（no_frame 回空，wire_ge 計數）。

輸出與 wire_ge.parse_page 同一套欄位（wire_ge.build 不分圖）：
  {'sheet','of','unit','h':{jb, jb_desc, jb_tb, panel, panel_tb, field_tb},'mode','groups':[{desc, desc_w, cable, cable_w, spec, lo, hi}],
   'trunks':[{cable, cable_w, spec, lo, hi}],'rows':[{core, core_w, jb_cell, field_cell, jb_in, field_core, group, trunk, panel_cell, pcore_w}],
   'pdesc','flags','sub'}；格子＝{'t','lines','w','y'}。
"""
import hashlib
import json
import os
import re

REF = {'L0': 279.1, 'L1': 421.3, 'L2': 462.9, 'P0': 629.5, 'P1': 679.4, 'P2': 771.9}   # GT-11 半本（FIELD 字 x0＝188）實測
FIELD_REF = 188.0
COL_TOL = 9.0                     # 找豎線：REF＋dx 的左右容許（pt）
END_TOL = 2.5                     # 橫線兩端對到豎線的容許（pt）
STUB_LEN = (10.0, 30.0)           # 接線短線最短長度（JB 側 L2→匯流線約 18 pt、盤側匯流線→P0 約 21 pt；直拉頁一條線畫到底）
LABEL_ABOVE = 13.0                # 芯色標籤底緣在短線上方這個距離內
DRAW_BOTTOM = 700.0               # 圖區下緣（標題欄、REV 欄以外）
CORE_RE = re.compile(r'^(?:BK|WH|RD|BU|BL|GN|YE|YL|OR|BR|BN|GY|GR|PU|PK|SH|SHD|GND)(?:-\d+)?$')
REV_PAD = 25.0                    # 盤框右緣 P2 之外：REV 欄的版次小框（'B'／'C'）在 GT-12 半本與標頭同一個 y，不收
CAB_RE = re.compile(r'^([A-Z0-9_]+?)\s*(-?WG-\d+)$')
KKS_RE = re.compile(r'[GS]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z0-9]*')
UNIT_RE = re.compile(r'\b([GS]\d{2})[A-Z]{3}\d{2}[A-Z]{2}\d{3}')
HDR_START = ('JUNCTION', 'MCC', 'PANEL', 'FIELD', 'INSTRUMENT')
FRAME_VERSION = 1


# ---------------------------------------------------------------- 小工具（不 import wire_ge，避免循環）
def lines_of(ws, tol=3.0):
    out = []
    for w in sorted(ws, key=lambda w: (w['y0'], w['x0'])):
        if out and abs(out[-1][0]['y0'] - w['y0']) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(l, key=lambda w: w['x0']) for l in out]


def ltext(l):
    return ' '.join(w['t'] for w in l)


def cy(w):
    return (w['y0'] + w['y1']) / 2.0


def cx(w):
    return (w['x0'] + w['x1']) / 2.0


def cell_of(ws, x0, x1, y0, y1):
    """一格（x0..x1, y0..y1）裡的字 → {'t','lines','w','y'}；空格回 None。"""
    cw = [w for w in ws if x0 < cx(w) < x1 and y0 < cy(w) < y1]
    if not cw:
        return None
    ls = lines_of(cw)
    return {'t': ' '.join(ltext(l) for l in ls), 'lines': [ltext(l) for l in ls], 'w': cw, 'y': ls[0][0]['y0']}


# ---------------------------------------------------------------- 向量框線（快取）
def page_frames(fpage):
    """PyMuPDF 一頁 → {'v': [[x, y0, y1]…], 'h': [[y, x0, x1]…], 'c': 有沒有彩色線（as-built 手改）}（顯示座標，四捨五入 0.1）。"""
    M = fpage.rotation_matrix
    v, h, colored = [], [], 0
    for dr in fpage.get_drawings():
        col = tuple(round(c, 2) for c in (dr.get('color') or dr.get('fill') or (0, 0, 0)))
        is_col = len(col) == 3 and max(col) - min(col) > 0.15
        for it in dr['items']:
            if it[0] == 're':
                r = it[1] * M
                r.normalize()
                x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
            elif it[0] == 'l':
                a, b = it[1] * M, it[2] * M
                x0, y0, x1, y1 = min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)
            else:
                continue
            if x0 > 900 or y0 > DRAW_BOTTOM:
                continue
            if x1 - x0 < 2.0 and y1 - y0 > 6:
                v.append([round((x0 + x1) / 2.0, 1), round(y0, 1), round(y1, 1)])
            elif y1 - y0 < 2.0 and x1 - x0 > 6:
                h.append([round((y0 + y1) / 2.0, 1), round(x0, 1), round(x1, 1)])
            else:
                continue
            if is_col:
                colored = 1
    return {'v': v, 'h': h, 'c': colored}


def load_frames(pdf_abs, rel, size, mtime, cache_dir, pages):
    """整本（或指定頁）的框線，快取在 cache_dir/frames_<hash>.json（以 rel／size／mtime／FRAME_VERSION 為鍵）。→ {頁: frames}。"""
    key = hashlib.sha1(('%s|%s|%s|%d' % (rel, size, mtime, FRAME_VERSION)).encode('utf-8')).hexdigest()[:16]
    fn = os.path.join(cache_dir, 'frames_%s.json' % key)
    have = {}
    if os.path.exists(fn):
        with open(fn, encoding='utf-8') as f:
            have = {int(k): v for k, v in json.load(f).items()}
    need = [p for p in pages if p not in have]
    if need:
        import fitz
        doc = fitz.open(pdf_abs)
        for p in need:
            have[p] = page_frames(doc[p - 1])
        doc.close()
        os.makedirs(cache_dir, exist_ok=True)
        tmp = fn + '.%d.tmp' % os.getpid()
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({str(k): have[k] for k in sorted(have)}, f, separators=(',', ':'))
        os.replace(tmp, fn)
    return have


# ---------------------------------------------------------------- 一頁
def sheet_no(ws):
    """圖框 'PROJ. 04 of 849'（小寫 of）→ (4, 849)。"""
    for i, w in enumerate(ws):
        if w['t'].lower() == 'of' and 0 < i < len(ws) - 1 and w['x0'] > 745 and w['y0'] > 760 \
                and ws[i - 1]['t'].isdigit() and ws[i + 1]['t'].isdigit():
            return int(ws[i - 1]['t']), int(ws[i + 1]['t'])
    return None, None


def unit_of(*texts):
    """盤／JB／幹線的 KKS 前綴 → 機組（G11／G12／S10…）；第一個找到的為準。"""
    for t in texts:
        m = UNIT_RE.search(t or '')
        if m:
            return m.group(1)
    return ''


def lcs_pair(a, b, key=lambda x: x):
    """兩個序列以 key 相等做 LCS 對齊，再把夾在兩個對齊點之間、數量相等的未對齊項目照順序補配（標記 'gap'）。
    → [(i, j, how)]，how＝'label'（標籤相同）或 'gap'（照順序補配、標籤不同）。"""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if key(a[i]) == key(b[j]) else max(dp[i + 1][j], dp[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if key(a[i]) == key(b[j]):
            pairs.append((i, j, 'label'))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    out, pi, pj = [], -1, -1
    for i2, j2, how in pairs + [(n, m, 'end')]:
        ga, gb = list(range(pi + 1, i2)), list(range(pj + 1, j2))
        if ga and len(ga) == len(gb):
            out += [(x, y, 'gap') for x, y in zip(ga, gb)]
        if how != 'end':
            out.append((i2, j2, how))
        pi, pj = i2, j2
    return out


def parse_hdr(lines, cols):
    """JB 欄與盤欄頂端的標頭行 → h。"""
    h = {'jb': '', 'jb_desc': '', 'jb_tb': '', 'panel': '', 'panel_tb': '', 'field_tb': '', 'kind': ''}
    for l in lines:
        x = l[0]['x0']
        t = re.sub(r'\s*/\s*', '/', ltext(l)).strip()
        side = 'panel' if x >= cols['P0'] - 8 else 'jb'
        m = re.match(r'^TERMINAL\s*NO\.?\s*:?\s*(.*)$', t)
        if m:
            h[side + '_tb'] = m.group(1).strip(' :')
            continue
        if side == 'panel':
            m = re.match(r'^PANEL\s*\.?\s*:?\s*(.*)$', t)
            if m:
                h['panel'] = m.group(1).strip(' :')
            continue
        m = re.match(r'^(JUNCTION BOX/PANEL|JUNCTION BOX|FIELD/JUNCTION BOX|FIELD|MCC NO\.|MCC/SWGR\.|INSTRUMENT NO\.|PANEL)\s*(\.)?\s*:?\s*(.*)$', t)
        if m and not h['jb']:
            h['jb'] = m.group(3).strip(' :')
            h['kind'] = m.group(1) + (m.group(2) or '')
        elif not h['jb_desc'] and h['jb']:
            h['jb_desc'] = t
    return h


def parse_page(pg_ws, fr):
    """一頁（display 座標的字表 pg_ws、框線 fr）→ 子圖清單（見檔頭）。不是接線圖的頁（封面、空白頁）回 []。
    沒有框線的頁回 [{'flags': ['no_frame'], …}]（兩層熱電偶頁等，這一版不解析）。"""
    ws = [w for w in pg_ws if w['y0'] < DRAW_BOTTOM + 120]
    sno, of = sheet_no(pg_ws)
    if not sno or any(w['t'] == 'Intentionally' for w in ws):
        return []
    F = sorted([w for w in ws if w['t'] == 'FIELD' and w['y0'] < 140 and w['x0'] < 320], key=lambda w: w['y0'])
    if not F:
        return [{'sheet': sno, 'of': of, 'flags': ['no_field_header'], 'rows': [], 'groups': [], 'mode': ''}]
    F = F[0]
    dx = F['x0'] - FIELD_REF
    cols = {}
    for k, ref in REF.items():
        c = [v for v in fr['v'] if abs(v[0] - (ref + dx)) < COL_TOL and v[1] > F['y0'] + 10]
        cols[k] = min(c, key=lambda v: abs(v[0] - (ref + dx)))[0] if c else None
    if any(cols[k] is None for k in ('L1', 'L2', 'P0', 'P1')):
        return [{'sheet': sno, 'of': of, 'flags': ['no_frame'], 'rows': [], 'groups': [], 'mode': ''}]
    if cols['L0'] is None:
        cols['L0'] = cols['L1'] - 142.0
    if cols['P2'] is None:
        cols['P2'] = cols['P1'] + 92.0
    L0, L1, L2, P0, P1, P2 = (cols[k] for k in ('L0', 'L1', 'L2', 'P0', 'P1', 'P2'))
    ytop = F['y0'] + 8
    H = [h for h in fr['h'] if ytop < h[0] < DRAW_BOTTOM]
    near = lambda a, b: abs(a - b) < END_TOL   # noqa: E731
    dev_sep = sorted({h[0] for h in H if near(h[1], L0) and near(h[2], L2)})
    jb_sep = sorted({h[0] for h in H if near(h[1], L1) and near(h[2], L2)})
    p_sep = sorted({h[0] for h in H if near(h[1], P0) and (near(h[2], P1) or near(h[2], P2))})
    # 芯：從 L2 起頭的橫線（短線接到 JB 匯流線，或直拉頁一路畫到 P0）／終點在 P0 的橫線
    jstub = sorted({h[0] for h in H if near(h[1], L2) and h[2] - h[1] > STUB_LEN[0] and h[2] < P0 + END_TOL})
    pstub = sorted({h[0] for h in H if near(h[2], P0) and h[2] - h[1] > STUB_LEN[0] and h[1] > L2 - END_TOL})
    tlines = sorted({h[0] for h in H if h[1] > L2 + 5 and h[2] < P0 - 5 and h[2] - h[1] > 60})
    if not dev_sep and not jb_sep:
        return [{'sheet': sno, 'of': of, 'flags': ['no_boxes'], 'rows': [], 'groups': [], 'mode': ''}]
    box_top = min(dev_sep + jb_sep)
    # ---- 子圖切分：JB 欄裡的標頭行（box_top 之上＝頁首；之下＝另一個子圖）
    # JB 欄的標頭行從 L1 起頭（端子格的字在格內縮排或是端子號），以 JUNCTION／MCC／PANEL／FIELD／INSTRUMENT 開頭
    hl = lines_of([w for w in ws if L1 - 6 <= w['x0'] < P0 - 30 and box_top < w['y0'] < DRAW_BOTTOM])
    starts = [ytop] + [l[0]['y0'] for l in hl if L1 - 6 <= l[0]['x0'] < L1 + 8 and ltext(l).startswith(HDR_START)]
    bounds = list(zip(starts, starts[1:] + [DRAW_BOTTOM]))
    # ---- 盤側（整頁共用）：標頭、說明、芯
    ph_lines = lines_of([w for w in ws if P0 - 8 <= w['x0'] < P2 + REV_PAD and ytop < w['y0'] < box_top and not CORE_RE.match(w['t'])])
    pdesc = ' '.join(ltext(l) for l in lines_of([w for w in ws if P1 + 2 < cx(w) < P2 and box_top < w['y0'] < DRAW_BOTTOM]))
    plabels = [w for w in ws if CORE_RE.match(w['t']) and P0 - 34 < w['x0'] < P0 and w['y0'] > box_top - 3]
    pcells_y = p_sep
    flags_page = ['asbuilt_markup'] if fr.get('c') else []
    out = []
    for si, (y0, y1) in enumerate(bounds):
        hdr = lines_of([w for w in ws if L1 - 6 <= w['x0'] < P0 - 30 and y0 - 1 <= w['y0'] < min([y for y in dev_sep + jb_sep if y > y0 + 2] or [y1])
                        and not CORE_RE.match(w['t'])])
        cap = lines_of([w for w in ws if L0 - 4 <= w['x0'] < L1 - 8 and y0 - 1 <= w['y0'] < min([y for y in dev_sep + jb_sep if y > y0 + 2] or [y1])])
        h = parse_hdr(hdr + (ph_lines if si == 0 else []), cols)
        if si:
            top_h = parse_hdr(ph_lines, cols)
            h['panel'], h['panel_tb'] = top_h['panel'], top_h['panel_tb']
        if not h['jb_desc'] and cap:
            h['jb_desc'] = ' '.join(ltext(l) for l in cap)
        flags = list(flags_page)
        if any(re.match(r'^PANEL\s*\.\s*:', ltext(l)) for l in ph_lines + hdr):   # 'PANEL.:' 頁＝盤對盤的通訊／接頭線
            out.append({'sheet': sno, 'of': of, 'unit': unit_of(h['panel'], h['jb']), 'h': h, 'mode': 'link', 'groups': [], 'trunks': [],
                        'rows': [], 'pdesc': pdesc, 'flags': ['link'], 'sub': si})
            continue
        ds = [y for y in dev_sep if y0 <= y < y1]
        js = sorted(set([y for y in jb_sep if y0 <= y < y1] + ds))
        # 元件框
        groups = []
        for a, b in zip(ds, ds[1:]):
            dw = [w for w in ws if L0 < cx(w) < L1 - 1 and a < cy(w) < b]
            if dw:
                ls = lines_of(dw)
                groups.append({'desc': ' '.join(ltext(l) for l in ls), 'desc_w': dw, 'cable': '', 'cable_w': None, 'spec': '', 'lo': a, 'hi': b})
        # JB 端子格（元件框之內，含框線分隔）
        jcells = []
        for a, b in zip(js, js[1:]):
            c = cell_of(ws, L1, L2, a, b)
            jcells.append((a, b, c))
        # 芯：JB 側短線
        st = [y for y in jstub if y0 <= y < y1]
        jl = [w for w in ws if CORE_RE.match(w['t']) and L2 - 3 < w['x0'] < L2 + 32 and y0 <= w['y0'] < y1]
        rows = []
        used = set()
        for y in st:
            cand = [w for w in jl if -2.0 <= y - w['y1'] <= LABEL_ABOVE and id(w) not in used]
            lab = min(cand, key=lambda w: abs(y - w['y1'])) if cand else None
            if lab is not None:
                used.add(id(lab))
            cell = next((c for a, b, c in jcells if a - 0.5 <= y <= b + 0.5), None)
            gi = next((k for k, g in enumerate(groups) if g['lo'] - 0.5 <= y <= g['hi'] + 0.5), None)
            rows.append({'core': lab['t'] if lab else '', 'core_w': lab, 'y': y, 'jb_cell': cell, 'group': gi})
        if not st and jl:            # 沒畫短線（少數頁）：以標籤底緣代替
            for w in sorted(jl, key=lambda w: w['y0']):
                y = w['y1'] + 1.5
                cell = next((c for a, b, c in jcells if a - 0.5 <= y <= b + 0.5), None)
                gi = next((k for k, g in enumerate(groups) if g['lo'] - 0.5 <= y <= g['hi'] + 0.5), None)
                rows.append({'core': w['t'], 'core_w': w, 'y': y, 'jb_cell': cell, 'group': gi})
            flags.append('no_stub')
        if any(not r['core'] for r in rows):
            flags.append('stub_without_label')
        # 盤側芯（這個子圖的 y 範圍；盤框是整頁的長框，子圖之間以 y 分）
        ps = [y for y in pstub if y0 <= y < y1]
        prow = []
        pused = set()
        for y in ps:
            cand = [w for w in plabels if -2.0 <= y - w['y1'] <= LABEL_ABOVE and id(w) not in pused]
            lab = min(cand, key=lambda w: abs(y - w['y1'])) if cand else None
            if lab is not None:
                pused.add(id(lab))
            cell = None
            for a, b in zip(pcells_y, pcells_y[1:]):
                if a - 0.5 <= y <= b + 0.5:
                    cell = cell_of(ws, P0, P1, a, b)
                    break
            prow.append({'core': lab['t'] if lab else '', 'w': lab, 'y': y, 'cell': cell})
        # 幹線
        tr = []
        tw = [w for w in ws if L2 + 22 < cx(w) < P0 - 22 and y0 <= w['y0'] < y1]
        for l in lines_of(tw):
            s = ''.join(w['t'] for w in l)
            m = CAB_RE.match(s)
            if m:
                cab = m.group(1) + '-' + m.group(2).lstrip('-')
                sp = [w for w in tw if l[0]['y1'] - 1 < w['y0'] < l[0]['y1'] + 9]
                tr.append({'cable': cab, 'cable_w': {'t': cab, 'x0': l[0]['x0'], 'y0': l[0]['y0'], 'x1': l[-1]['x1'], 'y1': l[-1]['y1']},
                           'spec': ' '.join(ltext(x) for x in lines_of(sp)), 'y': l[0]['y0']})
        tys = [y for y in tlines if y0 <= y < y1]
        if len(tr) > 1:
            ys = sorted(t['y'] for t in tr)
            for k, t in enumerate(sorted(tr, key=lambda t: t['y'])):
                t['lo'] = (ys[k - 1] + ys[k]) / 2.0 if k else y0
                t['hi'] = (ys[k] + ys[k + 1]) / 2.0 if k + 1 < len(ys) else y1
            tr.sort(key=lambda t: t['y'])
            flags.append('multi_trunk')
        else:
            for t in tr:
                t['lo'], t['hi'] = y0, y1
        if not tr and rows:
            flags.append('no_trunk')
        # JB 列 ↔ 盤列：同一條幹線內以芯色標籤 LCS 對齊（盤側常沒有 SH 列、標籤可能重複或印錯）
        for ti in range(max(len(tr), 1)):
            lo, hi = (tr[ti]['lo'], tr[ti]['hi']) if tr else (y0, y1)
            jr = [r for r in rows if lo <= r['y'] < hi]
            pr = [p for p in prow if lo - 30 <= p['y'] < hi + 30 and not p.get('done')] if len(tr) > 1 else [p for p in prow if not p.get('done')]
            jr_ = [r for r in jr if not r['core'].startswith('SH')]
            pr_ = [p for p in pr if not p['core'].startswith('SH')]
            for i, j, how in lcs_pair(jr_, pr_, key=lambda x: x['core']):
                r, p = jr_[i], pr_[j]
                r['panel_cell'], r['pcore_w'], r['pcore'] = p['cell'], p['w'], p['core']
                p['done'] = 1
                if how == 'gap':
                    r['ptypo'] = p['core']
                    flags.append('label_typo:%s→%s' % (r['core'], p['core']))
            # 盤側也畫了 SH 的（FF 段：SH 落盤端子）
            js_ = [r for r in jr if r['core'].startswith('SH')]
            ps_ = [p for p in pr if p['core'].startswith('SH') and not p.get('done')]
            for i, j, how in lcs_pair(js_, ps_, key=lambda x: x['core'].replace('SHD', 'SH')):
                js_[i]['panel_cell'], js_[i]['pcore_w'], js_[i]['pcore'] = ps_[j]['cell'], ps_[j]['w'], ps_[j]['core']
                ps_[j]['done'] = 1
            for r in jr:
                r['trunk'] = ti if tr else None
        for r in rows:
            r.setdefault('panel_cell', None)
            r.setdefault('trunk', None)
            if r['panel_cell'] is None and not r['core'].startswith('SH'):
                flags.append('panel_unmatched:%s' % (r['core'] or '?'))
        left = [p['core'] for p in prow if not p.get('done') and p['core'] and p['cell'] and 'SPARE' not in p['cell']['t'].upper()]   # 沒有標籤的＝盤底屏蔽匯流（IS／OS）
        if left:
            flags.append('panel_unpaired:%s' % ','.join(left))
        if any(r['group'] is None for r in rows):
            flags.append('row_no_dev')
        # 畫法
        jtb = h['jb_tb'].replace(' ', '')
        ptxt = ' '.join((r['panel_cell'] or {}).get('t', '') for r in rows)
        if 'FFPC' in ptxt:
            mode = 'ff'
        elif 'Direct' in jtb or re.match(r'^(?:Limit Switch|[0-9]{0,2}[A-Z]{1,6}-?[A-Z0-9]*-[0-9A-Z]+)/', h['jb']) and not re.match(r'^(?:JB|JBX|JBR|JBG|JBGFP|MSP|GPP|GCB|LCI|MCC|PANEL)', h['jb'], re.I):
            mode = 'direct'
        else:
            mode = 'jbdev'
        if not groups and rows:        # 沒有元件框（儀器本身就是「JB」，p.392）：以 JB 標頭當元件
            hw = [w for l in hdr for w in l]
            groups.append({'desc': h['jb'], 'desc_w': hw, 'cable': '', 'cable_w': None, 'spec': '', 'lo': y0, 'hi': y1})
            for r in rows:
                r['group'] = 0
            flags.append('device_is_header')
        if mode == 'direct':
            for r in rows:
                r['field_cell'], r['jb_cell'] = r['jb_cell'], None
            if tr:
                for g in groups:
                    g['cable'], g['cable_w'], g['spec'] = tr[0]['cable'], tr[0]['cable_w'], tr[0]['spec']
            trunks = []
            for r in rows:
                r['trunk'] = None
        else:
            trunks = [{'cable': t['cable'], 'cable_w': t['cable_w'], 'spec': t['spec'], 'lo': t['lo'], 'hi': t['hi']} for t in tr]
        for r in rows:
            r.setdefault('field_cell', None)
            r['jb_in'], r['field_core'], r['prox'] = '', '', ''
        unit = unit_of(h['panel'], h['jb'], tr[0]['cable'] if tr else '')
        out.append({'sheet': sno, 'of': of, 'unit': unit, 'h': h, 'mode': mode, 'groups': groups, 'trunks': trunks, 'rows': rows,
                    'pdesc': pdesc, 'flags': sorted(set(flags)), 'sub': si, 'cols': {k: round(v, 1) for k, v in cols.items()}})
    return out


# ---------------------------------------------------------------- GE 138T5502：燃機元件 → 撬上 JB 端子（一芯一列的向量表格）
CONN_COLS = ('rev', 'kks', 'ref111a', 'ge', 'desc', 'devterm', 'schem', 'hw', 'wire', 'cable', 'sig', 'ijb_loc', 'ijb', 'ijb_tb', 'ijb_term',
             'jb_loc', 'jb_desc', 'jb', 'jb_tb', 'jb_term', 'jumper')


def parse_conn(pdf_abs):
    """GE 138T5502「Turbine Connection Diagram」（MLI 0401；文件庫 HT0-1-GID01-D0003，Rev M AS-BUILT）→ [{CONN_COLS…, '_p', '_box'}]。
    欄界＝表頭下緣那排細長填色矩形的左右緣（21 欄 22 條界線；表頭沒有的續頁沿用上一頁）；列＝表頭以下、橫跨整張表的填色矩形（一芯一列）。
    _box＝這一列的框（PDF 座標；這份 /Rotate 0，與顯示座標相同）。"""
    import fitz
    doc = fitz.open(pdf_abs)
    rows, lastb, lasthb = [], None, 0.0
    for pno in range(1, doc.page_count + 1):
        pg = doc[pno - 1]
        xs, hdr_bot, cand = set(), 0.0, []
        for dr in pg.get_drawings():
            f = dr.get('fill')
            for it in dr['items']:
                if it[0] != 're':
                    continue
                r = it[1]
                if f and r.height < 1 and r.width > 10 and r.y0 < 60:
                    xs.add(round(r.x0))
                    xs.add(round(r.x1))
                if f and r.x0 < 35 and r.x1 > 960 and 2 < r.height < 80:
                    if f[0] < 0.3 and f[2] > 0.4:
                        hdr_bot = max(hdr_bot, r.y1)          # 深藍色表頭
                    else:
                        cand.append((round(r.y0, 1), round(r.y1, 1)))
        b = []
        for x in sorted(xs):
            if not b or x - b[-1] > 2:
                b.append(x)
        if len(b) != len(CONN_COLS) + 1:
            if lastb is None:
                continue
            b, hdr_bot = lastb, hdr_bot or lasthb
        lastb, lasthb = b, hdr_bot
        ws = pg.get_text('words')
        for y0, y1 in sorted({c for c in cand if c[0] >= hdr_bot - 1}):
            cells = {}
            for w in ws:
                wy, wx = (w[1] + w[3]) / 2.0, (w[0] + w[2]) / 2.0
                if y0 <= wy < y1:
                    for i in range(len(b) - 1):
                        if b[i] <= wx < b[i + 1]:
                            cells.setdefault(CONN_COLS[i], []).append((round(w[1], 1), w[0], w[4]))
                            break
            r = {k: ' '.join(t for _, _, t in sorted(v)) for k, v in cells.items()}
            if r.get('ge'):
                r.update({'_p': pno, '_box': [b[0], y0, b[-1], y1]})
                rows.append(r)
    doc.close()
    return rows


def jb_short(name):
    """接線圖表頭的 JB 名 'JB1T/G11MBY01XD102'、'JB637C-WL1/G11XBM01XD102' → 'JB1T'、'JB637C-WL1'；GE 表的 'JB1T N' → 'JB1T'。"""
    return re.sub(r'\s+N$', '', (name or '').split('/')[0].strip())


def jb_same(a, b):
    """接線圖的 JB 短名與 GE 表的 JB 名是不是同一個箱子（'JB637C-WL1' ＝ 'WL1'）。"""
    a, b = jb_short(a).upper(), jb_short(b).upper()
    return bool(a) and (a == b or a.endswith('-' + b) or b.endswith('-' + a))


def term_key(cell, hdr_tb=''):
    """JB 端子 → (端子排, 端子)：'TBA 13'、'TBB- 01' → ('TBA','13')、('TBB','1')；只有 '13' 時用表頭的端子排（表頭寫 'TBA/TBB' 這種就留空）。
    端子號去掉前導 0；比對時端子排空的那一邊不比。"""
    t = re.sub(r'\s+', ' ', (cell or '').strip())
    ht = re.sub(r'^[-\s:]+', '', hdr_tb or '').strip()        # 表頭 'TERMINAL NO.: - TBB'（G11 p.407）
    m = re.match(r'^(TB[A-Z0-9]*)\s*-?\s*(\S+)$', t)
    tb, term = (m.group(1), m.group(2)) if m else ((ht if re.fullmatch(r'TB[A-Z0-9]*', ht) else ''), t)
    if re.fullmatch(r'0+\d+', term):
        term = term.lstrip('0')
    return tb, term.upper()
