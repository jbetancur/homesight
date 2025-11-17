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


class AqaraFetcher(ManufacturerFetcher):
    """Fetch Aqara device manuals using LLM to find documentation"""
    
    # Known Aqara models - Using direct links when available
    # Note: These URLs may change. LLM will be used as fallback.
    KNOWN_MODELS = {
        "SJCGQ11LM": "water_leak_sensor",  # Water Leak Sensor
        "WSDCGQ11LM": "temp_humidity_sensor",  # Temperature & Humidity Sensor
        "MCCGQ11LM": "door_window_sensor",  # Door/Window Sensor
        "RTCGQ11LM": "motion_sensor",  # Motion Sensor
        "WXKG11LM": "wireless_switch",  # Wireless Switch
    }
    
    async def fetch(self, model: str) -> Optional[Path]:
        """
        Fetch Aqara manual by model number
        
        Strategy:
        1. Check cache first
        2. Use LLM to find official documentation URL
        3. Download and cache the documentation
        4. Fallback to template if LLM can't find docs
        """
        
        # Check cache first
        cached = self._is_cached(model)
        if cached:
            logger.info(f"Aqara {model} manual found in cache")
            return cached
        
        # Try LLM-powered document finding
        if self.llm_finder and self.llm_finder.enabled:
            device_type = self.KNOWN_MODELS.get(model, "smart home device")
            doc_url = await self.llm_finder.find_documentation_url(
                manufacturer="Aqara",
                model=model,
                device_type=device_type
            )
            
            if doc_url:
                # Try to download the documentation
                downloaded = await self._download_from_url(model, doc_url)
                if downloaded:
                    return downloaded
                logger.warning(f"Failed to download from LLM-provided URL: {doc_url}")
        
        # Fallback: use template for known models
        device_type = self.KNOWN_MODELS.get(model)
        if device_type:
            logger.info(f"Using template documentation for Aqara {model}")
            return await self._create_manual_from_template(model, device_type)
        
        logger.warning(f"Could not find manual for Aqara {model}")
        return None
    
    async def _download_from_url(self, model: str, url: str) -> Optional[Path]:
        """Download documentation from URL and cache it"""
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                
                if response.status_code == 200:
                    # Determine file type from content or URL
                    content_type = response.headers.get("content-type", "")
                    
                    if "pdf" in content_type or url.endswith(".pdf"):
                        filename = f"{model}_manual.pdf"
                    else:
                        filename = f"{model}_manual.txt"
                    
                    cache_path = self._get_cache_path(model, filename)
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    cache_path.write_bytes(response.content)
                    logger.info(f"Downloaded and cached documentation for {model}")
                    return cache_path
                else:
                    logger.warning(f"Failed to download from {url}: HTTP {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error downloading from {url}: {e}")
            return None
    
    async def _search_support_site(self, model: str) -> Optional[str]:
        """Search Aqara support site for model"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try US support site
                response = await client.get(
                    "https://www.aqara.com/us/support/download.html",
                    follow_redirects=True
                )
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Look for PDF links containing model number
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if model.lower() in href.lower() and href.endswith('.pdf'):
                            if not href.startswith('http'):
                                href = f"https://www.aqara.com{href}"
                            return href
        
        except Exception as e:
            logger.error(f"Error searching Aqara support site: {e}")
        
        return None
    
    async def _create_manual_from_template(self, model: str, device_type: str) -> Optional[Path]:
        """
        Create manual from template (fallback when web fetch fails)
        
        This provides baseline documentation for common Aqara devices.
        In production, you'd either:
        1. Fix the web scraping to get real PDFs
        2. Pre-download PDFs to cache directory
        3. Use a community repository
        """
        cache_path = self._get_cache_path(model, f"{model}_manual.txt")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Template content based on device type
        templates = {
            "water_leak_sensor": """
Aqara Water Leak Sensor (SJCGQ11LM) - User Manual

OVERVIEW
The Aqara Water Leak Sensor detects water leaks and sends instant notifications to your phone.
Battery-powered with 2+ year lifespan using CR2032 battery.

SPECIFICATIONS
- Model: SJCGQ11LM
- Power: CR2032 battery (3V)
- Battery Life: 2+ years
- Detection Time: <60 seconds
- Operating Temperature: -10°C to 60°C (14°F to 140°F)
- Wireless Protocol: Zigbee 3.0
- Dimensions: 50 x 50 x 15 mm

INSTALLATION
1. Remove protective film from sensor probe
2. Place sensor in leak-prone areas:
   - Near water heaters
   - Under sinks
   - Around washing machines
   - Near dishwashers
   - In basements
3. Ensure probe contacts touch the floor
4. Press button on top to pair with Zigbee hub

PAIRING WITH HUB
1. Open Aqara Home app
2. Tap "+" to add device
3. Select "Water Leak Sensor"
4. Press and hold button for 5 seconds until LED flashes
5. Follow app instructions to complete pairing

TROUBLESHOOTING
- Sensor not responding: Replace battery (CR2032)
- False alarms: Clean sensor probe with dry cloth, check for condensation
- Sensor offline: Check hub connection, try re-pairing device
- Slow detection: Ensure probe contacts are touching floor
- Range issues: Move hub closer or add Zigbee repeater

MAINTENANCE
- Replace battery every 2 years
- Clean sensor probe monthly with dry cloth (no liquids!)
- Test sensor quarterly by placing in shallow water
- Check mounting position after moving furniture

BATTERY REPLACEMENT
1. Twist sensor cover counter-clockwise
2. Remove old CR2032 battery
3. Insert new battery (positive side up)
4. Replace cover and twist clockwise
5. Sensor should flash LED to confirm power

LED INDICATORS
- Solid blue: Normal operation
- Flashing blue: Pairing mode
- Red flash: Water detected
- Red solid: Low battery

TESTING
To test sensor: Place in shallow water (1-2mm deep)
Sensor should trigger within 60 seconds
Remove from water immediately after testing

IMPORTANT SAFETY NOTES
- Not waterproof! Only water-resistant
- Do not submerge sensor body
- Only probe contacts should touch water
- Keep sensor away from steam sources
- Do not use in temperatures below -10°C or above 60°C

OPTIMAL PLACEMENT
Best locations:
- Directly on floor near water heater
- Under sink cabinets (probe on floor)
- Behind washing machine
- Near sump pump
- At lowest point in basement

Avoid:
- Areas with frequent condensation
- Direct steam exposure
- Areas that flood regularly (use multiple sensors)
""",
            "temp_humidity_sensor": """
Aqara Temperature & Humidity Sensor (WSDCGQ11LM) - User Manual

OVERVIEW
Monitors temperature and humidity levels with high precision.
Reports data every 5-60 minutes depending on changes detected.

SPECIFICATIONS
- Model: WSDCGQ11LM
- Temperature Range: -20°C to 60°C (-4°F to 140°F)
- Humidity Range: 0-100% RH
- Temperature Accuracy: ±0.3°C
- Humidity Accuracy: ±3% RH
- Battery: CR2032
- Battery Life: 2+ years
- Wireless: Zigbee 3.0

INSTALLATION & SETUP
1. Open case by twisting counter-clockwise
2. Pull insulation tab to activate battery
3. Press button to enter pairing mode
4. Mount using adhesive or stand
5. Place in representative location

BEST PRACTICES
- Avoid direct sunlight
- Keep away from heat sources
- Don't place in drafts
- Allow air circulation around sensor
- Mount at chest height for accurate readings

TROUBLESHOOTING
- Inaccurate readings: Allow 30 minutes to stabilize after placement
- Offline: Check hub connectivity, replace battery
- Condensation in case: Move to drier location
""",
            "door_window_sensor": """
Aqara Door/Window Sensor (MCCGQ11LM) - User Manual

OVERVIEW
Detects opening and closing of doors and windows.
Sends instant notifications when contact is broken.

SPECIFICATIONS
- Model: MCCGQ11LM
- Detection Range: <22mm gap
- Battery: CR1632
- Battery Life: 2+ years
- Response Time: <1 second
- Wireless: Zigbee 3.0

INSTALLATION
1. Clean mounting surfaces
2. Attach main sensor to door/window frame
3. Attach magnet to moving part
4. Align sensor and magnet (<22mm gap when closed)
5. Pair with hub

TROUBLESHOOTING
- False triggers: Check alignment, reduce gap
- Not detecting: Battery low or gap too large
- Range issues: Add Zigbee repeater
"""
        }
        
        content = templates.get(device_type, "")
        if content:
            cache_path.write_text(content, encoding='utf-8')
            logger.info(f"Created manual template for {model} at {cache_path}")
            return cache_path
        
        return None
    
    async def _download_pdf(self, model: str, url: str) -> Optional[Path]:
        """Download PDF from URL"""
        try:
            cache_path = self._get_cache_path(model, f"{model}_manual.pdf")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Downloading Aqara {model} manual from {url}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, follow_redirects=True)
                
                if response.status_code == 200:
                    cache_path.write_bytes(response.content)
                    logger.info(f"Downloaded Aqara {model} manual to {cache_path}")
                    return cache_path
                else:
                    logger.error(f"Failed to download: HTTP {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error downloading Aqara manual: {e}")
        
        return None


class ShellyFetcher(ManufacturerFetcher):
    """Fetch Shelly device manuals from knowledge base"""
    
    KNOWN_MODELS = {
        "Shelly 1": "https://shelly-api-docs.shelly.cloud/gen1/#shelly1",
        "Shelly 1PM": "https://shelly-api-docs.shelly.cloud/gen1/#shelly1-1pm",
        "Shelly Plus 1": "https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen2/ShellyPlus1",
        "Shelly Plus 1PM": "https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen2/ShellyPlus1PM",
        "Shelly Door/Window": "https://kb.shelly.cloud/knowledge-base/shelly-door-window",
    }
    
    async def fetch(self, model: str) -> Optional[Path]:
        """Fetch Shelly documentation"""
        
        cached = self._is_cached(model)
        if cached:
            logger.info(f"Shelly {model} docs found in cache")
            return cached
        
        # Shelly uses HTML docs, need to convert to PDF or extract text
        url = self.KNOWN_MODELS.get(model)
        
        if url:
            # For now, download HTML and extract text
            # In production, could use wkhtmltopdf or similar to create PDF
            return await self._download_html_as_text(model, url)
        
        return None
    
    async def _download_html_as_text(self, model: str, url: str) -> Optional[Path]:
        """Download HTML docs and save as text"""
        try:
            cache_path = self._get_cache_path(model, f"{model}_manual.txt")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Downloading Shelly {model} docs from {url}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, follow_redirects=True)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract main content
                    content = soup.get_text(separator='\n', strip=True)
                    cache_path.write_text(content, encoding='utf-8')
                    
                    logger.info(f"Downloaded Shelly {model} docs to {cache_path}")
                    return cache_path
        
        except Exception as e:
            logger.error(f"Error downloading Shelly docs: {e}")
        
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
        self.fetchers = {
            "aqara": AqaraFetcher(self.cache_dir / "aqara", self.llm_finder),
            "shelly": ShellyFetcher(self.cache_dir / "shelly", self.llm_finder),
        }
    
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
        
        # Get appropriate fetcher
        fetcher = self.fetchers.get(manufacturer)
        if not fetcher:
            logger.info(f"No fetcher available for {manufacturer}")
            return False
        
        # Fetch document
        logger.info(f"Fetching docs for {manufacturer} {model}")
        doc_path = await fetcher.fetch(model)
        
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
        """Ingest document into RAG database"""
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
            
            # Add to RAG with metadata
            metadata = {
                "source": f"{device['manufacturer']} {device['model']} Manual",
                "manufacturer": device['manufacturer'].title(),
                "model": device['model'],
                "device_type": device.get('type', 'unknown'),
                "category": "device_manual",
                "auto_fetched": True,
                "file_path": str(doc_path)
            }
            
            # Split large docs into chunks
            chunk_size = 2000
            if len(text) > chunk_size:
                chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
                for i, chunk in enumerate(chunks):
                    chunk_meta = metadata.copy()
                    chunk_meta['chunk'] = i + 1
                    chunk_meta['total_chunks'] = len(chunks)
                    self.rag.add_document(text=chunk, metadata=chunk_meta)
                logger.info(f"Ingested {len(chunks)} chunks from {doc_path.name}")
            else:
                self.rag.add_document(text=text, metadata=metadata)
                logger.info(f"Ingested {doc_path.name}")
        
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


if __name__ == "__main__":
    asyncio.run(test_auto_fetch())
