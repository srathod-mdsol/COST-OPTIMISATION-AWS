"""
Database module for AWS Cost Optimization Tool.

This module provides database access through SQLAlchemy ORM with support
for both SQLite (development) and PostgreSQL (production).
Compatible with Roll framework.

Usage:
    from database import get_session, init_db, Base
    from database.models import RawInstance, EtlRun
    
    # Initialize database
    init_db()
    
    # Synchronous usage
    with get_session() as session:
        instances = session.query(RawInstance).all()
    
    # Asynchronous usage
    async with get_async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(RawInstance))
        instances = result.scalars().all()
"""

from database.client import (
    get_session,
    get_async_session,
    init_db,
    drop_db,
    engine,
    async_engine,
    config,
    DatabaseConfig,
    DatabaseClient,
    Session,
    AsyncSession,
    Base,
)

from database.models import (
    EtlRun,
    RawInstance,
    RawMetric,
    InstanceTag,
    DataFreshness,
    EtlLock,
    AnalysisCache,
    AwsPricing,
    EbsPricing,
)

__all__ = [
    # Client functions
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
    # Models
    "EtlRun",
    "RawInstance",
    "RawMetric",
    "InstanceTag",
    "DataFreshness",
    "EtlLock",
    "AnalysisCache",
    "AwsPricing",
    "EbsPricing",
]
