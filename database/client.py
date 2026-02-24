"""
Database client wrapper for SQLAlchemy ORM.

This module provides a database client for AWS Cost Optimization Tool,
using SQLAlchemy ORM with support for both SQLite and PostgreSQL databases.
Compatible with Roll framework.

Usage:
    from database.client import get_session, get_async_session, engine
    
    # Synchronous usage
    with get_session() as session:
        instances = session.query(RawInstance).all()
    
    # Asynchronous usage
    async with get_async_session() as session:
        result = await session.execute(select(RawInstance))
        instances = result.scalars().all()
"""

import os
from typing import Optional, Generator, AsyncGenerator
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from database.models import Base


class DatabaseConfig:
    """Database configuration from environment variables."""
    
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./data/etl_database.db")
        self.environment = os.getenv("NODE_ENV", os.getenv("ENVIRONMENT", "development"))
        self.is_production = self.environment == "production"
        
        # Ensure data directory exists for SQLite
        if self.is_sqlite and not self.database_url.startswith("sqlite:///:memory:"):
            db_path = self.database_url.replace("sqlite:///", "")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return self.database_url.startswith("sqlite")
    
    @property
    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL database."""
        return self.database_url.startswith("postgresql")
    
    @property
    def async_database_url(self) -> str:
        """Get async-compatible database URL."""
        if self.is_sqlite:
            # Convert sqlite:/// to sqlite+aiosqlite:///
            return self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        elif self.is_postgresql:
            # Convert postgresql:// to postgresql+asyncpg://
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        return self.database_url


# Global configuration instance
config = DatabaseConfig()

# Create synchronous engine with proper connection pooling
_engine_kwargs = {
    "echo": os.getenv("SQL_ECHO", "false").lower() == "true",
}

if config.is_sqlite:
    # SQLite-specific settings
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    _engine_kwargs["poolclass"] = StaticPool
elif config.is_postgresql:
    # PostgreSQL connection pooling to prevent "too many clients" errors
    _engine_kwargs["pool_size"] = 5           # Number of connections to keep in pool
    _engine_kwargs["max_overflow"] = 10       # Additional connections allowed beyond pool_size
    _engine_kwargs["pool_pre_ping"] = True    # Check connection health before using
    _engine_kwargs["pool_recycle"] = 3600     # Recycle connections after 1 hour
    _engine_kwargs["pool_timeout"] = 30       # Timeout for getting connection from pool

engine = create_engine(config.database_url, **_engine_kwargs)

# Create async engine with proper connection pooling
_async_engine_kwargs = {
    "echo": os.getenv("SQL_ECHO", "false").lower() == "true",
}

if config.is_sqlite:
    _async_engine_kwargs["connect_args"] = {"check_same_thread": False}
    _async_engine_kwargs["poolclass"] = StaticPool
elif config.is_postgresql:
    # PostgreSQL connection pooling for async engine
    _async_engine_kwargs["pool_size"] = 5
    _async_engine_kwargs["max_overflow"] = 10
    _async_engine_kwargs["pool_pre_ping"] = True
    _async_engine_kwargs["pool_recycle"] = 3600
    _async_engine_kwargs["pool_timeout"] = 30

async_engine = create_async_engine(config.async_database_url, **_async_engine_kwargs)

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# Enable foreign key constraints for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key constraints for SQLite."""
    if config.is_sqlite:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def drop_db():
    """Drop all database tables."""
    Base.metadata.drop_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Get a database session.
    
    Yields:
        Session: SQLAlchemy session.
    
    Example:
        with get_session() as session:
            instances = session.query(RawInstance).all()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get an async database session.
    
    Yields:
        AsyncSession: SQLAlchemy async session.
    
    Example:
        async with get_async_session() as session:
            result = await session.execute(select(RawInstance))
            instances = result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class DatabaseClient:
    """
    Database client class for managing connections.
    
    Provides both synchronous and asynchronous access patterns.
    Compatible with Roll framework.
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database client.
        
        Args:
            database_url: Optional database URL override.
        """
        self._database_url = database_url or config.database_url
        self._engine = None
        self._async_engine = None
        self._session_factory = None
        self._async_session_factory = None
    
    @property
    def engine(self):
        """Get or create the synchronous engine."""
        if self._engine is None:
            _kwargs = {"echo": os.getenv("SQL_ECHO", "false").lower() == "true"}
            if self._database_url.startswith("sqlite"):
                _kwargs["connect_args"] = {"check_same_thread": False}
                _kwargs["poolclass"] = StaticPool
            elif self._database_url.startswith("postgresql"):
                # PostgreSQL connection pooling to prevent "too many clients" errors
                _kwargs["pool_size"] = 5
                _kwargs["max_overflow"] = 10
                _kwargs["pool_pre_ping"] = True
                _kwargs["pool_recycle"] = 3600
                _kwargs["pool_timeout"] = 30
            self._engine = create_engine(self._database_url, **_kwargs)
        return self._engine
    
    @property
    def async_engine(self):
        """Get or create the async engine."""
        if self._async_engine is None:
            async_url = self._database_url
            if self._database_url.startswith("sqlite:///"):
                async_url = self._database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
            elif self._database_url.startswith("postgresql://"):
                async_url = self._database_url.replace("postgresql://", "postgresql+asyncpg://")
            
            _kwargs = {"echo": os.getenv("SQL_ECHO", "false").lower() == "true"}
            if async_url.startswith("sqlite"):
                _kwargs["connect_args"] = {"check_same_thread": False}
                _kwargs["poolclass"] = StaticPool
            elif async_url.startswith("postgresql"):
                # PostgreSQL connection pooling for async engine
                _kwargs["pool_size"] = 5
                _kwargs["max_overflow"] = 10
                _kwargs["pool_pre_ping"] = True
                _kwargs["pool_recycle"] = 3600
                _kwargs["pool_timeout"] = 30
            self._async_engine = create_async_engine(async_url, **_kwargs)
        return self._async_engine
    
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async database session."""
        if self._async_session_factory is None:
            self._async_session_factory = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
        async with self._async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    def init_db(self):
        """Initialize database tables."""
        Base.metadata.create_all(bind=self.engine)
    
    def drop_db(self):
        """Drop all database tables."""
        Base.metadata.drop_all(bind=self.engine)


# Export commonly used items
__all__ = [
    "get_session",
    "get_async_session",
    "init_db",
    "drop_db",
    "engine",
    "async_engine",
    "config",
    "DatabaseConfig",
    "DatabaseClient",
    "Session",
    "AsyncSession",
    "Base",
]
