"""
MCP (Model Context Protocol) handlers.

Implements the MCP specification for tool exposure to LLM clients.
See: https://modelcontextprotocol.io/
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


class MCPToolDefinition(BaseModel):
    """MCP tool definition."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class MCPToolResult(BaseModel):
    """MCP tool execution result."""

    content: list[dict[str, Any]]
    isError: bool = False


class MCPHandler:
    """
    Handler for MCP protocol operations.

    Exposes document search and management as MCP tools.
    """

    @staticmethod
    def get_tools() -> list[MCPToolDefinition]:
        """Return list of available MCP tools."""
        return [
            MCPToolDefinition(
                name="search_context",
                description=(
                    "Search the knowledge base for relevant context. "
                    "Returns the most relevant document chunks for a given query."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to find relevant context",
                        },
                        "k": {
                            "type": "integer",
                            "description": "Number of results to return (default: 5)",
                            "default": 5,
                        },
                        "collection": {
                            "type": "string",
                            "description": "Optional collection to search in",
                        },
                    },
                    "required": ["query"],
                },
            ),
            MCPToolDefinition(
                name="list_documents",
                description="List all documents in the knowledge base.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of documents to return",
                            "default": 100,
                        },
                        "collection": {
                            "type": "string",
                            "description": "Optional collection to filter by",
                        },
                    },
                },
            ),
            MCPToolDefinition(
                name="get_document_info",
                description="Get detailed information about a specific document.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "The UUID of the document",
                        },
                    },
                    "required": ["document_id"],
                },
            ),
        ]

    @staticmethod
    async def handle_tool_call(
        db: AsyncSession,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        """
        Handle an MCP tool call.

        Args:
            db: Database session
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            MCPToolResult with the execution result
        """
        from sqlalchemy import func, select

        from src.database.models import Document
        from src.retrieval import SearchEngine

        try:
            if tool_name == "search_context":
                query = arguments.get("query", "")
                k = arguments.get("k", 5)
                collection = arguments.get("collection")

                engine = SearchEngine()
                results = await engine.search(
                    db=db, query=query, k=k, collection=collection
                )

                if not results:
                    return MCPToolResult(
                        content=[
                            {
                                "type": "text",
                                "text": "No relevant context found for your query.",
                            }
                        ]
                    )

                content = []
                for i, result in enumerate(results, 1):
                    source_info = f"Source: {result.document_name}"
                    if result.page_number:
                        source_info += f", Page {result.page_number}"

                    content.append(
                        {
                            "type": "text",
                            "text": f"[{i}] {source_info}\nScore: {result.score:.3f}\n\n{result.content}",
                        }
                    )

                return MCPToolResult(content=content)

            elif tool_name == "list_documents":
                limit = arguments.get("limit", 100)
                collection = arguments.get("collection")

                stmt = (
                    select(Document).order_by(Document.created_at.desc()).limit(limit)
                )
                if collection:
                    stmt = stmt.where(Document.collection == collection)

                result = await db.execute(stmt)
                documents = result.scalars().all()

                if not documents:
                    return MCPToolResult(
                        content=[
                            {
                                "type": "text",
                                "text": "No documents in the knowledge base.",
                            }
                        ]
                    )

                doc_list = []
                for doc in documents:
                    doc_list.append(
                        f"• {doc.name} (ID: {doc.id})\n"
                        f"  Type: {doc.file_type}, Chunks: {doc.chunk_count}, "
                        f"Created: {doc.created_at.strftime('%Y-%m-%d %H:%M')}"
                    )

                return MCPToolResult(
                    content=[
                        {
                            "type": "text",
                            "text": f"Documents ({len(documents)}):\n\n"
                            + "\n\n".join(doc_list),
                        }
                    ]
                )

            elif tool_name == "get_document_info":
                doc_id = arguments.get("document_id")
                if not doc_id:
                    return MCPToolResult(
                        content=[
                            {"type": "text", "text": "Error: document_id is required"}
                        ],
                        isError=True,
                    )

                result = await db.execute(
                    select(Document).where(Document.id == UUID(doc_id))
                )
                doc = result.scalar_one_or_none()

                if not doc:
                    return MCPToolResult(
                        content=[
                            {"type": "text", "text": f"Document not found: {doc_id}"}
                        ],
                        isError=True,
                    )

                info = (
                    f"Document: {doc.name}\n"
                    f"ID: {doc.id}\n"
                    f"Type: {doc.file_type}\n"
                    f"Size: {doc.file_size or 'unknown'} bytes\n"
                    f"Chunks: {doc.chunk_count}\n"
                    f"Created: {doc.created_at}\n"
                    f"Source: {doc.source_path}"
                )

                return MCPToolResult(content=[{"type": "text", "text": info}])

            else:
                return MCPToolResult(
                    content=[{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    isError=True,
                )

        except Exception as e:
            return MCPToolResult(
                content=[
                    {"type": "text", "text": f"Error executing {tool_name}: {str(e)}"}
                ],
                isError=True,
            )
