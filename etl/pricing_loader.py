"""
AWS Pricing Loader - Loads pricing data from JSON files into database.
Supports multiple database backends via SQLAlchemy.
"""

import pandas as pd
import json
import os
from core.logger import setup_logger
from core.config import Config
from core.constants import PRICING_BATCH_SIZE, AWS_LOCATION_TO_REGION
from etl.base_db import BaseDatabase, DatabaseType

logger = setup_logger(__name__)


class PricingLoader(BaseDatabase):
    """
    Loads AWS pricing data from local JSON files into the database.
    Supports multiple database backends via SQLAlchemy.
    """
    
    def __init__(self, db_path: str = None, database_url: str = None):
        """Initialize pricing loader with database path or URL"""
        # Use pricing database URL by default (separate from main database)
        if database_url is None:
            database_url = Config.get_pricing_database_url()
        
        super().__init__(database_url)
        
        # Keep db_path for backwards compatibility
        self.db_path = db_path or Config.PRICING_DB_PATH
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Ensure the pricing table exists with proper schema"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS aws_pricing (
            sku TEXT PRIMARY KEY,
            instance_type TEXT,
            region TEXT,
            price_per_hour REAL,
            currency TEXT,
            service TEXT,
            raw_json TEXT,
            -- Extended attributes for accurate pricing
            operating_system TEXT,
            tenancy TEXT,
            database_engine TEXT,
            deployment_option TEXT,
            license_model TEXT,
            pre_installed_sw TEXT
        )
        """
        self.execute(create_table_sql)
        
        # Ensure 'service' column exists for older databases
        self.add_column_if_not_exists('aws_pricing', 'service', 'TEXT')
        
        # Add new columns for extended pricing attributes
        self.add_column_if_not_exists('aws_pricing', 'operating_system', 'TEXT')
        self.add_column_if_not_exists('aws_pricing', 'tenancy', 'TEXT')
        self.add_column_if_not_exists('aws_pricing', 'database_engine', 'TEXT')
        self.add_column_if_not_exists('aws_pricing', 'deployment_option', 'TEXT')
        self.add_column_if_not_exists('aws_pricing', 'license_model', 'TEXT')
        self.add_column_if_not_exists('aws_pricing', 'pre_installed_sw', 'TEXT')
        
        # Create index for faster lookups
        self.create_index_if_not_exists('idx_pricing_lookup', 'aws_pricing', ['instance_type', 'region', 'service'])
        self.create_index_if_not_exists('idx_pricing_ec2_lookup', 'aws_pricing', ['instance_type', 'region', 'operating_system', 'tenancy'])
        self.create_index_if_not_exists('idx_pricing_rds_lookup', 'aws_pricing', ['instance_type', 'region', 'database_engine', 'deployment_option'])
        
        logger.info("Pricing table schema verified")

    def load_pricing(self, ec2_path=None, rds_path=None, regions=None, chunk_size=None):
        """Load pricing data from provided JSON paths"""
        chunk_size = chunk_size or PRICING_BATCH_SIZE
        paths = [
            ('EC2', ec2_path or Config.PRICING_JSON_PATHS.get('ec2')),
            ('RDS', rds_path or Config.PRICING_JSON_PATHS.get('rds'))
        ]
        
        for service, json_path in paths:
            if not json_path or not os.path.exists(json_path):
                logger.warning(f"Pricing file for {service} not found at {json_path}")
                continue
                
            try:
                logger.info(f"Loading {service} pricing from {json_path}...")
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    
                products = data.get('products', {})
                terms = data.get('terms', {}).get('OnDemand', {})
                product_items = list(products.items())
                logger.info(f"Found {len(product_items)} products in {service} pricing file")
                
                total_loaded = 0
                total_filtered = 0
                for i in range(0, len(product_items), chunk_size):
                    chunk = product_items[i:i+chunk_size]
                    rows = []
                    
                    for sku, offer in chunk:
                        attrs = offer.get('attributes', {})
                        instance_type = attrs.get('instanceType') or attrs.get('instance_type')
                        location = attrs.get('location') or attrs.get('region')
                        
                        # Extract extended pricing attributes
                        operating_system = attrs.get('operatingSystem') or attrs.get('operating_system')
                        tenancy = attrs.get('tenancy')
                        database_engine = attrs.get('databaseEngine') or attrs.get('database_engine')
                        deployment_option = attrs.get('deploymentOption') or attrs.get('deployment_option')
                        license_model = attrs.get('licenseModel') or attrs.get('license_model')
                        pre_installed_sw = attrs.get('preInstalledSw') or attrs.get('pre_installed_sw')
                        
                        # Convert location name to region code if possible
                        region_code = AWS_LOCATION_TO_REGION.get(location, location)
                        
                        # Extract price from terms
                        price = 0.0
                        currency = 'USD'
                        sku_terms = terms.get(sku, {})
                        for term in sku_terms.values():
                            for price_dim in term.get('priceDimensions', {}).values():
                                try:
                                    price = float(price_dim.get('pricePerUnit', {}).get('USD', 0))
                                    if price > 0:  # Take first non-zero price
                                        break
                                except (ValueError, TypeError):
                                    price = 0.0
                                currency = 'USD'
                            if price > 0:
                                break
                                
                        if instance_type and location and price > 0:
                            # Store with location name for the region column
                            # Also store extended attributes
                            rows.append((
                                sku, instance_type, location, price, currency, service, json.dumps(offer),
                                operating_system, tenancy, database_engine, deployment_option, license_model, pre_installed_sw
                            ))
                    
                    if rows:
                        self._insert_rows(rows)
                        total_loaded += len(rows)
                
                logger.info(f"Successfully loaded {total_loaded} {service} pricing records (filtered out {total_filtered} records)")
                if total_loaded == 0:
                    logger.warning(f"No {service} pricing records loaded. Check if region filter matches location names in pricing file.")
                
            except Exception as e:
                logger.error(f"Failed to process {service} pricing: {e}", exc_info=True)

    def _insert_rows(self, rows):
        """Insert a batch of pricing rows into the database"""
        for row in rows:
            # Handle both old format (7 columns) and new format (13 columns)
            if len(row) == 7:
                sku, instance_type, region, price_per_hour, currency, service, raw_json = row
                operating_system = None
                tenancy = None
                database_engine = None
                deployment_option = None
                license_model = None
                pre_installed_sw = None
            else:
                sku, instance_type, region, price_per_hour, currency, service, raw_json, \
                    operating_system, tenancy, database_engine, deployment_option, license_model, pre_installed_sw = row
            
            # Use database-agnostic upsert
            if self.db_type == DatabaseType.POSTGRESQL:
                self.execute(
                    """
                    INSERT INTO aws_pricing (sku, instance_type, region, price_per_hour, currency, service, raw_json,
                        operating_system, tenancy, database_engine, deployment_option, license_model, pre_installed_sw)
                    VALUES (:sku, :instance_type, :region, :price_per_hour, :currency, :service, :raw_json,
                        :operating_system, :tenancy, :database_engine, :deployment_option, :license_model, :pre_installed_sw)
                    ON CONFLICT (sku) DO UPDATE SET
                        instance_type = EXCLUDED.instance_type,
                        region = EXCLUDED.region,
                        price_per_hour = EXCLUDED.price_per_hour,
                        currency = EXCLUDED.currency,
                        service = EXCLUDED.service,
                        raw_json = EXCLUDED.raw_json,
                        operating_system = EXCLUDED.operating_system,
                        tenancy = EXCLUDED.tenancy,
                        database_engine = EXCLUDED.database_engine,
                        deployment_option = EXCLUDED.deployment_option,
                        license_model = EXCLUDED.license_model,
                        pre_installed_sw = EXCLUDED.pre_installed_sw
                    """,
                    {
                        "sku": sku, "instance_type": instance_type, "region": region,
                        "price_per_hour": price_per_hour, "currency": currency,
                        "service": service, "raw_json": raw_json,
                        "operating_system": operating_system, "tenancy": tenancy,
                        "database_engine": database_engine, "deployment_option": deployment_option,
                        "license_model": license_model, "pre_installed_sw": pre_installed_sw
                    }
                )
            elif self.db_type == DatabaseType.MYSQL:
                self.execute(
                    """
                    INSERT INTO aws_pricing (sku, instance_type, region, price_per_hour, currency, service, raw_json,
                        operating_system, tenancy, database_engine, deployment_option, license_model, pre_installed_sw)
                    VALUES (:sku, :instance_type, :region, :price_per_hour, :currency, :service, :raw_json,
                        :operating_system, :tenancy, :database_engine, :deployment_option, :license_model, :pre_installed_sw)
                    ON DUPLICATE KEY UPDATE
                        instance_type = VALUES(instance_type),
                        region = VALUES(region),
                        price_per_hour = VALUES(price_per_hour),
                        currency = VALUES(currency),
                        service = VALUES(service),
                        raw_json = VALUES(raw_json),
                        operating_system = VALUES(operating_system),
                        tenancy = VALUES(tenancy),
                        database_engine = VALUES(database_engine),
                        deployment_option = VALUES(deployment_option),
                        license_model = VALUES(license_model),
                        pre_installed_sw = VALUES(pre_installed_sw)
                    """,
                    {
                        "sku": sku, "instance_type": instance_type, "region": region,
                        "price_per_hour": price_per_hour, "currency": currency,
                        "service": service, "raw_json": raw_json,
                        "operating_system": operating_system, "tenancy": tenancy,
                        "database_engine": database_engine, "deployment_option": deployment_option,
                        "license_model": license_model, "pre_installed_sw": pre_installed_sw
                    }
                )
            else:
                # SQLite and others
                self.execute(
                    """
                    INSERT OR REPLACE INTO aws_pricing (sku, instance_type, region, price_per_hour, currency, service, raw_json,
                        operating_system, tenancy, database_engine, deployment_option, license_model, pre_installed_sw)
                    VALUES (:sku, :instance_type, :region, :price_per_hour, :currency, :service, :raw_json,
                        :operating_system, :tenancy, :database_engine, :deployment_option, :license_model, :pre_installed_sw)
                    """,
                    {
                        "sku": sku, "instance_type": instance_type, "region": region,
                        "price_per_hour": price_per_hour, "currency": currency,
                        "service": service, "raw_json": raw_json,
                        "operating_system": operating_system, "tenancy": tenancy,
                        "database_engine": database_engine, "deployment_option": deployment_option,
                        "license_model": license_model, "pre_installed_sw": pre_installed_sw
                    }
                )

    @staticmethod
    def run_etl(db_path=None, database_url=None, ec2_json_path=None, rds_json_path=None, regions=None):
        """Static wrapper for easy invocation from UI"""
        loader = PricingLoader(db_path=db_path, database_url=database_url)
        loader.load_pricing(
            ec2_path=ec2_json_path,
            rds_path=rds_json_path,
            regions=regions
        )


def run_pricing_etl(db_path=None, database_url=None, regions=None):
    """Wrapper for backward compatibility and easy invocation"""
    PricingLoader.run_etl(db_path=db_path, database_url=database_url, regions=regions)
