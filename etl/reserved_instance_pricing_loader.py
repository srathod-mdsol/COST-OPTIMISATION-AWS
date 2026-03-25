"""
Reserved Instance Pricing Loader - Loads and caches Reserved Instance pricing data.
Supports EC2 and RDS Reserved Instances.

Reserved Instances offer significant discounts compared to On-Demand pricing.
This loader handles different term lengths and payment options.
"""

import boto3
import json
from typing import Optional, Dict, List
from core.logger import setup_logger
from core.config import Config
from core.constants import AWS_LOCATION_TO_REGION, HOURS_PER_MONTH
from etl.base_db import BaseDatabase, DatabaseType

logger = setup_logger(__name__)


class ReservedInstancePricingLoader(BaseDatabase):
    """
    Loads Reserved Instance pricing from AWS Pricing API.
    Supports EC2 and RDS Reserved Instances with various term options.
    """
    
    PRICING_REGION = "us-east-1"
    
    # Term lengths
    TERM_LENGTHS = ['1year', '3year']
    
    # Payment options
    PAYMENT_OPTIONS = ['All Upfront', 'Partial Upfront', 'No Upfront']
    
    # Default discount factors (fallback if API fails)
    # These are approximate - actual prices vary by instance type/region
    DEFAULT_RI_DISCOUNTS = {
        '1year': {
            'All Upfront': 0.60,      # ~60% savings
            'Partial Upfront': 0.45,   # ~45% savings
            'No Upfront': 0.30        # ~30% savings
        },
        '3year': {
            'All Upfront': 0.65,      # ~65% savings
            'Partial Upfront': 0.55,   # ~55% savings
            'No Upfront': 0.40        # ~40% savings
        }
    }
    
    def __init__(self, db_path: str = None, database_url: str = None):
        """Initialize Reserved Instance pricing loader"""
        if database_url is None:
            database_url = Config.get_pricing_database_url()
        
        super().__init__(database_url)
        
        self.db_path = db_path or Config.PRICING_DB_PATH
        self.pricing = boto3.client('pricing', region_name=self.PRICING_REGION)
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """Create Reserved Instance pricing table"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS ri_pricing (
            sku TEXT PRIMARY KEY,
            service_code TEXT NOT NULL,
            instance_type TEXT NOT NULL,
            region TEXT NOT NULL,
            term_length TEXT NOT NULL,
            payment_option TEXT NOT NULL,
            price_per_hour REAL NOT NULL,
            upfront_price REAL,
            currency TEXT DEFAULT 'USD',
            location TEXT,
            raw_json TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.execute(create_table_sql)
        
        # Create indexes
        self.create_index_if_not_exists('idx_ri_pricing_lookup', 'ri_pricing', 
            ['service_code', 'instance_type', 'region', 'term_length', 'payment_option'])
        
        logger.info("Reserved Instance pricing table schema verified")
    
    def get_ri_price(
        self,
        service_code: str,  # AmazonEC2 or AmazonRDS
        instance_type: str,
        region: str,
        term_length: str = '1year',
        payment_option: str = 'Partial Upfront'
    ) -> Optional[Dict]:
        """
        Get Reserved Instance price.
        
        Args:
            service_code: AmazonEC2 or AmazonRDS
            instance_type: Instance type (e.g., t3.micro, db.t3.micro)
            region: AWS region code
            term_length: 1year or 3year
            payment_option: All Upfront, Partial Upfront, No Upfront
            
        Returns:
            Dictionary with price details or None if not found
        """
        # Try local database first
        price_data = self._get_local_price(service_code, instance_type, region, term_length, payment_option)
        if price_data:
            return price_data
        
        # Try to fetch from AWS API
        price_data = self._fetch_from_aws_api(service_code, instance_type, region, term_length, payment_option)
        if price_data:
            self._cache_price(price_data)
            return price_data
        
        # Fall back to default discounts
        return self._get_default_discount(service_code, instance_type, region, term_length, payment_option)
    
    def _get_local_price(
        self,
        service_code: str,
        instance_type: str,
        region: str,
        term_length: str,
        payment_option: str
    ) -> Optional[Dict]:
        """Get RI price from local database"""
        try:
            location = self._region_to_location(region)
            
            row = self.fetch_one(
                """
                SELECT price_per_hour, upfront_price FROM ri_pricing 
                WHERE service_code = :service_code 
                AND instance_type = :instance_type 
                AND (region = :region OR region = :location)
                AND term_length = :term_length 
                AND payment_option = :payment_option
                LIMIT 1
                """,
                {
                    "service_code": service_code,
                    "instance_type": instance_type,
                    "region": region,
                    "location": location,
                    "term_length": term_length,
                    "payment_option": payment_option
                }
            )
            
            if row:
                logger.debug(f"Found local RI price for {instance_type} in {region}")
                return {
                    'price_per_hour': row[0],
                    'upfront_price': row[1],
                    'is_default': False
                }
            
            return None
        except Exception as e:
            logger.warning(f"Error querying local RI price: {e}")
            return None
    
    def _cache_price(self, price_data: Dict):
        """Cache RI price in local database"""
        try:
            location = self._region_to_location(price_data['region'])
            sku = f"ri-{price_data['service_code']}-{price_data['instance_type']}-{price_data['region']}-{price_data['term_length']}-{price_data['payment_option']}"
            
            if self.db_type == DatabaseType.POSTGRESQL:
                self.execute(
                    """
                    INSERT INTO ri_pricing (sku, service_code, instance_type, region, term_length, 
                                          payment_option, price_per_hour, upfront_price, currency, location)
                    VALUES (:sku, :service_code, :instance_type, :region, :term_length,
                            :payment_option, :price_per_hour, :upfront_price, 'USD', :location)
                    ON CONFLICT (sku) DO UPDATE SET
                        price_per_hour = EXCLUDED.price_per_hour,
                        upfront_price = EXCLUDED.upfront_price
                    """,
                    price_data
                )
            elif self.db_type == DatabaseType.MYSQL:
                self.execute(
                    """
                    INSERT INTO ri_pricing (sku, service_code, instance_type, region, term_length,
                                          payment_option, price_per_hour, upfront_price, currency, location)
                    VALUES (:sku, :service_code, :instance_type, :region, :term_length,
                            :payment_option, :price_per_hour, :upfront_price, 'USD', :location)
                    ON DUPLICATE KEY UPDATE
                        price_per_hour = VALUES(price_per_hour),
                        upfront_price = VALUES(upfront_price)
                    """,
                    price_data
                )
            else:
                self.execute(
                    """
                    INSERT OR REPLACE INTO ri_pricing (sku, service_code, instance_type, region, term_length,
                                                      payment_option, price_per_hour, upfront_price, currency, location)
                    VALUES (:sku, :service_code, :instance_type, :region, :term_length,
                            :payment_option, :price_per_hour, :upfront_price, 'USD', :location)
                    """,
                    price_data
                )
            
            logger.debug(f"Cached RI price for {price_data['instance_type']}")
        except Exception as e:
            logger.warning(f"Error caching RI price: {e}")
    
    def _fetch_from_aws_api(
        self,
        service_code: str,
        instance_type: str,
        region: str,
        term_length: str,
        payment_option: str
    ) -> Optional[Dict]:
        """Fetch RI price from AWS Pricing API"""
        location = self._region_to_location(region)
        
        # Convert term length
        lease_length = term_length.replace('year', '')
        
        try:
            response = self.pricing.get_products(
                ServiceCode=service_code,
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                    {"Type": "TERM_MATCH", "Field": "leaseContractLength", "Value": lease_length},
                    {"Type": "TERM_MATCH", "Field": "offeringType", "Value": payment_option},
                    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Compute Instance" if service_code == "AmazonEC2" else "Database Instance"}
                ],
                MaxResults=1,
            )
            
            price_list = response.get("PriceList", [])
            if not price_list:
                logger.warning(f"No RI price found for {instance_type} in {region}")
                return None
            
            price_item = json.loads(price_list[0])
            terms = price_item.get("terms", {}).get("Reserved", {})
            
            for term_sku, term_data in terms.items():
                for price_dim in term_data.get("priceDimensions", {}).values():
                    price = float(price_dim.get("pricePerUnit", {}).get("USD", 0))
                    if price > 0:
                        # Extract upfront price if available
                        upfront = 0.0
                        # RI pricing can have upfront and hourly components
                        
                        return {
                            'sku': term_sku,
                            'service_code': service_code,
                            'instance_type': instance_type,
                            'region': region,
                            'term_length': term_length,
                            'payment_option': payment_option,
                            'price_per_hour': price,
                            'upfront_price': upfront,
                            'location': location
                        }
            
            return None
        except Exception as e:
            logger.error(f"Error fetching RI price from AWS API: {e}")
            return None
    
    def _get_default_discount(
        self,
        service_code: str,
        instance_type: str,
        region: str,
        term_length: str,
        payment_option: str
    ) -> Dict:
        """Calculate default RI discount (fallback)"""
        # Get On-Demand price first
        on_demand_price = self._get_on_demand_price(service_code, instance_type, region)
        
        # Get discount factor
        discount = self.DEFAULT_RI_DISCOUNTS.get(term_length, {}).get(payment_option, 0.40)
        
        ri_price = on_demand_price * (1 - discount)
        
        return {
            'price_per_hour': ri_price,
            'upfront_price': 0,
            'is_default': True,
            'on_demand_price': on_demand_price,
            'discount_percent': discount * 100,
            'term_length': term_length,
            'payment_option': payment_option
        }
    
    def _get_on_demand_price(self, service_code: str, instance_type: str, region: str) -> float:
        """Get On-Demand price for reference"""
        try:
            from etl.pricing_loader import PricingLoader
            loader = PricingLoader()
            return loader.get_pricing(instance_type, region, service=service_code.replace('Amazon', ''))
        except Exception as e:
            logger.warning(f"Failed to get on-demand price for {instance_type} in {region}: {e}")
            return 0.0
    
    def _region_to_location(self, region: str) -> str:
        """Convert region code to AWS location name"""
        for location, region_code in AWS_LOCATION_TO_REGION.items():
            if region_code == region:
                return location
        return 'US East (N. Virginia)'
    
    def calculate_savings(
        self,
        on_demand_hourly: float,
        term_length: str = '1year',
        payment_option: str = 'Partial Upfront'
    ) -> Dict:
        """Calculate potential RI savings"""
        ri_price = self._get_default_discount(
            'AmazonEC2', '', '', term_length, payment_option
        )
        
        discount = ri_price.get('discount_percent', 40) / 100
        ri_hourly = on_demand_hourly * (1 - discount)
        savings_hourly = on_demand_hourly - ri_hourly
        
        return {
            'on_demand_hourly': on_demand_hourly,
            'ri_hourly': ri_hourly,
            'savings_hourly': savings_hourly,
            'savings_monthly': savings_hourly * HOURS_PER_MONTH,
            'savings_annual': savings_hourly * HOURS_PER_MONTH * 12,
            'discount_percent': discount * 100,
            'term_length': term_length,
            'payment_option': payment_option
        }


def run_ri_pricing_etl(db_path: str = None, database_url: str = None, regions: list = None):
    """Wrapper function for easy invocation"""
    loader = ReservedInstancePricingLoader(db_path=db_path, database_url=database_url)
    logger.info("Reserved Instance pricing ETL complete")


if __name__ == "__main__":
    run_ri_pricing_etl()
