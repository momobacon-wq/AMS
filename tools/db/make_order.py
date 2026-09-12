# -*- coding: utf-8 -*-
"""Build order.json for build_workbook.py from workflow_results.json + curated notes."""
import json, re
r = json.load(open('workflow_results.json', encoding='utf-8'))
c, d = r['critic'], r['domains']

DROP = {('security', '登入與帳號異動事件'),   # = events 登入登出統計 + 使用者帳號變更
        ('security', '資料表清單與領域'),     # keep modules 資料表字典
        ('alerts', '網路通訊與輪詢設定'),     # = devices 網路清單
        ('alerts', '警報類別代碼'),           # in modules 代碼對照表
        ('events', '事件類別碼表')}           # in modules 代碼對照表

import copy
old_order = copy.deepcopy(c['sheet_order'])
order = [o for o in c['sheet_order'] if (o['module_key'], o['sheet_name']) not in DROP]
# fixed numbers: 02 = formula card (built by build_workbook), 03 = 設備總表, 04 = 位號索引; the rest from 05 in critic order
fixed = {('devices', '設備總表'): '03', ('index', '位號索引'): '04'}
order = [o for o in order if (o['module_key'], o['sheet_name']) not in fixed]
i = 5
for o in order:
    o['number'] = f'{i:02d}'; i += 1
order = [{'number': '03', 'module_key': 'devices', 'sheet_name': '設備總表'}, {'number': '04', 'module_key': 'index', 'sheet_name': '位號索引'}] + order
DROP_FINDINGS = ('34 台裝置 IdentStatus=0 (未識別)', '34 台設備 IdentStatus=0（', '345 筆刪除裝置事件涉及 177 台裝置', '前簿 (.ams_merge 文字匯出)',
                 '本廠 AMS 的 Alert Monitor 從未使用', 'Alert Monitor 雖在伺服器啟用', '共用帳號 HMI', 'BlockData 140,790 筆 (40%)', '授權全開',
                 'AMS Device Manager 主程式沒有登出事件', '1,540 個舊位號(ExtBlockTags)仍留在資料庫', '14 台 HART 設備的 AMS 位號是自動時間戳')

SEV_RANK = {'高': 0, '中': 1, '低': 2, '資訊': 3}
def norm(t):
    return re.sub(r'[\s\W_]+', '', t)[:18]
# old critic numbering -> new numbering, for the sheet references inside findings
old2new = {}
for o_old in old_order:
    for o_new in order:
        if o_new['sheet_name'] == o_old['sheet_name'] and o_new['module_key'] == o_old['module_key']:
            old2new[o_old['number'] + '_' + o_old['sheet_name']] = o_new['number'] + '_' + o_new['sheet_name']
def fix_ref(t):
    for a, b in old2new.items():
        t = t.replace(a, b)
    t = t.replace('50_事件類別碼表', '49_代碼對照表').replace('51_警報類別代碼', '49_代碼對照表').replace('45_登入與帳號異動事件', '23_登入登出統計')
    return t
top = [dict(f, sheet=fix_ref(f['sheet'])) for f in c['top_findings']]
seen = {norm(f['text']) for f in top}
rest = []
for k, dom in d.items():
    for f in dom['findings']:
        if norm(f['text']) in seen or f['text'].startswith(DROP_FINDINGS):
            continue
        seen.add(norm(f['text']))
        rest.append({'severity': f['severity'], 'text': f['text'], 'evidence': f['evidence'], 'sheet': f'（{k} 領域）'})
rest.sort(key=lambda f: SEV_RANK.get(f['severity'], 9))
findings = top + rest

open_q = []
for k, dom in d.items():
    for q in dom['open_questions']:
        open_q.append(f'[{k}] {q}')
cross = []
for k, dom in d.items():
    for q in dom['cross_checks']:
        cross.append(f'[{k}] {q}')

cfg = {
    'title': '新複循環廠 AMS Device Manager 資料庫解析',
    'default_query': 'G12HAP70BT001',
    'sheets': order,
    'skip_sheets': [list(x) for x in DROP],
    'header_renames': [
        [r'設備序號 \(Identifier\)', '裝置ID (Identifier)'],
        [r'裝置序號/識別 \(Identifier\)', '裝置ID (Identifier)'],
    ],
    'sources': [
        ['原始檔', '20260912.ams_bckup（365.6 MB；Microsoft SQL Server 2014 原生備份，MTF 格式）'],
        ['資料庫', 'AmsDb（AMS Device Manager V14.1.1；資料庫結構版本 5.1；伺服器 AMS1SVR\\EMERSON2014；定序 SQL_Latin1_General_CP1_CI_AS）'],
        ['還原方式', 'WSL Ubuntu 24.04 內安裝 SQL Server 2025 Express → RESTORE DATABASE（相容層級 120）→ pyodbc 逐表倒出成 SQLite（105 表、1,170,089 列）→ Python/openpyxl 產生本簿'],
        ['備份時間', '檔案時間 2026-09-12 09:29；EventLog 最後一筆事件為判定基準（見 16_事件稽核摘要）'],
        ['與前簿關係', '20260910_AMS解析.xlsx 來自 .ams_merge 文字匯出（13,682 事件、1,928 台）；本簿來自完整資料庫（29,773 事件），涵蓋前簿沒有的：實體網路位置（MUX/通道/COM 埠/FF LD）、登入/帳號/刪除/掃描/同步事件、警報定義、權限、範本參數、SnapOn 檔案資訊、資料表與程式碼字典'],
        ['大表拆分', '列數 ≥ 120,000 的三張表（參數現值 344,943、範本參數現值 306,891、全部警報定義 140,438）放在明細活頁簿 20260912_AMS資料庫解析_明細.xlsx，主簿留存說明頁'],
        ['產生器', 'scratchpad/build/sheets_*.py（8 個領域模組）＋ build_workbook.py；每張表的產表模組名稱見目錄「來源表」與註記'],
        ['解析方法', 'ultracode 多代理：7 個領域代理解讀 → 7 個對抗驗證代理逐表反駁並修正 → 完備性稽核代理檢查涵蓋率/矛盾/CSV 缺陷（未涵蓋的 NetworkHierarchies 1 列已補入跨域對帳表）'],
    ],
    'reading_notes': [
        '時間：資料庫事件時間為 UTC；欄名帶「(台灣)」者已加 8 小時。裝置內部儲存的日期（HART date、FF 日期）時區不明，範本/參數表的「值(日期)」欄一併加了 8 小時，判讀時請留意。',
        '哨兵值：資料庫用 -1/-2 鍵、EventIdDay 25569（1970-01-01）與 49710（2036-02-07，代表「尚未結束」）、OLE 0（1899-12-30）、1900-01-01、0001-01-01 表示「無/未設定/現行」。本簿把這些日期一律留白，鍵值保留原值並在註記說明。',
        '位號：「現行 AMS 位號」= ExtBlockTags 經 BlockAsgms 之現行指派（EventIdDayOut=49710），每台恰一筆；「識別時位號 (Devices.AmsDeviceTag)」是 AMS 識別當下讀到的 HART 短位號，常含殘碼或空白。設備領域各表用清理後位號，其他表用原值；10 台兩者不同，對照見「位號跨表對照」。',
        'Devices.Identifier 是 HART Device ID（= HostPath 中的裝置 UID 末 6 hex），不是銘牌序號；本簿一律稱「裝置ID」。',
        '參數值解碼：ParamDataType 4 = int32、6 = float32、8 = OLE 日期 double、12 = UTF-16LE 字串、9 = 位元組、3 = 窄字串（本庫只有 FF 裝置的十六進位容器使用，Archived=1）。FF 參數容器內的型別字母 D/E/G/I 等由樣本推得。已與前簿 21/22 參數現值逐值核對（見 15_參數解碼摘要）。',
        'ComputerId 為 IPv4 以有號 32 位元整數儲存，已解成點分格式；2130706433 = 127.0.0.1（伺服器本機）。',
        '本廠 AMS 只作組態/稽核用：Alert Monitor 服務旗標為 1 但無任何裝置在監視名單，AlertList/AlertLog/DeviceMonitorList/TestResults/Routes 等 0 列；Disposition 全為 Spare；CalStatus 全 0（校正資料以 Beamex CMX 為準）。',
        '中文欄名後括號為原始欄名或來源表.欄；「推定」「(低信心)」字樣代表推論，非資料庫明示。各表註記見本頁第 5 節。',
        '查詢：02_設備查詢卡 在 C3 輸入任何位號字串即顯示該設備（公式查表，來源 04_位號索引）；各表都有「設備別名 (alias)」欄可互相篩選，D0xxxx 別名與前簿相同。',
        '前簿（20260910_AMS解析.xlsx）交叉核對：設備 GUID 對上 1,928/1,928；參數現值總數 344,943 = 前簿 204,562 HART + 140,381 FF；事件由 13,682 擴充為 29,773。',
    ],
    'kpis': [
        ['設備數', '1,928 台（HART 1,577＝現場儀表 1,324 + GE Mark VIe HART I/O 模組(MUX) 253；FF 351）；網路 18 個 MUX 網路 + 1 個 FF HSE 網路（22 個 FF 連結裝置）'],
        ['事件', '29,773 筆（1996–2026；2024-11 起本廠 22,063 筆）；前簿匯出只含 13,682 筆'],
        ['參數', '現值 344,943 筆、變更歷程 6,179 筆、參數名 9,258 個'],
        ['識別狀態', 'IdentStatus=0（上次掃描未再識別）34 台；同一 MUX 通道雙設備 3 組'],
        ['刪除裝置事件', '345 筆 / 177 台（168 台 FF 於 2025-03-31 與 04-09 各被刪一次），對應 Assets 345 筆孤立資產'],
        ['帳號', 'Windows 使用者 7、AMS 標準使用者 4；6 人擁有全部 46 項權限；共用帳號 HMI\\GEAdmin 佔 8,133 筆事件'],
        ['警報定義', '140,438 筆 DD 警報定義（使用中機型 2,877 筆），無任何警報歷史'],
        ['範本', '2,712 個 NamedConfigs（前簿 2,178 個範本）、範本參數 306,891 筆'],
    ],
    'top_findings': findings,
    'open_questions': open_q,
    'cross_checks': cross,
}
json.dump(cfg, open('order.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('sheets', len(order), 'findings', len(findings), 'open_q', len(open_q))
for o in order:
    print(o['number'], o['module_key'], o['sheet_name'])
