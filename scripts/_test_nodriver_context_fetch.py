
import asyncio
import nodriver as uc
import sys

async def main():
    print("Launching nodriver Chrome...")
    # Launch browser headlessly or headed
    browser = await uc.start(
        headless=True,
        browser_args=['--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36']
    )
    
    # Get the main page
    page = await browser.get('about:blank')
    
    print("Navigating to https://www.sofascore.com/football/2026-05-13 ...")
    await page.get('https://www.sofascore.com/football/2026-05-13')
    
    print("Waiting 12 seconds for Cloudflare challenge to pass...")
    await asyncio.sleep(12)
    
    print("Evaluating fetch in page context...")
    result = await page.evaluate('''
        async () => {
            try {
                let res = await fetch("https://api.sofascore.app/api/v1/sport/football/scheduled-events/2026-05-13", {
                    headers: { "Origin": "https://www.sofascore.com" }
                });
                return await res.text();
            } catch (e) {
                return "ERROR: " + e.toString();
            }
        }
    ''')
    
    print("--- RAW RESULT PREVIEW ---")
    if result:
        print(result[:500])
        if "challenge" in result.lower() or "error" in result.lower():
            print("\n⚠️ Still getting challenge!")
        elif "events" in result:
            print("\n✅ SUCCESS! We got events.")
    else:
        print("Empty result!")
        
    await browser.stop()

if __name__ == '__main__':
    uc.loop().run_until_complete(main())
