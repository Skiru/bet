import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

from scripts.api_clients.base_client import _record_source_health
from scripts.api_clients.rate_limiter import RateLimiter

try:
    from google import genai
    from google.genai import types
    has_genai = True
except ImportError:
    has_genai = False

T = TypeVar("T", bound=BaseModel)

class GeminiNotConfiguredError(Exception):
    pass

class GeminiError(Exception):
    pass

@dataclass
class GeminiResponse:
    text: str
    parsed: Optional[Any] = None
    thoughts: Optional[str] = None
    search_results: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    latency_ms: int = 0


class GeminiClient:
    def __init__(self):
        self.api_name = "gemini"
        
        # Load API key
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            keys_file = Path("config/api_keys.json")
            if keys_file.exists():
                try:
                    keys = json.loads(keys_file.read_text(encoding="utf-8"))
                    self.api_key = keys.get(self.api_name)
                except Exception:
                    pass
        
        # Load Config
        self.config = {}
        config_file = Path("config/gemini_config.json")
        if config_file.exists():
            try:
                self.config = json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        self.default_model = self.config.get("default_model", "gemini-2.5-flash")
        self.deep_analysis_model = self.config.get("deep_analysis_model", "gemini-2.5-pro")
        self.max_retries = self.config.get("max_retries", 3)
        self.rate_limit_delay = self.config.get("rate_limit_delay_seconds", 4.0)
        
        # Not configured check
        if not has_genai or not self.api_key:
            self._configured = False
        else:
            self._configured = True
            self.client = genai.Client(api_key=self.api_key)
            
        self.rate_limiter = RateLimiter()
        self.usage_dir = Path("betting/data/.api_usage")

    def _check_configured(self):
        if not self._configured:
            raise GeminiNotConfiguredError("Gemini package not installed or API key missing.")

    def _track_cost(self, usage: Dict[str, int]) -> None:
        if not self.config.get("cost_tracking", {}).get("enabled", True):
            return
            
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cost_file = self.usage_dir / f"gemini_{date_str}.json"
        self.usage_dir.mkdir(parents=True, exist_ok=True)
        
        data = {"input_tokens": 0, "output_tokens": 0, "total_calls": 0}
        if cost_file.exists():
            try:
                data = json.loads(cost_file.read_text(encoding="utf-8"))
            except Exception:
                pass
                
        data["input_tokens"] += usage.get("promptTokenCount", 0)
        data["output_tokens"] += usage.get("candidatesTokenCount", 0)
        data["total_calls"] += 1
        
        cost_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _check_budget(self):
        # We rely on existing RateLimiter for requests budget 
        self.rate_limiter.check_limit("gemini")

    def _parse_response(self, response: Any, start_time: float, model: str, response_schema: Optional[Type[BaseModel]] = None) -> GeminiResponse:
        latency = int((time.time() - start_time) * 1000)
        
        usage = {
            "promptTokenCount": getattr(response.usage_metadata, "prompt_token_count", 0),
            "candidatesTokenCount": getattr(response.usage_metadata, "candidates_token_count", 0),
            "totalTokenCount": getattr(response.usage_metadata, "total_token_count", 0),
        }
        
        text = response.text if hasattr(response, "text") else ""
        
        # Parse search results
        search_results = []
        if getattr(response, "candidates", None) and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if getattr(candidate, "grounding_metadata", None):
                gm = candidate.grounding_metadata
                if getattr(gm, "grounding_chunks", None):
                    for chunk in gm.grounding_chunks:
                        if getattr(chunk, "web", None):
                            search_results.append({
                                "title": getattr(chunk.web, "title", ""),
                                "uri": getattr(chunk.web, "uri", ""),
                            })
                            
        parsed_out = None
        if response_schema and text:
            try:
                parsed_out = response_schema.model_validate_json(text)
            except Exception as e:
                pass
                
        # Parse thinking thoughts if available
        thoughts = None
        if getattr(response, "parts", None):
            for p in response.parts:
                if getattr(p, "thought", None):
                    thoughts = p.text

        self._track_cost(usage)
            
        return GeminiResponse(
            text=text,
            parsed=parsed_out,
            thoughts=thoughts,
            search_results=search_results,
            usage=usage,
            model=model,
            latency_ms=latency
        )

    def generate(self, prompt: str, model: Optional[str] = None, response_schema: Optional[Type[BaseModel]] = None) -> GeminiResponse:
        self._check_configured()
        self._check_budget()
        
        target_model = model or self.default_model
        
        config_kwargs = {}
        if response_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema
            
        gen_config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
        
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                response = self.client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=gen_config
                )
                
                _record_source_health(self.api_name, True)
                return self._parse_response(response, start_time, target_model, response_schema)
                
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "503" in err_str:
                    time.sleep(self.rate_limit_delay * (attempt + 1))
                    continue
                if "400" in err_str or "401" in err_str:
                    _record_source_health(self.api_name, False)
                    raise GeminiError(f"API Error: {err_str}") from e
                    
                _record_source_health(self.api_name, False)
                raise GeminiError(f"Generation failed: {str(e)}") from e
                
        _record_source_health(self.api_name, False)
        raise GeminiError("Max retries exceeded")

    def search_grounded_query(self, prompt: str, model: Optional[str] = None) -> GeminiResponse:
        self._check_configured()
        self.rate_limiter.check_limit("gemini-search")
        
        target_model = model or self.default_model
        gen_config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
        
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                response = self.client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=gen_config
                )
                
                _record_source_health(self.api_name, True)
                return self._parse_response(response, start_time, target_model)
                
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "503" in err_str:
                    time.sleep(self.rate_limit_delay * (attempt + 1))
                    continue
                if "400" in err_str or "401" in err_str:
                    _record_source_health(self.api_name, False)
                    raise GeminiError(f"API Error: {err_str}")
                    
                _record_source_health(self.api_name, False)
                raise GeminiError(f"Search query failed: {str(e)}")
                
        raise GeminiError("Max retries exceeded")

    def read_url(self, url: str, prompt: str, model: Optional[str] = None, response_schema: Optional[Type[BaseModel]] = None) -> GeminiResponse:
        self._check_configured()
        self._check_budget()
        
        target_model = model or self.default_model
        
        config_kwargs = {}
        if response_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema
            
        gen_config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
        
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                contents = [
                    types.Part.from_uri(uri=url, mime_type="text/plain"),
                    prompt
                ]
                # If from_uri fails or needs specific format, we will gracefully fallback to prompt
                response = self.client.models.generate_content(
                    model=target_model,
                    contents=contents,
                    config=gen_config
                )
                
                _record_source_health(self.api_name, True)
                return self._parse_response(response, start_time, target_model, response_schema)
                
            except Exception as e:
                err_str = str(e)
                # Google GenAI might not support arbitrary URIs unless uploaded 
                # Let's fallback to prompt inclusion if URI part fails
                try:
                    start_time = time.time()
                    fallback_prompt = f"URL Context: {url}\n\n{prompt}"
                    response = self.client.models.generate_content(
                        model=target_model,
                        contents=fallback_prompt,
                        config=gen_config
                    )
                    _record_source_health(self.api_name, True)
                    return self._parse_response(response, start_time, target_model, response_schema)
                except Exception as e_fallback:
                    err_str = str(e_fallback)
                    if "429" in err_str or "503" in err_str:
                        time.sleep(self.rate_limit_delay * (attempt + 1))
                        continue
                    if "400" in err_str or "401" in err_str:
                        _record_source_health(self.api_name, False)
                        raise GeminiError(f"API Error: {err_str}")
                    
                    _record_source_health(self.api_name, False)
                    raise GeminiError(f"URL read failed: {str(e)}")
                
        raise GeminiError("Max retries exceeded")

    def get_usage_report(self) -> Dict[str, Any]:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cost_file = self.usage_dir / f"gemini_{date_str}.json"
        if not cost_file.exists():
            return {"input_tokens": 0, "output_tokens": 0, "total_calls": 0}
        return json.loads(cost_file.read_text(encoding="utf-8"))
