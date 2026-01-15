"""API routes for document management and search."""

import os
import tempfile
import hashlib
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import __version__
from src.api.schemas import (
    ContextRequest,
    ContextResponse,
    CrawlResponse,
    DocumentListResponse,
    DocumentResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SiteCrawlRequest,
    URLIngestRequest,
)
from src.database.connection import get_db
from src.database.models import Chunk, Document
from src.ingestion import DocumentParser, Embedder, TextChunker, URLCrawler
from src.retrieval import SearchEngine

router = APIRouter()


@router.get(
    "/collections",
    response_model=list[str],
    tags=["Documents"],
)
async def list_collections(
    db: AsyncSession = Depends(get_db),
):
    """List all unique collection names."""
    stmt = select(Document.collection).distinct()
    result = await db.execute(stmt)
    collections = result.scalars().all()
    return list(collections)


@router.get(
    "/documents/export",
    tags=["Documents"],
)
async def export_documents(
    collection: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Export all documents and chunks as JSON."""
    from sqlalchemy.orm import selectinload

    stmt = select(Document).options(selectinload(Document.chunks))
    if collection:
        stmt = stmt.where(Document.collection == collection)

    result = await db.execute(stmt)
    docs = result.scalars().all()

    export_data = []
    for doc in docs:
        doc_dict = {
            "id": str(doc.id),
            "name": doc.name,
            "collection": doc.collection,
            "file_type": doc.file_type,
            "source_path": doc.source_path,
            "content_hash": doc.content_hash,
            "metadata": doc.doc_metadata,
            "created_at": doc.created_at.isoformat(),
            "chunks": [
                {
                    "content": chunk.content,
                    "index": chunk.chunk_index,
                    "page": chunk.page_number,
                    "tokens": chunk.token_count,
                    "metadata": chunk.doc_metadata,
                }
                for chunk in doc.chunks
            ],
        }
        export_data.append(doc_dict)

    return export_data


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check API and database health."""
    try:
        doc_count = await db.execute(select(func.count()).select_from(Document))
        chunk_count = await db.execute(select(func.count()).select_from(Chunk))
        db_status = "healthy"
        stats = {
            "documents": doc_count.scalar() or 0,
            "chunks": chunk_count.scalar() or 0,
        }
    except Exception:
        db_status = "unhealthy"
        stats = {}

    return HealthResponse(
        status="ok" if db_status == "healthy" else "degraded",
        database=db_status,
        version=__version__,
        stats=stats,
    )


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Documents"],
)
async def upload_document(
    file: UploadFile = File(...),
    collection: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and ingest a document.

    Parses the document, chunks the content, generates embeddings,
    and stores everything in the database.
    """
    allowed_extensions = {
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
    file_ext = os.path.splitext(file.filename or "")[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_extensions}",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        content_hash = hashlib.sha256(content).hexdigest()

        existing_doc_stmt = select(Document).where(
            Document.name == (file.filename or "unknown"),
            Document.collection == collection,
        )
        existing_doc_result = await db.execute(existing_doc_stmt)
        existing_doc = existing_doc_result.scalar_one_or_none()

        if existing_doc:
            if existing_doc.content_hash == content_hash:
                return existing_doc
            else:
                await db.delete(existing_doc)
                await db.flush()

        parser = DocumentParser()
        parsed = parser.parse(tmp_path)

        document = Document(
            name=file.filename or "unknown",
            source_path=parsed.file_path,
            file_type=parsed.file_type,
            file_size=parsed.file_size,
            collection=collection,
            content_hash=content_hash,
            doc_metadata={"page_count": parsed.page_count} if parsed.page_count else {},
        )
        db.add(document)
        await db.flush()

        chunker = TextChunker()
        if parsed.pages:
            chunks = chunker.chunk_pages(parsed.pages)
        else:
            chunks = chunker.chunk_text(parsed.content)

        embedder = Embedder()
        texts = [c.content for c in chunks]
        embeddings = await embedder.embed_batch(texts)

        for chunk, embedding in zip(chunks, embeddings):
            db_chunk = Chunk(
                document_id=document.id,
                content=chunk.content,
                embedding=embedding,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                token_count=chunk.token_count,
                doc_metadata=chunk.metadata or {},
            )
            db.add(db_chunk)

        document.chunk_count = len(chunks)
        await db.commit()
        await db.refresh(document)

        return document

    finally:
        os.unlink(tmp_path)


@router.get("/documents", response_model=DocumentListResponse, tags=["Documents"])
async def list_documents(
    collection: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List documents, optionally filtered by collection."""
    count_stmt = select(func.count()).select_from(Document)
    if collection:
        count_stmt = count_stmt.where(Document.collection == collection)

    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    stmt = (
        select(Document).order_by(Document.created_at.desc()).offset(skip).limit(limit)
    )
    if collection:
        stmt = stmt.where(Document.collection == collection)

    result = await db.execute(stmt)
    documents = result.scalars().all()

    return DocumentListResponse(documents=list(documents), total=total)


@router.get(
    "/documents/{document_id}", response_model=DocumentResponse, tags=["Documents"]
)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a document by ID."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found: {document_id}",
        )

    return document


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Documents"],
)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and all its chunks."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found: {document_id}",
        )

    await db.delete(document)
    await db.commit()


@router.post("/search", response_model=SearchResponse, tags=["Search"])
async def search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Search for relevant document chunks.

    Uses vector similarity to find the most relevant chunks
    for the given query.
    """
    engine = SearchEngine()
    results = await engine.search(
        db=db,
        query=request.query,
        k=request.k,
        collection=request.collection,
        document_ids=request.document_ids,
        min_score=request.min_score,
    )

    return SearchResponse(
        query=request.query,
        results=[
            SearchResultItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                document_name=r.document_name,
                content=r.content,
                score=r.score,
                chunk_index=r.chunk_index,
                page_number=r.page_number,
                metadata=r.metadata,
            )
            for r in results
        ],
        total=len(results),
    )


@router.post("/context", response_model=ContextResponse, tags=["Search"])
async def get_context(
    request: ContextRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Get formatted context for LLM consumption.

    Returns a formatted string suitable for including in
    an LLM prompt as context.
    """
    engine = SearchEngine()
    context = await engine.get_context(
        db=db,
        query=request.query,
        k=request.k,
        max_tokens=request.max_tokens,
    )

    sources = []
    for line in context.split("\n"):
        if line.startswith("[Source:"):
            source = line.split("]")[0].replace("[Source: ", "")
            if source not in sources:
                sources.append(source)

    return ContextResponse(
        query=request.query,
        context=context,
        sources=sources,
    )


@router.post(
    "/ingest/url",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ingest"],
)
async def ingest_url(
    request: URLIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest content from a single URL.

    Fetches the page, extracts text content, chunks it,
    generates embeddings, and stores in the database.
    """
    crawler = URLCrawler()

    try:
        parsed = await crawler.crawl_url(request.url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch URL: {str(e)}",
        )

    content_hash = hashlib.sha256(parsed.content.encode()).hexdigest()

    # Check for duplicate
    existing_doc_stmt = select(Document).where(
        Document.source_path == request.url, Document.collection == request.collection
    )
    existing_doc_result = await db.execute(existing_doc_stmt)
    existing_doc = existing_doc_result.scalar_one_or_none()

    if existing_doc:
        if existing_doc.content_hash == content_hash:
            return existing_doc
        else:
            await db.delete(existing_doc)
            await db.flush()

    document = Document(
        name=parsed.file_name,
        source_path=request.url,
        file_type="url",
        file_size=parsed.file_size,
        collection=request.collection,
        content_hash=content_hash,
        doc_metadata={"url": request.url},
    )
    db.add(document)
    await db.flush()

    chunker = TextChunker()
    chunks = chunker.chunk_text(parsed.content)

    embedder = Embedder()
    texts = [c.content for c in chunks]

    if texts:
        embeddings = await embedder.embed_batch(texts)

        for chunk, embedding in zip(chunks, embeddings):
            db_chunk = Chunk(
                document_id=document.id,
                content=chunk.content,
                embedding=embedding,
                chunk_index=chunk.chunk_index,
                page_number=None,
                token_count=chunk.token_count,
                doc_metadata={},
            )
            db.add(db_chunk)

    document.chunk_count = len(chunks)
    await db.commit()
    await db.refresh(document)

    return document


@router.post(
    "/ingest/site",
    response_model=CrawlResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ingest"],
)
async def ingest_site(
    request: SiteCrawlRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Crawl and ingest a documentation site.

    Recursively crawls the site, extracts content from each page,
    and stores all pages in the database.
    """
    crawler = URLCrawler(
        max_pages=request.max_pages,
        max_depth=request.max_depth,
    )

    try:
        result = await crawler.crawl_site(
            base_url=request.url,
            path_filter=request.path_filter,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to crawl site: {str(e)}",
        )

    documents_created = 0
    chunker = TextChunker()
    embedder = Embedder()

    for page in result.pages:
        try:
            content_hash = hashlib.sha256(page.content.encode()).hexdigest()

            source_path = page.url or page.file_path
            existing_doc_stmt = select(Document).where(
                Document.source_path == source_path,
                Document.collection == request.collection,
            )
            existing_doc_result = await db.execute(existing_doc_stmt)
            existing_doc = existing_doc_result.scalar_one_or_none()

            if existing_doc:
                if existing_doc.content_hash == content_hash:
                    continue
                else:
                    await db.delete(existing_doc)
                    await db.flush()

            document = Document(
                name=page.file_name,
                source_path=source_path,
                file_type="url",
                file_size=page.file_size,
                collection=request.collection,
                content_hash=content_hash,
                doc_metadata={"url": page.url, "base_url": request.url},
            )
            db.add(document)
            await db.flush()

            chunks = chunker.chunk_text(page.content)
            texts = [c.content for c in chunks]

            if texts:
                embeddings = await embedder.embed_batch(texts)

                for chunk, embedding in zip(chunks, embeddings):
                    db_chunk = Chunk(
                        document_id=document.id,
                        content=chunk.content,
                        embedding=embedding,
                        chunk_index=chunk.chunk_index,
                        page_number=None,
                        token_count=chunk.token_count,
                        doc_metadata={},
                    )
                    db.add(db_chunk)

            document.chunk_count = len(chunks)
            documents_created += 1

        except Exception as e:
            result.errors.append(f"{page.url}: {str(e)}")

    await db.commit()

    return CrawlResponse(
        documents_created=documents_created,
        base_url=request.url,
        errors=result.errors,
    )
