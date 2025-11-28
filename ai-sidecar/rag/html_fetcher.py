# ai_sidecar/rag/html_fetcher.py

import httpx
from readability import Document
from bs4 import BeautifulSoup

async def fetch_html(url: str) -> str:
    """
    Fetch URL → extract readable main article text.
    Returns cleaned text or None.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return None

    try:
        doc = Document(html)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "html.parser")
        text = soup.get_text("\n", strip=True)
        return text
    except Exception:
        return None
