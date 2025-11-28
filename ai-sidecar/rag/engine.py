"""
RAG Engine for HomeSight

Manages document ingestion, vector storage, and retrieval for manufacturer manuals,
troubleshooting guides, and home maintenance documentation.
"""

import hashlib
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from functools import lru_cache
import logging
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

# Import metrics
from metrics import rag_retrieval_duration, rag_retrievals


class RAGEngine:
    """RAG engine using ChromaDB with FastEmbed for fully offline operation"""

    def __init__(self, persist_directory: str = "./rag-db"):
        """
        Initialize RAG engine with persistent storage and local FastEmbed embeddings

        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Query result cache (LRU cache for repeated queries)
        # Cache key: (query_text, n_results, where_clause_hash)
        # Improves performance for repeated queries (common in chat sessions)
        self._query_cache: Dict[Tuple[str, int, str], Tuple[List[Dict], float]] = {}
        self._query_cache_lock = threading.Lock()
        self._query_cache_max_size = 100  # Max cached queries
        self._query_cache_ttl = 300  # 5 minutes TTL

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False)
        )

        # Use FastEmbed for local, offline embeddings
        logger.info("Using FastEmbed for local embeddings (BAAI/bge-small-en-v1.5)...")
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        # ChromaDB's DefaultEmbeddingFunction uses sentence-transformers
        # For fastembed, we'll create a custom embedding function
        try:
            from fastembed import TextEmbedding

            class FastEmbedFunction:
                def __init__(self):
                    import os
                    # Try to use pre-cached model to avoid runtime downloads
                    cache_dir = os.environ.get("FASTEMBED_CACHE_PATH", None)
                    self.model = TextEmbedding(
                        model_name="BAAI/bge-small-en-v1.5",
                        cache_dir=cache_dir
                    )

                def __call__(self, input: List[str]) -> List[List[float]]:
                    embeddings = list(self.model.embed(input))
                    return embeddings

                def embed_query(self, input: List[str]) -> List[List[float]]:
                    """Alias for __call__ - required by ChromaDB 1.3+"""
                    return self.__call__(input)

                @staticmethod
                def name() -> str:
                    return "BAAI/bge-small-en-v1.5"

            self.embedding_function = FastEmbedFunction()
            logger.info("FastEmbed initialized successfully - fully offline operation enabled")

        except ImportError:
            logger.error("FastEmbed not installed. Install with: pip install fastembed")
            raise

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="homesight_docs",
            embedding_function=self.embedding_function,
            metadata={"description": "Home maintenance and device documentation"}
        )

        # Async processing support
        # Increased thread pool from 4 to 8 workers for better concurrency
        # ThreadPool is appropriate here because:
        # 1. FastEmbed releases GIL during embedding computation
        # 2. ChromaDB is thread-safe
        # 3. ProcessPool would require pickling complex objects (ChromaDB client)
        # 4. 8 threads can handle ~16-24 concurrent device ingestions
        import os
        max_workers = int(os.environ.get('RAG_MAX_WORKERS', '8'))
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="rag-worker")
        self._ingestion_lock = threading.Lock()
        self._ingestion_queue: asyncio.Queue = None
        self._ingestion_worker_task = None

        logger.info(f"RAG engine initialized with local embeddings (offline mode, {max_workers} workers)")
    
    def add_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None
    ):
        """Add a document to the vector database (synchronous - use for single docs)"""
        # Generate ID if not provided
        if doc_id is None:
            doc_id = f"doc_{hash(text)}"

        # Add to collection (ChromaDB handles embedding automatically)
        self.collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[doc_id]
        )

        logger.info(f"Added document: {doc_id} from {metadata.get('source', 'unknown')}")

    def add_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 10
    ):
        """
        Add multiple documents in batches (non-blocking)

        Args:
            documents: List of dicts with 'text', 'metadata', and optional 'doc_id'
            batch_size: Number of documents to process at once (default: 10)

        This method processes documents in batches to avoid memory exhaustion.
        Batching reduces the number of times the embedding model is loaded.
        """
        if not documents:
            return

        logger.info(f"Starting batched ingestion of {len(documents)} documents (batch_size={batch_size})")

        # Process in batches
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            texts = []
            metadatas = []
            ids = []

            for doc in batch:
                text = doc.get('text', '')
                metadata = doc.get('metadata', {})
                doc_id = doc.get('doc_id', f"doc_{hash(text)}")

                texts.append(text)
                metadatas.append(metadata)
                ids.append(doc_id)

            # Add batch to collection (ChromaDB batches embeddings internally)
            with self._ingestion_lock:
                self.collection.add(
                    documents=texts,
                    metadatas=metadatas,
                    ids=ids
                )

            logger.info(f"Ingested batch {i//batch_size + 1}/{(len(documents)-1)//batch_size + 1} ({len(batch)} docs)")

        # Update cached count after ingestion
        try:
            self._cached_count = self.collection.count()
        except:
            pass

        logger.info(f"Completed batched ingestion of {len(documents)} documents")

    async def add_documents_async(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 10
    ):
        """
        Add documents asynchronously without blocking the event loop

        Args:
            documents: List of dicts with 'text', 'metadata', and optional 'doc_id'
            batch_size: Number of documents to process at once

        This runs the CPU-intensive embedding work in a thread pool to keep
        the API responsive during document ingestion.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            self.add_documents_batch,
            documents,
            batch_size
        )
        logger.info(f"Async ingestion completed for {len(documents)} documents")
    
    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query for relevant documents with caching

        Returns documents with relevance scores (1 - distance).
        Higher relevance scores are better (closer to 1 = more relevant).

        Caching Strategy:
        - Cache key: (query_text, n_results, where_clause_hash)
        - TTL: 5 minutes
        - Max size: 100 queries
        - Thread-safe
        """
        start_time = time.time()
        status = "error"

        # Generate cache key
        where_hash = hashlib.md5(str(where).encode()).hexdigest() if where else "none"
        cache_key = (query_text, n_results, where_hash)

        # Check cache
        with self._query_cache_lock:
            if cache_key in self._query_cache:
                cached_results, cached_time = self._query_cache[cache_key]
                age = time.time() - cached_time

                if age < self._query_cache_ttl:
                    # Cache hit!
                    logger.debug(f"Query cache hit (age: {age:.1f}s)")
                    rag_retrievals.labels(status="cache_hit").inc()
                    return cached_results
                else:
                    # Expired - remove it
                    del self._query_cache[cache_key]

        try:
            # Cache miss - query collection (ChromaDB handles query embedding automatically)
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where
            )

            # Format results with relevance scores
            formatted_results = []
            for i in range(len(results['ids'][0])):
                distance = results['distances'][0][i] if 'distances' in results else 1.0
                # Convert distance to relevance (similarity)
                # Distance is typically 0-2, with 0 being identical
                # Convert to 0-1 scale where 1 is most relevant
                relevance = max(0.0, 1.0 - (distance / 2.0))

                formatted_results.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'distance': distance,
                    'relevance_score': relevance,
                })

            # Track status based on results
            if len(formatted_results) == 0:
                status = "empty"
            else:
                status = "success"

            # Cache the results
            with self._query_cache_lock:
                # Evict oldest if cache full (simple FIFO)
                if len(self._query_cache) >= self._query_cache_max_size:
                    oldest_key = next(iter(self._query_cache))
                    del self._query_cache[oldest_key]

                self._query_cache[cache_key] = (formatted_results, time.time())

            return formatted_results

        except Exception as e:
            status = "error"
            logger.error(f"RAG query failed: {e}")
            raise

        finally:
            # Track retrieval metrics
            duration = time.time() - start_time
            rag_retrieval_duration.observe(duration)
            rag_retrievals.labels(status=status).inc()

    def delete_device_docs(self, manufacturer: str, model: str) -> bool:
        """Delete all documents for a specific device from the RAG database"""
        try:
            # Use ChromaDB where clause to find and delete documents for this device
            where = {"$and": [{"manufacturer": manufacturer.title()}, {"model": model}]}
            # Get IDs to delete
            results = self.collection.get(where=where)
            if results and results.get('ids'):
                self.collection.delete(ids=results['ids'])
                logger.info(f"Deleted {len(results['ids'])} documents for {manufacturer} {model} from RAG")
                # Clear cached count
                if hasattr(self, '_cached_count'):
                    delattr(self, '_cached_count')
                return True
            else:
                logger.info(f"No documents found for {manufacturer} {model} in RAG")
                return False
        except Exception as e:
            logger.error(f"Error deleting documents for {manufacturer} {model}: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get RAG database statistics (non-blocking)"""
        try:
            # Try to get count without blocking too long
            # If ingestion is happening, this might be slow, so we cache it
            if hasattr(self, '_cached_count'):
                count = self._cached_count
            else:
                count = self.collection.count()
                self._cached_count = count
        except Exception as e:
            logger.warning(f"Error getting collection count: {e}")
            count = -1

        return {
            "total_documents": count,
            "persist_directory": str(self.persist_directory),
            "embedding_model": "BAAI/bge-small-en-v1.5 (FastEmbed - Local)",
            "collection_name": "homesight_docs"
        }


if __name__ == "__main__":
    # RAG engine can be tested with real documents via the ingest script
    print("Use ingest-docs.py to add manufacturer documentation to the RAG engine")
    print("Or use the /rag/ingest endpoint to add documents via API")
