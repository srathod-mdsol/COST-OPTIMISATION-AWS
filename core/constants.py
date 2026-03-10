"""
Constants used throughout the AWS Cost Optimizer application.

This module centralizes all magic numbers and configuration constants
to improve maintainability and make changes easier.
"""

# =============================================================================
# TIME AND DURATION CONSTANTS
# =============================================================================

# Number of hours in a typical billing month (730 hours = 30.42 days)
HOURS_PER_MONTH: int = 730

# Number of hours in a year (8760 hours = 365 days)
HOURS_PER_YEAR: int = 8760

# Number of days in a typical billing month
DAYS_PER_MONTH: int = 30

# Days per year for calculations
DAYS_PER_YEAR: int = 365

# Time conversion (seconds)
SECONDS_PER_MINUTE: int = 60
SECONDS_PER_HOUR: int = 3600
SECONDS_PER_DAY: int = 86400
HOURS_PER_DAY: int = 24

# Default number of days to analyze for activity detection
DEFAULT_ACTIVITY_THRESHOLD_DAYS: int = 30

# Grace period percentage for activity detection (10% of threshold)
ACTIVITY_GRACE_PERCENTAGE: float = 0.10

# Default hours for CloudWatch metrics retrieval
DEFAULT_CLOUDWATCH_HOURS: int = 24

# Maximum days to look back for CloudWatch metrics
MAX_CLOUDWATCH_DAYS: int = 90


# =============================================================================
# ETL AND DATABASE CONSTANTS
# =============================================================================

# Lock timeout in minutes (prevents concurrent ETL runs)
LOCK_TIMEOUT_MINUTES: int = 60

# Maximum concurrent workers for ETL processing
MAX_CONCURRENT_WORKERS: int = 10

# CloudWatch API timeout in seconds
CLOUDWATCH_TIMEOUT_SECONDS: int = 60

# Batch size for processing pricing data
PRICING_BATCH_SIZE: int = 10000

# Maximum metric data queries per batch (AWS limit is 100)
METRIC_DATA_QUERY_BATCH_SIZE: int = 100


# =============================================================================
# CACHE TTL CONSTANTS (Performance Optimization)
# =============================================================================

# Pricing data cache TTL (1 hour - pricing rarely changes)
PRICING_CACHE_TTL_SECONDS: int = 3600

# Instance list cache TTL (1 minute - for UI responsiveness)
INSTANCE_LIST_CACHE_TTL_SECONDS: int = 60

# Data freshness cache TTL (5 minutes)
DATA_FRESHNESS_CACHE_TTL_SECONDS: int = 300

# Tags cache TTL (5 minutes)
TAGS_CACHE_TTL_SECONDS: int = 300

# CSS cache TTL (1 hour - static content)
CSS_CACHE_TTL_SECONDS: int = 3600

# Manager instance cache TTL (resource-level, persists across reruns)
MANAGER_CACHE_TTL_SECONDS: int = 3600


# =============================================================================
# UNIT CONVERSION CONSTANTS
# =============================================================================

# Bytes conversion
BYTES_PER_KB: int = 1024
BYTES_PER_MB: int = 1024**2
BYTES_PER_GB: int = 1024**3
BYTES_PER_TB: int = 1024**4

# Bits to Bytes
BITS_PER_BYTE: int = 8


# =============================================================================
# RESOURCE PROVISIONING CONSTANTS
# =============================================================================

# EBS GP3 default baseline performance
EBS_GP3_BASE_IOPS: int = 3000
EBS_GP3_BASE_THROUGHPUT_MBPS: int = 125

# NOTE: Storage costs should be fetched from AWS Pricing API
# Do not hardcode default prices - run pricing ETL to populate database
# The following are placeholders only and should NOT be used for calculations
DEFAULT_EBS_STORAGE_COST: float = None  # Must fetch from API
DEFAULT_RDS_STORAGE_COST: float = None  # Must fetch from API


# =============================================================================
# RATE LIMITING CONSTANTS
# =============================================================================

# Maximum AWS API calls per time period
RATE_LIMIT_MAX_CALLS: int = 100

# Time period for rate limiting (in seconds)
RATE_LIMIT_PERIOD_SECONDS: int = 60

# Maximum wait time when rate limit is hit (in seconds)
RATE_LIMIT_MAX_WAIT_SECONDS: int = 10


# =============================================================================
# IDLE DETECTION THRESHOLDS
# =============================================================================

# CPU utilization threshold for idle detection (percentage)
CPU_IDLE_THRESHOLD: float = 5.0
CPU_CRITICAL_THRESHOLD: float = 1.0

# Database connection threshold for idle (connections)
DB_CONNECTIONS_IDLE_THRESHOLD: float = 1.0

# IOPS thresholds for idle detection
READ_IOPS_IDLE_THRESHOLD: float = 1.0
WRITE_IOPS_IDLE_THRESHOLD: float = 1.0

# Network throughput threshold (bytes per second)
NETWORK_IDLE_THRESHOLD: float = 1000.0

# Disk activity thresholds (bytes)
DISK_READ_IDLE_THRESHOLD: float = 1000.0
DISK_WRITE_IDLE_THRESHOLD: float = 1000.0


# =============================================================================
# IDLE SCORE WEIGHTS
# =============================================================================

# Weight for activity-based idle detection (high priority)
ACTIVITY_WEIGHT: int = 80

# Weight for CPU low usage
CPU_LOW_WEIGHT: int = 15
CPU_VERY_LOW_WEIGHT: int = 20

# Weight for no database connections
NO_CONNECTIONS_WEIGHT: int = 20

# Weight for no IO operations
NO_READ_WEIGHT: int = 15
NO_WRITE_WEIGHT: int = 15

# Weight for minimal network activity
NETWORK_LOW_WEIGHT: int = 10

# Weight for no disk activity
DISK_READ_WEIGHT: int = 15
DISK_WRITE_WEIGHT: int = 15


# =============================================================================
# IDLE SCORE SEVERITY THRESHOLDS
# =============================================================================

SEVERITY_CRITICAL_THRESHOLD: int = 75
SEVERITY_HIGH_THRESHOLD: int = 50
SEVERITY_MEDIUM_THRESHOLD: int = 25
SEVERITY_LOW_THRESHOLD: int = 0


# =============================================================================
# UI AND DISPLAY CONSTANTS
# =============================================================================

# Default number of days for activity slider
DEFAULT_IDLE_THRESHOLD_DAYS: int = 30

# Minimum and maximum for idle threshold slider
MIN_IDLE_THRESHOLD_DAYS: int = 7
MAX_IDLE_THRESHOLD_DAYS: int = 90

# Default idle score threshold for flagging
DEFAULT_IDLE_SCORE_THRESHOLD: int = 50


# =============================================================================
# AWS Location to Region Code mapping
AWS_LOCATION_TO_REGION: dict = {
    # US Regions
    'US East (N. Virginia)': 'us-east-1',
    'US East (Ohio)': 'us-east-2',
    'US West (N. California)': 'us-west-1',
    'US West (Oregon)': 'us-west-2',
    # EU Regions
    'EU (Ireland)': 'eu-west-1',
    'EU (London)': 'eu-west-2',
    'EU (Frankfurt)': 'eu-central-1',
    'EU (Paris)': 'eu-west-3',
    'EU (Stockholm)': 'eu-north-1',
    'EU (Milan)': 'eu-south-1',
    'EU (Spain)': 'eu-south-2',
    'EU (Zurich)': 'eu-central-2',
    # Asia Pacific Regions
    'Asia Pacific (Mumbai)': 'ap-south-1',
    'Asia Pacific (Singapore)': 'ap-southeast-1',
    'Asia Pacific (Sydney)': 'ap-southeast-2',
    'Asia Pacific (Tokyo)': 'ap-northeast-1',
    'Asia Pacific (Seoul)': 'ap-northeast-2',
    'Asia Pacific (Osaka)': 'ap-northeast-3',
    'Asia Pacific (Hong Kong)': 'ap-east-1',
    'Asia Pacific (Jakarta)': 'ap-southeast-3',
    'Asia Pacific (Melbourne)': 'ap-southeast-4',
    # South America
    'South America (São Paulo)': 'sa-east-1',
    # Canada
    'Canada (Central)': 'ca-central-1',
    'Canada West (Calgary)': 'ca-west-1',
    # Middle East
    'Middle East (Bahrain)': 'me-south-1',
    'Middle East (UAE)': 'me-central-1',
    # Africa
    'Africa (Cape Town)': 'af-south-1',
    # Israel
    'Israel (Tel Aviv)': 'il-central-1',
}

# AWS REGIONS
# =============================================================================

# Common AWS regions
AWS_REGIONS: list = [
    # US Regions
    'us-east-1',    # US East (N. Virginia)
    'us-east-2',    # US East (Ohio)
    'us-west-1',    # US West (N. California)
    'us-west-2',    # US West (Oregon)
    # EU Regions
    'eu-west-1',    # EU (Ireland)
    'eu-west-2',    # EU (London)
    'eu-west-3',    # EU (Paris)
    'eu-central-1', # EU (Frankfurt)
    'eu-central-2', # EU (Zurich)
    'eu-north-1',   # EU (Stockholm)
    'eu-south-1',   # EU (Milan)
    'eu-south-2',   # EU (Spain)
    # Asia Pacific Regions
    'ap-south-1',   # Asia Pacific (Mumbai)
    'ap-southeast-1', # Asia Pacific (Singapore)
    'ap-southeast-2', # Asia Pacific (Sydney)
    'ap-southeast-3', # Asia Pacific (Jakarta)
    'ap-southeast-4', # Asia Pacific (Melbourne)
    'ap-northeast-1', # Asia Pacific (Tokyo)
    'ap-northeast-2', # Asia Pacific (Seoul)
    'ap-northeast-3', # Asia Pacific (Osaka)
    'ap-east-1',    # Asia Pacific (Hong Kong)
    # South America
    'sa-east-1',    # South America (Sao Paulo)
    # Canada
    'ca-central-1', # Canada (Central)
    'ca-west-1',    # Canada West (Calgary)
    # Middle East
    'me-south-1',   # Middle East (Bahrain)
    'me-central-1', # Middle East (UAE)
    # Africa
    'af-south-1',   # Africa (Cape Town)
    # Israel
    'il-central-1', # Israel (Tel Aviv)
]

# Default region
DEFAULT_REGION: str = 'us-east-1'


# =============================================================================
# CLOUDWATCH METRICS CONFIGURATION
# =============================================================================

# RDS CloudWatch metrics to collect
RDS_METRICS: dict = {
    'DatabaseConnections': {'stat': 'Average', 'unit': 'Count', 'ns': 'AWS/RDS'},
    'CPUUtilization': {'stat': 'Average', 'unit': 'Percent', 'ns': 'AWS/RDS'},
    'FreeableMemory': {'stat': 'Average', 'unit': 'Bytes', 'ns': 'AWS/RDS'},
    'ReadIOPS': {'stat': 'Average', 'unit': 'Count/Second', 'ns': 'AWS/RDS'},
    'WriteIOPS': {'stat': 'Average', 'unit': 'Count/Second', 'ns': 'AWS/RDS'},
    'NetworkReceiveThroughput': {'stat': 'Average', 'unit': 'Bytes/Second', 'ns': 'AWS/RDS'},
    'NetworkTransmitThroughput': {'stat': 'Average', 'unit': 'Bytes/Second', 'ns': 'AWS/RDS'},
    'ReadLatency': {'stat': 'Average', 'unit': 'Seconds', 'ns': 'AWS/RDS'},
    'WriteLatency': {'stat': 'Average', 'unit': 'Seconds', 'ns': 'AWS/RDS'},
    'ReadThroughput': {'stat': 'Average', 'unit': 'Bytes/Second', 'ns': 'AWS/RDS'},
    'WriteThroughput': {'stat': 'Average', 'unit': 'Bytes/Second', 'ns': 'AWS/RDS'}
}

# EC2 CloudWatch metrics to collect
EC2_METRICS: dict = {
    'CPUUtilization': {'stat': 'Average', 'unit': 'Percent', 'ns': 'AWS/EC2'},
    'NetworkIn': {'stat': 'Average', 'unit': 'Bytes', 'ns': 'AWS/EC2'},
    'NetworkOut': {'stat': 'Average', 'unit': 'Bytes', 'ns': 'AWS/EC2'},
    'DiskReadBytes': {'stat': 'Average', 'unit': 'Bytes', 'ns': 'AWS/EC2'},
    'DiskWriteBytes': {'stat': 'Average', 'unit': 'Bytes', 'ns': 'AWS/EC2'},
    'DiskReadOps': {'stat': 'Average', 'unit': 'Count', 'ns': 'AWS/EC2'},
    'DiskWriteOps': {'stat': 'Average', 'unit': 'Count', 'ns': 'AWS/EC2'}
}


# =============================================================================
# ACTIVITY DETECTION METRICS
# =============================================================================

# Metrics to check for activity detection per service
RDS_ACTIVITY_METRICS: list = [
    'DatabaseConnections',
    'ReadIOPS',
    'WriteIOPS',
    'CPUUtilization'
]

EC2_ACTIVITY_METRICS: list = [
    'CPUUtilization',
    'NetworkIn',
    'NetworkOut'
]


# =============================================================================
# ACTIVITY THRESHOLDS FOR DETECTION
# =============================================================================

# Minimum values to consider as "activity" (non-idle)
ACTIVITY_THRESHOLDS: dict = {
    'DatabaseConnections': 0.5,
    'ReadIOPS': 1,
    'WriteIOPS': 1,
    'CPUUtilization': 5,
    'NetworkTransmitThroughput': 1000,
    'NetworkIn': 1000,
    'NetworkOut': 1000
}
