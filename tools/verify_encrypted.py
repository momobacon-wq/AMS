# -*- coding: utf-8 -*-
"""Independent check that a site's data dir is properly encrypted and consistent — run before every push.

  py tools/verify_encrypted.py [docs] [docs/db]      (default: both)

Written without importing encrypt_data's crypto (only its key-file reader): re-derives the key from the passphrase, opens
meta.check, decrypts EVERY .bin with AAD = its relative path, gunzips, parses JSON; asserts no plaintext *.json besides
meta.json; every file listed in manifest (sheets[].files, aux.card.index and its files) exists as .bin and vice versa;
recomputes build from the plaintext the way the generators do (sheets/*.json by basename, then card/*.json by rel path,
plus manifest without build) and requires meta.build == manifest.build == version.json.build == index.html's
<meta name="ams-build"> == the meta.json preload ?v=; total size < 900 MB; no local absolute paths.  Exit 0 only with 0 errors.
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
from encrypt_data import passphrase_and_salt  # noqa: E402  (key file convention only)

# 建置機器的本機路徑絕不能外流；AMS 資料本身含伺服器路徑（C:\ProgramData\… 之類）是資料內容，只計數提醒
LOCAL_RE = re.compile(r'Users[\\/]bacon|/c/Users/|我的雲端硬碟|@@新機組資料備份')
ABS_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]:(?:\\|/)')
CHECK_TEXT = b"ams-ok"
ERRORS = []


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
    vals["index.html preload"] = (m.group(2) if m else None)
    if m and m.group(1) != "meta":
        err("index.html preloads data/manifest.json (must be data/meta.json when encrypted)")
    if len(set(vals.values())) == 1:
        ok(f"build consistent everywhere: {build}")
    else:
        err(f"build mismatch: {vals}")
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
