# AWS Cost Optimizer - Idle Instance Cost Calculation

## Overview

This document provides comprehensive documentation on how the AWS Cost Optimizer application calculates the cost of idle EC2 and RDS instances.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Idle Detection Methodology](#idle-detection-methodology)
3. [EC2 Idle Cost Calculation](#ec2-idle-cost-calculation)
4. [RDS Idle Cost Calculation](#rds-idle-cost-calculation)
5. [Cost Calculation Parameters](#cost-calculation-parameters)
6. [Data Flow](#data-flow)
7. [API Integration](#api-integration)

---

## Architecture Overview

The application consists of several key components:

```
┌─────────────────────────────────────────────────────────────────┐
│                     AWS Cost Optimizer                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ EC2 Manager  │  │ RDS Manager  │  │   EBS Manager     │   │
│  └──────────────┘  └──────────────┘  └────────────────────┘   │
│           │               │                    │               │
│           └───────────────┼────────────────────┘               │
│                           ▼                                    │
│              ┌────────────────────────┐                         │
│              │   ETL Data Provider    │                         │
│              │   (CloudWatch Data)   │                         │
│              └────────────────────────┘                         │
│                           │                                    │
│           ┌───────────────┼───────────────┐                     │
│           ▼               ▼               ▼                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Idle Analyzer│  │    Cost      │  │   Pricing   │          │
│  │              │  │  Calculator  │  │   Loader    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│           │               │                                   │
│           └───────────────┼───────────────────────┐            │
│                           ▼                               ▼    │
│              ┌────────────────────────┐  ┌──────────────┐     │
│              │    Dashboard/UI         │  │    CLI       │     │
│              └────────────────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Idle Detection Methodology

### 1. Activity-Based Detection (Primary)

The application uses **activity-based detection** as the primary method to identify idle instances. This is weighted highest (80 points).

```python
# From analysis/idle_analyzer.py
ACTIVITY_WEIGHT = 80

# Detection Logic:
if days_since_activity >= activity_threshold_days (default: 30):
    # Mark as CRITICAL idle
    idle_score += ACTIVITY_WEIGHT (80 points)
elif days_since_activity >= grace_period:
    # Grace period is 10% of threshold (default: 3 days)
    # Add proportional weight
    idle_score += ACTIVITY_WEIGHT * progress_ratio * 0.5
```

### 2. Metrics-Based Detection (Secondary)

The application also analyzes CloudWatch metrics to detect idle instances:

#### RDS Metrics Analyzed:

| Metric | Threshold | Weight | Idle Indicator |
|--------|-----------|--------|----------------|
| CPUUtilization | < 5% | 15-20 | Low CPU usage |
| DatabaseConnections | < 1 | 20 | No connections |
| ReadIOPS | < 1 | 15 | No read operations |
| WriteIOPS | < 1 | 15 | No write operations |
| NetworkThroughput | < 1000 B/s | 10 | Minimal network |

#### EC2 Metrics Analyzed:

| Metric | Threshold | Weight | Idle Indicator |
|--------|-----------|--------|----------------|
| CPUUtilization | < 5% | 15-20 | Low CPU usage |
| NetworkIn | < 1000 B | 10 | No incoming traffic |
| NetworkOut | < 1000 B | 10 | No outgoing traffic |
| DiskReadBytes | < 1000 B | 15 | No disk reads |
| DiskWriteBytes | < 1000 B | 15 | No disk writes |

### 3. Idle Score Calculation

```python
# Total possible score: 100 points
idle_score = sum(indicator['weight'] for indicator in indicators)
idle_score = min(100, idle_score)  # Cap at 100
```

### 4. Severity Classification

| Idle Score | Severity | Action |
|------------|----------|--------|
| 75-100 | CRITICAL | 🚨 Immediate action recommended |
| 50-74 | HIGH | ⚠️ Consider stopping/terminating |
| 25-49 | MEDIUM | 📊 Review for optimization |
| 0-24 | LOW | ✅ Active instance |

---

## EC2 Idle Cost Calculation

### Step 1: Gather Instance Data

```python
# From services/ec2_manager.py
ec2_data = {
    'instance_id': 'i-xxxxxxxx',
    'instance_type': 't3.micro',      # From DescribeInstances
    'region': 'us-east-1',            # From AvailabilityZone
    'platform': 'Linux/UNIX',          # From Platform field
    'tenancy': 'shared',              # From Placement.Tenancy
    'state': 'running',               # From State.Name
}
```

### Step 2: Get Pricing from AWS API

```python
# All parameters for accurate pricing lookup:
pricing = get_pricing(
    instance_type='t3.micro',         # Instance type
    region='us-east-1',               # Region
    service='EC2',                     # Service
    operating_system='Linux',          # Platform (Linux/Windows/RHEL/SLES)
    tenancy='shared'                   # Tenancy (shared/dedicated/host)
)
# Result: $0.0104/hour (example)
```

### Step 3: Get EBS Volume Costs

```python
# Attached EBS volumes from EC2 DescribeVolumes
volumes = [
    {
        'volume_id': 'vol-xxx',
        'size_gb': 8,
        'volume_type': 'gp3',
        'iops': 3000
    }
]

# Calculate each volume cost
for vol in volumes:
    ebs_cost = calculate_ebs_cost(
        size_gb=vol['size_gb'],
        volume_type=vol['volume_type'],
        iops=vol.get('iops'),
        region=region
    )
```

### Step 4: Calculate Total EC2 Cost

```python
# Formula:
hourly_cost = instance_hourly_price + sum(ebs_volume_costs)
monthly_cost = hourly_cost * 730  # Average billing hours
yearly_cost = monthly_cost * 12
```

### Example Calculation:

```
Instance: t3.micro in us-east-1 (Linux)
- Instance Price: $0.0104/hour
- EBS Volume: 8 GB gp3: $0.08/GB = $0.64/month

Monthly Cost = ($0.0104 * 730) + $0.64
             = $7.59 + $0.64
             = $8.23/month

Yearly Cost = $8.23 * 12 = $98.76/year
```

---

## RDS Idle Cost Calculation

### Step 1: Gather Instance Data

```python
# From services/rds_manager.py
rds_data = {
    'instance_id': 'mydb',
    'instance_class': 'db.t3.micro',   # From DBInstanceClass
    'engine': 'postgres',              # From Engine
    'engine_version': '14.7',         # From EngineVersion
    'allocated_storage': 100,          # From AllocatedStorage (GB)
    'storage_type': 'gp2',             # From StorageType
    'iops': 0,                        # From Iops
    'multi_az': True,                 # From MultiAZ
    'license_model': 'included',      # From LicenseModel
    'region': 'us-east-1',            # From AvailabilityZone
}
```

### Step 2: Get RDS Instance Pricing

```python
# All parameters for accurate RDS pricing:
instance_price = get_pricing(
    instance_type='db.t3.micro',       # Instance class
    region='us-east-1',                # Region
    service='RDS',                    # Service
    database_engine='postgres',        # Engine (postgres/mysql/oracle/etc.)
    deployment_option='Multi-AZ',      # Single-AZ or Multi-AZ
    license_model='included'          # included or BYOL
)
# Result: $0.017/hour (example)
```

### Step 3: Calculate RDS Storage Cost (CRITICAL!)

**IMPORTANT**: RDS storage pricing is DIFFERENT from EC2 EBS pricing!

```python
# RDS-specific storage pricing (from etl/rds_storage_pricing_loader.py)
storage_cost = calculate_rds_storage_cost(
    allocated_storage=100,            # GB
    storage_type='gp2',               # gp2/gp3/io1/io2/magnetic
    iops=0,                           # Provisioned IOPS
    multi_az=True,                    # Multi-AZ requires 2x storage!
    region='us-east-1'
)
```

#### Multi-AZ Calculation:

```python
# Multi-AZ requires storage in BOTH availability zones!
storage_multiplier = 2.0 if multi_az else 1.0
effective_storage = allocated_storage * storage_multiplier

# Example: 100GB with Multi-AZ = 200GB charged
# RDS gp2 price: $0.115/GB/month
# Monthly Storage = 200 * $0.115 = $23.00/month
```

### Step 4: Calculate Total RDS Cost

```python
# Formula:
hourly_cost = instance_hourly_price + (storage_monthly / 730) + (iops_monthly / 730)
monthly_cost = (instance_hourly_price * 730) + storage_monthly + iops_monthly
yearly_cost = monthly_cost * 12
```

### Example Calculation:

```
Instance: db.t3.micro in us-east-1 (PostgreSQL, Multi-AZ)
- Instance Price: $0.017/hour
- Storage: 100 GB gp2 x 2 (Multi-AZ) = 200 GB
- Storage Price: $0.115/GB/month

Monthly Instance Cost = $0.017 * 730 = $12.41
Monthly Storage Cost = 200 * $0.115 = $23.00

Total Monthly Cost = $12.41 + $23.00 = $35.41/month
Total Yearly Cost = $35.41 * 12 = $424.92/year
```

---

## Cost Calculation Parameters

### EC2 Parameters

| Parameter | Source | Used For |
|-----------|--------|----------|
| instance_type | DescribeInstances | Instance pricing |
| region | AvailabilityZone | Regional pricing |
| operating_system | Platform | Linux/Windows/RHEL/SLES pricing |
| tenancy | Placement.Tenancy | shared/dedicated/host pricing |
| ebs_volumes | DescribeVolumes | EBS storage costs |
| ebs_iops | DescribeVolumes | Provisioned IOPS costs |

### RDS Parameters

| Parameter | Source | Used For |
|-----------|--------|----------|
| instance_class | DescribeDBInstances | Instance pricing |
| database_engine | DescribeDBInstances | postgres/mysql/oracle pricing |
| deployment_option | DescribeDBInstances | Single-AZ/Multi-AZ pricing |
| license_model | DescribeDBInstances | included/BYOL pricing |
| allocated_storage | DescribeDBInstances | Storage cost |
| storage_type | DescribeDBInstances | gp2/gp3/io1/io2 pricing |
| iops | DescribeDBInstances | Provisioned IOPS cost |
| multi_az | DescribeDBInstances | Multi-AZ multiplier (2x) |

---

## Data Flow

### 1. ETL Process (Data Collection)

```
AWS API                          ETL Database
─────────                        ────────────
DescribeInstances      ──►        raw_instances (EC2)
DescribeDBInstances   ──►        raw_instances (RDS)
DescribeVolumes       ──►        raw_instances (EBS)
CloudWatch Metrics   ──►        raw_metrics
```

### 2. Idle Analysis Process

```
ETL Database                     Idle Analyzer
────────────                     ─────────────
raw_instances    ──────────►    Get instance data
raw_metrics      ──────────►    Analyze metrics
                             
                              Calculate idle score
                              Determine severity
```

### 3. Cost Calculation Process

```
Idle Analyzer    Pricing Loader    Cost Calculator
────────────     ────────────     ───────────────
idle_score  ──►              ──► Calculate savings
severity    ──►              ──► Hourly/Daily/Monthly/Yearly
instance    ──► get_pricing() ──► Full cost breakdown
details     ──►  (from API)  ──►
```

---

## API Integration

### AWS Services Used

| Service | API Calls | Purpose |
|---------|-----------|---------|
| EC2 | DescribeInstances | Get EC2 instance data |
| EC2 | DescribeVolumes | Get EBS volume data |
| RDS | DescribeDBInstances | Get RDS instance data |
| CloudWatch | GetMetricStatistics | Get performance metrics |
| CloudWatch | GetMetricData | Batch metrics retrieval |
| Pricing | GetProducts | Get on-demand pricing |
| Pricing | GetProducts | Get Reserved Instance pricing |

### Pricing API Filters

#### EC2 Pricing:
```python
{
    'ServiceCode': 'AmazonEC2',
    'Filters': [
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
        {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': os},
        {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': tenancy}
    ]
}
```

#### RDS Pricing:
```python
{
    'ServiceCode': 'AmazonRDS',
    'Filters': [
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
        {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': engine},
        {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ' or 'Multi-AZ'},
        {'Type': 'TERM_MATCH', 'Field': 'licenseModel', 'Value': license_model}
    ]
}
```

---

## Idle Detection Thresholds

### Configurable Parameters (from core/constants.py)

```python
# Idle Thresholds
CPU_IDLE_THRESHOLD = 5.0           # % CPU utilization
CPU_CRITICAL_THRESHOLD = 1.0      # % for critical
DB_CONNECTIONS_IDLE_THRESHOLD = 1.0  # connections
READ_IOPS_IDLE_THRESHOLD = 1.0   # IOPS
WRITE_IOPS_IDLE_THRESHOLD = 1.0   # IOPS
NETWORK_IDLE_THRESHOLD = 1000.0   # bytes/second
DISK_READ_IDLE_THRESHOLD = 1000.0 # bytes
DISK_WRITE_IDLE_THRESHOLD = 1000.0 # bytes

# Weights
ACTIVITY_WEIGHT = 80               # Primary indicator
CPU_LOW_WEIGHT = 15
CPU_VERY_LOW_WEIGHT = 20
NO_CONNECTIONS_WEIGHT = 20
NO_READ_WEIGHT = 15
NO_WRITE_WEIGHT = 15
NETWORK_LOW_WEIGHT = 10
DISK_READ_WEIGHT = 15
DISK_WRITE_WEIGHT = 15

# Severity Thresholds
SEVERITY_CRITICAL_THRESHOLD = 75
SEVERITY_HIGH_THRESHOLD = 50
SEVERITY_MEDIUM_THRESHOLD = 25

# Activity Detection
DEFAULT_ACTIVITY_THRESHOLD_DAYS = 30
ACTIVITY_GRACE_PERCENTAGE = 0.10  # 10% of threshold
```

---

## Output Examples

### EC2 Instance Analysis

```json
{
  "instance_id": "i-0abc123def456789",
  "instance_type": "t3.micro",
  "service": "EC2",
  "idle_score": 80,
  "severity": "CRITICAL",
  "recommendation": "🚨 CRITICAL: No activity detected in last 30 days",
  "potential_savings": {
    "hourly": 0.0104,
    "daily": 0.2496,
    "monthly": 7.59,
    "yearly": 91.08
  },
  "indicators": [
    {
      "name": "No Activity in Last 30 Days",
      "value": "No activity detected",
      "severity": "critical",
      "weight": 80
    }
  ]
}
```

### RDS Instance Analysis

```json
{
  "instance_id": "mydb-production",
  "instance_class": "db.t3.micro",
  "engine": "postgres",
  "service": "RDS",
  "idle_score": 80,
  "severity": "CRITICAL",
  "recommendation": "🚨 CRITICAL: No activity detected in last 30 days",
  "potential_savings": {
    "hourly": 0.0485,
    "daily": 1.164,
    "monthly": 35.41,
    "yearly": 424.92
  },
  "breakdown": {
    "instance_hourly": 0.017,
    "instance_monthly": 12.41,
    "storage_monthly": 23.00,
    "storage_hourly": 0.0315,
    "allocated_storage_gb": 100,
    "storage_type": "gp2",
    "multi_az": true,
    "effective_storage_gb": 200,
    "price_per_gb": 0.115
  }
}
```

---

## Summary

The application calculates idle instance costs by:

1. **Detecting Idle Instances**: Using CloudWatch metrics and activity timestamps
2. **Scoring System**: Weighted idle score (0-100) based on multiple factors
3. **Getting Accurate Pricing**: All prices from AWS Pricing API (no hardcoded values)
4. **Including All Costs**: Instance + Storage + IOPS for RDS (Multi-AZ 2x)
5. **Calculating Savings**: Hourly → Daily → Monthly → Yearly projections

The key differentiator is using **RDS-specific storage pricing** (not EC2 EBS!) and **Multi-AZ storage multiplication** (2x) for accurate RDS cost calculations.
