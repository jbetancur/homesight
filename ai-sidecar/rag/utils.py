"""
Shared Utilities for RAG

Common functions used across RAG modules for:
- Manufacturer/model normalization
- ChromaDB query building
- Text chunking utilities
"""

import re


def normalize_manufacturer(name: str) -> str:
    """
    Normalize manufacturer name for consistent lookups and storage.
    
    Uses title case for display/storage (e.g., "Zooz", "Aqara").
    
    Args:
        name: Raw manufacturer name
    
    Returns:
        Normalized manufacturer name in title case
    
    Examples:
        >>> normalize_manufacturer("zooz")
        'Zooz'
        >>> normalize_manufacturer("AQARA")
        'Aqara'
        >>> normalize_manufacturer("philips hue")
        'Philips Hue'
    """
    if not name:
        return ""
    return name.strip().title()


def normalize_manufacturer_key(name: str) -> str:
    """
    Normalize manufacturer name for cache/lookup keys.
    
    Uses lowercase without spaces for key consistency.
    
    Args:
        name: Raw manufacturer name
    
    Returns:
        Normalized lowercase key
    
    Examples:
        >>> normalize_manufacturer_key("Zooz")
        'zooz'
        >>> normalize_manufacturer_key("Philips Hue")
        'philipshue'
    """
    if not name:
        return ""
    return re.sub(r'[^a-z0-9]', '', name.lower().strip())


def get_device_key(manufacturer: str, model: str) -> str:
    """
    Generate a consistent cache key for a device.
    
    Args:
        manufacturer: Manufacturer name
        model: Model number
    
    Returns:
        Formatted device key "Manufacturer:Model"
    
    Examples:
        >>> get_device_key("Zooz", "ZSE42")
        'Zooz:ZSE42'
    """
    return f"{normalize_manufacturer(manufacturer)}:{model.strip()}"


def build_chromadb_where(
    manufacturer: str = "",
    model: str = ""
) -> dict | None:
    """
    Build a ChromaDB where filter for device queries.
    
    Args:
        manufacturer: Manufacturer name (optional)
        model: Model number (optional)
    
    Returns:
        ChromaDB where clause dict, or None if no filters
    
    Examples:
        >>> build_chromadb_where("Zooz", "ZSE42")
        {'$and': [{'manufacturer': 'Zooz'}, {'model': 'ZSE42'}]}
        >>> build_chromadb_where("Zooz")
        {'manufacturer': 'Zooz'}
        >>> build_chromadb_where()
        None
    """
    conditions = []
    
    if manufacturer:
        conditions.append({"manufacturer": normalize_manufacturer(manufacturer)})
    
    if model:
        conditions.append({"model": model.strip()})
    
    if not conditions:
        return None
    
    if len(conditions) == 1:
        return conditions[0]
    
    return {"$and": conditions}


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 0) -> list[str]:
    """
    Split text into chunks for RAG ingestion.
    
    Args:
        text: Text to split
        chunk_size: Maximum characters per chunk
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if not text:
        return []
    
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence endings near the chunk boundary
            for boundary in [". ", ".\n", "! ", "? ", "\n\n"]:
                boundary_pos = text.rfind(boundary, start + chunk_size // 2, end)
                if boundary_pos > 0:
                    end = boundary_pos + len(boundary)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap if overlap > 0 else end
    
    return chunks
