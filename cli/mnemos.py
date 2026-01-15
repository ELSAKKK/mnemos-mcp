#!/usr/bin/env python3
"""
Mnemos CLI - Command-line interface for the knowledge server.

Usage:
    mnemos add <file>           Add a document to the knowledge base
    mnemos add <dir> --recursive  Add all documents in a directory
    mnemos search <query>       Search for relevant context
    mnemos list                 List all documents
    mnemos delete <id>          Delete a document
    mnemos server               Start the API server
"""

import asyncio
import os
import sys
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.database.connection import async_session_maker
from src.database.models import Chunk, Document
from src.ingestion import DocumentParser, Embedder, TextChunker
from src.retrieval import SearchEngine

app = typer.Typer(
    name="mnemos",
    help="Mnemos - Local MCP Compatible Knowledge Server",
    add_completion=False,
)
console = Console()


def run_async(coro):
    """Run async function in sync context."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        return asyncio.get_event_loop().run_until_complete(coro)


@app.command()
def add(
    path: str = typer.Argument(..., help="Path to file or directory"),
    collection: str = typer.Option(
        "default", "--collection", "-c", help="Collection name"
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-r", help="Recursively add files from directory"
    ),
):
    """Add a document or directory to the knowledge base."""
    target = Path(path)

    if not target.exists():
        console.print(f"[red]Error:[/red] Path not found: {path}")
        raise typer.Exit(1)

    async def _add_document(file_path: Path):
        """Add a single document."""
        with open(file_path, "rb") as f:
            content = f.read()
        content_hash = hashlib.sha256(content).hexdigest()

        async with async_session_maker() as db:
            from sqlalchemy import select
            stmt = select(Document).where(
                Document.name == file_path.name, Document.collection == collection
            )
            result = await db.execute(stmt)
            existing_doc = result.scalar_one_or_none()

            if existing_doc:
                if existing_doc.content_hash == content_hash:
                    return existing_doc.id, existing_doc.chunk_count, True
                else:
                    await db.delete(existing_doc)
                    await db.flush()

            parser = DocumentParser()
            parsed = parser.parse(file_path)

            document = Document(
                name=file_path.name,
                source_path=str(file_path.absolute()),
                file_type=parsed.file_type,
                file_size=parsed.file_size,
                collection=collection,
                content_hash=content_hash,
                doc_metadata=(
                    {"page_count": parsed.page_count} if parsed.page_count else {}
                ),
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
                )
                db.add(db_chunk)

            document.chunk_count = len(chunks)
            await db.commit()

            return document.id, len(chunks), False

    if target.is_file():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Processing {target.name}...", total=None)
            doc_id, chunk_count, skipped = run_async(_add_document(target))
            progress.update(task, completed=True)

        if skipped:
            console.print(
                f"[yellow]![/yellow] [bold]{target.name}[/bold] is unchanged, skipping."
            )
        else:
            console.print(
                Panel(
                    f"[green]✓[/green] Added [bold]{target.name}[/bold]\n"
                    f"  ID: {doc_id}\n"
                    f"  Collection: {collection}\n"
                    f"  Chunks: {chunk_count}",
                    title="Document Added",
                )
            )

    elif target.is_dir():
        parser = DocumentParser()
        files = list(target.glob("**/*" if recursive else "*"))
        supported = [
            f
            for f in files
            if f.is_file() and f.suffix.lower() in parser.SUPPORTED_EXTENSIONS
        ]

        if not supported:
            console.print(f"[yellow]No supported files found in {path}[/yellow]")
            raise typer.Exit(0)

        console.print(f"Found {len(supported)} supported files")

        added = 0
        skipped = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            for file_path in supported:
                task = progress.add_task(f"Processing {file_path.name}...", total=None)
                try:
                    _, _, was_skipped = run_async(_add_document(file_path))
                    if was_skipped:
                        skipped += 1
                    else:
                        added += 1
                    progress.update(task, completed=True)
                except Exception as e:
                    console.print(f"[red]Error processing {file_path.name}:[/red] {e}")
                    progress.remove_task(task)

        msg = f"\n[green]✓[/green] Added {added} documents"
        if skipped:
            msg += f" ([yellow]{skipped} skipped[/yellow])"
        console.print(msg)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    collection: Optional[str] = typer.Option(
        None, "--collection", "-c", help="Filter by collection"
    ),
    k: int = typer.Option(5, "--top", "-k", help="Number of results"),
):
    """Search the knowledge base for relevant context."""

    async def _search():
        engine = SearchEngine()
        async with async_session_maker() as db:
            return await engine.search(db=db, query=query, k=k, collection=collection)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching...", total=None)
        results = run_async(_search())
        progress.update(task, completed=True)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print(f"\n[bold]Results for:[/bold] {query}\n")

    for i, result in enumerate(results, 1):
        source = f"{result.document_name}"
        if result.page_number:
            source += f", p.{result.page_number}"

        panel = Panel(
            result.content[:500] + ("..." if len(result.content) > 500 else ""),
            title=f"[{i}] {source} (score: {result.score:.3f})",
            border_style="blue",
        )
        console.print(panel)
        console.print()


@app.command("list")
def list_docs(
    collection: Optional[str] = typer.Option(
        None, "--collection", "-c", help="Filter by collection"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of documents to show"),
):
    """List all documents in the knowledge base."""
    from sqlalchemy import select

    async def _list():
        async with async_session_maker() as db:
            stmt = select(Document).order_by(Document.created_at.desc()).limit(limit)
            if collection:
                stmt = stmt.where(Document.collection == collection)
            result = await db.execute(stmt)
            return result.scalars().all()

    documents = run_async(_list())

    if not documents:
        console.print("[yellow]No documents in the knowledge base.[/yellow]")
        return

    table = Table(title="Documents")
    table.add_column("Name", style="cyan")
    table.add_column("Collection", style="magenta")
    table.add_column("Type", style="green")
    table.add_column("Chunks", justify="right")
    table.add_column("Created", style="dim")
    table.add_column("ID", style="dim")

    for doc in documents:
        table.add_row(
            doc.name[:40] + ("..." if len(doc.name) > 40 else ""),
            doc.collection,
            doc.file_type,
            str(doc.chunk_count),
            doc.created_at.strftime("%Y-%m-%d %H:%M"),
            str(doc.id)[:8] + "...",
        )

    console.print(table)


@app.command()
def delete(
    document_id: str = typer.Argument(..., help="Document ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a document from the knowledge base."""
    from sqlalchemy import select

    async def _delete():
        async with async_session_maker() as db:
            result = await db.execute(
                select(Document).where(Document.id == UUID(document_id))
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return None

            name = doc.name
            await db.delete(doc)
            await db.commit()
            return name

    if not force:
        confirm = typer.confirm(f"Delete document {document_id}?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    name = run_async(_delete())

    if name:
        console.print(f"[green]✓[/green] Deleted [bold]{name}[/bold]")
    else:
        console.print(f"[red]Document not found:[/red] {document_id}")
        raise typer.Exit(1)


@app.command()
def server(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """Start the API server."""
    import uvicorn

    console.print(
        Panel(
            f"[bold] Mnemos Server[/bold]\n\n"
            f"API: http://{host}:{port}\n"
            f"Docs: http://{host}:{port}/docs\n"
            f"MCP Tools: http://{host}:{port}/mcp/tools",
            title="Starting Server",
        )
    )

    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def export(
    output: str = typer.Argument("mnemos_export.json", help="Output JSON file"),
    collection: Optional[str] = typer.Option(
        None, "--collection", "-c", help="Export specific collection only"
    ),
):
    """Export the knowledge base for backup."""
    from sqlalchemy.orm import selectinload

    async def _export():
        async with async_session_maker() as db:
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

    console.print(f"Exporting knowledge base to {output}...")
    data = run_async(_export())

    with open(output, "w") as f:
        json.dump(data, f, indent=2)

    console.print(f"[green]✓[/green] Exported {len(data)} documents to {output}")


@app.callback()
def main():
    """Mnemos - Local MCP-Compatible Knowledge Server"""
    pass


if __name__ == "__main__":
    app()
