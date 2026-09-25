# -*- coding: utf-8 -*-
"""測試共用：開瀏覽器、登入（mock 員工代號）、輸入密語、載入查詢卡。"""
import os
from contextlib import contextmanager
from playwright.sync_api import sync_playwright

CARD_READY = ("document.querySelector('.sum-search') && !document.querySelector('.sum-search .cl-empty')?.textContent.includes('載入中')"
              " && !document.querySelector('.sum-range .pending') && !document.querySelector('.sum-dev .pending')")


class Checks:
    def __init__(self):
        self.fails = []

    def __call__(self, name, cond, info=''):
        print(('  ok   ' if cond else '  FAIL ') + name + ((' ' + str(info)) if info else ''), flush=True)
        if not cond:
            self.fails.append(name + ((' ' + str(info)) if info else ''))


@contextmanager
def browser(ctx, mobile=False):
    """yield (page, errors, console)；errors = pageerror 訊息、console = error/warning 訊息（favicon 除外）"""
    with sync_playwright() as p:
        b = p.chromium.launch()
        vp = {'width': 390, 'height': 844} if mobile else {'width': 1280, 'height': 900}
        c = b.new_context(viewport=vp, bypass_csp=True, is_mobile=mobile, has_touch=mobile)
        page = c.new_page()
        errors, console = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: console.append((m.type, m.text)) if m.type in ('error', 'warning') and 'favicon' not in m.text else None)
        try:
            yield page, errors, console
        finally:
            b.close()


def login(page, ctx, site='db'):
    page.goto(ctx['base'] + ('/db/#/card/' if site == 'db' else '/#/s/00'))
    page.wait_for_selector('#auth-id', timeout=15000)
    page.fill('#auth-id', ctx['uid']); page.click('#auth-submit')
    page.wait_for_selector('#key-pass', timeout=15000)
    page.fill('#key-pass', ctx['pass']); page.click('#key-submit')
    page.wait_for_selector('.cq-input' if site == 'db' else '.sheet-link', timeout=60000)


def load_card(page, ctx, key):
    page.goto(ctx['base'] + '/db/#/card/' + key)
    page.wait_for_function(CARD_READY, timeout=60000)
    page.wait_for_timeout(300)


def shot(page, ctx, name):
    try:
        page.screenshot(path=os.path.join(ctx['out'], name + '.png'))
    except Exception:
        pass
