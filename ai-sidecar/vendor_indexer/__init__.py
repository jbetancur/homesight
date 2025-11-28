"""
Vendor Document Indexer

Persistent background indexing system for manufacturer documentation.

This module provides:
- Manufacturer-specific domain crawling
- PDF and manual URL collection
- Persistent storage (SQLite)
- Scheduled refresh (weekly)
- Fast lookup by manufacturer + model

This becomes the TIER 1 discovery mechanism, checked before web search.
"""

from .storage import VendorDocumentStorage, IndexedDocument
from .crawler import VendorCrawler
from .scheduler import VendorIndexScheduler, get_scheduler, start_background_indexer, stop_background_indexer

__all__ = [
    "VendorDocumentStorage",
    "IndexedDocument",
    "VendorCrawler",
    "VendorIndexScheduler",
    "get_scheduler",
    "start_background_indexer",
    "stop_background_indexer",
]
