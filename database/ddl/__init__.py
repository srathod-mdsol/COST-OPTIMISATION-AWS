"""
Database DDL Module
Provides SQL DDL statements for multiple database types.
"""

from database.ddl.base import BaseDDL
from database.ddl.postgres import PostgreSQLDDL
from database.ddl.mysql import MySQLDDL
from database.ddl.oracle import OracleDDL
from database.ddl.mssql import MSSQLDDL
from database.ddl.sqlite import SQLiteDDL
from database.ddl.factory import get_ddl, get_ddl_from_url, get_all_ddl

__all__ = [
    'BaseDDL',
    'PostgreSQLDDL', 
    'MySQLDDL',
    'OracleDDL', 
    'MSSQLDDL',
    'SQLiteDDL',
    'get_ddl',
    'get_ddl_from_url',
    'get_all_ddl'
]
