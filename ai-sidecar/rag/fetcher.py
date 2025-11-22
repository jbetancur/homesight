"""
Auto-fetch device documentation from manufacturer websites

This module automatically downloads manuals when devices are discovered.
Zero configuration required - uses LLM to intelligently find documentation.
"""

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict
import httpx
from bs4 import BeautifulSoup
import pypdf
import shutil
import tempfile

logger = logging.getLogger(__name__)


class LLMDocumentFinder:
    """Use LLM to intelligently find manufacturer documentation"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("No OpenAI API key - LLM document finding disabled")
            self.enabled = False
        else:
            self.enabled = True
    
    async def find_documentation_url(
        self,
        manufacturer: str,
        model: str,
        device_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Use GPT to find the most likely documentation URL
        
        Returns:
            URL to documentation PDF or support page, or None if not found
        """
        if not self.enabled:
            logger.warning("LLM document finder not enabled - no API key")
            return None
        
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key)
            
            device_info = f"{manufacturer} {model}"
            if device_type:
                device_info += f" ({device_type})"
            
            prompt = f"""Find the official documentation/manual URL for this device:

Device: {device_info}

Please provide:
1. The official manufacturer support/documentation page URL
2. Direct PDF manual URL if available
3. Alternative documentation sources if official not available

Respond in JSON format:
{{
    "official_support_url": "url here or null",
    "pdf_manual_url": "url here or null",
    "search_queries": ["query 1", "query 2"],
    "notes": "any helpful notes"
}}

Focus on official manufacturer sources first. Be conservative - only suggest URLs you're confident about."""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",  # Cheap and fast
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that finds official device documentation. Always prioritize manufacturer websites."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Low temperature for factual responses
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            
            # Parse JSON response
            try:
                result = json.loads(content)
                
                # Return PDF URL if available, otherwise support page
                if result.get("pdf_manual_url"):
                    logger.info(f"LLM found PDF URL for {device_info}: {result['pdf_manual_url']}")
                    return result["pdf_manual_url"]
                elif result.get("official_support_url"):
                    logger.info(f"LLM found support page for {device_info}: {result['official_support_url']}")
                    return result["official_support_url"]
                else:
                    logger.warning(f"LLM couldn't find documentation for {device_info}")
                    return None
                    
            except json.JSONDecodeError:
                logger.error(f"LLM response not valid JSON: {content}")
                return None
                
        except Exception as e:
            logger.error(f"Error using LLM to find documentation: {e}")
            return None


class ManufacturerFetcher:
    """Base class for manufacturer-specific doc fetchers"""
    
    def __init__(self, cache_dir: Path, llm_finder: Optional[LLMDocumentFinder] = None):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.llm_finder = llm_finder
    
    async def fetch(self, model: str) -> Optional[Path]:
        """Fetch manual for a specific model. Returns path to cached PDF."""
        raise NotImplementedError
    
    def _get_cache_path(self, model: str, filename: str) -> Path:
        """Get cache path for a model's manual"""
        safe_model = model.replace("/", "-").replace(" ", "-")
        return self.cache_dir / safe_model / filename
    
    def _is_cached(self, model: str) -> Optional[Path]:
        """Check if manual is already cached"""
        model_dir = self.cache_dir / model.replace("/", "-").replace(" ", "-")
        if model_dir.exists():
            pdfs = list(model_dir.glob("*.pdf"))
            if pdfs:
                return pdfs[0]
        return None








class GenericFetcher(ManufacturerFetcher):
    """Generic fetcher that uses the LLM finder to locate docs for any manufacturer"""

    async def fetch(self, model: str, manufacturer: Optional[str] = None, device_type: Optional[str] = None) -> Optional[Path]:
        # Check cache first
        cached = self._is_cached(model)
        if cached:
            logger.info(f"{manufacturer or 'Generic'} {model} manual found in cache")
            return cached

        # Use LLM to find documentation URL
        if self.llm_finder and self.llm_finder.enabled:
            doc_url = await self.llm_finder.find_documentation_url(
                manufacturer=(manufacturer or ""),
                model=model,
                device_type=device_type
            )

            if doc_url:
                downloaded = await self._download_from_url(model, doc_url)
                if downloaded:
                    return downloaded
                logger.warning(f"Failed to download from LLM-provided URL: {doc_url}")

        logger.info(f"Could not find docs for {manufacturer or 'Unknown'} {model} using generic fetcher")
        return None

    async def _download_from_url(self, model: str, url: str) -> Optional[Path]:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "pdf" in content_type or url.endswith('.pdf'):
                        filename = f"{model}_manual.pdf"
                    else:
                        filename = f"{model}_manual.txt"

                    cache_path = self._get_cache_path(model, filename)
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_bytes(response.content)
                    logger.info(f"Downloaded and cached documentation for {model} from {url}")
                    return cache_path
                else:
                    logger.warning(f"Failed to download from {url}: HTTP {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error downloading from {url}: {e}")
            return None
    
    async def _download_html_as_text(self, model: str, url: str) -> Optional[Path]:
        """Download HTML docs and save as text or PDF (prefer PDF conversion).

        Tries to convert HTML to PDF using system `wkhtmltopdf` via `pdfkit`.
        Falls back to extracting text if conversion not available.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code != 200:
                    logger.warning(f"Failed to download HTML from {url}: HTTP {resp.status_code}")
                    return None

                html = resp.text

            # Try to convert HTML -> PDF using pdfkit/wkhtmltopdf if available
            try:
                import pdfkit
                # Write HTML to a temp file then convert
                with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as tf:
                    tf.write(html)
                    tmp_html = tf.name

                cache_path = self._get_cache_path(model, f"{model}_manual.pdf")
                cache_path.parent.mkdir(parents=True, exist_ok=True)

                pdfkit.from_file(tmp_html, str(cache_path))
                logger.info(f"Converted HTML to PDF for {model} and saved to {cache_path}")
                try:
                    os.unlink(tmp_html)
                except:
                    pass
                return cache_path
            except Exception:
                # pdfkit not available or conversion failed; fall back to text
                soup = BeautifulSoup(html, 'html.parser')
                content = soup.get_text(separator='\n', strip=True)
                cache_path = self._get_cache_path(model, f"{model}_manual.txt")
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(content, encoding='utf-8')
                logger.info(f"Saved extracted HTML text for {model} to {cache_path}")
                return cache_path

        except Exception as e:
            logger.error(f"Error downloading HTML docs from {url}: {e}")
            return None


class DocumentAutoFetcher:
    """
    Automatically fetch device documentation with zero configuration
    Uses LLM to intelligently find documentation sources.
    
    Usage:
        fetcher = DocumentAutoFetcher(rag_engine, cache_dir, openai_api_key)
        await fetcher.fetch_for_device({
            "manufacturer": "Aqara",
            "model": "SJCGQ11LM",
            "type": "water_leak"
        })
    """
    
    def __init__(self, rag_engine, cache_dir: Path = None, openai_api_key: Optional[str] = None):
        self.rag = rag_engine
        self.cache_dir = cache_dir or Path.home() / ".homesight" / "manuals"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize LLM document finder
        self.llm_finder = LLMDocumentFinder(openai_api_key)
        
        # Initialize manufacturer fetchers with LLM support
        # Use only the generic fetcher for onboarding and caching
        self.fetchers = {}
        self.generic_fetcher = GenericFetcher(self.cache_dir / "generic", self.llm_finder)
    
    async def fetch_for_device(self, device: Dict) -> bool:
        """
        Auto-fetch and ingest documentation for a device
        
        Args:
            device: Dict with keys: manufacturer, model, type
        
        Returns:
            True if docs were fetched/ingested, False otherwise
        """
        manufacturer = device.get("manufacturer", "").lower()
        model = device.get("model", "")
        device_type = device.get("type", "")
        
        if not manufacturer or not model:
            logger.warning(f"Device missing manufacturer or model: {device}")
            return False
        
        # Check if already indexed in RAG
        if self._is_indexed(manufacturer, model):
            logger.info(f"Docs already indexed for {manufacturer} {model}")
            return True
        
        # Prefer a specialized fetcher if we have one, otherwise use generic LLM-based fetcher
        fetcher = self.fetchers.get(manufacturer)
        if fetcher:
            logger.info(f"Using specialized fetcher for {manufacturer} {model}")
            doc_path = await fetcher.fetch(model)
        else:
            logger.info(f"Using generic fetcher for {manufacturer} {model}")
            doc_path = await self.generic_fetcher.fetch(model, manufacturer=manufacturer, device_type=device_type)
        
        if doc_path:
            # Ingest into RAG
            await self._ingest_document(doc_path, device)
            return True
        
        return False
    
    def _is_indexed(self, manufacturer: str, model: str) -> bool:
        """Check if device docs are already in RAG"""
        try:
            # Query RAG for this specific device
            results = self.rag.query(
                query_text=f"{manufacturer} {model}",
                n_results=1,
                where={
                    "manufacturer": manufacturer.title(),
                    "model": model
                }
            )
            return len(results) > 0
        except:
            return False
    
    async def _ingest_document(self, doc_path: Path, device: Dict):
        """Ingest document into RAG database (async batched for performance)"""
        try:
            # Extract text based on file type
            if doc_path.suffix == '.pdf':
                text = self._extract_pdf_text(doc_path)
            elif doc_path.suffix in ['.txt', '.html']:
                text = doc_path.read_text(encoding='utf-8')
            else:
                logger.error(f"Unsupported file type: {doc_path.suffix}")
                return

            if not text or len(text) < 100:
                logger.warning(f"Document too short or empty: {doc_path}")
                return

            # Base metadata
            metadata = {
                "source": f"{device['manufacturer']} {device['model']} Manual",
                "manufacturer": device['manufacturer'].title(),
                "model": device['model'],
                "device_type": device.get('type', 'unknown'),
                "category": "device_manual",
                "auto_fetched": True,
                "file_path": str(doc_path)
            }

            # Split large docs into chunks for better retrieval
            chunk_size = 2000
            documents = []

            if len(text) > chunk_size:
                chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
                for i, chunk in enumerate(chunks):
                    chunk_meta = metadata.copy()
                    chunk_meta['chunk'] = i + 1
                    chunk_meta['total_chunks'] = len(chunks)
                    documents.append({
                        'text': chunk,
                        'metadata': chunk_meta
                    })
                logger.info(f"Split {doc_path.name} into {len(chunks)} chunks")
            else:
                documents.append({
                    'text': text,
                    'metadata': metadata
                })

            # Use async batch ingestion (non-blocking)
            await self.rag.add_documents_async(documents, batch_size=10)
            logger.info(f"Ingested {doc_path.name} ({len(documents)} document(s))")

        except Exception as e:
            logger.error(f"Error ingesting document {doc_path}: {e}")
    
    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """Extract text from PDF"""
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            text_parts = []
            
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text.strip():
                    text_parts.append(f"[Page {page_num + 1}]\n{text}")
            
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return ""


# Example usage for testing
async def test_auto_fetch():
    """Test the auto-fetcher"""
    from rag_engine import RAGEngine
    
    rag = RAGEngine("/tmp/test-rag")
    fetcher = DocumentAutoFetcher(rag)
    
    # Test Aqara water leak sensor
    device = {
        "manufacturer": "Aqara",
        "model": "SJCGQ11LM",
        "type": "water_leak"
    }
    
    success = await fetcher.fetch_for_device(device)
    print(f"Fetch success: {success}")
    
    if success:
        # Query to verify
        results = rag.query("water leak sensor battery", n_results=2)
        for r in results:
            print(f"\nSource: {r['metadata']['source']}")
            print(f"Relevance: {r['relevance_score']:.3f}")


async def test_smoke_fetch():
    """Smoke test that simulates a device.created onboarding flow using a Mock RAG."""
    class MockRAG:
        def __init__(self):
            self.docs = []
        def add_document(self, text: str, metadata: dict):
            self.docs.append({'text': text, 'metadata': metadata})
        def query(self, query_text: str, n_results: int = 1, where: dict = None):
            # Return docs that match model in metadata
            if where:
                model = where.get('model')
                return [d for d in self.docs if d['metadata'].get('model') == model]
            return self.docs[:n_results]

    rag = MockRAG()
    fetcher = DocumentAutoFetcher(rag)

    # Create a fake cached manual to simulate a prior download
    model = "TEST123"
    manufacturer = "Acme"
    model_dir = fetcher.generic_fetcher._get_cache_path(model, "").parent
    model_dir.mkdir(parents=True, exist_ok=True)
    fake_manual = model_dir / f"{model}_manual.txt"
    fake_manual.write_text("This is a fake manual for testing.", encoding='utf-8')

    device = {"manufacturer": manufacturer, "model": model, "type": "sensor"}
    success = await fetcher.fetch_for_device(device)
    print(f"Smoke fetch success: {success}")
    print(f"Mock RAG docs count: {len(rag.docs)}")


if __name__ == "__main__":
    # Run both tests if desired
    asyncio.run(test_smoke_fetch())
