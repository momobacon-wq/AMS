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
index.json 內記下 bounds／canvas／device（原始 szlDevice）／scale 供回推（**這是設計時那一筆**；有執行時截圖的畫面，
那一筆會整包搬到 `emf` 子物件下，頂層換成執行時那張的欄位——見下面「輸出」）。

**為什麼要遮掉畫面邊框（chrome）**：縮圖看起來「很多殘影」——左側導覽樹整片文字疊在一起、左上角三組 ### 錶框互疊、
紅字「Screen was not found in navigation.」壓在「Loading...」上、選單列 `Block1` 疊著 `Plant`。
這**不是渲染器的 bug**（製程圖區乾淨，GDI+ 又是 EMF+ 的參考實作），而是 **CimEdit 存設計時快照時把所有分支一起畫出來**：
執行時才用 visibility 動畫只顯示其中一組，快照沒有動畫，於是每一組都畫了。實測 BOP_Feed_Water 的 1485 筆 DrawString
有 532 筆落在只能顯示 21~28 列的導覽面板內（列距 26px、面板高 742px），**過繪約 19~25 倍**；
211 個相異原點叢集裡 139 個擠了 2 筆以上，最大一叢 13 筆完全同點，內容正好對應選單列的 13 個機組分頁。
已排除「GDI+ 丟掉裁剪」這個競爭解釋：全檔 EMF+ 只有兩筆裁剪記錄（一個 19x18 的「?」說明圖示框，隨即被 Infinite region 取消），
導覽樹第一筆字串在那之後，繪製時裁剪已是無限大；GDI 層 12 組 EMR_EXTSELECTCLIPRGN 也全是 26x27 圖示框或 2x133 細線。

因此在**原生 1920x1080 PNG 階段**（GDI+ 輸出之後、PIL 縮圖之前）把堆疊的 chrome 區塊用該區取樣到的背景色塗平。
不裁切：裁掉會動到座標基準，index.json／card.js 的標記換算／CONTRACT／aux 全要改，而 hmi.json 的 744 筆全畫面標記
**沒有一筆**落在這些 chrome 區（最接近的左緣 x=213.47，所以導覽右緣訂在 213 不可再往右），裁切毫無好處。
也不做 EMF+ 記錄外科手術：+ 圖示與錶框是 FillPolygon／DrawLines／FillRects 一樣在疊，改完還是得遮。
**逐張判斷才遮**（見 mask_rects）：只對全畫面型、且真的數到堆疊的畫面套用；faceplate 小圖與沒有 chrome 的樣板頁一律不遮。

**執行時截圖優先（2026-10-04 起）**：設計時快照再怎麼塗平，值還是 ###、標題還是 CAPTION 佔位。使用者 2026-10-04
在機組上逐頁拍了執行時畫面（`Screens\圖控\*.xlsx` 內嵌 PNG，290 張、全部 1920x1080），對應表由 `hmi_runtime_map.py`
離線產生並 commit 成 `tools/db/hmi_runtime_map.json`（本工具只讀表、不做 OCR）。**截圖的解析度正好就是標記所用的裝置
座標系**，實測把 hmi.json 的標記疊到執行時截圖與疊到同一張設計時縮圖，落點像素級一致，所以是原位替換、不動任何換算。
有截圖的畫面：`file`／`w`／`h`／`bytes`／`source` 改指執行時那張，原本的設計時那筆**整包**搬到 `emf`（不丟）；
`runtime.variants` 逐「選單機組」各一張（同一張畫面在 HRSG11／HRSG12 是兩份不同的現值，不可共用一張）。
`--no-runtime` 完全不碰，輸出與沒有這段程式時逐位元組相同。

用法：
  py tools/db/hmi_shots.py                                   # 全部，輸出到 %LOCALAPPDATA%\AMS\cardwork\hmi_shots
  py tools/db/hmi_shots.py --width 1280 --format webp
  py tools/db/hmi_shots.py --only list.txt                   # 每行一個檔名（可含子目錄；大小寫不拘）
  py tools/db/hmi_shots.py --screens D:\Screens --out D:\out
  py tools/db/hmi_shots.py --no-mask --out D:\before         # 不遮（回溯比對用）
  py tools/db/hmi_shots.py --no-runtime --out D:\emfonly     # 只出設計時縮圖（回溯比對用）

輸出：
  <out>/<slug>.webp|png                     設計時（ThumbNail EMF）縮圖
  <out>/<slug>__<選單機組>.webp|png          執行時截圖（有對應表的畫面才有；機組去掉結尾的點，如 H11.→H11）
  <out>/index.json  {"<檔名.cim>":{"file","w","h","bytes","source","canvas","device","scale","flags",…}}
                   **每一筆的 file／w／h／bytes／source 一律是「這個畫面要發布的那張影像」**：
                     有執行時截圖 → source="runtime capture"，另有
                                    "runtime":{"captured","primary","variants":{選單機組:{file,w,h,bytes,book,anchor,src_sha1,crumb,…}},
                                               "skipped":{選單機組:原因}（只有真的被閘門擋掉時才有）}，
                                    而設計時那筆（含 bounds／cropped／sha1／masked／mask_metrics／device_mismatch）原封不動搬進 "emf"；
                                    **頂層的 device 是截圖解析度（＝螢幕矩形），不是 EMF 標頭的 szlDevice**，
                                    bounds／cropped／sha1／device_mismatch 只存在於 "emf" 子物件（上面第 17~21 行講的那三張就是這種）。
                                    **primary ＝對應表裡 (book, anchor) 最前、而且通過 sha1／尺寸閘門的那個選單機組**，
                                    `file` 指著它；前端挑不到自己那一列的機組時會退到它，所以被閘門擋掉而讓 primary 往後滑的那些
                                    一定要記在 "skipped" 裡（不然 index.json 看不出少了誰）。
                     沒有          → source="ThumbNail EMF"，欄位同 2026-10-03 版，沒有 "runtime"／"emf" 鍵。
                   設計時那筆的欄位：{"file","w","h","bytes","source","bounds","canvas","device","scale","dup_of","flags",
                                   "masked":{"nav":[l,t,r,b],"loading":…,"menubar":…,"banner":…}
                                             （原生裝置座標、只列真的塗掉的矩形；沒遮就是 {}）,
                                   "mask_metrics":{nav_pairs,nav_strings,banner_pairs,banner_strings,
                                                   nav_bottom,nav_vocab_ignored}}
                   mask_metrics 的鍵**是條件性的**，讀的時候一律用 .get()：
                     只有評估過遮罩的全畫面型才有這個鍵（faceplate 根本沒有，2026-10-03 語料 112/156）；
                     nav_pairs／nav_strings 一定有；banner_pairs／banner_strings／nav_bottom 只在過了 nav 門檻的那幾張（109）；
                     nav_vocab_ignored 只在真的有命中被樓地板忽略時才寫（今天 0 張）。
"""
import argparse
import hashlib
import io
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
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

RUNTIME_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hmi_runtime_map.json')   # hmi_runtime_map.py 的輸出（commit 進 repo）
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


# ---------------------------------------------------------------- 執行時截圖（hmi_runtime_map.json → webp）
def unit_slug(unit):
    """選單機組 'H11.' → 'H11'（檔名用；結尾的點是 CIMPLICITY 的前綴寫法，不是副檔名）。"""
    return re.sub(r'[^0-9A-Za-z._-]+', '_', (unit or '').rstrip('.')) or 'x'


def runtime_shots(map_path, screens_root, allow_keys, out_dir, width, fmt, quality, scr_w, scr_h):
    """讀 hmi_runtime_map.json，把活頁簿裡的執行時截圖縮成 webp，回傳 {cim_key: runtime 區塊}。

    每張都核對 PNG 的 sha1 與尺寸：活頁簿被重拍／重排過就會對不上，寧可少一張也不默默貼錯圖。
    **截圖必須是 scr_w x scr_h**（＝標記的裝置座標系）；不是就跳過，因為縮圖的 x/y 比例會對不上標記。
    allow_keys＝這次要處理的畫面 key（大小寫原樣）；None 代表不限制。"""
    if not os.path.exists(map_path):
        print('※ 沒有執行時截圖對應表 %s → 只出設計時縮圖' % map_path)
        return {}, []
    with open(map_path, encoding='utf-8') as f:
        rm = json.load(f)
    if rm.get('kind') != 'hmi_runtime_map':
        print('※ %s 不是 hmi_runtime_map（kind=%r）→ 只出設計時縮圖' % (map_path, rm.get('kind')))
        return {}, []
    sdir = os.path.join(screens_root, rm.get('subdir') or '圖控')
    if not os.path.isdir(sdir):
        print('※ 對應表指的截圖目錄不存在：%s → 只出設計時縮圖' % sdir)
        return {}, []
    allow = {k.lower() for k in allow_keys} if allow_keys is not None else None
    books, out, notes = {}, {}, []
    captured = rm.get('captured')
    for key in sorted(rm.get('screens') or {}):
        if allow is not None and key.lower() not in allow:
            continue
        # skipped_units＝對應表裡有、但這次沒產出來的機組（閘門擋掉）。一定要留下來：
        # 少一組時 primary 會順勢滑到下一個機組，那張圖就會被拿去配別台機組的位號，而 index.json 看不出少了誰
        variants, primary, skipped_units = {}, None, {}
        for unit, v in sorted((rm['screens'][key]).items(), key=lambda kv: (kv[1].get('book', ''), kv[1].get('anchor', 0))):
            bk = v['book']
            if bk not in books:
                bp = os.path.join(sdir, bk)
                if not os.path.exists(bp):
                    books[bk] = None
                else:
                    books[bk] = zipfile.ZipFile(bp)
            zf = books[bk]
            if zf is None:
                # 逐 (畫面, 機組) 各記一則：只在「第一個用到這本」的畫面名下記一則，
                # 等於一本活頁簿不見時整批截圖默默消失，而訊息還掛在不相干的畫面上
                skipped_units[unit] = '活頁簿 %s 不在' % bk
                notes.append((key, '%s 的 %s 不在 → 這一組沒有影像' % (unit, bk)))
                continue
            try:
                raw = zf.read(v['media'])
            except KeyError:
                skipped_units[unit] = '%s 裡沒有 %s' % (bk, v['media'])
                notes.append((key, '%s：%s' % (unit, skipped_units[unit])))
                continue
            got = hashlib.sha1(raw).hexdigest()
            if got != v['sha1']:
                skipped_units[unit] = ('%s#%d sha1 不符（表 %s、檔 %s）→ 活頁簿換過了，請重跑 hmi_runtime_map.py'
                                       % (bk, v['anchor'], v['sha1'][:10], got[:10]))
                notes.append((key, '%s：%s' % (unit, skipped_units[unit])))
                continue
            im = Image.open(io.BytesIO(raw))
            im.load()
            if im.size != (scr_w, scr_h):
                skipped_units[unit] = ('%s#%d 是 %dx%d，不是 %dx%d（座標基準會對不上）'
                                       % (bk, v['anchor'], im.width, im.height, scr_w, scr_h))
                notes.append((key, '%s：%s' % (unit, skipped_units[unit])))
                continue
            im = im.convert('RGB')
            if width and im.width > width:
                im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
            name = '%s__%s.%s' % (slug(key), unit_slug(unit), fmt)
            if name in {x['file'] for x in variants.values()}:
                # 兩個不同的選單機組被 unit_slug 洗成同一個檔名 → 後者會蓋掉前者，等於把別的機組的現值端出去
                skipped_units[unit] = '檔名與既有變體相撞（%s）；unit_slug 要能分開這兩個機組' % name
                notes.append((key, '%s：%s' % (unit, skipped_units[unit])))
                continue
            dst = os.path.join(out_dir, name)
            if fmt == 'webp':
                im.save(dst, 'WEBP', quality=quality, method=5)
            else:
                im.save(dst, 'PNG', optimize=True)
            variants[unit] = dict(file=name, w=im.width, h=im.height, bytes=os.path.getsize(dst),
                                  book=bk, anchor=v['anchor'], src_sha1=v['sha1'], crumb=v.get('crumb'),
                                  **{k: val for k, val in content_stats(im).items()})
            if primary is None:
                primary = unit
        if variants:
            out[key] = {'captured': captured, 'primary': primary, 'variants': variants}
            if skipped_units:
                out[key]['skipped'] = skipped_units
    for zf in books.values():
        if zf is not None:
            zf.close()
    return out, notes


# ---------------------------------------------------------------- 設計時堆疊遮罩（chrome）
# 四個矩形都是**原生裝置座標**（1920x1080 畫布的像素），由實測推導、不是目測：
#   nav     重疊連通元件 [0,208,208,912] 有 33969 組重疊字串對，比第二名高 187 倍；右緣 213 是硬上限
#           （最近的位號標記左緣 x=213.47，差 0.47px），底緣取面板本體下界 1048（逐列掃描：面板底色到 1048~1052 為止）
#           再由 MASK_VOCAB 逐張往上夾。**底緣不可以只取 949**：導覽樹最後一列會垂到 956~960，
#           遮到 949 會把那一列從中間切半，留下半截字（UPS_*_SLD 的 VLP Drain Pot Level 最明顯）。
#           反過來也不可以無條件遮到 1048：46 張畫面在 y 958~1052 畫了真正的畫面按鈕（MASTER RESET／
#           DIAGNOSTIC RESET／####），所以一定要靠逐張夾限。實測 y≥949 的導覽欄字串**全部**屬 MASK_VOCAB，
#           夾限抓得乾淨：13 張夾到 925、33 張夾到 958~972、其餘 63 張維持 1048（那段原本就是空面板）。
#           （以 2026-10-03 語料實測；925 那 13 張＝12 張 ST_* ＋ Common_Tur_Gen_H2_Monitoring_UX。）
#   loading 紅字 (10,184)-(328,205) 疊在 Loading... (12,187)-(91,206) 上，109/112 張都有且只有這 1 組。
#           上緣 182 是為了不切到 GE VERNOVA（box 底 180）與 logo 的 g（179）；下緣 205 是為了不切到
#           8 張畫面 y=205 起的螢幕標題（HP Group／Inlet System…）。代價：Loading... 下緣 1px 殘留，縮圖後看不見。
#   banner  橫幅唯一真正堆疊處：(290,42)/(290,76)/(290,110) 各疊 5 筆 H|HH|HHH|LL|LLL 限值標籤＋### 疊 #####。
#           左緣 224 = 台電 logo 白底面板右界。
#   menubar Block1 (232,136)-(298,167) 與分頁 Plant (286,…)-(341,…) 水平疊 12px（佔較小框 0.218，低於 0.25
#           門檻所以配對數抓不到，但使用者明確抱怨）。左緣必須 213（UPS_*_SLD 是 Block8，left=214）；
#           右緣 370（分頁 G11 left=371）。代價：一併蓋掉每張都一樣、不帶畫面資訊的 Plant 分頁標籤。
MASK_NAV = (0, 207, 213, 1048)
MASK_LOADING = (0, 182, 334, 205)
MASK_BANNER = (224, 0, 450, 133)
MASK_MENUBAR = (213, 136, 370, 177)
# nav 底緣夾限的**樓地板**：只有 top >= 這條線的 MASK_VOCAB 命中才拿來夾（見 nav_clamp）。
# 沒有樓地板的話，nav 區帶（y 207~1048）上半部任何一筆命中都會把矩形整片吃掉：實證 tp_actPt_objects_Hsinta.cim
# 的 #### 在 nav 區帶內 top=280.3，無樓地板會夾成 nb=273（矩形只剩 66px 高、導覽樹整片留著）；
# 再低一點（top 210）矩形會退化成 <2px 被 apply_mask 丟掉，整個 nav 一點都沒遮，而且是靜默的。
# 900 的依據：全庫真正要夾的按鈕最高一筆是 top=932.2（#### 按鈕），離 900 還有 32px 餘裕；
# 導覽樹最後一列垂到 956~960，畫面自己的按鈕全部在 y>=926 → 900 這條線兩邊都不碰。
# 另一個作用：MASK_FILL['nav'] 的 probe 底緣就取「樓地板減掉夾限留白」＝最低可能的夾限線，
# 所以「probe 一定在夾限線以上」是由構造保證的，不是兩個剛好對得上的數字。
# 被樓地板忽略掉的命中會記進 mask_metrics.nav_vocab_ignored 並在結尾印警告（不靜默）。
MASK_NAV_FLOOR = 900
MASK_NAV_GAP = 7                 # 夾限留白：底緣夾到按鈕上緣再往上這麼多（最低可能的底緣＝900-7＝893）
# 門檻：全畫面型 112 張的 nav 配對數實測是 0(x3) 與 3251~4699(x109)，面板型最高只有 90 → 放 1000 極安全（間隙 36 倍）。
# banner 配對數是 0(x4)／3(x2)／22~88(x106)，3 → 22 之間沒有任何畫面 → 放 20。
# banner 低於門檻的兩張 Controllable_Parameters_* 橫幅不是錶框而是 AMBIENT/Temp/Press/RH 環境條件（真實內容），
# 這條判斷就是「不可一視同仁套樣板矩形」的理由，不要拿掉。
MASK_NAV_PAIRS = 1000
MASK_BANNER_PAIRS = 20
# 填色一律**逐張取樣**，不可寫死（寫死就是貼膠帶）。取樣區一定要挑「這張圖上確定沒有內容」的乾淨區，
# 不可以拿整個矩形的眾數：選單列矩形上緣含橫幅深底會取到 (45,45,47)，
# 導覽矩形在 3 張 UPS 畫面疊字太密會取到 (0,0,0)。乾淨區在矩形外或矩形內都可以，逐帶各挑；
# 兩種取法，依該帶是不是純色決定（實測）：
#   flat 純色帶（nav）→ 單一 probe 區取眾數。導覽面板整片 (191,194,197)。
#     nav 的 probe **落在矩形內部**（不是矩形外——nav 右邊緊鄰製程圖，矩形外沒有乾淨區可取）：
#     取右緣那條 x 180~208 的細帶，導覽樹的字絕大多數在 x<180，這條細帶幾乎只有面板底色。
#     y 取 840~(MASK_NAV_FLOOR - MASK_NAV_GAP)＝893＝**最低可能的夾限線**，所以永遠取不到
#     夾限線以下那塊「畫面自己的可見區」。原本取 y 960~1046 正是錯在這裡：那段在 46 張夾限過的畫面上
#     是 ####／MASTER RESET／DIAGNOSTIC RESET 按鈕所在（眾數佔比掉到 0.44~0.66），
#     結果對只是因為那些按鈕剛好也是灰的。以 2026-10-03 語料實測：新 probe 在 109 張的眾數佔比
#     最低 0.832、中位數 0.989，109 張全部取到 (191,194,197)（與舊 probe 同色，所以換 probe 不改輸出像素）。
#   rows 逐列帶（loading／menubar／banner）→ **同一列**往右取一段 donor 的眾數，一列一列填。
#     選單列是**垂直漸層**：標準版整條 (90,93,99)，但 3 張 UPS Block9 變體是 86→68 的漸層，拿單一色填會留亮塊；
#     而且有的畫面 y=176 整條是 (79,121,174) 藍色底線（BOP_Clean_Drain_System1），
#     有的畫面橫幅／選單列交界落在 y=142 而非 136（gtHA_Gen2_Hot_Restart_UX，136~140 其實還是橫幅深底）。
#     逐列取樣把這三種差異全部自動吃掉。各 donor 已驗過**每一列**背景都佔多數（全庫最低 0.55），所以逐列眾數必是背景色。
MASK_BG = {'nav': (191, 194, 197), 'loading': (191, 194, 197),
           'banner': (45, 45, 47), 'menubar': (90, 93, 99)}
MASK_FILL = {'nav': ('flat', 180, 840, 208, MASK_NAV_FLOOR - MASK_NAV_GAP),  # 導覽面板右緣細帶，夾限線以上（佔比 ≥0.83）
             'loading': ('rows', 600, 1000),         # 紅字列右側的同一帶
             'menubar': ('rows', 380, 1900),         # 分頁列右側（含分頁文字，但背景仍佔多數）
             'banner': ('rows', 700, 1900)}          # 橫幅右半（與緊鄰矩形右側的 donor 逐列比對過，109 張幾乎全一致）
# flat 帶（nav）取樣不可信時**整個矩形不塗**，不是改塗預設色：取樣不可信就是「這張圖的版型跟我們推導的不一樣」，
# 這時把一塊灰色塗在可能錯的位置，比留著疊影更糟（原廠換版型應該讓人看到原圖，再回來重訂矩形）。
# rows 帶（loading／menubar／banner）仍保留逐列退回預設：那三帶的 donor 每一列都驗過背景佔多數（全庫最低 0.55），
# 單列偶發不足退回預設只影響 1px 高，且矩形位置本身另有配對數門檻把關。
MASK_BG_TOL = 24                                   # flat probe 與預設色每通道差超過這個 → 不信 probe（flat 跳過不塗）
MASK_BG_FRAC = 0.30                                # 取樣區眾數佔比低於這個 → 不信（flat 跳過不塗；rows 該列退回預設）
# 畫面內容詞彙：這些字串出現在 nav 矩形內、且在 MASK_NAV_FLOOR 以下，代表「那不是導覽樹，是畫面自己的按鈕」
# → 底緣要夾到它上面。以 2026-10-03 語料實測（全畫面型 112 張）：
#   nav 區帶內有命中的 47 張，其中 46 張過了 nav 配對數門檻、真的夾了底緣
#     （13 張夾到 925：左下角的 #### 按鈕，box top 932.2、方塊實際自 926 起；
#       33 張 gtHA_Gen2_* 等夾到 958~972：MASTER RESET／DIAGNOSTIC RESET，top 965~979），
#     剩下 1 張 tp_actPt_objects_Hsinta 的 #### 在 top=280.3，nav 配對數是 0 本來就不遮，
#     就算哪天過了門檻也會被 MASK_NAV_FLOOR 忽略掉。其餘 63 張維持 1048。
#   真正會命中的只有 3 個詞：'####' 15 筆／14 張、'MASTER RESET' 46 筆／46 張、'DIAGNOSTIC RESET' 46 筆／46 張。
#   下面第二組 8 個詞**目前全庫零命中**，是預防性的（原廠改版型時同類佔位字／按鈕字可能換成這些寫法）；
#   留著零成本——有了樓地板，誤命中最多只能把底緣往上夾到 893，不會再吃掉導覽樹。
#   ※ 'DH' 其實是這套 chrome 的活字串：全庫 486 筆（全畫面型 468 筆），y<133 的橫幅區佔 259 筆，
#     其餘散在 y 200~966（最高 966.5）——只是沒有一筆落在 nav 區帶的 x 範圍內，所以 nav 這裡算零命中。
#     它是「預防性詞彙不等於不存在的詞彙」的例子：哪天有畫面把它畫到左欄，夾限就會被它拉動（有樓地板擋著，最壞也只到 893）。
# 已驗證：導覽欄裡 y≥949 的字串**沒有一筆**落在這份詞彙之外，所以夾限不會漏掉畫面自己的按鈕。
MASK_VOCAB = frozenset(('####', 'MASTER RESET', 'DIAGNOSTIC RESET') +          # 實測會命中
                       ('###', '#####', '##', 'CAPTION', 'Perm Text', 'MED-DUAL', 'LOAD CMD', 'DH'))  # 預防性、零命中

EMR_COMMENT = 70
_IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mmul(a, b):
    """2x3 仿射相乘（GDI+ 列向量慣例 [x y 1]·M）：回傳 a*b，點先經 a 再經 b。"""
    a11, a12, a21, a22, adx, ady = a
    b11, b12, b21, b22, bdx, bdy = b
    return (a11 * b11 + a12 * b21, a11 * b12 + a12 * b22,
            a21 * b11 + a22 * b21, a21 * b12 + a22 * b22,
            adx * b11 + ady * b21 + bdx, adx * b12 + ady * b22 + bdy)


def emfplus_payload(data):
    """EMF+ 的記錄流散在多個 EMR_COMMENT（ident 'EMF+'）裡，大記錄會跨分塊 → 必須先串接再解析。"""
    buf = bytearray()
    off, n = 0, len(data)
    while off + 8 <= n:
        itype, nsize = struct.unpack_from('<II', data, off)
        if nsize < 8 or off + nsize > n:
            break
        if itype == EMR_COMMENT and nsize >= 16:
            cb = struct.unpack_from('<I', data, off + 8)[0]
            end = min(off + 12 + cb, off + nsize)
            if data[off + 12:off + 16] == b'EMF+':
                buf += data[off + 16:end]
        off += nsize
    return bytes(buf)


def emfplus_strings(data):
    """解 ThumbNail 的 EMF+ 記錄流，累積世界×頁面變換，把每筆 DrawString 還原成**裝置座標**包圍盒。
    回傳 [dict(text, box=(l,t,r,b), org=(x,y))]。

    DrawString 記錄裡的 LayoutRect 是**區域座標**，真實位置在它前面那串世界變換
    （SetWorldTransform → Translate → Scale → Rotate）；拿 layout.x 直接當螢幕 x 過濾會全中，是錯的。
    乘法次序旗標是 bit13（set=Append→M·T，clear=Prepend→T·M）；CimEdit 每筆字串前都重設 SetWorldTransform，
    所以 bit13／0／2／11 四種解讀的結果完全相同（已驗），這裡照規格取 bit13。
    還原後的錨點與原生 PNG 對得上（ActivePoint™ HMI → (12.4,1058)-(146.2,1077)，各張一致），
    且**與 rclBounds 的負位移無關**（HRSG_HP_Group_UX 的 bounds 左緣 -961，導覽面板像素邊界與別張同在 x=208）。
    """
    buf = emfplus_payload(data)
    world, page, dpiy = _IDENT, _IDENT, 96.0
    stack, cont, fonts, pend = {}, [], {}, {}
    out = []
    off, n = 0, len(buf)
    while off + 12 <= n:
        rtype, flags, size, dsize = struct.unpack_from('<HHII', buf, off)
        if size < 12 or off + size > n:
            break
        d = buf[off + 12:off + 12 + dsize]
        off += size
        if rtype == 0x4001:                      # Header（取 dpiY，Point 字級要用）
            if len(d) >= 16:
                dy = struct.unpack_from('<I', d, 12)[0]
                if dy:
                    dpiy = float(dy)
        elif rtype == 0x402A:                    # SetWorldTransform（整個替換）
            world = struct.unpack_from('<6f', d, 0)
        elif rtype == 0x402B:                    # ResetWorldTransform
            world = _IDENT
        elif rtype in (0x402C, 0x402D, 0x402E, 0x402F):
            if rtype == 0x402C:                  # MultiplyWorldTransform
                T = struct.unpack_from('<6f', d, 0)
            elif rtype == 0x402D:                # Translate
                dx, dy = struct.unpack_from('<2f', d, 0)
                T = (1.0, 0.0, 0.0, 1.0, dx, dy)
            elif rtype == 0x402E:                # Scale
                sx, sy = struct.unpack_from('<2f', d, 0)
                T = (sx, 0.0, 0.0, sy, 0.0, 0.0)
            else:                                # Rotate
                ang = math.radians(struct.unpack_from('<f', d, 0)[0])
                c, s = math.cos(ang), math.sin(ang)
                T = (c, s, -s, c, 0.0, 0.0)
            world = _mmul(world, T) if (flags & 0x2000) else _mmul(T, world)
        elif rtype == 0x4030:                    # SetPageTransform（PageUnit 在 flags、PageScale 1 float）
            unit, sc = flags & 0xFF, (struct.unpack_from('<f', d, 0)[0] if len(d) >= 4 else 1.0)
            if unit in (0, 1, 2):                # World/Display/Pixel
                s = sc if unit else 1.0
                page = (s, 0.0, 0.0, s, 0.0, 0.0)
            else:
                per = {3: 72.0, 4: 1.0, 5: 25.4, 6: 300.0}.get(unit, 1.0)
                s = sc * dpiy / per
                page = (s, 0.0, 0.0, s, 0.0, 0.0)
        elif rtype == 0x4025:                    # Save
            stack[struct.unpack_from('<I', d, 0)[0] if len(d) >= 4 else 0] = (world, page)
        elif rtype == 0x4026:                    # Restore
            k = struct.unpack_from('<I', d, 0)[0] if len(d) >= 4 else 0
            if k in stack:
                world, page = stack[k]
        elif rtype in (0x4027, 0x4028):          # BeginContainer[NoParams]
            cont.append((world, page))
        elif rtype == 0x4029:                    # EndContainer
            if cont:
                world, page = cont.pop()
        elif rtype == 0x4008 and ((flags >> 8) & 0x7F) == 6:    # Object（ObjectType 6 = Font；型別是 1-based）
            oid, body = flags & 0xFF, d
            if flags & 0x8000:                   # continuation：大物件跨多筆，要串接
                pend.setdefault(oid, bytearray())
                pend[oid] += body[4:] if len(body) >= 4 else body
                body = bytes(pend[oid])
            else:
                pend.pop(oid, None)
            if len(body) >= 12:
                em, unit = struct.unpack_from('<fI', body, 4)
                fonts[oid] = (em * dpiy / 72.0 if unit == 3 else em)
        elif rtype == 0x401C and len(d) >= 28:   # DrawString
            ln = struct.unpack_from('<I', d, 8)[0]
            rx, ry, rw, rh = struct.unpack_from('<4f', d, 12)
            txt = d[28:28 + ln * 2].decode('utf-16-le', 'replace')
            if rw <= 0.01 or rh <= 0.01:         # 有些字串 LayoutRect 是 0 → 用字級估一個框，否則交集永遠 0
                em = fonts.get(flags & 0xFF, 12.0)
                rw = max(rw, len(txt) * em * 0.55)
                rh = max(rh, em * 1.25)
            M = _mmul(world, page)
            xs, ys = [], []
            for px, py in ((rx, ry), (rx + rw, ry), (rx, ry + rh), (rx + rw, ry + rh)):
                xs.append(px * M[0] + py * M[2] + M[4])
                ys.append(px * M[1] + py * M[3] + M[5])
            out.append(dict(text=txt, box=(min(xs), min(ys), max(xs), max(ys)),
                            org=(rx * M[0] + ry * M[2] + M[4], rx * M[1] + ry * M[3] + M[5])))
    return out


def overlap_pairs(strs, zone, min_frac=0.25):
    """zone 內（origin 落在裡面，左緣放寬 8px）兩兩字串「bbox 交集 > 0.25×較小框面積且 > 4px²」的配對數。
    **不可以改成「每格字串數」**：製程圖區單格也能有 10+ 筆字串，但它們互不重疊；一定要數重疊配對。
    不提早收手——全庫 112 張精確計數只要 2 秒，數滿才能把真正的配對數記進 index.json 供日後回頭調門檻。"""
    l, t, r, b = zone
    sel = [s['box'] for s in strs if l - 8 <= s['org'][0] < r and t <= s['org'][1] < b]
    n = 0
    for i in range(len(sel)):
        ax1, ay1, ax2, ay2 = sel[i]
        aa = (ax2 - ax1) * (ay2 - ay1)
        for j in range(i + 1, len(sel)):
            bx1, by1, bx2, by2 = sel[j]
            ow = min(ax2, bx2) - max(ax1, bx1)
            if ow <= 0:
                continue
            oh = min(ay2, by2) - max(ay1, by1)
            if oh <= 0:
                continue
            ov = ow * oh
            if ov > 4 and ov > min_frac * min(aa, (bx2 - bx1) * (by2 - by1)):
                n += 1
    return n, len(sel)


def nav_clamp(strs):
    """nav 矩形的底緣（畫面自己的按鈕要留著）。回傳 (nb, ignored)。

    只採 top >= MASK_NAV_FLOOR 的 MASK_VOCAB 命中——樓地板之上的命中一定不是畫面底部的按鈕
    （導覽樹本體就在那裡），拿它當夾限會把導覽樹整片留著、甚至讓矩形退化成 0 高度被整個丟掉。
    被忽略的命中照原文回報（ignored），由呼叫端記進 index.json 並在結尾印警告——不可以靜默。"""
    nl, nt, nr, nb = MASK_NAV
    inzone = [s for s in strs
              if s['box'][0] < nr and s['box'][2] > nl and s['box'][1] < nb and s['box'][3] > nt
              and s['text'].strip() in MASK_VOCAB]
    tops = [s['box'][1] for s in inzone if s['box'][1] >= MASK_NAV_FLOOR]
    ignored = sorted({(s['text'].strip(), round(s['box'][1], 1))
                      for s in inzone if s['box'][1] < MASK_NAV_FLOOR})
    if tops:
        nb = min(nb, int(math.floor(min(tops))) - MASK_NAV_GAP)
    return nb, ignored


def mask_rects(strs):
    """逐張算要遮哪些矩形（原生裝置座標）。回傳 (rects=[(name,l,t,r,b)], metrics)。
    nav 配對數沒過門檻就整張不遮（沒有 chrome 的樣板頁 3 張是 0 組，會自動排除，不必寫白名單）。"""
    nav_pairs, nav_n = overlap_pairs(strs, MASK_NAV)
    metrics = dict(nav_pairs=nav_pairs, nav_strings=nav_n)
    if nav_pairs < MASK_NAV_PAIRS:
        return [], metrics
    ban_pairs, ban_n = overlap_pairs(strs, MASK_BANNER)
    metrics.update(banner_pairs=ban_pairs, banner_strings=ban_n)
    # nav 底緣夾限：畫面自己的按鈕（MASK_VOCAB）若落在 nav 矩形內的樓地板以下，底緣縮到它上面 7px
    nl, nt, nr, _ = MASK_NAV
    nb, nav_ignored = nav_clamp(strs)
    metrics.update(nav_bottom=nb)
    if nav_ignored:
        metrics['nav_vocab_ignored'] = [list(t) for t in nav_ignored]
    rects = [('nav', nl, nt, nr, nb), ('loading',) + MASK_LOADING, ('menubar',) + MASK_MENUBAR]
    if ban_pairs >= MASK_BANNER_PAIRS:
        # banner 右緣夾限：橫幅裡第一個 left >= 430 的非 ### 字串（HRSG 類的 HP SEPARATOR left=433）往左 2px
        bl, bt, br, bb = MASK_BANNER
        cand = [s['box'][0] for s in strs
                if s['org'][1] < bb and s['box'][0] >= 430 and s['text'].strip() != '###']
        if cand:
            br = min(br, int(math.floor(min(cand))) - 2)
        rects.append(('banner', bl, bt, br, bb))
    return rects, metrics


def area_mode(im, box):
    """box 內的眾數色與其佔比。用 PIL 的 getcolors（C 實作）而不是自己疊 Counter：
    逐列取樣會呼叫上萬次，純 Python 疊 tuple 會慢上一個量級。"""
    l, t, r, b = box
    if r <= l or b <= t or r > im.width or b > im.height or l < 0 or t < 0:
        return None, 0.0
    cols = im.crop(box).getcolors((r - l) * (b - t))
    if not cols:
        return None, 0.0
    cnt, col = max(cols)
    return col, cnt / float((r - l) * (b - t))


def mask_fill_colors(im, name, t, b):
    """該矩形每一列要填的顏色：flat 帶回傳單一色、rows 帶回傳逐列色。回傳 (cols, why)。

    flat 帶（nav）取樣不可信（眾數佔比不足、或偏離預設超過 MASK_BG_TOL）→ 回傳 `(None, why)`
    叫呼叫端**整個矩形跳過不塗**。不可以改塗 MASK_BG 的預設色：取樣不可信就代表這張圖的版型跟推導時不一樣，
    這時把灰塊塗在可能錯的位置比留著疊影更糟。rows 帶單列不足仍退回預設（只影響 1px，見 MASK_BG_TOL 旁註）。"""
    default = MASK_BG[name]
    kind = MASK_FILL[name]
    if kind[0] == 'flat':
        col, frac = area_mode(im, kind[1:])
        if col is None or frac < MASK_BG_FRAC:
            return None, '取樣區眾數佔比 %.2f 不足 → 整個矩形不塗' % frac
        if max(abs(col[i] - default[i]) for i in range(3)) > MASK_BG_TOL:
            return None, '取樣色 %s 偏離預設 %s → 整個矩形不塗' % (col, default)
        return [col] * (b - t), ''
    x1, x2 = kind[1], kind[2]
    out, nfb = [], 0
    for y in range(t, b):
        col, frac = area_mode(im, (x1, y, x2, y + 1))
        if col is None or frac < MASK_BG_FRAC:
            col, nfb = default, nfb + 1
        out.append(col)
    return out, ('%d／%d 列取樣不足，該列退回預設' % (nfb, b - t)) if nfb else ''


def apply_mask(im, rects):
    """在原生 PNG 上把矩形用該區取樣到的背景色塗平（必須在 PIL 縮圖**之前**：先縮再遮，矩形要乘 scale 還有半像素誤差）。
    回傳 (masked, notes)：`masked` 是**具名** dict `{"nav":[l,t,r,b], …}`，只含真的塗掉的矩形
    （用具名而不是位置陣列，是因為矩形組合會變——banner 沒過門檻就不在裡面、取樣不可信的矩形會整個跳過——
    拿 masked[0]／masked[3] 當 nav／banner 讀，矩形一少就會把 loading 的底緣誤報成 nav 的夾限）。
    矩形邊界**不外擴**——四個矩形都已經逐張夾過相鄰內容
    （nav 右緣 213 距最近的位號標記只有 0.47px），再外擴就會切到東西。"""
    from PIL import ImageDraw
    dr = ImageDraw.Draw(im)
    done, notes = {}, []
    for name, l, t, r, b in rects:
        l, t = max(0, l), max(0, t)
        r, b = min(im.width, r), min(im.height, b)
        if r - l < 2 or b - t < 2:
            notes.append('%s：矩形退化成 %dx%d → 不塗' % (name, r - l, b - t))
            continue
        cols, why = mask_fill_colors(im, name, t, b)
        if why:
            notes.append('%s：%s' % (name, why))
        if cols is None:            # flat 取樣不可信 → 整個矩形不塗（寧可留原圖，不要塗錯地方）
            continue
        for i, y in enumerate(range(t, b)):
            dr.rectangle([l, y, r - 1, y], fill=cols[i])
        done[name] = [l, t, r, b]
    return done, notes


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
    ap.add_argument('--no-mask', action='store_true',
                    help='不遮設計時堆疊的 chrome（導覽樹／錶框／Loading 紅字／選單下拉）；回溯比對用，見模組說明')
    ap.add_argument('--runtime-map', default=RUNTIME_MAP,
                    help='執行時截圖對應表（hmi_runtime_map.py 的輸出；預設 tools/db/hmi_runtime_map.json）')
    ap.add_argument('--no-runtime', action='store_true',
                    help='不出執行時截圖，只出設計時縮圖；輸出與沒有這段程式時逐位元組相同（回溯比對用）')
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
                         raw=len(data), dups=[], emf_bytes=data))
        by_sha[h] = jobs[-1]

    print('有 ThumbNail %d、無 %d、讀取失敗 %d；去重後要渲染 %d'
          % (len(jobs) + sum(len(j['dups']) for j in jobs), len(skipped), len(errors), len(jobs)))
    for j in jobs:
        if j['dups']:
            print('  重複 sha1：%s == %s' % (j['key'], ', '.join(j['dups'])))
    # 1.5) 執行時截圖（使用者在機組上拍的）。**一定要在「沒有可渲染的畫面」那道早退之前**：
    # 201 張執行時畫面裡有 101 張本來就沒有 ThumbNail（其中 23 張是網站真的發布的），
    # 早退擺前面的話 `--only` 只挑這種畫面時會一個檔都不產、index.json 也不寫。
    rt, rt_notes = ({}, [])
    if not args.no_runtime:
        rt, rt_notes = runtime_shots(args.runtime_map, root, set(keys[p] for p in cims),
                                     args.out, args.width, args.format, args.quality, scr_w, scr_h)
    else:
        print('※ --no-runtime：只出設計時縮圖')
    if not jobs and not rt:
        sys.exit('沒有可產出的影像（這批畫面既沒有 ThumbNail，也沒有執行時截圖）')

    # 2) 一次 PowerShell 批次渲染（每次啟動 PowerShell 很慢，絕不逐檔啟動）
    res = {}
    if jobs:          # --only 只挑到「沒有 ThumbNail、只有執行時截圖」的畫面時整段跳過（不白啟動 PowerShell）
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
        with open(log, encoding='utf-8') as f:
            for line in f:
                c = line.rstrip('\n').split('\t')
                res[c[1]] = c

    # 3) 堆疊 chrome 遮罩 + PIL 縮圖 + 內容檢查 + index.json
    # 遮罩矩形是寫死的裝置座標，只有在畫布真的是 1920x1080 時才對得上；--screen 改過就不遮（不要縮放矩形硬套）
    can_mask = not args.no_mask and (scr_w, scr_h) == (SCREEN_W, SCREEN_H)
    if args.no_mask:
        print('※ --no-mask：不遮設計時堆疊的 chrome')
    elif not can_mask:
        print('※ --screen %dx%d 非 %dx%d → 不遮 chrome（矩形是寫死的裝置座標，不縮放硬套）'
              % (scr_w, scr_h, SCREEN_W, SCREEN_H))
    index, failed, mismatch = {}, [], []
    mask_log, bg_notes = {}, []
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
        # ---- 設計時堆疊的 chrome 遮罩：只對全畫面型評估，逐張數堆疊，數不到就不遮（見模組說明與 mask_rects）
        masked, metrics = {}, None
        if can_mask and j['full'] and j['canvas'] == [0, 0, SCREEN_W, SCREEN_H]:
            if im.mode != 'RGB':      # 取樣與填色都假設 RGB（GDI+ 存的是 24bpp，照理一定是）
                im = im.convert('RGB')
            rects, metrics = mask_rects(emfplus_strings(j['emf_bytes']))
            if rects:
                masked, notes = apply_mask(im, rects)
                if masked:            # 記真的塗掉的，不是打算塗的（取樣不可信的矩形會被跳過）
                    mask_log[j['key']] = list(masked)
                bg_notes += [(j['key'], nt) for nt in notes]
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
                     sha1=j['sha'], masked=masked, **{k: v for k, v in stats.items()})
        if metrics is not None:
            entry['mask_metrics'] = metrics        # 沒遮的畫面也留配對數，門檻要再調時不必重跑整套分析
        if j['full'] and j['hdr']['device'] != [scr_w, scr_h]:
            # szlDevice（錄製當時的視窗／裝置解析度）不等於螢幕矩形 → 這張不要拿 device 當座標基準
            entry['device_mismatch'] = True
        index[j['key']] = entry
        for d in j['dups']:
            index[d] = dict(entry, dup_of=j['key'])

    # 4) 執行時截圖（步驟 1.5 已經產好）併進 index：有對應表就蓋過設計時那張，設計時那筆整包搬進 'emf'
    rt_new = 0
    for key in sorted(rt):
        blk = rt[key]
        v = blk['variants'][blk['primary']]
        # 內容統計直接沿用 primary 那張的（runtime_shots 已經算過），不要再開檔重算：
        # 重算是對 webp 解碼後的像素算，會跟 variants 裡的數字差一點點，同一筆 index 出現兩組 nonbg 只會讓人懷疑哪個才對
        top = dict(file=v['file'], w=v['w'], h=v['h'], bytes=v['bytes'], source='runtime capture',
                   canvas=[0, 0, scr_w, scr_h], device=[scr_w, scr_h], scale=round(v['w'] / float(scr_w), 6),
                   masked={}, runtime=blk,
                   **{k: v[k] for k in ('nonbg', 'colors', 'luma', 'bg', 'flags')})
        old = index.get(key)
        if old is not None:
            top['emf'] = old       # 設計時那筆原封不動（含 bounds／masked／mask_metrics／sha1／dup_of），不丟
        else:
            rt_new += 1            # 這張畫面本來沒有 ThumbNail，現在第一次有影像
        index[key] = top

    with open(os.path.join(args.out, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1, sort_keys=True)

    if not args.keep_tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print('暫存保留：%s' % tmp)

    # 遮罩／EMF 相關的統計一律看「設計時那一筆」：被執行時截圖蓋過的畫面，那筆在 e['emf'] 裡
    # （不這樣做，換了執行時截圖的 43 張就會從遮罩統計裡悄悄消失）
    emf_ix = {k: (e.get('emf') or e) for k, e in index.items() if e.get('emf') or e.get('source') == 'ThumbNail EMF'}
    # 三種都要算進去，否則「實體檔 N 個／總位元組」會漏掉非 primary 的執行時變體（實測漏 84 個、低估 29%）：
    # 每筆要發布的那張 ∪ 設計時那張 ∪ 每個選單機組的執行時變體
    uniq = ({e['file'] for e in index.values()} | {e['file'] for e in emf_ix.values()}
            | {v['file'] for e in index.values() for v in ((e.get('runtime') or {}).get('variants') or {}).values()})
    gone = sorted(f for f in uniq if not os.path.exists(os.path.join(args.out, f)))
    total = sum(os.path.getsize(os.path.join(args.out, f)) for f in uniq if f not in gone)
    big = max(((os.path.getsize(os.path.join(args.out, f)), f) for f in uniq if f not in gone), default=(0, ''))
    print('\n完成：%d 個畫面有影像（實體檔 %d 個）' % (len(index), len(uniq)))
    print('  總位元組 %.1f MB、單檔最大 %d bytes（%s）、平均 %d bytes'
          % (total / 1048576.0, big[0], big[1], total // max(1, len(uniq))))
    if gone:      # index 指到卻不在磁碟上的檔案要出聲，不能靜默當成 0 bytes
        print('  ※ index 指到但檔案不在 %d 個：%s' % (len(gone), ', '.join(gone[:5]) + ('…' if len(gone) > 5 else '')))
    flagged = {k: e['flags'] for k, e in index.items() if e['flags']}
    print('  內容可疑（blank/flat/dark）%d：%s' % (len(flagged), json.dumps(flagged, ensure_ascii=False)))
    print('  裁切過（內容超出可視區）%d' % sum(1 for e in emf_ix.values() if e.get('cropped')))
    if rt:
        nvar = sum(len(e['runtime']['variants']) for e in index.values() if e.get('runtime'))
        rtb = sum(v['bytes'] for e in index.values() if e.get('runtime') for v in e['runtime']['variants'].values())
        print('  執行時截圖（%s 擷取）：%d 個畫面、%d 組（畫面, 選單機組），共 %.1f MB；'
              '其中 %d 個畫面本來沒有 ThumbNail、現在第一次有影像'
              % (rt[next(iter(rt))]['captured'], len(rt), nvar, rtb / 1048576.0, rt_new))
    for k, nt in rt_notes:
        print('    ※ %s：%s' % (k, nt))
    if can_mask:
        ev = [k for k, e in emf_ix.items() if 'mask_metrics' in e and 'dup_of' not in e]
        no = [k for k in ev if not emf_ix[k]['masked']]
        cmb = Counter(tuple(v) for v in mask_log.values())
        print('  堆疊 chrome 遮罩：評估 %d 張全畫面型，遮了 %d 張（矩形組合 %s）'
              % (len(ev), len(mask_log), '；'.join('%s x%d' % ('+'.join(k), n) for k, n in cmb.most_common())))
        print('    沒遮 %d（nav 配對數未過門檻，或矩形全被取樣不可信跳過）：%s'
              % (len(no), ', '.join(sorted(no)) or '無'))
        # 一律以**具名鍵**讀，不可用 masked[0]／masked[3]（矩形組合會變，見 apply_mask）
        clamped = [(k, e['masked']['nav'][3]) for k, e in emf_ix.items()
                   if e['masked'].get('nav') and e['masked']['nav'][3] != MASK_NAV[3]]
        print('    nav 底緣夾限（畫面自己的按鈕）%d：%s'
              % (len(clamped), ', '.join('%s→%d' % c for c in sorted(clamped)[:4]) + ('…' if len(clamped) > 4 else '')))
        bclam = [(k, e['masked']['banner'][2]) for k, e in emf_ix.items()
                 if e['masked'].get('banner') and e['masked']['banner'][2] != MASK_BANNER[2]]
        print('    banner 右緣夾限 %d：%s' % (len(bclam), ', '.join('%s→%d' % c for c in sorted(bclam)[:4])
                                              + ('…' if len(bclam) > 4 else '')))
        ign = sorted((k, e['mask_metrics']['nav_vocab_ignored']) for k, e in emf_ix.items()
                     if 'dup_of' not in e and (e.get('mask_metrics') or {}).get('nav_vocab_ignored'))
        print('    ※ nav 夾限樓地板（y<%d）忽略的畫面內容詞 %d：%s'
              % (MASK_NAV_FLOOR, len(ign),
                 '；'.join('%s %s' % (k, v) for k, v in ign[:4]) or '無'))
        if ign:
            print('       → 這些畫面的 nav 區帶上半部出現畫面內容詞，底緣沒有照它夾（照它夾會吃掉導覽樹）。'
                  '若是原廠換了版型，要回來重訂 MASK_NAV／MASK_NAV_FLOOR，不要直接放寬樓地板。')
        print('    填色取樣不可信（flat 跳過不塗／rows 該列退回預設）%d：%s'
              % (len(bg_notes), bg_notes[:3] or '無（全部採用逐張取樣色）'))
    dm = sorted(k for k, e in emf_ix.items() if e.get('device_mismatch'))
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
