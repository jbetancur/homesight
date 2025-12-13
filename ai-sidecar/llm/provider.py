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
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

logger = logging.getLogger(__name__)

from metrics.metrics  import (
    llm_inference_duration,
    llm_inferences,
    llm_input_tokens,
    llm_output_tokens
)


class CircuitBreaker:
    """
    Simple circuit breaker to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, reject requests immediately
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying again
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "OPEN":
            # Check if recovery timeout has elapsed
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info("Circuit breaker entering HALF_OPEN state (testing recovery)")
                self.state = "HALF_OPEN"
            else:
                raise Exception(f"Circuit breaker OPEN - OpenAI API unavailable (tried {self.failure_count} times)")

        try:
            result = func(*args, **kwargs)
            # Success - reset circuit breaker
            if self.state == "HALF_OPEN":
                logger.info("Circuit breaker closing (service recovered)")
            self.failure_count = 0
            self.state = "CLOSED"
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                logger.error(f"Circuit breaker OPEN after {self.failure_count} failures")
                self.state = "OPEN"

            raise


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
        self.chat_mode = getattr(config, 'chat_mode', 'local')  # Config-driven

        # Thread safety: llama.cpp is NOT thread-safe
        self._llama_lock = asyncio.Lock()

        # Initialize circuit breaker for OpenAI API
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=int(os.environ.get('OPENAI_CIRCUIT_BREAKER_THRESHOLD', '5')),
            recovery_timeout=int(os.environ.get('OPENAI_CIRCUIT_BREAKER_TIMEOUT', '60'))
        )

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
        """Initialize local Llama model with Vulkan GPU acceleration."""
        try:
            from llama_cpp import Llama
            model_path = Path(self.config.local_model_path)

            if not model_path.exists():
                logger.error(f"Local model not found at: {model_path}")
                return

            logger.info(f"Loading local LLM from {model_path}")

            llama_kwargs = {
                "model_path": str(model_path),
                "n_ctx": self.config.local_n_ctx,
                "n_threads": self.config.local_n_threads,
                "verbose": False,
            }

            # Vulkan activation
            if os.getenv("LLAMA_VULKAN", "1") == "1":
                logger.info("🟣 Vulkan GPU backend ACTIVE")
                llama_kwargs["use_vulkan"] = True
                llama_kwargs["n_gpu_layers"] = self.config.local_n_gpu_layers
            else:
                logger.info("⚠️ Vulkan disabled via LLAMA_VULKAN=0")
                llama_kwargs["use_vulkan"] = False
                llama_kwargs["n_gpu_layers"] = 0

            # Instantiate LLM
            self.local_llm = Llama(**llama_kwargs)

            # ==========================================================
            # GPU VERIFICATION
            # Note: llama-cpp-python doesn't expose backend info directly,
            # so we verify based on what we requested + successful load.
            # The verbose output during load confirms "using device Vulkan0"
            # n_gpu_layers: -1 means ALL layers to GPU, 0 means CPU only
            # ==========================================================
            n_gpu = llama_kwargs.get("n_gpu_layers", 0)
            gpu_active = llama_kwargs.get("use_vulkan") and n_gpu != 0  # -1 = all layers, >0 = some layers
            
            if gpu_active:
                layers_desc = "ALL" if n_gpu == -1 else str(n_gpu)
                logger.info(f"✅ Vulkan GPU acceleration ACTIVE")
                logger.info(f"   GPU layers: {layers_desc}")
                logger.info(f"🚀 Model loaded successfully with Vulkan backend")
            else:
                logger.info("ℹ️ Running in CPU-only mode")

        except Exception as e:
            logger.error(f"Failed to initialize local LLM: {e}")



    def _prepare_openai_kwargs(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Prepare OpenAI API kwargs with model-specific parameter handling.

        Consolidates GPT-5 special cases in one place.

        GPT-5 Differences:
        - Doesn't support temperature parameter (always uses default=1)
        - Uses max_completion_tokens instead of max_tokens
        """
        kwargs = {
            "model": self.config.openai_model,
            "messages": messages,
        }

        # GPT-5-mini doesn't support temperature parameter
        if "gpt-5" not in self.config.openai_model.lower():
            kwargs["temperature"] = temperature

        # GPT-5 models use max_completion_tokens instead of max_tokens
        if "gpt-5" in self.config.openai_model.lower():
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

        # Add tools if provided
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return kwargs

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        override_mode: Optional[str] = None
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """
        Generate chat response with explicit routing based on config.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (OpenAI format)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            override_mode: Optional override for chat_mode ('cloud' or 'local').
                          Use this to force a specific mode for a single request
                          without mutating shared state.

        Returns:
            Tuple of (response_text, tool_calls)
        """
        # Use override if provided, otherwise use configured mode
        effective_mode = override_mode if override_mode is not None else self.chat_mode

        if effective_mode == 'cloud':
            return self._chat_cloud(messages, tools, temperature, max_tokens)
        elif effective_mode == 'local':
            return self._chat_local(messages, temperature, max_tokens), None
        else:
            return f"Invalid chat mode: {effective_mode}", None

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

    def _call_openai_with_retry(self, **kwargs):
        """
        Call OpenAI API with retry logic and circuit breaker.

        Uses tenacity for exponential backoff retry and circuit breaker for failure protection.
        """
        @retry(
            retry=retry_if_exception_type((Exception,)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        def _make_request():
            return self.circuit_breaker.call(
                self.openai_client.chat.completions.create,
                **kwargs
            )

        return _make_request()

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: int
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """Chat using OpenAI with retry logic and circuit breaker"""
        start_time = time.time()
        status = "error"

        try:
            # Use centralized kwargs preparation (consolidates GPT-5 handling)
            kwargs = self._prepare_openai_kwargs(messages, temperature, max_tokens, tools)

            # Call OpenAI with retry logic and circuit breaker
            response = self._call_openai_with_retry(**kwargs)
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
        """Chat using local Llama model (crash-safe)."""

        start_time = time.time()
        status = "error"
        model_name = "llama-local"

        # Disable fork/thread crashes
        os.environ["TOKENIZERS_PARALLELISM"] = "false"

        try:
            # Do NOT manually insert BOS token
            formatted_prompt = ""

            # Build safe instruct prompt
            for msg in messages:
                role = msg["role"]
                content = msg["content"]

                # Strip unsafe special tokens
                for t in [
                    "<|begin_of_text|>",
                    "<|start_header_id|>",
                    "<|end_header_id|>",
                    "<|eot_id|>",
                    "<|end_of_text|>"
                ]:
                    content = content.replace(t, "")

                if role == "system":
                    formatted_prompt += f"<|start_header_id|>system<|end_header_id|>\n{content}<|eot_id|>"
                elif role == "user":
                    formatted_prompt += f"<|start_header_id|>user<|end_header_id|>\n{content}<|eot_id|>"
                elif role == "assistant":
                    formatted_prompt += f"<|start_header_id|>assistant<|end_header_id|>\n{content}<|eot_id|>"

            # Add assistant header for generation
            formatted_prompt += "<|start_header_id|>assistant<|end_header_id|>\n"

            # TRUNCATE PROMPT to avoid ggml crashes
            # Get max_prompt_chars from config (calculated as: n_ctx - max_tokens, with buffer)
            cfg = getattr(self, 'config', None)
            max_prompt_chars = getattr(cfg, 'chat_max_prompt_chars', 55000) if cfg else 55000
            if len(formatted_prompt) > max_prompt_chars:
                # Smart truncation: keep system message + last N user/assistant turns
                logger.warning(f"Local prompt exceeded {max_prompt_chars} chars ({len(formatted_prompt)}), truncating intelligently.")

                # Find system message end
                system_end = formatted_prompt.find("<|start_header_id|>user<|end_header_id|>")
                if system_end > 0:
                    system_msg = formatted_prompt[:system_end]
                    conversation = formatted_prompt[system_end:]

                    # Truncate conversation to fit
                    available = max_prompt_chars - len(system_msg)
                    if len(conversation) > available:
                        # Keep most recent conversation (end of string)
                        conversation = conversation[-available:]

                    formatted_prompt = system_msg + conversation
                else:
                    # Fallback: just truncate from start
                    formatted_prompt = formatted_prompt[:max_prompt_chars]

            # Estimate tokens for metrics and log for debugging
            input_token_count = len(formatted_prompt) // 4
            logger.info(f"📊 Prompt: {len(formatted_prompt)} chars, ~{input_token_count} tokens (n_ctx={self.config.local_n_ctx}, max_tokens={max_tokens})")
            llm_input_tokens.labels(model=model_name, provider="local").inc(input_token_count)

            # Run llama-cpp safely
            # Stop tokens for various model formats (Llama, Qwen, ChatML)
            response = self.local_llm(
                formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=[
                    "<|eot_id|>",           # Llama 3 format
                    "<|end_of_text|>",      # Llama 3 format  
                    "<|im_end|>",           # ChatML / Qwen format
                    "<|endoftext|>",        # GPT-2 style
                    "<|eot_header_id|>",    # Llama 3 role marker (shouldn't continue past)
                    "user<|",               # Prevent fake conversation continuation
                    "\nuser\n",             # Prevent fake conversation continuation
                ],
                echo=False
            )

            response_text = response['choices'][0]['text'].strip()

            # Output metrics
            output_token_count = len(response_text) // 4
            llm_output_tokens.labels(model=model_name, provider="local").inc(output_token_count)

            status = "success"
            return response_text

        finally:
            duration = time.time() - start_time
            llm_inference_duration.labels(model=model_name, provider="local").observe(duration)
            llm_inferences.labels(model=model_name, provider="local", status=status).inc()

    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        override_mode: Optional[str] = None
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """
        Async chat - for OpenAI (which has async client).
        Local mode falls back to sync.

        Args:
            override_mode: Optional override for chat_mode ('cloud' or 'local')
        """
        # Use override if provided, otherwise use configured mode
        effective_mode = override_mode if override_mode is not None else self.chat_mode

        if effective_mode == 'cloud' and self.openai_client:
            try:
                return await self._chat_openai_async(messages, tools, temperature, max_tokens)
            except Exception as e:
                logger.error(f"OpenAI async chat failed: {e}")
                return f"Cloud chat error: {str(e)}", None
        else:
            # Local mode: run sync in background
            loop = asyncio.get_event_loop()
            # Pass override_mode to sync chat
            return await loop.run_in_executor(
                None,
                lambda: self.chat(messages, tools, temperature, max_tokens, override_mode)
            )

    async def _call_openai_async_with_retry(self, client, **kwargs):
        """
        Call OpenAI API (async) with retry logic and circuit breaker.

        Uses tenacity for exponential backoff retry and circuit breaker for failure protection.
        """
        @retry(
            retry=retry_if_exception_type((Exception,)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        async def _make_request():
            # Circuit breaker check (sync operation)
            if self.circuit_breaker.state == "OPEN":
                if time.time() - self.circuit_breaker.last_failure_time >= self.circuit_breaker.recovery_timeout:
                    logger.info("Circuit breaker entering HALF_OPEN state (testing recovery)")
                    self.circuit_breaker.state = "HALF_OPEN"
                else:
                    raise Exception(f"Circuit breaker OPEN - OpenAI API unavailable")

            try:
                result = await client.chat.completions.create(**kwargs)
                # Success - reset circuit breaker
                if self.circuit_breaker.state == "HALF_OPEN":
                    logger.info("Circuit breaker closing (service recovered)")
                self.circuit_breaker.failure_count = 0
                self.circuit_breaker.state = "CLOSED"
                return result
            except Exception as e:
                self.circuit_breaker.failure_count += 1
                self.circuit_breaker.last_failure_time = time.time()
                if self.circuit_breaker.failure_count >= self.circuit_breaker.failure_threshold:
                    logger.error(f"Circuit breaker OPEN after {self.circuit_breaker.failure_count} failures")
                    self.circuit_breaker.state = "OPEN"
                raise

        return await _make_request()

    async def _chat_openai_async(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: int
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """Async OpenAI chat with retry logic and circuit breaker"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.config.openai_api_key)

        try:
            # Use centralized kwargs preparation (consolidates GPT-5 handling)
            kwargs = self._prepare_openai_kwargs(messages, temperature, max_tokens, tools)

            # Call OpenAI with retry logic and circuit breaker
            response = await self._call_openai_async_with_retry(client, **kwargs)
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

        # GPT-5-mini needs significantly higher token limits due to internal reasoning
        effective_max_tokens = max_tokens
        if "gpt-5" in self.config.openai_model.lower():
            # Scale up tokens to account for reasoning overhead
            # Minimum 4x to avoid reasoning consuming all tokens
            effective_max_tokens = max(max_tokens * 8, 4000)

        response, _ = self.chat(messages, tools=None, temperature=temperature, max_tokens=effective_max_tokens)
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

        # GPT-5-mini needs significantly higher token limits due to internal reasoning
        effective_max_tokens = max_tokens
        if "gpt-5" in self.config.openai_model.lower():
            # Scale up tokens to account for reasoning overhead
            # Minimum 4x to avoid reasoning consuming all tokens
            effective_max_tokens = max(max_tokens * 8, 4000)

        response, _ = await self.chat_async(messages, tools=None, temperature=temperature, max_tokens=effective_max_tokens)
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
