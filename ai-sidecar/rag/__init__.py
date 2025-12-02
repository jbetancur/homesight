"""RAG components for document retrieval and ingestion"""

from .engine import RAGEngine
from .fetcher import DocumentAutoFetcher, LLMDocumentFinder
from .document_ranker import DocumentRanker, get_ranker
from .validation_config import (
    DocumentValidationConfig,
    DeviceCategory,
    ManufacturerInfo,
    get_validation_config,
)
from .utils import (
    normalize_manufacturer,
    normalize_manufacturer_key,
    get_device_key,
    build_chromadb_where,
    chunk_text,
)
from .http_client import get_client, url_exists, download_content, fetch_text, Timeouts
from .protocols import (
    RAGEngineProtocol,
    SearchBackendProtocol,
    DocumentFetcherProtocol,
    URLCacheProtocol,
    MockRAGEngine,
    MockURLCache,
)

__all__ = [
    # Core components
    "RAGEngine",
    "DocumentAutoFetcher",
    "LLMDocumentFinder",
    "DocumentRanker",
    "get_ranker",
    # Validation config
    "DocumentValidationConfig",
    "DeviceCategory",
    "ManufacturerInfo",
    "get_validation_config",
    # Utilities
    "normalize_manufacturer",
    "normalize_manufacturer_key", 
    "get_device_key",
    "build_chromadb_where",
    "chunk_text",
    # HTTP client
    "get_client",
    "url_exists",
    "download_content",
    "fetch_text",
    "Timeouts",
    # Protocols for testing
    "RAGEngineProtocol",
    "SearchBackendProtocol",
    "DocumentFetcherProtocol",
    "URLCacheProtocol",
    "MockRAGEngine",
    "MockURLCache",
]
