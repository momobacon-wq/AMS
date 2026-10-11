# -*- coding: utf-8 -*-
"""登入閘門與密語：錯代號被擋、對的代號放行、錯密語被擋、對的密語解鎖；主站也能登入並看到「新版網站」連結；
「記住此裝置」預設不勾；讀不到 auth-config.json（斷網 abort／伺服器 503）時已登入者靠快取設定放行、未登入者鎖住；登出清掉 ams.key。"""
import json
import urllib.request

from e2e_common import Checks, browser


def control(ctx, **flags):
    """POST /mock-control：切換 mock 伺服器的故障模式（cfgdown → auth-config.json 回 503）"""
    req = urllib.request.Request(ctx['base'] + '/mock-control', data=json.dumps(flags).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def ls_get(page, key):
    return page.evaluate("k => { try { return localStorage.getItem(k); } catch (e) { return null; } }", key)


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        page.goto(ctx['base'] + '/db/#/card/')
        page.wait_for_selector('#auth-id', timeout=15000)
        page.fill('#auth-id', '000000'); page.click('#auth-submit'); page.wait_for_timeout(1200)
        ck('wrong employee id stays on login', page.locator('#auth-id').is_visible() and page.locator('#key-pass').count() == 0)
        page.fill('#auth-id', ctx['uid']); page.click('#auth-submit')
        page.wait_for_selector('#key-pass', timeout=15000)
        ck('remember-device unchecked by default', not page.is_checked('#key-remember'))
        page.fill('#key-pass', 'wrong-passphrase'); page.click('#key-submit'); page.wait_for_timeout(2500)
        ck('wrong passphrase stays locked', page.locator('#key-pass').is_visible() and page.locator('.cq-input').count() == 0)
        page.fill('#key-pass', ctx['pass']); page.check('#key-remember'); page.click('#key-submit')
        page.wait_for_selector('.cq-input', timeout=60000)
        ck('correct passphrase unlocks', True)
        ck('user chip shows name', page.locator('.auth-chip').count() == 1 and page.locator('.auth-chip').inner_text().strip() != '')
        ck('auth config cached in localStorage', bool(ls_get(page, 'ams.authcfg')))
        ck('remembered key stored', bool(ls_get(page, 'ams.key')))
        # 主站（20260910）：同一個工作階段與密語直接可用；側欄底部有到新版網站的連結
        page.goto(ctx['base'] + '/#/s/00'); page.wait_for_selector('.sheet-link', timeout=60000); page.wait_for_timeout(300)
        foot = page.locator('#sidebar-foot').inner_text() if page.locator('#sidebar-foot').count() else ''
        ck('old site links to new site', '新版網站' in foot, foot[-80:])

        # ---- 離線：擋掉 auth-config.json（route abort ＝ 斷網／hosts 擋掉）→ 已登入者靠快取設定放行，仍有使用者籤
        page.route('**/auth-config.json', lambda route: route.abort())
        page.goto(ctx['base'] + '/db/#/card/'); page.wait_for_selector('.cq-input', timeout=60000); page.wait_for_timeout(300)
        offline = page.evaluate('() => window.AMSAuth && { offline: AMSAuth.offline, enabled: AMSAuth.enabled, user: !!AMSAuth.user }')
        ck('config aborted: logged-in user still passes with chip', page.locator('#auth-gate').count() == 0 and page.locator('.auth-chip').count() == 1, offline)
        ck('config aborted: gate stays enabled via cached config', bool(offline) and offline['enabled'] and offline['offline'], offline)
        page.unroute('**/auth-config.json')
        # ---- 伺服器回 503（GitHub Pages 故障）：同樣走快取設定
        control(ctx, cfgdown=True)
        try:
            page.reload(); page.wait_for_selector('.cq-input', timeout=60000); page.wait_for_timeout(300)
            offline = page.evaluate('() => window.AMSAuth && { offline: AMSAuth.offline, enabled: AMSAuth.enabled, user: !!AMSAuth.user }')
            ck('config 503: logged-in user still passes', page.locator('#auth-gate').count() == 0 and bool(offline) and offline['offline'], offline)
            # ---- 沒有工作階段又讀不到設定：鎖住（送出鈕停用、顯示離線訊息），不能整站打開
            page.evaluate("() => localStorage.removeItem('ams.auth')")
            page.reload(); page.wait_for_selector('#auth-gate', timeout=15000); page.wait_for_timeout(500)
            msg = page.locator('#auth-msg').inner_text() if page.locator('#auth-msg').count() else ''
            ck('no session + config unavailable: locked', page.locator('#auth-submit').is_disabled() and '離線' in msg and page.locator('.cq-input').count() == 0, msg)
        finally:
            control(ctx, cfgdown=False)
        console[:] = [c for c in console if 'auth-config.json' not in c[1] and '503' not in c[1] and 'net::ERR_FAILED' not in c[1]]  # abort／503 是這段刻意製造的

        # ---- 登出：確認對話框接受 → 清掉工作階段與記住的密語金鑰
        page.reload(); page.wait_for_selector('#auth-id', timeout=15000)
        page.fill('#auth-id', ctx['uid']); page.click('#auth-submit')
        page.wait_for_selector('.cq-input', timeout=60000)  # 金鑰還記著，不再問密語
        ck('remembered key skips passphrase after re-login', bool(ls_get(page, 'ams.key')))
        page.once('dialog', lambda d: d.accept())
        page.click('.auth-chip'); page.wait_for_selector('#auth-id', timeout=15000); page.wait_for_timeout(300)
        ck('logout clears session', ls_get(page, 'ams.auth') is None)
        ck('logout clears remembered key (ams.key)', ls_get(page, 'ams.key') is None)
        ck('no page errors', not errors, errors[:3])
        ck('no console errors/warnings', not console, console[:3])
    return ck.fails
