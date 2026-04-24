#!/usr/bin/env python3
"""Scan niche sports from Flashscore and other sources for Apr 24."""
from playwright.sync_api import sync_playwright

def scan_sport(ctx, name, url, max_lines=60):
    page = ctx.new_page()
    try:
        page.goto(url, timeout=15000)
        page.wait_for_timeout(3000)
        try:
            page.click('#onetrust-accept-btn-handler', timeout=2000)
        except:
            pass
        page.wait_for_timeout(500)
        text = page.inner_text('body')
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        print(f'\n=== {name} ({len(lines)} lines) ===')
        for line in lines[:max_lines]:
            print(f'  {line[:140]}')
    except Exception as e:
        print(f'\n=== {name} === ERROR: {e}')
    finally:
        page.close()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(locale='en-GB')

    scan_sport(ctx, 'SNOOKER', 'https://www.flashscore.com/snooker/')
    scan_sport(ctx, 'DARTS', 'https://www.flashscore.com/darts/')
    scan_sport(ctx, 'TABLE TENNIS', 'https://www.flashscore.com/table-tennis/', max_lines=40)
    scan_sport(ctx, 'ESPORTS', 'https://www.flashscore.com/esports/', max_lines=80)
    scan_sport(ctx, 'MMA', 'https://www.flashscore.com/mma/')

    browser.close()
    print('\nDONE')
