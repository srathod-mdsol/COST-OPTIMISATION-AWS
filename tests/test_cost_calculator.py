"""
Unit tests for CostCalculator.
"""

import unittest
from analysis.cost_calculator import CostCalculator


class TestCostCalculator(unittest.TestCase):
    """Tests for CostCalculator class"""
    
    def test_calculate_rds_savings_with_price(self):
        """Test RDS savings calculation with valid price"""
        result = CostCalculator.calculate_rds_savings(0.50)
        
        self.assertEqual(result['hourly'], 0.50)
        self.assertEqual(result['monthly'], 0.50 * 730)
        self.assertEqual(result['annual'], 0.50 * 730 * 12)
    
    def test_calculate_rds_savings_zero_price(self):
        """Test RDS savings calculation with zero price"""
        result = CostCalculator.calculate_rds_savings(0)
        
        self.assertEqual(result['hourly'], 0)
        self.assertEqual(result['monthly'], 0)
        self.assertEqual(result['annual'], 0)
    
    def test_calculate_rds_savings_none_price(self):
        """Test RDS savings calculation with None price"""
        result = CostCalculator.calculate_rds_savings(None)
        
        self.assertEqual(result['hourly'], 0)
        self.assertEqual(result['monthly'], 0)
        self.assertEqual(result['annual'], 0)
    
    def test_calculate_ec2_savings_with_price(self):
        """Test EC2 savings calculation with valid price"""
        result = CostCalculator.calculate_ec2_savings(0.25)
        
        self.assertEqual(result['hourly'], 0.25)
        self.assertEqual(result['monthly'], 0.25 * 730)
        self.assertEqual(result['annual'], 0.25 * 730 * 12)
    
    def test_calculate_ec2_savings_zero_price(self):
        """Test EC2 savings calculation with zero price"""
        result = CostCalculator.calculate_ec2_savings(0)
        
        self.assertEqual(result['hourly'], 0)
        self.assertEqual(result['monthly'], 0)
        self.assertEqual(result['annual'], 0)
    
    def test_calculate_s3_savings_standard_storage(self):
        """Test S3 savings with standard storage"""
        result = CostCalculator.calculate_s3_savings(100)
        
        # Standard storage is 0.023 per GB
        expected_monthly = 100 * 0.023
        self.assertEqual(result['monthly'], expected_monthly)
        self.assertEqual(result['annual'], expected_monthly * 12)
    
    def test_calculate_s3_savings_glacier_deep_archive(self):
        """Test S3 savings with Glacier Deep Archive storage"""
        result = CostCalculator.calculate_s3_savings(1000, 'GlacierDeepArchiveStorage')
        
        # Glacier Deep Archive is 0.00099 per GB
        expected_monthly = 1000 * 0.00099
        self.assertEqual(result['monthly'], expected_monthly)
        self.assertEqual(result['annual'], expected_monthly * 12)
    
    def test_calculate_s3_savings_zero_size(self):
        """Test S3 savings with zero size"""
        result = CostCalculator.calculate_s3_savings(0)
        
        self.assertEqual(result['monthly'], 0)
        self.assertEqual(result['annual'], 0)
    
    def test_calculate_s3_savings_none_size(self):
        """Test S3 savings with None size"""
        result = CostCalculator.calculate_s3_savings(None)
        
        self.assertEqual(result['monthly'], 0)
        self.assertEqual(result['annual'], 0)
    
    def test_calculate_s3_savings_unknown_storage_class(self):
        """Test S3 savings with unknown storage class (falls back to standard)"""
        result = CostCalculator.calculate_s3_savings(100, 'UnknownStorageClass')
        
        # Should fall back to standard storage (0.023)
        expected_monthly = 100 * 0.023
        self.assertEqual(result['monthly'], expected_monthly)


if __name__ == '__main__':
    unittest.main()
