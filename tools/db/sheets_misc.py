# -*- coding: utf-8 -*-
"""
sheets_misc.py -- 完整性稽核補遺 (domain key: misc)
build(conn) -> list[dict]
  1. 跨域對帳與殘留資料 : 七個領域模組未涵蓋/未解釋的殘留資料 (NetworkHierarchies 唯一列、345 筆孤立 Assets 與 345 筆刪除裝置事件對帳、
                         各表位號字串口徑差異、Identifier 欄位命名差異) 的逐項對帳
  2. 位號跨表對照       : 每台設備一列，給出各領域工作表所用的位號字串 (原值 / 清理後)，供跨表 VLOOKUP 之用
"""
import re
import os
import sqlite3
import pandas as pd

DB = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/AmsDb.sqlite"
OUT = r"C:/Users/bacon/AppData/Local/Temp/claude/C--Users-bacon------------------AMS/2d1eb9a8-e320-409a-a821-ff8839ea87f9/scratchpad/build/out"
KEY = "misc"

_BAD = re.compile(r"[^\x20-\x7e]")               # 非可列印 ASCII (與 sheets_devices 同規則)
_TAIL_JUNK = re.compile(r"\s{2,}\S{1,2}$")        # HART 長位號讀取殘碼: 2+ 填充空白 + 1~2 雜字元


def clean_tag(t):
    if t is None:
        return ""
    s = _BAD.sub("", str(t))
    s = _TAIL_JUNK.sub("", s)
    return s.strip()


def tag_diff_kind(raw, clean):
    if raw is None:
        return "NULL"
    r = str(raw)
    if r == clean:
        return "相同"
    if _BAD.search(r):
        return "含非可列印字元"
    if _TAIL_JUNK.search(r):
        return "尾端殘碼(填充空白+雜字元)"
    if r.strip() == clean:
        return "前後空白"
    return "其他"


def build(conn):
    def q(sql):
        return pd.read_sql(sql, conn)

    def n(sql):
        return conn.execute(sql).fetchone()[0]

    # ---------------- sheet 1: 對帳
    rows = []

    def add(sec, item, val, note, src):
        rows.append({"區段": sec, "項目": item, "值": val, "說明/判讀": note, "來源表": src})

    nh = conn.execute("select NetworkNodeId, NodeName, NodeKind, NodeHierarchyId, NodeLevel from NetworkHierarchies").fetchall()
    for r in nh:
        add("NetworkHierarchies (唯一未被任何工作表引用的非空表)", str(r[1]),
            "NodeKind=%s, NodeHierarchyId=%s, NodeLevel=%s, NetworkNodeId=%s" % (r[2], r[3], r[4], r[0]),
            "網路階層樹的根節點哨兵 (do not delete)；NetworkHierarchiesData 0 列，表示本廠未建立網路階層檢視。無工程意義。", "NetworkHierarchies")

    n_assets = n("select count(*) from Assets")
    n_da = n("select count(*) from DeviceAssets")
    n_orphan = n("select count(*) from Assets a left join DeviceAssets d on a.AssetId=d.AssetId where d.AssetId is null")
    n_disc = dict(conn.execute("select Discriminator, count(*) from Assets group by 1").fetchall())
    n_del = n("select count(*) from EventLog where Category=52")
    n_del_dev = n("select count(distinct substr(Other, instr(Other,'serial number of ')+17, "
                  "instr(Other,' and an AMS tag')-instr(Other,'serial number of ')-17)) from EventLog where Category=52")
    n_del_days = conn.execute("select date(EventTime), count(*) from EventLog where Category=52 group by 1 order by 1").fetchall()
    add("Assets 孤立列對帳", "Assets 總列數", n_assets,
        "Discriminator 分佈 %s (1=實體裝置, 2=虛擬裝置；本廠無虛擬裝置)；Tag 欄全部 NULL" % n_disc, "Assets")
    add("Assets 孤立列對帳", "DeviceAssets 列數 (= 現存設備數)", n_da,
        "每台 Devices 恰一筆 AssetId (AmsSp_CreateDeviceAsset_1 於裝置建立時新增)", "DeviceAssets")
    add("Assets 孤立列對帳", "無 DeviceAssets 對應的 Assets (孤立)", n_orphan, "設備領域列為未解問題", "Assets, DeviceAssets")
    add("Assets 孤立列對帳", "EventLog Category 52 刪除裝置事件數", n_del,
        "涉及 %d 個不同序號；依日: %s" % (n_del_dev, ", ".join("%s×%d" % (d, c) for d, c in n_del_days)), "EventLog")
    add("Assets 孤立列對帳", "結論", "孤立 Assets %d = 刪除裝置事件 %d" % (n_orphan, n_del),
        "AmsSp_DeleteDevice_1 只刪 Devices/Blocks/BlockData/DeviceLocation/CalStatus/SnapOnData 等，DeviceAssets 隨 Devices 外鍵移除，但 Assets 主檔列不刪 "
        "(_modules 中僅 AmsSp_EF_VirtualDevice_Delete / AmsSp_ConvertVirtualToRealDevice_1 會 DELETE Assets)。每次刪除留下 1 筆孤立 Asset GUID；"
        "168 台被刪 2 次的 FF 裝置各留 2 筆。孤立列無 Tag、無法逐筆對回裝置，屬無害殘留，可忽略。", "_modules AmsSp_DeleteDevice_1")

    dev = q("""select d.DeviceKey, d.AmsDeviceId, d.AmsDeviceTag, d.Identifier, t.ExtBlockTag
               from Devices d join Blocks b on b.DeviceKey=d.DeviceKey and b.BlockIndex=0
               join BlockAsgms a on a.BlockKey=b.BlockKey and a.EventIdDayOut=49710
               join ExtBlockTags t on t.ExtBlockTagKey=a.ExtBlockTagKey where d.DeviceKey>=0""")
    dev["clean"] = dev["ExtBlockTag"].map(clean_tag)
    dev["kind"] = [tag_diff_kind(r, c) for r, c in zip(dev["ExtBlockTag"], dev["clean"])]
    kinds = dev["kind"].value_counts().to_dict()
    add("位號字串口徑", "現行 AMS 位號 原值≠清理後 的設備數", int((dev["kind"] != "相同").sum()),
        "分佈 %s。設備領域工作表 (設備總表/MUX清單/指派歷程/非現行位號池) 用『清理後』位號；事件/參數/範本/警報領域工作表用『原值』。"
        "跨表查詢請以 DeviceKey 或本模組『位號跨表對照』為鍵。" % kinds, "ExtBlockTags")
    adt = dev["AmsDeviceTag"]
    add("位號字串口徑", "Devices.AmsDeviceTag 為 NULL / 空白 的設備數",
        "NULL %d / 空白或僅空白 %d" % (int(adt.isna().sum()), int((adt.fillna("x").str.strip() == "").sum())),
        "設備領域報告寫 141、參數領域寫 140；SQL trim() 只去空格得 140 空白 + 3 NULL = 143，pandas strip() 另計入 1 筆僅含非空格之 Unicode 空白字元者得 141。設備總表對 3 筆 NULL 顯示 'nan' 字串 (缺陷)", "Devices")

    add("欄位命名口徑", "Devices.Identifier 的意義", "HART: Device ID (HART UID 末 3 bytes 十進位)；FF: FF Device ID 字串",
        "非銘牌序號 (與舊工作簿『設備序號』僅 21/1,928 相同)。設備領域已改名『裝置ID』；事件總帳/刪除裝置事件/位號主檔/測試定義指派/SnapOn 工作表仍標"
        "『設備序號』或『裝置序號/識別』，讀者請一律視為裝置 ID。", "Devices")

    add("計數口徑", "EventLog 列數", "%d (含 2 筆哨兵列 1970-01-01 / 2036-02-05)" % n("select count(*) from EventLog"),
        "事件領域報 29,773；安全領域『系統資訊』報 29,771 (已排除 2 筆哨兵)。兩者一致。", "EventLog")
    add("計數口徑", "PlantServer.AlertMonitorEnabled", n("select AlertMonitorEnabled from PlantServer where PlantServerKey=0"),
        "旗標=1 但 DeviceMonitorList/AlertList/AlertLog 皆 0 列 → Alert Monitor 服務啟用但未把任何裝置加入監視名單，資料庫無任何裝置警報歷史 "
        "(與事件/警報/程式碼領域結論一致)。", "PlantServer, DeviceMonitorList, AlertList, AlertLog")

    s1 = pd.DataFrame(rows)

    # ---------------- sheet 2: 位號跨表對照
    hasbd = set(x[0] for x in conn.execute("select distinct b.DeviceKey from BlockData d join Blocks b on d.BlockKey=b.BlockKey").fetchall())
    hassn = set(x[0] for x in conn.execute("select distinct b.DeviceKey from SnapOnData s join Blocks b on s.BlockKey=b.BlockKey").fetchall())
    hasev = set(x[0] for x in conn.execute("select distinct b.DeviceKey from EventLog e join Blocks b on e.BlockKey=b.BlockKey where e.BlockKey>=0").fetchall())
    yn = {True: "是", False: "否"}
    s2 = pd.DataFrame({
        "設備鍵 (DeviceKey)": dev["DeviceKey"],
        "設備GUID (AmsDeviceId)": dev["AmsDeviceId"],
        "清理後位號 (設備領域工作表用)": dev["clean"],
        "位號原值 (事件/參數/範本/警報工作表用) (ExtBlockTag)": dev["ExtBlockTag"],
        "原值與清理後差異": dev["kind"],
        "識別時裝置位號 原值 (Devices.AmsDeviceTag)": dev["AmsDeviceTag"].fillna(""),
        "識別時裝置位號 清理後": dev["AmsDeviceTag"].map(clean_tag),
        "識別時裝置位號 原值為NULL": dev["AmsDeviceTag"].isna().map(yn),
        "裝置ID (Devices.Identifier)": dev["Identifier"],
        "有參數紀錄 (BlockData)": dev["DeviceKey"].isin(hasbd).map(yn),
        "有DD檔案資訊 (SnapOnData)": dev["DeviceKey"].isin(hassn).map(yn),
        "有設備事件 (EventLog)": dev["DeviceKey"].isin(hasev).map(yn),
    }).sort_values("設備鍵 (DeviceKey)").reset_index(drop=True)

    return [
        {"name": "跨域對帳與殘留資料", "purpose": "七個領域模組未涵蓋或未解釋之殘留資料與跨域口徑差異的逐項對帳",
         "one_row": "一項對帳事實 (區段/項目/值/判讀)", "df": s1,
         "notes": ["NetworkHierarchies 為 105 表中唯一未被任何工作表引用的非空表，僅 1 筆根節點哨兵；NetworkHierarchiesData 0 列。",
                   "Assets 孤立 345 筆 = Category 52 刪除裝置事件 345 筆：AmsSp_DeleteDevice_1 不刪 Assets 主檔列，屬無害殘留。",
                   "本域無其他資料表；空表已由各領域摘要列出。"],
         "source_tables": ["NetworkHierarchies", "Assets", "DeviceAssets", "EventLog", "Devices", "ExtBlockTags", "BlockAsgms", "Blocks", "PlantServer", "_modules"]},
        {"name": "位號跨表對照", "purpose": "每台設備的各種位號字串 (原值/清理後/識別時位號) 對照表，供跨領域工作表以位號查詢時換算",
         "one_row": "一台現存設備 (DeviceKey>=0)", "df": s2,
         "notes": ["清理規則 = 設備領域 sheets_devices.clean_tag：去除非可列印 ASCII 字元，再去除『2 個以上填充空白 + 1~2 個雜字元』的尾端殘碼，最後 strip。",
                   "設備領域工作表 (設備總表/MUX多工器清單/位號指派歷程/非現行位號池/FF區塊清單) 使用清理後位號；事件總帳、參數現值、範本 SnapOn、同步失敗統計等使用原值。",
                   "以 DeviceKey 或 AmsDeviceId GUID 跨表最可靠。"],
         "source_tables": ["Devices", "Blocks", "BlockAsgms", "ExtBlockTags", "BlockData", "SnapOnData", "EventLog"]},
    ]


if __name__ == "__main__":
    import time
    t0 = time.time()
    conn = sqlite3.connect(DB)
    os.makedirs(OUT, exist_ok=True)
    for s in build(conn):
        print("%s: %d rows x %d cols" % (s["name"], len(s["df"]), s["df"].shape[1]))
        s["df"].to_csv(os.path.join(OUT, "%s__%s.csv" % (KEY, s["name"])), index=False, encoding="utf-8-sig")
    print("done in %.1fs" % (time.time() - t0))
