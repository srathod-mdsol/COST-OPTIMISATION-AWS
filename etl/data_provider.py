import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from cachetools import TTLCache

from core.config import Config
from core.logger import setup_logger
from etl.base_db import BaseDatabase, DatabaseType
from database.db_utils import get_engine, get_connection

logger = setup_logger(__name__)

# =============================================================================
# PERFORMANCE OPTIMIZATIONS
# =============================================================================

# Class-level pricing engine with connection pooling
_pricing_engine: Optional[Engine] = None

# Short TTL cache for pricing data (30 seconds) - balances accuracy with performance
# Pricing data rarely changes, so 30s TTL is acceptable while ensuring freshness
_pricing_ttl_cache = TTLCache(maxsize=1000, ttl=30)

def _get_pricing_engine() -> Engine:
    """Get or create pooled pricing database engine.
    
    Uses connection pooling for better performance:
    - pool_size=5: Maintain 5 connections
    - max_overflow=10: Allow up to 10 additional connections
    - pool_pre_ping=True: Check connection health before use
    """
    global _pricing_engine
    if _pricing_engine is None:
        pricing_db_url = Config.get_pricing_database_url()
        _pricing_engine = create_engine(
            pricing_db_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600  # Recycle connections after 1 hour
        )
        logger.info("Created pooled pricing database engine")
    return _pricing_engine


from core.constants import DEFAULT_EBS_STORAGE_COST, DAYS_PER_MONTH

class ETLDataProvider(BaseDatabase):
    """
    Data provider that reads from ETL database.
    Replaces direct AWS API calls with database queries.
    Supports multiple database backends via SQLAlchemy.
    
    Performance Optimizations:
    - Connection pooling for both main and pricing databases
    - Direct database queries with MIN() for accurate pricing
    - Batch query support for metrics
    """
    
    def __init__(self, db_path: str = None, database_url: str = None):
        """Initialize ETL data provider with database path or URL"""
        # Determine database URL
        if database_url is None:
            database_url = Config.get_database_url()
        
        # Initialize base class
        super().__init__(database_url)
        
        # Keep db_path for backwards compatibility and file-based operations
        self.db_path = db_path or Config.ETL_DB_PATH
        self._pricing_has_service_column = None
        # Ensure ETL database schema exists (creates data_freshness table, etc.)
        self._ensure_db_exists()
        # Ensure pricing database exists
        self._ensure_pricing_db_exists()
    
    def _ensure_db_exists(self):
        """Ensure the ETL database exists and has proper schema"""
        # For file-based databases (SQLite), create directory if needed
        if self.db_type == DatabaseType.SQLITE and self.db_path:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created ETL database directory: {db_dir}")

        # Use Orchestrator to ensure schema exists safely
        from etl.orchestrator import ETLOrchestrator
        ETLOrchestrator(database_url=self.database_url)
        logger.info(f"Verified schema for ETL database")
    
    def _ensure_pricing_db_exists(self):
        """Ensure the pricing database exists with proper schema"""
        pricing_db_url = Config.get_pricing_database_url()
        pricing_db_path = Config.get_pricing_db_path()
        
        # For SQLite, create directory if needed
        if Config.is_pricing_sqlite():
            db_dir = os.path.dirname(pricing_db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created pricing database directory: {db_dir}")
        
        # Create pricing table using SQLAlchemy
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(pricing_db_url)
            with engine.connect() as conn:
                # Create table with database-agnostic SQL
                if Config.is_pricing_sqlite():
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS aws_pricing (
                            sku TEXT PRIMARY KEY,
                            instance_type TEXT,
                            region TEXT,
                            price_per_hour REAL,
                            currency TEXT,
                            service TEXT,
                            raw_json TEXT
                        )
                    """))
                    # Create indexes for faster queries
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_pricing_lookup 
                        ON aws_pricing(instance_type, region, service)
                    """))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_pricing_instance_region 
                        ON aws_pricing(instance_type, region)
                    """))
                else:
                    # PostgreSQL version
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS aws_pricing (
                            sku VARCHAR(255) PRIMARY KEY,
                            instance_type VARCHAR(100),
                            region VARCHAR(50),
                            price_per_hour DECIMAL(10, 6),
                            currency VARCHAR(10),
                            service VARCHAR(50),
                            raw_json TEXT
                        )
                    """))
                    # Create index if not exists (PostgreSQL supports IF NOT EXISTS)
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_pricing_lookup 
                        ON aws_pricing(instance_type, region, service)
                    """))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_pricing_instance_region 
                        ON aws_pricing(instance_type, region)
                    """))
                conn.commit()
            logger.info(f"Pricing database initialized at {pricing_db_url}")
        except Exception as e:
            logger.error(f"Error initializing pricing database: {e}")
    
    def check_pricing_data_available(self) -> Dict[str, Any]:
        """Check if pricing data is available in the database using pooled connection."""
        pricing_db_path = Config.get_pricing_db_path()
        
        result = {
            'available': False,
            'total_records': 0,
            'services': [],
            'regions': [],
            'message': ''
        }
        
        # For SQLite, check if file exists
        if Config.is_pricing_sqlite() and not os.path.exists(pricing_db_path):
            result['message'] = f"Pricing database not found at {pricing_db_path}. Run pricing ETL to populate data."
            return result
        
        try:
            # Use pooled engine instead of creating new one
            engine = _get_pricing_engine()
            
            with engine.connect() as conn:
                # Get total count
                count_result = conn.execute(text("SELECT COUNT(*) FROM aws_pricing"))
                total = count_result.fetchone()[0]
                
                if total == 0:
                    result['message'] = "Pricing database is empty. Run pricing ETL to populate data."
                    return result
                
                # Get distinct services
                services_result = conn.execute(text("SELECT DISTINCT service FROM aws_pricing WHERE service IS NOT NULL"))
                services = [row[0] for row in services_result.fetchall()]
                
                # Get distinct regions
                regions_result = conn.execute(text("SELECT DISTINCT region FROM aws_pricing WHERE region IS NOT NULL"))
                regions = [row[0] for row in regions_result.fetchall()]
                
                result['available'] = True
                result['total_records'] = total
                result['services'] = services
                result['regions'] = regions
                result['message'] = f"Pricing data available: {total} records across {len(services)} services and {len(regions)} regions"
                
        except Exception as e:
            result['message'] = f"Error checking pricing data: {e}"
            logger.error(f"Error checking pricing data: {e}")
        
        return result
    
    def get_connection(self):
        """Get a database connection - returns SQLAlchemy connection"""
        return get_connection(self.database_url)
    
    def get_data_freshness(self, service_type: str) -> Dict:
        """Get data freshness information for a service"""
        # Use case-insensitive comparison
        row = self.fetch_one(
            'SELECT last_updated, next_scheduled, record_count, status FROM data_freshness WHERE UPPER(service_type) = UPPER(:service_type)',
            {"service_type": service_type}
        )
        if row:
            return {
                'last_updated': row[0],
                'next_scheduled': row[1],
                'record_count': row[2],
                'status': row[3]
            }
        
        # Fallback: Check raw_instances if data_freshness is empty
        count_row = self.fetch_one(
            'SELECT COUNT(*) as cnt FROM raw_instances WHERE UPPER(service_type) = UPPER(:service_type)',
            {"service_type": service_type}
        )
        if count_row and count_row[0] > 0:
            return {
                'last_updated': 'Unknown',
                'next_scheduled': 'Unknown',
                'record_count': count_row[0],
                'status': 'fresh'
            }
        return None
    
    def list_instances(self, service_type: str, region: str = None) -> List[Dict]:
        """List all instances from database for a given service type"""
        # Use case-insensitive comparison for service_type
        if region:
            rows = self.fetch_all(
                'SELECT * FROM raw_instances WHERE UPPER(service_type) = UPPER(:service_type) AND region = :region ORDER BY instance_id',
                {"service_type": service_type, "region": region}
            )
        else:
            rows = self.fetch_all(
                'SELECT * FROM raw_instances WHERE UPPER(service_type) = UPPER(:service_type) ORDER BY instance_id',
                {"service_type": service_type}
            )
        
        instances = []
        
        for row in rows:
            # Use _mapping for SQLAlchemy 2.x compatibility
            instance = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
            # Merge raw_data JSON fields into the instance dict for easy access
            if instance.get('raw_data'):
                try:
                    raw_data = json.loads(instance['raw_data'])
                    # Add raw_data fields to instance (size_gb, object_count, etc.)
                    for key, value in raw_data.items():
                        if key not in instance or instance[key] is None:
                            instance[key] = value
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse raw_data for {instance['instance_id']}")
            instances.append(instance)
        
        return instances

    def get_ebs_volumes_for_instance(self, instance_id: str) -> List[Dict]:
        """Get all EBS volumes attached to a specific EC2 instance"""
        rows = self.fetch_all(
            'SELECT * FROM raw_instances WHERE service_type = :service_type AND attached_instance_id = :instance_id',
            {"service_type": "EBS", "instance_id": instance_id}
        )
        volumes = []
        for row in rows:
            # Use _mapping for SQLAlchemy 2.x compatibility
            vol = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
            if vol.get('raw_data'):
                try:
                    raw_data = json.loads(vol['raw_data'])
                    for key, value in raw_data.items():
                        if key not in vol or vol[key] is None:
                            vol[key] = value
                except (json.JSONDecodeError, TypeError):
                    pass
            volumes.append(vol)
        return volumes

    def get_ebs_volumes_batch(self, instance_ids: List[str]) -> Dict[str, List[Dict]]:
        """Get all EBS volumes for multiple EC2 instances in a single query.
        
        This is more efficient than calling get_ebs_volumes_for_instance multiple times
        as it uses a single database connection and query.
        
        Args:
            instance_ids: List of EC2 instance IDs to fetch volumes for
            
        Returns:
            Dictionary mapping instance_id to list of attached volumes
        """
        if not instance_ids:
            return {}
        
        # Build parameterized query with IN clause
        placeholders = ', '.join([f':id_{i}' for i in range(len(instance_ids))])
        params = {f'id_{i}': iid for i, iid in enumerate(instance_ids)}
        params['service_type'] = 'EBS'
        
        query = f'''
            SELECT * FROM raw_instances 
            WHERE service_type = :service_type 
            AND attached_instance_id IN ({placeholders})
        '''
        
        rows = self.fetch_all(query, params)
        
        # Group volumes by instance_id
        result = {iid: [] for iid in instance_ids}
        for row in rows:
            vol = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
            if vol.get('raw_data'):
                try:
                    raw_data = json.loads(vol['raw_data'])
                    for key, value in raw_data.items():
                        if key not in vol or vol[key] is None:
                            vol[key] = value
                except (json.JSONDecodeError, TypeError):
                    pass
            attached_id = vol.get('attached_instance_id')
            if attached_id in result:
                result[attached_id].append(vol)
        
        return result

    def get_instance_tags(self, instance_id: str) -> Dict[str, str]:
        """Get all tags for a specific instance from the separate tags table"""
        rows = self.fetch_all(
            'SELECT tag_key, tag_value FROM instance_tags WHERE instance_id = :instance_id ORDER BY tag_key',
            {"instance_id": instance_id}
        )
        return {row[0]: row[1] for row in rows}

    def get_cloudwatch_metrics(self, instance_id: str, hours: int = 24) -> Dict:
        """Get CloudWatch metrics from database for an instance"""
        # Calculate time window
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)
        
        rows = self.fetch_all(
            '''
            SELECT metric_name, metric_value, timestamp, unit, statistics
            FROM raw_metrics
            WHERE instance_id = :instance_id AND timestamp >= :start_time
            ORDER BY metric_name, timestamp
            ''',
            {"instance_id": instance_id, "start_time": start_time.isoformat()}
        )
        
        metrics_dict = {}
        
        for row in rows:
            metric_name = row[0]  # metric_name
            if metric_name not in metrics_dict:
                metrics_dict[metric_name] = {'datapoints': [], 'values': []}
            
            # Handle timestamp - could be datetime object or string depending on database
            timestamp_raw = row[2]
            if isinstance(timestamp_raw, datetime):
                timestamp = timestamp_raw
            elif isinstance(timestamp_raw, str):
                timestamp = datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
            else:
                timestamp = datetime.now(timezone.utc)  # fallback
            
            datapoint = {
                'Timestamp': timestamp,
                'Average': row[1],  # metric_value
                'Unit': row[3]  # unit
            }
            
            if row[4]:  # statistics
                try:
                    stats = json.loads(row[4])
                    datapoint.update(stats)
                except (json.JSONDecodeError, TypeError):
                    pass
            
            metrics_dict[metric_name]['datapoints'].append(datapoint)
            metrics_dict[metric_name]['values'].append(row[1])  # metric_value
        
        result = {}
        for metric_name, data in metrics_dict.items():
            values = data['values']
            result[metric_name] = {
                'current': values[-1] if values else 0,
                'average': sum(values) / len(values) if values else 0,
                'max': max(values) if values else 0,
                'min': min(values) if values else 0,
                'datapoints': data['datapoints']
            }
        
        return result

    def get_cloudwatch_metrics_batch(self, instance_ids: List[str], hours: int = 24) -> Dict[str, Dict]:
        """Get CloudWatch metrics for multiple instances in a single query for better performance"""
        if not instance_ids:
            return {}
        
        # Calculate time window
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)
        
        # Single query for all instances using IN clause
        placeholders = ', '.join([f':id{i}' for i in range(len(instance_ids))])
        params = {f'id{i}': iid for i, iid in enumerate(instance_ids)}
        params['start_time'] = start_time.isoformat()
        
        query = f'''
            SELECT instance_id, metric_name, metric_value, timestamp, unit, statistics
            FROM raw_metrics
            WHERE instance_id IN ({placeholders}) AND timestamp >= :start_time
            ORDER BY instance_id, metric_name, timestamp
        '''
        
        rows = self.fetch_all(query, params)
        
        # Group by instance_id
        results = {iid: {} for iid in instance_ids}
        
        for row in rows:
            instance_id = row[0]
            metric_name = row[1]
            
            if metric_name not in results[instance_id]:
                results[instance_id][metric_name] = {'datapoints': [], 'values': []}
            
            # Handle timestamp
            timestamp_raw = row[3]
            if isinstance(timestamp_raw, datetime):
                timestamp = timestamp_raw
            elif isinstance(timestamp_raw, str):
                timestamp = datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
            else:
                timestamp = datetime.now(timezone.utc)
            
            datapoint = {
                'Timestamp': timestamp,
                'Average': row[2],  # metric_value
                'Unit': row[4]  # unit
            }
            
            if row[5]:  # statistics
                try:
                    stats = json.loads(row[5])
                    datapoint.update(stats)
                except (json.JSONDecodeError, TypeError):
                    pass
            
            results[instance_id][metric_name]['datapoints'].append(datapoint)
            results[instance_id][metric_name]['values'].append(row[2])
        
        # Process each instance's metrics
        for instance_id in instance_ids:
            result = {}
            for metric_name, data in results[instance_id].items():
                values = data['values']
                result[metric_name] = {
                    'current': values[-1] if values else 0,
                    'average': sum(values) / len(values) if values else 0,
                    'max': max(values) if values else 0,
                    'min': min(values) if values else 0,
                    'datapoints': data['datapoints']
                }
            results[instance_id] = result
        
        return results

    def get_analysis_cache(self, instance_id: str) -> Optional[Dict]:
        """Get cached analysis results for an instance"""
        row = self.fetch_one(
            'SELECT * FROM analysis_cache WHERE instance_id = :instance_id',
            {"instance_id": instance_id}
        )
        
        if row:
            # Use _mapping for SQLAlchemy 2.x compatibility
            analysis = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
            for field in ['idle_reasons', 'active_reasons', 'indicators']:
                if analysis.get(field):
                    try:
                        analysis[field] = json.loads(analysis[field])
                    except (json.JSONDecodeError, TypeError):
                        analysis[field] = []
            # Parse timestamp
            if analysis.get('last_activity_date') and isinstance(analysis['last_activity_date'], str):
                analysis['last_activity_date'] = datetime.fromisoformat(analysis['last_activity_date'].replace('Z', '+00:00'))
            return analysis
        return None

    def truncate_and_reload(self, service_type: str = None, aws_environment: str = 'Default', regions: List[str] = None):
        """Truncate tables and trigger ETL reload with lock safety
        
        Args:
            service_type: Optional service type to reload (e.g., 'RDS', 'EC2', 'EBS')
            aws_environment: AWS environment name
            regions: List of regions to fetch data from. If None, fetches all available regions.
        """
        from etl.orchestrator import ETLOrchestrator
        orchestrator = ETLOrchestrator(database_url=self.database_url)
        
        # BUG FIX: Check lock BEFORE truncating
        if orchestrator.is_etl_locked():
            logger.warning("ETL is currently locked. Cannot truncate and reload.")
            raise Exception("ETL process is already running. Please Wait.")

        try:
            if service_type:
                # Delete in correct order to respect foreign key constraints
                self.execute('DELETE FROM raw_metrics WHERE instance_id IN (SELECT instance_id FROM raw_instances WHERE service_type = :service_type)', {"service_type": service_type})
                self.execute('DELETE FROM analysis_cache WHERE service_type = :service_type', {"service_type": service_type})
                self.execute('DELETE FROM instance_tags WHERE instance_id IN (SELECT instance_id FROM raw_instances WHERE service_type = :service_type)', {"service_type": service_type})
                self.execute('DELETE FROM raw_instances WHERE service_type = :service_type', {"service_type": service_type})
                self.execute('DELETE FROM data_freshness WHERE service_type = :service_type', {"service_type": service_type})
            else:
                # Delete in correct order to respect foreign key constraints
                self.execute('DELETE FROM raw_metrics')
                self.execute('DELETE FROM analysis_cache')
                self.execute('DELETE FROM instance_tags')
                self.execute('DELETE FROM raw_instances')
                self.execute('DELETE FROM data_freshness')
            logger.info(f"Truncated tables for service_type: {service_type or 'ALL'}")
        except Exception as e:
            logger.error(f"Error truncating tables: {e}")
            raise

        # Now trigger the reload - if regions is None, orchestrator will fetch all regions
        result = orchestrator.run_etl(
            run_type='manual', 
            triggered_by='streamlit_refresh', 
            services=[service_type] if service_type else None,
            regions=regions,
            aws_environment=aws_environment
        )
        if result['status'] != 'success':
            error_msg = f"ETL failed: {result.get('error_message', 'Unknown error')}"
            logger.error(error_msg)
            raise Exception(error_msg)
            
        logger.info(f"ETL reload completed successfully: {result['records_loaded']} records loaded")

    def get_pricing(self, instance_type: str, region: str, service: str = 'EC2',
                   operating_system: str = None, tenancy: str = None,
                   database_engine: str = None, deployment_option: str = None,
                   license_model: str = None) -> Optional[float]:
        """
        Fetch hourly price for a given instance type, region, and service.
        Uses short TTL cache (30s) for performance while ensuring reasonable freshness.
        
        Uses pooled database connection for better performance.
        Uses MIN(price_per_hour) to always get the lowest available price.
        
        Handles multiple format variations:
        - RDS: Tries both with and without 'db.' prefix (e.g., 'db.t3.medium' and 't3.medium')
        - EC2: Tries case variations
        
        Args:
            instance_type: The instance type (e.g., 't3.medium', 'db.r5.large')
            region: The AWS region code (e.g., 'us-east-1')
            service: The AWS service ('EC2', 'RDS')
            operating_system: For EC2 - operating system (Linux, Windows, etc.)
            tenancy: For EC2 - tenancy (shared, dedicated, host)
            database_engine: For RDS - database engine (MySQL, PostgreSQL, etc.)
            deployment_option: For RDS - Single-AZ or Multi-AZ
            license_model: For RDS - license model (included, BYOL)
        """
        # Normalize operating_system to match database values
        # AWS pricing database uses: 'Linux', 'Windows', 'SUSE', 'RHEL', etc.
        # But EC2 API returns: 'Linux/UNIX', 'Windows with SQL Server', etc.
        if operating_system:
            os_mapping = {
                'Linux/UNIX': 'Linux',
                'linux': 'Linux',
                'LINUX': 'Linux',
                'Windows with SQL Server Standard': 'Windows',
                'Windows with SQL Server Enterprise': 'Windows',
                'Windows with SQL Server Web': 'Windows',
                'RHEL': 'RHEL',
                'Red Hat Enterprise Linux': 'RHEL',
                'SUSE': 'SUSE',
            }
            operating_system = os_mapping.get(operating_system, operating_system)
        
        # Validate inputs
        if not instance_type or not region:
            logger.warning(f"Invalid pricing request: instance_type={instance_type}, region={region}")
            return None
        
        # Build cache key from all parameters
        cache_key = (
            instance_type, region, service,
            operating_system or 'any',
            tenancy or 'any',
            database_engine or 'any',
            deployment_option or 'any',
            license_model or 'any'
        )
        
        # Check TTL cache first
        if cache_key in _pricing_ttl_cache:
            return _pricing_ttl_cache[cache_key]
        
        # Build parameter filters for query
        os_key = operating_system or 'any'
        tenancy_key = tenancy or 'any'
        engine_key = database_engine or 'any'
        deploy_key = deployment_option or 'any'
        license_key = license_model or 'any'
        
        pricing_db_path = Config.get_pricing_db_path()
        
        # For SQLite, check if file exists
        if Config.is_pricing_sqlite() and not os.path.exists(pricing_db_path):
            logger.warning(f"Pricing database not found at {pricing_db_path}. Run pricing ETL to populate data.")
            return None
        
        # Map region code to location name for AWS pricing lookup
        from core.constants import AWS_LOCATION_TO_REGION
        location_name = None
        for loc, reg in AWS_LOCATION_TO_REGION.items():
            if reg == region:
                location_name = loc
                break
        
        # If no location found, use region code directly
        if not location_name:
            logger.debug(f"No location mapping found for region {region}, using region code directly")
        
        # Prepare multiple instance_type variations to try based on service
        instance_types_to_try = [instance_type]
        
        if service == 'RDS':
            # RDS instances may be stored with or without 'db.' prefix
            # UI strips prefix before calling, but pricing DB might have it WITH prefix
            if instance_type.startswith('db.'):
                instance_types_to_try.append(instance_type[3:])  # Without 'db.'
            else:
                instance_types_to_try.append(f'db.{instance_type}')  # With 'db.'
        
        elif service == 'EC2':
            # Try case variations for EC2
            if instance_type != instance_type.lower():
                instance_types_to_try.append(instance_type.lower())
            if instance_type != instance_type.upper():
                instance_types_to_try.append(instance_type.upper())
        
        # Use pooled engine for pricing database
        engine = _get_pricing_engine()
        
        try:
            with engine.connect() as conn:
                has_service = self._ensure_pricing_service_column_sqlalchemy(conn)
                
                # Check if extended columns exist
                columns = self._get_pricing_columns(conn)
                has_extended_cols = all(col in columns for col in ['operating_system', 'tenancy', 'database_engine', 'deployment_option'])
                
                # Try all combinations of instance_type variations and region values
                # Priority: location_name first (if found), then region code
                regions_to_try = []
                if location_name:
                    regions_to_try.append(location_name)
                regions_to_try.append(region)  # Always try region code as fallback
                
                for inst_type in instance_types_to_try:
                    for region_value in regions_to_try:
                        if not region_value:  # Skip None values
                            continue
                        
                        # Build query with extended filters if columns exist
                        if has_extended_cols and (operating_system or tenancy or database_engine or deployment_option or license_model):
                            # Build WHERE clause with filters
                            where_clauses = ["instance_type = :inst_type", "region = :region", "price_per_hour > 0"]
                            params = {"inst_type": inst_type, "region": region_value}
                            
                            if service:
                                where_clauses.append("service = :service")
                                params["service"] = service
                            
                            # Add optional filters - STRICT matching (no NULL fallback for specific values)
                            # When a specific value is provided, ONLY match that value
                            # NULL entries are only used when no filter is specified (generic pricing)
                            if operating_system:
                                where_clauses.append("operating_system = :operating_system")
                                params["operating_system"] = operating_system
                            if tenancy:
                                where_clauses.append("tenancy = :tenancy")
                                params["tenancy"] = tenancy
                            if database_engine:
                                where_clauses.append("database_engine = :database_engine")
                                params["database_engine"] = database_engine
                            if deployment_option:
                                where_clauses.append("deployment_option = :deployment_option")
                                params["deployment_option"] = deployment_option
                            if license_model:
                                where_clauses.append("license_model = :license_model")
                                params["license_model"] = license_model
                            
                            # Use MIN(price_per_hour) to get the lowest On-Demand price for accurate cost savings calculation
                            # This ensures deterministic pricing regardless of database ordering
                            query = text("SELECT MIN(price_per_hour) FROM aws_pricing WHERE " + " AND ".join(where_clauses))
                        elif has_service:
                            query = text("SELECT MIN(price_per_hour) FROM aws_pricing WHERE instance_type = :inst_type AND region = :region AND service = :service AND price_per_hour > 0")
                            params = {"inst_type": inst_type, "region": region_value, "service": service}
                        else:
                            query = text("SELECT MIN(price_per_hour) FROM aws_pricing WHERE instance_type = :inst_type AND region = :region AND price_per_hour > 0")
                            params = {"inst_type": inst_type, "region": region_value}
                        
                        result = conn.execute(query, params)
                        row = result.fetchone()
                        if row and row[0] is not None:
                            logger.debug(f"Pricing found: {service} {inst_type} in {region_value} = ${row[0]}/hour")
                            price = row[0]
                            # Store in TTL cache before returning
                            _pricing_ttl_cache[cache_key] = price
                            return price
                        
                        # FALLBACK: If strict matching returns no results, try with NULL values (generic pricing)
                        # This handles cases where engine-specific pricing doesn't exist in the database
                        if has_extended_cols and (database_engine or operating_system or tenancy or deployment_option or license_model):
                            fallback_clauses = ["instance_type = :inst_type", "region = :region", "price_per_hour > 0"]
                            fallback_params = {"inst_type": inst_type, "region": region_value}
                            
                            if service:
                                fallback_clauses.append("service = :service")
                                fallback_params["service"] = service
                            
                            # Only include filters where value is None (use NULL matching for fallback)
                            if not operating_system:
                                fallback_clauses.append("(operating_system IS NULL OR operating_system = 'any')")
                            if not tenancy:
                                fallback_clauses.append("(tenancy IS NULL OR tenancy = 'any')")
                            if not database_engine:
                                fallback_clauses.append("(database_engine IS NULL OR database_engine = 'any')")
                            if not deployment_option:
                                fallback_clauses.append("(deployment_option IS NULL OR deployment_option = 'any')")
                            if not license_model:
                                fallback_clauses.append("(license_model IS NULL OR license_model = 'any')")
                            
                            fallback_query = text("SELECT MIN(price_per_hour) FROM aws_pricing WHERE " + " AND ".join(fallback_clauses))
                            fallback_result = conn.execute(fallback_query, fallback_params)
                            fallback_row = fallback_result.fetchone()
                            if fallback_row and fallback_row[0] is not None:
                                logger.debug(f"Pricing found (fallback): {service} {inst_type} in {region_value} = ${fallback_row[0]}/hour (generic pricing)")
                                price = fallback_row[0]
                                _pricing_ttl_cache[cache_key] = price
                                return price
                
                logger.warning(f"No pricing found for {service} {instance_type} in {region}. Tried variations: {instance_types_to_try} across regions: {regions_to_try}")
                # Cache the not-found result too (with None value)
                _pricing_ttl_cache[cache_key] = None
                return None
                
        except Exception as e:
            logger.error(f"Pricing database error: {e}. Run pricing ETL to initialize.")
            # Don't cache errors - might be transient
            return None

    def _ensure_pricing_service_column_sqlalchemy(self, conn) -> bool:
        """Ensure the aws_pricing table has the service column (SQLAlchemy version)"""
        if self._pricing_has_service_column is not None:
            return self._pricing_has_service_column
        
        from sqlalchemy import text
        from sqlalchemy import inspect
        
        # Use inspector from the engine, not the connection
        try:
            # Get the underlying engine from the connection
            if hasattr(conn, 'engine'):
                inspector = inspect(conn.engine)
            elif hasattr(conn, 'connection') and hasattr(conn.connection, 'engine'):
                inspector = inspect(conn.connection.engine)
            else:
                # Fallback: try direct query
                try:
                    conn.execute(text("SELECT service FROM aws_pricing LIMIT 1"))
                    conn.commit()
                    has_service = True
                    self._pricing_has_service_column = has_service
                    return has_service
                except Exception:
                    has_service = False
                    self._pricing_has_service_column = has_service
                    return has_service
            
            columns = [col['name'] for col in inspector.get_columns('aws_pricing')]
            has_service = 'service' in columns
        except Exception:
            # Fallback: try to query and see if service column exists
            try:
                conn.execute(text("SELECT service FROM aws_pricing LIMIT 1"))
                conn.commit()
                has_service = True
            except Exception:
                has_service = False
        
        if not has_service:
            try:
                if Config.is_pricing_sqlite():
                    conn.execute(text("ALTER TABLE aws_pricing ADD COLUMN service TEXT"))
                else:
                    conn.execute(text("ALTER TABLE aws_pricing ADD COLUMN service VARCHAR(50)"))
                conn.commit()
                has_service = True
            except Exception:
                pass
                
        self._pricing_has_service_column = has_service
        return has_service

    def _ensure_pricing_service_column(self, conn) -> bool:
        """Ensure the aws_pricing table has the service column (SQLite only - kept for backwards compatibility)"""
        if self._pricing_has_service_column is not None:
            return self._pricing_has_service_column
            
        cursor = conn.execute("PRAGMA table_info(aws_pricing)")
        columns = [row[1] for row in cursor.fetchall()]  # column name is at index 1 in PRAGMA table_info
        has_service = 'service' in columns
        
        if not has_service:
            try:
                conn.execute("ALTER TABLE aws_pricing ADD COLUMN service TEXT")
                has_service = True
            except Exception:
                pass
                
        self._pricing_has_service_column = has_service
        return has_service
    
    def _get_pricing_columns(self, conn) -> List[str]:
        """Get list of column names from aws_pricing table"""
        from sqlalchemy import inspect
        
        try:
            # Get the underlying engine from the connection
            if hasattr(conn, 'engine'):
                inspector = inspect(conn.engine)
            elif hasattr(conn, 'connection') and hasattr(conn.connection, 'engine'):
                inspector = inspect(conn.connection.engine)
            else:
                return []
            
            columns = [col['name'] for col in inspector.get_columns('aws_pricing')]
            return columns
        except Exception:
            return []

    def list_ebs_volumes(self, region: str = None) -> List[Dict]:
        """List all EBS volumes from database"""
        if region:
            rows = self.fetch_all(
                'SELECT * FROM raw_instances WHERE service_type = :service_type AND region = :region ORDER BY volume_id',
                {"service_type": "EBS", "region": region}
            )
        else:
            rows = self.fetch_all(
                'SELECT * FROM raw_instances WHERE service_type = :service_type ORDER BY volume_id',
                {"service_type": "EBS"}
            )
        
        volumes = []
        
        for row in rows:
            # Use _mapping for SQLAlchemy 2.x compatibility
            volume = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
            if volume.get('raw_data'):
                try:
                    raw_data = json.loads(volume['raw_data'])
                    for key, value in raw_data.items():
                        if key not in volume or volume[key] is None:
                            volume[key] = value
                except json.JSONDecodeError:
                    pass
            volumes.append(volume)
        
        return volumes

    def get_ebs_volumes_by_instance(self, instance_id: str) -> List[Dict]:
        """Get all EBS volumes attached to a specific EC2 instance"""
        rows = self.fetch_all(
            'SELECT * FROM raw_instances WHERE service_type = :service_type AND attached_instance_id = :instance_id',
            {"service_type": "EBS", "instance_id": instance_id}
        )
        
        volumes = []
        
        for row in rows:
            # Use _mapping for SQLAlchemy 2.x compatibility
            volume = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
            if volume.get('raw_data'):
                try:
                    volume.update(json.loads(volume['raw_data']))
                except (json.JSONDecodeError, TypeError):
                    pass
            volumes.append(volume)
        
        return volumes

    def get_ebs_costs_by_environment(self) -> Dict:
        """Get aggregated EBS costs grouped by environment tag"""
        rows = self.fetch_all('''
            SELECT 
                environment_tag as environment,
                COUNT(*) as volume_count,
                SUM(size_gb) as total_size_gb,
                SUM(monthly_cost) as monthly_cost
            FROM raw_instances 
            WHERE service_type = 'EBS'
            GROUP BY environment_tag
        ''')
        
        env_costs = {}
        for row in rows:
            env = row['environment'] or 'Unknown'
            monthly = row['monthly_cost'] or 0
            env_costs[env] = {
                'volume_count': row['volume_count'],
                'total_size_gb': row['total_size_gb'] or 0,
                'monthly_cost': monthly,
                'daily_cost': monthly / DAYS_PER_MONTH,
                'yearly_cost': monthly * 12
            }
        
        return env_costs

    def get_ebs_price(self, volume_type: str, region: str) -> float:
        """Get EBS price per GB per month"""
        from etl.ebs_pricing_loader import EBSPricingLoader
        
        try:
            loader = EBSPricingLoader(database_url=self.database_url)
            return loader.get_ebs_price(volume_type, region)
        except Exception as e:
            logger.warning(f"Failed to get EBS price: {e}")
            return DEFAULT_EBS_STORAGE_COST  # Default fallback


def create_data_provider(db_path: str = None, database_url: str = None) -> ETLDataProvider:
    """Factory function to create an ETL data provider"""
    return ETLDataProvider(db_path=db_path, database_url=database_url)
