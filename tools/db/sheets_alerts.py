# -*- coding: utf-8 -*-
"""
sheets_alerts.py  --  AMS Device Manager (AmsDb) 警報定義與診斷設定 (domain key: alerts)

build(conn) -> list[dict]   # conn = sqlite3 connection to AmsDb.sqlite

Sheets produced
  1. 使用中機型警報定義      : 本廠實際有設備的 43 個機型版本之警報定義 (一列一警報)
  2. 機型警報數量彙總        : 每個機型版本一列, 各警報類別數量、預設監視啟用數、是否使用中
  3. 全部警報定義            : DeviceAlertDesc 全部 140,438 筆 (含未使用機型), 欄位同 1 + 使用中
  4. 警報類別代碼            : AlertTypes 7 筆 + 中文 + AMS 嚴重度排序
  5. 網路通訊與輪詢設定      : NetworkInfoProperty 依網路樞轉 (一列一網路)
  6. 系統設定與警報監視狀態  : SystemDefaults / StationProperty / PlantServer / Policies /
                               空的警報與健康狀態表 (0 列) 與推論
"""
import os
import sqlite3
import pandas as pd

DB_PATH = (r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/"
           r"2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/AmsDb.sqlite")
OUT_DIR = (r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/"
           r"2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/build/out")
KEY = "alerts"
HELP_TRIM = 500

# ---------------------------------------------------------------- code tables
ALERT_TYPE_ZH = {
    "FAILED": "失效 (Failed)",
    "MAINT": "需維護 (Maintenance)",
    "ADVISE": "建議/提示 (Advisory)",
    "ABNORM": "異常 (Abnormal)",
    "COMM": "通訊失敗 (No Comm)",
    "CHKFNC": "功能檢查 (Check Function)",
    "": "未知 (Unknown)",
}
# AMS 嚴重度排序: 來源 AmsVw_Monitoring_DeviceAlertMetadata (FAILED=5, MAINT=4, ABNORM=3, CHKFNC=2, ADVISE=1, 其他=0)
ALERT_SEVERITY = {"FAILED": 5, "MAINT": 4, "ABNORM": 3, "CHKFNC": 2, "ADVISE": 1, "COMM": 0, "": 0}

# HART Command 48 byte layout (HART 7 spec; byte index = 十六進位 AlertId 後 4 bytes 小端序整數 - 1)
CMD48_BYTE_NAME = {
    0: "Device-Specific Status 0", 1: "Device-Specific Status 1", 2: "Device-Specific Status 2",
    3: "Device-Specific Status 3", 4: "Device-Specific Status 4", 5: "Device-Specific Status 5",
    6: "Extended Device Status", 7: "Device Operating Mode", 8: "Standardized Status 0",
    9: "Standardized Status 1", 10: "Analog Channel Saturated", 11: "Standardized Status 2",
    12: "Standardized Status 3", 13: "Analog Channel Fixed",
}
for _i in range(14, 25):
    CMD48_BYTE_NAME[_i] = f"Device-Specific Status {_i - 8}"

# 預設 (AmsDevRevId=-1) 的 9 個通用 HART 警報 AlertId (AmsUdf_GetHartAlertId)
DEFAULT_HART_ALERT_IDS = {
    "0100000000000000", "0200000000000000", "0400000000000000", "0800000000000000",
    "1000000000000000", "2000000000000000", "4000000000000000", "8000000000000000",
    "0001000000000000",
}

SYSDEF_ZH = {
    "AlertAutoSuppressionStatus": "重複警報自動抑制功能開關 (AmsSp_ReoccurringAlertCheck_1 讀取)",
    "AutoSuppressionMaxAlertsPerHour": "同一設備同一警報在觀察期內達此次數即開始抑制 (次)",
    "AutoSuppressionMaxAlertsPeriod": "觀察期長度 (小時)",
    "AutoSuppressionPeriod": "抑制持續時間 (小時)",
    "FC_AcceptablePointDeviation": "校正 (Field Communicator/校正記錄) 可接受點偏差 (%)",
    "FC_ChangeCalTimeDiff": "校正時間差門檻 (分鐘)",
    "FC_MeasurementSettlingTime": "校正量測穩定時間 (秒)",
    "FC_TemperatureStandard": "校正溫度標準代碼",
    "GlobalDeviceProtection": "全域裝置寫入保護 (Device Protection)",
    "SyncDbOnDeviceAccess": "存取裝置時自動同步資料庫",
}
POLICY_ZH = {
    "AuditTrail": "Trex 同步: 稽核軌跡 (Audit Trail)",
    "DeviceConfigs": "Trex 同步: 裝置組態",
    "HideDeAuthorized": "Trex 同步: 隱藏未授權裝置",
    "HideDisconnected": "Trex 同步: 隱藏已斷線裝置",
    "TrexSecurityWarnings": "Trex 同步: 顯示安全性警告",
    "UserConfigs": "Trex 同步: 使用者組態",
    "UserSecurity": "Trex 同步: 使用者安全性",
}

EMPTY_TABLES = [
    ("AlertList", "目前作用中警報清單 (Alert Monitor 主畫面資料)", "0 列 → Alert Monitor 從未收到/保留任何警報"),
    ("AlertLog", "警報事件記錄 (與 EventLog 以 EventIdDay/Fraction 連結)", "0 列 → 從未記錄任何裝置警報事件"),
    ("AlertFilterForDevice", "每台受監視裝置 × 警報之啟用/停用過濾設定", "0 列 → 沒有任何裝置被加入監視, 故無個別過濾設定"),
    ("DeviceMonitorList", "Alert Monitor 受監視裝置清單 (輪詢群組/頻率/DVM)", "0 列 → 沒有任何裝置被加入 Alert Monitor 監視"),
    ("DeviceAlertReoccurFilter", "重複警報自動抑制中的裝置/警報", "0 列 → 無警報被抑制 (亦因無警報)"),
    ("DeviceHealth", "裝置健康狀態 (Plantweb/Device Health 分類與時間)", "0 列 → 未使用裝置健康狀態功能"),
    ("DeviceHealthMonitor", "裝置健康監視區間", "0 列 → 未使用"),
    ("DeviceHealthSnapshots", "裝置健康每日快照", "0 列 → 未使用"),
    ("ProjectDeviceHealthSnapshots", "專案 × 健康快照", "0 列 → 未使用"),
    ("PoliciesAsgms", "行動裝置 (Trex) 與政策的指派", "0 列 → 無 Trex 行動裝置被指派政策"),
]


# ---------------------------------------------------------------- helpers
def _yesno(v):
    return "是" if bool(v) else "否"


def decode_alert_id(alert_id, protocol):
    """回傳 (格式, 狀態位元組/區塊, 位元/索引, 解碼說明)."""
    s = "" if alert_id is None else str(alert_id)
    is_hex16 = len(s) == 16 and all(c in "0123456789abcdefABCDEF" for c in s)
    if is_hex16:
        b = bytes.fromhex(s)
        mask = int.from_bytes(b[0:4], "little")
        idx = int.from_bytes(b[4:8], "little")
        bit = mask.bit_length() - 1 if mask and (mask & (mask - 1)) == 0 else None
        bit_txt = f"bit{bit}" if bit is not None else f"mask 0x{mask:08X}"
        if idx == 0:
            if mask == 0x0100:
                where = "AMS 內部: 通訊失敗 (NO_RESPONSE)"
                return ("HART 狀態位元", where, bit_txt, "AmsUdf_GetHartAlertId: 0x0100 = Device Not Responding")
            where = "HART Device Status 位元組 (回應碼第 2 個位元組 Field Device Status)"
            return ("HART 狀態位元", where, bit_txt, f"Device Status {bit_txt}")
        name = CMD48_BYTE_NAME.get(idx - 1, f"byte {idx - 1}")
        where = f"Cmd48 byte {idx - 1} ({name})"
        return ("HART 狀態位元", where, bit_txt, f"Command 48 Additional Status byte {idx - 1} {bit_txt}")
    parts = s.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        blk, par, bit = parts
        blk_name = {"257": "AI 功能區塊 (0x0101)", "258": "AO 功能區塊 (0x0102)", "262": "DO 功能區塊 (0x0106)",
                    "1000": "資源區塊 FF-912 現場診斷 (FD_*)"}.get(blk, f"區塊代碼 {blk}")
        return ("FF 區塊.參數.位元", blk_name, f"參數 {par} bit{bit}", f"區塊 {blk} / 參數相對索引 {par} / bit {bit}")
    if "(" in s and s.endswith(")"):
        head = s.split(".")[0]
        tail = s.split(".", 1)[1] if "." in s else ""
        return ("參數.值(型別)", head, tail, "DD 參數名稱.觸發值(資料型別), 常見於 PROFIBUS/其他 DD")
    return ("其他", "", "", "")


def _trim(txt, n=HELP_TRIM):
    if txt is None:
        return ""
    t = str(txt).replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(t) > n:
        return t[:n] + "…"
    return t


# ---------------------------------------------------------------- loaders
def _load_revisions(conn):
    """一列一 AmsDevRevId, 含製造商/協定/機型/版本與本廠設備數."""
    sql = """
    select r.AmsDevRevId, r.AmsDevTypeId, r.DeviceRevision, r.Name as RevName, r.Description as RevDescription,
           t.DeviceType as DeviceTypeCode, t.Name as DeviceTypeName, t.Description as DeviceTypeDescription,
           mp.MfrId, m.Name as Manufacturer, p.Name as Protocol
    from DeviceRevisions r
    left join DeviceTypes t on t.AmsDevTypeId = r.AmsDevTypeId
    left join MfrProtocols mp on mp.MfrProtocolId = t.MfrProtocolId
    left join Manufacturers m on m.AmsMfrNameId = mp.AmsMfrNameId
    left join DeviceProtocols p on p.ProtocolId = mp.ProtocolId
    """
    rev = pd.read_sql(sql, conn)
    dev = pd.read_sql("select AmsDevRevId, count(*) as DeviceCount from Devices where DeviceKey >= 0 group by AmsDevRevId", conn)
    rev = rev.merge(dev, on="AmsDevRevId", how="left")
    rev["DeviceCount"] = rev["DeviceCount"].fillna(0).astype(int)
    # -1 = AMS 預設 (通用 HART) 列
    m = rev["AmsDevRevId"] == -1
    rev.loc[m, "Manufacturer"] = "(AMS 預設)"
    rev.loc[m, "Protocol"] = "HART"
    rev.loc[m, "DeviceTypeName"] = "(通用 HART 預設警報)"
    rev.loc[m, "DeviceRevision"] = ""
    return rev


def _load_alerts(conn):
    a = pd.read_sql("select AlertDescId, AmsDevRevId, AlertId, Description, AlertTypeId from DeviceAlertDesc", conn)
    t = pd.read_sql("select AlertTypeId, Uid, AlertTypeName from AlertTypes", conn)
    e = pd.read_sql("select AlertDescId, DDHelpText, ExtendedHelpText from ExtDeviceAlertDesc", conn)
    p = pd.read_sql("select AlertDescId, ExtPropertyName, ExtPropertyValue from ExtDevAlertDescProp", conn)
    a = a.merge(t, on="AlertTypeId", how="left")
    a["AlertTypeName"] = a["AlertTypeName"].fillna("")
    a = a.merge(e, on="AlertDescId", how="left")
    # 屬性樞轉 (目前只有 AlertMonitorDefault 一種屬性; 若有其他屬性亦會成為欄位)
    pv = p.pivot_table(index="AlertDescId", columns="ExtPropertyName", values="ExtPropertyValue", aggfunc="first")
    pv.columns = [str(c) for c in pv.columns]
    a = a.merge(pv, left_on="AlertDescId", right_index=True, how="left")
    if "AlertMonitorDefault" not in a.columns:
        a["AlertMonitorDefault"] = None
    extra_props = [c for c in pv.columns if c != "AlertMonitorDefault"]
    return a, extra_props


def _alert_frame(a, rev, extra_props):
    df = a.merge(rev, on="AmsDevRevId", how="left")
    dec = [decode_alert_id(x, pr) for x, pr in zip(df["AlertId"], df["Protocol"])]
    df["fmt"] = [d[0] for d in dec]
    df["where"] = [d[1] for d in dec]
    df["bit"] = [d[2] for d in dec]
    df["dec_note"] = [d[3] for d in dec]
    df["sev"] = df["AlertTypeName"].map(ALERT_SEVERITY).fillna(0).astype(int)
    df["type_zh"] = df["AlertTypeName"].map(ALERT_TYPE_ZH).fillna(df["AlertTypeName"])
    df["mon_default"] = df["AlertMonitorDefault"].fillna("")
    df["mon_yes"] = df["mon_default"].map(lambda v: "是" if v == "ENABLED" else ("否" if v == "DISABLED" else ""))
    df["in_use"] = (df["DeviceCount"] > 0).map(_yesno)
    df["is_default9"] = df["AlertId"].isin(DEFAULT_HART_ALERT_IDS).map(_yesno)
    df["dd_help"] = df["DDHelpText"].map(_trim)
    df["ext_help"] = df["ExtendedHelpText"].map(_trim)
    df["dd_len"] = df["DDHelpText"].fillna("").map(len)
    df["ext_len"] = df["ExtendedHelpText"].fillna("").map(len)
    df["DeviceRevision"] = df["DeviceRevision"].fillna("").astype(str)
    df = df.sort_values(["DeviceCount", "Protocol", "Manufacturer", "DeviceTypeName", "DeviceRevision", "sev", "AlertId"],
                        ascending=[False, True, True, True, True, False, True], kind="mergesort")
    cols = {
        "通訊協定 (Protocol)": "Protocol",
        "製造商 (Manufacturer)": "Manufacturer",
        "機型 (DeviceTypes.Name)": "DeviceTypeName",
        "機型代碼 (DeviceType)": "DeviceTypeCode",
        "版本 (DeviceRevision)": "DeviceRevision",
        "本廠設備數 (Devices)": "DeviceCount",
        "使用中": "in_use",
        "警報代碼 (AlertId)": "AlertId",
        "警報說明 (Description)": "Description",
        "警報類別 (AlertTypeName)": "AlertTypeName",
        "警報類別中文": "type_zh",
        "AMS嚴重度排序 (5高-0低)": "sev",
        "預設監視 (AlertMonitorDefault)": "mon_default",
        "預設監視啟用": "mon_yes",
        "代碼格式": "fmt",
        "狀態位元組/區塊": "where",
        "位元/參數索引": "bit",
        "代碼解碼說明": "dec_note",
        "屬通用HART預設9警報": "is_default9",
        "DD說明 (DDHelpText, 截至500字)": "dd_help",
        "延伸說明 (ExtendedHelpText, 截至500字)": "ext_help",
        "DD說明原長度": "dd_len",
        "延伸說明原長度": "ext_len",
        "AlertDescId": "AlertDescId",
        "AmsDevRevId": "AmsDevRevId",
        "AlertTypeId": "AlertTypeId",
    }
    out = pd.DataFrame({k: df[v].values for k, v in cols.items()})
    for c in extra_props:
        out[f"屬性 {c} (ExtDevAlertDescProp)"] = df[c].fillna("").values
    return out, df


# ---------------------------------------------------------------- build
def build(conn):
    sheets = []
    rev = _load_revisions(conn)
    a, extra_props = _load_alerts(conn)
    full, raw = _alert_frame(a, rev, extra_props)

    n_types = raw["AlertTypeName"].value_counts()
    n_dis = int((raw["mon_default"] == "DISABLED").sum())
    n_en = int((raw["mon_default"] == "ENABLED").sum())

    # ---- 1. in use
    inuse = full[full["使用中"] == "是"].drop(columns=["使用中"]).reset_index(drop=True)
    n_rev_inuse = inuse["AmsDevRevId"].nunique()
    per_rev = (raw[raw["DeviceCount"] > 0].groupby("AmsDevRevId")
               .agg(n=("AlertId", "size"), d9=("is_default9", lambda s: int((s == "是").sum())),
                    dev=("DeviceCount", "first"), name=("DeviceTypeName", "first"), mfr=("Manufacturer", "first"),
                    r=("DeviceRevision", "first")))
    d9 = per_rev[(per_rev["n"] == 9) & (per_rev["d9"] == 9)].sort_values("dev", ascending=False)
    d9_txt = "、".join(f"{m} {n} rev{r} ({int(d)}台)" for m, n, r, d in zip(d9["mfr"], d9["name"], d9["r"], d9["dev"]))
    d9_dev = int(d9["dev"].sum())
    sheets.append({
        "name": "使用中機型警報定義",
        "purpose": "本廠實際有設備的機型版本 (Devices 計數>0) 之全部警報定義, 供查閱各機型會在 AMS 產生哪些警報、預設是否監視、以及 DD 說明/建議措施",
        "one_row": "一個機型版本 (AmsDevRevId) 的一個警報定義 (DeviceAlertDesc 一列)",
        "df": inuse,
        "notes": [
            f"使用中機型版本 {n_rev_inuse} 個 (本廠 1,928 台設備全部落在這 {n_rev_inuse} 個版本內; 沒有任何使用中版本缺少警報定義), 共 {len(inuse):,} 筆警報定義。",
            "警報定義是隨裝置 DD (Device Description) 安裝時由 AmsSp_AddDeviceAlertDesc_1 寫入, 屬於『機型』層級, 不是個別裝置的實際警報。實際警報應存於 AlertList/AlertLog/EventLog, 本資料庫這些表為空 (見『系統設定與警報監視狀態』)。",
            "警報代碼 (AlertId) 解碼: (a) 16 位十六進位 = 8 bytes; 前 4 bytes 小端序整數為位元遮罩 (0x01..0x80, 0x0100=通訊失敗), 後 4 bytes 小端序整數為狀態位元組索引: 0 = HART Device Status 位元組, k≥1 = Command 48 Additional Status byte k-1 (HART7: byte6=Extended Device Status, byte8=Standardized Status 0 ...)。證據: _modules AmsUdf_GetHartAlertId 定義 0x0001→'0100000000000000'、0x0100→'0001000000000000'; 且 byte8 bit0 全庫 655 筆中 335 筆為 'Simulation Active' (其餘為廠牌自訂文字), byte6 bit0 643 筆中 503 筆為 'Maintenance Required', byte10 bit0 286 筆 'Secondary analog channel saturated', byte13 bit0 286 筆 'Secondary analog channel fixed', 與 HART 7 Cmd48 規格一致。索引 >25 (Cmd48 未定義的 byte) 全庫僅 130 餘筆, 顯示為 'byte N'。前 4 bytes 非單一位元者 (全庫 1,501 筆, 使用中 16 筆, 顯示為 'mask 0x..') 為『狀態位元組等於該枚舉值』的比對 (例 0A00000005000000 = Cmd48 byte4 值 0x0A 'Incorrect password'; 0000000007000000 = byte6 值 0 'Normal')。",
            "(b) FF 代碼 '區塊.參數.位元' (例 1000.79.3): 區塊代碼 257/258/262 對應 FF 功能區塊 profile AI(0x0101)/AO(0x0102)/DO(0x0106); 1000 為資源區塊 FF-912 現場診斷 (FD_FAIL/OFFSPEC/MAINT/CHECK 四組, 各對應 FAILED/MAINT/ADVISE/CHKFNC 類別); 參數索引為 DD 相對索引, 依廠牌不同 (中等信心)。(c) 'M10_P40_BITWISE.256(b)' 形式為 DD 參數名.觸發值(型別), 僅見於未使用的 PROFIBUS/其他機型。",
            "預設監視 (AlertMonitorDefault): ENABLED/DISABLED 為 DD 提供的『加入 Alert Monitor 時是否預設監視此警報』。AmsSp_AL_GetDeviceAlertDescForDevice_2: 非 DISABLED 即視為 Enabled。",
            "AMS嚴重度排序: 來源 AmsVw_Monitoring_DeviceAlertMetadata (FAILED=5, MAINT=4, ABNORM=3, CHKFNC=2, ADVISE=1, COMM/未知=0); 該視圖並排除 COMM 類別 (不可建過濾)。",
            "DD說明/延伸說明 已截至 500 字 (原長度另列); AMS 顯示的『建議措施 (Recommendation)』= 延伸說明優先, 空則用 DD 說明。",
            f"僅含通用 HART 預設 9 警報 (無 DD 專屬警報, 全為 ABNORM 類別) 的使用中版本共 {len(d9)} 個、{d9_dev} 台: {d9_txt}。這些機型在 AMS 只能偵測 HART 標準狀態位元 (推論: 使用 Generic/預設 DD 或 DD 未含警報描述檔)。",
            "警報說明為空字串者為 DD 未提供文字 (例 3051 rev9 的 0001000000000000 通訊失敗)。",
            "排序: 本廠設備數 (多→少)、協定、製造商、機型、版本、嚴重度 (高→低)、警報代碼。",
        ],
        "source_tables": ["DeviceAlertDesc", "ExtDeviceAlertDesc", "ExtDevAlertDescProp", "AlertTypes", "DeviceRevisions",
                          "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "Devices"],
    })

    # ---- 2. per revision summary
    g = raw.groupby("AmsDevRevId")
    summ = g.agg(
        Protocol=("Protocol", "first"), Manufacturer=("Manufacturer", "first"), DeviceTypeName=("DeviceTypeName", "first"),
        DeviceTypeCode=("DeviceTypeCode", "first"), DeviceRevision=("DeviceRevision", "first"), RevName=("RevName", "first"),
        DeviceCount=("DeviceCount", "first"), n=("AlertDescId", "size"),
        n_en=("mon_default", lambda s: int((s == "ENABLED").sum())),
        n_dis=("mon_default", lambda s: int((s == "DISABLED").sum())),
        n_dd=("dd_len", lambda s: int((s > 0).sum())), n_ext=("ext_len", lambda s: int((s > 0).sum())),
        n_hex=("fmt", lambda s: int((s == "HART 狀態位元").sum())), n_ff=("fmt", lambda s: int((s == "FF 區塊.參數.位元").sum())),
        n_d9=("is_default9", lambda s: int((s == "是").sum())),
    ).reset_index()
    ct = pd.crosstab(raw["AmsDevRevId"], raw["AlertTypeName"]).reset_index()
    ct.columns = [str(c) for c in ct.columns]
    summ = summ.merge(ct, on="AmsDevRevId", how="left")
    for tname in ["FAILED", "MAINT", "ADVISE", "ABNORM", "COMM", "CHKFNC", ""]:
        if tname not in summ.columns:
            summ[tname] = 0
        summ[tname] = summ[tname].fillna(0).astype(int)
    summ["in_use"] = (summ["DeviceCount"] > 0).map(_yesno)
    summ["only_d9"] = ((summ["n"] == 9) & (summ["n_d9"] == 9)).map(_yesno)
    summ = summ.sort_values(["DeviceCount", "Protocol", "Manufacturer", "DeviceTypeName", "DeviceRevision"],
                            ascending=[False, True, True, True, True], kind="mergesort")
    summ_out = pd.DataFrame({
        "使用中": summ["in_use"].values,
        "本廠設備數 (Devices)": summ["DeviceCount"].values,
        "通訊協定 (Protocol)": summ["Protocol"].values,
        "製造商 (Manufacturer)": summ["Manufacturer"].values,
        "機型 (DeviceTypes.Name)": summ["DeviceTypeName"].values,
        "機型代碼 (DeviceType)": summ["DeviceTypeCode"].values,
        "版本 (DeviceRevision)": summ["DeviceRevision"].fillna("").astype(str).values,
        "警報定義總數": summ["n"].values,
        "失效 FAILED": summ["FAILED"].values,
        "需維護 MAINT": summ["MAINT"].values,
        "建議 ADVISE": summ["ADVISE"].values,
        "異常 ABNORM": summ["ABNORM"].values,
        "通訊失敗 COMM": summ["COMM"].values,
        "功能檢查 CHKFNC": summ["CHKFNC"].values,
        "未知類別": summ[""].values,
        "預設監視啟用數 (ENABLED)": summ["n_en"].values,
        "預設監視停用數 (DISABLED)": summ["n_dis"].values,
        "有DD說明數": summ["n_dd"].values,
        "有延伸說明數": summ["n_ext"].values,
        "HART狀態位元代碼數": summ["n_hex"].values,
        "FF區塊代碼數": summ["n_ff"].values,
        "僅通用HART預設9警報": summ["only_d9"].values,
        "AmsDevRevId": summ["AmsDevRevId"].values,
    })
    n_rev_all = len(summ_out)
    n_only9 = int((summ_out["僅通用HART預設9警報"] == "是").sum())
    n_revs_total = int(pd.read_sql("select count(*) as n from DeviceRevisions", conn)["n"].iloc[0])
    sheets.append({
        "name": "機型警報數量彙總",
        "purpose": "每個機型版本的警報定義數量統計 (依類別/預設監視/說明文字), 使用中版本排前, 用以比較各機型的診斷能力",
        "one_row": "一個機型版本 (AmsDevRevId) 的警報定義彙總",
        "df": summ_out,
        "notes": [
            f"共 {n_rev_all:,} 個有警報定義的機型版本 (DeviceRevisions 共 {n_revs_total:,} 版本, 其中 {n_revs_total - n_rev_all} 個無警報定義且皆非本廠使用); 使用中 {n_rev_inuse} 個。",
            f"全庫 {len(raw):,} 筆警報定義: FAILED {int(n_types.get('FAILED', 0)):,}、MAINT {int(n_types.get('MAINT', 0)):,}、ADVISE {int(n_types.get('ADVISE', 0)):,}、ABNORM {int(n_types.get('ABNORM', 0)):,}、COMM {int(n_types.get('COMM', 0)):,}、CHKFNC {int(n_types.get('CHKFNC', 0)):,}; 預設監視 ENABLED {n_en:,} / DISABLED {n_dis:,}。",
            f"『僅通用HART預設9警報』= 該版本恰為 AMS 預設的 9 個 HART 狀態位元警報 (全庫 {n_only9:,} 個版本), 表示 DD 未提供裝置專屬診斷警報。",
            "AmsDevRevId = -1 為 AMS 預設列 (AmsSp_GetDefaultHartAlertDesc_1 以 AmsDevRevId=-1 取預設說明), 非實際機型。",
            f"『未知類別』欄全為 0: AlertTypeId 0 (ALERT_UNKNOWN_ID) 在 DeviceAlertDesc 全庫無任何使用 (全庫 {int(n_types.get('', 0))} 筆), 欄位保留以對齊 AlertTypes 代碼表。",
        ],
        "source_tables": ["DeviceAlertDesc", "ExtDeviceAlertDesc", "ExtDevAlertDescProp", "AlertTypes", "DeviceRevisions",
                          "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "Devices"],
    })

    # ---- 3. full list
    sheets.append({
        "name": "全部警報定義",
        "purpose": "DeviceAlertDesc 全部警報定義 (含本廠未使用的機型版本), 欄位同『使用中機型警報定義』並加『使用中』欄",
        "one_row": "DeviceAlertDesc 一列 (一個機型版本的一個警報定義)",
        "df": full.reset_index(drop=True),
        "notes": [
            f"{len(full):,} 列 = DeviceAlertDesc 全表 (未達 1,000,000 列上限, 未截斷); ExtDeviceAlertDesc / ExtDevAlertDescProp 與其一對一 (皆 140,438 列, 無孤兒、無重複)。",
            "解碼規則與欄位定義同『使用中機型警報定義』的 notes。",
            "使用中=否 的版本是 AMS 安裝的 DD 程式庫內容 (2,000+ 機型版本), 與本廠設備無關, 僅供查詢。",
        ],
        "source_tables": ["DeviceAlertDesc", "ExtDeviceAlertDesc", "ExtDevAlertDescProp", "AlertTypes", "DeviceRevisions",
                          "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "Devices"],
    })

    # ---- 4. alert types
    t = pd.read_sql("select AlertTypeId, Uid, AlertTypeName from AlertTypes order by AlertTypeId", conn)
    t["AlertTypeName"] = t["AlertTypeName"].fillna("")
    cnt = raw["AlertTypeId"].value_counts()
    cnt_inuse = raw[raw["DeviceCount"] > 0]["AlertTypeId"].value_counts()
    types_out = pd.DataFrame({
        "AlertTypeId": t["AlertTypeId"],
        "類別名稱 (AlertTypeName)": t["AlertTypeName"],
        "類別中文": t["AlertTypeName"].map(ALERT_TYPE_ZH).fillna(""),
        "識別碼 (Uid)": t["Uid"],
        "AMS嚴重度排序 (5高-0低)": t["AlertTypeName"].map(ALERT_SEVERITY).fillna(0).astype(int),
        "全庫警報定義數": t["AlertTypeId"].map(cnt).fillna(0).astype(int),
        "使用中機型警報定義數": t["AlertTypeId"].map(cnt_inuse).fillna(0).astype(int),
        "說明": t["AlertTypeName"].map({
            "FAILED": "裝置失效, 量測/輸出不可信 (Plantweb Alert: Failed)",
            "MAINT": "需維護, 短期內應處理 (Maintenance)",
            "ADVISE": "建議/提示性資訊 (Advisory)",
            "ABNORM": "異常狀態; 通用 HART 狀態位元警報皆屬此類 (Abnormal)",
            "COMM": "通訊失敗 (Device Not Responding), AMS 內部產生, 不可建過濾",
            "CHKFNC": "功能檢查中 (NAMUR NE107 Check Function), FF-912 FD_CHECK",
            "": "未知類別 (AMS 保留)",
        }).fillna(""),
    })
    sheets.append({
        "name": "警報類別代碼",
        "purpose": "AlertTypes 代碼表, 對照 NAMUR NE107 / Plantweb 警報類別與 AMS 嚴重度排序",
        "one_row": "一個警報類別 (AlertTypes 一列)",
        "df": types_out,
        "notes": [
            "嚴重度排序取自 AmsVw_Monitoring_DeviceAlertMetadata 的 CASE 敘述; Uid 為 DD 警報描述檔 (AlertDescriptor) 使用的字串鍵。",
            "AlertTypeId 0 (ALERT_UNKNOWN_ID) 在 DeviceAlertDesc 無任何使用。",
        ],
        "source_tables": ["AlertTypes", "DeviceAlertDesc"],
    })

    # ---- 5. network properties pivot
    ni = pd.read_sql("select NetworkInfoKey, PlantServerKey, NetworkId, NetworkName, NetworkKindAsString from NetworkInfo", conn)
    nip = pd.read_sql("select NetworkInfoKey, NetworkInfoPropertyKey, NetworkInfoPropertyValue from NetworkInfoProperty", conn)
    dl = pd.read_sql("select NetworkInfoKey, count(*) as DevCount from DeviceLocation group by NetworkInfoKey", conn)
    pv = nip.pivot_table(index="NetworkInfoKey", columns="NetworkInfoPropertyKey", values="NetworkInfoPropertyValue", aggfunc="first")
    pv.columns = [str(c) for c in pv.columns]
    net = ni.merge(dl, on="NetworkInfoKey", how="left").merge(pv, left_on="NetworkInfoKey", right_index=True, how="left")
    net["DevCount"] = net["DevCount"].fillna(0).astype(int)
    net = net[net["NetworkInfoKey"] >= 0].sort_values("NetworkInfoKey")
    first = ["Port", "Baud", "SCAN_RANGE_START", "SCAN_RANGE_STOP", "HART_TIMEOUT", "HART_RETRIES", "HART_BUSY_RETRIES", "Retries",
             "HSE_TCPIPADDRESS", "FFAlertProcessingEnabled", "FFAlertMulticastIP", "FFAlertPort", "NoCommPollingInterval",
             "AutomaticDiscoveryEnabled", "Simulated", "ConfiguredSimulation", "Persist File", "Network Searcher Type"]
    rest = [c for c in pv.columns if c not in first]
    net_out = pd.DataFrame({
        "網路鍵 (NetworkInfoKey)": net["NetworkInfoKey"].values,
        "網路代號 (NetworkId)": net["NetworkId"].values,
        "網路名稱 (NetworkName)": net["NetworkName"].values,
        "網路種類 (NetworkKindAsString)": net["NetworkKindAsString"].values,
        "所屬設備數 (DeviceLocation)": net["DevCount"].values,
    })
    zh_first = {"Port": "COM 埠 (Port)", "Baud": "鮑率 (Baud)", "SCAN_RANGE_START": "HART 掃描位址起 (SCAN_RANGE_START)",
                "SCAN_RANGE_STOP": "HART 掃描位址迄 (SCAN_RANGE_STOP)", "HART_TIMEOUT": "HART 逾時 ms (HART_TIMEOUT)",
                "HART_RETRIES": "HART 重試次數 (HART_RETRIES)", "HART_BUSY_RETRIES": "HART 忙碌重試 (HART_BUSY_RETRIES)",
                "Retries": "重試 (Retries)", "HSE_TCPIPADDRESS": "HSE IP (HSE_TCPIPADDRESS)",
                "FFAlertProcessingEnabled": "FF 警報處理啟用 (FFAlertProcessingEnabled)", "FFAlertMulticastIP": "FF 警報多播 IP (FFAlertMulticastIP)",
                "FFAlertPort": "FF 警報埠 (FFAlertPort)", "NoCommPollingInterval": "無通訊輪詢間隔 ms (NoCommPollingInterval)",
                "AutomaticDiscoveryEnabled": "自動探索 (AutomaticDiscoveryEnabled)", "Simulated": "模擬 (Simulated)",
                "ConfiguredSimulation": "組態模擬 (ConfiguredSimulation)", "Persist File": "持久化檔案 (Persist File)",
                "Network Searcher Type": "網路搜尋器類型 (Network Searcher Type)"}
    for c in first:
        if c in net.columns:
            net_out[zh_first.get(c, c)] = net[c].fillna("").values
    for c in rest:
        net_out[c] = net[c].fillna("").values
    ff_alert = ""
    ffrow = net[net["NetworkKindAsString"].str.contains("FF", na=False)]
    if len(ffrow) and "FFAlertProcessingEnabled" in ffrow.columns:
        ff_alert = str(ffrow["FFAlertProcessingEnabled"].iloc[0])
    # 全空欄 (屬性存在但值為空字串) 與全網路同值欄, 供讀者辨識
    prop_cols = [c for c in net_out.columns if c not in ("網路鍵 (NetworkInfoKey)", "網路代號 (NetworkId)", "網路名稱 (NetworkName)",
                                                          "網路種類 (NetworkKindAsString)", "所屬設備數 (DeviceLocation)")]
    all_empty_cols = [c for c in prop_cols if (net_out[c].astype(str).str.strip() == "").all()]
    const_cols = [f"{c}={net_out[c].iloc[0]}" for c in prop_cols
                  if c not in all_empty_cols and net_out[c].astype(str).nunique() == 1]
    sheets.append({
        "name": "網路通訊與輪詢設定",
        "purpose": "AMS 每個通訊網路 (18 個 HART Mux 網路 + 1 個 FF HSE 網路) 的連線與輪詢參數, 含 FF 警報處理開關",
        "one_row": "一個 AMS 網路 (NetworkInfo 一列, NetworkInfoProperty 依屬性名樞轉成欄)",
        "df": net_out,
        "notes": [
            f"NetworkInfoProperty {len(nip):,} 列樞轉為欄; Mux 網路各 30 個屬性, FF HSE 網路 39 個屬性 (FF 專屬: HSE_TCPIPADDRESS, FFAlert*, NoCommPollingInterval 等), 空白代表該網路無此屬性。",
            f"FF HSE 網路的 FFAlertProcessingEnabled = '{ff_alert}' → FF 裝置的主動警報 (Alert 多播 239.255.0.33:45000) 未被 AMS 處理 (推論信心: 高, 直接讀值)。",
            "HART Mux 網路: SCAN_RANGE_START/STOP = 多點位址掃描範圍, HART_TIMEOUT/RETRIES 為通訊參數; 這些屬於裝置存取設定, 與 Alert Monitor 輪詢 (DeviceMonitorList.Frequency) 不同, 後者為空。",
            "AmsNetworkId_Unknown (NetworkInfoKey=-1) 保留列已排除。",
            f"全空欄 ({len(all_empty_cols)} 欄, 屬性存在於 NetworkInfoProperty 但值為空字串, 皆為 FF HSE 網路專屬未設定項): {', '.join(all_empty_cols)}。",
            f"全部 19 個網路同值的欄 ({len(const_cols)} 欄, AMS 安裝預設值): {'; '.join(const_cols)}。",
        ],
        "source_tables": ["NetworkInfo", "NetworkInfoProperty", "DeviceLocation"],
    })

    # ---- 6. system settings + empty tables
    rows = []
    sd = pd.read_sql("select Parameter, Data from SystemDefaults order by Parameter", conn)
    for p_, d_ in zip(sd["Parameter"], sd["Data"]):
        rows.append(("SystemDefaults 系統預設", p_, d_, SYSDEF_ZH.get(p_, ""), "SystemDefaults", None))
    sp = pd.read_sql("select StationPropertyKey, PlantServerKey, StationInfoPropertySection, StationInfoPropertyKey, StationInfoPropertyValue from StationProperty", conn)
    for r in sp.itertuples():
        zh = ""
        if r.StationInfoPropertyKey == "PollingFactor":
            zh = "Alert Monitor 輪詢因子 (ALARM 區段); 僅在 DeviceMonitorList 有裝置時生效, 本廠無受監視裝置"
        rows.append(("StationProperty 站台屬性", f"{r.StationInfoPropertySection}/{r.StationInfoPropertyKey}", r.StationInfoPropertyValue, zh, "StationProperty", None))
    ps = pd.read_sql("select PlantServerKey, PlantServerId, AlertMonitorEnabled from PlantServer where PlantServerKey >= 0", conn)
    for r in ps.itertuples():
        rows.append(("PlantServer 伺服器", f"{r.PlantServerId}/AlertMonitorEnabled", _yesno(r.AlertMonitorEnabled),
                     "伺服器層級 Alert Monitor 服務開關 (AmsSp_DevBlk_GetAlertMonitorStatus_1: 1=裝置在監視清單時可輪詢); 但監視清單為空, 實際無裝置被監視", "PlantServer", None))
    pol = pd.read_sql("""select p.PolicyKey, p.Name, p.Enable, pt.PolicyTypeName, pp.Name as PropName, pp.Value
                         from Policies p left join PolicyTypes pt on pt.PolicyTypeId = p.PolicyTypeId
                         left join PolicyProperties pp on pp.PolicyKey = p.PolicyKey order by p.PolicyKey, pp.Name""", conn)
    seen = set()
    for r in pol.itertuples():
        if r.PolicyKey not in seen:
            seen.add(r.PolicyKey)
            rows.append(("Policies 政策", f"{r.Name} (類型 {r.PolicyTypeName})/Enable", _yesno(r.Enable),
                         "AMS Trex 行動通訊器同步政策 (PolicyTypes: 0=TrexSync); PoliciesAsgms 為空 → 未指派給任何 Trex", "Policies/PolicyTypes", None))
        if r.PropName is not None:
            rows.append(("PolicyProperties 政策屬性", f"{r.Name}/{r.PropName}", r.Value, POLICY_ZH.get(r.PropName, ""), "PolicyProperties", None))
    ut = pd.read_sql("select AlertState, UpdateCount, InitializeTime, LastUpdateTime, LastAddTime from AlertList_UpdateTracking", conn)
    for r in ut.itertuples():
        rows.append(("AlertList_UpdateTracking 警報清單更新追蹤", f"AlertState={str(r.AlertState).strip()}",
                     f"UpdateCount={r.UpdateCount}; InitializeTime={r.InitializeTime} (UTC); LastUpdateTime={r.LastUpdateTime} (UTC); LastAddTime={r.LastAddTime} (UTC)",
                     "UpdateCount=0 且三個時間皆為 1970-01-01 00:00:00 UTC (Unix epoch 哨兵值, 未初始化, 故不換算台灣時間) → Alert List 從未被更新/新增過", "AlertList_UpdateTracking", None))
    tbl_counts = dict(pd.read_sql("select table_name, row_count from _tables", conn).values)
    for tname, desc, interp in EMPTY_TABLES:
        n = int(tbl_counts.get(tname, 0))
        rows.append(("空表 (警報/健康/監視)", tname, n, f"{desc}; {interp}", tname, n))
    ev = pd.read_sql("select count(*) as n from EventLog where Category in (20,21,30,31,62,63)", conn)["n"].iloc[0]
    rows.append(("交叉驗證", "EventLog 中警報類別事件數 (Category 20/21/30/31/62/63)", int(ev),
                 "AmsSp_ReoccurringAlertCheck_1 定義 20/30/62 = 警報發生、21/31/63 = 警報解除; 0 筆 → 事件記錄亦無任何裝置警報", "EventLog", None))
    rows.append(("推論", "本廠 Alert Monitor 使用狀態", "未啟用/未使用",
                 "信心: 高。證據: DeviceMonitorList 0 列、AlertList 0 列、AlertLog 0 列、AlertFilterForDevice 0 列、AlertList_UpdateTracking 未初始化、EventLog 無警報類別事件、FF 網路 FFAlertProcessingEnabled=No; 雖 PlantServer.AlertMonitorEnabled=是 (服務層級開關) 且 SystemDefaults 自動抑制=true, 但沒有任何裝置被加入監視清單, 故 AMS 從未產生或記錄任何裝置警報。", "", None))
    rows.append(("推論", "Device Health / Plantweb 健康快照", "未使用",
                 "信心: 高。DeviceHealth/DeviceHealthMonitor/DeviceHealthSnapshots/ProjectDeviceHealthSnapshots 皆 0 列。", "", None))
    sys_out = pd.DataFrame(rows, columns=["區塊", "項目", "值", "說明/解讀", "來源表 (source)", "資料列數 (空表)"])
    sys_out["值"] = sys_out["值"].astype(str)
    sys_out["資料列數 (空表)"] = sys_out["資料列數 (空表)"].astype("Int64")
    sheets.append({
        "name": "系統設定與警報監視狀態",
        "purpose": "AMS 系統層級設定 (SystemDefaults/StationProperty/PlantServer/Policies) 與警報監視相關空表清單, 並給出本廠 Alert Monitor 使用狀態的推論",
        "one_row": "一個設定項目、一個空表或一條推論",
        "df": sys_out,
        "notes": [
            "空表 (0 列, 不另建工作表): AlertList、AlertLog、AlertFilterForDevice、DeviceMonitorList、DeviceAlertReoccurFilter、DeviceHealth、DeviceHealthMonitor、DeviceHealthSnapshots、ProjectDeviceHealthSnapshots、PoliciesAsgms。",
            "SystemDefaults 的 AutoSuppression* 四項為『重複警報自動抑制』參數 (AmsSp_ReoccurringAlertCheck_1): 觀察期 1 小時內同一設備同一警報 ≥5 次即抑制 24 小時; 因無警報, 從未觸發。",
            "FC_* 為校正/現場通訊器相關預設; GlobalDeviceProtection=false 表示未啟用全域裝置寫入保護。",
            "Policies 僅 1 筆 TrexSync (AMS Trex 同步政策), 屬性 7 項皆為 Trex 同步選項, 與警報無關。",
        ],
        "source_tables": ["SystemDefaults", "StationProperty", "PlantServer", "Policies", "PolicyProperties", "PolicyTypes",
                          "AlertList_UpdateTracking", "_tables", "EventLog"],
    })
    return sheets


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
        print(f"{s['name']}: {len(df):,} rows x {df.shape[1]} cols")
        path = os.path.join(OUT_DIR, f"{KEY}__{s['name']}.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"done in {time.time() - t0:.1f}s")
