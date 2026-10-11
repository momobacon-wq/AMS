# -*- coding: utf-8 -*-
"""密語輪替（兩站一次完成）：舊密語解開 docs/data 與 docs/db/data → 以新密語重新加密 → 兩站戳記 → verify_encrypted 必須 0 錯誤
→ 才改寫 key 檔（舊檔另存 web.key.bak-<日期>）→ 印出新的 STOCK_TOKEN 與要跟著做的事。

  py tools/rotate_passphrase.py              # 互動：新密語用 getpass 輸入兩次（不從命令列收，不留在 shell 歷史）
  py tools/rotate_passphrase.py --dry-run    # 只印計畫（兩站狀態、key 檔、備份檔名、之後要做的事），不問新密語、不動任何檔
  py tools/rotate_passphrase.py --fresh-salt # 連 salt 一起換（同事「記住此裝置」的金鑰全部失效；預設 salt 不變）
  選項：--key-file FILE（預設 %LOCALAPPDATA%\\AMS\\web.key）、--root DIR（repo 根目錄，預設本檔上一層；測試時可指向 docs/ 的副本）、
        --new-key-file FILE（新密語讀自該檔第 1 行；只給自動化測試用，平常請用互動輸入）

作法（tools/encrypt_data.py 的 decrypt_dir／encrypt_dir，不在原地解密）：
  1. AMS_WEB_KEY 環境變數有設就拒絕執行（verify_encrypted、E2E 都會先讀它，寫了 key 檔也沒效）。
  2. 舊密語＋salt 由 key 檔讀（encrypt_data.passphrase_and_salt）；兩站都必須是密文狀態（有 meta.json、沒有 manifest.json）。
  3. 每站：decrypt_dir(data, 舊, out=data.rotate-tmp) 解出明文副本（原密文不動）→ encrypt_dir(副本, 新, salt) → 副本變成新密文。
  4. 兩站副本都好了才交換目錄：data → data.rotate-old、副本 → data。
  5. stamp_assets.stamp('docs') ＋ extract_db.stamp('docs/db', 'docs/assets')；verify_encrypted.main([]) 以新密語跑，必須回 0。
  6. 才寫 key 檔（新密語＋salt；舊檔複製成 web.key.bak-YYYYMMDD-HHMMSS），刪掉 data.rotate-old。
  任一步失敗：把 data.rotate-old 換回來、刪副本，資料維持舊密語密文；key 檔不動；非 0 結束。
  之後要做：npx wrangler secret put STOCK_TOKEN（貼印出的值）、GitHub Actions secret AMS_WEB_KEY 改成新密語、tools/stock/worker/.dev.vars 的 STOCK_TOKEN、
  push、通知同事新密語（舊的「記住此裝置」會自動失效：salt 不變時 meta.check 驗不過會重新問密語）。
"""
import argparse
import datetime
import getpass
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'db'))
sys.path.insert(0, str(HERE / 'stock'))
import encrypt_data  # noqa: E402

SITES = ('docs', 'docs/db')


def log(msg):
    print(msg, flush=True)


def site_state(root):
    """每站的 data 目錄與狀態（'enc' 密文／'plain' 明文／'missing'）。"""
    out = []
    for s in SITES:
        data = root / s / 'data'
        st = 'missing' if not data.is_dir() else ('enc' if encrypt_data.is_encrypted(data) else 'plain')
        out.append((s, data, st))
    return out


def read_new_passphrase(new_key_file):
    if new_key_file:
        lines = Path(new_key_file).read_text(encoding='utf-8').splitlines()
        pw = (lines[0] if lines else '').strip()
    else:
        if not sys.stdin.isatty():
            raise SystemExit('需要在終端機互動輸入新密語（或用 --new-key-file，只供測試）')
        pw = getpass.getpass('新密語（輸入時不顯示）：').strip()
        if pw != getpass.getpass('再輸入一次確認：').strip():
            raise SystemExit('兩次輸入不一致，取消')
    if len(pw) < 8:
        raise SystemExit('新密語太短（至少 8 個字元）')
    return pw


def stamp_both(root):
    import stamp_assets
    import extract_db
    stamp_assets.stamp(str(root / 'docs'))
    extract_db.stamp(str(root / 'docs' / 'db'), str(root / 'docs' / 'assets'))


def verify_with(root, passphrase):
    """verify_encrypted 以指定密語跑（它讀 AMS_WEB_KEY；跑完還原環境變數）。回傳錯誤數（0 才算過）。"""
    import verify_encrypted
    old = os.environ.get('AMS_WEB_KEY')
    os.environ['AMS_WEB_KEY'] = passphrase
    try:
        verify_encrypted.ERRORS.clear()
        rc = verify_encrypted.main([str(root / s) for s in SITES])
    finally:
        if old is None:
            os.environ.pop('AMS_WEB_KEY', None)
        else:
            os.environ['AMS_WEB_KEY'] = old
    return rc


def swap_in(data, tmp):
    """data → data.rotate-old、tmp → data。回傳 old 路徑。"""
    old = data.with_name(data.name + '.rotate-old')
    if old.exists():
        shutil.rmtree(old)
    os.rename(data, old)
    os.rename(tmp, data)
    return old


def swap_back(data, old):
    if data.exists():
        shutil.rmtree(data)
    os.rename(old, data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--key-file', help='密語檔（預設 %%LOCALAPPDATA%%\\AMS\\web.key）')
    ap.add_argument('--root', help='repo 根目錄（預設本檔上一層）')
    ap.add_argument('--fresh-salt', action='store_true', help='連 salt 一起換（記住此裝置的金鑰全部失效）')
    ap.add_argument('--dry-run', action='store_true', help='只印計畫，不問新密語、不動任何檔')
    ap.add_argument('--new-key-file', help='新密語讀自該檔第 1 行（只供自動化測試）')
    a = ap.parse_args(argv)

    if os.environ.get('AMS_WEB_KEY'):
        raise SystemExit('環境變數 AMS_WEB_KEY 已設定：輪替後 verify_encrypted／E2E 仍會用它，寫了 key 檔也沒效。先 set AMS_WEB_KEY= 再跑。')
    root = Path(a.root).resolve() if a.root else HERE.parent
    kf = Path(a.key_file) if a.key_file else encrypt_data.default_key_file()
    if not kf.exists():
        raise SystemExit('沒有 key 檔 %s（舊密語從它讀）' % kf)
    old_pw, salt = encrypt_data.passphrase_and_salt(kf, persist=False)
    states = site_state(root)
    stamp_ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = kf.with_name(kf.name + '.bak-' + stamp_ts)

    log('密語輪替計畫')
    log('  repo 根目錄   %s' % root)
    log('  key 檔        %s（舊密語由此讀；輪替後舊檔另存 %s）' % (kf, bak.name))
    log('  salt          %s' % ('換新（--fresh-salt：同事記住此裝置的金鑰全部失效）' if a.fresh_salt else '不變（記住此裝置者只需重輸新密語）'))
    for s, data, st in states:
        n = len(list(data.rglob('*.bin'))) if st != 'missing' else 0
        log('  %-8s %s  %s（%d 個 .bin）' % (s, {'enc': '密文', 'plain': '明文！', 'missing': '缺目錄'}[st], data, n))
    log('  步驟          解出明文副本 → 新密語加密 → 交換目錄 → 兩站戳記 → verify_encrypted 0 錯誤 → 寫 key 檔 → 印 STOCK_TOKEN')
    bad = [s for s, _, st in states if st != 'enc']
    if bad:
        raise SystemExit('以下站不是密文狀態，先處理（明文請 py tools/encrypt_data.py <data>）：%s' % ', '.join(bad))
    if a.dry_run:
        log('（--dry-run：到此為止，沒有改任何檔）')
        return 0

    new_pw = read_new_passphrase(a.new_key_file)
    if new_pw == old_pw:
        raise SystemExit('新密語與舊密語相同，取消')
    new_salt = os.urandom(16) if a.fresh_salt else salt

    tmps = []
    try:
        for s, data, _ in states:
            tmp = data.with_name(data.name + '.rotate-tmp')
            if tmp.exists():
                shutil.rmtree(tmp)
            log('\n==> %s：以舊密語解出明文副本 %s' % (s, tmp.name))
            encrypt_data.decrypt_dir(data, old_pw, out=tmp, log=log)
            log('==> %s：以新密語重新加密副本' % s)
            encrypt_data.encrypt_dir(tmp, new_pw, new_salt, log=log)
            tmps.append((s, data, tmp))
    except BaseException:
        for _, _, tmp in tmps:
            shutil.rmtree(tmp, ignore_errors=True)
        for s, data, _ in states:
            shutil.rmtree(data.with_name(data.name + '.rotate-tmp'), ignore_errors=True)
        log('\n!! 解密／重新加密失敗，原密文未動、key 檔未動')
        raise

    olds = []
    try:
        for s, data, tmp in tmps:
            olds.append((s, data, swap_in(data, tmp)))
        log('\n==> 兩站戳記')
        stamp_both(root)
        log('\n==> verify_encrypted（以新密語）')
        rc = verify_with(root, new_pw)
        if rc != 0:
            raise SystemExit('verify_encrypted 有錯誤（見上），不寫 key 檔')
    except BaseException:
        for s, data, old in olds:
            swap_back(data, old)
        log('\n!! 失敗：已把兩站換回舊密語的密文；key 檔未動（若戳記已改，重跑 py tools/db/rebuild.py --only-stamp 即可）')
        raise

    shutil.copy2(kf, bak)
    kf.write_text(new_pw + '\n' + encrypt_data.b64(new_salt) + '\n', encoding='utf-8')
    for s, data, old in olds:
        shutil.rmtree(old, ignore_errors=True)
    log('\n==> key 檔已改寫：%s（舊檔 %s）' % (kf, bak))

    from print_token import stock_token
    token = stock_token(new_pw, new_salt)
    log('\n完成。接著要做（依序）：')
    log('  1. 備品庫存 Worker 的 STOCK_TOKEN 換成下面這個值（否則領取／放入全部回「未授權（密語不符）」）：')
    log('     %s' % token)
    log('     cd tools/stock/worker && npx wrangler secret put STOCK_TOKEN     （貼上後 Enter；本機 .dev.vars 的 STOCK_TOKEN 也改）')
    log('  2. GitHub → Settings → Secrets and variables → Actions → AMS_WEB_KEY 改成新密語（.github/workflows/check.yml 用它驗證密文）')
    log('  3. py tools/tests/run_e2e.py（mock 會用新密語算 token 比對）→ git status 確認只有 docs/*/data、index.html、version.json 變動 → push')
    log('  4. 通知同事新密語；舊的「記住此裝置」金鑰開站時驗不過會自動改問密語%s' % ('' if not a.fresh_salt else '（salt 已換，所有人都要重輸）'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
