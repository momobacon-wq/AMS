# -*- coding: utf-8 -*-
r"""tools/db/wire_cov.py — 每個元件端子表的訊號畫到迴路圖了沒（v19）：DCS 端子表 HT1-1-IMI01-A0001（IO_Signal）逐列對接線路徑。

為什麼：端子表（設計文件）與接線圖（竣工圖）是兩份來源，卡片上列 5 個訊號、迴路圖只畫 3 個時，讀的人要知道是哪 2 個、為什麼——是畫在別的文件、
文件庫沒有芯線級的圖，還是端子表的舊列（控制器組態也沒有這個點）。這裡不補線，只比對與分類；沒有畫的訊號不會出現在迴路圖上。

比對（每列用 SIGNAL_NAME，SPARE 不算）：
  drawn：訊號名在 wire_kks.json／wire_ge.json 的某條芯上（cond.sig）。
  alt：  訊號名不在，但同一個控制器的（盤-板位, 端子）有芯——圖上寫別的訊號名（盤對盤的另一端名稱、竣工改名，或那組螺絲畫的是別的訊號）；alt 列出圖上寫的名稱，不判定是不是同一個訊號。
  miss： 都沒有。變數＝signal-atlas 控制器索引這一組螺絲上的變數（空＝這組螺絲組態沒有變數；同名變數可能在別的地方）；
         原因來自 ge_tags_dir 的 wire_gaps.json（不進 repo；{訊號: [類別, 出處, 說明]}，人工查證：哪份文件有畫、還是查無），沒有記載的類別是 'unk'。
輸出 cardwork/wire_cov.json：by_dev={元件: {n, m, alt: [[訊號, [圖上名稱…], 盤端子]…], miss: [[訊號, 說明, 控制器, 盤-板位, 點, 卡別, 端子, 變數, 類別, 出處, 說明]…]}}；
元件＝FLD_DEV（空的用 SIGNAL_NAME）；kids＝{設備 KKS: [它底下帶字母尾碼的元件…]}（'G11MSA30GH001' ← 'G11MSA30GH001A'：接線圖的鍵是 13 碼的設備）。
build_card_aux 依元件（KKS）接到卡片的 cv。drawn 只比訊號名：名字在別的控制器或別的端子上也算畫出（路徑自己的 ✗ 與註記會講）。

用法：py tools/db/wire_cov.py [--out X] [--dcdas X] [--gaps X]
"""
import argparse
import glob
import io
import json
import os
import re
import sqlite3
import sys
import warnings
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pid_index as PI  # noqa: E402

warnings.filterwarnings('ignore')
import openpyxl  # noqa: E402

import docmap_terminal as T  # noqa: E402

DOC = 'HT1-1-IMI01-A0001'
GENERATED_BY = 'tools/db/wire_cov.py'
KEEP = ('SIGNAL_NAME', 'FLD_DEV', 'DESC', 'CONTROLLER', 'CABINET', 'CASE', 'COL_ROW', 'POINT', 'PACK_TYPE', 'TB_PT_1', 'TB_PT_2')


def design_rows(root):
    """最新版的端子表（選版規則同 docmap_terminal：CoverSheet 最大 Rev、同版取修改時間新者）→ (版次, 檔名, [列…])。"""
    best = None
    for p in glob.glob(os.path.join(root, '**', '*IMI01-A0001*.xlsx'), recursive=True):
        if not os.path.basename(p).startswith(DOC):
            continue
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        rev = T.cover_info(wb)[0]
        ok = 'IO_Signal' in wb.sheetnames
        wb.close()
        k = (rev if rev is not None else -1, os.path.getmtime(p))
        if ok and (best is None or k > best[0]):
            best = (k, p)
    if best is None:
        sys.exit('找不到 %s 的 xlsx（文件庫：%s）' % (DOC, root))
    wb = openpyxl.load_workbook(best[1], read_only=True, data_only=True)
    rows = wb['IO_Signal'].iter_rows(values_only=True)
    hdr = [T.s(h) for h in next(rows)]
    H = {h: i for i, h in enumerate(hdr) if h}
    next(rows)                                 # 第 2 列是欄位說明
    out = []
    for r in rows:
        d = {k: T.s(r[H[k]]) if k in H and H[k] < len(r) else '' for k in KEEP}
        if d['SIGNAL_NAME'] and 'SPARE' not in d['SIGNAL_NAME'].upper():
            out.append(d)
    wb.close()
    return best[0][0], os.path.basename(best[1]), out


def wire_index(fns):
    """接線路徑 → (訊號集合, {(控制器, 盤-板位, 端子號): {圖上的訊號名}})。"""
    sig, pos = set(), defaultdict(set)
    for fn in fns:
        for pl in json.load(open(fn, encoding='utf-8'))['paths'].values():
            for p in pl if isinstance(pl, list) else [pl]:
                for c in p.get('cond') or []:
                    if c.get('sig'):
                        sig.add(c['sig'].upper())
                    if c.get('pos') and c.get('num'):
                        pos[(p.get('ctl') or '', c['pos'], str(int(c['num'])) if c['num'].isdigit() else c['num'])].add((c.get('sig') or '').upper())
    return sig, pos


def live_vars(path):
    """控制器組態：{(控制器, 櫃, 板位, 螺絲號): 變數}（只收有螺絲的點；櫃是 io_module.cabinet，與端子表的 CABINET 同一種寫法）。"""
    c = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    q = ('select p.ctrl, m.cabinet, b.position_r, s.number, v.name from io_point p join io_module m on m.id = p.module_id join io_board b on b.id = p.board_id '
         'join io_screw s on s.point_id = p.id left join variable v on v.id = p.var_id where s.number is not null')
    out = {}
    for ctrl, cab, pos, num, var in c.execute(q):
        if pos and '-' not in pos:
            k = (ctrl, cab or '', pos, int(num))
            out[k] = out.get(k) or var or ''
    c.close()
    return out


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    gdir = os.path.dirname(paths.GE_TAGS or '.')
    ap = argparse.ArgumentParser(description='端子表訊號對接線路徑（見檔頭 docstring）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT)
    ap.add_argument('--wire-ge', default=os.path.join(paths.CARDWORK, 'wire_ge.json'))
    ap.add_argument('--wire-kks', default=os.path.join(paths.CARDWORK, 'wire_kks.json'))
    ap.add_argument('--dcdas', default=paths.DCDAS_INDEX)
    ap.add_argument('--gaps', default=os.path.join(gdir, 'wire_gaps.json'), help='人工查證的原因表（預設 ge_tags.json 同目錄的 wire_gaps.json；不進 repo；沒有就全部 unk）')
    ap.add_argument('--out', default=os.path.join(paths.CARDWORK, 'wire_cov.json'))
    a = ap.parse_args()
    rev, fname, rows = design_rows(a.library)
    sig, pos = wire_index((a.wire_ge, a.wire_kks))
    live = live_vars(a.dcdas) if os.path.exists(a.dcdas) else {}
    gaps = json.load(open(a.gaps, encoding='utf-8')) if os.path.exists(a.gaps) else {}
    by, st = {}, Counter()
    for r in rows:
        sn = r['SIGNAL_NAME'].upper()
        dev = (r['FLD_DEV'] or sn).upper()
        e = by.setdefault(dev, {'n': 0, 'm': 0, 'alt': [], 'miss': []})
        e['n'] += 1
        st['signals'] += 1
        tbs = [x for x in (r['TB_PT_1'], r['TB_PT_2']) if x]
        where = '%s-%s' % (r['CASE'], r['COL_ROW'])
        if sn in sig:
            e['m'] += 1
            st['drawn'] += 1
            continue
        hit = {x for n in tbs for x in pos.get((r['CONTROLLER'], where, n), ()) if x}
        if any((r['CONTROLLER'], where, n) in pos for n in tbs):
            e['alt'].append([sn, sorted(hit), '%s %s' % (where, '／'.join(tbs))])
            st['alt'] += 1
            continue
        var = next((live[k] for k in ((r['CONTROLLER'], r['CABINET'], r['COL_ROW'], int(n)) for n in tbs if n.isdigit()) if live.get(k)), '')
        g = gaps.get(sn) or ['unk', '', '']
        e['miss'].append([sn, r['DESC'], r['CONTROLLER'], where, r['POINT'], r['PACK_TYPE'], '／'.join(tbs), var] + g)
        st['miss'] += 1
        st['miss_' + g[0]] += 1
        st['miss_live' if var else 'miss_novar'] += 1
    st['devices'] = len(by)
    st['devices_all_drawn'] = sum(1 for e in by.values() if e['m'] == e['n'])
    st['devices_alt'] = sum(1 for e in by.values() if e['alt'] and not e['miss'])
    st['devices_some'] = sum(1 for e in by.values() if 0 < e['m'] + len(e['alt']) and e['miss'])
    st['devices_none'] = sum(1 for e in by.values() if not e['m'] and not e['alt'])
    kids = defaultdict(list)
    for dev in sorted(by):
        if re.fullmatch(r'[A-Z]\d{2}[A-Z]{3}\d{2}[A-Z]{2}\d{3}[A-Z]', dev):
            kids[dev[:13]].append(dev)
    out = {'kind': 'wire_cov', 'generated_by': GENERATED_BY, 'doc': DOC, 'rev': rev, 'file': fname, 'by_dev': dict(sorted(by.items())), 'kids': dict(kids), 'stats': dict(st)}
    n = PI.write_json(a.out, out, 'wire_cov.json')
    print('寫出 %s（%.2f MB）；端子表 %s Rev.%s：%s' % (os.path.basename(a.out), n / 1048576.0, DOC, rev, dict(sorted(st.items()))))


if __name__ == '__main__':
    main()
