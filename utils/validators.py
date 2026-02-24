"""
Input validation utilities for AWS Cost Optimizer.

This module provides validation functions for user inputs to prevent
errors and ensure data integrity.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from core.constants import AWS_REGIONS, MIN_IDLE_THRESHOLD_DAYS, MAX_IDLE_THRESHOLD_DAYS


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


def validate_aws_region(region: str) -> Tuple[bool, Optional[str]]:
    """
    Validate AWS region code.
    
    Args:
        region: AWS region code (e.g., 'us-east-1')
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not region:
        return False, "Region cannot be empty"
    
    if region not in AWS_REGIONS:
        return False, f"Invalid region '{region}'. Valid regions: {', '.join(AWS_REGIONS)}"
    
    return True, None


def validate_instance_id(instance_id: str, service_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validate AWS instance ID format.
    
    Args:
        instance_id: The instance ID to validate
        service_type: Type of AWS service ('ec2', 'rds', 's3')
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not instance_id:
        return False, "Instance ID cannot be empty"
    
    if service_type.lower() == 'ec2':
        # EC2 instance IDs start with 'i-' followed by 8-17 hexadecimal characters
        if not re.match(r'^i-[0-9a-f]{8,17}$', instance_id):
            return False, f"Invalid EC2 instance ID format: {instance_id}. Expected format: i-xxxxxxxxxxxxxxxxx"
    
    elif service_type.lower() == 'rds':
        # RDS instance identifiers are 1-63 characters, alphanumeric
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9]*(-[a-zA-Z0-9]+)*$', instance_id):
            return False, f"Invalid RDS instance identifier: {instance_id}"
    
    elif service_type.lower() == 's3':
        # S3 bucket names must be 3-63 characters, lowercase, numbers, hyphens, periods
        if not re.match(r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$', instance_id):
            return False, f"Invalid S3 bucket name: {instance_id}. Bucket names must be 3-63 characters, lowercase, numbers, hyphens, or periods"
    
    return True, None


def validate_s3_bucket_name(bucket_name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate S3 bucket name.
    
    Args:
        bucket_name: S3 bucket name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not bucket_name:
        return False, "Bucket name cannot be empty"
    
    # S3 bucket naming rules
    if len(bucket_name) < 3 or len(bucket_name) > 63:
        return False, f"Bucket name must be between 3 and 63 characters: {bucket_name}"
    
    if not re.match(r'^[a-z0-9][a-z0-9.-]*[a-z0-9]$', bucket_name):
        return False, "Bucket name must be lowercase, can contain numbers, hyphens, and periods"
    
    # Check for reserved names
    reserved_names = {'aws', 'amazon', 'alexa'}
    if bucket_name.startswith('aws-') or bucket_name in reserved_names:
        return False, f"Bucket name '{bucket_name}' is reserved"
    
    # IP address format check
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', bucket_name):
        return False, "Bucket name cannot be an IP address"
    
    return True, None


def validate_activity_threshold_days(days: int) -> Tuple[bool, Optional[str]]:
    """
    Validate activity threshold days value.
    
    Args:
        days: Number of days for activity threshold
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(days, int):
        return False, f"Threshold must be an integer, got {type(days).__name__}"
    
    if days < MIN_IDLE_THRESHOLD_DAYS or days > MAX_IDLE_THRESHOLD_DAYS:
        return False, f"Threshold must be between {MIN_IDLE_THRESHOLD_DAYS} and {MAX_IDLE_THRESHOLD_DAYS} days"
    
    return True, None


def validate_idle_score(score: float) -> Tuple[bool, Optional[str]]:
    """
    Validate idle score value.
    
    Args:
        score: Idle score percentage (0-100)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(score, (int, float)):
        return False, f"Idle score must be a number, got {type(score).__name__}"
    
    if score < 0 or score > 100:
        return False, f"Idle score must be between 0 and 100, got {score}"
    
    return True, None


def validate_service_type(service_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validate AWS service type.
    
    Args:
        service_type: Service type ('ec2', 'rds', 's3')
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    valid_services = {'ec2', 'rds', 's3'}
    
    if not service_type:
        return False, "Service type cannot be empty"
    
    if service_type.lower() not in valid_services:
        return False, f"Invalid service type '{service_type}'. Valid types: {', '.join(valid_services)}"
    
    return True, None


def validate_hours(hours: int, max_hours: int = 168) -> Tuple[bool, Optional[str]]:
    """
    Validate hours parameter for CloudWatch queries.
    
    Args:
        hours: Number of hours to query
        max_hours: Maximum allowed hours (default: 168 = 7 days)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(hours, int):
        return False, f"Hours must be an integer, got {type(hours).__name__}"
    
    if hours < 1:
        return False, "Hours must be at least 1"
    
    if hours > max_hours:
        return False, f"Hours cannot exceed {max_hours} (CloudWatch limit)"
    
    return True, None


def validate_cloudwatch_hours(hours: int) -> Tuple[bool, Optional[str]]:
    """
    Validate CloudWatch metrics retrieval hours.
    
    Args:
        hours: Number of hours for CloudWatch data
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    return validate_hours(hours, max_hours=90)  # CloudWatch has 90-day limit


def sanitize_instance_id(instance_id: str) -> str:
    """
    Sanitize instance ID by removing potentially harmful characters.
    
    Args:
        instance_id: Instance ID to sanitize
        
    Returns:
        Sanitized instance ID
    """
    if not instance_id:
        return ""
    
    # Remove any non-alphanumeric characters except hyphens and periods
    return re.sub(r'[^a-zA-Z0-9.-]', '', instance_id)


def validate_and_sanitize_instance_id(instance_id: str, service_type: str) -> Tuple[str, Optional[str]]:
    """
    Validate and sanitize an instance ID.
    
    Args:
        instance_id: Instance ID to validate
        service_type: Type of AWS service
        
    Returns:
        Tuple of (sanitized_id, error_message)
    """
    sanitized = sanitize_instance_id(instance_id)
    
    if not sanitized:
        return "", "Instance ID cannot be empty after sanitization"
    
    is_valid, error = validate_instance_id(sanitized, service_type)
    
    if not is_valid:
        return sanitized, error
    
    return sanitized, None


class InputValidator:
    """
    Utility class for validating multiple inputs.
    """
    
    def __init__(self):
        self.errors: List[str] = []
    
    def add_error(self, message: str) -> None:
        """Add an error message"""
        self.errors.append(message)
    
    def is_valid(self) -> bool:
        """Check if all validations passed"""
        return len(self.errors) == 0
    
    def get_errors(self) -> List[str]:
        """Get list of error messages"""
        return self.errors
    
    def clear_errors(self) -> None:
        """Clear all errors"""
        self.errors = []
    
    def validate_region(self, region: str, field_name: str = "region") -> bool:
        """Validate AWS region"""
        is_valid, error = validate_aws_region(region)
        if not is_valid:
            self.add_error(f"{field_name}: {error}")
        return is_valid
    
    def validate_service_type(self, service_type: str, field_name: str = "service") -> bool:
        """Validate service type"""
        is_valid, error = validate_service_type(service_type)
        if not is_valid:
            self.add_error(f"{field_name}: {error}")
        return is_valid
    
    def validate_instance_id(self, instance_id: str, service_type: str, field_name: str = "instance") -> bool:
        """Validate instance ID"""
        is_valid, error = validate_instance_id(instance_id, service_type)
        if not is_valid:
            self.add_error(f"{field_name}: {error}")
        return is_valid
    
    def validate_activity_days(self, days: int, field_name: str = "threshold") -> bool:
        """Validate activity threshold days"""
        is_valid, error = validate_activity_threshold_days(days)
        if not is_valid:
            self.add_error(f"{field_name}: {error}")
        return is_valid
