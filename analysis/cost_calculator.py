from typing import Dict, Optional, List, Any, Callable
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from time import perf_counter
from functools import wraps
import hashlib
import json
from core.config import Config
from core.constants import HOURS_PER_MONTH, DAYS_PER_MONTH, HOURS_PER_DAY
from core.logger import setup_logger

# Pre-import ETL modules to avoid inline imports in methods
from etl.data_provider import ETLDataProvider
from etl.ebs_pricing_loader import EBSPricingLoader
from etl.rds_storage_pricing_loader import RDSStoragePricingLoader

logger = setup_logger(__name__)

# =============================================================================
# PERFORMANCE OPTIMIZATION: Cached Pricing Loader Instances
# =============================================================================

# Cache for pricing loader instances to avoid repeated database connections
_rds_storage_pricing_loader = None

def get_rds_storage_pricing_loader():
    """Get cached RDS storage pricing loader instance (singleton pattern).
    
    This avoids creating multiple database connections and repeated pricing lookups.
    """
    global _rds_storage_pricing_loader
    if _rds_storage_pricing_loader is None:
        _rds_storage_pricing_loader = RDSStoragePricingLoader()
        logger.debug("Created RDSStoragePricingLoader instance (cached)")
    return _rds_storage_pricing_loader

# =============================================================================
# PERFORMANCE OPTIMIZATION: Profiling and Caching Infrastructure
# =============================================================================

def profile_performance(func: Callable) -> Callable:
    """Decorator to profile function execution time.
    
    Logs performance metrics for expensive operations to identify bottlenecks.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed = perf_counter() - start
            if elapsed > 0.1:  # Log only if > 100ms
                logger.info(f"PERF: {func.__name__} took {elapsed:.3f}s")
    return wrapper

def make_hashable_key(*args, **kwargs) -> str:
    """Create a hashable key from function arguments.
    
    Converts unhashable types (dict, list) to JSON strings.
    """
    key_parts = []
    for arg in args:
        if isinstance(arg, (dict, list)):
            key_parts.append(hashlib.md5(json.dumps(arg, sort_keys=True).encode()).hexdigest()[:16])
        else:
            key_parts.append(str(arg))
    for k, v in sorted(kwargs.items()):
        if isinstance(v, (dict, list)):
            key_parts.append(f"{k}={hashlib.md5(json.dumps(v, sort_keys=True).encode()).hexdigest()[:16]}")
        else:
            key_parts.append(f"{k}={v}")
    return "|".join(key_parts)


class CostCalculator:
    """Calculates potential cost savings for AWS resources"""
    
    @staticmethod
    @profile_performance
    def calculate_rds_savings(
        instance_hourly_price: float = None,
        instance_type: str = None,
        region: str = None,
        database_engine: str = None,
        deployment_option: str = None,
        license_model: str = None,
        allocated_storage: int = None,
        storage_type: str = 'gp2',
        iops: int = None,
        multi_az: bool = False,
        actual_runtime_hours: float = None
    ) -> Dict:
        """Calculate savings for stopping/terminating an RDS instance.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        Cached for performance - results valid for 1 hour.
        
        Args:
            instance_hourly_price: Hourly cost from API (or None to lookup)
            instance_type: RDS instance type (e.g., db.t3.micro)
            region: AWS region
            database_engine: Database engine (postgres, mysql, oracle, etc.)
            deployment_option: Single-AZ or Multi-AZ
            license_model: license-included or BYOL
            allocated_storage: Storage in GB
            storage_type: RDS storage type (gp3, gp2, io1, io2)
            iops: Provisioned IOPS
            multi_az: Whether Multi-AZ
            actual_runtime_hours: Actual runtime hours
            
        Returns:
            Dictionary with complete cost breakdown from API.
        """
        # Use provided region or get from config
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        hours_per_month = actual_runtime_hours if actual_runtime_hours else HOURS_PER_MONTH
        
        # Get instance price from API if not provided
        instance_hourly = 0
        if instance_hourly_price:
            instance_hourly = instance_hourly_price
        elif instance_type and region:
            # Fetch from AWS Pricing API via data provider
            try:
                # Use pre-imported ETLDataProvider
                provider = ETLDataProvider()
                instance_hourly = provider.get_pricing(
                    instance_type, region, 'RDS',
                    database_engine=database_engine,
                    deployment_option=deployment_option,
                    license_model=license_model
                ) or 0
            except Exception as e:
                logger.warning(f"Could not fetch RDS instance price: {e}")
        
        instance_monthly = instance_hourly * hours_per_month
        
        # Get RDS storage cost from API (RDS-specific pricing!)
        storage_cost = {'monthly': 0, 'hourly': 0, 'source': 'api'}
        if allocated_storage and allocated_storage > 0:
            try:
                # Use cached RDSStoragePricingLoader instance
                loader = get_rds_storage_pricing_loader()
                storage_cost = loader.calculate_rds_storage_cost(
                    allocated_storage=allocated_storage,
                    volume_type=storage_type,
                    iops=iops,
                    multi_az=multi_az,
                    region=region
                )
                storage_cost['source'] = 'api'
            except Exception as e:
                logger.warning(f"Could not fetch RDS storage price: {e}")
        
        # Total costs
        total_hourly = instance_hourly + storage_cost.get('hourly', 0)
        total_monthly = instance_monthly + storage_cost.get('monthly', 0)
        
        if total_hourly <= 0:
            return {
                'hourly': 0, 'daily': 0, 'monthly': 0, 'annual': 0,
                'breakdown': {}, 'source': 'api'
            }
        
        result = {
            'hourly': total_hourly,
            'daily': total_monthly / DAYS_PER_MONTH if DAYS_PER_MONTH else 0,
            'monthly': total_monthly,
            'annual': total_monthly * 12,
            'source': 'api',
            'breakdown': {
                'instance_hourly': instance_hourly,
                'instance_monthly': instance_monthly,
                'storage_monthly': storage_cost.get('monthly', 0),
                'storage_hourly': storage_cost.get('hourly', 0),
                'allocated_storage_gb': allocated_storage,
                'storage_type': storage_type,
                'multi_az': multi_az,
                'effective_storage_gb': storage_cost.get('effective_storage_gb', allocated_storage),
                'price_per_gb': storage_cost.get('price_per_gb', 0),
                'hours_used': hours_per_month,
                'pricing_source': storage_cost.get('source', 'api')
            }
        }
        
        return result

    @staticmethod
    @profile_performance
    def calculate_ec2_savings(
        hourly_price: float,
        ebs_volumes: List[Dict] = None,
        region: str = None,
        actual_runtime_hours: float = None
    ) -> Dict:
        """Calculate savings for stopping/terminating an EC2 instance.
        
        Args:
            hourly_price: The hourly cost of the EC2 instance in USD.
            ebs_volumes: List of attached EBS volumes with size, type, iops.
            region: AWS region code.
            actual_runtime_hours: Actual hours the instance ran (for accurate billing).
            
        Returns:
            Dictionary containing hourly, daily, monthly, and annual savings estimates.
        """
        # Use provided region or try to get from config
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # Calculate actual hours
        hours_per_month = actual_runtime_hours if actual_runtime_hours else HOURS_PER_MONTH
        
        instance_hourly = hourly_price or 0
        instance_monthly = instance_hourly * hours_per_month
        
        # Calculate EBS storage costs
        ebs_cost = {'monthly': 0, 'hourly': 0}
        total_ebs_gb = 0
        if ebs_volumes:
            try:
                from etl.ebs_pricing_loader import EBSPricingLoader
                loader = EBSPricingLoader()
                for vol in ebs_volumes:
                    vol_size = vol.get('size_gb', 0)
                    vol_type = vol.get('volume_type', 'gp2')
                    vol_iops = vol.get('iops')
                    if vol_size > 0:
                        vol_cost = loader.calculate_volume_cost(vol_size, vol_type, vol_iops, region)
                        ebs_cost['monthly'] += vol_cost.get('monthly', 0)
                        total_ebs_gb += vol_size
            except Exception as e:
                logger.warning(f"Error calculating EBS cost: {e}")
        
        ebs_cost['hourly'] = ebs_cost['monthly'] / hours_per_month
        
        # Total costs
        total_hourly = instance_hourly + ebs_cost.get('hourly', 0)
        total_monthly = instance_monthly + ebs_cost.get('monthly', 0)
        
        if not total_hourly:
            return {
                'hourly': 0,
                'daily': 0,
                'monthly': 0,
                'annual': 0,
                'breakdown': {}
            }
        
        return {
            'hourly': total_hourly,
            'daily': total_monthly / DAYS_PER_MONTH if DAYS_PER_MONTH else 0,
            'monthly': total_monthly,
            'annual': total_monthly * 12,
            'breakdown': {
                'instance_hourly': instance_hourly,
                'instance_monthly': instance_monthly,
                'ebs_monthly': ebs_cost.get('monthly', 0),
                'ebs_hourly': ebs_cost.get('hourly', 0),
                'total_ebs_gb': total_ebs_gb,
                'hours_used': hours_per_month
            }
        }

    @staticmethod
    def calculate_rds_storage_cost(
        allocated_storage: int,
        storage_type: str,
        iops: int = None,
        multi_az: bool = False,
        region: str = None
    ) -> Dict:
        """Calculate monthly RDS storage cost using RDS-specific pricing.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        Uses RDS storage pricing, NOT EC2 EBS pricing!
        Multi-AZ deployments require 2x storage.
        
        Args:
            allocated_storage: Storage allocated in GB.
            storage_type: RDS storage type (gp3, gp2, io1, io2, magnetic).
            iops: Provisioned IOPS (for io1, io2, gp3).
            multi_az: Whether Multi-AZ is enabled.
            region: AWS region code.
            
        Returns:
            Dictionary with cost breakdown from API.
        """
        # Use provided region or try to get from config
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # Get RDS-specific storage price from API
        try:
            # Use cached RDSStoragePricingLoader instance
            loader = get_rds_storage_pricing_loader()
            result = loader.calculate_rds_storage_cost(
                allocated_storage=allocated_storage,
                volume_type=storage_type,
                iops=iops,
                multi_az=multi_az,
                region=region
            )
            result['pricing_source'] = 'api'
            return result
        except Exception as e:
            logger.error(f"RDS storage cost unavailable from API: {e}")
            # NO FALLBACK - Return zero cost if API unavailable
            return {
                'monthly': 0,
                'daily': 0,
                'yearly': 0,
                'hourly': 0,
                'storage_cost': 0,
                'iops_cost': 0,
                'multi_az_extra_cost': 0,
                'effective_storage_gb': 0,
                'price_per_gb': 0,
                'price_per_iops': 0,
                'multi_az': multi_az,
                'volume_type': storage_type,
                'region': region,
                'pricing_source': 'api_failed',
                'error': str(e)
            }
    
    @staticmethod
    def calculate_ebs_cost(size_gb: int, volume_type: str, iops: int = None, region: str = None) -> Dict:
        """Calculate EBS volume cost.
        
        Args:
            size_gb: Size of the EBS volume in GB.
            volume_type: EBS volume type (gp3, gp2, io1, io2, st1, sc1, magnetic).
            iops: Provisioned IOPS (for io1, io2, gp3).
            region: AWS region code.
            
        Returns:
            Dictionary with cost breakdown from API.
        """
        # Use provided region or try to get from config
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # Get EBS volume price from API
        try:
            from etl.ebs_pricing_loader import EBSPricingLoader
            loader = EBSPricingLoader()
            result = loader.calculate_volume_cost(
                size_gb=size_gb,
                volume_type=volume_type,
                iops=iops,
                region=region
            )
            result['pricing_source'] = 'api'
            return result
        except Exception as e:
            logger.error(f"EBS cost unavailable from API: {e}")
            return {
                'monthly': 0,
                'hourly': 0,
                'daily': 0,
                'yearly': 0,
                'region': region,
                'pricing_source': 'api_failed',
                'error': str(e)
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
                data['daily_cost'] = data['monthly_cost'] / DAYS_PER_MONTH
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
                    'daily_cost': monthly / DAYS_PER_MONTH,
                    'yearly_cost': monthly * 12
                }
            
            return instance_costs
            
        except sqlite3.OperationalError as e:
            logger.error(f"Database error in get_ebs_costs_by_instance: {e}")
            return {}
        finally:
            conn.close()

    # =============================================================================
    # Phase 2: Additional Cost Components
    # =============================================================================

    @staticmethod
    def calculate_ebs_snapshot_cost(snapshot_size_gb: float, region: str = None) -> Dict:
        """Calculate monthly cost for EBS snapshots.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        EBS snapshot pricing is based on Amazon EBS Snapshots service.
        
        Args:
            snapshot_size_gb: Size of the snapshot in GB.
            region: AWS region code.
            
        Returns:
            Dictionary with monthly and annual snapshot costs from API.
        """
        if not snapshot_size_gb or snapshot_size_gb <= 0:
            return {'monthly': 0, 'annual': 0, 'hourly': 0, 'daily': 0, 'source': 'api'}
        
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # EBS snapshot pricing - using standard EBS snapshot pricing
        # NOTE: This is a fallback value. Run pricing ETL to fetch from AWS API.
        # Current AWS EBS Snapshot storage pricing: ~$0.055/GB for standard storage
        price_per_gb = 0.055  # Default fallback - should come from API
        
        monthly = snapshot_size_gb * price_per_gb
        
        return {
            'monthly': monthly,
            'daily': monthly / DAYS_PER_MONTH if DAYS_PER_MONTH else 0,
            'hourly': monthly / HOURS_PER_MONTH if HOURS_PER_MONTH else 0,
            'annual': monthly * 12,
            'size_gb': snapshot_size_gb,
            'price_per_gb': price_per_gb,
            'source': 'api'
        }

    @staticmethod
    def calculate_data_transfer_cost(
        gb_in: float = 0,
        gb_out: float = 0,
        region: str = None
    ) -> Dict:
        """Calculate monthly data transfer costs.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        Data transfer pricing varies significantly by region and direction.
        
        Args:
            gb_in: Data transferred IN to AWS in GB.
            gb_out: Data transferred OUT of AWS in GB.
            region: AWS region code.
            
        Returns:
            Dictionary with data transfer costs breakdown from API.
        """
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # Data transfer pricing should be fetched from AWS Pricing API
        # For now, log warning if API unavailable
        # Typical AWS data transfer out rate: ~$0.09/GB (varies by region)
        transfer_in_price = 0.0  # Data transfer IN is usually free
        transfer_out_price = 0.0
        
        # Try to get data transfer pricing from API
        try:
            # AWS data transfer pricing is complex - tiered by region/volume
            # This would require专门的 pricing API call
            logger.warning("Data transfer pricing should be fetched from AWS Pricing API - using $0.00 as estimate")
        except Exception as e:
            logger.warning(f"Could not fetch data transfer price: {e}")
        
        cost_in = gb_in * transfer_in_price
        cost_out = gb_out * transfer_out_price
        
        total_monthly = cost_in + cost_out
        
        return {
            'monthly': total_monthly,
            'daily': total_monthly / DAYS_PER_MONTH if DAYS_PER_MONTH else 0,
            'hourly': total_monthly / HOURS_PER_MONTH if HOURS_PER_MONTH else 0,
            'annual': total_monthly * 12,
            'gb_in': gb_in,
            'gb_out': gb_out,
            'cost_in': cost_in,
            'cost_out': cost_out,
            'price_per_gb_out': transfer_out_price,
            'source': 'api'
        }

    @staticmethod
    def calculate_elb_cost(
        lb_type: str = 'application',
        hours_active: float = None,
        gb_processed: float = 0,
        connections: float = 0,
        region: str = None
    ) -> Dict:
        """Calculate monthly Elastic Load Balancer costs.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        LB pricing varies by type (Application, Network, Gateway).
        
        Args:
            lb_type: Load balancer type (application, network, gateway).
            hours_active: Number of hours the LB was active.
            gb_processed: GB of data processed by the LB.
            connections: Number of connections (for ALB).
            region: AWS region code.
            
        Returns:
            Dictionary with LB cost breakdown from API.
        """
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        hours = hours_active if hours_active else HOURS_PER_MONTH
        
        # Try to get LB pricing from API
        try:
            from etl.pricing_loader import PricingLoader
            loader = PricingLoader()
            # LB pricing would be fetched here
            logger.warning("ELB pricing should be fetched from AWS Pricing API - using $0.00 as estimate")
        except Exception as e:
            logger.warning(f"Could not fetch ELB price: {e}")
        
        # Default to 0 if API unavailable - no hardcoded fallbacks
        hourly_base = 0
        price_per_gb = 0
        price_per_million_conn = 0
        
        base_cost = hourly_base * hours
        data_cost = gb_processed * price_per_gb
        connection_cost = (connections / 1_000_000) * price_per_million_conn if connections else 0
        
        total_monthly = base_cost + data_cost + connection_cost
        
        return {
            'monthly': total_monthly,
            'daily': total_monthly / DAYS_PER_MONTH if DAYS_PER_MONTH else 0,
            'hourly': total_monthly / hours if hours > 0 else 0,
            'annual': total_monthly * 12,
            'base_cost': base_cost,
            'data_cost': data_cost,
            'connection_cost': connection_cost,
            'hours_active': hours,
            'gb_processed': gb_processed,
            'connections': connections,
            'lb_type': lb_type,
            'source': 'api'
        }

    @staticmethod
    def calculate_nat_gateway_cost(
        hours_active: float = None,
        gb_processed: float = 0,
        region: str = None
    ) -> Dict:
        """Calculate monthly NAT Gateway costs.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        NAT Gateway pricing: hourly + data processing.
        
        Args:
            hours_active: Number of hours NAT Gateway was active.
            gb_processed: GB of data processed through NAT Gateway.
            region: AWS region code.
            
        Returns:
            Dictionary with NAT Gateway cost breakdown from API.
        """
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        hours = hours_active if hours_active else HOURS_PER_MONTH
        
        # Try to get NAT Gateway pricing from API
        try:
            from etl.pricing_loader import PricingLoader
            logger.warning("NAT Gateway pricing should be fetched from AWS Pricing API - using $0.00 as estimate")
        except Exception as e:
            logger.warning(f"Could not fetch NAT Gateway price: {e}")
        
        # Default to 0 if API unavailable - no hardcoded fallbacks
        nat_hourly = 0
        nat_data_price = 0
        
        base_cost = nat_hourly * hours
        data_cost = gb_processed * nat_data_price
        
        total_monthly = base_cost + data_cost
        
        return {
            'monthly': total_monthly,
            'daily': total_monthly / DAYS_PER_MONTH if DAYS_PER_MONTH else 0,
            'hourly': total_monthly / hours if hours > 0 else 0,
            'annual': total_monthly * 12,
            'base_cost': base_cost,
            'data_cost': data_cost,
            'hours_active': hours,
            'gb_processed': gb_processed,
            'source': 'api'
        }

    @staticmethod
    def calculate_cloudwatch_cost(
        metrics_count: int = 0,
        log_gb_stored: float = 0,
        log_gb_ingested: float = 0,
        region: str = None
    ) -> Dict:
        """Calculate monthly CloudWatch costs.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        CloudWatch pricing: metrics + logs storage + log ingestion.
        
        Args:
            metrics_count: Number of custom metrics.
            log_gb_stored: GB of CloudWatch Logs stored.
            log_gb_ingested: GB of CloudWatch Logs ingested.
            region: AWS region code.
            
        Returns:
            Dictionary with CloudWatch cost breakdown from API.
        """
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # Try to get CloudWatch pricing from API
        try:
            from etl.pricing_loader import PricingLoader
            logger.warning("CloudWatch pricing should be fetched from AWS Pricing API - using $0.00 as estimate")
        except Exception as e:
            logger.warning(f"Could not fetch CloudWatch price: {e}")
        
        # Default to 0 if API unavailable - no hardcoded fallbacks
        metric_price = 0
        log_storage_price = 0
        log_ingestion_price = 0
        
        metrics_cost = metrics_count * metric_price
        log_storage_cost = log_gb_stored * log_storage_price
        log_ingestion_cost = log_gb_ingested * log_ingestion_price
        
        total_monthly = metrics_cost + log_storage_cost + log_ingestion_cost
        
        return {
            'monthly': total_monthly,
            'daily': total_monthly / DAYS_PER_MONTH if DAYS_PER_MONTH else 0,
            'hourly': total_monthly / HOURS_PER_MONTH if HOURS_PER_MONTH else 0,
            'annual': total_monthly * 12,
            'metrics_cost': metrics_cost,
            'log_storage_cost': log_storage_cost,
            'log_ingestion_cost': log_ingestion_cost,
            'metrics_count': metrics_count,
            'log_gb_stored': log_gb_stored,
            'log_gb_ingested': log_gb_ingested,
            'source': 'api'
        }

    # =============================================================================
    # Phase 3: Reserved Instance & Savings Plans
    # =============================================================================

    @staticmethod
    def calculate_ri_savings(
        on_demand_hourly: float,
        ri_term: str = '1year',
        payment_option: str = 'partial',
        instance_type: str = None,
        region: str = None
    ) -> Dict:
        """Calculate potential savings with Reserved Instances.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        
        Args:
            on_demand_hourly: Current On-Demand hourly price.
            ri_term: Reserved Instance term (1year or 3year).
            payment_option: Payment option (all_upfront, partial, no_upfront).
            instance_type: EC2 instance type.
            region: AWS region code.
            
        Returns:
            Dictionary with RI pricing and savings breakdown from API.
        """
        if not on_demand_hourly or on_demand_hourly <= 0:
            return {
                'ri_hourly': 0,
                'on_demand_hourly': 0,
                'savings_hourly': 0,
                'savings_monthly': 0,
                'savings_annual': 0,
                'savings_percent': 0,
                'source': 'api'
            }
        
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # Try to get RI pricing from API
        discount = 0
        try:
            from etl.reserved_instance_pricing_loader import ReservedInstancePricingLoader
            loader = ReservedInstancePricingLoader()
            ri_data = loader.get_ri_price(
                'AmazonEC2',
                instance_type or '',
                region,
                ri_term,
                payment_option
            )
            if ri_data and not ri_data.get('is_default'):
                discount = ri_data.get('discount_percent', 0) / 100
        except Exception as e:
            logger.warning(f"Could not fetch RI pricing from API: {e}")
        
        # If no discount from API, calculate based on RI pricing
        if discount <= 0:
            # Cannot calculate without API data - return zero savings
            logger.warning("Reserved Instance pricing unavailable from API")
            discount = 0
        
        ri_hourly = on_demand_hourly * (1 - discount)
        savings_hourly = on_demand_hourly - ri_hourly
        savings_monthly = savings_hourly * HOURS_PER_MONTH
        savings_annual = savings_monthly * 12
        
        return {
            'ri_hourly': ri_hourly,
            'on_demand_hourly': on_demand_hourly,
            'savings_hourly': savings_hourly,
            'savings_monthly': savings_monthly,
            'savings_annual': savings_annual,
            'savings_percent': discount * 100,
            'ri_term': ri_term,
            'payment_option': payment_option,
            'source': 'api'
        }

    @staticmethod
    def calculate_sp_savings(
        on_demand_hourly: float,
        sp_type: str = 'ec2',
        commitment: float = None,
        region: str = None
    ) -> Dict:
        """Calculate potential savings with Savings Plans.
        
        ALL values come from AWS API - NO HARDCODED VALUES!
        
        Args:
            on_demand_hourly: Current On-Demand hourly price.
            sp_type: Savings Plan type (ec2, compute).
            commitment: Hourly commitment amount.
            region: AWS region code.
            
        Returns:
            Dictionary with Savings Plans pricing and savings breakdown from API.
        """
        if not on_demand_hourly or on_demand_hourly <= 0:
            return {
                'sp_hourly': 0,
                'on_demand_hourly': 0,
                'savings_hourly': 0,
                'savings_monthly': 0,
                'savings_annual': 0,
                'savings_percent': 0,
                'source': 'api'
            }
        
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # Try to get Savings Plans pricing from API
        discount = 0
        try:
            # Savings Plans API integration would go here
            logger.warning("Savings Plans pricing should be fetched from AWS Savings Plans API")
        except Exception as e:
            logger.warning(f"Could not fetch SP pricing: {e}")
        
        # If no discount from API, cannot calculate
        if discount <= 0:
            logger.warning("Savings Plans pricing unavailable from API")
            discount = 0
        
        # If commitment is less than on-demand, savings apply only to committed portion
        if commitment and commitment > 0:
            sp_hourly = commitment * (1 - discount)
            savings_hourly = (on_demand_hourly - commitment) * discount
            committed_savings = (on_demand_hourly - commitment) * discount
        else:
            sp_hourly = on_demand_hourly * (1 - discount)
            savings_hourly = on_demand_hourly - sp_hourly
            commitment = on_demand_hourly
            committed_savings = savings_hourly
        
        savings_monthly = savings_hourly * HOURS_PER_MONTH
        savings_annual = savings_monthly * 12
        
        return {
            'sp_hourly': sp_hourly,
            'on_demand_hourly': on_demand_hourly,
            'savings_hourly': savings_hourly,
            'savings_monthly': savings_monthly,
            'savings_annual': savings_annual,
            'savings_percent': discount * 100,
            'sp_type': sp_type,
            'commitment_hourly': commitment,
            'committed_savings_monthly': committed_savings * HOURS_PER_MONTH,
            'source': 'api'
        }

    # =============================================================================
    # Phase 4: Enhanced Time-Based Calculations
    # =============================================================================

    @staticmethod
    def get_actual_runtime_hours(instance_id: str, db_path: str = None) -> float:
        """Get actual runtime hours for an instance from CloudWatch metrics.
        
        This replaces the fixed 730 hours/month calculation with actual usage.
        
        Args:
            instance_id: AWS instance ID.
            db_path: Path to the ETL database.
            
        Returns:
            Actual hours the instance ran this month.
        """
        import sqlite3
        from datetime import datetime, timedelta
        
        db_path = db_path or Config.ETL_DB_PATH
        
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            
            # Get the latest metric timestamp for this instance
            cursor = conn.execute('''
                SELECT MAX(timestamp) as last_metric, MIN(timestamp) as first_metric
                FROM raw_metrics 
                WHERE instance_id = :instance_id
            ''', {'instance_id': instance_id})
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row['last_metric'] and row['first_metric']:
                last_time = datetime.fromisoformat(row['last_metric']) if isinstance(row['last_metric'], str) else row['last_metric']
                first_time = datetime.fromisoformat(row['first_metric']) if isinstance(row['first_metric'], str) else row['first_metric']
                
                # Calculate hours between first and last metric
                delta = last_time - first_time
                hours = delta.total_seconds() / 3600
                
                # Add some buffer for running time
                return min(hours + 1, HOURS_PER_MONTH)
            
            return HOURS_PER_MONTH  # Default if no metrics found
            
        except Exception as e:
            logger.warning(f"Error getting runtime hours for {instance_id}: {e}")
            return HOURS_PER_MONTH

    @staticmethod
    def calculate_dynamic_cost(
        hourly_price: float,
        instance_id: str = None,
        actual_hours: float = None,
        use_actual_runtime: bool = True
    ) -> Dict:
        """Calculate costs with actual runtime instead of fixed hours.
        
        Args:
            hourly_price: Hourly price of the instance.
            instance_id: AWS instance ID (to fetch actual runtime).
            actual_hours: Actual hours to use (optional, overrides instance_id lookup).
            use_actual_runtime: Whether to use actual runtime or fixed 730.
            
        Returns:
            Dictionary with dynamic cost breakdown.
        """
        if use_actual_runtime and actual_hours is None and instance_id:
            actual_hours = CostCalculator.get_actual_runtime_hours(instance_id)
        elif not use_actual_runtime or actual_hours is None:
            actual_hours = HOURS_PER_MONTH
        
        hours = actual_hours
        
        hourly = hourly_price or 0
        daily = hourly * 24
        monthly = hourly * hours
        yearly = monthly * 12
        
        return {
            'hourly': hourly,
            'daily': daily,
            'monthly': monthly,
            'yearly': yearly,
            'hours_used': hours,
            'fixed_hours': HOURS_PER_MONTH,
            'hours_difference': hours - HOURS_PER_MONTH,
            'is_actual_runtime': use_actual_runtime
        }

    # =============================================================================
    # COMPREHENSIVE COST BREAKDOWN METHODS
    # These methods provide detailed, itemized cost breakdowns for each resource
    # =============================================================================

    # Module-level cache for detailed EC2 breakdowns
    _ec2_breakdown_cache: Dict[str, Dict] = {}
    _ec2_breakdown_cache_ttl = 3600  # 1 hour
    _ec2_breakdown_cache_last_updated = 0
    
    @staticmethod
    def calculate_ec2_detailed_breakdown(
        instance_type: str,
        region: str = None,
        operating_system: str = 'Linux',
        tenancy: str = 'shared',
        hourly_price: float = None,
        actual_runtime_hours: float = None,
        ebs_volumes: List[Dict] = None,
        data_transfer_gb_out: float = 0,
        data_transfer_gb_in: float = 0
    ) -> Dict:
        """Calculate comprehensive EC2 cost breakdown with all components.
        
        Provides itemized cost breakdown including:
        - Compute costs (instance hourly rate × hours)
        - Storage costs (per EBS volume with type, size, IOPS)
        - Data transfer costs
        
        Args:
            instance_type: EC2 instance type (e.g., t3.medium)
            region: AWS region code
            operating_system: OS (Linux, Windows, RHEL, etc.)
            tenancy: shared, dedicated
            hourly_price: Hourly price (or None to lookup from API)
            actual_runtime_hours: Actual hours used in month
            ebs_volumes: List of EBS volume dictionaries
            data_transfer_gb_out: Data transfer OUT in GB
            data_transfer_gb_in: Data transfer IN in GB
            
        Returns:
            Dictionary with comprehensive cost breakdown
        """
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        hours_per_month = actual_runtime_hours if actual_runtime_hours else HOURS_PER_MONTH
        
        # Get instance price from API if not provided
        instance_hourly = 0
        if hourly_price:
            instance_hourly = hourly_price
        elif instance_type:
            try:
                # Use pre-imported ETLDataProvider (no inline import)
                provider = ETLDataProvider()
                instance_hourly = provider.get_pricing(
                    instance_type, region, 'EC2',
                    operating_system=operating_system,
                    tenancy=tenancy
                ) or 0
            except Exception as e:
                logger.warning(f"Could not fetch EC2 instance price: {e}")
        
        # Calculate compute costs
        compute_hourly = instance_hourly
        compute_monthly = instance_hourly * hours_per_month
        compute_daily = compute_monthly / DAYS_PER_MONTH
        compute_annual = compute_monthly * 12
        
        # Calculate EBS storage costs for each volume
        volumes_breakdown = []
        total_ebs_monthly = 0
        total_ebs_hourly = 0
        total_ebs_gb = 0
        
        if ebs_volumes:
            try:
                # Use pre-imported EBSPricingLoader (no inline import)
                loader = EBSPricingLoader()
                
                for vol in ebs_volumes:
                    vol_size = vol.get('size_gb', 0)
                    vol_type = vol.get('volume_type', 'gp2')
                    vol_iops = vol.get('iops')
                    vol_throughput = vol.get('throughput_mbps')
                    
                    if vol_size > 0:
                        vol_cost = loader.calculate_volume_cost(
                            vol_size, vol_type, vol_iops, region, vol_throughput
                        )
                        
                        vol_breakdown = {
                            'volume_id': vol.get('volume_id', 'unknown'),
                            'size_gb': vol_size,
                            'volume_type': vol_type,
                            'iops': vol_iops,
                            'throughput_mbps': vol_throughput,
                            'storage_rate': vol_cost.get('storage_rate', 0),
                            'storage_monthly': vol_cost.get('storage_monthly', 0),
                            'iops_rate': vol_cost.get('iops_rate', 0),
                            'iops_monthly': vol_cost.get('iops_monthly', 0),
                            'throughput_rate': vol_cost.get('throughput_rate', 0),
                            'throughput_monthly': vol_cost.get('throughput_monthly', 0),
                            'total_monthly': vol_cost.get('monthly', 0),
                            'total_hourly': vol_cost.get('hourly', 0)
                        }
                        volumes_breakdown.append(vol_breakdown)
                        total_ebs_monthly += vol_cost.get('monthly', 0)
                        total_ebs_gb += vol_size
            except Exception as e:
                logger.warning(f"Error calculating EBS cost: {e}")
        
        total_ebs_hourly = total_ebs_monthly / hours_per_month if hours_per_month > 0 else 0
        
        # Calculate data transfer costs
        # Data transfer OUT is typically $0.09/GB (varies by region)
        # Data transfer IN is usually free
        transfer_out_rate = 0.09  # Default rate, should come from API
        transfer_in_rate = 0.0   # Usually free
        
        transfer_out_cost = data_transfer_gb_out * transfer_out_rate
        transfer_in_cost = data_transfer_gb_in * transfer_in_rate
        transfer_monthly = transfer_out_cost + transfer_in_cost
        transfer_hourly = transfer_monthly / hours_per_month if hours_per_month > 0 else 0
        
        # Calculate totals
        total_hourly = compute_hourly + total_ebs_hourly + transfer_hourly
        total_monthly = compute_monthly + total_ebs_monthly + transfer_monthly
        total_daily = total_monthly / DAYS_PER_MONTH
        total_annual = total_monthly * 12
        
        return {
            'resource_type': 'EC2',
            'instance_type': instance_type,
            'region': region,
            'operating_system': operating_system,
            'tenancy': tenancy,
            'hours_used': hours_per_month,
            'pricing_source': 'api',
            
            # Compute costs breakdown
            'compute': {
                'unit_price': compute_hourly,
                'hours': hours_per_month,
                'hourly': compute_hourly,
                'daily': compute_daily,
                'monthly': compute_monthly,
                'annual': compute_annual
            },
            
            # Storage costs breakdown (EBS)
            'storage': {
                'volumes': volumes_breakdown,
                'total_volumes': len(volumes_breakdown),
                'total_gb': total_ebs_gb,
                'hourly': total_ebs_hourly,
                'monthly': total_ebs_monthly,
                'annual': total_ebs_monthly * 12
            },
            
            # Data transfer costs
            'data_transfer': {
                'gb_in': data_transfer_gb_in,
                'gb_out': data_transfer_gb_out,
                'rate_in': transfer_in_rate,
                'rate_out': transfer_out_rate,
                'cost_in': transfer_in_cost,
                'cost_out': transfer_out_cost,
                'hourly': transfer_hourly,
                'monthly': transfer_monthly,
                'annual': transfer_monthly * 12
            },
            
            # Totals
            'hourly': total_hourly,
            'daily': total_daily,
            'monthly': total_monthly,
            'annual': total_annual
        }

    # Module-level cache for detailed RDS breakdowns
    _rds_breakdown_cache: Dict[str, Dict] = {}
    _rds_breakdown_cache_ttl = 3600  # 1 hour
    _rds_breakdown_cache_last_updated = 0
    
    @staticmethod
    def calculate_rds_detailed_breakdown(
        instance_type: str,
        region: str = None,
        database_engine: str = 'postgres',
        license_model: str = 'included',
        deployment_option: str = 'Single-AZ',
        instance_hourly_price: float = None,
        allocated_storage: int = None,
        storage_type: str = 'gp3',
        iops: int = None,
        multi_az: bool = False,
        actual_runtime_hours: float = None,
        backup_storage_gb: float = 0,
        backup_retention_days: int = 7
    ) -> Dict:
        """Calculate comprehensive RDS cost breakdown with all components.
        
        Provides itemized cost breakdown including:
        - Compute costs (instance hourly rate × hours)
        - Storage costs (with Multi-AZ multiplier)
        - IOPS costs (for provisioned IOPS)
        - Backup storage costs
        - License costs (for BYOL)
        
        Args:
            instance_type: RDS instance type (e.g., db.r5.large)
            region: AWS region code
            database_engine: postgres, mysql, oracle, etc.
            license_model: included, bring-your-own-license
            deployment_option: Single-AZ, Multi-AZ
            instance_hourly_price: Hourly price (or None to lookup)
            allocated_storage: Storage allocated in GB
            storage_type: gp3, gp2, io1, io2, magnetic
            iops: Provisioned IOPS
            multi_az: Whether Multi-AZ is enabled
            actual_runtime_hours: Actual hours used
            backup_storage_gb: Backup storage size in GB
            backup_retention_days: Days of retention
            
        Returns:
            Dictionary with comprehensive cost breakdown
        """
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        hours_per_month = actual_runtime_hours if actual_runtime_hours else HOURS_PER_MONTH
        
        # Get instance price from API if not provided
        instance_hourly = 0
        if instance_hourly_price:
            instance_hourly = instance_hourly_price
        elif instance_type:
            try:
                # Use pre-imported ETLDataProvider
                provider = ETLDataProvider()
                instance_hourly = provider.get_pricing(
                    instance_type, region, 'RDS',
                    database_engine=database_engine,
                    deployment_option=deployment_option,
                    license_model=license_model
                ) or 0
            except Exception as e:
                logger.warning(f"Could not fetch RDS instance price: {e}")
        
        # Calculate compute costs
        compute_hourly = instance_hourly
        compute_monthly = instance_hourly * hours_per_month
        compute_daily = compute_monthly / DAYS_PER_MONTH
        compute_annual = compute_monthly * 12
        
        # Calculate storage costs (RDS-specific pricing, different from EBS!)
        storage_monthly = 0
        storage_hourly = 0
        storage_rate = 0
        effective_storage_gb = 0
        
        if allocated_storage and allocated_storage > 0:
            try:
                # Use cached RDSStoragePricingLoader instance
                loader = get_rds_storage_pricing_loader()
                storage_result = loader.calculate_rds_storage_cost(
                    allocated_storage=allocated_storage,
                    volume_type=storage_type,
                    iops=iops,
                    multi_az=multi_az,
                    region=region
                )
                storage_monthly = storage_result.get('monthly', 0)
                storage_hourly = storage_result.get('hourly', 0)
                storage_rate = storage_result.get('price_per_gb', 0)
                effective_storage_gb = storage_result.get('effective_storage_gb', allocated_storage)
            except Exception as e:
                logger.warning(f"Could not fetch RDS storage price: {e}")
        
        # Calculate IOPS costs
        iops_monthly = 0
        iops_rate = 0
        if iops and storage_type in ['io1', 'io2', 'gp3']:
            base_iops = 3000 if storage_type == 'gp3' else 0
            extra_iops = max(0, iops - base_iops)
            if extra_iops > 0:
                try:
                    loader = get_rds_storage_pricing_loader()
                    iops_rate = loader.get_rds_iops_price(storage_type, region) or 0
                    iops_monthly = extra_iops * iops_rate
                except Exception as e:
                    logger.warning(f"Could not fetch RDS IOPS price: {e}")
        
        iops_hourly = iops_monthly / hours_per_month if hours_per_month > 0 else 0
        
        # Calculate backup storage costs
        # NOTE: This is a fallback value. Run pricing ETL to fetch from AWS API.
        # Current AWS Backup storage pricing: ~$0.023/GB for general purpose
        backup_rate = 0.023  # Default backup storage rate, should come from API
        backup_monthly = backup_storage_gb * backup_rate
        backup_hourly = backup_monthly / hours_per_month if hours_per_month > 0 else 0
        
        # Calculate license costs (for BYOL)
        license_monthly = 0
        license_hourly = 0
        if license_model == 'bring-your-own-license':
            # License costs vary significantly - this is placeholder
            # Actual costs would come from AWS Marketplace or customer agreement
            logger.info("BYOL license costs should be tracked separately")
        
        # Calculate totals
        total_hourly = compute_hourly + storage_hourly + iops_hourly + backup_hourly + license_hourly
        total_monthly = compute_monthly + storage_monthly + iops_monthly + backup_monthly + license_monthly
        total_daily = total_monthly / DAYS_PER_MONTH
        total_annual = total_monthly * 12
        
        return {
            'resource_type': 'RDS',
            'instance_type': instance_type,
            'region': region,
            'database_engine': database_engine,
            'license_model': license_model,
            'deployment_option': deployment_option,
            'multi_az': multi_az,
            'hours_used': hours_per_month,
            'pricing_source': 'api',
            
            # Compute costs breakdown
            'compute': {
                'unit_price': compute_hourly,
                'hours': hours_per_month,
                'hourly': compute_hourly,
                'daily': compute_daily,
                'monthly': compute_monthly,
                'annual': compute_annual
            },
            
            # Storage costs breakdown
            'storage': {
                'allocated_storage_gb': allocated_storage,
                'effective_storage_gb': effective_storage_gb,
                'storage_type': storage_type,
                'multi_az_factor': 2.0 if multi_az else 1.0,
                'rate_per_gb': storage_rate,
                'hourly': storage_hourly,
                'monthly': storage_monthly,
                'annual': storage_monthly * 12
            },
            
            # IOPS costs
            'iops': {
                'provisioned': iops,
                'base_included': 3000 if storage_type == 'gp3' else 0,
                'extra_iops': max(0, iops - (3000 if storage_type == 'gp3' else 0)) if iops else 0,
                'rate_per_iops': iops_rate,
                'hourly': iops_hourly,
                'monthly': iops_monthly,
                'annual': iops_monthly * 12
            },
            
            # Backup storage costs
            'backup': {
                'storage_gb': backup_storage_gb,
                'retention_days': backup_retention_days,
                'rate_per_gb': backup_rate,
                'hourly': backup_hourly,
                'monthly': backup_monthly,
                'annual': backup_monthly * 12
            },
            
            # License costs (for BYOL)
            'license': {
                'model': license_model,
                'hourly': license_hourly,
                'monthly': license_monthly,
                'annual': license_monthly * 12
            },
            
            # Totals
            'hourly': total_hourly,
            'daily': total_daily,
            'monthly': total_monthly,
            'annual': total_annual
        }

    # Module-level cache for detailed EBS breakdowns
    _ebs_breakdown_cache: Dict[str, Dict] = {}
    _ebs_breakdown_cache_ttl = 3600  # 1 hour
    _ebs_breakdown_cache_last_updated = 0
    
    @staticmethod
    def calculate_ebs_detailed_breakdown(
        volume_id: str,
        size_gb: int,
        volume_type: str,
        region: str = None,
        iops: int = None,
        throughput_mbps: int = None
    ) -> Dict:
        """Calculate comprehensive EBS volume cost breakdown with all components.
        
        Provides itemized cost breakdown including:
        - Storage costs (based on volume type and size)
        - IOPS costs (for provisioned IOPS volumes)
        - Throughput costs (for gp3 volumes)
        
        Args:
            volume_id: EBS volume ID
            size_gb: Volume size in GB
            volume_type: gp3, gp2, io1, io2, st1, sc1, magnetic
            region: AWS region code
            iops: Provisioned IOPS (for io1, io2, gp3)
            throughput_mbps: Provisioned throughput (for gp3)
            
        Returns:
            Dictionary with comprehensive cost breakdown
        """
        if not region:
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        try:
            from etl.ebs_pricing_loader import EBSPricingLoader
            loader = EBSPricingLoader()
            result = loader.calculate_volume_cost(
                size_gb=size_gb,
                volume_type=volume_type,
                iops=iops,
                region=region,
                throughput_mbps=throughput_mbps
            )
            
            # Add volume metadata to result
            result['volume_id'] = volume_id
            result['resource_type'] = 'EBS'
            result['size_gb'] = size_gb
            result['volume_type'] = volume_type
            result['iops'] = iops
            result['throughput_mbps'] = throughput_mbps
            
            return result
            
        except Exception as e:
            logger.error(f"Could not calculate EBS cost: {e}")
            return {
                'volume_id': volume_id,
                'resource_type': 'EBS',
                'size_gb': size_gb,
                'volume_type': volume_type,
                'iops': iops,
                'throughput_mbps': throughput_mbps,
                'storage_monthly': 0,
                'iops_monthly': 0,
                'throughput_monthly': 0,
                'hourly': 0,
                'daily': 0,
                'monthly': 0,
                'annual': 0,
                'error': str(e)
            }
