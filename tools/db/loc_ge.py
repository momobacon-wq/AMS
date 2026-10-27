# -*- coding: utf-8 -*-
r"""tools/db/loc_ge.py — 位置圖定位（GE 原廠編號版，v12）：GE 編號（CT-DA-2、TT-WR-3B、MAC20BP031 的汽機壓力開關…）→ GE 清單「位置圖」欄
列的那幾份圖（配置圖、電纜槽、導管總成、儀器總成、發電機輔機外型圖）上的哪一頁、圖上的哪個位置。

為什麼需要：GE 儀器清單（End User Template A0102 rev C 等）每顆元件有一欄 Location（例 CT-DA-2 → HT0-1-GZD01-M0147、HT0-1-GZD01-M0166），
告訴你「去哪幾張圖找它」，但不告訴你在圖上哪裡。查詢卡的 GE 編號卡已有 P&ID（pid_ge.py）與圖控（hmi_ge.py）位置；本檔補第三種：
位置圖上指著元件本體的引線標註，讓卡片像 P&ID 一樣直接框出來。**規則盡量重用 pid_lib／pid_ge**（文字層快取、轉正角、圖框分區、
GE 標籤的寫法展開、清單欄判定），本檔只加位置圖特有的幾件事。

== 文件集 ==
  GE 對照表（paths.GE_TAGS）每個條目 spec[].f 的 location 欄（build_card_aux.ge_ld_listed：'HT0-1-GZD01-M0166' → 'GZD01-M0166'；
  GE 圖號 307T1798 這種原樣）＝**這份圖被 GE 清單點名為某些元件的位置圖**。全部點名過的文件號就是文件集
  （ELECTRICAL ELEMENTARY 接線圖不收：接線圖上的編號是端子與電纜，不是元件的位置）。另加 EXTRA_DOCS 明列的 6 份
  （普查逐份看圖確認有元件引線、上面的條目沒有任何位置圖；不用標題正規式自動擴大）。
  每個文件號 → 文件庫裡檔名以它開頭的 PDF：排除副本／舊版／彙編／設備 dossier 夾（pid_lib.copy_flags 的 old／copy_path／collection／
  dossier；全被排除時才退用），取最高版次（pid_lib.rev_rank：數字版 > 字母版），同版取檔名不像重複下載、路徑短的。GE 圖號（307T1798）
  先比檔名裡的圖號，再找圖框印著它的位置圖（ge_no_by_title）；找不到的列在 docs[文件號].why，卡片寫「文件庫裡找不到這份圖」。
  範圍（燃機 G／汽機 S）看文件號的系統碼：pid_lib.SCOPE_LETTER（EGJ01＝燃機發電機、EGK01＝汽機發電機…）以外，G 開頭＝燃機、T 開頭＝汽機。

== 比對（只在範圍相符的圖上；每一頁先跳過 A4／Letter 封面與附加的規範、手冊頁）==
  第一道 GE 編號（via='ge'）：pid_ge.label_hits_page——圖上的字去括號與標點後與條目的 tag／forms **整詞相等**（VA21 不中 VA21-1）、
    斜線清單展開（96PG-5A/B/C）、純字母條目只收括號裡的。另加位置圖才有的寫法：
    * 逗號接續（form 'text-comma'）：'TT-WR-3A,3B,3C' 一個字、或 '45FT-2A,' '2B' 分成幾個字（同一行、同一閱讀方向、間距 ≤ COMMA_GAP 個字高）
      ——一條引線管好幾支，後面幾支只寫尾碼。展開規則同斜線清單（取代末段／取代末幾碼，只收表內有的）；框＝整串字的聯集。
    * 括號別名（paren_aliases）：G11 版清單的條目名稱帶括號（'TT-WS1FI-2(TT-WS1F1-2)'），括號前後像 GE 編號的字另當別名，只在那個寫法
      還不是任何條目的名稱時。
    * 形近字（form 'text-lookalike'）：圖上把 I／1、O／0 寫混（M0147 的 'TT-WSIF1-2' 是清單的 TT-WS1FI-2；EGJ01-D0021 的 'F0-2921'）。
      只看有連字號、有數字的字（'FILL'、'OIL' 會撞 FL1-1、OL 1）；形近正規化後與條目的寫法相等、全範圍只對到這一個條目，而且
      這一處是引線標註或這份圖是條目自己的位置圖才收；這一頁已有它的引線標註就不找。卡上 lvl＝推論並講明「差一個形近字」。
    * '-ABOVE'／'-BELOW' 尾綴（TZD01 p3 'JB/17A-ABOVE'）去掉再比。
  第二道 KKS（via='kks'）：圖上不帶機組的 KKS（TZD01-D0002 汽機電氣接線位置圖只寫 'MAC20BP031'）。字去分隔符後以 build_card_aux.GE_KKS_RE
    拆成（前綴, 本體, 子件），與條目現行 KKS 的（本體, 子件）**整字**相同才算（BP017A ≠ BP017）；前綴是別的機組（G21、S20…）不收；
    本體被超過 GE_SHARED_MAX 個沒有子件的條目共用（盤箱、多點元件）不歸戶；共用的標 shared。'JB-MAD50GD001' 這種接線盒標題去分隔符後
    不是 KKS 形狀，不會中。
  疊寫（stack_pass）：發電機輔機外型圖把 KKS 與 GE 編號上下兩行疊寫（'MKW49BP001'／'PDT-3461'）。KKS 那筆緊貼的 GE 標籤是同一個條目 →
    併成一個框；是別的條目 → KKS 那筆不發布，以圖上的 GE 標籤為準（EGJ01-D0027 的 96QT-2A 疊在 MBV01BP304 上，清單 96QT-2A 是 BP305）。
  借位置（反方驗證後的規則；lvl 一律推論）：
    alias＝兩個條目的現行 KKS（本體＋子件）完全相同、名字也相近（一個包含另一個，或相似度 ≥ 0.7）＝同一顆的兩個編號（'96HDAS-1B (96DP-012B)'、
      改號 DI-FA-70／DI-FA-702），互相借引線標註；共用 KKS 但名字完全不同的（96GN-5C 與管路標籤 96FGAFS-2C）不借。
    body＝子件（KKS 帶尾碼）借主設備（同本體、沒有尾碼）的引線標註，只在子件自己的位置圖上、而且子件在任何圖上都沒有自己的引線標註
      ，主設備必須是閥（KKS 設備碼 QN／QM／AA：定位器、電磁閥、極限開關裝在閥上；LE-3461 探棒裝在 SDE 裡、不借 LT-3461 傳送器頭）；
      主設備在對照表沒有 KKS 時，'90VA41-91'（定位器）這種「功能碼＋閥號」借那顆閥（GBD01-D0001）。
      **反方向不借**：控制器、定位器不借感測元件或致動器的框（TIS-2996B 在控制箱面板、90ESV-2 在 DVP 盤）。卡上「※ 框的是主設備」。
  這一處算什麼（note；page_classes，2026-10-27 普查六組各自看圖校準）：
    0＝圖上指著元件的引線標註（位置）。
    5＝設備表的一列：像編號的字排成一欄（≥ TABLE_MIN）、而且 ≥ TABLE_NB 的列右邊有別的欄（DEVICE TAG｜TRAY ROUTE、NAMEPLATE｜LOCATION、
      RDS-PP 清單）；疊寫的標註框右邊只有別的框的編號或什麼都沒有，不算（舊的「同一欄 ≥ 4 格」規則會把 TZD01 p3 的 KKS 方框、M0163 的
      PDI-FG106～110 誤判成清單）。同一頁有 ≥ LIST_PAGE_CHAINS 串 ≥ LIST_MIN 個沒有右欄的編號欄＝整頁清單（TZD01 p2 依區域分組的 KKS 框）。
      表格那一列上的其他編號（RDS-PP 清單的 KKS 欄）也算。
    1＝附註／引用（以「片語」判：同一行相鄰兩字空隙 ≤ PHRASE_GAP 字高——一排各自加框的標註不是一句話）：片語 ≥ SENT_MIN 字而且有 ≥ 2 個
      一般英文字；FOR／TO／FROM／SEE／PER／ON／VIA 之後（含疊寫的上一行以它結尾、下一行以 TO／FROM 開頭的整疊：'96GN-1A/B/C'…'TO MLI 0962
      AM10' 是導壓管束）；THRU 之前；不成對的右括號；接 (H)／(L)（取壓的高低壓側根閥）；詳圖標題（疊在 DETAIL／SECTION／VIEW 下、或接
      '(6 PLACES)'）；頁面上緣 SMALL_TOP 內的小字（改版紀錄）。LOC_REF_SHEETS 明列的頁（GID01-D0009 的互連導壓管、導壓管連接示意方塊圖，
      建置時要在頁面上找到 evidence 字樣才套用）整頁都是引用。
    不帶連字號的寫法、右邊 12 字高內有一般英文說明字（SYMBOL｜DEVICE DESCRIPTION 表的 'HV2940U｜HP SHUT-OFF VALVE'）＝設備表的一列。

== 排序、上限、取捨 ==
  條目有任何一處引線標註（note 0）時，它在設備表裡的列不發布（stats.dropped.table_with_callout；比照 pid_ge 的 list_with_symbol）。
  同一個字、同一個框（0.1 %）出現在頁面大小相同的另一份 PDF＝合訂本裡的影本（GID01-D0009 p22～31 合訂了 M0144／M0163／M0104／M0170／
  D0008；EGJ01 與 EGK01 的同一張發電機輔機圖）→ 只留排在前面的（stats.dropped.copy_of_other_sheet）。
  排序：清單點名的圖在前（listed）→ 引線標註在表格之前 → 正寫在形近字／主設備繼承之前 → 文件號 → 頁 → 由上到下、由左到右；
  每條目最多 LIMIT_SHEETS 張圖、每張圖最多 LIMIT_HITS 處。清單沒點名的圖上也寫著這個編號照收，listed=0（GE 標籤在 GE 圖上就是證據，
  lvl 不因此降級；卡上寫「清單沒有列這份圖」）。

== 輸出 cardwork/loc_ge.json（決定性：鍵排序、無時間戳、無本機絕對路徑）==
  {"kind":"loc_ge","generated_by","version","docs":{…},"sheets":{…},"by_ge":{…},"stats":{…}}
  docs[文件號]＝{doc（完整 HT 編號）, rel, rev, title, scope, alts（其他候選檔數）, fallback_copy, via_title?} 或 {why}（找不到檔）
    via_title＝檔名沒有這個 GE 圖號、由圖框印的號碼找到的（139T8282＝M0170；合訂本也印，取「印著它的頁佔全部圖紙頁比例」最高的那份）
  sheets：與 pid_ge.json 同一套欄位與算法（slug、rot、w_pt／h_pt、label_pt、grid、src…），另帶 kind='loc'；pid_shots 照樣出圖
  by_ge["<system>|<tag>"]＝[{sheet, x, y, w, h, label, rel('neutral'), drawn_as(''), how('text'), form, note, via('ge'|'kks'), units, listed,
          zone?, zone_near?, shared?, stack?}]

== 已知限制 ==
  * 只讀 PDF 文字層，不跑 OCR：普查清單點名、找得到檔的位置圖都有完整文字層（TZD01 的 NX 線條字上疊一層不可見文字，位置一致）。
    GE 圖的圖框分區號是線條、不是文字，所以位置圖沒有「圖框分區」。
  * 框是標籤字，不是箭頭端：引線指的常是取壓點／根閥（M0144、M0163 的變送器本體在 JB 架上），疊寫與逗號接續的一個標籤管好幾支。
    壓力量測配置圖（TAP_TITLE_RE）的圖紙帶 tap＝1，卡上講明「引線有的指傳送器本體，有的指取壓點、根閥或導壓管」。
  * 盤面銘牌是線條字時（EGJ01-D0020 p5 的 PAL-3462／PAL-3465）沒有文字層，讀不到；只標件號氣球、沒寫編號的（PDS-2996＝件號 17）不處理。
  * 圖面筆誤（96GHGT-3、MAD20CS003）、子件尾碼圖上沒寫（ZS-1212C）、清單的位置圖欄點錯圖（96WW-1、PDI-FG106～110-1）都照實不處理。

用法：
  py tools/db/loc_ge.py                       # 寫 <CARDWORK>\loc_ge.json
  py tools/db/loc_ge.py --verify "GT|CT-DA-2" "ST|PT-211A"   # 另印這些條目的命中並畫紅框圖到 --verify-dir
"""
import argparse
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pid_lib as L  # noqa: E402
import pid_index as PI  # noqa: E402
import pid_ge as PG  # noqa: E402
from build_card_aux import GE_SITE_UNITS, GE_SHARED_MAX, GE_KKS_RE, ge_cmp, ge_ld_listed  # noqa: E402

GENERATED_BY = 'tools/db/loc_ge.py'
VERSION = 1
LIMIT_SHEETS = 6
LIMIT_HITS = 8
NOTE_TABLE = 5
NOTE_SENTENCE = 1
COMMA_GAP = 2.0              # 逗號接續：下一個字與前一個字的間距 ≤ 幾個字高
TABLE_MIN = 3                # 表格：一欄至少幾個編號（M0117 的 96AT-6A／B／C 只有 3 列、列高 3.6 字高）
TABLE_GAP = (0.3, 4.0)       # 表格欄相鄰兩格的中心距（字高的倍數）
TABLE_NB = 0.6               # 表格：一欄裡至少這個比例的列在右邊有別的欄
LIST_MIN = 10                # 清單頁：一串沒有右欄的編號至少幾個才算「長串」
LIST_PAGE_CHAINS = 2         # 清單頁：至少幾串長串
SENT_MIN = 5                 # 附註句子：同一個片語至少幾個字、其中 ≥ 2 個一般英文字（P&ID 用 4；位置圖的標註常是「96BH-1A AND 96DH-1A HP」四個字）
PHRASE_GAP = 2.0             # 片語：同一行相鄰兩字的空隙超過幾個字高就切開（一排各自加框的標註不是一句話）
SMALL_FRAC = 0.6             # 小字：字高不到這一頁編號字高中位數的這個比例（改版紀錄）……
SMALL_TOP = 0.15             # ……而且在頁面上緣這個比例以內（GE 圖的改版紀錄在右上；盤面銘牌的小字在頁中，是位置）
# 只有引用、沒有實體位置的頁（宣告＋建置時驗證：頁面文字找得到 evidence 才套用，否則計數不套）：這幾頁上的命中一律 note 1
LOC_REF_SHEETS = {
    ('GID01-D0009', 12): ('INTERCONNECTS', 'AM10 與 AM20 之間的互連導壓管：管口用儀器編號命名，周圍沒有設備'),
    ('GID01-D0009', 19): ('TO JB34B', '導壓管連接示意方塊圖：框字清單接到「TO JB34B SEE AM20」，沒有實體位置'),
    ('GID01-D0009', 20): ('TO JB169B', '導壓管連接示意方塊圖（續）'),
}
TAP_TITLE_RE = re.compile(r'PRESSURE (TRANSDUCER|MEASUREMENT|INSTRUMENTATION)|TRANSDUCER ARR', re.I)   # 壓力量測配置圖：引線常指取壓點／導壓管
TRIGGERS = frozenset(('FOR', 'TO', 'FROM', 'SEE', 'PER', 'ON', 'VIA'))
TYPICAL_WORDS = frozenset(('PLACES', 'TYP', 'TYPICAL'))     # 同一片語有這些字＝典型詳圖的標題（'(6 PLACES)'），不是逐顆的位置
TUBE_WIN = 10.0              # 導壓管束說明的上下範圍（字高）
TITLE_WORDS = frozenset(('DETAIL', 'SECTION', 'VIEW'))      # 詳圖標題的第一個字：疊在它下面的編號行是標題的一部分
NB_STOP = frozenset(('NOTE', 'NOTES', 'SEE', 'TO', 'FROM', 'FOR', 'FARSIDE', 'TYP', 'REF', 'AND', '&', 'HP', 'LP', 'THRU'))
STACK_GAP = 1.6              # 疊寫：KKS 與 GE 編號上下兩行、垂直間距 ≤ 幾個字高、水平有重疊
BODY_MAX = 4                 # 借位置：同一個 KKS 本體最多幾個條目
BODY_EQ = frozenset(('QN', 'QM', 'AA'))   # body 只借閥（KKS 設備碼）：LE-3461 探棒裝在 SDE 裡，不在 LT-3461 傳送器頭上（反方驗證第二輪）
SKIP_FLAGS = ('old', 'copy_path', 'collection', 'dossier')
GE_NO_RE = re.compile(r'(?<![0-9A-Z])(\d{3}T\d{4})(?![0-9])')
# 清單沒點名、但普查（2026-10-27，corpus_gap 組逐份渲染）確認有元件引線標註、而且上面的條目沒有任何位置圖的配置圖。
# **明列，不用標題正規式擴大**（標題分類不可靠：M0139 其實是手冊、M0127 是規範）；接線圖、盤內配置、介面點為主的外型圖不收。
EXTRA_DOCS = {
    'GZD01-M0145': 'COOL COOLING AIR CABLE TRAY：p3 DETAIL A 的 PT-11A／B／C 三條引線',
    'GZD01-M0151': 'COOLED COOLING AIR TC 配置：PT-11A～C、PT-012A～C 引線',
    'GZD01-M0080': 'FLAME DETECTOR 配置：28FD-1／10／11／12 指燃燒筒上的火焰偵測器',
    'GZD01-M1203': '水霧滅火 skid 內部配置（廠商圖）：p4 的 23WM-1、88WM-1、26FP-1 引線',
    'EGJ01-D0016': 'PGA 可攜式氣體分析儀外型圖：p3 的 U-2995A、PCV-2995、HV-2995A～C',
    'EGJ01-D0011': '發電機機械外型圖：p5 的 DT-GGK-75／76',
}
_LOOK = str.maketrans({'I': '1', 'L': '1', 'O': '0', 'Q': '0'})
_TAIL_RE = re.compile(r'^[A-Z0-9]{1,4}$')


def r5(v):
    return round(float(v), 5)


def doc_scope(sysc):
    if sysc in L.SCOPE_LETTER:
        return L.SCOPE_LETTER[sysc]
    return 'G' if sysc[:1] == 'G' else 'S' if sysc[:1] == 'T' else None


# ================================================================ 文件集
def resolve_docs(lib, wanted, log):
    """wanted＝{文件號}（'GZD01-M0166'／'307T1798'）→ {文件號: {doc, rel, size, mtime, rev, title, scope, alts} 或 {why}}。"""
    cands = defaultdict(list)
    for rel, size, mtime in lib:
        base = rel.rsplit('/', 1)[-1]
        dn = L.docno(base)
        if dn:
            short = re.sub(r'^HT\d-\d-', '', dn[0].upper())
            if short in wanted:
                cands[short].append((rel, size, mtime, dn))
        for m in GE_NO_RE.finditer(base.upper()):
            if m.group(1) in wanted and dn:
                cands[m.group(1)].append((rel, size, mtime, dn))
    out = {}
    for no in sorted(wanted):
        cs = cands.get(no) or []
        if not cs:
            out[no] = {'why': '文件庫裡沒有檔名含這個文件號的 PDF'}
            continue
        pool = [c for c in cs if not set(L.copy_flags(c[0])) & set(SKIP_FLAGS)] or cs
        top = max(L.rev_rank(c[3][6]) for c in pool)
        best = min((c for c in pool if L.rev_rank(c[3][6]) == top),
                   key=lambda c: ('dupname' in L.copy_flags(c[0]), len(c[0]), c[0]))
        rel, size, mtime, dn = best
        doc, rev, _stem, title = L.ident(rel)
        out[no] = {'doc': doc or dn[0].upper(), 'rel': rel, 'size': size, 'mtime': mtime, 'rev': rev or '', 'title': title, 'extra': 1 if no in EXTRA_DOCS else 0,
                   'scope': doc_scope(dn[3].upper()), 'alts': len(cs) - 1,
                   'fallback_copy': 1 if all(set(L.copy_flags(c[0])) & set(SKIP_FLAGS) for c in cs) else 0}
    return out


def ge_no_by_title(docs, a, log):
    """檔名找不到的 GE 圖號（139T8282、301T6191）：在已找到的位置圖的文字層裡找印著這個號碼的頁（圖框的 Drawing Number）。
    合訂本（GID01-D0009 合訂了 M0170＝139T8282 的兩頁）也會印，所以取「印著它的頁佔全部圖紙頁的比例」最高的那份（專屬的圖是 100 %）；
    比例相同的不只一份就不選（why 列出是哪幾份）。採用的帶 via_title＝1。"""
    miss = [no for no, d in docs.items() if not d.get('rel') and GE_NO_RE.fullmatch(no)]
    if not miss:
        return
    have = {}
    for no, d in docs.items():
        if d.get('rel') and d['rel'] not in have:
            have[d['rel']] = d
    L.ensure_text(a.library, sorted({(d['rel'], d['size'], d['mtime']) for d in have.values()}), a.text_cache, a.jobs, log)
    texts = {rel: [pg for pg in L.load_text(a.library, rel, d['size'], d['mtime'], a.text_cache)['pg'] if not L.is_cover(pg)]
             for rel, d in have.items()}
    for no in miss:
        hits = []
        for rel, d in sorted(have.items()):
            pgs = texts[rel]
            n = sum(1 for pg in pgs if any(no in w[4].upper() for w in pg['words']))
            if n:
                hits.append((n / float(len(pgs)), d))
        if not hits:
            continue
        top = max(r for r, _d in hits)
        best = [d for r, d in hits if r == top]
        if len(best) == 1:
            docs[no] = dict(best[0], via_title=1)
        else:
            docs[no]['why'] = '圖框印著這個 GE 圖號的位置圖不只一份（%s），不選' % '、'.join(sorted(d['doc'] for d in best))


# ================================================================ 一頁的比對
def kks_plan(ents):
    """→ ({(範圍, 本體, 子件): [(條目鍵, 前綴)…]}, stats)。本體被超過 GE_SHARED_MAX 個沒有子件的條目共用 → 不歸戶。"""
    st = Counter()
    by = defaultdict(list)
    for k in sorted(ents):
        e = ents[k]
        if not e['scope']:
            continue
        for kk in e['kks']:
            m = GE_KKS_RE.match(ge_cmp(kk))
            if not m:
                st['unparsed'] += 1
                continue
            by[(e['scope'], m.group(2), m.group(3) or '')].append((k, m.group(1) or ''))
    nosub = Counter()
    for (sc, body, sub), lst in by.items():
        if not sub:
            nosub[(sc, body)] += len({k for k, _p in lst})
    out = {}
    for key, lst in by.items():
        if nosub[(key[0], key[1])] > GE_SHARED_MAX:
            st['group_too_big'] += 1
            continue
        out[key] = sorted(set(lst))
    st['bodies'] = len(out)
    return out, st


def tagish(t, scope, names):
    """像編號的字：表內的 GE 寫法、GE 形（96FG-1）或 KKS 形（MAC20BP031／JB 不算）。斜線、逗號前的第一段。"""
    t = PG.clean_word(t)
    head = t.split(',')[0].split('/')[0] if t else ''
    return bool(head) and ((scope, ge_cmp(head)) in names or bool(L.GE_RE.fullmatch(head)) or bool(GE_KKS_RE.match(ge_cmp(head))))


def page_classes(pg, R, scope, names):
    """一頁 → ({字索引: note}（只列不是 0 的；見檔頭「這一處算什麼」）, 版面資料 ctx）。2026-10-27 普查校準（scratchpad chains.py；12 份圖 18 頁）、
    同日反方驗證（7 組 196 筆看圖）後修正：
    * 表格（NOTE_TABLE）：像編號的字由上到下排成一欄（≥ TABLE_MIN 個、行首對齊 ≤ 0.8 字高、相鄰 0.3～4 字高），而且 ≥ TABLE_NB 的列
      在同一列右邊 25 字高內有**別的欄**（不是編號、不是逗號接續的尾碼、不是 NOTE／SEE 之類）——DEVICE TAG｜TRAY ROUTE｜CABLE BOM、
      NAMEPLATE｜LOCATION、RDS-PP 清單的編號都是 1.0；疊寫的標註框（TZD01 p3 的 KKS 方框、M0163 的 PDI-FG106～110、D0050 的偵測器框）
      右邊只有別的框的編號或什麼都沒有，0～0.67 → 不算。表格那一列上**自己也排成一欄**的其他編號（RDS-PP 清單的 KKS 欄）也算表格；
      寫在說明格句子裡的編號（'INLET BLEED HEAT VALVE VA20-1 UPSTREAM PRESSURE TRANSMITTER' 的 VA20-1，那是 96BH-1A 的列）不算。
    * 清單頁：同一頁有 ≥ LIST_PAGE_CHAINS 串 ≥ LIST_MIN 個、沒有右欄的編號欄（TZD01 p2 依區域分組的 KKS 清單框，27／21／13／11／10）
      ＝整頁的編號清單，這一頁沒有右欄的編號欄（≥ 3 個）全部算表格。只有一串長欄的（D0050 疊在一起的偵測器標註框 11）不算。
    * 附註（NOTE_SENTENCE）——都以「片語」判（同一行、相鄰兩字的空隙 ≤ PHRASE_GAP 字高；EGK01-D0011 p2 一排各自加框、相隔 3～10 字高的
      HS062／HS061／HS003／HS004／LE035 是五個標註，不是一句話）：
      片語 ≥ SENT_MIN 個字而且有 ≥ 2 個不是編號的英文字；FOR／TO／FROM／SEE／PER／ON／VIA 之後（含上一行以它結尾、或下一行以 TO／FROM
      開頭的疊寫框：'96GN-1A/B/C'…'TO MLI 0962 AM10' 是導壓管束）；THRU 之前；不成對的右括號；後面接 (H)／(L)（取壓的高低壓側）；
      同一片語、或疊在下一行有 PLACES／TYP／TYPICAL，或疊在 DETAIL／SECTION／VIEW 標題下面（詳圖標題「DETAIL E／CT-DA-1, 2, 3, 4, 5, 6／(6 PLACES)」）；
      頁面上緣 SMALL_TOP 以內、字高不到這一頁編號字高中位數 SMALL_FRAC 的小字（GE 圖的改版紀錄；盤面銘牌的小字在頁中，不受影響）。"""
    words = pg['words']
    fr = [L.reading_frame(w) for w in words]
    tg = [i for i, w in enumerate(words) if tagish(w[4], scope, names)]
    tgs = set(tg)
    out = {}
    hs = sorted(fr[i][2] for i in tg if fr[i][2] > 0)
    med = hs[len(hs) // 2] if hs else 0
    # ---- 行：同一個閱讀方向、橫軸中心差 ≤ 0.35 字高、沿軸向接著（表格列靠它）；片語：行再以空隙 > PHRASE_GAP 字高切開（句子靠它）
    lines, cur = [], []
    for i, w in enumerate(words):
        if cur:
            j = cur[-1]
            if words[j][5] == w[5] and fr[j][2] > 0 and abs(fr[i][1] - fr[j][1]) <= 0.35 * fr[j][2] and fr[i][0] >= fr[j][0]:
                cur.append(i)
                continue
            lines.append(cur)
        cur = [i]
    if cur:
        lines.append(cur)
    line_of = {i: li for li, ln in enumerate(lines) for i in ln}

    def wlen(i):
        return max(words[i][2] - words[i][0], words[i][3] - words[i][1])
    phrases = []
    for ln in lines:
        ph = [ln[0]]
        for x, y in zip(ln, ln[1:]):
            gap = (fr[y][0] - wlen(y) / 2.0) - (fr[x][0] + wlen(x) / 2.0)
            if fr[x][2] > 0 and gap > PHRASE_GAP * fr[x][2]:
                phrases.append(ph)
                ph = [y]
            else:
                ph.append(y)
        phrases.append(ph)

    def up(t):
        return t.upper().strip('()[],.;:')

    def stacked(a_ph, b_ph):
        """b_ph 緊貼在 a_ph 的下一行（同一閱讀方向、0.3～STACK_GAP 字高、行首或範圍有重疊）"""
        i, j = a_ph[0], b_ph[0]
        if words[i][5] != words[j][5] or fr[i][2] <= 0:
            return False
        dc = fr[j][1] - fr[i][1]
        a0, a1 = fr[i][3], fr[a_ph[-1]][3] + wlen(a_ph[-1])
        b0, b1 = fr[j][3], fr[b_ph[-1]][3] + wlen(b_ph[-1])
        return 0.3 * fr[i][2] < dc <= STACK_GAP * fr[i][2] and a0 < b1 + fr[i][2] and b0 < a1 + fr[i][2]
    for pi, ph in enumerate(phrases):
        trig = False
        for i in ph:
            if trig and i in tgs:
                out[i] = NOTE_SENTENCE
            if up(words[i][4]) in TRIGGERS:
                trig = True
        for x in ph:                                        # 不成對的右括號：'(FOR 45HGT-CB-1 &' 換行後的 '45HGT-CB-2)' 是同一句說明的續行
            t = words[x][4].strip()
            if x in tgs and t.endswith(')') and '(' not in t and not any('(' in words[y][4] for y in ph):
                out[x] = NOTE_SENTENCE
        for x, y in zip(ph, ph[1:]):                       # 'CT-DA-1 THRU 6'：範圍寫法；'96GN-2A/B/C (H)'：取壓的高壓側根閥
            if x in tgs and up(words[y][4]) in ('THRU', 'H', 'L') and (up(words[y][4]) == 'THRU' or words[y][4].strip().startswith('(')):
                out[x] = NOTE_SENTENCE
        if any(up(words[i][4]) in TYPICAL_WORDS for i in ph):   # 'CT-DA-1, 2, 3, 4, 5, 6 (6 PLACES)'：典型詳圖的標題，指的是一整組
            for i in ph:
                if i in tgs:
                    out[i] = NOTE_SENTENCE
        if len(ph) >= SENT_MIN and sum(1 for i in ph if i not in tgs and re.fullmatch(r'[A-Z]{2,}', up(words[i][4]))) >= 2:
            for i in ph:
                out.setdefault(i, NOTE_SENTENCE)
    # 上一行以 FOR／TO／FROM… 結尾（'CABLE TRAY FROM'／'PT-11A, B & C'）；下一行以 TO／FROM 開頭（疊寫的編號框＋'TO MLI 0962 AM10'）→ 往上整疊
    for pi, ph in enumerate(phrases):
        if up(words[ph[-1]][4]) in TRIGGERS:
            for q in phrases[pi + 1:pi + 4]:
                if stacked(ph, q):
                    for i in q:
                        if i in tgs:
                            out[i] = NOTE_SENTENCE
                    break
        if up(words[ph[0]][4]) in ('TO', 'FROM'):
            cur_ph = ph
            for q in reversed(phrases[max(0, pi - 12):pi]):
                if stacked(q, cur_ph) and any(i in tgs for i in q):
                    for i in q:
                        if i in tgs:
                            out[i] = NOTE_SENTENCE
                    cur_ph = q
    # 導壓管束的說明（GID01-D0009 p21 「96GN'S HIGH SIDE TUBE RUNS TO 0962 AM10」、「96CD'S … TUBE RUNS TO MLI 0805」）：
    # 說明上下 TUBE_WIN 字高、左右延伸的範圍裡的編號，是管束上的標籤，不是傳送器本體
    for ph in phrases:
        ws_ = [up(words[i][4]) for i in ph]
        if 'TUBE' in ws_ and ('RUNS' in ws_ or 'RUN' in ws_):
            h = fr[ph[0]][2]
            x0, x1 = fr[ph[0]][3], fr[ph[-1]][3] + wlen(ph[-1])
            for i in tg:
                if (words[i][5] == words[ph[0]][5] and abs(fr[i][1] - fr[ph[0]][1]) <= TUBE_WIN * h
                        and x0 - 15 * h <= fr[i][3] <= x1 + 25 * h):
                    out[i] = NOTE_SENTENCE
    # 詳圖標題：疊在 DETAIL／SECTION／VIEW 那一行下面、或下面接 '(6 PLACES)' 的編號行（M0147 p5「DETAIL E／CT-DA-1, 2, 3, 4, 5, 6／(6 PLACES)」）
    for pi, ph in enumerate(phrases):
        if not any(i in tgs for i in ph):
            continue
        near = [q for q in phrases[max(0, pi - 4):pi + 5] if q is not ph]
        above = [q for q in near if stacked(q, ph)]
        below = [q for q in near if stacked(ph, q)]
        if (any(up(words[q[0]][4]) in TITLE_WORDS for q in above)
                or any(up(words[i][4]) in TYPICAL_WORDS for q in below for i in q)):
            for i in ph:
                if i in tgs:
                    out[i] = NOTE_SENTENCE
    if med:
        pw, ph_ = L.upright_size(pg, R)
        for i in tg:
            if 0 < fr[i][2] < SMALL_FRAC * med and L.to_upright_frac(pg, words[i][:4], R)[3] < SMALL_TOP:
                out[i] = NOTE_SENTENCE
    # ---- 編號欄
    chains = []
    for mode in ('start', 'center'):                       # 行首對齊的欄、置中排的欄（EGJ01-D0021／D0022 p3 的 SYMBOL｜DEVICE DESCRIPTION 表）
        byd = defaultdict(list)
        for i in tg:
            a, c, h, s0 = fr[i]
            if h > 0:
                byd[words[i][5]].append((c, s0 if mode == 'start' else a, h, i))
        for lst in byd.values():
            lst.sort()
            cs = []
            for c, s0, h, i in lst:
                best = None
                for ch in cs:
                    lc, ls, lh, _li = ch[-1]
                    if TABLE_GAP[0] * min(h, lh) <= c - lc <= TABLE_GAP[1] * max(h, lh) and abs(s0 - ls) <= 0.8 * min(h, lh):
                        if best is None or abs(s0 - ls) < best[0]:
                            best = (abs(s0 - ls), ch)
                if best:
                    best[1].append((c, s0, h, i))
                else:
                    cs.append([(c, s0, h, i)])
            chains += [[x[3] for x in ch] for ch in cs]
    in_col = {i for ch in chains if len(ch) >= TABLE_MIN for i in ch}
    rows_of = defaultdict(list)                              # 同一列（幾何）：同一閱讀方向、橫軸中心差 ≤ 0.35 字高
    for j, w in enumerate(words):
        if fr[j][2] > 0:
            rows_of[(w[5], round(fr[j][1] / max(fr[j][2] * 0.35, 1.0)))].append(j)

    def same_row(i):
        h = fr[i][2]
        key = round(fr[i][1] / max(h * 0.35, 1.0))
        out_ = []
        for dk in (-1, 0, 1):
            for j in rows_of.get((words[i][5], key + dk), ()):
                if j != i and abs(fr[j][1] - fr[i][1]) <= 0.35 * h:
                    out_.append(j)
        return out_

    def right_cell(i):
        a, c, h, s0 = fr[i]
        end = a + wlen(i) / 2.0
        for j in same_row(i):
            if fr[j][3] < end - 0.2 * h or fr[j][3] - end > 25 * h:
                continue
            t = up(words[j][4])
            if j in tgs or not t or t in NB_STOP or (_TAIL_RE.match(t) and (words[i][4].rstrip().endswith(',') or words[j][4].rstrip().endswith(','))):
                continue
            if _TAIL_RE.match(t) and len(t) <= 2 and words[j - 1][4].rstrip().endswith(','):
                continue
            return True
        return False
    table = set()
    bare = []
    for ch in chains:
        if len(ch) < TABLE_MIN:
            continue
        nb = sum(1 for i in ch if right_cell(i))
        if nb >= TABLE_NB * len(ch):
            table.update(ch)
        elif nb < 0.3 * len(ch):
            bare.append(ch)
    if sum(1 for ch in bare if len(ch) >= LIST_MIN) >= LIST_PAGE_CHAINS:
        for ch in bare:
            table.update(ch)
    for i in list(table):                                  # 同一列上自己也排成一欄的其他編號（RDS-PP 清單的 KKS 欄）
        for j in same_row(i):
            if j in tgs and j in in_col:
                table.add(j)
    for i in table:
        out[i] = NOTE_TABLE
    return out, {'fr': fr, 'lines': lines, 'line_of': line_of, 'tgs': tgs}


def compact_row(i, words, ctx):
    """這個字的右邊（同一行、12 字高內）有一般英文說明字＝設備表的一列（SYMBOL｜DEVICE DESCRIPTION 兩欄之間有空隙）。"""
    fr = ctx['fr']
    a, c, h, s0 = fr[i]
    end = a + max(words[i][2] - words[i][0], words[i][3] - words[i][1]) / 2.0
    for j, w in enumerate(words):                               # 以幾何找同一列（文字層的順序不一定由左到右：表格的說明格常排在編號格前面）
        if (j != i and w[5] == words[i][5] and abs(fr[j][1] - c) <= 0.35 * h and 0 <= fr[j][3] - end <= 12 * h and j not in ctx['tgs']
                and re.fullmatch(r'[A-Z]{2,}', w[4].upper().strip('()[],.;:'))):
            return True
    return False


def note_of(i, cls):
    return cls.get(i, 0) if i is not None else 0


def comma_hits(words, scope, names, st):
    """逗號接續的編號 → [(字索引清單, 條目鍵…, 讀法)]：'TT-WR-3A,3B,3C'（一個字）或 '45FT-2A,' '2B'（同一行接著的字）。只回傳第 2 支以後
    （第 1 支 label_hits_page 已經收了）。"""
    out = []
    frames = [L.reading_frame(w) for w in words]
    used = set()
    for i, w in enumerate(words):
        if i in used:
            continue
        raw = PG.clean_word(w[4]) if ',' not in w[4] else w[4].upper().strip().strip('()[]{}.;:')
        segs = [x.strip().strip('()') for x in raw.split(',')]
        segs = segs[:1] + [x.lstrip('-') for x in segs[1:]]
        first = segs[0]
        if (scope, ge_cmp(first)) not in names:
            continue
        idx = [i]
        tails = [x for x in segs[1:] if x]
        trailing = w[4].rstrip().endswith(',') or (len(segs) > 1 and not segs[-1])
        a0, c0, h0 = frames[i][0], frames[i][1], frames[i][2]
        last_end = a0 + max(w[2] - w[0], w[3] - w[1]) / 2.0
        j = i + 1
        while trailing and j < len(words) and h0 > 0:
            wj = words[j]
            if wj[5] != w[5]:
                break
            aj, cj, hj = frames[j][0], frames[j][1], frames[j][2]
            lenj = max(wj[2] - wj[0], wj[3] - wj[1])
            if abs(cj - c0) > 0.35 * h0 or (aj - lenj / 2.0) - last_end > COMMA_GAP * h0 or aj < a0:
                break
            t = wj[4].upper().strip().strip('().;:')
            parts = [x.strip().lstrip('-') for x in t.split(',')]
            if not parts[0] or not _TAIL_RE.match(parts[0]):
                break
            tails += [x for x in parts if x]
            idx.append(j)
            used.add(j)
            last_end = aj + lenj / 2.0
            trailing = t.endswith(',')
            j += 1
        for p in tails:
            if not _TAIL_RE.match(p):
                continue
            cs = []
            if len(p) < len(first):
                cs.append(first[:len(first) - len(p)] + p)
            if '-' in first:
                cs.append(first.rsplit('-', 1)[0] + '-' + p)
            ok = sorted({c for c in cs if (scope, ge_cmp(c)) in names})
            if not ok:
                st['comma_unresolved'] += 1
                continue
            if len({ge_cmp(c) for c in ok}) > 1:
                st['comma_ambiguous'] += 1
                continue
            out.append((idx, names[(scope, ge_cmp(ok[0]))], ok[0]))
    return out


def union_box(words, idx):
    xs = [words[i] for i in idx]
    return [min(w[0] for w in xs), min(w[1] for w in xs), max(w[2] for w in xs), max(w[3] for w in xs)]


def scan_page(sh, scope, names, look, kix, listed_by_doc, st):
    """一頁 → [記錄]（條目鍵、框、字、form、note、via、units、shared）。"""
    pg, R = sh['pg'], sh['R']
    words = pg['words']
    cls, ctx = page_classes(pg, R, scope, names)
    ref = next((LOC_REF_SHEETS[(no, sh['page'])] for no in sh['nos'] if (no, sh['page']) in LOC_REF_SHEETS), None)
    if ref:
        if ref[0].upper() in ' '.join(w[4].upper() for w in words):
            cls = {i: NOTE_SENTENCE for i in range(len(words))}
            st['ref_sheet_applied'] += 1
        else:
            st['ref_sheet_evidence_missing'] += 1
    recs = []
    site = GE_SITE_UNITS[scope]
    # ---- GE 編號（pid_ge.label_hits_page：整詞相等、括號、斜線清單）
    lst = Counter()
    at = {}
    for k, w in enumerate(words):
        at.setdefault(tuple(L.to_upright_frac(pg, w[:4], R)), k)
    for h in PG.label_hits_page(sh, scope, names, lst, True):
        i = at.get(tuple(h['box']))
        if i is None:
            st['label_unmapped'] += 1
            continue
        note = note_of(i, cls)
        # 不帶連字號的寫法、右邊緊接說明字（SYMBOL／DEVICE DESCRIPTION 表的「HV2940U｜HP SHUT-OFF VALVE」）＝設備表的一列；引線標註寫帶連字號的
        if not note and '-' not in PG.clean_word(words[i][4]) and any('-' in k.split('|', 1)[1] for k in h['keys']) and compact_row(i, words, ctx):
            note = NOTE_TABLE
            st['compact_table_row'] += 1
        for ek in h['keys']:
            recs.append({'key': ek, 'box': tuple(h['box']), 'label': h['label'], 'form': h['form'], 'note': note, 'via': 'ge', 'units': site, 'i': i})
    for k, v in lst.items():
        st['label_' + k] += v
    # ---- 逗號接續
    for idx, keys, rd in comma_hits(words, scope, names, st):
        box = L.to_upright_frac(pg, union_box(words, idx), R)
        lab = ' '.join(re.sub(r'\s+', ' ', words[i][4]).strip() for i in idx)
        for ek in keys:
            recs.append({'key': ek, 'box': tuple(box), 'label': lab, 'form': 'text-comma', 'note': note_of(idx[0], cls), 'via': 'ge', 'units': site, 'i': idx[0]})
            st['comma_hits'] += 1
    # ---- '-ABOVE'／'-BELOW' 尾綴（TZD01 p3 'JB/17A-ABOVE'）：去掉尾綴再比
    for i, w in enumerate(words):
        m = re.match(r'^(.+?)-(ABOVE|BELOW)$', PG.clean_word(w[4]))
        if m and (scope, ge_cmp(m.group(1))) in names:
            for ek in names[(scope, ge_cmp(m.group(1)))]:
                recs.append({'key': ek, 'box': tuple(L.to_upright_frac(pg, w[:4], R)), 'label': re.sub(r'\s+', ' ', w[4]).strip(), 'form': 'text',
                             'note': note_of(i, cls), 'via': 'ge', 'units': site, 'i': i})
                st['above_below_hits'] += 1
    # ---- 形近字：條目自己的位置圖上；或這一處是引線標註（F0-2921＝FO-2921，EGJ01-D0021 p3）。這一頁已有它的引線標註就不找
    mine = set().union(*[listed_by_doc.get(no) or set() for no in sh['nos']])
    if True:
        got = {r['key'] for r in recs if not r['note']}
        for i, w in enumerate(words):
            t = PG.clean_word(w[4])
            if not t or (scope, ge_cmp(t)) in names:
                continue
            if '-' not in t or not re.search(r'\d', t):         # 形近字只看編號形的字（'FILL'、'OIL' 正規化後會撞 FL1-1、OL 1）
                continue
            ks = look.get((scope, ge_cmp(t).translate(_LOOK))) or []
            if len(ks) != 1 or ks[0] in got or (ks[0] not in mine and note_of(i, cls)):
                continue
            recs.append({'key': ks[0], 'box': tuple(L.to_upright_frac(pg, w[:4], R)), 'label': re.sub(r'\s+', ' ', w[4]).strip(),
                         'form': 'text-lookalike', 'note': note_of(i, cls), 'via': 'ge', 'units': site, 'i': i})
            st['lookalike_hits'] += 1
    # ---- KKS（圖上不帶機組的 KKS；'MKG52BP501/MKG52BP502' 這種斜線合寫的逐段比）
    for i, w in enumerate(words):
        parts = [x for x in PG.clean_word(w[4]).split('/') if x] or ['']
        for part in parts:
            c = ge_cmp(part)
            m = GE_KKS_RE.match(c) if len(c) >= 10 else None
            if not m:
                continue
            pf, body, sub = m.group(1) or '', m.group(2), m.group(3) or ''
            lst2 = kix.get((scope, body, sub))
            if not lst2:
                continue
            if pf and pf not in ('XX', 'YY') and pf not in site:
                st['kks_other_unit'] += 1
                continue
            units = (pf,) if pf in site else site
            keys = sorted({k for k, _p in lst2})
            for ek in keys:
                recs.append({'key': ek, 'box': tuple(L.to_upright_frac(pg, w[:4], R)), 'label': re.sub(r'\s+', ' ', w[4]).strip(),
                             'form': 'text-slash' if len(parts) > 1 else 'text', 'note': note_of(i, cls), 'via': 'kks', 'units': units,
                             'shared': [k.split('|', 1)[1] for k in keys if k != ek], 'i': i})
                st['kks_hits'] += 1
    return stack_pass(recs, words, st)


def stack_pass(recs, words, st):
    """KKS 與 GE 編號疊寫成上下兩行（發電機輔機外型圖「MKW49BP001／PDT-3461」，KKS 在上、GE 編號在下，引線從其中一行拉出）：
    KKS 那一筆找緊貼的 GE 標籤（同一閱讀方向、垂直間距 ≤ STACK_GAP 字高、水平有重疊；先找下面那一行、沒有才找上面）——
    是同一個條目 → 併成一個框（GE 那筆的框擴成兩行的聯集，KKS 那筆不另列）；是別的條目 → KKS 那筆不發布（圖上的 GE 標籤為準：
    EGJ01-D0027 的 96QT-2A 疊在 MBV01BP304 上，清單 96QT-2A 是 BP305，照 KKS 會把 96QT-2A 標到 96QT-2B 的位置）。"""
    fr = {}
    ge_by_i = defaultdict(list)
    for r in recs:
        if r['via'] == 'ge':
            ge_by_i[r['i']].append(r)

    def frame(i):
        if i not in fr:
            fr[i] = L.reading_frame(words[i])
        return fr[i]

    def adjacent(i, j):
        a1, c1, h1, s1 = frame(i)
        a2, c2, h2, s2 = frame(j)
        if words[i][5] != words[j][5] or h1 <= 0 or h2 <= 0:
            return None
        l1 = max(words[i][2] - words[i][0], words[i][3] - words[i][1])
        l2 = max(words[j][2] - words[j][0], words[j][3] - words[j][1])
        if s2 > s1 + l1 or s1 > s2 + l2:
            return None
        dc = c2 - c1
        return dc if 0.3 * h1 <= abs(dc) <= STACK_GAP * max(h1, h2) else None
    out = []
    for r in recs:
        if r['via'] != 'kks':
            out.append(r)
            continue
        cands = []
        for j, gl in ge_by_i.items():
            dc = adjacent(r['i'], j)
            if dc is not None:
                cands.append((0 if dc > 0 else 1, abs(dc), j))
        if not cands:
            out.append(r)
            continue
        j = sorted(cands)[0][2]
        mine = [g for g in ge_by_i[j] if g['key'] == r['key']]
        if mine:
            for g in mine:
                b = g['box']
                g['box'] = (min(b[0], r['box'][0]), min(b[1], r['box'][1]), max(b[2], r['box'][2]), max(b[3], r['box'][3]))
                g['label'] = '%s／%s' % (r['label'], g['label']) if r['label'] not in g['label'] else g['label']
                g['stack'] = 1
            st['stack_merged'] += 1
        else:
            st['kks_next_to_other_ge'] += 1
    return out


def page_sig(pg):
    """同一張圖的影本認法：頁面大小（pt，取整）。合訂本的影本圖框、蓋章不同（字的指紋對不上），所以只比頁面大小，
    再加上「同一個字、同一個框（0.1 %）」——兩張不同的圖在同一個位置寫同一個編號的機會可以不計。"""
    return (round(pg['w']), round(pg['h']))


_PAREN_RE = re.compile(r'\(([^()]*)\)')


def paren_aliases(ents, names):
    """GE 清單 G11 版的條目名稱常帶括號（'TT-WS1FI-2(TT-WS1F1-2)'、'BT-TA1-13 (a_btta113) (HMI: …)'），ge_cmp 後整串對不到圖上的字。
    括號前的本名、括號裡像 GE 編號的字（有字母、有數字、有 -）另當別名——**只在那個寫法還不是任何條目的名稱時**（96FM-4(SIL)／96FM-4(TCP)
    的本名 96FM-4 已是別的條目，不加）。只給本工具用，不改對照表。"""
    out = {k: list(v) for k, v in names.items()}
    n = 0
    for k in sorted(ents):
        e = ents[k]
        if not e['scope']:
            continue
        for f in e['forms']:
            if '(' not in f:
                continue
            cands = [f.split('(', 1)[0].strip()] + [x.strip() for x in _PAREN_RE.findall(f)]
            for c in cands:
                cc = ge_cmp(c)
                if not cc or '-' not in c or not re.search(r'\d', c) or not re.search(r'[A-Z]', c.upper()) or (e['scope'], cc) in names:
                    continue
                lst = out.setdefault((e['scope'], cc), [])
                if k not in lst:
                    lst.append(k)
                    n += 1
    return out, n


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


# ================================================================ 組裝
def build(a, log):
    t0 = time.time()
    ents, names, est = PG.load_entries(a.ge_tags)
    names, n_alias = paren_aliases(ents, names)
    with open(a.ge_tags, encoding='utf-8') as f:
        raw = {'%s|%s' % (e.get('system') or '', e['tag']): e for e in json.load(f)['entries']}
    listed = {k: ge_ld_listed(raw[k]) for k in ents if raw.get(k)}
    wanted = {no for v in listed.values() for no in v} | set(EXTRA_DOCS)
    look = defaultdict(set)
    for k, e in ents.items():
        if e['scope']:
            for f in e['forms']:
                look[(e['scope'], ge_cmp(f).translate(_LOOK))].add(k)
    look = {k: sorted(v) for k, v in look.items()}
    kix, kst = kks_plan(ents)
    lib = L.walk_pdfs(a.library)
    docs = resolve_docs(lib, wanted, log)
    ge_no_by_title(docs, a, log)
    found = {no: d for no, d in docs.items() if d.get('rel')}
    log('位置圖：GE 清單點名 %d 個文件號（%d 個條目），文件庫找得到 %d 個' % (len(wanted), sum(1 for v in listed.values() if v), len(found)))
    files = sorted({(d['rel'], d['size'], d['mtime']) for d in found.values()})
    n_new, errs = L.ensure_text(a.library, files, a.text_cache, a.jobs, log)
    listed_by_doc = defaultdict(set)
    for k, v in listed.items():
        for no in v:
            listed_by_doc[no].add(k)
    st = Counter()
    pages_info, n_pages = {}, {}
    rec = defaultdict(list)
    by_rel = defaultdict(list)                         # 同一份檔被兩個文件號點名（HT 編號與 GE 圖號）只掃一次
    for no in sorted(found):
        by_rel[found[no]['rel']].append(no)
    for rel in sorted(by_rel):
        nos = by_rel[rel]
        d = found[nos[0]]
        if not d['scope']:
            st['doc_no_scope'] += 1
            continue
        tx = L.load_text(a.library, d['rel'], d['size'], d['mtime'], a.text_cache)
        n_pages[rel] = tx['pages']
        if tx.get('err'):
            st['doc_text_error'] += 1
        for pno, pg in enumerate(tx['pg'], 1):
            if L.is_cover(pg):
                st['pages_cover'] += 1
                continue
            if not pg['words']:
                st['pages_no_text'] += 1
                continue
            info = L.upright_rotation_info(pg)
            R = info['R'] if info['R'] is not None else 0
            sh = {'rel': d['rel'], 'page': pno, 'pg': pg, 'R': R, 'rot_method': info['method'] or 'default', 'ocr': None, 'ge_ocr': None,
                  'nos': nos, 'no0': nos[0], 'doc': d, 'sig': page_sig(pg)}
            pages_info[(d['rel'], pno)] = sh
            st['pages'] += 1
            for r in scan_page(sh, d['scope'], names, look, kix, listed_by_doc, st):
                r['sheet_key'] = (d['rel'], pno)
                r['listed'] = 1 if set(nos) & set(listed.get(r['key'], ())) else 0
                rec[r['key']].append(r)

    # ---- 借位置（反方驗證後的規則）：
    #  alias：兩個條目的現行 KKS（本體＋子件）完全相同、名字也相近（same_name）＝同一顆的兩個編號（括號寫法 '96HDAS-1B (96DP-012B)'、改號 DI-FA-70／DI-FA-702），
    #         互相借引線標註，任何一張圖都可以（form 'alias'，卡上「圖上寫的是同一個 KKS 的另一個編號」、推論）。
    #  body： 子件（KKS 帶尾碼 -MB01／-BG02…）借主設備（同本體、沒有尾碼，**而且是閥**：KKS 設備碼 BODY_EQ）的引線標註，只在子件自己的位置圖上、而且子件在任何圖上都沒有自己的引線標註
    #         （GBD01-D0001 只標閥本體）。
    #         **反過來不借**：控制器、定位器（TIS-2996B＝MKG52BT002、90ESV-2＝MBC01MA004）不借子件（熱電偶 -BT01、致動器 -MA04）的框——
    #         它們在控制箱、DVP 盤，不在感測元件上。
    #  名稱：主設備在對照表沒有 KKS（VA41-91）時，'90VA41-91'（定位器）／'20…'（電磁閥）／'33…'（極限開關）＝功能碼＋閥號 → 借那顆閥，
    #         同樣只在自己的位置圖上（form 'body'）。共用本體的條目 > BODY_MAX 個（盤箱、多點元件）不借。
    kk = defaultdict(set)
    grp = defaultdict(set)
    for k, e in ents.items():
        if e['scope']:
            for x in e['kks']:
                m = GE_KKS_RE.match(ge_cmp(x))
                if m:
                    kk[k].add((m.group(2), m.group(3) or ''))
                    grp[(e['scope'], m.group(2))].add(k)
    by_sheet = defaultdict(lambda: defaultdict(list))
    for k, rs in rec.items():
        for r in rs:
            by_sheet[r['sheet_key']][k].append(r)
    tag_key = {(e['scope'], ge_cmp(e['tag'])): k for k, e in ents.items() if e['scope']}

    def same_name(e1, e2):
        """兩個編號寫法相近（一個包含另一個：括號寫法；或相似度 ≥ 0.7：改號 DI-FA-70／DI-FA-702）——共用 KKS 但名字完全不同的
        （96GN-5C 與管路標籤 96FGAFS-2C）不當別名。"""
        import difflib
        a, b = ge_cmp(e1['tag']), ge_cmp(e2['tag'])
        return a in ge_cmp(' '.join(e2['forms'])) or b in ge_cmp(' '.join(e1['forms'])) or difflib.SequenceMatcher(None, a, b).ratio() >= 0.7

    def donors(k):
        """→ [(主設備鍵, form)]"""
        e = ents[k]
        out = []
        for body, sub in sorted(kk.get(k, ())):
            g = grp[(e['scope'], body)]
            if len(g) > BODY_MAX:
                continue
            for y in sorted(g - {k}):
                if (body, sub) in kk[y] and same_name(e, ents[y]):
                    out.append((y, 'alias'))
                elif sub and (body, '') in kk[y] and body[5:7] in BODY_EQ:   # 主設備是閥（定位器、電磁閥、極限開關裝在閥上）
                    out.append((y, 'body'))
        m = re.match(r'^(?:20|33|90|96)([A-Z].*)$', e['tag'])
        if m:
            y = tag_key.get((e['scope'], ge_cmp(m.group(1))))
            if y and y != k and not kk.get(y):
                out.append((y, 'body'))
        return list(dict.fromkeys(out))
    own_callout = {k for k, rs in rec.items() if any(not r['note'] for r in rs)}
    remote = {k: True for k, e in raw.items() if any(re.search(r'\bREMOTE|\bINSIDE\b', str(v), re.I) for b in e.get('spec') or [] for _f, v in b.get('f') or [])}
    for k in sorted(ents):
        if not ents[k]['scope']:
            continue
        ds = donors(k)
        if k in own_callout or remote.get(k):                 # 自己已有引線標註（TE-2996A 不借控制箱面板上 TIS-2996A 的銘牌）、
            ds = [x for x in ds if x[1] == 'alias']             # 或規格寫明遠端安裝（LE-3461 探棒裝在 SDE 裡）：不借主設備
        if not ds:
            continue
        nos = set(listed.get(k) or ())
        for sk, per in by_sheet.items():
            if any(not r['note'] for r in per.get(k, [])):
                continue
            mine_sheet = bool(set(pages_info[sk]['nos']) & nos)
            for y, form in ds:
                if form == 'body' and not mine_sheet:
                    continue
                for r in per.get(y, []):
                    if r['via'] == 'ge' and not r['note'] and r['form'] not in ('body', 'alias'):
                        rec[k].append(dict(r, key=k, form=form, via='kks', shared=[ents[y]['tag']], listed=1 if mine_sheet else 0))
                        st[form + '_hits'] += 1

    # ---- 每條目：同一處 GE 與 KKS 只留 GE、有標註就不發布表格列、排序、上限
    drops = Counter(dict.fromkeys(('same_place_kks', 'table_with_callout', 'same_box', 'copy_of_other_sheet', 'sheets_over_cap', 'hits_over_cap'), 0))
    out_sel = {}
    for ek in sorted(rec):
        rs = rec[ek]
        ge_boxes = defaultdict(list)
        for r in rs:
            if r['via'] == 'ge':
                ge_boxes[r['sheet_key']].append(r['box'])
        n0 = len(rs)
        rs = [r for r in rs if not (r['via'] == 'kks' and any(overlap(r['box'], b) for b in ge_boxes[r['sheet_key']]))]
        drops['same_place_kks'] += n0 - len(rs)
        if any(not r['note'] for r in rs):
            n0 = len(rs)
            rs = [r for r in rs if r['note'] != NOTE_TABLE]
            drops['table_with_callout'] += n0 - len(rs)
        rs.sort(key=lambda r: (0 if r['listed'] else 1, 1 if r['note'] else 0, 1 if r['form'] in ('body', 'alias', 'text-lookalike') else 0, pages_info[r['sheet_key']]['doc']['doc'],
                               r['sheet_key'][0], r['sheet_key'][1], 0 if r['via'] == 'ge' else 1, round(r['box'][1], 5), round(r['box'][0], 5), r['label']))
        uniq, seen = [], set()
        # 別份 PDF 裡同一張圖的影本（GID01-D0009 p22～31 合訂了 M0144／M0163／M0104／M0170／D0008；EGJ01 與 EGK01 的同一張發電機輔機圖）：
        # 同一個字、同一個框 → 只留一份：清單點名的優先，其次頁數少的（專屬的那份圖，不是合訂本）
        kc_of = lambda r: (r['label'], tuple(round(v, 3) for v in r['box']), pages_info[r['sheet_key']]['sig'])   # noqa: E731
        best = {}
        for r in rs:
            kc = kc_of(r)
            rk = (0 if r['listed'] else 1, n_pages.get(r['sheet_key'][0], 999), r['sheet_key'])
            if kc not in best or rk < best[kc][0]:
                best[kc] = (rk, r['sheet_key'])
        for r in rs:
            k = (r['sheet_key'], tuple(round(v, 4) for v in r['box']))
            if k in seen:
                drops['same_box'] += 1
                continue
            if best[kc_of(r)][1] != r['sheet_key']:
                drops['copy_of_other_sheet'] += 1
                continue
            seen.add(k)
            uniq.append(r)
        order_sheets, per, res = [], Counter(), []
        for r in uniq:
            if r['sheet_key'] not in order_sheets:
                if len(order_sheets) >= LIMIT_SHEETS:
                    drops['sheets_over_cap'] += 1
                    continue
                order_sheets.append(r['sheet_key'])
            if per[r['sheet_key']] >= LIMIT_HITS:
                drops['hits_over_cap'] += 1
                continue
            per[r['sheet_key']] += 1
            res.append(r)
        res.sort(key=lambda r: order_sheets.index(r['sheet_key']))
        if res:
            out_sel[ek] = res

    # ---- sheets（＝pid_ge.json 的 sheets 同一套欄位與算法）
    ref = sorted({r['sheet_key'] for v in out_sel.values() for r in v})
    slug_of = {k: L.slug(k[0], k[1]) for k in ref}
    if len(set(slug_of.values())) != len(slug_of):
        sys.exit('slug 撞號（不同圖紙得到同一個鍵）')
    tags_on = Counter(k for v in out_sel.values() for k in {r['sheet_key'] for r in v})
    sheets_out, grids = {}, {}
    for k in ref:
        sh = pages_info[k]
        d = sh['doc']
        pg, R = sh['pg'], sh['R']
        w_pt, h_pt = L.upright_size(pg, R)
        grid = L.detect_grid(L.border_labels(pg, R))
        grids[k] = grid
        tx_pages = n_pages[d['rel']]
        sheets_out[slug_of[k]] = {
            'rel': d['rel'], 'file': d['rel'].rsplit('/', 1)[-1], 'doc': d['doc'], 'rev': d['rev'], 'title': d['title'],
            'page': k[1], 'pages': tx_pages, 'rot': R, 'rot_method': sh['rot_method'],
            'w_pt': round(w_pt, 1), 'h_pt': round(h_pt, 1), 'label_pt': L.label_height_pt(pg['words']), 'grid': grid,
            'words': len(pg['words']), 'ocr': False, 'tags': tags_on[k], 'src': {'size': d['size'], 'mtime': d['mtime']}, 'kind': 'loc'}
        if TAP_TITLE_RE.search(d['title'] or ''):
            sheets_out[slug_of[k]]['tap'] = 1
    by_ge = {}
    for ek, lst2 in out_sel.items():
        ents_out = []
        for r in lst2:
            b = r['box']
            e = {'sheet': slug_of[r['sheet_key']], 'x': r5(b[0]), 'y': r5(b[1]), 'w': r5(b[2] - b[0]), 'h': r5(b[3] - b[1]),
                 'label': r['label'], 'rel': 'neutral', 'drawn_as': '', 'how': 'text', 'form': r['form'], 'note': r['note'],
                 'via': r['via'], 'units': sorted(r['units']), 'listed': r['listed']}
            if r.get('shared'):
                e['shared'] = list(r['shared'])
            if r.get('stack'):
                e['stack'] = 1
            z, near = L.zone_of(grids[r['sheet_key']], (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
            if z:
                e['zone'] = z
                e['zone_near'] = 1 if near else 0
            ents_out.append(e)
        by_ge[ek] = ents_out

    # ---- stats
    with_listed = [k for k, v in listed.items() if v and ents[k]['scope']]
    loc_listed = [k for k in with_listed if any(e['listed'] for e in by_ge.get(k) or [])]
    docs_out = {}
    for no, d in docs.items():
        docs_out[no] = ({k: d[k] for k in ('doc', 'rel', 'rev', 'title', 'scope', 'alts', 'fallback_copy', 'via_title', 'extra') if k in d and d[k]} if d.get('rel')
                        else {'why': d['why']})
    stats = {
        'entries': est, 'kks': dict(sorted(kst.items())), 'paren_aliases': n_alias,
        'docs_wanted': len(wanted), 'docs_found': len(found), 'docs_missing': sorted(no for no in wanted if no not in found),
        'entries_with_listed': len(with_listed), 'entries_listed_located': len(loc_listed),
        'entries_located': len(by_ge),
        'entries_located_callout': sum(1 for v in by_ge.values() if any(not e['note'] for e in v)),
        'entries_located_only_unlisted': sum(1 for v in by_ge.values() if not any(e['listed'] for e in v)),
        'hits': sum(len(v) for v in by_ge.values()),
        'hits_by_via': dict(sorted(Counter(e['via'] for v in by_ge.values() for e in v).items())),
        'hits_by_note': dict(sorted(Counter(str(e['note']) for v in by_ge.values() for e in v).items())),
        'hits_by_form': dict(sorted(Counter(e['form'] for v in by_ge.values() for e in v).items())),
        'sheets_referenced': len(sheets_out), 'drawings_referenced': len({k[0] for k in ref}),
        'scan': {k: int(v) for k, v in sorted(st.items())},
        'dropped': {k: int(v) for k, v in sorted(drops.items())},
        'not_located_listed_sample': sorted(k for k in with_listed if k not in by_ge)[:40],
        'limits': {'sheets_per_entry': LIMIT_SHEETS, 'hits_per_sheet': LIMIT_HITS, 'col_min': PG.COL_MIN, 'comma_gap': COMMA_GAP,
                   'shared_max_nosub': GE_SHARED_MAX},
        'text_extracted': n_new, 'text_errors': len(errs),
    }
    out = {'kind': 'loc_ge', 'generated_by': GENERATED_BY, 'version': VERSION, 'docs': docs_out, 'sheets': sheets_out, 'by_ge': by_ge, 'stats': stats}
    return out, {'elapsed': time.time() - t0, 'pages': pages_info}


def verify(out, root, keys, vdir, log):
    """印出條目的命中，並把框疊在轉正後的整張圖上（紅框）另存 PNG——人工讀圖核對用。"""
    import fitz
    os.makedirs(vdir, exist_ok=True)
    for key in keys:
        hits = out['by_ge'].get(key) or []
        log('%s：%d 處' % (key, len(hits)))
        by = defaultdict(list)
        for h in hits:
            by[h['sheet']].append(h)
            log('  %s  %s  note=%s via=%s form=%s listed=%s zone=%s' % (h['sheet'], h['label'], h['note'], h['via'], h['form'], h['listed'], h.get('zone')))
        for s, hs in by.items():
            sh = out['sheets'][s]
            doc = fitz.open(os.path.join(root, sh['rel'].replace('/', os.sep)))
            page = doc[sh['page'] - 1]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0).prerotate(sh['rot']))
            from PIL import Image, ImageDraw
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            dr = ImageDraw.Draw(im)
            for h in hs:
                x0, y0 = h['x'] * im.width, h['y'] * im.height
                dr.rectangle([x0 - 6, y0 - 6, x0 + h['w'] * im.width + 6, y0 + h['h'] * im.height + 6], outline=(255, 0, 0), width=4)
            fn = os.path.join(vdir, re.sub(r'[^A-Za-z0-9_.-]', '_', key) + '__' + s + '.png')
            im.save(fn)
            log('  → %s' % fn)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='位置圖定位（GE 原廠編號版；見檔頭 docstring）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（預設 paths.LIBRARY_ROOT；唯讀）')
    ap.add_argument('--ge-tags', default=paths.GE_TAGS, help='GE 原廠編號對照表 ge_tags.json（預設 paths.GE_TAGS）')
    ap.add_argument('--text-cache', default=paths.PID_TEXT_CACHE, help='文字層字框快取目錄（預設 paths.PID_TEXT_CACHE，與 P&ID 共用）')
    ap.add_argument('--jobs', type=int, default=min(8, os.cpu_count() or 1), help='抽文字層用幾個行程（只有快取要補時才用到）')
    ap.add_argument('--out', default=os.path.join(paths.CARDWORK, 'loc_ge.json'), help='輸出（預設 <CARDWORK>\\loc_ge.json）')
    ap.add_argument('--verify', metavar='KEY', nargs='+', help='另印這些條目（"GT|CT-DA-2"）的命中並畫疊框圖')
    ap.add_argument('--verify-dir', default=os.path.join(paths.AMS_LOCAL, 'locverify_ge'), help='疊框圖輸出目錄')
    a = ap.parse_args()
    if not os.path.isdir(a.library):
        sys.exit('找不到文件庫：%s' % a.library)
    if not a.ge_tags or not os.path.exists(a.ge_tags):
        sys.exit('找不到 GE 編號對照表：%s' % a.ge_tags)
    t0 = time.time()
    out, ctx = build(a, print)
    n = PI.write_json(a.out, out, 'loc_ge.json')
    st = out['stats']
    print('寫出 %s（%.2f MB）' % (os.path.basename(a.out), n / 1048576.0))
    print('清單點名位置圖的條目 %d 個，其中 %d 個在點名的圖上找到；全部有位置圖位置的條目 %d 個（有引線標註 %d、只在清單沒點名的圖上 %d）' % (
        st['entries_with_listed'], st['entries_listed_located'], st['entries_located'], st['entries_located_callout'], st['entries_located_only_unlisted']))
    print('命中 %d：via %s、note %s、form %s' % (st['hits'], st['hits_by_via'], st['hits_by_note'], st['hits_by_form']))
    print('圖紙 %d 張（%d 份圖）；找不到檔的文件號 %s' % (st['sheets_referenced'], st['drawings_referenced'], st['docs_missing']))
    print('掃描 %s' % st['scan'])
    print('丟掉 %s' % st['dropped'])
    print('耗時 %.1f 秒' % (time.time() - t0))
    if a.verify:
        verify(out, a.library, a.verify, a.verify_dir, print)


if __name__ == '__main__':
    main()
