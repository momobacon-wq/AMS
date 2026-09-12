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

## 資料更新（20260910 匯出檔資料集）

```bash
# 需要 Python 3 + openpyxl
py tools/extract.py "<路徑>/20260910_AMS解析.xlsx" docs/data     # 約 25 秒，會先清掉舊輸出
py tools/verify_data.py "<路徑>/20260910_AMS解析.xlsx" docs/data # 逐格對帳，0 錯誤才 exit 0
```

- 活頁簿由 openpyxl 產生、沒有公式快取值，`tools/amsx/formula.py` 自行計算所有公式（HYPERLINK、MATCH、INDEX、COUNTIF、SUMPRODUCT…）；`tools/amsx/cf.py` 計算條件式格式。
- `tools/verify_data.py` 是獨立寫成的對帳程式（不引用 extractor 程式碼），比對每一格的值、每一個連結的目標、圖表數值與條件式格式。
- 資料格式說明見 [CONTRACT.md](CONTRACT.md)。

## 結構

```
docs/                 GitHub Pages 根目錄
  index.html
  assets/             core.js / table.js / grid.js / card.js / app.js / app.css / chart.umd.min.js
  data/manifest.json
  data/sheets/*.json  每張表一檔；21、22 依設備區塊切塊
tools/                extract.py、verify_data.py、amsx/（公式與條件式格式引擎）
```
