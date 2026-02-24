"""
DDL Factory
Factory for creating database-specific DDL generators.
"""

from typing import Optional
from database.ddl.base import BaseDDL
from database.ddl.postgres import PostgreSQLDDL
from database.ddl.mysql import MySQLDDL
from database.ddl.oracle import OracleDDL
from database.ddl.mssql import MSSQLDDL
from database.ddl.sqlite import SQLiteDDL


def get_ddl(db_type: str) -> BaseDDL:
    """
    Get the appropriate DDL generator for a database type.
    
    Args:
        db_type: Database type ('postgresql', 'mysql', 'oracle', 'mssql', 'sqlite')
    
    Returns:
        BaseDDL: Database-specific DDL generator
    
    Raises:
        ValueError: If database type is not supported
    """
    db_type_lower = db_type.lower()
    
    if db_type_lower in ('postgresql', 'postgres', 'psycopg2'):
        return PostgreSQLDDL()
    elif db_type_lower in ('mysql', 'mariadb'):
        return MySQLDDL()
    elif db_type_lower in ('oracle', 'cx_oracle'):
        return OracleDDL()
    elif db_type_lower in ('mssql', 'sqlserver', 'pyodbc'):
        return MSSQLDDL()
    elif db_type_lower in ('sqlite', 'sqlite3'):
        return SQLiteDDL()
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def get_ddl_from_url(database_url: str) -> BaseDDL:
    """
    Get the appropriate DDL generator from a database URL.
    
    Args:
        database_url: Database connection URL
    
    Returns:
        BaseDDL: Database-specific DDL generator
    """
    from database.db_utils import get_database_type
    db_type = get_database_type(database_url)
    return get_ddl(db_type)


# Convenience function to get all DDL generators
def get_all_ddl() -> dict:
    """
    Get all available DDL generators.
    
    Returns:
        dict: Dictionary mapping database type names to DDL instances
    """
    return {
        'postgresql': PostgreSQLDDL(),
        'mysql': MySQLDDL(),
        'oracle': OracleDDL(),
        'mssql': MSSQLDDL(),
        'sqlite': SQLiteDDL()
    }
