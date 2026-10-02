# -*- coding: utf-8 -*-
r"""tools/db/hmi_shots.py — 把圖控 HMI 畫面（GE CIMPLICITY／ActivePoint .cim）的 ThumbNail 設計時影像渲染成縮圖。

.cim 是 OLE 複合文件；其中 ThumbNail 串流是一張 **EMF+（EMF dual）** 全畫面設計時影像。
473 個 .cim 裡有 156 個帶 ThumbNail（其餘多為沒存縮圖的畫面與面板）。

渲染路徑：olefile 取出 ThumbNail → .emf →（PowerShell + GDI+ System.Drawing.Imaging.Metafile）→ 原生像素 PNG
→ PIL 縮到 --width、存 WebP。
**不要改用 PIL 直接開 .emf**：PIL 走 GDI PlayEnhMetaFile，不懂 EMF+ 記錄，實測只畫出幾條線（近乎空白）。
只有 GDI+ 的 Metafile 會播放 EMF+，畫面才完整。

座標系：ActivePoint 全畫面一律是 **1920x1080**；rclBounds 多半略大（1921~1924 x 1080~1126），
少數畫面物件畫到可視區外（最寬 5006）。本工具對「全畫面」型（bounds ≥ 1600x900）一律以固定的
**螢幕矩形 (0,0,1920,1080)**（--screen 可改）當畫布，可視區外的內容自然裁掉，輸出影像的座標系 == 畫面裝置座標系
（任務 A 的 x/y 比例可直接乘上去）；小尺寸的面板（faceplate）則以 bounds 當畫布，不放大。

**不要拿 EMF 標頭的 szlDevice 當畫布**：szlDevice 是「錄製當時的視窗／裝置解析度」，156 張裡有 3 張不是 1920x1080
（Controllable_Parameters_Pri_UX／Sec_UX = 1898x974、tp_actPt_objects_Hsinta = 1920x1200），
前兩張的 rclBounds 明明是 1921x1080 的滿版畫面，照 szlDevice 裁會砍掉右 23px 與底 106px（含底部 ActivePoint HMI 狀態列），
而且影像座標系會與真正的畫面座標系對不上。這 3 張在 index.json 標 `device_mismatch: true`。
index.json 內記下 bounds／canvas／device（原始 szlDevice）／scale 供回推。

用法：
  py tools/db/hmi_shots.py                                   # 全部，輸出到 %LOCALAPPDATA%\AMS\cardwork\hmi_shots
  py tools/db/hmi_shots.py --width 1280 --format webp
  py tools/db/hmi_shots.py --only list.txt                   # 每行一個檔名（可含子目錄；大小寫不拘）
  py tools/db/hmi_shots.py --screens D:\Screens --out D:\out

輸出：
  <out>/<slug>.webp|png
  <out>/index.json  {"<檔名.cim>":{"file","w","h","bytes","source","bounds","canvas","device","scale","dup_of","flags"}}
"""
import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

try:
    import olefile
except ImportError:
    sys.exit('缺 olefile：py -m pip install olefile')
try:
    from PIL import Image
except ImportError:
    sys.exit('缺 Pillow：py -m pip install pillow')

FULL_MIN_W, FULL_MIN_H = 1600, 900      # bounds 大於這個就當「全畫面」，改用固定螢幕矩形當畫布
SCREEN_W, SCREEN_H = 1920, 1080         # ActivePoint 全畫面的螢幕矩形（--screen 可改）；不可用 szlDevice 代替，見模組說明
BLANK_NONBG = 0.02                      # 非背景像素比例低於此 → 標記 blank
BLANK_UNIQ = 20                         # 量化後不同顏色數低於此 → 標記 flat
DARK_LUMA = 20                          # 平均亮度低於此 → 標記 dark

PS1 = r'''
param([string]$Jobs, [string]$Log)
Add-Type -AssemblyName System.Drawing
$out = New-Object System.Collections.Generic.List[string]
foreach ($line in [System.IO.File]::ReadAllLines($Jobs, [System.Text.Encoding]::UTF8)) {
  if ([string]::IsNullOrWhiteSpace($line)) { continue }
  $f = $line -split "`t"
  $src = $f[0]; $dst = $f[1]
  $cw = [int]$f[2]; $ch = [int]$f[3]
  $dx = [int]$f[4]; $dy = [int]$f[5]; $dw = [int]$f[6]; $dh = [int]$f[7]
  $mf = $null; $bmp = $null; $g = $null
  try {
    $mf = New-Object System.Drawing.Imaging.Metafile($src)
    $b = $mf.GetMetafileHeader().Bounds
    $bmp = New-Object System.Drawing.Bitmap($cw, $ch, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::White)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $rect = New-Object System.Drawing.Rectangle($dx, $dy, $dw, $dh)
    $g.DrawImage($mf, $rect)
    $g.Dispose(); $g = $null
    $bmp.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
    $out.Add("OK`t$src`t" + $b.X + "`t" + $b.Y + "`t" + $b.Width + "`t" + $b.Height)
  } catch {
    $out.Add("ERR`t$src`t" + ($_.Exception.Message -replace "[`t`r`n]", " "))
  } finally {
    if ($g) { $g.Dispose() }
    if ($bmp) { $bmp.Dispose() }
    if ($mf) { $mf.Dispose() }
  }
}
[System.IO.File]::WriteAllLines($Log, $out, (New-Object System.Text.UTF8Encoding($false)))
'''


def find_cims(root):
    out = []
    for dp, dn, fns in os.walk(root):
        for fn in fns:
            if fn.lower().endswith('.cim'):
                out.append(os.path.join(dp, fn))
    out.sort()
    return out


def screen_keys(root, cims):
    """檔名唯一就用檔名當 key；全 473 檔裡有同名的，用相對路徑（/）當 key 以免撞號。"""
    cnt = Counter(os.path.basename(p).lower() for p in cims)
    keys, collided = {}, []
    for p in cims:
        bn = os.path.basename(p)
        if cnt[bn.lower()] > 1:
            keys[p] = os.path.relpath(p, root).replace(os.sep, '/')
            collided.append(keys[p])
        else:
            keys[p] = bn
    return keys, sorted(collided)


def read_thumbnail(path):
    """回傳 ThumbNail 串流 bytes；沒有就 None。串流名大小寫不一，一律 lower() 比對。"""
    try:
        ole = olefile.OleFileIO(path)
    except Exception as e:
        return ('ERR', repr(e))
    try:
        for parts in ole.listdir():
            if len(parts) == 1 and parts[0].lower() == 'thumbnail':
                return ('OK', ole.openstream(parts[0]).read())
        return ('NONE', None)
    except Exception as e:
        return ('ERR', repr(e))
    finally:
        ole.close()


def emf_header(data):
    """EMF ENHMETAHEADER → bounds(l,t,r,b)、device(w,h)、frame(0.01mm)。非 EMF 回 None。"""
    if len(data) < 88:
        return None
    itype, nsize = struct.unpack('<II', data[0:8])
    if itype != 1 or data[40:44] != b' EMF':
        return None
    bl, bt, br, bb = struct.unpack('<4i', data[8:24])
    fl, ft, fr, fb = struct.unpack('<4i', data[24:40])
    devw, devh = struct.unpack('<2i', data[72:80])
    return dict(bounds=[bl, bt, br, bb], frame=[fl, ft, fr, fb], device=[devw, devh],
                bw=br - bl + 1, bh=bb - bt + 1)


def slug(key):
    s = re.sub(r'\.cim$', '', key, flags=re.I)
    return re.sub(r'[^0-9A-Za-z._-]+', '_', s.replace('/', '__'))


def content_stats(im):
    """背景不一定是白的：取量化後的眾數當背景色，算非背景比例、顏色數、平均亮度。"""
    small = im.convert('RGB')
    if small.width > 480:
        small = small.resize((480, max(1, round(480 * small.height / small.width))), Image.BILINEAR)
    px = list(getattr(small, 'get_flattened_data', small.getdata)())
    q = [(r >> 4, g >> 4, b >> 4) for r, g, b in px]
    cnt = Counter(q)
    bg, bgn = cnt.most_common(1)[0]
    nonbg = 1.0 - bgn / len(q)
    luma = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in px) / len(px)
    flags = []
    if nonbg < BLANK_NONBG:
        flags.append('blank')
    if len(cnt) < BLANK_UNIQ:
        flags.append('flat')
    if luma < DARK_LUMA:
        flags.append('dark')
    return dict(nonbg=round(nonbg, 4), colors=len(cnt), luma=round(luma, 1),
                bg=[bg[0] * 17, bg[1] * 17, bg[2] * 17], flags=flags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--screens', default=paths.HMI_SCREENS)
    ap.add_argument('--out', default=paths.HMI_SHOTS)
    ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--format', choices=['webp', 'png'], default='webp')
    ap.add_argument('--quality', type=int, default=78)
    ap.add_argument('--only', help='清單檔，每行一個 .cim（檔名或相對路徑，大小寫不拘）')
    ap.add_argument('--screen', default='%dx%d' % (SCREEN_W, SCREEN_H),
                    help='全畫面型的螢幕矩形 WxH（預設 1920x1080；固定值，不隨 szlDevice 變）')
    ap.add_argument('--keep-tmp', action='store_true')
    args = ap.parse_args()

    m = re.fullmatch(r'(\d+)x(\d+)', args.screen.strip().lower())
    if not m:
        sys.exit('--screen 要寫成 WxH，例如 1920x1080')
    scr_w, scr_h = int(m.group(1)), int(m.group(2))

    root = os.path.abspath(args.screens)
    if not os.path.isdir(root):
        sys.exit('找不到畫面目錄：%s（可用 AMS_HMI_SCREENS 覆寫）' % root)
    os.makedirs(args.out, exist_ok=True)

    cims = find_cims(root)
    keys, collided = screen_keys(root, cims)
    print('畫面檔 %d 個（%s）' % (len(cims), root))
    if collided:
        print('  ※ 檔名重複 %d 個，key 改用相對路徑：%s' % (len(collided), ', '.join(collided)))

    if args.only:
        want = set()
        with open(args.only, encoding='utf-8') as f:
            for line in f:
                line = line.strip().replace('\\', '/')
                if line and not line.startswith('#'):
                    want.add(line.lower())
        cims = [p for p in cims if os.path.basename(p).lower() in want
                or os.path.relpath(p, root).replace(os.sep, '/').lower() in want]
        print('  --only 篩出 %d 個' % len(cims))

    # 1) 取 ThumbNail、解 EMF 標頭、以 sha1 去重
    jobs, skipped, errors = [], [], []
    by_sha = {}
    tmp = tempfile.mkdtemp(prefix='hmishots_')
    for p in cims:
        key = keys[p]
        st, data = read_thumbnail(p)
        if st == 'NONE':
            skipped.append(key)
            continue
        if st == 'ERR':
            errors.append((key, 'OLE: ' + data))
            continue
        h = hashlib.sha1(data).hexdigest()
        hdr = emf_header(data)
        if not hdr:
            errors.append((key, 'ThumbNail 不是 EMF（%d bytes）' % len(data)))
            continue
        if h in by_sha:
            by_sha[h]['dups'].append(key)
            continue
        emf = os.path.join(tmp, h + '.emf')
        with open(emf, 'wb') as f:
            f.write(data)
        bl, bt, br, bb = hdr['bounds']
        devw, devh = hdr['device']
        full = hdr['bw'] >= FULL_MIN_W and hdr['bh'] >= FULL_MIN_H
        if full:
            canvas = [0, 0, scr_w, scr_h]        # 全畫面：畫布＝固定螢幕矩形，可視區外裁掉
        else:
            canvas = [bl, bt, hdr['bw'], hdr['bh']]   # 面板：畫布＝bounds，不裁不放大
        png = os.path.join(tmp, h + '.png')
        jobs.append(dict(key=key, sha=h, emf=emf, png=png, hdr=hdr, canvas=canvas, full=full,
                         dest=[bl - canvas[0], bt - canvas[1], hdr['bw'], hdr['bh']],
                         raw=len(data), dups=[]))
        by_sha[h] = jobs[-1]

    print('有 ThumbNail %d、無 %d、讀取失敗 %d；去重後要渲染 %d'
          % (len(jobs) + sum(len(j['dups']) for j in jobs), len(skipped), len(errors), len(jobs)))
    for j in jobs:
        if j['dups']:
            print('  重複 sha1：%s == %s' % (j['key'], ', '.join(j['dups'])))
    if not jobs:
        sys.exit('沒有可渲染的畫面')

    # 2) 一次 PowerShell 批次渲染（每次啟動 PowerShell 很慢，絕不逐檔啟動）
    ps1 = os.path.join(tmp, 'render.ps1')
    with open(ps1, 'w', encoding='utf-8') as f:
        f.write(PS1)
    jobs_tsv = os.path.join(tmp, 'jobs.tsv')
    with open(jobs_tsv, 'w', encoding='utf-8') as f:
        for j in jobs:
            f.write('%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n'
                    % (j['emf'], j['png'], j['canvas'][2], j['canvas'][3],
                       j['dest'][0], j['dest'][1], j['dest'][2], j['dest'][3]))
    log = os.path.join(tmp, 'render.log')
    print('渲染中（GDI+，%d 張）…' % len(jobs))
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                        '-File', ps1, '-Jobs', jobs_tsv, '-Log', log],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit('PowerShell 渲染失敗 rc=%d' % r.returncode)
    res = {}
    with open(log, encoding='utf-8') as f:
        for line in f:
            c = line.rstrip('\n').split('\t')
            res[c[1]] = c

    # 3) PIL 縮圖 + 內容檢查 + index.json
    index, failed, mismatch = {}, [], []
    for j in jobs:
        c = res.get(j['emf'])
        if not c or c[0] != 'OK':
            failed.append((j['key'], c[2] if c and len(c) > 2 else '渲染無輸出'))
            continue
        gx, gy, gw, gh = (int(x) for x in c[2:6])
        if abs(gw - j['hdr']['bw']) > 2 or abs(gh - j['hdr']['bh']) > 2 \
           or abs(gx - j['hdr']['bounds'][0]) > 2 or abs(gy - j['hdr']['bounds'][1]) > 2:
            mismatch.append((j['key'], [gx, gy, gw, gh], j['hdr']['bounds'][:2] + [j['hdr']['bw'], j['hdr']['bh']]))
        try:
            im = Image.open(j['png'])
            im.load()
        except Exception as e:
            failed.append((j['key'], 'PIL 開 PNG 失敗 ' + repr(e)))
            continue
        cw, ch = im.size
        if args.width and cw > args.width:          # 只縮不放大
            nh = max(1, round(ch * args.width / cw))
            im = im.resize((args.width, nh), Image.LANCZOS)
        stats = content_stats(im)
        name = slug(j['key']) + '.' + args.format
        dst = os.path.join(args.out, name)
        try:
            if args.format == 'webp':
                im.convert('RGB').save(dst, 'WEBP', quality=args.quality, method=5)
            else:
                im.convert('RGB').save(dst, 'PNG', optimize=True)
        except Exception as e:
            name = slug(j['key']) + '.png'
            dst = os.path.join(args.out, name)
            im.convert('RGB').save(dst, 'PNG', optimize=True)
            print('  %s：%s 存檔失敗（%r），退回 PNG' % (j['key'], args.format, e))
        entry = dict(file=name, w=im.width, h=im.height, bytes=os.path.getsize(dst),
                     source='ThumbNail EMF', bounds=j['hdr']['bounds'], canvas=j['canvas'],
                     device=j['hdr']['device'], scale=round(im.width / j['canvas'][2], 6),
                     cropped=bool(j['hdr']['bw'] - j['canvas'][2] > 4 or j['hdr']['bh'] - j['canvas'][3] > 4
                                  or j['canvas'][0] - j['hdr']['bounds'][0] > 4 or j['canvas'][1] - j['hdr']['bounds'][1] > 4),
                     sha1=j['sha'], **{k: v for k, v in stats.items()})
        if j['full'] and j['hdr']['device'] != [scr_w, scr_h]:
            # szlDevice（錄製當時的視窗／裝置解析度）不等於螢幕矩形 → 這張不要拿 device 當座標基準
            entry['device_mismatch'] = True
        index[j['key']] = entry
        for d in j['dups']:
            index[d] = dict(entry, dup_of=j['key'])

    with open(os.path.join(args.out, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1, sort_keys=True)

    if not args.keep_tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print('暫存保留：%s' % tmp)

    uniq = {e['file'] for e in index.values()}
    total = sum(os.path.getsize(os.path.join(args.out, f)) for f in uniq)
    big = max(((e['bytes'], k) for k, e in index.items()), default=(0, ''))
    print('\n完成：%d 個畫面有影像（實體檔 %d 個）' % (len(index), len(uniq)))
    print('  總位元組 %.1f MB、單檔最大 %d bytes（%s）、平均 %d bytes'
          % (total / 1048576.0, big[0], big[1], total // max(1, len(uniq))))
    flagged = {k: e['flags'] for k, e in index.items() if e['flags']}
    print('  內容可疑（blank/flat/dark）%d：%s' % (len(flagged), json.dumps(flagged, ensure_ascii=False)))
    print('  裁切過（內容超出可視區）%d' % sum(1 for e in index.values() if e['cropped']))
    dm = sorted(k for k, e in index.items() if e.get('device_mismatch'))
    print('  szlDevice ≠ 螢幕矩形 %dx%d（已改用螢幕矩形）%d：%s' % (scr_w, scr_h, len(dm), ', '.join(dm) or '無'))
    if mismatch:
        print('  GDI+ 與 EMF 標頭 bounds 不一致 %d：%s' % (len(mismatch), mismatch[:10]))
    if failed:
        print('  渲染失敗 %d：' % len(failed))
        for k, e in failed:
            print('    %s  %s' % (k, e))
    if errors:
        print('  讀檔失敗 %d：%s' % (len(errors), errors))
    print('  無 ThumbNail %d 個（不產圖）' % len(skipped))
    print('  index.json → %s' % os.path.join(args.out, 'index.json'))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
