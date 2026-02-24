"""
Base DDL Class
Provides abstract base for database-specific DDL generators.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BaseDDL(ABC):
    """
    Abstract base class for database-specific DDL generators.
    Each database type should implement its own DDL class.
    """
    
    # Database type identifier
    db_type: str = "base"
    
    # ==========================================
    # Data Type Mappings
    # ==========================================
    
    @abstractmethod
    def auto_increment_primary_key(self, name: str) -> str:
        """Generate auto-increment primary key column definition"""
        pass
    
    @abstractmethod
    def text_type(self, length: Optional[int] = None) -> str:
        """Generate text/varchar type"""
        pass
    
    @abstractmethod
    def timestamp_type(self) -> str:
        """Generate timestamp type"""
        pass
    
    @abstractmethod
    def boolean_type(self) -> str:
        """Generate boolean type"""
        pass
    
    @abstractmethod
    def json_type(self) -> str:
        """Generate JSON type"""
        pass
    
    @abstractmethod
    def blob_type(self) -> str:
        """Generate BLOB/binary type"""
        pass
    
    # ==========================================
    # Table Operations
    # ==========================================
    
    @abstractmethod
    def create_table(self, table_name: str, columns: List[str], if_not_exists: bool = True) -> str:
        """Generate CREATE TABLE statement"""
        pass
    
    @abstractmethod
    def drop_table(self, table_name: str, if_exists: bool = True) -> str:
        """Generate DROP TABLE statement"""
        pass
    
    @abstractmethod
    def truncate_table(self, table_name: str) -> str:
        """Generate TRUNCATE TABLE statement"""
        pass
    
    # ==========================================
    # Index Operations
    # ==========================================
    
    @abstractmethod
    def create_index(self, index_name: str, table_name: str, columns: List[str], 
                     unique: bool = False, if_not_exists: bool = True) -> str:
        """Generate CREATE INDEX statement"""
        pass
    
    @abstractmethod
    def drop_index(self, index_name: str, table_name: Optional[str] = None) -> str:
        """Generate DROP INDEX statement"""
        pass
    
    # ==========================================
    # Column Operations
    # ==========================================
    
    @abstractmethod
    def add_column(self, table_name: str, column_name: str, column_type: str, 
                   default_value: Optional[str] = None) -> str:
        """Generate ALTER TABLE ADD COLUMN statement"""
        pass
    
    @abstractmethod
    def drop_column(self, table_name: str, column_name: str) -> str:
        """Generate ALTER TABLE DROP COLUMN statement"""
        pass
    
    @abstractmethod
    def column_exists(self, table_name: str, column_name: str) -> str:
        """Generate SQL to check if column exists"""
        pass
    
    # ==========================================
    # Upsert Operations
    # ==========================================
    
    @abstractmethod
    def upsert(self, table_name: str, columns: List[str], 
               conflict_columns: List[str], update_columns: Optional[List[str]] = None) -> str:
        """Generate upsert/merge statement template"""
        pass
    
    # ==========================================
    # Utility Methods
    # ==========================================
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier (table name, column name, etc.)"""
        return f'"{identifier}"'
    
    def quote_string(self, value: str) -> str:
        """Quote a string value"""
        return f"'{value}'"
    
    def placeholder(self, name: str) -> str:
        """Generate parameter placeholder"""
        return f":{name}"
    
    # ==========================================
    # Schema Definitions
    # ==========================================
    
    def get_etl_runs_schema(self) -> List[str]:
        """Get column definitions for etl_runs table"""
        return [
            f"run_id {self.auto_increment_primary_key('run_id')}",
            "run_type TEXT",
            "status TEXT",
            "start_time TEXT",
            "end_time TEXT",
            "duration_seconds INTEGER",
            "records_extracted INTEGER",
            "records_loaded INTEGER",
            "error_message TEXT",
            "triggered_by TEXT",
            "service_flags TEXT"
        ]
    
    def get_etl_locks_schema(self) -> List[str]:
        """Get column definitions for etl_locks table"""
        return [
            f"lock_id {self.auto_increment_primary_key('lock_id')}",
            "lock_type TEXT UNIQUE",
            "locked_at TEXT",
            "locked_by TEXT",
            "expires_at TEXT"
        ]
    
    def get_raw_instances_schema(self) -> List[str]:
        """Get column definitions for raw_instances table"""
        return [
            f"id {self.auto_increment_primary_key('id')}",
            "instance_id TEXT",
            "service_type TEXT",
            "region TEXT",
            "instance_class TEXT",
            "engine TEXT",
            "status TEXT",
            "created_date TEXT",
            "name TEXT",
            "raw_data TEXT",
            "vpc_id TEXT",
            "publicly_accessible TEXT",
            "storage_type TEXT",
            "multi_az TEXT",
            "availability_zone TEXT",
            "db_instance_arn TEXT",
            "backup_retention TEXT",
            "maintenance_window TEXT",
            "backup_window TEXT",
            "image_id TEXT",
            "subnet_id TEXT",
            "architecture TEXT",
            "public_ip TEXT",
            "private_ip TEXT",
            "environment_tag TEXT",
            "attached_instance_id TEXT",
            "volume_id TEXT",
            "size_gb INTEGER",
            "volume_type TEXT",
            "iops INTEGER",
            "throughput_mbps INTEGER",
            "encrypted TEXT",
            "monthly_cost REAL"
        ]
    
    def get_raw_metrics_schema(self) -> List[str]:
        """Get column definitions for raw_metrics table"""
        return [
            f"id {self.auto_increment_primary_key('id')}",
            "instance_id TEXT",
            "metric_name TEXT",
            "metric_value REAL",
            "timestamp TEXT",
            "unit TEXT",
            "statistics TEXT"
        ]
    
    def get_instance_tags_schema(self) -> List[str]:
        """Get column definitions for instance_tags table"""
        return [
            f"id {self.auto_increment_primary_key('id')}",
            "instance_id TEXT",
            "tag_key TEXT",
            "tag_value TEXT"
        ]
    
    def get_data_freshness_schema(self) -> List[str]:
        """Get column definitions for data_freshness table"""
        return [
            "service_type TEXT PRIMARY KEY",
            "last_updated TEXT",
            "next_scheduled TEXT",
            "record_count INTEGER",
            "status TEXT"
        ]
    
    def get_analysis_cache_schema(self) -> List[str]:
        """Get column definitions for analysis_cache table"""
        return [
            f"id {self.auto_increment_primary_key('id')}",
            "instance_id TEXT UNIQUE",
            "service_type TEXT",
            "is_idle INTEGER",
            "idle_score REAL",
            "idle_reasons TEXT",
            "active_reasons TEXT",
            "indicators TEXT",
            "recommendation TEXT",
            "potential_savings REAL",
            "last_activity_date TEXT",
            "analysis_timestamp TEXT"
        ]
    
    def get_aws_pricing_schema(self) -> List[str]:
        """Get column definitions for aws_pricing table"""
        return [
            "sku TEXT PRIMARY KEY",
            "instance_type TEXT",
            "region TEXT",
            "price_per_hour REAL",
            "currency TEXT",
            "service TEXT",
            "raw_json TEXT"
        ]
    
    def get_ebs_pricing_schema(self) -> List[str]:
        """Get column definitions for ebs_pricing table"""
        return [
            "sku TEXT PRIMARY KEY",
            "volume_type TEXT",
            "region TEXT",
            "price_per_gb_month REAL",
            "price_per_iops_month REAL",
            "currency TEXT",
            "location TEXT",
            "raw_json TEXT",
            "extracted_at TEXT"
        ]
    
    def get_all_table_schemas(self) -> Dict[str, List[str]]:
        """Get all table schemas as a dictionary"""
        return {
            'etl_runs': self.get_etl_runs_schema(),
            'etl_locks': self.get_etl_locks_schema(),
            'raw_instances': self.get_raw_instances_schema(),
            'raw_metrics': self.get_raw_metrics_schema(),
            'instance_tags': self.get_instance_tags_schema(),
            'data_freshness': self.get_data_freshness_schema(),
            'analysis_cache': self.get_analysis_cache_schema(),
            'aws_pricing': self.get_aws_pricing_schema(),
            'ebs_pricing': self.get_ebs_pricing_schema()
        }
