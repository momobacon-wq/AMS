# -*- coding: utf-8 -*-
"""Encrypt (or decrypt) a built data directory in place — the last step before stamping, for both sites.

  py tools/encrypt_data.py docs/data                 # plaintext sheets/*.json, card/*.json, manifest.json → <rel>.bin + meta.json
  py tools/encrypt_data.py docs/db/data
  py tools/encrypt_data.py docs/db/data --decrypt    # back to plaintext in place (rebuild card aux / verify with xlsx…)
  py tools/encrypt_data.py docs/db/data --decrypt-to <dir>   # plaintext copy elsewhere, ciphertext untouched
  options: --key-file FILE  --fresh-salt  --dry-run

Scheme (same as momobacon-wq/signal-atlas; CONTRACT.md「加密與封裝」):
  key   = PBKDF2-HMAC-SHA256(passphrase, salt, 200000) → 32 bytes (AES-256-GCM)
  file  = <rel>.bin = 12-byte random IV || AES-GCM(gzip(JSON UTF-8, level 6, mtime 0)) with tag; AAD = rel (posix path
          relative to the data dir, without .bin) so a blob cannot be moved to another path
  meta.json (the only plaintext file) = {"enc":1,"gzip":1,"build":<manifest.build>,
          "kdf":{"name":"PBKDF2","hash":"SHA-256","iter":200000,"salt":<b64>},"check":<b64 seal(key,"ams-ok",aad="check")>}
Passphrase: env AMS_WEB_KEY, else line 1 of %LOCALAPPDATA%\\AMS\\web.key (or AMS_WEB_KEY_FILE / --key-file).  Line 2 of that
file holds the base64 16-byte salt: it is FIXED per installation (created on first run) so that a key remembered in the
browser (localStorage ams.key) survives rebuilds and is shared by docs/ and docs/db/ (same origin).  --fresh-salt rotates it.
`manifest.build` must already be computed on the plaintext (the generators do that); this tool never changes it.
The passphrase and key file never enter the repo.
"""
import argparse
import base64
import gzip
import json
import os
import secrets
import sys
from pathlib import Path

KDF_ITER = 200_000
CHECK_TEXT = b"ams-ok"
KEY_STORE = "ams.key"  # localStorage name used by docs/assets/core.js (not atlas.key: same origin as signal-atlas)


def b64(b):
    return base64.b64encode(b).decode("ascii")


def default_key_file():
    p = os.environ.get("AMS_WEB_KEY_FILE")
    if p:
        return Path(p)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AMS" / "web.key"


def passphrase_and_salt(key_file=None, fresh=False, persist=True):
    """(passphrase, salt).  Passphrase from AMS_WEB_KEY or line 1 of the key file; salt from line 2 (created/persisted on
    first use or with fresh=True)."""
    kf = Path(key_file) if key_file else default_key_file()
    lines = kf.read_text(encoding="utf-8").splitlines() if kf.exists() else []
    pw = (os.environ.get("AMS_WEB_KEY") or (lines[0] if lines else "")).strip()
    if not pw:
        raise SystemExit(f"site passphrase not found: set AMS_WEB_KEY or put it on line 1 of {kf}")
    if len(pw) < 8:
        raise SystemExit("site passphrase too short (min 8 characters)")
    salt = None
    if not fresh and len(lines) > 1 and lines[1].strip():
        try:
            salt = base64.b64decode(lines[1].strip())
        except Exception:
            salt = None
        if salt is not None and len(salt) != 16:
            salt = None
    if salt is None:
        salt = secrets.token_bytes(16)
        if persist:
            kf.parent.mkdir(parents=True, exist_ok=True)
            kf.write_text((lines[0] if lines else pw) + "\n" + b64(salt) + "\n", encoding="utf-8")
            print(f"[key] new salt written to {kf}")
        else:
            print("[key] WARNING: salt not persisted (remembered browser keys will not match next build)")
    return pw, salt


def derive_key(passphrase, salt):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=KDF_ITER).derive(passphrase.encode("utf-8"))


def seal(key, plain, aad):
    """12-byte random IV || AES-256-GCM ciphertext+tag (WebCrypto layout).  AAD = relative path (or 'check')."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = secrets.token_bytes(12)
    return iv + AESGCM(key).encrypt(iv, plain, aad.encode("utf-8"))


def unseal(key, blob, aad):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad.encode("utf-8"))


def is_encrypted(data):
    data = Path(data)
    return (data / "meta.json").exists() and not (data / "manifest.json").exists()


def plain_files(data):
    return sorted(p for p in Path(data).rglob("*.json") if p.name != "meta.json")


def encrypt_dir(data, passphrase, salt, log=print, dry_run=False):
    """Plaintext data dir → ciphertext in place.  Returns meta dict (None when already encrypted)."""
    data = Path(data)
    man_p = data / "manifest.json"
    if not man_p.exists():
        if (data / "meta.json").exists():
            log(f"[encrypt] {data}: already encrypted (no manifest.json) — nothing to do")
            return None
        raise SystemExit(f"[encrypt] {data}: manifest.json not found")
    man = json.loads(man_p.read_bytes().decode("utf-8"))
    build = man.get("build")
    if not build:
        raise SystemExit("[encrypt] manifest.json has no build (run the generator / data_build first)")
    files = plain_files(data)
    stale = sorted(data.rglob("*.bin"))
    if dry_run:
        log(f"[encrypt] dry run: {len(files)} files would be encrypted, {len(stale)} stale .bin removed, build {build}")
        return None
    for p in stale:
        p.unlink()
    key = derive_key(passphrase, salt)
    n = plain = wire = 0
    for p in files:
        rel = p.relative_to(data).as_posix()
        b = p.read_bytes()
        blob = seal(key, gzip.compress(b, 6, mtime=0), rel)
        (data / (rel + ".bin")).write_bytes(blob)
        p.unlink()
        n += 1; plain += len(b); wire += len(blob)
    meta = {"enc": 1, "gzip": 1, "build": build,
            "kdf": {"name": "PBKDF2", "hash": "SHA-256", "iter": KDF_ITER, "salt": b64(salt)},
            "check": b64(seal(key, CHECK_TEXT, "check"))}
    (data / "meta.json").write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8", newline="\n")
    log(f"[encrypt] {data}: {n} files  {plain / 1e6:.1f} MB → {wire / 1e6:.1f} MB on the wire  build {build}")
    return meta


def load_key(data, passphrase):
    """Key for an encrypted dir: salt from its meta.json; verifies the passphrase against meta.check."""
    meta = json.loads((Path(data) / "meta.json").read_text(encoding="utf-8"))
    if not meta.get("enc"):
        raise SystemExit("[decrypt] meta.json says enc:0 (plaintext export)")
    key = derive_key(passphrase, base64.b64decode(meta["kdf"]["salt"]))
    if unseal(key, base64.b64decode(meta["check"]), "check") != CHECK_TEXT:
        raise SystemExit("[decrypt] passphrase does not open meta.check")
    return key, meta


def decrypt_dir(data, passphrase, out=None, log=print):
    """Ciphertext → plaintext.  out=None: in place (removes .bin and meta.json); else write the plaintext copy under out."""
    data = Path(data)
    key, meta = load_key(data, passphrase)
    n = 0
    for p in sorted(data.rglob("*.bin")):
        rel = p.relative_to(data).as_posix()[:-4]
        b = gzip.decompress(unseal(key, p.read_bytes(), rel)) if meta.get("gzip", 1) else unseal(key, p.read_bytes(), rel)
        dst = (Path(out) if out else data) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b)
        if out is None:
            p.unlink()
        n += 1
    if out is None:
        (data / "meta.json").unlink()
    log(f"[decrypt] {data}: {n} files → {out or data}")
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir")
    ap.add_argument("--key-file")
    ap.add_argument("--decrypt", action="store_true", help="ciphertext → plaintext in place")
    ap.add_argument("--decrypt-to", metavar="DIR", help="plaintext copy under DIR (ciphertext kept)")
    ap.add_argument("--fresh-salt", action="store_true", help="rotate the salt (remembered browser keys stop working)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    data = Path(a.data_dir)
    if not data.is_dir():
        raise SystemExit(f"not a directory: {data}")
    if a.decrypt or a.decrypt_to:
        pw, _ = passphrase_and_salt(a.key_file, persist=False)
        decrypt_dir(data, pw, out=a.decrypt_to)
        return 0
    pw, salt = passphrase_and_salt(a.key_file, fresh=a.fresh_salt, persist=not a.dry_run)
    encrypt_dir(data, pw, salt, dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
