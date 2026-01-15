"""Document parser for multiple formats including PDF, Markdown, HTML, RST, DOCX, and text files."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fitz

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import docx2txt

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from docutils.core import publish_parts

    HAS_RST = True
except ImportError:
    HAS_RST = False

FileType = Literal["pdf", "md", "txt", "html", "rst", "docx", "url"]


@dataclass
class ParsedDocument:
    """Parsed document with content and metadata."""

    content: str
    file_type: FileType
    file_name: str
    file_path: str
    file_size: int
    page_count: int | None = None
    pages: list[dict] | None = None
    url: str | None = None


class DocumentParser:
    """Parser for various document formats."""

    SUPPORTED_EXTENSIONS = {
        ".pdf",
        ".md",
        ".markdown",
        ".txt",
        ".text",
        ".html",
        ".htm",
        ".rst",
        ".docx",
    }

    def parse(self, file_path: str | Path) -> ParsedDocument:
        """
        Parse a document file and extract its content.

        Args:
            file_path: Path to the document file

        Returns:
            ParsedDocument with extracted content and metadata

        Raises:
            ValueError: If file type is not supported
            FileNotFoundError: If file does not exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {extension}. "
                f"Supported: {self.SUPPORTED_EXTENSIONS}"
            )

        file_size = path.stat().st_size
        file_name = path.name

        if extension == ".pdf":
            return self._parse_pdf(path, file_name, file_size)
        elif extension in {".md", ".markdown"}:
            return self._parse_markdown(path, file_name, file_size)
        elif extension in {".html", ".htm"}:
            return self._parse_html(path, file_name, file_size)
        elif extension == ".rst":
            return self._parse_rst(path, file_name, file_size)
        elif extension == ".docx":
            return self._parse_docx(path, file_name, file_size)
        else:
            return self._parse_text(path, file_name, file_size)

    def _parse_pdf(self, path: Path, file_name: str, file_size: int) -> ParsedDocument:
        """Parse PDF file using PyMuPDF."""
        pages = []
        all_content = []

        with fitz.open(path) as doc:
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text")
                if text.strip():
                    pages.append({"page_num": page_num, "content": text})
                    all_content.append(text)

        return ParsedDocument(
            content="\n\n".join(all_content),
            file_type="pdf",
            file_name=file_name,
            file_path=str(path.absolute()),
            file_size=file_size,
            page_count=len(pages),
            pages=pages,
        )

    def _parse_markdown(
        self, path: Path, file_name: str, file_size: int
    ) -> ParsedDocument:
        """Parse Markdown file."""
        content = path.read_text(encoding="utf-8")

        return ParsedDocument(
            content=content,
            file_type="md",
            file_name=file_name,
            file_path=str(path.absolute()),
            file_size=file_size,
        )

    def _parse_html(self, path: Path, file_name: str, file_size: int) -> ParsedDocument:
        """Parse HTML file, extracting readable text content."""
        if not HAS_BS4:
            raise ImportError(
                "beautifulsoup4 is required for HTML parsing. Install with: pip install beautifulsoup4 lxml"
            )

        html_content = path.read_text(encoding="utf-8")
        content = self._extract_text_from_html(html_content)

        return ParsedDocument(
            content=content,
            file_type="html",
            file_name=file_name,
            file_path=str(path.absolute()),
            file_size=file_size,
        )

    def _extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML content."""
        soup = BeautifulSoup(html, "lxml")

        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        text = soup.get_text(separator="\n")

        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text

    def _parse_rst(self, path: Path, file_name: str, file_size: int) -> ParsedDocument:
        """Parse reStructuredText file."""
        if not HAS_RST:
            raise ImportError(
                "docutils is required for RST parsing. Install with: pip install docutils"
            )

        rst_content = path.read_text(encoding="utf-8")

        try:
            parts = publish_parts(rst_content, writer_name="html")
            html_body = parts["html_body"]
            content = self._extract_text_from_html(html_body)
        except Exception:
            content = rst_content

        return ParsedDocument(
            content=content,
            file_type="rst",
            file_name=file_name,
            file_path=str(path.absolute()),
            file_size=file_size,
        )

    def _parse_docx(self, path: Path, file_name: str, file_size: int) -> ParsedDocument:
        """Parse Word document (.docx)."""
        if not HAS_DOCX:
            raise ImportError(
                "docx2txt is required for DOCX parsing. Install with: pip install docx2txt"
            )

        content = docx2txt.process(str(path))

        return ParsedDocument(
            content=content,
            file_type="docx",
            file_name=file_name,
            file_path=str(path.absolute()),
            file_size=file_size,
        )

    def _parse_text(self, path: Path, file_name: str, file_size: int) -> ParsedDocument:
        """Parse plain text file."""
        content = path.read_text(encoding="utf-8")

        return ParsedDocument(
            content=content,
            file_type="txt",
            file_name=file_name,
            file_path=str(path.absolute()),
            file_size=file_size,
        )
