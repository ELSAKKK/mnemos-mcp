"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database (create tables if needed and handle basic migrations)."""
    from sqlalchemy import text
    from src.database.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(
            text(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS collection VARCHAR(50) DEFAULT 'default'"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_documents_collection ON documents (collection)"
            )
        )

        await conn.execute(
            text(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)"
            )
        )
