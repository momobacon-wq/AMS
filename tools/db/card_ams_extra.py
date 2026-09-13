# -*- coding: utf-8 -*-
"""
card_ams_extra.py -- 02_設備查詢卡 新增的 AMS DB 資訊 (每台設備, alias 鍵), 每個值附來源

用法:
  py tools/db/card_ams_extra.py <AmsDb.sqlite> <out ams.json> [備份日 2026-09-12] [--sheets docs/db/data/sheets]

輸出:
  { "kind":"ams", "backup_date":"2026-09-12",
    "by_alias": { "D00298": { "sync":[[欄位,值,lvl,來源],...], "change":[...], "ident":[...],
                              "device":[...], "alarm":[...], "ff":[...],
                              "dcs_writes": {"URV":[值,時間,事件,使用者,前值,參數,之後是否被非DCS改寫,AMS現值], ...},
                              "flags": {"last_change_dcs":bool, "has_dcs_write":bool, "sync_unrecovered":bool} } },
    "groups": {群組: 中文標題}, "stats": {...} }

lvl: raw 原始 / decoded 解碼 / inferred 推論 (doc/factory 由文件比對產生器使用)
alias -> DeviceKey 取自 03.json (第1欄 alias, 第2欄 DeviceKey); SQLite 以唯讀 (mode=ro) 開啟。
解碼函式沿用 sheets_params.py (decode_hart / decode_ff / translate / _value_key)。
"""
import os, sys, json, struct, re, sqlite3, datetime, math
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sheets_params import decode_hart, decode_ff, translate, _value_key, KEY_CONFIG, URV_NAMES, LRV_NAMES, FF_UNITS  # noqa: E402

TW = datetime.timedelta(hours=8)
FLT_MIN = 1.1754943508222875e-38
LVL_ZH = {"raw": "原始", "decoded": "解碼", "inferred": "推論"}
GROUPS = {"sync": "維護狀態", "change": "最後修改", "ident": "位號歷程補充", "device": "設備補充",
          "alarm": "類比輸出警報", "ff": "FF 診斷"}
CAT_KIND = {28: "DCS·外部主機 (Cat28)", 1: "人工 AMS (Cat1)", 2: "人工 AMS 巡檢站 (Cat2)", 0: "離線/無 (Cat0)"}

FF_UNITS_EXTRA = {1142: "psia", 1143: "psig", 1130: "Pa", 1137: "bar", 1138: "mbar", 1147: "inH2O(4°C)", 1148: "inH2O(68°F)",
                  1150: "mmH2O(4°C)", 1156: "inHg(0°C)", 1158: "mmHg(0°C)", 1018: "m", 1019: "cm", 1013: "mm", 1034: "m3",
                  1349: "m3/h", 1324: "kg/h", 1000: "K", 1243: "mV", 1211: "mA", 1240: "V"}
FF_NAMES = {
    "8002018e:00": "WRITE_LOCK", "80020b30:00": "FD_FAIL_ACTIVE", "80020b35:00": "FD_MAINT_ACTIVE",
    "80020b3a:00": "FD_OFFSPEC_ACTIVE", "80020b29:00": "FD_CHECK_ACTIVE", "80020b3f:00": "FD_RECOMMEN_ACT",
    "80020126:01": "MODE_BLK.TARGET", "80020126:02": "MODE_BLK.ACTUAL", "80020126:03": "MODE_BLK.PERMITTED", "80020126:04": "MODE_BLK.NORMAL",
    "8002010c:00": "L_TYPE", "80020132:01": "OUT_SCALE.EU_100", "80020132:02": "OUT_SCALE.EU_0", "80020132:03": "OUT_SCALE.UNITS",
    "80020132:04": "OUT_SCALE.DECIMAL", "80020192:01": "XD_SCALE.EU_100", "80020192:02": "XD_SCALE.EU_0", "80020192:03": "XD_SCALE.UNITS",
    "80020192:04": "XD_SCALE.DECIMAL", "8002013a:00": "PV_FTIME", "80020180:00": "TAG_DESC", "80020b57:00": "SOFTWARE_REV (字串)",
    "800200c4:00": "DEV_REV", "800200c2:00": "DD_REV",
}
MODE_BITS = [(128, "O/S"), (64, "IMan"), (32, "LO"), (16, "Man"), (8, "Auto"), (4, "Cas"), (2, "RCas"), (1, "ROut")]
L_TYPE = {0: "未初始化", 1: "Direct 直接", 2: "Indirect 間接", 3: "Ind Sqr Root 間接開方"}
WRITE_LOCK = {0: "未初始化", 1: "未鎖定 (Not Locked)", 2: "已鎖定 (Locked)"}
FD_RECOMMEN = {0: "未初始化", 1: "無需處置 (No Action Required)"}

ALARM_PARAMS = [  # (欄位, 候選名, 單位)
    ("警報方向 (loop_alarm_code)", ["loop_alarm_code"], None),
    ("警報電流 高", ["high_alarm_level", "rmt_press_ieee_high_alarm_level"], "mA"),
    ("警報電流 低", ["low_alarm_level", "low_alarm_level_n", "rmt_press_ieee_low_alarm_level"], "mA"),
    ("飽和電流 高", ["high_saturation_level", "rmt_press_ieee_high_saturation_level"], "mA"),
    ("飽和電流 低", ["low_saturation_level", "rmt_press_ieee_low_saturation_level"], "mA"),
    ("飽和電流 高 (廠家參數)", ["varHighSaturationCurrent", "hiSaturationCurrent", "analogHigh_SaturationLimit", "varSaturationUpperAout0"], None),
    ("飽和電流 低 (廠家參數)", ["varLowSaturationCurrent", "loSaturationCurrent", "analogLow_SaturationLimit", "varSaturationLowerAout0"], None),
    ("警報/飽和類型碼 (alarm_and_saturation_level_type)", ["alarm_and_saturation_level_type"], None),
]
HART_REV = [
    ("軟體版次 (software_revision)", ["software_revision", "SoftwareRevision", "varHART_ReadUniqueIdentifier_SoftwareRevision"]),
    ("硬體版次 (hardware_revision)", ["hardware_revision", "HardwareRevision", "HO_RevisionHW_1"]),
    ("HART 通用版次 (universal_revision)", ["universal_revision", "varHART_ReadUniqueIdentifier_HartRevision"]),
    ("裝置版次 (transmitter_revision)", ["transmitter_revision", "DeviceRevision", "varHART_ReadUniqueIdentifier_DeviceRevision"]),
]
SERIAL_SKIP = {"first_good_serial_number", "not_used_measurement_serial_number"}
# 動態/量測/計數值: 同步時自然變動, 不算「組態修改」(否則 Cat28 同步上傳 pv_value/運轉時數 會被誤標為 DCS 寫入)
DYNAMIC_RE = re.compile(r"^(pv|sv|tv|qv)_value$|UpdatePeriod$|^OperatingHours|^fManual(Pos|Sig)$|^nIPOutput$|Timestamp(_\d+)?$"
                        r"|Max(Resetable)?(_\d+)?$|Min(Resetable)?(_\d+)?$|Counter(_\d+)?$|^device_type$|digital_setpoint_value$|^var(Signal|ATC)Header_")
DYNAMIC_FF = {"80020b30:00", "80020b35:00", "80020b3a:00", "80020b29:00", "80020b3f:00", "80020126:02"}  # FD_*_ACTIVE / RECOMMEN / MODE.ACTUAL


# ----------------------------------------------------------------------------- helpers
def src(lvl, text, when=None):
    s = LVL_ZH[lvl] + " · " + text
    if when is not None:
        s += " · " + when.strftime("%Y-%m-%d %H:%M")
    return s


def row(field, value, lvl, source):
    return [field, value, lvl, source]


def blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def fmt_num(v, dtype=None):
    """float32 → 7 位有效數字; FLT_MIN 哨兵 → 未使用; 整數照原樣"""
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "INF" if v > 0 else "-INF"
        if abs(abs(v) - FLT_MIN) < 1e-45:
            return "未使用"
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        s = "%.7g" % v
        if "e" in s:
            return s
        return s.rstrip("0").rstrip(".") if "." in s else s
    return str(v)


def disp(num, text, date, hx=None):
    if text is not None:
        t = text.rstrip("\x00")
        return "—" if t.strip() == "" else t.strip()
    if date is not None:
        return date.strftime("%Y-%m-%d %H:%M:%S")
    if num is None:
        return ("0x" + hx) if hx else "—"
    return fmt_num(num)


def parse_utc(s):
    if s is None:
        return None
    s = str(s)[:19]
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def ip_of(v):
    if v is None:
        return None
    v = int(v)
    if v == -1:
        return None
    u = v & 0xFFFFFFFF
    return f"{(u >> 24) & 255}.{(u >> 16) & 255}.{(u >> 8) & 255}.{u & 255}"


def mode_zh(code):
    if code is None:
        return "—"
    code = int(code)
    names = [n for b, n in MODE_BITS if code & b]
    return ("+".join(names) if names else "無") + f" ({code})"


def ff_unit(code):
    if code is None:
        return None
    return FF_UNITS.get(int(code)) or FF_UNITS_EXTRA.get(int(code))


def blk_label(bt, bi, is_ai=False):
    if not bt:
        return "設備層"
    return f"{bt}{bi}" + (" (AI)" if is_ai else "")


# ----------------------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:]]
    sheets_dir = os.path.normpath(os.path.join(HERE, "..", "..", "docs", "db", "data", "sheets"))
    if "--sheets" in args:
        i = args.index("--sheets"); sheets_dir = args[i + 1]; del args[i:i + 2]
    if len(args) < 2:
        print(__doc__); sys.exit(2)
    db_path, out_path = args[0], args[1]
    backup = datetime.datetime.strptime(args[2] if len(args) > 2 else "2026-09-12", "%Y-%m-%d")

    d03 = json.load(open(os.path.join(sheets_dir, "03.json"), encoding="utf-8"))
    alias_of = {int(r[2]): r[1] for r in d03["rows"]}
    proto_of = {int(r[2]): r[21] for r in d03["rows"]}

    uri = "file:" + db_path.replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    q = lambda s, p=(): conn.execute(s, p).fetchall()

    blocks = {bk: (dk, bt or "", bi) for bk, dk, bi, bt in q("select BlockKey, DeviceKey, BlockIndex, BlockType from Blocks where BlockKey>=0")}
    users = {k: n for k, n in q("select UserKey, UserName from Users")}
    ident = {dk: idf for dk, idf in q("select DeviceKey, Identifier from Devices where DeviceKey>=0")}

    events = {}      # (day,frac) -> dict
    dev_events = defaultdict(list)
    for day, frac, et, uk, cid, bk, cat, desc, other in q(
            "select EventIdDay, EventIdFraction, EventTime, UserKey, ComputerId, BlockKey, Category, Description, Other from EventLog"):
        utc = parse_utc(et)
        e = {"seq": int(day) * 2147483648 + int(frac), "tw": (utc + TW) if utc else None, "user": users.get(uk),
             "ip": ip_of(cid), "bk": bk, "cat": cat, "desc": desc, "other": other}
        events[(day, frac)] = e
        if bk is not None and bk >= 0 and bk in blocks:
            dev_events[blocks[bk][0]].append(e)

    out = {dk: defaultdict(list) for dk in alias_of}
    dcs_writes = defaultdict(dict)
    flags = defaultdict(dict)
    st = defaultdict(int)

    # ======================================================= sync 維護狀態
    plant_last = None
    for dk in alias_of:
        evs = [e for e in dev_events.get(dk, []) if e["cat"] in (43, 44, 45)]
        for e in evs:
            if e["tw"] and e["tw"].year < 2036 and (plant_last is None or e["tw"] > plant_last):
                plant_last = e["tw"]
    for dk in alias_of:
        R = out[dk]["sync"]
        evs = sorted([e for e in dev_events.get(dk, []) if e["cat"] in (43, 44, 45)], key=lambda e: e["seq"])
        ok = [e for e in evs if e["cat"] in (43, 44)]
        fail = [e for e in evs if e["cat"] == 45]
        if ok:
            e = ok[-1]; st["sync_ok"] += 1
            R.append(row("最後成功同步 (台灣)", e["tw"].strftime("%Y-%m-%d %H:%M:%S"), "decoded", src("decoded", f"EventLog Cat{e['cat']} EventTime UTC+8")))
            R.append(row("最後成功同步訊息", disp(None, e["desc"], None), "raw", src("raw", f"EventLog.Description Cat{e['cat']}", e["tw"])))
            days = (backup.date() - e["tw"].date()).days
            R.append(row("距備份日天數", f"{days} 天 (備份日 {backup:%Y-%m-%d})", "decoded", src("decoded", f"備份日 − EventLog Cat{e['cat']} 最後成功", e["tw"])))
            if days > 365:
                st["sync_ok_over_365d"] += 1
        else:
            R.append(row("最後成功同步 (台灣)", "無成功同步紀錄", "decoded", src("decoded", "EventLog Cat43/44 查無")))
        R.append(row("同步次數 成功/失敗", f"{len(ok)} / {len(fail)}", "decoded", src("decoded", "EventLog Cat43+44 / Cat45 筆數")))
        if fail:
            e = fail[-1]; st["sync_fail"] += 1
            R.append(row("最後失敗 (台灣)", e["tw"].strftime("%Y-%m-%d %H:%M:%S"), "decoded", src("decoded", "EventLog Cat45 EventTime UTC+8")))
            msg = re.sub(r"^Device/database synchronization failed:?\s*", "", e["desc"] or "").strip()
            R.append(row("最後失敗訊息", msg or "—", "raw", src("raw", "EventLog.Description Cat45", e["tw"])))
            rec = bool(ok) and ok[-1]["seq"] > e["seq"]
            R.append(row("失敗後是否再成功", "是" if rec else "否 ⚠ 失敗後未再成功同步", "decoded",
                         src("decoded", "Cat43/44 最後時間 > Cat45 最後時間 (同 22_同步失敗統計 第15欄)")))
            if not rec:
                st["sync_fail_unrecovered"] += 1; flags[dk]["sync_unrecovered"] = True
    st["plant_last_sync_tw"] = plant_last.strftime("%Y-%m-%d %H:%M:%S") if plant_last else None

    # ======================================================= BlockData 解碼
    series = defaultdict(list)   # (bk, pn) -> [rec] (h only, sorted)
    offline = defaultdict(list)
    for bk, day, frac, pn, vm, t, b in q("select BlockKey, EventIdDay, EventIdFraction, ParamName, ValueMode, ParamDataType, ParamData from BlockData"):
        if bk not in blocks:
            continue
        ff = ":" in pn
        n, s, d, dn, hx = decode_ff(b) if ff else decode_hart(int(t), b)
        e = events.get((day, frac)) or {"seq": int(day) * 2147483648 + int(frac), "tw": None, "user": None, "cat": None, "desc": None}
        base = pn.lower() if ff else pn.split(".")[0]
        if ff:
            item, mem = pn.lower().split(":")[:2]
            code = translate("FF", base, item, mem, n, s, d)
        else:
            code = translate("HART", base, "", "", n, s, d)
        rec = {"bk": bk, "pn": pn, "base": base, "num": n, "text": s, "date": d, "dtype": dn, "hx": hx, "e": e,
               "key": _value_key(n, s, d, dn), "disp": disp(n, s, d, hx), "code": code}
        (series if vm == "h" else offline)[(bk, pn)].append(rec)
    for (bk, pn), lst in offline.items():
        if (bk, pn) not in series:
            series[(bk, pn)] = lst
    latest = defaultdict(dict)   # dk -> {(bk, base): rec}
    by_dev_base = defaultdict(lambda: defaultdict(list))  # dk -> base -> [latest rec per block]
    changes = defaultdict(list)  # dk -> [(prev, cur)]
    for (bk, pn), lst in series.items():
        lst.sort(key=lambda r: r["e"]["seq"])
        dk = blocks[bk][0]
        cur = lst[-1]
        latest[dk][(bk, cur["base"])] = cur
        by_dev_base[dk][cur["base"]].append(cur)
        dyn = bool(DYNAMIC_RE.search(cur["base"])) or cur["base"] in DYNAMIC_FF
        for a, b2 in zip(lst, lst[1:]):
            if a["key"] != b2["key"]:
                if dyn:
                    st["change_pairs_skipped_dynamic"] += 1
                elif a["disp"] == b2["disp"]:
                    st["change_pairs_skipped_same_display"] += 1
                else:
                    changes[dk].append((a, b2))
    # 量程/單位 主參數 = 與 13_設備參數統計 相同規則 (該設備現有參數基底依字母排序取第一個)
    primary = {}
    for dk, bb in by_dev_base.items():
        hb = {b for b in bb if ":" not in b}
        primary[dk] = {k: (sorted(hb & names)[0] if hb & names else None)
                       for k, names in (("URV", URV_NAMES), ("LRV", LRV_NAMES), ("UNIT", KEY_CONFIG["單位"]))}

    def pdisp(r):
        v = r["disp"]
        if r["code"] and r["code"] != v:
            v = f"{v} ({r['code']})"
        return v

    def pname(r):
        bt, bi = blocks[r["bk"]][1], blocks[r["bk"]][2]
        if ":" in r["pn"]:
            nm = FF_NAMES.get(r["base"], r["base"])
            return f"{blk_label(bt, bi)} {nm}"
        return r["base"]

    def pick(dk, names, block_type=None):
        best = None
        for nm in names:
            for r in by_dev_base[dk].get(nm, []):
                if block_type is not None and blocks[r["bk"]][1] != block_type:
                    continue
                if best is None:
                    best = r
            if best is not None:
                return best
        return None

    # ======================================================= change 最後修改
    ff_scale_items = {"80020132:01": "OUT_EU100", "80020132:02": "OUT_EU0", "80020132:03": "OUT_UNITS",
                      "80020192:01": "XD_EU100", "80020192:02": "XD_EU0", "80020192:03": "XD_UNITS"}
    unit_names = KEY_CONFIG["單位"]

    def key_of(r):
        if ":" in r["pn"]:
            k = ff_scale_items.get(r["base"])
            if k:
                bt, bi = blocks[r["bk"]][1], blocks[r["bk"]][2]
                return f"{k}@{bt}{bi}"
            return None
        pr = primary.get(blocks[r["bk"]][0], {})
        for k in ("URV", "LRV", "UNIT"):
            if pr.get(k) and r["base"] == pr[k]:
                return k
        return None

    for dk in alias_of:
        R = out[dk]["change"]
        ch = changes.get(dk, [])
        if not ch:
            continue
        st["change_any"] += 1
        ch.sort(key=lambda p: p[1]["e"]["seq"])

        def emit(prefix, pairs):
            e = pairs[-1][1]["e"]
            same = [p for p in pairs if p[1]["e"]["seq"] == e["seq"]]
            kind = CAT_KIND.get(e["cat"], f"Cat{e['cat']}")
            if e["cat"] == 28:
                kind = "⚠ " + kind
            R.append(row(f"{prefix}時間 (台灣)", e["tw"].strftime("%Y-%m-%d %H:%M:%S") if e["tw"] else "—", "decoded",
                         src("decoded", "EventLog EventTime UTC+8 (BlockData 相鄰值不同)")))
            R.append(row(f"{prefix}類別", kind, "decoded", src("decoded", f"EventLog.Category {e['cat']} → EventCategories", e["tw"])))
            R.append(row(f"{prefix}事件說明", disp(None, e["desc"], None), "raw", src("raw", "EventLog.Description", e["tw"])))
            R.append(row(f"{prefix}使用者", e["user"] or "—", "raw", src("raw", "EventLog.UserKey → Users.UserName", e["tw"])))
            R.append(row(f"{prefix}變更參數數", str(len(same)), "decoded", src("decoded", "BlockData 同一事件值改變的參數數", e["tw"])))
            for a, b2 in same[:5]:
                R.append(row(f"{prefix}{pname(b2)}", f"{pdisp(a)} → {pdisp(b2)}", "decoded",
                             src("decoded", f"BlockData {b2['pn']} {b2['dtype']}", e["tw"])))
            if len(same) > 5:
                R.append(row(f"{prefix}其餘參數", "、".join(pname(p[1]) for p in same[5:15]) + (" …" if len(same) > 15 else ""), "decoded",
                             src("decoded", "BlockData 同一事件", e["tw"])))
            return e

        last_e = emit("最後修改 ", ch)
        flags[dk]["last_change_dcs"] = last_e["cat"] == 28
        if last_e["cat"] == 28:
            st["last_change_dcs"] += 1
        dcs = [p for p in ch if p[1]["e"]["cat"] == 28]
        if dcs:
            flags[dk]["has_dcs_write"] = True
            st["has_dcs_change"] += 1
            if last_e["cat"] != 28:
                emit("最後 DCS 寫入 ", dcs)
        # key params: latest Cat28 change per key
        for a, b2 in ch:
            k = key_of(b2)
            if not k:
                continue
            e = b2["e"]
            if e["cat"] == 28:
                later = [p for p in ch if key_of(p[1]) == k and p[1]["e"]["seq"] > e["seq"]]
                cur = latest[dk].get((b2["bk"], b2["base"]))
                dcs_writes[dk][k] = [pdisp(b2), e["tw"].strftime("%Y-%m-%d %H:%M:%S") if e["tw"] else None, disp(None, e["desc"], None),
                                     e["user"], pdisp(a), b2["pn"], any(p[1]["e"]["cat"] != 28 for p in later),
                                     pdisp(cur) if cur else None]
        if dcs_writes.get(dk):
            st["dcs_writes_key"] += 1

    # ======================================================= ident 位號歷程補充
    del_by_serial = defaultdict(list)
    for e in sorted((e for e in events.values() if e["cat"] == 52), key=lambda e: e["seq"]):
        m = re.search(r"with a serial number of (.+?) and an AMS tag of (.+?) was deleted", e["other"] or "")
        if m:
            del_by_serial[m.group(1)].append((e, m.group(2)))
    for dk in alias_of:
        R = out[dk]["ident"]
        dl = del_by_serial.get(ident.get(dk), [])
        if dl:
            st["deleted"] += 1
            R.append(row("刪除重建次數", f"{len(dl)} 次", "decoded", src("decoded", "EventLog Cat52 Other 序號 = Devices.Identifier (同 21_刪除裝置事件)")))
            for i, (e, tag) in enumerate(dl, 1):
                R.append(row(f"第 {i} 次刪除", f"{e['tw']:%Y-%m-%d %H:%M} · {e['user'] or '—'} · {e['ip'] or '—'} · 刪除時位號 {tag}", "decoded",
                             src("decoded", "EventLog Cat52 EventTime UTC+8 / Users / ComputerId→IPv4", e["tw"])))
        meth = sorted([e for e in dev_events.get(dk, []) if e["desc"] and "executed" in e["desc"]], key=lambda e: e["seq"])
        if meth:
            st["methods"] += 1
            R.append(row("方法執行次數", f"{len(meth)} 次", "decoded", src("decoded", "EventLog.Description 含 'executed'")))
            for e in meth[::-1][:3]:
                R.append(row("方法執行 (最近)", f"{e['tw']:%Y-%m-%d %H:%M} · {re.sub(r'\s+', ' ', e['desc']).strip()} · {e['user'] or '—'}", "raw",
                             src("raw", f"EventLog.Description Cat{e['cat']}", e["tw"])))

    # ======================================================= SnapOn
    snap = {}
    for bk, t, blob, day, frac in q("select BlockKey, SnapOnDataType, SnapOnData, EventIdDay, EventIdFraction from SnapOnData"):
        if bk not in blocks:
            continue
        try:
            x = blob.decode("utf-16le", "replace") if isinstance(blob, (bytes, bytearray)) else str(blob)
        except Exception:
            continue
        m1 = re.search(r'DeviceRevision="(\d+)"', x); m2 = re.search(r'DDRevision="(\d+)"', x)
        e = events.get((day, frac))
        seq = int(day) * 2147483648 + int(frac)
        tw_ = e["tw"] if e and e["tw"] else (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=int(day) + int(frac) / 2147483648.0) + TW).replace(microsecond=0)
        dk = blocks[bk][0]
        if dk not in snap or seq > snap[dk][2]:
            snap[dk] = (m1.group(1) if m1 else None, m2.group(1) if m2 else None, seq, tw_, t)

    # ======================================================= device 設備補充
    for dk in alias_of:
        R = out[dk]["device"]
        r = pick(dk, ["final_assembly_number", "final_asmbly_num"])
        if r:
            st["fan"] += 1
            v = r["disp"]
            if v in ("0", "—"):
                v = "未寫入 (0)"
            else:
                st["fan_nonzero"] += 1
            R.append(row("銘牌序號 (final_assembly_number)", v, "decoded", src("decoded", f"BlockData {r['base']} {r['dtype']}", r["e"]["tw"])))
        serial = []
        for base, lst in by_dev_base[dk].items():
            if ":" in base or "serial" not in base.lower() or base in SERIAL_SKIP:
                continue
            for r in lst:
                serial.append(r)
        nz = [r for r in serial if r["disp"] not in ("0", "—", "未使用")]
        for r in sorted(nz, key=lambda r: r["base"])[:6]:
            R.append(row(f"序號參數 {r['base']}", r["disp"], "decoded", src("decoded", f"BlockData {r['base']} {r['dtype']}", r["e"]["tw"])))
        zero = sorted({r["base"] for r in serial if r not in nz})
        if zero:
            R.append(row("序號參數 (值 0/空)", "未寫入: " + "、".join(zero[:6]) + (" …" if len(zero) > 6 else ""), "decoded",
                         src("decoded", "BlockData *serial* 參數")))
        if nz:
            st["serial_nonzero"] += 1
        got_rev = False
        for label, names in HART_REV:
            r = pick(dk, names)
            if r and ":" not in r["pn"]:
                got_rev = True
                R.append(row(label, r["disp"], "decoded", src("decoded", f"BlockData {r['base']} {r['dtype']}", r["e"]["tw"])))
        if got_rev:
            st["hart_rev"] += 1
        got_ff = False
        for label, item in [("FF 軟體版本字串 (80020b57)", "80020b57:00"), ("FF DEV_REV (800200c4)", "800200c4:00"), ("FF DD_REV (800200c2)", "800200c2:00")]:
            r = pick(dk, [item])
            if r:
                got_ff = True
                R.append(row(label, r["disp"], "decoded", src("decoded", f"BlockData {blk_label(*blocks[r['bk']][1:])} {r['pn']} {r['dtype']}", r["e"]["tw"])))
        if got_ff:
            st["ff_rev"] += 1
        if dk in snap:
            dr, ddr, _, tw_, t = snap[dk]
            st["snapon"] += 1
            R.append(row("DD 版次 (SnapOn XML)", f"DeviceRevision {dr or '—'} / DDRevision {ddr or '—'}", "decoded",
                         src("decoded", f"SnapOnData XML DeviceInfo (UTF-16LE, Type {t})", tw_)))

    # ======================================================= alarm 類比輸出警報
    for dk in alias_of:
        R = out[dk]["alarm"]
        for label, names, unit in ALARM_PARAMS:
            r = pick(dk, names)
            if not r or ":" in r["pn"]:
                continue
            v = pdisp(r) if r["base"] == "loop_alarm_code" else r["disp"]
            if unit and v not in ("未使用", "—"):
                v = f"{v} {unit}"
            R.append(row(label, v, "decoded", src("decoded", f"BlockData {r['base']} {r['dtype']}", r["e"]["tw"])))
        if R:
            st["alarm_any"] += 1
        if any(x[0] == "警報電流 高" for x in R):
            st["alarm_level"] += 1

    # ======================================================= ff FF 診斷
    for dk in alias_of:
        R = out[dk]["ff"]
        if proto_of.get(dk) != "FF":
            continue
        lat = latest.get(dk, {})
        if not lat:
            continue
        st["ff_with_params"] += 1

        def one(item, label, fn, block_type="R"):
            r = pick(dk, [item], block_type)
            if not r:
                return None
            v = fn(r)
            R.append(row(label, v, "decoded", src("decoded", f"BlockData {blk_label(*blocks[r['bk']][1:])} {item} {r['dtype']}", r["e"]["tw"])))
            return r

        one("8002018e:00", "寫入鎖定 WRITE_LOCK", lambda r: f"{r['disp']} = {WRITE_LOCK.get(int(r['num']), '?')}" if r["num"] is not None else r["disp"])
        fd_any = False
        for item, label in [("80020b30:00", "FD_FAIL_ACTIVE"), ("80020b35:00", "FD_MAINT_ACTIVE"), ("80020b3a:00", "FD_OFFSPEC_ACTIVE"), ("80020b29:00", "FD_CHECK_ACTIVE")]:
            r = one(item, label, lambda r: ("0x%08X" % (int(r["num"]) & 0xFFFFFFFF) + (" ⚠ 有位元" if int(r["num"]) else " (無)")) if r["num"] is not None else r["disp"])
            if r is not None:
                fd_any = True
                if item == "80020b30:00" and r["num"]:
                    st["ff_fd_fail_nonzero"] += 1
        if fd_any:
            st["ff_fd"] += 1
        one("80020b3f:00", "建議處置 FD_RECOMMEN_ACT", lambda r: f"{r['disp']} = {FD_RECOMMEN.get(int(r['num']), '廠家自訂碼')}" if r["num"] is not None else r["disp"])
        one("80020180:00", "資源區塊 TAG_DESC", lambda r: r["disp"])
        # per block
        blks = sorted({bk for (bk, base) in lat if base.startswith("80020126:") or base.startswith("80020132:") or base.startswith("80020192:")},
                      key=lambda b: blocks[b][2])
        for bk in blks:
            bt, bi = blocks[bk][1], blocks[bk][2]
            is_ai = (bk, "8002010c:00") in lat
            lab = blk_label(bt, bi, is_ai)
            g = lambda base: lat.get((bk, base))
            r = g("80020126:01")
            if r:
                v = mode_zh(r["num"])
                if r["num"] is not None and int(r["num"]) & 128 and bt == "F":
                    v += " ⚠ 停止服務"
                R.append(row(f"{lab} 目標模式 MODE_BLK", v, "decoded", src("decoded", f"BlockData {bt}{bi} 80020126:01 {r['dtype']}", r["e"]["tw"])))
                if is_ai and r["num"] is not None and int(r["num"]) & 128:
                    st["ff_ai_os_blocks"] += 1
            r = g("8002010c:00")
            if r:
                R.append(row(f"{lab} L_TYPE", f"{r['disp']} = {L_TYPE.get(int(r['num']), '?')}" if r["num"] is not None else r["disp"], "decoded",
                             src("decoded", f"BlockData {bt}{bi} 8002010c:00 {r['dtype']}", r["e"]["tw"])))
            for it, nm in [("80020192", "XD_SCALE"), ("80020132", "OUT_SCALE")]:
                hi, lo, un = g(it + ":01"), g(it + ":02"), g(it + ":03")
                if hi or lo:
                    u = ff_unit(un["num"]) if un and un["num"] is not None else None
                    ustr = (u or (f"單位碼 {un['disp']}" if un else "")).strip()
                    rr = hi or lo
                    R.append(row(f"{lab} {nm}", f"{lo['disp'] if lo else '—'} ~ {hi['disp'] if hi else '—'} {ustr}".strip(), "decoded",
                                 src("decoded", f"BlockData {bt}{bi} {it}:01-03 float32/單位碼", rr["e"]["tw"])))
            r = g("8002013a:00")
            if r:
                R.append(row(f"{lab} PV_FTIME", f"{r['disp']} s", "decoded", src("decoded", f"BlockData {bt}{bi} 8002013a:00 {r['dtype']}", r["e"]["tw"])))
            r = g("80020180:00")
            if r and bt != "R" and r["disp"] != "—":
                R.append(row(f"{lab} TAG_DESC", r["disp"], "decoded", src("decoded", f"BlockData {bt}{bi} 80020180:00 {r['dtype']}", r["e"]["tw"])))

    # ======================================================= assemble
    by_alias = {}
    for dk, alias in alias_of.items():
        o = {g: out[dk][g] for g in GROUPS if out[dk].get(g)}
        if dcs_writes.get(dk):
            o["dcs_writes"] = dcs_writes[dk]
        if flags.get(dk):
            o["flags"] = flags[dk]
        by_alias[alias] = o
    n = len(alias_of)
    cov = {g: sum(1 for a in by_alias.values() if a.get(g)) for g in GROUPS}
    stats = {"devices": n, "backup_date": backup.strftime("%Y-%m-%d"), "group_coverage": cov, **dict(st),
             "notes": [
                 "時間皆為台灣時間 (EventLog.EventTime UTC + 8)；參數值為該參數最後一次記錄 (同步/寫入當下快照)",
                 "變更判定以 14_參數變更歷程為基礎 (同一 (BlockKey, ParamName) 相鄰兩筆 ValueMode=h 值不同)，但排除動態/量測/計數值 (pv_value、*UpdatePeriod、OperatingHours*、fManualPos/Sig、*Max/*Min、*Counter、*Timestamp、device_type、FF FD_*/RECOMMEN_ACT/MODE.ACTUAL) 與 7 位有效數字顯示相同的浮點殘差，故『最後修改』可能與 14 表不同；Cat28 'Change performed by foreign host' 標為 DCS·外部主機",
                 "dcs_writes：key 參數 (URV/LRV/UNIT 只取與 13_設備參數統計 相同的主參數 = 設備現有候選基底依字母排序第一個；FF 為 XD/OUT_SCALE@區塊) 最新一次『值有改變』的 Cat28 記錄；首次上傳 (無前值) 不算寫入。陣列 = [值, 時間, 事件, 使用者, 前值, ParamName, 之後是否被非 DCS 事件改寫, AMS 現值]",
                 "final_assembly_number：Rosemount 為銘牌序號後 7 碼 (他廠意義未確認)；0 = 未寫入",
                 "float32 以 7 位有效數字顯示；1.1754944e-38 (FLT_MIN) 為裝置『未使用』哨兵",
                 "WRITE_LOCK 依 FF 規範 1 = Not Locked、2 = Locked；FF 項目 80020132 = OUT_SCALE、80020192 = XD_SCALE (由單位 psig/psi 對照確認)",
             ]}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"kind": "ams", "backup_date": stats["backup_date"], "groups": GROUPS, "by_alias": by_alias, "stats": stats},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({k: v for k, v in stats.items() if k != "notes"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
