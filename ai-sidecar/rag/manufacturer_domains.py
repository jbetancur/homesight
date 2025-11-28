"""
Manufacturer Domain Heuristics Engine

This module infers likely documentation domains for manufacturers without
requiring manual configuration. It uses pattern recognition and common
industry practices to expand search domains automatically.

Key features:
- Infers primary domain from manufacturer name
- Adds common support subdomains (support., help., docs., kb., manual.)
- Includes CDN patterns (Shopify, Amazon S3, etc.)
- Self-expands as documents are discovered
- NO manual per-device configuration required
"""

import logging
import re
from typing import List, Set, Optional, Dict
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class ManufacturerDomainRegistry:
    """
    Registry of discovered manufacturer domains.

    This registry learns from successful document discoveries and
    stores domain patterns for future lookups.
    """

    def __init__(self, cache_file: Optional[Path] = None):
        """
        Initialize domain registry

        Args:
            cache_file: Optional path to JSON cache file for persistence
        """
        self.cache_file = cache_file or Path.home() / "homesight" / "manufacturer_domains.json"
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        # In-memory registry: {manufacturer_normalized: [domains]}
        self.registry: Dict[str, Set[str]] = {}
        self._load_cache()

    def _normalize_manufacturer(self, name: str) -> str:
        """Normalize manufacturer name for consistent lookups"""
        return name.lower().strip().replace(" ", "").replace("-", "")

    def _load_cache(self):
        """Load previously discovered domains from cache"""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                # Convert lists back to sets
                self.registry = {k: set(v) for k, v in data.items()}
                logger.info(f"Loaded {len(self.registry)} manufacturers from domain cache")
        except Exception as e:
            logger.warning(f"Failed to load domain cache: {e}")

    def _save_cache(self):
        """Save discovered domains to cache"""
        try:
            # Convert sets to lists for JSON serialization
            data = {k: list(v) for k, v in self.registry.items()}
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save domain cache: {e}")

    def add_domain(self, manufacturer: str, domain: str):
        """
        Register a discovered domain for a manufacturer

        Args:
            manufacturer: Manufacturer name
            domain: Discovered domain (e.g., "support.zooz.com")
        """
        norm = self._normalize_manufacturer(manufacturer)

        if norm not in self.registry:
            self.registry[norm] = set()

        # Clean domain (remove protocol, trailing slashes)
        clean_domain = domain.replace("https://", "").replace("http://", "").strip("/")

        if clean_domain not in self.registry[norm]:
            self.registry[norm].add(clean_domain)
            self._save_cache()
            logger.info(f"Registered domain {clean_domain} for {manufacturer}")

    def get_known_domains(self, manufacturer: str) -> List[str]:
        """
        Get previously discovered domains for a manufacturer

        Args:
            manufacturer: Manufacturer name

        Returns:
            List of known domains (may be empty)
        """
        norm = self._normalize_manufacturer(manufacturer)
        return list(self.registry.get(norm, set()))


# Global registry instance
_registry: Optional[ManufacturerDomainRegistry] = None


def get_registry() -> ManufacturerDomainRegistry:
    """Get or create global manufacturer domain registry"""
    global _registry
    if _registry is None:
        _registry = ManufacturerDomainRegistry()
    return _registry


def get_manufacturer_domains(manufacturer: str) -> List[str]:
    """
    Get all likely documentation domains for a manufacturer.

    This is the main entry point for domain inference.

    Strategy:
    1. Check known/discovered domains from registry
    2. Infer primary domain from manufacturer name
    3. Add common support subdomains
    4. Add common CDN patterns
    5. Return ranked list

    Args:
        manufacturer: Manufacturer name (e.g., "Zooz", "Aqara", "Shelly")

    Returns:
        List of domains to search, ranked by likelihood
    """
    if not manufacturer:
        return []

    domains = []
    manufacturer_clean = manufacturer.strip()

    # 1. Get previously discovered domains (highest priority)
    registry = get_registry()
    known = registry.get_known_domains(manufacturer_clean)
    domains.extend(known)

    # 2. Infer primary domain from manufacturer name
    primary = _infer_primary_domain(manufacturer_clean)
    if primary:
        domains.append(primary)

    # 3. Add common support subdomains
    if primary:
        support_subdomains = _generate_support_subdomains(primary)
        domains.extend(support_subdomains)

    # 4. Add common CDN patterns (many manufacturers use these)
    cdn_patterns = _get_cdn_patterns(manufacturer_clean)
    domains.extend(cdn_patterns)

    # Deduplicate while preserving order
    seen = set()
    unique_domains = []
    for d in domains:
        if d not in seen:
            seen.add(d)
            unique_domains.append(d)

    logger.debug(f"Generated {len(unique_domains)} domains for {manufacturer}: {unique_domains[:5]}...")
    return unique_domains


def _infer_primary_domain(manufacturer: str) -> Optional[str]:
    """
    Infer the primary manufacturer domain from the name.

    Examples:
    - "Zooz" -> "zooz.com"
    - "Aqara" -> "aqara.com"
    - "Shelly" -> "shelly.cloud" (known exception)
    - "Ring" -> "ring.com"

    This uses common patterns and known exceptions.
    """
    name_lower = manufacturer.lower().strip()

    # Known exceptions (manufacturers with non-.com primary domains)
    exceptions = {
        "shelly": "shelly.cloud",
        "shellypro": "shelly.cloud",
        "fibaro": "fibaro.com",
        "aqara": "aqara.com",
        "homeseer": "homeseer.com",
        "inovelli": "inovelli.com",
        "zooz": "zooz.com",
        "ge": "byjasco.com",  # GE smart home is now Jasco
        "jasco": "byjasco.com",
    }

    if name_lower in exceptions:
        return exceptions[name_lower]

    # Default pattern: <manufacturer>.com
    # Remove spaces, hyphens, special characters
    clean = re.sub(r'[^a-z0-9]', '', name_lower)

    if clean:
        return f"{clean}.com"

    return None


def _generate_support_subdomains(primary_domain: str) -> List[str]:
    """
    Generate common support subdomains for a primary domain.

    Args:
        primary_domain: Primary domain (e.g., "zooz.com")

    Returns:
        List of support subdomains (e.g., ["support.zooz.com", "help.zooz.com"])
    """
    subdomains = [
        "support",
        "help",
        "docs",
        "documentation",
        "manual",
        "manuals",
        "kb",
        "knowledge",
        "downloads",
        "resources",
        "cdn",
        "assets",
    ]

    return [f"{sub}.{primary_domain}" for sub in subdomains]


def _get_cdn_patterns(manufacturer: str) -> List[str]:
    """
    Return CDN root domains commonly used for hosting documentation
    (PDF manuals, datasheets, etc.)

    IMPORTANT:
    - Only return DOMAINS, not paths
    - No wildcards
    - These are safe for Brave/Bing `site:` filtering
    """

    name_lower = manufacturer.lower().strip()
    name_clean = re.sub(r'[^a-z0-9]', '', name_lower)

    domains = [
        # Shopify CDN
        "cdn.shopify.com",
        "files.shopifycdn.com",

        # Amazon S3 bucket patterns
        f"{name_clean}.s3.amazonaws.com",
        f"{name_clean}-docs.s3.amazonaws.com",
        f"{name_clean}-manuals.s3.amazonaws.com",

        # Amazon CloudFront root (cannot enumerate random subdomains)
        "cloudfront.net",

        # Google Cloud Storage
        "storage.googleapis.com",
        "storage.cloud.google.com",

        # Firebase storage CDNs
        "firebasestorage.googleapis.com",

        # WordPress & WooCommerce media
        "wpengine.com",
        "wp.com",
        "gravatar.com",
        "wordpress.com",

        # Squarespace
        "squarespace.com",
        "static1.squarespace.com",

        # Wix
        "wixstatic.com",

        # BigCommerce
        "bigcommerce.com",
        "bcassetcdn.com",

        # Fastly (used by many doc sites)
        "fastly.net",
        "fastlyusercontent.com",

        # Cloudflare (used heavily for PDFs)
        "cdn.cloudflare.net",
        "cloudflare.net",

        # Akamai
        "akamaihd.net",

        # Cloudinary (common for PDFs and product files)
        "res.cloudinary.com",

        # DigitalOcean Spaces
        "digitaloceanspaces.com",

        # Linode Object Storage
        "linodeobjects.com",
    ]

    # Deduplicate
    unique = []
    seen = set()
    for d in domains:
        if d not in seen:
            seen.add(d)
            unique.append(d)

    return unique


def register_discovered_domain(manufacturer: str, url: str):
    """
    Register a successfully discovered documentation URL's domain.

    This helps improve future searches by learning from successful discoveries.

    Args:
        manufacturer: Manufacturer name
        url: Successfully discovered URL
    """
    try:
        # Extract domain from URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc

        if domain:
            registry = get_registry()
            registry.add_domain(manufacturer, domain)
    except Exception as e:
        logger.debug(f"Failed to register domain from {url}: {e}")


# Pre-populated known manufacturer domains (seed data)
# This provides a starting point before auto-discovery kicks in
KNOWN_MANUFACTURER_DOMAINS = {
    "Zooz": [
        "zooz.com",
        "support.zooz.com",
        "cdn.shopify.com",
    ],
    "Aqara": [
        "aqara.com",
        "support.aqara.com",
        "cdn.aqara.cn",
    ],
    "Shelly": [
        "shelly.cloud",
        "kb.shelly.cloud",
        "support.shelly.cloud",
    ],
    "Ring": [
        "ring.com",
        "support.ring.com",
    ],
    "Philips Hue": [
        "philips-hue.com",
        "www2.meethue.com",
        "developers.meethue.com",
    ],
    "Samsung SmartThings": [
        "smartthings.com",
        "support.smartthings.com",
    ],
    "Sonoff": [
        "sonoff.tech",
        "support.sonoff.tech",
    ],
    "TP-Link": [
        "tp-link.com",
        "www.tp-link.com",
        "support.tp-link.com",
    ],
}


def initialize_known_domains():
    """
    Initialize the registry with pre-populated known domains.

    Call this once at startup to seed the domain registry.
    """
    registry = get_registry()

    for manufacturer, domains in KNOWN_MANUFACTURER_DOMAINS.items():
        for domain in domains:
            registry.add_domain(manufacturer, domain)

    logger.info(f"Initialized domain registry with {len(KNOWN_MANUFACTURER_DOMAINS)} known manufacturers")
