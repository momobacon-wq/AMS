# -*- coding: utf-8 -*-
"""Conditional-formatting engine (Excel semantics) used to materialise CF
results into static styles.

Supported rule types: expression, cellIs, containsText, notContainsText,
beginsWith, endsWith, containsBlanks, notContainsBlanks, containsErrors,
notContainsErrors, duplicateValues, uniqueValues, colorScale, dataBar.

Precedence: rules are processed by ascending ``priority``; for every cell and
every property (b, i, u, fc, bg, bd) the first TRUE rule that defines the
property wins; a TRUE rule with stopIfTrue stops lower-priority rules for that
cell.  Colour scales produce ``bg``; data bars produce ``bar = (p, colour)``.
"""
import datetime as dt

from .formula import parse, _compile, has_relative_col, XlError, Link, to_bool, compare, is_number, to_num, Criteria

WHITE = "#FFFFFF"


def _truth(v):
    if isinstance(v, Link):
        v = v.label
    if isinstance(v, XlError) or v is None:
        return False
    if isinstance(v, str):
        u = v.upper()
        return u == "TRUE"
    try:
        return to_bool(v)
    except XlError:
        return False


def _lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(int(a[k] + (b[k] - a[k]) * t + 0.5) for k in range(3))


def percentile_inc(sorted_vals, p):
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return sorted_vals[0]
    k = (n - 1) * p
    f = int(k)
    c = min(f + 1, n - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


class CFResult(object):
    def __init__(self):
        self.cells = {}  # (r, c) -> overlay dict
        self.rule_hits = []  # (priority, type, sqref, n_true_cells)


def _cells_in(ranges, region):
    r1, c1, r2, c2 = region
    for (a1, b1, a2, b2) in ranges:
        rr1, rr2 = max(a1, r1), min(a2, r2)
        cc1, cc2 = max(b1, c1), min(b2, c2)
        if rr1 > rr2 or cc1 > cc2:
            continue
        yield rr1, cc1, rr2, cc2


def evaluate_cf(ev, sheet, region=None, skip=None):
    """Evaluate every CF rule of ``sheet`` over ``region`` (r1,c1,r2,c2).

    Returns CFResult with overlays per cell.  ``skip`` is an optional
    predicate(rule, ranges) -> bool to leave a rule out (logged by caller).
    """
    sh = ev.sheet(sheet)
    styles = sh.wb.styles
    if region is None:
        region = (1, 1, max(sh.max_row, 1), max(sh.max_col, 1))
    rules = []
    for ranges, rl in sh.cf:
        for rule in rl:
            rules.append((rule["priority"], ranges, rule))
    rules.sort(key=lambda x: x[0])
    out = CFResult()
    cells = out.cells

    def apply(r, c, props, stop):
        key = (r, c)
        ov = cells.get(key)
        if ov is None:
            ov = cells[key] = {}
        elif ov.get("_stop"):
            return
        for k, v in props.items():
            if k not in ov:
                ov[k] = v
        if stop:
            ov["_stop"] = True

    def val(r, c):
        v = ev.value(sheet, r, c)
        if isinstance(v, Link):
            v = v.label
        return v

    for prio, ranges, rule in rules:
        if skip is not None and skip(rule, ranges):
            out.rule_hits.append((prio, rule["type"], ranges, None))
            continue
        typ = rule["type"]
        dxf = styles.dxfs[rule["dxf"]] if rule.get("dxf") is not None and rule["dxf"] < len(styles.dxfs) else {}
        stop = rule.get("stop", False)
        hits = 0
        a_r, a_c = ranges[0][0], ranges[0][1]  # anchor = top-left of the first range
        if typ == "expression":
            node = parse(rule["formulas"][0])
            fn = _compile(node)
            per_row = not has_relative_col(node)
            for (r1, c1, r2, c2) in _cells_in(ranges, region):
                for r in range(r1, r2 + 1):
                    if per_row:
                        res = _truth(ev.eval_node_fn(fn, sheet, r, c1, r - a_r, c1 - a_c))
                        if res:
                            for c in range(c1, c2 + 1):
                                apply(r, c, dxf, stop)
                                hits += 1
                    else:
                        for c in range(c1, c2 + 1):
                            if _truth(ev.eval_node_fn(fn, sheet, r, c, r - a_r, c - a_c)):
                                apply(r, c, dxf, stop)
                                hits += 1
        elif typ == "cellIs":
            op = rule.get("operator") or "equal"
            fns = [_compile(parse(f)) for f in rule["formulas"]]
            for (r1, c1, r2, c2) in _cells_in(ranges, region):
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        v = val(r, c)
                        if v is None and op not in ("equal", "notEqual"):
                            continue
                        args = [ev.eval_node_fn(f, sheet, r, c, r - a_r, c - a_c) for f in fns]
                        if any(isinstance(x, XlError) for x in args) or isinstance(v, XlError):
                            continue
                        try:
                            if op == "between":
                                lo, hi = sorted([args[0], args[1]], key=lambda x: (0, x) if is_number(x) else (1, str(x)))
                                ok = compare(v, lo) >= 0 and compare(v, hi) <= 0
                            elif op == "notBetween":
                                lo, hi = sorted([args[0], args[1]], key=lambda x: (0, x) if is_number(x) else (1, str(x)))
                                ok = not (compare(v, lo) >= 0 and compare(v, hi) <= 0)
                            else:
                                cres = compare(v, args[0])
                                ok = {"equal": cres == 0, "notEqual": cres != 0, "greaterThan": cres > 0,
                                      "lessThan": cres < 0, "greaterThanOrEqual": cres >= 0,
                                      "lessThanOrEqual": cres <= 0}[op]
                        except XlError:
                            ok = False
                        if ok:
                            apply(r, c, dxf, stop)
                            hits += 1
        elif typ in ("containsText", "notContainsText", "beginsWith", "endsWith",
                     "containsBlanks", "notContainsBlanks", "containsErrors", "notContainsErrors"):
            text = (rule.get("text") or "").lower()
            for (r1, c1, r2, c2) in _cells_in(ranges, region):
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        v = val(r, c)
                        s = "" if v is None else (v if isinstance(v, str) else str(v))
                        sl = s.lower()
                        if typ == "containsText":
                            ok = text in sl
                        elif typ == "notContainsText":
                            ok = text not in sl
                        elif typ == "beginsWith":
                            ok = sl.startswith(text)
                        elif typ == "endsWith":
                            ok = sl.endswith(text)
                        elif typ == "containsBlanks":
                            ok = s.strip() == ""
                        elif typ == "notContainsBlanks":
                            ok = s.strip() != ""
                        elif typ == "containsErrors":
                            ok = isinstance(v, XlError)
                        else:
                            ok = not isinstance(v, XlError)
                        if ok:
                            apply(r, c, dxf, stop)
                            hits += 1
        elif typ in ("duplicateValues", "uniqueValues"):
            allv = {}
            for (r1, c1, r2, c2) in ranges:
                for r in range(r1, min(r2, sh.max_row) + 1):
                    for c in range(c1, c2 + 1):
                        v = val(r, c)
                        if v is None:
                            continue
                        k = v.lower() if isinstance(v, str) else v
                        allv[k] = allv.get(k, 0) + 1
            for (r1, c1, r2, c2) in _cells_in(ranges, region):
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        v = val(r, c)
                        if v is None:
                            continue
                        k = v.lower() if isinstance(v, str) else v
                        dup = allv.get(k, 0) > 1
                        if dup == (typ == "duplicateValues"):
                            apply(r, c, dxf, stop)
                            hits += 1
        elif typ in ("colorScale", "dataBar"):
            nums = []
            for (r1, c1, r2, c2) in ranges:
                for r in range(r1, min(r2, sh.max_row) + 1):
                    for c in range(c1, c2 + 1):
                        v = val(r, c)
                        if is_number(v):
                            nums.append(to_num(v))
            if not nums:
                out.rule_hits.append((prio, typ, ranges, 0))
                continue
            nums.sort()
            lo_all, hi_all = nums[0], nums[-1]

            def thr(cfvo):
                t, v = cfvo
                if t == "min":
                    return lo_all
                if t == "max":
                    return hi_all
                if t == "num":
                    return float(v)
                if t == "percent":
                    return lo_all + (hi_all - lo_all) * float(v) / 100.0
                if t == "percentile":
                    return percentile_inc(nums, float(v) / 100.0)
                if t == "formula":
                    return to_num(ev.eval_text("=" + v, sheet, a_r, a_c))
                raise ValueError("cfvo %s" % t)
            ths = [thr(x) for x in rule["cfvo"]]
            colors = rule["colors"]
            for (r1, c1, r2, c2) in _cells_in(ranges, region):
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        v = val(r, c)
                        if not is_number(v):
                            continue
                        x = to_num(v)
                        if typ == "colorScale":
                            if len(ths) == 2:
                                lo, hi = ths
                                col = colors[0] if x <= lo else colors[1] if x >= hi else _lerp(colors[0], colors[1], (x - lo) / (hi - lo))
                            else:
                                lo, mid, hi = ths
                                if x <= lo:
                                    col = colors[0]
                                elif x >= hi:
                                    col = colors[2]
                                elif x <= mid:
                                    col = _lerp(colors[0], colors[1], (x - lo) / (mid - lo)) if mid > lo else colors[1]
                                else:
                                    col = _lerp(colors[1], colors[2], (x - mid) / (hi - mid)) if hi > mid else colors[2]
                            props = {"bg": col} if col and col.upper() != WHITE else {"bg_white": True}
                            apply(r, c, props, False)
                        else:
                            lo, hi = ths[0], ths[1]
                            p = 1.0 if hi <= lo else max(0.0, min(1.0, (x - lo) / (hi - lo)))
                            apply(r, c, {"bar": (round(p, 4), colors[0] if colors else "#638EC6")}, False)
                        hits += 1
        else:
            raise NotImplementedError("CF rule type %s in %s" % (typ, sheet))
        out.rule_hits.append((prio, typ, ranges, hits))
    for ov in cells.values():
        ov.pop("_stop", None)
    return out
