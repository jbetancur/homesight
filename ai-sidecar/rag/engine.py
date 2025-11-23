"""
RAG Engine for HomeSight

Manages document ingestion, vector storage, and retrieval for manufacturer manuals,
troubleshooting guides, and home maintenance documentation.
"""

import hashlib
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from pathlib import Path
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

    def __init__(self, persist_directory: str = "./rag-db", openai_api_key: Optional[str] = None):
        """
        Initialize RAG engine with persistent storage and local FastEmbed embeddings

        Note: openai_api_key parameter kept for backwards compatibility but not used for embeddings.
        OpenAI may still be used elsewhere (e.g., document fetching).
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

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
                    # Use BAAI/bge-small-en-v1.5 - lightweight and efficient
                    self.model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

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
        # Use 4 workers to handle concurrent embedding operations without blocking API
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rag-worker")
        self._ingestion_lock = threading.Lock()
        self._ingestion_queue: asyncio.Queue = None
        self._ingestion_worker_task = None

        logger.info("RAG engine initialized with local embeddings (offline mode)")
    
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
        Query for relevant documents

        Returns documents with relevance scores (1 - distance).
        Higher relevance scores are better (closer to 1 = more relevant).
        """
        start_time = time.time()
        status = "error"

        try:
            # Query collection (ChromaDB handles query embedding automatically)
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
