"""
Document validation configuration for RAG document fetching.

This module provides configurable rules for validating that downloaded
documents match their target devices. All device-specific terms and
patterns are defined here rather than hardcoded in the fetcher.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class DeviceCategory:
    """
    Defines a device category with its identification keywords and expected content.
    
    Attributes:
        name: Category name (e.g., "usb_controller", "dimmer_switch")
        identification_keywords: Keywords in model/device_name that identify this category
        required_content_keywords: At least one of these must appear in valid documents
        conflicting_content_keywords: If too many of these appear, document is likely wrong
        conflicting_threshold: Number of conflicting keywords before rejection
    """
    name: str
    identification_keywords: List[str] = field(default_factory=list)
    required_content_keywords: List[str] = field(default_factory=list)
    conflicting_content_keywords: List[str] = field(default_factory=list)
    conflicting_threshold: int = 3


@dataclass 
class ManufacturerInfo:
    """
    Manufacturer-specific validation info.
    
    Attributes:
        name: Canonical manufacturer name
        aliases: Alternative names/spellings to look for in documents
        model_pattern: Regex pattern to extract model identifiers (e.g., "ZEN74")
    """
    name: str
    aliases: List[str] = field(default_factory=list)
    model_pattern: Optional[str] = None


class DocumentValidationConfig:
    """
    Centralized configuration for document validation rules.
    
    This class holds all configurable validation rules, making it easy
    to add new device categories or manufacturers without code changes.
    """
    
    def __init__(self):
        # Device categories with their identification and validation rules
        self._categories: Dict[str, DeviceCategory] = {}
        self._manufacturers: Dict[str, ManufacturerInfo] = {}
        
        # Load default configuration
        self._load_defaults()
    
    def _load_defaults(self):
        """Load default validation rules."""
        
        # USB Controllers / Coordinators
        self.add_category(DeviceCategory(
            name="usb_controller",
            identification_keywords=[
                "usb", "stick", "controller", "coordinator", 
                "gateway", "hub", "dongle", "adapter"
            ],
            required_content_keywords=[
                "usb", "dongle", "stick", "serial", "coordinator",
                "z-wave controller", "zwave controller", "zigbee coordinator"
            ],
            conflicting_content_keywords=[
                "toggle up", "toggle down", "load wire", "line wire", 
                "neutral wire", "wiring diagram", "single pole", 
                "3-way setup", "4-way setup", "incandescent", 
                "brightness control", "ramp rate", "fade-in"
            ],
            conflicting_threshold=3
        ))
        
        # Dimmers and Switches
        self.add_category(DeviceCategory(
            name="dimmer_switch",
            identification_keywords=[
                "dimmer", "switch", "toggle", "relay"
            ],
            required_content_keywords=[
                "wiring", "load", "line", "neutral", "install"
            ],
            conflicting_content_keywords=[],  # No conflicts for switches
            conflicting_threshold=999
        ))
        
        # Sensors
        self.add_category(DeviceCategory(
            name="sensor",
            identification_keywords=[
                "sensor", "detector", "motion", "contact", 
                "leak", "temperature", "humidity"
            ],
            required_content_keywords=[
                "sensor", "detect", "battery", "alert", "notification"
            ],
            conflicting_content_keywords=[
                "toggle up", "toggle down", "load wire", "line wire",
                "neutral wire", "wiring diagram", "single pole"
            ],
            conflicting_threshold=5
        ))
        
        # Common manufacturers with their aliases and model patterns
        self.add_manufacturer(ManufacturerInfo(
            name="zooz",
            aliases=["zooz", "z-wave", "zwave"],
            model_pattern=r"ZEN\d{2}|ZSE\d{2}|ZST\d{2}|ZAC\d{2}|ZTR\d{2}|ZWA\d{2}"
        ))
        
        self.add_manufacturer(ManufacturerInfo(
            name="aqara",
            aliases=["aqara", "xiaomi", "lumi"],
            model_pattern=r"[A-Z]{4,6}\d{2}[A-Z]{2}"  # e.g., SJCGQ11LM
        ))
        
        self.add_manufacturer(ManufacturerInfo(
            name="philips",
            aliases=["philips", "hue", "signify"],
            model_pattern=r"[A-Z]{3}\d{3}"
        ))
        
        self.add_manufacturer(ManufacturerInfo(
            name="sonoff",
            aliases=["sonoff", "itead", "ewelink"],
            model_pattern=r"[A-Z]+\d*[A-Z]*"
        ))
        
        self.add_manufacturer(ManufacturerInfo(
            name="shelly",
            aliases=["shelly", "allterco"],
            model_pattern=r"[A-Za-z]+\d*[A-Za-z]*"
        ))
    
    def add_category(self, category: DeviceCategory):
        """Add or update a device category."""
        self._categories[category.name] = category
    
    def add_manufacturer(self, manufacturer: ManufacturerInfo):
        """Add or update a manufacturer."""
        self._manufacturers[manufacturer.name.lower()] = manufacturer
    
    def get_category_for_model(self, model: str, device_name: Optional[str] = None) -> Optional[DeviceCategory]:
        """
        Determine device category based on model and device name.
        
        Args:
            model: Device model string
            device_name: Optional device name
            
        Returns:
            Matching DeviceCategory or None
        """
        search_text = f"{model} {device_name or ''}".lower()
        
        for category in self._categories.values():
            if any(kw in search_text for kw in category.identification_keywords):
                return category
        
        return None
    
    def get_manufacturer_info(self, manufacturer: str) -> Optional[ManufacturerInfo]:
        """
        Get manufacturer info by name.
        
        Args:
            manufacturer: Manufacturer name
            
        Returns:
            ManufacturerInfo or None
        """
        return self._manufacturers.get(manufacturer.lower())
    
    def extract_model_identifiers(
        self, 
        model: str, 
        device_name: Optional[str], 
        manufacturer: Optional[str]
    ) -> Set[str]:
        """
        Extract model identifiers from model/device_name using manufacturer patterns.
        
        Args:
            model: Device model string
            device_name: Optional device name
            manufacturer: Optional manufacturer name
            
        Returns:
            Set of extracted model identifiers
        """
        search_text = f"{model} {device_name or ''}".upper()
        identifiers = set()
        
        # Try manufacturer-specific pattern first
        if manufacturer:
            mfr_info = self.get_manufacturer_info(manufacturer)
            if mfr_info and mfr_info.model_pattern:
                identifiers.update(re.findall(mfr_info.model_pattern, search_text))
        
        # Fallback: generic alphanumeric pattern (2-4 letters + 2-3 digits)
        if not identifiers:
            identifiers.update(re.findall(r'[A-Z]{2,4}\d{2,3}', search_text))
        
        return identifiers
    
    def find_model_numbers_in_text(
        self, 
        text: str, 
        manufacturer: Optional[str] = None
    ) -> Set[str]:
        """
        Find all model numbers in document text.
        
        Only uses specific manufacturer patterns to avoid false positives.
        Does NOT apply all patterns - only the one for the specified manufacturer.
        
        Args:
            text: Document text (should be uppercase)
            manufacturer: Optional manufacturer to use specific pattern
            
        Returns:
            Set of found model numbers
        """
        found = set()
        
        # Only use manufacturer-specific pattern if specified
        if manufacturer:
            mfr_info = self.get_manufacturer_info(manufacturer)
            if mfr_info and mfr_info.model_pattern:
                found.update(re.findall(mfr_info.model_pattern, text))
                return found
        
        # If no manufacturer specified, use strict patterns only
        # These are patterns that are very unlikely to have false positives
        strict_patterns = [
            r'ZEN\d{2}',  # Zooz switches/dimmers
            r'ZSE\d{2}',  # Zooz sensors
            r'ZST\d{2}',  # Zooz USB controllers
            r'ZAC\d{2}',  # Zooz accessories
        ]
        for pattern in strict_patterns:
            found.update(re.findall(pattern, text))
        
        return found
    
    def manufacturer_found_in_text(self, manufacturer: str, text_lower: str) -> bool:
        """
        Check if manufacturer (or its aliases) appears in text.
        
        Args:
            manufacturer: Manufacturer name
            text_lower: Lowercase document text
            
        Returns:
            True if manufacturer or alias found
        """
        mfr_info = self.get_manufacturer_info(manufacturer)
        if mfr_info:
            return any(alias in text_lower for alias in mfr_info.aliases)
        
        # Fallback: just check the manufacturer name directly
        return manufacturer.lower() in text_lower


# Global singleton instance
_validation_config: Optional[DocumentValidationConfig] = None


def get_validation_config() -> DocumentValidationConfig:
    """Get the global validation configuration instance."""
    global _validation_config
    if _validation_config is None:
        _validation_config = DocumentValidationConfig()
    return _validation_config
