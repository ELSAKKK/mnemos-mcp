"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/mnemos"

    embedding_model: str = "nomic-embed-text"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "nomic-embed-text"

    chunk_size: int = 200
    chunk_overlap: int = 30
    min_chunk_length: int = 20

    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def embedding_dimension(self) -> int:
        """Return embedding dimension for Ollama model."""
        return 768


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()