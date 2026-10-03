# -*- coding: utf-8 -*-
"""pneuvalve_site.py — 把「興達全廠氣動閥LIST_v2.6」（Google 試算表匯出的 xlsx）併進 docs/db 站。

  py tools/db/pneuvalve_site.py docs/db/data                 # 資料加密中 → 自動解密、套用、重算 build、加密（stamp 交給 rebuild.py）
  py tools/db/pneuvalve_site.py docs/db/data --keep-plain    # 只套用、不加密（接著還要跑別的產生器時）
  options: --xlsx X（預設 paths.PNEUVALVE_XLSX）  --xwalk J（對照覆寫檔，預設 <CARDWORK>/pneuvalve_xwalk.json）  --no-drive-map

更新來源：rclone backend copyid gdrive: 1_WOl6HYkY9y0WbGRH_NHP6d8cOsAWgk4ZmA1hwIQ5LE <xlsx> --drive-export-formats xlsx
（或直接用 fill26 的 build_v26.py 產出的本機 xlsx）。

做的事（冪等；重跑會先移除上一次加入的東西）：
- 新側欄群組「氣動閥清單」：57 氣動閥主表、58 水處理與公用水系統（xlsx 全部欄位＋AMS 設備連結欄）、59 兩讀並列、60 推翻紀錄、61 刪除紀錄。
  57／58 另帶 `valve_src`（查詢卡用的逐格出處：v2.6補齊明細的文件＋頁碼＋證據等級、推翻紀錄、專屬來源欄）與 `valve_docs`（文件 → Google 雲端硬碟連結）。
- 00_說明 目錄、manifest（groups、sheets、頁數）。
- 02.json：`valve`（位號 → 清單列、alias → 清單列＋定位器比對、查詢卡欄位表）；摘要組「氣動閥」（extract_db.summary_spec 也有，這裡只補缺）。
- AMS 對照：閥位號（xx／x0 依「涵蓋機組」展開）＝AMS 位號索引任一鍵（現行／舊／識別時位號、HostTag）；GT 閥另以 <機組>_90<GE 舊位號>（Legacy/GE Tag 欄）對照；
  再套對照覆寫檔（多代理逐筆驗證的結果：drop／add／note）。
必須在 extract_db／build_card_aux 之後跑（extract_db 會清掉 sheets/、patch_site_spec 會重寫 02 摘要）；rebuild.py 已把它接在兩條路徑的最後。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import encrypt_data  # noqa: E402
import extract_db  # noqa: E402
import paths  # noqa: E402
import pneuvalve_keys  # noqa: E402

GROUP = '氣動閥清單'
TAB_COLOR = '#8B5A00'
IDS = ['57', '58', '59', '60', '61']
MAIN_SHEETS = [('57', '氣動閥主表', '氣動閥主表'), ('58', '水處理與公用水系統', '水處理與公用水系統')]
AUX_SHEETS = [('59', 'v2.6兩讀並列', '氣動閥兩讀並列'), ('60', 'v2.6推翻紀錄', '氣動閥推翻紀錄'), ('61', 'v2.6刪除紀錄', '氣動閥刪除紀錄')]
SHEET_URL = 'https://docs.google.com/spreadsheets/d/1_WOl6HYkY9y0WbGRH_NHP6d8cOsAWgk4ZmA1hwIQ5LE/edit'
LIST_NAME = '興達全廠氣動閥LIST_v2.6'
TAG = 'Valve Tag No.'
AMS_COLS = ['AMS 設備 1（查詢卡）', 'AMS 設備 2（查詢卡）', 'AMS 對照（方式／定位器比對）']
HIDDEN = {'原System(v2.4)', '供證筆記本', '核對結果(System)', 'RDS-PP鍵', '核對證據(一手文件)', '反駁審查', '核對備註'}
BANDS = [('識別', 'No.'), ('製程與圖面', '流體介質'), ('閥體', '閥體型式'), ('執行器與附件', 'Actuator 品牌/型號'),
         ('備品料號', 'Positioner備品料號'), ('位置與文件', 'Legacy/GE Tag'), ('來源與核對', '備註')]
BAND_COLORS = ['#1F4E79', '#2E75B6', '#548235', '#8B5A00', '#7F7F7F', '#7030A0', '#404040']
FACET_COLS = ['Unit', '涵蓋機組', '功能分類', '閥體型式', '執行器形式', 'Fail Action (FO/FC/FL)', '證據等級', '控制來源']
# 查詢卡「氣動閥」組：顯示欄位（label, xlsx 欄名）；值的出處逐格帶
CARD_FIELDS = [
    ('閥門名稱 (EN)', 'Valve Name (EN)'), ('閥門名稱（中文）', '閥門名稱(中文)'), ('系統', 'System 系統'), ('流體介質', '流體介質'),
    ('閥體型式', '閥體型式'), ('功能分類', '功能分類'), ('閥體品牌／型號', 'Valve Manufacturer 閥體品牌/型號'),
    ('口徑', 'Valve Size (DN)'), ('壓力等級', 'Pressure Class'), ('Cv／流量特性', 'Cv/流量特性'),
    ('執行器品牌／型號', 'Actuator 品牌/型號'), ('執行器形式', '執行器形式'), ('失效動作', 'Fail Action (FO/FC/FL)'),
    ('定位器', 'Positioner 定位器'), ('控制訊號／通訊', '控制訊號/通訊'), ('SOV 電磁閥', 'SOV 電磁閥(型號/電壓/位號)'),
    ('極限開關／位置回授', 'Limit Switch/位置回授'), ('供氣壓力', '供氣壓力'), ('AFR 過濾減壓閥', 'AFR 過濾減壓閥'),
    ('P&ID', '所在P&ID圖號'), ('P&ID 張次', 'P&ID Sheet'), ('Hook-up 圖', 'Hook-up圖號'), ('序號', 'Serial No.'),
    ('GE 舊位號', 'Legacy/GE Tag'),
]
PAIRED_SRC = {'SOV 電磁閥(型號/電壓/位號)': 'SOV文件來源', 'Positioner 定位器': '定位器文件來源',
              'Limit Switch/位置回授': 'LS文件來源', 'Fail Action (FO/FC/FL)': '失效動作文件來源'}
LEVEL_LVL = {'推導': 'inferred', '翻譯': 'inferred'}
FACTORY_RE = re.compile(r'AQ[ABP]01-[QT]\d{4}|EOMR|FAT|出廠', re.I)
# 本機路徑一律剝掉：verify_encrypted.LOCAL_RE／build_card_aux.ABS_PATH_RE 會擋
# **字元集必須寫 [\\/]**：`[\/]` 在 Python 正則裡只等於 `[/]`（反斜線被當轉義吃掉），所以舊版對 Windows 的
# `C:\Users\bacon\…` 完全無效，試算表「來源」欄的建置機路徑就這樣跟著出貨（2026-10-03 修）。
LOCAL_PREFIX_RE = re.compile(r'(?:[A-Za-z]:[\\/]|/[a-z]/)?(?:Users[\\/]bacon[\\/])?(?:我的雲端硬碟[\\/])?@@新機組資料備份[\\/]?|我的雲端硬碟[\\/]?')
HOME_RE = re.compile(r'(?:[A-Za-z]:|/[a-z])?[\\/]Users[\\/]bacon(?=[\\/\s,;，；)）]|$)')  # 家目錄 → ~（signal-atlas 等 repo 外工具路徑）
# 最後一道：任何**還帶著本機痕跡**的絕對／多層路徑剝到只剩檔名（試算表的「來源」欄常整段貼
# `C:\Users\bacon\.claude\skills\…\srcdocs\HT0-1-….pdf`、`G:\其他電腦\辦公室\@@新機組\…`；
# 讀的人要的是文件檔名，不是建置者的目錄結構）。沒有本機痕跡的路徑（AMS 伺服器的 C:\ProgramData\… 之類）不動。
PATHY_RE = re.compile(r'(?:[A-Za-z]:|~)?[\\/](?:[^\\/\n;"]*[\\/])+([^\\/\n;"]+)')
LOCALISH_RE = re.compile(r'Users[\\/]bacon|我的雲端硬碟|@@新機組|其他電腦|\.claude[\\/]')


def scrub_paths(s):
    """字串裡的本機路徑 → 檔名（規則見 PATHY_RE／LOCALISH_RE 的註解）。"""
    def rep(m):
        return m.group(1) if LOCALISH_RE.search(m.group(0)) else m.group(0)
    return PATHY_RE.sub(rep, s)


# 輸出自檢用（與 tools/verify_encrypted.py 的 LOCAL_RE 同一份規則）：
# `[\\/]{1,2}` 是因為自檢掃的是**寫好的 JSON 文字**，裡面的分隔符是兩個反斜線
LOCAL_RE = re.compile(r'Users[\\/]{1,2}bacon|/c/Users/|我的雲端硬碟|@@新機組')
DOCNO_RE = re.compile(r'(HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4})(?:-([0-9A-Z]{1,2})(?![0-9A-Za-z]))?')
# 定位器家族（清單文字 vs AMS 製造商＋型號）
POS_FAM = [('Fisher', r'DVC\s*\d|FIELDVUE|\bFisher\b'), ('Masoneilan', r'SVI|Masoneilan'), ('Flowserve', r'Logix|Flowserve'),
           ('TopWorx', r'TopWorx|D2-FF'), ('YTC', r'\bYTC\b|\bYT-\d|C330'), ('ABB', r'TZID|\bABB\b'), ('Rotork', r'Rotork'),
           ('Siemens', r'SIPART|Siemens'), ('Samson', r'Samson|3730'), ('Metso', r'ND9|Neles|Metso|Valmet'), ('Azbil', r'Azbil|AVP')]


def compact(s):
    return re.sub(r'[^A-Z0-9]', '', re.sub(r'\s+', ' ', str(s or '').replace('=', '')).strip().upper())


def clean(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return '是' if v else '否'
    if isinstance(v, (int, float)):
        return v
    s = str(v)
    s = scrub_local(s)
    s = s.replace('\r\n', '\n').strip()
    return s if s else None


def name_clean(s):
    """閥名（建議清單用）：去掉查無類、開頭的「=位號(-KH01) / =位號 …：」參照、落單的 = ：與重複的詞。"""
    s = clean(s) or ''
    if not isinstance(s, str) or re.match(r'\s*(查無|待查|N/?A(?![A-Za-z]))', s):
        return ''
    s = re.sub(r'=\s*[A-Za-z0-9]{6,}(?:-[A-Z]{2}\d\d)?', ' ', s)
    s = re.sub(r'^[\s=/:：,;，；]+', '', s)
    s = re.sub(r'\s+=(?=\s|$)|[\s=/:：,;，；]+$', '', s)
    s = re.sub(r'\s+[:：]\s*', ' ', s)   # 拿掉參照後落單在中間的冒號（「定位器 ：HOOD 噴水」）
    out = []
    for w in s.split():
        if not out or out[-1] != w:
            out.append(w)
    return ' '.join(out).strip()


def col_meta(label, values):
    lens = [len(str(v)) for v in values if v is not None]
    num = bool(values) and all(isinstance(v, (int, float)) for v in values if v is not None) and any(v is not None for v in values)
    w = 80 if num else min(420, max(60, min(60, max(lens or [4])) * 8 + 16))
    d = {'label': label, 'fmt': None, 'type': 'num' if num else 'text', 'w': w, 'align': 'right' if num else 'left', 'bg': None}
    if re.search(r'Tag|位號|AMS 設備', label):
        d['mono'] = True
    if label in HIDDEN:
        d['hidden'] = True
    return d


def read_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        try:
            hdr = [str(h).strip() if h is not None else '' for h in next(it)]
        except StopIteration:
            continue
        while hdr and not hdr[-1]:
            hdr.pop()
        rows = []
        for r in it:
            r = list(r[:len(hdr)]) + [None] * (len(hdr) - len(r))
            # **在來源就剝掉本機路徑**：cell_sources() 讀的是這裡的原始列（不經過 clean()），
            # 只在 clean() 剝會讓「來源」欄的建置機路徑漏進 valve_src 跟著出貨
            r = [scrub_local(v) if isinstance(v, str) else v for v in r]
            if any(v not in (None, '') for v in r):
                rows.append(r)
        out[ws.title] = (hdr, rows)
    return out


def scrub_local(s):
    """本機路徑三道：文件庫根 → 相對、家目錄 → ~、其餘還帶本機痕跡的 → 只剩檔名。"""
    return scrub_paths(HOME_RE.sub('~', LOCAL_PREFIX_RE.sub('', s)))


# ------------------------------------------------------------------ AMS 對照
def load_json(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def expand_units(tag, cov):
    t = str(tag).strip().upper()
    m = re.match(r'([GCS])(XX|X0)(.*)$', t)
    if m:
        us = [u for u in re.findall(r'[GCS]\d\d', str(cov or '').upper()) if u[0] == m.group(1)]
        return [(u, u + m.group(3)) for u in us]
    m = re.match(r'((?:[GCS]\d\d/)+[GCS]\d\d)(.+)$', t)  # G11/G12/G32HSD10QN001：斜線列舉的機組
    if m:
        return [(u, u + m.group(2)) for u in m.group(1).split('/')]
    return [(t[:3], t)]


def pos_family(text):
    fams = [f for f, rx in POS_FAM if re.search(rx, text or '', re.I)]
    return fams


def crosswalk(valves, s03, s04, overrides):
    """→ {valve_tag: [{unit, alias, ams_tag, how, note}]}（同一閥同一 alias 只留一筆）"""
    keys = collections.defaultdict(list)
    for r in s04['rows']:
        keys[str(r[0]).upper()].append((str(r[2]), str(r[4])))
    dev = {str(r[1]): r for r in s03['rows']}
    out = collections.OrderedDict()
    for v in valves:
        tag = v['tag']; got = collections.OrderedDict()
        for u, e in expand_units(tag, v['cov']):
            for kind, al in keys.get(e, []):
                got.setdefault(al, {'unit': u, 'alias': al, 'how': 'KKS 位號＝AMS ' + re.sub(r'^\d+\s*', '', kind.split('(')[0]).strip() + '「' + e + '」'})
            if u.startswith('G'):
                for g in re.findall(r'\b[A-Z]{1,5}\d*[A-Z]?(?:-\d+[A-Z]?)+\b', str(v['legacy'] or '').upper()):
                    k = '%s_90%s' % (u, g)
                    for kind, al in keys.get(k, []):
                        got.setdefault(al, {'unit': u, 'alias': al, 'how': 'GE 舊位號＝AMS「%s」' % k})
        if got:
            out[tag] = list(got.values())
    drop = {(d['valve'], d['alias']) for d in overrides.get('drop', [])}
    for tag in list(out):
        out[tag] = [x for x in out[tag] if (tag, x['alias']) not in drop]
        if not out[tag]:
            del out[tag]
    for a in overrides.get('add', []):
        lst = out.setdefault(a['valve'], [])
        if not any(x['alias'] == a['alias'] for x in lst):
            lst.append({'unit': a.get('unit', ''), 'alias': a['alias'], 'how': a.get('how', '人工對照')})
    notes = {(n['valve'], n['alias']): n['note'] for n in overrides.get('note', [])}
    for tag, lst in out.items():
        for x in lst:
            d = dev.get(x['alias'])
            x['ams_tag'] = str(d[0]) if d else x['alias']
            x['ams_model'] = ' '.join(str(d[i]) for i in (24, 26) if d and d[i]) if d else ''
            if (tag, x['alias']) in notes:
                x['note'] = notes[(tag, x['alias'])]
        lst.sort(key=lambda x: x['unit'])
    return out


def positioner_cmp(list_text, ams_model):
    """清單定位器欄 vs AMS 製造商＋型號 → (status, text)；status ∈ ok|mismatch|absent|unknown"""
    lt = str(list_text or '')
    fa = pos_family(ams_model)
    if re.match(r'\s*(查無|待查|有\(|N/A)', lt) or not lt.strip():
        return 'unknown', '清單未載定位器型號；AMS＝%s' % ams_model
    if re.match(r'\s*無定位器', lt):
        return 'absent', '清單寫無定位器（%s）；AMS 有 %s' % (lt[:40], ams_model)
    fl = pos_family(lt)
    if not fl or not fa:
        return 'unknown', '無法判定廠牌（清單：%s；AMS：%s）' % (lt[:60], ams_model)
    if set(fl) & set(fa):
        return 'ok', '一致（%s）' % '／'.join(sorted(set(fl) & set(fa)))
    return 'mismatch', '不符：清單 %s ↔ AMS %s' % (lt[:60], ams_model)


# ------------------------------------------------------------------ 逐格出處
def doc_refs(text):
    return [(m.group(1), m.group(2) or '') for m in DOCNO_RE.finditer(str(text or '').upper())]


def resolve_docs(texts, drive):
    """文件編號（含版次）→ docs key（build_card_aux.resolve_doc_numbers 同規則：檔名以編號開頭、指定版次優先、PDF 優先、排除副本夾）"""
    if not drive:
        return {}, {}
    import build_card_aux
    rows = [['x', t] for t in texts]
    out = {'x': {'sec': {'v': {'entries': [{'rows': rows}]}}}}
    docs = {}
    doc_no = build_card_aux.resolve_doc_numbers(out, docs, drive)
    return doc_no, docs


def cell_sources(hdr, rows, sheet_name, fill, overturn, dual):
    """→ {row_idx: {col_label: [lvl, text, docno|None, two|None]}}（只做 CARD_FIELDS 的欄）"""
    ti = hdr.index(TAG)
    want = [c for _, c in CARD_FIELDS if c in hdr]
    main_src = hdr.index('主要資料來源(一手文件)') if '主要資料來源(一手文件)' in hdr else None
    out = {}
    for i, r in enumerate(rows):
        tag = str(r[ti])
        o = {}
        for c in want:
            v = r[hdr.index(c)]
            if v in (None, ''):
                continue
            k = (tag, sheet_name, c)
            two = dual.get((tag, c))
            if k in overturn:
                ev = overturn[k]
                text = '文件 · v2.6 推翻舊值（兩份一手文件互證）：%s；v2.5 原值「%s」（見 60 推翻紀錄）' % (ev['ev'], str(ev['old'])[:80])
                o[c] = ['factory' if FACTORY_RE.search(ev['ev']) else 'doc', text, (doc_refs(ev['ev']) or [(None,)])[0][0], two]
            elif k in fill:
                f = fill[k]
                lvl = LEVEL_LVL.get(f['lv']) or ('factory' if FACTORY_RE.search(f['doc']) else 'doc')
                lab = extract_db.SRC_PREFIX[lvl]
                text = '%s · %s%s（%s；v2.6 補齊）' % (lab, f['doc'], (' ' + f['loc']) if f['loc'] else '', f['lv'])
                o[c] = [lvl, text, (doc_refs(f['doc']) or [(None,)])[0][0], two]
            else:
                ps = PAIRED_SRC.get(c)
                pv = r[hdr.index(ps)] if ps and ps in hdr else None
                sv = pv or (r[main_src] if main_src is not None else None)
                if sv:
                    lvl = 'factory' if FACTORY_RE.search(str(sv)) else 'doc'
                    text = '%s · %s（%s）' % (extract_db.SRC_PREFIX[lvl], str(sv)[:300], ps if pv else '本列主要資料來源；v2.5 既有值')
                    o[c] = [lvl, text, (doc_refs(sv) or [(None,)])[0][0], two]
                else:
                    o[c] = ['doc', '文件 · v2.5 既有值（本列未記出處）', None, two]
            if isinstance(v, str) and '[推導]' in v and o[c][0] != 'inferred':
                o[c][0] = 'inferred'; o[c][1] = '推論 · ' + o[c][1].split(' · ', 1)[-1]
            if isinstance(v, str) and '(自動翻譯)' in v:
                o[c][0] = 'inferred'; o[c][1] = '推論 · 由英文名自動翻譯（%s）' % o[c][1].split(' · ', 1)[-1]
        if o:
            out[str(i)] = o
    return out


# ------------------------------------------------------------------ 輸出
def table_json(sid, name, title, hdr, rows, notes, ui_extra=None, bands=None):
    cols = [col_meta(h, [r[j] for r in rows]) for j, h in enumerate(hdr)]
    facets = [hdr.index(c) for c in FACET_COLS if c in hdr and 1 < len({str(r[hdr.index(c)]) for r in rows}) <= 40 and len(rows) > 20]
    if not bands:
        bands = [{'label': title[:60], 'from': 0, 'to': max(0, len(cols) - 1), 'bg': '#1F4E79', 'fc': '#FFFFFF'}]
    ui = {'default_sort': None, 'facets': facets, 'search_cols': None, 'alias_col': None, 'key_col': hdr.index(TAG) if TAG in hdr else 0}
    ui.update(ui_extra or {})
    return {'id': sid, 'name': '%s_%s' % (sid, name), 'mode': 'table', 'title': '%s_%s' % (sid, name), 'notes': notes,
            'header_cells': [{'r': 1, 'c': 1, 'v': {'t': '⌂ 目錄', 'l': {'s': '00', 'r': 1}}}], 'bands': bands, 'columns': cols,
            'freeze_cols': 2 if TAG in hdr and hdr.index(TAG) <= 1 else 1, 'rows': rows, 'styles': [], 'cell_styles': [], 'row_styles': [], 'ui': ui}


def band_list(hdr):
    out = []
    starts = [(hdr.index(c), lab, BAND_COLORS[k]) for k, (lab, c) in enumerate(BANDS) if c in hdr]
    starts.sort()
    for k, (s, lab, bg) in enumerate(starts):
        e = (starts[k + 1][0] - 1) if k + 1 < len(starts) else len(hdr) - 1
        out.append({'label': lab, 'from': 0 if k == 0 else s, 'to': e, 'bg': bg, 'fc': '#FFFFFF'})
    return out


def remove_previous(data, man):
    for sid in IDS:
        for p in (os.path.join(data, 'sheets', sid + '.json'),):
            if os.path.exists(p):
                os.remove(p)
    man['sheets'] = [s for s in man['sheets'] if s['id'] not in IDS]
    man['groups'] = [g for g in man.get('groups', []) if g != GROUP]


def patch_00(data, entries):
    p = os.path.join(data, 'sheets', '00.json')
    g = load_json(p)
    ours = set(IDS)
    def links_ours(row):
        return any(isinstance(c, dict) and isinstance(c.get('l'), dict) and c['l'].get('s') in ours for c in row.get('cells', []))
    # 移除上一次加入的列，之後的列往上補（sections 同步）
    removed = sorted(r['r'] for r in g['rows'] if links_ours(r))
    up = lambda r0: r0 - sum(1 for x in removed if x < r0)
    rows = [dict(row, r=up(row['r'])) for row in sorted(g['rows'], key=lambda x: x['r']) if not links_ours(row)]
    g['sections'] = [dict(s, r=up(s['r'])) for s in g['sections']]
    sec4 = next(s for s in g['sections'] if s['label'].startswith('4'))
    # 目錄：插在 4 節標題前的空白列（＝目錄最後一列＋1）
    toc_rows = [r for r in rows if r['r'] < sec4['r'] and any(isinstance(c, dict) and c.get('c') == 2 and isinstance(c.get('l'), dict) for c in r['cells'])]
    ins = max(r['r'] for r in toc_rows) + 1
    tmpl = toc_rows[-1]['cells']
    st = {c['c']: c.get('s') for c in tmpl}
    new = []
    for k, e in enumerate(entries):
        new.append({'r': ins + k, 'cells': [{'c': 2, 'v': e['name'], 's': st.get(2), 'l': {'s': e['id'], 'r': None}}, {'c': 3, 'v': e['desc'], 's': st.get(3)},
                                            {'c': 4, 'v': e['row_unit'], 's': st.get(4)}, {'c': 5, 'v': e['rows'], 's': st.get(5)}, {'c': 6, 'v': e['cols'], 's': st.get(6)},
                                            {'c': 7, 'v': e['sources'], 's': st.get(7)}]})
    n = len(new)
    rows = [dict(r, r=r['r'] + n) if r['r'] >= ins else r for r in rows]
    g['sections'] = [dict(s, r=s['r'] + n) if s['r'] >= ins else s for s in g['sections']]
    # 各表閱讀註記：接在最後
    last = max(r['r'] for r in rows)
    note_style = None
    for r in rows:
        for c in r['cells']:
            if c.get('c') == 3 and c.get('cs') == 5:
                note_style = c.get('s')
    tail = []
    rr = last + 1
    for e in entries:
        for t in e['_notes']:
            tail.append({'r': rr, 'cells': [{'c': 2, 'v': e['name'], 's': st.get(2), 'l': {'s': e['id'], 'r': None}}, {'c': 3, 'v': t, 's': note_style, 'cs': 5}]})
            rr += 1
    g['rows'] = sorted(rows + new + tail, key=lambda x: x['r'])
    g['max_row'] = max(r['r'] for r in g['rows']) + 1
    extract_db.write(p, g)
    return g['max_row']


def set_page_count(man, data):
    n = len(man['sheets'])
    wb = man['workbook']
    for k in ('subtitle', 'summary_subtitle'):
        if wb.get(k):
            wb[k] = re.sub(r'本站 \d+ 頁', '本站 %d 頁' % n, wb[k])
    p = os.path.join(data, 'sheets', '00.json')
    g = load_json(p)
    g['subtitle'] = re.sub(r'本站 \d+ 頁', '本站 %d 頁' % n, g.get('subtitle', ''))
    for r in g['rows']:
        for c in r['cells']:
            if isinstance(c.get('v'), str) and '本站 ' in c['v']:
                c['v'] = re.sub(r'本站 \d+ 頁', '本站 %d 頁' % n, c['v'])
    extract_db.write(p, g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data')
    ap.add_argument('--xlsx', default=paths.PNEUVALVE_XLSX)
    ap.add_argument('--xwalk', default=os.path.join(paths.CARDWORK, 'pneuvalve_xwalk.json'))
    ap.add_argument('--drive-map', default=paths.DRIVE_MAP)
    ap.add_argument('--no-drive-map', action='store_true')
    ap.add_argument('--keep-plain', action='store_true')
    a = ap.parse_args()
    data = a.data
    was_enc = encrypt_data.is_encrypted(data)
    if was_enc:
        encrypt_data.decrypt_dir(data, encrypt_data.passphrase_and_salt(persist=False)[0])
    try:
        run(a, data)
    except BaseException:
        if was_enc and not a.keep_plain:
            encrypt_data.encrypt_dir(data, *encrypt_data.passphrase_and_salt())
            print('!! 失敗：已把原資料加密回去（manifest.build 未變）')
        raise
    if not a.keep_plain:
        encrypt_data.encrypt_dir(data, *encrypt_data.passphrase_and_salt())


def run(a, data):
    if not os.path.exists(a.xlsx):
        raise SystemExit('!! 找不到氣動閥清單 xlsx：%s（--xlsx 或環境變數 AMS_PNEUVALVE_XLSX）' % a.xlsx)
    drive = None
    if not a.no_drive_map:
        import build_card_aux
        drive = build_card_aux.load_drive_map(a.drive_map)
        if not drive:
            raise SystemExit('!! 缺 drive_map（%s），若確定不要雲端連結請加 --no-drive-map' % a.drive_map)
    man_path = os.path.join(data, 'manifest.json')
    man = load_json(man_path)
    remove_previous(data, man)
    S = lambda sid: load_json(os.path.join(data, 'sheets', sid + '.json'))
    s02, s03, s04 = S('02'), S('03'), S('04')
    wbx = read_xlsx(a.xlsx)
    for _, sh, _ in MAIN_SHEETS + [(None, x[1], None) for x in AUX_SHEETS]:
        if sh not in wbx:
            raise SystemExit('!! xlsx 缺分頁：%s' % sh)
    overrides = load_json(a.xwalk) if a.xwalk and os.path.exists(a.xwalk) else {}
    print('對照覆寫檔：%s' % (a.xwalk if overrides else '（無，只用自動規則）'))

    # 逐格出處來源
    fh, frows = wbx['v2.6補齊明細']
    fill = {}
    for r in frows:
        d = dict(zip(fh, r))
        fill[(str(d['Valve Tag No.']), str(d['分頁']), str(d['欄位']))] = {'doc': clean(d['文件']) or '', 'loc': clean(d['頁/位置']) or '', 'lv': str(d['等級'] or '')}
    oh, orows = wbx['v2.6推翻紀錄']
    overturn = {}
    for r in orows:
        d = dict(zip(oh, r))
        overturn[(str(d['Valve Tag No.']), str(d['分頁']), str(d['欄位']))] = {'ev': clean(d['證據(一手互證)']) or '', 'old': clean(d['v2.5原值']) or ''}
    dh, drows = wbx['v2.6兩讀並列']
    dual = {}
    for r in drows:
        d = dict(zip(dh, r))
        dual[(str(d['Valve Tag No.']), str(d['欄位']))] = [clean(d['讀法A']), clean(d['出處A']), clean(d['讀法B']), clean(d['出處B']), clean(d['表內採用']), clean(d['備註'])]

    valves = []
    for sid, sh, _ in MAIN_SHEETS:
        hdr, rows = wbx[sh]
        ti, ci, li = hdr.index(TAG), hdr.index('涵蓋機組'), hdr.index('Legacy/GE Tag')
        for i, r in enumerate(rows):
            if r[ti]:
                valves.append({'sid': sid, 'row': i, 'tag': str(r[ti]).strip(), 'cov': r[ci], 'legacy': r[li], 'r': r, 'hdr': hdr})
    xw = crosswalk(valves, s03, s04, overrides)

    # 搜尋用識別碼（pneuvalve_keys）：index＝{compact 鍵: [[sid, 列], …]}（同一鍵可對多列：LCV-3461、VA46-1A）；
    # weak＝只當建議的廠商代號；vlist＝自動完成／查無頁建議用的 [sid, 列, 位號, [別名…], 中文名, 英文名]
    list_cores = {compact(pneuvalve_keys.core_of(v['tag'])) for v in valves}
    merged = collections.defaultdict(list)
    xh, xrows = wbx['v2.6刪除紀錄']
    if '併入列' in xh and '類別' in xh:
        for r in xrows:
            if r[xh.index('併入列')] and '別名' in str(r[xh.index('類別')]):
                merged[str(r[xh.index('併入列')]).strip()].append(str(r[0]).strip())
    all_texts = []
    entries = []
    valve_index = {}
    valve_weak = {}
    valve_list = []
    fam_stats = collections.Counter()
    by_alias = collections.defaultdict(list)
    cmp_stats = collections.Counter()
    for sid, sh, short in MAIN_SHEETS:
        hdr0, rows0 = wbx[sh]
        ti = hdr0.index(TAG)
        hdr = hdr0[:ti + 1] + AMS_COLS + hdr0[ti + 1:]
        pi = hdr0.index('Positioner 定位器')
        out_rows = []
        for i, r in enumerate(rows0):
            tag = str(r[ti]).strip() if r[ti] else ''
            rr = [clean(v) for v in r]
            lst = xw.get(tag, [])
            links = [{'t': x['ams_tag'], 'l': {'s': '02', 'q': x['alias']}} for x in lst[:2]]
            links += [None] * (2 - len(links))
            info = []
            for x in lst:
                st, txt = positioner_cmp(r[pi], x['ams_model'])
                cmp_stats[st] += 1
                x['cmp'] = st; x['cmp_text'] = txt
                info.append('%s %s → %s（%s）；定位器%s%s' % (x['unit'], x['alias'], x['ams_tag'], x['how'], txt, ('；' + x['note']) if x.get('note') else ''))
                by_alias[x['alias']].append([sid, i, x['unit'], x['how'], st, txt, x.get('note', '')])
            if len(lst) > 2:
                print('  ! %s 對到 %d 台 AMS 設備（只放前 2 台連結，其餘寫在對照欄）' % (tag, len(lst)))
            out_rows.append(rr[:ti + 1] + links + ['｜'.join(info) or None] + rr[ti + 1:])
            if tag:
                rowd = {h: ('' if v is None else str(v)) for h, v in zip(hdr0, r)}
                als = []
                for k, fam in pneuvalve_keys.valve_keys(rowd, list_cores, merged.get(tag, ())):
                    fam_stats[fam] += 1
                    tgt = valve_weak if fam in pneuvalve_keys.WEAK else valve_index
                    lst_k = tgt.setdefault(compact(k), [])
                    if [sid, i] not in lst_k:
                        lst_k.append([sid, i])
                    if fam not in ('tag', 'tag-unit', 'core', 'ge-dev-90', 'ge-kks-core'):
                        als.append(k)
                zh = name_clean(re.sub(r'\s*[(（]自動翻譯[)）]\s*$', '', rowd.get('閥門名稱(中文)') or ''))
                en = name_clean(rowd.get('Valve Name (EN)') or '')
                if len(re.findall(r'[一-鿿]', zh)) < 2:
                    zh = ''   # 自動翻譯只剩「= = ：」之類的殘渣 → 留空，建議改用英文名
                elif len(re.findall(r'[一-鿿]', zh)) < 4 and en:
                    zh = '%s（%s）' % (zh, en[:34])   # 只剩「密封油」「水洗」這種泛稱 → 附英文名才分得出是哪一顆
                units = sorted({u for u, _ in expand_units(tag, rowd.get('涵蓋機組'))})
                valve_list.append([sid, i, tag, als, zh[:40], en[:70], units])
            for c in hdr0:
                v = r[hdr0.index(c)]
                if isinstance(v, str):
                    all_texts.append(v)
        src = cell_sources(hdr0, rows0, sh, fill, overturn, dual)
        for o in src.values():
            for x in o.values():
                all_texts.append(x[1])
        n_amslinked = sum(1 for r in out_rows if r[ti + 1])
        notes = ['一列＝一個氣動閥位號（xx／x0 位號＝同構多機組合併一列，見「涵蓋機組」）｜列數 %d｜來源：Google 試算表「%s」分頁「%s」' % (len(out_rows), LIST_NAME, sh),
                 '試算表（正本、可編輯）：' + SHEET_URL,
                 '每格出處：v2.6 補齊的格見同列「v2.6補齊來源」欄（文件＋頁碼）；SOV／定位器／極限開關／失效動作另有專屬來源欄；查詢卡的「氣動閥」組逐格列出處並可開雲端文件。',
                 '「查無(理由)」＝已讀過的文件確定不載；「待查」＝尚有文件沒讀；「N/A(…)」＝不適用（如無 SOV 則 SOV 備品料號 N/A）；「[推導]」＝由同列其他欄推得；「(自動翻譯)」＝中文名由英文名翻譯。',
                 '兩份一手文件互相矛盾的格不硬裁，另列於 59_氣動閥兩讀並列，該列「v2.6補齊來源」有 [兩讀] 註記。',
                 'AMS 設備 1／2：本列閥在 AMS 資料庫裡的智慧定位器（點開查詢卡）；%d 列有對到。對照方式：閥位號（xx／x0 依涵蓋機組展開）＝AMS 位號索引任一鍵，或 GT 閥 <機組>_90<GE 舊位號>；'
                 '經多代理逐筆驗證。沒有 AMS 設備＝開關閥（SOV 直控）、非 HART/FF 定位器，或該機組不在本 AMS 資料庫（本庫只有 1 號機：G11、G12、S10、C10）。' % n_amslinked,
                 '「定位器比對」：清單定位器欄與 AMS 製造商＋型號比廠牌家族（Fisher DVC、Masoneilan SVI、Flowserve Logix…）；不符者請以現場銘牌為準。AMS 定位器序號換過就會變，只當旁證。']
        tj = table_json(sid, short, sh, hdr, out_rows, notes, ui_extra={'presets': [{'label': '有 AMS 設備', 'col': ti + 1, 'nonempty': True}]}, bands=band_list(hdr))
        tj['valve_src'] = src
        entries.append({'id': sid, 'name': '%s_%s' % (sid, short), 'short': short, 'tj': tj, 'rows': len(out_rows), 'cols': len(hdr),
                        'desc': '全廠氣動閥清單 v2.6「%s」：閥體／執行器／定位器／SOV／極限開關／失效動作規格、P&ID、備品料號，逐格可溯源到一手文件' % sh,
                        'row_unit': '一個氣動閥位號（同構多機組合併）', 'sources': LIST_NAME + '（Google 試算表）', '_notes': notes[:1] + notes[5:6]})
        print('%s %s: %d 列、%d 欄、%d 列對到 AMS 設備' % (sid, short, len(out_rows), len(hdr), n_amslinked))

    for sid, sh, short in AUX_SHEETS:
        hdr, rows = wbx[sh]
        rows = [[clean(v) for v in r] for r in rows]
        desc = {'59': '兩份一手文件對同一格讀法不同（不硬裁、留現場查對）：讀法 A／B 與各自出處、表內採用哪一個',
                '60': 'v2.6 以兩份一手文件互證推翻 v2.5 既有值：原值、新值與證據',
                '61': 'v2.6 經逐列複核刪除的範疇外列（直動 SOV、電動、手動、液動、減溫器、幽靈位號…）：原列全部欄位與刪除理由'}[sid]
        unit = {'59': '一個（位號, 欄位）的兩讀', '60': '一個被推翻的格', '61': '一個被刪除的列'}[sid]
        notes = ['一列＝%s｜列數 %d｜來源：Google 試算表「%s」分頁「%s」' % (unit, len(rows), LIST_NAME, sh), '試算表（正本）：' + SHEET_URL]
        tj = table_json(sid, short, sh, hdr, rows, notes)
        entries.append({'id': sid, 'name': '%s_%s' % (sid, short), 'short': short, 'tj': tj, 'rows': len(rows), 'cols': len(hdr), 'desc': desc,
                        'row_unit': unit, 'sources': LIST_NAME + '（Google 試算表）', '_notes': []})
        print('%s %s: %d 列' % (sid, short, len(rows)))

    # 文件 → 雲端連結
    doc_no, docs = resolve_docs(all_texts, drive)
    for e in entries:
        tj = e['tj']
        if 'valve_src' in tj:
            used = {}
            for o in tj['valve_src'].values():
                for x in o.values():
                    k = doc_no.get(x[2]) if x[2] else None
                    x[2] = k
                    if k:
                        used[k] = {kk: docs[k][kk] for kk in ('title', 'folder', 'why', 'url', 'url_note') if docs[k].get(kk)}
            tj['valve_docs'] = used
    # 寫檔＋manifest
    for e in entries:
        fn = 'sheets/%s.json' % e['id']
        nbytes = extract_db.write(os.path.join(data, fn), e['tj'])
        man['sheets'].append({'id': e['id'], 'name': e['name'], 'short': e['short'], 'group': GROUP, 'mode': 'table', 'rows': e['rows'], 'cols': e['cols'],
                              'files': [fn], 'bytes': nbytes, 'desc': e['desc'], 'row_unit': e['row_unit'], 'sources': e['sources'],
                              'toc_rows': e['rows'], 'tab_color': TAB_COLOR, 'data_first_row': 4})
    gs = [g for g in man.get('groups', []) if g != GROUP]
    gs.insert(gs.index('設備與位置') + 1 if '設備與位置' in gs else len(gs), GROUP)
    man['groups'] = gs
    # 00 目錄
    mr = patch_00(data, entries)
    for s in man['sheets']:
        if s['id'] == '00':
            s['rows'] = s['toc_rows'] = mr
            s['bytes'] = os.path.getsize(os.path.join(data, 'sheets', '00.json'))
    set_page_count(man, data)
    # 02：查詢卡
    summ = s02.get('summary') or {}
    groups = summ.get('groups') or []
    # 摘要組以 extract_db.summary_spec 為準（標籤／說明同步），位置在 range 之後（dev｜range 兩欄一對，氣動閥整列寬）
    spec_g = next(g for g in extract_db.summary_spec(lambda p: 0, lambda p: 0)['groups'] if g.get('key') == 'valve')
    groups[:] = [g for g in groups if g.get('key') != 'valve']
    pos = next((k + 1 for k, g in enumerate(groups) if g.get('key') == 'range'), next((k + 1 for k, g in enumerate(groups) if g.get('key') == 'dev'), len(groups)))
    groups.insert(pos, spec_g)
    summ['groups'] = groups
    s02['summary'] = summ
    s02['valve'] = {
        'sheets': {sid: '%s_%s' % (sid, short) for sid, _, short in MAIN_SHEETS},
        'fields': [[lab, col] for lab, col in CARD_FIELDS],
        'index': valve_index,
        'weak': valve_weak,
        'list': valve_list,
        'by_alias': dict(by_alias),
        'list_name': LIST_NAME, 'list_url': SHEET_URL,
    }
    extract_db.write(os.path.join(data, 'sheets', '02.json'), s02)
    # 自檢：任何新寫的檔不得含本機路徑
    for e in entries + [{'id': '02'}, {'id': '00'}]:
        txt = open(os.path.join(data, 'sheets', e['id'] + '.json'), encoding='utf-8').read()
        m = LOCAL_RE.search(txt)
        if m:
            raise SystemExit('!! sheets/%s.json 含本機路徑：…%s…' % (e['id'], txt[max(0, m.start() - 60):m.end() + 40]))
    man['build'] = extract_db.data_build(data, man)
    extract_db.write(man_path, man)
    n_al = len(by_alias)
    print('對照：%d 個閥位號 ↔ %d 台 AMS 設備；定位器比對 %s；位號索引 %d 鍵；雲端文件 %d 份；build %s'
          % (len(xw), n_al, dict(cmp_stats), len(valve_index), len(docs), man['build']))
    multi = {k: v for k, v in valve_index.items() if len(v) > 1}
    print('搜尋識別碼：%s；一鍵多列 %d 個（如 %s）；只當建議 %d 個' % (dict(fam_stats), len(multi), '、'.join(list(multi)[:6]), len(valve_weak)))
    dupe = [al for al, v in by_alias.items() if len(v) > 1]
    if dupe:
        print('  ! 同一台 AMS 設備對到多個閥列：%s' % ', '.join(dupe[:20]))


if __name__ == '__main__':
    main()
