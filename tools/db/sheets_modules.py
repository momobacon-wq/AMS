# -*- coding: utf-8 -*-
"""
sheets_modules.py — AmsDb 資料庫「程式碼與語意」領域解碼
產出：資料表字典 / 欄位字典 / 視圖與程序 / 關鍵語意規則 / 代碼對照表
build(conn) -> list[dict]
"""
import re
import sqlite3
import struct
import socket
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tools/db/paths.py：repo 外路徑的唯一來源
from paths import AMS_SQLITE as DB, SHEETS_OUT as OUT  # noqa: E402

KEY = "modules"

# ----------------------------------------------------------------------------
# 資料表中文說明（由欄位名 + 模組原始碼註解推得）
# ----------------------------------------------------------------------------
TABLE_DESC = {
    "__version": ("系統", "資料庫結構版本沿革（Major.Minor、日期、變更說明），自 1995 年起累積"),
    "AlertFilterForDevice": ("警報", "每台裝置 × 每個警報描述 (AlertDescId) 的啟用/停用過濾設定（Alert Monitor 用）"),
    "AlertList": ("警報", "Alert Monitor 目前作用中的警報清單（Set/Clear 狀態、確認狀態），由 EventLog 警報事件同步產生"),
    "AlertList_UpdateTracking": ("警報", "AlertList 變更追蹤（初始化/最後更新/最後新增時間），供 AmsSp_ALTrack_* 判斷清單是否需重讀"),
    "AlertLog": ("警報", "EventLog 中屬於警報 (Type=5) 事件的附屬紀錄：AlertId 與 AlertTypeId (FAILED/MAINT/ADVISE…)"),
    "AlertTypes": ("代碼", "警報種類代碼表：0 UNKNOWN、1 FAILED、2 MAINT、3 ADVISE、4 ABNORM、5 NOCOMM、6 CHKFNC"),
    "AreaLevels": ("階層", "廠區階層檢視 (ViewAreaId) 各層級對應的標籤 (Labels)：Level 1 = Area、Level 2 = Unit…"),
    "AreaViews": ("階層", "廠區階層檢視定義：ViewType U=使用者組態資料夾 / M=主廠區階層，MaxLevels 最大層數，Permissions 權限"),
    "Assets": ("資產", "資產主檔（GUID）：Discriminator 1=實體裝置、2=虛擬裝置；每台 Devices 對應一筆 DeviceAssets"),
    "AtomicTasks": ("專案", "專案工作項（Projects 底下的單一任務，關聯 Asset）"),
    "BlockAsgms": ("位號", "位號↔區塊指派歷史：ExtBlockTag 指派到 BlockKey 的期間 (EventIdIn→EventIdOut)；EventIdDayOut=49710 表示目前仍有效"),
    "BlockData": ("參數", "裝置參數歷史值：每個 Block 在某事件時刻 (EventIdDay/Fraction) 的每個參數值（二進位 ParamData，依 ParamDataType 解碼）"),
    "Blocks": ("裝置", "區塊主檔：每台裝置一筆裝置層級區塊 (BlockIndex=0, BlockType='')，FF 裝置另有 R/T/F 區塊"),
    "CalStatus": ("校正", "每台裝置的校正狀態：最後校正/下次到期 (Day/Fraction) 與是否通過；本廠全部為 0（未使用）"),
    "Components": ("階層", "把其他資料表的列 (TableName+TableKey) 掛到廠區階層節點 (AreaId)；本廠只掛了使用者組態 NamedConfigs 到 -4 Standard Configurations"),
    "DevRevExtProperty": ("型號", "裝置版本的擴充屬性 (如 PROFIBUS GsdId)"),
    "DeviceAlertDesc": ("警報", "各裝置型號版本 (AmsDevRevId) 可能發出的警報定義：AlertId(位元遮罩十六進位字串)、描述、AlertTypeId"),
    "DeviceAlertReoccurFilter": ("警報", "重複發生警報的抑制過濾紀錄 (SuppressionPeriod)"),
    "DeviceAssets": ("資產", "Devices.DeviceKey ↔ Assets.AssetId(GUID) 對照，安全性/Entity Framework 檢視以 GUID 識別裝置"),
    "DeviceCategories": ("型號", "裝置類別 = 主類別 (MajorDeviceCategories) × 次類別 (MinorDeviceCategories) 組合"),
    "DeviceHealth": ("健康", "裝置健康度紀錄（未使用）"),
    "DeviceHealthMonitor": ("健康", "裝置健康度監視期間（未使用）"),
    "DeviceHealthSnapshots": ("健康", "裝置健康度每日快照（未使用）"),
    "DeviceLocation": ("裝置", "裝置在網路上的實體位置：AmsPath (net!伺服器!網路!位址)、HostPath、HostTag、IdentStatus(1=已識別)、SisStatus、LatencyFactor"),
    "DeviceMonitorList": ("警報", "Alert Monitor 監視名單（哪些裝置被輪詢、頻率）；本廠為空 → 未啟用裝置監視"),
    "DeviceProtection": ("安全", "個別裝置寫入保護 (Device Protection) 設定；本廠為空"),
    "DeviceProtocols": ("代碼", "通訊協定代碼：0 Unknown、1 HART、2 Conventional、3 FF、4 PROFIBUS-DP、5 PROFIBUS-PA"),
    "DeviceRevisions": ("型號", "裝置型號版本 (Device Revision)：型號 + 版本號 + 類別；BlockData 的 DD 參數命名依此"),
    "DeviceTypes": ("型號", "裝置型號 (Device Type)：製造商協定組合 + 型號代碼 (DeviceType 數字) + 名稱"),
    "Devices": ("裝置", "裝置主檔：AmsDeviceId(GUID)、Identifier(序號/DeviceID)、ProtocolRevision(HART 版本)、DispositionId、AmsDeviceTag"),
    "Dispositions": ("代碼", "裝置處置狀態：0 Unknown、1 Assigned(已安裝)、2 Spare、3 Retired、4 don't use、5 Deleted"),
    "Domains": ("安全", "Windows 網域（HMI、AMS1SVR 本機、NullDomain）供使用者/群組主體歸屬"),
    "EventCategories": ("代碼", "事件類別代碼 (-1~99)：Field change(28)、Device synch(43-45)、Log In/Out(46/47)、Alert Set/Clear(20/21)…"),
    "EventLog": ("事件", "稽核軌跡/事件總帳：每筆事件的時間 (UTC)、使用者、電腦 (IP 整數)、區塊、來源程式、Type、Category、描述"),
    "ExtBlockTags": ("位號", "AMS 位號 (Tag) 主檔：ExtBlockTag 名稱、描述、指派的測試定義 (校正方案)"),
    "ExtDevAlertDescProp": ("警報", "警報定義的擴充屬性 (如 AlertMonitorDefault=ENABLED)"),
    "ExtDeviceAlertDesc": ("警報", "警報定義的 DD 說明文字與延伸說明文字（多數為空）"),
    "Grants": ("安全", "權限授與：主體 (PrincipalId) 在某廠區範圍 (PlantLocationId) 擁有某權限 (PrivilegeId)；全部 GUID"),
    "Grants_NetworkLocation": ("安全", "以網路節點為範圍的權限授與（未使用）"),
    "GroupPrincipalWindowsUserPrincipal": ("安全", "Windows 使用者 ↔ 群組成員關係（本廠為空：使用者權限皆直接授與）"),
    "Hierarchies": ("階層", "廠區/組態階層節點：AreaId、上層、層級、名稱、AreaIdentifier(GUID = PlantLocations.Id)；-99 為根"),
    "HostDeviceDefinition": ("網路", "主機(DeltaV/PROFIBUS)裝置定義與 GSD（未使用）"),
    "HostTagParams": ("組態", "主機位號參數（未使用）"),
    "InstantiableBlockAsgms": ("組態", "FF 可實例化功能區塊指派（未使用）"),
    "InstantiableConfigBlocks": ("組態", "FF 可實例化功能區塊定義（未使用）"),
    "InstantiableConfigData": ("組態", "FF 可實例化功能區塊參數資料（未使用）"),
    "Labels": ("階層", "階層層級標籤：3=Level 1、5=Level 2"),
    "MajorDeviceCategories": ("型號", "裝置主類別（Pressure、Temperature、Valve、Flow…共 28 種）"),
    "Manufacturers": ("型號", "製造商名稱 (218 家)"),
    "MfrProtocols": ("型號", "製造商 × 協定 組合，MfrId 為 HART/FF 製造商代碼 (如 Rosemount=38)"),
    "MinorDeviceCategories": ("型號", "裝置次類別 (84 種)"),
    "MobileDeviceEventLog": ("行動", "Trex 手持器同步進來的事件對照（未使用）"),
    "MobileDeviceTypes": ("代碼", "行動裝置類型：0 Trex Handheld"),
    "MobileDevices": ("行動", "已登錄的 Trex 手持器（本廠無）"),
    "NamedConfigAsgms": ("組態", "具名組態指派到位號/區塊 (HostTag/ConfigKey/BlockKey) 與最後傳送時間（未使用）"),
    "NamedConfigAssets": ("組態", "具名組態的資產 GUID（未使用）"),
    "NamedConfigBlocks": ("組態", "具名組態 (範本/使用者組態) 的區塊結構：ConfigKey × BlockIndex × BlockType(R/T/F/'')"),
    "NamedConfigData": ("組態", "具名組態的參數值 (範本預設值/使用者組態值)，格式同 BlockData；ValueMode h=已設定, o=關閉(未包含)"),
    "NamedConfigs": ("組態", "具名組態主檔：ConfigType T=範本(Template)、C=特性(Characteristics)、S=(H275 手持器範本)；H275=1 表示來自 375/475 手持器格式"),
    "NetworkHierarchies": ("網路", "實體網路階層 (hierarchyid)，本廠僅根節點"),
    "NetworkHierarchiesData": ("網路", "網路節點附加屬性（未使用）"),
    "NetworkInfo": ("網路", "AMS 網路定義 (20 個)：Mux Network (HART 多工器)、FF 網路…；NetworkName 對應 GE Mark VIe 的 I/O 模組名"),
    "NetworkInfoProperty": ("網路", "各網路的設定屬性 (MaxInCommObject、Protocol Type、Polling…)"),
    "NotifyQ": ("系統", "伺服器內部通知佇列（暫存，通常為空）"),
    "PermissionClassification": ("代碼", "權限分類：0 SIS、1 BPCS、2 System、3 Configuration"),
    "PermissionGroups": ("安全", "權限群組 (User Management、Calibration、ValveLink SNAP-ON…共 15 組)"),
    "PermissionListPermission": ("安全", "權限清單 ↔ 權限（未使用）"),
    "PlantLocations": ("安全", "廠區範圍 (Scope) 基底表 (GUID)，8 筆 = Hierarchies 的 8 個節點"),
    "PlantLocations_Scope": ("安全", "廠區範圍名稱：Site-wide、Unassigned、Manufacturer、System、User/Standard/Migrated/Handheld Configurations"),
    "PlantLocations_ScopeList": ("安全", "複合範圍清單（未使用）"),
    "PlantServer": ("網路", "廠區伺服器 (AMS1SVR) 與 Alert Monitor 是否啟用"),
    "Policies": ("行動", "Trex 同步政策 (TrexSync)"),
    "PoliciesAsgms": ("行動", "政策指派到行動裝置（未使用）"),
    "PolicyProperties": ("行動", "同步政策細項 (AuditTrail、DeviceConfigs 等 Enable/Disable)"),
    "PolicyTypes": ("代碼", "政策類型：0 TrexSync"),
    "Principals": ("安全", "安全主體基底表 (GUID)：使用者、群組、標準使用者"),
    "Principals_GroupWindowsPrincipal": ("安全", "Windows 群組主體（System Admin、Read-Only、Maintenance、Configuration）"),
    "Principals_StandardUserPrincipal": ("安全", "AMS 內建標準使用者 (AmsServiceUser、FS.AMS1SVR、install、PS.AMS1SVR)"),
    "Principals_UserWindowsPrincipal": ("安全", "Windows 使用者主體 (Admin1、GEAdmin、u675532、u120396…)：Status 1=啟用"),
    "Principals_WindowsPrincipal": ("安全", "Windows 主體 SID"),
    "Privileges": ("安全", "權限基底表 (GUID)"),
    "Privileges_Permission": ("安全", "權限定義 (46 項)：名稱、說明、分類 (SIS/BPCS/System/Configuration)、所屬群組"),
    "Privileges_PermissionList": ("安全", "複合權限清單（未使用）"),
    "ProjectDeviceHealthSnapshots": ("專案", "專案 ↔ 健康度快照（未使用）"),
    "Projects": ("專案", "專案 (未使用)"),
    "RouteFolders": ("校正", "校正路線資料夾（未使用）"),
    "RouteTags": ("校正", "校正路線內的位號順序與校正器下載狀態（未使用）"),
    "Routes": ("校正", "校正路線（未使用）"),
    "ScopeListScope": ("安全", "範圍清單 ↔ 範圍（未使用）"),
    "SecurityComponent": ("安全", "安全元件 (AMS Device Manager)"),
    "SecurityType": ("代碼", "安全物件建立類型：0 System、1 User-Defined"),
    "ServiceReasons": ("校正", "校正服務原因：1 Routine、2 Not Given"),
    "SnapOnData": ("裝置", "SNAP-ON/應用程式附加資料：本廠為 AmsDeviceManager 存的 XML (UTF-16) 區塊，DataType 1/3，例如裝置狀態/校正資訊"),
    "SnapOnDataOwners": ("代碼", "SnapOnData 擁有者：1 AmsDeviceManager"),
    "StationProperty": ("系統", "工作站/伺服器屬性 (ALARM PollingFactor)"),
    "SystemDefaults": ("系統", "系統預設值：警報自動抑制、校正 (FC_*) 設定、GlobalDeviceProtection、SyncDbOnDeviceAccess"),
    "TestDefAsgms": ("校正", "位號 ↔ 測試定義(校正方案) 指派歷史；EventIdDayOut=49710 表示目前有效"),
    "TestDefPoints": ("校正", "測試定義的測試點 (0/50/100%)"),
    "TestDefPointsHistory": ("校正", "測試點歷史版本"),
    "TestDefinition": ("校正", "測試定義(校正方案)：-1 Default Field Device、-2 Default External Lab、-3 Default Flow Verification"),
    "TestDefinitionHistory": ("校正", "測試定義歷史版本"),
    "TestResultAFAL": ("校正", "校正結果 As-Found/As-Left 誤差 (未使用)"),
    "TestResultPoints": ("校正", "校正結果各測試點 (未使用)"),
    "TestResults": ("校正", "校正結果主檔 (未使用)"),
    "Users": ("事件", "事件使用者 (EventLog.UserKey)：-1 None、0 Plant Server、HMI\\帳號、PS./FS.AMS1SVR 服務帳號"),
}

# ----------------------------------------------------------------------------
# 欄位中文意義（全域欄位名 → 意義；(表,欄) 覆寫）
# ----------------------------------------------------------------------------
COL_DESC = {
    "EventIdDay": "事件識別-日：OLE 日期序號整數部分 (1899-12-30 起算天數)，與 EventIdFraction 合為事件主鍵",
    "EventIdFraction": "事件識別-小數：當日經過比例 × 2^31（0~2147483647）",
    "EventIdDayOut": "指派結束事件-日；49710 (=2036-02-05) 為「尚未結束/目前有效」哨兵值",
    "EventIdFractionOut": "指派結束事件-小數",
    "EventIdDayIn": "指派開始事件-日",
    "EventIdFractionIn": "指派開始事件-小數",
    "BlockKey": "區塊鍵 (Blocks.BlockKey)；裝置層級區塊 BlockIndex=0",
    "DeviceKey": "裝置鍵 (Devices.DeviceKey)",
    "ExtBlockTagKey": "位號鍵 (ExtBlockTags)",
    "ExtBlockTag": "AMS 位號 (Tag) 名稱",
    "ExtBlockTagDesc": "位號描述",
    "TestDefinitionId": "測試定義(校正方案)鍵；負值為內建預設",
    "Archived": "已封存旗標（BlockData 中 =1 者全為 FF 裝置的型別 3 十六進位容器列；EventLog 全為 0）",
    "ParamKind": "參數種類：P=DD 參數 (Parameter)，D=裝置警報/非 DD 資料 (frsi.DeviceAlarm.*)",
    "ParamName": "參數名稱：HART 為 <名稱>.<DD item id 十六進位>.<sub>.<sub>；FF 為 <item id>:<member>",
    "ValueMode": "值模式：h=歷史/已設定 (history)，o=關閉/未包含 (off)",
    "ParamDataType": "參數資料型別：3 窄字串(ASCII)、4 Long(int32 LE)、6 Float(float32 LE)、8 Time(OLE 日期 double)、9 Binary、12 TString(UTF-16LE 寬字串)；5/7 僅見於範本 (4/8 位元組整數/雙精度，未確認)",
    "ParamDataSize": "ParamData 位元組長度",
    "ParamData": "參數值二進位 (依 ParamDataType 解碼)",
    "ConfigKey": "具名組態鍵 (NamedConfigs)",
    "ConfigName": "組態/範本名稱",
    "ConfigType": "組態類型：T=範本 Template、C=特性 Characteristics (每型號版本一筆)、S=手持器 (H275) 範本",
    "UniversalId": "HART 通用命令版本 (Universal Revision 5/6/7)，對應 Devices.ProtocolRevision",
    "H275": "是否為 375/475 手持器格式範本 (1=是)",
    "LastModified": "最後修改時間 (UTC)",
    "BlockIndex": "區塊索引：0=裝置層級；FF 的 R/T/F 區塊索引",
    "BlockType": "區塊類型：''=裝置層級、R=RESOURCE、T=TRANSDUCER、F=FUNCTION (FF)",
    "DispositionId": "處置狀態 (Dispositions)：1 Assigned、2 Spare、3 Retired…",
    "AmsDevRevId": "裝置型號版本鍵 (DeviceRevisions)",
    "AmsDevTypeId": "裝置型號鍵 (DeviceTypes)",
    "AmsMfrNameId": "製造商鍵 (Manufacturers)",
    "MfrProtocolId": "製造商×協定鍵 (MfrProtocols)",
    "ProtocolId": "協定鍵 (DeviceProtocols)：1 HART、3 FF",
    "MfrId": "HART/FF 製造商代碼 (Manufacturer ID)",
    "DeviceType": "型號代碼 (HART Device Type code；FF 為裝置類型代碼)",
    "DeviceRevision": "裝置版本號 (Device Revision)",
    "DeviceCategoryId": "裝置類別鍵",
    "MajorDeviceCategoryId": "主類別鍵",
    "MinorDeviceCategoryId": "次類別鍵",
    "AmsDeviceId": "裝置 GUID",
    "Identifier": "裝置識別碼：HART 為 Device ID (序號)，FF 為 32 字元 Device ID",
    "ProtocolRevision": "HART 通用命令版本 (5/6/7)；FF 裝置為 0",
    "AmsDeviceTag": "AMS 位號 (與 ExtBlockTags 同步)",
    "AssetId": "資產 GUID",
    "Discriminator": "1=實體裝置、2=虛擬裝置 (AmsSp_CreateDeviceAsset_1 註解)",
    "Tag": "資產位號 (僅虛擬裝置填)",
    "PlantServerKey": "廠區伺服器鍵 (PlantServer)",
    "PlantServerId": "廠區伺服器機器名稱",
    "NetworkInfoKey": "網路鍵 (NetworkInfo)；-1 未知",
    "NetworkId": "網路識別 (Mux Network n / FF Network n)",
    "NetworkName": "網路名稱 (本廠為 Mark VIe I/O 模組/機櫃名)",
    "NetworkKindAsString": "網路種類 (Mux Network / FF…)",
    "AmsPath": "AMS 路徑：net!伺服器!網路!位址!通道 (以 ! 分隔)",
    "HostPath": "主機端路徑 (多工器/卡件/通道位址)",
    "HostTag": "主機端讀到的位號 (HART Tag)",
    "IdentStatus": "識別狀態：1=identified 已識別、0=unknown (AmsUdf_DevBlkIdentStatusAsString)",
    "SisStatus": "SIS 安全儀控狀態：0/NULL=BPCS、1 或 2=SIS 裝置 (AmsVw_EF_Device Classification)",
    "LatencyFactor": "通訊延遲因子 (smallint)",
    "EventTime": "事件時間 (UTC；GMT，見 AmsSp_LogEventSummary 註解)",
    "UserKey": "使用者鍵 (Users)",
    "UserName": "使用者名稱 (Windows 網域\\帳號 或內建帳號)",
    "ComputerId": "電腦 IPv4 位址以 host-order 32 位元有號整數儲存 (a.b.c.d → a<<24|b<<16|c<<8|d)",
    "EventCode": "事件碼 (永遠為 0，AmsSp_LogEventSummary 註解)",
    "Source": "事件來源程式 (Server、AMS Device Manager Application、AmsMergeDoc、Database Maintenance…)",
    "Type": "事件型別 (EventLog)：1 組態變更、2 校正/測試方案、3 資料庫維護、4 應用/系統、5 狀態警報、6 範本/裝置型別建立(不列入稽核)、8 裝置掃描同步 (DBW_ET_DEVICE_SCAN)、9 不列入稽核",
    "Category": "事件類別 (EventCategories)",
    "Description": "描述",
    "OtherBufLen": "Other 欄位長度",
    "Other": "其他資料 (AlertId 等)",
    "MoreDetail": "詳細內容 (參數變更前後值等)",
    "AlertId": "警報識別：HART 標準狀態位元遮罩 16 位十六進位字串 (如 0100000000000000=PV out of limits)，或 DD 定義字串",
    "AlertTypeId": "警報種類 (AlertTypes)",
    "AlertDescId": "警報描述鍵 (DeviceAlertDesc)",
    "AlertState": "1=Set (作用中)、0=Clear",
    "AckState": "1=已確認",
    "SetCount": "重複發生次數",
    "AlertSource": "警報來源：AMSDMHostProcess 或 SNAP-ON 名稱 (AmsUdf_GetAlertSource)",
    "AlertTime": "警報時間",
    "Enabled": "是否啟用",
    "AreaId": "階層節點鍵 (Hierarchies)；-99 根、-1 Site-wide、-2 Unassigned、-3 User Configurations",
    "ParentAreaId": "上層節點鍵",
    "ViewAreaId": "所屬檢視 (AreaViews)",
    "AreaLevel": "層級 (0 起)",
    "AreaName": "節點名稱",
    "LabelId": "層級標籤 (Labels)",
    "AreaIdentifier": "節點 GUID (= PlantLocations.Id，安全範圍)",
    "ViewType": "U=使用者組態資料夾、M=主廠區階層",
    "MaxLevels": "最大層數",
    "Required": "必要",
    "Balanced": "各分支層數是否需相等",
    "Permissions": "權限標記 (ARO,RO)",
    "TableName": "被掛載的資料表名",
    "TableKey": "被掛載資料列的鍵",
    "Name": "名稱",
    "Title": "標題",
    "Id": "GUID 主鍵",
    "PrincipalId": "安全主體 GUID (使用者/群組)",
    "PrivilegeId": "權限 GUID (Privileges_Permission)",
    "PlantLocationId": "廠區範圍 GUID (PlantLocations_Scope / Hierarchies.AreaIdentifier)",
    "Classification": "權限分類 (PermissionClassification)：0 SIS、1 BPCS、2 System、3 Configuration",
    "PermissionGroupId": "權限群組 GUID",
    "ComponentId": "安全元件 GUID",
    "DomainId": "網域 GUID (Domains)",
    "BindingMode": "綁定模式",
    "CreateType": "建立類型 (SecurityType)：0 System、1 User-Defined",
    "Status": "1=啟用、0=停用 (AmsSp_HasPermission)",
    "State": "狀態",
    "Sid": "Windows SID",
    "FullName": "全名",
    "SSOID": "單一登入 ID",
    "UserIdentifier": "使用者識別",
    "DevLastCalibrationDay": "最後校正日 (EventIdDay 格式)",
    "DevLastCalibrationFraction": "最後校正小數",
    "DevNextCalibrationDueDay": "下次校正到期日",
    "DevNextCalibrationDueFraction": "下次校正到期小數",
    "DevPassedLastCalibration": "最後校正是否通過",
    "SnapOnDataId": "流水號",
    "SnapOnDataOwnerId": "擁有者 (SnapOnDataOwners)",
    "SnapOnDataNote": "附註 (本廠為 28 位十六進位識別碼)",
    "SnapOnDataType": "資料類型 (1、3；內容為 UTF-16 XML)",
    "SnapOnData": "二進位資料 (image)",
    "Parameter": "參數名",
    "Data": "值",
    "Major": "主版本",
    "Minor": "次版本",
    "SchemaDate": "結構日期",
    "SchemaNotes": "變更說明",
    "PolicyKey": "政策鍵",
    "PolicyTypeId": "政策類型",
    "Enable": "啟用",
    "Value": "值",
    "MobileDevKey": "行動裝置鍵",
    "MobDevTypeId": "行動裝置類型",
    "Acknowledged": "已確認",
    "EventSyncTime": "同步時間",
    "NodeName": "節點名稱",
    "NodeKind": "節點種類",
    "NodeHierarchyId": "hierarchyid 路徑",
    "NodeLevel": "層級",
    "NetworkNodeId": "網路節點 GUID",
    "NetworkInfoPropKey": "流水號",
    "NetworkInfoPropertyKey": "屬性名",
    "NetworkInfoPropertyValue": "屬性值",
    "StationPropertyKey": "流水號",
    "StationInfoPropertySection": "區段",
    "StationInfoPropertyKey": "屬性名",
    "StationInfoPropertyValue": "屬性值",
    "AlertMonitorEnabled": "Alert Monitor 是否啟用",
    "MonitorGroup": "監視群組",
    "Frequency": "輪詢頻率",
    "DVMEnabled": "裝置監視啟用",
    "ExtPropertyName": "擴充屬性名",
    "ExtPropertyValue": "擴充屬性值",
    "ExtPropertyId": "流水號",
    "DDHelpText": "DD 說明文字",
    "ExtendedHelpText": "延伸說明",
    "Uid": "識別字串",
    "AlertTypeName": "警報種類名稱",
    "CategoryDesc": "類別描述",
    "ServiceId": "服務原因",
    "ServiceDesc": "服務原因描述",
    "LabelName": "標籤名",
    "TestPointId": "測試點序",
    "DefTestPoint": "測試點 (%)",
    "DefCalibrationInterval": "校正週期",
    "DefIntervalUnits": "週期單位",
    "CriticalService": "關鍵服務",
    "DefNumberOfTestPoints": "測試點數",
    "ExpiredTime": "到期時間",
    "DPEnabled": "裝置保護啟用",
    "StartTime": "開始時間",
    "EndTime": "結束時間",
    "CompletionTime": "完成時間",
    "Priority": "優先順序",
    "ProjectId": "專案鍵",
    "TaskId": "任務鍵",
    "GroupPath": "群組路徑 (未使用，全為 NULL)",
    "NotifyKey": "通知鍵",
    "NotifyType": "通知類型 (6 AlertList 更新、7 DeviceMonitorList 更新、8 PlantServer AlertMonitor 更新…)",
    "NotifyData": "通知資料",
    "UpdateCount": "更新次數",
    "InitializeTime": "初始化時間",
    "LastUpdateTime": "最後更新時間",
    "LastAddTime": "最後新增時間",
    "SuppressionPeriod": "抑制期間",
    "InstantiableBlockKey": "可實例化區塊鍵",
    "DDItemId": "DD 項目 ID",
    "UtcDateTimeIn": "生效 (UTC)",
    "UtcDateTimeOut": "失效 (UTC)；9999-12-31 為目前有效",
    "ParamLabel": "參數標籤",
    "LastTransferred": "最後傳送",
    "ConfigStatus": "組態狀態",
    "HostDeviceId": "主機裝置 ID",
    "DeviceDefinition": "裝置定義",
    "GSDId": "PROFIBUS GSD ID",
    "RouteId": "路線鍵",
    "FolderId": "資料夾鍵",
    "FolderName": "資料夾名",
    "RouteName": "路線名",
    "RouteStatus": "路線狀態",
    "TestResultId": "校正結果鍵",
    "TechnicianId": "技師 (Users)",
    "WorkOrder": "工單",
    "MaxError": "最大誤差",
    "ZeroError": "零點誤差",
    "SpanError": "跨距誤差",
    "LinearityError": "線性誤差",
    "HysteresisError": "遲滯誤差",
    "Input": "輸入",
    "Output": "輸出",
    "Error": "誤差",
    "DeviceHealthId": "健康度鍵",
    "HealthMonitorId": "健康監視鍵",
    "DevHealthSnapshotId": "快照鍵",
    "DeviceId": "裝置鍵 (Devices.DeviceKey)",
    "Date": "日期",
    "Time": "時間",
}
COL_DESC_TBL = {
    ("Devices", "Identifier"): "裝置識別碼：HART=Device ID 十進位 (如 15015766)，FF=32 字元 Device ID；'Default' 為 -1 哨兵列",
    ("Blocks", "DispositionId"): "區塊處置 (本廠全為 0，實際處置看 Devices.DispositionId)",
    ("DeviceTypes", "DeviceType"): "型號代碼：HART Device Type code (256=Pressure 通用…) 或製造商專屬代碼",
    ("DeviceAlertDesc", "AmsDevRevId"): "所屬型號版本；-1 = HART 標準 (通用) 警報",
    ("NamedConfigs", "AmsDevRevId"): "所屬型號版本 (DeviceRevisions)",
    ("Users", "UserName"): "事件使用者名稱：HMI\\xxx Windows 帳號、PS.AMS1SVR/FS.AMS1SVR 服務帳號、admin=隨附範本作者",
    ("EventLog", "Other"): "其他：警報事件時為 AlertId 等附加資訊 (nvarchar；稽核程序以 varbinary 回傳)",
    ("Hierarchies", "AreaId"): "節點鍵：-7 System、-6 Handheld、-5 Migrated、-4 Standard Configs、-3 User Configs、-2 Unassigned、-1 Site-wide、1 Manufacturer (根 -99 不存在於表中)",
    ("AlertList_UpdateTracking", "AlertState"): "追蹤列識別 (nchar)",
    ("TestDefinition", "Type"): "測試類型：2 流量驗證、5 外部實驗室、99 現場儀器",
    ("TestDefPoints", "Type"): "測試點類型",
    ("TestResults", "Type"): "測試類型",
    ("Policies", "Name"): "政策名",
    ("SnapOnData", "SnapOnDataType"): "資料類型：1 (1,562 筆)、3 (227 筆)；內容皆為 UTF-16 XML",
}

# ----------------------------------------------------------------------------
# 模組名稱字元 → 中文 glossary（用於自動中文摘要）
# ----------------------------------------------------------------------------
PREFIX_CAT = [
    ("AmsSp_AL_", "警報清單 (Alert List)"), ("AmsSp_ALTrack_", "警報清單追蹤"),
    ("AmsSp_UM_", "使用者管理 (User Manager)"), ("AmsSp_EF_", "Entity Framework 資料存取"),
    ("AmsSp_Operation_", "操作"), ("AmsSp_DevBlk_", "裝置區塊"), ("AmsSp_Device_", "裝置"),
    ("AmsSp_Devices_", "裝置"), ("AmsSp_BulkTransfer_", "批次傳送"), ("AmsSp_DiagAnalysis_", "診斷分析"),
    ("AmsSp_AuditTrail", "稽核軌跡"), ("AmsSp_NamedConfig", "具名組態"), ("AmsSp_Blocks_", "區塊"),
    ("AmsSp_Calibration", "校正"), ("AmsSp_Route", "校正路線"), ("AmsSp_TestDef", "測試定義"),
    ("AmsSp_Mobile", "行動裝置 (Trex)"), ("AmsSp_Project", "專案"), ("AmsSp_Health", "健康度"),
    ("AmsSp_Notify", "通知"), ("AmsSp_Grant", "權限授與"), ("AmsSp_Has", "權限檢查"), ("AmsSp_Check", "權限檢查"),
    ("AmsSp_Security", "安全"), ("AmsSp_Hierarch", "階層"), ("AmsSp_Network", "網路"), ("AmsSp_PsNetwork", "網路"),
    ("AmsSp_Get", "查詢"), ("AmsSp_Add", "新增"), ("AmsSp_Create", "建立"), ("AmsSp_Update", "更新"),
    ("AmsSp_Set", "設定"), ("AmsSp_Delete", "刪除"), ("AmsSp_Remove", "移除"), ("AmsSp_Fix", "修復"),
    ("AmsSp_Log", "記錄事件"), ("AmsSp_Assign", "指派"), ("AmsSp_Sync", "同步"), ("AmsSp_Read", "讀取"),
    ("AmsSp_", "預存程序"),
    ("AmsVw_EF_", "Entity Framework 檢視"), ("AmsVw_Monitoring_", "監視檢視"), ("AmsVw_Management_", "管理檢視"),
    ("AmsVw_Security_", "安全檢視"), ("AmsVw_UM_", "使用者管理檢視"), ("AmsVw_Calibration_", "校正檢視"),
    ("AmsVw_Projects_", "專案檢視"), ("AmsVw_", "檢視"),
    ("AmsUdf_", "使用者定義函數"), ("AmsTr_", "觸發器"), ("Id", "舊版檢視"),
]
GLOSS = [
    ("AuditTrailSummary", "稽核軌跡摘要"), ("AuditTrail", "稽核軌跡"), ("AlertList", "警報清單"), ("AlertLog", "警報記錄"),
    ("AlertMonitor", "警報監視"), ("AlertFilter", "警報過濾"), ("AlertDesc", "警報描述"), ("Alerts", "警報"), ("Alert", "警報"),
    ("DeviceMonitorList", "裝置監視名單"), ("DeviceProtection", "裝置保護"), ("DeviceHealth", "裝置健康度"),
    ("DeviceLocation", "裝置位置"), ("DeviceTagLocation", "裝置位號位置"), ("DeviceTag", "裝置位號"), ("DeviceType", "裝置型號"),
    ("DeviceRev", "裝置版本"), ("DeviceModel", "裝置型號"), ("DeviceSnapshot", "裝置快照"), ("DeviceAsset", "裝置資產"),
    ("Devices", "裝置"), ("Device", "裝置"), ("DevBlk", "裝置區塊"), ("DevLvl", "裝置層級"), ("DevTag", "裝置位號"),
    ("NamedConfigs", "具名組態"), ("NamedConfig", "具名組態"), ("UserConfiguration", "使用者組態"), ("UserConfig", "使用者組態"),
    ("Configuration", "組態"), ("Config", "組態"), ("Template", "範本"), ("Characteristics", "特性"),
    ("BlockData", "區塊參數"), ("BlockAsgm", "區塊指派"), ("BlockTag", "區塊位號"), ("Blocks", "區塊"), ("Block", "區塊"),
    ("HistoricalConfigList", "歷史組態清單"), ("ConfigChangeHistory", "組態變更歷史"), ("History", "歷史"),
    ("PhysicalNetworkNode", "實體網路節點"), ("NetworkNode", "網路節點"), ("NetworkHierarch", "網路階層"),
    ("NetworkInfo", "網路資訊"), ("Networks", "網路"), ("Network", "網路"), ("Hierarchies", "階層"), ("Hierarchy", "階層"),
    ("PlantLocation", "廠區位置"), ("PlantServer", "廠區伺服器"), ("Location", "位置"), ("Area", "區域"),
    ("PermissionList", "權限清單"), ("Permission", "權限"), ("Privilege", "權限"), ("Principal", "主體"), ("Grant", "授與"),
    ("GroupWindows", "Windows 群組"), ("UserWindows", "Windows 使用者"), ("Windows", "Windows"), ("Group", "群組"),
    ("Users", "使用者"), ("User", "使用者"), ("Domain", "網域"), ("Scope", "範圍"), ("Security", "安全"),
    ("MobileDevice", "行動裝置"), ("Mobile", "行動"), ("Policies", "政策"), ("Policy", "政策"), ("Trex", "Trex"),
    ("Calibration", "校正"), ("Calibrator", "校正器"), ("TestDefinition", "測試定義"), ("TestDef", "測試定義"), ("TestResult", "測試結果"),
    ("TestEquipment", "測試設備"), ("TestScheme", "測試方案"), ("Route", "路線"), ("ExternalLab", "外部實驗室"),
    ("Projects", "專案"), ("Project", "專案"), ("Task", "任務"), ("Snapshot", "快照"), ("Health", "健康度"),
    ("SnapOnData", "SNAP-ON 資料"), ("SnapOn", "SNAP-ON"), ("Asset", "資產"), ("Virtual", "虛擬"), ("Real", "實體"), ("Future", "未來"),
    ("EventLog", "事件記錄"), ("EventSummary", "事件摘要"), ("Events", "事件"), ("Event", "事件"), ("Notification", "通知"), ("Notify", "通知"),
    ("Manufacturer", "製造商"), ("Protocol", "協定"), ("Categories", "類別"), ("Category", "類別"), ("Hart", "HART"), ("HART", "HART"), ("FF", "FF"),
    ("DeviceDescription", "裝置描述"), ("Descriptor", "描述子"), ("SoftwareRevision", "軟體版本"), ("Revision", "版本"),
    ("Parameters", "參數"), ("Param", "參數"), ("Value", "值"), ("Mode", "模式"), ("Type", "型別"), ("Info", "資訊"), ("Details", "明細"),
    ("Tags", "位號"), ("Tag", "位號"), ("Path", "路徑"), ("Key", "鍵"), ("Id", "識別"), ("Name", "名稱"), ("List", "清單"), ("All", "全部"),
    ("Current", "目前"), ("Last", "最後"), ("Latest", "最新"), ("Sync", "同步"), ("Time", "時間"), ("DateTime", "日期時間"), ("Date", "日期"),
    ("Status", "狀態"), ("Sis", "SIS"), ("Ident", "識別"), ("Disposition", "處置"), ("Dispos", "處置"), ("Assign", "指派"), ("Asgms", "指派"), ("Asgm", "指派"),
    ("Commission", "投用"), ("DeCommission", "退役"), ("Rename", "更名"), ("Move", "移動"), ("Import", "匯入"), ("Export", "匯出"),
    ("Backup", "備份"), ("Restore", "還原"), ("Purge", "清除"), ("Archive", "封存"), ("Merge", "合併"), ("Dup", "重複"), ("Fix", "修復"),
    ("Version", "版本"), ("Db", "資料庫"), ("Password", "密碼"), ("Login", "登入"), ("Startup", "啟動"), ("Initialize", "初始化"),
    ("Process", "處理"), ("Track", "追蹤"), ("Filter", "過濾"), ("Enable", "啟用"), ("Disable", "停用"), ("Suppress", "抑制"),
    ("Insert", "插入"), ("Delete", "刪除"), ("Remove", "移除"), ("Update", "更新"), ("Add", "新增"), ("Create", "建立"), ("Get", "取得"),
    ("Set", "設定"), ("Put", "寫入"), ("Read", "讀取"), ("Check", "檢查"), ("Has", "是否有"), ("Is", "是否"), ("Build", "建構"),
    ("Convert", "轉換"), ("Format", "格式化"), ("Split", "拆分"), ("Count", "計數"), ("From", "自"), ("To", "至"), ("By", "依"), ("For", "供"),
    ("With", "含"), ("And", "與"), ("Of", "之"), ("In", "內"), ("Per", "每"), ("Stmt", "SQL 陳述式"), ("String", "字串"), ("Binary", "二進位"),
    ("Int", "整數"), ("Dbl", "雙精度"), ("Utc", "UTC"), ("Local", "本地"), ("Display", "顯示"), ("Full", "完整"), ("Tree", "樹"),
    ("Child", "子"), ("Parent", "父"), ("Unit", "機組"), ("Equip", "設備"), ("Cntl", "控制"), ("Node", "節點"), ("Physical", "實體"),
    ("Controller", "控制器"), ("Station", "工作站"), ("Property", "屬性"), ("Properties", "屬性"), ("Data", "資料"), ("Detail", "明細"),
    ("Reoccur", "重複發生"), ("Exceptions", "例外"), ("Exception", "例外"), ("Displayable", "可顯示"), ("Uid", "UID"), ("Desc", "描述"),
    ("Options", "選項"), ("Defaults", "預設值"), ("System", "系統"), ("Server", "伺服器"), ("Plant", "廠區"), ("Site", "廠區"), ("Wide", "全域"),
    ("Code", "代碼"), ("Instantiable", "可實例化"), ("Func", "功能"), ("Instance", "實例"), ("Record", "紀錄"), ("Char", "特性"),
    ("NonDD", "非 DD"), ("DD", "DD"), ("Universal", "通用"), ("Extension", "擴充"), ("Ext", "擴充"), ("Prop", "屬性"), ("Reason", "原因"),
    ("Total", "總計"), ("Point", "點"), ("Projected", "預計"), ("Due", "到期"), ("Interval", "週期"), ("Schedule", "排程"),
    ("Component", "元件"), ("Label", "標籤"), ("View", "檢視"), ("Level", "層級"), ("Lvl", "層級"), ("Frequency", "頻率"),
    ("Sid", "SID"), ("Ps", "廠區伺服器"), ("Am", "警報監視"), ("AT", "稽核軌跡"), ("ATTS", "稽核軌跡時間序列"), ("LV", "ValveLink"),
]


TOKEN_ZH = {}
for _en, _zh in GLOSS:
    TOKEN_ZH.setdefault(_en.lower(), _zh)
TOKEN_ZH.update({
    "been": "已", "updated": "更新", "added": "新增", "deleted": "刪除", "changed": "變更", "dev": "裝置", "protect": "保護",
    "cal": "校正", "report": "報表", "bulk": "批次", "transfer": "傳送", "names": "名稱", "search": "搜尋", "select": "選取",
    "gen": "產生", "ex": "匯出", "vl": "ValveLink", "services": "服務", "locations": "位置", "gateway": "閘道", "nodes": "節點",
    "instances": "實例", "types": "型號", "revisions": "版本", "manufacturers": "製造商", "protocols": "協定", "tags": "位號",
    "keys": "鍵", "params": "參數", "values": "值", "blocks": "區塊", "devices": "裝置", "areas": "區域", "units": "機組",
    "all": "全部", "for": "供", "with": "含", "by": "依", "from": "自", "to": "至", "of": "之", "in": "內", "per": "每", "and": "與",
    "get": "取得", "add": "新增", "set": "設定", "put": "寫入", "is": "是否", "has": "是否有", "check": "檢查", "fix": "修復",
    "dup": "重複", "diag": "診斷", "analyze": "分析", "repair": "修復", "clear": "清除", "definition": "定義", "def": "定義",
    "host": "主機", "tec": "測試設備", "crs": "交叉", "ref": "參照", "schemes": "方案", "scheme": "方案", "equip": "設備",
    "reoccurring": "重複發生", "list": "清單", "item": "項目", "read": "讀取", "write": "寫入", "as": "為", "at": "稽核軌跡",
    "ps": "廠區伺服器", "am": "警報監視", "al": "警報清單", "um": "使用者管理", "ef": "EF", "id": "識別", "ids": "識別",
    "shared": "共用", "ancestor": "上層", "descendant": "下層", "principal": "主體", "account": "帳號", "retired": "退役",
    "ams": "AMS", "db": "資料庫", "sp": "程序", "vw": "檢視", "udf": "函數", "tr": "觸發器", "dates": "日期", "misc": "雜項",
    "commdecomm": "投用/退役", "comm": "投用", "decomm": "退役", "operation": "操作", "operations": "操作", "monitoring": "監視",
    "management": "管理", "security": "安全", "projects": "專案", "calibration": "校正", "snap": "SNAP", "on": "ON", "off": "關閉",
    "alarm": "警報", "alarms": "警報", "ackn": "確認", "ack": "確認", "state": "狀態", "count": "計數", "counts": "計數",
    "rename": "更名", "move": "移動", "copy": "複製", "purge": "清除", "clean": "清理", "up": "", "down": "", "load": "載入",
    "change": "變更", "does": "是否", "exist": "存在", "exists": "存在", "live": "線上", "polling": "輪詢", "crack": "解析", "should": "應", "exclude": "排除", "commissioning": "投用", "history": "歷史", "reportfor": "報表供", "summary": "摘要",
    "trex": "Trex", "sync": "同步", "auth": "授權", "de": "取消", "authorized": "已授權", "authorize": "授權",
})
CAMEL_RE = re.compile(r"[A-Z]{2,}(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|[A-Z]{2,}|\d+")


def zh_from_name(name: str) -> str:
    """將模組名稱拆為 CamelCase token 後逐字對照 glossary（機械式，供索引）；未知字保留英文"""
    base = re.sub(r"^(AmsSp|AmsVw|AmsUdf|AmsTr)_", "", name)
    base = re.sub(r"_\d+$", "", base)
    out = []
    for part in base.split("_"):
        for tok in CAMEL_RE.findall(part):
            zh = TOKEN_ZH.get(tok.lower())
            out.append(zh if zh is not None else tok)
    txt = "".join(out)
    txt = re.sub(r"([A-Za-z])([一-鿿])", r"\1 \2", txt)
    txt = re.sub(r"([一-鿿])([A-Za-z])", r"\1 \2", txt)
    return txt.strip()


# 手寫中文摘要（關鍵模組）
HAND_ZH = {
    "AmsUdf_EventIdDayFractionToDateTime": "EventIdDay/Fraction → datetime：(Day-2) + Fraction/2^31 天；VT_DATE 起點 1899-12-30",
    "AmsUdf_EventTimeAsDblToEventIdDay": "OLE 日期 double → EventIdDay = FLOOR(值)",
    "AmsUdf_EventTimeAsDblToEventIdFraction": "OLE 日期 double → EventIdFraction = int(小數部分×2^31+0.5)",
    "AmsUdf_GetLocalDateTimeFromUtc": "UTC → 伺服器本地時間（以 GETDATE-GETUTCDATE 分鐘差平移）",
    "AmsUdf_DevBlkIdentStatusAsString": "DeviceLocation.IdentStatus 0=unknown、1=identified",
    "AmsUdf_BinaryToInt": "4 位元組 little-endian 二進位 → int（軟體版本等）",
    "AmsUdf_CurrentSoftwareRevision": "取區塊最新 software_revision.0000009E 參數 (BinaryToInt)",
    "AmsUdf_CurrentDescriptor": "取裝置最新 descriptor.000000A5 / NonDDDeviceDescription；型別 12 以 nvarchar 解、3 以 varchar 解",
    "AmsUdf_AlertTypeUidFromParamName": "由參數名 frsi.DeviceAlarm.<AlertTypeUid> 擷取警報種類 UID",
    "AmsUdf_GetHartAlertId": "HART 標準狀態位元 → 16 位十六進位 AlertId (0x01→'0100000000000000' … 0x100→'0001000000000000')",
    "AmsUdf_GetHartAlertDesc": "HART 標準狀態位元 → 英文描述 (PV out of limits、Cold start、Device Not Responding…)",
    "AmsUdf_GetAlertSource": "事件類別 30/31/62/63 (應用/診斷警報) 用事件 Source，其餘為 AMSDMHostProcess",
    "AmsUdf_IsAlertDisplayable": "依 AlertFilterForDevice.Enabled 判斷警報是否顯示",
    "AmsUdf_GetFFBlockName": "BlockType R→RESOURCE、T→TRANSDUCER<idx>、F→FUNCTION<idx>",
    "AmsUdf_GetDevLvlTagAsgm": "由 FF 子區塊事件的 BlockKey+事件時間找出當時裝置層級的 AMS 位號",
    "AmsUdf_GetFormatedMobileDeviceSyncDateTime": "行動裝置同步時間格式化",
    "AmsUdf_GetFullDisplayPath": "NetworkHierarchies hierarchyid → 以 ! 串接的完整顯示路徑",
    "AmsUdf_FormatPhysicalNetworkNodePath": "AMS 路徑 (net!伺服器!網路!…) → DeltaV 實體節點路徑 (僅支援 DeltaV)",
    "AmsUdf_HierarchyStringSplit": "以分隔符拆解階層字串為 (NodeName, NodeLevel) 表",
    "AmsUdf_BuildATStmtForRead": "組合稽核軌跡 (Audit Trail) 讀取用 SQL 陳述式",
    "AmsUdf_BuildATTSStmtForRead": "組合稽核軌跡時間序列讀取用 SQL 陳述式",
    "AmsUdf_BuildLVStmtForRead": "組合 ValveLink 讀取用 SQL 陳述式",
    "AmsVw_BlockTags": "核心檢視：位號 → 製造商/協定/型號/版本/序號/ProtocolRevision/BlockKey (目前指派 BlockAsgms.EventIdDayOut=49710)",
    "AmsVw_DeviceTagLocation": "核心檢視：位號 + 裝置 + 處置 + 區域/機組/設備/控制 + 廠區伺服器 + 網路鍵",
    "AmsVw_DeviceTags": "裝置位號檢視（含類別、SIS、描述）",
    "AmsVw_DeviceLevelBlockKey": "任一 BlockKey → 同裝置 BlockIndex=0 的裝置層級 BlockKey",
    "AmsVw_CurrentTagBlockAsgms": "目前有效的位號↔區塊指派 (EventIdDayOut=49710)",
    "AmsVw_BlockLocation": "區塊所在階層：Area/Unit/Equipment/Control",
    "AmsVw_EF_Device": "EF 裝置檢視：AssetId、型號、序號、是否監視、SIS 分類 (SisStatus 1/2→1)",
    "AmsVw_AlertMonitorStartup": "Alert Monitor 啟動時要載入的監視裝置",
    "IdAllTagView": "舊版：所有位號↔BlockKey 指派（含歷史）",
    "IdLastTagView": "舊版：最後一次位號↔BlockKey 指派",
    "AmsTr_AlertAdded": "AlertLog 插入後 → 更新裝置健康度 (AmsSp_UpdateDeviceHealth_1)",
    "AmsTr_AlertListUpdated": "AlertList 更新後 → 更新追蹤表/健康度",
    "AmsTr_AlertFilterForDeviceUpdated": "AlertFilterForDevice 更新後 → 通知",
    "AmsTr_DeviceMonitorUpdate": "DeviceMonitorList 更新後 → 通知 Alert Monitor",
    "AmsTr_DeviceHealthChanged": "DeviceHealth 變更後 → 專案快照",
    "AmsTr_InsertHierarchies": "Hierarchies 插入後 → 同步 PlantLocations/Scope (安全範圍 GUID)",
    "AmsTr_UpdateHierarchies": "Hierarchies 更新後 → 同步 PlantLocations_Scope 名稱",
    "AmsTr_DeleteHierarchies": "Hierarchies 刪除後 → 刪除對應 PlantLocations/Grants",
    "AmsTr_DeleteNetworkHierarchies": "NetworkHierarchies 刪除後 → 清除 Grants_NetworkLocation",
    "AmsTr_UpdateUsersDomain": "Domains 更名後 → 同步 Users.UserName 前綴",
    "AmsTr_AddDeleteProjectTask": "AtomicTasks 增刪後 → 記錄事件",
    "AmsTr_UpdateProjects": "Projects 更新後 → 記錄事件",
    "AmsTr_DeleteProjectSnapshots": "Projects 刪除後 → 刪除快照",
    "AmsSp_LogEventSummary_2": "寫入單筆事件 (EventLog)：時間為 GMT 字串、ComputerId=IP、Type/Category；警報事件另寫 AlertLog/AlertList",
    "AmsSp_LogEventSummary_1": "寫入單筆事件 (舊版)",
    "AmsSp_EF_LogEventSummary": "寫入單筆事件 (EF 版)",
    "AmsSp_AuditTrailSummary_All_1": "稽核軌跡分頁查詢 (全部)；只列 Type 1~9 但排除 6 與 9",
    "AmsSp_AuditTrailSummary_ByDevice_1": "稽核軌跡分頁查詢 (依裝置)",
    "AmsSp_AuditTrailSummary_ByTag_1": "稽核軌跡分頁查詢 (依位號)",
    "AmsSp_AuditTrail_AllEvents_1": "稽核軌跡所有事件查詢",
    "AmsSp_DevBlk_GetLastSyncTime_1": "取區塊最後同步時間 = EventLog 中 Type=8 (DBW_ET_DEVICE_SCAN) 的最大 EventTime",
    "AmsSp_GetBlockKeyCurrentHartInfo_1": "取 HART tag/message/descriptor 目前值；型別 3 窄字串、12 寬字串，否則回 -2",
    "AmsSp_GetBlockKeyCurrentHartTag_1": "取 HART tag 目前值",
    "AmsSp_AssignDevTag_1": "指派位號到裝置：BlockAsgms 新列 EventIdDayOut=49710 表示目前有效，舊列以事件時間關閉",
    "AmsSp_AssignNewTagTestDef_1": "新位號指派預設測試定義 (TestDefAsgms, 49710 有效)",
    "AmsSp_HasPermission": "檢查使用者對某位號/全廠的權限：以 GUID 常數 (Site-wide 81C7311F…、Unassigned 10F82026…) 為範圍，含群組與 Device Protection 檢查",
    "AmsSp_CheckUserPermission": "檢查使用者 GUID 對某範圍 GUID 是否有某權限 GUID；AmsServiceUser 3044F0E9… 永遠允許",
    "AmsSp_CheckReadPermissionByDevIdentifier": "依裝置識別碼檢查讀取權限：SisStatus>0 需 SIS 讀取權限，否則 BPCS",
    "AmsSp_CreateDeviceAsset_1": "為裝置建立 Assets (Discriminator=1 實體) 與 DeviceAssets",
    "AmsSp_CreateUserConfiguration_1": "建立使用者組態：複製型號範本 (ConfigType T, H275=0) 的區塊結構，新列 ConfigType T、H275=1，掛到 Components",
    "AmsSp_Device_GetCharTemplateName_1": "取 FF 裝置的特性範本名稱 (每型號版本僅一筆 ConfigType='C')",
    "AmsSp_GetNamedConfigParamValueMode_1": "取具名組態參數 ValueMode：'h' history / 'o' off",
    "AmsSp_SetNamedConfigParamValueMode_1": "設定具名組態參數 ValueMode ('h'/'o')",
    "AmsSp_GetNonDDHistoricalConfigList_1": "取非 DD 參數 (ParamKind='D') 歷史；型別 12 (TString) 轉 varbinary 再轉 nvarchar",
    "AmsSp_ReadHARTDeviceDescription_1": "依 MfrId/DeviceType/Revision 讀 descriptor.000000A5 (型別 12 用 varbinary)",
    "AmsSp_AL_ProcessNotifyAlertLogInsert_1": "AlertLog 新增通知處理：事件 Type 必須為 5 (StatusAlert)，類別 20/30/62 = Set、21/31/63 = Clear",
    "AmsSp_AL_GetList_1": "取 Alert Monitor 作用中警報清單（含是否有新增/更新）",
    "AmsSp_DeviceTags_1": "裝置位號清單（BlockAsgms.EventIdDayOut=49710 為目前）",
    "AmsSp_Operation_GetProjectedCalibrationDate_1": "推算下次校正日 (25569 = 1970-01-01 視為未設定)",
    "AmsSp_AddHartDevTypeByCode_1": "依 HART 製造商/型號/版本代碼新增 DeviceTypes/DeviceRevisions",
    "AmsSp_AddDeviceParam_1": "新增 BlockData 一筆參數：型別 12 以 varbinary 存 (UTF-16)，其他直接存",
}

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def yn(v):
    return "是" if v else "否"


def eventid_to_dt(day, frac):
    if day is None:
        return None
    return datetime(1899, 12, 30) + timedelta(days=float(day) + float(frac or 0) / 2147483648.0)


def ip_from_computerid(cid):
    try:
        return socket.inet_ntoa(struct.pack(">i", int(cid)))
    except Exception:
        return None


def strip_comments(sql: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    s = re.sub(r"--[^\n]*", " ", s)
    return s


def header_block(sql: str) -> str:
    """CREATE 之前的註解區塊 (含 -- 與 /* */)"""
    m = re.search(r"^\s*CREATE\s", sql, flags=re.I | re.M)
    head = sql[: m.start()] if m else sql[:2000]
    return head


AUTHOR_RE = re.compile(
    r"([A-Z][a-z]+(?: [A-Z][A-Za-z]+)+)\s*[-,]?\s*(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{4})"
)
DATE_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{4})")


def parse_date(s):
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


def parse_header(name: str, sql: str):
    head = header_block(sql)
    lines = []
    for ln in head.splitlines():
        t = ln.strip()
        t = re.sub(r"^/\*+|\*+/$", "", t).strip()
        t = re.sub(r"^--+", "", t).strip()
        t = re.sub(r"^-{3,}$", "", t).strip()
        lines.append(t)
    # description: lines after the name line until blank / section keyword
    desc = []
    started = False
    for t in lines:
        if not started:
            if t.lower().startswith(name.lower()) or t.lower() == name.lower():
                started = True
            continue
        if re.match(r"^(Inputs?|Outputs?|Returns?|Notes?|Author|Input parameters|Source control|Example)\s*(-|:|$)", t, re.I):
            break
        if t == "" and desc:
            break
        if t:
            desc.append(t)
    if not desc:
        # views w/o name line: first non-empty comment lines
        for t in lines:
            if t and not t.startswith("$") and not t.startswith("@") and not t.lower().startswith("object:") and not re.match(r"^Ams\w+\s*$", t) and not re.match(r"^(Inputs?|Outputs?|Returns?|Notes?)\s*(-|:|$)", t, re.I):
                desc.append(t)
                if len(desc) >= 2:
                    break
    description = " ".join(desc)[:300]
    # author/date: "Author --\n Name\n date" or "Name date" / "Name, date" / "Name - date"
    entries = []
    for i, t in enumerate(lines):
        if re.match(r"^Author", t, re.I):
            nm = lines[i + 1].strip() if i + 1 < len(lines) else ""
            dt = lines[i + 2].strip() if i + 2 < len(lines) else ""
            if nm and DATE_RE.search(dt):
                entries.append((nm, DATE_RE.search(dt).group(1)))
            elif nm:
                m = AUTHOR_RE.search(nm)
                if m:
                    entries.append((m.group(1), m.group(2)))
    for t in lines:
        for m in AUTHOR_RE.finditer(t):
            entries.append((m.group(1), m.group(2)))
    # dedupe keep order
    seen = set()
    ents = []
    for e in entries:
        if e not in seen:
            seen.add(e)
            ents.append(e)
    revm = re.search(r"\$Revision:\s*(\d+)", head)
    return description, ents, (revm.group(1) if revm else None)


# ----------------------------------------------------------------------------
# 關鍵語意規則（固定內容，附證據）
# ----------------------------------------------------------------------------
RULES = [
    ("時間", "EventIdDay/EventIdFraction → 時間：datetime = (EventIdDay − 2) + EventIdFraction / 2147483648 天，以 SQL datetime 起點 1900-01-01 計；等價於 OLE 日期序號 (1899-12-30 起算) 的整數/小數拆分。結果為 UTC。",
     "AmsUdf_EventIdDayFractionToDateTime",
     "set @dtEventDate = cast( ( (cast(@iEventIdDay as float(53)) - 2.0) + (cast(@iEventIdFraction as float(53)) / 2147483648.0) ) as datetime) --VT_DATE starts at 12/30/1899", "高"),
    ("時間", "反向：EventIdDay = FLOOR(OLE 日期 double)；EventIdFraction = int(小數部分 × 2^31 + 0.5)。",
     "AmsUdf_EventTimeAsDblToEventIdDay / AmsUdf_EventTimeAsDblToEventIdFraction",
     "return(FLOOR(@dEventTime)) … return (cast(((@dDecimalPart * cast(2147483648.0 as double precision)) + 0.5) as int))", "高"),
    ("時間", "EventLog.EventTime 為 GMT/UTC；台灣時間 = +8 小時。用戶端以 'yyyy-mm-dd hh:mi:ss.mmm' 字串傳入 GMT。",
     "AmsSp_LogEventSummary_2 / AmsSp_Device_GetHistoricalConfigList_1",
     "-- @strEventTimeAsGMT … Note: this time is in GMT / -- Recordset containing list of configuration change dates (in GMT).", "高"),
    ("時間", "AmsUdf_GetLocalDateTimeFromUtc 以伺服器目前時區差 (GETDATE−GETUTCDATE) 平移 UTC；不處理日光節約歷史。",
     "AmsUdf_GetLocalDateTimeFromUtc",
     "return DATEADD(minute, DATEDIFF(minute,GETUTCDATE(), GETDATE()), @UtcDateTime);", "高"),
    ("哨兵", "EventIdDayOut = 49710 (=2036-02-05 OLE 序號) 表示位號/測試定義指派「目前仍有效」；查目前指派時以 EventIdDayOut=49710 過濾。",
     "AmsSp_AssignDevTag_1 / AmsSp_DeviceTags_1 / AmsVw_CurrentTagBlockAsgms",
     "values(@nExtBlockTagKey, @nDeviceLevelBlockKey, 49710, 0, @nEventIdDay, @nEventIdFraction, 0) … WHERE (dbo.BlockAsgms.EventIdDayOut = 49710)", "高"),
    ("哨兵", "EventIdDay = 25569 (=1970-01-01) 且 Fraction 0 為「未設定/測試列」哨兵：EventLog 首筆 'Test event log (do not remove)'、TestDefinitionHistory 初始版本、校正日期未設定。EventLog 另有 49710/0 (2036-02-05) 'Large event id (do not remove)' 哨兵列，供 BlockAsgms/TestDefAsgms 的 EventIdDayOut 外鍵指向；統計事件時應排除這 2 列 (UserKey/ComputerId/BlockKey 皆 -1)。",
     "AmsSp_Operation_GetProjectedCalibrationDate_1 / EventLog 資料 / _foreign_keys",
     "EventLog: 25569 | 0 | 1970-01-01 | 'Test event log (do not remove)' ; 49710 | 0 | 2036-02-05 | 'Large event id (do not remove)' ; FK BlockAsgms.EventIdDayOut -> EventLog.EventIdDay", "高"),
    ("哨兵", "鍵值 -1 為各主檔「Default unknown (do not remove)」哨兵列 (Devices/Blocks/DeviceRevisions/DeviceTypes/Users/ExtBlockTags/NetworkInfo/PlantServer/NamedConfigs)；TestDefinition -1/-2/-3 為內建預設方案 (Field Device / External Lab / Flow Verification)；Hierarchies -99 為虛擬根節點、-1 Site-wide、-2 Unassigned、-3 User Configurations、-4 Standard、-5 Migrated、-6 Handheld、-7 System。",
     "資料 + AmsSp_HasPermission (範圍 GUID 常數)",
     "Devices(-1): 'Default unknown (do not remove)'; TestDefinition(-1)='Default Field Device', (-2)='Default External Lab', (-3)='Default Flow Verification'; Hierarchies(-7,'System',parent -99)", "高"),
    ("參數", "BlockData/NamedConfigData.ParamDataType：3 = 窄字串 (narrow/ASCII)、12 = 寬字串 TString (UTF-16LE，存成 varbinary)。程式碼明示；其餘型別由位元組長度與 .ams_merge 匯出 vtype 對照：4 = Long (int32 LE)、6 = Float (float32 LE)、8 = Time (OLE 日期 double，如 date.000000A6 = 0x40E62F0000000000 → 45432 = 2024-05-20)、9 = Binary (變長 2~57 位元組)。5 (4 位元組)、7 (8 位元組) 僅見於範本 NamedConfigData，推測為無號整數/雙精度，未確認。",
     "AmsSp_GetBlockKeyCurrentHartInfo_1 / AmsUdf_CurrentDescriptor / AmsSp_GetNonDDHistoricalConfigList_1",
     "if @iParamType = 3 --Narrow string, parameter type = 3 … else if @iParamType = 12 --Generic string. parameter type = 12 ; 'convert ParamData to varbinary if the ParamDataType = 12 (TString)' ; 與前次工作簿 vtype 交叉：4↔Long 2958 參數、6↔Float 2656、8↔Time 20、9↔Binary 2、12↔TString 192 (無例外)", "高"),
    ("參數", "BlockData 中 ParamDataType=3 且 Archived=1 的 140,790 列全部屬於 FF 裝置（FF 參數以十六進位文字容器存放，AMS 對 FF 列一律 Archived=1）；HART 字串參數（descriptor 等）用型別 12。讀取最新值應以 EventIdDay/Fraction 最新者為準。",
     "AmsUdf_CurrentDescriptor (AOEP00032552 註解) + 資料",
     "--AOEP00032552 because of localization, the data type of this parameter is now Generic(wide) string type, it was narrow string type, this function needs to handle both (narrow(= 3) or wide(= 12))", "高"),
    ("參數", "ValueMode：'h' = history (參數值已設定/納入)，'o' = off (未包含)。BlockData 幾乎全為 h (12 列 o)；NamedConfigData 範本中 o 佔 147,591 列 = 範本未指定該參數。",
     "AmsSp_GetNamedConfigParamValueMode_1 / AmsSp_SetNamedConfigParamValueMode_1",
     "--  @valueMode - 'h' for history and 'o' for off", "高"),
    ("參數", "ParamKind：'P' = DD 參數；'D' = 裝置警報/非 DD 資料 (frsi.DeviceAlarm.<AlertTypeUid>、frsi.AlarmBlockIndex)。AmsUdf_AlertTypeUidFromParamName 由 'frsi.DeviceAlarm.' 後段取警報種類 UID。",
     "AmsSp_GetNonDDHistoricalConfigList_1 / AmsUdf_AlertTypeUidFromParamName",
     "WHERE BlockData.ParamKind = 'D' … (Non-DD parameters) ; set @sStartString = N'frsi.DeviceAlarm.'", "高"),
    ("參數", "HART 參數名格式 <name>.<DD item id 8 位十六進位>.<sub>.<sub>：tag.000000A3、message.000000A4、descriptor.000000A5、date.000000A6、software_revision.0000009E、device_id.000000A1、hardware_revision.0000009F、final_assembly_number.000000A9、polling_address.000000A2。",
     "AmsSp_GetBlockKeyCurrentHartInfo_1 / AmsUdf_CurrentSoftwareRevision",
     "\"tag.0000A3.0000.0000\" to get the HART tag / \"message.000000A4.0000.0000\" / \"descriptor.000000A5.0000.0000\" ; ParamName = N'software_revision.0000009E.0000.0000'", "高"),
    ("參數", "軟體版本等 4 位元組整數以 little-endian 儲存：int = b0 + b1×256 + b2×65536 + b3×16777216。",
     "AmsUdf_BinaryToInt",
     "cast(left(@bBinaryValue,1) as int) + substring(...,2,1)*256 + substring(...,3,1)*65536 + substring(...,4,1)*16777216", "高"),
    ("組態", "NamedConfigs.ConfigType：'T' = 範本 Template (含使用者組態，H275=1 為使用者/手持器格式)、'C' = 特性 Characteristics (每型號版本恰一筆，FF 用)、'S' = 手持器 (H275) 範本；'F' 於檢視中查詢但本廠無。使用者組態建立時複製 ConfigType='T' 且 H275=0 的原廠範本區塊，再以 Components 掛到階層資料夾。",
     "AmsSp_CreateUserConfiguration_1 / AmsSp_Device_GetCharTemplateName_1",
     "INSERT INTO NamedConfigs (…ConfigType, UniversalId, H275) VALUES (…'T', @protocolRev, 1) … WHERE (NamedConfigs.ConfigType = N'T') AND (NamedConfigs.H275 = 0) ; 'one and only one template of the deviceRevision and with the configuration type of C'", "高"),
    ("組態", "NamedConfigs.UniversalId = HART 通用命令版本 (ProtocolRevision 5/6/7)，查範本時以 UniversalId = 裝置 ProtocolRevision 比對；0 為 FF/特性。",
     "AmsSp_Devices_GetAddKey_2",
     "(dbo.NamedConfigs.UniversalId = @nProtocolRev) ; 資料：UniversalId 分佈 0/3/4/5/6/7", "高"),
    ("區塊", "Blocks.BlockType：'' (BlockIndex 0) = 裝置層級區塊；FF 裝置另有 'R' RESOURCE、'T' TRANSDUCER<n>、'F' FUNCTION<n>。每台裝置恰一筆裝置層級區塊；子區塊事件需經 AmsVw_DeviceLevelBlockKey 或 AmsUdf_GetDevLvlTagAsgm 回推位號。",
     "AmsUdf_GetFFBlockName / AmsSp_Blocks_GetAddId_1 / AmsVw_DeviceLevelBlockKey",
     "when N'R' then N'RESOURCE' when N'T' then N'TRANSDUCER' when N'F' then N'FUNCTION' ; if (@blockType !='R') blockName += blockIndex ; -- for the device level block, the BlockIndex = 0 and BlockType = ''", "高"),
    ("裝置", "DeviceLocation.IdentStatus：1 = identified (已識別/線上曾辨識)，0 = unknown；網路重建時整個網路先設 0，再逐台識別設 1。本廠 1,894 台為 1、34 台為 0。",
     "AmsUdf_DevBlkIdentStatusAsString / AmsSp_DevBlk_UpdateLocationInfo_1",
     "when 0 then N'unknown' when 1 then N'identified' ; update DeviceLocation set IdentStatus = 0 where @nNetworkKey = NetworkInfoKey", "高"),
    ("裝置", "DeviceLocation.SisStatus：0/NULL = BPCS (一般儀器)；1 或 2 = SIS 安全儀控裝置 (Classification=1)。讀取權限檢查時 SisStatus>0 需 SIS 讀取權限。本廠全部為 0。",
     "AmsVw_EF_Device / AmsSp_CheckReadPermissionByDevIdentifier",
     "WHEN DeviceLocation.SisStatus = 0 THEN 0 WHEN DeviceLocation.SISStatus = 1 THEN 1 WHEN DeviceLocation.SisStatus = 2 THEN 1 ELSE 0 END AS Classification ; if (@tagHasPermission = 0 and @sisStatus <= 0) --this is BPCS device", "高"),
    ("裝置", "Devices.DispositionId：0 Unknown、1 Assigned (Installed，指派到廠區階層時設定)、2 Spare、3 Retired (Not in service)、4 don't use、5 Deleted。查未指派裝置以 in (2,3) 過濾。本廠 1,928 台全為 2 Spare = 從未指派到廠區階層 (Unassigned)。",
     "Dispositions 表 / AmsSp_DevBlk_AssignToControl_1 / AmsSp_GetDevicesinPlantLocationPerPermission",
     "update Devices set DispositionId = 1 --(1 meaning assigned) ; Devices.DispositionId in (2, 3)", "高"),
    ("裝置", "Assets.Discriminator：1 = 實體裝置、2 = 虛擬裝置 (HostTag 建立)。DeviceAssets 將 DeviceKey 對到 AssetId GUID，EF/安全檢視以 GUID 為裝置 Id。",
     "AmsSp_CreateDeviceAsset_1 / AmsSp_CreateVirtualDeviceAsset",
     "--Discriminator = 1 implies real device ; --Discriminator = 2 implies virtual device Insert Assets (Discriminator, Tag) values(2, @HostTag)", "高"),
    ("裝置", "DeviceLocation.AmsPath 格式 'net!<伺服器>!<網路名>!<位址>!<子位址>'，以 '!' 分隔；HostPath 為主機端位址 (多工器: 卡.通道.…)。",
     "AmsUdf_FormatPhysicalNetworkNodePath / AmsUdf_HierarchyStringSplit",
     "Example of AMS network path: net!USRTC-NGHYHON8!DeltaV Network 1!Controller - CTLR-00D578!I/O - DeltaV!I/O HART Card - C01!CH01 ; 本廠: net!AMS1SVR!SAMP1_LU007!1!MUX_DEVICE", "高"),
    ("事件", "EventLog.ComputerId = 用戶端 IPv4 位址 (host-order 32 位元有號整數)：a.b.c.d = (a<<24)|(b<<16)|(c<<8)|d，以 Python struct.pack('>i') + inet_ntoa 還原。驗證：2130706433 → 127.0.0.1；-1408185981 → 172.16.201.131 (AMS1SVR，17,695 筆)；-1 = 255.255.255.255 (未知)。",
     "AmsSp_LogEventSummary_2",
     "-- @iComputerNameId int : This is the computer IP address (i.e. the 'where') of the event. ; 資料驗證 2130706433 = 0x7F000001 = 127.0.0.1", "高"),
    ("事件", "EventLog.Type (事件型別，程式碼僅明示 5 與 8)：5 = 狀態警報 StatusAlert (AlertLog 必須對應 Type 5)；8 = DBW_ET_DEVICE_SCAN 裝置掃描/同步 (最後同步時間 = Type 8 的 max EventTime)。稽核軌跡檢視只列 Type 1~9 且排除 6 與 9。資料推得：1 = 組態變更 (Category 1/28)、2 = 校正/測試方案指派 (Cat 49；本廠 1,642 筆全為 Cat 49)、3 = 資料庫維護 (Cat 14/52/16/12)、4 = 應用程式/系統事件 (登入、掃描開始/完成、啟動)、6 = 範本/裝置型別建立 (AmsMergeDoc/Create Device Template，不列入稽核)、0 = 其他/未分類。",
     "AmsSp_AL_ProcessNotifyAlertLogInsert_1 / AmsSp_DevBlk_GetLastSyncTime_1 / AmsSp_AuditTrailSummary_All_1",
     "if (@nType <> 5) … 'event not of statusAlert type' ; -- search for event type of DBW_ET_DEVICE_SCAN (8). … where BlockKey = @nBlockKey and Type = 8 ; WHERE (EventLog.Type >= 1 and EventLog.Type <= 9 and NOT EventLog.Type = 6 and NOT EventLog.Type = 9)", "中"),
    ("事件", "EventLog.Category 依 EventCategories 解碼 (-1~18 不可更動)；警報 Set/Clear：20/21 裝置警報、30/31 應用程式警報、62/63 診斷警報 → AlertState 1/0；74 = Alert Acknowledged (查警報時排除)；43/44/45 = 裝置同步 無變更/有變更/失敗；28 = Field change (現場變更)；1 = AMS 變更；49 = 測試方案指派；72/73 投用/退役；89/90 個別裝置保護啟用/停用。",
     "AmsSp_AL_ProcessNotifyAlertLogInsert_1 / AmsUdf_GetAlertSource / AmsSp_GetAlertListFromDateToCurrent_1 / AmsSp_SetDeviceProtectByTag",
     "if (@EventCategory in (20,30,62)) set @AlertState = 1; if (@EventCategory in (21,31,63)) set @AlertState = 0; ; when 30/31/62/63 then @sEventSource else N'AMSDMHostProcess' ; EventLog.Category <> 74 ; set @nEventCategory = 89;--Individual Device Protection Enabled", "高"),
    ("事件", "EventLog.Source = 寫入事件的應用程式 ('Server' = AMS 伺服器/Plant Server 自動偵測、'AMS Device Manager Application' = 使用者操作、'AmsMergeDoc' = 匯入範本、'Database Maintenance'、'FF Polling Application'、'AMS Device Manager - User Manager')；EventCode 永遠為 0。",
     "AmsSp_LogEventSummary_2",
     "-- @strEventSourceApplication : Some additional where for the event. ; -- @nEventCode smallint : This is the Event Code (always be 0).", "高"),
    ("事件", "EventLog.UserKey → Users；若 AMS 使用者不存在則改用檔案伺服器帳號 'FS.<computerName>'；'PS.<伺服器>' 為 Plant Server 服務帳號 (自動偵測 Field change)。",
     "AmsSp_LogEventSummary_2",
     "-- * if the Ams user name is not in the database it will use File Server user name instead. ; @strPSUserNameName … Format is 'FS.<computerName>'", "高"),
    ("警報", "AlertId (HART 標準)：狀態位元 → 16 位十六進位字串，位元對應 0x01 PV out of limits='0100000000000000'、0x02 Non-PV='0200…'、0x04 AO saturated='0400…'、0x08 AO fixed='0800…'、0x10 More status='1000…'、0x20 Cold start='2000…'、0x40 Config changed='4000…'、0x80 Malfunction='8000…'、0x100 No response='0001000000000000'。DeviceAlertDesc.AmsDevRevId=-1 列即此 9 個標準警報；其他 AlertId 為 DD 定義之裝置專屬字串。",
     "AmsUdf_GetHartAlertId / AmsUdf_GetHartAlertDesc",
     "when @DBW_DVS_PV_OUT_OF_LIMITS then N'0100000000000000' … when @DBW_DVS_NO_RESPONSE then N'0001000000000000' ; DeviceAlertDesc(0,-1,'0100000000000000','Primary Variable Out Of Limits',4)", "高"),
    ("警報", "AlertTypes：0 UNKNOWN、1 FAILED、2 MAINT、3 ADVISE、4 ABNORM、5 NOCOMM(COMM)、6 CHKFNC；AlertLog.AlertTypeId 指向之。AlertList.AlertState 1=Set/0=Clear、AckState 1=已確認；AlertSource 於 SNAP-ON 類別用事件 Source，否則 'AMSDMHostProcess'。",
     "AlertTypes 表 / AmsSp_AL_ProcessNotifyAlertLogInsert_1 / AmsUdf_GetAlertSource",
     "AlertTypes: (1,'ALERT_FAILED_ID','FAILED') … (6,'ALERT_CHKFNC_ID','CHKFNC') ; if (@nAlertState = 1) … set AckState = 1", "高"),
    ("警報", "本廠 AlertList / AlertLog / DeviceMonitorList / AlertFilterForDevice 全為空 → Alert Monitor 雖 PlantServer.AlertMonitorEnabled=1 但無裝置納入監視名單，資料庫中沒有任何裝置警報歷史 (EventLog 無 Type 5)。",
     "資料 + AmsSp_LogEventSummary_2 回傳碼",
     "-4 … alert associated device not in the device monitor list … ; -6 - alert was filtered because device is not in the device monitor list, no logging was done ; EventLog Type 分佈無 5", "高"),
    ("安全", "安全模型以 GUID 為主：Grants(PrincipalId, PrivilegeId, PlantLocationId)。範圍 GUID 常數：Site-wide 81C7311F-D829-4CDD-961A-A3E3A25D013F、Manufacturer 3CFEC380…、User Configurations 5DC4F174…、Unassigned 10F82026…、System 87FC0717…；= Hierarchies.AreaIdentifier。Configuration 類權限 (Classification 3) 的全域範圍改用 User Configurations 資料夾，System 類 (2) 改用 System 資料夾；AmsServiceUser 3044F0E9-7033-4FB0-8E8A-008D367E3A32 永遠有權限；使用者 Status 0/-1 = 停用一律無權限；群組成員經 GroupPrincipalWindowsUserPrincipal 繼承。",
     "AmsSp_HasPermission / AmsSp_CheckUserPermission",
     "DECLARE @SITE_WIDE UniqueIdentifier = '81c7311f-d829-4cdd-961a-a3e3a25d013f' … If @PerClassification = @Config_Permission set @SITE_WIDE = @UC_Folder ; if @UserIdentifier = @AMSSERVICEUSER set @hasPermission = 1", "高"),
    ("安全", "權限 GUID 常數：Device Write 3AC0E5EE-7A1A-4144-A8EB-0D1876EE9051、Device SIS Write 89F87233-DCD0-458E-ABA9-302C53A52317、ValveLink Change Instrument Mode D2EF7813…、Calibrate Instruments CD344651…、Run Diagnostics/Move Valve 68AE3624…、Configure Instruments 45579236…；這些寫入類權限另受 Device Protection 檢查。PermissionClassification：0 SIS、1 BPCS、2 System、3 Configuration。",
     "AmsSp_HasPermission",
     "DECLARE @Device_Write UniqueIdentifier = '3ac0e5ee-7a1a-4144-a8eb-0d1876ee9051' … --if @PermissionIdentifier is Device Write and ValveLink Snap on, check Device Protection status first", "高"),
    ("安全", "本廠授權現況：7 個 Windows 使用者 (Admin1、GEAdmin、HTPPAdmin、u120396、u534521、u534558、u675532) 各直接持有全部 46 項權限 (Site-wide 27 項 + System 資料夾 + User Configurations 資料夾)，等同全部為系統管理員；群組 (System Admin 46、Maintenance 38、Read-Only 10、Database Admin 5) 無成員 (GroupPrincipalWindowsUserPrincipal 空)。Grants 依權限分類落在不同範圍：Site-wide 244、System 156、User Configurations 18。",
     "Grants / Principals_UserWindowsPrincipal 資料 + AmsSp_HasPermission 範圍規則",
     "select p.Name,count(*) from Grants g join Principals_UserWindowsPrincipal p … → 每人 46 (Admin1 43)；GroupPrincipalWindowsUserPrincipal 0 列", "高"),
    ("安全", "Hierarchies 與 PlantLocations/PlantLocations_Scope 由觸發器同步：新增/更名/刪除階層節點時同步安全範圍 GUID (AreaIdentifier = PlantLocations.Id)。",
     "AmsTr_InsertHierarchies / AmsTr_UpdateHierarchies / AmsTr_DeleteHierarchies",
     "CREATE TRIGGER AmsTr_InsertHierarchies ON dbo.Hierarchies AFTER INSERT … Insert PlantLocations / PlantLocations_Scope", "中"),
    ("校正", "CalStatus 的 Day/Fraction 為 EventId 格式 (0 = 未校正)；TestDefinition.Type：2 流量驗證、5 外部實驗室、99 現場儀器；ExtBlockTags.TestDefinitionId 為位號目前校正方案 (-1 = Default Field Device)。校正結果表 (TestResults/AFAL/Points) 本廠皆空。",
     "TestDefinition 表 / AmsSp_AssignNewTagTestDef_1",
     "TestDefinition(-3,'Default Flow Verification',2,…) (-2,'Default External Lab',5,…) (-1,'Default Field Device',99,…)", "中"),
    ("組態", "SnapOnData：SnapOnDataOwnerId 1 = AmsDeviceManager；SnapOnData 內容為 UTF-16LE XML ('<?xml …')，SnapOnDataType 1 (1,562 筆) / 3 (227 筆)，以 BlockKey + EventIdDay/Fraction 對應事件。",
     "SnapOnDataOwners 表 / AmsSp_GetSnapOnData 類程序",
     "SnapOnData 樣本: <bin 358B 3c003f0078006d006c002000> = '<?xml ' UTF-16LE", "中"),
    ("網路", "NetworkInfo.NetworkKindAsString 'Mux Network' = HART 多工器網路 (本廠對應 GE Mark VIe 機櫃 I/O 名稱如 BOPE1_CA021、SAMP1_LU007)；NetworkInfoKey -1 = 未知；DeviceLocation.NetworkInfoKey<>-1 且 IdentStatus=1 才視為線上裝置。",
     "AmsSp_DeviceTagLocation_1 / NetworkInfo 表",
     "and (dbo.DeviceLocation.NetworkInfoKey <> -1) and (dbo.DeviceLocation.IdentStatus = 1)", "高"),
    ("工作簿", "前次工作簿 (20260910_AMS解析.xlsx) 交叉：17_使用者與電腦 的電腦 IP (172.16.201.131、10.1.141.54、172.16.101.17、10.8.0.6、10.223.32.77…) 與本規則的 ComputerId→IP 解碼完全一致；20_參數字典 vtype (Long/Float/Time/Binary/TString) 與 ParamDataType 4/6/8/9/12 一對一對應 (5,828 個 HART 參數無例外)。",
     "本模組交叉驗證",
     "見 sheets_modules.py 執行紀錄", "高"),
]

# 代碼對照表：小型查表彙整
LOOKUPS = [
    ("EventCategories", "Category", "CategoryDesc", None),
    ("AlertTypes", "AlertTypeId", "AlertTypeName", "Uid"),
    ("Dispositions", "DispositionId", "Name", "Description"),
    ("DeviceProtocols", "ProtocolId", "Name", "Description"),
    ("PermissionClassification", "Id", "Name", None),
    ("SecurityType", "Id", "Name", None),
    ("ServiceReasons", "ServiceId", "ServiceDesc", None),
    ("MobileDeviceTypes", "MobDevTypeId", "Name", None),
    ("PolicyTypes", "PolicyTypeId", "PolicyTypeName", None),
    ("Labels", "LabelId", "LabelName", None),
    ("SnapOnDataOwners", "SnapOnDataOwnerId", "Name", None),
    ("MajorDeviceCategories", "MajorDeviceCategoryId", "Name", "Description"),
    ("MinorDeviceCategories", "MinorDeviceCategoryId", "Name", "Description"),
    ("PlantLocations_Scope", "Id", "Name", None),
    ("Users", "UserKey", "UserName", None),
    ("Hierarchies", "AreaId", "AreaName", "ParentAreaId"),
    ("SystemDefaults", "Parameter", "Data", None),
]
ZH_LOOKUP = {
    ("Dispositions", "0"): "未知", ("Dispositions", "1"): "已指派/已安裝", ("Dispositions", "2"): "備品(未指派階層)", ("Dispositions", "3"): "退役(停用)", ("Dispositions", "4"): "勿用", ("Dispositions", "5"): "已刪除",
    ("AlertTypes", "0"): "未知", ("AlertTypes", "1"): "失效", ("AlertTypes", "2"): "需維護", ("AlertTypes", "3"): "建議", ("AlertTypes", "4"): "異常", ("AlertTypes", "5"): "無通訊", ("AlertTypes", "6"): "檢查功能",
    ("DeviceProtocols", "1"): "HART", ("DeviceProtocols", "2"): "傳統(4-20mA 無數位)", ("DeviceProtocols", "3"): "Foundation Fieldbus", ("DeviceProtocols", "4"): "PROFIBUS-DP", ("DeviceProtocols", "5"): "PROFIBUS-PA",
    ("PermissionClassification", "0"): "安全儀控 SIS", ("PermissionClassification", "1"): "基本程序控制 BPCS", ("PermissionClassification", "2"): "系統", ("PermissionClassification", "3"): "組態",
}
ZH_EVENTCAT = {
    -1: "未知", 0: "無", 1: "AMS Device Manager 執行的變更", 2: "巡檢站執行的變更", 3: "行動裝置執行的變更", 4: "校正前失敗/校正後失敗", 5: "校正前失敗/校正後通過",
    6: "儀器狀態", 7: "使用者狀態", 8: "網路狀態", 9: "封存", 10: "封存-清除", 11: "載入", 12: "備份", 13: "還原", 14: "自檔案合併(匯入)", 15: "自其他 AMS 資料庫合併",
    16: "擷取", 17: "壓縮", 18: "驗證-修復", 19: "測試方案變更", 20: "裝置警報發生(Set)", 21: "裝置警報解除(Clear)", 22: "HART Interchange 狀態設定", 23: "HART Interchange 狀態解除",
    24: "校正前通過/校正後失敗", 25: "校正前通過/校正後通過", 26: "校正前通過/校正後 N/A", 27: "校正前失敗/校正後 N/A", 28: "現場變更(由裝置端/外部主機變更，伺服器偵測)", 29: "SNAP-ON 應用程式變更",
    30: "應用程式警報發生", 31: "應用程式警報解除", 36: "校正器逾認證期校正", 37: "新測試設備", 38: "超出通知極限", 39: "外部實驗室校正", 40: "校正前 N/A/校正後 N/A", 41: "校正前 N/A/校正後失敗", 42: "校正前 N/A/校正後通過",
    43: "裝置同步成功-無差異", 44: "裝置同步成功-有差異", 45: "裝置同步失敗", 46: "登入", 47: "登出", 48: "手動事件", 49: "測試方案指派變更", 50: "SNAP-ON 應用程式執行的變更", 51: "應用程式", 52: "刪除裝置", 53: "系統選項",
    54: "啟用 Alert Monitor", 55: "停用 Alert Monitor", 56: "使用者密碼變更", 57: "新使用者", 58: "使用者帳號變更", 59: "電子簽章", 60: "裝置警報條件取消抑制", 61: "裝置警報條件抑制", 62: "診斷警報發生", 63: "診斷警報解除",
    64: "裝置警報已抑制", 65: "裝置警報已停用", 66: "驗證通過", 67: "驗證失敗", 68: "掃描裝置開始", 69: "掃描裝置完成", 70: "掃描裝置取消", 71: "重建階層", 72: "裝置投用(Commission)", 73: "裝置退役(Decommission)", 74: "警報已確認",
    75: "Alert Monitor 組態變更", 76: "加入無線網路", 77: "AMS 校正連接器執行的變更", 78: "具名組態資料", 79: "行動裝置授權變更", 80: "行動裝置同步開始", 81: "行動裝置同步完成", 82: "行動裝置傳輸中斷", 83: "行動裝置啟閉連線 App",
    84: "行動裝置偵測到 Command 48 設定", 85: "未授權動作", 86: "專案建立", 87: "全域裝置保護啟用", 88: "全域裝置保護停用", 89: "個別裝置保護啟用", 90: "個別裝置保護停用", 91: "專案刪除", 92: "專案更名", 93: "專案完成", 94: "專案取消完成",
    95: "任務加入專案", 96: "任務移出專案", 97: "任務完成", 98: "任務取消完成", 99: "裝置重複警報已過濾",
}


# ----------------------------------------------------------------------------
def build(conn: sqlite3.Connection) -> list:
    q = lambda s, p=(): conn.execute(s, p).fetchall()
    schema = pd.read_sql("select * from _schema", conn)
    tables = pd.read_sql("select table_name, row_count from _tables", conn)
    fks = pd.read_sql("select * from _foreign_keys", conn)
    mods = pd.read_sql("select type_desc, object_name, definition from _modules", conn)
    mods["definition"] = mods["definition"].fillna("")
    rowcount = dict(zip(tables.table_name, tables.row_count))
    table_names = sorted(rowcount.keys(), key=str.lower)

    # --- module ↔ table references (word-boundary, comments stripped)
    stripped = {r.object_name: strip_comments(r.definition) for r in mods.itertuples()}
    tbl_pat = {t: re.compile(r"(?<![A-Za-z0-9_])" + re.escape(t) + r"(?![A-Za-z0-9_])", re.I) for t in table_names}
    mod_pat = {m: re.compile(r"(?<![A-Za-z0-9_])" + re.escape(m) + r"(?![A-Za-z0-9_])", re.I) for m in mods.object_name}
    mod_tables = {}
    tbl_mods = defaultdict(list)
    mod_mods = {}
    for m, body in stripped.items():
        refs = [t for t in table_names if tbl_pat[t].search(body)]
        mod_tables[m] = refs
        for t in refs:
            tbl_mods[t].append(m)
        mod_mods[m] = [o for o in mods.object_name if o != m and mod_pat[o].search(body)]
    # column-level references: (table, column) mentioned in modules that reference the table
    col_ref_count = {}
    for t in table_names:
        cols = schema[schema.table_name == t].column_name.tolist()
        for c in cols:
            pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(c) + r"(?![A-Za-z0-9_])", re.I)
            n = 0
            for m in tbl_mods[t]:
                if pat.search(stripped[m]):
                    n += 1
            col_ref_count[(t, c)] = n

    fk_out = defaultdict(list)
    fk_in = defaultdict(list)
    fk_col = {}
    for r in fks.itertuples():
        fk_out[r.parent_table].append(f"{r.parent_column}→{r.ref_table}.{r.ref_column}")
        fk_in[r.ref_table].append(f"{r.parent_table}.{r.parent_column}")
        fk_col[(r.parent_table, r.parent_column)] = f"{r.ref_table}.{r.ref_column}"

    def typ(r):
        dt = r.data_type
        if dt in ("nvarchar", "nchar", "varchar", "char", "varbinary", "binary"):
            ml = r.max_length
            if ml == -1:
                return f"{dt}(max)"
            if dt.startswith("n"):
                return f"{dt}({int(ml // 2)})"
            return f"{dt}({int(ml)})"
        if dt in ("decimal", "numeric"):
            return f"{dt}({r.precision},{r.scale})"
        if dt in ("datetime2", "datetimeoffset", "time"):
            return f"{dt}({r.scale})"
        return dt

    # ---------------- Sheet 1: 資料表字典
    rows = []
    for t in table_names:
        sc = schema[schema.table_name == t].sort_values("column_id")
        pk = [c for c, p in zip(sc.column_name, sc.is_pk) if p]
        cols = [f"{r.column_name}:{typ(r)}" for r in sc.itertuples()]
        cat, desc = TABLE_DESC.get(t, ("", ""))
        n = int(rowcount[t])
        rows.append({
            "資料表 (table_name)": t,
            "領域": cat,
            "列數 (row_count)": n,
            "空表": yn(n == 0),
            "中文說明": desc + ("；本廠為空表" if n == 0 and "未使用" not in desc and "為空" not in desc else ""),
            "欄位數": len(cols),
            "主鍵欄位": ", ".join(pk),
            "欄位清單 (名稱:型別)": "; ".join(cols),
            "外鍵 (出)": "; ".join(fk_out[t]),
            "被參照 (入)": "; ".join(fk_in[t]),
            "參照模組數": len(tbl_mods[t]),
            "參照模組 (檢視)": ", ".join(m for m in tbl_mods[t] if m.startswith("AmsVw_") or m.startswith("Id"))[:1000],
            "參照模組 (程序/函數/觸發)": ", ".join(m for m in tbl_mods[t] if not (m.startswith("AmsVw_") or m.startswith("Id")))[:2000],
        })
    df_tables = pd.DataFrame(rows).sort_values(["領域", "資料表 (table_name)"]).reset_index(drop=True)
    empty_tables = [t for t in table_names if rowcount[t] == 0]

    # ---------------- Sheet 2: 欄位字典
    rows = []
    for r in schema.sort_values(["table_name", "column_id"]).itertuples():
        t, c = r.table_name, r.column_name
        meaning = COL_DESC_TBL.get((t, c)) or COL_DESC.get(c, "")
        rows.append({
            "資料表 (table_name)": t,
            "序 (column_id)": int(r.column_id),
            "欄位 (column_name)": c,
            "型別": typ(r),
            "可為空 (is_nullable)": yn(r.is_nullable),
            "主鍵 (is_pk)": yn(r.is_pk),
            "自動編號 (is_identity)": yn(r.is_identity),
            "外鍵目標": fk_col.get((t, c), ""),
            "中文意義": meaning,
            "資料表列數": int(rowcount[t]),
            "參照此欄的模組數": col_ref_count.get((t, c), 0),
            "資料表領域": TABLE_DESC.get(t, ("", ""))[0],
        })
    df_cols = pd.DataFrame(rows)

    # ---------------- Sheet 3: 視圖與程序
    TYPE_ZH = {"VIEW": "檢視 View", "SQL_STORED_PROCEDURE": "預存程序 Procedure", "SQL_SCALAR_FUNCTION": "純量函數",
               "SQL_INLINE_TABLE_VALUED_FUNCTION": "內嵌資料表函數", "SQL_TABLE_VALUED_FUNCTION": "資料表函數", "SQL_TRIGGER": "觸發器 Trigger"}
    rows = []
    for r in mods.itertuples():
        name, sql = r.object_name, r.definition
        description, ents, rev = parse_header(name, sql)
        cat = next((zh for p, zh in PREFIX_CAT if name.startswith(p)), "")
        auth0, date0 = (ents[0] if ents else ("", ""))
        dates = [parse_date(d) for _, d in ents]
        dates = [d for d in dates if d]
        first_dt = min(dates) if dates else None
        last_dt = max(dates) if dates else None
        # 手寫或機械式中文摘要
        zh = HAND_ZH.get(name)
        if not zh:
            zh = f"{cat}：{zh_from_name(name)}" if cat else zh_from_name(name)
        trig_on = re.search(r"TRIGGER\s+\S+\s+ON\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?\s+(AFTER|FOR|INSTEAD OF)\s+([A-Z, ]+)", sql, flags=re.I)
        params = re.findall(r"^\s*@(\w+)\s+([\w\(\),]+)", sql[: sql.lower().find("\nas") + 1 if sql.lower().find("\nas") > 0 else 3000], flags=re.M)
        rows.append({
            "類型": TYPE_ZH.get(r.type_desc, r.type_desc),
            "名稱 (object_name)": name,
            "分類": cat,
            "中文摘要": zh,
            "描述 (原文首段)": description,
            "作者 (首見)": auth0,
            "日期 (首見)": date0,
            "首次日期 (原廠註解)": first_dt,
            "最後修改日期 (原廠註解)": last_dt,
            "作者/日期紀錄": "; ".join(f"{a} {d}" for a, d in ents)[:500],
            "$Revision": rev or "",
            "大小 (字元)": len(sql),
            "行數": sql.count("\n") + 1,
            "參照資料表": ", ".join(mod_tables[name]),
            "參照資料表數": len(mod_tables[name]),
            "呼叫/參照其他模組": ", ".join(mod_mods[name])[:800],
            "觸發表/時機": (f"{trig_on.group(1)} {trig_on.group(2)} {trig_on.group(3).strip()}" if trig_on else ""),
            "參數 (@name type)": "; ".join(f"@{p} {t}" for p, t in params)[:800],
            "動態 SQL (EXEC 字串)": yn(bool(re.search(r"\bEXEC\s*\(|sp_executesql", sql, re.I))),
        })
    df_mods = pd.DataFrame(rows)
    df_mods["首次日期 (原廠註解)"] = pd.to_datetime(df_mods["首次日期 (原廠註解)"])
    df_mods["最後修改日期 (原廠註解)"] = pd.to_datetime(df_mods["最後修改日期 (原廠註解)"])
    df_mods = df_mods.sort_values(["類型", "分類", "名稱 (object_name)"]).reset_index(drop=True)

    # ---------------- Sheet 4: 關鍵語意規則 (含資料驗證欄)
    verify = {}
    # EventId formula check against EventLog.EventTime
    diffs = q("select EventIdDay, EventIdFraction, EventTime from EventLog where EventIdDay>25569 limit 5000")
    bad = 0
    for d, f, et in diffs:
        calc = eventid_to_dt(d, f)
        try:
            real = datetime.fromisoformat(et)
        except Exception:
            continue
        if abs((calc - real).total_seconds()) > 1.0:
            bad += 1
    verify["時間0"] = f"EventLog 前 5,000 筆 EventIdDay/Fraction 換算與 EventTime 差 >1 秒者：{bad} 筆"
    t5 = q("select count(*) from EventLog where Type=5")[0][0]
    cid = q("select ComputerId, count(*) from EventLog group by 1 order by 2 desc limit 3")
    verify["ComputerId"] = "前 3 名 ComputerId→IP：" + ", ".join(f"{c}→{ip_from_computerid(c)} ({n} 筆)" for c, n in cid)
    verify["Type5"] = f"EventLog Type=5 筆數：{t5}"
    arch = q("select Archived, ParamDataType, count(*) from BlockData group by 1,2")
    verify["Archived"] = "BlockData (Archived,型別,筆數)：" + "; ".join(f"({a},{t},{n})" for a, t, n in arch)
    out49710 = q("select count(*) from BlockAsgms where EventIdDayOut=49710")[0][0]
    verify["49710"] = f"BlockAsgms EventIdDayOut=49710 筆數：{out49710} (= 裝置數 1928)；TestDefAsgms：{q('select count(*) from TestDefAsgms where EventIdDayOut=49710')[0][0]}"
    rows = []
    for i, (cat, rule, src, ev, conf) in enumerate(RULES):
        v = ""
        if i == 0:
            v = verify["時間0"]
        elif "ComputerId" in rule:
            v = verify["ComputerId"]
        elif "EventLog.Type" in rule:
            v = verify["Type5"] + "；Type 分佈：" + ", ".join(f"{a}:{n}" for a, n in q("select Type,count(*) from EventLog group by 1 order by 1"))
        elif "Archived=1" in rule:
            v = verify["Archived"]
        elif "ParamDataType：3" in rule:
            v = "BlockData (型別,最小長度,最大長度,筆數)：" + "; ".join(f"({t},{a},{b},{n})" for t, a, b, n in q("select ParamDataType,min(ParamDataSize),max(ParamDataSize),count(*) from BlockData group by 1")) + "；NamedConfigData：" + "; ".join(f"({t},{a},{b},{n})" for t, a, b, n in q("select ParamDataType,min(ParamDataSize),max(ParamDataSize),count(*) from NamedConfigData group by 1"))
        elif "49710" in rule and "目前仍有效" in rule:
            v = verify["49710"]
        elif "ConfigType" in rule and "'T'" in rule:
            v = "NamedConfigs (ConfigType,H275,筆數)：" + "; ".join(f"({c},{h},{n})" for c, h, n in q("select ConfigType,H275,count(*) from NamedConfigs group by 1,2"))
        elif "BlockType" in rule and "RESOURCE" in rule:
            v = "Blocks (BlockType,筆數)：" + "; ".join(f"('{b}',{n})" for b, n in q("select BlockType,count(*) from Blocks group by 1"))
        elif "IdentStatus" in rule and "identified" in rule:
            v = "DeviceLocation (IdentStatus,SisStatus,筆數)：" + "; ".join(f"({a},{b},{n})" for a, b, n in q("select IdentStatus,SisStatus,count(*) from DeviceLocation group by 1,2"))
        elif "DispositionId" in rule and "Spare" in rule:
            v = "Devices (DispositionId,筆數)：" + "; ".join(f"({a},{n})" for a, n in q("select DispositionId,count(*) from Devices group by 1"))
        elif "ParamKind" in rule and "frsi.DeviceAlarm" in rule:
            v = "BlockData ParamKind：" + "; ".join(f"{a}:{n}" for a, n in q("select ParamKind,count(*) from BlockData group by 1")) + "；NamedConfigData：" + "; ".join(f"{a}:{n}" for a, n in q("select ParamKind,count(*) from NamedConfigData group by 1")) + " (BlockData 無 D 列；D 僅出現於範本 NamedConfigData 的 frsi.DeviceAlarm.* 警報設定)"
        elif "ValueMode" in rule:
            v = "BlockData ValueMode：" + "; ".join(f"{a}:{n}" for a, n in q("select ValueMode,count(*) from BlockData group by 1")) + "；NamedConfigData：" + "; ".join(f"{a}:{n}" for a, n in q("select ValueMode,count(*) from NamedConfigData group by 1"))
        elif "AlertList" in rule and "全為空" in rule:
            v = "AlertList/AlertLog/DeviceMonitorList/AlertFilterForDevice 列數：" + ", ".join(str(rowcount[t]) for t in ["AlertList", "AlertLog", "DeviceMonitorList", "AlertFilterForDevice"])
        rows.append({"規則類別": cat, "規則": rule, "出處模組": src, "證據片段": ev[:200], "信心": conf, "資料驗證": v})
    df_rules = pd.DataFrame(rows)

    # ---------------- Sheet 5: 代碼對照表
    rows = []
    for tbl, kcol, ncol, dcol in LOOKUPS:
        sel = f'select "{kcol}", "{ncol}"' + (f', "{dcol}"' if dcol else "") + f' from "{tbl}"'
        for rec in q(sel):
            k = rec[0]
            name = rec[1]
            d = rec[2] if dcol else None
            zh = ZH_LOOKUP.get((tbl, str(k)), "")
            if tbl == "EventCategories":
                zh = ZH_EVENTCAT.get(int(k), "")
            rows.append({"代碼表 (table)": tbl, "代碼 (key)": str(k), "名稱": name, "說明": (str(d) if d is not None else ""), "中文": zh,
                         "鍵欄位": kcol, "用於欄位": {
                             "EventCategories": "EventLog.Category", "AlertTypes": "AlertLog.AlertTypeId / DeviceAlertDesc.AlertTypeId",
                             "Dispositions": "Devices.DispositionId / Blocks.DispositionId", "DeviceProtocols": "MfrProtocols.ProtocolId",
                             "PermissionClassification": "Privileges_Permission.Classification", "SecurityType": "Principals_GroupWindowsPrincipal.CreateType",
                             "ServiceReasons": "TestResults.ServiceId", "MobileDeviceTypes": "MobileDevices.MobDevTypeId", "PolicyTypes": "Policies.PolicyTypeId",
                             "Labels": "AreaLevels.AreaLabelId / Hierarchies.LabelId", "SnapOnDataOwners": "SnapOnData.SnapOnDataOwnerId",
                             "MajorDeviceCategories": "DeviceCategories.MajorDeviceCategoryId", "MinorDeviceCategories": "DeviceCategories.MinorDeviceCategoryId",
                             "PlantLocations_Scope": "Grants.PlantLocationId / Hierarchies.AreaIdentifier", "Users": "EventLog.UserKey",
                             "Hierarchies": "Components.AreaId", "SystemDefaults": "(系統設定)"}.get(tbl, "")})
    # EventLog Type (推得) + ParamDataType + ValueMode + ConfigType + BlockType + ComputerId top
    extra = [
        ("EventLog.Type (程式碼+資料推得)", "0", "其他/未分類", "Create User Config 等", "其他"),
        ("EventLog.Type (程式碼+資料推得)", "1", "組態變更", "Category 1 AMS 變更 / 28 Field change / 53", "組態變更 (列入稽核)"),
        ("EventLog.Type (程式碼+資料推得)", "2", "校正/測試方案", "Category 49 Change Test Scheme assignment (本廠 1,642 筆全為 49)", "校正/測試方案 (列入稽核)"),
        ("EventLog.Type (程式碼+資料推得)", "3", "資料庫維護", "Category 14/52/16/12 Database Maintenance", "資料庫維護 (列入稽核)"),
        ("EventLog.Type (程式碼+資料推得)", "4", "應用程式/系統", "登入/登出、掃描開始/完成、AMS 啟動、重建階層", "系統事件 (列入稽核)"),
        ("EventLog.Type (程式碼+資料推得)", "5", "StatusAlert", "AmsSp_AL_ProcessNotifyAlertLogInsert_1: if (@nType <> 5) return -3", "狀態警報 (本廠 0 筆)"),
        ("EventLog.Type (程式碼+資料推得)", "6", "範本/裝置型別建立", "AmsMergeDoc Template Configuration、Create Device Template；稽核軌跡排除", "範本匯入 (不列入稽核)"),
        ("EventLog.Type (程式碼+資料推得)", "8", "DBW_ET_DEVICE_SCAN", "AmsSp_DevBlk_GetLastSyncTime_1: Type = 8 = 裝置掃描同步", "裝置同步 (列入稽核)"),
        ("EventLog.Type (程式碼+資料推得)", "9", "(稽核排除)", "AmsSp_AuditTrailSummary_*: NOT EventLog.Type = 9", "本廠無"),
        ("ParamDataType", "3", "narrow string", "AmsSp_GetBlockKeyCurrentHartInfo_1 註解", "窄字串 ASCII（本庫僅 FF 十六進位容器使用，Archived=1）"),
        ("ParamDataType", "4", "Long", "4 位元組；工作簿 vtype=Long", "32 位元整數 little-endian"),
        ("ParamDataType", "5", "(範本限定)", "4 位元組；僅 NamedConfigData 69 筆", "推測無號整數 (未確認)"),
        ("ParamDataType", "6", "Float", "4 位元組；工作簿 vtype=Float", "IEEE 754 單精度 little-endian"),
        ("ParamDataType", "7", "(範本限定)", "8 位元組；僅 NamedConfigData 10 筆 (totalizer preset)", "推測雙精度/64 位元 (未確認)"),
        ("ParamDataType", "8", "Time", "8 位元組 double；date.000000A6", "OLE 日期序號 double (1899-12-30 起算天數)"),
        ("ParamDataType", "9", "Binary", "變長 2~57 位元組；read_loop_status_data", "原始位元組/位元串"),
        ("ParamDataType", "12", "TString (Generic string)", "AmsSp_GetNonDDHistoricalConfigList_1: ParamDataType = 12 (TString)", "UTF-16LE 寬字串"),
        ("ValueMode", "h", "history", "AmsSp_GetNamedConfigParamValueMode_1", "已設定/納入歷史"),
        ("ValueMode", "o", "off", "AmsSp_GetNamedConfigParamValueMode_1", "關閉/未包含於組態"),
        ("ParamKind", "P", "Parameter", "AmsSp_DeviceBlocks_GetBlockData_1", "DD 參數"),
        ("ParamKind", "D", "Device alarm / Non-DD", "AmsSp_GetNonDDHistoricalConfigList_1", "frsi.DeviceAlarm.* 警報設定"),
        ("NamedConfigs.ConfigType", "T", "Template", "AmsSp_CreateUserConfiguration_1", "範本 (H275=1 為使用者/手持器格式)"),
        ("NamedConfigs.ConfigType", "C", "Characteristics", "AmsSp_Device_GetCharTemplateName_1", "特性範本 (每型號版本一筆)"),
        ("NamedConfigs.ConfigType", "S", "(H275)", "資料：10 筆皆 H275=1", "手持器範本"),
        ("Blocks.BlockType", "", "device level", "AmsSp_Blocks_GetAddId_1", "裝置層級 (BlockIndex 0)"),
        ("Blocks.BlockType", "R", "RESOURCE", "AmsUdf_GetFFBlockName", "FF 資源區塊"),
        ("Blocks.BlockType", "T", "TRANSDUCER<n>", "AmsUdf_GetFFBlockName", "FF 轉換器區塊"),
        ("Blocks.BlockType", "F", "FUNCTION<n>", "AmsUdf_GetFFBlockName", "FF 功能區塊 (AI/AO/PID…)"),
        ("DeviceLocation.IdentStatus", "0", "unknown", "AmsUdf_DevBlkIdentStatusAsString", "未識別"),
        ("DeviceLocation.IdentStatus", "1", "identified", "AmsUdf_DevBlkIdentStatusAsString", "已識別"),
        ("DeviceLocation.SisStatus", "0", "BPCS", "AmsVw_EF_Device", "一般儀器"),
        ("DeviceLocation.SisStatus", "1/2", "SIS", "AmsVw_EF_Device", "安全儀控裝置"),
        ("Assets.Discriminator", "1", "real device", "AmsSp_CreateDeviceAsset_1", "實體裝置"),
        ("Assets.Discriminator", "2", "virtual device", "AmsSp_CreateVirtualDeviceAsset", "虛擬裝置"),
        ("HART AlertId", "0100000000000000", "PV out of limits", "AmsUdf_GetHartAlertId", "主變數超限"),
        ("HART AlertId", "0200000000000000", "Non-PV out of limits", "AmsUdf_GetHartAlertId", "非主變數超限"),
        ("HART AlertId", "0400000000000000", "PV analog output saturated", "AmsUdf_GetHartAlertId", "類比輸出飽和"),
        ("HART AlertId", "0800000000000000", "PV analog output fixed", "AmsUdf_GetHartAlertId", "類比輸出固定"),
        ("HART AlertId", "1000000000000000", "More status available", "AmsUdf_GetHartAlertId", "更多狀態可用"),
        ("HART AlertId", "2000000000000000", "Cold start", "AmsUdf_GetHartAlertId", "冷啟動"),
        ("HART AlertId", "4000000000000000", "Configuration changed", "AmsUdf_GetHartAlertId", "組態已變更"),
        ("HART AlertId", "8000000000000000", "Field device malfunction", "AmsUdf_GetHartAlertId", "現場裝置故障"),
        ("HART AlertId", "0001000000000000", "Device Not Responding", "AmsUdf_GetHartAlertId", "裝置無回應"),
        ("哨兵值", "49710", "EventIdDayOut 目前有效", "AmsSp_AssignDevTag_1", "2036-02-05"),
        ("哨兵值", "25569", "EventIdDay 未設定", "EventLog 首筆/TestDefinitionHistory", "1970-01-01"),
        ("哨兵值", "-1", "Default unknown (do not remove)", "各主檔", "預設未知列"),
        ("安全範圍 GUID", "81C7311F-D829-4CDD-961A-A3E3A25D013F", "Site-wide", "AmsSp_HasPermission", "全廠"),
        ("安全範圍 GUID", "10F82026-03C4-4D47-9C9C-26F2F89B3F5D", "Unassigned", "AmsSp_HasPermission", "未指派裝置"),
        ("安全範圍 GUID", "3CFEC380-CC46-4D45-9A8B-09835D316AA9", "Manufacturer", "AmsSp_HasPermission", "製造商資料夾"),
        ("安全範圍 GUID", "5DC4F174-7FF7-43BF-8EA4-A47DD4143C79", "User Configurations", "AmsSp_HasPermission", "使用者組態資料夾"),
        ("安全範圍 GUID", "87FC0717-33EC-4BA2-8A35-C7A114567A40", "System", "AmsSp_HasPermission", "系統資料夾"),
        ("特殊主體 GUID", "3044F0E9-7033-4FB0-8E8A-008D367E3A32", "AmsServiceUser", "AmsSp_CheckUserPermission", "永遠有權限"),
    ]
    for tbl, k, name, d, zh in extra:
        rows.append({"代碼表 (table)": tbl, "代碼 (key)": k, "名稱": name, "說明": d, "中文": zh, "鍵欄位": "", "用於欄位": ""})
    # ComputerId → IP 對照 (前 40)
    for c, n in q("select ComputerId, count(*) from EventLog group by 1 order by 2 desc limit 40"):
        rows.append({"代碼表 (table)": "EventLog.ComputerId→IP", "代碼 (key)": str(c), "名稱": ip_from_computerid(c) or "", "說明": f"{n} 筆事件", "中文": "host-order IPv4", "鍵欄位": "ComputerId", "用於欄位": "EventLog.ComputerId"})
    df_lookup = pd.DataFrame(rows)

    # ---------------- notes
    n_auth = int((df_mods["作者 (首見)"] != "").sum())
    sheets = [
        {"name": "資料表字典", "purpose": "AmsDb 全部 105 張資料表的用途、列數、主鍵、欄位、外鍵與被哪些 SQL 模組使用",
         "one_row": "一張資料表", "df": df_tables,
         "notes": [
             "中文說明由欄位名稱、模組原始碼註解 (601 個 view/proc/function/trigger) 與資料實際分佈推得；『未使用/本廠為空』指本備份中列數為 0。",
             f"空表 ({len(empty_tables)} 張)：" + ", ".join(empty_tables),
             "參照模組數 = 去除註解後，以完整字詞比對出現該資料表名稱的模組數 (含間接經檢視引用者不計)。",
             "領域分類為本文件自訂 (裝置/位號/參數/組態/事件/警報/校正/安全/階層/網路/型號/資產/行動/專案/健康/代碼/系統)。",
             "鍵值 -1 列為『Default unknown (do not remove)』哨兵，統計裝置數時應扣除 (Devices 1,929 列 = 1,928 台 + 1)。",
         ],
         "source_tables": ["_schema", "_tables", "_foreign_keys", "_modules"]},
        {"name": "欄位字典", "purpose": "全部 535 個欄位的型別、可空、主鍵、外鍵目標與中文意義",
         "one_row": "一個欄位", "df": df_cols,
         "notes": [
             "型別長度依 SQL Server max_length 換算 (nvarchar 以字元數表示；-1 = max)。",
             "中文意義僅在可由程式碼/資料確認時填寫，空白表示未能確認。",
             "EventIdDay/EventIdFraction 在所有表中意義相同 (OLE 日期整數日 / 當日比例×2^31)，見『關鍵語意規則』。",
             "『參照此欄的模組數』= 有引用該資料表且原始碼中出現此欄位名稱的模組數 (同名欄位跨表時會高估)。",
         ],
         "source_tables": ["_schema", "_foreign_keys", "_modules"]},
        {"name": "視圖與程序", "purpose": "601 個 SQL 模組 (104 檢視、461 預存程序、23 函數、13 觸發器) 的用途、作者/日期、參照資料表與呼叫關係",
         "one_row": "一個 SQL 模組 (view / procedure / function / trigger)", "df": df_mods,
         "notes": [
             f"作者/日期自 CREATE 之前的註解區塊擷取 (格式如 '-- Joe Fisher, 06/14/01'、'Author --/Nghy Hong/9/25/06')；可解析出作者者 {n_auth} 個，其餘 (多為 EF/UM 系列檢視、觸發器) 無註解。",
             "日期為 Emerson 原廠開發日期 (2000~2019)，非本廠事件；$Revision 為原廠版控關鍵字；日期欄無時區 (非事件時間)。",
             "資料庫結構版本 __version 最新為 5.1 (2018-03-13, V14.1.1)；模組總數 601 = 461 程序 + 104 檢視 + 21 純量函數 + 2 資料表函數 + 13 觸發器。",
             "中文摘要：關鍵模組為人工撰寫；其餘由名稱字詞 glossary 機械翻譯 (僅供索引)，請對照『描述 (原文首段)』。",
             "參照資料表/其他模組 = 去除註解後完整字詞比對；動態 SQL (EXEC 字串) 內的引用也會被比對到。",
             "GRANT 授權陳述式不在 _modules 定義內 (僅 AmsSp_Device_GetCharTemplateName_1 內嵌一行 Grant Execute … to AmsDbUser, AmsDbViewer)，故不列 Grant 欄；AmsDbUser (讀寫)、AmsDbViewer (唯讀) 為 AMS 應用程式使用的資料庫角色。",
         ],
         "source_tables": ["_modules", "_tables"]},
        {"name": "關鍵語意規則", "purpose": "從程式碼萃取的解碼規則 (時間、哨兵、參數型別、事件/警報代碼、安全 GUID)，供其他領域解碼核對",
         "one_row": "一條解碼規則 (含出處模組、逐字證據、信心與本資料庫驗證結果)", "df": df_rules,
         "notes": [
             "信心 高 = 程式碼明文 + 資料驗證；中 = 程式碼部分明示 + 資料推論；低 = 僅推測。",
             "EventLog.Type 只有 5 與 8 在程式碼有明文，其餘型別意義由 Category/Source/Description 分佈推得 (信心中)。",
             "ParamDataType 5/7 僅出現在範本 NamedConfigData，未在程式碼或前次匯出中出現，型別為推測。",
             "ComputerId 解碼以 127.0.0.1 = 2130706433 及前次工作簿 17_使用者與電腦 的 IP 清單交叉驗證。",
         ],
         "source_tables": ["_modules", "EventLog", "BlockData", "NamedConfigData", "NamedConfigs", "Blocks", "DeviceLocation", "Devices", "BlockAsgms", "TestDefAsgms"]},
        {"name": "代碼對照表", "purpose": "所有小型代碼表 (事件類別、警報種類、處置、協定、權限分類…) 與程式碼內建代碼 (Type、ParamDataType、ValueMode、BlockType、AlertId、GUID、ComputerId→IP) 的彙整",
         "one_row": "一個代碼值", "df": df_lookup,
         "notes": [
             "資料表代碼直接取自資料庫；『程式碼+資料推得』類的來源為本文件『關鍵語意規則』。",
             "EventCategories 中文為本文件翻譯；-1~18 為系統保留不可更動。",
             "ComputerId→IP 僅列事件數前 40 名；172.16.201.131 為 AMS1SVR 本機 (17,695 筆)，155.177.x.x/10.x 等多為 Emerson 原廠隨附範本事件的來源電腦。",
         ],
         "source_tables": ["EventCategories", "AlertTypes", "Dispositions", "DeviceProtocols", "PermissionClassification", "SecurityType", "ServiceReasons",
                           "MobileDeviceTypes", "PolicyTypes", "Labels", "SnapOnDataOwners", "MajorDeviceCategories", "MinorDeviceCategories",
                           "PlantLocations_Scope", "Users", "Hierarchies", "SystemDefaults", "EventLog", "_modules"]},
    ]
    return sheets


if __name__ == "__main__":
    import os
    import time

    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    conn = sqlite3.connect(DB)
    sheets = build(conn)
    for s in sheets:
        df = s["df"]
        print(f"{s['name']}: {len(df)} rows x {len(df.columns)} cols")
        for c in df.columns:
            if df[c].map(lambda v: isinstance(v, (bytes, bytearray))).any():
                raise SystemExit(f"raw bytes in {s['name']}.{c}")
        df.to_csv(os.path.join(OUT, f"{KEY}__{s['name']}.csv"), index=False, encoding="utf-8-sig")
    print(f"done in {time.time() - t0:.1f}s")
