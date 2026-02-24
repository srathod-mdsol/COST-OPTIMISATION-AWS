"""
SQLite DDL Generator
Generates SQLite-specific DDL statements.
"""

from typing import List, Optional
from database.ddl.base import BaseDDL


class SQLiteDDL(BaseDDL):
    """SQLite-specific DDL generator"""
    
    db_type = "sqlite"
    
    # ==========================================
    # Data Type Mappings
    # ==========================================
    
    def auto_increment_primary_key(self, name: str) -> str:
        """Generate INTEGER PRIMARY KEY AUTOINCREMENT for SQLite"""
        return f"INTEGER PRIMARY KEY AUTOINCREMENT"
    
    def text_type(self, length: Optional[int] = None) -> str:
        """Generate TEXT type (SQLite has dynamic typing)"""
        return "TEXT"
    
    def timestamp_type(self) -> str:
        """Generate TEXT type for timestamps"""
        return "TEXT"
    
    def boolean_type(self) -> str:
        """Generate INTEGER for boolean (SQLite uses 0/1)"""
        return "INTEGER DEFAULT 0"
    
    def json_type(self) -> str:
        """Generate TEXT for JSON"""
        return "TEXT"
    
    def blob_type(self) -> str:
        """Generate BLOB type"""
        return "BLOB"
    
    # ==========================================
    # Table Operations
    # ==========================================
    
    def create_table(self, table_name: str, columns: List[str], if_not_exists: bool = True) -> str:
        """Generate CREATE TABLE statement"""
        columns_sql = ",\n    ".join(columns)
        if if_not_exists:
            return f"CREATE TABLE IF NOT EXISTS {self.quote_identifier(table_name)} (\n    {columns_sql}\n)"
        return f"CREATE TABLE {self.quote_identifier(table_name)} (\n    {columns_sql}\n)"
    
    def drop_table(self, table_name: str, if_exists: bool = True) -> str:
        """Generate DROP TABLE statement"""
        if if_exists:
            return f"DROP TABLE IF EXISTS {self.quote_identifier(table_name)}"
        return f"DROP TABLE {self.quote_identifier(table_name)}"
    
    def truncate_table(self, table_name: str) -> str:
        """Generate DELETE FROM (SQLite doesn't have TRUNCATE)"""
        return f"DELETE FROM {self.quote_identifier(table_name)}"
    
    # ==========================================
    # Index Operations
    # ==========================================
    
    def create_index(self, index_name: str, table_name: str, columns: List[str], 
                     unique: bool = False, if_not_exists: bool = True) -> str:
        """Generate CREATE INDEX statement"""
        unique_sql = "UNIQUE " if unique else ""
        columns_sql = ", ".join([self.quote_identifier(c) for c in columns])
        
        if if_not_exists:
            return f"CREATE {unique_sql}INDEX IF NOT EXISTS {index_name} ON {self.quote_identifier(table_name)} ({columns_sql})"
        return f"CREATE {unique_sql}INDEX {index_name} ON {self.quote_identifier(table_name)} ({columns_sql})"
    
    def drop_index(self, index_name: str, table_name: Optional[str] = None) -> str:
        """Generate DROP INDEX statement"""
        return f"DROP INDEX IF EXISTS {index_name}"
    
    # ==========================================
    # Column Operations
    # ==========================================
    
    def add_column(self, table_name: str, column_name: str, column_type: str, 
                   default_value: Optional[str] = None) -> str:
        """Generate ALTER TABLE ADD COLUMN statement"""
        default_sql = f" DEFAULT {default_value}" if default_value else ""
        return f"ALTER TABLE {self.quote_identifier(table_name)} ADD COLUMN {self.quote_identifier(column_name)} {column_type}{default_sql}"
    
    def drop_column(self, table_name: str, column_name: str) -> str:
        """Generate ALTER TABLE DROP COLUMN statement (SQLite 3.35.0+)"""
        return f"ALTER TABLE {self.quote_identifier(table_name)} DROP COLUMN {self.quote_identifier(column_name)}"
    
    def column_exists(self, table_name: str, column_name: str) -> str:
        """Generate SQL to check if column exists"""
        return f"SELECT name FROM pragma_table_info('{table_name}') WHERE name = '{column_name}'"
    
    # ==========================================
    # Upsert Operations
    # ==========================================
    
    def upsert(self, table_name: str, columns: List[str], 
               conflict_columns: List[str], update_columns: Optional[List[str]] = None) -> str:
        """Generate INSERT ... ON CONFLICT DO UPDATE statement (SQLite 3.24.0+)"""
        columns_sql = ", ".join([self.quote_identifier(c) for c in columns])
        placeholders = ", ".join([self.placeholder(c) for c in columns])
        conflict_sql = ", ".join([self.quote_identifier(c) for c in conflict_columns])
        
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_columns]
        
        update_sql = ", ".join([f"{self.quote_identifier(c)} = excluded.{self.quote_identifier(c)}" for c in update_columns])
        
        return f"""
INSERT INTO {self.quote_identifier(table_name)} ({columns_sql})
VALUES ({placeholders})
ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}
"""
    
    # ==========================================
    # Utility Methods
    # ==========================================
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier with double quotes"""
        return f'"{identifier}"'
