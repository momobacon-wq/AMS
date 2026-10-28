"""接線路徑的訊號型式與迴路供電（v16，wire_ge.py 用）。

規則與本廠盤內配電的對照放在 ge_tags_dir 的 wire_curated.json（signal.rules／signal.meta，人工查證、每條附手冊或圖面出處，不進 repo）；
這裡只有套規則的引擎：每條路徑落在 Mark VIe 的每一個點 → 這個點接到的螺絲名（'P24V3'、'20mA3'）、控制器組態的 signal_type／input_type／
params_json → 第一條符合的規則 → {訊號型式, 迴路供電, 等級, 旗標, 衝突, 出處}。

判定以接線為準（接了 P24V＋20mA＝兩線式），ToolboxST 的跳線欄位（TBAI JPnB、WROB JPn、TCDM JPxx、TVBA JPxA）只當「組態寫法」另列衝突，
不替任何一方選邊：同一種設計 G11 記 Dry、G12 記 Excited，跳線實際插哪裡要現場看。"""
import json
import re
from collections import OrderedDict

VIBKIND = {'VibProx-KPH1': '徑向振動', 'VibProx': '徑向振動', 'PosProx': '軸位移／位置', 'KeyPhasor': '鍵相（Keyphasor）'}
GT_CTRLS = ('G11', 'G12', 'G11S', 'G12S')
PARTIAL_RULES = ('TC_PARTIAL', 'TDBT_DI_RET', 'TDBT_DI_POS', 'AI_BORROW_PWR')   # 加上 *_ONLY：只對上一芯或借用電源端子的點，路徑上排在主要訊號後面


class _Keep(dict):
    def __missing__(self, k):
        return '{' + k + '}'


def fmt(s, f):
    return (s or '').format_map(_Keep(f))


def pin_pat(pins):
    """接到的螺絲名 → 規則用的型樣（數字換成 #、排序後以 + 串接）：['P24V3', '20mA3'] → '#mA#+P#V#'。"""
    return '+'.join(sorted(re.sub(r'\d+', '#', p) for p in pins))


def first_int(s):
    m = re.search(r'\d+', s or '')
    return int(m.group()) if m else None


def point_cfg(con, ctrl, mod, pt, posr):
    """控制器組態裡這個點的 (signal_type, input_type, params, 板名, DeviceTag)；先比板位，對不到再只比模組＋點名。"""
    q = ('select p.signal_type, p.input_type, p.params_json, b.name, p.device_tag from io_point p join io_board b on p.board_id = b.id '
         'join io_module m on p.module_id = m.id where p.ctrl = ? and m.name = ? and p.name = ?')
    row = con.execute(q + ' and b.position_r = ?', (ctrl, mod, pt, posr)).fetchone() or con.execute(q, (ctrl, mod, pt)).fetchone()
    if not row:
        return None
    return row[0], row[1], json.loads(row[2]) if row[2] else {}, row[3], row[4]


def contexts(r, con, pathkey):
    """一條路徑 → 每個 Mark VIe 點一個 context（FF 段幹線是一個 context）。r['io'] 的一列＝[控制器, 模組, 板位, 板名, 點, 變數, DeviceTag, 關係]。"""
    if r.get('mode') == 'ff':
        m = re.match(r'(FFPC\d+)\s+S(\d+)', (r.get('wire') or {}).get('panel_tb', ''))
        yield {'mode': 'ff', 'board': '(FF)', 'pt': '', 'pins': [], 'params': {}, 'signal_type': 'FF', 'input_type': None, 'ctrl': r.get('unit'),
               'posr': '', 'ffpc': m.group(1)[4:] if m else '?', 'seg': m.group(2) if m else '?', 'pathkey': pathkey, 'tag': r.get('tag', ''),
               'drawn': (r.get('wire') or {}).get('drawn', '')}
        return
    io = r.get('io') or []
    groups = OrderedDict()
    for c in r.get('cond') or []:
        if c.get('pt'):
            groups.setdefault((c.get('pos', ''), c['pt'], c.get('board', '')), set()).add(c.get('pin', ''))
    for (pos, pt, board), pins in groups.items():
        posr = pos.split('-')[-1] if pos else ''
        cands = [x for x in io if x[4] == pt and (not posr or x[2] == posr)] or [x for x in io if x[4] == pt]
        if not cands:
            continue
        ctrl, mod, posr2 = cands[0][0], cands[0][1], cands[0][2]
        cfg = point_cfg(con, ctrl, mod, pt, posr2)
        if not cfg:
            continue
        yield {'mode': r.get('mode'), 'board': board or cfg[3], 'pt': pt, 'pins': sorted(pins), 'params': cfg[2], 'signal_type': cfg[0],
               'input_type': cfg[1], 'ctrl': ctrl, 'mod': mod, 'posr': posr2, 'dtag': cfg[4], 'pathkey': pathkey, 'tag': r.get('tag', ''),
               'drawn': (r.get('wire') or {}).get('drawn', ''), 'jbdesc': '%s %s' % ((r.get('wire') or {}).get('jb', ''), (r.get('wire') or {}).get('jb_desc', ''))}


def pkey(x):
    return (x['ctrl'], x.get('mod'), x['posr'], x['pt'])


def _lab(pk):
    """內部路徑鍵 'ST|RP-1#0' → 卡上看得懂的 'RP-1'（路徑序號是建檔順序，卡上的「第 n 條」不一定同號）。"""
    return pk.rsplit('#', 1)[0].split('|', 1)[-1]


def matches(rule, x):
    w = rule['when']
    if 'mode' in w:
        return x['mode'] in w['mode']
    if x['mode'] == 'ff':
        return rule['id'] == 'FALLBACK'
    if '*' not in rule['board'] and x['board'] not in rule['board']:
        return False
    if 'signal_type' in w and x['signal_type'] not in w['signal_type']:
        return False
    if 'input_type' in w and (x['input_type'] or 'None') not in w['input_type']:
        return False
    if 'pins' in w and pin_pat(x['pins']) not in w['pins']:
        return False
    if any(not any(re.match(rx, p) for p in x['pins']) for rx in w.get('pins_re', [])):
        return False
    n = first_int(x['pt'])
    if 'pt_num' in w and (n is None or not (w['pt_num'][0] <= n <= w['pt_num'][1])):
        return False
    if any(x['params'].get(k) != v for k, v in w.get('params_eq', {}).items()):
        return False
    if 'vib_type' in w and not any(v in w['vib_type'] for k, v in x['params'].items() if k.startswith('VIB_Type')):
        return False
    return True


def load_of(x):
    """板供電繼電器（NO＋SOL）接的是什麼：照接線圖的設備描述與 GE 編號判（組態沒有這一欄，所以是推論）→ (訊號欄用語, 供電鏈用語)。"""
    d, tag, jd = (x.get('drawn') or '').upper(), (x.get('tag') or '').upper(), (x.get('jbdesc') or '').upper()
    if re.search(r'SOLENOID|\bSOV\b|\bSOL(?:ENOID)?\s+VALVE', d) or re.match(r'(20|FY-)', tag):
        return '驅動電磁閥', '電磁閥'
    if (re.search(r'MOTOR|PUMP|\bFAN\b|HEATER|\bSTART\b|\bSTOP\b|COMMAND|\bCMD|PERMISSIVE', d) or re.match(r'(88|23|4[A-Z]|71|33)', tag)
            or re.search(r'POWER CENTER|\bMCC\b|\bPC-', jd)):
        return '送啟停命令到對方盤（負載是對方盤的命令迴路）', '對方盤命令迴路'
    return '負載型式見接線圖的設備描述', '負載'


def fields(x, meta, U):
    """規則句子的填空：點號、跳線、熱電偶／RTD 型式、本盤 WROB 供電來源、YSIL 濕潤電壓、同一個點別條路徑接了哪些螺絲。"""
    p = x['params']
    n = first_int(x['pt']) or 0
    f = dict(p)
    f.update({'n': n, 'n2': '%02d' % n, 'nn': '%02d' % n, 'pt': x['pt'], 'board': x['board'], 'signal_type': x['signal_type'],
              'ffpc': x.get('ffpc', ''), 'seg': x.get('seg', ''), 'posr': x.get('posr', ''), 'dtag': x.get('dtag') or x['pt']})
    f['JPB'] = p.get('JP%dB' % n, '?')
    f['hart'] = '（HART 啟用）' if p.get('Hart_Enable') == 'Enable' else ''
    tc = p.get('ThermCplType') or p.get('TC_Type') or ''
    f['tc'] = '%s 型' % tc if tc and tc != 'Unused' else '型式：此板位這個點組態未啟用' if tc == 'Unused' else '型式不明'
    f['rtd'] = p.get('RTDType', '?')
    f['contact'] = 'NC' if any(q.startswith('NC') for q in x['pins']) else 'NO'
    vt = [v for k, v in p.items() if k.startswith('VIB_Type')]
    f['vibkind'] = VIBKIND.get(vt[0], vt[0]) if vt else '?'
    pp = pin_pat(x['pins'])
    f['wiring_hint'] = {'#mA#+P#V#': '兩線式（P24V 供電）', '#mA#+Ret#': '四線式／外部供電'}.get(pp, pp)
    f['jps'] = ','.join('%s=%s' % (k, p[k]) for k in sorted(k for k in p if re.fullmatch(r'JP\d', k))) or '-'
    f['val'] = p.get('JP%dA' % n, '?')
    grp = 'GT' if x.get('ctrl') in GT_CTRLS else 'ST'
    feeds = ((meta.get('constants') or {}).get('wrob_jf1_feed') or {}).get(grp) or {}
    f['wrob_src'] = next((src for src, poss in feeds.items() if f['posr'] in poss), '圖面沒有查到這個位置的 WROB JF1 饋電')
    f['exc_v'] = ((meta.get('constants') or {}).get('ysil_excitation_volt') or {}).get(x.get('ctrl'), '未知（不在組態表）')
    f['ysil_src'] = ((meta.get('constants') or {}).get('ysil_src') or {}).get(grp, '')
    f['jpnote'] = ((meta.get('constants') or {}).get('jpnote') or {}).get(grp, '')
    f['load'], f['loadc'] = load_of(x)
    u = U.get(pkey(x)) if x['mode'] != 'ff' else None
    f['elsewhere'] = sorted(u['pins'] - set(x['pins'])) if u else []
    f['elsewhere_paths'] = sorted({_lab(k) for k, pins in u['by_path'].items() if pins - set(x['pins'])}) if u else []
    n24 = 'N24V%02d' % n
    src = [k for k, pins in (u['by_path'].items() if u else []) if n24 in pins]
    if not src and x.get('pathkey'):
        base = re.sub(r'\s*\(Jumpered\)', '', x['pathkey'].rsplit('#', 1)[0])     # 同一顆探頭接在另一片 TVBA（'RP-1 (Jumpered)' ← 'RP-1'）：那一片的 N24V 供電
        for (c2, m2, pr2, _pt2), u2 in U.items():
            for k2, pins2 in u2['by_path'].items():
                if k2.rsplit('#', 1)[0] == base and any(q.startswith('N24V') for q in pins2) and (m2, pr2) != (x.get('mod'), x['posr']):
                    src.append('%s %s %s 的 %s（%s 那一條）' % (c2, m2, pr2, '+'.join(sorted(q for q in pins2 if q.startswith('N24V'))), _lab(k2)))
        f['n24_src'] = ('另一片 TVBA：' + '、'.join(src)) if src else '另一個來源（第一片 TVBA 或外部監測系統，資料裡沒有）'
    else:
        f['n24_src'] = ('本 TVBA 的 %s（接在 %s 那一條）' % (n24, '、'.join(sorted({_lab(q) for q in src})))) if src else '另一個來源（第一片 TVBA 或外部監測系統，資料裡沒有）'
    for k in ('Output_MA', 'Low_MA', 'High_MA', 'Range', 'InputUse', 'Servo_MA_Out', 'TBmAJmpPos'):
        f.setdefault(k, '?')
    return f


def _mA(v):
    m = re.search(r'\d+', str(v or ''))
    return int(m.group()) if m else None


def conflicts(rule, x, f, meta):
    """規則附的「組態寫法 vs 接線」檢查 → 句子清單（跳線欄位與接線不一致、TSVC 電流設定互相矛盾…）。"""
    out = []
    for cf in rule.get('conflicts', []):
        hit, ff = False, dict(f)
        if cf.get('always'):
            hit = True
        elif cf.get('relay12_jg1_pos'):
            pos = (meta.get('constants') or {}).get('wroB_jg1_powered_positions') or {}
            hit = f['n'] == 12 and x['posr'] in (pos.get('GT' if x['ctrl'] in ('G11', 'G12') else 'ST') or [])
        elif cf.get('tsvc_mismatch'):
            keys = ['JP%d' % k for k in ((1, 3, 5) if f['n'] == 1 else (2, 4, 6))]
            vals = {_mA(x['params'].get('Servo_MA_Out')), _mA(x['params'].get('TBmAJmpPos'))} | {_mA(x['params'].get(k)) for k in keys if k in x['params']}
            vals.discard(None)
            ff['jps'] = ','.join('%s=%s' % (k, x['params'].get(k)) for k in keys if k in x['params']) or '-'
            hit = len(vals) > 1
        elif 'param' in cf:
            v = x['params'].get(fmt(cf['param'], f))
            ff['val'] = v
            hit = (v == cf['value']) if cf['op'] == 'eq' else (v is not None and v != cf['value']) if cf['op'] == 'ne_present' else False
        if hit:
            out.append(fmt(cf['msg'], ff))
    return out


def classify(x, rules, meta, U):
    for rule in rules:
        if matches(rule, x):
            f = fields(x, meta, U)
            cite = []
            for c in rule.get('cite', [])[:2]:
                cite.append('%s p.%s' % (str(c.get('doc', '')).replace('\\', '/').rsplit('/', 1)[-1], c.get('page', '?')))
            notes = [fmt(s, f) for s in rule.get('notes', [])]
            if f['elsewhere']:
                notes.append('這個點另有 %s 接在別條路徑（%s）' % ('+'.join(f['elsewhere']), '、'.join(f['elsewhere_paths'])))
            return {'rule': rule['id'], 'sig': fmt(rule['signal_zh'], f), 'pow': fmt(rule['power_zh'], f), 'g': rule.get('grade', ''),
                    'flag': rule.get('flag', ''), 'cf': conflicts(rule, x, f, meta), 'nt': notes, 'cite': cite}
    return None


def union(paths, con):
    """同一個 Mark VIe 點在所有路徑上接到的螺絲（N24V 由哪一條路徑接、一個點的兩芯分在兩條路徑時用）。"""
    U = {}
    for key, plist in paths.items():
        for i, r in enumerate(plist):
            for x in contexts(r, con, '%s#%d' % (key, i)):
                if x['mode'] == 'ff':
                    continue
                u = U.setdefault(pkey(x), {'pins': set(), 'by_path': {}})
                u['pins'] |= set(x['pins'])
                u['by_path']['%s#%d' % (key, i)] = set(x['pins'])
    return U
