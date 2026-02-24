"""
MySQL DDL Generator
Generates MySQL-specific DDL statements.
"""

from typing import List, Optional
from database.ddl.base import BaseDDL


class MySQLDDL(BaseDDL):
    """MySQL-specific DDL generator"""
    
    db_type = "mysql"
    
    # ==========================================
    # Data Type Mappings
    # ==========================================
    
    def auto_increment_primary_key(self, name: str) -> str:
        """Generate AUTO_INCREMENT PRIMARY KEY for MySQL"""
        return f"INT AUTO_INCREMENT PRIMARY KEY"
    
    def text_type(self, length: Optional[int] = None) -> str:
        """Generate VARCHAR or TEXT type"""
        if length:
            return f"VARCHAR({length})"
        return "TEXT"
    
    def timestamp_type(self) -> str:
        """Generate TIMESTAMP type"""
        return "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    
    def boolean_type(self) -> str:
        """Generate BOOLEAN type (TINYINT(1) in MySQL)"""
        return "TINYINT(1)"
    
    def json_type(self) -> str:
        """Generate JSON type"""
        return "JSON"
    
    def blob_type(self) -> str:
        """Generate BLOB type"""
        return "LONGBLOB"
    
    # ==========================================
    # Table Operations
    # ==========================================
    
    def create_table(self, table_name: str, columns: List[str], if_not_exists: bool = True) -> str:
        """Generate CREATE TABLE statement"""
        columns_sql = ",\n    ".join(columns)
        if if_not_exists:
            return f"CREATE TABLE IF NOT EXISTS {self.quote_identifier(table_name)} (\n    {columns_sql}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        return f"CREATE TABLE {self.quote_identifier(table_name)} (\n    {columns_sql}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    
    def drop_table(self, table_name: str, if_exists: bool = True) -> str:
        """Generate DROP TABLE statement"""
        if if_exists:
            return f"DROP TABLE IF EXISTS {self.quote_identifier(table_name)}"
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
        
        # MySQL doesn't support IF NOT EXISTS for indexes
        # We need to check and create conditionally
        if if_not_exists:
            return f"""
SET @exist := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = '{table_name}' AND index_name = '{index_name}');
SET @sqlstmt := IF(@exist = 0, 'CREATE {unique_sql}INDEX {index_name} ON {self.quote_identifier(table_name)} ({columns_sql})', 'SELECT ''Index already exists.''');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""
        return f"CREATE {unique_sql}INDEX {index_name} ON {self.quote_identifier(table_name)} ({columns_sql})"
    
    def drop_index(self, index_name: str, table_name: Optional[str] = None) -> str:
        """Generate DROP INDEX statement (MySQL requires table name)"""
        if table_name:
            return f"DROP INDEX {index_name} ON {self.quote_identifier(table_name)}"
        return f"DROP INDEX {index_name}"
    
    # ==========================================
    # Column Operations
    # ==========================================
    
    def add_column(self, table_name: str, column_name: str, column_type: str, 
                   default_value: Optional[str] = None) -> str:
        """Generate ALTER TABLE ADD COLUMN statement"""
        default_sql = f" DEFAULT {default_value}" if default_value else ""
        # MySQL doesn't support IF NOT EXISTS for ADD COLUMN directly
        return f"""
SET @exist := (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = '{table_name}' AND column_name = '{column_name}');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE {self.quote_identifier(table_name)} ADD COLUMN {self.quote_identifier(column_name)} {column_type}{default_sql}', 'SELECT ''Column already exists.''');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""
    
    def drop_column(self, table_name: str, column_name: str) -> str:
        """Generate ALTER TABLE DROP COLUMN statement"""
        return f"ALTER TABLE {self.quote_identifier(table_name)} DROP COLUMN {self.quote_identifier(column_name)}"
    
    def column_exists(self, table_name: str, column_name: str) -> str:
        """Generate SQL to check if column exists"""
        return f"""
SELECT column_name 
FROM information_schema.columns 
WHERE table_schema = DATABASE() AND table_name = '{table_name}' AND column_name = '{column_name}'
"""
    
    # ==========================================
    # Upsert Operations
    # ==========================================
    
    def upsert(self, table_name: str, columns: List[str], 
               conflict_columns: List[str], update_columns: Optional[List[str]] = None) -> str:
        """Generate INSERT ... ON DUPLICATE KEY UPDATE statement"""
        columns_sql = ", ".join([self.quote_identifier(c) for c in columns])
        placeholders = ", ".join([self.placeholder(c) for c in columns])
        
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_columns]
        
        update_sql = ", ".join([f"{self.quote_identifier(c)} = VALUES({self.quote_identifier(c)})" for c in update_columns])
        
        return f"""
INSERT INTO {self.quote_identifier(table_name)} ({columns_sql})
VALUES ({placeholders})
ON DUPLICATE KEY UPDATE {update_sql}
"""
    
    # ==========================================
    # Utility Methods
    # ==========================================
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier with backticks"""
        return f"`{identifier}`"
