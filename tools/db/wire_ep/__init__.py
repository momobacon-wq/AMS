# -*- coding: utf-8 -*-
r"""tools/db/wire_ep — 接線路徑的「電氣盤那一跳」（v16，給 wire_ge.py 用）：接線圖上 JB 或盤那一端是發電機保護盤、手動同步盤、
GCB 低壓箱、UAT 就地箱、LCI 中壓盤／52ET 時，到那份設備圖上框出端子（或隔間）。

== 六類（GROUPS，依序）==
  gpp_gt  燃機 GPP（G1xMKY40UC001／UC002）   GE 140T1264＝HT0-1-EGJ01-D0023（六台燃機共用）       端子排＋端子表那一列
  gpp_st  汽機 GPP（S10MKY40UC001／UC002）    GE 140T1267＝HT0-1-EGK01-D0018                     端子排＋端子表那一列
  msp     手動同步盤（xxxCCS01UC001）         G11：EOMR HT1-1-AQB01-Q1980 裡的 226B4841；S10：檔名含 'C086A LAYOUT AND ELECTRICAL DIAGRAM'
                                             的 226B4843 rev02；G12 借 G11 的圖（類比，52L1↔52L3）     背視圖格子＋端子圖表那一列
  gcb     GCB 低壓箱（G1xMSC20XD512）          GE Grid VS332679EDD01D＝HT0-1-EGJ01-D0066（每台共用）  低壓箱配置圖端子塊＋端子表那一欄
  uat     UAT 就地箱（C[123]0B[BC]T10）       Fortune 21A3D3014＝HT0-1-ETE01-D1030（六台共用）       端子格＋端子排
  mv      LCI 中壓盤 G1xMBJ10UC200／52ET G1xMKC10QA101   D0037（G11）／D0052（G12）／D0035（52ET，共用）   只到隔間（level 'cmp'）
每個子模組是探勘版的移植（演算法、門檻照舊），只用 stdlib＋fitz；各自有 build(paths)、key_of、locate、missing。

== 用法（wire_ge.py）==
  for doc_key, how, value in doc_specs():   # how＝'docno'（完整文件號，resolve_doc）或 'title'（檔名片段，resolve_fragment）
  ix = build_indexes({doc_key: 絕對路徑, …})      # 每類只開一次各自的 PDF；缺圖的類是 None
  g = group_of(unit, jb + jb_desc + jb_kks) 或 group_of(unit, panel + panel_desc)
  hits = locate(ix, g, entry, cond)；why = missing(ix, g, entry, cond)
  entry：unit、end（'jb'／'panel'＝要框的是哪一端）、jb、jb_desc、jb_tb、panel、panel_tb、cond（整條電纜的芯，UAT 修筆誤用）；
  cond：core、jb_term、panel_board、panel_tb、panel_num。
  hit：{doc_key, page（1 起）, box [x0,y0,x1,y1]（未轉的 PDF 座標）, kind 'strip'／'term'／'row'／'cmp', label（圖上印的短字）,
        primary（卡片要畫的框）, extra}。extra 依類別保留探勘時抓到的：線號、LOCATION、表頭、訊號、來源框、analog／generic／approx／whole 等旗標。
  missing：找不到端子（或隔間）的原因（卡片註記用）；找得到回 None。
"""
import re
from collections import OrderedDict

from . import gcb, gpp_gt, gpp_st, msp, mv, uat

# 文件鍵 → (找法, 值, 一份圖是否多台共用, 圖名)；找法 'docno'＝完整文件號、'title'＝檔名片段（不分大小寫的子字串）
DOCS = OrderedDict([
    ('epgg', ('docno', 'HT0-1-EGJ01-D0023', True, '燃機 GPP 配置圖 GE 140T1264')),
    ('epgs', ('docno', 'HT0-1-EGK01-D0018', True, '汽機 GPP 配置圖 GE 140T1267')),
    ('epm1', ('docno', 'HT1-1-AQB01-Q1980', False, 'G11 手動同步盤 EOMR（226B4841 rev04）')),
    ('epms', ('title', 'C086A LAYOUT AND ELECTRICAL DIAGRAM', True, 'S10 手動同步盤面板圖（226B4843 rev02）')),
    ('epgc', ('docno', 'HT0-1-EGJ01-D0066', True, 'GCB 接線圖 VS332679EDD01D')),
    ('epua', ('docno', 'HT0-1-ETE01-D1030', True, 'UAT 就地箱接線圖 21A3D3014')),
    ('epv1', ('docno', 'HT0-1-EGJ01-D0037', True, 'G11 LCI 中壓盤配置圖')),
    ('epv2', ('docno', 'HT0-1-EGJ01-D0052', True, 'G12 LCI 中壓盤配置圖')),
    ('epbr', ('docno', 'HT0-1-EGJ01-D0035', True, '52ET 斷路器配置圖')),
])

# 文件鍵 → 卡片上加註的版次狀態（查核時對過正式版；正式版是掃描圖、框不了，所以框在向量版上）
DOC_NOTE = {
    'epgs': 'GE 出廠圖（AS-SHIPPED，HT0 全廠共用編號），不是 S10 竣工圖',
    'epm1': 'EOMR 內附的向量圖蓋有 DRAFT 浮水印；正式版是 HT0-1-EGJ01-D0071（封面 226B4841 Revision 04、2025-08-01，GT11 與 GT21 共用，掃描圖），用到的端子與訊號相同',
    'epms': '向量版 rev02；正式版是 HT0-1-EGK01-D0048（封面 226B4843 Revision 04、2025-08-01，掃描圖），端子相同，rev02 的 GPP 來源框在 rev04 已拿掉',
    'epua': '檔名寫 UNIT MAIN TRANSFORMER，實為 UAT 圖；Fortune Rev.5（2025-12-24），客戶文件號 HT0-1-ETE01-D1030',
    'epv1': 'GTG#11／#21／#31 共用一份；只到隔間，端子號只出自接線圖 D1004',
    'epv2': 'GTG#12／#22／#32 共用一份；只到隔間，端子號只出自接線圖 D1004',
    'epbr': '只到隔間，端子號只出自接線圖 D1004',
}

# 類 → 用到的文件鍵、子模組、層級（'term' 端子／'cmp' 只到隔間）、generic（一份圖多台共用；mv 只有 52ET 那份共用，記在 DOCS 與 hit 的 extra.generic）
GROUPS = OrderedDict([
    ('gpp_gt', {'docs': ('epgg',), 'module': gpp_gt, 'level': 'term', 'generic': True, 'zh': '燃機發電機保護盤（GPP）'}),
    ('gpp_st', {'docs': ('epgs',), 'module': gpp_st, 'level': 'term', 'generic': False, 'zh': '汽機發電機保護盤（GPP）'}),
    ('msp', {'docs': ('epm1', 'epms'), 'module': msp, 'level': 'term', 'generic': False, 'zh': '手動同步盤（MSP）'}),
    ('gcb', {'docs': ('epgc',), 'module': gcb, 'level': 'term', 'generic': True, 'zh': '發電機斷路器低壓箱（GCB）'}),
    ('uat', {'docs': ('epua',), 'module': uat, 'level': 'term', 'generic': True, 'zh': '廠用變壓器就地控制箱（UAT）'}),
    ('mv', {'docs': ('epv1', 'epv2', 'epbr'), 'module': mv, 'level': 'cmp', 'generic': False, 'zh': 'LCI 中壓開關盤／52ET 斷路器'}),
])
for _g in GROUPS.values():
    _g['specs'] = tuple((k,) + DOCS[k][:2] for k in _g['docs'])

# 卡片「對應方式」用：類 → (圖名, 方法)
DESC = {
    'gpp_gt': ('燃機發電機保護盤配置圖 GE 140T1264（HT0-1-EGJ01-D0023，六台燃機共用一份）',
               '配置圖上框端子排（引線末端所指的那一段軌道或子盤上那一排；BAY-3 是 AUX 盤，標籤沒印 (A)），'
               '端子表（13A–13E）框這一號那一列，附原理圖頁區與線號'),
    'gpp_st': ('汽機發電機保護盤配置圖 GE 140T1267（HT0-1-EGK01-D0018）',
               '配置圖上框端子排標籤（含塊數）與引線末端，端子表框這一號那一列，附原理圖頁區與線號'),
    'msp': ('手動同步盤面板圖：G11 用 EOMR HT1-1-AQB01-Q1980 裡的 226B4841 rev04，S10 用 226B4843 rev02（正式版 rev04 是掃描圖），'
            'G12 沒有向量圖、借 G11 的',
            '背視圖上數格子框這一號端子，端子圖表框那一列（原理圖那一欄的訊號名、燈／按鈕與來源框是定位時核對用，卡上沒有列）'),
    'gcb': ('燃機發電機斷路器接線圖 GE Grid VS332679EDD01D rev09（HT0-1-EGJ01-D0066，每台共用一份）',
            '低壓箱配置圖（LVC）上框印著這個號碼的端子塊（同一號有幾格並接時框整組；端子表 TER 那一欄有原理圖參照與上下兩側接到哪，卡上沒有框）'),
    'uat': ('廠用變壓器就地控制箱接線圖 Fortune 21A3D3014 rev 5（HT0-1-ETE01-D1030，六台共用一份）',
            'CT 接線圖（p.19）或端子圖（p.21）上框這一號的格子，箱內配置圖（p.3）上框端子排'),
    'mv': ('LCI 中壓開關盤配置圖（G11 HT0-1-EGJ01-D0037、G12 D0052）與 52ET 斷路器配置圖（D0035，每台共用）',
           '只到隔間：正視圖、內部正視圖、低壓箱上框 -A01／-A02／-A03；接線圖沒寫隔間的框整面盤'),
}

_GT_UNIT = re.compile(r'^G\d\d$')


def doc_specs():
    """→ [(doc_key, how, value)]；how＝'docno'（完整文件號）或 'title'（檔名片段）。"""
    return [(k, v[0], v[1]) for k, v in DOCS.items()]


def group_of(unit, text):
    """JB 端（jb＋jb_desc＋jb_kks）或盤端（panel＋panel_desc）的文字 → 類或 None（看盤的 KKS）。"""
    t = re.sub(r'\s+', '', (text or '').upper())
    u = (unit or '').upper()
    gt = bool(_GT_UNIT.match(u))
    if re.search(r'MKY40UC00[12]', t):
        return 'gpp_st' if u == 'S10' else ('gpp_gt' if gt else None)
    if 'CCS01UC001' in t:
        return 'msp' if u in ('G11', 'G12', 'S10') else None
    if 'MSC20XD512' in t:
        return 'gcb' if gt else None
    if re.search(r'C[123]0B[BC]T10', t):
        return 'uat' if gt else None
    if re.search(r'MBJ10UC200|MKC10QA101', t):
        return 'mv' if gt else None
    return None


def resolve_fragment(lib, frag, copy_flags=None, rev_rank=None, skip=('old', 'copy_path', 'collection', 'dossier')):
    """檔名片段（不分大小寫）→ 文件庫裡的那份 PDF {doc, rel, size, mtime, rev, title, alts} 或 {why}（形狀同 wire_ge.resolve_title）。
    lib＝[(相對路徑, 大小, 修改時間)]（pid_lib.walk_pdfs）；copy_flags／rev_rank 傳 pid_lib 的同名函式時，規則同 resolve_doc：
    排除副本旗標、取最高版次（檔名 '_revX'），同版取不像重複下載、路徑短的。"""
    cs = []
    for rel, size, mtime in lib:
        base = rel.rsplit('/', 1)[-1]
        if frag.upper() in base.upper():
            m = re.search(r'_rev([A-Za-z0-9]{0,3})[-.]*\.pdf$', base, re.I)
            cs.append((rel, size, mtime, (m.group(1) if m else '').upper()))
    if not cs:
        return {'why': '文件庫裡沒有檔名含「%s」的 PDF' % frag}
    flags = copy_flags or (lambda rel: [])
    pool = [c for c in cs if not set(flags(c[0])) & set(skip)] or cs
    rank = rev_rank or (lambda rev: 0)
    top = max(rank(c[3]) for c in pool)
    rel, size, mtime, rev = min((c for c in pool if rank(c[3]) == top), key=lambda c: ('dupname' in flags(c[0]), len(c[0]), c[0]))
    return {'doc': '', 'rel': rel, 'size': size, 'mtime': mtime, 'rev': rev, 'title': '', 'alts': len(cs) - 1}


def build_indexes(paths_by_doc_key, groups=None):
    """{doc_key: 絕對路徑} → {類: 索引或 None}；每類只開一次各自的 PDF。groups 限定只建哪幾類。"""
    ix = {}
    for g, d in GROUPS.items():
        if groups and g not in groups:
            continue
        have = {k: paths_by_doc_key[k] for k in d['docs'] if paths_by_doc_key.get(k)}
        ix[g] = d['module'].build(have) if have else None
    return ix


def locate(ix, group, entry, cond):
    """→ [hit]（見檔頭）；不屬於任何類、或那一類的圖不在文件庫時回 []。"""
    if group not in GROUPS or not ix.get(group):
        return []
    return GROUPS[group]['module'].locate(ix[group], entry, cond)


def missing(ix, group, entry, cond):
    """找不到端子（mv：隔間）的原因；找得到回 None。"""
    if group not in GROUPS:
        return '沒有對應的設備圖'
    if not ix.get(group):
        return '%s 的圖不在文件庫' % GROUPS[group]['zh']
    return GROUPS[group]['module'].missing(ix[group], entry, cond)
