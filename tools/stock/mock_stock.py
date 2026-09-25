# -*- coding: utf-8 -*-
"""tools/stock/Code.gs 的本機替身（由 tools/auth/mock_server.py 掛在 POST /mock-stock）。
同一套 action（list / logs / txn / adjust）與回應格式；不驗 token（只要求欄位存在）。
資料：mock_inventory.json（假資料，進 repo）→ 第一次啟動複製成 mock_stock_state.json（執行狀態，不進 repo）；
紀錄：mock_stock_log.jsonl（最新在前讀出）。
"""
import json
import os
import re
import threading
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, 'mock_inventory.json')
STATE = os.path.join(HERE, 'mock_stock_state.json')
LOG = os.path.join(HERE, 'mock_stock_log.jsonl')
_lock = threading.Lock()
_txns = {}


def _norm(s):
    return ''.join(unicodedata.normalize('NFKC', str(s or '')).split()).upper()


def _load():
    if not os.path.exists(STATE):
        with open(SEED, encoding='utf-8') as f:
            items = json.load(f)
        _save(items)
    with open(STATE, encoding='utf-8') as f:
        return json.load(f)


def _save(items):
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


def _log(rows):
    with open(LOG, 'a', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def _read_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, encoding='utf-8') as f:
        rows = [json.loads(x) for x in f if x.strip()]
    rows.reverse()
    return rows


def reset():
    """測試用：回到 seed、清紀錄"""
    with _lock:
        if os.path.exists(STATE):
            os.remove(STATE)
        if os.path.exists(LOG):
            os.remove(LOG)
        _txns.clear()


def handle(body, user):
    """body: 請求 JSON；user: {'id','name'}（mock_server 由 token 解出，解不出就用 body.id）→ 回應 dict"""
    action = body.get('action')
    if not body.get('stockToken'):
        return {'ok': False, 'auth': True, 'error': '未授權（缺 stockToken）'}
    if not body.get('token') or not body.get('id'):
        return {'ok': False, 'auth': True, 'error': '工作階段無效，請重新登入。'}
    with _lock:
        items = _load()
        if action == 'list':
            return {'ok': True, 'rev': str(int(os.path.getmtime(STATE))), 'items': items}
        if action == 'logs':
            pn, kks = str(body.get('pn') or '').strip(), _norm(body.get('kks'))
            limit = max(1, min(300, int(body.get('limit') or 300)))
            out = [r for r in _read_log() if (not pn or r['pn'] == pn) and (not kks or _norm(r.get('kks')) == kks)]
            return {'ok': True, 'rows': out[:limit]}
        if action == 'txn':
            txn = str(body.get('txnId') or '')
            if not re.match(r'^[A-Za-z0-9_-]{8,40}$', txn):
                return {'ok': False, 'error': 'txnId 格式錯誤'}
            if txn in _txns:  # 同 txnId 重送：回上次結果（與 Worker 同格式 replay:true，不重扣）
                return dict(_txns[txn], replay=True)
            seen = [r for r in _read_log() if r.get('txn') == txn]  # mock 重啟後記憶體沒了，退而查紀錄檔
            if seen:
                seen.reverse()
                return {'ok': True, 'replay': True, 'results': [{'pn': r['pn'], 'qty': r['bal'], 'delta': r['delta']} for r in seen]}
            reqs = body.get('items') or []
            if not reqs:
                return {'ok': False, 'error': '沒有項目'}
            by = {it['pn']: it for it in items}
            merged, order = {}, []
            for i, r in enumerate(reqs):
                pn = str(r.get('pn') or '').strip()
                try:
                    d = int(r.get('delta'))
                except (TypeError, ValueError):
                    d = 0
                if not pn:
                    return {'ok': False, 'error': f'第 {i + 1} 項缺料號'}
                if d == 0 or abs(d) > 9999:
                    return {'ok': False, 'error': f'{pn}：數量必須是非零整數'}
                if pn not in by:
                    return {'ok': False, 'error': f'料號不存在：{pn}'}
                if pn not in merged:
                    merged[pn] = 0; order.append(pn)
                merged[pn] += d
            plan = []
            for pn in order:
                nq = int(by[pn]['qty']) + merged[pn]
                if nq < 0:
                    return {'ok': False, 'error': f'{pn}：庫存不足（現有 {by[pn]["qty"]}，要領 {-merged[pn]}）'}
                plan.append((pn, merged[pn], nq))
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            rows = [{'ts': ts, 'id': user['id'], 'name': user['name'], 'action': 'IN' if d > 0 else 'OUT', 'pn': pn, 'delta': d, 'bal': nq,
                     'kks': _norm(body.get('kks'))[:40], 'note': str(body.get('note') or '')[:200], 'wo': str(body.get('wo') or '')[:40],
                     'source': str(body.get('source') or 'ams')[:20], 'txn': txn} for pn, d, nq in plan]
            _log(rows)
            for pn, d, nq in plan:
                by[pn]['qty'] = nq
            _save(items)
            res = {'ok': True, 'results': [{'pn': pn, 'qty': nq, 'delta': d} for pn, d, nq in plan]}
            _txns[txn] = res
            print('STOCK', json.dumps(rows, ensure_ascii=False), flush=True)
            return res
        if action == 'adjust':
            pn = str(body.get('pn') or '').strip()
            try:
                q = int(body.get('qty'))
            except (TypeError, ValueError):
                return {'ok': False, 'error': '數量必須是 0 以上的整數'}
            it = next((x for x in items if x['pn'] == pn), None)
            if not it:
                return {'ok': False, 'error': f'料號不存在：{pn}'}
            cur = int(it['qty'])
            _log([{'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'id': user['id'], 'name': user['name'], 'action': 'STOCKTAKE', 'pn': pn, 'delta': q - cur, 'bal': q,
                   'kks': '', 'note': str(body.get('note') or '')[:200], 'wo': '', 'source': 'ams-stock', 'txn': ''}])
            it['qty'] = q
            _save(items)
            return {'ok': True, 'results': [{'pn': pn, 'qty': q, 'delta': q - cur}]}
        return {'ok': False, 'error': '未知的動作'}
