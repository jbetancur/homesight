"""
Protocol definitions for RAG components

Defines interfaces for dependency injection and unit testing.
Use these protocols to type-hint dependencies and create mocks.

Example:
    def my_service(rag: RAGEngineProtocol):
        # Works with real RAGEngine or mock
        results = rag.query("test query")
"""

from typing import Protocol, List, Dict, Any, Optional, runtime_checkable
from dataclasses import dataclass
from datetime import datetime


@runtime_checkable
class RAGEngineProtocol(Protocol):
    """
    Protocol for RAG engine implementations.
    
    Allows swapping RAGEngine for mocks in unit tests.
    """
    
    def add_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> None:
        """Add a single document to the vector database."""
        ...
    
    def add_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 10
    ) -> None:
        """Add multiple documents in batches."""
        ...
    
    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        apply_ranking: bool = True
    ) -> List[Dict[str, Any]]:
        """Query for relevant documents."""
        ...
    
    def delete_device_docs(self, manufacturer: str, model: str) -> bool:
        """Delete all documents for a specific device."""
        ...
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG database statistics."""
        ...


@runtime_checkable  
class SearchBackendProtocol(Protocol):
    """
    Protocol for search API backends (Brave, Bing, etc.).
    
    Enables testing without real API calls.
    """
    
    def available(self) -> bool:
        """Check if this backend is configured and available."""
        ...
    
    async def search(
        self,
        query: str,
        max_results: int
    ) -> List["SearchResult"]:
        """Execute a search query."""
        ...


@dataclass
class SearchResult:
    """
    Standard search result from any backend.
    
    This is the canonical model - backends convert their
    native responses to this format.
    """
    url: str
    title: str
    snippet: str
    source: str  # Backend name: "brave", "bing", etc.
    timestamp: datetime
    relevance_score: float = 0.0
    
    def __post_init__(self):
        """Ensure URL has protocol."""
        if not self.url.startswith(("http://", "https://")):
            self.url = "https://" + self.url


@runtime_checkable
class DocumentFetcherProtocol(Protocol):
    """
    Protocol for document fetchers.
    
    Enables testing document ingestion without network calls.
    """
    
    async def fetch_for_device(
        self,
        device: Any,
        force: bool = False
    ) -> bool:
        """Fetch and ingest documentation for a device."""
        ...


@runtime_checkable
class URLCacheProtocol(Protocol):
    """
    Protocol for URL caching.
    
    Enables testing without filesystem access.
    """
    
    def get(self, manufacturer: str, model: str) -> Optional[str]:
        """Get cached URL for a device."""
        ...
    
    def set(
        self,
        manufacturer: str,
        model: str,
        url: str,
        confidence: str = "medium"
    ) -> None:
        """Cache a discovered URL."""
        ...
    
    def has(self, manufacturer: str, model: str) -> bool:
        """Check if URL is cached."""
        ...


class MockRAGEngine:
    """
    Mock RAG engine for unit testing.
    
    Usage:
        def test_my_service():
            mock_rag = MockRAGEngine()
            mock_rag.set_query_results([
                {"text": "test doc", "relevance_score": 0.9}
            ])
            
            service = MyService(rag=mock_rag)
            result = service.do_something()
            
            assert mock_rag.query_count == 1
    """
    
    def __init__(self):
        self.documents: List[Dict[str, Any]] = []
        self.query_results: List[Dict[str, Any]] = []
        self.query_count = 0
        self.add_count = 0
        self.last_query: Optional[str] = None
        self.last_where: Optional[Dict] = None
    
    def set_query_results(self, results: List[Dict[str, Any]]):
        """Set results to return for next query."""
        self.query_results = results
    
    def add_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> None:
        self.documents.append({
            "text": text,
            "metadata": metadata,
            "doc_id": doc_id
        })
        self.add_count += 1
    
    def add_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 10
    ) -> None:
        self.documents.extend(documents)
        self.add_count += len(documents)
    
    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        apply_ranking: bool = True
    ) -> List[Dict[str, Any]]:
        self.query_count += 1
        self.last_query = query_text
        self.last_where = where
        return self.query_results[:n_results]
    
    def delete_device_docs(self, manufacturer: str, model: str) -> bool:
        before = len(self.documents)
        self.documents = [
            d for d in self.documents 
            if not (
                d.get("metadata", {}).get("manufacturer") == manufacturer and
                d.get("metadata", {}).get("model") == model
            )
        ]
        return len(self.documents) < before
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_documents": len(self.documents),
            "query_count": self.query_count,
            "add_count": self.add_count
        }


class MockURLCache:
    """Mock URL cache for testing."""
    
    def __init__(self):
        self._cache: Dict[str, str] = {}
    
    def get(self, manufacturer: str, model: str) -> Optional[str]:
        key = f"{manufacturer}:{model}"
        return self._cache.get(key)
    
    def set(
        self,
        manufacturer: str,
        model: str,
        url: str,
        confidence: str = "medium"
    ) -> None:
        key = f"{manufacturer}:{model}"
        self._cache[key] = url
    
    def has(self, manufacturer: str, model: str) -> bool:
        key = f"{manufacturer}:{model}"
        return key in self._cache
