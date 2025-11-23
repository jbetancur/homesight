"""Enhanced document discovery and ingestion service"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from rag.fetcher import DocumentAutoFetcher, LLMDocumentFinder
from rag.engine import RAGEngine
from config import get_config

logger = logging.getLogger(__name__)


class DocumentService:
    """
    Enhanced document service that discovers and ingests multiple types of documentation:
    - Official manufacturer PDFs
    - Support forums
    - Reddit discussions
    - YouTube troubleshooting guides (transcripts)
    - Community knowledge
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

        # Get configuration
        config = get_config()
        self.config = config

        # Initialize document fetcher with RAG config
        self.fetcher = DocumentAutoFetcher(
            rag_engine=rag_engine,
            cache_dir=self.cache_dir,
            openai_api_key=openai_api_key,
            rag_config=config.rag
        )

        # Store batch size for community sources from config
        self.batch_size_community = config.rag.batch_size_community

        # Initialize enhanced LLM finder
        self.llm_finder = LLMDocumentFinder(openai_api_key)

    async def discover_and_ingest_device_docs(self, device: Dict[str, Any]) -> Dict[str, Any]:
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
            device: Dict with manufacturer, model, type

        Returns:
            Summary of discovered and ingested documents
        """
        manufacturer = device.get("manufacturer", "")
        model = device.get("model", "")
        device_type = device.get("type", "")

        if not manufacturer or not model:
            logger.warning(f"Device missing manufacturer or model: {device}")
            return {"status": "error", "message": "Missing device info"}

        logger.info(f"Starting document discovery for {manufacturer} {model}")

        results = {
            "manufacturer": manufacturer,
            "model": model,
            "sources_found": []
        }

        # 1. PRIMARY: Fetch official documentation PDFs if available
        # This provides the authoritative source we want OpenAI to ground against.
        doc_path = None
        try:
            official_success = await self.fetcher.fetch_for_device(device)
            if official_success:
                results["sources_found"].append("official_pdf_manual")
                logger.info(f"✅ Official PDF docs found for {manufacturer} {model}")
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

            if self.llm_finder.enabled:
                await self._generate_comprehensive_knowledge(device, documentation_text=documentation_text)
                results["sources_found"].append("ai_generated_knowledge")
                logger.info(f"✅ Generated comprehensive knowledge for {manufacturer} {model}")
        except Exception as e:
            logger.error(f"Knowledge generation failed: {e}")

        results["status"] = "success" if results["sources_found"] else "partial"
        results["total_sources"] = len(results["sources_found"])

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


    async def _generate_comprehensive_knowledge(self, device: Dict[str, Any], documentation_text: Optional[str] = None):
        """
        Generate comprehensive, curated knowledge base entry using OpenAI

        This leverages OpenAI's training data to create high-quality device documentation
        that includes:
        - Exact specifications and model details
        - Battery/power requirements with part numbers
        - Troubleshooting procedures with specific steps
        - Integration guidance
        - Common issues and solutions

        This is preferable to web scraping because:
        - Curated and verified information
        - Faster than searching web + scraping
        - You're already paying for the API
        - Consistent formatting and quality
        """
        if not self.llm_finder.enabled:
            return

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.llm_finder.api_key)

            manufacturer = device.get("manufacturer", "")
            model = device.get("model", "")
            device_type = device.get("type", "")

            # Attach documentation text if available; truncate to reasonable size for prompts
            doc_text_snippet = None
            if documentation_text:
                # Limit to first ~30k chars to keep prompt reasonable
                doc_text_snippet = documentation_text[:30000]

            prompt = f"""You are a technical documentation expert. You will generate a COMPREHENSIVE, DETAILED knowledge base entry for a device using ONLY verifiable information from the provided input text and publicly known manufacturer data.

⚠️ STRICT RULES (NEVER BREAK THESE):
- NEVER invent or guess specifications, dimensions, button sequences, pairing steps, or any technical detail.
- If data is not explicitly known or publicly documented, write:
  "Information not publicly documented by manufacturer."
- DO NOT infer facts from similar models.
- DO NOT hallucinate part numbers, frequencies, or metrics.
- ONLY use information that is explicitly in the provided documentation or widely confirmed by the manufacturer.

You may only use:
✔ The manufacturer-provided document
✔ The device name/model
✔ Widely confirmed public information
✔ Industry-standard general behaviors (ONLY if noted as “typical, but not confirmed”)

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
"Manufacturer specification not publicly available."

---

2. SETUP & PAIRING
- Step-by-step pairing instructions
- Factory reset instructions
- LED indicator chart
- Troubleshooting for failed pairing

If missing, write:
"Exact procedure not provided by manufacturer."

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
"Information not publicly documented by manufacturer."

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
                    "content": """
            You are an expert technical writer generating device documentation.
            Follow these rules STRICTLY:

            1. USE ONLY information explicitly provided in the user prompt or the provided documentation text.
            2. NEVER guess, infer, or create any technical details. If a detail is not present in the documentation text, state: "Manufacturer specification not publicly available."
            3. NEVER invent or hallucinate part numbers, pairing steps, reset sequences, LED patterns, or exact measurements.
            4. If documentation text is not provided, return a short 'unverified' summary and explicitly label it as unverified.
            5. Output must be structured Markdown suitable for ingestion.
            6. Accuracy is more important than completeness.
            """
                }
            ]

            user_payload = f"Manufacturer: {manufacturer}\nModel: {model}\nType: {device_type}\n\n"
            if doc_text_snippet:
                user_payload += f"Source Documentation:\n\n{doc_text_snippet}\n\n"
            else:
                user_payload += "Source Documentation: (none provided)\n\n"

            user_payload += "Please generate the structured knowledge base entry as described. If no documentation is provided, produce a short UNVERIFIED summary and clearly label it."

            messages.append({"role": "user", "content": user_payload})

            response = await client.chat.completions.create(
                model=self.config.llm.openai_model,
                messages=messages,
                temperature=0.0,
                max_tokens=2000,
            )

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

        except Exception as e:
            logger.error(f"Comprehensive knowledge generation failed: {e}")
