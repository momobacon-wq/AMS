# -*- coding: utf-8 -*-
"""Fast, dependency-light reader for the openpyxl-generated AMS workbook.

The workbook stores every string inline (no sharedStrings), formulas as <f>
with empty <v> (no cached values) and is ~340 MB of sheet XML, so the cell
data is scanned with regular expressions (≈1 s per 3M cells) while the small
parts (styles, workbook, sheet head/tail, drawings) are parsed with
ElementTree.  Numeric cells whose number format is a date format are
converted with openpyxl's own ``from_excel`` so that values match what
openpyxl (used by verify_data.py) reports.
"""
import re
import zipfile
import posixpath
import datetime as dt
import xml.etree.ElementTree as ET

from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format
from openpyxl.utils.datetime import from_excel, CALENDAR_WINDOWS_1900, CALENDAR_MAC_1904
from openpyxl.utils.cell import column_index_from_string, get_column_letter

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
M = "{%s}" % NS_MAIN
RID = "{%s}id" % NS_R

# ---------------------------------------------------------------------------
# XML text helpers
# ---------------------------------------------------------------------------
_ENT_RE = re.compile(r"&(#x[0-9a-fA-F]+|#[0-9]+|amp|lt|gt|quot|apos);")
_ENT = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def _ent(m):
    g = m.group(1)
    if g[0] == "#":
        return chr(int(g[2:], 16) if g[1] in "xX" else int(g[1:]))
    return _ENT[g]


def xml_unescape(s):
    """XML (not HTML!) entity decoding: &#129; must stay U+0081."""
    if "&" not in s:
        return s
    return _ENT_RE.sub(_ent, s)


_COLCACHE = {}


def col_index(letters):
    v = _COLCACHE.get(letters)
    if v is None:
        v = column_index_from_string(letters)
        _COLCACHE[letters] = v
    return v


def col_letter(idx):
    return get_column_letter(idx)


_REF_RE = re.compile(r"^\$?([A-Z]{1,3})\$?(\d+)$")


def parse_cell_ref(ref):
    m = _REF_RE.match(ref)
    return int(m.group(2)), col_index(m.group(1))


def parse_range(ref):
    """'A4:DP1932' -> (r1, c1, r2, c2); 'B5' -> (5,2,5,2)"""
    ref = ref.replace("$", "")
    if ":" in ref:
        a, b = ref.split(":")
        r1, c1 = parse_cell_ref(a)
        r2, c2 = parse_cell_ref(b)
    else:
        r1, c1 = parse_cell_ref(ref)
        r2, c2 = r1, c1
    return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)


def color_of(el):
    """<color rgb="00RRGGBB"/> -> '#RRGGBB' ; theme / indexed / auto -> None"""
    if el is None:
        return None
    rgb = el.get("rgb")
    if rgb:
        rgb = rgb[-6:].upper()
        return "#" + rgb
    idx = el.get("indexed")
    if idx is not None:
        i = int(idx)
        if i == 64 or i == 65:  # system fore/back
            return None
        return _INDEXED.get(i)
    return None  # theme colours: theme 1 = default text, not meaningful here


_INDEXED = {0: "#000000", 1: "#FFFFFF", 2: "#FF0000", 3: "#00FF00", 4: "#0000FF", 5: "#FFFF00",
            6: "#FF00FF", 7: "#00FFFF", 8: "#000000", 9: "#FFFFFF", 10: "#FF0000"}


def _bool_attr(el, default=True):
    if el is None:
        return None
    v = el.get("val")
    if v is None:
        return default
    return v not in ("0", "false", "False")


# ---------------------------------------------------------------------------
# styles.xml
# ---------------------------------------------------------------------------
class Font(object):
    __slots__ = ("name", "sz", "b", "i", "u", "strike", "color")

    def __init__(self, el):
        f = lambda t: el.find(M + t)
        n = f("name")
        self.name = n.get("val") if n is not None else None
        s = f("sz")
        self.sz = float(s.get("val")) if s is not None else None
        self.b = bool(_bool_attr(f("b")))
        self.i = bool(_bool_attr(f("i")))
        u = f("u")
        self.u = (u.get("val") or "single") if u is not None and u.get("val") != "none" else None
        self.strike = bool(_bool_attr(f("strike")))
        self.color = color_of(f("color"))


class Xf(object):
    __slots__ = ("numfmt", "font", "fill", "border", "ha", "va", "wrap", "indent", "shrink", "rotation")


class Styles(object):
    def __init__(self, xml_bytes):
        root = ET.fromstring(xml_bytes)
        self.numfmts = dict(BUILTIN_FORMATS)
        nf = root.find(M + "numFmts")
        if nf is not None:
            for e in nf:
                self.numfmts[int(e.get("numFmtId"))] = e.get("formatCode")
        self.fonts = [Font(e) for e in root.find(M + "fonts")]
        self.fills = []
        for e in root.find(M + "fills"):
            pf = e.find(M + "patternFill")
            bg = None
            if pf is not None and pf.get("patternType") not in (None, "none"):
                bg = color_of(pf.find(M + "fgColor")) or color_of(pf.find(M + "bgColor"))
            self.fills.append(bg)
        self.borders = []
        for e in root.find(M + "borders"):
            sides = {}
            for side, key in (("left", "l"), ("right", "r"), ("top", "t"), ("bottom", "b")):
                s = e.find(M + side)
                if s is not None and s.get("style"):
                    sides[key] = (s.get("style"), color_of(s.find(M + "color")))
            self.borders.append(sides)
        self.xfs = []
        for e in root.find(M + "cellXfs"):
            x = Xf()
            x.numfmt = self.numfmts.get(int(e.get("numFmtId", 0)), "General")
            x.font = self.fonts[int(e.get("fontId", 0))]
            x.fill = self.fills[int(e.get("fillId", 0))]
            x.border = self.borders[int(e.get("borderId", 0))]
            a = e.find(M + "alignment")
            x.ha = a.get("horizontal") if a is not None else None
            x.va = a.get("vertical") if a is not None else None
            x.wrap = bool(a is not None and a.get("wrapText") in ("1", "true"))
            x.indent = int(a.get("indent", 0)) if a is not None else 0
            x.shrink = bool(a is not None and a.get("shrinkToFit") in ("1", "true"))
            x.rotation = int(a.get("textRotation", 0)) if a is not None else 0
            self.xfs.append(x)
        self.is_date = [bool(is_date_format(x.numfmt)) for x in self.xfs]
        # differential formats (conditional formatting)
        self.dxfs = []
        dx = root.find(M + "dxfs")
        if dx is not None:
            for e in dx:
                d = {}
                fo = e.find(M + "font")
                if fo is not None:
                    for t, k in (("b", "b"), ("i", "i")):
                        v = _bool_attr(fo.find(M + t))
                        if v is not None:
                            d[k] = v
                    u = fo.find(M + "u")
                    if u is not None:
                        d["u"] = u.get("val") != "none"
                    c = color_of(fo.find(M + "color"))
                    if c:
                        d["fc"] = c
                fi = e.find(M + "fill")
                if fi is not None:
                    pf = fi.find(M + "patternFill")
                    if pf is not None:
                        c = color_of(pf.find(M + "bgColor")) or color_of(pf.find(M + "fgColor"))
                        if c:
                            d["bg"] = c
                bo = e.find(M + "border")
                if bo is not None:
                    sides = {}
                    for side, key in (("left", "l"), ("right", "r"), ("top", "t"), ("bottom", "b")):
                        s = bo.find(M + side)
                        if s is not None and s.get("style"):
                            sides[key] = (s.get("style"), color_of(s.find(M + "color")))
                    if sides:
                        d["bd"] = sides
                self.dxfs.append(d)


# ---------------------------------------------------------------------------
# cells
# ---------------------------------------------------------------------------
class Formula(object):
    """A REAL formula cell (XML <f>).  ``text`` keeps the leading '='."""
    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return "Formula(%r)" % self.text


_CELL_RE = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
_ROW_RE = re.compile(r"<row ([^>]*?)/?>")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_T_RE = re.compile(r"<t(?:\s[^>]*)?>(.*?)</t>|<t(?:\s[^>]*)?/>", re.S)
_F_RE = re.compile(r"<f(?:\s[^>]*)?>(.*?)</f>", re.S)
_V_RE = re.compile(r"<v>(.*?)</v>", re.S)


def _cast_number(v):
    if "." in v or "E" in v or "e" in v:
        return float(v)
    return int(v)


class Sheet(object):
    """One worksheet: values/styles by row, geometry and formatting metadata."""

    def __init__(self, wb, name, index, part):
        self.wb = wb
        self.name = name
        self.id = name[:2]
        self.index = index
        self.part = part
        self.rows = {}      # r -> list of values (index c-1)
        self.srows = {}     # r -> list of style ids
        self.max_row = 0
        self.max_col = 0
        self.row_ht = {}    # r -> (pt, custom)
        self.hidden_rows = set()
        self.cols = []      # (min, max, width, hidden, outline)
        self.merges = []    # (r1, c1, r2, c2)
        self.pane = None
        self.show_gridlines = True
        self.zoom = None
        self.autofilter = None
        self.cf = []        # list of (ranges, [rule dicts])
        self.dv = []
        self.default_col_width = None
        self.default_row_ht = 15.0
        self.tab_color = None
        self.drawing_rids = []
        self.formula_count = 0

    # --- parsing ---------------------------------------------------------
    def load(self, xml_bytes):
        text = xml_bytes.decode("utf-8")
        i = text.find("<sheetData")
        j = text.find("</sheetData>")
        if j < 0:  # <sheetData/>
            j2 = text.find("/>", i)
            head, data, tail = text[:i], "", text[j2 + 2:]
        else:
            k = text.find(">", i) + 1
            head, data, tail = text[:i], text[k:j], text[j + len("</sheetData>"):]
        self._parse_meta(head + "<sheetData/>" + tail)
        self._parse_rows(data)
        self._parse_cells(data)

    def _parse_meta(self, xml):
        root = ET.fromstring(xml)
        sp = root.find(M + "sheetPr")
        if sp is not None:
            tc = sp.find(M + "tabColor")
            self.tab_color = color_of(tc)
        sv = root.find(M + "sheetViews")
        if sv is not None:
            v = sv.find(M + "sheetView")
            if v is not None:
                self.show_gridlines = v.get("showGridLines") not in ("0", "false")
                self.zoom = int(v.get("zoomScale")) if v.get("zoomScale") else None
                p = v.find(M + "pane")
                if p is not None and p.get("state") in ("frozen", "frozenSplit"):
                    self.pane = {"x": int(float(p.get("xSplit", 0))), "y": int(float(p.get("ySplit", 0))),
                                 "top_left": p.get("topLeftCell")}
        fp = root.find(M + "sheetFormatPr")
        if fp is not None:
            if fp.get("defaultColWidth"):
                self.default_col_width = float(fp.get("defaultColWidth"))
            elif fp.get("baseColWidth"):
                # Excel: default width = baseColWidth + 5px padding ≈ base + 0.43 chars (for 8 -> 8.43)
                self.default_col_width = float(fp.get("baseColWidth")) + 0.43
            if fp.get("defaultRowHeight"):
                self.default_row_ht = float(fp.get("defaultRowHeight"))
        cols = root.find(M + "cols")
        if cols is not None:
            for c in cols:
                self.cols.append((int(c.get("min")), int(c.get("max")),
                                  float(c.get("width")) if c.get("width") else None,
                                  c.get("hidden") in ("1", "true"), int(c.get("outlineLevel", 0))))
        af = root.find(M + "autoFilter")
        if af is not None:
            self.autofilter = parse_range(af.get("ref"))
        mc = root.find(M + "mergeCells")
        if mc is not None:
            for m in mc:
                self.merges.append(parse_range(m.get("ref")))
        for cfe in root.findall(M + "conditionalFormatting"):
            ranges = [parse_range(x) for x in cfe.get("sqref").split()]
            rules = []
            for r in cfe.findall(M + "cfRule"):
                d = {"type": r.get("type"), "priority": int(r.get("priority", 0)),
                     "dxf": int(r.get("dxfId")) if r.get("dxfId") is not None else None,
                     "stop": r.get("stopIfTrue") in ("1", "true"),
                     "operator": r.get("operator"), "text": r.get("text"),
                     "formulas": [(f.text or "") for f in r.findall(M + "formula")]}  # ET already decoded entities
                cs = r.find(M + "colorScale")
                if cs is not None:
                    d["cfvo"] = [(c.get("type"), c.get("val")) for c in cs.findall(M + "cfvo")]
                    d["colors"] = [color_of(c) for c in cs.findall(M + "color")]
                db = r.find(M + "dataBar")
                if db is not None:
                    d["cfvo"] = [(c.get("type"), c.get("val")) for c in db.findall(M + "cfvo")]
                    d["colors"] = [color_of(c) for c in db.findall(M + "color")]
                    d["minLength"] = int(db.get("minLength", 10))
                    d["maxLength"] = int(db.get("maxLength", 90))
                rules.append(d)
            self.cf.append((ranges, rules))
        dvs = root.find(M + "dataValidations")
        if dvs is not None:
            for d in dvs:
                f1 = d.find(M + "formula1")
                self.dv.append({"sqref": d.get("sqref"), "type": d.get("type"), "operator": d.get("operator"),
                                "prompt": d.get("prompt"), "promptTitle": d.get("promptTitle"),
                                "errorStyle": d.get("errorStyle"),
                                "formula1": f1.text if f1 is not None else None})
        for d in root.findall(M + "drawing"):
            self.drawing_rids.append(d.get(RID))

    def _parse_rows(self, data):
        for m in _ROW_RE.finditer(data):
            attrs = dict(_ATTR_RE.findall(m.group(1)))
            r = int(attrs["r"])
            if "ht" in attrs:
                self.row_ht[r] = (float(attrs["ht"]), attrs.get("customHeight") in ("1", "true"))
            if attrs.get("hidden") in ("1", "true"):
                self.hidden_rows.add(r)

    def _parse_cells(self, data):
        styles = self.wb.styles
        is_date = styles.is_date
        epoch = self.wb.epoch
        rows = self.rows
        srows = self.srows
        cur_r = -1
        vals = sv = None
        max_col = 0
        nform = 0
        for m in _CELL_RE.finditer(data):
            col_l, r_s, attrs, inner = m.groups()
            c = _COLCACHE.get(col_l)
            if c is None:
                c = col_index(col_l)
            r = int(r_s)
            s = 0
            t = None
            if attrs:
                p = attrs.find(' s="')
                if p >= 0:
                    s = int(attrs[p + 4:attrs.index('"', p + 4)])
                p = attrs.find(' t="')
                if p >= 0:
                    t = attrs[p + 4:attrs.index('"', p + 4)]
            val = None
            if inner:
                if t == "inlineStr":
                    parts = _T_RE.findall(inner)
                    if parts or "<is" in inner:
                        val = xml_unescape("".join(parts))
                elif "<f" in inner:
                    fm = _F_RE.search(inner)
                    if fm is not None:
                        val = Formula("=" + xml_unescape(fm.group(1)))
                        nform += 1
                    else:  # <f .../> shared formula child without text: not expected
                        raise ValueError("unsupported formula form in %s %s%s" % (self.name, col_l, r_s))
                else:
                    vm = _V_RE.search(inner)
                    if vm is not None and vm.group(1) != "":
                        raw = vm.group(1)
                        if t in (None, "n"):
                            val = _cast_number(raw)
                            if is_date[s]:
                                val = from_excel(val, epoch)
                        elif t == "b":
                            val = raw in ("1", "true")
                        elif t in ("s",):
                            val = self.wb.shared_strings[int(raw)]
                        elif t == "str":
                            val = xml_unescape(raw)
                        elif t == "e":
                            val = xml_unescape(raw)
                        elif t == "d":
                            val = dt.datetime.fromisoformat(raw.replace("Z", ""))
                        else:
                            val = xml_unescape(raw)
            if r != cur_r:
                vals = rows.get(r)
                if vals is None:
                    vals = rows[r] = []
                    sv = srows[r] = []
                else:
                    sv = srows[r]
                cur_r = r
            n = len(vals)
            if c > n:
                if c > n + 1:
                    vals.extend([None] * (c - 1 - n))
                    sv.extend([0] * (c - 1 - n))
                vals.append(val)
                sv.append(s)
            else:
                vals[c - 1] = val
                sv[c - 1] = s
            if c > max_col:
                max_col = c
        self.max_col = max_col
        self.max_row = max(rows) if rows else 0
        if self.row_ht:
            self.max_row = max(self.max_row, max(self.row_ht))
        self.formula_count = nform

    # --- access ----------------------------------------------------------
    def raw(self, r, c):
        row = self.rows.get(r)
        if row is None or c > len(row) or c < 1:
            return None
        return row[c - 1]

    def style_id(self, r, c):
        row = self.srows.get(r)
        if row is None or c > len(row) or c < 1:
            return 0
        return row[c - 1]

    def xf(self, r, c):
        return self.wb.styles.xfs[self.style_id(r, c)]

    def number_format(self, r, c):
        return self.wb.styles.xfs[self.style_id(r, c)].numfmt

    def has_cell(self, r, c):
        row = self.rows.get(r)
        return row is not None and 1 <= c <= len(row)

    def col_width(self, c):
        for mn, mx, w, hid, ol in self.cols:
            if mn <= c <= mx:
                return w
        return self.default_col_width

    def col_hidden(self, c):
        for mn, mx, w, hid, ol in self.cols:
            if mn <= c <= mx:
                return hid
        return False

    def merge_map(self):
        """(r,c) -> ('anchor', rs, cs) | ('covered', r0, c0)"""
        mm = {}
        for r1, c1, r2, c2 in self.merges:
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    mm[(r, c)] = ("covered", r1, c1)
            mm[(r1, c1)] = ("anchor", r2 - r1 + 1, c2 - c1 + 1)
        return mm


class Workbook(object):
    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path)
        self.names = set(self.zip.namelist())
        self.styles = Styles(self.zip.read("xl/styles.xml"))
        wbx = ET.fromstring(self.zip.read("xl/workbook.xml"))
        pr = wbx.find(M + "workbookPr")
        self.epoch = CALENDAR_MAC_1904 if (pr is not None and pr.get("date1904") in ("1", "true")) else CALENDAR_WINDOWS_1900
        rels = self.rels("xl/workbook.xml")
        self.sheet_names = []
        self.sheet_parts = {}
        for s in wbx.find(M + "sheets"):
            nm = s.get("name")
            self.sheet_names.append(nm)
            self.sheet_parts[nm] = rels[s.get(RID)]
        self.defined_names = []
        dn = wbx.find(M + "definedNames")
        if dn is not None:
            for d in dn:
                self.defined_names.append({"name": d.get("name"), "local": d.get("localSheetId"), "ref": d.text})
        self.shared_strings = []
        if "xl/sharedStrings.xml" in self.names:
            root = ET.fromstring(self.zip.read("xl/sharedStrings.xml"))
            for si in root:
                self.shared_strings.append("".join(t.text or "" for t in si.iter(M + "t")))
        self.sheets = {}

    def rels(self, part):
        d, b = posixpath.split(part)
        rp = "%s/_rels/%s.rels" % (d, b)
        if rp not in self.names:
            return {}
        root = ET.fromstring(self.zip.read(rp))
        out = {}
        for r in root:
            t = r.get("Target")
            t = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join(d, t))
            out[r.get("Id")] = t
        return out

    def load_sheet(self, name):
        if name in self.sheets:
            return self.sheets[name]
        sh = Sheet(self, name, self.sheet_names.index(name), self.sheet_parts[name])
        sh.load(self.zip.read(sh.part))
        self.sheets[name] = sh
        return sh

    def sheet_by_id(self, sid):
        for n in self.sheet_names:
            if n[:2] == sid:
                return self.load_sheet(n)
        raise KeyError(sid)

    def name_by_id(self, sid):
        for n in self.sheet_names:
            if n[:2] == sid:
                return n
        return None

    def read_xml(self, part):
        return ET.fromstring(self.zip.read(part))
