# -*- coding: utf-8 -*-
r"""tools/db/pid_ge.py — P&ID 圖面定位（GE 原廠編號版）：GE 編號（96FG-1A、VA13-25…）→ 畫在哪一份 P&ID、PDF 第幾頁、圖上的哪個位置。

為什麼需要：pid_index.py 只替 AMS 現行位號定位；查詢卡的「GE 編號卡」（AMS 沒有的元件也查得到，例：P1 腔壓力傳送器
96FG-1A＝KKS XXMBP70BP001，Mark VIe 訊號 G11.a_96fg1a）同樣要回答「畫在 P&ID 的哪裡」。
**規則全部重用 pid_lib.py／pid_index.py**（文件集、最新版、轉正角、文字層快取、OCR 對照表、scan()／select()、sheets 的算法），
本檔只加 GE 編號特有的兩件事：GE 標籤比對（第二道）與「同一個 KKS 本體的幾個 GE 編號」的歸戶。

== 輸入 ==
  paths.GE_TAGS（hst-docsearch 的 ge_tags.json）：entries 每筆 tag、forms、system（GT／ST／GT-GEN／ST-GEN／?／?-GEN）、kks（XXMBP70BP001；
  子件帶 -KH01／-MB01…）。**條目鍵＝"<system>|<tag>"**（3,956 筆唯一；同一個 tag 在 GT-GEN 與 ST-GEN 各有一筆是常態，例 HV-2952）。
  範圍 scope：system 以 GT 開頭＝'G'、以 ST 開頭＝'S'；其餘（?、?-GEN）不發布、只計數。本站機組＝build_card_aux.GE_SITE_UNITS（G11、G12；S10）。

== 第一道：KKS 球泡（via='kks'）==
  每個有範圍的條目的 KKS 依本站機組展開成「位號」（XXMBP70BP001 → G11MBP70BP001、G12MBP70BP001；YY…／S10… → S10…；沒寫前綴的自己補），
  當成位號集合餵給 pid_lib.build_index → pid_index.scan() → pid_index.select()，與 AMS 位號走**完全同一條路**：
  GE 示意圖上的裸 'MBP70BP001'（沒寫機組）在 GFD01 這種「不寫機組的圖」上是 neutral，兩部機共用同一個位置（D0005-3 p7 實測吃得到）。
  機組前綴的規則：XX／YY／沒寫 → 本範圍全部機組；G11／G12 → 照 build_card_aux.ge_unit_kks 的「GT 清單只印 G11（G11=G12）」兩部機都算，
  **但同一個本體在表內同時有印 G11 與印 G12 的條目時，各照字面**（'ACR UNIT #11'／'#12' 這種逐機組的條目）；
  G21／G22／G31／G32／S20 是二、三號機組的 KKS，**不換成本站**（ge_unit_kks 會把 G21 換成 G11——那是卡片顯示的便宜行事，拿來定位就會把
  二號機組的設備標到一號機組的圖上），計入 stats.kks.other_unit。
  同一個 KKS 本體常有好幾個 GE 編號（閥本體 VA13T-1／定位器 90VA13T-1（-KH01）／電磁閥／極限開關）：本體的位置歸給它們全部，
  標 shared（列出共用的其他編號）。**沒有子件尾碼的條目超過 GE_SHARED_MAX（3）個共用一個本體**（96DT-1A~7 共用接線盒 MKA01XD005、
  'ACR UNIT #nn' 共用盤體）＝不同的設備共用一個盤箱編號，本體的位置不代表它們，整組不歸戶（stats.kks.group_too_big）。
  select() 的等級規則（exact > neutral > typical…）照用：G11 若在 BOP 圖上有寫全名的 exact 符號，GE 示意圖上不寫機組的 neutral 符號會被擠掉
  ——對 GE 編號而言 GE 示意圖才是正本，所以**同一支位號在 GE 圖家族上被擠掉的 neutral 符號補回來**（why 'ge_family_neutral'；
  stats.kks.ge_family_neutral_kept；偏離 pid_index 的地方，理由見 select_kks）。
  **子件 KKS**：GE 圖把定位器／電磁閥／極限開關寫成「本體-子件」（'MKW15QN222-BG01'＝ZT-3462、疊寫的 'MBP71' / 'QN310-MA01'＝20VGC-1）。
  pid_lib 的「尾碼必須相等」把它們當成別的項目（對 AMS 位號是對的），所以子件另做一支位號（'G11MKW15QN222-BG01'，只歸給子件相同的條目），
  執行 scan() 期間把 pid_lib.own_suffix 換成也認 '-XXnn' 的 _own_suffix_ge（**只在本程式的行程裡、不改 pid_lib.py**；本體位號的行為不變）；
  疊寫的子件 pid_lib 的疊寫規則不認（設備段帶尾碼），由 stacked_sub_hits 補（同一個幾何門檻）。子件條目從本體借來的位置（shared）在同一張圖
  已有它自己的標籤時不再列（stats.dropped.parent_on_own_sheet）。

== 第二道：GE 標籤（via='ge'）==
  同一批頁面（scan() 的 sheets：轉正角、封面、驗過的 OCR 對照表都沿用）的文字層字＋OCR 字（分數 ≥ OCR_MIN_SCORE、與文字層任何字重疊的丟掉），
  去掉前後的括號與標點後，以 ge_cmp（去非英數、轉大寫）與條目的 tag／forms **整詞相等**比對（VA21 不會中 VA21-1）。
  **只在範圍相符的圖上比**：圖號家族的系統碼 GFD01／EGJ01 → G、TFD01／EGK01 → S（pid_lib.SCOPE_LETTER）。其他家族（BOP 的 AFF01、
  HRSG 的 BFD01、廠商檔名的副本 X:…）不發布，只統計「如果比的話會命中幾個」（stats.label.offscope）。GE 圖家族的判定依據見 GE_FAMILY_NOTES。
  * 斜線清單：'(96FG-2A/2B/2C)'、'(96FG-25A/B/C)'、'96HDASDP-3A/B/C' 展開（取代末段／取代末幾碼兩種，只收表內有的；form 'text-slash'）
  * 純字母的條目（COMMON、LCI、GSUT、ACV、OCM…）只收**括號裡的字**（'(OCM)'），否則計入 label.alpha_unparenthesized——'COMMON' 是表內的垃圾條目，
    'LCI' 是附註裡的 LOAD COMMUTATED INVERTER
  * 拆寫（'(96FG-' + '1A)'、球泡上下兩行）：GE 圖家族全部頁面實測只有 2 處（TFD01-D0002 p2 'HX' + '-1/'），只計數不處理（label.split_pairs）
  * 引用（note=1）：附註句子（同一行 ≥ 4 個字，pid_lib 的 sentence 規則）；清單欄＝同一頁、同一閱讀方向、同一欄（行首或中心差 ≤ 0.8 個字高）
    由上到下 ≥ COL_MIN（4）個 GE 形的字、相鄰中心距 0.3~2.6 個字高（與 pid_lib 文字層表格列同一個間距門檻）；OCR 字用 pid_lib.ocr_table_tokens。
    **有符號（note=0）的條目，清單格不發布**（stats.dropped.list_with_symbol；比照 pid_index 的 ocr_list_with_symbol）

== 合併、上限、排序 ==
  * 同一條目、同一張圖：GE 標籤與自己的 KKS 標籤**互為最近**、而且中心距離 < MERGE_FRAC×頁面對角線 → 併成一處（框取聯集，form＝via＝'ge+kks'）。
    為什麼不是單純的距離門檻：實測「自己那一對」的距離 q50 0.0062、q90 0.0093，但「離別的條目的 KKS」最近的 5 % 只有 0.0079（密排的熱電偶、
    電磁閥／定位器／閥本體三個標籤圍著同一個本體 KKS），兩個分布重疊；互為最近才分得開（merge_pairs 的說明）。每次執行都把距離分布、
    沒併的原因寫進 stats.merge；GE 標籤緊貼著別的條目的 KKS（< CONFLICT_FRAC）另列 stats.merge.label_next_to_other_kks（對照表 vs 圖面不一致的線索，
    例：EGJ01-D0004 的 (GC-1..4) 與 MKA01 EG001..004 順序相反）
  * G11、G12 落在同一個框、同一級的命中先併成一筆（units 兩個）再套上限；GE 標籤的 units＝範圍內全部機組（GE 示意圖不分機組）
  * 排序：符號在引用之前 → GE 圖家族在其他圖之前（對 GE 編號而言 GE 示意圖是正本；只照圖號排會讓 AFF01 排在 GFD01 前面）→ 文字層在 OCR 之前 →
    圖號 → 頁 → 由上到下、由左到右；每條目最多 6 張圖、每張圖最多 8 處（＝pid_index 的上限），超過的丟掉並計數

== 輸出 cardwork/pid_ge.json（決定性：鍵排序、清單排序、無時間戳、無本機絕對路徑，寫出前以 pid_lib.ABS_PATH_RE 自檢）==
  {"kind":"pid_ge","generated_by":"tools/db/pid_ge.py","version":1,"sheets":{…},"by_ge":{…},"stats":{…}}
  sheets：與 pid.json 的 sheets **同一個 slug、同樣的欄位與算法**（pid_index.build 的 sheets_out 那一段；tags＝這張圖上有幾個 GE 條目），
          所以同一張圖的影像兩邊共用（pid_shots 會檢查兩邊的 rel／page／rot／src／label_pt／w_pt／h_pt 相同）
  by_ge["<system>|<tag>"]＝[{sheet, x, y, w, h（轉正後 0~1、左上角＋寬高，5 位小數）, label（圖上的字）, rel, drawn_as, how('text'|'ocr'),
          form, note, via('ge'|'kks'|'ge+kks'), units[...], conf?, raw?, zone?, zone_near?, shared?[...]}]
  stats：條目數、各種丟掉的原因、合併、清單降級、shared、被引用的圖紙裡不在 pid.json 的幾張（之後 pid_shots 要多出這幾張）…

== 實測（2026-10-24；數字每次執行都會印出來，也都在 stats 裡——別的文件要引用請取自 stats）==
  條目 3,956（有範圍 G 2,385／S 1,558；?、?-GEN 13 不發布）→ 定位 2,454（62.2 %；G 1,389、S 1,065）；有 KKS 的條目 2,851 只有 431 支沒位置，
  沒有 KKS 的 1,092 支只能靠 GE 標籤。被引用 107 張圖紙（38 份圖；GE 圖家族 84 張），其中 54 張不在 pid.json 的 sheets 裡。
  耗時：文字層快取都在時 13 秒（scan 兩道＋全部 372 張圖的 GE 標籤）。
  看圖核對：D0005-3 p7 的 96FG-1A（MBP70BP001＋(96FG-1A)）、96FG-1B、VA13-25 與分層抽樣（verify 目錄的紅框圖）見任務回報。

== 已知限制 ==
  * 線條字的 GE 標籤：OCR 對照表只留 pid_lib.tag_like 認得的字（GE_RE 要兩位數字開頭），'(VA13-15)'、'(FV-24)' 這種不會進表。
    v11（2026-10-25）起另讀 pid_ocr.py --distill-ge 寫的 paths.PID_OCR_GE（括號裡的線條字，只給本工具；pid_ocr_map.json 與 pid_index 不動），
    與對照表的 tokens 走同一套規則（文字層重疊丟、分數門檻、清單欄降級）；以 size／mtime／rot 認頁，不符的整頁不用（stats.ocr_ge.stale）
  * OCR 系統段分數 0.747 這種差一點的（D0005 p7 的 MBP70／QN230＝VA13-15）照 pid_lib 的門檻不收
  * 母條目（TE-203、96PH-G1）圖上只畫子項（TE-203A／B／C）：尾碼必須相等，不給位置，列在 stats.not_located_parent_with_located_children
  * 對照表 KKS 與 GE 圖面不一致（GC-1..4）：兩邊都照實發布（GE 標籤一處、KKS 一處），線索在 stats.merge.label_next_to_other_kks
  * 清單欄規則在現行 GE 圖的文字層上 0 處：GE 圖沒有整頁儀器清單；放寬間距到 4~6 個字高只會抓到一排排疊放的球泡（EGJ01-D0004 p2／p3 讀圖確認是符號），
    所以門檻不放寬

用法：
  py tools/db/pid_ge.py                       # 全用 paths.py 的預設，寫 %LOCALAPPDATA%\AMS\cardwork\pid_ge.json
  py tools/db/pid_ge.py --out X.json --no-ocr
  py tools/db/pid_ge.py --verify "GT|96FG-1A" "GT|VA13-25"     # 另印這些條目的命中並畫疊框圖（紅框）到 --verify-dir
"""
import argparse
import io
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pid_lib as L  # noqa: E402
import pid_index as PI  # noqa: E402
import pid_ocr as PO  # noqa: E402  （只用 overlaps_strict；模組層級不載入 OCR 引擎）
from build_card_aux import GE_SITE_UNITS, GE_SHARED_MAX, ge_cmp, ge_kks  # noqa: E402  （模組層級只有常數與函式定義）

GENERATED_BY = 'tools/db/pid_ge.py'
VERSION = 1
GE_OCR_LOW = 0.65            # GE 線條字（--distill-ge）分數在這與 OCR_MIN_SCORE 之間：只在與自己的 KKS 併成 ge+kks 時收（KKS 相符就排除了誤讀；
                             # 反方驗證 2026-10-25：(VGS-1) 0.748、(FL1-1) 0.747、(VPR7-2) 0.734、(SF-1) 0.71 都緊貼在自己的 KKS 上）
COL_MIN = 4                  # 清單欄：同一欄由上到下至少幾個 GE 形的字
COL_ALIGN = 0.8              # 同一欄：行首（或中心）差 ≤ 幾個字高
COL_GAP = (0.3, 2.6)         # 相鄰兩格的中心距（字高的倍數；＝pid_lib 文字層表格列／ocr_table_tokens 的門檻）
# GE 標籤與它自己的 KKS 標籤併成一處的距離上限（頁面對角線的比例；另須互為最近，見 merge_pairs）。2026-10-24 實測（stats.merge 每次都重量）：
#   互為最近的 2,118 對裡 <0.01 有 1,996、0.01~0.02 有 85、0.02~0.03 有 37（GFD01-D0020 p4 熱電偶標籤在球泡左邊 0.021，讀圖確認是同一顆）；
#   0.03 以上的 own 配對多是子件標籤（電磁閥 20VGST-1、極限開關 33VS4-4H、33VG-8）對閥本體的 KKS——是不同的符號，不併。
MERGE_FRAC = 0.03
CONFLICT_FRAC = 0.012        # GE 標籤離「別的條目的 KKS」這麼近（≈ 自己那一對距離的 q90）就列為對照表 vs 圖面不一致的線索
LIMIT_SHEETS = PI.MAX_SHEETS_PER_TAG
LIMIT_HITS = PI.MAX_HITS_PER_SHEET
GE_FAMILY_NOTES = {
    'GFD01': 'GE 燃機 System Schematic／Instrument Diagram（137T97xx；GE 編號寫在括號裡、KKS 不寫機組）→ G',
    'EGJ01': 'GE 燃機發電機示意圖（Load Equipment 0440、Generator Auxiliary Systems）→ G',
    'TFD01': 'GE 汽機 P&ID（VD1H／VD1L／VD1T、ST Instruments）→ S',
    'EGK01': 'GE 汽機發電機示意圖（Generator Auxiliary Systems、C474 STG Haz Gas）→ S',
}
# 依檔名與內容看過、決定**不**當 GE 圖家族的候選（只計數；stats.ge_families.excluded）
GE_FAMILY_EXCLUDED = {
    'X:IGV VGV': 'noKKS_IGV VGV SYSTEM P&ID_rev-：GFD01-D0018（137T9794）的廠商檔名舊副本，p3 標籤與 D0018-1 p3 相同；發布會重複',
    'X:MIST SKID WATER': 'noKKS_P&ID - WATER MIST SKID：GT 水霧滅火 skid 的廠商圖，位號是廠商自己的 ISA 名（HV111、PSH111），不是 GE 編號',
    'AFF01': 'CTCI 的 BOP P&ID：D0029／D0031（發電機氫氣密封油）印著 GE 發電機元件名（HS027、LE010），但那是 BOP 圖的引用，依任務只計數',
}
# KKS 那一道也不收的圖紙家族：廠商檔名的舊副本（標籤與代表圖逐字相同，收了卡片會多出重複的一張圖；反方驗證 2026-10-25 模式 C：
# x_4c23b583 p3 的 23DVP-1／90EGV-1／ESV-1 等 11 筆與 GFD01-D0018-1 p3 重複）
GE_KKS_SKIP_FAMILIES = {'X:IGV VGV': GE_FAMILY_EXCLUDED['X:IGV VGV']}
# 只有 GE 這一道要多收的圖號家族（pid_lib.EXTRA_FAMILIES 的格式；**不改 pid_lib**，AMS 設備的 P&ID 位置不受影響）：
# ST Generator Load Equipment Schematic（138T0051、MLI 0440 STG）——檔名的 Load Equipment 讓 kind_of 判成電氣圖，GT 版 EGJ01-D0004
# 已在 pid_lib.EXTRA_FAMILIES，ST 版沒有；汽機發電機的定子 RTD、振動、碳刷等 97 個 GE 編號只畫在這份圖上（反方驗證 2026-10-25 漏網 P1；
# 汽機儀器清單 TLD01-A0104 的 P&ID 欄寫的就是它，95 列）
GE_EXTRA_FAMILIES = {'1-EGK01-D0033': '汽機發電機示意圖（ST Generator Load Equipment Schematic；汽機儀器清單列為 P&ID）'}
_PAREN_OPEN = '([{'
_EDGE_RE = re.compile(r'^[(\[{]+|[)\]}.,;:]+$')
_EDGE = '=()[]{}<>,;:.\'"“”‘’|\\*# '


def r5(v):
    return round(float(v), 5)


# ================================================================ 條目
def scope_of(system):
    s = system or ''
    return 'G' if s.startswith('GT') else 'S' if s.startswith('ST') else None


def load_entries(path):
    """ge_tags.json → (entries {鍵: 條目}, 名稱索引 {(範圍, ge_cmp): [鍵…]}, stats)。"""
    with open(path, encoding='utf-8') as f:
        j = json.load(f)
    if not isinstance(j.get('entries'), list):
        sys.exit('!! %s 不是 GE 編號對照表（缺 entries）' % os.path.basename(path))
    ents = {}
    for e in j['entries']:
        key = '%s|%s' % (e.get('system') or '', e['tag'])
        if key in ents:
            sys.exit('!! GE 條目鍵重複：%s' % key)
        sc = scope_of(e.get('system'))
        forms = sorted({f for f in [e['tag']] + list(e.get('forms') or []) if f})
        ents[key] = {'key': key, 'tag': e['tag'], 'system': e.get('system') or '', 'scope': sc, 'forms': forms,
                     'kks': list(e.get('kks') or [])}
    names = defaultdict(set)
    for k, e in ents.items():
        if not e['scope']:
            continue
        for f in e['forms']:
            c = ge_cmp(f)
            if c:
                names[(e['scope'], c)].add(k)
    names = {k: sorted(v) for k, v in names.items()}
    st = {'total': len(ents), 'by_system': dict(sorted(Counter(e['system'] for e in ents.values()).items())),
          'scoped': dict(sorted(Counter(e['scope'] for e in ents.values() if e['scope']).items())),
          'unscoped': sum(1 for e in ents.values() if not e['scope']),
          'scoped_with_kks': sum(1 for e in ents.values() if e['scope'] and e['kks']),
          'name_keys_ambiguous': sum(1 for v in names.values() if len(v) > 1)}
    return ents, names, st


def is_alpha_tag(key_cmp):
    return not any(ch.isdigit() for ch in key_cmp)


# ================================================================ 第一道：KKS
def kks_plan(ents):
    """→ (pseudo {位號: [(條目鍵, 子件尾碼)…]}, body_group {(範圍, 本體): [條目鍵…]}, stats)。"""
    st = Counter()
    bodies = defaultdict(list)                      # (範圍, 本體) → [(鍵, 前綴, 子件)]
    for k in sorted(ents):
        e = ents[k]
        if not e['scope']:
            if e['kks']:
                st['unscoped_with_kks'] += 1
            continue
        for kk in e['kks']:
            p = ge_kks(kk)
            if not p:
                st['unparsed'] += 1
                continue
            bodies[(e['scope'], p[1])].append((k, p[0], p[2]))
    pseudo = defaultdict(list)                      # 位號 → [(條目鍵, 子件, 種類 'body'|'sub')]
    subs = {}                                       # 子件位號（G11MKW15QN222-BG01）→ (字母, 機組, 核心)
    group = {}
    for (sc, body), lst in sorted(bodies.items()):
        keys = sorted({k for k, _p, _s in lst})
        group[(sc, body)] = keys
        nosub = sorted({k for k, _p, s in lst if not s})
        if len(nosub) > GE_SHARED_MAX:
            st['group_too_big'] += 1
            st['group_too_big_entries'] += len(keys)
            continue
        site = GE_SITE_UNITS[sc]
        literal = len({pf for _k, pf, _s in lst if pf in site}) >= 2     # 同一本體同時有印 G11 與 G12 的條目：各照字面
        for k, pf, sub in lst:
            if pf in ('XX', 'YY', ''):
                units = site
            elif pf in site:
                units = (pf,) if literal else site
            else:
                st['other_unit'] += 1                                   # G21／G31／S20…：二、三號機組的 KKS
                continue
            for u in units:
                if (k, sub, 'body') not in pseudo[u + body]:
                    pseudo[u + body].append((k, sub, 'body'))
                # GE 圖把子件寫成「本體-子件」（'MKW15QN222-BG01'＝ZT-3462）：子件另成一支位號，只歸給子件相同的條目
                if sub and SUB_RE.match(sub):
                    if not L.AMS_KKS.match(u + body):
                        st['sub_body_with_letter'] += 1                 # 本體帶元件字母又帶子件：沒遇過，不做
                        continue
                    t = '%s%s-%s' % (u, body, sub)
                    subs[t] = (u[0], u[1:], body)
                    if (k, sub, 'sub') not in pseudo[t]:
                        pseudo[t].append((k, sub, 'sub'))
    for v in pseudo.values():
        v.sort()
    st['sub_tags'] = len(subs)
    st['bodies'] = len(group)
    st['bodies_shared'] = sum(1 for v in group.values() if len(v) > 1)
    st['pseudo_tags'] = len(pseudo)
    return dict(pseudo), subs, group, st


SUB_RE = re.compile(r'^[A-Z]{2}\d{2,3}$')       # 子件尾碼（KH01、MB01、BG01…）＝pid_lib.SFX_SUB 去掉 '-'


def build_ix(pseudo, subs):
    """位號集合 → pid_lib 的查表。本體位號照 build_index；子件位號（'G11MKW15QN222-BG01'）build_index 不認，手動掛到同一個核心底下，
    尾碼記 '-BG01'——配合 _own_suffix_ge，圖上的 'MKW15QN222-BG01'（parse_pdf_label 的尾碼 '-BG01'）就只歸給它。"""
    ix = L.build_index(sorted(t for t in pseudo if t not in subs))
    kks = {k: list(v) for k, v in ix['kks'].items()}
    for t in sorted(subs):
        letter, unit, core = subs[t]
        kks.setdefault(core, []).append((t, letter, unit, t[len(letter + unit + core):]))
    ix['kks'] = kks
    ix['cores'] = frozenset(kks)
    ix['units'] = frozenset(tl + tu for v in kks.values() for (_t, tl, tu, _s) in v)
    return ix


_OWN_SUFFIX = L.own_suffix


def _own_suffix_ge(sfx):
    """pid_lib.own_suffix 的延伸（只在本程式呼叫 scan() 的期間替換，不改 pid_lib.py）：子件尾碼 '-BG01' 也算位號自己的尾碼。
    本體位號（與 AMS 位號）不會有這種尾碼，所以對它們的行為與原函式完全相同。"""
    if sfx[:1] == '-' and L.SFX_SUB.match(sfx):
        return sfx
    return _OWN_SUFFIX(sfx)


def select_kks(hits, sheets, dropped, trace, ge_fam_keys, st):
    """pid_index.select() 原樣跑，再把「GE 圖家族上、不寫機組的 neutral 符號」補回來。
    為什麼偏離：select 每支位號只留最好的一級——G11MKW31… 若在 CTCI 的 BOP 圖（AFF01-D0029）上寫成全名（exact），EGJ01 示意圖上的
    裸 'MKW31…'（neutral）就被擠掉，G11 只剩 BOP 圖、G12（BOP 圖沒寫 G12）只剩示意圖，同一個 GE 編號兩部機各指一張圖，
    GE 標籤也併不到 KKS 球泡上。GE 編號的正本是 GE 示意圖，所以補回來（why 'ge_family_neutral'；數量在 stats.kks.ge_family_neutral_kept）。"""
    sel = PI.select(hits, sheets, dropped, trace)
    by = defaultdict(list)
    for h in hits:
        if not h['note'] and h['rel'] == 'neutral' and h['key'] in ge_fam_keys:
            by[h['tag']].append(h)
    for tag in sorted(by):
        have = {(h['key'], tuple(round(v, 4) for v in h['box'])) for h in sel.get(tag, [])}
        add = []
        for h in by[tag]:
            k = (h['key'], tuple(round(v, 4) for v in h['box']))
            if k not in have:
                have.add(k)
                h = dict(h, why=list(h.get('why') or []) + ['ge_family_neutral'])
                add.append(h)
        if add:
            st['ge_family_neutral_kept'] += len(add)
            st['ge_family_neutral_tags'] += 1
            sel[tag] = list(sel.get(tag, [])) + add
    return sel


_EQ_SUB = re.compile(r'^([A-Z]{2}\d{3})-([A-Z]{2}\d{2,3})$')       # 'QN310-MA01'：設備段＋子件


def stacked_sub_hits(words, ix, ctx):
    """文字層一頁 → 疊寫子件標籤的命中 [{tag, rel, drawn_as, box（未旋轉）, label, note}]。
    GE 圖把子件寫成兩行：系統段 'MBP71' 在上、'QN310-MA01' 在下（與 pid_lib.page_candidates 的 stacked 同一個幾何門檻：以閱讀方向為準，
    行距 −1.7 ~ −0.6 個字高、沿行偏移 ≤ 1.2 個字高；同一個設備段有幾個系統段可接時取最近的）。歸戶照 pid_lib._attribute_kks
    （尾碼必須相等；呼叫端已換上 _own_suffix_ge，所以只會歸給「本體-子件」位號）。note：同一行 ≥ 4 個字＝附註句子（1）。"""
    toks = [L.clean_token(w[4]) for w in words]
    frames = [L.reading_frame(w) for w in words]
    sys_by_dir = defaultdict(list)
    for i, t in enumerate(toks):
        if t and L.PDF_KKS_SYS.match(t):
            sys_by_dir[words[i][5]].append(i)
    out = []
    for e, t in enumerate(toks):
        if not t or not _EQ_SUB.match(t):
            continue
        ea, ec, eh, _ = frames[e]
        if eh <= 0:
            continue
        best = None
        for si in sys_by_dir.get(words[e][5], ()):
            sa, sc, _sh, _ = frames[si]
            da, dc = (sa - ea) / eh, (sc - ec) / eh
            if -1.7 <= dc <= -0.6 and abs(da) <= 1.2:
                score = abs(da) + abs(dc + 1.1)
                if best is None or score < best[0]:
                    best = (score, si)
        if not best:
            continue
        si = best[1]
        k = L.parse_pdf_label(toks[si] + t)
        if not k:
            continue
        box = [min(words[si][0], words[e][0]), min(words[si][1], words[e][1]), max(words[si][2], words[e][2]), max(words[si][3], words[e][3])]
        label = '%s %s' % (re.sub(r'\s+', ' ', words[si][4]).strip(), re.sub(r'\s+', ' ', words[e][4]).strip())
        note = 1 if words[e][6] >= 4 else 0
        for tag, rel, drawn, _sfx in L._attribute_kks(ix, k[0], k[1], k[2], ctx, k[3]):
            out.append({'tag': tag, 'rel': rel, 'drawn_as': drawn, 'box': box, 'label': label, 'note': note})
    return out


# ================================================================ 第二道：GE 標籤
def clean_word(s):
    return s.upper().replace('＝', '=').strip().strip(_EDGE)


def expand_word(raw, scope, names, st):
    """圖上的一個字 → [(條目鍵…, 讀法, form)]。逗號分開的各段、斜線清單展開；只收表內有的。"""
    t = clean_word(raw)
    if not t:
        return []
    paren = raw.strip()[:1] in _PAREN_OPEN or raw.strip()[-1:] in ')]}'
    out = []
    for seg in [x for x in t.split(',') if x.strip(_EDGE)]:
        seg = seg.strip(_EDGE)
        parts = seg.split('/')
        first = parts[0].strip(_EDGE)
        reads = []
        if len(parts) == 1:
            reads.append((first, 'text'))
        else:
            if (scope, ge_cmp(first)) in names:
                reads.append((first, 'text-slash'))
                for p in parts[1:]:
                    p = p.strip(_EDGE)
                    if not p:
                        continue
                    cands = []
                    if len(p) < len(first):
                        cands.append(first[:len(first) - len(p)] + p)                 # 取代末幾碼：96FG-25A + B
                    if '-' in first:
                        cands.append(first.rsplit('-', 1)[0] + '-' + p)                # 取代末段：96FG-2A + 2B
                    if (scope, ge_cmp(p)) in names:
                        cands.append(p)                                               # 完整的另一個編號：LE071/LE072
                    ok = sorted({c for c in cands if (scope, ge_cmp(c)) in names})
                    if not ok:
                        st['slash_unresolved'] += 1
                    elif len({ge_cmp(c) for c in ok}) > 1:
                        st['slash_ambiguous'] += 1
                    for c in ok:
                        reads.append((c, 'text-slash'))
            elif (scope, ge_cmp(seg)) in names:
                reads.append((seg, 'text'))                                           # 斜線是編號本身的一部分（52ET/CLOSED）
        for rd, form in reads:
            c = ge_cmp(rd)
            keys = names.get((scope, c))
            if not keys:
                continue
            if is_alpha_tag(c) and not paren:
                st['alpha_unparenthesized'] += 1
                continue
            if len(keys) > 1:
                st['ambiguous_name'] += 1
            out.append((keys, rd, form))
    return out


def column_members(items):
    """items＝[(索引, 字框 [x0,y0,x1,y1,字,方向,…])] → 位在清單欄裡的索引集合（定義見檔頭；以字自己的閱讀方向為準）。"""
    out = set()
    byd = defaultdict(list)
    for i, w in items:
        a, c, h, st = L.reading_frame(w)
        if h > 0:
            byd[w[5]].append((c, a, st, h, i))
    for lst in byd.values():
        lst.sort()
        for mode in (2, 1):                                                   # 行首對齊／中心對齊
            chains = []
            for c, a, stt, h, i in lst:
                al = stt if mode == 2 else a
                best = None
                for ch in chains:
                    lc, la, lh = ch[-1]
                    dc = c - lc
                    da = abs(al - la)
                    if COL_GAP[0] * min(h, lh) <= dc <= COL_GAP[1] * max(h, lh) and da <= COL_ALIGN * min(h, lh) and (best is None or da < best[0]):
                        best = (da, ch)
                if best:
                    best[1].append((c, al, h))
                    best[1].idx.append(i)
                else:
                    ch = _Chain([(c, al, h)])
                    ch.idx = [i]
                    chains.append(ch)
            for ch in chains:
                if len(ch) >= COL_MIN:
                    out.update(ch.idx)
    return out


class _Chain(list):
    idx = None


def load_ocr_ge(path):
    """pid_ocr.py --distill-ge 的輸出 → pages dict（不在就 None）。格式見 pid_ocr.write_ge_map。"""
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    if not isinstance(d, dict) or d.get('kind') != 'pid_ocr_ge' or not isinstance(d.get('pages'), dict):
        sys.exit('GE 線條字表格式不對（要 {"kind":"pid_ocr_ge","pages":{…}}）：%s' % os.path.basename(path))
    return d['pages']


def attach_ocr_ge(sheets, pages):
    """GE 線條字掛到 sheets[(rel, 頁)]['ge_ocr']（只在本行程；輸出的 sheets 記錄不帶它）。檔案大小／修改時間／轉正角不符的頁不用。"""
    st = Counter(present=int(pages is not None), pages=len(pages or {}), used=0, stale=0, tokens=0)
    for key, ent in sorted((pages or {}).items()):
        rel, _, pg = key.rpartition('|')
        sh = sheets.get((rel, int(pg)))
        if sh is None:
            st['not_in_corpus'] += 1
            continue
        if ent.get('size') != sh['fam']['size'] or ent.get('mtime') != sh['fam']['mtime'] or int(ent.get('rot') or 0) != sh['R']:
            st['stale'] += 1
            continue
        sh['ge_ocr'] = ent.get('tokens') or []
        st['used'] += 1
        st['tokens'] += len(sh['ge_ocr'])
    return st


def ge_ocr_dup(b, text, tboxes, gwords):
    """GE 線條字（--distill-ge）的去重：(1) 與文字層位號框真的疊在一起（不加容許邊界，pid_ocr.overlaps_strict），或
    (2) 容許邊界內有寫著同一個 GE 編號的文字層字，才算重複。對照表 tokens 的規則（任何位號字、加容許邊界）會讓緊貼在下一行的
    文字層 KKS 把標籤擋掉（GFD01-D0013-10 p7 的 '(FT-PH-5)' 下一行就是 MBP01 BT010）。"""
    if PO.overlaps_strict(b, tboxes):
        return True
    g = ge_cmp(_EDGE_RE.sub('', (text or '').upper().replace(' ', '')))
    return any(g2 == g and PI.overlaps_text(b, [bx]) for g2, bx in gwords)


def label_hits_page(sh, scope, names, st, publish):
    """一頁 → GE 標籤命中 [{'keys', 'key', 'box'(轉正比例), 'label', 'how', 'form', 'note', 'nk', 'conf'?}]。publish=False 只算數。"""
    pg, R = sh['pg'], sh['R']
    words = pg['words']
    found = []
    geish = []
    for i, w in enumerate(words):
        reads = expand_word(w[4], scope, names, st)
        t = clean_word(w[4])
        if reads or L.GE_RE.fullmatch(t.split('/')[0] if t else ''):
            geish.append((i, w))
        for keys, rd, form in reads:
            found.append((i, keys, rd, form))
    if not found and not (publish and (sh.get('ocr') or sh.get('ge_ocr'))):
        return []
    cand, table = L.page_candidates(words) if found else ([], set())
    col = column_members(geish) if found else set()
    out = []
    for i, keys, rd, form in found:
        w = words[i]
        nk = ''
        if i in table or i in col:
            nk = 'table'
            st['list_col' if i in col else 'list_pidlib'] += 1
        elif w[6] >= 4:
            nk = 'sentence'
            st['sentence'] += 1
        out.append({'keys': keys, 'key': (sh['rel'], sh['page']), 'box': L.to_upright_frac(pg, w[:4], R), 'label': re.sub(r'\s+', ' ', w[4]).strip(),
                    'read': rd, 'how': 'text', 'form': form, 'note': 1 if nk else 0, 'nk': nk})
    # ---- OCR：文字層為準——與文字層「像位號／像 GE 編號」的字重疊的丟掉（＝pid_index 的 text_tag_boxes，再加上 GE 形的字）；分數不夠的不收。
    # 不可拿全部的字來比：重疊的容許邊界（pid_index.OVERLAP_MX／MY）會讓緊鄰的 'NO'、'HP' 這種字把線條字的標籤擋掉
    # （GFD01-D0021 p5 實測：線條字 '(HV314)' 的框離下一顆閥的文字層 'NO' 不到 0.001）
    ent = sh.get('ocr') if publish else None
    toks = (list((ent or {}).get('tokens') or []) + list(sh.get('ge_ocr') or [])) if publish else []
    n_map = len((ent or {}).get('tokens') or [])                 # 前 n_map 個是 pid_ocr_map.json 的，之後是 --distill-ge 的線條字
    if toks:
        tboxes = PI.text_tag_boxes(pg, R)
        gwords = [(ge_cmp(clean_word(w[4])), L.to_upright_frac(pg, w[:4], R)) for _i, w in geish]
        wboxes = tboxes + [bx for _g, bx in gwords]
        w_pt, h_pt = L.upright_size(pg, R)
        ow = []
        for tk in toks:
            b = L.ocr_token_box(tk)
            x0, y0, x1, y1 = b[0] * w_pt, b[1] * h_pt, b[2] * w_pt, b[3] * h_pt
            ow.append([x0, y0, x1, y1, tk[0], 0 if (x1 - x0) >= (y1 - y0) else 3, 1, float(tk[5])])
        otable = L.ocr_table_tokens(ow)
        for j, tk in enumerate(toks):
            b = L.ocr_token_box(tk)
            reads = expand_word(tk[0], scope, names, Counter())
            if not reads:
                continue
            if (PI.overlaps_text(b, wboxes) if j < n_map else ge_ocr_dup(b, tk[0], tboxes, gwords)):
                st['ocr_dup_text'] += 1
                continue
            low = float(tk[5]) < L.OCR_MIN_SCORE
            if low and not (j >= n_map and float(tk[5]) >= GE_OCR_LOW):
                st['ocr_low_score'] += 1
                continue
            for keys, rd, form in reads:
                st['ocr_hits'] += 1
                st['ocr_ge_hits'] += 1 if j >= n_map else 0
                out.append({'keys': keys, 'key': (sh['rel'], sh['page']), 'box': tuple(min(max(v, 0.0), 1.0) for v in b),
                            'label': rd, 'read': rd, 'how': 'ocr', 'form': 'ocr' if form == 'text' else 'ocr-slash',
                            'note': 1 if j in otable else 0, 'nk': 'table' if j in otable else '', 'conf': round(float(tk[5]), 3)})
                if low:
                    out[-1]['low'] = True
    return out


def name_prefixes(names):
    """{範圍: 各名稱（ge_cmp）的真前綴集合}——split_pairs 先用它篩掉不可能是前半段的字（逐對比對太慢）。"""
    out = defaultdict(set)
    for sc, c in names:
        for k in range(1, len(c)):
            out[sc].add(c[:k])
    return out


def split_pairs(words, scope, names, prefixes):
    """拆成兩個字的 GE 標籤（同一行相鄰、或上下兩行）——只計數（實測極少，見檔頭）。"""
    n = 0
    fr = [L.reading_frame(w) for w in words]
    isn = [bool((scope, ge_cmp(clean_word(w[4]))) in names) for w in words]
    pre = prefixes.get(scope, ())
    for i, a in enumerate(words):
        if isn[i] or fr[i][2] <= 0 or not ge_cmp(a[4]) or ge_cmp(a[4]) not in pre:
            continue
        for j, b in enumerate(words):
            if i == j or isn[j] or b[5] != a[5]:
                continue
            if (scope, ge_cmp(a[4] + b[4])) not in names:
                continue
            da, dc = fr[j][0] - fr[i][0], (fr[j][1] - fr[i][1]) / fr[i][2]
            aw = max(a[2] - a[0], a[3] - a[1])
            bw = max(b[2] - b[0], b[3] - b[1])
            if (abs(dc) <= 0.35 and da > 0 and (da - aw / 2.0 - bw / 2.0) / fr[i][2] <= 1.6) or (0.6 <= dc <= 1.7 and abs(da) / fr[i][2] <= 2.5):
                n += 1
    return n


# ================================================================ 組裝
def center(b):
    return (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0


def page_diag(sh):
    w, h = L.upright_size(sh['pg'], sh['R'])
    return w, h, math.hypot(w, h)


VIA_RANK = {'ge+kks': 0, 'ge': 1, 'kks': 2}


def merge_pairs(rec, sheets):
    """同一條目、同一張圖紙：GE 標籤（note 0）與這個條目自己的 KKS 標籤（note 0；含共用本體、子件）**互為最近**而且距離 < MERGE_FRAC×對角線
    才併成一處。互為最近＝(a) 這個 GE 標籤最近的 KKS 框是自己的（比同一張圖上任何別的條目的 KKS 框都近）；(b) 那個 KKS 框最近的 GE 標籤
    就是它。為什麼不用單純的距離門檻：電磁閥 20VGC-1、定位器 90VGC-1 與閥本體 VGC-1 共用本體 KKS，三個 GE 標籤都在閥本體 KKS 的
    兩三公分內；單純門檻會把電磁閥的標籤和閥本體的 KKS 併成一個跨兩個符號的大框。(b) 讓那個 KKS 只跟 VGC-1 的標籤併。
    回 (併了幾處, 統計)。統計裡的距離都是對角線比例。"""
    gl = defaultdict(list)                                         # 圖紙 → [(條目鍵, 記錄鍵, x, y, 框鍵)]（pt）
    kb = defaultdict(dict)                                         # 圖紙 → {框鍵: [x, y, {條目鍵}]}
    for ek in sorted(rec):
        for mk, r in sorted(rec[ek].items(), key=lambda kv: str(kv[0])):
            if r['note']:
                continue
            w, h, _diag = page_diag(sheets[r['key']])
            cx, cy = center(r['box'])
            bk = tuple(round(v, 4) for v in r['box'])
            if r['via'] == 'ge':
                gl[r['key']].append((ek, mk, cx * w, cy * h, bk))
            elif r['via'] == 'kks':
                kb[r['key']].setdefault(bk, [cx * w, cy * h, set(), r['label']])[2].add(ek)
    st = Counter()
    own_d, other_d = [], []
    todo = []
    conflicts = []

    def rec_tag(k):
        return k.split('|', 1)[1]
    for skey in sorted(gl):
        w, h, diag = page_diag(sheets[skey])
        boxes = sorted((kbk, v[:3]) for kbk, v in kb.get(skey, {}).items())
        lab_pts = sorted({bk: (x, y) for _e, _m, x, y, bk in gl[skey]}.items())
        for ek, mk, x, y, bk in gl[skey]:
            own = sorted((math.hypot(x - bx, y - by) / diag, kbk) for kbk, (bx, by, es) in boxes if ek in es)
            if not own:
                continue
            d_own, kbk = own[0]
            oth = [math.hypot(x - bx, y - by) / diag for kbk2, (bx, by, es) in boxes if ek not in es]
            d_oth = min(oth) if oth else None
            bx, by, _es, _lab = kb[skey][kbk]
            g_near = min(lab_pts, key=lambda kv: (math.hypot(kv[1][0] - bx, kv[1][1] - by), kv[0]))[0]
            own_d.append(d_own)
            if d_oth is not None:
                other_d.append(d_oth)
            a_ok = d_oth is None or d_own <= d_oth
            b_ok = g_near == bk
            st['pairs'] += 1
            if not a_ok:
                st['not_nearest_kks'] += 1
                # GE 標籤緊貼著（< CONFLICT_FRAC）別的條目的 KKS：對照表與圖面不一致的線索（例：EGJ01-D0004 的 (GC-2) 印在 MKA01/EG002 下面，
                # 對照表的 GC-2＝MKA01EG003、EG002＝GC-3）。只列出來，不改歸戶
                if d_oth < CONFLICT_FRAC:
                    nb = min(((math.hypot(x - v[0], y - v[1]), kbk2) for kbk2, v in kb[skey].items() if ek not in v[2]))[1]
                    conflicts.append([rec[ek][mk]['label'], kb[skey][nb][3], sorted(rec_tag(e2) for e2 in kb[skey][nb][2]), ek])
            elif not b_ok:
                st['kks_nearer_other_label'] += 1
            elif d_own >= MERGE_FRAC:
                st['mutual_over_max'] += 1
            else:
                todo.append((ek, mk, skey, kbk, d_own))
    merged = 0
    for ek, mk, skey, kbk, d in todo:
        rs = rec[ek]
        g = rs.get(mk)
        if g is None:
            continue
        ks = [(km, k) for km, k in sorted(rs.items(), key=lambda kv: str(kv[0]))
              if k['via'] == 'kks' and not k['note'] and k['key'] == skey and tuple(round(v, 4) for v in k['box']) == kbk]
        if not ks:
            continue
        del rs[mk]
        left = set(g['units'])
        for n, (km, k) in enumerate(ks):
            b = (min(g['box'][0], k['box'][0]), min(g['box'][1], k['box'][1]), max(g['box'][2], k['box'][2]), max(g['box'][3], k['box'][3]))
            m = dict(k)
            m.update({'box': b, 'label': '%s %s' % (g['label'], k['label']), 'form': 'ge+kks', 'via': 'ge+kks', 'derived': False,
                      'units': set(k['units']), 'why': sorted(set(k['why']) | {'merged'})})
            left -= k['units']
            if g['how'] == 'ocr' or k['how'] == 'ocr':
                m['how'] = 'ocr'
                m['conf'] = min(x.get('conf', 1.0) for x in (g, k) if x['how'] == 'ocr')
            del rs[km]
            rs[('merged',) + km[1:]] = m
            merged += 1
        if left:                                                   # GE 標籤不分機組；KKS 那一筆只有其中一部機時，其餘機組也併進第一筆
            rs[('merged',) + ks[0][0][1:]]['units'] |= left
        st['merged_' + ('lt01' if d < 0.01 else 'lt02' if d < 0.02 else 'lt03' if d < 0.03 else 'ge03')] += 1

    def q(v, p):
        if not v:
            return None
        s = sorted(v)
        return r5(s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))])
    out = {k: int(v) for k, v in sorted(st.items())}
    out.update({'own_q50': q(own_d, 0.5), 'own_q90': q(own_d, 0.9), 'own_q99': q(own_d, 0.99), 'own_max': q(own_d, 1.0),
                'other_min': q(other_d, 0.0), 'other_q05': q(other_d, 0.05), 'other_q50': q(other_d, 0.5)})
    conflicts = sorted(conflicts, key=lambda c: (c[3], c[0], c[1]))
    out['label_next_to_other_kks'] = {'n': len(conflicts), 'frac': CONFLICT_FRAC,
                                      'sample': [[c[3], c[0], c[1], c[2]] for c in conflicts[:30]]}
    return merged, out


def drop_conflicts(rec, sheets, ents):
    """合併之後、選位置之前，丟掉三種「位置對、但不是這個編號」的命中（反方驗證 2026-10-25，四個鏡頭看圖確認的錯誤模式）：
    (1) 廠商舊副本（GE_KKS_SKIP_FAMILIES）上的命中：代表圖已經有同一批標籤，收了只是重複。
    (2) 重複印的 GE 標籤（dup_label）：條目在同一張圖已有一處 ge+kks（GE 標籤與自己的 KKS 併成一處），另一個單獨的 GE 標籤卻緊貼別的條目的 KKS
        （≤ CONFLICT_FRAC×對角線，或落在別人的 ge+kks 框內）＝圖面把標籤印了兩次（TFD01-D0004 p4 的 (TE-201R) 也印在 TE-201V 的 BT861 下、
        GFD01-D0008 p6 的 (HV156) 也印在 HV157 的 QM415 下）。條目自己也有的共用 KKS 框不算別人的；名牌（附近沒有 KKS）不受影響。
    (3) KKS 落在印著別的 GE 編號的符號上（kks_under_other_label）：條目只靠 KKS（via=kks）的一處，那個符號旁邊的 GE 標籤是別的條目的
        （單獨的 GE 標籤要「最近的 KKS 框就是這一處」，ge+kks 要這一處落在它的框內），而且（條目在同一張圖已有自己的 GE 標籤，或兩個條目的
        KKS 本體不相交）＝對照表的 GE↔KKS 與圖面不一致（EGJ01-D0004 的 GC-1～4、EGK01-D0027 的 HV-2996J～M、TFD01-D0004 的 TE-243E-1/3、
        GFD01-D0001 的 96CT-IF-1R），或電磁閥的 KKS 少了 -MBnn 而落在閥本體上（20VS4-4、20VG8、20VSC-1）——以圖上的 GE 標籤為準。
        KKS 本體相同、條目在這張圖沒有自己的標籤（極限開關、電磁閥畫在閥本體上）照留，卡片照 shared 寫明是共用。
        標籤「點名」了這個 KKS 框的任一擁有者（同一處標籤歸給的條目之一，或標籤字去分隔符等於擁有者的任一寫法：斜線合寫的
        (39VE-1R/T) 就是條目 39VE-1R/T）就不算衝突。
    (2) 先做：被它丟掉的重複標籤不再拿來否決 (3) 的 KKS（TE-201V 的 BT861 因此保留）。回傳計數。"""
    st = Counter(dict.fromkeys(('skip_family', 'dup_label', 'kks_under_other_label'), 0))
    samples = defaultdict(list)
    body = {ek: {p[1] for p in map(ge_kks, ents[ek]['kks']) if p} for ek in ents}
    fcmp = {ek: {ge_cmp(f) for f in ents[ek]['forms']} for ek in ents}
    for ek in sorted(rec):
        for mk in sorted(rec[ek], key=str):
            if sheets[rec[ek][mk]['key']]['fam']['family'] in GE_KKS_SKIP_FAMILIES:
                del rec[ek][mk]
                st['skip_family'] += 1
    by_sheet = defaultdict(list)
    for ek in sorted(rec):
        for mk, r in sorted(rec[ek].items(), key=lambda kv: str(kv[0])):
            if not r['note']:
                by_sheet[r['key']].append((ek, mk, r))
    dead = set()
    for skey in sorted(by_sheet):
        w, h, diag = page_diag(sheets[skey])
        lim, pad = CONFLICT_FRAC * diag, 0.004 * diag
        items = by_sheet[skey]

        def pt(r):
            cx, cy = center(r['box'])
            return cx * w, cy * h

        def inside(p, r):
            x0, y0, x1, y1 = r['box']
            return x0 * w - pad <= p[0] <= x1 * w + pad and y0 * h - pad <= p[1] <= y1 * h + pad

        def bk(r):
            return tuple(round(v, 4) for v in r['box'])
        owners = defaultdict(set)                                  # KKS 框 → 有這一框的條目（共用本體時不只一個）
        for ek, _mk, r in items:
            if r['via'] in ('kks', 'ge+kks'):
                owners[bk(r)].add(ek)
        kboxes = [(ek, r) for ek, _mk, r in items if r['via'] in ('kks', 'ge+kks')]
        merged_on = {ek for ek, _mk, r in items if r['via'] == 'ge+kks'}
        for ek, mk, r in items:                                    # (2) 重複印的 GE 標籤
            if r['via'] != 'ge' or ek not in merged_on:
                continue
            p = pt(r)
            for ek2, r2 in kboxes:
                if ek2 == ek or ek in owners[bk(r2)]:
                    continue
                q = pt(r2)
                if (inside(p, r2) if r2['via'] == 'ge+kks' else math.hypot(p[0] - q[0], p[1] - q[1]) < lim):
                    dead.add((ek, mk))
                    st['dup_label'] += 1
                    samples['dup_label'].append([ek, r['label'], r2['label'], ek2, PI._slug_or_key(skey[0], skey[1])])
                    break
        labels = [(ek, r) for ek, mk, r in items if r['via'] in ('ge', 'ge+kks') and (ek, mk) not in dead]
        own_label = {ek for ek, _r in labels}
        named = defaultdict(set)                                   # 標籤框 → 這處標籤歸給的條目（斜線展開、同名多條目）
        for ek, r in labels:
            named[bk(r)].add(ek)

        def names_owner(r2, own):
            txt = ge_cmp(_EDGE_RE.sub('', (r2['label'] or '').split(' ')[0]))
            return bool(named[bk(r2)] & own) or any(txt in fcmp[o] for o in own)
        for ek, mk, r in items:                                    # (3) KKS 落在別人標著的符號上
            if r['via'] != 'kks':
                continue
            p = pt(r)
            for ek2, r2 in labels:
                if ek2 == ek or ek2 in owners[bk(r)] or names_owner(r2, owners[bk(r)]):
                    continue
                if r2['via'] == 'ge+kks':
                    near = inside(p, r2)
                else:
                    q = pt(r2)
                    if math.hypot(p[0] - q[0], p[1] - q[1]) >= lim:
                        continue
                    nearest = min(kboxes, key=lambda x: (math.hypot(q[0] - pt(x[1])[0], q[1] - pt(x[1])[1]), x[0]))
                    near = ek in owners[bk(nearest[1])] and bk(nearest[1]) == bk(r)
                if near and (ek in own_label or not (body[ek] & body[ek2])):
                    dead.add((ek, mk))
                    st['kks_under_other_label'] += 1
                    samples['kks_under_other_label'].append([ek, r['label'], r2['label'], ek2, PI._slug_or_key(skey[0], skey[1])])
                    break
    for ek, mk in dead:
        rec[ek].pop(mk, None)
    out = dict(st)
    out['samples'] = {k: sorted(v)[:200] for k, v in sorted(samples.items())}
    return out


def build(a, log):
    t0 = time.time()
    ents, names, est = load_entries(a.ge_tags)
    log('GE 條目 %d（有範圍 %s；沒有範圍 %d；有範圍且有 KKS %d）；名稱鍵撞號 %d' % (
        est['total'], est['scoped'], est['unscoped'], est['scoped_with_kks'], est['name_keys_ambiguous']))
    pseudo, subs, group, kst = kks_plan(ents)
    log('KKS：本體 %d（共用 %d）→ 位號 %d；沒有子件的條目 > %d 個共用一個本體的 %d 組不歸戶；二、三號機組 KKS %d' % (
        kst['bodies'], kst['bodies_shared'], kst['pseudo_tags'], GE_SHARED_MAX, kst['group_too_big'], kst['other_unit']))
    ix = build_ix(pseudo, subs)
    _extra = L.EXTRA_FAMILIES
    L.EXTRA_FAMILIES = dict(_extra, **GE_EXTRA_FAMILIES)
    try:
        corpus = L.build_corpus(a.library, a.text_cache, a.jobs, log)
    finally:
        L.EXTRA_FAMILIES = _extra
    ocr_pages, ocr_present = (None, False) if a.no_ocr else PI.load_ocr_map(a.ocr_map)
    ge_ocr = load_ocr_ge(None if a.no_ocr else a.ocr_ge)
    L.own_suffix = _own_suffix_ge
    try:
        sheets, hits, dropped, ocr_stat, decl, trace, bad_ocr = PI.scan(corpus, ix, ocr_pages, log)
    finally:
        L.own_suffix = _OWN_SUFFIX
    hits = [h for h in hits if h['tag'] in pseudo]
    ost = attach_ocr_ge(sheets, ge_ocr)
    ge_fam = {f['rel']: L.SCOPE_LETTER[f['sys']] for f in corpus['drawings'] if f['sys'] in L.SCOPE_LETTER}
    ge_fam_keys = {k for k in sheets if k[0] in ge_fam}
    kst['ge_family_neutral_kept'] = 0
    kst['ge_family_neutral_tags'] = 0
    sel = select_kks(hits, sheets, dropped, trace, ge_fam_keys, kst)
    foreign = set(decl['foreign']['sheets'])

    # ---- 第一道的命中 → 條目（同框同級的各機組併成一筆）
    rec = defaultdict(dict)                                       # 條目鍵 → {合併鍵: 記錄}
    sfx_used = Counter()
    for tag in sorted(sel):
        unit = tag[:3]
        for h in sel[tag]:
            for ek, sub, kind in pseudo[tag]:
                body = subs[tag][2] if kind == 'sub' else tag[3:]
                if kind == 'sub':
                    same = [x for x, _s2, k2 in pseudo[tag] if k2 == 'sub']                      # 同一個「本體-子件」的其他條目
                else:
                    same = group.get((ents[ek]['scope'], body)) or [ek]
                mk = ('kks', h['key'], tuple(round(v, 4) for v in h['box']), h['rel'], h['drawn_as'], h['note'], h['how'], h['label'])
                r = rec[ek].get(mk)
                if r is None:
                    r = {'key': h['key'], 'box': tuple(h['box']), 'label': h['label'], 'rel': h['rel'], 'drawn_as': h['drawn_as'],
                         'how': h['how'], 'form': h['form'], 'note': h['note'], 'via': 'kks', 'units': set(),
                         'derived': bool(kind == 'body' and sub), 'sub_label': kind == 'sub',
                         'shared': sorted({ents[x]['tag'] for x in same if x != ek} - {ents[ek]['tag']}), 'why': sorted(set(h.get('why') or []))}
                    if h['how'] == 'ocr':
                        r['conf'] = h['conf']
                        if h.get('raw') is not None and h['form'] == 'ocr-fix':
                            r['raw'] = h['raw']
                    rec[ek][mk] = r
                r['units'].add(unit)
                if sub:
                    sfx_used['%s_%s' % (kind, sub[:2])] += 1
    # ---- 第一道之二：疊寫的子件 KKS（'MBP71' 一行、'QN310-MA01' 下一行；pid_lib 的疊寫規則只認不帶尾碼的設備段）
    n_stk = Counter()
    L.own_suffix = _own_suffix_ge
    try:
        for key in sorted(sheets):
            sh = sheets[key]
            if sh['cover'] or PI._slug_or_key(key[0], key[1]) in foreign:
                continue
            ctx = L.make_ctx(sh['fam']['family'], sh['fam']['sys'], False)
            ctx['rej'] = None
            for h in stacked_sub_hits(sh['pg']['words'], ix, ctx):
                n_stk['hits'] += 1
                box = L.to_upright_frac(sh['pg'], h['box'], sh['R'])
                for ek, sub, kind in pseudo.get(h['tag'], ()):
                    if kind != 'sub':
                        continue
                    mk = ('kks', key, tuple(round(v, 4) for v in box), h['rel'], h['drawn_as'], h['note'], 'text', h['label'])
                    r = rec[ek].get(mk)
                    if r is None:
                        same = [x for x, _s2, k2 in pseudo[h['tag']] if k2 == 'sub']
                        r = {'key': key, 'box': box, 'label': h['label'], 'rel': h['rel'], 'drawn_as': h['drawn_as'], 'how': 'text',
                             'form': 'stacked-sub', 'note': h['note'], 'via': 'kks', 'units': set(), 'derived': False, 'sub_label': True,
                             'shared': sorted({ents[x]['tag'] for x in same if x != ek} - {ents[ek]['tag']}), 'why': ['stacked_sub']}
                        rec[ek][mk] = r
                        n_stk['records'] += 1
                    r['units'].add(h['tag'][:3])
    finally:
        L.own_suffix = _OWN_SUFFIX
    kst['stacked_sub_hits'] = n_stk['hits']
    kst['stacked_sub_records'] = n_stk['records']

    # ---- 第二道：GE 標籤（範圍相符的 GE 圖家族才發布；其他家族只計數）
    lst = Counter()
    prefixes = name_prefixes(names)
    off = Counter()
    off_ents = set()
    off_fam = Counter()
    n_split = 0
    lab_raw = 0
    for key in sorted(sheets):
        sh = sheets[key]
        if sh['cover']:
            continue
        fam = sh['fam']
        sc = ge_fam.get(fam['rel'])
        if sc is None:
            for s2 in ('G', 'S'):
                hs = label_hits_page(sh, s2, names, Counter(), False)
                off[s2] += len(hs)
                for h in hs:
                    off_ents.update(h['keys'])
                    off_fam[fam['family']] += 1
            continue
        hs = label_hits_page(sh, sc, names, lst, True)
        n_split += split_pairs(sh['pg']['words'], sc, names, prefixes)
        slug_k = PI._slug_or_key(key[0], key[1])
        if slug_k in foreign:
            lst['foreign_sheet'] += len(hs)
            continue
        for h in hs:
            lab_raw += 1
            for ek in h['keys']:
                mk = ('ge', h['key'], tuple(round(v, 4) for v in h['box']), h['read'])
                if mk in rec[ek]:
                    continue
                r = {'key': h['key'], 'box': tuple(h['box']), 'label': h['label'], 'rel': 'neutral', 'drawn_as': '', 'how': h['how'],
                     'form': h['form'], 'note': h['note'], 'nk': h['nk'], 'via': 'ge', 'units': set(GE_SITE_UNITS[sc]), 'why': []}
                if 'conf' in h:
                    r['conf'] = h['conf']
                if h.get('low'):
                    r['low'] = True
                rec[ek][mk] = r

    for k in ('list_col', 'list_pidlib', 'sentence', 'alpha_unparenthesized', 'ambiguous_name', 'slash_unresolved', 'slash_ambiguous',
              'ocr_dup_text', 'ocr_low_score', 'ocr_hits', 'ocr_ge_hits', 'ocr_ge_low_dropped', 'foreign_sheet'):
        lst[k] += 0                                               # 0 也要寫出來：「這條規則實測 0 處」是事實，不是漏記

    # ---- 合併（同條目、同圖紙：GE 標籤 ↔ KKS 標籤）：互為最近才併（定義見 merge_pairs）
    merged, mst = merge_pairs(rec, sheets)
    n_low = 0                                                     # 分數偏低的 GE 線條字沒併上自己的 KKS：不收（GE_OCR_LOW）
    for ek in rec:
        for mk in [m for m, r in rec[ek].items() if r.get('low') and r['via'] == 'ge']:
            del rec[ek][mk]
            n_low += 1
    lst['ocr_ge_low_dropped'] = n_low
    # ---- 對照表與圖面衝突、廠商舊副本（反方驗證 2026-10-25；定義見 drop_conflicts）
    cst = drop_conflicts(rec, sheets, ents)
    log('衝突過濾：重複印的 GE 標籤 %d、KKS 落在印著別的 GE 編號的符號上 %d、廠商舊副本 %d' % (
        cst['dup_label'], cst['kks_under_other_label'], cst['skip_family']))

    # ---- 每條目：清單降級、排序、上限
    out_sel = {}
    drops = Counter(dict.fromkeys(('parent_on_own_sheet', 'list_with_symbol', 'same_box', 'sheets_over_cap', 'hits_over_cap'), 0))
    for ek in sorted(rec):
        rs = list(rec[ek].values())
        if not rs:
            continue
        # 子件條目（定位器／電磁閥／極限開關）從本體 KKS 借來的位置：同一張圖已有它自己的標籤（GE 編號或「本體-子件」）就不再列本體
        own_sheets = {r['key'] for r in rs if not r['note'] and not r.get('derived')}
        n0 = len(rs)
        rs = [r for r in rs if not (r.get('derived') and r['key'] in own_sheets)]
        drops['parent_on_own_sheet'] += n0 - len(rs)
        has_sym = any(not r['note'] for r in rs)
        if has_sym:
            n0 = len(rs)
            rs = [r for r in rs if not (r['note'] == 1 and r.get('nk') == 'table' and r['via'] == 'ge')]
            drops['list_with_symbol'] += n0 - len(rs)

        def order(r):
            fam = sheets[r['key']]['fam']
            return (1 if r['note'] else 0, 0 if r['key'][0] in ge_fam else 1, 0 if r['how'] == 'text' else 1,
                    fam['doc'] or ('~' + fam['rel'].rsplit('/', 1)[-1]), fam['rel'], r['key'][1], VIA_RANK[r['via']], 1 if r.get('derived') else 0,
                    round(r['box'][1], 5), round(r['box'][0], 5), r['label'])
        rs.sort(key=order)
        uniq, seen = [], set()
        for r in rs:
            k = (r['key'], tuple(round(v, 4) for v in r['box']), r['via'], tuple(sorted(r['units'])))
            if k in seen:
                drops['same_box'] += 1
                continue
            seen.add(k)
            uniq.append(r)
        order_sheets, per, res = [], Counter(), []
        for r in uniq:
            if r['key'] not in order_sheets:
                if len(order_sheets) >= LIMIT_SHEETS:
                    drops['sheets_over_cap'] += 1
                    continue
                order_sheets.append(r['key'])
            if per[r['key']] >= LIMIT_HITS:
                drops['hits_over_cap'] += 1
                continue
            per[r['key']] += 1
            res.append(r)
        res.sort(key=lambda r: order_sheets.index(r['key']))
        if res:
            out_sel[ek] = res

    # ---- sheets（＝pid_index.build 的 sheets_out，逐欄同算法）
    ref_keys = sorted({r['key'] for v in out_sel.values() for r in v})
    slug_of = {k: L.slug(k[0], k[1]) for k in ref_keys}
    if len(set(slug_of.values())) != len(slug_of):
        sys.exit('slug 撞號（不同圖紙得到同一個鍵）')
    tags_on = Counter(k for v in out_sel.values() for k in {r['key'] for r in v})
    sheets_out, grids = {}, {}
    for k in ref_keys:
        sh = sheets[k]
        fam = sh['fam']
        R = sh['R']
        w_pt, h_pt = L.upright_size(sh['pg'], R)
        grid = PI.sheet_grid(sh)
        grids[k] = grid
        label_pt = L.label_height_pt(sh['pg']['words'])
        if label_pt is None and sh['ocr'] and sh['ocr'].get('tokens'):
            hs = sorted(min(t[3] * w_pt, t[4] * h_pt) for t in sh['ocr']['tokens'])
            label_pt = round(hs[len(hs) // 2] / L.OCR_BOX_PER_GLYPH, 2) if len(hs) >= 5 else None
        sheets_out[slug_of[k]] = {
            'rel': fam['rel'], 'file': fam['rel'].rsplit('/', 1)[-1], 'doc': fam['doc'], 'rev': fam['rev'], 'title': fam['title'],
            'page': k[1], 'pages': fam['pages'], 'rot': R, 'rot_method': sh['rot_method'],
            'w_pt': round(w_pt, 1), 'h_pt': round(h_pt, 1), 'label_pt': label_pt, 'grid': grid,
            'words': sh['words'], 'ocr': bool(sh['ocr']), 'tags': tags_on[k], 'src': {'size': fam['size'], 'mtime': fam['mtime']}}
    by_ge = {}
    for ek, lst2 in out_sel.items():
        ents_out = []
        for r in lst2:
            b = r['box']
            e = {'sheet': slug_of[r['key']], 'x': r5(b[0]), 'y': r5(b[1]), 'w': r5(b[2] - b[0]), 'h': r5(b[3] - b[1]),
                 'label': r['label'], 'rel': r['rel'], 'drawn_as': r['drawn_as'], 'how': r['how'], 'form': r['form'], 'note': r['note'],
                 'via': r['via'], 'units': sorted(r['units'])}
            if 'conf' in r:
                e['conf'] = r['conf']
            if r.get('raw') is not None:
                e['raw'] = r['raw']
            if r['via'] != 'ge' and r.get('shared'):
                e['shared'] = list(r['shared'])
            z, near = L.zone_of(grids[r['key']], (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
            if z:
                e['zone'] = z
                e['zone_near'] = 1 if near else 0
            ents_out.append(e)
        by_ge[ek] = ents_out

    # ---- stats
    scoped = [k for k, e in ents.items() if e['scope']]
    located = set(by_ge)
    via_sets = {k: {e['via'] for e in v} for k, v in by_ge.items()}
    pid_sheets = {}
    if a.pid_json and os.path.exists(a.pid_json):
        with open(a.pid_json, encoding='utf-8') as f:
            pid_sheets = json.load(f).get('sheets') or {}
    not_in_pid = sorted(s for s in sheets_out if s not in pid_sheets)
    rec_mismatch = sorted(s for s in sheets_out if s in pid_sheets and any(
        pid_sheets[s].get(k) != sheets_out[s].get(k) for k in ('rel', 'page', 'rot', 'src', 'label_pt', 'w_pt', 'h_pt', 'grid', 'rot_method')))
    unloc = sorted(k for k in scoped if k not in located and ents[k]['kks'])
    # 沒有位置、但「同名加 A／B／C…」的條目有位置：表內的母條目（TE-203＝MAA10BT005），圖上只畫了 TE-203A／B／C（MAA10BT005A…）。
    # 尾碼必須相等，所以不把子項的位置給母條目；列出來給卡片或人工參考
    parents = sorted([k, [k2.split('|', 1)[1] for k2 in (k + c for c in 'ABCDEF') if k2 in by_ge]]
                     for k in scoped if k not in located and any((k + c) in by_ge for c in 'ABCDEF'))
    stats = {
        'entries': est,
        'scoped': len(scoped), 'located': len(located),
        'located_by_scope': dict(sorted(Counter(ents[k]['scope'] for k in located).items())),
        'located_pct': round(100.0 * len(located) / len(scoped), 1) if scoped else 0.0,
        'located_by_via': {'ge_only': sum(1 for v in via_sets.values() if v == {'ge'}),
                           'kks_only': sum(1 for v in via_sets.values() if v == {'kks'}),
                           'merged': sum(1 for v in via_sets.values() if 'ge+kks' in v),
                           'ge_and_kks_separate': sum(1 for v in via_sets.values() if 'ge+kks' not in v and {'ge', 'kks'} <= v)},
        'located_symbol': sum(1 for v in by_ge.values() if any(not e['note'] for e in v)),
        'located_ref_only': sum(1 for v in by_ge.values() if all(e['note'] for e in v)),
        'located_shared': sum(1 for v in by_ge.values() if any(e.get('shared') for e in v)),
        'located_with_kks_none': sum(1 for k in located if not ents[k]['kks']),
        'not_located_with_kks': len(unloc),
        'hits': sum(len(v) for v in by_ge.values()),
        'hits_by_via': dict(sorted(Counter(e['via'] for v in by_ge.values() for e in v).items())),
        'hits_by_note': dict(sorted(Counter(str(e['note']) for v in by_ge.values() for e in v).items())),
        'hits_by_how': dict(sorted(Counter(e['how'] for v in by_ge.values() for e in v).items())),
        'hits_by_form': dict(sorted(Counter(e['form'] for v in by_ge.values() for e in v).items())),
        'hits_by_rel': dict(sorted(Counter(e['rel'] for v in by_ge.values() for e in v).items())),
        'hits_units': dict(sorted(Counter(','.join(e['units']) for v in by_ge.values() for e in v).items())),
        'sheets_referenced': len(sheets_out), 'drawings_referenced': len({k[0] for k in ref_keys}),
        'sheets_not_in_pid_json': {'n': len(not_in_pid), 'slugs': not_in_pid},
        'sheets_record_differs_from_pid_json': rec_mismatch,
        'sheets_on_ge_family': sum(1 for k in ref_keys if k[0] in ge_fam),
        'rot': dict(sorted(Counter(str(s['rot']) for s in sheets_out.values()).items())),
        'rot_method': dict(sorted(Counter(s['rot_method'] for s in sheets_out.values()).items())),
        'ge_families': {'rule': 'pid_lib.SCOPE_LETTER（圖號系統碼）', 'notes': GE_FAMILY_NOTES, 'excluded': GE_FAMILY_EXCLUDED,
                        'drawings': dict(sorted(Counter(v for v in ge_fam.values()).items())),
                        'families': sorted(f['family'] for f in corpus['drawings'] if f['sys'] in L.SCOPE_LETTER)},
        'kks': {k: int(v) for k, v in sorted(kst.items())},
        'kks_sub_used': dict(sorted(sfx_used.items())),
        'kks_scan_dropped': {k: int(v) for k, v in sorted(dropped.items()) if v},
        'label': {k: int(v) for k, v in sorted(lst.items())},
        'label_raw_hits': lab_raw, 'label_split_pairs': n_split,
        'label_offscope': {'hits_if_compared': dict(sorted(off.items())), 'entries_if_compared': len(off_ents),
                           'top_families': [[f, int(n)] for f, n in sorted(off_fam.items(), key=lambda kv: (-kv[1], kv[0]))[:15]]},
        'merge': dict(mst, max_frac_of_diagonal=MERGE_FRAC, merged=merged),
        'conflicts': cst,
        'dropped': {k: int(v) for k, v in sorted(drops.items())},
        'not_located_parent_with_located_children': parents,
        'not_located_sample': {'GT': [ents[k]['tag'] for k in unloc if ents[k]['scope'] == 'G'][:20],
                               'ST': [ents[k]['tag'] for k in unloc if ents[k]['scope'] == 'S'][:20]},
        'ocr_map': {'present': bool(ocr_present), 'pages': int(ocr_stat.get('pages', 0)), 'stale': int(ocr_stat.get('stale', 0)),
                    'rot_conflict': int(ocr_stat.get('rot_conflict', 0)), 'size_mismatch': int(ocr_stat.get('size_mismatch', 0))},
        'ocr_ge': dict(ost),
        'corpus': corpus['stats'],
        'limits': {'sheets_per_entry': LIMIT_SHEETS, 'hits_per_sheet': LIMIT_HITS, 'col_min': COL_MIN, 'col_align': COL_ALIGN,
                   'col_gap': list(COL_GAP), 'ocr_min_score': L.OCR_MIN_SCORE, 'shared_max_nosub': GE_SHARED_MAX},
    }
    out = {'kind': 'pid_ge', 'generated_by': GENERATED_BY, 'version': VERSION, 'sheets': sheets_out, 'by_ge': by_ge, 'stats': stats}
    return out, {'corpus': corpus, 'ents': ents, 'elapsed': time.time() - t0, 'unloc': unloc}


def verify(out, root, keys, vdir, log):
    """印出條目的命中，並把框疊在轉正後的整張圖上（紅框）另存 PNG（整張＋第一處周圍 4 px/pt 放大）。"""
    import fitz
    from PIL import Image, ImageDraw
    os.makedirs(vdir, exist_ok=True)
    for key in keys:
        ents = out['by_ge'].get(key)
        log('\n=== %s ===' % key)
        if not ents:
            log('  查無')
            continue
        by_sheet = defaultdict(list)
        for e in ents:
            by_sheet[e['sheet']].append(e)
            log('  %-6s %-5s %-10s note=%d  x=%.4f y=%.4f w=%.4f h=%.4f  %s  units=%s  label=%r  shared=%s  [%s]' % (
                e['via'], e['how'], e['form'], e['note'], e['x'], e['y'], e['w'], e['h'], e.get('zone', '-'), e['units'], e['label'],
                e.get('shared', ''), e['sheet']))
        safe = re.sub(r'[^A-Za-z0-9_.-]', '_', key)
        for sk, lst in by_sheet.items():
            s = out['sheets'][sk]
            doc = fitz.open(os.path.join(root, s['rel'].replace('/', os.sep)))
            page = doc[s['page'] - 1]
            pix = L.render_upright(page, s['rot'], long_px=2400)
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            dr = ImageDraw.Draw(im)
            for e in lst:
                x0, y0 = e['x'] * im.width, e['y'] * im.height
                x1, y1 = (e['x'] + e['w']) * im.width, (e['y'] + e['h']) * im.height
                dr.rectangle([x0 - 8, y0 - 8, x1 + 8, y1 + 8], outline=(255, 0, 0), width=4)
            p1 = os.path.join(vdir, '%s__%s.png' % (safe, sk))
            im.save(p1)
            for n, e in enumerate(lst[:3]):
                z = 4.0
                pix = L.render_upright(page, s['rot'], zoom=z)
                im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                cx, cy = (e['x'] + e['w'] / 2.0) * im.width, (e['y'] + e['h'] / 2.0) * im.height
                box = (int(max(0, min(cx - 500, im.width - 1000))), int(max(0, min(cy - 350, im.height - 700))))
                cr = im.crop((box[0], box[1], box[0] + 1000, box[1] + 700))
                dr = ImageDraw.Draw(cr)
                for e2 in lst:
                    x0, y0 = e2['x'] * im.width - box[0], e2['y'] * im.height - box[1]
                    x1, y1 = (e2['x'] + e2['w']) * im.width - box[0], (e2['y'] + e2['h']) * im.height - box[1]
                    dr.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], outline=(255, 0, 0), width=3 if e2 is e else 1)
                cr.save(p1[:-4] + '__crop%d.png' % n)
            doc.close()
            log('  圖紙 %s：%s 第 %d／%d 頁 rot=%d → %s' % (sk, s['file'], s['page'], s['pages'], s['rot'], os.path.basename(p1)))


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='P&ID 圖面定位（GE 原廠編號版；見檔頭 docstring）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（預設 paths.LIBRARY_ROOT；唯讀）')
    ap.add_argument('--ge-tags', default=paths.GE_TAGS, help='GE 原廠編號對照表 ge_tags.json（預設 paths.GE_TAGS）')
    ap.add_argument('--text-cache', default=paths.PID_TEXT_CACHE, help='文字層字框快取目錄（預設 paths.PID_TEXT_CACHE）')
    ap.add_argument('--ocr-map', default=paths.PID_OCR_MAP, help='OCR 對照表（預設 paths.PID_OCR_MAP）')
    ap.add_argument('--no-ocr', action='store_true', help='不讀 OCR 對照表（也不讀 --ocr-ge）')
    ap.add_argument('--ocr-ge', default=paths.PID_OCR_GE, help='括號線條字 GE 標籤表（pid_ocr.py --distill-ge；預設 paths.PID_OCR_GE；不在就只用對照表）')
    ap.add_argument('--pid-json', default=paths.PID_JSON, help='pid_index.py 的輸出（只讀：統計哪些圖紙不在 pid.json）')
    ap.add_argument('--jobs', type=int, default=min(8, os.cpu_count() or 1), help='抽文字層用幾個行程（只有快取要補時才用到）')
    ap.add_argument('--out', default=os.path.join(paths.CARDWORK, 'pid_ge.json'), help='輸出（預設 <CARDWORK>\\pid_ge.json）')
    ap.add_argument('--verify', metavar='KEY', nargs='+', help='另印這些條目（"GT|96FG-1A"）的命中並畫疊框圖')
    ap.add_argument('--verify-dir', default=os.path.join(paths.AMS_LOCAL, 'pidverify_ge'), help='疊框圖輸出目錄')
    a = ap.parse_args()
    if not os.path.isdir(a.library):
        sys.exit('找不到文件庫：%s' % a.library)
    if not a.ge_tags or not os.path.exists(a.ge_tags):
        sys.exit('找不到 GE 編號對照表：%s' % a.ge_tags)
    t0 = time.time()
    out, ctx = build(a, print)
    n = PI.write_json(a.out, out, 'pid_ge.json')
    st = out['stats']
    print('寫出 %s（%.2f MB）' % (os.path.basename(a.out), n / 1048576.0))
    print('定位 %d／%d 個有範圍的條目（%.1f%%；%s）：%s；有符號 %d、只有引用 %d、shared %d' % (
        st['located'], st['scoped'], st['located_pct'], st['located_by_scope'], st['located_by_via'], st['located_symbol'],
        st['located_ref_only'], st['located_shared']))
    print('命中 %d：via %s、note %s、how %s、form %s' % (st['hits'], st['hits_by_via'], st['hits_by_note'], st['hits_by_how'], st['hits_by_form']))
    print('圖紙 %d 張（%d 份圖；GE 圖家族 %d 張）；不在 pid.json 的 %d 張；與 pid.json 記錄不同的 %d 張' % (
        st['sheets_referenced'], st['drawings_referenced'], st['sheets_on_ge_family'], st['sheets_not_in_pid_json']['n'],
        len(st['sheets_record_differs_from_pid_json'])))
    print('KKS %s；子件 %s；scan 丟掉 %s' % (st['kks'], st['kks_sub_used'], st['kks_scan_dropped']))
    print('標籤 %s；原始命中 %d；拆寫 %d；其他家族若比會中 %s' % (st['label'], st['label_raw_hits'], st['label_split_pairs'], st['label_offscope']))
    print('合併 %s' % st['merge'])
    print('丟掉 %s' % st['dropped'])
    print('耗時 %.1f 秒' % (time.time() - t0))
    if a.verify:
        verify(out, ctx['corpus']['root'], a.verify, a.verify_dir, print)


if __name__ == '__main__':
    main()
