# -*- coding: utf-8 -*-
r"""tools/db/hmi_runtime_map.py — 把使用者拍的「執行時」圖控畫面（Screens\圖控\*.xlsx 內嵌 PNG）對應到 .cim 畫面與選單機組。

**為什麼要這個對應表**：查詢卡原本只能用 .cim 內含的 ThumbNail（設計時快照：值是 ###、文字是 CAPTION 佔位、
所有選單分支疊在一起，見 hmi_shots.py 的模組說明），156 個畫面檔才 109 張能用。使用者 2026-10-04 在機組上
逐頁擷取了執行時畫面，貼進 7 個 xlsx（每個對應導覽選單的一組分頁），共 290 張 **1920x1080**＝正好是
hmi_index 的標記所用的裝置座標系，所以可以原位換掉縮圖、不動任何座標換算。

**怎麼認出一張截圖是哪個畫面**：靠兩個互相獨立的訊號，缺一不可。
  1. **擷取順序**＝選單順序。每個活頁簿只收一組分頁（見 BOOK_MENUS），而且是照 `navigation/CIMNavigationMenuItemsStd.csv`
     由上而下拍的。單靠順序不行：有人重貼過同一張（實測 3 處），一張多出來就把後面全部推移一格。
  2. **畫面左上的麵包屑**（選單列下方那條淺藍帶）寫著 `分頁 :: 子選單 :: 項目`，OCR 出來跟 CSV 的封閉詞彙比對。
     單靠 OCR 也不行：同一個分頁裡「Hp & Lp Economiser」「Chiller Unit」各出現兩次（機組不同、文字一樣），
     而且 OCR 會把 HRSG11 讀成 HRSG1，分不出 HRSG11／HRSG12——那是活頁簿決定的，不是文字決定的。
  兩者合起來：以 OCR 相似度當分數、以 Needleman-Wunsch 求**單調**對齊（允許跳過圖與跳過選單列），
  就能一邊容忍重貼、一邊讓每張圖落在唯一的選單列上；選單列決定 `Cim Screen FileName` 與 `Unit`。
  **位元組完全相同的兩張截圖**（Excel 會把相同的圖片共用同一個 media）一定是重貼：留分數高的那張，另一張丟掉，
  它本來要對上的那列選單其實沒拍到。

**輸出是要 commit 的產物**：`tools/db/hmi_runtime_map.json`。hmi_shots.py 只讀這張表（不需要 OCR），
所以重建流程不依賴 rapidocr；要重跑這支才需要 `py -m pip install rapidocr-onnxruntime`。
表裡每張圖都記 PNG 的 sha1，xlsx 換過（重拍、順序不同）時 hmi_shots 會對不上而出聲，不會默默貼錯圖。

用法：
  py tools/db/hmi_runtime_map.py                      # 讀 Screens\圖控\*.xlsx，寫 tools/db/hmi_runtime_map.json
  py tools/db/hmi_runtime_map.py --out x.json --dump  # 另存他處，並逐張印出對齊結果
"""
import argparse
import collections
import csv
import difflib
import hashlib
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

# 每個活頁簿收的分頁（CSV 的 Menu Item Name），照拍攝順序。2026-10-04 語料的張數對照：
#   G11 64 anchors ≒ Plant 6 ＋ G11 41 ＋ G11S 16 ＝ 63（多的 1 張是重貼）
#   G12 57 ＝ G12 41 ＋ G12S 16（其中 2 張重貼）／H11 20 ＝ HRSG11 20／H12 20 ＝ HRSG12 20
#   S1 43 ＝ S1 26 ＋ S1S 17／BOP 51 ＝ BOP 51／BOPE 35 ＝ BOPE 25 ＋ Performance 9 ＋ Annunciator 1
# 對齊是單調 DP，不是逐張硬配，所以這裡只要「分頁集合與順序」對，張數差幾張不影響。
BOOK_MENUS = {
    'G11': ['Plant', 'G11', 'G11S'],
    'G12': ['G12', 'G12S'],
    'H11': ['HRSG11'],
    'H12': ['HRSG12'],
    'S1': ['S1', 'S1S'],
    'BOP': ['BOP'],
    'BOPE': ['BOPE', 'Performance', 'Annunciator', 'Alarms'],
}
CRUMB_BOX = (0, 186, 760, 214)     # 麵包屑那條淺藍帶（1920x1080 裝置座標）；OCR 前放大 2 倍
GAP_IMG, GAP_ROW = -0.55, -0.15    # DP：跳過一張圖 / 跳過一列選單的代價（跳圖貴，因為每張圖都該有歸屬）
LOW_SCORE = 0.80                   # 低於此分數就列進 review（OCR 讀壞或對齊可疑，要人眼確認）
ARGMAX_GAP = 0.05                  # 被指派的那列比「OCR 最像的那列」差這麼多就列進 review（見下面的第二道檢查）


def norm(s):
    s = (s or '').lower().replace('::', ':')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9:]+', ' ', s)).strip()


def crumb_of(row):
    parts = [row['Menu Item Name']] + ([row['Sub Menu Item Name']] if row['Sub Menu Item Name'] else []) + [row['Item Name']]
    return ' :: '.join(p.strip() for p in parts)


def anchors_of(zf, book):
    """xlsx 的繪圖錨點 → [(anchor 序號, 'xl/media/xxx.png')]，照 drawing*.xml 的文件順序（＝貼上順序）。

    直接抓 `r:embed`，**不要**去比對 `<xdr:cNvPr …/>` 的形狀：使用者填了替代文字（多一個 `descr=`）或加了超連結
    （`cNvPr` 不再自閉合）時，那種寫法會整張跳過，而且 `.*?` 會接到下一張的 `r:embed`，後面的序號整串挪位——
    序號挪一格就等於整本的畫面對應整串錯開，而且不會有任何徵兆。
    也要走訪**全部** drawing（截圖貼在第二張工作表時是 drawing2.xml），並以 `<xdr:pic>` 的個數當斷言。"""
    out = []
    for name in sorted(n for n in zf.namelist() if re.fullmatch(r'xl/drawings/drawing\d+\.xml', n)):
        rel = 'xl/drawings/_rels/%s.rels' % os.path.basename(name)
        rmap = (dict(re.findall(r'Id="(rId\d+)"[^>]*Target="\.\./media/([^"]+)"', zf.read(rel).decode('utf-8')))
                if rel in zf.namelist() else {})
        dr = zf.read(name).decode('utf-8')
        emb = re.findall(r'r:embed="(rId\d+)"', dr)
        npic = len(re.findall(r'<xdr:pic[ >]', dr))
        if len(emb) != npic:
            sys.exit('%s 的 %s：<xdr:pic> %d 個但 r:embed %d 個，對不起來；'
                     'anchor 序號就是貼上順序這個前提會破掉，不能照舊往下跑' % (book, name, npic, len(emb)))
        for rid in emb:
            tgt = rmap.get(rid)
            if not tgt:
                sys.exit('%s 的 %s：%s 不在 rels 裡（或不是 media）' % (book, name, rid))
            out.append('xl/media/' + tgt)
    return list(enumerate(out, 1))


def ocr_crumbs(books):
    """每張截圖的麵包屑 OCR。只有這支工具需要 rapidocr；hmi_shots 讀的是本工具的輸出。"""
    try:
        import numpy as np
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        sys.exit('缺 OCR 相依（%s）：py -m pip install rapidocr-onnxruntime pillow numpy' % e)
    eng = RapidOCR()
    out, n, tot = {}, 0, sum(len(v['anchors']) for v in books.values())
    for bk, b in books.items():
        zf = b['zip']
        for i, media in b['anchors']:
            raw = zf.read(media)
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            b['size'][(i, media)] = im.size
            b['sha'][(i, media)] = hashlib.sha1(raw).hexdigest()
            crop = im.crop(CRUMB_BOX)
            crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            r, _ = eng(np.array(crop))
            out[(bk, i)] = ' '.join(t[1] for t in (r or [])).strip()
            n += 1
            if n % 25 == 0:
                print('  OCR %d/%d' % (n, tot), flush=True)
    return out


def align(imgs, rows, score):
    """單調對齊（Needleman-Wunsch）：回傳 [(img 索引, row 索引 或 None)]，img 一律照順序出現。"""
    N, M = len(imgs), len(rows)
    dp = [[0.0] * (M + 1) for _ in range(N + 1)]
    bt = [[None] * (M + 1) for _ in range(N + 1)]
    for i in range(1, N + 1):
        dp[i][0], bt[i][0] = dp[i - 1][0] + GAP_IMG, 'i'
    for j in range(1, M + 1):
        dp[0][j], bt[0][j] = dp[0][j - 1] + GAP_ROW, 'j'
    for i in range(1, N + 1):
        for j in range(1, M + 1):
            best = (dp[i - 1][j - 1] + score[i - 1][j - 1], 'm')
            if dp[i - 1][j] + GAP_IMG > best[0]:
                best = (dp[i - 1][j] + GAP_IMG, 'i')
            if dp[i][j - 1] + GAP_ROW > best[0]:
                best = (dp[i][j - 1] + GAP_ROW, 'j')
            dp[i][j], bt[i][j] = best
    i, j, out = N, M, []
    while i > 0 or j > 0:
        op = bt[i][j]
        if op == 'm':
            out.append((i - 1, j - 1)); i -= 1; j -= 1
        elif op == 'i':
            out.append((i - 1, None)); i -= 1
        else:
            j -= 1
    out.reverse()
    return out


def cim_keys(root):
    """Screens 根目錄的 .cim 檔名 → 磁碟上的真實大小寫（CSV 寫 HRSG_Reheater_UX.CIM，檔案是 .cim）。"""
    out = {}
    for n in os.listdir(root):
        if n.lower().endswith('.cim') and os.path.isfile(os.path.join(root, n)):
            out[n.lower()] = n
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--screens', default=paths.HMI_SCREENS, help='圖控畫面檔目錄（預設 AMS_HMI_SCREENS）')
    ap.add_argument('--shots-subdir', default='圖控', help='執行時截圖活頁簿所在的子目錄（預設「圖控」）')
    ap.add_argument('--nav', default=None, help='選單 CSV（預設 <screens>/navigation/CIMNavigationMenuItemsStd.csv）')
    ap.add_argument('--captured', default=None, help='擷取日期 YYYY-MM-DD（預設取活頁簿最新的修改日）')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hmi_runtime_map.json'))
    ap.add_argument('--dump', action='store_true', help='逐張印出對齊結果')
    a = ap.parse_args()

    root = os.path.abspath(a.screens)
    sdir = os.path.join(root, a.shots_subdir)
    if not os.path.isdir(sdir):
        sys.exit('找不到截圖目錄：%s' % sdir)
    navp = a.nav or os.path.join(root, 'navigation', 'CIMNavigationMenuItemsStd.csv')
    if not os.path.exists(navp):
        sys.exit('找不到選單 CSV：%s' % navp)
    with open(navp, encoding='utf-8-sig') as f:
        nav = list(csv.DictReader(f))
    real = cim_keys(root)

    books, mtime = {}, 0
    for n in sorted(os.listdir(sdir)):
        if not n.lower().endswith('.xlsx') or n.startswith('~$'):
            continue
        stem = os.path.splitext(n)[0]
        if stem not in BOOK_MENUS:
            print('  ※ 略過 %s：BOOK_MENUS 沒有這個活頁簿（要新增分頁對照才收）' % n)
            continue
        p = os.path.join(sdir, n)
        mtime = max(mtime, os.path.getmtime(p))
        zf = zipfile.ZipFile(p)
        books[stem] = {'file': n, 'zip': zf, 'anchors': anchors_of(zf, n), 'size': {}, 'sha': {},
                       'bytes': os.path.getsize(p),
                       'sha1': hashlib.sha1(open(p, 'rb').read()).hexdigest()}
        print('%-6s %3d 張（%s）' % (stem, len(books[stem]['anchors']), n))
    if not books:
        sys.exit('%s 裡沒有可用的活頁簿' % sdir)

    print('OCR 麵包屑…', flush=True)
    crumbs = ocr_crumbs(books)

    shots, review = [], []
    for stem in sorted(books):
        b = books[stem]
        rows = [r for g in BOOK_MENUS[stem] for r in nav if r['Menu Item Name'] == g]
        imgs = b['anchors']
        sc = [[difflib.SequenceMatcher(None, norm(crumbs[(stem, i)]), norm(crumb_of(r))).ratio() for r in rows]
              for i, _ in imgs]
        for ii, jj in align(imgs, rows, sc):
            i, media = imgs[ii]
            rec = {'book': b['file'], 'anchor': i, 'media': media, 'sha1': b['sha'][(i, media)],
                   'w': b['size'][(i, media)][0], 'h': b['size'][(i, media)][1],
                   'ocr': crumbs[(stem, i)]}
            if jj is None:
                rec.update({'screen': None, 'unit': None, 'crumb': None, 'score': 0.0, 'why': '沒有對上任何選單列'})
            else:
                r = rows[jj]
                fn = r['Cim Screen FileName']
                rec.update({'screen': real.get(fn.lower(), fn), 'unit': r['Unit'],
                            'crumb': crumb_of(r), 'score': round(sc[ii][jj], 3)})
                if fn.lower() not in real:
                    rec['why'] = '選單指到的 .cim 不在 %s 根目錄' % root
                # **與分數門檻無關的第二道檢查**：被指派的那一列若不是這張圖 OCR 最像的那一列、而且差距明顯，
                # 就列進 review。單看分數擋不住「同一頁拍了兩張（不是重貼）」——多出來的那張會被 DP 綁到鄰列，
                # 同子選單的麵包屑彼此極像，分數常常還在 0.80 以上。實測這道檢查在今天的語料只命中 2 張（都是對的）。
                bj = max(range(len(rows)), key=lambda x: sc[ii][x])
                if bj != jj and sc[ii][bj] - sc[ii][jj] > ARGMAX_GAP:
                    rec['why'] = ('OCR 最像的是「%s」（%.3f），卻被順序綁到「%s」（%.3f）→ 可能是同一頁拍了兩張'
                                  % (crumb_of(rows[bj]), sc[ii][bj], crumb_of(r), sc[ii][jj]))
                    rec['argmax'] = crumb_of(rows[bj])
            shots.append(rec)

    # 位元組相同的兩張 ＝ 重貼：留分數高的，另一張（連同它本來要對上的那列選單）丟掉。
    # **以 (活頁簿, sha1) 分組**：Excel 共用 media 只發生在同一本之內，跨本位元組相同是另一回事
    # （CSV 有 77 個 .cim 同時掛在兩本的分頁下、只差機組；真的撞在一起時丟掉的是另一部機的那張照片）。
    bysha = collections.defaultdict(list)
    for s in shots:
        bysha[(s['book'], s['sha1'])].append(s)
    dropped = []
    for _, group in bysha.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda s: -s['score'])
        for s in group[1:]:
            # crumb 可能是 None：圖比選單列多的活頁簿（G11 64 張 vs 63 列）會有一張對不上任何列，
            # 而那一張正好就是重貼的那張——這時沒有「本來要對上的那列」可講
            s['why'] = ('與 %s#%d 位元組相同（重貼）' % (group[0]['book'], group[0]['anchor'])
                        + ('；本來要對上的「%s」其實沒拍到' % s['crumb'] if s['crumb'] else '；沒有對上任何選單列'))
            dropped.append(s)
    # 跨活頁簿位元組相同：只警告、不丟（丟掉的會是「另一部機那張照片」，而它是獨立資訊）
    allsha = collections.defaultdict(list)
    for s in shots:
        allsha[s['sha1']].append(s)
    cross = [sorted('%s#%d' % (s['book'], s['anchor']) for s in g)
             for g in allsha.values() if len({s['book'] for s in g}) > 1]

    unmatched = [s for s in shots if not s['screen'] and s not in dropped]
    keep = [s for s in shots if s['screen'] and s not in dropped]
    screens = {}
    clash = []
    for s in sorted(keep, key=lambda s: (s['book'], s['anchor'])):
        d = screens.setdefault(s['screen'], {})
        if s['unit'] in d:
            # 同一個 .cim＋同一個 Unit 出現兩列選單（GT_Perf 的 Gas Turbine 1／2、HRSG_Perf 的 HRSG 1／2：
            # 只差 ScreenVariables 的 num;1_／num;2_）。**那是兩個不同的頁面，不是重複**，但 variants 以機組當鍵
            # 分不開，只能留第一張——所以第二張一定要寫進 dropped 讓人看得到「這一頁拍到了卻沒被採用」。
            clash.append((s['screen'], s['unit'], d[s['unit']]['anchor'], s['anchor']))
            s['why'] = ('同畫面同選單機組（%s）已經有 %s#%d；兩列選單只差 ScreenVariables，variants 以機組當鍵分不開 → 這張沒被採用'
                        % (s['unit'], d[s['unit']]['book'], d[s['unit']]['anchor']))
            dropped.append(s)
            continue
        d[s['unit']] = {k: s[k] for k in ('book', 'anchor', 'media', 'sha1', 'w', 'h', 'crumb', 'ocr', 'score')}
    keep = [s for s in keep if s not in dropped]
    for s in keep:
        if s['score'] < LOW_SCORE or s.get('argmax'):
            review.append(s)

    import datetime
    cap = a.captured or datetime.date.fromtimestamp(mtime).isoformat()
    out = {'kind': 'hmi_runtime_map', 'generated_by': 'tools/db/hmi_runtime_map.py',
           'captured': cap, 'subdir': a.shots_subdir,
           'books': {b['file']: {'sha1': b['sha1'], 'bytes': b['bytes'], 'menus': BOOK_MENUS[stem],
                                 'anchors': len(b['anchors'])}
                     for stem, b in sorted(books.items())},
           'screens': {k: screens[k] for k in sorted(screens)},
           'dropped': sorted(({k: s[k] for k in ('book', 'anchor', 'media', 'sha1', 'crumb', 'ocr', 'score', 'why')}
                              for s in dropped), key=lambda s: (s['book'], s['anchor'])),
           'review': sorted(({k: s.get(k) for k in ('book', 'anchor', 'screen', 'unit', 'crumb', 'ocr', 'score', 'why')}
                             for s in review), key=lambda s: s['score']),
           # 沒對上任何選單列的截圖：一定要列出來。少一張就代表 BOOK_MENUS 的分頁清單與活頁簿不符，
           # 而那會讓整本後面的對應整串挪位——以前這些只寫進 rec['why'] 然後沒人讀，統計看起來完全乾淨
           'unmatched': sorted(({k: s.get(k) for k in ('book', 'anchor', 'media', 'sha1', 'ocr', 'why')}
                                for s in unmatched), key=lambda s: (s['book'], s['anchor'])),
           'cross_book_identical': cross,
           'stats': {'books': len(books), 'shots': len(shots), 'mapped': len(keep), 'dropped': len(dropped),
                     'unmatched': len(unmatched),
                     'screens': len(screens), 'pairs': sum(len(v) for v in screens.values()),
                     'low_score': len(review), 'clash': clash}}
    assert len(shots) == len(keep) + len(dropped) + len(unmatched), '每張截圖都要有歸屬（採用／丟棄／沒對上）'
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)

    if a.dump:
        for s in shots:
            print('%-10s #%-3d %.2f %-46s %-40s %s'
                  % (s['book'], s['anchor'], s['score'], (s['crumb'] or '-')[:46], (s['screen'] or '-')[:40], s['unit']))
    print('\n完成：%d 張截圖 ＝ 採用 %d ＋ 丟棄 %d ＋ 沒對上 %d → %d 個畫面、%d 組（畫面, 選單機組）；待人工確認 %d 張'
          % (len(shots), len(keep), len(dropped), len(unmatched), len(screens), out['stats']['pairs'], len(review)))
    for s in out['dropped']:
        print('  丟棄 %s#%d：%s' % (s['book'], s['anchor'], s['why']))
    for s in out['unmatched']:
        print('  ※ 沒對上 %s#%d（OCR %r）→ BOOK_MENUS 的分頁清單可能與這本活頁簿不符，整本後面的對應會挪位'
              % (s['book'], s['anchor'], (s['ocr'] or '')[:40]))
    for s in out['review']:
        print('  待確認 %s#%d %.2f：OCR %r vs 選單 %r%s'
              % (s['book'], s['anchor'], s['score'], (s['ocr'] or '')[:40], s['crumb'],
                 '　←　' + s['why'] if s.get('why') else ''))
    if clash:
        print('  ※ 同畫面同選單機組有兩列選單（只差 ScreenVariables，留第一張、第二張已進 dropped）：%s' % clash)
    if cross:
        print('  ※ 跨活頁簿位元組相同（沒丟，但值得看一眼是不是擷取失敗）：%s' % cross)
    print('寫出 %s' % a.out)


if __name__ == '__main__':
    main()
