"""
LLM Provider with explicit config-driven routing

Chat modes:
- "cloud": OpenAI gpt-4o-mini (high quality, function calling, data to cloud)
- "local": Local Llama 3.2 (private, limited quality, no external calls)

Knowledge generation and analysis always use OpenAI (background operations).
"""

import logging
import asyncio
import os
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import json

logger = logging.getLogger(__name__)

from metrics import (
    llm_inference_duration,
    llm_inferences,
    llm_input_tokens,
    llm_output_tokens
)


class LLMProvider:
    """
    LLM provider with explicit routing based on config.

    Chat uses config-specified mode (cloud or local).
    Knowledge generation/analysis always use OpenAI.
    """

    def __init__(self, config):
        """
        Initialize LLM provider

        Args:
            config: LLMConfig with chat_mode ("cloud" or "local")
        """
        self.config = config
        self.openai_client = None
        self.local_llm = None
        self.chat_mode = getattr(config, 'chat_mode', 'cloud')  # Config-driven

        if self.chat_mode not in ('cloud', 'local'):
            raise ValueError(f"Invalid chat_mode: {self.chat_mode}. Must be 'cloud' or 'local'")

        # Initialize OpenAI (needed for cloud chat and background operations)
        if config.openai_api_key:
            self._init_openai()
        else:
            logger.warning("No OpenAI API key - OpenAI features disabled")

        # Initialize local LLM (needed if chat_mode == "local")
        if self.chat_mode == 'local' or config.provider in ["local", "hybrid"]:
            self._init_local()

    def _init_openai(self):
        """Initialize OpenAI client"""
        try:
            from openai import OpenAI
            self.openai_client = OpenAI(api_key=self.config.openai_api_key)
            logger.info("✅ OpenAI client initialized (primary LLM)")
        except ImportError:
            logger.error("openai package not installed. Install with: pip install openai")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI: {e}")

    def _init_local(self):
        """Initialize local Llama model"""
        try:
            from llama_cpp import Llama

            model_path = Path(self.config.local_model_path)
            if not model_path.is_absolute():
                model_path = Path(__file__).parent.parent / model_path

            if not model_path.exists():
                if self.config.local_auto_download:
                    logger.info("Local model not found, attempting download...")
                    if self._download_model(model_path):
                        logger.info("Model downloaded successfully")
                    else:
                        logger.warning("Model download failed, local LLM unavailable")
                        return
                else:
                    logger.warning(f"Local model not found: {model_path}")
                    return

            logger.info(f"Loading local LLM from {model_path}")
            self.local_llm = Llama(
                model_path=str(model_path),
                n_ctx=self.config.local_n_ctx,
                n_threads=self.config.local_n_threads,
                n_gpu_layers=self.config.local_n_gpu_layers,
                verbose=False
            )
            logger.info(f"✅ Local LLM loaded (fallback): {model_path.name}")

        except ImportError:
            logger.warning("llama-cpp-python not installed, local LLM unavailable")
        except Exception as e:
            logger.error(f"Failed to load local LLM: {e}")

    def _download_model(self, model_path: Path) -> bool:
        """Download model from HuggingFace"""
        try:
            from huggingface_hub import hf_hub_download
            import os

            model_path.parent.mkdir(parents=True, exist_ok=True)

            # Default to Llama 3.2 3B
            repo_id = "bartowski/Llama-3.2-3B-Instruct-GGUF"
            filename = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"

            logger.info(f"Downloading {filename} from {repo_id}...")

            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(model_path.parent),
                local_dir_use_symlinks=False,
                token=os.environ.get('HF_TOKEN')
            )

            temp_path = model_path.parent / filename
            if temp_path.exists():
                temp_path.rename(model_path)
                logger.info(f"✅ Model downloaded: {model_path}")
                return True

            return False

        except Exception as e:
            logger.error(f"Model download failed: {e}")
            return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """
        Generate chat response with explicit routing based on config.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (OpenAI format)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Tuple of (response_text, tool_calls)
        """
        if self.chat_mode == 'cloud':
            return self._chat_cloud(messages, tools, temperature, max_tokens)
        elif self.chat_mode == 'local':
            return self._chat_local(messages, temperature, max_tokens), None
        else:
            return "Invalid chat mode configuration", None

    def _chat_cloud(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: int
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """
        Cloud-based chat using OpenAI.
        Supports function calling, multi-turn conversation, tools.
        """
        if not self.openai_client:
            return "OpenAI not available (check API key)", None

        try:
            return self._chat_openai(messages, tools, temperature, max_tokens)
        except Exception as e:
            logger.error(f"OpenAI chat failed: {e}")
            return f"Cloud chat error: {str(e)}", None

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: int
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """Chat using OpenAI"""
        start_time = time.time()
        status = "error"

        try:
            kwargs = {
                "model": self.config.openai_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = self.openai_client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            # Track token usage
            if hasattr(response, 'usage'):
                llm_input_tokens.labels(
                    model=self.config.openai_model,
                    provider="openai"
                ).inc(response.usage.prompt_tokens)

                llm_output_tokens.labels(
                    model=self.config.openai_model,
                    provider="openai"
                ).inc(response.usage.completion_tokens)

            # Extract tool calls if present
            tool_calls = None
            if hasattr(message, 'tool_calls') and message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                    })

            response_text = message.content or ""
            status = "success"

            return response_text, tool_calls

        finally:
            # Track inference metrics
            duration = time.time() - start_time
            llm_inference_duration.labels(
                model=self.config.openai_model,
                provider="openai"
            ).observe(duration)

            llm_inferences.labels(
                model=self.config.openai_model,
                provider="openai",
                status=status
            ).inc()

    def _chat_local(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Chat using local Llama model"""
        start_time = time.time()
        status = "error"
        model_name = "llama-3.2-3b"  # Default model name

        try:
            # Format messages for Llama 3.2 Instruct
            formatted_prompt = "<|begin_of_text|>"

            for msg in messages:
                role = msg["role"]
                # Sanitize message content to avoid embedding Llama special tokens
                # If earlier generations or stored messages include markers like
                # "<|begin_of_text|>" or header tokens, strip them to avoid
                # duplicate leading tokens that reduce response quality.
                content = msg["content"]
                if isinstance(content, str):
                    for token in ["<|begin_of_text|>", "<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>", "<|end_of_text|>"]:
                        content = content.replace(token, "")

                if role == "system":
                    formatted_prompt += f"<|start_header_id|>system<|end_header_id|>\n\n{content}<|eot_id|>"
                elif role == "user":
                    formatted_prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{content}<|eot_id|>"
                elif role == "assistant":
                    formatted_prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n{content}<|eot_id|>"

            # Add assistant header for response
            formatted_prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"

            # Track input tokens (approximate based on prompt length)
            input_token_count = len(formatted_prompt) // 4  # Rough estimate: 4 chars per token
            llm_input_tokens.labels(
                model=model_name,
                provider="local"
            ).inc(input_token_count)

            response = self.local_llm(
                formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=["<|eot_id|>", "<|end_of_text|>"],
                echo=False
            )

            response_text = response['choices'][0]['text'].strip()

            # Track output tokens (approximate based on response length)
            output_token_count = len(response_text) // 4
            llm_output_tokens.labels(
                model=model_name,
                provider="local"
            ).inc(output_token_count)

            status = "success"
            return response_text

        finally:
            # Track inference metrics
            duration = time.time() - start_time
            llm_inference_duration.labels(
                model=model_name,
                provider="local"
            ).observe(duration)

            llm_inferences.labels(
                model=model_name,
                provider="local",
                status=status
            ).inc()

    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """
        Async chat - for OpenAI (which has async client).
        Local mode falls back to sync.
        """
        if self.chat_mode == 'cloud' and self.openai_client:
            try:
                return await self._chat_openai_async(messages, tools, temperature, max_tokens)
            except Exception as e:
                logger.error(f"OpenAI async chat failed: {e}")
                return f"Cloud chat error: {str(e)}", None
        else:
            # Local mode: run sync in background
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.chat,
                messages,
                tools,
                temperature,
                max_tokens
            )

    async def _chat_openai_async(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: int
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """Async OpenAI chat using AsyncOpenAI client"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.config.openai_api_key)

        try:
            kwargs = {
                "model": self.config.openai_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = await client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            tool_calls = None
            if hasattr(message, 'tool_calls') and message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                    })

            return message.content or "", tool_calls

        finally:
            await client.close()

    def simple_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512
    ) -> str:
        """Simple text generation"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response, _ = self.chat(messages, tools=None, temperature=temperature, max_tokens=max_tokens)
        return response

    async def simple_generate_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512
    ) -> str:
        """Async text generation"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response, _ = await self.chat_async(messages, tools=None, temperature=temperature, max_tokens=max_tokens)
        return response

    def is_available(self) -> bool:
        """Check if any LLM is available"""
        return self.openai_client is not None or self.local_llm is not None

    def get_info(self) -> Dict[str, Any]:
        """Get provider information"""
        return {
            "provider": "hybrid",
            "openai_available": self.openai_client is not None,
            "local_available": self.local_llm is not None,
            "openai_model": self.config.openai_model if self.openai_client else None,
            "local_model": str(self.config.local_model_path) if self.local_llm else None
        }
