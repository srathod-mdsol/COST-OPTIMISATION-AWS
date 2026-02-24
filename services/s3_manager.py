from typing import Dict, List
import json
from datetime import datetime, timezone, timedelta
from services.base_manager import BaseServiceManager
from core.logger import setup_logger
from core.config import Config
from core.constants import (
    SECONDS_PER_DAY,
    BYTES_PER_GB
)
import streamlit as st

logger = setup_logger(__name__)

class S3Manager(BaseServiceManager):
    """Manages AWS S3 and CloudWatch operations"""
    
    def __init__(self, region: str = 'us-east-1', use_etl: bool = None, aws_environment: str = 'Default'):
        super().__init__('s3', region, use_etl, aws_environment)
        self.s3_client = self.client

    def list_instances(self) -> List[Dict]:
        """List all S3 buckets"""
        if self.use_etl:
            return self._list_s3_buckets_from_etl()
        else:
            return self._list_s3_buckets_impl()

    def _list_s3_buckets_from_etl(self) -> List[Dict]:
        """Get S3 buckets from ETL database"""
        provider = self.get_etl_provider()
        if provider is None:
            return []
        
        try:
            instances = provider.list_instances('S3', self.region)
            result = []
            for inst in instances:
                res = {
                    'instance_id': inst.get('instance_id'),
                    'name': inst.get('instance_id'),
                    'bucket_name': inst.get('instance_id'),
                    'creation_date': inst.get('created_date'),
                    'region': inst.get('region', self.region),  # Ensure region is always present
                    'size_bytes': inst.get('size_bytes', 0),
                    'size_gb': inst.get('size_gb', 0),
                    'object_count': inst.get('object_count', 0),
                    'versioning': inst.get('versioning', 'Disabled'),
                    'raw_data': inst.get('raw_data'),
                    'environment_tag': inst.get('environment_tag')
                }
                for k, v in inst.items():
                    if k not in res:
                        res[k] = v
                result.append(res)
            logger.info(f"Loaded {len(result)} S3 buckets from ETL for region {self.region}")
            return result
        except Exception as e:
            logger.error(f"Error fetching S3 buckets from ETL: {e}")
            return []

    def _list_s3_buckets_impl(self) -> List[Dict]:
        """Implementation of list S3 buckets via API"""
        buckets = []
        try:
            response = self.s3_client.list_buckets()
            
            for bucket in response.get('Buckets', []):
                bucket_name = bucket['Name']
                
                try:
                    # Get bucket location
                    location_response = self.s3_client.get_bucket_location(Bucket=bucket_name)
                    location = location_response.get('LocationConstraint') or 'us-east-1'
                    
                    # Get bucket size and object count
                    try:
                        size_response = self.cloudwatch.get_metric_statistics(
                            Namespace='AWS/S3',
                            MetricName='BucketSizeBytes',
                            Dimensions=[
                                {'Name': 'BucketName', 'Value': bucket_name},
                                {'Name': 'StorageType', 'Value': 'StandardStorage'}
                            ],
                            StartTime=datetime.now(timezone.utc) - timedelta(days=2),
                            EndTime=datetime.now(timezone.utc),
                            Period=SECONDS_PER_DAY,
                            Statistics=['Average']
                        )
                        
                        size_bytes = 0
                        if size_response.get('Datapoints'):
                            size_bytes = size_response['Datapoints'][-1].get('Average', 0)
                        
                        count_response = self.cloudwatch.get_metric_statistics(
                            Namespace='AWS/S3',
                            MetricName='NumberOfObjects',
                            Dimensions=[
                                {'Name': 'BucketName', 'Value': bucket_name},
                                {'Name': 'StorageType', 'Value': 'AllStorageTypes'}
                            ],
                            StartTime=datetime.now(timezone.utc) - timedelta(days=2),
                            EndTime=datetime.now(timezone.utc),
                            Period=SECONDS_PER_DAY,
                            Statistics=['Average']
                        )
                        
                        object_count = 0
                        if count_response.get('Datapoints'):
                            object_count = int(count_response['Datapoints'][-1].get('Average', 0))
                    except Exception as e:
                        logger.debug(f"Could not fetch metrics for bucket {bucket_name}: {e}")
                        size_bytes = 0
                        object_count = 0
                    
                    # Get bucket tags
                    tags = {}
                    try:
                        tag_response = self.s3_client.get_bucket_tagging(Bucket=bucket_name)
                        tags = {tag['Key']: tag['Value'] for tag in tag_response.get('TagSet', [])}
                    except Exception as e:
                        logger.debug(f"Could not fetch tags for bucket {bucket_name}: {e}")

                    buckets.append({
                        'instance_id': bucket_name,
                        'name': bucket_name,
                        'bucket_name': bucket_name,
                        'creation_date': bucket['CreationDate'],
                        'region': location,
                        'size_bytes': size_bytes,
                        'size_gb': size_bytes / BYTES_PER_GB if size_bytes > 0 else 0,
                        'object_count': object_count,
                        'raw_data': json.dumps({'tags': tags}),
                        'environment_tag': next((v for k, v in tags.items() if k.lower() == 'environment'), 'Unknown')
                    })
                except Exception as e:
                    continue
                    
        except Exception as e:
            logger.error(f"Error listing S3 buckets: {e}")
            if not Config.CLI_MODE:
                st.error(f"Error listing S3 buckets: {e}")
            else:
                logger.error(f"Error listing S3 buckets: {e}")
        
        return buckets

    def get_cloudwatch_metrics(self, bucket_name: str, hours: int = 24) -> Dict:
        """Get CloudWatch metrics for S3 bucket"""
        if self.use_etl:
            provider = self.get_etl_provider()
            try:
                return provider.get_cloudwatch_metrics(bucket_name, hours)
            except Exception as e:
                logger.error(f"Error fetching S3 metrics from ETL: {e}")
                return {}
        else:
            # CLI mode - this was not fully implemented in main.py either, but we can add placeholders
            return {}

    def detect_last_activity(self, bucket_name: str, days: int = 30) -> Dict:
        """Detect last activity for S3 bucket"""
        if self.use_etl:
            return self._get_last_activity_from_etl(
                bucket_name, days,
                ['AllRequests', 'PutRequests', 'GetRequests']
            )
        return {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}}
    
    def detect_last_activity_batch(self, bucket_names: List[str], days: int = 30) -> Dict[str, Dict]:
        """Batch version of detect_last_activity for better performance with ETL mode"""
        if self.use_etl:
            return self._get_last_activity_batch_from_etl(
                bucket_names, days,
                ['AllRequests', 'PutRequests', 'GetRequests']
            )
        return {bid: {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}} for bid in bucket_names}
