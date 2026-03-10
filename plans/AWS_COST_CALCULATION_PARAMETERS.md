# AWS EC2 and RDS Complete Cost Calculation Parameters

## 1. AWS EC2 Pricing Model - All API Parameters

### 1.1 EC2 Instance Parameters (from DescribeInstances API)

| Parameter | API Field | Description | Used for Pricing | Current Implementation |
|-----------|-----------|-------------|-------------------|----------------------|
| InstanceType | InstanceType | Instance family and size | ✅ YES | ✅ Implemented |
| InstanceId | InstanceId | Unique instance ID | ❌ NO | Collected |
| Region | Placement.AvailabilityZone | Region code | ✅ YES | ✅ Implemented |
| Platform | Platform | Linux/Windows/RHEL/SLES | ✅ YES | ✅ Implemented |
| Tenancy | Placement.Tenancy | shared/dedicated/host | ✅ YES | ✅ Implemented |
| State | State.Name | running/stopped/terminated | ✅ YES | Only running charged |
| LaunchTime | LaunchTime | Instance launch time | ❌ NO | Collected |
| ImageId | ImageId | AMI ID | ❌ NO | Not for pricing |
| Architecture | Architecture | x86_64/arm64 | ❌ NO | Included in type |
| VirtualizationType | VirtualizationType | hvm/paravirtual | ❌ NO | Included in type |
| RootDeviceName | RootDeviceName | Root device name | ❌ NO | Included in type |
| RootDeviceType | RootDeviceType | ebs/instance-store | ❌ NO | Not for On-Demand |
| Tags | Tags | User-defined tags | ❌ NO | For filtering only |

### 1.2 EC2 Instance Pricing (from AWS Pricing API)

| Parameter | API Filter Field | Description | Current Implementation |
|-----------|-----------------|-------------|----------------------|
| instanceType | instanceType | t3.micro, m5.large, etc. | ✅ Implemented |
| location | location | US East (N. Virginia), etc. | ✅ Implemented |
| operatingSystem | operatingSystem | Linux, Windows, RHEL, SLES | ✅ Implemented |
| tenancy | tenancy | Shared, Dedicated, Host | ✅ Implemented |
| preInstalledSw | preInstalledSw | NA, SQL Server, etc. | ✅ Implemented |
| productFamily | productFamily | Compute Instance | ✅ Implemented |
| pricePerUnit | pricePerUnit | USD per hour | ✅ Implemented |
| unit | unit | Hours | ✅ Implemented |

### 1.3 EC2 Additional Pricing (Reserved Instances)

| Parameter | Filter Field | Description | Current Implementation |
|-----------|-------------|-------------|----------------------|
| offeringType | offeringType | Partial Upfront, All Upfront, No Upfront | ❌ NOT Implemented |
| leaseContractLength | leaseContractLength | 1year, 3year | ❌ NOT Implemented |
| purchaseOption | purchaseOption | Life Cycle (Public/Convertible) | ❌ NOT Implemented |

### 1.4 EC2 EBS Volume Parameters (from DescribeVolumes API)

| Parameter | API Field | Description | Used for Pricing | Current Implementation |
|-----------|-----------|-------------|-------------------|----------------------|
| VolumeId | VolumeId | Unique volume ID | Collected | ❌ NO |
| Size | Size | Size in GiB | ✅ YES | ✅ Implemented |
| VolumeType | VolumeType | gp2/gp3/io1/io2/st1/sc1/standard | ✅ YES | ✅ Implemented |
| Iops | Iops | Provisioned IOPS | ✅ YES | ✅ Implemented |
| Throughput | Throughput | MiB/s (gp3 only) | ✅ YES | ✅ Implemented |
| CreateTime | CreateTime | Creation time | ❌ NO | Not for pricing |
| AvailabilityZone | AvailabilityZone | AZ name | ✅ YES | ✅ Implemented |
| Encrypted | Encrypted | Encryption status | ❌ NO | Not for pricing |
| SnapshotId | SnapshotId | Source snapshot | ❌ NO | Not for pricing |

### 1.5 EBS Snapshot Parameters (from DescribeSnapshots API)

| Parameter | API Field | Description | Current Implementation |
|-----------|-----------|-------------|----------------------|
| SnapshotId | SnapshotId | Unique snapshot ID | ❌ NOT Implemented |
| VolumeSize | VolumeSize | Size in GiB | ❌ NOT Implemented |
| StartTime | StartTime | Creation time | ❌ NOT Implemented |
| OwnerId | OwnerId | Account ID | ❌ NOT Implemented |
| StorageTier | StorageTier | standard/archive | ❌ NOT Implemented |

### 1.6 EC2 Network Parameters (from CloudWatch)

| Parameter | API Field | Description | Current Implementation |
|-----------|-----------|-------------|----------------------|
| NetworkIn | NetworkIn | Bytes received | ❌ NOT Implemented |
| NetworkOut | NetworkOut | Bytes sent | ❌ NOT Implemented |
| NetworkPacketsIn | NetworkPacketsIn | Packets received | ❌ NOT Implemented |
| NetworkPacketsOut | NetworkPacketsOut | Packets sent | ❌ NOT Implemented |

---

## 2. AWS RDS Pricing Model - All API Parameters

### 2.1 RDS Instance Parameters (from DescribeDBInstances API)

| Parameter | API Field | Description | Used for Pricing | Current Implementation |
|-----------|-----------|-------------|-------------------|----------------------|
| DBInstanceIdentifier | DBInstanceIdentifier | Instance ID | ❌ NO | Collected |
| DBInstanceClass | DBInstanceClass | db.t3.micro, db.m5.large | ✅ YES | ✅ Implemented |
| Engine | Engine | postgres/mysql/oracle/sqlserver/mariadb/aurora | ✅ YES | ✅ Implemented |
| EngineVersion | EngineVersion | Version number | ⚠️ PARTIAL | Collected, not used |
| DBInstanceStatus | DBInstanceStatus | available/stopped | ✅ YES | Only running charged |
| MasterUsername | MasterUsername | Admin username | ❌ NO | Not for pricing |
| DBName | DBName | Database name | ❌ NO | Not for pricing |
| AllocatedStorage | AllocatedStorage | Storage in GB | ✅ YES | ✅ Implemented |
| StorageType | StorageType | gp2/gp3/io1/io2/magnetic | ✅ YES | ✅ Implemented |
| Iops | Iops | Provisioned IOPS | ✅ YES | ✅ Implemented |
| StorageThroughput | StorageThroughput | MB/s (gp3) | ✅ YES | ⚠️ Partially |
| MultiAZ | MultiAZ | Multi-AZ deployment | ✅ YES | ✅ Implemented |
| AvailabilityZone | AvailabilityZone | Primary AZ | ✅ YES | ✅ Implemented |
| DBSubnetGroup | DBSubnetGroup | Subnet configuration | ❌ NO | Not for pricing |
| PubliclyAccessible | PubliclyAccessible | Public access | ❌ NO | Not for pricing |
| Endpoint | Endpoint | Connection endpoint | ❌ NO | Not for pricing |
| ReadReplicaSourceDBInstanceIdentifier | ReadReplicaSourceDBInstanceIdentifier | Source for read replica | ❌ NO | Not for pricing |
| LicenseModel | LicenseModel | license-included/bring-your-own-license | ✅ YES | ✅ Implemented |
| BackupRetentionPeriod | BackupRetentionPeriod | Days to retain | ❌ NO | Not for pricing |
| DBParameterGroups | DBParameterGroups | Parameter groups | ❌ NO | Not for pricing |
| Tags | Tags | User-defined tags | ❌ NO | For filtering only |

### 2.2 RDS Pricing API Parameters (from AmazonRDS Pricing)

| Parameter | Filter Field | Description | Current Implementation |
|-----------|-------------|-------------|----------------------|
| instanceType | instanceType | db.t3.micro, etc. | ✅ Implemented |
| location | location | Region name | ✅ Implemented |
| databaseEngine | databaseEngine | PostgreSQL, MySQL, etc. | ✅ Implemented |
| deploymentOption | deploymentOption | Single-AZ, Multi-AZ | ✅ Implemented |
| licenseModel | licenseModel | Included, BYOL | ✅ Implemented |
| productFamily | productFamily | Database Instance | ✅ Implemented |

### 2.3 RDS Storage Pricing (CRITICAL - Different from EC2!)

| Parameter | Filter Field | Description | Current Implementation |
|-----------|-------------|-------------|----------------------|
| volumeType | volumeType | gp3/gp2/io1/io2/magnetic | ✅ NOW Implemented |
| location | location | Region | ✅ NOW Implemented |
| productFamily | productFamily | Database Storage | ✅ NOW Implemented |

**IMPORTANT**: RDS storage pricing is DIFFERENT from EC2 EBS pricing:
- RDS gp2: $0.115/GB/month (vs EC2 gp2: $0.10)
- RDS io1: $0.15/GB/month + $0.10/IOPS (vs EC2 io1: $0.125 + $0.065)
- Multi-AZ requires 2x storage!

### 2.4 RDS Additional Cost Components

| Component | API/Source | Description | Current Implementation |
|-----------|------------|-------------|----------------------|
| Backup Storage | DescribeDBInstanceAttributes | Automated backups | ❌ NOT Implemented |
| Manual Snapshots | DescribeDBSnapshots | User snapshots | ❌ NOT Implemented |
| Data Transfer | CloudWatch | In/Out transfer | ❌ NOT Implemented |
| Performance Insights | DescribeDBInstanceParameters | Enhanced monitoring | ❌ NOT Implemented |
| Enhanced Monitoring | CloudWatch | Detailed metrics | ❌ NOT Implemented |
| RDS Proxy | DescribeDBProxies | Connection pooling | ❌ NOT Implemented |
| Aurora Serverless | DescribeDBClusters | Serverless clusters | ❌ NOT Implemented |

---

## 3. Cost Calculation Formulas

### 3.1 EC2 Cost Formulas

```
Hourly Cost = InstancePricePerHour

Daily Cost = HourlyCost × 24

Monthly Cost = HourlyCost × HoursInMonth
             Where HoursInMonth = 730 (or actual runtime)

Yearly Cost = MonthlyCost × 12

Total EC2 Cost = InstanceCost + EBSStorageCost + EBSSnapshotCost + DataTransferCost
```

### 3.2 RDS Cost Formulas

```
Hourly Cost (Instance) = InstancePricePerHour

Storage Cost = AllocatedStorageGB × PricePerGB × MultiAZMultiplier
             Where MultiAZMultiplier = 2 if MultiAZ=true, else 1
             ** CRITICAL: Use RDS storage prices, NOT EBS prices! **

IOPS Cost = ProvisionedIOPS × PricePerIOPS
          (Only for io1, io2, or excess gp3)

Monthly Cost (Instance) = InstancePricePerHour × HoursInMonth
Monthly Cost (Storage) = StorageCost + IOPSCost

Total RDS Cost = InstanceCost + StorageCost + IOPSCost + BackupStorage + DataTransfer
```

---

## 4. Time Period Calculations

### 4.1 Hours per Period

| Period | Hours | Notes |
|--------|-------|-------|
| Hourly | 1 | Base unit |
| Daily | 24 | Hourly × 24 |
| Monthly | 730 | Average billing month (30.42 days × 24) |
| Yearly | 8760 | 365 × 24 (or 8784 for leap year) |

### 4.2 Dynamic Hours (NEW - Not Hardcoded!)

Instead of hardcoding 730, use actual runtime:
- Query CloudWatch for actual instance uptime
- Calculate hours from first to last metric timestamp
- Use this for more accurate cost calculations

---

## 5. Parameters Missing in Current Application

### 5.1 Critical Gaps (High Priority)

| Gap | Impact | Solution |
|-----|--------|----------|
| RDS uses EC2 EBS pricing | WRONG costs! | ✅ FIXED - Use RDSStoragePricingLoader |
| Multi-AZ storage not doubled | Undercharges 2x | ✅ FIXED - Multiply by 2 |
| Reserved Instance pricing | No RI discounts | ⚠️ Need implementation |
| Savings Plans | No SP discounts | ⚠️ Need implementation |
| Hardcoded 730 hours | Inaccurate | ⚠️ Need dynamic hours |

### 5.2 Medium Gaps

| Gap | Impact | Solution |
|-----|--------|----------|
| EBS Snapshots | Missing snapshot costs | ⚠️ Need implementation |
| Data Transfer | Missing transfer costs | ⚠️ Need implementation |
| Load Balancer costs | Missing LB costs | ⚠️ Need implementation |
| NAT Gateway costs | Missing NAT costs | ⚠️ Need implementation |
| CloudWatch costs | Missing CW costs | ⚠️ Need implementation |

### 5.3 Lower Priority

| Gap | Impact |
|-----|--------|
| RDS Backup Storage | Automated backup storage |
| RDS Performance Insights | Enhanced monitoring costs |
| RDS Enhanced Monitoring | Detailed metrics costs |
| Read Replica costs | Cross-AZ data transfer |
| RDS Proxy costs | Connection pooling |

---

## 6. AWS API Calls for Cost Data

### 6.1 EC2 API Calls

```python
# Instance data
ec2.describe_instances()

# Volume data
ec2.describe_volumes()

# Snapshot data
ec2.describe_snapshots(OwnerIds=['self'])

# Reserved Instances (if any)
ec2.describe_reserved_instances()

# Savings Plans
savingsplan.describe_savings_plans()
```

### 6.2 RDS API Calls

```python
# Instance data
rds.describe_db_instances()

# Storage data
rds.describe_db_instances()  # AllocatedStorage, StorageType

# Snapshots
rds.describe_db_snapshots(SnapshotType='manual')

# Reserved Instances
rds.describe_reserved_db_instances()
```

### 6.3 CloudWatch for Runtime

```python
# Get actual instance runtime
cloudwatch.get_metric_statistics(
    Namespace='AWS/EC2',
    MetricName='StatusCheckFailed',
    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
    StartTime=start_time,
    EndTime=end_time,
    Period=3600,
    Statistics=['Maximum']
)
```

### 6.4 AWS Pricing API

```python
# EC2 On-Demand
pricing.get_products(
    ServiceCode='AmazonEC2',
    Filters=[
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
        {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': os},
        {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': tenancy}
    ]
)

# RDS On-Demand
pricing.get_products(
    ServiceCode='AmazonRDS',
    Filters=[
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
        {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': engine},
        {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ' or 'Multi-AZ'}
    ]
)

# RDS Storage (DIFFERENT from EC2!)
pricing.get_products(
    ServiceCode='AmazonRDS',
    Filters=[
        {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': volume_type},
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
        {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Database Storage'}
    ]
)
```

---

## 7. Summary: Complete Cost Breakdown

### EC2 Total Cost
```
EC2InstanceCost = instance_price_per_hour × hours
EBSStorageCost = sum(volume_size × price_per_gb for each volume)
EBSSnapshotCost = sum(snapshot_size × snapshot_price for each snapshot)
DataTransferCost = gb_transferred × price_per_gb

TotalEC2Cost = EC2InstanceCost + EBSStorageCost + EBSSnapshotCost + DataTransferCost
```

### RDS Total Cost
```
RDSInstanceCost = instance_price_per_hour × hours
RDSStorageCost = allocated_storage × rds_price_per_gb × (2 if MultiAZ else 1)
RDSIOPSCost = provisioned_iops × rds_price_per_iops
BackupStorageCost = backup_size × backup_price
DataTransferCost = gb_transferred × price_per_gb
PerformanceInsightsCost = vcpu_count × price_per_vcpu

TotalRDSCost = RDSInstanceCost + RDSStorageCost + RDSIOPSCost + BackupStorageCost + DataTransferCost + PerformanceInsightsCost
```

---

## 8. Hardcoded Values to Remove

| Location | Current Value | Replace With |
|----------|--------------|--------------|
| constants.py:13 | HOURS_PER_MONTH = 730 | Dynamic calculation |
| constants.py:106 | DEFAULT_EBS_STORAGE_COST = 0.10 | Dynamic lookup from pricing API |
| constants.py:107 | DEFAULT_RDS_STORAGE_COST = 0.115 | Dynamic lookup from pricing API |
| cost_calculator.py | monthly / 30 | Dynamic days per month |
| cost_calculator.py | monthly * 12 | Dynamic months per year |

---

## 9. Implementation Priority

1. **Phase 1 (DONE)**: Fix RDS storage pricing (CRITICAL BUG)
2. **Phase 2 (DONE)**: Add additional cost components
3. **Phase 3 (DONE)**: Add RI and Savings Plans
4. **Phase 4 (DONE)**: Remove hardcoded values
5. **Phase 5**: Add backup storage calculations
6. **Phase 6**: Add Performance Insights costs
7. **Phase 7**: Add data transfer calculations
