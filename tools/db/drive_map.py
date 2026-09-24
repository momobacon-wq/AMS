# -*- coding: utf-8 -*-
"""drive_map.py — 工程文件庫（Google 雲端硬碟資料夾）相對路徑 → Drive 檔案 ID 對照表

  py tools/db/drive_map.py                         # 寫 %LOCALAPPDATA%\\AMS\\drive_map.json
  py tools/db/drive_map.py --out <path> [--root-id 1RIrN6nv…] [--title "@@新機組資料備份"]

來源：本機「Google 雲端硬碟桌面版」的中繼資料庫 %LOCALAPPDATA%\\Google\\DriveFS\\<帳號>\\metadata_sqlite_db
（items.id 就是雲端檔案 ID、stable_parents 是父子關係），不必打 Drive API。先複製 db（含 -wal）到暫存再讀，避免鎖檔。
輸出 {"root": <資料夾 ID>, "built": <時間>, "files": {"<相對路徑（小寫、/ 分隔）>": "<檔案 ID>"}}；捷徑改指向目標檔。
這個對照表只在本機使用（不進 repo）；build_card_aux.py --drive-map 用它替 index.docs 補 url。
"""
import argparse
import collections
import datetime
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile

DEFAULT_ROOT_ID = '1RIrN6nvXEC8JTF_L7dCuETh757Fb37My'   # @@新機組資料備份（hst-docsearch 的 library_root）
DEFAULT_OUT = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'drive_map.json')


def find_metadata_db():
    base = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'DriveFS')
    cands = [p for p in glob.glob(os.path.join(base, '*', 'metadata_sqlite_db')) if os.path.getsize(p) > 0]
    if not cands:
        raise SystemExit('找不到 Google 雲端硬碟桌面版的 metadata_sqlite_db（%s）' % base)
    return max(cands, key=os.path.getsize)


def open_copy(db_path):
    tmp = tempfile.mkdtemp(prefix='drivefs_')
    dst = os.path.join(tmp, 'meta.db')
    shutil.copy2(db_path, dst)
    for suf in ('-wal', '-shm'):
        if os.path.exists(db_path + suf):
            shutil.copy2(db_path + suf, dst + suf)
    c = sqlite3.connect(dst)
    c.text_factory = lambda b: b.decode('utf-8', 'replace')
    return c, tmp


def build(root_id, title):
    c, tmp = open_copy(find_metadata_db())
    try:
        row = c.execute('SELECT stable_id, id FROM items WHERE id=?', (root_id,)).fetchone() if root_id else None
        if not row and title:
            row = c.execute("SELECT stable_id, id FROM items WHERE is_folder=1 AND trashed=0 AND local_title=?", (title,)).fetchone()
        if not row:
            raise SystemExit('資料庫裡找不到根資料夾（id=%s / title=%s）' % (root_id, title))
        root_sid, root_cloud = row
        kids = collections.defaultdict(list)
        for it, par in c.execute('SELECT item_stable_id, parent_stable_id FROM stable_parents'):
            kids[par].append(it)
        info = {r[0]: r[1:] for r in c.execute('SELECT stable_id, id, local_title, is_folder, mime_type, trashed FROM items')}
        shortcut = {r[0]: r[1] for r in c.execute('SELECT shortcut_stable_id, target_stable_id FROM shortcut_details')}
        files = {}
        stack = [(root_sid, '')]
        n_dir = 0
        while stack:
            sid, p = stack.pop()
            for k in kids.get(sid, []):
                i = info.get(k)
                if not i or i[4] or not i[1]:
                    continue
                rel = (p + '/' if p else '') + i[1]
                if i[2]:
                    n_dir += 1
                    stack.append((k, rel))
                    continue
                cid = i[0]
                if i[3] == 'application/vnd.google-apps.shortcut' and k in shortcut and shortcut[k] in info:
                    cid = info[shortcut[k]][0]
                files[rel.lower()] = cid
        return {'root': root_cloud, 'built': datetime.datetime.now().isoformat(timespec='seconds'), 'dirs': n_dir, 'files': files}
    finally:
        c.close()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--root-id', default=DEFAULT_ROOT_ID)
    ap.add_argument('--title', default='@@新機組資料備份')
    a = ap.parse_args()
    m = build(a.root_id, a.title)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False)
    print('drive_map: root %s, %d 個檔（%d 個資料夾）→ %s' % (m['root'], len(m['files']), m['dirs'], a.out))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
