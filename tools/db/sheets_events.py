# -*- coding: utf-8 -*-
"""
sheets_events.py  --  AMS Device Manager (AmsDb) 事件稽核紀錄 (EventLog) 解碼模組
Domain key: events
build(conn) -> list[dict]  (conn = sqlite3 connection to AmsDb.sqlite)

Decode rules (evidence in notes of each sheet):
 * EventTime is UTC (AmsSp_LogEventSummary_1: "@strEventTimeAsGMT ... this time is in GMT"); 台灣 = UTC+8.
 * EventIdDay/EventIdFraction = OLE date serial day + fraction*2^31 (AmsUdf_EventIdDayFractionToDateTime).
 * ComputerId = IPv4 packed big-endian into a signed 32-bit int (AmsSp_LogEventSummary_1: "@iComputerNameId ... the computer IP address");
   2130706433 -> 127.0.0.1, 167873846 -> 10.1.141.54, -1408185981 -> 172.16.201.131.
 * Tag at event time: BlockAsgms(ExtBlockTagKey, device-level BlockKey, [EventIdIn, EventIdOut)) exactly as AmsUdf_BuildATStmtForRead joins it.
"""
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

DB_PATH = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/AmsDb.sqlite"
OUT_DIR = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/build/out"
KEY = "events"
TW_OFFSET = pd.Timedelta(hours=8)

# --------------------------------------------------------------------------------------
# 碼表
# --------------------------------------------------------------------------------------
CATEGORY_ZH = {
    -1: "未知 (Unknown；2 筆為哨兵列 do not remove、1 筆為 1996 FMS 舊版匯入)",
    0: "無分類 (含離線組態編輯)",
    1: "AMS 操作變更 (組態寫入/方法執行/裝置識別/位號更名/建立範本)",
    2: "巡檢站變更 (roving station)",
    3: "行動裝置變更",
    4: "校正：As-found 不合格, As-left 不合格",
    5: "校正：As-found 不合格, As-left 合格",
    6: "儀器狀態",
    7: "使用者狀態",
    8: "網路狀態",
    9: "封存",
    10: "封存-清除",
    11: "載入",
    12: "資料庫備份 (Backup)",
    13: "資料庫還原 (Restore)",
    14: "由檔案合併匯入 (Merge from File；範本/裝置定義 .mrg)",
    15: "由其他 AMS 資料庫合併",
    16: "資料庫匯出 (Extract → .ams_merge)",
    17: "壓縮 (Compact)",
    18: "驗證-修復",
    19: "測試方案變更",
    20: "裝置警報發生",
    21: "裝置警報清除",
    22: "HART Interchange 狀態設定",
    23: "HART Interchange 狀態清除",
    24: "校正：As-found 合格, As-left 不合格",
    25: "校正：As-found 合格, As-left 合格",
    26: "校正：As-found 合格, As-left N/A",
    27: "校正：As-found 不合格, As-left N/A",
    28: "現場變更 (伺服器讀取裝置時偵測到與資料庫的差異)",
    29: "SNAP-ON 應用程式變更",
    30: "應用程式警報發生",
    31: "應用程式警報清除",
    36: "以逾期校正器執行校正",
    37: "新增測試設備",
    38: "超過通知限值",
    39: "外部實驗室校正",
    40: "校正：As-found N/A, As-left N/A",
    41: "校正：As-found N/A, As-left 不合格",
    42: "校正：As-found N/A, As-left 合格",
    43: "裝置同步成功－無差異",
    44: "裝置同步成功－有差異",
    45: "裝置同步失敗",
    46: "登入",
    47: "登出",
    48: "手動事件",
    49: "位號／測試方案指派變更 (AMS tag assignment)",
    50: "SNAP-ON 應用程式執行之變更",
    51: "應用程式 (AMS 啟動/關閉)",
    52: "刪除裝置",
    53: "系統選項變更",
    54: "啟用警報監視",
    55: "停用警報監視",
    56: "使用者密碼變更",
    57: "新使用者",
    58: "使用者帳號變更 (新增/更名/群組/權限)",
    59: "電子簽章",
    60: "裝置警報條件解除抑制",
    61: "裝置警報條件抑制",
    62: "診斷警報發生",
    63: "診斷警報清除",
    64: "裝置警報已抑制",
    65: "裝置警報已停用",
    66: "驗證通過",
    67: "驗證失敗",
    68: "裝置掃描開始",
    69: "裝置掃描完成",
    70: "裝置掃描取消",
    71: "重建階層 (Rebuild Hierarchy)",
    72: "裝置投用 (Commission)",
    73: "裝置停用 (Decommission)",
    74: "警報確認",
    75: "警報監視設定變更",
    76: "加入無線網路",
    77: "AMS Calibration Connector 執行之變更",
    78: "具名組態資料",
    79: "行動裝置授權變更",
    80: "行動裝置同步開始",
    81: "行動裝置同步完成",
    82: "行動裝置傳輸中斷",
    83: "行動裝置啟動/關閉 AMS 連線 App",
    84: "行動裝置偵測到 Command 48 設定",
    85: "發生未授權動作",
    86: "專案建立",
    87: "全域裝置保護啟用",
    88: "全域裝置保護停用",
    89: "個別裝置保護啟用",
    90: "個別裝置保護停用",
    91: "專案刪除",
    92: "專案更名",
    93: "專案完成",
    94: "專案取消完成",
    95: "任務加入專案",
    96: "任務移出專案",
    97: "任務完成",
    98: "任務取消完成",
    99: "裝置警報重複發生已過濾",
}

TYPE_ZH = {
    0: "無/哨兵或未分類",
    1: "裝置組態事件 (Category 1/28/53)",
    2: "指派事件 (Category 49)",
    3: "資料庫維護事件 (Category 12/14/16/52)",
    4: "應用程式/系統/使用者事件 (Category 46/47/51/58/68-71)",
    6: "範本/舊版匯入事件 (Category 1 建立範本、2 巡檢站、14 AmsMergeDoc)",
    8: "裝置同步事件 (Category 43/44/45)",
}

SOURCE_ZH = {
    "Server": "AMS 伺服器服務 (背景輪詢/代寫/同步)",
    "AmsMergeDoc": "合併匯入文件 (.mrg 範本內附事件)",
    "AMS Device Manager Application": "AMS 用戶端程式 (使用者操作)",
    "Database Maintenance": "資料庫維護工具",
    "AMS Device Manager": "AMS Device Manager 主程式",
    "AMS Device Manager - User Manager": "AMS 使用者管理員",
    "FF Polling Application": "FF 警報輪詢程式",
    "ManualInserted": "手動插入 (Emerson 範本)",
    "AMS": "AMS (舊版)",
    "FMS": "FMS (舊版 Fisher-Rosemount)",
    "Install": "安裝程式",
    "none": "無 (哨兵列)",
    "": "空白 (哨兵列)",
}

BLOCKTYPE_ZH = {"": "裝置層級", "F": "功能區塊 (Function)", "T": "轉換區塊 (Transducer)", "R": "資源區塊 (Resource)"}

# 前一版工作簿 20260910_AMS解析.xlsx / 10_事件總帳 (13,682 列) 依 Category 的筆數 (由該表統計)
PREV_WORKBOOK_COUNTS = {-1: 3, 0: 3, 1: 5901, 14: 146, 16: 1, 28: 6001, 46: 3, 49: 1622, 68: 1, 70: 1}
PREV_WORKBOOK_TOTAL = 13682

SENTINEL_DAYS = {25569, 49710}  # 1970-01-01 'Test event log', 2036-02-05 'Large event id'


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def ip_from_computer_id(v):
    if v is None or pd.isna(v):
        return None
    v = int(v)
    if v == -1:
        return "(無) -1"
    u = v & 0xFFFFFFFF
    return f"{(u >> 24) & 255}.{(u >> 16) & 255}.{(u >> 8) & 255}.{u & 255}"


def eventid_to_utc(day, frac):
    # OLE date: day 0 = 1899-12-30; fraction of day = frac / 2^31
    base = pd.Timestamp("1899-12-30")
    return base + pd.to_timedelta(day, unit="D") + pd.to_timedelta(frac / 2147483648.0 * 86400.0, unit="s")


def yesno(s):
    return s.map({True: "是", False: "否"})


def tw(series_utc):
    return series_utc + TW_OFFSET


def _sql(conn, q, params=()):
    return pd.read_sql_query(q, conn, params=params)


# --------------------------------------------------------------------------------------
# core loaders
# --------------------------------------------------------------------------------------
def load_events(conn):
    ev = _sql(conn, """
        SELECT e.EventIdDay, e.EventIdFraction, e.EventTime, e.UserKey, e.ComputerId, e.BlockKey,
               e.EventCode, e.Source, e.Type, e.Category, e.Description, e.OtherBufLen, e.Other,
               e.Archived, e.MoreDetail,
               c.CategoryDesc, u.UserName
        FROM EventLog e
        LEFT JOIN EventCategories c ON c.Category = e.Category
        LEFT JOIN Users u ON u.UserKey = e.UserKey
    """)
    # device / block info (current)
    blk = _sql(conn, """
        SELECT b.BlockKey, b.DeviceKey, b.BlockIndex, b.BlockType,
               d.AmsDeviceTag, d.Identifier, d.AmsDeviceId, d.ProtocolRevision, d.DispositionId,
               dr.Name AS DeviceRevisionName, dr.DeviceRevision,
               dt.Name AS DeviceTypeName,
               m.Name AS Manufacturer, p.Name AS Protocol,
               di.Name AS DispositionName
        FROM Blocks b
        LEFT JOIN Devices d ON d.DeviceKey = b.DeviceKey
        LEFT JOIN DeviceRevisions dr ON dr.AmsDevRevId = d.AmsDevRevId
        LEFT JOIN DeviceTypes dt ON dt.AmsDevTypeId = dr.AmsDevTypeId
        LEFT JOIN MfrProtocols mp ON mp.MfrProtocolId = dt.MfrProtocolId
        LEFT JOIN Manufacturers m ON m.AmsMfrNameId = mp.AmsMfrNameId
        LEFT JOIN DeviceProtocols p ON p.ProtocolId = mp.ProtocolId
        LEFT JOIN Dispositions di ON di.DispositionId = d.DispositionId
        WHERE b.BlockKey >= 0
    """)
    cur_tag = _sql(conn, """
        SELECT d.DeviceKey, t.ExtBlockTag AS CurrentAmsTag
        FROM Blocks d
        JOIN BlockAsgms a ON a.BlockKey = d.BlockKey AND a.EventIdDayOut = 49710
        JOIN ExtBlockTags t ON t.ExtBlockTagKey = a.ExtBlockTagKey
        WHERE d.BlockIndex = 0 AND d.DeviceKey >= 0
    """).drop_duplicates("DeviceKey")
    blk = blk.merge(cur_tag, on="DeviceKey", how="left")
    # tag at event time via BlockAsgms interval (same join as AmsUdf_BuildATStmtForRead)
    tag_at = _sql(conn, """
        SELECT e.EventIdDay, e.EventIdFraction, t.ExtBlockTag AS TagAtEvent, t.ExtBlockTagDesc AS TagDescAtEvent
        FROM EventLog e
        JOIN Blocks b ON b.BlockKey = e.BlockKey
        JOIN Blocks d ON d.DeviceKey = b.DeviceKey AND d.BlockIndex = 0
        JOIN BlockAsgms a ON a.BlockKey = d.BlockKey
             AND (e.EventIdDay > a.EventIdDayIn OR (e.EventIdDay = a.EventIdDayIn AND e.EventIdFraction >= a.EventIdFractionIn))
             AND (e.EventIdDay < a.EventIdDayOut OR (e.EventIdDay = a.EventIdDayOut AND e.EventIdFraction < a.EventIdFractionOut))
        JOIN ExtBlockTags t ON t.ExtBlockTagKey = a.ExtBlockTagKey
        WHERE e.BlockKey >= 0
    """)
    # rows in BlockData tied to each event id (parameter values written by this event)
    bd = _sql(conn, """
        SELECT EventIdDay, EventIdFraction, COUNT(*) AS ParamRows
        FROM BlockData GROUP BY EventIdDay, EventIdFraction
    """)
    # tag-assignment link: events referenced by BlockAsgms In/Out
    asg_in = _sql(conn, """
        SELECT a.EventIdDayIn AS EventIdDay, a.EventIdFractionIn AS EventIdFraction,
               t.ExtBlockTag AS AsgmTagIn
        FROM BlockAsgms a JOIN ExtBlockTags t ON t.ExtBlockTagKey = a.ExtBlockTagKey
    """)
    asg_out = _sql(conn, """
        SELECT a.EventIdDayOut AS EventIdDay, a.EventIdFractionOut AS EventIdFraction,
               t.ExtBlockTag AS AsgmTagOut
        FROM BlockAsgms a JOIN ExtBlockTags t ON t.ExtBlockTagKey = a.ExtBlockTagKey
        WHERE a.EventIdDayOut < 49710
    """)
    asg_in = asg_in.groupby(["EventIdDay", "EventIdFraction"], as_index=False).agg(AsgmTagIn=("AsgmTagIn", lambda s: " | ".join(sorted(set(s)))))
    asg_out = asg_out.groupby(["EventIdDay", "EventIdFraction"], as_index=False).agg(AsgmTagOut=("AsgmTagOut", lambda s: " | ".join(sorted(set(s)))))

    ev = ev.merge(blk, on="BlockKey", how="left")
    ev = ev.merge(tag_at, on=["EventIdDay", "EventIdFraction"], how="left")
    ev = ev.merge(bd, on=["EventIdDay", "EventIdFraction"], how="left")
    ev = ev.merge(asg_in, on=["EventIdDay", "EventIdFraction"], how="left")
    ev = ev.merge(asg_out, on=["EventIdDay", "EventIdFraction"], how="left")

    ev["utc"] = pd.to_datetime(ev["EventTime"], errors="coerce")
    ev["utc_id"] = eventid_to_utc(ev["EventIdDay"].astype("int64"), ev["EventIdFraction"].astype("int64"))
    ev["tw"] = tw(ev["utc"])
    ev["tw_id"] = tw(ev["utc_id"])
    ev["ip"] = ev["ComputerId"].map(ip_from_computer_id)
    ev["Source_clean"] = ev["Source"].fillna("").str.strip()
    ev["is_sentinel"] = ev["EventIdDay"].isin(SENTINEL_DAYS) & (ev["UserKey"] == -1)
    ev["is_device_event"] = ev["BlockKey"] >= 0
    ev["year"] = ev["utc"].dt.year
    return ev


def computer_labels(ev):
    """Label each IP by observed usage (rule-based, evidence in notes)."""
    g = ev.groupby("ip").agg(n=("ip", "size"), first=("utc", "min"), last=("utc", "max"))
    labels = {}
    for ip, r in g.iterrows():
        if ip == "(無) -1":
            labels[ip] = "無 (哨兵列)"
        elif ip == "127.0.0.1":
            labels[ip] = "本機 localhost (伺服器本身或範本內附)"
        elif ip == "0.0.0.0":
            labels[ip] = "0.0.0.0 (舊版 FMS 匯入)"
        elif r["last"] < pd.Timestamp("2020-01-01"):
            labels[ip] = "Emerson 隨附範本/舊資料庫來源 (2019 以前，非本廠)"
        elif ip == "172.16.201.131":
            labels[ip] = "AMS1SVR 伺服器 (推定：事件最多、備份/匯出/刪除裝置/使用者管理皆在此)"
        elif ip in ("172.16.101.17", "10.1.141.54"):
            labels[ip] = "試運轉期間其他站台 (推定：僅 2025-01~05 有事件，伺服器服務帳號亦在此登錄)"
        else:
            labels[ip] = "本廠其他電腦 (2024 以後)"
    return labels


# --------------------------------------------------------------------------------------
# sheet builders
# --------------------------------------------------------------------------------------
def sheet_master(ev, ip_labels):
    df = pd.DataFrame({
        "時間(台灣)": ev["tw"],
        "時間 UTC 原值 (EventTime)": ev["EventTime"],
        "事件ID換算時間(台灣) 含毫秒": ev["tw_id"].dt.floor("ms"),
        "EventIdDay": ev["EventIdDay"],
        "EventIdFraction": ev["EventIdFraction"],
        "類別代碼 (Category)": ev["Category"],
        "類別中文": ev["Category"].map(CATEGORY_ZH).fillna("(未列)"),
        "類別原文 (CategoryDesc)": ev["CategoryDesc"],
        "Type": ev["Type"],
        "Type 意義 (推定)": ev["Type"].map(TYPE_ZH).fillna("(未知)"),
        "來源 (Source)": ev["Source_clean"],
        "來源中文": ev["Source_clean"].map(SOURCE_ZH).fillna("(未列)"),
        "使用者 (UserName)": ev["UserName"],
        "UserKey": ev["UserKey"],
        "電腦 IP (ComputerId 解碼)": ev["ip"],
        "電腦判讀": ev["ip"].map(ip_labels),
        "ComputerId 原值": ev["ComputerId"],
        "事件當時位號 (BlockAsgms)": ev["TagAtEvent"],
        "目前 AMS 位號 (ExtBlockTag 現行指派)": ev["CurrentAmsTag"],
        "位號已變更": yesno((ev["TagAtEvent"].notna()) & (ev["CurrentAmsTag"].notna()) & (ev["TagAtEvent"] != ev["CurrentAmsTag"])),
        "裝置內位號 (Devices.AmsDeviceTag)": ev["AmsDeviceTag"],
        "設備事件": yesno(ev["is_device_event"]),
        "DeviceKey": ev["DeviceKey"].astype("Int64"),
        "BlockKey": ev["BlockKey"],
        "區塊類型 (BlockType)": ev["BlockType"].map(BLOCKTYPE_ZH),
        "區塊索引 (BlockIndex)": ev["BlockIndex"].astype("Int64"),
        "製造商": ev["Manufacturer"],
        "型號 (DeviceTypeName)": ev["DeviceTypeName"],
        "裝置版本": ev["DeviceRevision"].astype("Int64"),
        "協定": ev["Protocol"],
        "裝置ID (Identifier)": ev["Identifier"],
        "描述 (Description)": ev["Description"],
        "其他 (Other)": ev["Other"],
        "OtherBufLen": ev["OtherBufLen"],
        "MoreDetail 有值": yesno(ev["MoreDetail"].notna()),
        "本事件寫入參數筆數 (BlockData)": ev["ParamRows"].fillna(0).astype("int64"),
        "位號指派-指派入 (BlockAsgms In)": ev["AsgmTagIn"],
        "位號指派-指派出 (BlockAsgms Out)": ev["AsgmTagOut"],
        "哨兵列": yesno(ev["is_sentinel"]),
        "年月(台灣)": ev["tw"].dt.strftime("%Y-%m"),
    })
    df = df.sort_values(["EventIdDay", "EventIdFraction"]).reset_index(drop=True)
    return df


def sheet_summary(ev):
    ev2 = ev.copy()
    g = ev2.groupby("Category").agg(
        n=("Category", "size"),
        n_dev=("is_device_event", "sum"),
        first=("tw", "min"), last=("tw", "max"),
        types=("Type", lambda s: ",".join(str(x) for x in sorted(set(s)))),
        sources=("Source_clean", lambda s: " | ".join(sorted(set(s)))),
        users=("UserName", lambda s: " | ".join(sorted(set(x for x in s if x)))),
    ).reset_index()
    desc = ev2.groupby("Category")["CategoryDesc"].first()
    g["CategoryDesc"] = g["Category"].map(desc)
    g["prev"] = g["Category"].map(PREV_WORKBOOK_COUNTS).fillna(0).astype(int)
    df = pd.DataFrame({
        "類別代碼 (Category)": g["Category"],
        "類別中文": g["Category"].map(CATEGORY_ZH),
        "類別原文 (CategoryDesc)": g["CategoryDesc"],
        "本資料庫筆數": g["n"].astype(int),
        "其中設備事件 (BlockKey>=0)": g["n_dev"].astype(int),
        "其中非設備事件 (BlockKey=-1)": (g["n"] - g["n_dev"]).astype(int),
        "前簿 10_事件總帳 筆數": g["prev"],
        "前簿未收錄筆數": (g["n"] - g["prev"]).astype(int),
        "Type 出現值": g["types"],
        "來源 (Source)": g["sources"],
        "使用者": g["users"],
        "最早(台灣)": g["first"],
        "最晚(台灣)": g["last"],
    })
    total = pd.DataFrame([{
        "類別代碼 (Category)": pd.NA, "類別中文": "合計", "類別原文 (CategoryDesc)": "",
        "本資料庫筆數": int(df["本資料庫筆數"].sum()),
        "其中設備事件 (BlockKey>=0)": int(df["其中設備事件 (BlockKey>=0)"].sum()),
        "其中非設備事件 (BlockKey=-1)": int(df["其中非設備事件 (BlockKey=-1)"].sum()),
        "前簿 10_事件總帳 筆數": PREV_WORKBOOK_TOTAL,
        "前簿未收錄筆數": int(df["本資料庫筆數"].sum()) - PREV_WORKBOOK_TOTAL,
        "Type 出現值": "", "來源 (Source)": "", "使用者": "",
        "最早(台灣)": df["最早(台灣)"].min(), "最晚(台灣)": df["最晚(台灣)"].max(),
    }])
    df = pd.concat([df, total], ignore_index=True)
    df["類別代碼 (Category)"] = df["類別代碼 (Category)"].astype("Int64")
    return df


def sheet_cat_month(ev):
    e = ev.copy()
    e["ym"] = e["tw"].dt.strftime("%Y-%m")
    e["cat"] = e["Category"].astype(str) + " " + e["Category"].map(CATEGORY_ZH).fillna("")
    pv = pd.pivot_table(e, index="ym", columns="cat", values="EventIdDay", aggfunc="size", fill_value=0)
    pv["合計"] = pv.sum(axis=1)
    pv = pv.reset_index().rename(columns={"ym": "年月(台灣)"})
    pv.columns.name = None
    return pv


LOGIN_PATTERNS = [
    (re.compile(r"^Successful login of user: (.+?) to AMS Device Manager\.?$"), "登入成功 (AMS Device Manager)"),
    (re.compile(r"^Unsuccessful login of user: (.+?)\.?$"), "登入失敗 (AMS Device Manager)"),
    (re.compile(r"^User '(.+?)' logged in User Manager\.?$"), "登入 User Manager"),
    (re.compile(r"^User '(.+?)' logged off User Manager\.?$"), "登出 User Manager"),
]


def parse_login(desc):
    if not isinstance(desc, str):
        return (None, "其他")
    for rx, kind in LOGIN_PATTERNS:
        m = rx.match(desc.strip())
        if m:
            return (m.group(1), kind)
    return (None, "其他")


def sheet_logins(ev, ip_labels, users_df):
    e = ev[ev["Category"].isin([46, 47])].copy()
    parsed = e["Description"].map(parse_login)
    e["acct_raw"] = parsed.map(lambda t: t[0])
    e["kind"] = parsed.map(lambda t: t[1])
    canon = {u.lower(): u for u in users_df["UserName"].dropna()}
    e["acct"] = e["acct_raw"].map(lambda a: canon.get(a.lower(), a) if isinstance(a, str) else "(無法解析)")
    g = e.groupby(["acct", "ip"]).agg(
        ok=("kind", lambda s: int((s == "登入成功 (AMS Device Manager)").sum())),
        fail=("kind", lambda s: int((s == "登入失敗 (AMS Device Manager)").sum())),
        um_in=("kind", lambda s: int((s == "登入 User Manager").sum())),
        um_out=("kind", lambda s: int((s == "登出 User Manager").sum())),
        n=("kind", "size"),
        first=("tw", "min"), last=("tw", "max"),
        spellings=("acct_raw", lambda s: " | ".join(sorted(set(x for x in s if isinstance(x, str))))),
        logged_as=("UserName", lambda s: " | ".join(sorted(set(x for x in s if x)))),
    ).reset_index()
    df = pd.DataFrame({
        "帳號 (由描述解析)": g["acct"],
        "電腦 IP": g["ip"],
        "電腦判讀": g["ip"].map(ip_labels),
        "登入成功次數": g["ok"],
        "登入失敗次數": g["fail"],
        "User Manager 登入次數": g["um_in"],
        "User Manager 登出次數": g["um_out"],
        "事件合計": g["n"],
        "首次(台灣)": g["first"],
        "最後(台灣)": g["last"],
        "帳號拼法 (原文)": g["spellings"],
        "事件記錄之 UserKey 帳號": g["logged_as"],
    }).sort_values(["事件合計"], ascending=False).reset_index(drop=True)
    return df


def sheet_sync_fail(ev):
    dev = ev[ev["is_device_event"] & ev["Category"].isin([43, 44, 45])].copy()
    fail = dev[dev["Category"] == 45].copy()
    fail["blk_in_desc"] = fail["Description"].str.extract(r"failed on ([A-Z]+\d+)")[0]
    fail["msg"] = fail["Description"].str.replace(r"^Device/database synchronization failed:?\s*", "", regex=True)
    g = fail.groupby("DeviceKey").agg(
        tag=("CurrentAmsTag", "first"), devtag=("AmsDeviceTag", "first"), tag_at=("TagAtEvent", lambda s: " | ".join(sorted(set(x for x in s if isinstance(x, str))))),
        mfr=("Manufacturer", "first"), model=("DeviceTypeName", "first"), proto=("Protocol", "first"),
        n=("DeviceKey", "size"), first=("tw", "min"), last=("tw", "max"),
        msgs=("msg", lambda s: " | ".join(sorted(set(s)))),
        blocks=("blk_in_desc", lambda s: " | ".join(sorted(set(x for x in s if isinstance(x, str))))),
        users=("UserName", lambda s: " | ".join(sorted(set(x for x in s if x)))),
        ips=("ip", lambda s: " | ".join(sorted(set(x for x in s if x)))),
    ).reset_index()
    ok = dev[dev["Category"].isin([43, 44])].groupby("DeviceKey").agg(ok_n=("DeviceKey", "size"), ok_last=("tw", "max")).reset_index()
    g = g.merge(ok, on="DeviceKey", how="left")
    g["ok_n"] = g["ok_n"].fillna(0).astype(int)
    g["recovered"] = (g["ok_last"].notna()) & (g["ok_last"] > g["last"])
    df = pd.DataFrame({
        "目前 AMS 位號": g["tag"],
        "事件當時位號": g["tag_at"],
        "裝置內位號 (AmsDeviceTag)": g["devtag"],
        "DeviceKey": g["DeviceKey"].astype("Int64"),
        "製造商": g["mfr"], "型號": g["model"], "協定": g["proto"],
        "同步失敗次數": g["n"],
        "首次失敗(台灣)": g["first"],
        "最後失敗(台灣)": g["last"],
        "失敗訊息 (去重)": g["msgs"],
        "失敗區塊 (描述中)": g["blocks"],
        "同步成功次數 (43+44)": g["ok_n"],
        "最後成功同步(台灣)": g["ok_last"],
        "最後失敗之後曾成功同步": yesno(g["recovered"]),
        "使用者": g["users"],
        "電腦 IP": g["ips"],
    }).sort_values(["同步失敗次數", "最後失敗(台灣)"], ascending=[False, False]).reset_index(drop=True)
    return df


DEL_RX = re.compile(r"^The (.+?) device with a serial number of (.+?) and an AMS tag of (.+?) was deleted from the database\.?$")
DEL_REV_RX = re.compile(r"^(.*?) (HART|FF|Fieldbus|PROFIBUS|Profibus|WirelessHART|ISA100|Modbus) Rev (\d+)$")


def sheet_deleted(ev, conn):
    e = ev[ev["Category"] == 52].copy()
    dev_now = _sql(conn, """
        SELECT d.DeviceKey, d.Identifier, d.AmsDeviceTag, d.AmsDeviceId, m.Name AS Manufacturer, dt.Name AS DeviceTypeName,
               (SELECT t.ExtBlockTag FROM Blocks b JOIN BlockAsgms a ON a.BlockKey = b.BlockKey AND a.EventIdDayOut = 49710
                JOIN ExtBlockTags t ON t.ExtBlockTagKey = a.ExtBlockTagKey WHERE b.DeviceKey = d.DeviceKey AND b.BlockIndex = 0 LIMIT 1) AS CurrentAmsTag
        FROM Devices d
        LEFT JOIN DeviceRevisions dr ON dr.AmsDevRevId = d.AmsDevRevId
        LEFT JOIN DeviceTypes dt ON dt.AmsDevTypeId = dr.AmsDevTypeId
        LEFT JOIN MfrProtocols mp ON mp.MfrProtocolId = dt.MfrProtocolId
        LEFT JOIN Manufacturers m ON m.AmsMfrNameId = mp.AmsMfrNameId
        WHERE d.DeviceKey >= 0
    """)
    mfr_names = sorted(_sql(conn, "SELECT Name FROM Manufacturers")["Name"].dropna().tolist(), key=len, reverse=True)
    tags_now = set(_sql(conn, "SELECT ExtBlockTag FROM ExtBlockTags")["ExtBlockTag"].dropna())

    def parse(o):
        if not isinstance(o, str):
            return dict(desc=None, serial=None, tag=None, mfr=None, model=None, proto=None, rev=None)
        m = DEL_RX.match(o.strip())
        if not m:
            return dict(desc=o, serial=None, tag=None, mfr=None, model=None, proto=None, rev=None)
        d, serial, tag = m.group(1), m.group(2), m.group(3)
        proto = rev = None
        core = d
        m2 = DEL_REV_RX.match(d)
        if m2:
            core, proto, rev = m2.group(1), m2.group(2), int(m2.group(3))
        mfr = next((n for n in mfr_names if core.startswith(n + " ")), None)
        model = core[len(mfr) + 1:] if mfr else core
        return dict(desc=d, serial=serial, tag=tag, mfr=mfr, model=model, proto=proto, rev=rev)

    p = pd.DataFrame([parse(o) for o in e["Other"]], index=e.index)
    e = pd.concat([e, p], axis=1)
    by_serial = dev_now.drop_duplicates("Identifier").set_index("Identifier")
    e["now_key"] = e["serial"].map(by_serial["DeviceKey"])
    e["now_tag"] = e["serial"].map(by_serial["CurrentAmsTag"])
    e["tag_exists"] = e["tag"].isin(tags_now)
    e["del_count"] = e.groupby("serial")["serial"].transform("size")
    e["del_seq"] = e.sort_values(["EventIdDay", "EventIdFraction"]).groupby("serial").cumcount() + 1
    df = pd.DataFrame({
        "刪除時間(台灣)": e["tw"],
        "時間 UTC 原值": e["EventTime"],
        "刪除時之位號 (由 Other 解析)": e["tag"],
        "裝置ID (Identifier)": e["serial"],
        "製造商": e["mfr"], "型號": e["model"], "協定": e["proto"], "裝置版本": e["rev"].astype("Int64"),
        "操作者 (UserName)": e["UserName"],
        "電腦 IP": e["ip"],
        "同一裝置ID目前仍在 Devices": yesno(e["now_key"].notna()),
        "目前 DeviceKey": e["now_key"].astype("Int64"),
        "目前 AMS 位號": e["now_tag"],
        "目前位號與刪除時相同": yesno(e["now_tag"].notna() & (e["now_tag"] == e["tag"])),
        "位號仍存在於 ExtBlockTags": yesno(e["tag_exists"]),
        "此序號被刪除次數": e["del_count"],
        "此為第幾次刪除": e["del_seq"],
        "描述 (Description)": e["Description"],
        "原文 (Other)": e["Other"],
        "EventIdDay": e["EventIdDay"], "EventIdFraction": e["EventIdFraction"],
    }).sort_values(["刪除時間(台灣)", "刪除時之位號 (由 Other 解析)"]).reset_index(drop=True)
    return df


SCAN_RX = re.compile(r"^(Scan All|Scan New) (started|completed|cancelled) on (.+?)\s*$")
POLL_RX = re.compile(r"^FF Alert Polling is (starting|complete)\s*$")


def sheet_scans(ev, ip_labels):
    e = ev[ev["Category"].isin([68, 69, 70])].sort_values(["EventIdDay", "EventIdFraction"]).copy()

    def parse(d):
        if not isinstance(d, str):
            return (None, None, None)
        m = SCAN_RX.match(d)
        if m:
            path = m.group(3).strip()
            return (m.group(1), m.group(2), path)
        m = POLL_RX.match(d)
        if m:
            return ("FF Alert Polling", {"starting": "started", "complete": "completed"}[m.group(1)], "(全部 FF 網路)")
        return (None, None, d)

    parsed = e["Description"].map(parse)
    e["kind"] = parsed.map(lambda t: t[0])
    e["state"] = parsed.map(lambda t: t[1])
    e["path"] = parsed.map(lambda t: t[2])
    e["pathnorm"] = e["path"].fillna("").str.lstrip("\\").str.replace(r"^NET\\", "", regex=True, case=False).str.lstrip("\\").str.upper()
    rows = []
    recs = e.to_dict("records")
    used = set()
    for i, r in enumerate(recs):
        if r["Category"] != 68:
            continue
        end = None
        # end logged within 5 s BEFORE the start (FF Alert Polling 'complete' can precede 'starting' by <1 s)
        j = i - 1
        if j >= 0 and j not in used and recs[j]["Category"] in (69, 70) and recs[j]["kind"] == r["kind"]                 and recs[j]["pathnorm"] == r["pathnorm"] and (r["utc"] - recs[j]["utc"]).total_seconds() <= 5:
            end = recs[j]
            used.add(j)
        for j in (range(i + 1, len(recs)) if end is None else []):
            s = recs[j]
            if s["kind"] == r["kind"] and s["pathnorm"] == r["pathnorm"]:
                if s["Category"] == 68:
                    break  # a new start of the same scan before any end -> unpaired
                if j not in used and s["Category"] in (69, 70):
                    end = s
                    used.add(j)
                    break
        result = {69: "完成", 70: "取消"}.get(end["Category"]) if end else "未見結束事件"
        dur = (end["utc"] - r["utc"]).total_seconds() if end else None
        rows.append({
            "開始(台灣)": r["tw"],
            "結束(台灣)": end["tw"] if end else pd.NaT,
            "歷時(秒)": dur,
            "結果": result,
            "掃描類型": r["kind"] or "(未解析)",
            "路徑 (Description 解析)": r["path"],
            "使用者 (UserName)": r["UserName"],
            "電腦 IP": r["ip"],
            "電腦判讀": ip_labels.get(r["ip"]),
            "來源 (Source)": r["Source_clean"],
            "開始描述": r["Description"],
            "結束描述": end["Description"] if end else None,
            "開始 EventIdDay": r["EventIdDay"], "開始 EventIdFraction": r["EventIdFraction"],
        })
    # ends without a start
    for j, s in enumerate(recs):
        if s["Category"] in (69, 70) and j not in used:
            rows.append({
                "開始(台灣)": pd.NaT, "結束(台灣)": s["tw"], "歷時(秒)": None,
                "結果": "僅見結束事件 (" + ("完成" if s["Category"] == 69 else "取消") + ")，無對應開始",
                "掃描類型": s["kind"] or "(未解析)", "路徑 (Description 解析)": s["path"],
                "使用者 (UserName)": s["UserName"], "電腦 IP": s["ip"], "電腦判讀": ip_labels.get(s["ip"]),
                "來源 (Source)": s["Source_clean"], "開始描述": None, "結束描述": s["Description"],
                "開始 EventIdDay": s["EventIdDay"], "開始 EventIdFraction": s["EventIdFraction"],
            })
    df = pd.DataFrame(rows)
    df["_k"] = df["開始(台灣)"].fillna(df["結束(台灣)"])
    df = df.sort_values("_k").drop(columns="_k").reset_index(drop=True)
    return df


UA_PATTERNS = [
    (re.compile(r"^AMS Device Manager User added: '(.+?)'\.?$"), "新增使用者", None, None),
    (re.compile(r"^AMS Device Manager User removed: '(.+?)'\.?$"), "移除使用者", None, None),
    (re.compile(r"^AMS Device Manager User '(.+?)' renamed as '(.+?)'\.?$"), "更名", 2, None),
    (re.compile(r"^AMS Device Manager User '(.+?)' added to group '(.+?)'\.?$"), "加入群組", 2, None),
    (re.compile(r"^AMS Device Manager User '(.+?)' removed from group '(.+?)'\.?$"), "移出群組", 2, None),
    (re.compile(r"^AMS Device Manager User '(.+?)' granted permission '(.+?)' at '(.+?)'\.?$"), "授予權限", 2, 3),
    (re.compile(r"^AMS Device Manager User '(.+?)' revoked permission '(.+?)' at '(.+?)'\.?$"), "撤銷權限", 2, 3),
    (re.compile(r"^AMS Device Manager User '(.+?)' (.+)$"), "其他", None, None),
]


def sheet_user_changes(ev, ip_labels):
    e = ev[ev["Category"] == 58].sort_values(["EventIdDay", "EventIdFraction"]).copy()

    def parse(d):
        if not isinstance(d, str):
            return (None, "其他", None, None)
        s = d.strip()
        for rx, act, gi, si in UA_PATTERNS:
            m = rx.match(s)
            if m:
                target = m.group(1)
                obj = m.group(gi) if gi else None
                scope = m.group(si) if si else None
                if act == "其他":
                    obj = m.group(2)
                return (target, act, obj, scope)
        return (None, "其他", s, None)

    p = e["Description"].map(parse)
    df = pd.DataFrame({
        "時間(台灣)": e["tw"],
        "時間 UTC 原值": e["EventTime"],
        "操作者 (UserName)": e["UserName"],
        "電腦 IP": e["ip"],
        "電腦判讀": e["ip"].map(ip_labels),
        "對象帳號": p.map(lambda t: t[0]),
        "動作": p.map(lambda t: t[1]),
        "群組 / 權限 / 新名稱": p.map(lambda t: t[2]),
        "權限範圍": p.map(lambda t: t[3]),
        "來源 (Source)": e["Source_clean"],
        "原文 (Description)": e["Description"],
        "EventIdDay": e["EventIdDay"], "EventIdFraction": e["EventIdFraction"],
    }).reset_index(drop=True)
    return df


MERGE_RX = re.compile(r"^(\d+) objects, (\d+) configurations, (\d+) block assignments, (\d+) other events imported from file (.+?)\.?$")
BACKUP_RX = re.compile(r"^Backup file (.+?) successfully written\.?$")
EXTRACT_RX = re.compile(r"^Records from database (\w+) written to export file '(.+?)'\.?$")
REBUILD_RX = re.compile(r"^Rebuild Hierarchy performed on (.+?)\s*$")


def sheet_maintenance(ev, ip_labels):
    e = ev[(ev["Category"].isin([12, 16, 51, 53, 71])) | ((ev["Category"] == 14) & (ev["Source_clean"] == "Database Maintenance"))]
    e = e.sort_values(["EventIdDay", "EventIdFraction"]).copy()

    def parse(cat, desc, other):
        out = dict(act=None, file=None, proto=None, mfr_hex=None, type_hex=None, objs=None, cfgs=None, asg=None, oth=None, path=None)
        o = other if isinstance(other, str) else ""
        d = desc if isinstance(desc, str) else ""
        if cat == 14:
            m = MERGE_RX.match(o.strip())
            if m:
                f = m.group(5)
                if f.lower().endswith(".mrg."):
                    f = f[:-1]
                out.update(act="匯入 .mrg 裝置定義/範本", file=f, objs=int(m.group(1)), cfgs=int(m.group(2)), asg=int(m.group(3)), oth=int(m.group(4)))
                mp = re.search(r"[\\/](HART|FF)[\\/]([0-9A-Fa-f]+)[\\/]([0-9A-Fa-f]+)[\\/]", f)
                if mp:
                    out.update(proto=mp.group(1), mfr_hex=mp.group(2).lower(), type_hex=mp.group(3).lower())
            else:
                out.update(act="由檔案合併 (未解析)", file=o or None)
        elif cat == 12:
            m = BACKUP_RX.match(o.strip())
            out.update(act="資料庫備份", file=m.group(1) if m else (o or None))
        elif cat == 16:
            m = EXTRACT_RX.match(o.strip())
            out.update(act="資料庫匯出 (.ams_merge)", file=m.group(2) if m else (o or None))
        elif cat == 71:
            m = REBUILD_RX.match(d)
            out.update(act="重建階層", path=m.group(1) if m else d)
        elif cat == 51:
            out.update(act="AMS 啟動" if "started" in d else ("AMS 關閉" if "shutdown" in d else "應用程式"))
        elif cat == 53:
            out.update(act="系統選項：" + ("啟用" if d.startswith("Enable") else "停用" if d.startswith("Disable") else "") + "存取裝置時同步線上組態")
        return out

    p = pd.DataFrame([parse(c, d, o) for c, d, o in zip(e["Category"], e["Description"], e["Other"])], index=e.index)
    df = pd.DataFrame({
        "時間(台灣)": e["tw"],
        "時間 UTC 原值": e["EventTime"],
        "類別代碼": e["Category"],
        "類別中文": e["Category"].map(CATEGORY_ZH),
        "動作 (解析)": p["act"],
        "使用者 (UserName)": e["UserName"],
        "電腦 IP": e["ip"],
        "電腦判讀": e["ip"].map(ip_labels),
        "檔案路徑": p["file"],
        "階層路徑": p["path"],
        "協定 (由路徑)": p["proto"],
        "製造商碼 hex (由路徑)": p["mfr_hex"],
        "裝置型別碼 hex (由路徑)": p["type_hex"],
        "匯入物件數": p["objs"].astype("Int64"),
        "匯入組態數": p["cfgs"].astype("Int64"),
        "匯入區塊指派數": p["asg"].astype("Int64"),
        "匯入其他事件數": p["oth"].astype("Int64"),
        "來源 (Source)": e["Source_clean"],
        "描述 (Description)": e["Description"],
        "其他 (Other)": e["Other"],
        "EventIdDay": e["EventIdDay"], "EventIdFraction": e["EventIdFraction"],
    }).reset_index(drop=True)
    return df


def sheet_users(ev, users_df):
    g = ev.groupby("UserKey").agg(n=("UserKey", "size"), first=("tw", "min"), last=("tw", "max"),
                                  cats=("Category", lambda s: ",".join(str(x) for x in sorted(set(s)))),
                                  ips=("ip", lambda s: " | ".join(sorted(set(x for x in s if x)))),
                                  ndev=("is_device_event", "sum")).reset_index()
    u = users_df.merge(g, on="UserKey", how="left")

    def nature(name):
        if not isinstance(name, str):
            return ""
        if "do not remove" in name:
            return "AMS 內建哨兵/系統帳號"
        if name.startswith("FS.") or name.startswith("PS."):
            return "AMS 伺服器服務帳號 (FS=File Server, PS=Plant Server；伺服器自動作業)"
        if name.startswith("HMI\\"):
            return "Windows 網域帳號 (HMI 網域)"
        if name in ("admin", "install"):
            return "Emerson 隨附/安裝帳號 (範本事件)"
        if name == "AmsServiceUser":
            return "AMS 服務帳號"
        if name.startswith("DBM"):
            return "資料庫維護帳號"
        return "其他"

    df = pd.DataFrame({
        "UserKey": u["UserKey"],
        "使用者名稱 (UserName)": u["UserName"],
        "帳號性質 (推定)": u["UserName"].map(nature),
        "事件數": u["n"].fillna(0).astype(int),
        "其中設備事件": u["ndev"].fillna(0).astype(int),
        "首次事件(台灣)": u["first"],
        "最後事件(台灣)": u["last"],
        "出現類別代碼": u["cats"],
        "使用電腦 IP": u["ips"],
        "UserIdentifier": u["UserIdentifier"],
        "SSOID": u["SSOID"],
    }).sort_values("事件數", ascending=False).reset_index(drop=True)
    return df


def sheet_computers(ev, ip_labels):
    g = ev.groupby(["ip", "ComputerId"]).agg(
        n=("ip", "size"), ndev=("is_device_event", "sum"), first=("tw", "min"), last=("tw", "max"),
        users=("UserName", lambda s: " | ".join(f"{k}×{v}" for k, v in s.value_counts().items())),
        cats=("Category", lambda s: ",".join(str(x) for x in sorted(set(s)))),
        ndevices=("DeviceKey", lambda s: int(s.dropna().nunique())),
    ).reset_index()
    df = pd.DataFrame({
        "電腦 IP (解碼)": g["ip"],
        "ComputerId 原值": g["ComputerId"],
        "判讀": g["ip"].map(ip_labels),
        "事件數": g["n"].astype(int),
        "其中設備事件": g["ndev"].astype(int),
        "涉及裝置數": g["ndevices"],
        "首次(台灣)": g["first"],
        "最後(台灣)": g["last"],
        "使用者 (×次數)": g["users"],
        "出現類別代碼": g["cats"],
    }).sort_values("事件數", ascending=False).reset_index(drop=True)
    return df


def sheet_category_codes(ev, conn):
    cats = _sql(conn, "SELECT Category, CategoryDesc FROM EventCategories ORDER BY Category")
    g = ev.groupby("Category").agg(n=("Category", "size"), types=("Type", lambda s: ",".join(str(x) for x in sorted(set(s)))),
                                   first=("tw", "min"), last=("tw", "max")).reset_index()
    c = cats.merge(g, on="Category", how="left")
    df = pd.DataFrame({
        "類別代碼 (Category)": c["Category"],
        "類別原文 (CategoryDesc)": c["CategoryDesc"],
        "類別中文": c["Category"].map(CATEGORY_ZH),
        "本資料庫筆數": c["n"].fillna(0).astype(int),
        "Type 出現值": c["types"],
        "最早(台灣)": c["first"],
        "最晚(台灣)": c["last"],
    })
    return df


# --------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------
def build(conn):
    ev = load_events(conn)
    users_df = _sql(conn, "SELECT UserKey, UserName, UserIdentifier, SSOID FROM Users ORDER BY UserKey")
    ip_labels = computer_labels(ev)

    n_total = len(ev)
    n_dev = int(ev["is_device_event"].sum())
    n_sent = int(ev["is_sentinel"].sum())
    n_pre2020 = int(((ev["utc"] < "2020-01-01") & (~ev["is_sentinel"])).sum())  # 1996~2019, 1970 sentinel excluded
    n_tag_resolved = int(ev.loc[ev["is_device_event"], "TagAtEvent"].notna().sum())
    n_tag_changed = int(((ev["TagAtEvent"].notna()) & (ev["CurrentAmsTag"].notna()) & (ev["TagAtEvent"] != ev["CurrentAmsTag"])).sum())
    n_orphan_ident = int(((ev["Category"] == 1) & (ev["Description"] == "Device identified") & (~ev["is_device_event"])).sum())

    common_notes = [
        "時間：EventLog.EventTime 為 UTC (AmsSp_LogEventSummary_1 註解 '@strEventTimeAsGMT ... this time is in GMT')；'(台灣)' 欄 = UTC+8。",
        "EventIdDay/EventIdFraction：OLE 日期序號 (1899-12-30 起算) 與 當日比例×2^31 (AmsUdf_EventIdDayFractionToDateTime)；全部 29,773 列與 EventTime 差 <2 秒，故可作毫秒級時間。",
        "ComputerId：IPv4 以 big-endian 打包成有號 32 位元整數 (AmsSp_LogEventSummary_1: '@iComputerNameId ... the computer IP address')；驗證 2130706433→127.0.0.1、167873846→10.1.141.54、-1408185981→172.16.201.131 (與前簿 17_使用者與電腦 一致)；-1 = 無。",
        "事件當時位號：依 BlockAsgms(ExtBlockTagKey, 裝置層級 BlockKey, [EventIdIn, EventIdOut)) 區間比對，與 AmsUdf_BuildATStmtForRead (AMS 稽核軌跡 UI 所用) 相同；EventIdDayOut=49710 (2036-02-05 哨兵) 表示現行指派。",
        "Type 意義為依 Type×Category 共現推定 (非官方碼表)：0 無/哨兵、1 裝置組態(1/28/53)、2 指派(49)、3 資料庫維護(12/14/16/52)、4 應用程式/系統/使用者(46/47/51/58/68-71)、6 範本/舊版匯入(1 建立範本、2、14 AmsMergeDoc)、8 裝置同步(43/44/45)。",
        "EventCode 全部為 0 (程序註解 'always be 0')；Archived 全部 0；MoreDetail 僅 2,105 列 'Device identified' 事件有值且長度 0。",
    ]

    sheets = []

    # 1 summary
    df_sum = sheet_summary(ev)
    sheets.append({
        "name": "事件稽核摘要",
        "purpose": "EventLog 全部 29,773 筆依類別統計，並與前簿 10_事件總帳 (13,682 筆) 對帳",
        "one_row": "一列一個事件類別 (Category)，末列合計",
        "df": df_sum,
        "notes": common_notes + [
            f"本資料庫 EventLog 共 {n_total:,} 列；設備事件 (BlockKey>=0) {n_dev:,} 列、非設備事件 {n_total - n_dev:,} 列；哨兵列 {n_sent} 列 (1970-01-01 'Test event log (do not remove)' 與 2036-02-05 'Large event id (do not remove)'，UserKey/ComputerId/BlockKey 皆 -1，Category -1；2036 列同時是 BlockAsgms.EventIdDayOut=49710 的現行指派哨兵)。",
            f"前簿 10_事件總帳 (由 .ams_merge 文字匯出) 13,682 列 vs 本 DB 29,773 列，差 16,091 列。.ams_merge 匯出僅含裝置/範本相關事件：完全遺漏 Category 43/44/45 裝置同步 (4,673)、47 登出 (19)、51 應用程式啟停 (170)、52 刪除裝置 (345)、53 系統選項 (2)、58 使用者帳號變更 (215)、69 掃描完成 (172)、71 重建階層 (53)、12 備份 (1)、2 巡檢站 (166)；幾乎遺漏 46 登入 (233→3)、68 掃描開始 (204→1)、70 掃描取消 (31→1)、14 由檔案合併 (8,542→146；含 6,772 筆 AmsMergeDoc 範本內附事件、1,726 筆 Database Maintenance 匯入紀錄與 44 筆 ManualInserted 範本事件)、16 匯出 (2→1)。Category 1 前簿 5,901 vs DB 7,243 (差 1,342：Category 1 中 BlockKey=-1 者共 848 筆 = 652 筆 'Create Device Template' 範本事件 + 177 筆已刪除裝置殘留的 'Device identified' + 19 筆其他舊事件)；Category 49 前簿 1,622 vs DB 1,642 (差 20)；Category 28 兩者皆 6,001 (完全一致)。",
            f"前簿 'Device identified' 2,234 筆 > DB 2,105 筆：前簿計數含 .ams_merge 重複輸出，DB 每台裝置 (1,928) 恰 1 筆 + 177 筆已刪除裝置殘留。",
            f"已刪除裝置的事件：AmsSp_DeleteDevice_1 會實體刪除該裝置的 EventLog 列，只保留被 BlockAsgms 參照 (改寫 BlockKey) 或被 TestDefAsgms 參照 (BlockKey 改為 -1) 的事件；因此 {n_orphan_ident} 筆 'Device identified' (Category 1、BlockKey=-1、2024-12-04~2025-03-18) 即為 177 台曾被刪除裝置的殘留，其餘組態/同步歷史已不可考。",
            f"位號解析：{n_tag_resolved:,}/{n_dev:,} 設備事件皆能解析出事件當時位號；其中 {n_tag_changed:,} 筆事件當時位號 ≠ 目前位號 (1,633 筆 'Renamed AMS tag' 事件即 BlockAsgms 的 Out 事件)。",
            f"2019 年以前的 {n_pre2020:,} 筆事件 (1996~2019；使用者 admin/install/Plant Server；來源 AmsMergeDoc/Server/FMS) 為 Emerson 隨附裝置範本 (.mrg) 內附事件，非本廠操作；本廠事件自 2024-11-20 (UTC) 起。",
            "本域相關空表 (未另製表)：AlertLog、AlertList、DeviceMonitorList、MobileDeviceEventLog、NotifyQ、AlertFilterForDevice、DeviceAlertReoccurFilter、DeviceHealth* 皆 0 列 → 本廠未啟用警報監視 (Alert Monitor)，故無 Category 20/21/62/63/74/99 事件。",
        ],
        "source_tables": ["EventLog", "EventCategories", "Users", "Blocks", "BlockAsgms", "ExtBlockTags"],
    })

    # 2 master
    df_master = sheet_master(ev, ip_labels)
    sheets.append({
        "name": "事件總帳",
        "purpose": "EventLog 全部 29,773 筆事件逐列解碼 (時間/類別/使用者/電腦 IP/事件當時位號/目前位號/裝置資訊)",
        "one_row": "一列一筆 EventLog 事件 (主鍵 EventIdDay+EventIdFraction)，依事件 ID 排序",
        "df": df_master,
        "notes": common_notes + [
            "'目前 AMS 位號' = BlockAsgms 中 EventIdDayOut=49710 (現行) 指派之 ExtBlockTag；'事件當時位號' 為 BlockAsgms 區間解析；'位號已變更' = 兩者不同。'裝置內位號 (Devices.AmsDeviceTag)' 是裝置本身的 HART 8 字元 Tag / FF 裝置 Tag，1,928 台僅 1,395 個不同值，不可當 AMS 位號使用 (HART 1,577 台僅 8 台與 AMS 位號相同)。",
            "'本事件寫入參數筆數' = BlockData 中 EventId 相同的列數 (Category 28 'Field change' 每筆平均 ~58 個參數；Category 1 中 2,112 筆有參數值)；參數內容屬 BlockData 域。",
            "'位號指派-指派入/出' = 該事件被 BlockAsgms.EventIdIn/Out 參照的位號 (3,561 筆指派入 = Category 1 'Device identified'/'Renamed AMS tag'；1,633 筆指派出 = 'Renamed AMS tag' 事件)。",
            "Category 49 'AMS tag assignment' 1,642 筆 BlockKey 皆 -1 且未被 BlockAsgms 參照，對應 TestDefAsgms (測試方案指派) 域，本表無法連到裝置。",
            "區塊類型：BlockType ''=裝置層級 (BlockIndex 0)、F=功能區塊、T=轉換區塊、R=資源區塊；同步事件 (43/44/45) 常記在 F/T/R 區塊上 (Description 內 FUNCTION1600 等)。",
            "'Renamed AMS tag ÿÿÿÿ… to X' / '____ to X' 之舊位號為 AMS 首次識別時的亂碼預設位號，非真實位號。",
        ],
        "source_tables": ["EventLog", "EventCategories", "Users", "Blocks", "Devices", "DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "BlockAsgms", "ExtBlockTags", "BlockData"],
    })

    # 3 category x month
    df_cm = sheet_cat_month(ev)
    sheets.append({
        "name": "類別×年月統計",
        "purpose": "各事件類別依台灣時間年月的筆數矩陣",
        "one_row": "一列一個年月 (台灣時間)，欄為類別代碼+中文，末欄合計",
        "df": df_cm,
        "notes": ["年月以 UTC+8 換算；1970-01 與 2036-02 為哨兵列；1996~2019 為 Emerson 範本內附事件 (非本廠)。"],
        "source_tables": ["EventLog", "EventCategories"],
    })

    # 4 logins
    df_login = sheet_logins(ev, ip_labels, users_df)
    sheets.append({
        "name": "登入登出統計",
        "purpose": "Category 46/47 依帳號×電腦統計登入成功/失敗與 User Manager 登入登出",
        "one_row": "一列一個 (帳號, 電腦 IP) 組合",
        "df": df_login,
        "notes": [
            "帳號由 Description 解析 ('Successful login of user: X to AMS Device Manager.'、'Unsuccessful login of user: X'、\"User 'X' logged in/off User Manager.\")，大小寫拼法統一為 Users 表拼法，原拼法列於 '帳號拼法'。",
            "登入事件本身的 UserKey 多為 FS.AMS1SVR/PS.AMS1SVR 等服務帳號或登入者本人，故以描述解析之帳號為準。",
            "AMS Device Manager 主程式無 '登出' 事件 (Category 47 僅 User Manager 登出 19 筆)，故無法計算 AMS 使用時長。",
            "'HMI\\GEAdmin' 為共用帳號 (登入 167 次、佔絕大多數)，無法追溯到個人；具名帳號 u534558/u534521/u675532/HTPPAdmin 自 2026-06 起才出現。",
        ],
        "source_tables": ["EventLog", "Users"],
    })

    # 5 sync failures
    df_sync = sheet_sync_fail(ev)
    sheets.append({
        "name": "同步失敗統計",
        "purpose": "Category 45 裝置同步失敗依裝置彙總 (次數、時間、訊息、失敗後是否再同步成功)",
        "one_row": "一列一台裝置 (DeviceKey)",
        "df": df_sync,
        "notes": [
            "同步事件 (43/44/45) 全部為 Source='Server'、Type 8、UserKey=PS.AMS1SVR (伺服器自動同步)，僅發生於 2024-12-12~2026-07-18；失敗 565 筆集中在 2025-04-09~2025-05-12 (FF 裝置試運轉期間)。",
            "失敗訊息兩型：'failed during parameter update with database' (355 筆，資料庫端寫入失敗) 與 'failed on FUNCTIONxxxx:CM Response code' (210 筆，FF 功能區塊通訊回應碼錯誤)。",
            "'最後失敗之後曾成功同步' = 該裝置在最後一次失敗之後有 Category 43/44 事件。",
            "本表 332 台裝置協定皆為 FF (HART 裝置無同步失敗事件)；'使用者' 欄皆為 PS.AMS1SVR (伺服器自動同步)。",
        ],
        "source_tables": ["EventLog", "Blocks", "Devices", "DeviceTypes", "Manufacturers", "DeviceProtocols", "BlockAsgms", "ExtBlockTags"],
    })

    # 6 deleted devices
    df_del = sheet_deleted(ev, conn)
    n_del_serial = df_del["裝置ID (Identifier)"].nunique()
    n_still = int((df_del.drop_duplicates("裝置ID (Identifier)")["同一裝置ID目前仍在 Devices"] == "是").sum())
    sheets.append({
        "name": "刪除裝置事件",
        "purpose": "Category 52 'Delete Device' 345 筆：刪除時位號/序號/型號、操作者，及該序號目前是否仍在資料庫",
        "one_row": "一列一筆刪除事件 (同一裝置可被刪除多次)",
        "df": df_del,
        "notes": [
            "刪除內容由 Other 欄解析 ('The <製造商 型號> <協定> Rev <n> device with a serial number of <序號> and an AMS tag of <位號> was deleted from the database.')；製造商以 Manufacturers 表名稱前綴比對切分。",
            f"345 筆刪除事件涉及 {n_del_serial} 個不同序號；其中 168 個序號在 2025-03-31 與 2025-04-09 各被刪除一次 (共兩次)，皆由 HMI\\GEAdmin 於 172.16.101.17 操作；2025-05-07 7 筆、2026-04-29/05-05 各 1 筆於 172.16.201.131。",
            f"{n_still}/{n_del_serial} 個被刪序號目前仍存在於 Devices (同序號重新掃描建檔，DeviceKey 已不同)；{n_del_serial - n_still} 個已不在 Devices (G11HAD30BL001_old、G11HAH11BT001_old 等)。所有 177 個被刪位號仍留在 ExtBlockTags (位號表不隨裝置刪除)。'操作者' 全部為 HMI\\GEAdmin；'描述 (Description)' 全部為 'Database Maintenance' (刪除內容只在 Other 欄)。",
            "AmsSp_DeleteDevice_1 會實體刪除被刪裝置的事件與參數歷史 (BlockData)，僅保留被 BlockAsgms/TestDefAsgms 參照的事件 (BlockKey 改為新 BlockKey 或 -1)，故被刪裝置在 2025-03-31 之前的組態歷史已不可考。",
        ],
        "source_tables": ["EventLog", "Devices", "DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers", "ExtBlockTags"],
    })

    # 7 scans
    df_scan = sheet_scans(ev, ip_labels)
    sheets.append({
        "name": "裝置掃描作業",
        "purpose": "Category 68/69/70 掃描開始/完成/取消配對為一次作業，含歷時與結果",
        "one_row": "一列一次掃描作業 (以同類型、同路徑的下一個完成/取消事件配對)",
        "df": df_scan,
        "notes": [
            "掃描類型：'Scan All' 全部掃描、'Scan New' 掃描新裝置、'FF Alert Polling' FF 警報輪詢 (FF Polling Application 每次啟動即 starting/complete 各 1 筆，107 對)。",
            "路徑為 AMS 網路階層 (\\AMS1SVR\\<網路>\\<多工器/連結>)；配對規則：同類型同路徑 (忽略大小寫與前導反斜線) 的下一個 69/70 事件；若先遇到另一次開始則視為 '未見結束事件'。FF Alert Polling 有 1 對 complete 比 starting 早 1 秒 (歷時 -1)；全廠 Scan All/Scan New 有 6 次歷時 8~66 小時 (跨夜完成/取消，依配對規則判定，未經現場確認)。",
            "204 開始 / 172 完成 / 31 取消；未配對者多為 AMS 用戶端於掃描中被關閉。",
        ],
        "source_tables": ["EventLog", "Users"],
    })

    # 8 user account changes
    df_ua = sheet_user_changes(ev, ip_labels)
    sheets.append({
        "name": "使用者帳號變更",
        "purpose": "Category 58 'User Account Changed' 215 筆：新增/更名/群組/權限變更逐筆解析",
        "one_row": "一列一筆帳號變更事件",
        "df": df_ua,
        "notes": [
            "動作由 Description 解析：'User added'、'renamed as'、'added to group'、'removed from group'、'granted permission … at …'、'revoked permission'。",
            "全部由 AMS Device Manager - User Manager 記錄、全部在 172.16.201.131 (AMS1SVR 伺服器) 執行；2025-12-16 2 筆 (GEAdmin 加入/移出 System Admin)，其餘 213 筆集中在 2026-06~07 建立具名帳號 (HTPPAdmin、Admin→Admin1、u120396、u534521、u534558、u675532) 並逐項授權。",
        ],
        "source_tables": ["EventLog", "Users"],
    })

    # 9 maintenance/system
    df_mt = sheet_maintenance(ev, ip_labels)
    sheets.append({
        "name": "資料庫維護與系統事件",
        "purpose": "備份(12)/匯出(16)/由檔案合併匯入(14, Database Maintenance)/刪除裝置除外/系統選項(53)/AMS 啟停(51)/重建階層(71)",
        "one_row": "一列一筆維護或系統事件；.mrg 匯入紀錄解析出檔案、協定、製造商碼、匯入物件數",
        "df": df_mt,
        "notes": [
            "Category 14 分三種來源：Source='Database Maintenance' (1,726 筆，Type 3，AMS 匯入 C:\\AMS\\Devices\\<HART|FF>\\<mfr hex>\\<type hex>\\*.mrg 裝置定義，每筆 Other 記 'N objects, N configurations, N block assignments, N other events imported from file …') 、Source='AmsMergeDoc' (6,772 筆，Type 6，為 .mrg 內附的範本組態事件) 與 Source='ManualInserted' (44 筆，Type 6，Emerson 範本手動插入事件)；後兩者本表不列，見事件總帳。'匯入區塊指派數' 於 1,725 筆解析列皆為 0 (匯入的是裝置定義，不含位號指派)；1 筆 2010-03-15 Other='4' 無法解析。",
            "備份僅 1 筆 (2025-04-23 C:\\AMS\\Bin\\20250423.ams_bckup)；匯出 2 筆 (2026-09-10 HMI\\u534558 匯出 20260910.ams_merge 至 S:\\TPC B1\\I&C\\AMS 與桌面，即前簿來源)。",
            "重建階層 53 筆列出被重建的網路節點 (FF HSE Net 1、各 HART 多工器 *_LU0xx / *_CA0xx)。",
        ],
        "source_tables": ["EventLog", "Users"],
    })

    # 10 users
    df_users = sheet_users(ev, users_df)
    sheets.append({
        "name": "使用者清單",
        "purpose": "Users 表 15 個帳號及其事件統計",
        "one_row": "一列一個 Users 帳號",
        "df": df_users,
        "notes": [
            "UserKey -1/0 為 AMS 內建；FS./PS.AMS1SVR 為伺服器 File Server/Plant Server 服務帳號 (AmsSp_LogEventSummary_1: 'if the Ams user name is not in the database it will use File Server user name instead')；admin/install 為 Emerson 範本內附事件之帳號。",
            "'HMI\\u534558' 等 '\\u' 為 Windows 帳號字面字元 (網域 HMI、帳號 u534558)，非跳脫序列。UserIdentifier/SSOID 皆空。",
        ],
        "source_tables": ["Users", "EventLog"],
    })

    # 11 computers
    df_pc = sheet_computers(ev, ip_labels)
    sheets.append({
        "name": "電腦清單",
        "purpose": "ComputerId 解碼後之 IP 清單與事件統計/判讀",
        "one_row": "一列一個 IP (ComputerId)",
        "df": df_pc,
        "notes": [
            "判讀規則：最後事件 <2020 → Emerson 範本/舊資料庫來源；172.16.201.131 → AMS1SVR 伺服器 (推定)；172.16.101.17 與 10.1.141.54 → 試運轉期間其他站台 (推定，待確認)；127.0.0.1 → 本機。",
            "2024 以後本廠 IP 僅 5 個：172.16.201.131 (17,695 筆)、172.16.101.17 (2,438)、10.1.141.54 (1,918)、10.0.0.1 (5 筆 AMS 啟動)、10.1.111.54 (ComputerId 167866166，1 筆 AMS 啟動)；另 127.0.0.1 有 6 筆登入失敗事件 (伺服器本機)。",
        ],
        "source_tables": ["EventLog", "Users"],
    })

    # 12 category code table
    df_cc = sheet_category_codes(ev, conn)
    sheets.append({
        "name": "事件類別碼表",
        "purpose": "EventCategories 97 個類別代碼、中文翻譯與本資料庫出現筆數",
        "one_row": "一列一個 Category 代碼",
        "df": df_cc,
        "notes": ["中文為依 CategoryDesc 翻譯；本廠僅用到 22 個類別。"],
        "source_tables": ["EventCategories", "EventLog"],
    })

    return sheets


# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    out = Path(OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    sheets = build(conn)
    for s in sheets:
        df = s["df"]
        assert len(s["name"]) <= 28, s["name"]
        # no raw bytes
        for col in df.columns:
            if df[col].map(lambda x: isinstance(x, (bytes, bytearray))).any():
                raise SystemExit(f"raw bytes in sheet {s['name']} col {col}")
        print(f"{s['name']}: rows={len(df):,} cols={len(df.columns)}")
        df.to_csv(out / f"{KEY}__{s['name']}.csv", index=False, encoding="utf-8-sig")
    # diagnostics
    m = {s["name"]: s["df"] for s in sheets}
    ua = m["使用者帳號變更"]
    print("user-change actions:", ua["動作"].value_counts().to_dict())
    sc = m["裝置掃描作業"]
    print("scan results:", sc["結果"].value_counts().to_dict(), "kinds:", sc["掃描類型"].value_counts().to_dict())
    lg = m["登入登出統計"]
    print("login accounts:", lg["帳號 (由描述解析)"].value_counts().to_dict())
    dl = m["刪除裝置事件"]
    print("deleted: rows", len(dl), "serials", dl["裝置ID (Identifier)"].nunique(), "still:", dl.drop_duplicates("裝置ID (Identifier)")["同一裝置ID目前仍在 Devices"].value_counts().to_dict())
    mt = m["資料庫維護與系統事件"]
    print("maintenance actions:", mt["動作 (解析)"].value_counts().to_dict())
    ms = m["事件總帳"]
    print("master tag resolved:", ms["事件當時位號 (BlockAsgms)"].notna().sum(), "changed:", (ms["位號已變更"] == "是").sum(), "sentinels:", (ms["哨兵列"] == "是").sum())
    print("ip labels:", m["電腦清單"][["電腦 IP (解碼)", "事件數", "判讀"]].head(8).to_string())
