"""
Document Ranking and Quality Scoring for RAG

Implements source-aware ranking to prioritize:
1. Recent HTML (product pages often more current than PDFs)
2. Official PDFs (authoritative but may be outdated)
3. AI-generated content (fallback, lower confidence)

Freshness Signals:
- HTML pages often have schema.org dateModified
- PDFs have metadata creation/modification dates
- Manufacturer support pages updated more frequently

Quality Signals:
- Source type (official site > third-party > AI-generated)
- Content completeness (sections present)
- Model-specific vs generic content
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DocumentScore:
    """Computed document quality score with breakdown"""
    doc_id: str
    total_score: float
    
    # Score components (0-1 scale each)
    relevance_score: float = 0.0       # Semantic similarity from embedding
    source_type_score: float = 0.0     # Official PDF > HTML > AI-generated
    freshness_score: float = 0.0       # Newer is better (decay function)
    specificity_score: float = 0.0     # Model-specific > generic manufacturer
    completeness_score: float = 0.0    # Has setup, troubleshooting, etc.
    
    # Metadata
    source_type: str = "unknown"
    last_updated: Optional[datetime] = None
    
    # Original document data
    document: Dict[str, Any] = field(default_factory=dict)


# Source type priority weights
SOURCE_TYPE_WEIGHTS = {
    # Official sources (highest priority)
    "official_pdf": 1.0,
    "official_html": 0.95,
    "manufacturer_website": 0.90,
    
    # Product pages (often more current than PDFs)
    "product_page_html": 0.92,
    "support_page_html": 0.88,
    
    # Third-party but reliable
    "retailer_spec_sheet": 0.70,
    "community_wiki": 0.60,
    
    # AI-generated (fallback)
    "ai_generated": 0.50,
    "ai_generated_unverified": 0.30,
    
    # Unknown
    "unknown": 0.40,
}

# Freshness decay parameters
FRESHNESS_HALF_LIFE_DAYS = 365  # 50% decay after 1 year
MAX_AGE_DAYS = 1825  # 5 years max consideration


class DocumentRanker:
    """
    Ranks and re-scores RAG query results based on multiple quality signals.
    
    Usage:
        ranker = DocumentRanker()
        ranked_results = ranker.rank_results(raw_results, query_context)
    """
    
    def __init__(
        self,
        source_weight: float = 0.25,
        freshness_weight: float = 0.20,
        relevance_weight: float = 0.35,
        specificity_weight: float = 0.15,
        completeness_weight: float = 0.05,
    ):
        """
        Initialize ranker with configurable weights.
        
        Weights should sum to 1.0 for interpretable scores.
        """
        self.source_weight = source_weight
        self.freshness_weight = freshness_weight
        self.relevance_weight = relevance_weight
        self.specificity_weight = specificity_weight
        self.completeness_weight = completeness_weight
        
        # Normalize weights
        total = (source_weight + freshness_weight + relevance_weight + 
                 specificity_weight + completeness_weight)
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total}, normalizing...")
            self.source_weight /= total
            self.freshness_weight /= total
            self.relevance_weight /= total
            self.specificity_weight /= total
            self.completeness_weight /= total
    
    def rank_results(
        self,
        results: List[Dict[str, Any]],
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        prefer_recent: bool = True,
    ) -> List[DocumentScore]:
        """
        Rank query results with multi-signal scoring.
        
        Args:
            results: Raw RAG query results
            manufacturer: Target manufacturer (for specificity scoring)
            model: Target model (for specificity scoring)
            prefer_recent: If True, boost freshness weight for HTML sources
        
        Returns:
            List of DocumentScore objects, sorted best-first
        """
        scored_results = []
        
        for result in results:
            score = self._score_document(result, manufacturer, model, prefer_recent)
            scored_results.append(score)
        
        # Sort by total_score descending
        scored_results.sort(key=lambda x: x.total_score, reverse=True)
        
        logger.debug(
            f"Ranked {len(scored_results)} docs: "
            f"top_score={scored_results[0].total_score:.3f} "
            f"(rel={scored_results[0].relevance_score:.2f}, "
            f"src={scored_results[0].source_type_score:.2f}, "
            f"fresh={scored_results[0].freshness_score:.2f})"
            if scored_results else "no results"
        )
        
        return scored_results
    
    def _score_document(
        self,
        doc: Dict[str, Any],
        manufacturer: Optional[str],
        model: Optional[str],
        prefer_recent: bool,
    ) -> DocumentScore:
        """Score a single document across all dimensions."""
        
        metadata = doc.get("metadata", {})
        text = doc.get("text", "")
        
        # Extract key metadata
        source_type = self._infer_source_type(metadata, doc)
        last_updated = self._extract_freshness(metadata)
        
        # Calculate component scores
        relevance = doc.get("relevance_score", 0.5)
        source_score = self._score_source_type(source_type)
        freshness = self._score_freshness(last_updated, source_type, prefer_recent)
        specificity = self._score_specificity(metadata, text, manufacturer, model)
        completeness = self._score_completeness(text)
        
        # Weighted total
        total = (
            self.relevance_weight * relevance +
            self.source_weight * source_score +
            self.freshness_weight * freshness +
            self.specificity_weight * specificity +
            self.completeness_weight * completeness
        )
        
        return DocumentScore(
            doc_id=doc.get("id", "unknown"),
            total_score=total,
            relevance_score=relevance,
            source_type_score=source_score,
            freshness_score=freshness,
            specificity_score=specificity,
            completeness_score=completeness,
            source_type=source_type,
            last_updated=last_updated,
            document=doc,
        )
    
    def _infer_source_type(self, metadata: Dict, doc: Dict) -> str:
        """Infer source type from metadata and content."""
        
        # Check explicit source type
        if "source_type" in metadata:
            return metadata["source_type"]
        
        # Check if AI-generated
        if metadata.get("auto_generated") or metadata.get("generation_method"):
            return "ai_generated"
        
        # Check file path
        file_path = metadata.get("file_path", "").lower()
        if file_path.endswith(".pdf"):
            if metadata.get("auto_fetched"):
                return "official_pdf"
            return "official_pdf"
        
        # Check URL or source hints
        source = metadata.get("source", "").lower()
        url = metadata.get("url", "").lower()
        
        # Official manufacturer domains
        if any(d in url or d in source for d in ["zooz.com", "getzooz.com", "support.zooz"]):
            if ".pdf" in url:
                return "official_pdf"
            return "product_page_html"
        
        if any(d in url or d in source for d in ["aqara.com", "shelly.cloud", "philips-hue.com"]):
            return "manufacturer_website"
        
        # Category hints
        category = metadata.get("category", "").lower()
        if "manual" in category or "device_manual" in category:
            return "official_pdf"
        if "comprehensive_knowledge" in category:
            return "ai_generated"
        
        return "unknown"
    
    def _extract_freshness(self, metadata: Dict) -> Optional[datetime]:
        """Extract document freshness from metadata."""
        
        # Try various date fields
        for field in ["last_modified", "date_modified", "updated_at", "last_verified", 
                      "discovered_at", "created_at", "fetch_date"]:
            value = metadata.get(field)
            if value:
                try:
                    if isinstance(value, datetime):
                        return value
                    if isinstance(value, str):
                        # Try ISO format
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except Exception:
                    continue
        
        return None
    
    def _score_source_type(self, source_type: str) -> float:
        """Score based on source authority."""
        return SOURCE_TYPE_WEIGHTS.get(source_type, 0.4)
    
    def _score_freshness(
        self,
        last_updated: Optional[datetime],
        source_type: str,
        prefer_recent: bool,
    ) -> float:
        """
        Score based on document freshness with exponential decay.
        
        HTML sources get a freshness bonus when prefer_recent=True,
        reflecting that web pages are often more current than PDFs.
        """
        if not last_updated:
            # Unknown freshness - give moderate score
            # HTML sources get benefit of the doubt (often fresher)
            if "html" in source_type.lower():
                return 0.6
            return 0.4
        
        now = datetime.now()
        if last_updated.tzinfo:
            now = datetime.now(last_updated.tzinfo)
        
        age_days = (now - last_updated).days
        
        if age_days < 0:
            age_days = 0  # Future dates treated as now
        
        if age_days > MAX_AGE_DAYS:
            return 0.1  # Very old documents get minimal score
        
        # Exponential decay
        decay = 0.5 ** (age_days / FRESHNESS_HALF_LIFE_DAYS)
        
        # HTML freshness bonus when preferring recent
        if prefer_recent and "html" in source_type.lower():
            decay = min(1.0, decay * 1.15)  # 15% boost
        
        return decay
    
    def _score_specificity(
        self,
        metadata: Dict,
        text: str,
        manufacturer: Optional[str],
        model: Optional[str],
    ) -> float:
        """Score how specific the document is to the target device."""
        
        score = 0.5  # Base score
        
        doc_manufacturer = metadata.get("manufacturer", "").lower()
        doc_model = metadata.get("model", "").lower()
        
        # Manufacturer match
        if manufacturer and doc_manufacturer:
            if manufacturer.lower() == doc_manufacturer:
                score += 0.2
            elif manufacturer.lower() in doc_manufacturer:
                score += 0.1
        
        # Model match (most important)
        if model and doc_model:
            model_lower = model.lower()
            if model_lower == doc_model:
                score += 0.3  # Exact match
            elif model_lower in doc_model or doc_model in model_lower:
                score += 0.2  # Partial match
        
        # Check model appears in text
        if model and model.lower() in text.lower():
            score += 0.1
        
        return min(1.0, score)
    
    def _score_completeness(self, text: str) -> float:
        """Score document completeness based on expected sections."""
        
        text_lower = text.lower()
        
        # Key sections we expect in good documentation
        sections = [
            ("specifications", ["specification", "specs", "dimensions", "weight"]),
            ("setup", ["setup", "installation", "pairing", "inclusion"]),
            ("troubleshooting", ["troubleshoot", "problem", "issue", "fix", "reset"]),
            ("maintenance", ["maintenance", "battery", "clean", "care"]),
            ("compatibility", ["compatible", "works with", "integration", "hub"]),
        ]
        
        found_sections = 0
        for section_name, keywords in sections:
            if any(kw in text_lower for kw in keywords):
                found_sections += 1
        
        return found_sections / len(sections)


def get_ranker() -> DocumentRanker:
    """Factory function to get configured ranker instance."""
    return DocumentRanker(
        source_weight=0.25,
        freshness_weight=0.20,
        relevance_weight=0.35,
        specificity_weight=0.15,
        completeness_weight=0.05,
    )
