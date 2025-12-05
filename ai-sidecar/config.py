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
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")

    # Local LLM settings
    local_model_path: str = Field(default="./models/llama-3.2-3b-instruct.gguf")
    local_n_ctx: int = 4096
    local_n_threads: int = 4
    local_n_gpu_layers: int = 0

    # Chat inference settings
    chat_temperature: float = Field(default=0.3, description="Temperature for chat responses (lower = less hallucination)")
    chat_max_tokens: int = Field(default=400, description="Max tokens for chat responses")
    chat_max_system_prompt_chars: int = Field(default=6000, description="Max chars for system prompt")
    chat_max_user_message_chars: int = Field(default=2000, description="Max chars for user message")
    chat_max_memory_turns: int = Field(default=20, description="Max conversation turns to store per session")
    chat_context_turns: int = Field(default=10, description="Conversation turns to include in LLM context")

    # Inference concurrency settings (for background operations)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)

    @property
    def openai_api_key(self) -> Optional[str]:
        """Get OpenAI API key from environment variable"""
        return os.getenv("OPENAI_API_KEY")


class RAGConfig(BaseModel):
    """RAG engine configuration"""
    persist_directory: str = Field(default="/var/lib/homesight/rag")
    fallback_directory: str = Field(default="./data/rag")
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    batch_size_documents: int = Field(default=3, description="Batch size for PDF/official documentation ingestion")
    batch_size_community: int = Field(default=2, description="Batch size for community source ingestion")
    
    # Document processing
    chunk_size: int = Field(default=2000, description="Max characters per text chunk for embedding")
    min_document_length: int = Field(default=100, description="Minimum chars for a document to be valid")
    
    # Cache settings  
    query_cache_max_size: int = Field(default=100, description="Max cached query results")
    query_cache_ttl_seconds: int = Field(default=300, description="Query cache TTL in seconds")
    max_workers: int = Field(default=8, description="Thread pool workers for async ingestion")


class SearchConfig(BaseModel):
    """Web search API configuration"""
    enable_vendor_indexer: bool = Field(default=True, description="Enable background vendor documentation indexing")
    vendor_refresh_days: int = Field(default=7, description="Days between vendor index refreshes")
    
    # Search parameters
    max_results: int = Field(default=10, description="Max search results per query")
    search_timeout_seconds: float = Field(default=15.0, description="HTTP timeout for search APIs")
    download_timeout_seconds: float = Field(default=30.0, description="HTTP timeout for downloading documents")
    rate_limit_cooldown_seconds: int = Field(default=65, description="Cooldown after rate limit (429)")

    @property
    def brave_api_key(self) -> Optional[str]:
        """Get Brave Search API key from environment variable"""
        return os.getenv("BRAVE_SEARCH_API_KEY")

    @property
    def bing_api_key(self) -> Optional[str]:
        """Get Bing Search API key from environment variable"""
        return os.getenv("BING_SEARCH_API_KEY")


class DocumentFetcherConfig(BaseModel):
    """Document fetcher configuration"""
    cache_directory: str = Field(default="~/homesight/manuals")


class SingleQueueConfig(BaseModel):
    """Configuration for a single task queue"""
    max_concurrent: int = Field(default=2, description="Max concurrent tasks")
    max_queue_depth: int = Field(default=10, description="Max pending tasks")
    cpu_threshold: float = Field(default=0.80, description="CPU threshold (0-1)")
    memory_threshold: float = Field(default=0.85, description="Memory threshold (0-1)")


class WeatherConfig(BaseModel):
    """Weather service configuration"""
    zip_code: str = Field(default="94102", description="ZIP code for weather location")
    location_name: Optional[str] = Field(default=None, description="Location name (auto-detected from ZIP if not set)")
    cache_duration_minutes: int = Field(default=15, description="How long to cache weather data")
    refresh_interval_minutes: int = Field(default=90, description="Background refresh interval")


class QueuesConfig(BaseModel):
    """Task queue configurations"""
    discovery: SingleQueueConfig = Field(default_factory=SingleQueueConfig)
    ingestion: SingleQueueConfig = Field(default_factory=lambda: SingleQueueConfig(max_concurrent=2, max_queue_depth=5))
    analysis: SingleQueueConfig = Field(default_factory=lambda: SingleQueueConfig(max_concurrent=4, max_queue_depth=20))


class ErraticConfig(BaseModel):
    """Erratic behavior detection configuration"""
    decay_half_life_seconds: float = Field(
        default=300.0,
        description="Exponential decay half-life for erratic scores (seconds)"
    )
    threshold: float = Field(
        default=0.5,
        description="Threshold for flagging a device as erratic (0.0-1.0)"
    )
    list_threshold: float = Field(
        default=0.3,
        description="Threshold for listing in erratic devices query (0.0-1.0)"
    )


class HSILConfig(BaseModel):
    """HSIL (HomeSight Intelligence Layer) configuration"""
    erratic: ErraticConfig = Field(default_factory=ErraticConfig)


class Config(BaseModel):
    """Main application configuration"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    document_fetcher: DocumentFetcherConfig = Field(default_factory=DocumentFetcherConfig)
    queues: QueuesConfig = Field(default_factory=QueuesConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    hsil: HSILConfig = Field(default_factory=HSILConfig)
    backend_url: str = Field(
        default_factory=lambda: os.getenv('BACKEND_URL', 'http://localhost:8080'),
        description="HomeSight Go backend API URL"
    )

    @property
    def bing_search_api_key(self) -> Optional[str]:
        """Convenience property for Bing API key"""
        return self.search.bing_api_key

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

            llm_section = ai_config.get('llm', {})
            if 'provider' in llm_section:
                llm_config_data['provider'] = llm_section['provider']
            if 'chat_mode' in llm_section:
                llm_config_data['chat_mode'] = llm_section['chat_mode']

            # Local settings
            local_section = llm_section.get('local', {})
            if 'model_path' in local_section:
                llm_config_data['local_model_path'] = local_section['model_path']
            if 'n_ctx' in local_section:
                llm_config_data['local_n_ctx'] = local_section['n_ctx']
            if 'n_threads' in local_section:
                llm_config_data['local_n_threads'] = local_section['n_threads']
            if 'n_gpu_layers' in local_section:
                llm_config_data['local_n_gpu_layers'] = local_section['n_gpu_layers']
            if 'temperature' in local_section:
                llm_config_data['chat_temperature'] = local_section['temperature']
            if 'max_tokens' in local_section:
                llm_config_data['chat_max_tokens'] = local_section['max_tokens']
            if 'max_system_prompt_chars' in local_section:
                llm_config_data['chat_max_system_prompt_chars'] = local_section['max_system_prompt_chars']
            if 'max_user_message_chars' in local_section:
                llm_config_data['chat_max_user_message_chars'] = local_section['max_user_message_chars']
            if 'max_memory_turns' in local_section:
                llm_config_data['chat_max_memory_turns'] = local_section['max_memory_turns']
            if 'context_turns' in local_section:
                llm_config_data['chat_context_turns'] = local_section['context_turns']

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

            # Extract backend_url: environment variable takes precedence over YAML
            backend_url = os.getenv('BACKEND_URL') or yaml_data.get('backend_url', 'http://localhost:8080')

            # Build RAG config
            rag_config_data = {}
            rag_section = yaml_data.get('rag', {})
            if 'batch_size_documents' in rag_section:
                rag_config_data['batch_size_documents'] = rag_section['batch_size_documents']
            if 'batch_size_community' in rag_section:
                rag_config_data['batch_size_community'] = rag_section['batch_size_community']
            if 'chunk_size' in rag_section:
                rag_config_data['chunk_size'] = rag_section['chunk_size']
            if 'min_document_length' in rag_section:
                rag_config_data['min_document_length'] = rag_section['min_document_length']
            if 'query_cache_max_size' in rag_section:
                rag_config_data['query_cache_max_size'] = rag_section['query_cache_max_size']
            if 'query_cache_ttl_seconds' in rag_section:
                rag_config_data['query_cache_ttl_seconds'] = rag_section['query_cache_ttl_seconds']
            if 'max_workers' in rag_section:
                rag_config_data['max_workers'] = rag_section['max_workers']

            # Build Search config
            search_config_data = {}
            search_section = yaml_data.get('search', {})
            if 'enable_vendor_indexer' in search_section:
                search_config_data['enable_vendor_indexer'] = search_section['enable_vendor_indexer']
            if 'vendor_refresh_days' in search_section:
                search_config_data['vendor_refresh_days'] = search_section['vendor_refresh_days']
            if 'max_results' in search_section:
                search_config_data['max_results'] = search_section['max_results']
            if 'search_timeout_seconds' in search_section:
                search_config_data['search_timeout_seconds'] = search_section['search_timeout_seconds']
            if 'download_timeout_seconds' in search_section:
                search_config_data['download_timeout_seconds'] = search_section['download_timeout_seconds']
            if 'rate_limit_cooldown_seconds' in search_section:
                search_config_data['rate_limit_cooldown_seconds'] = search_section['rate_limit_cooldown_seconds']

            # Build Weather config
            weather_config_data = {}
            weather_section = yaml_data.get('weather', {})
            if 'zip_code' in weather_section:
                weather_config_data['zip_code'] = str(weather_section['zip_code'])
            if 'location_name' in weather_section:
                weather_config_data['location_name'] = weather_section['location_name']
            if 'cache_duration_minutes' in weather_section:
                weather_config_data['cache_duration_minutes'] = weather_section['cache_duration_minutes']
            if 'refresh_interval_minutes' in weather_section:
                weather_config_data['refresh_interval_minutes'] = weather_section['refresh_interval_minutes']

            # Build HSIL config
            hsil_config_data = {}
            hsil_section = ai_config.get('hsil', {})
            erratic_section = hsil_section.get('erratic', {})
            erratic_config_data = {}
            if 'decay_half_life_seconds' in erratic_section:
                erratic_config_data['decay_half_life_seconds'] = float(erratic_section['decay_half_life_seconds'])
            if 'threshold' in erratic_section:
                erratic_config_data['threshold'] = float(erratic_section['threshold'])
            if 'list_threshold' in erratic_section:
                erratic_config_data['list_threshold'] = float(erratic_section['list_threshold'])

            if erratic_config_data:
                hsil_config_data['erratic'] = ErraticConfig(**erratic_config_data)

            return cls(
                llm=LLMConfig(**llm_config_data),
                rag=RAGConfig(**rag_config_data),
                search=SearchConfig(**search_config_data),
                weather=WeatherConfig(**weather_config_data),
                hsil=HSILConfig(**hsil_config_data) if hsil_config_data else HSILConfig(),
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
