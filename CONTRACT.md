# AMS 解析網頁 — 資料契約（extractor ⇄ front-end）

來源：`C:\Users\bacon\我的雲端硬碟\@@新機組資料備份\AMS\20260910_AMS解析.xlsx`（28 張工作表；Google Sheet `20260910_AMS解析.gsheet` 是它的轉檔，內容相同）。
輸出：GitHub 公開 repo `momobacon-wq/AMS`，GitHub Pages 從 `main:/docs` 發佈。

```
C:\Users\bacon\AMS\                      （完整的逐檔用途表見 README「結構」；repo 外檔案與線上服務也列在那裡）
  CONTRACT.md            ← 本檔
  README.md              ← 操作手冊：重建步驟表、加密／密語輪替、備品庫存、登入閘門、E2E、結構
  tools/extract.py       ← 主站產生器：py tools/extract.py <xlsx> docs/data（可重跑；純 Python + openpyxl；結尾加密＋戳記）
  tools/verify_data.py   ← 主站獨立對帳：xlsx vs docs/data（列數、抽樣儲存格、連結、公式值）
  tools/encrypt_data.py / verify_encrypted.py / rotate_passphrase.py / stamp_assets.py   ← 加密、驗證、密語輪替、版本戳（「加密與封裝」）
  tools/db/              ← db 站：paths.py（repo 外路徑唯一來源）、install.sh／restore.sh（WSL SQL Server → AmsDb.sqlite）、sheets_*.py＋build_workbook.py（Excel）、
                            extract_db.py（→ docs/db/data）、card_ams_extra／docmap_*／drive_map（cardwork）、hmi_*.py（圖控 HMI 畫面位置，v5）、
                            pid_lib／pid_index／pid_shots／pid_ocr.py＋pid_ocr_map.json（P&ID 圖面位置，v6）、build_card_aux.py（card aux）、rebuild.py（一鍵／--sqlite 一條龍）
  tools/auth/  tools/stock/  tools/tests/  tools/hooks/   ← 登入閘門、備品庫存 Worker、端對端測試、pre-commit（各節）
  docs/index.html        ← 主站單頁 App 殼（vanilla JS，無 build step）；docs/db/index.html ← db 站殼（同一套 assets）
  docs/assets/           ← boot / auth / report / core / table / grid / card / stock / app .js、app.css、chart.umd.min.js（Chart.js 4.x，vendored）
  docs/sw.js             ← Service Worker（兩站共用）
  docs/data/meta.json    ← 唯一明文（加密參數與 build）；其餘為密文：
  docs/data/manifest.json.bin
  docs/data/sheets/<id>.json.bin        ← 一般工作表
  docs/data/sheets/<id>-<nnn>.json.bin  ← 大表分塊（21、22，以及任何 > 8 MB 的表）
  docs/db/data/…                        ← 同上（第二資料集）＋ card/index.json.bin、card/aux-NN.json.bin（card aux）、card/hmi/*.json.bin（圖控畫面影像，v5）、card/pid/*.json.bin（P&ID 圖紙影像，v6）
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

### v2.3（快取版本與站內連結）
- `manifest.build`：所有輸出檔（sheets/*.json＋不含 build 的 manifest）的 sha256 前 10 碼，由 `tools/extract.py` 寫入（決定性，不含時間）。前端對每個資料檔請求加 `?v=<build>`（加密站是 `?v=<build><金鑰標記>`，見「加密與封裝」），同一分頁不會混用兩次建置的分塊。
- `tools/stamp_assets.py`（extract 結束時自動執行；只改 docs/assets 時手動執行）：index.html 的 `assets/*.js|css` 加 `?v=<檔案雜湊>`、`<meta name="ams-build" content=<build> data-key data-app data-chart>`、meta／manifest preload 加 `?v=<build><金鑰標記>`；寫出 `docs/version.json {"build","app","key"}`（key＝金鑰標記）。開著的分頁在切回前景／換頁（至多每 5 分鐘）以 no-cache 取 version.json，不同時提示重新整理。
- 連結物件 `{s, r}` 可另帶 `f`（逐欄篩選，鍵為欄號或**欄名**，值為篩選字串）；前端 01 的 KPI／重點發現連結以此重現該數字（例：K11 → 07 `{"嚴重度":"=高"}`）。沒有目標列的表格連結輸出 `?q=`（重設上次的搜尋／篩選）。資料檔本身不變。
- `?data=` 只接受同源相對路徑；index.html 帶 CSP（`script-src 'self'`），主題初始化移到 `assets/boot.js`。

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

## v3（docs/db 站 02_設備查詢卡：欄位來源 src 與附加資料 card aux）

以下適用 `docs/db/`（20260912 資料庫站，產生器 `tools/db/extract_db.py`）；舊站 `docs/` 的 02.json 沒有這些鍵，前端維持原行為（不顯示來源切換）。

### src 契約（欄位來源）
- 02.json 頂層 `src_defs: {raw|decoded|inferred|doc|factory|ctrl|hmi: {label, desc}}`（`hmi` 是 v5 加的）；`src_default: {wide:"full", narrow:"badge", breakpoint:640}`。
- `sections[].fields[]` 與 `stats.fields[]` 每欄可帶 `src: {lvl, text}`：
  - `lvl` ∈ `raw`（原始：DB 欄，可經 JOIN；灰）、`decoded`（解碼：時間/切段/int32/float32/UTF-16/FF hex/碼表；藍）、`inferred`（推論：經驗規則、對照表、外部對照檔、機組範本；橙）、`doc`（文件·設計；綠）、`factory`（出廠·EOMR；深綠）、`ctrl`（控制器·ToolboxST checkout 快照經 signal-atlas 索引；紫）。v5 另加 `hmi`（圖控 HMI 畫面檔解析；青）。**v6 的 P&ID 圖面位置不新增分級**：`sec.pid` 的列只用既有的 `doc`（PDF 文字層命中，而且圖上畫的就是本台或圖面不分機組）與 `inferred`（典型圖／迴路／同型各台，以及所有 OCR 讀出來的位置）；`src_defs` 仍是七級。
  - `text` 以級別中文名開頭：`「原始 · Devices.Identifier」`、`「解碼 · BlockData {c16} float32 · 最後記錄 {c36}」`、`「文件 · HT1-1-IMI01-A0001-H（推定） IO_Signal!r4514」`、`「出廠 · HT1-1-AQA01-T4739-0 p.1662」`。`{cNN}` 由前端代入同一列（03 或 13）第 NN 欄的值（空白顯示 `—`）。
- 欄位其他可選鍵：`label_by {col, map, default}`（依同列欄值切換標籤，例：協定 FF → 「裝置ID (FF 裝置識別字串)」）；`col` 為陣列時 `join`＋`prefixes`（R/T/F 區塊數 → `R1 / T1 / F12`）＋`blank_if_zero`；`serial`（0 → 「未寫入」）；`flt`（float32）；`cmp`（`ams_lo`／`ams_hi`＝AMS 量程下限／上限欄（只在該端列入比較且不符時標 ⚠）、`ams_unit`＝AMS 單位欄，DCS 比對不符／未比較時加標記）；`proto`（`HART`｜`FF`：協定專用欄位，設備協定（03 `protocol_col`）不同且值空白時不顯示）。
- 值顯示規則（前端 `U.cardValue`）：null／全空白字串 → 「—」；float32 FLT_MIN（|v|<1e-30 且 ≠0，1.1754943508222875e-38）→ 「未使用」；非整數以 7 位有效數字（10000.0009765625 → 10000）；`serial` 且值 0 → 「未寫入」。
- `recent_changes.columns[]` 可帶 `map`（值對照顯示）、`warn_eq`（等於此值時醒目標示）、`title`（表頭說明）、`src {lvl, text}`（欄位來源：徽章模式在表頭顯示分級籤、點開列出；完整模式在表下列出各欄來源）；空白值（含全空白字串，`cols` 的每一段）顯示「—」；「類別」欄＝14 表事件分類：`Change performed by foreign host`（Cat 28）→「DCS·外部主機」，其餘 →「人工 AMS」。
- `sections_aux: [{key, label, kind?, only_ff?, empty?, note?}]`：附加區段的標題與順序（維護狀態、最後修改、DCS 比對、FF 診斷（僅 FF）、控制系統·控制器現行 I/O 組態（dcdas）、控制系統·端子表、設計規格、GE 原廠編號（getag，v7）、出廠紀錄、文件索引、文件全文檢索（docsearch）、P&ID 圖面位置（pid，v6）、圖控 HMI 畫面位置（hmi，v5）、位號歷程補充、類比輸出警報、設備補充）；`summary.groups[]` 的 `per_entry` 組（`kind: dcdas|terminal`）每個訊號一塊；`aux: {index:"card/index.json", number_from:5}`：附加區段自第 5 節起連續編號，快速連結與最近變更接在其後。`protocol_col`＝03 協定欄。
- `summary.groups[].items[]` 可帶 `hide_empty: true`：取不到值（含 aux 沒載到）時整格移除，不顯示「—」（v7 的「GE 原廠編號」：非 GE 供貨的設備佔多數）。
- `summary.groups[]` 可帶 `collapsed: true`（渲染成 `<details class="sum-g">`＋`<summary class="sum-gh">`，預設收合；展開狀態記 localStorage `ams.card.sumOpen[key]`；列印時照既有規則展開）與 `after_stock: true`（排在前端動態加的「備品庫存（倉庫）」組之後；沒有備品庫存時排最後）。
- `summary.groups[].items[]` 的 `alt`（單一 `{kind,key}` 或陣列）：主來源空白時依序改用的備援；標籤加「（<kind 中文名>）」。`kind` 為 rows 型區段（`docindex`／`docsearch`）時以列名（類別／推定值名）對照，該列自帶 lvl／來源／文件。

### card aux（`docs/db/data/card/`）
產生：`py tools/db/build_card_aux.py <cardwork_dir> docs/db/data`（在 extract_db 之後執行；會把 card/*.json 納入 `manifest.build` 並重新 stamp）。輸入為 `card_ams_extra.py`、`docmap_terminal.py`、`docmap_instlist.py`、`docmap_eomr.py`、`docmap_docindex.py` 的輸出（不進 repo），加上 signal-atlas 的控制器索引 `%LOCALAPPDATA%\dcdas\index.sqlite`（`--dcdas` 可指定、`--no-dcdas` 略過；不進 repo）、`docmap_docsearch.py` 的輸出 `%LOCALAPPDATA%\AMS\cardwork\docsearch.json`（`--docsearch`／`--no-docsearch`）與 `drive_map.py` 的 `%LOCALAPPDATA%\AMS\drive_map.json`（`--drive-map`／`--no-drive-map`；文件庫相對路徑 → Google 雲端硬碟檔案 ID，由 Drive 桌面版中繼資料庫產生）。`--recompare docs/db/data`：cardwork 不在手邊時讀已發布的 card/*.json 只重算 `sec.dcdas`／`compare`／`flags.cmp`（舊資料無 compare 的設備，儀器清單／EOMR 量程不列入比對），有給 docsearch.json 就換掉 `sec.docsearch`，有 drive_map 就重新對照 `docs[].url`／`url_note`（`file|…` 整批重算）。dcdas／docsearch／hmi／pid／drive_map／ge_tags 任一缺席而沒給對應 `--no-*` 旗標時以非 0 結束（印「!! 缺 …，若確定要略過請加 --no-…」；圖控、P&ID、GE 原廠編號的輸入、旗標與各自的關卡見 v5、v6、v7；`--recompare` 也每次重算 `sec.getag`），`rebuild.py` 因此中止並走加密回滾——少了它們查詢卡的「控制器組態」／「文件全文檢索」區段或所有 Drive 連結會整個消失，而 build 雜湊與 verify_encrypted 都不會察覺。
- `manifest.aux.card = {index, desc, parts, bytes}`。`manifest.build` 雜湊涵蓋 `sheets/*.json`＋`card/**/*.json`（含 `card/hmi/`、`card/pid/` 的影像檔）＋manifest（不含 build）；前端所有資料請求加 `?v=<build><金鑰標記>`（`D.dataV`）。
- `card/index.json`（v2，只留全廠共用的小東西；密文原本約 27 KB；加了 v5 的 `hmi` 之後 git HEAD 是 32,570 bytes，2026-10-10 是 41,466 bytes——多出來的是 v6 的 `pid.sheets` 117 筆與 `pid.note`）：`{version:2, parts, part_width, files:["card/aux-00.json",…], alias:{alias: 塊號}, src_defs, kind_label, doc_cat_order, searched:{dcdas|terminal|instlist|eomr|docindex|docsearch|hmi|pid|getag: [{doc_id, rev, ref?, title, folder, used, why, category?}]}, source_stats, stats, compare_rule, hmi?, pid?}`（頂層的 `hmi` 見 v5、`pid` 見 v6；`kind_label`、`source_stats`、`stats.sections` 也各多了 `hmi`、`pid`、`getag`（v7），`stats` 另有 `getag`）（`dcdas` 那筆＝signal-atlas 索引本身：doc_id `signal-atlas`、rev＝各控制器 checkout 日（`controller.last_mod`）列表、ref 含 checkout 區間與索引建立日；`docsearch` 那筆＝hst-docsearch 索引本身：doc_id `hst-docsearch`、rev＝索引日期）。`stats` 另含 `near`、`dcdas_multi`、`ams_vs_dcdas:{ok,near,mismatch,not_compared}`、`docs_with_url`、`docs_with_url_altrev`、`doc_no_resolved`。
- 文件中繼資料 `docs` 與 `doc_no` **隨各分塊攜帶**（v1 全放 index，每筆含 33 字元 Drive ID 不可壓縮、占第一張卡下載量近半）：`card/aux-NN.json = {part, by_alias:{alias: {sec, compare, flags}}, docs:{"kind|doc_id|rev": {title, folder, why?, category?, url?, url_note?}}, doc_no:{文件編號: "file|編號|版次"}}`，`docs`／`doc_no` 只含該塊 by_alias 引用到的子集（所有鍵名 `d` 指到的文件＋塊內文字出現的文件編號）；前端 `D.loadAux` 把分塊的 `docs`／`doc_no` 併回 `ix` 再交給卡片，卡片端仍讀 `ix.docs`／`ix.doc_no`（舊版 index 也相容）。`docs[].url`＝`https://drive.google.com/open?id=<Drive 檔案 ID>`（有 drive_map 時；前端把該文件來源的數值變成連結，來源展開列「Google 雲端硬碟」）；`url_note`＝退路只對到同編號、別版次（或檔名版次不明）的檔時的說明「雲端只找到 <檔名>（版次 X，與本站資料來源的版次 Y 不同）」——連結仍給（同編號別版次仍有參考價值），前端列「Google 雲端硬碟（版次不同：檔名）」並併入滑鼠提示，工程師才不會把別版次的值拿去改現場。無編號的檔 key 為 `docsearch|<sha1(路徑)前 12 碼>|`。`doc_no`＝欄位值本身寫的文件編號（P&ID、邏輯圖、Hook-up 圖、位置圖、EOMR 亦見於…）對到文件庫裡那份檔（檔名以編號開頭；值有寫版次取該版，否則最高版次；PDF 優先、排除副本夾；指定版次不在雲端時 why 寫「指定版次 X 不在雲端，改開最高版次 Y」），docs 同 key 給 title/folder/url；前端讓這種值直接開那份圖（來源展開多一列「欄位所指文件」），不是開提到它的來源文件。`folder` 一律是相對工程文件庫根目錄的資料夾名；**任何 JSON 不得含本機絕對路徑**（產生器以 regex 自檢，命中即中止）。
- `card/aux-NN.json`（依 03 列序分塊，每塊明文 ≤ 約 350 KB／密文 ≤ 約 45 KB，含該塊的 docs 子集）：`{part, by_alias:{alias: {sec, compare, flags}}, docs, doc_no}`。
  - `sec.sync|change|ident|device|alarm|ff = {rows: [[欄位, 值, lvl, 來源字串]]}`（AMS DB 補充）。
  - `sec.dcdas|terminal|instlist|eomr = {entries: [{h, lvl, src, rule, d?, note?, rows: [[欄位, 值, 狀態?]]}]}`：一筆 entry＝一份文件的一列/一頁（dcdas：控制器的一個類比輸入通道，lvl `ctrl`，rows＝控制器、I/O 模組、通道、訊號名、裝置位號 (DeviceTag)、輸入型式、HART 通道、`DCS AI 量程 (Low/High Value)`、訊號說明、signal-atlas 深連結；`rule`＝位號對照方式）；entry 內各欄共用 `src`；`d` 指向 docs（分塊自帶）；狀態 `near|mismatch|unit_mismatch|unit_unknown`（量程欄與 DCS 基準比對）或 `warn`（EOMR 序號與 AMS 不符；dcdas：同位號另一通道的量程與基準通道不同）。
  - 文件參照字串：產生器可給 `ref`（完整顯示字串），否則 `doc_id-rev`。DCS 端子表 xlsx 本身沒有版次字母（CoverSheet「Revision」欄未隨 IO Rev 更新）：字母取自同 IO Rev 的 PDF 檔名時寫 `HT1-1-IMI01-A0001-H（推定）`；找不到對應 PDF 時寫 `HT3-1-IMI01-A0001（IO Rev3，版次字母不明）`。同 IO Rev 多份 xlsx 取修改時間最新者。
  - 儀器清單 HRSG xls 的 RANGE 若為數值儲存格（原文無單位，「0~」與單位只來自整欄數字格式）：`設計量程（原文）` 寫原數值並說明格式，另加 `量程單位來源＝儲存格數字格式（推定）`；比對一律 `unit_unknown`。
  - `sec.docindex = {rows: [[類別, "文件-版次 · p.頁", lvl, 來源字串, {rule, d?}]]}`。
  - `sec.hmi = {rows: [[欄位, 值, "hmi", 來源字串, extra]]}`＝圖控 HMI 畫面位置（每組畫面 4 列；見下方「v5（docs/db 站：圖控 HMI 畫面位置）」）。
  - `sec.pid = {rows: [[欄位, 值, "doc"|"inferred", 來源字串, extra]]}`＝P&ID 圖面位置（每張圖紙 5 列；見下方「v6（docs/db 站：P&ID 圖面位置）」）。
  - `sec.getag = {entries: [{h, lvl:"doc"|"inferred", src, rule, d?, rows}]}`＝GE 原廠編號（第一筆是本台；見下方「v7（docs/db 站：GE 原廠編號）」）。
  - `sec.docsearch = {rows: [[類別 | 推定值名, 值, lvl, 來源字串, {rule, d, hit?, pages?, term?, alt?:[{ref, d, p, why}]}]]}`（`docmap_docsearch.py`）：同家族（HT0/HT1/HT2 同編號、EOMR 的 AQA01-T####／AQP01-Q#### 兩本、noKKS_ 原件副本）只列代表，其餘放 `alt`（前端來源明細列「其他版本／副本」各自可點開）；同類別第 2 個家族的標籤寫「類別（另：編號 標題）」；根目錄 `all instrument list` 個人彙整檔排除。類別列（儀器清單、出廠證書／EOMR、規格表、DCS 端子表、P&ID、Hook-up、位置圖、邏輯圖、接線圖／迴路圖、電纜表、操作說明、手冊、Open Item／查修、教材、其他）的值＝`"文件-版次 p.N｜命中行"`（Office 檔無頁碼），每類別最多 2 份、同編號取最高版次、副本夾與本站匯出排除；推定值列（`序號命中（文件）`、`出廠型號（文件）`、`型號（文件）`、`廠牌（文件）`、`量程（文件）`、`量程（邏輯圖）`）由命中行／命中頁以規則抽出（rule `FTS-…`），lvl `factory`（出廠證書類）或 `doc`；位號不採 OCR 命中，序號的 OCR 命中在來源字串標「需開原圖確認」。不列入 compare。
  - `compare = [{item:"量程", baseline:{kind:"dcs_write"|"dcdas"|"terminal", label, lvl, src, lo, hi, unit, note, bounds:["hi"]|["lo"]|["hi","lo"]}, others:[{kind:"dcdas"|"dcdas_ch"|"terminal"|"ams"|"instlist"|"eomr", label, lvl, src, lo, hi, unit, status:"ok"|"near"|"mismatch"|"unit_mismatch"|"unit_unknown"|"ref_only", note}]}]`。`kind:"dcdas_ch"`＝同位號其餘量程不同的控制器通道（label「控制器組態 · <控制器> <訊號名>」，note 前綴「同位號另一通道；」），各自與基準比對但不寫 `flags.cmp.dcdas`。
    - 基準（以 DCS 為主）依序：(1) 控制器現行 I/O 組態（`sec.dcdas` 有 Low/High 的通道中，優先取控制器與位號機組前綴一致者（同一 DeviceTag 可能接在 G11／G12／S1 多個控制器），其次單位有寫的，否則索引排序第一個；標「DCS 控制器組態 (AI Low/High Value)」；各通道量程不一時 baseline.note 註明、其餘通道列成 others `dcdas_ch`、`flags.cmp.dcdas_multi="warn"`（前端黃色 pill「控制器多通道量程不一」；多點溫度元件多量程可能是正常設計，不當故障））→ (2) AMS 事件中該參數最新一次「值有改變」的 Cat 28 外部主機寫入（`dcs_writes` URV/LRV，標「DCS 寫入 (AMS 事件)」；只有寫入日期晚於該控制器的 checkout 日期（dcdas `controller.last_mod`；索引建立日只是備援）、或沒有控制器資料時才當基準，否則列為 others 且只比它寫入的那一端，`others[].bounds` 註明）→ (3) DCS 端子表 DEVICE_LO/HI（設計文件）。非基準的 DCS 來源也列入 others 比對。（2026-09-24：G12HAP70BT001 的 DCS 寫入 160 已被人工改回 200 且控制器為 200，寫入事件是歷史，不能讓一致的來源被標 ⚠。）DCS 只寫入一端時 `bounds` 只含該端：另一端顯示端子表（或 AMS 現值）僅供參考，不比較（前端標「（不比較）」）。DCS 寫入基準的單位＝AMS 單位（UNIT 寫入 > AMS 現值單位）；AMS 單位空白時留空（不借端子表單位），note 註明未翻譯的 AMS 單位碼。2026-09-26 全廠比對（有控制器基準且 AMS 有現值的 1,240 台）：AMS 現值與控制器組態完全相同 1,128（91%）、近似 22（2%）、不符 53（4%）、未比較 37；端子表 37% 與控制器不同，所以端子表排第 3。
    - 比對：同單位（不需換算）時 7 位有效數字完全相同才 `ok`（量程差異只會是 float32 殘差或真的有人改過，URV 1000 vs 996 不該顯示 ✓），差在 ±0.5% span 內為 `near`（note「≈ 近似（上限 x vs y；同單位但數值不同，差在 ±0.5% span 內，請確認）」；前端黃色「≈ 近似（請確認）」、不併入紅色 ⚠），超過為 `mismatch`；需換算單位者（°C/°F/K、Pa/kPa/MPa/mbar/bar/psi/mmH2O/inH2O/inHg/mmHg、mm/cm/m/in、%）文件常寫圓整值（0-145 psi 對 0-1000 kPa 換算 999.7），維持換算後 ±0.5% span 內為 `ok`。兩邊單位都明確但量綱不同、或明確「絕對壓 vs 表壓/差壓」→ `unit_mismatch`（單位不同未比較）；一邊明確絕壓、另一邊未標示且差 1 atm（容許 max(2% span, 2 kPa)）即相符 → 也判 `unit_mismatch`，note「疑似絕壓↔表壓表示不同」。任一邊單位空白、無法辨識或僅為推定 → `unit_unknown`（單位不明未比較）。儀器清單只取主體列（排除保護管／感測元件）；EOMR 優先取「序號與 AMS 相符＝是」的證書；序號不符（「否（AMS=…）」＝非本台）者不比較、不寫 `flags.cmp`，只在 others 列一筆 `status:"ref_only"`（note「證書序號與 AMS 不符（非本台），僅供參考、未比較」）；AMS 未寫入序號者仍比對，note 前綴「AMS 未寫入序號，無法確認為同一台；」。
  - `flags = {last_change_dcs, has_dcs_write, dcs_write_keys, sync_unrecovered, cmp:{kind: status, "<kind>_lo"|"<kind>_hi": status, dcdas_multi?: "warn"}, ff}`（`<kind>_lo/_hi` 只給列入比較的那一端；整體 mismatch／near 時未不同的那一端為 `ok`；`dcdas_multi` 只在同位號多通道量程不一時出現，`dcdas_ch` 列不寫進 cmp）。
- 多份副本／多版次：各產生器以新版為主（版次大者；同版次取修改時間最新），來源字串寫「文件編號-版次＋工作表!列 或 p.頁」。

### 前端（card.js／core.js／app.css）
- 「來源：隱藏｜徽章｜完整」三段切換，選擇存 `localStorage['ams.card.srcMode']`（讀寫 try/catch）；未選時容器寬 ≥640px 預設「完整」、否則「徽章」。斷點依 `.card-scroll` 寬度（ResizeObserver 在 `.cq-body` 加 `.narrow`），不是視窗寬。
- 完整模式每區段表頭「欄位｜數據｜來源」三欄；徽章模式值後加色點按鈕（≥32px 觸控區，`aria-expanded`）點開完整來源；窄容器上下堆疊。
- `beforeprint` 展開卡片內 `<details>`（參數現值除外）並強制完整模式；`afterprint` 還原。
- `D.loadAux(alias)`：先取 `card/index.json`，再按需載入該 alias 所在的 `aux-NN.json`（以 `this.res.alias` 防競態）。文件區段無資料時顯示「查無（已比對：文件編號-版次…）」。
- 文件連結：欄位值來自某份文件（entry 的 `d` 或列的 `{d}`）且 `index.docs[d].url` 存在時，值渲染成 `<a class="cf-t doclk" target="_blank" rel="noopener noreferrer">`（底線點狀＋↗），來源展開的「文件資訊」多一列「Google 雲端硬碟 → 開啟檔案」。`docs[d].url_note`（雲端只找到同編號別版次）存在時該列改「Google 雲端硬碟（版次不同）：<url_note> → 開啟 ↗」，並併進 doclk 的滑鼠提示。CSP 不需放行（只是導覽連結）。
- 路由 `#/card/<查詢鍵>?a=<alias>`（app.js `R.parse` 把 `?` 後解析成 `params`）：同一鍵對到多台時指定顯示哪一台；`lookup()` 在 `count>1` 且 `a` ∈ `IX.aliasesOf(key)` 時改用該 alias 的 03 列，輸入框／網址主體／分頁標題維持原查詢鍵，`.cq-alts` chips 一直顯示（第一台連 `#/card/<鍵>`，其餘帶 `?a=`；位號在前、alias 在後、目前這台 `.on`）。hero「分享」鈕的網址由 `shareUrl(res)` 產生（`navigator.share` 沒有就複製）。
- 「最近查過」（localStorage `ams.card.recent`）：`AMS.CardView.recent()`／`recentItems()` 為靜態方法，查詢卡與頂列搜尋的 Autocomplete 以 `emptyItems` 選項在框內空白（聚焦或清空）時列出（`src` 顯示「最近查過」）；結果頁 `.cq-meta` 尾端有「← 上一個：<位號>」chip（最近查過裡第一個不是目前設備者）。
- 摘要標頭 `.sum-asof`「資料：AMS 資料庫 yyyy-mm-dd｜控制器 checkout 起～迄｜文件索引 yyyy-mm-dd」：初值取 `manifest.workbook.source` 的 yyyymmdd，card/index.json 到達後改用 `source_stats.ams.backup_date`、`searched.dcdas[0].ref`（去掉括號；沒有 ref 就從 `rev` 取最早～最晚日期）與 `searched.docsearch[0].rev`；列印保留。
- 複製：`AMS.copyText(s)`（`navigator.clipboard` 不存在或被拒時退回 textarea＋`execCommand('copy')`）；摘要 `.sumgrid` 的值點一下即複製（`.cf-v[data-copy]` 原值，網址類複製完整網址；連結／按鈕／來源展開／拖曳選字不攔）並 `U.toast`。
- 比對狀態顯示：`near` → 黃色 `.cmp-flag.warn`「≈ 近似（請確認）」，摘要標頭另出黃色 pill「≈ 量程近似（請確認）：<來源>」不併入紅色 ⚠；`flags.cmp.dcdas_multi === 'warn'` → 黃色 pill「控制器多通道量程不一（n 個通道）」（n＝`sec.dcdas.entries` 數）；`kind` `dcdas_ch`（其他通道）標籤「控制器組態（其他通道）」。這些鍵沒有資料時前端不顯示。
- 查詢卡連到分塊表（參數現值）的連結帶 `rn=<此設備最後一列>`（`sheetHref(sid, {r, rn, f})`），table.js 可只載 r..rn 所在的分塊。table.js 的部分載入模式：`U.isMobile()`、或路由帶 `r`／`f` 時分塊表只 `ensurePart(partOf(r)..partOf(rn))`、不自動 `loadAll`；工具列載入列顯示「已載入 k/N 部分 · …（篩選、排序、CSV 只含已載入的列）」與「載入全部」鈕（`data-act="loadall"` → `loadRest(null)`）；桌機無參數維持自動全載。

## v4（docs/db 站：氣動閥清單；tools/db/pneuvalve_site.py）

來源是 Google 試算表「興達全廠氣動閥LIST_v2.6」匯出的 xlsx（`paths.PNEUVALVE_XLSX`／`AMS_PNEUVALVE_XLSX`），不是 AMS 資料庫；產生器在 extract_db／build_card_aux（或 `--recompare`）之後跑，資料加密中也可直接跑（自行解密 → 套用 → `extract_db.data_build` → 加密）。冪等：先移除上一次的 57～61、群組與 00 目錄列再重加。`rebuild.py` 兩條路徑結尾都會跑，`--only-pneuvalve` 只跑這一步、`--skip-pneuvalve` 略過。
- 側欄群組「氣動閥清單」（`manifest.groups` 排在「設備與位置」之後；`tab_color #8B5A00`）：`57_氣動閥主表`、`58_水處理與公用水系統`（xlsx 全部欄位＋`Valve Tag No.` 後插入 `AMS 設備 1（查詢卡）`／`AMS 設備 2（查詢卡）`（連結格 `{t:<AMS 位號>, l:{s:"02", q:<alias>}}`）與 `AMS 對照（方式／定位器比對）`；`ui.presets`「有 AMS 設備」；七條 bands）、`59_氣動閥兩讀並列`、`60_氣動閥推翻紀錄`、`61_氣動閥刪除紀錄`（原分頁照搬）。00 目錄與各表註記、`workbook.subtitle` 的「本站 N 頁」同步更新。
- 57／58 另帶兩個前端專用鍵（table.js 不讀）：`valve_src = {"<列>": {"<xlsx 欄名>": [lvl, 來源字串, docKey|null, 兩讀|null]}}`（只做查詢卡顯示的欄；來源依序取 v2.6推翻紀錄、v2.6補齊明細（文件＋頁碼＋證據等級；推導／翻譯 → `inferred`，EOMR／FAT → `factory`）、專屬來源欄（SOV／定位器／LS／失效動作文件來源）、本列主要資料來源；兩讀＝`[讀法A, 出處A, 讀法B, 出處B, 表內採用, 備註]`）與 `valve_docs = {docKey: {title, folder, why?, url?, url_note?}}`（文件編號經 `build_card_aux.resolve_doc_numbers` 對到雲端檔案）。
- `02.json.valve = {sheets, fields:[[卡片標籤, xlsx 欄名]], index:{compact 鍵: [[sid, 列], …]}, weak:{compact 鍵: [[sid, 列], …]}, list:[[sid, 列, 位號, [別名…], 中文名, 英文名]], by_alias:{alias: [[sid, 列, 機組, 對照方式, 定位器比對 ok|mismatch|absent|unknown, 比對說明, 備註]]}, list_name, list_url}`。鍵＝`IX.compact`；一鍵可對多列（`LCV-3461`、`VA46-1A`）。
  - `index` 的鍵由 `tools/db/pneuvalve_keys.py` 逐列抽出（2026-10-03：查 GE 舊位號 `VA13-25` 找不到）：清單位號、依「涵蓋機組」展開的位號（Gxx→G11…G32、Cx0→C10…、`G11/G12…` 斜線列舉）、去機組核心（`MBP70QN222`、`XX`／`YY`＋核心）、Legacy/GE Tag 欄的 GE 器件號（`VA13-25`、`90VA13-25`）、迴路號（`LCV-3461`）、Mark VIe 器件名（`20SSV-3B`、`SSV-3B`、`HPEV`）、標了 (GE KKS) 的 `11LBF54AA004`／`LBF54AA004`、SOV／LS／定位器欄裡這顆閥自己的附件位號（`20VG8`、`LY-3461`、先導 SOV 專屬位號）、刪除紀錄併入本列的別名。查無／待查／N/A 開頭的儲存格與備註、序號欄不取。`weak`＝多列共用的廠商代號（`V1`～`V4`、`IGV`、`UVT`）。機組前綴寫法（`G11_90VA13-25`）不存，前端去前綴再查。
  - `list`：自動完成與查無頁建議的來源，每筆 `[sid, 列, 位號, [別名…], 中文名, 英文名, [涵蓋機組…]]`（別名＝index 裡位號／核心以外的顯示字串；名稱去掉「(自動翻譯)」、開頭的「=位號：」參照與落單的 = ：，中文名剩不到兩個字就留空改用英文名；涵蓋機組＝`expand_units` 的結果）。
- 對照：閥位號（展開後）＝04 位號索引任一鍵，或 GT 閥 `<機組>_90<Legacy/GE Tag>`；再套 `<CARDWORK>/pneuvalve_xwalk.json`（`drop`／`add`／`note`；2026-10-02 多代理逐筆驗證的結果，另存 fill26/pneuvalve_ams_xwalk.json）。定位器比對＝清單「Positioner 定位器」欄與 AMS 製造商＋型號比廠牌家族（`POS_FAM`）。
- 摘要組 `{"key":"valve","valve":true,label,note}`（`extract_db.summary_spec`，排在 `dev` 之後；舊 02 缺的話產生器補上）：`by_alias` 有此 alias 才渲染（否則整組不出現），`fillValveGroup` 懶載 57／58，每個清單列一塊 `.sum-sig`（標頭：清單位號、本卡機組、⚠ 定位器廠牌不符、兩讀 n 格、「在 57_… 開啟此列」），欄位逐格帶 `src`（文件連結開雲端檔案；兩讀在「文件資訊」列 A／B）。
- 查詢（`core.js` `AMS.valves`：`load()`／`hit(V, q, amsLen)`／`suggest(V, q, limit)`／`item`／`covers`／`core`／`amsLen(rs)`，查詢卡與頂列搜尋共用；`load()` 在 manifest 還沒載時不記住結果）：順序＝AMS 位號索引完全相符 → 去分隔符相符 → **氣動閥** `hit` → AMS 包含 → AMS 唯一建議 → 查無。`hit` 回 `{ents:[{sid,row}], unit, c, k, via}`，`via`：`key`（整串是鍵）→ `suffix`（去附件後綴 `-MB01`／`-KH01`…）→ `unit`（去機組前綴 `G11(_)(90)`，只留 `list[6]` 涵蓋該機組的列：`G11_LCV-3461` 只剩 GT 那列）／`unit-other`（鍵存在但沒有一列涵蓋該機組：仍顯示閥卡，狀態列寫「清單這一列只涵蓋 …（沒有 G21）」，AMS chips 標「同型閥在其他機組」，不可說成清單位號）→ `weak`（廠商代號；閥卡下另列 AMS 位號索引含該字串的鍵）→ `contain`（包含 ≥6 字元的鍵且比 AMS 的包含命中長）→ `token`（Mark VIe 訊號名：以 `_ . 空白` 分段、去開頭 `L` 後整段是鍵，`S1.do_l20wsv_o`）。
  - `lookup()`／`valveLookup`：AMS 的模糊對應指到的正是這顆閥自己的 AMS 設備（只打數字機組的 `11HAD10QN005`、只有一台的核心 `HAD10QN001`）→ 照舊開那台 AMS 設備，**但機組要與使用者打的一致**（機組取自去掉的前綴、命中鍵本身的 `G11…`，或鍵前面的兩位數；`G12HAD10QN001`／`12HAD10QN001`／`G12HAD10QN001.PV` 在 AMS 只有 G11 那台時不可開 G11 的設備，改顯示閥卡並註明「AMS 資料庫沒有 G12 這台，同型閥在其他機組」；`unit-other` 一律不讓）；輸入帶機組且該機組恰有一台 AMS 設備 → 顯示那台（狀態列說明經由哪種識別碼）；否則 `res.valve` → `renderValveOnly`（每個清單列一塊；hero 在整串就是清單位號時保留清單寫法 `Gxx…`；狀態列不標紅）。
  - 模糊對應的採用（`valveBlocksFuzzy`；`go()`、頂列 `onEnter` 同規則）：清單有命中，或清單有「開頭相符」而且不是 AMS 那台自己的閥的候選 → 不自動跳到 AMS 的包含／唯一建議（`C10MAJ60QM06` 不再悄悄開 `C10MAJ60BP006`、`G11_90VA13` 不再直接開 VA13T-1），改顯示查無頁並把 AMS 的模糊候選列在最前。
- 建議：`AMS.searchSuggestSource`（查詢卡輸入框與頂列搜尋）把 `IX.suggest`（AMS 在前，至少 8 筆）與 `AMS.valves.suggest`（最多 4～6 筆）合併；`AMS.tagSuggestSource` 維持只有 AMS 位號索引（備品庫存的 KKS 正規化用它，氣動閥別名／`Gxx` 位號不得寫進領料紀錄）；04 裡 v7 的 GE 原廠編號列（來源類型 `8 `）也濾掉（一個 GE 編號常對 G11、G12 兩台，正規化會默默改寫成第一台）。`valves.suggest` 項目 `{key, src:'氣動閥清單', alias:<名稱>, tag:<清單位號>, valve:[sid,列], m:'pre'|'sub'|'name', rows?}`：位號／別名開頭 → 包含；輸入帶機組或 `90` 時去前綴再比、只取涵蓋該機組的列、`key` 給帶機組的位號（`G11MBP70QN2` → `G11MBP70QN222`）；輸入含中文時改比名稱（空白分段、每段都要出現）；同一別名對多列只列一次，`rows`＝列數（`tag` 保持真的位號）；`key` 一定是 `hit`／位號索引查得到的字串。查無頁 `renderNotFound` 多一塊「氣動閥清單中相近的閥」（`.nf-valves`）與「在 57／58 搜尋」連結；兩邊都沒有候選時狀態列加註可到 57／58 搜尋。
- 打錯字：`AMS.fuzzy(V, q, limit)`（core.js）只在 `IX.suggest` 與 `valves.suggest` 都沒有結果、且 `IX.resolve`／`valves.hit` 也對不到時，由 `searchSuggestSource` 與查無頁（`.nf-fuzzy`「是不是打錯字？」，狀態列改說「可能打錯字」）使用；項目 `m:'fuzzy'`、下拉提示前加「相近」。去分隔符／帶前後綴就對得到的字串（`G12-HAP70-BT001`、`….PV`）下拉只列 Enter 會開的那個鍵。比對：輸入先 NFKC 正規化（全形、各種破折號）；易混字元（S/5、O/Q/0、I/L/1、B/8、Z/2）視為相同後算編輯距離（含相鄰對調）≤1，實際比的那一段（不含機組／90 前綴）≥9 字元可到 2；只回傳最接近的一層；清單每列只出一筆（位號、核心、各別名取最接近的寫法），帶機組的輸入只取涵蓋該機組的列；純數字鍵只給 ≥6 位的純數字輸入比；去分隔符後不到 4 字元或含中日文不做。**只列出、永不自動開**：`IX.resolve`、`valves.hit`、Enter 的行為都不看它；`tagSuggestSource` 不含。
- 表格「搜尋此表」（table.js `refresh`）：照字面一列都找不到時，位號型查詢（字母＋數字且去分隔符後 ≥4 字元，或純字母 ≥8 字元；純 ASCII，先 NFKC）改以去分隔符比對——查詢拿掉 `-` `_` 空白、儲存格只拿掉 `-` `_`（`VA1325`、`va13 25` 找得到 `VA13-25`）。字面有結果就不跑第二輪；逐欄篩選維持原樣比對。
- 窄螢幕頂列（app.css／app.js）：≤720px 間距 6px；≤520px 登入鈕只留圖示，有登入鈕（`body.auth-on`）時「清除密語」收起（登出會一併清除）；≤380px 品牌標收起。觸控裝置聚焦 `#global-search` 時 app.js 在 `.app-header` 加 `gs-focus`，品牌／圖例／主題／登入鈕讓位、搜尋框佔滿整列；框內空白按 Esc 離開。滑鼠／鍵盤的窄視窗不收（Tab 要走得到那些按鈕）。
- 端對端：`tools/tests/test_pneuvalve.py`（測試位號從 02.json `valve` 挑，不寫死）。

## v5（docs/db 站：圖控 HMI 畫面位置；`tools/db/hmi_shots.py`／`hmi_nav.py`／`hmi_index.py`）

查詢卡除了「這台儀器是什麼」，再回答「它畫在圖控的哪一頁、畫面上哪個位置」。來源是 GE CIMPLICITY／ActivePoint 的畫面檔目錄
`paths.HMI_SCREENS`（`AMS_HMI_SCREENS`，預設 `<LIBRARY_ROOT>\AMS\Screens`；遞迴 473 個 `.cim`／223 MB，**唯讀、不修改**），不是 AMS 資料庫。

**掃描範圍（寫報告、寫卡片文案一律用這組數字，不要再寫成「掃了 473 個 .cim」）**：索引只建**根目錄的 248 個**＝操作員能從選單導覽到的畫面。
其餘 **225 個在子目錄**（`customFaceplate` 157／`tpFpFaceplate` 47／`customLibrary` 17／`navigation` 2／`utilities` 1／`help` 1）＝元件面板與函式庫範本，
沒有選單列也沒有畫面變數，座標沒有「畫面上哪裡」可言，**不建索引**。但 `hmi_index.scan_excluded()` 仍會把這 225 個檔的字串逐條用同一套 `extract_tags` 掃過，
結果寫進 `stats.excluded_scan`（`{files, dirs, strings, tag_hits, tags, ff_hits, ff_tags, screens_root, screens_all}`）：
實測 **AMS 位號 12 支命中、而這 12 支都已由根目錄畫面涵蓋**（沒有因此漏掉任何一台）、**FF 位號 0 命中**。
卡片的「查無」文案、`index.hmi.stats`、`index.searched.hmi[0].why` 的數字全部取自這裡，不是口頭聲明；`--no-excluded-scan` 可略過（省約 20 秒，但 `excluded_scan` 會是 `null`，文案就只說排除、不聲稱 0 命中）。
三個產生器照這個順序跑，輸出全在 cardwork（不進 repo）：

| 步驟 | 程式 | 輸出 | 內容 |
|---|---|---|---|
| 0 | `tools/db/hmi_runtime_map.py` | `tools/db/hmi_runtime_map.json`（**進 repo**，290 張截圖 → 201 個畫面、285 組（畫面, 選單機組）） | **離線**（不在 `rebuild.py` 裡）把使用者 2026-10-04 在機組上拍的執行時畫面對應到 `.cim`。輸入是 `Screens\圖控\*.xlsx` 七個活頁簿內嵌的 PNG（`BOP` 51／`BOPE` 35／`G11` 64／`G12` 57／`H11` 20／`H12` 20／`S1` 43，**全部 1920×1080**＝標記所用的裝置座標系）。**認畫面要兩個互相獨立的訊號，缺一不可**：①擷取順序＝`CIMNavigationMenuItemsStd.csv` 的選單順序（`BOOK_MENUS` 記每個活頁簿收哪幾個分頁）——單靠順序不行，有人重貼過同一張，多一張就把後面全部推移一格；②畫面左上麵包屑（`分頁 :: 子選單 :: 項目`，裁 `(0,186,760,214)` 放大 2 倍後 OCR）比對 CSV 的封閉詞彙——單靠 OCR 也不行，同一分頁裡「Hp & Lp Economiser」「Chiller Unit」各出現兩次（機組不同、文字一樣），而且 OCR 把 HRSG11 讀成 HRSG1、分不出 HRSG11／HRSG12（那是活頁簿決定的）。兩者以 **Needleman–Wunsch 單調對齊**（`GAP_IMG=-0.55`／`GAP_ROW=-0.15`，跳圖比跳選單列貴）合起來，選單列決定 `Cim Screen FileName` 與 `Unit`。**位元組完全相同的兩張**（Excel 會讓同一本裡兩個錨點共用同一個 media，所以以 `(活頁簿, sha1)` 分組；跨本相同只列進 `cross_book_identical` 警告、不丟）一定是重貼：留分數高的、丟另一張，它本來要對上的那列其實沒拍到（實測 3 張：`G11#17`＝Compressor 重貼、`G12#10`＝Gas Fuel Purge 重貼、`G12#55`＝G12S SIL Ventilation 重貼）。**還有兩道與分數無關的守門**，因為光看分數擋不住「同一頁拍了兩張（不是重貼）」——多出來的那張會被 DP 綁到鄰列，而同子選單的麵包屑彼此極像，分數常常還在 0.80 以上：①**argmax 檢查**：被指派的那列若不是這張圖 OCR 最像的那列、而且差距 > `ARGMAX_GAP`＝0.05，就列進 `review`（今天命中 2 張，`G11#49`／`G12#42` 的「SIL Overview vs Overview」，都是對的——只能靠順序分辨）；②**每張都要有歸屬**：`shots == mapped + dropped + unmatched`，`assert` 擋著，沒對上任何選單列的一律列進 `unmatched` 並逐張印出（`BOOK_MENUS` 的分頁清單與活頁簿不符時整本後面會挪位，以前這種情況統計看起來完全乾淨）。同一個 `.cim` ＋同一個 `Unit` 出現兩列選單（`GT_Perf` 的 Gas Turbine 1／2、`HRSG_Perf` 的 HRSG 1／2，只差 `ScreenVariables` 的 `num;1_`／`num;2_`）是**兩個不同的頁面、不是重複**，但 `variants` 以機組當鍵分不開，只能留第一張——第二張會進 `dropped` 並附理由，`stats.clash` 也記著（今天 2 組，都沒有 AMS 位號落在上面）。讀繪圖錨點時走訪**全部** `xl/drawings/drawing*.xml`、直接抓 `r:embed`，並以 `<xdr:pic>` 的個數當斷言：舊寫法要求 `<xdr:cNvPr …/>` 自閉合，使用者填了替代文字或加了超連結就會整張跳過、後面的序號整串挪位。每張都記 PNG 的 `sha1`，活頁簿重拍／重排時 `hmi_shots` 會對不上而出聲，不會默默貼錯圖。**只有這支要 `rapidocr-onnxruntime`**；重建流程讀的是它 commit 出來的 JSON，不跑 OCR。輸出另有 `dropped`（5 張：3 張重貼＋2 張同機組兩列選單）／`review`（6 張：分數 < 0.80 的 4 張＋argmax 命中的 2 張）／`unmatched`（0）／`cross_book_identical`（0）／`stats.clash` 供覆核。2026-10-04 真的會發布的 66 組已逐張以視覺覆核過麵包屑＋分頁高亮＋左欄高亮＋頁面標題，全部相符（其中 3 張 HMI 自己把麵包屑的分頁段落畫成空白，靠另外三個訊號定案）。 |
| 1 | `tools/db/hmi_shots.py` | `CARDWORK/hmi_shots/`（155 個設計時 `.webp` 6.8 MB ＋ 285 個執行時 `<slug>__<選單機組>.webp` 15.1 MB ＝ 440 個 webp 共 21.9 MB，連 `index.json` 整個目錄 22.2 MB；257 個畫面有影像，其中 101 個本來沒有 ThumbNail） | **影像優先序：執行時截圖 > 設計時 ThumbNail。** 讀步驟 0 的對應表（`--runtime-map`，預設 `tools/db/hmi_runtime_map.json`），逐張核對 PNG 的 `sha1` 與尺寸必須是 `1920×1080`，再縮成寬 1280 WebP；**逐「選單機組」各存一張**（同一張畫面在 HRSG11／HRSG12 是兩份不同的現值，不可共用）。`index.json` 每一筆的 `file`／`w`／`h`／`bytes`／`source` 一律是「這個畫面要發布的那張」：有執行時截圖 → `source="runtime capture"`、另有 `runtime:{captured, primary, variants:{選單機組:{file,w,h,bytes,book,anchor,src_sha1,crumb,…}}}`，而設計時那一筆（含 `bounds`／`masked`／`mask_metrics`／`sha1`／`dup_of`）**原封不動整包搬進 `emf`**（不丟，遮罩統計也改讀它）；沒有截圖 → 欄位與 2026-10-03 版完全相同、沒有 `runtime`／`emf` 鍵。`--no-runtime` 完全不碰執行時這段，實測輸出與加這段程式之前**156/156 逐位元組相同**（含 `index.json`）。以下設計時那條路徑不變：`.cim` 的 `ThumbNail` 串流＝設計時全畫面 EMF → PowerShell GDI+ `System.Drawing.Imaging.Metafile` 渲染成 1920×1080 → **在原生尺寸塗平堆疊 chrome** → 寬 1280 WebP。**全畫面一律以裝置矩形 (0,0,1920,1080) 當畫布**（不可用 EMF 的 `szlDevice`：156 張裡有 3 張不是 1920×1080），所以影像像素 × 1.5 ＝ 畫面裝置像素。PIL 直接開 `.emf` 不可用（走 GDI `PlayEnhMetaFile`，不懂 EMF+ 記錄，畫出來近乎空白）。**塗平堆疊 chrome**（縮圖「殘影」的成因是 CimEdit 存設計時快照時把所有分支／所有機組變體的子物件全部畫出來、執行時才用 visibility 動畫只亮其中一組——導覽面板實測過繪 19~25 倍，**不是渲染器的 bug**）：在 GDI+ 輸出之後、PIL 縮圖之前，把四個原生裝置座標矩形 `nav (0,207,213,1048)`／`loading (0,182,334,205)`／`menubar (213,136,370,177)`／`banner (224,0,450,133)` 用該區逐張（`nav` 單一 probe、其餘逐列 donor）取樣到的背景色塗平，**不裁切**（裁切會動到座標基準，而 `hmi.json` 的 744 筆全畫面標記沒有一筆落在這些區塊內）。閘門：畫布必須真的是 `[0,0,1920,1080]` 且 `--screen` 未改，再逐張數重疊字串配對數——`nav` ≥ 1000 才遮（面板型與沒有 chrome 的樣板頁自動排除，不寫白名單）、`banner` 另需 ≥ 20。逐張夾限：`nav` 底緣由 `MASK_VOCAB`（畫面自己的按鈕 `####`／`MASTER RESET`／`DIAGNOSTIC RESET`）落在 **`MASK_NAV_FLOOR`＝900 以下**的命中往上夾 7px（樓地板以上的命中一律忽略並在結尾印警告——照它夾會把導覽樹整片留著，甚至讓矩形退化到整個不遮）、`banner` 右緣由第一個 `left ≥ 430` 的非 `###` 字串往左夾 2px；`nav` 的取樣 probe 固定在 `y 840~893`（＝樓地板 900 − 夾限留白 7，也就是最低可能的夾限線）＝一定在夾限線以上，`nav` 取樣不可信（眾數佔比 < 0.30 或偏離預設 > 24）時該矩形**整個不塗**（版型變了就該不塗，不是把灰塊放在可能錯的位置）；其餘三個矩形是逐列取樣，單列不可信只有那一列退回預設色（差一列只差 1px，且矩形位置另有配對數門檻把關）。`--no-mask` 完全不遮（回溯比對用）。以 2026-10-03 語料：遮 109 張、不遮 47 張（3 張樣板頁配對數 0 ＋ 44 張 faceplate），`nav` 夾限 46 張（13 張→925、33 張→958~972）、`banner` 夾限 7 張、取樣退回 0 張。`index.json` 每筆因此多兩個欄位：**`masked`**＝真的塗掉的**具名**矩形 `{"nav":[l,t,r,b],"loading":…,"menubar":…,"banner":…}`（沒遮就是 `{}`；不可寫成位置陣列——矩形組合會變，`masked[0]` 會把 `loading` 誤讀成 `nav`）、**`mask_metrics`**＝`{nav_pairs, nav_strings, banner_pairs, banner_strings, nav_bottom, nav_vocab_ignored}`（沒過門檻的畫面也留配對數，日後要調門檻不必重跑整套分析）。`masked` 每筆都有，`mask_metrics` 的**鍵是條件性的、一律用 `.get()` 讀**：只有評估過遮罩的全畫面型才有這個鍵（2026-10-03 語料 112/156，faceplate 沒有），`banner_*`／`nav_bottom` 只在過了 `nav` 門檻的 109 張，`nav_vocab_ignored` 只在真有命中被樓地板忽略時才寫（今天 0 張）。 |
| 2 | `tools/db/hmi_nav.py` | `CARDWORK/hmi_nav.json`（248 筆） | 每個根目錄畫面的**逐列對齊**選單路徑：`nav`／`units`／`variables`／`nav_src` 四個陣列同序（`navigation/CIMNavigationMenuItemsStd.csv` 的原始列序，不去重），另有 `title_en`／`label`／`caption_en`／`title_src`／`title_conf`／`captions`／`alt_names`／`file_aliases`＋`alias_tier`（`case`＝定讞／`norm`＝很可能／`loose`＝推論）。`title_zh` 全部 `null`：原廠語言檔只宣告西班牙／日／法文，473 個 `.cim` 的字串 0 個含中文（LanguageMapper.clm 裡像中文的漢字是日文）。 |
| 3 | `tools/db/hmi_index.py` | `CARDWORK/hmi.json`（354 KB） | `{by_tag:{位號:[{screen, unit, route, ref, x, y, w, h}]}, screens:{檔名:{title_en, title_zh, nav, units, img, img_w, img_h, img_canvas, w, h}}, stats}`。讀 1＋2 的輸出與 `paths.AMS_SQLITE`（現行 AMS 位號集合）、`paths.DCDAS_INDEX`。 |

**兩種影像共用同一個座標系**：執行時截圖與設計時 ThumbNail 都是 1920×1080 裝置像素、版型逐像素相同（實測把 `C10LAB22BF001`
的兩個標記疊到 `BOP_Feed_Water` 的執行時截圖與設計時縮圖，落點一致），所以換影像來源**不動任何換算**——`index.json` 的 `canvas`、
`hmi.json` 的 `x/y/w/h`、`card.js` 的百分比定位、本節以下所有數字全部照舊。

**座標基準：28800 × 16200 twips**（＝1920×1080 裝置像素 × 15，16:9）。先前推測的 25600×14400 是讀偏一個位元組的旗標對造成的錯覺，**已作廢**。
`.cim` 的矩形四元組是 `(left, top, right, bottom)` 且 **y 軸向上**（top > bottom），而且貼在**下一個**物件名之前，所以屬於前一個物件
（綁錯會讓全部物件整體錯位一個物件，在鏡像面板畫面上表現為 G11／G12 左右互換）。`hmi.json` 的 `x/y/w/h` 已換算成 **0~1 比例、左上為原點**，
可直接乘上縮圖寬高。`w` 或 `h` 可能為 0（直線、文字錨點），面積 > 25% 畫面者判定為背景面板不採用（`x/y` 為 `null`）。

四條對應來源（`entry.route`）：`obj`（物件屬性包＋選單變數代入，**有座標**）、`var`（`.cim` 字串補漏）、`pointdb`（`navigation/tp_actPt_navPointSearchDbStd.csv`）、
`dcdas`（控制器索引的 `variable.display_screen`，`hmi_point.unit_prefix` 當 `unit` 帶出來，格式與選單列的 Unit 欄一致＝`BOPM1B.`）。
覆蓋 **870 / 1,679 台（51.8%；母數已扣掉 249 台 JK MUX 模組）**，其中 HART 870/1,328（65.5%）、
**FF 0/351**：351 支 FF 位號在**根目錄 248 個畫面 0 命中**（索引本體），在**子目錄 225 個元件面板也 0 命中**（`stats.excluded_scan.ff_hits`），
兩段加起來＝遞迴全部 473 個 `.cim` 都查過，定讞查無。

`route=obj` 的 `ref`（卡片「對應方式」顯示的那一串）挑選順序：**值不是純 `{變數}` 樣板** → 值自帶位號字樣（`LITERAL_RE`） → 鍵在 `REF_KEYS` → 值較短。
第一個條件是後補的：`aliasSignal={device}` 比 `device=1-LI-CW101-1_XQ01` 短，舊版因此在 74 列顯示未代入的樣板（對操作員零資訊）。
真的只剩樣板可挑時（該物件沒有任何自帶位號字樣的屬性）會補上 `（代入後 …）`。

### card aux 的 `sec.hmi`、`card/hmi/*.json` 與 `index.hmi`

`build_card_aux.py` 的 `--hmi`（預設 `%LOCALAPPDATA%\AMS\cardwork\hmi.json`）／`--hmi-shots`（預設 `…\cardwork\hmi_shots`）／`--hmi-nav`（預設 `…\cardwork\hmi_nav.json`）／`--no-hmi`，
`--recompare` 同樣吃（沒給 `--no-hmi` 又缺 `hmi.json` 時以非 0 結束，與 dcdas／docsearch 一致）。以**現行 AMS 位號**（不是 alias）對照 `hmi.json.by_tag`。

- `sec.hmi = {rows: [[欄位, 值, "hmi", 來源字串, extra]]}`：每一組（畫面, 選單機組）**4 列**——`圖控畫面`（畫面名稱，中文優先、目前一律英文，附畫面上標題）、
  `導覽路徑`（`Block1 › BOP › HP/IP Feed Water › Feed Water　·　以選單機組 BOPM1A. 開啟`；取 `hmi_nav.json` 裡 `units[i] == entry.unit` 的那一列，對不起來才列全部並在 extra 標 `nav_all`。
  **用詞必須是「以選單機組 X 開啟」**——`unit` 是開啟這張畫面的那一列選單項的機組欄，不是儀器所屬機組，寫成「機組 X」會讓 69 台看起來像「同時存在兩個機組」）、
  `所在位置`（`畫面左 58%／上 46%（約佔畫面寬 7%、高 4%）＝圖上標記 ①；這支位號在同一張畫面另有 1 處（圖上 ②），位置可能幾乎重疊`）、
  `對應方式`（`物件參照：device=C{UNIT1_NO}LAB22BF001_XQ01`；結尾帶 `\012\013` 的多點簡寫會補一句白話「同一個物件掛 …BP001、…BP002、…BP003 共 3 支，每一支都另有自己的索引」，
  否則使用者會以為是亂碼——涵蓋 572 列）。
  每列 `extra` 都帶 `{s: 畫面檔名, g: 組序}` 供前端分組；**第一列**另帶 `nav`／`img`（該畫面有沒有影像，兩種來源都算）／`marks`／`routes`／`unit`／`ref`。
- `marks: [[中心 x, 中心 y, 框寬, 框高]]`（0~1 比例、左上原點、已去重）：框寬／高為 **0 時只標點不畫框**（直線、文字錨點）；
  同一畫面同時有「有框」與「線狀」標記時只留有框的。**`marks[0]` 就是「所在位置」那列文字描述的那處**（面積最大者排前面），
  前端照陣列順序標 ①②③——同一位號的兩處常常只差 1~2% 畫面高（放大圖上約 11 px），沒有編號使用者看不出有兩個圈、也對不上「另有 N 處」。
- **影像**：有設備對應到、而且有影像的畫面才包，`docs/db/data/card/hmi/….json ＝ {w, h, mime:"image/webp", b64}`，
  **走既有 `*.json` 加密路徑**（`encrypt_data.py` 的 `rglob("*.json")`），沒有第二套加密。寫之前先整個清掉 `card/hmi/`，掉出覆蓋範圍的畫面不會留下孤兒密文。
  檔名分兩種：執行時截圖是 **`<畫面名去掉 .cim>__<選單機組去掉結尾的點>.json`**（`BOP_Feed_Water__BOPM1A.json`），**逐選單機組一檔、而且只發布這一輪真的用得到的那幾組**
  （再加上 `runtime.primary` 那組當退路）；設計時 ThumbNail 是 `<畫面名去掉 .cim>.json`，整個畫面一檔。
  **同一張畫面不可跨機組共用執行時截圖**——HRSG11 與 HRSG12 是兩份不同的現值，共用等於把別的機組的數字端到使用者面前。
- `card/index.json` 新增 `hmi = {screens:{檔名:{title, en, zh?, caption?, nav, img, source?, captured?, variants?, file?, w?, h?, bytes?, rows}}, files:[…], bytes, captured, design:[28800,16200], canvas:[1920,1080], note, stats}`。
  `source` ＝ `"runtime"`（使用者拍的執行時畫面；此時 `captured` 是擷取日期、`variants:{選單機組:{file,w,h,bytes}}`、`file` 是挑不到機組時的退路）或 `"emf"`（設計時 ThumbNail）；沒有影像的畫面兩個鍵都沒有，一律用 `.get()`／`?.` 讀。
  `stats` 另有 `screens_with_img`（有影像的畫面數）／`screens_runtime`（其中用執行時截圖的）／`files`（實際發布的影像檔數，有機組變體時會大於畫面數）。
  `stats` 除了覆蓋率，另有 `screens_total`（建索引的根目錄畫面數 248）／`screens_all`（遞迴全部 473）／`excluded`（225）／`excluded_scanned`／`excluded_tag_hits`／`excluded_ff_hits`
  ——卡片「查無」那句要一次講完掃描範圍，不然同一張卡會同時出現 248 與 473 兩個數字、看起來自相矛盾。
  `files` 是 `card/hmi/*.json` 的清單——`tools/verify_encrypted.py` 以它認得這些密文不是孤兒；`extract_db.data_build` 的雜湊也涵蓋 `card/**/*.json`
  （兩邊都以 **posix 相對路徑**排序，Windows 的 `\` 與 posix 的 `/` 排序不同，否則 build 會對不起來）。
- `index.searched.hmi[0]`＝把畫面檔目錄當一份「文件」描述（`doc_id: hmi-screens`、`folder: AMS/Screens（圖控畫面檔目錄，唯讀）`、`why` 含覆蓋率）；沒有 Drive 連結、不進 `index.docs`。
- 來源分級新增 **`lvl: "hmi"`（標籤「圖控」，青色 `--src-hmi`）**：`extract_db.SRC_DEFS`／`build_card_aux.SRC_DEFS`／`U.SRC_LVLS`／`.lvl-hmi` 四處要一致，缺一個前端會靜默退回 `raw`。

### 前端（card.js `fillHmi`／`hmiShot`／`hmiFrame`／`openHmiLightbox`；core.js `D.loadHmiImage`；app.css）

- 摘要組 `{"key":"hmi","kind":"hmi"}`（**不收合、排在「備品庫存（倉庫）」之前**——它是 `summary.groups` 最後一個不帶 `after_stock` 的組，
  而備品庫存是前端在所有非 `after_stock` 組之後才插進去的）與附加區段 `{"key":"hmi","kind":"hmi"}`（排在 `docsearch` 之後）**都有縮圖與標記**
  （2026-10-03：使用者回報在摘要看不到圖控畫面，摘要組從「只列名稱＋導覽路徑」改成也顯示縮圖；
  2026-10-05：使用者要求「力求版面精簡」，摘要組改成**不收合、只有畫面標頭＋影像**，並從備品庫存之後搬到之前）。
  兩者都走 `fillHmi(sec, ix, grid, mode, inSum)`；第 5 個參數**只決定版面**，不決定載不載圖（原本的 `withImages` 已經沒有 `false` 的呼叫點）：
  - 摘要組（`inSum=true`）佔整列寬（`.sum-hmi { grid-column: 1 / -1 }`——漏了這一條就只佔兩欄格的左半、右半邊空著），
    每張畫面一塊：標頭（畫面名／導覽路徑／`以選單機組 X 開啟`／`.hmi-cap` 短籤／`.cim` 檔名）＋影像（`.hmi-frame` 上限 920px）。
    **不印 `.hmi-f` 四個欄位、也沒有組說明**（`summary_spec` 的 hmi 組已經不帶 `note`）：「圖控畫面／導覽路徑」兩列與標頭重複，
    「所在位置」講的就是圖上那個紅圈，完整欄位與逐格來源都在「完整資料 › 圖控 HMI 畫面位置」。
    原本寬容器才成立的「左欄四個欄位、右欄縮圖」容器查詢（`@container hmilist` ＋ `.sum-has-shot`）已經連同欄位一起移除。
  - **超過 `HMI_FOLD`（＝3）張時只先展開第一張**（2026-10-05 使用者指定）：每塊畫面改成 `<details class="hmi-screen">`＋
    `<summary class="hmi-head">`（第一塊帶 `open`），標頭尾端掛 `.hmi-exp`（CSS `::after` 給「▸ 顯示畫面／▾ 收合」，
    `summary` 是 flex 所以瀏覽器不畫預設三角）；收起來的那幾張**影像也延後**，`whenDetailsOpen` 要掛在 `<summary>` 以外的
    子元素（`.hmi-shot`）上——`<details>` 自己收合時仍然可見，掛在它身上 `IntersectionObserver` 會立刻觸發、等於沒延後。
    另加一句 `.aux-note`「這台設備有 N 張畫面，先展開第 1 張…」。3 張以內維持 `<div>`、全部展開（870 台平均 1.5 張、九成 ≤ 2 張）。
  - **查無時摘要只印一句短的**（「查無（這些畫面都沒有引用此位號）」／FF「查無（FF 訊號不出現在任何圖控畫面檔）」）：
    248／225／473 的掃描範圍那段留給完整資料區（`inSum=false`）。摘要組不收合又緊貼備品庫存，809 台沒有圖控畫面的設備
    不能在那裡被塞一段 60–75 字的說明。
  - `.hmi-cap`（只有摘要組掛，`hmiCapText(meta, pick)`）：執行時截圖寫「YYYY-MM-DD 擷取·非即時值」、設計時影像寫「設計時影像（值＝###）」、
    退回別組機組的截圖時寫「⚠ …這張是選單機組 X 的（沒有 Y 的截圖）」並轉紅（`.hmi-cap.warn`）。
    **摘要組拿掉說明之後，「擷取日期」與「非即時值」在摘要只剩這一個出處**；完整那一句仍在 `title`／`alt`／燈箱說明列（`hmiSrcText`）。
  - 附加區段（`inSum=false`）維持整列寬的大圖＋四個欄位與逐格來源（那裡本來就是「完整資料」）。
- **影像延後載入**：`hmiShot()` 只先建好 `.hmi-frame.loading` 佔位，`D.loadHmiImage` 何時跑分三種：
  **完整資料區（`inSum=false`）**交給 `whenDetailsOpen(grid, …)`，`.cq-more` 展開後跑一次（那一區是「卡片一渲染就填好」
  而不是展開才填，不延後的話每次開卡都白抓 70–105 KB／張的密文）；**摘要組展開中的畫面**傳 `loaders=null`，渲染時就載
  （2026-10-03 的回歸：當時摘要組自己是 `<details>`，延後到 toggle 才載會永遠停在 loading）；**摘要組收起來的畫面**
  （> 3 張時的第 2 張起）各自 `whenDetailsOpen(.hmi-shot, …)`，點開標頭才抓。代價：`beforeprint` 強制展開時 `load`
  來不及完成，沒展開過的畫面第一次列印只會印到佔位框（與「參數現值」同一個已知取捨；`@media print` 的佔位文字會說明原因，
  摘要與 `.cq-more` 兩種措辭不同）。
- 影像：`D.loadHmiImage(path)` → `D.fetchJSON`（AES-GCM → gunzip）→ base64 → `Blob` → `URL.createObjectURL`；同一張圖多處共用，
  `CardView.destroy()` 呼叫 `D.revokeHmiImages()` 一次 revoke 並把 `card/hmi/*` 從 `D.cache` 丟掉。**`docs/db/index.html` 的 CSP `img-src` 必須含 `blob:`。**
- 標記**不燒進影像**：`.hmi-mk`（紅圈）／`.hmi-box`（物件矩形）是以百分比絕對定位疊在 `<img>` 上的空元素，所以同一張圖可給多個位號共用，放大時自動同步縮放。
  多處時另加 `.hmi-no`＝編號 ①②③（`card.js` 以 inline `transform` 逐個往右上／右下錯開，兩圈幾乎重疊時編號才分得出來）；
  `marks[0]` 拿 `.pri`（實線粗框、深紅編號），其餘 `.hmi-box` 改虛線；另有一句 `.sr-only` 供螢幕閱讀器。
- 放大：`.hmi-lb`（沿用 `.modal`）全螢幕疊層，✕／Esc／點背景關閉，**`AMS.overlay.open('modal', …, true)`（第三個參數 `force`）**
  ——全螢幕模態在平板／桌機也要用返回鍵關掉，不然 768px 觸控平板（有觸控、沒有實體 Esc、習慣手勢返回）按返回會整張查詢卡跳掉；
  `OV.open` 的 `popstate` 處理器本身不看寬度，所以 `force` 推進去的歷史一樣會被正確吃掉。
  ✕ 以 `.hmi-lb .modal-x { position: static; align-self: flex-end }` 排成影像**上方自己的一列**（原本絕對定位壓在影像右上角，會遮住畫面的 UNACKNOWLEDGED／告警列）；
  影像寬度上限由 `card.js` 依該圖長寬比換算成 `min(100%, calc((100dvh - 152px) * <ar>))`（108px 說明列＋✕ 那一列），高度一定塞得進視窗。
- **挑哪一張**：`hmiPick(meta, ex)` 先用 `meta.variants[ex.unit]`（執行時截圖逐選單機組各一張），挑不到才退回 `meta.file`；
  `hmiShot`／`hmiFrame`（長寬比）／`openHmiLightbox`（影像、寬度上限）**三處都要用它**，只改其中一處會讓佔位框的長寬比對不上真正載進來的圖。
  `hmiSrcText(meta, ex)` 產生 alt 與燈箱說明列的那句：執行時截圖寫「執行時畫面（YYYY-MM-DD 擷取，選單機組 X），畫面上的值是擷取當時的現值、不是即時值」
  ——**擷取日期與「不是即時值」這兩件事一定要寫出來**，不然現場人員會把一張舊截圖當成即時畫面；設計時影像維持「設計時影像（值顯示為 ###）」。
- 無影像的畫面只顯示名稱與路徑，並註明「這張畫面沒有影像（沒拍到執行時畫面，.cim 也沒有 ThumbNail 串流）」。
- 查無：一次講完掃描範圍（取 `index.hmi.stats`）——FF 設備（`flags.ff`）寫「查無（FF 訊號不在控制器 I/O 索引，位號字串也不出現在任何圖控畫面檔；已掃 248 個操作員畫面，另 225 個子目錄元件面板／函式庫也掃過字串（共 473 個 .cim））」，
  其餘寫「查無（已掃 248 個操作員畫面，…（共 473 個 .cim）：這些畫面都沒有引用此位號）」。
- `nav_all`：前端以 `.hmi-allnav`「（此畫面全部選單列）」顯示在導覽路徑旁（不只寫在來源字串裡）。`dcdas` 路線帶出 `unit` 之後目前實測為 0 組，前端仍保留這條分支。
- 手機（`.cq-body.narrow`）標記縮成 20px、縮圖滿寬、`.hmi-f .cf-v` 縮一級字；`.hmi-f .cf-v` 另設 `word-break: normal; overflow-wrap: break-word`
  （`.cf-v` 預設的 `word-break: break-word` 等於 `overflow-wrap: anywhere`，會把位號在 token 中間切成 `…LAB22BF001_X` / `Q01`）。
  列印時 `.hmi-screen` 不跨頁、標記以 `print-color-adjust: exact` 印出、放大層由 `.modal` 的列印規則隱藏。

### 已知限制（誠實標註）

- **FF 設備（351 台）完全無法對應**：FF 位號不出現在任何 `.cim` 字串裡（根目錄 248 個與子目錄 225 個都掃過，見上面「掃描範圍」）；這不是解析漏抓。
- **執行時截圖是 2026-10-04 的一次性快照，不是即時畫面**：值、告警數、時鐘都停在擷取當下，之後現場改了也不會變；前端每一處（摘要組標頭的 `.hmi-cap` 短籤、縮圖 alt、燈箱說明列、完整資料區的區段說明）都必須寫出擷取日期與「不是即時值」。要更新只能請使用者重拍、重跑 `hmi_runtime_map.py` 再重建。
- **同一張畫面只拍到一組選單機組時，另一組就沒有自己的影像**：目前 66 組全部有對應機組的截圖（實測 1298 組卡片區塊 1298 組命中自己那一組，0 次退回），
  但洞是存在的——`gtHA_Gen2_Gas_Fuel_Module_UX`／`gtHA_Gen2_SIL_FP_UX` 的選單有 G11./G12. 兩列而只拍到 G11.（那兩張是重貼，見步驟 0 的 `dropped`），只是目前沒有 AMS 位號落在那兩列。
  真的發生時前端會退回 `meta.file`（＝`meta.unit` 那一組）並在說明列與 alt **明寫**「⚠ 這張是選單機組 X 的畫面，沒有 Y 的截圖——位置對得上，數值不是這一組的」：
  版型相同所以紅圈位置仍然正確，**但數值不是那一組的，絕不可以不出聲**。`hmi_runtime_map.json` 的 `review`／`dropped`／`stats.clash` 就是用來發現「哪些選單列其實沒拍到」。
- **摘要組一開卡就抓「展開中」的畫面影像**（`fillHmi` 的 `inSum` 路徑對展開中的畫面刻意不延後，2026-10-03 修「摘要看不到圖控畫面」時定的；
  2026-10-05 起摘要組連 `<details>` 都沒有了，只有 > 3 張時第 2 張起才收合）：改成逐選單機組一檔之後，同一張畫面的 H11／H12 不再共用同一個路徑，
  `D.loadHmiImage` 以路徑為鍵的去重失效——最重的卡（14 組，另有約 7 台同樣）曾經是一開卡就解 14 檔 1,217 KB。
  2026-10-05 的折疊（使用者指定「超過 3 張只先展開第一張」）把它壓回 1 檔約 90 KB，其餘點開才抓；一般的卡 1~3 組、約 100~300 KB，全部直接載。
  **不要**把展開中的那幾張也改成延後：那正是 2026-10-03 回報「摘要看不到圖控畫面」的那條路徑。
- **23 個引用到 AMS 位號的畫面檔沒有 ThumbNail**（量最大的是 `HPOT_HP_OT_Temp_UX.cim` 158 筆、`HRSG_Hot_Reheat_UX.cim` 123、`HRSG_LP_Group_UX.cim` 94、`HRSG_LP_Common_UX.cim` 78）——2026-10-04 起這 23 個全部改用執行時截圖，所以**現行語料沒有任何一個被引用的畫面是沒有影像的**（`.hmi-noimg` 分支 0 筆，前端仍保留這條分支）。
- **來源裡沒有中文畫面名**，`title_zh` 一律 `null`；要中文只能另建人工對照表。
- `sec.hmi` 的 `ref` 取自該組排序後第一個命中物件，**不保證屬於某一個座標**（同組多個矩形共用一個 `ref`），不要當成「這個位置的物件屬性」。
  `ref` 裡仍可能留著 `{UNIT1_NO}`、`{Unit_NO}` 這類**未代入的畫面變數**——那是 `.cim` 裡的原文參照字串（設計行為，不是壞資料）。
- `unit` 欄＝「用哪一列選單開這張畫面」，不是儀器所屬機組（`BOP_Blowdown_Recovery_System.cim`、`Plant_Overview_UX.cim` 本來就同時畫兩部機）；
  69 台因此在同一張畫面列兩組、紅框完全相同，卡片以「以選單機組 X 開啟」表達這件事。
- 「所在位置」只描述 `marks[0]` 一處；其餘處只能靠圖上的 ②③ 對照，文字不會逐處列座標。

## v6（docs/db 站：P&ID 圖面位置；`tools/db/pid_lib.py`／`pid_index.py`／`pid_shots.py`／`pid_ocr.py`）

查詢卡再回答一題：「這台儀器畫在哪一份 P&ID、PDF 第幾頁、圖上哪個位置」。來源是工程文件庫 `paths.LIBRARY_ROOT` 裡現行的 P&ID PDF（**唯讀、現場走訪**），
不是 AMS 資料庫，也不讀 hst-docsearch 的全文索引（索引比磁碟舊，認不得剛進庫的新版次）。2026-10-08 第一次發布；
2026-10-10 經六組獨立查核後改過一輪——位置本身沒有錯，錯的是「一筆命中可以代表什麼」——本節寫的是改過之後的契約，數字取自那次建置
（`pid.json` sha1 `0c2f5f6c…`）。**寫報告、寫卡片文案一律取 `pid.json` 的 `stats`／`card/index.json` 的 `pid.stats`，不要抄這裡的數字。**

**範圍與文件集**（`pid_lib.build_corpus`；`stats.corpus`）：走訪 31,896 個 PDF → 只看檔名認出 P&ID 類 712 份（`kind_of`：檔名含 P&ID／PID／管線儀表流程圖／…系統圖，
GE 的 System Schematic／Instrument Diagram 等，或文件編號屬於 AFF01／GFD01／TFD01／BFD01 的 D 類圖；`EXTRA_FAMILIES` 明列檔名規則認不出來的發電機示意圖 EGJ01-D0004；
彙編夾 18 份、根目錄彙編／初稿 4 份不收）→ 同一張圖的各版次、HT1 舊編號、廠商檔名副本歸成一個**圖號家族**（398 張圖：HT 編號 382、廠商檔名 16；廠商檔名副本以
「文字層完全相同」或「KKS 標籤詞彙 Jaccard ≥ 0.6」認親，沒有文字層的才看標題而且要完全相同）→ **每個家族只留最高版次當代表檔**（順序：有 HT 編號 > HT0 > HT1 > 其他首碼 >
**版次高**（數字 > 字母 > 無；廠商檔名認 `_revX`）> 非副本夾 > 非 `_舊版` > 非「(2)」重複檔 > 修改時間新；版次一定排在資料夾旗標之前，緊接在編號後面的標題字不當版次）→
扣掉二、三號機組專屬圖（HT2-／HT3-／標題 UNIT-2、UNIT-3）26 張 ＝ **372 份圖 1,047 頁**。A4／Letter 直式的頁（長邊 < 1000 pt 且直式）是送審封面（240 頁），
不當位置也不進 OCR；其餘 807 頁是圖紙（595 頁有可用的文字層；212 頁沒有＝不到 30 個字或不到 400 個字元）。
**舊版次的座標絕不發布**：舊版與副本只留在統計（`stats.superseded_only` 列出只在舊版找得到的位號，現在是 0 支）；代表檔讀不了（壞檔、有密碼、零頁）時那張圖就沒有位置，
不會退回舊版（`unreadable_representative`，並印 `!!`）；讀不了的 PDF 只計數（`text_errors`），不讓整個流程中止。
母數與圖控相同：現行 AMS 位號扣掉 JK 開頭的 HART 多工器模組（1,928 → 1,679；直接呼叫 `hmi_index.load_ams`，兩邊才會永遠相同）。

四張**宣告＋建置時驗證**的表（都是 `pid_lib.py` 的常數，每筆附讀圖證據的註解；驗不過就不套用、計數並印出來，套用情形在 `stats.train`／`foreign`／`air`／`overrides`）：

| 常數 | 宣告的內容 | 建置時的把關 | 效果 |
|---|---|---|---|
| `TRAIN_TYPICALS` | 圖面自己聲明「同型各台共用」的圖：`1-TCM01-D1114`（畫 LCC10，代表 LCC20／LCC30）、`1-TDM01-D1205`（只畫 LAC50，代表 LAC60／LAC70） | D1114：圖上找得到 `P&ID is applicable for all condensate pumps`（兩邊去空白、轉大寫再比）。D1205 整份沒有文字層，改驗 OCR 對照表的**結構**：至少 10 列「同一列既有 LAC50 的格子、也有 LAC60／LAC70 的格子，而且設備段相同」（實測 189 列，`stats.train.evidence`） | 別台的位號取圖上那一台的**符號**位置：`rel:"train"`、`drawn_as`＝圖上畫的系統碼（`LCC10`／`LAC50`）。只認符號：清單／附註／旗標裡的字不代表別台畫在那裡 |
| `FOREIGN_SHEETS` | 圖上自己聲明「這一張不是本機組的組態」：`1-GFD01-D0013` 的 note 12（sheet 3、KKS 前綴 X2，只適用 unit 2-2） | 那句話要印在圖上；頁以**內容**認（文字層裡有 `X2`＋KKS 系統段的頁），不寫死 PDF 頁碼 | 那一頁（現在是 PDF 第 7 頁）的命中全部不發布（`stats.dropped.foreign_sheet` 70） |
| `AIR_SHEETS` | 儀用／廠用空氣**分配圖**：`1-AFF01-D0021`、`1-BFD01-D0006` | 逐頁驗（`air_sheet`）：頁面印著 INSTRUMENT AIR，而且 KKS 功能碼 QE／QF 開頭的標籤 ≥ 30 個（實測 D0021 第 2／3 頁 264／326 個；D0006 只有第 4 頁 89 個過關，第 2／3 頁 0 個） | 這種頁上**別的系統**的符號命中改成 `note:3`（那是這顆閥的供氣接點，不是閥在製程管線上的位置） |
| `HIT_OVERRIDES` | 人工讀圖確認、通用規則判不出來的逐處覆寫：`1-TDM01-D1205` 第 5 頁下緣與右下的兩個區域（迴路詳圖「TYPICAL FOR … TRANSMITTER」小圖） | 以家族＋PDF 頁＋轉正後比例的矩形認（不看位號、不靠清單順序）；沒有對到任何命中的條目計入 `overrides.unmatched` 並印出來——圖換版、頁序變了就要重新讀圖 | 中心落在區域裡的符號命中改成 `note:4`（套用 51 處，選級之後發布 45 處） |

三支工具照這個順序，輸出除了對照表都在 cardwork（不進 repo）：

| 步驟 | 程式 | 輸出 | 內容 |
|---|---|---|---|
| 0 | `tools/db/pid_ocr.py` | `tools/db/pid_ocr_map.json`（**進 repo**；807 頁、1,419,324 bytes、像位號的字 20,513 個） | **離線**（不在 `rebuild.py` 裡；要 `rapidocr-onnxruntime`，實測 1.2.3）。圖紙清單＝`pid_index --worklist` 的結果（`need`＝沒有可用文字層 OR 這份圖已有位號被文字層定位到 OR 這頁畫了某個 KKS 系統而 AMS 在該系統還有位號沒著落；`--scope all`＝每一張圖紙，這次 807 張全做）。每頁：定轉正角 R（文字層 ≥ 400 字用文字層，否則 OCR 定向投票）→ 以 `render_upright` 渲染轉正後的整頁 → 分塊偵測 → 辨識；配方 `r1b`（偵測 2.5 px/pt、渲染 4 px/pt、小字圖自適應放大、0／180 分類器）整包進快取鍵。逐頁快取 `paths.PID_OCR_CACHE`（`%LOCALAPPDATA%\AMS\pidocr\`，807 檔 25 MB；鍵＝路徑＋size＋mtime＋頁＋配方＋引擎版本與模型檔大小）。`--distill` 把快取裡「像位號」的字（`pid_lib.tag_like`：完整 KKS、系統段／設備段、GE 元件名、ISA 名、差一兩個形近字的 KKS；**OCR 原文、不先對 AMS**）寫成對照表；**與文字層位號重疊的字不寫**（用的是 `pid_index.text_tag_boxes`／`overlaps_text`，68,439 個）、圖框裡印的 CAD 檔路徑不寫（18 個）。**`--distill` 只寫有快取的頁**：快取不全時蒸餾出來的表是殘缺的 |
| 1 | `tools/db/pid_index.py` | `CARDWORK/pid.json`（517 KB） | 文件集 → 逐頁比對文字層（`match_page`）→ 併入對照表的 OCR 字（`match_ocr_tokens`）→ 四張宣告表 → 選級、排序、上限 → 圖框分區與字高。文字層字框快取 `paths.PID_TEXT_CACHE`（`pidtext\`，712 檔 14 MB；依 size＋mtime，PDF 一變就重抽）。**決定性**：鍵排序、清單排序、無時間戳、無本機絕對路徑（結尾以 regex 自檢）——同樣的輸入重跑逐位元組相同（2026-10-10 實測）。`--verify 位號…` 另畫疊框圖到 `%LOCALAPPDATA%\AMS\pidverify\`；`--worklist FILE` 寫 OCR 工作清單；`--trace FILE` 寫追查旁檔（每筆命中用到的特殊規則、每筆沒發布的命中與原因；**不屬於契約**）；`--no-ocr` 只用文字層 |
| 2 | `tools/db/pid_shots.py` | `CARDWORK/pid_shots/<slug>.webp`＋`index.json`（117 張、10,539,536 bytes） | 只渲染 `by_tag` 真的引用到的圖紙：轉正後**整張圖**一張影像、所有位號共用，標記不燒進影像。**四階灰階、不抖色、無損 WebP**；長邊＝clamp(2400, round(12 px × 圖紙長邊 pt ÷ `label_pt`), 3600)，讓位號那一行字約 12 px 高。量化（`RENDER_VERSION` 4，2026-10-10）：先量黑點（墨跡像素由暗到亮累計到 2 % 的那一階，≥ 24 才算），把 [黑點, 255] 拉到 [0, 255]——整張用灰色畫的圖才不會斷線（117 張裡 3 張會拉：TCM01-D1701 第 2 頁與 TDM01-D1205 第 4、5 頁）；再做 gamma 2 才取四階——淺灰的髮絲線與線條字留得住。**點陣頁例外**（`raster_page`：嵌入點陣圖合計蓋住頁面 30 % 以上，以未旋轉的 CropBox 計；現行 4 張：TDM01-D1205 第 7、8 頁的儀器清單、BMM01-D3702 第 2 頁、廠商檔名的 Service Water Pumps 圖）：不拉黑點、不偏暗，回到等距四階——點陣頁的小字本來就粗，再偏暗會把 0／6／8／B 的字腔填滿（2026-10-10 在真實站上看到 C10LAC60 讀起來像 C13LAC80）。逐位元組決定性（實測 117 張重出後全部相同；PyMuPDF 1.27.1、Pillow 12.2.0）。快取：`index.json` 的參數與 webp 都在就跳過；`pid.json` 記的 PDF size／mtime 與磁碟不符、`rot` 不是 0／90／180／270、頁碼超出範圍都只算那一張失敗（回傳碼 1，上一次的影像原樣留著）；`--max-minutes` 做不完回傳碼 2；不再被引用的 `<slug>.webp` 刪掉 |

**全專案只有一個轉正慣例 R**：R＝在頁面自己的 `/Rotate` **之上**再順時針多轉幾度才是正的（0／90／180／270）。`pid.json` 的 `sheets[].rot`、`pid_ocr_map.json` 的 `pages[].rot`、
`pid_shots/index.json` 的 `rot` 全部是 R；渲染＝`page.get_pixmap(matrix=fitz.Matrix(z, z).prerotate(R))`（`get_pixmap` 自己會套 `/Rotate`）。
PyMuPDF 的 `get_text('words')` 座標是**未旋轉**的頁面空間，有 `/Rotate` 旗標的頁直接除以 `page.rect` 會整頁標錯而且不報錯——一律走 `pid_lib.to_upright_frac(page, rect, R)`
（先乘 `rotation_matrix` 到顯示空間，再依 R 換到轉正後的比例）。`/Rotate` 不等於轉正（D0027 第 4 版的圖紙 `/Rotate` 0、R＝270）。R 怎麼定（`sheets[].rot_method`）：
`text`＝文字層 ≥ 400 字，取字數最多的書寫方向當水平（大圖若因此直立，改看兩個橫式候選）；`ocr`＝文字層不夠，用對照表的 `rot`（`pid_ocr` 的 OCR 定向投票）；
`text-thin`／`default`＝兩者都沒有時的退路。被引用的 117 張：`text` 109、`ocr` 8；R＝0 的 116 張、R＝270 的 1 張（KND01-D0027-4 第 2 頁）。
**兩個軸要分開驗**：TCM01-D1114 第 5 頁、BDM01-D2111 第 3 頁是 `/Rotate` 270、R＝0（驗 `rotation_matrix` 那一步）；KND01-D0027-4 第 2 頁是 `/Rotate` 0、R＝270（驗 R 那一步）。
對照表的 `rot` 與文字層定出的 R 不同、或它記的 `w_pt`／`h_pt` 與「照它的 `rot` 轉正後的尺寸」差超過 2 pt 的頁，OCR **整筆不用**（`stats.ocr_map.rot_conflict`／`size_mismatch`）。

### `pid.json`（`pid_index.py` 的輸出）

`{"kind":"pid","generated_by":"tools/db/pid_index.py","version":1,"sheets":{…},"by_tag":{…},"stats":{…}}`

- **圖紙鍵 slug**＝`<文件編號-版次｜x>_<sha1(文件庫相對路徑)[:8]>__p<PDF 頁次>`（`HT0-1-KND01-D0027-4_1030bef1__p2`；檔名沒有 HT 編號的是 `x_…`）。
  `sheets` 的鍵、`by_tag[*].sheet`、`pid_shots` 的檔名與 `index.json` 的鍵、`sec.pid` 的 `extra.s`、`index.pid.sheets` 的鍵、`card/pid/<slug>.json` 都是它。
  圖的身分（`doc`／`rev`／`title`）**全部取自檔名**（圖框裡印的編號不可靠），頁次只說「PDF 第 p 頁」。
- `sheets[slug] = {rel, file, doc, rev, title, page, pages, rot, rot_method, w_pt, h_pt, label_pt, grid, words, ocr, tags, src:{size, mtime}}`：只列**被引用**的圖紙。
  `rel`＝相對文件庫根目錄的 posix 路徑（**任何輸出都不含本機絕對路徑**）；`w_pt`／`h_pt`＝轉正後的尺寸；`label_pt`＝這張圖位號字的字高（有文字層＝位號字框高度的中位數；
  沒有文字層＝OCR 偵測框短邊的中位數 ÷ 1.3，換算成字形本身的高度；`pid_shots` 據此決定影像大小）；`words`＝文字層字數（0＝整頁沒有文字層）；`ocr`＝這一頁用到了對照表；
  `tags`＝這張圖上有幾支位號；`src`＝代表檔的大小＋修改時間（`pid_shots`、`build_card_aux` 都拿它核對是不是同一版 PDF）；
  `grid`＝圖框分區 `{ok, src, cols:{kind, labs:[[位置, 標籤]…], pitch}, rows:{…}}` 或 `null`。
- `by_tag[位號] = [hit…]`，hit＝`{sheet, x, y, w, h, label, rel, drawn_as, how, form, note}`＋條件性的 `conf`／`raw`／`zone`／`zone_near`（一律用 `.get()` 讀）：
  - `x`／`y`＝框的**左上角**、`w`／`h`＝寬高，都是轉正後整張圖的 0~1 比例、左上為原點（五位小數）；可直接乘 `pid_shots` 那張影像的寬高。
  - `label`＝圖上的字。文字層＝圖上寫的字（拆寫的片段以一個空白相接）；OCR＝**這一筆自己的**正規化讀法（前綴照圖上寫的＋核心＋尾碼；斜線與機組清單保留圖上的寫法
    `C10PHC10/20BT011`、`G11/12HAP65BP001`），不含併進同一框的鄰字、功能碼、管徑、括號。
  - `rel`（發布的五級）：`exact`＝圖上畫的就是本台（`=G12…`、`12HAH…`）；`neutral`＝圖面不分機組（位號不帶機組，或寫佔位符 `=GXX…`）；`typical`＝圖上畫的是同一 Block 的另一部氣機
    （G12 的位號落在畫成 11 的標籤上）；`loop`＝ISA 迴路名只對到迴路號（`1-PIT-CW014-1` ↔ AMS `1-PI-CW014-1`）；`train`＝`TRAIN_TYPICALS`。
    `drawn_as`＝圖上寫的機組（`G11`／`11`／`C10`）或系統碼（`LCC10`／`LAC50`）。
  - `how`：`text`｜`ocr`。`form`：文字層 `word`｜`prefixed`（`=G11` 另成一個文字物件）｜`stacked`（系統段在上一行）｜`inline`；OCR `ocr`｜`ocr-fix`（經形近字修復）｜`ocr-stacked`｜`ocr-inline`（兩個框合併）。
  - **`note` 代碼**：`0` 儀器符號旁的標籤｜`1` 附註句子（≥ 4 個字的一行文字）、整齊排列的清單欄、OCR 讀到的整頁儀器清單的一格｜`2` 跨圖訊號旗標（上緣有訊號編號、下緣有「DCDAS TO／FROM」或去向圖號的箭頭框；`…BL001/2/3` 連號也算）｜`3` 空氣分配圖上的用氣點｜`4` 迴路詳圖 TYPICAL 小圖。
    1～4 是**引用**——圖上「提到」這支位號的地方，不是儀器符號的位置。現行各代碼的命中（`stats.hits_by_note`）：1,658／36／15／72／45。
  - `conf`＝OCR 辨識分數（`how:"ocr"` 才有）；`raw`＝這個標籤 OCR 原本讀到的字（**只有 `form:"ocr-fix"` 才有**，如 `C10LAC50 BTO11`）；
    `zone`＝圖框分區 `C-5`（有格線而且點在圖框內才有）、`zone_near`＝離分區邊界不到格距 3 %（卡片寫「約 C-5」）。
  - **同一支位號的各筆不一定同一級**：符號是 `typical`／`train` 時，印著位號全名的引用（`exact`）會一起發布——現在 29 支位號帶兩級（`exact`＋`train` 28、`exact`＋`typical` 1）。
    所以「每支位號只發布最好的一級」說的是**符號**；`stats.by_rel`／`by_how` 統計的是每支位號的第一筆。
- `stats`：`located`／`located_pct`／`not_located`、`located_symbol`／`located_note_only`／`located_ref_only`（只有引用的位號，依代碼分；混著的記 `mixed`）、`hits`／`hits_by_note`、
  `by_rel`／`by_how`／`by_proto`／`proto_total`／`by_shape`／`shape_total`、`tags_with_ocr_hit`／`tags_multi_sheet`／`tags_per_sheet_max`、`drawings`／`pages`／`pages_cover`／`pages_sheet`／`pages_text`／`pages_sparse`／`pages_ocr`、
  `sheets_referenced`／`drawings_referenced`／`sheets_with_grid`／`sheets_without_label_pt`、`rot`／`rot_method`、`dropped`（`sfx_mismatch`／`foreign_sheet`／`other_class`／`scope_letter`／`ocr_list_with_symbol`…，只列非 0 的）、
  `train`／`foreign`／`air`／`overrides`、`ocr_map`（`present`／`pages`／`stale`／`unused`／`cover`／`rot_conflict`／`size_mismatch`／`tokens_used`／`tokens_dup_text`／`tokens_low_score`）、`ocr_near`（`admitted`、`tags`）、
  `superseded_only`、`corpus`、`limits`（`sheets_per_tag` 6、`hits_per_sheet` 8、`ocr_min_score` 0.75、`ocr_near_score` 0.7、`min_orient_chars` 400、`sparse_words` 30）。
- 2026-10-10 的數字：定位 **1,582／1,679（94.2 %）**；第一筆的級別 `exact` 818、`neutral` 446、`typical` 244、`loop` 6、`train` 68；第一筆來自文字層 1,483、OCR 99；HART 1,243／1,328、FF 339／351；
  KKS 1,203／1,217、GE 元件名 373／385、ISA 6／51、其他（時間戳、殘缺名稱）0／26；命中 1,826 處、117 張圖紙（54 份 PDF）；只有引用的位號 4 支（`{"1":3,"mixed":1}`）。

### 比對規則（`pid_lib`；每一條的由來與案例在檔頭）

- **兩邊都正規化**：圖上 `=G11HSD10QN101` →（字母 G、機組 11、核心 `HSD10QN101`）；AMS `G12HSD10QN101` → 同一個核心。AMS 這邊的裝飾（尾端 `_`、`_01`）剝掉再比。
- **機組關係**（`relation`）：同字母同機組／只寫數字且相同 → `exact`；佔位符或沒寫機組 → `neutral`；同字母、同一 Block 的另一部氣機 → `typical`。
  **絕不歸戶**：字母不同（C10 與 G11 是不同設備）、別的 Block（G21、C20）。`SCOPE_LETTER`（`TFD01`／`EGK01`→S、`GFD01`／`EGJ01`→G）：不寫機組的圖上，沒有前綴的標籤只可能屬於那個機組字母
  （汽機圖上的 `LBA10BT001` 是 S10 的，不是 G12 的同核心位號；`dropped.scope_letter`）。
- **尾碼必須相等**（`_attribute_kks`）：標籤核心後面帶元件字母／元件碼／子項的（`…BP272C`、`…BT044A`、`…BT008AB`、`…QN001N1`、`…BL001-BL01`）是**另一個項目**，
  只歸給自己尾碼相同的 AMS 位號（`S10MAV01BP272C` 的 `C`），沒有「退而歸給不帶尾碼的那支」。文字層與 OCR、符號與清單都一樣；`train` 也要尾碼相等。
  不發布的計入 `dropped.sfx_mismatch`（129）。
- **標籤拆寫**（`page_candidates`，以該字自己的閱讀方向為準，所以直書的標籤同樣適用）：系統段在設備段的上一行（`stacked`）、`=G11` 另成一個文字物件接在前面（`prefixed`）、同一行隔一格（`inline`）。
- **GE 元件名**嚴格整詞相等（`96FG-1` ≠ `96FG-1A`；AMS 的 `_01` 兩位數尾碼剝掉再比）；**ISA 名**全名相等＝`exact`，只對到（機組數字、功能首字母、迴路、序號）＝`loop`——開頭的機組數字要一起比（`2-PIT-…` 不是 `1-PI-…`）。
- **文字層為準**（`pid_index.text_tag_boxes`／`overlaps_text`）：OCR 的字只要與文字層任何一個「含有 KKS 核心或像位號」的字重疊（容許圖寬 0.4 %／圖高 0.6 %）就丟掉，OCR 只補文字層沒有的地方。
  含有 KKS 核心的文字層字**一律算**，不只是比對器認得的寫法——文字層有的字，OCR 就沒有發言權；文字層比對器不認的寫法，寧可兩邊都不收。
- **OCR 的字**（`ocr_scan`／`match_ocr_tokens`）：用搜尋而不是整詞相等，一個框裡有幾個標籤就切成幾筆（框沿閱讀方向依字元位置等比例切開）；
  辨識分數 < 0.75 的字不用；只做**安全的形近字修復**（字母位出現數字或反過來時換成形近字，至多修 2 個字，**展開後只落在一個 AMS 核心才接受**）；不做編輯距離比對
  （834 個 AMS 核心有 802 個存在只差一個字的鄰居）。機組前綴讀不出來的整個不收；沒寫機組的讀數只在 `SCOPE_LETTER` 的圖上才收（`dropped.ocr_nounit`）。
  機組清單（`G11/12HAP65 BP001`）兩部機各自 `exact`；斜線系統段（`C10PHC10/20 BT011`）展開成兩支。整頁儀器清單的一格（`ocr_table_tokens`：≥ 5 個完整位號由上到下緊鄰、左緣或中心對齊）記 `note:1`。
- **差一點點的疊寫標籤**（唯一放寬到 0.70 的地方）：上下兩行拆寫的閥號，設備段的分數在 0.70～0.75 之間時，只有在正上方的系統段 ≥ 0.75、那個系統段沒有別的設備段可接、合起來是 AMS 核心、
  這一頁沒有別的讀數是同一個核心、而且這支位號在這一頁的文字層沒有著落，才接受。每次建置都印出接受了幾處、是哪幾支（`stats.ocr_near`；現在 6 處：`G11HAD10QN003`／`QN004`／`QN006`、`G12HAD10QN006`、`G11`／`G12LAB65QN003`，分數 0.734～0.749），每一處都要讀圖核對。

### 選級、排序與上限（`pid_index.select`）

- **等級只看符號命中（`note:0`）**：`exact` > `neutral` > `typical` > `loop` > `train`，每支位號留最好那一級的符號。引用（`note` 1～4）絕不把等級較低的符號擠掉；留下來的引用＝與符號同一級的，
  加上「圖上印的就是這支位號自己的全名（`exact`）而符號是較低的一級」的——但同一張圖上這支位號另有等級更好的命中時，等級較差的引用不留。沒有任何符號命中的位號照樣發布（等級取引用裡最好的一級）。
- 已經有符號位置的位號，**OCR 在清單裡讀到的那幾格不發布**（`dropped.ocr_list_with_symbol` 13）：清單裡上下左右都是只差一個數字的兄弟位號，同類誤讀最容易歸錯戶。
  例外：符號是 `train` 的位號，清單格就是對照的憑據，要留。文字層的附註／清單不受影響。
- **排序**：符號在引用之前 → 文字層在 OCR 之前 → 圖號 → 頁 → 由上到下、由左到右；圖紙的順序＝第一筆命中出現的順序，同一張圖的命中排在一起。
  所以 `by_tag[*][0]` 是「最像儀器本身」的那一處，`build_card_aux` 的 `marks[0]` 就是它。
- 每支位號最多 6 張圖、每張圖最多 8 處（超過的丟掉並計數；現在沒有一支碰到上限：最多 3 張圖、一張圖 5 處）。

### `pid_ocr_map.json` 與 `pid_shots/index.json`

- 對照表：`{"kind":"pid_ocr","generated_by":"tools/db/pid_ocr.py","version":1,"recipe":{…},"stats":{…},"pages":{"<相對路徑>|<頁>": {size, mtime, rot, rot_method, w_pt, h_pt, boxes, dup_text, tokens, border}}}`，一頁一行（方便看 git diff）。
  `tokens`＝`[[OCR 原文, cx, cy, w, h, 分數]…]`（**中心**＋寬高，轉正後整張圖的 0~1 比例，五位小數；依 cy、cx、原文排序）；`border`＝`[[字, cx, cy]…]`（貼著圖紙邊緣 3 % 以內的 1 個字母或 1～2 位數字，圖框分區用；
  文字層自己有格線的頁不寫）；`size`／`mtime`＝OCR 當時那份 PDF 的身分——**與磁碟上的檔不符＝過期，`pid_index` 整筆不用**（`stats.ocr_map.stale`）。`recipe` 含引擎身分（rapidocr 版本＋三個 onnx 模型檔的大小）。
  壞檔（不是合法 JSON、`kind` 不對、某一頁的 `tokens` 格式不對）`pid_index` 以一行訊息中止並指出是哪一頁。
- `pid_shots/index.json`：`{"<slug>": {file, w, h, bytes, bp, raster, long, levels, rot, ver, src:{size, mtime}}}`（`bp`＝量到的黑點，0＝沒有拉伸；`long`＝長邊像素；`levels`＝灰階數 4；`ver`＝`RENDER_VERSION`）。

### card aux 的 `sec.pid`、`card/pid/*.json`、`index.pid` 與 docs

`build_card_aux.py` 的 `--pid`（預設 `paths.PID_JSON`）／`--pid-shots`（預設 `paths.PID_SHOTS`）／`--no-pid`，`--recompare` 同樣吃。以**現行 AMS 位號**（不是 alias）對照 `pid.json.by_tag`。
`--no-pid` 的 `--recompare` 保留上次發布的 `sec.pid`／`index.pid`／`card/pid/*.json`／`docs` 的 `pid|…`／`stats.pid`（鍵序與重算時相同，同樣的資料產出同樣的位元組）。

- `sec.pid = {rows: [[欄位, 值, lvl, 來源字串, extra]]}`：每張圖紙一組 **5 列**——`P&ID 圖面`（`HT0-1-KND01-D0027 Rev.4　HRSG SCR System P&ID`）、`圖面頁次`（`PDF 第 2 頁（共 3 頁）`）、
  `所在位置`（`圖面左 47%／上 71%（圖框分區 C-5）`；多處時「＝圖上標記 ①；這支位號在同一張圖另有 3 處（圖上 ②、③、④），其中 ②、③、④ 是跨圖訊號旗標（不是儀器符號的位置）」）、
  `圖上標示`（`OCR 讀到的字：=G11HSD10QN101（這張是以 G11 繪製的典型圖，本台 G12 取同一位置）`）、`對應方式`（`OCR 讀圖（圖上的位號是線條字，不在 PDF 文字層；辨識信心 0.91）`）。
  組的順序＝`pid.json` 裡各圖紙第一次出現的順序。現在 1,582 台、1,770 組（1,395 台一組、186 台兩組、1 台三組）。
- **`lvl` 不新增分級**：這一組的 ① 是文字層命中而且 `rel` 是 `exact`／`neutral` → `doc`；其餘（`typical`／`loop`／`train`，以及所有 OCR 命中）→ `inferred`。
  以**那一組自己的 ①** 為準，與 `note` 無關（一塊只有訊號旗標的圖紙，旗標是文字層印的本台位號時仍是 `doc`——「文件上印著這串字」是事實，「這一處不是儀器符號」由 `note` 與文案交代）。
  來源字串＝`文件 · <檔名> 第 N 頁`／`推論 · …`。
- 每列 `extra` 都帶 `{s: 圖紙鍵, g: 組序}`；**第一列**另帶（現在 1,770 組裡各鍵出現的組數）：
  - 一定有：`d`（`docs` 的鍵＝這張圖自己的那份 PDF）、`p`／`n`（PDF 頁次／總頁數；`pid.json` 的 `pages` 不明時沒有 `n`，現在每一組都有）、`img: true`、`marks`、`drawn`（圖上畫的字，去掉句尾標點與不成對的括號）、`unit`（圖上畫的機組或系統碼；只寫數字的已補上本台的機組字母）、`rel`、`how`（都是 ① 的）。
  - `zone`（1,562 組）／`zone_near: 1`（172）：① 的圖框分區；沒有就只寫百分比。
  - `conf`（191）＝① 的 OCR 辨識信心（① 是 OCR 才有）；`conf_min`（191）＝這張圖上所有 OCR 標記裡最低的信心；`confs`（191）＝逐處的信心，與 `marks` 一一對應（文字層的那幾處是 `null`）。後兩個只要有任何一處是 OCR 就帶——**紅字看 `conf_min`，不是只看 ①**。
  - `notes`（137）＝逐處的 `note` 代碼，與 `marks` 一一對應；這張圖上有任何一處是引用才帶。`note`（116）＝這張圖上**每一處**都是引用時才有：代碼都相同＝那個代碼，不同＝`1`。沒有 `note`＝① 是儀器符號旁的標籤。
  - `fix: 1`（32）＝① 是 `ocr-fix`；`raw`（32）＝OCR 原本讀到的字。`odd: 1`＝① 是 `exact` 而圖上的字與位號對不起來（`pid_label_is_tag` 為假；產生器照規則輸出時是 0 筆，建置時 `pid_odd_labels` 會印出來，不擋建置）。
- `marks: [[中心 x, 中心 y, 框寬, 框高]]`（0~1 比例、左上原點；`pid.json` 給的是左上角＋寬高，這裡換成與圖控相同的「中心＋寬高」；完全重疊的只留第一筆）。
  **`marks[0]` 就是「所在位置」那列描述的那處**；符號標籤排在引用之前（穩定排序，同級維持 `pid.json` 的順序），前端照陣列順序編號。
- **文案規矩**（`pid_label_text`／`pid_pos_text`／`pid_how_text`；`tools/tests/test_pid_wording.py` 逐條釘住）：
  「與本台位號相同」只在圖上的字正規化後**真的等於**位號時才寫（省略機組字母、少了 AMS 的 `_01`、幾支位號合寫成一個標籤各有自己的說法；說不出差在哪裡的寫「請對照圖面確認」）；
  OCR 讀到的字前面標「OCR 讀到的字：」；`ocr-fix` 不寫「相同」，改寫「OCR 讀成「<raw>」，相近字元（0／O、8／B…）校正後才對上本台位號」；
  ① 是引用時句尾講明是哪一種（1 `這一處是圖上註記或表格（儀器清單）裡的文字，不是儀器符號旁的標籤`｜2 `這一處是跨圖訊號旗標（接往另一張圖的訊號引用），不是儀器本身的位置`｜
  3 `這一處是儀用／廠用空氣分配圖上的用氣點（這顆閥的供氣接點），不是閥在製程管線上的位置`｜4 `這一處在圖紙上的迴路詳圖（TYPICAL 小圖）裡，不是主流程圖上的位置`；認不得的代碼一律當「不是儀器符號旁的標籤」），
  再接「儀器符號畫在這台設備的另一張圖紙上」或——這支位號在任何一張圖上都沒有符號時——「這次比對（PDF 文字層＋OCR）沒有讀到這支位號的儀器符號，不代表圖上沒有畫，請開 PDF 確認」（不可以寫成「圖上沒有」：C10LAC50BT029 的球泡明明畫在圖上，只是 OCR 沒讀到）；
  OCR 命中在清單頁或整頁沒有文字層的頁不說「線條字」（改說那一頁／那一處沒有 PDF 文字層）；辨識信心印兩位小數，四捨五入後看不出低於 0.8 的多印一位（0.799）。
- **影像**：`docs/db/data/card/pid/<slug>.json ＝ {w, h, mime:"image/webp", b64}`，每張圖紙一檔、畫在上面的所有位號共用，**走既有 `*.json` 加密路徑**（與 `card/hmi/` 同一種包法）。
  現在 117 檔：明文（base64）14,177,304 bytes、密文 10.7 MB（每檔 21～354 KB）；影像 2400～3600 px，解碼後每張 16～37 MB（寬×高×4）。只發布真的有設備引用的圖紙。
- `card/index.json` 新增 `pid = {sheets:{slug:{doc, rev, title, name, page, pages, d, file, w, h, bytes, rows, ocr}}, files:[…], bytes, note, stats}`：
  `name`＝真正的檔名、`d`＝`docs` 的鍵、`file`＝`card/pid/<slug>.json`、`w`／`h`＝影像像素、`rows`＝有幾台設備畫在這張圖上、`ocr`＝這一頁用到 OCR 結果；`files` 是影像清單——
  `tools/verify_encrypted.py` 以它認得這些密文不是孤兒，`extract_db.data_build` 的雜湊涵蓋 `card/**/*.json`。
  `stats`＝`pid.json` 的 `stats` 裡 `PID_STATS_KEEP` 列的鍵原樣帶過來（`ams_tags`／`ams_tags_base`／`located`／`located_pct`／`located_symbol`／`located_note_only`／`located_ref_only`／`not_located`／`hits_by_note`／
  `by_proto`／`proto_total`／`by_rel`／`by_how`／`tags_with_ocr_hit`／`drawings`／`pages`／`pages_cover`／`pages_sheet`／`pages_text`／`pages_sparse`／`pages_ocr`／`sheets_referenced`／`drawings_referenced`／`dropped`／`ocr_map`；
  `corpus`／`limits`／`superseded_only` 這些大塊不進站），再加這次實際發布的數字：`devices`（有 `sec.pid` 的設備數）、`devices_ref_only`（每張圖上都只有引用的設備數，現在 4）、`tags`、`tags_unpublished`（`pid.json` 有、現行設備總表沒有的位號）、
  `images`、`docs`、`no_url`／`no_url_docs`（沒有雲端硬碟連結的圖紙張數／PDF 份數，現在 0）。`index.stats.pid`＝同一份再加 `bytes`；`index.source_stats.pid` 再加 `notes`。
  **卡片的「查無」文案與 `searched.pid[0].why` 的數字全部取自這裡，不寫死。**
- `index.searched.pid[0]`＝把「文件庫現行的 P&ID 圖面」整批當一份文件描述（`doc_id: "pid-drawings"`、`rev: "372 份圖面"`、`ref`、`title`、`folder`、`why`）；`index.kind_label.pid`＝`P&ID 圖面`。
- **docs 與雲端硬碟連結**：每份被引用的 PDF 登記一筆 `docs["pid|<文件編號>|<版次>"] = {title: 真正的檔名, folder: 文件庫相對資料夾, why, url?}`（檔名沒有 HT 編號的用 `pid|<sha1(相對路徑)前 12 碼>|`；
  兩個不同的檔撞同一組編號＋版次時後者也退用 sha1 鍵），現在 54 筆。**連結只給「位置讀自的那一份檔」**（`pid_own_urls_only`）：`add_drive_urls` 對一般文件會退而連到同編號的別版次並加 `url_note`，
  `pid|…` 不准——座標是從這一版讀出來的；drive_map 沒有那一份檔就不附連結並計入 `stats.pid.no_url`，**永遠沒有 `url_note`**。唯一的例外是同一份檔的本機檔名：
  雲端硬碟桌面版替撞名的項目在本機檔名尾端加的「 (N)」雲端上並沒有，精確路徑對不到時只再試去掉那個尾碼的名字（現在 2 份，`why` 會補一句說明）。
- 02.json 的規格（`extract_db.py`，本機靠 `patch_site_spec` 進站）：摘要組 `{"key":"pid","label":"P&ID 圖面位置（這台儀器畫在哪一張圖、圖上哪裡）","kind":"pid"}`——不收合、不帶 `note`，排在 `hmi` 組**之前**
  （`summary.groups` 現在的順序：dev、range、valve、dcs、ctrl、draw、docs、**pid**、hmi、〔前端插入的備品庫存〕、search）；附加區段 `{"key":"pid","label":"P&ID 圖面位置","kind":"pid","note":…}` 排在 `docsearch` 之後、`hmi` 之前。
  區段說明文字不寫死任何張數、頁數、涵蓋率。

### 建置關卡、寫檔順序與 `rebuild.py`

- **缺檔不靜默降級**：沒有 `pid.json`、或有 `pid.json` 而沒有 `pid_shots/index.json`，又沒給 `--no-pid` → 與 dcdas／docsearch／hmi／drive_map 一樣以非 0 結束，而且是在動資料目錄之前。
- **`pid_check`**（`load_pid` 時一次查完，有任何一項就列出來並以非 0 結束，不發布成「只有文字沒有圖」）：`by_tag` 引用的圖紙都在 `sheets`；圖紙鍵合乎檔名規則、等於 `pid_slug(rel, page)`、不分大小寫也不重複（建置機是 Windows，Pages 分大小寫）；
  `rel` 是文件庫相對路徑；每張被引用的圖紙在 `pid_shots/index.json` 有一筆、檔案在、是 WebP 且檔頭的寬高與索引相同、`rot` 與來源 PDF 的 size＋mtime 和 `pid.json` 相同（不同＝影像是另一版 PDF 或另一個角度畫的，標記會整批落在錯的地方）；
  每筆命中的 `rel`／`how` 合法、`note` 是 0 或正整數、框的中心在圖內。
- **同一個框不可被不相干的位號認領**（`pid_shared_boxes`，屬於 `pid_check`）：同一張圖上左上角座標（取到小數 4 位）相同的框被兩支以上的位號認領時，正當的共用只有三種——機組雙胞胎與 AMS 的 `_01`／`_` 重複名稱、
  `train`（鍵換成圖上畫的那一台再比）、標籤本身合寫了幾支位號（斜線後面接數字）；`loop` 不參加比較。其餘＝產生器把別的儀器的標籤算了進來（實例：`S10MAV01BP272` 與 `S10MAV01BP272C` 曾經互掛），
  建置機分不出誰對，**擋下來不發布**。
- **寫檔順序**（`write_output`）：圖紙影像先只收在記憶體（`pid_collect` 不寫檔）→ 分塊與 `index.json` 全部序列化並通過「不含本機絕對路徑」自檢 → 才動資料目錄：換掉 `aux-*.json` → 整個清掉 `card/pid/` 重寫（掉出覆蓋範圍的圖紙不留孤兒密文）→ 寫 `index.json` → `manifest.build` → 加密 → 戳記。
  自檢之前失敗，資料目錄裡的 `card/` 原封不動。（圖控的 `card/hmi/` 仍在最前面先寫，那一段照舊。）
- **`rebuild.py`**：`run_pid` 在圖控三步之後、`build_card_aux` 之前跑 `pid_index` → `pid_shots`（順序固定，與圖控相反：先定位才知道要出哪些圖）；`--skip-pid` 沿用 cardwork 裡上次的 `pid.json`／`pid_shots`。
  `pid_flags`：cardwork 有 `pid.json` 就明指 `--pid`／`--pid-shots`，連 `pid.json` 都沒有才 `--no-pid`。沒有 `pid_ocr_map.json` 時只用文字層（印一句提醒）。
  **站台規格自動套用**（`spec_lacks_pid`）：這次會發布 P&ID，而已發布的 02.json 還沒有 `pid` 摘要組／區段、**或**那個區段的內容與 `extract_db.SECTIONS_AUX` 現在的不同 → 等同 `--spec`（否則 `sec.pid` 與影像照樣發布，卡片卻沒有地方顯示，或永遠拿不到新的說明文字）。
  `patch_site_spec` 排在各產生器之後、`build_card_aux` 之前；`build_card_aux` 沒跑完時把 02／13 換回這次重建之前的內容（`spec_snapshot`），再把明文加密回去。
  **大聲的警告**（`pid_loud`；不解析輸出文字，只讀 `pid.json` 的 `stats`；回傳碼不變）：`stats.ocr_map` 的 `stale`／`rot_conflict`／`size_mismatch` 不是 0，或重跑之前靠 OCR 定位（第一筆是 OCR）的位號這次整支不見了，
  就印一段 `!! ====` 框起來的訊息，結尾在「rebuild 完成」之前**再印一次**。`pid_index` 自己也印 `!!` 開頭的行點名是哪幾份圖。

### 前端（card.js `fillPid`／`pidMeta`／`pidView`／`pidMini`／`pidShot`／`pidLoad`／`openPidLightbox`；core.js `D.loadImage`／`D.revokeImages`；app.css）

- 摘要組與附加區段都走 `fillPid(sec, ix, grid, mode, inSum)`；`inSum` **只決定版面**：摘要組是「圖紙標頭＋PDF 連結列＋影像」（`.sum-pid { grid-column: 1 / -1 }` 佔整列寬），完整資料區另有五個欄位與逐格來源。
  容器 class：`.sum-pid`／`.aux-pid`；區塊外殼、標頭、收合提示與標記元素沿用圖控的 `.hmi-screen`／`.hmi-head`／`.hmi-exp`／`.hmi-mk`／`.hmi-box`／`.hmi-no`，另掛 `.pid-sheet`／`.pid-head`；影像容器是自己的（`.pid-shot`／`.pid-view`／`.pid-stage`／`.pid-mini`）。
- **`pidMeta(ix, ex)` 是 `{file, w, h}` 的唯一出處**（細部視窗、小地圖、燈箱三處共用；各讀各的話舞台的長寬比、標記的百分比位置與載入後的影像會對不起來——同圖控 `hmiPick` 的教訓）。
  每張圖紙只有一張影像（沒有逐機組的變體）；沒有影像或長寬不明時 `file` 是 `null`，區塊改印一句話（`.pid-noimg`；現行資料 0 筆）。
- **同一張影像三個視角**（圖紙長邊 2400～3600 px，整張縮進卡片一個字都讀不到）：**細部視窗** `.pid-view`（舞台 `.pid-stage`＝整張圖紙，寬＝影像寬 × `--pid-k`，現在寬窄版都是 1＝一個影像像素一個 CSS 像素；
  以純 CSS 的 `clamp()` 把標記 ① 擺到視窗正中央、同時不讓圖紙邊緣縮進視窗）、**小地圖** `.pid-mini`（同一張影像縮小；`.pid-dot` 紅圈＝每處標記、`.pid-rect` 藍框＝細部視窗的範圍，由一個全卡共用的 `ResizeObserver` 重算）、
  **燈箱** `.pid-lb`（沿用 `.modal.hmi-lb`）：開啟時一個影像像素一個 CSS 像素、對準 ①；滾輪／雙指／＋ −／鍵盤縮放（上限 `PID_ZMAX`＝3，下限＝看得見整張圖）、拖曳平移、「全圖」「回到標記」、多處標記時「下一處」；
  縮放是改舞台的 width／left／top，不用 `transform: scale`（標記的框線與編號粗細不變）。關閉流程同圖控燈箱（✕／Esc／背景／返回鍵，`AMS.overlay.open('modal', …, true)`），另有 Tab 焦點圈。
  卡片裡的細部視窗不接手勢（在會捲動的卡片裡攔滾輪／拖曳會讓手機捲不動頁面）。深色主題把圖紙反相，列印還原。
- **標記不燒進影像**：有框的（文字層／OCR 的字框）只畫外框線、往外推幾個像素（框壓在位號那幾個字上，填色會把字蓋掉）；寬或高為 0 的才畫圈。`marks[0]` 拿 `.pri`（實線；其餘虛線）。
  多處時掛編號牌 `.hmi-no`：**印一般數字 1、2、3**（紅底圓牌＋白字；圓圈數字 ①②③ 在這個大小糊成一團），說明文字與「下一處 ②」照舊寫圓圈數字；另有一句 `.sr-only`。
- **收合與延後載入**：一台設備畫在超過 `PID_FOLD`（＝1）張圖紙上時每塊改成 `<details class="pid-sheet">`、只先展開第一張，**摘要組與完整資料區都照收**（圖控只收摘要組）。
  影像**一律延後**：展開中的那一張等捲進畫面才抓（`whenNear`：`IntersectionObserver`，`beforeprint` 也補載），收起來的等使用者展開才抓（`whenDetailsOpen`，要掛在 `<summary>` 以外的元素上）。
  PDF 連結列 `.pid-bar` 放在標頭**外面**（標頭收合時是 `<summary>`，連結放裡面一點就把這一塊展開／收起來）。
- **記憶體釋放**：`D.loadImage(path)`（`D.loadHmiImage` 是它的舊名）解密 → base64 → `Blob` → blob URL，同一張圖共用一個 URL；`card/pid/` 的影像 JSON 在 blob 建好之後就從 `D.cache` 拿掉。
  `pidRelease(aux, ix)`→`D.revokeImages('card/pid/', keep)`：換到另一台設備時把新卡用不到的圖紙 blob 收掉、新卡還要的留著（G11／G12 共用同一張典型圖時不必重抓）；新畫面沒有 P&ID 區塊（查無位號、首頁、閥卡）就全部收掉。
  `pidReset()` 收掉上一張卡的 `ResizeObserver` 與還沒觸發的 `whenNear`，並把世代加一——還在路上的影像抓回來也不再插入。離開查詢卡時 `destroy()`→`D.revokeHmiImages()` 連圖控一起全收。
  `D.imagesHeld(dir)` 回目前還握著 blob 的路徑（測試與除錯用）。`docs/db/index.html` 的 CSP 要有 `img-src blob:` 與 `style-src 'unsafe-inline'`（標記與舞台用行內 style 定位）。
- **標頭的短籤**（`pidCapBits`，最多三段 `.hmi-cap`；完整那句在 `title`／`alt`／燈箱說明列 `pidSrcText`，「圖上標示」「對應方式」的整句照抄 `build_card_aux` 寫好的、不在前端另外造句）：
  (a) `drawn`（灰字）＝圖上畫的字＋它跟本台的關係——「圖上畫的是 …」／「OCR 讀到的是 …」／「OCR 校正後是 …」＋（就是本台｜幾支位號合寫的標籤，本台是其中一支｜圖面不分機組｜以 G11 繪製的典型圖，本台取同一位置｜同一迴路的儀器｜只畫 LAC50 一台，同型各台共用這張圖，本台取同一位置；`odd` 時寫「寫法與位號不完全相同，請對照圖面」）。
  (b) `.pid-ref`（**粗體，不是紅字**——資料沒有錯）＝標記 ① 是引用時「※ 這一處是…，不是儀器符號」；以 `notes[0]` 為準，沒有 `notes` 才看 `note`（`pidRefCode`）。
  (c) `.pid-how`＝「PDF 文字層」或「OCR 讀圖（信心 0.91…，字元經校正）」；**這張圖上任何一處 OCR 標記的信心低於 `PID_LOW`（＝0.8）時加 `⚠` 並轉紅（`.warn`）、點名是哪幾處**（`pidLow` 讀 `confs`，沒有才退回 `conf_min`／`conf`）。
  整台設備每一張圖紙都只有引用時，最上面先印 `.pid-nosym`「這次比對（PDF 文字層＋OCR）沒有讀到這支位號的儀器符號——不代表圖上沒有畫，請開 PDF 確認…」。圖上的字一律當文字插入（不當 HTML）。
- **查無**：摘要只印一句短的「查無（現行 P&ID 圖面上找不到這個位號）」；完整資料區的 `pidNoneText` 把比對範圍講完（份數、頁數、封面頁、文字層頁數、OCR 頁數、定位數），數字全部取自 `index.pid.stats`，缺哪個鍵就不講那一段。
  **JK 位號那一行**（`pidIsJk`：`stats.ams_tags > ams_tags_base` 而且這一台的位號以 JK 開頭）寫「不在 P&ID 比對範圍（JK 開頭的位號是 HART 多工器模組…）」，**不可以寫「查無」**——那是「比過了、找不到」的意思。
- 手機（`.cq-body.narrow`）：細部視窗改 4:3，小地圖疊在細部視窗的角落、放在標記 ① 的對角（`.mini-r`／`.mini-t`）；無橫向捲動；燈箱雙指開合縮放。
  列印：影像捲到／展開才載，`beforeprint` 會補載，來不及時佔位框的文字會說明原因（三種措辭）。

### 測試

- `tools/tests/test_card.py`：`pid_typ`（位置、延後載入、幾何、燈箱）、`pid_wording`（短籤每一種情形直接打 prototype）、`pid_many`（多張圖紙收合、編號牌、「下一處」）、`pid_refs`（現行資料的引用 1～4 各一台）、
  `pid_lowconf`（紅字與點名）、`pid_jk`、`pid_none_leave`（查無文案、雙胞胎共用不重抓、離開時釋放）、`pid_mobile`，以及檔尾**照網站的 CSP 執行**的一段（其餘測試都以 `bypass_csp` 略過 CSP）。測試位號在檔頭的常數。
- **那一個釘子**：`PID_PIN = ('HT0-1-KND01-D0027-4_1030bef1__p2', 0.4666, 0.7083, 0.003)`＝G12HSD10QN101 的標記 ① 在 D0027 Rev.4 第 2 頁（R＝270 的那一張）轉正後的絕對位置與容差。
  其餘幾何檢查都只拿畫面與資料自己的 `marks[0]` 互比——`pid_index`／`pid_shots` 的轉正角或座標換算錯了，那些檢查照樣全綠；只有這一筆會紅。
- `tools/tests/test_pid_wording.py`（不開瀏覽器、不碰資料目錄，以合成的命中直接呼叫 `pid_rows`／`pid_shared_boxes`／`pid_check`／`pid_doc`／`pid_collect`；可單獨跑，`run_e2e` 也會收它）：
  rel 五種與拆寫的 form、`note` 代碼 0～4 的說法與 `extra.note`／`notes`、「與本台位號相同」的條件、`ocr-fix` 的 raw、`conf`／`conf_min`／`confs`、共用框的關卡不誤擋雙胞胎／`_01`／同型各台／合寫標籤、`searched.pid` 的頁數說法、`pid_collect` 不寫檔。
- 2026-10-10：7 個模組 383 項全過（`test_card` 180、`test_pid_wording` 83）。

### 已知限制（誠實標註）

- **OCR 的同類誤讀擋不掉**（C 讀成 Q、0 讀成 9、6 讀成 5）：正規化救不回來，分數門檻也擋不住。把關只有四道——文字層為準、分數 ≥ 0.75、形近字修復只接受唯一的 AMS 核心、已有符號位置的位號不發布 OCR 的清單格；
  所以 **OCR 讀出的位置一律 `inferred`、卡片寫出辨識信心**，`conf_min` < 0.8 時紅字點名（239 處 OCR 命中裡 41 處；卡片上 38 塊圖紙、37 台設備）。形近字修復另有一個已知的洞：
  圖上本來就不是 AMS 位號的標籤，被讀錯一個多值形近字時有極小機會「剛好」修成別的 AMS 核心。
- **沒讀到的球泡**：`C10LAC50BP005` 在給水泵組圖主流程上的球泡 OCR 沒讀到（只有第 5 頁的迴路詳圖小圖與第 7 頁的清單格）、`C10LAC50BT029` 的球泡也沒讀到（只有清單格）；`C10LAC60BP005`／`C10LAC70BP005` 因此也只有清單格。
  這四台就是 `devices_ref_only`。這一輪不換 OCR 配方重跑（會讓已查核的讀數全部作廢）。
- **清單頁本身是點陣圖**：TDM01-D1205 第 7、8 頁的儀器清單在 PDF 裡沒有文字層（0 個字、內嵌 92／85 張影像），原檔的解析度就是極限——發布的影像再大，5／6、8／9 也一樣要放大才分得出來。
- **同一支位號的幾個球泡之間的先後仍是由上到下**（傳送器／元件／DCS 顯示符號）：① 不一定是傳送器那一顆。
- **沒有文字層的圖紙沒有圖框分區**：一般 OCR 偵測抓不到圖框邊條上孤立的單一字元，被引用的圖紙裡，對照表的 `border` 湊不出任何一張的格線（104 張有分區的全部來自文字層）。117 張裡 13 張沒有分區（8 張沒有可用的文字層、5 張文字層裡沒有圖框字），那些位置只寫百分比。
- **顏色丟掉了**：四階灰階。117 張裡 44 張有 2 % 以上的彩色墨跡（GE 的示意圖整張把管線畫成藍色），非藍色的彩色墨跡超過 0.5 % 的 15 張（紅色版次雲形框、收文章）；雲形框的輪廓還在，只是不再是紅的。影像只供定位，內容以 PDF 為準。
- **97 台查無**（`not_located`）：ISA 迴路名 45（`1-TI-CW011-*` 39 台在掃描的循環水泵圖 HT0-0-UCA04-D0114 上寫成帶 X 佔位的 `X-TE-CW011-XAE`，沒有比對規則；`1-LI-CW101-*`、`1-TI-CW029-*` 各 3）、
  時間戳／殘缺名稱 26、G11／G12 `MAN30` 與 C10 `MAN60` 的 BP101～104 共 12、GE `96TT-GT-10～12`／`96TT-PH-1～3` 共 12、`C10LAC60BT029`／`C10LAC70BT029` 2。
  查無＝現行圖面的文字層與 OCR 結果都找不到，不代表圖上一定沒有。
- **舊版次從不採用**：文件庫進了新版，位置就跟著新版走；新版的圖還沒做 OCR（或對照表過期）時，那張圖上靠 OCR 的位號會變回查無，直到重跑 `pid_ocr.py` 並 commit 對照表——建置不會中止，只會大聲印出來。
- **只做 AMS 設備的卡**：AMS 沒有的閥（v4 的閥卡）不在這一版範圍。
- **圖紙影像大**：一張解碼後 16～37 MB；靠「捲到／展開才抓」與換卡釋放壓住，不要改成一開卡就抓。沒展開過的圖紙第一次列印可能只印到佔位框（與圖控、參數現值同一個取捨）。
- **查核提出、這一輪沒有裁決的**（都是潛在問題，現行資料 0 例，改規則時要記得）：(1) `typical` 在任何一張圖上都給，不限圖面自己聲明典型的圖；`SCOPE_LETTER` 只管沒寫機組的標籤，不管佔位符與只寫數字的。
  (2) ISA 的 `loop` 只比功能首字母，不看元件尾碼字母（現在 6 筆是 PIT↔PI、TE↔TI）。(3) 沒有文字層的頁，OCR 定向若差 180 度沒有任何關卡看得出來（尺寸檢查只擋 90 度，轉正角衝突要文字層 ≥ 400 字）。
  (4) OCR 清單偵測只數橫書、完整的位號；清單格若被 OCR 拆成系統段＋設備段兩個框，會當成符號（`note:0`）；直書的清單不處理。

## v7（docs/db 站：GE 原廠編號；`build_card_aux.py` 的 getag）

GE 供貨範圍（燃機、汽機、發電機與附屬撬）的設備在 GE 的 Device Summary、P&ID、Trip List、警報與 Mark VIe 邏輯裡用 GE 自己的編號（Legacy Tag／GE No.，例 `96PG-5B`、`CT-DA-1`、`90VA2-1`）；同一顆元件常有好幾種寫法（清單 `CT-DA-1`、邏輯 `CTDA1`、FF 傳送器 `96CTDA-1`）。查詢卡顯示它、搜尋打它也找得到。

- **來源**：GE 原廠設備編號對照表 `ge_tags.json`（hst-docsearch 的 `build_ge_tags.py` 產生，從 GE 各版清單、型錄總表、Mark VIe I/O 清單等文件逐列抽出，每筆帶出處＝文件庫相對路徑＋頁／列；不在工程文件庫、不進 repo）。路徑 `paths.GE_TAGS`（環境變數 `AMS_GE_TAGS`，預設 hst-docsearch `config.json` 的 `ge_tags_dir` 下的 `ge_tags.json`）；`build_card_aux --ge-tags <path>`／`--no-ge`。缺檔而沒給 `--no-ge` 時以非 0 結束（同其他外部來源）。`--recompare` 每次重算 `sec.getag`；`--no-ge` 時保留上次發布的 `sec.getag`、`docs` 的 `ge|…`、04 的 GE 列與 `stats.getag`（`sec` 與 `searched`／`source_stats` 的鍵序都放回重算時的位置，build 雜湊才不會因走哪條路而變）。`rebuild.py` 的 `ge_flags`：對照表在就明指 `--ge-tags`；不在（換了機器、hst-docsearch 沒裝）或給了 `--skip-ge` 時走 `--no-ge` 並印 `!!` 警告，不中止。`--no-drive-map` 時 `ge|…` 沿用上次的 url。對照表本身的頂層欄位只取 `built_at`、`n_rows`、`sources` 份數（它的 `dcdas_index`、`rows_file` 是本機路徑，不得進資料）。
- **對照規則**（`ge_match`）：
  - 位號是 GE 名稱寫法（`G11_96PG-5B`，含尾端 `_01` 這類 AMS 同位號的另一筆設備紀錄）→ 去機組前綴比 GE 編號（去分隔符、不分大小寫），只比燃機範圍的條目，lvl `doc`。對不到而以 `90` 開頭時去 `90` 再比（定位器 `90VAST-11` 在對照表只有閥本體 `VAST-11`），lvl `inferred`。
  - 位號是 KKS 寫法（`S10LBA12BP003`）→ 比 KKS 本體：兩邊都去機組前綴（`G\d\d`／`S\d\d`／通用 `XX`＝燃機、`YY`＝汽機）與子件尾碼（`-KH01` 定位器、`-MB01` 電磁閥、`-BG01` 極限開關、`-BL01` 液位探棒、`-MA01` 馬達），範圍要相同（燃機／汽機各有同名、同本體的設備：`G11LBA10BT001`（HRSG）不配汽機的 `TE-227-1`＝`LBA10BT001`）。本體相同時無尾碼的排前，lvl `doc`。
  - 條目的範圍取對照表 `system`（`GT*`→燃機、`ST*`→汽機），沒有再看 KKS 前綴。
- **`sec.getag`**＝`{entries:[{h:"<GE 編號> · <說明>", lvl, src:"文件 · <檔名> <頁／列>"|"推論 · …", rule, d:"ge|<sha1(相對路徑)前 12 碼>|", rows}]}`。第一筆（或幾筆，一個位號對到多個條目時）是本台；其後最多 4 筆 lvl `inferred` 的「在 GE 文件中共用同一個**現行** KKS 本體的另一個編號」（常是同一套設備——閥本體、定位器、電磁閥——或同一盒的另一顆，也可能是文件誤植，規則文字照這樣講、不斷定）：舊版文件的 KKS（old_kks）不拿來找（96PGT-3B／3C 是舊版把 KKS 寫重）；本身就是另一台 AMS 設備主條目的編號不列（那台有自己的卡；`ge_prepass` 先對全部位號比一次）；一個本體被 4 個以上編號共用——盤箱、多點溫度元件——時也不列。`rows`：`GE 編號`、`GE 說明 (Service)`（一個編號對多個 KKS 時改成每個 KKS 一列 `GE 說明（<KKS>）`；只出自 Mark VIe I/O 清單 FF H1 裝置報告的條目改叫 `GE 裝置類型（FF H1 Device Name）`，那一欄是型號，也不放進標題）、`KKS（GE 文件）`（前綴換成本台機組：清單印 G11 或 XX／YY）、`子件`、`範圍`、`MLI`、`Mark VIe 訊號`（只列本台機組的控制器；對照表只列同設計的 G11 時換成本台控制器、signal-atlas 索引確認有這個變數才列並註明「由 G11 推得」，確認不了就不列——不可把 G11 的訊號掛在 G12 的卡上）、`相關裝置`（FF 傳送器↔量測元件）、`其他文件寫的 KKS（照原文）`、`文件不一致`、`其他出處`。`d` 指的文件以「資料夾／檔名」登記進 `docs`，`add_drive_urls` 照常補 url。
- **index**：`kind_label.getag`、`searched.getag`（一筆＝對照表本身：doc_id `ge-tags`、rev＝建表時間）、`source_stats.getag`、`stats.sections.getag`、`stats.getag:{aliases, ge_keys（實際加進 04 的鍵數）, index_rows, skipped_keys}`。
- **摘要**：`dev` 組「現行 AMS 位號 (KKS)」之後一格 `K('GE 原廠編號', 'getag', 'GE 編號', big, hide_empty, alt=instlist 'GE 編號')`；完整資料的 `sections_aux` 在「設計規格（儀器清單）」之後加 `getag` 段（說明文字不寫死數字）。`rebuild.py` 的 `spec_lacks_pid` 也檢查 02 有沒有 `getag` 段與 dev 組那一格、兩者是否與 extract_db 現在的規格相同，不同就自動套 `patch_site_spec`（P&ID 與 GE 各自判斷：`--no-pid` 不會讓 GE 的檢查一起跳過）。
- **搜尋**（04 位號索引）：每個「對到 AMS 設備的主條目 GE 編號 × 設備」加一列，來源類型 `8 GE 原廠編號（GE 文件）`，查詢鍵＝`IX.norm(GE 編號)`、位號字串＝原寫法、其餘欄取該台「1 設備別名」那一列、對應設備數＝這個編號對到的台數（>1 多半是 G11、G12 兩台或 AMS 同位號的另一筆設備紀錄，不是歧義；04 說明有寫）。鍵與 04 既有鍵相同、或去分隔符後相同（core.js `compactMap` 先到先得，會搶走既有鍵）的跳過，`build_card_aux` 印出被跳過的鍵、`stats.getag.skipped_keys` 記個數。每次先刪掉上次加的列再加（冪等）；穩定排序只用 (鍵, 是否 GE 列, GE 列的目前位號)，既有列保持 `sheets_index` 給的順序，同一 GE 鍵內 G11 在 G12 前（搜尋預設開 G11 那台）；列數改寫在 04 的說明、00 目錄的 04 列、manifest。這些新內容在分塊與 index 自檢通過、card/ 寫完之後才寫檔（`ge_index_plan` 只算不寫）。
  - 前端：正式寫法走 exact、不打連字號走 compact、兩台出切換按鈕、頂列搜尋同樣，都是既有程式。`IX.load` 記下 GE 鍵（`IX.ge`：第一列來源類型是 `8 ` 的鍵）；`IX.suggest(q, limit, skip)` 多兩件事：(1) 輸入本身不帶分隔符、含字母、去分隔符後 ≥3 字元時，GE 鍵去分隔符後以它開頭也算開頭相符（打 `96PG5` 列出 `96PG-5B`）——只對 GE 鍵，其他帶分隔符的鍵（HostTag「50 BL001」、時間戳、尾端底線的位號）與帶分隔符的輸入照舊，主站 05 沒有 GE 鍵所以不變；(2) `skip(k)` 在掃描時就跳過的鍵。`AMS.tagSuggestSource` 用 `skip` 跳過 GE 鍵（不是先取 N 筆再濾——GE 鍵沒有機組前綴、排在 AMS 位號前面，會把名額佔光）。
  - GE 編號是 04 的 exact 鍵，所以排在氣動閥命中之前：`90VA2-1` 這種既是閥清單鍵又對到 AMS 的寫法直接開 AMS 卡（卡上本來就有「氣動閥」組）。沒有 AMS 設備的 GE 編號（`CT-DA-1`、`88VGC-1`…）不進 04；v8 起開「GE 編號卡」（見下節），閥清單也有的照舊開閥卡。其他讀 04 的產生器（`docmap_instlist`、`docmap_eomr`、`pneuvalve_site`）跳過來源類型 8 的列。
  - 首頁說明「可輸入 … GE 原廠編號」只在 02 規格有 `getag` 段時出現（`card.js` 兩站共用，主站沒有）。
- **測試**：`tools/tests/test_getag.py`（GE 編號從 04 的來源類型 8 挑，不寫死）。
- **已知限制**：只涵蓋 AMS 資料庫裡的設備（1 號機 G11／G12／S10）；HRSG、BOP 等非 GE 供貨的設備沒有 GE 編號。對照表重建後要重跑 `rebuild.py` 才會更新。

## v8（docs/db 站：GE 編號卡；`build_card_aux.py` 的 `ge_card_data`、core.js `AMS.getag`）

v7 只把「對到 AMS 設備」的 GE 編號放進 04；熱電偶 `CT-DA-1`、限位開關、閥本體這些 AMS 沒有的元件照舊查無。v8 把整份對照表（約 4 千個編號）也放上站：打 GE 編號、Mark VIe 訊號名或 KKS，就知道它在 GE 文件裡是哪個元件。

- **資料**：`card/getag.json`（照常加密成 `.bin`，進 `manifest.build`；`card/index.json` 的 `getag:{version, files:["card/getag.json"], built_at, n, docs, docs_with_url, shadowed, bytes}` 指向它，`verify_encrypted` 把 `getag.files` 算進引用清單）。內容 `{version:1, built_at, n, units:{G:["G11","G12"], S:["S10"]}, rule, rule_unit, entries:[…], docs:{"ge|…|": {title, folder, why, url?, url_note?}}}`；每個條目 `{t:正式寫法, f?:[去分隔符後與 t 不同的寫法], sc:"G"|"S"|"", sys:"燃機"…（範圍不明為空）, svc:英文說明（FF H1 型號那種不放）, c:{lvl, src, d, rows}, u?:[[機組, rows]], gone?:1, ams?:[[alias, AMS 位號, 對照規則]], tw?:[[alias, AMS 位號, 同 KKS 的那個 GE 編號]], ln?:[[名稱, 關係, 對到的條目或 ""]], sib?:[同一 KKS 本體的其他編號], sig?:[Mark VIe 訊號名（不帶控制器）], lg?:{機組:[控制器.訊號]}, kb?:[現行 KKS 本體], okb?:[其他文件寫的 KKS 本體]}`。
  - 每個條目照 v7 的 `ge_entry` 逐機組產生（本站機組 `GE_SITE_UNITS`：燃機 G11／G12、汽機 S10；範圍不明的 13 筆不分機組、「範圍」寫「不明」），所以 KKS 前綴與 Mark VIe 訊號的規則與 `sec.getag` 完全相同（不可把 G11 的訊號掛在 G12）；各機組都相同的列併成 `c`，不同的（KKS、多 KKS 時的說明、訊號）放 `u`。規則文字每筆一樣，只寫在檔頭 `rule`／`rule_unit`。`lg` 由 `ge_logic` 算（同規則），給 signal-atlas 連結。「相關裝置」不放列、只做連結（`ln`）。
  - `gone`：對照表 note 寫「最新版 GE 清單已無此編號」的 98 筆；`c.rows` 第二列加「文件狀態」＝那一分句＋指向現行編號／閥本體／舊 KKS 的分句（`ge_gone`），卡片標頭、狀態列、建議都加註。note 的其餘內容不發布。
  - `ams`＝這個條目是哪幾台 AMS 設備的主條目（`ge_apply` 順手記下 `ge['ams_of']`）；`tw`＝同一範圍、共用同一個現行 KKS 本體（≤ `GE_SHARED_MAX`）的另一個編號是 AMS 設備（改過編號的同一顆傳送器常見，例 `96FGAFS-1A` ↔ `96GN-4A`），一律標「推論」。`sib` 只看現行 KKS、一個本體被 4 個以上編號共用（盤箱、多點溫度元件）就不列。`ln` 的名稱先比同範圍的寫法、再去掉尾端通道字母（`DTGSC1A` → `DT-GSC-1`），對不到的只顯示文字、不做連結；最多 12 個。
  - 出處文件自成一份 `docs`（不併進 index 的 docs：那裡只放卡片分塊用到的），自己跑 `add_drive_urls`；`--no-drive-map` 時沿用上一份 `card/getag.json` 的 url，第一次（還沒有上一份）退而用卡片 docs 的 `ge|…`。
  - 沒有 AMS 設備的 GE 編號，去分隔符後與 04 既有鍵相同的（`74-1`、`74-2`、`74-3`、`81-4` ＝設備鍵 741…）建置時印 `!!` 並記 `index.getag.shadowed`；前端另有處理（見下）。
  - 寫檔時機同分塊：序列化與 `ABS_PATH_RE` 自檢通過、index 也通過才寫。`--no-ge` 的 `--recompare` 原檔、`index.getag` 都留著，`stats.getag` 寫回與重算時同一個位置（鍵序相同，build 雜湊不變）；完整建置沒有對照表時刪掉，不留沒人引用的密文。2026-10-22：3,956 個編號、27 份出處文件（都有雲端連結）、明文約 2.5 MB、密文約 210 KB。
- **前端載入**（`AMS.getag`）：`load()` 只在 manifest 有 `aux.card` 且 index 有 `getag` 時抓（主站 `state:'none'`）；查詢卡開啟、搜尋框聚焦時就開始抓。`state`：`idle`／`loading`／`ready`／`none`／`error`（下載失敗；15 秒內不重抓，之後任何呼叫都會再試）。`pending()`＝還沒開始或還在下載、而且沒有等過頭。
  - `lookup()` 走到非 exact／compact（或純數字 compact，見下）的路而 `pending()` 時，回 `gePending`（狀態列「查詢中：GE 原廠編號對照表下載中…」）；`run()` 等 `GE.wait(4000)` 再查一次。等不到就記 `slow`，之後的查詢不再等，照沒有 GE 的方式先顯示；畫面是查無的，對照表載到後自動重查一次，狀態列也會講「還沒載到」。這樣同一個網址冷開（深連結、重新整理、書籤）與熱開是同一個結果。
  - `go()` 與頂列 Enter（`app.js`）從不等待：對照表還沒 `ready()`（下載中、慢、失敗）時一律不把模糊對應改寫成 AMS 鍵（網址留原字串，交給卡片判斷）。對照表慢或失敗而這次走了 AMS 的模糊對應（`geLate`），狀態列講明「這是 AMS 的模糊對應」，載到後背景重查；失敗的等 15 秒冷卻過了自動再抓。背景重查不會蓋掉使用者正在框裡打的字。冷開 04 的 GE 鍵時，「另一個範圍也有同編號」那一句在對照表載到後補進狀態列。
  - 下拉建議不等對照表：先列 AMS 與閥清單，回傳的陣列掛 `later`（`GE.load()`），載完後 `Autocomplete` 在框內字沒變、清單沒被收起時重查一次。`Autocomplete` 另有 `gen`：收起（Enter、點選、Esc、離開）之後才回來的建議一律丟掉，不會在新的卡片上把清單打開。
- **比對**（`AMS.getag.hit`；一律整串相等，去分隔符、不分大小寫，**不做包含**——`CTDA1` 不可中 `CTDA10`；`IX.norm` 先把全形英數與符號折成半形，`ＣＴＤＡ－１` 也查得到）：任一寫法 `key` → 去機組前綴（只認全廠真的機組 G11／G12／G21／G22／G31／G32／S10／S20／S30，也認廠內寫法 GT12／ST10；只留該範圍的條目）`unit` → 去字頭 `90`（推論：多半是定位器、對照表只有閥本體）`90` → 現行 KKS 本體（要有前綴 `G\d\d`／`S\d\d`／`XX`／`YY` 才比，範圍同 v7；範圍不明的條目也比；多了子件尾碼記 `kks-sub`）→ 其他文件寫的 KKS 本體 `oldkks` → Mark VIe 訊號名 `signal`（可帶控制器 `G11.`／`G11S.`／`S1.`／`SAMP1.`，只留該機組；控制器之外只能有一個字；不帶控制器又不含底線時，有任何 AMS 或 GE 鍵以它開頭就不算——打一半的 `96QV-` 不搶）。
- **查詢順序**（`lookup()`）：04 exact／compact（AMS 設備；04 的 GE 鍵開到 AMS 設備而另一個範圍也有同編號、那一顆沒有 AMS 設備時，狀態列加註，例汽機發電機 `PT-2950` 是 AMS 設備、燃機發電機的不是；網址帶 `?sc=` 指到那個沒有 AMS 設備的範圍時改開它的 GE 編號卡）→ 氣動閥清單的命中（多顆閥共用的廠商代號 `weak` 除外；「包含／訊號名分段」命中的閥位號不是 GE 條目自己的寫法時——電磁閥 `20VA41-21` 內含閥本體 `VA41-21`——讓給 GE；閥卡下面接 GE 對照 `.ge-below`；輸入開頭的機組 `G12.`／`GT12_` 交給閥卡當機組，不去猜 GE 的 20／90 字頭）→ GE 編號卡（閥清單讓給 AMS 模糊對應時，GE 命中也優先：它帶著機組，`G12.a_90va21` 開 G12 那台）→ AMS 的模糊對應。例外：去分隔符才對到**純數字**的鍵（設備鍵 DeviceKey）而輸入本身不是純數字（`numCompact`：`74-1` → `741`），GE 編號整串命中時開 GE 編號卡、狀態列交代那個數字是另一台的設備鍵。GE 命中、或只是 AMS 的唯一建議而 GE 有「不在 04 的」開頭相符編號時，不採用 AMS 的模糊對應（`geBlocksFuzzy`；GE 的候選本身就是 04 的鍵時照舊直接開，`PDT-273` → `PDT-273A`）。命中的條目恰好對到一台 AMS 設備（輸入帶本站機組時只看該機組），而且沒有「另一個範圍、沒有 AMS 設備」的同編號（`a_96pdt292_dp` 燃機發電機與汽機發電機都有）時，直接開那台、狀態列說明經由哪個 GE 編號。訊號名後面貼著 `.PV`／`.VALUE` 照樣認得。網址 `?sc=G|S`（卡內 chips 帶的）只留該範圍的條目。
- **畫面**（`renderGeOnly`）：標頭＝GE 編號、範圍、英文說明、「最新版 GE 清單已無此編號」（`gone`）、AMS 設備 chips、同一 KKS 的 AMS 設備 chips（推論）、「氣動閥清單也有」連到閥卡；「GE 原廠編號對照（GE 文件）」一組：每個條目一塊（燃機、汽機同編號時兩塊），共同的列＋逐機組的列（輸入帶本站機組時只列那一台；本站以外的機組 G21… 列 1 號機並在狀態列講明），逐格來源點（每一格各自一份來源明細，都有雲端連結；列好幾份文件的格——其他出處、文件狀態、其他文件寫的 KKS、文件不一致——值不連到主出處，明細另列「本格提到的文件」各自的連結）；長的值（其他出處、文件不一致、文件狀態、其他文件寫的 KKS、Mark VIe 訊號）佔兩格。連結列：Mark VIe 訊號（signal-atlas `#/v/<控制器>.<訊號>`）、相關裝置、同一 KKS 的其他編號（推論）；連結帶著本站機組前綴，沒有機組時帶 `?sc=`。狀態列的訊號名照使用者打的寫法。查無頁多一塊「GE 原廠編號中相近的編號」（`.nf-ge`），打錯字的相近鍵（`AMS.fuzzy`）也比 GE 編號（兩邊都 ≥5 字，`CDTA1` → `CT-DA-1`）；首頁說明在 02 規格有 `getag` 段時多一句。
- **建議**：`AMS.searchSuggestSource` 合併 AMS／閥清單／GE（`AMS.getag.suggest`：任一寫法開頭 → 包含（≥3 字元）→ 英文說明每段都出現；帶機組時去前綴、key 補回機組；燃機汽機同編號只列一次、範圍併寫；已在 04 的 GE 鍵不重列）。名額：AMS 有 8 筆以上時留 8 筆，其餘 GE 至少拿一半、清單最多 6 筆、用不完的互相補。都沒有而 GE 整串命中（訊號名、KKS）時列它對到的編號（同樣合併、最多 12）。`AMS.tagSuggestSource`（備品庫存）不收 GE。
- **測試**：`tools/tests/test_getag.py` 後半（`ge_card`）：`CTDA1`／`CTDA-1`／小寫／全形、`G12.CTDA1` 與 `GT12_CTDA1` 只列 G12、`G11.a_ctda1`（狀態列照原寫法）、KKS `G11MBM01BT025`、`CTDA10` 與 `XYZ CTDA1` 不中、`CDTA1` 的打錯字建議、燃機汽機同編號兩塊、閥清單也有的編號與它的訊號名（閥卡＋GE 對照）、最新版已無此編號、`74-1`（純數字設備鍵）、查無頁與下拉建議（≤12）、04 GE 鍵的唯一建議照舊直接開、頂列 Enter（清單不會再打開）、每一格的來源明細都有雲端連結、深連結冷開（查無類與 AMS 會模糊對應到別台的那一類，編號從資料挑）、對照表下載失敗不卡住、手機不橫向捲動。
- **已知限制**：`--no-drive-map` 而上一份 `card/getag.json` 不在時，只補得到卡片 docs 與其他類別文件裡有的連結（建置印 `!!` 與份數），下次有 drive_map 的建置會補齊；GE 文件只有英文說明（沒有中文名）；對照表本身的問題照樣顯示（同一顆的拼法變體各成一筆、少數解析殘留的寫法、非標準 KKS 字串不進 `kb`），要在 hst-docsearch 的 `build_ge_tags.py` 修；`96DT-7` 這類 FF 傳送器若對照表沒有它的條目，相關裝置只顯示文字；對照表重建後一樣重跑 `rebuild.py`。

## v9（docs/db 站：GE 元件詳細資料與相關閥；`build_card_aux.py` 的 `ge_spec_blocks`／`ge_rel_rows`／`ge_prot_rows`）

v8 的 GE 編號卡只有對照（編號、說明、KKS、訊號）；查 `96FG-1A`（P1 腔壓力傳送器）看不到它是什麼型號、量程多少、跟哪些閥有關（使用者 2026-10-24）。v9 把 hst-docsearch 對照表新增的四類欄位放上卡：規格、相關閥／儀器、所在腔室、保護功能。編號 ↔ KKS 的對照與 v8 完全相同。

- **來源**：`ge_tags.json` 的條目多了這些欄位（hst-docsearch `ge_details.py` 從 `ge_detail_rows.jsonl`、`ge_relation_groups.jsonl` 併入；兩檔不進 repo，同 v7 規則）：
  - `spec`：[{doc, loc, rev, evidence, label, old, via, f:[[欄位鍵, 值]]}]，一份 GE 清單一塊。後面的塊不重列前面相同的值；同家族舊版只補新版沒有的欄。
  - `valves`／`instruments`：KKS 子件尾碼、閥清單 Solenoid Tag 欄、說明寫明。
  - `pos`／`pos_in`：P&ID 腔室／管段與邊界閥。
  - `prot`／`prot_in`：保護功能與它動作的閥。
  - 檔頭另有 `spec_fields`（欄位鍵 → 中文名），建置照它印。
- **`card/getag.json`**：每個條目再加：
  - `sp?`：[{h:清單短名, lvl:'doc', src, d, ev:evidence, rows}]，規則文字在檔頭 `rule_spec`。
  - `vl?`／`vi?`：[[GE 編號, 關係種類, 說明, lvl, 出處文字, 文件鍵]]，各 ≤12。
  - `ps?`／`pv?`／`pr?`／`pi?`：[[功能名, 本顆的角色, 說明, [[GE 編號, 角色]…], 出處文字, 文件鍵]]。功能組的規則文字在檔頭 `rule_prot`。
  - 所有出處文件登記進 `docs`，照 v8 補雲端連結。
  - 2026-10-24：1,984 個編號有規格；功能組 46 個；出處文件 34 份，全部有雲端連結；明文約 4.4 MB。
- **AMS 設備卡**（`sec.getag`）：主條目之後接「<GE 編號> 規格 · <清單>」各塊，以及相關閥、相關儀器、所在腔室、邊界的腔室、參與的保護功能、會動作這顆閥的保護功能各一塊（rows 是文字）。摘要格仍只取 `entries[0]`。
- **畫面**（`renderGeOnly`）：
  - 規格塊排在共同列之後、逐機組的 KKS 之前，標頭「規格　<清單短名>」（`.ge-spec`），逐格來源點照 v8。
  - 連結區依序：所在腔室／管段（`ps`）、相關閥（`vl`）、相關儀器（`vi`）、這顆閥邊界的腔室（`pv`）、參與的保護功能（`pr`）、會動作這顆閥的保護功能（`pi`），之後才是 v8 的訊號與相關裝置。
  - 功能組一項一塊（`.ge-prot-i`）：功能名＋本顆的角色＋對方編號 chips（帶角色）＋說明＋出處雲端連結。chips 超過 10 個先藏、按鈕全部列出；一段超過 4 項整段收合（`details.ge-prot`）。
  - chips 連到該編號的卡（氣動閥清單有的開閥卡，其餘開 GE 編號卡）。
- **測試**：`test_getag.py` 的 `ge_spec`：
  - `96FG-1A` 的規格有 EMERSON／3051CG5A22A1AK7M5Q4Z1／-14.2 to 800 psi-g，13 格出處都有雲端連結。
  - 所在腔室 P1 腔列出 VS4-4、VGS-1、VA13-25 並帶角色；參與的保護功能中有一項同時動作 VS4-4 與 VA13-25（通風 SIF）。
  - 點 VA13-25 開閥卡，下面 GE 對照的「邊界的腔室」列出 96FG-1A，「相關儀器」有極限開關 33VG-8。
  - AMS 設備卡完整資料區有規格塊。
  - 手機寬度不橫向捲動。
- **已知限制**：
  - 規格與關係照 GE 原文，原文印錯的照印。
  - 台電整理檔（Bently xlsx）的值不是 GE 原文，塊名寫明。
  - 熄火保護「88VGC-2～5 屬延時後跳」是推論（說明裡寫了）。
  - 汽機閥本體沒有 GE 編號，汽機保護組只連到跳脫電磁閥與 ASV、ACV。
  - 只出現在接線圖、I/O、負載、設備、配管清單的編號沒有規格。
  - 對照表重建後一樣要重跑 `rebuild.py`。

## v10（docs/db 站：GE 編號卡的 P&ID 圖面位置與圖控 HMI 畫面位置；`tools/db/pid_ge.py`、`tools/db/hmi_ge.py`、`build_card_aux.py` 的 `ge_loc_build`／`ge_pid_rows`／`ge_hmi_rows`）

使用者 2026-10-24：「96FG-1A 可以跟其他的一樣顯示出它在 P&ID 的哪個地方嗎？圖控 HMI 有的也顯示圖控的位置；這類 GE 編號的都幫我完善」。v6 的 P&ID 圖面位置與圖控畫面位置只比對 AMS 現行位號，GE 範圍的元件（燃機、汽機、發電機的儀器與閥）一支都沒有。v10 用同一套定位引擎另做一份「GE 編號 → 位置」，GE 編號卡直接用設備卡現成的圖紙細部視窗與圖控縮圖顯示。**AMS 設備卡的 sec.pid／sec.hmi 與 v9 逐位元組相同**（2026-10-25 解密逐台比對 1,928 台；index.pid／index.hmi 原有的圖紙與畫面記錄也相同，只多了 GE 用到的與幾個 `ge_*` 統計鍵）。

- **P&ID：`pid_ge.py` → `cardwork/pid_ge.json`**（不進 repo；約 15 秒）。與 `pid_index` 共用 corpus（現行最高版次）、文字層快取、OCR 對照表、轉正座標與圖框分區（import 重用，不改 `pid_lib`）。兩條比對：
  - **KKS**：條目的 KKS 依本站機組展開（XX／YY／G11 印法 → G11、G12；S10），走 `build_index → scan → select`。GE 示意圖印的是不帶機組的本體（`MBP70BP001`）＝ `neutral`；BOP 圖印全名＝ `exact`，只帶那一部機。子件尾碼（`-BG01`、上下兩行拆寫的 `QN310-MA01`）另建子件位號。二、三號機組的 KKS（G21…）不換成本站。
  - **GE 編號標籤**：括號裡的 `(96FG-1A)`，去掉標點後 `ge_cmp` 整詞相等（不做包含）；斜線合寫（`39VE-7R/T`）展開；純字母的編號（`EBP`）只收括號內的。**只在 GE 圖家族上比**：GFD01／EGJ01 → 燃機範圍，TFD01／EGK01 → 汽機範圍（`pid_lib.SCOPE_LETTER`），範圍不符不發布。附註句子（同一行 4 字以上）與清單欄（同欄 4 格以上）標 `note=1`（引用）。
  - 同一條目、同一張圖，GE 標籤與它的 KKS「互為最近」而且相距 < 0.03 頁面對角線 → 併成一處（`via='ge+kks'`，框取聯集）。同一 KKS 本體被閥本體／定位器／電磁閥／極限開關共用時，KKS 的位置標給每一個並帶 `shared`（推論）；超過 3 個共用一個本體而且沒有子件尾碼（盤箱、接線盒）整組不歸戶。
  - **衝突過濾**（`drop_conflicts`，2026-10-25 四組反方驗證看圖找到的錯誤模式）：(1) 廠商檔名的舊副本（`GE_KKS_SKIP_FAMILIES`：noKKS_IGV VGV，與 GFD01-D0018-1 p3 逐字相同）不收；(2) 圖面把同一個 GE 標籤印了兩次、第二次印在別的條目的 KKS 旁（TE-201R、HV156）→ 那一處不收；(3) 只靠 KKS 的一處，符號旁印的是別的條目的 GE 標籤（該標籤也沒有點名這個 KKS 的任何擁有者），而且這個條目在同一張圖已有自己的標籤、或兩者 KKS 本體不相交 → 不收：對照表的 GE↔KKS 與圖面對調時以**圖上的標籤**為準（EGJ01-D0004 的 GC-1～4、EGK01-D0027 的 HV-2996J～L、TFD01-D0004 的 TE-243E-1/3、GFD01-D0001 的 96CT-IF-1R），電磁閥／定位器／極限開關在同一張圖已有自己的符號時也不再標到閥本體上（20VS4-4、20VG8、90VGC-1…）。計數與樣本在 `stats.conflicts`。
  - 只有 GE 這一道多收汽機發電機示意圖 EGK01-D0033（`GE_EXTRA_FAMILIES`；檔名的 Load Equipment 讓 `kind_of` 判成電氣圖，汽機儀器清單卻列它為 P&ID；97 個 GE 編號只畫在這份圖）。`pid_lib.EXTRA_FAMILIES` 沒改，AMS 設備的 P&ID 位置不受影響。
  - 命中格式與 `pid.json` 的 by_tag 相同，另帶 `via`（ge／kks／ge+kks）、`units`、`shared?`；`sheets` 與 `pid.json` 同一 slug 的記錄必須相同（`build_card_aux` 與 `pid_shots` 都檢查），影像共用。
- **圖控：`hmi_ge.py` → `cardwork/hmi_ge.json`**（不進 repo；約 20 秒）。只掃根目錄 248 個操作員畫面，每組選單變數各展開一次（重用 `hmi_index` 的 .cim 解析與座標）。命中三種：
  - `io`：物件引用條目的 Mark VIe I/O 訊號（控制器限定，例 `G11S.a_96fg1a`；裸名配物件的 `ctrlr`）——位置。
  - `label`：畫面上顯示的文字（caption／defaultText／tooltip／靜態文字…）`ge_cmp` 後等於 GE 編號——位置。另外三條：去分隔符後至少 4 字（`CV2` 不配潤滑油逆止閥 CV-2）；數字分段要相同（`TTXD1_6` 去分隔符是 TTXD16，但它是 6 號熱電偶，不是 TT-XD-16）；caption 被 defaultText 蓋掉的（permit 列顯示 SSOV、caption 是 VS4-4）與 DVP Status 按鈕的 CAPTION 不算。數值格／警報燈／棒圖／類比指示的 caption 是設計時標題、不一定畫在畫面上：物件引用的訊號屬於別的 GE 編號時不算（SIL_VibProx 上 39VS-91 的警報燈 caption＝39V-1A），其餘照收並標 `via='caption'`。
  - `related`：只引用「說明提到這個編號」的別的訊號——**不是位置**，條目沒有任何位置時才在卡上另外講。
  - **機組＝物件引用的控制器所屬機組**（G11／G11S → G11、G12／G12S → G12、S1／S1S／SAMP1 → S10），不是選單機組。對照表只列 G11 訊號而 G12 畫面引用同名訊號時，signal-atlas 確認 G12 有同名變數才算（`via='sibling'`，卡上寫「推論」，與 GE 卡「Mark VIe 訊號」同一個規則）。
  - `via='host'`：條目的 KKS 帶子件尾碼（-BGnn 極限開關、-MBnn 電磁閥、-EBnn 加熱器…）而訊號是從主設備 KKS 別名繼承來的（對照表 `logic_how`＝KKS 別名）——畫面上那個物件是主設備，卡上寫「畫在主設備上」（23QB-1＝88QB1 泵、ZS-203B＝ASV 開位）。
  - `via='derived'`（`DERIVED` 規則，目前一條）：排氣熱電偶 TT-XD-n 在畫面上顯示的是 I/O 訊號經 AI 與排氣溫度補償巨集逐通道轉手後的 `TTXD1_n`／`TTXD_n`，一對一對回 TT-XD-n（signal-atlas trace 確認）。
  - 物件外框取函式庫連結記錄後的外框（`hmi_index` 的矩形常是後面的標題或線段，實測 GT／ST 畫面 4,541 個物件有 1,066 個不同）。
- **`card/getag-loc.json`**（新檔，約 6 MB 明文，開 GE 編號卡才下載；`getag.json` 在查詢時就要載，所以不併進去）：`{version, built_at, by_i: {條目序號: {pd?, hm?, hmx?, hr?}}}`。`getag.json` 檔頭多 `loc`（這個檔的路徑）、`rule_loc`、`hmi_max`；條目有位置的帶 `lc: 1`。`index.getag.files` 列兩個檔，另有 `loc_entries`、`loc_bytes`。
  - `pd`：與 `sec.pid.rows` 同格式（每張圖紙一組 5 列）。第一列 extra 另帶 `via`、`shared?`、`gu?`（這一組只有某幾部機才有：BOP 圖分別印 G11／G12 的 KKS）。`lvl`：文字層而且不是共用 KKS＝doc，OCR 或共用 KKS＝inferred。
  - `hm`：與 `sec.hmi.rows` 同格式（每個（畫面, 機組）一組 4 列）。第一列 extra：`unit`＝開這張畫面的選單列（挑 G11／G12 的執行時截圖用）、`gu`＝元件所屬機組、`ctrl`＝引用的控制器。排序：機組 → 製程畫面在 SIL 畫面之前 → 畫面名；每部機最多 `hmi_max`（6）張，其餘的畫面名放 `hmx`＝[[機組, [畫面名…]]]（SIL 各頁共用「最終元件」面板：VS4-4 一部機就有 25 張）。
  - `hms`：SIL 各頁共用「最終元件」面板時（標記座標逐字相同），只留一張代表（有 SIL_Overview 就用它），其餘畫面名放 [[機組, 代表畫面名, [其他畫面名…]]]，不佔 `hmi_max` 名額；同一部機同一張畫面從兩個選單列都進得去（S10 在 HRSG11／HRSG12）且標記相同，只留一列。
  - `hr`：沒有任何位置時，相關訊號出現的畫面 [[機組, 畫面名, 控制器.訊號]]（≤12）。
  - `pd` 第一列另有 `on_body`：只靠 KKS 的一處、條目 KKS 帶子件尾碼而圖上的字沒有＝框的是主設備（附屬件在這張圖上沒有單獨畫），標頭與「圖上標示」照實寫。`hm` 第一列另有 `host`（整組都是 `via='host'`）。
  - 用到的 P&ID PDF（`pid|…`）登記進 `getag.json` 的 `docs`，雲端連結照 `pid_own_urls_only`（只連那一份檔）。
- **`index.pid`／`index.hmi`**：`sheets`／`screens` 加上 GE 用到的（`rows` 0、`ge`＝幾個 GE 條目／幾列）；`index.pid.stats` 的 AMS 數字（devices、images、docs、no_url）照舊只算 AMS 設備，GE 另記 `ge_entries`、`ge_sheets`、`ge_only_sheets`、`ge_docs`、`ge_no_url`；`index.hmi.stats` 另記 `screens_ams`、`ge_screens`（`screens`、`files` 是發布的總數）。影像仍是一張圖紙／一個（畫面, 選單機組）一檔，AMS 與 GE 共用。
- **畫面**（`renderGeOnly` → `geLocBox`）：每個條目在共同列之後、規格塊之前接「P&ID 圖面位置」「圖控 HMI 畫面位置」兩塊，直接呼叫 `fillPid`／`fillHmi`（摘要版面：圖紙標頭、開啟 PDF、細部視窗＋小地圖＋燈箱；畫面標頭＋縮圖紅圈；超過 3 張只先展開第一張）。P&ID 標頭另有「依 KKS 對應」「※ 共用 KKS（也是 …）」與機組短籤；圖控標頭寫「機組 G11（控制器 G11S）」而不是「以選單機組開啟」。帶機組（`G12_96FG-1A`）只列那一台的。查無時一句話講清楚（沒有訊號、還是畫面上沒有；P&ID 可能是線條字或只畫在接線圖上）。換到另一張卡時照 `pidRelease` 收掉用不到的圖紙影像。
- **測試**：`test_getag.py` 的 `ge_loc`：反方驗證的五個例子（見上）；VS4-4 的 SIL 同面板只列一張並有說明；位置檔 `lc` 與檔內一致、≥ 2000 個條目有 P&ID、≥ 500 個有圖控；`96FG-1A` 的 ① 在 GFD01-D0005-3 第 7 頁左上 A-3、`ge+kks`；圖控有 SIL EFFF／FtI／Vent 的 G11／G12 各組、機組＝控制器的機組；卡上位置區在規格之前、圖紙標頭有雲端連結與影像紅框；`G12_96FG-1A` 只列 G12；沒有位置的編號兩塊都寫查無並收掉上一張的圖紙影像；手機寬度不橫向捲動。
- **數字（2026-10-25，反方驗證後的規則）**：3,943 個有範圍的條目中 2,550 個有 P&ID 位置（110 張圖紙，57 張是 AMS 設備沒用到的）、682 個有圖控位置（93 個畫面）；只有相關訊號的 20 個。
- **反方驗證**（2026-10-25，四個鏡頭各自抽樣、在發布的影像與原 PDF 上畫框看圖）：P&ID 錯戶 69 筆（隨機 36 筆對 34）——燃機／汽機、機組 0 筆錯掛，錯的都是對照表 KKS 與圖面對調；共用 KKS／清單 39 筆錯 2；圖控 36 筆錯 7、存疑 5（數字黏合、caption 錯標題、短名撞名、附屬件繼承主設備訊號）；漏網 50 筆找到 EGK01-D0033 整份沒收與排氣熱電偶。上面的規則就是照這些錯誤模式改的，修完重跑後逐項回測（`test_getag` 的 GC-1、TT-XD-16、39V-4A、23QB-1、CV-2 五項）。
- **已知限制**：
  - 線條字的 GE 標籤沒進 OCR 對照表（`pid_ocr --distill` 只留像位號的字；例 VA13-15、FV-24，原始 OCR 快取讀得到，約 8 個條目）。**v11 已做**（`--distill-ge`）。
  - 圖面筆誤（GFD01-D0001 p3 把 TT-R6C 印成 TR-R6C）、附註裡的範圍寫法（「TT-XD-101 TO 104」）、同一顆儀器的 I/O 別名條目湊滿 4 個（96FM-4(SIL)／(TCP)／_PWR）不歸戶，都沒有處理。
  - 圖控畫面顯示的是 I/O 訊號經 MOVE／AI 一對一轉手後的變數時（71GS-1B → F71SCR3DR、45HGT-8A → 96HGT8A，估計約 69 個條目），除了排氣熱電偶之外都還沒做。**v11 已做**（`--chain`，55 個）。
  - 附屬件的 KKS 抄錯（ZS-211AC 寫成 MAB11 而不是 MAA11）時 `host` 會指到另一顆主設備；這是對照表的問題，卡上標「畫在主設備上」、屬推論。**v11 已由對照表更正檔處理**（改正或 `no_alias`）。
  - 母條目沒有位置、子項有（TE-203 只畫 TE-203A/B/C）：照「尾碼必須相等」不給母條目。
  - 對照表與圖面不一致（EGJ01-D0004 的 GC-1～4 與 MKA01 EG001～004 順序相反）時兩邊照實發布，同一張圖可能出現兩處。
  - 圖控只認對照表字面列出的訊號：畫面顯示邏輯複本（`A96HGT2_HGD`）或區段合成值（`TTWR2B`）的元件抓不到；沒進選單的 45 個畫面變數解不出來。
  - 圖控只有本站（G11、G12、S10）的畫面檔，卡上只列本站機組的畫面。
  - 對照表或圖面重建後要重跑 `rebuild.py`（它會跑 `pid_ge`／`hmi_ge`）。

## v11（docs/db 站：GE 編號卡位置的補強與 GE 編號對照表更正；`hmi_ge.py --chain`、`pid_ocr.py --distill-ge`、hst-docsearch `build_ge_tags.py` 的更正檔）

使用者 2026-10-25：v10 報告列的「還沒做」三項都做——P&ID 線條字的 GE 標籤、圖控畫面顯示的是轉手後的變數、GE 對照表本身的錯（GC-1～4 對調、ZS-211AC 的 KKS 寫錯）；P1 腔上下游閥同圖標記仍留在建議裡。三項都經反方驗證（對照表 4 組查證＋4 位反方；轉手鏈與 OCR 新位置 3 個鏡頭），錯誤模式都已改成規則。**AMS 設備卡的 sec.pid／sec.hmi 與 v10 逐台相同（1,928 台）**；sec.getag 有 12 台不同，都是對照表更正造成的：96PGT-3C（G11／G12）與 PDT-216 多了「文件不一致」「對照表更正」兩列，汽機 9 支壓力傳送器的 Mark VIe 訊號改成 I/O 訊號排前面。index.pid／index.hmi 的 AMS 記錄只有 `ge` 計數不同。

- **圖控轉手鏈（`hmi_ge.py --chain`，`rebuild.py` 有 dcdas 索引時自動帶）**：畫面物件引用的變數若是本編號 I/O 訊號經一對一方塊轉手而來，也算位置，`via='chain'`。
  - 只走 `CHAIN_PINS` 的資料腳位：MOVE／MOVE_STATUS 的 SRC→DEST、AI_INT 的 IN→OUT、AI 的 IN→以變數命名的主輸出（不含 `.BQ`／`.INH`）；腳位方向來源 L／H／R／- 不走。使用者方塊、巨集、RUNG、選擇器不走（`d_49gcb → L30GCB_TRP_COIL1` 是任意邏輯）。
  - 起點只用條目 logic 裡**綁在 I/O 點上**的訊號；最多 3 跳、逐層取最短。丟掉：寫入者不只一個的變數（90）、本身就在任何條目 logic／related 裡的（380，那是該條目自己的 io）、名稱去分隔符等於別的編號的（2）。
  - 間接命中另兩條限制（反方驗證）：只出現在長趨勢清單（`addToTrendVars` 另有 ≥ 2 個變數）裡的不算——Trend 捷徑鈕不是顯示這顆設備的地方，同一條也套在 v10 的 `DERIVED`（排氣畫面 TREND 鈕 54 處、Overview 的 9 點 Trend 鈕）；沒有物件外框的（畫面層級參數，18 處）不發布。直接 io 優先於轉手鏈（同一外框兩種都中時留 io）。
  - 每處帶 `chain`＝[[方塊型別, 方塊路徑, 進, 出], …]；起點是 `--sibling` 推來的 G12 訊號時帶 `sib:1`（卡上 lvl＝推論，實測 0 處）；物件屬性裡的標題是另一種 GE 寫法時帶 `cap`（汽機 SIL 振動列標 VX-1X、顯示的是 VP-1X；30 個編號），卡上註明「與本編號的寫法不同，以訊號為準」。
  - 卡上「對應方式」寫出整條鏈（`build_card_aux.ge_chain_text`）：「a_71gs1b →搬移方塊 MOVE_STATUS（HardwireInputs/HW_IN_GFC/MOVE_4）→ F71SCR3DR」。
- **P&ID 線條字的 GE 標籤（`pid_ocr.py --distill-ge` → `tools/db/pid_ocr_ge.json`，不進 repo）**：OCR 快取裡「頭或尾有括號、3～20 個英數與 - /、有字母也有數字、不是 tag_like」的字另寫一份（210 頁 2,123 個），`pid_ge` 併進同一頁的 OCR 字一起比。**`pid_ocr_map.json` 與 `pid_index` 一個位元組都沒動**（重新蒸餾對照表會因舊資料漂移而改到 AMS 設備卡，所以另寫一份；`--distill` 的輸出經比對逐位元組不變）。
  - 去重：只在與文字層位號框真的疊在一起（不加容許邊界，`pid_ocr.overlaps_strict`）、或容許邊界內有寫著同一個 GE 編號的文字層字時才丟——GE 線條字常緊貼在文字層 KKS 的正上方，對照表 tokens 的容許邊界會把它擋掉。
  - 分數 0.65～0.75 的只在與自己的 KKS 併成 ge+kks 時收（`GE_OCR_LOW`；VGS-1、FL1-1、VPR7-2、SF-1 這四個 0.71～0.748）；以 size／mtime／rot 認頁，不符的整頁不用。
  - 結果：多 6 個編號有位置（VA13-15、汽機 FV-24／FV-82／F-2259／LS-253、LCV-3459），另有約 60 處原本只對到 KKS 的現在也對上旁邊的 GE 標籤（ge+kks）；`stats.label.ocr_ge_hits` 68。
- **GE 編號對照表更正（hst-docsearch `ge_tags_dir/ge_tags_overrides.json`，不進任何 repo；`build_ge_tags.py` 在合併之後、連訊號之前套用）**：每筆附出處（文件、頁、原文、有沒有看圖）與反方結論，條目多 `fix`＝{kind, text, basis, confidence, no_alias?, logic_add?}，卡上多一列「對照表更正」。
  - `correction`（14）：清單自己前後矛盾而且有獨立來源支持才改。燃料氣 5 顆電磁閥（20VS4-4、20VG8、20VG-1、20VGS-1、20VSC-1）誤取閥清單 xlsx 的閥本體列 → -MB01／-MB02（說明也換成 SOLENOID）；汽機 ZS-211AC／BC 寫成再熱側 MAB1x → MAA1xQN001-BG04；ST-GEN HV-2987、HV-2996J 一個編號兩列；WSV 混進別顆閥；以及 4 筆只拿掉「其他文件 KKS」裡出自作廢列的寫法（FY-2971／2972、TE-255A／256A）。原寫的進 old_kks 並註明「已更正」。
  - `conflict`（46）：文件之間不一致不替文件選。另一份文件的 KKS 只進 old_kks（查得到、卡上列，但**不**繼承 Mark VIe 訊號、**不**拿去 P&ID 定位）。`note_only`（16）＝只有一份文件寫錯、其餘一致（VE45 互連圖把 4／5 號軸承整組錯一號、互連接線清單把 LSH／LSHH-2990 對調），只記說明、錯的 KKS 不列為別名（原本在 old_kks 的也拿掉）。`no_alias`（12）＝再熱停止閥／攔截閥的附件（FY-1203…、SV-1203A／1204A、ZS-1203C／1204C）與 VE45 寫法的 TE-243E-1／3：清單 KKS 本體掛錯閥，不再經 KKS 別名繼承主設備訊號（v10 卡上它們的圖控位置是另一顆閥的）。
  - `link`（2）與 `logic_add`：I/O 組態的 device_tag 只寫 KKS 或照抄清單錯的 KKS 時，指定要連的訊號（FY-211A／B 的 do_l20cv1／2_qc、ZS-211AC／BC 的 di_l33cv1／2_c_st）。
  - 連訊號規則另改兩處（`link_logic`）：「a_／d_ 前綴」連到的 I/O 點，device_tag 點名的是 KKS 本體完全不同的另一顆時不連（96HGT-1～4 是流量計，a_96hgtN 是濃度計 96HGT-CB-N 的；20VGC-1 的 d_20vgc1 是 4VGC 跳脫裝置的，改列相關訊號）；汽機 device_tag 寫成「KKS/GE 編號」時斜線後那段也認（VP-1X～5Y、DEDP、EP、TE-243-E 等 40 個編號多連 98 個訊號）。
  - 對照表重建前後逐條比對：不加更正檔、不改連訊號規則時與 v10 的 3,956 筆逐欄相同；全部套用後 KKS 改了 10 筆、Mark VIe 訊號有增減的 58 筆，都對得上上面的規則。
- **數字（2026-10-25）**：3,943 個有範圍的條目中 2,556 個有 P&ID 位置（109 張圖紙，56 張是 AMS 設備沒用到的）、727 個有圖控位置（95 個畫面）；與 v10 比：圖控多 57（轉手鏈 55、補連訊號 2）、少 12（v10 掛在錯的閥上），P&ID 多 6。
- **反方驗證**：對照表——發電機組、燃機組、汽機組、全表掃描共 77 筆要改對照表的提案，反方 76 筆成立、1 筆推翻（另 2 筆補連訊號由主控查索引）（45HG-CB-7B：BQ008 只出自同一份清單的舊版，維持舊版 KKS、不標衝突）。轉手鏈 79 個編號（邏輯）＋75 處（截圖）：錯 4 個編號 8 處（96HGT-1～4 的前綴誤連，已從對照表修掉）、趨勢鈕 1 類、無外框 1 類；存疑的 17 處都是畫面標題用 GE 範本槽號（BT-TA1-7 顯示 BT-TA1-6、VX-1X 顯示 VP-1X），改為卡上註明。OCR 新位置 67 處看圖：錯 0（另 2 處錯戶是 v10 就有的 ST-GEN HV-2987／HV-2996M KKS 問題，已由更正檔處理）。
- **測試**：`test_getag.py` 的 `ge_loc` 前面加 9 項：ZS-211AC 改正後的 KKS／「已更正」／新訊號、GC-1 文件不一致、VP-4X 不把 VE45 寫法列為別名、20VS4-4 的電磁閥 KKS 與說明、≥ 50 筆有更正列；71GS-1B 經 MOVE_STATUS 轉手、PT-270C 由設計標題升成訊號位置、VA13-15 與汽機 FV-24 的線條字標籤、≥ 40 個編號經轉手鏈定位。
- **已知限制**：
  - 對照表沒有的編號（HV-2989＝MKG90QM035、汽封母管熱電偶 MAW15BT001／002）不會因更正檔憑空長出來；ST 閥清單 rev G 改版、GT／ST 文件之間的衝突（GC-1～4、96CT-IF-xR、96PGT-3C…）要等 GE 回覆。
  - device_tag 只寫 KKS 的 I/O 點（汽機常見）沒有一般規則去連：只靠 KKS 連會繼承 I/O 組態抄錯的值（FY-211B 的 device_tag 與 SV-211B 重號），這一版只用 `logic_add` 點名。
  - 轉手鏈只認一對一的搬移／類比輸入方塊；畫面顯示的是選擇器、表決或計算後的值（TTWR2B、P1 壓力中位數）仍抓不到。畫面標題只看物件屬性，畫在旁邊的靜態文字（BT-TA1-7）沒註明。
  - 線條字只收括號包著的；附註裡的範圍寫法（「TT-XD-101 TO 104」）、圖面筆誤（TR-R6C）仍不處理。

## v12（docs/db 站：GE 編號卡的位置圖位置與規格格的文件連結；`tools/db/loc_ge.py`、`build_card_aux.py` 的 `ge_ld_rows`／`ge_doc_numbers`、card.js `valueLink` 的 segs）

使用者 2026-10-27：「例如 CT-DA-2 這類有位置圖的，其位置圖有顯示文件號碼 HT0-1-GZD01-M0147 和 HT0-1-GZD01-M0166，可以讓我點選文字就打開對應的雲端文件嗎？並且像 P&ID 和 HMI 一樣直接秀出這個東西在哪裡」。兩件事：(1) GE 編號卡規格格裡的文件編號可點；(2) 位置區多第三塊「位置圖位置」。**AMS 設備卡的分塊（card/aux-NN）與 v11 逐位元組相同**（重建後 git 只動了 getag／getag-loc／index／manifest 與新增的圖紙影像）。

- **規格格的文件編號（`ge_doc_numbers` → `getag.json` 的 `doc_no`）**：GE 編號卡共同列與規格塊裡寫的 HT 文件編號（位置圖、P&ID、Hook-up…；「其他出處／文件不一致／文件狀態／其他文件寫的 KKS」這幾格不算）照 AMS 設備卡 `resolve_doc_numbers` 的規則對到文件庫那一份檔（`resolve_wanted`，兩邊共用：檔名以編號開頭、有指定版次取該版、否則最高版次、PDF 優先、排除副本夾），`file|編號|版次` 的文件併進 `getag.json` 的 `docs`（都有雲端 url）。`--no-drive-map` 時沿用上一份 getag.json 的 `doc_no`。GE 圖號（307T1798、137T9778_1）不是 HT 編號，不處理。
  - **一格寫了兩個以上的編號**（CT-DA-2 的位置圖「HT0-1-GZD01-M0147 HT0-1-GZD01-M0166」）：`valueLink` 回 `segs`＝[{t, href?, title?}]，`fieldEl` 逐段顯示、每個編號各自一個連結（以前整格只連第一個）；來源明細逐份列「欄位所指文件 <編號>」。AMS 設備卡的格子同一套（儀器清單的位置圖欄也可能寫兩份）。
- **位置圖：`loc_ge.py` → `cardwork/loc_ge.json`**（不進 repo；約 3 秒；`rebuild.py` 跟著 `pid_ge` 跑，在 `pid_shots` 之前）。規則與實測依據全在檔頭；要點：
  - 文件集＝GE 對照表每個條目 spec 的 location 欄點名的文件號（`build_card_aux.ge_ld_listed`；GE 圖號 139T8282／301T6191 由圖框印的號碼找到 M0170／GID01-D0009），加 `EXTRA_DOCS` 明列的 6 份（普查看圖確認有元件引線、上面的條目沒有任何位置圖：GZD01-M0145／M0151／M0080／M1203、EGJ01-D0016／D0011）。文件號 → 現行最高版次、排除副本夾。範圍看系統碼（`SCOPE_LETTER`，否則 G＝燃機、T＝汽機）。
  - 比對：GE 編號（`pid_ge.label_hits_page` 的整詞相等、括號、斜線展開）＋逗號接續（`TT-WR-3A,3B,3C`、`96FG-1A,` `1B`、`-3C`）＋括號別名＋形近字（I／1、O／0；有連字號與數字的字、全範圍唯一，而且是引線標註或條目自己的位置圖）＋`-ABOVE`／`-BELOW` 尾綴＋KKS 本體（TZD01-D0002 只寫不帶機組的 KKS；斜線合寫逐段）＋疊寫（KKS／GE 上下兩行：同一條目併一框，別的條目則 KKS 那筆不發布）。**在圖上比對全部條目**，不限清單點名這份圖的；`listed` 記清單有沒有點名。
  - 借位置（lvl 推論）：`alias`＝KKS（本體＋子件）完全相同、名字相近的兩個條目互借（括號寫法、改號）；`body`＝子件借主設備，只在子件自己的位置圖、而且子件在任何圖上都沒有自己的標註（LE-3461 借 LT-3461；主設備沒有 KKS 時 `90VA41-91` 借 `VA41-91`）。控制器／定位器不借感測元件或致動器（反方驗證抓到 TIS-2996B、90ESV-2 借反了）。
  - 這一處算什麼：0＝引線標註；5＝設備表的一列（新代碼；一欄編號的右邊有別的欄才算，疊寫的標註框不算；整頁編號清單另認；不帶連字號、右邊有說明字的 `HV2940U` 也算）；1＝附註／引用（以「片語」判，同一行空隙 > 2 字高就切開：片語 ≥ 5 字且有 ≥ 2 個一般英文字、FOR／TO／FROM／SEE／PER／ON／VIA 之後、下一行以 TO／FROM 開頭的整疊、THRU 之前、不成對的右括號、(H)／(L) 取壓側、詳圖標題、頁面上緣的改版紀錄小字；`LOC_REF_SHEETS` 明列的 GID01-D0009 三頁導壓管示意整頁）。有標註的條目不發布它的表格列；合訂本裡的影本（同一個字、同一個框、頁面大小相同）只留一份，清單點名的優先、其次頁數少的。
  - 壓力量測配置圖（`TAP_TITLE_RE`）的圖紙帶 `tap: 1`，卡上「對應方式」講明引線有的指傳送器本體、有的指取壓點／根閥／導壓管。
  - `sheets` 與 `pid_ge.json` 同一套欄位，另帶 `kind: 'loc'`；`pid_shots --loc-ge` 一併出圖（同一個 slug 在兩份輸入的記錄必須相同），影像進 `card/pid/`。位置圖的圖框分區是線條不是文字，所以沒有分區。
- **`card/getag-loc.json`**：`by_i[序號]` 多 `ld`（與 `pd` 同格式，每張圖紙一組 5 列：位置圖／圖面頁次／所在位置／圖上標示／對應方式）與 `ldn`＝[[文件號, 狀態]]（清單點名的位置圖各自的狀態：hit／miss／nofile／noscope／cap，有任何一份不是 hit 才帶）。`ld` 第一列 extra 另帶 `listed`、`on_body`（主設備繼承）、`via`、`shared?`（alias 的對方、共用 KKS）。`lvl`：文字層、引線標註、不是共用 KKS、不是形近字／別名／主設備繼承 → doc，其餘 inferred（清單沒點名這份圖不降級：GE 圖上的 GE 標籤本身就是證據）。
- **`index.pid`**：位置圖的圖紙在 `sheets` 多 `loc: 1`；`stats` 的 `ge_*` 只算 P&ID（與 v10 同義），位置圖另記 `ld_sheets`、`ld_docs`。index 的 `stats` 另有 `getag_loc.ld_entries`、`ld_sheets`、`ld_listed_missing` 與 `getag_doc_no`。
- **畫面**（`geLocBox`）：P&ID、圖控之後第三塊「位置圖位置（GE 配置／電纜槽／外型圖）」，直接交給 `fillPid`（圖紙標頭、開啟 PDF、細部視窗＋小地圖＋燈箱）；設備表的一列（note 5）標頭寫「※ 這一處是位置圖設備表的一列」；主設備繼承寫「※ 框的是主設備」；`ldn` 印在塊下：「GE 清單『位置圖』欄列的圖：M0147（有位置）、…」。換卡時 `pidRelease` 連位置圖影像一起收。
- **測試**：`test_getag.py` 的 `ge_ld`（在 `ge_loc` 前面）：≥ 1000 個條目有位置圖位置；CT-DA-2 的位置圖 ① 是 M0147、M0166 只留第 3 頁的引線標註（第 4 頁設備表不發布）；TT-WR-3B 逗號接續（M0150）；TT-WS1FI-2 形近字（M0147，推論）；汽機 ≥ 100 個條目以 KKS 標在 TZD01-D0002；`doc_no` 對到 M0147、M0166 的雲端連結；卡上「位置圖」那一格兩個編號各自一個連結、位置圖塊有 M0147、影像與紅框。96FG-1A 的位置區標題改為三塊。
- **數字（2026-10-27，兩輪反方驗證後的規則）**：位置圖文件集＝清單點名 46 個文件號＋`EXTRA_DOCS` 6 份＝52，文件庫找得到 47 個（含那 6 份；找不到的 GAF01-D0001、GBD01-D0002、GID01-D0001、307T1798、139T4816）。GE 清單點名位置圖的條目 822 個，其中 637 個在點名的圖上找到；全部 1,144 個條目有位置圖位置（1,033 個有引線標註、507 個只在清單沒點名的圖上），110 張圖紙（45 份 PDF）。`card/getag-loc.json` 密文 333 KB → 458 KB；位置圖影像 110 檔共 9.3 MB（開那張圖才下載）。規格格裡可開的文件編號 81 個。
- **反方驗證**（兩輪，各組在發布的影像與原 PDF 上畫紅框看圖）：
  - 第一輪 7 組 196 筆：引線標註 55 筆對 44（錯 11：壓力量測配置圖上指取壓點／導壓管的 7、表格列 1、TO 疊寫 1、隱形舊字 1、同名異物 1）；表格／附註分類 35 筆 0 錯；特殊寫法 40 筆錯 4（主設備繼承方向反 3、銘牌小字被當附註 1）；清單點名卻沒找到 30 筆查得對 25；只有表格列的 20 筆錯 5（一排各自加框的標註被當句子 3、形近字閘門、括號別名）。
  - 依錯誤模式改規則（片語、表格擴散只給成欄的編號、TO 疊寫、(H)／(L)、詳圖標題、上緣小字、`LOC_REF_SHEETS`、compact 表格列、形近字閘門、別名、繼承方向、影本留原圖、`-ABOVE`、逗號 `-3C`）後第二輪 3 組 84 筆：第一輪的錯 34 筆修好 19、屬已知限制 14、仍錯 3；新的借位與形近字 30 筆、改分類的 20 筆另找出「置中排的 SYMBOL 欄」「導壓管束說明附近的標籤」「遠端探棒借傳送器」三類，已改（置中欄、TUBE RUNS 範圍、body 只借閥）。
- **已知限制**：
  - 引線終點不分析：壓力量測配置圖（GID01-D0009、M0144、M0163、M0135…，`tap: 1`）的標註有的指傳送器本體、有的指取壓點／根閥／導壓管，卡上講明，不自動區分。
  - 只讀文字層：盤面銘牌是線條字的（EGJ01-D0020 p5 的 PAL-3462／3465）讀不到；同一框疊了看不見的舊字（GID01-D0009 p17 的 96CCS-12A 疊在 96HDASDP-2A 下）照文字層發布。
  - 圖面筆誤（TZD01 的 MAB12CT863＝TE-206W、96GHGT-3）、只標件號氣球（PDS-2996＝件號 17）、用被量測物的編號標儀器（M0163 的 FA110 是 DI-FA110-1 差壓錶）、同名異物（M0135 的 96CCS-1／2 是傳送器，對照表是閥位回授）、刪除線條目（ZS-303）都照實，要改對照表才會變。
  - GE 清單「位置圖」欄有時點錯圖或點得太粗（TZD01-D0002 被液壓油站 MAX 的條目點名、GBD01-D0001 只畫介面），`ldn` 照實列「圖上沒有讀到」。
  - 位置圖的圖框分區號是線條，沒有分區。

## v13（docs/db 站：GE 編號卡的接線路徑——汽機 TSI 從探頭到電子室盤；`tools/db/wire_ge.py`、`build_card_aux.py` 的 `ge_wire_card`、card.js `fillWire`）

使用者 2026-10-27：「ST 汽機監視 TSI 所有偵測元件到現場 local 盤再到電子室的現場位置圖面要像 P&ID 一樣顯示出來，包含接線箱內的端子 TB 接法」。做法：一號機汽機 TSI 的 54 個 GE 編號，GE 編號卡位置區多第四塊「接線路徑（現場 → 接線箱 → 電子室盤）」——每一跳一列的摘要表、每一條芯的端子對照（現場端子 → 接線箱端子 → 盤端子 → Mark VIe 腳位）、文件互相矛盾的註記、各跳的圖（接線圖那一頁、接線箱平面位置、盤內板位、3500 盤端子、3500 機架槽位，同一套細部視窗與燈箱），與同一個接線箱裡的 TSI 端子排。**TSI 沒有中間的「現場盤」**：軸承座接線箱（前置器裝在箱內 DIN 軌）的幹線直接進電子室（ST ELECTRONIC EQUIPMENT BUILDING EER E-402）。**AMS 設備卡的分塊（card/aux-NN）與 v12 逐位元組相同**；非 TSI 的 GE 卡不出這一塊。

- **`wire_ge.py` → `cardwork/wire_ge.json`**（不進 repo；約 7 秒；`rebuild.py` 跟著 `loc_ge` 跑，在 `pid_shots` 之前，帶 `--dcdas paths.DCDAS_INDEX`）。規則與實測依據全在檔頭；要點：
  - 範圍＝`TSI_RE`：GE TSI 訂購圖 TZD01-M0348（GE 137T9953）的八類 46 顆＋Bently 3500 盤同收的發電機 8 顆（39VS-91／92／101／102、39V-4A／4B／5A／5B）。只讀一號機的接線圖（本站 S10）。其他汽機儀器不收：接線圖其他頁的範本變化沒有逐頁驗證過。
  - 文件：接線圖 HT1-1-ICE01-D1005（文件庫現行最高版次＝Rev.3 As Built；試算表附件版次舊、照列對齊會錯配，不用）、JB 位置 HT1-1-IIF01-D0004（p.5 FFL +15.60 m）、盤面配置 HT0-1-TZD01-M0213（GE 137T8654AL，板位與控制器組態逐片吻合）、Bently 3500 盤圖（檔名沒有 HT 編號，以第 1 頁的 GE 圖號 120V8111＋'ST-VMP' 認定）。接線圖 420 頁，文字層快取另放 `%LOCALAPPDATA%\AMS\wiretext\`（pid_lib 的共用快取每份只抽 80 頁）。
  - 接線圖一頁的解析（`parse_page`）：整本由同一個試算表範本產生、欄位 x 固定（`BAND`）；四種畫法 coax（同軸延長線 → 箱內前置器）、tb（現場端子 → 箱內端子排）、jbdev（元件畫在發電機接線箱欄裡）、direct（直拉到盤）。端子格（功能名／端子號那一行收成一格）與芯色標籤用 `order_match`（DP、保持上下順序、一格最多一個標籤）配；**盤側一律以芯色標籤字對接**，不照列對齊（COAX 型的 SH 在盤側不落端子）。前置器區塊以 JB 入線格 'VX-1X COAX' 分段，端子格印錯名字（ZPX-201B／C 的 SH 格印 'ZPX-201A SH'、VP-5X／5Y 印探頭編號）以格子所在的區塊為準並自動註記。
  - Mark VIe：盤端子（板位, 板名, 端子號）對 signal-atlas 索引 `io_screw` 的（position_r, 板名, 螺絲號）；同一顆螺絲掛在幾個點上時取 DeviceTag 與元件相關的那個（`io_relates`：同 KKS／GE 編號，'MAD20BS001/2/3'、'ST-202A,B,C' 合寫也展開；'loc'＝同位置、量測碼不同的電源點 MAD10CY004_PWR）。對不上或沒有螺絲都進 `flags`。
  - 接線箱位置（`jb_locate`）：標籤（KKS 下一行是座標；JB TABLE 那一份不算）→ 沿藍色引線走到底 → 紅線小長方形＝JB 符號，兩個都框。盤內板位（`board_box`）：板名是線條字，框由背板的欄、列標籤推算，是約略範圍（卡上講明）。3500：盤內配置頁 '1TBVIB, SIGNAL…' 三行標註；槽位表 KKS 那一格（槽＝同欄 SLOT 表頭、通道＝同列 CHn）。
  - 註記：自動的（幹線電纜號前綴不是這個接線箱也不是盤；端子格名字與前置器不同）＋人工查證的 `wire_notes.json`（ge_tags.json 同目錄，不進 repo；人工註記已講清楚的自動註記不重複）。
  - 輸出：`sheets`（與 loc_ge 同一套欄位，接線圖 kind 'wire'、其餘 'loc'）、`by_ge`（每一跳的框，帶 `hop`；pid_shots 出圖、pid_check 檢查）、`paths`（每個條目的路徑）、`jbs`（每個接線箱的端子排，照圖上順序）、`stats`。
- **`card/getag-loc.json`**：`by_i[序號]` 多 `wp`＝{`mode`, `sum`[[跳, 內容, lvl, 出處]], `t`[[芯, 現場端子, 接線箱端子, 盤端子, Mark VIe 腳位, 核對]], `rows`（與 `pd` 同格式，每張圖紙 5 列，第一列 extra 另帶 `hop`：wire／jbloc／cab／vms／rack）, `n`[[文字, 出處]], `jb`[接線箱, [[JB 端子, 芯, 元件, 盤端子]…]]}。lvl：接線圖、位置圖、盤圖的列＝doc；Mark VIe 列＝ctrl。`getag.json` 檔頭多 `rule_wire`。`--no-pid` 時沿用上一份的 `wp`。
- **`index.pid`**：接線路徑的圖紙在 `sheets` 多 `wire: 1`；`stats` 另記 `wp_sheets`、`wp_docs`（`ge_*` 只算 P&ID，與 v10 同義）。index 的 `stats.getag_loc` 另有 `wp_entries`、`wp_sheets`、`wp_notes`。
- **畫面**（`geLocBox` → `fillWire`）：只有 `wp` 的條目才出第四塊。摘要表（每一跳一列，滑鼠停在內容上看等級與出處）、芯線對照（Mark VIe 腳位 ✓＝控制器組態的螺絲號核對過是這個元件；✗＝是別的元件）、註記（沿用 `.pid-nosym` 的提醒樣式）、圖（`fillPid`；標頭前加這一跳的名稱 `.wire-hop`；第一張展開、其餘收合、展開才下載）、`details.wire-jb` 同箱端子排（元件連到它的卡）。換卡時 `pidRelease` 連這些影像一起收。
- **測試**：`test_getag.py` 的 `ge_wp`（在 `ge_ld` 之後）：54 個條目有接線路徑；VP-1X 是 coax、BK-1 → JB VX-1X -VDC → CA004-1L1A TVBA 04、腳位 N24V02 核對過；VP-1X 的跳有接線圖／接線箱位置／盤內板位／3500 機架、Mark VIe 列有 a_39vb1x、同箱端子排 ≥ 20 條；VP-5XVL 落 1TBVIB 57 且帶 57／47 的矛盾註記；SEDP-1 直拉、39VS-91 在發電機接線箱；落在 Mark VIe 端子板的 116 條芯全部核對過、沒有一條對不上；VP-1X 卡上第四塊有摘要表、4 條芯、接線圖排第一（雲端連結、影像、紅框）、同箱端子排；CT-DA-2（非 TSI）沒有這一塊。
- **數字（2026-10-27）**：54／54 個 TSI 條目有接線路徑（coax 28、tb 16、jbdev 8、direct 2），落在 Mark VIe 端子板（TVBA／TTUR／TCSA／TBAI）的 116 條芯全部以控制器組態的螺絲號核對過（同元件 112、同位置的 LVDT 電源點 4）；接線箱 7 個（5 個在 JB 位置圖上、發電機的 JB-163／164 不在）、盤內板位 8 個、3500 機架槽位 48 個；圖紙 28 張（接線圖 22 頁、JB 位置圖 1、盤面配置 2、3500 盤圖 3）、4 份 PDF；註記 55 則。
- **反方驗證**（6 組，各自以 300～400 dpi 重繪原圖逐格看）：接線圖 54 個元件 192 條芯（元件、KKS、現場電纜與規格、JB 名與端子、芯色、幹線、盤名、盤端子）資料錯 0、框錯 0；找到的瑕疵已改（-TBB 端子排名漏抓、同軸電纜規格多一個 'COAX'、盤欄說明夾表頭殘字、發電機接線箱端子排沒照圖上順序）。位置那幾跳：接線箱 5 個逐條循引線確認沒有互換、板位 8 個都套住那一片板、3500 槽位 48 個逐格對表、1TBVIB 標註改框三行。註記 7 則＋2 類自動註記逐句對圖：補出處（Bently p.29）、補遺漏（1L4A 的 JB1 與 JA1 也與 Mark VIe 對調、Bently p.24 的通道順序、39V-4A／5A 的芯色、39V-5A／5B 的 57／60、SEDP 的 3500/62 收的是 Mark VIe 轉送值）、改措辭（M0309 的 JB/25 是自己續頁的筆誤、幹線前綴講明電纜表的到端也是 GD010、端子格只有 SH 那格印錯）。
- **已知限制**：
  - 只有一號機（本站）。二、三號機的接線圖（HT2／HT3-1-ICE01-D1005）是施工版、不是竣工版，盤端子與一號機相同但幹線電纜號、速度型延長線線規有差；二、三號機的 JB 位置圖不在文件庫。
  - 電子室只到房間（E-402）：盤在房內哪一列查無可讀的圖（GA 圖是掃描、櫃名讀不出）。
  - 接線箱內前置器、端子排的實體排列沒有圖（只有接線圖的邏輯排列）；盤內板位的框是約略範圍。
  - 文件互相矛盾的地方照列、不選邊（VP-5XVL 57／47、速度型芯色、3500/45 與 JA1 的通道順序、M0377 的板位、JB/18 幹線的出線箱、39V-5A／5B 屏蔽），要現場或 GE／EPC 定讞。
  - 其他汽機儀器（熱電偶、壓力、極限開關…）不在範圍；要做得先逐頁驗證接線圖其他範本。

## v14（docs/db 站：GE 編號卡的接線路徑擴到一號機全部 GE 編號——燃機、汽機、發電機；`tools/db/wire_ge.py`、`tools/db/wire_gt.py`、`build_card_aux.py` 的 `ge_wire_card`／`ge_wire_cards`、card.js `fillWire`）

使用者 2026-10-28：「所有有 GE 編號的元件都要有偵測元件到現場 local 盤再到電子室的現場位置圖面，要像 P&ID 一樣顯示出來，包含接線箱內的端子 TB 接法」。做法：v13 的「接線路徑」從汽機 TSI 54 顆擴到一號機兩份儀控電纜接線圖上的全部 GE 編號（汽機 D1005、燃機 D1004 的 GT-11／GT-12 兩半本），燃機撬上那一跳由 GE 138T5502 補，FF 元件接到段幹線。**一個編號可以有好幾條路徑**（兩台燃機各一條、同一顆的多組接點、電源＋訊號）。**AMS 設備卡的分塊（card/aux-NN）與 v13 逐位元組相同**；TSI 54 顆的路徑內容不變，只多「電纜表」那一跳與「電纜與房間」一列。

- **`wire_ge.py` → `cardwork/wire_ge.json` v2**（不進 repo；約 13 秒，燃機接線圖的向量框線第一次抽要多約 1 分鐘、之後快取）。規則全在兩支檔頭；要點：
  - 範圍：全部 GE 條目，接線圖說明格的 GE 編號（汽機圖只對 ST／ST-GEN、燃機圖只對 GT／GT-GEN）；沒有 GE 編號就看 KKS；都沒有由盤端子反查控制器 DeviceTag（via `io`，那顆螺絲在組態只對到一個點才算）。機組看盤／JB／幹線的 KKS 前綴，不看圖框標題。
  - 汽機 `parse_page` 的修正（TSI 那 22 頁逐頁比對不變）：盤標頭門檻 `PANEL_X`（x≈553 的盤標頭會蓋掉 JB 名，17 頁）、整欄不帶號的芯色（`pick_cores`：3C／5C 電纜，57 頁原本 0 列）、入線芯色帶號的雙支熱電偶、`MCC/SWGR.` 標頭；**盤側對接改成 LCS＋夾縫補配**（標籤筆誤時舊做法會靜默配到別條芯：p.348 TE-260H），補配的芯自動註記。
  - 燃機 `wire_gt.parse_page`：欄位由向量框線定（表頭 FIELD 字給位移，兩半本平移約 16 pt），每條芯以接線短線定位；一頁可有幾個子圖（JB 欄中段的標頭另起一段）；畫法 jbdev／direct／ff（FF 段幹線）／link（盤對盤通訊，不收）；兩層熱電偶頁與分隔頁回空（計數）。
  - 盤端子 `term_parts`：（櫃-板位, 板名, TB, 螺絲號）；'CA001 -1E1A'、'CA004'＋'1M3A TCSA' 接回；'TBDT'／'DBT' 是 TDBT 的筆誤；TDBT 沒寫 TB 用盤表頭的 TERMINAL NO.。
  - Mark VIe（`io_index`／`io_lookup`／`io_rel`）：鍵＝(機組, 櫃, 板位, 板名, 螺絲號)，TDBT 以 io_screw.note 分 TB1（繼電器）／TB2（接點）（兩排螺絲號重疊）；S1S 的櫃號在索引是 'Group'（記成空）；圖上 TBTC 而組態是 STTC 換算通道（⌈n/2⌉）並註記。關係 ✓ same／logic（變數就是對照表的訊號或變數名含 GE 編號）／equip（DeviceTag 是同一設備的 KKS，或對照表 linked 的量測鏈）／loc／suffix，≈ alias（名稱寫法不同），✗ other（組態掛的是另一個 GE 編號、數字也不同）／spare（備用點）。✗／≈ 自動註記，措辭不選邊。
  - GE 138T5502（`wire_gt.parse_conn`，HT0-1-GID01-D0003 Rev M）：一芯一列的向量表格，以（JB, 端子排, 端子）接上 D1004 的 JB 端子格（`jb_same`：'JB637C-WL1'＝'WL1'）；接上的路徑多 `field`（元件端子、芯色、電纜、經過的中間元件、JB 端子、JB 所在）與 `conn`（那幾列的框）。
  - FF：燃機圖的 'ff' 子圖（段保護器 FBSP-GT-n 的段幹線 → CA002 FFPCn Sm）；138T5502 上 JB 欄是 FBSP-GT-n 的元件接到那一段，路徑帶 `ff`{seg, port, loc, dev（中間 FF 傳送器）, members, s, vars, other_s}；`ff_index` 以控制器變數宣告的 FF_IN_S(8(n−1)+m) 核對，段號對不上自動註記。
  - 身分與芯的歸屬（`identify`／`build`）：說明格有括號編號時以括號裡的為準（'… FOR 52GX-1/2 RELAYS (52G/AUX)' 只是 52G/AUX）；括號被斷行切開時沒配對的 ')' 也算括號裡；同一子圖幾顆元件時，芯依控制器螺絲（只認組態裡只對到一顆的螺絲）投票分給元件，只剩一顆沒分到時沒歸屬的芯給它；同一顆的兩種寫法（TE-243-E1／TE-243E-1）共用芯。合寫 KKS（'MAV01EB011,12,13'）展開後算同一設備。
  - 盤端子格與電纜表的補充（第二輪查核後）：'CA001-1C1A- TBDT-TB2 21' 這種格（板位尾巴多連字號、板名與 TB 連寫）拆成板位／TDBT／TB2；說明格裡不帶機組前綴的 KKS（'LBH31QM001-BG02'）也算圖上寫的設備 KKS；電纜表刪除線的舊列（'…-WG008' 少連字號）也算一列，系統層的盤碼（'S10BPA10'、'C10BBT10'）認得；S 開頭的精簡型端子板（STTC、STAI、SCSA、SPID、SHRA…）框半格；電纜表最右邊 Revision 欄寫 '#1'／'#2' 的列是刪除線（已刪除）的列（`del`），同號以現行列為準，「查無、同一個設備的電纜是…」不列已刪除的列、前綴是盤時不出；對照表同一顆的兩筆（寫法去符號相同，或 KKS 相同：96FM-4／96FM-4(TCP)）共用芯。
  - 電纜表那一跳的註記：圖上幹線規格與電纜表不同（'4T-18' 與 '04T-18' 視為相同）、電纜表查無這條電纜，都自動註記；燃機 138T5502 同一組 JB 端子有兩個去處（p.167 88BT-1 與 23QT 共用端子）寫成註記，不另開路徑；CUST AO 頁的重複路徑不收。
  - 位置：汽機 JB（IIF01-D0004，v13）、燃機撬上 JB（`gtjb_locate`：GE 137T6223 p.11 JB 表那一列與座標、p.12 等角圖標籤）、電纜表（`cable_schedule`：A1005／A1004 那一列的兩端房間、設備、型式、長度；以房間碼、設備 KKS 的字形切欄，兩份表欄位 x 不同）、盤內板位（`cab_page`＋`board_box`：汽機 M0213、燃機 A1002，背板與左右側板；欄標籤取最上面一排、列標籤取緊靠左側那一排）。
  - 其餘接線箱所在的設備圖（`JBDOCS`＋`jbdoc_locate`，hop `jbdoc`）：汽機 JB 位置圖與燃機 137T6223 都沒有的箱子，到 12 份 GE／廠商外形圖、配置圖上找標籤——燃機／汽機發電機電氣外形圖（EGJ01-D0012、EGK01-D0009；跳過寫 IDENTIFICATION 的尺寸表頁，框視圖上的標籤）、兩台發電機的氫氣封油盤（EGJ01-D0020、EGK01-D0011）、氣體乾燥器（EGJ01-D0017）、出線箱氫氣抽氣偵測（EGJ01-D0050、EGK01-D0045）、集電環室氫氣偵測（EGJ01-D0070、EGK01-D0046）、汽機控制接線位置圖 VE02（TZD01-D0002）、汽機潤滑／液壓油箱 VR20（TAD01-D0004）、燃機細水霧撬（GZD01-M1203）。先找 KKS 寫法（'JB-MAD20GD020'、封油盤標示的 'MKW15UC110'），沒有才找箱名（'JB-5C'、'JB/10A'、'JBR-7A'，比對時去掉連字號、斜線、'-ABOVE'／'-BELOW' 與前導 0）：VE02 上 'JB/2' 這種短號在別張圖是另一個箱子；KKS 找到的那一頁，不是短號的箱名也一起框，最多 4 個框。不算標籤的（`jb_label_ok`，看圖查核後加的）：一般註記的句子（同一行左邊 ≥ 5 個字或右邊 ≥ 3 個字）、元件表的列（同一欄上方 25 個字高內有 DESCRIPTION／TAG／TABLE 表頭）、走線說明（左邊或上一行是 TO／FROM、右邊或下一行有 HIDDEN）；一頁只剩這些的就往下一頁找（細水霧撬 JBX001 由註記頁改到 p.4 的標籤、VE02 的 JB-MAD50GD010 由 p.4 的 'TO … (HIDDEN)' 改到 p.9 的立體圖）。用箱名找到時，標籤下方兩行內寫的箱子 KKS（設備碼 G*／U*／X*，例 '(MAV01GD001)'、'CKB01XD103'）與接線圖不同就註記（`kks_drawn`）。這些圖只標出箱子在設備上的位置，沒有廠區座標，卡上講明。
  - 文件交叉比對的註記：發電機接線箱（KKS 含 MKA10XG）不在該機發電機外形圖上的（燃機 JB-5D：燃機發電機外形圖只畫 JB-163、JB-164、JB-5A、JB-5C、JB-508、JB-510、JB-513）；`gtjb_rows`／`gtjb_conflicts`：137T6223 JB 表的箱名與 KKS 和接線圖交叉不一致的（表上 JB20RA 那一列是 XXCKB01XD102，接線圖 JB20RA 是 CKB01XD101、JB529B 才是 CKB01XD102；表上 JB20 是 XXCKB01XD101；JB169B 與 JB34C 在表上同為 XXMBY01XD109）——座標屬於哪一個箱子不判定、不採用，兩邊的卡都註記。同一列＝XX 碼左邊、上下差 ≤ 5 pt 最近的字，箱名欄不是 JB 開頭的列不收。
  - 輸出：`paths[鍵]` 是清單（每條帶 unit、doc、via）；`by_ge` 的框多 `pi`（路徑序）；`jbs` 鍵＝'機組|JB 名'，`strip` 是那個子圖的每一條芯（不論認不認得元件，第 8 欄是 GE 鍵）；`ff`＝每個段的幹線；`stats` 改版（by_system、by_unit、by_via、tsi_*、boards_missing…）。
- **`card/getag-loc.json`**：`wp`＝第一條路徑，多 `u`（機組）、`f`（GE 接線表那一跳）；`wpx`＝其餘路徑（同格式）；`wpn`＝1：有 Mark VIe 訊號但沒有路徑；`wpr`＝其中組態把訊號接在實體螺絲、而接線圖上那組螺絲畫在別的編號底下的：[[機組, 控制器.變數, 板位 板名 點名, 那個 GE 編號, 接線圖頁]…]（`ge_wire_xref`，來源是各路徑核對螺絲時記下的組態點 `paths[k].io`，不另查索引；每台機組最多 4 筆；常見是同一台設備的另一組接點、別名或圖面與組態不一致，只指位置不判定）。`rows` 的 hop 多 conn／gtjb／gtjbt／jbdoc／cs。`jb` 的端子排每列多第 5 欄（是不是 GE 編號，給前端決定要不要做連結）。摘要表多「現場 → 接線箱（GE 接線表）」「FF 段」「段幹線」「電纜與房間」列；終點不是 Mark VIe 的寫明「沒有控制器螺絲可核」。「接線箱」列：有設備圖的寫「〈圖名〉〈文件號〉第 N 頁有畫（圖上寫…；沒有廠區座標）」；電氣盤（MCC、PC、EMCC、GPP、MSP、GCB、啟動盤…，`GE_WIRE_PANEL_RE`，名稱 JB 開頭的不算）寫「這是電氣盤／設備（不是接線箱）」與格位（'G11BFB10_A3C' → 第 A3C 格）；沒有位置圖的都補電纜表上那一端的房間（`ge_wire_jb_room`：設備碼含這個箱子 KKS 的那一端，否則第二端）。`rule_wire` 改 v14。
- **畫面**（`geLocBox` → `fillWire`）：多條路徑各一個 `.wire-path`（標題「G11 第 1 條：盤…」）；有站別（G11_…）時只列那一台；`wpn` 的條目出一句查無與查過的範圍，有 `wpr` 時下面列「控制器.變數（板位）→ 接線圖第 N 頁畫在 X 底下」並連到 X 的卡（`ul.wire-xref`，有站別時只列那一台）；`table.wire-field` 列 GE 接線表的每一芯；Mark VIe 腳位 ✓／≈／✗（`GE_WIRE_MARK`，說明在 title）；端子排是整排（`details.wire-jb`），認得 GE 編號的才是連結。
- **測試**：`test_getag.py` 的 `ge_wp` 改寫：TSI 54 顆都有、全部 1,000 條目以上有、wpn 300 以上；VP-1X 那幾條照舊（多 cs 那一跳、電纜與房間列提到 E-402）；TSI 落在 Mark VIe 的 116 條芯全部 ✓；96CD-2A 兩條（G11、G12）、BK-1 → TBA 13 → CA004-1L4A TBAI 17 ✓；CT-DA-4 是 ff、有 GE 接線表的列、FF 段列、Mark VIe 列寫 FF_IN_S28、第一跳是 GE 接線表；23WR-1B 兩芯 ✗ 且註記指名 23WR-3A；96HDASDP-3A 的註記指名 FF_IN_S15；畫面上 96CD-2A 兩個路徑框、第一張接線圖是 D1004；孔板 FO-3 沒有這一塊；wpr 75 個以上、MIC-2996 的 wpr 指到 G11 p.388 的 ME-2996（1B2A TBAI AnalogInput03），卡上「查無」下面有 ME-2996 的連結；第一條路徑帶 jbdoc 的 100 個以上、LT-260 的 JB/21 框在 VR20 油箱配置圖（接線箱列寫 MLI VR20）、燃機 39VC-101R 的註記寫 JB-5D 不在燃機發電機電氣外形圖、52GT-1 的 GPP 接線箱列寫電氣盤與 E-305。
- **數量（2026-10-28 建置）**：3,956 條目中 1,329 個 GE 編號有路徑，共 2,206 條（G11 800、G12 791、S10 615；via ge 1,866／io 197／conn 132／kks 11；畫法 jbdev 1,691、ff 207、direct 183、tb 95、coax 30）；TSI 54／54；控制器螺絲核對 3,609 芯：✓ 3,260（same 2,831、logic 367、equip 50、suffix 8、loc 4）、≈ 76、✗ 97（other 70、spare 27）、索引無這顆螺絲 176（多是 SPID 108、TSVC 的 LVDT 60）；有電纜表房間 2,180 條、有燃機 JB 位置 585 條（577 條有座標）、接線箱在設備圖上 330 條（51 個箱子，12 份圖）、有 GE 接線表的列 256 條、FF 158 條；要接線箱位置的 1,816 條中 829 條有（汽機 JB 位置圖 107、燃機 137T6223、設備圖），其餘 987 條＝電氣盤 700（691 條寫電纜表房間）＋現場接線箱 287（62 個箱子，273 條寫電纜表房間）；註記 509 則（含發電機外形圖不在 58、137T6223 箱名／KKS 交叉不一致 70、設備圖上標的 KKS 與接線圖不同 64）；圖紙 1,034 張；盤內板位 112 塊都找到；有訊號沒路徑 475 個，其中 84 個帶 wpr。`getag-loc.json.bin` 由約 0.5 MB 變約 1.4 MB（未壓縮約 26 MB）。
- **看圖查核（接線箱設備圖）**：每份設備圖抽一條（19 張）、JB20RA 那一列、8 個電氣盤的電纜表列與房間、燃機發電機外形圖上沒有 JB-5D，共 28 項交 5 組反方看渲染圖：21 項全對；7 項是正確的框之外多框了註記句子、元件表的列或走線說明（JBR-6 NOTE 6、JBX001 兩處註記、JB-512A／JB-529A 的 TABLE 1、'TO JB-MAD50GD010 (HIDDEN)'），已用上面的規則排除並重畫確認；另指出 JB21、汽機 JB-529A／B、JB-512A 圖上標的 KKS 與接線圖不同，改成註記。
- **已知限制**：只做一號機（G11、G12、S10）；燃機兩層熱電偶頁（GT p.395–400 等）與分隔頁不解析；FF 元件在段保護器上的埠號（spur）在已索引文件裡沒有；JB20RA、JB529B 在 137T6223 的座標列箱名與 KKS 交叉矛盾，不採用；燃機 JB-5D、JB-90、JB300／JB301、UAT、JB505、JB512N 等 62 個現場箱子沒有位置圖（JB512N 的中性點接地盤配置圖是掃描圖）；設備圖只有箱子在設備上的位置、沒有廠區座標；MCC／PC／EMCC 的格位配置圖（EP24）有文字層但這版沒有框（v15 已框，見「v15」）；發電機 RTD → JB-5A 不在兩份接線圖範圍；E-305／E-402 房間配置是掃描圖，沒有房間內位置；部分 ≈／✗ 判斷是名稱比對，卡上只列事實不選邊（例 72EBOP、4ESOPX、4QEZ、TE-201W）；電纜表遠端房間空白 274 條。

## v15（docs/db 站：GE 編號卡的迴路圖與電氣盤格位；`build_card_aux.py` 的 `ge_wire_loop`、card.js `fillLoop`／`loopSvg`、`tools/db/wire_ge.py` 的 `MCC_DOCS`／`mcc_*`／`shield_bars`）

使用者 2026-10-28（v14 回覆的兩個建議，「好，都幫我做」）：① ISA-5.4 式迴路圖——用卡上已有的資料，每條路徑畫一張「元件 → 接線箱端子 → 幹線 → 盤端子 → Mark VIe 腳位」的單線圖，可以列印；② MCC 格位框圖——GE 的 MCC／PC 盤面配置圖（EP24）有文字層，把電氣盤直接框到格位。**AMS 設備卡的分塊不動**；接線路徑的芯、端子、房間、各跳、I/O 核對與 v14 逐條相同（`wire_ge.json` 比對：只多 mcc 一跳、`shield`、`kks_drawn` 與 25 則註記），卡上多 `wp.d`、`t` 每列多兩欄、盤側沒畫端子的屏蔽線改寫法。

- **迴路圖（前端畫，不另載檔）**：`build_card_aux.ge_wire_loop` 在每條路徑多 `d`（空的不輸出）：kk＝本台 KKS、kw＝接線圖說明格寫的 KKS（與 kk 不同時）、ds＝接線圖說明、fc／fs＝現場電纜與規格、jb／jd／jt／px＝接線箱、說明、端子排、前置器、jl＝接線箱位置短句（汽機 JB 位置圖座標／137T6223／設備圖頁／電氣盤格位與「盤面配置圖 p.N 有框」／沒有位置圖＋電纜表房間；FF 的段保護器也算）、tc／ts／tl＝幹線、規格、長度、rf／rp＝電纜表上接線箱（或現場）那一端、盤那一端的房間（`ge_wire_rooms`；`ge_wire_jb_room` 改成取它的第一個，結果不變）、pk／pn／pr＝盤 KKS、盤名、盤所在房間、cp＝盤內位置（板位、背板／側板、板名）、io＝[[控制器, I/O 模組, 板位, 板名, 點, 變數, 核對]…]、ff＝[段, 埠, FF_IN_S 段號, [變數…]]、fm＝這一條是段保護器本身時接在這一段的元件、sb＝[IS 排, OS 排]（這一頁盤欄底部印的屏蔽排說明）、pg＝[接線圖 PDF 頁, Sheet, 共幾張]。`t` 每列多 [盤端子號, 組態的點]（前 6 欄不變，表格照舊）；盤側沒畫端子的屏蔽芯，盤端子欄由「（盤側不落端子）」改成「（盤側沒畫端子；這一頁盤欄底部印「IS → B 排、OS → A 排接地」）」（有屏蔽排說明的頁）。FF 段幹線本身（沒有段號）的 Mark VIe 列改寫「FF 段幹線：接到〈盤〉的 FF 電源調節器（〈櫃 板 段〉）；段上各元件的控制器 FF 變數在各元件的卡上」（原本寫「不進 Mark VIe」）。
  - card.js `fillWire(wp, ix, el, mode, href, lp)` 多第 6 個參數 {tag, open}；說明行之後放 `details.wire-loop`（多條路徑時只展開第一條），內含「列印這張迴路圖」「下載 SVG」兩個鈕與 `.loop-fig`。`loopSvg` 用字串組 SVG（U.h 建的是 HTML 元素，畫不出 SVG）：寬 1120，標題列（編號、KKS〔kw 不同時並列「接線圖寫 …」〕、機組、接線圖頁與 Sheet）→ 五區（現場｜接線箱｜幹線｜電子室盤｜Mark VIe，虛線分隔；直拉的第二區寫「沒有接線箱」，FF 寫「FF 段保護器」，電氣盤寫「電氣盤（不是接線箱）」並以粗框，沒有 Mark VIe 的最後一區寫「終點」並放摘要表那一句）→ 一條芯一列：元件是 ISA 現場安裝圓圈（沒有橫線），**每條芯從圓圈上各自的點出線**（共用一點會看成接在一起）；芯色寫在幹線上，屏蔽線虛線（虛線只代表屏蔽線）；**盤側沒畫端子的屏蔽線畫到盤邊為止、寫「盤側沒畫端子」，不畫接地**；有 sb 的在盤框底部照抄「屏蔽排：IS → B 排 OS → A 排」＋接地符號與「（接線圖盤欄底部的說明，沒有逐芯畫）」。依畫法：tb 畫現場端子與現場電纜；燃機有 GE 接線表的元件端子（f）照 JB 端子對上；coax 箱內畫前置器；jbdev 而沒有 GE 接線表的——電氣盤（MCC／PC 的格）把盤框從現場區延伸過來框住元件（接點在盤內），其他接線箱畫成元件在現場區、以灰線接到箱內端子並寫「接線圖上元件畫在端子排旁、沒有現場電纜號；中間若有轉換器、放大器或另一個箱子，不在這張圖上」（96KP 的電荷放大器、MIC-2996 變送器、JB87 的 CAN、JB-164 都是這種）；ff 有 GE 接線表的畫元件端子 → FF 傳送器（f 的經過欄）→ 支線各芯到段保護器的埠端子 → 段匯流排 → 段幹線，沒有的畫一條支線到埠；段幹線本身（段保護器）不畫元件圓圈、寫明「這一條是 FF 段幹線本身」。幹線電纜號、規格、長度分三行（不截斷）；接線箱端子框依字寬加寬（最寬 150）；Mark VIe 每列「螺絲｜通道｜變數」＋ ✓≈✗（`GE_WIRE_MARK`，title 是 `GE_WIRE_IO` 的核對依據）→ 接線箱位置、房間、接線圖說明（寫在下方，不放在現場的斜線上；FF 元件另寫元件 KKS）→ 出處（rows 裡每一跳的圖與頁）、⚠ 註記（最多 8 則、每則最多 3 行）、兩行圖例（✓≈✗、虛線＝屏蔽線；依文件自動產生、不是竣工圖、不替任何一方選邊）。樣式寫在 SVG 自己的 `<style>`，選擇器都掛在 `.loop-svg` 底下；白底黑線，深色主題也一樣。
  - 列印：按鈕把這張 SVG 放進 body 底下的 `#loop-print`、body 加 `print-loop` 再 `window.print()`，`afterprint` 收掉；app.css `@media print` 只留 `#loop-print`（`@page loop` A4 橫向）。整頁列印時迴路圖跟著卡片印，鈕不印。下載：Blob（`<?xml…>`＋SVG）存成 `迴路圖_<編號>_<機組>.svg`。
  - 手機：`.loop-fig` 自己水平捲動（SVG 最小寬 760 px），頁面不橫捲。
- **電氣盤格位（`wire_ge.py` 3d，hop `mcc`）**：接線圖「接線箱」欄是 480 V MCC／PC 格位的（`MCC_RE`：'G11BGB10_A1C'、'…PC-GT111/G11BFA10_2D'、'S10BGB10-A2A'、'G11BKB20_NP3-3'），框在 GE EP24 盤面配置圖正視圖上那一格。
  - 文件（`MCC_DOCS`，檔名沒有文件號，`resolve_title` 照檔名標題找、取最高版次）：480V MOTOR CONTROL CENTER FOR UNIT 1 GT1（revQ）／GT2（revR）／ST（revP）、480V POWER CENTER (G11BFA10, G11BGA10)（revO）／(G12…)（revO）／(S10…)（revP）；ge-scrape 的同名 EP24_EA_001／002 與這六份逐位元組相同。
  - 排在哪一頁（`mcc_pages`）：只看有 'FRONT VIEW' 的頁；MCC 認正視圖上方的大字標題（字高 ≥ 8 pt，圖框右下標題欄的小字不算），PC 認 '(G11BFA10)'，都沒有（ST 的 EMCC 標題是線條字）才看斷路器編號最多的那一排；同一頁兩排（GT 的 BFB10＋BGB10）格位標籤歸給水平距離最近的標題；排名稱（'MCC-GT111'、'PC-GT122'）一起記。
  - 格子（`mcc_cell`）：格位標籤（'A1C'、'2B'；沒有尾字母的 'A1'、'A3' 不算）寫在格子左下角；框線取有顏色、線寬 > 0 的（寬 0 的是盤內單線圖走線，會穿過格子）——左＝標籤左邊最近、跨過標籤的垂直線，下＝標籤下方最近的水平線，右＝標籤右邊最近的垂直線（MCC 是門板線，右邊的配線槽不算），上＝標籤上方最近、橫跨這一格八成寬的水平線。PC 的正視圖頁轉了 270°，全部在顯示座標算。
  - NP 區（`mcc_np`，EMCC 的 'NP3-3'）：正視圖上只有區頂的 'NP3-1' 是文字，小格銘牌是線條字——區＝'NPa-1' 字左右整區高（≥ 60 pt）的垂直線（字外面的銘牌小框不算），小格＝區內從左緣拉到右緣的隔板由上往下數第 b 格（推算，approx）；另框左上 NP 表（'NP NO.' 那一欄）上 'NPa-b' 那一格：左右＝表格的垂直框線（右邊是 DESCRIPTION 欄的右框）、上下＝橫跨整張表的水平線（表格右邊緊鄰 TOP VIEW，不用字的範圍推），比對用那一列的說明。
  - 比對（`mcc_match`，不判定誰對）：格內寫的 KKS（'G11MBV01GQ002' 下一個字 '-MA01' 接回）與這條路徑的 KKS、dkks、說明格寫的 KKS、說明格點名的 GE 編號（'(88QA-1) Lube Oil Pump 1 Motor - Available' 的 88QA-1）的 KKS 比本體前 10 碼：same（就是這個元件的 KKS）／same_rel（接線圖說明格寫的、或點名的設備的 KKS；這個元件自己的沒有寫在格內）／system（系統碼同）／breaker（格內只寫這一排自己的斷路器編號，沒有負載 KKS 可比）／nokks（這條沒有 KKS）／space（SPACE／SPARE，註記）／diff（別的設備，註記）／none。排名稱：接線圖寫的（'PC-GT112'）與圖上的（'PC-GT122'）不同時註記（排的 KKS 與格位相同、名稱不同）；格位標籤在正視圖上找不到時註記。
  - 輸出：`paths[k].mcc`＝{lineup, cub, content（格內字，≤ 160）, match, approx, np}；hop ['mcc', 圖紙, 框（格子；NP 再加表那一格）, '排 格']；`stats.mcc_cells`、`mcc_paths`，`scan.mcc_*`。
- **其他產生器改動（`wire_ge.py` 3c2，第四輪查核後）**：`shield_bars`：接線圖一頁盤欄底部的屏蔽排說明（'IS' 右下 'B'、'OS' 右下 'A'；左上角圖號欄的 'IS' 不算）→ `paths[k].shield`＝{IS, OS}（729 條路徑）；接線圖上緊貼這個編號寫的 KKS（'TE-201V/ S10MAA11BT863'、'S10MAB10BT005C (TE-205C)'；沒有緊貼的才看整段只寫一個 KKS 的）本體與對照表的 KKS 不同 → `kks_drawn` 與註記（「接線圖〈說明格／接線箱或盤欄標頭（…）〉寫這個元件的 KKS 是 X，GE 編號對照表是 Y；對照表上 KKS 是 X 的是〈別的編號〉：兩份文件不一致…」——TE-201V／TE-201X 互相指名）；燃機發電機接線箱不在外形圖上的註記，若 GE 燃機發電機接線圖 HT0-1-EGJ01-M0109（`GEN_WIRING`）的元件表有這個箱子，改寫成「…第 2、9 頁的元件表有 JB-5D（箱子存在，這兩份圖都沒有畫出位置）」（58 則）；同一條電纜兩芯標同一個芯色號 → 註記；人工註記 `wire_notes.json` 寫在 'ST|REDP-1A' 的，對照表另一種寫法 'ST|-REDP-1A'（VE45 互連清單的寫法）也出。
- **`build_card_aux`**：`GE_WIRE_HOP`／`GE_WIRE_REL` 多 mcc（'電氣盤格位（GE EP24 盤面配置圖）'、exact——各機組一份）；「接線箱」列的電氣盤句子多「盤面配置圖〈檔名〉第 N 頁〈排〉正視圖上框出〈格〉格，〈比對結果〉」（`GE_WIRE_MCC_MATCH`；NP 加「照區內隔板推算，另框 NP 表那一列」）；格位改認 `GE_WIRE_MCC_RE`（'S10BGB10-A2A' 的連字號也算）；圖紙的「所在位置」「對應方式」列寫 mcc 的框法。card.js `GE_WIRE_HOP` 多 mcc：'電氣盤格位'。
- **測試**：`test_getag.py`：每條第一路徑都有 `wp.d`；第一條路徑帶 mcc 的 80 個以上、23HG-1 的接線箱列寫「G11BGB10 正視圖上框出 A1C 格」與 G11MKA10EB001、KKS 相同，d.jl 寫「盤面配置圖 p.11 有框」；88BT-2 的 G12 那條註記 PC-GT112／PC-GT122；VP-1X 卡上迴路圖一張、展開、寬 ≥ 300 px，SVG 的字有 VP-1X、-VDC、TVBA、N24V02、✓，兩個鈕都在；「列印這張迴路圖」（把 window.print 換成記錄器）時 `#loop-print` 只有這張 SVG、body 有 print-loop，afterprint 後都收掉；「下載 SVG」存出的檔有 xml 宣告、xmlns、自己的 `<style>`；96CD-2A 兩條路徑兩張迴路圖、只有第一張展開，兩張都有 TBAI 與 P24V5。全部 513 項（`test_getag` 130）。
- **數量（2026-10-28 建置）**：迴路圖 2,206 條路徑都有資料（`getag-loc.json.bin` 約 1.46 → 1.6 MB）。電氣盤格位：6 份 EP24 圖、12 張正視圖頁、14 排、51 格全部框到（MCC 40 格、PC 11 格；NP 小格 4 種 7 格），260 條路徑（112 個 GE 編號）；比對 same 94、same_rel 141（例 30QA1 是 88QA-1 馬達的接點；23HT-3B 與 23HT-3A 共用一格）、breaker 10（GT 的潤滑油加熱器 23QT 那兩格只寫斷路器編號）、nokks 15、diff 0、space 0；排名稱不同 6 條（G12BGA10：接線圖 PC-GT112、圖上 PC-GT122）。屏蔽排說明 729 條路徑（汽機接線圖 291／420 頁、燃機 188／855 頁印著）；盤側沒畫端子的屏蔽芯 720 條、其中 643 條所在頁有說明。註記 509 → 534（排名稱 6、接線圖 KKS 與對照表不同 15、同標芯色 2、對照表另一種寫法的人工註記 2）；圖紙 1,034 → 1,046 張（新增 12 張 EP24 正視圖頁）。偵察 3 組另行量的 51 格框與本產生器的框 IoU 全部 ≥ 0.9。
- **看圖查核**：第四輪 6 組（51 格、27 張迴路圖、ISA-5.4 完整度評審）與 2 組複查，見報告 v1.2 §10。
- **已知限制**：只框 480 V MCC／PC 的格；其餘電氣盤（GPP 191 條、MSP 104、GCB 62、MV CUBICLE 20、UAT 14、EX2100e 11、LCI 8、52ET 8、DC 啟動盤 46…）不在 EP24——偵察過的結果：GPP、GCB、MSP、UAT 的配置圖有文字層可框到端子排，MV CUBICLE、52ET 可框到隔間，LCI、EX2100e 文字層偏移或只有舊版，DC 啟動盤是掃描圖；GT 的 23QT 加熱器那兩格（G11BFB10 A3C、G12BFB10 A2D）圖上只寫斷路器編號，加熱器 KKS 不在圖上，沒有比對；EMCC NP 區的小格是照隔板順序推算；迴路圖畫的是文件上的接法（接線圖、電纜表、組態），不是竣工圖；訊號型式、迴路供電、Bently 3500 並聯分支、迴路圖編號沒有畫。

## v16（docs/db 站：其餘電氣盤的端子排、迴路圖的中間設備、3500 並聯分支、訊號型式與迴路供電、迴路圖編號；`tools/db/wire_ep/`、`tools/db/wire_sig.py`、`wire_ge.py` 1c／2b／3e／4b／4c、`build_card_aux.py` 的 `ge_wire_ep_txt`、card.js `loopSvg`）

使用者 2026-10-28（v15 回覆的四個建議，「請幫我做，有專家級的建議也請提出」）：① 其餘電氣盤（GPP、MSP、GCB、UAT）框到端子排；② 迴路圖補中間設備（GE 138T5502 的電荷放大器、ME-2996 → MIC-2996…）；③ 迴路圖加訊號型式與迴路供電（推論的標【推論】）、Bently 3500 並聯分支、迴路圖編號的標題欄；④ 對照表重複列 -REDP-1A／REDP-1A。**AMS 設備卡的分塊不動**；接線路徑的芯、端子、房間、I/O 核對與 v15 逐條相同，差異只有：ST|CT-20 補上盤側端子排 TBCT／接線箱端子排 TBSC-S（標頭說明的 GND 被當成芯色、表頭範圍算短）、GCB 低壓箱 '-XT07-NN' 格子（8 條）拆成端子排＋端子號、ST 52L2／52L3 CLOSE 兩芯的 ✓ 改 ✗（變數名與 DeviceTag 交叉）、兩個 '-REDP' 鍵併掉（對照表）、GT-GEN|39VE-1R 在接線圖 p.257／677 那兩條改掛 GT|39VE-13R（接線圖漏字）、38 條路徑多 GE 接線表那一跳、RP-1 (Jumpered) 拿掉 3500 槽位、燃機 38 條多 3500 槽位。

- **其餘電氣盤的端子排（`wire_ge.py` 3e，hop `epnl`）**：接線圖「接線箱」欄或盤欄是 GPP、手動同步盤（MSP）、GCB 低壓箱、UAT 就地箱、LCI 中壓盤／52ET 的，框在那份設備圖上。定位程式在新套件 `tools/db/wire_ep/`（六個子模組：gpp_gt、gpp_st、msp、gcb、uat、mv；只用 stdlib＋fitz，偵察版移植、門檻照舊），介面 `doc_specs()`／`group_of(unit, 文字)`（看盤的 KKS：MKY40UC00x、CCS01UC001、MSC20XD512、C[123]0B[BC]T10、MBJ10UC200／MKC10QA101）／`build_indexes()`／`locate()`／`missing()`；hit＝{doc_key, page, box（未轉的 PDF 座標）, kind strip／term／row／cmp, label, primary, extra}，`wire_ge.disp_box` 轉成顯示座標再 `mark_of`。
  - 文件（`wire_ep.DOCS`，第三欄＝一份圖多台共用）：燃機 GPP GE 140T1264（HT0-1-EGJ01-D0023，共用）；汽機 GPP GE 140T1267（HT0-1-EGK01-D0018，GE 出廠圖 AS-SHIPPED、HT0 全廠編號，共用）；手動同步盤 G11＝EOMR HT1-1-AQB01-Q1980 裡的 226B4841 rev04（向量，蓋 DRAFT 浮水印；正式版 HT0-1-EGJ01-D0071 是掃描圖）、S10＝檔名含「C086A LAYOUT AND ELECTRICAL DIAGRAM」的 226B4843 rev02（`resolve_fragment`；正式版 rev04＝HT0-1-EGK01-D0048 是掃描圖，共用）、G12 沒有向量圖、框在 G11 的圖上（類比，`extra.analog`）；GCB GE Grid VS332679EDD01D rev09（HT0-1-EGJ01-D0066，共用）；UAT Fortune 21A3D3014 rev 5（HT0-1-ETE01-D1030，共用）；LCI 中壓盤 D0037（GTG#11／21／31 共用）／D0052（#12／22／32 共用），52ET D0035（共用）——圖照盤的 KKS 選，不照路徑的機組。`wire_ep.DOC_NOTE`：卡上加註的版次狀態（DRAFT 與正式版文號、出廠圖、UAT 檔名寫錯、中壓盤只到隔間）。
  - 框：GPP＝配置圖上的端子排（引線末端那一段軌道或子盤那一排；BAY-3／AUX 的標籤沒印 (A)，照盤區補）＋端子表（TERMINAL BLOCK ARRNAGEMENT）那一號那一列，附 LOCATION（原理圖頁區）與線號；MSP＝背視圖數格子框那一號＋端子圖表那一列；GCB＝低壓箱配置圖（LVC）上印著那個號碼的端子塊（同一號幾格並接時框整組），端子表那一欄不畫；UAT＝CT 接線圖或端子圖那一格＋箱內配置圖的端子排；LCI 中壓盤／52ET 只到隔間（-A01／-A02／-A03），接線圖沒寫隔間的框整面盤。一條路徑一端一組，每頁一跳；兩端都是電氣盤的（UAT → GPP-AUX）兩端各一組。
  - 輸出：`paths[k].ep`＝[{end（jb／panel）, grp, zh, lv（term／cmp）, doc（用到的圖名）, how, pages, labs（端子或隔間）, strips（配置圖上的端子排標籤，'TBTCD (26)' 寫成「TBTCD（共 26 點）」）, multi（同一頁同一號框了幾格的）, n（這一端有端子的芯）, ok（找到的芯）, rows（[標籤, LOCATION, 線號]）, dn（版次狀態）, shared, analog, approx, whole, rel（類比＝typical、共用圖＝neutral、本台的圖＝exact）}]；hop ['epnl', 圖紙, 框, 標籤]；找不到的芯註記「接線圖把這條接到〈盤〉的端子，〈圖〉上沒有找到…」；`stats.ep_paths`、`ep_jb_paths`、`ep_panel_paths`，`scan.ep_*`。
  - `build_card_aux`：接線箱欄是電氣盤時摘要列改叫「現場 → 電氣盤」「電氣盤」「盤內端子」（Mark VIe 繼電器輸出、手動同步盤 XDI 這種盤內是受控端的，第一列寫「盤內是受控端…接點在另一端（控制盤 Mark VIe 繼電器輸出 RelayNN）」；其他寫「元件（接點）在 … 盤內」）；盤端是另一面電氣盤（不是 TCP）時「電子室盤」列改叫「終點盤」、多個隔間或端子排的照排分開寫。兩列都多「〈圖〉第 N 頁 框端子排 …；框端子 …（N 芯都找到）；…是同一號幾格並接；端子表：…；〈類比／共用／版次狀態〉」（`ge_wire_ep_txt`，全部列出不截斷）；`GE_WIRE_PANEL_RE` 多認 UAT（C?0B[BC]T10）、LCI 中壓盤（MBJ10UC）、52ET（MKC10QA）；只到隔間的圖紙列叫「電氣盤配置圖（只到隔間）」。`GE_WIRE_HOP` 多 epnl（'電氣盤端子排（設備配置圖）'）、bnw（'3500 接線表（Bently 盤圖）'）。
- **人工查證資料 `ge_tags_dir/wire_curated.json`（不進 repo；`wire_ge --curated`，沒有就不做）**：mid（中間設備）、branch（3500 並聯分支）、signal（訊號型式與供電規則）、rekey（接線圖誤印，路徑改掛到正確編號）。每條附文件、頁與等級（定讞／文字層／推論）。
- **接線圖誤印改掛（1c；rekey）**：{from, pages, to, note}——G1 p.257（G12 p.677）JB-5D TBC 15／16 那一格寫「(39VE-1R)」，GE 發電機接線圖 p.9 是 39VE-13R：那一頁的路徑搬到 GT|39VE-13R（tag、KKS 換成它的），註記跟著搬；`stats.rekeyed`。
- **中間設備（`wire_ge.py` 1b、4c；`paths[k].mid`）**：① GE 138T5502 的「接線箱端子排」欄寫的是箱內的中間設備（`DEV_TB_RE`：'96KP-n CHARGE AMP'、'RAIL MOUNTED PROXIMIT'、'TB PROX_<tag>'），探頭落在設備的進線端（電荷放大器 5／8）、接線圖的 JB 端子格是出線端（09／12）——端子號接不上，改以「接線箱＋這個編號」接到這一台唯一的那條路徑，現場那一跳照 GE 表列（38 條：96KP-1～12、39VS-11／12／21／22、77RP-11、96VC-11／12，兩台）；② `wire_curated.json` 的 mid：每個編號一串 [{at（jb＝在這個接線箱裡／field＝先進另一個箱子／self＝這個編號本身在箱裡／pre＝上游還有沒有 GE 編號的感測器）, n, s, i（進線端）, o（出線端）, g, src}]、gap（沒有圖的那一段）、one（'coax' 同軸延長線／'fiber' 光纖：現場到中間設備只有一條線）、ns（屏蔽不從元件拉：同軸、盤內接地、GE 段與幹線兩段不連）、notes——96KP 電荷放大器（PCB EX682M85）、乾燥器的安全柵＋Lectrodryer PLC（GE 的 MIC-2996 就是 PLC 這一段【推論】）、燃機發電機的 JB-164／JB-163／JB-5A（GE 發電機接線圖 107T0000 p.2、p.4、p.5、p.7；39VS-91～102 的前置器在 JB-164／163 裡、直出到 JB-5C）、JB87 的 DVP 數位閥定位器（CAN 匯流排歸屬 135T4640 與 D1004 不一致、照列）、JB1T／JB2T 的前置器（料號取燃機 EOMR BOM）、JB-5D 的光電轉換模組、96CT-IF-nR 上游的四線 RTD。迴路圖：箱內的設備把接線箱框往左延伸框住它（訊號芯經過、屏蔽芯繞過）、另一個箱子畫在現場區（它到接線箱那一段是 GE 範圍電纜、一號機接線圖沒畫，畫灰線）、DVP 把箱框延伸過來框住元件、同軸畫粗線、光纖畫點線；框下寫說明與進、出線端，左上寫沒有圖的部分。卡上摘要表多「中間設備」列（照訊號路徑排：上游感測器在最前、其餘接在「現場 → …」之後）。
- **3500 並聯分支（4b；`paths[k].bx`）**：Mark VIe TVBA 先收到訊號、3500 收 TVBA 的緩衝輸出（JA1／JB1／JC1／JD1 → ET 排線 → ETB 或直插 3500 模組）；1TBVIB 速度型只有 3500 收；SEDP 是另一塊 SHRA 卡轉送的 4–20 mA → 3500/62。bx＝{kind, lab（燃機照機組寫 RACK 與控制器）, conn, mod, rack, slot, ch, alt（另一種讀法的位置）, aw（'pr'＝汽機 Bently 標示與 Mark VIe 通道順序不一致、'legacy'＝燃機盤圖 Legacy Tag 欄與 RDS-PP 欄順序不同）, g, cf, via（'經 ETB 2 CH2'／SHRA 來源）, panel（3500 盤）, cite}；燃機的機架槽位這一版才有（GT-VMP Rev D 的 RDS-PP 欄＝Mark VIe 通道；G11→RACK 1、G12→RACK 2），`paths[k].rack` 多 `by: 'bx'`、沒有 rack 那一跳；新的一跳 bnw＝3500 接線表那一頁（汽機 Bently 120V8111 p.22～30，燃機 EOMR HT1-1-AQB01-Q1850 p.52／53，只框 G11 的 RACK 1；G12 的出處寫 p.54～55、p.42）；'RP-1 (Jumpered)' 是送 GHM 櫃的鍵相，不進 3500，拿掉照標籤掛上的 RACK 1 SLOT 5 並註記。分支的警語人工註記沒講過的才加（G12 卡寫 G12S）。迴路圖：Mark VIe 框下面一條線（「緩衝輸出 JA1」／「另一塊 SHRA 卡轉送 4–20 mA」）接一個四行的 3500 框（RACK／SLOT／CH；盤與模組；經過的 ETB 或 SHRA 來源；推論說明或紅字的另一種讀法）；1TBVIB 的終點框寫 3500 槽位。卡上摘要表多「3500 分支」列（燃機另列 Legacy 欄讀法），燃機的「Bently 3500」列寫 RDS-PP 欄；3500 盤圖的出處帶資料夾（汽機與燃機兩份同名檔）。
- **訊號型式與迴路供電（2b；`tools/db/wire_sig.py`；`paths[k].sig`）**：每個 Mark VIe 點 → 接到的螺絲名（'P24V3'、'20mA3'、'N24V02'、'SOL5'…）＋控制器組態的 signal_type／input_type／params_json → `wire_curated.json` signal.rules 第一條符合的規則（42 條，引用 Mark VIe 端子板手冊或盤內配電圖）→ [點, 訊號, 供電, 等級, 旗標, 衝突, 出處, 備註]。判定以接線為準（P24V＋20mA＝兩線式、20mA＋Ret＝四線式或外部供電、NO＋SOL＝板供電輸出、COM＋NO／NC＝乾接點、N24V＝TVBA 供前置器…）；板供電輸出接的是電磁閥還是對方盤的啟停命令迴路，照接線圖的設備描述與 GE 編號判（`load_of`，推論）。ToolboxST 的跳線、選項欄位（TBAI JPnA／JPnB、WROB JPn、TCDM JPxx、TVBA JPxA）與接線不一致的另列一則註記（一條路徑一則），寫「組態欄位與此不符，請以現場跳線為準」、不替任何一方選邊（燃機寫 G11 記 Dry、G12 多記 Excited；汽機寫 S1 全記 Dry）。「只對到一芯」那幾條不說另一芯不存在，寫「接線圖上沒有對上螺絲名（可能是標籤筆誤）」；熱電偶組態 Unused 的點不印「Unused 型」。汽機六個 WROB 位置的饋電只寫圖例的條件（只適用 259G9083G01 版），不寫成交流電壓的事實；FF 段電源的 FFPC↔PFFB 對應標推論；TTUR 斷路器接點寫成 52G(L) 輔助接點電壓感測。主要訊號排前面（看規則代號：*_ONLY、TC_PARTIAL、TDBT_DI_RET／POS、AI_BORROW_PWR 排後面——`wire_sig.PARTIAL_RULES`；不看句子，句子改過措辭也不會亂）。卡上摘要表多「訊號與供電」列（最多 4 個點，多個點時列名帶點名，規則備註接在後面），迴路圖 Mark VIe 欄下方寫「【等級】訊號：…」「供電：…」（等級在最前面，截斷不會截掉）。
- **迴路圖編號與標題欄**：`ge_wire_cards` 依機組編 'LP-<機組>-<GE 編號>'（同一台好幾條加 -P 序號；GE 編號照寫，不改標點）→ `d.no`，好幾條時 `d.nn`＝這一台共幾條；`d.wd`＝依據的接線圖文件號＋版次。迴路圖底部多一列標題欄：迴路圖編號（本站自編；有 -P 時寫「（共 N 條）」）｜元件／KKS／機組｜依據的接線圖（文件號 Rev. p.N Sheet）｜產生日期與「程式整理・本圖未經簽核」。
- **迴路圖其他改動（第五輪查核後）**：圖例四行（線型、框型、✓≈✗ 與證據標記【定讞】【文字層】【推論】【組態】、「本圖由程式整理、不是簽核過的竣工圖、截斷的全文見網頁卡片」）；第四欄終點不是控制盤 TCP（另一面電氣盤、GHM 櫃、VMS 盤）時叫「終點盤 PANEL」（`d.po`）；電氣盤是受控端時第二欄寫接點在另一端（`d.jr`）；FF 段保護器內部畫成＋、−、屏蔽各一條（不畫成一條匯流排），同一段的其他元件寫在位置欄（`d.fsm`）；Mark VIe 框 FF 段寫「組態沒有螺絲點，以段變數對應」；出處同一份圖的頁碼併成一筆；接線圖說明重複的去掉；端子格自己帶端子排的（'TB2 27'、"-TBTCD '01"）不再加表頭的端子排名（`d.jt` 空；"-TBTCD '01" 寫成 'TBTCD 01'）；字寬把箭頭與數學符號算全形。
- **對照表（hst-docsearch，不在本 repo）**：`build_ge_tags.py` 去掉 VE45 互連清單元件欄的 IEC 前綴「-」（'-REDP-1A' → 'REDP-1A'，原寫法留在其他寫法），更正檔加 ST|REDP-1A／1B（conflict、note_only：VE45 寫 MAD60BG011／012，是它第 4、5 號軸承整組錯一號，同 VP-5X）。對照表 3,956 → 3,954 筆；`wire_ge` 的 '-REDP' 人工註記備援拿掉。
- **其他**：`wire_notes.json` 的鍵可以加 '@p<頁>'（只掛接線圖那一頁的路徑）；人工註記 16 → 21 則（GCB XT100 30／31 是線圈監視、未結事項 2025041406／12；GCB XT81 VT3 現場改線 2025041407／13；GCB XT01 87 兩格並接、2025041402／08；手動同步盤 52L2／52L3 CLOSE 是一條 7 芯電纜帶兩個迴路、TB2 30 用兩次、組態變數名與 DeviceTag 交叉；G12 MSP-DO-52L1PERM 實為 52L3；UAT 96P 接在故障指示器 30-11 的備用接點、表頭 TB06 抄錯、'TB 29' 筆誤；汽機 GPP 9 條的盤名寫 MAIN、端子排是 AUX 的 TBTCD(A)；83LBS／83LBSX 同一列；T60-TL 那一芯是 +VDC 共用線；燃機 39VS-11／12／21／22、96VC-12 的 COM／OUT 落 PRxxH／L 與同頁其他探頭相反；96CT-IF-1R／2R／3R 兩份文件的 KKS 錯一號；3500 通道衝突的三則補「最新版 Rev C 同表未改」）；`wire_ge.io_rel` 先比 DeviceTag 是不是另一個 GE 編號、再看變數名（DeviceTag 有空白的整串也比）；`term_parts` 認 '-XT07-21'；`rebuild.py` 的說明改耗時。
- **測試**：`test_getag.py` 多 3 項：第一條路徑帶 epnl 的 250 個以上，14HRI 的「電氣盤」列有 TBTCD(A) 25、線號 4898、「各台共用」，41E-1 有「G11 手動同步盤」與 XDI 13，49GCB 有 -XT100 30 與 2025041406、-B.K14 的註記；96KP-1 的 d.md 是電荷放大器、GE 接線表 2 列以上、多 conn 一跳、中間設備列有 EX682M85，VP-1X 的 d.bx 是 tvba_vib RACK 1 SLOT 8 CH2、「3500 分支」列有 JA1，39V-1A（燃機）有 RACK 1 SLOT 13，RP-1 (Jumpered) 沒有 3500 列；第一條路徑帶 d.sg 的 1,100 個以上、96CD-2A 是兩線式，VP-1X、96CD-2A 的迴路圖編號 LP-S10-VP-1X／LP-G11-96CD-2A、依據的接線圖 'HT1-1-ICE01-D1004 Rev.'，對照表沒有 '-REDP-1A'。VP-1X 的迴路圖字多檢 LP-S10-VP-1X、'Bently 3500 RACK 1 SLOT 8 CH2'、'供電：'、'迴路圖編號'。v14／v15 檢查電氣盤的那兩項（52GT-1 的 GPP、23HG-1 的 MCC 格）改看「電氣盤」列。
- **數量（2026-10-28 建置）**：GE 編號 1,328 個有路徑（3,954 筆對照表；-REDP 兩筆併掉、39VE-13R 多一筆）、2,204 條路徑（G11 800、G12 791、S10 613）、圖紙 1,089 張、註記 868 則；epnl 471 條（接線箱端 399：燃機 GPP 136、汽機 GPP 55、手動同步盤 104、GCB 62、UAT 14、中壓盤／52ET 28；盤端 138），1,264 芯全部找到；GE 接線表接在設備進線端的 38 條；mid 126 條；bx 87 條（TVBA 緩衝輸出 70、1TBVIB 速度型 14、SHRA 2、GHM 1），3500 槽位 86 條（汽機 48、燃機 38），兩種讀法 26 條；sig 1,815 條、1,952 個點（組態 36、文字層 1,178、文字層／推論 156、推論 582），跳線欄位不一致註記 184 條；rekeyed 2；wire_ge 約 50 秒（電氣盤配置圖索引約 22 秒）；e2e 8 模組 516 項全過（test_getag 133），約 148 秒
- **已知限制**：DC 啟動盤、EBOP／ESOP 啟動盤是掃描圖，框不了；EX2100e、LCI 盤（文字層偏移或只有舊版）、GSUT、6.9 kV 開關盤、CCR 操作台沒有框；G12 手動同步盤是類比（G12 正式圖 D0072 是掃描圖）、G11 的向量圖是 DRAFT、S10 是 rev02 向量（正式版 rev04 是掃描圖、來源框有改）；GCB、GPP、UAT、LCI 中壓盤、52ET 的圖是各台共用的設計圖或出廠圖，不是本台竣工；接頭第 n 通道＝ETB／3500 第 n 通道是推論（ET 排線腳位沒有圖），汽機 16 列 Bently 標示與 Mark VIe 通道順序不一致、燃機 Legacy 欄與 RDS-PP 欄順序不同，兩種讀法都列；中間設備是人工查證的清單（中間 JB 的電纜號、廠商盒內配線多半沒有圖）；訊號型式與供電是照接線與手冊判，跳線實際位置要現場看；燃機 UAT 那類「X TO T60AT-B」的路徑，迴路圖的現場圓圈仍寫接收端的編號（T60AT-B 是 GPP-AUX 裡的電驛，說明在「接線圖說明」）；電氣盤配置圖索引每次重建約 22 秒（沒有快取）。

## v17（docs/db 站：只有 KKS 的元件也有接線路徑——HRSG、電氣 I&C、BOP 接線圖與燃機／汽機圖上沒有 GE 編號的框；AMS 設備卡的「接線路徑」組與 KKS 編號卡；`tools/db/wire_epc.py`、`tools/db/wire_kks.py`、`wire_ge.py` 的 kks 模式、`build_card_aux.py` 的 `kks_wire_build`、card.js `renderKksOnly`／`fillWireGroup`、core.js `AMS.kkstag`／`D.loadWire`）

使用者 2026-10-29（「除了GE編號的，其它已經有KKS的也一併和GE編號的一樣處理」）：v13～v16 只做 GE 編號；這一版把同一套接線路徑、迴路圖、盤端子核對、訊號與供電、位置圖、P&ID／圖控位置給「只有 KKS」的元件。**GE 編號卡的資料不動**（`wire_ge.json` 與 v16 逐位元組相同；每次改完都比對過），**AMS 設備卡的 aux 分塊不動**（`aux-NN`、`getag*` 加密檔重建後沒有變）；接線路徑另成 `card/wire-NN.json`（與 aux 同一個分塊編號）與 `card/kkstag*.json`。

- **範圍**：一號機 HRSG 儀控電纜接線圖 HT1-1-ICE01-D1001（289 頁）、電氣 I&C D1002、BOP-WSC D1003（975 頁），加上燃機 D1004／汽機 D1005 上說明格沒有 GE 編號、只寫 KKS 的框；D1006（網路）不做。電纜表 HT1-1-ILE01-A1001（HRSG）／A1002（電氣 I&C）／A1003（BOP）；位置圖 HT1-1-IIF01-D0001～D0006、D0008（沒有 D0007）；控制器索引 H11、H12、BOPE1、BOPM1A、BOPM1B、WSC1、SAMP1、AGC1（一號機 checkout 沒有 BOPCM1、BOPCM5、DWTC2，那幾面盤的端子不核對、卡上寫明）。
- **產生器**：`wire_kks.py` 只是入口（`a.kks=True` 呼叫 `wire_ge.build`，寫 `cardwork/wire_kks.json`，kind 'wire_kks'；人工註記讀 `ge_tags_dir/wire_notes_kks.json`，沒有就不帶；`wire_curated.json` 兩版共用）。`wire_ge.build` 的 kks 模式：鍵 'KKS|<設備 KKS 13 碼>'（`kks_ent` 補條目）；燃機／汽機圖上說明格認得 GE 編號、或盤端子反查得到 GE 編號的框不收（那是 GE 卡的）；1b（GE 接線表）、1c（rekey）不做；`other_keys` 改成「DeviceTag 是另一個設備的 KKS」；I/O 核對多兩種關係（見下）；位置圖、電纜表、MCC 格另走 EPC 版。
- **頁面解析（`wire_epc.py`；呼叫同一個 `wire_ge.parse_page`，`use_layout` 暫時換欄帶、標頭規則與配對函式）**：
  - 欄帶由這一頁芯色標籤的 x 群推出（x ≥ 590 第一欄＝盤側；它左邊 x ≥ 470 最右一欄＝JB 出線；420～出線欄＝JB 入線；x < 420 最右一欄＝現場）；端子格左緣有向量框線時取那一欄的直線（說明格的 'Open'、'Cmd' 會寫到端子格旁邊）；圖區下界＝最低芯色＋45 pt。
  - 配對：芯色標籤在格子上緣、端子號在格子中間——格子先上移「標籤 → 下一個端子號」距離的中位數再配（`order_match_epc`）；兩端標籤配對（`lcs_pair_epc`）先配兩端各自唯一的標籤（芯在圖上可以交叉），剩下的照配好的那幾對分段各段 LCS＋夾縫補配（盤側把 WH-1 印成 WH-2 時照順序配、記標籤筆誤）；整排標籤一致地差一個號（D1003 p.732 盤側 BK-11、WH-11、BK-12、WH-12）照順序配；盤側沒畫屏蔽芯時 JB 側的 SH 不參加配對；盤側那一段完全沒有芯色標籤（p.727）時，同一條幹線沒配到的芯與沒有標籤的盤端子格數量相同就照順序配（旗標 panel_nolabel）。
  - 芯色正規化：'Bk-3' → BK-3；芯色欄裡的 'B-8' → BK-8；端子格照一般規則併行（'PL3'＋'1'、'TB-0'＋'37' 是同一格）；元件框標頭那一行的字不當現場端子。
  - 元件身分（`row_signals`）：每個訊號格寫一個訊號 KKS（設備 13 碼＋'XB01'／'XG02'／'XQ01'，同一碼分 A～D 的 'XB11A'；與說明黏在一起的 '=G11HSD10QM001XB61NH3' 也認），向量框線切出訊號格，芯歸同一格的訊號字（MCC 頁訊號字在格子上緣）；格子沒有訊號字才取 y 最近的；沒有現場那一側、盤端子寫 SPARE 的備用芯不歸任何設備。標頭照訊號格各自算（每一格取它上面最近的一行 'KKS:說明'；括號裡的 KKS 不算標頭）。有現場電纜的頁，群組照現場芯色序列切（每條電纜從 BK-1 編起，標籤重複、號碼變小或芯色家族換了就是下一條；`cable_runs`）——wire_ge 以電纜號 y 中點分群，8P 電纜的號碼寫在 16 條芯中間，上一條 1P 的群會吃掉它最上面幾條芯。
  - 標頭：'MCC/SWGR NO.: =G11BFB30_A1_A1E'、'Junction Box No:'、'PANEL :' 都認，去掉 '=' 與 '-' 字頭；MCC 頁的 'G11HSD12CQ101:SCR Dilution Air Blower 1' 是元件框標頭、不是 MCC 說明（MCC 說明取電纜表）；盤欄沒有 'PANEL:' 的取說明開頭的 KKS（液位遠端顯示器 G11HAD60CM025）。
  - 溫度兩段頁（D1003 98 頁）：上段「FIELD (TEMPERATURE ELEMENT) → TEMPERATURE TRANSMITTER」＝熱電偶 → TC 補償導線 → 傳送器輸入端子，下段「TEMPERATURE TRANSMITTER → JUNCTION BOX → DCDAS PANEL」＝傳送器 4–20 mA → 接線箱 → 盤：下段標題列以下照一般頁解析，上段另抽成 `p['sensors']`（`sensor_units`：熱電偶 KKS／說明、補償導線與規格、傳送器 KKS／說明、[芯色, 熱電偶端子, 傳送器端子]），依設備 KKS 掛到下段的路徑（同一頁只有一組而兩段寫的 KKS 不同時照位置配並註記，路徑同時列在上段那個 KKS 底下）。
- **控制器 I/O（`wire_epc.io_index`／`assign_cab`）**：盤端子格只寫 'CA002 -2D1B' 與螺絲號、沒有板名，索引的櫃是 'LU001'（兩櫃並列一組）或 'CA015'——每個（盤 KKS, 圖上 CA 號）以 DeviceTag 投票定到索引的（控制器, 櫃），板名照索引補。KKS 版的 `io_rel`：DeviceTag 或變數裡有這個設備的完整 KKS → same（DeviceTag）／logic（只在變數，DeviceTag 寫母設備：G11MST10EW005XB01）；只差機組碼（BOP 控制器同時管 G11／G12／S10 的同名設備）→ unit（✗，註記「另一台機組的同一種設備」；「這個編號的點在…」也不再列別台的點）；同一片板上同一個 DeviceTag 的其他點不加（KKS 的 DeviceTag 是設備層，別的點多半畫在別頁）。
- **電纜表（`wire_epc.cable_schedule`）**：一列一條電纜、欄序固定；列的範圍以上下兩條電纜號的中點切（格子垂直置中，三行的房間說明第一行在電纜號那一行上面）；欄照這一列的房間碼、設備碼、型式切，房間 2 代碼空白時用同一頁其他列的房間 2 欄位置；分段標題列（'Instrument/Valves to DCS Cables'）不屬於任何一列；房間碼 '10UTG10R001*'、設備 'G12BGA10-1B(Rear)'、長度 '47 + 280'（紅字追加）整串保留、型式收到外徑欄之前（'01P-16 AWG TC TYPE E'）；路由欄不收（多行、紅字刪改、跨列，讀不準）。比對：接線圖的接線箱／MCC 格與電纜表這條幹線那一端不同（分隔字元不計；一邊只寫排算沒有可比；'G12BKB30_A9_A2D' 只比格位 A2D——A9 是盤面配置圖那一格裡寫的單元標籤）→ 註記；元件自己的電纜在電纜表上的另一端不是接線圖畫的那一端 → 註記（兩份文件不一致，不替任何一方選）；溫度上段的補償導線也查電纜表。
- **位置圖（`wire_epc.loc_labels`）**：KKS 字下一行是廠區座標的就是位置標籤（接線箱、儀表架 GZ）；儀器本身多半只列在同一張圖的儀器清單表（INSTRUMENT RACK／TAG 兩欄，儀表架是合併格）——有向量橫線時照格線切合併格，儀器取同一格的儀表架（D0001 p.3 C10LAB42BP001 → C10LAB42GZ002），沒有才取 y 最近；hop devloc／devlist，卡上「元件位置」列在最前。別台機組的設備接在這個接線箱（G12QJE11BW001 → G11QJE10UC151）的位置照箱子的 KKS 找。
- **MCC 格（3d）**：EPC 圖的格位寫成「排_欄_格」（`MCC_EPC_RE`：'G11BFB30_A1_A1E'），框在 GE EP24 盤面配置圖那一格，比對同 v15。
- **路徑欄位（`wire_kks.json` paths[k] 比 GE 多的）**：cond[].sig（訊號 KKS）、dsc（元件說明：標頭 KKS 後面的字，沒有就用第一個訊號格的說明）、ctl（盤端子所屬的控制器；燃機／汽機圖上的取核對到的點）、wire.field_cables（一個設備的訊號分走幾條現場電纜）、wire.trunks（也分走幾條幹線）、wire.sensor（溫度上段，含 cs）、devloc／jbloc 的 kind；drawn 只收這幾條芯所在的訊號格（加它們上面的標頭行）。
- **P&ID／圖控位置（KKS 編號卡）**：`pid_index.py --tags-file wire_kks.json --out pid_kks.json`、`hmi_index.py --tags-file … --out hmi_kks.json`（位號清單改成 wire_kks 的 KKS；AMS 現行位號另有自己的索引），`pid_shots.py --wire-kks --pid-kks` 一併出圖；`rebuild.py` 的 `run_pid_ge` 依序跑 wire_kks → pid_index → hmi_index → pid_shots。
- **`build_card_aux`**：`kks_wire_build` → AMS 設備卡（KKS 就是 AMS 位號的）的接線路徑塊 `card/wire-NN.json`（by_alias，分塊同 aux-NN；本身是 GE 元件的 AMS 設備，塊裡帶 GE 卡的路徑與 ge 鍵）、KKS 編號卡 `card/kkstag.json`（條目：KKS、說明、機組、文件）＋`kkstag-loc-NN.json`（每檔 300 條：接線路徑、P&ID、圖控）；`index.wire`、`index.kkstag`。`ge_wire_card(kks=True)`：盤 KKS 認 C 開頭、迴路圖不重印 KKS、「元件位置」列、溫度上段「熱電偶 → 傳送器」列（下一列改叫「傳送器 → 接線箱／盤」）、幹線與現場電纜不只一條時全列、盤的控制器不在索引時寫明、迴路圖編號 'LP-<KKS>[-Pn]'。`extract_db` 摘要多「接線路徑」組（在全文檢索之前）。
- **訊號與供電（`wire_sig.py`、`wire_curated.json`）**：`params_eq` 的鍵可寫 'JP{n}B'（這個點的跳線）；新規則 AI_4W_OPEN（SHRA／TBAI 四線式、JPnB=Open：回線不接 PCOM）排在 AI_4W 之前——原本的句子寫「回線 Ret 經 JPnB=Open 接 PCOM」與手冊相反（GE 卡沒有 Open 的點，句子不變）。
- **前端**：core.js `AMS.kkstag`（載入、訊號 KKS 去尾碼、建議、分檔載入）、`D.loadWire`；card.js 查詢先看 KKS 編號卡（整串命中或「開頭相符、不是 AMS 鍵」的候選會擋掉位號索引的模糊對應：打一半的 G11LAE12QM0 不會悄悄開舊位號 G11LAE12）、`renderKksOnly`（標頭、P&ID、圖控、接線路徑三組；查無寫明）、`fillWireGroup`（AMS 卡摘要的「接線路徑」組；GE 元件註明另有 GE 卡）、查無頁 `.nf-kks` 候選；app.js 頂列 Enter 同一套判斷。`GE_WIRE_IO`／`GE_WIRE_MARK` 多 unit（✗）。
- **測試**：`test_kks.py` 27 項：儀表架標高 'D'（C10LCM11BT001 'E 4359570 N 4093841 D 2102'）、A1002 'G11MST10 LCC' 之後的房間欄 101UBA20R001、PDF 沒有而 xlsx rev 1 有的電纜（G11EKT50BF001 的 C10PBH00UC151-WG-300）、MCC 排名不同（C10LCC20GP001 C10BAC30_15_1 ↔ C10BCA30_6_1）；以及index.wire／kkstag 數量、G11LAE12QM004（KKS 編號卡，直拉到 H11 RIO、8 芯以上 ✓、電纜表、迴路圖編號）、G12HAP70BT001（AMS 卡的接線路徑組、CA007-1A5B 29／30 ✓、迴路圖字）、GE 元件的 AMS 設備帶 GE 路徑、溫度兩段頁 C00LBG30BT401 的「熱電偶 → 傳送器」列、p.916 上下段 KKS 不一致（路徑在 C00LBG40BT411、註記寫明下段寫的 C00LBG30BT411，後者仍開得到自己 p.912 的路徑）、MCC 格 G11BFB30_A1_A1E 框出 A1E 且沒有「NO.:」、G12QJE11BW001 的 G11 接線箱位置、p.727 盤側沒畫標籤的兩芯 ✓、KKS 卡的 P&ID 與圖控、摘要組順序、沒有路徑的 AMS 設備不出這一組、設備／訊號／小寫三種寫法、頂列 Enter、打一半的候選、console 零錯誤、手機不橫捲。
- **數量（2026-10-29 建置）**：只有 KKS 的元件 2,912 個、3,334 條路徑（BOP 2,243、HRSG 809、電氣 I&C 235、汽機圖 43、燃機圖 4；機組 C10 1,206、G11 882、G12 879、C00 202、S10 119、C20／C30／G10／Q00 46；畫法 jbdev 1,636、tb 1,308、direct 390）；AMS 設備卡的接線路徑塊 1,259 台（KKS 路徑 1,141 台；其餘是 GE 元件帶 GE 路徑）、71 個檔約 21 MB，KKS 編號卡 1,772 個（P&ID 位置 1,101、圖控位置 1,114，79 個畫面），loc 6 個檔約 33 MB。盤端子核對 11,275 芯：same 10,407、logic 42、loc 8、alias 10、other 90、spare 104、組態沒有（多半是控制器不在索引）614；控制器 H11／H12 各 626、SAMP1 590、WSC1 327、BOPM1A 305、BOPM1B 301、BOPE1 232、S1 42、AGC1 22、沒有（BOPCM1／BOPCM5／DWTC2 等）262 條。電纜表 3,250 條路徑、接線箱位置 1,102、元件位置 267、MCC 格 84、溫度上段 235、分走幾條現場電纜 85、幾條幹線 20；註記 595 則（PDF 較舊、xlsx rev 1 才有的 57 則；電纜表那一列讀不到的 1 則）（控制器不在索引 185、跳線欄位 94、組態的點在別處 47、電纜表查無 32、備用點 31、組態掛別的設備 28、訊號編號不同 27、標籤筆誤 19、電纜號前綴 15、溫度上下段不一致 15、同一顆螺絲兩芯 9、MCC 中間段 9、電纜表兩端 8、盤標頭 vs 盤框 8…）；圖面一頁上帶訊號尾碼、編號慣例不同（圖 XB31 ↔ 組態 XB01 這類，出現在 3 個以上設備）的不註記。圖紙（含 P&ID）1,539 張，新增的接線圖影像約 45 MB；wire_kks 約 2 分鐘，加 pid_index／hmi_index --tags-file 與出圖，整個重建約 25 分鐘。GE 的 wire_ge.json 與 v16 逐位元組相同。
- **第二輪看圖查核後補的（`wire_epc`）**：一頁好幾個接線箱／端子排／盤框——`header_cands` 收整頁的標頭（'TERMINAL NO.: GT11 PB1'／'PB2'；標頭與值分在兩欄的 LCS 頁）、`panel_boxes` 以框線切盤框（p.787 上下兩框 G12CCH02UC201／G11CCH02UC201），wire_ge 每條路徑取第一條芯上面最近的那一組、盤端子所在的那一框（只有一框而標頭與框裡寫的不同時，盤取框裡的、註記兩者）；幹線照 JB 出線芯色序列切（`trunk_runs`）、電纜號可帶尾字母（'-WG-002A'）；帶訊號尾碼的盤／箱 KKS（'G11MSA30UC101DXG01'、AGC 的 'C10AAF10UC101XQ01'）也是訊號來源，行首只有設備 KKS 的是標頭或圖說（'G11MAN30QN001 - JB'）；框標頭與現場電纜號都寫另一個設備時路徑照它們（p.20，註記訊號格寫的）；溫度兩段頁的下段左邊也可能是 'TRANSMITTER'、'FIELD(MOV/…)'，沒有標題列的以最後一條補償導線下面的 'Junction Box No:'／'PANEL:' 為界；上段熱電偶與傳送器框寫同一個 KKS、下段寫別的時——下段那個 KKS 另有自己的路徑而電纜號也寫上段的，路徑搬到上段的 KKS（p.916／917）；否則兩個編號都列；上段傳送器框自己寫錯的（p.671、p.698）只註記。同一顆盤端子畫給兩條芯 → 註記；電纜表型式寫在第二行、'G11MST10 LCC' 的設備欄、'11UHA02' 的房間碼、'HRSG 12 I&C Cable List' 分段列；位置標籤只取跨過 KKS 的那一段座標（右邊緊鄰的標籤不收）。`wire_ge`（kks）：一頁的旗標只留這條路徑的芯；盤欄位只取盤 KKS；組態的點在哪裡那則只列這幾條芯的訊號（變數名帶 KKS 的控制器）；設備說明取各訊號格共同的開頭；MCC 格位相同、中間那一段不同的另列一則（只列出）。
- **看圖查核**：第一輪 6 組 147 條路徑（每頁渲染對照）；第二輪 6 組 211 條（第一輪有實質問題的 96 條逐項複核＋這一版改動的各類抽樣：當時第一輪的問題 168 項已修、60 項仍錯，之後再修，見報告 §4）。報告「KKS元件接線路徑_一號機_2026-10-29.md」與核對紀錄資料夾在文件庫 claude/。
- **已知限制**：燃機／汽機圖上只有 KKS 的框（47 條）只做到 v16 的程度：汽機的訊號格 'MAL40QM001-BG01'、'MAX31GP004_AVAIL' 照 y 最近認，TDBT 的 TB1／TB2、雙元件熱電偶第二支、汽機的溫度兩段頁（D1005 p.404）沒有處理，A1005 電纜表被裁切的列（S10LBH30QN001-WG-001）讀不到、d1d／d2d 空；分走兩條電纜的設備，第二條電纜的電纜表那一列不列、每條芯不寫是哪一條電纜；JB 出線標籤夾在兩個端子之間的頁（D1003 p.856）那幾條芯丟掉；UAT 頁 D1002 p.144／150 欄位認錯；以 ISA 位號（'1-CSC-CW011-1'）寫的訊號（D1003 p.329 冷卻水）沒有 KKS、不建卡；控制器索引沒有 BOPCM1、BOPCM5、DWTC2，那幾面盤不核對；盤標頭寫在別的欄位、名稱前綴（'BOPE1_CNTRL/'）只取 KKS；6.9 kV 開關盤只到盤名、沒有框隔間；A1003 的 PDF 是 rev 0（xlsx rev 1 較新、長度不同；卡上照 PDF，PDF 上沒有的電纜才註記 xlsx 那一列）；位置圖上 9 個接線箱沒有位置圖；第三輪報告查核列的未修項（燃機 CCR 緊急停機 SG002 的 PB1／PB2 與 'CA004-ESTOP-TB1'、VMS 盤 'TB1 nn'、C00MSP10KC100 接線箱欄空白、p.846 兩條幹線同名 WH-4、溫度上段 240 條補償導線有 6 條沒接上下段、p.289 重複頁的房間塊、D1002 p.200 只寫排的 MCC）照現狀；註記只列出文件之間的不一致，不替任何一方選邊。

- **第三輪報告查核後補的（2026-10-29；5 個查核代理把報告 74 項主張逐項開圖或重算）**：
  - 位置標籤讀到標高為止——'U nnn' 或 'D nnn'（D0004 p.3 儀表架寫 'D 1501'；`LOC_COORD_RE`），左對齊的讀法（`loc_label_left`）也截，不收右邊緊鄰儀表架的 E／N。
  - 電纜表設備欄併 'LCC'／'HVN' 之後才取房間欄位置（先取會錯一個字：A1002 p.10 房間 2 讀成 'U1'）。
  - `wire_epc.cable_xlsx`：A1003 另有 xlsx（`HT1-1-ILE01-A1003*.xlsx`，在文件庫第二層資料夾；取版次最高的，表頭列有 'Cable No.'，版次與日期在表頭上面）——接線圖的電纜號不在電纜表 PDF 上、但在 xlsx 的，註記「PDF 版次較舊、xlsx 第 N 列兩端／型式／長度」，不再寫「兩份文件不一致」；卡上的房間塊仍只照 PDF。沒有 openpyxl 時不讀。
  - `wire_epc.cs_text_page`：解析出的列裡沒有、但電纜表文字層有這個電纜號（表上分成 'S10LBH30QN001 WG 001' 幾格）——註記「那一列讀不到（例如頁底被裁切）」（只在 kks 模式，GE 的句子不變）。
  - 幹線兩端核對：接線圖寫的 MCC 格（'排_格'）與幹線電纜號的排不同、電纜表那一端是幹線那一排的格（D1003 p.577 'C10BAC30_15_1' ↔ 'C10BCA30-WG-301'／'C10BCA30_6_1'）也比對並註記；只限 EPC 圖、MCC 格的寫法（接線箱 KKS 'C00EKB10UC101' 不算）。
  - `build_card_aux`：現場電纜帶規格時 GE 原句不留空格（「（3C-14 AWG）直拉到盤」、「（…）→ 接線箱端子排」），沒有規格的 KKS 電纜才補空格。

## 加密與封裝（tools/encrypt_data.py；兩站共用）

GitHub Pages 是公開靜態站，`docs/*/data` 一律以**密文**發布，只有 `data/meta.json` 是明文；瀏覽器在員工代號登入後再輸入**密語**解密（與 momobacon-wq/signal-atlas 同一套作法）。

- 金鑰：`PBKDF2-HMAC-SHA256(密語, salt, 200000)` → 32 bytes（AES-256-GCM）。密語只存建置機器 `%LOCALAPPDATA%\AMS\web.key` 第 1 行（或環境變數 `AMS_WEB_KEY`／`AMS_WEB_KEY_FILE`），**永不進 repo**。
- salt（16 bytes）存 key 檔第 2 行，**固定不隨建置改變**（salt 本來就公開在 meta.json；固定後「記住此裝置」的金鑰在資料重建後仍可用，且 docs/ 與 docs/db/ 同源共用同一把）。`--fresh-salt` 或改密語＝輪替，兩站都要重新加密（那一次全部重封；輪替的 commit 進去之前不能原地重建，見下面「這次的金鑰不是已發布的那一把」）。
- 每個資料檔（`manifest.json`、`sheets/*.json`、`card/**/*.json`——含 `card/hmi/`、`card/pid/` 的影像檔；`encrypt_data.py` 以 `rglob("*.json")` 收，`meta.json` 除外）存成 `<rel>.bin` ＝ `12-byte 隨機 IV ‖ AES-GCM(gzip(JSON UTF-8, level 6, mtime 0))`（含 16-byte tag，WebCrypto 版面），**AAD＝相對路徑 rel（不含 .bin）**，密文不能搬到別的路徑。**IV 只在「重封」時才重新抽**：2026-10-08 起，明文沒變的檔沿用 git HEAD 上那一份密文（連 IV 一起，見下面「沿用沒變的密文」），所以「每次建置每個檔的密文都不同、每次 commit 都帶全部 `.bin`」已經不成立；同一組（金鑰、IV）仍然不會拿去封第二份明文——內容一變就重新抽 IV。
- `meta.json` ＝ `{"enc":1,"gzip":1,"build":<manifest.build>,"kdf":{"name":"PBKDF2","hash":"SHA-256","iter":200000,"salt":<b64>},"check":<b64 seal(key,"ams-ok",aad="check")>}`；`check` 只用來驗密語；git HEAD 的 `meta.json` 的 `kdf` 與這次相同、`check` 用這把金鑰打得開時沿用原字串（內容沒變的站重新加密後 `meta.json` 逐位元組相同）。
- `manifest.build` 仍以**明文**內容計算（重封的檔 IV 隨機，密文不可拿來算 hash；一個檔是沿用還是重封都不影響 build）：產生器先算 build 寫 manifest → `encrypt_dir` → stamp。`tools/stamp_assets.py`／`extract_db.stamp` 在 `meta.json` 存在時從它取 build，並把 index.html 的 preload 改指 `data/meta.json`。db 站的 `extract_db.stamp` 另以 `<!-- ams-preload --> … <!-- /ams-preload -->` 標記整段重寫首訪 preload（第一行 meta.json，其後 `PRELOAD_DATA`＝manifest＋sheets/02、04、03 的 `.bin`，全部 `?v=<build><金鑰標記>`，讓 600 KB 與登入閘門往返重疊；重複 stamp 不累加，舊版單行會自動遷移成區塊；`stamp_html()` 是純函式可單測）；主站 `stamp_assets.py` 維持只 preload meta。這些 `?v=` 都等於 `D.dataV`，已在 SW keep 清單內。
- **資料網址的版本值＝build＋金鑰標記（2026-10-14）**：金鑰標記＝`meta.check` 去掉非英數字後的前 8 個字（`encrypt_data.key_tag()`；明文站為空）。兩支 stamp 寫進 `<meta name="ams-build" data-key=…>` 與 preload；core.js 以 `?v=<build><data-key>` 取 meta.json，取到之後以**實際拿到的** meta 重算 `D.dataV`＝build＋標記，manifest 與所有 `.bin` 都帶它；`swKeep` 只列 `D.dataV`。由來：密語輪替時 build（明文雜湊）不變、密文全換，舊版網址只帶 build，Service Worker 對 `?v=` 快取優先 → 回訪的瀏覽器拿快取裡舊金鑰的 meta.json 與 `.bin`（新密語「不正確」、舊的記住金鑰遇到沒快取的檔「解密失敗」）。金鑰不變時 check 沿用（compare-and-keep），標記不變、快取照用；`--no-keep`／`--fresh-salt` 會重封 check → 標記換掉、大家重抓一次。`verify_encrypted` 檢查 data-key 與 preload 和 meta.json 一致（不一致＝戳記過期，重跑 stamp）。
- 前端（core.js）：`D.loadMeta()` 與登入閘門並行；`meta.json` 404 或 `enc:0` → 明文模式（本機開發／mock）。加密模式下 `D.url` 檔名加 `.bin`、`D.fetchJSON` 收齊 bytes → `crypto.subtle.decrypt`（AAD＝path）→ `DecompressionStream('gzip')` → JSON；進度以密文 content-length 為分母（不再用 manifest bytes 估計）。`D.unlock()`：先試 `localStorage['ams.key']`（raw key base64，「記住此裝置」勾選才存；**不可用 `atlas.key`**，同源會與 signal-atlas 互踩），否則密語視窗；標頭「清除密語」＝ `D.forgetKey()`。`D.cryptoOK()` 不通過（舊瀏覽器／非 https）顯示說明。
- 指令：
  - `py tools/encrypt_data.py docs/data`、`py tools/encrypt_data.py docs/db/data`（明文 → 密文，原地，刪明文）；`--decrypt`（原地還原）；`--decrypt-to DIR`（另存明文副本）；`--no-keep`（每個檔都以新的隨機 IV 重封，也不檢查金鑰是不是已發布的那一把）；`--fresh-salt`（換 salt，等同 `--no-keep`）；`--key-file FILE`；`--dry-run`（只印會沿用／重封幾份、會刪幾個過期的 `.bin`，不寫檔）。
  - 產生器 `extract.py`／`extract_db.py` 結尾自動加密（`--no-encrypt` 只供本機測試，**不可 push**）；`extract_db.py`／`build_card_aux.py` 遇到已加密的輸出目錄會先原地解密。
  - `py tools/verify_encrypted.py`：重新以密語解開全部 `.bin`、確認沒有明文 `.json`、manifest 引用與檔案一一對應（含 `card/index.json` 的 `hmi.files`、`pid.files` 兩份影像清單）、以明文重算 build（`sheets/*.json`＋`card/**/*.json`）並比對 meta／manifest／version.json／index.html、掃建置機器本機路徑、robots／noindex。**每次 push 前必須 exit 0**。
    本機路徑規則 `LOCAL_RE = Users[\\/]{1,2}bacon|/c/Users/|我的雲端硬碟|@@新機組`：**`{1,2}` 不可拿掉**——掃的是 JSON 文字，Windows 分隔符在裡面是兩個反斜線，
    舊版寫成 `Users[\\/]bacon` 對 JSON 內的 Windows 路徑整支失效（假陰性，`sheets/61.json` 就這樣帶著建置機家目錄出貨）。
    「其他電腦」刻意**不**列入：AMS 資料庫自己的工作站標籤叫「本廠其他電腦 (2024 以後)」（sheets 19／24／28），不是路徑。
    供料端同一份規則在 `tools/db/pneuvalve_site.py`：`scrub_local()`＝文件庫根 → 相對、家目錄 → `~`、其餘還帶本機痕跡的多層路徑 → **只剩檔名**，
    而且在 `read_xlsx()` 就剝（`cell_sources()` 讀的是未經 `clean()` 的原始列，只在 `clean()` 剝會漏）。注意 Python 字元集要寫 `[\\/]`，`[\/]` 只等於 `[/]`。
- **沿用沒變的密文（compare-and-keep，2026-10-08）**：`encrypt_dir(data, passphrase, salt, keep=True)` 加密時只開一個 `git cat-file --batch`（cwd＝資料目錄，物件名 `HEAD:./<rel>.bin`，所以與呼叫端的 cwd 無關；`GIT_DIR` 這類指定 repo 位置的環境變數先拿掉）取 **git HEAD** 上同一路徑的密文，每一份先以 git 報的物件名驗過（物件名＝內容的雜湊）才收。用**現在這把金鑰**、AAD＝rel 打得開，而且 gunzip 之後與新明文**逐位元組相同**，就把 HEAD 那份原封不動寫回去；否則以新的隨機 IV 重封。比的是明文、不是 gzip 之後的位元組（zlib 換版照樣沿用）；來源是 HEAD、不是工作目錄（原地解密時 `.bin` 已經刪掉了）——上一次建置還沒 commit 就再建一次，有變的檔會再重封一次，無妨。加密格式沒變：瀏覽器、`decrypt_dir`、`verify_encrypted` 都不必改。沒裝 git、資料目錄不在 git 工作區、HEAD 沒有那個路徑、git 逾時（300 秒）、個別舊密文打不開或明文不同 → 那幾份照舊重封，不報錯。
  結尾那行：`[encrypt] <dir>: N files  X MB → Y MB on the wire  build …  (K kept from git HEAD, M sealed fresh = Z MB new)`；**一份都沒沿用**時附原因 `[keep off]`／`[nothing for this dir at git HEAD]`／`[no file matches its git HEAD copy]`／`[key mismatch with git HEAD]`，有沿用而 HEAD 的 `meta.check` 用不上時附中性的 `[meta.check re-sealed]`。2026-10-10 那次重建：db 站 333 檔裡沿用 137、重封 196（＝工作目錄 71 個有變的 `.bin`＋125 個新檔：117 張 P&ID 圖紙、8 個新分塊）；git HEAD 是 208 檔 17.9 MB、現在 333 檔 28.7 MB。全部密文先放在記憶體再寫檔，用量是該站密文大小的數倍（`encrypt_data.py` 檔頭有實測）。
- **寫檔順序（中斷在任何一步都救得回來）**：全部密文先在記憶體備妥（到這裡資料目錄一個位元組都沒動）→ 先刪掉「與這次要寫的 `.bin` 只差大小寫」的舊 `.bin`（不分大小寫的檔案系統上，新密文會寫進舊檔名、AAD 卻是新檔名 → 打不開）→ 寫全部 `.bin`（明文還在，中斷就重跑）→ 刪掉沒有對應明文的舊 `.bin` → 寫 `meta.json` → 刪 `manifest.json`（**這一刻起 `is_encrypted()` 為真**＝有 `meta.json` 而沒有 `manifest.json`）→ 刪其餘明文。
- **殘留明文的收拾（leftover sweep）**：刪明文那一步刪不掉的（檔案被別的程式開著）跳過、其餘照刪，最後以非 0 結束並列出剩下的檔。同一個加密指令再跑一次（目錄已加密、裡面還有明文 → `sweep_leftovers`）：金鑰用**這個目錄 `meta.json` 的 salt**＋密語（不看 key 檔的 salt，它可能正是出錯的那個；密語打不開 `check` 就在動任何檔之前結束）；殘留的明文若與它的 `.bin` 解開、gunzip 後逐位元組相同就刪掉；沒有 `.bin`、打不開、內容不同、刪不掉的一個都不動，列出來並以非 0 結束（那不是已經封存的內容，要人看過才能刪）。
- **這次的金鑰不是已發布的那一把 → 封完之後擋下來（2026-10-10）**：三個條件都成立才擋——(1) keep 開著（不是 `--no-keep`／`--fresh-salt`／`keep=False`）；(2) git HEAD 上這個資料目錄有 `meta.json`，而且讀得懂（JSON、`enc` 為真、`kdf.salt` 16 bytes、`check` 長度正確）；(3) 這次的金鑰（密語＋salt）打不開它的 `check`。擋的方式：**照常把整個目錄封完**（用這次的金鑰；不能因為要擋就把明文留在 `docs/` 底下）→ 印結尾那行 → `raise SystemExit`（**exit 1**；行程內呼叫 `encrypt_dir` 的產生器同樣是這個 SystemExit 往外傳，後面的戳記不跑，`index.html`／`version.json` 沒被動過）。訊息 `[encrypt] STOP - key mismatch: …` 寫原因——密語不同／salt 不同（HEAD 的 salt 是公開的，拿它重算一把就分得出來，並印出已發布的 salt，照抄到 key 檔第 2 行即可）／兩者都不同／KDF 參數不同——與三條出路：① `git checkout -- <data>` 再 `git clean -fd -- <data>`（後者清掉 HEAD 沒有的 `.bin`）放棄這次建置；② 修正 `AMS_WEB_KEY` 或 key 檔（第 1 行密語、第 2 行 salt）後做 ① 再重建；③ 確定是要換金鑰：目錄已經用新金鑰封好，戳記、驗證、commit 即可，手動加密時加 `--no-keep` 就不做這項檢查。`--dry-run` 遇到同樣情形也印原因並以非 0 結束（什麼都沒寫）。
  由來：key 檔少了第 2 行（例如只從密碼管理器還原了密語）時 `passphrase_and_salt()` 會自己產生新 salt 寫回去，`AMS_WEB_KEY` 給錯也一樣——以前加密照樣成功、`verify_encrypted` 拿同一把金鑰去驗當然全過，沒有任何一關會紅；上線才看得到後果：同源的兩站共用瀏覽器的 `ams.key`，salt 一邊換了一邊沒換就互相重問密語，`STOCK_TOKEN` 由金鑰算出、對不上之後領取／放入全部「未授權」。**不會誤擋**：第一次加密、資料目錄不在 git 工作區、沒裝 git（HEAD 查無 `meta.json`）、`rotate_passphrase.py`（它加密的是 `data.rotate-tmp` 副本，HEAD 沒有那個路徑）。**會擋，而且是故意的**：密語輪替完還沒 commit 就原地重建（HEAD 仍是舊金鑰的 `meta.json`）——先把輪替 commit 進去。經 `rebuild.py`：`build_card_aux`／`pneuvalve_site` 封完以非 0 結束 → rebuild 中止（它的失敗處理只在 `manifest.json` 還在時才再跑一次加密，這時已經不在）。**限制**：靠的是 git HEAD——查不到 HEAD 的 `meta.json` 就沒有這項保護，結尾那行會是 `[nothing for this dir at git HEAD]`；在 repo 裡重建卻看到這句，一樣要停下來查。
- `.gitattributes`（repo 根目錄，2026-10-10）：只有一條 `*.bin binary`——密文不做換行轉換（`core.autocrlf`）、不做文字 diff／merge；沒有全 repo 的 eol 規則。
- `.gitignore` 擋掉 `docs/*/data/**/*.json`（meta.json 除外），明文永遠 commit 不進去；`docs/robots.txt` Disallow 全站、index.html `noindex, nofollow`。
- 誠實的限制：同一組密語所有同事共用，沒有個人撤銷；勾「記住此裝置」時 raw key 明文存在該瀏覽器 localStorage（嚴格 CSP、無行內 script 是它的防線）；員工代號閘門只是稽核紀錄，密語才是真正的保護。沿用密文之後，commit 歷史**確定**看得出「哪幾個檔這次有變」（內容仍然看不到；以前從密文大小其實也幾乎看得出來——AES-GCM 不改變長度、gzip 的結果是固定的）。

## 備品庫存（stock；docs/db 站；tools/stock/）

倉庫資料不在 `data/`，而是即時來自 **Cloudflare Worker + D1**（`tools/stock/worker/`：`src/index.js`、`schema.sql`；表 items／ledger／txns／client_log／revoked）；前端 `docs/assets/stock.js`，另有第二個前端 **Transmitter 網站**（另一個 repo，`https://momobacon-wq.github.io/Transmitter/#/inventory`）：同一套 API、同一套授權（登入 token ＋ `stockToken`，Worker 不為它放寬），讀 `docs/db/stock-config.json` 取得 endpoint；Worker 端不需任何改動（同源，CORS `ALLOWED_ORIGINS` 已涵蓋）。SSO：兩站同源共用 localStorage `ams.auth`（`auth.js` 工作階段）與 `ams.key`（`core.js`「記住此裝置」的 raw key），任一站登入另一站沿用；密語解鎖只有勾「記住此裝置」（寫入 `ams.key`）時才跨站沿用，沒勾時只存在該分頁（Transmitter 存 sessionStorage `transmitter.stockToken`，綁定解鎖當時的登入者）；任一站登出都清掉這兩個鍵；Worker 回密語不符時兩站都不刪 `ams.key`。Transmitter 不能新增品項（Worker 沒有新增 API）；舊試算表 Inventory／Logs 凍結，不遷移。兩站共用每 IP 每分鐘 60 次 POST 限額，Transmitter 自動刷新間隔須 ≥30 秒且分頁隱藏時暫停。**改 API 回應格式、`stockToken` 算法、`ams.auth`／`ams.key` 的格式或鍵名時，Transmitter 要同步改。**`tools/stock/Code.gs`（試算表＋Apps Script）是同一 API 格式的替代後端，前端不分後端。

- 啟用條件：`docs/db/stock-config.json` `{"endpoint": "https://script.google.com/macros/s/…/exec"}`（空＝關閉，查詢卡沒有該組、側欄沒有「備品庫存」、`#/stock/` 顯示未啟用）且已登入（`AMSAuth.user.token`）。`app.js` 在 `loadManifest` 後 `AMS.Stock.ready()`。
- D1 `items(pn PK, model, brand, spec, loc, qty CHECK≥0, proto, family, contract, cqty, min_qty, note, updated_at)`、`ledger(id, ts ISO-UTC, emp_id, emp_name, action OUT／IN／STOCKTAKE／IMPORT, pn, delta, balance, kks, note, wo, source ams-card／ams-stock／transmitter（未帶＝ams；Worker 截 20 字）, txn_id)`（只附加）、`txns(txn_id PK)`。
  試算表版（Code.gs）對應：Inventory A–L＝PartNumber, Name(型號), Brand, Spec, Location, Quantity, Protocol, Family, Contract, ContractQty, MinQty, Note（A–F 與 Transmitter 相容）；Logs A–L＝Timestamp, EmployeeID, ActionType, PartNumber, ChangeAmount, Balance, EmployeeName, KKS, Note, WorkOrder, Source, TxnId。
- API（POST text/plain JSON，回 `{ok,…}`；每個 action 都帶 `id`、`name`（只做紀錄顯示）、`token`（登入 HMAC token，後端用同一個 `AUTH_SECRET` 驗）與 `stockToken`；Worker 只對 `ALLOWED_ORIGINS` 回 CORS 標頭）：
  `list` → `{rev, lowCount, items[{pn, model, brand, spec, loc, qty, proto, family, contract, cqty, min, note}]}`（`lowCount`＝`min_qty` 非 NULL 且 `qty ≤ min_qty` 的料號數；側欄「備品庫存」徽章、`#/stock/` 進頁面預選「低於安全存量」）；
  `logs {pn?, kks?, limit≤300, since?, until?, before?}` → `{rows[{ts,id,name,action,pn,delta,bal,kks,note,wo,source,txn,rid}]}`（`since`／`until` ISO UTC 字串，`ts >= since`、`ts < until`，非 ISO 視為沒給；`before`＝ledger id 游標只回 `id < before`；`rid`＝該列 ledger id，前端「載入更多」「匯出區間全部」以最後一列的 `rid` 當下一頁 `before`）；
  `txn {txnId, items[{pn, delta}], kks?, note?, wo?, source?}` → `{results[{pn, qty, delta, min, low}], replay?}`（整批驗證、任一失敗不寫；Worker 用 `DB.batch` 單一交易：INSERT txns → UPDATE items → INSERT ledger，`CHECK(qty>=0)` 兜底，同 txnId 重送回同結果 `replay:true`；`low`＝寫入後 `qty ≤ min_qty`，前端 toast 加「已低於安全存量」）。
  庫存不足（預檢或 CHECK 兜底）→ `{ok:false, stale:true, error, items[{pn, qty}]}`：本批全部料號的現量，前端領取視窗就地更新「現有 N」與上限、不關窗（`S.openTxn` 的 `onStale`），不清購物車。盤點 `adjust` 動作已移除（數量調整用 SQL 同時 UPDATE items ＋ INSERT ledger STOCKTAKE，見 `tools/stock/README.md`）。
  前端 `S.openTxn` 開窗時產生一次 `txnId`（`S.newTxnId`），同一視窗重送沿用同一 txnId（`S.txn(o)` 有 `o.txnId` 就用它）；連線逾時／fetch 失敗只提示「可能已寫入，重按不重扣」，不自動重送；回應 `replay` 為真時 toast 加「先前已寫入，未重扣」。
  失敗：`{ok:false, auth:true}` 未授權（含 `revoked` 表命中：「此員工代號已停用」，`clientlog` 同樣擋）、`{ok:false, transient:true}` 伺服器錯誤（固定文案「伺服器暫時無法服務，請稍後再試」，D1 原文只進 Worker console）、HTTP 429 `{ok:false, transient:true}` 每 IP 每分鐘 60 次 POST 超限（`wrangler.toml` `[[ratelimits]]` binding `RL`；沒有 binding 時不限）；`clientlog` 每人每分鐘 10 筆，超過回 `{ok:true, dropped:true}` 不寫（索引 `client_log_emp_ts`）。
  停權：`revoked(emp_id PK, ts)`，`auth()` 與 `clientlog` 在 token 驗證通過後查一次；`INSERT OR IGNORE INTO revoked` 即時生效，離職 SOP 見 `tools/stock/README.md`。
- `STOCK_TOKEN`＝`hex(SHA-256("ams-stock:" + base64(AES 原始金鑰)))`：瀏覽器由解鎖後的 `D.key` 算（明文模式送 `plain`，只有 mock 接受）；建置端 `tools/stock/print_token.py`。換密語／salt → `npx wrangler secret put STOCK_TOKEN` 重貼。
- 對照規則（`AMS.Stock.match`；`contracts_to_inventory.py` 的 FAMILY_RULES 同步維護）：正規化＝大寫、去空白／-／_／／；E+H 取 `+` 前段；本體碼＝`3051|2051|2088|214C|5408|8732E` 開頭者取前 12 碼，其餘整段。
  第一層「同型號」＝本體碼相同；第二層「同系列」＝系列鍵相同（`3051S`、`3051[CLT]X`、`2051[CT]X`、`2088[AG]`、`644`、`848T`、`5408`、`8732E`、`214C`、`PMD75`、`PMP71`、`TMT82`）。
  設備端候選碼：card aux 儀器清單「完整型號碼」、EOMR「出廠型號」（`/` 後的歧管碼去掉）；兩者皆無時才用 AMS 型號的家族（`3051`→`3051*` 全系列、`iTEMP TMT82`→`TMT82`、`Deltabar S`→`PMD75`、`Cerabar S`→`PMP71`…）。
- 查詢卡：`renderSummary` 末尾加 `section.sum-g.sum-stock`（不改 02.json，不必重建資料），資料到齊後 `stockCtx(row, aux, tag)` → `AMS.Stock.fillCard(grid, ctx)`；領取／放入視窗自動帶入位號 KKS；「此位號紀錄」以 KKS 篩選紀錄。
- 本機：`tools/auth/mock_server.py` 把 `stock-config.json` 指到 `/mock-stock`（`tools/stock/mock_stock.py`，假資料 `mock_inventory.json`）；環境變數 `AMS_STOCK_ENDPOINT=http://127.0.0.1:8787` 則指到 `npx wrangler dev` 的真 Worker（本機 D1，`.dev.vars` 的 `AUTH_SECRET=mock-secret` 可驗 mock 登入 token）。真實庫存匯入檔（`tools/stock/*.csv`、`worker/import*.sql`）不進 repo；`docs/db/index.html` CSP `connect-src` 含 `https://*.workers.dev`。

## 前端快取（Service Worker）與錯誤回報

- `docs/sw.js` 由 `assets/app.js` 註冊（網址從自己的 `<script src>` 推得，範圍＝站根目錄，主站與 `db/` 共用）。同源 GET：`?v=` → 快取優先；`version.json`／`auth-config.json`／`stock-config.json` → 只走網路；其餘 → 網路優先、失敗用快取。跨網域不處理。頁面 `boot()` 結尾 `postMessage {type:'keep', dir, v:[…]}`，Service Worker 刪除 `<dir>data/` 與 `assets/` 底下 `?v=` 不在清單內的項目（另一站的 `data/` 不動）。**因此所有資料檔與程式檔的網址都必須帶版本值**（stamp 已保證；資料檔的版本值含金鑰標記，換密語就換網址）；沒有版本值的檔不會被快取優先。
- `docs/assets/report.js`（兩站 `index.html` 在 `boot.js` 之後載入）：`window.AMSReport.send(kind, msg, {stack, path})`；`core.js` 的 `D.fetchJSON` 失敗時呼叫 `send('load', …, {path})`。端點取 `<meta name="ams-report">`（主站指向 `db/stock-config.json`）或 `<meta name="ams-stock-config">`（db 站）；請求 `{action:'clientlog', id, token, name, kind, msg, stack, path, page, site, build, app, ua}`，Worker 只驗登入 token（不需 stockToken），寫 D1 `client_log`。只在 `AMSAuth.user.token` 存在時送；每次載入最多 8 筆、同訊息不重送；主站 CSP `connect-src` 因此也列了 Worker 主機。
- `card.js` 的 `run(q)`：查詢框無條件同步成路由裡的查詢（上一頁／網址列深連結也會換）；查無位號但有相近建議時狀態列用 `lookup.msg.notfound_near`（DEFAULT 內建，規格可覆寫）。
- 端對端測試：`tools/tests/run_e2e.py`（README）。
