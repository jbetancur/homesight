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
        # Use /var/lib/homesight for persistence (same volume as other DBs)
        self.db_path = db_path or Path("/var/lib/homesight/vendor_index.db")
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

    def lookup_docs(self, manufacturer: str, model: Optional[str] = None, device_name: Optional[str] = None) -> List[IndexedDocument]:
        """
        Lookup documents for a manufacturer (with optional model filter).
        Returns list of IndexedDocument objects, prioritizing exact matches and PDFs.
        
        Args:
            manufacturer: Device manufacturer name
            model: Device model name/description
            device_name: Device name which may contain model identifier (e.g., "ZSE44")
        """

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if model:
                # Extract potential model identifiers from both model and device_name
                # e.g., "ZSE44" from device name "ZSE44" or model "Temperature Humidity XS Sensor ZSE44"
                import re
                search_text = f"{model} {device_name or ''}"
                model_identifiers = re.findall(r'[A-Z]{2,4}\d{2,3}', search_text.upper())
                
                # Remove duplicates while preserving order
                seen = set()
                model_identifiers = [x for x in model_identifiers if not (x in seen or seen.add(x))]
                
                if model_identifiers:
                    logger.debug(f"Extracted model identifiers for lookup: {model_identifiers}")
                
                # Build query to match:
                # 1. Exact model match (highest priority)
                # 2. Model identifier match (e.g., ZSE44)
                # 3. Partial model match (contains)
                # 4. NULL model (fallback, lowest priority)
                # Then order by: PDF > HTML, recent first
                
                if model_identifiers:
                    # If we extracted a model identifier (like ZSE44), prioritize it
                    identifier_conditions = " OR ".join(["UPPER(model) = ?" for _ in model_identifiers])
                    query = f"""
                        SELECT *, 
                            CASE 
                                WHEN UPPER(model) = UPPER(?) THEN 1
                                WHEN {identifier_conditions} THEN 2
                                WHEN model IS NOT NULL AND INSTR(UPPER(model), UPPER(?)) > 0 THEN 3
                                WHEN model IS NOT NULL AND INSTR(UPPER(?), UPPER(model)) > 0 THEN 4
                                WHEN model IS NULL THEN 9
                                ELSE 10
                            END as match_priority,
                            CASE document_type 
                                WHEN 'pdf' THEN 1 
                                WHEN 'html' THEN 2 
                                ELSE 3 
                            END as doc_priority
                        FROM indexed_documents
                        WHERE LOWER(manufacturer) = LOWER(?)
                        ORDER BY match_priority ASC, doc_priority ASC, discovered_at DESC
                    """
                    params = [model] + model_identifiers + [model, model, manufacturer]
                else:
                    # No identifier extracted, simpler matching
                    query = """
                        SELECT *, 
                            CASE 
                                WHEN UPPER(model) = UPPER(?) THEN 1
                                WHEN model IS NOT NULL AND INSTR(UPPER(model), UPPER(?)) > 0 THEN 3
                                WHEN model IS NOT NULL AND INSTR(UPPER(?), UPPER(model)) > 0 THEN 4
                                WHEN model IS NULL THEN 9
                                ELSE 10
                            END as match_priority,
                            CASE document_type 
                                WHEN 'pdf' THEN 1 
                                WHEN 'html' THEN 2 
                                ELSE 3 
                            END as doc_priority
                        FROM indexed_documents
                        WHERE LOWER(manufacturer) = LOWER(?)
                        ORDER BY match_priority ASC, doc_priority ASC, discovered_at DESC
                    """
                    params = [model, model, model, manufacturer]
                
                cursor.execute(query, params)
            else:
                # No model filter - just return all for manufacturer, PDFs first
                cursor.execute("""
                    SELECT *,
                        CASE document_type 
                            WHEN 'pdf' THEN 1 
                            WHEN 'html' THEN 2 
                            ELSE 3 
                        END as doc_priority
                    FROM indexed_documents
                    WHERE LOWER(manufacturer) = LOWER(?)
                    ORDER BY doc_priority ASC, discovered_at DESC
                """, (manufacturer,))

            rows = cursor.fetchall()
            conn.close()

            # Convert to IndexedDocument objects, excluding the priority columns
            docs = []
            for row in rows:
                row_dict = dict(row)
                # Remove our temporary priority columns
                row_dict.pop('match_priority', None)
                row_dict.pop('doc_priority', None)
                docs.append(IndexedDocument.from_dict(row_dict))
            
            return docs

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
