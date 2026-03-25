"""
AWS RDS Database Engine Pricing Loader

This module fetches RDS pricing data directly from AWS Price List API
to populate the database_engine field which is missing in many pricing records.

AWS Price List API Reference:
https://docs.aws.amazon.com/aws-cost-management/latest/userguide/price-list-examples.html
"""

import boto3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from core.logger import setup_logger
from core.config import Config
from core.constants import AWS_LOCATION_TO_REGION
from etl.base_db import BaseDatabase, DatabaseType

logger = setup_logger(__name__)


class RDSDatabaseEnginePricingLoader(BaseDatabase):
    """
    Fetches RDS pricing with database engine information from AWS Price List API.
    
    This addresses the issue where the original pricing JSON files don't contain
    databaseEngine attribute, causing incorrect pricing lookups.
    """
    
    # RDS Database Engines to fetch
    DATABASE_ENGINES = [
        'mysql',
        'postgres',
        'mariadb',
        'oracle-ee',
        'oracle-se2',
        'oracle-se1',
        'oracle-se',
        'sqlserver-ee',
        'sqlserver-se',
        'sqlserver-ex',
        'sqlserver-web',
        'aurora',
        'aurora-mysql',
        'aurora-postgresql',
        'neptune',
        'docdb'
    ]
    
    # RDS Instance families
    INSTANCE_FAMILIES = [
        't3', 't4g', 'm5', 'm6g', 'm7g', 'r5', 'r6g', 'r7g',
        'x2g', 'z1d', 'db.t3', 'db.t4g', 'db.m5', 'db.m6g', 'db.r5', 
        'db.r6g', 'db.x2g', 'db.z1d'
    ]
    
    def __init__(self, db_path: str = None, database_url: str = None):
        """Initialize RDS database engine pricing loader"""
        if database_url is None:
            database_url = Config.get_pricing_database_url()
        
        super().__init__(database_url)
        
        self.db_path = db_path or Config.PRICING_DB_PATH
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """Ensure the pricing table exists"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS aws_pricing (
            sku TEXT PRIMARY KEY,
            instance_type TEXT,
            region TEXT,
            price_per_hour REAL,
            currency TEXT,
            service TEXT,
            raw_json TEXT,
            operating_system TEXT,
            tenancy TEXT,
            database_engine TEXT,
            deployment_option TEXT,
            license_model TEXT,
            pre_installed_sw TEXT
        )
        """
        self.execute(create_table_sql)
        
        # Add columns if not exist
        for col in ['service', 'operating_system', 'tenancy', 'database_engine', 
                    'deployment_option', 'license_model', 'pre_installed_sw']:
            self.add_column_if_not_exists('aws_pricing', col, 'TEXT')
        
        # Create indexes
        self.create_index_if_not_exists('idx_pricing_rds_lookup', 'aws_pricing', 
                                         ['instance_type', 'region', 'database_engine', 'deployment_option'])
    
    def fetch_rds_pricing_from_aws(self, region: str = 'us-east-1') -> List[Dict]:
        """
        Fetch RDS pricing from AWS Price List API.
        
        Uses the Price List API to get accurate database engine-specific pricing.
        
        Args:
            region: AWS region code
            
        Returns:
            List of pricing dictionaries with database_engine information
        """
        pricing_data = []
        
        try:
            # Create Pricing client
            pricing_client = boto3.client('pricing', region_name='us-east-1')
            
            # Pagination token
            next_token = None
            
            logger.info(f"Fetching RDS pricing from AWS for region {region}...")
            
            while True:
                # Build filter for RDS service
                filter_params = {
                    'Type': 'TERM_MATCH',
                    'Field': 'serviceCode',
                    'Value': 'AmazonRDS'
                }
                
                # API request parameters
                params = {
                    'ServiceCode': 'AmazonRDS',
                    'Version': '2023-10-31',
                    'Filters': [filter_params],
                    'MaxResults': 100
                }
                
                if next_token:
                    params['NextToken'] = next_token
                
                # Make API call
                response = pricing_client.get_products(**params)
                
                # Process results
                for price_json in response.get('PriceList', []):
                    try:
                        product = json.loads(price_json) if isinstance(price_json, str) else price_json
                        
                        # Extract product attributes
                        attrs = product.get('product', {}).get('attributes', {})
                        
                        instance_type = attrs.get('instanceType')
                        location = attrs.get('location')
                        database_engine = attrs.get('databaseEngine')
                        deployment_option = attrs.get('deploymentOption')
                        license_model = attrs.get('licenseModel')
                        tenancy = attrs.get('tenancy')
                        
                        # Skip if not an instance
                        if not instance_type or not instance_type.startswith('db.'):
                            continue
                        
                        # Extract price
                        terms = product.get('terms', {}).get('OnDemand', {})
                        price = 0.0
                        
                        for term in terms.values():
                            for price_dim in term.get('priceDimensions', {}).values():
                                try:
                                    price_val = price_dim.get('pricePerUnit', {}).get('USD')
                                    if price_val:
                                        price = float(price_val)
                                        break
                                except (ValueError, TypeError):
                                    pass
                            if price > 0:
                                break
                        
                        if price > 0 and instance_type and location:
                            pricing_data.append({
                                'instance_type': instance_type,
                                'region': location,
                                'region_code': AWS_LOCATION_TO_REGION.get(location, location),
                                'price_per_hour': price,
                                'database_engine': database_engine,
                                'deployment_option': deployment_option,
                                'license_model': license_model,
                                'tenancy': tenancy,
                                'service': 'RDS'
                            })
                            
                    except Exception as e:
                        logger.debug(f"Error processing price item: {e}")
                        continue
                
                # Check for next page
                next_token = response.get('NextToken')
                if not next_token:
                    break
                    
        except Exception as e:
            logger.error(f"Error fetching RDS pricing from AWS: {e}")
        
        logger.info(f"Fetched {len(pricing_data)} RDS pricing records from AWS")
        return pricing_data
    
    def update_database_engine_pricing(self, region: str = None) -> int:
        """
        Update the aws_pricing table with database engine information.
        
        Fetches fresh pricing from AWS API and updates the database.
        
        Args:
            region: Optional region filter (None = all regions)
            
        Returns:
            Number of records updated
        """
        # Fetch from AWS
        pricing_data = self.fetch_rds_pricing_from_aws(region or 'us-east-1')
        
        if not pricing_data:
            logger.warning("No pricing data fetched from AWS")
            return 0
        
        # Group by instance_type and region to find unique combinations
        unique_pricing = {}
        for item in pricing_data:
            key = (item['instance_type'], item['region'])
            if key not in unique_pricing:
                unique_pricing[key] = item
        
        updated_count = 0
        
        # Update database
        for (instance_type, region), item in unique_pricing.items():
            try:
                # Update the database_engine for matching records
                if self.db_type == DatabaseType.SQLITE:
                    sql = """
                        UPDATE aws_pricing 
                        SET database_engine = :engine,
                            deployment_option = :deploy,
                            license_model = :license,
                            tenancy = :tenancy
                        WHERE instance_type = :instance_type 
                        AND region = :region
                        AND (database_engine IS NULL OR database_engine = '')
                    """
                else:
                    sql = """
                        UPDATE aws_pricing 
                        SET database_engine = :engine,
                            deployment_option = :deploy,
                            license_model = :license,
                            tenancy = :tenancy
                        WHERE instance_type = :instance_type 
                        AND region = :region
                        AND (database_engine IS NULL OR database_engine = '')
                    """
                
                self.execute(sql, {
                    'engine': item['database_engine'],
                    'deploy': item['deployment_option'],
                    'license': item['license_model'],
                    'tenancy': item['tenancy'],
                    'instance_type': instance_type,
                    'region': region
                })
                updated_count += 1
                
            except Exception as e:
                logger.debug(f"Error updating {instance_type} in {region}: {e}")
        
        logger.info(f"Updated {updated_count} pricing records with database_engine")
        return updated_count
    
    def populate_missing_database_engines(self) -> Dict[str, int]:
        """
        Populate missing database_engine values using AWS API.
        
        Returns:
            Dictionary with counts of updated records by engine type
        """
        results = {}
        
        # Fetch for a few key regions
        regions = ['us-east-1', 'us-west-2', 'eu-west-1']
        
        for region in regions:
            logger.info(f"Processing region: {region}")
            count = self.update_database_engine_pricing(region)
            results[region] = count
        
        return results


def main():
    """Main entry point for running the loader"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update RDS database engine pricing')
    parser.add_argument('--region', type=str, default=None, help='AWS region (default: all)')
    args = parser.parse_args()
    
    loader = RDSDatabaseEnginePricingLoader()
    
    if args.region:
        count = loader.update_database_engine_pricing(args.region)
        print(f"Updated {count} records for region {args.region}")
    else:
        results = loader.populate_missing_database_engines()
        print("Results by region:")
        for region, count in results.items():
            print(f"  {region}: {count} records updated")


if __name__ == '__main__':
    main()
