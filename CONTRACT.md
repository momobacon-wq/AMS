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
                            extract_db.py（→ docs/db/data）、card_ams_extra／docmap_*／drive_map（cardwork）、build_card_aux.py（card aux）、rebuild.py（一鍵／--sqlite 一條龍）
  tools/auth/  tools/stock/  tools/tests/  tools/hooks/   ← 登入閘門、備品庫存 Worker、端對端測試、pre-commit（各節）
  docs/index.html        ← 主站單頁 App 殼（vanilla JS，無 build step）；docs/db/index.html ← db 站殼（同一套 assets）
  docs/assets/           ← boot / auth / report / core / table / grid / card / stock / app .js、app.css、chart.umd.min.js（Chart.js 4.x，vendored）
  docs/sw.js             ← Service Worker（兩站共用）
  docs/data/meta.json    ← 唯一明文（加密參數與 build）；其餘為密文：
  docs/data/manifest.json.bin
  docs/data/sheets/<id>.json.bin        ← 一般工作表
  docs/data/sheets/<id>-<nnn>.json.bin  ← 大表分塊（21、22，以及任何 > 8 MB 的表）
  docs/db/data/…                        ← 同上（第二資料集）＋ card/index.json.bin、card/aux-NN.json.bin（card aux）
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
- 02.json 頂層 `src_defs: {raw|decoded|inferred|doc|factory|ctrl: {label, desc}}`；`src_default: {wide:"full", narrow:"badge", breakpoint:640}`。
- `sections[].fields[]` 與 `stats.fields[]` 每欄可帶 `src: {lvl, text}`：
  - `lvl` ∈ `raw`（原始：DB 欄，可經 JOIN；灰）、`decoded`（解碼：時間/切段/int32/float32/UTF-16/FF hex/碼表；藍）、`inferred`（推論：經驗規則、對照表、外部對照檔、機組範本；橙）、`doc`（文件·設計；綠）、`factory`（出廠·EOMR；深綠）、`ctrl`（控制器·ToolboxST checkout 快照經 signal-atlas 索引；紫）。
  - `text` 以級別中文名開頭：`「原始 · Devices.Identifier」`、`「解碼 · BlockData {c16} float32 · 最後記錄 {c36}」`、`「文件 · HT1-1-IMI01-A0001-H（推定） IO_Signal!r4514」`、`「出廠 · HT1-1-AQA01-T4739-0 p.1662」`。`{cNN}` 由前端代入同一列（03 或 13）第 NN 欄的值（空白顯示 `—`）。
- 欄位其他可選鍵：`label_by {col, map, default}`（依同列欄值切換標籤，例：協定 FF → 「裝置ID (FF 裝置識別字串)」）；`col` 為陣列時 `join`＋`prefixes`（R/T/F 區塊數 → `R1 / T1 / F12`）＋`blank_if_zero`；`serial`（0 → 「未寫入」）；`flt`（float32）；`cmp`（`ams_lo`／`ams_hi`＝AMS 量程下限／上限欄（只在該端列入比較且不符時標 ⚠）、`ams_unit`＝AMS 單位欄，DCS 比對不符／未比較時加標記）；`proto`（`HART`｜`FF`：協定專用欄位，設備協定（03 `protocol_col`）不同且值空白時不顯示）。
- 值顯示規則（前端 `U.cardValue`）：null／全空白字串 → 「—」；float32 FLT_MIN（|v|<1e-30 且 ≠0，1.1754943508222875e-38）→ 「未使用」；非整數以 7 位有效數字（10000.0009765625 → 10000）；`serial` 且值 0 → 「未寫入」。
- `recent_changes.columns[]` 可帶 `map`（值對照顯示）、`warn_eq`（等於此值時醒目標示）、`title`（表頭說明）、`src {lvl, text}`（欄位來源：徽章模式在表頭顯示分級籤、點開列出；完整模式在表下列出各欄來源）；空白值（含全空白字串，`cols` 的每一段）顯示「—」；「類別」欄＝14 表事件分類：`Change performed by foreign host`（Cat 28）→「DCS·外部主機」，其餘 →「人工 AMS」。
- `sections_aux: [{key, label, kind?, only_ff?, empty?, note?}]`：附加區段的標題與順序（維護狀態、最後修改、DCS 比對、FF 診斷（僅 FF）、控制系統·控制器現行 I/O 組態（dcdas）、控制系統·端子表、設計規格、出廠紀錄、文件索引、文件全文檢索（docsearch）、位號歷程補充、類比輸出警報、設備補充）；`summary.groups[]` 的 `per_entry` 組（`kind: dcdas|terminal`）每個訊號一塊；`aux: {index:"card/index.json", number_from:5}`：附加區段自第 5 節起連續編號，快速連結與最近變更接在其後。`protocol_col`＝03 協定欄。
- `summary.groups[]` 可帶 `collapsed: true`（渲染成 `<details class="sum-g">`＋`<summary class="sum-gh">`，預設收合；展開狀態記 localStorage `ams.card.sumOpen[key]`；列印時照既有規則展開）與 `after_stock: true`（排在前端動態加的「備品庫存（倉庫）」組之後；沒有備品庫存時排最後）。
- `summary.groups[].items[]` 的 `alt`（單一 `{kind,key}` 或陣列）：主來源空白時依序改用的備援；標籤加「（<kind 中文名>）」。`kind` 為 rows 型區段（`docindex`／`docsearch`）時以列名（類別／推定值名）對照，該列自帶 lvl／來源／文件。

### card aux（`docs/db/data/card/`）
產生：`py tools/db/build_card_aux.py <cardwork_dir> docs/db/data`（在 extract_db 之後執行；會把 card/*.json 納入 `manifest.build` 並重新 stamp）。輸入為 `card_ams_extra.py`、`docmap_terminal.py`、`docmap_instlist.py`、`docmap_eomr.py`、`docmap_docindex.py` 的輸出（不進 repo），加上 signal-atlas 的控制器索引 `%LOCALAPPDATA%\dcdas\index.sqlite`（`--dcdas` 可指定、`--no-dcdas` 略過；不進 repo）、`docmap_docsearch.py` 的輸出 `%LOCALAPPDATA%\AMS\cardwork\docsearch.json`（`--docsearch`／`--no-docsearch`）與 `drive_map.py` 的 `%LOCALAPPDATA%\AMS\drive_map.json`（`--drive-map`／`--no-drive-map`；文件庫相對路徑 → Google 雲端硬碟檔案 ID，由 Drive 桌面版中繼資料庫產生）。`--recompare docs/db/data`：cardwork 不在手邊時讀已發布的 card/*.json 只重算 `sec.dcdas`／`compare`／`flags.cmp`（舊資料無 compare 的設備，儀器清單／EOMR 量程不列入比對），有給 docsearch.json 就換掉 `sec.docsearch`，有 drive_map 就重新對照 `docs[].url`／`url_note`（`file|…` 整批重算）。dcdas／docsearch／drive_map 任一缺席而沒給對應 `--no-*` 旗標時以非 0 結束（印「!! 缺 …，若確定要略過請加 --no-…」），`rebuild.py` 因此中止並走加密回滾——少了它們查詢卡的「控制器組態」／「文件全文檢索」區段或所有 Drive 連結會整個消失，而 build 雜湊與 verify_encrypted 都不會察覺。
- `manifest.aux.card = {index, desc, parts, bytes}`。`manifest.build` 雜湊涵蓋 `sheets/*.json`＋`card/*.json`＋manifest（不含 build）；前端所有資料請求加 `?v=<build>`。
- `card/index.json`（v2，只留全廠共用的小東西；密文約 27 KB）：`{version:2, parts, part_width, files:["card/aux-00.json",…], alias:{alias: 塊號}, src_defs, kind_label, doc_cat_order, searched:{dcdas|terminal|instlist|eomr|docindex|docsearch: [{doc_id, rev, ref?, title, folder, used, why, category?}]}, source_stats, stats, compare_rule}`（`dcdas` 那筆＝signal-atlas 索引本身：doc_id `signal-atlas`、rev＝各控制器 checkout 日（`controller.last_mod`）列表、ref 含 checkout 區間與索引建立日；`docsearch` 那筆＝hst-docsearch 索引本身：doc_id `hst-docsearch`、rev＝索引日期）。`stats` 另含 `near`、`dcdas_multi`、`ams_vs_dcdas:{ok,near,mismatch,not_compared}`、`docs_with_url`、`docs_with_url_altrev`、`doc_no_resolved`。
- 文件中繼資料 `docs` 與 `doc_no` **隨各分塊攜帶**（v1 全放 index，每筆含 33 字元 Drive ID 不可壓縮、占第一張卡下載量近半）：`card/aux-NN.json = {part, by_alias:{alias: {sec, compare, flags}}, docs:{"kind|doc_id|rev": {title, folder, why?, category?, url?, url_note?}}, doc_no:{文件編號: "file|編號|版次"}}`，`docs`／`doc_no` 只含該塊 by_alias 引用到的子集（所有鍵名 `d` 指到的文件＋塊內文字出現的文件編號）；前端 `D.loadAux` 把分塊的 `docs`／`doc_no` 併回 `ix` 再交給卡片，卡片端仍讀 `ix.docs`／`ix.doc_no`（舊版 index 也相容）。`docs[].url`＝`https://drive.google.com/open?id=<Drive 檔案 ID>`（有 drive_map 時；前端把該文件來源的數值變成連結，來源展開列「Google 雲端硬碟」）；`url_note`＝退路只對到同編號、別版次（或檔名版次不明）的檔時的說明「雲端只找到 <檔名>（版次 X，與本站資料來源的版次 Y 不同）」——連結仍給（同編號別版次仍有參考價值），前端列「Google 雲端硬碟（版次不同：檔名）」並併入滑鼠提示，工程師才不會把別版次的值拿去改現場。無編號的檔 key 為 `docsearch|<sha1(路徑)前 12 碼>|`。`doc_no`＝欄位值本身寫的文件編號（P&ID、邏輯圖、Hook-up 圖、位置圖、EOMR 亦見於…）對到文件庫裡那份檔（檔名以編號開頭；值有寫版次取該版，否則最高版次；PDF 優先、排除副本夾；指定版次不在雲端時 why 寫「指定版次 X 不在雲端，改開最高版次 Y」），docs 同 key 給 title/folder/url；前端讓這種值直接開那份圖（來源展開多一列「欄位所指文件」），不是開提到它的來源文件。`folder` 一律是相對工程文件庫根目錄的資料夾名；**任何 JSON 不得含本機絕對路徑**（產生器以 regex 自檢，命中即中止）。
- `card/aux-NN.json`（依 03 列序分塊，每塊明文 ≤ 約 350 KB／密文 ≤ 約 45 KB，含該塊的 docs 子集）：`{part, by_alias:{alias: {sec, compare, flags}}, docs, doc_no}`。
  - `sec.sync|change|ident|device|alarm|ff = {rows: [[欄位, 值, lvl, 來源字串]]}`（AMS DB 補充）。
  - `sec.dcdas|terminal|instlist|eomr = {entries: [{h, lvl, src, rule, d?, note?, rows: [[欄位, 值, 狀態?]]}]}`：一筆 entry＝一份文件的一列/一頁（dcdas：控制器的一個類比輸入通道，lvl `ctrl`，rows＝控制器、I/O 模組、通道、訊號名、裝置位號 (DeviceTag)、輸入型式、HART 通道、`DCS AI 量程 (Low/High Value)`、訊號說明、signal-atlas 深連結；`rule`＝位號對照方式）；entry 內各欄共用 `src`；`d` 指向 docs（分塊自帶）；狀態 `near|mismatch|unit_mismatch|unit_unknown`（量程欄與 DCS 基準比對）或 `warn`（EOMR 序號與 AMS 不符；dcdas：同位號另一通道的量程與基準通道不同）。
  - 文件參照字串：產生器可給 `ref`（完整顯示字串），否則 `doc_id-rev`。DCS 端子表 xlsx 本身沒有版次字母（CoverSheet「Revision」欄未隨 IO Rev 更新）：字母取自同 IO Rev 的 PDF 檔名時寫 `HT1-1-IMI01-A0001-H（推定）`；找不到對應 PDF 時寫 `HT3-1-IMI01-A0001（IO Rev3，版次字母不明）`。同 IO Rev 多份 xlsx 取修改時間最新者。
  - 儀器清單 HRSG xls 的 RANGE 若為數值儲存格（原文無單位，「0~」與單位只來自整欄數字格式）：`設計量程（原文）` 寫原數值並說明格式，另加 `量程單位來源＝儲存格數字格式（推定）`；比對一律 `unit_unknown`。
  - `sec.docindex = {rows: [[類別, "文件-版次 · p.頁", lvl, 來源字串, {rule, d?}]]}`。
  - `sec.hmi = {rows: [[欄位, 值, "hmi", 來源字串, extra]]}`＝圖控 HMI 畫面位置（每組畫面 4 列；見下方「v5（docs/db 站：圖控 HMI 畫面位置）」）。
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
- `02.json.valve = {sheets, fields:[[卡片標籤, xlsx 欄名]], index:{compact 位號: [sid, 列]}, by_alias:{alias: [[sid, 列, 機組, 對照方式, 定位器比對 ok|mismatch|absent|unknown, 比對說明, 備註]]}, list_name, list_url}`。`index` 收清單位號本身與依「涵蓋機組」展開的位號（Gxx→G11…G32、Cx0→C10…、`G11/G12…` 斜線列舉）；鍵＝`IX.compact`。
- 對照：閥位號（展開後）＝04 位號索引任一鍵，或 GT 閥 `<機組>_90<Legacy/GE Tag>`；再套 `<CARDWORK>/pneuvalve_xwalk.json`（`drop`／`add`／`note`；2026-10-02 多代理逐筆驗證的結果，另存 fill26/pneuvalve_ams_xwalk.json）。定位器比對＝清單「Positioner 定位器」欄與 AMS 製造商＋型號比廠牌家族（`POS_FAM`）。
- 摘要組 `{"key":"valve","valve":true,label,note}`（`extract_db.summary_spec`，排在 `dev` 之後；舊 02 缺的話產生器補上）：`by_alias` 有此 alias 才渲染（否則整組不出現），`fillValveGroup` 懶載 57／58，每個清單列一塊 `.sum-sig`（標頭：清單位號、本卡機組、⚠ 定位器廠牌不符、兩讀 n 格、「在 57_… 開啟此列」），欄位逐格帶 `src`（文件連結開雲端檔案；兩讀在「文件資訊」列 A／B）。
- 查詢：`lookup()` 在位號索引只有模糊對應（`contain`／`suggest`／`none`）時先查 `valve.index`：輸入帶機組且該機組恰有一台 AMS 設備 → 顯示那台（狀態列「是氣動閥清單位號，對應 AMS 設備 …」）；否則 `res.valve` → `renderValveOnly`（閥卡＋同一閥在 AMS 的設備 chips；狀態列不標紅）。`go()` 與頂列搜尋 `onEnter` 同樣不讓模糊對應蓋掉清單位號。
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
| 1 | `tools/db/hmi_shots.py` | `CARDWORK/hmi_shots/`（155 個 `.webp` ＋ `index.json`，6.8 MB） | `.cim` 的 `ThumbNail` 串流＝設計時全畫面 EMF → PowerShell GDI+ `System.Drawing.Imaging.Metafile` 渲染成 1920×1080 → **在原生尺寸塗平堆疊 chrome** → 寬 1280 WebP。**全畫面一律以裝置矩形 (0,0,1920,1080) 當畫布**（不可用 EMF 的 `szlDevice`：156 張裡有 3 張不是 1920×1080），所以影像像素 × 1.5 ＝ 畫面裝置像素。PIL 直接開 `.emf` 不可用（走 GDI `PlayEnhMetaFile`，不懂 EMF+ 記錄，畫出來近乎空白）。**塗平堆疊 chrome**（縮圖「殘影」的成因是 CimEdit 存設計時快照時把所有分支／所有機組變體的子物件全部畫出來、執行時才用 visibility 動畫只亮其中一組——導覽面板實測過繪 19~25 倍，**不是渲染器的 bug**）：在 GDI+ 輸出之後、PIL 縮圖之前，把四個原生裝置座標矩形 `nav (0,207,213,1048)`／`loading (0,182,334,205)`／`menubar (213,136,370,177)`／`banner (224,0,450,133)` 用該區逐張（`nav` 單一 probe、其餘逐列 donor）取樣到的背景色塗平，**不裁切**（裁切會動到座標基準，而 `hmi.json` 的 744 筆全畫面標記沒有一筆落在這些區塊內）。閘門：畫布必須真的是 `[0,0,1920,1080]` 且 `--screen` 未改，再逐張數重疊字串配對數——`nav` ≥ 1000 才遮（面板型與沒有 chrome 的樣板頁自動排除，不寫白名單）、`banner` 另需 ≥ 20。逐張夾限：`nav` 底緣由 `MASK_VOCAB`（畫面自己的按鈕 `####`／`MASTER RESET`／`DIAGNOSTIC RESET`）落在 **`MASK_NAV_FLOOR`＝900 以下**的命中往上夾 7px（樓地板以上的命中一律忽略並在結尾印警告——照它夾會把導覽樹整片留著，甚至讓矩形退化到整個不遮）、`banner` 右緣由第一個 `left ≥ 430` 的非 `###` 字串往左夾 2px；`nav` 的取樣 probe 固定在 `y 840~893`（＝樓地板 900 − 夾限留白 7，也就是最低可能的夾限線）＝一定在夾限線以上，`nav` 取樣不可信（眾數佔比 < 0.30 或偏離預設 > 24）時該矩形**整個不塗**（版型變了就該不塗，不是把灰塊放在可能錯的位置）；其餘三個矩形是逐列取樣，單列不可信只有那一列退回預設色（差一列只差 1px，且矩形位置另有配對數門檻把關）。`--no-mask` 完全不遮（回溯比對用）。以 2026-10-03 語料：遮 109 張、不遮 47 張（3 張樣板頁配對數 0 ＋ 44 張 faceplate），`nav` 夾限 46 張（13 張→925、33 張→958~972）、`banner` 夾限 7 張、取樣退回 0 張。`index.json` 每筆因此多兩個欄位：**`masked`**＝真的塗掉的**具名**矩形 `{"nav":[l,t,r,b],"loading":…,"menubar":…,"banner":…}`（沒遮就是 `{}`；不可寫成位置陣列——矩形組合會變，`masked[0]` 會把 `loading` 誤讀成 `nav`）、**`mask_metrics`**＝`{nav_pairs, nav_strings, banner_pairs, banner_strings, nav_bottom, nav_vocab_ignored}`（沒過門檻的畫面也留配對數，日後要調門檻不必重跑整套分析）。`masked` 每筆都有，`mask_metrics` 的**鍵是條件性的、一律用 `.get()` 讀**：只有評估過遮罩的全畫面型才有這個鍵（2026-10-03 語料 112/156，faceplate 沒有），`banner_*`／`nav_bottom` 只在過了 `nav` 門檻的 109 張，`nav_vocab_ignored` 只在真有命中被樓地板忽略時才寫（今天 0 張）。 |
| 2 | `tools/db/hmi_nav.py` | `CARDWORK/hmi_nav.json`（248 筆） | 每個根目錄畫面的**逐列對齊**選單路徑：`nav`／`units`／`variables`／`nav_src` 四個陣列同序（`navigation/CIMNavigationMenuItemsStd.csv` 的原始列序，不去重），另有 `title_en`／`label`／`caption_en`／`title_src`／`title_conf`／`captions`／`alt_names`／`file_aliases`＋`alias_tier`（`case`＝定讞／`norm`＝很可能／`loose`＝推論）。`title_zh` 全部 `null`：原廠語言檔只宣告西班牙／日／法文，473 個 `.cim` 的字串 0 個含中文（LanguageMapper.clm 裡像中文的漢字是日文）。 |
| 3 | `tools/db/hmi_index.py` | `CARDWORK/hmi.json`（354 KB） | `{by_tag:{位號:[{screen, unit, route, ref, x, y, w, h}]}, screens:{檔名:{title_en, title_zh, nav, units, img, img_w, img_h, img_canvas, w, h}}, stats}`。讀 1＋2 的輸出與 `paths.AMS_SQLITE`（現行 AMS 位號集合）、`paths.DCDAS_INDEX`。 |

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
  每列 `extra` 都帶 `{s: 畫面檔名, g: 組序}` 供前端分組；**第一列**另帶 `nav`／`img`（該畫面有沒有設計時影像）／`marks`／`routes`／`unit`／`ref`。
- `marks: [[中心 x, 中心 y, 框寬, 框高]]`（0~1 比例、左上原點、已去重）：框寬／高為 **0 時只標點不畫框**（直線、文字錨點）；
  同一畫面同時有「有框」與「線狀」標記時只留有框的。**`marks[0]` 就是「所在位置」那列文字描述的那處**（面積最大者排前面），
  前端照陣列順序標 ①②③——同一位號的兩處常常只差 1~2% 畫面高（放大圖上約 11 px），沒有編號使用者看不出有兩個圈、也對不上「另有 N 處」。
- **影像**：有設備對應到、而且 `.cim` 內含 ThumbNail 的畫面，縮圖包成 `docs/db/data/card/hmi/<畫面名去掉 .cim>.json ＝ {w, h, mime:"image/webp", b64}`，
  **走既有 `*.json` 加密路徑**（`encrypt_data.py` 的 `rglob("*.json")`），沒有第二套加密。寫之前先整個清掉 `card/hmi/`，掉出覆蓋範圍的畫面不會留下孤兒密文。
- `card/index.json` 新增 `hmi = {screens:{檔名:{title, en, zh?, caption?, nav, img, file?, w?, h?, bytes?, rows}}, files:[…], bytes, design:[28800,16200], canvas:[1920,1080], note, stats}`。
  `stats` 除了覆蓋率，另有 `screens_total`（建索引的根目錄畫面數 248）／`screens_all`（遞迴全部 473）／`excluded`（225）／`excluded_scanned`／`excluded_tag_hits`／`excluded_ff_hits`
  ——卡片「查無」那句要一次講完掃描範圍，不然同一張卡會同時出現 248 與 473 兩個數字、看起來自相矛盾。
  `files` 是 `card/hmi/*.json` 的清單——`tools/verify_encrypted.py` 以它認得這些密文不是孤兒；`extract_db.data_build` 的雜湊也涵蓋 `card/**/*.json`
  （兩邊都以 **posix 相對路徑**排序，Windows 的 `\` 與 posix 的 `/` 排序不同，否則 build 會對不起來）。
- `index.searched.hmi[0]`＝把畫面檔目錄當一份「文件」描述（`doc_id: hmi-screens`、`folder: AMS/Screens（圖控畫面檔目錄，唯讀）`、`why` 含覆蓋率）；沒有 Drive 連結、不進 `index.docs`。
- 來源分級新增 **`lvl: "hmi"`（標籤「圖控」，青色 `--src-hmi`）**：`extract_db.SRC_DEFS`／`build_card_aux.SRC_DEFS`／`U.SRC_LVLS`／`.lvl-hmi` 四處要一致，缺一個前端會靜默退回 `raw`。

### 前端（card.js `fillHmi`／`hmiShot`／`hmiFrame`／`openHmiLightbox`；core.js `D.loadHmiImage`；app.css）

- 摘要組 `{"key":"hmi","kind":"hmi","collapsed":true,"after_stock":true}`（排在「文件全文檢索」之後）與附加區段 `{"key":"hmi","kind":"hmi"}`
  （排在 `docsearch` 之後）**都有縮圖與標記**（2026-10-03：使用者回報在摘要看不到圖控畫面，摘要組從「只列名稱＋導覽路徑」改成也顯示縮圖）。
  兩者都走 `fillHmi(sec, ix, grid, mode, inSum)`；第 5 個參數**只決定版面**，不再決定載不載圖（原本的 `withImages` 已經沒有 `false` 的呼叫點）：
  - 摘要組（`inSum=true`）佔整列寬（`.sum-hmi { grid-column: 1 / -1 }`——漏了這一條就只佔兩欄格的左半、右半邊空著），
    有縮圖的畫面塊掛 `.sum-has-shot`，而 `.sum-hmi .hmi-list` 宣告 `container-type: inline-size; container-name: hmilist`：
    **容器 ≥ 1150px 時左欄四個欄位、右欄縮圖**（`@container hmilist`，看容器寬不是視窗寬；1280 筆電的容器是 1238px，成立）。
    斷點刻意不取 900：容器 900–1100（含 iPad 橫向 1024）時左欄只有 374–440px，`src-full` 的三欄 `.cf` 會把中文值切成 7–10 行，比上下排版更難讀。
    窄容器與沒有縮圖的畫面塊維持原本的「圖在上、欄位在下」；左欄比縮圖矮時下方留白（`align-self: start` 的必然代價，不要改成 stretch，否則 `.cfields` 會把高度攤給每一列）。
  - 附加區段（`inSum=false`）不掛 `.sum-has-shot`、不套容器查詢，維持整列寬的大圖（那裡縮圖是主角）。
- **影像延後載入**：`hmiShot()` 只先建好 `.hmi-frame.loading` 佔位，真正的 `D.loadHmiImage` 由 `whenDetailsOpen(grid, …)`
  在祖先 `<details>`（摘要組自己／`.cq-more`）**全部展開後**才跑一次。兩個區段都是「卡片一渲染就填好」（不是展開才填），
  不延後的話只要位號有圖控畫面，每次開卡都會白抓 70–105 KB／張的密文。代價：`beforeprint` 強制展開時 `load` 來不及完成，
  沒展開過的組第一次列印只會印到佔位框（與「參數現值」同一個已知取捨；`@media print` 的佔位文字會說明原因）。
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
- 無影像的畫面只顯示名稱與路徑，並註明「此畫面檔未內含設計時影像（.cim 沒有 ThumbNail 串流）」。
- 查無：一次講完掃描範圍（取 `index.hmi.stats`）——FF 設備（`flags.ff`）寫「查無（FF 訊號不在控制器 I/O 索引，位號字串也不出現在任何圖控畫面檔；已掃 248 個操作員畫面，另 225 個子目錄元件面板／函式庫也掃過字串（共 473 個 .cim））」，
  其餘寫「查無（已掃 248 個操作員畫面，…（共 473 個 .cim）：這些畫面都沒有引用此位號）」。
- `nav_all`：前端以 `.hmi-allnav`「（此畫面全部選單列）」顯示在導覽路徑旁（不只寫在來源字串裡）。`dcdas` 路線帶出 `unit` 之後目前實測為 0 組，前端仍保留這條分支。
- 手機（`.cq-body.narrow`）標記縮成 20px、縮圖滿寬、`.hmi-f .cf-v` 縮一級字；`.hmi-f .cf-v` 另設 `word-break: normal; overflow-wrap: break-word`
  （`.cf-v` 預設的 `word-break: break-word` 等於 `overflow-wrap: anywhere`，會把位號在 token 中間切成 `…LAB22BF001_X` / `Q01`）。
  列印時 `.hmi-screen` 不跨頁、標記以 `print-color-adjust: exact` 印出、放大層由 `.modal` 的列印規則隱藏。

### 已知限制（誠實標註）

- **FF 設備（351 台）完全無法對應**：FF 位號不出現在任何 `.cim` 字串裡（根目錄 248 個與子目錄 225 個都掃過，見上面「掃描範圍」）；這不是解析漏抓。
- **23 個引用到 AMS 位號的畫面檔沒有 ThumbNail**（量最大的是 `HPOT_HP_OT_Temp_UX.cim` 158 筆、`HRSG_Hot_Reheat_UX.cim` 123、`HRSG_LP_Group_UX.cim` 94、`HRSG_LP_Common_UX.cim` 78），只能顯示畫面名稱與導覽路徑。
- **來源裡沒有中文畫面名**，`title_zh` 一律 `null`；要中文只能另建人工對照表。
- `sec.hmi` 的 `ref` 取自該組排序後第一個命中物件，**不保證屬於某一個座標**（同組多個矩形共用一個 `ref`），不要當成「這個位置的物件屬性」。
  `ref` 裡仍可能留著 `{UNIT1_NO}`、`{Unit_NO}` 這類**未代入的畫面變數**——那是 `.cim` 裡的原文參照字串（設計行為，不是壞資料）。
- `unit` 欄＝「用哪一列選單開這張畫面」，不是儀器所屬機組（`BOP_Blowdown_Recovery_System.cim`、`Plant_Overview_UX.cim` 本來就同時畫兩部機）；
  69 台因此在同一張畫面列兩組、紅框完全相同，卡片以「以選單機組 X 開啟」表達這件事。
- 「所在位置」只描述 `marks[0]` 一處；其餘處只能靠圖上的 ②③ 對照，文字不會逐處列座標。

## 加密與封裝（tools/encrypt_data.py；兩站共用）

GitHub Pages 是公開靜態站，`docs/*/data` 一律以**密文**發布，只有 `data/meta.json` 是明文；瀏覽器在員工代號登入後再輸入**密語**解密（與 momobacon-wq/signal-atlas 同一套作法）。

- 金鑰：`PBKDF2-HMAC-SHA256(密語, salt, 200000)` → 32 bytes（AES-256-GCM）。密語只存建置機器 `%LOCALAPPDATA%\AMS\web.key` 第 1 行（或環境變數 `AMS_WEB_KEY`／`AMS_WEB_KEY_FILE`），**永不進 repo**。
- salt（16 bytes）存 key 檔第 2 行，**固定不隨建置改變**（salt 本來就公開在 meta.json；固定後「記住此裝置」的金鑰在資料重建後仍可用，且 docs/ 與 docs/db/ 同源共用同一把）。`--fresh-salt` 或改密語＝輪替，兩站都要重新加密。
- 每個資料檔（`manifest.json`、`sheets/*.json`、`card/*.json`）存成 `<rel>.bin` ＝ `12-byte 隨機 IV ‖ AES-GCM(gzip(JSON UTF-8, level 6, mtime 0))`（含 16-byte tag，WebCrypto 版面），**AAD＝相對路徑 rel（不含 .bin）**，密文不能搬到別的路徑。
- `meta.json` ＝ `{"enc":1,"gzip":1,"build":<manifest.build>,"kdf":{"name":"PBKDF2","hash":"SHA-256","iter":200000,"salt":<b64>},"check":<b64 seal(key,"ams-ok",aad="check")>}`；`check` 只用來驗密語。
- `manifest.build` 仍以**明文**內容計算（IV 隨機，密文不可拿來算 hash）：產生器先算 build 寫 manifest → `encrypt_dir` → stamp。`tools/stamp_assets.py`／`extract_db.stamp` 在 `meta.json` 存在時從它取 build，並把 index.html 的 preload 改指 `data/meta.json`。db 站的 `extract_db.stamp` 另以 `<!-- ams-preload --> … <!-- /ams-preload -->` 標記整段重寫首訪 preload（第一行 meta.json，其後 `PRELOAD_DATA`＝manifest＋sheets/02、04、03 的 `.bin`，全部 `?v=<build>`，讓 600 KB 與登入閘門往返重疊；重複 stamp 不累加，舊版單行會自動遷移成區塊；`stamp_html()` 是純函式可單測）；主站 `stamp_assets.py` 維持只 preload meta。這些 `?v=` 都等於 build，已在 SW keep 清單內。
- 前端（core.js）：`D.loadMeta()` 與登入閘門並行；`meta.json` 404 或 `enc:0` → 明文模式（本機開發／mock）。加密模式下 `D.url` 檔名加 `.bin`、`D.fetchJSON` 收齊 bytes → `crypto.subtle.decrypt`（AAD＝path）→ `DecompressionStream('gzip')` → JSON；進度以密文 content-length 為分母（不再用 manifest bytes 估計）。`D.unlock()`：先試 `localStorage['ams.key']`（raw key base64，「記住此裝置」勾選才存；**不可用 `atlas.key`**，同源會與 signal-atlas 互踩），否則密語視窗；標頭「清除密語」＝ `D.forgetKey()`。`D.cryptoOK()` 不通過（舊瀏覽器／非 https）顯示說明。
- 指令：
  - `py tools/encrypt_data.py docs/data`、`py tools/encrypt_data.py docs/db/data`（明文 → 密文，原地，刪明文）；`--decrypt`（原地還原）；`--decrypt-to DIR`（另存明文副本）；`--dry-run`。
  - 產生器 `extract.py`／`extract_db.py` 結尾自動加密（`--no-encrypt` 只供本機測試，**不可 push**）；`extract_db.py`／`build_card_aux.py` 遇到已加密的輸出目錄會先原地解密。
  - `py tools/verify_encrypted.py`：重新以密語解開全部 `.bin`、確認沒有明文 `.json`、manifest 引用與檔案一一對應、以明文重算 build 並比對 meta／manifest／version.json／index.html、掃建置機器本機路徑、robots／noindex。**每次 push 前必須 exit 0**。
    本機路徑規則 `LOCAL_RE = Users[\\/]{1,2}bacon|/c/Users/|我的雲端硬碟|@@新機組`：**`{1,2}` 不可拿掉**——掃的是 JSON 文字，Windows 分隔符在裡面是兩個反斜線，
    舊版寫成 `Users[\\/]bacon` 對 JSON 內的 Windows 路徑整支失效（假陰性，`sheets/61.json` 就這樣帶著建置機家目錄出貨）。
    「其他電腦」刻意**不**列入：AMS 資料庫自己的工作站標籤叫「本廠其他電腦 (2024 以後)」（sheets 19／24／28），不是路徑。
    供料端同一份規則在 `tools/db/pneuvalve_site.py`：`scrub_local()`＝文件庫根 → 相對、家目錄 → `~`、其餘還帶本機痕跡的多層路徑 → **只剩檔名**，
    而且在 `read_xlsx()` 就剝（`cell_sources()` 讀的是未經 `clean()` 的原始列，只在 `clean()` 剝會漏）。注意 Python 字元集要寫 `[\\/]`，`[\/]` 只等於 `[/]`。
- `.gitignore` 擋掉 `docs/*/data/**/*.json`（meta.json 除外），明文永遠 commit 不進去；`docs/robots.txt` Disallow 全站、index.html `noindex, nofollow`。
- 誠實的限制：同一組密語所有同事共用，沒有個人撤銷；勾「記住此裝置」時 raw key 明文存在該瀏覽器 localStorage（嚴格 CSP、無行內 script 是它的防線）；員工代號閘門只是稽核紀錄，密語才是真正的保護。

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
