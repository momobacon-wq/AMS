# -*- coding: utf-8 -*-
"""
Domain: devices (設備、位號與實體位置) — AMS Device Manager AmsDb (SQL Server backup 20260912, plant 新複循環廠, server AMS1SVR)

build(conn) -> list[dict]  (one dict per sheet; see README rules in orchestrator)

Decode rules (evidence in _modules of AmsDb):
  * Current AMS tag  : ExtBlockTags JOIN BlockAsgms WHERE EventIdDayOut = 49710  (AmsVw_CurrentTagBlockAsgms, AmsSp_GetAdd_AssignDevTag_1
                       inserts EventIdDayOut=49710 / FractionOut=0 as the "still open" sentinel; 49710 = OLE day 2036-02-07).
  * Device-level block: Blocks.BlockIndex = 0 (AmsVw_DeviceLevelBlockKey); DeviceLocation / BlockAsgms only reference these.
  * Event id -> time  : AmsUdf_EventIdDayFractionToDateTime: OLE date serial; UTC = 1899-12-30 + day + fraction/2^31 days.  Taiwan = UTC+8.
  * IdentStatus       : AmsUdf_DevBlkIdentStatusAsString: 1 = identified, 0/other = unknown.  AmsSp_DevBlk_ReconcileIdentStatus_1 sets 0 when a
                       rescan of the same HostPath no longer finds the device -> 0 means "last scan could not re-identify device at this path".
  * FF block name     : AmsUdf_GetFFBlockName: R -> RESOURCE, T -> TRANSDUCER<idx>, F -> FUNCTION<idx>.
  * Auto tag          : AmsSp_CreateAmsTagName_1 / AmsSp_GetAdd_AssignDevTag_1: an empty device tag gets 'MM/DD/YYYY hh:mm:ss.fff' (server local time).
  * Dup tag suffix    : AmsSp_UnassignedTag_Get_1: if the tag is already assigned, AMS appends _01.._99.
  * HostPath (Mux)    : '<COM port#>.<MUX addr>.<code>.<MUX HART UID>.<device HART UID>.<channel|MUX_DEVICE>.<MUX addr|0>.<HART rev>'
                       (verified: seg1 == NetworkInfoProperty 'Port' number, seg2 == AmsPath mux segment, seg6 == AmsPath channel segment,
                        seg8 == Devices.ProtocolRevision for all 1,577 HART rows; seg4==seg5 exactly for the 253 MUX_DEVICE rows).
  * HostPath (FF)     : '<linking-device id>/<link#>/<device tag>' ; AmsPath 'net!AMS1SVR!FF Block 1!<LD name>!Link #<n>!<tag>'.
"""
import os
import re
import sqlite3
import datetime as _dt

import pandas as pd

DB_PATH = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/AmsDb.sqlite"
OUT_DIR = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/build/out"
PREV_XLSX = r"C:/Users/bacon/我的雲端硬碟/@@新機組資料備份/AMS/20260910_AMS解析.xlsx"
KEY = "devices"

OPEN_DAY = 49710                     # BlockAsgms.EventIdDayOut sentinel = still assigned
OLE_EPOCH = _dt.datetime(1899, 12, 30)
TW_OFFSET = pd.Timedelta(hours=8)

DOMAIN_TABLES = ["Devices", "Blocks", "DeviceLocation", "NetworkInfo", "NetworkInfoProperty", "PlantServer", "DeviceAssets", "Assets",
                 "ExtBlockTags", "BlockAsgms", "DeviceRevisions", "DeviceTypes", "Manufacturers", "MfrProtocols", "DeviceProtocols",
                 "DeviceCategories", "MajorDeviceCategories", "MinorDeviceCategories", "Dispositions", "CalStatus", "DevRevExtProperty",
                 "Hierarchies", "Labels"]

# ----------------------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------------------
def _q(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def ole_to_utc(day, frac):
    """EventIdDay/EventIdFraction -> pandas UTC-naive datetime (AmsUdf_EventIdDayFractionToDateTime). 0/0 -> NaT."""
    day = pd.to_numeric(day, errors="coerce")
    frac = pd.to_numeric(frac, errors="coerce")
    secs = (day.astype("float64") + frac.astype("float64") / 2147483648.0) * 86400.0
    out = pd.to_datetime(OLE_EPOCH) + pd.to_timedelta(secs, unit="s")
    out = out.where((day > 0) & (day != OPEN_DAY))
    return out.dt.round("ms")


def utc_text(ts):
    return ts.dt.strftime("%Y-%m-%d %H:%M:%S").where(ts.notna(), "")


def to_tw(ts):
    return ts + TW_OFFSET


def yes_no(s):
    return s.map(lambda v: "是" if bool(v) else "否")


_BAD = re.compile(r"[^\x20-\x7e]")
_TAIL_JUNK = re.compile(r"\s{2,}\S{1,2}$")     # HART long-tag read residue: 2+ padding spaces then 1-2 garbage chars (ASCII or not)


def clean_tag(t):
    """strip trailing junk bytes / padding that HART short-tag reads leave behind."""
    if t is None:
        return ""
    s = _BAD.sub("", str(t))
    s = _TAIL_JUNK.sub("", s)
    return s.strip()


def tag_quality(raw):
    if raw is None or str(raw).strip() == "":
        return "空白"
    s = str(raw)
    if _BAD.search(s):
        return "含非可列印字元"
    if _TAIL_JUNK.search(s):
        return "含尾端殘碼(填充空白+雜字元)"
    if re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\.\d{3}", s.strip()):
        return "AMS自動時間戳位號"
    if re.fullmatch(r"_+", s.strip()) or re.fullmatch(r"X+", s.strip()):
        return "佔位字元"
    return "正常"


KKS_RE = re.compile(r"^([GSC]\d{2})([A-Z]{3})(\d{2})([A-Z]{2})(\d{3})(?:_.*)?$")
UNIT_RE = re.compile(r"^(G1[12]|S10|C10|C53)")


def kks_parts(tag):
    """Return (unit, system, system_no, equip_code, seq) for KKS style tags like G12LAB16QN005, else unit only where detectable."""
    t = clean_tag(tag)
    m = KKS_RE.match(t)
    if m:
        return m.groups()
    m2 = UNIT_RE.match(t)
    unit = m2.group(1) if m2 else ""
    return (unit, "", "", "", "")


UNIT_ZH = {"G11": "GT11 燃氣輪機 #1 / HRSG11 側", "G12": "GT12 燃氣輪機 #2 / HRSG12 側", "S10": "ST10 汽輪機", "C10": "C10 共用/BOP 系統", "C53": "C53"}


def parse_hostpath(ap, hp):
    """Split AmsPath / HostPath into a dict of components. Works for Mux networks and the FF HSE network."""
    d = dict(net_seg="", mux_addr=None, channel="", is_mux=False, ld_name="", ld_id="", link_no=None, com_port=None,
             hp_code="", mux_uid="", dev_uid="", hp_hart_rev=None)
    a = (ap or "").split("!")
    if len(a) >= 3:
        d["net_seg"] = a[2]
    if len(a) == 5:                     # net!AMS1SVR!<network>!<mux>!<channel|MUX_DEVICE>
        try:
            d["mux_addr"] = int(a[3])
        except ValueError:
            d["mux_addr"] = None
        d["channel"] = a[4]
        d["is_mux"] = a[4] == "MUX_DEVICE"
        s = (hp or "").split(".")
        if len(s) == 8:
            d["com_port"] = int(s[0]) if s[0].isdigit() else None
            d["hp_code"] = s[2]
            d["mux_uid"] = s[3]
            d["dev_uid"] = s[4]
            d["hp_hart_rev"] = int(s[7]) if s[7].isdigit() else None
    elif len(a) == 6:                   # net!AMS1SVR!FF Block 1!<LD>!Link #n!<tag>
        d["ld_name"] = a[3]
        m = re.search(r"(\d+)", a[4])
        d["link_no"] = int(m.group(1)) if m else None
        s = (hp or "").split("/")
        if len(s) == 3:
            d["ld_id"] = s[0]
    return d


def load_prev_alias():
    """GUID -> alias (D0xxxx) from the previous workbook 03_設備總表 (optional; blank if the file is not reachable)."""
    try:
        import openpyxl
        if not os.path.exists(PREV_XLSX):
            return {}
        wb = openpyxl.load_workbook(PREV_XLSX, read_only=True)
        ws = wb["03_設備總表"]
        out = {}
        hdr = None
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 3:
                hdr = list(row)
                ia, ig = hdr.index("設備別名"), hdr.index("AmsDeviceId (GUID)")
                continue
            if i > 3 and hdr is not None:
                g = row[ig]
                if g:
                    out[str(g).upper()] = row[ia]
        wb.close()
        return out
    except Exception:
        return {}


# ----------------------------------------------------------------------------------------------------------------------
# base frames
# ----------------------------------------------------------------------------------------------------------------------
def _type_library(conn):
    sql = """
    SELECT r.AmsDevRevId, t.AmsDevTypeId, m.AmsMfrNameId, mp.MfrProtocolId, p.ProtocolId,
           p.Name AS Protocol, m.Name AS Manufacturer, mp.MfrId, t.DeviceType AS DeviceTypeCode, t.Name AS DeviceTypeName,
           t.Description AS DeviceTypeDesc, r.DeviceRevision, r.Name AS RevName, r.Description AS RevDesc,
           r.DeviceCategoryId, mj.Name AS MajorCategory, mn.Name AS MinorCategory
    FROM DeviceRevisions r
    JOIN DeviceTypes t ON t.AmsDevTypeId = r.AmsDevTypeId
    JOIN MfrProtocols mp ON mp.MfrProtocolId = t.MfrProtocolId
    JOIN Manufacturers m ON m.AmsMfrNameId = mp.AmsMfrNameId
    JOIN DeviceProtocols p ON p.ProtocolId = mp.ProtocolId
    LEFT JOIN DeviceCategories dc ON dc.DeviceCategoryId = r.DeviceCategoryId
    LEFT JOIN MajorDeviceCategories mj ON mj.MajorDeviceCategoryId = dc.MajorDeviceCategoryId
    LEFT JOIN MinorDeviceCategories mn ON mn.MinorDeviceCategoryId = dc.MinorDeviceCategoryId
    """
    return _q(conn, sql)


def _assignments(conn):
    """BlockAsgms (device-level blocks) joined to tags, events, users. One row per assignment."""
    sql = """
    SELECT a.ExtBlockTagKey, a.BlockKey, a.EventIdDayIn, a.EventIdFractionIn, a.EventIdDayOut, a.EventIdFractionOut, a.Archived,
           t.ExtBlockTag, t.ExtBlockTagDesc, t.TestDefinitionId,
           b.DeviceKey, b.BlockIndex,
           ei.EventTime AS InEventTime, ei.Description AS InDesc, ei.Source AS InSource, ui.UserName AS InUser,
           eo.EventTime AS OutEventTime, eo.Description AS OutDesc, eo.Source AS OutSource, uo.UserName AS OutUser
    FROM BlockAsgms a
    JOIN ExtBlockTags t ON t.ExtBlockTagKey = a.ExtBlockTagKey
    JOIN Blocks b ON b.BlockKey = a.BlockKey
    LEFT JOIN EventLog ei ON ei.EventIdDay = a.EventIdDayIn AND ei.EventIdFraction = a.EventIdFractionIn
    LEFT JOIN Users ui ON ui.UserKey = ei.UserKey
    LEFT JOIN EventLog eo ON eo.EventIdDay = a.EventIdDayOut AND eo.EventIdFraction = a.EventIdFractionOut AND a.EventIdDayOut <> 49710
    LEFT JOIN Users uo ON uo.UserKey = eo.UserKey
    """
    df = _q(conn, sql)
    df["in_utc"] = ole_to_utc(df["EventIdDayIn"], df["EventIdFractionIn"])
    df["out_utc"] = ole_to_utc(df["EventIdDayOut"], df["EventIdFractionOut"])
    df["is_open"] = df["EventIdDayOut"] == OPEN_DAY
    return df


# ----------------------------------------------------------------------------------------------------------------------
# sheet 1: 設備總表
# ----------------------------------------------------------------------------------------------------------------------
def sheet_devices(conn, lib, asg, alias_map):
    dev = _q(conn, """
        SELECT d.DeviceKey, d.AmsDevRevId, d.AmsDeviceId, d.Identifier, d.ProtocolRevision, d.DispositionId, d.AmsDeviceTag,
               ds.Name AS Disposition, ds.Description AS DispositionDesc,
               b.BlockKey,
               l.PlantServerKey, l.NetworkInfoKey, l.AmsPath, l.HostPath, l.HostTag, l.IdentStatus, l.SisStatus, l.LatencyFactor,
               n.NetworkId, n.NetworkName, n.NetworkKindAsString,
               ps.PlantServerId,
               c.DevLastCalibrationDay, c.DevLastCalibrationFraction, c.DevNextCalibrationDueDay, c.DevNextCalibrationDueFraction,
               c.DevPassedLastCalibration,
               da.AssetId
        FROM Devices d
        LEFT JOIN Dispositions ds ON ds.DispositionId = d.DispositionId
        LEFT JOIN Blocks b ON b.DeviceKey = d.DeviceKey AND b.BlockIndex = 0
        LEFT JOIN DeviceLocation l ON l.BlockKey = b.BlockKey
        LEFT JOIN NetworkInfo n ON n.NetworkInfoKey = l.NetworkInfoKey
        LEFT JOIN PlantServer ps ON ps.PlantServerKey = l.PlantServerKey
        LEFT JOIN CalStatus c ON c.DeviceKey = d.DeviceKey
        LEFT JOIN DeviceAssets da ON da.DeviceKey = d.DeviceKey
        WHERE d.DeviceKey >= 0
    """)
    dev = dev.merge(lib.drop(columns=["AmsDevTypeId", "AmsMfrNameId", "MfrProtocolId", "ProtocolId", "DeviceCategoryId"]),
                    on="AmsDevRevId", how="left")

    # current tag + assignment stats
    cur = asg[asg["is_open"]][["BlockKey", "ExtBlockTag", "ExtBlockTagKey", "in_utc", "InDesc", "InUser"]].rename(
        columns={"ExtBlockTag": "CurrentTag", "in_utc": "cur_in_utc"})
    dev = dev.merge(cur, on="BlockKey", how="left")
    hist = asg.groupby("BlockKey").agg(n_asg=("ExtBlockTagKey", "size"),
                                       first_in=("in_utc", "min")).reset_index()
    dev = dev.merge(hist, on="BlockKey", how="left")
    prev = (asg[~asg["is_open"]].sort_values("out_utc").groupby("BlockKey").last()[["ExtBlockTag"]]
            .rename(columns={"ExtBlockTag": "PrevTag"}).reset_index())
    dev = dev.merge(prev, on="BlockKey", how="left")

    # FF block counts
    blk = _q(conn, "SELECT DeviceKey, BlockType, COUNT(*) n FROM Blocks WHERE BlockIndex > 0 GROUP BY DeviceKey, BlockType")
    piv = blk.pivot_table(index="DeviceKey", columns="BlockType", values="n", aggfunc="sum", fill_value=0)
    for col in ("R", "T", "F"):
        if col not in piv.columns:
            piv[col] = 0
    piv = piv[["R", "T", "F"]].rename(columns={"R": "n_R", "T": "n_T", "F": "n_F"}).reset_index()
    dev = dev.merge(piv, on="DeviceKey", how="left")
    dev[["n_R", "n_T", "n_F"]] = dev[["n_R", "n_T", "n_F"]].fillna(0).astype(int)

    # path parsing
    parsed = pd.DataFrame([parse_hostpath(a, h) for a, h in zip(dev["AmsPath"], dev["HostPath"])], index=dev.index)
    dev = pd.concat([dev, parsed], axis=1)

    # tags
    dev["CurrentTagClean"] = dev["CurrentTag"].map(clean_tag)
    dev["AmsDeviceTagClean"] = dev["AmsDeviceTag"].map(clean_tag)
    dev["tag_quality"] = dev["CurrentTag"].map(tag_quality)
    dev["devtag_quality"] = dev["AmsDeviceTag"].map(tag_quality)

    def rel(r):
        a, b = r["AmsDeviceTagClean"], r["CurrentTagClean"]
        if a == "" and b == "":
            return "皆空白"
        if a == b:
            return "相同"
        if a and b.startswith(a):
            return "AMS位號=識別位號+後綴 " + b[len(a):]
        if a == "":
            return "識別位號空白(AMS另行命名)"
        return "不同(AMS已改名)"
    dev["tag_relation"] = dev.apply(rel, axis=1)

    kk = pd.DataFrame([kks_parts(t) for t in dev["CurrentTag"]], columns=["kks_unit", "kks_sys", "kks_sysno", "kks_eq", "kks_seq"], index=dev.index)
    dev = pd.concat([dev, kk], axis=1)
    dev["unit_zh"] = dev["kks_unit"].map(UNIT_ZH).fillna("")

    # previous workbook alias
    dev["alias"] = dev["AmsDeviceId"].str.upper().map(alias_map).fillna("")

    # cal status
    dev["last_cal_utc"] = ole_to_utc(dev["DevLastCalibrationDay"], dev["DevLastCalibrationFraction"])
    dev["next_cal_utc"] = ole_to_utc(dev["DevNextCalibrationDueDay"], dev["DevNextCalibrationDueFraction"])

    dev["ident_text"] = dev["IdentStatus"].map({1: "已識別 (identified)", 0: "未知 (unknown：上次掃描未在此路徑再識別到)"}).fillna("未知")
    dev["proto_rev_text"] = dev.apply(lambda r: (f"{r['Protocol']} rev {r['ProtocolRevision']}" if r["Protocol"] == "HART" else str(r["Protocol"])), axis=1)
    dev["node_kind"] = dev.apply(lambda r: "MUX本體 (GE Mark VIe HART I/O)" if r["is_mux"] else ("FF 現場裝置" if r["Protocol"] == "FF" else "HART 現場裝置"), axis=1)

    out = pd.DataFrame({
        "設備鍵 (DeviceKey)": dev["DeviceKey"],
        "舊工作簿別名 (alias@20260910)": dev["alias"],
        "現行AMS位號 (ExtBlockTag)": dev["CurrentTagClean"],
        "現行位號原值 (ExtBlockTag raw)": dev["CurrentTag"],
        "現行位號品質": dev["tag_quality"],
        "識別時裝置位號 (Devices.AmsDeviceTag)": dev["AmsDeviceTagClean"],
        "識別位號品質": dev["devtag_quality"],
        "AMS位號與識別位號關係": dev["tag_relation"],
        "前一個AMS位號 (上一筆已結束指派)": dev["PrevTag"].fillna("").map(clean_tag),
        "位號指派次數 (BlockAsgms)": dev["n_asg"].fillna(0).astype(int),
        "現行位號指派時間(台灣)": to_tw(dev["cur_in_utc"]),
        "現行位號指派事件 (EventLog.Description)": dev["InDesc"].fillna(""),
        "指派者 (Users.UserName)": dev["InUser"].fillna(""),
        "首次識別時間(台灣)": to_tw(dev["first_in"]),
        "機組 (KKS/前綴)": dev["kks_unit"],
        "機組說明": dev["unit_zh"],
        "KKS系統碼": dev["kks_sys"],
        "KKS系統編號": dev["kks_sysno"],
        "KKS設備碼": dev["kks_eq"],
        "KKS流水號": dev["kks_seq"],
        "節點種類": dev["node_kind"],
        "協定 (DeviceProtocols.Name)": dev["Protocol"],
        "協定版本 (Devices.ProtocolRevision)": pd.to_numeric(dev["ProtocolRevision"], errors="coerce"),
        "協定+版本": dev["proto_rev_text"],
        "製造商 (Manufacturers.Name)": dev["Manufacturer"],
        "製造商代碼 (MfrProtocols.MfrId)": dev["MfrId"],
        "型號 (DeviceTypes.Name)": dev["DeviceTypeName"],
        "型號代碼 (DeviceTypes.DeviceType)": dev["DeviceTypeCode"],
        "設備版本 (DeviceRevisions.DeviceRevision)": dev["DeviceRevision"],
        "主類別 (MajorDeviceCategories.Name)": dev["MajorCategory"],
        "次類別 (MinorDeviceCategories.Name)": dev["MinorCategory"],
        "裝置ID (Devices.Identifier；HART=Device ID非銘牌序號)": dev["Identifier"],
        "處置 (Dispositions.Name)": dev["Disposition"],
        "處置說明": dev["DispositionDesc"],
        "網路名稱 (NetworkInfo.NetworkName)": dev["NetworkName"],
        "網路ID (NetworkInfo.NetworkId)": dev["NetworkId"],
        "網路種類 (NetworkKindAsString)": dev["NetworkKindAsString"],
        "MUX位址 (AmsPath第4段)": dev["mux_addr"].astype("Int64"),
        "通道 (AmsPath第5段)": dev["channel"],
        "COM埠號 (HostPath第1段)": dev["com_port"].astype("Int64"),
        "MUX HART UID (HostPath第4段)": dev["mux_uid"],
        "裝置 HART UID (HostPath第5段)": dev["dev_uid"],
        "HostPath第3段碼(未確定)": dev["hp_code"],
        "HART版本 (HostPath第8段)": dev["hp_hart_rev"].astype("Int64"),
        "FF連結設備名稱 (AmsPath第4段)": dev["ld_name"],
        "FF連結設備ID (HostPath第1段)": dev["ld_id"],
        "FF Link編號 (AmsPath第5段)": dev["link_no"].astype("Int64"),
        "主機位號 (DeviceLocation.HostTag)": dev["HostTag"].map(clean_tag),
        "AMS路徑 (DeviceLocation.AmsPath)": dev["AmsPath"],
        "主機路徑 (DeviceLocation.HostPath)": dev["HostPath"],
        "識別狀態碼 (IdentStatus)": dev["IdentStatus"].astype("Int64"),
        "識別狀態": dev["ident_text"],
        "SIS狀態 (SisStatus)": dev["SisStatus"].astype("Int64"),
        "延遲因子 (LatencyFactor)": dev["LatencyFactor"].astype("Int64"),
        "伺服器 (PlantServer.PlantServerId)": dev["PlantServerId"],
        "FF資源區塊數 (Blocks R)": dev["n_R"],
        "FF轉換區塊數 (Blocks T)": dev["n_T"],
        "FF功能區塊數 (Blocks F)": dev["n_F"],
        "上次校正(台灣) (CalStatus)": to_tw(dev["last_cal_utc"]),
        "下次校正到期(台灣) (CalStatus)": to_tw(dev["next_cal_utc"]),
        "上次校正通過 (DevPassedLastCalibration)": yes_no(dev["DevPassedLastCalibration"].fillna(0)),
        "設備GUID (Devices.AmsDeviceId)": dev["AmsDeviceId"].str.upper(),
        "資產GUID (DeviceAssets.AssetId)": dev["AssetId"].fillna("").str.upper(),
        "設備層區塊鍵 (Blocks.BlockKey, BlockIndex=0)": dev["BlockKey"].astype("Int64"),
        "設備版本鍵 (AmsDevRevId)": dev["AmsDevRevId"],
        "網路鍵 (NetworkInfoKey)": dev["NetworkInfoKey"].astype("Int64"),
    })
    out = out.sort_values(["機組 (KKS/前綴)", "現行AMS位號 (ExtBlockTag)", "設備鍵 (DeviceKey)"], kind="stable").reset_index(drop=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# sheet 2: 網路清單
# ----------------------------------------------------------------------------------------------------------------------
def sheet_networks(conn, devices_df):
    ni = _q(conn, """SELECT n.NetworkInfoKey, n.PlantServerKey, ps.PlantServerId, ps.AlertMonitorEnabled, n.NetworkId, n.NetworkName, n.NetworkKindAsString
                     FROM NetworkInfo n LEFT JOIN PlantServer ps ON ps.PlantServerKey = n.PlantServerKey WHERE n.NetworkInfoKey >= 0""")
    prop = _q(conn, "SELECT NetworkInfoKey, NetworkInfoPropertyKey, NetworkInfoPropertyValue FROM NetworkInfoProperty")
    pv = prop.pivot_table(index="NetworkInfoKey", columns="NetworkInfoPropertyKey", values="NetworkInfoPropertyValue", aggfunc="first")
    pv = pv.reset_index()
    ni = ni.merge(pv, on="NetworkInfoKey", how="left")

    d = devices_df
    g = d.groupby("網路鍵 (NetworkInfoKey)").agg(
        n_dev=("設備鍵 (DeviceKey)", "size"),
        n_mux=("節點種類", lambda s: int((s.str.startswith("MUX本體")).sum())),
        n_hart_field=("節點種類", lambda s: int((s == "HART 現場裝置").sum())),
        n_ff=("節點種類", lambda s: int((s == "FF 現場裝置").sum())),
        n_unident=("識別狀態碼 (IdentStatus)", lambda s: int((s == 0).sum())),
        mux_min=("MUX位址 (AmsPath第4段)", "min"), mux_max=("MUX位址 (AmsPath第4段)", "max"),
        units=("機組 (KKS/前綴)", lambda s: ",".join(sorted({x for x in s if x}))),
        n_ld=("FF連結設備名稱 (AmsPath第4段)", lambda s: len({x for x in s if x})),
    ).reset_index().rename(columns={"網路鍵 (NetworkInfoKey)": "NetworkInfoKey"})
    ni = ni.merge(g, on="NetworkInfoKey", how="left")
    for c in ("n_dev", "n_mux", "n_hart_field", "n_ff", "n_unident", "n_ld"):
        ni[c] = ni[c].fillna(0).astype(int)

    def gp(c):
        return ni[c] if c in ni.columns else pd.Series([""] * len(ni), index=ni.index)

    out = pd.DataFrame({
        "網路鍵 (NetworkInfoKey)": ni["NetworkInfoKey"],
        "網路名稱 (NetworkName)": ni["NetworkName"],
        "網路ID (NetworkId)": ni["NetworkId"],
        "網路種類 (NetworkKindAsString)": ni["NetworkKindAsString"],
        "伺服器 (PlantServerId)": ni["PlantServerId"],
        "警報監視啟用 (AlertMonitorEnabled)": yes_no(ni["AlertMonitorEnabled"].fillna(0)),
        "設備數 (DeviceLocation)": ni["n_dev"],
        "MUX本體數 (GE I/O模組)": ni["n_mux"],
        "HART現場裝置數": ni["n_hart_field"],
        "FF現場裝置數": ni["n_ff"],
        "FF連結設備數 (LD)": ni["n_ld"],
        "未識別設備數 (IdentStatus=0)": ni["n_unident"],
        "MUX位址範圍": ni.apply(lambda r: (f"{int(r['mux_min'])}-{int(r['mux_max'])}" if pd.notna(r["mux_min"]) else ""), axis=1),
        "涉及機組": ni["units"].fillna(""),
        "序列埠 (Port)": gp("Port"),
        "鮑率 (Baud)": pd.to_numeric(gp("Baud"), errors="coerce").astype("Int64"),
        "MUX掃描起 (SCAN_RANGE_START)": pd.to_numeric(gp("SCAN_RANGE_START"), errors="coerce").astype("Int64"),
        "MUX掃描迄 (SCAN_RANGE_STOP)": pd.to_numeric(gp("SCAN_RANGE_STOP"), errors="coerce").astype("Int64"),
        "HART逾時ms (HART_TIMEOUT)": pd.to_numeric(gp("HART_TIMEOUT"), errors="coerce").astype("Int64"),
        "HART重試 (HART_RETRIES)": pd.to_numeric(gp("HART_RETRIES"), errors="coerce").astype("Int64"),
        "HART忙碌重試 (HART_BUSY_RETRIES)": pd.to_numeric(gp("HART_BUSY_RETRIES"), errors="coerce").astype("Int64"),
        "重試 (Retries)": pd.to_numeric(gp("Retries"), errors="coerce").astype("Int64"),
        "多點低位址 (Multi drop low address)": gp("Multi drop low address"),
        "多點高位址 (Multi drop high address)": gp("Multi drop high address"),
        "網路搜尋器類型 (Network Searcher Type)": gp("Network Searcher Type"),
        "網路類型碼 (Network Type)": gp("Network Type"),
        "設定檔ID (Config file Id)": gp("Config file Id"),
        "持久化檔 (Persist File)": gp("Persist File"),
        "通訊元件 (ProgIdCommNetSpecific)": gp("ProgIdCommNetSpecific"),
        "階層元件 (ProgIdHierNetSpecific)": gp("ProgIdHierNetSpecific"),
        "UI元件 (ProgIdUserInterface)": gp("ProgIdUserInterface"),
        "HSE IP (HSE_TCPIPADDRESS)": gp("HSE_TCPIPADDRESS"),
        "FF警報多播IP (FFAlertMulticastIP)": gp("FFAlertMulticastIP"),
        "FF警報埠 (FFAlertPort)": gp("FFAlertPort"),
        "FF警報處理 (FFAlertProcessingEnabled)": gp("FFAlertProcessingEnabled"),
        "自動探索 (AutomaticDiscoveryEnabled)": gp("AutomaticDiscoveryEnabled"),
        "無通訊輪詢間隔ms (NoCommPollingInterval)": gp("NoCommPollingInterval"),
        "模擬 (Simulated)": gp("Simulated"),
        "序列化 (Serialize)": gp("Serialize"),
        "清除組態變更旗標 (Clear Config Change Flag)": gp("Clear Config Change Flag"),
        "協定類型 (Protocol Type)": gp("Protocol Type"),
        "設備家族 (Device Family)": gp("Device Family"),
    })
    out = out.fillna({c: "" for c in out.columns if out[c].dtype == object})
    out = out.sort_values("網路鍵 (NetworkInfoKey)").reset_index(drop=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# sheet 3: MUX 多工器清單 (one row per GE Mark VIe HART I/O module)
# ----------------------------------------------------------------------------------------------------------------------
def sheet_muxes(devices_df):
    d = devices_df
    mux = d[d["節點種類"].str.startswith("MUX本體")].copy()
    field = d[(d["協定 (DeviceProtocols.Name)"] == "HART") & (~d["節點種類"].str.startswith("MUX本體"))]
    key = ["網路鍵 (NetworkInfoKey)", "MUX位址 (AmsPath第4段)"]
    fg = field.groupby(key).agg(
        n_ch=("設備鍵 (DeviceKey)", "size"),
        n_unident=("識別狀態碼 (IdentStatus)", lambda s: int((s == 0).sum())),
        ch_list=("通道 (AmsPath第5段)", lambda s: ",".join(sorted({x for x in s if x}, key=lambda v: int(v) if v.isdigit() else 999))),
        tags=("現行AMS位號 (ExtBlockTag)", lambda s: "; ".join(sorted(x for x in s if x))),
        models=("型號 (DeviceTypes.Name)", lambda s: "; ".join(f"{k}×{v}" for k, v in s.value_counts().items())),
        units=("機組 (KKS/前綴)", lambda s: ",".join(sorted({x for x in s if x}))),
    ).reset_index()
    mux = mux.merge(fg, on=key, how="left")
    mux["n_ch"] = mux["n_ch"].fillna(0).astype(int)
    mux["n_unident"] = mux["n_unident"].fillna(0).astype(int)
    out = pd.DataFrame({
        "網路名稱 (NetworkName)": mux["網路名稱 (NetworkInfo.NetworkName)"],
        "COM埠號": mux["COM埠號 (HostPath第1段)"],
        "MUX位址": mux["MUX位址 (AmsPath第4段)"],
        "MUX AMS位號 (ExtBlockTag)": mux["現行AMS位號 (ExtBlockTag)"],
        "MUX識別位號 (AmsDeviceTag)": mux["識別時裝置位號 (Devices.AmsDeviceTag)"],
        "位號後綴 (機架/槽位推測)": mux.apply(lambda r: r["現行AMS位號 (ExtBlockTag)"][len(r["識別時裝置位號 (Devices.AmsDeviceTag)"]):] if r["現行AMS位號 (ExtBlockTag)"].startswith(r["識別時裝置位號 (Devices.AmsDeviceTag)"]) and r["識別時裝置位號 (Devices.AmsDeviceTag)"] else "", axis=1),
        "MUX型號 (DeviceTypes.Name)": mux["型號 (DeviceTypes.Name)"],
        "MUX設備版本": mux["設備版本 (DeviceRevisions.DeviceRevision)"],
        "MUX HART版本": mux["協定版本 (Devices.ProtocolRevision)"],
        "MUX HART UID": mux["MUX HART UID (HostPath第4段)"],
        "MUX HART裝置ID (Identifier)": mux["裝置ID (Devices.Identifier；HART=Device ID非銘牌序號)"],
        "MUX識別狀態": mux["識別狀態"],
        "掛載現場裝置數": mux["n_ch"],
        "其中未識別數": mux["n_unident"],
        "使用通道": mux["ch_list"].fillna(""),
        "涉及機組": mux["units"].fillna(""),
        "掛載型號統計": mux["models"].fillna(""),
        "掛載位號清單": mux["tags"].fillna(""),
        "MUX設備鍵 (DeviceKey)": mux["設備鍵 (DeviceKey)"],
        "MUX AMS路徑": mux["AMS路徑 (DeviceLocation.AmsPath)"],
    })
    out = out.sort_values(["網路名稱 (NetworkName)", "MUX位址"]).reset_index(drop=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# sheet 4: 位號指派歷程
# ----------------------------------------------------------------------------------------------------------------------
def sheet_assignments(asg, devices_df):
    d = devices_df[["設備鍵 (DeviceKey)", "現行AMS位號 (ExtBlockTag)", "型號 (DeviceTypes.Name)", "製造商 (Manufacturers.Name)",
                    "網路名稱 (NetworkInfo.NetworkName)", "裝置ID (Devices.Identifier；HART=Device ID非銘牌序號)", "舊工作簿別名 (alias@20260910)"]].rename(
        columns={"設備鍵 (DeviceKey)": "DeviceKey"})
    a = asg.merge(d, on="DeviceKey", how="left")
    a["dur_days"] = ((a["out_utc"].fillna(pd.Timestamp("2026-09-12 00:00:00")) - a["in_utc"]).dt.total_seconds() / 86400.0).round(2)
    n_per_tag = a.groupby("ExtBlockTagKey")["BlockKey"].transform("size")
    n_per_dev = a.groupby("BlockKey")["ExtBlockTagKey"].transform("size")
    out = pd.DataFrame({
        "位號 (ExtBlockTag)": a["ExtBlockTag"].map(clean_tag),
        "位號原值": a["ExtBlockTag"],
        "狀態": a["is_open"].map({True: "現行", False: "已結束"}),
        "設備鍵 (DeviceKey)": a["DeviceKey"],
        "舊工作簿別名": a["舊工作簿別名 (alias@20260910)"].fillna(""),
        "該設備現行位號": a["現行AMS位號 (ExtBlockTag)"].fillna(""),
        "製造商": a["製造商 (Manufacturers.Name)"].fillna(""),
        "型號": a["型號 (DeviceTypes.Name)"].fillna(""),
        "裝置ID (Identifier)": a["裝置ID (Devices.Identifier；HART=Device ID非銘牌序號)"].fillna(""),
        "網路": a["網路名稱 (NetworkInfo.NetworkName)"].fillna(""),
        "指派開始(台灣)": to_tw(a["in_utc"]),
        "指派開始 UTC (EventIdDayIn/FractionIn)": utc_text(a["in_utc"]),
        "指派結束(台灣)": to_tw(a["out_utc"]),
        "指派結束 UTC (EventIdDayOut/FractionOut)": utc_text(a["out_utc"]),
        "持續天數 (現行者以2026-09-12計)": a["dur_days"],
        "開始事件 (EventLog.Description)": a["InDesc"].fillna(""),
        "開始事件來源 (Source)": a["InSource"].fillna(""),
        "開始事件使用者": a["InUser"].fillna(""),
        "結束事件 (EventLog.Description)": a["OutDesc"].fillna(""),
        "結束事件使用者": a["OutUser"].fillna(""),
        "此位號被指派過的次數": n_per_tag,
        "此設備被指派過的位號數": n_per_dev,
        "位號鍵 (ExtBlockTagKey)": a["ExtBlockTagKey"],
        "區塊鍵 (BlockKey)": a["BlockKey"],
        "已封存 (Archived)": yes_no(a["Archived"].fillna(0)),
        "EventIdDayIn": a["EventIdDayIn"], "EventIdFractionIn": a["EventIdFractionIn"],
        "EventIdDayOut": a["EventIdDayOut"], "EventIdFractionOut": a["EventIdFractionOut"],
    })
    out = out.sort_values(["設備鍵 (DeviceKey)", "指派開始(台灣)"]).reset_index(drop=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# sheet 5: 未指派/歷史位號 (ExtBlockTags rows that are not currently assigned)
# ----------------------------------------------------------------------------------------------------------------------
def sheet_tag_pool(conn, asg, devices_df):
    tags = _q(conn, "SELECT ExtBlockTagKey, ExtBlockTag, ExtBlockTagDesc, TestDefinitionId FROM ExtBlockTags WHERE ExtBlockTagKey >= 0")
    cur = set(asg.loc[asg["is_open"], "ExtBlockTagKey"])
    ever = asg.groupby("ExtBlockTagKey").agg(n=("BlockKey", "size"), last_out=("out_utc", "max"), last_dev=("DeviceKey", "last")).reset_index()
    tags = tags.merge(ever, on="ExtBlockTagKey", how="left")
    tags["state"] = tags.apply(lambda r: "現行使用中" if r["ExtBlockTagKey"] in cur else ("曾指派、已釋放" if pd.notna(r["n"]) else "從未指派(孤立位號)"), axis=1)
    tags = tags[tags["state"] != "現行使用中"].copy()
    dmap = devices_df.set_index("設備鍵 (DeviceKey)")["現行AMS位號 (ExtBlockTag)"]
    out = pd.DataFrame({
        "位號 (ExtBlockTag)": tags["ExtBlockTag"].map(clean_tag),
        "位號原值": tags["ExtBlockTag"],
        "狀態": tags["state"],
        "曾指派次數": tags["n"].fillna(0).astype(int),
        "最後釋放時間(台灣)": to_tw(tags["last_out"]),
        "最後掛載設備鍵": tags["last_dev"].astype("Int64"),
        "該設備現行位號": tags["last_dev"].map(dmap).fillna(""),
        "位號說明 (ExtBlockTagDesc)": tags["ExtBlockTagDesc"].fillna(""),
        "測試定義 (TestDefinitionId)": tags["TestDefinitionId"],
        "位號鍵 (ExtBlockTagKey)": tags["ExtBlockTagKey"],
    })
    out = out.sort_values(["狀態", "位號 (ExtBlockTag)"]).reset_index(drop=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# sheet 6: FF 區塊清單
# ----------------------------------------------------------------------------------------------------------------------
def sheet_ff_blocks(conn, devices_df):
    b = _q(conn, "SELECT BlockKey, DeviceKey, BlockIndex, BlockType, DispositionId FROM Blocks WHERE BlockIndex > 0")
    d = devices_df[["設備鍵 (DeviceKey)", "現行AMS位號 (ExtBlockTag)", "舊工作簿別名 (alias@20260910)", "製造商 (Manufacturers.Name)",
                    "型號 (DeviceTypes.Name)", "設備版本 (DeviceRevisions.DeviceRevision)", "FF連結設備名稱 (AmsPath第4段)",
                    "FF Link編號 (AmsPath第5段)", "機組 (KKS/前綴)"]].rename(columns={"設備鍵 (DeviceKey)": "DeviceKey"})
    b = b.merge(d, on="DeviceKey", how="left")
    name_map = {"R": "RESOURCE", "T": "TRANSDUCER", "F": "FUNCTION"}
    b["blockname"] = b.apply(lambda r: name_map.get(r["BlockType"], r["BlockType"]) + ("" if r["BlockType"] == "R" else str(r["BlockIndex"])), axis=1)
    b["blocktype_zh"] = b["BlockType"].map({"R": "資源區塊", "T": "轉換區塊", "F": "功能區塊"}).fillna(b["BlockType"])
    disp = _q(conn, "SELECT DispositionId, Name FROM Dispositions").set_index("DispositionId")["Name"]
    out = pd.DataFrame({
        "設備位號 (現行 ExtBlockTag)": b["現行AMS位號 (ExtBlockTag)"],
        "舊工作簿別名": b["舊工作簿別名 (alias@20260910)"].fillna(""),
        "機組": b["機組 (KKS/前綴)"].fillna(""),
        "區塊名稱 (AmsUdf_GetFFBlockName)": b["blockname"],
        "區塊類型 (BlockType)": b["BlockType"],
        "區塊類型說明": b["blocktype_zh"],
        "區塊索引 (BlockIndex)": b["BlockIndex"],
        "製造商": b["製造商 (Manufacturers.Name)"],
        "型號": b["型號 (DeviceTypes.Name)"],
        "設備版本": b["設備版本 (DeviceRevisions.DeviceRevision)"],
        "FF連結設備": b["FF連結設備名稱 (AmsPath第4段)"].fillna(""),
        "FF Link編號": b["FF Link編號 (AmsPath第5段)"],
        "區塊處置 (Blocks.DispositionId)": b["DispositionId"].map(disp).fillna(b["DispositionId"].astype(str)),
        "區塊鍵 (BlockKey)": b["BlockKey"],
        "設備鍵 (DeviceKey)": b["DeviceKey"],
    })
    out = out.sort_values(["設備位號 (現行 ExtBlockTag)", "區塊索引 (BlockIndex)"]).reset_index(drop=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# sheet 7: DD 型號庫
# ----------------------------------------------------------------------------------------------------------------------
def sheet_dd_library(conn, lib):
    cnt = _q(conn, "SELECT AmsDevRevId, COUNT(*) n FROM Devices WHERE DeviceKey >= 0 GROUP BY AmsDevRevId")
    ext = _q(conn, "SELECT AmsDevRevId, ExtPropertyName, ExtPropertyValue FROM DevRevExtProperty")
    extp = ext.pivot_table(index="AmsDevRevId", columns="ExtPropertyName", values="ExtPropertyValue", aggfunc="first").reset_index()
    ncfg = _q(conn, "SELECT AmsDevRevId, COUNT(*) n_cfg, MIN(UniversalId) uid FROM NamedConfigs WHERE ConfigKey >= 0 GROUP BY AmsDevRevId")
    lib = lib.merge(cnt, on="AmsDevRevId", how="left").merge(extp, on="AmsDevRevId", how="left").merge(ncfg, on="AmsDevRevId", how="left")
    lib["n"] = lib["n"].fillna(0).astype(int)
    lib["n_cfg"] = lib["n_cfg"].fillna(0).astype(int)
    type_used = lib.groupby("AmsDevTypeId")["n"].transform("sum")
    out = pd.DataFrame({
        "使用中設備數 (Devices)": lib["n"],
        "同型號各版本合計設備數": type_used,
        "協定 (DeviceProtocols.Name)": lib["Protocol"],
        "製造商 (Manufacturers.Name)": lib["Manufacturer"],
        "製造商代碼 (MfrProtocols.MfrId)": lib["MfrId"],
        "型號 (DeviceTypes.Name)": lib["DeviceTypeName"],
        "型號代碼 (DeviceTypes.DeviceType)": lib["DeviceTypeCode"],
        "型號說明 (DeviceTypes.Description)": lib["DeviceTypeDesc"],
        "設備版本 (DeviceRevisions.DeviceRevision)": lib["DeviceRevision"],
        "版本名稱 (DeviceRevisions.Name)": lib["RevName"],
        "版本說明 (DeviceRevisions.Description)": lib["RevDesc"],
        "主類別 (MajorDeviceCategories.Name)": lib["MajorCategory"],
        "次類別 (MinorDeviceCategories.Name)": lib["MinorCategory"],
        "類別鍵 (DeviceCategoryId)": lib["DeviceCategoryId"],
        "GSD識別 (DevRevExtProperty.GsdId)": lib["GsdId"] if "GsdId" in lib.columns else "",
        "已存範本數 (NamedConfigs)": lib["n_cfg"],
        "範本通用版本 (NamedConfigs.UniversalId)": lib["uid"].astype("Int64"),
        "設備版本鍵 (AmsDevRevId)": lib["AmsDevRevId"],
        "型號鍵 (AmsDevTypeId)": lib["AmsDevTypeId"],
        "製造商鍵 (AmsMfrNameId)": lib["AmsMfrNameId"],
    })
    out = out.sort_values(["使用中設備數 (Devices)", "製造商 (Manufacturers.Name)", "型號 (DeviceTypes.Name)", "設備版本 (DeviceRevisions.DeviceRevision)"],
                          ascending=[False, True, True, True]).reset_index(drop=True)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# sheet 8: 摘要
# ----------------------------------------------------------------------------------------------------------------------
def sheet_summary(conn, devices_df, asg, nets, muxes, tagpool, ffb, lib_df):
    d = devices_df
    rows = []

    def add(section, item, value, note=""):
        rows.append({"分類": section, "項目": item, "數值": value, "說明": note})

    tc = _q(conn, "SELECT table_name, row_count FROM _tables").set_index("table_name")["row_count"]
    for t in DOMAIN_TABLES:
        add("資料表列數", t, int(tc.get(t, 0)), "含 -1 哨兵列" if t in ("Devices", "Blocks", "CalStatus", "ExtBlockTags", "NetworkInfo", "PlantServer", "DeviceRevisions", "DeviceTypes", "Manufacturers", "MfrProtocols") else "")
    add("設備", "設備總數 (DeviceKey>=0)", len(d))
    for k, v in d["協定 (DeviceProtocols.Name)"].value_counts().items():
        add("設備", f"協定 {k}", int(v))
    for k, v in d["節點種類"].value_counts().items():
        add("設備", f"節點種類 {k}", int(v))
    for k, v in d["協定+版本"].value_counts().items():
        add("設備", f"協定版本 {k}", int(v))
    for k, v in d["識別狀態"].value_counts().items():
        add("設備", f"識別狀態 {k}", int(v))
    for k, v in d["處置 (Dispositions.Name)"].value_counts().items():
        add("設備", f"處置 {k}", int(v))
    for k, v in d["機組 (KKS/前綴)"].replace("", "(無法判定)").value_counts().items():
        add("設備", f"機組 {k}", int(v))
    add("設備", "KKS 五段可完整解析之位號數", int((d["KKS流水號"] != "").sum()))
    for k, v in d["現行位號品質"].value_counts().items():
        add("位號", f"現行AMS位號品質 {k}", int(v))
    for k, v in d["識別位號品質"].value_counts().items():
        add("位號", f"識別位號(AmsDeviceTag)品質 {k}", int(v))
    for k, v in d["AMS位號與識別位號關係"].str.replace(r"後綴 .*", "後綴", regex=True).value_counts().items():
        add("位號", f"AMS位號與識別位號關係 {k}", int(v))
    add("位號", "位號指派紀錄總數 (BlockAsgms)", len(asg))
    add("位號", "現行指派 (EventIdDayOut=49710)", int(asg["is_open"].sum()))
    add("位號", "已結束指派", int((~asg["is_open"]).sum()))
    add("位號", "被指派過 >1 次的設備數", int((asg.groupby("BlockKey").size() > 1).sum()))
    add("位號", "ExtBlockTags 位號總數 (key>=0)", int(tc.get("ExtBlockTags", 0)) - 1)
    for k, v in tagpool["狀態"].value_counts().items():
        add("位號", f"非現行位號 {k}", int(v))
    add("位號", "最早指派時間(台灣)", str(to_tw(asg["in_utc"]).min()))
    add("位號", "最晚指派時間(台灣)", str(to_tw(asg["in_utc"]).max()))
    add("網路", "網路數 (NetworkInfo, key>=0)", len(nets))
    add("網路", "MUX 網路數", int((nets["網路種類 (NetworkKindAsString)"] == "Mux Network").sum()))
    add("網路", "FF HSE 網路數", int((nets["網路種類 (NetworkKindAsString)"] == "FF HSE Network").sum()))
    add("網路", "MUX 本體數 (GE Mark VIe HART I/O)", len(muxes))
    add("網路", "FF 連結設備數 (LD)", int(nets["FF連結設備數 (LD)"].sum()))
    add("FF區塊", "FF 區塊總數 (BlockIndex>0)", len(ffb))
    for k, v in ffb["區塊類型說明"].value_counts().items():
        add("FF區塊", f"{k}", int(v))
    add("DD型號庫", "設備版本(DD)總數", len(lib_df))
    add("DD型號庫", "有設備使用的設備版本數", int((lib_df["使用中設備數 (Devices)"] > 0).sum()))
    add("DD型號庫", "有設備使用的製造商數", int(lib_df.loc[lib_df["使用中設備數 (Devices)"] > 0, "製造商 (Manufacturers.Name)"].nunique()))
    add("校正", "CalStatus 有上次校正日期的設備", int(d["上次校正(台灣) (CalStatus)"].notna().sum()), "全為 0 → 校正管理功能未使用")
    add("交叉比對", "舊工作簿(20260910) GUID 對上的設備數", int((d["舊工作簿別名 (alias@20260910)"] != "").sum()), "以 Devices.AmsDeviceId 比對 03_設備總表 AmsDeviceId")
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------------------------------
def build(conn):
    lib = _type_library(conn)
    asg = _assignments(conn)
    alias_map = load_prev_alias()

    devices = sheet_devices(conn, lib, asg, alias_map)
    nets = sheet_networks(conn, devices)
    muxes = sheet_muxes(devices)
    asg_sheet = sheet_assignments(asg, devices)
    tagpool = sheet_tag_pool(conn, asg, devices)
    ffb = sheet_ff_blocks(conn, devices)
    ddlib = sheet_dd_library(conn, lib)
    summary = sheet_summary(conn, devices, asg, nets, muxes, tagpool, ffb, ddlib)

    common_notes = [
        "時間欄位 '(台灣)' = 資料庫 UTC 時間 +8 小時；EventIdDay/EventIdFraction 依 AmsUdf_EventIdDayFractionToDateTime 解碼：UTC = 1899-12-30 + Day + Fraction/2^31 天。",
        "-1 鍵值為 AMS 內建 'do not remove' 哨兵列，已排除。",
    ]
    _dq = devices["識別位號品質"].value_counts()
    _n_devtag_nonprint = int(_dq.get("含非可列印字元", 0))
    _n_devtag_tail = int(_dq.get("含尾端殘碼(填充空白+雜字元)", 0))
    _n_devtag_junk = _n_devtag_nonprint + _n_devtag_tail
    sheets = [
        dict(name="設備領域摘要", purpose="設備/位號/網路領域的關鍵統計與資料表列數", one_row="一個統計項目",
             df=summary, source_tables=DOMAIN_TABLES + ["_tables"],
             notes=common_notes + [
                 "本領域 23 張資料表皆非空（最小為 PlantServer 2 列、Labels 4 列、Hierarchies 8 列、DevRevExtProperty 23 列），故無空表。",
                 "Hierarchies 8 列只是 AMS 內建的樹狀根節點（Site-wide / Unassigned / User Configurations / Manufacturer 等），廠內未建立自訂廠區階層；Labels 只有 Level 1 / Level 2 預設標籤。",
                 "Assets 2,273 列中 1,928 列透過 DeviceAssets 對應到設備（1:1），其餘 345 列為無對應之資產 GUID（Discriminator 皆為 1、Tag 皆空），本域未另製表。",
                 "CalStatus 1,929 列全部為 0（無校正日期、PassedLastCalibration=0），AMS 校正管理功能未使用。",
             ]),
        dict(name="設備總表", purpose="每台設備一列：現行位號、型號、協定、類別、實體位置(網路/MUX/通道)、識別狀態", one_row="一台 AMS 設備（Devices.DeviceKey，含 253 台 GE Mark VIe HART I/O 模組即 MUX 本體）",
             df=devices, source_tables=["Devices", "Blocks", "DeviceLocation", "NetworkInfo", "PlantServer", "BlockAsgms", "ExtBlockTags", "EventLog", "Users", "DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "DeviceCategories", "MajorDeviceCategories", "MinorDeviceCategories", "Dispositions", "CalStatus", "DeviceAssets"],
             notes=common_notes + [
                 "現行AMS位號 = ExtBlockTags JOIN BlockAsgms WHERE EventIdDayOut=49710（AmsVw_CurrentTagBlockAsgms 之定義；49710 為『尚未結束』哨兵日）。每台設備恰有一筆現行指派。",
                 "設備層區塊 = Blocks.BlockIndex=0（AmsVw_DeviceLevelBlockKey）；DeviceLocation 與 BlockAsgms 只掛在設備層區塊。",
                 "AmsPath (HART) = net!<伺服器>!<網路名稱>!<MUX位址>!<通道 或 MUX_DEVICE>；MUX_DEVICE 代表該列即 MUX 本體（GE PHRA/53634 HART I/O 模組）。",
                 "HostPath (HART) 8 段 = COM埠號.MUX位址.第3段碼.MUX HART UID.裝置 HART UID.通道(或MUX_DEVICE).MUX位址(現場裝置為0).HART版本。驗證：第1段=NetworkInfoProperty 'Port' 之 COM 號、第8段=Devices.ProtocolRevision（1,577/1,577 相符）、MUX 本體第4段=第5段（253/253）。",
                 "HostPath 第3段碼未確定：MUX本體=4、一般HART裝置=5、Rosemount 644=6、Honeywell XNX=9；推測與裝置回報之最少前導碼數相關，僅供參考。",
                 "AmsPath (FF) = net!AMS1SVR!FF Block 1!<連結設備LD名稱>!Link #<n>!<位號>；HostPath (FF) = <LD裝置ID>/<Link#>/<位號>。",
                 "識別狀態 IdentStatus：1=identified；0=unknown（AmsUdf_DevBlkIdentStatusAsString）。AmsSp_DevBlk_ReconcileIdentStatus_1 在重新掃描同一 HostPath 卻找不到該設備時將其設為 0，故 0 = 上次掃描未於原路徑再識別到（可能已拆除/斷線/更換）。",
                 "SisStatus 全為 0、LatencyFactor 全為 0（無 SIS 設備標記）；處置 (Dispositions) 全為 Spare、伺服器全為 AMS1SVR（單一 AMS 伺服器、未使用處置管理）。",
                 f"識別時裝置位號 (Devices.AmsDeviceTag) = 建立設備時讀到的 HART 短位號(8字元)/FF 位號；{_n_devtag_junk} 筆含殘碼（非可列印字元 {_n_devtag_nonprint} 筆、尾端『2個以上填充空白+1~2個雜字元』{_n_devtag_tail} 筆，為 HART 長位號讀取殘碼），已另提供清理欄位（去除非可列印字元及尾端填充+雜字元）。AMS 位號 (ExtBlockTag) 才是使用者看到的位號。",
                 "裝置ID (Devices.Identifier)：HART 設備 = HART Device ID（裝置唯一識別碼後 3 bytes 之十進位，等於 HostPath 第5段 HART UID 末 6 個 hex 字元，1,577/1,577 相符），並非銘牌序號（銘牌序號在 HART 參數 FINAL_ASMBLY_NUM/SENSOR_SN 等，見參數領域）；FF 設備 = FF Device ID 字串（製造商碼+型別碼+序號式字串）。",
                 "位號為 'MM/DD/YYYY hh:mm:ss.fff' 者是 AMS 在設備位號空白時自動以伺服器本地時間命名（AmsSp_CreateAmsTagName_1 / AmsSp_GetAdd_AssignDevTag_1）。位號尾綴 _01.._99 是 AMS 遇到重複位號時自動加上（AmsSp_UnassignedTag_Get_1）。",
                 "KKS 解析：^([GSC]\\d{2})([A-Z]{3})(\\d{2})([A-Z]{2})(\\d{3})$ → 機組/系統碼/系統編號/設備碼/流水號（如 G12LAB16QN005）；FF 位號 G11_90LT-1 只取機組 G11。JK… 開頭者為 GE I/O 模組序號式位號，無 KKS。",
                 "舊工作簿別名 = 20260910_AMS解析.xlsx 03_設備總表 之『設備別名』，以 AmsDeviceId GUID 對應（1,928/1,928 全對上）；別名並非 DeviceKey（僅 57 筆巧合相同），為當時匯出順序編號。",
                 "CalStatus 日期全為 0 → 顯示為空。",
             ]),
        dict(name="網路清單", purpose="AMS 通訊網路（18 個 MUX 網路 + 1 個 FF HSE 網路）之設定屬性與掛載設備統計", one_row="一個 NetworkInfo 網路",
             df=nets, source_tables=["NetworkInfo", "NetworkInfoProperty", "PlantServer", "DeviceLocation"],
             notes=common_notes + [
                 "NetworkInfoProperty 以 NetworkInfoPropertyKey 轉置為欄；空欄表示該網路無此屬性（FF HSE 網路無 COM 埠/掃描範圍，MUX 網路無 HSE IP）。",
                 "網路名稱即 GE Mark VIe 控制器/機櫃代號（H11/H12=HRSG11/12、G11S/G12S=燃機、S1=汽機、BOP*、WSC1=水處理、SAMP1=取樣、AGC1）；MUX 掃描迄 (SCAN_RANGE_STOP) = 該 COM 埠上最大 MUX 位址。",
                 "'Network Searcher Type' Mux_PassThrough / HSE_PassThrough 表示 AMS 透過 HART pass-through（Mux Server）與 FF HSE 存取設備，非 DeltaV。",
                 "全網路相同之設定（單一伺服器、統一參數）：伺服器 AMS1SVR、警報監視啟用=是、SCAN_RANGE_START=0、HART_TIMEOUT=1000ms、HART_RETRIES=2、HART_BUSY_RETRIES=5、多點位址 0/0、Network Type=9、Protocol Type=Primary、Device Family=1、Simulated=No、Serialize=Yes、Clear Config Change Flag=Yes；FF HSE 網路獨有：HSE IP 10.0.0.1、FF 警報多播 239.255.0.33:45000、FF 警報處理=No、自動探索=Yes、無通訊輪詢 15000ms。",
             ]),
        dict(name="MUX多工器清單", purpose="每台 GE Mark VIe HART I/O 模組（AMS 視為 MUX）之位置、型號、掛載通道與現場裝置", one_row="一台 MUX 本體（AmsPath 第5段 = MUX_DEVICE）",
             df=muxes, source_tables=["DeviceLocation", "Devices", "DeviceTypes", "NetworkInfo", "ExtBlockTags", "BlockAsgms"],
             notes=common_notes + [
                 "MUX 本體型號 GE 'PHRA'（244 台，HART5）與 GE '53634'（9 台，HART7）。AMS 位號 = HART 序號式短位號 + '-' + 4 碼（如 JK7L0PT-1A3B），後綴推測為機架/槽位標示，非 DB 內定義。",
                 "掛載現場裝置數 = 同網路同 MUX 位址下 AmsPath 第5段為通道號之 HART 設備數。",
                 "MUX HART裝置ID (Identifier) = HART Device ID（非銘牌序號）；MUX 設備版本 (DeviceRevision) 全為 1。",
             ]),
        dict(name="位號指派歷程", purpose="BlockAsgms 每筆位號↔設備指派（含現行與已結束），附開始/結束事件與使用者", one_row="一筆位號指派（ExtBlockTagKey × BlockKey × 開始事件）",
             df=asg_sheet, source_tables=["BlockAsgms", "ExtBlockTags", "Blocks", "Devices", "EventLog", "Users"],
             notes=common_notes + [
                 "狀態 現行 = EventIdDayOut=49710；已結束者其 Out 事件即『Renamed AMS tag A to B』事件，同一事件同時是舊指派的結束與新指派的開始。",
                 "開始事件 'Device identified'（Source=Server, 使用者 PS.AMS1SVR）= AMS 掃描首次識別設備並自動建立位號；'Renamed AMS tag …' = 使用者在 AMS 改名。",
                 "所有 In/Out 事件均能在 EventLog 找到（3,561/3,561、1,633/1,633）；已結束指派之結束事件使用者全為 HMI\\GEAdmin（所有改名皆由此帳號操作）；Archived 全為 否（AMS 未封存任何指派）。",
             ]),
        dict(name="非現行位號池", purpose="ExtBlockTags 中目前未掛在任何設備的位號（曾指派已釋放、或從未指派）", one_row="一個非現行 ExtBlockTag",
             df=tagpool, source_tables=["ExtBlockTags", "BlockAsgms"],
             notes=common_notes + [
                 "ExtBlockTags 是位號字典，改名後舊位號仍保留；'從未指派(孤立位號)' 15 筆多為手動建立後未掛設備或 _old 備份位號。",
                 "ExtBlockTagDesc 全空、TestDefinitionId 全為 -1（未配置校正測試定義）。",
             ]),
        dict(name="FF區塊清單", purpose="FF 設備的資源/轉換/功能區塊（Blocks.BlockIndex>0）", one_row="一個 FF 區塊",
             df=ffb, source_tables=["Blocks", "Devices", "ExtBlockTags", "BlockAsgms", "DeviceLocation"],
             notes=common_notes + [
                 "區塊名稱依 AmsUdf_GetFFBlockName：R→RESOURCE、T→TRANSDUCER<BlockIndex>、F→FUNCTION<BlockIndex>。BlockIndex 為 DD 內區塊索引（如 Rosemount 3051 FF：R=1000、T=1100..1300、F=1400..2400）。",
                 "HART 設備只有 BlockIndex=0 的設備層區塊，不在本表。",
                 "區塊處置 (Blocks.DispositionId) 全為 0=Unknown（Dispositions 表：0 Unknown/1 Assigned/2 Spare/3 Retired/5 Deleted；AMS 未對區塊設定處置）。",
             ]),
        dict(name="DD型號庫", purpose="AMS 已安裝的設備描述庫：製造商×型號×版本，及各版本使用中設備數", one_row="一個 DeviceRevisions 設備版本（DD）",
             df=ddlib, source_tables=["DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers", "DeviceProtocols", "DeviceCategories", "MajorDeviceCategories", "MinorDeviceCategories", "DevRevExtProperty", "NamedConfigs", "Devices"],
             notes=common_notes + [
                 "型號代碼 DeviceTypes.DeviceType = HART 設備型別碼(Device Type Code)/FF 型別碼；製造商代碼 MfrId = HART/FF 製造商 ID（HART 例：38=Rosemount、17=E+H、26=ABB、209=GE）。",
                 "DevRevExtProperty 僅 23 筆 GsdId（PROFIBUS GSD 識別），本廠無 PROFIBUS 設備。",
                 "使用中設備數為 0 的列是 AMS 隨附但本廠未用的 DD。",
             ]),
    ]
    return sheets


if __name__ == "__main__":
    import time
    t0 = time.time()
    conn = sqlite3.connect(DB_PATH)
    sheets = build(conn)
    os.makedirs(OUT_DIR, exist_ok=True)
    for s in sheets:
        df = s["df"]
        print(f"{s['name']}: {len(df)} rows x {df.shape[1]} cols")
        df.to_csv(os.path.join(OUT_DIR, f"{KEY}__{s['name']}.csv"), index=False, encoding="utf-8-sig")
    print(f"done in {time.time() - t0:.1f}s")
