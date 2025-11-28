"""
Vendor Document Storage

SQLite-based persistent storage for indexed manufacturer documentation.

Features:
- Fast lookup for manufacturer + model documents
- Stores PDFs, HTML docs, datasheets, etc.
- Tracks discovery time, verification time, metadata, size
- Auto-normalizes DB rows to IndexedDocument instances
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass: IndexedDocument
# ---------------------------------------------------------------------------

@dataclass
class IndexedDocument:
    """
    Represents a stored manufacturer documentation record.

    Required fields come first (Python dataclass rule).
    Optional fields must come last.
    """

    # ---- REQUIRED (no defaults) ----
    manufacturer: str
    url: str
    title: str
    document_type: str          # pdf, html, datasheet, manual, etc
    discovered_at: datetime

    # ---- OPTIONAL (defaults allowed) ----
    model: Optional[str] = None
    id: Optional[int] = None    # primary key in SQLite
    last_verified: Optional[datetime] = None
    file_size: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert object to dict compatible with SQLite schema."""
        d = asdict(self)
        d["discovered_at"] = self.discovered_at.isoformat()
        d["last_verified"] = (
            self.last_verified.isoformat() if self.last_verified else None
        )
        d["metadata"] = json.dumps(self.metadata) if self.metadata else None
        return d

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "IndexedDocument":
        """
        Create a sanitized IndexedDocument instance from SQLite Row → dict.
        Unknown keys are ignored.
        """

        allowed = set(cls.__dataclass_fields__.keys())
        d = {k: v for k, v in raw.items() if k in allowed}

        # Parse timestamps
        if isinstance(d.get("discovered_at"), str):
            d["discovered_at"] = datetime.fromisoformat(d["discovered_at"])

        if isinstance(d.get("last_verified"), str):
            d["last_verified"] = datetime.fromisoformat(d["last_verified"])

        # Parse metadata JSON
        if isinstance(d.get("metadata"), str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except Exception:
                d["metadata"] = None

        return cls(**d)


# ---------------------------------------------------------------------------
# VendorDocumentStorage
# ---------------------------------------------------------------------------

class VendorDocumentStorage:
    """
    SQLite storage backend for vendor documentation index.

    Provides:
      • add/update storage
      • fast lookup by manufacturer/model
      • indexing stats
      • cleanup
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path.home() / "homesight" / "vendor_index.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        logger.info(f"VendorDocumentStorage initialized at: {self.db_path}")

    # -------------------------------------------------------------------
    # DDL - Schema
    # -------------------------------------------------------------------

    def _init_db(self):
        """Create tables + indexes if missing."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indexed_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manufacturer TEXT NOT NULL,
                model TEXT,
                url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                document_type TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                last_verified TEXT,
                file_size INTEGER,
                metadata TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manufacturer_model
            ON indexed_documents(manufacturer, model)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manufacturer
            ON indexed_documents(manufacturer)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_url
            ON indexed_documents(url)
        """)

        conn.commit()
        conn.close()

    # -------------------------------------------------------------------
    # Insert / Update
    # -------------------------------------------------------------------

    def add_document(self, doc: IndexedDocument) -> bool:
        """
        Insert or replace a document entry.
        Uses url as unique constraint.
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            d = doc.to_dict()

            cursor.execute("""
                INSERT OR REPLACE INTO indexed_documents
                (manufacturer, model, url, title, document_type,
                 discovered_at, last_verified, file_size, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["manufacturer"],
                d["model"],
                d["url"],
                d["title"],
                d["document_type"],
                d["discovered_at"],
                d["last_verified"],
                d["file_size"],
                d["metadata"]
            ))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Failed to add document: {e}")
            return False

    # -------------------------------------------------------------------
    # Lookup
    # -------------------------------------------------------------------

    def lookup_docs(self, manufacturer: str, model: Optional[str] = None) -> List[IndexedDocument]:
        """
        Lookup documents for a manufacturer (with optional model filter).
        Returns list of IndexedDocument objects.
        """

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if model:
                cursor.execute("""
                    SELECT * FROM indexed_documents
                    WHERE LOWER(manufacturer) = LOWER(?)
                    AND (LOWER(model) = LOWER(?) OR model IS NULL)
                    ORDER BY discovered_at DESC
                """, (manufacturer, model))
            else:
                cursor.execute("""
                    SELECT * FROM indexed_documents
                    WHERE LOWER(manufacturer) = LOWER(?)
                    ORDER BY discovered_at DESC
                """, (manufacturer,))

            rows = cursor.fetchall()
            conn.close()

            return [IndexedDocument.from_dict(dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Lookup failed: {e}")
            return []

    # -------------------------------------------------------------------
    # Diagnostics
    # -------------------------------------------------------------------

    def get_all_manufacturers(self) -> List[str]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT manufacturer
                FROM indexed_documents
                ORDER BY manufacturer
            """)

            results = [r[0] for r in cursor.fetchall()]
            conn.close()
            return results

        except Exception as e:
            logger.error(f"Failed to fetch manufacturer list: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM indexed_documents")
            total_docs = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT manufacturer) FROM indexed_documents")
            total_mfr = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM indexed_documents WHERE document_type = 'pdf'")
            pdf_count = cursor.fetchone()[0]

            conn.close()

            return {
                "total_documents": total_docs,
                "total_manufacturers": total_mfr,
                "pdf_documents": pdf_count,
                "db": str(self.db_path),
            }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    # -------------------------------------------------------------------
    # Delete
    # -------------------------------------------------------------------

    def delete_manufacturer_docs(self, manufacturer: str) -> int:
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM indexed_documents
                WHERE LOWER(manufacturer) = LOWER(?)
            """, (manufacturer,))

            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            logger.info(f"Deleted {deleted} docs for {manufacturer}")
            return deleted

        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return 0

    # -------------------------------------------------------------------
    # Update Verification Timestamp
    # -------------------------------------------------------------------

    def update_last_verified(self, url: str):
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE indexed_documents
                SET last_verified = ?
                WHERE url = ?
            """, (datetime.now().isoformat(), url))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.debug(f"Update verification failed: {e}")
            return
