"""
Home Memory Layer

Stores and retrieves home preferences, behaviors, and history using:
- SQLite for structured data
- ChromaDB for semantic search via embeddings
"""

import logging
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid

from .types import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)


class HomeMemoryService:
    """
    Manages long-term memory for the home intelligence layer.

    Uses:
    - SQLite for structured storage
    - ChromaDB (via existing RAG engine) for semantic search
    """

    def __init__(
        self,
        db_path: str = "/var/lib/homesight/hsil_memory.db",
        chroma_client=None
    ):
        self.db_path = db_path
        self.chroma_client = chroma_client
        self.collection_name = "home_memory"

        # Initialize SQLite
        self._init_db()

        # Initialize ChromaDB collection
        if self.chroma_client:
            try:
                self.collection = self.chroma_client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"description": "HomeSight long-term memory"}
                )
                logger.info(f"ChromaDB collection '{self.collection_name}' ready")
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB collection: {e}")
                self.collection = None
        else:
            self.collection = None
            logger.warning("ChromaDB client not provided, semantic search disabled")

        logger.info(f"HomeMemoryService initialized with db_path={db_path}")

    def _init_db(self):
        """Initialize SQLite database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,  -- JSON
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_entries(type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_entries(created_at DESC)
        """)

        conn.commit()
        conn.close()

        logger.info("SQLite memory database initialized")

    async def store(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None
    ) -> MemoryEntry:
        """
        Store a memory entry.

        Args:
            content: Text content of the memory
            memory_type: Type of memory
            metadata: Additional metadata
            embedding: Optional pre-computed embedding

        Returns:
            Created MemoryEntry
        """
        entry_id = str(uuid.uuid4())
        now = datetime.now()

        import json

        # Store in SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO memory_entries (id, type, content, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry_id,
            memory_type.value,
            content,
            json.dumps(metadata or {}),
            now.isoformat(),
            now.isoformat()
        ))

        conn.commit()
        conn.close()

        # Store in ChromaDB for semantic search
        if self.collection and embedding:
            try:
                self.collection.add(
                    ids=[entry_id],
                    documents=[content],
                    embeddings=[embedding],
                    metadatas=[{
                        "type": memory_type.value,
                        "created_at": now.isoformat(),
                        **(metadata or {})
                    }]
                )
            except Exception as e:
                logger.error(f"Failed to store embedding in ChromaDB: {e}")

        entry = MemoryEntry(
            id=entry_id,
            type=memory_type,
            content=content,
            embedding=embedding,
            metadata=metadata or {},
            created_at=now,
            updated_at=now
        )

        logger.info(f"Stored memory entry: type={memory_type.value}, id={entry_id}")

        return entry

    async def search_semantic(
        self,
        query: str,
        query_embedding: List[float],
        limit: int = 5,
        memory_type: Optional[MemoryType] = None
    ) -> List[MemoryEntry]:
        """
        Search memory using semantic similarity.

        Args:
            query: Search query text
            query_embedding: Query embedding
            limit: Maximum results
            memory_type: Filter by memory type

        Returns:
            List of matching MemoryEntry objects
        """
        if not self.collection:
            logger.warning("ChromaDB not available, falling back to keyword search")
            return await self.search_keyword(query, limit, memory_type)

        try:
            # Build where clause for filtering
            where_clause = None
            if memory_type:
                where_clause = {"type": memory_type.value}

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_clause
            )

            # Convert results to MemoryEntry objects
            entries = []
            if results and results.get("ids") and len(results["ids"]) > 0:
                for i, entry_id in enumerate(results["ids"][0]):
                    # Fetch full entry from SQLite
                    entry = await self.get_by_id(entry_id)
                    if entry:
                        entries.append(entry)

            logger.info(f"Semantic search found {len(entries)} results")
            return entries

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    async def search_keyword(
        self,
        query: str,
        limit: int = 5,
        memory_type: Optional[MemoryType] = None
    ) -> List[MemoryEntry]:
        """
        Search memory using keyword matching (SQLite FTS or LIKE).

        Args:
            query: Search query
            limit: Maximum results
            memory_type: Filter by memory type

        Returns:
            List of matching MemoryEntry objects
        """
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        sql = """
            SELECT id, type, content, metadata, created_at, updated_at
            FROM memory_entries
            WHERE content LIKE ?
        """

        params = [f"%{query}%"]

        if memory_type:
            sql += " AND type = ?"
            params.append(memory_type.value)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        entries = []
        for row in rows:
            entry = MemoryEntry(
                id=row[0],
                type=MemoryType(row[1]),
                content=row[2],
                metadata=json.loads(row[3]) if row[3] else {},
                created_at=datetime.fromisoformat(row[4]),
                updated_at=datetime.fromisoformat(row[5])
            )
            entries.append(entry)

        return entries

    async def get_by_id(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get memory entry by ID"""
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, type, content, metadata, created_at, updated_at
            FROM memory_entries
            WHERE id = ?
        """, (entry_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        entry = MemoryEntry(
            id=row[0],
            type=MemoryType(row[1]),
            content=row[2],
            metadata=json.loads(row[3]) if row[3] else {},
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5])
        )

        return entry

    async def get_recent(
        self,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None
    ) -> List[MemoryEntry]:
        """Get recent memory entries"""
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        sql = """
            SELECT id, type, content, metadata, created_at, updated_at
            FROM memory_entries
        """

        params = []
        if memory_type:
            sql += " WHERE type = ?"
            params.append(memory_type.value)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        entries = []
        for row in rows:
            entry = MemoryEntry(
                id=row[0],
                type=MemoryType(row[1]),
                content=row[2],
                metadata=json.loads(row[3]) if row[3] else {},
                created_at=datetime.fromisoformat(row[4]),
                updated_at=datetime.fromisoformat(row[5])
            )
            entries.append(entry)

        return entries
