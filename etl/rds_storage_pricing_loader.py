"""
RDS Storage Pricing Loader - Loads and caches RDS-specific storage pricing data.
This is DIFFERENT from EC2 EBS pricing! RDS has its own storage pricing structure.

Key differences from EBS:
- RDS uses different volume type names (gp3, gp2, io1, io2, magnetic)
- RDS storage prices are typically HIGHER than equivalent EBS prices
- RDS IOPS pricing structure is different
- Multi-AZ requires 2x storage allocation

Supports multiple database backends via SQLAlchemy.
"""

import boto3
import json
from typing import Optional, Dict
from core.logger import setup_logger
from core.config import Config
from core.constants import AWS_LOCATION_TO_REGION, HOURS_PER_MONTH, DAYS_PER_MONTH
from etl.base_db import BaseDatabase, DatabaseType

logger = setup_logger(__name__)


class RDSStoragePricingLoader(BaseDatabase):
    """
    Loads RDS-specific storage pricing data from AWS Pricing API and caches locally.
    RDS storage is priced DIFFERENTLY from EC2 EBS - this loader handles that difference.
    """
    
    REGION = "ap-south-1"
    PRICING_REGION = "us-east-1"
    
    # RDS Volume type to AWS pricing product family mapping
    # Note: RDS uses different terminology than EC2 EBS
    VOLUME_TYPE_MAPPING = {
        'gp3': 'General Purpose',
        'gp2': 'General Purpose',
        'io1': 'Provisioned IOPS',
        'io2': 'Provisioned IOPS',
        'magnetic': 'Magnetic',
        'standard': 'Magnetic'
    }
    
    # RDS Storage pricing - fetched from API (no hardcoded defaults!)
    # These are last resort fallbacks ONLY if API completely fails
    DEFAULT_STORAGE_PRICES = {
        'gp3': None,    # Must fetch from API
        'gp2': None,   # Must fetch from API
        'io1': None,   # Must fetch from API
        'io2': None,   # Must fetch from API
        'magnetic': None  # Must fetch from API
    }
    
    # RDS IOPS pricing - fetched from API (no hardcoded defaults!)
    DEFAULT_IOPS_PRICES = {
        'io1': None,   # Must fetch from API
        'io2': None,   # Must fetch from API
        'gp3': None,   # Must fetch from API
        'gp2': None,   # Not applicable
        'magnetic': None,  # Not applicable
        'standard': None
    }
    
    # Multi-AZ storage multiplication factor
    # Multi-AZ requires storage in TWO availability zones
    MULTI_AZ_STORAGE_MULTIPLIER = 2.0
    
    def __init__(self, db_path: str = None, database_url: str = None):
        """Initialize RDS storage pricing loader with database path or URL"""
        # Use pricing database URL by default (separate from main database)
        if database_url is None:
            database_url = Config.get_pricing_database_url()
        
        super().__init__(database_url)
        
        # Keep db_path for backwards compatibility
        self.db_path = db_path or Config.PRICING_DB_PATH
        self.pricing = boto3.client('pricing', region_name=self.PRICING_REGION)
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """Create RDS storage pricing table if not exists"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS rds_storage_pricing (
            sku TEXT PRIMARY KEY,
            volume_type TEXT NOT NULL,
            region TEXT NOT NULL,
            price_per_gb_month REAL NOT NULL,
            price_per_iops_month REAL,
            currency TEXT DEFAULT 'USD',
            location TEXT,
            raw_json TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.execute(create_table_sql)
        
        # Create index for faster lookups
        self.create_index_if_not_exists('idx_rds_storage_pricing_lookup', 'rds_storage_pricing', ['volume_type', 'region'])
        
        logger.info("RDS storage pricing table schema verified")
    
    def get_rds_storage_price(self, volume_type: str, region: str) -> float:
        """
        Get RDS storage price per GB per month for a volume type.
        
        ALL values come from AWS Pricing API - NO HARDCODED VALUES!
        
        Args:
            volume_type: RDS storage type (gp3, gp2, io1, io2, magnetic, standard)
            region: AWS region code (e.g., 'us-east-1')
            
        Returns:
            Price per GB per month in USD (from API)
        """
        # Normalize volume type - map aliases to canonical names
        # 'standard' is an alias for 'magnetic' in RDS
        volume_type = self.VOLUME_TYPE_MAPPING.get(volume_type, volume_type)
        
        # Try local database first (populated from API)
        price = self._get_local_storage_price(volume_type, region)
        if price is not None and price > 0:
            return price
        
        # Fetch from AWS Pricing API
        price = self._fetch_storage_from_aws_api(volume_type, region)
        if price > 0:
            # Cache the price
            self._cache_storage_price(volume_type, region, price)
            return price
        
        # NO FALLBACK - Log error and return 0 if API fails
        logger.error(f"RDS storage price unavailable for {volume_type} in {region}. Please run pricing ETL.")
        return 0.0
    
    def get_rds_iops_price(self, volume_type: str, region: str) -> float:
        """
        Get RDS IOPS price per IOPS per month.
        
        ALL values come from AWS Pricing API - NO HARDCODED VALUES!
        
        Args:
            volume_type: RDS storage type (io1, io2, gp3)
            region: AWS region code
            
        Returns:
            Price per IOPS per month in USD (from API)
        """
        # Normalize volume type - map aliases to canonical names
        volume_type = self.VOLUME_TYPE_MAPPING.get(volume_type, volume_type)
        
        # Try local database first (populated from API)
        price = self._get_local_iops_price(volume_type, region)
        if price is not None and price > 0:
            return price
        
        # Fetch from AWS Pricing API
        price = self._fetch_iops_from_aws_api(volume_type, region)
        if price > 0:
            # Cache the price
            self._cache_iops_price(volume_type, region, price)
            return price
        
        # NO FALLBACK - Log error and return 0 if API fails
        logger.error(f"RDS IOPS price unavailable for {volume_type} in {region}. Please run pricing ETL.")
        return 0.0
    
    def _get_local_storage_price(self, volume_type: str, region: str) -> Optional[float]:
        """Get RDS storage price from local database"""
        try:
            location = self._region_to_location(region)
            
            row = self.fetch_one(
                """
                SELECT price_per_gb_month FROM rds_storage_pricing 
                WHERE volume_type = :volume_type AND (region = :region OR region = :location) 
                AND price_per_gb_month > 0
                LIMIT 1
                """,
                {"volume_type": volume_type, "region": region, "location": location}
            )
            
            if row:
                logger.debug(f"Found local RDS storage price for {volume_type} in {region}: ${row[0]}")
                return row[0]
            
            return None
        except Exception as e:
            logger.warning(f"Error querying local RDS storage price: {e}")
            return None
    
    def _get_local_iops_price(self, volume_type: str, region: str) -> Optional[float]:
        """Get RDS IOPS price from local database"""
        try:
            location = self._region_to_location(region)
            
            row = self.fetch_one(
                """
                SELECT price_per_iops_month FROM rds_storage_pricing 
                WHERE volume_type = :volume_type AND (region = :region OR region = :location) 
                AND price_per_iops_month IS NOT NULL AND price_per_iops_month > 0
                LIMIT 1
                """,
                {"volume_type": volume_type, "region": region, "location": location}
            )
            
            if row:
                logger.debug(f"Found local RDS IOPS price for {volume_type} in {region}: ${row[0]}")
                return row[0]
            
            return None
        except Exception as e:
            logger.warning(f"Error querying local RDS IOPS price: {e}")
            return None
    
    def _cache_storage_price(self, volume_type: str, region: str, price: float):
        """Cache RDS storage price in local database"""
        try:
            location = self._region_to_location(region)
            sku = f"rds-storage-{volume_type}-{region}"
            
            if self.db_type == DatabaseType.POSTGRESQL:
                self.execute(
                    """
                    INSERT INTO rds_storage_pricing (sku, volume_type, region, price_per_gb_month, currency, location)
                    VALUES (:sku, :volume_type, :region, :price_per_gb_month, 'USD', :location)
                    ON CONFLICT (sku) DO UPDATE SET
                        volume_type = EXCLUDED.volume_type,
                        region = EXCLUDED.region,
                        price_per_gb_month = EXCLUDED.price_per_gb_month,
                        location = EXCLUDED.location
                    """,
                    {"sku": sku, "volume_type": volume_type, "region": region, "price_per_gb_month": price, "location": location}
                )
            elif self.db_type == DatabaseType.MYSQL:
                self.execute(
                    """
                    INSERT INTO rds_storage_pricing (sku, volume_type, region, price_per_gb_month, currency, location)
                    VALUES (:sku, :volume_type, :region, :price_per_gb_month, 'USD', :location)
                    ON DUPLICATE KEY UPDATE
                        volume_type = VALUES(volume_type),
                        region = VALUES(region),
                        price_per_gb_month = VALUES(price_per_gb_month),
                        location = VALUES(location)
                    """,
                    {"sku": sku, "volume_type": volume_type, "region": region, "price_per_gb_month": price, "location": location}
                )
            else:
                # SQLite and others
                self.execute(
                    """
                    INSERT OR REPLACE INTO rds_storage_pricing (sku, volume_type, region, price_per_gb_month, currency, location)
                    VALUES (:sku, :volume_type, :region, :price_per_gb_month, 'USD', :location)
                    """,
                    {"sku": sku, "volume_type": volume_type, "region": region, "price_per_gb_month": price, "location": location}
                )
            
            logger.debug(f"Cached RDS storage price for {volume_type} in {region}: ${price}")
        except Exception as e:
            logger.warning(f"Error caching RDS storage price: {e}")
    
    def _cache_iops_price(self, volume_type: str, region: str, price: float):
        """Cache RDS IOPS price in local database"""
        try:
            location = self._region_to_location(region)
            sku = f"rds-iops-{volume_type}-{region}"
            
            if self.db_type == DatabaseType.POSTGRESQL:
                self.execute(
                    """
                    INSERT INTO rds_storage_pricing (sku, volume_type, region, price_per_iops_month, currency, location)
                    VALUES (:sku, :volume_type, :region, :price_per_iops_month, 'USD', :location)
                    ON CONFLICT (sku) DO UPDATE SET
                        volume_type = EXCLUDED.volume_type,
                        region = EXCLUDED.region,
                        price_per_iops_month = EXCLUDED.price_per_iops_month,
                        location = EXCLUDED.location
                    """,
                    {"sku": sku, "volume_type": volume_type, "region": region, "price_per_iops_month": price, "location": location}
                )
            elif self.db_type == DatabaseType.MYSQL:
                self.execute(
                    """
                    INSERT INTO rds_storage_pricing (sku, volume_type, region, price_per_iops_month, currency, location)
                    VALUES (:sku, :volume_type, :region, :price_per_iops_month, 'USD', :location)
                    ON DUPLICATE KEY UPDATE
                        volume_type = VALUES(volume_type),
                        region = VALUES(region),
                        price_per_iops_month = VALUES(price_per_iops_month),
                        location = VALUES(location)
                    """,
                    {"sku": sku, "volume_type": volume_type, "region": region, "price_per_iops_month": price, "location": location}
                )
            else:
                # SQLite and others
                self.execute(
                    """
                    INSERT OR REPLACE INTO rds_storage_pricing (sku, volume_type, region, price_per_iops_month, currency, location)
                    VALUES (:sku, :volume_type, :region, :price_per_iops_month, 'USD', :location)
                    """,
                    {"sku": sku, "volume_type": volume_type, "region": region, "price_per_iops_month": price, "location": location}
                )
            
            logger.debug(f"Cached RDS IOPS price for {volume_type} in {region}: ${price}")
        except Exception as e:
            logger.warning(f"Error caching RDS IOPS price: {e}")
    
    def _fetch_storage_from_aws_api(self, volume_type: str, region: str) -> float:
        """
        Fetch RDS storage price from AWS Pricing API.
        
        Note: RDS storage pricing is under AmazonRDS service, not AmazonEC2.
        """
        location = self._region_to_location(region)
        
        try:
            response = self.pricing.get_products(
                ServiceCode="AmazonRDS",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "volumeType", "Value": volume_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Database Storage"},
                ],
                MaxResults=1,
            )
            
            price_list = response.get("PriceList", [])
            if not price_list:
                logger.warning(f"No RDS storage price found for {volume_type} in {region}")
                return 0.0
            
            price_item = json.loads(price_list[0])
            terms = price_item.get("terms", {}).get("OnDemand", {})
            
            for term in terms.values():
                for dim in term.get("priceDimensions", {}).values():
                    price = float(dim.get("pricePerUnit", {}).get("USD", 0))
                    if price > 0:
                        logger.info(f"Fetched RDS storage price from AWS: {volume_type} in {location} = ${price}/GB/month")
                        return price
            
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching RDS storage price from AWS API: {e}")
            return 0.0
    
    def _fetch_iops_from_aws_api(self, volume_type: str, region: str) -> float:
        """
        Fetch RDS IOPS price from AWS Pricing API.
        
        Note: RDS IOPS pricing is separate from storage pricing.
        """
        location = self._region_to_location(region)
        
        # For gp3, IOPS is included up to 3x storage (baseline)
        # For io1/io2, IOPS is provisioned separately
        
        try:
            response = self.pricing.get_products(
                ServiceCode="AmazonRDS",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "volumeType", "Value": volume_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Provisioned IOPS"},
                ],
                MaxResults=1,
            )
            
            price_list = response.get("PriceList", [])
            if not price_list:
                # Try alternate product family
                return 0.0
            
            price_item = json.loads(price_list[0])
            terms = price_item.get("terms", {}).get("OnDemand", {})
            
            for term in terms.values():
                for dim in term.get("priceDimensions", {}).values():
                    price = float(dim.get("pricePerUnit", {}).get("USD", 0))
                    if price > 0:
                        logger.info(f"Fetched RDS IOPS price from AWS: {volume_type} in {location} = ${price}/IOPS/month")
                        return price
            
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching RDS IOPS price from AWS API: {e}")
            return 0.0
    
    def _region_to_location(self, region: str) -> str:
        """Convert region code to AWS location name"""
        # Reverse the mapping from constants
        for location, region_code in AWS_LOCATION_TO_REGION.items():
            if region_code == region:
                return location
        
        # Default fallback mapping
        fallback = {
            'us-east-1': 'US East (N. Virginia)',
            'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)',
            'us-west-2': 'US West (Oregon)',
            'ap-south-1': 'Asia Pacific (Mumbai)',
            'ap-southeast-1': 'Asia Pacific (Singapore)',
            'ap-southeast-2': 'Asia Pacific (Sydney)',
            'eu-west-1': 'EU (Ireland)',
            'eu-west-2': 'EU (London)',
            'eu-central-1': 'EU (Frankfurt)',
        }
        return fallback.get(region, 'US East (N. Virginia)')
    
    def calculate_rds_storage_cost(
        self, 
        allocated_storage: int, 
        volume_type: str, 
        iops: int = None, 
        multi_az: bool = False,
        region: str = None
    ) -> Dict:
        """
        Calculate monthly cost for RDS storage.
        
        CRITICAL: This is DIFFERENT from EC2 EBS cost calculation!
        
        Key differences:
        1. Uses RDS-specific pricing (not EBS)
        2. Multi-AZ requires 2x storage (primary + standby)
        3. IOPS pricing is different from EBS
        
        Args:
            allocated_storage: Storage allocated in GB
            volume_type: RDS storage type (gp3, gp2, io1, io2, magnetic)
            iops: Provisioned IOPS (for io1, io2, gp3)
            multi_az: Whether Multi-AZ is enabled
            region: AWS region code
            
        Returns:
            Dictionary with cost breakdown:
            - monthly: Total monthly cost
            - daily: Daily cost (monthly / 30)
            - yearly: Yearly cost (monthly * 12)
            - hourly: Hourly cost (monthly / 730)
            - storage_cost: Base storage cost
            - iops_cost: Provisioned IOPS cost
            - multi_az_cost: Additional Multi-AZ storage cost
            - price_per_gb: Price per GB
            - price_per_iops: Price per IOPS
        """
        # Use provided region or try to get from config
        if not region:
            from core.config import Config
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        # Get RDS-specific storage price (DIFFERENT from EBS!)
        price_per_gb = self.get_rds_storage_price(volume_type, region)
        
        # Calculate storage cost
        # Multi-AZ requires storage in TWO availability zones!
        storage_multiplier = self.MULTI_AZ_STORAGE_MULTIPLIER if multi_az else 1.0
        effective_storage = allocated_storage * storage_multiplier
        storage_cost = effective_storage * price_per_gb
        
        # Calculate IOPS cost (RDS-specific pricing)
        iops_cost = 0
        price_per_iops = 0
        
        if iops and volume_type in ['io1', 'io2']:
            # For io1/io2, IOPS is provisioned separately
            price_per_iops = self.get_rds_iops_price(volume_type, region)
            iops_cost = iops * price_per_iops
        elif iops and volume_type == 'gp3':
            # For gp3, calculate excess IOPS above baseline
            # Baseline IOPS = 3 * allocated_storage (for gp3)
            baseline_iops = 3 * allocated_storage
            if iops > baseline_iops:
                excess_iops = iops - baseline_iops
                price_per_iops = self.get_rds_iops_price(volume_type, region)
                iops_cost = excess_iops * price_per_iops
        
        # Calculate total monthly cost
        monthly = storage_cost + iops_cost
        
        # Calculate breakdown
        multi_az_extra_cost = storage_cost if multi_az else 0
        
        return {
            'monthly': monthly,
            'daily': monthly / DAYS_PER_MONTH,
            'yearly': monthly * 12,
            'hourly': monthly / HOURS_PER_MONTH,
            'storage_cost': storage_cost,
            'iops_cost': iops_cost,
            'multi_az_extra_cost': multi_az_extra_cost,
            'effective_storage_gb': effective_storage,
            'price_per_gb': price_per_gb,
            'price_per_iops': price_per_iops,
            'multi_az': multi_az,
            'volume_type': volume_type,
            'region': region
        }
    
    @staticmethod
    def run_etl(db_path: str = None, database_url: str = None, regions: list = None):
        """Static wrapper to load RDS storage pricing for specified regions"""
        loader = RDSStoragePricingLoader(db_path=db_path, database_url=database_url)
        regions = regions or ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2', 
                             'ap-south-1', 'ap-southeast-1', 'ap-southeast-2']
        
        volume_types = ['gp3', 'gp2', 'io1', 'io2', 'magnetic', 'standard']
        
        for region in regions:
            for volume_type in volume_types:
                storage_price = loader.get_rds_storage_price(volume_type, region)
                iops_price = loader.get_rds_iops_price(volume_type, region)
                logger.info(f"RDS {volume_type} in {region}: ${storage_price}/GB/mo, IOPS: ${iops_price}/IOPS/mo")


def run_rds_storage_pricing_etl(db_path: str = None, database_url: str = None, regions: list = None):
    """Wrapper function for easy invocation"""
    RDSStoragePricingLoader.run_etl(db_path=db_path, database_url=database_url, regions=regions)


if __name__ == "__main__":
    run_rds_storage_pricing_etl()
