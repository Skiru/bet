"""Test nodriver (undetectable Chrome) to bypass Sofascore WAF.

nodriver = successor to undetected-chromedriver, 4.2K stars.
No WebDriver markers, direct CDP communication.
"""
import nodriver as uc
import json
import asyncio

DATE = "2026-05-13"

async def main():
    print("Starting nodriver (undetectable Chrome)...")
    browser = await uc.start(
        headless=False,
        browser_executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    
    # Collect API responses
    api_responses = {}
    
    tab = await browser.get("about:blank")
    
    # Set up network interception via CDP
    await tab.send(uc.cdp.network.enable())
    
    captured = []
    
    async def on_response(event):
        url = event.response.url
        if "api" in url and ("scheduled-events" in url or "sport" in url):
            # Capture API response
            try:
                body = await tab.send(uc.cdp.network.get_response_body(event.request_id))
                if body and body[0]:  # body is (body_text, base64_encoded)
                    data = json.loads(body[0])
                    events_count = len(data.get("events", []))
                    print(f"  CAPTURED: {url} — {events_count} events")
                    captured.append({"url": url, "data": data})
            except Exception as e:
                print(f"  CAPTURE ERROR for {url}: {e}")
    
    tab.add_handler(uc.cdp.network.ResponseReceived, on_response)
    
    # Navigate to Sofascore football page
    print(f"\nNavigating to Sofascore football scheduled events for {DATE}...")
    
    # Try direct API call first — the browser should pass WAF since it's real Chrome
    api_url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{DATE}"
    tab2 = await browser.get(api_url)
    await tab2.sleep(3)
    
    # Get the page content (should be JSON if WAF passed)
    content = await tab2.get_content()
    print(f"\nDirect API response length: {len(content)}")
    
    # Try to extract JSON from the page
    try:
        # nodriver returns HTML, but the body might contain JSON
        pre_el = await tab2.select("pre")
        if pre_el:
            text = pre_el.text
            data = json.loads(text)
            events_count = len(data.get("events", []))
            print(f"SUCCESS! Direct API returned {events_count} events!")
            if events_count > 0:
                ev = data["events"][0]
                print(f"  First: {ev.get('homeTeam',{}).get('name')} vs {ev.get('awayTeam',{}).get('name')}")
            # Save the data
            with open("betting/data/nodriver_sofa_test.json", "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved to betting/data/nodriver_sofa_test.json")
    except Exception as e:
        print(f"Not JSON in pre: {e}")
        # Print first 500 chars of content for debugging
        print(f"Content preview: {content[:500]}")
    
    # Also try the web page approach: navigate to Sofascore and capture XHR
    print(f"\nNavigating to Sofascore main page to capture API calls...")
    tab3 = await browser.get(f"https://www.sofascore.com/football/{DATE}")
    tab3.add_handler(uc.cdp.network.ResponseReceived, on_response)
    await tab3.sleep(5)
    
    print(f"\nCaptured {len(captured)} API responses")
    for c in captured:
        url = c["url"]
        events = len(c["data"].get("events", []))
        print(f"  {url}: {events} events")
    
    # Try other sports too via direct API
    for sport in ["basketball", "tennis", "ice-hockey", "volleyball"]:
        sport_url = f"https://api.sofascore.com/api/v1/sport/{sport}/scheduled-events/{DATE}"
        tab_sport = await browser.get(sport_url)
        await tab_sport.sleep(2)
        try:
            pre = await tab_sport.select("pre")
            if pre:
                data = json.loads(pre.text)
                events = len(data.get("events", []))
                print(f"{sport}: {events} events")
        except:
            print(f"{sport}: failed to parse")
    
    browser.stop()
    print("\nDone!")

if __name__ == "__main__":
    uc.loop().run_until_complete(main())
