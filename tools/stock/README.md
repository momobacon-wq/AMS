# 備品庫存（Cloudflare Worker + D1；前端 docs/assets/stock.js）

查詢卡「一目了然」多一組「備品庫存（倉庫）」：以儀器清單「完整型號碼」／EOMR「出廠型號」對照倉庫料號，列出同型號（本體型號相同）與同系列的備品數量、儲位，並可直接領取／放入（自動帶入位號 KKS、可填用途與工單號）。
`#/stock/` 是備品庫存總表：搜尋、購物車批次領取／放入、紀錄查詢／匯出 CSV、反查可安裝的位號。只在 `docs/db/` 站啟用（`docs/db/stock-config.json` 有 endpoint 且已登入）。

後端是 `worker/`（Cloudflare Workers + D1，免費方案：每天 10 萬次請求、5 GB，不用信用卡）：
- `worker/src/index.js`：API（list／logs／txn／adjust），與 `Code.gs`（試算表版替代後端）同一套請求／回應格式；前端不分後端。
- `worker/schema.sql`：`items`（料號、型號、數量…；`qty CHECK ≥ 0`）、`ledger`（每筆出入庫，只附加）、`txns`（同 txnId 重送不重扣）。
- 寫入要同時有 AMS 登入 token（同登入閘門的 HMAC，密鑰 `AUTH_SECRET`）與 `STOCK_TOKEN`（由站台密語導出）；只對 `ALLOWED_ORIGINS` 回 CORS。
- 領取：整批驗證（料號存在、不可扣成負數）→ `DB.batch` 單一交易（寫 txns → 改數量 → 寫紀錄），任一失敗整批回滾。

## 一次性：合約 → 匯入 SQL

```bash
py tools/stock/contracts_to_inventory.py 合約A.docx 合約B.docx --current 現行Inventory.csv --sql import.sql [--out inventory_import.csv]
```
- 解析採購規範 .docx 的「料號 CR…／型號／測量範圍／數量」；`--qty contract`（預設）數量以合約為準，`--current` 只用來帶儲位並列出差異。
- `import.sql`＝`items` INSERT ＋ 每料號一列 `ledger` `IMPORT`；真實檔不進 repo（`worker/.gitignore`）。`--out` 另出 CSV 給試算表參考。

## 部署（一次，約 10 分鐘；指令都在 `tools/stock/worker/` 目錄下執行）

1. 註冊 Cloudflare 帳號：https://dash.cloudflare.com/sign-up（Free 方案，不用信用卡）。
2. `npm install`（裝 wrangler）→ `npx wrangler login`（開瀏覽器按「Allow」）。
3. `npx wrangler d1 create ams-stock` → 把印出的 `database_id = "…"` 貼到 `wrangler.toml` 取代 `REPLACE_WITH_ID_FROM_wrangler_d1_create`。
4. 建表與匯入：`npx wrangler d1 execute ams-stock --remote --file schema.sql` → `npx wrangler d1 execute ams-stock --remote --file import.sql`。
5. 機密：`npx wrangler secret put AUTH_SECRET`（貼登入閘門 Apps Script「專案設定 → 指令碼屬性」的 `AUTH_SECRET`）、`npx wrangler secret put STOCK_TOKEN`（貼 `py tools/stock/print_token.py` 的輸出）。
6. `npx wrangler deploy` → 印出 `https://ams-stock.<子網域>.workers.dev`；瀏覽器開它應回 `{"ok":true,"service":"ams-stock","backend":"d1"}`。
7. 網址填到 `docs/db/stock-config.json` 的 `endpoint` → `py tools/stamp_assets.py docs`、`extract_db.stamp`（見根 README「資料加密」）→ `py tools/verify_encrypted.py` → push。
   `docs/db/index.html` CSP `connect-src` 已含 `https://*.workers.dev`。
8. 之後改 `src/index.js` 只要 `npx wrangler deploy`；換密語 → 重跑 `print_token.py` 並 `npx wrangler secret put STOCK_TOKEN`。

常用查詢（`npm run d1:status`／`npm run d1:ledger`，或）：
```bash
npx wrangler d1 execute ams-stock --remote --command "SELECT pn, model, qty, loc FROM items WHERE qty <= COALESCE(min_qty, 0)"      # 缺貨／低於安全存量
npx wrangler d1 execute ams-stock --remote --command "SELECT * FROM ledger WHERE kks = 'G11HAD60BT001' ORDER BY id DESC"          # 某位號紀錄
npx wrangler d1 execute ams-stock --remote --json --command "SELECT * FROM ledger ORDER BY id" > ledger.json                        # 全部紀錄匯出
npx wrangler d1 execute ams-stock --remote --command "UPDATE items SET loc = 'A-01', min_qty = 2 WHERE pn = 'CR262002843'"         # 改儲位／安全存量
```
Cloudflare 儀表板（Workers & Pages → D1 → ams-stock）也能直接看表、下 SQL。

## 本機測試（不用部署；真 Worker＋假登入）

```bash
cd tools/stock/worker && npm install
copy .dev.vars.example .dev.vars           # STOCK_TOKEN 填 py tools/stock/print_token.py 的輸出；AUTH_SECRET=mock-secret（mock 登入用的密鑰）
py ../contracts_to_inventory.py --from-json ../mock_inventory.json --sql mock_import.sql
npx wrangler d1 execute ams-stock --local --file schema.sql && npx wrangler d1 execute ams-stock --local --file mock_import.sql
npx wrangler dev --port 8787               # 本機 Worker（本機 D1 在 .wrangler/）
# 另一個視窗：
set AMS_STOCK_ENDPOINT=http://127.0.0.1:8787 && py tools/auth/mock_server.py 8766 docs
# 開 http://127.0.0.1:8766/db/ → 900001 登入 → 密語 → 查 D01062（同型號）／D01088（同系列）／#/stock/
```
不設 `AMS_STOCK_ENDPOINT` 時 mock_server 改用 `/mock-stock`（`mock_stock.py`，純 Python 替身，不需 wrangler）。

## 替代後端：試算表「物料管理系統」＋ Apps Script（`Code.gs`）

同一套 API 格式；適合想讓同事直接在試算表看／改數量、且 Transmitter 網站共用同一份資料的情況。部署：新 Apps Script 專案貼 `Code.gs`，指令碼屬性 `INVENTORY_SS_ID`／`USERS_SS_ID`／`AUTH_SECRET`／`STOCK_TOKEN`，執行 `setup()`，`contracts_to_inventory.py --out` 的 CSV 貼到「Import」分頁後執行 `migrateFromImport()`，部署為網頁應用程式（執行身分「我」、存取「所有人」）。限制：與 Transmitter 的綁定式腳本沒有共同鎖，同一秒同時出入庫可能互相覆蓋（`auditBalances()` 可對帳）。

## 已知限制

- 對照只到「本體型號」（Rosemount 前 12 碼／E+H `+` 前段）；選項碼（防爆、顯示器、接頭…）不比對，同系列列表一律要人工確認量程、輸出與製程接口。
- AMS 資料庫的型號只有家族名（3051、644…），沒有工程文件型號碼的設備只能列同系列。
- Transmitter 網站仍指向試算表，與 D1 各自獨立；舊 Logs 歷史留在試算表（舊 12 碼料號對不回 CR 料號）。
