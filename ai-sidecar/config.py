"""Configuration management for HomeSight AI"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class InferenceConfig(BaseModel):
    """Inference concurrency configuration"""
    max_concurrent_tasks: int = Field(default=4, description="Semaphore limit for concurrent analyze requests")


class LLMConfig(BaseModel):
    """LLM provider configuration"""
    # Chat routing (explicit user choice)
    chat_mode: str = Field(
        default="cloud",
        description="Chat mode: 'cloud' (OpenAI, quality/tools) or 'local' (Llama 3.2, private)"
    )

    provider: str = Field(default="local", description="Provider type for initialization")
    openai_api_key: Optional[str] = None
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")

    # Local LLM settings
    local_model_path: str = Field(default="./models/llama-3.2-3b-instruct.gguf")
    local_auto_download: bool = True
    local_n_ctx: int = 4096
    local_n_threads: int = 4
    local_n_gpu_layers: int = 0

    # Inference concurrency settings (for background operations)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)


class RAGConfig(BaseModel):
    """RAG engine configuration"""
    persist_directory: str = Field(default="/var/lib/homesight/rag")
    fallback_directory: str = Field(default="./data/rag")
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    batch_size_documents: int = Field(default=3, description="Batch size for PDF/official documentation ingestion")
    batch_size_community: int = Field(default=2, description="Batch size for community source ingestion")
    manufacturers: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Known manufacturer documentation URL patterns")


class DocumentFetcherConfig(BaseModel):
    """Document fetcher configuration"""
    cache_directory: str = Field(default="~/.homesight/manuals")


class SingleQueueConfig(BaseModel):
    """Configuration for a single task queue"""
    max_concurrent: int = Field(default=2, description="Max concurrent tasks")
    max_queue_depth: int = Field(default=10, description="Max pending tasks")
    cpu_threshold: float = Field(default=0.80, description="CPU threshold (0-1)")
    memory_threshold: float = Field(default=0.85, description="Memory threshold (0-1)")


class QueuesConfig(BaseModel):
    """Task queue configurations"""
    discovery: SingleQueueConfig = Field(default_factory=SingleQueueConfig)
    ingestion: SingleQueueConfig = Field(default_factory=lambda: SingleQueueConfig(max_concurrent=2, max_queue_depth=5))
    analysis: SingleQueueConfig = Field(default_factory=lambda: SingleQueueConfig(max_concurrent=4, max_queue_depth=20))


class Config(BaseModel):
    """Main application configuration"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    document_fetcher: DocumentFetcherConfig = Field(default_factory=DocumentFetcherConfig)
    queues: QueuesConfig = Field(default_factory=QueuesConfig)
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

            # Inference concurrency settings
            inference_section = llm_section.get('inference', {})
            inference_config_data = {}
            if 'max_concurrent_tasks' in inference_section:
                inference_config_data['max_concurrent_tasks'] = inference_section['max_concurrent_tasks']

            if inference_config_data:
                llm_config_data['inference'] = InferenceConfig(**inference_config_data)

            # Extract backend_url from root level if present
            backend_url = yaml_data.get('backend_url', 'http://localhost:8080')

            # Build RAG config
            rag_config_data = {}
            rag_section = yaml_data.get('rag', {})
            if 'batch_size_documents' in rag_section:
                rag_config_data['batch_size_documents'] = rag_section['batch_size_documents']
            if 'batch_size_community' in rag_section:
                rag_config_data['batch_size_community'] = rag_section['batch_size_community']
            if 'manufacturers' in rag_section:
                rag_config_data['manufacturers'] = rag_section['manufacturers']

            return cls(
                llm=LLMConfig(**llm_config_data),
                rag=RAGConfig(**rag_config_data),
                document_fetcher=DocumentFetcherConfig(),
                backend_url=backend_url
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
