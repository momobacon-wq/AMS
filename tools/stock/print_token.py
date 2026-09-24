# -*- coding: utf-8 -*-
"""印出 STOCK_TOKEN（貼到備品庫存 Apps Script 的指令碼屬性）。

  py tools/stock/print_token.py [--key-file F]

token = SHA-256("ams-stock:" + base64(AES 原始金鑰)) 的 hex；AES 金鑰＝PBKDF2(密語, salt)（同 tools/encrypt_data.py）。
瀏覽器端（docs/assets/stock.js）以解鎖後的 D.key 算出同一值，所以只有知道密語的人能讀寫庫存；換密語／salt 後要重貼。
"""
import base64
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from encrypt_data import derive_key, passphrase_and_salt  # noqa: E402


def stock_token(passphrase, salt):
    raw = derive_key(passphrase, salt)
    return hashlib.sha256(b"ams-stock:" + base64.b64encode(raw)).hexdigest()


if __name__ == "__main__":
    kf = None
    if "--key-file" in sys.argv:
        kf = sys.argv[sys.argv.index("--key-file") + 1]
    pw, salt = passphrase_and_salt(key_file=kf, persist=False)
    print(stock_token(pw, salt))
