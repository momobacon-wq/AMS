# -*- coding: utf-8 -*-
r"""tools/db/pid_index.py — P&ID 圖面定位索引：現行 AMS 位號 → 畫在哪一份 P&ID、PDF 第幾頁、圖上的哪個位置。

為什麼需要：查詢卡已經有「圖控 HMI 畫面位置」，現場人員同樣想知道這台儀器在 P&ID 的哪一張、哪一塊。
卡片原本只有端子表／儀器清單抄來的一個圖號（沒有頁、沒有位置，而且端子表抄的圖號只有約 83 % 是對的），
本工具直接去讀圖：把文件庫裡現行的 P&ID 逐頁比對，輸出每支位號在轉正後圖紙上的 0~1 比例框，
配合 tools/db/pid_shots.py 的整張圖影像就能直接標點。規則都在 tools/db/pid_lib.py（檔頭有每一條的由來），
這裡只記「這支驅動程式怎麼把它們組起來」與實測數字。

== 流程 ==
  1. AMS 現行位號（hmi_index.load_ams；母數＝不以 JK 開頭的位號，與圖控 HMI 同一個母數）
  2. pid_lib.build_corpus：現場走訪文件庫 → P&ID 類的檔 → 圖號家族 → 每張圖只留最新版（二、三號機組專屬圖不收）
  3. 逐頁：封面（A4／Letter 直式）跳過；文字層字框（paths.PID_TEXT_CACHE 快取）→ pid_lib.match_page →
     以 to_upright_frac 換成轉正後的比例（**座標是未旋轉空間，一定要走這個函式**）
  4. 有 OCR 對照表（tools/db/pid_ocr_map.json，pid_ocr.py --distill 離線產生並 commit）就併進來：
     * 對照表的鍵是「<相對路徑>|<頁>」，每筆記著 PDF 的 size／mtime；與磁碟上的檔不符＝過期，**整筆不用**並計數——
       而且結尾會印 '!!' 開頭的一行點名是哪幾份圖、哪些原本靠 OCR 定位的位號這次沒有位置了（loud；回傳碼仍是 0）。
       PDF 重新同步後只要修改時間變了就會這樣，要補回來得重跑 pid_ocr.py 再 --distill
     * **文字層為準**：OCR 的字只要與文字層任何一個**含有 KKS 核心**或像位號的字重疊就丟掉（text_tag_boxes），只補文字層
       沒有的地方。照常蒸餾的對照表本來就不含這些字，所以 stats.ocr_map.tokens_dup_text 平常是 0；不是 0 代表對照表
       是用舊規則蒸餾的（結果一樣，只是該重新 --distill 了）
     * OCR 命中要過辨識分數門檻（0.75）與安全的形近字修復（pid_lib.match_ocr_tokens）；唯一放寬到 0.70 的是條件很嚴的
       「差一點點的疊寫標籤」，接受了幾處、是哪幾支都會印出來（stats.ocr_near），每一處都要讀圖核對
     * 頁面的轉正角：文字層 ≥ 400 字用文字層；否則用對照表的 rot。**兩者不同時那一頁的對照表整筆不用**（計入
       stats.ocr_map.rot_conflict 並印出來）：那代表 OCR 是在側躺的影像上跑的，或 rot 記成了別的慣例，框的位置不可信。
       對照表記的 w_pt／h_pt 與「照它的 rot 轉正後的尺寸」不符也整筆不用（size_mismatch；沒有文字層可交叉驗證的頁靠這條擋）
     * **OCR 讀到的儀器清單不是符號**：整頁的 INSTRUMENT LIST（TDM01-D1205 p7／p8）裡一欄一欄的位號標成 note=1
       （pid_lib.ocr_table_tokens；分數不夠的字不會成為命中，但仍交給它判斷「這一欄是不是清單」）。已經有符號位置的位號，
       OCR 的清單格不發布（stats.dropped.ocr_list_with_symbol）——清單裡上下左右都是只差一個數字的兄弟位號，
       同類誤讀（6 讀成 5）在這裡最容易歸錯戶，實測抓到 1 處；只有清單可找的位號照留，卡片要說明那是清單
  5. **宣告＋建置時驗證**的規則（常數與每一條的證據都在 pid_lib.py；驗不過就不套用、計數並印出來；套用情形在 stats 的
     train／foreign／air／overrides）：
     * TRAIN_TYPICALS  同型各台共用的圖（TCM01-D1114 找註記；TDM01-D1205 驗 OCR 對照表的清單結構）→ rel=train
     * FOREIGN_SHEETS  圖上自己聲明不是本機組組態的圖紙（GFD01-D0013 的 X2 那一張）→ 整頁不發布（dropped.foreign_sheet）
     * AIR_SHEETS      儀用／廠用空氣分配圖 → 別的系統的位號是用氣點，note=3
     * HIT_OVERRIDES   人工讀圖確認的逐處覆寫（TDM01-D1205 p5 的迴路詳圖小圖 → note=4）
  6. 每支位號只留**最好的一級**（exact > neutral > typical > loop > train），**等級只看符號命中（note=0）**；
     引用（note>0）絕不把等級較低的符號擠掉，留下來的條件見 select()。只有引用的位號照樣發布（stats.located_ref_only）
  7. 排序：符號（note=0）在引用之前 → 文字層在 OCR 之前 → 圖號 → 頁 → 由上到下、由左到右；
     每支位號最多 6 張圖、每張圖最多 8 處，超過的丟掉並記在 stats.dropped
  8. 圖框分區（pid_lib.detect_grid；文字層沒有圖框字就用對照表的 border 做容缺擬合）、位號字高 label_pt
     （文字層圖紙＝字框高；沒有文字層的圖紙＝OCR 框換算的字形高度，見 build()）

== 一定要知道的事（細節與證據在 pid_lib.py 檔頭）==
  * **轉正慣例只有一個**：rot＝R＝在 /Rotate 之上再順時針多轉的角度。驗收時務必讀圖：
    TCM01-D1114 p5、BDM01-D2111 p3（/Rotate 270、R=0）與 KND01-D0027-4 p2（/Rotate 0、R=270）。
  * **舊版次的位置絕不發布**。stats.superseded_only 列出「只在舊版／副本找得到」的位號當證據
    （G12HSD10QN101：D0027 第 2 版的文字層有 =G11HSD10QN101，但那是旁通閥下面的舊標註，第 4 版已改掉）。
  * **典型圖要講明白**：G12 的位號有 241 支落在畫成 11 的標籤上（五份 HRSG 廠商 PID），drawn_as 記下圖上寫的機組，
    卡片照著說「這張是以 11 號機繪製的典型圖」。
  * **文字層豐富不代表位號在文字層裡**（D0027 的儀表球泡是線條字）——所以 OCR 工作清單不能只收沒有文字層的頁。

== OCR 工作清單（--worklist FILE；給 tools/db/pid_ocr.py）==
文件集裡每一張圖紙（封面不列）一筆：rel、page、pages、size、mtime、rotate（/Rotate）、R（文字層定出的轉正角；
定不出來＝null，要 OCR 定向）、w_pt／h_pt（顯示尺寸）、words、chars、tag_words、img、reasons、need。
reasons 的三個旗標都**只用文字層**算（所以有沒有對照表，清單都一樣）：
  sparse      沒有可用的文字層：不到 30 個字或不到 400 個字元（線條字、掃描圖）
  referenced  這張圖（整份 PDF）已有 AMS 位號被文字層定位到——同一份圖常有零星的向量字（BFD01 的 HAD10 控制閥）
  expected    這頁的文字層畫了某個 KKS 系統（功能碼三個字母，如 HSD、LAC、HAD），而 AMS 在同一機組字母、同一系統
              還有位號沒被文字層定位到——位號多半就在這張圖，只是畫成線條字（D0027-4 p2／p3 就是靠這條進來的）
**need ＝ sparse OR referenced OR expected**。任務說明原訂 need＝sparse OR referenced、expected 只是提示旗標，
但那樣使用者的例子 D0027-4 p2（953 個字、文字層定位 0 支）會被排除在預設 OCR 範圍外，所以把 expected 定義得更嚴
（必須同時「這頁畫了該系統」且「該系統還有位號沒著落」）並納入 need。pid_ocr --scope all 則是清單全部。

== 用法 ==
  py tools/db/pid_index.py                         # 全用 paths.py 的預設，寫 %LOCALAPPDATA%\AMS\cardwork\pid.json
  py tools/db/pid_index.py --no-ocr                # 不讀 OCR 對照表（只用文字層）
  py tools/db/pid_index.py --ocr-map X.json --out Y.json
  py tools/db/pid_index.py --worklist W.json       # 另寫 OCR 工作清單
  py tools/db/pid_index.py --verify G12HSD10QN101 C10LAB22BF001
        # 另印這些位號的命中，並各畫一張疊框圖（轉正後整張圖＋紅框）與一張放大圖到 --verify-dir（預設 %LOCALAPPDATA%\AMS\pidverify）
  py tools/db/pid_index.py --library D:\lib --sqlite D:\AmsDb.sqlite --text-cache D:\pidtext --jobs 8

輸出（契約＝SPEC 第 3 節；決定性：鍵排序、清單排序、無時間戳、無本機絕對路徑，結尾以 regex 自檢）
  {"kind":"pid","generated_by":"tools/db/pid_index.py","version":1,"sheets":{…},"by_tag":{…},"stats":{…}}
  sheets 只列**被引用**的圖紙（by_tag 用到的）；鍵＝slug（pid_lib.slug），同時是 pid_shots 的檔名。
  by_tag[*] 的 x／y 是框的**左上角**、w／h 是寬高，都是轉正後整張圖的 0~1 比例（與 hmi.json 同慣例）。
  SPEC 之外多的欄位：sheets[*].rot_method（text／ocr／text-thin／default）、tags（這張圖上有幾支位號）、
  by_tag[*].form 的 OCR 形式（ocr／ocr-fix／ocr-stacked／ocr-inline）；stats 多了 corpus、superseded_only、rot_method 等對帳數字。
  命中層級的契約（2026-10-10 起；卡片產生器與前端照這個寫文字）：
    note   0 符號旁的標籤｜1 附註句子／清單欄／儀器清單的一格｜2 跨圖訊號旗標｜3 空氣分配圖上的用氣點｜4 迴路詳圖（TYPICAL 小圖）
    label  文字層＝圖上寫的字（拆寫的片段以一個空白相接）；OCR＝**這一筆自己的**正規化讀法（前綴照圖上寫的＋核心，
           兩個框合併的以一個空白相接；斜線與機組清單保留圖上的寫法：'C10PHC10/20BT011'、'G11/12HAP65BP001'），
           不含鄰字、功能碼、管徑、括號。帶尾碼的標籤不會歸給不帶尾碼的位號，所以 label 去掉空白後若與位號不同，
           差別只會在機組前綴（典型圖、不寫機組的圖）、系統碼（同型典型 train）或上述的斜線／清單寫法
    raw    只有 form='ocr-fix' 才有：這個標籤原本讀到的字（'C10LAC50 BTO11'），卡片用來交代「相近字元校正後才對上」
    rel    'train' 現在有兩張圖：TCM01-D1114（drawn_as 'LCC10'）與 TDM01-D1205（drawn_as 'LAC50'）
    同一支位號的各筆命中**不一定同一級**：符號是 typical／train 時，印著位號全名的引用（exact）會一起發布
  另有不屬於契約的追查旁檔（--trace FILE）：每筆命中用到的特殊規則、每筆沒發布的命中與原因（A13 的差異報告用）。

== 實測（2026-10-08；只有文字層，OCR 對照表還沒產生）==
  文件庫 31,896 個 PDF → P&ID 類 712 份（含舊版與副本）→ 398 張圖（HT 編號 382、廠商檔名 16）→ 扣掉二、三號機組專屬 26 張
  → 文件集 372 張圖／1,047 頁（封面 240、圖紙 807：有文字層 595、沒有 212）。
  定位 1,502／1,679（89.5 %）：exact 783、neutral 446、typical 241、train 26、loop 6；HART 1,163／1,328、FF 339／351；
  KKS 1,123／1,217、GE 元件名 373／385、ISA 6／51、其他（時間戳、殘缺名稱）0／26。被引用 109 張圖紙（48 份圖）。
  與 census 探勘的 1,445 支逐支比對：全部同檔同頁、標記中心差 ≤ 0.005；多出的 57 支＝EGJ01-D0004 的 96DT 31 支＋
  TCM01-D1114 的 train 26 支。census 唯一一筆「舊版 fallback」（G12HSD10QN101）已不在輸出裡，改列 stats.superseded_only。
  被文字層定位到的 109 張圖紙 rot 全是 0（其中 4 張有 /Rotate 270 旗標）；rot=270 的 D0027 要等 OCR 對照表。
  OCR 工作清單：807 張圖紙，need 394（sparse 212、referenced 170、expected 46，有重疊）。
  耗時：冷啟動（712 份 PDF 抽文字層、8 個行程）14 秒；有快取 7 秒。
  加上 OCR 對照表之後（同日，tools/db/pid_ocr.py 把 807 張圖紙全部跑完）：定位 1,568／1,679（93.4 %），多出的 66 支全靠 OCR
  （LAC 55、MAJ 6、HSD 5；其中 33 支只在儀器清單裡找得到＝located_note_only）；OCR 命中 216 處／156 支位號，
  被引用 118 張圖紙（54 份圖），rot=270 的 D0027-4 p2 進來了（G12HSD10QN101：typical、drawn_as G11、C-5）。
  沒有文字層的圖紙沒有圖框分區（OCR 讀不到邊條上的單一字元，原因與後續見 pid_ocr.py 檔頭「已知限制」）。
  這些數字每次執行都會印出來，也都在 pid.json 的 stats 裡——別的文件要引用請取自 stats，不要抄這裡的。

== 2026-10-10：六位獨立查核者稽核 10-08 的輸出之後的修正（裁決 A1~A13；位置本身沒有錯，錯的是「一筆命中可以代表什麼」）==
  對 10-08 的輸出（1,568 支／1,876 處／118 張圖紙）逐筆比對的結果（差異報告工具與逐筆清單不在 repo，數字是那次比對印出來的）：
    移除 148 處  ＝帶尾碼的標籤 78（控制閥 ZI／ZIC／ZIO 回授球泡 N1／B1／B2 52、RTD 的 A／B 元件球泡與清單的 A／B／AB 列 22、
                  MAV01BP272 與 BP272C 互標 2、MKW15BL00x-BL01 2）＋GFD01-D0013 只適用 unit 2-2 的那一張 70
    改列引用 98 處＝跨圖訊號旗標 15（note 2）＋空氣分配圖的用氣點 72（note 3）＋TDM01-D1205 p5 迴路詳圖小圖裡的 11（note 4）
    新增 98 處   ＝給水泵組同型典型 70（LAC60／LAC70 取 LAC50 的符號位置，另含它們在小圖裡的引用）＋斜線／機組清單 14＋
                  差一點點的疊寫標籤 6＋合併框切開多出來的 6＋等級規則 2
    沒有任何位號因此失去位置；新定位 14 支（LAC60／LAC70 12、G11HAD10QN003／QN004）→ 1,582／1,679（94.2 %）；
    66 支位號的第一個標記換了地方（從旗標／用氣點／元件球泡／別人的球泡換到自己的符號）。被引用 117 張圖紙。
  還做不到的（已知限制）：C10LAC50BP005 主圖上的球泡與 C10LAC50BT029 的球泡 OCR 沒讀到（前者只有小圖與清單、後者只有清單；
  這一輪不換 OCR 配方重跑，否則已稽核的讀數全部作廢）；同一支位號的幾個球泡（傳送器／元件／DCS 顯示）之間的先後仍是由上到下；
  45 支 ISA 名的循環水儀器（圖上寫 X-TE-CW011-XBE）沒有比對規則。
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

MAX_SHEETS_PER_TAG = 6                 # 每支位號最多列幾張圖
MAX_HITS_PER_SHEET = 8                 # 同一支位號在同一張圖最多留幾處
OVERLAP_MX, OVERLAP_MY = 0.004, 0.006  # 「OCR 的字與文字層的位號重疊」的容許邊界（圖寬／圖高的比例；ocr 探勘 compare() 的值）
VERIFY_DIR = os.path.join(paths.AMS_LOCAL, 'pidverify')


def r5(v):
    return round(float(v), 5)


def tail_of(family):
    return re.sub(r'^HT\d-', '', family or '')


def load_ocr_map(path):
    """OCR 對照表 → (pages dict 或 None, 是否存在)。格式見 SPEC 第 4 節；壞檔直接中止並說是哪裡壞
    （那是 commit 進 repo 的檔，不該壞；手改壞了要看得出是哪一頁，而不是一串 traceback）。"""
    if not path or not os.path.exists(path):
        return None, False
    name = os.path.basename(path)
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
    except ValueError as e:
        sys.exit('OCR 對照表不是合法的 JSON：%s（%s）' % (name, str(e)[:80]))
    if not isinstance(d, dict) or d.get('kind') != 'pid_ocr' or not isinstance(d.get('pages'), dict):
        sys.exit('OCR 對照表格式不對（要 {"kind":"pid_ocr","pages":{…}}）：%s' % name)
    for key, ent in d['pages'].items():
        ok = isinstance(ent, dict) and isinstance(ent.get('tokens') or [], list)
        if ok:
            for tk in ent.get('tokens') or []:
                if not (isinstance(tk, list) and len(tk) >= 6 and isinstance(tk[0], str)
                        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in tk[1:6])):
                    ok = False
                    break
        if not ok:
            sys.exit('OCR 對照表 %s 的這一頁格式不對（tokens 每筆要 [原文, cx, cy, w, h, 分數]）：%s' % (name, key.rsplit('/', 1)[-1]))
    return d['pages'], True


_KKS_CORE_RE = re.compile(L.KKS_CORE)


def text_tag_boxes(pg, R):
    """這一頁文字層裡所有「像位號」的標籤框（轉正後比例）——不管 AMS 有沒有這支。OCR 的字與它們重疊就不用。
    **含有 KKS 核心的字一律算**（2026-10-10 裁決 A12），不只是比對器認得的寫法：CTCI 的 AFF01 圖把控制閥的 ZI／ZIC／ZIO
    回授球泡寫成「核心＋元件碼」（'G11MAN31QN001N1'），舊版的文字層比對器不認這種寫法、這裡也就沒列，結果 OCR 把同一個
    文字層的字再讀一次、用比較寬鬆的搜尋歸給閥本身，卡片上還寫成「OCR 讀圖（線條字，不在 PDF 文字層）」——26 支位號 52 處。
    文字層有的字，OCR 就不該再有發言權；文字層比對器不認的寫法，寧可兩邊都不收。"""
    cand, _table = L.page_candidates(pg['words'])
    out = []
    for text, box, form, _members in cand:
        if L.parse_pdf_label(text) or (form == 'word' and (L.GE_RE.fullmatch(text) or L.ISA_RE.match(text) or L.PDF_KKS_SYS.match(text)
                                                           or L.PDF_KKS_EQ.match(text) or _KKS_CORE_RE.search(text))):
            out.append(L.to_upright_frac(pg, box, R))
    return out


def overlaps_text(tb, boxes):
    cx, cy = (tb[0] + tb[2]) / 2.0, (tb[1] + tb[3]) / 2.0
    for b in boxes:
        if b[0] - OVERLAP_MX <= cx <= b[2] + OVERLAP_MX and b[1] - OVERLAP_MY <= cy <= b[3] + OVERLAP_MY:
            return True
        bx, by = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        if tb[0] - OVERLAP_MX <= bx <= tb[2] + OVERLAP_MX and tb[1] - OVERLAP_MY <= by <= tb[3] + OVERLAP_MY:
            return True
    return False


def _slug_or_key(rel, page):
    try:
        return L.slug(rel, page)
    except ValueError:
        return '%s|%d' % (rel.rsplit('/', 1)[-1], page)


def _drop(trace, why, tag, key, box, label, how):
    """沒發布的命中記一筆（--trace 才寫出去；A13 的差異報告靠它說明每一筆為什麼不見）。box＝轉正後比例 (x0, y0, x1, y1)。"""
    trace.append({'why': why, 'tag': tag, 'sheet': _slug_or_key(key[0], key[1]), 'x': r5(box[0]), 'y': r5(box[1]),
                  'w': r5(box[2] - box[0]), 'h': r5(box[3] - box[1]), 'label': label, 'how': how})


def scan(corpus, ix, ocr_pages, log):
    """逐張圖逐頁比對 → (sheets, hits, dropped, ocr_stat, decl, trace)。
    sheets[(rel, page)]＝每一頁的內部記錄（含封面）；hits＝未篩選的全部命中（文字層＋OCR），note 已是發布用的代碼；
    decl＝各條「宣告＋建置時驗證」規則這次套用的情形（train／foreign／air／overrides）；trace＝在這一步就沒發布的命中與原因。"""
    sheets = {}
    hits = []
    dropped = Counter()
    ocr_stat = Counter()
    used_keys = set()
    trace = []
    bad_ocr = defaultdict(set)                                        # 對照表不能用的頁：原因 → 檔名（A9 要印出來）
    decl = {'train': {'declared': len(L.TRAIN_TYPICALS), 'applied': 0, 'families': [], 'evidence': {}},
            'foreign': {'declared': len(L.FOREIGN_SHEETS), 'applied': 0, 'sheets': []},
            'air': {'declared': len(L.AIR_SHEETS), 'applied': 0, 'sheets': []},
            'overrides': {'declared': len(L.HIT_OVERRIDES), 'hits': 0, 'unmatched': 0}}
    ov_used = Counter()
    for fam in corpus['drawings']:
        pages = L.drawing_pages(corpus, fam)
        tail = tail_of(fam['family'])
        # ---- 第一輪：每頁的記錄；OCR 對照表那一筆能不能用；轉正角
        recs = []
        for pno, pg in enumerate(pages, 1):
            key = (fam['rel'], pno)
            cover = L.is_cover(pg)
            info = L.upright_rotation_info(pg)
            n_tag, _hs, systems = L.tag_word_stats(pg['words'])
            sh = {'fam': fam, 'rel': fam['rel'], 'page': pno, 'cover': cover, 'pg': pg, 'info': info, 'words': len(pg['words']),
                  'chars': sum(len(w[4]) for w in pg['words']), 'tag_words': n_tag, 'systems': systems, 'ocr': None, 'text_tags': set()}
            sheets[key] = sh
            recs.append(sh)
            ent = ocr_pages.get('%s|%d' % (fam['rel'], pno)) if ocr_pages else None
            if ent is not None:
                used_keys.add('%s|%d' % (fam['rel'], pno))
                rot_e = int(ent.get('rot') or 0)
                uw, uh = L.upright_size(pg, rot_e) if rot_e in (0, 90, 180, 270) else (0, 0)
                name = fam['rel'].rsplit('/', 1)[-1]
                if ent.get('size') != fam['size'] or ent.get('mtime') != fam['mtime']:
                    ocr_stat['stale'] += 1
                    bad_ocr['stale'].add(name)
                    ent = None
                elif cover:
                    ocr_stat['cover'] += 1
                    ent = None
                elif rot_e not in (0, 90, 180, 270) or (info['method'] == 'text' and info['R'] != rot_e):
                    # 文字層（≥ 400 字）定出的轉正角與對照表不同：對照表那一頁多半是在側躺的影像上辨識的，或 rot 記成了別的慣例
                    # （例如記成「總旋轉」）。兩種情況框的位置都不可信，整筆不用，寧可回到只有文字層。
                    ocr_stat['rot_conflict'] += 1
                    bad_ocr['rot_conflict'].add(name)
                    log('  注意：OCR 對照表 %s 第 %d 頁的 rot=%s 與文字層定出的 R=%s 不符，整筆不用' % (name, pno, ent.get('rot'), info['R']))
                    ent = None
                elif ent.get('w_pt') and ent.get('h_pt') and (abs(ent['w_pt'] - uw) > 2.0 or abs(ent['h_pt'] - uh) > 2.0):
                    # 對照表記的轉正後尺寸與「這一頁照它的 rot 轉正」算出來的不符 ＝ rot 差了 90 度（沒有文字層可以交叉驗證的頁靠這條擋）
                    ocr_stat['size_mismatch'] += 1
                    bad_ocr['size_mismatch'].add(name)
                    log('  注意：OCR 對照表 %s 第 %d 頁的尺寸 %sx%s 與 rot=%d 不符（應為 %.0fx%.0f），整筆不用' % (
                        name, pno, ent.get('w_pt'), ent.get('h_pt'), rot_e, uw, uh))
                    ent = None
            sh['ent'] = ent
            # 轉正角：文字層夠多字 → 文字層；否則 OCR 對照表；再不然薄文字層；最後信任 /Rotate
            if info['method'] == 'text':
                R, how_r = info['R'], 'text'
            elif ent is not None:
                R, how_r = int(ent.get('rot') or 0) % 360, 'ocr'
            elif info['R'] is not None:
                R, how_r = info['R'], 'text-thin'
            else:
                R, how_r = 0, 'default'
            sh['R'], sh['rot_method'] = R, how_r
        # ---- 這張圖的宣告規則（每一條都在建置時驗證；驗不過就不套用、計數並印出來）
        train_ok = False
        tr = L.TRAIN_TYPICALS.get(tail)
        if tr:
            if 'note' in tr:
                train_ok = L.train_note_found(pages, tr['note'])
                why_not = '圖上找不到「%s」' % tr['note']
                evidence = 'note'
            else:
                n_rows = L.train_rows_found([sh['ent'].get('tokens') for sh in recs if sh['ent'] is not None], ix, tr)
                train_ok = n_rows >= tr['rows']
                why_not = 'OCR 對照表裡只有 %d 列同時有 %s 與 %s 的格子（要 %d 列）' % (n_rows, tr['drawn'], '／'.join(tr['stands_for']), tr['rows'])
                evidence = 'rows %d' % n_rows
            decl['train']['evidence'][fam['family']] = evidence
            if train_ok:
                decl['train']['applied'] += 1
                decl['train']['families'].append(fam['family'])
            else:
                dropped['train_no_note' if 'note' in tr else 'train_no_rows'] += 1
                if 'note' in tr or ocr_pages:                         # 沒讀對照表（--no-ocr）時 rows 把關本來就驗不了，不必嚷嚷
                    log('  注意：%s %s，同型典型規則不套用' % (fam['family'], why_not))
        foreign = set()
        fd = L.FOREIGN_SHEETS.get(tail)
        if fd:
            fp = L.foreign_pages(pages, fd)
            if fp is None:
                dropped['foreign_no_note'] += 1
                log('  注意：%s 圖上找不到「%s」，「非本機組組態的圖紙」規則不套用' % (fam['family'], fd['note']))
            else:
                foreign = {p for p in fp if not recs[p - 1]['cover']}
                decl['foreign']['applied'] += 1
                decl['foreign']['sheets'] += [_slug_or_key(fam['rel'], p) for p in sorted(foreign)]
        air_pages = 0
        ctx = L.make_ctx(fam['family'], fam['sys'], train_ok)
        for sh in recs:
            pno, pg, key, cover, R, ent = sh['page'], sh['pg'], (fam['rel'], sh['page']), sh['cover'], sh['R'], sh['ent']
            del ctx['rej'][:]
            th = L.match_page(pg['words'], ix, ctx)
            if cover:
                dropped['cover_hits'] += len(th)
                continue
            page_hits = []
            for h in th:
                f = L.to_upright_frac(pg, h['box'], R)
                page_hits.append({'tag': h['tag'], 'key': key, 'box': f, 'label': h['label'], 'rel': h['rel'], 'drawn_as': h['drawn_as'],
                                  'how': 'text', 'form': h['form'], 'note': h['note'], 'why': ['flag'] if h['note'] == L.NOTE_FLAG else []})
                sh['text_tags'].add(h['tag'])
            for r in ctx['rej']:
                _drop(trace, r['why'], r['tag'], key, L.to_upright_frac(pg, r['box'], R), r['label'], 'text')
            del ctx['rej'][:]
            if ent is not None:
                ocr_stat['pages'] += 1
                sh['ocr'] = ent                                       # 走到這裡 R 一定等於對照表的 rot（不符的已在上面整筆剔除）
                tboxes = text_tag_boxes(pg, R)
                w_pt, h_pt = L.upright_size(pg, R)
                toks = []
                for tk in ent.get('tokens') or []:
                    b = L.ocr_token_box(tk)
                    if overlaps_text(b, tboxes):
                        ocr_stat['tokens_dup_text'] += 1
                        continue
                    if float(tk[5]) < L.OCR_MIN_SCORE:
                        # 分數不夠的字**不會成為命中**（match_ocr_tokens 自己會跳過；唯一的例外是「差一點點的疊寫標籤」），
                        # 但仍要交給它：判斷「這一欄是不是儀器清單」要看得到整欄，少了這幾格清單欄會斷成幾截而漏判
                        ocr_stat['tokens_low_score'] += 1
                    else:
                        ocr_stat['tokens_used'] += 1
                    toks.append([tk[0], (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0, b[2] - b[0], b[3] - b[1], tk[5]])
                for h in L.match_ocr_tokens(toks, ix, w_pt, h_pt, ctx):
                    if 'near' in h['why'] and h['tag'] in sh['text_tags']:
                        dropped['ocr_near_has_text'] += 1             # 差一點點的讀數只用來補「這一頁完全沒有著落」的位號
                        _drop(trace, 'ocr_near_has_text', h['tag'], key, h['box'], h['label'], 'ocr')
                        continue
                    # note＝1：這個 OCR 框在整頁儀器清單的欄位裡（pid_lib.ocr_table_tokens），不是符號——與文字層的表格列同樣處理
                    e = {'tag': h['tag'], 'key': key, 'box': h['box'], 'label': h['label'], 'rel': h['rel'], 'drawn_as': h['drawn_as'],
                         'how': 'ocr', 'form': h['form'], 'note': h['note'], 'conf': h['conf'], 'why': list(h['why'])}
                    if h.get('raw') is not None:
                        e['raw'] = h['raw']
                    page_hits.append(e)
                for r in ctx['rej']:
                    _drop(trace, r['why'], r['tag'], key, r['box'], r['label'], 'ocr')
                del ctx['rej'][:]
            if pno in foreign:
                # 圖面自己聲明這一張是別的機組的組態（FOREIGN_SHEETS）：整頁的命中都不發布
                dropped['foreign_sheet'] += len(page_hits)
                for h in page_hits:
                    _drop(trace, 'foreign_sheet', h['tag'], key, h['box'], h['label'], h['how'])
                continue
            if tail in L.AIR_SHEETS:
                ok, _n = L.air_sheet(pg['words'])
                if ok:
                    air_pages += 1
                    decl['air']['sheets'].append(_slug_or_key(fam['rel'], pno))
                    for h in page_hits:
                        if h['note'] == L.NOTE_SYMBOL and L.tag_system(h['tag'])[:2] not in L.AIR_SYS:
                            h['note'] = L.NOTE_AIR                    # 空氣分配圖上別的系統的位號＝這顆閥的供氣接點
                            h['why'].append('air')
            for oi, ov in enumerate(L.HIT_OVERRIDES):
                if ov['family'] != tail or ov['page'] != pno:
                    continue
                x0, y0, x1, y1 = ov['box']
                for h in page_hits:
                    cx, cy = (h['box'][0] + h['box'][2]) / 2.0, (h['box'][1] + h['box'][3]) / 2.0
                    if h['note'] == L.NOTE_SYMBOL and x0 <= cx <= x1 and y0 <= cy <= y1:
                        h['note'] = ov['note']
                        h['why'].append('override')
                        ov_used[oi] += 1
            hits += page_hits
        if tail in L.AIR_SHEETS:
            if air_pages:
                decl['air']['applied'] += 1
            else:
                dropped['air_no_evidence'] += 1
                log('  注意：%s 沒有一頁驗得出是空氣分配圖（要印著 INSTRUMENT AIR、而且 QE／QF 系統的標籤 ≥ %d 個），用氣點規則不套用' % (
                    fam['family'], L.AIR_MIN_LABELS))
        for k in ('scope_letter', 'sfx_mismatch', 'ocr_nounit'):
            dropped[k] += ctx['drops'][k]
    for oi, ov in enumerate(L.HIT_OVERRIDES):
        decl['overrides']['hits'] += ov_used[oi]
        if not ov_used[oi]:
            decl['overrides']['unmatched'] += 1
            if ocr_pages:                                             # --no-ocr 時 OCR 圖紙上的條目本來就對不到，只計數
                log('  注意：覆寫表第 %d 筆（%s 第 %d 頁：%s）沒有對到任何命中——圖換版或頁序變了？要重新讀圖' % (
                    oi + 1, ov['family'], ov['page'], ov['why']))
    decl['air']['sheets'].sort()
    decl['foreign']['sheets'].sort()
    if ocr_pages:
        ocr_stat['unused'] = len(set(ocr_pages) - used_keys)
    return sheets, hits, dropped, ocr_stat, decl, trace, {k: sorted(v) for k, v in sorted(bad_ocr.items())}


def superseded_only(corpus, ix, located):
    """只在舊版次／副本找得到的位號（統計用；它們的位置不發布）。"""
    found = set()
    for fam in corpus['drawings']:
        ctx = L.make_ctx(fam['family'], fam['sys'], False)
        ctx['rej'] = None
        for m in fam['members']:
            rec = L.load_text(corpus['root'], m['rel'], m['size'], m['mtime'], corpus['cache_dir'])
            for pg in rec['pg']:
                if L.is_cover(pg):
                    continue
                found.update(h['tag'] for h in L.match_page(pg['words'], ix, ctx) if not h['note'])
    return sorted(found - located)


def select(hits, sheets, dropped, trace):
    """每支位號：最好的一級 → 排序 → 上限。回 {tag: [hit…]}（hit 仍帶內部的 key）。
    **等級只看符號命中（note=0）**；引用（note>0：清單／附註、訊號旗標、用氣點、迴路詳圖）絕不把等級較低的符號擠掉。
    留下來的＝最好那一級的符號命中，再加上這些引用：
      * 與符號同一級的（與舊版相同）；
      * 圖上印的就是**這支位號自己的全名**（exact）而符號是較低的一級——例：G12HAP61BL001 的訊號旗標寫 'G12HAP61BL001/2/3'，
        真正的 LISZA 球泡在 HRSG 廠商圖上畫成 11（typical）。舊版把旗標當符號，只發布旗標、真正的球泡反而被丟掉；
        給水泵組畫的是 LAC50（train），LAC60／LAC70 自己的名字只印在儀器清單裡，也是這一種。
        不寫機組的表格字（neutral）不算：那不是這支位號的名字，典型圖上的 G12 位號不會因此多出一處。
      * 但同一張圖上若這支位號另有等級更好的命中，等級較差的引用不留（同一張圖既有 'G12…' 的旗標，'G11…' 的旗標就不是 G12 的）。
    沒有任何符號命中的位號（只在清單／旗標／用氣點出現）照樣發布，等級取引用裡最好的一級。"""
    by = defaultdict(list)
    for h in hits:
        by[h['tag']].append(h)
    out = {}
    rank = L.REL_RANK
    for tag in sorted(by):
        lst = by[tag]
        sym = [h for h in lst if not h['note']]
        best = min(rank[h['rel']] for h in (sym or lst))
        if sym:
            keep = [h for h in lst if (rank[h['rel']] == best if not h['note'] else
                                       (rank[h['rel']] == best or (h['rel'] == 'exact' and rank[h['rel']] < best)))]
            on = {}
            for h in keep:
                on[h['key']] = min(on.get(h['key'], 9), rank[h['rel']])
            keep = [h for h in keep if not h['note'] or rank[h['rel']] == on[h['key']]]
        else:
            keep = [h for h in lst if rank[h['rel']] == best]
        dropped['other_class'] += len(lst) - len(keep)
        if len(keep) != len(lst):
            kept = {id(h) for h in keep}
            for h in lst:
                if id(h) not in kept:
                    _drop(trace, 'other_class', tag, h['key'], h['box'], h['label'], h['how'])
        if sym and best != rank['train']:
            # 已經有符號位置的位號，OCR 在清單裡讀到的那幾格不發布。清單是同類誤讀最容易歸錯戶的地方：每一格的上下左右都是
            # 只差一個數字的兄弟位號。2026-10-08 實測 TDM01-D1205 p7 的清單格 'C10LAC50 BT026' 被讀成 BT025（6→5，分數 0.777），
            # 於是 C10LAC50BT025 多了一處其實是 BT026 的「清單位置」。符號位置已經回答了「畫在哪」，清單格不值得冒這個險；
            # 只有清單可找的位號照樣保留，卡片會說明那是清單不是符號。文字層的附註／清單不受影響（不會讀錯字）。
            # 例外：符號是同型典型（train）的位號——圖上畫的是 LAC50，這支位號自己的名字只印在清單裡，那一格就是對照的憑據，要留。
            n0 = len(keep)
            for h in keep:
                if h['note'] == L.NOTE_LIST and h['how'] == 'ocr':
                    _drop(trace, 'ocr_list_with_symbol', tag, h['key'], h['box'], h['label'], h['how'])
            keep = [h for h in keep if not (h['note'] == L.NOTE_LIST and h['how'] == 'ocr')]
            dropped['ocr_list_with_symbol'] += n0 - len(keep)

        def order(h):
            fam = sheets[h['key']]['fam']
            return (1 if h['note'] else 0, 0 if h['how'] == 'text' else 1, fam['doc'] or ('~' + fam['rel'].rsplit('/', 1)[-1]), fam['rel'],
                    h['key'][1], round(h['box'][1], 5), round(h['box'][0], 5), h['label'])
        keep.sort(key=order)
        # 同一個位置同一支位號只留一筆（單字與合併候選可能指到同一個框）
        uniq, seen = [], set()
        for h in keep:
            k = (h['key'], round(h['box'][0], 4), round(h['box'][1], 4), round(h['box'][2], 4), round(h['box'][3], 4))
            if k in seen:
                dropped['same_box'] += 1
                continue
            seen.add(k)
            uniq.append(h)
        order_sheets, per = [], Counter()
        res = []
        for h in uniq:
            if h['key'] not in order_sheets:
                if len(order_sheets) >= MAX_SHEETS_PER_TAG:
                    dropped['sheets_over_cap'] += 1
                    _drop(trace, 'sheets_over_cap', tag, h['key'], h['box'], h['label'], h['how'])
                    continue
                order_sheets.append(h['key'])
            if per[h['key']] >= MAX_HITS_PER_SHEET:
                dropped['hits_over_cap'] += 1
                _drop(trace, 'hits_over_cap', tag, h['key'], h['box'], h['label'], h['how'])
                continue
            per[h['key']] += 1
            res.append(h)
        # 圖的順序＝第一筆命中出現的順序；同一張圖的命中排在一起
        res.sort(key=lambda h: order_sheets.index(h['key']))
        out[tag] = res
    return out


def sheet_grid(sh):
    """圖框格線：先文字層；沒有再用 OCR 對照表的 border 做容缺擬合。"""
    R = sh['R']
    g = L.detect_grid(L.border_labels(sh['pg'], R))
    if g:
        return g
    ent = sh.get('ocr')
    if ent and ent.get('border'):
        return L.fit_grid([(cx, cy, str(t).strip().upper()) for t, cx, cy in ent['border']])
    return None


def build(a, log):
    tags_all = L.load_ams(a.sqlite)
    base = sorted(t for t in tags_all if not t.startswith('JK'))
    log('AMS 現行位號 %d（JK* %d，母數 %d；HART %d／FF %d）' % (
        len(tags_all), len(tags_all) - len(base), len(base),
        sum(1 for t in base if tags_all[t] == 'HART'), sum(1 for t in base if tags_all[t] == 'FF')))
    ix = L.build_index(tags_all)
    corpus = L.build_corpus(a.library, a.text_cache, a.jobs, log)
    if corpus['text_extracted'] or corpus['text_errors']:
        log('文字層快取：重抽 %d 份、失敗 %d 份' % (corpus['text_extracted'], len(corpus['text_errors'])))
        for k, v in sorted(corpus['text_errors'].items())[:10]:
            log('    %s：%s' % (k.rsplit('/', 1)[-1], v))
    ocr_pages, ocr_present = (None, False) if a.no_ocr else load_ocr_map(a.ocr_map)
    sheets, hits, dropped, ocr_stat, decl, trace, bad_ocr = scan(corpus, ix, ocr_pages, log)
    hits = [h for h in hits if h['tag'] in tags_all and not h['tag'].startswith('JK')]
    sel = select(hits, sheets, dropped, trace)

    # ---- 被引用的圖紙
    ref_keys = sorted({h['key'] for v in sel.values() for h in v})
    slug_of = {k: L.slug(k[0], k[1]) for k in ref_keys}
    if len(set(slug_of.values())) != len(slug_of):
        sys.exit('slug 撞號（不同圖紙得到同一個鍵）')
    tags_on = Counter(k for v in sel.values() for k in {h['key'] for h in v})
    sheets_out = {}
    grids = {}
    for k in ref_keys:
        sh = sheets[k]
        fam = sh['fam']
        R = sh['R']
        w_pt, h_pt = L.upright_size(sh['pg'], R)
        grid = sheet_grid(sh)
        grids[k] = grid
        label_pt = L.label_height_pt(sh['pg']['words'])
        if label_pt is None and sh['ocr'] and sh['ocr'].get('tokens'):
            # 沒有文字層的圖紙：位號是線條字或點陣圖，字高只能從 OCR 偵測框估。這裡給的是**字形本身的高度**（框的短邊 ÷
            # OCR_BOX_PER_GLYPH），不是文字層圖紙那種「字框高」：線條字的筆畫是髮絲線，要讓字形本身有 12 px 才讀得出來
            # （TDM01-D1205 p4／p5 舊版照框高算只給 2400 px，球泡裡的 PT 讀起來像 PI）。文字層圖紙的算法不變。
            hs = sorted(min(t[3] * w_pt, t[4] * h_pt) for t in sh['ocr']['tokens'])
            label_pt = round(hs[len(hs) // 2] / L.OCR_BOX_PER_GLYPH, 2) if len(hs) >= 5 else None
        sheets_out[slug_of[k]] = {
            'rel': fam['rel'], 'file': fam['rel'].rsplit('/', 1)[-1], 'doc': fam['doc'], 'rev': fam['rev'], 'title': fam['title'],
            'page': k[1], 'pages': fam['pages'], 'rot': R, 'rot_method': sh['rot_method'],
            'w_pt': round(w_pt, 1), 'h_pt': round(h_pt, 1), 'label_pt': label_pt, 'grid': grid,
            'words': sh['words'], 'ocr': bool(sh['ocr']), 'tags': tags_on[k], 'src': {'size': fam['size'], 'mtime': fam['mtime']}}
    by_tag = {}
    for tag, lst in sel.items():
        ents = []
        for h in lst:
            b = h['box']
            e = {'sheet': slug_of[h['key']], 'x': r5(b[0]), 'y': r5(b[1]), 'w': r5(b[2] - b[0]), 'h': r5(b[3] - b[1]),
                 'label': h['label'], 'rel': h['rel'], 'drawn_as': h['drawn_as'], 'how': h['how'], 'form': h['form'], 'note': h['note']}
            if h['how'] == 'ocr':
                e['conf'] = h['conf']
                if h.get('raw') is not None and h['form'] == 'ocr-fix':
                    e['raw'] = h['raw']
            z, near = L.zone_of(grids[h['key']], (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
            if z:
                e['zone'] = z
                e['zone_near'] = 1 if near else 0
            ents.append(e)
        by_tag[tag] = ents

    # ---- stats
    located = set(by_tag)
    draw_pages = [sh for sh in sheets.values()]
    real = [sh for sh in draw_pages if not sh['cover']]
    sparse = [sh for sh in real if is_sparse(sh)]
    shape_tot = Counter(L.tag_shape(t) for t in base)
    old_only = superseded_only(corpus, ix, located) if not a.no_superseded else None
    # 只有引用（沒有任何符號命中）的位號，依代碼分：全部同一種 → 那個代碼；混著 → 'mixed'
    ref_only = Counter()
    for v in by_tag.values():
        if all(e['note'] for e in v):
            codes = {e['note'] for e in v}
            ref_only[str(next(iter(codes))) if len(codes) == 1 else 'mixed'] += 1
    near_hits = sorted((tag, slug_of[h['key']]) for tag, lst in sel.items() for h in lst if 'near' in h.get('why', ()))
    stats = {
        'ams_tags': len(tags_all), 'ams_tags_base': len(base),
        'located': len(located), 'located_pct': round(100.0 * len(located) / len(base), 1) if base else 0.0,
        'located_symbol': sum(1 for v in by_tag.values() if any(not e['note'] for e in v)),
        'located_note_only': sum(1 for v in by_tag.values() if all(e['note'] for e in v)),
        'located_ref_only': dict(sorted(ref_only.items())),
        'hits_by_note': dict(sorted(Counter(str(e['note']) for v in by_tag.values() for e in v).items())),
        'ocr_near': {'admitted': len(near_hits), 'tags': [t for t, _s in near_hits]},
        'not_located': len(base) - len(located),
        'by_proto': dict(sorted(Counter(tags_all[t] for t in located).items())),
        'proto_total': dict(sorted(Counter(tags_all[t] for t in base).items())),
        'by_rel': dict(sorted(Counter(v[0]['rel'] for v in by_tag.values()).items())),
        'by_how': {'text': sum(1 for v in by_tag.values() if v[0]['how'] == 'text'), 'ocr': sum(1 for v in by_tag.values() if v[0]['how'] == 'ocr')},
        'tags_with_ocr_hit': sum(1 for v in by_tag.values() if any(e['how'] == 'ocr' for e in v)),
        'by_shape': dict(sorted(Counter(L.tag_shape(t) for t in located).items())), 'shape_total': dict(sorted(shape_tot.items())),
        'drawings': len(corpus['drawings']), 'pages': len(draw_pages), 'pages_cover': len(draw_pages) - len(real),
        'pages_sheet': len(real), 'pages_text': len(real) - len(sparse), 'pages_sparse': len(sparse),
        'pages_ocr': int(ocr_stat.get('pages', 0)),
        'sheets_referenced': len(sheets_out), 'drawings_referenced': len({k[0] for k in ref_keys}),
        'hits': sum(len(v) for v in by_tag.values()), 'tags_multi_sheet': sum(1 for v in by_tag.values() if len({e['sheet'] for e in v}) > 1),
        'tags_per_sheet_max': max(tags_on.values()) if tags_on else 0,
        'rot': dict(sorted(Counter(str(s['rot']) for s in sheets_out.values()).items())),
        'rot_method': dict(sorted(Counter(s['rot_method'] for s in sheets_out.values()).items())),
        'sheets_with_grid': sum(1 for s in sheets_out.values() if s['grid']),
        'sheets_without_label_pt': sum(1 for s in sheets_out.values() if s['label_pt'] is None),
        'dropped': {k: int(v) for k, v in sorted(dropped.items()) if v},
        'train': decl['train'], 'foreign': decl['foreign'], 'air': decl['air'], 'overrides': decl['overrides'],
        'ocr_map': {'present': bool(ocr_present), 'pages': int(ocr_stat.get('pages', 0)), 'stale': int(ocr_stat.get('stale', 0)),
                    'unused': int(ocr_stat.get('unused', 0)), 'cover': int(ocr_stat.get('cover', 0)),
                    'rot_conflict': int(ocr_stat.get('rot_conflict', 0)), 'size_mismatch': int(ocr_stat.get('size_mismatch', 0)),
                    'tokens_used': int(ocr_stat.get('tokens_used', 0)),
                    'tokens_dup_text': int(ocr_stat.get('tokens_dup_text', 0)), 'tokens_low_score': int(ocr_stat.get('tokens_low_score', 0))},
        'superseded_only': None if old_only is None else {'tags': len(old_only), 'sample': old_only[:20]},
        'corpus': corpus['stats'],
        'limits': {'sheets_per_tag': MAX_SHEETS_PER_TAG, 'hits_per_sheet': MAX_HITS_PER_SHEET, 'ocr_min_score': L.OCR_MIN_SCORE,
                   'ocr_near_score': L.OCR_NEAR_SCORE, 'min_orient_chars': L.MIN_ORIENT_CHARS, 'sparse_words': L.SPARSE_WORDS},
    }
    out = {'kind': 'pid', 'generated_by': L.GENERATED_BY_INDEX, 'version': L.PID_VERSION,
           'sheets': sheets_out, 'by_tag': by_tag, 'stats': stats}
    # 追查用的旁檔（--trace；不是契約的一部分）：每一筆發布的命中用到哪些特殊規則、每一筆沒發布的命中為什麼沒發布
    tr = {'kind': 'pid_trace', 'generated_by': L.GENERATED_BY_INDEX,
          'why': {tag: [sorted(h.get('why', ())) for h in lst] for tag, lst in sorted(sel.items()) if any(h.get('why') for h in lst)},
          'drops': sorted(trace, key=lambda d: (d['tag'], d['sheet'], d['y'], d['x'], d['why'], d['label'])),
          'near': [list(x) for x in near_hits]}
    return out, {'corpus': corpus, 'sheets': sheets, 'sel': sel, 'tags_all': tags_all, 'base': base, 'ix': ix, 'hits': hits,
                 'trace': tr, 'bad_ocr': bad_ocr}


def is_sparse(sh):
    """沒有可用的文字層（線條字／掃描圖）：不到 SPARSE_WORDS 個字，或字元數不足以定轉正角。"""
    return sh['words'] < L.SPARSE_WORDS or sh['chars'] < L.MIN_ORIENT_CHARS


def worklist(ctx, out):
    """OCR 工作清單（定義見檔頭）。只用文字層的命中來算旗標。"""
    corpus, sheets, tags_all, base, ix = ctx['corpus'], ctx['sheets'], ctx['tags_all'], ctx['base'], ctx['ix']
    text_located = {h['tag'] for h in ctx['hits'] if h['how'] == 'text' and not h['note']}
    ref_files = {h['key'][0] for h in ctx['hits'] if h['how'] == 'text' and not h['note']}
    # AMS 還沒被文字層定位到的 KKS 位號 → {(機組字母, 系統碼三字母)}
    missing = defaultdict(int)
    for core, lst in ix['kks'].items():
        for (tag, tl, _tu, _sfx) in lst:
            if tag not in text_located:
                missing[(tl, core[:3])] += 1
    rows = []
    cnt = Counter()
    for key in sorted(sheets):
        sh = sheets[key]
        if sh['cover']:
            continue
        fam, pg = sh['fam'], sh['pg']
        scope = L.SCOPE_LETTER.get(fam['sys'] or '')
        exp = sorted({s for (letter, s) in sh['systems']
                      for (tl, s2) in missing if s2 == s and (letter == tl or (not letter and (not scope or scope == tl)))})
        reasons = []
        if is_sparse(sh):
            reasons.append('sparse')
        if fam['rel'] in ref_files:
            reasons.append('referenced')
        if exp:
            reasons.append('expected')
        need = bool(reasons)
        for r in reasons:
            cnt[r] += 1
        cnt['need'] += need
        cnt['sheets'] += 1
        rows.append({'rel': fam['rel'], 'page': key[1], 'pages': fam['pages'], 'size': fam['size'], 'mtime': fam['mtime'],
                     'family': fam['family'], 'doc': fam['doc'], 'rev': fam['rev'],
                     'rotate': pg['rot'], 'R': sh['info']['R'] if sh['info']['method'] == 'text' else None,
                     'R_thin': sh['info']['R'] if sh['info']['method'] == 'text-thin' else None,
                     'w_pt': pg['w'], 'h_pt': pg['h'], 'words': sh['words'], 'chars': sh['chars'], 'tag_words': sh['tag_words'],
                     'img': pg.get('img') or [0, 0], 'tags_text': len(sh['text_tags']), 'expected_systems': exp,
                     'reasons': reasons, 'need': need})
    return {'kind': 'pid_worklist', 'generated_by': L.GENERATED_BY_INDEX, 'version': L.PID_VERSION,
            'need_rule': 'sparse OR referenced OR expected',
            'counts': {k: int(v) for k, v in sorted(cnt.items())},
            'drawings': out['stats']['drawings'], 'sheets': rows}


def write_json(path, obj, what):
    txt = L.dumps(obj)
    bad = L.ABS_PATH_RE.search(txt)
    if bad:
        sys.exit('%s 含本機絕對路徑：%r' % (what, txt[max(0, bad.start() - 60):bad.start() + 60]))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt)
    os.replace(tmp, path)
    return len(txt.encode('utf-8'))


def verify(out, root, tags, vdir, log):
    """印出位號的命中，並把框疊在轉正後的整張圖上（紅框）另存 PNG——人工讀圖核對用。
    每張被引用的圖出兩個檔：<TAG>__<slug>.png（整張，長邊 2400 px）與 <TAG>__<slug>__crop.png（第一處周圍，4 px/pt）。"""
    import fitz
    from PIL import Image, ImageDraw
    os.makedirs(vdir, exist_ok=True)
    for tag in tags:
        tag = tag.strip().upper()
        ents = out['by_tag'].get(tag)
        log('\n=== %s ===' % tag)
        if not ents:
            log('  查無（現行 P&ID 文件集裡找不到這支位號）')
            continue
        by_sheet = defaultdict(list)
        for e in ents:
            by_sheet[e['sheet']].append(e)
            log('  %-9s %-5s %-11s note=%d  x=%.4f y=%.4f w=%.4f h=%.4f  %s%s  drawn_as=%r  label=%r  [%s]' % (
                e['rel'], e['how'], e['form'], e['note'], e['x'], e['y'], e['w'], e['h'],
                ('zone ' + e['zone'] + ('~' if e.get('zone_near') else '')) if e.get('zone') else 'zone -',
                ('  conf %.2f' % e['conf']) if 'conf' in e else '', e['drawn_as'], e['label'], e['sheet']))
        for sk, lst in by_sheet.items():
            s = out['sheets'][sk]
            log('  圖紙 %s：%s 第 %d／%d 頁，rot=%d（%s），%.0f x %.0f pt' % (
                sk, s['file'], s['page'], s['pages'], s['rot'], s['rot_method'], s['w_pt'], s['h_pt']))
            doc = fitz.open(os.path.join(root, s['rel'].replace('/', os.sep)))
            page = doc[s['page'] - 1]
            pix = L.render_upright(page, s['rot'], long_px=2400)
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            dr = ImageDraw.Draw(im)
            for e in lst:
                x0, y0 = e['x'] * im.width, e['y'] * im.height
                x1, y1 = (e['x'] + e['w']) * im.width, (e['y'] + e['h']) * im.height
                dr.rectangle([x0 - 10, y0 - 10, x1 + 10, y1 + 10], outline=(255, 0, 0), width=4)
                dr.ellipse([(x0 + x1) / 2 - 60, (y0 + y1) / 2 - 60, (x0 + x1) / 2 + 60, (y0 + y1) / 2 + 60], outline=(255, 0, 0), width=3)
            p1 = os.path.join(vdir, '%s__%s.png' % (re.sub(r'[^A-Za-z0-9_.-]', '_', tag), sk))
            im.save(p1)
            e = lst[0]
            z = 4.0
            pix = L.render_upright(page, s['rot'], zoom=z)
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            cx, cy = (e['x'] + e['w'] / 2.0) * im.width, (e['y'] + e['h'] / 2.0) * im.height
            box = (int(max(0, min(cx - 600, im.width - 1200))), int(max(0, min(cy - 400, im.height - 800))))
            cr = im.crop((box[0], box[1], box[0] + 1200, box[1] + 800))
            dr = ImageDraw.Draw(cr)
            for e2 in lst:
                x0, y0 = e2['x'] * im.width - box[0], e2['y'] * im.height - box[1]
                x1, y1 = (e2['x'] + e2['w']) * im.width - box[0], (e2['y'] + e2['h']) * im.height - box[1]
                dr.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], outline=(255, 0, 0), width=2)
            p2 = p1[:-4] + '__crop.png'
            cr.save(p2)
            doc.close()
            log('    疊框圖：%s ／ %s' % (os.path.basename(p1), os.path.basename(p2)))
    log('疊框圖目錄：%s' % vdir)


def previous_ocr_located(path):
    """上一次的輸出（即將被覆寫的那個檔）裡，第一個位置是靠 OCR 的位號 → {位號: 那張圖的檔名}。讀不到就回 {}。
    只用來在這次執行結束時大聲提醒「原本有位置、現在沒有了」（loud）；不影響輸出。"""
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        sh = d.get('sheets') or {}
        return {t: (sh.get(v[0]['sheet']) or {}).get('file') or v[0]['sheet'] for t, v in (d.get('by_tag') or {}).items()
                if v and v[0].get('how') == 'ocr'}
    except Exception:                                     # noqa: BLE001
        return {}


def loud(a, out, ctx, prev):
    """會讓位置**默默消失**的情況要印成 '!!' 開頭的一行並點名是哪幾份圖（2026-10-10 裁決 A9；回傳碼仍是 0）：
      * OCR 對照表有過期／轉正角衝突／尺寸不符的頁——PDF 重新同步後只要修改時間變了，那一頁的 OCR 位號就全部不用，
        以前只在統計裡多一個數字；要補回來得重跑 pid_ocr.py（需要 rapidocr）再 --distill、commit 對照表
      * 上一次輸出裡靠 OCR 定位的位號，這次沒有位置了"""
    bad = ctx.get('bad_ocr') or {}
    label = {'stale': '過期（PDF 的大小／修改時間與對照表記的不同）', 'rot_conflict': '轉正角與文字層不符', 'size_mismatch': '尺寸與轉正角不符'}
    for why in ('stale', 'rot_conflict', 'size_mismatch'):
        names = bad.get(why) or []
        if names:
            print('!! OCR 對照表有 %d 頁%s，整筆沒用——這些圖上靠 OCR 的位號這次都找不到：%s%s' % (
                out['stats']['ocr_map'][why], label[why], '、'.join(names[:8]), '…' if len(names) > 8 else ''))
            print('!!   補救：py tools/db/pid_ocr.py（重跑這幾份）→ py tools/db/pid_ocr.py --distill → commit tools/db/pid_ocr_map.json')
    lost = sorted(t for t in prev if t not in out['by_tag'])
    if lost:
        files = sorted({prev[t] for t in lost})
        print('!! 上一次靠 OCR 定位的位號有 %d 支這次沒有位置了：%s%s；原本在：%s%s' % (
            len(lost), '、'.join(lost[:8]), '…' if len(lost) > 8 else '', '、'.join(files[:6]), '…' if len(files) > 6 else ''))


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='P&ID 圖面定位索引（見檔頭 docstring）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（預設 paths.LIBRARY_ROOT；唯讀）')
    ap.add_argument('--sqlite', default=paths.AMS_SQLITE, help='AmsDb.sqlite（預設 paths.AMS_SQLITE）')
    ap.add_argument('--text-cache', default=paths.PID_TEXT_CACHE, help='文字層字框快取目錄（預設 paths.PID_TEXT_CACHE）')
    ap.add_argument('--ocr-map', default=paths.PID_OCR_MAP, help='OCR 對照表（預設 paths.PID_OCR_MAP；不存在就只用文字層）')
    ap.add_argument('--no-ocr', action='store_true', help='不讀 OCR 對照表')
    ap.add_argument('--no-superseded', action='store_true', help='不掃舊版次／副本（省約 2 秒；stats.superseded_only 會是 null）')
    ap.add_argument('--jobs', type=int, default=min(8, os.cpu_count() or 1), help='抽文字層用幾個行程（只有快取要補時才用到）')
    ap.add_argument('--out', default=paths.PID_JSON, help='輸出 pid.json（預設 paths.PID_JSON）')
    ap.add_argument('--worklist', metavar='FILE', help='另寫 OCR 工作清單 JSON（給 tools/db/pid_ocr.py）')
    ap.add_argument('--verify', metavar='TAG', nargs='+', help='另印這些位號的命中並畫疊框圖')
    ap.add_argument('--verify-dir', default=VERIFY_DIR, help='疊框圖輸出目錄（預設 %%LOCALAPPDATA%%\\AMS\\pidverify）')
    ap.add_argument('--trace', metavar='FILE', help='另寫追查用的旁檔：每筆命中用到的特殊規則、每筆沒發布的命中與原因')
    a = ap.parse_args()
    if not os.path.isdir(a.library):
        sys.exit('找不到文件庫：%s' % a.library)
    t0 = time.time()
    prev = previous_ocr_located(a.out)
    out, ctx = build(a, print)
    n = write_json(a.out, out, 'pid.json')
    st = out['stats']
    print('寫出 %s（%.2f MB）' % (os.path.basename(a.out), n / 1048576.0))
    print('定位 %d/%d (%.1f%%)：%s；協定 %s／%s' % (st['located'], st['ams_tags_base'], st['located_pct'],
                                              '、'.join('%s %d' % kv for kv in st['by_rel'].items()), st['by_proto'], st['proto_total']))
    print('來源 %s；形狀 %s／%s；有符號位置 %d 支、只有引用 %d 支（依代碼 %s）；各代碼的命中 %s' % (
        st['by_how'], st['by_shape'], st['shape_total'], st['located_symbol'], st['located_note_only'], st['located_ref_only'],
        st['hits_by_note']))
    print('文件集 %d 張圖 %d 頁（封面 %d、圖紙 %d：有文字層 %d／沒有 %d）；被引用 %d 張圖紙（%d 份圖）；rot %s（%s）' % (
        st['drawings'], st['pages'], st['pages_cover'], st['pages_sheet'], st['pages_text'], st['pages_sparse'],
        st['sheets_referenced'], st['drawings_referenced'], st['rot'], st['rot_method']))
    print('OCR 對照表 %s；丟掉的 %s；只在舊版次／副本找得到 %s' % (st['ocr_map'], st['dropped'], st['superseded_only']))
    print('宣告規則：同型典型 %s；非本機組組態的圖紙 %s；空氣分配圖 %s；覆寫表 %s' % (st['train'], st['foreign'], st['air'], st['overrides']))
    if st['ocr_near']['admitted']:
        print('差一點點的疊寫標籤（設備段分數 %.2f~%.2f）接受 %d 處：%s——每一處都要讀圖核對' % (
            L.OCR_NEAR_SCORE, L.OCR_MIN_SCORE, st['ocr_near']['admitted'],
            '、'.join('%s（%s）' % (t, s) for t, s in ctx['trace']['near'])))
    loud(a, out, ctx, prev)
    if a.trace:
        write_json(a.trace, ctx['trace'], '追查旁檔')
    if a.worklist:
        wl = worklist(ctx, out)
        write_json(a.worklist, wl, 'OCR 工作清單')
        print('OCR 工作清單 %s：%s' % (os.path.basename(a.worklist), wl['counts']))
    print('耗時 %.1f 秒' % (time.time() - t0))
    if a.verify:
        verify(out, ctx['corpus']['root'], a.verify, a.verify_dir, print)


if __name__ == '__main__':
    main()
