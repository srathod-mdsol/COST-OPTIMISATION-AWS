# Comprehensive Cost Breakdown Plan

## Executive Summary

This document outlines the implementation plan for providing comprehensive, itemized cost breakdowns for AWS resources (EC2, RDS, EBS). The goal is to show transparent calculations with all expense components clearly displayed.

---

## Current State Analysis

### Existing Cost Calculation Components

| Resource Type | Current Breakdown | Location |
|--------------|-------------------|----------|
| **EC2** | Instance hourly/monthly, attached EBS costs | `analysis/cost_calculator.py:122-196` |
| **RDS** | Instance hourly/monthly, storage, Multi-AZ | `analysis/cost_calculator.py:15-120` |
| **EBS** | Volume storage cost, IOPS cost | `analysis/cost_calculator.py:260-299` |
| **EBS Snapshots** | Snapshot storage | `analysis/cost_calculator.py:481-515` |
| **ELB** | Base cost, data processing, connections | `analysis/cost_calculator.py:570-631` |
| **NAT Gateway** | Hourly + data processing | `analysis/cost_calculator.py:633-690` |
| **Data Transfer** | Transfer in/out costs | `analysis/cost_calculator.py:517-568` |

### Current Data Sources

- **Pricing**: AWS Pricing API via `etl/pricing_loader.py`
- **EBS Pricing**: `etl/ebs_pricing_loader.py` 
- **RDS Storage**: `etl/rds_storage_pricing_loader.py`
- **Cost Display**: `ui/dashboard.py` (lines 1095-1200)

---

## Target Cost Breakdown Structure

### EC2 Instance Cost Breakdown

| Component | Description | Source |
|-----------|-------------|--------|
| Instance Type | EC2 instance type (e.g., t3.medium) | AWS API |
| Unit Price | Price per hour | AWS API |
| Operating System | Linux/Windows | AWS API |
| Tenancy | Shared/Dedicated | AWS API |
| Region | AWS region | Config |
| Hours Used | Actual runtime hours | CloudWatch |
| Compute Cost | Unit Price × Hours | Calculated |
| Attached EBS | List of attached volumes | AWS API |
| EBS Storage Cost | Per volume storage | EBS Pricing API |
| EBS IOPS Cost | Provisioned IOPS cost | EBS Pricing API |
| Snapshot Cost | Snapshot storage | S3 Pricing |
| Data Transfer | IN/OUT transfer | AWS API |

### RDS Instance Cost Breakdown

| Component | Description | Source |
|-----------|-------------|--------|
| Instance Type | DB instance class | AWS API |
| Database Engine | PostgreSQL/MySQL/Oracle | AWS API |
| License Model | Included/BYOL | AWS API |
| Deployment | Single-AZ/Multi-AZ | AWS API |
| Unit Price | Price per hour | AWS API |
| Storage Type | gp3/gp2/io1/io2 | AWS API |
| Allocated Storage | GB allocated | AWS API |
| Multi-AZ Factor | 2x for Multi-AZ | AWS API |
| Effective Storage | Allocated × Multi-AZ | Calculated |
| Storage Rate | $/GB/month | RDS Storage API |
| IOPS Rate | $/IOPS/month | RDS Storage API |
| Backup Storage | Backup retention | AWS API |
| I/O Requests | Read/Write requests | CloudWatch |

### EBS Volume Cost Breakdown

| Component | Description | Source |
|-----------|-------------|--------|
| Volume Type | gp3/gp2/io1/io2/st1/sc1 | AWS API |
| Size | Volume size in GB | AWS API |
| Base IOPS | Included IOPS (gp3: 3000) | AWS API |
| Provisioned IOPS | User-specified IOPS | AWS API |
| Extra IOPS | Provisioned - Base | Calculated |
| IOPS Rate | $/IOPS/month | EBS Pricing API |
| Base Throughput | Included throughput | AWS API |
| Provisioned Throughput | User-specified | AWS API |
| Storage Rate | $/GB/month | EBS Pricing API |
| Storage Cost | Size × Rate | Calculated |
| IOPS Cost | Extra IOPS × Rate | Calculated |
| Throughput Cost | Extra throughput × Rate | Calculated |
| Total Monthly | Sum of all costs | Calculated |

---

## Implementation Requirements

### 1. EC2 Instance Detailed Breakdown

**File to Modify**: `analysis/cost_calculator.py`

**Add new method**: `calculate_ec2_detailed_breakdown()`

### 2. RDS Instance Detailed Breakdown

**File to Modify**: `analysis/cost_calculator.py`

**Enhance existing method**: `calculate_rds_savings()`

### 3. EBS Volume Detailed Breakdown

**File to Modify**: `analysis/cost_calculator.py`

**Enhance existing method**: `calculate_ebs_cost()`

### 4. Dashboard Display Enhancement

**File to Modify**: `ui/dashboard.py`

Add new expandable sections for itemized breakdowns.

---

## Files to Modify

| Priority | File | Changes |
|----------|------|---------|
| 1 | `analysis/cost_calculator.py` | Add detailed breakdown methods |
| 2 | `etl/ebs_pricing_loader.py` | Add throughput pricing |
| 3 | `etl/rds_storage_pricing_loader.py` | Add I/O request pricing |
| 4 | `ui/dashboard.py` | Display itemized breakdowns |
| 5 | `core/constants.py` | Add new cost constants |

---

## Missing Pricing Components

The following AWS pricing components are not currently implemented:

1. **EBS Throughput** - gp3 provisioned throughput pricing
2. **RDS I/O Requests** - RDS storage I/O request pricing  
3. **RDS Backup Storage** - Automated backup retention pricing
4. **Data Transfer** - Cross-region/data transfer out pricing
5. **Reserved Instance Pricing** - RI pricing breakdown
6. **Savings Plans** - Compute savings plans pricing
7. **Taxes & Fees** - Regional tax calculations (not typically in AWS pricing)
8. **License Costs** - BYOL license tracking

---

## Implementation Roadmap

### Phase 1: Core Cost Breakdown
- [ ] Enhance EC2 cost calculation with itemized breakdown
- [ ] Enhance RDS cost calculation with storage/IOPS breakdown
- [ ] Enhance EBS cost calculation with IOPS/throughput breakdown

### Phase 2: Dashboard Display
- [ ] Add itemized cost display in EC2 detail view
- [ ] Add itemized cost display in RDS detail view
- [ ] Add itemized cost display in EBS detail view

### Phase 3: Additional Components
- [ ] Add backup storage cost calculation
- [ ] Add data transfer cost calculation
- [ ] Add Reserved Instance comparison

---

## Output Format Example

### EC2 Instance
```
EC2 Instance: i-0abc123def456789a (web-server-01)
------------------------------------------
COMPUTE COSTS
  Instance Type: t3.medium
  Unit Price: $0.0416/hour
  Hours (730 hrs/mo): 730
  Compute Subtotal: $30.37/month

STORAGE COSTS (EBS)
  Volume: vol-0abc123 (Root)
    Type: gp3
    Size: 30 GB
    Rate: $0.08/GB/mo
    Cost: $2.40/month
  Volume: vol-0def456 (Data)
    Type: gp3
    Size: 100 GB
    Rate: $0.08/GB/mo
    Cost: $8.00/month
  Storage Subtotal: $10.40/month

DATA TRANSFER
  Transfer Out: 5 GB
  Rate: $0.09/GB
  Transfer Cost: $0.45/month

TOTAL MONTHLY COST: $41.22/month
TOTAL ANNUAL COST: $494.64/year
```

### RDS Instance
```
RDS Instance: db-rds-01 (prod-database)
----------------------------------------
COMPUTE COSTS
  Instance: db.r5.large
  Engine: PostgreSQL 14.5
  Multi-AZ: Yes
  Unit Price: $0.29/hour
  Hours: 730
  Compute Subtotal: $211.70/month

STORAGE COSTS
  Storage Type: gp3
  Allocated: 500 GB
  Multi-AZ Factor: 2x (replica)
  Effective Storage: 1000 GB
  Rate: $0.08/GB/mo
  Storage Subtotal: $80.00/month

IOPS COSTS
  Provisioned: 3000 IOPS
  Base Included: 3000 IOPS
  Extra IOPS: 0
  IOPS Cost: $0.00/month

BACKUP STORAGE
  Retention: 7 days
  Backup Size: 50 GB
  Rate: $0.023/GB/mo
  Backup Cost: $1.15/month

TOTAL MONTHLY COST: $292.85/month
TOTAL ANNUAL COST: $3,514.20/year
```

---

## Next Steps

1. **Approve this plan** - Confirm the scope matches requirements
2. **Switch to Code mode** - Begin implementing the cost breakdown methods
3. **Test with sample data** - Verify calculations match AWS console
4. **Deploy to dashboard** - Update UI to show itemized breakdowns
