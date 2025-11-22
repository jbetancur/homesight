"""Hybrid LLM provider supporting OpenAI with local fallback"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class HybridLLMProvider:
    """
    Hybrid LLM provider that uses OpenAI for chat/analysis with local fallback.

    Strategy:
    - Primary: OpenAI (GPT-4o-mini) for chat, function calling, complex reasoning
    - Fallback: Local Llama for simple queries when OpenAI unavailable
    - Embeddings: Always local (FastEmbed)
    """

    def __init__(self, config):
        """
        Initialize hybrid LLM provider

        Args:
            config: LLMConfig instance
        """
        self.config = config
        self.openai_client = None
        self.local_llm = None

        # Initialize OpenAI (primary)
        if config.openai_api_key:
            self._init_openai()
        else:
            logger.warning("No OpenAI API key - OpenAI features disabled")

        # Initialize local LLM (fallback)
        if config.provider in ["local", "hybrid"]:
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
        Generate chat response with optional function calling

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (OpenAI format)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Tuple of (response_text, tool_calls)
        """
        # Try OpenAI first (supports function calling)
        if self.openai_client and tools:
            try:
                return self._chat_openai(messages, tools, temperature, max_tokens)
            except Exception as e:
                logger.error(f"OpenAI chat failed: {e}")
                # Don't fall back to local for function calling - it won't work
                return f"I'm having trouble connecting to my reasoning engine. Error: {str(e)}", None

        # Use OpenAI for complex multi-turn conversations
        if self.openai_client and len(messages) > 2:
            try:
                return self._chat_openai(messages, None, temperature, max_tokens)
            except Exception as e:
                logger.error(f"OpenAI chat failed, falling back to local: {e}")

        # Fallback to local for simple queries
        if self.local_llm:
            try:
                return self._chat_local(messages, temperature, max_tokens), None
            except Exception as e:
                logger.error(f"Local chat failed: {e}")
                return f"I'm having trouble generating a response: {str(e)}", None

        return "AI service unavailable. Please check configuration.", None

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: int
    ) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
        """Chat using OpenAI"""
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

        return response_text, tool_calls

    def _chat_local(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Chat using local Llama model"""
        # Format messages for Llama 3.2 Instruct
        formatted_prompt = "<|begin_of_text|>"

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                formatted_prompt += f"<|start_header_id|>system<|end_header_id|>\n\n{content}<|eot_id|>"
            elif role == "user":
                formatted_prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{content}<|eot_id|>"
            elif role == "assistant":
                formatted_prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n{content}<|eot_id|>"

        # Add assistant header for response
        formatted_prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"

        response = self.local_llm(
            formatted_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["<|eot_id|>", "<|end_of_text|>"],
            echo=False
        )

        return response['choices'][0]['text'].strip()

    def simple_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512
    ) -> str:
        """
        Simple text generation (for backward compatibility)

        Args:
            prompt: User prompt
            system_prompt: Optional system instruction
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Generated text
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response, _ = self.chat(messages, tools=None, temperature=temperature, max_tokens=max_tokens)
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
