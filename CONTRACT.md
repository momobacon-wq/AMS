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
- `manifest.build`：所有輸出檔（sheets/*.json＋不含 build 的 manifest）的 sha256 前 10 碼，由 `tools/extract.py` 寫入（決定性，不含時間）。前端對每個資料檔請求加 `?v=<build>`，同一分頁不會混用兩次建置的分塊。
- `tools/stamp_assets.py`（extract 結束時自動執行；只改 docs/assets 時手動執行）：index.html 的 `assets/*.js|css` 加 `?v=<檔案雜湊>`、`<meta name="ams-build" content=<build> data-app data-chart>`、manifest preload 加 `?v=<build>`；寫出 `docs/version.json {"build","app"}`。開著的分頁在切回前景／換頁（至多每 5 分鐘）以 no-cache 取 version.json，不同時提示重新整理。
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
- `sections_aux: [{key, label, kind?, only_ff?, empty?, note?}]`：附加區段的標題與順序（維護狀態、最後修改、DCS 比對、FF 診斷（僅 FF）、控制系統·控制器現行 I/O 組態（dcdas）、控制系統·端子表、設計規格、出廠紀錄、文件索引、文件全文檢索（docsearch）、P&ID 圖面位置（pid，v6）、圖控 HMI 畫面位置（hmi，v5）、位號歷程補充、類比輸出警報、設備補充）；`summary.groups[]` 的 `per_entry` 組（`kind: dcdas|terminal`）每個訊號一塊；`aux: {index:"card/index.json", number_from:5}`：附加區段自第 5 節起連續編號，快速連結與最近變更接在其後。`protocol_col`＝03 協定欄。
- `summary.groups[]` 可帶 `collapsed: true`（渲染成 `<details class="sum-g">`＋`<summary class="sum-gh">`，預設收合；展開狀態記 localStorage `ams.card.sumOpen[key]`；列印時照既有規則展開）與 `after_stock: true`（排在前端動態加的「備品庫存（倉庫）」組之後；沒有備品庫存時排最後）。
- `summary.groups[].items[]` 的 `alt`（單一 `{kind,key}` 或陣列）：主來源空白時依序改用的備援；標籤加「（<kind 中文名>）」。`kind` 為 rows 型區段（`docindex`／`docsearch`）時以列名（類別／推定值名）對照，該列自帶 lvl／來源／文件。

### card aux（`docs/db/data/card/`）
產生：`py tools/db/build_card_aux.py <cardwork_dir> docs/db/data`（在 extract_db 之後執行；會把 card/*.json 納入 `manifest.build` 並重新 stamp）。輸入為 `card_ams_extra.py`、`docmap_terminal.py`、`docmap_instlist.py`、`docmap_eomr.py`、`docmap_docindex.py` 的輸出（不進 repo），加上 signal-atlas 的控制器索引 `%LOCALAPPDATA%\dcdas\index.sqlite`（`--dcdas` 可指定、`--no-dcdas` 略過；不進 repo）、`docmap_docsearch.py` 的輸出 `%LOCALAPPDATA%\AMS\cardwork\docsearch.json`（`--docsearch`／`--no-docsearch`）與 `drive_map.py` 的 `%LOCALAPPDATA%\AMS\drive_map.json`（`--drive-map`／`--no-drive-map`；文件庫相對路徑 → Google 雲端硬碟檔案 ID，由 Drive 桌面版中繼資料庫產生）。`--recompare docs/db/data`：cardwork 不在手邊時讀已發布的 card/*.json 只重算 `sec.dcdas`／`compare`／`flags.cmp`（舊資料無 compare 的設備，儀器清單／EOMR 量程不列入比對），有給 docsearch.json 就換掉 `sec.docsearch`，有 drive_map 就重新對照 `docs[].url`／`url_note`（`file|…` 整批重算）。dcdas／docsearch／hmi／pid／drive_map 任一缺席而沒給對應 `--no-*` 旗標時以非 0 結束（印「!! 缺 …，若確定要略過請加 --no-…」；圖控與 P&ID 的輸入、旗標與各自的關卡見 v5、v6），`rebuild.py` 因此中止並走加密回滾——少了它們查詢卡的「控制器組態」／「文件全文檢索」區段或所有 Drive 連結會整個消失，而 build 雜湊與 verify_encrypted 都不會察覺。
- `manifest.aux.card = {index, desc, parts, bytes}`。`manifest.build` 雜湊涵蓋 `sheets/*.json`＋`card/**/*.json`（含 `card/hmi/`、`card/pid/` 的影像檔）＋manifest（不含 build）；前端所有資料請求加 `?v=<build>`。
- `card/index.json`（v2，只留全廠共用的小東西；密文原本約 27 KB；加了 v5 的 `hmi` 之後 git HEAD 是 32,570 bytes，2026-10-10 是 41,466 bytes——多出來的是 v6 的 `pid.sheets` 117 筆與 `pid.note`）：`{version:2, parts, part_width, files:["card/aux-00.json",…], alias:{alias: 塊號}, src_defs, kind_label, doc_cat_order, searched:{dcdas|terminal|instlist|eomr|docindex|docsearch|hmi|pid: [{doc_id, rev, ref?, title, folder, used, why, category?}]}, source_stats, stats, compare_rule, hmi?, pid?}`（頂層的 `hmi` 見 v5、`pid` 見 v6；`kind_label`、`source_stats`、`stats.sections` 也各多了 `hmi`、`pid`）（`dcdas` 那筆＝signal-atlas 索引本身：doc_id `signal-atlas`、rev＝各控制器 checkout 日（`controller.last_mod`）列表、ref 含 checkout 區間與索引建立日；`docsearch` 那筆＝hst-docsearch 索引本身：doc_id `hst-docsearch`、rev＝索引日期）。`stats` 另含 `near`、`dcdas_multi`、`ams_vs_dcdas:{ok,near,mismatch,not_compared}`、`docs_with_url`、`docs_with_url_altrev`、`doc_no_resolved`。
- 文件中繼資料 `docs` 與 `doc_no` **隨各分塊攜帶**（v1 全放 index，每筆含 33 字元 Drive ID 不可壓縮、占第一張卡下載量近半）：`card/aux-NN.json = {part, by_alias:{alias: {sec, compare, flags}}, docs:{"kind|doc_id|rev": {title, folder, why?, category?, url?, url_note?}}, doc_no:{文件編號: "file|編號|版次"}}`，`docs`／`doc_no` 只含該塊 by_alias 引用到的子集（所有鍵名 `d` 指到的文件＋塊內文字出現的文件編號）；前端 `D.loadAux` 把分塊的 `docs`／`doc_no` 併回 `ix` 再交給卡片，卡片端仍讀 `ix.docs`／`ix.doc_no`（舊版 index 也相容）。`docs[].url`＝`https://drive.google.com/open?id=<Drive 檔案 ID>`（有 drive_map 時；前端把該文件來源的數值變成連結，來源展開列「Google 雲端硬碟」）；`url_note`＝退路只對到同編號、別版次（或檔名版次不明）的檔時的說明「雲端只找到 <檔名>（版次 X，與本站資料來源的版次 Y 不同）」——連結仍給（同編號別版次仍有參考價值），前端列「Google 雲端硬碟（版次不同：檔名）」並併入滑鼠提示，工程師才不會把別版次的值拿去改現場。無編號的檔 key 為 `docsearch|<sha1(路徑)前 12 碼>|`。`doc_no`＝欄位值本身寫的文件編號（P&ID、邏輯圖、Hook-up 圖、位置圖、EOMR 亦見於…）對到文件庫裡那份檔（檔名以編號開頭；值有寫版次取該版，否則最高版次；PDF 優先、排除副本夾；指定版次不在雲端時 why 寫「指定版次 X 不在雲端，改開最高版次 Y」），docs 同 key 給 title/folder/url；前端讓這種值直接開那份圖（來源展開多一列「欄位所指文件」），不是開提到它的來源文件。`folder` 一律是相對工程文件庫根目錄的資料夾名；**任何 JSON 不得含本機絕對路徑**（產生器以 regex 自檢，命中即中止）。
- `card/aux-NN.json`（依 03 列序分塊，每塊明文 ≤ 約 350 KB／密文 ≤ 約 45 KB，含該塊的 docs 子集）：`{part, by_alias:{alias: {sec, compare, flags}}, docs, doc_no}`。
  - `sec.sync|change|ident|device|alarm|ff = {rows: [[欄位, 值, lvl, 來源字串]]}`（AMS DB 補充）。
  - `sec.dcdas|terminal|instlist|eomr = {entries: [{h, lvl, src, rule, d?, note?, rows: [[欄位, 值, 狀態?]]}]}`：一筆 entry＝一份文件的一列/一頁（dcdas：控制器的一個類比輸入通道，lvl `ctrl`，rows＝控制器、I/O 模組、通道、訊號名、裝置位號 (DeviceTag)、輸入型式、HART 通道、`DCS AI 量程 (Low/High Value)`、訊號說明、signal-atlas 深連結；`rule`＝位號對照方式）；entry 內各欄共用 `src`；`d` 指向 docs（分塊自帶）；狀態 `near|mismatch|unit_mismatch|unit_unknown`（量程欄與 DCS 基準比對）或 `warn`（EOMR 序號與 AMS 不符；dcdas：同位號另一通道的量程與基準通道不同）。
  - 文件參照字串：產生器可給 `ref`（完整顯示字串），否則 `doc_id-rev`。DCS 端子表 xlsx 本身沒有版次字母（CoverSheet「Revision」欄未隨 IO Rev 更新）：字母取自同 IO Rev 的 PDF 檔名時寫 `HT1-1-IMI01-A0001-H（推定）`；找不到對應 PDF 時寫 `HT3-1-IMI01-A0001（IO Rev3，版次字母不明）`。同 IO Rev 多份 xlsx 取修改時間最新者。
  - 儀器清單 HRSG xls 的 RANGE 若為數值儲存格（原文無單位，「0~」與單位只來自整欄數字格式）：`設計量程（原文）` 寫原數值並說明格式，另加 `量程單位來源＝儲存格數字格式（推定）`；比對一律 `unit_unknown`。
  - `sec.docindex = {rows: [[類別, "文件-版次 · p.頁", lvl, 來源字串, {rule, d?}]]}`。
  - `sec.hmi = {rows: [[欄位, 值, "hmi", 來源字串, extra]]}`＝圖控 HMI 畫面位置（每組畫面 4 列；見下方「v5（docs/db 站：圖控 HMI 畫面位置）」）。
  - `sec.pid = {rows: [[欄位, 值, "doc"|"inferred", 來源字串, extra]]}`＝P&ID 圖面位置（每張圖紙 5 列；見下方「v6（docs/db 站：P&ID 圖面位置）」）。
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
- 建議：`AMS.searchSuggestSource`（查詢卡輸入框與頂列搜尋）把 `IX.suggest`（AMS 在前，至少 8 筆）與 `AMS.valves.suggest`（最多 4～6 筆）合併；`AMS.tagSuggestSource` 維持只有 AMS 位號索引（備品庫存的 KKS 正規化用它，氣動閥別名／`Gxx` 位號不得寫進領料紀錄）。`valves.suggest` 項目 `{key, src:'氣動閥清單', alias:<名稱>, tag:<清單位號>, valve:[sid,列], m:'pre'|'sub'|'name', rows?}`：位號／別名開頭 → 包含；輸入帶機組或 `90` 時去前綴再比、只取涵蓋該機組的列、`key` 給帶機組的位號（`G11MBP70QN2` → `G11MBP70QN222`）；輸入含中文時改比名稱（空白分段、每段都要出現）；同一別名對多列只列一次，`rows`＝列數（`tag` 保持真的位號）；`key` 一定是 `hit`／位號索引查得到的字串。查無頁 `renderNotFound` 多一塊「氣動閥清單中相近的閥」（`.nf-valves`）與「在 57／58 搜尋」連結；兩邊都沒有候選時狀態列加註可到 57／58 搜尋。
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

## 加密與封裝（tools/encrypt_data.py；兩站共用）

GitHub Pages 是公開靜態站，`docs/*/data` 一律以**密文**發布，只有 `data/meta.json` 是明文；瀏覽器在員工代號登入後再輸入**密語**解密（與 momobacon-wq/signal-atlas 同一套作法）。

- 金鑰：`PBKDF2-HMAC-SHA256(密語, salt, 200000)` → 32 bytes（AES-256-GCM）。密語只存建置機器 `%LOCALAPPDATA%\AMS\web.key` 第 1 行（或環境變數 `AMS_WEB_KEY`／`AMS_WEB_KEY_FILE`），**永不進 repo**。
- salt（16 bytes）存 key 檔第 2 行，**固定不隨建置改變**（salt 本來就公開在 meta.json；固定後「記住此裝置」的金鑰在資料重建後仍可用，且 docs/ 與 docs/db/ 同源共用同一把）。`--fresh-salt` 或改密語＝輪替，兩站都要重新加密（那一次全部重封；輪替的 commit 進去之前不能原地重建，見下面「這次的金鑰不是已發布的那一把」）。
- 每個資料檔（`manifest.json`、`sheets/*.json`、`card/**/*.json`——含 `card/hmi/`、`card/pid/` 的影像檔；`encrypt_data.py` 以 `rglob("*.json")` 收，`meta.json` 除外）存成 `<rel>.bin` ＝ `12-byte 隨機 IV ‖ AES-GCM(gzip(JSON UTF-8, level 6, mtime 0))`（含 16-byte tag，WebCrypto 版面），**AAD＝相對路徑 rel（不含 .bin）**，密文不能搬到別的路徑。**IV 只在「重封」時才重新抽**：2026-10-08 起，明文沒變的檔沿用 git HEAD 上那一份密文（連 IV 一起，見下面「沿用沒變的密文」），所以「每次建置每個檔的密文都不同、每次 commit 都帶全部 `.bin`」已經不成立；同一組（金鑰、IV）仍然不會拿去封第二份明文——內容一變就重新抽 IV。
- `meta.json` ＝ `{"enc":1,"gzip":1,"build":<manifest.build>,"kdf":{"name":"PBKDF2","hash":"SHA-256","iter":200000,"salt":<b64>},"check":<b64 seal(key,"ams-ok",aad="check")>}`；`check` 只用來驗密語；git HEAD 的 `meta.json` 的 `kdf` 與這次相同、`check` 用這把金鑰打得開時沿用原字串（內容沒變的站重新加密後 `meta.json` 逐位元組相同）。
- `manifest.build` 仍以**明文**內容計算（重封的檔 IV 隨機，密文不可拿來算 hash；一個檔是沿用還是重封都不影響 build）：產生器先算 build 寫 manifest → `encrypt_dir` → stamp。`tools/stamp_assets.py`／`extract_db.stamp` 在 `meta.json` 存在時從它取 build，並把 index.html 的 preload 改指 `data/meta.json`。db 站的 `extract_db.stamp` 另以 `<!-- ams-preload --> … <!-- /ams-preload -->` 標記整段重寫首訪 preload（第一行 meta.json，其後 `PRELOAD_DATA`＝manifest＋sheets/02、04、03 的 `.bin`，全部 `?v=<build>`，讓 600 KB 與登入閘門往返重疊；重複 stamp 不累加，舊版單行會自動遷移成區塊；`stamp_html()` 是純函式可單測）；主站 `stamp_assets.py` 維持只 preload meta。這些 `?v=` 都等於 build，已在 SW keep 清單內。
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

- `docs/sw.js` 由 `assets/app.js` 註冊（網址從自己的 `<script src>` 推得，範圍＝站根目錄，主站與 `db/` 共用）。同源 GET：`?v=` → 快取優先；`version.json`／`auth-config.json`／`stock-config.json` → 只走網路；其餘 → 網路優先、失敗用快取。跨網域不處理。頁面 `boot()` 結尾 `postMessage {type:'keep', dir, v:[…]}`，Service Worker 刪除 `<dir>data/` 與 `assets/` 底下 `?v=` 不在清單內的項目（另一站的 `data/` 不動）。**因此所有資料檔與程式檔的網址都必須帶版本值**（stamp 已保證）；沒有版本值的檔不會被快取優先。
- `docs/assets/report.js`（兩站 `index.html` 在 `boot.js` 之後載入）：`window.AMSReport.send(kind, msg, {stack, path})`；`core.js` 的 `D.fetchJSON` 失敗時呼叫 `send('load', …, {path})`。端點取 `<meta name="ams-report">`（主站指向 `db/stock-config.json`）或 `<meta name="ams-stock-config">`（db 站）；請求 `{action:'clientlog', id, token, name, kind, msg, stack, path, page, site, build, app, ua}`，Worker 只驗登入 token（不需 stockToken），寫 D1 `client_log`。只在 `AMSAuth.user.token` 存在時送；每次載入最多 8 筆、同訊息不重送；主站 CSP `connect-src` 因此也列了 Worker 主機。
- `card.js` 的 `run(q)`：查詢框無條件同步成路由裡的查詢（上一頁／網址列深連結也會換）；查無位號但有相近建議時狀態列用 `lookup.msg.notfound_near`（DEFAULT 內建，規格可覆寫）。
- 端對端測試：`tools/tests/run_e2e.py`（README）。
