"""
EBS Pricing Loader - Loads and caches EBS pricing data.
Supports multiple database backends via SQLAlchemy.
"""

import boto3
import json
from typing import Optional, Dict
from core.logger import setup_logger
from core.config import Config
from core.constants import AWS_LOCATION_TO_REGION, DAYS_PER_MONTH
from etl.base_db import BaseDatabase, DatabaseType

logger = setup_logger(__name__)


class EBSPricingLoader(BaseDatabase):
    """
    Loads EBS pricing data from AWS Pricing API and caches locally.
    Supports multiple database backends via SQLAlchemy.
    """
    
    REGION = "ap-south-1"
    PRICING_REGION = "us-east-1"
    
    # Volume type to AWS pricing product family mapping
    VOLUME_TYPE_MAPPING = {
        'gp3': 'General Purpose',
        'gp2': 'General Purpose',
        'io1': 'Provisioned IOPS',
        'io2': 'Provisioned IOPS',
        'st1': 'Throughput Optimized HDD',
        'sc1': 'Cold HDD',
        'standard': 'Magnetic'
    }
    
    # Default prices (fallback if API fails)
    DEFAULT_PRICES = {
        'gp3': 0.08,   # $0.08 per GB/month
        'gp2': 0.10,   # $0.10 per GB/month
        'io1': 0.125,  # $0.125 per GB/month + IOPS cost
        'io2': 0.125,  # $0.125 per GB/month + IOPS cost
        'st1': 0.045,  # $0.045 per GB/month
        'sc1': 0.025,  # $0.025 per GB/month
        'standard': 0.05  # $0.05 per GB/month (magnetic)
    }
    
    # IOPS prices (per IOPS per month)
    IOPS_PRICES = {
        'io1': 0.065,  # $0.065 per IOPS/month
        'io2': 0.065,  # $0.065 per IOPS/month
        'gp3': 0.0     # GP3 includes base IOPS
    }
    
    def __init__(self, db_path: str = None, database_url: str = None):
        """Initialize EBS pricing loader with database path or URL"""
        # Use pricing database URL by default (separate from main database)
        if database_url is None:
            database_url = Config.get_pricing_database_url()
        
        super().__init__(database_url)
        
        # Keep db_path for backwards compatibility
        self.db_path = db_path or Config.PRICING_DB_PATH
        self.pricing = boto3.client('pricing', region_name=self.PRICING_REGION)
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """Create EBS pricing table if not exists"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS ebs_pricing (
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
        self.create_index_if_not_exists('idx_ebs_pricing_lookup', 'ebs_pricing', ['volume_type', 'region'])
        
        logger.info("EBS pricing table schema verified")
    
    def get_ebs_price(self, volume_type: str, region: str) -> float:
        """Get price per GB per month for a volume type"""
        # First try local database
        price = self._get_local_price(volume_type, region)
        if price is not None:
            return price
        
        # Fetch from AWS Pricing API
        price = self._fetch_from_aws_api(volume_type, region)
        if price > 0:
            # Cache the price
            self._cache_price(volume_type, region, price)
            return price
        
        # Fall back to default prices
        return self.DEFAULT_PRICES.get(volume_type, 0.08)
    
    def get_iops_price(self, volume_type: str, region: str) -> float:
        """Get price per IOPS per month for a volume type"""
        return self.IOPS_PRICES.get(volume_type, 0.065)
    
    def _get_local_price(self, volume_type: str, region: str) -> Optional[float]:
        """Get price from local database"""
        try:
            # Try both region code and location name
            location = self._region_to_location(region)
            
            row = self.fetch_one(
                """
                SELECT price_per_gb_month FROM ebs_pricing 
                WHERE volume_type = :volume_type AND (region = :region OR region = :location) 
                AND price_per_gb_month > 0
                LIMIT 1
                """,
                {"volume_type": volume_type, "region": region, "location": location}
            )
            
            if row:
                logger.debug(f"Found local EBS price for {volume_type} in {region}: ${row[0]}")
                return row[0]
            
            return None
        except Exception as e:
            logger.warning(f"Error querying local EBS price: {e}")
            return None
    
    def _cache_price(self, volume_type: str, region: str, price: float):
        """Cache price in local database"""
        try:
            location = self._region_to_location(region)
            sku = f"ebs-{volume_type}-{region}"
            
            # Use database-agnostic upsert
            if self.db_type == DatabaseType.POSTGRESQL:
                self.execute(
                    """
                    INSERT INTO ebs_pricing (sku, volume_type, region, price_per_gb_month, currency, location)
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
                    INSERT INTO ebs_pricing (sku, volume_type, region, price_per_gb_month, currency, location)
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
                    INSERT OR REPLACE INTO ebs_pricing (sku, volume_type, region, price_per_gb_month, currency, location)
                    VALUES (:sku, :volume_type, :region, :price_per_gb_month, 'USD', :location)
                    """,
                    {"sku": sku, "volume_type": volume_type, "region": region, "price_per_gb_month": price, "location": location}
                )
            
            logger.debug(f"Cached EBS price for {volume_type} in {region}: ${price}")
        except Exception as e:
            logger.warning(f"Error caching EBS price: {e}")
    
    def _fetch_from_aws_api(self, volume_type: str, region: str) -> float:
        """Fetch EBS price from AWS Pricing API"""
        location = self._region_to_location(region)
        
        try:
            response = self.pricing.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "volumeType", "Value": volume_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
                ],
                MaxResults=1,
            )
            
            price_list = response.get("PriceList", [])
            if not price_list:
                logger.warning(f"No EBS price found for {volume_type} in {region}")
                return 0.0
            
            price_item = json.loads(price_list[0])
            terms = price_item.get("terms", {}).get("OnDemand", {})
            
            for term in terms.values():
                for dim in term.get("priceDimensions", {}).values():
                    price = float(dim.get("pricePerUnit", {}).get("USD", 0))
                    if price > 0:
                        logger.info(f"Fetched EBS price from AWS: {volume_type} in {location} = ${price}/GB/month")
                        return price
            
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching EBS price from AWS API: {e}")
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
    
    def calculate_volume_cost(self, size_gb: int, volume_type: str, 
                             iops: int = None, region: str = None, 
                             throughput_mbps: int = None) -> Dict:
        """Calculate monthly cost for an EBS volume with full breakdown
        
        Provides itemized cost breakdown:
        - Storage cost (based on volume type and size)
        - IOPS cost (for provisioned IOPS volumes - io1, io2, gp3)
        - Throughput cost (for gp3 provisioned throughput)
        
        Args:
            size_gb: Volume size in GB
            volume_type: Volume type (gp3, gp2, io1, io2, st1, sc1, magnetic)
            iops: Provisioned IOPS (for io1, io2, gp3)
            region: AWS region code
            throughput_mbps: Provisioned throughput in MB/s (for gp3)
            
        Returns:
            Dictionary with cost breakdown
        """
        # Use provided region or try to get from config, don't default to us-east-1
        if not region:
            from core.config import Config
            region = getattr(Config, 'DEFAULT_REGION', 'us-east-1')
        
        from core.constants import EBS_GP3_BASE_IOPS, EBS_GP3_BASE_THROUGHPUT_MBPS
        
        # Get storage price per GB
        price_per_gb = self.get_ebs_price(volume_type, region)
        storage_monthly = size_gb * price_per_gb
        
        # Calculate IOPS cost if applicable
        iops_cost = 0
        iops_rate = 0
        extra_iops = 0
        base_iops_included = 0
        
        if iops and volume_type in ['io1', 'io2', 'gp3']:
            # gp3 includes baseline IOPS, io1/io2 do not
            base_iops_included = EBS_GP3_BASE_IOPS if volume_type == 'gp3' else 0
            extra_iops = max(0, iops - base_iops_included)
            
            if extra_iops > 0:
                iops_rate = self.get_iops_price(volume_type, region)
                iops_cost = extra_iops * iops_rate
        
        # Calculate throughput cost if applicable (gp3 only)
        throughput_cost = 0
        throughput_rate = 0
        extra_throughput = 0
        base_throughput_included = 0
        
        if throughput_mbps and volume_type == 'gp3':
            base_throughput_included = EBS_GP3_BASE_THROUGHPUT_MBPS
            extra_throughput = max(0, throughput_mbps - base_throughput_included)
            
            if extra_throughput > 0:
                # Throughput is typically $0.04 per MB/s/month for gp3
                throughput_rate = 0.04
                throughput_cost = extra_throughput * throughput_rate
        
        # Calculate totals
        monthly = storage_monthly + iops_cost + throughput_cost
        hourly = monthly / 730  # Average hours per month
        daily = monthly / 30
        yearly = monthly * 12
        
        return {
            'monthly': monthly,
            'hourly': hourly,
            'daily': daily,
            'yearly': yearly,
            
            # Storage breakdown
            'storage_monthly': storage_monthly,
            'storage_rate': price_per_gb,
            'size_gb': size_gb,
            
            # IOPS breakdown
            'iops_monthly': iops_cost,
            'iops_rate': iops_rate,
            'iops_provisioned': iops,
            'iops_base_included': base_iops_included,
            'iops_extra': extra_iops,
            
            # Throughput breakdown (gp3 only)
            'throughput_monthly': throughput_cost,
            'throughput_rate': throughput_rate,
            'throughput_provisioned': throughput_mbps,
            'throughput_base_included': base_throughput_included,
            'throughput_extra': extra_throughput,
            
            # Legacy fields for compatibility
            'base_cost': storage_monthly,
            'iops_cost': iops_cost,
            'price_per_gb': price_per_gb
        }
    
    @staticmethod
    def run_etl(db_path: str = None, database_url: str = None, regions: list = None):
        """Static wrapper to load EBS pricing for specified regions"""
        loader = EBSPricingLoader(db_path=db_path, database_url=database_url)
        regions = regions or ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2', 
                             'ap-south-1', 'ap-southeast-1', 'ap-southeast-2']
        
        for region in regions:
            for volume_type in ['gp3', 'gp2', 'io1', 'io2', 'st1', 'sc1', 'standard']:
                price = loader.get_ebs_price(volume_type, region)
                logger.info(f"EBS {volume_type} in {region}: ${price}/GB/month")


def run_ebs_pricing_etl(db_path: str = None, database_url: str = None, regions: list = None):
    """Wrapper function for easy invocation"""
    EBSPricingLoader.run_etl(db_path=db_path, database_url=database_url, regions=regions)


if __name__ == "__main__":
    run_ebs_pricing_etl()
