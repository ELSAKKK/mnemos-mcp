"""
Mnemos: Local MCP-Compatible Knowledge Server

FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src import __version__
from src.api import router as api_router
from src.config import get_settings
from src.database.connection import get_db
from src.mcp import MCPHandler

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    from src.database.connection import init_db

    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info(f"Mnemos v{__version__} starting...")

    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

    logger.info(f"UI available at: http://{settings.host}:{settings.port}")
    yield
    logger.info("Mnemos shutting down...")


app = FastAPI(
    title="Mnemos",
    description=(
        "Local MCP-Compatible Knowledge Server. "
        "A self-hosted context provider for developer documentation."
    ),
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class MCPToolsListResponse(BaseModel):
    """Response for listing MCP tools."""

    tools: list[dict[str, Any]]


class MCPToolCallRequest(BaseModel):
    """Request to call an MCP tool."""

    name: str
    arguments: dict[str, Any] = {}


class MCPToolCallResponse(BaseModel):
    """Response from MCP tool call."""

    content: list[dict[str, Any]]
    isError: bool = False


@app.get("/mcp/tools", response_model=MCPToolsListResponse, tags=["MCP"])
async def list_mcp_tools():
    """List available MCP tools."""
    tools = MCPHandler.get_tools()
    return MCPToolsListResponse(tools=[t.model_dump() for t in tools])


@app.post("/mcp/call", response_model=MCPToolCallResponse, tags=["MCP"])
async def call_mcp_tool(
    request: MCPToolCallRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute an MCP tool call."""
    result = await MCPHandler.handle_tool_call(
        db=db,
        tool_name=request.name,
        arguments=request.arguments,
    )
    return MCPToolCallResponse(
        content=result.content,
        isError=result.isError,
    )


@app.get("/", include_in_schema=False)
async def root():
    """Serve the frontend UI."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return RedirectResponse(url="/api/docs")


@app.get("/api", tags=["Info"])
async def api_info():
    """API information endpoint."""
    return {
        "name": "Mnemos",
        "version": __version__,
        "description": "Local MCP-Compatible Knowledge Server",
        "docs": "/api/docs",
        "mcp_tools": "/mcp/tools",
    }


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )