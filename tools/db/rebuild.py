# -*- coding: utf-8 -*-
"""一鍵重建 docs/db 站的查詢卡附加資料（README「文件全文檢索與 Google 雲端硬碟連結」那五步，按順序、任一步失敗就停）。

  py tools/db/rebuild.py                    # drive_map → 解密 → docsearch → build_card_aux --recompare → 戳記 → verify_encrypted
  py tools/db/rebuild.py --spec             # 多跑 patch_site_spec（extract_db 的 02／13 規格有改時）
  py tools/db/rebuild.py --skip-docsearch   # 不重跑 hst-docsearch（約 4 分鐘；沿用上次的 docsearch.json）
  py tools/db/rebuild.py --skip-hmi        # 不重跑圖控 HMI 三步（hmi_shots／hmi_nav／hmi_index）；沿用 cardwork 裡上次的 hmi.json／hmi_shots
  py tools/db/rebuild.py --skip-drive-map   # 不重讀 Google 雲端硬碟中繼資料
  py tools/db/rebuild.py --cardwork DIR     # 有各產生器輸出時做完整建置（build_card_aux DIR），而不是 --recompare
  py tools/db/rebuild.py --only-stamp       # 只改了前端程式：兩站重新戳記＋驗證
  py tools/db/rebuild.py --only-pneuvalve   # 只重新併入氣動閥清單（試算表改了）：pneuvalve_site → 戳記 → 驗證
                                            # （兩條完整路徑最後也都會跑 pneuvalve_site；--skip-pneuvalve 略過）
  py tools/db/rebuild.py --only-stamp --e2e # push 前關卡：戳記＋驗證＋端對端測試（tools/tests/run_e2e.py），結尾印 git status --short docs/
  py tools/db/rebuild.py --sqlite <AmsDb.sqlite> [--backup-date 2026-09-12]
                                            # 一條龍（拿到新的 .ams_bckup、tools/db/restore.sh 倒出 SQLite 之後）：
                                            #   build_workbook（Excel＋sheets_final.pkl）→ extract_db（明文）→ card_ams_extra／docmap_terminal／
                                            #   docmap_instlist／docmap_eomr／docmap_docindex（寫到 cardwork）→ docmap_docsearch
                                            #   → 圖控 HMI 三步（hmi_shots 縮圖 → hmi_nav 選單路徑 → hmi_index 位號座標）→ build_card_aux 完整
                                            #   （加密＋戳記）→ 兩站戳記 → verify_encrypted；路徑一律取自 tools/db/paths.py（環境變數可覆寫），開頭先印出來

任何一步失敗：若資料仍是明文，先原地加密回去（不留明文在 docs/ 底下），再以非 0 結束；結尾一定跑 verify_encrypted（加 --e2e 再跑 run_e2e），0 錯誤才可 push。
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PY = sys.executable
DATA = os.path.join('docs', 'db', 'data')
sys.path.insert(0, HERE)
import paths  # noqa: E402  （tools/db/paths.py：repo 外路徑的唯一來源）


def run(label, *cmd):
    t0 = time.time()
    print('\n==> %s\n    %s' % (label, ' '.join(cmd)), flush=True)
    # 子程序一律以 UTF-8 輸出：Windows 主控台預設 cp950，產生器的中文訊息（例 pneuvalve_site 的 '↔'）會在 print 時
    # 丟 UnicodeEncodeError，而那是在加密之後、戳記之前，會留下 index.html 與資料 build 不一致
    r = subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    print('    (%.0f s, exit %d)' % (time.time() - t0, r.returncode), flush=True)
    if r.returncode != 0:
        raise SystemExit('rebuild 中止於「%s」（exit %d）' % (label, r.returncode))


def is_plaintext():
    return os.path.exists(os.path.join(ROOT, DATA, 'manifest.json'))


def stamp_both():
    run('主站戳記（stamp_assets）', PY, os.path.join('tools', 'stamp_assets.py'), 'docs')
    run('db 站戳記（extract_db.stamp）', PY, '-c', "import sys; sys.path.insert(0, 'tools/db'); import extract_db; extract_db.stamp('docs/db', 'docs/assets')")


def verify_and_finish(a, t0, label):
    """收尾：verify_encrypted →（--e2e）run_e2e → 印 git status --short docs/。任一步非 0 就以非 0 結束（run 會 raise SystemExit）。"""
    run('驗證（verify_encrypted）', PY, os.path.join('tools', 'verify_encrypted.py'))
    if a.e2e:
        run('端對端測試（run_e2e：mock 登入伺服器＋Playwright）', PY, os.path.join('tools', 'tests', 'run_e2e.py'))
    print('\nrebuild 完成（%s），%.0f s；docs/ 變更如下，確認後即可 push：' % (label, time.time() - t0), flush=True)
    subprocess.run(['git', 'status', '--short', 'docs/'], cwd=ROOT)


PNEU = '氣動閥清單（pneuvalve_site：%s → 57～61 分頁、查詢卡「氣動閥」組；自行解密／加密）'

def hmi_flags(a):
    """build_card_aux 的圖控旗標：cardwork 有 hmi.json 就明指路徑與縮圖目錄；連 hmi.json 都沒有才 --no-hmi
    （缺檔又不給 --no-hmi 時 build_card_aux 會以非 0 結束，rebuild 跟著中止並走加密回滾）。"""
    if os.path.exists(paths.HMI_JSON):
        return ['--hmi', paths.HMI_JSON, '--hmi-shots', paths.HMI_SHOTS]
    print('    （cardwork 沒有 hmi.json → build_card_aux 走 --no-hmi：查詢卡不會有「圖控 HMI 畫面位置」）', flush=True)
    return ['--no-hmi']


def run_hmi(a):
    """圖控 HMI 三步，順序固定：縮圖（hmi_shots）→ 選單路徑／標題（hmi_nav）→ 位號座標索引（hmi_index 會讀前兩者的輸出）。
    **執行時截圖的對應表不在這裡**：`tools/db/hmi_runtime_map.py` 是離線工具（唯一需要 rapidocr），輸出 `tools/db/hmi_runtime_map.json`
    已 commit 進 repo，hmi_shots 只讀它；只有使用者重拍／補拍畫面（`Screens\\圖控\\*.xlsx` 換過）時才要手動重跑那支。
    輸入是唯讀的 .cim 畫面檔目錄 paths.HMI_SCREENS（不修改），輸出全在 cardwork；必須在 build_card_aux 之前跑完。"""
    if a.skip_hmi:
        print('\n== 略過圖控 HMI（--skip-hmi）：沿用 cardwork 裡上次的 hmi.json／hmi_shots ==', flush=True); return
    if not os.path.isdir(paths.HMI_SCREENS):
        raise SystemExit('沒有圖控畫面檔目錄 %s（設 AMS_HMI_SCREENS，或用 --skip-hmi）' % paths.HMI_SCREENS)
    db = os.path.join('tools', 'db')
    run('圖控畫面影像（hmi_shots：執行時截圖〔hmi_runtime_map.json〕＋.cim 的 ThumbNail EMF → %s，約 70 秒）' % paths.HMI_SHOTS,
        PY, os.path.join(db, 'hmi_shots.py'))
    run('圖控畫面選單路徑與標題（hmi_nav → cardwork/hmi_nav.json）', PY, os.path.join(db, 'hmi_nav.py'))
    run('圖控位號定位索引（hmi_index → %s）' % paths.HMI_JSON, PY, os.path.join(db, 'hmi_index.py'))


def run_pneuvalve(a):
    """必須在 extract_db／build_card_aux／patch_site_spec 之後（它們會清掉 sheets/ 或重寫 02 摘要）；資料加密中也可直接跑。"""
    if a.skip_pneuvalve:
        print('\n== 略過氣動閥清單（--skip-pneuvalve）：57～61 分頁與查詢卡氣動閥組不會出現 ==', flush=True); return
    run(PNEU % paths.PNEUVALVE_XLSX, PY, os.path.join('tools', 'db', 'pneuvalve_site.py'), DATA)


def rebuild_from_sqlite(a, t0):
    """--sqlite：README「重建」步驟表的全部步驟。每步先印輸入／輸出路徑；任一步失敗就停（明文會先加密回去）。"""
    sqlite = os.path.abspath(a.sqlite)
    if not os.path.exists(sqlite):
        raise SystemExit('沒有 %s（tools/db/restore.sh 的輸出）' % sqlite)
    os.environ['AMS_SQLITE'] = sqlite  # build_workbook／sheets_*.py（子程序）由 paths.AMS_SQLITE 讀
    import importlib; importlib.reload(paths)  # 讓本程序的 paths.AMS_SQLITE 也跟著換
    cardwork, lib, cache = paths.CARDWORK, paths.LIBRARY_ROOT, paths.PDFTXT_CACHE
    print('路徑（tools/db/paths.py；環境變數可覆寫）：\n' + paths.report(), flush=True)
    for p in (cardwork, os.path.join(cache, 'eomr'), os.path.join(cache, 'docindex'), paths.BUILD_DIR):
        os.makedirs(p, exist_ok=True)
    if not os.path.isdir(lib):
        raise SystemExit('沒有工程文件庫根目錄 %s（設 AMS_LIBRARY_ROOT）' % lib)
    sheets = os.path.join(DATA, 'sheets')
    db = os.path.join('tools', 'db')
    if not a.skip_drive_map:
        run('Google 雲端硬碟對照（drive_map）→ %s' % paths.DRIVE_MAP, PY, os.path.join(db, 'drive_map.py'), '--out', paths.DRIVE_MAP)
    if not a.skip_workbook:
        xl = os.path.join(paths.BUILD_DIR, 'AMS資料庫解析.xlsx'); xd = os.path.join(paths.BUILD_DIR, 'AMS資料庫解析_明細.xlsx')
        run('Excel 工作簿（build_workbook：%s → %s、%s、%s；order.json 已在 repo，make_order 不必重跑；約 10 分鐘）' % (sqlite, xl, xd, paths.SHEETS_FINAL),
            PY, os.path.join(db, 'build_workbook.py'), os.path.join(db, 'order.json'), xl, xd, '120000')
    if not os.path.exists(paths.SHEETS_FINAL):
        raise SystemExit('沒有 %s（build_workbook 的輸出）' % paths.SHEETS_FINAL)
    try:
        run('網站資料（extract_db：%s → %s，明文，稍後由 build_card_aux 加密）' % (paths.SHEETS_FINAL, DATA), PY, os.path.join(db, 'extract_db.py'), paths.SHEETS_FINAL, DATA, '--no-encrypt')
        run('AMS DB 補充（card_ams_extra → %s/ams.json）' % cardwork, PY, os.path.join(db, 'card_ams_extra.py'), sqlite, os.path.join(cardwork, 'ams.json'), a.backup_date, '--sheets', sheets)
        run('DCS 端子表（docmap_terminal → terminal.json）', PY, os.path.join(db, 'docmap_terminal.py'), lib, sheets, os.path.join(cardwork, 'terminal.json'))
        run('儀器清單（docmap_instlist → instlist.json）', PY, os.path.join(db, 'docmap_instlist.py'), '--root', lib, '--sheets', sheets, '--out', os.path.join(cardwork, 'instlist.json'))
        run('出廠證書 EOMR（docmap_eomr → eomr.json；pdftotext 快取 %s）' % os.path.join(cache, 'eomr'), PY, os.path.join(db, 'docmap_eomr.py'), '--root', lib, '--sheets', sheets,
            '--sqlite', sqlite, '--cache', os.path.join(cache, 'eomr'), '--out', os.path.join(cardwork, 'eomr.json'))
        run('文件索引（docmap_docindex → docindex.json；pdftotext 快取 %s）' % os.path.join(cache, 'docindex'), PY, os.path.join(db, 'docmap_docindex.py'), '--root', lib,
            '--sheets03', os.path.join(sheets, '03.json'), '--cache', os.path.join(cache, 'docindex'), '--out', os.path.join(cardwork, 'docindex.json'))
        if not a.skip_docsearch:
            run('文件全文檢索（docmap_docsearch → %s，約 4 分鐘）' % paths.DOCSEARCH_JSON, PY, os.path.join(db, 'docmap_docsearch.py'), '--data', DATA, '--out', paths.DOCSEARCH_JSON,
                '--library', lib, '--drive-map', paths.DRIVE_MAP)
        run_hmi(a)
        run('查詢卡附加資料（build_card_aux 完整：%s → card/*.json，加密、戳記）' % cardwork, PY, os.path.join(db, 'build_card_aux.py'), cardwork, DATA,
            '--dcdas', paths.DCDAS_INDEX, '--docsearch', paths.DOCSEARCH_JSON, '--drive-map', paths.DRIVE_MAP, *hmi_flags(a))
        run_pneuvalve(a)
    except BaseException:
        if is_plaintext():
            print('\n!! 建置失敗，資料仍是明文 → 先原地加密回去（不留明文）', flush=True)
            subprocess.run([PY, os.path.join('tools', 'encrypt_data.py'), DATA], cwd=ROOT)
        raise
    if is_plaintext():
        raise SystemExit('build_card_aux 結束後資料仍是明文（應已自動加密）——請檢查')
    stamp_both()
    verify_and_finish(a, t0, '一條龍（--sqlite）')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--spec', action='store_true', help='套用 extract_db 的 02／13 規格（patch_site_spec）')
    ap.add_argument('--skip-docsearch', action='store_true')
    ap.add_argument('--skip-hmi', action='store_true', help='略過圖控 HMI 三步（hmi_shots／hmi_nav／hmi_index）；沿用 cardwork 裡上次的 hmi.json／hmi_shots')
    ap.add_argument('--skip-drive-map', action='store_true')
    ap.add_argument('--cardwork', metavar='DIR', help='各產生器輸出目錄：做完整 build_card_aux 而非 --recompare')
    ap.add_argument('--only-stamp', action='store_true', help='只重新戳記兩站並驗證（前端程式有改、資料沒改）')
    ap.add_argument('--e2e', action='store_true', help='verify_encrypted 之後再跑 tools/tests/run_e2e.py（push 前關卡）')
    ap.add_argument('--sqlite', metavar='AmsDb.sqlite', help='一條龍：從 restore.sh 倒出的 SQLite 重做 Excel、網站資料、cardwork 與查詢卡附加資料')
    ap.add_argument('--backup-date', default='2026-09-12', help='備份日（card_ams_extra 的「距備份 N 天」基準；--sqlite 用）')
    ap.add_argument('--skip-workbook', action='store_true', help='--sqlite 時略過 build_workbook（沿用 paths.SHEETS_FINAL）')
    ap.add_argument('--skip-pneuvalve', action='store_true', help='略過氣動閥清單（pneuvalve_site.py；57～61 分頁與查詢卡氣動閥組會消失）')
    ap.add_argument('--only-pneuvalve', action='store_true', help='只重新併入氣動閥清單（試算表改了、AMS 資料沒變）→ 戳記 → 驗證')
    a = ap.parse_args()
    t0 = time.time()
    if a.only_pneuvalve:
        try:
            run_pneuvalve(a)
        except BaseException:
            if is_plaintext():
                subprocess.run([PY, os.path.join('tools', 'encrypt_data.py'), DATA], cwd=ROOT)
            raise
        stamp_both()
        verify_and_finish(a, t0, '氣動閥清單'); return
    if a.only_stamp:
        stamp_both()
        verify_and_finish(a, t0, '只戳記'); return
    if a.sqlite:
        rebuild_from_sqlite(a, t0); return
    if not a.skip_drive_map:
        run('Google 雲端硬碟對照（drive_map）', PY, os.path.join('tools', 'db', 'drive_map.py'))
    try:
        if not is_plaintext():
            run('解密 docs/db/data', PY, os.path.join('tools', 'encrypt_data.py'), DATA, '--decrypt')
        if not a.skip_docsearch:
            run('文件全文檢索（docmap_docsearch，約 4 分鐘）', PY, os.path.join('tools', 'db', 'docmap_docsearch.py'), '--data', DATA)
        if a.spec:
            run('套用站台規格（patch_site_spec）', PY, os.path.join('tools', 'db', 'patch_site_spec.py'), DATA)
        run_hmi(a)
        hmi = hmi_flags(a)
        if a.cardwork:
            run('查詢卡附加資料（build_card_aux 完整）', PY, os.path.join('tools', 'db', 'build_card_aux.py'), a.cardwork, DATA, *hmi)
        else:
            run('查詢卡附加資料（build_card_aux --recompare：併入 docsearch、圖控畫面位置、Drive 連結、重算比對、加密、戳記）',
                PY, os.path.join('tools', 'db', 'build_card_aux.py'), '--recompare', DATA, *hmi)
        run_pneuvalve(a)
    except BaseException:
        if is_plaintext():
            print('\n!! 建置失敗，資料仍是明文 → 先原地加密回去（不留明文）', flush=True)
            subprocess.run([PY, os.path.join('tools', 'encrypt_data.py'), DATA], cwd=ROOT)
        raise
    if is_plaintext():
        raise SystemExit('build_card_aux 結束後資料仍是明文（應已自動加密）——請檢查')
    stamp_both()
    verify_and_finish(a, t0, '完整')


if __name__ == '__main__':
    main()
