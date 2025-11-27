#!/usr/bin/env python3
"""
Quick test to verify all imports work correctly.
This catches NameError issues before starting the service.
"""

print("Testing imports...")

try:
    print("  - models.device_profile...", end=" ")
    from models.device_profile import DeviceProfile, DeviceType
    print("✓")
except Exception as e:
    print(f"✗ {e}")
    exit(1)

try:
    print("  - models...", end=" ")
    from models import DeviceProfile
    print("✓")
except Exception as e:
    print(f"✗ {e}")
    exit(1)

try:
    print("  - llm.provider...", end=" ")
    from llm.provider import LLMProvider
    print("✓")
except Exception as e:
    print(f"✗ {e}")
    exit(1)

try:
    print("  - rag.engine...", end=" ")
    from rag.engine import RAGEngine
    print("✓")
except Exception as e:
    print(f"✗ {e}")
    exit(1)

try:
    print("  - services.chat_service...", end=" ")
    from services.chat_service import ChatService
    print("✓")
except Exception as e:
    print(f"✗ {e}")
    exit(1)

try:
    print("  - services.document_service...", end=" ")
    from services.document_service import DocumentService
    print("✓")
except Exception as e:
    print(f"✗ {e}")
    exit(1)

try:
    print("  - services.analysis_service...", end=" ")
    from services.analysis_service import AnalysisService
    print("✓")
except Exception as e:
    print(f"✗ {e}")
    exit(1)

try:
    print("  - rag.fetcher...", end=" ")
    from rag.fetcher import DocumentAutoFetcher
    print("✓")
except Exception as e:
    print(f"✗ {e}")
    exit(1)

print("\n✅ All imports successful!")
