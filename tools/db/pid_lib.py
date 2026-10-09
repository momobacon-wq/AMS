# -*- coding: utf-8 -*-
r"""tools/db/pid_lib.py — P&ID 圖面定位的共用函式庫（pid_index.py／pid_shots.py／pid_ocr.py 三支共用；本檔沒有 main）。

要回答的問題：AMS 查詢卡上的這台儀器，畫在哪一份 P&ID、PDF 第幾頁、圖上哪個位置。
四件事集中在這裡，三支工具才不會各寫一套而對不起來：
  1. 文件集   文件庫現場走訪 → 哪些 PDF 是 P&ID → 同一張圖的各版次／副本歸成一個「圖號家族」→ 只留最新版
  2. 幾何     PDF 文字層座標 → 轉正後整張圖的 0~1 比例；轉正角 R；圖框分區（zone）
  3. 文字層   每份 PDF 的字框快取（paths.PID_TEXT_CACHE）
  4. 比對     圖上的字 ↔ 現行 AMS 位號（兩邊都正規化、拆寫合併、機組關係、GE 元件名、ISA 迴路名、OCR 形近字修復）

== 一、文件集（這幾條都是踩過坑才定的）==
* **文件庫要現場走訪，不可用 hst-docsearch 的全文索引**：索引比磁碟舊。使用者自己舉的例子
  HT0-1-KND01-D0027 第 4 版（2026-09-18 進庫）就不在索引裡，索引只認得第 3 版；drive_map 也有同樣的落差。
  走訪 31,896 個 PDF 只要 0.3 秒（os.scandir），沒有理由讀索引。
* **哪些檔是 P&ID 只看檔名**（kind_of）：檔名含 P&ID／PID／管線儀表流程圖／…系統圖，或 GE 的 System Schematic／
  Instrument Diagram／Pneumatic Schematic；或文件編號屬於 AFF01／GFD01／TFD01／BFD01 的 D 類圖（PID_SYS，
  與 docmap_docindex.classify 同一組再加 HRSG 廠商的 BFD01）。訓練教材裡的「PID 控制」、EOMR、清單、單線圖、
  HVAC、PFD、圖例檔（Symbol／Legend，但「(incl. Legend)」不算）一律不是。沒有標題的版次（HT0-1-URM01-D5001-0.pdf）
  跟同編號的兄弟檔同類。
* **GE 燃氣機的「System Schematic」（GFD01-D00xx）才是畫 GE 元件名（96FG-1、90VA41-31）的地方**，
  先前的探勘因為路徑過濾只收「P&ID」而整批漏掉，FF 裝置因此被誤判成「圖上沒有」（實際 351 台 FF 有 308 台以上在這些圖上）。
* **EXTRA_FAMILIES**：查詢卡把它當 P&ID 引用、但檔名規則認不出來的圖號，明列在常數裡（目前只有發電機示意圖
  EGJ01-D0004；檔名有「Load Equipment」會被當成電氣圖）。核對方法與結果見該常數的註解。
* **同一張圖只留最新版**：家族 = (HT 後第二碼, 系統碼, 類別字母, 流水號)；HT1（字母版次的舊編號）與 HT0 是同一張圖
  重新送審時合併，但「同號不同圖」（FFD01-D5001 HT0=消防水、HT1/2/3=各機組氣機房）要靠標題相似度分開。
  代表檔的挑法：有 HT 編號 > HT0 > HT1 > 其他首碼 > **版次高**（數字 > 字母 > 無；'1A' 排在 '1' 後面；廠商檔名認 _revX）>
  非副本夾 > 非 _舊版 > 檔名不是「(2)」重複檔 > 修改時間新。版次一定排在資料夾旗標前面（2026-10-10 以前相反：新版次只要
  剛好只放在副本夾／設備 dossier 夾，就會輸給正式資料夾裡的舊版次；真實文件庫 0 例，合成文件庫可重現）。
  緊接在編號後面的標題字不當版次（rev_is_title_word：'-GT System'、'-P&ID'、'-of 3'）。認不得的版次寫法
  （'D0027 Rev.5'、'D0027_6_'、三位數版次）仍當成沒有版次——已知限制，真實文件庫沒有這種檔名。
  **舊版次的座標絕不發布**：唯一遇到的案例（D0027 第 2 版的 =G11HSD10QN101）標在旁通閥下面，第 4 版同一位置已改成
  =G11HSD10QM107，真正的 FCV 球泡在上方而且是線條字。舊版與副本只留在 members 當統計。最新版若讀不了（壞檔、有密碼），
  那張圖就沒有位置，**不會**退回舊版次（build_corpus 會印 '!!'；stats.corpus.unreadable_representative）。
* **讀不了的 PDF 不可讓整個流程中止**：extract_text 對壞檔、空檔、有密碼、零頁的檔一律回 err（計入 stats.corpus.text_errors，
  從快取記錄數所以每次執行都一樣）。文件庫是雲端硬碟的同步夾，隨時可能多出一個這樣的檔。
* **廠商檔名的副本**（noKKS_FUEL GAS SYSTEM P&ID_rev0.pdf 這類）用**圖上標籤詞彙**認親：文字層完全相同，或
  KKS 標籤集合的 Jaccard ≥ 0.6（兩邊都要 ≥ 20 個標籤）。只靠標題認親不可靠——census 用「標題相似＋頁數」連了 13 個
  沒有文字層的檔，其中 3 個連錯（Service Water **Pumps** 連到 Service Water **System**、Lube Oil **Flushing** 連到
  Lube Oil **Tank**…），本檔改成「標題鍵（title_key）完全相同、而且只對到一個家族」才連，連不上的自成一張圖
  （會進 OCR 工作清單；Service Water Pumps 那張掃描圖 OCR 讀得到 32 個 AMS 核心，連錯就永遠定位不到）。
* **二、三號機組專屬圖（HT2-／HT3-／標題 UNIT-2、UNIT-3）不收**：AMS 是一號機組的資料庫，那些圖上的位號是姊妹機組的。
* **封面與圖例**：A4／Letter 直式的頁（長邊 < 1000 pt 且直式）是送審封面，不是圖紙；547 份含圖紙的 PDF 有 200 份
  以封面開頭。封面不當位置、也不進 OCR 工作清單。不要用「頁面幾何判斷這頁是不是表格」，試過會誤殺真圖。

== 二、幾何：**全專案只有一個轉正慣例 R** ==
  R ＝ 在頁面自己的 /Rotate **之上**再順時針多轉幾度才是正的（0／90／180／270）。
  渲染：page.get_pixmap(matrix=fitz.Matrix(z, z).prerotate(R))（get_pixmap 本來就會套 /Rotate）。
  pid.json 的 sheets[].rot、pid_ocr_map.json 的 pages[].rot、pid_shots/index.json 的 rot 全部是 R。
* **PyMuPDF 1.27.1 的 get_text('words'／'dict') 座標與行方向是「未旋轉」的頁面空間**（CropBox 左上為原點），
  /Rotate 不是 0 的頁也一樣（實測 213 頁有旗標的頁，211 頁的字框只塞得進未旋轉的框）。直接除以 page.rect 會讓
  252 頁有旗標的頁全部標錯位置而且不會報錯。一律走 to_upright_frac(page, rect, R)：先乘 page.rotation_matrix
  到「顯示空間」，再依 R 換到轉正後的比例。六張實際圖紙各 40 個字框人工讀圖＋八種合成（/Rotate × CropBox 位移）
  墨跡相關係數 1.000 驗證過。**兩個軸要分開驗**：TCM01-D1114 p5、BDM01-D2111 p3 是 /Rotate 270、R=0（驗
  rotation_matrix 那一步）；KND01-D0027-4 p2 是 /Rotate 0、R=270（驗 R 那一步）。
* **/Rotate 不等於轉正**：1,769 頁裡 20 頁（P&ID 圖紙 15 頁）/Rotate 套完還是側躺，D0027 第 3、4 版的四張圖紙全是。
* **轉正角怎麼定**（decide_R）：文字層的書寫方向，取字數最多的方向當水平（argmax）；但洩水／排水類 P&ID 有 50~88 % 的
  字是直書閥號，argmax 會把橫式圖紙立起來，所以大圖（長邊 ≥ 1000 pt）若 argmax 的結果是直式，改看兩個橫式候選
  （工程圖只有水平字與由下往上讀的直書字，沒有倒字與由上往下的字）。文字層不到 400 字（MIN_ORIENT_CHARS）時不可信
  （三張 Servovalve 圖只有一行直書邊註，會指錯），upright_rotation_text() 回 None，交給 OCR 定向。
  三套探勘程式的寫法不一樣，搬程式時要小心：census 用 rotation_matrix＋upright_deg（＝R）；ocr 探勘先呼叫
  page.remove_rotation()（/Rotate 變 0、顯示的畫面不變）再量 rot，所以它存下來的 rot **已經是 R**——若照字面拿
  「rot − 原本的 /Rotate 旗標」去換算，有旗標的頁會全部多轉 90 度（實測 TCM01-D1114 p5：旗標 270、探勘 rot 0、
  正確的 R 是 0，減旗標會變成 90）。通則：R = (相對於某個頁面物件量到的總旋轉 − **那個頁面物件當時的** page.rotation) % 360。
  pid_index 會擋這種錯：對照表的 rot 與文字層定出的 R 不符的頁，OCR 整筆不用並印出來。
* **圖框分區**：圖框四邊的 A、B、C…／1、2、3… 在 593／1,073 張圖紙的文字層裡（detect_grid）；沒有的用 OCR 讀邊條
  再做容缺擬合（fit_grid）。分區邊界由標籤位置推回去；被引用的圖紙只有四種圖框，疊圖實測邊界與印的刻度線最多差圖寬的
  0.13 %，所以離邊界不到格距 3 % 才算「靠近」（zone_of 回 near=True，卡片寫「約 C-5」；量法與舊值見 zone_of）。

== 三、比對（為什麼文字層就能定位 86 %，而第一版探勘只有 37 %）==
* **兩邊都要正規化**：圖上 '=G11HSD10QN101' → (字母 G, 機組 11, 核心 HSD10QN101)；AMS 'G12HSD10QN101' → 同一個核心。
  第一版只剝 AMS 這邊的機組，再拿去跟帶 '=G11' 的 PDF 字比，當然對不到。
* **標籤拆寫**（全庫 4,580 個）：CTCI 的 AFF01 圖把閥與管線寫成上下兩行（'C10LAC50' 一行、'BP005' 下一行，stacked），
  GE 氣機／汽機圖把 KKS 拆成 'MBH01'／'WP130'，EKI 的 SCR 圖把 '=G11' 畫成獨立的文字物件再接 'HSD10QN101'
  （prefixed），少數同一行中間隔一格（inline）。合併規則用「以該字自己的閱讀方向為準」的座標（reading_frame），
  所以直書的標籤同樣適用：系統段在設備段的上一行（行距 −1.7 ~ −0.6 個字高、沿行偏移 ≤ 1.2 個字高）。
* **機組關係**（relation；只發布每支位號最好的一級）：
    exact    圖上的機組與位號相同（'=G12…'、'12HAH…'）
    neutral  圖上不寫機組（GE 氣機示意圖的 '(96FG-1)'、汽機圖的 'LBC10BT001'）或寫佔位符（=GXX…）→ 各機組共用同一位置
    typical  圖上畫的是同一 Block 的另一部氣機（G12 的位號落在畫成 11 的標籤上；五份 HRSG 廠商 PID 每頁都印
             「UNIT11; …／UNIT12; …」成對的介面圖號，是明講的典型圖）→ drawn_as 記下圖上寫的機組
    loop     ISA 迴路名只對到迴路號（'1-PIT-CW014-1' ↔ AMS '1-PI-CW014-1'）
    train    圖面自己聲明「同型各台共用」的圖（TRAIN_TYPICALS，每筆都在建置時驗證）：凝結水泵 TCM01-D1114 註明
             "P&ID is applicable for all condensate pumps"，圖上畫 LCC10，AMS 是 LCC20／LCC30；給水泵組 TDM01-D1205 只畫
             C10LAC50，p7／p8 的儀器清單逐列對照 LAC50｜LAC60｜LAC70（沒有文字層，改驗 OCR 對照表裡的清單結構）。
             train 只認符號：清單／附註裡的 LCC10、LAC50 不代表別台畫在那裡。
  **絕不歸戶**的：字母不同（C10 與 G11 是不同設備）、C00（全廠共用，AMS 沒有）、別的 Block（G21、C20）。
* **尾碼必須相等**（2026-10-10 獨立查核後的裁決；細節與案例在 _attribute_kks）：標籤核心後面帶元件字母／元件碼／子項的
  （'…BP272C'、'…BT044A'、'…BT008AB'、'…QN001N1'、'…BL001-BL01'）是另一個項目，只歸給尾碼相同的 AMS 位號，不退而歸給
  不帶尾碼的那一支。文字層與 OCR、符號與清單都一樣。AMS 命名的裝飾（'_'、'_01'）不算尾碼。
* **圖上自己說「這一張不是本機組的」就不發布**（FOREIGN_SHEETS：GFD01-D0013 的 sheet 3 只適用 unit 2-2；宣告＋建置時
  找那句註記，以頁面內容認頁）。
* **圖的歸屬字母**（SCOPE_LETTER）：汽機圖（TFD01／EGK01）上不寫機組的 'LBA10BT001' 是 S10 的，不是 G11／G12 的同核心位號
  （AMS 有 11 個核心同時存在於兩個字母下，census 修掉 22 支誤歸戶）。GE 元件名同理：只有 G11_／G12_ 前綴的位號，
  不歸到汽機／汽機發電機的圖上。
* **GE 元件名**在 GE 示意圖上是括號裡的純文字，嚴格整詞相等（'96FG-1' ≠ '96FG-1A'）；AMS 這邊 13 支 GE 位號帶 '_01' 這種
  兩位數尾碼（G11_96PG-2A_01），剝掉再比。（尾端 '_' 與元件字母是 KKS 位號那一邊的事：C10LAF71QN001_ 的 '_' 是裝飾，
  S10MAV01BP272C 的 'C' 是真的尾碼——見上面「尾碼必須相等」。）
* **ISA 迴路規則要連開頭的機組數字一起比**：'2-PIT-CW014-1' 是二號機組的，不是 AMS 的 '1-PI-CW014-1'。
* **「提到位號」不等於「畫在這裡」**——命中的 note 代碼（0 才是符號旁的標籤；其餘都是**引用**，排在符號之後，
  也絕不把等級較低的符號擠掉，見 pid_index.select）：
    1  附註句子（≥ 4 個字的一行文字）或整齊排列的清單欄／OCR 讀到的整頁儀器清單的一格
    2  跨圖訊號旗標（signal_flag：CTCI 的 AFF01 圖上「DCDAS TO／FROM …＋去向圖號」的箭頭框；'…BL001/2/3' 連號也是）
    3  儀用／廠用空氣分配圖上的用氣點（AIR_SHEETS＋air_sheet：這顆閥的供氣接點，不是閥在製程管線上的位置）
    4  迴路詳圖「TYPICAL FOR …」小圖裡（HIT_OVERRIDES 逐處覆寫表；沒有通用偵測）
  2~4 是 2026-10-10 獨立查核後加的：舊版把它們當符號發布——旗標 15 處（7 支位號的第一個標記在旗標上）、
  用氣點 72 處（23 支的第一個標記、4 支只有這裡）。
* **文字層豐富不代表位號在文字層裡**：D0027 第 4 版 p2 有 953 個字，但儀表球泡是 CAD 線條字（41 個裡 35 個不在文字層）；
  BFD01-D0002 p3 有 863 個字，HAD10 QN002~QN010 控制閥卻是向量字。所以 OCR 工作清單不能只收「沒有文字層」的頁
  （見 pid_index.py 的 --worklist）。
* **OCR 字的比對**（ocr_scan／match_ocr_tokens）：OCR 會把上一行的功能碼併進同一框（'(XFV) =G11HSD10QM002'）、在字中間插空白、
  把 '=' 讀成 ':'／'E'、把機組讀成 '=GT1'、把兩三個相鄰的球泡讀成一個框。所以 OCR 這邊用「搜尋」而不是整詞相等，
  **每一次出現各自成一筆**（框依字元位置切開），並且只做**安全的形近字修復**：字母位出現數字（或反過來）時換成形近字，
  **只有剛好得到一個 AMS 核心時才接受**（單字替換 12,493 次 0 次修錯、20 萬個隨機字串 0 個被接受；但圖上本來就不是
  AMS 位號的標籤，被讀錯一個多值形近字時有極小機會「剛好」修成別的 AMS 核心——125,418 次裡 22 次，已知限制）。
  同類誤讀（C 讀成 Q、0 讀成 9）救不回來也擋不掉：834 個 AMS 核心有 802 個存在只差一個字的鄰居，所以**不做編輯距離比對**，
  並以辨識分數 ≥ 0.75 把關（唯一的例外是條件很嚴的「差一點點的疊寫標籤」，見 match_ocr_tokens）、OCR 命中一律標 inferred。
  發布的 label 是「這一筆自己的」正規化讀法，不是整個框的原文；修過形近字的另附 raw（原本讀到的字）。
  機組前綴讀不出來的整個不收——核心前面黏著無法解讀的字、只剩一個字母、被標點切開（'=G11.HSD…'）都算（_ocr_prefix）；
  沒寫機組的讀數只在「不寫機組的圖」（SCOPE_LETTER）上才收。寧可漏，不可把典型圖說成不分機組。
  機組清單（'G11/12HAP65 BP001'）兩部機各自 exact；斜線系統段（'C10PHC10/20 BT011'）展開成兩支，拆成兩個框的也一樣。

模組層級只編譯 regex、不讀檔、不建目錄；fitz（PyMuPDF）只在真的要開 PDF 時才 import。
"""
import gzip
import hashlib
import itertools
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

GENERATED_BY_INDEX = 'tools/db/pid_index.py'
PID_VERSION = 1
TEXT_CACHE_VERSION = 1                 # 文字層快取格式版本（改了抽取方式就 +1，舊快取自動重抽）
MAX_TEXT_PAGES = 80                    # 每份 PDF 最多抽幾頁文字（P&ID 沒有這麼厚的；超過的檔計入 stats.truncated）
MIN_ORIENT_CHARS = 400                 # 文字層少於這麼多字就不拿來定轉正角（見檔頭「轉正角怎麼定」）
SPARSE_WORDS = 30                      # 一頁不到這麼多個字 ＝ 沒有可用的文字層（線條字／掃描圖）
COVER_LONG_PT = 1000.0                 # 長邊小於這個值且直式 ＝ A4／Letter 封面
OCR_MIN_SCORE = 0.75                   # OCR 命中的最低辨識分數（探勘中正確位號的最低分是 0.78）
OCR_NEAR_SCORE = 0.70                  # 疊寫標籤的設備段可以放寬到這個分數（條件很嚴，見 match_ocr_tokens「差一點點的疊寫標籤」）
# OCR 偵測框的短邊 ÷ 字形本身的高度（大寫字高）。2026-10-10 在 14 張「同一批位號既有文字層字框、又有 OCR 框」的 AFF01 圖紙上量的：
# 字形 7.33 pt、文字層字框 9.0~10.0 pt（1.23~1.36 倍）、OCR 框 9.2~10.6 pt（1.26~1.45 倍，多數 1.26~1.31）。
# 沒有文字層的圖紙拿它把 OCR 框換算成字形高度（pid_index 的 label_pt；pid_shots 據此決定影像大小）。
OCR_BOX_PER_GLYPH = 1.3
ABS_PATH_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|\\Users\\|/Users/|我的雲端硬碟')   # 與 hmi_index.ABS_PATH_RE 相同
SLUG_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$')                                # ＝ build_card_aux.HMI_SLUG_RE
# ＝ build_card_aux.DOCNO_VAL_RE（抄一份而不 import：build_card_aux 之後會反過來讀本工具的輸出，避免循環）
DOCNO_VAL_RE = re.compile(r'(HT\d-\d-[A-Z]{3}\d\d-[A-Z]\d{4})(?:-([0-9A-Z]{1,2})(?![0-9A-Za-z]))?')

# 查詢卡把它當 P&ID 引用、檔名規則卻認不出來的圖號家族（鍵＝去掉 'HTx-' 的家族尾碼）。
# 核對方法：carddata 探勘把卡片上「圖面›P&ID」引用的 66 個文件值逐一對磁碟（pid_docs_disk.json），本檔的文件集建好後
# 再對一次——有 HT 編號、磁碟上有檔、卻不在任何家族裡的只有這一個；其餘沒對上的不是沒有檔（HT0-1-AFA00-X0007、
# HT0-2-UFA00-D0002、instlist 的筆誤 D8-1-BFD01-D0006）就是廠商檔名的副本（noKKS_FUEL GAS SYSTEM P&ID_rev0 → GFD01-D0013 等，
# 已由標籤詞彙認親收進家族）或根目錄的個人彙編（Hsinta_MCW_P&ID.pdf）。
EXTRA_FAMILIES = {
    # GT Generator Load Equipment Schematic（MLI 0440）：發電機定子 RTD 96DT-1A… 31 支 FF 位號只畫在這張圖的 p3；
    # 檔名的「Load Equipment」會讓 kind_of 判成電氣圖，儀器清單（instlist）卻把它列為這些裝置的 P&ID。
    '1-EGJ01-D0004': '發電機示意圖（96DT 定子 RTD；儀器清單列為 P&ID）',
}

# 不寫機組的圖：圖上沒有機組前綴的標籤只可能屬於哪個機組字母（鍵＝圖號的系統碼）
SCOPE_LETTER = {'TFD01': 'S', 'EGK01': 'S', 'GFD01': 'G', 'EGJ01': 'G'}

# 圖面自己聲明的「同型各台共用」典型圖（要加必須是圖上有明文證據的；每筆都在建置時驗證，驗不過就不套用並計數）。
# 鍵＝家族尾碼；drawn＝圖上畫的系統碼；stands_for＝同一張圖代表的其他系統碼；把關二擇一：
#   note＝圖上必須找得到的那句話（比對前兩邊都去掉空白、轉大寫；train_note_found）
#   rows＝OCR 對照表裡至少要有幾列「同一列既有 drawn 的格子、也有 stands_for 的格子，而且設備段相同」（train_rows_found）
TRAIN_TYPICALS = {
    # 凝結水泵：圖上印 "P&ID is applicable for all condensate pumps"，畫 LCC10；AMS 只有 LCC20／LCC30（沒有 LCC10）。
    '1-TCM01-D1114': {'note': 'P&ID is applicable for all condensate pumps', 'drawn': 'LCC10', 'stands_for': ('LCC20', 'LCC30')},
    # 給水泵組（Baker Hughes；整份沒有文字層）：p4／p5／p6 只畫 C10LAC50 這一台，封面的 ITEM 表列 C10／C20／C30 x LAC50／60／70 GP001，
    # p7／p8 的「INSTRUMENT／JUNCTION BOX／EQUIPMENT LIST」一列一支儀器、欄位是 1209808 (C10LAC50GP001)｜1209809 (C10LAC60GP001)｜
    # 1209810 (C10LAC70GP001)…＝各台的對照表（2026-10-10 兩位獨立查核者讀圖確認；裁決 A5 取代原本「只有一張」的決議 12）。
    # 這張圖沒有文字層可以找註記，所以把關改看 OCR 對照表的**結構**（rows）；湊不到就不套用並計數。
    '1-TDM01-D1205': {'rows': 10, 'drawn': 'LAC50', 'stands_for': ('LAC60', 'LAC70')},
}

# 圖上自己聲明「這一張不是本機組的組態」的圖紙（2026-10-10 裁決 A2；與 TRAIN_TYPICALS 同樣是「宣告＋建置時驗證」）。
# 鍵＝家族尾碼；note＝圖上必須找得到的那句話（去空白、轉大寫再比）；prefix＝那張圖紙的標籤所帶的 KKS 前綴。
# 建置時：note 找得到 → 這份圖裡「有 prefix 開頭的 KKS 系統段（如 X2MBP01）」的頁，一號機組的位號一律不發布
# （stats.dropped.foreign_sheet）；找不到 note → 規則不套用、計數並印出來。**以內容認頁，不寫死 PDF 頁碼**（第 9 版與第 10 版頁數不同）。
FOREIGN_SHEETS = {
    # GE 137T9790 Fuel Gas Performance Heating（Rev.10 的 PDF p5 是 GE sheet 1，note 12 原文）：
    #   "SPLIT HEAT EXCHANGER CONFIGURATION SHOWN ON SHEET 3 (KKS TAG PREFIX X2) IS APPLICABLE TO UNIT 2-2 (SN 299661).
    #    ALL OTHER UNIT CONFIGURATIONS REFLECT THAT SHOWN ON SHEET 2."
    # sheet 2（PDF p6）的標籤是 X1MPB01、sheet 3（PDF p7）是 X2MBP01；全文件集只有這兩頁有 X<數字> 前綴的 KKS 字。
    # 舊版把 p7 當成「不分機組」的第二張圖發給 70 支 G11_／G12_ 位號（其中 10 支位置與 p6 差 0.01 以上，最多 0.24）。
    # 查核者另確認：19 份不分機組的圖裡，這是唯一一句機組適用性的註記，所以沒有可推廣的通則。
    '1-GFD01-D0013': {'note': 'SPLIT HEAT EXCHANGER CONFIGURATION SHOWN ON SHEET 3 (KKS TAG PREFIX X2) IS APPLICABLE TO UNIT 2-2',
                      'prefix': 'X2'},
}

# 儀用／廠用空氣**分配圖**（2026-10-10 裁決 A3，note=3）：圖上一整排是「這顆閥的供氣接點」——空氣支管末端寫著用氣設備的位號
# （旁邊是 'HP TERMINAL ATTEMPERATOR SPRAY WATER CONTROL VALVE HT1-1-AFF01-D0002 SH.01' 這種去向說明）。位號讀得沒錯，
# 但那不是閥在製程管線上的位置；舊版當成符號發布，72 支位號裡有 23 支的第一個標記落在這裡、4 支只有這裡。
# 宣告家族＋每頁建置時驗證（air_sheet）：這頁要有 AIR_PHRASE、而且空氣系統自己的標籤（KKS 功能碼 QE／QF 開頭）≥ AIR_MIN_LABELS 個，
# 才算分配圖；這樣的頁上，**別的系統**的位號就是用氣點。BFD01-D0006 只有 p4 過得了（p2／p3 是排污槽與輔助設備本身，0 個 QF 標籤）。
AIR_SHEETS = {
    '1-AFF01-D0021': 'P&ID Compressed Air System（p2／p3：INSTRUMENT AIR／PLANT AIR DISTRIBUTION SYSTEM；QFB 221／278 個標籤）',
    '1-BFD01-D0006': 'HRSG PID - Auxiliary Equipment 的儀用空氣那一張（p4：INSTRUMENT AIR SYSTEM／SERVICE AIR SYSTEM；QFB 80 個標籤）',
}
AIR_SYS = ('QE', 'QF')                 # 壓縮空氣系統的 KKS 功能碼開頭（QEB 廠用空氣、QFB 儀用空氣…）
AIR_PHRASE = 'INSTRUMENTAIR'           # 去空白轉大寫後比
AIR_MIN_LABELS = 30

# 人工維護的**逐處覆寫表**（2026-10-10 裁決 A3）：通用規則判不出來、但讀圖已經確認的地方。每筆＝一個區域：
#   family 家族尾碼、page PDF 頁（1 起算）、box 轉正後比例的 (x0, y0, x1, y1)、note 要改成的代碼、why 證據（讀了哪張圖、看到什麼）。
# 符號命中（note=0）的**中心**落在區域裡就套用（不看位號，也不靠清單順序）。建置時沒有對到任何命中的條目會印出來並計數
# （stats.overrides.unmatched）——圖換版、頁序變了就會這樣，那時要重新讀圖，不可默默略過。
HIT_OVERRIDES = [
    # TDM01-D1205 p5（LUBE OIL SYSTEM，sheet 4 of 8）下緣一排五個小圖 ①~⑤「TYPICAL FOR TEMPERATURE TRANSMITTER ON OIL RESERVOIR／
    # PRESSURE TRANSMITTER ON LUBE OIL SUPPLY／LEVEL TRANSMITTER ON OIL RESERVOIR／DIFFERENTIAL PRESSURE TRANSMITTER ON LUBE OIL
    # FILTERS／PRESSURE TRANSMITTER ON LUBE OIL SUPPLY」＝迴路詳圖（傳送器球泡 → DCDAS 的 PI｜PAL 功能方塊），帶的是真位號。
    # 2026-10-10 查核者逐處讀圖（verify/audit-ocr-a/HIT_TABLE.md #32~#45）：這一區 12 處、右邊的 ⑥ 2 處。其中 C10LAC50BP005 的
    # 兩處都在小圖 ⑤ 裡（主圖右上角的球泡 OCR 沒讀到），舊版把 DCDAS 功能方塊當成它的位置。
    {'family': '1-TDM01-D1205', 'page': 5, 'box': (0.035, 0.835, 0.712, 0.960), 'note': 4,
     'why': 'p5 下緣小圖 ①~⑤ TYPICAL FOR … TRANSMITTER（迴路詳圖）'},
    # 同一頁右下、標題欄上方的小圖 ⑥「TYPICAL FOR TEMPERATURE TRANSMITTER ON LUBE OIL SUPPLY」（C10LAC50BT009 的 TE／TT → DCDAS TI｜TAH）
    {'family': '1-TDM01-D1205', 'page': 5, 'box': (0.713, 0.780, 0.882, 0.902), 'note': 4,
     'why': 'p5 右下小圖 ⑥ TYPICAL FOR TEMPERATURE TRANSMITTER ON LUBE OIL SUPPLY（迴路詳圖）'},
]
NOTE_SYMBOL, NOTE_LIST, NOTE_FLAG, NOTE_AIR, NOTE_INSET = 0, 1, 2, 3, 4      # pid.json 命中的 note 代碼（契約見 pid_index.py 檔頭）

REL_RANK = {'exact': 0, 'neutral': 1, 'typical': 2, 'loop': 3, 'train': 4}
# 內部關係（relation() 的回傳）→ 發布的五級
REL_CLASS = {'exact': 'exact', 'digits': 'exact', 'generic': 'neutral', 'nounit': 'neutral', 'ge_nounit': 'neutral',
             'typical': 'typical', 'digits_typ': 'typical', 'isa_loop': 'loop', 'train': 'train'}


def dumps(o):
    """決定性 JSON（鍵排序、無多餘空白；與 hmi_index.dumps 相同）。"""
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def load_ams(sqlite_path=None):
    """現行 AMS 位號 → 協定（HART／FF）。直接用 hmi_index.load_ams，P&ID 與 HMI 的母數才會永遠相同
    （母數＝不以 JK 開頭的位號，hmi_index.py 的 non_jk；2026-10-08 實測 1,928 → 1,679）。"""
    import hmi_index
    return hmi_index.load_ams(sqlite_path or paths.AMS_SQLITE)


# ================================================================ 一、文件集：檔名分類
DOCNO = re.compile(r'(HT(\d)-(\d)-([A-Z]{3}\d\d)-([A-Z])(\d{4}))(?:-([0-9A-Z]{1,2})(?![0-9A-Za-z]))?', re.I)
# 副本夾（與 build_card_aux.COPY_PATH_RE／docmap_docsearch 同規則，含設備 dossier 夾）
COPY_PATH_RE = re.compile(r'(^|/)(_舊版|_fix[^/]*|_chunks|_nb[^/]*|_缺漏補齊[^/]*|_xlsx_pdf|am10|am20|am30|所有線路圖)/|'
                          r'/(?:[a-z0-9]{3})?[a-z]{3}[a-z0-9]{2}[a-z]{2}\d{3}[^/]*/\d{2}_[^/]+/[^/]+$', re.I)
OLD_RE = re.compile(r'(^|/)_舊版/')
# 整夾都是彙編／教材／工作檔的資料夾（repo 的 regex 沒列，這個文件庫實際有）
COLLECTION_RE = re.compile(r'(^|/)(受訓資料|ge-scrape|92_[^/]*|所有線路圖|claude|AMS|_流程文件)/', re.I)
DOSSIER2_RE = re.compile(r'/\d{2}_(?:PID|P&ID)[^/]*流程圖[^/]*/[^/]+$|/[^/]*(?:Transmitter|Valve|傳送器|閥)[^/]*/\d{2}_[^/]+/[^/]+$', re.I)

NAME_PID = re.compile(r'P\s*&\s*I\s*D|P_ID|(?<![A-Z])PID(?![A-Z])|P\s*&\s*I\s+DIAG|PIPING\s*(?:&|AND)\s*INSTRUMENT|'
                      r'PROCESS\s*(?:&|AND)(?:AMP;)?\s*INSTRUMENT|管線儀表流程圖|'
                      r'(?:飲用水|生水|廢水|廢水收集|排水|空氣|消防|循環水|冷卻水|封油|海水|除礦水)系統圖', re.I)
NAME_SCHEM = re.compile(r'SYSTEM\s+SCHEMATIC|INSTRUMENT(?:S)?\s+DIAGRAM|PNEUMATIC\s+SCHEMATIC|HYDRAULIC\s+DIAGRAM|SEAL\s*OIL\s+SCHEMATIC|'
                        r'AUXILIARY\s+SYSTEMS\s+SCHEMATIC|MONITORING\s+INSTRUMENTS|FLUSHING\s+DIAGRAM|'
                        r'LUBE\s+AND\s+HYDRAULIC\s+OIL\s+MODULE|密封油系統示意圖', re.I)
# 控制理論的 PID（訓練教材）、EOMR、細部圖：檔名有「PID」也不是 P&ID
NOT_PID = re.compile(r'PID的|PID模型|PID\+?\s*CONTROL|PID\s*控制|PID整定|PID參數|EOMR|END\s+OF\s+MANUFACTUR|DETAIL\s+DRAWING|MARKUP\s+FOR', re.I)
PID_SYS = {('AFF01', 'D'), ('GFD01', 'D'), ('TFD01', 'D'), ('BFD01', 'D')}   # docmap_docindex.classify 的三組＋HRSG 廠商 PID

K_LEGEND = re.compile(r'SYMBOL|LEGEND\s+(?:FOR|SHEET)|^.*\bLEGENDS?\s+AND\s+GENERAL|NOMENCLATURE|圖例|符號', re.I)
K_INCL_LEGEND = re.compile(r'INCL\.?\s*LEGEND', re.I)
K_PFD = re.compile(r'(?<![A-Z])PFD(?![A-Z])|PROCESS\s+FLOW\s+DIAGRAM|HEAT\s*&\s*MATERIAL\s+BALANCE', re.I)
K_HVAC = re.compile(r'HVAC', re.I)
K_LIST = re.compile(r'\bLIST\b|DATA\s*SHEET|DATASHEET|EQUIPMENT\s+DATA|清單|清冊|規格', re.I)
K_ELEC = re.compile(r'ONE[\s\-]LINE|SINGLE\s+LINE|ELECTRICAL|WIRING|ALARM\s*&\s*TRIP|PROTECTION\s+SCHEM|POWER\s+DISTRIBUTION|'
                    r'CONNECTION\s+DIAGRAM|LOAD\s+EQUIPMENT|LIGHTING|P\.A\.\s*SYSTEM|LCI\s+COOLING|TERMINAL|CABLE|LOOP\s+DIAGRAM|接線|單線', re.I)
K_MANUAL = re.compile(r'OPERATING\s+DESCRIPTION|DESIGN\s+GUIDELINES|GUIDELINES|^PPT\b|MANUAL|說明|保養作業|STEEL\s+STRUCTURE|PIPE\s+RACK|'
                      r'OUTLINE|LOGIC|PART\s+LIST', re.I)
K_DUPNAME = re.compile(r'\(\d\)\s*(?:-\s*)?\.pdf$|^●|-合併|有註解|符號之意思', re.I)


def rev_is_title_word(rev_as_written, after):
    """文件編號後面那一兩個**純字母**其實是標題的第一個字、不是版次？（rev_as_written＝檔名裡原本的大小寫；after＝它後面的字）
    三種情形算標題字：小寫（'…D0027-of 3.pdf'）；後面緊接 '&'（'…D0027-P&ID.pdf'、'-I&C …'）；兩個字母而且隔著空白就接字
    （'…D0027-GT System.pdf'）。**單一個大寫字母後面隔空白接字的是真版次**（'…D3101-B Electrical and I&C Wiring Diagram'、
    '…R0001-B I&C Cabling Concept'，全庫 17 個），不可誤殺。2026-10-10 全庫 31,896 個檔名實測：真的字母版次都是單一個大寫字母
    （後面接 '-'、' - '、'_'、'('、'.pdf' 或空白），兩個字母的純字母版次 0 個、小寫 0 個、緊接 '&' 的 0 個——所以這三條現在
    一個真檔都不會碰到，只擋將來的怪檔名。數字或數字加字母（'4'、'1b'）不在此列。"""
    if not rev_as_written or not rev_as_written.isalpha():
        return False
    if rev_as_written != rev_as_written.upper() or after.startswith('&'):
        return True
    return len(rev_as_written) == 2 and bool(re.match(r'\s+[0-9A-Za-z]', after))


def docno(base):
    """檔名 → (完整文件編號 'HTx-1-SSSnn-Lnnnn', HT 後第一碼, 第二碼, 系統碼, 類別字母, 流水號, 版次) 或 None。
    緊接在編號後面的標題字不算版次（rev_is_title_word）。"""
    m = DOCNO.search(base)
    if not m:
        return None
    rev = m.group(7) or ''
    if rev and rev_is_title_word(rev, base[m.end():]):
        rev = ''
    return (m.group(1).upper(), m.group(2), m.group(3), m.group(4).upper(), m.group(5).upper(), m.group(6), rev.upper())


def rev_rank(rev):
    """版次新舊（越大越新）：數字 > 字母 > 無；數字比大小，數字後面帶一個字母的（'1A'、'0b'）排在同數字的後面（'1' < '1A' < '2'）；
    純字母先比長度再比字典序（A < B < … < Z < AA）。
    repo 既有的 rev_key 對字母版次只取前兩欄，等於所有字母版次同級、靠修改時間決定；這裡把字母也排了序。"""
    rev = (rev or '').upper()
    if not rev:
        return (0, 0, 0, '')
    if rev.isdigit():
        return (2, int(rev), 0, '')
    m = re.fullmatch(r'(\d+)([A-Z])', rev)
    if m:
        return (2, int(m.group(1)), 1, m.group(2))
    return (1, 0, len(rev), rev)


def vendor_name(base):
    """'noKKS_標題_revX.pdf'／'<KKS>_etc_標題_revX.pdf' → (前綴, 標題, 版次) 或 None。"""
    m = re.match(r'^(.*?)_(?:etc_)?(.+?)_rev([^.]*)\.*\.pdf$', base, re.I)
    if not m:
        return None
    return (m.group(1), m.group(2), m.group(3).strip("-' ").upper())


def title_of(base):
    """檔名 → 分類用的標題（去文件編號、括號、重複檔尾碼；只供 kind_of 與認親，不是給人看的）。"""
    t = os.path.splitext(base)[0]
    d = DOCNO.search(t)
    if d:
        t = t[:d.start()] + ' ' + t[d.end():]
    v = vendor_name(base)
    if v and not d:
        t = v[1]
    t = re.sub(r'\(\d\)\s*$', ' ', t)
    t = re.sub(r'[_（）()\[\]【】●]+', ' ', t)
    t = re.sub(r'\s*-\s*$|^\s*-\s*', ' ', t.strip())
    return re.sub(r'\s+', ' ', t).strip(' -')


def title_tokens(title):
    """標題 → 詞集合（去掉張數「1 of 2」與 P&ID／SYSTEM／DIAGRAM 這類每張圖都有的字），標題相似度用。"""
    t = title.upper()
    t = re.sub(r'\(?\b\d+\s*(?:OF|/|_|-)\s*\d+\)?', ' ', t)
    t = re.sub(r'P\s*&\s*ID|PIPING\s*(?:&|AND)\s*INSTRUMENT(?:ATION)?\s*DIAGRAMS?|\bPID\b|INCL\.?\s*LEGEND|\bCOMMON\b|UNIT-?\d|'
               r'\bFOR\b|\bOF\b|\bTHE\b|\bAND\b|SYSTEM|DIAGRAM', ' ', t)
    return frozenset(re.findall(r'[A-Z0-9一-鿿]{2,}', t))


def title_key(title):
    """沒有文字層的廠商檔名副本認親用的標題鍵：title_tokens 再去掉帶數字的詞（'002'、'12HAP65GP001' 這種檔名前綴殘段）、
    純中文的詞（業主檔名前面加的中文圖名）、以及被檔名長度截斷的 'SYSTE'／'DIAGRA'。兩邊的鍵**完全相同**才算同一張圖。"""
    out = set()
    for t in title_tokens(title):
        if any(c.isdigit() for c in t) or not re.search(r'[A-Z]', t):
            continue
        if len(t) >= 4 and t != 'SYSTEM' and t != 'DIAGRAM' and ('SYSTEM'.startswith(t) or 'DIAGRAM'.startswith(t)):
            continue
        out.add(t)
    return frozenset(out)


def jaccard(a, b):
    return len(a & b) / float(len(a | b)) if (a or b) else 0.0


def kind_of(rel):
    """只看檔名判文件種類：pid／legend／pfd／hvac／list／elec／manual／other（規則的理由見檔頭「文件集」）。"""
    base = rel.rsplit('/', 1)[-1]
    t = title_of(base)
    dn = docno(base)
    if NOT_PID.search(t):
        return 'manual'
    if K_HVAC.search(t):
        return 'hvac'
    if K_PFD.search(t) and not NAME_PID.search(t):
        return 'pfd'
    if K_LIST.search(t):
        return 'list'
    if K_MANUAL.search(t) and not re.search(r'P&ID\s+(?:FOR|DIAGRAM\s+FOR)', t, re.I):
        if not (NAME_PID.search(t) and not re.search(r'OPERATING|GUIDELINE|PPT|LOGIC|PART LIST|OUTLINE|STEEL|RACK', t, re.I)):
            return 'manual'
    if K_ELEC.search(t) and not NAME_PID.search(t):
        return 'elec'
    if K_LEGEND.search(t) and not K_INCL_LEGEND.search(t):
        return 'legend'
    if NAME_PID.search(t) or NAME_SCHEM.search(t):
        return 'pid'
    if dn and (dn[3], dn[4]) in PID_SYS:
        if dn[3] == 'AFF01' and int(dn[5]) < 2:
            return 'legend'             # AFF01-D0001 ＝ 全廠 P&ID 圖例
        if dn[3] == 'AFF01' and int(dn[5]) > 99:
            return 'other'              # AFF01-D27xx ＝ 設備細部圖
        return 'pid'
    if re.search(r'FLOW\s*DIAGRAM|流程圖', t, re.I):
        return 'pfd'
    return 'other'


def copy_flags(rel):
    """路徑上的副本／舊版／彙編夾旗標：old／copy_path／collection／dossier／dupname／root。"""
    low = '/' + rel
    f = []
    if OLD_RE.search(low):
        f.append('old')
    if COPY_PATH_RE.search(low):
        f.append('copy_path')
    if COLLECTION_RE.search(low):
        f.append('collection')
    if DOSSIER2_RE.search(low):
        f.append('dossier')
    if K_DUPNAME.search(rel.rsplit('/', 1)[-1]):
        f.append('dupname')
    if '/' not in rel:
        f.append('root')
    return f


def ident(rel):
    """文件庫相對路徑 → (doc, rev, stem, title)：圖號、版次、slug 的前段、給人看的標題——**全部取自檔名**。
    圖框裡印的編號不可靠（D0027 的圖紙上根本沒印業主編號 HT0-1-KND01-D0027，只有廠商圖號與六個別份文件的參照），
    印的張數 n/m 也有 16 % 與 PDF 頁序、檔名都對不上，所以身分只認檔名，頁次只說「PDF 第 p 頁」。"""
    base = rel.rsplit('/', 1)[-1]
    m = DOCNO_VAL_RE.search(base.upper())
    doc = m.group(1) if m else None
    rev = (m.group(2) if m else None) or None
    cut = m.end() if m else 0
    if rev and rev_is_title_word(base[m.start(2):m.end(2)], base[m.end():]):
        rev, cut = None, m.end(1)                                    # 緊接在編號後面的標題字不是版次（'…D0027-GT System'）
    stem = (doc + ('-' + rev if rev else '')) if doc else 'x'
    title = re.sub(r'\.pdf$', '', base, flags=re.I)
    if m:
        title = title[:m.start()] + ' ' + title[cut:]
    title = re.sub(r'\s*-?\s*\(\d\)\s*-?\s*$', ' ', title)          # 重複下載的「- (2)」
    title = re.sub(r'\s+', ' ', title).strip(' -_')
    return doc, rev, stem, title


def slug(rel, page):
    """圖紙鍵（SPEC 第 2 節）：<STEM>_<sha1(rel)[:8]>__p<頁>；不合 SLUG_RE 就丟例外（產生器要中止）。"""
    s = '%s_%s__p%d' % (ident(rel)[2], hashlib.sha1(rel.encode('utf-8')).hexdigest()[:8], page)
    if not SLUG_RE.match(s):
        raise ValueError('slug 不合規則：%r（%s 第 %d 頁）' % (s, rel, page))
    return s


def walk_pdfs(root):
    """現場走訪文件庫 → [(相對路徑（posix）, 大小, 修改時間秒)]，依路徑排序。唯讀；讀不到的資料夾略過。"""
    root = os.path.normpath(root)
    out = []
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.name.lower().endswith('.pdf'):
                        st = e.stat()
                        out.append((os.path.relpath(e.path, root).replace('\\', '/'), st.st_size, int(st.st_mtime)))
                except OSError:
                    continue
    out.sort()
    return out


# ================================================================ 二、幾何
_ORDER = 'ENWS'                         # 把畫面順時針轉 90 度，閱讀方向 N→E、W→N、S→W、E→S
_R_OF = {'E': 0, 'N': 90, 'W': 180, 'S': 270}
_DIR_CODE = {0: 'E', 1: 'S', 2: 'W', 3: 'N'}      # 快取裡的方向碼：0=(1,0) 由左往右、1=(0,1) 由上往下、2=倒字、3=(0,-1) 由下往上
_DIRS = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}


def page_geom(page):
    """fitz.Page 或文字層快取的一頁（dict）→ (顯示寬, 顯示高, /Rotate, rotation_matrix 六個數)。
    顯示＝套完 /Rotate 之後（page.rect）；rotation_matrix 把未旋轉座標帶到顯示空間。"""
    if isinstance(page, dict):
        return page['w'], page['h'], page['rot'], page['rm']
    r = page.rect
    m = page.rotation_matrix
    return r.width, r.height, page.rotation, (m.a, m.b, m.c, m.d, m.e, m.f)


def text_dirs(page):
    """文字層各閱讀方向的字數（**未旋轉**空間）→ {'E','N','W','S'}。fitz.Page 逐行數；快取頁用字框的方向碼加總。"""
    dirs = Counter()
    if isinstance(page, dict):
        for w in page['words']:
            c = _DIR_CODE.get(w[5])
            if c:
                dirs[c] += len(w[4])
        return dict(dirs)
    import fitz
    for b in page.get_text('dict', flags=fitz.TEXTFLAGS_WORDS)['blocks']:
        for ln in b.get('lines', []):
            dx, dy = ln.get('dir', (1, 0))
            if not (abs(abs(dx) - 1) < 0.02 or abs(abs(dy) - 1) < 0.02):
                continue
            c = _DIR_CODE.get(_DIRS.get((int(round(dx)), int(round(dy)))))
            n = sum(len(s['text'].replace(' ', '')) for s in ln['spans'])
            if c and n:
                dirs[c] += n
    return dict(dirs)


def rot_dirs(d, deg):
    """把畫面順時針轉 deg 度之後，各閱讀方向的字數。"""
    k = (deg // 90) % 4
    out = {}
    for c, v in d.items():
        if c in _ORDER:
            c2 = _ORDER[(_ORDER.index(c) - k) % 4]
            out[c2] = out.get(c2, 0) + v
    return out


def decide_R(dirs_disp, W, H):
    """dirs_disp＝**顯示空間**（套完 /Rotate）各閱讀方向的字數；W、H＝page.rect 的寬高 → (R, 信心, 字數, 規則)。
    規則 1 argmax：字數最多的方向就是水平。
    規則 2 landscape-pair（只用在大圖＝長邊 ≥ 1000 pt）：規則 1 若讓圖紙直立，就看兩個橫式候選；工程圖只有水平字與
           由下往上的直書字，選「有一些水平字（≥ 1.5 % 且 ≥ 20 字）、禁用方向 ≤ 5 %、而且比規則 1 少」的那個
           （洩水／排水 P&ID 有 50~88 % 是直書閥號）。
    沒有字回 (None, 0, 0, 'none')。"""
    d = {k: dirs_disp.get(k, 0) for k in _ORDER}
    n = sum(d.values())
    if not n:
        return None, 0.0, 0, 'none'

    def parts(R):
        dd = rot_dirs(d, R)
        return dd.get('E', 0), dd.get('N', 0), dd.get('W', 0) + dd.get('S', 0)      # 水平、由下往上、禁用方向

    A = max(_ORDER, key=lambda k: d[k])
    R = _R_OF[A]
    rule = 'argmax'
    land = (W > H) if R in (0, 180) else (H > W)
    if not land and max(W, H) >= COVER_LONG_PT:
        bad0 = parts(R)[2]
        for R2 in ((R + 90) % 360, (R + 270) % 360):
            h, _v, bad = parts(R2)
            if h >= 0.015 * n and h >= 20 and bad <= 0.05 * n and bad < bad0:
                R = R2
                rule = 'landscape-pair'
                break
    h, v, _bad = parts(R)
    return R, (h + v) / n, n, rule


def upright_rotation_info(page):
    """→ {'R', 'method': 'text'|'text-thin'|None, 'rule', 'conf', 'n'}。method='text' 才是可信的（字數 ≥ MIN_ORIENT_CHARS）；
    'text-thin' 的 R 只能當沒有 OCR 時的退路；完全沒有字 → R=None。"""
    W, H, rot, _rm = page_geom(page)
    R, conf, n, rule = decide_R(rot_dirs(text_dirs(page), rot), W, H)
    if R is None:
        return {'R': None, 'method': None, 'rule': 'none', 'conf': 0.0, 'n': 0}
    return {'R': R, 'method': 'text' if n >= MIN_ORIENT_CHARS else 'text-thin', 'rule': rule, 'conf': round(conf, 3), 'n': n}


def upright_rotation_text(page):
    """文字層定出的轉正角 R（0／90／180／270；定義見檔頭「幾何」）；文字層不足以判斷（< 400 字）回 None。
    page 可以是 fitz.Page，也可以是文字層快取的一頁。回 None 的頁要靠 OCR 定向（pid_ocr）。"""
    i = upright_rotation_info(page)
    return i['R'] if i['method'] == 'text' else None


def upright_size(page, R):
    """轉正後的圖紙尺寸 (w_pt, h_pt)。"""
    W, H, _rot, _rm = page_geom(page)
    return (H, W) if R in (90, 270) else (W, H)


def to_upright_frac(page, rect, R):
    """rect＝(x0, y0, x1, y1)，就是 page.get_text('words'|'dict') 或 search_for 回的座標（**未旋轉**頁面空間）
    → (fx0, fy0, fx1, fy1)：轉正後整張圖的 0~1 比例，左上為原點。page 可以是 fitz.Page 或文字層快取的一頁。"""
    W, H, _rot, m = page_geom(page)
    a, b, c, d, e, f = m
    xs, ys = [], []
    for x, y in ((rect[0], rect[1]), (rect[2], rect[3])):
        xs.append((x * a + y * c + e) / W)                           # 未旋轉 → 顯示空間（點 × rotation_matrix）
        ys.append((x * b + y * d + f) / H)
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if R == 0:
        fr = (x0, y0, x1, y1)
    elif R == 90:
        fr = (1 - y1, x0, 1 - y0, x1)
    elif R == 180:
        fr = (1 - x1, 1 - y1, 1 - x0, 1 - y0)
    elif R == 270:
        fr = (y0, 1 - x1, y1, 1 - x0)
    else:
        raise ValueError('R 只能是 0／90／180／270：%r' % (R,))
    return tuple(min(max(v, 0.0), 1.0) for v in fr)


def rerotate_frac(box, d_r):
    """(fx0, fy0, fx1, fy1) 是以 R1 轉正的比例 → 換成以 R2 轉正的比例；d_r＝(R2 − R1) % 360。
    工具函式（換算別的轉正慣例存下來的框時用）。pid_index **不會**拿它去「修正」對照表：對照表的 rot 與文字層定出的 R
    不一致時，那一頁的 OCR 整筆不用（見 pid_index.py 檔頭），因為不一致通常代表框本身就是在錯的方向上量的。"""
    x0, y0, x1, y1 = box
    d_r %= 360
    if d_r == 0:
        return (x0, y0, x1, y1)
    if d_r == 90:
        return (1 - y1, x0, 1 - y0, x1)
    if d_r == 180:
        return (1 - x1, 1 - y1, 1 - x0, 1 - y0)
    if d_r == 270:
        return (y0, 1 - x1, y1, 1 - x0)
    raise ValueError(d_r)


def render_upright(page, R, long_px=None, zoom=None, gray=False):
    """轉正後的整頁 fitz.Pixmap。long_px＝輸出影像長邊的像素數，或 zoom＝每 pt 幾個像素（二擇一）。
    get_pixmap 自己會套 /Rotate，所以矩陣只需要再 prerotate(R)。"""
    import fitz
    r = page.rect
    z = zoom if zoom else float(long_px) / max(r.width, r.height)
    return page.get_pixmap(matrix=fitz.Matrix(z, z).prerotate(R), alpha=False, colorspace=fitz.csGRAY if gray else fitz.csRGB)


def is_cover(page):
    """A4／Letter 直式的頁＝送審封面（或夾在圖冊裡的文字頁），不是圖紙。page＝fitz.Page 或快取頁。"""
    W, H, _rot, _rm = page_geom(page)
    return max(W, H) < COVER_LONG_PT and H > W


# ---------------------------------------------------------------- 圖框分區（orient 探勘的 gridzone）
_ONE = re.compile(r'^(?:[A-Z]|\d{1,2})$')
_LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'      # 圖框字母通常跳過 I 與 O
_LETTERS_ALL = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def _seq_ok(labs):
    txt = [t for _, t in labs]
    if all(t.isdigit() for t in txt):
        v = [int(t) for t in txt]
        d = {b - a for a, b in zip(v, v[1:])}
        return (d <= {1} or d <= {-1}) and len(v) >= 3, 'num'
    if all(t.isalpha() for t in txt):
        for alpha in (_LETTERS, _LETTERS_ALL):
            try:
                v = [alpha.index(t) for t in txt]
            except ValueError:
                continue
            d = {b - a for a, b in zip(v, v[1:])}
            if (d <= {1} or d <= {-1}) and len(v) >= 3:
                return True, 'alpha'
        return False, 'alpha'
    return False, 'mixed'


def _best_line(cands, axis, tol=0.006):
    best = []
    key = sorted(cands, key=lambda c: (c[axis], c[1 - axis], c[2]))
    i = 0
    while i < len(key):
        j = i
        while j + 1 < len(key) and key[j + 1][axis] - key[i][axis] <= tol:
            j += 1
        grp = key[i:j + 1]
        if len(grp) > len(best):
            best = grp
        i += 1
    return best


def _edge(labels, side, band=0.07):
    if side == 'top':
        c = [x for x in labels if x[1] < band]
        ax, along = 1, 0
    elif side == 'bottom':
        c = [x for x in labels if x[1] > 1 - band]
        ax, along = 1, 0
    elif side == 'left':
        c = [x for x in labels if x[0] < band]
        ax, along = 0, 1
    else:
        c = [x for x in labels if x[0] > 1 - band]
        ax, along = 0, 1
    c = [x for x in c if _ONE.match(x[2])]
    if len(c) < 3:
        return []
    g = sorted({(round(x[along], 4), x[2]) for x in _best_line(c, ax)})
    out = []
    for p, t in g:
        if out and abs(p - out[-1][0]) < 0.004 and t == out[-1][1]:
            continue
        out.append((p, t))
    return out


def _uniform(labs):
    p = [x for x, _ in labs]
    d = [b - a for a, b in zip(p, p[1:])]
    if not d:
        return False, 0
    m = sorted(d)[len(d) // 2]
    inner = d[1:-1] if len(d) > 2 else d
    ok = all(abs(x - m) <= 0.15 * m for x in inner) and all(abs(x - m) <= 0.35 * m for x in (d[0], d[-1]))
    return ok, m


def _pick(labels, a, b):
    good = []
    for side in (a, b):
        e = _edge(labels, side)
        ok, kind = _seq_ok(e) if e else (False, '')
        uni, pitch = _uniform(e) if e else (False, 0)
        if ok and uni:
            good.append({'labs': e, 'kind': kind, 'pitch': pitch})
    if not good:
        return None
    return max(good, key=lambda r: len(r['labs']))          # 兩邊一樣多取第一邊（上／左）


def detect_grid(labels):
    """labels＝[(cx, cy, text)]（轉正後 0~1 比例；通常是文字層裡 1~2 個字元的字）→ 圖框格線 dict 或 None。
    每一軸要求：靠邊 7 % 內、同一條線上 ≥ 3 個、連號（數字或字母，可倒序）、間距均勻（頭尾兩格放寬到 35 %）。"""
    cols = _pick(labels, 'top', 'bottom')
    rows = _pick(labels, 'left', 'right')
    if not cols or not rows:
        return None
    return _grid_out(cols, rows, 'text')


def _fit_axis(labels, sides):
    pts = sorted(pt for s in sides for pt in _edge(labels, s))
    best = None
    for kind, alpha in (('num', None), ('alpha', _LETTERS), ('alpha', _LETTERS_ALL)):
        if kind == 'num':
            arr = [(p, int(t)) for p, t in pts if t.isdigit()]
        else:
            arr = [(p, alpha.index(t)) for p, t in pts if t.isalpha() and t in alpha]
        if len({v for _, v in arr}) < 3:
            continue
        pit = [(pj - pi) / (vj - vi) for i, (pi, vi) in enumerate(arr) for (pj, vj) in arr[i + 1:] if vj != vi]
        pos = [x for x in pit if x > 0]
        neg = [x for x in pit if x < 0]
        grp = pos if len(pos) >= len(neg) else neg
        pitch = statistics.median(grp)
        if abs(pitch) < 0.02:
            continue
        org = statistics.median(p - v * pitch for p, v in arr)
        inl = [(p, v) for p, v in arr if abs(p - (org + v * pitch)) < 0.25 * abs(pitch)]
        nv = len({v for _, v in inl})
        if nv < 3:
            continue
        org = statistics.median(p - v * pitch for p, v in inl)
        if best is None or nv > best[0]:
            best = (nv, kind, alpha, pitch, org, inl)
    if not best:
        return None
    nv, kind, alpha, pitch, org, inl = best
    lo = min(v for _, v in inl) - 1
    hi = max(v for _, v in inl) + 1
    if kind == 'num' and min(v for _, v in inl) >= 1:
        lo = max(lo, 1)
    lo = max(lo, 0)
    if kind == 'alpha':
        hi = min(hi, len(alpha) - 1)
    labs = []
    for v in range(lo, hi + 1):
        p = org + v * pitch
        seen = any(v == vv for _, vv in inl)
        if seen or (p - 0.3 * abs(pitch) > 0.005 and p + 0.3 * abs(pitch) < 0.995):      # 沒讀到的端格要放得進圖紙
            labs.append((p, str(v) if kind == 'num' else alpha[v]))
    labs.sort()
    return {'labs': labs, 'kind': kind, 'pitch': abs(pitch)}


def fit_grid(labels):
    """OCR 讀到的邊條標籤（會漏讀、誤讀）→ 容缺擬合的格線 dict 或 None：位置 = 原點 + 序號 × 間距，
    兩個對邊一起用，至少 3 個相異序號吻合同一個間距。labels 格式同 detect_grid。"""
    cols = _fit_axis(labels, ('top', 'bottom'))
    rows = _fit_axis(labels, ('left', 'right'))
    if not cols or not rows:
        return None
    return _grid_out(cols, rows, 'ocr')


def _grid_out(cols, rows, src):
    def ax(g):
        return {'labs': [[round(p, 4), t] for p, t in g['labs']], 'pitch': round(g['pitch'], 5), 'kind': g['kind']}
    return {'ok': True, 'src': src, 'cols': ax(cols), 'rows': ax(rows)}


def _bounds(labs, pitch):
    """n 個標籤 → n+1 條邊界。中間取相鄰標籤的中點；頭尾兩格常被圖框與標題欄截短、標籤也不在正中，
    所以頭尾第一條內部邊界改由相鄰邊界加減一個間距外推。"""
    p = [x for x, _ in labs]
    mid = [(a + c) / 2 for a, c in zip(p, p[1:])]
    if len(mid) >= 4:
        mid[0] = mid[1] - pitch
        mid[-1] = mid[-2] + pitch
    return [max(mid[0] - pitch, 0.0)] + mid + [min(mid[-1] + pitch, 1.0)]


def zone_of(grid, fx, fy, near=0.004, near_pitch=0.03, edge=0.012, edge_pitch=0.10):
    """(fx, fy)＝轉正後的比例 → (分區 'C-5', 是否靠近邊界)；沒有格線或點在圖框外 → (None, False)。
    一律印成「字母-數字」。邊界是由標籤位置推回去的（相鄰標籤的中點）。
    「靠近邊界」（卡片寫「約 C-5」）＝離某條內部邊界不到 min(near, near_pitch × 格距)＝**格距的 3 %**（上限圖寬的 0.4 %）。
    這個數字是量出來的（2026-10-10 裁決 A11）：被引用的圖紙只有四種圖框（AFF01 17x12、BFD01 16x12、GE 的 GFD01／TFD01／
    EGJ01／EGK01 16x10、KND01 8x8 倒序），各挑一張把上緣與左緣的邊條放大、疊上算出來的邊界讀圖，邊界與圖框印的刻度線
    最多差圖寬的 0.13 %（＝格距的 2 %；AFF01 與各張的列方向完全重合）。舊值是格距的一成，等於每條邊界兩側各一成、
    整張圖三成多的面積都算「靠近」——1,693 處有分區的命中裡 580 處（34 %）被寫成「約」，新值是一成左右。
    點在圖框外的容許值（edge、edge_pitch）不變：那是「最外面一格的邊界是外推的」的容差，與上面量的不是同一件事。"""
    if not grid or not grid.get('ok'):
        return None, False
    out = []
    nb = False
    for g, v in ((grid['rows'], fy), (grid['cols'], fx)):
        b = _bounds(g['labs'], g['pitch'])
        tol_e = min(edge, edge_pitch * g['pitch'])
        if v < b[0] - tol_e or v > b[-1] + tol_e:
            return None, False
        k = 0
        while k < len(g['labs']) - 1 and v > b[k + 1]:
            k += 1
        out.append(g['labs'][k][1])
        tol = min(near, near_pitch * g['pitch'])
        nb = nb or any(abs(v - x) < tol for x in b[1:-1])
    r, c = out
    if r.isdigit() and c.isalpha():
        r, c = c, r
    return '%s-%s' % (r, c), nb


def border_labels(page, R):
    """文字層快取的一頁 → 可能是圖框標籤的字 [(cx, cy, text)]（1 個字母或 1~2 位數字；轉正後比例），給 detect_grid。"""
    out = []
    for w in page['words']:
        t = w[4].strip()
        if _ONE.match(t):
            f = to_upright_frac(page, w, R)
            out.append(((f[0] + f[2]) / 2, (f[1] + f[3]) / 2, t))
    return out


# ================================================================ 三、文字層快取
def text_cache_path(cache_dir, rel):
    return os.path.join(cache_dir, hashlib.sha1(rel.lower().encode('utf-8')).hexdigest()[:20] + '.json.gz')


def extract_text(abs_path):
    """開 PDF 抽每一頁的字框（唯讀）→ 快取記錄（不含 size／mtime）。
    每頁：w、h＝顯示尺寸（page.rect）；rot＝/Rotate；rm＝rotation_matrix；words＝[x0, y0, x1, y1, 字, 方向碼, 同行字數]
    （座標是**未旋轉**空間，四捨五入到 0.1 pt）；img＝[嵌入影像數, 最大影像像素]；clen＝內容串流長度。"""
    import fitz
    rec = {'v': TEXT_CACHE_VERSION, 'pages': 0, 'err': None, 'pg': []}
    # 讀不了的檔（壞檔、空檔、有密碼、零頁）一律記進 err 回去，**絕不丟例外**：文件庫是雲端硬碟的同步夾，
    # 31,896 個 PDF 裡只要有一個檔名像 P&ID 的檔有密碼，舊版就整個 pid_index（連帶整個重建）中止在 traceback 上——
    # PyMuPDF 開加密檔不會出錯，要到 page_count／逐頁讀才丟 ValueError。
    try:
        doc = fitz.open(abs_path)
    except Exception as e:                                # noqa: BLE001
        # PyMuPDF 的訊息會帶整條本機路徑（"Cannot open empty file: filename='C:\…'"）；記錄裡只留原因
        rec['err'] = re.sub(r"\s*:?\s*(?:filename=)?'[^']*[\\/][^']*'?", '', str(e))[:120].strip() or type(e).__name__
        return rec
    try:
        n_pages = 0
        if doc.needs_pass:
            rec['err'] = 'encrypted（要密碼才能開）'
        else:
            n_pages = doc.page_count
            if n_pages <= 0:
                rec['err'] = 'no pages（零頁）'
    except Exception as e:                                # noqa: BLE001
        rec['err'] = str(e)[:120] or type(e).__name__
    if rec['err']:
        try:
            doc.close()
        except Exception:                                 # noqa: BLE001
            pass
        return rec
    rec['pages'] = n_pages
    for i in range(n_pages):
        if i >= MAX_TEXT_PAGES:
            break
        try:
            page = doc.load_page(i)
            r = page.rect
            m = page.rotation_matrix
        except Exception as e:                            # noqa: BLE001
            rec['err'] = 'p%d %s' % (i + 1, str(e)[:80])
            break                                         # 這一頁讀不了：後面的頁碼會對不上，到此為止（pages 仍是總頁數 → 算 truncated）
        words = []
        try:
            tp = page.get_textpage(flags=fitz.TEXTFLAGS_WORDS)
            ldir = {}
            for b in page.get_text('dict', textpage=tp)['blocks']:
                for li, ln in enumerate(b.get('lines', [])):
                    dx, dy = ln.get('dir', (1, 0))
                    ok = abs(abs(dx) - 1) < 0.02 or abs(abs(dy) - 1) < 0.02
                    ldir[(b['number'], li)] = _DIRS.get((int(round(dx)), int(round(dy))), 4) if ok else 4
            ws = page.get_text('words', textpage=tp)
            nline = Counter((w[5], w[6]) for w in ws)
            for w in ws:
                words.append([round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1), w[4],
                              ldir.get((w[5], w[6]), 4), nline[(w[5], w[6])]])
        except Exception as e:                            # noqa: BLE001
            rec['err'] = 'p%d %s' % (i + 1, str(e)[:80])
        try:
            imgs = page.get_images(full=True)
            img = [len(imgs), max([im[2] * im[3] for im in imgs] or [0])]
        except Exception:                                 # noqa: BLE001
            img = [0, 0]
        try:
            clen = len(page.read_contents())
        except Exception:                                 # noqa: BLE001
            clen = -1
        rec['pg'].append({'w': round(r.width, 2), 'h': round(r.height, 2), 'rot': page.rotation,
                          'rm': [round(v, 4) for v in (m.a, m.b, m.c, m.d, m.e, m.f)], 'words': words, 'img': img, 'clen': clen})
    doc.close()
    return rec


def _read_cache(cp, size, mtime):
    try:
        with gzip.open(cp, 'rt', encoding='utf-8') as f:
            d = json.load(f)
    except Exception:                                     # noqa: BLE001
        return None
    if d.get('v') != TEXT_CACHE_VERSION or d.get('size') != size or d.get('mtime') != mtime:
        return None
    return d


def _extract_job(job):
    """（多行程工作函式）一份 PDF：快取有效就跳過，否則抽文字寫快取。回 (rel, 是否重抽, 錯誤訊息)。"""
    root, rel, size, mtime, cache_dir = job
    cp = text_cache_path(cache_dir, rel)
    if _read_cache(cp, size, mtime) is not None:
        return rel, False, None
    try:
        rec = extract_text(os.path.join(root, rel.replace('/', os.sep)))
    except Exception as e:                                # noqa: BLE001 — extract_text 自己不該丟；真丟了也只算這一份讀不了
        rec = {'v': TEXT_CACHE_VERSION, 'pages': 0, 'err': '%s: %s' % (type(e).__name__, str(e)[:100]), 'pg': []}
    rec['size'], rec['mtime'] = size, mtime
    tmp = cp + '.%d.tmp' % os.getpid()
    with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=5) as f:
        json.dump(rec, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, cp)
    return rel, True, rec.get('err')


def ensure_text(root, files, cache_dir=None, jobs=0, log=None):
    """把 files＝[(rel, size, mtime)] 的文字層快取補齊（鍵＝路徑；內容記 size＋mtime，不符就重抽）。
    一份 PDF 一個快取檔，隨時中斷都可續跑；jobs > 1 用多行程（Windows 下呼叫端必須在 __main__ 保護內）。
    回 (重抽幾份, {rel: 錯誤訊息})。"""
    cache_dir = cache_dir or paths.PID_TEXT_CACHE
    os.makedirs(cache_dir, exist_ok=True)
    todo = [(root, rel, size, mtime, cache_dir) for rel, size, mtime in files
            if not _cache_fresh(text_cache_path(cache_dir, rel), size, mtime)]
    errs = {}
    if not todo:
        return 0, errs
    if log:
        log('文字層快取：%d 份要抽（共 %d 份）…' % (len(todo), len(files)))
    if jobs and jobs > 1 and len(todo) > 8:
        import multiprocessing as mp
        with mp.Pool(min(jobs, len(todo))) as pool:
            res = list(pool.imap_unordered(_extract_job, todo, chunksize=4))
    else:
        res = [_extract_job(j) for j in todo]
    for rel, _fresh, err in res:
        if err:
            errs[rel] = err
    return len(todo), errs


def _cache_fresh(cp, size, mtime):
    """快取檔存在、解得開、而且版本／size／mtime 都對（_read_cache 會整個解壓核對；build_corpus 走的是自己先解一次的路，
    只有直接呼叫 ensure_text 的地方會經過這裡）。"""
    return os.path.exists(cp) and _read_cache(cp, size, mtime) is not None


def load_text(root, rel, size, mtime, cache_dir=None):
    """→ 快取記錄 {'pages': 總頁數, 'pg': [頁…], 'err'}；沒有或過期就當場抽（單行程）。"""
    cache_dir = cache_dir or paths.PID_TEXT_CACHE
    d = _read_cache(text_cache_path(cache_dir, rel), size, mtime)
    if d is None:
        os.makedirs(cache_dir, exist_ok=True)
        _extract_job((root, rel, size, mtime, cache_dir))
        d = _read_cache(text_cache_path(cache_dir, rel), size, mtime)
    return d


# ================================================================ 四、正規化與比對
KKS_CORE = r'[A-Z]{3}\d{2}[A-Z]{2}\d{3}'
AMS_KKS = re.compile(r'^([A-Z])(\d)(\d)(' + KKS_CORE + r')$')
AMS_SUFFIX = re.compile(r'(?:_\d\d|_|(?<=\d{3})[A-Z])$')       # AMS 這邊的裝飾：G11_96PH-F1_01／C10LAF71QN001_／S10MAV01BP272C
AMS_GE = re.compile(r'^([GS]\d\d)_(.+)$')
AMS_ISA = re.compile(r'^(\d)-([A-Z]{2,4})-([A-Z]{2}\d{3})-(\d)([A-Z]{0,2})$')
_STRIP = '=()[]{}<>,;:.\'"“”‘’|/\\*#'
# 圖上的 KKS 寫法： =G11HSD10QN101｜G11HSD10QN101｜11HSD10QN101｜GXXHSD10QN101｜XXHSD…｜HSD10QN101
PDF_KKS = re.compile(r'^(?:([A-Z])([0-9XY])([0-9XY])|([0-9XY])([0-9XY]))?(' + KKS_CORE + r')([A-Z]?)(?:[\-_/].*)?$')
# 同上，但把核心後面的尾碼原樣取出來（parse_pdf_label 用）：緊貼的元件字母（A／B／AB／C）或元件碼（N1／B1／B2），
# 以及 '-'／'_'／'/' 之後的尾巴（'-BL01' 子項、'/2/3' 連號）。PDF_KKS 本身不動：它還決定哪些字算「像位號」
# （表格列偵測、label_pt、廠商檔名副本的標籤詞彙認親），放寬它會連文件集一起變。
PDF_KKS_EX = re.compile(r'^(?:([A-Z])([0-9XY])([0-9XY])|([0-9XY])([0-9XY]))?(' + KKS_CORE + r')([A-Z]{1,2}|[A-Z]\d{1,2})?([\-_/].*)?$')
SFX_SUB = re.compile(r'^-[A-Z]{2}\d{2,3}$')                     # 子項：'MKW15BL001-BL01'（LT 底下的 LE 元件）
SFX_SEQ = re.compile(r'^(?:/\d{1,3})+$')                        # 連號：'C10MAG10BL001/2/3'＝BL001、BL002、BL003（只出現在跨圖訊號旗標裡）
PDF_KKS_SYS = re.compile(r'^(?:([A-Z])([0-9XY])([0-9XY])|([0-9XY])([0-9XY]))?([A-Z]{3}\d{2})$')     # '=G11HAD60'／'11HAD60'／'HAD60'
PDF_KKS_EQ = re.compile(r'^([A-Z]{2}\d{3})([A-Z]?)$')                                            # 'CT001'
PDF_UNIT_PREFIX = re.compile(r'^(?:[A-Z][0-9XY]{2}|[0-9XY]{2})$')                                # 自成一個文字物件的 '=G11'
ISA_RE = re.compile(r'^(\d)-([A-Z]{2,4})-([A-Z]{2}\d{3})-(\d)([A-Z]{0,2})$')
GE_RE = re.compile(r'(?<![A-Z0-9])(\d{2}[A-Z][A-Z0-9]{1,6}(?:-[A-Z0-9]{1,5}){1,2})(?![A-Z0-9])')    # 96FG-1／90VA41-31／96TT-GT-10
_TABLE_TAGGY = (re.compile(r'^\d{2}[A-Z]{2,}[A-Z0-9]*-'), re.compile(r'^\d-[A-Z]{2,4}-'))


def clean_token(s):
    """PDF 的一個字 → 大寫、去掉頭尾的 '='／括號／標點（中間的 - 與 _ 保留）。"""
    return s.upper().replace('＝', '=').strip().strip(_STRIP + ' ')


def parse_pdf_kks(tok):
    """clean_token 過的字 → (字母或 '', 機組兩碼如 '11'／'XX'／'', 核心, 元件字母) 或 None。"""
    m = PDF_KKS.match(tok)
    if not m:
        return None
    if m.group(1):
        return (m.group(1), m.group(2) + m.group(3), m.group(6), m.group(7) or '')
    if m.group(4):
        return ('', m.group(4) + m.group(5), m.group(6), m.group(7) or '')
    return ('', '', m.group(6), m.group(7) or '')


def parse_pdf_label(tok):
    """clean_token 過的字 → (字母或 '', 機組兩碼, 核心, 尾碼, 是否連號) 或 None。比 parse_pdf_kks 多認「核心＋元件碼」
    （'G11MAN31QN001N1'）並把尾碼交出來，歸戶時要拿它跟 AMS 位號自己的尾碼比（_attribute_kks；規則與由來見該函式）：
      尾碼 ''      圖上就是這個核心（'…BP272'）；'/2/3' 這種連號也算（標籤代表 BL001 起的幾支，連號旗標另由 note 表示）
      尾碼 'C'／'A'／'AB'／'N1'／'B2'／'-BL01'   元件字母／元件碼／子項＝**另一個項目**
    認不得的尾巴（'-'／'_'／'/' 之後的其他字）照舊當成沒有尾碼——2026-10-10 全庫 372 張圖的文字層裡，含 AMS 核心的字
    只有五種尾巴：沒有 900、元件碼 N1／B1／B2 56、連號 /2/3 10、子項 -BL01 4、元件字母 C 1。"""
    m = PDF_KKS_EX.match(tok)
    if not m:
        return None
    sfx = m.group(7) or ''
    tail = m.group(8) or ''
    seq = False
    if not sfx and tail:
        if SFX_SUB.match(tail):
            sfx = tail
        elif SFX_SEQ.match(tail):
            seq = True
    if m.group(1):
        return (m.group(1), m.group(2) + m.group(3), m.group(6), sfx, seq)
    if m.group(4):
        return ('', m.group(4) + m.group(5), m.group(6), sfx, seq)
    return ('', '', m.group(6), sfx, seq)


def tag_shape(t):
    """AMS 位號的形狀：KKS／GE／ISA／other（統計用；other＝時間戳、殘缺名稱，本來就定位不到）。"""
    if AMS_KKS.match(t) or (AMS_SUFFIX.sub('', t) != t and AMS_KKS.match(AMS_SUFFIX.sub('', t))):
        return 'KKS'
    if AMS_GE.match(t):
        return 'GE'
    if AMS_ISA.match(t):
        return 'ISA'
    return 'other'


def tag_system(t):
    """AMS 位號（KKS 形）→ 系統碼五碼（'G11HAD10QN002' → 'HAD10'）；不是 KKS 形回 ''。"""
    m = AMS_KKS.match(t) or AMS_KKS.match(AMS_SUFFIX.sub('', t))
    return m.group(4)[:5] if m else ''


def build_index(tags):
    """AMS 位號 → 查表。JK*（HART MUX 模組）不收。AMS 這邊的裝飾（尾端 _、_01、元件字母）剝掉再建索引。
      kks       核心 → [(位號, 字母, 機組兩碼, 剝掉的尾碼)]
      ge        GE 元件名 → [(位號, 剝掉的尾碼)]
      isa       ISA 全名 → 位號          isa_loop  (機組數字, 功能首字母, 迴路, 序號) → [位號]
      cores     KKS 核心集合（OCR 形近字修復的判準）      units  AMS 出現過的機組前綴（C10／G11／G12／S10）"""
    kks = defaultdict(list)
    ge = defaultdict(list)
    isa = {}
    isa_loop = defaultdict(list)
    for t in sorted(tags):
        if t.startswith('JK'):
            continue
        m = AMS_KKS.match(t)
        sfx = ''
        if not m:
            b = AMS_SUFFIX.sub('', t)
            if b != t and AMS_KKS.match(b):
                m, sfx = AMS_KKS.match(b), t[len(b):]
        if m:
            kks[m.group(4)].append((t, m.group(1), m.group(2) + m.group(3), sfx))
            continue
        m = AMS_GE.match(t)
        if m:
            core = m.group(2)
            ge[core].append((t, ''))
            b = re.sub(r'_\d\d$', '', core)
            if b != core:
                ge[b].append((t, core[len(b):]))
            continue
        m = AMS_ISA.match(t)
        if m:
            isa[t] = t
            isa_loop[(m.group(1), m.group(2)[0], m.group(3), m.group(4))].append(t)     # 開頭數字＝機組：2-PIT-… 不是 1-PI-…
    return {'kks': dict(kks), 'ge': dict(ge), 'isa': isa, 'isa_loop': dict(isa_loop), 'cores': frozenset(kks),
            'units': frozenset(tl + tu for v in kks.values() for (_t, tl, tu, _s) in v)}


def relation(tag_letter, tag_unit, lab_letter, lab_unit):
    """圖上標籤的機組前綴 ↔ AMS 位號的機組 → 內部關係名或 None（None＝絕不歸戶）。
      exact       同字母同機組（=G12… ↔ G12…）          digits      只寫數字且相同（11HSD… ↔ G11…）
      generic     佔位符（=GXX…、XX…、G1X…）且不矛盾     nounit      圖上沒寫機組（HSD10QN101）
      typical     同字母、同 Block 的另一部氣機（=G11… ↔ G12…）   digits_typ  只寫數字的同上（11… ↔ G12…）
    字母不同（C10 與 G11）、Block 不同（C20／G21／G31）、非氣機的不同機組 → None。"""
    if lab_letter and lab_letter != tag_letter:
        return None
    if not lab_unit:
        return 'nounit'
    if any(ch in 'XY' for ch in lab_unit):
        ok = all(a in 'XY' or a == b for a, b in zip(lab_unit, tag_unit))
        return 'generic' if ok else None
    if lab_unit == tag_unit:
        return 'exact' if lab_letter else 'digits'
    if lab_unit[0] != tag_unit[0]:
        return None
    if tag_letter == 'G' and tag_unit[1] in '12' and lab_unit[1] in '12':
        return 'typical' if lab_letter else 'digits_typ'
    return None


def own_suffix(sfx):
    """AMS 位號被 build_index 剝掉的尾碼 → 這支位號**自己的**元件尾碼：字母（S10MAV01BP272C 的 'C'）照留；
    '_'、'_01' 是 AMS 命名的裝飾，圖上本來就不會寫，視為沒有尾碼。"""
    return sfx if sfx.isalpha() else ''


def _attribute_kks(ix, letter, unit, core, ctx, lab_sfx=''):
    """圖上讀到的 (字母, 機組, 核心, 尾碼) → [(位號, 發布關係, drawn_as, AMS 尾碼)]。
    ctx＝{'scope': 圖的歸屬字母或 None, 'train': TRAIN_TYPICALS 的一筆或 None, 'drops': Counter, 'rej': list}。
    **尾碼必須相等**（2026-10-10 獨立查核的裁決 A1）：標籤核心後面帶元件字母／元件碼／子項的（'…BP272C'、'…BT044A'、
    '…BT008AB'、'…QN001N1'、'…BL001-BL01'）是**另一個項目**，只有 AMS 位號自己的尾碼（own_suffix）與它相同才歸戶，
    沒有「退而歸給不帶尾碼的那支」這回事。由來：S10MAV01BP272（PDIT，PDT-272）與 S10MAV01BP272C（PT-270C）是兩台儀器，
    舊版把尾碼丟掉再比，兩張卡片互相標到對方的球泡上；控制閥的 ZI／ZIC／ZIO 回授球泡（N1／B1／B2）與 RTD 的 A／B 元件、
    清單裡 A／B／AB 各自成列的格子同理（AFF01-D0007 p2 還有一處圖面自己把鄰閥的回授球泡標成 QN001B1／B2）。
    因為尾碼不合而沒歸戶的記進 ctx['rej']（呼叫端補上框與標籤）與 drops['sfx_mismatch']。"""
    out = []
    scope = ctx.get('scope')
    drawn = (letter + unit) if (letter or unit) else ''
    rej = ctx.get('rej')
    for (tag, tl, tu, sfx) in ix['kks'].get(core, ()):
        rel = relation(tl, tu, letter, unit)
        if not rel:
            continue
        if scope and rel == 'nounit' and tl != scope:
            ctx['drops']['scope_letter'] += 1                 # 汽機圖上的 'LBA10BT001' 是 S10 的，不是 G12LBA10BT001
            continue
        if own_suffix(sfx) != lab_sfx:
            ctx['drops']['sfx_mismatch'] += 1
            if rej is not None:
                rej.append((tag, 'sfx_mismatch'))
            continue
        out.append((tag, REL_CLASS[rel], drawn, sfx))
    tr = ctx.get('train')
    if tr and core.startswith(tr['drawn']):
        for sysc in tr['stands_for']:
            for (tag, tl, tu, sfx) in ix['kks'].get(sysc + core[len(tr['drawn']):], ()):
                if relation(tl, tu, letter, unit) in ('exact', 'digits', 'generic', 'nounit'):
                    if own_suffix(sfx) != lab_sfx:
                        continue                              # 典型畫法同樣要尾碼相等（LAC50 的 BT044A 不代表 LAC60 的 BT044）
                    out.append((tag, 'train', tr['drawn'], sfx))
    return out


def _attribute_ge(ix, gcore, gunit, ctx):
    """GE 元件名（整詞相等）→ [(位號, 發布關係, drawn_as, AMS 尾碼)]。"""
    out = []
    scope = ctx.get('scope')
    for tag, sfx in ix['ge'].get(gcore, ()):
        if gunit and not tag.startswith(gunit + '_'):
            continue
        if not gunit and scope and tag[0] != scope:
            ctx['drops']['scope_letter'] += 1                 # G11_／G12_ 的元件名不歸到汽機圖上
            continue
        out.append((tag, 'exact' if gunit else 'neutral', gunit, sfx))
    return out


def _attribute_isa(ix, text):
    """ISA 名（'1-TI-CW011-1AA'）→ [(位號, 發布關係, drawn_as, '')]：全名相等＝exact；只對到迴路＝loop。"""
    if text in ix['isa']:
        return [(ix['isa'][text], 'exact', '', '')]
    m = ISA_RE.match(text)
    if m:
        return [(t, 'loop', '', '') for t in ix['isa_loop'].get((m.group(1), m.group(2)[0], m.group(3), m.group(4)), ())]
    return []


def reading_frame(w):
    """字框 → (沿行中心, 跨行中心, 字高, 行首邊)，全部換到「這個字自己的閱讀方向」：下一行永遠在跨行座標較大的那一側。"""
    x0, y0, x1, y1, d = w[0], w[1], w[2], w[3], w[5]
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    if d == 1:          # 由上往下寫：下一行在左邊（x 較小）
        return (cy, -cx, x1 - x0, y0)
    if d == 3:          # 由下往上寫：下一行在右邊（x 較大）
        return (-cy, cx, x1 - x0, -y1)
    if d == 2:          # 倒字
        return (-cx, -cy, y1 - y0, -x1)
    return (cx, cy, y1 - y0, x0)


def _label_text(words, members, form):
    """圖上實際寫的字：拆寫的片段依閱讀順序以一個空白相接；'=G11'＋'HSD10QN101' 這種前綴拆寫直接相連。"""
    parts = [re.sub(r'\s+', ' ', words[i][4]).strip() for i in members]
    s = (''.join(parts) if form == 'prefixed' else ' '.join(parts))
    return re.sub(r':(?=[\\/])', ': ', s)


def page_candidates(words):
    """一頁的字框 → 標籤候選 [(正規化文字, 框 [x0,y0,x1,y1], 形式, 成員字的索引)]＋表格列成員集合。
    形式：word 單一個字／prefixed '=G11' 另成一個文字物件接在前面／stacked 系統段在上一行／inline 同一行隔一格。
    座標沿用輸入字框的座標系（文字層＝未旋轉空間；OCR＝轉正後的 pt），合併規則以 reading_frame 為準所以與方向無關。"""
    toks = [clean_token(w[4]) for w in words]
    frames = [reading_frame(w) for w in words]
    cand = []
    S, E = [], []
    U = defaultdict(list)
    for i, tok in enumerate(toks):
        if tok and PDF_UNIT_PREFIX.match(tok) and (words[i][4].lstrip('([ ').startswith('=') or tok[0].isalpha()):
            U[words[i][5]].append(i)
    pref = {}
    if U:
        for i, tok in enumerate(toks):
            if not tok:
                continue
            k = parse_pdf_kks(tok)
            ms = PDF_KKS_SYS.match(tok)
            if not ((k and not k[0] and not k[1]) or (ms and not ms.group(1) and not ms.group(4))):
                continue
            ia, ic, ih, _ = frames[i]
            if ih <= 0:
                continue
            iw = max(words[i][2] - words[i][0], words[i][3] - words[i][1])
            for u in U.get(words[i][5], ()):
                ua, uc, _uh, _ = frames[u]
                uw = max(words[u][2] - words[u][0], words[u][3] - words[u][1])
                gap = ((ia - ua) * 1.0 - iw / 2.0 - uw / 2.0) / ih
                if abs(uc - ic) <= 0.35 * ih and -0.4 <= gap <= 1.0:
                    pref[i] = u
                    break
    texts, boxes, memb = {}, {}, {}
    for i, tok in enumerate(toks):
        if not tok:
            continue
        if i in pref:
            u = pref[i]
            texts[i] = toks[u] + tok
            boxes[i] = [min(words[u][0], words[i][0]), min(words[u][1], words[i][1]), max(words[u][2], words[i][2]), max(words[u][3], words[i][3])]
            memb[i] = (u, i)
            cand.append((texts[i], boxes[i], 'prefixed', (u, i)))
        else:
            texts[i] = tok
            boxes[i] = list(words[i][:4])
            memb[i] = (i,)
            cand.append((tok, boxes[i], 'word', (i,)))
        if PDF_KKS_SYS.match(texts[i]):
            S.append(i)
        elif PDF_KKS_EQ.match(tok):
            E.append(i)
    # 拆寫合併：系統段正好在設備段的上一行（以閱讀方向為準）且置中；或同一行、中間隔一格
    if S and E:
        byd = defaultdict(list)
        for i in S:
            byd[words[i][5]].append(i)
        for e in E:
            ea, ec, eh, _ = frames[e]
            if eh <= 0:
                continue
            best = None
            for s in byd.get(words[e][5], ()):
                sa, sc, _sh, _ = frames[s]
                da, dc = (sa - ea) / eh, (sc - ec) / eh
                if -1.7 <= dc <= -0.6 and abs(da) <= 1.2:
                    score = abs(da) + abs(dc + 1.1)
                    form = 'stacked'
                elif abs(dc) <= 0.35 and da < 0:
                    sw = max(words[s][2] - words[s][0], words[s][3] - words[s][1])
                    ew = max(words[e][2] - words[e][0], words[e][3] - words[e][1])
                    gap = (-da * eh - sw / 2.0 - ew / 2.0) / eh
                    if gap > 1.6 or gap < -0.3:
                        continue
                    score = 2 + gap
                    form = 'inline'
                else:
                    continue
                if best is None or score < best[0]:
                    best = (score, s, form)
            if best:
                s = best[1]
                box = [min(boxes[s][0], words[e][0]), min(boxes[s][1], words[e][1]), max(boxes[s][2], words[e][2]), max(boxes[s][3], words[e][3])]
                cand.append((texts[s] + toks[e], box, best[2], memb[s] + (e,)))
    # 表格列：≥ 5 個像位號的字共用同一條行首邊、間距緊密規律
    taggy = [i for i, tok in enumerate(toks) if tok and (parse_pdf_kks(tok) or PDF_KKS_SYS.match(tok) or any(r.match(tok) for r in _TABLE_TAGGY))]
    table = set()
    groups = defaultdict(list)
    for i in taggy:
        _a, c, h, st = frames[i]
        groups[(words[i][5], int(round(st / 2.0)))].append((c, h, i))
    for lst in groups.values():
        if len(lst) < 5:
            continue
        lst.sort()
        run = [lst[0]]
        for prev, cur in zip(lst, lst[1:]):
            if cur[0] - prev[0] <= 2.6 * max(prev[1], 1):
                run.append(cur)
            else:
                if len(run) >= 5:
                    table.update(x[2] for x in run)
                run = [cur]
        if len(run) >= 5:
            table.update(x[2] for x in run)
    return cand, table


_FLAG_ABOVE = re.compile(r'^(?:HST/|1GP0\d{3,})')                 # 旗標上緣的訊號編號：'HST/10/E/LC------EN/FD/001'、'1GP030089.001'
_FLAG_BELOW = re.compile(r'HT\d-\d-[A-Z]{3}\d\d-D\d{4}|DCDAS\s+(?:TO|FROM)|\bSH\.\d')   # 旗標下緣：去向圖號／DCDAS TO、FROM／SH.01


def _in_frame(cx, cy, d):
    """(cx, cy) → 以方向碼 d 的閱讀方向為準的 (沿行, 跨行) 座標（與 reading_frame 同一套）。"""
    if d == 1:
        return cy, -cx
    if d == 3:
        return -cy, cx
    if d == 2:
        return -cx, -cy
    return cx, cy


def signal_flag(words, members, form):
    """這個標籤是不是寫在**跨圖訊號旗標**裡（CTCI 的 AFF01 圖：一個箭頭形的框，上緣是訊號編號 'HST/10/E/…'／'1GP0…'，
    中間是位號，下緣是「DCDAS TO／FROM …」與去向圖號 'HT0-1-AFF01-D0013 SH.01'）。旗標是「這個訊號接到另一張圖」的引用，
    不是儀器畫在這裡——真正的球泡在它指過去的那張圖上。
    判法（2026-10-10 文字層查核的分類器 weak2.py 原樣搬來；它在 1,660 處文字層命中上挑出的 15 處逐一讀圖確認過）：
    以標籤自己的閱讀方向為準，標籤長度左右各放寬三成的範圍內，上方 0.15~3.0 個行高有訊號編號、**而且**下方 0.15~3.6 個行高
    有去向圖號或 DCDAS TO／FROM。上下各只有一項的不算（球泡旁邊剛好有一行圖號的情形）。"""
    d = words[members[0]][5]
    a0 = a1 = c0 = c1 = None
    for m in members:
        w = words[m]
        for (x, y) in ((w[0], w[1]), (w[2], w[3])):
            a, c = _in_frame(x, y, d)
            a0, a1 = (a if a0 is None else min(a0, a)), (a if a1 is None else max(a1, a))
            c0, c1 = (c if c0 is None else min(c0, c)), (c if c1 is None else max(c1, c))
    lh = (c1 - c0) / (2.0 if form == 'stacked' else 1.0)
    if lh <= 0:
        return False
    pad = 0.3 * (a1 - a0)
    above = False
    below = []
    mem = set(members)
    for i, w in enumerate(words):
        if i in mem:
            continue
        a, c = _in_frame((w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0, d)
        if not (a0 - pad <= a <= a1 + pad):
            continue
        da, db = (c0 - c) / lh, (c - c1) / lh
        if 0.15 <= da <= 3.0 and _FLAG_ABOVE.match(w[4].strip()):
            above = True
        if 0.15 <= db <= 3.6:
            below.append((db, i, w[4]))
    if not above:
        return False
    below.sort()
    return bool(_FLAG_BELOW.search(' '.join(t for _d, _i, t in below)))


def match_page(words, ix, ctx=None):
    """文字層的一頁字框 → 命中 [{tag, rel, drawn_as, form, box, label, note, nk, sfx}]。
    box 是輸入字框的座標系（文字層＝未旋轉空間，之後用 to_upright_frac 轉）；rel 是發布的五級之一；
    note＝**發布用的代碼**：0 符號標籤、1 清單欄或附註句子裡的字、2 跨圖訊號旗標（signal_flag；'…BL001/2/3' 連號也算）；
    nk＝細分（''／'table' 整齊排列的清單欄／'sentence' ≥ 4 個字的一行文字／'flag'），只供追查用。
    ctx＝{'scope', 'train', 'drops', 'rej'}（make_ctx 產生）。同一支位號同一個框只出一筆。
    尾碼不合而沒歸戶的（_attribute_kks）記在 ctx['rej']：{tag, why, box, label, form}，座標系同命中。"""
    ctx = ctx or make_ctx()
    cand, table = page_candidates(words)
    hits = []
    seen = set()
    rej = ctx.get('rej')

    def emit(found, form, box, members, nk, seq=False):
        note = 1 if nk else 0
        if found and not nk and (seq or signal_flag(words, members, form)):
            note, nk = 2, 'flag'
        for tag, rel, drawn, sfx in found:
            if rel == 'train' and note:
                continue                                      # 典型畫法只認符號：清單／附註／旗標裡的 LCC10 不代表 LCC20 畫在那裡
            key = (tag, round(box[0]), round(box[1]), form == 'word', rel)
            if key in seen:
                continue
            seen.add(key)
            hits.append({'tag': tag, 'rel': rel, 'drawn_as': drawn, 'form': form, 'box': [round(v, 1) for v in box],
                         'label': _label_text(words, members, form), 'note': note, 'nk': nk, 'sfx': sfx})

    for text, box, form, members in cand:
        nk = 'table' if any(m in table for m in members) else ''
        if not nk and form in ('word', 'prefixed') and words[members[-1]][6] >= 4:
            nk = 'sentence'
        k = parse_pdf_label(text)
        if k:
            n0 = len(rej) if rej is not None else 0
            emit(_attribute_kks(ix, k[0], k[1], k[2], ctx, k[3]), form, box, members, nk, k[4])
            if rej is not None:
                for j in range(n0, len(rej)):
                    rej[j] = {'tag': rej[j][0], 'why': rej[j][1], 'box': [round(v, 1) for v in box],
                              'label': _label_text(words, members, form), 'form': form}
            continue
        if form != 'word':
            continue
        m = re.match(r'^([GS]\d\d)[_\-](.+)$', text)            # GE 元件名：嚴格整詞相等，可帶 G11_／G12_ 前綴
        gcore, gunit = (m.group(2), m.group(1)) if m else (text, '')
        if gcore in ix['ge']:
            emit(_attribute_ge(ix, gcore, gunit, ctx), form, box, members, nk)
            continue
        emit(_attribute_isa(ix, text), form, box, members, nk)
    return hits


def make_ctx(family=None, sysc=None, train_ok=False):
    """一張圖的比對情境：歸屬字母（SCOPE_LETTER）與圖面自己聲明的同型典型（TRAIN_TYPICALS，train_ok 才套）。
    drops＝各種「沒歸戶」的計數；rej＝因尾碼不合而沒歸戶的明細（match_page／match_ocr_tokens 填，呼叫端每頁取走）。"""
    tail = re.sub(r'^HT\d-', '', family or '')
    return {'scope': SCOPE_LETTER.get(sysc or ''), 'train': TRAIN_TYPICALS.get(tail) if train_ok else None, 'drops': Counter(),
            'rej': []}


def train_note_found(pages, note):
    """圖面聲明典型的那句話是否真的印在圖上（任一頁）。字在文字層裡是一個字一個字的，所以兩邊都去空白、轉大寫再找。"""
    want = re.sub(r'\s+', '', note).upper()
    for pg in pages:
        if want in re.sub(r'\s+', '', ''.join(w[4] for w in pg['words'])).upper():
            return True
    return False


def foreign_pages(pages, decl):
    """FOREIGN_SHEETS 的一筆 → 這份圖裡「不是本機組組態」的頁（1 起算的集合）。
    note 那句話要印在圖上（任一頁）才算數；頁的認法＝文字層裡有 decl['prefix'] 開頭的 KKS 系統段（'X2MBP01'）。
    找不到 note 回 None（呼叫端計數並印出來，規則不套用）。"""
    if not train_note_found(pages, decl['note']):
        return None
    rx = re.compile('^' + re.escape(decl['prefix']) + r'[A-Z]{3}\d{2}')
    return {i for i, pg in enumerate(pages, 1) if any(rx.match(clean_token(w[4])) for w in pg['words'])}


def air_sheet(words):
    """這一頁是不是壓縮空氣的**分配圖**（AIR_SHEETS 的每頁驗證）→ (是否, 空氣系統標籤數)。
    條件：頁面上印著 AIR_PHRASE，而且 KKS 功能碼以 AIR_SYS 開頭的標籤（完整位號或拆寫的系統段）≥ AIR_MIN_LABELS 個。"""
    n = 0
    for w in words:
        tok = clean_token(w[4])
        k = parse_pdf_kks(tok) if tok else None
        ms = None if (k or not tok) else PDF_KKS_SYS.match(tok)
        sysc = k[2] if k else (ms.group(6) if ms else '')
        if sysc[:2] in AIR_SYS:
            n += 1
    if n < AIR_MIN_LABELS:
        return False, n
    return AIR_PHRASE in re.sub(r'\s+', '', ''.join(w[4] for w in words)).upper(), n


def train_rows_found(token_pages, ix, tr, min_score=OCR_MIN_SCORE):
    """TRAIN_TYPICALS 的 rows 把關：OCR 對照表裡，這份圖有幾列「同一列既有 drawn 系統的格子、也有 stands_for 系統的格子，
    而且設備段（含尾碼）相同」。token_pages＝[這份圖每一頁的 tokens]（pid_ocr_map 的格式：[text, cx, cy, w, h, score]）。
    同一列＝中心的 y 差不到半個框高。只數分數夠的字；同一頁同一個設備段只算一列（清單有 C10／C20／C30 三組欄位，
    一列會有好幾個 drawn 的格子）。2026-10-10 實測 TDM01-D1205 整份 189 列（門檻 10）。"""
    rows = set()
    for pi, tokens in enumerate(token_pages):
        cells = []
        for tk in tokens or []:
            if float(tk[5]) < min_score:
                continue
            for it in ocr_scan(tk[0], ix)[3]:
                for core in it['cores']:
                    cells.append((core[:5], core[5:] + it['sfx'], tk[2], tk[4]))
        want = defaultdict(list)
        for sysc, eq, cy, h in cells:
            if sysc in tr['stands_for']:
                want[eq].append((cy, h))
        for sysc, eq, cy, h in cells:
            if sysc == tr['drawn'] and any(abs(cy - cy2) <= 0.5 * min(h, h2) for cy2, h2 in want.get(eq, ())):
                rows.add((pi, eq))
    return len(rows)


def tag_word_stats(words):
    """一頁文字層 → (像位號的字數, 這些字的字高清單 pt, 系統碼集合 {(字母或 '', 'HSD')})。
    像位號＝完整 KKS、KKS 系統段／設備段、GE 元件名、ISA 名的形狀（與 AMS 有沒有這支無關）。
    系統碼取 KKS 功能碼的三個字母（HSD、LAC、HAD）：線條字的圖文字層裡常常只剩幾個閥號，比到五碼會漏掉同系統的另一張。"""
    n = 0
    hs = []
    systems = set()
    for w in words:
        tok = clean_token(w[4])
        if not tok:
            continue
        k = parse_pdf_kks(tok)
        ms = None if k else PDF_KKS_SYS.match(tok)
        if k:
            systems.add((k[0], k[2][:3]))
        elif ms:
            systems.add((ms.group(1) or '', ms.group(6)[:3]))
        elif not (PDF_KKS_EQ.match(tok) or GE_RE.fullmatch(tok) or ISA_RE.match(tok)):
            continue
        n += 1
        if w[5] in (0, 2):
            hs.append(w[3] - w[1])
        elif w[5] in (1, 3):
            hs.append(w[2] - w[0])
    return n, hs, systems


def label_height_pt(words):
    """這張圖上位號字的典型字高（pt；字框的短邊＝行高）＝像位號的字的中位數；不到 5 個回 None。pid_shots 用它決定影像大小。"""
    _n, hs, _s = tag_word_stats(words)
    hs = [h for h in hs if h > 0]
    return round(statistics.median(hs), 2) if len(hs) >= 5 else None


# ---------------------------------------------------------------- OCR 這一側
_OCR_DASH = dict.fromkeys(map(ord, '‐‑‒–—―−_﹣－'), '-')
_OCR_CORE = re.compile(r'([A-Z]{3}\d{2}[A-Z]{2}\d{3})(?!\d)')
_OCR_SLASH = re.compile(r'([A-Z]{3})(\d{2})((?:/\d{2}){1,3})([A-Z]{2}\d{3})(?!\d)')       # 'C10PHC10/20BT011' ＝ PHC10BT011＋PHC20BT011
_OCR_SYS = re.compile(r'^(?:[A-Z][0-9XY]{2}|[0-9XY]{2})?[A-Z]{3}\d{2}$')
# 形近字：字母位出現的數字可能是哪些字母；數字位出現的字母可能是哪些數字
TO_DIGIT = {'O': '0', 'Q': '0', 'D': '0', 'I': '1', 'L': '1', 'T': '17', 'S': '5', 'B': '8', 'Z': '27', 'G': '6', 'A': '4'}
TO_LETTER = {'0': 'OQD', '1': 'ILT', '5': 'S', '8': 'B', '2': 'Z', '6': 'G', '4': 'A', '7': 'TZ'}
_SHAPE = 'LLLDDLLDDD'
_EQ_STOP = frozenset(('DN', 'PN', 'NB', 'NO', 'OD', 'ID'))      # 管徑／壓力等級不是 KKS 設備段（DN300、PN016）


def ocr_clean(s):
    """OCR 原文 → NFKC、大寫、各種破折號與底線統一成 '-'、去掉所有空白（OCR 會在字中間插空白）。"""
    s = unicodedata.normalize('NFKC', s or '').upper().translate(_OCR_DASH)
    return re.sub(r'\s+', '', s)


_OCR_UNITLIST = re.compile(r'([A-Z])(\d\d)[/&,](?:\1)?(\d\d)$')            # 'G11/12HAP65 BP001'＝11、12 兩部機共用的標籤
_OCR_SEP_PREFIX = re.compile(r'[A-Z][0-9XY' + ''.join(sorted(TO_DIGIT)) + r']{2}[^A-Z0-9]{1,2}$')    # '=G11.'、'G11:'：機組被標點切開
_OCR_SFX = (re.compile(r'([A-Z]{1,2})(?![A-Z0-9])'), re.compile(r'([A-Z]\d{1,2})(?![A-Z0-9])'), re.compile(r'(-[A-Z]{2}\d{2,3})(?![A-Z0-9])'))


def _ocr_prefix(t, p, units):
    """核心從 t[p] 開始 → (字母, [機組…], 修了幾個字, 前綴起點) 或 None（前綴讀不出來，整個不收）。
    看核心前面緊貼的英數字：
      'G11/12'／'G11/G12'／'G11&12'   機組清單＝這個標籤同時屬於兩部機，各自都是 exact（BMM01-D3702 p2 的 'G11/12HAP65 BP001'；
                                      舊版只認到後面的 '12'，G11 那一支就漏了）
      沒有                            圖上沒寫機組——但前面隔著一兩個標點又是一組像機組的字（'=G11.HSD10QN101'、'G11:HSD…'）
                                      ＝機組被切開、讀不準，不收
      末三碼是 '字母+兩碼'            照讀；末三碼可用形近字修成**唯一一個** AMS 機組＝修
      只有兩位數字                    只寫數字的機組
      其餘（單一個字母＝前綴只剩一碼、單一數字、無法解讀的黏字）＝不收。寧可漏，不可把典型圖說成不分機組。"""
    before = t[:p]
    m = _OCR_UNITLIST.search(before)
    if m and (m.start() == 0 or not before[m.start() - 1].isalnum()):
        return (m.group(1), [m.group(2), m.group(3)], 0, m.start())
    i = p
    while i > 0 and p - i < 5 and t[i - 1].isalnum():
        i -= 1
    pre = t[i:p]
    if not pre:
        if _OCR_SEP_PREFIX.search(before):
            return None
        return ('', [''], 0, p)
    p3 = pre[-3:]
    if len(p3) == 3 and re.fullmatch(r'[A-Z][0-9XY]{2}', p3):
        return (p3[0], [p3[1:]], 0, p - 3)
    if len(p3) == 3 and p3[0].isalpha() and all(c.isdigit() or c in TO_DIGIT for c in p3[1:]):
        opts = [(c if c.isdigit() else TO_DIGIT[c]) for c in p3[1:]]
        c = {p3[0] + a + b for a in opts[0] for b in opts[1]} & set(units)
        if len(c) == 1:
            u = next(iter(c))
            return (u[0], [u[1:]], sum(1 for ch in p3[1:] if not ch.isdigit()), p - 3)
    if re.fullmatch(r'[0-9XY]{2}', pre):
        return ('', [pre], 0, p - 2)
    return None


def _ocr_suffix(tail):
    """核心後面到下一個標籤之前的字 → 尾碼：元件字母（A／B／AB／C）、元件碼（N1／B1／B2）、子項（-BL01）；其餘回 ''。
    管徑之類黏上來的鄰字（'DN25'、'/DN25'）、尾端的標點（'/'、')'）不是尾碼。兩個字母的鄰字（黏上來的功能碼 'TE'）分不出來，
    一律當尾碼——那個標籤就不歸戶（寧可漏）。"""
    for rx in _OCR_SFX:
        m = rx.match(tail)
        if m and m.group(1) not in _EQ_STOP:
            return m.group(1)
    return ''


def ocr_scan(text, ix):
    """OCR 的一段原文 → (t, raw, idx, items)：t＝ocr_clean 後的字串；raw＝NFKC 後的原文；idx[k]＝t[k] 在 raw 裡的位置
    （切框與取「原本讀到的字」用）；items＝這段字裡讀到的每一個 KKS 標籤，依出現位置排序：
      {'a' 前綴起點, 'c' 核心起點, 'e' 核心終點, 'end' 這個標籤管到哪裡（下一個標籤的前綴起點或字串結尾）——都是 t 的索引；
       'letter', 'units' [機組…]（機組清單有兩個）, 'cores' [核心…]（'PHC10/20 BT011' 的斜線展開有兩個）, 'nfix' 修了幾個形近字,
       'sfx' 尾碼（_ocr_suffix）, 'label' 正規化後的讀法（'=' ＋ 前綴照圖上寫的 ＋ 核心 ＋ 尾碼；斜線與機組清單保留圖上的寫法）,
       'raw' 這個標籤原本讀到的字（空白收成一格）}
    一個 OCR 框常常蓋住兩三個相鄰的球泡（'C10LAC50 BT047AC10LAC50 BT04Z'），所以**每一次出現各自成一筆**，尾碼只看到下一筆為止。
    步驟：先嚴格搜尋（核心原樣出現；含斜線展開）；嚴格搜尋沒蓋到的剩餘片段再做安全的形近字修復——10 個字元的視窗逐格看，
    字母位／數字位出現另一類的形近字就列出可能，**展開後只落在一個 AMS 核心**才接受（至多修 2 個字）。
    舊版是「嚴格搜尋一個都沒有才修」，合併框裡讀壞的那一半（上例的 'BT04Z'）就永遠修不到。"""
    raw = unicodedata.normalize('NFKC', text or '')
    chars, idx = [], []
    for i, ch in enumerate(raw):
        for c in ch.upper().translate(_OCR_DASH):
            if not c.isspace():
                chars.append(c)
                idx.append(i)
    t = ''.join(chars)
    items = []
    for m in _OCR_CORE.finditer(t):
        pf = _ocr_prefix(t, m.start(1), ix['units'])
        if pf is not None:
            items.append({'a': pf[3], 'c': m.start(1), 'e': m.end(1), 'letter': pf[0], 'units': pf[1], 'cores': [m.group(1)], 'nfix': pf[2]})
    for m in _OCR_SLASH.finditer(t):
        pf = _ocr_prefix(t, m.start(1), ix['units'])
        if pf is not None:
            cores = [m.group(1) + nn + m.group(4) for nn in [m.group(2)] + m.group(3).strip('/').split('/')]
            items.append({'a': pf[3], 'c': m.start(1), 'e': m.end(4), 'letter': pf[0], 'units': pf[1], 'cores': cores, 'nfix': pf[2],
                          'slash': True})
    # 形近字修復：只在嚴格搜尋沒蓋到的片段上做
    pieces, pos = [], 0
    for a, e in sorted((it['a'], it['e']) for it in items):
        if a > pos:
            pieces.append((pos, a))
        pos = max(pos, e)
    if pos < len(t):
        pieces.append((pos, len(t)))

    def fuzzy(seg, si, contiguous):
        """seg＝只含英數字的字串；si[k]＝seg[k] 在 t 的索引 → 這一段修得出來的標籤。"""
        out = []
        last = -1
        for i in range(0, len(seg) - 9):
            if i <= last:
                continue                                              # 與剛接受的那一個重疊
            w = seg[i:i + 10]
            opts = []
            nfix = 0
            for ch, cls in zip(w, _SHAPE):
                if cls == 'L':
                    if ch.isalpha():
                        opts.append(ch)
                    elif ch in TO_LETTER:
                        opts.append(TO_LETTER[ch])
                        nfix += 1
                    else:
                        opts = None
                        break
                else:
                    if ch.isdigit():
                        opts.append(ch)
                    elif ch in TO_DIGIT:
                        opts.append(TO_DIGIT[ch])
                        nfix += 1
                    else:
                        opts = None
                        break
            if not opts or nfix == 0 or nfix > 2 or seg[i + 10:i + 11].isdigit():      # 後面還接著數字＝不是三位數的設備號
                continue
            cands = {''.join(c) for c in itertools.product(*opts)} & ix['cores']
            if len(cands) != 1:
                continue
            # 連續的片段在 t 上看前綴（才看得到前面的標點）；擠掉標點的版本只能在擠過的字串上看
            pf = _ocr_prefix(t, si[i], ix['units']) if contiguous else _ocr_prefix(seg, i, ix['units'])
            if pf is None:
                continue
            a = pf[3] if contiguous else si[pf[3]]
            if a < si[0]:
                continue                                              # 前綴伸進了前一個標籤（不該發生；保守起見不收）
            out.append({'a': a, 'c': si[i], 'e': si[i + 9] + 1, 'letter': pf[0], 'units': pf[1], 'cores': [next(iter(cands))],
                        'nfix': nfix + pf[2]})
            last = i + 9
        return out

    for ps, pe in pieces:
        got = []
        for m in re.finditer(r'[A-Z0-9]{10,}', t[ps:pe]):
            got += fuzzy(m.group(0), list(range(ps + m.start(), ps + m.end())), True)
        if not got:
            si = [k for k in range(ps, pe) if re.match(r'[A-Z0-9]', t[k])]
            if len(si) >= 10 and si[-1] - si[0] + 1 != len(si):          # 中間夾著標點：擠掉再試一次
                got = fuzzy(''.join(t[k] for k in si), si, False)
        items += got
    items.sort(key=lambda it: (it['c'], it['a'], it['e']))
    for k, it in enumerate(items):
        nxt = [o['a'] for o in items[k + 1:] if o['a'] >= it['e']]
        it['end'] = min(nxt) if nxt else len(t)
        sfx = _ocr_suffix(t[it['e']:it['end']])
        if sfx and any(raw[idx[j]] != t[j] for j in range(it['e'], it['e'] + len(sfx))):
            sfx = ''                                                  # 原文是小寫（'…WP006 to …' 的 to）＝鄰字，不是尾碼
        it['sfx'] = sfx
        # 前綴：單一機組印正規化（修好）的寫法（'C1Q' → 'C10'）；機組清單照圖上寫的（'G11/12'）
        pre = (it['letter'] + it['units'][0]) if len(it['units']) == 1 else t[it['a']:it['c']]
        core = t[it['c']:it['e']] if it.get('slash') else it['cores'][0]
        it['label'] = ('=' if it['a'] > 0 and t[it['a'] - 1] == '=' else '') + pre + core + it['sfx']
        e2 = it['e'] + (len(it['sfx']) if it['sfx'] and t.startswith(it['sfx'], it['e']) else 0)
        it['raw'] = re.sub(r'\s+', ' ', raw[idx[it['a']]:idx[e2 - 1] + 1]).strip() if e2 > it['a'] else ''
    return t, raw, idx, items


def ocr_parse_kks(text, ix):
    """OCR 的一段原文 → [(字母, 機組, 核心, 修了幾個字)]（ocr_scan 的精簡版：同一支只留一筆，不含尾碼與位置；
    機組清單與斜線展開各出一筆）。位置、尾碼、標籤文字要用 ocr_scan。"""
    out, got = [], set()
    for it in ocr_scan(text, ix)[3]:
        for u in it['units']:
            for core in it['cores']:
                if (it['letter'], u, core) not in got:
                    got.add((it['letter'], u, core))
                    out.append((it['letter'], u, core, it['nfix']))
    return out


def tag_like(text):
    """OCR 原文「看起來像不像位號」（**與 AMS 有哪些位號無關**；pid_ocr --distill 用它決定哪些字留進對照表）。
    回形狀名或 None：'kks'（完整核心，可帶機組）、'kks_sys'（系統段 C10PAB60／11HAD61／HAD60）、'kks_eq'（設備段 QN001）、
    'ge'（GE 元件名 96FG-1）、'isa'（1-PIT-CW014-1）、'kks_fuzzy'（差一兩個形近字就是 KKS 核心的字串，留給 pid_index 用 AMS 集合修）。
    系統段與設備段必須留：圖上有一半的閥號是拆成上下兩行寫的，要兩段都在才合得回來。"""
    t = ocr_clean(text)
    if not t:
        return None
    if _OCR_CORE.search(t) or _OCR_SLASH.search(t):
        return 'kks'
    b = t.strip(_STRIP + '-')
    if ISA_RE.match(b):
        return 'isa'
    if GE_RE.search(t):
        return 'ge'
    head = b.split('/')[0]
    if _OCR_SYS.match(head) and re.fullmatch(r'(?:/\d{2}){0,3}', b[len(head):]):
        return 'kks_sys'
    if PDF_KKS_EQ.match(b) and b[:2] not in _EQ_STOP:
        return 'kks_eq'
    sq = re.sub(r'[^A-Z0-9]', '', t)
    for i in range(0, len(sq) - 9):
        nfix = 0
        for ch, cls in zip(sq[i:i + 10], _SHAPE):
            if cls == 'L':
                if not ch.isalpha():
                    if ch not in TO_LETTER:
                        break
                    nfix += 1
            elif not ch.isdigit():
                if ch not in TO_DIGIT:
                    break
                nfix += 1
        else:
            if 0 < nfix <= 2:
                return 'kks_fuzzy'
    return None


def ocr_token_box(tok):
    """OCR 對照表的一筆 [text, cx, cy, w, h, score] → (x0, y0, x1, y1) 比例。"""
    _t, cx, cy, w, h = tok[:5]
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def ocr_table_tokens(words):
    """OCR 的字框（match_ocr_tokens 內部格式：[x0, y0, x1, y1, 原文, 方向, …]，單位 pt）→ 位在「清單欄」裡的框的索引集合。
    清單欄＝≥ 5 個像位號的橫書框由上到下緊鄰（中心間距 0.3~2.6 個框高）、而且左緣或中心對齊（差 ≤ 0.8 個框高）——
    與文字層的表格列規則（page_candidates）同一個門檻，只是 OCR 的框沒有「行首邊」可用，改看左緣／中心。
    為什麼需要（2026-10-08 第一次真的跑 OCR 才發現）：TDM01-D1205（給水泵組，整份沒有文字層）的 p7／p8 整頁是
    「INSTRUMENT／JUNCTION BOX／EQUIPMENT LIST」，九欄 C10／C20／C30 x LAC50／60／70 各五十幾列位號。不標出來的話，
    LAC60／LAC70 的位號會被當成「畫在這個位置的符號」發布，其實那只是清單的一格（符號只畫了 LAC50 那一台，在 p4／p5）。
    只數**完整的位號**（完整 KKS、差一兩個形近字的 KKS、GE 元件名、ISA 名）：拆成上下兩行寫的標籤（'C10MAJ61'／'WP007'）
    在圖上本來就一疊一疊的，把系統段、設備段也算進來會把真的符號誤標成清單（TCM01-D1701 p2 實測誤標 1 處）。
    直書的清單不處理（沒遇過）；符號真的五個以上等距疊成一欄時會被誤標成清單——與文字層那條規則同樣的取捨。"""
    cand = [(i, w) for i, w in enumerate(words) if w[5] == 0 and (w[2] - w[0]) > 0 and (w[3] - w[1]) > 0
            and tag_like(w[4]) in ('kks', 'kks_fuzzy', 'ge', 'isa')]
    cand.sort(key=lambda iw: ((iw[1][1] + iw[1][3]) / 2.0, iw[1][0], iw[0]))
    out = set()
    for align in (lambda w: w[0], lambda w: (w[0] + w[2]) / 2.0):          # 左緣對齊／中心對齊各找一次
        chains = []                                                         # 每條鏈＝[(索引, 字框), …]，由上到下
        for i, w in cand:
            h = w[3] - w[1]
            cy = (w[1] + w[3]) / 2.0
            best = None
            for ch in chains:
                lw = ch[-1][1]
                lh = lw[3] - lw[1]
                dy = cy - (lw[1] + lw[3]) / 2.0
                da = abs(align(w) - align(lw))
                if 0.3 * min(h, lh) <= dy <= 2.6 * max(h, lh) and da <= 0.8 * min(h, lh) and (best is None or da < best[0]):
                    best = (da, ch)
            if best:
                best[1].append((i, w))
            else:
                chains.append([(i, w)])
        for ch in chains:
            if len(ch) < 5:
                continue
            out.update(i for i, _w in ch)
            # 同一欄裡被讀壞的鄰格打斷而落單的框也算（欄的範圍內、對齊同一條線）：否則清單裡剛好落單的那一格會被當成符號
            col = statistics.median(align(w) for _i, w in ch)
            pad = 2.6 * statistics.median(w[3] - w[1] for _i, w in ch)
            top, bot = ch[0][1][1] - pad, ch[-1][1][3] + pad
            for i, w in cand:
                if i not in out and top <= (w[1] + w[3]) / 2.0 <= bot and abs(align(w) - col) <= 0.8 * (w[3] - w[1]):
                    out.add(i)
    return out


_OCR_SYS_SLASH = re.compile(r'^((?:[A-Z][0-9XY]{2}|[0-9XY]{2})?)([A-Z]{3})(\d{2})((?:/\d{2}){1,3})$')      # 'C10PHC10/20'


def _split_box(w, n_raw, i0, i1):
    """OCR 框 w＝[x0, y0, x1, y1, 原文, 方向, …] 依原文第 i0~i1 個字元（共 n_raw 個）切出一段。橫書沿 x、直書（由下往上讀）沿 y。"""
    f0, f1 = i0 / float(n_raw), i1 / float(n_raw)
    if w[5] == 0:
        return [w[0] + f0 * (w[2] - w[0]), w[1], w[0] + f1 * (w[2] - w[0]), w[3]]
    return [w[0], w[3] - f1 * (w[3] - w[1]), w[2], w[3] - f0 * (w[3] - w[1])]


def match_ocr_tokens(tokens, ix, w_pt, h_pt, ctx=None, min_score=OCR_MIN_SCORE, near_score=OCR_NEAR_SCORE):
    """OCR 讀到的字（**原文**＋轉正後比例的框）→ 命中，欄位與 match_page 相同再加 conf（辨識分數）、fix（修了幾個形近字）、
    raw（form='ocr-fix' 才有：這個標籤原本讀到的字）、why（這筆命中用到的特殊規則，追查用）。
    note：0＝符號標籤、1＝這個框在清單欄裡（ocr_table_tokens；整頁儀器清單的一格，不是符號位置）。
      tokens  [[text, cx, cy, w, h, score], …]：pid_ocr_map.json 的 pages[].tokens（中心＋尺寸，0~1 比例，轉正後）
      w_pt, h_pt  轉正後的圖紙尺寸（拆寫合併的距離要用 pt 算，比例在長寬不等的圖上不能直接比）
    回傳的 box 是 **轉正後的比例** (x0, y0, x1, y1)。form：'ocr' 原樣讀到／'ocr-fix' 經形近字修復／'ocr-stacked'、'ocr-inline' 兩個框合併。
    **label 一律是「這一筆自己的」正規化讀法**（前綴照圖上寫的＋核心＋尾碼；兩個框合併的以一個空白相接），不再是整個 OCR 框的原文：
    原文常帶著併進同一框的功能碼、鄰字、管徑、括號（'…BT047AC10LAC50 BT04Z'、'CC10LAC50…'、'…BT013DN25'、'…QN001B2)'），
    照抄會讓卡片把雜訊說成「圖上標示」。一個框裡有幾個標籤就切成幾筆，框沿閱讀方向依字元位置等比例切開。
    規則：分數 < min_score 的字不用；KKS 用搜尋（ocr_scan）＋安全的形近字修復；尾碼必須與 AMS 位號自己的尾碼相同（_attribute_kks）；
    GE 元件名與 ISA 名只接受原樣；機組前綴讀不出來的不收；**沒寫機組的讀數只在「不寫機組的圖」（SCOPE_LETTER）上才收**——
    OCR 框切到邊時前綴會整個不見，在寫機組的圖上把它當成「不分機組」就是把典型圖說成各機組共用（drops['ocr_nounit']）。
    **差一點點的疊寫標籤**（裁決 A7）：上下兩行拆寫的閥號，設備段的分數在 near_score~min_score 之間時，只有在
    正上方的系統段 ≥ min_score、那個系統段沒有別的設備段可接、合起來是 AMS 核心、而且這一頁沒有別的讀數是同一個核心，
    才接受（why 含 'near'；pid_index 還會再擋掉文字層已經有的）。實例：BFD01-D0002 p3 的 11HAD10 QN003（0.734）／QN004（0.749）。
    回傳前不做「文字層為準」的去重——那是 pid_index 的事（它才知道文字層在哪裡有位號）。"""
    ctx = ctx or make_ctx()
    hits = []
    seen = set()
    rej = ctx.get('rej')
    words = []
    for tk in tokens:
        text, cx, cy, w, h = tk[0], tk[1], tk[2], tk[3], tk[4]
        x0, y0, x1, y1 = (cx - w / 2.0) * w_pt, (cy - h / 2.0) * h_pt, (cx + w / 2.0) * w_pt, (cy + h / 2.0) * h_pt
        d = 0 if (x1 - x0) >= (y1 - y0) else 3                        # 直的框＝由下往上讀的直書
        words.append([x0, y0, x1, y1, text, d, 1, float(tk[5]) if len(tk) > 5 else 0.0])

    table = ocr_table_tokens(words)

    def frac(box):
        return (box[0] / w_pt, box[1] / h_pt, box[2] / w_pt, box[3] / h_pt)

    def attribute(letter, unit, core, sfx, form, box, label):
        """_attribute_kks＋沒寫機組的把關；尾碼不合的補上框與標籤記進 rej。"""
        if not letter and not unit and not ctx.get('scope'):
            if core in ix['kks']:
                ctx['drops']['ocr_nounit'] += 1
            return []
        n0 = len(rej) if rej is not None else 0
        found = _attribute_kks(ix, letter, unit, core, ctx, sfx)
        if rej is not None:
            for j in range(n0, len(rej)):
                rej[j] = {'tag': rej[j][0], 'why': rej[j][1], 'box': frac(box), 'label': label, 'form': form}
        return found

    def emit(found, form, box, label, conf, fix, note=0, raw=None, why=()):
        for tag, rel, drawn, sfx in found:
            if rel == 'train' and note:
                continue                                              # 典型畫法只認符號（理由見 match_page）
            key = (tag, round(box[0]), round(box[1]), rel)
            if key in seen:
                continue
            seen.add(key)
            h = {'tag': tag, 'rel': rel, 'drawn_as': drawn, 'form': form, 'label': re.sub(r':(?=[\\/])', ': ', label),
                 'box': frac(box), 'note': note, 'nk': 'table' if note else '', 'sfx': sfx, 'conf': round(conf, 3), 'fix': fix,
                 'why': list(why)}
            if raw is not None:
                h['raw'] = raw
            hits.append(h)

    frag_s, frag_e, frag_low = [], [], []
    page_cores = set()
    for i, w in enumerate(words):
        b = ocr_clean(w[4]).strip(_STRIP + '-')
        if w[7] < min_score:
            if w[7] >= near_score and PDF_KKS_EQ.match(b) and b[:2] not in _EQ_STOP:
                frag_low.append(i)
            continue
        t, raw_n, idx, items = ocr_scan(w[4], ix)
        note = 1 if i in table else 0
        # 一個框裡有幾個標籤就切幾段；看起來不是單獨一行字的框（太方：可能是上下兩行被框在一起）不切，各筆都用整個框
        long_, short_ = max(w[2] - w[0], w[3] - w[1]), min(w[2] - w[0], w[3] - w[1])
        # （2026-10-10 對照表裡 89 個多標籤的框，長邊÷(短邊×字數) 全在 0.30~0.86；上下兩行被框在一起的話約 0.15）
        can_split = len(items) > 1 and len(raw_n) > 0 and long_ >= 0.2 * len(t) * short_
        for k, it in enumerate(items):
            why = []
            box = w[:4]
            if can_split:
                i0 = 0 if k == 0 else idx[it['a']]
                i1 = len(raw_n) if k == len(items) - 1 else idx[items[k + 1]['a']]
                if i1 > i0:
                    box = _split_box(w, len(raw_n), i0, i1)
                    why.append('split')
            elif len(items) > 1:
                why.append('nosplit')
            if len(it['units']) > 1:
                why.append('unitlist')
            form = 'ocr-fix' if it['nfix'] else 'ocr'
            for unit in it['units']:
                for core in it['cores']:
                    page_cores.add(core)
                    emit(attribute(it['letter'], unit, core, it['sfx'], form, box, it['label']), form, box, it['label'], w[7], it['nfix'],
                         note, it['raw'] if it['nfix'] else None, why)
        if items:
            continue
        got = False
        for m in GE_RE.finditer(t):
            gcore = m.group(1)
            if gcore in ix['ge']:
                pm = re.search(r'([GS]\d\d)-$', t[:m.start(1)])
                emit(_attribute_ge(ix, gcore, pm.group(1) if pm else '', ctx), 'ocr', w[:4], ((pm.group(1) + '-') if pm else '') + gcore,
                     w[7], 0, note)
                got = True
        if got:
            continue
        isa = _attribute_isa(ix, b)
        if isa:
            emit(isa, 'ocr', w[:4], b, w[7], 0, note)
            continue
        if _OCR_SYS.match(b) or _OCR_SYS_SLASH.match(b):              # 'TP1-1-6' 這種帶連字號的不是設備段，所以不去掉中間的符號
            frag_s.append(i)
        elif PDF_KKS_EQ.match(b) and b[:2] not in _EQ_STOP:
            frag_e.append(i)

    # 兩個框的拆寫合併（偵測框比字大一圈，所以用「間隙」而不是行距來判斷；門檻取自 ocr 探勘的 _join_two_line）
    def nearest(s, pool):
        sw = words[s]
        ws_, hs_ = sw[2] - sw[0], sw[3] - sw[1]
        cxs, cys = (sw[0] + sw[2]) / 2.0, (sw[1] + sw[3]) / 2.0
        best = None
        for e in pool:
            ew = words[e]
            we_, he_ = ew[2] - ew[0], ew[3] - ew[1]
            cxe, cye = (ew[0] + ew[2]) / 2.0, (ew[1] + ew[3]) / 2.0
            d = None
            form = None
            if sw[5] == 0 and ew[5] == 0:
                gap = ew[1] - sw[3]                                   # 設備段在正下方
                if abs(cxs - cxe) <= 0.6 * max(ws_, we_) and -0.3 * hs_ <= gap <= 1.2 * hs_:
                    d, form = abs(cxs - cxe) + abs(gap), 'ocr-stacked'
                gap = ew[0] - sw[2]                                   # 同一行、在右邊
                if abs(cys - cye) <= 0.5 * hs_ and -0.5 * hs_ <= gap <= 2.5 * hs_ and (d is None or abs(gap) < d):
                    d, form = abs(gap), 'ocr-inline'
            elif sw[5] == 3 and ew[5] == 3:
                gap = ew[0] - sw[2]                                   # 直書：下一行在右邊
                if abs(cys - cye) <= 0.6 * max(hs_, he_) and -0.3 * ws_ <= gap <= 1.2 * ws_:
                    d, form = abs(cys - cye) + abs(gap), 'ocr-stacked'
                gap = sw[1] - ew[3]                                   # 直書同一行：往上接
                if abs(cxs - cxe) <= 0.5 * ws_ and -0.5 * ws_ <= gap <= 2.5 * ws_ and (d is None or abs(gap) < d):
                    d, form = abs(gap), 'ocr-inline'
            if d is not None and (best is None or d < best[0]):
                best = (d, e, form)
        return best

    def joined(s, e):
        """系統段＋設備段 → [(字母, 機組, 核心, 尾碼)]、標籤文字、合併框。'C10PHC10/20'＋'BT010' 展開成兩支（與單一框的寫法一致）。"""
        sw, ew = words[s], words[e]
        sys_t = ocr_clean(sw[4]).strip(_STRIP + '-')
        eq_t = ocr_clean(ew[4]).strip(_STRIP + '-')
        ms = _OCR_SYS_SLASH.match(sys_t)
        variants = [ms.group(1) + ms.group(2) + nn for nn in [ms.group(3)] + ms.group(4).strip('/').split('/')] if ms else [sys_t]
        ks = []
        for v in variants:
            k = parse_pdf_label(v + eq_t)
            if k:
                ks.append(k[:4])
        box = [min(sw[0], ew[0]), min(sw[1], ew[1]), max(sw[2], ew[2]), max(sw[3], ew[3])]
        return ks, '%s %s' % (sys_t, eq_t), box, bool(ms)

    near = []
    for s in frag_s:
        best = nearest(s, frag_e)
        if not best:
            low = nearest(s, frag_low)
            if low and low[2] == 'ocr-stacked':
                near.append((s, low[1]))
            continue
        e = best[1]
        ks, label, box, slash = joined(s, e)
        note = 1 if (s in table or e in table) else 0
        for letter, unit, core, sfx in ks:
            page_cores.add(core)
            emit(attribute(letter, unit, core, sfx, best[2], box, label), best[2], box, label, min(words[s][7], words[e][7]), 0, note,
                 None, ['slashjoin'] if slash else [])
    # 差一點點的疊寫標籤（A7）：合起來的核心在這一頁必須是唯一的讀數
    near_cores = Counter()
    cand = []
    for s, e in near:
        ks, label, box, slash = joined(s, e)
        if len(ks) != 1 or slash:
            continue
        cand.append((s, e, ks[0], label, box))
        near_cores[ks[0][2]] += 1
    for s, e, (letter, unit, core, sfx), label, box in cand:
        if core not in ix['cores'] or core in page_cores or near_cores[core] != 1:
            continue
        emit(attribute(letter, unit, core, sfx, 'ocr-stacked', box, label), 'ocr-stacked', box, label, min(words[s][7], words[e][7]), 0,
             1 if (s in table or e in table) else 0, None, ['near'])
    return hits


# ================================================================ 文件集：家族、最新版、圖紙
def _file_summary(rec):
    """快取記錄 → 認親用的摘要：每頁字數、全文指紋、KKS 標籤詞彙。"""
    nw = [len(p['words']) for p in rec['pg']]
    h = hashlib.md5()
    toks = set()
    for p in rec['pg']:
        for w in p['words']:
            h.update(w[4].encode('utf-8', 'ignore'))
            tok = clean_token(w[4])
            if tok and (parse_pdf_kks(tok) or PDF_KKS_SYS.match(tok) or PDF_KKS_EQ.match(tok)):
                toks.add(tok)
    return {'pages': rec['pages'], 'nw': nw, 'words': sum(nw), 'md5': h.hexdigest(), 'toks': frozenset(toks), 'err': rec.get('err'),
            'truncated': rec['pages'] > len(rec['pg'])}


def build_corpus(root=None, cache_dir=None, jobs=0, log=None):
    """文件庫 → 現行 P&ID 文件集。步驟：走訪 → 檔名分類 → 補文字層快取 → 圖號家族 → 每個家族挑最新版當代表。
    回 dict：
      root       文件庫根目錄（絕對路徑；只在記憶體裡用，不可寫進輸出）
      families   每張圖一筆（含二、三號機組專屬圖）：{family, doc, rev, rel, size, mtime, title, sys, block, extra, flags,
                 pages, words, members:[{rel, role, rev}]}；rel＝代表檔（最新版）的相對路徑
      drawings   families 裡 block 不是 '2'／'3' 的＝一號機組的 P&ID 文件集（定位只用這些檔）
      stats      走訪與歸戶的統計（pdf_walked、pid_files、families、…；決定性，可直接寫進輸出）
      text_extracted／text_errors  這次重抽了幾份文字層、哪些檔抽取失敗（只供列印）
    log＝可呼叫物件（印進度）或 None。呼叫端若給 jobs > 1，Windows 下必須在 __main__ 保護內。"""
    root = os.path.normpath(root or paths.LIBRARY_ROOT)
    cache_dir = cache_dir or paths.PID_TEXT_CACHE
    say = log or (lambda *_a: None)
    lib = walk_pdfs(root)
    F = {}
    by_dn = defaultdict(list)
    for rel, size, mtime in lib:
        base = rel.rsplit('/', 1)[-1]
        dn = docno(base)
        o = {'rel': rel, 'size': size, 'mtime': mtime, 'dn': dn, 'kind': kind_of(rel), 'flags': copy_flags(rel), 'title': title_of(base)}
        F[rel] = o
        if dn:
            by_dn[dn[0]].append(o)
    # 沒有標題的版次跟同編號的兄弟檔同類（只在兄弟裡有人被檔名規則認成 P&ID 時才需要算）
    n_inherit = 0
    for no, lst in by_dn.items():
        kinds = Counter(o['kind'] for o in lst if o['kind'] != 'other')
        if 'pid' not in kinds:
            continue
        top = max(kinds.values())
        first = next(o['kind'] for o in lst if o['kind'] != 'other' and kinds[o['kind']] == top)   # 同數時取路徑排序最前的（決定性）
        if first == 'pid':
            for o in lst:
                if o['kind'] == 'other':
                    o['kind'] = 'pid'
                    o['inherited'] = True
                    n_inherit += 1
    n_extra = 0
    for o in F.values():
        if o['dn'] and re.sub(r'^HT\d-', '', o['dn'][0]) in EXTRA_FAMILIES and o['kind'] != 'pid':
            o['kind'] = 'pid'
            o['extra'] = True
            n_extra += 1
    pid_all = [o for o in F.values() if o['kind'] == 'pid']
    pid = [o for o in pid_all if 'collection' not in o['flags']]
    # 沒有編號又放在根目錄的檔、以及「初稿」＝個人彙編，不是送審圖
    loose = [o for o in pid if not o['dn'] and ('root' in o['flags'] or '初稿' in o['rel'])]
    loose_set = {o['rel'] for o in loose}
    pid = sorted((o for o in pid if o['rel'] not in loose_set), key=lambda o: o['rel'])
    todo = []
    for o in pid:                                                    # 快取每份只解一次；缺的、過期的才交給 ensure_text
        rec = _read_cache(text_cache_path(cache_dir, o['rel']), o['size'], o['mtime'])
        if rec is None:
            todo.append(o)
        else:
            o.update(_file_summary(rec))
    n_new, errs = ensure_text(root, [(o['rel'], o['size'], o['mtime']) for o in todo], cache_dir, jobs, log) if todo else (0, {})
    for o in todo:
        o.update(_file_summary(load_text(root, o['rel'], o['size'], o['mtime'], cache_dir)))
    # ---- 家族：HT 編號
    fam = {}
    groups = defaultdict(list)
    for o in pid:
        if o['dn']:
            groups[(o['dn'][2], o['dn'][3], o['dn'][4], o['dn'][5])].append(o)
    n_merge = n_split = 0
    for key in sorted(groups):
        files = groups[key]
        byht = defaultdict(list)
        for o in files:
            byht[o['dn'][1]].append(o)
        if len(byht) == 1:
            fam['HT%s-%s-%s-%s%s' % (next(iter(byht)), key[0], key[1], key[2], key[3])] = files
            continue
        # 幾個 HT 首碼共用 (系統, 字母, 流水號)：是同一張圖重新送審（HT1 字母版次 → HT0），還是各機組各一張？
        digs = sorted(byht)
        tt = {d: [title_tokens(o['title']) for o in byht[d] if title_tokens(o['title'])] for d in digs}
        gs = []
        for d in digs:
            placed = False
            for g in gs:
                ref = [t for x in sorted(g) for t in tt[x]]
                mine = tt[d]
                sim = max([jaccard(a, b) for a in ref for b in mine] or [1.0 if (not ref or not mine) else 0.0])
                unit_marked = any(re.search(r'UNIT[\s\-]*\d', o['title'], re.I) for x in sorted(g) + [d] for o in byht[x])
                if sim >= 0.5 and not unit_marked:
                    g.add(d)
                    placed = True
                    break
            if not placed:
                gs.append({d})
        for g in gs:
            lead = '0' if '0' in g else sorted(g)[0]
            fam['HT%s-%s-%s-%s%s' % (lead, key[0], key[1], key[2], key[3])] = [o for d in sorted(g) for o in byht[d]]
            if len(g) > 1:
                n_merge += 1
        if len(gs) > 1:
            n_split += 1
    # ---- 沒有 HT 編號的檔：靠內容認親（文字完全相同 → 標籤詞彙相近 → 沒有文字層的才看標題，而且要詞集合完全相同）
    ht_fams = sorted(fam.items())
    md5_to_fam = {}
    for k, files in ht_fams:
        for o in files:
            if o['words'] >= 50:
                md5_to_fam.setdefault(o['md5'], k)
    link = Counter()
    unl = []
    for o in pid:
        if o['dn']:
            continue
        k = md5_to_fam.get(o['md5']) if o['words'] >= 50 else None
        how = 'identical_text'
        mine = o['toks']
        if not k and len(mine) >= 20:
            bestc = (0, None)
            for fk, files in ht_fams:
                for x in files:
                    if len(x['toks']) >= 20:
                        j = jaccard(mine, x['toks'])
                        if j > bestc[0]:
                            bestc = (j, fk)
            if bestc[0] >= 0.6:
                k, how = bestc[1], 'label_vocabulary'
        if not k and len(mine) < 20:
            tt = title_key(o['title'])
            if tt:
                same = [fk for fk, files in ht_fams if any(title_key(x['title']) == tt for x in files)]
                if len(same) == 1:
                    k, how = same[0], 'same_title'
        if k:
            o['linked'] = how
            fam[k].append(o)
            link[how] += 1
        else:
            unl.append(o)
    for o in unl:
        v = vendor_name(o['rel'].rsplit('/', 1)[-1])
        t = ' '.join(sorted(title_tokens(v[1] if v else o['title']))) or o['title']
        fam.setdefault('X:' + t[:80], []).append(o)

    # ---- 每個家族的代表檔（最新版）
    # 順序（2026-10-10 裁決 A8）：有 HT 編號 > HT0 > HT1 > 其他 HT 首碼 > **版次高**（數字 > 字母 > 無；廠商檔名認 _revX）>
    # 非副本夾 > 非 _舊版 > 檔名不是「(2)」重複檔 > 修改時間新 > 路徑。**版次排在資料夾旗標前面**：舊版把「非副本夾、非 _舊版」
    # 排在版次前面，新版次只要剛好只存在副本夾／設備 dossier 夾裡，就會輸給放在正式資料夾的舊版次，而且那個新版次還被標成
    # 'older_rev'（合成文件庫實測；真實文件庫目前 0 例）——「舊版次的位置絕不發布」不能靠資料夾擺得剛好來成立。
    # HT 首碼仍排在版次前面：HT1 是舊編號（多半是字母版次），HT2／HT3 是二、三號機組的檔，不可因為版次字母大就選到它們。
    def file_rev(o):
        return o['dn'][6] if o['dn'] else (vendor_name(o['rel'].rsplit('/', 1)[-1]) or ('', '', ''))[2]

    def sort_key(o):
        f = set(o['flags'])
        is_copy = bool(f & {'copy_path', 'collection', 'dossier'}) and 'old' not in f
        rr = rev_rank(file_rev(o))
        ht = 3 if not o['dn'] else (0 if o['dn'][1] == '0' else (1 if o['dn'][1] == '1' else 2))
        return (ht, -rr[0], -rr[1], -rr[2], tuple(-ord(c) for c in rr[3]), 1 if is_copy else 0, 1 if 'old' in f else 0,
                1 if f & {'dupname', 'root'} else 0, -o['mtime'], o['rel'])

    families = []
    roles = Counter()
    newer = []                                                       # 版次比代表檔還新的成員（不該有；有就大聲印出來）
    for k in sorted(fam):
        files = sorted(fam[k], key=sort_key)
        rep = files[0]
        members = []
        for o in files[1:]:
            if rev_rank(file_rev(o)) > rev_rank(file_rev(rep)) and bool(o['dn']) == bool(rep['dn']):
                newer.append((k, rep['rel'].rsplit('/', 1)[-1], o['rel'].rsplit('/', 1)[-1]))
        for o in files[1:]:
            f = set(o['flags'])
            if o.get('linked'):
                role = 'vendor_named_copy'
            elif not o['dn']:
                role = 'same_title_copy'
            elif o['dn'][1] != (rep['dn'][1] if rep['dn'] else None):
                role = 'old_numbering'
            elif rep['dn'] and o['dn'][6] == rep['dn'][6]:
                role = 'same_rev_copy'
            else:
                role = 'older_rev'
            roles[role] += 1
            members.append({'rel': o['rel'], 'role': role + ('+copy_folder' if (f & {'copy_path', 'collection', 'dossier'} and 'old' not in f) else ''),
                            'rev': o['dn'][6] if o['dn'] else (vendor_name(o['rel'].rsplit('/', 1)[-1]) or ('', '', ''))[2],
                            'size': o['size'], 'mtime': o['mtime']})
        dn = rep['dn']
        title = rep['title'] or next((o['title'] for o in files if o['title']), '')
        um = re.search(r'UNIT[\s\-]*(\d)', title, re.I)
        block = (dn[1] if dn and dn[1] in '123' else None) or (um.group(1) if um else None)
        doc, rev, _stem, disp = ident(rep['rel'])
        families.append({'family': k, 'doc': doc, 'rev': rev, 'rel': rep['rel'], 'size': rep['size'], 'mtime': rep['mtime'],
                         'title': disp, 'sys': dn[3] if dn else None, 'block': block, 'flags': rep['flags'],
                         'extra': bool(dn and re.sub(r'^HT\d-', '', k) in EXTRA_FAMILIES),
                         'pages': rep['pages'], 'words': rep['words'], 'truncated': rep['truncated'], 'err': rep['err'], 'members': members})
    drawings = [f for f in families if f['block'] not in ('2', '3')]
    # 讀不了的 P&ID 檔（壞檔、空檔、有密碼、零頁）：從快取記錄數，所以每次執行都一樣（舊版只數「這次重抽時失敗的」，第二次跑就變 0）
    errs = {o['rel']: o['err'] for o in pid if o.get('err')}
    stats = {'pdf_walked': len(lib), 'pid_files': len(pid), 'pid_files_collection': len(pid_all) - len(pid) - len(loose),
             'pid_files_loose': len(loose), 'kind_inherited': n_inherit, 'extra_files': n_extra,
             'families': len(families), 'families_ht': sum(1 for f in families if f['family'].startswith('HT')),
             'families_unnumbered': sum(1 for f in families if not f['family'].startswith('HT')),
             'ht_merged': n_merge, 'ht_split': n_split, 'linked': dict(sorted(link.items())), 'member_roles': dict(sorted(roles.items())),
             'members': sum(len(f['members']) for f in families),
             'block23': sum(1 for f in families if f['block'] in ('2', '3')),
             'text_errors': len(errs), 'truncated': sum(1 for f in drawings if f['truncated']),
             'unreadable_representative': sum(1 for f in drawings if f['err'] and not f['pages']),
             'newer_rev_not_representative': len(newer)}
    say('文件庫 %d 個 PDF → P&ID 類 %d 份（另：彙編夾 %d、根目錄彙編／初稿 %d 不收）→ %d 張圖（HT 編號 %d、廠商檔名 %d）；'
        '二、三號機組專屬 %d 張不收 → 文件集 %d 張圖' % (
            len(lib), len(pid), stats['pid_files_collection'], len(loose), len(families), stats['families_ht'],
            stats['families_unnumbered'], stats['block23'], len(drawings)))
    for k, a_, b_ in newer[:10]:
        say('!! %s：成員 %s 的版次比代表檔 %s 還新（HT 首碼不同才會這樣）——要人工確認哪一份才是現行版' % (k, b_, a_))
    for f in drawings:
        if f['err'] and not f['pages']:
            say('!! %s 的最新版讀不了（%s）：%s——這張圖這次沒有任何位置；舊版次不會頂上來' % (f['family'], f['err'], f['rel'].rsplit('/', 1)[-1]))
    # text_extracted（這次重抽了幾份）每次執行不同，所以不放進 stats（stats 會原樣寫進 pid.json，必須是決定性的）
    return {'root': root, 'cache_dir': cache_dir, 'families': families, 'drawings': drawings, 'stats': stats, 'text_errors': errs,
            'text_extracted': n_new}


def drawing_pages(corpus, fam):
    """文件集裡一張圖（代表檔）的各頁（文字層快取記錄的 pg 清單；最多 MAX_TEXT_PAGES 頁）。"""
    rec = load_text(corpus['root'], fam['rel'], fam['size'], fam['mtime'], corpus['cache_dir'])
    return rec['pg']
