"""
Device knowledge base generation and ingestion.

Strategy:
1. Try to fetch official PDF from manufacturer (best grounding)
2. Generate comprehensive knowledge with OpenAI (grounded in PDF if available)
3. Ingest into RAG for retrieval
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List
from pathlib import Path
from rag.fetcher import DocumentAutoFetcher
from rag.engine import RAGEngine
from config import get_config
from ingestion_tracker import IngestionTracker
from metrics import kb_ingestions, kb_average_confidence, kb_sources

logger = logging.getLogger(__name__)

# Global ingestion tracker
_ingestion_tracker = None


def get_ingestion_tracker() -> IngestionTracker:
    """Get or create the global ingestion tracker"""
    global _ingestion_tracker
    if _ingestion_tracker is None:
        _ingestion_tracker = IngestionTracker()
    return _ingestion_tracker


class DocumentService:
    """
    Generates and ingests device knowledge base entries.

    Pipeline:
    1. Fetch official PDF (optional, best effort)
    2. Generate structured knowledge with OpenAI
    3. Ingest into ChromaDB with source metadata
    """

    def __init__(
        self,
        rag_engine: RAGEngine,
        cache_dir: Optional[Path] = None,
        openai_api_key: Optional[str] = None
    ):
        self.rag = rag_engine
        self.cache_dir = cache_dir or Path.home() / ".homesight" / "manuals"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        config = get_config()
        self.config = config
        self.openai_api_key = openai_api_key

        self.fetcher = DocumentAutoFetcher(
            rag_engine=rag_engine,
            cache_dir=self.cache_dir,
            openai_api_key=openai_api_key,
            rag_config=config.rag
        )

    async def discover_and_ingest_device_docs(self, device, force: bool = False) -> Dict[str, Any]:
        """
        Smart document discovery and ingestion for a device

        Strategy:
        1. Use OpenAI to generate comprehensive, curated device documentation
        2. Optionally fetch official PDFs if URLs are known (for accuracy)
        3. Skip web scraping - OpenAI knowledge is cleaner and faster

        This approach:
        - Leverages OpenAI's existing knowledge (you're paying for API anyway)
        - Gets curated info, not noisy forum posts
        - Is much faster and more reliable
        - Produces high-quality knowledge base entries

        Args:
            device: DeviceProfile or Dict[str, Any] (backward compatible)
            force: If True, clear all caches and re-ingest everything fresh

        Returns:
            Summary of discovered and ingested documents
        """
        from models import DeviceProfile

        # Handle both DeviceProfile and legacy Dict
        if isinstance(device, dict):
            device = DeviceProfile.from_dict(device)
        elif not isinstance(device, DeviceProfile):
            logger.error(f"Invalid device type: {type(device)}")
            return {"status": "error", "message": "Invalid device type"}

        manufacturer = device.manufacturer
        model = device.model
        device_type = device.device_type if isinstance(device.device_type, str) else device.device_type.value
        device_id = device.id

        start_time = time.time()
        tracker = get_ingestion_tracker()
        tracker.start_ingestion(manufacturer, model, device_id)

        results = {
            "manufacturer": manufacturer,
            "model": model,
            "sources_found": [],
            "force_refresh": force
        }

        try:
            # If force refresh, clean up existing RAG entries for this device
            if force:
                logger.info(f"Force refresh: cleaning RAG entries for {manufacturer} {model}")
                self.rag.delete_device_docs(manufacturer, model)

            # 1. PRIMARY: Fetch official documentation PDFs if available
            # This provides the authoritative source we want OpenAI to ground against.
            doc_path = None
            try:
                official_success = await self.fetcher.fetch_for_device(device, force=force)
                tracker.set_pdf_status(manufacturer, model, official_success)
                if official_success:
                    results["sources_found"].append("official_pdf_manual")
                    # Try to locate the cached manual across fetchers
                    try:
                        # Check specialized fetchers first
                        cached = None
                        for f in getattr(self.fetcher, 'fetchers', {}).values():
                            cached = f._is_cached(model)
                            if cached:
                                doc_path = cached
                                break

                        # Fallback to generic cache
                        if not doc_path:
                            doc_path = self.fetcher.generic_fetcher._is_cached(model)
                    except Exception:
                        doc_path = None
            except Exception as e:
                logger.debug(f"Official PDF fetch failed (optional): {e}")
                tracker.set_pdf_status(manufacturer, model, False)

            # 2. SECONDARY: Generate comprehensive knowledge using OpenAI, grounded
            # on the official doc text if available. If no official docs found, the
            # generator will produce limited/unverified content and label it clearly.
            try:
                documentation_text = None
                if doc_path:
                    try:
                        if doc_path.suffix.lower() == ".pdf":
                            # Reuse the fetcher's PDF extractor if possible
                            documentation_text = self.fetcher._extract_pdf_text(doc_path)
                        else:
                            documentation_text = doc_path.read_text(encoding='utf-8')
                    except Exception:
                        documentation_text = None

                if self.openai_api_key:
                    content_len = await self._generate_comprehensive_knowledge(device, documentation_text=documentation_text)
                    tracker.set_ai_generation(manufacturer, model, True, content_len)
                    results["sources_found"].append("ai_generated_knowledge")
            except Exception as e:
                logger.error(f"Knowledge generation failed: {e}")
                tracker.set_ai_generation(manufacturer, model, False, 0)

            results["status"] = "success" if results["sources_found"] else "partial"
            results["total_sources"] = len(results["sources_found"])

            # Record KB metrics
            kb_ingestions.labels(status=results["status"]).inc()
            for source in results["sources_found"]:
                kb_sources.labels(source_type=source).inc()

            # Update confidence from tracker
            tracker_stats = tracker.get_stats()
            if tracker_stats.get("average_confidence", 0) > 0:
                kb_average_confidence.set(tracker_stats["average_confidence"])

        except Exception as e:
            duration = time.time() - start_time
            tracker.complete_ingestion(manufacturer, model, duration, "failed", str(e))
            kb_ingestions.labels(status="failed").inc()
            raise

        duration = time.time() - start_time
        tracker.complete_ingestion(manufacturer, model, duration, "success")
        return results


    async def _rag_add_documents(self, documents: List[Dict[str, Any]], batch_size: int = 1):
        """Helper to add documents to RAG with async/sync compatibility."""
        try:
            if hasattr(self.rag, "add_documents_async"):
                await self.rag.add_documents_async(documents, batch_size=batch_size)
            elif hasattr(self.rag, "add_documents_batch"):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.rag.add_documents_batch, documents, batch_size)
            elif hasattr(self.rag, "add_document"):
                for doc in documents:
                    try:
                        self.rag.add_document(doc.get("text", ""), doc.get("metadata", {}))
                    except Exception:
                        logger.debug("Failed to add single document via fallback add_document")
            else:
                logger.error("RAG engine does not expose a known ingestion API")
        except Exception as e:
            logger.error(f"Error adding documents to RAG: {e}")


    async def _generate_comprehensive_knowledge(self, device: Dict[str, Any], documentation_text: Optional[str] = None) -> int:
        """
        Generate structured knowledge base entry using OpenAI.

        Grounding strategy:
        - If documentation_text (PDF) provided: ground in actual docs, high confidence
        - If no docs: use training data only, mark as unverified

        Output includes:
        - Specifications (model, dimensions, power, protocol)
        - Setup & pairing procedures
        - Common issues & solutions
        - Maintenance
        - Integration & compatibility
        - Warranty & support

        Returns:
            Length of generated content in characters
        """
        if not self.openai_api_key:
            return 0

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.openai_api_key)

            manufacturer = device.manufacturer
            model = device.model
            device_type = device.device_type if isinstance(device.device_type, str) else device.device_type.value

            # Attach documentation text if available; truncate to reasonable size for prompts
            doc_text_snippet = None
            if documentation_text:
                # Limit to first ~30k chars to keep prompt reasonable
                doc_text_snippet = documentation_text[:30000]

            prompt = f"""You are a technical documentation expert. You will generate a COMPREHENSIVE, DETAILED knowledge base entry for a device using ONLY verifiable information from the provided input text and publicly known manufacturer data.

⚠️ STRICT RULES (NEVER BREAK THESE):
- NEVER invent or guess specifications, dimensions, button sequences, pairing steps, or any technical detail.
- If data is not explicitly known or publicly documented, write:
  "Specification not available from manufacturer documentation."
- DO NOT infer facts from similar models.
- DO NOT hallucinate part numbers, frequencies, or metrics.
- ONLY use information that is explicitly in the provided documentation or widely confirmed by the manufacturer.
- NEVER use first-person phrases like "I couldn't find", "I was unable to", or "I don't have access to"
- Output must be written in third-person, factual documentation style

You may only use:
✔ The manufacturer-provided document
✔ The device name/model
✔ Widely confirmed public information
✔ Industry-standard general behaviors (ONLY if noted as "typical, but not confirmed")

---

INPUT
Manufacturer: {manufacturer}
Model: {model}
Type: {device_type}
Source Documentation:
{{documentation_text}}

---

OUTPUT STRUCTURE
Generate a Markdown document with the following sections.

1. DEVICE SPECIFICATIONS
- Exact model number & variants
- Physical dimensions & weight
- Communication protocol(s)
- Battery type (EXACT model only if confirmed)
- Expected battery life
- Operating temperature range
- Wireless range

For any unavailable spec, write:
"Specification not available from manufacturer documentation."

---

2. SETUP & PAIRING
- Step-by-step pairing instructions
- Factory reset instructions
- LED indicator chart
- Troubleshooting for failed pairing

If missing, write:
"Procedure not available from manufacturer documentation."

---

3. COMMON ISSUES & SOLUTIONS
- Known issues
- Confirmed troubleshooting procedures
- Signal problems
- Battery-related behaviors

Do NOT fabricate issues or fixes.

---

4. MAINTENANCE
- Cleaning
- Battery replacement
- Firmware update availability
- Long-term reliability notes

If not documented, note:
"Information not available from manufacturer documentation."

---

5. INTEGRATION & COMPATIBILITY
- Confirmed compatible hubs/platforms
- Protocol details
- Automation examples based ONLY on known behavior

If compatibility is unknown, state so.

---

6. WARRANTY & SUPPORT
- Warranty length (if known)
- Manufacturer support links
- Documentation links

---

STYLE REQUIREMENTS
- Use precise, technical language.
- NEVER assume or guess missing information.
- If unsure, explicitly mark the data as unavailable.
- Use tables where appropriate.
- Keep formatting structured and consistent for ingestion into a knowledge base."""

            # Build messages; include documentation_text if present and instruct model to use it
            messages = [
                {
                    "role": "system",
                    "content": """You are an expert technical writer generating device documentation.
Follow these rules STRICTLY:

1. USE ONLY information explicitly provided in the user prompt or the provided documentation text.
2. NEVER guess, infer, or create any technical details. If a detail is not present, state: "Specification not available from manufacturer documentation."
3. NEVER invent part numbers, pairing steps, reset sequences, LED patterns, or measurements.
4. NEVER use first-person phrases. Do NOT write: "I couldn't find", "I was unable to", "I don't have access to"
5. ALWAYS write in third-person factual style: "Specification not available", "Documentation not provided", etc.
6. If no documentation is provided, generate a minimal template with all sections marked as unavailable.
7. Output must be structured Markdown suitable for knowledge base ingestion.
8. Accuracy is more important than completeness.

UNACCEPTABLE OUTPUT EXAMPLES (NEVER USE):
❌ "I couldn't find specific information about..."
❌ "I was unable to locate documentation for..."
❌ "I don't have access to the official manual..."

ACCEPTABLE OUTPUT EXAMPLES:
✅ "Specification not available from manufacturer documentation."
✅ "Procedure not documented by manufacturer."
✅ "Official documentation not provided."
"""
                }
            ]

            user_payload = f"Manufacturer: {manufacturer}\nModel: {model}\nType: {device_type}\n\n"
            if doc_text_snippet:
                user_payload += f"Source Documentation:\n\n{doc_text_snippet}\n\n"
                user_payload += "Please generate the structured knowledge base entry as described, using ONLY information from the documentation above."
            else:
                user_payload += "Source Documentation: NOT PROVIDED\n\n"
                user_payload += """Since no official documentation was provided, generate a minimal knowledge base template with the required sections.
For each section, state: "Specification not available from manufacturer documentation."
Do NOT attempt to fill in details from general knowledge. Keep entries factual and minimal."""

            messages.append({"role": "user", "content": user_payload})

            # Build kwargs with conditional parameters for GPT-5 compatibility
            kwargs = {
                "model": self.config.llm.openai_model,
                "messages": messages,
            }

            # GPT-5-mini doesn't support temperature parameter
            if "gpt-5" not in self.config.llm.openai_model.lower():
                kwargs["temperature"] = 0.0

            if "gpt-5" in self.config.llm.openai_model.lower():
                # GPT-5-mini uses reasoning_tokens extensively, need much higher limits
                kwargs["max_completion_tokens"] = 16000
            else:
                kwargs["max_tokens"] = 2000

            response = await client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content

            # Ingest generated content into RAG (use helper for compatibility)
            metadata = {
                "source": f"{manufacturer} {model} - Comprehensive Knowledge Base (AI)",
                "manufacturer": manufacturer,
                "model": model,
                "device_type": device_type,
                "category": "comprehensive_knowledge",
                "auto_generated": True,
                "generation_method": "openai_curated",
            }

            documents = [{"text": content, "metadata": metadata}]
            await self._rag_add_documents(documents, batch_size=1)
            logger.info(f"✅ Generated comprehensive knowledge for {manufacturer} {model} ({len(content)} chars)")
            return len(content)

        except Exception as e:
            logger.error(f"Comprehensive knowledge generation failed: {e}")
            return 0
