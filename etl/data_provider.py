import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from functools import lru_cache
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from core.config import Config
from core.logger import setup_logger
from etl.base_db import BaseDatabase, DatabaseType
from database.db_utils import get_engine, get_connection

logger = setup_logger(__name__)

# =============================================================================
# PERFORMANCE OPTIMIZATIONS
# =============================================================================

# Cache for pricing data (TTL = 1 hour - pricing rarely changes)
_PRICING_CACHE: Dict[str, Any] = {}
_PRICING_CACHE_TTL = 3600  # 1 hour (increased from 5 minutes)

# Class-level pricing engine with connection pooling
_pricing_engine: Optional[Engine] = None

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
    - LRU caching for pricing lookups
    - Batch query support for metrics
    - Increased cache TTL for pricing data
    """
    
    def __init__(self, db_path: str = None, database_url: str = None, use_cache: bool = True):
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
        # Enable caching
        self._use_cache = use_cache
        self._init_cache()
    
    def _init_cache(self):
        """Initialize cache variables"""
        global _PRICING_CACHE
        _PRICING_CACHE = {
            'pricing_data': {},
            'instances': {},
            'last_updated': time.time()
        }
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if not self._use_cache:
            return None
        
        cache_entry = _PRICING_CACHE.get(key)
        if cache_entry is None:
            return None
        
        # Check if cache is expired
        if time.time() - _PRICING_CACHE.get('last_updated', 0) > _PRICING_CACHE_TTL:
            return None
        
        return cache_entry
    
    def _set_cache(self, key: str, value: Any) -> None:
        """Set value in cache"""
        if not self._use_cache:
            return
        
        global _PRICING_CACHE
        _PRICING_CACHE[key] = value
        _PRICING_CACHE['last_updated'] = time.time()
    
    def invalidate_cache(self) -> None:
        """Invalidate all caches"""
        global _PRICING_CACHE
        _PRICING_CACHE = {
            'pricing_data': {},
            'instances': {},
            'last_updated': time.time()
        }
        # Also clear LRU cache
        self._get_pricing_cached.cache_clear()
        logger.info("Cache invalidated")
        
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
        row = self.fetch_one(
            'SELECT last_updated, next_scheduled, record_count, status FROM data_freshness WHERE service_type = :service_type',
            {"service_type": service_type}
        )
        if row:
            return {
                'last_updated': row[0],
                'next_scheduled': row[1],
                'record_count': row[2],
                'status': row[3]
            }
        return None
    
    def list_instances(self, service_type: str, region: str = None) -> List[Dict]:
        """List all instances from database for a given service type"""
        if region:
            rows = self.fetch_all(
                'SELECT * FROM raw_instances WHERE service_type = :service_type AND region = :region ORDER BY instance_id',
                {"service_type": service_type, "region": region}
            )
        else:
            rows = self.fetch_all(
                'SELECT * FROM raw_instances WHERE service_type = :service_type ORDER BY instance_id',
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

    def truncate_and_reload(self, service_type: str = None, aws_environment: str = 'Default'):
        """Truncate tables and trigger ETL reload with lock safety"""
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

        # Now trigger the reload
        result = orchestrator.run_etl(
            run_type='manual', 
            triggered_by='streamlit_refresh', 
            services=[service_type] if service_type else None,
            aws_environment=aws_environment
        )
        if result['status'] != 'success':
            error_msg = f"ETL failed: {result.get('error_message', 'Unknown error')}"
            logger.error(error_msg)
            raise Exception(error_msg)
            
        logger.info(f"ETL reload completed successfully: {result['records_loaded']} records loaded")

    def get_pricing(self, instance_type: str, region: str, service: str = 'EC2') -> Optional[float]:
        """
        Fetch hourly price for a given instance type, region, and service.
        Results are cached for 1 hour to improve performance.
        
        Uses pooled database connection for better performance.
        
        Handles multiple format variations:
        - RDS: Tries both with and without 'db.' prefix (e.g., 'db.t3.medium' and 't3.medium')
        - EC2: Tries case variations
        - S3: Tries with and without 'Storage' suffix
        """
        # Validate inputs
        if not instance_type or not region:
            logger.warning(f"Invalid pricing request: instance_type={instance_type}, region={region}")
            return None
        
        # Check cache first
        cache_key = f"{instance_type}:{region}:{service}"
        cached_price = self._get_from_cache(f"pricing:{cache_key}")
        if cached_price is not None:
            logger.debug(f"Using cached price for {cache_key}")
            return cached_price
        
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
        
        elif service == 'S3':
            # Try storage class name variations
            if 'Storage' not in instance_type and instance_type:
                instance_types_to_try.append(f'{instance_type}Storage')
            if instance_type.endswith('Storage'):
                instance_types_to_try.append(instance_type[:-7])  # Without 'Storage'
        
        # Use pooled engine for pricing database
        engine = _get_pricing_engine()
        
        try:
            with engine.connect() as conn:
                has_service = self._ensure_pricing_service_column_sqlalchemy(conn)
                
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
                        
                        # Add filter for non-zero prices to avoid getting $0.00 pricing entries
                        if has_service:
                            query = text("SELECT price_per_hour FROM aws_pricing WHERE instance_type = :inst_type AND region = :region AND service = :service AND price_per_hour > 0 LIMIT 1")
                            params = {"inst_type": inst_type, "region": region_value, "service": service}
                        else:
                            query = text("SELECT price_per_hour FROM aws_pricing WHERE instance_type = :inst_type AND region = :region AND price_per_hour > 0 LIMIT 1")
                            params = {"inst_type": inst_type, "region": region_value}
                        
                        result = conn.execute(query, params)
                        row = result.fetchone()
                        if row and row[0] is not None:
                            logger.debug(f"Pricing found: {service} {inst_type} in {region_value} = ${row[0]}/hour")
                            price = row[0]
                            # Cache the result
                            self._set_cache(f"pricing:{cache_key}", price)
                            return price
                
                logger.warning(f"No pricing found for {service} {instance_type} in {region}. Tried variations: {instance_types_to_try} across regions: {regions_to_try}")
                # Cache the "not found" result as well to avoid repeated lookups
                self._set_cache(f"pricing:{cache_key}", None)
                return None
                
        except Exception as e:
            logger.error(f"Pricing database error: {e}. Run pricing ETL to initialize.")
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
