# -*- coding: utf-8 -*-
"""02_設備查詢卡 -> declarative card JSON (specs/02.md).

The card's 136 formulas are NOT evaluated into static values (they depend on
the input cell C3).  Instead they are parsed to derive the field -> 03
column mapping, the lookup chain, messages, quick links, the recent-change
recipe and the CF rules.  ``link_index`` precomputes per-alias link targets
and counts so the front-end need not load 06/07/08/10/11/12 to show counts.
The derivation is cross-checked by evaluating the real formulas for the
default query with the formula engine (see ``verify_default``).
"""
import re
import collections

from openpyxl.utils.cell import get_column_letter

from .formula import Formula, Link, XlError
from .xlsx import col_index, parse_range
from .values import plain_value

_STR = re.compile(r'"((?:[^"]|"")*)"')
_INDEX03 = re.compile(r"INDEX\('03_設備總表'!\$([A-Z]+):\$\1,\$J\$4\)")
_MATCH_C4 = re.compile(r"MATCH\(\$C\$4,'([^']+)'!\$([A-Z]+):\$[A-Z]+,0\)")
_COUNT_C4 = re.compile(r"COUNTIF\('([^']+)'!\$([A-Z]+):\$[A-Z]+,\$C\$4(&\"#\*\")?\)")
_INDEX_REC = re.compile(r"INDEX\('([^']+)'!\$([A-Z]+):\$[A-Z]+,MATCH\(\$C\$4&\"#\"&(\d+),'([^']+)'!\$([A-Z]+):\$[A-Z]+,0\)\)")


def _strs(f):
    return [s.replace('""', '"') for s in _STR.findall(f)]


def build_card(ctx, sheet_name):
    wb, ev = ctx.wb, ctx.ev
    sh = wb.load_sheet(sheet_name)
    mm = sh.merge_map()
    F = lambda ref: (sh.raw(*_rc(ref)).text if isinstance(sh.raw(*_rc(ref)), Formula) else None)
    V = lambda ref: sh.raw(*_rc(ref))

    title = V("B1")
    notes = [V("B2")] if isinstance(V("B2"), str) else []
    home = F("A1")
    home_link = None
    if home:
        m = re.match(r'^=HYPERLINK\("(#[^"]+)","([^"]*)"\)$', home)
        if m:
            home_link = {"t": m.group(2), "l": ctx.resolver.resolve(m.group(1), "02", "A1")}

    # ---- lookup chain (J2, J3, C4, G4, H4, J4, F3) -------------------------
    j3 = F("J3") or ""
    mj3 = re.search(r"MATCH\(\$J\$2,'([^']+)'!\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+),0\)\+(\d+)", j3)
    idx_sheet = mj3.group(1)[:2]
    key_col = col_index(mj3.group(2)) - 1
    mc4 = re.search(r"INDEX\('([^']+)'!\$([A-Z]+):\$[A-Z]+,\$J\$3\)", F("C4") or "")
    alias_col = col_index(mc4.group(2)) - 1
    mg4 = re.search(r"INDEX\('([^']+)'!\$([A-Z]+):\$[A-Z]+,\$J\$3\)", F("G4") or "")
    count_col = col_index(mg4.group(2)) - 1
    mj4 = re.search(r"MATCH\(\$C\$4,'([^']+)'!\$([A-Z]+):\$[A-Z]+,0\)", F("J4") or "")
    target_sheet = mj4.group(1)[:2]
    target_alias_col = col_index(mj4.group(2)) - 1
    f3 = F("F3") or ""
    f3_idx = re.findall(r"INDEX\('([^']+)'!\$([A-Z]+):\$[A-Z]+,\$J\$(\d)\)", f3)
    src_col = next(col_index(c) - 1 for s, c, j in f3_idx if j == "3" and col_index(c) - 1 != key_col)
    tag_col = next(col_index(c) - 1 for s, c, j in f3_idx if j == "4")
    s3 = _strs(f3)
    # literal order in F3: "", 請輸入位號…, "", 查無此字串…, 來源：, ［鍵 , ］, "", （測試…）, " → 目前位號 "
    nonempty = [x for x in s3 if x != ""]
    msg = {"empty": nonempty[0], "notfound": nonempty[1],
           "found": nonempty[2] + "{src}" + nonempty[3] + "{key}" + nonempty[4],
           "no_device": nonempty[5], "device": nonempty[6] + "{tag}"}
    h4 = [x for x in _strs(F("H4") or "") if x]
    if h4:
        msg["multi"] = h4[0]
    j2 = F("J2") or ""
    normalize = "remove '=' ; collapse spaces ; trim ; upper" if ("TRIM" in j2 and "UPPER" in j2) else j2

    prompt = None
    for d in sh.dv:
        if "C3" in (d.get("sqref") or "").split():
            prompt = d.get("prompt")
    input_label = V("B3")
    default_query = V("C3")

    # ---- sections & fields ---------------------------------------------------
    headings = []  # (row, label)
    for r in range(1, sh.max_row + 1):
        v = sh.raw(r, 2)
        m = mm.get((r, 2))
        if isinstance(v, str) and m and m[0] == "anchor" and m[2] >= 6 and r > 2:
            headings.append((r, v))
    field_rows = {}
    sections = []
    cell_field = {}
    link_head = rec_head = None
    for hi, (hr, hlabel) in enumerate(headings):
        nxt = headings[hi + 1][0] if hi + 1 < len(headings) else sh.max_row + 1
        fields = []
        is_field_section = False
        for r in range(hr + 1, nxt):
            for c in (3, 6):  # value cells C and F
                f = F("%s%d" % (get_column_letter(c), r))
                if not f or "'03_設備總表'" not in f or "$J$4" not in f or "HYPERLINK" in f:
                    continue
                cols = [col_index(x) - 1 for x in _INDEX03.findall(f)]
                cols = list(dict.fromkeys(cols))
                if not cols:
                    continue
                is_field_section = True
                lab = sh.raw(r, c - 1)
                ref = "%s%d" % (get_column_letter(c), r)
                fd = {"label": lab, "col": cols[0] if len(cols) == 1 else cols, "join": None,
                      "blank_if_empty": True, "cell": ref}
                if len(cols) > 1:
                    fd["join"] = " "
                    fd["trim"] = "TRIM(" in f
                if 'IF(INDEX(' in f:
                    fd["raw"] = True
                    fd["fmt"] = sh.number_format(r, c)
                m = mm.get((r, c))
                if m and m[0] == "anchor":
                    ref2 = "%s%d:%s%d" % (get_column_letter(c), r, get_column_letter(c + m[2] - 1), r + m[1] - 1)
                    fd["cell"] = ref2
                    if c == 3 and c + m[2] - 1 >= 8:
                        fd["span"] = 2
                fields.append(fd)
                cell_field[ref] = fd
        if is_field_section:
            sections.append({"label": hlabel, "fields": fields})
        else:
            body = [F("%s%d" % (get_column_letter(c), r)) or "" for r in range(hr + 1, nxt) for c in range(2, 9)]
            if any("HYPERLINK" in b for b in body) and link_head is None and not any("#\"&" in b for b in body if "HYPERLINK" not in b):
                link_head = (hr, hlabel, nxt)
            elif any('"#"&' in b for b in body):
                rec_head = (hr, hlabel, nxt)

    # ---- quick links -------------------------------------------------------------
    links = []
    if link_head:
        hr, hlabel, nxt = link_head
        for r in range(hr + 1, nxt):
            for c in range(2, 9):
                f = F("%s%d" % (get_column_letter(c), r))
                if not f or "HYPERLINK" not in f:
                    continue
                lits = [x for x in _strs(f) if x]
                if "'03_設備總表'!A\"&$J$4" in f.replace(" ", ""):
                    links.append({"label": lits[-1], "sheet": "03", "self": True, "cell": "%s%d" % (get_column_letter(c), r)})
                    continue
                pm = re.findall(r"INDEX\('03_設備總表'!\$([A-Z]+):\$[A-Z]+,\$J\$4\)", f)
                if pm and "MATCH($C$4" not in f:
                    cols = list(dict.fromkeys(col_index(x) - 1 for x in pm))
                    # order in formula: DF (sheet) test, DF (sheet name), DG (row), DH (count)
                    sheet_col, row_col, count_col_p = cols[0], cols[1], cols[2]
                    none_lab = next(x for x in lits if "（無）" in x)
                    pre = next(x for x in lits if x.startswith("→") and "（無）" not in x)
                    suf = lits[-1] if lits[-1] != pre else ""
                    links.append({"label": pre.strip(), "param": {"sheet_col": sheet_col, "row_col": row_col, "count_col": count_col_p},
                                  "none": none_lab, "fmt": pre + "{n}" + suf, "cell": "%s%d" % (get_column_letter(c), r)})
                    continue
                mm_ = _MATCH_C4.search(f)
                cm = _COUNT_C4.search(f)
                if not mm_ or not cm:
                    ctx.warnings.append("02 %s%d: unrecognised quick-link formula" % (get_column_letter(c), r))
                    continue
                none_lab = next(x for x in lits if "（無）" in x)
                pre = next(x for x in lits if x.startswith("→") and "（無）" not in x)
                suf = [x for x in lits if x not in (pre, none_lab) and not x.startswith("#")]
                suf = suf[-1] if suf else ""
                links.append({"label": pre.strip(), "sheet": mm_.group(1)[:2], "match_col": col_index(mm_.group(2)) - 1,
                              "count_mode": "prefix#" if cm.group(3) else "eq", "count_col": col_index(cm.group(2)) - 1,
                              "fmt": pre + "{n}" + suf, "none": none_lab, "cell": "%s%d" % (get_column_letter(c), r)})
    links_title = link_head[1] if link_head else None

    # ---- recent changes ---------------------------------------------------------
    recent = None
    if rec_head:
        hr, hlabel, nxt = rec_head
        hdr_row = hr + 1
        rec_rows = [r for r in range(hdr_row + 1, nxt) if any(F("%s%d" % (get_column_letter(c), r)) for c in range(2, 9))]
        cols_spec = []
        rsheet = key_col_r = None
        r0 = rec_rows[0]
        for c in range(2, 9):
            m = mm.get((r0, c))
            if m and m[0] == "covered":
                continue
            f = F("%s%d" % (get_column_letter(c), r0))
            if not f:
                continue
            parts = _INDEX_REC.findall(f)
            if not parts:
                continue
            lab = sh.raw(hdr_row, c)
            rsheet = parts[0][0][:2]
            key_col_r = col_index(parts[0][4]) - 1
            cs = [col_index(p[1]) - 1 for p in parts]
            d = {"label": lab}
            if len(cs) == 1:
                d["col"] = cs[0]
            else:
                d["cols"] = cs
                joins = [x for x in _strs(f) if x and x != "#"]
                d["join"] = joins[0] if joins else " "
            nf = sh.number_format(r0, c)
            if nf not in ("General", "@"):
                d["fmt"] = nf
            cols_spec.append(d)
        recent = {"title": hlabel, "sheet": rsheet, "key_col": key_col_r, "k_max": len(rec_rows), "columns": cols_spec}

    # ---- conditional-format rules ----------------------------------------------
    rules = []
    count_cell = "G4"
    for ranges, rl in sh.cf:
        targets = []
        for (r1, c1, r2, c2) in ranges:
            ref = "%s%d" % (get_column_letter(c1), r1)
            fd = cell_field.get(ref) or next((x for k, x in cell_field.items() if x["cell"].startswith(ref + ":")), None)
            if fd is not None:
                targets.append(fd["col"])
            elif ref == count_cell:
                targets.append("count")
        for rule in rl:
            when = _translate_rule(rule["formulas"][0] if rule.get("formulas") else "", cell_field, count_cell)
            dxf = wb.styles.dxfs[rule["dxf"]] if rule.get("dxf") is not None else {}
            style = {}
            if dxf.get("b"):
                style["b"] = 1
            if dxf.get("i"):
                style["i"] = 1
            if dxf.get("fc"):
                style["fc"] = dxf["fc"]
            if dxf.get("bg"):
                style["bg"] = dxf["bg"]
            if when is None:
                ctx.warnings.append("02 CF rule not translated: %s" % rule.get("formulas"))
                continue
            rules.append({"when": when, "targets": targets, "style": style, "excel": rule["formulas"][0]})

    card = {"id": "02", "name": sheet_name, "mode": "card", "title": title, "notes": notes,
            "default_query": default_query,
            "input": {"label": input_label, "prompt": prompt,
                      "suggest": {"sheet": idx_sheet, "col": key_col, "hint_cols": [src_col, alias_col]}},
            "lookup": {"index_sheet": idx_sheet, "key_col": key_col, "src_col": src_col, "alias_col": alias_col,
                       "count_col": count_col, "target_sheet": target_sheet, "target_alias_col": target_alias_col,
                       "target_tag_col": tag_col, "normalize": normalize, "msg": msg,
                       "labels": {"alias": V("B4"), "count": V("F4")}},
            "sections": sections, "links": links, "links_title": links_title,
            "recent_changes": recent, "rules": rules, "home_link": home_link}
    return card


def _rc(ref):
    m = re.match(r"^([A-Z]+)(\d+)$", ref)
    return int(m.group(2)), col_index(m.group(1))


def _translate_rule(f, cell_field, count_cell):
    """Translate the 4 card CF formulas into the declarative JSON form."""
    f = f.lstrip("=")

    def cond(expr):
        expr = expr.strip()
        m = re.match(r'^\$([A-Z]+)\$(\d+)="(.*)"$', expr)
        if m:
            return _fcol(cell_field, m.group(1) + m.group(2), {"eq": m.group(3)})
        m = re.match(r'^\$([A-Z]+)\$(\d+)<>""$', expr)
        if m:
            return _fcol(cell_field, m.group(1) + m.group(2), {"nonempty": True})
        m = re.match(r'^LEFT\(\$([A-Z]+)\$(\d+),(\d+)\)="(.*)"$', expr)
        if m:
            return _fcol(cell_field, m.group(1) + m.group(2), {"startsWith": m.group(4)})
        m = re.match(r'^AND\(ISNUMBER\(\$([A-Z]+)\$(\d+)\),\$\1\$\2>(\d+)\)$', expr)
        if m and m.group(1) + m.group(2) == count_cell:
            return {"count_gt": int(m.group(3))}
        return None
    m = re.match(r"^OR\((.*)\)$", f)
    if m:
        parts = _split_args(m.group(1))
        cs = [cond(p) for p in parts]
        return None if any(c is None for c in cs) else {"any": cs}
    return cond(f)


def _fcol(cell_field, ref, d):
    fd = cell_field.get(ref) or next((x for k, x in cell_field.items() if x["cell"].startswith(ref + ":")), None)
    if fd is None:
        return None
    out = {"col": fd["col"]}
    out.update(d)
    return out


def _split_args(s):
    out, depth, cur, q = [], 0, "", False
    for ch in s:
        if ch == '"':
            q = not q
        if not q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append(cur)
                cur = ""
                continue
        cur += ch
    out.append(cur)
    return out


def build_link_index(ctx, card, sheet_rows):
    """alias -> {sheet: [r0, n]} for every quick link with a match column.

    sheet_rows: {sid: (rows_list, data_first_row)} of the emitted tables.
    r0 = first data row whose match column equals the alias (MATCH, case-insensitive);
    n  = COUNTIF count (exact or 'alias#*' prefix).  Aliases without a match are omitted.
    """
    target = card["lookup"]["target_sheet"]
    alias_col = card["lookup"]["target_alias_col"]
    aliases = [row[alias_col] for row in sheet_rows[target][0] if isinstance(row[alias_col], str)]
    idx = {a: {} for a in aliases}
    for ln in card["links"]:
        if "match_col" not in ln:
            continue
        sid = ln["sheet"]
        rows = sheet_rows[sid][0]
        mc, cc = ln["match_col"], ln["count_col"]
        first = {}
        cnt = collections.Counter()
        for i, row in enumerate(rows):
            v = row[mc]
            if isinstance(v, dict):
                v = v.get("t")
            if isinstance(v, str):
                first.setdefault(v.upper(), i)
            w = row[cc]
            if isinstance(w, dict):
                w = w.get("t")
            if isinstance(w, str):
                if ln["count_mode"] == "prefix#":
                    if "#" in w:
                        cnt[w.split("#", 1)[0].upper()] += 1
                else:
                    cnt[w.upper()] += 1
        for a in aliases:
            r0 = first.get(a.upper())
            if r0 is not None:
                idx[a][sid] = [r0, cnt.get(a.upper(), 0)]
    return {a: v for a, v in idx.items() if v}


def verify_default(ctx, card, query=None):
    """Evaluate the real 02 formulas with C3 := query and compare them with the
    declarative card applied to the extracted tables.  Returns list of problems."""
    ev = ctx.ev
    sh = ctx.wb.load_sheet(card["name"])
    q = query if query is not None else card["default_query"]
    ev.overrides[(card["name"], 3, 3)] = q
    ev.cache = {k: v for k, v in ev.cache.items() if k[0] != card["name"]}
    out = {}
    try:
        for r, vals in sh.rows.items():
            for c, v in enumerate(vals, 1):
                if isinstance(v, Formula):
                    res = ev.value(card["name"], r, c)
                    out["%s%d" % (get_column_letter(c), r)] = res
    finally:
        del ev.overrides[(card["name"], 3, 3)]
        ev.cache = {k: v for k, v in ev.cache.items() if k[0] != card["name"]}
    return out
