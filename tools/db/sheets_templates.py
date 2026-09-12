# -*- coding: utf-8 -*-
"""
sheets_templates.py  --  AMS Device Manager (AmsDb) 範本、測試定義與附加資料 (domain key: templates)

build(conn) -> list[dict]   每個 dict = {name, purpose, one_row, df, notes, source_tables}

Tables covered: NamedConfigs, NamedConfigBlocks, NamedConfigData, Components, Hierarchies,
TestDefinition, TestDefinitionHistory, TestDefPoints, TestDefPointsHistory, TestDefAsgms,
ExtBlockTags, SnapOnData, SnapOnDataOwners, DevRevExtProperty, plus lookups
(DeviceRevisions, DeviceTypes, MfrProtocols, Manufacturers, DeviceProtocols, DeviceCategories,
Major/MinorDeviceCategories, Devices, Blocks, BlockAsgms, EventLog, Users).
Empty tables (no sheet, listed in summary notes): TestResults, TestResultAFAL, TestResultPoints,
InstantiableConfigBlocks, InstantiableConfigData, InstantiableBlockAsgms, NamedConfigAsgms,
NamedConfigAssets, HostDeviceDefinition, HostTagParams, Routes, RouteFolders, RouteTags.
"""
import os
import re
import json
import struct
import sqlite3
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

DB_PATH = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/AmsDb.sqlite"
OUT_DIR = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/build/out"
PREV_JSON = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/build/prev_templates.json"
PREV_XLSX = r"C:/Users/bacon/我的雲端硬碟/@@新機組資料備份/AMS/20260910_AMS解析.xlsx"
KEY = "templates"

OLE_EPOCH = pd.Timestamp("1899-12-30")
LARGEDAY = 49710          # DBW_HIGHRES_LARGEDAY = 'still current / open' sentinel (AmsSp_AssignNewTagTestDef_1)
TW = pd.Timedelta(hours=8)


# ---------------------------------------------------------------- helpers
def eventid_to_utc(day, frac):
    """EventIdDay/EventIdFraction -> UTC datetime (AmsUdf_EventIdDayFractionToDateTime:
    VT_DATE day serial since 1899-12-30 + fraction/2^31 day)."""
    day = pd.to_numeric(day, errors="coerce")
    frac = pd.to_numeric(frac, errors="coerce")
    ok = day.notna() & frac.notna() & (day > 0) & (day < LARGEDAY)
    out = pd.Series(pd.NaT, index=day.index, dtype="datetime64[ns]")
    sec = (day[ok].astype("float64") * 86400.0 + frac[ok].astype("float64") / 2147483648.0 * 86400.0)
    out[ok] = OLE_EPOCH + pd.to_timedelta(np.round(sec.values * 1000.0), unit="ms")
    return out


def serial_to_utc(serial):
    """float OLE day serial (day + fraction) -> UTC datetime"""
    s = pd.to_numeric(serial, errors="coerce")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    ok = s.notna()
    out[ok] = OLE_EPOCH + pd.to_timedelta(np.round(s[ok].values * 86400.0), unit="s")
    return out


def utc_text(ts):
    return ts.dt.strftime("%Y-%m-%d %H:%M:%S").where(ts.notna(), None)


def to_tw(ts):
    return ts + TW


def yn(s):
    return s.map(lambda v: None if pd.isna(v) else ("是" if int(v) else "否"))


def ole_to_dt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if -1 <= v < 100000:
        return OLE_EPOCH + pd.to_timedelta(round(v * 86400.0), unit="s")
    return None


FLOAT32_NOVALUE = 0x7F7FFFFD  # bytes FD FF 7F 7F = 'not set' placeholder in templates
DTYPE_NAME = {
    3: "ASCII字串(3)",
    4: "整數int32(4)",
    5: "無號整數uint32(5)",
    6: "浮點數float32(6)",
    7: "倍精度float64(7)",
    8: "日期OLE double(8)",
    12: "Unicode字串UTF-16LE(12)",
}


def decode_param(dtype, raw):
    """return (numeric_value, text_value, datetime_value)"""
    if raw is None:
        return (None, None, None)
    if isinstance(raw, str):
        raw = raw.encode("latin-1", "replace")
    b = bytes(raw)
    try:
        if dtype == 12:
            return (None, b.decode("utf-16-le", "replace").rstrip("\x00"), None)
        if dtype == 3:
            return (None, b.decode("latin-1", "replace").rstrip("\x00"), None)
        if dtype == 4 and len(b) == 4:
            v = struct.unpack("<i", b)[0]
            return (v, str(v), None)
        if dtype == 5 and len(b) == 4:
            v = struct.unpack("<I", b)[0]
            return (v, str(v), None)
        if dtype == 6 and len(b) == 4:
            u = struct.unpack("<I", b)[0]
            v = struct.unpack("<f", b)[0]
            if u == FLOAT32_NOVALUE:
                return (v, "未設定(7F7FFFFD)", None)
            return (v, repr(v), None)
        if dtype == 7 and len(b) == 8:
            v = struct.unpack("<d", b)[0]
            return (v, repr(v), None)
        if dtype == 8 and len(b) == 8:
            v = struct.unpack("<d", b)[0]
            d = ole_to_dt(v)
            return (v, d.strftime("%Y-%m-%d %H:%M:%S") if d is not None else repr(v), d)
    except Exception:
        pass
    return (None, "0x" + b.hex(), None)


_FF_NAME = re.compile(r"^[0-9A-Fa-f]{8}:[0-9A-Fa-f]{2}$")
_FF_HEX = re.compile(r"^01(4[4-9])([0-9A-Fa-f]*)$")
FF_HEX_TYPE = {"44": "D 字串/八位元組串", "45": "E 有號整數", "46": "F 無號整數/列舉/位元串", "47": "G 浮點數float32", "49": "I 日期時間(OLE double)"}


def decode_ff_hex(text):
    """FF (C/S 紀錄) 參數值：ParamDataType=3 的 ASCII 內容其實是 hex 字串 '01' + 型別字母 + 小端序 payload。
    型別字母依 FF 標準 TEST_RW 記錄(80020089) 成員順序驗證：D=字串(FF FE FF <len> + UTF-16LE)、E=有號整數、
    F=無號整數(列舉/位元串；與前版工作簿 UnsignedLong 值 1,224/1,224 相符)、G=float32、I=4 bytes + OLE 日期 double。
    return (num, txt, dt, typename) or None"""
    m = _FF_HEX.match(text or "")
    if not m:
        return None
    code, pay = m.group(1).upper(), m.group(2)
    try:
        b = bytes.fromhex(pay)
    except ValueError:
        return None
    tname = FF_HEX_TYPE.get(code, code)
    try:
        if code == "46" and len(b) == 4:
            v = struct.unpack("<I", b)[0]; return (v, str(v), None, tname)
        if code == "45" and len(b) == 4:
            v = struct.unpack("<i", b)[0]; return (v, str(v), None, tname)
        if code == "47" and len(b) == 4:
            v = struct.unpack("<f", b)[0]; return (v, repr(v), None, tname)
        if code == "49" and len(b) == 12:
            v = struct.unpack("<d", b[4:12])[0]; d = ole_to_dt(v)
            return (v, d.strftime("%Y-%m-%d %H:%M:%S") if d is not None else repr(v), d, tname)
        if code == "44":
            if b[:3] == b"\xff\xfe\xff" and len(b) >= 4:
                n = b[3]
                s = b[4:4 + 2 * n].decode("utf-16-le", "replace")
                return (None, s, None, tname)
            s = b.decode("latin-1")
            if all(32 <= ord(ch) < 127 for ch in s):
                return (None, s, None, tname)
            return (None, "0x" + pay.lower(), None, tname)
    except Exception:
        pass
    return (None, "0x" + pay.lower(), None, tname)


def read_sql(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


# ---------------------------------------------------------------- lookups
def load_revision_lookup(conn):
    sql = """
    select r.AmsDevRevId, r.DeviceRevision, r.Name as RevName, r.Description as RevDesc,
           t.AmsDevTypeId, t.DeviceType as DeviceTypeCode, t.Name as TypeName, t.Description as TypeDesc,
           mp.MfrProtocolId, mp.MfrId, m.Name as MfrName, p.Name as Protocol,
           mj.Name as MajorCat, mi.Name as MinorCat
    from DeviceRevisions r
    left join DeviceTypes t on t.AmsDevTypeId = r.AmsDevTypeId
    left join MfrProtocols mp on mp.MfrProtocolId = t.MfrProtocolId
    left join Manufacturers m on m.AmsMfrNameId = mp.AmsMfrNameId
    left join DeviceProtocols p on p.ProtocolId = mp.ProtocolId
    left join DeviceCategories dc on dc.DeviceCategoryId = r.DeviceCategoryId
    left join MajorDeviceCategories mj on mj.MajorDeviceCategoryId = dc.MajorDeviceCategoryId
    left join MinorDeviceCategories mi on mi.MinorDeviceCategoryId = dc.MinorDeviceCategoryId
    """
    return read_sql(conn, sql)


def load_current_tags(conn):
    """DeviceKey -> current AMS tag (ExtBlockTags via open BlockAsgms, EventIdDayOut=49710)."""
    return read_sql(conn, f"""select bl.DeviceKey, e.ExtBlockTag as AmsTag, e.ExtBlockTagKey as AmsTagKey
                              from BlockAsgms a join Blocks bl on bl.BlockKey=a.BlockKey
                              join ExtBlockTags e on e.ExtBlockTagKey=a.ExtBlockTagKey
                              where a.EventIdDayOut={LARGEDAY}""").drop_duplicates("DeviceKey")


_TAG_OK = re.compile(r"^[A-Za-z0-9_.\-]+$")


def tag_abnormal(t):
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return None
    return "否" if _TAG_OK.match(str(t)) else "是"


def load_prev_templates():
    """previous workbook 26_附錄_範本 (2,178 rows) -> dict name(stripped)->row ; cached JSON built from xlsx"""
    rows = None
    if os.path.exists(PREV_JSON):
        try:
            rows = json.load(open(PREV_JSON, encoding="utf-8"))
        except Exception:
            rows = None
    if rows is None and os.path.exists(PREV_XLSX):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(PREV_XLSX, read_only=True)
            ws = wb["26_附錄_範本"]
            rows = []
            for row in ws.iter_rows(min_row=5, values_only=True):
                if row[0] is None:
                    continue
                rows.append({"alias": row[0], "name": row[1], "type": row[2], "protrev": row[3],
                             "devrev": row[4], "mfr": row[5], "model": row[6], "rev": row[7], "blocks": row[8]})
            wb.close()
            try:
                json.dump(rows, open(PREV_JSON, "w", encoding="utf-8"), ensure_ascii=False)
            except Exception:
                pass
        except Exception:
            rows = None
    out = {}
    if rows:
        for r in rows:
            n = (r.get("name") or "").strip()
            out.setdefault(n, r)
    return out


CONFIG_TYPE = {
    "T": "T 組態範本(Template)",
    "C": "C 裝置特性紀錄(Characteristics)",
    "S": "S 標準組態(Standard Configurations 資料夾內的出廠 UC)",
}
BLOCK_TYPE = {"R": "R 資源區塊", "T": "T 轉換區塊", "F": "F 功能區塊", "": "(裝置層)"}
VALUE_MODE = {"h": "h 歷史值", "o": "o 離線/範本值"}
PARAM_KIND = {"P": "P DD參數", "D": "D 非DD內部參數(NonDDL；frsi.* 裝置警報描述)"}


# ---------------------------------------------------------------- sheet 1: 範本清單
def sheet_templates(conn, rev):
    nc = read_sql(conn, "select ConfigKey, AmsDevRevId, ConfigName, ConfigType, UniversalId, H275, LastModified from NamedConfigs")
    nc = nc[nc.ConfigKey >= 0].copy()
    blocks = read_sql(conn, """select ConfigKey, count(*) as nblk,
                                      group_concat(BlockIndex || ':' || BlockType, ' ') as blist
                               from (select * from NamedConfigBlocks order by ConfigKey, BlockIndex) group by ConfigKey""")
    data = read_sql(conn, """select ConfigKey,
                                    count(*) as nrows,
                                    count(distinct BlockIndex || '|' || ParamName) as nparams,
                                    count(distinct BlockIndex) as ndatablk,
                                    sum(case when ValueMode='h' then 1 else 0 end) as n_h,
                                    sum(case when ValueMode='o' then 1 else 0 end) as n_o,
                                    min(EventIdDay + EventIdFraction/2147483648.0) as first_ev,
                                    max(EventIdDay + EventIdFraction/2147483648.0) as last_ev
                             from NamedConfigData group by ConfigKey""")
    comp = read_sql(conn, """select c.TableKey as ConfigKey, h.AreaName, c.AreaId
                             from Components c left join Hierarchies h on h.AreaId=c.AreaId
                             where c.TableName='NamedConfigs'""")
    devs = read_sql(conn, f"""select AmsDevRevId, count(*) as ndev,
                                    group_concat(AmsTag, ', ') as tags
                             from (select d.AmsDevRevId, coalesce(e.ExtBlockTag, d.AmsDeviceTag) as AmsTag
                                   from Devices d
                                   left join Blocks bl on bl.DeviceKey=d.DeviceKey and bl.BlockIndex=0
                                   left join BlockAsgms a on a.BlockKey=bl.BlockKey and a.EventIdDayOut={LARGEDAY}
                                   left join ExtBlockTags e on e.ExtBlockTagKey=a.ExtBlockTagKey
                                   where d.DeviceKey>=0 order by 2)
                             group by AmsDevRevId""")
    devs["tags"] = devs["tags"].map(lambda s: s if s is None or len(s) <= 200 else s[:200] + " …")
    same = nc.groupby("AmsDevRevId").agg(n_T=("ConfigType", lambda s: int((s == "T").sum())),
                                        n_C=("ConfigType", lambda s: int((s == "C").sum())),
                                        n_S=("ConfigType", lambda s: int((s == "S").sum()))).reset_index()

    df = nc.merge(rev, on="AmsDevRevId", how="left").merge(blocks, on="ConfigKey", how="left") \
           .merge(data, on="ConfigKey", how="left").merge(comp, on="ConfigKey", how="left") \
           .merge(devs, on="AmsDevRevId", how="left").merge(same, on="AmsDevRevId", how="left")

    prev = load_prev_templates()
    prev_rows = df["ConfigName"].map(lambda n: prev.get((n or "").strip()))
    lm = pd.to_datetime(df["LastModified"], errors="coerce")

    out = pd.DataFrame({
        "範本鍵 (ConfigKey)": df.ConfigKey,
        "範本名稱 (ConfigName)": df.ConfigName,
        "範本類型 (ConfigType)": df.ConfigType.map(CONFIG_TYPE).fillna(df.ConfigType),
        "手持機/使用者組態 (H275)": yn(df.H275),
        "所在資料夾 (Components→Hierarchies)": df.AreaName.fillna("(無;範本庫)"),
        "通訊協定 (DeviceProtocols.Name)": df.Protocol,
        "製造商 (Manufacturers.Name)": df.MfrName,
        "型號 (DeviceTypes.Name)": df.TypeName,
        "型號代碼 (DeviceType)": df.DeviceTypeCode,
        "版次 (DeviceRevision)": df.DeviceRevision,
        "版次名稱 (DeviceRevisions.Name)": df.RevName,
        "協定版本 (UniversalId)": df.UniversalId,
        "主類別 (MajorDeviceCategories)": df.MajorCat,
        "次類別 (MinorDeviceCategories)": df.MinorCat,
        "裝置版次鍵 (AmsDevRevId)": df.AmsDevRevId,
        "廠內使用此版次的裝置數 (Devices)": df.ndev.fillna(0).astype(int),
        "廠內使用此版次": df.ndev.map(lambda v: "是" if pd.notna(v) and v > 0 else "否"),
        "廠內裝置 AMS 位號 (ExtBlockTag 現行, 最多200字)": df.tags,
        "FF區塊數 (NamedConfigBlocks)": df.nblk.fillna(0).astype(int),
        "FF區塊清單 (BlockIndex:BlockType)": df.blist,
        "有資料的區塊數 (NamedConfigData.BlockIndex)": df.ndatablk.fillna(0).astype(int),
        "參數數 (distinct BlockIndex+ParamName)": df.nparams.fillna(0).astype(int),
        "參數資料列數 (NamedConfigData rows)": df.nrows.fillna(0).astype(int),
        "離線值列數 (ValueMode=o)": df.n_o.fillna(0).astype(int),
        "歷史值列數 (ValueMode=h)": df.n_h.fillna(0).astype(int),
        "參數最早事件 (台灣)": to_tw(serial_to_utc(df.first_ev)),
        "參數最新事件 (台灣)": to_tw(serial_to_utc(df.last_ev)),
        "最後修改 (LastModified) (台灣)": to_tw(lm),
        "最後修改 UTC (LastModified)": utc_text(lm),
        "同版次範本數 T/C/S": df.apply(lambda r: f"{int(r.n_T)}/{int(r.n_C)}/{int(r.n_S)}", axis=1),
        "前版工作簿有此範本": prev_rows.map(lambda r: "是" if r else "否"),
        "前版範本別名 (T0xxxx)": prev_rows.map(lambda r: r["alias"] if r else None),
        "前版區塊數": prev_rows.map(lambda r: r["blocks"] if r else None),
    })
    out = out.sort_values(["範本類型 (ConfigType)", "製造商 (Manufacturers.Name)", "範本名稱 (ConfigName)"],
                          key=lambda s: s.astype(str).str.lower()).reset_index(drop=True)

    n_T = int((nc.ConfigType == "T").sum()); n_C = int((nc.ConfigType == "C").sum()); n_S = int((nc.ConfigType == "S").sum())
    n_prev = int((out["前版工作簿有此範本"] == "是").sum())
    used = out[out["廠內使用此版次"] == "是"]
    ct = used["範本類型 (ConfigType)"].str[:1]
    notes = [
        f"NamedConfigs 共 2,713 列 = 1 列 sentinel(ConfigKey=-1 'Default none (do not remove)', 已排除) + T {n_T} + C {n_C} + S {n_S}。",
        "ConfigType 解碼(依 _modules 原始碼)：T=組態範本 Template(AmsSp_GetDeviceTemplateName_1/CreateUserConfiguration_1 以 ConfigType='T' 建立)；"
        "C=裝置特性紀錄 Characteristics record(AmsSp_NamedConfig_GetTypeInfo_1: ConfigType=N'C' AND H275=0 為該裝置版次的特性紀錄，名稱 Char!製造商Id!型號代碼!版次)；"
        "S=10 列 H275=1 且掛在 Components/Hierarchies AreaId=-4 'Standard Configurations' 的出廠標準組態，名稱如 '3051 HART R10 UC-US'(UC=User Configuration，US/Int=美制/國際單位)；注意 _modules 沒有任何程序處理 ConfigType='S'(AmsSp_GetUserConfigHeaders_1 只列 ConfigType='T' AND H275=1)，'S'=Standard 為依資料夾與命名推斷。",
        "H275=1 依 AmsSp_GetUserConfigHeaders_1/CreateUserConfiguration_1 註解 = 使用者組態(User Configuration，可下載到 475/AMS Trex 手持機)；H275=0 = 系統範本。",
        f"前版工作簿 26_附錄_範本 有 2,178 個(T 2,171 + C 7)；本庫以名稱比對到 {n_prev} 個。差異 535 = C 多 524 個(本庫 531 個 Char! 特性紀錄全部 LastModified 2025-12-11 UTC，前版 .ams_merge 匯出只含廠內裝置有用到的 7 個 C) + S 10 個(前版未匯出) + sentinel 1。",
        f"廠內 1,928 裝置共用 43 個 AmsDevRevId；其中 36 個版次有對應範本/特性紀錄(對應 T {int((ct == 'T').sum())}、C {int((ct == 'C').sum())}、S {int((ct == 'S').sum())} 列)，7 個版次(含 GE Mark VIe I/O 等)沒有任何 NamedConfigs 列。",
        "HART 範本沒有 NamedConfigBlocks 列(FF區塊數=0)，參數全部掛在 BlockIndex 0；FF 範本才有 R/T/F 區塊清單。'有資料的區塊數' 由 NamedConfigData 計算，可看出 HART 範本/UC 實際含參數的區塊。",
        "只有 2 個 T 範本是廠內人員自建(LastModified 非 2024-11-20 安裝日)：ConfigKey 2710 'GE PHRA' (2025-04-29 UTC)、2711 'GE YSIL' (2025-05-06 UTC)。其餘 2,169 個 T 範本為 2024-11-20 09:01~09:18 UTC 安裝時批次匯入。",
        f"參數數/列數：NamedConfigData 318,558 列、306,891 個 (ConfigKey,BlockIndex,ParamName) 鍵；{int((out['參數資料列數 (NamedConfigData rows)'] == 0).sum()):,} 個範本(多為 HART 舊型號範本)完全沒有參數資料，只是名稱佔位。",
        "UniversalId 依 AmsSp_GetNamedConfigInfo_1 = ProtocolRev(HART universal revision 3/4/5/6/7，其中 3、4 各僅 4、3 個舊範本；FF/Conventional/PROFIBUS 為 0)。",
        "時間欄：LastModified 為 SQL datetime2 (UTC)，'(台灣)' 欄 = UTC+8；事件時間由 EventIdDay/EventIdFraction 依 AmsUdf_EventIdDayFractionToDateTime 換算。",
    ]
    return {"name": "範本清單", "purpose": "AMS 範本庫(NamedConfigs)全清單：型號/版次/類型/區塊與參數數/是否廠內使用/與前版工作簿比對",
            "one_row": "一個 NamedConfig(組態範本 T / 裝置特性紀錄 C / 使用者組態 S)",
            "df": out, "notes": notes,
            "source_tables": ["NamedConfigs", "NamedConfigBlocks", "NamedConfigData", "Components", "Hierarchies", "DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "DeviceCategories", "MajorDeviceCategories", "MinorDeviceCategories", "Devices"]}


# ---------------------------------------------------------------- sheet 2: 範本參數現值
def sheet_template_params(conn, rev):
    d = read_sql(conn, """select d.ConfigKey, d.BlockIndex, d.ParamKind, d.ParamName, d.ValueMode, d.ParamDataType,
                                 d.ParamDataSize, d.ParamData, d.GroupPath, d.EventIdDay, d.EventIdFraction, d.Archived
                          from NamedConfigData d""")
    nc = read_sql(conn, "select ConfigKey, ConfigName, ConfigType, AmsDevRevId from NamedConfigs")
    nb = read_sql(conn, "select ConfigKey, BlockIndex, BlockType from NamedConfigBlocks")
    total = len(d)
    d["_ord"] = d.EventIdDay.astype("int64") * 2147483648 + d.EventIdFraction.astype("int64")
    d = d.sort_values(["ConfigKey", "BlockIndex", "ParamName", "_ord"], ascending=[True, True, True, False])
    hist = d.groupby(["ConfigKey", "BlockIndex", "ParamName"]).size().rename("nver").reset_index()
    d = d.drop_duplicates(["ConfigKey", "BlockIndex", "ParamName"], keep="first").reset_index(drop=True)
    d = d.merge(hist, on=["ConfigKey", "BlockIndex", "ParamName"], how="left")

    dec = [decode_param(t, b) for t, b in zip(d.ParamDataType.values, d.ParamData.values)]
    # FF C/S 紀錄：ParamDataType=3 但內容為 hex 編碼的型別化值 ('01'+型別字母+payload)，再解一層
    fftype = [None] * len(dec)
    n_ff = 0
    for i, (t, pn) in enumerate(zip(d.ParamDataType.values, d.ParamName.values)):
        if t == 3 and _FF_NAME.match(str(pn)):
            r = decode_ff_hex(dec[i][1])
            if r is not None:
                dec[i] = r[:3]; fftype[i] = r[3]; n_ff += 1
    d["val_num"] = [x[0] for x in dec]
    d["val_txt"] = [x[1] for x in dec]
    d["val_dt"] = [x[2] for x in dec]
    d["fftype"] = fftype

    d = d.merge(nc, on="ConfigKey", how="left").merge(nb, on=["ConfigKey", "BlockIndex"], how="left") \
         .merge(rev[["AmsDevRevId", "MfrName", "TypeName", "DeviceRevision", "Protocol"]], on="AmsDevRevId", how="left")
    ev = eventid_to_utc(d.EventIdDay, d.EventIdFraction)
    parts = d.ParamName.astype(str).str.split(".", n=1, expand=True)
    pshort = parts[0]
    pid = parts[1] if parts.shape[1] > 1 else pd.Series([None] * len(d))
    n_multi = int((d.nver > 1).sum())

    out = pd.DataFrame({
        "範本鍵 (ConfigKey)": d.ConfigKey,
        "範本名稱 (ConfigName)": d.ConfigName,
        "範本類型 (ConfigType)": d.ConfigType.map(CONFIG_TYPE).fillna(d.ConfigType),
        "製造商": d.MfrName, "型號": d.TypeName, "版次": d.DeviceRevision, "協定": d.Protocol,
        "區塊索引 (BlockIndex)": d.BlockIndex,
        "區塊類型 (BlockType)": d.BlockType.map(BLOCK_TYPE).fillna(d.BlockType).fillna("(HART/裝置層)"),
        "參數名稱": pshort,
        "參數ID (DD item id 等)": pid,
        "完整參數名 (ParamName)": d.ParamName,
        "參數種類 (ParamKind)": d.ParamKind.map(PARAM_KIND).fillna(d.ParamKind),
        "值模式 (ValueMode)": d.ValueMode.map(VALUE_MODE).fillna(d.ValueMode),
        "資料型別 (ParamDataType)": d.ParamDataType.map(DTYPE_NAME).fillna(d.ParamDataType.astype(str)),
        "FF 值型別 (hex 前綴 01xx)": d.fftype,
        "資料長度 (ParamDataSize)": d.ParamDataSize,
        "值(數值)": pd.to_numeric(d.val_num, errors="coerce"),
        "值(文字/解碼)": d.val_txt,
        "值(日期) (台灣)": pd.to_datetime(d.val_dt, errors="coerce") + TW,
        "群組路徑 (GroupPath)": d.GroupPath,
        "此值的事件時間 (台灣)": to_tw(ev),
        "此值的事件時間 UTC": utc_text(ev),
        "事件日 (EventIdDay)": d.EventIdDay,
        "事件分數 (EventIdFraction)": d.EventIdFraction,
        "歷史版本數 (同鍵列數)": d.nver,
        "已封存 (Archived)": yn(d.Archived),
    })
    out = out.sort_values(["範本鍵 (ConfigKey)", "區塊索引 (BlockIndex)", "完整參數名 (ParamName)"]).reset_index(drop=True)
    notes = [
        f"NamedConfigData 原始 {total:,} 列；本表取每個 (ConfigKey, BlockIndex, ParamName) 依 EventIdDay/EventIdFraction 最新的一列，共 {len(out):,} 列(與 AmsSp_NamedConfigData_GetBlockData_1 的 TOP 1 ... ORDER BY EventIdDay DESC, EventIdFraction DESC 相同邏輯)；'歷史版本數' >1 者({n_multi:,} 鍵)表示範本內該參數曾被改值。",
        "ParamData 解碼規則(與 BlockData 同編碼，依樣本位元組驗證)：12=UTF-16LE 字串；3=單位元組 ASCII 字串(如 tag/message/descriptor；FF 參數見下條)；4=有號 int32 LE(80FFFFFF=-128, FFFFFFFF=-1)；5=無號 uint32 LE(僅 universal_revision/polling_address 等 69 列)；6=float32 LE，FD FF 7F 7F(=3.4028e38)為'未設定'佔位標為 未設定(7F7FFFFD)；7=float64 LE(totalizer_forward 9A99999999993C40=28.6)；8=float64 OLE 日期序號(參數名皆為 date/current_date/stdz_date 等；34732.75=1995-02-02 18:00)。所有列的 ParamDataSize 都與型別長度一致(4/8 bytes)，無需 hex 退回；值(文字) 以 '0x' 開頭的 4 列是裝置字串參數本身的內容(如 ABB EDP300 uiLoopVoltage='0x1a8d')。",
        f"FF 特性紀錄(C)與標準組態(S)的參數名為 'item id(8 hex):成員(2 hex)'，ParamDataType=3 但內容是 hex 編碼的型別化值 '01'+型別字母+小端序 payload，共 {n_ff:,} 列已再解一層並在 'FF 值型別' 欄標示："
        "D=字串(FF FE FF <長度> + UTF-16LE，如 TAG_DESC)、E=有號整數、F=無號整數/列舉/位元串(與前版工作簿 27_附錄_範本參數 UnsignedLong 值 1,224 列全部相符)、G=float32、I=4 bytes + OLE 日期 double(UPDATE_EVT 時間戳等)；型別字母依 FF 標準 TEST_RW 記錄(80020089 成員 01~0D 型別順序)驗證。",
        "值(日期) 只對型別 8 與 FF 型別 I 有值，依全域慣例 +8h 標為台灣時間；注意其中 HART 'date' 等裝置日期參數為裝置內儲存的日期(OLE 序號，非事件時間)，1,107 列中 184 列帶非零時刻(如 18:00/19:00)，+8h 後可能跨日，原始序號請看 值(數值)/值(文字)。其餘型別為 NaT。值(數值) 對字串型別為空。",
        "ValueMode：h=歷史值(history)、o=離線值(offline，範本設定值)，依 AmsSp_GetNamedConfigParamValueMode_1 註解。ParamKind：P=DD 參數；D=AMS 內部非 DD 參數(前版工作簿 27 標為 NonDDL；內容為 frsi.AlarmBlockIndex / frsi.DeviceAlarm.* 裝置警報描述，僅 C 特性紀錄有)；與前版 27_附錄_範本參數 kind 欄 1,370 列 1:1 對應(DDL↔P、NonDDL↔D)，mode 'Normal'↔ValueMode 'h'。",
        "GroupPath 全部為 NULL(318,558 列)，AmsSp_SetNamedConfigParamGroupPath_1 從未被使用；Archived 全部為 0。",
        "參數名格式 '名稱.DD項目ID(hex).0000.0000'；此表以 '.' 拆成 參數名稱 與 參數ID。",
        "所有 7,698 個 (EventIdDay, EventIdFraction) 都在 EventLog 中；範本參數事件日期落在 1996~2019 年(EventIdDay 35107~43693)，為 Emerson 出廠範本原始建檔時間，非本廠操作。",
    ]
    return {"name": "範本參數現值", "purpose": "每個範本每個區塊每個參數的最新解碼值(離線範本值/歷史值)",
            "one_row": "一個 (範本, 區塊, 參數) 的最新值", "df": out, "notes": notes,
            "source_tables": ["NamedConfigData", "NamedConfigs", "NamedConfigBlocks", "DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols"]}


# ---------------------------------------------------------------- sheet 3: 測試定義
TEST_TYPE = {99: "99 現場裝置校正 (Field Device)", 2: "2 流量驗證 (Flow Verification)", 5: "5 外部實驗室 (External Lab)"}
INTERVAL_UNITS = {0: "0 無", 1: "1 天", 2: "2 週", 3: "3 月", 4: "4 年"}


def _tri(v):
    if pd.isna(v):
        return None
    v = int(v)
    return {1: "是", 0: "否", -1: "不適用(-1)"}.get(v, str(v))


def _testdef_frame(df, with_event=False):
    base = {
        "測試定義ID (TestDefinitionId)": df.TestDefinitionId,
        "名稱 (Name)": df.Name,
        "測試類型 (Type)": df.Type.map(TEST_TYPE).fillna(df.Type.astype(str)),
        "校正週期 (DefCalibrationInterval)": df.DefCalibrationInterval,
        "週期單位 (DefIntervalUnits)": df.DefIntervalUnits.map(INTERVAL_UNITS).fillna(df.DefIntervalUnits.astype(str)),
        "關鍵服務 (CriticalService)": df.CriticalService.map(_tri),
        "通知限值% (DefNotificationLimit)": df.DefNotificationLimit,
        "調整限值% (DefAdjustmentLimit)": df.DefAdjustmentLimit,
        "最大誤差限值% (DefMaxErrorLimit)": df.DefMaxErrorLimit,
        "零點誤差限值% (DefZeroErrorLimit)": df.DefZeroErrorLimit,
        "量程誤差限值% (DefSpanErrorLimit)": df.DefSpanErrorLimit,
        "線性誤差限值% (DefLinearityErrorLimit)": df.DefLinearityErrorLimit,
        "遲滯誤差限值% (DefHysteresisErrorLimit)": df.DefHysteresisErrorLimit,
        "使用零點誤差 (DefUseZeroError)": df.DefUseZeroError.map(_tri),
        "使用量程誤差 (DefUseSpanError)": df.DefUseSpanError.map(_tri),
        "使用線性誤差 (DefUseLinearityError)": df.DefUseLinearityError.map(_tri),
        "使用遲滯誤差 (DefUseHysteresisError)": df.DefUseHysteresisError.map(_tri),
        "校正器供電 (DefCalPowerSource)": df.DefCalPowerSource.map(_tri),
        "校正器產生輸入 (DefCalGenerateInput)": df.DefCalGenerateInput.map(_tri),
        "校正器量測輸入 (DefCalMeasureInput)": df.DefCalMeasureInput.map(_tri),
        "校正器量測輸出 (DefCalMeasureOutput)": df.DefCalMeasureOutput.map(_tri),
        "測試點數 (DefNumberOfTestPoints)": df.DefNumberOfTestPoints,
        "設置說明 (DefSetupInstructions)": df.DefSetupInstructions,
        "收尾說明 (DefCleanupInstructions)": df.DefCleanupInstructions,
        "校驗器材質 (ProverMaterial)": df.ProverMaterial,
    }
    if with_event:
        ev = eventid_to_utc(df.EventIdDay, df.EventIdFraction)
        base["歷史版本時間 (台灣)"] = to_tw(ev)
        base["歷史版本時間 UTC"] = utc_text(ev)
        base["事件日 (EventIdDay)"] = df.EventIdDay
        base["事件分數 (EventIdFraction)"] = df.EventIdFraction
    return pd.DataFrame(base)


def sheet_testdefs(conn):
    td = read_sql(conn, "select * from TestDefinition order by TestDefinitionId")
    tdh = read_sql(conn, "select * from TestDefinitionHistory order by TestDefinitionId, EventIdDay, EventIdFraction")
    pts = read_sql(conn, "select * from TestDefPoints order by TestDefinitionId, TestPointId")
    ptsh = read_sql(conn, "select * from TestDefPointsHistory order by TestDefinitionId, EventIdDay, EventIdFraction, TestPointId")
    asg_n = read_sql(conn, f"""select TestDefinitionId, sum(case when EventIdDayOut={LARGEDAY} then 1 else 0 end) as n_open,
                                     count(*) as n_all from TestDefAsgms group by TestDefinitionId""")
    tags_n = read_sql(conn, "select TestDefinitionId, count(*) as n_tags from ExtBlockTags group by TestDefinitionId")

    cur = _testdef_frame(td)
    cur.insert(0, "紀錄來源", "現行 (TestDefinition)")
    his = _testdef_frame(tdh, with_event=True)
    his.insert(0, "紀錄來源", "歷史 (TestDefinitionHistory)")
    allrows = pd.concat([cur, his], ignore_index=True)
    ptxt = {k: "; ".join(f"{int(r.TestPointId)}:{r.DefTestPoint:g}%" for r in g.itertuples())
            for k, g in pts.groupby("TestDefinitionId")}
    allrows["測試點 (TestDefPoints, 點號:%)"] = allrows["測試定義ID (TestDefinitionId)"].map(ptxt)
    allrows = allrows.merge(asg_n.rename(columns={"TestDefinitionId": "測試定義ID (TestDefinitionId)", "n_open": "現行指派位號數 (TestDefAsgms open)", "n_all": "指派列數 (TestDefAsgms all)"}),
                            on="測試定義ID (TestDefinitionId)", how="left")
    allrows = allrows.merge(tags_n.rename(columns={"TestDefinitionId": "測試定義ID (TestDefinitionId)", "n_tags": "ExtBlockTags.TestDefinitionId 指向此定義的位號數"}),
                            on="測試定義ID (TestDefinitionId)", how="left")
    for c in ("現行指派位號數 (TestDefAsgms open)", "指派列數 (TestDefAsgms all)", "ExtBlockTags.TestDefinitionId 指向此定義的位號數"):
        allrows[c] = allrows[c].fillna(0).astype(int)
    allrows = allrows.sort_values(["測試定義ID (TestDefinitionId)", "紀錄來源"]).reset_index(drop=True)

    p1 = pd.DataFrame({"紀錄來源": "現行 (TestDefPoints)", "測試定義ID (TestDefinitionId)": pts.TestDefinitionId,
                       "測試點號 (TestPointId)": pts.TestPointId, "測試點 %量程 (DefTestPoint)": pts.DefTestPoint,
                       "測試類型 (Type)": pts.Type.map(TEST_TYPE).fillna(pts.Type.astype(str))})
    evh = eventid_to_utc(ptsh.EventIdDay, ptsh.EventIdFraction)
    p2 = pd.DataFrame({"紀錄來源": "歷史 (TestDefPointsHistory)", "測試定義ID (TestDefinitionId)": ptsh.TestDefinitionId,
                       "測試點號 (TestPointId)": ptsh.TestPointId, "測試點 %量程 (DefTestPoint)": ptsh.DefTestPoint,
                       "測試類型 (Type)": ptsh.Type.map(TEST_TYPE).fillna(ptsh.Type.astype(str)),
                       "歷史版本時間 (台灣)": to_tw(evh), "歷史版本時間 UTC": utc_text(evh)})
    points = pd.concat([p1, p2], ignore_index=True)
    points["測試定義名稱"] = points["測試定義ID (TestDefinitionId)"].map(dict(zip(td.TestDefinitionId, td.Name)))
    points = points[["紀錄來源", "測試定義ID (TestDefinitionId)", "測試定義名稱", "測試點號 (TestPointId)", "測試點 %量程 (DefTestPoint)", "測試類型 (Type)", "歷史版本時間 (台灣)", "歷史版本時間 UTC"]]

    notes = [
        "TestDefinition 只有 AMS 預設 3 筆(ID -3 Default Flow Verification、-2 Default External Lab、-1 Default Field Device)，沒有廠內自訂測試定義；TestDefinitionHistory/TestDefPointsHistory 各只有一版(EventIdDay 25569 = 1970-01-01，即安裝預設)。",
        "校正週期單位 DefIntervalUnits 依 AmsSp_Operation_GetProjectedCalibrationDate_1 註解：0=none, 1=days, 2=weeks, 3=months, 4=years；三個預設定義 DefCalibrationInterval=3 但 Units=0(無) → 校正排程實際未啟用。",
        "Type 代碼：99=Field Device(現場裝置校正，5 測試點 0/25/50/75/100%)、2=Flow Verification(3 點 0/50/100%)、5=External Lab；為 AMS Calibration Assistant 型別代碼(_modules 未列常數，依名稱與 TestDefPoints 對應)。",
        "誤差限值欄位單位為 % 量程；Default Field Device 通知 0.6%/調整 0.4%/最大 0.5%。DefCalPowerSource 等 -1 表示不適用。",
        "TestResults / TestResultAFAL / TestResultPoints 皆為空：本廠從未在 AMS 中登錄校正結果。",
        "6 列(3 定義 × 現行/歷史)內容完全相同(歷史版=安裝預設)：DefCalibrationInterval 皆 3、CriticalService 皆 否、Span/Linearity 限值皆 0、DefUse* 皆 否、設置說明/收尾說明/校驗器材質 皆空字串；ExtBlockTags/TestDefAsgms 指派數只有 -1 Default Field Device 非 0(-2/-3 為 0；sentinel 位號 -1 另有一列指到 -2)。",
    ]
    return [
        {"name": "測試定義", "purpose": "校正測試定義(現行+歷史)含週期、誤差限值、測試點與指派數", "one_row": "一個測試定義的一個版本",
         "df": allrows, "notes": notes, "source_tables": ["TestDefinition", "TestDefinitionHistory", "TestDefPoints", "TestDefAsgms", "ExtBlockTags"]},
        {"name": "測試定義測試點", "purpose": "各測試定義的測試點(%量程)，現行與歷史", "one_row": "一個測試定義的一個測試點",
         "df": points, "notes": ["TestDefPoints 8 列 + TestDefPointsHistory 8 列；歷史版本 EventIdDay 25569 = 1970-01-01 安裝預設。"],
         "source_tables": ["TestDefPoints", "TestDefPointsHistory", "TestDefinition"]},
    ]


# ---------------------------------------------------------------- sheet 4: 測試定義指派 (TestDefAsgms)
def sheet_testdef_asgms(conn, rev):
    a = read_sql(conn, """select t.ExtBlockTagKey, t.TestDefinitionId, t.EventIdDayIn, t.EventIdFractionIn, t.EventIdDayOut, t.EventIdFractionOut,
                                 e.ExtBlockTag, e.ExtBlockTagDesc, e.TestDefinitionId as TagTestDefId,
                                 td.Name as TestDefName
                          from TestDefAsgms t
                          left join ExtBlockTags e on e.ExtBlockTagKey = t.ExtBlockTagKey
                          left join TestDefinition td on td.TestDefinitionId = t.TestDefinitionId""")
    cur = read_sql(conn, f"""select b.ExtBlockTagKey, b.BlockKey, bl.DeviceKey, d.AmsDeviceTag, d.Identifier, d.AmsDevRevId
                             from BlockAsgms b join Blocks bl on bl.BlockKey=b.BlockKey join Devices d on d.DeviceKey=bl.DeviceKey
                             where b.EventIdDayOut={LARGEDAY}""").drop_duplicates("ExtBlockTagKey")
    cur = cur.merge(rev[["AmsDevRevId", "MfrName", "TypeName", "DeviceRevision", "Protocol"]], on="AmsDevRevId", how="left")
    ev_in = read_sql(conn, "select EventIdDay, EventIdFraction, Description, UserKey from EventLog").drop_duplicates(["EventIdDay", "EventIdFraction"])
    users = read_sql(conn, "select UserKey, UserName from Users")
    ev_in = ev_in.merge(users, on="UserKey", how="left").drop(columns=["UserKey"])

    a = a.merge(cur, on="ExtBlockTagKey", how="left")
    a = a.merge(ev_in.rename(columns={"EventIdDay": "EventIdDayIn", "EventIdFraction": "EventIdFractionIn", "Description": "DescIn", "UserName": "UserIn"}),
                on=["EventIdDayIn", "EventIdFractionIn"], how="left")
    a = a.merge(ev_in.rename(columns={"EventIdDay": "EventIdDayOut", "EventIdFraction": "EventIdFractionOut", "Description": "DescOut", "UserName": "UserOut"}),
                on=["EventIdDayOut", "EventIdFractionOut"], how="left")
    tin = eventid_to_utc(a.EventIdDayIn, a.EventIdFractionIn)
    tout = eventid_to_utc(a.EventIdDayOut, a.EventIdFractionOut)
    is_open = a.EventIdDayOut == LARGEDAY
    out = pd.DataFrame({
        "位號 (ExtBlockTag)": a.ExtBlockTag,
        "位號鍵 (ExtBlockTagKey)": a.ExtBlockTagKey,
        "指派狀態": np.where(is_open, "現行 (EventIdDayOut=49710)", "已結束"),
        "測試定義ID (TestDefinitionId)": a.TestDefinitionId,
        "測試定義名稱": a.TestDefName,
        "指派開始 (台灣)": to_tw(tin), "指派開始 UTC": utc_text(tin),
        "指派結束 (台灣)": to_tw(tout).where(~is_open, pd.NaT), "指派結束 UTC": utc_text(tout).where(~is_open, None),
        "開始事件說明 (EventLog)": a.DescIn, "開始事件使用者": a.UserIn,
        "結束事件說明 (EventLog)": a.DescOut.where(~is_open, None), "結束事件使用者": a.UserOut.where(~is_open, None),
        "位號含異常字元": a.ExtBlockTag.map(tag_abnormal),
        "目前裝置內部位號 (Devices.AmsDeviceTag)": a.AmsDeviceTag,
        "裝置ID (Identifier)": a.Identifier,
        "製造商": a.MfrName, "型號": a.TypeName, "版次": a.DeviceRevision, "協定": a.Protocol,
        "目前裝置鍵 (DeviceKey)": a.DeviceKey, "目前區塊鍵 (BlockKey)": a.BlockKey,
        "位號主檔測試定義 (ExtBlockTags.TestDefinitionId)": a.TagTestDefId,
        "事件日入 (EventIdDayIn)": a.EventIdDayIn, "事件分數入 (EventIdFractionIn)": a.EventIdFractionIn,
        "事件日出 (EventIdDayOut)": a.EventIdDayOut, "事件分數出 (EventIdFractionOut)": a.EventIdFractionOut,
    })
    out = out.sort_values(["指派狀態", "位號 (ExtBlockTag)", "指派開始 (台灣)"]).reset_index(drop=True)
    n_closed = int((~is_open).sum())
    n_nodev = int(out[(out["指派狀態"].str.startswith("現行")) & out["目前裝置鍵 (DeviceKey)"].isna()].shape[0])
    notes = [
        f"TestDefAsgms 3,505 列 = {int(is_open.sum()):,} 列現行指派(EventIdDayOut=49710 為 DBW_HIGHRES_LARGEDAY '仍有效' 哨兵；3,483 個實際位號各 1 列 + sentinel 位號 -1 'None' 2 列) + {n_closed} 列已結束(位號被重新指派/改名時 AmsSp 關閉舊列再開新列；結束事件皆為 EventLog 'AMS tag assignment'，使用者皆 HMI\\GEAdmin)。",
        "全部位號都指向 TestDefinitionId -1 'Default Field Device'(sentinel 位號 -1 另有 -2 一列)；本廠未做任何自訂測試定義指派。",
        "AmsSp_AssignNewTagTestDef_1：建立位號時插入 TestDefAsgms(EventIdDayOut=49710) 並更新 ExtBlockTags.TestDefinitionId；EventIdDayIn/FractionIn 為 EventLog 中該次位號指派事件。",
        f"'目前裝置' 由 BlockAsgms 現行列(EventIdDayOut=49710, 1,928 列)取得；{n_nodev} 列現行指派的位號目前沒有掛任何裝置(其中 1,540 個是試車期間位號改名後遺留的舊位號、16 個從未掛過裝置，見 位號主檔)。Devices.AmsDeviceTag 為裝置內部的 tag 欄位(HART 8 字短位號等)，與 AMS 位號(ExtBlockTag)不同。",
        "已結束列中 JK661X1-1D4A 有 2 段歷史(3 列)、其餘 19 個位號各 1 段；多為 2024-12~2025-01 試車期間位號改掛裝置。",
    ]
    return {"name": "測試定義指派", "purpose": "每個位號(ExtBlockTag)指派到哪個測試定義、何時開始/結束、目前掛哪台裝置",
            "one_row": "一個位號的一段測試定義指派期間", "df": out, "notes": notes,
            "source_tables": ["TestDefAsgms", "ExtBlockTags", "TestDefinition", "BlockAsgms", "Blocks", "Devices", "EventLog", "Users", "DeviceRevisions"]}


# ---------------------------------------------------------------- sheet 5: 位號主檔 (ExtBlockTags)
def sheet_ext_tags(conn, rev):
    e = read_sql(conn, "select ExtBlockTagKey, ExtBlockTag, ExtBlockTagDesc, TestDefinitionId from ExtBlockTags")
    td = read_sql(conn, "select TestDefinitionId, Name as TestDefName from TestDefinition")
    ba = read_sql(conn, """select b.ExtBlockTagKey, b.BlockKey, b.EventIdDayIn, b.EventIdFractionIn, b.EventIdDayOut, b.EventIdFractionOut,
                                  bl.DeviceKey, bl.BlockIndex, d.AmsDeviceTag, d.Identifier, d.AmsDevRevId
                           from BlockAsgms b join Blocks bl on bl.BlockKey=b.BlockKey join Devices d on d.DeviceKey=bl.DeviceKey""")
    ba["_in"] = ba.EventIdDayIn.astype("float64") + ba.EventIdFractionIn.astype("float64") / 2147483648.0
    cur = ba[ba.EventIdDayOut == LARGEDAY].drop_duplicates("ExtBlockTagKey")
    cur = cur.merge(rev[["AmsDevRevId", "MfrName", "TypeName", "DeviceRevision", "Protocol"]], on="AmsDevRevId", how="left")
    agg = ba.groupby("ExtBlockTagKey").agg(n_asg=("BlockKey", "size"), first_in=("_in", "min"),
                                          n_dev=("DeviceKey", "nunique"),
                                          devs=("AmsDeviceTag", lambda s: ", ".join(sorted(set(map(str, s)))))).reset_index()
    tda = read_sql(conn, f"select ExtBlockTagKey, count(*) as n_td, sum(case when EventIdDayOut={LARGEDAY} then 1 else 0 end) as n_td_open from TestDefAsgms group by ExtBlockTagKey")
    e = e.merge(td, on="TestDefinitionId", how="left").merge(cur, on="ExtBlockTagKey", how="left") \
         .merge(agg, on="ExtBlockTagKey", how="left").merge(tda, on="ExtBlockTagKey", how="left")
    cur_in = eventid_to_utc(e.EventIdDayIn, e.EventIdFractionIn)
    out = pd.DataFrame({
        "位號 (ExtBlockTag)": e.ExtBlockTag,
        "位號鍵 (ExtBlockTagKey)": e.ExtBlockTagKey,
        "位號說明 (ExtBlockTagDesc)": e.ExtBlockTagDesc,
        "狀態": np.where(e.ExtBlockTagKey < 0, "sentinel(-1 系統保留列)",
                       np.where(e.DeviceKey.notna(), "現行(掛有裝置)", np.where(e.n_asg.fillna(0) > 0, "舊位號(曾掛裝置，改名/改掛後遺留)", "孤兒位號(從未掛裝置)"))),
        "位號含異常字元": e.ExtBlockTag.map(tag_abnormal),
        "目前裝置內部位號 (Devices.AmsDeviceTag)": e.AmsDeviceTag,
        "目前裝置ID (Identifier)": e.Identifier,
        "製造商": e.MfrName, "型號": e.TypeName, "版次": e.DeviceRevision, "協定": e.Protocol,
        "目前裝置鍵 (DeviceKey)": e.DeviceKey, "目前區塊鍵 (BlockKey)": e.BlockKey,
        "目前掛載開始 (台灣)": to_tw(cur_in), "目前掛載開始 UTC": utc_text(cur_in),
        "歷來掛載裝置數 (BlockAsgms distinct DeviceKey)": e.n_dev.fillna(0).astype(int),
        "歷來掛載列數 (BlockAsgms)": e.n_asg.fillna(0).astype(int),
        "歷來掛載裝置位號": e.devs,
        "首次掛載 (台灣)": to_tw(serial_to_utc(e.first_in)),
        "測試定義 (ExtBlockTags.TestDefinitionId)": e.TestDefinitionId,
        "測試定義名稱": e.TestDefName,
        "測試定義指派列數 (TestDefAsgms)": e.n_td.fillna(0).astype(int),
    })
    out = out.sort_values(["狀態", "位號 (ExtBlockTag)"]).reset_index(drop=True)
    orphans = out[out["狀態"].str.startswith("孤兒")]
    stale = out[out["狀態"].str.startswith("舊位號")]
    cur_ab = out[(out["狀態"].str.startswith("現行")) & (out["位號含異常字元"] == "是")]
    notes = [
        f"ExtBlockTags 3,484 列 = 1 列 sentinel(-1 'None'，狀態另標) + 3,483 個實際位號；BlockAsgms 現行列 1,928 = 每台裝置一個現行位號；{len(stale):,} 個舊位號(曾掛裝置、BlockAsgms 已全部關閉；多為 2024-12 試車期間位號改名，例如 JK7L0PT → JK7L0PT-xxxx，AMS 保留舊 ExtBlockTags 列)；{len(orphans)} 個孤兒位號從未掛過裝置：{', '.join(orphans['位號 (ExtBlockTag)'].astype(str).str.strip().tolist())}。",
        "孤兒位號中 'D30BL001                  d'(含尾部空白與 d)、'G11HAD30BL001_old'、'G11HAH11BT001_old'、'82_S807AF0426C' 疑為誤鍵/改名遺留，建議在 AMS 中清除。",
        f"'位號含異常字元'=是 表示位號含 A-Z/0-9/_/./- 以外字元(空白、控制字元、非 ASCII)；現行位號有 {len(cur_ab)} 個異常，例如 ' G12LAB65BF001'(前導空白)、'S10MAC10BP021 '(尾隨空白)、14 個位號是時間戳(如 '10/21/2025 14:03:22.037'、'12/16/2025 16:51:46.933'；13 台 ABB TTX200 series + 1 台 Rosemount 8712EM/8732EM，2025-10~12 新增裝置時 AMS 以時間當位號)、'50 BL001                  ù'(HART 長位號填滿空白+亂碼)。全部 ExtBlockTags 有 761 個異常，多為舊位號。",
        "Devices.AmsDeviceTag 是裝置內部 tag 欄位(HART short tag 8 字/long tag 32 字，讀自裝置)，1,579 台與 AMS 位號不同(AMS 位號多加 '-1C4A' 等後綴)，758 台內容為空白填充或亂碼。",
        "ExtBlockTagDesc 除 sentinel 外全部空白，本廠未在 AMS 位號填說明。所有位號 TestDefinitionId=-1 (Default Field Device)。",
        "'歷來掛載' 由 BlockAsgms 全部列統計(含已結束列)，可看出位號曾換過幾台裝置。",
    ]
    return {"name": "位號主檔", "purpose": "AMS 位號(ExtBlockTags)主檔：目前掛載裝置、歷來掛載、孤兒位號、測試定義", "one_row": "一個 AMS 位號",
            "df": out, "notes": notes, "source_tables": ["ExtBlockTags", "BlockAsgms", "Blocks", "Devices", "TestDefinition", "TestDefAsgms", "DeviceRevisions"]}


# ---------------------------------------------------------------- sheet 6: SnapOn 資料
SNAP_TYPE = {1: "1 HART 裝置檔案資訊", 3: "3 FF 裝置檔案資訊"}


def _parse_snap(b):
    if b is None:
        return {}
    try:
        txt = bytes(b).decode("utf-16-le", "replace").rstrip("\x00").strip()
    except Exception:
        return {"_raw": "0x" + bytes(b).hex()}
    res = {"_xml": txt}
    try:
        root = ET.fromstring(txt)
        di = root.find("DeviceInfo")
        if di is not None:
            res.update({k: v for k, v in di.attrib.items()})
        res["_blocks"] = [bl.attrib.get("BlockIndex") for bl in root.iter("Block")]
        res["_root"] = root.tag
    except Exception as ex:
        res["_err"] = str(ex)
    return res


def sheet_snapon(conn, rev):
    s = read_sql(conn, """select s.SnapOnDataId, s.BlockKey, s.EventIdDay, s.EventIdFraction, s.SnapOnDataOwnerId, o.Name as OwnerName,
                                 s.SnapOnDataNote, s.SnapOnDataType, s.SnapOnData,
                                 bl.DeviceKey, bl.BlockIndex, d.AmsDeviceTag, d.Identifier, d.AmsDevRevId, d.ProtocolRevision
                          from SnapOnData s
                          left join SnapOnDataOwners o on o.SnapOnDataOwnerId = s.SnapOnDataOwnerId
                          left join Blocks bl on bl.BlockKey = s.BlockKey
                          left join Devices d on d.DeviceKey = bl.DeviceKey""")
    s = s.merge(rev[["AmsDevRevId", "MfrName", "TypeName", "DeviceTypeCode", "DeviceRevision", "Protocol", "MfrId"]], on="AmsDevRevId", how="left")
    s = s.merge(load_current_tags(conn), on="DeviceKey", how="left")
    pdf = pd.DataFrame([_parse_snap(b) for b in s.SnapOnData.values])
    for c in ("Manufacturer", "DeviceType", "DeviceRevision", "DDRevision", "_blocks", "_xml"):
        if c not in pdf.columns:
            pdf[c] = None
    pdf = pdf.rename(columns={"DeviceRevision": "XDeviceRevision"})
    mfrs = read_sql(conn, """select mp.MfrId, p.Name as Protocol, m.Name as MfrNameX from MfrProtocols mp
                             join Manufacturers m on m.AmsMfrNameId=mp.AmsMfrNameId join DeviceProtocols p on p.ProtocolId=mp.ProtocolId""").drop_duplicates(["MfrId", "Protocol"])
    types = read_sql(conn, """select mp.MfrId, p.Name as Protocol, t.DeviceType as DeviceTypeCode, t.Name as TypeNameX from DeviceTypes t
                              join MfrProtocols mp on mp.MfrProtocolId=t.MfrProtocolId join DeviceProtocols p on p.ProtocolId=mp.ProtocolId""").drop_duplicates(["MfrId", "Protocol", "DeviceTypeCode"])
    x = pd.concat([s.reset_index(drop=True), pdf.reset_index(drop=True)], axis=1)
    x["xm"] = pd.to_numeric(x["Manufacturer"], errors="coerce")
    x["xt"] = pd.to_numeric(x["DeviceType"], errors="coerce")
    x["xr"] = pd.to_numeric(x["XDeviceRevision"], errors="coerce")
    x["xdd"] = pd.to_numeric(x["DDRevision"], errors="coerce")
    mfrs["MfrId"] = pd.to_numeric(mfrs.MfrId, errors="coerce"); types["MfrId"] = pd.to_numeric(types.MfrId, errors="coerce")
    types["DeviceTypeCode"] = pd.to_numeric(types.DeviceTypeCode, errors="coerce")
    x = x.merge(mfrs.rename(columns={"MfrId": "xm"}), on=["xm", "Protocol"], how="left")
    x = x.merge(types.rename(columns={"MfrId": "xm", "DeviceTypeCode": "xt"}), on=["xm", "Protocol", "xt"], how="left")
    ev = eventid_to_utc(x.EventIdDay, x.EventIdFraction)
    evl = read_sql(conn, "select EventIdDay, EventIdFraction, Description from EventLog").drop_duplicates(["EventIdDay", "EventIdFraction"])
    x = x.merge(evl, on=["EventIdDay", "EventIdFraction"], how="left")

    def note_devid(row):
        n = row.SnapOnDataNote
        if row.SnapOnDataType == 1 and isinstance(n, str) and len(n) >= 24:
            try:
                return int(n[16:24], 16)
            except Exception:
                return None
        return None
    x["note_devid"] = x.apply(note_devid, axis=1)
    idn = pd.to_numeric(x.Identifier, errors="coerce")
    match = np.where(x.SnapOnDataType == 1, x.note_devid == idn, x.SnapOnDataNote == x.Identifier)
    rev_match = (x.xr == pd.to_numeric(x.DeviceRevision, errors="coerce"))
    blocks = x["_blocks"]
    out = pd.DataFrame({
        "AMS 位號 (ExtBlockTag 現行)": x.AmsTag,
        "裝置內部位號 (Devices.AmsDeviceTag)": x.AmsDeviceTag,
        "資料類型 (SnapOnDataType)": x.SnapOnDataType.map(SNAP_TYPE).fillna(x.SnapOnDataType.astype(str)),
        "備註/裝置識別 (SnapOnDataNote)": x.SnapOnDataNote,
        "備註解碼 HART 裝置ID (十進位)": x.note_devid,
        "備註與 Devices.Identifier 相符": np.where(match, "是", "否"),
        "裝置序號/識別 (Devices.Identifier)": x.Identifier,
        "XML 製造商代碼 (DeviceInfo.Manufacturer)": x.xm,
        "XML 製造商名稱 (MfrProtocols→Manufacturers)": x.MfrNameX,
        "XML 型號代碼 (DeviceInfo.DeviceType)": x.xt,
        "XML 型號名稱 (DeviceTypes)": x.TypeNameX,
        "XML 裝置版次 (DeviceInfo.DeviceRevision)": x.xr,
        "XML DD版次 (DeviceInfo.DDRevision)": x.xdd,
        "XML 區塊數 (FileInfo/Block)": blocks.map(lambda v: len(v) if isinstance(v, list) else None),
        "XML 區塊清單 (BlockIndex)": blocks.map(lambda v: " ".join(str(i) for i in v) if isinstance(v, list) else None),
        "裝置登錄製造商": x.MfrName, "裝置登錄型號": x.TypeName, "裝置登錄型號代碼": x.DeviceTypeCode,
        "裝置登錄版次 (DeviceRevisions.DeviceRevision)": x.DeviceRevision,
        "XML版次與裝置登錄版次一致": np.where(rev_match, "是", "否"),
        "協定": x.Protocol, "HART協定版本 (Devices.ProtocolRevision)": x.ProtocolRevision,
        "資料擁有者 (SnapOnDataOwners.Name)": x.OwnerName,
        "記錄事件時間 (台灣)": to_tw(ev), "記錄事件時間 UTC": utc_text(ev),
        "事件說明 (EventLog, 若存在)": x.Description,
        "事件日 (EventIdDay)": x.EventIdDay, "事件分數 (EventIdFraction)": x.EventIdFraction,
        "SnapOn資料ID (SnapOnDataId)": x.SnapOnDataId, "區塊鍵 (BlockKey)": x.BlockKey, "區塊索引 (BlockIndex)": x.BlockIndex, "裝置鍵 (DeviceKey)": x.DeviceKey,
        "原始 XML": x["_xml"],
    })
    out = out.sort_values(["資料類型 (SnapOnDataType)", "AMS 位號 (ExtBlockTag 現行)"]).reset_index(drop=True)
    n_nomatch = int((out["備註與 Devices.Identifier 相符"] == "否").sum())
    n_revdiff = int((out["XML版次與裝置登錄版次一致"] == "否").sum())
    n_noev = int(out["事件說明 (EventLog, 若存在)"].isna().sum())
    mm = out[out["XML版次與裝置登錄版次一致"] == "否"]
    mm_txt = "; ".join(f"{k[0]} 登錄版次{k[1]}→XML版次{k[2]:g} {v} 台"
                       for k, v in mm.groupby(["裝置登錄型號", "裝置登錄版次 (DeviceRevisions.DeviceRevision)", "XML 裝置版次 (DeviceInfo.DeviceRevision)"]).size()
                       .sort_values(ascending=False).head(8).items()) if len(mm) else ""
    notes = [
        "SnapOnData 1,789 列 = 1,789 台裝置各一列(BlockKey 皆為裝置層 BlockIndex 0)；擁有者皆 'AmsDeviceManager'；SnapOnDataType 1=HART(1,562 台) / 3=FF(227 台)。廠內 1,928 台中有 139 台沒有此紀錄(FF 124 台、HART 15 台)。",
        "SnapOnData 為 UTF-16LE XML：<DeviceFiles><DeviceInfo Manufacturer DeviceType DeviceRevision DDRevision/><FileInfo><Block BlockIndex=…/>…</FileInfo></DeviceFiles>，記錄 AMS 為該裝置載入的 DD 檔案資訊(製造商/型號/版次/DD 版次)與含 DD 檔的區塊索引；HART 只有 Block 0。",
        f"SnapOnDataNote 解碼：FF = 裝置 Identifier(FF device id，227/227 相符)；HART = 28 字 hex，第 17~24 字為 HART 裝置 ID(device id)，轉十進位 = Devices.Identifier(1,562/1,562 相符)，前 16 字為固定前綴(含擴充型號碼，未完全解讀)。不相符 {n_nomatch} 列。",
        f"XML DeviceInfo.DeviceRevision 與 AMS 登錄版次(DeviceRevisions.DeviceRevision)不一致 {n_revdiff} 台，全為 HART：{mm_txt}。表示 AMS 為該裝置載入的 DD 檔版次與裝置登錄版次不同(裝置實際版次無對應 DD 時 AMS 以相近版次 DD 開啟，或登錄版次非裝置回報值)，建議核對 GE PHRA(228 台)與 E+H iTEMP TMT82(274 台)。",
        f"EventIdDay/Fraction 是寫入 SnapOnData 時的事件；{n_noev} 列在 EventLog 找不到對應事件(EventLog 只保留部分歷史)，其餘為 '裝置/資料庫同步' 事件。",
        "XML 製造商/型號名稱由 MfrProtocols.MfrId + DeviceTypes.DeviceType 依協定反查；查無時為空。",
    ]
    return {"name": "SnapOn裝置檔案資訊", "purpose": "解碼 SnapOnData XML：每台裝置的 DD 檔案資訊(製造商/型號/版次/DD版次/區塊)與識別碼核對",
            "one_row": "一台裝置(裝置層區塊)的 SnapOn DeviceFiles 紀錄", "df": out, "notes": notes,
            "source_tables": ["SnapOnData", "SnapOnDataOwners", "Blocks", "Devices", "DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "EventLog"]}


# ---------------------------------------------------------------- sheet 7: DevRevExtProperty (GSD)
def sheet_devrev_ext(conn, rev):
    p = read_sql(conn, "select AmsDevRevId, ExtPropertyName, ExtPropertyValue from DevRevExtProperty")
    p = p.merge(rev, on="AmsDevRevId", how="left")
    ndev = read_sql(conn, "select AmsDevRevId, count(*) as ndev from Devices where DeviceKey>=0 group by AmsDevRevId")
    p = p.merge(ndev, on="AmsDevRevId", how="left")
    out = pd.DataFrame({
        "裝置版次鍵 (AmsDevRevId)": p.AmsDevRevId,
        "屬性名稱 (ExtPropertyName)": p.ExtPropertyName,
        "屬性值 (ExtPropertyValue)": p.ExtPropertyValue,
        "協定": p.Protocol, "製造商": p.MfrName, "型號": p.TypeName, "型號代碼": p.DeviceTypeCode, "版次": p.DeviceRevision, "版次名稱": p.RevName,
        "廠內使用此版次的裝置數": p.ndev.fillna(0).astype(int),
    }).sort_values(["協定", "製造商", "型號"]).reset_index(drop=True)
    return {"name": "裝置版次擴充屬性", "purpose": "DevRevExtProperty：PROFIBUS 裝置版次對應的 GSD 檔識別(GsdId)", "one_row": "一個裝置版次的一個擴充屬性",
            "df": out, "notes": ["23 列全部為 ExtPropertyName='GsdId'，對應 PROFIBUS-DP/PA 裝置版次(HostDeviceDefinition.GSDId 亦指向此，但該表為空)；廠內無 PROFIBUS 裝置使用。"],
            "source_tables": ["DevRevExtProperty", "DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "Devices"]}


# ---------------------------------------------------------------- sheet 0: 總覽
EMPTY_TABLES = ["TestResults", "TestResultAFAL", "TestResultPoints", "InstantiableConfigBlocks", "InstantiableConfigData",
                "InstantiableBlockAsgms", "NamedConfigAsgms", "NamedConfigAssets", "HostDeviceDefinition", "HostTagParams",
                "Routes", "RouteFolders", "RouteTags"]


def sheet_summary(conn, sheets):
    counts = dict(read_sql(conn, "select table_name, row_count from _tables").values.tolist())
    desc = {
        "NamedConfigs": "範本/特性紀錄/使用者組態主檔", "NamedConfigBlocks": "FF 範本的區塊清單(R/T/F)", "NamedConfigData": "範本參數值(二進位)",
        "Components": "範本所在資料夾(Hierarchies AreaId)", "Hierarchies": "資料夾樹(System/User Configurations/Standard/Migrated/Handheld…)",
        "TestDefinition": "校正測試定義", "TestDefinitionHistory": "測試定義歷史", "TestDefPoints": "測試點", "TestDefPointsHistory": "測試點歷史",
        "TestDefAsgms": "位號→測試定義指派", "ExtBlockTags": "AMS 位號主檔", "SnapOnData": "裝置 DD 檔案資訊 XML", "SnapOnDataOwners": "SnapOn 資料擁有者",
        "DevRevExtProperty": "裝置版次擴充屬性(GsdId)",
    }
    rows = [{"資料表": t, "列數": counts.get(t), "說明": dsc, "狀態": "有資料" if counts.get(t) else "空"} for t, dsc in desc.items()]
    rows += [{"資料表": t, "列數": counts.get(t, 0), "說明": "本域空表(未使用功能)", "狀態": "空"} for t in EMPTY_TABLES]
    sdf = pd.DataFrame(rows)
    sh = pd.DataFrame([{"資料表": f"[表] {s['name']}", "列數": len(s["df"]), "說明": s["purpose"], "狀態": f"{s['df'].shape[1]} 欄"} for s in sheets])
    out = pd.concat([sh, sdf], ignore_index=True)
    notes = [
        "本域空表(未建立工作表)：" + "、".join(EMPTY_TABLES) + " —— 表示本廠未使用：校正結果登錄(TestResults*)、可實例化 FF 功能區塊組態(Instantiable*)、範本指派/資產綁定(NamedConfigAsgms/Assets)、DeltaV/Host 位號參數(HostDeviceDefinition/HostTagParams)、巡檢路線(Routes*)。",
        "Hierarchies 中 User Configurations(-3) 底下有 Standard(-4)/Migrated(-5)/Handheld(-6) 三個資料夾；Components 只有 10 列，全部是 S 型使用者組態放在 Standard Configurations，Migrated/Handheld 資料夾為空。",
        "所有時間欄位：資料庫存 UTC，'(台灣)' 欄 = UTC+8。",
    ]
    return {"name": "範本域總覽", "purpose": "本域各資料表列數/用途與各工作表索引", "one_row": "一個資料表或一張工作表", "df": out, "notes": notes,
            "source_tables": ["_tables"] + list(desc.keys()) + EMPTY_TABLES}


# ---------------------------------------------------------------- build
def build(conn):
    rev = load_revision_lookup(conn)
    sheets = []
    sheets.append(sheet_templates(conn, rev))
    sheets.append(sheet_template_params(conn, rev))
    sheets.extend(sheet_testdefs(conn))
    sheets.append(sheet_testdef_asgms(conn, rev))
    sheets.append(sheet_ext_tags(conn, rev))
    sheets.append(sheet_snapon(conn, rev))
    sheets.append(sheet_devrev_ext(conn, rev))
    summary = sheet_summary(conn, sheets)
    return [summary] + sheets


if __name__ == "__main__":
    import time
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        sheets = build(conn)
    finally:
        conn.close()
    for s in sheets:
        df = s["df"]
        print(f"{s['name']}: rows={len(df):,} cols={df.shape[1]}")
        safe = re.sub(r"[\\/:*?\"<>|]", "_", s["name"])
        df.to_csv(os.path.join(OUT_DIR, f"{KEY}__{safe}.csv"), index=False, encoding="utf-8-sig")
    print(f"done in {time.time()-t0:.1f}s")
