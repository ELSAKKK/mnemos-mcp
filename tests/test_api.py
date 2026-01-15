"""Tests for API schemas and basic route functionality."""

import pytest
from pydantic import ValidationError
from src.api.schemas import (
    SearchRequest,
    ContextRequest,
    URLIngestRequest,
    SiteCrawlRequest,
    DocumentResponse,
    HealthResponse,
)


class TestSearchRequest:
    """Tests for SearchRequest schema."""

    def test_valid_request(self):
        """Test valid search request."""
        request = SearchRequest(query="test query")
        assert request.query == "test query"
        assert request.k == 5 
        assert request.min_score == 0.0 

    def test_custom_k(self):
        """Test custom k parameter."""
        request = SearchRequest(query="test", k=10)
        assert request.k == 10

    def test_k_bounds(self):
        """Test k parameter bounds."""
        with pytest.raises(ValidationError):
            SearchRequest(query="test", k=0)
        with pytest.raises(ValidationError):
            SearchRequest(query="test", k=25)

    def test_min_score_bounds(self):
        """Test min_score parameter bounds."""
        with pytest.raises(ValidationError):
            SearchRequest(query="test", min_score=-0.1)
        with pytest.raises(ValidationError):
            SearchRequest(query="test", min_score=1.5)

    def test_empty_query_rejected(self):
        """Test that empty query is rejected."""
        with pytest.raises(ValidationError):
            SearchRequest(query="")

    def test_collection_filter(self):
        """Test collection filter."""
        request = SearchRequest(query="test", collection="my-docs")
        assert request.collection == "my-docs"


class TestContextRequest:
    """Tests for ContextRequest schema."""

    def test_valid_request(self):
        """Test valid context request."""
        request = ContextRequest(query="test")
        assert request.query == "test"
        assert request.k == 5
        assert request.max_tokens == 4000

    def test_max_tokens_bounds(self):
        """Test max_tokens parameter bounds."""
        with pytest.raises(ValidationError):
            ContextRequest(query="test", max_tokens=50) 
        with pytest.raises(ValidationError):
            ContextRequest(query="test", max_tokens=20000) 


class TestURLIngestRequest:
    """Tests for URLIngestRequest schema."""

    def test_valid_request(self):
        """Test valid URL ingest request."""
        request = URLIngestRequest(url="https://example.com")
        assert request.url == "https://example.com"
        assert request.collection == "default"

    def test_custom_collection(self):
        """Test custom collection."""
        request = URLIngestRequest(url="https://example.com", collection="docs")
        assert request.collection == "docs"


class TestSiteCrawlRequest:
    """Tests for SiteCrawlRequest schema."""

    def test_valid_request(self):
        """Test valid site crawl request."""
        request = SiteCrawlRequest(url="https://docs.example.com")
        assert request.url == "https://docs.example.com"
        assert request.max_pages == 50
        assert request.max_depth == 3

    def test_max_pages_bounds(self):
        """Test max_pages parameter bounds."""
        with pytest.raises(ValidationError):
            SiteCrawlRequest(url="https://example.com", max_pages=0)
        with pytest.raises(ValidationError):
            SiteCrawlRequest(url="https://example.com", max_pages=500)

    def test_max_depth_bounds(self):
        """Test max_depth parameter bounds."""
        with pytest.raises(ValidationError):
            SiteCrawlRequest(url="https://example.com", max_depth=0)
        with pytest.raises(ValidationError):
            SiteCrawlRequest(url="https://example.com", max_depth=10)

    def test_path_filter(self):
        """Test path filter."""
        request = SiteCrawlRequest(
            url="https://docs.example.com",
            path_filter="/api/"
        )
        assert request.path_filter == "/api/"


class TestHealthResponse:
    """Tests for HealthResponse schema."""

    def test_valid_response(self):
        """Test valid health response."""
        response = HealthResponse(
            status="ok",
            database="healthy",
            version="1.0.0",
            stats={"documents": 10, "chunks": 100}
        )
        assert response.status == "ok"
        assert response.database == "healthy"
        assert response.stats["documents"] == 10
