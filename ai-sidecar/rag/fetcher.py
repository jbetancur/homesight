"""
Auto-fetch device documentation from manufacturer websites.

This module automatically downloads manuals when devices are discovered.
Zero configuration required – uses LLM + heuristics to intelligently find documentation.

Hybrid strategy:
- Prefer official manufacturer PDFs
- Use brand-specific fetchers where patterns are known (e.g. Aqara, Zooz, Shelly)
- Fall back to generic LLM-assisted + search-based discovery
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import httpx
from bs4 import BeautifulSoup
import pypdf
import tempfile
import urllib.parse

from .url_cache import URLCache

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
# LLM helper: find manufacturer docs & metadata
# --------------------------------------------------------------------------------------


class LLMDocumentFinder:
    """Use LLM to intelligently find manufacturer documentation and doc patterns."""

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

    async def infer_manufacturer_metadata(self, manufacturer: str) -> Dict[str, str]:
        """
        Ask the LLM for high-level manufacturer metadata:
        - canonical name
        - primary website/domain
        - docs/support base URL pattern

        This is used to constrain search (site:domain) and generate
        better candidate URLs.
        """
        if not self.enabled:
            return {}

        system = (
            "You are an expert at identifying official manufacturer websites and "
            "documentation entrypoints. Respond ONLY with strict JSON. Do NOT guess if uncertain."
        )
        user = f"""
Identify metadata for this manufacturer:

Manufacturer: "{manufacturer}"

Return JSON ONLY in this format:
{{
  "canonical_name": "Full Canonical Name or empty if unknown",
  "primary_domain": "https://example.com or empty if unknown",
  "support_or_docs_base": "https://example.com/support or https://example.com/docs or empty if unknown"
}}
If you are not at least reasonably confident, return empty strings for fields.
"""

        try:
            content = await self._chat(system, user)
            # Strip code fences if present
            if "```" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    content = content[start:end]

            meta = json.loads(content)
            if not isinstance(meta, dict):
                return {}
            return {
                "canonical_name": meta.get("canonical_name") or "",
                "primary_domain": meta.get("primary_domain") or "",
                "support_or_docs_base": meta.get("support_or_docs_base") or "",
            }
        except Exception as e:
            logger.error(f"LLM metadata inference failed for {manufacturer}: {e}")
            return {}

    async def find_documentation_url(
        self,
        manufacturer: str,
        model: str,
        device_type: Optional[str] = None,
        preferred_domain: Optional[str] = None,
    ) -> Tuple[Optional[str], List[str]]:
        """
        Intelligently find an official documentation URL using the LLM.

        Strategy:
        1. Ask LLM for likely documentation URLs & search queries.
        2. Validate URLs via HTTP HEAD/GET.
        3. Return a (url, search_queries) tuple.

        NOTE: We always validate URLs; if they 404, we ignore them.
        """
        if not self.enabled:
            logger.warning("LLM document finder not enabled - no API key")
            return None, []

        device_info = f"{manufacturer} {model}"
        if device_type:
            device_info += f" ({device_type})"

        manufacturer = manufacturer.strip()
        model = model.strip()

        system = (
            "You are an expert at finding OFFICIAL manufacturer documentation and product manuals.\n"
            "You MUST NOT invent or guess non-existent URLs. Only return URLs that are highly likely to exist, "
            "based on known patterns or widely referenced documentation.\n"
            "If unsure, keep 'expected_doc_url' and 'pdf_manual_url' empty and rely on 'search_queries'.\n"
            "Respond with STRICT JSON only."
        )

        user = f"""
Find official documentation for this device:

Device: "{device_info}"

If you know the manufacturer documentation patterns, include them.
Only include URLs that are typical/likely for the official site. If not reasonably confident, leave URL fields empty.

Return JSON ONLY in this format:
{{
  "manufacturer_name": "Full name if known, else empty",
  "manufacturer_website": "https://... or empty",
  "doc_base_url": "https://... documentation or support base URL, or empty",
  "expected_doc_url": "https://... likely product documentation page (HTML), or empty",
  "pdf_manual_url": "https://... direct PDF link if known, or empty",
  "search_queries": [
    "site:manufacturer.com {manufacturer} {model} manual pdf",
    "site:manufacturer.com {model} documentation"
  ],
  "confidence": "high|medium|low",
  "notes": "Brief notes on where docs are usually located"
}}
"""

        try:
            content = await self._chat(system, user)
            if "```" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    content = content[start:end]

            result = json.loads(content)
            if not isinstance(result, dict):
                return None, []

            # If we have a preferred domain from the caller, rewrite search queries to constrain site:
            search_queries = result.get("search_queries", []) or []
            if preferred_domain:
                domain = preferred_domain.replace("https://", "").replace("http://", "").strip("/")
                constrained_queries = []
                for q in search_queries:
                    if f"site:{domain}" not in q:
                        constrained_queries.append(f"site:{domain} {q}")
                    else:
                        constrained_queries.append(q)
                search_queries = constrained_queries

            # Validate candidate URLs in order of specificity
            for key in ("pdf_manual_url", "expected_doc_url", "doc_base_url"):
                url = result.get(key) or None
                if url and await url_exists(url):
                    logger.info(f"LLM suggested {key} for {device_info}: {url}")
                    return url, search_queries

            logger.info(f"LLM could not find direct URL for {device_info}, falling back to search queries.")
            return None, search_queries

        except Exception as e:
            logger.error(f"Error using LLM to find documentation: {e}")
            return None, []


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
    Generic fetcher using:
    - LLM to locate likely doc URLs
    - Web search (DuckDuckGo HTML) with "site:" scoping when possible
    - HTML parsing to find PDF/manual links
    """

    async def fetch(self, model: str, manufacturer: Optional[str] = None, device_type: Optional[str] = None) -> Optional[Path]:
        # Check cache first
        cached = self._is_cached(model)
        if cached:
            logger.info(f"{manufacturer or 'Generic'} {model} manual found in cache")
            return cached

        manufacturer = manufacturer or ""
        preferred_domain = None

        # Try to infer manufacturer metadata to constrain search / docs
        if self.llm_finder and self.llm_finder.enabled and manufacturer:
            meta = await self.llm_finder.infer_manufacturer_metadata(manufacturer)
            preferred_domain = meta.get("primary_domain") or None

        # Use LLM to find documentation URL with search fallback
        doc_url = None
        search_queries: List[str] = []
        if self.llm_finder and self.llm_finder.enabled:
            doc_url, search_queries = await self.llm_finder.find_documentation_url(
                manufacturer=manufacturer,
                model=model,
                device_type=device_type,
                preferred_domain=preferred_domain,
            )

        # 1) Try direct URL first
        if doc_url:
            downloaded = await self._download_from_url(model, doc_url)
            if downloaded:
                return downloaded
            logger.warning(f"Failed to download from LLM-provided URL: {doc_url}, trying search fallback...")

        # 2) Fallback to search-based discovery if direct URL failed
        if search_queries:
            for q in search_queries[:2]:  # limit for performance
                doc_path = await self._search_and_download(model, q)
                if doc_path:
                    return doc_path

        logger.info(f"Could not find docs for {manufacturer or 'Unknown'} {model} using generic fetcher")
        return None

    async def _download_from_url(self, model: str, url: str) -> Optional[Path]:
        """Download either direct PDF or HTML and convert/extract."""
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"Failed to download from {url}: HTTP {resp.status_code}")
                    return None

                content_type = resp.headers.get("content-type", "").lower()
                if "pdf" in content_type or url.lower().endswith(".pdf"):
                    filename = f"{model}_manual.pdf"
                    cache_path = self._get_cache_path(model, filename)
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_bytes(resp.content)
                    logger.info(f"Downloaded PDF documentation for {model} from {url}")
                    return cache_path

                # HTML or other: try to find PDF links first
                html = resp.text
                pdf_url = self._extract_pdf_link_from_html(html, base_url=str(resp.url))
                if pdf_url:
                    logger.info(f"Found PDF link in HTML for {model}: {pdf_url}")
                    return await self._download_from_url(model, pdf_url)

                # Fallback: save HTML as text
                return await self._download_html_as_text(model, html)
        except Exception as e:
            logger.error(f"Error downloading from {url}: {e}")
            return None

    def _extract_pdf_link_from_html(self, html: str, base_url: str) -> Optional[str]:
        """Scan HTML for links that look like PDFs/manuals."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a", href=True)

            # First pass: look for PDFs with strong manual indicators
            for a in links:
                href = a["href"]
                text = (a.get_text() or "").lower()
                if ".pdf" in href.lower() and ("manual" in text or "guide" in text or "user" in text or "documentation" in text or "datasheet" in text):
                    return urllib.parse.urljoin(base_url, href)

            # Second pass: look for any PDF link (less strict)
            for a in links:
                href = a["href"]
                if ".pdf" in href.lower():
                    logger.info(f"Found PDF link with less strict matching: {href}")
                    return urllib.parse.urljoin(base_url, href)

            return None
        except Exception:
            return None

    async def _download_html_as_text(self, model: str, html: str) -> Optional[Path]:
        """Save HTML as text, stripping tags."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if not text:
                return None
            cache_path = self._get_cache_path(model, f"{model}_manual.txt")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text, encoding="utf-8")
            logger.info(f"Saved HTML text docs for {model} to {cache_path}")
            return cache_path
        except Exception as e:
            logger.error(f"Error converting HTML to text: {e}")
            return None

    async def _search_and_download(self, model: str, search_query: str) -> Optional[Path]:
        """
        Search for documentation using DuckDuckGo HTML and download first relevant result.
        Prefer links that look like manuals or PDFs.
        """
        try:
            search_url = f"https://duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
            logger.info(f"Searching for docs using query: {search_query}")

            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                resp = await client.get(search_url, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"Search failed: HTTP {resp.status_code}")
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")
                result_links: List[str] = []

                for a in soup.find_all("a", {"class": "result__a"}, limit=10):
                    href = a.get("href")
                    if not href:
                        continue

                    # DuckDuckGo wraps URLs; unwrap uddg param if present
                    if href.startswith("//duckduckgo.com/l/"):
                        try:
                            parsed = urllib.parse.urlparse(f"https:{href}")
                            params = urllib.parse.parse_qs(parsed.query)
                            if "uddg" in params:
                                href = params["uddg"][0]
                        except Exception:
                            continue

                    text = (a.get_text() or "").lower()
                    if "manual" in text or "documentation" in text or "support" in text or href.lower().endswith(".pdf"):
                        result_links.append(href)
                        if len(result_links) >= 3:
                            break

                if not result_links:
                    logger.info(f"No obvious manual links found in search results for '{search_query}'")
                    return None

                for url in result_links[:2]:
                    logger.info(f"Trying to download from search result: {url}")
                    doc_path = await self._download_from_url(model, url)
                    if doc_path:
                        logger.info(f"✅ Successfully downloaded docs from search: {url}")
                        return doc_path

                logger.warning(f"Could not download valid docs from search for '{search_query}'")
                return None

        except Exception as e:
            logger.error(f"Error during web search: {e}")
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

    def __init__(self, rag_engine, cache_dir: Path = None, openai_api_key: Optional[str] = None, rag_config=None):
        self.rag = rag_engine
        self.cache_dir = cache_dir or Path.home() / ".homesight" / "manuals"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.batch_size_documents = (rag_config.batch_size_documents if rag_config else None) or 3

        self.llm_finder = LLMDocumentFinder(openai_api_key)
        self.url_cache = URLCache()

        # All devices use generic fetcher (no special per-manufacturer logic anymore)
        # LLM discovery + URL caching handles variation automatically
        self.generic_fetcher = GenericFetcher(self.cache_dir, self.llm_finder)

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

        # Discover URL via LLM (fallback for unknown manufacturers)
        logger.info(f"Discovering documentation for {manufacturer} {model}")
        doc_url, search_queries = await self.llm_finder.find_documentation_url(
            manufacturer=manufacturer,
            model=model,
            device_type=device_type,
        )

        if doc_url:
            logger.info(f"LLM found documentation URL: {doc_url}")
            doc_path = await self.generic_fetcher._download_from_url(model, doc_url)
            if doc_path:
                self.url_cache.set(manufacturer, model, doc_url, confidence="high")
                await self._ingest_document(doc_path, device_dict)
                return True

        # Fallback to search-based discovery
        if search_queries:
            logger.info(f"Trying search-based discovery with {len(search_queries)} queries")
            for q in search_queries[:2]:  # limit for performance
                doc_path = await self.generic_fetcher._search_and_download(model, q)
                if doc_path:
                    logger.info(f"Found via search query: {q}")
                    await self._ingest_document(doc_path, device_dict)
                    return True

        logger.warning(f"Could not find documentation for {manufacturer} {model}")
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
        """Extract text from PDF with simple page markers."""
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            parts: List[str] = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                page_text = page_text.strip()
                if page_text:
                    parts.append(f"[Page {i + 1}]\n{page_text}")
            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"Error extracting PDF text from {pdf_path}: {e}")
            return ""


