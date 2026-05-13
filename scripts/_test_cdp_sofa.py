"""CDP approach: navigate to Sofascore event page, capture API calls via CDP.

Based on mckayjohns technique:
1. Open browser with CDP enabled
2. Navigate to sofascore.com event page
3. CDP captures ALL network responses including internal API calls
4. Extract the API data we need
"""
import sys, time, json
sys.path.insert(0, "src")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

print("=" * 60)
print("CDP Approach: Capture internal API calls from event page")
print("=" * 60)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        '--disable-blink-features=AutomationControlled',
        '--disable-infobars',
        '--no-sandbox',
    ])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
        locale="en-US",
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    
    # Create CDP session
    cdp = context.new_cdp_session(page)
    
    # Enable network tracking
    cdp.send("Network.enable")
    
    # Store all network responses
    responses = []
    request_map = {}
    
    def on_request(params):
        request_map[params["requestId"]] = params.get("request", {}).get("url", "")
    
    def on_response(params):
        url = params.get("response", {}).get("url", "")
        status = params.get("response", {}).get("status", 0)
        request_id = params.get("requestId", "")
        
        # Only track API calls
        if "api" in url.lower() and status == 200:
            responses.append({
                "requestId": request_id,
                "url": url,
                "status": status,
                "mimeType": params.get("response", {}).get("mimeType", ""),
            })
    
    cdp.on("Network.requestWillBeSent", on_request)
    cdp.on("Network.responseReceived", on_response)
    
    # Navigate to the football schedule page
    print("\nNavigating to sofascore.com/football/2026-05-13...")
    page.goto("https://www.sofascore.com/football/2026-05-13", wait_until="domcontentloaded", timeout=25000)
    
    # Wait for page to fully load and make API calls
    print("Waiting for page JavaScript to make API calls...")
    time.sleep(8)
    
    # Scroll to trigger lazy loading
    page.evaluate("window.scrollBy(0, 1000)")
    time.sleep(3)
    page.evaluate("window.scrollBy(0, 2000)")
    time.sleep(3)
    
    print(f"\nCaptured {len(responses)} API responses:")
    for resp in responses:
        print(f"  [{resp['status']}] {resp['url'][:120]}")
    
    # Try to extract response bodies
    print(f"\nExtracting response bodies...")
    for resp in responses:
        try:
            body_result = cdp.send("Network.getResponseBody", {
                "requestId": resp["requestId"]
            })
            body = body_result.get("body", "")
            is_base64 = body_result.get("base64Encoded", False)
            
            if is_base64:
                import base64
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            
            # Try to parse as JSON
            try:
                data = json.loads(body)
                # Check if this has events
                if "events" in data:
                    print(f"\n  FOUND EVENTS in {resp['url'][:80]}")
                    events = data["events"]
                    print(f"  Count: {len(events)}")
                    if events:
                        ev = events[0]
                        print(f"  First: {ev.get('homeTeam',{}).get('name')} vs {ev.get('awayTeam',{}).get('name')}")
                else:
                    print(f"  {resp['url'][:60]} — keys: {list(data.keys())[:5]}")
            except json.JSONDecodeError:
                print(f"  {resp['url'][:60]} — not JSON ({len(body)} bytes)")
                
        except Exception as e:
            print(f"  {resp['url'][:60]} — body error: {e}")
    
    # Also check ALL network requests (not just API)
    print(f"\nAll tracked requests: {len(request_map)}")
    api_requests = [url for url in request_map.values() if "sofascore" in url and "api" in url.lower()]
    print(f"Sofascore API requests: {len(api_requests)}")
    for url in api_requests[:20]:
        print(f"  {url[:120]}")
    
    cdp.detach()
    context.close()
    browser.close()
