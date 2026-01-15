"""Vector search engine using pgvector."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Chunk, Document
from src.ingestion.embedder import Embedder


@dataclass
class SearchResult:
    """A search result with relevance score."""

    chunk_id: UUID
    document_id: UUID
    document_name: str
    content: str
    score: float 
    chunk_index: int
    page_number: int | None
    metadata: dict


class SearchEngine:
    """
    Vector search engine using pgvector cosine similarity.

    Performs semantic search over document chunks.
    """

    def __init__(self):
        """Initialize search engine with embedder."""
        self.embedder = Embedder()

    async def search(
        self,
        db: AsyncSession,
        query: str,
        k: int = 5,
        collection: str | None = None,
        document_ids: list[UUID] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """
        Search for relevant chunks using vector similarity.

        Args:
            db: Database session
            query: Search query text
            k: Number of results to return
            collection: Optional collection to filter by
            document_ids: Optional list of document IDs to filter
            min_score: Minimum similarity score threshold

        Returns:
            List of SearchResult objects sorted by relevance
        """
        query_embedding = await self.embedder.embed(query)
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        filters = ["c.embedding IS NOT NULL"]
        params = {
            "embedding": embedding_str,
            "min_score": min_score,
            "k": k,
        }

        if collection:
            filters.append("LOWER(d.collection) = LOWER(:collection)")
            params["collection"] = collection

        if document_ids:
            doc_id_params = []
            for i, doc_id in enumerate(document_ids):
                param_name = f"doc_id_{i}"
                doc_id_params.append(f":{param_name}")
                params[param_name] = str(doc_id)
            filters.append(f"c.document_id IN ({','.join(doc_id_params)})")

        filter_clause = " AND ".join(filters)

        sql = text(
            f"""
            SELECT 
                c.id as chunk_id,
                c.document_id,
                d.name as document_name,
                c.content,
                1 - (c.embedding <=> :embedding::vector) as score,
                c.chunk_index,
                c.page_number,
                c.metadata
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE {filter_clause}
            AND 1 - (c.embedding <=> :embedding::vector) >= :min_score
            ORDER BY c.embedding <=> :embedding::vector
            LIMIT :k
        """
        )

        result = await db.execute(sql, params)
        rows = result.fetchall()

        return [
            SearchResult(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                document_name=row.document_name,
                content=row.content,
                score=float(row.score),
                chunk_index=row.chunk_index,
                page_number=row.page_number,
                metadata=row.metadata or {},
            )
            for row in rows
        ]

    async def search_by_document(
        self,
        db: AsyncSession,
        query: str,
        document_id: UUID,
        k: int = 5,
    ) -> list[SearchResult]:
        """Search within a specific document."""
        return await self.search(
            db=db,
            query=query,
            k=k,
            document_ids=[document_id],
        )

    async def get_context(
        self,
        db: AsyncSession,
        query: str,
        k: int = 5,
        collection: str | None = None,
        max_tokens: int = 4000,
    ) -> str:
        """
        Get formatted context string for LLM consumption.

        Args:
            db: Database session
            query: Search query
            k: Number of chunks to retrieve
            collection: Optional collection to filter by
            max_tokens: Approximate max tokens in output

        Returns:
            Formatted context string
        """
        results = await self.search(db, query, k=k, collection=collection)

        if not results:
            return "No relevant context found."

        context_parts = []
        total_chars = 0
        char_limit = max_tokens * 4 

        for result in results:
            chunk_text = f"[Source: {result.document_name}"
            if result.page_number:
                chunk_text += f", Page {result.page_number}"
            chunk_text += f"]\n{result.content}\n"

            if total_chars + len(chunk_text) > char_limit:
                break

            context_parts.append(chunk_text)
            total_chars += len(chunk_text)

        return "\n---\n".join(context_parts)
