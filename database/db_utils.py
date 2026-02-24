"""
Database utilities for multi-database support.

This module provides utilities for working with different database backends
(PostgreSQL, MySQL, Oracle, MSSQL, SQLite) through SQLAlchemy.

Usage:
    from database.db_utils import get_engine, get_connection, DatabaseType
    from database.db_utils import create_tables, execute_query
"""

import os
from typing import Optional, Union, Any, Dict, List
from enum import Enum
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.pool import StaticPool, NullPool
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


class DatabaseType(Enum):
    """Supported database types."""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    ORACLE = "oracle"
    MSSQL = "mssql"


def parse_database_url(database_url: str) -> Dict[str, Any]:
    """
    Parse a database URL and extract database type and components.
    
    Args:
        database_url: SQLAlchemy database URL
        
    Returns:
        Dictionary with database type and parsed components
    """
    result = {
        "type": None,
        "driver": None,
        "async_driver": None,
        "is_async": False
    }
    
    if database_url.startswith("sqlite"):
        result["type"] = DatabaseType.SQLITE
        result["driver"] = "sqlite"
        result["async_driver"] = "sqlite+aiosqlite"
    elif database_url.startswith("postgresql"):
        result["type"] = DatabaseType.POSTGRESQL
        result["driver"] = "postgresql+psycopg2"
        result["async_driver"] = "postgresql+asyncpg"
    elif database_url.startswith("mysql"):
        result["type"] = DatabaseType.MYSQL
        result["driver"] = "mysql+pymysql"
        result["async_driver"] = "mysql+aiomysql"
    elif database_url.startswith("oracle"):
        result["type"] = DatabaseType.ORACLE
        result["driver"] = "oracle+cx_oracle"
        result["async_driver"] = "oracle+cx_oracle"  # No async driver for Oracle
    elif database_url.startswith("mssql") or database_url.startswith("sqlserver"):
        result["type"] = DatabaseType.MSSQL
        result["driver"] = "mssql+pyodbc"
        result["async_driver"] = "mssql+pyodbc"  # No async driver for MSSQL
    else:
        raise ValueError(f"Unsupported database URL: {database_url[:50]}...")
    
    return result


def normalize_database_url(database_url: str, async_mode: bool = False) -> str:
    """
    Normalize a database URL to use the appropriate driver.
    
    Args:
        database_url: Original database URL
        async_mode: Whether to use async driver
        
    Returns:
        Normalized database URL with appropriate driver
    """
    parsed = parse_database_url(database_url)
    
    # If URL already has a driver specified, return as-is
    if "+" in database_url.split("://")[0]:
        return database_url
    
    # Add appropriate driver
    prefix = database_url.split("://")[0]
    rest = "://".join(database_url.split("://")[1:])
    
    if async_mode:
        driver = parsed["async_driver"]
    else:
        driver = parsed["driver"]
    
    return f"{driver}://{rest}"


def get_engine(
    database_url: Optional[str] = None,
    echo: bool = False,
    pool_size: Optional[int] = None,
    max_overflow: Optional[int] = None,
    **kwargs
) -> Engine:
    """
    Create a SQLAlchemy engine based on the database URL.
    
    Args:
        database_url: Database connection URL (defaults to DATABASE_URL env var)
        echo: Whether to echo SQL statements
        pool_size: Connection pool size
        max_overflow: Maximum overflow connections
        **kwargs: Additional engine arguments
        
    Returns:
        SQLAlchemy Engine instance
    """
    database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/etl_database.db")
    parsed = parse_database_url(database_url)
    
    # Normalize URL with appropriate driver
    url = normalize_database_url(database_url, async_mode=False)
    
    # Engine kwargs
    engine_kwargs = {
        "echo": echo or os.getenv("SQL_ECHO", "false").lower() == "true",
    }
    
    # Database-specific settings
    if parsed["type"] == DatabaseType.SQLITE:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool
    elif parsed["type"] in [DatabaseType.POSTGRESQL, DatabaseType.MYSQL]:
        if pool_size:
            engine_kwargs["pool_size"] = pool_size
        if max_overflow:
            engine_kwargs["max_overflow"] = max_overflow
    elif parsed["type"] in [DatabaseType.ORACLE, DatabaseType.MSSQL]:
        engine_kwargs["pool_pre_ping"] = True
    
    # Merge with user kwargs
    engine_kwargs.update(kwargs)
    
    return create_engine(url, **engine_kwargs)


def get_async_engine(
    database_url: Optional[str] = None,
    echo: bool = False,
    **kwargs
):
    """
    Create an async SQLAlchemy engine based on the database URL.
    
    Args:
        database_url: Database connection URL (defaults to DATABASE_URL env var)
        echo: Whether to echo SQL statements
        **kwargs: Additional engine arguments
        
    Returns:
        SQLAlchemy async Engine instance
    """
    database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/etl_database.db")
    parsed = parse_database_url(database_url)
    
    # Normalize URL with async driver
    url = normalize_database_url(database_url, async_mode=True)
    
    # Engine kwargs
    engine_kwargs = {
        "echo": echo or os.getenv("SQL_ECHO", "false").lower() == "true",
    }
    
    # Database-specific settings
    if parsed["type"] == DatabaseType.SQLITE:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool
    
    # Merge with user kwargs
    engine_kwargs.update(kwargs)
    
    return create_async_engine(url, **engine_kwargs)


@contextmanager
def get_connection(database_url: Optional[str] = None, **kwargs):
    """
    Get a database connection as a context manager.
    
    Args:
        database_url: Database connection URL
        **kwargs: Additional engine arguments
        
    Yields:
        SQLAlchemy Connection instance
    """
    engine = get_engine(database_url, **kwargs)
    with engine.connect() as connection:
        yield connection


def get_session_maker(database_url: Optional[str] = None, **kwargs) -> sessionmaker:
    """
    Create a session maker for the database.
    
    Args:
        database_url: Database connection URL
        **kwargs: Additional engine arguments
        
    Returns:
        SQLAlchemy sessionmaker instance
    """
    engine = get_engine(database_url, **kwargs)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_async_session_maker(database_url: Optional[str] = None, **kwargs) -> async_sessionmaker:
    """
    Create an async session maker for the database.
    
    Args:
        database_url: Database connection URL
        **kwargs: Additional engine arguments
        
    Returns:
        SQLAlchemy async_sessionmaker instance
    """
    engine = get_async_engine(database_url, **kwargs)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


def execute_query(
    query: str,
    params: Optional[Dict[str, Any]] = None,
    database_url: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Execute a SQL query and return results.
    
    Args:
        query: SQL query string
        params: Query parameters
        database_url: Database connection URL
        **kwargs: Additional engine arguments
        
    Returns:
        Query result
    """
    with get_connection(database_url, **kwargs) as conn:
        result = conn.execute(text(query), params or {})
        conn.commit()
        return result


def execute_many(
    query: str,
    params_list: List[Dict[str, Any]],
    database_url: Optional[str] = None,
    **kwargs
) -> int:
    """
    Execute a SQL query multiple times with different parameters.
    
    Args:
        query: SQL query string
        params_list: List of parameter dictionaries
        database_url: Database connection URL
        **kwargs: Additional engine arguments
        
    Returns:
        Total row count affected
    """
    with get_connection(database_url, **kwargs) as conn:
        result = conn.execute(text(query), params_list)
        conn.commit()
        return result.rowcount


def table_exists(table_name: str, database_url: Optional[str] = None, **kwargs) -> bool:
    """
    Check if a table exists in the database.
    
    Args:
        table_name: Name of the table
        database_url: Database connection URL
        **kwargs: Additional engine arguments
        
    Returns:
        True if table exists, False otherwise
    """
    engine = get_engine(database_url, **kwargs)
    from sqlalchemy import inspect
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def get_database_type(database_url: Optional[str] = None) -> DatabaseType:
    """
    Get the database type from the URL.
    
    Args:
        database_url: Database connection URL
        
    Returns:
        DatabaseType enum value
    """
    database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/etl_database.db")
    parsed = parse_database_url(database_url)
    return parsed["type"]


def is_postgresql(database_url: Optional[str] = None) -> bool:
    """Check if the database is PostgreSQL."""
    return get_database_type(database_url) == DatabaseType.POSTGRESQL


def is_mysql(database_url: Optional[str] = None) -> bool:
    """Check if the database is MySQL."""
    return get_database_type(database_url) == DatabaseType.MYSQL


def is_sqlite(database_url: Optional[str] = None) -> bool:
    """Check if the database is SQLite."""
    return get_database_type(database_url) == DatabaseType.SQLITE


def is_oracle(database_url: Optional[str] = None) -> bool:
    """Check if the database is Oracle."""
    return get_database_type(database_url) == DatabaseType.ORACLE


def is_mssql(database_url: Optional[str] = None) -> bool:
    """Check if the database is MSSQL."""
    return get_database_type(database_url) == DatabaseType.MSSQL


# SQL dialect helpers
def get_placeholder_style(database_url: Optional[str] = None) -> str:
    """
    Get the placeholder style for the database.
    
    Returns:
        Placeholder style: 'qmark', 'numeric', 'named', 'format', or 'pyformat'
    """
    db_type = get_database_type(database_url)
    
    if db_type == DatabaseType.SQLITE:
        return "qmark"  # ?
    elif db_type == DatabaseType.POSTGRESQL:
        return "pyformat"  # %(name)s
    elif db_type == DatabaseType.MYSQL:
        return "format"  # %s
    elif db_type == DatabaseType.ORACLE:
        return "named"  # :name
    elif db_type == DatabaseType.MSSQL:
        return "pyformat"  # %(name)s
    
    return "named"


def get_auto_increment_sql(database_url: Optional[str] = None) -> str:
    """
    Get the auto-increment SQL for the database.
    
    Returns:
        Auto-increment SQL clause
    """
    db_type = get_database_type(database_url)
    
    if db_type == DatabaseType.SQLITE:
        return "AUTOINCREMENT"
    elif db_type == DatabaseType.POSTGRESQL:
        return ""  # Use SERIAL or IDENTITY
    elif db_type == DatabaseType.MYSQL:
        return "AUTO_INCREMENT"
    elif db_type in [DatabaseType.ORACLE, DatabaseType.MSSQL]:
        return ""  # Use sequences or IDENTITY
    
    return ""


def get_current_timestamp_sql(database_url: Optional[str] = None) -> str:
    """
    Get the current timestamp SQL for the database.
    
    Returns:
        Current timestamp SQL function
    """
    db_type = get_database_type(database_url)
    
    if db_type == DatabaseType.SQLITE:
        return "CURRENT_TIMESTAMP"
    elif db_type == DatabaseType.POSTGRESQL:
        return "CURRENT_TIMESTAMP"
    elif db_type == DatabaseType.MYSQL:
        return "CURRENT_TIMESTAMP"
    elif db_type == DatabaseType.ORACLE:
        return "SYSTIMESTAMP"
    elif db_type == DatabaseType.MSSQL:
        return "GETDATE()"
    
    return "CURRENT_TIMESTAMP"
