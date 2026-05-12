import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars'
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        # Inject standard stealth scripts (navigator.webdriver false)
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        
        print("Fetching Betclic...")
        response = await page.goto("https://www.betclic.pl/pilka-nozna-s1", wait_until="domcontentloaded")
        print(f"Status: {response.status}")
        
        content = await page.content()
        with open("betclic_test.html", "w") as f:
            f.write(content)
            
        print(f"Page title: {await page.title()}")
        print(f"Content length: {len(content)} bytes")
        
        if "zablokowany" in content.lower() or "cloudflare" in content.lower() or "rozwiązanie problemu" in content.lower():
            print("FAILED: Probably blocked by Cloudflare/Datadome.")
        else:
            print("SUCCESS: Looks like we got the actual page.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())