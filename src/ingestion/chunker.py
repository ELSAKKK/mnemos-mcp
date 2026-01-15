"""Text chunking for document processing."""

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import get_settings


@dataclass
class TextChunk:
    """A chunk of text with metadata."""

    content: str
    chunk_index: int
    char_count: int
    page_number: int | None = None
    metadata: dict | None = None

    @property
    def token_count(self) -> int:
        """Approximate token count (characters / 4)."""
        return self.char_count // 4


class TextChunker:
    """
    Text chunker using recursive character splitting.

    Splits text into chunks of approximately equal size
    while preserving sentence boundaries where possible.
    """

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        """
        Initialize the chunker.

        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks in characters
        """
        self._settings = get_settings()
        self.chunk_size = chunk_size or (self._settings.chunk_size * 4)
        self.chunk_overlap = chunk_overlap or (self._settings.chunk_overlap * 4)
        self.min_chunk_length = self._settings.min_chunk_length

        markdown_separators = [
            "\n# ",
            "\n## ",
            "\n### ",
            "\n#### ",
            "\n##### ",
            "\n###### ",
            "# ",
            "## ",
            "### ",
            "#### ",
            "\n```",
            "```",
            "\n\n",
            "\n",
            ". ",
            "! ",
            "? ",
            "; ",
            ": ",
            " ",
            "",
        ]

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=markdown_separators,
            length_function=len,
        )

    def chunk_text(
        self,
        text: str,
        metadata: dict | None = None,
    ) -> list[TextChunk]:
        """
        Split text into chunks with quality filtering.
        """
        raw_chunks = self._splitter.split_text(text)

        chunks = []
        for content in raw_chunks:
            content = content.strip()

            if len(content) < self.min_chunk_length or not any(c.isalnum() for c in content):
                continue

            chunks.append(
                TextChunk(
                    content=content,
                    chunk_index=len(chunks),
                    char_count=len(content),
                    metadata=metadata,
                )
            )

        return chunks

    def chunk_pages(
        self,
        pages: list[dict],
        metadata: dict | None = None,
    ) -> list[TextChunk]:
        """
        Split pages into chunks, preserving page number information with quality filtering.
        """
        all_chunks = []
        global_chunk_index = 0

        for page in pages:
            page_num = page["page_num"]
            page_content = page["content"]

            raw_chunks = self._splitter.split_text(page_content)

            for content in raw_chunks:
                content = content.strip()

                if len(content) < self.min_chunk_length or not any(c.isalnum() for c in content):
                    continue

                all_chunks.append(
                    TextChunk(
                        content=content,
                        chunk_index=global_chunk_index,
                        char_count=len(content),
                        page_number=page_num,
                        metadata=metadata,
                    )
                )
                global_chunk_index += 1

        return all_chunks