# -*- coding: utf-8 -*-
r"""tools/db/pid_shots.py — 把 pid.json 引用到的 P&ID 圖紙渲染成整張影像（查詢卡「P&ID 圖面位置」用來標點的底圖）。

輸入：tools/db/pid_index.py 的 pid.json（只渲染 by_tag 真的引用到的圖紙）＋文件庫裡那份 PDF（唯讀）。
輸出：<out>/<slug>.webp（轉正後整張圖）＋ <out>/index.json。

== 影像規格（為什麼是這樣）==
* **一張圖紙一張影像，所有位號共用**，標記不燒進影像（前端用百分比疊框，與圖控 HMI 同一套做法）。
  量過三種做法：整張圖 8.1 MB、總覽＋4x3 分塊 10.4 MB、每支位號各裁一張 14.6 MB——整張圖最省也最簡單。
* **轉正**：page.get_pixmap(matrix=Matrix(z, z).prerotate(rot))，rot 就是 pid.json 的 sheets[].rot
  （＝在 /Rotate 之上再順時針多轉的角度；get_pixmap 自己會套 /Rotate）。pid.json 的 x／y／w／h 就是這張影像的比例。
* **四階灰階、不抖色、無損 WebP（method 6）**：圖紙是黑線白底，四階灰保住反鋸齒的筆畫邊緣，位號字 10 px 高就讀得出來；
  全部 106 張實測（2026-10-08，當時只有文字層定位到的圖紙）：四階灰無損在 3200 px 是 9.1 MB，有損 WebP q60 反而要 24 MB
  （線條圖的高頻邊緣是有損編碼的弱項），兩階（純黑白）在字高 13 px 以下筆畫會斷，十六階要 14 MB。
* **量化（2026-10-10 改；RENDER_VERSION 2）：先拉黑點、再偏暗、才取四階**（black_point／quant_lut）。舊版是等距四捨五入，
  兩種圖因此讀不出來，都是獨立查核者在發布的影像上讀出來的：
  - **整張圖用灰色畫的圖紙**（TCM01-D1701 p2：最暗的線也只有灰階 137）：髮絲線反鋸齒後更淡，四捨五入成白色，字斷成碎片，
    16 處標記有約 10 處沒辦法逐字讀。做法：量這張圖的黑點（墨跡像素由暗到亮累計到 2 % 的那一階），≥ 24 就把
    [黑點, 255] 線性拉到 [0, 255]。一般黑線白底的圖黑點是 0，不受影響；被引用的 117 張裡有 5 張會拉
    （D1701 p2，以及 TDM01-D1205 的四張——那份是灰階掃描品質的向量圖與點陣清單）。
  - **線條字（CAD 的單線字）**：筆畫只有零點幾個像素寬，反鋸齒後是 180~230 的淺灰，等距四階把 213 以上的全部變白
    （TDM01-D1205 p5 球泡裡的 PT，橫畫不見了讀成 PI）。做法：量化前先做 gamma 2（v' = 255·(v/255)²），等於把三條門檻從
    43／128／213 移到 104／180／233：淺灰留得住，筆畫看起來粗一點。A0 的密圖（TCM01-D1114 p5、AFF01-D0002 p2、
    D0027-4 p2）並排看過，字變粗但沒有糊掉。
  代價（2026-10-10 實測，同一批 117 張）：9.73 MB → 10.63 MB（+9.2 %）；其中大小沒變的 112 張 +7.6 %（純粹是量化變暗），
  另外 5 張是下一條放大的（合計 0.39 → 0.59 MB）。
* **長邊依字高決定**：long = clamp(2400, round(12 px × 圖紙長邊 pt ÷ label_pt), 3600)，讓位號那一行字大約 12 px 高；
  pid.json 沒有 label_pt（null）時用 3200。A0 的 GE 圖（3370 pt、字高 10 pt）會頂到 3600；A1 的廠商圖多半 2400~2600。
  固定 2400 px 的話有 45 張圖的字不到 9 px（讀不清楚），固定 1600 px 則每一張都讀不出來。
  label_pt 的意義依圖紙而定（pid_index 給的）：有文字層的圖紙是位號**字框**的高度；沒有文字層的圖紙（線條字、點陣圖）是
  **字形本身**的高度（OCR 偵測框 ÷ 1.3），所以後者的字會比前者大三成——線條字需要。TDM01-D1205 p4／p5（A4 大小的頁、
  字形只有 3.5 pt）由 2400 變 2903 px，TCM01-D1604 p2 由 2709 變 3521，TCM01-D1701 p2 由 2978 變 3600，BMM01-D3702 p2
  由 2400 變 2901。改完後在發布的影像上 100 % 讀過：D1701 p2、D1205 p4／p5 的位號逐字讀得出來。
  **放大救不了的兩件事**：(1) D1205 p7／p8 的儀器清單本身是 2.08 px/pt 的點陣圖（整頁只有 1,750 px 寬的資訊），5／6、8／9
  在原檔上就要放大才分得出來，影像再大也一樣（拉黑點之後字變黑了，比舊版好讀，但極限在原檔）。(2) D1205 p5 球泡裡的
  功能碼 PT：原圖把 T 的橫畫畫得貼在球泡的上緣，PDF 放大 12 倍也是黏在一起的；發布的影像上看得出 T 頂著外框、
  旁邊的 PI 則與外框有空隙，但要仔細看。
* **彩色**：四階灰會丟掉顏色。--colour-report 逐張量「有顏色的墨跡佔多少」。實測（2026-10-08，被引用的 109 張）：
  - 45 張（GE 的 GFD01／TFD01／EGK01 示意圖）彩色墨跡 > 2 %，最高 36 %：整張圖的管線與符號都畫成**藍色**、字是黑色。
    只有一種顏色，不是用顏色區分資訊；轉灰階後線條變成較淺的灰、字仍是黑的，讀圖沒有問題（看過彩色／灰階並排裁圖）。
  - 15 張（多為 AFF01）有非藍色墨跡 0.5~3 %：**紅色的版次雲形框**與紅色收文章。轉灰階後雲形框的扇貝形輪廓還在
    （看得出哪裡改過版，只是不再是紅的）；紅色收文章若蓋在附註文字上，灰階後會比彩色時難分辨一些。
  所以目前沒有一張圖是「只靠顏色」傳達資訊的，沒有設例外。真的需要時的做法：LEVELS_OVERRIDE 可逐張指定灰階數；
  若使用者希望版次雲形框保留紅色，建議另加「16 色調色盤無損 WebP」模式逐張指定（census 實測同尺寸約為四階灰的 1.6 倍），
  那會動到 index.json 的欄位（levels 之外要多一個 mode），目前沒有實作。

本工具實測（2026-10-08，文字層定位到的 109 張，舊量化）：共 8.55 MB（每張中位數 61 KiB、最大 356 KiB），長邊 2445~3600 px
（中位數 2623）；全部重做 3~5 秒（6 個行程），有快取 0.2 秒。六張不同來源的圖在 100 % 下看過，球泡裡的位號都讀得出來；
最吃緊的是 TCM01-D1114 p5（A0、位號字高約 7 px，已頂到 3600 px 上限）。
2026-10-10（含 OCR 定位的圖紙共 117 張，新量化）：10.63 MB（每張中位數 70 KiB、最大 345 KiB），長邊 2400~3600 px
（中位數 2623），全部重做 3.5 秒；--jobs 6 與 --jobs 3 各跑一次逐位元組相同。

== 快取與決定性 ==
* index.json 每筆記下 src（PDF 的 size／mtime，來自 pid.json）與參數（long、levels、rot、ver）；
  全部相同而且 webp 還在、大小也對 → 跳過。所以中斷後重跑只會補沒做完的；--max-minutes 可以分批跑。
* pid.json 記的 size／mtime 與磁碟上的 PDF 不符＝pid.json 過期（圖換版了）→ 那一張回報錯誤、回傳碼 1，請先重跑 pid_index.py。
  rot 不是 0／90／180／270、頁碼超出 PDF 的範圍、渲染丟例外也一樣：只算那一張失敗，其他照做（舊版頁碼不對會整批中止在
  traceback 上）。**失敗的那一張，上一次的影像與 index.json 裡它那一筆原樣留著**（舊版會把它當成不再被引用而刪掉）。
* 同樣的輸入產生逐位元組相同的 webp（PyMuPDF 渲染與 libwebp 無損編碼都是決定性的；版本要固定：
  實測 PyMuPDF 1.27.1、Pillow 12.2.0、libwebp 1.6.0）。index.json 鍵排序、無時間戳、無絕對路徑。
* 不再被引用的 <slug>.webp 會刪掉（只刪檔名符合 slug 規則的 .webp；其他檔不碰）。

用法：
  py tools/db/pid_shots.py                                   # 讀 paths.PID_JSON，寫 paths.PID_SHOTS
  py tools/db/pid_shots.py --pid X\pid.json --out X\pid_shots --jobs 6
  py tools/db/pid_shots.py --max-minutes 8                   # 做不完就先寫 index.json、回傳碼 2，再跑一次即可續
  py tools/db/pid_shots.py --force                           # 忽略快取全部重做
  py tools/db/pid_shots.py --colour-report                   # 另印每張圖的彩色墨跡比例（不影響輸出）

index.json：{"<slug>": {"file","w","h","bytes","bp","long","levels","rot","ver","src":{"size","mtime"}}}
  bp＝這張圖量到的黑點（0＝沒有拉伸；見上面「量化」）。raster＝1：整頁是嵌入的點陣圖（RASTER_FRAC），這種頁不拉黑點、不偏暗（等距四階）。
"""
import argparse
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pid_lib as L  # noqa: E402

RENDER_VERSION = 4                     # 渲染／量化／編碼方式一改就 +1（快取全部失效）；2＝2026-10-10 的黑點拉伸＋偏暗量化；3、4＝點陣頁不偏暗
RASTER_FRAC = 0.3                      # 嵌入點陣圖蓋住頁面這個比例以上＝點陣頁（掃描頁、TDM01-D1205 p7／p8 的儀器清單）：不拉黑點、不偏暗。
                                       # 實測：D1205 p7／p8 的清單是 95／92 條橫切的點陣圖，合計佔頁面一半上下；圖框上的 logo 只佔 2～3 %
                                       # 偏暗是為了留住向量圖的髮絲線；點陣頁的小字本來就粗，再偏暗會把 0／6／8／B 的字腔填滿
                                       # （2026-10-10 在真實站上看到 C10LAC60 讀起來像 C13LAC80），所以回到等距四階
LEVELS = 4                             # 灰階數
TARGET_LABEL_PX = 12.0                 # 希望位號那一行字在影像上大約幾 px 高
LONG_MIN, LONG_MAX, LONG_DEFAULT = 2400, 3600, 3200
LEVELS_OVERRIDE = {}                   # {slug: 灰階數}——個別圖紙需要更多階時才填（目前沒有；見檔頭「彩色」）
QUANT_GAMMA = 2.0                      # 量化前的 gamma（> 1 ＝偏暗：淺灰的髮絲線留得住；見檔頭「量化」）
BLACK_PCT = 0.02                       # 黑點＝墨跡像素（灰階 < INK_MAX）由暗到亮累計到這個比例的那一階
BLACK_MIN = 24                         # 黑點不到這個值＝圖本來就有黑色的墨，不拉伸
INK_MAX = 250


def long_side(sheet):
    """這張圖紙影像的長邊像素數（規則見檔頭）。"""
    lp = sheet.get('label_pt')
    if not lp:
        return LONG_DEFAULT
    long_pt = max(sheet['w_pt'], sheet['h_pt'])
    return int(min(max(round(TARGET_LABEL_PX * long_pt / lp), LONG_MIN), LONG_MAX))


def black_point(hist):
    """8 位元灰階直方圖（256 格）→ 黑點（0~255）：墨跡像素由暗到亮累計到 BLACK_PCT 的那一階；不到 BLACK_MIN 回 0（不拉伸）。
    整張圖用灰色畫的圖紙（TCM01-D1701 p2：最暗的線也只有 140 左右）黑點就很高；一般黑線白底的圖是 0。"""
    total = sum(hist[:INK_MAX])
    if total < 100:
        return 0
    need, acc = BLACK_PCT * total, 0
    for v in range(INK_MAX):
        acc += hist[v]
        if acc >= need:
            return v if v >= BLACK_MIN else 0
    return 0


def quant_lut(levels, bp=0, gamma=QUANT_GAMMA):
    """256 格的對照表：先把 [bp, 255] 線性拉到 [0, 255]（bp＝黑點），再做 gamma（偏暗），最後等距量化成 levels 階（不抖色）。"""
    step = 255.0 / (levels - 1)
    lut = []
    for v in range(256):
        s = min(max((v - bp) * 255.0 / (255.0 - bp), 0.0), 255.0) if bp else float(v)
        g = 255.0 * (s / 255.0) ** gamma
        lut.append(int(round(round(g / step) * step)))
    return lut


def quantise(im, levels, bp=0, gamma=QUANT_GAMMA):
    """8 位元灰階 → levels 階（黑點拉伸＋偏暗量化；規則與由來見檔頭「量化」）。"""
    return im.point(quant_lut(levels, bp, gamma))


def raster_page(page):
    """這一頁（幾乎）整頁是嵌入的點陣圖嗎：各嵌入影像的外框面積合計 ≥ RASTER_FRAC × 頁面面積（條狀切開的也算，面積相加）。判斷不了就當不是。"""
    try:
        r = page.cropbox                                  # 未旋轉的頁框：get_image_info 的 bbox 也是未旋轉座標（/Rotate 90 的頁不能拿 page.rect 來裁）
        pa = abs(r.width * r.height) or 1.0
        area = 0.0
        for info in page.get_image_info():
            x0, y0, x1, y1 = info['bbox']
            area += max(0.0, min(x1, r.x1) - max(x0, r.x0)) * max(0.0, min(y1, r.y1) - max(y0, r.y0))
        return min(area, pa) >= RASTER_FRAC * pa
    except Exception:                                     # noqa: BLE001
        return False


def render_job(job):
    """（多行程工作函式）渲染一張圖紙 → (slug, index 的一筆 或 None, 錯誤訊息)。任何失敗都回錯誤訊息，不丟例外
    （一張圖的頁碼或轉正角不對，不該讓整批渲染中止在 traceback 上）。"""
    root, out_dir, slug, sheet, want = job
    try:
        import fitz
        from PIL import Image
        if sheet.get('rot') not in (0, 90, 180, 270):
            return slug, None, 'pid.json 的 rot 不是 0／90／180／270（%r）：%s' % (sheet.get('rot'), slug)
        ap = os.path.join(root, sheet['rel'].replace('/', os.sep))
        try:
            st = os.stat(ap)
        except OSError:
            return slug, None, '找不到 PDF：%s' % sheet['file']
        if st.st_size != sheet['src']['size'] or int(st.st_mtime) != sheet['src']['mtime']:
            return slug, None, 'PDF 與 pid.json 記的不是同一版（size／mtime 不符）：%s' % sheet['file']
        doc = fitz.open(ap)
        try:
            if not (isinstance(sheet.get('page'), int) and 1 <= sheet['page'] <= doc.page_count):
                return slug, None, 'pid.json 的頁碼 %r 超出這份 PDF 的範圍（共 %d 頁）：%s' % (sheet.get('page'), doc.page_count, sheet['file'])
            page = doc[sheet['page'] - 1]
            pix = L.render_upright(page, sheet['rot'], long_px=want['long'], gray=True)
            im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
            raster = raster_page(page)
            bp = 0 if raster else black_point(im.histogram())
            im = quantise(im, want['levels'], bp, 1.0 if raster else QUANT_GAMMA)
        finally:
            doc.close()
        fn = slug + '.webp'
        tmp = os.path.join(out_dir, fn + '.%d.tmp' % os.getpid())
        im.save(tmp, 'WEBP', lossless=True, method=6)
        os.replace(tmp, os.path.join(out_dir, fn))
        ent = {'file': fn, 'w': im.width, 'h': im.height, 'bytes': os.path.getsize(os.path.join(out_dir, fn)), 'bp': bp, 'raster': 1 if raster else 0}
        ent.update(want)
        return slug, ent, None
    except Exception as e:                                # noqa: BLE001
        return slug, None, '渲染失敗（%s: %s）：%s' % (type(e).__name__, str(e)[:120], slug)


def colour_job(job):
    """（多行程工作函式）一張圖紙的彩色墨跡：1200 px 的 RGB 渲染裡，非白像素有多少是「有顏色的」（RGB 最大最小差 > 60），
    其中又有多少**不是藍色**（藍＝B 是最大的通道；GE 的示意圖把管線與符號整張畫成藍色、字是黑色，那不算靠顏色傳達資訊）。
    回 (slug, 彩色比例, 非藍彩色比例, 墨跡像素數)。"""
    root, slug, sheet = job
    import fitz
    import numpy as np
    doc = fitz.open(os.path.join(root, sheet['rel'].replace('/', os.sep)))
    try:
        pix = L.render_upright(doc[sheet['page'] - 1], sheet['rot'], long_px=1200)
        a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).astype(np.int16)
    finally:
        doc.close()
    ink = a.min(axis=2) < 200
    col = ink & ((a.max(axis=2) - a.min(axis=2)) > 60)
    blue = col & (a[:, :, 2] >= a[:, :, 0]) & (a[:, :, 2] >= a[:, :, 1]) & (a[:, :, 2] - a[:, :, 0] > 40)
    n_ink = int(ink.sum())
    if not n_ink:
        return slug, 0.0, 0.0, 0
    return slug, float(col.sum()) / n_ink, float((col & ~blue).sum()) / n_ink, n_ink


def run_pool(func, jobs, n_proc, deadline=None):
    """依序交出結果；n_proc > 1 用多行程。過了 deadline 就不再等剩下的（已完成的照樣回傳）。"""
    if n_proc > 1 and len(jobs) > 1:
        import multiprocessing as mp
        with mp.Pool(min(n_proc, len(jobs))) as pool:
            it = pool.imap_unordered(func, jobs)
            for _ in range(len(jobs)):
                if deadline and time.time() > deadline:               # 時間到：還在做的丟掉（留下的 .tmp 下次開頭會清掉）
                    pool.terminate()
                    return
                try:
                    yield it.next(timeout=max(1.0, deadline - time.time()) if deadline else None)
                except mp.TimeoutError:
                    pool.terminate()
                    return
    else:
        for j in jobs:
            if deadline and time.time() > deadline:
                return
            yield func(j)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='P&ID 圖紙影像（見檔頭 docstring）')
    ap.add_argument('--pid', default=paths.PID_JSON, help='pid_index.py 的輸出（預設 paths.PID_JSON）')
    ap.add_argument('--out', default=paths.PID_SHOTS, help='輸出目錄（預設 paths.PID_SHOTS）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（預設 paths.LIBRARY_ROOT；唯讀）')
    ap.add_argument('--jobs', type=int, default=min(6, os.cpu_count() or 1), help='同時渲染幾張')
    ap.add_argument('--max-minutes', type=float, default=0, help='最多跑幾分鐘（0＝不限）；做不完回傳碼 2，再跑一次即可續')
    ap.add_argument('--force', action='store_true', help='忽略快取全部重做')
    ap.add_argument('--colour-report', action='store_true', help='另印每張圖的彩色墨跡比例')
    a = ap.parse_args()
    t0 = time.time()
    if not os.path.exists(a.pid):
        sys.exit('找不到 pid.json：%s（先跑 tools/db/pid_index.py）' % a.pid)
    with open(a.pid, encoding='utf-8') as f:
        pid = json.load(f)
    sheets = pid.get('sheets') or {}
    used = sorted({e['sheet'] for v in (pid.get('by_tag') or {}).values() for e in v})
    miss = [s for s in used if s not in sheets]
    if miss:
        sys.exit('pid.json 的 by_tag 引用了 sheets 裡沒有的圖紙：%s' % miss[:5])
    for s in used:
        if not L.SLUG_RE.match(s):
            sys.exit('slug 不合規則：%r' % s)
    os.makedirs(a.out, exist_ok=True)
    ip = os.path.join(a.out, 'index.json')
    prev = {}
    if os.path.exists(ip):
        try:
            with open(ip, encoding='utf-8') as f:
                prev = json.load(f)
        except Exception:                                  # noqa: BLE001
            prev = {}
    old = {} if a.force else prev
    index, todo = {}, []
    errs = []
    kept_old = 0
    for s in used:
        sh = sheets[s]
        # 先驗這一筆本身合不合理（rot、頁碼、頁碼與 slug 一致）：不合理的不渲染也不信快取，上一次的影像留著
        if sh.get('rot') not in (0, 90, 180, 270) or not isinstance(sh.get('page'), int) or isinstance(sh.get('page'), bool) \
                or sh['page'] < 1 or not s.endswith('__p%d' % sh['page']):
            errs.append('pid.json 這張圖紙的 rot／page 不合理（rot=%r、page=%r）：%s' % (sh.get('rot'), sh.get('page'), s))
            e = prev.get(s)
            if isinstance(e, dict) and os.path.exists(os.path.join(a.out, s + '.webp')):
                index[s] = e
                kept_old += 1
            continue
        want = {'long': long_side(sh), 'levels': int(LEVELS_OVERRIDE.get(s, LEVELS)), 'rot': sh['rot'], 'ver': RENDER_VERSION,
                'src': {'size': sh['src']['size'], 'mtime': sh['src']['mtime']}}
        e = old.get(s)
        fp = os.path.join(a.out, s + '.webp')
        if e and all(e.get(k) == v for k, v in want.items()) and os.path.exists(fp) and os.path.getsize(fp) == e.get('bytes'):
            index[s] = e
        else:
            todo.append((a.library, a.out, s, sh, want))
    print('被引用的圖紙 %d 張：快取可用 %d、要渲染 %d（%d 個行程）' % (len(used), len(index) - kept_old, len(todo), a.jobs))
    deadline = (t0 + a.max_minutes * 60.0) if a.max_minutes else None
    n_done = 0
    for slug, ent, err in run_pool(render_job, todo, a.jobs, deadline):
        if err:
            errs.append(err)
            # 這一張做不出來：上一次的影像與它在 index.json 的那一筆原樣留著（舊版會在下面的清理把它當成「不再被引用」刪掉，
            # 於是一張頁碼寫錯的 pid.json 就能把原本好好的影像清掉）。回傳碼仍是 1，要先把原因排除再重跑。
            e = prev.get(slug)
            if isinstance(e, dict) and os.path.exists(os.path.join(a.out, slug + '.webp')):
                index[slug] = e
                kept_old += 1
            continue
        index[slug] = ent
        n_done += 1
        if n_done % 20 == 0:
            print('  .. %d／%d（%.0f 秒）' % (n_done, len(todo), time.time() - t0), flush=True)
    # 不再被引用的影像刪掉（只碰檔名符合 slug 規則的 .webp 與上次中斷留下的 .tmp）
    removed = 0
    for fn in sorted(os.listdir(a.out)):
        if fn.endswith('.tmp') or (fn.endswith('.webp') and L.SLUG_RE.match(fn[:-5]) and fn[:-5] not in index):
            os.remove(os.path.join(a.out, fn))
            removed += 1
    txt = json.dumps(dict(sorted(index.items())), ensure_ascii=False, sort_keys=True, indent=1)
    bad = L.ABS_PATH_RE.search(txt)
    if bad:
        sys.exit('index.json 含本機絕對路徑：%r' % txt[max(0, bad.start() - 60):bad.start() + 60])
    with open(ip + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt)
    os.replace(ip + '.tmp', ip)
    by = sorted(e['bytes'] for e in index.values())
    longs = sorted(e['long'] for e in index.values())
    if by:
        print('index.json：%d 張、共 %.2f MB（%d bytes；每張中位數 %.0f KiB、最大 %.0f KiB）；長邊 %d~%d px（中位數 %d）；'
              '黑點拉伸 %d 張；本次渲染 %d、刪除 %d' % (
                  len(index), sum(by) / 1048576.0, sum(by), by[len(by) // 2] / 1024.0, by[-1] / 1024.0, longs[0], longs[-1],
                  longs[len(longs) // 2], sum(1 for e in index.values() if e.get('bp')), n_done, removed))
    for e in sorted(set(errs)):
        print('  錯誤：' + e)
    if kept_old:
        print('  有 %d 張做不出來，上一次的影像原樣留著（index.json 裡仍是舊的那一筆）' % kept_old)
    if a.colour_report:
        rows = sorted(run_pool(colour_job, [(a.library, s, sheets[s]) for s in used], a.jobs), key=lambda r: (-r[2], -r[1], r[0]))
        print('彩色墨跡（非白像素裡 RGB 最大最小差 > 60 的比例）：> 2 %% 的有 %d 張；其中**非藍色** > 0.5 %% 的有 %d 張' % (
            sum(1 for r in rows if r[1] > 0.02), sum(1 for r in rows if r[2] > 0.005)))
        for slug, frac, nonblue, n_ink in rows[:12]:
            print('  彩色 %6.2f %%  非藍 %6.2f %%  墨跡 %7d px  %s' % (100.0 * frac, 100.0 * nonblue, n_ink, slug))
    print('耗時 %.1f 秒' % (time.time() - t0))
    if errs:
        sys.exit(1)
    if len(index) < len(used):
        print('還有 %d 張沒做完（時間到）；再跑一次即可續' % (len(used) - len(index)))
        sys.exit(2)


if __name__ == '__main__':
    main()
