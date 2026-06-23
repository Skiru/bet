import datetime
import requests
from typing import Any, Dict, Tuple


def safe_http_get(
    url: str, 
    headers: Dict[str, str] | None = None, 
    params: Dict[str, Any] | None = None, 
    timeout: float = 10.0
) -> Tuple[int, Any, str | None]:
    """
    Perform a safe HTTP GET request, returning (status_code, body, error_message).
    Ensures HTML content is blocked and headers/secrets are never printed or returned.
    """
    try:
        # Perform the actual request
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        
        content_type = response.headers.get("Content-Type", "").lower()
        
        if "text/html" in content_type:
            return response.status_code, "[BLOCKED_HTML]", "HTML content blocked"
            
        # Double check body text for HTML patterns just in case content-type is mislabeled
        text = response.text
        text_lower = text.lower()
        if "<html" in text_lower or "<!doctype" in text_lower or "<body" in text_lower:
            return response.status_code, "[BLOCKED_HTML]", "HTML body blocked"
            
        if "application/json" in content_type or "json" in content_type:
            try:
                return response.status_code, response.json(), None
            except Exception as e:
                return response.status_code, text, f"Failed to parse JSON: {e}"
                
        return response.status_code, text, None

    except Exception as e:
        return 0, None, f"HTTP exception: {str(e)}"
