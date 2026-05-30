"""Local LLM Client — inference via OpenAI-compatible API (Rapid-MLX).

Connects to Rapid-MLX server at localhost:8000 (configurable via
config/lmstudio_config.json). Supports structured output via json_schema
response format.

Usage:
    from bet.api_clients.lmstudio_client import LMStudioClient
    client = LMStudioClient()
    response = client.generate("Analyze this match", system_prompt="You are a betting analyst")
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel

from bet.api_clients.base_client import _record_source_health
from bet.api_clients.rate_limiter import RateLimiter

T = TypeVar("T", bound=BaseModel)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class LMStudioNotAvailableError(Exception):
    """Raised when LM Studio server is not reachable."""
    pass


class LMStudioError(Exception):
    """Raised on LM Studio API errors."""
    pass


@dataclass
class LMStudioResponse:
    text: str
    parsed: Optional[Any] = None
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    latency_ms: int = 0


class LMStudioClient:
    def __init__(self):
        self.api_name = "lmstudio"

        # Load config
        self.config: Dict[str, Any] = {}
        config_file = PROJECT_ROOT / "config" / "lmstudio_config.json"
        if config_file.exists():
            self.config = json.loads(config_file.read_text(encoding="utf-8"))

        self.base_url = self.config.get("base_url", "http://localhost:8000/v1")
        self.model = self.config.get("model", "default")
        self.max_tokens = self.config.get("max_tokens", 32768)
        self.temperature = self.config.get("temperature", 0.3)
        self.timeout = self.config.get("timeout_seconds", 300)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay_seconds", 5.0)
        self.structured_output = self.config.get("structured_output", True)

        self.rate_limiter = RateLimiter()
        self.usage_dir = PROJECT_ROOT / "betting" / "data" / ".api_usage"
        self._configured = True

        # Health check on init if configured
        if self.config.get("health_check_on_init", True):
            if not self.health_check():
                self._configured = False

    def health_check(self) -> bool:
        """Check if LM Studio server is reachable."""
        try:
            resp = httpx.get(
                f"{self.base_url}/models",
                timeout=10.0
            )
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def _check_configured(self) -> None:
        if not self._configured:
            raise LMStudioNotAvailableError(
                f"LM Studio server not reachable at {self.base_url}. "
                "Ensure LM Studio is running with a model loaded."
            )

    def _track_usage(self, usage: Dict[str, int]) -> None:
        """Track token usage to daily log file."""
        if not self.config.get("usage_tracking", {}).get("enabled", True):
            return

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.usage_dir.mkdir(parents=True, exist_ok=True)
        usage_file = self.usage_dir / f"lmstudio_{date_str}.json"

        data = {"input_tokens": 0, "output_tokens": 0, "total_calls": 0, "total_latency_ms": 0}
        if usage_file.exists():
            try:
                data = json.loads(usage_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        data["input_tokens"] += usage.get("prompt_tokens", 0)
        data["output_tokens"] += usage.get("completion_tokens", 0)
        data["total_calls"] += 1
        data["total_latency_ms"] += usage.get("latency_ms", 0)

        usage_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _build_messages(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Build OpenAI-style messages array."""
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if context:
            context_text = "\n\n---\n\n".join(context)
            user_content = f"## Context\n\n{context_text}\n\n---\n\n## Task\n\n{prompt}"
        else:
            user_content = prompt

        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_response_format(
        self, response_schema: Optional[Type[BaseModel]]
    ) -> Optional[Dict[str, Any]]:
        """Build json_schema response format from Pydantic model."""
        if not response_schema or not self.structured_output:
            return None

        schema = response_schema.model_json_schema()
        return {
            "type": "json_schema",
            "json_schema": {
                "name": response_schema.__name__,
                "strict": True,
                "schema": schema,
            },
        }

    def _extract_json_from_text(self, text: str) -> Optional[str]:
        """Fallback: extract JSON from markdown code blocks or raw text."""
        # Try ```json ... ``` blocks
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try raw JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        return None

    def _parse_response(
        self,
        resp_json: Dict[str, Any],
        start_time: float,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LMStudioResponse:
        """Parse OpenAI-compatible response into LMStudioResponse."""
        latency = int((time.time() - start_time) * 1000)

        choice = resp_json.get("choices", [{}])[0]
        text = choice.get("message", {}).get("content", "")
        model = resp_json.get("model", self.model)

        usage = resp_json.get("usage", {})
        usage["latency_ms"] = latency

        parsed = None
        if response_schema and text:
            # Try direct JSON parse
            try:
                parsed = response_schema.model_validate_json(text)
            except Exception:
                # Fallback: extract JSON from text
                extracted = self._extract_json_from_text(text)
                if extracted:
                    try:
                        parsed = response_schema.model_validate_json(extracted)
                    except Exception:
                        pass

        self._track_usage(usage)

        return LMStudioResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            model=model,
            latency_ms=latency,
        )

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: Optional[str] = None,
        response_schema: Optional[Type[BaseModel]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LMStudioResponse:
        """Generate a completion from LM Studio.

        Args:
            prompt: User message content.
            system_prompt: System message (optional).
            model: Override model name (optional).
            response_schema: Pydantic model for structured JSON output.
            temperature: Override temperature.
            max_tokens: Override max tokens.

        Returns:
            LMStudioResponse with text, parsed output, and usage stats.
        """
        self._check_configured()

        messages = self._build_messages(prompt, system_prompt)
        response_format = self._build_response_format(response_schema)

        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.timeout,
                )

                if resp.status_code != 200:
                    error_text = resp.text[:500]
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    raise LMStudioError(
                        f"LM Studio returned {resp.status_code}: {error_text}"
                    )

                result = self._parse_response(
                    resp.json(), start_time, response_schema
                )
                _record_source_health("lmstudio", True)
                return result

            except httpx.TimeoutException:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                _record_source_health("lmstudio", False)
                raise LMStudioError(
                    f"LM Studio timeout after {self.timeout}s (attempt {attempt + 1})"
                )
            except httpx.ConnectError:
                _record_source_health("lmstudio", False)
                raise LMStudioNotAvailableError(
                    f"Cannot connect to LM Studio at {self.base_url}"
                )

        raise LMStudioError("Max retries exceeded")

    def generate_with_context(
        self,
        prompt: str,
        context: List[str],
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LMStudioResponse:
        """Generate with additional context (e.g., search results).

        Same as generate() but prepends context sections into the user message.
        Used as the synthesis step after Brave Search fetches results.
        """
        self._check_configured()

        messages = self._build_messages(prompt, system_prompt, context)
        response_format = self._build_response_format(response_schema)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.timeout,
                )

                if resp.status_code != 200:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    raise LMStudioError(
                        f"LM Studio returned {resp.status_code}: {resp.text[:500]}"
                    )

                result = self._parse_response(
                    resp.json(), start_time, response_schema
                )
                _record_source_health("lmstudio", True)
                return result

            except httpx.TimeoutException:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                _record_source_health("lmstudio", False)
                raise LMStudioError(
                    f"LM Studio timeout after {self.timeout}s (attempt {attempt + 1})"
                )
            except httpx.ConnectError:
                _record_source_health("lmstudio", False)
                raise LMStudioNotAvailableError(
                    f"Cannot connect to LM Studio at {self.base_url}"
                )

        raise LMStudioError("Max retries exceeded")
