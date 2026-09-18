// ==UserScript==
// @name         Sofascore bridge (bet pipeline)
// @namespace    bet.sofa
// @version      2.2.0
// @description  Serves the local bet pipeline's Sofascore requests from inside a real sofascore.com tab.
// @match        https://www.sofascore.com/*
// @match        https://sofascore.com/*
// @run-at       document-start
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      127.0.0.1
// ==/UserScript==

/*
 * Why this exists
 * ---------------
 * Since 2026-09-17 Sofascore answers /api/v1/ with 403 {"reason":"challenge"}
 * for every non-browser client. The SPA's x-captcha token carries an `f` claim -
 * a fingerprint of the live connection, recomputed server-side - so the token
 * cannot be lifted out and replayed from curl_cffi. Only a request issued on the
 * browser's own connection gets a 200.
 *
 * So this script hooks window.fetch to learn the header pair the SPA sends,
 * polls the local queue (scripts/sofa/bridge_server.py) and performs the
 * pipeline's requests here, in page context.
 *
 * Note on the two transports below, which is not incidental: the sofascore.com
 * request uses plain `fetch` because it MUST ride the page's own connection,
 * while the 127.0.0.1 request uses GM_xmlhttpRequest because it must NOT be
 * subject to Sofascore's Content-Security-Policy, which does not list localhost
 * in connect-src and would block a plain fetch outright. Swapping either one
 * breaks the bridge in a way that looks like a network fault.
 *
 * Security note: Tampermonkey itself holds all-sites access, which is more than
 * this script needs (sofascore.com + the bridge port). That was a deliberate,
 * informed trade for its maturity and its UI for disabling scripts. If that ever
 * stops feeling right, the same logic fits an unpacked extension scoped to
 * exactly those two origins, talking to this same server.
 */

(function () {
  'use strict';

  const BRIDGE = 'http://127.0.0.1:8787';

  // Declaring any @grant puts this script in Tampermonkey's sandbox, where
  // `window` is a proxy and `window.fetch` is NOT the page's fetch. Hooking the
  // proxy silently captures nothing - the SPA's requests never pass through it -
  // and the bridge then sends unauthenticated requests that come back 403.
  // unsafeWindow is the real page object, and both the hook and the outgoing
  // request must use it.
  const pageWindow = (typeof unsafeWindow !== 'undefined') ? unsafeWindow : window;

  // Never exceed this rate. We are a guest on someone else's production API, and
  // an unpaced burst from this machine (~2800 requests in 15 minutes, peaking at
  // 550 req/s) coincided with Sofascore closing /api/v1/ on 2026-09-17. The
  // Python client paces too; this is the floor that holds even if it does not.
  const MIN_INTERVAL_MS = 350;

  // A stale x-captcha shows up as 403. Reloading makes the SPA mint a fresh one,
  // but a reload loop against a hard block would be its own kind of abuse.
  const RELOAD_COOLDOWN_MS = 120000;

  let capturedHeaders = null;
  let lastRequestAt = 0;
  let lastReloadAt = 0;
  let consecutive403 = 0;

  // --- 1. learn the headers the SPA sends ---------------------------------

  const origFetch = pageWindow.fetch;
  pageWindow.fetch = function () {
    try {
      const a = arguments;
      const req = a[0] instanceof pageWindow.Request
        ? a[0]
        : new pageWindow.Request(a[0], a[1]);
      if (req.url.indexOf('/api/v1/') !== -1) {
        const h = {};
        req.headers.forEach(function (v, k) { h[k] = v; });
        if (h['x-captcha'] || h['x-requested-with']) {
          if (!capturedHeaders) {
            console.log('[sofa-bridge] captured the SPA headers: ' +
              Object.keys(h).filter(function (k) {
                return k.indexOf('x-') === 0;
              }).join(', '));
          }
          capturedHeaders = h;
        }
      }
    } catch (e) { /* never break the page */ }
    return origFetch.apply(this, arguments);
  };

  // --- 2. the localhost leg, exempt from the page's CSP --------------------

  function bridgeRequest(method, path, body) {
    return new Promise(function (resolve, reject) {
      GM_xmlhttpRequest({
        method: method,
        url: BRIDGE + path,
        headers: body ? { 'Content-Type': 'application/json' } : {},
        data: body ? JSON.stringify(body) : undefined,
        timeout: 40000,
        onload: function (res) {
          try { resolve(JSON.parse(res.responseText)); }
          catch (e) { reject(e); }
        },
        onerror: reject,
        ontimeout: reject,
      });
    });
  }

  // --- 3. serve the pipeline's requests ------------------------------------

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function pace() {
    const wait = MIN_INTERVAL_MS - (Date.now() - lastRequestAt);
    if (wait > 0) await sleep(wait);
    lastRequestAt = Date.now();
  }

  function maybeReload(status) {
    // One 403 can be a genuinely forbidden resource. Three in a row is a stale
    // token, and only then is a reload worth its cost.
    if (status !== 403) { consecutive403 = 0; return; }
    consecutive403 += 1;
    if (consecutive403 < 3) return;
    if (Date.now() - lastReloadAt < RELOAD_COOLDOWN_MS) return;
    lastReloadAt = Date.now();
    consecutive403 = 0;
    console.warn('[sofa-bridge] 3x 403 - reloading to mint a fresh x-captcha');
    location.reload();
  }

  // The pipeline addresses api.sofascore.com, but this page is www.sofascore.com
  // and api.* sends no CORS headers for it, so a cross-origin fetch dies as an
  // opaque "TypeError: Failed to fetch". The SPA only ever calls /api/v1/ on its
  // own origin; same-origin is the condition that makes the request work at all,
  // so rewrite rather than ask the pipeline to know about page origins.
  function sameOrigin(url) {
    return url.replace(
      /^https:\/\/api\.sofascore\.com\//,
      'https://www.sofascore.com/'
    );
  }

  async function runJob(job) {
    if (!/^https:\/\/(www|api)\.sofascore\.com\//.test(job.url)) {
      await bridgeRequest('POST', '/push', {
        id: job.id, status: null, error: 'refused non-sofascore URL',
      }).catch(function () {});
      return;
    }

    await pace();
    if (!capturedHeaders) {
      // Worth saying out loud: without them Sofascore answers 403, and the
      // cause (no SPA traffic seen yet) looks nothing like the symptom.
      console.warn('[sofa-bridge] no SPA headers captured yet - click a match ' +
        'on the page so the app issues an /api/v1/ request');
    }
    let payload;
    try {
      const headers = Object.assign({ Accept: 'application/json' }, capturedHeaders || {});
      const res = await origFetch(sameOrigin(job.url), { headers: headers, credentials: 'include' });
      const body = await res.text();
      payload = { id: job.id, status: res.status, body: body };
      maybeReload(res.status);
    } catch (e) {
      payload = { id: job.id, status: null, error: String(e) };
    }

    await bridgeRequest('POST', '/push', payload).catch(function () {});
  }

  async function loop() {
    console.log('[sofa-bridge] starting, will poll ' + BRIDGE);
    let loggedError = null;
    let everConnected = false;

    for (;;) {
      let job = null;
      try {
        job = (await bridgeRequest('GET', '/pull')).job;
        if (!everConnected) {
          everConnected = true;
          loggedError = null;
          console.log('[sofa-bridge] connected to the bridge server');
        }
      } catch (e) {
        // Surface this once per distinct cause. Silently sleeping here made a
        // broken bridge look identical to an idle one, which cost real time.
        const msg = String(e && e.error ? e.error : e);
        if (msg !== loggedError) {
          loggedError = msg;
          console.error(
            '[sofa-bridge] cannot reach ' + BRIDGE + ': ' + msg +
            ' - is bridge_server.py running, and did Tampermonkey grant the ' +
            '@connect 127.0.0.1 permission?'
          );
        }
        await sleep(5000);
        continue;
      }
      if (!job) continue;
      await runJob(job);
    }
  }

  if (window.top === window.self) loop();
})();
