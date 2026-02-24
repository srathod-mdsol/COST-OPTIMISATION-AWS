"""
Microsoft SQL Server DDL Generator
Generates MSSQL-specific DDL statements.
"""

from typing import List, Optional
from database.ddl.base import BaseDDL


class MSSQLDDL(BaseDDL):
    """Microsoft SQL Server-specific DDL generator"""
    
    db_type = "mssql"
    
    # ==========================================
    # Data Type Mappings
    # ==========================================
    
    def auto_increment_primary_key(self, name: str) -> str:
        """Generate INT IDENTITY PRIMARY KEY for MSSQL"""
        return f"INT IDENTITY(1,1) PRIMARY KEY"
    
    def text_type(self, length: Optional[int] = None) -> str:
        """Generate NVARCHAR or NVARCHAR(MAX) type"""
        if length:
            return f"NVARCHAR({length})"
        return "NVARCHAR(MAX)"
    
    def timestamp_type(self) -> str:
        """Generate DATETIME2 type"""
        return "DATETIME2 DEFAULT GETUTCDATE()"
    
    def boolean_type(self) -> str:
        """Generate BIT type"""
        return "BIT DEFAULT 0"
    
    def json_type(self) -> str:
        """Generate NVARCHAR(MAX) for JSON (MSSQL 2016+ has JSON functions)"""
        return "NVARCHAR(MAX)"
    
    def blob_type(self) -> str:
        """Generate VARBINARY(MAX) type"""
        return "VARBINARY(MAX)"
    
    # ==========================================
    # Table Operations
    # ==========================================
    
    def create_table(self, table_name: str, columns: List[str], if_not_exists: bool = True) -> str:
        """Generate CREATE TABLE statement"""
        columns_sql = ",\n    ".join(columns)
        
        if if_not_exists:
            return f"""
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '{table_name}')
BEGIN
    CREATE TABLE {self.quote_identifier(table_name)} (
        {columns_sql}
    )
END
"""
        return f"CREATE TABLE {self.quote_identifier(table_name)} (\n    {columns_sql}\n)"
    
    def drop_table(self, table_name: str, if_exists: bool = True) -> str:
        """Generate DROP TABLE statement"""
        if if_exists:
            return f"""
IF EXISTS (SELECT * FROM sys.tables WHERE name = '{table_name}')
BEGIN
    DROP TABLE {self.quote_identifier(table_name)}
END
"""
        return f"DROP TABLE {self.quote_identifier(table_name)}"
    
    def truncate_table(self, table_name: str) -> str:
        """Generate TRUNCATE TABLE statement"""
        return f"TRUNCATE TABLE {self.quote_identifier(table_name)}"
    
    # ==========================================
    # Index Operations
    # ==========================================
    
    def create_index(self, index_name: str, table_name: str, columns: List[str], 
                     unique: bool = False, if_not_exists: bool = True) -> str:
        """Generate CREATE INDEX statement"""
        unique_sql = "UNIQUE " if unique else ""
        columns_sql = ", ".join([self.quote_identifier(c) for c in columns])
        
        if if_not_exists:
            return f"""
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = '{index_name}' AND object_id = OBJECT_ID('{table_name}'))
BEGIN
    CREATE {unique_sql}INDEX {index_name} ON {self.quote_identifier(table_name)} ({columns_sql})
END
"""
        return f"CREATE {unique_sql}INDEX {index_name} ON {self.quote_identifier(table_name)} ({columns_sql})"
    
    def drop_index(self, index_name: str, table_name: Optional[str] = None) -> str:
        """Generate DROP INDEX statement (MSSQL requires table name)"""
        if table_name:
            return f"DROP INDEX IF EXISTS {index_name} ON {self.quote_identifier(table_name)}"
        return f"DROP INDEX {index_name}"
    
    # ==========================================
    # Column Operations
    # ==========================================
    
    def add_column(self, table_name: str, column_name: str, column_type: str, 
                   default_value: Optional[str] = None) -> str:
        """Generate ALTER TABLE ADD COLUMN statement"""
        default_sql = f" DEFAULT {default_value}" if default_value else ""
        
        return f"""
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = '{column_name}')
BEGIN
    ALTER TABLE {self.quote_identifier(table_name)} ADD {self.quote_identifier(column_name)} {column_type}{default_sql}
END
"""
    
    def drop_column(self, table_name: str, column_name: str) -> str:
        """Generate ALTER TABLE DROP COLUMN statement"""
        return f"""
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = '{column_name}')
BEGIN
    ALTER TABLE {self.quote_identifier(table_name)} DROP COLUMN {self.quote_identifier(column_name)}
END
"""
    
    def column_exists(self, table_name: str, column_name: str) -> str:
        """Generate SQL to check if column exists"""
        return f"""
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = '{table_name}' AND column_name = '{column_name}'
"""
    
    # ==========================================
    # Upsert Operations
    # ==========================================
    
    def upsert(self, table_name: str, columns: List[str], 
               conflict_columns: List[str], update_columns: Optional[List[str]] = None) -> str:
        """Generate MERGE statement for MSSQL"""
        columns_sql = ", ".join([self.quote_identifier(c) for c in columns])
        placeholders = ", ".join([self.placeholder(c) for c in columns])
        
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_columns]
        
        # Build ON clause for conflict columns
        on_clause = " AND ".join([f"t.{self.quote_identifier(c)} = s.{self.quote_identifier(c)}" for c in conflict_columns])
        
        # Build UPDATE SET clause
        update_sql = ", ".join([f"t.{self.quote_identifier(c)} = s.{self.quote_identifier(c)}" for c in update_columns])
        
        return f"""
MERGE INTO {self.quote_identifier(table_name)} AS t
USING (SELECT {placeholders}) AS s ON ({on_clause})
WHEN MATCHED THEN
    UPDATE SET {update_sql}
WHEN NOT MATCHED THEN
    INSERT ({columns_sql}) VALUES ({placeholders});
"""
    
    # ==========================================
    # Utility Methods
    # ==========================================
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier with square brackets"""
        return f"[{identifier}]"
