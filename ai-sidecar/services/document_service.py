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
        Comprehensive document discovery for a device

        Discovers:
        1. Official manufacturer documentation
        2. Support forums and articles (on initial discovery only)
        3. Community troubleshooting guides (on initial discovery only)
        4. Synthetic knowledge (on initial discovery only)

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

        # 1. Try official documentation first (always do this - fastest path)
        try:
            official_success = await self.fetcher.fetch_for_device(device)
            if official_success:
                results["sources_found"].append("official_manual")
                logger.info(f"✅ Official docs found for {manufacturer} {model}")
        except Exception as e:
            logger.error(f"Official doc fetch failed: {e}")

        # 2. Discover community sources using LLM (skip on reingest to reduce CPU)
        # Community source discovery is only done on initial device creation
        # Reingest operations focus on finding official documentation
        # This reduces CPU/LLM overhead during reingest operations
        if self.llm_finder.enabled and device.get("_initial_discovery", True):
            try:
                community_docs = await self._discover_community_sources(
                    manufacturer=manufacturer,
                    model=model,
                    device_type=device_type
                )

                if community_docs:
                    results["sources_found"].extend(community_docs)
                    logger.info(f"✅ Found {len(community_docs)} community sources")

            except Exception as e:
                logger.error(f"Community source discovery failed: {e}")

        # 3. Generate synthetic knowledge base entry (skip on reingest)
        if device.get("_initial_discovery", True):
            try:
                await self._generate_synthetic_knowledge(device)
                results["sources_found"].append("synthetic_knowledge")
                logger.info("✅ Generated synthetic knowledge base entry")
            except Exception as e:
                logger.error(f"Synthetic knowledge generation failed: {e}")

        results["status"] = "success" if results["sources_found"] else "partial"
        results["total_sources"] = len(results["sources_found"])

        return results

    async def _discover_community_sources(
        self,
        manufacturer: str,
        model: str,
        device_type: Optional[str]
    ) -> List[str]:
        """
        Use LLM to discover community sources (forums, Reddit, etc.)

        Returns:
            List of source types discovered
        """
        if not self.llm_finder.enabled:
            return []

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.llm_finder.api_key)

            device_info = f"{manufacturer} {model}"
            if device_type:
                device_info += f" ({device_type})"

            prompt = f"""Find online community resources and discussions about this device:

Device: {device_info}

Find:
1. Support forum URLs (manufacturer forums, tech support sites)
2. Reddit threads discussing common issues
3. Popular YouTube troubleshooting videos
4. Community guides and wikis

For each source, provide:
- URL
- Type (forum/reddit/youtube/guide)
- Brief description of content
- Relevance (high/medium/low)

Respond in JSON format:
{{
    "sources": [
        {{
            "url": "https://...",
            "type": "reddit",
            "description": "Common battery issues thread",
            "relevance": "high"
        }}
    ]
}}

Only include sources you're confident exist and are relevant."""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at finding community tech support resources online."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )

            content = response.choices[0].message.content

            # Parse and fetch sources
            import json
            json_start = content.find("{")
            json_end = content.rfind("}") + 1

            if json_start != -1 and json_end > json_start:
                result = json.loads(content[json_start:json_end])
                sources_found = []

                for source in result.get("sources", []):
                    if source.get("relevance") == "high":
                        # Attempt to fetch and ingest
                        try:
                            success = await self._fetch_web_content(
                                url=source["url"],
                                device={"manufacturer": manufacturer, "model": model},
                                source_type=source["type"]
                            )
                            if success:
                                sources_found.append(source["type"])
                        except Exception as e:
                            logger.warning(f"Failed to fetch {source['url']}: {e}")

                return sources_found

        except Exception as e:
            logger.error(f"Community source discovery failed: {e}")

        return []

    async def _fetch_web_content(
        self,
        url: str,
        device: Dict[str, Any],
        source_type: str
    ) -> bool:
        """
        Fetch and ingest web content (forum post, Reddit thread, etc.)

        Args:
            url: URL to fetch
            device: Device info for metadata
            source_type: Type of source (reddit, forum, youtube, etc.)

        Returns:
            True if successful
        """
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    logger.warning(f"Failed to fetch {url}: HTTP {response.status_code}")
                    return False

                # Extract text content
                soup = BeautifulSoup(response.text, 'html.parser')

                # Remove script and style elements
                for script in soup(["script", "style", "nav", "header", "footer"]):
                    script.decompose()

                text = soup.get_text(separator='\n', strip=True)

                # Only ingest if we got meaningful content
                if len(text) < 200:
                    logger.warning(f"Content too short from {url}")
                    return False

                # Ingest into RAG
                metadata = {
                    "source": f"{device['manufacturer']} {device['model']} - {source_type}",
                    "manufacturer": device['manufacturer'],
                    "model": device['model'],
                    "category": f"community_{source_type}",
                    "url": url,
                    "auto_fetched": True
                }

                # Chunk large content and batch ingest
                chunk_size = 2000
                documents = []

                if len(text) > chunk_size:
                    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
                    for i, chunk in enumerate(chunks[:5]):  # Limit to 5 chunks per source
                        chunk_meta = metadata.copy()
                        chunk_meta['chunk'] = i + 1
                        documents.append({'text': chunk, 'metadata': chunk_meta})
                else:
                    documents.append({'text': text, 'metadata': metadata})

                # Use async batch ingestion with smaller batches to reduce CPU spike
                await self.rag.add_documents_async(documents, batch_size=self.batch_size_community)

                logger.info(f"✅ Ingested content from {url}")
                return True

        except Exception as e:
            logger.error(f"Error fetching web content: {e}")
            return False

    async def _generate_synthetic_knowledge(self, device: Dict[str, Any]):
        """
        Generate synthetic knowledge base entry using LLM

        This creates a baseline knowledge entry even if no docs are found.
        """
        if not self.llm_finder.enabled:
            return

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.llm_finder.api_key)

            manufacturer = device.get("manufacturer", "")
            model = device.get("model", "")
            device_type = device.get("type", "")

            prompt = f"""Generate a comprehensive knowledge base entry for this device:

Manufacturer: {manufacturer}
Model: {model}
Type: {device_type}

Include:
1. Common issues and troubleshooting steps
2. Typical battery life and replacement procedures (if applicable)
3. Sensor type and what it monitors
4. Common false alarm causes (if applicable)
5. Maintenance recommendations
6. Integration/compatibility notes

Write in a clear, technical documentation style."""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a technical writer creating device documentation. Be accurate and comprehensive."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=1200
            )

            content = response.choices[0].message.content

            # Ingest into RAG (async batch)
            metadata = {
                "source": f"{manufacturer} {model} - AI Generated Knowledge",
                "manufacturer": manufacturer,
                "model": model,
                "device_type": device_type,
                "category": "synthetic_knowledge",
                "auto_generated": True
            }

            documents = [{'text': content, 'metadata': metadata}]
            await self.rag.add_documents_async(documents, batch_size=1)
            logger.info(f"✅ Generated synthetic knowledge for {manufacturer} {model}")

        except Exception as e:
            logger.error(f"Synthetic knowledge generation failed: {e}")
