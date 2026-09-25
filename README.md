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

### 重建（拿到新的 .ams_bckup 時）

所有 repo 外的路徑只寫在 `tools/db/paths.py`（環境變數 `AMS_SQLITE`／`AMS_CARDWORK`／`AMS_PDFTXT_CACHE`／`AMS_LIBRARY_ROOT`／`AMS_PREV_XLSX`／`AMS_BUILD_DIR` 可覆寫；`py tools/db/paths.py` 印出目前解析到的每一個與是否存在）。`order.json` 已在 repo，`make_order.py` 不必重跑。

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
| 7. 戳記＋驗證 | `py tools/db/rebuild.py --only-stamp` | — | 兩站 `index.html`／`version.json`；`verify_encrypted` 0 錯誤 | 1 分 |
| 8. push 前 | `py tools/db/rebuild.py --only-stamp --e2e` | — | 端對端測試全綠 | 3 分 |

只改資料來源（docsearch／Drive 連結／比對規則）而沒有新備份時仍用 `py tools/db/rebuild.py`（`--recompare`，見下）；`rebuild.py --sqlite` 也接受 `--skip-workbook`（沿用 `sheets_final.pkl`）、`--skip-docsearch`、`--skip-drive-map`。

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

### 密語輪替

```bash
py tools/rotate_passphrase.py --dry-run   # 先看計畫：兩站狀態、key 檔、備份檔名
py tools/rotate_passphrase.py             # 新密語用 getpass 互動輸入兩次（不從命令列收）；--fresh-salt 連 salt 一起換
```
一條指令做完：舊密語（`web.key`）解出兩站明文副本 → 新密語重新加密 → 交換目錄 → 兩站戳記 → `verify_encrypted` 必須 0 錯誤 → 才改寫 `web.key`（舊檔另存 `web.key.bak-<日期時間>`）→ 印出新的 `STOCK_TOKEN`。任一步失敗就把舊密文換回來、key 檔不動；環境變數 `AMS_WEB_KEY` 有設時拒絕執行（否則寫了 key 檔也沒效）。
輪替後要跟著做：(1) `cd tools/stock/worker && npx wrangler secret put STOCK_TOKEN` 貼印出的值（忘了會使領取／放入全部回「未授權（密語不符）」；E2E 的 `test_stock` 用同一算法比對，抓得到）、本機 `.dev.vars` 也改；(2) GitHub Actions secret `AMS_WEB_KEY` 改成新密語；(3) `py tools/tests/run_e2e.py` → push；(4) 通知同事新密語——舊的「記住此裝置」金鑰開站時驗不過 `meta.check` 會自動改問密語，不必逐台清；`--fresh-salt` 時所有人都要重輸。

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
```
密語與 `encrypt_data.py` 同一來源：環境變數 `AMS_WEB_KEY` → `AMS_WEB_KEY_FILE` 指向的檔 → `%LOCALAPPDATA%\AMS\web.key` 第一行；測試員工代號用 `tools/auth/mock_users.csv`。
涵蓋：登入閘門（錯代號、錯密語）、查詢卡（文件全文檢索收合組與 Google 雲端硬碟連結、DCS 不符旗標、查無位號的相近建議、上一頁同步查詢框、手機無橫向捲動）、備品庫存（`test_stock`：卡片領取 1 顆、位號自動帶入 → `#/stock/` 數量 −1 → 紀錄有位號；錯的 `stockToken` 回「未授權」——mock 以 `AMS_MOCK_STOCK_TOKEN`（`run_e2e` 用密語＋salt 算出，與 Worker 的 `STOCK_TOKEN` 同算法）比對，密語輪替後忘了換 Worker 的 secret 在這裡就會露餡）、版本橫幅與 Service Worker（`test_sw`：假 `version.json`＋時鐘快轉 6 分鐘 → 「資料已更新」；植入舊版本快取 → 重載後被 keep 清單刪掉、另一站的 `data/` 不動）、舊站（`test_main`：`#/s/03?q=GT11` 有列與 facet 下拉、01 六張圖表、點連結儲存格 → `?r=` 且目標列高亮、手機無橫向捲動）、錯誤回報、console 零錯誤。截圖在 `tools/tests/out/`（不進 repo）。push 前統一跑 `py tools/db/rebuild.py --only-stamp --e2e`（戳記＋驗證＋這套測試）。

## 前端快取與錯誤回報

- `docs/sw.js`（Service Worker，兩站共用）：帶 `?v=` 的資料檔／程式檔快取優先（網址已含建置或內容雜湊），`version.json`／`auth-config.json`／`stock-config.json` 只走網路，其餘網路優先、離線用快取。頁面載入後把本站用到的版本值交給它，舊版本快取自動清掉。GitHub Pages 只給 10 分鐘快取，沒有它每次回訪都要重新驗證每個檔。
- `docs/assets/report.js`：未捕捉錯誤、未處理的 Promise 拒絕、資源與資料檔載入失敗 → 備品庫存 Worker `clientlog`（D1 表 `client_log`；本機 mock 記到 `tools/auth/mock_log.jsonl`）。只在登入後送，每次載入最多 8 筆。查看：見 `tools/stock/README.md`。

## 結構（`git ls-files`，2026-09-26；資料密文略）

```
.github/workflows/check.yml     push／PR 時在 GitHub 跑 verify_encrypted（密語用 Actions secret AMS_WEB_KEY）
.gitignore                      擋明文資料、密語／備份／匯入檔、pkl／sqlite、測試輸出
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
  assets/core.js                共用：資料載入／解密／分塊、位號索引與查詢解析、自動完成、工具函式
  assets/table.js               table 模式（虛擬捲動、篩選、facet、CSV、分塊漸進／部分載入）
  assets/grid.js                grid 模式（版面頁、Chart.js 圖表）
  assets/card.js                02 設備查詢卡（摘要、來源、比對旗標、文件連結、參數現值）
  assets/stock.js               備品庫存（卡片內備品組、#/stock/ 總表、領取／放入視窗）
  assets/app.js                 路由、側欄、版本偵測、SW 註冊與 keep、啟動流程
  assets/app.css                全站樣式（淺色／深色）
  assets/chart.umd.min.js       Chart.js 4（vendored）
  assets/icon-180.png  og.png   圖示與分享預覽圖
  data/meta.json                主站唯一明文：加密參數（salt、iter）與 build；其餘 *.json.bin 為 AES-GCM 密文
  db/index.html                 db 站（20260912 完整資料庫）App 殼；extract_db.stamp 改寫（含 <!-- ams-preload --> 區塊）
  db/stock-config.json          備品庫存 Worker 端點；空＝功能隱藏
  db/version.json  db/data/meta.json   同主站
tools/extract.py                主站產生器：xlsx → docs/data（結尾加密＋戳記）
tools/verify_data.py            主站獨立對帳：xlsx vs docs/data
tools/amsx/                     公式（formula.py）、條件式格式（cf.py）、圖表（charts.py）、table／grid／card 轉換器
tools/amsx_common.py            兩個產生器共用的儲存格／日期格式化
tools/encrypt_data.py           明文 ⇄ 密文（AES-256-GCM；密語與 salt 在 web.key）
tools/verify_encrypted.py       兩站密文驗證：可解、無明文、引用一致、build 一致、無本機路徑；push 前必 0 錯誤
tools/rotate_passphrase.py      密語輪替一條指令（解密→重加密→戳記→驗證→寫 key 檔→印 STOCK_TOKEN；失敗回滾）
tools/stamp_assets.py           主站版本戳（assets ?v=、<meta ams-build>、preload、version.json）
tools/hooks/pre-commit          commit 時擋機密檔與明文資料（git config core.hooksPath tools/hooks 啟用）
tools/auth/Code.gs              登入閘門 Apps Script（Users／AMS_Log 分頁、節流）
tools/auth/README.md            登入閘門部署、本機測試、離職／停權 SOP
tools/auth/mock_server.py       本機靜態＋mock 登入＋mock 備品伺服器（E2E 用）
tools/auth/mock_users.csv       測試用員工代號
tools/db/paths.py               repo 外路徑的唯一來源（AmsDb.sqlite、cardwork、pdftotext 快取、文件庫、前簿 xlsx、build 目錄）
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
tools/db/build_card_aux.py      docs/db/data/card/*.json：五份 cardwork＋dcdas 索引＋docsearch＋drive_map → 查詢卡附加資料、DCS 比對（--recompare 只重算）
tools/db/patch_site_spec.py     把 extract_db 的 02／13 規格改動套到已發布資料
tools/db/rebuild.py             一鍵：--recompare 流程、--only-stamp、--e2e、--sqlite 一條龍
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
tools/tests/test_auth.py  test_card.py  test_stock.py  test_sw.py  test_main.py   各測試模組（涵蓋見「端對端測試」）
```

### repo 外的檔案（建置機器；遺失後果與重建方式）

| 路徑 | 由誰產生 | 用途 | 遺失後果 | 重建 |
|---|---|---|---|---|
| `%LOCALAPPDATA%\AMS\web.key` | 首次 `encrypt_data.py`（第 2 行 salt 自動產生） | 密語＋salt；所有加密／驗證／E2E 都讀它 | **無法重建資料、無法驗證、E2E 全掛；密語沒人記得＝資料要重新產生並全員換密語** | 從密碼管理器還原；或 `rotate_passphrase.py` 換新（要重新產生兩站資料時才不需要舊密語） |
| `%LOCALAPPDATA%\AMS\AmsDb.sqlite` | `tools/db/restore.sh` | 所有 sheets_*.py、card_ams_extra、docmap_eomr 的資料來源 | 不能重跑 Excel／網站資料，只能用 `--recompare` 繞 | `restore.sh <備份> <輸出>`（10 分鐘） |
| `%LOCALAPPDATA%\AMS\build\sheets_cache.pkl`、`sheets_final.pkl` | `build_workbook.py` | 模組結果快取；`sheets_final.pkl`＝extract_db 的輸入 | 只能 `--recompare`／`patch_site_spec` 繞，資料層退化 | 重跑 `build_workbook.py`（10 分鐘） |
| `%LOCALAPPDATA%\AMS\cardwork\*.json` | 五個產生器＋docmap_docsearch | build_card_aux 完整建置的輸入 | 只能 `--recompare`：儀器清單／EOMR 量程不再列入比對 | `rebuild.py --sqlite`（需文件庫） |
| `%LOCALAPPDATA%\AMS\pdftxt\` | docmap_eomr／docmap_docindex | pdftotext 純文字快取 | 重抽一次（數小時） | 自動 |
| `%LOCALAPPDATA%\AMS\drive_map.json` | `drive_map.py`（讀 Google 雲端硬碟桌面版中繼資料庫） | 文件 → Drive 檔案 ID | 查詢卡所有 Drive 連結消失（build_card_aux 會以非 0 中止提醒） | `py tools/db/drive_map.py`（需已登入的 Drive 桌面版） |
| `%LOCALAPPDATA%\dcdas\index.sqlite` | signal-atlas repo `py tools\dcdas.py build` | 控制器 I/O 組態（DCS 比對基準第一順位） | 「控制器組態」區段與基準消失（build_card_aux 以非 0 中止提醒） | 在 signal-atlas 重建（需 ToolboxST checkout 匯出） |
| `~/hst_docsearch/hst_fts.db`＋`~/.claude/skills/hst-docsearch/config.json` | hst-docsearch skill | 全文檢索索引與文件庫根目錄設定 | 「文件全文檢索」區段消失（同上中止提醒） | 依 hst-docsearch skill 重建（數小時） |
| 工程文件庫 `<LIBRARY_ROOT>`（Google 雲端硬碟桌面版「@@新機組資料備份」） | Drive 同步 | docmap_* 的原始文件、前簿 `AMS\20260910_AMS解析.xlsx` | 產生器全部不能跑 | 重新同步 Drive |
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
