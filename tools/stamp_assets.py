# -*- coding: utf-8 -*-
"""Cache-busting stamp for the static site (GitHub Pages serves every file with max-age=600 and no versioned URLs).

Usage:  py tools/stamp_assets.py [docs]

* data/manifest.json gets "build" = sha256 of all data files (computed by tools/extract.py; recomputed here if missing).
  The front-end appends ?v=<build> to every data/sheets/*.json request, so one tab never mixes chunks of two builds.
* index.html: every assets/*.js|css reference gets ?v=<sha256 of that file>[:10]; <meta name="ams-build"> gets the data
  build plus the app / Chart.js hashes; the manifest preload gets ?v=<build> (the same URL core.js fetches).
* version.json = {"build", "app"}: an open tab re-fetches it (no-cache) and offers a reload when either changed.

Idempotent and deterministic (no timestamps).  tools/extract.py runs it after writing the data; run it by hand after
editing anything in docs/assets.
"""
import glob
import hashlib
import json
import os
import re
import sys


def sha(data, n=10):
    return hashlib.sha256(data).hexdigest()[:n]


def data_build(data_dir):
    """Hash of every sheets/*.json plus manifest.json without its own "build" key."""
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(data_dir, "sheets", "*.json"))):
        h.update(os.path.basename(p).encode("utf-8") + b"\0")
        with open(p, "rb") as f:
            h.update(f.read())
    with open(os.path.join(data_dir, "manifest.json"), "rb") as f:
        man = json.loads(f.read().decode("utf-8"))
    man.pop("build", None)
    h.update(json.dumps(man, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()[:10]


def stamp(docs):
    docs = os.path.abspath(docs)
    data_dir = os.path.join(docs, "data")
    man_path = os.path.join(data_dir, "manifest.json")
    meta_path = os.path.join(data_dir, "meta.json")
    encrypted = os.path.exists(meta_path) and not os.path.exists(man_path)
    if encrypted:  # 加密站（tools/encrypt_data.py）：manifest 已是 .bin，build 記在明文 meta.json
        with open(meta_path, "rb") as f:
            build = json.loads(f.read().decode("utf-8")).get("build")
        if not build:
            raise SystemExit("meta.json has no build")
    else:
        with open(man_path, "rb") as f:
            man = json.loads(f.read().decode("utf-8"))
        build = man.get("build")
        if not build:
            build = data_build(data_dir)
            man["build"] = build
            with open(man_path, "wb") as f:
                f.write(json.dumps(man, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))
    assets = os.path.join(docs, "assets")
    fh = {}
    for p in sorted(glob.glob(os.path.join(assets, "*.js")) + glob.glob(os.path.join(assets, "*.css"))):
        with open(p, "rb") as f:
            fh[os.path.basename(p)] = sha(f.read())
    app = sha("".join("%s=%s;" % kv for kv in sorted(fh.items())).encode("utf-8"))
    chart = fh.get("chart.umd.min.js", "")

    ix_path = os.path.join(docs, "index.html")
    with open(ix_path, "r", encoding="utf-8") as f:
        html = f.read()
    orig = html

    def ref(m):
        name = m.group(2)
        return m.group(1) + "assets/" + name + ("?v=" + fh[name] if name in fh else "") + m.group(4)
    html = re.sub(r'((?:src|href)=")assets/([\w.-]+\.(?:js|css))(\?v=[0-9a-zA-Z]*)?(")', ref, html)
    html = re.sub(r'<meta name="ams-build"[^>]*>',
                  '<meta name="ams-build" content="%s" data-app="%s" data-chart="%s">' % (build, app, chart), html)
    html = re.sub(r'(<link rel="preload" href=")data/(?:meta|manifest)\.json(\?v=[0-9a-zA-Z]*)?(")',
                  r'\g<1>data/%s.json?v=%s\g<3>' % ("meta" if encrypted else "manifest", build), html)
    if html != orig:
        with open(ix_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
    ver = {"build": build, "app": app}
    with open(os.path.join(docs, "version.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(ver, separators=(",", ":")))
    return ver


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(here), "docs")
    print(json.dumps(stamp(d)))
