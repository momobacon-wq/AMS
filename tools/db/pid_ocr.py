# -*- coding: utf-8 -*-
r"""tools/db/pid_ocr.py — P&ID 圖紙的離線 OCR：把「畫成線條字／掃描圖、不在 PDF 文字層裡」的位號讀出來，
蒸餾成 tools/db/pid_ocr_map.json（要 commit；tools/db/pid_index.py 只讀這張表，重建流程不依賴 OCR）。

**為什麼需要**：查詢卡的「P&ID 圖面位置」先用 PDF 文字層定位（pid_index.py），但有一批圖的位號根本不是文字——
EKI 的 SCR 圖（HT0-1-KND01-D0027）儀表球泡是 CAD 線條字、TDM01／TCM01 的廠商圖整張沒有文字層、少數是掃描圖。
使用者自己舉的例子 G12HSD10QN101 就只在 D0027 第 4 版 p2 的線條字球泡「=G11HSD10QN101」裡。
這支工具與 hmi_runtime_map.py 同一個定位：離線、慢（每頁數秒到十幾秒）、有快取、輸出一張進 repo 的對照表；
要重跑才需要 `py -m pip install rapidocr-onnxruntime`（實測版本 1.2.3＝PP-OCRv3，純 CPU）。

== 流程 ==
  1. 圖紙清單＝pid_index 的 OCR 工作清單（在行程內直接呼叫 pid_index.build＋worklist，約 7 秒；或 --worklist FILE）。
     --scope need（預設）＝清單裡 need 的頁：sparse（沒有可用文字層）OR referenced（這份圖已有位號被文字層定位到）
     OR expected（這頁畫了某個 KKS 系統、而 AMS 在那個系統還有位號沒著落——D0027-4 p2 就是靠這條進來的）；
     --scope all＝文件集裡每一張圖紙。封面不在清單裡。
  2. 每頁（一個工作行程做完一頁就自己寫一個快取檔，父行程被砍掉也不會丟已完成的頁）：
     a. 轉正角 R：清單的 R（文字層 ≥ 400 字定出來的）直接用；沒有（null）就做 **OCR 定向投票**（見下）。
     b. 以 pid_lib.render_upright(page, R, zoom) 渲染轉正後的整頁 → 縮小到「偵測倍率」→ 1536 px 分塊偵測文字框 →
        回到原渲染裁出每個框 → 直的框轉 90 度 → 0／180 分類器 → 辨識。
     c. 框的四個角除以影像寬高＝轉正後整張圖的 0~1 比例（與 pid.json、pid_shots 同一個座標系）。
  3. --distill：把快取裡「像位號」的字（pid_lib.tag_like；**不**先對 AMS）與圖框邊條的 1~2 字元標籤寫成對照表。

== 配方 r1b（＝ocr 探勘的 r1＋兩處為了速度的改動；改任何一個參數都會換快取鍵＝全部重跑，先在真值頁上驗過再改）==
  真值頁＝HT0-1-KND01-D0027-4 p2 的人工真值（線條字位號 67 處／51 支）。同一把尺（探勘的 d1_p2score）量到的：
      探勘 r1                      原樣 63、含形近字修復 66／67，51 支裡找到 50 支，KKS 讀數 136 個對 135 個
      本工具照 r1 跑（開 arena）    63／66／50——590 個框與探勘逐一相同（arena 不影響結果）
      r1 ＋ 辨識批次 1              62／65／50
      r1 ＋ 等分分塊                64／66／51
      **r1b（等分分塊＋批次 1）     64／66／51，135／136**；正式比對器（pid_lib.ocr_parse_kks）讀到 66／67、機組前綴 66 處全對
  差一處都在探勘量到的「分塊大小 ±1 處」雜訊之內，不代表哪一個比較準；選 r1b 是因為它在多行程下快一倍以上（見「速度」）。
  * **等分分塊（tiling='even'）**：探勘固定切 1536x1536、最後一塊貼齊邊緣，常與前一塊幾乎整塊重疊。改成塊數不變、
    每一軸把起點等分、邊長縮到剛好蓋滿而重疊仍 ≥ 256 px（32 的倍數）：A1 圖 20 塊由 1536x1536 變 1408x1248，
    送進偵測器的像素少 26 %（A3 大小的頁少 31~41 %）。'probe' 仍保留，可重現探勘的結果。
  * **辨識批次 1（rec_batch）**：RapidOCR 預設一次送 6 個框，同批補白到最寬的那個，所以批次大小會讓極少數框讀法不同
    （真值頁 590 框裡 13 個）。批次 1 在單一行程一樣快，但 12 個行程同跑時辨識只慢 2.5 倍而不是 8 倍（見「速度」）。
  * **偵測倍率是決定性的參數：2.5 px/pt**（位號框在偵測影像裡約 20~27 px 高）。倍率再高，DB 偵測器會把字距很寬的
    CAD 線條字拆成碎片（'=G11HSD11' ＋ '1BP203'）：偵測與辨識同倍率時真值頁得分 z2 66、z2.5 64、z3 61、z4 63／67；
    偵測固定 2.5、辨識從 3 或 4 px/pt 的渲染裁圖則都是 66／67。所以**偵測倍率（det_zoom）與渲染倍率分開**：
    渲染＝偵測 × 1.6（＝4 px/pt），偵測在縮小的副本上做，辨識的裁圖取自原渲染。
  * **渲染長邊上限 12,000 px**：A0（3370 pt）在 4 px/pt 會超過，渲染降到 3.56 px/pt，但**偵測仍維持 2.5**
    （縮小比例由 0.625 改成 2.5／3.56；探勘實測偵測跟著掉到 2.2 時 CTCI 的 A0 圖少讀 9 個位號：451 對 460／489）。
  * **小字圖要放大（自適應倍率）**：有一批圖是 A1 的圖縮印在 A3 大小的頁面上（need 清單 394 頁裡約 180 頁長邊只有
    1,191 pt），字只有一半大，2.5 px/pt 下位號框只有 14 px 高，辨識數明顯偏低（凝結水抽氣圖 TCM01-D1701 p2：
    偵測 2.5／3.75／5.0 px/pt → 位號 124／144／148 個、AMS 核心 12／16／16 個）。做法：第一輪照 2.5 偵測，量
    「長寬比 ≥ 2 的框」短邊的中位數；不到 17 px 就把偵測倍率乘上 21／中位數（上限 5.0 px/pt 與渲染上限）整頁重做，
    否則第一輪的框直接用（正常大小的圖不多花任何時間）。量測依據：14 張探勘頁在 2.5 px/pt 的中位數是 20~27 px
    （大字的掃描圖 41 px），只有那張縮印圖是 14 px。**只往上調、不往下調**（大字的圖降倍率沒有量過）。
  * **0／180 分類器一定要開**：直的框一律逆時針轉 90 度再交給分類器決定要不要倒過來；關掉分類器直書標籤全滅
    （49／67）。直書不需要第二輪：把渲染再轉 90 度重跑一次只多救 1 個球泡、時間 1.9 倍；多尺度偵測聯集完全沒有增益。
  * **長寬比超過 30 的框不辨識**（整行附註；真值頁 781 框裡 11 個，CPU 省 27 %、召回不變）。
  * 其餘是 RapidOCR 預設：thresh 0.3、box_thresh 0.5、unclip 1.6、dilation、limit_side_len 736（min）、text_score 0.5。
    分塊上限 1536 px、重疊 256 px；被分塊邊切到、而鄰塊能完整容納的框丟掉（edge guard），
    跨塊重複的框以「交集佔較小框 ≥ 60 %」去重、留大的。全白的分塊（最小灰階 > 235）不送偵測。
  * **坑：RapidOCR.__call__ 在影像寬／高 > 8 時會跳過偵測、把整張圖當一個框**（config.yaml 的 width_height_ratio: 8），
    長條影像（圖框邊條）整條送進去什麼都讀不到。本工具不呼叫 eng(img)，三個階段（text_detector／text_cls／
    text_recognizer）分開直接呼叫，而且偵測只吃方形分塊，所以不受影響；之後若要單獨 OCR 邊條，務必切成 ≤ 6:1 的小塊。

== 轉正角（**全專案只有一個慣例**：rot＝R＝在頁面自己的 /Rotate 之上再順時針多轉幾度；見 pid_lib 檔頭）==
  * 本工具**從不呼叫 page.remove_rotation()**。ocr 探勘是先 remove_rotation 再量 rot（所以它存的 rot 其實已經是 R），
    若照字面拿「總旋轉 − 原本的 /Rotate」換算，252 頁有旗標的頁會全部多轉 90 度而且不會報錯。這裡直接：
    R 來自清單（＝pid_lib.upright_rotation_text，pid_index 之後也是拿同一個值來核對）或 OCR 投票；
    渲染＝page.get_pixmap(matrix=Matrix(z, z).prerotate(R))（get_pixmap 自己會套 /Rotate）；
    存的 w_pt／h_pt＝pid_lib.upright_size(page, R)。pid_index 會核對這兩樣，不符的頁整筆不用。
  * **OCR 定向投票**（文字層不到 400 字的頁；orient 探勘的 ocr_dirs，對文字層答案驗證 123／123、合成四向 15／15）：
    把頁面**照顯示的樣子**（只套 /Rotate）渲染成長邊 1,800~4,200 px（每 mm 4.5 px），整張偵測一次，取最長的 60 個
    長條框，每個框朝兩個可能的閱讀方向各辨識一次，辨識分數高出 0.08 以上的那個方向得到「字數」票；
    再用與文字層同一條規則（pid_lib.decide_R：字數最多的方向是水平；大圖若因此直立，改看兩個橫式候選）定 R。
    票數不到 12 個字就退回薄文字層的猜測（text-thin），再不行就 0（default）。薄文字層本身不可信：
    三張 Servovalve 圖只有一行直書邊註，文字層會指向 90 度，OCR 才對。

== 速度（2026-10-08 在這台 12 核機器上量的；瓶頸是記憶體頻寬，不是核心數）==
  * **一定要開 onnxruntime 的 CPU memory arena**：RapidOCR 的包裝把它關掉，每次推論都重新向系統要記憶體。
    真值頁單一行程單執行緒：關 arena 偵測 6.1 秒＋辨識 14.8 秒；開 arena 5.1＋4.8 秒。結果逐框相同。make_engine 自己重建三個 session。
  * **多行程幾乎不會線性變快**：純推論（session.run）的時間，1 個行程偵測 4.1 秒／辨識 5.3 秒；6 個行程同跑 13.3／20.6 秒；
    12 個行程 28.4／41.7 秒——也就是整機吞吐量只有單行程的 1.7 倍左右，核心再多也一樣（同一台機器跑純 Python 迴圈或小矩陣乘法，
    12 個行程只慢 1.3 倍，所以不是排程或降頻）。偵測網路在 1536 px 分塊上的中間張量每個幾十到上百 MB，辨識一批 6 個框也有幾 MB，
    全都在洗記憶體。對策就是讓工作量變小、變得放得進快取：等分分塊（偵測像素少 26 %）、辨識批次 1。
    改完之後同一頁讓 N 個行程同時各跑一次：8 個行程 x 1 執行緒每頁 2.5 秒（12x1 一樣、6x2 是 2.6、16x1 是 2.8、4x3 是 2.9；
    單行程單執行緒 8.7 秒）。所以 --workers 開 6~8 就到頂了；預設 6 x 2 執行緒（SPEC），實跑用的是 8 x 1。
  * 全量實測：need 394 頁 670 秒（每頁 1.70 秒）、其餘 413 頁 543 秒（每頁 1.31 秒），合計 807 頁 20 分鐘；
    頁內時間中位數 8.9 秒、最長 47.5 秒。OCR 定向投票平均每頁 2.4 秒（209 頁）。

== 已知限制（寫給看結果的人）==
  * **同類誤讀擋不掉**：C 讀成 Q、0 讀成 9、W 讀成 N 這種「字母讀成另一個字母、數字讀成另一個數字」，正規化救不回來，
    而 AMS 的 834 個 KKS 核心有 802 個存在只差一個字的鄰居。探勘量到約 0.3~0.7 %（1,082 個文字層位號裡 3 個）。
    所以 OCR 命中在卡片上一律標「推定」並寫出辨識信心，pid_index 另以辨識分數 ≥ 0.75 把關。
    本工具全量跑完後拿文字層當真值再量一次（468 頁、16,514 個「單一個字就是完整 KKS」的文字層位號）：OCR 在同一位置讀出同一個
    核心 92.1 %、沒讀出 KKS 7.7 %、讀成別的核心 38 個（0.23 %，其中一部分是鄰框重疊不是誤讀）；讀成的核心剛好是另一支
    AMS 位號的只有 1 個（PHC20BT017 讀成 BT011，分數 0.888——分數門檻擋不住）。那一頁有文字層所以不受影響，
    但沒有文字層的頁出現同樣的誤讀就會默默歸錯戶。實際抓到的一個：TDM01-D1205 p7 的儀器清單格 'C10LAC50 BT026' 讀成 BT025
    （分數 0.777）。清單是最危險的地方（上下左右都是只差一個數字的兄弟位號），所以 pid_index 對「已有符號位置的位號」
    不發布 OCR 的清單格；只有清單可找的位號才留，並標成清單（note=1）。
  * **圖框分區（border）目前等於沒有**：一般偵測（box_thresh 0.5）幾乎抓不到圖框邊條上孤立的單一字元——807 頁只有 120 頁
    讀到任何邊條標籤、沒有一頁湊得出格線（pid_lib.fit_grid 0／807），所以沒有文字層的圖紙（TDM01-D1205、TCM01-D1604／D1701、
    BMM01-D3702、Service Water Pumps）上的 OCR 命中都沒有分區，卡片只會寫百分比位置。orient 探勘另外 OCR 四條邊條
    （7 % 深、box_thresh 0.3、切成 ≤ 6:1 的小塊）可以讀到 7／10，但**不能直接接上**：pid_lib 的分區模型假設標籤印在每一格的正中間，
    而 Baker Hughes 的圖框（TDM01-D1205；沒有分區的 140 處 OCR 命中有 85 處在這份圖）把數字印在每一格**尾端的刻度旁**
    （讀圖確認），照中點推邊界會有一半的位號被標到隔壁格。要做就得先偵測刻度線，本工具沒有做。
  * 重疊的球泡（D0027-4 p2 的 =G11HSD11BE001 被鄰框壓到）偵測會斷成兩截；45 度斜寫的標籤偵測率低；
    很淡的灰色大字佔位符常沒有框。這些都不重跑第二輪去救。
  * 掃描圖 HT0-0-UCA04-D0114 上的 'X-TE-CW011-XBE' 這類帶 X 佔位的 ISA 名讀得到，但 pid_lib 沒有對應的比對規則。
  * 決定性的保證在快取之後：同一批快取 → --distill 逐位元組相同。OCR 本身只比過一頁（真值頁：8 行程 x 1 執行緒的正式結果
    與單行程 2 執行緒重跑的 597 個框，原文、座標、分數完全相同），沒有保證換了執行緒數、onnxruntime 版本之後每一頁都逐位元相同。

== 快取 ==
  paths.PID_OCR_CACHE\<sha1>.json，一頁一檔；sha1 的原文＝`rel.lower()|size|int(mtime)|page|配方 JSON`，
  配方 JSON 含版本（ver）與引擎身分（rapidocr-onnxruntime 版本＋三個 onnx 模型檔的大小）。PDF 換版、配方或模型一變，
  鍵就不同＝自動重做；舊檔留在原地不礙事（要清就整個資料夾刪掉，代價是重跑）。失敗的頁寫成 <sha1>.err.json，
  算「做過了」，--retry-errors 才會再試。快取內容是**全部**的框（原文、分數、四個角、是否直書）與每頁的倍率、轉正角、
  耗時；位號比對規則之後怎麼改都不必重跑 OCR，只要重跑 --distill。

== 對照表 tools/db/pid_ocr_map.json（--distill；契約＝SPEC 第 4 節）==
  {"kind":"pid_ocr","generated_by":…,"version":1,"recipe":{…},"stats":{…},"pages":{"<相對路徑>|<頁>":
     {"size","mtime","rot","rot_method","w_pt","h_pt","boxes","dup_text","tokens":[[原文,cx,cy,w,h,分數],…],"border":[[字,cx,cy],…]}}}
  * tokens＝pid_lib.tag_like 認得的字（完整 KKS、系統段／設備段、GE 元件名、ISA 名、差一兩個形近字的 KKS），
    **OCR 原文、不先對 AMS**；座標是轉正後整張圖的比例（中心＋寬高，五位小數）。依（cy, cx, 原文）排序。
  * **與文字層位號重疊的 OCR 字不寫進表**（dup_text 記下丟了幾個）。pid_index 本來就會丟掉它們（文字層為準），
    這裡用的是 pid_index 自己的兩個函式（text_tag_boxes／overlaps_text），結果一樣；差別只在檔案大小——
    文字層完整的 A0 圖一頁就有 800 個重複的位號框。要看沒丟之前的樣子用 --keep-text-dups（別 commit 那個）。
    2026-10-10 起 text_tag_boxes 把「含有 KKS 核心的文字層字」全部算進去（不只是比對器認得的寫法），所以 CTCI 圖上
    'G11MAN31QN001N1' 這種「核心＋元件碼」的字，OCR 再讀一次的那一筆也不寫了（全庫多丟 690 個）。
  * border＝貼著圖紙邊緣 3 % 以內、1 個字母或 1~2 位數字的框（圖框分區用；pid_lib.fit_grid 做容缺擬合）。
    文字層自己就有圖框格線的頁不寫（pid_index 先用文字層的）。目前沒有一頁靠它湊得出格線（見「已知限制」）。
  * 圖框裡印的 CAD 檔路徑（磁碟代號開頭、…8274-001-06.dwg 結尾的那種字串）會被 tag_like 當成「差一兩個字的 KKS」，而且會觸發
    「不可含本機絕對路徑」的自檢，所以原文符合 pid_lib.ABS_PATH_RE 或 PATH_LIKE_RE 的字不寫（stats.path_like，全庫 18 個）。
    只用 ABS_PATH_RE 的時候（2026-10-08）只擋到 4 個：OCR 常在冒號後面多讀一個空白，另外 14 個就留在表裡了。
  * 沒有時間戳、沒有本機絕對路徑（結尾以 regex 自檢）；一頁一行，方便看 git diff。

== 用法 ==
  py tools/db/pid_ocr.py --status                              # 各範圍：已快取／失敗／待做
  py tools/db/pid_ocr.py --max-minutes 7                       # 跑 need 範圍，7 分鐘到就停派工、等手上的頁做完、回傳碼 0
  py tools/db/pid_ocr.py --scope all --max-minutes 7 --workers 8 --threads 1
  py tools/db/pid_ocr.py --only "KND01-D0027-4" --force        # 只做路徑含這段字的頁（可寫成 "…pdf|2" 指定頁）
  py tools/db/pid_ocr.py --distill                             # 快取 → tools/db/pid_ocr_map.json
  之後：py tools/db/pid_index.py ＆ py tools/db/pid_shots.py（讀到新的對照表，更新 cardwork）。
  前景指令 10 分鐘會被砍：每次用 --max-minutes／--max-pages 限量，重複執行到「待做 0」為止；隨時中斷都可續跑。

== 實測（2026-10-08，Ryzen 9 9900X 12 核 24 緒、8 行程 x 1 執行緒；數字都是本工具與 pid_index 印出來的，別處要引用請重跑）==
  OCR：工作清單 807 張圖紙全部做完（need 394＋其餘 413），失敗 0；快取 807 檔 25.0 MB；框 275,332 個。
       轉正角：文字層 595 頁、OCR 投票 209 頁、default 3 頁（空白頁）；R≠0 的 7 頁（D0027-4 p2／p3 與 TMM01-D1001 p2 是 270；
       四份 UP?02 系統圖的 p3 是 /Rotate 270 再加 R=90——橫躺掃進去的送件清單，讀圖確認轉正）。放大重做 90 頁（偵測 3.2~4.8 px/pt）。
  對照表：807 頁、1.39 MB（1,460,699 bytes）；像位號的字 21,217 個（kks 6,130、kks_fuzzy 8,781、kks_eq 3,204、kks_sys 2,727、ge 375），
       另有 67,749 個與文字層重疊而不寫（--keep-text-dups 全寫進去是 4.69 MB，超過 3 MB 的目標）；圖框標籤 550 個。
       連跑兩次逐位元組相同。
  定位（pid_index）：1,502 → **1,568／1,679（93.4 %）**，新增 66 支全靠 OCR：LAC 55（TDM01-D1205 給水泵組，其中 33 支只在清單裡）、
       MAJ 6（TCM01-D1604）、HSD 5（D0027-4 p2，含使用者的例子 G12HSD10QN101）。另有 90 支文字層已定位的位號多了 OCR 命中。
       OCR 命中 216 處／156 支位號；被引用圖紙 109 → 118 張、圖紙影像 9.0 → 9.8 MB。只做 need 與全部都做，定位數相同（1,568）。
       還找不到的 111 支：ISA 名 45（圖上寫 X-TE-CW011-XBE，沒有比對規則）、殘缺名稱 26、LAC60／70 14（清單格的機組前綴或核心
       讀壞，例如 'C1CLAC60BL001'）、MAN30／60 的 BP101~104 共 12、GE 96TT-GT-10~12／PH-1~3 共 12、G11HAD10QN003／004 共 2
       （後三組在全部 807 頁的 OCR 結果裡找不到原樣的讀數；只差一個字的都是別的位號，如 MAN60BP001、MAN60WP101）。
  讀圖核對：31 處 OCR 命中（11 份圖 14 張圖紙，其中 22 處在有 /Rotate 旗標的圖紙上）框都在標籤上；讀錯 1 處
       （上面那個清單格，靠「清單同一列各欄的設備段應該相同」交叉比對抓到，已不發布），其餘 30 處位號都讀對。

== 2026-10-10：只重新蒸餾（**沒有重跑 OCR**；配方、快取鍵、807 個快取檔都沒動）==
  蒸餾規則改了兩處（上面「對照表」兩條：文字層已有的字一律不寫、CAD 檔路徑擋乾淨），其餘不變：
  對照表 807 頁、1.35 MB（1,419,324 bytes）；像位號的字 21,217 → 20,513 個（kks 5,445、kks_fuzzy 8,762、kks_eq 3,204、
  kks_sys 2,727、ge 375）＝少掉 690 個文字層已有的字與 14 個路徑字串；連跑兩次逐位元組相同。
  pid_index 用新舊兩張對照表跑出來的 by_tag 與 sheets 完全相同（只有 stats.ocr_map 的兩個計數不同）。
  同一天 pid_index 的比對規則大改（尾碼必須相等、引用的 note 代碼、給水泵組同型典型、斜線系統段兩框合併、差一點點的
  疊寫標籤…），各項數字與逐筆差異見 pid_index.py 檔頭「2026-10-10」。OCR 定位的數字因此不同於上面 10-08 的那一段。
"""
import argparse
import hashlib
import io
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pid_lib as L  # noqa: E402

GENERATED_BY = 'tools/db/pid_ocr.py'
MAP_VERSION = 1
CACHE_VERSION = 1                      # 快取檔格式版本（欄位改了就 +1；配方改了請改 RECIPE['ver']）

# 配方：整包進快取鍵。每個值的由來見檔頭「配方 r1」。
RECIPE = {
    'ver': 'r1b',
    'det_zoom': 2.5,                   # 偵測影像的倍率（px/pt）
    'rec_per_det': 1.6,                # 渲染（辨識裁圖用）＝偵測倍率 × 1.6 ＝ 4 px/pt
    'max_px': 12000,                   # 渲染長邊上限（px）
    'det_zoom_max': 5.0,               # 自適應倍率的上限（px/pt）
    'adapt_low_px': 17.0,              # 偵測影像裡框短邊的中位數低於這個值＝字太小，要放大重做
    'adapt_target_px': 21.0,           # 放大到中位數約這麼高
    'adapt_min_boxes': 12,             # 長條框不到這麼多個就不判斷（幾乎空白的頁）
    'adapt_min_gain': 1.15,            # 算出來的新倍率沒有比原來大 15 % 以上就不重做
    'tile': 1536, 'overlap': 256, 'blank_tile': 235,
    'tiling': 'even',                  # 'even'＝各軸等分、分塊縮到剛好夠用；'probe'＝探勘的固定 1536 方塊（最後一塊貼齊邊緣）
    'edge_guard': True, 'dedupe_contain': 0.6,
    'det_limit_side_len': 736, 'det_limit_type': 'min',
    'det_thresh': 0.3, 'det_box_thresh': 0.5, 'det_unclip_ratio': 1.6, 'det_use_dilation': True,
    'text_score': 0.5,
    'rec_batch': 1,                    # 辨識一次送幾個框（結果會因同批補白寬度而有極少數差異，所以進配方）
    'use_cls': True, 'vert_ratio': 1.5, 'max_aspect': 30,
    'orient': {'px_per_mm': 4.5, 'lo': 1800, 'hi': 4200, 'max_boxes': 60, 'min_chars': 3, 'margin': 0.08,
               'min_score': 0.6, 'min_n': 12},
}
BORDER_BAND = 0.03                     # 圖框標籤：中心離圖紙邊緣不到 3 %
BORDER_RE = re.compile(r'^(?:[A-Z]|\d{1,2})$')
# 圖框裡印的 CAD 檔路徑（--distill 不寫進對照表）：磁碟代號＋冒號＋（OCR 多讀的空白）＋斜線，或 .dwg 結尾的檔名
PATH_LIKE_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]:\s*[\\/]|\.dwg\b', re.I)
THREAD_ENV = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')


# ================================================================ 引擎與配方
def engine_identity():
    """OCR 引擎身分（進快取鍵）：rapidocr-onnxruntime 的版本＋三個 onnx 模型檔的大小。沒安裝回 None。
    只看檔案、不 import 套件（--status／--distill 不需要把 onnxruntime 載進來）。"""
    try:
        import importlib.util
        from importlib import metadata
        spec = importlib.util.find_spec('rapidocr_onnxruntime')
        if spec is None or not spec.submodule_search_locations:
            return None
        d = os.path.join(list(spec.submodule_search_locations)[0], 'models')
        models = {fn: os.path.getsize(os.path.join(d, fn)) for fn in sorted(os.listdir(d)) if fn.endswith('.onnx')}
        return {'rapidocr': metadata.version('rapidocr-onnxruntime'), 'models': models}
    except Exception:                                     # noqa: BLE001
        return None


def full_recipe():
    """RECIPE＋引擎身分＝快取鍵用的完整配方；沒裝 rapidocr 就中止（沒有引擎身分算不出鍵，也不可能有快取）。"""
    eng = engine_identity()
    if eng is None:
        sys.exit('找不到 rapidocr-onnxruntime（py -m pip install rapidocr-onnxruntime）；本工具的快取鍵含引擎身分，沒有它無法繼續')
    r = dict(RECIPE)
    r['engine'] = eng
    return r


def make_engine(threads, rc):
    """RapidOCR 引擎，兩件事原廠包裝都沒給選項、實測差很多，所以自己接手三個模型的 onnxruntime session：
      * **intra-op 執行緒數釘死**：不釘的話每個行程各開滿所有核心，多行程時互相踩。
      * **打開 CPU memory arena**：包裝把它關掉（enable_cpu_mem_arena=False），每次推論的中間張量都重新向系統要記憶體；
        辨識是上千次的小推論，關著 arena 時 770 個框要 14.8 秒，打開只要 4.8 秒（偵測 6.1 → 5.1 秒）。輸出逐位元相同。
    做法：先讓包裝照常建好（它的 SessionOptions 工廠換成釘執行緒的版本），再把三個 session 換成自己建的。
    屬性名稱是 rapidocr-onnxruntime 1.2.3 的（text_detector.infer／text_cls.infer／text_recognizer.session）；
    換了版本若對不上就退回包裝自己建的 session（只是比較慢），不影響結果。"""
    import onnxruntime
    import rapidocr_onnxruntime.utils as U

    def _so():
        so = onnxruntime.SessionOptions()
        so.intra_op_num_threads = int(threads)
        so.inter_op_num_threads = 1
        return so
    U.SessionOptions = _so
    from rapidocr_onnxruntime import RapidOCR
    # det_model_path=None 一定要給：RapidOCR 1.2.3 只要收到任何 det_* 參數就會去讀 det_dict['model_path']（None＝用內建模型）
    eng = RapidOCR(det_model_path=None, det_limit_side_len=rc['det_limit_side_len'], det_limit_type=rc['det_limit_type'],
                   det_thresh=rc['det_thresh'], det_box_thresh=rc['det_box_thresh'],
                   det_unclip_ratio=rc['det_unclip_ratio'], det_use_dilation=rc['det_use_dilation'],
                   text_score=rc['text_score'])
    eng.text_recognizer.rec_batch_num = int(rc['rec_batch'])
    models = os.path.join(os.path.dirname(U.__file__), 'models')
    for holder, model in ((getattr(eng.text_detector, 'infer', None), 'ch_PP-OCRv3_det_infer.onnx'),
                          (getattr(eng.text_cls, 'infer', None), 'ch_ppocr_mobile_v2.0_cls_infer.onnx'),
                          (getattr(eng.text_recognizer, 'session', None), 'ch_PP-OCRv3_rec_infer.onnx')):
        mp = os.path.join(models, model)
        if holder is None or not hasattr(holder, 'session') or not os.path.exists(mp):
            continue
        so = _so()
        so.log_severity_level = 4
        so.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.enable_cpu_mem_arena = True
        holder.session = onnxruntime.InferenceSession(mp, sess_options=so, providers=[
            ('CPUExecutionProvider', {'arena_extend_strategy': 'kSameAsRequested'})])
    return eng


def cache_key(rel, size, mtime, page, recipe):
    s = '%s|%d|%d|%d|%s' % (rel.lower(), size, mtime, page, json.dumps(recipe, sort_keys=True, separators=(',', ':')))
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def cache_paths(cache_dir, key):
    """→ (成功的快取檔, 失敗記錄檔)。"""
    return os.path.join(cache_dir, key + '.json'), os.path.join(cache_dir, key + '.err.json')


# ================================================================ 影像處理（ocr 探勘 pidocr.py 的移植；只在工作行程裡用）
def _bgr(pix):
    import cv2
    import numpy as np
    a = np.frombuffer(pix.samples_mv, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(a, cv2.COLOR_RGB2BGR)


def _tiles(W, H, tile, ov, mode='even'):
    """偵測影像 → 分塊 [(x, y, 寬, 高)]。
    'probe'：探勘的切法——固定 tile x tile，步距 tile − ov，最後一塊貼齊邊緣（常與前一塊幾乎整塊重疊）。
    'even' ：塊數相同，但每一軸把起點等分、塊的邊長縮到「剛好蓋滿而且重疊仍 ≥ ov」（進位到 32 的倍數，偵測網路的步幅）。
             A1 圖 20 塊由 1536x1536 變 1408x1248，送進偵測器的像素少 26 %（A3 大小的頁少 31~41 %）；
             偵測是這支工具的瓶頸（吃記憶體頻寬，多行程也不會變快），所以這是實打實省下的時間。"""
    def axis(n):
        if n <= tile:
            return [(0, n)]
        if mode == 'probe':
            return [(x, tile) for x in list(range(0, n - tile, tile - ov)) + [n - tile]]
        k = -(-(n - ov) // (tile - ov))                              # 塊數＝ceil((n − ov) ÷ 步距)
        size = min(tile, -(-(n + (k - 1) * ov) // (k * 32)) * 32)
        return [(int(round(i * (n - size) / float(k - 1))), size) for i in range(k)]
    return [(x, y, tw, th) for (y, th) in axis(H) for (x, tw) in axis(W)]


def _crop(img, pts):
    import cv2
    import numpy as np
    pts = np.float32(pts)
    w = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3])))
    h = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
    if w < 2 or h < 2:
        return None
    m = cv2.getPerspectiveTransform(pts, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))
    return cv2.warpPerspective(img, m, (w, h), borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_CUBIC)


def _dedupe(quads, thr):
    """跨分塊的重複框：交集面積 ≥ thr × 較小框的面積 → 留大的（沒被切到的那個）。"""
    import numpy as np
    if not quads:
        return []
    bb = np.array([[min(p[0] for p in q), min(p[1] for p in q), max(p[0] for p in q), max(p[1] for p in q)] for q in quads],
                  dtype=np.float32)
    area = (bb[:, 2] - bb[:, 0]) * (bb[:, 3] - bb[:, 1])
    order = np.argsort(-area, kind='stable')
    keep = []
    cell = 256
    grid = {}
    for i in order:
        x0, y0, x1, y1 = bb[i]
        cells = [(gx, gy) for gx in range(int(x0) // cell, int(x1) // cell + 1) for gy in range(int(y0) // cell, int(y1) // cell + 1)]
        dup = False
        for j in sorted({j for c in cells for j in grid.get(c, ())}):
            ix = min(x1, bb[j, 2]) - max(x0, bb[j, 0])
            iy = min(y1, bb[j, 3]) - max(y0, bb[j, 1])
            if ix > 0 and iy > 0 and ix * iy >= thr * area[i]:
                dup = True
                break
        if not dup:
            keep.append(int(i))
            for c in cells:
                grid.setdefault(c, []).append(int(i))
    return [quads[i] for i in keep]


def detect(eng, img, det_scale, rc):
    """img＝轉正後的渲染（BGR）；偵測在縮小 det_scale 倍的副本上分塊做 → (框清單（**渲染影像**的 px，四個角）, 統計)。"""
    import cv2
    import numpy as np
    dimg = cv2.resize(img, None, fx=det_scale, fy=det_scale, interpolation=cv2.INTER_AREA) if det_scale < 0.999 else img
    ds = det_scale if det_scale < 0.999 else 1.0
    DH, DW = dimg.shape[:2]
    tile, ov = rc['tile'], rc['overlap']
    quads = []
    ntile = nedge = 0
    for (x, y, tw, th) in _tiles(DW, DH, tile, ov, rc['tiling']):
        t = dimg[y:y + th, x:x + tw]
        if t.min() > rc['blank_tile']:                        # 全白的分塊
            continue
        ntile += 1
        boxes, _ = eng.text_detector(np.ascontiguousarray(t))
        if boxes is None or len(boxes) == 0:
            continue
        for b in boxes:
            bx0, by0 = float(b[:, 0].min()), float(b[:, 1].min())
            bx1, by1 = float(b[:, 0].max()), float(b[:, 1].max())
            if rc['edge_guard'] and (
                    (x > 0 and bx0 <= 3 and bx1 < ov - 6) or (x + tw < DW and bx1 >= tw - 4 and bx0 > tw - ov + 6) or
                    (y > 0 and by0 <= 3 and by1 < ov - 6) or (y + th < DH and by1 >= th - 4 and by0 > th - ov + 6)):
                nedge += 1                                    # 被內側分塊邊切到、而且短到鄰塊能完整容納 → 丟（鄰塊會給完整的）
                continue
            quads.append([[(float(p[0]) + x) / ds, (float(p[1]) + y) / ds] for p in b])
    nraw = len(quads)
    quads = _dedupe(quads, rc['dedupe_contain'])
    hs = []
    for q in quads:
        w = max(math.dist(q[0], q[1]), math.dist(q[2], q[3]))
        h = max(math.dist(q[0], q[3]), math.dist(q[1], q[2]))
        if max(w, h) >= 2 * min(w, h):
            hs.append(min(w, h) * ds)
    return quads, {'tiles': ntile, 'raw': nraw, 'edge_drop': nedge, 'boxes': len(quads), 'long_boxes': len(hs),
                   'med_h': round(statistics.median(hs), 1) if hs else None}


def recognise(eng, img, quads, rc):
    """每個框從渲染影像裁出來 → 直的轉 90 度 → 0／180 分類 → 辨識 → [(原文, 分數, 四個角 px, 是否直書)]＋統計。"""
    import numpy as np
    crops, meta = [], []
    nskip = 0
    for qi, q in enumerate(quads):
        c = _crop(img, q)
        if c is None:
            continue
        h, w = c.shape[:2]
        if rc['max_aspect'] and max(h, w) > rc['max_aspect'] * min(h, w):
            nskip += 1
            continue
        if h >= rc['vert_ratio'] * w:
            crops.append(np.ascontiguousarray(np.rot90(c)))
            meta.append((qi, 1))
        else:
            crops.append(c)
            meta.append((qi, 0))
    out = []
    if crops:
        if rc['use_cls']:
            crops, _cls, _ = eng.text_cls(crops)
        rec, _ = eng.text_recognizer(crops)
        for (qi, v), (txt, sc) in zip(meta, rec):
            sc = float(sc)
            if sc >= rc['text_score'] and txt.strip():
                out.append((txt, sc, quads[qi], v))
    return out, {'crops': len(crops), 'ar_skip': nskip, 'read': len(out)}


def ocr_dirs(eng, img, oc):
    """OCR 定向投票（orient 探勘 pidorient.ocr_dirs 的移植）：img＝**照顯示的樣子**渲染的整頁。
    整張偵測一次；取最長的 max_boxes 個長條框，每個朝兩個可能的閱讀方向各辨識一次，分數較高（差距 ≥ margin、
    至少 min_score、至少 min_chars 個英數字）的方向得到「英數字數」票 → {'E','N','W','S': 票數}。"""
    import numpy as np
    out = Counter()
    boxes, _ = eng.text_detector(img)
    if boxes is None or len(boxes) == 0:
        return dict(out)
    cand = []
    for b in boxes:
        c = _crop(img, b)
        if c is None or c.shape[0] < 4 or c.shape[1] < 4:
            continue
        h, w = c.shape[:2]
        if w >= 1.5 * h:
            cand.append((w, 'H', c))
        elif h >= 1.5 * w:
            cand.append((h, 'V', c))
    cand.sort(key=lambda t: -t[0])
    cand = cand[:oc['max_boxes']]
    if not cand:
        return dict(out)
    a, b2, kinds = [], [], []
    for _n, k, c in cand:
        if k == 'H':
            a.append(c)                                                  # 由左往右（E）
            b2.append(np.ascontiguousarray(c[::-1, ::-1]))               # 倒字（W）
        else:
            a.append(np.ascontiguousarray(np.rot90(c, 3)))               # 由下往上讀（N）：順時針轉正
            b2.append(np.ascontiguousarray(np.rot90(c, 1)))              # 由上往下讀（S）
        kinds.append(k)
    ra, _ = eng.text_recognizer(a)
    rb, _ = eng.text_recognizer(b2)
    for k, (ta, sa), (tb, sb) in zip(kinds, ra, rb):
        na = sum(ch.isalnum() for ch in ta)
        nb = sum(ch.isalnum() for ch in tb)
        sa, sb = float(sa), float(sb)
        if max(sa, sb) < oc['min_score'] or abs(sa - sb) < oc['margin']:
            continue
        if sa > sb and na >= oc['min_chars']:
            out['E' if k == 'H' else 'N'] += na
        elif sb > sa and nb >= oc['min_chars']:
            out['W' if k == 'H' else 'S'] += nb
    return dict(out)


def ocr_page(eng, page, r_text, r_thin, rc):
    """一頁 fitz.Page → 快取記錄的內容（不含檔案身分）。r_text＝文字層定出的 R 或 None；r_thin＝薄文字層的猜測或 None。
    **不可呼叫 page.remove_rotation()**（見檔頭「轉正角」）。"""
    import fitz
    tm = {}
    t0 = time.perf_counter()
    W_pt, H_pt = page.rect.width, page.rect.height             # 顯示尺寸（套完 /Rotate）
    votes = None
    if r_text is not None:
        R, method = int(r_text), 'text'
    else:
        oc = rc['orient']
        mm = max(W_pt, H_pt) / 72.0 * 25.4
        z = int(min(max(mm * oc['px_per_mm'], oc['lo']), oc['hi'])) / max(W_pt, H_pt)
        votes = ocr_dirs(eng, _bgr(page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False, colorspace=fitz.csRGB)), oc)
        R2, _conf, n, _rule = L.decide_R(votes, W_pt, H_pt)
        if R2 is not None and n >= oc['min_n']:
            R, method = int(R2), 'ocr'
        elif r_thin is not None:
            R, method = int(r_thin), 'text-thin'
        else:
            R, method = 0, 'default'
    tm['orient_s'] = round(time.perf_counter() - t0, 2)
    long_pt = max(W_pt, H_pt)
    cap = rc['max_px'] / long_pt                                # 渲染倍率上限（px/pt）
    det_zoom = min(rc['det_zoom'], cap)
    passes = []
    img = quads = None
    zoom = 0.0
    for attempt in (1, 2):
        zoom = max(min(det_zoom * rc['rec_per_det'], cap), det_zoom)
        t1 = time.perf_counter()
        img = None                                              # 先放掉上一輪的影像再渲染（A0 一張 300 MB）
        img = _bgr(L.render_upright(page, R, zoom=zoom))
        t2 = time.perf_counter()
        quads, st = detect(eng, img, det_zoom / zoom, rc)
        st.update(det_zoom=round(det_zoom, 3), zoom=round(zoom, 3), render_s=round(t2 - t1, 2), det_s=round(time.perf_counter() - t2, 2))
        passes.append(st)
        if attempt == 1 and st['long_boxes'] >= rc['adapt_min_boxes'] and st['med_h'] is not None and st['med_h'] < rc['adapt_low_px']:
            z2 = min(det_zoom * rc['adapt_target_px'] / max(st['med_h'], 1.0), rc['det_zoom_max'], cap)
            if z2 >= det_zoom * rc['adapt_min_gain']:
                det_zoom = z2
                continue
        break
    t3 = time.perf_counter()
    items, rst = recognise(eng, img, quads, rc)
    tm['rec_s'] = round(time.perf_counter() - t3, 2)
    H, W = img.shape[:2]
    boxes = []
    for txt, sc, q, v in items:
        row = [txt, round(sc, 3)]
        for p in q:
            row += [round(p[0] / W, 5), round(p[1] / H, 5)]
        row.append(v)
        boxes.append(row)
    boxes.sort(key=lambda b: (round((b[3] + b[7]) / 2.0, 5), round((b[2] + b[6]) / 2.0, 5), b[0]))
    w_pt, h_pt = L.upright_size(page, R)
    return {'rotate': page.rotation, 'rot': R, 'rot_method': method, 'rot_votes': votes,
            'w_pt': round(w_pt, 2), 'h_pt': round(h_pt, 2), 'zoom': round(zoom, 4), 'det_zoom': round(det_zoom, 4),
            'W': W, 'H': H, 'passes': passes, 'rec': rst,
            'box_fields': ['text', 'score', 'x0', 'y0', 'x1', 'y1', 'x2', 'y2', 'x3', 'y3', 'vertical'],
            'boxes': boxes, 'timing': tm}


# ================================================================ 多行程
_W = {}


def _worker_init(threads, recipe, root, cache_dir):
    """工作行程啟動：OpenCV 單執行緒、建引擎（每個行程一個，執行緒數釘死）。行程裡不印任何東西（主控台是 cp950）。"""
    import cv2
    cv2.setNumThreads(1)
    try:
        cv2.ocl.setUseOpenCL(False)
    except Exception:                                     # noqa: BLE001
        pass
    _W.update(eng=make_engine(threads, recipe), recipe=recipe, root=root, cache=cache_dir)


def _write_json(path, obj):
    tmp = path + '.%d.tmp' % os.getpid()
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


def _worker_page(job):
    """（多行程工作函式）一頁：OCR → **自己寫快取檔** → 只回摘要。失敗寫 <key>.err.json（算做過了，--retry-errors 才重試）。"""
    t0 = time.perf_counter()
    c0 = time.process_time()
    rec = {'v': CACHE_VERSION, 'key': job['key'], 'rel': job['rel'], 'page': job['page'], 'size': job['size'], 'mtime': job['mtime'],
           'recipe': _W['recipe'], 'err': None}
    try:
        ap = os.path.join(_W['root'], job['rel'].replace('/', os.sep))
        st = os.stat(ap)
        if st.st_size != job['size'] or int(st.st_mtime) != job['mtime']:
            raise RuntimeError('PDF changed since the worklist was built (size/mtime)')
        import fitz
        doc = fitz.open(ap)
        try:
            rec.update(ocr_page(_W['eng'], doc[job['page'] - 1], job.get('R'), job.get('R_thin'), _W['recipe']))
        finally:
            doc.close()
    except Exception as e:                                # noqa: BLE001
        rec['err'] = '%s: %s' % (type(e).__name__, str(e)[:200])
    tm = dict(rec.get('timing') or {})
    tm.update(wall_s=round(time.perf_counter() - t0, 2), cpu_s=round(time.process_time() - c0, 2))
    rec['timing'] = tm
    ok_path, err_path = cache_paths(_W['cache'], job['key'])
    if rec['err']:
        _write_json(err_path, rec)
    else:
        _write_json(ok_path, rec)
        if os.path.exists(err_path):
            os.remove(err_path)
    last = (rec.get('passes') or [{}])[-1]
    return {'rel': job['rel'], 'page': job['page'], 'err': rec['err'], 'wall_s': tm['wall_s'], 'cpu_s': tm['cpu_s'],
            'rot': rec.get('rot'), 'rot_method': rec.get('rot_method'), 'rotate': rec.get('rotate'),
            'det_zoom': rec.get('det_zoom'), 'zoom': rec.get('zoom'), 'passes': len(rec.get('passes') or []),
            'med_h': last.get('med_h'), 'boxes': len(rec.get('boxes') or [])}


# ================================================================ 工作清單
def get_worklist(a, log, need_ctx=False):
    """→ (工作清單 dict, pid_index.build 的內部情境 或 None)。預設在行程內呼叫 pid_index（只用文字層；約 7 秒）。
    --worklist FILE 則讀現成的檔（need_ctx＝蒸餾要用到文字層，不能只給檔）。"""
    if a.worklist and not need_ctx:
        with open(a.worklist, encoding='utf-8') as f:
            wl = json.load(f)
        if wl.get('kind') != 'pid_worklist':
            sys.exit('不是 pid_index.py --worklist 寫出的檔：%s' % os.path.basename(a.worklist))
        return wl, None
    import pid_index
    ns = argparse.Namespace(library=a.library, sqlite=a.sqlite, text_cache=a.text_cache, jobs=min(8, os.cpu_count() or 1),
                            ocr_map=None, no_ocr=True, no_superseded=True)
    out, ctx = pid_index.build(ns, log)
    return pid_index.worklist(ctx, out), ctx


def select_rows(wl, scope, only):
    rows = [r for r in wl['sheets'] if scope == 'all' or r['need']]
    if only:
        low = [o.lower() for o in only]
        rows = [r for r in rows if any(o in ('%s|%d' % (r['rel'], r['page'])).lower() for o in low)]
    return rows


def _prio(r):
    """先做 OCR 真的會補到東西的頁（沒有文字層、或該有位號卻沒著落），再做「只是同一份圖已被引用」的頁。"""
    rs = r.get('reasons') or []
    return (0 if ('sparse' in rs or 'expected' in rs) else (1 if rs else 2), r['rel'], r['page'])


def row_state(cache_dir, r, recipe):
    """→ (key, 'ok'|'err'|'todo')。"""
    k = cache_key(r['rel'], r['size'], r['mtime'], r['page'], recipe)
    ok_path, err_path = cache_paths(cache_dir, k)
    return k, ('ok' if os.path.exists(ok_path) else ('err' if os.path.exists(err_path) else 'todo'))


# ================================================================ 三個指令
def cmd_status(a):
    recipe = full_recipe()
    wl, _ctx = get_worklist(a, print)
    print('配方 %s；引擎 %s' % (recipe['ver'], recipe['engine']))
    print('快取目錄 %s' % a.cache)
    for scope in ('need', 'all'):
        rows = select_rows(wl, scope, a.only)
        c = Counter(row_state(a.cache, r, recipe)[1] for r in rows)
        print('--scope %-4s 圖紙 %4d：已快取 %4d、失敗 %d、待做 %4d' % (scope, len(rows), c['ok'], c['err'], c['todo']))
        if scope == 'need':
            for reason in ('sparse', 'expected', 'referenced'):
                sub = [r for r in rows if reason in r['reasons']]
                c2 = Counter(row_state(a.cache, r, recipe)[1] for r in sub)
                print('      %-10s %4d：已快取 %4d、失敗 %d、待做 %4d' % (reason, len(sub), c2['ok'], c2['err'], c2['todo']))
    if os.path.isdir(a.cache):
        fs = [f for f in os.listdir(a.cache) if f.endswith('.json')]
        print('快取檔 %d 個、%.1f MB（含舊配方／舊版 PDF 留下的）' % (
            len(fs), sum(os.path.getsize(os.path.join(a.cache, f)) for f in fs) / 1048576.0))


def cmd_run(a):
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    t0 = time.time()
    recipe = full_recipe()
    wl, _ctx = get_worklist(a, print)
    rows = sorted(select_rows(wl, a.scope, a.only), key=_prio)
    os.makedirs(a.cache, exist_ok=True)
    for fn in os.listdir(a.cache):                              # 上次被砍掉留下的半成品
        if fn.endswith('.tmp'):
            try:
                os.remove(os.path.join(a.cache, fn))
            except OSError:
                pass
    jobs = []
    st = Counter()
    for r in rows:
        k, state = row_state(a.cache, r, recipe)
        if not a.force and (state == 'ok' or (state == 'err' and not a.retry_errors)):
            st[state] += 1
            continue
        jobs.append({'key': k, 'rel': r['rel'], 'page': r['page'], 'size': r['size'], 'mtime': r['mtime'],
                     'R': r.get('R'), 'R_thin': r.get('R_thin')})
    pending = len(jobs)
    if a.max_pages:
        jobs = jobs[:a.max_pages]
    print('--scope %s%s：圖紙 %d、已快取 %d、先前失敗 %d、待做 %d；這次最多做 %d 頁%s（%d 個行程 x %d 執行緒）' % (
        a.scope, ('（--only %s）' % a.only) if a.only else '', len(rows), st['ok'], st['err'], pending, len(jobs),
        ('、%.1f 分鐘' % a.max_minutes) if a.max_minutes else '', a.workers, a.threads), flush=True)
    if not jobs:
        print('沒有要做的頁。')
        return 0
    for k in THREAD_ENV:                                        # 工作行程繼承：BLAS／OpenMP 不要再各開一堆執行緒
        os.environ.setdefault(k, '1')
    deadline = (t0 + a.max_minutes * 60.0) if a.max_minutes else None
    done = errs = 0
    wall_sum = cpu_sum = 0.0
    timed_out = False
    t_pool = time.time()
    n_proc = max(1, min(a.workers, len(jobs)))
    with ProcessPoolExecutor(max_workers=n_proc, initializer=_worker_init,
                             initargs=(a.threads, recipe, os.path.normpath(a.library), a.cache)) as ex:
        it = iter(jobs)
        live = set()

        def feed():
            nonlocal timed_out
            while len(live) < n_proc and not timed_out:         # 手上最多 n_proc 頁：時間到之後最多再等這幾頁做完
                if deadline and time.time() > deadline:
                    timed_out = True
                    break
                j = next(it, None)
                if j is None:
                    break
                live.add(ex.submit(_worker_page, j))
        feed()
        while live:
            fin, live = wait(live, return_when=FIRST_COMPLETED)
            for fu in fin:
                s = fu.result()
                done += 1
                wall_sum += s['wall_s']
                cpu_sum += s['cpu_s']
                name = s['rel'].rsplit('/', 1)[-1]
                if s['err']:
                    errs += 1
                    print('  [%3d/%d] 失敗 %s p%d：%s' % (done, len(jobs), name[:60], s['page'], s['err']), flush=True)
                else:
                    print('  [%3d/%d] %5.1fs  /Rotate %3d  rot %3d(%-9s)  det %.2f render %.2f px/pt%s  框 %4d  %s p%d' % (
                        done, len(jobs), s['wall_s'], s['rotate'], s['rot'], s['rot_method'], s['det_zoom'], s['zoom'],
                        '*' if s['passes'] > 1 else ' ', s['boxes'], name[:58], s['page']), flush=True)
            feed()
    el = time.time() - t_pool
    print('這次做完 %d 頁（失敗 %d）：行程池 %.0f 秒＝每頁 %.2f 秒（%d 行程 x %d 執行緒）；頁內平均 %.1f 秒、CPU %.1f 秒／頁' % (
        done, errs, el, el / max(done, 1), n_proc, a.threads, wall_sum / max(done, 1), cpu_sum / max(done, 1)))
    left = pending - done
    if left > 0:
        print('還有 %d 頁待做（%s）；估計還要 %.0f 分鐘。再跑一次同樣的指令即可續。' % (
            left, '時間到' if timed_out else '--max-pages', left * (el / max(done, 1)) / 60.0))
    else:
        print('待做 0。下一步：py tools/db/pid_ocr.py --distill')
    if errs:
        print('有 %d 頁失敗（已記成 .err.json，不會自動重試）；看完原因後用 --retry-errors 重跑。' % errs)
    print('耗時 %.1f 秒' % (time.time() - t0))
    return 0


def cmd_distill(a):
    import pid_index
    t0 = time.time()
    recipe = full_recipe()
    wl, ctx = get_worklist(a, print, need_ctx=True)
    pages = {}
    st = Counter()
    kinds = Counter()
    methods = Counter()
    for r in sorted(wl['sheets'], key=lambda r: (r['rel'], r['page'])):
        st['sheets'] += 1
        st['sheets_need'] += 1 if r['need'] else 0
        key, state = row_state(a.cache, r, recipe)
        if state != 'ok':
            st['err' if state == 'err' else 'not_cached'] += 1
            st['need_missing'] += 1 if r['need'] else 0
            continue
        with open(cache_paths(a.cache, key)[0], encoding='utf-8') as f:
            rec = json.load(f)
        if rec.get('v') != CACHE_VERSION or rec.get('size') != r['size'] or rec.get('mtime') != r['mtime']:
            st['bad_record'] += 1
            continue
        sh = ctx['sheets'][(r['rel'], r['page'])]
        pg = sh['pg']
        R = int(rec['rot'])
        tboxes = [] if a.keep_text_dups else pid_index.text_tag_boxes(pg, R)
        has_grid = bool(L.detect_grid(L.border_labels(pg, R)))
        tokens, border = [], []
        dup = 0
        for b in rec['boxes']:
            t = b[0].strip()
            xs, ys = b[2:10:2], b[3:10:2]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            kind = L.tag_like(t)
            if kind and (L.ABS_PATH_RE.search(t) or PATH_LIKE_RE.search(t)):
                # 圖框裡印的 CAD 檔路徑（磁碟代號開頭、.dwg 結尾）被 tag_like 當成「差一兩個字的 KKS」；
                # 它不是位號，而且會觸發本表與 pid.json 的「不可含本機絕對路徑」自檢，所以不寫。
                # OCR 常在冒號後面多讀一個空白（'P: \Contracts\2021\8274\8274-001-06.dwg'），ABS_PATH_RE 認不得，另以 PATH_LIKE_RE 補。
                st['path_like'] += 1
                continue
            if kind:
                if tboxes and pid_index.overlaps_text((x0, y0, x1, y1), tboxes):
                    dup += 1
                    continue
                kinds[kind] += 1
                tokens.append([t, round(cx, 5), round(cy, 5), round(x1 - x0, 5), round(y1 - y0, 5), round(float(b[1]), 3)])
            elif not has_grid and BORDER_RE.match(t.upper()) and (min(cx, 1 - cx) < BORDER_BAND or min(cy, 1 - cy) < BORDER_BAND):
                border.append([t.upper(), round(cx, 5), round(cy, 5)])
        tokens.sort(key=lambda t: (t[2], t[1], t[0]))
        border.sort(key=lambda t: (t[2], t[1], t[0]))
        pages['%s|%d' % (r['rel'], r['page'])] = {
            'size': r['size'], 'mtime': r['mtime'], 'rot': R, 'rot_method': rec['rot_method'],
            'w_pt': round(rec['w_pt'], 1), 'h_pt': round(rec['h_pt'], 1), 'boxes': len(rec['boxes']), 'dup_text': dup,
            'tokens': tokens, 'border': border}
        methods[rec['rot_method']] += 1
        st['pages'] += 1
        st['pages_need'] += 1 if r['need'] else 0
        st['boxes'] += len(rec['boxes'])
        st['tokens'] += len(tokens)
        st['dup_text'] += dup
        st['border'] += len(border)
        st['pages_with_tokens'] += 1 if tokens else 0
        st['pages_rescaled'] += 1 if len(rec.get('passes') or []) > 1 else 0
        st['rot_nonzero'] += 1 if R else 0
    stats = {'pages': st['pages'], 'pages_need': st['pages_need'], 'pages_with_tokens': st['pages_with_tokens'],
             'pages_rescaled': st['pages_rescaled'], 'rot_nonzero': st['rot_nonzero'],
             'rot_method': dict(sorted(methods.items())), 'boxes': st['boxes'], 'tokens': st['tokens'], 'dup_text': st['dup_text'],
             'border': st['border'], 'path_like': st['path_like'], 'token_kinds': dict(sorted(kinds.items())),
             'text_dups_kept': bool(a.keep_text_dups)}
    head = {'kind': 'pid_ocr', 'generated_by': GENERATED_BY, 'version': MAP_VERSION, 'recipe': recipe, 'stats': stats}
    # 一頁一行（鍵排序）；整份仍是合法的 JSON，pid_index 用 json.load 讀
    lines = ['{' + L.dumps(head)[1:-1] + ',"pages":{']
    keys = sorted(pages)
    for i, k in enumerate(keys):
        lines.append(json.dumps(k, ensure_ascii=False) + ':' + L.dumps(pages[k]) + (',' if i < len(keys) - 1 else ''))
    lines.append('}}')
    txt = '\n'.join(lines) + '\n'
    json.loads(txt)                                             # 自檢：真的是合法 JSON
    bad = L.ABS_PATH_RE.search(txt)
    if bad:
        sys.exit('對照表含本機絕對路徑：%r' % txt[max(0, bad.start() - 60):bad.start() + 60])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    tmp = a.out + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt)
    os.replace(tmp, a.out)
    n = len(txt.encode('utf-8'))
    print('寫出 %s：%d 頁、%.2f MB（%d bytes），sha1 %s' % (os.path.basename(a.out), st['pages'], n / 1048576.0, n,
                                                 hashlib.sha1(txt.encode('utf-8')).hexdigest()))
    print('  工作清單 %d 張圖紙（need %d）：有快取 %d（need %d）、沒快取 %d（need 缺 %d）、失敗 %d、記錄不符 %d' % (
        st['sheets'], st['sheets_need'], st['pages'], st['pages_need'], st['not_cached'], st['need_missing'], st['err'], st['bad_record']))
    print('  框 %d → 像位號的字 %d（%s）＋與文字層重疊而不寫的 %d＋像檔案路徑而不寫的 %d；圖框標籤 %d；有字的頁 %d；放大重做的頁 %d' % (
        st['boxes'], st['tokens'], dict(sorted(kinds.items())), st['dup_text'], st['path_like'], st['border'], st['pages_with_tokens'],
        st['pages_rescaled']))
    print('  轉正角：%s；rot≠0 的頁 %d' % (dict(sorted(methods.items())), st['rot_nonzero']))
    if n > 3 * 1048576:
        print('  注意：超過 3 MB 的目標')
    print('耗時 %.1f 秒' % (time.time() - t0))
    return 0


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='P&ID 圖紙離線 OCR（見檔頭 docstring）')
    ap.add_argument('--status', action='store_true', help='只印各範圍已快取／待做的頁數')
    ap.add_argument('--distill', action='store_true', help='快取 → OCR 對照表（不跑 OCR）')
    ap.add_argument('--scope', choices=('need', 'all'), default='need', help='need＝沒有文字層／已被引用／該有位號卻沒著落的圖紙（預設）；all＝全部圖紙')
    ap.add_argument('--only', action='append', metavar='SUBSTR', help='只做「相對路徑|頁」含這段字的圖紙（不分大小寫；可重複）')
    ap.add_argument('--workers', type=int, default=6, help='工作行程數（預設 6）')
    ap.add_argument('--threads', type=int, default=2, help='每個行程的 onnxruntime 執行緒數（預設 2）')
    ap.add_argument('--max-pages', type=int, default=0, help='這次最多做幾頁（0＝不限）')
    ap.add_argument('--max-minutes', type=float, default=0, help='幾分鐘後停止派工、等手上的頁做完（0＝不限）；回傳碼仍是 0')
    ap.add_argument('--force', action='store_true', help='已有快取的頁也重做')
    ap.add_argument('--retry-errors', action='store_true', help='先前失敗（.err.json）的頁再試一次')
    ap.add_argument('--keep-text-dups', action='store_true', help='--distill：與文字層位號重疊的字也寫進表（分析用，檔案大很多，不要 commit）')
    ap.add_argument('--worklist', metavar='FILE', help='讀 pid_index.py --worklist 寫好的清單（預設在行程內現算；--distill 一律現算）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（預設 paths.LIBRARY_ROOT；唯讀）')
    ap.add_argument('--sqlite', default=paths.AMS_SQLITE, help='AmsDb.sqlite（預設 paths.AMS_SQLITE；算工作清單用）')
    ap.add_argument('--text-cache', default=paths.PID_TEXT_CACHE, help='文字層字框快取目錄（預設 paths.PID_TEXT_CACHE）')
    ap.add_argument('--cache', default=paths.PID_OCR_CACHE, help='OCR 逐頁快取目錄（預設 paths.PID_OCR_CACHE）')
    ap.add_argument('--out', default=paths.PID_OCR_MAP, help='--distill 的輸出（預設 paths.PID_OCR_MAP＝tools/db/pid_ocr_map.json）')
    a = ap.parse_args()
    if not os.path.isdir(a.library):
        sys.exit('找不到文件庫：%s' % a.library)
    if a.status:
        return cmd_status(a)
    if a.distill:
        return cmd_distill(a)
    return cmd_run(a)


if __name__ == '__main__':
    sys.exit(main() or 0)
