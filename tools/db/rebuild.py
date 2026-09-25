# -*- coding: utf-8 -*-
"""一鍵重建 docs/db 站的查詢卡附加資料（README「文件全文檢索與 Google 雲端硬碟連結」那五步，按順序、任一步失敗就停）。

  py tools/db/rebuild.py                    # drive_map → 解密 → docsearch → build_card_aux --recompare → 戳記 → verify_encrypted
  py tools/db/rebuild.py --spec             # 多跑 patch_site_spec（extract_db 的 02／13 規格有改時）
  py tools/db/rebuild.py --skip-docsearch   # 不重跑 hst-docsearch（約 4 分鐘；沿用上次的 docsearch.json）
  py tools/db/rebuild.py --skip-drive-map   # 不重讀 Google 雲端硬碟中繼資料
  py tools/db/rebuild.py --cardwork DIR     # 有各產生器輸出時做完整建置（build_card_aux DIR），而不是 --recompare
  py tools/db/rebuild.py --only-stamp       # 只改了前端程式：兩站重新戳記＋驗證

任何一步失敗：若資料仍是明文，先原地加密回去（不留明文在 docs/ 底下），再以非 0 結束；結尾一定跑 verify_encrypted，0 錯誤才可 push。
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


def run(label, *cmd):
    t0 = time.time()
    print('\n==> %s\n    %s' % (label, ' '.join(cmd)), flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    print('    (%.0f s, exit %d)' % (time.time() - t0, r.returncode), flush=True)
    if r.returncode != 0:
        raise SystemExit('rebuild 中止於「%s」（exit %d）' % (label, r.returncode))


def is_plaintext():
    return os.path.exists(os.path.join(ROOT, DATA, 'manifest.json'))


def stamp_both():
    run('主站戳記（stamp_assets）', PY, os.path.join('tools', 'stamp_assets.py'), 'docs')
    run('db 站戳記（extract_db.stamp）', PY, '-c', "import sys; sys.path.insert(0, 'tools/db'); import extract_db; extract_db.stamp('docs/db', 'docs/assets')")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--spec', action='store_true', help='套用 extract_db 的 02／13 規格（patch_site_spec）')
    ap.add_argument('--skip-docsearch', action='store_true')
    ap.add_argument('--skip-drive-map', action='store_true')
    ap.add_argument('--cardwork', metavar='DIR', help='各產生器輸出目錄：做完整 build_card_aux 而非 --recompare')
    ap.add_argument('--only-stamp', action='store_true', help='只重新戳記兩站並驗證（前端程式有改、資料沒改）')
    a = ap.parse_args()
    t0 = time.time()
    if a.only_stamp:
        stamp_both()
        run('驗證（verify_encrypted）', PY, os.path.join('tools', 'verify_encrypted.py'))
        print('\nrebuild 完成（只戳記），%.0f s' % (time.time() - t0)); return
    if not a.skip_drive_map:
        run('Google 雲端硬碟對照（drive_map）', PY, os.path.join('tools', 'db', 'drive_map.py'))
    try:
        if not is_plaintext():
            run('解密 docs/db/data', PY, os.path.join('tools', 'encrypt_data.py'), DATA, '--decrypt')
        if not a.skip_docsearch:
            run('文件全文檢索（docmap_docsearch，約 4 分鐘）', PY, os.path.join('tools', 'db', 'docmap_docsearch.py'), '--data', DATA)
        if a.spec:
            run('套用站台規格（patch_site_spec）', PY, os.path.join('tools', 'db', 'patch_site_spec.py'), DATA)
        if a.cardwork:
            run('查詢卡附加資料（build_card_aux 完整）', PY, os.path.join('tools', 'db', 'build_card_aux.py'), a.cardwork, DATA)
        else:
            run('查詢卡附加資料（build_card_aux --recompare：併入 docsearch、Drive 連結、重算比對、加密、戳記）', PY, os.path.join('tools', 'db', 'build_card_aux.py'), '--recompare', DATA)
    except BaseException:
        if is_plaintext():
            print('\n!! 建置失敗，資料仍是明文 → 先原地加密回去（不留明文）', flush=True)
            subprocess.run([PY, os.path.join('tools', 'encrypt_data.py'), DATA], cwd=ROOT)
        raise
    if is_plaintext():
        raise SystemExit('build_card_aux 結束後資料仍是明文（應已自動加密）——請檢查')
    stamp_both()
    run('驗證（verify_encrypted）', PY, os.path.join('tools', 'verify_encrypted.py'))
    print('\nrebuild 完成，%.0f s；git status 確認後即可 push' % (time.time() - t0))


if __name__ == '__main__':
    main()
