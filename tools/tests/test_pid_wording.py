# -*- coding: utf-8 -*-
"""P&ID 圖面位置的建置端文案與關卡（tools/db/build_card_aux.py 的 pid_*）：**不開瀏覽器、不碰資料目錄**，以合成的命中直接呼叫
pid_rows／pid_shared_boxes／pid_check／pid_doc／pid_collect。端對端測試只看得到現行資料剛好有的情形；這裡把每一種情形都釘住：

  * rel 五種（exact／typical／neutral／loop／train）與拆寫的 form、圖框分區、頁數不明、多張圖紙的順序
  * note 代碼 0～4（單獨、與符號標籤同張、不同代碼混在同一張、認不得的代碼）在「所在位置」「圖上標示」與 extra.note／notes 的說法
  * 「與本台位號相同」只在正規化後真的相同時才出現；ocr-fix 要寫出 OCR 原本讀到的字（raw），不寫「相同」
  * OCR：extra.conf／conf_min／confs（最低的不在 ① 也要帶得出來）；清單頁與沒有文字層的頁不說「線條字」
  * 同一個框被兩支不相干的位號認領 → pid_shared_boxes 抓得到、pid_check 以非 0 結束；機組雙胞胎／_01／同型各台／合寫標籤不誤擋
  * searched.pid 那句話的頁數說法（數字全取自 stats，缺鍵不炸）
  * pid_collect 不寫檔、pid_write_images 才清空重寫（失敗時 card/pid/ 原封不動）

  py tools/tests/test_pid_wording.py          # 單獨跑；exit 0＝全過
  py tools/tests/run_e2e.py --only pid_wording   # 由端對端入口跑（run_e2e 會自動收 test_*.py；ctx 用不到）
"""
import json
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'db'))
sys.dont_write_bytecode = True

FIX = '相近字元（0／O、8／B…）'
N1 = '這一處是圖上註記或表格（儀器清單）裡的文字，不是儀器符號旁的標籤'
N2 = '這一處是跨圖訊號旗標（接往另一張圖的訊號引用），不是儀器本身的位置'
N3 = '這一處是儀用／廠用空氣分配圖上的用氣點（這顆閥的供氣接點），不是閥在製程管線上的位置'
N4 = '這一處在圖紙上的迴路詳圖（TYPICAL 小圖）裡，不是主流程圖上的位置'
NOSYM = '這次比對（PDF 文字層＋OCR）沒有讀到這支位號的儀器符號，不代表圖上沒有畫，請開 PDF 確認'
ELSEWHERE = '儀器符號畫在這台設備的另一張圖紙上'
SAME = '與本台位號相同'


class Checks:
    """與 e2e_common.Checks 相同的輸出格式；另外寫一份是為了不 import playwright（這個測試沒有瀏覽器）。"""
    def __init__(self):
        self.fails = []

    def __call__(self, name, cond, info=''):
        print(('  ok   ' if cond else '  FAIL ') + name + ((' ' + str(info)) if (info != '' and not cond) else ''), flush=True)
        if not cond:
            self.fails.append(name + ((' ' + str(info)) if info != '' else ''))


def run(ctx=None):
    import build_card_aux as B
    ck = Checks()

    def sheet(rel, page, pages=3, **kw):
        base = rel.rpartition('/')[2]
        m = B.DOCNO_VAL_RE.search(base.upper())
        d = {'rel': rel, 'file': base, 'doc': m.group(1) if m else None, 'rev': (m.group(2) if m else None), 'title': 'T', 'page': page, 'pages': pages,
             'rot': 0, 'ocr': False, 'words': 900, 'src': {'size': 1, 'mtime': 2}}
        d.update(kw)
        return d

    def hit(s, x, y, label, rel, drawn_as='', how='text', form='word', note=0, **kw):
        return dict({'sheet': s, 'x': x, 'y': y, 'w': 0.02, 'h': 0.004, 'label': label, 'rel': rel, 'drawn_as': drawn_as, 'how': how, 'form': form, 'note': note}, **kw)

    def ocr(s, x, y, label, rel, drawn_as, conf, note=0, form='ocr', **kw):
        return hit(s, x, y, label, rel, drawn_as, how='ocr', form=form, note=note, conf=conf, **kw)

    R = {'a': 'sysA/HT0-1-TCM01-D1114-3 Condensate pumps.pdf', 'b': 'sysB/HT0-1-BFD01-D0002-4 - HRSG HP.pdf', 'c': 'sysC/vendor P&ID no number.pdf',
         'd1': 'sysD/a/HT0-1-AFF01-D0011-2 copy one.pdf', 'd2': 'sysD/b/HT0-1-AFF01-D0011-2 copy two.pdf', 'e': 'sysE/HT0-1-GFD01-D0013 no rev.pdf', 'root': 'HT0-1-AFF01-D0099-1 at root.pdf',
         'flag': 'sysF/HT0-1-AFF01-D0036-5 - P&ID - Blowdown.pdf', 'air': 'sysF/HT0-1-AFF01-D0021-5 - P&ID - Instrument Air.pdf',
         'pump': 'sysG/HT0-1-TDM01-D1205-0 - BFP P&ID.pdf', 'list': 'sysG/HT0-1-TDM01-D1205-0 - BFP P&ID list.pdf'}
    S = {k: B.pid_slug(v, 2) for k, v in R.items()}
    sheets = {S[k]: sheet(R[k], 2) for k in R}
    sheets[S['e']]['pages'] = None
    sheets[S['pump']]['words'] = 0      # 整頁沒有文字層（掃描影像）
    sheets[S['list']]['words'] = 0
    by_tag = {
        'C10LCC20BT012': [hit(S['a'], 0.1, 0.1, 'C10LCC10BT012', 'train', 'LCC10')],
        'G11HAH10BT003': [hit(S['b'], 0.2, 0.2, '11HAH10BT003', 'exact', '11')],
        'G12HAD10QN002': [hit(S['b'], 0.3, 0.3, '=G11 HAD10QN002', 'typical', 'G11', form='prefixed')],
        'G12HAD61QN404': [ocr(S['b'], 0.3, 0.4, '11HAD61 QN404', 'typical', '11', 0.7812, form='ocr-stacked', zone='B-3', zone_near=1)],
        'G11MBP01BP001': [hit(S['c'], 0.5, 0.5, 'GXXMBP01BP001', 'neutral', 'GXX', form='inline')],
        'C10LAB10BT001': [hit(S['d1'], 0.6, 0.6, 'C10LAB10BT001', 'exact', 'C10', note=1), hit(S['d2'], 0.6, 0.6, 'C10LAB10BT001', 'exact', 'C10', note=1),
                          hit(S['d2'], 0.7, 0.7, 'C10LAB10BT001', 'exact', 'C10', note=0)],
        'C10LAB10BT002': [hit(S['e'], 0.1, 0.2, 'C10LAB10BT002', 'exact', 'C10', note=1), hit(S['e'], 0.1, 0.3, 'C10LAB10 BT002', 'exact', 'C10', note=1)],
        'G12HSD10BF101': [ocr(S['root'], 0.4, 0.4, '=G12HSD10BF101', 'exact', 'G12', 0.95),
                          hit(S['root'], 0.4, 0.6, 'G12HSD10BF101', 'exact', 'G12', note=1),
                          ocr(S['root'], 0.4, 0.8, '=G12HSD10BF101', 'exact', 'G12', 0.81),
                          ocr(S['root'], 0.4, 0.4, '=G12HSD10BF101', 'exact', 'G12', 0.95)],
        '1-PI-CW014-1': [hit(S['c'], 0.9, 0.9, '1-PIT-CW014-1', 'loop', '')],
        # ---- 2026-10-10：note 代碼、ocr-fix、conf_min、同型各台（LAC）
        'G12HAP61BL001': [hit(S['flag'], 0.36, 0.5, 'G12HAP61BL001/2/3', 'exact', 'G12', note=2, zone='F-7', zone_near=1)],                 # 只有旗標
        'C10LCB40BT001': [hit(S['flag'], 0.5, 0.5, 'C10LCB40BT001', 'exact', 'C10'), hit(S['air'], 0.2, 0.2, 'C10LCB40BT001', 'exact', 'C10', note=2),
                          hit(S['flag'], 0.6, 0.5, 'C10LCB40BT001', 'exact', 'C10', note=2), hit(S['flag'], 0.7, 0.5, 'C10LCB40BT001', 'exact', 'C10', note=2),
                          hit(S['flag'], 0.8, 0.5, 'C10LCB40BT001', 'exact', 'C10', note=2)],
        'G12LAB65QN003': [hit(S['air'], 0.3, 0.3, '11LAB65 QN003', 'typical', '11', form='stacked', note=3)],                              # 只有用氣點
        'G12LAB65QN004': [hit(S['air'], 0.3, 0.4, '11LAB65 QN004', 'typical', '11', form='stacked', note=3), hit(S['air'], 0.5, 0.4, '11LAB65 QN004', 'typical', '11', note=2)],
        'C10LAC50BP005': [ocr(S['pump'], 0.65, 0.9, 'C10LAC50BP005', 'exact', 'C10', 0.821, note=4, form='ocr-fix', raw='C1OLAC50BPO05'),
                          ocr(S['pump'], 0.58, 0.9, 'C10LAC50BP005', 'exact', 'C10', 0.807, note=4, form='ocr-fix', raw='C1OLAC50BPOO5')],
        'C10LAC50BP006': [ocr(S['pump'], 0.73, 0.15, 'C10LAC50 BP006', 'exact', 'C10', 0.889), ocr(S['pump'], 0.26, 0.9, 'C10LAC50BP006', 'exact', 'C10', 0.889, note=4)],
        'C10LAC50BP007': [ocr(S['pump'], 0.53, 0.11, 'C10LAC50BP007', 'exact', 'C10', 0.881), ocr(S['pump'], 0.53, 0.5, 'C10LAC50BP007', 'exact', 'C10', 0.846, form='ocr-fix', raw='C1OLAC50BPO07'),
                          ocr(S['pump'], 0.46, 0.7, 'C10LAC50BP007', 'exact', 'C10', 0.772)],
        'C10LAC70BP005': [ocr(S['list'], 0.52, 0.37, 'C10LAC70BP005', 'exact', 'C10', 0.83, note=1)],                                       # 只在儀器清單（OCR）
        'C10LAC60BT022': [ocr(S['pump'], 0.21, 0.5, 'C10LAC50 BT022', 'train', 'LAC50', 0.818), ocr(S['list'], 0.47, 0.22, 'C10LAC60BT022', 'exact', 'C10', 0.836, note=1)],
        'C10LAC50BT011': [ocr(S['pump'], 0.67, 0.23, 'C10LAC50BT011', 'exact', 'C10', 0.799, form='ocr-fix')],                              # 舊資料：ocr-fix 沒有 raw
        'G12HAD10QN009': [ocr(S['b'], 0.6, 0.6, '=G11HAD10QN009', 'typical', 'G11', 0.9, form='ocr-fix', raw='=G11HAD1OQN009')],
        'C10LCP30QN014': [hit(S['flag'], 0.1, 0.8, 'C10LCP30QN014', 'exact', 'C10'), ocr(S['flag'], 0.2, 0.8, 'C10LCP30 QN014', 'exact', 'C10', 0.798)],
        'C10LAB20BT009': [ocr(S['b'], 0.8, 0.8, 'C10LAB20 BT009', 'exact', 'C10', 0.9, note=1)],                                            # 有文字層的頁上的 OCR 清單列
        'C10LAF71QN001_': [hit(S['flag'], 0.15, 0.15, 'C10LAF71 QN001', 'exact', 'C10', form='stacked')],
        'G11_96DT-6_01': [hit(S['c'], 0.2, 0.9, '(96DT-6)', 'neutral', '')],
        'G12_90VA41-2': [hit(S['c'], 0.3, 0.9, '(90VA41-2)', 'neutral', ''), hit(S['e'], 0.5, 0.5, '(90VA41-2', 'neutral', '', note=1)],
        'G12_90VA41-21': [hit(S['e'], 0.6, 0.5, '90VA41-21).', 'neutral', '', note=1)],
        'G12HAH10BT005': [hit(S['b'], 0.1, 0.9, 'G12HAH10BT005', 'exact', 'G12'), hit(S['b'], 0.2, 0.9, '12HAH10BT005', 'exact', '12'), hit(S['b'], 0.3, 0.9, '12HAH10 BT005', 'exact', '12', form='stacked')],
        'C10LAC50BT044': [ocr(S['pump'], 0.15, 0.32, 'C10LAC50 BT044B', 'exact', 'C10', 0.873), ocr(S['pump'], 0.12, 0.33, 'C10LAC50 BT044C10LAC50 BTO44A', 'exact', 'C10', 0.879)],   # 產生器修好之後不該再有；防呆
        'G11HAP65BP001': [hit(S['air'], 0.9, 0.9, 'G11/12HAP65 BP001', 'exact', 'G11')],
        'C10XYZ10BT001': [hit(S['air'], 0.8, 0.1, 'C10XYZ10BT001', 'exact', 'C10', note=7)],                                                # 認不得的代碼
    }
    pm = {'sheets': sheets, 'by_tag': by_tag, '_applied': set(), '_shots_dir': '', '_shots': {s: {'file': s + '.webp', 'w': 10, 'h': 10, 'rot': 0, 'src': {'size': 1, 'mtime': 2}} for s in sheets}}
    pm['_used'] = sorted({e['sheet'] for v in by_tag.values() for e in v})
    pm['_dkey'], pm['_docs'] = B.pid_doc_keys(pm)

    def rows(tag):
        return B.pid_rows(pm, tag)

    # ---------------------------------------------------------------- 圖紙鍵與 docs 鍵
    ck('圖紙鍵：SPEC 的例子', B.pid_slug('03_HRSG 餘熱鍋爐/02_流程與電控圖面/HT0-1-KND01-D0027-4-HRSG SCR System P&ID.pdf', 2) == 'HT0-1-KND01-D0027-4_1030bef1__p2')
    ck('檔名沒有 HT 編號：圖紙鍵 x_<sha8>__p2、docs 鍵 pid|<sha12>|', S['c'].startswith('x_') and S['c'].endswith('__p2') and pm['_dkey'][S['c']].startswith('pid|')
       and pm['_dkey'][S['c']].endswith('|') and len(pm['_dkey'][S['c']].split('|')[1]) == 12)
    ck('兩個檔同一組 編號＋版次：圖紙鍵不同；路徑在前的用 pid|doc|rev，在後的退用 pid|<sha12>|',
       S['d1'] != S['d2'] and pm['_dkey'][S['d1']] == 'pid|HT0-1-AFF01-D0011|2' and pm['_dkey'][S['d2']] != pm['_dkey'][S['d1']] and len(pm['_dkey'][S['d2']].split('|')[1]) == 12)
    ck('檔名沒有版次：圖紙鍵只有編號，docs 鍵 pid|doc|', S['e'].startswith('HT0-1-GFD01-D0013_') and pm['_dkey'][S['e']] == 'pid|HT0-1-GFD01-D0013|')
    ck('docs 項目：title＝檔名、folder＝文件庫相對資料夾（根目錄是 "."），沒有本機絕對路徑',
       pm['_docs'][pm['_dkey'][S['a']]]['title'] == 'HT0-1-TCM01-D1114-3 Condensate pumps.pdf' and pm['_docs'][pm['_dkey'][S['a']]]['folder'] == 'sysA'
       and pm['_docs'][pm['_dkey'][S['root']]]['folder'] == '.' and not B.ABS_PATH_RE.search(json.dumps(pm['_docs'], ensure_ascii=False)))
    ck('合成的圖紙鍵都能當檔名', all(B.HMI_SLUG_RE.match(s) for s in S.values()))

    # ---------------------------------------------------------------- rel 與 form（原有的說法）
    r = rows('C10LCC20BT012')
    ck('train：圖上畫的是 LCC10、unit LCC10、lvl 推論', r[3][1] == 'C10LCC10BT012（這份圖只畫 LCC10 一台，圖面把同型各台並列為同一張圖適用，本台 LCC20 取同一位置）' and r[0][4]['unit'] == 'LCC10' and r[0][2] == 'inferred', r[3][1])
    r = rows('G11HAH10BT003')
    ck('exact，圖上只寫機組數字：講明省略機組字母、unit G11、lvl 文件', r[3][1] == '11HAH10BT003（就是本台位號，圖上省略機組字母 G）' and r[0][4]['unit'] == 'G11' and r[0][2] == 'doc', r[3][1])
    r = rows('G12HAD10QN002')
    ck('typical＋prefixed：典型圖的說法；對應方式講前綴分開寫；推論', '以 G11 繪製的典型圖，本台 G12 取同一位置' in r[3][1] and r[4][1] == 'PDF 文字層（機組前綴與位號分開寫，合併後對上）' and r[0][2] == 'inferred', (r[3][1], r[4][1]))
    r = rows('G12HAD61QN404')
    ck('typical 由 OCR 讀出（上下拆寫、只寫機組數字、zone_near）：約 B-3、unit G11、conf 原值、文字寫 0.78 與拆寫',
       r[2][1] == '圖面左 31%／上 40%（圖框分區約 B-3）' and r[0][4]['unit'] == 'G11' and r[0][4]['conf'] == 0.7812 and r[0][4]['zone'] == 'B-3' and r[0][4].get('zone_near') == 1
       and r[4][1] == 'OCR 讀圖（圖上的位號是線條字，不在 PDF 文字層；上下兩行拆寫合併；辨識信心 0.78）', (r[2][1], r[4][1]))
    ck('OCR 讀到的字前面標明是辨識結果；單一 OCR 標記也帶 conf_min／confs', r[3][1] == 'OCR 讀到的字：11HAD61 QN404（這張是以 G11 繪製的典型圖，本台 G12 取同一位置）'
       and r[0][4]['conf_min'] == 0.7812 and r[0][4]['confs'] == [0.7812], (r[3][1], r[0][4]))
    r = rows('G11MBP01BP001')
    ck('neutral＋機組佔位字＋inline；沒有 HT 編號時「P&ID 圖面」＝去掉 .pdf 的檔名',
       r[3][1] == 'GXXMBP01BP001（圖上的機組寫成 GXX；這張圖不分機組，各機組共用）' and r[4][1] == 'PDF 文字層（同一行分兩段寫，合併後對上）' and r[0][1] == 'vendor P&ID no number' and r[0][2] == 'doc', r[3][1])
    r = rows('1-PI-CW014-1')
    ck('loop（drawn_as 是空字串）：unit 空、句子寫出兩支位號', r[0][4]['unit'] == '' and r[3][1] == '1-PIT-CW014-1（同一迴路的儀器，與本台位號 1-PI-CW014-1 只差功能代號，依迴路編號對應）', r[3][1])
    ck('03 的位號有空白／小寫也對得到；空字串與不存在的位號回空', len(B.pid_rows(pm, ' c10lcc20bt012 ')) == 5 and B.pid_rows(pm, '') == [] and B.pid_rows(pm, 'NOPE') == [])
    allrows = [x for t in by_tag for x in B.pid_rows(pm, t)]
    ck('每一列：5 個元素、lvl 是 doc／inferred、來源＝「<文件|推論> · <檔名> 第 2 頁」',
       all(len(x) == 5 and x[2] in ('doc', 'inferred') and x[3].endswith(' 第 2 頁') and x[3].split(' · ')[0] in ('文件', '推論') for x in allrows))
    ck('每組 5 列的欄位名稱與順序', [x[0] for x in rows('C10LCC20BT012')] == ['P&ID 圖面', '圖面頁次', '所在位置', '圖上標示', '對應方式'])

    # ---------------------------------------------------------------- note 1：註記／表格（儀器清單）
    r = rows('C10LAB10BT001')
    ck('圖紙順序＝pid.json 第一次出現的順序；同一張裡符號標籤是 ①、註記是 ②，「所在位置」講明 ② 是什麼',
       [x[4]['s'] for x in r[::5]] == [S['d1'], S['d2']] and r[5][4]['marks'][0][:2] == [0.71, 0.702] and 'note' not in r[5][4] and r[5][4]['notes'] == [0, 1]
       and r[7][1] == '圖面左 71%／上 70%＝圖上標記 ①；這支位號在同一張圖另有 1 處（圖上 ②），其中 ② 是圖上註記或表格（儀器清單）裡的文字（不是儀器符號的位置）', r[7][1])
    ck('整張圖只有註記：extra.note＝1、notes＝[1]；「圖上標示」講明不是符號旁的標籤，並指到另一張有符號的圖紙',
       r[0][4].get('note') == 1 and r[0][4]['notes'] == [1] and r[3][1] == 'C10LAB10BT001（%s）；%s；%s' % (SAME, N1, ELSEWHERE)
       and r[2][1] == '圖面左 61%／上 60%；這一處是圖上註記或表格（儀器清單）裡的文字，不是儀器符號的位置', (r[3][1], r[2][1]))
    ck('符號標籤那一張不帶 note，也不說「不是儀器符號」', r[8][1] == 'C10LAB10BT001（%s）' % SAME, r[8][1])
    r = rows('C10LAB10BT002')
    ck('頁數不明：沒有 n、不寫（共 N 頁）；沒有版次：「P&ID 圖面」不寫 Rev.', 'n' not in r[0][4] and r[1][1] == 'PDF 第 2 頁' and r[0][1] == 'HT0-1-GFD01-D0013　T', (r[0][1], r[1][1]))
    ck('任何一張圖都沒有符號標籤：直說圖上沒有找到儀器符號；只差空白的兩處不算「另一種寫法」',
       r[3][1] == 'C10LAB10BT002（%s）；%s；%s' % (SAME, N1, NOSYM) and '寫成' not in r[3][1]
       and r[2][1].endswith('；這 2 處都是圖上註記或表格（儀器清單）裡的文字，不是儀器符號的位置') and r[0][4]['note'] == 1 and r[0][4]['notes'] == [1, 1], (r[3][1], r[2][1]))
    r = rows('G12HSD10BF101')
    ck('同一張圖 OCR＋文字層：重複的合併（3 處）、OCR 的符號標籤在前、文字層的註記在後；how／conf 講 ①，conf_min 是最低的那處',
       len(r[0][4]['marks']) == 3 and r[0][4]['how'] == 'ocr' and r[0][4]['conf'] == 0.95 and r[0][4]['conf_min'] == 0.81 and r[0][4]['confs'] == [0.95, 0.81, None]
       and r[0][2] == 'inferred' and r[0][4]['notes'] == [0, 0, 1] and 'note' not in r[0][4]
       and r[4][1] == 'OCR 讀圖（圖上的位號是線條字，不在 PDF 文字層；辨識信心 ① 0.95、② 0.81）；圖上 ③ 在 PDF 文字層'
       and r[3][1] == 'OCR 讀到的字：=G12HSD10BF101（%s）' % SAME, (r[4][1], r[3][1], r[0][4]))

    # ---------------------------------------------------------------- note 2：跨圖訊號旗標
    r = rows('G12HAP61BL001')
    ck('只有旗標（任何一張圖都沒有符號）：note＝2；不寫「與本台位號相同」（圖上是合寫的標籤）；講明是旗標、圖上沒有找到符號；文字層 exact 仍是「文件」',
       r[0][4]['note'] == 2 and r[0][4]['notes'] == [2] and r[0][2] == 'doc' and SAME not in r[3][1]
       and r[3][1] == 'G12HAP61BL001/2/3（圖上把幾支位號合寫成一個標籤，本台是其中一支）；%s；%s' % (N2, NOSYM)
       and r[2][1] == '圖面左 37%／上 50%（圖框分區約 F-7）；這一處是跨圖訊號旗標，不是儀器符號的位置', (r[3][1], r[2][1]))
    r = rows('C10LCB40BT001')
    ck('符號＋3 個旗標在同一張、另一張只有旗標：符號那張排第一、① 是符號；「所在位置」逐處講明 ②③④ 是旗標',
       [x[4]['s'] for x in r[::5]] == [S['flag'], S['air']] and 'note' not in r[0][4] and r[0][4]['notes'] == [0, 2, 2, 2] and r[0][4]['marks'][0][:2] == [0.51, 0.502]
       and r[2][1] == '圖面左 51%／上 50%＝圖上標記 ①；這支位號在同一張圖另有 3 處（圖上 ②、③、④），其中 ②、③、④ 是跨圖訊號旗標（不是儀器符號的位置）'
       and r[3][1] == 'C10LCB40BT001（%s）' % SAME, (r[2][1], r[3][1]))
    ck('只有旗標的那一張：note＝2，「圖上標示」指到另一張有符號的圖紙', r[5][4]['note'] == 2 and r[8][1] == 'C10LCB40BT001（%s）；%s；%s' % (SAME, N2, ELSEWHERE), r[8][1])

    # ---------------------------------------------------------------- note 3：空氣分配圖的用氣點
    r = rows('G12LAB65QN003')
    ck('只有用氣點（典型圖）：note＝3，講明是供氣接點、不是閥在製程管線上的位置；圖上沒有找到符號',
       r[0][4]['note'] == 3 and r[0][4]['rel'] == 'typical' and r[0][2] == 'inferred'
       and r[3][1] == '11LAB65 QN003（這張是以 G11 繪製的典型圖，本台 G12 取同一位置）；%s；%s' % (N3, NOSYM)
       and r[2][1] == '圖面左 31%／上 30%；這一處是儀用／廠用空氣分配圖上的用氣點，不是儀器符號的位置', (r[3][1], r[2][1]))
    r = rows('G12LAB65QN004')
    ck('同一張圖上兩種引用（3＋2）、沒有符號：note＝1（混合），notes 逐處帶代碼；「所在位置」逐處講是哪一種；「圖上標示」照 ① 自己的種類講',
       r[0][4]['note'] == 1 and r[0][4]['notes'] == [3, 2]
       and r[2][1] == '圖面左 31%／上 40%＝圖上標記 ①；這支位號在同一張圖另有 1 處（圖上 ②）；① 是儀用／廠用空氣分配圖上的用氣點，② 是跨圖訊號旗標，都不是儀器符號的位置'
       and N3 in r[3][1] and N2 not in r[3][1], (r[2][1], r[3][1]))

    # ---------------------------------------------------------------- note 4：迴路詳圖；ocr-fix 與 raw
    r = rows('C10LAC50BP005')
    ck('迴路詳圖＋ocr-fix：note＝4；不寫「與本台位號相同」，改寫 OCR 原本讀成什麼；extra.fix／raw',
       r[0][4]['note'] == 4 and r[0][4]['notes'] == [4, 4] and r[0][4]['fix'] == 1 and r[0][4]['raw'] == 'C1OLAC50BPO05' and SAME not in r[3][1]
       and r[3][1] == 'C10LAC50BP005（OCR 讀成「C1OLAC50BPO05」，%s校正後才對上本台位號）；%s；%s' % (FIX, N4, NOSYM), r[3][1])
    ck('沒有文字層的頁：「對應方式」不說線條字；① 的校正寫在括號裡，② 的校正另外點名；辨識信心逐處寫',
       r[4][1] == ('OCR 讀圖（這一頁沒有 PDF 文字層，圖上的字是影像或線條畫出來的；OCR 讀成「C1OLAC50BPO05」，%s校正後才對上本台位號；辨識信心 ① 0.82、② 0.81）；'
                   '圖上 ② 的字經過%s校正（OCR 讀成「C1OLAC50BPOO5」）' % (FIX, FIX)) and '線條字' not in r[4][1], r[4][1])
    ck('兩處都是迴路詳圖：「所在位置」說這 2 處都是', r[2][1].endswith('；這 2 處都是迴路詳圖（TYPICAL 小圖）裡的標籤，不是儀器符號的位置'), r[2][1])
    r = rows('C10LAC50BP006')
    ck('符號＋迴路詳圖在同一張：① 是符號（不帶 note）、② 講明是迴路詳圖；只差空白的 ② 不算另一種寫法',
       'note' not in r[0][4] and r[0][4]['notes'] == [0, 4] and r[2][1].endswith('，其中 ② 是迴路詳圖（TYPICAL 小圖）裡的標籤（不是儀器符號的位置）')
       and r[3][1] == 'OCR 讀到的字：C10LAC50 BP006（%s）' % SAME, (r[2][1], r[3][1]))
    r = rows('C10LAC50BT011')
    ck('ocr-fix 但 pid.json 沒給 raw（舊資料）：照樣講明有校正，不寫「與本台位號相同」；fix＝1、沒有 raw 鍵',
       r[3][1] == 'C10LAC50BT011（OCR 讀到的字有%s讀錯，校正後才對上本台位號）' % FIX and SAME not in r[3][1] and r[0][4]['fix'] == 1 and 'raw' not in r[0][4]
       and r[0][4]['conf_min'] == 0.799, r[3][1])
    r = rows('G12HAD10QN009')
    ck('ocr-fix 的典型圖：先講典型圖，再講校正後才是圖上那串字（不是「對上本台位號」）',
       r[3][1] == '=G11HAD10QN009（這張是以 G11 繪製的典型圖，本台 G12 取同一位置；OCR 讀成「=G11HAD1OQN009」，%s校正後才是這串字）' % FIX
       and r[4][1] == 'OCR 讀圖（圖上的位號是線條字，不在 PDF 文字層；OCR 讀成「=G11HAD1OQN009」，%s校正後才是這串字；辨識信心 0.90）' % FIX, (r[3][1], r[4][1]))

    # ---------------------------------------------------------------- OCR：conf_min、清單頁
    r = rows('C10LAC50BP007')
    ck('三處 OCR、只有 ③ 低於 0.8：conf＝①、conf_min＝③、confs 逐處；「對應方式」逐處寫信心，② 的校正點名',
       r[0][4]['conf'] == 0.881 and r[0][4]['conf_min'] == 0.772 and r[0][4]['confs'] == [0.881, 0.846, 0.772] and 'fix' not in r[0][4]
       and r[4][1] == ('OCR 讀圖（這一頁沒有 PDF 文字層，圖上的字是影像或線條畫出來的；辨識信心 ① 0.88、② 0.85、③ 0.77）；圖上 ② 的字經過%s校正（OCR 讀成「C1OLAC50BPO07」）' % FIX),
       (r[0][4], r[4][1]))
    r = rows('C10LCP30QN014')
    ck('① 是文字層、② 是 OCR 而且信心偏低：沒有 conf（那是 ① 的），conf_min 與 confs 照樣帶；lvl 以 ① 為準＝文件；0.798 不印成 0.80',
       'conf' not in r[0][4] and r[0][4]['conf_min'] == 0.798 and r[0][4]['confs'] == [None, 0.798] and r[0][2] == 'doc' and r[0][4]['how'] == 'text'
       and r[4][1] == 'PDF 文字層；圖上 ② 是 OCR 讀圖（圖上的位號是線條字，不在 PDF 文字層；辨識信心 ② 0.798）', (r[0][4], r[4][1]))
    ck('全是文字層的圖紙不帶 conf／conf_min／confs／notes', not any(k in rows('G11HAH10BT003')[0][4] for k in ('conf', 'conf_min', 'confs', 'notes', 'note', 'fix', 'raw')))
    r = rows('C10LAC70BP005')
    ck('只在儀器清單、由 OCR 讀出（整頁沒有文字層）：不說線條字，說清單沒有文字層；講明不是符號、圖上沒有找到符號',
       r[4][1] == 'OCR 讀圖（這一頁的清單／註記沒有 PDF 文字層；辨識信心 0.83）' and '線條字' not in r[4][1] and r[0][4]['note'] == 1
       and r[3][1] == 'OCR 讀到的字：C10LAC70BP005（%s）；%s；%s' % (SAME, N1, NOSYM), (r[4][1], r[3][1]))
    r = rows('C10LAB20BT009')
    ck('有文字層的頁上、由 OCR 讀出的清單列：說那一處的清單文字不在文字層（也不說線條字）', r[4][1] == 'OCR 讀圖（這一處的清單／註記文字不在 PDF 文字層；辨識信心 0.90）', r[4][1])

    # ---------------------------------------------------------------- 同型各台（LAC60 畫成 LAC50）
    r = rows('C10LAC60BT022')
    ck('train 由 OCR 讀出：圖上畫的是 LAC50、unit LAC50、推論；自己那一列清單是另一張圖紙上的引用（note 1），指回有符號的那一張',
       [x[4]['s'] for x in r[::5]] == [S['pump'], S['list']] and r[0][4]['rel'] == 'train' and r[0][4]['unit'] == 'LAC50' and r[0][2] == 'inferred' and 'note' not in r[0][4]
       and r[3][1] == 'OCR 讀到的字：C10LAC50 BT022（這份圖只畫 LAC50 一台，圖面把同型各台並列為同一張圖適用，本台 LAC60 取同一位置）'
       and r[5][4]['note'] == 1 and r[5][4]['rel'] == 'exact' and r[8][1] == 'OCR 讀到的字：C10LAC60BT022（%s）；%s；%s' % (SAME, N1, ELSEWHERE), (r[3][1], r[8][1]))

    # ---------------------------------------------------------------- 「與本台位號相同」的紀律、標籤清理、其他寫法
    r = rows('C10LAF71QN001_')
    ck('AMS 位號結尾有 _：圖上沒有，不寫「相同」，講明差在哪裡', r[3][1] == 'C10LAF71 QN001（就是本台位號，圖上沒有 AMS 位號結尾的「_」）', r[3][1])
    r = rows('G11_96DT-6_01')
    ck('GE 位號（不分機組）照舊；成對的括號是圖上的畫法，照留', r[3][1] == '(96DT-6)（這張圖不分機組，各機組共用）' and r[0][4]['drawn'] == '(96DT-6)', r[3][1])
    r = rows('G12_90VA41-2')
    ck('註記句子切出來的殘字：不成對的括號拿掉（圖上標示與 extra.drawn）', r[8][1].startswith('90VA41-2（這張圖不分機組，各機組共用）；' + N1) and r[5][4]['drawn'] == '90VA41-2', r[8][1])
    r = rows('G12_90VA41-21')
    ck('註記句尾的標點與括號拿掉', r[3][1].startswith('90VA41-21（') and r[0][4]['drawn'] == '90VA41-21', r[3][1])
    r = rows('G12HAH10BT005')
    ck('同一張圖上真的有另一種寫法（省略機組字母）才列出來，而且講是 ②③ 哪幾處；只差空白的併在一起',
       r[3][1] == 'G12HAH10BT005（%s）；圖上 ②、③ 寫成 12HAH10BT005' % SAME, r[3][1])
    r = rows('C10LAC50BT044')
    ck('防呆（產生器不該再給）：帶元件尾碼／幾個標籤黏成一串的 exact 命中——不寫「就是本台位號」也不寫「相同」，叫人對照圖面；黏成一串的不列為另一種寫法',
       SAME not in r[3][1] and '就是本台位號' not in r[3][1] and '請對照圖面確認' in r[3][1] and '寫成' not in r[3][1] and r[0][4].get('odd') == 1
       and 'odd' not in rows('G12HAH10BT005')[0][4] and 'odd' not in rows('G11HAP65BP001')[0][4], (r[3][1], r[0][4]))
    ck('pid_label_is_tag：相同／省略機組字母／少了 _01／合寫標籤算，元件尾碼與黏字不算',
       B.pid_label_is_tag('G12HAH10BT005', '12HAH10 BT005') and B.pid_label_is_tag('G11_96PG-2A_01', 'G11_96PG-2A') and B.pid_label_is_tag('C10MAG10BL002', 'C10MAG10BL001/2/3')
       and not B.pid_label_is_tag('C10LAC50BT044', 'C10LAC50 BT044B') and not B.pid_label_is_tag('C10MAJ61BT013', 'C10MAJ61BT013DN25') and not B.pid_label_is_tag('S10MAV01BP272', 'S10MAV01BP272C'))
    import io as _io
    import contextlib
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        n_odd = B.pid_odd_labels(pm)
    ck('pid_odd_labels 把對不起來的 exact 命中印出來（不擋建置）', n_odd == 2 and '!! pid: 2 筆' in buf.getvalue() and 'C10LAC50BT044' in buf.getvalue(), buf.getvalue()[:200])
    r = rows('G11HAP65BP001')
    ck('合寫兩台機組的標籤（G11/12…）：不寫「相同」，說是合寫', r[3][1] == 'G11/12HAP65 BP001（圖上把幾支位號合寫成一個標籤，本台是其中一支）', r[3][1])
    r = rows('C10XYZ10BT001')
    ck('認不得的 note 代碼：照樣當引用（不會被當成符號），用上位的說法', r[0][4]['note'] == 7 and r[0][4]['notes'] == [7] and '不是儀器符號旁的標籤' in r[3][1] and NOSYM in r[3][1]
       and r[2][1].endswith('不是儀器符號的位置'), (r[3][1], r[2][1]))
    ck('全部合成資料裡，「與本台位號相同」只出現在正規化後真的等於位號、而且不是 ocr-fix 的 ① 上',
       all((SAME not in B.pid_rows(pm, t)[5 * g + 3][1]) or (B.pid_norm(B.pid_label_clean(u[0].get('label'))) == B.pid_norm(t) and u[0].get('form') != 'ocr-fix')
           for t in by_tag for g, u in enumerate(_groups(B, by_tag[t]))))

    # ---------------------------------------------------------------- 關卡：同一個框被幾支位號認領
    def share(*claims):
        bt = {}
        for tag, label, rel, da in claims:
            bt.setdefault(tag, []).append(hit('S', 0.5, 0.5, label, rel, da))
        return B.pid_shared_boxes(bt)
    ck('關卡：機組雙胞胎（G11 exact＋G12 typical）不擋', share(('G11HSD10QN101', '=G11HSD10QN101', 'exact', 'G11'), ('G12HSD10QN101', '=G11HSD10QN101', 'typical', 'G11')) == [])
    ck('關卡：不分機組的 GE 位號（G11_／G12_）與 _01 重複名稱不擋',
       share(('G11_96PG-2A', '(96PG-2A)', 'neutral', ''), ('G12_96PG-2A', '(96PG-2A)', 'neutral', ''), ('G11_96PG-2A_01', '(96PG-2A)', 'neutral', ''), ('G12_96PG-2A_01', '(96PG-2A)', 'neutral', '')) == [])
    ck('關卡：AMS 位號結尾多一個 _ 的重複名稱不擋', share(('C10LAF71QN001', 'C10LAF71 QN001', 'exact', 'C10'), ('C10LAF71QN001_', 'C10LAF71 QN001', 'exact', 'C10')) == [])
    ck('關卡：同型各台（LCC20／LCC30 畫成 LCC10；LAC60／LAC70 畫成 LAC50）不擋',
       share(('C10LCC10BT012', 'C10LCC10BT012', 'exact', 'C10'), ('C10LCC20BT012', 'C10LCC10BT012', 'train', 'LCC10'), ('C10LCC30BT012', 'C10LCC10BT012', 'train', 'LCC10')) == []
       and share(('C10LAC50BT022', 'C10LAC50 BT022', 'exact', 'C10'), ('C10LAC60BT022', 'C10LAC50 BT022', 'train', 'LAC50'), ('C10LAC70BT022', 'C10LAC50 BT022', 'train', 'LAC50')) == [])
    ck('關卡：合寫的標籤（…BL001/2/3、C10PHC10/20、G11/12…）不擋',
       share(('C10MAG10BL001', 'C10MAG10BL001/2/3', 'exact', 'C10'), ('C10MAG10BL002', 'C10MAG10BL001/2/3', 'exact', 'C10'), ('C10MAG10BL003', 'C10MAG10BL001/2/3', 'exact', 'C10')) == []
       and share(('C10PHC10BT010', 'C10PHC10/20 BT010', 'exact', 'C10'), ('C10PHC20BT010', 'C10PHC10/20 BT010', 'exact', 'C10')) == [])
    ck('關卡：迴路對應（PI 借 PIT 的位置）不擋', share(('1-PIT-CW014-1', '1-PIT-CW014-1', 'exact', ''), ('1-PI-CW014-1', '1-PIT-CW014-1', 'loop', '')) == [])
    ck('關卡：同一支位號在同一個框出現兩次不算', share(('C10LAB10BT001', 'C10LAB10BT001', 'exact', 'C10'), ('C10LAB10BT001', 'C10LAB10BT001', 'exact', 'C10')) == [])
    b = share(('S10MAV01BP272', 'MAV01BP272C', 'neutral', ''), ('S10MAV01BP272C', 'MAV01BP272C', 'neutral', ''))
    ck('關卡：稽核的實例（S10MAV01BP272 與 BP272C 掛在同一個標籤）擋下來，訊息點出兩支位號', len(b) == 1 and 'S10MAV01BP272（' in b[0] and 'S10MAV01BP272C（' in b[0], b)
    ck('關卡：元件尾碼（BT044 與 BT044A）、同型但設備碼不同、共用與機組（C10／S10）互掛都擋',
       len(share(('C10LAC50BT044', 'C10LAC50 BT044A', 'exact', 'C10'), ('C10LAC50BT044A', 'C10LAC50 BT044A', 'exact', 'C10'))) == 1
       and len(share(('C10LCC10BT012', 'C10LCC10BT012', 'exact', 'C10'), ('C10LCC20BT013', 'C10LCC10BT012', 'train', 'LCC10'))) == 1
       and len(share(('C10LBA10BP001', 'LBA10BP001', 'neutral', ''), ('S10LBA10BP001', 'LBA10BP001', 'neutral', ''))) == 1)
    tmp = tempfile.mkdtemp(prefix='pidtest_')
    try:
        vp8l = b'RIFF' + struct.pack('<I', 100) + b'WEBP' + b'VP8L' + struct.pack('<I', 50) + b'\x2f' + struct.pack('<I', (3200 - 1) | ((2261 - 1) << 14)) + b'\0' * 8
        vp8x = b'RIFF' + struct.pack('<I', 100) + b'WEBP' + b'VP8X' + struct.pack('<I', 10) + b'\0\0\0\0' + (1279).to_bytes(3, 'little') + (719).to_bytes(3, 'little') + b'\0' * 4
        for name, data, want in (('l.webp', vp8l, (3200, 2261)), ('x.webp', vp8x, (1280, 720)), ('bad.webp', b'\x89PNG' + b'\0' * 40, None), ('short.webp', b'RIFF', None)):
            p = os.path.join(tmp, name)
            open(p, 'wb').write(data)
            ck('pid_webp_size(%s) == %s' % (name, want), B.pid_webp_size(p) == want, B.pid_webp_size(p))
        # pid_check 整合：一張圖紙＋一個真的 WebP 檔頭；乾淨的資料過關，BP272 那種資料以非 0 結束
        rel = 'sysT/HT0-1-TFD01-D0002-3 - Turbine.pdf'
        s = B.pid_slug(rel, 4)
        open(os.path.join(tmp, s + '.webp'), 'wb').write(vp8l)

        def mk(bt):
            return {'sheets': {s: sheet(rel, 4)}, 'by_tag': bt, '_applied': set(), '_shots_dir': tmp,
                    '_shots': {s: {'file': s + '.webp', 'w': 3200, 'h': 2261, 'rot': 0, 'src': {'size': 1, 'mtime': 2}}}}

        def check(bt):
            out = _io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    B.pid_check(mk(bt), 'pid.json')
                return None, out.getvalue()
            except SystemExit as e:
                return str(e), out.getvalue()
        ok = check({'S10MAV01BP272C': [hit(s, 0.7, 0.3, 'MAV01BP272C', 'neutral')], 'S10MAV01BP272': [hit(s, 0.6, 0.1, 'MAV01BP272', 'neutral')]})
        ck('pid_check：各認各的標籤 → 過關', ok[0] is None and '!!' not in ok[1], ok)
        bad = check({'S10MAV01BP272C': [hit(s, 0.7, 0.3, 'MAV01BP272C', 'neutral')], 'S10MAV01BP272': [hit(s, 0.7, 0.3, 'MAV01BP272C', 'neutral'), hit(s, 0.6, 0.1, 'MAV01BP272', 'neutral')]})
        ck('pid_check：同一個標籤被兩支不相干的位號認領 → 以非 0 結束（SystemExit），並印出是哪兩支', bad[0] is not None and '!! pid:' in bad[1] and 'S10MAV01BP272C' in bad[1] and '同一個標籤' in bad[1], bad)
        badn = check({'S10MAV01BP272': [hit(s, 0.6, 0.1, 'MAV01BP272', 'neutral', note='x')]})
        ck('pid_check：note 不是 0 或正整數 → 以非 0 結束', badn[0] is not None and 'note' in badn[1], badn)
        # pid_collect 不寫檔；pid_write_images 才清空重寫
        outdir = os.path.join(tmp, 'data')
        os.makedirs(os.path.join(outdir, 'card', 'pid'))
        stale = os.path.join(outdir, 'card', 'pid', 'stale.json')
        open(stale, 'w').write('{}')
        pm2 = mk({'S10MAV01BP272': [hit(s, 0.6, 0.1, 'MAV01BP272', 'neutral')], 'S10MAV01BP272C': [hit(s, 0.7, 0.3, 'MAV01BP272C', 'neutral', note=2)]})
        pm2['stats'] = {'drawings': 5, 'pages': 9}
        pm2['_used'] = [s]
        pm2['_dkey'], pm2['_docs'] = B.pid_doc_keys(pm2)
        out = {'A1': {'sec': {'pid': {'rows': B.pid_rows(pm2, 'S10MAV01BP272')}}}, 'A2': {'sec': {'pid': {'rows': B.pid_rows(pm2, 'S10MAV01BP272C')}}}, 'A3': {'sec': {}}}
        st = {}
        with contextlib.redirect_stdout(_io.StringIO()):
            ix, blobs = B.pid_collect(out, pm2, st)
        ck('pid_collect：只收集、不寫檔（舊的 card/pid/ 原封不動）；index.pid 的 files／sheets／bytes 與影像內容一致',
           os.listdir(os.path.join(outdir, 'card', 'pid')) == ['stale.json'] and list(blobs) == ['card/pid/%s.json' % s] == ix['files']
           and ix['sheets'][s]['bytes'] == len(blobs[ix['files'][0]]) == ix['bytes'] and ix['sheets'][s]['rows'] == 2 and json.loads(blobs[ix['files'][0]].decode('utf-8'))['w'] == 3200, ix)
        ck('pid_collect：stats 的 devices／devices_ref_only（每張圖都只有引用的設備數）／images', ix['stats']['devices'] == 2 and ix['stats']['devices_ref_only'] == 1 and ix['stats']['images'] == 1
           and ix['stats']['drawings'] == 5 and st['pid']['bytes'] == ix['bytes'], ix['stats'])
        B.pid_write_images(outdir, blobs)
        ck('pid_write_images：清掉舊檔、寫出新檔', os.listdir(os.path.join(outdir, 'card', 'pid')) == [s + '.json'])
        B.pid_write_images(outdir, {})
        ck('pid_write_images（空的）：只清，不留 card/pid/', not os.path.exists(os.path.join(outdir, 'card', 'pid')))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    real = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'AMS', 'cardwork', 'hmi_shots')   # 建置機才有：真的有損 WebP（VP8）檔頭
    lossy = next((f for f in sorted(os.listdir(real)) if f.endswith('.webp')), None) if os.path.isdir(real) else None
    if lossy:
        ck('pid_webp_size 讀得懂有損 WebP（hmi_shots 的 1280 寬縮圖）', (B.pid_webp_size(os.path.join(real, lossy)) or (0,))[0] == 1280, lossy)
    else:
        print('  （略過：這台機器沒有 %LOCALAPPDATA%/AMS/cardwork/hmi_shots，有損 WebP 檔頭那一筆沒測）')

    # ---------------------------------------------------------------- searched.pid 的說法（數字全取自 stats）
    full = {'drawings': 372, 'pages': 1047, 'pages_cover': 240, 'pages_sheet': 807, 'pages_text': 595, 'pages_sparse': 212, 'pages_ocr': 807,
            'located': 1568, 'ams_tags_base': 1679, 'devices': 1568, 'devices_ref_only': 41, 'images': 118, 'docs': 54, 'no_url': 0}
    d = B.pid_doc(full)
    ck('searched.pid：每一張圖紙頁都做過 OCR，其中幾頁的位號只在 OCR 結果裡——不再說「線條字的頁面再以 OCR 補」',
       '共 372 份 1047 頁：其中 240 頁是封面、目錄等非圖紙頁；595 頁有 PDF 文字層可比對；所有圖紙頁都做過離線 OCR（807 頁），其中 212 頁的位號只在 OCR 結果裡' in d['why']
       and '再以離線 OCR 補' not in d['why'] and '1568/1679' in d['why'] and '其中 41 台只找到引用、沒有找到儀器符號' in d['why'] and d['ref'] == '現行 P&ID 圖面（372 份 1047 頁，PDF 文字層＋OCR）', d['why'])
    d2 = B.pid_doc(dict(full, pages_ocr=600))
    ck('searched.pid：不是每一張圖紙頁都做過 OCR 時照實寫頁數', '600 頁做過離線 OCR' in d2['why'] and '所有圖紙頁' not in d2['why'], d2['why'][:200])
    d3 = B.pid_doc(dict(full, pages_ocr=0))
    ck('searched.pid：還沒有 OCR 結果', '還沒有離線 OCR 的結果' in d3['why'] and d3['ref'].endswith('PDF 文字層）'), d3['why'][:200])
    d4 = B.pid_doc({'drawings': 3})
    ck('searched.pid：stats 缺鍵不炸、不印 None', 'None' not in d4['why'] and '共 3 份 ? 頁。' in d4['why'], d4['why'][:120])
    ck('searched.pid 的文字不含寫死的頁數（換一組數字就跟著變）', '807' not in B.pid_doc(dict(full, pages_ocr=11, pages_sheet=11))['why'])

    # ---------------------------------------------------------------- rebuild.py：P&ID 位置「默默變少」要大聲講（只讀 cardwork/pid.json，不解析 pid_index 的輸出）
    import rebuild as RB
    tmp = tempfile.mkdtemp(prefix='pidtest_')
    keep_path, keep_loud = RB.paths.PID_JSON, list(RB.LOUD)
    try:
        RB.paths.PID_JSON = os.path.join(tmp, 'pid.json')

        def put(by, om=None):
            json.dump({'sheets': {'S1': {'file': 'HT0-1-TDM01-D1205-0.pdf'}, 'S2': {'file': 'HT0-1-KND01-D0027-4.pdf'}}, 'by_tag': by,
                       'stats': {'ocr_map': dict({'present': True, 'pages': 807, 'stale': 0, 'rot_conflict': 0, 'size_mismatch': 0}, **(om or {}))}},
                      open(RB.paths.PID_JSON, 'w', encoding='utf-8'), ensure_ascii=False)

        def loud(before):
            del RB.LOUD[:]
            out = _io.StringIO()
            with contextlib.redirect_stdout(out):
                RB.pid_loud(before)
            return out.getvalue(), list(RB.LOUD)
        before_by = {'A1': [{'how': 'ocr', 'sheet': 'S1'}], 'A2': [{'how': 'ocr', 'sheet': 'S2'}, {'how': 'text', 'sheet': 'S1'}], 'T1': [{'how': 'text', 'sheet': 'S1'}, {'how': 'ocr', 'sheet': 'S2'}]}
        put(before_by)
        prev = RB.pid_ocr_located()
        ck('rebuild：重跑之前「① 靠 OCR 定位」的位號與圖檔名（文字層在前的不算）', prev == {'A1': 'HT0-1-TDM01-D1205-0.pdf', 'A2': 'HT0-1-KND01-D0027-4.pdf'}, prev)
        o, l = loud(prev)
        ck('rebuild：對照表沒有過期、位號一支都沒少 → 不出聲', o == '' and l == [], (o, l))
        put({'A2': before_by['A2'], 'T1': before_by['T1']}, {'stale': 3, 'size_mismatch': 1})
        o, l = loud(prev)
        ck('rebuild：OCR 對照表有過期／尺寸不符的頁 → 一段「!! ====」框起來的訊息，寫出各有幾頁與補救的指令',
           o.count('!! ' + '=' * 20) == 2 and '過期' in o and '3 頁' in o and '尺寸與轉正角不符 1 頁' in o and 'pid_ocr.py --distill' in o and len(l) == 2, o)
        ck('rebuild：上一次靠 OCR 定位、這次整支不見的位號點名，並說原本畫在哪一份圖', '有 1 支這次沒有圖面位置了：A1' in o and 'HT0-1-TDM01-D1205-0.pdf' in o and 'A2' not in o.split('沒有圖面位置了')[1], o)
        o2, l2 = loud(None)
        ck('rebuild --skip-pid（沒有重跑，before=None）：照樣檢查沿用的那份 pid.json 的對照表統計，但不比位號', '過期' in o2 and '沒有圖面位置了' not in o2 and len(l2) == 1, o2)
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            RB.loud_print(RB.LOUD, again=True)
        ck('rebuild：結尾再印一次（標明是再說一次）', '（再說一次）' in out.getvalue() and '過期' in out.getvalue(), out.getvalue())
        os.remove(RB.paths.PID_JSON)
        o3, l3 = loud(prev)
        open(RB.paths.PID_JSON, 'w').write('{not json')
        o4, l4 = loud(prev)
        ck('rebuild：pid.json 不存在或讀不了 → 不出聲也不炸（示警不可以讓重建失敗）', o3 == '' and o4 == '' and RB.pid_ocr_located() == {}, (o3, o4))
    finally:
        RB.paths.PID_JSON = keep_path
        RB.LOUD[:] = keep_loud
        shutil.rmtree(tmp, ignore_errors=True)
    return ck.fails


def _groups(B, ents):
    """與 pid_rows 相同的分組（每張圖紙一組，組內照 pid_marks 的順序）→ 每組的命中清單"""
    order, groups = [], {}
    for e in ents:
        if e['sheet'] not in groups:
            groups[e['sheet']] = []
            order.append(e['sheet'])
        groups[e['sheet']].append(e)
    return [B.pid_marks(groups[s])[0] for s in order]


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    fails = run(None)
    print('\n%s（%d 失敗）' % ('ALL OK' if not fails else 'FAILED', len(fails)))
    for f in fails:
        print('  FAIL', f)
    sys.exit(1 if fails else 0)
