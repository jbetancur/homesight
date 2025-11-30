"""
Ingestion tracking and monitoring for device knowledge base entries.

Tracks:
- Devices ingested
- Sources (PDF, AI-generated, etc)
- Confidence scores
- Timing and performance
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Source types for ingested knowledge"""
    OFFICIAL_PDF = "official_pdf"
    AI_GENERATED = "ai_generated"
    TRAINING_DATA = "training_data"
    VENDOR_INDEX = "vendor_index"  # Tier 1
    WEB_SEARCH = "web_search"  # Tier 2


@dataclass
class IngestionRecord:
    """Record of a device knowledge base ingestion"""
    manufacturer: str
    model: str
    device_id: Optional[str] = None
    timestamp: str = ""
    source_types: List[str] = None
    confidence: float = 0.0
    pdf_found: bool = False
    ai_generated: bool = False
    content_length: int = 0
    duration_seconds: float = 0.0
    status: str = "pending"  # pending, success, failed
    error_message: Optional[str] = None
    discovery_tier: Optional[str] = None  # "tier1_vendor_index", "tier2_web_search", "tier3_llm_ranked", "tier4_ai_fallback"
    vendor_index_hits: int = 0  # Number of indexed docs found

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
        if self.source_types is None:
            self.source_types = []


class IngestionTracker:
    """Track ingestion operations and maintain statistics"""

    def __init__(self, log_file: Optional[Path] = None):
        if log_file:
            self.log_file = log_file
        else:
            # Use centralized log directory
            import os
            if os.path.exists('/.dockerenv'):
                log_dir = Path('/app/log')
            else:
                log_dir = Path('logs')
            self.log_file = log_dir / 'ingestion.jsonl'
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.records: Dict[str, IngestionRecord] = {}

    def start_ingestion(self, manufacturer: str, model: str, device_id: Optional[str] = None) -> IngestionRecord:
        """Start tracking an ingestion operation"""
        key = f"{manufacturer}:{model}"
        record = IngestionRecord(
            manufacturer=manufacturer,
            model=model,
            device_id=device_id,
            timestamp=datetime.utcnow().isoformat(),
            status="pending"
        )
        self.records[key] = record
        logger.info(f"📋 Ingestion started: {manufacturer} {model} (device_id={device_id})")
        return record

    def set_pdf_status(self, manufacturer: str, model: str, found: bool):
        """Record PDF fetch result"""
        key = f"{manufacturer}:{model}"
        if key in self.records:
            self.records[key].pdf_found = found
            if found:
                logger.info(f"✅ PDF found: {manufacturer} {model}")
                self.records[key].source_types.append(SourceType.OFFICIAL_PDF.value)
            else:
                logger.info(f"⚠️  No PDF found: {manufacturer} {model} (will use training data)")

    def set_ai_generation(self, manufacturer: str, model: str, success: bool, content_length: int = 0):
        """Record AI knowledge generation"""
        key = f"{manufacturer}:{model}"
        if key in self.records:
            self.records[key].ai_generated = success
            self.records[key].content_length = content_length
            if success:
                logger.info(f"🤖 AI generation complete: {manufacturer} {model} ({content_length} chars)")
                self.records[key].source_types.append(SourceType.AI_GENERATED.value)
                # Confidence scoring
                if self.records[key].pdf_found:
                    self.records[key].confidence = 0.90
                else:
                    self.records[key].confidence = 0.65

    def complete_ingestion(self, manufacturer: str, model: str, duration_seconds: float, status: str = "success", error: Optional[str] = None):
        """Mark ingestion as complete"""
        key = f"{manufacturer}:{model}"
        if key in self.records:
            self.records[key].status = status
            self.records[key].duration_seconds = duration_seconds
            if error:
                self.records[key].error_message = error
                logger.error(f"❌ Ingestion failed: {manufacturer} {model} - {error}")
            else:
                logger.info(
                    f"✨ Ingestion complete: {manufacturer} {model} "
                    f"({duration_seconds:.2f}s, confidence: {self.records[key].confidence:.2f}, "
                    f"sources: {', '.join(self.records[key].source_types)})"
                )
            self._write_record(self.records[key])

    def _write_record(self, record: IngestionRecord):
        """Write record to JSONL log file"""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(asdict(record)) + "\n")
        except Exception as e:
            logger.error(f"Failed to write ingestion record: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get ingestion statistics"""
        completed = [r for r in self.records.values() if r.status == "success"]
        failed = [r for r in self.records.values() if r.status == "failed"]
        pending = [r for r in self.records.values() if r.status == "pending"]

        total_duration = sum(r.duration_seconds for r in completed)
        avg_duration = total_duration / len(completed) if completed else 0
        avg_confidence = sum(r.confidence for r in completed) / len(completed) if completed else 0
        pdf_count = sum(1 for r in completed if r.pdf_found)

        return {
            "total_ingested": len(completed),
            "total_failed": len(failed),
            "total_pending": len(pending),
            "pdf_sourced": pdf_count,
            "ai_generated": sum(1 for r in completed if r.ai_generated),
            "average_confidence": round(avg_confidence, 3),
            "average_duration_seconds": round(avg_duration, 2),
            "total_duration_seconds": round(total_duration, 2),
            "recent_devices": [
                {
                    "manufacturer": r.manufacturer,
                    "model": r.model,
                    "status": r.status,
                    "confidence": r.confidence,
                    "timestamp": r.timestamp
                }
                for r in sorted(self.records.values(), key=lambda x: x.timestamp, reverse=True)[:10]
            ]
        }

    def get_ingestion_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent ingestion records from log file"""
        records = []
        try:
            with open(self.log_file, "r") as f:
                for line in f.readlines()[-limit:]:
                    if line.strip():
                        records.append(json.loads(line))
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"Failed to read ingestion log: {e}")
        return records
