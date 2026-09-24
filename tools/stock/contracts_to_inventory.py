# -*- coding: utf-8 -*-
"""採購規範 .docx → 試算表「物料管理系統」Inventory 分頁匯入檔（A–L 欄）。

  py tools/stock/contracts_to_inventory.py 合約1.docx [合約2.docx …] [--current 現行Inventory.csv] [--qty contract|current]
                                           [--out inventory_import.csv] [--sql import.sql]
  py tools/stock/contracts_to_inventory.py --from-json tools/stock/mock_inventory.json --sql worker/mock_import.sql   # 假資料 → 本機 D1

- 每份 .docx 的 word/document.xml 逐段解析：「<廠牌>傳送器(料號: CRxxxxxxxxx)」開頭一項，接著「型號:」「測量範圍:」「數量:N只」等鍵值列
  （半形／全形冒號與括號皆接受）。料號 CR… 是唯一鍵；型號、數量缺一即報錯。
- --current：目前 Inventory 匯出的 CSV（PartNumber,Name,Brand,Spec,Location,Quantity[,…]）。現行列序＝合約順序，且 PartNumber 是
  完整型號的前綴（Rosemount 前 12 碼）；逐列對齊後帶入 Location，並列出與合約數量不同、或前綴對不上的列。
- --qty：contract（預設，數量＝合約數量）或 current（沿用 --current 的現行數量）。
- --out CSV 欄：PartNumber(=料號), Name(=完整型號), Brand, Spec, Location, Quantity, Protocol, Family, Contract, ContractQty, MinQty, Note
  （A–F 與 Transmitter 網站相容；試算表「Import」分頁＋Apps Script migrateFromImport() 用）。
- --sql：D1 匯入檔（items INSERT ＋ 每料號一列 ledger IMPORT），`npx wrangler d1 execute ams-stock --remote --file import.sql`（見 worker/README）。
"""
import argparse
import csv
import datetime
import io
import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ITEM_RE = re.compile(r'^(.*?)\s*[\(（]\s*料號\s*[:：]\s*([A-Z]{1,3}\d{6,12})\s*[\)）]')
KV_RE = re.compile(r'^(型號|測量範圍|量測範圍|溫度範圍|範圍|數量|Pressure range|Sensor Type|感測器型式|Model|Base model|傳送器輸出|Transmitter output|Signal output|Outputs?|輸出)\s*[:：]\s*(.*)$', re.I)
# 系列鍵：與 docs/assets/stock.js 的 FAMILY_RULES 一致（正規化後比對）
FAMILY_RULES = [
    r'^3051S', r'^3051[CLT][A-Z]?', r'^2051[CT][A-Z]?', r'^2088[AG]', r'^644', r'^848T', r'^5408', r'^8732E', r'^214C',
    r'^PMD75', r'^PMP71', r'^TMT82',
]
CONTRACT_SHORT = [  # 合約標題關鍵字 → 簡稱
    ('氣渦輪機', 'GT/HRSG/ST 傳送器'),
    ('蒸汽側', 'HRSG 蒸汽側傳送器'),
]


def norm_code(s):
    return re.sub(r'[\s\-_/]', '', str(s or '').upper())


def family(model):
    n = norm_code(model)
    for r in FAMILY_RULES:
        m = re.match(r, n)
        if m:
            return m.group(0)
    return n[:5]


def doc_lines(path):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read('word/document.xml'))
    out = []
    for p in root.iter(W + 'p'):
        t = ''.join(x.text or '' for x in p.iter(W + 't')).strip()
        if t:
            out.append(t)
    return out


def parse_doc(path):
    lines = doc_lines(path)
    title = lines[0] if lines else path
    short = next((s for k, s in CONTRACT_SHORT if k in title), title[:20])
    items, cur = [], None
    for ln in lines:
        m = ITEM_RE.match(ln)
        if m:
            brand_line = m.group(1).strip()
            brand = 'Endress+Hauser' if 'Endress' in brand_line else ('Rosemount' if 'Rosemount' in brand_line else re.sub(r'傳送器.*$', '', brand_line))
            cur = {'mat': m.group(2), 'brand': brand, 'model': '', 'range': '', 'qty': None, 'sensor': '', 'desc': '', 'output': '', 'extra': []}
            items.append(cur)
            continue
        if cur is None:
            continue
        m = KV_RE.match(ln)
        if not m:
            if ln.startswith(('交貨', '驗收', '保固', '付款', '罰則', '終止')):
                cur = None
            else:
                cur['extra'].append(ln)
            continue
        k, v = m.group(1), m.group(2).strip()
        if k == '型號':
            cur['model'] = v
        elif k == '數量':
            cur['qty'] = int(re.sub(r'\D', '', v) or 0)
        elif k in ('測量範圍', '量測範圍', '溫度範圍', '範圍') or k.lower() == 'pressure range':
            cur['range'] = v
        elif k.lower() == 'sensor type' or k == '感測器型式':
            cur['sensor'] = v
        elif k.lower() in ('model', 'base model'):
            cur['desc'] = v
        else:
            cur['output'] += ' ' + v
    for it in items:
        it['contract'] = short
        if not it['model'] or it['qty'] is None:
            raise SystemExit(f"{it['mat']}: 缺型號或數量（{path}）")
        blob = ' '.join([it['output']] + it['extra']).upper()
        it['proto'] = 'FF' if re.search(r'FOUNDATION|FIELDBUS|\bFF\b', blob) else ('HART' if 'HART' in blob else '')
        spec = it['range']
        if not spec and it['sensor']:
            spec = re.sub(r'^Thermocouple\s*', '', re.sub(r',?\s*IEC\s*584.*$', '', it['sensor'])).strip()
        if not spec and it['desc']:
            spec = re.sub(r'\s*-\s*Field Mount$', '', it['desc']).strip()
        it['spec'] = spec
    return items


def sql_str(v):
    return "'" + str('' if v is None else v).replace("'", "''") + "'"


def write_sql(path, rows, ts):
    """rows: dict(pn, model, brand, spec, loc, qty, proto, family, contract, cqty, min, note) → items INSERT ＋ ledger IMPORT"""
    out = ['-- 由 tools/stock/contracts_to_inventory.py 產生；npx wrangler d1 execute ams-stock --remote --file ' + os.path.basename(path)]
    for r in rows:
        cq = 'NULL' if r.get('cqty') is None else int(r['cqty'])
        mn = 'NULL' if r.get('min') in (None, '') else int(r['min'])
        out.append('INSERT INTO items (pn, model, brand, spec, loc, qty, proto, family, contract, cqty, min_qty, note, updated_at) VALUES ('
                   + ', '.join([sql_str(r['pn']), sql_str(r['model']), sql_str(r.get('brand')), sql_str(r.get('spec')), sql_str(r.get('loc')), str(int(r['qty'])),
                                sql_str(r.get('proto')), sql_str(r.get('family')), sql_str(r.get('contract')), str(cq), str(mn), sql_str(r.get('note')), sql_str(ts)]) + ');')
        out.append("INSERT INTO ledger (ts, emp_id, emp_name, action, pn, delta, balance, kks, note, wo, source, txn_id) VALUES ("
                   + ', '.join([sql_str(ts), "'system'", "'import'", "'IMPORT'", sql_str(r['pn']), 'NULL', str(int(r['qty'])), "''", sql_str('匯入：' + str(r.get('contract') or '')), "''", "'import'", "''"]) + ');')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')


def load_current(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    return rows


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('docx', nargs='*')
    ap.add_argument('--current')
    ap.add_argument('--qty', choices=['contract', 'current'], default='contract')
    ap.add_argument('--out', default=None, help='CSV（試算表 Import 用）')
    ap.add_argument('--sql', default=None, help='D1 匯入 SQL')
    ap.add_argument('--from-json', default=None, help='items JSON（mock_inventory.json 格式）→ 只輸出 --sql')
    a = ap.parse_args(argv)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    if a.from_json:
        rows = json.load(open(a.from_json, encoding='utf-8'))
        if not a.sql:
            raise SystemExit('--from-json 需要 --sql')
        write_sql(a.sql, rows, ts)
        print(f'寫出 {a.sql}：{len(rows)} 項（來自 {a.from_json}）')
        return 0
    if not a.docx:
        raise SystemExit('請給合約 .docx')
    items = []
    for p in a.docx:
        got = parse_doc(p)
        print(f'{p}: {len(got)} 項 {sum(i["qty"] for i in got)} 只（{got[0]["contract"] if got else ""}）')
        items += got
    mats = [i['mat'] for i in items]
    if len(set(mats)) != len(mats):
        raise SystemExit('料號重複：' + ', '.join(sorted({m for m in mats if mats.count(m) > 1})))
    models = [norm_code(i['model']) for i in items]
    if len(set(models)) != len(models):
        print('注意：完整型號重複（料號不同）：' + ', '.join(sorted({i['model'] for i in items if models.count(norm_code(i['model'])) > 1})))
    cur = load_current(a.current) if a.current else None
    diffs = []
    if cur is not None:
        if len(cur) != len(items):
            print(f'注意：現行 {len(cur)} 列 ≠ 合約 {len(items)} 項，依序對齊到較短者', file=sys.stderr)
        for i, it in enumerate(items):
            c = cur[i] if i < len(cur) else None
            it['loc'] = (c or {}).get('Location', '') or ''
            it['proto'] = it['proto'] or ((c or {}).get('Name', '') or '').strip()
            if c is None:
                it['now'] = it['qty']; diffs.append((it['mat'], it['model'], '現行無此列', it['qty'], it['qty'])); continue
            pn = norm_code(c.get('PartNumber', ''))
            if not norm_code(it['model']).startswith(pn) and not pn.startswith(norm_code(it['model'])):
                diffs.append((it['mat'], it['model'], f'型號前綴不符：現行 {c.get("PartNumber")}', it['qty'], c.get('Quantity')))
            try:
                it['now'] = int(float(c.get('Quantity') or 0))
            except ValueError:
                it['now'] = it['qty']
            if it['now'] != it['qty']:
                diffs.append((it['mat'], it['model'], '數量與合約不同（' + ('沿用現行' if a.qty == 'current' else '以合約為準') + '）', it['qty'], it['now']))
    else:
        for it in items:
            it['now'] = it['qty']; it['loc'] = ''
    if a.qty == 'contract':
        for it in items:
            it['now'] = it['qty']
    rows = [dict(pn=it['mat'], model=it['model'], brand=it['brand'], spec=it['spec'], loc=it['loc'], qty=it['now'], proto=it['proto'], family=family(it['model']), contract=it['contract'], cqty=it['qty'], min=None, note='') for it in items]
    if a.sql:
        write_sql(a.sql, rows, ts)
        print(f'寫出 {a.sql}：{len(rows)} 項，{sum(r["qty"] for r in rows)} 只')
    if not a.out:
        a.out = None
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['PartNumber', 'Name', 'Brand', 'Spec', 'Location', 'Quantity', 'Protocol', 'Family', 'Contract', 'ContractQty', 'MinQty', 'Note'])
    for it in items:
        w.writerow([it['mat'], it['model'], it['brand'], it['spec'], it['loc'], it['now'], it['proto'], family(it['model']), it['contract'], it['qty'], '', ''])
    if a.out:
        with open(a.out, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(buf.getvalue())
        print(f'寫出 {a.out}：{len(items)} 項')
    print(f'{len(items)} 項，合約 {sum(i["qty"] for i in items)} 只，採用數量合計 {sum(i["now"] for i in items)} 只（--qty {a.qty}）')
    if diffs:
        print('\n差異（料號 | 型號 | 說明 | 合約數 | 現行數）')
        for d in diffs:
            print(' | '.join(str(x) for x in d))
    fam = {}
    for it in items:
        fam.setdefault(family(it['model']), []).append(it['mat'])
    print('\n系列分佈：' + ', '.join(f'{k}×{len(v)}' for k, v in sorted(fam.items())))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
