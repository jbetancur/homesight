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

logger = logging.getLogger(__name__)


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
        logger.info("RAG engine initialized with local embeddings (offline mode)")
    
    def add_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None
    ):
        """Add a document to the vector database"""
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
        
        return formatted_results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG database statistics"""
        count = self.collection.count()
        return {
            "total_documents": count,
            "persist_directory": str(self.persist_directory),
            "embedding_model": "BAAI/bge-small-en-v1.5 (FastEmbed - Local)",
            "collection_name": "homesight_docs"
        }


def demo_rag():
    """Demo the RAG engine with sample documents"""
    engine = RAGEngine()
    
    # Add some sample docs
    sample_docs = [
        {
            "text": "Aqara SJCGQ11LM water leak sensor has a 2-year battery life. The LED indicator flashes when water is detected. Test monthly by applying water to the detection probe.",
            "metadata": {
                "source": "Aqara SJCGQ11LM Manual",
                "device_type": "water_leak",
                "manufacturer": "Aqara",
                "section": "operation"
            }
        },
        {
            "text": "For basement water leaks: 1) Immediately shut off the main water valve 2) Turn off electrical power to the affected area 3) Remove standing water 4) Contact a licensed plumber 5) Document damage with photos for insurance",
            "metadata": {
                "source": "Plumbing Emergency Guide",
                "topic": "leak_response",
                "category": "emergency"
            }
        },
        {
            "text": "Water heater T&P (temperature and pressure) valve leaks are common. Check if the valve is properly seated. If dripping continues, the valve may need replacement. This is a safety device - do not cap or plug it.",
            "metadata": {
                "source": "Water Heater Maintenance",
                "appliance": "water_heater",
                "issue": "leak"
            }
        },
        {
            "text": "IRC Section P2801.5 requires drain pans under water heaters in attic and basement installations. Pan must be at least 1.5 inches deep and drain to an approved location.",
            "metadata": {
                "source": "International Residential Code",
                "code": "IRC P2801.5",
                "topic": "water_heater",
                "category": "building_code"
            }
        },
        {
            "text": "Freeze protection: Pipes in unheated areas should be insulated with foam pipe insulation. During extreme cold, let faucets drip slightly and open cabinet doors to allow warm air circulation.",
            "metadata": {
                "source": "Winterization Guide",
                "topic": "freeze_prevention",
                "season": "winter"
            }
        }
    ]
    
    print("Adding sample documents...")
    for doc in sample_docs:
        engine.add_document(
            text=doc["text"],
            metadata=doc["metadata"]
        )
    
    # Test queries
    print("\n" + "="*60)
    print("Testing RAG retrieval:")
    print("="*60)
    
    queries = [
        "water leak in basement",
        "freeze protection for pipes",
        "water heater dripping",
        "building code requirements"
    ]
    
    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 40)
        results = engine.query(query, n_results=2)
        for i, result in enumerate(results, 1):
            print(f"\n{i}. Source: {result['metadata'].get('source', 'Unknown')}")
            print(f"   Text: {result['text'][:100]}...")
            print(f"   Relevance score: {1 - result['distance']:.3f}")
    
    # Show stats
    print("\n" + "="*60)
    stats = engine.get_stats()
    print(f"RAG Stats: {stats['total_documents']} documents indexed")
    print("="*60)


if __name__ == "__main__":
    demo_rag()
