import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Any, Dict, Tuple

def safe_http_get(
    url: str,
    headers: Dict[str, str] | None = None,
    params: Dict[str, Any] | None = None,
    timeout: float = 10.0
) -> Tuple[int, Any, str | None]:
    """
    Perform a safe HTTP GET request using standard urllib, returning (status_code, body, error_message).
    Ensures HTML content is blocked, timeout is capped at 20.0s, and response size is capped at 2,000,000 bytes.
    Headers/secrets are never printed or logged.
    """
    if params:
        query_string = urllib.parse.urlencode(params)
        url = f"{url}?{query_string}" if "?" not in url else f"{url}&{query_string}"

    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    actual_timeout = min(timeout, 20.0)

    try:
        with urllib.request.urlopen(req, timeout=actual_timeout) as response:
            status_code = response.status
            content = response.read(2000001)
            if len(content) > 2000000:
                return status_code, None, "Response exceeded maximum size of 2,000,000 bytes"

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                return status_code, "[BLOCKED_HTML]", "HTML content blocked"

            try:
                text = content.decode("utf-8", errors="replace")
            except Exception as e:
                return status_code, None, f"Decode error: {e}"

            text_lower = text.lower()
            if "<html" in text_lower or "<!doctype" in text_lower or "<body" in text_lower:
                return status_code, "[BLOCKED_HTML]", "HTML body blocked"

            if "application/json" in content_type or "json" in content_type:
                try:
                    return status_code, json.loads(text), None
                except Exception as e:
                    return status_code, text, f"Failed to parse JSON: {e}"

            return status_code, text, None

    except urllib.error.HTTPError as e:
        status_code = e.code
        try:
            content = e.read(2000001)
            if len(content) > 2000000:
                return status_code, None, "Response exceeded maximum size of 2,000,000 bytes"
            text = content.decode("utf-8", errors="replace")
            return status_code, text, f"HTTPError {status_code}: {e.reason}"
        except Exception:
            return status_code, None, f"HTTPError {status_code}: {e.reason}"
    except Exception as e:
        return 0, None, f"HTTP exception: {str(e)}"


def safe_http_post(
    url: str,
    headers: Dict[str, str] | None = None,
    json_data: Any = None,
    timeout: float = 10.0
) -> Tuple[int, Any, str | None]:
    """
    Perform a safe HTTP POST request using standard urllib, returning (status_code, body, error_message).
    Ensures HTML content is blocked, timeout is capped at 20.0s, and response size is capped at 2,000,000 bytes.
    Headers/secrets are never printed or logged.
    """
    data_bytes = None
    if json_data is not None:
        data_bytes = json.dumps(json_data).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, method="POST")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    if json_data is not None:
        req.add_header("Content-Type", "application/json")

    actual_timeout = min(timeout, 20.0)

    try:
        with urllib.request.urlopen(req, timeout=actual_timeout) as response:
            status_code = response.status
            content = response.read(2000001)
            if len(content) > 2000000:
                return status_code, None, "Response exceeded maximum size of 2,000,000 bytes"

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                return status_code, "[BLOCKED_HTML]", "HTML content blocked"

            try:
                text = content.decode("utf-8", errors="replace")
            except Exception as e:
                return status_code, None, f"Decode error: {e}"

            text_lower = text.lower()
            if "<html" in text_lower or "<!doctype" in text_lower or "<body" in text_lower:
                return status_code, "[BLOCKED_HTML]", "HTML body blocked"

            if "application/json" in content_type or "json" in content_type:
                try:
                    return status_code, json.loads(text), None
                except Exception as e:
                    return status_code, text, f"Failed to parse JSON: {e}"

            return status_code, text, None

    except urllib.error.HTTPError as e:
        status_code = e.code
        try:
            content = e.read(2000001)
            if len(content) > 2000000:
                return status_code, None, "Response exceeded maximum size of 2,000,000 bytes"
            text = content.decode("utf-8", errors="replace")
            return status_code, text, f"HTTPError {status_code}: {e.reason}"
        except Exception:
            return status_code, None, f"HTTPError {status_code}: {e.reason}"
    except Exception as e:
        return 0, None, f"HTTP exception: {str(e)}"
