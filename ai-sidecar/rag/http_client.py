"""
Shared HTTP Client Utilities for RAG

Provides consistent HTTP client configuration and utilities for:
- URL validation
- Content downloading
- Rate limiting support

This eliminates duplicate httpx.AsyncClient creation across RAG modules
and provides a single place to configure timeouts, retries, etc.
"""

import httpx
import logging
from typing import Optional, Tuple
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


# Default timeout configurations
class Timeouts:
    """Standard timeout configurations for different use cases"""
    QUICK_CHECK = 5.0      # URL existence checks
    STANDARD = 15.0        # Normal page fetches
    DOWNLOAD = 30.0        # Large file downloads (PDFs)


@asynccontextmanager
async def get_client(
    timeout: float = Timeouts.STANDARD,
    follow_redirects: bool = True
):
    """
    Get a configured async HTTP client.
    
    Usage:
        async with get_client() as client:
            response = await client.get(url)
    
    Args:
        timeout: Request timeout in seconds
        follow_redirects: Whether to follow HTTP redirects
    
    Yields:
        Configured httpx.AsyncClient
    """
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects
    ) as client:
        yield client


async def url_exists(url: str) -> bool:
    """
    Check if a URL is accessible.
    
    Tries HEAD first (faster), falls back to GET.
    
    Args:
        url: URL to check
    
    Returns:
        True if URL returns 200, False otherwise
    """
    # Try HEAD first (faster)
    try:
        async with get_client(timeout=Timeouts.QUICK_CHECK) as client:
            resp = await client.head(url)
            if resp.status_code == 200:
                return True
    except Exception:
        pass

    # Fallback to GET (some servers don't support HEAD)
    try:
        async with get_client(timeout=Timeouts.QUICK_CHECK + 3.0) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False


async def download_content(
    url: str,
    timeout: float = Timeouts.DOWNLOAD
) -> Tuple[Optional[bytes], Optional[str], int]:
    """
    Download content from a URL.
    
    Args:
        url: URL to download from
        timeout: Download timeout in seconds
    
    Returns:
        Tuple of (content_bytes, content_type, status_code)
        content_bytes is None on failure
    """
    try:
        async with get_client(timeout=timeout) as client:
            resp = await client.get(url)
            
            if resp.status_code != 200:
                logger.warning(f"Download failed: {url} returned {resp.status_code}")
                return None, None, resp.status_code
            
            content_type = resp.headers.get("content-type", "").lower()
            return resp.content, content_type, resp.status_code
            
    except httpx.TimeoutException:
        logger.warning(f"Download timeout: {url}")
        return None, None, 0
    except Exception as e:
        logger.error(f"Download error for {url}: {e}")
        return None, None, 0


async def fetch_text(
    url: str,
    timeout: float = Timeouts.STANDARD
) -> Tuple[Optional[str], int]:
    """
    Fetch text content from a URL.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
    
    Returns:
        Tuple of (text_content, status_code)
        text_content is None on failure
    """
    try:
        async with get_client(timeout=timeout) as client:
            resp = await client.get(url)
            
            if resp.status_code != 200:
                return None, resp.status_code
            
            return resp.text, resp.status_code
            
    except httpx.TimeoutException:
        logger.warning(f"Fetch timeout: {url}")
        return None, 0
    except Exception as e:
        logger.error(f"Fetch error for {url}: {e}")
        return None, 0
