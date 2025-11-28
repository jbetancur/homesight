"""
Auto-fetch device documentation from manufacturer websites.

This module automatically downloads manuals when devices are discovered.
Zero configuration required – uses a robust tiered discovery pipeline.

NEW ARCHITECTURE (Tier-based Discovery):
Tier 1: Vendor Index (persistent, manufacturer-specific catalog)
Tier 2: Web Search API
Tier 3: LLM-assisted ranking and validation (NOT URL guessing)
Tier 4: AI-generated fallback documentation

This replaces the old LLM URL guessing + HTML scraping approach.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime

import fitz  # PyMuPDF
from pdfminer.high_level import extract_text as pdfminer_extract_text
from PIL import Image
import io
import pytesseract
import httpx
from .html_fetcher import fetch_html
from bs4 import BeautifulSoup
import pypdf
import tempfile
import urllib.parse

from .url_cache import URLCache
from .search_api import SearchAPI, SearchResult
from .manufacturer_domains import get_manufacturer_domains, register_discovered_domain
from vendor_indexer import VendorDocumentStorage, VendorIndexScheduler, get_scheduler

logger = logging.getLogger(__name__)


def get_known_manufacturers_from_config() -> Dict[str, Dict]:
    """Load known manufacturer patterns from config."""
    try:
        from config import get_config
        config = get_config()
        return config.rag.manufacturers or {}
    except Exception as e:
        logger.warning(f"Failed to load manufacturers from config: {e}")
        return {}


async def get_known_manufacturer_url(manufacturer: str, model: str) -> Optional[str]:
    """Check if we have a known URL pattern for this manufacturer."""
    manufacturers = get_known_manufacturers_from_config()
    mfr = manufacturers.get(manufacturer)
    if not mfr:
        return None

    patterns = mfr.get("patterns", {})
    if model in patterns:
        url = f"{mfr['base_url']}/{patterns[model]}"
        if await url_exists(url):
            logger.info(f"Found known URL pattern for {manufacturer} {model}: {url}")
            return url

    return None


# --------------------------------------------------------------------------------------
# LLM helper: Ranking, validation, and keyword generation (NOT URL guessing)
# --------------------------------------------------------------------------------------


class LLMDocumentFinder:
    """
    Use LLM for document discovery assistance.

    NEW ROLE:
    - Generate search keywords and synonyms
    - Rank search results by relevance
    - Validate document quality
    - Extract model variants/aliases

    NO LONGER DOES:
    - URL guessing (moved to search APIs)
    - Domain inference (moved to manufacturer_domains.py)
    """

    def __init__(self, openai_api_key: Optional[str] = None):
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("No OpenAI API key - LLM document finding disabled")
            self.enabled = False
        else:
            self.enabled = True

    async def _chat(self, system: str, user: str, model: Optional[str] = None) -> str:
        """Internal helper to call OpenAI chat with safe defaults."""
        from openai import AsyncOpenAI  # imported lazily
        client = AsyncOpenAI(api_key=self.api_key)
        # Choose model from parameter, environment, or fallback to a widely-available model
        chosen_model = model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"

        resp = await client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=800,
        )
        return resp.choices[0].message.content or ""

    async def generate_search_keywords(
        self,
        manufacturer: str,
        model: str,
        device_type: Optional[str] = None
    ) -> List[str]:
        """
        Generate search keywords and model variants/synonyms.

        This helps find documentation when manufacturers use different
        naming conventions or model variants.

        Args:
            manufacturer: Manufacturer name
            model: Model number
            device_type: Optional device type

        Returns:
            List of search keyword strings
        """
        if not self.enabled:
            # Fallback: basic keywords
            return [
                f"{manufacturer} {model} manual pdf",
                f"{manufacturer} {model} user guide",
                f"{manufacturer} {model} documentation"
            ]

        system = (
            "You are an expert at device documentation search. Generate search keywords "
            "that will help find official manuals. Include model variants, common "
            "alternative names, and document type keywords. Respond with JSON only."
        )

        user = f"""
Generate search keywords for finding documentation for:

Manufacturer: {manufacturer}
Model: {model}
Type: {device_type or 'unknown'}

Return JSON in this format:
{{
  "keywords": [
    "{manufacturer} {model} manual pdf",
    "{manufacturer} {model} user guide",
    "...additional search queries..."
  ],
  "model_variants": ["{model}", "...possible variants..."]
}}

Include:
- Full product name variations
- Model number with/without hyphens
- Common abbreviations
- Document types (manual, guide, datasheet, installation)
"""

        try:
            content = await self._chat(system, user)
            if "```" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    content = content[start:end]

            result = json.loads(content)
            keywords = result.get("keywords", [])

            # Always include basic fallback
            if not keywords:
                keywords = [
                    f"{manufacturer} {model} manual pdf",
                    f"{manufacturer} {model} user guide"
                ]

            return keywords[:5]  # Limit to top 5

        except Exception as e:
            logger.debug(f"LLM keyword generation failed: {e}")
            return [
                f"{manufacturer} {model} manual pdf",
                f"{manufacturer} {model} user guide"
            ]

    async def rank_search_results(
        self,
        manufacturer: str,
        model: str,
        results: List[SearchResult]
    ) -> List[SearchResult]:
        """
        Rank search results by relevance to the device.

        Uses LLM to assess which results are most likely to be
        official manufacturer documentation.

        Args:
            manufacturer: Manufacturer name
            model: Model number
            results: List of SearchResult objects

        Returns:
            Ranked list of SearchResult objects (best first)
        """
        if not self.enabled or not results:
            # Fallback: sort by existing relevance scores
            return sorted(results, key=lambda r: r.relevance_score, reverse=True)

        # Build prompt with result summaries
        result_summaries = []
        for idx, result in enumerate(results[:10]):  # Limit to top 10
            result_summaries.append(f"""
Result {idx + 1}:
URL: {result.url}
Title: {result.title}
Snippet: {result.snippet[:150]}
""")

        system = (
            "You are an expert at identifying official manufacturer documentation. "
            "Rank search results by likelihood of being the official manual. "
            "Prefer PDFs, official manufacturer domains, and exact model matches. "
            "Respond with JSON only."
        )

        user = f"""
Rank these search results for finding the official manual for:

Manufacturer: {manufacturer}
Model: {model}

Search Results:
{''.join(result_summaries)}

Return JSON in this format:
{{
  "ranked_indices": [1, 3, 2, ...],
  "confidence": "high|medium|low"
}}

The ranked_indices should be result numbers (1-based) in order of best to worst.
"""

        try:
            content = await self._chat(system, user, model="gpt-4o-mini")
            if "```" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    content = content[start:end]

            ranking = json.loads(content)
            ranked_indices = ranking.get("ranked_indices", [])

            # Reorder results based on LLM ranking
            ranked_results = []
            for idx in ranked_indices:
                if 1 <= idx <= len(results):
                    ranked_results.append(results[idx - 1])

            # Add any results not in the ranking
            seen_indices = set(ranked_indices)
            for idx, result in enumerate(results, 1):
                if idx not in seen_indices:
                    ranked_results.append(result)

            return ranked_results

        except Exception as e:
            logger.debug(f"LLM ranking failed: {e}")
            # Fallback to original ordering
            return sorted(results, key=lambda r: r.relevance_score, reverse=True)

    # DEPRECATED: Old URL guessing method removed
    # URL discovery is now handled by:
    # - Tier 1: Vendor Index
    # - Tier 2: Web Search API
    # LLM only used for ranking/validation


# --------------------------------------------------------------------------------------
# Shared HTTP utilities
# --------------------------------------------------------------------------------------


async def url_exists(url: str) -> bool:
    """Check if a URL is accessible."""
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.head(url)
            if resp.status_code == 200:
                return True
    except Exception:
        pass

    # Fallback to GET
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False


async def download_url_to_path(url: str, dest_path: Path) -> bool:
    """Download content from URL and write to dest path."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"Failed to download from {url}: HTTP {resp.status_code}")
                return False
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(resp.content)
            return True
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        return False


# --------------------------------------------------------------------------------------
# Manufacturer fetcher base + Generic fetcher
# --------------------------------------------------------------------------------------


class ManufacturerFetcher:
    """Base class for manufacturer-specific doc fetchers."""

    def __init__(self, cache_dir: Path, llm_finder: Optional[LLMDocumentFinder] = None):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.llm_finder = llm_finder

    def _get_cache_path(self, model: str, filename: str) -> Path:
        """Get cache path for a model's manual."""
        safe_model = model.replace("/", "-").replace(" ", "-")
        return self.cache_dir / safe_model / filename

    def _is_cached(self, model: str) -> Optional[Path]:
        """Check if manual is already cached."""
        model_dir = self.cache_dir / model.replace("/", "-").replace(" ", "-")
        if model_dir.exists():
            pdfs = list(model_dir.glob("*.pdf"))
            if pdfs:
                return pdfs[0]
            txts = list(model_dir.glob("*.txt"))
            if txts:
                return txts[0]
        return None

    async def fetch(self, model: str, manufacturer: Optional[str] = None, device_type: Optional[str] = None) -> Optional[Path]:
        """Fetch manual for a specific model. Must be implemented by subclasses."""
        raise NotImplementedError


class GenericFetcher(ManufacturerFetcher):
    """
    NEW TIERED DISCOVERY FETCHER

    Discovery pipeline:
    Tier 1: Vendor Index (persistent catalog)
    Tier 2: Web Search API (Brave → Bing fallback)
    Tier 3: LLM-assisted ranking
    Tier 4: AI-generated fallback (via document_service)
    """

    def __init__(
        self,
        cache_dir: Path,
        llm_finder: Optional[LLMDocumentFinder] = None,
        brave_api_key: Optional[str] = None,
        bing_api_key: Optional[str] = None
    ):
        super().__init__(cache_dir, llm_finder)

        self.vendor_storage = VendorDocumentStorage()

        # NEW SearchAPI (unified Brave + Bing)
        self.search_api = SearchAPI()

    async def fetch(
        self,
        model: str,
        manufacturer: Optional[str] = None,
        device_type: Optional[str] = None
    ) -> Optional[Path]:

        # -------------------------------
        # CACHE CHECK
        # -------------------------------
        cached = self._is_cached(model)
        if cached:
            logger.info(f"{manufacturer or 'Generic'} {model} manual found in cache")
            return cached

        manufacturer = manufacturer or ""

        if not manufacturer:
            logger.warning("No manufacturer specified, cannot discover docs")
            return None

        # -------------------------------
        # TIER 1 — Vendor Index
        # -------------------------------
        logger.info(f"[Tier 1] Checking vendor index for {manufacturer} {model}")

        indexed_docs = self.vendor_storage.lookup_docs(manufacturer, model)

        if indexed_docs:
            logger.info(f"[Tier 1] Found {len(indexed_docs)} indexed docs")

            for doc in indexed_docs[:3]:
                downloaded = await self._download_from_url(model, doc.url)
                if downloaded:
                    self.vendor_storage.update_last_verified(doc.url)
                    logger.info(f"✅ [Tier 1] Downloaded from vendor index: {doc.url}")
                    return downloaded

            logger.info("[Tier 1] Indexed URLs failed, continuing → Tier 2")

        # -------------------------------
        # TIER 2 — Unified Web Search
        # -------------------------------
        logger.info(f"[Tier 2] Searching web for {manufacturer} {model}")

        # Manufacturer domains for scoping
        domains = get_manufacturer_domains(manufacturer)
        logger.debug(f"[Tier 2] Manufacturer domains: {domains[:5]}")

        # Keyword generation (LLM or fallback)
        if self.llm_finder and self.llm_finder.enabled:
            keywords = await self.llm_finder.generate_search_keywords(
                manufacturer, model, device_type
            )
        else:
            keywords = [
                f"{manufacturer} {model} manual pdf",
                f"{manufacturer} {model} user guide",
                f"{manufacturer} {model} documentation"
            ]

        all_results: List[SearchResult] = []

        # Limit to 2 keyword searches to reduce API usage
        for keyword in keywords[:2]:
            try:
                logger.info(f"[Tier 2] Query → {keyword}")

                results = await self.search_api.search(
                    query=keyword,
                    max_results=10,
                    domains=domains[:5],
                    keywords=["manual", "pdf", "user", "guide", "datasheet", "installation", "troubleshooting"]
                )

                if results:
                    logger.info(f"[Tier 2] {len(results)} results from SearchAPI for '{keyword}'")
                else:
                    logger.info(f"[Tier 2] No results found for '{keyword}'")

                all_results.extend(results)

            except Exception as e:
                logger.warning(f"[Tier 2] Search failed for '{keyword}': {e}")

        if not all_results:
            logger.info("[Tier 2] No search results found, cannot proceed")
            return None

        # -------------------------------
        # TIER 3 — LLM Ranking
        # -------------------------------
        logger.info(f"[Tier 3] Ranking {len(all_results)} search results")

        if self.llm_finder and self.llm_finder.enabled:
            ranked_results = await self.llm_finder.rank_search_results(
                manufacturer, model, all_results
            )
        else:
            ranked_results = sorted(all_results, key=lambda r: r.relevance_score, reverse=True)

        # Attempt downloading results in ranked order
        for result in ranked_results[:5]:  # Try top 5
            logger.info(f"[Tier 3] Trying → {result.url} (score {result.relevance_score:.2f})")

            downloaded = await self._download_from_url(model, result.url)
            if downloaded:
                logger.info(f"✅ [Tier 3] Downloaded: {result.url}")

                # Register domain for future manufacturer scoping
                register_discovered_domain(manufacturer, result.url)

                # Insert into vendor index for future fetches
                from vendor_indexer import IndexedDocument
                doc = IndexedDocument(
                    manufacturer=manufacturer,
                    model=model,
                    url=result.url,
                    title=result.title,
                    document_type="pdf" if result.url.lower().endswith(".pdf") else "html",
                    discovered_at=datetime.now()
                )
                self.vendor_storage.add_document(doc)

                return downloaded

        logger.info(f"⚠️ No docs found for {manufacturer} {model} — all tiers exhausted")
        return None

    # ------------------------------------------------------------
    # INTERNAL HELPERS (unchanged)
    # ------------------------------------------------------------

    async def _download_from_url(self, model: str, url: str) -> Optional[Path]:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)

            if resp.status_code != 200:
                logger.warning(f"Failed to download from {url}: HTTP {resp.status_code}")
                return None

            content_type = resp.headers.get("content-type", "").lower()

            # PDF direct
            if "pdf" in content_type or url.lower().endswith(".pdf"):
                filename = f"{model}_manual.pdf"
                cache_path = self._get_cache_path(model, filename)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(resp.content)
                logger.info(f"PDF downloaded for {model} from {url}")
                return cache_path

            # HTML auto-extract
            html = resp.text
            pdf_url = self._extract_pdf_link_from_html(html, base_url=str(resp.url))
            if pdf_url:
                logger.info(f"Found PDF link → {pdf_url}")
                return await self._download_from_url(model, pdf_url)

            readable_text = await fetch_html(str(resp.url))
            if readable_text and len(readable_text) > 200:
                filename = f"{model}_manual.txt"
                cache_path = self._get_cache_path(model, filename)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(readable_text, encoding="utf-8")
                logger.info(f"HTML converted → {cache_path}")
                return cache_path

            # Fallback: raw HTML → text
            return await self._download_html_as_text(model, html)

        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return None

    def _extract_pdf_link_from_html(self, html: str, base_url: str) -> Optional[str]:
        try:
            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a", href=True)

            # Strict manual keywords first
            for a in links:
                href = a["href"]
                text = (a.get_text() or "").lower()
                if ".pdf" in href.lower() and any(k in text for k in ["manual", "guide", "user", "documentation", "datasheet"]):
                    return urllib.parse.urljoin(base_url, href)

            # Loose matching second pass
            for a in links:
                href = a["href"]
                if ".pdf" in href.lower():
                    return urllib.parse.urljoin(base_url, href)

            return None

        except Exception:
            return None

    async def _download_html_as_text(self, model: str, html: str) -> Optional[Path]:
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if not text:
                return None
            cache_path = self._get_cache_path(model, f"{model}_manual.txt")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text, encoding="utf-8")
            logger.info(f"Raw HTML text saved → {cache_path}")
            return cache_path
        except Exception as e:
            logger.error(f"HTML→text conversion failed: {e}")
            return None


# --------------------------------------------------------------------------------------
# DocumentAutoFetcher: main orchestration entrypoint
# --------------------------------------------------------------------------------------


class DocumentAutoFetcher:
    """
    Automatically fetch device documentation with zero configuration.

    Hybrid strategy:
    - Use manufacturer-specific fetchers when available (Aqara, Zooz, Shelly, ...)
    - Fall back to GenericFetcher with LLM + search
    - Ingest text/PDF into RAG
    """

    def __init__(self, rag_engine, cache_dir: Path = None, openai_api_key: Optional[str] = None, brave_api_key: Optional[str] = None, bing_api_key: Optional[str] = None, rag_config=None):
        self.rag = rag_engine
        self.cache_dir = cache_dir or Path.home() / "homesight" / "manuals"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.batch_size_documents = (rag_config.batch_size_documents if rag_config else None) or 3

        self.llm_finder = LLMDocumentFinder(openai_api_key)
        self.url_cache = URLCache()

        # Get search API keys from environment if not provided
        self.brave_api_key = brave_api_key or os.getenv("BRAVE_SEARCH_API_KEY")
        self.bing_api_key = bing_api_key or os.getenv("BING_SEARCH_API_KEY")

        # All devices use generic fetcher with NEW tiered discovery
        self.generic_fetcher = GenericFetcher(
            self.cache_dir,
            self.llm_finder,
            brave_api_key=self.brave_api_key,
            bing_api_key=self.bing_api_key
        )

        # Initialize vendor index scheduler (background crawling)
        self.vendor_scheduler = get_scheduler()

        logger.info("DocumentAutoFetcher initialized with tiered discovery pipeline")

    async def cleanup_device(self, manufacturer: str, model: str) -> None:
        """
        Clean up all cached data for a device (for force refresh).
        - Remove from URL cache
        - Delete manual files
        Note: RAG cleanup is handled separately by document_service
        """
        # Clear URL cache entry
        try:
            key = self.url_cache.get_device_key(manufacturer, model)
            self.url_cache._cache.pop(key, None)
            self.url_cache._save_cache()
            logger.info(f"Cleared URL cache for {manufacturer} {model}")
        except Exception as e:
            logger.warning(f"Error clearing URL cache: {e}")

        # Delete manual files
        try:
            model_dir = self.cache_dir / model.replace("/", "-").replace(" ", "-")
            if model_dir.exists():
                import shutil
                shutil.rmtree(model_dir)
                logger.info(f"Deleted manual files for {manufacturer} {model}")
        except Exception as e:
            logger.warning(f"Error deleting manual files: {e}")

    async def fetch_for_device(self, device, force: bool = False) -> bool:
        """
        Auto-fetch and ingest documentation for a device.

        Discovery strategy:
        1. If force=True: clean up all caches and re-ingest fresh
        2. Check if docs already indexed in RAG
        3. Check URL cache (previously discovered)
        4. Call LLM to find documentation URL (auto-discovery)
        5. Cache discovered URL for future use
        6. Download and ingest

        Args:
            device: DeviceProfile or Dict (backward compatible)
            force: If True, bypass cache and RAG check, re-ingest everything

        Returns:
            True if docs were fetched/ingested, False otherwise.
        """
        # Handle both DeviceProfile and legacy Dict
        if hasattr(device, 'manufacturer'):
            # DeviceProfile object
            manufacturer = device.manufacturer
            model = device.model
            device_type = device.device_type if isinstance(device.device_type, str) else device.device_type.value
            device_dict = device.to_dict()
        else:
            # Legacy dict format
            manufacturer = (device.get("manufacturer") or "").strip()
            model = (device.get("model") or "").strip()
            device_type = device.get("type", "")
            device_dict = device

        if not manufacturer or not model:
            logger.warning(f"Device missing manufacturer or model")
            return False

        # If force=True, clean up all caches first
        if force:
            logger.info(f"Force refresh requested for {manufacturer} {model} - clearing caches")
            await self.cleanup_device(manufacturer, model)

        # Already indexed in RAG? (skip if force refresh)
        if not force and self._is_indexed(manufacturer, model):
            logger.info(f"Docs already indexed for {manufacturer} {model}")
            return True

        # Check URL cache first
        cached_url = self.url_cache.get(manufacturer, model)
        if cached_url:
            logger.info(f"Found cached URL for {manufacturer} {model}: {cached_url}")
            doc_path = await self.generic_fetcher._download_from_url(model, cached_url)
            if doc_path:
                await self._ingest_document(doc_path, device_dict)
                return True
            else:
                logger.warning(f"Cached URL no longer valid: {cached_url}")

        # Check known manufacturer patterns (before LLM for reliability)
        known_url = await get_known_manufacturer_url(manufacturer, model)
        if known_url:
            logger.info(f"Found known URL for {manufacturer} {model}: {known_url}")
            doc_path = await self.generic_fetcher._download_from_url(model, known_url)
            if doc_path:
                self.url_cache.set(manufacturer, model, known_url, confidence="high")
                await self._ingest_document(doc_path, device_dict)
                return True
            else:
                logger.warning(f"Known URL failed to download: {known_url}")

        # Use NEW tiered discovery via GenericFetcher
        logger.info(f"Starting tiered discovery for {manufacturer} {model}")
        doc_path = await self.generic_fetcher.fetch(
            model=model,
            manufacturer=manufacturer,
            device_type=device_type
        )

        if doc_path:
            logger.info(f"✅ Tiered discovery succeeded for {manufacturer} {model}")
            await self._ingest_document(doc_path, device_dict)
            return True

        logger.warning(f"⚠️ Tiered discovery failed for {manufacturer} {model} - all tiers exhausted")
        # Tier 4 (AI-generated fallback) is handled by document_service
        return False

    def _is_indexed(self, manufacturer: str, model: str) -> bool:
        """Check if device docs are already in RAG."""
        try:
            # ChromaDB expects a single operator in the `where` clause (e.g. $and/$or).
            where = {"$and": [{"manufacturer": manufacturer.title()}, {"model": model}]}
            results = self.rag.query(
                query_text=f"{manufacturer} {model}",
                n_results=1,
                where=where,
            )
            return bool(results)
        except Exception:
            return False

    async def _ingest_document(self, doc_path: Path, device: Dict):
        """Ingest document into RAG (async batched for performance)."""
        try:
            if doc_path.suffix.lower() == ".pdf":
                text = self._extract_pdf_text(doc_path)
            else:
                text = doc_path.read_text(encoding="utf-8")

            if not text or len(text) < 100:
                logger.warning(f"Document too short or empty: {doc_path}")
                return

            metadata = {
                "source": f"{device['manufacturer']} {device['model']} Manual",
                "manufacturer": device["manufacturer"].title(),
                "model": device["model"],
                "device_type": device.get("type", "unknown"),
                "category": "device_manual",
                "auto_fetched": True,
                "file_path": str(doc_path),
            }

            chunk_size = 2000
            documents = []
            if len(text) > chunk_size:
                chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
                total = len(chunks)
                for i, chunk in enumerate(chunks):
                    chunk_meta = metadata.copy()
                    chunk_meta["chunk"] = i + 1
                    chunk_meta["total_chunks"] = total
                    documents.append({"text": chunk, "metadata": chunk_meta})
                logger.info(f"Split {doc_path.name} into {len(chunks)} chunks")
            else:
                documents.append({"text": text, "metadata": metadata})

            # Attempt async ingestion, but be compatible with RAG clients that expose
            # synchronous ingestion APIs (add_documents_batch / add_document).
            try:
                if hasattr(self.rag, "add_documents_async"):
                    await self.rag.add_documents_async(documents, batch_size=self.batch_size_documents)
                elif hasattr(self.rag, "add_documents_batch"):
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.rag.add_documents_batch, documents, self.batch_size_documents)
                elif hasattr(self.rag, "add_document"):
                    # Fallback: add documents one-by-one
                    for doc in documents:
                        try:
                            self.rag.add_document(doc.get("text", ""), doc.get("metadata", {}))
                        except Exception:
                            logger.debug("Failed to add single document via fallback add_document")
                else:
                    logger.error("RAG engine does not expose a known ingestion API")

                logger.info(f"Ingested {doc_path.name} ({len(documents)} document(s))")
            except Exception as e:
                logger.error(f"Error during ingestion into RAG: {e}")

        except Exception as e:
            logger.error(f"Error ingesting document {doc_path}: {e}")

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        logger.info(f"[PDF] Extracting text from: {pdf_path}")

        text_output = []
        image_output = []

        # --------------------------------------------
        # TIER 1 — PDFMiner (best structured text)
        # --------------------------------------------
        try:
            logger.info("[PDF] Trying PDFMiner extraction...")
            text = pdfminer_extract_text(str(pdf_path))
            if text and len(text.strip()) > 80:
                logger.info("[PDF] PDFMiner succeeded")
                return text
            else:
                logger.info("[PDF] PDFMiner returned insufficient text")
        except Exception as e:
            logger.warning(f"[PDF] PDFMiner failed: {e}")

        # --------------------------------------------
        # TIER 2 — PyMuPDF extraction (text + images)
        # --------------------------------------------
        try:
            logger.info("[PDF] Trying PyMuPDF extraction...")
            doc = fitz.open(str(pdf_path))

            for page_num, page in enumerate(doc, start=1):
                extracted = page.get_text("text")
                if extracted.strip():
                    text_output.append(f"[Page {page_num}]\n{extracted}")

                # Extract images + OCR
                for img_index, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image = Image.open(io.BytesIO(image_bytes))

                    if not extracted.strip():  # scanned page
                        ocr_text = pytesseract.image_to_string(image)
                        if ocr_text.strip():
                            text_output.append(f"[Page {page_num} OCR]\n{ocr_text}")

            combined = "\n\n".join(text_output)
            if len(combined.strip()) > 30:
                logger.info("[PDF] PyMuPDF succeeded")
                return combined
            else:
                logger.info("[PDF] PyMuPDF returned insufficient text")

        except Exception as e:
            logger.warning(f"[PDF] PyMuPDF failed: {e}")

        # --------------------------------------------
        # TIER 3 — pypdf fallback
        # --------------------------------------------
        try:
            logger.info("[PDF] Trying pypdf fallback...")
            reader = pypdf.PdfReader(str(pdf_path))
            parts = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    parts.append(f"[Page {i+1}]\n{page_text}")

            final = "\n\n".join(parts)
            logger.info("[PDF] pypdf fallback succeeded")
            return final

        except Exception as e:
            logger.error(f"[PDF] pypdf fallback failed: {e}")

        logger.error("[PDF] All PDF extractors failed — returning empty text")
        return ""
