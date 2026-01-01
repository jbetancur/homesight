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
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from rag.fetcher import DocumentAutoFetcher
from rag.engine import RAGEngine
from config import get_config
from services.ingestion_tracker import IngestionTracker
from metrics.metrics import kb_ingestions, kb_average_confidence, kb_sources
from hsil.prompts import get_prompt, get_prompt_section

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
        self.cache_dir = cache_dir or Path.home() / "homesight" / "manuals"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        config = get_config()
        self.config = config
        self.openai_api_key = openai_api_key

        # Get search API keys from config or environment
        brave_api_key = getattr(config.search, 'brave_api_key', None) or os.environ.get('BRAVE_SEARCH_API_KEY')
        bing_api_key = getattr(config.search, 'bing_api_key', None) or os.environ.get('BING_SEARCH_API_KEY')

        self.fetcher = DocumentAutoFetcher(
            rag_engine=rag_engine,
            cache_dir=self.cache_dir,
            openai_api_key=openai_api_key,
            brave_api_key=brave_api_key,
            bing_api_key=bing_api_key,
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
            "source_urls": [],  # Track documentation source URLs
            "force_refresh": force
        }

        try:
            # Check if we already have RAG documents for this manufacturer/model
            # Skip re-ingestion unless force refresh is requested
            if not force and self.rag.has_documents_for_model(manufacturer, model):
                logger.info(f"RAG dedup: Found existing documents for {manufacturer} {model}, skipping ingestion")
                tracker.complete_ingestion(manufacturer, model, time.time() - start_time, "deduped")

                # Retrieve existing KB content from RAG to return to Go backend
                # This ensures the Go backend can still store KB even when deduping
                kb_content = None
                try:
                    # Query RAG for comprehensive knowledge (category filter)
                    where_filter = {
                        "$and": [
                            {"manufacturer": {"$eq": manufacturer}},
                            {"model": {"$eq": model}},
                            {"category": {"$eq": "comprehensive_knowledge"}}
                        ]
                    }
                    existing_docs = self.rag.collection.get(where=where_filter, limit=1)
                    if existing_docs and existing_docs.get('documents') and len(existing_docs['documents']) > 0:
                        kb_content = existing_docs['documents'][0]
                        logger.info(f"Retrieved existing KB content for {manufacturer} {model} ({len(kb_content)} chars)")
                except Exception as e:
                    logger.warning(f"Could not retrieve existing KB content: {e}")

                return {
                    "status": "success",
                    "manufacturer": manufacturer,
                    "model": model,
                    "sources_found": ["existing_rag_documents"],
                    "source_urls": [],
                    "total_sources": 1,
                    "force_refresh": False,
                    "deduped": True,
                    "kb_content": kb_content,  # Include existing KB content
                    "message": f"Using existing RAG knowledge base for {manufacturer} {model}"
                }

            # If force refresh, clean up existing RAG entries for this device
            if force:
                logger.info(f"Force refresh: cleaning RAG entries for {manufacturer} {model}")
                self.rag.delete_device_docs(manufacturer, model)

            # 1. PRIMARY: Fetch official documentation PDFs if available
            # This provides the authoritative source we want OpenAI to ground against.
            doc_path = None
            source_url = None
            logger.info(f"Starting doc fetch for {manufacturer} {model}")
            try:
                official_success = await self.fetcher.fetch_for_device(device, force=force)
                logger.info(f"Fetch result for {manufacturer} {model}: official_success={official_success}")
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
                                logger.info(f"Found cached PDF via specialized fetcher: {doc_path}")
                                break

                        # Fallback to generic cache
                        if not doc_path:
                            doc_path = self.fetcher.generic_fetcher._is_cached(model)
                            logger.info(f"generic_fetcher._is_cached({model}) returned: {doc_path}")
                            if doc_path:
                                logger.info(f"Found cached PDF via generic fetcher: {doc_path}")
                        
                        if not doc_path:
                            logger.warning(f"PDF fetch succeeded but cache lookup failed for model: {model}")
                        
                        # Get source URL for documentation references
                        source_url = self.fetcher.get_source_url(manufacturer, model)
                        if source_url:
                            results["source_urls"].append(source_url)
                            logger.info(f"Source URL for {manufacturer} {model}: {source_url}")
                    except Exception as e:
                        logger.warning(f"Cache lookup exception for {model}: {e}")
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
                    kb_content = await self._generate_comprehensive_knowledge(
                        device, 
                        documentation_text=documentation_text,
                        source_urls=results.get("source_urls", [])
                    )
                    if kb_content:
                        tracker.set_ai_generation(manufacturer, model, True, len(kb_content))
                        results["sources_found"].append("ai_generated_knowledge")
                        results["kb_content"] = kb_content  # Include generated content for Go backend
                    else:
                        tracker.set_ai_generation(manufacturer, model, False, 0)
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


    async def _generate_comprehensive_knowledge(
        self, 
        device: Dict[str, Any], 
        documentation_text: Optional[str] = None,
        source_urls: Optional[List[str]] = None
    ) -> Optional[str]:
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
        - Source references (links to official documentation)

        Args:
            device: DeviceProfile with device metadata
            documentation_text: Optional PDF/manual text to ground against
            source_urls: Optional list of source URLs to include as references

        Returns:
            Generated KB content as string, or None if generation failed
        """
        if not self.openai_api_key:
            return None

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

            # Build source references section instruction
            # NOTE: Source URLs are now appended directly to generated content, not via prompt

            # Load prompt from external YAML for hot-reload capability
            prompt = get_prompt(
                "kb_generation",
                "user_prompt",
                manufacturer=manufacturer,
                model=model,
                device_type=device_type,
                documentation_text="{documentation_text}"  # Placeholder for later substitution
            )

            # Build messages; include documentation_text if present and instruct model to use it
            # Load system prompt from external YAML for hot-reload capability
            messages = [
                {
                    "role": "system",
                    "content": get_prompt_section("kb_generation", "system_prompt")
                }
            ]

            user_payload = f"Manufacturer: {manufacturer}\nModel: {model}\nType: {device_type}\n\n"
            if doc_text_snippet:
                logger.info(f"KB generation for {manufacturer} {model}: using {len(doc_text_snippet)} chars of documentation")
                user_payload += f"Source Documentation:\n\n{doc_text_snippet}\n\n"
                user_payload += """Generate an EXHAUSTIVE and COMPREHENSIVE knowledge base entry. This should be a LONG, DETAILED document.

CRITICAL REQUIREMENTS:
- Extract EVERY piece of information from the documentation - do not summarize or abbreviate
- Include ALL parameter numbers, ALL values, ALL button sequences verbatim
- List EVERY command class, EVERY association group, EVERY specification
- Copy exact wording for procedures - do not paraphrase
- Include ALL troubleshooting steps, not just a summary
- The output should be 3000-5000 words minimum
- Better to include too much detail than too little

Include ALL sections: Overview, Installation, Configuration (with FULL parameter tables), Troubleshooting, and Specifications."""
            else:
                logger.info(f"KB generation for {manufacturer} {model}: NO documentation available")
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
                kwargs["max_tokens"] = 8000  # High limit for exhaustive KB extraction

            response = await client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content

            # Append source URLs section if available (don't rely on model to include them)
            if source_urls:
                sources_section = "\n\n## Sources\n"
                for url in source_urls:
                    sources_section += f"- [{url}]({url})\n"
                content = content + sources_section

            # Ingest generated content into RAG (use helper for compatibility)
            import datetime
            metadata = {
                "source": f"{manufacturer} {model} - Comprehensive Knowledge Base (AI)",
                "manufacturer": manufacturer,
                "model": model,
                "device_type": device_type,
                "category": "comprehensive_knowledge",
                "auto_generated": True,
                "generation_method": "openai_curated",
                # Source-aware ranking metadata (AI-generated has lower source quality)
                "source_type": "ai_generated",
                "fetched_at": datetime.datetime.now().isoformat(),
            }

            documents = [{"text": content, "metadata": metadata}]
            await self._rag_add_documents(documents, batch_size=1)
            logger.info(f"✅ Generated comprehensive knowledge for {manufacturer} {model} ({len(content)} chars)")
            return content

        except Exception as e:
            logger.error(f"Comprehensive knowledge generation failed: {e}")
            return None
