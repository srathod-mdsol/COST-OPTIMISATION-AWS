"""Single instance analysis view.

This module contains the display_single_analysis method for showing
detailed analysis of a single AWS resource.
"""

import streamlit as st
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from core.constants import HOURS_PER_MONTH


def display_single_analysis_view(
    manager,
    service_type: str,
    instance_id: str,
    cloudwatch_hours: int,
    activity_days: int,
    get_instances_cached,
    get_cloudwatch_metrics,
    detect_last_activity,
    get_attached_volumes,
    get_pricing_cached,
    get_ec2_detailed_breakdown_cached,
    get_rds_detailed_breakdown_cached,
    get_ebs_detailed_breakdown_cached,
    session_state
) -> None:
    """Display single instance analysis with improved visual hierarchy.
    
    Args:
        manager: Service manager instance
        service_type: Service type (EC2, RDS, EBS)
        instance_id: Instance ID to analyze
        cloudwatch_hours: CloudWatch lookback hours
        activity_days: Activity detection window
        get_instances_cached: Cache function for listing instances
        get_cloudwatch_metrics: Function to get CloudWatch metrics
        detect_last_activity: Function to detect last activity
        get_attached_volumes: Function to get attached volumes
        get_pricing_cached: Cache function for pricing
        get_ec2_detailed_breakdown_cached: Cache function for EC2 costs
        get_rds_detailed_breakdown_cached: Cache function for RDS costs
        get_ebs_detailed_breakdown_cached: Cache function for EBS costs
        session_state: Streamlit session state
    """
    env = session_state.get('aws_environment', 'Default')
    
    with st.spinner(f"🔍 Analyzing {instance_id}..."):
        try:
            # Fetch metrics
            metrics = get_cloudwatch_metrics(instance_id, cloudwatch_hours)
            last_activity = detect_last_activity(instance_id, activity_days)
            
            # Get instance info
            attached_volumes = []
            if service_type == 'RDS':
                instances = manager.list_instances()
                instance_info = next((i for i in instances if i.get('instance_id') == instance_id), None)
            elif service_type == 'EC2':
                instances = manager.list_instances()
                instance_info = next((i for i in instances if i.get('instance_id') == instance_id), None)
                attached_volumes = get_attached_volumes(instance_id)
            elif service_type == 'EBS':
                instances = manager.list_instances()
                instance_info = next((i for i in instances if i.get('volume_id') == instance_id), None)

            if not instance_info:
                st.error("Resource information not found")
                return

            # Get pricing
            region = instance_info.get('region', 'us-east-1')
            pricing = None
            
            if service_type == 'EC2':
                instance_type = instance_info.get('instance_type', '')
                operating_system = instance_info.get('platform', 'Linux')
                pricing = get_pricing_cached(instance_type, region, 'EC2', env, 
                                           operating_system=operating_system)
            elif service_type == 'RDS':
                instance_type = instance_info.get('instance_type', '')
                db_engine = instance_info.get('engine', 'mysql')
                deployment = instance_info.get('multi_az', False)
                pricing = get_pricing_cached(instance_type, region, 'RDS', env,
                                           database_engine=db_engine,
                                           deployment_option='Multi-AZ' if deployment else 'Single-AZ')
            elif service_type == 'EBS':
                vol_type = instance_info.get('volume_type', 'gp2')
                pricing = get_pricing_cached(vol_type, region, 'EBS', env)

            # Calculate idle score
            cpu_avg = metrics.get('cpu_utilization_avg', 0)
            memory_avg = metrics.get('memory_utilization_avg', 0)
            network_in = metrics.get('network_in_avg', 0)
            network_out = metrics.get('network_out_avg', 0)
            
            # Idle score calculation (0-100, higher = more idle)
            cpu_idle_score = max(0, 100 - cpu_avg)
            memory_idle_score = max(0, 100 - memory_avg) if memory_avg else 50
            network_idle_score = max(0, 100 - min(100, (network_in + network_out) / 1024 / 1024 * 10))
            
            idle_score = (cpu_idle_score * 0.5 + memory_idle_score * 0.3 + network_idle_score * 0.2)

            # Display header
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #232f3e 0%, #1a2332 100%);
                padding: 1.5rem;
                border-radius: 10px;
                margin-bottom: 1.5rem;
            ">
                <h2 style="color: white; margin: 0;">🔍 Instance Analysis: {instance_id}</h2>
                <p style="color: #aab7c4; margin: 0.5rem 0 0 0;">
                    Type: {instance_info.get('instance_type', instance_info.get('volume_type', 'Unknown'))} | 
                    Region: {region}
                </p>
            </div>
            """, unsafe_allow_html=True)

            # Metrics overview
            st.markdown("### 📊 Activity Metrics")
            
            cols = st.columns(4)
            with cols[0]:
                st.metric("CPU Utilization", f"{cpu_avg:.1f}%", 
                          delta_color="inverse" if cpu_avg > 50 else "normal")
            with cols[1]:
                if memory_avg:
                    st.metric("Memory Utilization", f"{memory_avg:.1f}%",
                             delta_color="inverse" if memory_avg > 50 else "normal")
                else:
                    st.metric("Memory Utilization", "N/A")
            with cols[2]:
                st.metric("Network In", f"{network_in/1024/1024:.2f} MB")
            with cols[3]:
                st.metric("Network Out", f"{network_out/1024/1024:.2f} MB")

            # Idle score visualization
            st.markdown("### 🎯 Idle Score")
            
            idle_col1, idle_col2 = st.columns([3, 1])
            
            with idle_col1:
                # Idle score bar
                idle_color = "green" if idle_score < 30 else "orange" if idle_score < 70 else "red"
                st.markdown(f"""
                <div style="
                    background: linear-gradient(90deg, #00aa00 0%, #ffaa00 50%, #ff0000 100%);
                    height: 30px;
                    border-radius: 15px;
                    position: relative;
                    margin: 1rem 0;
                ">
                    <div style="
                        position: absolute;
                        left: {idle_score}%;
                        top: -5px;
                        width: 4px;
                        height: 40px;
                        background: white;
                        border: 2px solid black;
                    "></div>
                </div>
                <div style="display: flex; justify-content: space-between; color: #666;">
                    <span>Active (0)</span>
                    <span>Idle (100)</span>
                </div>
                """, unsafe_allow_html=True)
                
            with idle_col2:
                st.markdown(f"""
                <div style="
                    text-align: center;
                    padding: 1rem;
                    background: {idle_color};
                    border-radius: 10px;
                    color: white;
                ">
                    <div style="font-size: 2rem; font-weight: bold;">{idle_score:.0f}</div>
                    <div>IDLE SCORE</div>
                </div>
                """, unsafe_allow_html=True)

            # Cost information
            st.markdown("### 💰 Cost Analysis")
            
            hourly_cost = pricing if pricing else 0
            monthly_cost = hourly_cost * HOURS_PER_MONTH
            
            cost_col1, cost_col2, cost_col3 = st.columns(3)
            with cost_col1:
                st.metric("Hourly Cost", f"${hourly_cost:.4f}")
            with cost_col2:
                st.metric("Monthly Cost", f"${monthly_cost:.2f}")
            with cost_col3:
                st.metric("Annual Cost", f"${monthly_cost * 12:.2f}")

            # Last activity
            st.markdown("### 🕐 Activity Timeline")
            
            if last_activity:
                last_active = last_activity.get('last_activity')
                if last_active:
                    if isinstance(last_active, str):
                        last_active = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                    
                    now = datetime.now(timezone.utc)
                    if last_active.tzinfo is None:
                        last_active = last_active.replace(tzinfo=timezone.utc)
                    
                    hours_since = (now - last_active).total_seconds() / 3600
                    
                    st.info(f"Last activity: {last_active.strftime('%Y-%m-%d %H:%M:%S UTC')} ({hours_since:.1f} hours ago)")
                else:
                    st.warning("No activity data available")
            else:
                st.warning("Unable to determine last activity")

            # Display charts
            st.markdown("### 📈 Performance Charts")
            
            # CPU chart
            cpu_data = metrics.get('cpu_utilization', [])
            if cpu_data:
                create_cpu_chart(cpu_data)
            
            # Network charts
            net_in = metrics.get('network_in', [])
            net_out = metrics.get('network_out', [])
            if net_in or net_out:
                create_network_chart(net_in, net_out)

            # Detailed cost breakdown
            st.markdown("---")
            st.markdown("### 💵 Detailed Cost Breakdown")
            
            # Get cost breakdown based on service type
            try:
                if service_type == 'EC2':
                    display_ec2_details(
                        instance_info, region, hourly_cost, monthly_cost,
                        attached_volumes, get_ec2_detailed_breakdown_cached, env
                    )
                elif service_type == 'RDS':
                    display_rds_details(
                        instance_info, region, hourly_cost, monthly_cost,
                        get_rds_detailed_breakdown_cached, env
                    )
                elif service_type == 'EBS':
                    display_ebs_details(
                        instance_info, region, hourly_cost, monthly_cost,
                        get_ebs_detailed_breakdown_cached, env
                    )
            except Exception as e:
                st.warning(f"Could not generate detailed breakdown: {e}")

        except Exception as e:
            st.error(f"Error analyzing instance: {e}")
            st.code(traceback.format_exc())


def create_cpu_chart(cpu_data: List) -> None:
    """Create CPU utilization chart."""
    import plotly.express as px
    import pandas as pd
    
    if cpu_data:
        df = pd.DataFrame(cpu_data, columns=['timestamp', 'value'])
        fig = px.line(df, x='timestamp', y='value', 
                     title='CPU Utilization Over Time',
                     labels={'value': 'CPU %', 'timestamp': 'Time'})
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)


def create_network_chart(network_in: List, network_out: List) -> None:
    """Create network traffic chart."""
    import plotly.graph_objects as go
    from datetime import datetime
    
    fig = go.Figure()
    
    if network_in:
        df_in = pd.DataFrame(network_in, columns=['timestamp', 'value'])
        fig.add_trace(go.Scatter(
            x=df_in['timestamp'], y=df_in['value']/1024/1024,
            mode='lines', name='Network In (MB)',
            line=dict(color='#00aa00')
        ))
    
    if network_out:
        df_out = pd.DataFrame(network_out, columns=['timestamp', 'value'])
        fig.add_trace(go.Scatter(
            x=df_out['timestamp'], y=df_out['value']/1024/1024,
            mode='lines', name='Network Out (MB)',
            line=dict(color='#ff0000')
        ))
    
    fig.update_layout(
        title='Network Traffic Over Time',
        xaxis_title='Time',
        yaxis_title='MB',
        height=300
    )
    st.plotly_chart(fig, use_container_width=True)


def display_ec2_details(
    instance_info: Dict,
    region: str,
    hourly_cost: float,
    monthly_cost: float,
    attached_volumes: List,
    get_ec2_detailed_breakdown_cached,
    env: str
) -> None:
    """Display EC2-specific cost details."""
    import json
    
    st.markdown("### 💻 EC2 Instance Cost Breakdown")
    
    try:
        sku = instance_info.get('instance_type', '')
        operating_system = instance_info.get('platform', 'Linux')
        tenancy = instance_info.get('tenancy', 'default')
        
        ebs_volumes_for_calc = []
        if attached_volumes:
            for vol in attached_volumes:
                ebs_volumes_for_calc.append({
                    'volume_id': vol.get('volume_id', 'unknown'),
                    'size_gb': vol.get('size', 10),
                    'volume_type': vol.get('volume_type', 'gp2')
                })
        
        ebs_volumes_json = json.dumps(ebs_volumes_for_calc) if ebs_volumes_for_calc else '[]'
        
        detailed_cost = get_ec2_detailed_breakdown_cached(
            instance_type=sku,
            region=region,
            operating_system=operating_system,
            tenancy=tenancy,
            hourly_price=hourly_cost,
            env=env,
            ebs_volumes_json=ebs_volumes_json
        )
        
        # Display compute costs
        compute = detailed_cost.get('compute', {})
        st.markdown("**COMPUTE COSTS**")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Instance Type", detailed_cost.get('instance_type', sku))
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
        
        # Display storage costs
        storage = detailed_cost.get('storage', {})
        if storage.get('volumes'):
            st.markdown("**STORAGE COSTS (EBS)**")
            for vol in storage.get('volumes', []):
                st.markdown(f"""
                <div style="background: rgba(255,150,0,0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin: 5px 0;">
                    <strong>Volume: {vol.get('volume_id', 'unknown')}</strong><br/>
                    <small>Type: {vol.get('volume_type')} | Size: {vol.get('size_gb')} GB</small><br/>
                    <strong>Total: ${vol.get('total_monthly', 0):.2f}/mo</strong>
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


def display_rds_details(
    instance_info: Dict,
    region: str,
    hourly_cost: float,
    monthly_cost: float,
    get_rds_detailed_breakdown_cached,
    env: str
) -> None:
    """Display RDS-specific cost details."""
    st.markdown("### 🗄️ RDS Instance Cost Breakdown")
    
    try:
        sku = instance_info.get('instance_type', '')
        database_engine = instance_info.get('engine', 'mysql')
        license_model = instance_info.get('license_model', 'included')
        deployment_option = 'Multi-AZ' if instance_info.get('multi_az', False) else 'Single-AZ'
        allocated_storage = instance_info.get('allocated_storage', 100)
        storage_type = instance_info.get('storage_type', 'gp2')
        iops = instance_info.get('iops')
        multi_az = instance_info.get('multi_az', False)
        
        detailed_cost = get_rds_detailed_breakdown_cached(
            instance_type=sku,
            region=region,
            database_engine=database_engine,
            license_model=license_model,
            deployment_option=deployment_option,
            instance_hourly_price=hourly_cost,
            allocated_storage=allocated_storage,
            storage_type=storage_type,
            iops=int(iops) if iops else 0,
            multi_az=multi_az,
            env=env
        )
        
        # Display compute costs
        compute = detailed_cost.get('compute', {})
        st.markdown("**COMPUTE COSTS**")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Instance Type", detailed_cost.get('instance_type', sku))
        with col2:
            st.metric("Database Engine", detailed_cost.get('database_engine', database_engine))
        
        st.markdown(f"""
        <div style="background: rgba(0,100,0,0.1); padding: 10px; border-radius: 5px; margin: 10px 0;">
            <strong>Compute Subtotal:</strong> ${compute.get('monthly', 0):.2f}/month
        </div>
        """, unsafe_allow_html=True)
        
        # Storage costs
        storage = detailed_cost.get('storage', {})
        st.markdown(f"""
        <div style="background: rgba(255,150,0,0.1); padding: 10px; border-radius: 5px; border-left: 3px solid #ff9900; margin: 10px 0;">
            <strong>Storage Subtotal:</strong> ${storage.get('monthly', 0):.2f}/month
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


def display_ebs_details(
    instance_info: Dict,
    region: str,
    hourly_cost: float,
    monthly_cost: float,
    get_ebs_detailed_breakdown_cached,
    env: str
) -> None:
    """Display EBS-specific cost details."""
    st.markdown("### 💿 EBS Volume Cost Breakdown")
    
    try:
        volume_id = instance_info.get('volume_id', 'unknown')
        vol_size = instance_info.get('size_gb', 0)
        vol_type = instance_info.get('volume_type', 'gp2')
        vol_iops = instance_info.get('iops')
        vol_throughput = instance_info.get('throughput_mbps')
        
        detailed_cost = get_ebs_detailed_breakdown_cached(
            volume_id=volume_id,
            size_gb=vol_size,
            volume_type=vol_type,
            region=region,
            iops=vol_iops if vol_iops else 0,
            throughput_mbps=vol_throughput if vol_throughput else 0,
            env=env
        )
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Volume Type", detailed_cost.get('volume_type', vol_type))
        with col2:
            st.metric("Size", f"{detailed_cost.get('size_gb', vol_size)} GB")
        with col3:
            st.metric("Storage Rate", f"${detailed_cost.get('storage_rate', 0):.3f}/GB/mo")
        
        st.markdown(f"""
        <div style="background: rgba(0,150,0,0.2); padding: 15px; border-radius: 5px; margin: 15px 0; border: 2px solid #00aa00;">
            <strong style="font-size: 1.2em;">TOTAL MONTHLY COST: ${detailed_cost.get('monthly', 0):.2f}</strong><br/>
            <strong style="font-size: 1.2em;">TOTAL ANNUAL COST: ${detailed_cost.get('annual', 0):.2f}</strong>
        </div>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        st.warning(f"Could not generate detailed breakdown: {e}")


# Import pandas for charts
import pandas as pd
import traceback
