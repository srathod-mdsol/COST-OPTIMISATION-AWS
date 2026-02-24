from typing import Dict, Optional, List
from collections import defaultdict
from core.config import Config
from core.constants import HOURS_PER_MONTH, S3_STORAGE_COSTS, DEFAULT_S3_STORAGE_CLASS
from core.logger import setup_logger

logger = setup_logger(__name__)


class CostCalculator:
    """Calculates potential cost savings for AWS resources"""
    
    @staticmethod
    def calculate_rds_savings(hourly_price: float) -> Dict:
        """Calculate savings for stopping/terminating an RDS instance.
        
        Args:
            hourly_price: The hourly cost of the RDS instance in USD.
            
        Returns:
            Dictionary containing hourly, monthly, and annual savings estimates.
        """
        if not hourly_price:
            return {'hourly': 0, 'monthly': 0, 'annual': 0}
            
        monthly = hourly_price * HOURS_PER_MONTH  # Average hours per month
        return {
            'hourly': hourly_price,
            'monthly': monthly,
            'annual': monthly * 12
        }

    @staticmethod
    def calculate_ec2_savings(hourly_price: float) -> Dict:
        """Calculate savings for stopping/terminating an EC2 instance.
        
        Args:
            hourly_price: The hourly cost of the EC2 instance in USD.
            
        Returns:
            Dictionary containing hourly, monthly, and annual savings estimates.
        """
        if not hourly_price:
            return {'hourly': 0, 'monthly': 0, 'annual': 0}
            
        monthly = hourly_price * HOURS_PER_MONTH
        return {
            'hourly': hourly_price,
            'monthly': monthly,
            'annual': monthly * 12
        }

    @staticmethod
    def calculate_s3_savings(size_gb: float, storage_class: str = DEFAULT_S3_STORAGE_CLASS, region: str = 'us-east-1') -> Dict:
        """Calculate savings for deleting/archiving an S3 bucket."""
        if not size_gb:
            return {'monthly': 0, 'annual': 0}
            
        try:
            from etl.s3_pricing_loader import S3PricingLoader
            loader = S3PricingLoader()
            cost_per_gb = loader.get_s3_price(storage_class, region)
        except Exception:
            # Final fallback
            cost_per_gb = S3_STORAGE_COSTS.get(storage_class, S3_STORAGE_COSTS[DEFAULT_S3_STORAGE_CLASS])
            
        monthly = size_gb * cost_per_gb
        return {
            'monthly': monthly,
            'annual': monthly * 12
        }
    
    @staticmethod
    def calculate_ebs_cost(size_gb: int, volume_type: str, 
                          iops: int = None, region: str = 'us-east-1') -> Dict:
        """Calculate monthly EBS cost for a volume."""
        from etl.ebs_pricing_loader import EBSPricingLoader
        from core.constants import DEFAULT_EBS_STORAGE_COST, DAYS_PER_MONTH
        
        try:
            loader = EBSPricingLoader()
            return loader.calculate_volume_cost(size_gb, volume_type, iops, region)
        except Exception:
            # Fallback for extreme cases where loader fails
            price_per_gb = DEFAULT_EBS_STORAGE_COST
            monthly = size_gb * price_per_gb
            return {
                'monthly': monthly,
                'daily': monthly / DAYS_PER_MONTH,
                'annual': monthly * 12,
                'base_cost': monthly,
                'iops_cost': 0,
                'price_per_gb': price_per_gb
            }
    
    @staticmethod
    def calculate_environment_costs(db_path: str = None) -> Dict:
        """Aggregate EBS costs by environment tag.
        
        Args:
            db_path: Path to the ETL database.
            
        Returns:
            Dictionary mapping environment names to cost summaries.
        """
        import sqlite3
        from core.config import Config
        
        db_path = db_path or Config.ETL_DB_PATH
        
        env_costs = defaultdict(lambda: {
            'instance_count': 0,  # Number of EC2 instances
            'volume_count': 0,    # Number of EBS volumes
            'total_size_gb': 0,
            'monthly_cost': 0,
            'ec2_instances': [],
            'ebs_volumes': []
        })
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Get EC2 instances with environment tags
            cursor = conn.execute('''
                SELECT instance_id, environment_tag, name, instance_class, region
                FROM raw_instances 
                WHERE service_type = 'EC2'
            ''')
            
            for row in cursor.fetchall():
                env = row['environment_tag'] or 'Unknown'
                env_costs[env]['instance_count'] += 1
                env_costs[env]['ec2_instances'].append({
                    'instance_id': row['instance_id'],
                    'name': row['name'],
                    'instance_class': row['instance_class'],
                    'region': row['region']
                })
            
            # Get EBS volumes with environment tags and costs
            cursor = conn.execute('''
                SELECT volume_id, attached_instance_id, environment_tag, size_gb, 
                       volume_type, monthly_cost, region
                FROM raw_instances 
                WHERE service_type = 'EBS'
            ''')
            
            for row in cursor.fetchall():
                env = row['environment_tag'] or 'Unknown'
                env_costs[env]['volume_count'] += 1
                env_costs[env]['total_size_gb'] += row['size_gb'] or 0
                env_costs[env]['monthly_cost'] += row['monthly_cost'] or 0
                env_costs[env]['ebs_volumes'].append({
                    'volume_id': row['volume_id'],
                    'attached_instance_id': row['attached_instance_id'],
                    'size_gb': row['size_gb'],
                    'volume_type': row['volume_type'],
                    'monthly_cost': row['monthly_cost'],
                    'region': row['region']
                })
            
            # Calculate daily and yearly costs
            for env, data in env_costs.items():
                data['daily_cost'] = data['monthly_cost'] / 30
                data['yearly_cost'] = data['monthly_cost'] * 12
            
            return dict(env_costs)
            
        except sqlite3.OperationalError as e:
            logger.error(f"Database error in get_ebs_costs_by_env: {e}")
            return {}
        finally:
            conn.close()
    
    @staticmethod
    def get_ebs_costs_by_instance(db_path: str = None) -> Dict:
        """Get EBS costs grouped by EC2 instance.
        
        Args:
            db_path: Path to the ETL database.
            
        Returns:
            Dictionary mapping EC2 instance IDs to their EBS costs.
        """
        import sqlite3
        from core.config import Config
        
        db_path = db_path or Config.ETL_DB_PATH
        
        instance_costs = {}
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute('''
                SELECT attached_instance_id, 
                       COUNT(*) as volume_count,
                       SUM(size_gb) as total_size_gb,
                       SUM(monthly_cost) as total_monthly_cost
                FROM raw_instances 
                WHERE service_type = 'EBS' AND attached_instance_id IS NOT NULL
                GROUP BY attached_instance_id
            ''')
            
            for row in cursor.fetchall():
                instance_id = row['attached_instance_id']
                monthly = row['total_monthly_cost'] or 0
                instance_costs[instance_id] = {
                    'volume_count': row['volume_count'],
                    'total_size_gb': row['total_size_gb'] or 0,
                    'monthly_cost': monthly,
                    'daily_cost': monthly / 30,
                    'yearly_cost': monthly * 12
                }
            
            return instance_costs
            
        except sqlite3.OperationalError as e:
            logger.error(f"Database error in get_ebs_costs_by_instance: {e}")
            return {}
        finally:
            conn.close()
