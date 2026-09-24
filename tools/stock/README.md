# 備品庫存（倉庫試算表「物料管理系統」＋ Apps Script API）

查詢卡「一目了然」多一組「備品庫存（倉庫）」：以儀器清單「完整型號碼」／EOMR「出廠型號」對照倉庫料號，列出可直接替換（本體型號相同）與同系列的備品數量、儲位，並可直接領取／放入（自動帶入位號 KKS）。
`#/stock/` 是備品庫存總表：搜尋、購物車批次領取／放入、紀錄查詢／匯出 CSV、反查可安裝的位號。只在 `docs/db/` 站啟用（`docs/db/stock-config.json` 有 endpoint 且已登入）。

- 資料：Google 試算表「物料管理系統」（同事在用的 Transmitter 網站後端）。**A–F 欄意義不變**（PartNumber, Name, Brand, Spec, Location, Quantity），Transmitter 照常可用；
  本案把 A 改為正式料號 CR…、B 改為完整型號，並加 G Protocol、H Family、I Contract、J ContractQty、K MinQty、L Note。
- 紀錄：同一份試算表 Logs 分頁（最新在第 2 列），A–F 同 Transmitter，加 G EmployeeName、H KKS、I Note、J WorkOrder、K Source、L TxnId。
  ActionType：`OUT` 領取、`IN` 放入、`STOCKTAKE` 盤點、`IMPORT` 重建匯入（Transmitter 的 CHECK_IN/OUT、BATCH_IN/OUT 也會出現在紀錄裡）。
- 後端：`Code.gs`（獨立 Apps Script 專案，不碰 Transmitter 綁定的那支）。寫入要同時有 AMS 登入 token（同登入閘門的 HMAC）與 `STOCK_TOKEN`（由站台密語導出），
  領取時整批驗證（料號存在、不可扣成負數）、先寫紀錄再改數量、`txnId` 重送不重扣。
- 前端：`docs/assets/stock.js`（`AMS.Stock`、`AMS.StockView`）；查詢卡接點在 `card.js` `renderSummary`／`stockCtx`；路由與側欄在 `app.js`。

## 一次性：把合約品項匯入試算表

```bash
py tools/stock/contracts_to_inventory.py 合約A.docx 合約B.docx --current 現行Inventory.csv --out inventory_import.csv
```
`--current` 是目前 Inventory 分頁匯出的 CSV（列序＝合約順序），數量取現行值（已扣領用）並列出與合約不同的列供確認。輸出 `inventory_import.csv`（A–L 欄；不進 repo）。

1. 試算表新增分頁 **Import**，把 `inventory_import.csv` 整個貼上（含表頭，A1 開始）。
2. Apps Script 編輯器執行 `setup()`（補 Inventory／Logs 的 G–L 表頭與格式），再執行 `migrateFromImport()`：
   舊 Inventory 先複製成 `Inventory_backup_日期`，Inventory 改成 Import 的內容，Logs 每個料號寫一列 `IMPORT`。
3. 確認無誤後可刪 Import 分頁（備份分頁建議留著）。

## 部署 Apps Script（一次，約 5 分鐘）

1. https://script.google.com → 新專案（名稱如「AMS 備品庫存」）→ 把 `Code.gs` 內容貼上取代預設 → 專案設定：時區 Asia/Taipei。
2. 專案設定 → 指令碼屬性，新增四個：
   | 屬性 | 值 |
   |---|---|
   | `INVENTORY_SS_ID` | 「物料管理系統」試算表網址中 `/d/` 與 `/edit` 之間的 ID |
   | `USERS_SS_ID` | 「物料管理系統 的副本」（登入閘門用的 Users 分頁）的 ID |
   | `AUTH_SECRET` | 登入閘門專案（tools/auth/Code.gs）指令碼屬性裡的 `AUTH_SECRET`，整段複製 |
   | `STOCK_TOKEN` | `py tools/stock/print_token.py` 印出的 64 字元 |
3. 執行一次 `setup()`（會要求授權：選帳號 → 進階 → 前往專案 → 允許），再依上一節匯入。
4. 部署 → 新增部署作業 → 網頁應用程式 → 執行身分「**我**」、誰可以存取「**所有人**」→ 部署 → 複製網址（`…/exec`）。
5. 網址填到 `docs/db/stock-config.json` 的 `endpoint` → `py tools/stamp_assets.py docs`、`extract_db.stamp`（見 README「資料加密」）→ `py tools/verify_encrypted.py` → push。
6. 驗證：瀏覽器開 `…/exec` 應回 `{"ok":true,"service":"ams-stock"}`；網站登入＋密語後，查詢卡出現「備品庫存（倉庫）」、側欄出現「備品庫存」。
7. 之後改 `Code.gs` 要「部署 → 管理部署作業 → 編輯 → 版本：新版本 → 部署」，網址不變。

換密語（或 salt）時：`print_token.py` 重新印出 → 更新 `STOCK_TOKEN`。`auditBalances()` 可由紀錄重算數量並與現值比對（結果在執行紀錄）。

## 本機測試（不用部署）

```bash
py tools/auth/mock_server.py 8766 docs      # /mock-stock：tools/stock/mock_stock.py（假資料 mock_inventory.json；狀態與紀錄檔不進 repo）
# 開 http://127.0.0.1:8766/db/ → 900001 登入 → 密語 → 查詢 D01062（3051CD3A02B1…，同型號）／D01088（同系列）／#/stock/
# POST /mock-stock-reset 回到 seed
```

## 已知限制

- Transmitter 的綁定式腳本與本 API 各自有 LockService，兩邊「同一秒」同時出入庫時可能互相覆蓋數量；Logs 是附加式，可用 `auditBalances()` 對帳。
- 對照只到「本體型號」（Rosemount 前 12 碼／E+H `+` 前段）；選項碼（防爆、顯示器、接頭…）不比對，同系列列表一律要人工確認量程、輸出與製程接口。
- AMS 資料庫的型號只有家族名（3051、644…），沒有工程文件型號碼的設備只能列同系列。
