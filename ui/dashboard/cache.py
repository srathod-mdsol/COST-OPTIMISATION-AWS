"""Functions for dashboard data retrieval.

This module contains all data fetching functions used by the dashboard.
All functions fetch fresh data to ensure accurate cost calculations.
"""

import streamlit as st
import os
from typing import Dict, List, Optional

from core.config import Config
from core.logger import setup_logger
from core.constants import HOURS_PER_MONTH
from services.rds_manager import RDSManager
from services.ec2_manager import EC2Manager
from services.ebs_manager import EBSManager
from etl.data_provider import ETLDataProvider

logger = setup_logger(__name__)


# =============================================================================
# FUNCTIONS FOR COST CALCULATIONS
# =============================================================================

def get_ec2_detailed_breakdown_cached(
    instance_type: str,
    region: str,
    operating_system: str,
    tenancy: str,
    hourly_price: float,
    env: str,
    ebs_volumes_json: str  # JSON serialized for hashable cache key
) -> Dict:
    """Get EC2 detailed cost breakdown - fetches fresh data each time for accuracy.
    
    No caching to ensure accurate cost calculations.
    """
    import json
    from analysis.cost_calculator import CostCalculator
    
    ebs_volumes = json.loads(ebs_volumes_json) if ebs_volumes_json else []
    
    return CostCalculator.calculate_ec2_detailed_breakdown(
        instance_type=instance_type,
        region=region,
        operating_system=operating_system,
        tenancy=tenancy,
        hourly_price=hourly_price,
        actual_runtime_hours=HOURS_PER_MONTH,
        ebs_volumes=ebs_volumes
    )


def get_rds_detailed_breakdown_cached(
    instance_type: str,
    region: str,
    database_engine: str,
    license_model: str,
    deployment_option: str,
    instance_hourly_price: float,
    allocated_storage: int,
    storage_type: str,
    iops: int,
    multi_az: bool,
    env: str,
    backup_storage_gb: float = 0,
    backup_retention_days: int = 7
) -> Dict:
    """Get RDS detailed cost breakdown - fetches fresh data each time for accuracy.
    
    No caching to ensure accurate cost calculations.
    """
    """Get cached RDS detailed cost breakdown with 1-hour TTL.
    
    Pricing data rarely changes, so we cache it for an hour.
    
    Args:
        backup_storage_gb: Backup storage size in GB (optional)
        backup_retention_days: Days of retention (default: 7)
    """
    from analysis.cost_calculator import CostCalculator
    
    return CostCalculator.calculate_rds_detailed_breakdown(
        instance_type=instance_type,
        region=region,
        database_engine=database_engine,
        license_model=license_model,
        deployment_option=deployment_option,
        instance_hourly_price=instance_hourly_price,
        allocated_storage=allocated_storage,
        storage_type=storage_type,
        iops=iops,
        multi_az=multi_az,
        actual_runtime_hours=HOURS_PER_MONTH,
        backup_storage_gb=backup_storage_gb,
        backup_retention_days=backup_retention_days
    )


def get_ebs_detailed_breakdown_cached(
    volume_id: str,
    size_gb: int,
    volume_type: str,
    region: str,
    iops: int,
    throughput_mbps: int,
    env: str
) -> Dict:
    """Get EBS detailed cost breakdown - fetches fresh data each time for accuracy.
    
    No caching to ensure accurate cost calculations.
    """
    from analysis.cost_calculator import CostCalculator
    
    return CostCalculator.calculate_ebs_detailed_breakdown(
        volume_id=volume_id,
        size_gb=size_gb,
        volume_type=volume_type,
        region=region,
        iops=iops,
        throughput_mbps=throughput_mbps
    )


def get_etl_provider_cached(env: str) -> ETLDataProvider:
    """Get ETL provider instance - creates fresh instance each time for accurate data.
    
    No caching to ensure fresh data is always used for cost calculations.
    """
    db_path = Config.get_db_path(env)
    return ETLDataProvider(db_path)


def get_instances_cached(service_type: str, region: str, env: str) -> List[Dict]:
    """Get instance list - fetches fresh data each time."""
    provider = get_etl_provider_cached(env)
    return provider.list_instances(service_type, region)


def get_data_freshness_cached(service_type: str, env: str) -> Optional[Dict]:
    """Get data freshness - fetches fresh data each time."""
    provider = get_etl_provider_cached(env)
    return provider.get_data_freshness(service_type)


def get_pricing_cached(instance_type: str, region: str, service: str, env: str,
                      operating_system: str = None, tenancy: str = None,
                      database_engine: str = None, deployment_option: str = None) -> Optional[float]:
    """Get pricing - fetches fresh data each time for accurate cost calculations.
    
    Critical for cost savings accuracy - never cache pricing data.
    
    Args:
        instance_type: The instance type (e.g., 't3.medium', 'db.r5.large')
        region: The AWS region code (e.g., 'us-east-1')
        service: The AWS service ('EC2', 'RDS', 'S3')
        env: The environment name
        operating_system: For EC2 - operating system
        tenancy: For EC2 - tenancy
        database_engine: For RDS - database engine
        deployment_option: For RDS - Single-AZ or Multi-AZ
    """
    provider = get_etl_provider_cached(env)
    return provider.get_pricing(instance_type, region, service,
                               operating_system=operating_system,
                               tenancy=tenancy,
                               database_engine=database_engine,
                               deployment_option=deployment_option)


def get_instance_tags_cached(instance_id: str, env: str) -> Dict[str, str]:
    """Get instance tags - fetches fresh data each time."""
    provider = get_etl_provider_cached(env)
    return provider.get_instance_tags(instance_id)


def get_manager_cached(service_type: str, region: str, env: str):
    """Get service manager instance - creates fresh instance each time."""
    if service_type == 'RDS':
        return RDSManager(region, use_etl=True, aws_environment=env)
    elif service_type == 'EC2':
        return EC2Manager(region, use_etl=True, aws_environment=env)
    elif service_type == 'EBS':
        return EBSManager(region, use_etl=True, aws_environment=env)


def load_css_cached() -> str:
    """Load CSS from external file.
    
    Reads the CSS file.
    """
    css_path = os.path.join(os.path.dirname(__file__), '..', 'styles.css')
    try:
        with open(css_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"CSS file not found at {css_path}, using inline fallback")
        return ""
