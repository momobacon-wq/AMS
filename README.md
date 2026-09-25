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

### 重建

```bash
# 1. 還原備份並倒出 SQLite（WSL Ubuntu 內，見 tools/db/install_mssql.sh、export_to_sqlite.py、fix_blobs.py）
# 2. 產出 Excel（sheets_*.py 每個領域一個模組；sheets_cache.pkl 快取模組結果）
py tools/db/make_order.py                      # 產生 order.json（工作表順序、摘要、來源說明）
py tools/db/build_workbook.py tools/db/order.json 主簿.xlsx 明細.xlsx 120000   # 也寫出 sheets_final.pkl
# 3. 網站資料（與 Excel 同一份後處理結果）
py tools/db/extract_db.py tools/db/sheets_final.pkl docs/db/data          # 寫 manifest / sheets，並戳記 docs/db/index.html、version.json
py tools/stamp_assets.py docs                                             # 前端程式有改時，主站也重新戳記
```

## 資料加密（兩站；push 前必做）

`docs/*/data` 只發布密文：每個 JSON 以 AES-256-GCM 加密成 `<檔名>.bin`，金鑰由密語經 PBKDF2 導出，瀏覽器在登入後輸入密語解密（作法同 signal-atlas，細節見 [CONTRACT.md](CONTRACT.md)「加密與封裝」）。密語放在 `%LOCALAPPDATA%\AMS\web.key`（第 1 行；第 2 行是固定 salt，首次執行自動產生），不在 repo 裡。

```bash
py tools/encrypt_data.py docs/data              # 產生器已自動做；手動把明文目錄轉成 .bin + meta.json
py tools/encrypt_data.py docs/db/data
py tools/stamp_assets.py docs                   # 加密後重新戳記（build 讀 meta.json）
py -c "import sys; sys.path.insert(0,'tools/db'); import extract_db; extract_db.stamp('docs/db','docs/assets')"
py tools/verify_encrypted.py                    # 兩站重新解密驗證；0 錯誤才可 push（密語也可用環境變數 AMS_WEB_KEY 給）
py tools/encrypt_data.py docs/db/data --decrypt # 要重跑 build_card_aux / verify_data 時先還原明文（結尾會再加密）
```

只重建查詢卡附加資料：`encrypt_data.py --decrypt` → `build_card_aux.py`（結尾自動加密＋戳記）→ `verify_encrypted.py`。
DCS 比對的基準會讀 signal-atlas 的控制器索引 `%LOCALAPPDATA%\dcdas\index.sqlite`（在 signal-atlas repo 跑 `py tools\dcdas.py build` 產生；沒有就只用 DCS 寫入／端子表）。
各產生器輸出（cardwork）不在手邊時：`py tools/db/build_card_aux.py --recompare docs/db/data` 只重算 DCS 比對（並換入 docsearch、補 Drive 連結）；`py tools/db/patch_site_spec.py docs/db/data` 把 02/13 表規格改動套到已發布資料（要先解密）。

查詢卡的「文件全文檢索」與 Google 雲端硬碟連結（2026-09-24 起）：

```bash
py tools/db/rebuild.py            # 一鍵：下面五步按順序跑，任一步失敗就停（明文會先加密回去）；--spec 多跑 patch_site_spec、--skip-docsearch／--skip-drive-map 省時間、--only-stamp 只改了前端、--e2e 最後多跑端對端測試

# rebuild.py 等價的手動步驟
py tools/db/drive_map.py                                   # Google 雲端硬碟桌面版中繼資料 → %LOCALAPPDATA%\AMS\drive_map.json（文件庫相對路徑 → 檔案 ID）
py tools/encrypt_data.py docs/db/data --decrypt
py tools/db/docmap_docsearch.py --data docs/db/data         # hst-docsearch 的 FTS 索引（~/.claude/skills/hst-docsearch/config.json）以位號＋AMS 序號搜全庫 → %LOCALAPPDATA%\AMS\cardwork\docsearch.json（約 4 分鐘）
py tools/db/patch_site_spec.py docs/db/data                 # 02.json 摘要／區段規格（只在 extract_db 規格有改時）
py tools/db/build_card_aux.py --recompare docs/db/data      # 併入 sec.docsearch、index.docs 補 url、重算比對、加密、戳記
py tools/stamp_assets.py docs && py tools/verify_encrypted.py
```

摘要空白的欄位（設計廠牌／型號、出廠型號／序號、設計量程、P&ID／邏輯圖／Hook-up／位置圖）會依序改用文件索引、全文檢索命中的推定值；所有文件來源的數值都可點開雲端硬碟的那份檔案（需有該資料夾的 Drive 權限）。
`extract.py`／`extract_db.py` 的 `--no-encrypt` 只供本機測試，明文輸出不可 push（`.gitignore` 也擋著）。

### push 前關卡

```bash
git config core.hooksPath tools/hooks             # 一次（只影響本機）：commit 時擋機密檔（web.key／.dev.vars／.ams_bckup／.ams_sa_pw／庫存 csv／import*.sql）與 docs/*/data 明文 .json
py tools/db/rebuild.py --only-stamp --e2e         # 每次 push 前：兩站戳記 → verify_encrypted → run_e2e（端對端）→ 印 git status --short docs/；exit 0 才 push
```
GitHub 端另有 `.github/workflows/check.yml`：每次 push／PR 在 ubuntu 上跑 `tools/verify_encrypted.py`，密語讀 repo 的 Actions secret `AMS_WEB_KEY`（值＝`web.key` 第一行；沒設定就直接失敗，不會靜默通過）。

## 備品庫存（docs/db 站）

查詢卡「一目了然」最後一組「備品庫存（倉庫）」：以儀器清單／EOMR 的完整型號碼對照倉庫料號，列出同型號／同系列的備品數量與儲位，可直接領取／放入（自動帶入位號、可填用途與工單號）；`#/stock/` 是庫存總表（搜尋、購物車批次、紀錄匯出、反查可安裝位號）。
後端是 Cloudflare Worker + D1（`tools/stock/worker/`，免費方案）；寫入需要登入 token＋由密語導出的 `STOCK_TOKEN`。部署、合約匯入（`contracts_to_inventory.py`）與本機測試見 [tools/stock/README.md](tools/stock/README.md)；`docs/db/stock-config.json` 的 `endpoint` 留空時整個功能隱藏。試算表「物料管理系統」＋Apps Script（`tools/stock/Code.gs`）是同格式的替代後端。

## 登入閘門（員工代號）與登入紀錄

兩個網站共用 `docs/assets/auth.js`：開站先要求輸入員工代號，對照 Google 試算表的 **Users** 分頁（姓名由分頁帶出），登入／造訪／登出都寫進同一份試算表的 **AMS_Log** 分頁。驗證與寫入由綁在試算表上的 Apps Script 網頁應用程式（`tools/auth/Code.gs`）處理；部署步驟與本機測試方式見 [tools/auth/README.md](tools/auth/README.md)。`docs/auth-config.json` 的 `endpoint` 留空時閘門關閉。

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
```
密語與 `encrypt_data.py` 同一來源：環境變數 `AMS_WEB_KEY` → `AMS_WEB_KEY_FILE` 指向的檔 → `%LOCALAPPDATA%\AMS\web.key` 第一行；測試員工代號用 `tools/auth/mock_users.csv`。
涵蓋：登入閘門（錯代號、錯密語）、查詢卡（文件全文檢索收合組與 Google 雲端硬碟連結、DCS 不符旗標、查無位號的相近建議、上一頁同步查詢框、手機無橫向捲動）、Service Worker 快取、錯誤回報、console 零錯誤。截圖在 `tools/tests/out/`（不進 repo）。push 前統一跑 `py tools/db/rebuild.py --only-stamp --e2e`（戳記＋驗證＋這套測試）。

## 前端快取與錯誤回報

- `docs/sw.js`（Service Worker，兩站共用）：帶 `?v=` 的資料檔／程式檔快取優先（網址已含建置或內容雜湊），`version.json`／`auth-config.json`／`stock-config.json` 只走網路，其餘網路優先、離線用快取。頁面載入後把本站用到的版本值交給它，舊版本快取自動清掉。GitHub Pages 只給 10 分鐘快取，沒有它每次回訪都要重新驗證每個檔。
- `docs/assets/report.js`：未捕捉錯誤、未處理的 Promise 拒絕、資源與資料檔載入失敗 → 備品庫存 Worker `clientlog`（D1 表 `client_log`；本機 mock 記到 `tools/auth/mock_log.jsonl`）。只在登入後送，每次載入最多 8 筆。查看：見 `tools/stock/README.md`。

## 結構

```
docs/                 GitHub Pages 根目錄
  index.html
  assets/             core.js / table.js / grid.js / card.js / app.js / app.css / chart.umd.min.js
  data/meta.json      唯一明文（加密參數與 build）
  data/manifest.json.bin、data/sheets/*.json.bin  每張表一檔（AES-GCM 密文）；21、22 依設備區塊切塊
tools/                extract.py、verify_data.py、encrypt_data.py、verify_encrypted.py、amsx/（公式與條件式格式引擎）
tools/hooks/          pre-commit（git config core.hooksPath tools/hooks 啟用；擋機密檔與明文資料）
.github/workflows/    check.yml（push／PR 時在 GitHub 跑 verify_encrypted，密語用 secret AMS_WEB_KEY）
tools/stock/          備品庫存：worker/（Cloudflare Worker + D1：src/index.js、schema.sql、wrangler.toml）、contracts_to_inventory.py、print_token.py、mock_stock.py、Code.gs（試算表版替代後端）
```
