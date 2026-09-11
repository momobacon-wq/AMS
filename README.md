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

## 資料更新

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
