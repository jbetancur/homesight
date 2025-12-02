# ai_sidecar/rag/html_fetcher.py

from readability import Document
from bs4 import BeautifulSoup
from .http_client import fetch_text


async def fetch_html(url: str) -> str:
    """
    Fetch URL → extract readable main article text.
    Returns cleaned text or None.
    """
    text, status = await fetch_text(url)
    if not text:
        return None

    try:
        doc = Document(text)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "html.parser")
        clean_text = soup.get_text("\n", strip=True)
        return clean_text
    except Exception:
        return None
