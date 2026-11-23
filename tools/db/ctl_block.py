# -*- coding: utf-8 -*-
"""v27：GE 編號卡的「Mark VIe 控制方塊」——設備物件方塊（電磁閥 S_O_V_V3、馬達 STARTER_V3、調節 PID_MA_ENH_V2）的腳位與接線。

對照表的強連結訊號（ge_tags.json 的 logic；名稱相同、KKS 別名…）若正好是某個設備物件方塊的「裝置名稱」輸出腳（腳位名＝方塊名，
例 G11 GasFuelSkid/ACTUATOR_20VSFG2/20VSFG2 的 20VSFG2 腳），就把那顆方塊有接線的腳（V 變數、L 方塊連線、E 列舉、N 常數；
A＝方塊自己宣告、沒有接東西的不列）整理成一張卡：腳位意思取自 GE DCS Block Library（GEI-100679AB）各方塊的腳位表，
變數照 signal-atlas 控制器索引的宣告（說明、常數值與單位）。接到變數的腳往外追：只跟著單純搬移的 MOVE（ENABLE 為常數 True）
走到 I/O 點（板、位置、點名、DeviceTag、螺絲）或 EGD（另一台控制器送來），遇到其他邏輯方塊就停，只寫寫入者方塊與 file:line
（邏輯本身到 signal-atlas 看）。每台機組用自己控制器的方塊（G12 不借 G11 的）。

輸出（build 的回傳）：
  cards＝{'G11.20VSFG2': 卡}；卡＝{c 控制器, u 機組, n 裝置名, typ 方塊種類, tl 中文名, d 說明, p 方塊路徑, at file:line 或列印圖頁,
         hmi 面板物件, lib 說明書頁, i 輸入腳 [[腳, 中文, 種類, 值, 說明, 追到哪]…], o 輸出腳（同格式）}
  per＝{條目序號: [[卡鍵, 本條目是不是這顆設備本體 0/1]…]}
  own＝{條目序號: [[裝置名, 方塊種類]…]}（本條目是裝置本體的：查詢卡打裝置名時排第一）
  devio＝{(機組, 去分隔符的 DeviceTag): [I/O 組態點的文字…]}（接線路徑只畫到非 Mark VIe 端子板時補一句組態掛在哪）
追到哪＝[[變數, 說明]…中間的 MOVE 搬移]＋終點：{'io': 文字, 'dt': DeviceTag} | {'egd': 來源控制器.變數} | {'w': 方塊種類, 'wp': 路徑, 'at': file:line}
       | {'r': 讀取者個數, 'scr': 畫面張數, 'pub': 有送 EGD}（輸出腳）| {'n': 0}（沒有寫入者）。I/O 點只在方向相符時停（輸入腳 I、輸出腳 O；
       '?' 多半是模組內部點，照常往寫入者追）。
  boards＝{機組: {'pos': {(櫃, 板位)}, 'names': {板名}}}（接線路徑那一列說盤端子板在不在 I/O 組態裡）"""
import os
import re
import sqlite3

DEVICE_TYPES = {'S_O_V_V3': '電磁閥控制方塊', 'STARTER_V3': '馬達啟停控制方塊', 'PID_MA_ENH_V2': '調節控制方塊（PID 手自動站）'}
LIB_DOC = 'HT0-1-IAI01-S0010-0 DCS Block Library（GE GEI-100679AB）'
LIB_PAGES = {'S_O_V_V3': 'PDF p.618～619（印刷頁 617～618）腳位表；p.612～617 動作說明',
             'STARTER_V3': 'PDF p.679～681（印刷頁 678～680）腳位表',
             'PID_MA_ENH_V2': 'PDF p.492～496（印刷頁 491～495）腳位表'}
# 腳位中文：照說明書腳位表的 Description／Function 欄（只列這幾種方塊在本站實際有接線的腳；沒有列的照原名顯示）
GLOSS = {
    'S_O_V_V3': {
        'AU_SEL': '選自動（脈衝）', 'AU_OP': '自動開命令', 'AU_CL': '自動關命令', 'AU_PMT': '自動許可', 'OP_PMT': '開閥許可', 'CL_PMT': '關閥許可',
        'RDY_SV': '電磁閥迴路可操作（I/O 監視）', 'OP_OVR': '超越開', 'CL_OVR': '超越關', 'MN_REJ': '退手動', 'RDY_CL': '關命令迴路可操作',
        'RDY_OP': '開命令迴路可操作', 'CL_INP': '關到位回授', 'OP_INP': '開到位回授', 'CL_FRC': '強制關', 'OP_FRC': '強制開', 'FAULT_RESET': '故障復歸',
        'CTL': '控制字（操作畫面用）', 'FL_OP_T': '開閥失敗時限', 'FL_CL_T': '關閥失敗時限', 'PWR_FL_TMR': '失電退手動時限',
        'IO_MON': 'I/O 監視選項（電壓／保險絲）', 'IO_OPT': '閥的型式（FS_OP 失效開／FS_CL 失效關／DUAL 雙動）', 'MODE_OPT': '可用的模式',
        'DIS_REJ_FL_P': '故障時不退手動',
        'SV_ORD': '電磁閥命令（激磁）', 'OP_ORD': '開命令', 'CL_ORD': '關命令', 'AUTO': '自動模式中', 'CLOSED': '已關', 'OPEN': '已開', 'LOCK': '鎖定中',
        'PMT_AU': '自動許可', 'PMT_CL': '關許可', 'PMT_OP': '開許可', 'FAULT': '故障中', 'MODE': '目前狀態', 'OVR_CL': '超越關中', 'OVR_OP': '超越開中',
        'FRC_CL': '強制關中', 'FRC_OP': '強制開中', 'SV_FLR': '電磁閥迴路失效', 'CL_FLR': '關迴路失效', 'OP_FLR': '開迴路失效',
        'AU_REQ': '自動要求（手動中、自動邏輯要它動）', 'CONGR_A': '位置不一致警報（回授與命令不符）', 'FL_CL_A': '關閥失敗警報',
        'FL_OP_A': '開閥失敗警報', 'MN_REJ_A': '退手動警報', 'TRIPPED': '閥跳脫（沒有命令卻失激）'},
    'STARTER_V3': {
        'AU_SEL': '選自動（脈衝）', 'AU_STR': '自動啟動命令', 'AU_STP': '自動停止命令', 'AU_PMT': '自動許可', 'STR_PMT': '啟動許可', 'STP_PMT': '停止許可',
        'AVAIL': '馬達可用（I/O）', 'CP_OK': '控制電源正常（I/O）', 'RDY_STR': '啟動迴路可操作', 'RDY_STP': '停止迴路可操作', 'RCKD_IN': '斷路器已插入（I/O）',
        'REMOTE': '在遠端（I/O）', 'TRP_OVR': '跳脫超越（外部邏輯跳馬達）', 'PR_TRP': '保護跳脫（I/O）', 'MN_REJ': '退手動', 'TK': '追蹤',
        'LDLG_ORDER': '主備順序（只供畫面顯示）', 'ON_INP': '運轉回授', 'OFF_INP': '停止回授', 'OFF_FRC': '強制停', 'ON_FRC': '強制開', 'FAULT_RESET': '故障復歸',
        'CTL': '控制字（操作畫面用）', 'FL_ST_T': '啟動失敗時限', 'FL_SP_T': '停止失敗時限', 'PWR_FL_TMR': '失電退手動時限', 'IO_MON': 'I/O 監視選項',
        'IO_OPT': '馬達 I/O 選項', 'MODE_OPT': '可用的模式',
        'ON_ORD': '啟動命令', 'OFF_ORD': '停止命令', 'ON': '運轉中', 'OFF': '停止中', 'AUTO': '自動模式中', 'FAULT': '故障中', 'FL_ST_A': '啟動失敗警報',
        'FL_SP_A': '停止失敗警報', 'MOM_OUT_P': '脈衝輸出屬性', 'TRIPPED': '跳脫', 'MN_REJ_A': '退手動警報', 'CONGR_A': '狀態不一致警報'},
    'PID_MA_ENH_V2': {
        'BLOCK_OPT': '方塊選項', 'RSP': '遠端設定值', 'MODE_OPT': '可用的模式', 'CTRL_ACT': '控制作用（正／反）', 'CV_L': 'CV pop 位準', 'CV_R': 'CV pop 復位',
        'CV_MN': 'CV pop 最低位準', 'SH': '設定值上限', 'SL': '設定值下限', 'PV': '製程變數（量測值）', 'SF': 'PID 比例因子', 'POS_CV': '開度回授',
        'AU_SEL': '選自動', 'IG': '積分增益', 'PG': '比例增益', 'DG': '微分增益', 'L': '輸出下限', 'H': '輸出上限', 'TV': '追蹤值', 'CVI': '控制變數輸入',
        'CMD_FRC': '強制命令', 'FV': '強制值', 'CMD_TK': '追蹤命令', 'CMD_OVR': '超越命令', 'OV': '超越值', 'OVR_CTRL': '超越選擇狀態',
        'POS_DH_T': '開度偏差高延時', 'POS_DH_SP': '開度偏差高設定', 'BKCAL_IN_CV': 'CV 回算追蹤值', 'SR': '設定值變化率', 'MR': '手動調整率',
        'PV_SP_LIM_TRK': '在限位追蹤到 PV 越過 SP', 'RSP_SEL': '選遠端設定值', 'PR_DEC_RT': '優先減的速率', 'PR_INC_RT': '優先增的速率',
        'PR_DEC': '優先減', 'PR_INC': '優先增', 'INH_INC': '禁止增', 'INH_DEC': '禁止減', 'MOD_PMT': '調節許可', 'CASC_IN': '串級輸入狀態',
        'IG_CDB': 'IG 無擾切換死區', 'PG_CDB': 'PG 無擾切換死區', 'IG_C': 'IG 無擾切換', 'PG_C': 'PG 無擾切換', 'CV_X': '輸出特性曲線 X',
        'CV_Y': '輸出特性曲線 Y', 'SV_X': '分程特性曲線 X', 'SV_Y': '分程特性曲線 Y', 'BQ_MAN': '訊號品質壞時退手動（True）／追蹤（False）',
        'FF': '前饋值', 'SP_TRACK': '設定值追蹤', 'INH_PDG': '設定值變動時抑制比例與微分', 'EV': '外部重置值', 'ER': '外部重置啟用', 'MN_REJ': '退手動',
        'ERR_C': '誤差死區啟用', 'ERR_CDB': '誤差死區', 'PROC_LIM_HIGH': '製程相依上限', 'SC': '設定值', 'CTL': '控制字（操作畫面用）',
        'CVO': '控制輸出', 'CV': '特性化後的輸出', 'POS_CV_DH': '開度偏差高警報', 'CASC_OUT': '串級輸出狀態', 'US': '在上限', 'LS': '在下限',
        'AUTO': '自動模式中', 'MN_REJ_A': '退手動警報', 'RS': '遠端設定模式', 'SP': '設定值'},
}
CTRL_UNIT = {'G11': 'G11', 'G11S': 'G11', 'G12': 'G12', 'G12S': 'G12', 'S1': 'S10', 'S1S': 'S10', 'SAMP1': 'S10'}
MAX_HOPS = 4


def cmp_(s):
    return re.sub(r'[^A-Z0-9]', '', str(s or '').upper())


class _Ix:
    def __init__(self, path):
        self.c = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
        self.c.row_factory = sqlite3.Row
        self.built = (self.c.execute("select value from meta where key='built_at'").fetchone() or [''])[0]
        self.fmt = {r['name']: r['units'] for r in self.c.execute('select name, units from format_spec')}

    def var(self, ctrl, name):
        return self.c.execute('select * from variable where ctrl=? and name=? collate nocase and sub_of is null', (ctrl, name)).fetchone()

    def var_id(self, vid):
        return self.c.execute('select * from variable where id=?', (vid,)).fetchone()

    def block(self, bid):
        return self.c.execute('select b.*, pr.file_path, pr.encrypted from block b join program pr on pr.id=b.program_id where b.id=?', (bid,)).fetchone()

    def pins(self, bid):
        return self.c.execute('select * from pin where block_id=? order by id', (bid,)).fetchall()

    def writers(self, vid):
        return self.c.execute("select * from pin where var_id=? and direction='O'", (vid,)).fetchall()

    def readers(self, vid):
        return self.c.execute("select * from pin where var_id=? and direction='I'", (vid,)).fetchall()

    def io(self, vid):
        return self.c.execute("""select p.*, m.name mname, m.cabinet, b.name bname, b.position_r from io_point p
                                 left join io_module m on m.id=p.module_id left join io_board b on b.id=p.board_id where p.var_id=?""", (vid,)).fetchall()

    def screws(self, pid):
        return self.c.execute('select name, number from io_screw where point_id=? order by number', (pid,)).fetchall()

    def egd_src(self, vid):
        return self.c.execute('select producer_ctrl, var_name from egd_consumed where local_var_id=?', (vid,)).fetchone()

    def block_at(self, b):
        """方塊的位置：XML 行號（有 file_path、未加密）或列印圖頁（加密程式的方塊取自列印圖）。只給檔名，不給本機路徑。"""
        if b['line_no'] and b['file_path'] and not b['encrypted']:
            return '%s:%d' % (b['file_path'], b['line_no'])
        bc = self.c.execute('select pdf, page, cell from block_cite where block_id=?', (b['id'],)).fetchone()
        if bc:
            return '%s p.%s%s' % (os.path.basename(bc['pdf'].replace('\\', '/')), bc['page'], (' ' + bc['cell']) if bc['cell'] else '')
        return ''


def _unit(ix, v):
    u = v['units'] or (ix.fmt.get(v['format_spec']) if v['format_spec'] else None)
    return u or ''


def _io_text(ix, p):
    scr = '、'.join('%s＝%s' % (s['number'], s['name']) for s in ix.screws(p['id']))
    where = ' '.join(x for x in (p['bname'], p['position_r']) if x)
    return '%s %s%s %s%s' % (p['ctrl'], p['mname'] or '', ('（%s%s）' % (where, ('，櫃 %s' % p['cabinet']) if p['cabinet'] else '')) if where else '',
                             p['name'] or '', ('；螺絲 %s' % scr) if scr else '')


def _var_cell(ix, v):
    """變數 → (值文字, 說明)。常數帶值與單位。"""
    desc = (v['description'] or '').strip()
    if v['control_constant']:
        val = '%s%s' % (v['value'], (' ' + _unit(ix, v)) if _unit(ix, v) else '')
        return '%s ＝ %s' % (v['name'], val), desc
    return v['name'], desc


def _end_writer(ix, ctrl, b):
    return {'w': b['block_type'] or '', 'wp': b['path'], 'at': ix.block_at(b)}


def _up(ix, v):
    """輸入腳的變數往上游追：MOVE 搬移照走，到 I/O 點／EGD／別的邏輯方塊停。"""
    hops = []
    for _ in range(MAX_HOPS):
        ios = [p for p in ix.io(v['id']) if p['direction'] == 'I']   # 只在實體輸入點停（'?' 多半是模組內部點，例 PTUR 的 Synch_Reset）
        if ios:
            p = ios[0]
            return hops, {'io': _io_text(ix, p), 'dt': p['device_tag'] or ''}
        eg = ix.egd_src(v['id'])
        if eg:
            src = '%s.%s' % (eg['producer_ctrl'], eg['var_name'])
            if hops and hops[-1][0] == src:   # 本地的 EGD 變數名就是「來源控制器.變數」：不重複列
                hops.pop()
            return hops, {'egd': src}
        ws = ix.writers(v['id'])
        if len(ws) != 1:
            return hops, ({'n': 0} if not ws else {'w': '', 'wp': '（%d 個寫入者）' % len(ws), 'at': ''})
        b = ix.block(ws[0]['block_id'])
        bt = b['block_type'] or ''
        pins = {p['name']: p for p in ix.pins(b['id'])}
        nxt, mark = None, None
        if bt == 'MOVE' and ws[0]['name'] == 'DEST':
            src, en = pins.get('SRC'), pins.get('ENABLE')
            if src is not None and src['conn_kind'] == 'V' and src['var_id'] and (en is None or (en['connection'] or '').upper() in ('N:TRUE', '')):
                nxt = src['var_id']
        elif bt == 'LOGIC_BUILDER' and ws[0]['name'] == 'OUT' and re.sub(r'\s', '', (pins.get('EQN') or {'connection': ''})['connection'] or '').upper() == 'N:(IN1)':
            src = pins.get('IN1')   # 許可方塊（OP_PMT／CL_PMT…）只有一項 IN1：照走
            if src is not None and src['conn_kind'] == 'V' and src['var_id']:
                nxt, mark = src['var_id'], ['（許可方塊 %s：方程式只有 IN1）' % b['name'], '']
        elif bt == 'NOT' and ws[0]['name'] == 'NOT_A':
            src = pins.get('A')
            if src is not None and src['conn_kind'] == 'V' and src['var_id']:
                nxt, mark = src['var_id'], ['（反相 NOT）', '']
        if nxt:
            nv = ix.var_id(nxt)
            if nv is not None:
                if mark:
                    hops.append(mark)
                hops.append(list(_var_cell(ix, nv)))
                v = nv
                continue
        return hops, _end_writer(ix, v['ctrl'], b)
    return hops, {'w': '', 'wp': '（追到第 %d 層停）' % MAX_HOPS, 'at': ''}


def _down(ix, v):
    """輸出腳的變數往下游追：唯一讀取者是 MOVE 的 SRC 就照走，到 I/O 點停；否則寫讀取者個數。"""
    hops = []
    for _ in range(MAX_HOPS):
        ios = [p for p in ix.io(v['id']) if p['direction'] == 'O']   # 只在實體輸出點停
        if ios:
            p = ios[0]
            return hops, {'io': _io_text(ix, p), 'dt': p['device_tag'] or ''}
        rs = ix.readers(v['id'])
        if len(rs) == 1:
            b = ix.block(rs[0]['block_id'])
            if (b['block_type'] or '') == 'MOVE' and rs[0]['name'] == 'SRC':
                dst = next((p for p in ix.pins(b['id']) if p['name'] == 'DEST'), None)
                if dst is not None and dst['var_id']:
                    nv = ix.var_id(dst['var_id'])
                    if nv is not None:
                        hops.append(list(_var_cell(ix, nv)))
                        v = nv
                        continue
        nh = ix.c.execute('select count(distinct screen) from hmi_point where var_id=?', (v['id'],)).fetchone()[0]
        ne = ix.c.execute('select count(*) from egd_produced where var_id=?', (v['id'],)).fetchone()[0]
        return hops, {'r': len(rs), 'scr': nh, 'pub': 1 if ne else 0}   # 讀取者個數、畫面張數、有沒有送 EGD
    return hops, {'r': -1}


def _pin_row(ix, ctrl, b, p, typ):
    name, kind = p['name'], p['conn_kind']
    gl = GLOSS.get(typ, {}).get(name, '')
    conn = p['connection'] or ''
    if kind == 'V' and p['var_id']:
        v = ix.var_id(p['var_id'])
        if v is None:
            return [name, gl, 'v', conn, '', None]
        val, desc = _var_cell(ix, v)
        if v['control_constant']:
            return [name, gl, 'k', val, desc, None]
        hops, end = (_up if p['direction'] == 'I' else _down)(ix, v)
        return [name, gl, 'v', val, desc, hops + [end]]
    if kind == 'L':
        tb = ix.block(p['tgt_block_id']) if p['tgt_block_id'] else None
        txt = conn[2:] if conn.startswith('L:') else conn
        desc = ''
        if tb is not None:
            desc = '%s 方塊的輸出' % (tb['block_type'] or '')
            if (tb['block_type'] or '') == 'NOT':
                a = next((q for q in ix.pins(tb['id']) if q['name'] == 'A' and q['var_id']), None)
                av = ix.var_id(a['var_id']) if a else None
                if av is not None:
                    desc = '反相（NOT）%s' % av['name']
        return [name, gl, 'l', txt, desc, None]
    if kind in ('E', 'N'):
        return [name, gl, 'e' if kind == 'E' else 'n', re.sub(r'^[EN]:', '', conn), '', None]
    return None


def device_block(ix, ctrl, sig):
    """控制器.訊號 是設備物件方塊的裝置名稱輸出腳 → 方塊列；不是回 None。"""
    v = ix.var(ctrl, sig)
    if v is None:
        return None
    for w in ix.writers(v['id']):
        b = ix.block(w['block_id'])
        if b is not None and (b['block_type'] or '') in DEVICE_TYPES and cmp_(w['name']) == cmp_(b['name']):
            return b
    return None


def card(ix, ctrl, b):
    typ = b['block_type']
    ins, outs = [], []
    for p in ix.pins(b['id']):
        if p['direction'] not in ('I', 'O') or cmp_(p['name']) == cmp_(b['name']):
            continue
        r = _pin_row(ix, ctrl, b, p, typ)
        if r is None:
            continue
        (ins if p['direction'] == 'I' else outs).append(r)
    prog, _s, rest = b['path'].partition('/')
    return {'c': ctrl, 'u': CTRL_UNIT.get(ctrl, ''), 'n': b['name'], 'typ': typ, 'tl': DEVICE_TYPES[typ], 'd': (b['description'] or '').strip(),
            'p': b['path'], 'at': ix.block_at(b), 'hmi': b['hmi_linked_object'] or '', 'lib': '%s %s' % (LIB_DOC, LIB_PAGES.get(typ, '')),
            'i': ins, 'o': outs}


def _body_is(e, body, kks_of):
    """條目的現行 KKS 有一個正好是 body、而且沒有子件尾碼（-MB01 電磁閥、-BG01 極限開關…）＝這個條目就是設備本體。"""
    for k in e.get('kks') or []:
        p = kks_of(k)
        if p and p[1] == body and not p[2]:
            return True
    return False


def build(ge, index_path, units_of, logic_of, kks_of):
    """ge：build_card_aux.load_ge 的回傳；units_of(e)→本站機組；logic_of(e, 機組)→本台控制器的訊號；kks_of(k)→(前綴, 本體, 子件尾碼)。
    回傳 dict(cards, per, own, devio, built, stats)；索引不在回 None。"""
    if not index_path or not os.path.exists(index_path):
        return None
    ix = _Ix(index_path)
    cards, per, own = {}, {}, {}
    for e in ge['entries']:
        how = e.get('logic_how') or {}
        # 本條目是不是設備本體：以訊號名判（G12 的變數沒有 KKS 別名，GE 文件只印 G11 的——看任何一台的同名變數）
        body_of = {}
        for fn, why in how.items():
            ctrl, _d, sig = fn.partition('.')
            v = ix.var(ctrl, sig)
            al = kks_of((v['alias'] or '').split('.')[0]) if v is not None and v['alias'] else None
            if why == '名稱相同' or (al and _body_is(e, al[1], kks_of)):
                body_of[sig.upper()] = 1
        rows = []
        for un in units_of(e):
            cand = list(logic_of(e, un))
            # 對照表的訊號在姊妹機控制器（只列 G11 的 KKS 別名）：本台有同名變數就用本台自己的方塊
            mine = [c for c, u in CTRL_UNIT.items() if u == un]
            for fn in e.get('logic') or []:
                c0, _d, sig = fn.partition('.')
                if CTRL_UNIT.get(c0) == un:
                    continue
                tc = next((c for c in mine if c[0] == c0[0] and c.endswith('S') == c0.endswith('S') and len(c) == len(c0)), None)
                if tc and ix.var(tc, sig) is not None and '%s.%s' % (tc, sig) not in cand:
                    cand.append('%s.%s' % (tc, sig))
            for fn in cand:
                ctrl, _d, sig = fn.partition('.')
                key = '%s.%s' % (ctrl, sig)
                if key not in cards:
                    b = device_block(ix, ctrl, sig)
                    cards[key] = card(ix, ctrl, b) if b is not None else None
                if cards[key] is None:
                    continue
                if not any(r[0] == key for r in rows):
                    rows.append([key, body_of.get(sig.upper(), 0)])
        if rows:
            per[e['_i']] = rows
            o = []
            for key, body in rows:
                if body and not any(x[0] == cards[key]['n'] for x in o):
                    o.append([cards[key]['n'], cards[key]['typ']])
            if o:
                own[e['_i']] = o
    cards = {k: v for k, v in cards.items() if v is not None and any(k == r[0] for rows in per.values() for r in rows)}
    boards = {}   # 機組 → {'pos': {(櫃, 板位)}, 'names': {板名}}：接線圖的盤端子板在不在 I/O 組態裡
    for r in ix.c.execute('select m.ctrl, m.cabinet, b.name, b.position_r from io_board b join io_module m on m.id=b.module_id'):
        un = CTRL_UNIT.get(r['ctrl'])
        if not un:
            continue
        d = boards.setdefault(un, {'pos': set(), 'names': set()})
        pos = r['position_r'] or ''
        cab = r['cabinet'] or ''
        if '-' in pos:   # 安全控制器的板位寫成 'CA004-1M3A'（櫃欄是控制器名）
            cab, pos = pos.split('-', 1)
        if pos:
            d['pos'].add((cab, pos))
        if r['name']:
            d['names'].add(r['name'].upper())
    devio = {}
    for r in ix.c.execute("""select p.*, m.name mname, m.cabinet, b.name bname, b.position_r, v.name vname from io_point p
                             left join io_module m on m.id=p.module_id left join io_board b on b.id=p.board_id
                             left join variable v on v.id=p.var_id where p.device_tag is not null and p.device_tag<>''"""):
        un = CTRL_UNIT.get(r['ctrl'])
        if not un or not r['vname']:   # 沒有變數的點（安全控制器板在主控制器那邊的影子）不列
            continue
        t = _io_text(ix, r) + (' → %s' % r['vname'] if r['vname'] else '')
        lst = devio.setdefault((un, cmp_(r['device_tag'])), [])
        if t not in lst:
            lst.append(t)
    stats = {'cards': len(cards), 'entries': len(per), 'owners': len(own),
             'by_type': {t: sum(1 for c in cards.values() if c['typ'] == t) for t in DEVICE_TYPES}}
    return {'cards': cards, 'per': per, 'own': own, 'devio': devio, 'boards': boards, 'built': ix.built, 'stats': stats}
