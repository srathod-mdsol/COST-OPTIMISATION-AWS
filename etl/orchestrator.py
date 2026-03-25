import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
import threading
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from core.logger import setup_logger
from core.config import Config
from core.constants import LOCK_TIMEOUT_MINUTES, MAX_CONCURRENT_WORKERS, CLOUDWATCH_TIMEOUT_SECONDS, PRICING_BATCH_SIZE
from etl.base_db import BaseDatabase
from database.db_utils import DatabaseType

logger = setup_logger(__name__)


class ETLOrchestrator(BaseDatabase):
    """Orchestrates ETL process to extract AWS resource data and load into database.
    
    Supports multiple database backends: PostgreSQL, MySQL, Oracle, MSSQL, SQLite.
    """
    
    CLOUDWATCH_TIMEOUT_SECONDS = CLOUDWATCH_TIMEOUT_SECONDS
    MAX_CONCURRENT_WORKERS = MAX_CONCURRENT_WORKERS
    LOCK_TIMEOUT_MINUTES = LOCK_TIMEOUT_MINUTES
    
    def __init__(self, db_path: str = None, database_url: str = None):
        """Initialize ETL Orchestrator.
        
        Args:
            db_path: Legacy SQLite path (for backward compatibility)
            database_url: SQLAlchemy database URL (takes precedence)
        """
        # Determine database URL
        if database_url:
            url = database_url
        elif db_path:
            url = f"sqlite:///{db_path}"
        else:
            url = Config.DATABASE_URL or f"sqlite:///{Config.ETL_DB_PATH}"
        
        super().__init__(database_url=url)
        self.db_path = db_path or Config.ETL_DB_PATH  # Keep for backward compatibility
        self._ensure_schema()

    def _get_aws_clients(self, service_name: str, region: str, aws_environment: str):
        """Helper to get boto3 clients with error handling"""
        creds = Config.get_aws_credentials(aws_environment)
        client_kwargs = {'region_name': region}
        if creds.get('aws_access_key_id'):
            client_kwargs['aws_access_key_id'] = creds['aws_access_key_id']
            client_kwargs['aws_secret_access_key'] = creds['aws_secret_access_key']
        if creds.get('aws_session_token'):
            client_kwargs['aws_session_token'] = creds['aws_session_token']
            
        try:
            client = boto3.client(service_name, **client_kwargs)
            cw = boto3.client('cloudwatch', **client_kwargs)
            return client, cw
        except (NoCredentialsError, PartialCredentialsError) as e:
            logger.error(f"AWS Credential error for environment '{aws_environment}': {str(e)}")
            raise Exception(f"AWS Credentials for '{aws_environment}' are missing or incomplete.")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'ExpiredToken':
                logger.error(f"AWS Session Token for '{aws_environment}' has expired.")
                raise Exception(f"AWS Session for '{aws_environment}' has expired.")
            raise

    def get_all_aws_regions(self, aws_environment: str = 'Default') -> List[str]:
        """Discover all available AWS regions using boto3 Session.
        
        Uses session.get_available_regions() to get regions for EC2 and RDS
        services and returns a combined unique list of all regions.
        Regions are cached in the aws_regions table for faster access.
        
        Args:
            aws_environment: AWS environment name for credentials
            
        Returns:
            Sorted list of unique region names
        """
        from core.constants import AWS_REGIONS  # Fallback list
        
        # First, try to get regions from the database cache
        try:
            cached_regions = self.fetch_all(
                "SELECT region_name FROM aws_regions WHERE is_enabled = TRUE ORDER BY region_name"
            )
            if cached_regions and len(cached_regions) > 0:
                logger.info(f"Using {len(cached_regions)} cached regions from database")
                return [r['region_name'] for r in cached_regions]
        except Exception as e:
            logger.debug(f"Could not fetch regions from cache: {e}")
        
        # Discover regions from AWS API
        try:
            creds = Config.get_aws_credentials(aws_environment)
            session_kwargs = {}
            if creds.get('aws_access_key_id'):
                session_kwargs['aws_access_key_id'] = creds['aws_access_key_id']
                session_kwargs['aws_secret_access_key'] = creds['aws_secret_access_key']
            if creds.get('aws_session_token'):
                session_kwargs['aws_session_token'] = creds['aws_session_token']
            
            # Create a session - use us-east-1 as default region for the session
            session_kwargs['region_name'] = 'us-east-1'
            session = boto3.Session(**session_kwargs)
            
            # Get regions for each service we use
            all_regions = set()
            for service in ['ec2', 'rds']:
                try:
                    regions = session.get_available_regions(service)
                    all_regions.update(regions)
                except Exception as e:
                    logger.warning(f"Could not get regions for service {service}: {e}")
            
            if all_regions:
                logger.info(f"Discovered {len(all_regions)} AWS regions")
                sorted_regions = sorted(list(all_regions))
                
                # Store discovered regions in the database
                self._store_discovered_regions(sorted_regions)
                
                return sorted_regions
            else:
                logger.warning("No regions discovered, using fallback list")
                return AWS_REGIONS
                
        except Exception as e:
            logger.warning(f"Error discovering AWS regions: {e}. Using fallback list.")
            from core.constants import AWS_REGIONS
            return AWS_REGIONS

    def _store_discovered_regions(self, regions: List[str]):
        """Store discovered regions in the aws_regions table.
        
        Args:
            regions: List of region names to store
        """
        try:
            current_ts = datetime.now(timezone.utc).isoformat()
            
            # Determine region groups based on region name prefixes
            def get_region_group(region_name: str) -> str:
                if region_name.startswith('us-'):
                    return 'Americas'
                elif region_name.startswith('eu-'):
                    return 'Europe'
                elif region_name.startswith('ap-'):
                    return 'Asia Pacific'
                elif region_name.startswith('sa-'):
                    return 'South America'
                elif region_name.startswith('ca-'):
                    return 'Canada'
                elif region_name.startswith('me-'):
                    return 'Middle East'
                elif region_name.startswith('af-'):
                    return 'Africa'
                else:
                    return 'Other'
            
            for region in regions:
                region_group = get_region_group(region)
                
                # Use UPSERT pattern - insert or update
                if self.db_type == DatabaseType.POSTGRESQL:
                    self.execute("""
                        INSERT INTO aws_regions (region_name, region_group, is_enabled, discovered_at, last_seen_at)
                        VALUES (:region, :region_group, TRUE, :ts, :ts)
                        ON CONFLICT (region_name) DO UPDATE SET last_seen_at = :ts, is_enabled = TRUE
                    """, {"region": region, "region_group": region_group, "ts": current_ts})
                elif self.db_type == DatabaseType.MYSQL:
                    self.execute("""
                        INSERT INTO aws_regions (region_name, region_group, is_enabled, discovered_at, last_seen_at)
                        VALUES (:region, :region_group, TRUE, :ts, :ts)
                        ON DUPLICATE KEY UPDATE last_seen_at = :ts, is_enabled = TRUE
                    """, {"region": region, "region_group": region_group, "ts": current_ts})
                else:
                    # SQLite and others - use simpler approach
                    existing = self.fetch_value(
                        "SELECT COUNT(*) FROM aws_regions WHERE region_name = :region",
                        {"region": region}
                    )
                    if existing == 0:
                        self.execute("""
                            INSERT INTO aws_regions (region_name, region_group, is_enabled, discovered_at, last_seen_at)
                            VALUES (:region, :region_group, TRUE, :ts, :ts)
                        """, {"region": region, "region_group": region_group, "ts": current_ts})
                    else:
                        self.execute("""
                            UPDATE aws_regions SET last_seen_at = :ts, is_enabled = TRUE WHERE region_name = :region
                        """, {"region": region, "ts": current_ts})
            
            logger.info(f"Stored {len(regions)} regions in aws_regions table")
            
        except Exception as e:
            logger.warning(f"Error storing regions in database: {e}")

    def _ensure_schema(self):
        """Ensure database schema and lock table exists.
        
        This method creates all required tables with database-agnostic SQL.
        Supports PostgreSQL, MySQL, Oracle, MSSQL, and SQLite.
        """
        # Get database-specific types
        auto_inc = self.get_auto_increment_type()
        text_type = self.get_text_type()
        timestamp_type = self.get_timestamp_type()
        boolean_type = self.get_boolean_type()
        current_ts = self.get_current_timestamp()
        
        # For PostgreSQL, we need to handle auto-increment differently
        # PostgreSQL uses SERIAL or IDENTITY
        if self.db_type == DatabaseType.POSTGRESQL:
            etl_runs_pk = "run_id SERIAL PRIMARY KEY"
            raw_metrics_pk = "metric_id SERIAL PRIMARY KEY"
        elif self.db_type == DatabaseType.MYSQL:
            etl_runs_pk = "run_id INT AUTO_INCREMENT PRIMARY KEY"
            raw_metrics_pk = "metric_id INT AUTO_INCREMENT PRIMARY KEY"
        elif self.db_type in [DatabaseType.ORACLE, DatabaseType.MSSQL]:
            # These need special handling, use simpler approach
            etl_runs_pk = "run_id INT PRIMARY KEY"
            raw_metrics_pk = "metric_id INT PRIMARY KEY"
        else:  # SQLite
            etl_runs_pk = "run_id INTEGER PRIMARY KEY AUTOINCREMENT"
            raw_metrics_pk = "metric_id INTEGER PRIMARY KEY AUTOINCREMENT"
        
        # Core tables
        self.execute(f'''
            CREATE TABLE IF NOT EXISTS etl_runs (
                {etl_runs_pk},
                run_type {text_type} NOT NULL,
                status {text_type} NOT NULL,
                start_time {timestamp_type} NOT NULL,
                end_time {timestamp_type},
                duration_seconds INTEGER,
                records_extracted INTEGER,
                records_loaded INTEGER,
                error_message {text_type},
                triggered_by {text_type},
                service_flags {text_type}
            )
        ''')
        
        self.execute(f'''
            CREATE TABLE IF NOT EXISTS raw_instances (
                instance_id {text_type} PRIMARY KEY,
                service_type {text_type} NOT NULL, 
                region {text_type} NOT NULL,
                instance_class {text_type}, 
                engine {text_type}, 
                status {text_type},
                created_date {timestamp_type}, 
                vpc_id {text_type}, 
                publicly_accessible {boolean_type},
                storage_type {text_type}, 
                multi_az {boolean_type}, 
                availability_zone {text_type},
                db_instance_arn {text_type}, 
                backup_retention INTEGER, 
                maintenance_window {text_type},
                backup_window {text_type}, 
                image_id {text_type}, 
                subnet_id {text_type}, 
                architecture {text_type},
                public_ip {text_type}, 
                private_ip {text_type}, 
                root_device {text_type}, 
                virtualization {text_type},
                name {text_type}, 
                raw_data {text_type}, 
                extracted_at {timestamp_type} DEFAULT {current_ts},
                environment_tag {text_type},
                attached_instance_id {text_type},
                volume_id {text_type},
                size_gb INTEGER,
                volume_type {text_type},
                iops INTEGER,
                throughput_mbps INTEGER,
                encrypted {boolean_type},
                monthly_cost REAL DEFAULT 0
            )
        ''')

        self.execute(f'''
            CREATE TABLE IF NOT EXISTS raw_metrics (
                {raw_metrics_pk},
                instance_id {text_type} NOT NULL, 
                metric_name {text_type} NOT NULL,
                metric_value REAL, 
                timestamp {timestamp_type} NOT NULL,
                unit {text_type}, 
                statistics {text_type}, 
                extracted_at {timestamp_type} DEFAULT {current_ts}
            )
        ''')
        
        self.execute(f'''
            CREATE TABLE IF NOT EXISTS data_freshness (
                service_type {text_type} PRIMARY KEY,
                last_updated {timestamp_type} NOT NULL,
                next_scheduled {timestamp_type},
                record_count INTEGER,
                status {text_type} DEFAULT 'fresh'
            )
        ''')

        self.execute(f'''
            CREATE TABLE IF NOT EXISTS etl_lock (
                lock_id INTEGER PRIMARY KEY,
                is_locked {boolean_type} NOT NULL,
                locked_at {timestamp_type},
                locked_by {text_type}
            )
        ''')
        
        # Analysis cache table
        self.execute(f'''
            CREATE TABLE IF NOT EXISTS analysis_cache (
                instance_id {text_type} PRIMARY KEY,
                service_type {text_type} NOT NULL,
                idle_score INTEGER,
                severity {text_type},
                last_activity_date {timestamp_type},
                days_idle REAL,
                idle_reasons {text_type},
                active_reasons {text_type},
                indicators {text_type},
                recommendation {text_type},
                potential_savings_monthly REAL,
                analyzed_at {timestamp_type} DEFAULT {current_ts}
            )
        ''')

        # Tags table
        self.execute(f'''
            CREATE TABLE IF NOT EXISTS instance_tags (
                instance_id {text_type} NOT NULL,
                tag_key {text_type} NOT NULL,
                tag_value {text_type},
                extracted_at {timestamp_type} DEFAULT {current_ts},
                PRIMARY KEY (instance_id, tag_key)
            )
        ''')

        # AWS Regions table - stores discovered regions
        self.execute(f'''
            CREATE TABLE IF NOT EXISTS aws_regions (
                region_name {text_type} PRIMARY KEY,
                region_group {text_type},
                is_enabled {boolean_type} DEFAULT TRUE,
                discovered_at {timestamp_type} DEFAULT {current_ts},
                last_seen_at {timestamp_type}
            )
        ''')

        # Create indexes
        self.create_index_if_not_exists('idx_tags_instance', 'instance_tags', ['instance_id'])
        self.create_index_if_not_exists('idx_raw_instances_service_type', 'raw_instances', ['service_type'])
        self.create_index_if_not_exists('idx_raw_instances_region', 'raw_instances', ['region'])
        self.create_index_if_not_exists('idx_raw_instances_status', 'raw_instances', ['status'])
        self.create_index_if_not_exists('idx_raw_instances_environment', 'raw_instances', ['environment_tag'])
        self.create_index_if_not_exists('idx_raw_instances_attached', 'raw_instances', ['attached_instance_id'])
        self.create_index_if_not_exists('idx_raw_metrics_instance_id', 'raw_metrics', ['instance_id'])
        self.create_index_if_not_exists('idx_raw_metrics_timestamp', 'raw_metrics', ['timestamp'])
        self.create_index_if_not_exists('idx_raw_metrics_metric_name', 'raw_metrics', ['metric_name'])
        self.create_index_if_not_exists('idx_etl_runs_status', 'etl_runs', ['status'])
        self.create_index_if_not_exists('idx_etl_runs_start_time', 'etl_runs', ['start_time'])
        self.create_index_if_not_exists('idx_data_freshness_service_type', 'data_freshness', ['service_type'])

        # Check for lock row
        lock_count = self.fetch_value("SELECT COUNT(*) FROM etl_lock WHERE lock_id = 1")
        if lock_count == 0:
            self.execute("INSERT INTO etl_lock (lock_id, is_locked) VALUES (1, FALSE)")
        
        # Migration: Add new columns if they don't exist (for existing databases)
        self.add_column_if_not_exists('raw_instances', 'environment_tag', text_type)
        self.add_column_if_not_exists('raw_instances', 'attached_instance_id', text_type)
        self.add_column_if_not_exists('raw_instances', 'volume_id', text_type)
        self.add_column_if_not_exists('raw_instances', 'size_gb', 'INTEGER')
        self.add_column_if_not_exists('raw_instances', 'volume_type', text_type)
        self.add_column_if_not_exists('raw_instances', 'iops', 'INTEGER')
        self.add_column_if_not_exists('raw_instances', 'throughput_mbps', 'INTEGER')
        self.add_column_if_not_exists('raw_instances', 'encrypted', boolean_type)
        self.add_column_if_not_exists('raw_instances', 'monthly_cost', 'REAL', default_value=0)

        # Migration: Fix statistics column type from VARCHAR to TEXT (for PostgreSQL)
        # This fixes the "value too long for type character varying(20)" error
        if self.db_type == DatabaseType.POSTGRESQL:
            try:
                # Check if statistics column is VARCHAR and needs to be converted to TEXT
                result = self.fetch_one("""
                    SELECT data_type, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'raw_metrics' AND column_name = 'statistics'
                """)
                if result and result[0] == 'character varying' and result[1] is not None:
                    logger.info("Migrating statistics column from VARCHAR to TEXT...")
                    self.execute("ALTER TABLE raw_metrics ALTER COLUMN statistics TYPE TEXT")
                    logger.info("Successfully migrated statistics column to TEXT")
            except Exception as e:
                logger.warning(f"Could not migrate statistics column: {e}")

    def is_etl_locked(self) -> bool:
        """Check if ETL is locked and handle stale locks"""
        row = self.fetch_one("SELECT is_locked, locked_at FROM etl_lock WHERE lock_id = 1")
        
        if row and row[0]:
            locked_at_str = row[1]
            if locked_at_str:
                try:
                    locked_at = datetime.fromisoformat(str(locked_at_str).replace('Z', '+00:00'))
                    # Check if lock is stale
                    if (datetime.now(timezone.utc) - locked_at).total_seconds() > self.LOCK_TIMEOUT_MINUTES * 60:
                        logger.warning(f"Detected stale ETL lock from {locked_at_str}. Auto-unlocking.")
                        self.release_lock()
                        return False
                except (ValueError, TypeError):
                    pass
            return True
        return False

    def acquire_lock(self, locked_by: str = 'system') -> bool:
        """Try to acquire the ETL lock"""
        if self.is_etl_locked():
            return False
        
        try:
            self.execute(
                "UPDATE etl_lock SET is_locked = TRUE, locked_at = :locked_at, locked_by = :locked_by WHERE lock_id = 1 AND is_locked = FALSE",
                {"locked_at": datetime.now(timezone.utc).isoformat(), "locked_by": locked_by}
            )
            return True
        except Exception as e:
            logger.error(f"Error acquiring lock: {e}")
            return False

    def release_lock(self):
        """Release the ETL lock"""
        try:
            self.execute("UPDATE etl_lock SET is_locked = FALSE, locked_at = NULL, locked_by = NULL WHERE lock_id = 1")
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")

    def force_unlock(self) -> bool:
        """Forcefully release the lock (admin/user action)"""
        logger.info("Forcefully unlocking ETL process")
        self.release_lock()
        return True

    def run_etl(self, run_type='manual', triggered_by='system', services=None, regions=None, aws_environment: str = 'Default') -> Dict:
        """Execute ETL pipeline with locking and error handling"""
        if not self.acquire_lock(triggered_by):
            logger.warning(f"ETL run skipped: process is locked (triggered by {triggered_by})")
            return {'status': 'locked', 'error_message': 'Another ETL process is currently running.'}

        start_time = datetime.now(timezone.utc)
        status = 'running'
        run_id = None
        error_message = None
        records_extracted = 0
        records_loaded = 0
        
        services = services or ['RDS', 'EC2', 'EBS']
        if regions is None:
            regions = self.get_all_aws_regions(aws_environment)
        
        try:
            logger.info(f"Starting ETL run: {run_type}, services={services}, regions={regions}, env={aws_environment}")
            
            for service in services:
                for region in regions:
                    try:
                        if service == 'RDS':
                            instances, metrics = self._extract_rds(region, aws_environment)
                        elif service == 'EC2':
                            instances, metrics = self._extract_ec2(region, aws_environment)
                        elif service == 'EBS':
                            instances, metrics = self._extract_ebs(region, aws_environment)
                        else:
                            continue
                        
                        self._load_data(service, region, instances, metrics)
                        records_extracted += len(instances) + len(metrics)
                        records_loaded += len(instances)
                        logger.info(f"Loaded {len(instances)} instances and {len(metrics)} metrics for {service} in {region}")
                        
                    except Exception as e:
                        logger.error(f"Error in {service} ETL for {region}: {e}")
            
            self._update_freshness(services)
            status = 'success'
            logger.info(f"ETL run completed successfully: {records_loaded} instances loaded into database.")
            
        except Exception as e:
            status = 'failed'
            error_message = str(e)
            logger.error(f"Global ETL failure: {e}", exc_info=True)
            
        finally:
            self.release_lock()
            end_time = datetime.now(timezone.utc)
            duration = int((end_time - start_time).total_seconds())
            
            try:
                self.execute(
                    """
                    INSERT INTO etl_runs (run_type, status, start_time, end_time, duration_seconds, 
                    records_extracted, records_loaded, error_message, triggered_by, service_flags)
                    VALUES (:run_type, :status, :start_time, :end_time, :duration_seconds,
                            :records_extracted, :records_loaded, :error_message, :triggered_by, :service_flags)
                    """,
                    {
                        "run_type": run_type,
                        "status": status,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "duration_seconds": duration,
                        "records_extracted": records_extracted,
                        "records_loaded": records_loaded,
                        "error_message": error_message,
                        "triggered_by": triggered_by,
                        "service_flags": ','.join(services)
                    }
                )
                # Get the last inserted ID
                if self.db_type == DatabaseType.POSTGRESQL:
                    run_id = self.fetch_value("SELECT currval(pg_get_serial_sequence('etl_runs', 'run_id'))")
                elif self.db_type == DatabaseType.MYSQL:
                    run_id = self.fetch_value("SELECT LAST_INSERT_ID()")
                else:  # SQLite and others
                    run_id = self.fetch_value("SELECT last_insert_rowid()")
            except Exception as e:
                logger.error(f"Failed to log ETL run metadata: {e}")
                
        return {
            'run_id': run_id, 
            'status': status, 
            'duration': duration, 
            'error_message': error_message,
            'records_loaded': records_loaded,
            'records_extracted': records_extracted
        }

    # Helper for CloudWatch timeout protection
    def _run_cw_with_timeout(self, func, *args, **kwargs):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=self.CLOUDWATCH_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                raise TimeoutError(f"CloudWatch API call timed out after {self.CLOUDWATCH_TIMEOUT_SECONDS}s")

    def _extract_rds(self, region, aws_environment: str = 'Default'):
        """Extract RDS instances and metrics using multi-threading"""
        rds, cw = self._get_aws_clients('rds', region, aws_environment)
        
        instances = []
        metrics = []
        instances_lock = threading.Lock()
        metrics_lock = threading.Lock()
        
        def process_rds_instance(db, count):
            """Process a single RDS instance and its metrics"""
            logger.info(f"Processing RDS instance {count}")
            id = db['DBInstanceIdentifier']
            
            # Fetch RDS tags
            rds_tags = []
            try:
                if db.get('DBInstanceArn'):
                    tags_response = rds.list_tags_for_resource(ResourceName=db.get('DBInstanceArn'))
                    rds_tags = tags_response.get('TagList', [])
            except Exception as e:
                logger.debug(f"Could not fetch tags for RDS {id}: {e}")
            
            # Get read replica info
            read_replicas = db.get('ReadReplicaDBInstanceIdentifiers', [])
            
            inst = {
                'instance_id': id, 'service_type': 'RDS', 'region': region,
                'instance_class': db['DBInstanceClass'], 'engine': db['Engine'],
                'status': db['DBInstanceStatus'], 
                'name': id,  # Add name field for RDS instances
                'created_date': db.get('InstanceCreateTime', datetime.now(timezone.utc)).isoformat(),
                'raw_data': json.dumps({
                    'engine_version': db.get('EngineVersion'),
                    'allocated_storage': db.get('AllocatedStorage'),
                    'multi_az': db.get('MultiAZ'),
                    'availability_zone': db.get('AvailabilityZone'),
                    'storage_type': db.get('StorageType'),
                    'publicly_accessible': db.get('PubliclyAccessible'),
                    'vpc_id': db.get('DBSubnetGroup', {}).get('VpcId') if db.get('DBSubnetGroup') else None,
                    'db_instance_arn': db.get('DBInstanceArn'),
                    'backup_retention': db.get('BackupRetentionPeriod'),
                    'maintenance_window': db.get('PreferredMaintenanceWindow'),
                    'backup_window': db.get('PreferredBackupWindow'),
                    'endpoint_address': db.get('Endpoint', {}).get('Address'),
                    'endpoint_port': db.get('Endpoint', {}).get('Port'),
                    'read_replicas': read_replicas,
                    'read_replica_count': len(read_replicas),
                    'iam_auth_enabled': db.get('IAMDatabaseAuthenticationEnabled', False),
                    'deletion_protection': db.get('DeletionProtection', False),
                    'performance_insights_enabled': db.get('PerformanceInsightsEnabled', False),
                    'enhanced_monitoring_enabled': db.get('MonitoringInterval', 0) > 0,
                    'monitoring_interval': db.get('MonitoringInterval', 0),
                    'license_model': db.get('LicenseModel', ''),
                    'db_name': db.get('DBName', ''),
                    'master_username': db.get('MasterUsername', ''),
                })
            }
            
            instance_metrics = []
            # Extract metrics for this instance - including health & performance metrics
            rds_metrics = [
                'CPUUtilization', 
                'DatabaseConnections', 
                'FreeableMemory', 
                'ReadIOPS', 
                'WriteIOPS', 
                'NetworkReceiveThroughput', 
                'NetworkTransmitThroughput',
                'FreeStorageSpace',  # Free storage space in bytes
                'ReadLatency',       # Read latency in seconds
                'WriteLatency',      # Write latency in seconds
                'ReadThroughput',    # Read throughput
                'WriteThroughput',   # Write throughput
            ]
            
            # Add replication lag metric only if this is a source DB or has replicas
            if read_replicas or db.get('MultiAZ'):
                rds_metrics.append('ReplicaLag')
            
            for mname in rds_metrics:
                try:
                    resp = self._run_cw_with_timeout(
                        cw.get_metric_statistics,
                        Namespace='AWS/RDS', MetricName=mname,
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': id}],
                        StartTime=datetime.now(timezone.utc) - timedelta(hours=24),
                        EndTime=datetime.now(timezone.utc),
                        Period=3600, Statistics=['Average']
                    )
                    for dp in resp.get('Datapoints', []):
                        instance_metrics.append({
                            'instance_id': id, 'metric_name': mname,
                            'metric_value': dp.get('Average', 0),
                            'timestamp': dp['Timestamp'].isoformat(),
                            'unit': dp.get('Unit', ''),
                            'statistics': json.dumps({'Average': dp.get('Average', 0)})
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch {mname} for RDS {id}: {e}")
            
            return inst, instance_metrics, rds_tags
        
        # Collect all RDS instances first
        all_dbs = []
        paginator = rds.get_paginator('describe_db_instances')
        for page in paginator.paginate():
            all_dbs.extend(page['DBInstances'])
        
        logger.info(f"Found {len(all_dbs)} RDS instances in {region}. Starting multi-threaded processing...")
        
        # Process instances concurrently using thread pool
        max_workers = min(self.MAX_CONCURRENT_WORKERS, len(all_dbs)) if all_dbs else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_db = {}
            for count, db in enumerate(all_dbs, start=1):
                future = executor.submit(process_rds_instance, db, count)
                future_to_db[future] = db
            
            # Collect results as they complete
            for future in as_completed(future_to_db):
                try:
                    instance, instance_metrics, rds_tags = future.result()
                    with instances_lock:
                        instances.append(instance)
                        # Store tags with instance for deferred insertion (after instance is loaded)
                        if rds_tags:
                            instance['_tags'] = rds_tags
                    with metrics_lock:
                        metrics.extend(instance_metrics)
                except Exception as e:
                    db = future_to_db[future]
                    instance_id = db.get('DBInstanceIdentifier', 'unknown')
                    logger.error(f"Error processing RDS instance {instance_id}: {e}")
        
        logger.info(f"Completed processing {len(instances)} RDS instances with {len(metrics)} metrics")
        return instances, metrics

    def _extract_ec2(self, region, aws_environment: str = 'Default'):
        """Extract EC2 instances and metrics using multi-threading"""
        ec2, cw = self._get_aws_clients('ec2', region, aws_environment)
        
        instances = []
        metrics = []
        instances_lock = threading.Lock()
        metrics_lock = threading.Lock()
        
        def process_ec2_instance(ec2_inst, count):
            """Process a single EC2 instance and its metrics"""
            logger.info(f"Processing EC2 instance {count}")
            id = ec2_inst['InstanceId']
            name = next((t['Value'] for t in ec2_inst.get('Tags', []) if t['Key'] == 'Name'), id)
            
            # Get IAM Instance Profile
            iam_profile = ec2_inst.get('IamInstanceProfile', {})
            iam_role = iam_profile.get('Arn', '').split('/')[-1] if iam_profile else ''
            
            # Get Instance Lifecycle (Spot/On-demand)
            instance_lifecycle = ec2_inst.get('InstanceLifecycle', 'on-demand')
            
            # Get EBS volumes and calculate total storage and encryption
            total_ebs_storage_gb = 0
            ebs_encrypted = False
            for ebs_vol in ec2_inst.get('BlockDeviceMappings', []):
                try:
                    vol_id = ebs_vol.get('Ebs', {}).get('VolumeId')
                    if vol_id:
                        vol_info = ec2.describe_volumes(VolumeIds=[vol_id])['Volumes'][0]
                        total_ebs_storage_gb += vol_info.get('Size', 0)
                        ebs_encrypted = ebs_encrypted or vol_info.get('Encrypted', False)
                except:
                    pass
            
            # Get OS Version from ImageId (simplified)
            image_id = ec2_inst.get('ImageId', '')
            os_version = 'Linux/UNIX'
            eol_date = None
            eol_status = 'supported'
            
            # Try to get more details from image
            try:
                image_info = ec2.describe_images(ImageIds=[image_id])['Images'][0] if image_id else None
                if image_info:
                    platform_details = image_info.get('PlatformDetails', '')
                    description = image_info.get('Description', '')
                    
                    # Determine OS and approximate version
                    if 'ubuntu' in platform_details.lower() or 'ubuntu' in description.lower():
                        os_version = 'Ubuntu'
                        # Ubuntu EOL dates (approximate)
                        if '22.04' in description or 'jammy' in description.lower():
                            os_version = 'Ubuntu 22.04'
                            eol_date = '2027-04'
                        elif '24.04' in description or 'noble' in description.lower():
                            os_version = 'Ubuntu 24.04'
                            eol_date = '2029-04'
                        elif '20.04' in description or 'focal' in description.lower():
                            os_version = 'Ubuntu 20.04'
                            eol_date = '2025-04'
                            eol_status = 'near_eol' if datetime.now(timezone.utc) < datetime(2025, 4, 1, tzinfo=timezone.utc) else 'eol'
                        elif '18.04' in description or 'bionic' in description.lower():
                            os_version = 'Ubuntu 18.04'
                            eol_date = '2023-06'
                            eol_status = 'eol'
                    elif 'amazon linux' in platform_details.lower() or 'amazon linux' in description.lower():
                        os_version = 'Amazon Linux'
                        # Amazon Linux 2 EOL is around 2025, AL2023 is longer
                        if 'al2023' in description.lower():
                            os_version = 'Amazon Linux 2023'
                            eol_date = '2028-03'
                        elif 'al2' in description.lower():
                            os_version = 'Amazon Linux 2'
                            eol_date = '2025-06'
                            eol_status = 'near_eol' if datetime.now(timezone.utc) < datetime(2025, 6, 1, tzinfo=timezone.utc) else 'eol'
                    elif 'windows' in platform_details.lower():
                        os_version = 'Windows Server'
                        # Windows Server EOL varies by version
                        if '2019' in description:
                            os_version = 'Windows Server 2019'
                            eol_date = '2029-01'
                        elif '2022' in description:
                            os_version = 'Windows Server 2022'
                            eol_date = '2032-01'
                        elif '2016' in description:
                            os_version = 'Windows Server 2016'
                            eol_date = '2027-01'
                    elif 'red hat' in platform_details.lower() or 'rhel' in platform_details.lower():
                        os_version = 'RHEL'
                        # RHEL versions typically supported for 10 years
                        if '8.' in description:
                            os_version = 'RHEL 8'
                            eol_date = '2029-05'
                        elif '9.' in description:
                            os_version = 'RHEL 9'
                            eol_date = '2032-05'
            except:
                pass
            
            # Calculate EOL status
            if eol_date:
                try:
                    eol_dt = datetime.strptime(eol_date, '%Y-%m')
                    if eol_dt < datetime.now(timezone.utc):
                        eol_status = 'eol'
                    elif (eol_dt - datetime.now(timezone.utc)).days < 180:
                        eol_status = 'near_eol'
                except:
                    pass
            
            inst = {
                'instance_id': id, 'service_type': 'EC2', 'region': region,
                'instance_class': ec2_inst['InstanceType'], 
                'engine': ec2_inst.get('Platform', 'Linux/UNIX'),
                'status': ec2_inst['State']['Name'],
                'created_date': ec2_inst.get('LaunchTime', datetime.now(timezone.utc)).isoformat(),
                'name': name,
                'environment_tag': self._get_tag_value(ec2_inst.get('Tags', []), 'Environment'),
                'raw_data': json.dumps({
                    'vpc_id': ec2_inst.get('VpcId'),
                    'public_ip': ec2_inst.get('PublicIpAddress'),
                    'private_ip': ec2_inst.get('PrivateIpAddress'),
                    'architecture': ec2_inst.get('Architecture'),
                    'subnet_id': ec2_inst.get('SubnetId'),
                    'image_id': image_id,
                    'root_device': ec2_inst.get('RootDeviceType'),
                    'virtualization': ec2_inst.get('VirtualizationType'),
                    'availability_zone': ec2_inst.get('Placement', {}).get('AvailabilityZone'),
                    'ebs_volume_count': len(ec2_inst.get('BlockDeviceMappings', [])),
                    'iam_role': iam_role,
                    'instance_lifecycle': instance_lifecycle,
                    'total_ebs_storage_gb': total_ebs_storage_gb,
                    'ebs_encrypted': ebs_encrypted,
                    'os_version': os_version,
                    'eol_date': eol_date,
                    'eol_status': eol_status
                })
            }
            
            instance_metrics = []
            # Collect standard CloudWatch metrics
            for mname in ['CPUUtilization', 'NetworkIn', 'NetworkOut', 'DiskReadBytes', 'DiskWriteBytes', 'StatusCheckFailed']:
                try:
                    resp = self._run_cw_with_timeout(
                        cw.get_metric_statistics,
                        Namespace='AWS/EC2', MetricName=mname,
                        Dimensions=[{'Name': 'InstanceId', 'Value': id}],
                        StartTime=datetime.now(timezone.utc) - timedelta(hours=24),
                        EndTime=datetime.now(timezone.utc),
                        Period=3600, Statistics=['Average']
                    )
                    for dp in resp.get('Datapoints', []):
                        instance_metrics.append({
                            'instance_id': id, 'metric_name': mname,
                            'metric_value': dp.get('Average', 0),
                            'timestamp': dp['Timestamp'].isoformat(),
                            'unit': dp.get('Unit', ''),
                            'statistics': json.dumps({'Average': dp.get('Average', 0)})
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch {mname} for EC2 {id}: {e}")
            
            return inst, instance_metrics
        
        # Collect all EC2 instances first
        all_instances = []
        paginator = ec2.get_paginator('describe_instances')
        for page in paginator.paginate():
            for res in page['Reservations']:
                all_instances.extend(res['Instances'])
        
        logger.info(f"Found {len(all_instances)} EC2 instances in {region}. Starting multi-threaded processing...")
        
        # Process instances concurrently using thread pool
        max_workers = min(self.MAX_CONCURRENT_WORKERS, len(all_instances)) if all_instances else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_inst = {}
            for count, ec2_inst in enumerate(all_instances, start=1):
                future = executor.submit(process_ec2_instance, ec2_inst, count)
                future_to_inst[future] = ec2_inst
            
            # Collect results as they complete
            for future in as_completed(future_to_inst):
                try:
                    instance, instance_metrics = future.result()
                    with instances_lock:
                        instances.append(instance)
                        # Store tags with instance for deferred insertion (after instance is loaded)
                        ec2_inst = future_to_inst[future]
                        if ec2_inst.get('Tags'):
                            instance['_tags'] = ec2_inst['Tags']
                    with metrics_lock:
                        metrics.extend(instance_metrics)
                except Exception as e:
                    ec2_inst = future_to_inst[future]
                    instance_id = ec2_inst.get('InstanceId', 'unknown')
                    logger.error(f"Error processing EC2 instance {instance_id}: {e}")
        
        logger.info(f"Completed processing {len(instances)} EC2 instances with {len(metrics)} metrics")
        return instances, metrics

    def _extract_ebs(self, region, aws_environment: str = 'Default'):
        """Extract EBS volumes as a separate service and link to EC2 instances"""
        from etl.ebs_pricing_loader import EBSPricingLoader
        
        ec2, _ = self._get_aws_clients('ec2', region, aws_environment)
        pricing_loader = EBSPricingLoader()
        
        instances = []
        metrics = []
        instances_lock = threading.Lock()
        
        # First, get a mapping of EC2 instance IDs to their environment tags
        ec2_env_map = {}
        try:
            paginator = ec2.get_paginator('describe_instances')
            for page in paginator.paginate():
                for reservation in page.get('Reservations', []):
                    for inst in reservation.get('Instances', []):
                        instance_id = inst.get('InstanceId')
                        env_tag = self._get_tag_value(inst.get('Tags', []), 'Environment')
                        ec2_env_map[instance_id] = env_tag
        except Exception as e:
            logger.warning(f"Failed to get EC2 instances for environment mapping: {e}")
        
        # Get all volumes in the region
        try:
            paginator = ec2.get_paginator('describe_volumes')
            volume_count = 0
            
            for page in paginator.paginate():
                for vol in page['Volumes']:
                    volume_count += 1
                    
                    # Get attached instance info
                    attachments = vol.get('Attachments', [])
                    attached_instance_id = None
                    attachment_state = None
                    if attachments:
                        attached_instance_id = attachments[0].get('InstanceId')
                        attachment_state = attachments[0].get('State')
                    
                    # Get environment tag from attached EC2 instance
                    environment_tag = ec2_env_map.get(attached_instance_id, 'Unknown')
                    
                    # Calculate monthly cost
                    size_gb = vol.get('Size', 0)
                    volume_type = vol.get('VolumeType', 'gp3')
                    iops = vol.get('Iops')
                    
                    cost_result = pricing_loader.calculate_volume_cost(
                        size_gb, volume_type, iops, region
                    )
                    monthly_cost = cost_result['monthly']
                    
                    inst = {
                        'instance_id': vol['VolumeId'],  # Use volume_id as instance_id
                        'service_type': 'EBS',
                        'region': region,
                        'volume_id': vol['VolumeId'],
                        'size_gb': size_gb,
                        'volume_type': volume_type,
                        'iops': iops,
                        'throughput_mbps': vol.get('Throughput'),
                        'encrypted': vol.get('Encrypted', False),
                        'attached_instance_id': attached_instance_id,
                        'attachment_state': attachment_state,
                        'environment_tag': environment_tag,
                        'monthly_cost': monthly_cost,
                        'raw_data': json.dumps({
                            'create_time': vol.get('CreateTime').isoformat() if vol.get('CreateTime') else None,
                            'availability_zone': vol.get('AvailabilityZone'),
                            'state': vol.get('State'),
                            'snapshot_id': vol.get('SnapshotId'),
                            'cost_details': cost_result
                        })
                    }
                    # Store tags with instance for deferred insertion (after instance is loaded)
                    if vol.get('Tags'):
                        inst['_tags'] = vol['Tags']
                    instances.append(inst)
            
            logger.info(f"Completed processing {len(instances)} EBS volumes in {region}")
            
        except Exception as e:
            logger.error(f"Failed to extract EBS volumes: {e}")
            
        return instances, metrics

    def _get_tag_value(self, tags, key):
        """Helper to get tag value from a list of tags"""
        if not tags:
            return 'Unknown'
        for tag in tags:
            if tag.get('Key') == key:
                return tag.get('Value', 'Unknown')
        return 'Unknown'

    def _store_tags(self, instance_id: str, tags: list):
        """Store tags in the instance_tags table"""
        if not tags:
            return
        
        try:
            # Delete existing tags for this instance
            self.execute("DELETE FROM instance_tags WHERE instance_id = :instance_id", {"instance_id": instance_id})
            
            # Insert new tags
            for tag in tags:
                if isinstance(tag, dict) and 'Key' in tag:
                    self.execute(
                        """
                        INSERT INTO instance_tags (instance_id, tag_key, tag_value)
                        VALUES (:instance_id, :tag_key, :tag_value)
                        """,
                        {"instance_id": instance_id, "tag_key": tag['Key'], "tag_value": tag.get('Value', '')}
                    )
        except Exception as e:
            logger.error(f"Error storing tags for {instance_id}: {e}")

    def _load_data(self, service_type, region, instances, metrics):
        """Load data into staging/final tables"""
        logger.debug(f"Loading {len(instances)} instances into database for {service_type}...")
        try:
            # Clear old data for the region/service
            self.execute(
                "DELETE FROM raw_metrics WHERE instance_id IN (SELECT instance_id FROM raw_instances WHERE service_type=:service_type AND region=:region)",
                {"service_type": service_type, "region": region}
            )
            # Delete tags first (due to foreign key constraint)
            self.execute(
                "DELETE FROM instance_tags WHERE instance_id IN (SELECT instance_id FROM raw_instances WHERE service_type=:service_type AND region=:region)",
                {"service_type": service_type, "region": region}
            )
            self.execute(
                "DELETE FROM raw_instances WHERE service_type=:service_type AND region=:region",
                {"service_type": service_type, "region": region}
            )
            
            # Load new instances
            for i in instances:
                # Parse raw_data to populate structured columns
                raw_data_str = i.get('raw_data', '{}')
                raw_data = json.loads(raw_data_str) if isinstance(raw_data_str, str) else raw_data_str
                
                # Handle EBS-specific fields
                environment_tag = i.get('environment_tag')
                attached_instance_id = i.get('attached_instance_id')
                volume_id = i.get('volume_id')
                size_gb = i.get('size_gb')
                volume_type = i.get('volume_type')
                iops = i.get('iops')
                throughput_mbps = i.get('throughput_mbps')
                encrypted = i.get('encrypted')
                monthly_cost = i.get('monthly_cost', 0)
                
                self.execute(
                    """
                    INSERT INTO raw_instances (
                        instance_id, service_type, region, instance_class, engine, status, created_date, name, raw_data,
                        vpc_id, publicly_accessible, storage_type, multi_az, availability_zone,
                        db_instance_arn, backup_retention, maintenance_window, backup_window,
                        image_id, subnet_id, architecture, public_ip, private_ip,
                        environment_tag, attached_instance_id, volume_id, size_gb, volume_type,
                        iops, throughput_mbps, encrypted, monthly_cost
                    )
                    VALUES (:instance_id, :service_type, :region, :instance_class, :engine, :status, :created_date, :name, :raw_data,
                            :vpc_id, :publicly_accessible, :storage_type, :multi_az, :availability_zone,
                            :db_instance_arn, :backup_retention, :maintenance_window, :backup_window,
                            :image_id, :subnet_id, :architecture, :public_ip, :private_ip,
                            :environment_tag, :attached_instance_id, :volume_id, :size_gb, :volume_type,
                            :iops, :throughput_mbps, :encrypted, :monthly_cost)
                    """,
                    {
                        "instance_id": i['instance_id'], "service_type": i['service_type'], "region": i['region'],
                        "instance_class": i.get('instance_class'), "engine": i.get('engine'), "status": i.get('status'),
                        "created_date": i.get('created_date'), "name": i.get('name'), "raw_data": raw_data_str,
                        "vpc_id": raw_data.get('vpc_id'), "publicly_accessible": raw_data.get('publicly_accessible'),
                        "storage_type": raw_data.get('storage_type'), "multi_az": raw_data.get('multi_az'),
                        "availability_zone": raw_data.get('availability_zone'), "db_instance_arn": raw_data.get('db_instance_arn'),
                        "backup_retention": raw_data.get('backup_retention'), "maintenance_window": raw_data.get('maintenance_window'),
                        "backup_window": raw_data.get('backup_window'), "image_id": raw_data.get('image_id'),
                        "subnet_id": raw_data.get('subnet_id'), "architecture": raw_data.get('architecture'),
                        "public_ip": raw_data.get('public_ip'), "private_ip": raw_data.get('private_ip'),
                        "environment_tag": environment_tag, "attached_instance_id": attached_instance_id,
                        "volume_id": volume_id, "size_gb": size_gb, "volume_type": volume_type,
                        "iops": iops, "throughput_mbps": throughput_mbps, "encrypted": encrypted, "monthly_cost": monthly_cost
                    }
                )
                
                # Store tags after instance is inserted (deferred from extraction)
                if i.get('_tags'):
                    self._store_tags(i['instance_id'], i['_tags'])
                
            # Load new metrics
            for m in metrics:
                self.execute(
                    """
                    INSERT INTO raw_metrics (instance_id, metric_name, metric_value, timestamp, unit, statistics)
                    VALUES (:instance_id, :metric_name, :metric_value, :timestamp, :unit, :statistics)
                    """,
                    {
                        "instance_id": m['instance_id'], "metric_name": m['metric_name'],
                        "metric_value": m['metric_value'], "timestamp": m['timestamp'],
                        "unit": m.get('unit'), "statistics": m.get('statistics')
                    }
                )
        except Exception as e:
            raise e

    def _update_freshness(self, services):
        """Update data freshness metadata for each service"""
        for s in services:
            count_result = self.fetch_one("SELECT COUNT(*) as cnt FROM raw_instances WHERE service_type=:service_type", {"service_type": s})
            count = count_result[0] if count_result else 0
            
            # Use database-agnostic upsert
            if self.db_type == DatabaseType.POSTGRESQL:
                self.execute(
                    """
                    INSERT INTO data_freshness (service_type, last_updated, record_count, status)
                    VALUES (:service_type, :last_updated, :record_count, :status)
                    ON CONFLICT (service_type) DO UPDATE SET
                        last_updated = EXCLUDED.last_updated,
                        record_count = EXCLUDED.record_count,
                        status = EXCLUDED.status
                    """,
                    {"service_type": s, "last_updated": datetime.now(timezone.utc).isoformat(), "record_count": count, "status": 'fresh'}
                )
            elif self.db_type == DatabaseType.MYSQL:
                self.execute(
                    """
                    INSERT INTO data_freshness (service_type, last_updated, record_count, status)
                    VALUES (:service_type, :last_updated, :record_count, :status)
                    ON DUPLICATE KEY UPDATE
                        last_updated = VALUES(last_updated),
                        record_count = VALUES(record_count),
                        status = VALUES(status)
                    """,
                    {"service_type": s, "last_updated": datetime.now(timezone.utc).isoformat(), "record_count": count, "status": 'fresh'}
                )
            else:
                # SQLite and others - use INSERT OR REPLACE
                self.execute(
                    """
                    INSERT OR REPLACE INTO data_freshness (service_type, last_updated, record_count, status)
                    VALUES (:service_type, :last_updated, :record_count, :status)
                    """,
                    {"service_type": s, "last_updated": datetime.now(timezone.utc).isoformat(), "record_count": count, "status": 'fresh'}
                )
