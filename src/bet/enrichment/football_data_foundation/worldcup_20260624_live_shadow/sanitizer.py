import hashlib
import json
import re
from pathlib import Path
from typing import Any

SECRET_KEYS = {
    "api_key", "x-api-key", "x-auth-token", "authorization", 
    "bearer", "token", "cookie", "set-cookie", "secret", "password"
}

SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|x[_-]api[_-]key|x[_-]auth[_-]token|authorization|bearer|token|cookie|set[_-]cookie|secret|password)"
)


def is_html(text: str) -> bool:
    text_lower = text.lower()
    return "<html" in text_lower or "<!doctype" in text_lower or "<body" in text_lower or "<div" in text_lower


def sanitize_json_body(val: Any) -> Any:
    """
    Recursively sanitize JSON bodies to strip/redact secret-like keys and values,
    and block HTML.
    """
    if isinstance(val, str):
        if is_html(val):
            raise ValueError("HTML content is not allowed in response body")
        
        # Check if the string itself contains any secret-like words
        val_lower = val.lower()
        if any(secret in val_lower for secret in ["bearer ", "token=", "api_key=", "password="]):
            return "[REDACTED_SECRET_VALUE]"
        if SECRET_PATTERN.search(val):
            # If it looks like a raw token/secret, redact it
            if len(val) > 10 and not val.startswith("{") and not val.startswith("["):
                return "[REDACTED_SECRET_VALUE]"
        return val

    if isinstance(val, dict):
        new_dict = {}
        for k, v in val.items():
            k_str = str(k)
            k_lower = k_str.lower()
            
            # Force selectable_for_production to False
            if k_lower == "selectable_for_production":
                new_dict[k_str] = False
                continue
                
            if SECRET_PATTERN.search(k_str) or any(s in k_lower for s in SECRET_KEYS):
                new_dict[k_str] = "[REDACTED_SECRET]"
            else:
                try:
                    new_dict[k_str] = sanitize_json_body(v)
                except ValueError as e:
                    if "HTML" in str(e):
                        raise
                    new_dict[k_str] = "[BLOCKED_HTML]"
        return new_dict

    if isinstance(val, list):
        return [sanitize_json_body(item) for item in val]

    return val


def compute_body_sha256(body: Any) -> str:
    """
    Compute stable SHA-256 for the same sanitized body.
    """
    if body is None:
        return hashlib.sha256(b"").hexdigest()
    if isinstance(body, str):
        payload = body
    else:
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_json(path: Path, data: Any) -> None:
    """
    Write deterministic JSON with indent=2, sort_keys=True, and a final newline.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")
