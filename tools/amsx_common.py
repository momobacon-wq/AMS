# -*- coding: utf-8 -*-
"""Shared helpers for tools/extract.py and tools/verify_data.py.

Everything here is pure (no workbook access) so that the extractor and the
independent verifier format values identically:

* ``fmt_datetime(value, number_format)`` - datetime -> string per CONTRACT v2
* ``col_px / table_col_px / row_px``      - Excel geometry -> CSS px
* ``SHEET_MODES`` / ``sheet_id``           - workbook-wide mode map
* ``link_target_row``                      - HYPERLINK row -> JSON ``r``
"""
import datetime as _dt
import re as _re

# ---------------------------------------------------------------------------
# sheet ids / modes
# ---------------------------------------------------------------------------
GRID_IDS = ("00", "01", "14", "16", "17", "18", "24")
CARD_IDS = ("02",)
CHUNKED_IDS = ("21", "22")
CHUNK_TARGET_ROWS = 25000

SHEET_MODES = {}
for _i in range(28):
    _sid = "%02d" % _i
    SHEET_MODES[_sid] = "grid" if _sid in GRID_IDS else ("card" if _sid in CARD_IDS else "table")

TABLE_DATA_FIRST_ROW = 5  # every table sheet: header row 4, data from row 5


def sheet_id(sheet_name):
    """'03_設備總表' -> '03'"""
    return sheet_name[:2]


def short_name(sheet_name):
    """'03_設備總表' -> '設備總表', '25_附錄_型號庫' -> '附錄_型號庫'"""
    return sheet_name[3:] if len(sheet_name) > 3 and sheet_name[2] == "_" else sheet_name


def link_target_row(target_id, excel_row, modes=None, data_first_row=None):
    """Excel row of a HYPERLINK target -> contract ``r``.

    grid  -> Excel row (1-based)
    table -> 0-based data index (row - data_first_row), None inside the title area
    card  -> None
    For chunked tables the index is GLOBAL (across parts).
    """
    modes = modes or SHEET_MODES
    mode = modes.get(target_id)
    if mode == "grid":
        return int(excel_row)
    if mode == "table":
        dfr = data_first_row or TABLE_DATA_FIRST_ROW
        if isinstance(dfr, dict):
            dfr = dfr.get(target_id, TABLE_DATA_FIRST_ROW)
        return None if excel_row < dfr else int(excel_row) - dfr
    return None


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------
EXCEL_DEFAULT_COL_WIDTH = 8.43
EXCEL_DEFAULT_ROW_PT = 15.0


def col_px(width):
    """Excel column width (chars) -> px, x7.5 rounded half-up (not banker's)."""
    if width is None:
        width = EXCEL_DEFAULT_COL_WIDTH
    return int(float(width) * 7.5 + 0.5)


def table_col_px(width):
    """Table-mode column width: col_px clamped to [40, 420]."""
    return max(40, min(420, col_px(width)))


def row_px(pt):
    """Row height pt -> px = round(pt*4/3) (half-up)."""
    if pt is None:
        pt = EXCEL_DEFAULT_ROW_PT
    return int(float(pt) * 4.0 / 3.0 + 0.5)


def emu_px(emu):
    return int(round(int(emu) / 9525.0))


# ---------------------------------------------------------------------------
# datetime formatting (CONTRACT v2)
# ---------------------------------------------------------------------------
_MS_RE = _re.compile(r"s\.0+", _re.I)


def _round_to(dt, unit_us):
    us = dt.microsecond
    rem = us % unit_us
    base = dt - _dt.timedelta(microseconds=rem)
    if rem * 2 >= unit_us:
        base += _dt.timedelta(microseconds=unit_us)
    return base


def fmt_kind(number_format):
    """Classify a date/time number format: 'ms' | 'date' | 'min' | 'sec'."""
    nf = (number_format or "").lower()
    # strip literal/quoted sections and colour/locale brackets
    nf = _re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", nf)
    if _MS_RE.search(nf):
        return "ms"
    has_time = ("h" in nf) or ("s" in nf) or (":" in nf)
    if not has_time:
        return "date"
    if "s" not in nf:
        return "min"
    return "sec"


def fmt_datetime(value, number_format=None):
    """Format a datetime/date/time per the cell number_format (CONTRACT v2).

    * format contains ``.000``        -> ``YYYY-MM-DD HH:MM:SS.fff`` (rounded to ms)
    * date-only format (yyyy-mm-dd)   -> ``YYYY-MM-DD``
    * ``yyyy-mm-dd hh:mm``            -> ``YYYY-MM-DD HH:MM`` (seconds rounded, then cut)
    * any other date/time             -> ``YYYY-MM-DD HH:MM:SS`` rounded to the second
    Non-datetime values are returned unchanged.
    """
    if isinstance(value, _dt.datetime):
        kind = fmt_kind(number_format)
        if kind == "ms":
            d = _round_to(value, 1000)
            return d.strftime("%Y-%m-%d %H:%M:%S") + ".%03d" % (d.microsecond // 1000)
        if kind == "date":
            return value.strftime("%Y-%m-%d")
        d = _round_to(value, 1000000)
        if kind == "min":
            return d.strftime("%Y-%m-%d %H:%M")
        return d.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, _dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, _dt.time):
        d = _dt.datetime.combine(_dt.date(1900, 1, 1), value)
        kind = fmt_kind(number_format)
        if kind == "ms":
            d = _round_to(d, 1000)
            return d.strftime("%H:%M:%S") + ".%03d" % (d.microsecond // 1000)
        d = _round_to(d, 1000000)
        return d.strftime("%H:%M:%S")
    return value


# ---------------------------------------------------------------------------
# number formatting (subset; used for pre-rendered "d" strings)
# ---------------------------------------------------------------------------
_NUM_SEC = _re.compile(r'^((?:"[^"]*"|\\.|[^0#?.,%])*?)([0#?,]+(?:\.[0#?]+)?)(%?)((?:"[^"]*"|\\.|[^0#?])*)$')


def _lit(s):
    return _re.sub(r'"([^"]*)"|\\(.)', lambda m: m.group(1) if m.group(1) is not None else m.group(2), s)


def fmt_number(v, number_format):
    """Format a number with a simple Excel format ('0.0', '#,##0', '0.0%',
    '+0.0;-0.0;0.0' ...).  Returns None when the format is not understood."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    nf = number_format or "General"
    if nf == "General":
        return None
    secs = nf.split(";")
    if len(secs) >= 3 and v == 0:
        sec, x = secs[2], 0.0
    elif len(secs) >= 2 and v < 0:
        sec, x = secs[1], -v  # the negative section carries its own sign literal
    else:
        sec, x = secs[0], v
    m = _NUM_SEC.match(sec)
    if not m:
        return None
    pre, body, pct, post = m.groups()
    if pct:
        x = x * 100.0
    dec = len(body.split(".")[1]) if "." in body else 0
    grp = "," in body.split(".")[0]
    neg = x < 0 and len(secs) == 1
    x = abs(x)
    q = 10 ** dec
    x = float("%.15g" % (x * q))
    x = int(x + 0.5) / float(q) if dec else float(int(x + 0.5))
    s = ("{:,.%df}" % dec).format(x) if grp else ("{:.%df}" % dec).format(x)
    return ("-" if neg else "") + _lit(pre) + s + pct + _lit(post)


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------
REAL_FORMULA_RE = _re.compile(r"^=\s*[A-Z][A-Z0-9.]*\(")


def is_real_formula_text(s):
    """CONTRACT fact 1 regex (the extractor itself uses the XML <f> element)."""
    return isinstance(s, str) and bool(REAL_FORMULA_RE.match(s))


def csv_safe(v):
    """CONTRACT v2: values starting with = + - @ get a leading apostrophe in CSV."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def style_string(b=False, i=False, u=False, bg=None, fc=None):
    """Compact table style string ``flags|bg|fc`` (flags subset of 'biu')."""
    flags = ("b" if b else "") + ("i" if i else "") + ("u" if u else "")
    return "%s|%s|%s" % (flags, bg or "", fc or "")


def parse_style_string(s):
    flags, bg, fc = (s.split("|") + ["", ""])[:3]
    return {"b": "b" in flags, "i": "i" in flags, "u": "u" in flags,
            "bg": bg or None, "fc": fc or None}
