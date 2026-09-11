# -*- coding: utf-8 -*-
"""mode = "table" sheet builder (CONTRACT.md v2)."""
import collections
import datetime as dt

from amsx_common import table_col_px, style_string, CHUNK_TARGET_ROWS
from .formula import Formula, Link, XlError
from .values import json_value, plain_value
from .cf import evaluate_cf
from . import config

EMPTY = (False, False, False, None, None)  # (b, i, u, bg, fc)
LINK_BLUE = "#0563C1"
MONO_FONTS = ("consolas", "courier new", "courier", "lucida console", "cascadia mono", "cascadia code", "menlo")


def _norm_fc(c):
    return None if c in (None, "#000000") else c


def static_style(xf, is_link):
    f = xf.font
    fc = _norm_fc(f.color)
    u = bool(f.u)
    if is_link:
        if fc == LINK_BLUE:
            fc = None
        u = False
    bg = xf.fill
    if bg == "#FFFFFF":
        bg = None
    return (bool(f.b), bool(f.i), u, bg, fc)


def apply_overlay(st, ov):
    if not ov:
        return st
    b, i, u, bg, fc = st
    if "b" in ov:
        b = bool(ov["b"])
    if "i" in ov:
        i = bool(ov["i"])
    if "u" in ov:
        u = bool(ov["u"])
    if "bg" in ov:
        bg = ov["bg"]
    elif "bg_white" in ov:
        bg = None
    if "fc" in ov:
        fc = _norm_fc(ov["fc"])
    return (b, i, u, bg, fc)


def merge_style(base, over):
    """Property-wise merge (flags OR, colours of ``over`` win)."""
    return (base[0] or over[0], base[1] or over[1], base[2] or over[2],
            over[3] if over[3] else base[3], over[4] if over[4] else base[4])


class StyleTable(object):
    def __init__(self):
        self.list = []
        self.idx = {}

    def get(self, t):
        s = style_string(*t)
        i = self.idx.get(s)
        if i is None:
            i = self.idx[s] = len(self.list)
            self.list.append(s)
        return i


def split_notes(s):
    if not isinstance(s, str):
        return []
    return [p for p in s.split("｜")]


def _value_class(v):
    if v is None:
        return None
    if isinstance(v, dict):
        if "l" in v or "u" in v:
            return "link_num" if isinstance(v.get("t"), (int, float)) and not isinstance(v.get("t"), bool) else "link"
        return "num" if isinstance(v.get("v"), (int, float)) else "text"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "num"
    return "text"


def build_table(ctx, sheet_name):
    """Returns (json_obj_or_parts, info) for a table-mode sheet."""
    ev, wb, resolver = ctx.ev, ctx.wb, ctx.resolver
    sh = wb.load_sheet(sheet_name)
    sid = sh.id
    styles_x = wb.styles.xfs
    warnings = ctx.warnings
    if sh.autofilter is None:
        raise ValueError("%s: table sheet without autofilter" % sheet_name)
    hr, c1, last_row, last_col = sh.autofilter
    first = hr + 1
    drop = config.DROP_COLS.get(sid, {})
    excel_cols = [c for c in range(1, last_col + 1) if (c - 1) not in drop]
    ncols = len(excel_cols)
    mm = sh.merge_map()

    # ---- header area -----------------------------------------------------
    consumed = set()
    title = None
    notes = []
    header_cells = []
    stbl = StyleTable()
    r1_cells = [(c, sh.raw(1, c)) for c in range(1, sh.max_col + 1)]
    texts = [(c, v) for c, v in r1_cells if isinstance(v, str) and mm.get((1, c), ("anchor",))[0] != "covered"]
    if texts:
        title = texts[0][1]
        consumed.add((1, texts[0][0]))
    if len(texts) > 1:
        notes = split_notes(texts[1][1])
        consumed.add((1, texts[1][0]))
    # bands (row 2)
    bands = []
    band_row = 2 if hr >= 3 else None
    if band_row:
        for c in range(1, last_col + 1):
            m = mm.get((band_row, c))
            if m and m[0] == "covered":
                continue
            v = sh.raw(band_row, c)
            if v is None or (isinstance(v, str) and v.strip() == ""):
                continue
            span = m[2] if m else 1
            c_end = c + span - 1
            cols_in = [i for i, ec in enumerate(excel_cols) if c <= ec <= c_end]
            if not cols_in:
                continue
            xf = sh.xf(band_row, c)
            bands.append({"label": plain_value(v), "from": cols_in[0], "to": cols_in[-1],
                          "bg": xf.fill, "fc": xf.font.color})
            consumed.add((band_row, c))
    note_row = hr - 1 if hr >= 3 else None
    # header cells: everything else in rows 1..hr-1 inside the table columns
    for r in range(1, hr):
        for c in range(1, last_col + 1):
            if (r, c) in consumed:
                continue
            if r == note_row:
                continue
            m = mm.get((r, c))
            if m and m[0] == "covered":
                continue
            raw = sh.raw(r, c)
            if raw is None:
                continue
            val = ev.value(sheet_name, r, c) if isinstance(raw, Formula) else raw
            nf = sh.number_format(r, c)
            hc = {"r": r, "c": c, "v": json_value(val, nf, resolver, sid, "%s%d" % (_cl(c), r), warnings)}
            if isinstance(hc["v"], str) and isinstance(raw, Formula) and hc["v"] == "":
                hc["v"] = None
            xf = sh.xf(r, c)
            st = static_style(xf, isinstance(val, Link))
            if st != EMPTY:
                hc["s"] = stbl.get(st)
            if isinstance(val, (int, float)) and not isinstance(val, bool) and nf not in ("General", "@"):
                hc["f"] = nf
            if m and m[0] == "anchor":
                hc["cs"] = m[2]
                hc["rs"] = m[1]
            header_cells.append(hc)

    # ---- columns -----------------------------------------------------------
    columns = []
    for i, c in enumerate(excel_cols):
        lab = sh.raw(hr, c)
        note = sh.raw(note_row, c) if note_row else None
        hxf = sh.xf(hr, c)
        col = {"label": plain_value(lab) if lab is not None else None, "fmt": None, "type": "text",
               "w": table_col_px(sh.col_width(c)), "align": "left", "bg": None}
        if isinstance(note, str) and note.strip():
            col["note"] = note
        if hxf.fill:
            col["hbg"] = hxf.fill
        if _norm_fc(hxf.font.color):
            col["hfc"] = hxf.font.color
        if sh.col_hidden(c):
            col["hidden"] = True
        columns.append(col)

    # ---- data rows -----------------------------------------------------------
    rows = []
    E = []  # effective styles per row (list of tuples) or None if no styling
    cf = evaluate_cf(ev, sheet_name, (first, 1, last_row, last_col),
                     skip=(lambda rule, ranges: sid in config.DROP_COLS and _zebra_rule(rule, drop)))
    ctx.cf_hits[sid] = [(p, t, [_rng_s(x) for x in rg], h) for p, t, rg, h in cf.rule_hits]
    ov_cells = cf.cells
    style_cache = {}
    col_nf = [collections.Counter() for _ in excel_cols]
    col_cls = [collections.Counter() for _ in excel_cols]
    col_ha = [collections.Counter() for _ in excel_cols]
    col_gcls = [collections.Counter() for _ in excel_cols]
    col_wrap = [collections.Counter() for _ in excel_cols]
    col_mono = [collections.Counter() for _ in excel_cols]
    col_nonempty = [0] * ncols
    bars = []
    any_style = bool(ov_cells)
    for r in range(first, last_row + 1):
        rv = sh.rows.get(r) or []
        rs = sh.srows.get(r) or []
        out = [None] * ncols
        est = [EMPTY] * ncols
        for i, c in enumerate(excel_cols):
            raw = rv[c - 1] if c <= len(rv) else None
            s_id = rs[c - 1] if c <= len(rs) else 0
            xf = styles_x[s_id]
            nf = xf.numfmt
            if isinstance(raw, Formula):
                val = ev.value(sheet_name, r, c)
                v = json_value(val, nf, resolver, sid, "%s%d" % (_cl(c), r), warnings)
                if v == "":
                    v = None
                is_link = isinstance(val, Link)
            else:
                val = raw
                is_link = False
                if raw is None:
                    v = None
                elif isinstance(raw, (dt.datetime, dt.date, dt.time)):
                    v = plain_value(raw, nf)
                else:
                    v = raw
            out[i] = v
            if v is not None:
                col_nonempty[i] += 1
                cls = _value_class(v)
                if isinstance(val, (dt.datetime, dt.date)):
                    cls = "date"
                col_cls[i][cls] += 1
                if cls in ("num", "date", "link_num"):
                    col_nf[i][nf] += 1
                col_ha[i][xf.ha or ""] += 1
                if (xf.ha or "general") == "general":
                    col_gcls[i][cls] += 1
                col_wrap[i][xf.wrap] += 1
                fn = (xf.font.name or "").lower()
                col_mono[i][fn in MONO_FONTS] += 1
            # style
            if s_id or (r, c) in ov_cells:
                key = (s_id, is_link)
                st = style_cache.get(key)
                if st is None:
                    st = style_cache[key] = static_style(xf, is_link)
                ov = ov_cells.get((r, c))
                if ov:
                    st = apply_overlay(st, ov)
                    b = ov.get("bar")
                    if b is not None:
                        bars.append([r - first, i, b[0], b[1]])
                if st is not EMPTY and st != EMPTY:
                    est[i] = st
                    any_style = True
        rows.append(out)
        E.append(est)

    nrows = len(rows)
    # column type / fmt / align
    for i, col in enumerate(columns):
        cls = col_cls[i]
        total = sum(cls.values())
        typ = "text"
        if total:
            top, n = cls.most_common(1)[0]
            links = cls.get("link", 0) + cls.get("link_num", 0)
            if cls.get("link", 0) >= total * 0.5:
                typ = "link"
            elif (cls.get("num", 0) + cls.get("link_num", 0)) >= total * 0.95:
                typ = "num"
            elif cls.get("date", 0) >= total * 0.95:
                typ = "date"
            elif cls.get("bool", 0) == total:
                typ = "bool"
        col["type"] = typ
        if col_nf[i]:
            nf = col_nf[i].most_common(1)[0][0]
            col["fmt"] = None if nf in ("General", "@") else nf
        ha = col_ha[i].most_common(1)[0][0] if col_ha[i] else ""
        if ha in ("left", "center", "right", "justify"):
            col["align"] = ha
        elif ha in ("centerContinuous", "distributed"):
            col["align"] = "center"
        elif ha == "fill":
            col["align"] = "left"
        else:
            # Excel General aligns per value: numbers/dates right, booleans centre, text (and text-label
            # links) left.  Pick the column setting that puts the most cells on Excel's side; align=None
            # lets the page apply that per-value rule itself (dates are strings in JSON, so they need 'right').
            g = col_gcls[i]
            score = [("left", g["text"] + g["link"]), ("right", g["num"] + g["date"] + g["link_num"]),
                     ("center", g["bool"]), (None, g["num"] + g["link_num"] + g["bool"] + g["text"] + g["link"])]
            best = max(s for _, s in score)
            col["align"] = next(k for k, s in score if s == best) if best else ("right" if typ == "num" else "left")
        if col_wrap[i] and col_wrap[i].get(True, 0) > col_nonempty[i] / 2.0:
            col["wrap"] = True
        if col_mono[i] and col_mono[i].get(True, 0) > col_nonempty[i] / 2.0:
            col["mono"] = True
    # per-cell number formats that differ from the column fmt
    for ri, r in enumerate(range(first, last_row + 1)):
        rs = sh.srows.get(r) or []
        row = rows[ri]
        for i, c in enumerate(excel_cols):
            v = row[i]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                s_id = rs[c - 1] if c <= len(rs) else 0
                nf = styles_x[s_id].numfmt
                cf_ = columns[i]["fmt"]
                if nf not in ("General", "@") and nf != cf_:
                    row[i] = {"v": v, "f": nf}
                elif nf in ("General", "@") and cf_ is not None:
                    row[i] = {"v": v, "f": "General"}
            elif isinstance(v, dict) and "l" in v and isinstance(v.get("t"), (int, float)):
                s_id = rs[c - 1] if c <= len(rs) else 0
                nf = styles_x[s_id].numfmt
                if nf not in ("General", "@") and nf != columns[i]["fmt"]:
                    v["f"] = nf

    # ---- style encoding ----------------------------------------------------
    row_styles, cell_styles = [], []
    if any_style:
        row_styles, cell_styles = _encode_styles(E, rows, columns, stbl)

    # ---- extras -------------------------------------------------------------
    ui = {"default_sort": None, "facets": [], "search_cols": None}
    ucfg = dict(config.TABLE_UI.get(sid, {}))
    for k, v in ucfg.items():
        ui[k] = v
    if sid == "15":
        sc = ucfg.get("summary_col")
        ui["summary_rows"] = [ri for ri, row in enumerate(rows) if row[sc] in ucfg.get("summary_values", [])]
    freeze = 0
    if sh.pane and sh.pane.get("x"):
        freeze = len([c for c in excel_cols if c <= sh.pane["x"]])
    obj = {"id": sid, "name": sheet_name, "mode": "table", "title": title, "notes": notes,
           "header_cells": header_cells, "bands": bands, "columns": columns, "freeze_cols": freeze,
           "rows": rows, "styles": stbl.list, "cell_styles": cell_styles, "row_styles": row_styles}
    if bars:
        obj["bars"] = bars
    obj["ui"] = ui
    # data validations (informational: list choices of input columns)
    dvs = _data_validations(sh, excel_cols, first)
    if dvs:
        obj["validations"] = dvs
    # sub-grid (summary / side blocks outside the autofilter table)
    sub = _subgrid(ctx, sh, last_row, last_col, mm)
    if sub is not None:
        obj["subgrid"], obj["subgrid_pos"] = sub
    info = {"rows": nrows, "cols": ncols, "first": first, "last": last_row, "excel_cols": excel_cols,
            "dropped": {(_cl(c + 1)): why for c, why in drop.items()}}
    return obj, info


def _zebra_rule(rule, drop):
    """True for the device-parity zebra rule whose helper column is dropped."""
    if rule["type"] != "expression" or not rule.get("formulas"):
        return False
    f = rule["formulas"][0].replace("$", "")
    for c in drop:
        if f.startswith(_cl(c + 1)):
            return True
    return False


def _rng_s(rg):
    r1, c1, r2, c2 = rg
    return "%s%d:%s%d" % (_cl(c1), r1, _cl(c2), r2)


def _cl(c):
    from openpyxl.utils.cell import get_column_letter
    return get_column_letter(c)


def _lacking(e, s, empty):
    """Properties set in layer ``s`` that the effective style ``e`` does not have.

    Renderers may layer column -> row -> cell property by property, where a
    layer can only *set* a property (flag on / colour), never unset it.  So a
    row / column layer must never carry a property that some cell of it lacks,
    otherwise no cell_style can take it back (e.g. 12 column A sits outside the
    grey-font CF range B:AJ of its row).  Fonts are invisible on empty cells.
    """
    out = set()
    if s[3] and not e[3]:
        out.add(3)
    if not empty:
        for k in (0, 1, 2, 4):
            if s[k] and not e[k]:
                out.add(k)
    return out


def _drop_props(t, props):
    if not props:
        return t
    t = list(t)
    for k in props:
        t[k] = None if k >= 3 else False
    t = tuple(t)
    return None if t == EMPTY else t


def _encode_styles(E, rows, columns, stbl):
    nrows = len(E)
    ncols = len(columns)
    # 1. row styles: most common tuple of the row covering >= half the columns,
    #    reduced to the properties every cell of the row really has
    R = [None] * nrows
    for ri in range(nrows):
        cnt = collections.Counter(E[ri])
        t, n = cnt.most_common(1)[0]
        if t != EMPTY and n * 2 >= ncols:
            bad = set()
            for ci in range(ncols):
                bad |= _lacking(E[ri][ci], t, rows[ri][ci] is None)
            R[ri] = _drop_props(t, bad)
    # 2. column-level props: uniform over rows without a row style
    D = []
    for ci in range(ncols):
        bgs = set()
        fonts = {"b": set(), "i": set(), "u": set(), "fc": set()}
        seen_font = False
        for ri in range(nrows):
            if R[ri] is not None:
                continue
            t = E[ri][ci]
            bgs.add(t[3])
            if rows[ri][ci] is not None:
                seen_font = True
                fonts["b"].add(t[0])
                fonts["i"].add(t[1])
                fonts["u"].add(t[2])
                fonts["fc"].add(t[4])
        one = lambda s: next(iter(s)) if len(s) == 1 else None
        bg = one(bgs) if bgs else None
        b = bool(one(fonts["b"])) if seen_font else False
        it = bool(one(fonts["i"])) if seen_font else False
        u = bool(one(fonts["u"])) if seen_font else False
        fc = one(fonts["fc"]) if seen_font else None
        d = (b, it, u, bg, fc)
        # the column layer also sits under row-styled rows: drop what any cell lacks
        bad = set()
        for ri in range(nrows):
            bad |= _lacking(E[ri][ci], d, rows[ri][ci] is None)
        d = _drop_props(d, bad) or EMPTY
        b, it, u, bg, fc = d
        D.append(d)
        col = columns[ci]
        if b:
            col["bold"] = True
        if it:
            col["italic"] = True
        if u:
            col["underline"] = True
        if bg:
            col["bg"] = bg
        if fc:
            col["fc"] = fc
    # 3. emission
    row_styles, cell_styles = [], []
    for ri in range(nrows):
        r_st = R[ri]
        if r_st is not None:
            row_styles.append([ri, stbl.get(r_st)])
        est = E[ri]
        row = rows[ri]
        for ci in range(ncols):
            e = est[ci]
            d = D[ci]
            empty = row[ci] is None
            if r_st is None:
                if empty:
                    diff = e[3] != d[3]
                else:
                    diff = e != d
            else:
                m = merge_style(d, r_st)
                if empty:
                    diff = e[3] != r_st[3] or e[3] != m[3]
                else:
                    diff = e != r_st or e != m
            if diff:
                if empty:
                    # fonts don't show on empty cells: keep the reference fonts
                    ref = r_st if r_st is not None else d
                    e = (ref[0], ref[1], ref[2], e[3], ref[4])
                cell_styles.append([ri, ci, stbl.get(e)])
    return row_styles, cell_styles


def _data_validations(sh, excel_cols, first):
    from .xlsx import parse_range
    out = []
    for d in sh.dv:
        for part in (d.get("sqref") or "").split():
            r1, c1, r2, c2 = parse_range(part)
            if r2 < first:
                continue
            cols = [i for i, c in enumerate(excel_cols) if c1 <= c <= c2]
            if not cols:
                continue
            item = {"cols": cols, "type": d.get("type")}
            f1 = d.get("formula1")
            if d.get("type") == "list" and f1:
                if f1.startswith('"'):
                    item["options"] = f1.strip('"').split(",")
                else:
                    item["source"] = f1
            elif f1:
                item["formula"] = f1
                if d.get("operator"):
                    item["operator"] = d.get("operator")
            if d.get("prompt"):
                item["prompt"] = d.get("prompt")
            out.append(item)
    return out


def _subgrid(ctx, sh, last_row, last_col, mm):
    """Cells outside the autofilter table (e.g. 09 方法小計, 19 側表)."""
    boxes = []
    for r, vals in sh.rows.items():
        for c, v in enumerate(vals, 1):
            if r <= last_row and c <= last_col:
                continue
            m = mm.get((r, c))
            if m and m[0] == "covered":
                a_r, a_c = m[1], m[2]
                if a_r <= last_row and a_c <= last_col:
                    continue  # part of a merge anchored inside the table (e.g. the I1 notes)
            if v is None or (isinstance(v, str) and v.strip() == ""):
                xf = sh.xf(r, c)
                if not (v is None and xf.fill and xf.fill != "#FFFFFF"):
                    continue  # blank / whitespace-only spacer (e.g. 19 N2 white-on-white)
            boxes.append((r, c))
    if not boxes:
        return None
    r1 = min(b[0] for b in boxes)
    r2 = max(b[0] for b in boxes)
    c1 = min(b[1] for b in boxes)
    c2 = max(b[1] for b in boxes)
    from .grid import build_grid_region
    g = build_grid_region(ctx, sh.name, (r1, c1, r2, c2), relative=True)
    pos = "below" if r1 > last_row else "above"
    return g, pos


def chunk_parts(obj, alias_col, target=CHUNK_TARGET_ROWS):
    """Split a table object into device-aligned parts (never split an alias block)."""
    rows = obj["rows"]
    bounds = []  # start index of each block
    prev = object()
    for i, row in enumerate(rows):
        a = row[alias_col]
        if a != prev:
            bounds.append(i)
            prev = a
    bounds.append(len(rows))
    parts = []
    start = 0
    cur = 0
    for bi in range(len(bounds) - 1):
        b0, b1 = bounds[bi], bounds[bi + 1]
        size = b1 - b0
        if cur > 0 and cur + size > target:
            parts.append((start, b0))
            start = b0
            cur = 0
        cur += size
    if start < len(rows):
        parts.append((start, len(rows)))
    # blocks must be contiguous: check no alias appears in two blocks
    seen = set()
    for bi in range(len(bounds) - 1):
        a = rows[bounds[bi]][alias_col]
        if a in seen:
            raise ValueError("%s: alias %r appears in two non-contiguous blocks" % (obj["id"], a))
        seen.add(a)
    out = []
    n = len(parts)
    for k, (s, e) in enumerate(parts):
        p = dict(obj)
        p["rows"] = rows[s:e]
        p["cell_styles"] = [[r - s, c, st] for r, c, st in obj.get("cell_styles", []) if s <= r < e]
        p["row_styles"] = [[r - s, st] for r, st in obj.get("row_styles", []) if s <= r < e]
        if "bars" in obj:
            p["bars"] = [[r - s, c, pp, col] for r, c, pp, col in obj["bars"] if s <= r < e]
        p["part"] = {"index": k, "of": n, "row_offset": s, "rows": e - s,
                     "first_alias": rows[s][alias_col], "last_alias": rows[e - 1][alias_col]}
        out.append(p)
    return out, [s for s, e in parts], len(bounds) - 1
