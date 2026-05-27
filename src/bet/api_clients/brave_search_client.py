"""Brave Search Client — web search for Python scripts.

Replaces Gemini's native search grounding with Brave Search API + LMStudio synthesis.
Two-step pattern: Brave fetches results → LMStudio synthesizes into structured data.

Usage:
    from bet.api_clients.brave_search_client import BraveSearchClient
    client = BraveSearchClient()
    results = client.search("Arsenal injuries May 2026")
    summary = client.search_and_summarize("Arsenal injuries", lmstudio_client, system_prompt="...")
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel

from bet.api_clients.base_client import _record_source_health
from bet.api_clients.rate_limiter import RateLimiter

T = TypeVar("T", bound=BaseModel)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
BRAVE_API_BASE = "https://api.search.brave.com/res/v1"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    age: str = ""


@dataclass
class NewsResult:
    title: str
    url: str
    description: str
    age: str = ""
    source: str = ""


class BraveSearchNotConfiguredError(Exception):
    pass


class BraveSearchError(Exception):
    pass


class BraveSearchClient:
    def __init__(self):
        self.api_name = "brave-search-api"

        # Load API key
        self.api_key = os.environ.get("BRAVE_API_KEY")
        if not self.api_key:
            keys_file = PROJECT_ROOT / "config" / "api_keys.json"
            if keys_file.exists():
                try:
                    keys = json.loads(keys_file.read_text(encoding="utf-8"))
                    self.api_key = keys.get("brave_search") or keys.get("brave-search")
                except Exception:
                    pass

        if not self.api_key:
            raise BraveSearchNotConfiguredError(
                "Brave Search API key not found. Set BRAVE_API_KEY env var or add to config/api_keys.json"
            )

        self.rate_limiter = RateLimiter()
        self._headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

    def search(
        self,
        query: str,
        count: int = 5,
        freshness: Optional[str] = "pw",
    ) -> List[SearchResult]:
        """Web search via Brave Search API.

        Args:
            query: Search query string.
            count: Number of results (max 20).
            freshness: Time filter — "pd" (past day), "pw" (past week), "pm" (past month), None (all time).

        Returns:
            List of SearchResult with title, url, snippet.
        """
        if not self.rate_limiter.can_request(self.api_name):
            raise BraveSearchError("Brave Search daily quota exceeded")

        params: Dict[str, Any] = {"q": query, "count": min(count, 20)}
        if freshness:
            params["freshness"] = freshness

        try:
            resp = httpx.get(
                f"{BRAVE_API_BASE}/web/search",
                headers=self._headers,
                params=params,
                timeout=15.0,
            )

            if resp.status_code != 200:
                _record_source_health(self.api_name, False)
                raise BraveSearchError(f"Brave Search returned {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            _record_source_health(self.api_name, True)

            results = []
            for item in data.get("web", {}).get("results", []):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                    age=item.get("age", ""),
                ))
            return results

        except httpx.TimeoutException:
            _record_source_health(self.api_name, False)
            raise BraveSearchError(f"Brave Search timeout for query: {query[:80]}")
        except httpx.ConnectError:
            _record_source_health(self.api_name, False)
            raise BraveSearchError("Cannot connect to Brave Search API")

    def news_search(
        self,
        query: str,
        count: int = 5,
        freshness: Optional[str] = "pd",
    ) -> List[NewsResult]:
        """News search via Brave Search API.

        Args:
            query: Search query string.
            count: Number of results (max 20).
            freshness: "pd" (past day), "pw" (past week).

        Returns:
            List of NewsResult.
        """
        if not self.rate_limiter.can_request(self.api_name):
            raise BraveSearchError("Brave Search daily quota exceeded")

        params: Dict[str, Any] = {"q": query, "count": min(count, 20)}
        if freshness:
            params["freshness"] = freshness

        try:
            resp = httpx.get(
                f"{BRAVE_API_BASE}/news/search",
                headers=self._headers,
                params=params,
                timeout=15.0,
            )

            if resp.status_code != 200:
                _record_source_health(self.api_name, False)
                raise BraveSearchError(f"Brave News returned {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            _record_source_health(self.api_name, True)

            results = []
            for item in data.get("results", []):
                results.append(NewsResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    description=item.get("description", ""),
                    age=item.get("age", ""),
                    source=item.get("meta_url", {}).get("hostname", ""),
                ))
            return results

        except httpx.TimeoutException:
            _record_source_health(self.api_name, False)
            raise BraveSearchError(f"Brave News timeout for query: {query[:80]}")
        except httpx.ConnectError:
            _record_source_health(self.api_name, False)
            raise BraveSearchError("Cannot connect to Brave Search API")

    def search_and_summarize(
        self,
        query: str,
        lmstudio_client: Any,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
        count: int = 5,
        freshness: Optional[str] = "pw",
    ) -> Any:
        """Two-step search grounding replacement: Brave Search → LMStudio synthesis.

        This is the direct replacement for Gemini's search_grounded_query().
        1. Fetch web results via Brave Search
        2. Feed results as context to LMStudio for structured synthesis

        Args:
            query: Search query.
            lmstudio_client: LMStudioClient instance for synthesis.
            system_prompt: System prompt for synthesis.
            response_schema: Pydantic model for structured output.
            count: Number of search results to fetch.
            freshness: Time filter for results.

        Returns:
            LMStudioResponse (with .parsed if response_schema provided).
        """
        # Step 1: Fetch search results
        results = self.search(query, count=count, freshness=freshness)

        if not results:
            # Try without freshness filter
            results = self.search(query, count=count, freshness=None)

        # Format results as context
        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(
                f"[{i}] {r.title}\nURL: {r.url}\n{r.snippet}"
            )

        # Step 2: Synthesize with LMStudio
        synthesis_prompt = (
            f"Based on the search results provided as context, answer this query:\n\n"
            f"{query}\n\n"
            f"Synthesize the information from the search results into a structured response. "
            f"Only include facts that are supported by the search results."
        )

        return lmstudio_client.generate_with_context(
            prompt=synthesis_prompt,
            context=context_parts,
            system_prompt=system_prompt,
            response_schema=response_schema,
        )

    def news_and_summarize(
        self,
        query: str,
        lmstudio_client: Any,
        system_prompt: str = "",
        response_schema: Optional[Type[BaseModel]] = None,
        count: int = 5,
    ) -> Any:
        """Two-step news grounding: Brave News → LMStudio synthesis."""
        results = self.news_search(query, count=count)

        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(
                f"[{i}] {r.title} ({r.source}, {r.age})\n{r.description}"
            )

        synthesis_prompt = (
            f"Based on the news articles provided as context, answer this query:\n\n"
            f"{query}\n\n"
            f"Extract relevant facts from the news. Only include confirmed information."
        )

        return lmstudio_client.generate_with_context(
            prompt=synthesis_prompt,
            context=context_parts,
            system_prompt=system_prompt,
            response_schema=response_schema,
        )
