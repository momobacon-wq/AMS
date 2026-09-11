# -*- coding: utf-8 -*-
"""Native Excel charts -> contract chart specs (specs/charts.md).

drawing rels -> chart XML -> <c:f> refs -> evaluated cell values.
Anchors are oneCellAnchor (from + ext); ``to`` is computed from Excel-native
column pixel widths (MDW 7) and row heights, then clipped so that a chart
does not overlap a sibling chart starting to its right/below and does not
leave the sheet's print area.
"""
import re
import math

from amsx_common import emu_px
from .formula import Link, XlError
from .xlsx import col_index, parse_range
from openpyxl.utils.cell import get_column_letter

NS = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
RID = "{%s}id" % NS["r"]
_REF = re.compile(r"^'?(.+?)'?!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?$")


def _txt(el):
    if el is None:
        return None
    return "".join(t.text or "" for t in el.iter("{%s}t" % NS["a"]))


def _val(el, path, default=None):
    e = el.find(path, NS)
    return e.get("val") if e is not None else default


def _color(sppr, line=False):
    if sppr is None:
        return None
    e = sppr.find("a:ln/a:solidFill/a:srgbClr" if line else "a:solidFill/a:srgbClr", NS)
    return "#" + e.get("val").upper() if e is not None else None


def _parse_ref(ref):
    m = _REF.match(ref)
    sh, c1, r1, c2, r2 = m.groups()
    c2, r2 = c2 or c1, r2 or r1
    return sh, int(r1), col_index(c1), int(r2), col_index(c2)


def _excel_col_px(width):
    """Excel-native column pixel width with a 7 px max digit width."""
    if width is None:
        width = 8.43
    return int(math.floor(((256.0 * width + math.floor(128.0 / 7)) / 256.0) * 7))


class ChartBuilder(object):
    def __init__(self, ctx):
        self.ctx = ctx
        self.wb = ctx.wb
        self.ev = ctx.ev

    def values(self, ref):
        sh, r1, c1, r2, c2 = _parse_ref(ref)
        out = []
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                v = self.ev.value(sh, r, c)
                if isinstance(v, Link):
                    v = v.label
                if isinstance(v, XlError):
                    self.ctx.warnings.append("chart ref %s: error %s" % (ref, v.code))
                    v = None
                out.append(v)
        return out

    def parse_chart(self, part):
        root = self.wb.read_xml(part)
        ch = root.find("c:chart", NS)
        pa = ch.find("c:plotArea", NS)
        axes = {}
        for ax in list(pa):
            tag = ax.tag.split("}")[1]
            if tag in ("catAx", "valAx", "dateAx", "serAx"):
                nf = ax.find("c:numFmt", NS)
                rpr = ax.find(".//a:defRPr[@sz]", NS)
                axes[_val(ax, "c:axId")] = {
                    "kind": tag, "orientation": _val(ax, "c:scaling/c:orientation"),
                    "min": _val(ax, "c:scaling/c:min"), "max": _val(ax, "c:scaling/c:max"),
                    "majorUnit": _val(ax, "c:majorUnit"), "crosses": _val(ax, "c:crosses"),
                    "axPos": _val(ax, "c:axPos"), "delete": _val(ax, "c:delete"),
                    "title": _txt(ax.find("c:title", NS)), "gridlines": ax.find("c:majorGridlines", NS) is not None,
                    "numFmt": nf.get("formatCode") if nf is not None else None,
                    "font_sz": int(rpr.get("sz")) / 100.0 if rpr is not None else None}
        groups, series = [], []
        for grp in list(pa):
            tag = grp.tag.split("}")[1]
            if not tag.endswith("Chart"):
                continue
            ax_ids = [a.get("val") for a in grp.findall("c:axId", NS)]
            g = {"kind": tag, "barDir": _val(grp, "c:barDir"), "grouping": _val(grp, "c:grouping"),
                 "gapWidth": _val(grp, "c:gapWidth"), "overlap": _val(grp, "c:overlap"),
                 "holeSize": _val(grp, "c:holeSize"), "varyColors": _val(grp, "c:varyColors"),
                 "firstSliceAng": _val(grp, "c:firstSliceAng"), "axIds": ax_ids}
            gdl = grp.find("c:dLbls", NS)
            groups.append(g)
            for s in grp.findall("c:ser", NS):
                sp = s.find("c:spPr", NS)
                ln = sp.find("a:ln", NS) if sp is not None else None
                f = lambda t: (s.find("c:%s//c:f" % t, NS).text if s.find("c:%s//c:f" % t, NS) is not None else None)
                d = {"group": tag, "gi": len(groups) - 1, "order": int(_val(s, "c:order", 0)),
                     "tx_ref": f("tx"), "cat_ref": f("cat"), "val_ref": f("val"),
                     "tx_lit": _txt(s.find("c:tx", NS)) if s.find("c:tx/c:v", NS) is not None else None,
                     "fill": _color(sp), "line": _color(sp, True),
                     "line_w": int(ln.get("w")) if ln is not None and ln.get("w") else None,
                     "marker": _val(s, "c:marker/c:symbol"), "smooth": _val(s, "c:smooth"),
                     "dpt": [(int(_val(dp, "c:idx", 0)), _color(dp.find("c:spPr", NS))) for dp in s.findall("c:dPt", NS)],
                     "axIds": ax_ids}
                dl = s.find("c:dLbls", NS)
                if dl is None:
                    dl = gdl
                if dl is not None:
                    flags = {k: _val(dl, "c:%s" % k) for k in ("showVal", "showPercent", "showCatName", "showSerName")}
                    nf = dl.find("c:numFmt", NS)
                    d["dlbl"] = {k: v == "1" for k, v in flags.items() if v is not None}
                    d["dlbl_fmt"] = nf.get("formatCode") if nf is not None else None
                series.append(d)
        leg = ch.find("c:legend", NS)
        return {"title": _txt(ch.find("c:title", NS)), "groups": groups, "series": series, "axes": axes,
                "legend": _val(leg, "c:legendPos") if leg is not None else None}

    def charts_for_sheet(self, sheet_name, first_id):
        sh = self.wb.load_sheet(sheet_name)
        rels = self.wb.rels(sh.part)
        anchors = []
        for rid in sh.drawing_rids:
            dpart = rels.get(rid)
            if not dpart:
                continue
            drels = self.wb.rels(dpart)
            droot = self.wb.read_xml(dpart)
            for anc in list(droot):
                cref = anc.find(".//c:chart", NS)
                if cref is None:
                    continue
                fr = anc.find("xdr:from", NS)
                to = anc.find("xdr:to", NS)
                ext = anc.find("xdr:ext", NS)
                anchors.append((anc.tag.split("}")[1], fr, to, ext, drels[cref.get(RID)]))
        out = []
        n = first_id
        for kind, fr, to, ext, cpart in anchors:
            spec = self.parse_chart(cpart)
            fc, frr = int(fr.find("xdr:col", NS).text), int(fr.find("xdr:row", NS).text)
            fco = int(fr.find("xdr:colOff", NS).text or 0) if fr.find("xdr:colOff", NS) is not None else 0
            fro = int(fr.find("xdr:rowOff", NS).text or 0) if fr.find("xdr:rowOff", NS) is not None else 0
            if ext is not None:
                w, h = emu_px(ext.get("cx")), emu_px(ext.get("cy"))
                xml_to = None
            else:
                w = h = None
                xml_to = (int(to.find("xdr:row", NS).text) + 1, int(to.find("xdr:col", NS).text) + 1)
            out.append(self._build(sheet_name, "C%d" % n, spec, (frr + 1, fc + 1), (fro, fco), (w, h), xml_to, cpart))
            n += 1
        self._compute_to(sh, out)
        return out

    def _build(self, sheet, cid, spec, frm, off, size, xml_to, cpart):
        groups = spec["groups"]
        g0 = groups[0]
        kinds = {g["kind"] for g in groups}
        tmap = {"barChart": "bar", "bar3DChart": "bar", "lineChart": "line", "line3DChart": "line",
                "pieChart": "pie", "pie3DChart": "pie", "doughnutChart": "doughnut", "areaChart": "area",
                "scatterChart": "scatter", "radarChart": "radar"}
        ctype = "combo" if len(kinds) > 1 else tmap.get(g0["kind"], g0["kind"])
        cats = None
        series = []
        refs = []
        prim_val_ax = g0["axIds"][1] if len(g0["axIds"]) > 1 else None
        for s in sorted(spec["series"], key=lambda s: s["order"]):
            name = None
            if s["tx_ref"]:
                name = self.values(s["tx_ref"])[0]
                refs.append(s["tx_ref"])
            elif s["tx_lit"]:
                name = s["tx_lit"]
            vals = self.values(s["val_ref"]) if s["val_ref"] else []
            refs.append(s["val_ref"])
            if s["cat_ref"]:
                c = [v if isinstance(v, str) or v is None else v for v in self.values(s["cat_ref"])]
                refs.append(s["cat_ref"])
                if cats is None:
                    cats = c
                elif c != cats:
                    self.ctx.warnings.append("%s %s: series with different categories" % (sheet, cid))
            stype = tmap.get(s["group"], s["group"])
            axis = "y"
            if prim_val_ax is not None and len(s["axIds"]) > 1 and s["axIds"][1] != prim_val_ax:
                axis = "y2"
            o = {"name": name, "values": vals, "color": s["fill"] or s["line"], "type": stype, "axis": axis}
            if s["dpt"]:
                cols = [None] * len(vals)
                for i, col in s["dpt"]:
                    if i < len(cols):
                        cols[i] = col
                o["colors"] = cols
                o["border"] = s["line"]
                o["color"] = None
            if stype in ("line", "scatter", "radar"):
                if s["line_w"]:
                    o["line_px"] = round(s["line_w"] / 12700.0 * 96 / 72, 1)
                if s["marker"] == "none":
                    o["point_radius"] = 0
                if s["smooth"] == "1":
                    o["smooth"] = True
            series.append(o)
        # axes
        ax = spec["axes"]
        valaxes = [(k, a) for k, a in ax.items() if a["kind"] == "valAx"]
        cataxes = [a for a in ax.values() if a["kind"] in ("catAx", "dateAx")]
        prim = ax.get(prim_val_ax) if prim_val_ax else None
        sec = None
        for k, a in valaxes:
            if k != prim_val_ax and any(s["axis"] == "y2" for s in series):
                sec = a

        def axis_obj(a, secondary=False):
            d = {"grid": bool(a["gridlines"])}
            if a["min"] is not None:
                d["min"] = float(a["min"])
            if a["max"] is not None:
                d["max"] = float(a["max"])
            if a["majorUnit"]:
                d["step"] = float(a["majorUnit"])
            if a["numFmt"] and a["numFmt"] != "General":
                d["fmt"] = a["numFmt"]
            if a["title"]:
                d["title"] = a["title"]
            if secondary:
                d["position"] = "right"
            return d
        chart = {"id": cid, "title": spec["title"], "type": ctype,
                 "horizontal": g0.get("barDir") == "bar",
                 "stacked": g0.get("grouping") in ("stacked", "percentStacked"),
                 "percent": g0.get("grouping") == "percentStacked",
                 "anchor": {"from": {"r": frm[0], "c": frm[1]}, "to": None},
                 "size_px": {"w": size[0], "h": size[1]} if size[0] else None,
                 "categories": cats or [], "series": series,
                 "y_title": prim["title"] if prim else None,
                 "y2_title": sec["title"] if sec else None}
        # source = bounding range of every ref (single sheet)
        parsed = [_parse_ref(r) for r in refs if r]
        shs = {p[0] for p in parsed}
        if len(shs) == 1:
            shn = parsed[0][0]
            r1 = min(p[1] for p in parsed)
            c1 = min(p[2] for p in parsed)
            r2 = max(p[3] for p in parsed)
            c2 = max(p[4] for p in parsed)
            chart["source"] = "'%s'!$%s$%d:$%s$%d" % (shn, get_column_letter(c1), r1, get_column_letter(c2), r2)
            chart["src"] = {"s": shn[:2], "r": max(1, r1 - 1)}
        else:
            chart["source"] = None
        chart["legend"] = {"b": "bottom", "r": "right", "t": "top", "l": "left", "tr": "right"}.get(spec["legend"]) if spec["legend"] else None
        if ctype in ("pie", "doughnut"):
            if g0.get("holeSize"):
                chart["hole"] = int(g0["holeSize"]) / 100.0
        else:
            chart["cat_font_pt"] = cataxes[0]["font_sz"] if cataxes else None
            if prim:
                chart["y"] = axis_obj(prim)
            if sec:
                chart["y2"] = axis_obj(sec, True)
            if cataxes and cataxes[0]["orientation"] == "maxMin" and not chart["horizontal"]:
                chart["reverse"] = True
        dl = [s for s in spec["series"] if s.get("dlbl")]
        chart["data_labels"] = None
        if dl:
            d = dl[0]["dlbl"]
            if d.get("showPercent"):
                chart["data_labels"] = {"mode": "percent", "fmt": dl[0].get("dlbl_fmt") or "0%"}
            elif d.get("showVal"):
                chart["data_labels"] = {"mode": "value", "fmt": dl[0].get("dlbl_fmt") or "General"}
        # tooltip notes: text in the column right of the category range (e.g. C6 Q1..Q7 names)
        cat_refs = [s["cat_ref"] for s in spec["series"] if s["cat_ref"]]
        if cat_refs:
            shn, r1, c1, r2, c2 = _parse_ref(cat_refs[0])
            if c1 == c2:
                notes = [self.ev.value(shn, r, c1 + 1) for r in range(r1, r2 + 1)]
                if all(isinstance(x, str) and x for x in notes):
                    chart["cat_notes"] = notes
        chart["_xml_to"] = xml_to
        chart["_part"] = cpart
        return chart

    def _compute_to(self, sh, charts):
        """Native end cell (MDW 7 px), clipped at sibling charts and the print area."""
        pa = None
        for d in self.wb.defined_names:
            if d["name"] == "_xlnm.Print_Area" and d["local"] is not None and int(d["local"]) == sh.index:
                ref = d["ref"].split("!")[1]
                pa = parse_range(ref)
        for ch in charts:
            if ch.get("_xml_to"):
                ch["anchor"]["to"] = {"r": ch["_xml_to"][0], "c": ch["_xml_to"][1]}
                continue
            r0, c0 = ch["anchor"]["from"]["r"], ch["anchor"]["from"]["c"]
            w, h = ch["size_px"]["w"], ch["size_px"]["h"]
            c = c0
            acc = 0
            while True:
                cw = 0 if sh.col_hidden(c) else _excel_col_px(sh.col_width(c))
                if acc + cw >= w:
                    break
                acc += cw
                c += 1
            r = r0
            acc = 0
            while True:
                ht = sh.row_ht.get(r)
                rh = int(round((ht[0] if ht else sh.default_row_ht) * 4.0 / 3.0))
                if acc + rh >= h:
                    break
                acc += rh
                r += 1
            # clip at sibling charts starting to the right on overlapping rows
            for other in charts:
                if other is ch:
                    continue
                oc, orr = other["anchor"]["from"]["c"], other["anchor"]["from"]["r"]
                if c0 < oc <= c and orr <= r and orr + 1 >= r0 and abs(orr - r0) <= 2:
                    c = oc - 1
            if pa is not None:
                pr1, pc1, pr2, pc2 = pa
                if pc1 <= c0 <= pc2 and c > pc2:
                    c = pc2
            ch["anchor"]["to"] = {"r": r, "c": c}
        for ch in charts:
            ch.pop("_xml_to", None)
            ch.pop("_part", None)
