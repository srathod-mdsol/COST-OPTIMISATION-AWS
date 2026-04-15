"""
Unit tests for CostCalculator.
"""

import unittest
from analysis.cost_calculator import CostCalculator
from core.constants import HOURS_PER_MONTH


class TestCostCalculator(unittest.TestCase):
    """Tests for CostCalculator class"""
    
    def test_calculate_rds_savings_with_price(self):
        """Test RDS savings calculation with valid price"""
        result = CostCalculator.calculate_rds_savings(0.50)
        
        self.assertEqual(result['hourly'], 0.50)
        self.assertEqual(result['monthly'], 0.50 * HOURS_PER_MONTH)
        self.assertEqual(result['annual'], 0.50 * HOURS_PER_MONTH * 12)
    
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
        self.assertEqual(result['monthly'], 0.25 * HOURS_PER_MONTH)
        self.assertEqual(result['annual'], 0.25 * HOURS_PER_MONTH * 12)
    
    def test_calculate_ec2_savings_zero_price(self):
        """Test EC2 savings calculation with zero price"""
        result = CostCalculator.calculate_ec2_savings(0)
        
        self.assertEqual(result['hourly'], 0)
        self.assertEqual(result['monthly'], 0)
        self.assertEqual(result['annual'], 0)


if __name__ == '__main__':
    unittest.main()
