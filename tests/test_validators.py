"""
Unit tests for validation utilities.
"""

import unittest
from utils.validators import (
    validate_aws_region,
    validate_instance_id,
    validate_s3_bucket_name,
    validate_activity_threshold_days,
    validate_idle_score,
    validate_service_type,
    validate_cloudwatch_hours,
    sanitize_instance_id,
    validate_and_sanitize_instance_id,
    InputValidator
)


class TestValidateAWSRegion(unittest.TestCase):
    """Tests for validate_aws_region function"""
    
    def test_valid_regions(self):
        """Test valid AWS regions"""
        for region in ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1']:
            is_valid, error = validate_aws_region(region)
            self.assertTrue(is_valid, f"Expected {region} to be valid")
    
    def test_invalid_region(self):
        """Test invalid AWS region"""
        is_valid, error = validate_aws_region('invalid-region')
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
    
    def test_empty_region(self):
        """Test empty region"""
        is_valid, error = validate_aws_region('')
        self.assertFalse(is_valid)
        self.assertIn('empty', error.lower())


class TestValidateInstanceID(unittest.TestCase):
    """Tests for validate_instance_id function"""
    
    def test_valid_ec2_instance(self):
        """Test valid EC2 instance ID"""
        is_valid, error = validate_instance_id('i-1234567890abcdef', 'ec2')
        self.assertTrue(is_valid, f"Expected valid, got error: {error}")
    
    def test_invalid_ec2_instance(self):
        """Test invalid EC2 instance ID"""
        is_valid, error = validate_instance_id('invalid', 'ec2')
        self.assertFalse(is_valid)
    
    def test_valid_rds_instance(self):
        """Test valid RDS instance identifier"""
        is_valid, error = validate_instance_id('my-database', 'rds')
        self.assertTrue(is_valid)
    
    def test_valid_s3_bucket(self):
        """Test valid S3 bucket name"""
        is_valid, error = validate_instance_id('my-bucket', 's3')
        self.assertTrue(is_valid)


class TestValidateS3BucketName(unittest.TestCase):
    """Tests for validate_s3_bucket_name function"""
    
    def test_valid_bucket_name(self):
        """Test valid S3 bucket name"""
        is_valid, error = validate_s3_bucket_name('my-bucket-123')
        self.assertTrue(is_valid)
    
    def test_bucket_name_too_short(self):
        """Test bucket name too short"""
        is_valid, error = validate_s3_bucket_name('ab')
        self.assertFalse(is_valid)
    
    def test_bucket_name_too_long(self):
        """Test bucket name too long"""
        is_valid, error = validate_s3_bucket_name('a' * 64)
        self.assertFalse(is_valid)
    
    def test_bucket_name_uppercase(self):
        """Test bucket name with uppercase"""
        is_valid, error = validate_s3_bucket_name('MyBucket')
        self.assertFalse(is_valid)


class TestValidateActivityThresholdDays(unittest.TestCase):
    """Tests for validate_activity_threshold_days function"""
    
    def test_valid_days(self):
        """Test valid threshold days"""
        for days in [7, 14, 30, 60, 90]:
            is_valid, error = validate_activity_threshold_days(days)
            self.assertTrue(is_valid, f"Expected {days} to be valid")
    
    def test_invalid_days_too_low(self):
        """Test days below minimum"""
        is_valid, error = validate_activity_threshold_days(1)
        self.assertFalse(is_valid)
    
    def test_invalid_days_too_high(self):
        """Test days above maximum"""
        is_valid, error = validate_activity_threshold_days(100)
        self.assertFalse(is_valid)


class TestValidateIdleScore(unittest.TestCase):
    """Tests for validate_idle_score function"""
    
    def test_valid_scores(self):
        """Test valid idle scores"""
        for score in [0, 25, 50, 75, 100]:
            is_valid, error = validate_idle_score(score)
            self.assertTrue(is_valid, f"Expected {score} to be valid")
    
    def test_invalid_score_negative(self):
        """Test negative score"""
        is_valid, error = validate_idle_score(-1)
        self.assertFalse(is_valid)
    
    def test_invalid_score_too_high(self):
        """Test score above 100"""
        is_valid, error = validate_idle_score(101)
        self.assertFalse(is_valid)


class TestValidateServiceType(unittest.TestCase):
    """Tests for validate_service_type function"""
    
    def test_valid_services(self):
        """Test valid service types"""
        for service in ['ec2', 'rds', 's3']:
            is_valid, error = validate_service_type(service)
            self.assertTrue(is_valid, f"Expected {service} to be valid")
    
    def test_invalid_service(self):
        """Test invalid service type"""
        is_valid, error = validate_service_type('invalid')
        self.assertFalse(is_valid)


class TestSanitizeInstanceID(unittest.TestCase):
    """Tests for sanitize_instance_id function"""
    
    def test_no_change_needed(self):
        """Test instance ID that doesn't need sanitization"""
        result = sanitize_instance_id('i-1234567890abcdef')
        self.assertEqual(result, 'i-1234567890abcdef')
    
    def test_sanitize_special_chars(self):
        """Test sanitization of special characters"""
        result = sanitize_instance_id('i-123!@#$456')
        self.assertEqual(result, 'i-123456')
    
    def test_empty_input(self):
        """Test empty input"""
        result = sanitize_instance_id('')
        self.assertEqual(result, '')


class TestInputValidator(unittest.TestCase):
    """Tests for InputValidator class"""
    
    def test_valid_state(self):
        """Test validator in valid state"""
        validator = InputValidator()
        self.assertTrue(validator.is_valid())
        self.assertEqual(len(validator.get_errors()), 0)
    
    def test_add_error(self):
        """Test adding errors"""
        validator = InputValidator()
        validator.add_error("Test error")
        self.assertFalse(validator.is_valid())
        self.assertEqual(len(validator.get_errors()), 1)
    
    def test_clear_errors(self):
        """Test clearing errors"""
        validator = InputValidator()
        validator.add_error("Test error")
        validator.clear_errors()
        self.assertTrue(validator.is_valid())
    
    def test_validate_multiple(self):
        """Test validating multiple fields"""
        validator = InputValidator()
        validator.validate_region('us-east-1', 'region')
        validator.validate_service_type('ec2', 'service')
        validator.validate_activity_days(30, 'threshold')
        self.assertTrue(validator.is_valid())


if __name__ == '__main__':
    unittest.main()
