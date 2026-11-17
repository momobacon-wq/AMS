# -*- coding: utf-8 -*-
"""Independent check that a site's data dir is properly encrypted and consistent — run before every push.

  py tools/verify_encrypted.py [docs] [docs/db]      (default: both)

Written without importing encrypt_data's crypto (only its key-file reader): re-derives the key from the passphrase, opens
meta.check, decrypts EVERY .bin with AAD = its relative path, gunzips, parses JSON; asserts no plaintext *.json besides
meta.json; every file listed in manifest (sheets[].files, aux.card.index and its files, plus card/index.json's hmi.files
= the HMI screen images, pid.files = the P&ID sheet images and getag.files = the GE tag card data) exists as .bin and vice versa;
recomputes build from the plaintext the way the generators do (sheets/*.json by basename, then card/**/*.json by rel path,
plus manifest without build) and requires meta.build == manifest.build == version.json.build == index.html's
<meta name="ams-build">; the meta.json preload ?v= == build + key tag (key_tag(meta), also <meta ams-build data-key> and
version.json key); total size < 900 MB; no local absolute paths.  Exit 0 only with 0 errors.
"""
import base64
import gzip
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from encrypt_data import key_tag, passphrase_and_salt  # noqa: E402  (key file convention + cache-key tag)

# 建置機器的本機路徑絕不能外流；AMS 資料本身含伺服器路徑（C:\ProgramData\… 之類）是資料內容，只計數提醒
# 注意 `[\\/]{1,2}`：這些檔是 JSON，路徑分隔符在 JSON 文字裡是**兩個**反斜線（`Users\\bacon`）。
# 原本寫成 `Users[\\/]bacon` 只抓得到單一分隔符 → 整支守門程式對 JSON 內的 Windows 路徑是假陰性（2026-10-03 修）。
# `@@新機組` 不加「資料備份」：使用者另有 G:\其他電腦\…\@@新機組\… 這個資料夾也是本機路徑。
# 「其他電腦」刻意**不**列入：AMS 資料庫自己的工作站標籤就叫「本廠其他電腦 (2024 以後)」（sheets 19/24/28），不是路徑。
LOCAL_RE = re.compile(r'Users[\\/]{1,2}bacon|/c/Users/|我的雲端硬碟|@@新機組')
ABS_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]:(?:\\|/)')
CHECK_TEXT = b"ams-ok"
ERRORS = []


def _deny_strings():
    """本機 site_terms.json（%LOCALAPPDATA%\\AMS\\site_terms.json 或 AMS_SITE_TERMS）的 DENY_STRINGS（| 分隔）→ list；沒有檔或沒有這個鍵 → None。"""
    p = os.environ.get("AMS_SITE_TERMS") or os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local"), "AMS", "site_terms.json")
    try:
        with open(p, encoding="utf-8-sig") as f:
            v = json.load(f).get("DENY_STRINGS")
    except (OSError, ValueError):
        return None
    return [s for s in str(v).split("|") if s.strip()] if v else None


def err(m):
    ERRORS.append(m); print("ERR  " + m)


def ok(m):
    print("ok   " + m)


def dump(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_site(docs, pw):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    docs = Path(docs); data = docs / "data"
    print(f"== {docs}")
    if not data.is_dir():
        err(f"missing {data}"); return
    mp = data / "meta.json"
    if not mp.exists():
        err("meta.json missing → PLAINTEXT export, must not be published"); return
    meta = json.loads(mp.read_text(encoding="utf-8"))
    if not meta.get("enc"):
        err("meta.enc is 0 → plaintext export"); return
    k = meta.get("kdf") or {}
    if (k.get("name"), k.get("hash"), int(k.get("iter") or 0)) != ("PBKDF2", "SHA-256", 200000):
        err(f"unexpected kdf {k}")
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(k["salt"]), iterations=int(k["iter"])).derive(pw.encode("utf-8"))
    chk = base64.b64decode(meta["check"])
    try:
        if AESGCM(key).decrypt(chk[:12], chk[12:], b"check") != CHECK_TEXT:
            err("meta.check opened but content differs"); return
    except Exception:
        err("passphrase does not open meta.check"); return
    ok(f"passphrase verified (PBKDF2 x{k['iter']}, AES-256-GCM)")
    plain_json = [p.relative_to(data).as_posix() for p in data.rglob("*.json") if p.name != "meta.json"]
    (ok if not plain_json else err)(f"{len(plain_json)} plaintext .json besides meta.json" + (": " + ", ".join(plain_json[:5]) if plain_json else ""))
    # decrypt everything
    texts = {}
    disk = mp.stat().st_size
    bins = sorted(data.rglob("*.bin"))
    for p in bins:
        rel = p.relative_to(data).as_posix()[:-4]
        blob = p.read_bytes(); disk += len(blob)
        try:
            pt = AESGCM(key).decrypt(blob[:12], blob[12:], rel.encode("utf-8"))
            b = gzip.decompress(pt) if meta.get("gzip", 1) else pt
            json.loads(b.decode("utf-8"))
        except Exception as e:
            err(f"cannot open {rel}.bin: {e.__class__.__name__}"); continue
        texts[rel] = b
    ok(f"{len(texts)}/{len(bins)} .bin files decrypt + parse; {disk / 1e6:.1f} MB on disk")
    if disk > 900_000_000:
        err("total > 900 MB (GitHub Pages limit 1 GB)")
    if "manifest.json" not in texts:
        err("manifest.json.bin missing"); return
    man = json.loads(texts["manifest.json"].decode("utf-8"))
    # referenced ↔ present
    refs = set()
    for s in man.get("sheets", []):
        for f in s.get("files") or []:
            refs.add(f)
    aux = ((man.get("aux") or {}).get("card") or {})
    if aux.get("index"):
        refs.add(aux["index"])
        if aux["index"] in texts:
            ix = json.loads(texts[aux["index"]].decode("utf-8"))
            for f in ix.get("files") or []:
                refs.add(f)
            # card/index.json 的 hmi.files = 圖控畫面影像（card/hmi/<slug>.json；CONTRACT.md「圖控 HMI 畫面位置」）
            for f in ((ix.get("hmi") or {}).get("files")) or []:
                refs.add(f)
            # card/index.json 的 pid.files = P&ID 圖紙影像（card/pid/<slug>.json；CONTRACT.md「P&ID 圖面位置」）
            for f in ((ix.get("pid") or {}).get("files")) or []:
                refs.add(f)
            # card/index.json 的 getag.files = GE 編號卡的整份對照表（card/getag.json；CONTRACT.md「v8」）
            for f in ((ix.get("getag") or {}).get("files")) or []:
                refs.add(f)
            # v17：AMS 設備卡的接線路徑塊（card/wire-NN.json；沒有接線路徑的分塊是 null）與 KKS 編號卡（card/kkstag.json＋kkstag-loc-NN.json）
            for f in ((ix.get("wire") or {}).get("files")) or []:
                if f:
                    refs.add(f)
            for f in ((ix.get("kkstag") or {}).get("files")) or []:
                refs.add(f)
    # v26：電動閥清單的查詢卡分塊（card/mov-NN.json）登記在 02.json 的 mov.files（tools/db/mov_site.py）
    if "sheets/02.json" in texts:
        try:
            s02 = json.loads(texts["sheets/02.json"].decode("utf-8"))
        except ValueError:
            s02 = {}
        for f in ((s02.get("mov") or {}).get("files")) or []:
            refs.add(f)
    missing = sorted(r for r in refs if r not in texts)
    orphan = sorted(r for r in texts if r != "manifest.json" and r not in refs)
    (ok if not missing else err)(f"{len(missing)} referenced files missing" + (": " + ", ".join(missing[:5]) if missing else ""))
    (ok if not orphan else err)(f"{len(orphan)} orphan .bin not referenced" + (": " + ", ".join(orphan[:5]) if orphan else ""))
    # build recomputed on plaintext (generator algorithm)
    h = hashlib.sha256()
    sheets = sorted(r for r in texts if r.startswith("sheets/"))
    cards = sorted(r for r in texts if r.startswith("card/"))
    for rel in sheets + cards:
        name = os.path.basename(rel) if rel.startswith("sheets/") else rel
        h.update(name.encode("utf-8") + b"\0"); h.update(texts[rel])
    h.update(dump({kk: v for kk, v in man.items() if kk != "build"}))
    build = h.hexdigest()[:10]
    vals = {"recomputed": build, "meta": meta.get("build"), "manifest": man.get("build")}
    vp = docs / "version.json"
    vals["version.json"] = json.loads(vp.read_text(encoding="utf-8")).get("build") if vp.exists() else None
    html = (docs / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<meta name="ams-build" content="([0-9a-f]+)"', html)
    vals["index.html meta"] = m.group(1) if m else None
    m = re.search(r'<link rel="preload" href="data/(meta|manifest)\.json\?v=([0-9a-zA-Z]+)"', html)
    pre = m.group(2) if m else None
    if m and m.group(1) != "meta":
        err("index.html preloads data/manifest.json (must be data/meta.json when encrypted)")
    if len(set(vals.values())) == 1:
        ok(f"build consistent everywhere: {build}")
    else:
        err(f"build mismatch: {vals}")
    # 資料網址的 ?v= ＝ build＋金鑰標記（key_tag）：戳記若還是舊金鑰的標記，換密語後瀏覽器會拿快取的舊密文
    tag = key_tag(meta)
    m = re.search(r'<meta name="ams-build"[^>]* data-key="([0-9a-zA-Z]*)"', html)
    vk = json.loads(vp.read_text(encoding="utf-8")).get("key") if vp.exists() else None
    vals_k = {"meta.check tag": tag, "index.html data-key": m.group(1) if m else None, "index.html preload": pre, "version.json key": vk}
    want = {"meta.check tag": tag, "index.html data-key": tag, "index.html preload": build + tag, "version.json key": tag}
    if vals_k == want:
        ok(f"key tag stamped: data-key={tag}, preload ?v={build}{tag}")
    else:
        err(f"key tag mismatch (re-stamp: py tools/db/rebuild.py --only-stamp): got {vals_k}, want {want}")
    # content hygiene
    bad = drive = 0
    for rel, b in texts.items():
        t = b.decode("utf-8", "replace")
        mm = LOCAL_RE.search(t)
        if mm:
            bad += 1
            if bad <= 5:
                err(f"build-machine local path in {rel}: {mm.group(0)}")
        drive += len(ABS_RE.findall(t))
    if not bad:
        ok(f"no build-machine local paths in plaintext ({drive} drive-letter paths inside the data itself, e.g. AMS server paths)")
    # 不可出貨的字串（人名等）：清單放在本機 site_terms.json 的 DENY_STRINGS（以 | 分隔；不進 repo）。沒有本機檔（CI）就略過
    deny = _deny_strings()
    if deny is None:
        ok("deny-string check skipped (no local site_terms.json DENY_STRINGS)")
    else:
        hits = [(rel, s) for rel, b in texts.items() for s in deny if s in b.decode("utf-8", "replace")]
        if hits:
            for rel, s in hits[:5]:
                err(f"deny-listed string in {rel} (DENY_STRINGS entry #{deny.index(s) + 1})")
        else:
            ok(f"0 deny-listed strings ({len(deny)} entries) in {len(texts)} decrypted files")
    if 'name="robots"' not in html:
        err("index.html lacks <meta name=\"robots\" content=\"noindex, nofollow\">")


def main(argv):
    sites = argv or ["docs", "docs/db"]
    root = Path(__file__).resolve().parent.parent
    pw, _ = passphrase_and_salt(persist=False)
    for s in sites:
        verify_site(root / s if not Path(s).is_absolute() else Path(s), pw)
    rp = root / "docs" / "robots.txt"
    (ok if rp.exists() and "Disallow: /" in rp.read_text() else err)("docs/robots.txt Disallow: /")
    print(f"== {len(ERRORS)} error(s)")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
