# -*- coding: utf-8 -*-
"""Cell value -> JSON conversion and HYPERLINK target resolution."""
import re
import datetime as dt

from amsx_common import fmt_datetime, link_target_row
from .formula import Link, XlError, Formula

_TARGET_RE = re.compile(r"^#(?:'((?:[^']|'')+)'|([^!']+))?!?\$?([A-Z]{1,3})\$?(\d+)(?::\$?[A-Z]{1,3}\$?\d+)?$")


class LinkResolver(object):
    """Turns HYPERLINK targets into contract link objects and records them
    so every emitted link can be validated after all sheets are built."""

    def __init__(self, wb, modes, data_first_rows):
        self.wb = wb
        self.modes = modes
        self.dfr = data_first_rows
        self.by_name = {n: n[:2] for n in wb.sheet_names}
        self.records = []   # (src_id, where, target_id, r, excel_row)
        self.warnings = []

    def resolve(self, target, src_id, where):
        if not isinstance(target, str):
            self.warnings.append("%s %s: non-text link target %r" % (src_id, where, target))
            return None
        if target.startswith("#"):
            m = _TARGET_RE.match(target)
            if not m:
                self.warnings.append("%s %s: unparsable link target %r" % (src_id, where, target))
                return None
            name = (m.group(1) or "").replace("''", "'") or m.group(2)
            if name is None:
                tid = src_id
            else:
                tid = self.by_name.get(name)
                if tid is None:
                    self.warnings.append("%s %s: link to unknown sheet %r" % (src_id, where, name))
                    return None
            row = int(m.group(4))
            r = link_target_row(tid, row, self.modes, self.dfr)
            self.records.append((src_id, where, tid, r, row))
            return {"s": tid, "r": r}
        if re.match(r"^(https?|mailto|ftp|file):", target, re.I):
            return {"u": target}
        self.warnings.append("%s %s: unsupported link target %r" % (src_id, where, target))
        return None


def plain_value(v, numfmt=None):
    """Non-link value -> JSON scalar (datetimes formatted per number format)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        return v
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return fmt_datetime(v, numfmt)
    if isinstance(v, XlError):
        return v.code
    if isinstance(v, Link):
        return plain_value(v.label, numfmt)
    return str(v)


def json_value(v, numfmt, resolver, src_id, where, warnings=None):
    """Evaluated cell value -> contract cell value (table mode).

    Link -> {"t": label, "l": {...}}; "" from a formula -> None; errors -> code string.
    """
    if isinstance(v, Link):
        lab = plain_value(v.label, numfmt)
        tgt = resolver.resolve(v.target, src_id, where)
        if tgt is None:
            return lab
        return {"t": lab, "l": tgt} if "u" not in tgt else {"t": lab, "u": tgt["u"]}
    if isinstance(v, XlError):
        if warnings is not None:
            warnings.append("%s %s: formula error %s" % (src_id, where, v.code))
        return v.code
    return plain_value(v, numfmt)
