# -*- coding: utf-8 -*-
"""位號索引：每個曾出現過的位號字串 → 目前位號 / 設備別名 / 設備鍵（查詢卡與網頁全域搜尋的查表來源）。
Sources: ExtBlockTags+BlockAsgms (all tags ever assigned, current and ended), Devices.AmsDeviceTag, Devices.Identifier,
Devices.AmsDeviceId (GUID), DeviceLocation.HostTag, DeviceKey, and the old-workbook alias (D0xxxx) taken from
sheets_cache.pkl (devices/設備總表) when available, else from 20260910_AMS解析.xlsx.
Column order is fixed (the web front-end reads by index): 0 查詢鍵, 1 位號字串(原樣), 2 來源類型, 3 目前位號, 4 設備別名, 5 設備鍵, 6 型號, 7 此字串對應設備數.
"""
import os, re, sqlite3, pickle, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # tools/db/paths.py：repo 外路徑的唯一來源
from paths import AMS_SQLITE as DB, SHEETS_CACHE, PREV_XLSX  # noqa: E402

CTRL = re.compile(r'[\x00-\x1f\x7f-\x9f\u2028\u2029]')


def norm_key(s):
    """= Excel UPPER(TRIM(SUBSTITUTE(x,"=",""))) with control chars removed and inner whitespace collapsed (same as web IX.norm)."""
    if s is None:
        return ''
    s = CTRL.sub('', str(s)).replace('=', '')
    s = re.sub(r'\s+', ' ', s).strip().upper()
    return s


def clean_tag(s):
    if s is None:
        return ''
    return CTRL.sub('', str(s)).strip()


CLEAN_TAG_OF = {}  # DeviceKey -> the cleaned current tag shown in 設備總表 (devices module's clean_tag)


def alias_map(conn):
    """DeviceKey -> alias (D0xxxx). Prefer the cached 設備總表 (already matched by GUID against the old workbook)."""
    cache = SHEETS_CACHE
    if os.path.exists(cache):
        raw = pickle.load(open(cache, 'rb'))
        for s in raw.get('devices', []):
            if s['name'] == '設備總表':
                df = s['df']
                kc = [c for c in df.columns if c.startswith('設備鍵')][0]
                ac = [c for c in df.columns if c.startswith('舊工作簿別名')][0]
                tc = [c for c in df.columns if c.startswith('現行AMS位號')][0]
                CLEAN_TAG_OF.update({int(k): (t if isinstance(t, str) else '') for k, t in zip(df[kc], df[tc])})
                return {int(k): (a if isinstance(a, str) else '') for k, a in zip(df[kc], df[ac])}
    # fallback: GUID match against the old workbook
    import openpyxl
    xlsx = PREV_XLSX
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb['03_設備總表']
    hdr = None; guid_col = alias_col = None; g2a = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 3:
            hdr = list(row)
            for j, h in enumerate(hdr):
                if h and 'AmsDeviceId' in str(h): guid_col = j
                if h and str(h).startswith('設備別名'): alias_col = j
        elif i > 3 and guid_col is not None:
            g = row[guid_col]; a = row[alias_col]
            if g and a: g2a[str(g).upper()] = str(a)
    out = {}
    for k, g in conn.execute('select DeviceKey, AmsDeviceId from Devices where DeviceKey>=0'):
        out[int(k)] = g2a.get(str(g).upper(), '')
    return out


def build(conn):
    a_of = alias_map(conn)
    dev = pd.read_sql_query("""
        select d.DeviceKey, d.AmsDeviceTag, d.Identifier, d.AmsDeviceId, dt.Name as Model, p.Name as Protocol, l.HostTag
        from Devices d
        left join DeviceRevisions dr on dr.AmsDevRevId=d.AmsDevRevId
        left join DeviceTypes dt on dt.AmsDevTypeId=dr.AmsDevTypeId
        left join MfrProtocols mp on mp.MfrProtocolId=dt.MfrProtocolId
        left join DeviceProtocols p on p.ProtocolId=mp.ProtocolId
        left join Blocks b on b.DeviceKey=d.DeviceKey and b.BlockIndex=0
        left join DeviceLocation l on l.BlockKey=b.BlockKey
        where d.DeviceKey>=0""", conn)
    cur = pd.read_sql_query("""
        select b.DeviceKey, t.ExtBlockTag from BlockAsgms a join ExtBlockTags t on t.ExtBlockTagKey=a.ExtBlockTagKey
        join Blocks b on b.BlockKey=a.BlockKey where a.EventIdDayOut=49710 and b.DeviceKey>=0""", conn)
    cur_of = {int(k): clean_tag(t) for k, t in zip(cur.DeviceKey, cur.ExtBlockTag)}
    cur_raw = {int(k): (t or '') for k, t in zip(cur.DeviceKey, cur.ExtBlockTag)}
    ended = pd.read_sql_query("""
        select b.DeviceKey, t.ExtBlockTag, a.EventIdDayOut, a.EventIdFractionOut from BlockAsgms a
        join ExtBlockTags t on t.ExtBlockTagKey=a.ExtBlockTagKey join Blocks b on b.BlockKey=a.BlockKey
        where a.EventIdDayOut<>49710 and b.DeviceKey>=0 order by a.EventIdDayOut desc, a.EventIdFractionOut desc""", conn)

    rows = []  # (prio, src, raw, devkey)
    def add(prio, src, raw, k):
        if raw is None: return
        raw = str(raw)
        if not norm_key(raw): return
        rows.append((prio, src, raw, int(k)))

    for r in dev.itertuples(index=False):
        k = r.DeviceKey
        add(0, '0 目前AMS位號', cur_of.get(k, ''), k)
        raw_cur = cur_raw.get(k, '')
        if norm_key(raw_cur) != norm_key(cur_of.get(k, '')):
            add(0, '0 目前AMS位號 (原值)', raw_cur, k)
        shown = CLEAN_TAG_OF.get(k, '')
        if shown and norm_key(shown) not in (norm_key(cur_of.get(k, '')), norm_key(raw_cur)):
            add(0, '0 目前AMS位號 (清理後)', shown, k)
        add(1, '1 設備別名', a_of.get(k, ''), k)
        add(3, '3 識別時裝置位號 (AmsDeviceTag)', r.AmsDeviceTag, k)
        add(4, '4 主機位號 (HostTag)', r.HostTag, k)
        add(5, '5 裝置ID (Identifier)', r.Identifier, k)
        add(6, '6 設備鍵 (DeviceKey)', str(k), k)
        add(7, '7 設備GUID', r.AmsDeviceId, k)
    seen_prev = set()
    for r in ended.itertuples(index=False):
        key = (norm_key(r.ExtBlockTag), int(r.DeviceKey))
        if key in seen_prev: continue
        seen_prev.add(key)
        add(2, '2 舊AMS位號 (已結束指派)', r.ExtBlockTag, r.DeviceKey)

    df = pd.DataFrame(rows, columns=['prio', 'src', 'raw', 'DeviceKey'])
    df['key'] = df['raw'].map(norm_key)
    # de-dup identical (key, device, src)
    df = df.drop_duplicates(['key', 'DeviceKey', 'src'])
    model = dict(zip(dev.DeviceKey, dev.Model))
    df['tag'] = df['DeviceKey'].map(cur_of)
    df['alias'] = df['DeviceKey'].map(a_of)
    df['model'] = df['DeviceKey'].map(model)
    n_dev = df.groupby('key')['DeviceKey'].nunique()
    df['n'] = df['key'].map(n_dev)
    df = df.sort_values(['key', 'prio', 'DeviceKey']).reset_index(drop=True)
    out = pd.DataFrame({
        '查詢鍵 (UPPER/TRIM/去=)': df['key'],
        '位號字串(原樣)': df['raw'].map(lambda s: CTRL.sub('', s)),
        '來源類型 (數字小者優先)': df['src'],
        '目前AMS位號': df['tag'],
        '設備別名 (alias)': df['alias'],
        '設備鍵 (DeviceKey)': df['DeviceKey'],
        '型號': df['model'],
        '此字串對應設備數': df['n'].astype(int),
    })
    return [{
        'name': '位號索引',
        'purpose': '曾出現過的每個位號字串（目前/舊 AMS 位號、識別時位號、HostTag、裝置ID、設備鍵、GUID、別名）→ 目前位號與設備別名；設備查詢卡與網頁搜尋的查表來源',
        'one_row': '一個位號字串 × 來源類型 × 設備',
        'df': out,
        'notes': ['查詢鍵 = 去掉 "="、去頭尾空白與控制字元、連續空白合一、轉大寫（= Excel UPPER(TRIM(SUBSTITUTE(x,"=","")))）',
                  '同一鍵對應多台設備時，來源類型數字小者排前（查詢卡 MATCH 先命中）；此字串對應設備數 >1 代表歧義',
                  '設備別名 = 前簿 20260910_AMS解析.xlsx 的 alias（以設備 GUID 對應，1,928/1,928）'],
        'source_tables': ['ExtBlockTags', 'BlockAsgms', 'Devices', 'DeviceLocation', 'DeviceTypes'],
    }]


if __name__ == '__main__':
    conn = sqlite3.connect(DB)
    for s in build(conn):
        print(s['name'], s['df'].shape)
        print(s['df'].head(12).to_string())
        print(s['df']['來源類型 (數字小者優先)'].value_counts())
        print('ambiguous keys:', (s['df'].drop_duplicates('查詢鍵 (UPPER/TRIM/去=)')['此字串對應設備數'] > 1).sum())
