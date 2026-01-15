"""Tests for the DocumentParser class."""

import tempfile
from pathlib import Path

import pytest
from src.ingestion.parser import DocumentParser, ParsedDocument


class TestDocumentParser:
    """Unit tests for DocumentParser."""

    def test_supported_extensions(self):
        """Test that all expected extensions are supported."""
        parser = DocumentParser()
        expected = {".pdf", ".md", ".markdown", ".txt", ".text", ".html", ".htm", ".rst", ".docx"}
        assert parser.SUPPORTED_EXTENSIONS == expected

    def test_parse_text_file(self):
        """Test parsing a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("This is test content.\nWith multiple lines.")
            f.flush()
            temp_path = Path(f.name)

        try:
            parser = DocumentParser()
            result = parser.parse(temp_path)

            assert isinstance(result, ParsedDocument)
            assert result.file_type == "txt"
            assert "test content" in result.content
            assert result.file_name == temp_path.name
            assert result.file_size > 0
        finally:
            temp_path.unlink()

    def test_parse_markdown_file(self):
        """Test parsing a markdown file."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
            f.write("# Heading\n\nThis is **bold** text.")
            f.flush()
            temp_path = Path(f.name)

        try:
            parser = DocumentParser()
            result = parser.parse(temp_path)

            assert result.file_type == "md"
            assert "# Heading" in result.content
            assert "**bold**" in result.content
        finally:
            temp_path.unlink()

    def test_parse_html_file(self):
        """Test parsing an HTML file."""
        html_content = """
        <html>
        <head><title>Test</title></head>
        <body>
            <nav>Navigation</nav>
            <main>
                <h1>Main Content</h1>
                <p>This is the body text.</p>
            </main>
            <footer>Footer</footer>
        </body>
        </html>
        """
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            f.write(html_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            parser = DocumentParser()
            result = parser.parse(temp_path)

            assert result.file_type == "html"
            assert "Main Content" in result.content
            assert "body text" in result.content
        finally:
            temp_path.unlink()

    def test_parse_file_not_found(self):
        """Test that FileNotFoundError is raised for missing files."""
        parser = DocumentParser()
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/path/file.txt")

    def test_parse_unsupported_extension(self):
        """Test that ValueError is raised for unsupported file types."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"test")
            temp_path = Path(f.name)

        try:
            parser = DocumentParser()
            with pytest.raises(ValueError, match="Unsupported file type"):
                parser.parse(temp_path)
        finally:
            temp_path.unlink()

    def test_parsed_document_fields(self):
        """Test that ParsedDocument has all expected fields."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("Test content")
            f.flush()
            temp_path = Path(f.name)

        try:
            parser = DocumentParser()
            result = parser.parse(temp_path)

            assert hasattr(result, "content")
            assert hasattr(result, "file_type")
            assert hasattr(result, "file_name")
            assert hasattr(result, "file_path")
            assert hasattr(result, "file_size")
            assert hasattr(result, "page_count")
            assert hasattr(result, "pages")
            assert hasattr(result, "url")
        finally:
            temp_path.unlink()

    def test_parse_empty_file(self):
        """Test parsing an empty file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("")
            f.flush()
            temp_path = Path(f.name)

        try:
            parser = DocumentParser()
            result = parser.parse(temp_path)

            assert result.content == ""
            assert result.file_size == 0
        finally:
            temp_path.unlink()

    def test_parse_utf8_content(self):
        """Test parsing files with UTF-8 characters."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
            f.write("Unicode: 你好世界 🎉 привет")
            f.flush()
            temp_path = Path(f.name)

        try:
            parser = DocumentParser()
            result = parser.parse(temp_path)

            assert "你好世界" in result.content
            assert "🎉" in result.content
            assert "привет" in result.content
        finally:
            temp_path.unlink()
