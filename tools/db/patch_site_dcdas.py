# -*- coding: utf-8 -*-
"""把 extract_db.py／sheets_params.py 的規格改動套到「已發布」的 docs/db/data（sheets_final.pkl 不在手邊、無法重跑 extract_db 時用）。

  py tools/encrypt_data.py docs/db/data --decrypt
  py tools/db/patch_site_dcdas.py docs/db/data
  py tools/db/build_card_aux.py --recompare docs/db/data      # 重算 DCS 比對、manifest.build、加密、stamp

做的事（可重跑，冪等）：
- 02.json：`summary` 以 extract_db.summary_spec 重建（欄索引改由 03/13.json 的欄標籤反查）、`sections_aux`＝extract_db.SECTIONS_AUX、
  `src_defs`＝extract_db.SRC_DEFS、說明列補「控制器（紫）」。
- 13.json：`單位(解碼)` 空白而 (單位參數, 單位碼) 在 sheets_params.DEVICE_UNIT_ENUMS 的列補上單位（E+H Pressure1Unit=9→kPa、
  OutUnitEasy=18→mmH2O）；notes 的單位說明同步。
不重算 manifest.build、不加密（交給 build_card_aux --recompare；若不跑它，請自行 encrypt_data.py + stamp）。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract_db  # noqa: E402
from sheets_params import DEVICE_UNIT_ENUMS  # noqa: E402


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def save(p, o):
    with open(p, 'wb') as f:
        f.write(json.dumps(o, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))


def col_index(sheet):
    labels = [str(c.get('label') if isinstance(c, dict) else c) for c in sheet['columns']]

    def ci(prefix):
        if prefix in labels:
            return labels.index(prefix)
        for i, c in enumerate(labels):
            if c.startswith(prefix):
                return i
        raise KeyError(prefix)
    return ci


def main(data_dir):
    sheets = os.path.join(data_dir, 'sheets')
    if not os.path.exists(os.path.join(sheets, '02.json')):
        raise SystemExit('沒有明文 02.json：先 py tools/encrypt_data.py %s --decrypt' % data_dir)
    s02, s03, s13 = (load(os.path.join(sheets, n + '.json')) for n in ('02', '03', '13'))

    # ---- 02：summary / sections_aux / src_defs / notes
    s02['summary'] = extract_db.summary_spec(col_index(s03), col_index(s13))
    s02['sections_aux'] = extract_db.SECTIONS_AUX
    s02['src_defs'] = extract_db.SRC_DEFS
    s02['notes'] = [extract_db.CARD_NOTE_SRC if n.startswith('「來源：隱藏｜徽章｜完整」') else n for n in s02.get('notes', [])]
    save(os.path.join(sheets, '02.json'), s02)
    print('02.json: summary groups %s; sections_aux %s' % ([g['key'] for g in s02['summary']['groups']], [s['key'] for s in s02['sections_aux']]))

    # ---- 13：單位(解碼)
    ci = col_index(s13)
    c_unit, c_code, c_param = ci('單位(解碼)'), ci('單位碼'), ci('單位參數')
    n = 0
    for r in s13['rows']:
        if (r[c_unit] or '').strip():
            continue
        code, param = r[c_code], r[c_param]
        try:
            code = int(float(code))
        except (TypeError, ValueError):
            continue
        u = DEVICE_UNIT_ENUMS.get(param, {}).get(code)
        if u:
            r[c_unit] = u
            n += 1
    s13['notes'] = ['單位(解碼) 使用 HART Table-2 單位碼表; 裝置自訂列舉只解 E+H Pressure1Unit=9 (kPa)、OutUnitEasy=18 (mmH2O) (2026-09-24 以控制器 I/O 量程反推, DEVICE_UNIT_ENUMS), 其餘僅列碼'
                    if x.startswith('單位(解碼) 使用 HART Table-2') else x for x in s13.get('notes', [])]
    save(os.path.join(sheets, '13.json'), s13)
    print('13.json: 補上單位 %d 列' % n)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join('docs', 'db', 'data'))
