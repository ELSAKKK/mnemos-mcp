"""Tests for the TextChunker class."""

import pytest
from src.ingestion.chunker import TextChunker, TextChunk


class TestTextChunker:
    """Unit tests for TextChunker."""

    def test_init_default_values(self):
        """Test chunker initializes with default settings."""
        chunker = TextChunker()
        assert chunker.chunk_size > 0
        assert chunker.chunk_overlap > 0
        assert chunker.min_chunk_length > 0

    def test_init_custom_values(self):
        """Test chunker accepts custom chunk size and overlap."""
        chunker = TextChunker(chunk_size=500, chunk_overlap=50)
        assert chunker.chunk_size == 500
        assert chunker.chunk_overlap == 50

    def test_chunk_text_basic(self):
        """Test basic text chunking."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        text = "This is a test paragraph. " * 20
        chunks = chunker.chunk_text(text)

        assert len(chunks) > 0
        assert all(isinstance(c, TextChunk) for c in chunks)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert len(chunk.content) >= chunker.min_chunk_length

    def test_chunk_text_filters_short_content(self):
        """Test that chunks shorter than min_chunk_length are filtered."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        text = "Hi"
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 0

    def test_chunk_text_filters_non_alphanumeric(self):
        """Test that chunks without alphanumeric content are filtered."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        text = "---- ****" * 20
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 0

    def test_chunk_text_preserves_markdown_headers(self):
        """Test that markdown headers influence chunk boundaries."""
        chunker = TextChunker(chunk_size=200, chunk_overlap=20)
        text = """
# Header One

This is the first section with some content.

## Header Two

This is the second section with different content.
"""
        chunks = chunker.chunk_text(text)

        assert len(chunks) > 0
        all_content = " ".join(c.content for c in chunks)
        assert "Header" in all_content

    def test_chunk_pages_basic(self):
        """Test page-based chunking."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        pages = [
            {"page_num": 1, "content": "First page content. " * 10},
            {"page_num": 2, "content": "Second page content. " * 10},
        ]
        chunks = chunker.chunk_pages(pages)

        assert len(chunks) > 0
        page_numbers = set(c.page_number for c in chunks if c.page_number)
        assert 1 in page_numbers or 2 in page_numbers

    def test_chunk_pages_global_index(self):
        """Test that chunk_index is global across pages."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        pages = [
            {"page_num": 1, "content": "First page content. " * 10},
            {"page_num": 2, "content": "Second page content. " * 10},
        ]
        chunks = chunker.chunk_pages(pages)

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunk_text_metadata_passed(self):
        """Test that metadata is passed to chunks."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        text = "This is a test paragraph. " * 10
        metadata = {"source": "test", "author": "tester"}
        chunks = chunker.chunk_text(text, metadata=metadata)

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.metadata == metadata

    def test_text_chunk_token_count(self):
        """Test TextChunk token count property."""
        chunk = TextChunk(
            content="a" * 100,
            chunk_index=0,
            char_count=100,
        )
        assert chunk.token_count == 25

    def test_empty_text(self):
        """Test handling of empty text."""
        chunker = TextChunker()
        chunks = chunker.chunk_text("")
        assert chunks == []

    def test_whitespace_only_text(self):
        """Test handling of whitespace-only text."""
        chunker = TextChunker()
        chunks = chunker.chunk_text("   \n\n   \t   ")
        assert chunks == []
