import boto3
import json
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError, CredentialRetrievalError
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from core.config import Config
from core.logger import setup_logger
from core.constants import SECONDS_PER_DAY

logger = setup_logger(__name__)

class BaseServiceManager:
    """Base class for AWS service managers with dual-mode support (ETL vs Direct API)"""
    
    # Class-level cache for ETL provider to avoid repeated initialization
    _etl_provider_cache = {}
    
    def __init__(self, service_name: str, region: str = 'us-east-1', use_etl: bool = None, aws_environment: str = 'Default'):
        self.service_name = service_name
        self.region = region
        self.aws_environment = aws_environment
        # Default to use_etl if not specified, except in CLI_MODE
        self.use_etl = use_etl if use_etl is not None else (not Config.CLI_MODE)
        
        self.client = None
        self.cloudwatch = None
        self._etl_provider = None  # Instance-level cache
        
        if not self.use_etl:
            try:
                # Get environment-specific credentials
                creds = Config.get_aws_credentials(aws_environment)
                
                # Filter out region if passed explicitly, use creds default region otherwise
                final_region = region if region else creds.get('region_name', 'us-east-1')
                
                # Extract specific keys for boto3 client
                client_kwargs = {
                    'region_name': final_region
                }
                
                if creds.get('aws_access_key_id'):
                    client_kwargs['aws_access_key_id'] = creds['aws_access_key_id']
                if creds.get('aws_secret_access_key'):
                    client_kwargs['aws_secret_access_key'] = creds['aws_secret_access_key']
                if creds.get('aws_session_token'):
                    client_kwargs['aws_session_token'] = creds['aws_session_token']

                self.client = boto3.client(service_name, **client_kwargs)
                self.cloudwatch = boto3.client('cloudwatch', **client_kwargs)
                logger.info(f"Initialized {service_name} manager for region: {final_region} (Env: {aws_environment}) (Direct API mode)")
            except (NoCredentialsError, PartialCredentialsError, CredentialRetrievalError) as e:
                logger.error(f"AWS Credential error for environment '{aws_environment}': {str(e)}")
                raise Exception(f"AWS Credentials for '{aws_environment}' are missing or incomplete.")
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == 'ExpiredToken':
                    logger.error(f"AWS Session Token for '{aws_environment}' has expired.")
                    raise Exception(f"AWS Session for '{aws_environment}' has expired. Please refresh your credentials.")
                else:
                    logger.error(f"AWS API Error during {service_name} init: {error_code}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error initializing {service_name} manager: {str(e)}")
                raise Exception("An internal error occurred while connecting to AWS. Check logs for details.")
        else:
            logger.info(f"Initialized {service_name} manager for region: {region} (Env: {aws_environment}) (ETL mode)")

    def get_etl_provider(self):
        """Lazy import/check for ETL provider to avoid circular dependencies.
        Uses caching to avoid repeated database initialization."""
        # Check instance-level cache first
        if self._etl_provider is not None:
            return self._etl_provider
        
        # Check class-level cache for this environment
        cache_key = self.aws_environment
        if cache_key in BaseServiceManager._etl_provider_cache:
            self._etl_provider = BaseServiceManager._etl_provider_cache[cache_key]
            return self._etl_provider
        
        # Create new provider and cache it
        from etl.data_provider import create_data_provider
        db_path = Config.get_db_path(self.aws_environment)
        provider = create_data_provider(db_path)
        
        # Cache at both levels
        self._etl_provider = provider
        BaseServiceManager._etl_provider_cache[cache_key] = provider
        
        return provider

    def _get_last_activity_from_etl(self, resource_id: str, days: int, metric_names: List[str]) -> Dict:
        """Shared logic for detecting last activity from ETL data"""
        provider = self.get_etl_provider()
        if not provider:
            logger.warning(f"ETL provider not available for {resource_id}")
            return {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}}
        
        try:
            # Always derive from metrics for real-time accuracy
            metrics = provider.get_cloudwatch_metrics(resource_id, days * 24)
            
            if not metrics:
                logger.warning(f"No metrics found for {resource_id} in last {days} days")
                return {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}}
            
            last_time = None
            last_metric_name = None
            last_metric_value = None
            
            # Scan all relevant metrics for activity
            for metric_name in metric_names:
                metric_data = metrics.get(metric_name, {})
                datapoints = metric_data.get('datapoints', [])
                
                if not datapoints:
                    continue
                
                # Sort datapoints by timestamp descending to find most recent activity
                sorted_datapoints = sorted(datapoints, key=lambda x: x.get('Timestamp'), reverse=True)
                
                for dp in sorted_datapoints:
                    ts = dp.get('Timestamp')
                    if not ts:
                        continue
                    
                    # Handle string timestamps from DB
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    
                    # Ensure datetime is timezone-aware
                    if isinstance(ts, datetime) and ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    
                    # Handle both 'Average' and 'Sum' depending on metric
                    val = dp.get('Average', dp.get('Sum', 0))
                    
                    # Consider any non-zero value as activity
                    if val > 0:
                        if last_time is None or ts > last_time:
                            last_time = ts
                            last_metric_name = metric_name
                            last_metric_value = val
            
            if last_time:
                days_since = (datetime.now(timezone.utc) - last_time).total_seconds() / SECONDS_PER_DAY
                logger.info(f"Last activity for {resource_id}: {last_time.isoformat()} ({days_since:.1f} days ago) - {last_metric_name}={last_metric_value}")
                
                return {
                    'last_activity_time': last_time,
                    'days_since_activity': days_since,
                    'activity_details': {
                        'metric_name': last_metric_name,
                        'metric_value': last_metric_value,
                        'timestamp': last_time.isoformat()
                    }
                }
            else:
                logger.warning(f"No activity detected for {resource_id} in last {days} days (checked {len(metric_names)} metrics)")
                
        except Exception as e:
            logger.error(f"Error getting last activity from ETL for {resource_id}: {e}", exc_info=True)
            
        return {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}}

    def _get_last_activity_batch_from_etl(self, resource_ids: List[str], days: int, metric_names: List[str]) -> Dict[str, Dict]:
        """Batch version of _get_last_activity_from_etl for better performance.
        Fetches metrics for all resources in a single query."""
        provider = self.get_etl_provider()
        if not provider:
            logger.warning("ETL provider not available for batch activity detection")
            return {rid: {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}} for rid in resource_ids}
        
        try:
            # Batch fetch metrics for all resources
            all_metrics = provider.get_cloudwatch_metrics_batch(resource_ids, days * 24)
            
            results = {}
            for resource_id in resource_ids:
                metrics = all_metrics.get(resource_id, {})
                
                if not metrics:
                    results[resource_id] = {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}}
                    continue
                
                last_time = None
                last_metric_name = None
                last_metric_value = None
                
                for metric_name in metric_names:
                    metric_data = metrics.get(metric_name, {})
                    datapoints = metric_data.get('datapoints', [])
                    
                    if not datapoints:
                        continue
                    
                    sorted_datapoints = sorted(datapoints, key=lambda x: x.get('Timestamp'), reverse=True)
                    
                    for dp in sorted_datapoints:
                        ts = dp.get('Timestamp')
                        if not ts:
                            continue
                        
                        if isinstance(ts, str):
                            ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        
                        if isinstance(ts, datetime) and ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        
                        val = dp.get('Average', dp.get('Sum', 0))
                        
                        if val > 0:
                            if last_time is None or ts > last_time:
                                last_time = ts
                                last_metric_name = metric_name
                                last_metric_value = val
                
                if last_time:
                    days_since = (datetime.now(timezone.utc) - last_time).total_seconds() / SECONDS_PER_DAY
                    results[resource_id] = {
                        'last_activity_time': last_time,
                        'days_since_activity': days_since,
                        'activity_details': {
                            'metric_name': last_metric_name,
                            'metric_value': last_metric_value,
                            'timestamp': last_time.isoformat()
                        }
                    }
                else:
                    results[resource_id] = {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}}
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch activity detection: {e}", exc_info=True)
            return {rid: {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}} for rid in resource_ids}
