# -*- coding: utf-8 -*-
"""端對端測試入口：起本機 mock 登入＋靜態伺服器（tools/auth/mock_server.py）→ 依序跑 test_*.py 的 run(ctx) → 關掉伺服器。

  py tools/tests/run_e2e.py                    # 全部；exit 0 = 全過
  py tools/tests/run_e2e.py --only card auth   # 只跑 test_card.py、test_auth.py
  py tools/tests/run_e2e.py --keep-server      # 跑完伺服器留著（手動看 http://127.0.0.1:8771/db/）
  py tools/tests/run_e2e.py --base http://127.0.0.1:8766   # 用已經在跑的伺服器

需要：py -m pip install playwright && py -m playwright install chromium
密語與 encrypt_data.py 同一來源：環境變數 AMS_WEB_KEY → AMS_WEB_KEY_FILE 指向的檔 → %LOCALAPPDATA%\\AMS\\web.key 第一行；員工代號 900001（tools/auth/mock_users.csv）。
每個測試模組提供 run(ctx) → 失敗清單（list[str]）；ctx = {'base', 'pass', 'out', 'uid'}。
"""
import argparse
import importlib
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PORT = 8771
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from encrypt_data import passphrase_and_salt  # noqa: E402  （只借密語讀法，和 verify_encrypted.py 一樣）


def passphrase():
    # 來源順序同 encrypt_data.default_key_file：AMS_WEB_KEY → AMS_WEB_KEY_FILE → %LOCALAPPDATA%\AMS\web.key 第一行
    return passphrase_and_salt(persist=False)[0]


def wait_up(base, secs=20):
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            with urllib.request.urlopen(base + '/db/version.json', timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', nargs='*', default=None, help='模組名（去掉 test_ 前綴）')
    ap.add_argument('--keep-server', action='store_true')
    ap.add_argument('--base', default=None)
    ap.add_argument('--port', type=int, default=PORT)
    a = ap.parse_args()
    out = os.path.join(HERE, 'out')
    os.makedirs(out, exist_ok=True)
    ctx = {'base': a.base or 'http://127.0.0.1:%d' % a.port, 'pass': passphrase(), 'out': out, 'uid': '900001'}
    proc = None
    if not a.base:
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'tools', 'auth', 'mock_server.py'), str(a.port), os.path.join(ROOT, 'docs')],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_up(ctx['base']):
            proc.kill()
            print('mock server 沒有起來（port %d 被占用？）' % a.port); sys.exit(2)
    names = a.only or [f[5:-3] for f in sorted(os.listdir(HERE)) if f.startswith('test_') and f.endswith('.py')]
    sys.path.insert(0, HERE)
    fails = []
    t0 = time.time()
    try:
        for n in names:
            print('\n### test_%s' % n, flush=True)
            t1 = time.time()
            try:
                mod = importlib.import_module('test_' + n)
                f = mod.run(ctx) or []
            except Exception as e:  # 測試本身炸掉也算失敗
                f = ['%s: exception %s: %s' % (n, type(e).__name__, e)]
            for x in f:
                print('  FAIL', x)
            fails += ['%s: %s' % (n, x) for x in f]
            print('  (%.1f s, %d 失敗)' % (time.time() - t1, len(f)), flush=True)
    finally:
        if proc and not a.keep_server:
            proc.kill()
    print('\n%s：%d 個模組，%d 失敗，%.0f s' % ('ALL PASS' if not fails else 'FAILED', len(names), len(fails), time.time() - t0))
    if a.keep_server and proc:
        print('伺服器留著：%s（pid %d）' % (ctx['base'], proc.pid))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
