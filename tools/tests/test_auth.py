# -*- coding: utf-8 -*-
"""登入閘門與密語：錯代號被擋、對的代號放行、錯密語被擋、對的密語解鎖；主站也能登入並看到「新版網站」連結。"""
from e2e_common import Checks, browser


def run(ctx):
    ck = Checks()
    with browser(ctx) as (page, errors, console):
        page.goto(ctx['base'] + '/db/#/card/')
        page.wait_for_selector('#auth-id', timeout=15000)
        page.fill('#auth-id', '000000'); page.click('#auth-submit'); page.wait_for_timeout(1200)
        ck('wrong employee id stays on login', page.locator('#auth-id').is_visible() and page.locator('#key-pass').count() == 0)
        page.fill('#auth-id', ctx['uid']); page.click('#auth-submit')
        page.wait_for_selector('#key-pass', timeout=15000)
        page.fill('#key-pass', 'wrong-passphrase'); page.click('#key-submit'); page.wait_for_timeout(2500)
        ck('wrong passphrase stays locked', page.locator('#key-pass').is_visible() and page.locator('.cq-input').count() == 0)
        page.fill('#key-pass', ctx['pass']); page.click('#key-submit')
        page.wait_for_selector('.cq-input', timeout=60000)
        ck('correct passphrase unlocks', True)
        ck('user chip shows name', page.locator('.auth-chip').count() == 1 and page.locator('.auth-chip').inner_text().strip() != '')
        # 主站（20260910）：同一個工作階段與密語直接可用；側欄底部有到新版網站的連結
        page.goto(ctx['base'] + '/#/s/00'); page.wait_for_selector('.sheet-link', timeout=60000); page.wait_for_timeout(300)
        foot = page.locator('#sidebar-foot').inner_text() if page.locator('#sidebar-foot').count() else ''
        ck('old site links to new site', '新版網站' in foot, foot[-80:])
        ck('no page errors', not errors, errors[:3])
        ck('no console errors/warnings', not console, console[:3])
    return ck.fails
