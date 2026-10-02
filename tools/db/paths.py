# -*- coding: utf-8 -*-
"""tools/db/paths.py — 重建流程所有「repo 外」路徑的唯一來源（sheets_*.py、sheets_index.py、build_workbook.py、rebuild.py --sqlite 都從這裡拿）。

每個值都可用環境變數覆寫；沒設就用預設（集中在 %LOCALAPPDATA%\\AMS，與 web.key、drive_map.json、cardwork 同處）。
  AMS_SQLITE        還原備份後倒出的 AmsDb.sqlite（tools/db/restore.sh 的輸出）          預設 %LOCALAPPDATA%\\AMS\\AmsDb.sqlite；
                    該檔不存在時退用文件庫的備份副本 <LIBRARY_ROOT>\\AMS\\20260912_AMS資料庫解析_工作檔\\AmsDb.sqlite（20260912、已 fix_blobs＋索引；只讀）
  AMS_CARDWORK      各產生器輸出 ams／terminal／instlist／eomr／docindex／docsearch.json   預設 %LOCALAPPDATA%\\AMS\\cardwork
  AMS_PDFTXT_CACHE  pdftotext 純文字快取（docmap_eomr／docmap_docindex 的 --cache）        預設 %LOCALAPPDATA%\\AMS\\pdftxt
  AMS_LIBRARY_ROOT  工程文件庫根目錄（Google 雲端硬碟桌面版的「@@新機組資料備份」）        預設 hst-docsearch config.json 的 library_root，否則 <家目錄>\\我的雲端硬碟\\@@新機組資料備份
  AMS_PREV_XLSX     前一版工作簿 20260910_AMS解析.xlsx（設備別名以 GUID 對應）             預設 <LIBRARY_ROOT>\\AMS\\20260910_AMS解析.xlsx
  AMS_BUILD_DIR     sheets_*.py 的 csv 傾印（out/）、sheets_cache.pkl、sheets_final.pkl、prev_templates.json  預設 %LOCALAPPDATA%\\AMS\\build
  AMS_DCDAS_INDEX   signal-atlas 控制器索引（build_card_aux --dcdas）                     預設 %LOCALAPPDATA%\\dcdas\\index.sqlite
  AMS_DRIVE_MAP     drive_map.py 的輸出                                                 預設 %LOCALAPPDATA%\\AMS\\drive_map.json
  AMS_HMI_SCREENS   圖控 HMI（GE CIMPLICITY／ActivePoint）畫面檔目錄（*.cim 與 navigation/ 設定；hmi_shots.py／hmi_nav.py 的輸入，唯讀不可修改）
                    預設 <LIBRARY_ROOT>\\AMS\\Screens
  AMS_PNEUVALVE_XLSX  全廠氣動閥清單 xlsx（試算表「興達全廠氣動閥LIST_v2.6」匯出；pneuvalve_site.py 的輸入）
                    預設 ~\\.claude\\skills\\notebooklm-batch5-Research\\data\\興達全廠氣動閥LIST_v2.6.xlsx

  py tools/db/paths.py     # 印出目前解析到的每個路徑與是否存在（接手新機器時先跑這個）

規則：模組層級只算路徑（AMS_SQLITE 預設值會檢查檔案是否存在）、不建目錄、不讀檔（import 不會有副作用）；需要目錄的呼叫端自己 os.makedirs。
"""
import json
import os

_LOCAL = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
AMS_LOCAL = os.path.join(_LOCAL, 'AMS')


def _env(name, default):
    v = os.environ.get(name)
    return os.path.normpath(v) if v else default


def _library_root_default():
    cfg = os.path.join(os.path.expanduser('~'), '.claude', 'skills', 'hst-docsearch', 'config.json')
    try:
        with open(cfg, encoding='utf-8') as f:
            root = json.load(f).get('library_root')
        if root:
            return os.path.normpath(root)
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), '我的雲端硬碟', '@@新機組資料備份')


def _fts_default():
    cfg = os.path.join(os.path.expanduser('~'), '.claude', 'skills', 'hst-docsearch', 'config.json')
    try:
        with open(cfg, encoding='utf-8') as f:
            p = json.load(f).get('fts_db')
        return os.path.normpath(p) if p else ''
    except Exception:
        return ''


LIBRARY_ROOT = _env('AMS_LIBRARY_ROOT', _library_root_default())


def _sqlite_default():
    local = os.path.join(AMS_LOCAL, 'AmsDb.sqlite')
    lib = os.path.join(LIBRARY_ROOT, 'AMS', '20260912_AMS資料庫解析_工作檔', 'AmsDb.sqlite')
    return lib if not os.path.exists(local) and os.path.exists(lib) else local


AMS_SQLITE = _env('AMS_SQLITE', _sqlite_default())
CARDWORK = _env('AMS_CARDWORK', os.path.join(AMS_LOCAL, 'cardwork'))
PDFTXT_CACHE = _env('AMS_PDFTXT_CACHE', os.path.join(AMS_LOCAL, 'pdftxt'))
PREV_XLSX = _env('AMS_PREV_XLSX', os.path.join(LIBRARY_ROOT, 'AMS', '20260910_AMS解析.xlsx'))
BUILD_DIR = _env('AMS_BUILD_DIR', os.path.join(AMS_LOCAL, 'build'))
DCDAS_INDEX = _env('AMS_DCDAS_INDEX', os.path.join(_LOCAL, 'dcdas', 'index.sqlite'))
DRIVE_MAP = _env('AMS_DRIVE_MAP', os.path.join(AMS_LOCAL, 'drive_map.json'))
FTS_DB = _env('AMS_FTS_DB', _fts_default())
PNEUVALVE_XLSX = _env('AMS_PNEUVALVE_XLSX', os.path.join(os.path.expanduser('~'), '.claude', 'skills', 'notebooklm-batch5-Research', 'data',
                                                        '興達全廠氣動閥LIST_v2.6.xlsx'))
HMI_SCREENS = _env('AMS_HMI_SCREENS', os.path.join(LIBRARY_ROOT, 'AMS', 'Screens'))  # 圖控 HMI 畫面檔（GE CIMPLICITY／ActivePoint .cim，唯讀）

# 衍生路徑（由上面推得，不另設環境變數）
SHEETS_OUT = os.path.join(BUILD_DIR, 'out')                       # sheets_*.py 直接執行時的 csv 傾印
SHEETS_CACHE = os.path.join(BUILD_DIR, 'sheets_cache.pkl')         # build_workbook：各模組 build(conn) 結果快取（刪掉即重算）
SHEETS_FINAL = os.path.join(BUILD_DIR, 'sheets_final.pkl')         # build_workbook 的後處理結果＝extract_db 的輸入
PREV_TEMPLATES_JSON = os.path.join(BUILD_DIR, 'prev_templates.json')  # sheets_templates：前簿 26_附錄_範本 的 JSON 快取
DOCSEARCH_JSON = os.path.join(CARDWORK, 'docsearch.json')          # docmap_docsearch 的輸出（build_card_aux --docsearch）
HMI_JSON = os.path.join(CARDWORK, 'hmi.json')                      # tools/db/hmi_index.py 的輸出（畫面／位號→座標索引）
HMI_SHOTS = os.path.join(CARDWORK, 'hmi_shots')                    # 畫面縮圖（ThumbNail EMF → png/webp）＋ index.json

ALL = [('AMS_SQLITE', AMS_SQLITE), ('CARDWORK', CARDWORK), ('PDFTXT_CACHE', PDFTXT_CACHE), ('LIBRARY_ROOT', LIBRARY_ROOT),
       ('PREV_XLSX', PREV_XLSX), ('BUILD_DIR', BUILD_DIR), ('SHEETS_CACHE', SHEETS_CACHE), ('SHEETS_FINAL', SHEETS_FINAL),
       ('DCDAS_INDEX', DCDAS_INDEX), ('DRIVE_MAP', DRIVE_MAP), ('DOCSEARCH_JSON', DOCSEARCH_JSON), ('FTS_DB', FTS_DB),
       ('PNEUVALVE_XLSX', PNEUVALVE_XLSX), ('HMI_SCREENS', HMI_SCREENS), ('HMI_JSON', HMI_JSON), ('HMI_SHOTS', HMI_SHOTS)]


def report():
    """每個路徑一行：名稱、是否存在、路徑（供 rebuild.py --sqlite 開頭與人工檢查）。"""
    lines = []
    for name, p in ALL:
        ok = bool(p) and os.path.exists(p)
        lines.append('  %-15s %s  %s' % (name, '有' if ok else '無', p or '（未設定）'))
    return '\n'.join(lines)


if __name__ == '__main__':
    print(report())
