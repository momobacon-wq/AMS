# 備品庫存（Cloudflare Worker + D1；前端 docs/assets/stock.js）

查詢卡「一目了然」多一組「備品庫存（倉庫）」：以儀器清單「完整型號碼」／EOMR「出廠型號」對照倉庫料號，列出同型號（本體型號相同）與同系列的備品數量、儲位，並可直接領取／放入（自動帶入位號 KKS、可填用途與工單號）。
`#/stock/` 是備品庫存總表：搜尋、購物車批次領取／放入、紀錄查詢／匯出 CSV、反查可安裝的位號。只在 `docs/db/` 站啟用（`docs/db/stock-config.json` 有 endpoint 且已登入）。

後端是 `worker/`（Cloudflare Workers + D1，免費方案、不用信用卡）：
- 免費額度：Workers 每天 10 萬次請求；D1 每天 500 萬列讀取、10 萬列寫入、共 5 GB。現況估算：88 個料號、每次 `list` 讀約 90 列、每筆領料寫 3 列，一天不到 1,000 列寫入，離額度很遠；用完當天 `txn` 會回 `transient`（伺服器暫時無法服務）。
- `worker/src/index.js`：API（list／logs／txn／clientlog），與 `Code.gs`（試算表版替代後端）同一套請求／回應格式；前端不分後端。盤點 `adjust` 已移除（見下方「數量調整」）。
- `worker/schema.sql`：`items`（料號、型號、數量…；`qty CHECK ≥ 0`、`min_qty` 安全存量）、`ledger`（每筆出入庫，只附加）、`txns`（同 txnId 重送不重扣）、`client_log`（前端錯誤回報）、`revoked`（停權黑名單）。改了 schema 要重跑 `npx wrangler d1 execute ams-stock --remote --file schema.sql`（可重複執行）。
- 寫入要同時有 AMS 登入 token（同登入閘門的 HMAC，密鑰 `AUTH_SECRET`）與 `STOCK_TOKEN`（由站台密語導出），且員工代號不在 `revoked`；只對 `ALLOWED_ORIGINS` 回 CORS。
- 限速：`wrangler.toml` 的 `[[ratelimits]]` binding `RL`（每 IP 每分鐘 60 次 POST，含未登入的請求），超過回 HTTP 429；`clientlog` 另有每人每分鐘 10 筆（超過丟棄、仍回 ok）。本機 `wrangler dev` 也會限速；沒有 binding 時 Worker 不限。
- 領取：整批驗證（料號存在、不可扣成負數）→ `DB.batch` 單一交易（寫 txns → 改數量 → 寫紀錄），任一失敗整批回滾。兩人搶最後一顆：慢的一方收到 `{stale:true, items:[{pn, qty}]}`，前端領取視窗就地把「現有 N」與上限改成現量、不關窗，調整數量後再按一次即可。
- 安全存量：`txn` 回應每項帶 `min`／`low`（寫入後 qty ≤ min_qty），前端 toast 加「⚠ 已低於安全存量…請通知採購」；`list` 回 `lowCount`，側欄「備品庫存」顯示徽章，`#/stock/` 進頁面時預選「低於安全存量」篩選。`min_qty` 由 `contracts_to_inventory.py --min-sql` 產生（見下）。
- 冪等：前端開領取／放入視窗時產生一次 `txnId`，同一視窗重按幾次都沿用；連線逾時（20 秒）或 fetch 失敗時提示「可能已寫入；再按一次會以同一交易編號重送，不會重扣」，後端對同一 `txnId` 回 `replay:true`，toast 加註「先前已寫入，未重扣」。`mock_stock.py` 同樣回 `replay`（記憶體＋紀錄檔）。
- 伺服器錯誤一律回固定文案「伺服器暫時無法服務，請稍後再試」，D1 原文只在 Worker 紀錄（`npx wrangler tail`）。
- 紀錄：`logs` 接受 `since`／`until`（ISO UTC）與 `before`（ledger id 游標），單次 300 列；前端紀錄分頁有日期區間、「載入更多」與「匯出區間全部」（一頁頁抓完再組 CSV），庫存分頁有「匯出庫存 CSV」（今天的庫存快照）。

## 一次性：合約 → 匯入 SQL

```bash
py tools/stock/contracts_to_inventory.py 合約A.docx 合約B.docx --current 現行Inventory.csv --sql import.sql [--out inventory_import.csv]
```
- 解析採購規範 .docx 的「料號 CR…／型號／測量範圍／數量」；`--qty contract`（預設）數量以合約為準，`--current` 只用來帶儲位並列出差異。
- `import.sql`＝`items` INSERT ＋ 每料號一列 `ledger` `IMPORT`；真實檔不進 repo（`worker/.gitignore`）。`--out` 另出 CSV 給試算表參考。
- 安全存量：`--min-rule quarter`（預設）＝ max(1, ceil(合約數量 × 0.25))，寫進 INSERT 的 `min_qty` 與 CSV 的 MinQty；`--min-rule none` 留空。

### 已上線的 D1 補安全存量（目前 88 項 `min_qty` 全 NULL）

```bash
py tools/stock/contracts_to_inventory.py 合約A.docx 合約B.docx --min-sql tools/stock/worker/min_qty.sql     # 只產 UPDATE，不撞 INSERT 主鍵
cd tools/stock/worker && npx wrangler d1 execute ams-stock --remote --file min_qty.sql
```
- 只更新 `min_qty IS NULL` 的列，手動用 `UPDATE items SET min_qty = …` 調過的不會被覆蓋；要重算全部就把 SQL 裡的 `AND min_qty IS NULL` 拿掉。
- 個別料號：`npx wrangler d1 execute ams-stock --remote --command "UPDATE items SET min_qty = 2 WHERE pn = 'CR262002843'"`。

## 部署（一次，約 10 分鐘；指令都在 `tools/stock/worker/` 目錄下執行）

1. 註冊 Cloudflare 帳號：https://dash.cloudflare.com/sign-up（Free 方案，不用信用卡）。
2. `npm install`（裝 wrangler）→ `npx wrangler login`（開瀏覽器按「Allow」）。
3. `npx wrangler d1 create ams-stock` → 把印出的 `database_id = "…"` 貼到 `wrangler.toml` 取代 `REPLACE_WITH_ID_FROM_wrangler_d1_create`。
4. 建表與匯入：`npx wrangler d1 execute ams-stock --remote --file schema.sql` → `npx wrangler d1 execute ams-stock --remote --file import.sql`。
5. 機密：`npx wrangler secret put AUTH_SECRET`（貼登入閘門 Apps Script「專案設定 → 指令碼屬性」的 `AUTH_SECRET`）、`npx wrangler secret put STOCK_TOKEN`（貼 `py tools/stock/print_token.py` 的輸出）。
6. `npx wrangler deploy` → 印出 `https://ams-stock.<子網域>.workers.dev`；瀏覽器開它應回 `{"ok":true,"service":"ams-stock","backend":"d1"}`。
7. 網址填到 `docs/db/stock-config.json` 的 `endpoint` → `py tools/stamp_assets.py docs`、`extract_db.stamp`（見根 README「資料加密」）→ `py tools/verify_encrypted.py` → push。
   `docs/db/index.html` CSP `connect-src` 已含 `https://*.workers.dev`。
8. 之後改 `src/index.js` 只要 `npx wrangler deploy`；換密語 → 用根目錄的 `py tools/rotate_passphrase.py`（結尾直接印新 token）或重跑 `print_token.py`，再 `npx wrangler secret put STOCK_TOKEN`（忘了的話 E2E `test_stock` 會以「未授權」抓到）。

常用查詢（`npm run d1:status`／`npm run d1:ledger`，或）：
```bash
npx wrangler d1 execute ams-stock --remote --command "SELECT pn, model, qty, loc FROM items WHERE qty <= COALESCE(min_qty, 0)"      # 缺貨／低於安全存量
npx wrangler d1 execute ams-stock --remote --command "SELECT * FROM ledger WHERE kks = 'G11HAD60BT001' ORDER BY id DESC"          # 某位號紀錄
npx wrangler d1 execute ams-stock --remote --json --command "SELECT * FROM ledger ORDER BY id" > ledger.json                        # 全部紀錄匯出
npx wrangler d1 execute ams-stock --remote --command "UPDATE items SET loc = 'A-01', min_qty = 2 WHERE pn = 'CR262002843'"         # 改儲位／安全存量
npx wrangler d1 execute ams-stock --remote --command "SELECT ts, emp_id, site, kind, msg, page, build FROM client_log ORDER BY id DESC LIMIT 50"  # 前端錯誤回報（docs/assets/report.js）
```
Cloudflare 儀表板（Workers & Pages → D1 → ams-stock）也能直接看表、下 SQL。

### 數量調整（盤點）：一律同時寫一筆 ledger

儲位、安全存量、備註可以直接 `UPDATE items`；**數量不要只改 `items.qty`**（紀錄會對不上、`auditBalances` 式的對帳就失效），一律用下面的兩句一起跑（`--command` 可放多句）：
```bash
npx wrangler d1 execute ams-stock --remote --command "
UPDATE items SET qty = 7, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE pn = 'CR262002843';
INSERT INTO ledger (ts, emp_id, emp_name, action, pn, delta, balance, kks, note, wo, source, txn_id)
  SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now'), '900001', '倉管', 'STOCKTAKE', pn, 7 - (SELECT balance FROM ledger WHERE pn = items.pn ORDER BY id DESC LIMIT 1), qty, '', '盤點：實盤 7', '', 'ams-stock', ''
  FROM items WHERE pn = 'CR262002843';"
```
- `7` 換成實盤數量、`'900001'`／`'倉管'` 換成盤點人；`delta`＝新數量 − 上一筆紀錄的結餘（沒有紀錄時為 NULL，可手動填）。前端紀錄分頁會顯示為「盤點」。
- Windows 終端機把中文塞進 `--command` 可能變亂碼（cp950）：中文備註改存成 UTF-8 的 `.sql` 檔用 `--file` 跑，或備註用英數。
- API 的 `adjust` 動作已移除（它沒有畫面、沒有角色限制、不記原因；任何持 token 的人都能 curl 改數）。

### 停權／離職 SOP（Worker 端即時生效）

```bash
npx wrangler d1 execute ams-stock --remote --command "INSERT OR IGNORE INTO revoked VALUES ('900123', datetime('now'))"   # 停權：立刻不能領料、也不能寫 client_log
npx wrangler d1 execute ams-stock --remote --command "DELETE FROM revoked WHERE emp_id = '900123'"                        # 復權
npx wrangler d1 execute ams-stock --remote --command "SELECT * FROM revoked ORDER BY ts DESC"                              # 目前停權名單
```
1. 登入閘門的 Google Sheet `Users` 分頁刪掉該列（之後不能再登入、resume 也會被擋）。
2. 上面的 `INSERT INTO revoked`（員工代號不含前導 0；手上未過期的 12 小時 token 從此對 Worker 無效）。
3. 若要切斷**資料瀏覽**（`.bin` 是公開靜態檔，記得密語的人仍能開）：只能輪換站台密語（根 README「資料加密」→ 重新加密 → `print_token.py` → `npx wrangler secret put STOCK_TOKEN` → deploy），全員要重輸密語。

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
