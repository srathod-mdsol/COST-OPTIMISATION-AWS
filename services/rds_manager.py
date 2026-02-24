from typing import Dict, List
import json
from datetime import datetime, timezone, timedelta
from services.base_manager import BaseServiceManager
from utils.rate_limiter import rate_limiter
from core.logger import setup_logger
import streamlit as st
from core.config import Config
from core.constants import (
    SECONDS_PER_HOUR,
    SECONDS_PER_DAY,
    METRIC_DATA_QUERY_BATCH_SIZE
)

logger = setup_logger(__name__)

class RDSManager(BaseServiceManager):
    """Manages AWS RDS and CloudWatch operations"""
    
    def __init__(self, region: str = 'us-east-1', use_etl: bool = None, aws_environment: str = 'Default'):
        super().__init__('rds', region, use_etl, aws_environment)
        self.rds_client = self.client

    def list_instances(self) -> List[Dict]:
        """List all RDS instances in the region"""
        if self.use_etl:
            return self._list_rds_instances_from_etl()
        else:
            return self._list_rds_instances_impl()

    def _list_rds_instances_from_etl(self) -> List[Dict]:
        """Get RDS instances from ETL database"""
        provider = self.get_etl_provider()
        if provider is None:
            logger.warning("ETL provider not initialized")
            return []
        
        try:
            instances = provider.list_instances('RDS', self.region)
            result = []
            for inst in instances:
                res = {
                    'instance_id': inst.get('instance_id'),
                    'instance_class': inst.get('instance_class'),
                    'engine': inst.get('engine'),
                    'engine_version': inst.get('engine_version'),
                    'status': inst.get('status'),
                    'allocated_storage': inst.get('allocated_storage'),
                    'storage_type': inst.get('storage_type'),
                    'multi_az': inst.get('multi_az', False),
                    'availability_zone': inst.get('availability_zone'),
                    'endpoint': inst.get('endpoint'),
                    'publicly_accessible': inst.get('publicly_accessible'),
                    'vpc_id': inst.get('vpc_id'),
                    'db_instance_arn': inst.get('db_instance_arn'),
                    'backup_retention': inst.get('backup_retention'),
                    'maintenance_window': inst.get('maintenance_window'),
                    'backup_window': inst.get('backup_window'),
                    'raw_data': inst.get('raw_data'),
                    'environment_tag': inst.get('environment_tag'),
                    'region': inst.get('region', self.region),  # Ensure region is always present
                    'name': inst.get('name') or inst.get('instance_id')  # Ensure name is always present
                }
                # Include any other fields from inst that might be needed
                for k, v in inst.items():
                    if k not in res:
                        res[k] = v
                result.append(res)
            logger.info(f"Loaded {len(result)} RDS instances from ETL for region {self.region}")
            return result
        except Exception as e:
            logger.error(f"Error fetching RDS instances from ETL: {e}")
            if not Config.CLI_MODE:
                st.error(f"Error loading RDS instances from database: {e}")
            return []

    def _list_rds_instances_impl(self) -> List[Dict]:
        """Implementation of list RDS instances via API"""
        instances = []
        try:
            paginator = self.rds_client.get_paginator('describe_db_instances')
            for page in paginator.paginate():
                for db in page['DBInstances']:
                    arn = db.get('DBInstanceArn')
                    tags = {}
                    if arn:
                        try:
                            tags_resp = self.rds_client.list_tags_for_resource(ResourceName=arn)
                            tags = {tag['Key']: tag['Value'] for tag in tags_resp.get('TagList', [])}
                        except Exception as e:
                            logger.debug(f"Could not fetch tags for RDS {arn}: {e}")

                    # Extract region from availability zone or use self.region
                    az = db.get('AvailabilityZone', '')
                    region_from_az = az[:-1] if az and az[-1].isalpha() else self.region
                    
                    instances.append({
                        'instance_id': db['DBInstanceIdentifier'],
                        'instance_class': db['DBInstanceClass'],
                        'engine': db['Engine'],
                        'engine_version': db['EngineVersion'],
                        'status': db['DBInstanceStatus'],
                        'allocated_storage': db['AllocatedStorage'],
                        'storage_type': db['StorageType'],
                        'multi_az': db['MultiAZ'],
                        'availability_zone': az,
                        'endpoint': db.get('Endpoint', {}).get('Address'),
                        'raw_data': json.dumps({'tags': tags}),
                        'environment_tag': next((v for k, v in tags.items() if k.lower() == 'environment'), 'Unknown'),
                        'region': region_from_az or self.region,  # Ensure region is always present
                        'name': db['DBInstanceIdentifier']  # Ensure name is always present
                    })
            logger.info(f"Loaded {len(instances)} RDS instances via API for region {self.region}")
        except Exception as e:
            error_msg = "Failed to list RDS instances. Check permissions and region."
            logger.error(f"RDS listing error: {str(e)}", exc_info=True)
            if not Config.CLI_MODE:
                st.error(error_msg)
            else:
                logger.error(error_msg)
            
        return instances

    def get_cloudwatch_metrics(self, instance_id: str, hours: int = 24) -> Dict:
        """Get CloudWatch metrics for an RDS instance"""
        if self.use_etl:
            provider = self.get_etl_provider()
            try:
                return provider.get_cloudwatch_metrics(instance_id, hours)
            except Exception as e:
                logger.error(f"Error fetching metrics from ETL: {e}")
                return {}
        else:
            all_metrics = self.get_cloudwatch_metrics_batch([instance_id], hours)
            return all_metrics.get(instance_id, {})

    def get_cloudwatch_metrics_batch(self, instance_ids: list, hours: int = 24) -> dict:
        """Batch fetch CloudWatch metrics for multiple RDS instances"""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)
        metrics_to_fetch = {
            'DatabaseConnections': {'stat': 'Average', 'unit': 'Count', 'ns': 'AWS/RDS'},
            'CPUUtilization': {'stat': 'Average', 'unit': 'Percent', 'ns': 'AWS/RDS'},
            'FreeableMemory': {'stat': 'Average', 'unit': 'Bytes', 'ns': 'AWS/RDS'},
            'ReadIOPS': {'stat': 'Average', 'unit': 'Count/Second', 'ns': 'AWS/RDS'},
            'WriteIOPS': {'stat': 'Average', 'unit': 'Count/Second', 'ns': 'AWS/RDS'},
            'NetworkReceiveThroughput': {'stat': 'Average', 'unit': 'Bytes/Second', 'ns': 'AWS/RDS'},
            'NetworkTransmitThroughput': {'stat': 'Average', 'unit': 'Bytes/Second', 'ns': 'AWS/RDS'},
            'ReadLatency': {'stat': 'Average', 'unit': 'Seconds', 'ns': 'AWS/RDS'},
            'WriteLatency': {'stat': 'Average', 'unit': 'Seconds', 'ns': 'AWS/RDS'},
            'ReadThroughput': {'stat': 'Average', 'unit': 'Bytes/Second', 'ns': 'AWS/RDS'},
            'WriteThroughput': {'stat': 'Average', 'unit': 'Bytes/Second', 'ns': 'AWS/RDS'}
        }
        
        metric_data_queries = []
        id_map = {}
        for instance_id in instance_ids:
            for metric_name, config in metrics_to_fetch.items():
                # Safe ID for GetMetricData
                qid = f"id_{hash(instance_id + metric_name) & 0xffffffff:08x}"
                metric_data_queries.append({
                    'Id': qid,
                    'MetricStat': {
                        'Metric': {
                            'Namespace': config['ns'],
                            'MetricName': metric_name,
                            'Dimensions': [{'Name': 'DBInstanceIdentifier', 'Value': instance_id}]
                        },
                        'Period': SECONDS_PER_HOUR,
                        'Stat': config['stat'],
                        'Unit': config['unit']
                    },
                    'ReturnData': True
                })
                id_map[qid] = (instance_id, metric_name)

        results = {iid: {} for iid in instance_ids}
        for i in range(0, len(metric_data_queries), METRIC_DATA_QUERY_BATCH_SIZE):
            batch = metric_data_queries[i:i+METRIC_DATA_QUERY_BATCH_SIZE]
            try:
                response = self.cloudwatch.get_metric_data(
                    MetricDataQueries=batch,
                    StartTime=start_time,
                    EndTime=end_time,
                    ScanBy='TimestampAscending'
                )
                for r in response['MetricDataResults']:
                    iid, mname = id_map[r['Id']]
                    values = r['Values']
                    results[iid][mname] = {
                        'current': values[-1] if values else 0,
                        'average': sum(values) / len(values) if values else 0,
                        'max': max(values) if values else 0,
                        'min': min(values) if values else 0,
                        'datapoints': [
                            {'Timestamp': t, metrics_to_fetch[mname]['stat']: v}
                            for t, v in zip(r['Timestamps'], r['Values'])
                        ]
                    }
            except Exception as e:
                logger.error(f"Error in batch metrics: {e}")
                continue
        return results

    @rate_limiter
    def detect_last_activity(self, instance_id: str, days: int = 30) -> Dict:
        """Detect when the RDS instance was last active"""
        if self.use_etl:
            return self._get_last_activity_from_etl(
                instance_id, days, 
                ['DatabaseConnections', 'ReadIOPS', 'WriteIOPS', 'CPUUtilization']
            )
        
        # CLI mode: Direct API call
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        
        activity_indicators = {
            'DatabaseConnections': 0.5,
            'ReadIOPS': 1,
            'WriteIOPS': 1,
            'CPUUtilization': 5,
            'NetworkTransmitThroughput': 1000
        }
        
        last_activity_time = None
        activity_details = {}
        
        for metric_name, threshold in activity_indicators.items():
            try:
                response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/RDS',
                    MetricName=metric_name,
                    Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': instance_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=SECONDS_PER_HOUR,
                    Statistics=['Maximum']
                )
                
                datapoints = [dp for dp in response.get('Datapoints', []) if dp['Maximum'] > threshold]
                
                if datapoints:
                    latest = max(datapoints, key=lambda x: x['Timestamp'])
                    activity_details[metric_name] = {
                        'last_active': latest['Timestamp'],
                        'value': latest['Maximum']
                    }
                    if last_activity_time is None or latest['Timestamp'] > last_activity_time:
                        last_activity_time = latest['Timestamp']
            except Exception as e:
                logger.debug(f"Error fetching metric {metric_name} for RDS {instance_id}: {e}")
                continue
        
        days_since = (end_time - last_activity_time).total_seconds() / SECONDS_PER_DAY if last_activity_time else None
        
        return {
            'last_activity_time': last_activity_time,
            'days_since_activity': days_since,
            'activity_details': activity_details
        }
    
    def detect_last_activity_batch(self, instance_ids: List[str], days: int = 30) -> Dict[str, Dict]:
        """Batch version of detect_last_activity for better performance with ETL mode"""
        if self.use_etl:
            return self._get_last_activity_batch_from_etl(
                instance_ids, days,
                ['DatabaseConnections', 'ReadIOPS', 'WriteIOPS', 'CPUUtilization']
            )
        
        # Non-ETL mode: fall back to individual calls
        results = {}
        for instance_id in instance_ids:
            results[instance_id] = self.detect_last_activity(instance_id, days)
        return results
    
    def get_cloudwatch_metrics_with_batch(self, instance_id: str, hours: int = 24, batch_metrics: Dict = None) -> Dict:
        """Get CloudWatch metrics, optionally using pre-fetched batch data"""
        if batch_metrics and instance_id in batch_metrics:
            return batch_metrics[instance_id]
        return self.get_cloudwatch_metrics(instance_id, hours)
