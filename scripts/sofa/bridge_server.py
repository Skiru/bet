"""Local bridge between the pipeline and a real browser tab on sofascore.com.

Since 2026-09-17 Sofascore answers `/api/v1/` with `403 {"reason":"challenge"}`
for every non-browser client. The `x-captcha` token the SPA sends carries an `f`
claim — a fingerprint of the *live connection*, recomputed server-side — so the
token cannot be lifted out of the browser and replayed from curl_cffi. The only
client that gets a 200 is the browser itself.

This server is the queue between the two halves:

    pipeline  --POST /fetch-->  [queue]  <--GET /pull--  userscript (browser tab)
    pipeline  <--result------   [queue]  <--POST /push-  userscript

The browser half is `userscripts/sofascore-bridge.user.js`, a Tampermonkey
script on an open sofascore.com tab. It performs the `fetch` in page context —
inheriting the real connection, cookies and the SPA's own headers — and posts
the JSON back. This server also serves that script at
`/sofascore-bridge.user.js`, which Tampermonkey turns into a one-click install.

Run it with:  python scripts/sofa/bridge_server.py
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger("sofa.bridge")

# The page origin allowed to talk to this server. Chrome exempts http://localhost
# from mixed-content blocking (it is a "potentially trustworthy" origin), so an
# HTTPS page can reach us without a certificate.
ALLOWED_ORIGIN = "https://www.sofascore.com"

DEFAULT_PORT = 8787
# How long a job may sit unclaimed before the pipeline gives up on it.
JOB_TIMEOUT_S = 60.0
# How long /pull blocks waiting for work before answering empty.
#
# Short on purpose. On 2026-09-23 every request the tabs made to 127.0.0.1 ran
# over ONE connection, one at a time (lsof: a single ESTABLISHED socket with
# five windows open), so a tab's /push waited behind the other tabs' /pull
# long-polls. Every /push landed 7-17 ms after some /pull closed; a job the tab
# had already fetched came back after 60-80 s, and the pipeline's 60 s deadline
# turned a healthy bridge into a 504 on every request. At 20.0 the preflight
# FAILed three times in a row; at 1.0, same browser, same tabs, it passed, and
# measure_bridge_capacity.py sustained 14.4-14.8 req/s over 300 requests, zero
# non-200 - the 5 x 2.86 design ceiling. An empty /pull on localhost costs
# nothing, so a short wait is cheap even when the connections are parallel.
PULL_WAIT_S = 1.0


class Job:
    __slots__ = (
        "id", "url", "done", "status", "body", "headers", "error", "created",
    )

    def __init__(self, url: str) -> None:
        self.id = uuid.uuid4().hex
        self.url = url
        self.done = threading.Event()
        self.status: int | None = None
        self.body: str | None = None
        # The diagnostic response headers, if the userscript sent any. The
        # only place a provider says outright that it is throttling us (F24).
        self.headers: dict[str, str] = {}
        self.error: str | None = None
        self.created = time.monotonic()


class JobQueue:
    def __init__(self) -> None:
        self._pending: list[Job] = []
        self._by_id: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._work = threading.Condition(self._lock)
        self.last_pull: float | None = None

    def submit(self, url: str) -> Job:
        job = Job(url)
        with self._work:
            self._pending.append(job)
            self._by_id[job.id] = job
            self._work.notify()
        return job

    def claim(self, wait: float) -> Job | None:
        """Hand one pending job to the browser, blocking up to `wait` seconds."""
        deadline = time.monotonic() + wait
        with self._work:
            self.last_pull = time.monotonic()
            while not self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._work.wait(remaining)
            return self._pending.pop(0)

    def complete(
        self,
        job_id: str,
        status: int | None,
        body: str | None,
        error: str | None,
        headers: dict[str, str] | None = None,
    ) -> bool:
        with self._lock:
            job = self._by_id.pop(job_id, None)
        if job is None:
            return False
        job.status = status
        job.body = body
        job.headers = headers or {}
        job.error = error
        job.done.set()
        return True

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._by_id.pop(job_id, None)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pending": len(self._pending),
                "in_flight": len(self._by_id),
                "last_pull_age_s": (
                    None
                    if self.last_pull is None
                    else round(time.monotonic() - self.last_pull, 1)
                ),
            }


QUEUE = JobQueue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _reply(self, code: int, payload: Any) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- endpoints --------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/pull"):
            job = QUEUE.claim(PULL_WAIT_S)
            if job is None:
                self._reply(200, {"job": None})
            else:
                self._reply(200, {"job": {"id": job.id, "url": job.url}})
            return
        if self.path.startswith("/health"):
            self._reply(200, {"ok": True, **QUEUE.stats()})
            return
        if self.path.startswith("/sofascore-bridge.user.js"):
            self._serve_userscript()
            return
        self._reply(404, {"error": "unknown path"})

    def _serve_userscript(self) -> None:
        """Serve the userscript for one-click install.

        Tampermonkey intercepts any navigation to a URL ending in `.user.js` and
        shows its install page, which turns installation into a single click
        instead of a copy-paste into its editor.
        """
        path = (
            Path(__file__).resolve().parents[2]
            / "userscripts"
            / "sofascore-bridge.user.js"
        )
        try:
            raw = path.read_bytes()
        except OSError as e:
            self._reply(500, {"error": f"cannot read userscript: {e}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        try:
            data = self._read_json()
        except Exception as e:
            self._reply(400, {"error": f"bad json: {e}"})
            return

        if self.path.startswith("/push"):
            raw_headers = data.get("headers")
            ok = QUEUE.complete(
                str(data.get("id")),
                data.get("status"),
                data.get("body"),
                data.get("error"),
                {
                    str(k): str(v)
                    for k, v in raw_headers.items()
                    if isinstance(raw_headers, dict)
                }
                if isinstance(raw_headers, dict)
                else {},
            )
            self._reply(200, {"accepted": ok})
            return

        if self.path.startswith("/fetch"):
            url = data.get("url")
            if not isinstance(url, str) or not url.startswith(
                ("https://www.sofascore.com/", "https://api.sofascore.com/")
            ):
                self._reply(400, {"error": "url must be a sofascore.com URL"})
                return
            timeout = float(data.get("timeout") or JOB_TIMEOUT_S)
            job = QUEUE.submit(url)
            if not job.done.wait(timeout):
                QUEUE.forget(job.id)
                self._reply(
                    504,
                    {
                        "error": "bridge timeout — is the sofascore.com tab open "
                        "with the userscript running?",
                        **QUEUE.stats(),
                    },
                )
                return
            self._reply(
                200,
                {
                    "status": job.status,
                    "body": job.body,
                    "headers": job.headers,
                    "error": job.error,
                },
            )
            return

        self._reply(404, {"error": "unknown path"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    logger.info("sofa bridge listening on http://127.0.0.1:%d", args.port)
    logger.info(
        "install the userscript: http://127.0.0.1:%d/sofascore-bridge.user.js",
        args.port,
    )
    logger.info("then open https://www.sofascore.com/ and leave the tab open")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
