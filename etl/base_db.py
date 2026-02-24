"""
Base database operations for ETL modules.

This module provides a database-agnostic layer for ETL operations,
supporting PostgreSQL, MySQL, Oracle, MSSQL, and SQLite.
"""

import os
from typing import Optional, List, Dict, Any, Union
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import text, create_engine, MetaData, Table, Column, inspect
from sqlalchemy.engine import Engine, Connection, Row
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.pool import StaticPool

from database.db_utils import (
    get_engine, get_connection, get_database_type, DatabaseType,
    is_sqlite, is_postgresql, is_mysql, is_oracle, is_mssql,
    get_current_timestamp_sql
)
from database.ddl import get_ddl, BaseDDL
from core.config import Config
from core.logger import setup_logger

logger = setup_logger(__name__)


class BaseDatabase:
    """Base class for database operations with multi-database support."""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database connection.
        
        Args:
            database_url: Database connection URL. Defaults to Config.DATABASE_URL.
        """
        self.database_url = database_url or Config.DATABASE_URL or f"sqlite:///{Config.ETL_DB_PATH}"
        self._engine: Optional[Engine] = None
        self._db_type: Optional[DatabaseType] = None
        self._ddl: Optional[BaseDDL] = None
    
    @property
    def engine(self) -> Engine:
        """Get or create the SQLAlchemy engine with connection pooling."""
        if self._engine is None:
            # Determine if this is PostgreSQL or SQLite
            is_postgres = self.database_url.startswith("postgresql")
            is_sqlite = self.database_url.startswith("sqlite")
            
            # Base engine kwargs
            engine_kwargs = {
                "echo": False,  # Set to True for SQL debugging
            }
            
            if is_sqlite:
                # SQLite-specific settings - use StaticPool for simplicity
                engine_kwargs["connect_args"] = {"check_same_thread": False}
                engine_kwargs["poolclass"] = StaticPool
            elif is_postgres:
                # PostgreSQL connection pooling to prevent "too many clients" errors
                engine_kwargs["pool_size"] = 5           # Number of connections to keep in pool
                engine_kwargs["max_overflow"] = 10       # Additional connections allowed beyond pool_size
                engine_kwargs["pool_pre_ping"] = True    # Check connection health before using
                engine_kwargs["pool_recycle"] = 3600     # Recycle connections after 1 hour
                engine_kwargs["pool_timeout"] = 30       # Timeout for getting connection from pool
            
            self._engine = create_engine(self.database_url, **engine_kwargs)
        return self._engine
    
    @property
    def db_type(self) -> DatabaseType:
        """Get the database type."""
        if self._db_type is None:
            self._db_type = get_database_type(self.database_url)
        return self._db_type
    
    @property
    def ddl(self) -> BaseDDL:
        """Get the DDL generator for this database type."""
        if self._ddl is None:
            self._ddl = get_ddl(self.db_type.value)
        return self._ddl
    
    @contextmanager
    def get_connection(self) -> Connection:
        """Get a database connection as a context manager."""
        with self.engine.connect() as conn:
            yield conn
    
    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a SQL statement.
        
        Args:
            sql: SQL statement
            params: Parameters for the statement
            
        Returns:
            Result of the execution
        """
        with self.get_connection() as conn:
            result = conn.execute(text(sql), params or {})
            conn.commit()
            return result
    
    def execute_many(self, sql: str, params_list: List[Dict[str, Any]]) -> int:
        """Execute a SQL statement multiple times.
        
        Args:
            sql: SQL statement
            params_list: List of parameter dictionaries
            
        Returns:
            Number of rows affected
        """
        with self.get_connection() as conn:
            result = conn.execute(text(sql), params_list)
            conn.commit()
            return result.rowcount
    
    def fetch_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Row]:
        """Fetch a single row.
        
        Args:
            sql: SQL query
            params: Query parameters
            
        Returns:
            A single row or None
        """
        with self.get_connection() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchone()
    
    def fetch_all(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Row]:
        """Fetch all rows.
        
        Args:
            sql: SQL query
            params: Query parameters
            
        Returns:
            List of rows
        """
        with self.get_connection() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchall()
    
    def fetch_value(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Fetch a single value.
        
        Args:
            sql: SQL query
            params: Query parameters
            
        Returns:
            A single value or None
        """
        row = self.fetch_one(sql, params)
        return row[0] if row else None
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists.
        
        Args:
            table_name: Name of the table
            
        Returns:
            True if table exists
        """
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()
    
    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            
        Returns:
            True if column exists
        """
        inspector = inspect(self.engine)
        if table_name not in inspector.get_table_names():
            return False
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    
    def create_table(self, table_name: str, columns: List[str], if_not_exists: bool = True) -> bool:
        """Create a table using DDL.
        
        Args:
            table_name: Name of the table
            columns: List of column definitions
            if_not_exists: Whether to add IF NOT EXISTS clause
            
        Returns:
            True if table was created
        """
        if if_not_exists and self.table_exists(table_name):
            return False
        
        sql = self.ddl.create_table(table_name, columns, if_not_exists)
        try:
            self.execute(sql)
            logger.info(f"Created table {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error creating table {table_name}: {e}")
            return False
    
    def drop_table(self, table_name: str, if_exists: bool = True) -> bool:
        """Drop a table using DDL.
        
        Args:
            table_name: Name of the table
            if_exists: Whether to add IF EXISTS clause
            
        Returns:
            True if table was dropped
        """
        sql = self.ddl.drop_table(table_name, if_exists)
        try:
            self.execute(sql)
            logger.info(f"Dropped table {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error dropping table {table_name}: {e}")
            return False
    
    def add_column_if_not_exists(self, table_name: str, column_name: str, 
                                  column_type: str, default_value: Any = None) -> bool:
        """Add a column to a table if it doesn't exist using DDL.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            column_type: SQL type of the column
            default_value: Default value for the column
            
        Returns:
            True if column was added
        """
        if self.column_exists(table_name, column_name):
            return False
        
        try:
            default_str = str(default_value) if default_value is not None else None
            sql = self.ddl.add_column(table_name, column_name, column_type, default_str)
            self.execute(sql)
            logger.info(f"Added column {column_name} to table {table_name}")
            return True
        except Exception as e:
            logger.debug(f"Could not add column {column_name}: {e}")
            return False
    
    def create_index_if_not_exists(self, index_name: str, table_name: str, 
                                    columns: List[str], unique: bool = False) -> bool:
        """Create an index if it doesn't exist using DDL.
        
        Args:
            index_name: Name of the index
            table_name: Name of the table
            columns: List of column names
            unique: Whether the index should be unique
            
        Returns:
            True if index was created
        """
        try:
            sql = self.ddl.create_index(index_name, table_name, columns, unique, if_not_exists=True)
            self.execute(sql)
            logger.info(f"Created index {index_name} on {table_name}")
            return True
        except Exception as e:
            logger.debug(f"Could not create index {index_name}: {e}")
            return False
    
    def get_auto_increment_type(self) -> str:
        """Get the auto-increment column type for the current database.
        
        Returns:
            SQL type string for auto-increment column
        """
        return self.ddl.auto_increment_primary_key("id")
    
    def get_text_type(self) -> str:
        """Get the text type for the current database."""
        return self.ddl.text_type()
    
    def get_timestamp_type(self) -> str:
        """Get the timestamp type for the current database."""
        return self.ddl.timestamp_type()
    
    def get_boolean_type(self) -> str:
        """Get the boolean type for the current database."""
        return self.ddl.boolean_type()
    
    def get_current_timestamp(self) -> str:
        """Get the current timestamp SQL for the current database."""
        return get_current_timestamp_sql(self.database_url)
    
    def begin_transaction(self) -> Connection:
        """Begin a transaction.
        
        Returns:
            A connection with an active transaction
        """
        conn = self.engine.connect()
        conn.begin()
        return conn
    
    def truncate_table(self, table_name: str) -> None:
        """Truncate a table using DDL.
        
        Args:
            table_name: Name of the table to truncate
        """
        sql = self.ddl.truncate_table(table_name)
        self.execute(sql)
    
    def upsert(self, table_name: str, data: Dict[str, Any], 
               conflict_columns: List[str], update_columns: Optional[List[str]] = None) -> bool:
        """Perform an upsert operation using DDL.
        
        Args:
            table_name: Name of the table
            data: Dictionary of column names to values
            conflict_columns: Columns to check for conflicts
            update_columns: Columns to update on conflict (defaults to all non-conflict columns)
            
        Returns:
            True if upsert was successful
        """
        columns = list(data.keys())
        sql = self.ddl.upsert(table_name, columns, conflict_columns, update_columns)
        try:
            self.execute(sql, data)
            return True
        except Exception as e:
            logger.error(f"Upsert failed for {table_name}: {e}")
            return False
    
    def initialize_schema(self, tables: Optional[List[str]] = None) -> None:
        """Initialize database schema with all required tables.
        
        Args:
            tables: List of table names to create (defaults to all)
        """
        all_schemas = self.ddl.get_all_table_schemas()
        
        if tables:
            schemas = {k: v for k, v in all_schemas.items() if k in tables}
        else:
            schemas = all_schemas
        
        for table_name, columns in schemas.items():
            self.create_table(table_name, columns)
            
            # Create indexes for specific tables
            if table_name == 'raw_instances':
                self.create_index_if_not_exists('idx_raw_instances_service_region', 'raw_instances', 
                                                ['service_type', 'region'])
                self.create_index_if_not_exists('idx_raw_instances_instance_id', 'raw_instances', 
                                                ['instance_id'])
                self.create_index_if_not_exists('idx_raw_instances_service', 'raw_instances', 
                                                ['service_type'])
                self.create_index_if_not_exists('idx_raw_instances_region', 'raw_instances', 
                                                ['region'])
            elif table_name == 'raw_metrics':
                self.create_index_if_not_exists('idx_raw_metrics_instance', 'raw_metrics', 
                                                ['instance_id', 'metric_name'])
                self.create_index_if_not_exists('idx_raw_metrics_instance_id', 'raw_metrics', 
                                                ['instance_id'])
                self.create_index_if_not_exists('idx_raw_metrics_timestamp', 'raw_metrics', 
                                                ['timestamp'])
                self.create_index_if_not_exists('idx_raw_metrics_instance_timestamp', 'raw_metrics', 
                                                ['instance_id', 'timestamp'])
            elif table_name == 'instance_tags':
                self.create_index_if_not_exists('idx_instance_tags_instance', 'instance_tags', 
                                                ['instance_id'])
                self.create_index_if_not_exists('idx_instance_tags_key', 'instance_tags', 
                                                ['tag_key'])
            elif table_name == 'aws_pricing':
                self.create_index_if_not_exists('idx_pricing_lookup', 'aws_pricing', 
                                                ['instance_type', 'region', 'service'])
                self.create_index_if_not_exists('idx_pricing_instance_region', 'aws_pricing', 
                                                ['instance_type', 'region'])
                self.create_index_if_not_exists('idx_pricing_service', 'aws_pricing', 
                                                ['service'])
            elif table_name == 'ebs_pricing':
                self.create_index_if_not_exists('idx_ebs_pricing_lookup', 'ebs_pricing', 
                                                ['volume_type', 'region'])
        
        logger.info(f"Database schema initialized for {len(schemas)} tables")
