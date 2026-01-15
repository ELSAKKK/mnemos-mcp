"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentBase(BaseModel):
    """Base document schema."""

    name: str
    file_type: str


class DocumentCreate(BaseModel):
    """Schema for document creation (via file upload)."""

    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    """Document response schema."""

    id: UUID
    name: str
    source_path: str
    file_type: str
    file_size: int | None
    chunk_count: int
    collection: str
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="doc_metadata"
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """Response for listing documents."""

    documents: list[DocumentResponse]
    total: int


class SearchRequest(BaseModel):
    """Search request schema."""

    query: str = Field(..., min_length=1, description="Search query text")
    k: int = Field(default=5, ge=1, le=20, description="Number of results")
    collection: str | None = Field(
        default=None, description="Filter to a specific collection"
    )
    document_ids: list[UUID] | None = Field(
        default=None, description="Filter to specific documents"
    )
    min_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum similarity score"
    )


class SearchResultItem(BaseModel):
    """Single search result."""

    chunk_id: UUID
    document_id: UUID
    document_name: str
    content: str
    score: float
    chunk_index: int
    page_number: int | None
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    """Search response schema."""

    query: str
    results: list[SearchResultItem]
    total: int


class ContextRequest(BaseModel):
    """Request for formatted context."""

    query: str = Field(..., min_length=1)
    k: int = Field(default=5, ge=1, le=20)
    max_tokens: int = Field(default=4000, ge=100, le=16000)


class ContextResponse(BaseModel):
    """Formatted context response."""

    query: str
    context: str
    sources: list[str]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: str
    version: str
    stats: dict[str, int] = Field(default_factory=dict)


class URLIngestRequest(BaseModel):
    """Request to ingest a single URL."""

    url: str = Field(..., description="URL to ingest")
    collection: str = Field(default="default", description="Collection name")


class SiteCrawlRequest(BaseModel):
    """Request to crawl a documentation site."""

    url: str = Field(..., description="Base URL of the documentation site")
    collection: str = Field(default="default", description="Collection name")
    path_filter: str | None = Field(
        default=None, description="Path prefix to filter URLs (e.g., '/docs/')"
    )
    max_pages: int = Field(
        default=50, ge=1, le=200, description="Maximum number of pages to crawl"
    )
    max_depth: int = Field(
        default=3, ge=1, le=5, description="Maximum depth for recursive crawling"
    )


class CrawlResponse(BaseModel):
    """Response from URL/site crawl."""

    documents_created: int
    base_url: str
    errors: list[str] = Field(default_factory=list)
