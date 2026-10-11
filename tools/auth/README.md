# 登入閘門（員工代號）與登入紀錄

網站是 GitHub Pages 靜態站，沒有伺服器可以驗證帳號，所以把「對照 Users 分頁、寫入紀錄」交給綁定在 Google 試算表上的
Apps Script 網頁應用程式；前端（`docs/assets/auth.js`）在載入資料前先跟它確認。

- 使用者清單：試算表「物料管理系統 的副本」的 **Users** 分頁（`EMPLOYEE_ID`、`EMPLOYEE_NAME`）。改清單只要改分頁，不用重新部署。
- 登入紀錄：同一份試算表自動建立 **AMS_Log** 分頁：`Timestamp | EmployeeID | EmployeeName | ActionType | Site | Page | UserAgent`
  - `LOGIN` 登入成功、`LOGIN_FAIL` 代號不在清單、`LOGIN_BLOCKED` 同一代號 10 分鐘內失敗 ≥20 次、`VISIT` 沿用工作階段再次開站、`LOGOUT`
  - Site 分「AMS 匯出檔解析（20260910）」與「AMS 資料庫解析（20260912）」；Page 是開站時的 #/… 路徑
- 工作階段 12 小時（`SESSION_HOURS` 與 `docs/auth-config.json` 的 `sessionHours`）；token 是 HMAC 簽章，密鑰存在指令碼屬性。10 分鐘內（`auth.js` 的 `REVERIFY_MS`）驗證過的工作階段再開站不會重打端點（所以 VISIT 不會每次重新整理都記一筆）；超過就送 resume 重驗，已從 Users 分頁移除的代號在這一步被踢出。
- 比對規則：只憑員工代號（去空白、全形轉半形、去前導零）；姓名由 Users 分頁帶出，顯示在右上角並寫入紀錄。
- 枚舉節流（`Code.gs` 開頭的常數）：代號只有 6 位數字，所以除了「同一代號 10 分鐘內失敗 ≥20 次」之外，還有**全站**每分鐘登入嘗試 ≥30 次或失敗 ≥20 次就一律回「嘗試次數過多」（不查 Users、不寫紀錄，換代號也躲不掉）；`LOGIN_FAIL`／`LOGIN_BLOCKED` 每 10 分鐘最多寫 20 列，其餘只計數（避免有人把 AMS_Log 灌到試算表儲存格上限，讓正常人登不進）；每次失敗回應前延遲 1.5 秒。計數用 CacheService，重新部署或快取失效會歸零，作為節流足夠。
- 端點故障（5xx／逾時／Apps Script 內部錯誤）時，已登入者沿用快取工作階段放行；未登入者看到「無法連線」可重試。`docs/auth-config.json` 若存在但格式錯誤，網站會鎖住並顯示錯誤（避免手滑把站台打開）。
- 離線或讀不到 `auth-config.json`（斷網、hosts 擋掉、GitHub Pages 回 5xx）：`auth.js` 改用上次成功讀到、存在 localStorage `ams.authcfg` 的設定——有未過期的工作階段照常放行（Service Worker 讓已看過的資料離線可查），沒有就顯示「目前離線，無法登入」鎖住。只有設定檔 404 或 `endpoint` 留空才算閘門關閉（同時清掉快取設定）。第一次開站就離線（沒有快取設定）也鎖住。
- 登出會同時清掉工作階段與「記住此裝置」存的密語金鑰（localStorage `ams.key`），密語視窗的「記住此裝置」預設不勾——共用工作站上不會留下可解密的金鑰。
- 這是**軟性閘門**：只擋一般瀏覽並留下紀錄，不是資安防線。資料的真正保護是登入後的**密語**：`docs/*/data` 只發布 AES-256-GCM 密文，瀏覽器以密語解密（見 README「資料加密」與 CONTRACT.md「加密與封裝」）。

## 部署（一次，約 3 分鐘）

0. 試算表 檔案 → 設定 → 時區 設為 (GMT+08:00) 台北（AMS_Log 的時間依此顯示）。
1. 開啟試算表 → 擴充功能 → Apps Script，把 `Code.gs` 的內容貼進去（取代預設內容），存檔；左側「專案設定」的時區也設 Asia/Taipei。
2. 部署 → 新增部署作業 → 齒輪選「網頁應用程式」→ 說明隨意、執行身分「**我**」、誰可以存取「**所有人**」→ 部署。
   第一次會要求授權：選你的帳號 → 出現「Google 尚未驗證這個應用程式」→ 點「進階」→「前往 <專案名稱>（不安全）」→ 允許。
   存取權一定要是「所有人」；選「任何擁有 Google 帳戶的使用者」時瀏覽器會被導到 Google 登入頁，網站只會顯示「無法連線」。
3. 複製「網頁應用程式網址」（`https://script.google.com/macros/s/…/exec`），填到 `docs/auth-config.json` 的 `endpoint`，push 到 GitHub（GitHub Pages 的 CDN 最多約 10 分鐘後生效）。
   端點留空 = 閘門關閉，網站照舊。
4. 驗證：瀏覽器開 `…/exec` 應看到 `{"ok":true,"service":"ams-auth"}`；開網站應出現登入畫面，登入後 AMS_Log 多一列。
5. 之後修改 `Code.gs` 要「部署 → 管理部署作業 → 編輯 → 版本：新版本 → 部署」，網址不變。

## 離職／停權 SOP

三層各自獨立，要切斷什麼就做到哪一層（由淺到深）：

| 要切斷的能力 | 做法 | 生效時間 |
|---|---|---|
| 1. 再登入、開站留紀錄 | 試算表 **Users** 分頁刪掉該列（不用重新部署） | 立即擋新登入；手上未過期的工作階段（最長 12 小時）在下一次 resume 重驗（10 分鐘內驗證過的不重打）時被踢出；離線開站則沿用快取放行到工作階段到期 |
| 2. 備品庫存寫入（領料、盤點、錯誤回報） | Worker D1 的 `revoked` 表加一列：`npx wrangler d1 execute ams-stock --remote --command "INSERT OR IGNORE INTO revoked VALUES ('員工代號', datetime('now'))"`（詳見 `tools/stock/README.md`） | 立即；Worker 每次寫入都查表，不必等 token 過期 |
| 3. 瀏覽資料 | **只能輪換密語**：資料 `.bin` 是公開靜態檔，記得密語（或瀏覽器留著 `ams.key`）的人不受上面兩層影響。重新加密兩站（README「資料加密」）、重新部署 Worker 的 `STOCK_TOKEN`、把新密語發給留任同仁 | push 上線後；舊密語立刻失效 |

- 通常做 1＋2；承商離職、密語可能外流才做 3（會讓所有人重新輸入密語）。
- 想讓「所有人」立刻重新登入：Apps Script 專案設定 → 指令碼屬性 刪掉 `AUTH_SECRET`（下次執行自動重產）並 `npx wrangler secret put AUTH_SECRET` 同步到 Worker；這會作廢全部 token，不分人。
- 事後查：AMS_Log 篩 EmployeeID 看最後登入時間與站台；Worker `ledger`／`client_log` 依 `emp_id` 查寫入紀錄。

## 本機測試（不用部署）

```bash
py tools/auth/mock_server.py 8766        # 同時提供 docs/ 靜態檔與 /mock-auth（使用者見 mock_users.csv，紀錄寫 mock_log.jsonl）
# 開 http://127.0.0.1:8766/ 或 /db/ → 輸入 900001 登入（測試甲）
```
測試伺服器會把 `auth-config.json` 改指向 `/mock-auth`；`POST /mock-control {"down":true}` 可模擬端點故障、`{"slow":20}` 模擬逾時、`{"cfgdown":true}` 讓 `auth-config.json` 回 503（驗證離線改用快取設定）。mock 不做枚舉節流（那段只在 Code.gs）。
