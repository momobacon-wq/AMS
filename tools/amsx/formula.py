# -*- coding: utf-8 -*-
"""A small Excel formula evaluator covering every function used by the AMS
workbook (cells and conditional-format rules):

HYPERLINK MATCH INDEX IFERROR IF AND OR NOT ISNUMBER ISTEXT ISBLANK ISERROR
COUNTIF COUNTIFS COUNTA COUNT SUM SUMPRODUCT AVERAGE ROUND ROUNDUP ROUNDDOWN
INT ABS MIN MAX TRIM UPPER LOWER LEFT RIGHT MID LEN SUBSTITUTE SEARCH FIND
YEAR MONTH DAY DATE VALUE TEXT(General only) CONCATENATE TRUE FALSE
operators: & = <> < > <= >= + - * / ^ unary +/- %

Formulas are tokenised with a regex, parsed with a Pratt parser and compiled
into Python closures.  Evaluation takes a context (workbook, sheet, row/col
shift) so conditional-format formulas with relative references can be
evaluated for any cell of their range.  Cell references to other formula
cells are evaluated recursively and memoised, so evaluation order follows
the dependency graph automatically.
"""
import re
import math
import datetime as dt

from openpyxl.utils.datetime import to_excel

from .xlsx import Formula, col_index

# ---------------------------------------------------------------------------
# value types
# ---------------------------------------------------------------------------


class XlError(Exception):
    """Excel error value (#N/A, #VALUE!, ...).  Used both as value and exception."""

    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code

    def __repr__(self):
        return self.code

    def __eq__(self, other):
        return isinstance(other, XlError) and other.code == self.code

    def __hash__(self):
        return hash(self.code)


NA = XlError("#N/A")
VALUE = XlError("#VALUE!")
DIV0 = XlError("#DIV/0!")
REF = XlError("#REF!")
NAME = XlError("#NAME?")
NUM = XlError("#NUM!")


class Link(object):
    """Result of HYPERLINK(): behaves like its label in every other context."""
    __slots__ = ("target", "label")

    def __init__(self, target, label):
        self.target = target
        self.label = label

    def __repr__(self):
        return "Link(%r, %r)" % (self.target, self.label)


class Rng(object):
    """A (possibly whole-column) range reference."""
    __slots__ = ("sheet", "r1", "c1", "r2", "c2")

    def __init__(self, sheet, r1, c1, r2, c2):
        self.sheet, self.r1, self.c1, self.r2, self.c2 = sheet, r1, c1, r2, c2

    @property
    def nrows(self):
        return self.r2 - self.r1 + 1

    @property
    def ncols(self):
        return self.c2 - self.c1 + 1


# ---------------------------------------------------------------------------
# tokenizer / parser
# ---------------------------------------------------------------------------
_TOK = re.compile(r"""
 (?P<ws>\s+)
|(?P<str>"(?:[^"]|"")*")
|(?P<err>\#(?:NULL!|DIV/0!|VALUE!|REF!|NAME\?|NUM!|N/A))
|(?P<func>(?:_xlfn\.)?[A-Za-z][A-Za-z0-9._]*(?=\())
|(?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_-￿][\w.-￿]*)!)?
    (?:\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?|\$?[A-Z]{1,3}:\$?[A-Z]{1,3}|\$?\d+:\$?\d+))
|(?P<bool>TRUE|FALSE)(?![\w(])
|(?P<num>\d+\.?\d*(?:[Ee][+-]?\d+)?|\.\d+(?:[Ee][+-]?\d+)?)
|(?P<op><>|<=|>=|[-+*/^&=<>%])
|(?P<lp>\()|(?P<rp>\))|(?P<sep>,)
|(?P<name>[A-Za-z_-￿][\w.-￿]*)
""", re.X)

_REFPART = re.compile(r"^(?:(?P<sheet>'(?:[^']|'')+'|[^!]+)!)?(?P<body>.+)$")
_CELL = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)(\d+)$")
_COLS = re.compile(r"^(\$?)([A-Z]{1,3}):(\$?)([A-Z]{1,3})$")
_ROWS = re.compile(r"^(\$?)(\d+):(\$?)(\d+)$")


def tokenize(src):
    toks = []
    pos = 0
    n = len(src)
    while pos < n:
        m = _TOK.match(src, pos)
        if not m:
            raise SyntaxError("cannot tokenize %r at %d" % (src, pos))
        kind = m.lastgroup
        if kind != "ws":
            toks.append((kind, m.group(kind)))
        pos = m.end()
    return toks


def _parse_ref(text):
    m = _REFPART.match(text)
    sheet = m.group("sheet")
    if sheet is not None and sheet.startswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    body = m.group("body")
    if ":" in body:
        a, b = body.split(":")
        ma, mb = _CELL.match(a), _CELL.match(b)
        if ma and mb:
            return ("range", sheet,
                    (int(ma.group(4)), col_index(ma.group(2)), bool(ma.group(3)), bool(ma.group(1))),
                    (int(mb.group(4)), col_index(mb.group(2)), bool(mb.group(3)), bool(mb.group(1))))
        mc = _COLS.match(body)
        if mc:
            return ("cols", sheet, col_index(mc.group(2)), bool(mc.group(1)), col_index(mc.group(4)), bool(mc.group(3)))
        mr = _ROWS.match(body)
        if mr:
            return ("rows", sheet, int(mr.group(2)), bool(mr.group(1)), int(mr.group(4)), bool(mr.group(3)))
        raise SyntaxError("bad range %r" % text)
    mc = _CELL.match(body)
    return ("ref", sheet, int(mc.group(4)), col_index(mc.group(2)), bool(mc.group(3)), bool(mc.group(1)))


_BIN = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1, "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}


class _Parser(object):
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expr(self, minp=0):
        left = self.unary()
        while True:
            kind, v = self.peek()
            if kind == "op" and v == "%":
                self.next()
                left = ("pct", left)
                continue
            if kind != "op" or v not in _BIN:
                break
            p = _BIN[v]
            if p < minp:
                break
            self.next()
            right = self.expr(p + 1)  # all Excel binary operators are left-associative
            left = ("bin", v, left, right)
        return left

    def unary(self):
        kind, v = self.peek()
        if kind == "op" and v in ("-", "+"):
            self.next()
            operand = self.unary()
            return ("neg", operand) if v == "-" else operand
        return self.primary()

    def primary(self):
        kind, v = self.next()
        if kind == "num":
            f = float(v)
            return ("const", int(f) if f.is_integer() and "." not in v and "e" not in v.lower() else f)
        if kind == "str":
            return ("const", v[1:-1].replace('""', '"'))
        if kind == "bool":
            return ("const", v == "TRUE")
        if kind == "err":
            return ("const", XlError(v))
        if kind == "ref":
            return _parse_ref(v)
        if kind == "func":
            name = v.upper().replace("_XLFN.", "")
            self.next()  # (
            args = []
            if self.peek()[0] == "rp":
                self.next()
                return ("func", name, args)
            while True:
                if self.peek()[0] in ("sep", "rp"):
                    args.append(("const", None))  # omitted argument
                else:
                    args.append(self.expr())
                k, _ = self.next()
                if k == "rp":
                    break
                if k != "sep":
                    raise SyntaxError("expected , or )")
            return ("func", name, args)
        if kind == "lp":
            e = self.expr()
            if self.next()[0] != "rp":
                raise SyntaxError("expected )")
            return e
        if kind == "name":
            return ("name", v)
        raise SyntaxError("unexpected token %r %r" % (kind, v))


def parse(src):
    s = src[1:] if src.startswith("=") else src
    p = _Parser(tokenize(s))
    node = p.expr()
    if p.i != len(p.t):
        raise SyntaxError("trailing tokens in %r" % src)
    return node


def has_relative_col(node):
    """True if the formula contains a column-relative reference."""
    k = node[0]
    if k == "ref":
        return not node[5]
    if k == "range":
        return not node[2][3] or not node[3][3]
    if k == "cols":
        return not node[3] or not node[5]
    if k in ("bin",):
        return has_relative_col(node[2]) or has_relative_col(node[3])
    if k in ("neg", "pct"):
        return has_relative_col(node[1])
    if k == "func":
        return any(has_relative_col(a) for a in node[2])
    return False


def has_relative_row(node):
    k = node[0]
    if k == "ref":
        return not node[4]
    if k == "range":
        return not node[2][2] or not node[3][2]
    if k == "rows":
        return not node[3] or not node[5]
    if k in ("bin",):
        return has_relative_row(node[2]) or has_relative_row(node[3])
    if k in ("neg", "pct"):
        return has_relative_row(node[1])
    if k == "func":
        return any(has_relative_row(a) for a in node[2])
    return False


# ---------------------------------------------------------------------------
# coercions
# ---------------------------------------------------------------------------
def _serial(d):
    return to_excel(d)


def scalar(ctx, v):
    """Dereference a single-cell range / link / datetime to a plain value."""
    if isinstance(v, Rng):
        if v.r1 == v.r2 and v.c1 == v.c2:
            v = ctx.ev.value(v.sheet, v.r1, v.c1)
        else:
            # implicit intersection
            if v.c1 == v.c2 and v.r1 <= ctx.row <= v.r2 and v.sheet == ctx.sheet:
                v = ctx.ev.value(v.sheet, ctx.row, v.c1)
            elif v.r1 == v.r2 and v.c1 <= ctx.col <= v.c2 and v.sheet == ctx.sheet:
                v = ctx.ev.value(v.sheet, v.r1, ctx.col)
            else:
                raise VALUE
    if isinstance(v, Link):
        v = v.label
    return v


def to_num(v):
    if isinstance(v, XlError):
        raise v
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, (dt.datetime, dt.date)):
        return _serial(v)
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            raise VALUE
        try:
            return float(s) if any(ch in s for ch in ".eE") else int(s)
        except ValueError:
            raise VALUE
    raise VALUE


def num_to_text(v):
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        s = "%.15g" % v
        if "e" in s:
            mant, ex = s.split("e")
            s = mant + "E" + ("+" if int(ex) >= 0 else "-") + ("%02d" % abs(int(ex)))
        return s
    return str(v)


def to_text(v):
    if isinstance(v, XlError):
        raise v
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (dt.datetime, dt.date)):
        return num_to_text(_serial(v))
    return num_to_text(v)


def to_bool(v):
    if isinstance(v, XlError):
        raise v
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, (dt.datetime, dt.date)):
        return True
    if isinstance(v, str):
        u = v.upper()
        if u == "TRUE":
            return True
        if u == "FALSE":
            return False
        raise VALUE
    raise VALUE


def is_number(v):
    return (isinstance(v, (int, float)) and not isinstance(v, bool)) or isinstance(v, (dt.datetime, dt.date))


def _rank(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return 2
    if is_number(v):
        return 0
    return 1


def compare(a, b):
    """Excel comparison -> -1/0/1 (text case-insensitive; number < text < bool)."""
    if isinstance(a, XlError):
        raise a
    if isinstance(b, XlError):
        raise b
    ra, rb = _rank(a), _rank(b)
    if ra is None and rb is None:
        return 0
    if ra is None:
        a = 0 if rb == 0 else ("" if rb == 1 else False)
        ra = rb
    if rb is None:
        b = 0 if ra == 0 else ("" if ra == 1 else False)
        rb = ra
    if ra != rb:
        return -1 if ra < rb else 1
    if ra == 0:
        x, y = to_num(a), to_num(b)
    elif ra == 1:
        x, y = a.lower(), b.lower()
    else:
        x, y = bool(a), bool(b)
    return (x > y) - (x < y)


# ---------------------------------------------------------------------------
# wildcard / criteria
# ---------------------------------------------------------------------------
def wildcard_regex(pat):
    out = []
    i = 0
    while i < len(pat):
        ch = pat[i]
        if ch == "~" and i + 1 < len(pat) and pat[i + 1] in "*?~":
            out.append(re.escape(pat[i + 1]))
            i += 2
            continue
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$", re.S | re.I)


def has_wildcard(s):
    return any(ch in s for ch in "*?~")


_CRIT_OP = re.compile(r"^(<=|>=|<>|<|>|=)?(.*)$", re.S)


class Criteria(object):
    """COUNTIF criterion (Excel semantics, case-insensitive text)."""

    def __init__(self, crit):
        self.num = None
        self.text = None
        self.rx = None
        self.blank = False
        if isinstance(crit, Link):
            crit = crit.label
        if crit is None:
            self.op, rest = "=", ""
            self.blank = True
            self.num = 0
            self.kind = "empty_ref"
            return
        if isinstance(crit, bool):
            self.op, self.kind, self.val = "=", "bool", crit
            return
        if is_number(crit):
            self.op, self.kind, self.num = "=", "num", to_num(crit)
            return
        m = _CRIT_OP.match(crit)
        self.op = m.group(1) or "="
        rest = m.group(2)
        try:
            self.num = float(rest) if rest.strip() != "" else None
            self.kind = "num" if self.num is not None else "text"
        except ValueError:
            self.kind = "text"
        if rest.upper() in ("TRUE", "FALSE"):
            self.kind, self.val = "bool", rest.upper() == "TRUE"
        if self.kind == "text":
            self.text = rest.lower()
            if self.op in ("=", "<>") and has_wildcard(rest):
                self.rx = wildcard_regex(rest)
        self.rest = rest

    def match(self, v):
        if isinstance(v, Link):
            v = v.label
        op = self.op
        if self.kind == "empty_ref":
            return v is None or v == ""
        if self.kind == "bool":
            if isinstance(v, bool):
                return (v == self.val) if op == "=" else (v != self.val) if op == "<>" else False
            return op == "<>"
        if self.kind == "num":
            if is_number(v):
                x = to_num(v)
                y = self.num
                return {"=": x == y, "<>": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]
            if op == "<>":
                return True
            if op == "=" and isinstance(v, str):
                try:
                    return float(v) == self.num
                except ValueError:
                    return False
            return False
        # text criterion
        if op == "=":
            if self.rest == "":
                return v is None or v == ""
            if not isinstance(v, str):
                return False
            if self.rx is not None:
                return bool(self.rx.match(v))
            return v.lower() == self.text
        if op == "<>":
            if self.rest == "":
                return not (v is None or v == "")
            if not isinstance(v, str):
                return True
            if self.rx is not None:
                return not self.rx.match(v)
            return v.lower() != self.text
        if not isinstance(v, str):
            return False
        x, y = v.lower(), self.text
        return {"<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]


# ---------------------------------------------------------------------------
# evaluator
# ---------------------------------------------------------------------------
class Ctx(object):
    __slots__ = ("ev", "sheet", "row", "col", "dr", "dc")

    def __init__(self, ev, sheet, row, col, dr=0, dc=0):
        self.ev, self.sheet, self.row, self.col, self.dr, self.dc = ev, sheet, row, col, dr, dc


class Evaluator(object):
    def __init__(self, wb):
        self.wb = wb
        self.cache = {}          # (sheet, r, c) -> result
        self.compiled = {}       # formula text -> closure
        self.match_index = {}    # (sheet, c) -> {key: first row}
        self.col_cache = {}      # (sheet, c, r1, r2) -> list
        self.in_progress = set()
        self.overrides = {}      # (sheet, r, c) -> value (used for card evaluation)
        self.n_eval = 0

    # --- cells -----------------------------------------------------------
    def sheet(self, name):
        return self.wb.load_sheet(name)

    def value(self, sheet, r, c):
        key = (sheet, r, c)
        if key in self.overrides:
            return self.overrides[key]
        sh = self.sheet(sheet)
        v = sh.raw(r, c)
        if isinstance(v, Formula):
            if key in self.cache:
                return self.cache[key]
            if key in self.in_progress:
                raise XlError("#CIRC!")
            self.in_progress.add(key)
            try:
                res = self.eval_text(v.text, sheet, r, c)
            finally:
                self.in_progress.discard(key)
            self.cache[key] = res
            return res
        return v

    def cell_result(self, sheet, r, c):
        """Evaluated value of a formula cell (errors returned as XlError)."""
        return self.value(sheet, r, c)

    # --- compile / eval --------------------------------------------------
    def compile(self, text):
        fn = self.compiled.get(text)
        if fn is None:
            node = parse(text)
            fn = _compile(node)
            self.compiled[text] = fn
        return fn

    def eval_text(self, text, sheet, row, col, dr=0, dc=0):
        fn = self.compile(text)
        ctx = Ctx(self, sheet, row, col, dr, dc)
        self.n_eval += 1
        try:
            v = fn(ctx)
            if isinstance(v, Rng):
                v = scalar(ctx, v)
            return v
        except XlError as e:
            return e
        except RecursionError:
            raise

    def eval_node_fn(self, fn, sheet, row, col, dr=0, dc=0):
        ctx = Ctx(self, sheet, row, col, dr, dc)
        try:
            v = fn(ctx)
            if isinstance(v, Rng):
                v = scalar(ctx, v)
            return v
        except XlError as e:
            return e

    # --- range helpers ---------------------------------------------------
    def rng_values(self, rng):
        """Row-major flat list of evaluated values in the range."""
        sh = self.sheet(rng.sheet)
        r2 = min(rng.r2, sh.max_row)
        key = (rng.sheet, rng.r1, rng.c1, r2, rng.c2)
        cv = self.col_cache.get(key)
        if cv is not None:
            return cv
        out = []
        for r in range(rng.r1, r2 + 1):
            for c in range(rng.c1, rng.c2 + 1):
                out.append(self.value(rng.sheet, r, c))
        # NOTE: blank rows beyond the used range are not materialised (whole-column
        # refs); COUNTIF/MATCH/COUNTA never need them (no blank criteria used).
        self.col_cache[key] = out
        return out

    def match_idx(self, sheet, c, r1, r2):
        key = (sheet, c, r1, r2)
        idx = self.match_index.get(key)
        if idx is None:
            idx = {}
            sh = self.sheet(sheet)
            for r in range(r1, min(r2, sh.max_row) + 1):
                v = self.value(sheet, r, c)
                if isinstance(v, Link):
                    v = v.label
                k = _mkey(v)
                if k is not None and k not in idx:
                    idx[k] = r - r1 + 1
            self.match_index[key] = idx
        return idx


def _mkey(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return ("b", v)
    if is_number(v):
        return ("n", float(to_num(v)))
    if isinstance(v, str):
        return ("s", v.lower())
    return None


# ---------------------------------------------------------------------------
# compiler
# ---------------------------------------------------------------------------
def _sheet_of(ctx, s):
    return s if s is not None else ctx.sheet


def _compile(node):
    k = node[0]
    if k == "const":
        v = node[1]
        return lambda ctx: v
    if k == "ref":
        _, sheet, r, c, rabs, cabs = node

        def f(ctx):
            rr = r if rabs else r + ctx.dr
            cc = c if cabs else c + ctx.dc
            return Rng(_sheet_of(ctx, sheet), rr, cc, rr, cc)
        return f
    if k == "range":
        _, sheet, a, b = node

        def f(ctx):
            r1 = a[0] if a[2] else a[0] + ctx.dr
            c1 = a[1] if a[3] else a[1] + ctx.dc
            r2 = b[0] if b[2] else b[0] + ctx.dr
            c2 = b[1] if b[3] else b[1] + ctx.dc
            return Rng(_sheet_of(ctx, sheet), min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))
        return f
    if k == "cols":
        _, sheet, c1, a1, c2, a2 = node

        def f(ctx):
            s = _sheet_of(ctx, sheet)
            x1 = c1 if a1 else c1 + ctx.dc
            x2 = c2 if a2 else c2 + ctx.dc
            return Rng(s, 1, min(x1, x2), 1048576, max(x1, x2))
        return f
    if k == "rows":
        _, sheet, r1, a1, r2, a2 = node

        def f(ctx):
            s = _sheet_of(ctx, sheet)
            y1 = r1 if a1 else r1 + ctx.dr
            y2 = r2 if a2 else r2 + ctx.dr
            return Rng(s, min(y1, y2), 1, max(y1, y2), 16384)
        return f
    if k == "neg":
        inner = _compile(node[1])

        def f(ctx):
            v = inner(ctx)
            if isinstance(v, list):
                return [(-to_num(x)) if not isinstance(x, XlError) else x for x in v]
            return -to_num(scalar(ctx, v))
        return f
    if k == "pct":
        inner = _compile(node[1])
        return lambda ctx: to_num(scalar(ctx, inner(ctx))) / 100.0
    if k == "bin":
        return _compile_bin(node[1], _compile(node[2]), _compile(node[3]))
    if k == "func":
        name = node[1]
        args = [_compile(a) for a in node[2]]
        impl = FUNCS.get(name)
        if impl is None:
            raise NotImplementedError("function %s" % name)
        return lambda ctx: impl(ctx, args)
    if k == "name":
        nm = node[1]

        def f(ctx):
            raise NAME
        return f
    raise ValueError(k)


def _arr(ctx, v):
    """Value -> list if it is a multi-cell range or an array, else None."""
    if isinstance(v, list):
        return v
    if isinstance(v, Rng) and not (v.r1 == v.r2 and v.c1 == v.c2):
        return ctx.ev.rng_values(v)
    return None


def _binop(op, a, b):
    if isinstance(a, XlError):
        return a
    if isinstance(b, XlError):
        return b
    try:
        if op == "&":
            return to_text(a) + to_text(b)
        if op in ("=", "<>", "<", ">", "<=", ">="):
            c = compare(a, b)
            return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]
        x, y = to_num(a), to_num(b)
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        if op == "/":
            if y == 0:
                return DIV0
            return x / y
        if op == "^":
            return x ** y
    except XlError as e:
        return e
    raise ValueError(op)


def _compile_bin(op, fa, fb):
    def f(ctx):
        a = fa(ctx)
        b = fb(ctx)
        la, lb = _arr(ctx, a), _arr(ctx, b)
        if la is not None or lb is not None:
            if la is None:
                sa = scalar(ctx, a)
                return [_binop(op, sa, _unlink(y)) for y in lb]
            if lb is None:
                sb = scalar(ctx, b)
                return [_binop(op, _unlink(x), sb) for x in la]
            return [_binop(op, _unlink(x), _unlink(y)) for x, y in zip(la, lb)]
        r = _binop(op, scalar(ctx, a), scalar(ctx, b))
        if isinstance(r, XlError):
            raise r
        return r
    return f


def _unlink(v):
    return v.label if isinstance(v, Link) else v


# ---------------------------------------------------------------------------
# functions
# ---------------------------------------------------------------------------
def _v(ctx, fn):
    v = scalar(ctx, fn(ctx))
    if isinstance(v, XlError):
        raise v
    return v


def _values(ctx, fn):
    """All values of an argument (range -> flat list, scalar -> [v])."""
    v = fn(ctx)
    if isinstance(v, Rng):
        if v.r1 == v.r2 and v.c1 == v.c2:
            return [ctx.ev.value(v.sheet, v.r1, v.c1)]
        return ctx.ev.rng_values(v)
    if isinstance(v, list):
        return v
    return [v]


def f_if(ctx, a):
    cond = to_bool(_v(ctx, a[0]))
    if cond:
        return a[1](ctx) if len(a) > 1 else True
    if len(a) > 2:
        return a[2](ctx)
    return False


def f_iferror(ctx, a):
    try:
        v = a[0](ctx)
        if isinstance(v, Rng):
            v = scalar(ctx, v)
        if isinstance(v, XlError):
            raise v
        return v
    except XlError:
        return a[1](ctx)


def _logicals(ctx, a):
    """Logical values of AND/OR arguments (text/blank cells in references are ignored)."""
    out = []
    for fn in a:
        v = fn(ctx)
        if isinstance(v, Rng):
            if v.r1 == v.r2 and v.c1 == v.c2:
                vals = [ctx.ev.value(v.sheet, v.r1, v.c1)]
            else:
                vals = ctx.ev.rng_values(v)
            for x in vals:
                x = _unlink(x)
                if isinstance(x, XlError):
                    raise x
                if x is None or isinstance(x, str):
                    continue
                out.append(to_bool(x))
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, XlError):
                    raise x
                if x is None or isinstance(x, str):
                    continue
                out.append(to_bool(x))
        else:
            out.append(to_bool(_unlink(v)))
    if not out:
        raise VALUE
    return out


def f_and(ctx, a):
    return all(_logicals(ctx, a))


def f_or(ctx, a):
    return any(_logicals(ctx, a))


def f_not(ctx, a):
    return not to_bool(_v(ctx, a[0]))


def f_isnumber(ctx, a):
    try:
        v = scalar(ctx, a[0](ctx))
    except XlError:
        return False
    return is_number(v)


def f_istext(ctx, a):
    try:
        v = scalar(ctx, a[0](ctx))
    except XlError:
        return False
    return isinstance(v, str)


def f_isblank(ctx, a):
    try:
        v = scalar(ctx, a[0](ctx))
    except XlError:
        return False
    return v is None


def f_iserror(ctx, a):
    try:
        v = scalar(ctx, a[0](ctx))
    except XlError:
        return True
    return isinstance(v, XlError)


def f_hyperlink(ctx, a):
    target = to_text(_v(ctx, a[0]))
    if len(a) > 1:
        lab = _v(ctx, a[1])
    else:
        lab = target
    return Link(target, lab)


def f_match(ctx, a):
    look = _v(ctx, a[0])
    rng = a[1](ctx)
    mtype = 1
    if len(a) > 2:
        mtype = to_num(_v(ctx, a[2]))
    if not isinstance(rng, Rng):
        raise NA
    if mtype == 0:
        if rng.c1 == rng.c2:
            vertical = True
        elif rng.r1 == rng.r2:
            vertical = False
        else:
            raise NA
        if isinstance(look, str) and has_wildcard(look):
            rx = wildcard_regex(look)
            vals = ctx.ev.rng_values(rng)
            for i, v in enumerate(vals):
                v = _unlink(v)
                if isinstance(v, str) and rx.match(v):
                    return i + 1
            raise NA
        if vertical:
            idx = ctx.ev.match_idx(rng.sheet, rng.c1, rng.r1, rng.r2)
            k = _mkey(look)
            if k is None:
                raise NA
            pos = idx.get(k)
            if pos is None:
                raise NA
            return pos
        vals = ctx.ev.rng_values(rng)
        k = _mkey(look)
        for i, v in enumerate(vals):
            if _mkey(_unlink(v)) == k:
                return i + 1
        raise NA
    # approximate match (sorted data)
    vals = ctx.ev.rng_values(rng)
    best = None
    for i, v in enumerate(vals):
        v = _unlink(v)
        if v is None:
            continue
        c = compare(v, look)
        if mtype > 0:
            if c <= 0:
                best = i + 1
            else:
                break
        else:
            if c >= 0:
                best = i + 1
            else:
                break
    if best is None:
        raise NA
    return best


def f_index(ctx, a):
    rng = a[0](ctx)
    nargs = len(a)
    r = int(to_num(_v(ctx, a[1]))) if nargs > 1 else 0
    c = int(to_num(_v(ctx, a[2]))) if nargs > 2 else 0
    if isinstance(rng, Rng):
        if nargs == 2 and rng.r1 == rng.r2 and rng.c1 != rng.c2:
            r, c = 1, r  # single-row range: the 2nd argument is the column
        if rng.c1 == rng.c2 and c == 0:
            c = 1
        if rng.r1 == rng.r2 and r == 0:
            r = 1
        if r < 1 or c < 1:
            raise REF
        rr, cc = rng.r1 + r - 1, rng.c1 + c - 1
        if rr > rng.r2 or cc > rng.c2:
            raise REF
        return Rng(rng.sheet, rr, cc, rr, cc)
    if isinstance(rng, list):
        if r < 1 or r > len(rng):
            raise REF
        return rng[r - 1]
    raise VALUE


def f_countif(ctx, a):
    rng = a[0](ctx)
    crit_v = a[1](ctx)
    vals = _values_rng(ctx, rng)
    crit_list = _arr(ctx, crit_v)
    if crit_list is not None:
        # array criteria, e.g. SUMPRODUCT(1/COUNTIF(P,P)) distinct count
        out = []
        counts = None
        for cv in crit_list:
            cv = _unlink(cv)
            plain = isinstance(cv, str) and cv != "" and not has_wildcard(cv) and not _CRIT_OP.match(cv).group(1)
            if plain:
                if counts is None:
                    counts = {}
                    for v in vals:
                        v = _unlink(v)
                        if isinstance(v, str):
                            k = v.lower()
                            counts[k] = counts.get(k, 0) + 1
                out.append(counts.get(cv.lower(), 0))
            else:
                cr = Criteria(cv)
                out.append(sum(1 for v in vals if cr.match(v)))
        return out
    cr = Criteria(scalar(ctx, crit_v))
    return sum(1 for v in vals if cr.match(v))


def _values_rng(ctx, rng):
    if isinstance(rng, Rng):
        return ctx.ev.rng_values(rng)
    if isinstance(rng, list):
        return rng
    return [rng]


def f_countifs(ctx, a):
    pairs = []
    n = None
    for i in range(0, len(a), 2):
        vals = _values_rng(ctx, a[i](ctx))
        cr = Criteria(scalar(ctx, a[i + 1](ctx)))
        if n is None:
            n = len(vals)
        elif len(vals) != n:
            raise VALUE
        pairs.append((vals, cr))
    cnt = 0
    for j in range(n or 0):
        ok = True
        for vals, cr in pairs:
            if not cr.match(vals[j]):
                ok = False
                break
        if ok:
            cnt += 1
    return cnt


def f_counta(ctx, a):
    n = 0
    for fn in a:
        v = fn(ctx)
        if isinstance(v, Rng):
            if v.r1 == v.r2 and v.c1 == v.c2:
                vals = [ctx.ev.sheet(v.sheet).raw(v.r1, v.c1)]
            else:
                sh = ctx.ev.sheet(v.sheet)
                vals = []
                for r in range(v.r1, min(v.r2, sh.max_row) + 1):
                    row = sh.rows.get(r)
                    if row is None:
                        continue
                    vals.extend(row[v.c1 - 1:v.c2])
            n += sum(1 for x in vals if x is not None)
        elif isinstance(v, list):
            n += sum(1 for x in v if x is not None)
        else:
            n += 0 if v is None else 1
    return n


def f_count(ctx, a):
    n = 0
    for fn in a:
        for v in _values(ctx, fn):
            if is_number(_unlink(v)):
                n += 1
    return n


def _nums(ctx, a):
    out = []
    for fn in a:
        v = fn(ctx)
        if isinstance(v, Rng) and not (v.r1 == v.r2 and v.c1 == v.c2):
            for x in ctx.ev.rng_values(v):
                x = _unlink(x)
                if isinstance(x, XlError):
                    raise x
                if is_number(x):
                    out.append(to_num(x))
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, XlError):
                    raise x
                if is_number(x):
                    out.append(to_num(x))
        else:
            x = scalar(ctx, v)
            if isinstance(x, XlError):
                raise x
            if x is None:
                continue
            out.append(to_num(x))
    return out


def f_sum(ctx, a):
    return sum(_nums(ctx, a))


def f_average(ctx, a):
    xs = _nums(ctx, a)
    if not xs:
        raise DIV0
    return sum(xs) / len(xs)


def f_min(ctx, a):
    xs = _nums(ctx, a)
    return min(xs) if xs else 0


def f_max(ctx, a):
    xs = _nums(ctx, a)
    return max(xs) if xs else 0


def f_sumproduct(ctx, a):
    arrays = []
    for fn in a:
        v = fn(ctx)
        l = _arr(ctx, v)
        if l is None:
            l = [scalar(ctx, v)]
        arrays.append(l)
    n = len(arrays[0])
    total = 0
    for j in range(n):
        p = 1
        for arr in arrays:
            x = _unlink(arr[j])
            if isinstance(x, XlError):
                raise x
            p *= x if is_number(x) and not isinstance(x, (dt.datetime, dt.date)) else (to_num(x) if is_number(x) else 0)
        total += p
    return total


def _round_half_away(x, n):
    """Excel ROUND: half away from zero, on the 15-significant-digit decimal value."""
    m = 10.0 ** n
    y = float("%.15g" % (abs(x) * m))
    r = math.floor(y + 0.5) / m
    r = float("%.15g" % r)
    return math.copysign(r, x) if r != 0 else 0.0


def f_round(ctx, a):
    x = to_num(_v(ctx, a[0]))
    n = int(to_num(_v(ctx, a[1]))) if len(a) > 1 else 0
    r = _round_half_away(x, n)
    if n <= 0:
        r = float(int(r)) if abs(r) < 1e15 else r
        return int(r) if float(r).is_integer() else r
    return r


def f_int(ctx, a):
    return math.floor(to_num(_v(ctx, a[0])))


def f_abs(ctx, a):
    return abs(to_num(_v(ctx, a[0])))


def f_trim(ctx, a):
    s = to_text(_v(ctx, a[0]))
    return re.sub(" +", " ", s.strip(" "))


def f_upper(ctx, a):
    return to_text(_v(ctx, a[0])).upper()


def f_lower(ctx, a):
    return to_text(_v(ctx, a[0])).lower()


def f_left(ctx, a):
    s = to_text(_v(ctx, a[0]))
    n = int(to_num(_v(ctx, a[1]))) if len(a) > 1 else 1
    if n < 0:
        raise VALUE
    return s[:n]


def f_right(ctx, a):
    s = to_text(_v(ctx, a[0]))
    n = int(to_num(_v(ctx, a[1]))) if len(a) > 1 else 1
    if n < 0:
        raise VALUE
    return s[-n:] if n else ""


def f_mid(ctx, a):
    s = to_text(_v(ctx, a[0]))
    st = int(to_num(_v(ctx, a[1])))
    n = int(to_num(_v(ctx, a[2])))
    if st < 1 or n < 0:
        raise VALUE
    return s[st - 1:st - 1 + n]


def f_len(ctx, a):
    return len(to_text(_v(ctx, a[0])))


def f_substitute(ctx, a):
    s = to_text(_v(ctx, a[0]))
    old = to_text(_v(ctx, a[1]))
    new = to_text(_v(ctx, a[2]))
    if len(a) > 3:
        inst = int(to_num(_v(ctx, a[3])))
        if old == "":
            return s
        idx = -1
        for _ in range(inst):
            idx = s.find(old, idx + 1)
            if idx < 0:
                return s
        return s[:idx] + new + s[idx + len(old):]
    if old == "":
        return s
    return s.replace(old, new)


def f_search(ctx, a):
    find = to_text(_v(ctx, a[0]))
    within = to_text(_v(ctx, a[1]))
    start = int(to_num(_v(ctx, a[2]))) if len(a) > 2 else 1
    if start < 1 or start > len(within) + 1:
        raise VALUE
    if has_wildcard(find):
        rx = wildcard_regex(find)
        pat = re.compile(rx.pattern[1:-1], re.S | re.I)
        m = pat.search(within, start - 1)
        if not m:
            raise VALUE
        return m.start() + 1
    i = within.lower().find(find.lower(), start - 1)
    if i < 0:
        raise VALUE
    return i + 1


def f_find(ctx, a):
    find = to_text(_v(ctx, a[0]))
    within = to_text(_v(ctx, a[1]))
    start = int(to_num(_v(ctx, a[2]))) if len(a) > 2 else 1
    i = within.find(find, start - 1)
    if i < 0:
        raise VALUE
    return i + 1


def _ymd(v):
    """Excel serial / date -> (year, month, day); serial 0 is 1900-01-00."""
    if isinstance(v, dt.datetime) or isinstance(v, dt.date):
        return v.year, v.month, v.day
    x = to_num(v)
    if x < 0:
        raise NUM
    if x < 1:
        return 1900, 1, 0
    from openpyxl.utils.datetime import from_excel
    d = from_excel(math.floor(x))
    return d.year, d.month, d.day


def f_year(ctx, a):
    return _ymd(_v(ctx, a[0]))[0]


def f_month(ctx, a):
    return _ymd(_v(ctx, a[0]))[1]


def f_day(ctx, a):
    return _ymd(_v(ctx, a[0]))[2]


def f_date(ctx, a):
    y = int(to_num(_v(ctx, a[0])))
    m = int(to_num(_v(ctx, a[1])))
    d = int(to_num(_v(ctx, a[2])))
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    base = dt.datetime(y, m, 1) + dt.timedelta(days=d - 1)
    return int(to_excel(base))


def f_value(ctx, a):
    return to_num(_v(ctx, a[0]))


def f_concat(ctx, a):
    return "".join(to_text(_v(ctx, fn)) for fn in a)


def f_true(ctx, a):
    return True


def f_false(ctx, a):
    return False


FUNCS = {
    "IF": f_if, "IFERROR": f_iferror, "AND": f_and, "OR": f_or, "NOT": f_not,
    "ISNUMBER": f_isnumber, "ISTEXT": f_istext, "ISBLANK": f_isblank, "ISERROR": f_iserror,
    "HYPERLINK": f_hyperlink, "MATCH": f_match, "INDEX": f_index,
    "COUNTIF": f_countif, "COUNTIFS": f_countifs, "COUNTA": f_counta, "COUNT": f_count,
    "SUM": f_sum, "SUMPRODUCT": f_sumproduct, "AVERAGE": f_average, "MIN": f_min, "MAX": f_max,
    "ROUND": f_round, "INT": f_int, "ABS": f_abs,
    "TRIM": f_trim, "UPPER": f_upper, "LOWER": f_lower, "LEFT": f_left, "RIGHT": f_right, "MID": f_mid,
    "LEN": f_len, "SUBSTITUTE": f_substitute, "SEARCH": f_search, "FIND": f_find,
    "YEAR": f_year, "MONTH": f_month, "DAY": f_day, "DATE": f_date, "VALUE": f_value,
    "CONCATENATE": f_concat, "TRUE": f_true, "FALSE": f_false,
}
