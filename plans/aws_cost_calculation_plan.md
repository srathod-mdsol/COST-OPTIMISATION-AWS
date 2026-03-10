# AWS Cost Optimization - Comprehensive Cost Calculation Plan

## Executive Summary

This document provides a detailed plan for calculating AWS costs for EC2 and RDS instances. It identifies all parameters that should be considered for accurate cost calculation and identifies gaps in the current application implementation.

---

## Part 1: AWS EC2 Pricing Model - Complete Parameter Analysis

### 1.1 EC2 On-Demand Instance Pricing Parameters

| Parameter | Description | AWS API Field | Current App Status |
|-----------|-------------|---------------|-------------------|
| **Instance Type** | The instance family and size (e.g., t3.micro, m5.large) | `InstanceType` | ✅ Implemented |
| **Region** | AWS region where instance runs | `Placement.AvailabilityZone` (extract region) | ✅ Implemented |
| **Operating System** | Linux, Windows, RHEL, SLES | `Platform` attribute | ✅ Implemented |
| **Tenancy** | Shared, Dedicated, Host | `Placement.Tenancy` | ✅ Implemented |
| **Hourly Price** | Base hourly cost per instance | AWS Pricing API | ✅ Implemented |

### 1.2 EC2 Additional Cost Components

| Cost Component | Description | Pricing Unit | Current App Status |
|----------------|-------------|--------------|-------------------|
| **EBS Storage** | Root volume + additional EBS volumes | $/GB/month | ✅ Partially Implemented |
| **EBS Snapshots** | S3-backed snapshots | $/GB/month | ❌ Not Implemented |
| **Data Transfer IN** | Data transferred into AWS | $/GB | ❌ Not Implemented |
| **Data Transfer OUT** | Data transferred out of AWS | $/GB | ❌ Not Implemented |
| **Public IP Data Transfer** | Data transfer for Elastic IP | $/GB | ❌ Not Implemented |
| **NAT Gateway** | NAT gateway data processing | $/GB | ❌ Not Implemented |
| **NAT Gateway Hourly** | NAT gateway hourly charge | $/hour | ❌ Not Implemented |
| **Elastic Load Balancer** | Application/Network Load Balancer | $/hour + $/LB-hour + $/GB | ❌ Not Implemented |
| **CloudWatch Monitoring** | Detailed monitoring costs | $/metric/month | ❌ Not Implemented |
| **CloudWatch Logs** | Log storage and ingestion | $/GB ingested + $/GB stored | ❌ Not Implemented |
| **VPC Endpoints** | Gateway/Interface endpoints | $/hour + $/GB | ❌ Not Implemented |
| **Direct Connect** | Dedicated network connection | $/port/hour + $/GB | ❌ Not Implemented |
| **Reserved Instance** | Reserved capacity discount | Various terms | ❌ Not Implemented |
| **Savings Plans** | Compute savings plans | Various terms | ❌ Not Implemented |
| **Spot Instance** | Bid-based pricing | Variable | ❌ Not Implemented |
| **Dedicated Host** | Physical host reservation | $/hour | ❌ Not Implemented |

### 1.3 EC2 Cost Calculation Formulas

```python
# Hourly Cost
EC2_hourly = instance_hourly_price

# Daily Cost  
EC2_daily = EC2_hourly * 24

# Monthly Cost
EC2_monthly = EC2_hourly * 730  # 730 hours = average billing month

# Yearly Cost
EC2_yearly = EC2_monthly * 12
```

### 1.4 EBS Volume Cost Formulas

```python
# Monthly Storage Cost
EBS_storage_monthly = size_gb * price_per_gb_month

# Provisioned IOPS Cost (io1, io2)
EBS_iops_monthly = iops_count * price_per_iops_month

# gp3 Throughput Cost (if exceeding base)
EBS_throughput_excess_mbps = max(0, throughput_mbps - 125)  # 125 MB/s base
EBS_throughput_cost = EBS_throughput_excess_mbps * price_per_mbps_month

# Total EBS Monthly
EBS_monthly = EBS_storage_monthly + EBS_iops_monthly + EBS_throughput_cost
```

---

## Part 2: AWS RDS Pricing Model - Complete Parameter Analysis

### 2.1 RDS Instance Pricing Parameters

| Parameter | Description | AWS API Field | Current App Status |
|-----------|-------------|---------------|-------------------|
| **Instance Class** | DB instance family (db.t3.micro, db.m5.large) | `DBInstanceClass` | ✅ Implemented |
| **Region** | AWS region | `AvailabilityZone` (extract region) | ✅ Implemented |
| **Database Engine** | MySQL, PostgreSQL, Oracle, SQL Server, MariaDB, Aurora | `Engine` | ✅ Implemented |
| **Engine Version** | Specific version | `EngineVersion` | ⚠️ Collected but not used for pricing |
| **Deployment Option** | Single-AZ or Multi-AZ | `MultiAZ` boolean | ✅ Implemented |
| **License Model** | Included or BYOL | `LicenseModel` | ✅ Implemented |
| **Multi-AZ Standby** | Secondary standby instance cost | N/A (derived from MultiAZ) | ❌ **MISSING** |
| **Hourly Price** | Base hourly instance cost | AWS Pricing API | ✅ Implemented |

### 2.2 RDS Storage Pricing Parameters

| Parameter | Description | AWS API Field | Current App Status |
|-----------|-------------|---------------|-------------------|
| **Allocated Storage** | Storage in GB | `AllocatedStorage` | ✅ Implemented |
| **Storage Type** | gp2, gp3, io1, io2, magnetic | `StorageType` | ✅ Implemented |
| **IOPS** | Provisioned IOPS (io1, io2, gp3) | `Iops` | ✅ Implemented |
| **Throughput** | Throughput for gp3 | `StorageThroughput` | ⚠️ Collected but not used |
| **Storage Price** | Per GB/month by type/region | AWS RDS Storage Pricing | ⚠️ **WRONG CALCULATION** |
| **Backup Storage** | Automated backup storage | N/A | ❌ Not Implemented |
| **Snapshot Storage** | Manual snapshots | N/A | ❌ Not Implemented |
| **Data Transfer** | Data transfer in/out | N/A | ❌ Not Implemented |

### 2.3 RDS Additional Cost Components

| Cost Component | Description | Pricing Unit | Current App Status |
|----------------|-------------|--------------|-------------------|
| **Performance Insights** | Enhanced monitoring | $/vCPU/hour | ❌ Not Implemented |
| **Enhanced Monitoring** | CloudWatch detailed metrics | $/hour + $/GB | ❌ Not Implemented |
| **RDS Proxy** | Connection pooling | $/hour + $/hour per connection | ❌ Not Implemented |
| **Aurora Serverless** | On-demand scaling | ACU-hour | ❌ Not Implemented |
| **Aurora Global Database** | Cross-region replication | $/GB write + $/GB read | ❌ Not Implemented |
| **RDS Blue/Green Deployments** | Managed deployments | Included | ❌ Not Implemented |
| **Backtrack** | Point-in-time recovery | $/instance/hour | ❌ Not Implemented |
| **Log Exports** | CloudWatch log exports | $/GB | ❌ Not Implemented |

### 2.4 RDS Cost Calculation Formulas (Current vs Correct)

#### Current Application (INCORRECT):
```python
# This is WRONG - uses EC2 EBS pricing instead of RDS storage!
RDS_storage_monthly = calculate_ebs_cost(allocated_storage, storage_type, iops, region)
# Missing: Multi-AZ storage cost (Multi-AZ requires 2x storage!)
```

#### Correct RDS Calculation:
```python
# Instance Hourly Cost
RDS_instance_hourly = instance_hourly_price  # Already includes Multi-AZ for instance itself

# Storage Cost - DIFFERENT from EC2 EBS!
storage_price_per_gb = get_rds_storage_price(storage_type, region)  # RDS-specific pricing
storage_multiplier = 2.0 if multi_az else 1.0  # Multi-AZ requires 2x storage

# Monthly Storage Cost
RDS_storage_monthly = allocated_storage * storage_price_per_gb * storage_multiplier

# Provisioned IOPS Cost (RDS-specific)
if storage_type in ['io1', 'io2']:
    rds_iops_price = get_rds_iops_price(storage_type, region)  # Different from EBS!
    RDS_iops_monthly = iops * rds_iops_price
else:
    RDS_iops_monthly = 0

# Total RDS Monthly
RDS_monthly = (RDS_instance_hourly * 730) + RDS_storage_monthly + RDS_iops_monthly

# Breakdown
RDS_hourly = RDS_instance_hourly + (RDS_storage_monthly / 730) + (RDS_iops_monthly / 730)
RDS_daily = RDS_hourly * 24
RDS_yearly = RDS_monthly * 12
```

---

## Part 3: Gaps Analysis - What's Missing in Current Application

### 3.1 Critical Gaps (High Priority)

| Gap | Impact | Location | Fix Required |
|-----|--------|----------|--------------|
| **RDS Storage Pricing** | Uses EC2 EBS pricing instead of RDS-specific storage pricing | `CostCalculator.calculate_ebs_cost()` | Create separate RDS storage calculator |
| **Multi-AZ Storage** | Doesn't account for 2x storage in Multi-AZ | `cost_calculator.py` | Multiply storage by 2x for Multi-AZ |
| **RDS IOPS Pricing** | Uses EC2 IOPS pricing instead of RDS-specific | `ebs_pricing_loader.py` | Add RDS-specific IOPS pricing |
| **Reserved Instance Pricing** | Only calculates On-Demand | All cost calculators | Add Reserved Instance lookup |
| **Savings Plans** | Not considered | All cost calculators | Add Savings Plans pricing |
| **Spot Instance Pricing** | Not considered | All cost calculators | Add Spot pricing lookup |

### 3.2 Medium Priority Gaps

| Gap | Impact | Location | Fix Required |
|-----|--------|----------|--------------|
| **EBS Snapshot Costs** | Not calculated | `cost_calculator.py` | Add snapshot storage calculation |
| **Data Transfer Costs** | Not calculated | `cost_calculator.py` | Add data transfer pricing |
| **ELB Costs** | Not calculated | `cost_calculator.py` | Add load balancer pricing |
| **NAT Gateway Costs** | Not calculated | `cost_calculator.py` | Add NAT gateway pricing |
| **CloudWatch Costs** | Not calculated | `cost_calculator.py` | Add CloudWatch pricing |
| **EBS Throughput (gp3)** | Not fully calculated | `ebs_pricing_loader.py` | Add throughput excess calculation |

### 3.3 Lower Priority Gaps

| Gap | Impact | Fix Required |
|-----|--------|--------------|
| **Reserved Instance Coverage** | No visibility into RI coverage | Add RI metadata storage |
| **Savings Plans Coverage** | No visibility into SP coverage | Add SP metadata storage |
| **Cost Explorer Integration** | No actual AWS Cost Explorer data | Could integrate with Cost API |
| **Budget Alerts** | No budget tracking | Add budget configuration |
| **Cost Anomaly Detection** | No anomaly detection | Add anomaly monitoring |

---

## Part 4: Implementation Plan - Detailed Task List

### 4.1 Phase 1: Fix Critical RDS Issues

```
[ ] Task 1: Create RDS-specific storage pricing loader
    - File: etl/rds_storage_pricing_loader.py (new)
    - Add method: get_rds_storage_price(volume_type, region)
    - Add method: get_rds_iops_price(volume_type, region)
    - RDS storage prices differ from EC2 EBS!

[ ] Task 2: Update CostCalculator for RDS storage
    - File: analysis/cost_calculator.py
    - Add method: calculate_rds_storage_cost()
    - Fix: Use RDS-specific pricing instead of EBS
    - Fix: Multiply by 2x for Multi-AZ deployments

[ ] Task 3: Update RDS cost calculation to include:
    - Storage: allocated_storage * price_per_gb * (2 if Multi-AZ else 1)
    - IOPS: iops * price_per_iops (RDS-specific rates)
    - Throughput: for gp3 exceeding baseline
    - Multi-AZ instance cost (already included in instance price)
```

### 4.2 Phase 2: Add Comprehensive Cost Components

```
[ ] Task 4: Add EBS Snapshot Cost Calculation
    - File: analysis/cost_calculator.py
    - Add method: calculate_snapshot_cost(snapshot_size_gb)
    - Need: Snapshot size from AWS API

[ ] Task 5: Add Data Transfer Cost Calculation
    - File: analysis/cost_calculator.py
    - Add method: calculate_data_transfer_cost(gb_in, gb_out, region)
    - Need: CloudWatch data transfer metrics

[ ] Task 6: Add Load Balancer Cost Calculation
    - File: analysis/cost_calculator.py
    - Add method: calculate_elb_cost(lb_type, hours, gb_processed, connections)
    - Need: LB type, hours active, data processed

[ ] Task 7: Add NAT Gateway Cost Calculation
    - File: analysis/cost_calculator.py
    - Add method: calculate_nat_gateway_cost(hours, gb_processed)
    - Need: NAT gateway data from VPC
```

### 4.3 Phase 3: Add Reserved Instance & Savings Plans

```
[ ] Task 8: Add Reserved Instance Pricing Lookup
    - File: etl/pricing_loader.py
    - Extend: Load Reserved Instance pricing from JSON
    - Add: ri_term (1-year, 3-year), payment_option (All Upfront, Partial, No Upfront)

[ ] Task 9: Add Savings Plans Support
    - File: etl/pricing_loader.py
    - Extend: Load Savings Plans pricing
    - Add: sp_type (EC2 SP, Compute SP), commitment

[ ] Task 10: Update CostCalculator for RI/SP
    - File: analysis/cost_calculator.py
    - Add method: calculate_ri_savings(on_demand_hourly, ri_term, payment_option)
    - Add method: calculate_sp_savings(on_demand_hourly, sp_type, commitment)
```

### 4.4 Phase 4: Enhance Time-Based Calculations

```
[ ] Task 11: Add Actual Runtime-Based Calculations
    - Current: Uses 730 hours/month (fixed)
    - Fix: Use actual instance runtime from CloudWatch
    - Add: get_actual_runtime_hours(instance_id) from metrics
    - Formula: actual_hourly * actual_hours instead of 730

[ ] Task 12: Add Daily Breakdown
    - Current: monthly / 30 (approximate)
    - Fix: Use actual days in month (28-31)
    - Add: DAYS_PER_MONTH dynamic calculation

[ ] Task 13: Add Yearly Breakdown with Leap Year
    - Current: monthly * 12 (assumes 365 days)
    - Fix: Account for 365 or 366 days
    - Add: Actual days calculation
```

### 4.5 Phase 5: Database Schema Updates

```
[ ] Task 14: Extend aws_pricing table
    - Add columns: ri_price_1yr_all_upfront, ri_price_1yr_partial, 
                    ri_price_3yr_all_upfront, ri_price_3yr_partial,
                    sp_price_ec2, sp_price_compute

[ ] Task 15: Extend raw_instances table for cost tracking
    - Add: actual_runtime_hours, last_cost_calculation, cost_breakdown_json
    - Add: ri_coverage_percentage, sp_coverage_percentage
```

---

## Part 5: Complete Parameter Checklist

### 5.1 Parameters to Collect from AWS API

```python
# EC2 Instance Parameters
ec2_params = {
    'instance_id': 'i-xxxxx',
    'instance_type': 't3.micro',
    'region': 'us-east-1',
    'availability_zone': 'us-east-1a',
    'platform': 'Linux/UNIX',  # or Windows, RHEL, SLES
    'tenancy': 'shared',  # or dedicated, host
    'state': 'running',
    'launch_time': datetime,
    # EBS Volumes
    'block_device_mappings': [
        {'ebs': {'volume_id': 'vol-xxx', 'size': 8, 'type': 'gp3'}}
    ],
    # Network
    'vpc_id': 'vpc-xxx',
    'subnet_id': 'subnet-xxx',
    'private_ip_address': '10.0.0.1',
    'public_ip_address': '54.1.2.3',
    # Tags
    'tags': {'Environment': 'prod', 'Name': 'web-server'}
}

# RDS Instance Parameters
rds_params = {
    'db_instance_identifier': 'mydb',
    'db_instance_class': 'db.t3.micro',
    'engine': 'postgres',  # mysql, postgres, oracle, sqlserver, mariadb, aurora
    'engine_version': '14.7',
    'allocated_storage': 100,  # GB
    'storage_type': 'gp3',  # gp2, gp3, io1, io2, magnetic
    'iops': 3000,
    'storage_throughput': 125,  # MB/s for gp3
    'multi_az': True,
    'license_model': 'license-included',  # or bring-your-own-license
    'availability_zone': 'us-east-1a',
    'endpoint': {'Address': 'xxx.rds.amazonaws.com'},
    'backup_retention_period': 7,
    'db_name': 'mydb'
}

# EBS Volume Parameters (for attached volumes)
ebs_params = {
    'volume_id': 'vol-xxxxx',
    'size': 100,  # GB
    'volume_type': 'gp3',  # gp2, gp3, io1, io2, st1, sc1, standard
    'iops': 3000,
    'throughput': 125,  # MB/s for gp3
    'encrypted': True,
    'attachment': {'InstanceId': 'i-xxx', 'Device': '/dev/sda1'}
}
```

### 5.2 Parameters to Load from Pricing API

```python
# EC2 Pricing
ec2_pricing_params = {
    'instance_type': 't3.micro',
    'region': 'us-east-1',
    'operating_system': 'Linux',  # Windows, RHEL, SLES
    'tenancy': 'shared',  # dedicated, host
    'price_per_hour': 0.0104,
    'currency': 'USD',
    # Reserved Instance Prices (new columns)
    'ri_1yr_partial': 0.0075,
    'ri_1yr_all_upfront': 0.0062,
    'ri_3yr_partial': 0.0045,
    'ri_3yr_all_upfront': 0.0031
}

# RDS Pricing
rds_pricing_params = {
    'instance_type': 'db.t3.micro',
    'region': 'us-east-1',
    'database_engine': 'postgres',
    'deployment_option': 'Single-AZ',  # or Multi-AZ
    'license_model': 'included',
    'price_per_hour': 0.017,  # Instance only
    # RDS Storage Pricing (different from EC2!)
    'storage_price_per_gb': {
        'gp3': 0.10,
        'gp2': 0.115,
        'io1': 0.125,
        'io2': 0.125,
        'magnetic': 0.02
    },
    # RDS IOPS Pricing (different from EC2!)
    'iops_price_per_iops': 0.065
}
```

---

## Part 6: AWS Pricing API Parameters (from AWS Documentation)

### 6.1 EC2 Pricing API Filters

```python
# EC2 On-Demand Pricing
ec2_filters = [
    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": "t3.micro"},
    {"Type": "TERM_MATCH", "Field": "location", "Value": "US East (N. Virginia)"},
    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
    {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
    {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Compute Instance"}
]
```

### 6.2 RDS Pricing API Filters

```python
# RDS On-Demand Pricing
rds_filters = [
    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": "db.t3.micro"},
    {"Type": "TERM_MATCH", "Field": "location", "Value": "US East (N. Virginia)"},
    {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": "PostgreSQL"},
    {"Type": "TERM_MATCH", "Field": "deploymentOption", "Value": "Single-AZ"},
    {"Type": "TERM_MATCH", "Field": "licenseModel", "Value": "license-included"},
    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Database Instance"}
]

# RDS Storage Pricing
rds_storage_filters = [
    {"Type": "TERM_MATCH", "Field": "volumeType", "Value": "General Purpose (SSD)"},
    {"Type": "TERM_MATCH", "Field": "location", "Value": "US East (N. Virginia)"},
    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Database Storage"}
]
```

---

## Part 7: Summary of Required Changes

### 7.1 Files to Create

| File | Purpose |
|------|---------|
| `etl/rds_storage_pricing_loader.py` | RDS-specific storage pricing (different from EBS!) |
| `etl/reserved_instance_pricing_loader.py` | Reserved Instance pricing |
| `etl/savings_plans_pricing_loader.py` | Savings Plans pricing |
| `analysis/data_transfer_calculator.py` | Data transfer costs |
| `analysis/elb_cost_calculator.py` | Load balancer costs |
| `analysis/nat_gateway_calculator.py` | NAT Gateway costs |

### 7.2 Files to Modify

| File | Changes |
|------|---------|
| `analysis/cost_calculator.py` | Complete rewrite of RDS calculation, add all missing components |
| `etl/pricing_loader.py` | Add RI and SP pricing columns |
| `etl/data_provider.py` | Add pricing lookup for new types |
| `database/models.py` | Add new columns for cost tracking |
| `core/constants.py` | Add new cost constants |

### 7.3 Key Formulas Summary

```python
# Complete Cost Calculation (Target State)

# EC2 Monthly Cost
ec2_monthly = (instance_price * hours) + ebs_storage + ebs_iops + ebs_throughput + snapshots + data_transfer

# RDS Monthly Cost  
rds_monthly = (instance_price * hours) + rds_storage + rds_iops + backup_storage + data_transfer + performance_insights

# Where:
# - hours: actual runtime hours (not fixed 730!)
# - rds_storage: allocated_storage * rds_price * (2 if multi_az else 1)  # CRITICAL: RDS storage != EC2 EBS!
# - rds_iops: iops * rds_iops_price (different rates from EC2!)
```

---

## Part 8: Hardcoded Values to Remove

The following hardcoded values need to be replaced with dynamic calculations:

| Location | Current Hardcoded Value | Should Be |
|----------|------------------------|-----------|
| `core/constants.py:13` | `HOURS_PER_MONTH = 730` | Dynamic based on actual billing |
| `core/constants.py:106` | `DEFAULT_EBS_STORAGE_COST = 0.10` | Dynamic per volume type/region |
| `core/constants.py:107` | `DEFAULT_RDS_STORAGE_COST = 0.115` | Dynamic per RDS storage type/region |
| `analysis/cost_calculator.py:26` | `monthly = hourly_price * HOURS_PER_MONTH` | `hourly * actual_hours` |
| `analysis/cost_calculator.py:169` | `daily_cost = monthly / 30` | Dynamic days |
| Multiple locations | Hardcoded region fallback | Use actual instance region |

---

## Conclusion

The current application has a good foundation for basic EC2 and RDS cost calculation, but has significant gaps, particularly:

1. **Critical**: RDS storage pricing is using EC2 EBS pricing (WRONG!)
2. **Critical**: Multi-AZ storage not doubled for RDS
3. **Missing**: Reserved Instance and Savings Plans support
4. **Missing**: Data transfer, ELB, NAT Gateway, CloudWatch costs
5. **Hardcoded**: Fixed hours (730) instead of actual runtime

This plan provides a comprehensive roadmap to address all gaps and achieve accurate AWS cost calculation.
