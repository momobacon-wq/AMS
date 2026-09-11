# AMS 解析網頁 — 資料契約（extractor ⇄ front-end）

來源：`C:\Users\bacon\我的雲端硬碟\@@新機組資料備份\AMS\20260910_AMS解析.xlsx`（28 張工作表；Google Sheet `20260910_AMS解析.gsheet` 是它的轉檔，內容相同）。
輸出：GitHub 公開 repo `momobacon-wq/AMS`，GitHub Pages 從 `main:/docs` 發佈。

```
C:\Users\bacon\AMS\
  CONTRACT.md            ← 本檔
  tools/extract.py       ← py tools/extract.py <xlsx> docs/data   （可重跑；純 Python + openpyxl）
  tools/verify_data.py   ← 獨立對帳：xlsx vs docs/data（列數、抽樣儲存格、連結、公式值）
  docs/index.html        ← 單頁 App（vanilla JS，無 build step）
  docs/assets/app.js, app.css, chart.umd.min.js（Chart.js 4.x，vendored）
  docs/data/manifest.json
  docs/data/sheets/<id>.json            ← 一般工作表
  docs/data/sheets/<id>-<nnn>.json      ← 大表分塊（21、22，以及任何 > 8 MB 的表）
```

## 關鍵事實（extractor 必須處理）

1. **活頁簿沒有公式快取值**（由 openpyxl 產生）。`data_only=True` 讀到的公式儲存格全是 None。
   必須以 `data_only=False` 讀，並自行求值。全部公式樣式目錄見 scratchpad `dump/formula_patterns.json`（338 種）。
   - `=HYPERLINK("#'<sheet>'!A<row>", <label>)` → 連結儲存格，顯示 label（label 可能是數字，如 01_摘要 的 KPI 1928）。
   - `=HYPERLINK("#'03_設備總表'!A"&MATCH("D01760",'03_設備總表'!$B:$B,0),"↗")` → 在 extract 時就把 MATCH 解成列號。
   - `=IFERROR(HYPERLINK(...MATCH(...)...),"（無）")` → 找不到時輸出純文字 "（無）"。
   - 其他真公式（COUNTIF、INDEX/MATCH、COUNTA、SUMPRODUCT、IF…）→ 在 Python 內求值成最終值。02_設備查詢卡 例外（見下）。
   - **假公式**：以 `=` 開頭但不是函式呼叫的字串（如 `=G12HAD6`、`= 某設備 DM.current_tag_raw`、`=1 (Off)（計數…）`）是**原樣文字**，保留含 `=` 的原字串。判定：`^=\s*[A-Z][A-Z0-9.]*\(` 才是真公式。
2. 多數資料表：第 1 列標題、第 2 列說明、第 3 列欄位群組色帶（可能合併）、第 4 列欄名、第 5 列起資料；有 autofilter。
3. 01_摘要 有 7 張原生圖表、16_時間軸 有 1 張（xl/charts/chart1..8.xml，資料來自 14_統計表 的 T01…T13 命名範圍等）。網頁要用 Chart.js 重畫，不可遺漏。

## v2 修訂（依 9 份分析規格 scratchpad/specs/*.md；與上文衝突時以本節為準）

- **圖表**：01_摘要 有 6 張（chart1–6 = C1–C6），16_時間軸 有 2 張（chart7 = C7 @M3、chart8 = C8 @I43；資料來自 16 本身）。錨點全是 oneCellAnchor（from＋ext），`size_px:{w,h}` = EMU/9525；`to` 依欄寬列高推算（見 specs/charts.md §4；chart spec 可加欄位：size_px、legend、axes{x,y,y2:{grid,min,max,step,fmt,title,position}}、data_labels{mode:value|percent,fmt}、hole、series[].colors（逐點）、series[].border、line_px、point_radius、cat_font_pt、reverse）。charts.md 已附解析後的實際數值，可直接對帳。
- **真公式判定**：`cell.data_type == 'f'`（XML `<f>`）；以 `=` 開頭的 inlineStr 是原樣文字。
- **表格標題區實際版面**（03–13、15、19–23、25–27 共用）：第 1 列 = A1 `⌂ 目錄` 連結＋B1 標題（合併）＋I1（或 D1…）說明（以 `｜` 切成 notes）；第 2 列 = 群組色帶 bands；第 3 列 = 各欄來源欄位註記（灰 8pt）→ `columns[].note`；第 4 列 = 欄名；第 5 列起資料。以各 spec 為準。
- **日期時間字串**：依儲存格 number_format 輸出。含 `.000` → `YYYY-MM-DD HH:MM:SS.fff`；`yyyy-mm-dd` → `YYYY-MM-DD`；`yyyy-mm-dd hh:mm` → `YYYY-MM-DD HH:MM`；其他日期時間 → `YYYY-MM-DD HH:MM:SS`（**四捨五入到秒**，同 Excel 顯示）。extract 與 verify 共用同一 helper（`tools/amsx_common.py`）。
- **樣式字串**擴充：`"flags|bg|fc"`，flags 可含 `b`（粗）`i`（斜）`u`（底線）。欄層級：`columns[].bold/italic/bg/fc/hidden`。優先序：cell_styles > row_styles > 欄層級。
- **條件式格式**：openpyxl 不會套用；extract 必須解析 sheet XML `<conditionalFormatting>` 與 styles.xml `<dxfs>`，依 Excel 規則（priority、stopIfTrue、逐屬性第一個成立者）在 Python 內求值，**實體化**到 row_styles / cell_styles（grid 則寫入 cell 的 `s`）。色階 → 計算出的 bg；資料橫條 → grid cell 加 `"bar": {"p": 0.0–1.0, "c": "#638EC6"}`，table cell 以 `bars: [[r,c,p,color]]` 稀疏陣列。
- **grid**：`h` = round(pt×4/3) px，只給 customHeight 列，其餘 `null`＝自動高度。style 物件擴充：`bd`（`{"t":"thin #BFBFBF","l":"thick #BF8F00",...}`）、`mono`（等寬）、`sz`（pt）。sheet 層級 `gridlines: bool`。**溢出**：未換行文字右側為空且無樣式的鄰格時，cell 給 `"ov": N`（可向右溢出 N 格），front-end 以 colspan 渲染。
- **連結 r 解析**需全活頁簿 mode 表（two-pass）：目標為 grid → Excel 列號；table → 列號 − 5（< 5 則 null）；card → null。
- **大表分塊**：21、22 每塊約 25,000 列，**對齊設備區塊**（同一 alias 不跨塊）。manifest 該表加 `"part_offsets": [0, 25012, ...]`。所有指向它們的連結 `r` 為**全域** 0-based 索引。
- **table 附屬區塊**：若表格工作表另有摘要小表（如 09），用 `"subgrid": {grid 物件}` ＋ `"subgrid_pos": "above|below"`。
- **card**：02.json 依 specs/02.md（含 `rules` 條件格式擴充）；另外預算 `link_index: {alias: {"08": [r0, n], "10": [r0, n], "07": [...], "06": [...], "11": [...], "12": [...]}}`，讓查詢卡不必載入大表就能顯示筆數。
- **CSV 匯出**：以 `=`、`+`、`-`、`@` 開頭的值加前綴 `'`。
- 數字存成文字者（'@' 格式）一律維持字串；front-end 排序用自然排序。
- JSON 以緊湊格式輸出（`separators=(',',':')`, `ensure_ascii=False`），UTF-8。

### v2.1（資料整合補充）
- **樣式疊層可逐屬性合併**：欄層級 → row_styles → cell_styles，每層只能「設定」屬性、不能取消；因此 row/欄層級絕不帶有其涵蓋儲存格所沒有的屬性（例：12 的灰字 CF 只套 B:AJ，A 欄不灰，故該列不用 row_style）。整格取代（cell_style 即完整樣式）也同樣正確。
- `columns[].align` 可為 `null`：該欄在 Excel 是 General 且值型別混雜，由前端逐值對齊（數字靠右、布林置中、文字靠左），與 Excel 相同。純日期欄（JSON 為字串）一律 `right`。
- grid style 可含 `shrink: 1`（Excel shrinkToFit，01 KPI 數字；目前字已放得下，前端可忽略）。
- grid `col_widths` 會延伸到 max_col 右側 3 欄內有明確寬度的邊界欄（01 Z 寬 2）。

### v2.2（UI 整合：前端如何解讀既有欄位）
- 資料橫條 `bar.p` / `bars[..p..]` / `columns[].bar`：前端畫成 **10% + 80%·p** 的格寬（Excel 無 x14 擴充的 dataBar 預設 minLength 10、maxLength 90）。
- `ui.sort_key {顯示欄: 鍵欄}`（10 時間(台灣)→UTC 原值欄）、`ui.presets`（08 快速篩選按鈕：`nonempty`→`!∅`、`eq`→`=值`）、`ui.summary_rows`（15 小計／總計：排序時固定在最後、不計入 facet 筆數）皆已由 table.js 使用。
- chart 可選欄位 `gap`（Excel gapWidth，預設 150）：柱寬 categoryPercentage = n／(n＋gap/100)。圖例依 series 順序。
- 顯示色：前端在「字比底暗且對比 < 3:1」時把字色往黑色調整到 3:1（Excel 淡灰字 #A6A6A6 疊在條件式底色上），JSON 色值不變。

## manifest.json

```json
{
  "workbook": {"title": "...", "subtitle": "...", "source": "20260910.ams_merge", "built": "2026-09-11 15:14", "xlsx": "20260910_AMS解析.xlsx"},
  "sheets": [
    {"id": "03", "name": "03_設備總表", "short": "設備總表", "group": "設備", "mode": "table",
     "rows": 1928, "cols": 120, "desc": "第 2 列說明文字", "files": ["sheets/03.json"], "bytes": 1234567}
  ],
  "search": {"index_sheet": "05", "key_col": 0, "alias_col": 4}
}
```
`mode` ∈ `table` | `grid` | `card`。`files` 相對於 `docs/data/`。分塊表：`files` 依序列出所有塊；每塊 `rows` 為該塊資料；front-end 依序載入並顯示進度。

## 共同儲存格表示法（table 與 grid 都用）

- 純值：`string` | `number` | `null`（空）| `true/false`。日期時間一律輸出字串 `YYYY-MM-DD HH:MM:SS`（或原本就是字串者照舊）。
- 連結：`{"t": <顯示文字或數字>, "l": {"s": "03", "r": <目標>}}`
  - table 模式目標表：`r` = **0-based 資料列索引**（Excel 列號 − 資料首列）。目標為標題區（列 < 資料首列）時 `r` = null（跳到表頭）。
  - grid 模式目標表：`r` = **Excel 列號**（1-based）。
  - 外部 URL：`{"t": "...", "u": "https://..."}`。
- 帶數字格式：欄層級 `fmt` 優先；個別儲存格需要不同格式時用 `{"v": 0.9898, "f": "0.0%"}`。
- fmt 字串用 Excel 原格式碼（如 `0.0%`、`#,##0`、`0.00`、`yyyy-mm-dd`），front-end 實作常見子集：General、0、0.0…、#,##0、#,##0.0…、0%、0.0%、0.00%、日期碼。

## mode = "table"

```json
{
  "id": "03", "name": "03_設備總表", "mode": "table",
  "title": "第 1 列主標題", "notes": ["第 2 列…", "..."],
  "header_cells": [{"c": 18, "v": "高", "s": 3}],      // 標題區(1–3 列)其他零散儲存格（如 07 的 COUNTIF 統計），可省略
  "bands": [{"label": "1 識別", "from": 0, "to": 7, "bg": "#1F4E79", "fc": "#FFFFFF"}],
  "columns": [{"label": "位號", "fmt": null, "type": "text|num|date|link|bool", "w": 110, "align": "left", "bg": null, "note": "欄註解(可省略)"}],
  "freeze_cols": 2,
  "rows": [[...], ...],
  "styles": ["b|#FFC7CE|#9C0006", "..."],                // 樣式表：粗體旗標|底色|字色（空字串=無）
  "cell_styles": [[rowIdx, colIdx, styleIdx], ...],     // 稀疏；只記「與該欄預設不同」的有意義底色/字色
  "row_styles": [[rowIdx, styleIdx], ...],               // 整列一致時用這個比較省
  "ui": {"default_sort": null, "facets": [1, 5], "search_cols": null},
  "part": {"index": 0, "of": 1, "row_offset": 0}         // 分塊表才有
}
```
`w` 為 px（Excel 欄寬 × 7.5 取整，最小 40、最大 420）。

## mode = "grid"（版面型工作表：00、01、14、15、16、17、18、23、24… 由分析決定）

```json
{
  "id": "01", "name": "01_摘要", "mode": "grid",
  "col_widths": [60, 49, ...],            // px，index 0 = A 欄
  "rows": [{"r": 1, "h": 28, "cells": [{"c": 2, "v": "文字", "s": 5, "cs": 24, "rs": 1, "l": null, "f": null}]}],
  "styles": [{"b": 1, "i": 0, "u": 0, "bg": "#1F4E79", "fc": "#FFFFFF", "sz": 14, "ha": "center", "va": "middle", "wrap": 1, "bd": "thin"}],
  "sections": [{"r": 71, "label": "重點發現"}],       // 目錄/跳轉用（粗體標題列）
  "charts": [ {chart 規格，見下} ],
  "hidden_cols": [], "hidden_rows": []
}
```
`c` 為 1-based 欄號；合併儲存格只輸出左上角並給 `cs`/`rs`。空列可省略（front-end 以 `h` 預設 20px 補位或壓縮連續空列——但**圖表錨點區的空列不可壓縮**）。

### chart 規格
```json
{"id": "C1", "title": "C1 子機組 × 迴路類型（台，不含 I/O）", "type": "bar|line|pie|doughnut|area|combo",
 "horizontal": false, "stacked": false, "percent": false,
 "anchor": {"from": {"r": 14, "c": 2}, "to": {"r": 32, "c": 13}},   // 1-based Excel 列/欄
 "categories": ["GT11", "..."],
 "series": [{"name": "...", "values": [1, 2], "color": "#1F4E79", "type": "bar", "axis": "y"}],
 "y_title": null, "y2_title": null, "source": "'14_統計表'!$A$27:$L$37"}
```

## mode = "card"（02_設備查詢卡）

`docs/data/sheets/02.json`：
```json
{"id": "02", "name": "02_設備查詢卡", "mode": "card", "title": "...", "notes": ["..."], "default_query": "G11HAD60BT001",
 "sections": [{"label": "1. 識別", "fields": [{"label": "位號", "col": 0, "join": null, "blank_if_empty": true}]}],
 "links": [{"label": "→ 變更（有意義）", "sheet": "08", "match_col": 2, "count_mode": "prefix#", "count_col": 0}],
 "recent_changes": {"sheet": "08", "key_col": 0, "k_max": 10, "columns": [{"label": "時間(台灣)", "col": 6}], "join": [...]}}
```
`col` = 03_設備總表 的 0-based 欄索引（由 02 的 INDEX 公式反推，A=0）。查詢流程：輸入字串 → UPPER(TRIM(去除 `=`)) → 在 05_位號索引 第 A 欄精確比對（找不到→顯示「查無此字串」訊息）→ 取 E 欄 alias、H 欄對應設備數 → 在 03 B 欄找 alias → 取值。這些都在 front-end 以 JS 實作，資料來自 05、03、08 等 table JSON。

## front-end 必備功能

- 側欄：28 張表依群組列出（含列數），可收合；手機版變抽屜。頂部全域位號搜尋（走 05 索引 → 設備查詢卡）。
- table：虛擬捲動（固定列高）、凍結欄、欄位群組色帶、排序、全表關鍵字篩選、逐欄篩選、常用欄 facet 下拉、欄位顯示/隱藏、CSV 匯出（目前篩選結果）、點列開「列詳情」側板（全部欄位直列，手機友善）、連結儲存格可跳轉並高亮目標列、深連結 `#/s/03?r=12&q=...`。
- grid：忠實重現底色、字色、粗體、合併、欄寬、換行；圖表依錨點放在對應位置（或至少依序置於所在區段）；sections 目錄。
- card：查詢框＋自動完成（05 A 欄），多台對應提示，快速連結帶筆數，最近 10 筆有意義變更，並可展開該設備的 HART/FF 參數現值（依 03 的 DF/DG/DH 目標列懶載入對應分塊）。
- 淺色/深色主題、繁體中文 UI、載入進度、手機 400px 可用。
