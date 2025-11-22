"""Configuration management for HomeSight AI"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    """LLM provider configuration"""
    provider: str = Field(default="hybrid", description="Provider type: 'openai', 'local', or 'hybrid'")
    openai_api_key: Optional[str] = None
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")

    # Local LLM settings
    local_model_path: str = Field(default="./models/llama-3.2-3b-instruct.gguf")
    local_auto_download: bool = True
    local_n_ctx: int = 4096
    local_n_threads: int = 4
    local_n_gpu_layers: int = 0


class RAGConfig(BaseModel):
    """RAG engine configuration"""
    persist_directory: str = Field(default="/var/lib/homesight/rag")
    fallback_directory: str = Field(default="./data/rag")
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")


class DocumentFetcherConfig(BaseModel):
    """Document fetcher configuration"""
    cache_directory: str = Field(default="~/.homesight/manuals")
    enable_forums: bool = True
    enable_reddit: bool = True
    enable_youtube: bool = False  # Requires additional API setup


class Config(BaseModel):
    """Main application configuration"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    document_fetcher: DocumentFetcherConfig = Field(default_factory=DocumentFetcherConfig)
    backend_url: str = Field(default="http://localhost:8080", description="HomeSight Go backend API URL")

    @classmethod
    def load_from_yaml(cls, config_path: Optional[str] = None) -> "Config":
        """Load configuration from YAML file"""
        if not config_path:
            config_path = os.getenv("HOMESIGHT_CONFIG", "config.yaml")

        # Try multiple locations
        possible_paths = [
            Path(config_path) if os.path.isabs(config_path) else None,
            Path(__file__).parent.parent / config_path,
            Path.cwd() / config_path,
            Path.cwd().parent / config_path,
        ]

        config_file = None
        for path in possible_paths:
            if path and path.exists():
                config_file = path
                break

        if not config_file:
            logger.warning(f"Config file not found, using defaults. Tried: {[str(p) for p in possible_paths if p]}")
            return cls()

        logger.info(f"Loading config from: {config_file}")
        try:
            with open(config_file, 'r') as f:
                yaml_data = yaml.safe_load(f) or {}

            # Extract AI section
            ai_config = yaml_data.get('ai', {})

            # Build LLM config
            llm_config_data = {}
            if 'openai_api_key' in ai_config:
                llm_config_data['openai_api_key'] = ai_config['openai_api_key']

            llm_section = ai_config.get('llm', {})
            if 'provider' in llm_section:
                llm_config_data['provider'] = llm_section['provider']

            # Local settings
            local_section = llm_section.get('local', {})
            if 'model_path' in local_section:
                llm_config_data['local_model_path'] = local_section['model_path']
            if 'auto_download' in local_section:
                llm_config_data['local_auto_download'] = local_section['auto_download']
            if 'n_ctx' in local_section:
                llm_config_data['local_n_ctx'] = local_section['n_ctx']
            if 'n_threads' in local_section:
                llm_config_data['local_n_threads'] = local_section['n_threads']
            if 'n_gpu_layers' in local_section:
                llm_config_data['local_n_gpu_layers'] = local_section['n_gpu_layers']

            # OpenAI settings
            openai_section = llm_section.get('openai', {})
            if 'model' in openai_section:
                llm_config_data['openai_model'] = openai_section['model']

            return cls(
                llm=LLMConfig(**llm_config_data),
                rag=RAGConfig(),
                document_fetcher=DocumentFetcherConfig()
            )

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return cls()


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance"""
    global _config
    if _config is None:
        _config = Config.load_from_yaml()
    return _config


def reload_config():
    """Reload configuration from file"""
    global _config
    _config = Config.load_from_yaml()
    return _config
