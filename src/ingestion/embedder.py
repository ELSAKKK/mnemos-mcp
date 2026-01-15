"""Embedding generation for text chunks."""

import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


class BaseEmbedder(ABC):
    """Base class for embedding providers."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        pass


class OllamaEmbedder(BaseEmbedder):
    """Ollama local embedding provider."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        """
        Initialize Ollama embedder.

        Args:
            base_url: Ollama API base URL (defaults to settings)
            model: Model name (defaults to settings)
        """
        settings = get_settings()
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create a persistent client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text with retries."""
        if not text.strip():
            settings = get_settings()
            return [0.0] * settings.embedding_dimension

        if len(text) > 8000:
            text = text[:8000]

        max_retries = 3
        retry_delay = 1.0
        client = await self._get_client()

        for attempt in range(max_retries):
            try:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": text},
                )

                if response.status_code == 200:
                    data = response.json()
                    if "embeddings" in data and len(data["embeddings"]) > 0:
                        return data["embeddings"][0]
                    elif "embedding" in data:
                        return data["embedding"]
                    else:
                        raise ValueError(
                            f"Unexpected Ollama response format: {list(data.keys())}"
                        )

                if response.status_code == 500:
                    await asyncio.sleep(2.0 * (attempt + 1))

                logger.warning(
                    f"Ollama error {response.status_code} (Attempt {attempt+1}): {response.text[:200]}"
                )

            except (
                httpx.HTTPStatusError,
                httpx.RemoteProtocolError,
                httpx.ConnectError,
                httpx.ReadTimeout,
            ) as e:
                logger.warning(f"Ollama connection error: {str(e)} (Attempt {attempt+1})")

            if attempt < max_retries - 1:
                wait = retry_delay * (attempt + 1)
                await asyncio.sleep(wait)
            else:
                if "response" in locals():
                    response.raise_for_status()
                else:
                    raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.
        """
        if not texts:
            return []

        embeddings = []
        total = len(texts)
        for i, text in enumerate(texts):
            try:
                embedding = await self.embed(text)
                embeddings.append(embedding)
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.error(f"Failed embedding chunk {i+1}/{total}: {str(e)}")
                raise
        return embeddings


class Embedder:
    """
    Unified embedding interface focusing on Ollama.
    """

    def __init__(self):
        """Initialize embedder with Ollama provider."""
        self._embedder = OllamaEmbedder()

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        return await self._embedder.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return await self._embedder.embed_batch(texts)
