"""
RAG Engine for HomeSight

Manages document ingestion, vector storage, and retrieval for manufacturer manuals,
troubleshooting guides, and home maintenance documentation.
"""

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class RAGEngine:
    """RAG engine using ChromaDB and sentence transformers"""
    
    def __init__(self, persist_directory: str = "./rag-db"):
        """Initialize RAG engine with persistent storage"""
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Initialize embedding model
        logger.info("Loading embedding model...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Embedding model loaded")
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="homesight_docs",
            metadata={"description": "Home maintenance and device documentation"}
        )
    
    def add_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None
    ):
        """Add a document to the vector database"""
        # Generate embedding
        embedding = self.embedding_model.encode(text).tolist()
        
        # Generate ID if not provided
        if doc_id is None:
            doc_id = f"doc_{hash(text)}"
        
        # Add to collection
        self.collection.add(
            embeddings=[embedding],
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
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query_text).tolist()
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
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
            "embedding_model": "all-MiniLM-L6-v2",
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
