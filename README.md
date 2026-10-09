# 新複循環廠 AMS Device Manager 匯出檔解析 — 網頁版

把 `20260910_AMS解析.xlsx`（28 張工作表、約 40 萬列，來源 `20260910.ams_merge`）轉成可搜尋、可篩選的靜態網頁。

**線上瀏覽：** https://momobacon-wq.github.io/AMS/

## 功能

- 28 張工作表全收錄，側欄依群組列出（總覽／設備／變更與查核／事件與 FF／CMX／統計與時間／參數／附錄）。
- **表格**（03–13、15、19–23、25–27）：虛擬捲動（21_HART參數現值 20 萬列也順）、凍結欄、欄位群組色帶、排序、全表搜尋、逐欄篩選與下拉 facet、欄位顯示/隱藏、匯出 CSV、點列看完整欄位詳情。
- **版面頁**（00、01、14、16、17、18、24）：忠實重現 Excel 的底色、字色、合併儲存格；01 摘要與 16 時間軸的 8 張圖表以 Chart.js 重畫。
- **02 設備查詢卡**：輸入目前位號、舊位號、HART 短/長位號、FF Block Tag、CMX 位號或 alias → 自動帶出識別、量程、FF、查核、CMX、最近 10 筆有意義變更，並可展開該設備的 HART/FF 參數現值。頂部搜尋框任何頁面都能用。
- 工作簿內所有 `HYPERLINK`（約 5 萬個）都變成可點的連結，跳到目標表並標示目標列；深連結可分享（例：`#/s/03?q=GT11`、`#/card/G11HAD60BT001`）。
- 條件式格式（嚴重度、信心、CMX 狀態、色階、資料橫條）已套用；淺色/深色主題；手機可用。

## 第二個資料集：完整資料庫解析（20260912，`docs/db/`）

**線上瀏覽：** https://momobacon-wq.github.io/AMS/db/

`20260912.ams_bckup` 是 AMS 的 SQL Server 2014 原生備份（資料庫 AmsDb）。還原後逐表倒成 SQLite，經多代理解讀／對抗驗證／稽核，產出 `20260912_AMS資料庫解析.xlsx`（55 張表）與同內容的網站（同一套前端，資料放在 `docs/db/data/`）。比文字匯出多出：實體網路位置（MUX／通道／COM 埠／FF LD）、完整事件稽核（29,773 筆 vs 13,682）、警報定義、使用者權限、範本參數、SnapOn 檔案資訊、資料表與程式碼字典。

- 02_設備查詢卡：輸入目前／舊位號、識別時位號、HostTag、裝置 ID、設備鍵、GUID 或別名（D0xxxx，與前一版相同）。
- 各表都有「設備別名 (alias)」欄，可在兩個資料集之間互相對照。
- 未收錄於網站（只在 Excel 明細活頁簿）：範本參數現值 306,891 列、全部警報定義 140,438 列。
- **氣動閥清單**（側欄群組，57～61）：Google 試算表「興達全廠氣動閥LIST_v2.6」併入——57 主表／58 水處理（每列附 AMS 設備連結與定位器廠牌比對）、59 兩讀並列、60 推翻紀錄、61 刪除紀錄。查詢卡：對到清單的 AMS 設備多一組「氣動閥」（閥體／執行器／定位器／SOV／極限開關／失效動作…，每格附出處、可開雲端文件）；AMS 沒有的閥位號（開關閥等）改顯示閥卡，不再是「查無」。試算表改了：`rclone backend copyid gdrive: 1_WOl6HYkY9y0WbGRH_NHP6d8cOsAWgk4ZmA1hwIQ5LE <xlsx> --drive-export-formats xlsx`（或 fill26 的 build_v26.py 輸出）→ `py tools/db/rebuild.py --only-pneuvalve --e2e`。格式見 CONTRACT.md「v4」。

### 重建（拿到新的 .ams_bckup 時）

所有 repo 外的路徑只寫在 `tools/db/paths.py`（環境變數 `AMS_SQLITE`／`AMS_CARDWORK`／`AMS_PDFTXT_CACHE`／`AMS_LIBRARY_ROOT`／`AMS_PREV_XLSX`／`AMS_BUILD_DIR` 可覆寫；`py tools/db/paths.py` 印出目前解析到的每一個與是否存在）。P&ID 的五個路徑是衍生的、沒有自己的環境變數：`PID_JSON`／`PID_SHOTS` 跟著 `AMS_CARDWORK`，`PID_TEXT_CACHE`（`pidtext\`）／`PID_OCR_CACHE`（`pidocr\`）固定在 `%LOCALAPPDATA%\AMS\`（各工具的 `--text-cache`／`--cache` 可改），`PID_OCR_MAP` 就是 repo 裡的 `tools/db/pid_ocr_map.json`。`order.json` 已在 repo，`make_order.py` 不必重跑。

| 步驟 | 指令 | 輸入 | 輸出 | 約 |
|---|---|---|---|---|
| 0. 一次：WSL 裝 SQL Server | `wsl -d Ubuntu-24.04 -u root bash /mnt/c/Users/<me>/AMS/tools/db/install.sh` | — | SQL Server 2025 Express、sqlcmd、pyodbc；sa 密碼寫 `/root/.ams_sa_pw` | 5 分 |
| 1. 還原並倒成 SQLite | `wsl -d Ubuntu-24.04 -u root bash /mnt/c/…/tools/db/restore.sh "/mnt/c/…/20260912.ams_bckup" /mnt/c/Users/<me>/AppData/Local/AMS/AmsDb.sqlite` | `.ams_bckup`（邏輯檔名從備份讀出） | `AmsDb.sqlite`（`paths.AMS_SQLITE`；`export_to_sqlite.py`＋`fix_blobs.py`） | 10 分 |
| 2～8 一條龍 | `py tools/db/rebuild.py --sqlite %LOCALAPPDATA%\AMS\AmsDb.sqlite --backup-date 2026-09-12` | 上一步的 SQLite、工程文件庫、dcdas 索引、hst-docsearch FTS | 下面每一步的輸出，結尾 verify_encrypted | 40 分 |
| 2. Excel 工作簿 | `py tools/db/build_workbook.py tools/db/order.json 主簿.xlsx 明細.xlsx 120000` | `AmsDb.sqlite`、`PREV_XLSX`（別名對應） | `AMS資料庫解析.xlsx`／`_明細.xlsx`、`sheets_cache.pkl`（模組結果快取，刪掉即重算）、`sheets_final.pkl`（都在 `BUILD_DIR`） | 10 分 |
| 3. 網站資料 | `py tools/db/extract_db.py <sheets_final.pkl> docs/db/data` | `sheets_final.pkl` | `docs/db/data/manifest.json`、`sheets/*.json`（結尾加密＋戳記；一條龍裡用 `--no-encrypt` 留明文給下面的產生器） | 2 分 |
| 4. 各產生器 → cardwork | `card_ams_extra.py`、`docmap_terminal.py`、`docmap_instlist.py`、`docmap_eomr.py`、`docmap_docindex.py`（引數見各檔檔頭） | `AmsDb.sqlite`、明文 `sheets/`、工程文件庫（`LIBRARY_ROOT`）、pdftotext 快取（`PDFTXT_CACHE`） | `CARDWORK/ams.json`、`terminal.json`、`instlist.json`、`eomr.json`、`docindex.json` | 15 分（首次 pdftotext 更久） |
| 5. 全文檢索 | `py tools/db/docmap_docsearch.py --data docs/db/data` | hst-docsearch 的 FTS 索引、`drive_map.json` | `CARDWORK/docsearch.json` | 4 分 |
| 6. 查詢卡附加資料 | `py tools/db/build_card_aux.py <CARDWORK> docs/db/data` | cardwork 五份＋docsearch、`%LOCALAPPDATA%\dcdas\index.sqlite`、`drive_map.json` | `docs/db/data/card/*.json` → 加密＋戳記 | 3 分 |
| 6b. 圖控 HMI 畫面位置 | `py tools/db/hmi_shots.py` → `py tools/db/hmi_nav.py` → `py tools/db/hmi_index.py`（順序固定；`rebuild.py` 在第 6 步之前自動跑，`--skip-hmi` 略過）。前置的 `py tools/db/hmi_runtime_map.py` **不在重建流程裡**：它是離線工具（要 rapidocr；重建流程本身沒有一步需要 OCR，要 rapidocr 的只有它和 6c 的 `pid_ocr.py` 兩支離線工具），輸出 `tools/db/hmi_runtime_map.json` 已 commit，只有使用者重拍／補拍圖控畫面時才要重跑 | `AMS_HMI_SCREENS`（圖控 `.cim` 畫面檔目錄＋`圖控\*.xlsx` 執行時截圖，唯讀）、`tools/db/hmi_runtime_map.json`、`AmsDb.sqlite`、dcdas 索引 | `CARDWORK/hmi_shots/`（440 張 webp＝155 設計時＋285 執行時，約 22 MB）、`hmi_nav.json`、`hmi.json` → 第 6 步併成 `sec.hmi` 與 `card/hmi/*.json` | 2 分 |
| 6c. P&ID 圖面位置 | `py tools/db/pid_index.py` → `py tools/db/pid_shots.py`（順序固定，與圖控相反：先定位才知道要出哪些圖；`rebuild.py` 在 6b 之後、第 6 步之前自動跑，`--skip-pid` 略過）。`py tools/db/pid_ocr.py` **不在重建流程裡**：它是離線工具（要 rapidocr-onnxruntime），蒸餾出的 `tools/db/pid_ocr_map.json` 已 commit、`pid_index` 只讀它；文件庫的 P&ID 換版或新增圖面時才要重跑（步驟見下面「P&ID 圖面位置」）。這兩步要 PyMuPDF 與 Pillow（實測 1.27.1／12.2.0）。OCR 對照表有過期的頁、或上一次靠 OCR 定位的位號這次不見了，`pid_index` 會印 `!!` 開頭的行點名是哪幾份圖，`rebuild.py` 在結尾再框起來印一次——**不中止、回傳碼不變**，要自己看 | `LIBRARY_ROOT`（工程文件庫現行的 P&ID PDF，現場走訪、唯讀）、`tools/db/pid_ocr_map.json`、`AmsDb.sqlite`（現行位號） | `CARDWORK/pid.json`（0.5 MB）、`CARDWORK/pid_shots/`（117 張轉正後的四階灰階 webp，10.5 MB，＋`index.json`）；文字層快取 `%LOCALAPPDATA%\AMS\pidtext\`（712 檔 14 MB）→ 第 6 步併成 `sec.pid` 與 `card/pid/*.json` | 10 秒（2026-10-10 實測：`pid_index` 9.6 秒＋`pid_shots` 全部沿用快取 0.1 秒；首次——沒有文字層快取、要抽 712 份 PDF，117 張圖全部重出——是 `pid_index` 16.5 秒＋`pid_shots` 3.2 秒：約 20 秒） |
| 7. 戳記＋驗證 | `py tools/db/rebuild.py --only-stamp` | — | 兩站 `index.html`／`version.json`；`verify_encrypted` 0 錯誤 | 1 分 |
| 7b. 氣動閥清單 | `py tools/db/pneuvalve_site.py docs/db/data`（`rebuild.py` 兩條路徑結尾自動跑；`--only-pneuvalve` 單跑） | `PNEUVALVE_XLSX`、`<CARDWORK>/pneuvalve_xwalk.json`、`drive_map.json` | `sheets/57～61.json`、02.json `valve`、00 目錄、manifest | 1 分 |
| 8. push 前 | `py tools/db/rebuild.py --only-stamp --e2e` | — | 端對端測試全綠 | 3 分 |

只改資料來源（docsearch／Drive 連結／比對規則）而沒有新備份時仍用 `py tools/db/rebuild.py`（`--recompare`，見下）；`rebuild.py --sqlite` 也接受 `--skip-workbook`（沿用 `sheets_final.pkl`）、`--skip-docsearch`、`--skip-drive-map`、`--skip-hmi`（沿用 cardwork 裡上次的 `hmi.json`／`hmi_shots`）、`--skip-pid`（沿用 cardwork 裡上次的 `pid.json`／`pid_shots`）。

## 資料加密（兩站；push 前必做）

`docs/*/data` 只發布密文：每個 JSON 以 AES-256-GCM 加密成 `<檔名>.bin`，金鑰由密語經 PBKDF2 導出，瀏覽器在登入後輸入密語解密（作法同 signal-atlas，細節見 [CONTRACT.md](CONTRACT.md)「加密與封裝」）。密語放在 `%LOCALAPPDATA%\AMS\web.key`（第 1 行；第 2 行是固定 salt，首次執行自動產生），不在 repo 裡。

```bash
py tools/encrypt_data.py docs/data              # 產生器已自動做；手動把明文目錄轉成 .bin + meta.json
py tools/encrypt_data.py docs/db/data
py tools/stamp_assets.py docs                   # 加密後重新戳記（build 讀 meta.json）
py -c "import sys; sys.path.insert(0,'tools/db'); import extract_db; extract_db.stamp('docs/db','docs/assets')"
py tools/verify_encrypted.py                    # 兩站重新解密驗證；0 錯誤才可 push（密語也可用環境變數 AMS_WEB_KEY 給）
py tools/encrypt_data.py docs/db/data --decrypt # 要重跑 build_card_aux / verify_data 時先還原明文（結尾會再加密）
py tools/encrypt_data.py docs/db/data --no-keep # 每個檔都以新的隨機 IV 重封（不沿用 git HEAD 的密文，也不檢查金鑰是不是已發布的那一把；平常不需要）
py tools/encrypt_data.py docs/db/data --dry-run # 只印會沿用／重封幾份、會刪幾個過期的 .bin，不寫檔（金鑰不符時同樣印原因並以非 0 結束）
```

**重新加密只動真的有變的檔（compare-and-keep，2026-10-08 起）**：`encrypt_data.py`（各產生器結尾呼叫的也是它）加密時會向 git 取 **HEAD** 上同一路徑的 `.bin`，用現在的金鑰打得開（AAD＝相對路徑）、而且解開後與新明文逐位元組相同，就把 HEAD 那份原封不動寫回去；有變的檔、新檔才以新的隨機 IV 重封。`meta.json` 的 `check` 同理沿用，所以內容沒變的站重新加密後 `meta.json` 也逐位元組相同。加密格式沒變，瀏覽器與 `verify_encrypted` 不必改。結果是重建後 `git status --short docs/` 只列出明文真的有變的 `.bin`，commit 也只帶那些。結尾那行會報數，2026-10-10 這次重建的實際輸出：`[encrypt] docs\db\data: 333 files  208.0 MB → 28.7 MB on the wire  build 729812fa52  (137 kept from git HEAD, 196 sealed fresh = 13.7 MB new)`——196＝工作目錄裡 71 個有變的 `.bin`＋125 個新檔（117 張 P&ID 圖紙＋8 個新增的分塊），其餘 137 個與 HEAD 逐位元組相同、不進這次 commit。以前每次重建都把全部密文重寫一遍（git HEAD 的 db 站是 208 檔 17.9 MB；加了 P&ID 圖紙影像之後是 333 檔 28.7 MB），密文不能做 delta 壓縮，全數進 `.git`（現在 292 MB）。比的是 HEAD 不是工作目錄：上一次建置還沒 commit 就再建一次，有變的檔會再重封一次，無妨。沒裝 git、資料目錄不在 git 工作區、HEAD 沒有那個檔（新檔、第一次加密）、個別舊密文打不開或明文不同 → 那幾份照舊重封，不報錯；**一份都沒沿用**時那行尾端附原因：`[keep off]`（`--no-keep`／`--fresh-salt`）／`[nothing for this dir at git HEAD]`／`[no file matches its git HEAD copy]`／`[key mismatch with git HEAD]`（最後一種不是附個括號就算了，見下一段）；有沿用、只是 HEAD 的 `meta.check` 用不上時附中性的 `[meta.check re-sealed]`。代價：commit 歷史從此確定看得出「哪幾個檔這次有變」（內容仍然看不到；以前從密文大小其實也幾乎看得出來）。

**這次的金鑰不是已發布的那一把 → 封完之後停下來（2026-10-10 起）**：git HEAD 上這個資料目錄有讀得懂的 `meta.json`、而這次的金鑰（密語＋salt）打不開它的 `check` 時，`encrypt_data.py` 照常把整個目錄封完（用這次的金鑰；不會因為要擋就把明文留在 `docs/` 底下）、印結尾那行，然後印 `[encrypt] STOP - key mismatch …` 並以 **exit 1** 結束。訊息寫原因——密語不同、salt 不同（會印出已發布的 salt，它本來就公開在 `meta.json`，照抄到 key 檔第 2 行即可）、兩者都不同、或 KDF 參數不同——與三條出路：(1) 放棄這次建置：`git checkout -- docs/db/data` 再 `git clean -fd -- docs/db/data`（後者清掉 HEAD 沒有的 `.bin`）；(2) 金鑰給錯了：修正 `AMS_WEB_KEY` 或 key 檔（第 1 行密語、第 2 行 salt），做 (1) 再重建；(3) 確定是要換金鑰（例如輪替完還沒 commit）：目錄已經用新金鑰封好，`py tools/db/rebuild.py --only-stamp` 戳記＋驗證後 commit 即可，手動加密時加 `--no-keep` 就不做這項檢查。為什麼要擋：key 檔第 2 行（salt）不見時（例如只從密碼管理器還原了密語）`encrypt_data.py` 會自己產生新 salt 寫回去，`AMS_WEB_KEY` 給錯也一樣——加密照樣成功、`verify_encrypted` 拿同一把金鑰去驗當然全綠，上線後才發現兩站互相重問密語、備品庫存的 `STOCK_TOKEN` 對不上而領取／放入全部「未授權」。經 `rebuild.py` 時：`build_card_aux`（或 `pneuvalve_site`）封完以非 0 結束 → rebuild 中止、不戳記，`index.html`／`version.json` 沒被動過。這項保護靠的是 git HEAD：在 repo 裡重建卻看到 `[nothing for this dir at git HEAD]`，一樣要停下來查。

**中斷後救得回來**：寫檔順序＝全部密文先在記憶體備妥（到這裡資料目錄完全沒動）→ 寫全部 `.bin`（明文還在，中斷就重跑）→ 刪掉沒有對應明文的舊 `.bin` → 寫 `meta.json` → 刪 `manifest.json`（這一刻起算「已加密」）→ 刪其餘明文。刪明文那一步刪不掉（檔案被別的程式開著）會跳過那幾個、其餘照刪，最後以非 0 結束並列出剩下的檔；**同一個加密指令再跑一次就會收拾**：殘留的明文與它的 `.bin` 解開後逐位元組相同就刪掉；沒有 `.bin`、打不開、內容不同的一個都不動，列出來並以非 0 結束（那不是已經封存的內容，要人看過才能刪）。

`.gitattributes`（repo 根目錄，2026-10-10 新增）只有一條規則 `*.bin binary`：密文不做換行轉換（`core.autocrlf`）、不做文字 diff／merge；沒有全 repo 的 eol 規則。

### 密語輪替

```bash
py tools/rotate_passphrase.py --dry-run   # 先看計畫：兩站狀態、key 檔、備份檔名
py tools/rotate_passphrase.py             # 新密語用 getpass 互動輸入兩次（不從命令列收）；--fresh-salt 連 salt 一起換
```
一條指令做完：舊密語（`web.key`）解出兩站明文副本 → 新密語重新加密 → 交換目錄 → 兩站戳記 → `verify_encrypted` 必須 0 錯誤 → 才改寫 `web.key`（舊檔另存 `web.key.bak-<日期時間>`）→ 印出新的 `STOCK_TOKEN`。任一步失敗就把舊密文換回來、key 檔不動；環境變數 `AMS_WEB_KEY` 有設時拒絕執行（否則寫了 key 檔也沒效）。
輪替那一次兩站全部 `.bin` 都會重寫（`rotate_passphrase.py` 加密的是 `data.rotate-tmp` 副本，git HEAD 沒有那個路徑；新金鑰也打不開舊密文，無從沿用——所以也不會被上面「金鑰不是已發布的那一把」那一關擋下），屬正常；輪替的 commit 進去之後，之後的重建才又只動有變的檔。**輪替完先 commit、再做別的重建**：HEAD 還是舊金鑰的 `meta.json` 時原地重建（`rebuild.py`、各產生器）會封好然後停在那一關，這是故意的。
輪替後要跟著做：(1) `cd tools/stock/worker && npx wrangler secret put STOCK_TOKEN` 貼印出的值（忘了會使領取／放入全部回「未授權（密語不符）」；E2E 的 `test_stock` 用同一算法比對，抓得到）、本機 `.dev.vars` 也改；(2) GitHub Actions secret `AMS_WEB_KEY` 改成新密語；(3) `py tools/tests/run_e2e.py` → push；(4) 通知同事新密語——舊的「記住此裝置」金鑰開站時驗不過 `meta.check` 會自動改問密語，不必逐台清；`--fresh-salt` 時所有人都要重輸。

只重建查詢卡附加資料：`encrypt_data.py --decrypt` → `build_card_aux.py`（結尾自動加密＋戳記）→ `verify_encrypted.py`。
DCS 比對的基準會讀 signal-atlas 的控制器索引 `%LOCALAPPDATA%\dcdas\index.sqlite`（在 signal-atlas repo 跑 `py tools\dcdas.py build` 產生；沒有就只用 DCS 寫入／端子表）。
各產生器輸出（cardwork）不在手邊時：`py tools/db/build_card_aux.py --recompare docs/db/data` 只重算 DCS 比對（並換入 docsearch、補 Drive 連結；cardwork 沒有 `hmi.json`／`pid.json` 時要自己加 `--no-hmi`／`--no-pid` 沿用上次發布的那一組，否則以非 0 結束——`rebuild.py` 會替你判斷）；`py tools/db/patch_site_spec.py docs/db/data` 把 02/13 表規格改動套到已發布資料（要先解密）。

查詢卡的「文件全文檢索」與 Google 雲端硬碟連結（2026-09-24 起）：

```bash
py tools/db/rebuild.py            # 一鍵：下面各步按順序跑，任一步失敗就停（明文會先加密回去；patch_site_spec 改過而 build_card_aux 沒跑完時 02／13 先換回原樣）；--spec 多跑 patch_site_spec（這次會發布 P&ID 圖面位置，而已發布的 02 還沒有它的摘要組／區段、或那個區段的標題／說明文字與 extract_db 現在的不同時自動套，不必加）、--skip-docsearch／--skip-drive-map／--skip-hmi／--skip-pid 省時間、--only-stamp 只改了前端、--e2e 最後多跑端對端測試；P&ID 位置默默變少（OCR 對照表過期等）不算失敗，但結尾會再框起來印一次 `!!` 警告

# rebuild.py 等價的手動步驟
py tools/db/drive_map.py                                   # Google 雲端硬碟桌面版中繼資料 → %LOCALAPPDATA%\AMS\drive_map.json（文件庫相對路徑 → 檔案 ID）
py tools/encrypt_data.py docs/db/data --decrypt
py tools/db/docmap_docsearch.py --data docs/db/data         # hst-docsearch 的 FTS 索引（~/.claude/skills/hst-docsearch/config.json）以位號＋AMS 序號搜全庫 → %LOCALAPPDATA%\AMS\cardwork\docsearch.json（約 4 分鐘）
py tools/db/hmi_shots.py && py tools/db/hmi_nav.py && py tools/db/hmi_index.py   # 圖控 HMI：畫面縮圖 → 選單路徑 → 位號座標索引（順序固定，約 2 分鐘；--skip-hmi 時略過）
py tools/db/pid_index.py && py tools/db/pid_shots.py         # P&ID 圖面：位號在哪張圖、圖上哪裡（文字層＋已 commit 的 pid_ocr_map.json）→ 被引用圖紙的影像（順序固定，約 10 秒；--skip-pid 時略過）
py tools/db/patch_site_spec.py docs/db/data                 # 02.json 摘要／區段規格（只在 extract_db 規格有改時；rebuild.py 把它排在各產生器之後、build_card_aux 之前）
py tools/db/build_card_aux.py --recompare docs/db/data      # 併入 sec.docsearch、sec.hmi＋card/hmi/*.json、sec.pid＋card/pid/*.json、index.docs 補 url、重算比對、加密、戳記
py tools/stamp_assets.py docs && py tools/verify_encrypted.py
```

摘要空白的欄位（設計廠牌／型號、出廠型號／序號、設計量程、P&ID／邏輯圖／Hook-up／位置圖）會依序改用文件索引、全文檢索命中的推定值；所有文件來源的數值都可點開雲端硬碟的那份檔案（需有該資料夾的 Drive 權限）。

查詢卡的「圖控 HMI 畫面位置」（2026-10-03 起）：摘要在「備品庫存（倉庫）」之前直接顯示「圖控 HMI 畫面（這台儀器畫在哪一頁）」——畫面名稱＋導覽路徑＋畫面影像與紅圈標記（2026-10-05 起不收合、也不再重複列欄位；超過 3 張時只先展開第一張，其餘點標題才展開並載入）；「完整資料」裡的「圖控 HMI 畫面位置」有同一張圖與完整欄位、逐格來源（同一張畫面多處時標 ①②③，「所在位置」描述的永遠是 ①；點圖可放大）。覆蓋 870/1,679 台（51.8%）。索引建在 Screens **根目錄的 248 個操作員畫面**；另 225 個子目錄的元件面板／函式庫範本不建索引，但字串已逐條掃過（命中的 12 支位號都已由根目錄畫面涵蓋、FF 0 命中）＝遞迴全部 473 個 `.cim` 都查過。FF 設備（351 台）定讞無法對應。**2026-10-04 起畫面影像改用執行時截圖**（使用者在機組上逐頁拍的 1920×1080 畫面，`Screens\圖控\*.xlsx`；對應表 `tools/db/hmi_runtime_map.json` 由 `hmi_runtime_map.py` 離線產生並 commit）：被引用的 43 個畫面**全部**有影像（原本只有 20 個有設計時 ThumbNail），而且**逐選單機組各一張**（HRSG11／HRSG12 是兩份不同的現值，卡片依「以選單機組 … 開啟」那一列挑）。畫面上的值是擷取當時的現值、不是即時值，說明列會寫明日期與機組。細節與座標基準見 [CONTRACT.md](CONTRACT.md)「v5（docs/db 站：圖控 HMI 畫面位置）」。

查詢卡的「P&ID 圖面位置」（2026-10-08 起；2026-10-10 經六組獨立查核後修正過一輪，以下都是修正後的數字）：摘要在「圖控 HMI 畫面」之前直接顯示「P&ID 圖面位置（這台儀器畫在哪一張圖、圖上哪裡）」——每張圖紙一塊：圖號＋版次、圖名、「PDF 第 p／n 頁」、圖框分區，最多三段短籤（(a) 圖上實際畫的字與它跟本台的關係；(b) 這一處不是儀器符號時以粗體寫明它是什麼；(c) PDF 文字層或 OCR 讀圖＋辨識信心——這張圖上任何一處 OCR 標記的辨識信心低於 0.8 時這一段轉紅並點名是哪幾處）、「開啟 PDF（Google 雲端硬碟）↗」，再來是以標記 ① 為中心的**細部視窗**（一個影像像素一個 CSS 像素，字讀得到）＋整張圖的**小地圖**（紅圈＝位號、藍框＝細部範圍）；點細部視窗開可縮放、拖曳的燈箱（− ＋ 全圖 回到標記，多處時「下一處」）。不收合；畫在兩張以上的圖紙時只先展開第一張，其餘點圖號那一列才展開並下載那一張圖。影像一律延後：展開中的那一張捲進畫面才抓，換到另一台設備時把新卡用不到的圖紙影像釋放掉（一張解碼後 16～37 MB）。「完整資料」裡的「P&ID 圖面位置」是同一塊圖＋五個欄位（P&ID 圖面／圖面頁次／所在位置／圖上標示／對應方式）與逐格來源（同一張圖多處時標 ①②③，「所在位置」描述的永遠是 ①，儀器符號旁的標籤一律排在引用之前）。覆蓋 **1,582/1,679 台（94.2%**；母數與圖控相同，已扣掉 249 台 JK MUX 模組——那些卡片寫的是「不在 P&ID 比對範圍」，不是「查無」）：HART 1,243/1,328、**FF 339/351**（和圖控相反，FF 設備在圖上找得到：GE 氣機的 GFD01 系統示意圖／P&ID 308 台＋發電機示意圖 EGJ01-D0004 31 台），畫在 117 張圖紙（54 份 PDF）上，1,395 台只畫在一張、187 台兩張以上（最多 3 張）。這些數字在 `card/index.json` 的 `pid.stats`（單張／多張的台數是由各台的 `sec.pid` 數出來的），卡片的「查無」文案也取自那裡、不寫死。
怎麼找的（`tools/db/pid_index.py`，規則與每一條的由來在 `pid_lib.py` 檔頭）：**現場走訪**工程文件庫（31,896 個 PDF；不讀 hst-docsearch 索引——索引比磁碟舊，認不得剛進庫的新版次），只看檔名認出 P&ID／系統示意圖 712 份，把同一張圖的各版次、舊編號、廠商檔名副本歸成一個圖號家族、**每張圖只留最高版次**（398 張圖扣掉二、三號機組專屬 26 張）＝ 372 份圖 1,047 頁（A4 直式封面 240 頁、圖紙 807 張）。先比對 PDF 文字層（595 張圖紙有可用的文字層），再以離線 OCR 的對照表補文字層沒有的字（807 張圖紙都做過 OCR；**文字層為準**，與文字層的位號重疊的 OCR 字一律不用）：標記 ① 來自文字層的 1,483 台、來自 OCR 的 99 台（給水泵組 TDM01-D1205 整份沒有文字層 67 台、HRSG 廠商圖 BFD01-D0002／D0003／D0004 上畫成向量字的控制閥 21 台、TCM01-D1604 6 台、SCR 圖 KND01-D0027 的線條字球泡 5 台）。同一支位號只發布「機組歸屬」最好的一級，**等級只看儀器符號旁的標籤**：圖上畫的就是本台（818 台）＞圖面不分機組（446 台，GE 氣機／汽機圖的位號不帶機組）＞以另一台氣機繪製的**典型圖**（244 台，全是 G12：卡片上看到的是 `=G11…`／`11…`，會照實寫「這張是以 G11 繪製的典型圖，本台 G12 取同一位置」）＞同一迴路編號、功能代號不同（6 台）＞圖面自己聲明適用於同型各台（68 台：凝結水泵 TCM01-D1114 畫 LCC10，LCC20／LCC30 共 26 台取同一位置；給水泵組 TDM01-D1205 只畫 LAC50，LAC60／LAC70 共 42 台取同一位置）；C10 與 G11／G12、別的 Block 的位號絕不互相套用。2026-10-10 查核後加的四條規矩：(a) **尾碼必須相等**——圖上 `…BP272C`、`…BT044A`、`…QN001N1`、`…BL001-BL01` 這種核心後面帶元件字母／元件碼／子項的標籤是另一個項目，只歸給尾碼相同的 AMS 位號，不退而歸給不帶尾碼的那一支（`stats.dropped.sfx_mismatch` 129）；(b) **圖上自己聲明不適用本機組的圖紙不發布**——GFD01-D0013 標籤帶 X2 前綴的那一張只適用 unit 2-2（`dropped.foreign_sheet` 70）；(c) **「提到位號」不等於「畫在這裡」**——每一處命中帶 `note` 代碼：0 儀器符號旁的標籤（1,658 處）、1 圖上註記或表格（儀器清單）裡的文字（36）、2 跨圖訊號旗標（15）、3 儀用／廠用空氣分配圖上的用氣點（72）、4 迴路詳圖 TYPICAL 小圖（45）；1～4 是**引用**，排在符號之後、絕不把等級較低的符號擠掉，卡片逐處寫明「不是儀器符號的位置」；(d) OCR 的字經過相近字元（0／O、8／B…）校正才對上的（`ocr-fix`，55 處），卡片寫出 OCR 原本讀成什麼，不寫「與本台位號相同」。同型各台、(b)、空氣分配圖與逐處覆寫是 `pid_lib.py` 裡**宣告＋建置時驗證**的四張表（`TRAIN_TYPICALS`／`FOREIGN_SHEETS`／`AIR_SHEETS`／`HIT_OVERRIDES`）：圖上找不到那句註記或那個結構就不套用、計數並印出來，不會默默照舊。
要知道的但書：(1) **影像不是正本**——是那一頁轉正後的四階灰階無損 WebP（長邊 2400～3600 px，117 張共 10.5 MB；2026-10-10 起量化偏暗、整張用灰色畫的圖先拉黑點，髮絲線與線條字才留得住——整頁是點陣圖的 4 張例外，照原樣等距取四階，免得小字糊掉；顏色丟掉了，GE 圖的藍色管線、紅色版次雲形框都變成灰——117 張裡 44 張有 2 % 以上的彩色墨跡，非藍色的彩色墨跡超過 0.5 % 的有 15 張），只供定位，內容以「開啟 PDF」那一份為準。連結只開「位置讀自的那一份檔」，雲端硬碟對照（drive_map）沒有它就不附連結、**不改連其他版次**（目前 54 份都有連結；其中 2 份的本機檔名多了雲端硬碟桌面版加的「 (1)」，以去掉尾碼的檔名對到雲端上的同一份檔）。(2) **只用現行最高版次**：舊版次圖面上的位置一律不發布（使用者自己舉的 G12HSD10QN101 就是例子——D0027 第 2 版的文字層有 `HSD10QN101`，第 4 版的文字層已經沒有這個字，真正的 FCV 球泡是線條字，只有 OCR 讀得到）。文件庫進了新版，位置就跟著新版走；最新版讀不了（壞檔、有密碼）時那張圖就沒有位置，不會退回舊版。(3) **OCR 可能把字讀成相近的另一支位號**（同類誤讀擋不掉）：OCR 讀出的位置一律標「推論」並寫出辨識信心（採用門檻 0.75；唯一放寬到 0.70 的是條件很嚴的「差一點點的疊寫標籤」，目前 6 處，每次建置都會印出是哪幾支）；這張圖上各處 OCR 標記的最低信心（`conf_min`）低於 0.8 時卡片用紅字點名是哪幾處——239 處 OCR 命中裡 41 處，落在 37 台設備的 38 塊圖紙上。典型圖／迴路／同型各台也標「推論」，只有「文字層而且圖上就是本台或不分機組」才標「文件」（各台第一塊圖紙：文件 1,217 台、推論 365 台）。(4) **4 台在現行圖上只找到引用、沒有儀器符號**（`pid.stats.devices_ref_only`）：C10LAC50BP005 只在給水泵組圖第 5 頁的迴路詳圖小圖與第 7 頁的儀器清單裡，C10LAC50BT029、C10LAC60BP005、C10LAC70BP005 只在第 7 頁的儀器清單裡——卡片最上面會先說「這次比對（PDF 文字層＋OCR）沒有讀到這支位號的儀器符號——不代表圖上沒有畫，請開 PDF 確認」。另有 120 台除了儀器符號還帶著引用的標記（用氣點、旗標、清單格…），逐處標明。(5) **圖框分區不是每張都有**：117 張裡 13 張沒有（8 張沒有可用的文字層、5 張文字層裡沒有圖框字；OCR 讀不到邊條上孤立的單一字元），1,770 塊圖紙裡 208 塊的 ① 沒有分區、只寫百分比位置。(6) 還有 **97 台查無**：ISA 迴路名 45（1-TI-CW011-* 39 台在掃描的循環水泵圖 UCA04-D0114 上寫成帶 X 佔位的 `X-TE-CW011-XAE`，沒有比對規則；1-LI-CW101-*、1-TI-CW029-* 各 3 台）、時間戳／殘缺名稱 26、G11／G12 MAN30 與 C10MAN60 的 BP101～104 12、GE 96TT-GT-10～12／96TT-PH-1～3 12、C10LAC60BT029 與 C10LAC70BT029 2——查無＝現行圖面的文字層與 OCR 結果都找不到，不代表圖上一定沒有。(7) 只做 AMS 設備的卡；AMS 沒有的閥（閥卡）不在這一版範圍。其餘已知限制（OCR 沒讀到的球泡、清單頁本身是點陣圖、同一支位號幾個球泡的先後…）見 CONTRACT v6「已知限制」。
離線 OCR（`tools/db/pid_ocr.py`，定位與 `hmi_runtime_map.py` 相同）：要跑它才需要 `py -m pip install rapidocr-onnxruntime`（實測 1.2.3；`--status`／`--distill` 也要——快取鍵含引擎版本與模型檔大小，換了版本等於快取全部失效）；逐頁結果快取在 `%LOCALAPPDATA%\AMS\pidocr\`（807 頁 25 MB），`--distill` 蒸餾成 `tools/db/pid_ocr_map.json`（807 頁、1.4 MB、像位號的字 20,513 個，**要 commit**；存的是 OCR 原文與字框，不預先對 AMS；與文字層位號重疊的字、圖框裡印的 CAD 檔路徑不寫），重建流程只讀這張表、不跑 OCR。什麼時候要動它：

| 情境 | 要做的 |
|---|---|
| 拿到新的 AMS 備份（位號變了、圖沒變） | 不必碰 OCR：`rebuild.py --sqlite …`（或 `rebuild.py`）自己會跑 `pid_index` → `pid_shots`，新位號直接拿現有的文字層快取與對照表重新比對 |
| 文件庫的 P&ID 換版或新增圖面 | `rebuild.py` 照常會用新版的文字層；但那份 PDF 在對照表裡的項目（以檔案大小＋修改時間認）已過期，`pid_index` 整筆不用、計入 `stats.ocr_map.stale`，並印 `!!` 開頭的行點名是哪幾份圖、哪些上一次靠 OCR 定位的位號這次沒有位置了（`rebuild.py` 結尾再框起來印一次；**不會中止、回傳碼不變**），那張圖上靠 OCR 的位號會變回查無。補回：`py tools/db/pid_ocr.py --status` → `py tools/db/pid_ocr.py --max-minutes 7 --workers 8 --threads 1`（重複執行到印出「待做 0」；只做快取沒有的頁；加 `--scope all` 連目前不需要的圖紙也做——2026-10-08 全部 807 頁約 20 分鐘，數字見 `pid_ocr.py` 檔頭）→ `py tools/db/pid_ocr.py --distill` → commit `pid_ocr_map.json` → `py tools/db/rebuild.py --e2e`。換版後 `pid_lib.HIT_OVERRIDES`（寫的是頁碼與圖上區域）若對不到任何命中也會印出來，要重新讀圖再改那張表 |
| `pidocr\` 快取不見了（換機器） | 已 commit 的對照表照常可用。**不要直接跑 `--distill`**：它只寫有快取的頁，會把表蒸餾成殘缺的；要先 `--scope all` 全部重跑（rapidocr 版本不同也一樣：快取鍵不同，等於沒有快取） |
| 想確認某一支位號標得對不對 | `py tools/db/pid_index.py --verify G12HSD10QN101`：印出命中並把紅框疊在轉正後的整張圖上（另有第一處周圍的放大圖），存到 `%LOCALAPPDATA%\AMS\pidverify\`（會順便重寫 `pid.json`；輸出是決定性的——同樣的輸入重跑，`pid.json` 與圖紙影像都逐位元組相同） |
| 想知道某一筆命中為什麼沒發布 | `py tools/db/pid_index.py --trace <檔>`：另寫追查旁檔（每筆命中用到的特殊規則、每筆沒發布的命中與原因；不屬於資料契約） |

格式、轉正角慣例、比對規則與已知限制見 [CONTRACT.md](CONTRACT.md)「v6（docs/db 站：P&ID 圖面位置）」。
`extract.py`／`extract_db.py` 的 `--no-encrypt` 只供本機測試，明文輸出不可 push（`.gitignore` 也擋著）。

### push 前關卡

```bash
git config core.hooksPath tools/hooks             # 一次（只影響本機）：commit 時擋機密檔（web.key／.dev.vars／.ams_bckup／.ams_sa_pw／庫存 csv／import*.sql）與 docs/*/data 明文 .json
py tools/db/rebuild.py --only-stamp --e2e         # 每次 push 前：兩站戳記 → verify_encrypted → run_e2e（端對端）→ 印 git status --short docs/；exit 0 才 push
```
GitHub 端另有 `.github/workflows/check.yml`：每次 push／PR 在 ubuntu 上跑 `tools/verify_encrypted.py`，密語讀 repo 的 Actions secret `AMS_WEB_KEY`（值＝`web.key` 第一行；沒設定就直接失敗，不會靜默通過）。

## 備品庫存（docs/db 站）

查詢卡「一目了然」靠後的一組「備品庫存（倉庫）」（前面兩組依序是 P&ID 圖面位置、圖控 HMI 畫面——兩組都整列寬、直接看圖，備品庫存緊接在圖控之後；後面只剩收合的文件全文檢索）：以儀器清單／EOMR 的完整型號碼對照倉庫料號，列出同型號／同系列的備品數量與儲位，可直接領取／放入（自動帶入位號、可填用途與工單號）；`#/stock/` 是庫存總表（搜尋、購物車批次、紀錄匯出、反查可安裝位號）。
後端是 Cloudflare Worker + D1（`tools/stock/worker/`，免費方案）；寫入需要登入 token＋由密語導出的 `STOCK_TOKEN`。部署、合約匯入（`contracts_to_inventory.py`）與本機測試見 [tools/stock/README.md](tools/stock/README.md)；`docs/db/stock-config.json` 的 `endpoint` 留空時整個功能隱藏。試算表「物料管理系統」＋Apps Script（`tools/stock/Code.gs`）是同格式的替代後端。

## 登入閘門（員工代號）與登入紀錄

兩個網站共用 `docs/assets/auth.js`：開站先要求輸入員工代號，對照 Google 試算表的 **Users** 分頁（姓名由分頁帶出），登入／造訪／登出都寫進同一份試算表的 **AMS_Log** 分頁。驗證與寫入由綁在試算表上的 Apps Script 網頁應用程式（`tools/auth/Code.gs`）處理；部署步驟與本機測試方式見 [tools/auth/README.md](tools/auth/README.md)。`docs/auth-config.json` 的 `endpoint` 留空時閘門關閉。

- 枚舉節流：全站每分鐘登入 ≥30 次或失敗 ≥20 次一律回「嘗試次數過多」、失敗紀錄每 10 分鐘最多寫 20 列、失敗回應延遲 1.5 秒（改常數在 `Code.gs` 開頭，改完要重新部署新版本）。
- 離線：讀不到 `auth-config.json` 時用 localStorage 快取的設定撐住閘門——有工作階段才放行（已看過的資料離線可查），沒有就鎖住；只有設定檔 404 或 `endpoint` 留空才算關閉。登出會清掉工作階段與記住的密語金鑰，「記住此裝置」預設不勾。
- 離職／停權：Users 分頁刪列（擋新登入；舊工作階段在下次開站且距上次驗證超過 10 分鐘時踢出）→ D1 `revoked` 表加代號（立即擋備品寫入）→ 需切斷資料瀏覽只能輪換密語。步驟見 [tools/auth/README.md](tools/auth/README.md)「離職／停權 SOP」。

## 資料更新（20260910 匯出檔資料集）

```bash
# 需要 Python 3 + openpyxl
py tools/extract.py "<路徑>/20260910_AMS解析.xlsx" docs/data     # 約 25 秒，會先清掉舊輸出
py tools/verify_data.py "<路徑>/20260910_AMS解析.xlsx" docs/data # 逐格對帳，0 錯誤才 exit 0
```

- 活頁簿由 openpyxl 產生、沒有公式快取值，`tools/amsx/formula.py` 自行計算所有公式（HYPERLINK、MATCH、INDEX、COUNTIF、SUMPRODUCT…）；`tools/amsx/cf.py` 計算條件式格式。
- `tools/verify_data.py` 是獨立寫成的對帳程式（不引用 extractor 程式碼），比對每一格的值、每一個連結的目標、圖表數值與條件式格式。
- 資料格式說明見 [CONTRACT.md](CONTRACT.md)。

## 端對端測試（tools/tests/）

```
py -m pip install playwright && py -m playwright install chromium   # 一次
py tools/tests/run_e2e.py                                           # 起本機 mock 登入伺服器（8771）→ 跑全部測試 → 關掉；exit 0 才算過
py tools/tests/run_e2e.py --keep-server --only card                 # 只跑某個模組、伺服器留著給你手動看
py tools/tests/test_pid_wording.py                                  # P&ID 建置端的文案與關卡：不開瀏覽器、不碰資料目錄，可單獨跑（run_e2e 也會收它：--only pid_wording）
```
密語與 `encrypt_data.py` 同一來源：環境變數 `AMS_WEB_KEY` → `AMS_WEB_KEY_FILE` 指向的檔 → `%LOCALAPPDATA%\AMS\web.key` 第一行；測試員工代號用 `tools/auth/mock_users.csv`。
2026-10-10 的實際結果：7 個模組全過、383 項檢查（`test_auth` 17、`test_card` 180、`test_main` 13、`test_pid_wording` 83、`test_pneuvalve` 69、`test_stock` 10、`test_sw` 11），約 80 秒。
涵蓋：登入閘門（錯代號、錯密語）、查詢卡（文件全文檢索收合組與 Google 雲端硬碟連結、DCS 不符旗標、查無位號的相近建議、上一頁同步查詢框、手機無橫向捲動；圖控 HMI 畫面的縮圖、標記與逐選單機組的截圖）、**P&ID 圖面位置**（`test_card` 的 `pid_*` 幾段：摘要組排在圖控之前、圖紙標頭與 PDF 連結、細部視窗對準標記 ①、小地圖、縮放拖曳的燈箱與「下一處」、影像捲到／展開才抓、多張圖紙只先展開第一張、引用（註記／旗標／用氣點／迴路詳圖）講明不是儀器符號、紅字看整張圖最低的辨識信心並點名、`ocr-fix`、JK 位號寫「不在比對範圍」、查無文案的數字取自 `index.pid.stats`、換卡／雙胞胎共用／離開時的影像釋放、手機版面與雙指縮放、**照網站的 CSP 執行一遍**（其餘測試略過 CSP）；`PID_PIN` 把 G12HSD10QN101 的標記 ① 釘在 D0027 Rev.4 第 2 頁的絕對座標 (0.4666, 0.7083)±0.003——其餘幾何檢查都只拿畫面與資料自己的 `marks` 互比，轉正角或座標換算錯了照樣全綠，只有這一筆抓得到。`test_pid_wording`：以合成的命中直接呼叫 `build_card_aux` 的 `pid_rows`／`pid_shared_boxes`／`pid_check`／`pid_doc`／`pid_collect`，把 rel 五種、note 代碼 0～4、「與本台位號相同」的條件、`ocr-fix` 的 raw、`conf`／`conf_min`／`confs`、同一個框被不相干的位號認領就以非 0 結束、`card/pid/` 失敗時原封不動，逐項釘住）、備品庫存（`test_stock`：卡片領取 1 顆、位號自動帶入 → `#/stock/` 數量 −1 → 紀錄有位號；錯的 `stockToken` 回「未授權」——mock 以 `AMS_MOCK_STOCK_TOKEN`（`run_e2e` 用密語＋salt 算出，與 Worker 的 `STOCK_TOKEN` 同算法）比對，密語輪替後忘了換 Worker 的 secret 在這裡就會露餡）、版本橫幅與 Service Worker（`test_sw`：假 `version.json`＋時鐘快轉 6 分鐘 → 「資料已更新」；植入舊版本快取 → 重載後被 keep 清單刪掉、另一站的 `data/` 不動）、舊站（`test_main`：`#/s/03?q=GT11` 有列與 facet 下拉、01 六張圖表、點連結儲存格 → `?r=` 且目標列高亮、手機無橫向捲動）、錯誤回報、console 零錯誤。截圖在 `tools/tests/out/`（不進 repo）。push 前統一跑 `py tools/db/rebuild.py --only-stamp --e2e`（戳記＋驗證＋這套測試）。

## 前端快取與錯誤回報

- `docs/sw.js`（Service Worker，兩站共用）：帶 `?v=` 的資料檔／程式檔快取優先（網址已含建置或內容雜湊），`version.json`／`auth-config.json`／`stock-config.json` 只走網路，其餘網路優先、離線用快取。頁面載入後把本站用到的版本值交給它，舊版本快取自動清掉。GitHub Pages 只給 10 分鐘快取，沒有它每次回訪都要重新驗證每個檔。
- `docs/assets/report.js`：未捕捉錯誤、未處理的 Promise 拒絕、資源與資料檔載入失敗 → 備品庫存 Worker `clientlog`（D1 表 `client_log`；本機 mock 記到 `tools/auth/mock_log.jsonl`）。只在登入後送，每次載入最多 8 筆。查看：見 `tools/stock/README.md`。

## 結構（`git ls-files`，2026-09-26；2026-10-10 補上 P&ID 圖面位置這一輪新增的檔——commit 之前它們還是未追蹤檔；資料密文略）

```
.github/workflows/check.yml     push／PR 時在 GitHub 跑 verify_encrypted（密語用 Actions secret AMS_WEB_KEY）
.gitignore                      擋明文資料、密語／備份／匯入檔、pkl／sqlite、測試輸出
.gitattributes                  只有一條 *.bin binary：密文不做換行轉換、不做文字 diff／merge（2026-10-10）
CONTRACT.md                     資料契約（extractor ⇄ 前端；card aux、加密、備品庫存、SW 都在這）
README.md                       本檔
docs/                           GitHub Pages 根目錄（主站＝20260910 匯出檔）
  index.html                    主站單頁 App 殼（CSP、版本戳、preload；stamp_assets.py 改寫）
  404.html  .nojekyll  robots.txt  version.json   GitHub Pages 相關；robots Disallow 全站；version.json 供開著的分頁偵測新版
  auth-config.json              登入閘門端點（Apps Script 網址、工作階段時數）；endpoint 空＝關閉
  sw.js                         Service Worker（兩站共用）：?v= 檔快取優先、keep 清單清舊版
  assets/boot.js                最早載入：主題、字級等啟動前設定
  assets/auth.js                登入閘門（員工代號 → Apps Script）、離線快取設定、登出
  assets/report.js              前端錯誤回報 → Worker clientlog
  assets/core.js                共用：資料載入／解密／分塊、位號索引與查詢解析、自動完成、工具函式；查詢卡影像（圖控畫面、P&ID 圖紙）的 blob 載入與釋放
  assets/table.js               table 模式（虛擬捲動、篩選、facet、CSV、分塊漸進／部分載入）
  assets/grid.js                grid 模式（版面頁、Chart.js 圖表）
  assets/card.js                02 設備查詢卡（摘要、來源、比對旗標、文件連結、參數現值；圖控 HMI 畫面與 P&ID 圖紙的影像、標記、燈箱）
  assets/stock.js               備品庫存（卡片內備品組、#/stock/ 總表、領取／放入視窗）
  assets/app.js                 路由、側欄、版本偵測、SW 註冊與 keep、啟動流程
  assets/app.css                全站樣式（淺色／深色）
  assets/chart.umd.min.js       Chart.js 4（vendored）
  assets/icon-180.png  og.png   圖示與分享預覽圖
  data/meta.json                主站唯一明文：加密參數（salt、iter）與 build；其餘 *.json.bin 為 AES-GCM 密文
  db/index.html                 db 站（20260912 完整資料庫）App 殼；extract_db.stamp 改寫（含 <!-- ams-preload --> 區塊）
  db/stock-config.json          備品庫存 Worker 端點；空＝功能隱藏
  db/version.json  db/data/meta.json   同主站（db 站的密文另有 card/index、card/aux-NN 分塊、card/hmi/ 圖控畫面影像、card/pid/ P&ID 圖紙影像）
tools/extract.py                主站產生器：xlsx → docs/data（結尾加密＋戳記）
tools/verify_data.py            主站獨立對帳：xlsx vs docs/data
tools/amsx/                     公式（formula.py）、條件式格式（cf.py）、圖表（charts.py）、table／grid／card 轉換器
tools/amsx_common.py            兩個產生器共用的儲存格／日期格式化
tools/encrypt_data.py           明文 ⇄ 密文（AES-256-GCM；密語與 salt 在 web.key）；內容沒變的檔沿用 git HEAD 的密文、金鑰不是已發布的那一把就封完停下、中斷後可收拾
tools/verify_encrypted.py       兩站密文驗證：可解、無明文、引用一致、build 一致、無本機路徑；push 前必 0 錯誤
tools/rotate_passphrase.py      密語輪替一條指令（解密→重加密→戳記→驗證→寫 key 檔→印 STOCK_TOKEN；失敗回滾）
tools/stamp_assets.py           主站版本戳（assets ?v=、<meta ams-build>、preload、version.json）
tools/hooks/pre-commit          commit 時擋機密檔與明文資料（git config core.hooksPath tools/hooks 啟用）
tools/auth/Code.gs              登入閘門 Apps Script（Users／AMS_Log 分頁、節流）
tools/auth/README.md            登入閘門部署、本機測試、離職／停權 SOP
tools/auth/mock_server.py       本機靜態＋mock 登入＋mock 備品伺服器（E2E 用）
tools/auth/mock_users.csv       測試用員工代號
tools/db/paths.py               repo 外路徑的唯一來源（AmsDb.sqlite、cardwork、pdftotext 快取、文件庫、前簿 xlsx、build 目錄、圖控 Screens、P&ID 的 pid.json／pid_shots／pidtext／pidocr 與 repo 內的 pid_ocr_map.json）
tools/db/install.sh             一次：WSL 裝 SQL Server 2025 Express＋sqlcmd＋pyodbc（sa 密碼寫 /root/.ams_sa_pw）
tools/db/restore.sh             每份備份：.ams_bckup → RESTORE → export_to_sqlite.py ＋ fix_blobs.py → AmsDb.sqlite
tools/db/export_to_sqlite.py    WSL 內：SQL Server 全表 → SQLite（含 _schema／_tables／_modules）
tools/db/fix_blobs.py           WSL 內：BlockData／NamedConfigData 的 varbinary 重倒＋索引
tools/db/order.json             工作表順序、摘要、來源說明（已定案，make_order.py 不必重跑）
tools/db/make_order.py          從 workflow_results.json 產 order.json（歷史工具）
tools/db/sheets_*.py            八個領域模組（alerts／devices／events／index／misc／modules／params／security／templates）：SQLite → DataFrame 工作表
tools/db/build_workbook.py      組 Excel 主簿＋明細簿，寫 sheets_cache.pkl／sheets_final.pkl
tools/db/extract_db.py          db 站產生器：sheets_final.pkl → docs/db/data（manifest、sheets、02 查詢卡規格；結尾加密＋戳記）
tools/db/card_ams_extra.py      cardwork/ams.json：AMS DB 補充（同步、DCS 寫入、FF 診斷、版次、警報）
tools/db/docmap_terminal.py     cardwork/terminal.json：DCS 端子表（IMI01-A0001 xlsx／pdf）
tools/db/docmap_instlist.py     cardwork/instlist.json：儀器清單
tools/db/docmap_eomr.py         cardwork/eomr.json：出廠證書 EOMR（pdftotext）
tools/db/docmap_docindex.py     cardwork/docindex.json：文件索引（PDF 前幾頁提位號）
tools/db/docmap_docsearch.py    cardwork/docsearch.json：hst-docsearch FTS 全文檢索命中與推定值
tools/db/drive_map.py           %LOCALAPPDATA%\AMS\drive_map.json：文件庫相對路徑 → Google 雲端硬碟檔案 ID
tools/db/hmi_runtime_map.py     tools/db/hmi_runtime_map.json（進 repo）：Screens\圖控\*.xlsx 的執行時截圖 → .cim 畫面＋選單機組（離線跑，要 rapidocr）
tools/db/hmi_shots.py           cardwork/hmi_shots/：執行時截圖（逐選單機組）＋圖控 .cim 的 ThumbNail（設計時 EMF）→ 1280 寬 webp＋index.json
tools/db/hmi_nav.py             cardwork/hmi_nav.json：圖控畫面的選單路徑、標題、畫面變數（逐列對齊）
tools/db/hmi_index.py           cardwork/hmi.json：位號 → 圖控畫面＋畫面上的 0~1 座標（物件參照／畫面變數／點位索引／控制器 display_screen）
tools/db/pid_lib.py             P&ID 圖面定位的共用函式庫（沒有 main）：文件集（現場走訪、圖號家族、只留最高版次）、轉正角 R 與座標換算、圖框分區、文字層快取、位號比對規則與四張宣告表
tools/db/pid_index.py           cardwork/pid.json：現行 AMS 位號 → 哪一份 P&ID、PDF 第幾頁、轉正後圖上的 0~1 框（文字層＋pid_ocr_map.json）；--verify 疊框圖、--worklist OCR 工作清單、--trace 追查旁檔
tools/db/pid_shots.py           cardwork/pid_shots/：pid.json 引用到的圖紙 → 轉正後整張圖的四階灰階無損 webp＋index.json
tools/db/pid_ocr.py             離線 OCR（要 rapidocr；不在重建流程裡）：逐頁快取 %LOCALAPPDATA%\AMS\pidocr\ → --distill 蒸餾成 pid_ocr_map.json
tools/db/pid_ocr_map.json       OCR 對照表（進 repo；807 頁、OCR 原文與字框，不預先對 AMS）：pid_index 只讀它，重建流程不跑 OCR
tools/db/build_card_aux.py      docs/db/data/card/*.json：五份 cardwork＋dcdas 索引＋docsearch＋drive_map＋hmi＋pid → 查詢卡附加資料、DCS 比對、圖控畫面位置與縮圖、P&ID 圖面位置與圖紙影像（--recompare 只重算）
tools/db/patch_site_spec.py     把 extract_db 的 02／13 規格改動套到已發布資料
tools/db/rebuild.py             一鍵：--recompare 流程（含圖控 HMI 三步、P&ID 兩步；--skip-hmi／--skip-pid）、--only-stamp、--e2e、--sqlite 一條龍、--only-pneuvalve
tools/db/pneuvalve_site.py      氣動閥清單（試算表 xlsx）→ 57～61 分頁、02.json valve、00 目錄（自行解密／加密）
tools/db/pneuvalve_keys.py      氣動閥清單每列可搜尋的識別碼（GE 舊位號、去機組核心、Mark VIe 器件名、GE KKS、附件位號）→ valve.index／valve.list
tools/stock/README.md           備品庫存部署、匯入、本機測試、D1 額度
tools/stock/worker/src/index.js Cloudflare Worker API（list／logs／txn／clientlog；D1）
tools/stock/worker/schema.sql   D1 表：items、ledger、txns、client_log、revoked
tools/stock/worker/wrangler.toml  Worker 名稱、D1 綁定、ALLOWED_ORIGINS（機密另用 wrangler secret）
tools/stock/worker/.dev.vars.example  本機 wrangler dev 的機密範本
tools/stock/worker/package.json  wrangler 與 d1:* 指令
tools/stock/contracts_to_inventory.py  採購規範 .docx → items 匯入 SQL／min_qty SQL／CSV
tools/stock/print_token.py      印 STOCK_TOKEN（密語＋salt 導出）
tools/stock/mock_stock.py  mock_inventory.json   本機備品後端替身與假資料
tools/stock/Code.gs             試算表版替代後端
tools/tests/run_e2e.py          端對端入口（起 mock 伺服器、給 mock 真的 stockToken、跑 test_*.py）
tools/tests/e2e_common.py       開瀏覽器、登入、輸入密語、載入卡片
tools/tests/test_auth.py  test_card.py  test_stock.py  test_sw.py  test_main.py  test_pneuvalve.py   各測試模組（涵蓋見「端對端測試」）
tools/tests/test_pid_wording.py P&ID 建置端的文案與關卡（build_card_aux 的 pid_*）：合成資料、不開瀏覽器、不碰資料目錄；可單獨跑
```

### repo 外的檔案（建置機器；遺失後果與重建方式）

| 路徑 | 由誰產生 | 用途 | 遺失後果 | 重建 |
|---|---|---|---|---|
| `%LOCALAPPDATA%\AMS\web.key` | 首次 `encrypt_data.py`（第 2 行 salt 自動產生） | 密語＋salt；所有加密／驗證／E2E 都讀它 | **無法重建資料、無法驗證、E2E 全掛；密語沒人記得＝資料要重新產生並全員換密語**。只少了第 2 行（salt）：下一次加密會自己產生新 salt 寫回去——金鑰因此不是已發布的那一把，`encrypt_data.py` 封完之後以 exit 1 停下並印出已發布的 salt | 從密碼管理器還原**兩行**（密語＋salt；salt 也公開在 `docs/*/data/meta.json` 的 `kdf.salt`，照抄到第 2 行即可）；或 `rotate_passphrase.py` 換新（要重新產生兩站資料時才不需要舊密語） |
| `%LOCALAPPDATA%\AMS\AmsDb.sqlite` | `tools/db/restore.sh` | 所有 sheets_*.py、card_ams_extra、docmap_eomr 的資料來源 | 不能重跑 Excel／網站資料，只能用 `--recompare` 繞 | `restore.sh <備份> <輸出>`（10 分鐘）；本機沒有時 `paths.py` 自動改讀文件庫的備份副本 `<LIBRARY_ROOT>\AMS\20260912_AMS資料庫解析_工作檔\AmsDb.sqlite`（20260912、已 fix_blobs；只讀） |
| `PNEUVALVE_XLSX`（預設 `~\.claude\skills\notebooklm-batch5-Research\data\興達全廠氣動閥LIST_v2.6.xlsx`） | 試算表匯出／fill26 build_v26.py | 氣動閥清單 57～61 與查詢卡氣動閥組 | `pneuvalve_site` 中止（rebuild 可 `--skip-pneuvalve`，但氣動閥分頁會消失） | rclone 從試算表匯出（README「氣動閥清單」） |
| `%LOCALAPPDATA%\AMS\cardwork\pneuvalve_xwalk.json` | 2026-10-02 對照驗證（副本在 fill26/pneuvalve_ams_xwalk.json） | 氣動閥 ↔ AMS 對照覆寫（剔除／補對／備註） | 只剩自動規則：少 2 組 GE 90LT 對照、查詢卡少驗證備註 | 從 fill26 副本複製回來 |
| `%LOCALAPPDATA%\AMS\build\sheets_cache.pkl`、`sheets_final.pkl` | `build_workbook.py` | 模組結果快取；`sheets_final.pkl`＝extract_db 的輸入 | 只能 `--recompare`／`patch_site_spec` 繞，資料層退化 | 重跑 `build_workbook.py`（10 分鐘） |
| `%LOCALAPPDATA%\AMS\cardwork\*.json` | 五個產生器＋docmap_docsearch | build_card_aux 完整建置的輸入 | 只能 `--recompare`：儀器清單／EOMR 量程不再列入比對 | `rebuild.py --sqlite`（需文件庫） |
| `%LOCALAPPDATA%\AMS\cardwork\hmi.json`、`hmi_nav.json`、`hmi_shots\` | `hmi_index.py`／`hmi_nav.py`／`hmi_shots.py`（讀 `AMS_HMI_SCREENS` 的 .cim，唯讀不修改） | 查詢卡「圖控 HMI 畫面位置」與畫面縮圖 | 查詢卡少掉圖控畫面區段（build_card_aux 會以非 0 中止提醒，除非給 `--no-hmi`） | `py tools/db/hmi_shots.py && py tools/db/hmi_nav.py && py tools/db/hmi_index.py`（需圖控 Screens 目錄） |
| `%LOCALAPPDATA%\AMS\cardwork\pid.json`、`pid_shots\` | `pid_index.py`／`pid_shots.py`（讀 `LIBRARY_ROOT` 的 P&ID PDF，唯讀不修改） | 查詢卡「P&ID 圖面位置」與圖紙影像（0.5 MB＋117 張 webp 10.5 MB） | `rebuild.py` 預設每次都重做這兩步，所以不見了無妨；直接跑 `build_card_aux` 而缺 `pid.json`、缺 `pid_shots\index.json`、缺任何一張被引用的圖紙或兩者不同步時以非 0 中止（除非給 `--no-pid` 沿用上次發布的） | `py tools/db/pid_index.py && py tools/db/pid_shots.py`（約 20 秒，需文件庫） |
| `%LOCALAPPDATA%\AMS\pidtext\` | `pid_index.py`（`pid_lib.ensure_text`） | 每份 P&ID PDF 的文字層字框快取（712 檔 14 MB；依檔案大小＋修改時間，PDF 一變就自動重抽那一份） | 下一次 `pid_index` 全部重抽（整支約 17 秒，平常約 10 秒） | 自動 |
| `%LOCALAPPDATA%\AMS\pidocr\` | `pid_ocr.py`（離線，要 rapidocr） | 逐頁 OCR 原始結果（807 檔 25 MB）；`--distill` 由它產生 `tools/db/pid_ocr_map.json` | 已 commit 的對照表照常可用，重建不受影響；但之後要重新蒸餾（圖換版、蒸餾規則改了）就得先全部重跑 OCR——**不可在快取不全時跑 `--distill`**，它只寫有快取的頁 | `py tools/db/pid_ocr.py --scope all --max-minutes 7 --workers 8 --threads 1` 重複到「待做 0」（2026-10-08 實測 807 頁約 20 分鐘） |
| `%LOCALAPPDATA%\AMS\pidverify\` | `pid_index.py --verify <位號…>` | 人工讀圖核對用的疊框圖（整張＋放大） | 無妨 | 再跑一次 `--verify` |
| `%LOCALAPPDATA%\AMS\pdftxt\` | docmap_eomr／docmap_docindex | pdftotext 純文字快取 | 重抽一次（數小時） | 自動 |
| `%LOCALAPPDATA%\AMS\drive_map.json` | `drive_map.py`（讀 Google 雲端硬碟桌面版中繼資料庫） | 文件 → Drive 檔案 ID | 查詢卡所有 Drive 連結消失（build_card_aux 會以非 0 中止提醒） | `py tools/db/drive_map.py`（需已登入的 Drive 桌面版） |
| `%LOCALAPPDATA%\dcdas\index.sqlite` | signal-atlas repo `py tools\dcdas.py build` | 控制器 I/O 組態（DCS 比對基準第一順位） | 「控制器組態」區段與基準消失（build_card_aux 以非 0 中止提醒） | 在 signal-atlas 重建（需 ToolboxST checkout 匯出） |
| `~/hst_docsearch/hst_fts.db`＋`~/.claude/skills/hst-docsearch/config.json` | hst-docsearch skill | 全文檢索索引與文件庫根目錄設定 | 「文件全文檢索」區段消失（同上中止提醒） | 依 hst-docsearch skill 重建（數小時） |
| 工程文件庫 `<LIBRARY_ROOT>`（Google 雲端硬碟桌面版「@@新機組資料備份」） | Drive 同步 | docmap_* 的原始文件、P&ID PDF（`pid_index` 每次現場走訪）、前簿 `AMS\20260910_AMS解析.xlsx` | 產生器全部不能跑（P&ID 可 `rebuild.py --skip-pid` 沿用 cardwork 裡上次的 `pid.json`／`pid_shots`） | 重新同步 Drive（注意：重新同步若改了 PDF 的修改時間，OCR 對照表裡那幾份會被當成過期，見「P&ID 圖面位置」的表） |
| WSL `/root/.ams_sa_pw` | `tools/db/install.sh` | SQL Server sa 密碼 | restore.sh 跑不了 | 刪掉重跑 install.sh（會重設 sa 密碼） |
| `tools/stock/worker/.dev.vars`、`tools/stock/*.csv`、`worker/import*.sql` | 手動／contracts_to_inventory | 本機 Worker 機密、真實庫存匯入檔 | 本機 wrangler dev 跑不了；線上 D1 不受影響 | 照 tools/stock/README 重做 |

### 線上服務清單

| 服務 | 名稱／位置 | 設定在 | 機密 | 改了要做 |
|---|---|---|---|---|
| GitHub Pages | `momobacon-wq/AMS`，`main:/docs` → https://momobacon-wq.github.io/AMS/（主站）、`/AMS/db/`（db 站） | repo Settings → Pages | — | push 後最多 10 分鐘生效；`.github/workflows/check.yml` 每次 push 跑 verify_encrypted |
| GitHub Actions secret | `AMS_WEB_KEY`（＝web.key 第 1 行） | repo Settings → Secrets and variables → Actions | 密語 | 密語輪替後改 |
| 登入閘門 | Apps Script 網頁應用程式（`tools/auth/Code.gs`，綁在試算表「物料管理系統 的副本」：Users／AMS_Log 分頁） | 網址在 `docs/auth-config.json` `endpoint` | 指令碼屬性 `AUTH_SECRET`（HMAC） | 改 Code.gs 要「管理部署作業 → 新版本」；改 Users 分頁不用部署 |
| 備品庫存 Worker | Cloudflare Workers `ams-stock` → https://ams-stock.momobaconno1.workers.dev | `tools/stock/worker/wrangler.toml`；網址在 `docs/db/stock-config.json` | `AUTH_SECRET`（同閘門）、`STOCK_TOKEN`（`print_token.py`）：`npx wrangler secret put` | `npx wrangler deploy`；密語輪替後重貼 STOCK_TOKEN |
| D1 資料庫 | `ams-stock`（`database_id` 在 wrangler.toml；表 items／ledger／txns／client_log／revoked） | `schema.sql` | — | `npx wrangler d1 execute ams-stock --remote --file …`；免費額度見 tools/stock/README |
| Google 雲端硬碟 | 工程文件庫「@@新機組資料備份」（根資料夾 ID 在 `drive_map.py`） | — | 同事需有該資料夾檢視權限才能開卡片內的文件連結 | — |
| CSP 允許的主機 | `script.google.com`、`script.googleusercontent.com`、`ams-stock.momobaconno1.workers.dev` | 兩站 `index.html` `<meta http-equiv="Content-Security-Policy">` `connect-src` | — | 換 Worker 子網域或閘門端點時同步改 |
| 試算表版替代後端（未啟用） | 「物料管理系統」＋`tools/stock/Code.gs` | 指令碼屬性 `INVENTORY_SS_ID`／`USERS_SS_ID`／`AUTH_SECRET`／`STOCK_TOKEN` | 同上 | 見 tools/stock/README |
