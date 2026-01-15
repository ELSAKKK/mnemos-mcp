"""Tests for configuration settings."""

import os
import pytest
from src.config import Settings, get_settings


class TestSettings:
    """Unit tests for Settings configuration."""

    def test_default_values(self):
        """Test that Settings has sensible defaults."""
        get_settings.cache_clear()
        
        settings = Settings()
        
        assert "postgresql" in settings.database_url
        assert settings.embedding_model == "nomic-embed-text"
        assert "11434" in settings.ollama_base_url
        assert settings.chunk_size > 0
        assert settings.chunk_overlap > 0
        assert settings.min_chunk_length > 0
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000

    def test_embedding_dimension(self):
        """Test embedding dimension property."""
        settings = Settings()
        assert settings.embedding_dimension == 768

    def test_get_settings_cached(self):
        """Test that get_settings returns cached instance."""
        get_settings.cache_clear()
        
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2

    def test_port_matches_docker_compose(self):
        """Test that default database port matches docker-compose.yml."""
        settings = Settings()
        assert "5433" in settings.database_url

    def test_min_chunk_length_configurable(self):
        """Test that min_chunk_length is configurable."""
        settings = Settings()
        assert settings.min_chunk_length == 20

    def test_chunk_settings(self):
        """Test chunk size and overlap are reasonable."""
        settings = Settings()
        assert settings.chunk_overlap < settings.chunk_size
        assert settings.chunk_size > 0
        assert settings.chunk_overlap >= 0
