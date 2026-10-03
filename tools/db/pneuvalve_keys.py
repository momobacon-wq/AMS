# -*- coding: utf-8 -*-
"""pneuvalve_keys.py — 氣動閥清單每一列「工程師可能會打的識別碼」（pneuvalve_site.py 用來建 02.json valve.index／valve.list）。

valve_keys(row, list_cores, merged_alias) → [(顯示字串, family)]，row＝{欄名: 儲存格文字}。family：
  tag／tag-unit   清單位號、依涵蓋機組展開的位號
  core            去掉機組的 RDS-PP 核心（MBP70QN222）與 GE 閥清單寫法 XX／YY＋核心
  ge-dev／ge-dev-90   Legacy/GE Tag 欄的 GE 器件號（VA13-25、VGST-2）與 90＋器件號
  loop-dev        迴路號（LCV-3461、TCV-260、EV1）
  mk6e-dev／mk6e-stem／mk6e-name   Mark VIe 器件名（20SSV-3B → SSV-3B；HPEV）
  ge-kks／ge-kks-core   標了 (GE KKS) 的 11LBF54AA004 與去機組碼 LBF54AA004
  acc-dev／acc-isa／acc-kks／acc-drift   SOV／LS／定位器欄裡屬於這顆閥的附件位號（20VG8、LY-3461、先導 SOV 專屬位號…）
  vendor-tag／alias   出廠 tag、刪除紀錄裡併入本列的別名位號
  vendor          V1～V4／IGV／UVT：多列共用的廠商代號 → 只當建議，不當精確命中（WEAK）
機組前綴的寫法（G11_90VA13-25、G11_VA13-25、S10_LCV-3461）不存：前端去掉 <機組>(_)(90) 後再查同一張索引。
查無／待查／N/A／無(…) 開頭的儲存格是敘述，不取任何 token；備註、序號欄不取（會指到別顆閥）。
規則與 93 筆查詢案例來自 2026-10-03 的識別碼盤點（fill26/pneuvalve_search_audit.md）。
"""
import re

TAG, COV, LEG = 'Valve Tag No.', '涵蓋機組', 'Legacy/GE Tag'
SOV, LS, POS, AFR, ACC = 'SOV 電磁閥(型號/電壓/位號)', 'Limit Switch/位置回授', 'Positioner 定位器', 'AFR 過濾減壓閥', '其他附件'


def norm(q):      # == core.js IX.norm
    return re.sub(r'\s+', ' ', str(q or '').replace('=', '')).strip().upper()


def compact(q):   # == core.js IX.compact / pneuvalve_site.compact
    return re.sub(r'[^A-Z0-9]', '', norm(q))


def expand_units(tag, cov):   # copy of pneuvalve_site.expand_units
    t = str(tag).strip().upper()
    m = re.match(r'([GCS])(XX|X0)(.*)$', t)
    if m:
        us = [u for u in re.findall(r'[GCS]\d\d', str(cov or '').upper()) if u[0] == m.group(1)]
        return [(u, u + m.group(3)) for u in us]
    m = re.match(r'((?:[GCS]\d\d/)+[GCS]\d\d)(.+)$', t)
    if m:
        return [(u, u + m.group(2)) for u in m.group(1).split('/')]
    return [(t[:3], t)]


def core_of(tag):             # GxxMBP70QN222 / G11/G12HSD11QM001 / C00GBN77QM061 -> MBP70QN222
    t = str(tag).strip().upper()
    m = re.match(r'(?:[GCS](?:XX|X0|\d\d)/?)+(.+)$', t)
    return m.group(1) if m else t


# ---------------------------------------------------------------- token shapes
RE_VTAG = re.compile(r'V[A-Z]{0,3}\d{0,2}[A-Z]?-\d{1,2}[A-Z]?$')            # VA13-25 VA13T-1 VS4-4 VAS-10 VGST-2 VA46-1A VA2-1
RE_LOOP = re.compile(r'[A-Z]{2,3}-\d{2,4}[A-Z]?$')                          # LCV-3461 DCV-2996B TCV-260 FV-81
RE_EV = re.compile(r'[A-Z]{2,5}\d?$')                                       # EV1 EV2 HPEV IGV UVT (classified below)
RE_MK6DEV = re.compile(r'(\d{2})([A-Z]{2,5}(?:-\d{1,2}[A-Z]?)?)$')          # 20SSV-3B 33SSV-3B 20HABV 20WSV
RE_GEKKS = re.compile(r'(?<![A-Z0-9])(\d{2})([A-Z]{3}\d{2}AA\d{3})(?![A-Z0-9])')
RE_SOVDEV = re.compile(r'\d{2}[A-Z]{2,5}-?\d{1,2}[A-Z]?$')                  # whole SOV cell: 20VG8 20VG-1 20VGS-1
RE_ISA = re.compile(r'(?<![A-Z0-9\-])(LY|FY|ZT|ZS|PCV)-(\d{3,4})((?:[A-Z](?:/[A-Z])*)?)((?:/\d{3,4})*)(?![A-Z0-9])')
KKS_FULL = r'[GCS](?:\d\d|[Xx][Xx]|[Xx]0)[A-Z]{3}\d{2}[A-Z]{2}\d{3}'
RE_SOVKKS = re.compile(r'SOV\s*=?\s*(?:專屬位號|獨立位號|獨立tag)?\s*=?\s*(' + KKS_FULL + r')((?:/\d{3})*)'
                       r'|SOV [^;；()]{0,60}\(=(' + KKS_FULL + r')\)')
RE_DRIFT = re.compile(r'(?<![A-Z0-9])([A-Z]{3}\d{2}[A-Z]{2}\d{3})-(?:KH|MB|BG)\d\d')   # A0102 XDT01QN001-KH01 (儀器清單位號漂移)
NEG_HEAD = re.compile(r'^\s*(查無|待查|N/?A|N\.A\.|無\(|—|-+$|$)')
VENDOR = {'IGV', 'UVT'}


def legacy_keys(cell):
    """Legacy/GE Tag cell -> [(token, family)]
    families: ge-dev, loop-dev, mk6e-dev, mk6e-name, ge-kks, vendor, vendor-tag, acc-dev"""
    s = str(cell or '').strip()
    out = []
    if NEG_HEAD.match(s):
        return out                                                    # 查無/待查/N/A/無(…): prose only, never mined
    if s.startswith('無Legacy'):                                      # only explicit Mark VIe anchors
        m = re.search(r'Mark VIe 器件名\s*([0-9A-Z\-]+(?:\s*/\s*[0-9A-Z\-]+)*)', s)
        if m:
            out += [(t.strip(), 'mk6e-dev') for t in m.group(1).split('/')]
        m = re.search(r'Mark VIe 名\s*([A-Z][A-Z0-9_]{2,})', s)
        if m:
            out.append((m.group(1), 'mk6e-name'))
        return out
    if '(GE KKS)' in s:                                               # 11LBF55AA001 … (row1879 / ALF01 / G11/G21 never match)
        return [(a + b, 'ge-kks') for a, b in RE_GEKKS.findall(s)]
    if '出廠tag' in s:
        m = re.match(r'([A-Z]{3}\d{2}[A-Z]{2}\d{3})', s)
        return [(m.group(1), 'vendor-tag')] if m else []
    m = re.search(r'trip SOV\s+(\d{2}[A-Z]{2,5}-[A-Z0-9]+)', s)
    if m:
        out.append((m.group(1), 'acc-dev'))
    head = re.split(r'[(（;；\[]', s, maxsplit=1)[0]
    for t in (x.strip() for x in head.split(' / ')):
        if not t or not re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9]+)*', t):
            continue                                                  # anything with spaces/CJK left in the head -> rejected
        if re.fullmatch(r'V\d', t) or t in VENDOR:
            out.append((t, 'vendor'))
        elif RE_VTAG.match(t):
            out.append((t, 'ge-dev'))
        elif RE_MK6DEV.match(t):
            out.append((t, 'mk6e-dev'))
        elif RE_LOOP.match(t):
            out.append((t, 'loop-dev'))
        elif RE_EV.match(t):
            out.append((t, 'loop-dev' if re.search(r'\d$', t) else 'mk6e-name'))
    return out


def accessory_keys(row):
    out = []
    sv = str(row.get(SOV) or '').strip()
    if RE_SOVDEV.fullmatch(sv):
        out.append((sv, 'acc-dev'))
    for col in (SOV, LS, POS, AFR, ACC):
        txt = str(row.get(col) or '')
        if re.match(r'^\s*(查無|待查)', txt):
            continue
        for p, n, suf, more in RE_ISA.findall(txt):
            nums = [n] + [x for x in more.split('/') if x]
            sufs = [x for x in suf.split('/') if x] or ['']
            for nn in nums:
                for ss in sufs:
                    out.append(('%s-%s%s' % (p, nn, ss), 'acc-isa'))
                if suf:
                    out.append(('%s-%s' % (p, nn), 'acc-isa'))
        if col in (SOV, POS, ACC):
            for a, more, b in RE_SOVKKS.findall(txt):
                base = a or b
                out.append((base, 'acc-kks'))
                for x in [y for y in more.split('/') if y]:
                    out.append((base[:-3] + x, 'acc-kks'))
        if col == POS:
            for c in RE_DRIFT.findall(txt):
                out.append((c, 'acc-drift'))
    return out


def valve_keys(row, list_cores=frozenset(), merged_alias=()):
    """-> ordered, de-duplicated [(key_display, family)] for one valve row.
    list_cores: compact cores of ALL list tags (an alias equal to another row's own tag is dropped -> 'see also', not a key).
    merged_alias: tags from sheet v2.6刪除紀錄 (類別 含『別名』) whose 併入列 == this row's tag."""
    tag, cov = str(row.get(TAG) or '').strip(), row.get(COV)
    units = expand_units(tag, cov)
    core = core_of(tag)
    keys = [(tag, 'tag')] + [(t, 'tag-unit') for _, t in units if t != tag.upper()]
    keys.append((core, 'core'))
    if tag[:1].upper() == 'G':
        keys.append(('XX' + core, 'core'))                           # GE valve list spelling XXMBP70QN222
    if tag[:1].upper() == 'S':
        keys.append(('YY' + core, 'core'))
    ulist = [u for u, _ in units]
    for t, fam in legacy_keys(row.get(LEG)):
        if fam == 'ge-dev':
            keys.append((t, fam))
            keys.append(('90' + t, 'ge-dev-90'))
        elif fam == 'loop-dev':
            keys.append((t, fam))
        elif fam == 'mk6e-dev':
            keys.append((t, fam))
            keys.append((RE_MK6DEV.match(t).group(2), 'mk6e-stem'))
        elif fam == 'ge-kks':
            keys.append((t, fam))
            keys.append((t[2:], 'ge-kks-core'))
        elif fam == 'vendor-tag':
            if compact(t) not in list_cores:
                keys.append((t, fam))
        else:
            keys.append((t, fam))
    for t, fam in accessory_keys(row):
        if fam == 'acc-kks':
            if compact(core_of(t)) in list_cores:
                continue
            m = re.match(r'([GCS])(?:XX|X0)(.*)$', t, re.I)
            if m:
                keys += [(u + m.group(2), fam) for u in ulist if u[0] == m.group(1).upper()]
            keys.append((t, fam))
        elif fam == 'acc-drift':
            if compact(t) in list_cores or compact(t) == compact(core):
                continue
            keys.append((t, fam))
            keys += [(u + t, fam) for u in ulist]
        else:
            keys.append((t, fam))
    for a in merged_alias:
        keys.append((a, 'alias'))
        keys += [(t, 'alias') for _, t in expand_units(a, cov)]
        keys.append((core_of(a), 'alias'))
    seen, out = set(), []
    for k, f in keys:
        c = compact(k)
        if len(c) < 2 or c in seen:
            continue
        seen.add(c)
        out.append((k, f))
    return out


WEAK = {'vendor'}                      # V1..V4 / IGV / UVT：只當建議
