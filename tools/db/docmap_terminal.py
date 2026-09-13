"""docmap_terminal.py — DCS 端子表 (HT?-1-IMI01-A0001 IO_Signal) → 設備 alias 對照 JSON

用法:
  py tools/db/docmap_terminal.py <工程文件庫根目錄> <docs/db/data/sheets 目錄> <輸出 terminal.json>

規則:
  - 在文件庫全域找所有 *IMI01-A0001* 檔 (xlsx/pdf/gsheet)，全部寫進 searched。
  - 每個機組文件 (HT0/HT1/HT2/HT3) 選一份 xlsx：以新版為主
    (CoverSheet IO Revision 表最大 Rev → 欄數多者 → 修改時間新者)；其餘 used=false 並寫原因。
  - 文件版次字母取自同資料夾 PDF 檔名「<doc_id>-<字母>-…」中最大字母
    (該 PDF 封面 IO Revision 表須與 xlsx 最大 Rev 相同才採用，否則寫 '?')。
  - 比對：R1 = FLD_DEV 或 SIGNAL_NAME (trim/upper) 等於 03 現行位號；
          R6 = SIGNAL_NAME 為「位號+字尾」(位號長度>=8，最長者優先)；
          R1b = 以 04 位號索引 (舊位號/HostTag/AmsDeviceTag) 相等比對 (rule 註明來源類型)。
  - 輸出中不含本機絕對路徑；folder 為相對文件庫根目錄。
"""
import sys, os, re, json, glob, datetime, subprocess, warnings

warnings.filterwarnings("ignore")
import openpyxl

GEN = "tools/db/docmap_terminal.py"


def s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return repr(v)
    return str(v).strip()


def num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else v
    try:
        f = float(str(v).strip())
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def rel(root, p):
    return os.path.relpath(p, root).replace("\\", "/")


def cover_info(wb):
    """回傳 (最大 IO Rev, 日期字串, CoverSheet 'Revision' 欄值)"""
    if "CoverSheet" not in wb.sheetnames:
        return None, "", None
    best, date, cover_rev = None, "", None
    started = False
    for r in wb["CoverSheet"].iter_rows(values_only=True):
        v = [c for c in r if c is not None]
        if not v:
            continue
        if not started and str(v[0]).strip() == "Revision" and len(v) >= 2:
            cover_rev = s(v[1])
            continue
        if str(v[0]).strip() == "Rev":
            started = True
            continue
        if started and len(v) >= 2 and isinstance(v[1], datetime.datetime):
            rv = v[0]
            if isinstance(rv, (int, float)):
                if best is None or rv > best:
                    best, date = int(rv), v[1].strftime("%Y-%m-%d")
            elif best is None:
                best, date = 0, v[1].strftime("%Y-%m-%d")
    return best, date, cover_rev


def pdf_rev_letter(root, folder_files, doc_id, io_rev):
    """同 doc_id 的 '<doc_id>-<字母>-' PDF 中最大字母，且封面 IO Revision 表含 io_rev。"""
    cands = []
    for p in folder_files:
        b = os.path.basename(p)
        m = re.match(re.escape(doc_id) + r"-([A-Z])(?:[\s\-(]|$)", b)
        if m and b.lower().endswith(".pdf") and "__" not in b:
            cands.append((m.group(1), p))
    cands.sort(key=lambda x: x[0], reverse=True)
    for letter, p in cands:
        try:
            txt = subprocess.run(["pdftotext", "-l", "3", "-layout", p, "-"],
                                 capture_output=True, timeout=120).stdout.decode("utf-8", "ignore")
        except Exception:
            continue
        if io_rev is None or re.search(r"Rev%d for" % io_rev, txt):
            return letter, p, cands
    return "?", None, cands


def pdf_cover_rev(p):
    """PDF 前 3 頁封面 'RevN for' 的最大 N；無則 None。"""
    try:
        txt = subprocess.run(["pdftotext", "-l", "3", "-layout", p, "-"],
                             capture_output=True, timeout=120).stdout.decode("utf-8", "ignore")
    except Exception:
        return None
    revs = [int(x) for x in re.findall(r"Rev ?(\d+)[a-z]? for", txt)]
    return max(revs) if revs else None


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    root, sheets_dir, out = sys.argv[1:4]

    # --- AMS 位號 → alias
    d03 = json.load(open(os.path.join(sheets_dir, "03.json"), encoding="utf-8"))
    t2a = {}
    for r in d03["rows"]:
        if r[0] is not None and s(r[0]):
            t2a.setdefault(s(r[0]).upper(), s(r[1]))
    idx04 = {}
    p04 = os.path.join(sheets_dir, "04.json")
    if os.path.exists(p04):
        d04 = json.load(open(p04, encoding="utf-8"))
        for r in d04["rows"]:
            key, typ, alias, ndev = s(r[0]).upper(), s(r[2]), s(r[4]), r[7]
            if typ[:1] in ("2", "3", "4") and key and ndev == 1 and len(key) >= 6:
                idx04.setdefault(key, (alias, typ))

    # --- 找所有副本
    allf = sorted(glob.glob(os.path.join(root, "**", "*IMI01-A0001*"), recursive=True))
    searched = []
    xl_by_doc = {}
    for p in allf:
        b = os.path.basename(p)
        m = re.match(r"(HT\d-1-IMI01-A0001)", b)
        if not m:
            continue
        doc = m.group(1)
        ent = {"doc_id": doc, "rev": "", "title": b, "folder": rel(root, os.path.dirname(p)),
               "used": False, "why": ""}
        ext = b.lower().rsplit(".", 1)[-1]
        lm = re.match(re.escape(doc) + r"-([A-Z])(?:[\s\-(]|$)", b)
        if lm:
            ent["rev"] = lm.group(1)
        if ext == "xlsx":
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
            io_rev, io_date, cover_rev = cover_info(wb)
            ws = wb["IO_Signal"] if "IO_Signal" in wb.sheetnames else None
            ncol = ws.max_column if ws else 0
            ent["_io"] = (io_rev, io_date, ncol, os.path.getmtime(p), p, cover_rev)
            xl_by_doc.setdefault(doc, []).append(ent)
            wb.close()
        elif ext == "gsheet":
            ent["why"] = "Google 試算表捷徑 (無資料)"
        elif ext == "pdf":
            ent["why"] = "PDF 列印版 (欄位錯位不可結構化解析；資料以同版 xlsx 為準)"
            if "_舊版" in ent["folder"]:
                ent["why"] = "舊版資料夾 PDF (被取代)"
            if "__fixed" in b or "__v2" in b:
                ent["why"] = "PDF 修復/轉存副本"
        searched.append(ent)

    chosen = {}
    for doc, ents in xl_by_doc.items():
        # 使用者規則：版次大者（CoverSheet IO Revision 表最大 Rev）→ 同版次取修改時間最新
        ents.sort(key=lambda e: (e["_io"][0] if e["_io"][0] is not None else -1, e["_io"][3]),
                  reverse=True)
        best = ents[0]
        io_rev, io_date, ncol, mt, p, cover_rev = best["_io"]
        letter, pdfp, cands = pdf_rev_letter(root, [x for x in allf if os.path.basename(x).startswith(doc)],
                                             doc, io_rev)
        best["used"] = True
        if letter != "?":
            # xlsx 本身沒有版次字母（CoverSheet「Revision」欄未隨 IO Rev 更新）：字母取自同 IO Rev 的 PDF 檔名 → 推定
            best["rev"] = letter
            best["ref"] = "%s-%s（推定）" % (doc, letter)
            best["why"] = ("採用：IO Rev%s (%s)，%d 欄；xlsx 無版次字母（CoverSheet Revision=%s），"
                           "版次 %s 依同資料夾 PDF「%s-%s-…」封面 IO Revision 表含 Rev%s 推定"
                           % (io_rev, io_date, ncol, cover_rev if cover_rev not in (None, "") else "空白",
                              letter, doc, letter, io_rev))
        else:
            best["rev"] = ""
            best["ref"] = "%s（IO Rev%s，版次字母不明）" % (doc, io_rev)
            best["why"] = ("採用：IO Rev%s (%s)，%d 欄；xlsx 無版次字母（CoverSheet Revision=%s），"
                           "且無封面 IO Revision 表含 Rev%s 的 PDF，版次字母不明"
                           % (io_rev, io_date, ncol, cover_rev if cover_rev not in (None, "") else "空白", io_rev))
        if len(ents) > 1:
            best["why"] += "；同版次多副本取修改時間最新"
        for e in ents[1:]:
            r2 = e["_io"]
            e["rev"] = (letter if letter != "?" else "") if r2[0] == io_rev else e["rev"]
            if r2[0] is None:
                e["why"] = "無 CoverSheet 修訂表，無法判定版次，未採用 (%d 欄)" % r2[2]
            elif io_rev is not None and r2[0] < io_rev:
                e["why"] = "被取代：IO Rev%s < Rev%s" % (r2[0], io_rev)
            else:
                e["why"] = "副本：同 IO Rev%s，修改時間較舊，未採用 (%d 欄；採用者 %d 欄)" % (r2[0], r2[2], ncol)
        newer = []
        for e in searched:
            if e["doc_id"] != doc or not e["title"].lower().endswith(".pdf") or not e["rev"]:
                continue
            if letter != "?" and e["rev"] == letter:
                if "_舊版" not in e["folder"] and "__" not in e["title"]:
                    e["why"] = "同版 %s 的 PDF 列印版 (資料取自同版 xlsx)" % letter
            elif letter != "?" and e["rev"] < letter:
                e["why"] = "被取代：版次 %s < %s" % (e["rev"], letter)
            else:
                # 字母高於採用版次，或採用版次不明：以封面 IO Revision 表判斷新舊
                pr = pdf_cover_rev(os.path.join(root, e["folder"], e["title"]))
                if pr is not None and io_rev is not None and pr < io_rev:
                    e["why"] = "被取代：PDF 封面 IO Rev%d < 採用 xlsx Rev%d" % (pr, io_rev)
                else:
                    e["why"] = ("較新版 PDF (版次 %s；封面 IO Rev%s，採用 xlsx 為 Rev%s)；"
                                "無同版 xlsx，PDF 欄位錯位不可結構化解析，未採用"
                                % (e["rev"], pr if pr is not None else "不可辨識", io_rev))
                    if "__" not in e["title"]:
                        newer.append(e["rev"])
        if newer:
            best["why"] += "；注意：另有較新版 PDF %s 無對應 xlsx" % "/".join(sorted(set(newer)))
        chosen[doc] = best

    # --- 解析
    by_alias = {}
    stats_doc = {}
    rows_total = 0
    kks = sorted([t for t in t2a if len(t) >= 8], key=len, reverse=True)
    for doc, ent in sorted(chosen.items()):
        p = ent["_io"][4]
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        rows = wb["IO_Signal"].iter_rows(values_only=True)
        hdr = [s(h) for h in next(rows)]
        H = {h: i for i, h in enumerate(hdr) if h}
        next(rows)  # 第 2 列為欄位說明
        g = lambda r, k: r[H[k]] if k in H and H[k] < len(r) else None
        nmatch = 0
        for i, r in enumerate(rows, start=3):
            sn = s(g(r, "SIGNAL_NAME")).upper()
            fd = s(g(r, "FLD_DEV")).upper()
            if not sn and not fd:
                continue
            alias = rule = None
            if fd in t2a:
                alias, rule = t2a[fd], "R1"
            elif sn in t2a:
                alias, rule = t2a[sn], "R1"
            else:
                for t in kks:
                    if sn.startswith(t) and len(sn) > len(t):
                        alias, rule = t2a[t], "R6"
                        break
                if alias is None:
                    for k in (fd, sn):
                        if k in idx04:
                            alias, rule = idx04[k][0], "R1b(04索引:%s)" % idx04[k][1]
                            break
            if alias is None:
                continue
            nmatch += 1
            f = []
            add = lambda name, v: f.append([name, s(v)])
            add("訊號名", g(r, "SIGNAL_NAME"))
            add("說明 DESC", g(r, "DESC"))
            add("訊號等級", g(r, "SIG_LEVEL"))
            add("HART", g(r, "SIG_MODIFIER") or "")
            add("DCS 量程下限", g(r, "DEVICE_LO"))
            add("DCS 量程上限", g(r, "DEVICE_HI"))
            add("DCS 單位", g(r, "DEVICE_UNITS"))
            for ak in ("3_HI_ALARM", "2_HI_ALARM", "1_HI_ALARM", "1_LO_ALARM", "2_LO_ALARM", "3_LO_ALARM"):
                if s(g(r, ak)) != "":
                    add("警報 " + ak.replace("_ALARM", ""), g(r, ak))
            add("系統", g(r, "SYSTEM"))
            add("控制器", g(r, "CONTROLLER"))
            add("位置", g(r, "LOCATION"))
            add("盤櫃 CABINET", g(r, "CABINET"))
            add("Case", g(r, "CASE"))
            add("卡位 COL_ROW", g(r, "COL_ROW"))
            add("點號 POINT", g(r, "POINT"))
            add("PACK_TYPE", g(r, "PACK_TYPE"))
            add("端子 TB_PT_1/2", "/".join(x for x in (s(g(r, "TB_PT_1")), s(g(r, "TB_PT_2"))) if x))
            for fk in ("FF_MUX_DEV", "FF_MUX_CHANNEL", "FF_MUX_POINT_TYPE"):
                v = s(g(r, fk))
                if v not in ("", "0"):
                    add(fk, v)
            add("P&ID", g(r, "PID"))
            add("邏輯圖", g(r, "LOGIC"))
            f.append(["DCS量程下限_num", num(g(r, "DEVICE_LO"))])
            f.append(["DCS量程上限_num", num(g(r, "DEVICE_HI"))])
            by_alias.setdefault(alias, []).append({
                "doc_id": doc, "rev": ent["rev"], "ref": ent["ref"], "loc": "IO_Signal!r%d" % i, "rule": rule,
                "level": "doc", "fields": f})
        wb.close()
        stats_doc[doc] = nmatch
        rows_total += nmatch

    for e in searched:
        e.pop("_io", None)
    searched.sort(key=lambda e: (e["doc_id"], not e["used"], e["folder"], e["title"]))
    rules = {}
    for v in by_alias.values():
        for x in v:
            rules[x["rule"]] = rules.get(x["rule"], 0) + 1
    res = {
        "kind": "terminal",
        "generated_by": GEN,
        "searched": searched,
        "by_alias": dict(sorted(by_alias.items())),
        "stats": {
            "aliases_matched": len(by_alias),
            "rows": rows_total,
            "notes": "每文件命中列數 %s；規則分布 %s。設計文件 (GE IO Signal Report)，非 DCS 現行組態；"
                     "HT0/HT2/HT3 無 AMS 位號命中。" % (stats_doc, rules),
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fo:
        json.dump(res, fo, ensure_ascii=False, indent=1)
    print(json.dumps(res["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
