"""
SQLAlchemy database models for AWS Cost Optimization Tool.

This module defines the database schema using SQLAlchemy ORM,
compatible with Roll framework and supporting both SQLite and PostgreSQL.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class EtlRun(Base):
    """ETL Run management model."""
    __tablename__ = 'etl_runs'
    
    run_id = Column(Integer, primary_key=True, autoincrement=True)
    run_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    start_time = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    records_extracted = Column(Integer, nullable=True)
    records_loaded = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(100), nullable=True)
    service_flags = Column(String(255), nullable=True)
    
    __table_args__ = (
        Index('ix_etl_runs_status', 'status'),
        Index('ix_etl_runs_start_time', 'start_time'),
    )


class RawInstance(Base):
    """AWS Resource Instances (EC2, RDS, EBS) model."""
    __tablename__ = 'raw_instances'
    
    instance_id = Column(String(100), primary_key=True)
    service_type = Column(String(20), nullable=False)
    region = Column(String(50), nullable=False)
    instance_class = Column(String(50), nullable=True)
    engine = Column(String(50), nullable=True)
    status = Column(String(30), nullable=True)
    created_date = Column(DateTime, nullable=True)
    vpc_id = Column(String(50), nullable=True)
    publicly_accessible = Column(Boolean, nullable=True)
    storage_type = Column(String(30), nullable=True)
    multi_az = Column(Boolean, nullable=True)
    availability_zone = Column(String(30), nullable=True)
    db_instance_arn = Column(String(255), nullable=True)
    backup_retention = Column(Integer, nullable=True)
    maintenance_window = Column(String(50), nullable=True)
    backup_window = Column(String(50), nullable=True)
    image_id = Column(String(50), nullable=True)
    subnet_id = Column(String(50), nullable=True)
    architecture = Column(String(20), nullable=True)
    public_ip = Column(String(50), nullable=True)
    private_ip = Column(String(50), nullable=True)
    root_device = Column(String(100), nullable=True)
    virtualization = Column(String(30), nullable=True)
    name = Column(String(100), nullable=True)
    raw_data = Column(Text, nullable=True)
    extracted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # EBS Volume fields
    environment_tag = Column(String(50), nullable=True)
    attached_instance_id = Column(String(100), nullable=True)
    volume_id = Column(String(50), nullable=True)
    size_gb = Column(Integer, nullable=True)
    volume_type = Column(String(20), nullable=True)
    iops = Column(Integer, nullable=True)
    throughput_mbps = Column(Integer, nullable=True)
    encrypted = Column(Boolean, nullable=True)
    monthly_cost = Column(Float, default=0.0)
    
    # Relationships
    metrics = relationship("RawMetric", back_populates="instance", cascade="all, delete-orphan")
    tags = relationship("InstanceTag", back_populates="instance", cascade="all, delete-orphan")
    analysis_cache = relationship("AnalysisCache", back_populates="instance", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_raw_instances_service_type', 'service_type'),
        Index('ix_raw_instances_region', 'region'),
        Index('ix_raw_instances_status', 'status'),
        Index('ix_raw_instances_environment_tag', 'environment_tag'),
        Index('ix_raw_instances_attached_instance_id', 'attached_instance_id'),
    )


class RawMetric(Base):
    """CloudWatch Metrics model."""
    __tablename__ = 'raw_metrics'
    
    metric_id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(String(100), ForeignKey('raw_instances.instance_id'), nullable=False)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False)
    unit = Column(String(20), nullable=True)
    statistics = Column(String(20), nullable=True)
    extracted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship
    instance = relationship("RawInstance", back_populates="metrics")
    
    __table_args__ = (
        Index('ix_raw_metrics_instance_id', 'instance_id'),
        Index('ix_raw_metrics_timestamp', 'timestamp'),
        Index('ix_raw_metrics_metric_name', 'metric_name'),
    )


class InstanceTag(Base):
    """Instance Tags model."""
    __tablename__ = 'instance_tags'
    
    instance_id = Column(String(100), ForeignKey('raw_instances.instance_id'), primary_key=True)
    tag_key = Column(String(100), primary_key=True)
    tag_value = Column(String(255), nullable=True)
    extracted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship
    instance = relationship("RawInstance", back_populates="tags")
    
    __table_args__ = (
        Index('ix_instance_tags_instance_id', 'instance_id'),
    )


class DataFreshness(Base):
    """Data Freshness Tracking model."""
    __tablename__ = 'data_freshness'
    
    service_type = Column(String(50), primary_key=True)
    last_updated = Column(DateTime, nullable=False)
    next_scheduled = Column(DateTime, nullable=True)
    record_count = Column(Integer, nullable=True)
    status = Column(String(20), default='fresh')


class EtlLock(Base):
    """ETL Lock Management model."""
    __tablename__ = 'etl_lock'
    
    lock_id = Column(Integer, primary_key=True, default=1)
    is_locked = Column(Boolean, nullable=False, default=False)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(String(100), nullable=True)


class AnalysisCache(Base):
    """Analysis Cache model."""
    __tablename__ = 'analysis_cache'
    
    instance_id = Column(String(100), ForeignKey('raw_instances.instance_id'), primary_key=True)
    service_type = Column(String(20), nullable=False)
    idle_score = Column(Integer, nullable=True)
    severity = Column(String(20), nullable=True)
    last_activity_date = Column(DateTime, nullable=True)
    days_idle = Column(Float, nullable=True)
    idle_reasons = Column(Text, nullable=True)
    active_reasons = Column(Text, nullable=True)
    indicators = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    potential_savings_monthly = Column(Float, nullable=True)
    analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship
    instance = relationship("RawInstance", back_populates="analysis_cache")


class AwsPricing(Base):
    """AWS Pricing Data model."""
    __tablename__ = 'aws_pricing'
    
    sku = Column(String(100), primary_key=True)
    instance_type = Column(String(50), nullable=True)
    region = Column(String(50), nullable=True)
    price_per_hour = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    service = Column(String(30), nullable=True)
    raw_json = Column(Text, nullable=True)
    
    __table_args__ = (
        Index('ix_aws_pricing_instance_type_region_service', 'instance_type', 'region', 'service'),
    )


class EbsPricing(Base):
    """EBS Pricing Data model."""
    __tablename__ = 'ebs_pricing'
    
    sku = Column(String(100), primary_key=True)
    volume_type = Column(String(30), nullable=False)
    region = Column(String(50), nullable=False)
    price_per_gb_month = Column(Float, nullable=False)
    price_per_iops_month = Column(Float, nullable=True)
    currency = Column(String(10), default='USD')
    location = Column(String(100), nullable=True)
    raw_json = Column(Text, nullable=True)
    extracted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('ix_ebs_pricing_volume_type_region', 'volume_type', 'region'),
    )
