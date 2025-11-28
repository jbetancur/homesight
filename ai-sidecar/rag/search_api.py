"""
Unified Web Search API for HomeSight
------------------------------------

Final v1.0 production version.

Features:
- Brave Search (primary, 2,000 req/mo)
- Bing Web Search (fallback)
- Rate limiting (1 req/sec)
- Brave 429 cooldown tracking
- Clean SearchResult model
- Strategy-based backend architecture
- High-level unified search() API
"""

import logging
import os
import httpx
import asyncio
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class SearchError(Exception):
    pass

class RateLimitError(SearchError):
    pass

class BraveCooldownError(SearchError):
    pass


# =============================================================================
# Models
# =============================================================================

@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    source: str     # e.g., "brave" or "bing"
    timestamp: datetime
    relevance_score: float = 0.0

    def __post_init__(self):
        if not self.url.startswith(("http://", "https://")):
            self.url = "https://" + self.url


# =============================================================================
# Brave Backend
# =============================================================================

class BraveBackend:
    """Raw Brave Search adapter + cooldown + throttling."""

    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    RATE_LIMIT_SECONDS = 1.0
    COOLDOWN_AFTER_429 = timedelta(minutes=2)

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key
        self._last_call_ts = 0.0
        self._cooldown_until: Optional[datetime] = None

    def available(self) -> bool:
        return bool(self.api_key)


    async def search(self, query: str, max_results: int) -> List[SearchResult]:
        if not self.api_key:
            raise SearchError("Brave API key missing")

        # Cooldown enforcement
        if self._cooldown_until and datetime.now() < self._cooldown_until:
            raise BraveCooldownError(
                f"Brave API in cooldown until {self._cooldown_until}"
            )

        # Throttle 1req/sec
        now = time.time()
        delta = now - self._last_call_ts
        if delta < self.RATE_LIMIT_SECONDS:
            await asyncio.sleep(self.RATE_LIMIT_SECONDS - delta)

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }

        params = {
            "q": query,
            "count": min(max_results, 20),
            "search_lang": "en",
            "result_filter": "web",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(self.ENDPOINT, headers=headers, params=params)

        self._last_call_ts = time.time()

        if resp.status_code == 429:
            # Initiate cooldown
            self._cooldown_until = datetime.now() + self.COOLDOWN_AFTER_429
            raise RateLimitError(f"Brave rate limit hit (429): {resp.text}")

        if resp.status_code != 200:
            raise SearchError(f"Brave returned {resp.status_code}: {resp.text}")

        data = resp.json()
        items = data.get("web", {}).get("results", [])
        results: List[SearchResult] = []

        for idx, item in enumerate(items):
            url = item.get("url") or item.get("link")
            if not url:
                continue

            score = 1.0 - (idx / max(len(items), 1))
            results.append(SearchResult(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("snippet", "") or item.get("description", ""),
                source="brave",
                timestamp=datetime.now(),
                relevance_score=score
            ))

        return results


# =============================================================================
# Bing Backend
# =============================================================================

class BingBackend:
    ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, max_results: int) -> List[SearchResult]:
        if not self.api_key:
            raise SearchError("Bing API key missing")

        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {
            "q": query,
            "count": min(max_results, 50),
            "responseFilter": "Webpages",
            "textDecorations": False,
            "textFormat": "Raw",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(self.ENDPOINT, headers=headers, params=params)

        if resp.status_code == 429:
            raise RateLimitError(f"Bing rate limit hit: {resp.text}")

        if resp.status_code != 200:
            raise SearchError(f"Bing returned {resp.status_code}: {resp.text}")

        data = resp.json()
        items = data.get("webPages", {}).get("value", [])
        results: List[SearchResult] = []

        for idx, item in enumerate(items):
            url = item.get("url")
            if not url:
                continue

            score = 1.0 - (idx / max(len(items), 1))
            results.append(SearchResult(
                url=url,
                title=item.get("name", ""),
                snippet=item.get("snippet", "") or "",
                source="bing",
                timestamp=datetime.now(),
                relevance_score=score,
            ))

        return results


# =============================================================================
# Unified high-level Search API
# =============================================================================

class SearchAPI:
    """
    High-level unified search service.
    Handles:
    - Brave primary
    - Bing fallback
    - Keyword boosting
    """

    def __init__(self):
        self.brave = BraveBackend(os.getenv("BRAVE_SEARCH_API_KEY"))
        self.bing = BingBackend(os.getenv("BING_SEARCH_API_KEY"))

    async def search(
        self,
        query: str,
        max_results: int = 10,
        domains: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[SearchResult]:

        full_query = self._build_query(query, domains)

        # 1. Brave first
        if self.brave.available():
            try:
                results = await self.brave.search(full_query, max_results)
                return self._boost(results, keywords or [])
            except RateLimitError as e:
                logger.warning(f"Brave rate limited: {e}")
            except BraveCooldownError:
                logger.warning("Brave in cooldown period")
            except Exception as e:
                logger.warning(f"Brave error: {e}")

        # 2. Bing fallback
        if self.bing.available():
            try:
                results = await self.bing.search(full_query, max_results)
                return self._boost(results, keywords or [])
            except Exception as e:
                logger.warning(f"Bing error: {e}")

        logger.error("No search backends available or all failed")
        return []

    # ------------------------------------------------------------
    # Utility Functions
    # ------------------------------------------------------------

    @staticmethod
    def _build_query(query: str, domains: Optional[List[str]]) -> str:
        if not domains:
            return query

        domain_expr = " OR ".join([f"site:{d}" for d in domains])
        return f"{query} ({domain_expr})"


    @staticmethod
    def _boost(results: List[SearchResult], keywords: List[str]) -> List[SearchResult]:
        for result in results:
            text = f"{result.url.lower()} {result.title.lower()} {result.snippet.lower()}"

            # PDF boost
            if ".pdf" in result.url.lower():
                result.relevance_score += 0.3

            # Keyword boosts
            for kw in keywords:
                if kw.lower() in text:
                    result.relevance_score += 0.2

            result.relevance_score = min(result.relevance_score, 1.0)

        return sorted(results, key=lambda r: r.relevance_score, reverse=True)


# =============================================================================
# Convenience function for manual discovery
# =============================================================================

async def search_for_manual(manufacturer: str, model: str) -> List[SearchResult]:
    api = SearchAPI()

    query = f"{manufacturer} {model} manual pdf documentation"

    keywords = [
        "manual", "pdf", "user guide", "datasheet", "installation"
    ]

    return await api.search(
        query=query,
        max_results=10,
        domains=None,
        keywords=keywords,
    )
