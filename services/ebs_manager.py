from typing import Dict, List
import json
from datetime import datetime, timezone, timedelta
from services.base_manager import BaseServiceManager
from core.logger import setup_logger
from core.config import Config

logger = setup_logger(__name__)

class EBSManager(BaseServiceManager):
    """Manages AWS EBS operations"""
    
    def __init__(self, region: str = 'us-east-1', use_etl: bool = None, aws_environment: str = 'Default'):
        # EBS uses the 'ec2' client in boto3
        super().__init__('ec2', region, use_etl, aws_environment)
        self.ec2_client = self.client

    def list_instances(self) -> List[Dict]:
        """List all EBS volumes"""
        if self.use_etl:
            return self._list_ebs_volumes_from_etl()
        else:
            try:
                volumes = []
                paginator = self.ec2_client.get_paginator('describe_volumes')
                for page in paginator.paginate():
                    for vol in page['Volumes']:
                        tags = {tag['Key']: tag['Value'] for tag in vol.get('Tags', [])}
                        name = tags.get('Name', vol['VolumeId'])
                        
                        # Extract region from availability zone
                        az = vol['AvailabilityZone']
                        region_from_az = az[:-1] if az and az[-1].isalpha() else self.region
                        
                        volumes.append({
                            'instance_id': vol['VolumeId'],
                            'volume_id': vol['VolumeId'],
                            'name': name,
                            'status': vol['State'],
                            'size_gb': vol['Size'],
                            'volume_type': vol['VolumeType'],
                            'availability_zone': az,
                            'raw_data': json.dumps({'tags': tags}),
                            'environment_tag': next((v for k, v in tags.items() if k.lower() == 'environment'), 'Unknown'),
                            'region': region_from_az or self.region  # Ensure region is always present
                        })
                logger.info(f"Loaded {len(volumes)} EBS volumes via API for region {self.region}")
                return volumes
            except Exception as e:
                logger.error(f"Error listing EBS volumes: {e}")
                return []

    def _list_ebs_volumes_from_etl(self) -> List[Dict]:
        """Get EBS volumes from ETL database"""
        provider = self.get_etl_provider()
        if provider is None:
            return []
        
        try:
            volumes = provider.list_instances('EBS', self.region)
            result = []
            for vol in volumes:
                res = {
                    'instance_id': vol.get('instance_id'), # VolumeID as instance_id
                    'volume_id': vol.get('volume_id'),
                    'name': vol.get('name') or vol.get('volume_id'),
                    'status': vol.get('status', 'unknown'),
                    'state': vol.get('status', 'unknown'),
                    'size_gb': vol.get('size_gb'),
                    'volume_type': vol.get('volume_type'),
                    'iops': vol.get('iops'),
                    'throughput_mbps': vol.get('throughput_mbps'),
                    'encrypted': vol.get('encrypted'),
                    'attached_instance_id': vol.get('attached_instance_id'),
                    'availability_zone': vol.get('availability_zone'),
                    'monthly_cost': vol.get('monthly_cost', 0),
                    'region': vol.get('region', self.region),  # Ensure region is always present
                    'raw_data': vol.get('raw_data'),
                    'environment_tag': vol.get('environment_tag')
                }
                for k, v in vol.items():
                    if k not in res:
                        res[k] = v
                result.append(res)
            logger.info(f"Loaded {len(result)} EBS volumes from ETL for region {self.region}")
            return result
        except Exception as e:
            logger.error(f"Error fetching EBS volumes from ETL: {e}")
            return []

    def get_cloudwatch_metrics(self, volume_id: str, hours: int = 24) -> Dict:
        """Get CloudWatch metrics for an EBS volume"""
        if self.use_etl:
            provider = self.get_etl_provider()
            try:
                return provider.get_cloudwatch_metrics(volume_id, hours)
            except Exception as e:
                logger.error(f"Error fetching EBS metrics from ETL: {e}")
                return {}
        else:
            return {}

    def detect_last_activity(self, volume_id: str, days: int = 30) -> Dict:
        """Detect last activity for EBS volume"""
        if self.use_etl:
            return self._get_last_activity_from_etl(
                volume_id, days,
                ['VolumeReadOps', 'VolumeWriteOps', 'VolumeReadBytes', 'VolumeWriteBytes']
            )
        return {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}}
    
    def detect_last_activity_batch(self, volume_ids: List[str], days: int = 30) -> Dict[str, Dict]:
        """Batch version of detect_last_activity for better performance with ETL mode"""
        if self.use_etl:
            return self._get_last_activity_batch_from_etl(
                volume_ids, days,
                ['VolumeReadOps', 'VolumeWriteOps', 'VolumeReadBytes', 'VolumeWriteBytes']
            )
        return {vid: {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}} for vid in volume_ids}
