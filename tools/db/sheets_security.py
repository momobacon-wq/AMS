# -*- coding: utf-8 -*-
"""
sheets_security.py  --  AMS Device Manager (AmsDb) 解析：使用者、權限與系統 (domain key: security)

build(conn) -> list[dict]
  每個 dict: name / purpose / one_row / df / notes / source_tables

資料來源：AmsDb.sqlite (SQL Server 2014 備份 20260912.ams_bckup 之完整傾印, 廠 新複循環廠, 伺服器 AMS1SVR)
"""
import re
import struct
import socket
import sqlite3
from pathlib import Path

import os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tools/db/paths.py：repo 外路徑的唯一來源
from paths import AMS_SQLITE as DB_PATH, SHEETS_OUT as OUT_DIR  # noqa: E402
OUT_DIR = Path(OUT_DIR)

KEY = "security"

TW_OFFSET = pd.Timedelta(hours=8)

# ---------------------------------------------------------------------------
# 常數 (來源: _modules AmsSp_CheckUserPermission / AmsSp_HasPermission / AmsVw_UM_PlantLocation)
# ---------------------------------------------------------------------------
GUID_SITE_WIDE = "81C7311F-D829-4CDD-961A-A3E3A25D013F"
GUID_MANUFACTURER = "3CFEC380-CC46-4D45-9A8B-09835D316AA9"
GUID_UC_FOLDER = "5DC4F174-7FF7-43BF-8EA4-A47DD4143C79"
GUID_UNASSIGNED = "10F82026-03C4-4D47-9C9C-26F2F89B3F5D"
GUID_SYS_FOLDER = "87FC0717-33EC-4BA2-8A35-C7A114567A40"
GUID_AMSSERVICEUSER = "3044F0E9-7033-4FB0-8E8A-008D367E3A32"
GUID_NULL_DOMAIN = "F9B49376-6EA5-4AD7-98DB-5A8ABA2ED75C"

SCOPE_ROLE = {
    GUID_SITE_WIDE: "全廠範圍 (SIS/BPCS 類權限的根)",
    GUID_MANUFACTURER: "製造商層 (權限檢查時排除)",
    GUID_UC_FOLDER: "使用者組態資料夾 (Configuration 類權限的根)",
    GUID_UNASSIGNED: "未指派區 (視同 Site-wide 子節點)",
    GUID_SYS_FOLDER: "系統資料夾 (System 類權限的根)",
}

CLASSIFICATION_ZH = {-1: "未知", 0: "SIS 安全儀控", 1: "BPCS 基本製程控制", 2: "系統", 3: "組態"}
SECURITY_TYPE_ZH = {-1: "未知", 0: "系統內建", 1: "使用者自訂"}
STD_STATE_ZH = {0: "有效", 1: "可見 (已退役, AmsVw_UM_RetiredAccount)", 2: "隱藏 (內建服務帳號)"}
WIN_STATUS_ZH = {1: "啟用", 0: "停用"}
BINDING_ZH = {1: "是", 0: "否"}
AREAVIEW_TYPE_ZH = {"U": "U 使用者組態檢視", "M": "M 主要廠區階層檢視"}

PERM_GROUP_ZH = {
    "AMS ValveLink SNAP-ON": "ValveLink 閥門診斷外掛",
    "User Management": "使用者管理",
    "Calibration": "校正管理",
    "User Configuration": "使用者組態",
    "Database Utilities": "資料庫工具",
    "AMS Wireless SNAP-ON": "無線網路外掛",
    "Trex": "Trex 手持器同步",
    "Alert Monitor": "警報監視",
    "Device": "裝置",
    "Network Configuration": "網路組態",
    "System Settings": "系統設定",
}

PERM_NAME_ZH = {
    "Assign Plant Hierarchy Location": "指派廠區階層位置",
    "Read": "讀取",
    "Write": "寫入",
    "Manage Read": "管理-讀取",
    "Manage Write": "管理-寫入",
    "Calibrate Instruments": "校正儀器",
    "Change Instrument Mode": "變更儀器模式",
    "Change Instrument Protection": "變更儀器保護",
    "Configure Instruments": "組態儀器",
    "Edit/Run Scheduler (VL13.1 & up)": "編輯/執行排程器 (VL13.1+)",
    "Online Diagnostics (VL13.1 & up)": "線上診斷 (VL13.1+)",
    "Run Diagnostics": "執行診斷 (會動閥)",
    "Database Restore": "資料庫還原",
    "Import Data": "匯入資料",
    "Launch Purge and Other Utilities": "啟動清除及其他工具",
    "Verify Repair": "驗證/修復",
    "Launch": "啟動",
    "Manage Alert Configurations": "管理警報組態",
    "Manage Wireless Diagrams": "管理無線圖",
    "Management Read": "管理-讀取",
    "Management Write": "管理-寫入",
    "Test Results Read": "測試結果-讀取",
    "Test Results Write": "測試結果-寫入",
    "Acknowledge Alerts": "確認警報",
    "Clear Alerts": "清除警報",
    "Set Device Protection": "設定裝置保護",
    "Manage Connections": "管理連線",
    "Manage Sync Settings": "管理同步設定",
}

EVENT_CAT_ZH = {46: "登入", 47: "登出", 58: "使用者帳號異動", 56: "使用者密碼變更", 57: "新使用者", 7: "使用者狀態"}

# ---------------------------------------------------------------------------
# 資料表說明 (105 表; 依名稱/欄位/_modules 註解整理)
# ---------------------------------------------------------------------------
TABLE_DOC = {
    # 設備主檔
    "Devices": ("設備主檔", "每台裝置一列 (DeviceKey/Tag/DeviceType/Disposition)，主鍵 -1 為保留列"),
    "DeviceAssets": ("設備主檔", "Devices ↔ Assets 的 GUID 對照 (每台裝置的 AssetId)"),
    "Assets": ("設備主檔", "資產 GUID 主檔 (Discriminator 區分裝置/其他資產類型)"),
    "DeviceLocation": ("設備主檔", "裝置所屬 Plant Server / 網路 / 位置資訊"),
    "DeviceRevisions": ("設備主檔", "裝置型號的版本 (Device Revision) 清單"),
    "DeviceTypes": ("設備主檔", "裝置型號主檔 (製造商 + 型號 + 通訊協定)"),
    "DeviceCategories": ("設備主檔", "裝置型號對應之主/次類別"),
    "MajorDeviceCategories": ("設備主檔", "主類別代碼表 (壓力/溫度/閥定位器…)"),
    "MinorDeviceCategories": ("設備主檔", "次類別代碼表"),
    "Manufacturers": ("設備主檔", "製造商代碼表"),
    "MfrProtocols": ("設備主檔", "製造商 × 通訊協定 對照"),
    "DeviceProtocols": ("設備主檔", "通訊協定代碼表 (HART/FF/…)"),
    "Dispositions": ("設備主檔", "裝置處置狀態代碼表 (Spare/Assigned/…)"),
    "DevRevExtProperty": ("設備主檔", "裝置版本的延伸屬性 (鍵/值)"),
    "HostDeviceDefinition": ("設備主檔", "由主控系統 (DCS) 定義的裝置資訊"),
    "HostTagParams": ("設備主檔", "主控系統位號的參數"),
    "CalStatus": ("設備主檔", "每台裝置的校正狀態摘要"),
    # 區塊與參數
    "Blocks": ("區塊與參數", "裝置區塊 (HART 裝置 1 個, FF 裝置含多個功能區塊)"),
    "BlockAsgms": ("區塊與參數", "區塊 ↔ 外部位號 (ExtBlockTag) 指派及其生效/失效時間"),
    "BlockData": ("區塊與參數", "區塊參數值歷史 (每參數每次變更一列, ParamData 為二進位)"),
    "ExtBlockTags": ("區塊與參數", "外部位號 (HostTag) 主檔"),
    "InstantiableBlockAsgms": ("區塊與參數", "可實例化功能區塊指派"),
    "InstantiableConfigBlocks": ("區塊與參數", "可實例化功能區塊組態"),
    "InstantiableConfigData": ("區塊與參數", "可實例化功能區塊組態資料"),
    # 範本與使用者組態
    "NamedConfigs": ("範本與組態", "具名組態 (User Configuration / 範本) 主檔"),
    "NamedConfigBlocks": ("範本與組態", "具名組態內的區塊"),
    "NamedConfigData": ("範本與組態", "具名組態的參數值 (二進位)"),
    "NamedConfigAsgms": ("範本與組態", "具名組態 ↔ 位號 指派紀錄"),
    "NamedConfigAssets": ("範本與組態", "具名組態 ↔ 資產 對照"),
    "Components": ("範本與組態", "元件 (如 NamedConfigs) 所屬的階層區域 (AreaId) 與標籤"),
    # 事件與稽核
    "EventLog": ("事件與稽核", "稽核事件總帳 (時間 UTC, 使用者, 電腦 IP, 區塊, 類別, 說明)"),
    "EventCategories": ("事件與稽核", "事件類別代碼表 (97 種)"),
    "NotifyQ": ("事件與稽核", "通知佇列 (事件/警報插入通知)"),
    # 警報與健康
    "AlertList": ("警報與健康", "目前作用中的警報清單"),
    "AlertList_UpdateTracking": ("警報與健康", "警報清單更新追蹤 (初始化/最後更新時間)"),
    "AlertLog": ("警報與健康", "警報歷史 (對應 EventLog 的 EventId)"),
    "AlertTypes": ("警報與健康", "警報類型代碼表 (FAILED/MAINT/ADVISORY…)"),
    "AlertFilterForDevice": ("警報與健康", "每台裝置的警報過濾啟用設定"),
    "DeviceAlertDesc": ("警報與健康", "裝置警報描述 (每裝置每警報位元一列)"),
    "DeviceAlertReoccurFilter": ("警報與健康", "警報重複發生過濾"),
    "ExtDevAlertDescProp": ("警報與健康", "裝置警報描述的延伸屬性"),
    "ExtDeviceAlertDesc": ("警報與健康", "裝置警報描述延伸表"),
    "DeviceHealth": ("警報與健康", "裝置健康狀態"),
    "DeviceHealthMonitor": ("警報與健康", "裝置健康監視設定"),
    "DeviceHealthSnapshots": ("警報與健康", "裝置健康快照"),
    "DeviceMonitorList": ("警報與健康", "Alert Monitor 監視裝置清單"),
    "ProjectDeviceHealthSnapshots": ("警報與健康", "專案 ↔ 裝置健康快照"),
    "SnapOnData": ("警報與健康", "SNAP-ON 外掛 (ValveLink 等) 儲存的資料"),
    "SnapOnDataOwners": ("警報與健康", "SNAP-ON 資料擁有者"),
    # 校正與測試
    "TestDefinition": ("校正與測試", "校正測試方案 (Test Scheme) 定義"),
    "TestDefinitionHistory": ("校正與測試", "測試方案歷史版本"),
    "TestDefPoints": ("校正與測試", "測試方案的測試點"),
    "TestDefPointsHistory": ("校正與測試", "測試點歷史版本"),
    "TestDefAsgms": ("校正與測試", "測試方案 ↔ 位號 指派"),
    "TestResults": ("校正與測試", "校正測試結果 (技師 TechnicianId → Users)"),
    "TestResultPoints": ("校正與測試", "校正測試結果各點"),
    "TestResultAFAL": ("校正與測試", "校正 As-Found / As-Left 結果"),
    "Routes": ("校正與測試", "校正路線"),
    "RouteFolders": ("校正與測試", "校正路線資料夾"),
    "RouteTags": ("校正與測試", "校正路線內的位號"),
    "ServiceReasons": ("校正與測試", "校正服務原因代碼表 (Routine / Not Given)"),
    # 網路
    "NetworkInfo": ("網路", "AMS 網路 (Mux/HART Modem/FF/Foreign host…) 清單"),
    "NetworkInfoProperty": ("網路", "各網路的屬性鍵/值"),
    "NetworkHierarchies": ("網路", "實體網路階層節點"),
    "NetworkHierarchiesData": ("網路", "實體網路節點資料"),
    "PlantServer": ("網路", "Plant Server 清單 (本廠僅 AMS1SVR)"),
    "StationProperty": ("網路", "工作站屬性 (ALARM PollingFactor)"),
    # 使用者與權限
    "Users": ("使用者與權限", "事件/校正用使用者主檔 (UserKey; UserName = 網域\\帳號)"),
    "Principals": ("使用者與權限", "安全主體 GUID 主檔 (使用者/群組共用)"),
    "Principals_WindowsPrincipal": ("使用者與權限", "Windows 主體的 SID"),
    "Principals_UserWindowsPrincipal": ("使用者與權限", "Windows 使用者 (名稱/網域/啟用狀態/AD 綁定)"),
    "Principals_GroupWindowsPrincipal": ("使用者與權限", "群組 (內建 System Admin / Read-Only / Maintenance / Database Admin)"),
    "Principals_StandardUserPrincipal": ("使用者與權限", "標準 (非 Windows) 使用者，含隱藏服務帳號"),
    "GroupPrincipalWindowsUserPrincipal": ("使用者與權限", "群組 ↔ Windows 使用者 成員關係"),
    "Domains": ("使用者與權限", "Windows 網域/電腦名稱 (HMI, AMS1SVR, NullDomain)"),
    "SecurityType": ("使用者與權限", "主體建立類型代碼表 (System / User-Defined)"),
    "Grants": ("使用者與權限", "授權: 主體 × 權限 × 廠區範圍"),
    "Grants_NetworkLocation": ("使用者與權限", "授權: 主體 × 權限 × 實體網路節點"),
    "Privileges": ("使用者與權限", "權限 GUID 主檔 (單一權限與權限清單共用)"),
    "Privileges_Permission": ("使用者與權限", "單一權限 (名稱/標題/分類/權限群組)"),
    "Privileges_PermissionList": ("使用者與權限", "複合權限清單"),
    "PermissionListPermission": ("使用者與權限", "複合權限清單 ↔ 單一權限"),
    "PermissionGroups": ("使用者與權限", "權限群組 (Device/Calibration/Alert Monitor…)"),
    "PermissionClassification": ("使用者與權限", "權限分類代碼表 (SIS/BPCS/System/Configuration)"),
    "SecurityComponent": ("使用者與權限", "安全元件 (AMS Device Manager)"),
    "DeviceProtection": ("使用者與權限", "裝置保護 (鎖定裝置寫入) 設定"),
    # 廠區階層
    "Hierarchies": ("廠區階層", "廠區階層樹 (Site-wide/Unassigned/System/User Configurations…)"),
    "PlantLocations": ("廠區階層", "廠區位置 GUID 主檔 (授權範圍用)"),
    "PlantLocations_Scope": ("廠區階層", "單一範圍 (對應 Hierarchies.AreaIdentifier)"),
    "PlantLocations_ScopeList": ("廠區階層", "複合範圍清單"),
    "ScopeListScope": ("廠區階層", "複合範圍清單 ↔ 單一範圍"),
    "AreaViews": ("廠區階層", "階層檢視定義 (檢視類型/最大層數/是否平衡)"),
    "AreaLevels": ("廠區階層", "檢視各層級的標籤"),
    "Labels": ("廠區階層", "層級標籤名稱 (Level 1 / Level 2)"),
    # 行動裝置與政策
    "MobileDeviceTypes": ("行動裝置與政策", "行動裝置類型 (Trex Handheld)"),
    "MobileDevices": ("行動裝置與政策", "已登錄的 Trex 手持器"),
    "MobileDeviceEventLog": ("行動裝置與政策", "手持器同步事件 ↔ EventLog"),
    "Policies": ("行動裝置與政策", "政策 (TrexSync)"),
    "PoliciesAsgms": ("行動裝置與政策", "政策 ↔ 行動裝置 指派"),
    "PolicyProperties": ("行動裝置與政策", "政策屬性"),
    "PolicyTypes": ("行動裝置與政策", "政策類型代碼表"),
    # 專案
    "Projects": ("專案與任務", "專案"),
    "AtomicTasks": ("專案與任務", "專案內的原子任務"),
    # 系統
    "__version": ("系統", "資料庫結構版本歷程 (AMS 產品版本沿革)"),
    "SystemDefaults": ("系統", "系統預設值 (警報自動抑制/校正容差/全域裝置保護…)"),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def q(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def to_tw(series):
    """UTC datetime text -> Taiwan datetime (UTC+8)."""
    s = pd.to_datetime(series, errors="coerce")
    return s + TW_OFFSET


def yn(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return "是" if bool(v) else "否"


def ip_from_computer_id(v):
    """EventLog.ComputerId: IPv4 位址以 big-endian 有號 32 位元整數儲存 (2130706433 = 127.0.0.1)。"""
    try:
        if v is None or pd.isna(v):
            return ""
        if int(v) == -1:
            # 哨兵列 (EventLog 'do not remove' 測試列) 的 ComputerId=-1，非 IP (勿解成 255.255.255.255)
            return "(哨兵 -1)"
        return socket.inet_ntoa(struct.pack(">i", int(v)))
    except Exception:
        return str(v)


def perm_zh(name):
    return PERM_NAME_ZH.get(name, name)


# ---------------------------------------------------------------------------
# 基礎資料載入
# ---------------------------------------------------------------------------
def load_base(conn):
    b = {}
    b["domains"] = q(conn, "select Id, Name, Description, Title from Domains")
    dom_name = dict(zip(b["domains"].Id, b["domains"].Name.str.strip()))

    win = q(conn, """select u.Id, u.Name, u.Title, u.Description, u.FullName, u.Status, u.BindingMode,
                            u.LastModified, u.DomainId, w.Sid
                     from Principals_UserWindowsPrincipal u
                     left join Principals_WindowsPrincipal w on w.Id = u.Id""")
    grp = q(conn, """select g.Id, g.Name, g.Title, g.Description, g.BindingMode, g.LastModified, g.CreateType,
                            g.DomainId, w.Sid
                     from Principals_GroupWindowsPrincipal g
                     left join Principals_WindowsPrincipal w on w.Id = g.Id""")
    std = q(conn, "select Id, Name, State from Principals_StandardUserPrincipal")
    users = q(conn, "select UserKey, UserName, UserIdentifier, SSOID from Users")
    members = q(conn, "select Groups_Id, Users_Id from GroupPrincipalWindowsUserPrincipal")

    rows = []
    for r in win.itertuples():
        dom = dom_name.get(r.DomainId, "")
        rows.append(dict(PrincipalId=r.Id, 主體類型="Windows 使用者", 名稱=r.Name, 網域=dom,
                         登入名稱=f"{dom}\\{r.Name}" if dom else r.Name,
                         狀態碼=r.Status, 狀態=WIN_STATUS_ZH.get(r.Status, str(r.Status)),
                         啟用=yn(r.Status == 1), 綁定AD=BINDING_ZH.get(r.BindingMode, str(r.BindingMode)),
                         建立類型="", 職稱=r.Title or "", 全名=r.FullName or "", 說明=r.Description or "",
                         SID=r.Sid if r.Sid else "", 最後修改_AD=r.LastModified))
    for r in grp.itertuples():
        dom = dom_name.get(r.DomainId, "")
        rows.append(dict(PrincipalId=r.Id, 主體類型="群組", 名稱=r.Name, 網域=dom,
                         登入名稱="", 狀態碼=None, 狀態="", 啟用="",
                         綁定AD=BINDING_ZH.get(r.BindingMode, str(r.BindingMode)),
                         建立類型=SECURITY_TYPE_ZH.get(r.CreateType, str(r.CreateType)),
                         職稱=r.Title or "", 全名="", 說明=r.Description or "",
                         SID=r.Sid if r.Sid else "", 最後修改_AD=r.LastModified))
    for r in std.itertuples():
        rows.append(dict(PrincipalId=r.Id, 主體類型="標準使用者 (AMS 內部)", 名稱=r.Name, 網域="",
                         登入名稱=r.Name, 狀態碼=r.State, 狀態=STD_STATE_ZH.get(r.State, str(r.State)),
                         啟用=yn(r.State == 0), 綁定AD="", 建立類型="", 職稱="", 全名="", 說明="",
                         SID="", 最後修改_AD=None))
    pr = pd.DataFrame(rows)
    # 成員關係 (本庫為空表, 仍實作)
    grp_name = dict(zip(grp.Id, grp.Name))
    mem = members.groupby("Users_Id")["Groups_Id"].apply(lambda s: "; ".join(grp_name.get(g, g) for g in s))
    pr["所屬群組"] = pr.PrincipalId.map(mem).fillna("")
    # Users 對照 (Windows 使用者以 網域\帳號 對應, 標準使用者以名稱對應; 不分大小寫)
    users["_key"] = users.UserName.str.lower()
    pr["_key"] = pr.登入名稱.str.lower()
    pr = pr.merge(users[["UserKey", "UserName", "_key"]], on="_key", how="left")
    b.update(dict(win=win, grp=grp, std=std, users=users, principals=pr, dom_name=dom_name))
    return b


def load_hierarchy(conn):
    h = q(conn, "select AreaId, ParentAreaId, ViewAreaId, AreaLevel, AreaName, LabelId, AreaIdentifier from Hierarchies")
    name = dict(zip(h.AreaId, h.AreaName))
    parent = dict(zip(h.AreaId, h.ParentAreaId))

    def path(aid):
        parts = []
        cur = aid
        seen = set()
        while cur in name and cur not in seen:
            seen.add(cur)
            parts.append(name[cur])
            p = parent.get(cur)
            # ParentAreaId 0 → 視為 Site-wide 之下 (AmsVw_UM_PlantLocation / AmsVw_EF_Location)
            if p == 0:
                parts.append(name.get(-1, "Site-wide"))
                break
            cur = p
        return "~/" + "/".join(reversed(parts))

    h["路徑"] = h.AreaId.map(path)
    return h


# ---------------------------------------------------------------------------
# 事件 (登入 / 登出 / 帳號異動)
# ---------------------------------------------------------------------------
RE_LOGIN_OK = re.compile(r"^Successful login of user: (.+?) to AMS Device Manager\.?$")
RE_LOGIN_FAIL = re.compile(r"^Unsuccessful login of user: (.+?)$")
RE_UM_IN = re.compile(r"^User '(.+?)' logged in User Manager\.?$")
RE_UM_OUT = re.compile(r"^User '(.+?)' logged off User Manager\.?$")
RE_GRANT = re.compile(r"^AMS Device Manager User '(.+?)' (granted|revoked) permission '(.+?)' at '(.+?)'\.?$")
RE_ADDED = re.compile(r"^AMS Device Manager User added: '(.+?)'$")
RE_DELETED = re.compile(r"^AMS Device Manager User (deleted|removed): '(.+?)'$")
RE_GROUP = re.compile(r"^AMS Device Manager User '(.+?)' (added to|removed from) group '(.+?)'\.?$")
RE_RENAME = re.compile(r"^AMS Device Manager User '(.+?)' renamed as '(.+?)'\.?$")


def classify_event(desc):
    """回傳 (動作, 目標使用者, 權限, 範圍/群組/新名稱)"""
    d = (desc or "").strip()
    m = RE_LOGIN_OK.match(d)
    if m:
        return "登入成功 (Device Manager)", m.group(1), "", ""
    m = RE_LOGIN_FAIL.match(d)
    if m:
        return "登入失敗", m.group(1), "", ""
    m = RE_UM_IN.match(d)
    if m:
        return "登入 User Manager", m.group(1), "", ""
    m = RE_UM_OUT.match(d)
    if m:
        return "登出 User Manager", m.group(1), "", ""
    m = RE_GRANT.match(d)
    if m:
        return ("授予權限" if m.group(2) == "granted" else "撤銷權限"), m.group(1), m.group(3), m.group(4)
    m = RE_ADDED.match(d)
    if m:
        return "新增使用者", m.group(1), "", ""
    m = RE_DELETED.match(d)
    if m:
        return "刪除使用者", m.group(2), "", ""
    m = RE_GROUP.match(d)
    if m:
        return ("加入群組" if m.group(2) == "added to" else "移出群組"), m.group(1), "", m.group(3)
    m = RE_RENAME.match(d)
    if m:
        return "更名使用者", m.group(1), "", m.group(2)
    return "其他", "", "", ""


def load_user_events(conn, users):
    ev = q(conn, """select e.EventIdDay, e.EventIdFraction, e.EventTime, e.UserKey, e.ComputerId, e.Source, e.Type,
                           e.Category, ec.CategoryDesc, e.Description, e.Other
                    from EventLog e left join EventCategories ec on ec.Category = e.Category
                    where e.Category in (46, 47, 56, 57, 58, 7)
                    order by e.EventTime, e.EventIdDay, e.EventIdFraction""")
    uname = dict(zip(users.UserKey, users.UserName))
    ev["操作者"] = ev.UserKey.map(uname).fillna(ev.UserKey.astype(str))
    ev["電腦IP"] = ev.ComputerId.map(ip_from_computer_id)
    parsed = ev.Description.map(classify_event)
    ev["動作"] = [p[0] for p in parsed]
    ev["目標使用者"] = [p[1] for p in parsed]
    ev["權限"] = [p[2] for p in parsed]
    ev["範圍/群組/新名稱"] = [p[3] for p in parsed]
    ev["時間(台灣)"] = to_tw(ev.EventTime)
    ev["類別"] = ev.Category.map(EVENT_CAT_ZH).fillna(ev.CategoryDesc)
    return ev


# ---------------------------------------------------------------------------
# 主要 build
# ---------------------------------------------------------------------------
def build(conn):
    sheets = []
    b = load_base(conn)
    pr = b["principals"]
    users = b["users"]
    hier = load_hierarchy(conn)
    ev = load_user_events(conn, users)

    # ---------------- Grants 明細 ----------------
    gr = q(conn, """select g.PrincipalId, g.PrivilegeId, g.PlantLocationId,
                           p.Name as PermName, p.Title as PermTitle, p.Description as PermDesc, p.Classification,
                           pg.Name as GroupName, pg.Description as GroupDesc,
                           s.Name as ScopeName
                    from Grants g
                    left join Privileges_Permission p on p.Id = g.PrivilegeId
                    left join PermissionGroups pg on pg.Id = p.PermissionGroupId
                    left join PlantLocations_Scope s on s.Id = g.PlantLocationId""")
    hpath = dict(zip(hier.AreaIdentifier, hier.路徑))
    hid = dict(zip(hier.AreaIdentifier, hier.AreaId))
    pinfo = pr.set_index("PrincipalId")
    gr["主體名稱"] = gr.PrincipalId.map(pinfo.名稱)
    gr["主體類型"] = gr.PrincipalId.map(pinfo.主體類型)
    gr["登入名稱"] = gr.PrincipalId.map(pinfo.登入名稱)
    gr["主體啟用"] = gr.PrincipalId.map(pinfo.啟用)
    gr["分類"] = gr.Classification.map(CLASSIFICATION_ZH)
    gr["權限群組(中)"] = gr.GroupName.map(PERM_GROUP_ZH).fillna(gr.GroupName)
    gr["權限(中)"] = gr.PermName.map(perm_zh)
    gr["範圍路徑"] = gr.PlantLocationId.map(hpath)
    gr["範圍AreaId"] = gr.PlantLocationId.map(hid)
    gr["範圍角色"] = gr.PlantLocationId.map(SCOPE_ROLE).fillna("")
    gr["權限群組+分類"] = gr.GroupName + " [" + gr.分類.str.split(" ").str[0] + "]"

    type_order = {"Windows 使用者": 0, "群組": 1, "標準使用者 (AMS 內部)": 2}
    gr["_t"] = gr.主體類型.map(type_order)
    gr = gr.sort_values(["_t", "主體名稱", "Classification", "GroupName", "PermName", "ScopeName"]).drop(columns="_t")
    grant_df = pd.DataFrame({
        "主體名稱 (Principal)": gr.主體名稱,
        "主體類型": gr.主體類型,
        "登入名稱 (Users.UserName)": gr.登入名稱,
        "主體啟用": gr.主體啟用,
        "權限群組 (PermissionGroups.Name)": gr.GroupName,
        "權限群組(中)": gr["權限群組(中)"],
        "分類 (Classification)": gr.分類,
        "權限 (Privileges_Permission.Name)": gr.PermName,
        "權限(中)": gr["權限(中)"],
        "權限標題 (Title)": gr.PermTitle,
        "權限說明 (Description)": gr.PermDesc,
        "範圍 (PlantLocations_Scope.Name)": gr.ScopeName,
        "範圍路徑 (Hierarchies)": gr.範圍路徑,
        "範圍角色": gr.範圍角色,
        "範圍AreaId": gr.範圍AreaId,
        "PrincipalId": gr.PrincipalId,
        "PrivilegeId": gr.PrivilegeId,
        "PlantLocationId": gr.PlantLocationId,
    }).reset_index(drop=True)

    # ---------------- 主體清單 (Users ∪ Principals) ----------------
    allev = q(conn, """select UserKey, count(*) as n, min(EventTime) as t0, max(EventTime) as t1
                       from EventLog group by UserKey""")
    login_ok = ev[ev.動作 == "登入成功 (Device Manager)"].groupby("UserKey").agg(n=("UserKey", "size"), last=("EventTime", "max"))
    # 登入失敗事件一律記在 UserKey 6 (admin) / 127.0.0.1 之下，須以 Description 解析出的目標使用者歸戶 (不分大小寫)
    login_fail = ev[ev.動作 == "登入失敗"].目標使用者.str.lower().value_counts()
    um_in = ev[ev.動作 == "登入 User Manager"].groupby("UserKey").size()
    acct_ops = ev[ev.Category == 58].groupby("UserKey").size()
    # 主要電腦 (事件數最多的 IP)
    comp = q(conn, "select UserKey, ComputerId, count(*) as n from EventLog group by UserKey, ComputerId")
    comp["ip"] = comp.ComputerId.map(ip_from_computer_id)
    top_ip = comp.sort_values("n", ascending=False).drop_duplicates("UserKey").set_index("UserKey")
    n_ip = comp.groupby("UserKey").ip.nunique()
    gcount = gr.groupby("PrincipalId").size()
    gscopes = gr.groupby("PrincipalId").ScopeName.apply(lambda s: "; ".join(sorted(set(s))))
    gclass = gr.groupby("PrincipalId").分類.apply(lambda s: "; ".join(sorted(set(x.split(" ")[0] for x in s))))
    total_perm = q(conn, "select count(*) as n from Privileges_Permission").n[0]
    # 事件描述中被指名的目標 (帳號異動事件的受影響者), 不分大小寫比對
    target_lower = ev[ev.Category == 58].目標使用者.str.lower()
    tgt_cnt = target_lower.value_counts()

    rows = []
    # (a) 有 Principal 的
    for r in pr.itertuples():
        uk = r.UserKey if pd.notna(r.UserKey) else None
        a = allev[allev.UserKey == uk].iloc[0] if uk is not None and (allev.UserKey == uk).any() else None
        rows.append({
            "主體名稱": r.名稱, "登入名稱 (Users.UserName)": r.UserName if pd.notna(r.UserName) else r.登入名稱,
            "主體類型": r.主體類型, "網域 (Domains.Name)": r.網域, "狀態": r.狀態, "啟用": r.啟用,
            "綁定AD (BindingMode)": r.綁定AD, "建立類型 (CreateType)": r.建立類型,
            "說明 (Description)": r.說明, "職稱 (Title)": r.職稱, "全名 (FullName)": r.全名,
            "所屬群組": r.所屬群組,
            "授權筆數": int(gcount.get(r.PrincipalId, 0)), "權限總數": int(total_perm),
            "授權分類": gclass.get(r.PrincipalId, ""), "授權範圍": gscopes.get(r.PrincipalId, ""),
            "事件總數": int(a.n) if a is not None else 0,
            "登入成功次數": int(login_ok.n.get(uk, 0)) if uk is not None else 0,
            "登入失敗次數": int(login_fail.get(str(r.登入名稱).lower(), 0)),
            "User Manager 登入次數": int(um_in.get(uk, 0)) if uk is not None else 0,
            "執行帳號異動次數": int(acct_ops.get(uk, 0)) if uk is not None else 0,
            "被異動次數 (帳號異動事件目標)": int(tgt_cnt.get(str(r.登入名稱).lower(), 0)),
            "最後登入(台灣)": (pd.to_datetime(login_ok["last"].get(uk)) + TW_OFFSET) if uk is not None and uk in login_ok.index else pd.NaT,
            "最早事件(台灣)": (pd.to_datetime(a.t0) + TW_OFFSET) if a is not None else pd.NaT,
            "最晚事件(台灣)": (pd.to_datetime(a.t1) + TW_OFFSET) if a is not None else pd.NaT,
            "主要電腦IP": top_ip.ip.get(uk, "") if uk is not None else "",
            "使用電腦數": int(n_ip.get(uk, 0)) if uk is not None else 0,
            "UserKey": int(uk) if uk is not None else None,
            "SID": r.SID, "PrincipalId": r.PrincipalId,
            # 本庫全為 1900-01-01 / 0001-01-01 預設哨兵值 (非真實時間, 0001 年無法寫入 Excel 日期) → 以原值文字保留
            "AD最後修改原值 (LastModified)": str(r.最後修改_AD)[:19] if r.最後修改_AD else "",
        })
    # (b) 只在 Users 表 (無 Principal): 舊版/內建/匯入帳號
    have = set(pr.UserKey.dropna().astype(int))
    for r in users.itertuples():
        if int(r.UserKey) in have:
            continue
        uk = int(r.UserKey)
        a = allev[allev.UserKey == uk].iloc[0] if (allev.UserKey == uk).any() else None
        rows.append({
            "主體名稱": r.UserName, "登入名稱 (Users.UserName)": r.UserName,
            "主體類型": "僅 Users 表 (無安全主體)", "網域 (Domains.Name)": r.UserName.split("\\")[0] if "\\" in r.UserName else "",
            "狀態": "保留列 (do not remove)" if uk < 1 else "舊版/匯入帳號, 無法登入", "啟用": "否",
            "綁定AD (BindingMode)": "", "建立類型 (CreateType)": "", "說明 (Description)": "",
            "職稱 (Title)": "", "全名 (FullName)": "", "所屬群組": "",
            "授權筆數": 0, "權限總數": int(total_perm), "授權分類": "", "授權範圍": "",
            "事件總數": int(a.n) if a is not None else 0,
            "登入成功次數": int(login_ok.n.get(uk, 0)), "登入失敗次數": int(login_fail.get(r.UserName.lower(), 0)),
            "User Manager 登入次數": int(um_in.get(uk, 0)), "執行帳號異動次數": int(acct_ops.get(uk, 0)),
            "被異動次數 (帳號異動事件目標)": int(tgt_cnt.get(r.UserName.lower(), 0)),
            "最後登入(台灣)": pd.NaT,
            "最早事件(台灣)": (pd.to_datetime(a.t0) + TW_OFFSET) if a is not None else pd.NaT,
            "最晚事件(台灣)": (pd.to_datetime(a.t1) + TW_OFFSET) if a is not None else pd.NaT,
            "主要電腦IP": top_ip.ip.get(uk, ""), "使用電腦數": int(n_ip.get(uk, 0)),
            "UserKey": uk, "SID": "", "PrincipalId": "", "AD最後修改原值 (LastModified)": "",
        })
    plist = pd.DataFrame(rows)
    order = {"Windows 使用者": 0, "群組": 1, "標準使用者 (AMS 內部)": 2, "僅 Users 表 (無安全主體)": 3}
    plist["_o"] = plist.主體類型.map(order)
    plist = plist.sort_values(["_o", "事件總數", "主體名稱"], ascending=[True, False, True]).drop(columns="_o").reset_index(drop=True)

    # 帳號性質備註
    def nature(r):
        n = str(r["登入名稱 (Users.UserName)"]).lower()
        if r["主體類型"] == "群組":
            return "內建權限範本群組 (無成員; GroupPrincipalWindowsUserPrincipal 為空)"
        if n == "admin" or n.startswith("dbm:"):
            return "隨 AmsMergeDoc 範本匯入之舊帳號 (原廠範本環境, 非本廠)"
        if n in ("amsserviceuser",):
            return "AMS 服務帳號 (AmsSp_CheckUserPermission 中永遠有權限)"
        if n.startswith("ps."):
            return "Plant Server 服務帳號 (伺服器自動偵測現場變更)"
        if n.startswith("fs."):
            return "File Server 服務帳號"
        if n == "install":
            return "安裝程式帳號 (其下 807 筆事件為 1996–2019 範本匯入之原廠事件, 非本廠)"
        if "geadmin" in n:
            return "共用管理帳號 (推定 GE 試運轉使用)"
        if "admin" in n:
            return "管理帳號"
        if re.fullmatch(r"(hmi\\)?u\d{6}", n):
            return "具名個人帳號 (台電員工編號)"
        if "do not remove" in n:
            return "AMS 內建保留列"
        return ""

    plist.insert(3, "帳號性質(推定)", plist.apply(nature, axis=1))

    sheets.append(dict(
        name="使用者與安全主體",
        purpose="列出 AMS 所有安全主體 (Windows 使用者/群組/標準使用者) 與 Users 表帳號，含啟用狀態、授權數與事件活動統計",
        one_row="一個安全主體 (Principal) 或 Users 表帳號",
        df=plist,
        notes=[
            "來源: Principals_UserWindowsPrincipal / _GroupWindowsPrincipal / _StandardUserPrincipal ∪ Users；Users.UserName 對 Windows 使用者為「網域\\帳號」(AmsSp_CreateWinUserPrincipal)，對標準使用者為名稱本身 (AmsSp_CreateStdUserPrincipal)，不分大小寫比對。",
            "Windows 使用者 Status: 1=啟用, 0=停用 (AmsVw_UM_WindowsUser: Enabled = Status=1；AmsSp_HasPermission: Status 0/-1 一律無權限)。",
            "標準使用者 State: 0=有效, 1=可見(已退役, AmsVw_UM_RetiredAccount), 2=隱藏 (AmsSp_CreateStdUserPrincipal 註解; AmsSp_AmsUser_GetKey_1 以 State=2 自動建立服務帳號)。本庫 4 個標準使用者皆為 2=隱藏。",
            "BindingMode 1=已綁定 Active Directory (AmsVw_UM_WindowsUser Bound)；本庫全部 0。CreateType → SecurityType (0=系統內建, 1=使用者自訂)。",
            "所屬群組來自 GroupPrincipalWindowsUserPrincipal，本庫為空表 → 4 個內建群組無任何成員，權限全部直接授予使用者。",
            "登入失敗事件 (Unsuccessful login of user: X) 一律記在 UserKey 6 (admin)、ComputerId 127.0.0.1 之下，故失敗次數依 Description 中的帳號歸戶 (GEAdmin 5 次、HTPPAdmin 1 次)。",
            "登入成功/失敗/User Manager 登入取自 EventLog Category 46 (Log In) 之 Description 文字；帳號異動取自 Category 58；事件總數為 EventLog 全部 29,773 筆依 UserKey 統計。",
            "主要電腦IP = 該使用者事件數最多的 ComputerId；ComputerId 為 IPv4 以 big-endian 有號 32 位元整數儲存 (2130706433=127.0.0.1)，與前版 17_使用者與電腦 的 172.16.201.131 等一致。",
            "時間欄位皆已由 UTC 轉台灣時間 (+8h)。AD最後修改原值 (LastModified) 本庫全為 1900-01-01 (10 列) / 0001-01-01 (GEAdmin) 之未同步 AD 預設哨兵值，非真實時間，故以文字保留原值。",
            "SID 欄本庫全部空白/NULL：使用者未與 Windows SID 綁定 (AmsSp_CreateWinUserPrincipal @Sid 預設 '')。全名 (FullName) 欄本庫亦全部空白 (建立使用者時未填)。綁定AD 全為否、建立類型 (群組) 全為系統內建。",
            "'install' (標準使用者, UserKey 10) 名下 807 筆事件全為 1996–2019 年、來自 226 個原廠 IP (155.177.x 等) 的範本匯入事件，與 admin/DBM: None 同屬 AmsMergeDoc 範本環境；本廠自 2024-11 起 install 無事件。",
            "主要電腦IP '(哨兵 -1)' = EventLog 測試列 (UserKey -1, ComputerId -1) 的非 IP 哨兵值。",
            "'HMI\\Admin1' 原名 'HMI\\Admin'，2026-06-18 由 GEAdmin 更名 (EventLog Category 58)。",
        ],
        source_tables=["Principals", "Principals_UserWindowsPrincipal", "Principals_GroupWindowsPrincipal", "Principals_StandardUserPrincipal",
                       "Principals_WindowsPrincipal", "GroupPrincipalWindowsUserPrincipal", "Users", "Domains", "SecurityType", "Grants", "EventLog", "EventCategories"],
    ))

    # ---------------- 授權明細 ----------------
    sheets.append(dict(
        name="權限授予明細",
        purpose="每一筆授權 (主體 × 權限 × 廠區範圍)，權限已對應群組/分類，範圍已解析為階層路徑",
        one_row="Grants 表一列 (一個主體對一個權限在一個範圍的授權)",
        df=grant_df,
        notes=[
            "Grants(PrincipalId, PrivilegeId, PlantLocationId) → Privileges_Permission (權限) → PermissionGroups (群組)；PlantLocationId → PlantLocations_Scope.Name = Hierarchies.AreaIdentifier。",
            "分類 (PermissionClassification): 0=SIS, 1=BPCS, 2=System, 3=Configuration。AmsSp_CheckUserPermission: System 類權限的根範圍為 '~/System' (87FC0717…)，Configuration 類為 '~/User Configurations' (5DC4F174…)，SIS/BPCS 類為 '~/Site-wide' (81C7311F…)；Manufacturer (3CFEC380…) 在檢查時排除。",
            "本庫授權只出現在三個範圍：Site-wide 244 筆、System 156 筆、User Configurations 18 筆 (Unassigned 與 Manufacturer 無授權)。",
            "權限判定 = 使用者自身授權 ∪ 所屬群組授權 (GroupPrincipalWindowsUserPrincipal)；本庫群組無成員，故群組列僅為權限範本。",
            "Privileges_PermissionList / PermissionListPermission / PlantLocations_ScopeList / ScopeListScope (複合權限/複合範圍) 皆為空表，未使用。",
            "Device Write 及 ValveLink 動閥類權限在 AmsSp_HasPermission 中另檢查 DeviceProtection (本庫為空 → 無裝置被保護)。",
        ],
        source_tables=["Grants", "Privileges", "Privileges_Permission", "PermissionGroups", "PermissionClassification", "PlantLocations", "PlantLocations_Scope", "Hierarchies", "Principals_UserWindowsPrincipal", "Principals_GroupWindowsPrincipal"],
    ))

    # ---------------- 權限矩陣 (主體 × 權限群組) ----------------
    perms = q(conn, """select p.Id, p.Name, p.Title, p.Classification, pg.Name as GroupName
                       from Privileges_Permission p left join PermissionGroups pg on pg.Id = p.PermissionGroupId""")
    perms["分類"] = perms.Classification.map(CLASSIFICATION_ZH).str.split(" ").str[0]
    perms["群組+分類"] = perms.GroupName + " [" + perms.分類 + "]"
    grp_total = perms.groupby("群組+分類").size()
    grp_cols = sorted(grp_total.index, key=lambda g: (perms[perms["群組+分類"] == g].Classification.iloc[0], g))
    principals_ordered = plist[plist.PrincipalId != ""][["主體名稱", "主體類型", "登入名稱 (Users.UserName)", "啟用", "PrincipalId"]]
    cnt = gr.groupby(["PrincipalId", "權限群組+分類"]).PrivilegeId.nunique()
    mrows = []
    for r in principals_ordered.itertuples(index=False):
        row = {"主體名稱": r[0], "主體類型": r[1], "登入名稱": r[2], "啟用": r[3]}
        tot = 0
        for g in grp_cols:
            c = int(cnt.get((r[4], g), 0))
            tot += c
            row[f"{g} ({grp_total[g]})"] = f"{c}/{grp_total[g]}" if c else ""
        row["授權合計"] = f"{tot}/{int(total_perm)}"
        row["等級(推定)"] = ("完整 (全部權限)" if tot == total_perm else "無" if tot == 0 else "部分")
        mrows.append(row)
    matrix_grp = pd.DataFrame(mrows)
    sheets.append(dict(
        name="權限矩陣_依權限群組",
        purpose="主體 × 權限群組 的授權數量總覽 (n/群組內權限總數)，快速看出誰是完整管理者、誰是唯讀",
        one_row="一個安全主體",
        df=matrix_grp,
        notes=[
            "儲存格 = 該主體在該權限群組內被授予的權限數 / 群組內權限總數；空白 = 0。欄名中括號為分類 (SIS/BPCS/系統/組態)。",
            "同名權限群組 (Device / Calibration / Alert Monitor / AMS ValveLink SNAP-ON) 分 SIS 與 BPCS (或 System) 兩個 GUID，故以「群組 [分類]」區分。",
            "授權合計 46/46 = 擁有全部單一權限 (等同 System Admin 群組範本)。",
        ],
        source_tables=["Grants", "Privileges_Permission", "PermissionGroups", "PermissionClassification"],
    ))

    # ---------------- 權限矩陣 (主體 × 每個權限 是/否) ----------------
    perms_sorted = perms.sort_values(["Classification", "GroupName", "Name"])
    has = set(zip(gr.PrincipalId, gr.PrivilegeId))
    scope_of = gr.groupby(["PrincipalId", "PrivilegeId"]).ScopeName.first()
    mrows = []
    for r in principals_ordered.itertuples(index=False):
        row = {"主體名稱": r[0], "主體類型": r[1], "登入名稱": r[2], "啟用": r[3]}
        for p in perms_sorted.itertuples():
            col = f"{p.Title} [{p.分類}]"
            row[col] = "是" if (r[4], p.Id) in has else "否"
        mrows.append(row)
    matrix_perm = pd.DataFrame(mrows)
    # 附加一列: 範圍
    scope_row = {"主體名稱": "(授權範圍)", "主體類型": "", "登入名稱": "", "啟用": ""}
    for p in perms_sorted.itertuples():
        col = f"{p.Title} [{p.分類}]"
        scopes = sorted(set(gr[gr.PrivilegeId == p.Id].ScopeName))
        scope_row[col] = "; ".join(scopes)
    matrix_perm = pd.concat([matrix_perm, pd.DataFrame([scope_row])], ignore_index=True)
    sheets.append(dict(
        name="權限矩陣_逐權限",
        purpose="主體 × 46 個單一權限 的 是/否 矩陣，最後一列標示該權限實際授予的範圍",
        one_row="一個安全主體 (最末列為各權限的授權範圍彙整)",
        df=matrix_perm,
        notes=[
            "欄名 = Privileges_Permission.Title [分類]；是 = Grants 中存在該 (主體, 權限) 授權 (不論範圍)。",
            "最末列 (授權範圍) 列出本庫中該權限被授予的範圍名稱；SIS/BPCS 類權限只在 Site-wide，System 類只在 System，Configuration 類只在 User Configurations。",
        ],
        source_tables=["Grants", "Privileges_Permission", "PermissionGroups", "PermissionClassification", "PlantLocations_Scope"],
    ))

    # ---------------- 登入 / 登出 / 帳號異動事件 ----------------
    ev_df = pd.DataFrame({
        "時間(台灣)": ev["時間(台灣)"],
        "時間UTC (EventTime)": ev.EventTime,
        "類別": ev.類別,
        "動作": ev.動作,
        "操作者 (Users.UserName)": ev.操作者,
        "目標使用者": ev.目標使用者,
        "權限": ev.權限,
        "權限(中)": ev.權限.map(lambda x: perm_zh(x) if x else ""),
        "範圍/群組/新名稱": ev["範圍/群組/新名稱"],
        "電腦IP (ComputerId)": ev.電腦IP,
        "來源程式 (Source)": ev.Source,
        "說明 (Description)": ev.Description,
        "事件類別碼 (Category)": ev.Category,
        "類別原文 (CategoryDesc)": ev.CategoryDesc,
        "UserKey": ev.UserKey,
        "EventIdDay": ev.EventIdDay,
        "EventIdFraction": ev.EventIdFraction,
    }).sort_values(["時間(台灣)", "EventIdDay", "EventIdFraction"], ascending=[False, False, False]).reset_index(drop=True)
    sheets.append(dict(
        name="登入與帳號異動事件",
        purpose="EventLog 中的登入/登出/使用者帳號異動事件，已解析出目標使用者、權限與範圍",
        one_row="一筆 EventLog 事件 (Category 46 登入 / 47 登出 / 58 使用者帳號異動)",
        df=ev_df,
        notes=[
            "EventLog.EventTime 為 UTC，時間(台灣) = +8h；Category 對照 EventCategories：46=Log In, 47=Log Out, 58=User Account Changed (56/57/7 本庫無資料)。",
            "動作/目標使用者/權限/範圍 由 Description 以正規表示式解析：'Successful login of user: X to AMS Device Manager.'、'Unsuccessful login of user: X'、\"User 'X' logged in/off User Manager.\"、\"AMS Device Manager User 'X' granted permission 'P' at 'S'.\"、\"User added: 'X'\"、\"'X' added to/removed from group 'G'.\"、\"'X' renamed as 'Y'.\"",
            "目標使用者名稱大小寫依登入時輸入 (GEadmin/geadmin/GEAdmin 為同一帳號 UserKey 8)。",
            "登入失敗事件的操作者欄為 admin (UserKey 6)、IP 127.0.0.1：AMS 在驗證失敗時以內建 admin 帳號記錄，真正嘗試登入者見「目標使用者」。",
            "登出事件 (47) 只有 User Manager 的登出；AMS Device Manager 主程式不記錄登出。",
            "ComputerId 解碼為 IPv4 (big-endian 有號整數)。",
        ],
        source_tables=["EventLog", "EventCategories", "Users"],
    ))

    # ---------------- 使用者 × 電腦 × 事件類別 活動統計 ----------------
    act = q(conn, """select e.UserKey, e.ComputerId, e.Category, ec.CategoryDesc, count(*) as n,
                            min(e.EventTime) as t0, max(e.EventTime) as t1
                     from EventLog e left join EventCategories ec on ec.Category = e.Category
                     group by e.UserKey, e.ComputerId, e.Category""")
    uname = dict(zip(users.UserKey, users.UserName))
    act_df = pd.DataFrame({
        "使用者 (Users.UserName)": act.UserKey.map(uname).fillna(act.UserKey.astype(str)),
        "電腦IP (ComputerId)": act.ComputerId.map(ip_from_computer_id),
        "事件類別碼 (Category)": act.Category,
        "事件類別 (CategoryDesc)": act.CategoryDesc,
        "事件數": act.n,
        "最早(台灣)": to_tw(act.t0),
        "最晚(台灣)": to_tw(act.t1),
        "UserKey": act.UserKey,
        "ComputerId原值": act.ComputerId,
    }).sort_values(["事件數"], ascending=False).reset_index(drop=True)
    sheets.append(dict(
        name="使用者電腦活動統計",
        purpose="每個使用者在每台電腦 (IP) 上各類事件的數量與時間範圍，用於追溯誰從哪台工作站做了什麼",
        one_row="一個 (使用者, 電腦IP, 事件類別) 組合",
        df=act_df,
        notes=[
            "來源 EventLog 全部 29,773 筆 (Archived 全為 0)，含 2 筆哨兵測試列 (UserKey -1, ComputerId -1 → 電腦IP 顯示 '(哨兵 -1)', 時間 1970/2036)。",
            "ComputerId → IPv4 big-endian；172.16.201.131 為主要工作站 (17,695 筆)，127.0.0.1 為伺服器本機，1996 年 FMS 匯入事件的 IP (142.176.x / 155.177.x) 為範本原廠環境，非本廠。",
            "前版 17_使用者與電腦 只統計裝置事件 (13,682 筆)；本表含登入、掃描、Rebuild Hierarchy 等非裝置事件。",
        ],
        source_tables=["EventLog", "EventCategories", "Users"],
    ))

    # ---------------- 廠區階層與授權範圍 ----------------
    av = q(conn, "select ViewAreaId, ViewType, MaxLevels, Required, Balanced, Permissions from AreaViews")
    al = q(conn, "select ViewAreaId, AreaLevel, AreaLabelId from AreaLevels")
    lb = q(conn, "select LabelId, LabelName from Labels")
    # LabelId -1 / 0 為哨兵列 ('None (do not remove!!!!)' / 'Empty string (do not remove!!!!)') → 顯示空白
    lbl = {k: (v if k > 0 else "") for k, v in zip(lb.LabelId, lb.LabelName)}
    comp = q(conn, "select AreaId, count(*) as n, group_concat(TableName || ':' || TableKey, '; ') as comp_list from Components group by AreaId")
    nc = q(conn, "select ConfigKey, ConfigName from NamedConfigs where ConfigKey in (select TableKey from Components where TableName='NamedConfigs')")
    nc_name = dict(zip(nc.ConfigKey, nc.ConfigName))
    scope = q(conn, "select Id, Name from PlantLocations_Scope")
    scope_set = set(scope.Id)
    gr_by_scope = gr.groupby("PlantLocationId").size()
    gr_pr_scope = gr.groupby("PlantLocationId").主體名稱.nunique()
    dev_loc_cols = [c[1] for c in conn.execute("pragma table_info(DeviceLocation)")]
    av_i = av.set_index("ViewAreaId")

    def comp_items(aid):
        r = comp[comp.AreaId == aid]
        if r.empty:
            return ""
        keys = [int(x.split(":")[1]) for x in r.comp_list.iloc[0].split("; ")]
        return "; ".join(f"{k} {nc_name.get(k, '')}".strip() for k in keys)

    hrows = []
    for r in hier.sort_values(["ViewAreaId", "AreaLevel", "AreaId"]).itertuples():
        v = av_i.loc[r.ViewAreaId] if r.ViewAreaId in av_i.index else None
        hrows.append({
            "區域名稱 (AreaName)": r.AreaName,
            "路徑": r.路徑,
            "AreaId": r.AreaId, "ParentAreaId": r.ParentAreaId, "AreaLevel": r.AreaLevel, "ViewAreaId": r.ViewAreaId,
            "檢視類型 (AreaViews.ViewType)": AREAVIEW_TYPE_ZH.get(v.ViewType.strip(), v.ViewType) if v is not None else "",
            "最大層數 (MaxLevels)": int(v.MaxLevels) if v is not None else None,
            "必要 (Required)": yn(v.Required) if v is not None else "",
            "平衡樹 (Balanced)": yn(v.Balanced) if v is not None else "",
            "檢視權限旗標 (Permissions)": v.Permissions.strip() if v is not None else "",
            "層級標籤 (Labels)": lbl.get(r.LabelId, ""),
            "可作授權範圍": yn(r.AreaIdentifier in scope_set),
            "範圍角色": SCOPE_ROLE.get(r.AreaIdentifier, ""),
            "授權筆數": int(gr_by_scope.get(r.AreaIdentifier, 0)),
            "被授權主體數": int(gr_pr_scope.get(r.AreaIdentifier, 0)),
            "掛載元件 (Components)": comp_items(r.AreaId),
            "AreaIdentifier": r.AreaIdentifier,
        })
    hier_df = pd.DataFrame(hrows)
    sheets.append(dict(
        name="廠區階層與授權範圍",
        purpose="Hierarchies 階層樹 (含檢視定義/層級標籤) 與 PlantLocations_Scope 授權範圍的對應，以及各範圍的授權統計",
        one_row="一個階層節點 (Hierarchies 一列)",
        df=hier_df,
        notes=[
            "本廠未建立自訂廠區階層：Manufacturer (AreaId 1, ParentAreaId 0) 之下無任何區域 (AreaViews 1 定義 M 檢視最多 3 層、Labels Level 1/Level 2 但未使用)；所有 1,928 台裝置的位置皆為 Unassigned/Manufacturer 預設。",
            "ParentAreaId -99 = 根節點；0 = 掛在 Site-wide 之下 (AmsVw_EF_Location 規則)；-3 = User Configurations 子資料夾。",
            "AreaViews.Permissions 'ARO,RO' 為舊版 (V12 前) 檢視旗標，新版改用 Grants。",
            "Components 只有 10 列，全為 Standard Configurations (-4) 下的 NamedConfigs 範本 (ConfigKey 2700–2709)。",
            "AreaLevels: 檢視 1 (Manufacturer) 第 1 層標籤 'Level 1'、第 2 層 'Level 2'；Hierarchies 8 節點 LabelId 皆為 0 (哨兵 'Empty string (do not remove!!!!)') → 層級標籤欄全空白。",
            "8 個節點皆有對應 PlantLocations_Scope (可作授權範圍全為是；FK_Scope_Hierarchies: Scope.Id → Hierarchies.AreaIdentifier)；AreaViews 6 個檢視 Required 全為 1、Permissions 全為 'ARO,RO'。",
        ],
        source_tables=["Hierarchies", "PlantLocations", "PlantLocations_Scope", "AreaViews", "AreaLevels", "Labels", "Components", "NamedConfigs", "Grants"],
    ))

    # ---------------- 權限定義字典 ----------------
    pdef = q(conn, """select p.Id, p.Name, p.Title, p.Description, p.Classification, pg.Name as GroupName, pg.Description as GroupDesc,
                             sc.Name as ComponentName
                      from Privileges_Permission p
                      left join PermissionGroups pg on pg.Id = p.PermissionGroupId
                      left join SecurityComponent sc on sc.Id = pg.ComponentId
                      order by p.Classification, pg.Name, p.Name""")
    n_grant = gr.groupby("PrivilegeId").size()
    n_princ = gr.groupby("PrivilegeId").主體名稱.nunique()
    pdef_df = pd.DataFrame({
        "權限標題 (Title)": pdef.Title,
        "權限 (Name)": pdef.Name, "權限(中)": pdef.Name.map(perm_zh),
        "權限群組 (PermissionGroups.Name)": pdef.GroupName, "權限群組(中)": pdef.GroupName.map(PERM_GROUP_ZH).fillna(pdef.GroupName),
        "分類 (Classification)": pdef.Classification.map(CLASSIFICATION_ZH),
        "說明 (Description)": pdef.Description, "群組說明": pdef.GroupDesc,
        "安全元件 (SecurityComponent)": pdef.ComponentName,
        "授權筆數": pdef.Id.map(n_grant).fillna(0).astype(int),
        "被授權主體數": pdef.Id.map(n_princ).fillna(0).astype(int),
        "根範圍 (依分類)": pdef.Classification.map({0: "~/Site-wide", 1: "~/Site-wide", 2: "~/System", 3: "~/User Configurations"}),
        "PrivilegeId": pdef.Id,
    })
    sheets.append(dict(
        name="權限定義字典",
        purpose="AMS 的 46 個單一權限定義 (群組/分類/說明) 與本庫授權統計",
        one_row="一個權限 (Privileges_Permission 一列)",
        df=pdef_df,
        notes=[
            "PermissionGroups 15 個群組全屬 SecurityComponent 'AMS Device Manager'；同名群組以分類 (SIS/BPCS/System) 區分。",
            "根範圍依 AmsSp_CheckUserPermission：Classification 2 (System) → System 資料夾；3 (Configuration) → User Configurations；0/1 → Site-wide。",
        ],
        source_tables=["Privileges", "Privileges_Permission", "PermissionGroups", "PermissionClassification", "SecurityComponent", "Grants"],
    ))

    # ---------------- 資料庫版本歷程 ----------------
    ver = q(conn, "select Major, Minor, SchemaDate, SchemaNotes from __version order by Major, Minor")
    ver_df = pd.DataFrame({
        "版本 (Major.Minor)": ver.Major.astype(str) + "." + ver.Minor.astype(str),
        "結構日期 (SchemaDate)": pd.to_datetime(ver.SchemaDate, errors="coerce"),
        "備註 (SchemaNotes)": ver.SchemaNotes,
        "Major": ver.Major, "Minor": ver.Minor,
    })
    ver_df["目前版本"] = ["是" if i == len(ver_df) - 1 else "否" for i in range(len(ver_df))]
    sheets.append(dict(
        name="資料庫結構版本歷程",
        purpose="__version 表：AmsDb 結構版本沿革，可對應 AMS Device Manager 產品版本 (最新 5.1 = V14.1.1)",
        one_row="一個資料庫結構版本",
        df=ver_df,
        notes=[
            "SchemaDate 為 Emerson 發布該結構的日期 (非本廠升級日)；本庫最新為 5.1 V14.1.1 (2018-03-13)，即本廠 AMS Device Manager 為 V14.1.1 (或相容之 14.1.x)。",
            "版本 5.0 'V14' 日期 2016-05-24 早於 4.0 'V13.5' 2016-11-01，為原廠資料如此。",
            "代號: Viper=V7, Charger/Falcon/Puma/Stingray=V8–V11, Wildcat=V11.5, 之後直接以 V12/V12.5/V13.5/V14 命名。",
        ],
        source_tables=["__version"],
    ))

    # ---------------- 系統資訊 (key-value) ----------------
    info = q(conn, "select * from _dbinfo")
    ps = q(conn, "select PlantServerKey, PlantServerId, AlertMonitorEnabled from PlantServer")
    sc = q(conn, "select Id, Name, Description, Title from SecurityComponent")
    sr = q(conn, "select ServiceId, ServiceDesc from ServiceReasons")
    mdt = q(conn, "select MobDevTypeId, Name from MobileDeviceTypes")
    st = q(conn, "select SecurityType.Id, Name from SecurityType")
    pc = q(conn, "select Id, Name from PermissionClassification")
    sp = q(conn, "select * from StationProperty")
    sd = q(conn, "select * from SystemDefaults")
    tbl = q(conn, "select table_name, row_count from _tables")
    n_dev = conn.execute("select count(*) from Devices where DeviceKey >= 0").fetchone()[0]
    ev_span = conn.execute("select min(EventTime), max(EventTime), count(*) from EventLog where EventIdDay > 25569 and EventTime < '2030-01-01'").fetchone()

    krows = []

    def add(sec, item, val, src, note=""):
        krows.append({"區段": sec, "項目": item, "值": "" if val is None else str(val), "來源表": src, "備註": note})

    for r in info.itertuples():
        add("資料庫", "資料庫名稱", r.name, "_dbinfo")
        add("資料庫", "相容性層級 (compatibility_level)", r.compatibility_level, "_dbinfo", "120 = SQL Server 2014")
        add("資料庫", "定序 (collation_name)", r.collation_name, "_dbinfo", "不分大小寫 (CI)、區分腔調 (AS)")
        add("資料庫", "建立日期 (create_date)", r.create_date, "_dbinfo", "還原備份時之建立時間 (非原始安裝日)")
    add("資料庫", "結構版本 (__version 最新)", f"{ver.Major.iloc[-1]}.{ver.Minor.iloc[-1]} {ver.SchemaNotes.iloc[-1]} ({ver.SchemaDate.iloc[-1][:10]})", "__version", "對應 AMS Device Manager V14.1.1")
    add("資料庫", "資料表數", len(tbl), "_tables", f"非空 {int((tbl.row_count > 0).sum())} 表 / 空 {int((tbl.row_count == 0).sum())} 表")
    add("資料庫", "總列數", int(tbl.row_count.sum()), "_tables")
    add("資料庫", "裝置數 (Devices, 排除 -1)", n_dev, "Devices")
    add("資料庫", "事件數 (EventLog)", ev_span[2], "EventLog", f"有效時間範圍 UTC {ev_span[0]} ~ {ev_span[1]} (排除 1970 測試列及 2036 哨兵列)")
    for r in ps.itertuples():
        add("Plant Server", f"PlantServerKey {r.PlantServerKey}", r.PlantServerId, "PlantServer", f"AlertMonitorEnabled={yn(r.AlertMonitorEnabled)}" + ("；保留列" if r.PlantServerKey < 0 else "；本廠 AMS 伺服器"))
    for r in b["domains"].itertuples():
        add("網域", f"Domains {r.Name.strip()}", r.Id, "Domains", (r.Title if isinstance(r.Title, str) else "") + ("；NullDomain 為無網域哨兵 (AmsVw_UM_WindowsNetworkDomain 排除)" if r.Id == GUID_NULL_DOMAIN else "；Windows 網域/電腦名稱 (使用者登入用)" if r.Name.strip() == "HMI" else "；伺服器本機名 (內建群組所屬)"))
    for r in sc.itertuples():
        add("安全元件", r.Name, r.Id, "SecurityComponent")
    for r in st.itertuples():
        add("代碼表", f"SecurityType {r.Id}", r.Name, "SecurityType", SECURITY_TYPE_ZH.get(r.Id, ""))
    for r in pc.itertuples():
        add("代碼表", f"PermissionClassification {r.Id}", r.Name, "PermissionClassification", CLASSIFICATION_ZH.get(r.Id, ""))
    for r in sr.itertuples():
        add("代碼表", f"ServiceReasons {r.ServiceId}", r.ServiceDesc, "ServiceReasons", "校正服務原因 (TestResults.ServiceId；本庫無測試結果)")
    for r in mdt.itertuples():
        add("代碼表", f"MobileDeviceTypes {r.MobDevTypeId}", r.Name, "MobileDeviceTypes", "MobileDevices 為空 → 未登錄任何 Trex 手持器")
    for r in sp.itertuples():
        add("工作站", f"StationProperty {r[3]}.{r[4]}", r[5], "StationProperty", f"PlantServerKey={r[2]}")
    for r in sd.itertuples():
        add("系統預設值", r[1], r[2], "SystemDefaults", "GlobalDeviceProtection=false 表示全域裝置保護關閉" if r[1] == "GlobalDeviceProtection" else "")
    add("統計", "安全主體數", len(pr), "Principals", f"Windows 使用者 {len(b['win'])} / 群組 {len(b['grp'])} / 標準使用者 {len(b['std'])}")
    add("統計", "Users 表帳號數", len(users), "Users", "含 -1/0 保留列與 2 個無主體舊帳號 (admin, DBM: None)")
    add("統計", "授權筆數 (Grants)", len(gr), "Grants", f"主體 {gr.PrincipalId.nunique()} 個 × 範圍 {gr.PlantLocationId.nunique()} 種")
    add("統計", "登入成功事件", int((ev.動作 == "登入成功 (Device Manager)").sum()), "EventLog", f"登入失敗 {int((ev.動作 == '登入失敗').sum())} 筆")
    add("統計", "使用者帳號異動事件", int((ev.Category == 58).sum()), "EventLog")
    sys_df = pd.DataFrame(krows)
    sheets.append(dict(
        name="系統資訊",
        purpose="資料庫/伺服器/網域/代碼表/系統預設值等系統層級資訊之鍵值總覽 (本領域摘要表)",
        one_row="一個系統資訊項目 (鍵/值)",
        df=sys_df,
        notes=[
            "本領域空表 (未建立資料表, 僅列於此): Grants_NetworkLocation (網路節點授權)、GroupPrincipalWindowsUserPrincipal (群組成員)、Privileges_PermissionList / PermissionListPermission (複合權限)、PlantLocations_ScopeList / ScopeListScope (複合範圍)、MobileDevices / MobileDeviceEventLog (Trex 手持器)、DeviceProtection (裝置保護)。",
            "_dbinfo.create_date 2026-09-12 11:36 為 SQL Server 還原備份時的時間，非本廠 AMS 安裝日；本廠事件最早自 2024-11-20 (GEAdmin)、Plant Server 自 2024-12-04 開始。",
            "Domains 'HMI' = 使用者登入之 Windows 網域 (HMI\\帳號)；'AMS1SVR' = 伺服器本機，內建 4 群組掛於此。",
        ],
        source_tables=["_dbinfo", "_tables", "__version", "PlantServer", "Domains", "SecurityComponent", "SecurityType", "PermissionClassification", "ServiceReasons", "MobileDeviceTypes", "StationProperty", "SystemDefaults", "Devices", "EventLog", "Grants"],
    ))

    # ---------------- 資料表清單 ----------------
    fk = q(conn, "select * from _foreign_keys")
    fk_cols = list(fk.columns)
    # _foreign_keys: fk_name, parent_schema, parent_table, parent_column, ref_schema, ref_table, ref_column
    fk_out = fk.groupby("parent_table").fk_name.nunique()
    fk_in = fk.groupby("ref_table").fk_name.nunique()
    schema = q(conn, "select table_name, count(*) as ncol from _schema group by table_name")
    ncol = dict(zip(schema.table_name, schema.ncol))
    trows = []
    for r in tbl.itertuples():
        dom, desc = TABLE_DOC.get(r.table_name, ("其他", ""))
        trows.append({
            "領域": dom, "資料表 (table_name)": r.table_name, "列數 (row_count)": int(r.row_count),
            "欄位數": int(ncol.get(r.table_name, 0)), "是否空表": yn(r.row_count == 0),
            "說明": desc,
            "外鍵數 (參照他表)": int(fk_out.get(r.table_name, 0)), "被參照數": int(fk_in.get(r.table_name, 0)),
            "本解析領域": "是" if dom in ("使用者與權限", "廠區階層", "系統", "行動裝置與政策") else "否",
        })
    dom_order = ["設備主檔", "區塊與參數", "範本與組態", "事件與稽核", "警報與健康", "校正與測試", "網路", "使用者與權限", "廠區階層", "行動裝置與政策", "專案與任務", "系統", "其他"]
    tbl_df = pd.DataFrame(trows)
    tbl_df["_o"] = tbl_df.領域.map({d: i for i, d in enumerate(dom_order)})
    tbl_df = tbl_df.sort_values(["_o", "列數 (row_count)", "資料表 (table_name)"], ascending=[True, False, True]).drop(columns="_o").reset_index(drop=True)
    sheets.append(dict(
        name="資料表清單與領域",
        purpose="AmsDb 全部 105 張資料表依領域分組，附列數、欄位數、外鍵數與一行中文說明",
        one_row="一張資料表",
        df=tbl_df,
        notes=[
            "列數來自 _tables (傾印時統計)；說明依表名/欄位/_modules 註解整理。",
            "領域分組為本解析自訂，非 Emerson 官方分類。",
            f"外鍵欄位來源 _foreign_keys ({', '.join(fk_cols)})。",
        ],
        source_tables=["_tables", "_schema", "_foreign_keys"],
    ))

    return sheets


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import time
    t0 = time.time()
    conn = sqlite3.connect(DB_PATH)
    sheets = build(conn)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for s in sheets:
        df = s["df"]
        print(f"{s['name']}: {len(df)} rows x {len(df.columns)} cols")
        safe = re.sub(r"[\\/:*?\"<>|]", "_", s["name"])
        df.to_csv(OUT_DIR / f"{KEY}__{safe}.csv", index=False, encoding="utf-8-sig")
    print(f"done in {time.time() - t0:.1f}s")
