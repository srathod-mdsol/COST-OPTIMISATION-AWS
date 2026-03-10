"""Helper functions for cost display and formatting.

This module contains utility functions for displaying and formatting
cost information in the dashboard. These are extracted from the main
DashboardUI class for better maintainability.
"""

import streamlit as st
from typing import Dict, Any, Optional, List


def display_ec2_cost_breakdown(
    detailed_cost: Dict,
    instance_type: str,
    region: str,
    operating_system: str,
    tenancy: str,
    hourly_price: float,
    ebs_volumes: Optional[List[Dict]] = None
) -> None:
    """Display EC2 detailed cost breakdown.
    
    Args:
        detailed_cost: Cost breakdown dictionary from CostCalculator
        instance_type: EC2 instance type
        region: AWS region
        operating_system: Operating system
        tenancy: Tenancy type
        hourly_price: Hourly price
        ebs_volumes: List of attached EBS volumes
    """
    from core.constants import HOURS_PER_MONTH
    
    st.markdown("### 💻 EC2 Instance Cost Breakdown")
    
    # Get detailed cost breakdown using cached function
    try:
        import json
        ebs_volumes_json = json.dumps(ebs_volumes) if ebs_volumes else '[]'
        
        # Display Compute Costs
        compute = detailed_cost.get('compute', {})
        st.markdown("**COMPUTE COSTS**")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Instance Type", detailed_cost.get('instance_type', instance_type))
        with col2:
            st.metric("Operating System", operating_system)
        with col3:
            st.metric("Unit Price", f"${compute.get('unit_price', 0):.4f}/hr")
        with col4:
            st.metric("Hours/Month", f"{compute.get('hours', HOURS_PER_MONTH)}")
        
        st.markdown(f"""
        <div style="background: rgba(0,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
            <strong>Compute Subtotal:</strong> ${compute.get('monthly', 0):.2f}/month
        </div>
        """, unsafe_allow_html=True)
        
        # Display Storage Costs
        storage = detailed_cost.get('storage', {})
        volumes = storage.get('volumes', [])
        if volumes:
            st.markdown("**STORAGE COSTS (EBS)**")
            for vol in volumes:
                st.markdown(f"""
                <div style="background: rgba(255,150,0,0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin: 5px 0;">
                    <strong>Volume: {vol.get('volume_id', 'unknown')}</strong><br/>
                    <small>Type: {vol.get('volume_type')} | Size: {vol.get('size_gb')} GB</small><br/>
                    Storage: ${vol.get('storage_monthly', 0):.2f}/mo | IOPS: ${vol.get('iops_monthly', 0):.2f}/mo<br/>
                    <strong>Total: ${vol.get('total_monthly', 0):.2f}/mo</strong>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="background: rgba(0,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                <strong>Storage Subtotal:</strong> ${storage.get('monthly', 0):.2f}/month
            </div>
            """, unsafe_allow_html=True)
        
        # Display Data Transfer
        data_transfer = detailed_cost.get('data_transfer', {})
        if data_transfer.get('gb_out', 0) > 0 or data_transfer.get('gb_in', 0) > 0:
            st.markdown("**DATA TRANSFER**")
            st.markdown(f"""
            <div style="background: rgba(0,0,100,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                Transfer OUT: {data_transfer.get('gb_out', 0)} GB @ ${data_transfer.get('rate_out', 0):.2f}/GB = ${data_transfer.get('cost_out', 0):.2f}<br/>
                <strong>Transfer Subtotal:</strong> ${data_transfer.get('monthly', 0):.2f}/month
            </div>
            """, unsafe_allow_html=True)
        
        # Total
        st.markdown(f"""
        <div style="background: rgba(0,150,0,0.2); padding: 15px; border-radius: 5px; margin: 15px 0; border: 2px solid #00aa00;">
            <strong style="font-size: 1.2em;">TOTAL MONTHLY COST: ${detailed_cost.get('monthly', 0):.2f}</strong><br/>
            <strong style="font-size: 1.2em;">TOTAL ANNUAL COST: ${detailed_cost.get('annual', 0):.2f}</strong>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.warning(f"Could not generate detailed breakdown: {e}")


def display_rds_cost_breakdown(
    detailed_cost: Dict,
    instance_type: str,
    region: str,
    database_engine: str,
    license_model: str,
    deployment_option: str,
    instance_hourly_price: float,
    allocated_storage: int,
    storage_type: str,
    iops: Optional[int],
    multi_az: bool
) -> None:
    """Display RDS detailed cost breakdown.
    
    Args:
        detailed_cost: Cost breakdown dictionary from CostCalculator
        instance_type: RDS instance type
        region: AWS region
        database_engine: Database engine
        license_model: License model
        deployment_option: Deployment option (Single-AZ/Multi-AZ)
        instance_hourly_price: Hourly price
        allocated_storage: Allocated storage in GB
        storage_type: Storage type
        iops: IOPS value
        multi_az: Whether Multi-AZ is enabled
    """
    st.markdown("### 🗄️ RDS Instance Cost Breakdown")
    
    try:
        # Display Compute Costs
        compute = detailed_cost.get('compute', {})
        st.markdown("**COMPUTE COSTS**")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Instance Type", detailed_cost.get('instance_type', instance_type))
        with col2:
            st.metric("Database Engine", detailed_cost.get('database_engine', database_engine))
        
        col3, col4 = st.columns(2)
        with col3:
            st.metric("Deployment", detailed_cost.get('deployment_option', deployment_option))
        with col4:
            st.metric("Unit Price", f"${compute.get('unit_price', 0):.4f}/hr")
        
        st.markdown(f"""
        <div style="background: rgba(0,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
            <strong>Compute Subtotal:</strong> ${compute.get('monthly', 0):.2f}/month
        </div>
        """, unsafe_allow_html=True)
        
        # Display Storage Costs
        storage = detailed_cost.get('storage', {})
        st.markdown("**STORAGE COSTS**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Storage Type", storage.get('storage_type', storage_type))
        with col2:
            st.metric("Allocated", f"{storage.get('allocated_storage_gb', 0)} GB")
        with col3:
            st.metric("Multi-AZ Factor", f"{storage.get('multi_az_factor', 1)}x")
        
        st.markdown(f"""
        <div style="background: rgba(255,150,0,0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin: 10px 0;">
            Effective Storage: {storage.get('effective_storage_gb', 0)} GB @ ${storage.get('rate_per_gb', 0):.3f}/GB/mo<br/>
            <strong>Storage Subtotal:</strong> ${storage.get('monthly', 0):.2f}/month
        </div>
        """, unsafe_allow_html=True)
        
        # Display IOPS Costs
        iops_data = detailed_cost.get('iops', {})
        if iops_data.get('provisioned'):
            st.markdown("**IOPS COSTS**")
            st.markdown(f"""
            <div style="background: rgba(100,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                Provisioned: {iops_data.get('provisioned', 0)} IOPS<br/>
                Base Included: {iops_data.get('base_included', 0)} IOPS<br/>
                Extra IOPS: {iops_data.get('extra_iops', 0)} @ ${iops_data.get('rate_per_iops', 0):.4f}/IOPS/mo<br/>
                <strong>IOPS Subtotal:</strong> ${iops_data.get('monthly', 0):.2f}/month
            </div>
            """, unsafe_allow_html=True)
        
        # Total
        st.markdown(f"""
        <div style="background: rgba(0,150,0,0.2); padding: 15px; border-radius: 5px; margin: 15px 0; border: 2px solid #00aa00;">
            <strong style="font-size: 1.2em;">TOTAL MONTHLY COST: ${detailed_cost.get('monthly', 0):.2f}</strong><br/>
            <strong style="font-size: 1.2em;">TOTAL ANNUAL COST: ${detailed_cost.get('annual', 0):.2f}</strong>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.warning(f"Could not generate detailed breakdown: {e}")


def display_ebs_cost_breakdown(
    detailed_cost: Dict,
    volume_id: str,
    size_gb: int,
    volume_type: str,
    region: str
) -> None:
    """Display EBS detailed cost breakdown.
    
    Args:
        detailed_cost: Cost breakdown dictionary from CostCalculator
        volume_id: EBS volume ID
        size_gb: Size in GB
        volume_type: Volume type
        region: AWS region
    """
    st.markdown("### 💿 EBS Volume Cost Breakdown")
    
    try:
        vol_size = size_gb
        vol_type = volume_type
        
        # Display Storage Cost
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Volume Type", detailed_cost.get('volume_type', vol_type))
        with col2:
            st.metric("Size", f"{detailed_cost.get('size_gb', vol_size)} GB")
        with col3:
            st.metric("Storage Rate", f"${detailed_cost.get('storage_rate', 0):.3f}/GB/mo")
        
        st.markdown(f"""
        <div style="background: rgba(255,150,0,0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin: 10px 0;">
            <strong>Storage Cost:</strong> ${detailed_cost.get('storage_monthly', 0):.2f}/month
        </div>
        """, unsafe_allow_html=True)
        
        # Display IOPS Cost if applicable
        if detailed_cost.get('iops_provisioned'):
            st.markdown(f"""
            <div style="background: rgba(100,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                Provisioned IOPS: {detailed_cost.get('iops_provisioned', 0)}<br/>
                IOPS Rate: ${detailed_cost.get('iops_rate', 0):.4f}/IOPS/mo<br/>
                <strong>IOPS Cost:</strong> ${detailed_cost.get('iops_monthly', 0):.2f}/month
            </div>
            """, unsafe_allow_html=True)
        
        # Display Throughput Cost if applicable
        if detailed_cost.get('throughput_provisioned'):
            st.markdown(f"""
            <div style="background: rgba(100,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
                Provisioned Throughput: {detailed_cost.get('throughput_provisioned', 0)} MB/s<br/>
                Throughput Rate: ${detailed_cost.get('throughput_rate', 0):.4f}/MB/s/mo<br/>
                <strong>Throughput Cost:</strong> ${detailed_cost.get('throughput_monthly', 0):.2f}/month
            </div>
            """, unsafe_allow_html=True)
        
        # Total
        st.markdown(f"""
        <div style="background: rgba(0,150,0,0.2); padding: 15px; border-radius: 5px; margin: 15px 0; border: 2px solid #00aa00;">
            <strong style="font-size: 1.2em;">TOTAL MONTHLY COST: ${detailed_cost.get('monthly', 0):.2f}</strong><br/>
            <strong style="font-size: 1.2em;">TOTAL ANNUAL COST: ${detailed_cost.get('annual', 0):.2f}</strong>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.warning(f"Could not generate detailed breakdown: {e}")


def format_currency(amount: float) -> str:
    """Format amount as currency.
    
    Args:
        amount: Amount to format
        
    Returns:
        Formatted currency string
    """
    return f"${amount:,.2f}"


def format_percentage(value: float) -> str:
    """Format value as percentage.
    
    Args:
        value: Value to format (0-100)
        
    Returns:
        Formatted percentage string
    """
    return f"{value:.1f}%"


def calculate_idle_score(metrics: Dict) -> float:
    """Calculate idle score from CloudWatch metrics.
    
    Args:
        metrics: CloudWatch metrics dictionary
        
    Returns:
        Idle score (0-100)
    """
    # This is a placeholder - the actual implementation
    # is in the DashboardUI class with full context
    cpu_idle = 100 - metrics.get('cpu_utilization_avg', 0)
    network_idle = 100 - metrics.get('network_in_avg', 0) / max(metrics.get('network_in_max', 1), 1) * 100
    return (cpu_idle + network_idle) / 2
