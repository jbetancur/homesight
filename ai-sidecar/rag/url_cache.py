"""
Dynamic documentation URL discovery and caching system.

Instead of maintaining a static database, this system uses OpenAI to discover
documentation URLs on first encounter, then caches them locally for fast retrieval.

Cache format: ~/.homesight/doc_urls.json
{
  "Aqara:SJCGQ11LM": {
    "url": "https://cdn.aqara.com/...",
    "discovered_at": "2025-11-23T...",
    "confidence": "high"
  }
}
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class URLCache:
    """Persistent cache of discovered documentation URLs"""

    def __init__(self, cache_file: Path = None):
        if cache_file is None:
            cache_file = Path.home() / ".homesight" / "doc_urls.json"

        self.cache_file = cache_file
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from disk"""
        if self.cache_file.exists():
            try:
                return json.loads(self.cache_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load URL cache: {e}")
                return {}
        return {}

    def _save_cache(self):
        """Persist cache to disk"""
        try:
            self.cache_file.write_text(json.dumps(self._cache, indent=2))
        except Exception as e:
            logger.error(f"Failed to save URL cache: {e}")

    def get_device_key(self, manufacturer: str, model: str) -> str:
        """Generate cache key for device"""
        return f"{manufacturer}:{model}".strip()

    def get(self, manufacturer: str, model: str) -> Optional[str]:
        """Retrieve cached documentation URL"""
        key = self.get_device_key(manufacturer, model)
        entry = self._cache.get(key)
        if entry:
            logger.info(f"URL cache hit for {key}: {entry['url']}")
            return entry.get("url")
        return None

    def set(self, manufacturer: str, model: str, url: str, confidence: str = "medium"):
        """Cache a discovered documentation URL"""
        key = self.get_device_key(manufacturer, model)
        self._cache[key] = {
            "url": url,
            "discovered_at": datetime.utcnow().isoformat(),
            "confidence": confidence,
        }
        self._save_cache()
        logger.info(f"Cached URL for {key}: {url}")

    def has(self, manufacturer: str, model: str) -> bool:
        """Check if URL is cached"""
        key = self.get_device_key(manufacturer, model)
        return key in self._cache

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "total_entries": len(self._cache),
            "cache_file": str(self.cache_file),
        }
