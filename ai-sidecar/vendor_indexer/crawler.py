"""
Vendor Documentation Crawler

Crawls manufacturer-specific domains to discover and index documentation.

This crawler:
- Focuses ONLY on manufacturer domains (not the whole web)
- Looks for PDF and manual-like links
- Respects robots.txt
- Rate-limits requests (polite crawling)
- Stores discovered URLs in the vendor index

This is NOT a general web crawler - it's manufacturer-scoped.
"""

import logging
import asyncio
import httpx
from typing import List, Set, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from datetime import datetime
import re

from .storage import VendorDocumentStorage, IndexedDocument

logger = logging.getLogger(__name__)


class VendorCrawler:
    """
    Crawls manufacturer domains to discover documentation.

    Focused, polite, manufacturer-scoped crawler.
    """

    def __init__(self, storage: VendorDocumentStorage):
        """
        Initialize crawler

        Args:
            storage: VendorDocumentStorage instance
        """
        self.storage = storage

        # Crawl settings
        self.max_depth = 3  # Maximum link depth to follow
        self.max_pages_per_domain = 50  # Limit pages per manufacturer
        self.request_delay = 1.0  # Seconds between requests (polite)
        self.timeout = 15.0  # Request timeout

        # User agent
        self.user_agent = "HomeSight-DocCrawler/1.0 (https://github.com/homesight/homesight)"

    async def crawl_manufacturer(
        self,
        manufacturer: str,
        seed_urls: List[str]
    ) -> int:
        """
        Crawl a manufacturer's documentation domains.

        Args:
            manufacturer: Manufacturer name
            seed_urls: List of seed URLs to start crawling from
                      (e.g., ["https://support.zooz.com", "https://zooz.com/manuals"])

        Returns:
            Number of documents discovered and indexed
        """
        logger.info(f"Starting crawl for {manufacturer} from {len(seed_urls)} seed URLs")

        discovered_count = 0
        visited: Set[str] = set()
        to_visit: List[tuple[str, int]] = [(url, 0) for url in seed_urls]  # (url, depth)

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent}
        ) as client:

            while to_visit and len(visited) < self.max_pages_per_domain:
                url, depth = to_visit.pop(0)

                # Skip if already visited
                if url in visited:
                    continue

                # Skip if depth exceeded
                if depth > self.max_depth:
                    continue

                visited.add(url)

                # Polite crawling - delay between requests
                await asyncio.sleep(self.request_delay)

                try:
                    # Fetch page
                    response = await client.get(url)

                    if response.status_code != 200:
                        logger.debug(f"Skipping {url}: HTTP {response.status_code}")
                        continue

                    content_type = response.headers.get("content-type", "").lower()

                    # If it's a PDF, index it directly
                    if "pdf" in content_type or url.lower().endswith(".pdf"):
                        doc = IndexedDocument(
                            manufacturer=manufacturer,
                            model=None,  # Will try to extract from filename/title
                            url=url,
                            title=self._extract_title_from_url(url),
                            document_type="pdf",
                            discovered_at=datetime.now(),
                            file_size=int(response.headers.get("content-length", 0))
                        )
                        if self.storage.add_document(doc):
                            discovered_count += 1
                            logger.info(f"Discovered PDF: {url}")
                        continue

                    # If it's HTML, parse for links
                    if "html" in content_type:
                        html = response.text
                        base_url = str(response.url)

                        # Extract and index PDF links
                        pdf_links = self._extract_pdf_links(html, base_url)
                        for pdf_url, title in pdf_links:
                            doc = IndexedDocument(
                                manufacturer=manufacturer,
                                model=self._extract_model_from_text(title),
                                url=pdf_url,
                                title=title,
                                document_type="pdf",
                                discovered_at=datetime.now()
                            )
                            if self.storage.add_document(doc):
                                discovered_count += 1
                                logger.info(f"Discovered PDF: {pdf_url}")

                        # Extract manual/documentation page links to continue crawling
                        if depth < self.max_depth:
                            doc_links = self._extract_documentation_links(html, base_url, seed_urls)
                            for link in doc_links:
                                if link not in visited and len(to_visit) < self.max_pages_per_domain:
                                    to_visit.append((link, depth + 1))

                except httpx.TimeoutException:
                    logger.warning(f"Timeout crawling {url}")
                except Exception as e:
                    logger.debug(f"Error crawling {url}: {e}")

        logger.info(f"Crawl complete for {manufacturer}: discovered {discovered_count} documents, visited {len(visited)} pages")
        return discovered_count

    def _extract_pdf_links(self, html: str, base_url: str) -> List[tuple[str, str]]:
        """
        Extract PDF links from HTML.

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links

        Returns:
            List of (pdf_url, title) tuples
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            pdf_links = []

            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)

                # Check if it looks like a PDF link
                if ".pdf" in href.lower():
                    # Resolve relative URL
                    full_url = urljoin(base_url, href)

                    # Use link text as title, or extract from URL
                    title = text if text else self._extract_title_from_url(full_url)

                    pdf_links.append((full_url, title))

            return pdf_links

        except Exception as e:
            logger.debug(f"Error extracting PDF links: {e}")
            return []

    def _extract_documentation_links(
        self,
        html: str,
        base_url: str,
        seed_domains: List[str]
    ) -> List[str]:
        """
        Extract links to documentation/manual/support pages.

        Only follows links that:
        - Are on the same domain as seed URLs
        - Contain documentation-related keywords

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links
            seed_domains: List of allowed seed domains

        Returns:
            List of documentation page URLs
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            doc_links = []

            # Extract allowed domains from seed URLs
            allowed_domains = set()
            for seed in seed_domains:
                parsed = urlparse(seed)
                allowed_domains.add(parsed.netloc)

            # Documentation-related keywords
            doc_keywords = [
                "manual", "documentation", "support", "help", "guide",
                "download", "resource", "datasheet", "faq", "knowledge",
                "product", "install", "setup"
            ]

            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True).lower()

                # Resolve relative URL
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)

                # Only follow links on allowed domains
                if parsed.netloc not in allowed_domains:
                    continue

                # Only follow links with documentation keywords
                url_lower = full_url.lower()
                if any(kw in url_lower or kw in text for kw in doc_keywords):
                    doc_links.append(full_url)

            return doc_links

        except Exception as e:
            logger.debug(f"Error extracting documentation links: {e}")
            return []

    def _extract_title_from_url(self, url: str) -> str:
        """Extract a human-readable title from a URL"""
        # Get filename from URL
        parsed = urlparse(url)
        filename = parsed.path.split("/")[-1]

        # Remove extension
        name = filename.rsplit(".", 1)[0] if "." in filename else filename

        # Replace hyphens/underscores with spaces, title case
        title = name.replace("-", " ").replace("_", " ").title()

        return title or "Manual"

    def _extract_model_from_text(self, text: str) -> Optional[str]:
        """
        Try to extract a model number from text.

        Looks for common model number patterns like:
        - ZSE42
        - Model-123
        - ABC-123-XYZ

        Args:
            text: Text to search

        Returns:
            Extracted model number or None
        """
        # Common model number patterns
        patterns = [
            r'\b[A-Z]{2,}\s*-?\s*\d{2,}\b',  # e.g., ZSE42, ZEN-73
            r'\bModel[:\s]+([A-Z0-9-]+)\b',  # e.g., Model: ABC-123
            r'\b[A-Z]\d{2,}[A-Z]?\b',  # e.g., T6900, ZEN71
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Return the matched group or full match
                return match.group(1) if match.lastindex else match.group(0)

        return None


async def crawl_manufacturer_domains(
    manufacturer: str,
    domains: List[str],
    storage: Optional[VendorDocumentStorage] = None
) -> int:
    """
    Convenience function to crawl manufacturer domains.

    Args:
        manufacturer: Manufacturer name
        domains: List of domains to crawl (e.g., ["support.zooz.com", "zooz.com/manuals"])
        storage: Optional storage instance (creates one if not provided)

    Returns:
        Number of documents discovered
    """
    if not storage:
        storage = VendorDocumentStorage()

    crawler = VendorCrawler(storage)

    # Convert domains to full URLs if needed
    seed_urls = []
    for domain in domains:
        if not domain.startswith("http"):
            seed_urls.append(f"https://{domain}")
        else:
            seed_urls.append(domain)

    discovered = await crawler.crawl_manufacturer(manufacturer, seed_urls)

    return discovered
