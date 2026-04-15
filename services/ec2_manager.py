from typing import Dict, List
import json
from datetime import datetime, timezone, timedelta
from services.base_manager import BaseServiceManager
from core.logger import setup_logger
from core.config import Config

logger = setup_logger(__name__)

class EC2Manager(BaseServiceManager):
    """Manages AWS EC2 and CloudWatch operations"""
    
    def __init__(self, region: str = 'us-east-1', use_etl: bool = None, aws_environment: str = 'Default'):
        super().__init__('ec2', region, use_etl, aws_environment)
        self.ec2_client = self.client

    def list_instances(self) -> List[Dict]:
        """List all EC2 instances"""
        if self.use_etl:
            return self._list_ec2_instances_from_etl()
        else:
            try:
                instances = []
                paginator = self.ec2_client.get_paginator('describe_instances')
                for page in paginator.paginate():
                    for reservation in page['Reservations']:
                        for inst in reservation['Instances']:
                            tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
                            name = tags.get('Name', inst['InstanceId'])
                            
                            # Extract region from availability zone
                            az = inst['Placement']['AvailabilityZone']
                            region_from_az = az[:-1] if az and az[-1].isalpha() else self.region
                            
                            instances.append({
                                'instance_id': inst['InstanceId'],
                                'instance_type': inst['InstanceType'],
                                'name': name,
                                'platform': inst.get('Platform', 'Linux/UNIX'),
                                'tenancy': inst.get('Placement', {}).get('Tenancy', 'shared'),
                                'status': inst['State']['Name'],
                                'state': inst['State']['Name'],
                                'availability_zone': az,
                                'launch_time': inst['LaunchTime'].isoformat(),
                                'vpc_id': inst.get('VpcId'),
                                'subnet_id': inst.get('SubnetId'),
                                'raw_data': json.dumps({'tags': tags}),
                                'environment_tag': next((v for k, v in tags.items() if k.lower() == 'environment'), 'Unknown'),
                                'region': region_from_az or self.region  # Ensure region is always present
                            })
                logger.info(f"Loaded {len(instances)} EC2 instances via API for region {self.region}")
                return instances
            except Exception as e:
                logger.error(f"Error listing EC2 instances: {e}")
                return []

    def _list_ec2_instances_from_etl(self) -> List[Dict]:
        """Get EC2 instances from ETL database"""
        provider = self.get_etl_provider()
        if provider is None:
            return []
        
        try:
            instances = provider.list_instances('EC2', self.region)
            result = []
            for inst in instances:
                # Parse raw_data to get additional fields
                raw_data = inst.get('raw_data', {})
                if isinstance(raw_data, str):
                    try:
                        raw_data = json.loads(raw_data)
                    except:
                        raw_data = {}
                
                res = {
                    'instance_id': inst.get('instance_id'),
                    'instance_type': inst.get('instance_class'),
                    'name': inst.get('name') or inst.get('instance_id'),
                    'platform': inst.get('platform', 'Linux/UNIX'),
                    'tenancy': inst.get('tenancy', 'shared'),
                    'status': inst.get('status', 'unknown'),
                    'state': inst.get('status', 'unknown'),
                    'availability_zone': inst.get('availability_zone'),
                    'launch_time': inst.get('created_date'),
                    'vpc_id': inst.get('vpc_id'),
                    'subnet_id': inst.get('subnet_id'),
                    'image_id': inst.get('image_id'),
                    'architecture': inst.get('architecture'),
                    'public_ip': inst.get('public_ip'),
                    'private_ip': inst.get('private_ip'),
                    'root_device': inst.get('root_device'),
                    'virtualization': inst.get('virtualization'),
                    'raw_data': inst.get('raw_data'),
                    'environment_tag': inst.get('environment_tag'),
                    'region': inst.get('region', self.region),
                    # New fields from raw_data
                    'iam_role': raw_data.get('iam_role', ''),
                    'instance_lifecycle': raw_data.get('instance_lifecycle', 'on-demand'),
                    'total_ebs_storage_gb': raw_data.get('total_ebs_storage_gb', 0),
                    'ebs_encrypted': raw_data.get('ebs_encrypted', False),
                    'os_version': raw_data.get('os_version', 'Linux/UNIX'),
                    'eol_date': raw_data.get('eol_date', ''),
                    'eol_status': raw_data.get('eol_status', 'supported')
                }
                # Include any other fields (merged from raw_data in ETLDataProvider)
                for k, v in inst.items():
                    if k not in res:
                        res[k] = v
                result.append(res)
            logger.info(f"Loaded {len(result)} EC2 instances from ETL for region {self.region}")
            return result
        except Exception as e:
            logger.error(f"Error fetching EC2 instances from ETL: {e}")
            return []

    def get_cloudwatch_metrics(self, instance_id: str, hours: int = 24) -> Dict:
        """Get CloudWatch metrics for an EC2 instance"""
        if self.use_etl:
            provider = self.get_etl_provider()
            try:
                return provider.get_cloudwatch_metrics(instance_id, hours)
            except Exception as e:
                logger.error(f"Error fetching EC2 metrics from ETL: {e}")
                return {}
        else:
            return {}

    def detect_last_activity(self, instance_id: str, days: int = 30) -> Dict:
        """Detect last activity for EC2 instance"""
        if self.use_etl:
            return self._get_last_activity_from_etl(
                instance_id, days,
                ['CPUUtilization', 'NetworkIn', 'NetworkOut']
            )
        return {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}}
    
    def detect_last_activity_batch(self, instance_ids: List[str], days: int = 30) -> Dict[str, Dict]:
        """Batch version of detect_last_activity for better performance with ETL mode"""
        if self.use_etl:
            return self._get_last_activity_batch_from_etl(
                instance_ids, days,
                ['CPUUtilization', 'NetworkIn', 'NetworkOut']
            )
        return {iid: {'last_activity_time': None, 'days_since_activity': None, 'activity_details': {}} for iid in instance_ids}

    def get_attached_volumes(self, instance_id: str) -> List[Dict]:
        """Get all EBS volumes attached to this instance"""
        if self.use_etl:
            provider = self.get_etl_provider()
            if provider:
                try:
                    return provider.get_ebs_volumes_for_instance(instance_id)
                except Exception as e:
                    logger.error(f"Error fetching attached volumes for {instance_id}: {e}")
        return []

    def get_attached_volumes_batch(self, instance_ids: List[str]) -> Dict[str, List[Dict]]:
        """Get all EBS volumes for multiple instances in a single query.
        
        This is more efficient than calling get_attached_volumes multiple times
        as it uses a single database connection and query.
        
        Args:
            instance_ids: List of EC2 instance IDs to fetch volumes for
            
        Returns:
            Dictionary mapping instance_id to list of attached volumes
        """
        if self.use_etl:
            provider = self.get_etl_provider()
            if provider:
                try:
                    return provider.get_ebs_volumes_batch(instance_ids)
                except Exception as e:
                    logger.error(f"Error fetching attached volumes batch: {e}")
        return {iid: [] for iid in instance_ids}
