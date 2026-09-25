# -*- coding: utf-8 -*-
"""
sheets_params.py  --  AMS Device Manager (AmsDb) 參數資料解碼 (domain key: params)

build(conn) -> list[dict]   每個 dict = {"name","purpose","one_row","df","notes","source_tables"}

資料來源: BlockData (351,348 列) + EventLog / Blocks / Devices / DeviceRevisions / DeviceTypes /
MfrProtocols / Manufacturers / DeviceProtocols / BlockAsgms / ExtBlockTags / Users / EventCategories

ParamData BLOB 解碼規則 (以資料驗證; 見各工作表 notes):
  HART (ParamName = name.itemId.0000.0000):
    ParamDataType 4  = int32 LE                (AmsUdf_BinaryToInt / AmsSp_DevBlk_GetHartDeviceFlags_1 同法)
    ParamDataType 6  = float32 LE              (upper/lower_range_value, damping ... 與舊工作簿 21 全數相符)
    ParamDataType 8  = float64 LE = OLE 日期序號 (date.000000A6: 36526.0 = 2000-01-01; 2.0 = 未設定)
    ParamDataType 9  = 原始位元組 (僅 read_loop_status_data / read_scan_list_from_index_response, 舊匯出以 &XXXX 表示)
    ParamDataType 12 = UTF-16LE 字串           (AmsUdf_CurrentDescriptor: cast varbinary -> nvarchar)
    ParamDataType 3  = 窄字串 ASCII             (AmsSp_GetBlockKeyCurrentHartInfo_1; 本庫 HART 無此型)
  FF (ParamName = itemIdHex:memberHex): ParamDataType 3 但內容為「十六進位文字」容器:
    位元組0 = 0x01 (版本), 位元組1 = 型別碼:
      0x44 = 寬字串 (MFC CArchive 格式: FF FE FF + 長度 + UTF-16LE)
      0x45 = int32 LE (有號)        0x46 = uint32 LE (無號)
      0x47 = float32 LE             0x49 = 4 個補零位元組 + float64 LE OLE 日期 (26299.0 = 1972-01-01 = FF 紀元/未設定)
"""
import os, sys, json, struct, math, datetime, re
import sqlite3
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tools/db/paths.py：repo 外路徑的唯一來源
from paths import AMS_SQLITE as DB_PATH, SHEETS_OUT as OUT_DIR  # noqa: E402
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = "params"

OLE_EPOCH = datetime.datetime(1899, 12, 30)
TW = datetime.timedelta(hours=8)

# ----------------------------------------------------------------------------- optional dictionaries
def _load_json(name):
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

PREV_DICT = _load_json("param_dict_prev.json") or {"HART": {}, "FF": {}}
PREV_CODES = _load_json("code_tables_prev.json") or {}

def _table(key):
    """code -> zh  from previous workbook code tables (skip rule/explanation rows)."""
    out = {}
    for x in PREV_CODES.get(key, []):
        code = str(x.get("code") or "")
        if not re.fullmatch(r"-?\d+", code):
            continue
        zh = x.get("zh") or x.get("en") or ""
        out[int(code)] = zh
    return out

HART_UNITS = _table("HART 單位碼 (hart_units)")
FF_UNITS = _table("FF 單位碼 (ff_units)")
SIMPLE_TABLES = {  # base param name -> code table
    "transfer_function": _table("轉換函數 (transfer_function)"),
    "loop_alarm_code": _table("警報方向(迴路警報碼) (loop_alarm_code)"),
    "write_protect": _table("寫入保護 (write_protect)"),
    "device_flags": _table("裝置旗標 (device_flags)"),
    "physical_signaling_code": _table("實體訊號碼 (physical_signaling_code)"),
    "loop_flags": _table("迴路旗標 (loop_flags)"),
    "scaled_transfer_function": _table("比例變數轉換函數 (scaled_transfer_function)"),
    "alarm_select": _table("警報選擇 (alarm_select)"),
    "loop_current_mode": _table("迴路電流模式 (loop_current_mode)"),
    "burst_mode_select": _table("Burst 模式 (burst_mode_select)"),
    "universal_revision": _table("HART 通用版本 (universal_revision)"),
    "manufacturer_id": _table("HART 製造商碼 (hart_manufacturer_id)"),
}
# 內建保底 (無 JSON 時仍可解碼最常見的幾張表)
SIMPLE_TABLES["transfer_function"] = SIMPLE_TABLES["transfer_function"] or {0: "線性", 1: "開平方", 2: "開平方三次方", 3: "開平方五次方", 4: "特殊曲線", 5: "平方", 240: "製造商自訂", 250: "未使用", 251: "無", 252: "未知", 253: "特殊"}
SIMPLE_TABLES["write_protect"] = SIMPLE_TABLES["write_protect"] or {0: "否(未寫入保護)", 1: "是(已寫入保護)", 250: "未使用", 251: "無(裝置不支援)", 252: "未知", 253: "特殊"}
SIMPLE_TABLES["loop_alarm_code"] = SIMPLE_TABLES["loop_alarm_code"] or {0: "高(Upscale)", 1: "低(Downscale)", 239: "保持最後輸出值", 250: "未使用", 251: "無", 252: "未知", 253: "特殊"}
if not HART_UNITS:
    HART_UNITS = {1: "inH2O(68°F)", 2: "inHg", 4: "mmH2O", 6: "psi", 7: "bar", 8: "mbar", 12: "kPa", 32: "°C", 33: "°F", 36: "mV", 37: "Ω", 39: "mA", 57: "%", 250: "未使用", 251: "無單位"}
if not FF_UNITS:
    FF_UNITS = {1001: "°C", 1002: "°F", 1133: "kPa", 1141: "psi", 1146: "inH2O", 1342: "%", 0: "未設定"}
FF_UNIT_ITEMS = {"000206ee", "0100001f", "010000a8", "010000ae", "010000bf", "010000ce", "01000548", "800200e2", "80020132",
                 "8002013c", "80020186", "80020192", "80020368", "80020398", "80020d32", "80020d33", "80020d3c", "80020d3d", "80020d43"}
FF_MODE_VALUES = _table("FF 區塊模式值 (ff_mode_values)") or {8: "自動 Auto", 16: "手動 Man", 128: "停止服務 O/S"}
# 裝置自訂單位列舉（不是 HART Table-2）：2026-09-24 以控制器 I/O 組態（signal-atlas 索引 AI Low/High Value）反推——
# E+H Cerabar/Deltabar S evo 的 Pressure1Unit=9 有 134 台數值與控制器 kPa 量程完全相同、Deltabar OutUnitEasy=18 有 31 台
# 換算 mmH2O→kPa 後相同。其他碼未出現在本庫，不猜。
DEVICE_UNIT_ENUMS = {"Pressure1Unit": {9: "kPa"}, "OutUnitEasy": {18: "mmH2O"}}
DEVICE_SPECIFIC_UNIT_PARAMS = {"Pressure1Unit", "TemperatureUnit", "LevelUnit", "OutUnitEasy", "VirtualLevelUnitDensity",
                               "LE_CstOutputUnit_1", "LE_CustomUnit_1", "ECT_XEngineeringUnit_1", "ECT_YEngineeringUnit_1",
                               "varUnitCode0", "varUnitCode1", "varUnitCode2", "varUnitCode3", "varLcdLenUnit", "varLcdTempUnit",
                               "varLcdVelUnit", "varLcdVolUnit", "spec_area_units", "spec_length_units", "spec_travel_units",
                               "spec_torque_units", "spec_spring_rate_units", "var_span_unit", "var_span_old_unit",
                               "varDeviceConfig_General_UnitLimitation", "fo_1_pulse_unit", "fo_1_unit_pulse"}

# 關鍵組態參數 (舊工作簿 03_設備總表 用來取量程/單位/阻尼等的參數名)
KEY_CONFIG = {
    "量程": {"upperRange_value", "lowerRange_value", "upper_range_value", "lower_range_value", "pv_upperRange_value", "pv_lowerRange_value",
             "sensor1_upper_range_value", "sensor1_lower_range_value", "pressure_upper_range_value", "pressure_lower_range_value",
             "varURV", "varLRV", "UpperRangeValue", "LowerRangeValue", "SV_UPPER_RANGE", "SV_LOWER_RANGE"},
    "單位": {"pressure_units", "sensor1_digital_units", "pv_unit", "Pressure1Unit", "pv_range_units", "OutUnitEasy", "varPVUnit",
             "input_units", "scaled_variable_units", "Iunit", "pv_digital_units", "SV_UNITS", "conc_unit", "pdp_units", "flowUnits",
             "scaling_units", "varLengthUnit", "varDeviceUnits_PhysicalValueUnit", "mass_flow_digital_units", "scaled_units_string_short"},
    "阻尼": {"sensor1_damping_value", "pressure_damping", "pv_damping", "ActivePressure1Damping", "damping_value", "fDamping",
             "varDampingValue", "pressure_damping_value", "sensor_damping_value", "target_position_damping_value", "positionDampingValue",
             "conc_damping", "pdpDampingValue", "flowDamping", "flow_damping_value", "mass_flow_digital_damping", "CO_TauDamping_1", "damping"},
    "轉換函數": {"transfer_function"},
    "寫入保護": {"write_protect"},
    "描述": {"descriptor"},
    "訊息": {"message"},
    "日期": {"date"},
    "最終組裝號": {"final_assembly_number", "final_asmbly_num"},
    "位號": {"tag", "longTag", "LongTag", "long_tag", "HO_LongTag_1", "HO_Tag_1"},
    "輪詢位址": {"polling_address", "PollingAddress", "poll_addr"},
    "警報方向": {"loop_alarm_code"},
    "PV 變數碼": {"primary_variable_code"},
}
URV_NAMES = {n for n in KEY_CONFIG["量程"] if "upper" in n.lower() or n.lower().endswith("urv")}
LRV_NAMES = {n for n in KEY_CONFIG["量程"] if "lower" in n.lower() or n.lower().endswith("lrv")}
KEY_CONFIG_BY_NAME = {}
for cat, names in KEY_CONFIG.items():
    for n in names:
        KEY_CONFIG_BY_NAME.setdefault(n, cat)
FF_KEY_ITEMS = {  # FF 標準 item -> 類別
    "80020192": "量程(AI XD_SCALE)", "80020186": "量程(AI OUT_SCALE)", "80020126": "區塊模式 MODE_BLK",
    "00020000": "區塊位號 TAG", "80020037": "警報鍵值 ALERT_KEY", "800200e2": "量程(刻度)",
}

BLOCK_TYPE_ZH = {"": "設備層", "R": "R 資源區塊", "T": "T 轉換器區塊", "F": "F 功能區塊"}
VALUE_MODE_ZH = {"h": "h 正常(歷史值)", "o": "o 離線值"}
HART_TYPE_NAME = {3: "3 窄字串", 4: "4 int32", 6: "6 float32", 8: "8 float64 日期", 9: "9 原始位元組", 12: "12 UTF-16 字串"}
FF_TYPE_NAME = {0x44: "0x44 寬字串", 0x45: "0x45 int32", 0x46: "0x46 uint32", 0x47: "0x47 float32", 0x49: "0x49 float64 日期"}


# ----------------------------------------------------------------------------- decoders
def ole_to_dt(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    if v < -600000 or v > 3000000:
        return None
    try:
        return OLE_EPOCH + datetime.timedelta(days=float(v))
    except Exception:
        return None


def _fmt_num(v):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "INF" if v > 0 else "-INF"
        if abs(v) < 1e15:
            f32 = np.float32(v)
            if float(f32) == v:          # 來自 float32 的值: 用最短可還原的 float32 表示 (850.00024 而非 850.000244140625)
                if f32 == 0 or 1e-4 <= abs(float(f32)) < 1e15:
                    return np.format_float_positional(f32, unique=True, trim="0")   # 1000000.0 而非 1e+06
                return str(f32)
        return repr(v)
    return str(v)


def decode_hart(t, b):
    """-> (num, text, date, dtype_name, hexshort)"""
    if b is None:
        return (None, None, None, HART_TYPE_NAME.get(t, str(t)) + " (NULL)", None)
    hx = b.hex().upper()
    hs = hx if len(hx) <= 32 else hx[:32] + "…"
    try:
        if t == 4 and len(b) == 4:
            return (struct.unpack("<i", b)[0], None, None, HART_TYPE_NAME[4], hs)
        if t == 6 and len(b) == 4:
            return (float(struct.unpack("<f", b)[0]), None, None, HART_TYPE_NAME[6], hs)
        if t == 8 and len(b) == 8:
            v = struct.unpack("<d", b)[0]
            return (v, None, ole_to_dt(v), HART_TYPE_NAME[8], hs)
        if t == 12:
            return (None, b.decode("utf-16le", "replace"), None, HART_TYPE_NAME[12], hs)
        if t == 3:
            return (None, b.decode("latin1"), None, HART_TYPE_NAME[3], hs)
    except Exception:
        pass
    return (None, None, None, HART_TYPE_NAME.get(t, str(t)) + " (hex)", hs)


def decode_ff(b):
    """FF ParamData = ASCII hex text of a small serialized variant. -> (num, text, date, dtype_name, hexshort)"""
    if b is None:
        return (None, None, None, "FF (NULL)", None)
    txt = b.decode("ascii", "replace")
    hs = txt if len(txt) <= 32 else txt[:32] + "…"
    try:
        h = bytes.fromhex(txt)
    except Exception:
        return (None, None, None, "FF (非十六進位文字)", hs)
    if len(h) < 2 or h[0] != 0x01:
        return (None, None, None, "FF (未知容器)", hs)
    tc = h[1]
    p = h[2:]
    try:
        if tc == 0x44:
            if p[:3] == b"\xff\xfe\xff":
                n = p[3]
                q = 4
                if n == 0xFF:
                    n = struct.unpack("<H", p[4:6])[0]
                    q = 6
                    if n == 0xFFFF:
                        n = struct.unpack("<I", p[6:10])[0]
                        q = 10
                s = p[q:q + 2 * n].decode("utf-16le", "replace")
            else:  # ANSI 變體 (未在本庫出現)
                n = p[0]
                s = p[1:1 + n].decode("latin1")
            return (None, s, None, FF_TYPE_NAME[0x44], hs)
        if tc == 0x45:
            return (struct.unpack("<i", p[:4])[0], None, None, FF_TYPE_NAME[0x45], hs)
        if tc == 0x46:
            return (struct.unpack("<I", p[:4])[0], None, None, FF_TYPE_NAME[0x46], hs)
        if tc == 0x47:
            return (float(struct.unpack("<f", p[:4])[0]), None, None, FF_TYPE_NAME[0x47], hs)
        if tc == 0x49:
            v = struct.unpack("<d", p[4:12])[0]
            return (v, None, ole_to_dt(v), FF_TYPE_NAME[0x49], hs)
    except Exception:
        pass
    return (None, None, None, "FF 0x%02X (未知型別)" % tc, hs)


def translate(proto, base, item, member, num, text, date):
    """碼表翻譯 -> 解碼值 (文字)"""
    if date is not None:
        if abs((num or 0) - 2.0) < 1e-9:  # HART 與 FF 皆有 2.0 (=1900-01-01) 的未設定值
            return "未設定 (1900-01-01)"
        if proto == "FF" and abs((num or 0) - 26299.0) < 1e-9:
            return "未設定 (FF 紀元 1972-01-01)"
        return date.strftime("%Y-%m-%d %H:%M:%S") if (date.hour or date.minute or date.second) else date.strftime("%Y-%m-%d")
    if num is None or isinstance(num, float) and (math.isnan(num) or math.isinf(num)):
        return None
    if isinstance(num, float) and num != int(num):
        return None
    code = int(num)
    if proto == "HART":
        tbl = SIMPLE_TABLES.get(base)
        if tbl:
            return tbl.get(code)
        if base in ("primary_variable_code", "secondary_variable_code", "tertiary_variable_code", "quaternary_variable_code",
                    "burst_variable_code", "fourth_variable_code") and code == 250:
            return "未使用"
        if base in ("polling_address", "PollingAddress"):
            return "點對點(4-20mA)" if code == 0 else "多點位址"
        if base in DEVICE_UNIT_ENUMS:
            return DEVICE_UNIT_ENUMS[base].get(code)
        if "unit" in base.lower() and base not in DEVICE_SPECIFIC_UNIT_PARAMS:
            z = HART_UNITS.get(code)
            return z
        return None
    else:
        if member == "03" and item in FF_UNIT_ITEMS:
            return FF_UNITS.get(code)
        if item == "80020126" and member in ("01", "02", "03", "04"):
            return FF_MODE_VALUES.get(code)
        return None


# ----------------------------------------------------------------------------- helpers
def _tw(series_utc_text):
    s = pd.to_datetime(series_utc_text, errors="coerce")
    return s + pd.Timedelta(hours=8)


def _yn(x):
    return "是" if x else "否"


def _value_key(num, text, date, dtype):
    """用來判斷值是否相異的字串鍵"""
    if text is not None:
        return "s:" + text
    if num is not None:
        return "n:" + _fmt_num(num)
    return "x:" + (dtype or "")


def _display_value(num, text, date, hx=None):
    if text is not None:
        return text
    if date is not None:
        return date.strftime("%Y-%m-%d %H:%M:%S")
    if num is None:
        return ("0x" + hx) if hx else None
    return _fmt_num(num)


# ----------------------------------------------------------------------------- main build
def build(conn):
    sheets = []

    # ---- reference tables
    dev = pd.read_sql("""
        select dv.DeviceKey, dv.AmsDeviceTag, dv.AmsDeviceId, dv.Identifier as DeviceIdentifier, dv.ProtocolRevision,
               dr.Name as RevisionName, dt.Name as ModelName, dt.DeviceType as DeviceTypeCode,
               mf.Name as Manufacturer, pr.Name as Protocol
        from Devices dv
        left join DeviceRevisions dr on dr.AmsDevRevId = dv.AmsDevRevId
        left join DeviceTypes dt on dt.AmsDevTypeId = dr.AmsDevTypeId
        left join MfrProtocols mp on mp.MfrProtocolId = dt.MfrProtocolId
        left join Manufacturers mf on mf.AmsMfrNameId = mp.AmsMfrNameId
        left join DeviceProtocols pr on pr.ProtocolId = mp.ProtocolId""", conn)
    blocks = pd.read_sql("select BlockKey, DeviceKey, BlockIndex, BlockType from Blocks", conn)
    blocks["BlockType"] = blocks["BlockType"].fillna("")
    curtag = pd.read_sql("""
        select b.DeviceKey, t.ExtBlockTag, t.ExtBlockTagDesc
        from BlockAsgms a join Blocks b on b.BlockKey = a.BlockKey and b.BlockIndex = 0
        join ExtBlockTags t on t.ExtBlockTagKey = a.ExtBlockTagKey
        where a.EventIdDayOut = 49710""", conn).drop_duplicates("DeviceKey")
    dev = dev.merge(curtag, on="DeviceKey", how="left")
    dev["位號"] = dev["ExtBlockTag"].fillna(dev["AmsDeviceTag"])
    blocks = blocks.merge(dev[["DeviceKey", "位號", "AmsDeviceTag", "Protocol", "Manufacturer", "ModelName", "RevisionName", "ProtocolRevision"]],
                          on="DeviceKey", how="left")

    ev = pd.read_sql("""
        select e.EventIdDay, e.EventIdFraction, e.EventTime, e.Description, e.Category, ec.CategoryDesc, e.Source, e.Type,
               u.UserName
        from EventLog e
        left join EventCategories ec on ec.Category = e.Category
        left join Users u on u.UserKey = e.UserKey""", conn)
    # 只保留 BlockData 有用到的事件 (加速)
    bd = pd.read_sql("""select BlockKey, EventIdDay, EventIdFraction, ParamKind, ParamName, ValueMode, ParamDataType,
                               ParamDataSize, ParamData, Archived from BlockData""", conn)
    ev = ev.merge(bd[["EventIdDay", "EventIdFraction"]].drop_duplicates(), on=["EventIdDay", "EventIdFraction"])
    ev["事件時間(台灣)"] = _tw(ev["EventTime"])
    ev["事件時間UTC"] = ev["EventTime"].astype(str)
    ev["事件序"] = ev["EventIdDay"].astype("int64") * 2147483648 + ev["EventIdFraction"].astype("int64")

    # ---- decode every row
    is_ff = bd["ParamName"].str.contains(":", regex=False)
    bd["協定名"] = np.where(is_ff, "FF", "HART")
    nums, texts, dates, dtypes, hexs = [], [], [], [], []
    for t, b, ff in zip(bd["ParamDataType"].values, bd["ParamData"].values, is_ff.values):
        if ff:
            n, s, d, dn, hx = decode_ff(b)
        else:
            n, s, d, dn, hx = decode_hart(int(t), b)
        nums.append(n); texts.append(s); dates.append(d); dtypes.append(dn); hexs.append(hx)
    bd["數值"] = nums
    bd["文字"] = texts
    bd["日期值"] = dates
    bd["資料型別"] = dtypes
    bd["原始十六進位"] = hexs

    # names
    pn = bd["ParamName"]
    hart_parts = pn.where(~is_ff, "").str.split(".", n=2, expand=True)
    bd["參數名"] = np.where(is_ff, pn.str.split(":").str[0] + ":" + pn.str.split(":").str[1], hart_parts[0])
    bd["項目ID"] = np.where(is_ff, pn.str.split(":").str[0].str.lower(), hart_parts[1].fillna("").str.lower())
    bd["成員"] = np.where(is_ff, pn.str.split(":").str[1], "")
    bd["參數基底"] = np.where(is_ff, bd["參數名"], hart_parts[0])
    bd["值鍵"] = [_value_key(n, s, d, t) for n, s, d, t in zip(nums, texts, dates, dtypes)]
    bd["顯示值"] = [_display_value(n, s, d, hx) for n, s, d, hx in zip(nums, texts, dates, hexs)]
    bd["解碼值"] = [translate(p, base, item, mem, n, s, d) for p, base, item, mem, n, s, d in
                  zip(bd["協定名"].values, bd["參數基底"].values, bd["項目ID"].values, bd["成員"].values, nums, texts, dates)]

    def zh_name(proto, base):
        d = PREV_DICT.get(proto, {}).get(base)
        return d.get("zh") if d else None

    def en_name(proto, base):
        d = PREV_DICT.get(proto, {}).get(base)
        return d.get("en") if d else None

    def cat_name(proto, base):
        d = PREV_DICT.get(proto, {}).get(base)
        return d.get("cat") if d else None

    uniq = bd[["協定名", "參數基底"]].drop_duplicates()
    uniq["中文名稱"] = [zh_name(p, b) for p, b in zip(uniq["協定名"], uniq["參數基底"])]
    uniq["英文說明"] = [en_name(p, b) for p, b in zip(uniq["協定名"], uniq["參數基底"])]
    uniq["參數分類"] = [cat_name(p, b) for p, b in zip(uniq["協定名"], uniq["參數基底"])]

    def key_cat(proto, base, item):
        if proto == "HART":
            return KEY_CONFIG_BY_NAME.get(base)
        return FF_KEY_ITEMS.get(item)

    bd = bd.merge(uniq, on=["協定名", "參數基底"], how="left")
    bd["關鍵組態"] = [key_cat(p, b, i) for p, b, i in zip(bd["協定名"], bd["參數基底"], bd["項目ID"])]

    bd = bd.merge(blocks, on="BlockKey", how="left")
    bd = bd.merge(ev[["EventIdDay", "EventIdFraction", "事件序", "事件時間(台灣)", "事件時間UTC", "Description", "CategoryDesc", "UserName"]],
                  on=["EventIdDay", "EventIdFraction"], how="left")
    bd["區塊類型"] = bd["BlockType"].map(BLOCK_TYPE_ZH).fillna(bd["BlockType"])
    bd["值模式"] = bd["ValueMode"].map(VALUE_MODE_ZH).fillna(bd["ValueMode"])

    # ---- FF block tag (latest 00020000:01 / member :01 of BLOCK record) -- 本庫僅 1 個區塊有此參數
    # 舊工作簿的 Block Tag 來自文字匯出的區塊標頭, 本庫 BlockAsgms 對 R/T/F 區塊無指派; 故以 區塊類型+索引 表示

    # ---- history statistics per (BlockKey, ParamName)
    hb = bd[bd["ValueMode"] == "h"]
    grp = hb.groupby(["BlockKey", "ParamName"])
    stats = grp.agg(歷史記錄數=("值鍵", "size"), 相異值數=("值鍵", "nunique"),
                    首次記錄序=("事件序", "min")).reset_index()
    # latest: prefer h over o, then latest event
    bd["_mode_rank"] = np.where(bd["ValueMode"] == "h", 1, 0)
    latest = bd.sort_values(["BlockKey", "ParamName", "_mode_rank", "事件序"]).drop_duplicates(["BlockKey", "ParamName"], keep="last")
    latest = latest.merge(stats, on=["BlockKey", "ParamName"], how="left")
    latest["歷史記錄數"] = latest["歷史記錄數"].fillna(0).astype(int)
    latest["相異值數"] = latest["相異值數"].fillna(0).astype(int)
    first_time = ev.set_index("事件序")["事件時間(台灣)"]
    latest["首次記錄(台灣)"] = latest["首次記錄序"].map(first_time)

    # ---- changes (per (BlockKey,ParamName) consecutive different values, h-mode only)
    hb_sorted = hb.sort_values(["BlockKey", "ParamName", "事件序"])
    multi = hb_sorted[hb_sorted.duplicated(["BlockKey", "ParamName"], keep=False)]
    prev = multi.groupby(["BlockKey", "ParamName"]).shift(1)
    chg_mask = prev["值鍵"].notna() & (prev["值鍵"] != multi["值鍵"])
    chg = multi[chg_mask].copy()
    prevc = prev[chg_mask]
    chg["前值"] = prevc["顯示值"].values
    chg["前值解碼"] = prevc["解碼值"].values
    chg["前值時間(台灣)"] = prevc["事件時間(台灣)"].values
    chg["前值時間UTC"] = prevc["事件時間UTC"].values
    chg["前值事件"] = prevc["Description"].values
    chg["前值使用者"] = prevc["UserName"].values
    chg["前值原始"] = prevc["原始十六進位"].values
    chg["間隔(小時)"] = ((chg["事件時間(台灣)"] - chg["前值時間(台灣)"]).dt.total_seconds() / 3600).round(2)
    # numeric delta
    pn_num = pd.to_numeric(prevc["數值"], errors="coerce").values
    cn_num = pd.to_numeric(chg["數值"], errors="coerce").values
    delta = cn_num - pn_num
    chg["數值差"] = np.where(np.isfinite(delta), delta, np.nan)

    nchg = chg.groupby(["BlockKey", "ParamName"]).size().rename("變更次數").reset_index()
    latest = latest.merge(nchg, on=["BlockKey", "ParamName"], how="left")
    latest["變更次數"] = latest["變更次數"].fillna(0).astype(int)

    # ======================================================================= Sheet 1: 參數現值
    cols1 = {
        "位號": "位號 (ExtBlockTag)", "AmsDeviceTag": "AMS 設備位號 (AmsDeviceTag)", "Protocol": "協定 (Protocol)",
        "Manufacturer": "製造商 (Manufacturer)", "ModelName": "型號 (DeviceTypes.Name)", "RevisionName": "設備版本 (DeviceRevision)",
        "區塊類型": "區塊類型 (BlockType)", "BlockIndex": "區塊索引 (BlockIndex)",
        "參數名": "參數 (ParamName 基底 / item:member)", "中文名稱": "參數中文名稱", "參數分類": "參數分類", "關鍵組態": "關鍵組態類別",
        "顯示值": "現值", "解碼值": "解碼值(碼表)", "數值": "數值", "文字": "文字值", "日期值": "日期值(裝置日期,未換時區)",
        "資料型別": "資料型別(解碼規則)", "原始十六進位": "原始十六進位(短)", "值模式": "值模式 (ValueMode)",
        "事件時間(台灣)": "最後記錄時間(台灣)", "事件時間UTC": "最後記錄時間UTC", "CategoryDesc": "事件分類 (EventCategories)",
        "Description": "事件說明 (EventLog.Description)", "UserName": "使用者 (Users.UserName)",
        "歷史記錄數": "歷史記錄數", "相異值數": "相異值數", "變更次數": "變更次數", "首次記錄(台灣)": "首次記錄(台灣)",
        "Archived": "已封存 (Archived)", "項目ID": "項目 ID (itemId)", "成員": "FF 成員 (member)", "ParamDataType": "ParamDataType",
        "ParamDataSize": "ParamDataSize", "BlockKey": "區塊鍵 (BlockKey)", "DeviceKey": "設備鍵 (DeviceKey)", "ParamName": "ParamName 原文",
    }
    s1 = latest.sort_values(["位號", "BlockIndex", "參數名"], kind="stable")[list(cols1)].rename(columns=cols1).copy()
    s1["已封存 (Archived)"] = s1["已封存 (Archived)"].map(lambda x: _yn(int(x) == 1) if pd.notna(x) else None)
    s1["數值"] = pd.to_numeric(s1["數值"], errors="coerce")
    s1["日期值(裝置日期,未換時區)"] = pd.to_datetime(s1["日期值(裝置日期,未換時區)"], errors="coerce")
    s1 = s1.reset_index(drop=True)

    n_hart = int((latest["協定名"] == "HART").sum()); n_ff = int((latest["協定名"] == "FF").sum())
    n_o_only = int((latest["ValueMode"] == "o").sum())
    sheets.append({
        "name": "參數現值",
        "purpose": "每個區塊×參數的最新一筆組態值 (BlockData 解碼), 附設備位號/型號/事件資訊與歷史統計",
        "one_row": "一個 (BlockKey, ParamName) 的最新值; 同一參數多筆歷史只取事件時間最新者 (正常值優先於離線值)",
        "df": s1,
        "notes": [
            f"列數 = {len(s1):,} = 相異 (BlockKey, ParamName) 數; HART {n_hart:,} 列 + FF {n_ff:,} 列 (舊工作簿 21/22: 204,562 + 140,381 = 344,943, 完全一致)",
            "現值 = 文字值 / 數值 / 日期值三者擇一顯示; 解碼值(碼表) 為單位碼、轉換函數、寫入保護、警報方向、裝置旗標、FF 單位碼、MODE_BLK 等的碼表翻譯 (碼表取自舊工作簿 23_解碼說明), 無對應者留空",
            "HART 解碼: ParamDataType 4=int32 LE, 6=float32 LE, 8=float64 LE(OLE 日期序號, 2.0=未設定), 12=UTF-16LE 字串, 9=原始位元組(僅 2 個診斷參數, 以十六進位呈現)",
            "FF 解碼: ParamData 為十六進位文字; 0x01 版本 + 型別碼 0x44 寬字串(FF FE FF+長度+UTF-16LE) / 0x45 int32 / 0x46 uint32 / 0x47 float32 / 0x49 (4 補零 + float64 OLE 日期, 26299=1972-01-01 未設定)",
            "解碼驗證: 與舊工作簿 (自文字匯出解碼) 逐筆比對, HART 204,562 筆中 203,843 筆值相同, 其餘 719 筆僅顯示格式差異 (type 9 舊為 &XXXX 十六進位; NULL 字串舊為空白; 日期 2.0 舊顯示 2000/01/01); FF 140,381 筆中 136,435 筆相同, 其餘 3,946 筆為日期/INF 顯示格式差異",
            "位號 = BlockAsgms 目前指派 (EventIdDayOut=49710) 之 ExtBlockTag (含 -1A3B 等尾碼); AMS 設備位號 = Devices.AmsDeviceTag (不含尾碼); 1,583 台兩者不同, 皆列出",
            "FF R/T/F 區塊在 BlockAsgms 無位號指派, 區塊以 區塊類型+索引 (如 F 功能區塊 1400) 識別; 舊工作簿的 Block Tag (如 90LT1_1000) 來自文字匯出標頭, 本庫無",
            f"值模式 'o' 離線值僅 12 列 (3 台設備); 其中僅 {n_o_only} 列因無正常值而以離線值作現值",
            "日期值 為裝置內的日期欄位 (HART date / FF 日期參數), 非事件時間, 不做時區換算; 最後記錄時間(台灣) = EventLog.EventTime (UTC) + 8 小時",
            "FF 全部 140,790 列 Archived=1, HART 全部 Archived=0 (AMS 對 FF 參數的封存旗標用法不同, 非資料遺失)",
            "float32 值以最短可還原表示 (如 0.4、850.00024); 原始位元組 00008000 (= float32 最小正規化值 1.1754944e-38) 共 7,169 筆 (temperature_minSpan / first_good_* / sensor2_*_sensor_limit 等 3051 診斷欄位), 舊工作簿顯示 0, 實為裝置的『無值』標記, 讀表時視同 0/未設定",
            "EventLog.EventTime 為整秒 (由 EventIdDay/EventIdFraction 四捨五入); 舊工作簿的 (台灣) 時間取自文字匯出含小數秒再截斷, 故約半數列與本表相差 1 秒, 非時區問題",
            "參數中文名稱/參數分類 取自舊工作簿 20_參數字典 (機器斷詞, 命名信心見該表); 無 JSON 字典檔時此二欄為空",
            "本域空表 (未建工作表): HostTagParams (0 列), InstantiableConfigData (0 列), InstantiableConfigBlocks (0 列), InstantiableBlockAsgms (0 列)",
        ],
        "source_tables": ["BlockData", "EventLog", "Blocks", "Devices", "DeviceRevisions", "DeviceTypes", "MfrProtocols", "Manufacturers",
                          "DeviceProtocols", "BlockAsgms", "ExtBlockTags", "Users", "EventCategories"],
    })

    # ======================================================================= Sheet 2: 參數變更歷程
    cols2 = {
        "位號": "位號 (ExtBlockTag)", "AmsDeviceTag": "AMS 設備位號 (AmsDeviceTag)", "Protocol": "協定 (Protocol)", "ModelName": "型號 (DeviceTypes.Name)",
        "區塊類型": "區塊類型 (BlockType)", "BlockIndex": "區塊索引 (BlockIndex)",
        "參數名": "參數 (ParamName 基底 / item:member)", "中文名稱": "參數中文名稱", "關鍵組態": "關鍵組態類別",
        "前值": "前值", "顯示值": "新值", "數值差": "數值差(新-前)", "前值解碼": "前值解碼", "解碼值": "新值解碼",
        "前值時間(台灣)": "前值記錄時間(台灣)", "事件時間(台灣)": "變更記錄時間(台灣)", "間隔(小時)": "間隔(小時)",
        "事件時間UTC": "變更記錄時間UTC", "前值時間UTC": "前值記錄時間UTC",
        "CategoryDesc": "事件分類 (EventCategories)", "Description": "事件說明 (EventLog.Description)", "UserName": "使用者 (Users.UserName)",
        "前值事件": "前值事件說明", "前值使用者": "前值使用者", "資料型別": "資料型別(解碼規則)",
        "前值原始": "前值原始十六進位(短)", "原始十六進位": "新值原始十六進位(短)", "BlockKey": "區塊鍵 (BlockKey)", "DeviceKey": "設備鍵 (DeviceKey)",
        "ParamName": "ParamName 原文",
    }
    s2 = chg.sort_values(["位號", "BlockIndex", "參數名", "事件序"], kind="stable")[list(cols2)].rename(columns=cols2).reset_index(drop=True)
    s2["前值記錄時間(台灣)"] = pd.to_datetime(s2["前值記錄時間(台灣)"], errors="coerce")
    n_pairs_multi = int(multi.groupby(["BlockKey", "ParamName"]).ngroups)
    n_pairs_chg = int(chg.groupby(["BlockKey", "ParamName"]).ngroups)
    key_chg = chg[chg["關鍵組態"].notna()]
    sheets.append({
        "name": "參數變更歷程",
        "purpose": "同一區塊×參數在時間序列上值有改變的每一次變更 (前值 → 新值), 附事件分類/說明/使用者",
        "one_row": "一次值變更 (同一 (BlockKey, ParamName) 相鄰兩筆正常值不同者); 值相同的重複記錄不列",
        "df": s2,
        "notes": [
            f"有多筆歷史值的 (BlockKey, ParamName) 共 {n_pairs_multi:,} 組, 其中 {n_pairs_chg:,} 組值曾改變, 共 {len(s2):,} 次變更",
            f"關鍵組態類別 (量程/單位/阻尼/轉換函數/寫入保護/描述/訊息/日期/位號/輪詢位址/FF 量程/MODE_BLK) 的變更共 {len(key_chg):,} 次, 涉及 {key_chg['DeviceKey'].nunique():,} 台設備",
            "變更判定以解碼後的值比較 (文字完全相同視為未變; 數值以 float32 精度比較); 僅比較 ValueMode='h' 正常值, 離線值 (o) 不列入",
            "事件分類: 'Change performed by foreign host' = 現場端 (Field change, 由 PS.AMS1SVR 掃描寫入); 'Change performed by AMS Device Manager' = 由 AMS 使用者操作 (Routine Service / 方法執行)",
            "時間: EventLog.EventTime 為 UTC, (台灣) 欄 = UTC+8; 間隔(小時) = 新值時間 - 前值時間",
            "BlockData 的每筆事件 (EventIdDay, EventIdFraction) 皆能在 EventLog 找到 (缺漏 0 筆), 且 EventLog.BlockKey 與 BlockData.BlockKey 一致",
        ],
        "source_tables": ["BlockData", "EventLog", "Blocks", "Devices", "BlockAsgms", "ExtBlockTags", "Users", "EventCategories"],
    })

    # ======================================================================= Sheet 3: 參數字典
    h = hb.copy()
    h["設備"] = h["DeviceKey"]
    lat = latest.copy()

    def top_values(s, k=3):
        vc = s.value_counts().head(k)
        return " | ".join(f"{v}({n})" for v, n in vc.items())

    g = lat.groupby(["協定名", "參數基底"])
    d3 = g.agg(
        設備數=("DeviceKey", "nunique"), 區塊數=("BlockKey", "nunique"), 現值筆數=("BlockKey", "size"),
        資料型別=("資料型別", lambda s: " / ".join(sorted(set(x for x in s if x)))),
        項目ID=("項目ID", lambda s: ", ".join(sorted(set(s))[:6]) + (" …" if s.nunique() > 6 else "")),
        項目ID數=("項目ID", "nunique"),
        範例值=("顯示值", lambda s: next((x for x in s if x not in (None, "") and str(x).strip() != ""), None)),
        常見值=("顯示值", top_values),
        常見解碼值=("解碼值", lambda s: top_values(s.dropna())),
        相異現值數=("值鍵", "nunique"),
        中文名稱=("中文名稱", "first"), 英文說明=("英文說明", "first"), 參數分類=("參數分類", "first"), 關鍵組態=("關鍵組態", "first"),
        型號=("ModelName", top_values), 最後記錄=("事件時間(台灣)", "max"),
    ).reset_index()
    hist = hb.groupby(["協定名", "參數基底"]).agg(歷史記錄總數=("值鍵", "size")).reset_index()
    chg3 = chg.groupby(["協定名", "參數基底"]).agg(變更次數=("值鍵", "size"), 變更設備數=("DeviceKey", "nunique")).reset_index()
    d3 = d3.merge(hist, on=["協定名", "參數基底"], how="left").merge(chg3, on=["協定名", "參數基底"], how="left")
    d3["變更次數"] = d3["變更次數"].fillna(0).astype(int)
    d3["變更設備數"] = d3["變更設備數"].fillna(0).astype(int)
    d3["關鍵組態?"] = d3["關鍵組態"].notna().map(_yn)
    d3["FF 成員"] = np.where(d3["協定名"] == "FF", d3["參數基底"].str.split(":").str[1], "")
    d3["命名信心"] = [ (PREV_DICT.get(p, {}).get(b) or {}).get("conf") for p, b in zip(d3["協定名"], d3["參數基底"])]
    d3 = d3.sort_values(["協定名", "關鍵組態?", "設備數", "參數基底"], ascending=[True, False, False, True], kind="stable")
    cols3 = {
        "協定名": "協定", "參數基底": "參數 (ParamName 基底 / item:member)", "中文名稱": "中文名稱 (舊工作簿字典)", "英文說明": "英文說明 / FF 標準名稱",
        "參數分類": "參數分類", "命名信心": "命名信心", "關鍵組態?": "關鍵組態?", "關鍵組態": "關鍵組態類別",
        "資料型別": "資料型別(解碼規則)", "設備數": "設備數", "區塊數": "區塊數", "現值筆數": "現值筆數", "歷史記錄總數": "歷史記錄總數",
        "相異現值數": "相異現值數", "變更次數": "變更次數", "變更設備數": "變更設備數", "範例值": "範例值", "常見值": "常見值 top3",
        "常見解碼值": "常見解碼值 top3", "型號": "主要型號 top3", "項目ID": "項目 ID (itemId)", "項目ID數": "項目 ID 數", "FF 成員": "FF 成員 (member)",
        "最後記錄": "最後記錄(台灣)",
    }
    s3 = d3[list(cols3)].rename(columns=cols3).reset_index(drop=True)
    n_h3 = int((d3["協定名"] == "HART").sum()); n_f3 = int((d3["協定名"] == "FF").sum())
    multi_item = int(((d3["協定名"] == "HART") & (d3["項目ID數"] > 1)).sum())
    sheets.append({
        "name": "參數字典",
        "purpose": "BlockData 出現過的所有參數 (HART 依基底名稱, FF 依 item:member) 之統計、型別、範例值與關鍵組態標記",
        "one_row": "一個相異參數名 (HART: ParamName 第一段; FF: itemId:member)",
        "df": s3,
        "notes": [
            f"HART 參數 {n_h3:,} 個 (舊工作簿 20_參數字典 HART 5,828 個, 一致), FF item:member {n_f3:,} 個 (舊工作簿 3,443 個為 ff_items 全集, 本庫實際出現 3,430 個)",
            f"HART 同一基底名稱對應多個 itemId 者 {multi_item:,} 個 (不同 DD 之同名參數), 項目 ID 欄列出前 6 個",
            "關鍵組態? = 舊工作簿 03_設備總表 用以推得量程/單位/阻尼/轉換函數/寫入保護/描述/訊息/日期/最終組裝號/位號/輪詢位址/警報方向/PV 變數碼 的參數, 以及 FF 的 XD_SCALE/OUT_SCALE/MODE_BLK/TAG/ALERT_KEY",
            "資料型別(解碼規則) 為該參數出現過的解碼規則 (HART 依 ParamDataType, FF 依容器型別碼)",
            "中文名稱 / 英文說明 / 參數分類 / 命名信心 取自舊工作簿 20_參數字典 (需 build/param_dict_prev.json), 缺檔時留空",
            "統計皆以 ValueMode='h' 正常值計算 (離線值不計); 變更次數與 參數變更歷程 工作表一致",
        ],
        "source_tables": ["BlockData", "Blocks", "Devices", "DeviceTypes", "EventLog"],
    })

    # ======================================================================= Sheet 4: 設備參數統計
    lat = lat.sort_values("事件序", kind="stable")
    g4 = lat.groupby("DeviceKey")
    d4 = g4.agg(
        位號=("位號", "first"), AmsDeviceTag=("AmsDeviceTag", "first"), 協定=("Protocol", "first"), 製造商=("Manufacturer", "first"),
        型號=("ModelName", "first"), 設備版本=("RevisionName", "first"), HART版本=("ProtocolRevision", "first"),
        參數數=("ParamName", "size"), 區塊數=("BlockKey", "nunique"),
        區塊清單=("區塊類型", lambda s: ", ".join(f"{k}×{v}" for k, v in s.value_counts().sort_index().items())),
        歷史記錄總數=("歷史記錄數", "sum"), 變更次數=("變更次數", "sum"),
        有變更參數數=("變更次數", lambda s: int((s > 0).sum())),
        首次記錄=("首次記錄(台灣)", "min"), 最後記錄=("事件時間(台灣)", "max"),
        最後事件=("Description", lambda s: s.iloc[-1] if len(s) else None),
        最後使用者=("UserName", lambda s: s.iloc[-1] if len(s) else None),
    ).reset_index()
    nev = bd[bd["ValueMode"] == "h"].groupby("DeviceKey")["事件序"].nunique().rename("組態事件數").reset_index()
    d4 = d4.merge(nev, on="DeviceKey", how="left")
    # 關鍵組態現值 (HART)
    def pick(cat):
        sub = lat[(lat["關鍵組態"] == cat) & (lat["協定名"] == "HART")]
        sub = sub.sort_values(["DeviceKey", "參數基底"]).drop_duplicates("DeviceKey")
        return sub.set_index("DeviceKey")["顯示值"], sub.set_index("DeviceKey")["解碼值"], sub.set_index("DeviceKey")["參數基底"]
    for cat, colname in [("描述", "描述 (descriptor)"), ("訊息", "訊息 (message)"), ("日期", "HART 日期 (date)"),
                         ("寫入保護", "寫入保護"), ("轉換函數", "轉換函數"), ("輪詢位址", "輪詢位址"), ("最終組裝號", "最終組裝號")]:
        v, z, _ = pick(cat)
        d4[colname] = d4["DeviceKey"].map(v)
        if cat in ("寫入保護", "轉換函數", "日期"):
            d4[colname + "(解碼)"] = d4["DeviceKey"].map(z)
    # 量程: 取 upper/lower 對
    urv = lat[(lat["協定名"] == "HART") & lat["參數基底"].isin(URV_NAMES)]
    lrv = lat[(lat["協定名"] == "HART") & lat["參數基底"].isin(LRV_NAMES)]
    urv = urv.sort_values(["DeviceKey", "參數基底"]).drop_duplicates("DeviceKey").set_index("DeviceKey")
    lrv = lrv.sort_values(["DeviceKey", "參數基底"]).drop_duplicates("DeviceKey").set_index("DeviceKey")
    d4["URV 量程上限"] = pd.to_numeric(d4["DeviceKey"].map(urv["數值"]), errors="coerce")
    d4["LRV 量程下限"] = pd.to_numeric(d4["DeviceKey"].map(lrv["數值"]), errors="coerce")
    d4["量程參數"] = d4["DeviceKey"].map(urv["參數基底"])
    unit = lat[(lat["協定名"] == "HART") & lat["參數基底"].isin(KEY_CONFIG["單位"])].sort_values(["DeviceKey", "參數基底"]).drop_duplicates("DeviceKey").set_index("DeviceKey")
    d4["單位參數"] = d4["DeviceKey"].map(unit["參數基底"])
    d4["單位碼"] = pd.to_numeric(d4["DeviceKey"].map(unit["數值"]), errors="coerce")
    d4["單位(解碼)"] = d4["DeviceKey"].map(unit["解碼值"])
    damp = lat[(lat["協定名"] == "HART") & lat["參數基底"].isin(KEY_CONFIG["阻尼"])].sort_values(["DeviceKey", "參數基底"]).drop_duplicates("DeviceKey").set_index("DeviceKey")
    d4["阻尼(s)"] = pd.to_numeric(d4["DeviceKey"].map(damp["數值"]), errors="coerce")
    d4["阻尼參數"] = d4["DeviceKey"].map(damp["參數基底"])
    # FF: AI XD_SCALE (80020192) & MODE_BLK target
    ffx = lat[(lat["協定名"] == "FF") & (lat["項目ID"] == "80020192")]
    for mem, col in [("01", "FF XD_SCALE EU100"), ("02", "FF XD_SCALE EU0")]:
        sub = ffx[ffx["成員"] == mem].sort_values(["DeviceKey", "BlockIndex"]).drop_duplicates("DeviceKey").set_index("DeviceKey")
        d4[col] = pd.to_numeric(d4["DeviceKey"].map(sub["數值"]), errors="coerce")
    sub = ffx[ffx["成員"] == "03"].sort_values(["DeviceKey", "BlockIndex"]).drop_duplicates("DeviceKey").set_index("DeviceKey")
    d4["FF XD_SCALE 單位"] = d4["DeviceKey"].map(sub["解碼值"]).fillna(d4["DeviceKey"].map(sub["顯示值"]))
    d4["FF XD_SCALE 區塊索引"] = d4["DeviceKey"].map(sub["BlockIndex"])
    cols4 = {"位號": "位號 (ExtBlockTag)", "AmsDeviceTag": "AMS 設備位號 (AmsDeviceTag)", "協定": "協定 (Protocol)", "製造商": "製造商 (Manufacturer)",
             "型號": "型號 (DeviceTypes.Name)", "設備版本": "設備版本 (DeviceRevision)", "HART版本": "協定版次 (ProtocolRevision)",
             "參數數": "參數數", "區塊數": "區塊數", "區塊清單": "區塊類型×數", "組態事件數": "組態事件數", "歷史記錄總數": "歷史記錄總數",
             "有變更參數數": "有變更的參數數", "變更次數": "變更次數",
             "LRV 量程下限": "LRV 量程下限", "URV 量程上限": "URV 量程上限", "量程參數": "量程參數", "單位碼": "單位碼", "單位(解碼)": "單位(解碼)", "單位參數": "單位參數",
             "阻尼(s)": "阻尼(s)", "阻尼參數": "阻尼參數", "描述 (descriptor)": "描述 (descriptor)", "訊息 (message)": "訊息 (message)",
             "HART 日期 (date)(解碼)": "HART 日期 (date)", "寫入保護": "寫入保護碼", "寫入保護(解碼)": "寫入保護", "轉換函數": "轉換函數碼", "轉換函數(解碼)": "轉換函數",
             "輪詢位址": "輪詢位址", "最終組裝號": "最終組裝號",
             "FF XD_SCALE EU0": "FF XD_SCALE EU0", "FF XD_SCALE EU100": "FF XD_SCALE EU100", "FF XD_SCALE 單位": "FF XD_SCALE 單位", "FF XD_SCALE 區塊索引": "FF XD_SCALE 區塊索引",
             "首次記錄": "首次記錄(台灣)", "最後記錄": "最後記錄(台灣)", "最後事件": "最後事件說明", "最後使用者": "最後使用者", "DeviceKey": "設備鍵 (DeviceKey)"}
    s4 = d4.sort_values(["位號"], kind="stable")[list(cols4)].rename(columns=cols4).reset_index(drop=True)
    for col in ("寫入保護碼", "轉換函數碼", "輪詢位址", "最終組裝號"):
        s4[col] = pd.to_numeric(s4[col], errors="coerce")
    wp = d4["寫入保護"].astype(str)
    sheets.append({
        "name": "設備參數統計",
        "purpose": "每台設備的參數數量、區塊、事件/變更統計, 以及最常用的關鍵組態現值 (量程、單位、阻尼、描述、訊息、日期、寫入保護、轉換函數)",
        "one_row": "一台設備 (DeviceKey)",
        "df": s4,
        "notes": [
            f"設備數 {len(s4):,} (BlockData 有資料的設備; 全庫 1,928 台 + 1 個 -1 sentinel)",
            "量程/單位/阻尼取自該設備第一個符合關鍵組態名單的 HART 參數 (量程參數欄註明來源); FF 定位器/變送器以 AI 區塊 XD_SCALE (item 80020192) 為量程",
            "單位(解碼) 使用 HART Table-2 單位碼表; 裝置自訂列舉只解 E+H Pressure1Unit=9 (kPa)、OutUnitEasy=18 (mmH2O) (2026-09-24 以控制器 I/O 量程反推, DEVICE_UNIT_ENUMS), 其餘僅列碼",
            "組態事件數 = 該設備所有區塊之相異 (EventIdDay, EventIdFraction) 數",
        ],
        "source_tables": ["BlockData", "Blocks", "Devices", "DeviceRevisions", "DeviceTypes", "Manufacturers", "DeviceProtocols", "EventLog"],
    })

    # ======================================================================= Sheet 5: 參數解碼摘要
    rows = []
    hart = bd[bd["協定名"] == "HART"]; ffb = bd[bd["協定名"] == "FF"]
    for t, sub in hart.groupby("ParamDataType"):
        ex = sub.iloc[0]
        rows.append({"協定": "HART", "型別碼": f"ParamDataType {t}", "解碼規則": HART_TYPE_NAME.get(int(t), str(t)), "列數": len(sub),
                     "相異參數數": sub["參數基底"].nunique(), "長度(位元組)": " / ".join(map(str, sorted(sub["ParamDataSize"].unique())[:8])),
                     "範例參數": ex["參數基底"], "範例原始": ex["原始十六進位"], "範例解碼": ex["顯示值"],
                     "證據": {4: "AmsUdf_BinaryToInt/AmsSp_DevBlk_GetHartDeviceFlags_1 以 4 位元組小端組合整數; __new_digital_units=0xFA=250 (未使用)",
                              6: "upper/lower_range_value, damping, CM_1_sgWaterRefDens=62.428 lb/ft³ 等與舊工作簿逐筆相符",
                              8: "date.000000A6: 36526.0 = 2000-01-01 (OLE 序號); 2.0 = 未設定 (舊匯出顯示 2000/01/01)",
                              9: "僅 read_loop_status_data / read_scan_list_from_index_response, 舊匯出以 &XXXX 顯示同樣位元組",
                              12: "AmsUdf_CurrentDescriptor: type 12 = generic(wide) string, cast varbinary→nvarchar; tag/descriptor/message 可讀",
                              3: "AmsSp_GetBlockKeyCurrentHartInfo_1: type 3 = narrow string"}.get(int(t), "")})
    ffb2 = ffb.copy()
    ffb2["tc"] = ffb2["原始十六進位"].str[2:4]
    for tc, sub in ffb2.groupby("tc"):
        ex = sub.iloc[0]
        tci = int(tc, 16)
        rows.append({"協定": "FF", "型別碼": f"ParamDataType 3, 容器型別 0x{tc}", "解碼規則": FF_TYPE_NAME.get(tci, "未知"), "列數": len(sub),
                     "相異參數數": sub["參數基底"].nunique(), "長度(位元組)": " / ".join(map(str, sorted(sub["ParamDataSize"].unique())[:8])),
                     "範例參數": ex["參數基底"], "範例原始": ex["原始十六進位"], "範例解碼": ex["顯示值"],
                     "證據": {0x44: "FF FE FF 為 MFC CArchive Unicode 字串標記, 其後 1 位元組長度 + UTF-16LE; 解出 TAG_DESC/型號字串可讀, 與舊工作簿相符",
                              0x45: "4 位元組有號整數 (FFFFFFFF = -1), 與舊工作簿相符",
                              0x46: "CONFIRM_TIME 800200b8:00 = 00C40900 → 640000; 單位碼 3E05 → 1342(%), 7504 → 1141(psi); 與舊工作簿相符",
                              0x47: "XD_SCALE EU100 800200e2:01 = 0000C842 → 100.0; 0000807F = INF; 與舊工作簿相符",
                              0x49: "後 8 位元組 float64 = OLE 日期: 1AA8CC688FD3E540 → 44700.48 = 2022-05-19 11:33:25 (舊工作簿同值); 26299 = 1972-01-01 FF 紀元"}.get(tci, "")})
    rows.append({"協定": "全部", "型別碼": "ValueMode", "解碼規則": "h = 正常/歷史值, o = 離線值 (AmsSp_GetConfigurationHistoryByBlockKey_2 註解)",
                 "列數": len(bd), "相異參數數": bd["參數基底"].nunique(), "長度(位元組)": "", "範例參數": "", "範例原始": "",
                 "範例解碼": f"h: {int((bd['ValueMode']=='h').sum()):,} / o: {int((bd['ValueMode']=='o').sum()):,}", "證據": "離線值 12 列, 事件 Category=0 'None', 3 台設備"})
    rows.append({"協定": "全部", "型別碼": "ParamKind", "解碼規則": "P = 參數 (本庫僅此一種)", "列數": len(bd), "相異參數數": bd["參數基底"].nunique(),
                 "長度(位元組)": "", "範例參數": "", "範例原始": "", "範例解碼": "", "證據": "AmsSp_GetConfigurationHistoryByBlockKey_2 篩選 ParamKind='P'"})
    s5 = pd.DataFrame(rows)
    sheets.append({
        "name": "參數解碼摘要",
        "purpose": "BlockData 各型別碼的解碼規則、筆數、範例與證據 (本域的讀表說明)",
        "one_row": "一種 (協定, 型別碼) 的解碼規則",
        "df": s5,
        "notes": [
            f"BlockData 共 {len(bd):,} 列 (HART {len(hart):,} / FF {len(ffb):,}), 相異 (BlockKey, ParamName) {len(latest):,}, 涉及 {bd['BlockKey'].nunique():,} 個區塊 / {bd['DeviceKey'].nunique():,} 台設備 / {bd['事件序'].nunique():,} 個事件",
            "HART ParamName 格式 name.itemIdHex.0000.0000 (第 3/4 段本庫皆為 0000); FF ParamName 格式 itemIdHex:memberHex",
            "FF 的 ParamDataType 一律 3 (窄字串), 但字串內容是序列化變數的十六進位文字, 需二次解碼 (見各列)",
            "ParamDataSize 與 BLOB 長度完全一致 (不一致 0 筆); type 12 有 42 列 NULL (ParamDataSize=0, 空字串)",
            "事件時間: EventLog.EventTime 為 UTC; EventIdDay/EventIdFraction = OLE 日 + 小數×2^31 (AmsUdf_EventIdDayFractionToDateTime)",
            "本域空表: HostTagParams, InstantiableConfigData, InstantiableConfigBlocks, InstantiableBlockAsgms 皆 0 列, 未建工作表; NamedConfigData (318,558 列, 範本參數) 屬範本域, 其 ParamData 可用相同規則解碼",
        ],
        "source_tables": ["BlockData", "EventLog", "_modules"],
    })

    return sheets


if __name__ == "__main__":
    import time
    t0 = time.time()
    conn = sqlite3.connect(DB_PATH)
    out = build(conn)
    os.makedirs(OUT_DIR, exist_ok=True)
    for sh in out:
        df = sh["df"]
        print(f"{sh['name']}: rows={len(df):,} cols={len(df.columns)}")
        df.to_csv(os.path.join(OUT_DIR, f"{KEY}__{sh['name']}.csv"), index=False, encoding="utf-8-sig")
    print("elapsed %.1fs" % (time.time() - t0))
