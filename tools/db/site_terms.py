# -*- coding: utf-8 -*-
"""tools/db/site_terms.py — 廠內專屬字串（伺服器名稱、雲端硬碟／試算表 ID…）不進 repo：原始碼只寫 ⟦KEY⟧ 代號，執行時由本機檔還原。

本機檔：%LOCALAPPDATA%\\AMS\\site_terms.json（環境變數 AMS_SITE_TERMS 可覆寫），格式 {"KEY": "值", …}；
需要哪些 KEY 見 tools/db/site_terms.example.json（複製過去再填真值）。這個檔與 web.key 同一層級，**不可 commit**（.gitignore／pre-commit 都擋）。

  T('…伺服器 ⟦AMS_SERVER⟧…')    把字串裡每個 ⟦KEY⟧ 換成本機值；沒有代號的字串原樣回傳。
  get('DRIVE_ROOT_ID')          取單一值。

缺檔或缺 KEY 時直接中止並說明怎麼補（不靜默帶著代號產出資料）。
"""
import json
import os
import re

_LOCAL = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
PATH = os.environ.get('AMS_SITE_TERMS') or os.path.join(_LOCAL, 'AMS', 'site_terms.json')
_RX = re.compile('⟦([A-Z0-9_]+)⟧')
_terms = None


def _load():
    global _terms
    if _terms is None:
        try:
            with open(PATH, encoding='utf-8-sig') as f:
                _terms = json.load(f)
        except FileNotFoundError:
            raise SystemExit('找不到 %s（廠內專屬字串的本機檔，不進 repo）。請照 tools/db/site_terms.example.json 建立並填入真值，'
                             '或用環境變數 AMS_SITE_TERMS 指到它。' % PATH)
        except ValueError as e:
            raise SystemExit('%s 不是合法的 JSON（%s）。格式見 tools/db/site_terms.example.json。' % (PATH, e))
        if not isinstance(_terms, dict) or not all(isinstance(v, str) for v in _terms.values()):
            raise SystemExit('%s 必須是 {"KEY": "字串值", …}。格式見 tools/db/site_terms.example.json。' % PATH)
    return _terms


def get(key):
    terms = _load()
    if key not in terms:
        raise SystemExit('%s 缺少 %s（需要的 KEY 見 tools/db/site_terms.example.json）。' % (PATH, key))
    return terms[key]


def T(s):
    if '⟦' not in s:
        return s
    return _RX.sub(lambda m: get(m.group(1)), s)


if __name__ == '__main__':
    print('%s：%s' % (PATH, '有（%d 個 KEY）' % len(_load()) if os.path.exists(PATH) else '無'))
