# -*- coding: utf-8 -*-
r"""tools/db/wire_epc.py — 接線路徑（KKS 版，v17）：HRSG、電氣 I&C、BOP 三份儀控電纜接線圖的頁面解析（wire_ge.py 的 build 用）。

為什麼另外一支：三份圖（HT1-1-ICE01-D1001 HRSG、D1002 電氣 I&C、D1003 BOP-WSC）與汽機 D1005 同一個試算表範本家族（現場框 → 現場電纜 →
JB 入線芯色 → JB 端子 → 出線芯色 → 幹線 → 盤側芯色 → 盤端子格），但欄位的 x 每份不同（D1001 現場芯色在 x≈304、D1003 在 x≈320），
JB 欄標頭寫法不同（'Junction Box No:'、'JUNCTION BOX/PANEL/MCC:'、'SWITCHGEAR/MCC:'），頁碼寫 '293 of 975'，元件身分寫在每個訊號格裡的
訊號 KKS（'=G11LBA30QM502XG01'、'C00BFT35QA601XB61'）。這裡不另寫一套解析：每頁先由芯色標籤的欄（x 群）推出欄帶，再把 wire_ge 的
欄帶、標頭規則與兩個配對函式暫時換成這一頁的（use_layout），呼叫同一個 wire_ge.parse_page。

== 欄帶（epc_layout）==
  芯色標籤（BK-1／WH／SH-3…）依 x 中心分欄（間距 > CORE_GAP 另起一欄）：x ≥ 590 第一欄＝盤側；它左邊 x ≥ 470 最右一欄＝JB 出線；
  再左邊 420～出線欄＝JB 入線；x < 420 最右一欄＝現場芯色。欄帶照欄的左右緣切：現場端子格在現場芯色左邊 40 pt、JB 端子在入線與出線之間
  （沒有入線欄＝元件畫在 JB 欄裡，端子格取出線欄左邊 42 pt）、盤端子格在盤側芯色右邊 38 pt（盤欄說明 'Unit 1 ST electronic…' 從 x≈690 起，
  寬一點會把它併進端子格）。圖區上界＝頁頂大字欄名（字高 ≥ 7.5 pt）的下緣；下界＝最低一個芯色標籤＋45 pt（圖框底部的版權字不收）。
== 與 D1005 不同的兩件事（use_layout 換掉的函式）==
  order_match_epc：芯色標籤畫在自己那一格的上緣、端子號在格子中間（低半格，D1001 約 13 pt、D1003 約 7.5 pt），照 D1005 的距離配整排會錯一格；
    先估這一欄「標籤 → 下一個端子號」的距離（中位數）把格子往上平移再配。
  lcs_pair_epc：兩端標籤各自唯一時先照標籤配——同一條電纜的芯在圖上可以交叉（D1002 p.13 WH-2／BK-2 上下對調），LCS 只能保持順序；
    剩下的才照原本 LCS＋夾縫補配（圖面標籤筆誤）。
  pick_all：盤側同一欄可以同時有帶號（BK-1）與不帶號（3C 電纜的 BR／BL）的芯（D1003 p.15 兩條電纜直拉到同一個盤），兩種都收。
  幹線、現場電纜號：'-WG-nnn' 之外還有 '-WD-nnn'（CAB_RE_EPC）。
== 元件身分（row_signals）==
  每個元件框裡，每個訊號格寫一個訊號 KKS（設備 KKS 13 碼＋'XB01'／'XG02'／'XQ01'／'AXG52'…），格子寫 'SPARE' 的是備用芯。
  每一條芯歸給同一個框裡 y 最近的那一格（訊號格或 SPARE）：r['sig']＝訊號 KKS、r['dev']＝設備 KKS（13 碼）。框裡沒有訊號格時用框的標頭
  （'G11LBA30QM502:IP Superheater Vent Valve'、'C10LAF31QM004/-SHUTOFF VALVE…'）。標頭與訊號格寫的設備不同（D1003 p.15 第二框標頭
  C10LAF31QM004、訊號格 =G11HAC31QM506XB61）以訊號格為準，另記 g['hdr_dev']（給 wire_ge 寫註記）。
  標頭照訊號格各自算（每一格取它上面最近的一行標頭）：框底下一行屬於下一個框的標頭（D1001 p.191 'G12LBA60QM406:…' 寫在 BP203 那一格下面）
  不算這一格的；說明裡括號中的 KKS（'LP PHOS FD PMP (G11QCC61GP601)'）是說明，不是標頭。
== 第一輪審查後補的（同一個 v17）==
  欄帶的左緣用向量框線：說明格的字會寫到端子格旁邊（'…Valve Open' 的 Open、'…Open Cmd' 的 Cmd 落在端子格左邊 40 pt 內），
    有框線時現場端子格（jbdev 是 JB 端子格）的左緣改取端子格那一欄的直線。
  芯色標籤正規化：'Bk-3'（小寫）→ BK-3；芯色欄裡的 'B-8' → BK-8（D1001 p.141～145、286～290 液位遠端顯示器頁，記成標籤筆誤）；端子格不再一行一格
    （'PL3'＋'1' 兩行是同一格，wire_ge.cells_of 照一般規則併行）；盤端子格的螺絲號離 'CA012-2C5B' 太遠（p.972）時併回上一格。
  溫度兩段頁（D1003 約 98 頁）：上段「FIELD (TEMPERATURE ELEMENT) → TEMPERATURE TRANSMITTER」＝熱電偶 → TC 補償導線 → 傳送器輸入端子，
    下段（左邊寫 TEMPERATURE TRANSMITTER、TRANSMITTER 或 FIELD(MOV/…)，沒有標題列的以最後一條補償導線下面的 'Junction Box No:'／'PANEL:' 為界）
    ＝傳送器 4–20 mA → 接線箱 → 盤。下段照一般頁解析，上段另抽成 p['sensors']（sensor_units），wire_ge 依設備 KKS 掛到下段的路徑上。
  電纜與幹線：現場電纜照現場芯色序列切（cable_runs）、幹線照 JB 出線芯色序列切（trunk_runs）——wire_ge 以電纜號 y 中點分段，號碼寫在一大條芯
    中間時會吃掉鄰居的芯；電纜號可帶尾字母（'-WG-002A'）。
== 第二輪審查後補的 ==
  一頁好幾個接線箱／端子排／盤框：header_cands 收整頁的標頭（標頭與值分在兩欄的 LCS 頁也認），panel_boxes 以框線切盤框；wire_ge 每條路徑取
    它自己那一組（D1002 p.145 PB1／PB2、D1003 p.787 上下兩個盤框）。
  帶訊號尾碼的盤／箱 KKS（'G11MSA30UC101DXG01'、'S10BKA10UC001XB01'、AGC 的 'C10AAF10UC101XQ01'）也是訊號來源；行首只有設備 KKS、沒有訊號
    尾碼的是標頭或圖說（'G11MAN30QN001 - JB' 是位置圖說，不是標頭）。框標頭與現場電纜號都寫另一個設備時，路徑照它們（p.20，r['sigdev'] 記訊號格寫的）。
  同一顆盤端子畫給兩條芯 → p['dup_cells']；設備說明（device_desc）取各訊號格共同的開頭，沒有就空。"""
import contextlib
import os
import re
from collections import Counter, defaultdict
from statistics import median

import wire_ge as W
import wire_gt as WG

EPC_DOCS = (('hrsg', 'HT1-1-ICE01-D1001', 'HRSG 儀控電纜接線圖'), ('elec', 'HT1-1-ICE01-D1002', '電氣 I&C 電纜接線圖'),
            ('bop', 'HT1-1-ICE01-D1003', 'BOP-WSC 儀控電纜接線圖'))
EPC_X = 890.0          # 圖區右界（標題欄與 NOTE 欄在 x ≥ 900）
CORE_GAP = 14.0        # 芯色標籤分欄：x 中心相距超過這個值另起一欄
FOOT_Y = 760.0         # 圖框底部的版權字在這以下
PDESC_X = 805.0        # 盤欄說明的右界（盤框右緣約 780～795；右邊是 REV 欄的版次框）
CAB_RE_EPC = re.compile(r'-W[A-Z]-\d+[A-Z]?$')                      # 'C30EKD30UC101-WG-002A'
HDR_JB_EPC = re.compile(r'^(?:JUNCTION BOX/PANEL/MCC|JUNCTION BOX NO|SWITCHGEAR/MCC|JUNCTION BOX/PANEL|JUNCTION BOX|BOX/PANEL|INSTRUMENT NO\.?|'
                        r'MCC/SWGR\.?(?:\s*NO\.?)?)\s*\.?\s*:?\s*(.*)$', re.I)   # 'MCC/SWGR NO.: =G11BFB30_A1_A1E'
HDR_TB_EPC = re.compile(r'^TERMINAL NO\.?\s*:?\s*(.*)$', re.I)
DEV_RE = re.compile(r'(?<![A-Z0-9])=?([A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})([A-Z]?X[A-Z]\d{2})?(?![A-Z0-9])')   # 設備 KKS 13 碼＋訊號尾碼
SIG_LINE_RE = re.compile(r'^=?([A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})([A-Z]?X[A-Z]\d{2}[A-Z]?)?$')   # 'G11MST10QC601XB11A'（同一訊號碼分 A～D）
SIG_GLUE_RE = re.compile(r'^=?([A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})([A-Z]?X[A-Z]\d{2})([A-Za-z].*)$')   # 訊號 KKS 與說明黏在一起：'=G11HSD10QM001XB61NH3'
ENCL_CODES = ('UC', 'XD', 'GD')                       # 盤、接線箱的設備碼：不是現場元件


def core_cols(ws, y0, y1=FOOT_Y):
    """芯色標籤依 x 中心分欄 → [{'ws', 'x0', 'x1', 'c'}…]（由左到右）。"""
    cs = sorted([w for w in ws if W.CORE_RE.match(w['t']) and y0 < w['y0'] < y1 and w['x1'] < EPC_X], key=lambda w: (w['x0'] + w['x1']) / 2)
    cols = []
    for w in cs:
        c = (w['x0'] + w['x1']) / 2
        if cols and c - cols[-1]['c1'] <= CORE_GAP:
            cl = cols[-1]
            cl['ws'].append(w)
            cl['c1'] = c
            cl['x0'], cl['x1'] = min(cl['x0'], w['x0']), max(cl['x1'], w['x1'])
        else:
            cols.append({'ws': [w], 'c1': c, 'x0': w['x0'], 'x1': w['x1']})
    for cl in cols:
        cl['c'] = sum((w['x0'] + w['x1']) / 2 for w in cl['ws']) / len(cl['ws'])
    return cols


def frame_edge(frames, x_core, y0, y1):
    """向量框線裡，芯色欄左邊 6～75 pt、在圖區 y 範圍內的直線（端子格那一欄的左緣）→ x；沒有回 None。
    同一個 x（±1 pt）的短線段加總長度 ≥ 15 pt 才算一條框線，取最靠近芯色欄的那一條。"""
    if not frames:
        return None
    acc = defaultdict(float)
    for x, a, b in frames.get('v') or []:
        if x_core - 75 < x < x_core - 6 and b > y0 and a < y1:
            acc[round(x)] += min(b, y1) - max(a, y0)
    xs = sorted(k for k, v in acc.items() if v >= 15)
    return float(xs[-1]) if xs else None


def epc_layout(ws, frames=None, top=None):
    """一頁（顯示座標的字）→ {'band', 'draw_y', 'panel_x', 'cols'}；不是接線頁回 None，接線頁但沒有芯／盤欄回 {'band': None, 'why'}。
    frames＝這一頁的向量框線（有就用 frame_edge 定端子格左緣）；top＝圖區上界（溫度兩段頁的下段從下段標題列起算）。"""
    if not W.sheet_no(ws)[0]:
        return None
    if top is None:
        big = [w for w in ws if w['y0'] < 160 and w['x1'] < EPC_X and (w['y1'] - w['y0']) >= 7.5]
        top = max((w['y1'] for w in big), default=60.0)
    cols = core_cols(ws, top + 1)
    if not cols:
        return {'band': None, 'why': 'no_cores'}
    pan = [c for c in cols if c['c'] >= 590]
    if not pan:
        return {'band': None, 'why': 'no_panel_col'}
    p = pan[0]
    left = [c for c in cols if c['c'] < p['c'] - 40]
    jo = next((c for c in reversed(left) if c['c'] >= 470), None)
    ji = next((c for c in reversed(left) if 420 <= c['c'] < jo['c'] - 10), None) if jo else None
    fld = next((c for c in reversed(left) if c['c'] < 420), None)
    ybot = min(FOOT_Y, max(w['y1'] for c in cols for w in c['ws']) + 45.0)
    B = {'pcore': (p['x0'] - 1.0, p['x1'] + 1.5)}
    B['pterm'] = (B['pcore'][1], B['pcore'][1] + 38.0)
    B['pdesc'] = (B['pterm'][1], EPC_X)
    if jo:
        B['jbcore'] = (jo['x0'] - 1.0, jo['x1'] + 1.5)
        B['trunk'] = (B['jbcore'][1], B['pcore'][0])
        if ji:
            B['jbin'] = (ji['x0'] - 1.0, ji['x1'] + 1.5)
            B['jbterm'] = (B['jbin'][1], B['jbcore'][0])
        else:
            fe = frame_edge(frames, jo['x0'], top, ybot)   # 元件畫在 JB 欄裡：說明格的 'Open Cmd' 會寫到端子格旁邊
            B['jbterm'] = (fe + 0.5 if fe else B['jbcore'][0] - 42.0, B['jbcore'][0])
            B['jbin'] = (B['jbterm'][0] - 20.0, B['jbterm'][0])
    else:                                                  # 直拉：JB 三個帶留成空帶
        B['jbcore'] = (B['pcore'][0] - 2.0, B['pcore'][0] - 1.0)
        B['trunk'] = (B['jbcore'][1], B['pcore'][0])
        B['jbin'] = (B['jbcore'][0] - 2.0, B['jbcore'][0] - 1.0)
        B['jbterm'] = (B['jbin'][1], B['jbcore'][0])
    if fld:
        B['fcore'] = (fld['x0'] - 1.0, fld['x1'] + 1.5)
        fe = frame_edge(frames, fld['x0'], top, ybot)
        B['fterm'] = (fe + 0.5 if fe else B['fcore'][0] - 40.0, B['fcore'][0])
        B['fcab'] = (B['fcore'][1], B['jbin'][0] if (jo and ji) else B['pcore'][0])
        B['fdesc'] = (90.0, B['fterm'][0])
    else:                                                  # 元件畫在 JB 欄裡（jbdev）：parse_page 取 fterm 左緣到 jbterm 之間的字當元件說明
        B['fterm'] = (150.0, 151.0)
        B['fcore'] = (151.0, 152.0)
        B['fcab'] = (152.0, B['jbin'][0])
        B['fdesc'] = (90.0, 150.0)
    return {'band': B, 'draw_y': (top + 1.0, ybot), 'panel_x': B['pcore'][0] - 40.0, 'cols': [round(c['c']) for c in cols]}


_order_match = W.order_match
_lcs_pair = WG.lcs_pair


def order_match_epc(labels, cells):
    """見檔頭：格子往上平移「標籤 → 下一個端子號」距離的中位數再照 wire_ge.order_match 配。"""
    if not labels or not cells:
        return _order_match(labels, cells)
    ys = sorted(c['y'] for c in cells)
    d = []
    for l in labels:
        nxt = [y for y in ys if y >= l['y0'] - 1.0]
        if nxt:
            d.append(nxt[0] - l['y0'])
    sh = median(d) if d else 0.0
    if sh < 2.0:
        return _order_match(labels, cells)
    return _order_match(labels, [dict(c, y=c['y'] - sh) for c in cells])


def lcs_pair_epc(a, b, key=lambda x: x):
    """見檔頭：兩端各自唯一的標籤先照標籤配，剩下的照 wire_gt.lcs_pair。→ [(i, j, how)]（i 由小到大）。"""
    ka, kb = [key(x) for x in a], [key(x) for x in b]
    if not any((k or '').startswith('SH') for k in kb) and any((k or '').startswith('SH') for k in ka):
        keep = [i for i, k in enumerate(ka) if not (k or '').startswith('SH')]   # 盤側沒畫屏蔽芯（接 IS／OS 排）：JB 側的 SH 不參加配對
        return [(keep[i], j, how) for i, j, how in lcs_pair_epc([a[i] for i in keep], b, key)]
    # 整排標籤一致地差一個號（D1003 p.732：JB 側 BK-10、WH-10、BK-11、WH-11，盤側 BK-11、WH-11、BK-12、WH-12）＝盤側整排標錯，照順序配
    # （照標籤配會把 BK-11 對到 BK-11、剩下的 BK-10 對到 BK-12，兩條芯都錯；照順序配與控制器組態一致）
    nl = lambda k: re.fullmatch(r'([A-Z]+)-(\d+)', k or '')   # noqa: E731
    ia, ib = [i for i, k in enumerate(ka) if nl(k)], [j for j, k in enumerate(kb) if nl(k)]
    if len(ia) == len(ib) >= 2:
        pa, pb = [nl(ka[i]) for i in ia], [nl(kb[j]) for j in ib]
        d = {int(y.group(2)) - int(x.group(2)) for x, y in zip(pa, pb)}
        if all(x.group(1) == y.group(1) for x, y in zip(pa, pb)) and len(d) == 1 and d != {0}:
            return [(i, j, 'gap') for i, j in zip(ia, ib)]
    jb = {k: j for j, k in enumerate(kb) if kb.count(k) == 1}
    out = [(i, jb[k], 'label') for i, k in enumerate(ka) if ka.count(k) == 1 and k in jb]
    da, db = {i for i, _j, _h in out}, {j for _i, j, _h in out}
    # 剩下的照標籤配好的幾對分段（只用上下順序一致的那幾對當界）各段自己配：D1003 p.819 盤側把 WH-1 印成 WH-2（WH-2 出現兩次），
    # 整排一起配會把 JB 側的 WH-2 配給第一個 WH-2；分段後 BK-1 與 BK-2 之間的 WH-1 ↔ 'WH-2' 照順序補配（標籤筆誤）
    anc = sorted((i, j) for i, j, _h in out)
    ln, prv = [1] * len(anc), [-1] * len(anc)          # j 遞增的最長子序列（交叉的那幾對不當界）
    for x in range(len(anc)):
        for y in range(x):
            if anc[y][1] < anc[x][1] and ln[y] + 1 > ln[x]:
                ln[x], prv[x] = ln[y] + 1, y
    lis, x = [], max(range(len(anc)), key=lambda t: ln[t]) if anc else -1
    while x >= 0:
        lis.append(anc[x])
        x = prv[x]
    lis.reverse()
    bounds = [(-1, -1)] + lis + [(len(a), len(b))]
    for (i0, j0), (i1, j1) in zip(bounds, bounds[1:]):
        ra = [i for i in range(i0 + 1, i1) if i not in da]
        rb = [j for j in range(j0 + 1, j1) if j not in db]
        if ra and rb:
            out += [(ra[i], rb[j], how) for i, j, how in _lcs_pair([a[i] for i in ra], [b[j] for j in rb], key)]
    return sorted(out)


def pick_all(ws):
    """見檔頭：帶號、不帶號的芯色都收（由上到下）。"""
    return sorted(ws, key=lambda w: w['y0'])


_cells_of = W.cells_of


_SKIP = set()


def cells_multi(ws, band, y_top, single=False):
    """見檔頭：EPC 圖的端子格一律照一般規則併行（'PL3'＋'1' 是同一格；'+'／'-'／端子號照 KEY_RE 自成一格）。
    現場端子格不收元件框標頭那一行的字（'G11HSD11QM002:Vaporization … Isolation Valve' 寫過端子欄，'Valve' 會被當成端子；_SKIP）。"""
    cells = _cells_of([w for w in ws if id(w) not in _SKIP] if band == 'fterm' and _SKIP else ws, band, y_top)
    if band != 'pterm':
        return cells
    out = []
    for c in cells:   # 盤端子格的螺絲號離 'CA012-2C5B' 那一行超過一般行距（D1003 p.972 約 15 pt）：併回上一格
        if out and re.fullmatch(r'\d{1,3}', c['t']) and re.fullmatch(r'CA\d{3}\s*-\s*\w+', out[-1]['t']) and c['y'] - out[-1]['y'] < 20:
            out[-1] = dict(out[-1], t=out[-1]['t'] + ' ' + c['t'], lines=out[-1]['lines'] + c['lines'], w=out[-1]['w'] + c['w'])
        else:
            out.append(c)
    return out


def header_words(ws, x_max):
    """元件框標頭的行（行首是設備 KKS 接 ':' 或 '/'，從說明欄起筆）→ 那幾行所有字的 id。"""
    out = set()
    for l in W.lines_of([w for w in ws if w['x1'] < EPC_X]):
        if l[0]['x0'] < x_max and re.match(r'^=?[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}\S*?[:/]', l[0]['t']):
            out |= {id(w) for w in l}
    return out


CORE_LOOSE = re.compile(r'^(?:BK|WH|RD|BU|BL|GN|YE|YL|OR|BR|BN|GY|VT|PK|PU|SH)-\d+$', re.I)


def norm_cores(ws):
    """見檔頭：芯色標籤正規化（大小寫 'Bk-3' → 'BK-3'）；回新的字串列（不改原字）。"""
    return [dict(w, t=w['t'].upper()) if w['t'] != w['t'].upper() and CORE_LOOSE.match(w['t']) else w for w in ws]


def norm_core_typos(ws, band):
    """芯色欄（現場、JB 入線／出線、盤側）裡缺一個字母的 'B-8' → 'BK-8'（D1001 液位遠端顯示器頁）。"""
    cb = [band[k] for k in ('fcore', 'jbin', 'jbcore', 'pcore') if k in band]
    return [dict(w, t='BK-' + w['t'][2:], orig=w['t']) if re.fullmatch(r'B-\d+', w['t']) and any(lo <= (w['x0'] + w['x1']) / 2.0 <= hi for lo, hi in cb)
            else w for w in ws]


@contextlib.contextmanager
def use_layout(lay, ws=None):
    """把 wire_ge 的欄帶、圖區、標頭規則、配對函式暫時換成這一頁的（單執行緒；離開時還原）。ws＝正規化過的這一頁的字（disp_words 改回它）。"""
    keep = (W.BAND, W.DRAW_Y, W.PANEL_X, W.DRAW_X, W.FIELD_REQUIRED, W.HDR_JB_RE, W.HDR_TB_RE, W.CAB_RE, W.order_match, W.pick_cores, WG.lcs_pair,
            W.cells_of, W.disp_words)
    W.BAND, W.DRAW_Y, W.PANEL_X, W.DRAW_X, W.FIELD_REQUIRED = lay['band'], lay['draw_y'], lay['panel_x'], EPC_X, False
    W.HDR_JB_RE, W.HDR_TB_RE, W.CAB_RE = HDR_JB_EPC, HDR_TB_EPC, CAB_RE_EPC
    W.order_match, W.pick_cores, WG.lcs_pair, W.cells_of = order_match_epc, pick_all, lcs_pair_epc, cells_multi
    if ws is not None:
        W.disp_words = lambda _pg: ws
        _SKIP.clear()
        _SKIP.update(header_words(ws, lay['band']['fterm'][0]))
    try:
        yield
    finally:
        _SKIP.clear()
        (W.BAND, W.DRAW_Y, W.PANEL_X, W.DRAW_X, W.FIELD_REQUIRED, W.HDR_JB_RE, W.HDR_TB_RE, W.CAB_RE, W.order_match, W.pick_cores,
         WG.lcs_pair, W.cells_of, W.disp_words) = keep


TT_TERM_RE = re.compile(r'^(?:[+-]|\d{1,2}(?:\([+-]\))?)$')       # 溫度兩段頁上段的端子：熱電偶側 '+'／'-'，傳送器側 '3(+)'／'2(-)'
HDR_LINE_RE = re.compile(r'^=?([A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})(?![0-9])')   # 元件框的標頭：行首就是設備 KKS（'G11LBA30QM502:IP …'）


def tt_split(ws):
    """溫度兩段頁（頁頂欄名有 'FIELD (TEMPERATURE ELEMENT)'）→ (上段起點 y, 下段標題列上緣 y, 下段標題列下緣 y)；不是回 None。"""
    big = [w for w in ws if w['x1'] < EPC_X and (w['y1'] - w['y0']) >= 7.5]
    ls = W.lines_of(big)
    t0 = next((l for l in ls if 'TEMPERATURE ELEMENT' in ' '.join(w['t'] for w in l)), None)
    if not t0:
        return None
    for l in ls:   # 下段標題列：左邊寫 'TEMPERATURE TRANSMITTER' 或只寫 'TRANSMITTER'（D1003 p.787），同一列有 'JUNCTION BOX'／'DCDAS PANEL'
        t = ' '.join(w['t'] for w in l)
        if l[0]['y0'] > t0[0]['y1'] + 20 and l[0]['x0'] < 420 and re.search(r'JUNCTION BOX|PANEL', t):   # 下段左邊也可能是 'FIELD(MOV/CV/LS-DI/DO)'（p.848）
            return max(w['y1'] for w in t0), min(w['y0'] for w in l), max(w['y1'] for w in l)
    te = [w for w in ws if re.search(r'_TE-W[A-Z]-\d+', w['t']) and w['x1'] < EPC_X]
    if te:                                     # 下段沒有標題列（D1003 p.744）：最後一條補償導線下面第一個 'Junction Box No:'／'PANEL:' 標頭之上切開
        y_te = max(w['y1'] for w in te)
        hd = [w for w in ws if w['y0'] > y_te + 10 and re.match(r'^(?:Junction|JUNCTION|PANEL)', w['t']) and w['x1'] < EPC_X]
        if hd:
            y = min(w['y0'] for w in hd) - 3.0
            return max(w['y1'] for w in t0), y, y
    return None


def header_cands(ws, lay):
    """整頁圖區裡的接線箱、端子排、盤標頭（不只第一條芯上面那一組）→ {'jb': [(y, 值)…], 'jb_tb': […], 'panel': […]}：一頁畫好幾個箱子、
    端子排或盤時（D1002 p.145 'TERMINAL NO.: GT11 PB1'／'PB2' 兩組按鈕盒），wire_ge 每條路徑取它第一條芯上面最近的那一個。
    標頭與值分在兩欄（'JUNCTION BOX/PANEL/MCC:'＋'G12HBK11GQ102 LCS_…'，D1001 p.292／293）時取同一行右邊那一段的 KKS。"""
    out = {'jb': [], 'jb_tb': [], 'panel': []}
    draw = [w for w in ws if lay['draw_y'][0] - 30 < w['y0'] < lay['draw_y'][1] and w['x1'] < EPC_X]
    sgs = []
    for sg in W.segs_of(draw):
        k = next((i for i, w in enumerate(sg) if i and w['t'] == 'TERMINAL' and i + 1 < len(sg) and sg[i + 1]['t'].upper().startswith('NO')), None)
        sgs += [sg[:k], sg[k:]] if k else [sg]
    for i, sg in enumerate(sgs):
        t, x, y = ' '.join(w['t'] for w in sg), sg[0]['x0'], sg[0]['y0']
        m = HDR_TB_EPC.match(t)
        if m:
            if 300 <= x < lay['panel_x']:
                out['jb_tb'].append((y, m.group(1).strip(' :')))
            continue
        m = W.HDR_PANEL_RE.match(t)
        if m and x >= lay['panel_x']:
            out['panel'].append((y, m.group(1).strip(' :')))
            continue
        m = HDR_JB_EPC.match(t)
        if m and x < lay['panel_x']:
            v = m.group(1).strip(' :').lstrip('.: ').lstrip('=- ')
            if not v:
                nx = sorted([s2 for s2 in sgs if s2 is not sg and abs(s2[0]['y0'] - y) < 2.5 and s2[0]['x0'] > sg[-1]['x1'] and s2[0]['x0'] < lay['panel_x']],
                            key=lambda s2: s2[0]['x0'])
                mk = re.match(r'^=?([A-Z]?\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3})', nx[0][0]['t']) if nx else None
                if mk:
                    v = mk.group(1)
            out['jb'].append((y, v))
    return out


def panel_boxes(p, ws, lay, frames):
    """盤欄有不只一個盤框（D1003 p.787：上面的框是 G12CCH02UC201 H12_RIO、下面的框是 G11CCH02UC201 H11_RIO，'PANEL:' 標頭只寫在上面那個）
    → p['panels']＝{框序: {'desc', 'kks'}}，每條芯多 r['pbox']（盤端子格所在的框）；只有一個框就不加。框由向量框線裡橫過盤欄說明的橫線切。"""
    B = lay['band']
    pw = [w for w in ws if B['pdesc'][0] <= (w['x0'] + w['x1']) / 2.0 < PDESC_X and lay['draw_y'][0] < w['y0'] < FOOT_Y
          and not re.fullmatch(r'[@#]?[A-Z]', w['t'])]
    if not frames or not pw:
        return
    xc = sorted((w['x0'] + w['x1']) / 2.0 for w in pw)[len(pw) // 2]
    cuts = sorted({round(y, 1) for y, x0, x1 in frames.get('h') or [] if x0 - 2 <= xc <= x1 + 2 and x1 - x0 > 30})
    if len(cuts) < 2:
        return
    box = lambda y: sum(1 for c in cuts if c <= y)   # noqa: E731
    blocks = defaultdict(list)
    for w in pw:
        blocks[box((w['y0'] + w['y1']) / 2.0)].append(w)
    used = {box(r['panel_cell']['y'] + 3.0) for r in p['rows'] if r.get('panel_cell')}
    blocks = {k: v for k, v in blocks.items() if k in used and re.search(r'[A-Z]?\d{2}C[A-Z]{2}\d{2}UC\d{3,4}', W.text_of(v))}
    if len(blocks) < 2:
        return
    p['panels'] = {}
    for k, v in blocks.items():
        t = W.text_of(v)
        mk = re.search(r'[A-Z]?\d{2}C[A-Z]{2}\d{2}UC\d{3,4}', t)
        p['panels'][k] = {'desc': t, 'kks': mk.group(0) if mk else ''}
    for r in p['rows']:
        if r.get('panel_cell'):
            r['pbox'] = box(r['panel_cell']['y'] + 3.0)


def sensor_units(ws, y0, y1, frames=None):
    """溫度兩段頁的上段（y0～y1）→ [{'te', 'te_desc', 'cable', 'spec', 'tt', 'tt_desc', 'cond': [[芯色, 熱電偶端子, 傳送器端子]…], 'box'}…]，
    一條補償導線（'…_TE-WG-001'）一組：左欄芯色（PU／RD）在熱電偶框旁、右欄在傳送器框旁，兩欄照上下順序配。"""
    seg = [w for w in ws if y0 < w['y0'] < y1 and w['x1'] < EPC_X]
    cols = core_cols(seg, y0, y1)
    if len(cols) < 2:
        return []
    lc, rc = cols[0], cols[-1]
    cabs = sorted([w for w in seg if CAB_RE_EPC.search(w['t']) and lc['x1'] < w['x0'] and w['x1'] < rc['x0']], key=lambda w: w['y0'])
    out = []
    for (lo, hi), c in zip(W.ranges([w['y0'] for w in cabs], y0, y1), cabs):
        uw = [w for w in seg if lo <= w['y0'] < hi]
        spec = [w for w in uw if abs((w['x0'] + w['x1']) / 2.0 - (c['x0'] + c['x1']) / 2.0) < 60 and c['y1'] - 1 < w['y0'] < c['y1'] + 9
                and not CAB_RE_EPC.search(w['t'])]
        fe = frame_edge(frames, lc['x0'], lo, hi) or lc['x0'] - 40.0
        lterm = [w for w in uw if fe <= w['x0'] and w['x1'] <= lc['x0'] + 1 and TT_TERM_RE.match(w['t'])]
        rterm = [w for w in uw if rc['x1'] - 1 <= w['x0'] and w['x1'] <= rc['x1'] + 40 and TT_TERM_RE.match(w['t'])]
        te_w = [w for w in uw if 90 <= w['x0'] and w['x1'] < fe - 0.5]
        tt_w = [w for w in uw if w['x0'] > rc['x1'] + 40 and w['x1'] < PDESC_X]   # 右邊 NOTE 欄的編號 '1.'、'2.' 不收
        te_t, tt_t = W.text_of(te_w), W.text_of(tt_w)
        mte = re.match(r'^=?([A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}\S*)\s*(.*)$', te_t)
        mtt = re.match(r'^=?([A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}\S*)\s*(.*)$', tt_t)
        lcs = sorted([w for w in lc['ws'] if lo <= w['y0'] < hi], key=lambda w: w['y0'])
        rcs = sorted([w for w in rc['ws'] if lo <= w['y0'] < hi], key=lambda w: w['y0'])
        near = lambda ts, y: min(ts, key=lambda t: abs(t['y0'] - y))['t'] if ts and min(abs(t['y0'] - y) for t in ts) < 14 else ''   # noqa: E731
        cond = [[a['t'], near(lterm, a['y0']), near(rterm, b['y0'])] for a, b in zip(lcs, rcs)]
        out.append({'te': mte.group(1) if mte else '', 'te_desc': mte.group(2) if mte else te_t, 'cable': c['t'], 'spec': W.text_of(spec),
                    'tt': mtt.group(1) if mtt else '', 'tt_desc': mtt.group(2) if mtt else tt_t, 'cond': cond, 'box': W.ubox(uw)})
    return out


def parse_page(pg, frames=None):
    """接線圖一頁（wire_ge 文字層快取的頁）→ wire_ge.parse_page 的結果（多 'lay'），每條芯多 sig／dev；不是接線頁回 None。
    frames＝這一頁的向量框線（wire_gt.page_frames：{'h': [[y, x0, x1]…], 'v': …}），有就用來定端子格左緣（epc_layout）、切訊號格（row_signals）。
    溫度兩段頁只解析下段（傳送器 → 盤），上段放 p['sensors']（sensor_units）。"""
    ws = norm_cores(W.disp_words(pg))
    tt = tt_split(ws)
    lay = epc_layout(ws, frames, top=tt[2] if tt else None)
    if lay is None:
        return None
    if not lay.get('band'):
        return {'sheet': W.sheet_no(ws)[0], 'of': W.sheet_no(ws)[1], 'h': {}, 'mode': '', 'groups': [], 'trunks': [], 'rows': [], 'pdesc': '',
                'flags': [lay['why']]}
    ws = norm_core_typos(ws, lay['band'])
    with use_layout(lay, ws):
        p = W.parse_page(pg)
        if p and p['rows']:
            trunk_runs(p)
            fill_panel_nolabel(p, ws, lay)
            p['hdr_cands'] = header_cands(ws, lay)
    if p is None or not p['rows']:
        return p
    p['lay'] = {'cols': lay['cols']}
    # 第一個元件框的標頭（'G11HAC31QM506:IP Economizer Vent Valve'）畫在第一條芯上面，parse_page 會把它當成 JB 說明：搬回第一個群組
    B = lay['band']
    y_top = min(r['core_w']['y0'] for r in p['rows'] if r.get('core_w')) - 1.5
    if p['groups'] and p['mode'] != 'jbdev':
        hw = [w for l in W.lines_of([w for w in ws if lay['draw_y'][0] < w['y0'] < y_top and 90 <= w['x0'] and w['x1'] <= B['fcab'][0] + 2])
              if not re.match(r'TERMINAL\s+NO', ' '.join(x['t'] for x in l), re.I) for w in l]   # 現場端子格的表頭 'TERMINAL NO. XK' 不是元件說明
        if hw:
            t = W.text_of(hw)
            if p['h'].get('jb_desc') and p['h']['jb_desc'] in t:
                p['h']['jb_desc'] = ''
            g0 = p['groups'][0]
            g0['desc_w'] = hw + g0['desc_w']
            g0['desc'] = (t + ' ' + g0['desc']).strip()
    if not p['h'].get('jb') and p['h'].get('jb_desc') and any(v_ and p['h']['jb_desc'].startswith(v_) for _y, v_ in p['hdr_cands']['jb']):
        v_ = next(v_ for _y, v_ in p['hdr_cands']['jb'] if v_ and p['h']['jb_desc'].startswith(v_))   # 標頭與值分在兩欄（LCS 頁）
        p['h']['jb'], p['h']['jb_desc'] = v_, p['h']['jb_desc'][len(v_):].strip(' :')
    if p['mode'] == 'jbdev' and p['groups'] and HDR_LINE_RE.match(p['h'].get('jb_desc') or '') \
            and HDR_LINE_RE.match(p['h']['jb_desc']).group(1)[8:10] not in ENCL_CODES:
        # 元件畫在 JB 欄裡（MCC 頁）：'G11HSD12CQ101:SCR Dilution Air Blower 1' 是元件框的標頭，不是 MCC 的說明（MCC 說明在電纜表）
        for sg in W.segs_of([w for w in ws if lay['draw_y'][0] < w['y0'] < y_top and w['x1'] < lay['panel_x']]):
            if ' '.join(w['t'] for w in sg) == p['h']['jb_desc']:
                g0 = p['groups'][0]
                g0['desc_w'] = sg + g0['desc_w']
                g0['desc'] = (p['h']['jb_desc'] + ' ' + g0['desc']).strip()
                p['h']['jb_desc'] = ''
                break
    p['h']['jb'] = (p['h'].get('jb') or '').lstrip('=- ')      # 'MCC/SWGR NO.: =G11BFB30_A1_A1E'、'JUNCTION BOX/PANEL/MCC: -C00EKB10UC101'
    # 盤欄說明（'G11CCH01UC201 H11_CONTRL Unit 1 ELECTRICAL ANNEX BUILDING EER'）：盤欄帶裡由上往下第一塊字，行距超過 40 pt 就停——
    # 右下角的版次表（'As Built Issue VK ST L Tai 23-12-2025 … DESCRIPTION BY CHK'）與它在同一個 x 範圍，不能一起收
    pw = [w for w in ws if B['pdesc'][0] <= (w['x0'] + w['x1']) / 2.0 < PDESC_X and y_top < w['y0'] < FOOT_Y   # 盤欄說明置中在整個盤框，可能比最後一條芯低很多
          and not re.fullmatch(r'[@#]?[A-Z]', w['t'])]   # 版次雲形框的字母（'C'、'@B'、'#B'）不收
    keep, last = [], None
    for l in W.lines_of(pw):
        if last is not None and l[0]['y0'] - last > 40:
            break
        keep += l
        last = l[0]['y0']
    p['pdesc'] = W.text_of(keep)
    if not p['h'].get('panel'):                                # 盤欄沒有 'PANEL:' 標頭（液位遠端顯示器 'G11HAD60CM025 LP DRUM LEVEL …'）：取說明開頭的 KKS
        m = re.match(r'^=?([A-Z]?\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3,4})\b', p['pdesc'])
        if m:
            p['h']['panel'] = m.group(1)
    for r in p['rows']:                                        # 盤側印 'B-8'（正規化成 BK-8 才配得上）：照標籤筆誤記
        pw_ = r.get('pcore_w') or {}
        if pw_.get('orig') and not r.get('ptypo'):
            r['ptypo'] = pw_['orig']
            p['flags'] = sorted(set(p['flags']) | {'label_typo:%s→%s' % (r['core'], pw_['orig'])})
    if p['mode'] == 'tb':
        cable_runs(p)
    panel_boxes(p, ws, lay, frames)
    row_signals(p, frames)
    seen_ = defaultdict(list)                                  # 同一顆盤端子畫給兩條芯（D1003 p.846 CA011-1B3A 13／14 給兩個設備、p.787 33 印兩次）
    for r in p['rows']:
        t_ = re.sub(r'\s+', '', W.ctext(r.get('panel_cell')))
        if r.get('dev') and re.match(r'^CA\d{3}-\w+\d+$', t_):
            seen_[t_].append('%s %s' % (r['dev'], r['core']))
    p['dup_cells'] = {k_: v_ for k_, v_ in seen_.items() if len(v_) > 1}
    if tt:
        p['sensors'] = sensor_units(ws, tt[0], tt[1], frames)
    return p


def fill_panel_nolabel(p, ws, lay):
    """盤側沒畫芯色標籤的一段（D1003 p.727 第二條幹線 C10LCM11UC151-WG-003 → CA017-1C4B 9／10）：同一條幹線裡沒配到盤端子的芯，
    與這條幹線範圍內沒有標籤、也沒被配走的盤端子格（'CA…'）數量相同時，照上下順序配（旗標 panel_nolabel；在 use_layout 裡呼叫）。"""
    miss_all = [r for r in p['rows'] if not r.get('panel_cell') and not r['core'].startswith('SH') and r.get('core_w')]
    if not miss_all:
        return
    draw = [w for w in ws if lay['draw_y'][0] < w['y0'] < lay['draw_y'][1] and w['x1'] < EPC_X]
    y_top = min(r['core_w']['y0'] for r in p['rows'] if r.get('core_w')) - 1.5
    cells = W.cells_of(draw, 'pterm', y_top)
    used = {(round(r['panel_cell']['y'], 1), r['panel_cell']['t']) for r in p['rows'] if r.get('panel_cell')}
    labs = [w for w in draw if W.inb(w, 'pcore') and W.CORE_RE.match(w['t'])]
    free = [c for c in cells if (round(c['y'], 1), c['t']) not in used and re.match(r'^CA\d{3}', c['t'])
            and not any(abs(l_['y0'] - c['y']) < 12 for l_ in labs)]
    fixed = []
    for ti in sorted({r.get('trunk') for r in miss_all}, key=lambda x: -1 if x is None else x):
        lo, hi = (p['trunks'][ti]['lo'], p['trunks'][ti]['hi']) if ti is not None and p['trunks'] else (y_top, lay['draw_y'][1])
        miss = sorted([r for r in miss_all if r.get('trunk') == ti], key=lambda r: r['core_w']['y0'])
        fc = sorted([c for c in free if lo <= c['y'] < hi], key=lambda c: c['y'])
        if miss and len(miss) == len(fc):
            for r, c in zip(miss, fc):
                r['panel_cell'] = c
                fixed.append(r['core'])
    if fixed:
        p['flags'] = sorted((set(p['flags']) - {'panel_unmatched:%s' % c for c in fixed}) | {'panel_nolabel:%s' % c for c in fixed})


def core_runs(rows, key):
    """一串芯（由上到下）照芯色標籤切段：標籤重複、號碼變小，或帶號／不帶號換了（3C 電纜的 BR／BL 接在 BK-n 後面）就是下一條電纜。"""
    runs, cur, seen, last, fam = [], [], set(), None, False
    for r in rows:
        fc = key(r) or ''
        m = W.CORE_RE.match(fc)
        if m:
            n = int(m.group(2)) if m.group(2) else None
            if cur and seen and (fc in seen or (n is not None and last is not None and n < last) or ((n is None) != fam)):
                runs.append(cur)
                cur, seen, last = [], set(), None
            seen.add(fc)
            fam = n is None
            if n is not None:
                last = n
        cur.append(r)
    if cur:
        runs.append(cur)
    return runs


def trunk_runs(p):
    """一頁不只一條幹線：wire_ge.parse_page 以幹線電纜號的 y 中點分段，號碼寫在一大條芯的中間時上一條的段會吃掉它的芯（D1003 p.727
    BL003 的 SH-12 被分到 WG-003、p.193 XB61 的 BK-1／BK-2 被分到 5C 的 WD-008）。照 JB 出線芯色序列切段，段數與幹線數相同就照順序配。"""
    if len(p['trunks']) < 2:
        return
    rows = sorted([r for r in p['rows'] if r.get('core_w') and r.get('trunk') is not None], key=lambda r: r['core_w']['y0'])
    runs = core_runs(rows, lambda r: r['core'])
    if len(runs) != len(p['trunks']):
        return
    for ti, run in enumerate(runs):
        for r in run:
            r['trunk'] = ti


def cable_runs(p):
    """tb 頁：現場電纜的芯色（現場側 BK-1、WH-1、BK-2…）每條電纜從頭編——照芯色序列切段（標籤重複或號碼變小就是下一條電纜），
    一段配一條電纜（照上下順序）。wire_ge.parse_page 以電纜號的 y 中點分群，8P 電纜的號碼寫在 16 條芯的中間，上一條 1P 電纜的群會吃掉
    它最上面幾條芯（D1001 p.191 G12LBA60QM406 的 BK-13／WH-13 被分到 G12HSD11BP203-WG-001）。段數與電纜數不同就不動。"""
    rows = sorted([r for r in p['rows'] if r.get('core_w') and (r.get('field_core') or r.get('jb_in') or r.get('field_cell'))],
                  key=lambda r: r['core_w']['y0'])                # JB 的備用端子（沒有現場那一側）：不跟任何一條電纜
    runs = core_runs(rows, lambda r: r.get('field_core') or r.get('jb_in'))   # 現場側標籤沒讀到時用 JB 入線標籤（D1003 p.848 BK-2 的 'BK-1'）
    cab = [gi for gi, g in enumerate(p['groups']) if g.get('cable')]
    if len(runs) < 2 or len(runs) != len(cab):
        return
    for gi, run in zip(cab, runs):
        for r in run:
            if r.get('group') != gi:
                r['group'] = gi
                r['regrouped'] = 1


SIG_TAIL_RE = re.compile(r'\s+(?:On|Off|Open|Close|Start|Stop|Interlock\s+Stop|Remote(?:\s+Trip)?)\s+(?:Cmd|Command)$|\s+(?:Open|Closed?)$|\s+CB\s+On$'
                         r'|\s+Available$|\s+Digital(?:\s+(?:Feedback|[Cc]ommand))?$|\s+Analog(?:\s+Input)?$|\s+Running$|\s+Fault$'
                         r'|\s+(?:CB\s+)?ON\s+Return$|\s+Remote\s+Trip\s+Cmd$', re.I)


def device_desc(boxes):
    """每條芯所在訊號格的全文（'=G11HSD12CQ101XB61 SCR Dilution Air Blower 1 On Cmd'…）→ 設備說明（KKS 編號卡的標題用）：去掉訊號 KKS 與 SPARE，
    幾格共同的開頭字（兩個字以上，'SHUTOFF VALVE AIR EJECTOR VACUUM PUMP' Closed／Open Cmd）；只有一格就去掉結尾的訊號用語
    （'… temperature Analog Input' → '… temperature'；'… Valve B Valve Open' 去 'Valve Open'，'… Vent Valve Open' 只去 'Open'）。"""
    ds = []
    for b in boxes:
        t = re.sub(r'(?<![A-Z0-9])=?[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}(?:[A-Z]?X[A-Z]\d{2}[A-Z]?)?(?![A-Z0-9])', ' ', b or '')
        t = re.sub(r'\s+', ' ', re.sub(r'\bSPARE\b', ' ', t)).strip(' :/-')
        if t and t not in ds:
            ds.append(t)
    if not ds:
        return ''
    if len(ds) > 1:
        wl = [[x for x in re.split(r'[\s_]+', d) if x] for d in ds]   # 'FAN(B) MOTOR_Local/Remote Select'：底線也是分隔
        n = 0
        while all(len(x) > n for x in wl) and len({x[n].upper() for x in wl}) == 1:
            n += 1
        if n >= 2:
            return ' '.join(wl[0][:n])
        return ''                                      # 幾格的說明沒有共同的開頭（'DCS Close Indication'／'DCS Open Command'）：不拿其中一格當設備說明
    d = ds[0]
    m = re.search(r'\s+Valve\s+(?:Open|Closed?)$', d, re.I)
    if m and len(re.findall(r'\bValve\b', d, re.I)) >= 2:
        return d[:m.start()]
    return SIG_TAIL_RE.sub('', d).strip(' -')


def dev_of(t):
    """一個字 → (設備 KKS 13 碼, 訊號尾碼)；盤／接線箱（設備碼 UC、XD、GD）與不是 KKS 的回 (None, None)。"""
    m = DEV_RE.search(t or '')
    if not m or m.group(1)[8:10] in ENCL_CODES:
        return None, None
    return m.group(1), m.group(2) or ''


def row_signals(p, frames=None):
    """見檔頭：每條芯 → r['sig']（訊號 KKS，沒有就 ''）、r['dev']（設備 KKS 13 碼；SPARE 格或認不出來的是 None）；
    每個群組多 g['devs']（框裡出現的設備，照順序）、g['hdr_dev']（框頂的標頭寫的設備）、g['hdr_desc']（標頭 KKS 後面的說明）；
    每條芯多 r['sdesc']（所在訊號格的說明，例 'IP Superheater Vent Valve Open'）、r['sbox']（那一格的全文）、
    r['hdr']（那一格上面最近的標頭：(設備 KKS, 說明, 整行字)；沒有是 ('', '', '')）。
    歸屬：有向量框線時，元件框裡橫跨說明欄的橫線把框切成一格一格（一個訊號格占兩條芯，MCC 頁的訊號字在格子上緣），芯歸給同一格的訊號字；
    那一格沒有訊號字（或沒有框線）才退回 y 最近的那一格（D1001 p.203：訊號字在上緣，照 y 最近會把 WH 芯歸到下一格）。"""
    allw = [w for g in p['groups'] for w in g['desc_w']]
    cuts = []
    if frames and allw:
        xc = sorted((w['x0'] + w['x1']) / 2.0 for w in allw)[len(allw) // 2]
        cuts = sorted({round(y, 1) for y, x0, x1 in frames.get('h') or [] if x0 - 2 <= xc <= x1 + 2 and x1 - x0 > 30})
    box = (lambda y: sum(1 for c in cuts if c <= y)) if len(cuts) >= 2 else None
    for gi, g in enumerate(p['groups']):
        anchors, first_hdr, cur = [], None, ('', '', '')
        for l in W.lines_of(g['desc_w']):
            t = ' '.join(w['t'] for w in l)
            y = (l[0]['y0'] + l[0]['y1']) / 2.0
            first = l[0]['t']
            m = SIG_LINE_RE.match(first) or SIG_GLUE_RE.match(first)
            if m and not m.group(2):
                m = None                                   # 行首只有設備 KKS（沒有訊號尾碼）是標頭或圖說，不是訊號格
            if m:                                          # 帶訊號尾碼的盤／箱 KKS 也是訊號來源（'G11MSA30UC101DXG01' IPB 溫度、'S10BKA10UC001XB01' 陰極防蝕盤）
                rest = ' '.join(([m.group(3)] if m.lastindex == 3 else []) + [w['t'] for w in l[1:]])
                anchors.append({'y': y, 'dev': m.group(1), 'sig': (m.group(1) + m.group(2)) if m.group(2) else '', 'desc': rest,
                                'tok': first, 'hdr': cur, 'gi': gi})
                continue
            if anchors and anchors[-1]['dev'] and not anchors[-1]['desc']:
                anchors[-1]['desc'] = t.strip()             # 訊號格的第二行（說明）
            if re.fullmatch(r'SPARE', t.strip(), re.I):
                anchors.append({'y': y, 'dev': None, 'sig': '', 'desc': '', 'tok': 'SPARE', 'hdr': cur, 'gi': gi})
                continue
            mh = HDR_LINE_RE.match(first)                  # 'G11LBA30QM502:IP …'、'C10LAF31QM004/-SHUTOFF …'、'C00BKA10QA112'（行首；括號裡的不算）
            if mh and re.match(r'^=?\S+\s*-\s*JB\b', t):
                mh = None                                  # 'G11MAN30QN001 - JB'：寫在框外的位置圖說（這幾顆裝在那個閥的接線箱），不是標頭
            if mh and mh.group(1)[8:10] not in ENCL_CODES:
                cur = (mh.group(1), re.sub(r'^=?[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}(?:\S*?[:/]-?)?\s*', '', t).strip(' :/-'), t.strip())   # 只有 KKS 的一行：說明空
                if first_hdr is None and not anchors:
                    first_hdr = cur
        if first_hdr is None and not anchors and cur[0]:
            first_hdr = cur
        g['hdr_dev'], g['hdr_desc'] = (first_hdr or ('', '', ''))[:2]
        g['devs'] = list(dict.fromkeys(a['dev'] for a in anchors if a['dev'])) or ([g['hdr_dev']] if g['hdr_dev'] else [])
        g['_anchors'] = anchors
    # 框線：橫跨元件說明欄（各群組說明字的 x 中心）的橫線把整欄切成一格一格；芯跟同一格的訊號字走（必要時改掛到那一格的群組：
    # jbdev 頁的群組原本以文字塊中點切，訊號字在格子上緣時下面那條芯會被切到下一個群組）
    every = [a for g in p['groups'] for a in g['_anchors']]
    for a in every:
        bw = [w for w in allw if box((w['y0'] + w['y1']) / 2.0) == box(a['y'])] if box else []
        a['text'] = W.text_of(bw) if bw else ' '.join(x for x in (a['tok'], a['desc']) if x)
    for gi, g in enumerate(p['groups']):
        for r in [r for r in p['rows'] if r.get('group') == gi]:
            if p['mode'] in ('tb', 'direct') and not (r.get('field_core') or r.get('jb_in') or r.get('field_cell')) \
                    and W.ctext(r.get('panel_cell')).upper() in ('', 'SPARE'):
                r['dev'], r['sig'], r['hdr'] = None, '', ('', '', '')   # JB 與盤之間的備用芯（沒有現場那一側、盤端子寫 SPARE）
                continue
            c = r.get('field_cell') or r.get('jb_cell') or {}
            y = (c.get('y') if c.get('y') is not None else r['core_w']['y0']) + 3.0
            same = [a for a in every if box(a['y']) == box(y)] if box else []
            if p['mode'] == 'tb' and same and any(a['gi'] == gi for a in same):
                same = [a for a in same if a['gi'] == gi]   # 有現場電纜的頁：同一格裡先取自己這條電纜（群組）的訊號字
            own = g['_anchors']
            if same:
                a = min(same, key=lambda a: abs(a['y'] - y))
                if a['gi'] != gi and p['mode'] == 'jbdev':    # 有現場電纜的頁群組＝電纜（cable_runs），不跟著訊號字搬
                    r['group'] = a['gi']
                    r['regrouped'] = 1
            elif own:
                a = min(own, key=lambda a: abs(a['y'] - y))
            else:
                r['dev'], r['sig'], r['sbox'] = g['hdr_dev'] or None, '', g['desc']
                r['hdr'] = (g['hdr_dev'], g['hdr_desc'], '')
                continue
            r['dev'], r['sig'], r['sdesc'], r['sbox'], r['hdr'] = a['dev'], a['sig'], a['desc'], a['text'], a['hdr']
            cab_ = (p['groups'][r['group']]['cable'] if r.get('group') is not None else '') or ''
            if a['dev'] and a['hdr'][0] and a['hdr'][0] != a['dev'] and cab_.startswith(a['hdr'][0] + '-W'):
                r['sigdev'] = a['dev']                 # 框標頭與現場電纜號都寫另一個設備：路徑照它們（訊號格多半是複製時沒改），訊號格寫的另記
                r['dev'] = a['hdr'][0]
    for g in p['groups']:
        g.pop('_anchors', None)
    for r in p['rows']:
        r.setdefault('dev', None)
        r.setdefault('sig', '')
        r.setdefault('hdr', ('', '', ''))
    return p


# ================================================================ v17：控制器 I/O（HRSG、BOP 的控制器）
KKS_CTRLS = ('H11', 'H12', 'BOPE1', 'BOPM1A', 'BOPM1B', 'WSC1', 'SAMP1', 'AGC1')
PANEL_KKS_RE = re.compile(r'[A-Z]?\d{2}C[A-Z]{2}\d{2}UC\d{3,4}')   # 'C10CCF01UC006'、'G11CCH02UC201'；圖上也有漏首碼的 '10CCF01UC007'、多一位的 'C00CCF01UC0018'


def io_index(path):
    """signal-atlas 控制器索引 → {'by_pos': {(控制器, 櫃, 板位, 螺絲號): [點…]}, 'by_pn': {(板位, 螺絲號): [(控制器, 櫃)…]},
    'by_dev': {(控制器, 模組, 板位, DeviceTag): [(點, 變數)…]}}（KKS_CTRLS；這幾台的 io_module.cabinet 是 'LU001'（兩櫃並列一組）或單櫃的
    'CA015'，與圖上的 CA 號不同，所以櫃照索引原樣記、對應另外算——assign_cab）。接線圖的盤端子格只寫 'CA002 -2D1B' 與螺絲號、沒有板名：
    鍵不含板名，點上帶 board。沒有索引回 None。"""
    if not path or not os.path.exists(path):
        return None
    import sqlite3
    c = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    q = ('select p.ctrl, m.name, m.cabinet, b.position_r, b.name, p.name, s.name, s.number, s.note, v.name, p.device_tag from io_point p '
         'join io_module m on m.id = p.module_id join io_board b on b.id = p.board_id left join io_screw s on s.point_id = p.id '
         'left join variable v on v.id = p.var_id where p.ctrl in (%s)' % ','.join('?' * len(KKS_CTRLS)))
    by_pos, by_pn, by_dev = defaultdict(list), defaultdict(list), defaultdict(list)
    for ctrl, mod, cab, pos, board, pt, sn, num, note, var, dt in c.execute(q, KKS_CTRLS):
        if not pos or '-' in pos:
            continue
        if num is not None:
            k = (ctrl, cab or '', pos, int(num))
            by_pos[k].append({'ctrl': ctrl, 'mod': mod, 'pt': pt, 'sn': sn, 'var': var or '', 'dt': dt or '', 'tb': '', 'board': board,
                              'cab': cab or '', 'note': note or ''})
            if (ctrl, cab or '') not in by_pn[(pos, int(num))]:
                by_pn[(pos, int(num))].append((ctrl, cab or ''))
        if dt:
            k2 = (ctrl, mod, pos, dt)
            if (pt, var or '') not in by_dev[k2]:
                by_dev[k2].append((pt, var or ''))
    c.close()
    return {'by_pos': dict(by_pos), 'by_pn': dict(by_pn), 'by_dev': dict(by_dev)}


def panel_key(w):
    """路徑的盤（標頭 'BOPE1_CNTRL/ C10CCF01UC006'、盤欄說明）→ 盤 KKS；寫不出 KKS 的用標頭原字。"""
    m = PANEL_KKS_RE.search('%s %s' % (w.get('panel') or '', w.get('panel_desc') or ''))
    return m.group(0) if m else (w.get('panel') or '').strip()


def ca_parts(c):
    """一條芯的盤端子 → (CA 號, 板位, 螺絲號) 或 None。"""
    m = re.match(r'^(CA\d{3})-(\w+)$', c.get('pos') or '')
    n = c.get('num') or ''
    return (m.group(1), m.group(2), int(n)) if m and n.isdigit() else None


def assign_cab(recs, ix, kinds):
    """盤（盤 KKS）＋圖上的 CA 號 → 索引裡的（控制器, 櫃）：每條芯的（板位, 螺絲號）在索引各櫃查，DeviceTag 就是這條路徑的設備的那一櫃得一票，
    同一個（盤, CA）取得票最多的；那個 CA 一票都沒有（圖上 CA 號筆誤、或芯都是備用點）就用同一面盤得票最多、有這個（板位, 螺絲號）的櫃。
    結果記在每條路徑的 r['_cab']＝{CA: (控制器, 櫃)}、r['ctl']＝控制器；索引查到的芯補上板名（c['board']）。→ {(盤, CA): (控制器, 櫃, 票數)}。"""
    votes = defaultdict(Counter)
    for plist in recs.values():
        for r in plist:
            if r['doc'] not in kinds:
                continue
            pn, dev = panel_key(r['wire']), r['tag']
            for c in r['cond']:
                cp = ca_parts(c)
                if not cp:
                    continue
                for cc in ix['by_pn'].get((cp[1], cp[2]), ()):
                    if any((h['dt'] or '').upper().startswith(dev) for h in ix['by_pos'][cc + (cp[1], cp[2])]):
                        votes[(pn, cp[0])][cc] += 1
    best = {k: v.most_common(1)[0] for k, v in votes.items()}
    per_panel = defaultdict(Counter)
    for (pn, _ca), v in votes.items():
        per_panel[pn].update(v)
    for plist in recs.values():
        for r in plist:
            if r['doc'] not in kinds:
                continue
            pn = panel_key(r['wire'])
            cabs, ctl = {}, Counter()
            for c in r['cond']:
                cp = ca_parts(c)
                if not cp:
                    continue
                if cp[0] not in cabs:
                    b = best.get((pn, cp[0]))
                    if b:
                        cabs[cp[0]] = b[0]
                    else:
                        cand = [cc for cc, _n in per_panel[pn].most_common() if cc + (cp[1], cp[2]) in ix['by_pos']]
                        if cand:
                            cabs[cp[0]] = cand[0]
                cc = cabs.get(cp[0])
                if cc:
                    ctl[cc[0]] += 1
                    hs = ix['by_pos'].get(cc + (cp[1], cp[2])) or []
                    if hs and not c['board']:
                        c['board'] = hs[0]['board']
            r['_cab'] = cabs
            if ctl:
                r['ctl'] = ctl.most_common(1)[0][0]
    return {k: (v[0][0], v[0][1], v[1]) for k, v in best.items()}


def io_lookup(ix, r, c):
    """一條芯的盤端子 → (候選點, how)；照 assign_cab 定的（控制器, 櫃）查（板位, 螺絲號）。"""
    cp = ca_parts(c)
    cc = (r.get('_cab') or {}).get(cp[0]) if cp else None
    if not cc:
        return [], ''
    return ix['by_pos'].get(cc + (cp[1], cp[2]), []), ''


# ================================================================ v17：電纜表（HRSG A1001、電氣 I&C A1002、BOP A1003）
CS_DOCS = (('cs1', 'HT1-1-ILE01-A1001'), ('cs2', 'HT1-1-ILE01-A1002'), ('cs3', 'HT1-1-ILE01-A1003'))
CS_CAB_RE = re.compile(r'^[A-Z0-9_]{5,}-W[A-Z]-\d+[A-Z]?$')
CS_ROOM_RE = re.compile(r'^(?:\d{2,3}[A-Z]{3}\d{2}(?:R\d{3})?\*?|-)$')       # '10UTG10R001*'（星號是表上的註記）、'11UHA02'（沒有房號）
CS_DEV_RE = re.compile(r'^[A-Z]\d{2}[A-Z]{3}\d{2}(?:[A-Z]{2}\d{2,4}[A-Z0-9_-]*|[_-][A-Z0-9_-]+)?(?:\([A-Za-z]+\))?$')   # 'G12BGA10-1B(Rear)'
CS_TYPE_RE = re.compile(r'^\d{1,3}[A-Z]{1,2}-\d+(?:\.\d+)?$')
CS_NUM_RE = re.compile(r'^\d+(?:\.\d+)?$')


def cable_schedule(tx):
    """EPC 儀控電纜表（一列一條電纜；欄序：序號、電纜號、房間 1、房間 1 說明、設備 1、說明、[ATEX 1]、房間 2、說明、設備 2、說明、[ATEX 2]、
    型式、外徑、長度、路由、參考圖、備註、版次）→ {電纜號: {r1, r1d, d1, d1d, r2, r2d, d2, d2d, type, len, page, box}}，與 wire_ge.cable_schedule
    同一套鍵（多 d1d／d2d 設備說明）。一列的第一行照字形認出房間碼（'12UHX10R405'，空白寫 '-'）、設備碼（'G11UHA02UC152'、'C10BBA10_3-1'、
    'G12BGA10-1B(Rear)'）、ATEX 欄 'NA'、型式 '24P-18'。
    列的範圍：以上下兩條電纜號的中點切——格子垂直置中，三行的房間說明第一行在電纜號那一行上面（A1001 p.8 'GT ELECTRICAL BUILDING-'）。
    欄的範圍：說明格照這一列的房間碼、設備碼、型式的 x 切；房間 2 的代碼空白時，用同一頁其他列的房間 2 欄位置（不然房間 2 的說明會併進設備 1 的說明）。
    長度欄的紅字追加（'47 + 280'）整串保留；型式收到外徑欄之前（'01P-16 AWG TC TYPE E'）。路由欄不收（多行、紅字刪改、跨列，讀不準）。"""
    out = {}
    for pno, pg in enumerate(tx['pg'], 1):
        ws = W.disp_words(pg)
        sect = {id(w) for sg in W.segs_of(ws) if sg[0]['x0'] > 300 and re.search(r'(?i)\b(?:cables|cable list)$', ' '.join(w['t'] for w in sg)) for w in sg}
        ws = [w for w in ws if id(w) not in sect]          # 分段標題列（'Instrument/Valves to DCS Cables'、'HRSG 11 Field I&C Cables'）不屬於上下任一列
        cabs = sorted([w for w in ws if CS_CAB_RE.match(w['t']) and w['x0'] < 130], key=lambda w: w['y0'])
        ycs = [(w['y0'] + w['y1']) / 2.0 for w in cabs]
        rows = []
        for i, cw in enumerate(cabs):
            yc = ycs[i]
            up = (yc - ycs[i - 1]) / 2.0 if i else None
            dn = (ycs[i + 1] - yc) / 2.0 if i + 1 < len(cabs) else None
            lo = yc - (up if up is not None else min(dn or 14.0, 14.0))
            hi = yc + (dn if dn is not None else min(up or 14.0, 14.0))
            rw = [w for w in ws if lo <= (w['y0'] + w['y1']) / 2.0 < hi and w['x0'] > cw['x1']]
            first = sorted([w for w in rw if abs(w['y0'] - cw['y0']) < 2.5], key=lambda w: w['x0'])
            if not any(CS_TYPE_RE.match(w['t']) for w in first):   # 型式寫在第二行（A1003 p.6 'G11LBA61UC151-WG-004' 的 4P-18 低 5 pt）
                first = sorted(first + [w for w in rw if CS_TYPE_RE.match(w['t']) and abs(w['y0'] - cw['y0']) < 8], key=lambda w: w['x0'])
            ty = next((j for j, w in enumerate(first) if CS_TYPE_RE.match(w['t'])), None)
            if ty is None:
                continue
            head = first[:ty]
            devs = [j for j, w in enumerate(head) if CS_DEV_RE.match(w['t']) and not CS_ROOM_RE.match(w['t'])]
            if len(devs) < 2:
                continue
            d1, d2 = devs[0], devs[-1]
            for dj in (d1, d2):                            # 設備欄寫成 'G11MST10 LCC'、'G11MST10 HVN LCC'（排的 KKS＋盤名縮寫）
                while re.fullmatch(r'[A-Z]\d{2}[A-Z]{3}\d{2}(?: HVN| LCC)*', head[dj]['t']) and dj + 1 < len(head) and head[dj + 1]['t'] in ('LCC', 'HVN'):
                    head[dj] = dict(head[dj], t=head[dj]['t'] + ' ' + head[dj + 1]['t'], x1=head[dj + 1]['x1'])
                    del head[dj + 1]
                    if dj < d2:
                        d2 -= 1
            rooms = [j for j, w in enumerate(head) if CS_ROOM_RE.match(w['t'])]   # 併完再取（併的時候刪了字，先取的位置會往後錯一個字）
            rows.append({'cw': cw, 'rw': rw, 'first': first, 'ty': ty, 'head': head, 'd1': d1, 'd2': d2, 'lo': lo, 'hi': hi,
                         'r1': next((j for j in rooms if j < d1), None), 'r2': next((j for j in rooms if d1 < j < d2), None)})
        xr2 = sorted(R['head'][R['r2']]['x0'] for R in rows if R['r2'] is not None)
        x_r2_page = xr2[len(xr2) // 2] if xr2 else None
        for R in rows:
            cw, rw, first, head, ty = R['cw'], R['rw'], R['first'], R['head'], R['ty']
            dw1, dw2 = head[R['d1']], head[R['d2']]
            codes = {id(head[j]) for j in (R['r1'], R['r2']) if j is not None}

            def span(lo_x, hi_x):
                t_ = W.text_of([w for w in rw if lo_x <= (w['x0'] + w['x1']) / 2.0 < hi_x and w['t'] != 'NA' and id(w) not in codes])
                return '' if t_ == '-' else t_
            na1 = next((w['x0'] for w in head if w['t'] == 'NA' and dw1['x1'] < w['x0'] < dw2['x0']), None)
            if R['r2'] is not None:
                x_r2 = head[R['r2']]['x0']
            elif x_r2_page is not None and dw1['x1'] < x_r2_page < dw2['x0']:
                x_r2 = x_r2_page
            else:                                          # 這一頁沒有房間 2 欄可參考：設備 1 之後第一個 NA 為界，沒有就整段算設備 1 的說明（舊做法）
                x_r2 = na1 if na1 is not None else dw2['x0']
            num = [j for j in range(ty + 1, len(first)) if CS_NUM_RE.match(first[j]['t'])]
            rec = {'page': pno, 'box': [cw['x0'] - 20, R['lo'], max(w['x1'] for w in rw), R['hi']],
                   'r1': head[R['r1']]['t'].rstrip('*') if R['r1'] is not None and head[R['r1']]['t'] != '-' else '',
                   'r1d': span(cw['x1'] + 0.5, dw1['x0'] - 0.5),
                   'd1': dw1['t'], 'd1d': span(dw1['x1'] + 0.5, min(x_r2, na1 if na1 is not None else x_r2) - 0.5),
                   'r2': head[R['r2']]['t'].rstrip('*') if R['r2'] is not None and head[R['r2']]['t'] != '-' else '',
                   'r2d': span(x_r2 - 0.5, dw2['x0'] - 0.5),
                   'd2': dw2['t'], 'd2d': span(dw2['x1'] + 0.5, first[ty]['x0'] - 0.5),
                   'type': span(first[ty]['x0'] - 0.5, (first[num[0]]['x0'] if num else first[ty]['x1'] + 60.0) - 0.5)}
            if len(num) >= 2:                              # 外徑、長度
                j = num[1]
                ln = first[j]['t']
                while j + 2 < len(first) and first[j + 1]['t'] == '+' and CS_NUM_RE.match(first[j + 2]['t']):
                    ln += ' + ' + first[j + 2]['t']
                    j += 2
                rec['len'] = ln
            out.setdefault(cw['t'], rec)
    return out


CS_XLSX = 'HT1-1-ILE01-A1003'                     # BOP 電纜表另有 xlsx（文件庫有 rev 0 與 rev 1；PDF 只有 rev 0）


def cable_xlsx(root, log=print):
    """文件庫裡 A1003 的 xlsx（檔名 'HT1-1-ILE01-A1003*.xlsx'，在第二層資料夾）取版次最高的一份 →
    {rel, rev, date, rows: {電纜號: {sr, r1, d1, r2, d2, type, len}}} 或 None。表頭那一列有 'Cable No.'；版次與日期在表頭上面兩列
    （'Revision : 1'、'Dated: 06-November-2025'）。只拿來說明「接線圖的電纜號不在電纜表 PDF 上、但在較新的 xlsx」，不取代 PDF 那一列
    （xlsx 沒有頁面可框、卡上的房間與長度仍照 PDF）。"""
    import glob
    try:
        import openpyxl
    except ImportError:
        log('（沒有 openpyxl：不讀 %s 的 xlsx）' % CS_XLSX)
        return None
    best = None
    for p in glob.glob(os.path.join(root, '*', '*', CS_XLSX + '*.xlsx')):
        try:
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        except Exception as e:                             # noqa: BLE001 — 打不開的副本跳過
            log('（%s 打不開：%s）' % (os.path.basename(p), e.__class__.__name__))
            continue
        try:
            for ws in wb.worksheets:
                rev, date, col, rows = None, '', None, {}
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    cells = ['' if c is None else str(c).strip() for c in row]
                    if col is None:
                        for c in cells:
                            m = re.match(r'(?i)revision\s*:\s*(\S+)', c)
                            if m:
                                rev = m.group(1)
                            m = re.match(r'(?i)dated\s*:\s*(.+)', c)
                            if m:
                                date = m.group(1).strip()
                        if 'Cable No.' in cells:
                            hd = {re.sub(r'\s+', ' ', c): j for j, c in enumerate(cells) if c}
                            g = lambda *ks: next((hd[k] for k in hd if any(k.startswith(x) for x in ks)), None)   # noqa: E731
                            col = {'sr': g('Sr.No'), 'cab': hd['Cable No.'], 'r1': g('Room Desig. 1'), 'd1': g('Device Ref 1'),
                                   'r2': g('Room Desig. 2 (to)'), 'd2': g('Device Ref 2'), 'type': g('Cable Type'), 'len': g('Designed Length')}
                        if i > 20 and col is None:
                            break
                        continue
                    cab = re.sub(r'\s+', '', cells[col['cab']]) if col['cab'] < len(cells) else ''
                    if CS_CAB_RE.match(cab):
                        rows.setdefault(cab, {k: (cells[j] if j is not None and j < len(cells) else '') for k, j in col.items() if k != 'cab'})
                if rows:
                    rk = int(rev) if rev and rev.isdigit() else -1
                    if best is None or rk > best[0]:
                        best = (rk, {'rel': os.path.relpath(p, root).replace(os.sep, '/'), 'rev': rev or '?', 'date': date, 'rows': rows})
                    break
        finally:
            wb.close()
    if best:
        log('電纜表 xlsx：%s（rev %s，%s）%d 條電纜' % (best[1]['rel'], best[1]['rev'], best[1]['date'], len(best[1]['rows'])))
    return best[1] if best else None


def cs_text_page(tx, cab):
    """電纜號在電纜表的文字層裡出現的頁（電纜號在表上分成幾格：'S10LBH30QN001 WG 001'）→ 頁碼或 None。用在「解析出的列裡沒有」時分辨
    是兩份文件不一致，還是那一列程式讀不到（A1005 p.7 最後一列在頁底被裁切）。"""
    rx = re.compile(r'(?<![A-Z0-9])' + r'\W*'.join(re.escape(t) for t in cab.split('-')) + r'(?![0-9])')
    for pno, pg in enumerate(tx['pg'], 1):
        if rx.search(' '.join(w['t'] for w in W.disp_words(pg))):
            return pno
    return None


# ================================================================ v17：儀器與接線箱位置圖（一號機 IIF01 系列）的位置標籤
LOC_DOCS = (('il1', 'HT1-1-IIF01-D0001', 'HRSG 輔助廠房'), ('il2', 'HT1-1-IIF01-D0002', '燃機室外輔助區'), ('il3', 'HT1-1-IIF01-D0003', '主管架'),
            ('jbloc', 'HT1-1-IIF01-D0004', '汽機房'), ('il5', 'HT1-1-IIF01-D0005', 'HRSG 區'), ('il6', 'HT1-1-IIF01-D0006', '氫氣／二氧化碳鋼瓶房'),
            ('il8', 'HT1-1-IIF01-D0008', '燃料氣處理區'))
LOC_KKS_RE = re.compile(r'^[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]?$')


def inst_lists(ws, hl=None):
    """位置圖一頁的儀器清單表（INSTRUMENT LIST：S.NO.｜INSTRUMENT RACK｜INSTRUMENT TAG NO｜SEC｜PID…，一頁可並排好幾塊）→ {儀器 KKS: (儀表架 KKS, 儀器那一格的框, 儀表架那一格的框)}。
    表頭第二行的 'RACK' 與 'TAG' 同一行、相距 60～120 pt 是一組；儀表架那一欄是合併格（字在幾列的中間）。hl＝這一頁的水平線（table_hlines）：
    有就用橫過儀表架欄的線切出合併格，儀器取同一格裡的儀表架（D0001 p.3 C10LAB42BP001 在 C10LAB42GZ002 那一格的第一列，照 y 最近會配到上一格
    的 C10LAB72GZ001）；沒有線或那一格沒有儀表架字才取 y 最近的，一樣近時取 KKS 前 8 碼（系統碼）相同的。"""
    out = {}
    racks_h = [w for w in ws if w['t'] == 'RACK']
    for rh in racks_h:
        th = next((w for w in ws if w['t'] == 'TAG' and abs(w['y0'] - rh['y0']) < 3 and 60 < w['x0'] - rh['x0'] < 120), None)
        if not th:
            continue
        rc, tx0 = (rh['x0'] + rh['x1']) / 2.0, th['x0']
        rk = [w for w in ws if LOC_KKS_RE.match(w['t']) and w['t'][8:10] == 'GZ' and abs((w['x0'] + w['x1']) / 2.0 - rc) < 45 and w['y0'] > rh['y1']]
        tg = [w for w in ws if LOC_KKS_RE.match(w['t']) and w['t'][8:10] != 'GZ' and tx0 - 30 < w['x0'] < tx0 + 60 and w['y0'] > rh['y1']]
        if not rk or not tg:
            continue
        cuts = sorted({round(y, 1) for y, x0, x1 in hl or () if x0 - 2 <= rc <= x1 + 2 and y > rh['y1']})
        cell = (lambda y: sum(1 for c in cuts if c <= y)) if len(cuts) >= 2 else None
        for t in tg:
            yc = (t['y0'] + t['y1']) / 2.0
            same = [r for r in rk if cell((r['y0'] + r['y1']) / 2.0) == cell(yc)] if cell else []
            if len(same) == 1:
                best = same[0]
            else:
                best = min(same or rk, key=lambda r: (round(abs((r['y0'] + r['y1']) / 2.0 - yc), 1), r['t'][:8] != t['t'][:8]))
                if abs((best['y0'] + best['y1']) / 2.0 - yc) > 80:
                    continue
            out.setdefault(t['t'], (best['t'], W.ubox([t], 1.5), W.ubox([best], 1.5)))
    return out


def table_hlines(pdf_abs, pno):
    """位置圖一頁的水平線段（顯示座標）→ [(y, x0, x1)…]（直線段與長方形的上下緣；儀器清單表的格線）。"""
    import fitz
    doc = fitz.open(pdf_abs)
    try:
        page = doc[pno - 1]
        M = page.rotation_matrix
        out = []
        for dr in page.get_drawings():
            for it in dr['items']:
                if it[0] == 'l':
                    a_, b_ = it[1] * M, it[2] * M
                    if abs(a_.y - b_.y) < 1.0 and abs(a_.x - b_.x) > 6:
                        out.append(((a_.y + b_.y) / 2.0, min(a_.x, b_.x), max(a_.x, b_.x)))
                elif it[0] == 're':
                    r = it[1] * M
                    r.normalize()
                    if r.x1 - r.x0 > 6:
                        out += [(r.y0, r.x0, r.x1), (r.y1, r.x0, r.x1)]
        return out
    finally:
        doc.close()


def loc_label_centered(ws, w):
    """W.loc_label 的補充：座標那一行比 KKS 寬、兩行置中對齊（D0004 p.4 'G11MAN30GZ003' 下一行 'E 4325000 N 4077600 U 10199' 從 KKS 左邊開始）
    → (標籤框, 座標字串) 或 None。下一行（14 pt 內）與 KKS 的水平範圍重疊、以 'E 數字' 開頭、有 'N 數字' 才算。"""
    ln = [x for x in ws if 0 < x['y0'] - w['y0'] <= 14 and x['x1'] > w['x0'] - 80 and x['x0'] < w['x1'] + 80]
    if not ln:
        return None
    y = min(x['y0'] for x in ln)
    line = sorted([x for x in ln if abs(x['y0'] - y) <= 2], key=lambda x: x['x0'])
    segs, cur = [], []
    for x in line:                                    # 同一行右邊緊鄰的另一個標籤（D0004 'E 4355700 N 4070700'）不收：取跨過 KKS 的那一段
        if cur and x['x0'] - cur[-1]['x1'] > 12:
            segs.append(cur)
            cur = []
        cur.append(x)
    if cur:
        segs.append(cur)
    line = next((sg for sg in segs if sg[0]['x0'] <= w['x1'] and sg[-1]['x1'] >= w['x0']), [])
    if not line:
        return None
    txt = ' '.join(x['t'] for x in line)
    if not re.match(r'^E\s?\d{6,}.*\bN\s?\d{6,}', txt):
        return None
    m = LOC_COORD_RE.match(txt)                       # 右邊緊鄰的另一個標籤（'… U 10199 E 4355700 N 4070700'）不收；儀表架標高寫 'D 1501'（D0004 p.3）
    if m and m.group(0) != txt:
        n = len(m.group(0).split())
        line, txt = line[:n], m.group(0)
    return W.ubox([w] + line), txt


LOC_COORD_RE = re.compile(r'^E\s?\d{6,}\s+N\s?\d{6,}(?:\s+[UD]\s?-?\d+)?')


def loc_label_left(ws, w):
    """W.loc_label（座標那一行與 KKS 左對齊）＋到標高為止：D0004 p.3 儀表架 C10LCB04GZ001 的下一行
    'E 4315624 N 4099480 D 1501' 右邊緊接 C10LCB05GZ001 的 'E 4318912 N 4099480'，整行收會多收鄰居的座標。"""
    nxt = sorted([x for x in ws if 0 < x['y0'] - w['y0'] <= 14 and abs(x['x0'] - w['x0']) <= 4], key=lambda x: x['y0'])
    line = sorted([x for x in ws if nxt and abs(x['y0'] - nxt[0]['y0']) <= 2 and x['x0'] >= w['x0'] - 4 and x['x0'] - w['x1'] < 120],
                  key=lambda x: x['x0'])
    txt = ' '.join(x['t'] for x in line)
    if not re.match(r'^E\s?\d{6,}', txt):
        return None
    m = LOC_COORD_RE.match(txt)
    if m and m.group(0) != txt:
        n = len(m.group(0).split())
        line, txt = line[:n], m.group(0)
    return W.ubox([w] + line), txt


def loc_labels(pdf_abs, tx, want=None):
    """位置圖整份 → ({KKS: [{page, label, coords, sym}…]}, {儀器 KKS: {page, rack, tag_box, rack_box}})：KKS 字的下一行是廠區座標（W.loc_label）
    就是位置標籤（接線箱、儀表架 GZ；儀器本身多半不在平面上標，而是列在同一張圖的儀器清單表、寫它裝在哪個儀表架——inst_lists）；
    有標籤的頁才抽一次向量，沿藍色引線找紅色符號（W.jb_walk；不是紅框時 sym＝None，只框標籤）。want＝只要這些 KKS（None＝全部）。"""
    out, inst = defaultdict(list), {}
    for pno, pg in enumerate(tx['pg'], 1):
        ws = W.disp_words(pg)
        hl = None
        if any(w['t'] == 'RACK' for w in ws):
            try:
                hl = table_hlines(pdf_abs, pno)
            except Exception:                              # noqa: BLE001 — 抽不到向量就照 y 最近
                hl = None
        for t_, (rk_, tb_, rb_) in inst_lists(ws, hl).items():
            inst.setdefault(t_, {'page': pno, 'rack': rk_, 'tag_box': tb_, 'rack_box': rb_})
        labs = []
        for w in ws:
            if LOC_KKS_RE.match(w['t']) and (want is None or w['t'] in want):
                hit = loc_label_centered(ws, w) or loc_label_left(ws, w)   # 先取跨過 KKS 的那一段（右邊緊鄰別的標籤時 W.loc_label 會多收 'E'）
                if hit:
                    labs.append((w['t'], hit))
        if not labs:
            continue
        try:
            segs, red = W.jb_segments(pdf_abs, pno)
        except Exception:                                  # noqa: BLE001 — 抽不到向量就只框標籤
            segs, red = [], []
        for k, (lab, txt) in labs:
            out[k].append({'page': pno, 'label': lab, 'coords': txt, 'sym': W.jb_walk(lab, segs, red) if segs else None})
    return dict(out), inst
