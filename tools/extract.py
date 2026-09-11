# -*- coding: utf-8 -*-
"""AMS workbook -> static site data (CONTRACT.md v2).

Usage:  py tools/extract.py "<xlsx>" docs/data

Writes docs/data/manifest.json and docs/data/sheets/*.json (old outputs are
removed first).  Deterministic: no timestamps of the run are embedded.
"""
import os
import re
import sys
import json
import time
import glob
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from amsx_common import SHEET_MODES, CHUNKED_IDS, CHUNK_TARGET_ROWS, short_name, TABLE_DATA_FIRST_ROW  # noqa: E402
from amsx.xlsx import Workbook, parse_range  # noqa: E402
from amsx.formula import Evaluator, Formula, Link  # noqa: E402
from amsx.values import LinkResolver, plain_value  # noqa: E402
from amsx.table import build_table, chunk_parts  # noqa: E402
from amsx.grid import build_grid  # noqa: E402
from amsx.card import build_card, build_link_index, verify_default  # noqa: E402
from amsx.charts import ChartBuilder  # noqa: E402
from amsx import config  # noqa: E402
import stamp_assets  # noqa: E402

MAX_FILE_BYTES = 8 * 1024 * 1024

EXPECTED_ROWS = {"03": 1928, "04": 1675, "05": 14066, "06": 1928, "07": 1013, "08": 6386, "09": 140, "10": 13682,
                 "11": 5138, "12": 2007, "13": 761, "15": 201, "19": 3484, "20": 9271, "21": 204562,
                 "22": 140381, "23": 890, "25": 2126, "26": 2178, "27": 1370}


class Ctx(object):
    pass


def log(msg):
    print(msg, flush=True)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def write_json(path, obj):
    data = dumps(obj).encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def toc_from_00(ctx, sh):
    """00_說明 table of contents rows (A = HYPERLINK to a sheet)."""
    names = set(ctx.wb.sheet_names)
    out = []
    for r in sorted(sh.rows):
        raw = sh.raw(r, 1)
        if not isinstance(raw, Formula):
            continue
        v = ctx.ev.value(sh.name, r, 1)
        if isinstance(v, Link) and v.label in names:
            out.append({"id": v.label[:2], "name": v.label, "purpose": sh.raw(r, 2), "row_unit": sh.raw(r, 3),
                        "rows": sh.raw(r, 4), "sources": sh.raw(r, 5), "r": r})
    return out


def legend_from_00(ctx, sh, sections):
    """00 section '圖例': bold group rows + coloured sample cells with descriptions."""
    sec = [s for s in sections if "圖例" in s["label"]]
    if not sec:
        return []
    r0 = sec[0]["r"]
    nxt = min([s["r"] for s in sections if s["r"] > r0] or [sh.max_row + 1])
    out = []
    group = None
    for r in range(r0 + 1, nxt):
        a, b = sh.raw(r, 1), sh.raw(r, 2)
        if a is None:
            continue
        xf = sh.xf(r, 1)
        if b is None:
            group = a
            continue
        item = {"group": group, "label": a, "bg": xf.fill, "fc": xf.font.color if xf.font.color != "#000000" else None,
                "desc": b}
        if xf.font.b:
            item["b"] = 1
        if xf.font.i:
            item["i"] = 1
        if xf.font.u:
            item["u"] = 1
        if xf.border:
            item["bd"] = 1
        out.append(item)
    return out


def named_tables(wb, sheet_name):
    out = []
    for d in wb.defined_names:
        if d["local"] is not None or not d["ref"] or "!" not in d["ref"]:
            continue
        shn, ref = d["ref"].rsplit("!", 1)
        if shn.strip("'") != sheet_name:
            continue
        r1, c1, r2, c2 = parse_range(ref)
        sh = wb.load_sheet(sheet_name)
        last_a = sh.raw(r2, c1)
        out.append({"name": d["name"], "ref": ref.replace("$", ""), "title_row": r1 - 1, "header_row": r1,
                    "spec_row": r1 + 1, "first": r1 + 2, "last": r2,
                    "total_row": r2 if isinstance(last_a, str) and "合計" in last_a else None,
                    "source_row": r2 + 1, "cols": c2 - c1 + 1})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xlsx")
    ap.add_argument("outdir")
    args = ap.parse_args(argv)
    t0 = time.time()
    outdir = os.path.abspath(args.outdir)
    sheets_dir = os.path.join(outdir, "sheets")
    os.makedirs(sheets_dir, exist_ok=True)
    for p in glob.glob(os.path.join(sheets_dir, "*.json")) + [os.path.join(outdir, "manifest.json")]:
        if os.path.exists(p):
            os.remove(p)

    log("[load] %s" % args.xlsx)
    wb = Workbook(args.xlsx)
    for n in wb.sheet_names:
        t = time.time()
        sh = wb.load_sheet(n)
        log("  %-18s rows=%-7d cols=%-4d formulas=%-6d %.1fs" % (n, sh.max_row, sh.max_col, sh.formula_count, time.time() - t))
    log("[load] done %.1fs" % (time.time() - t0))

    modes = {}
    for n in wb.sheet_names:
        sid = n[:2]
        if sid not in SHEET_MODES:
            raise SystemExit("unexpected sheet %r" % n)
        modes[sid] = SHEET_MODES[sid]
    dfr = {}
    for n in wb.sheet_names:
        sid = n[:2]
        sh = wb.sheets[n]
        if modes[sid] == "table":
            dfr[sid] = sh.autofilter[0] + 1 if sh.autofilter else TABLE_DATA_FIRST_ROW
    ctx = Ctx()
    ctx.wb = wb
    ctx.ev = Evaluator(wb)
    ctx.resolver = LinkResolver(wb, modes, dfr)
    ctx.warnings = []
    ctx.cf_hits = {}

    # charts (numbered in workbook sheet order, then anchor order)
    cb = ChartBuilder(ctx)
    charts_by_sheet = {}
    nchart = 1
    for n in wb.sheet_names:
        if wb.sheets[n].drawing_rids:
            chs = cb.charts_for_sheet(n, nchart)
            nchart += len(chs)
            charts_by_sheet[n[:2]] = chs
    log("[charts] %s" % ", ".join("%s:%s" % (k, "/".join(c["id"] for c in v)) for k, v in charts_by_sheet.items()))

    manifest_sheets = []
    table_rows = {}     # sid -> (rows, dfr) for card link_index + self-check
    grid_info = {}
    sheet_info = {}
    toc = []
    card_name = None
    for n in wb.sheet_names:
        sid = n[:2]
        mode = modes[sid]
        t = time.time()
        entry = {"id": sid, "name": n, "short": short_name(n), "group": config.SHEET_GROUP.get(sid, "其他"),
                 "mode": mode}
        if mode == "card":
            card_name = n
            manifest_sheets.append(entry)
            continue
        if mode == "grid":
            obj = build_grid(ctx, n, charts_by_sheet.get(sid))
            if sid == "00":
                toc = toc_from_00(ctx, wb.sheets[n])
                obj["toc"] = [{k: v for k, v in x.items() if k != "r"} for x in toc]
                obj["legend"] = legend_from_00(ctx, wb.sheets[n], obj["sections"])
            nt = named_tables(wb, n)
            if nt:
                obj["named_tables"] = nt
            fn = "sheets/%s.json" % sid
            size = write_json(os.path.join(outdir, fn), obj)
            entry.update({"rows": obj["max_row"], "cols": obj["max_col"], "files": [fn], "bytes": size})
            grid_info[sid] = obj
            log("[grid ] %-18s rows=%-5d cells=%-6d charts=%d  %8.1f KB  %.1fs" % (
                n, obj["max_row"], sum(len(r["cells"]) for r in obj["rows"]), len(obj["charts"]), size / 1024.0,
                time.time() - t))
        else:
            obj, info = build_table(ctx, n)
            rows = obj["rows"]
            table_rows[sid] = (rows, info["first"])
            sheet_info[sid] = info
            files = []
            total = 0
            chunk = sid in CHUNKED_IDS
            if not chunk:
                data = dumps(obj).encode("utf-8")
                if len(data) > MAX_FILE_BYTES:
                    chunk = True
            if chunk:
                gcol = obj["ui"].get("group_col", obj["ui"].get("alias_col", 0))
                # facet dropdowns must work before every part is loaded
                fv = {}
                for fc in list(obj["ui"].get("facets", [])) + list(obj["ui"].get("facets_extra", [])):
                    seen = {}
                    for row in rows:
                        v = row[fc]
                        if isinstance(v, dict):
                            v = v.get("t", v.get("v"))
                        if v is not None and v not in seen:
                            seen[v] = 1
                            if len(seen) > 500:
                                break
                    if len(seen) <= 500:
                        fv[str(fc)] = list(seen)
                obj["ui"]["facet_values"] = fv
                parts, offsets, nblocks = chunk_parts(obj, gcol, CHUNK_TARGET_ROWS)
                _check_zebra(ctx, wb.sheets[n], info, gcol, rows)
                for k, p in enumerate(parts):
                    fn = "sheets/%s-%03d.json" % (sid, k)
                    total += write_json(os.path.join(outdir, fn), p)
                    files.append(fn)
                entry["part_offsets"] = offsets
                log("[table] %-18s rows=%-7d cols=%-4d parts=%d (blocks=%d) %8.1f KB  %.1fs" % (
                    n, len(rows), info["cols"], len(parts), nblocks, total / 1024.0, time.time() - t))
                if sid not in ("03", "06", "07", "08", "10", "11", "12"):
                    obj["rows"] = None  # free memory for the big sheets
                    table_rows[sid] = (None, info["first"])
                    del parts
            else:
                fn = "sheets/%s.json" % sid
                with open(os.path.join(outdir, fn), "wb") as f:
                    f.write(data)
                total = len(data)
                files.append(fn)
                log("[table] %-18s rows=%-7d cols=%-4d %8.1f KB  styles=%d cell_styles=%d row_styles=%d  %.1fs" % (
                    n, len(rows), info["cols"], total / 1024.0, len(obj["styles"]), len(obj["cell_styles"]),
                    len(obj["row_styles"]), time.time() - t))
            entry.update({"rows": len(rows) if rows is not None else info["rows"], "cols": info["cols"],
                          "files": files, "bytes": total})
            if info["dropped"]:
                entry["dropped_cols"] = info["dropped"]
        manifest_sheets.append(entry)

    # ---- card (needs the table rows) ----------------------------------------------
    t = time.time()
    card = build_card(ctx, card_name)
    card["link_index"] = build_link_index(ctx, card, table_rows)
    fn = "sheets/02.json"
    size = write_json(os.path.join(outdir, fn), card)
    for e in manifest_sheets:
        if e["id"] == "02":
            e.update({"rows": 0, "cols": 0, "files": [fn], "bytes": size})
    log("[card ] %-18s fields=%d links=%d link_index=%d  %8.1f KB  %.1fs" % (
        card_name, sum(len(s["fields"]) for s in card["sections"]), len(card["links"]), len(card["link_index"]),
        size / 1024.0, time.time() - t))

    # ---- manifest -------------------------------------------------------------------
    toc_by_id = {x["id"]: x for x in toc}
    for e in manifest_sheets:
        tx = toc_by_id.get(e["id"])
        if tx:
            e["desc"] = tx["purpose"]
            e["row_unit"] = tx["row_unit"]
            e["sources"] = tx["sources"]
            e["toc_rows"] = tx["rows"]
        else:
            e["desc"] = None
        tc = wb.sheets[e["name"]].tab_color
        if tc:
            e["tab_color"] = tc
    s00 = wb.sheets[wb.name_by_id("00")]
    s01 = wb.sheets[wb.name_by_id("01")]
    sub = s00.raw(2, 2) or ""
    m_src = re.search(r"資料來源\s*(\S+?)(?:｜|$)", sub)
    m_blt = re.search(r"建置\s*([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2})", sub)
    manifest = {
        "workbook": {"title": s00.raw(1, 2), "subtitle": sub, "summary_title": s01.raw(1, 2),
                     "summary_subtitle": s01.raw(2, 2),
                     "source": m_src.group(1) if m_src else None, "built": m_blt.group(1) if m_blt else None,
                     "xlsx": os.path.basename(args.xlsx)},
        "groups": config.GROUPS,
        "sheets": manifest_sheets,
        "search": {"index_sheet": "05", "key_col": 0, "alias_col": 4, "count_col": 7, "prio_col": 2, "tag_col": 3},
    }
    size = write_json(os.path.join(outdir, "manifest.json"), manifest)
    # build hash over every output file (deterministic): the front-end versions data URLs with it (?v=<build>)
    manifest["build"] = stamp_assets.data_build(outdir)
    size = write_json(os.path.join(outdir, "manifest.json"), manifest)
    log("[manifest] %d sheets  %.1f KB  build %s" % (len(manifest_sheets), size / 1024.0, manifest["build"]))
    docs_dir = os.path.dirname(outdir)
    if os.path.exists(os.path.join(docs_dir, "index.html")):
        log("[stamp] %s" % json.dumps(stamp_assets.stamp(docs_dir)))

    # ---- self-check -----------------------------------------------------------------
    problems = self_check(ctx, outdir, manifest, table_rows, grid_info, card)
    total_bytes = sum(e.get("bytes", 0) for e in manifest_sheets)
    log("[done] %d files, %.1f MB, %.1fs" % (sum(len(e.get("files", [])) for e in manifest_sheets) + 1,
                                            total_bytes / 1048576.0, time.time() - t0))
    if ctx.warnings:
        log("[warnings] %d" % len(ctx.warnings))
        for w in ctx.warnings[:50]:
            log("  - " + w)
    if ctx.resolver.warnings:
        log("[link warnings] %d" % len(ctx.resolver.warnings))
        for w in ctx.resolver.warnings[:50]:
            log("  - " + w)
    if problems:
        log("[SELF-CHECK FAILED] %d problem(s)" % len(problems))
        for p in problems:
            log("  ! " + p)
        return 1
    log("[self-check] OK")
    return 0


def _check_zebra(ctx, sh, info, gcol, rows):
    """The dropped parity column must equal the alternation of alias blocks
    (so ui.group_zebra reproduces the Excel CF exactly)."""
    sid = sh.id
    for ci, why in config.DROP_COLS.get(sid, {}).items():
        c = ci + 1
        blk = -1
        prev = object()
        bad = 0
        first = info["first"]
        for i, row in enumerate(rows):
            a = row[gcol]
            if a != prev:
                blk += 1
                prev = a
            q = sh.raw(first + i, c)
            if q != blk % 2:
                bad += 1
        if bad:
            ctx.warnings.append("%s: dropped parity column %s differs from block alternation in %d rows" % (sid, c, bad))


def self_check(ctx, outdir, manifest, table_rows, grid_info, card):
    problems = []
    rows_by_id = {}
    grid_rows = {}
    for e in manifest["sheets"]:
        sid = e["id"]
        n = 0
        cols = None
        offs = []
        for k, fn in enumerate(e.get("files", [])):
            with open(os.path.join(outdir, fn), "rb") as f:
                obj = json.loads(f.read().decode("utf-8"))
            if obj.get("mode") == "table":
                if "part" in obj:
                    offs.append(obj["part"]["row_offset"])
                    if obj["part"]["row_offset"] != n:
                        problems.append("%s part %d offset %s != %d" % (sid, k, obj["part"]["row_offset"], n))
                n += len(obj["rows"])
                cols = len(obj["columns"])
                for ri, row in enumerate(obj["rows"]):
                    if len(row) != cols:
                        problems.append("%s row %d has %d cells (expected %d)" % (sid, ri, len(row), cols))
                        break
            elif obj.get("mode") == "grid":
                grid_rows[sid] = {r["r"] for r in obj["rows"]}
                n = obj["max_row"]
        rows_by_id[sid] = n
        if e.get("part_offsets") is not None and e["part_offsets"] != offs:
            problems.append("%s part_offsets mismatch" % sid)
        if e["mode"] == "table" and e["rows"] != n:
            problems.append("%s manifest rows %s != file rows %d" % (sid, e["rows"], n))
        exp = EXPECTED_ROWS.get(sid)
        if exp is not None and n != exp:
            problems.append("%s rows %d != expected %d" % (sid, n, exp))
        for fn in e.get("files", []):
            sz = os.path.getsize(os.path.join(outdir, fn))
            if sz > MAX_FILE_BYTES:
                problems.append("%s: %s is %.1f MB (> 8 MB)" % (sid, fn, sz / 1048576.0))
    # links
    modes = {e["id"]: e["mode"] for e in manifest["sheets"]}
    nlinks = 0
    for src, where, tid, r, xrow in ctx.resolver.records:
        nlinks += 1
        m = modes.get(tid)
        if m == "table":
            if r is not None and not (0 <= r < rows_by_id[tid]):
                problems.append("link %s %s -> %s r=%s out of range" % (src, where, tid, r))
        elif m == "grid":
            if not (1 <= r <= rows_by_id[tid]):
                problems.append("link %s %s -> %s r=%s out of range" % (src, where, tid, r))
        elif m == "card":
            if r is not None:
                problems.append("link %s %s -> card with r=%s" % (src, where, r))
        else:
            problems.append("link %s %s -> unknown sheet %s" % (src, where, tid))
    log("[self-check] %d links validated" % nlinks)
    # formula / KPI spot checks (spec vectors)
    ev = ctx.ev

    def V(sid, ref):
        m = re.match(r"^([A-Z]+)(\d+)$", ref)
        from amsx.xlsx import col_index
        v = ev.value(ctx.wb.name_by_id(sid), int(m.group(2)), col_index(m.group(1)))
        return v.label if isinstance(v, Link) else v
    checks = [
        ("07", "S1", 155), ("07", "U1", 386), ("07", "W1", 454), ("07", "Y1", 18),
        ("01", "B6", 1928), ("01", "F6", 1577), ("01", "J6", 17), ("01", "N6", 0.9898507462686568), ("01", "R6", 87.4),
        ("01", "V6", "0 / 1,928"), ("01", "B11", 8116), ("01", "F11", 4757), ("01", "J11", 435), ("01", "N11", 379),
        ("01", "R11", 155), ("01", "V11", 429),
        ("14", "F6", 1928), ("14", "F7", 1577), ("14", "F8", 17), ("14", "F9", 0.9899), ("14", "F10", 87.4),
        ("14", "F11", 0), ("14", "F12", 8116), ("14", "F13", 4757), ("14", "F14", 435), ("14", "F15", 379),
        ("14", "F16", 155), ("14", "F17", 429), ("14", "F18", 7), ("14", "F19", 28), ("14", "F20", 26),
        ("14", "F21", 367), ("14", "F22", 1053), ("14", "F279", 13682),
        ("24", "E53", 1928), ("24", "E80", 204562), ("24", "E81", 140381), ("24", "E56", 1928), ("24", "E57", 1928),
    ]
    for sid, ref, exp in checks:
        got = V(sid, ref)
        if got != exp:
            problems.append("%s!%s = %r (expected %r)" % (sid, ref, got, exp))
    s14 = ctx.wb.name_by_id("14")
    s24 = ctx.wb.name_by_id("24")
    ifs = 0
    for (sname, r, c), v in list(ev.cache.items()):
        if sname in (s14, s24) and isinstance(v, str) and v in ("✓", "✗"):
            ifs += 1
            if v != "✓":
                problems.append("%s %d,%d evaluates to ✗" % (sname, r, c))
    log("[self-check] %d ✓/✗ formulas all ✓" % ifs if not any("✗" in p for p in problems) else "[self-check] ✗ found")
    # card default vector
    res = verify_default(ctx, card)
    exp = {"C4": "D00759", "G4": 1, "J3": 7410, "J4": 234,
           "F3": "來源：1 目前AMS位號［鍵 G11HAD60BT001］ → 目前位號 G11HAD60BT001"}
    for k, want in exp.items():
        got = res.get(k)
        if isinstance(got, Link):
            got = got.label
        if got != want:
            problems.append("02 %s = %r (expected %r)" % (k, got, want))
    b49 = res.get("B49")
    if not (isinstance(b49, Link) and b49.label == "→ 變更（有意義） 4 筆" and b49.target.endswith("!A323")):
        problems.append("02 B49 = %r" % (b49,))
    li = card["link_index"].get("D00759", {})
    if li.get("08") != [318, 4] or li.get("10") != [6698, 6] or li.get("06") != [1165, 1] or li.get("12") != [490, 1] \
            or "07" in li or "11" in li:
        problems.append("02 link_index D00759 = %r" % li)
    # every card link_index entry must agree with the evaluated formulas for a sample of aliases
    rows03 = table_rows["03"][0]
    i3 = next(i for i, row in enumerate(rows03) if row[1] == "D00759")
    if i3 != 229:
        problems.append("03 idx of D00759 = %d (expected 229)" % i3)
    # card fields resolve to 03 columns with the expected default values
    want_fields = {"子機組": "HRSG11", "製造商": "Endress+Hauser", "協定": "HART 7", "位號指派時間(台灣)": "2025-04-11 09:09:56.496"}
    for sec in card["sections"]:
        for fd in sec["fields"]:
            if fd["label"] in want_fields:
                got = rows03[i3][fd["col"]]
                if got != want_fields[fd["label"]]:
                    problems.append("02 field %s -> 03[%s] = %r" % (fd["label"], fd["col"], got))
    nfields = sum(len(s["fields"]) for s in card["sections"])
    if nfields != 60:
        problems.append("02 card has %d fields (expected 60)" % nfields)
    # charts
    chart_ids = [c["id"] for s in ("01", "16") for c in grid_info.get(s, {}).get("charts", [])]
    if chart_ids != ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]:
        problems.append("charts = %r" % chart_ids)
    return problems


if __name__ == "__main__":
    sys.exit(main())
