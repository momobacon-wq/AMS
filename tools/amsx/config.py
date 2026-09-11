# -*- coding: utf-8 -*-
"""Per-sheet presentation hints taken from the analyst specs (scratchpad/specs/NN.md).

Only UI hints live here (facets, search columns, key columns, sidebar groups,
synthetic sections).  Everything that is *data* (values, links, styles,
geometry, bands, notes ...) is extracted generically from the workbook.
Column indexes are 0-based data-column indexes of the emitted table.
"""

GROUPS = ["總覽", "設備", "變更與查核", "事件與FF", "CMX", "統計與時間", "參數", "附錄"]

SHEET_GROUP = {
    "00": "總覽", "01": "總覽", "02": "總覽",
    "03": "設備", "04": "設備", "05": "設備", "06": "設備",
    "07": "變更與查核", "08": "變更與查核", "09": "變更與查核",
    "10": "事件與FF", "11": "事件與FF",
    "12": "CMX", "13": "CMX",
    "14": "統計與時間", "15": "統計與時間", "16": "統計與時間", "17": "統計與時間", "18": "統計與時間",
    "19": "參數", "20": "參數", "21": "參數", "22": "參數",
    "23": "附錄", "24": "附錄", "25": "附錄", "26": "附錄", "27": "附錄",
}

# ui hints per table sheet ------------------------------------------------
TABLE_UI = {
    "03": {"facets": [2, 5, 6, 7, 15, 18, 32, 74, 98, 103], "search_cols": None, "key_col": 0, "alias_col": 1,
           "facets_extra": [20, 9, 101, 59]},
    "04": {"facets": [0, 3, 7, 9, 14, 31], "facets_extra": [12, 22, 23], "key_col": 4, "alias_col": 5, "link_col": 6,
           "freeze_cols_narrow": 1},
    "05": {"facets": [2, 6], "facets_extra": [5], "search_cols": [0, 1, 3, 4], "key_col": 0, "alias_col": 4,
           "count_col": 7, "prio_col": 2, "tag_col": 3},
    "06": {"facets": [5, 8, 25, 26, 4, 16], "facets_extra": [21, 27], "search_cols": [0, 2, 6, 14, 17, 18, 19, 20],
           "key_col": 2, "alias_col": 0, "link_col": 1, "pre_cols": [3, 7, 15, 19]},
    "07": {"facets": [1, 2, 4, 9, 19, 20], "key_col": 0, "alias_col": 6, "tag_col": 5,
           "order": {"1": ["高", "中", "低", "資訊"]},
           "facet_options": {"20": ["未處理", "處理中", "需現場確認", "已確認-無誤", "已修正", "不需處理"]}},
    "08": {"facets": [5, 10, 16, 21, 22, 20], "facets_extra": [18, 19, 24, 28, 4], "key_col": 31, "alias_col": 2,
           "tag_col": 1, "presets": [{"label": "只看有意義", "col": 0, "nonempty": True},
                                     {"label": "MOC 審查", "col": 21, "eq": "是"}]},
    "09": {"facets": [8, 9, 10, 6], "facets_extra": [7, 11], "key_col": 0, "alias_col": 3, "tag_col": 5},
    "10": {"facets": [3, 1, 10, 15, 17, 29], "facets_extra": [2, 4, 16, 20, 11, 12], "key_col": 0, "alias_col": 7,
           "tag_col": 9, "sort_key": {"5": 6}},
    "11": {"facets": [3, 4, 6, 7, 10, 21], "facets_extra": [11, 19, 15, 18, 9], "key_col": 0, "alias_col": 1},
    "12": {"facets": [0, 4, 6, 8, 22], "facets_extra": [7, 14, 29, 19], "key_col": 3, "alias_col": 1, "cmx_col": 17},
    "13": {"facets": [3, 5, 8], "facets_extra": [11, 4], "key_col": 1, "alias_col": 12},
    "15": {"facets": [0, 1, 4], "search_cols": [2, 3, 17, 18], "summary_col": 2, "summary_values": ["小計", "總計"]},
    "19": {"facets": [4, 8], "key_col": 2, "alias_col": 5},
    "20": {"facets": [0, 6, 7, 4, 5], "key_col": 1},
    "21": {"facets": [2, 3, 9], "facets_extra": [10], "key_col": 4, "alias_col": 1, "group_col": 1,
           "group_zebra": "#F7F7F7", "search_cols": [4, 5, 0, 1, 6]},
    "22": {"facets": [2, 4, 5, 10, 3], "facets_extra": [14], "key_col": 7, "alias_col": 1, "group_col": 1,
           "group_zebra": "#F7F7F7", "search_cols": [7, 8, 9, 6, 0, 1, 11]},
    "23": {"facets": [0, 5], "key_col": 2, "group_col": 0},
    "25": {"facets": [0, 7, 13], "facets_extra": [14], "key_col": 9},
    "26": {"facets": [2, 3, 5], "key_col": 0},
    "27": {"facets": [0, 5, 7, 11], "key_col": 0},
}

# Columns dropped from the emitted table (0-based Excel columns), with reason.
DROP_COLS = {
    "21": {16: "Q 組 (hidden device-parity helper for the zebra CF $Q5=1) -> ui.group_zebra"},
    "22": {19: "T 組 (hidden device-parity helper for the zebra CF $T5=1) -> ui.group_zebra"},
}

# Grid sheets: synthetic sections (01 has no heading cells for the KPI/chart bands)
GRID_SECTIONS = {
    "01": [{"r": 4, "label": "KPI K1–K6"}, {"r": 9, "label": "KPI K7–K12"}, {"r": 13, "label": "圖表 C1–C6"},
           {"r": 71, "label": "重點發現"}, {"r": 83, "label": "待決事項"}],
}
# extra sections added to the generic detection (24 A111 is a bold 10pt sub-heading)
GRID_EXTRA_SECTIONS = {
    "24": [111],
}
