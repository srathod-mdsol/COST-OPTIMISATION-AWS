"""Reusable UI components for the dashboard.

This module contains helper methods for rendering various UI components
within the Streamlit dashboard. These are used by the DashboardUI class.
"""

import streamlit as st
from typing import Dict, Optional, Tuple


def render_auth_section(auth, session_state=None) -> None:
    """Render authentication section in sidebar.
    
    Shows login form for unauthenticated users, and user info/logout
    for authenticated users. Also provides password change functionality.
    
    Args:
        auth: AuthManager instance
        session_state: Streamlit session state (optional)
    """
    # Use provided session_state or get from st
    if session_state is None:
        session_state = st.session_state
    
    # Check if admin users are configured
    if not auth.has_users():
        # No admin users configured - show info message
        st.markdown('''
        <div style="
            background: rgba(255, 153, 0, 0.1); 
            padding: 1rem; 
            border-radius: 10px; 
            border: 1px solid rgba(255, 153, 0, 0.3);
            margin-bottom: 1rem;
        ">
            <p style="margin: 0; font-size: 0.85rem; color: #ff9900;">
                🔐 Admin features unlocked. Configure ADMIN_USERS in .env to enable authentication.
            </p>
        </div>
        ''', unsafe_allow_html=True)
        # Set admin access to True when no users configured
        session_state['admin_authenticated'] = True
        return
    
    # Update activity timestamp if authenticated
    if auth.is_authenticated(session_state):
        auth.update_activity(session_state)
    
    if auth.is_authenticated(session_state):
        # Authenticated user info
        username = auth.get_current_user(session_state)
        remaining_time = auth.get_remaining_session_time(session_state)
        
        st.markdown(f'''
        <div style="
            background: rgba(0, 200, 83, 0.1); 
            padding: 1rem; 
            border-radius: 10px;
        ">
            <p style="margin: 0; font-size: 0.9rem; color: #00c853;">
                ✅ Logged in as <strong>{username}</strong>
            </p>
            <p style="margin: 0.25rem 0 0 0; font-size: 0.75rem; color: #666;">
                Session expires in {remaining_time}
            </p>
        </div>
        ''', unsafe_allow_html=True)
        
        # Logout button
        if st.button("Logout", key="logout_btn"):
            auth.logout(session_state)
            st.rerun()
    else:
        # Login form
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit:
                success, message = auth.login(username, password, session_state)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # Store authentication status for use in other methods
    session_state['admin_authenticated'] = auth.is_authenticated(session_state)


def render_tags_display(instance_id: str, env: str) -> None:
    """Render tags for a given instance.
    
    Args:
        instance_id: The instance ID to display tags for
        env: The environment name
    """
    from ui.dashboard.cache import get_instance_tags_cached
    
    try:
        tags = get_instance_tags_cached(instance_id, env)
        if tags:
            st.markdown("**Tags:**")
            cols = st.columns([1, 2])
            for i, (key, value) in enumerate(tags.items()):
                with cols[i % 2]:
                    st.caption(f"**{key}**: {value}")
        else:
            st.caption("No tags found")
    except Exception as e:
        st.caption(f"Unable to fetch tags: {e}")


def render_instance_selector(manager, service_type: str) -> Optional[str]:
    """Render instance selector dropdown.
    
    Args:
        manager: Service manager instance (EC2, RDS, or EBS)
        service_type: The service type string
        
    Returns:
        Selected instance ID or None
    """
    from ui.dashboard.cache import get_instances_cached
    
    try:
        # Get instances from cache
        import streamlit as st
        region = st.session_state.get('selected_region', 'us-east-1')
        env = st.session_state.get('aws_environment', 'Default')
        
        instances = get_instances_cached(service_type, region, env)
        
        if not instances:
            st.info(f"No {service_type} instances found in this region")
            return None
        
        # Format instance options based on service type
        if service_type == 'EBS':
            options = [f"{i.get('volume_id', 'Unknown')} - {i.get('size_gb', 0)}GB" 
                      for i in instances]
        else:
            options = [f"{i.get('instance_id', 'Unknown')} ({i.get('instance_type', 'Unknown')})" 
                      for i in instances]
        
        selected = st.selectbox(
            f"Select {service_type} Instance",
            options,
            help=f"Choose a {service_type} instance to analyze"
        )
        
        # Extract instance ID from selection
        if selected:
            if service_type == 'EBS':
                return selected.split(" - ")[0]
            else:
                return selected.split(" (")[0]
        
        return None
    except Exception as e:
        st.error(f"Error loading instances: {e}")
        return None


def render_freshness_info(service_type: str) -> None:
    """Render data freshness information.
    
    Args:
        service_type: The service type to check freshness for
    """
    from ui.dashboard.cache import get_data_freshness_cached
    from datetime import datetime, timezone
    
    try:
        import streamlit as st
        env = st.session_state.get('aws_environment', 'Default')
        freshness = get_data_freshness_cached(service_type, env)
        
        if freshness:
            last_updated = freshness.get('last_updated')
            record_count = freshness.get('record_count', 0)
            
            if last_updated:
                if isinstance(last_updated, str):
                    last_updated = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                
                now = datetime.now(timezone.utc)
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=timezone.utc)
                
                age = (now - last_updated).total_seconds() / 3600  # hours
                
                if age < 1:
                    st.caption(f"✅ Data: Just now ({record_count} records)")
                elif age < 24:
                    st.caption(f"⚠️ Data: {age:.1f}h old ({record_count} records)")
                else:
                    st.caption(f"❌ Data: {age/24:.1f}d old ({record_count} records)")
            else:
                st.caption(f"📊 {record_count} records")
        else:
            st.caption("❌ No data available")
    except Exception as e:
        st.caption(f"Unable to check freshness: {e}")


def render_header() -> None:
    """Render main header with AWS Console styling and animations"""
    st.markdown("""
    <!-- AWS Console Style Header with Animations -->
    <div class="aws-header">
        <div class="aws-header-left">
            <div class="aws-logo-container">
                <svg class="aws-logo" width="48" height="48" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <linearGradient id="awsGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#FF9900;stop-opacity:1" />
                            <stop offset="100%" style="stop-color:#FF6600;stop-opacity:1" />
                        </linearGradient>
                    </defs>
                    <path d="M32 4L4 22V50L32 62L60 50V22L32 4Z" stroke="url(#awsGrad)" stroke-width="2" fill="rgba(255,153,0,0.1)"/>
                    <path d="M32 14L14 25V43L32 52L50 43V25L32 14Z" fill="url(#awsGrad)"/>
                </svg>
            </div>
            <div class="aws-header-text">
                <h1>AWS Idle Instance Monitor</h1>
                <p class="aws-subtitle">Intelligent Cost Optimization & Resource Management</p>
            </div>
        </div>
        <div class="aws-header-right">
            <div class="aws-status-indicator">
                <span class="status-pulse"></span>
                <span>System Online</span>
            </div>
            <div class="aws-version-badge">v2.0</div>
        </div>
    </div>
    
    <style>
    .aws-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1.5rem 2rem;
        background: linear-gradient(135deg, #232f3e 0%, #1a2332 100%);
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }
    
    .aws-header-left {
        display: flex;
        align-items: center;
        gap: 1.5rem;
    }
    
    .aws-logo-container {
        position: relative;
    }
    
    .aws-logo {
        animation: float 3s ease-in-out infinite;
    }
    
    @keyframes float {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-5px); }
    }
    
    .aws-header-text h1 {
        margin: 0;
        font-size: 1.75rem;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: -0.5px;
    }
    
    .aws-subtitle {
        margin: 0.25rem 0 0 0;
        color: #aab7c4;
        font-size: 0.9rem;
    }
    
    .aws-header-right {
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    
    .aws-status-indicator {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: rgba(0,113,133,0.2);
        border-radius: 20px;
        color: #00d8ff;
        font-size: 0.85rem;
        font-weight: 500;
    }
    
    .status-pulse {
        width: 8px;
        height: 8px;
        background: #00d8ff;
        border-radius: 50%;
        animation: pulse 2s ease-in-out infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(1.2); }
    }
    
    .aws-version-badge {
        padding: 0.35rem 0.75rem;
        background: #ff9900;
        color: #232f3e;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    
    .aws-header-divider {
        border: none;
        height: 2px;
        background: linear-gradient(90deg, transparent, #ff9900, transparent);
        margin: 0 0 1.5rem 0;
    }
    </style>
    """, unsafe_allow_html=True)


def render_parameters() -> Tuple[int, int, int, dict]:
    """Render parameter controls with improved spacing.
    
    Returns:
        Tuple of (cloudwatch_hours, activity_days, idle_threshold, pricing_settings)
    """
    import streamlit as st
    
    st.markdown('''
    <div style="
        background: #ffffff; 
        border: 1px solid #dfe3e8; 
        border-radius: 10px; 
        padding: 1.5rem; 
        margin: 1rem 0 2rem 0;
    ">
        <h3 style="
            color: #232f3e; 
            font-size: 1.1rem; 
            margin: 0 0 1.5rem 0;
            padding-bottom: 0.75rem;
            border-bottom: 2px solid #ff9900;
        ">⚡ Mission Parameters</h3>
    </div>
    ''', unsafe_allow_html=True)
    
    # Create three columns with helpful tooltips
    col1, col2, col3 = st.columns(3)
    
    with col1:
        cw_hours = st.slider(
            "CloudWatch Lookback", 
            min_value=1, 
            max_value=2160, 
            value=2160,
            help="How far back to look for CloudWatch metrics (in hours). Higher values = more historical data but slower queries."
        )
        st.caption(f"📊 Viewing {cw_hours // 24} day(s) of metrics")
        
    with col2:
        act_days = st.slider(
            "Activity Detection Window", 
            min_value=1, 
            max_value=90, 
            value=30,
            help="Days of inactivity before marking a resource as potentially idle. Longer windows = fewer false positives."
        )
        st.caption(f"🔍 {act_days} day activity window")
        
    with col3:
        threshold = st.slider(
            "Idle Score Threshold", 
            min_value=0, 
            max_value=100, 
            value=70,
            help="Minimum idle score (0-100) to classify as idle. Higher = more strict classification."
        )
        st.caption(f"🎯 Threshold: {threshold}+")
    
    # Pricing Model Settings Section
    st.markdown('''
    <div style="
        background: #ffffff; 
        border: 1px solid #dfe3e8; 
        border-radius: 10px; 
        padding: 1.5rem; 
        margin: 1rem 0 2rem 0;
    ">
        <h3 style="
            color: #232f3e; 
            font-size: 1.1rem; 
            margin: 0 0 1.5rem 0;
            padding-bottom: 0.75rem;
            border-bottom: 2px solid #ff9900;
        ">💰 Pricing Model Settings</h3>
    </div>
    ''', unsafe_allow_html=True)
    
    # Pricing model selection
    pricing_col1, pricing_col2, pricing_col3 = st.columns(3)
    
    with pricing_col1:
        pricing_model = st.selectbox(
            "Pricing Model",
            options=["On-Demand", "Reserved Instances", "Savings Plans"],
            index=0,
            help="Select your pricing model to calculate accurate potential savings."
        )
    
    # Initialize pricing settings dictionary
    pricing_settings = {
        'pricing_model': pricing_model,
        'ri_coverage': 0,
        'sp_coverage': 0,
        'use_actual_runtime': False,
        'actual_hours': None
    }
    
    if pricing_model == "Reserved Instances":
        with pricing_col2:
            ri_coverage = st.slider(
                "RI Coverage", 
                min_value=0, 
                max_value=100, 
                value=0,
                help="Percentage of instances covered by Reserved Instances (0-100%). This reduces the calculated savings."
            )
            pricing_settings['ri_coverage'] = ri_coverage / 100.0
        st.caption(f"🔒 {ri_coverage}% covered by RI")
    elif pricing_model == "Savings Plans":
        with pricing_col2:
            sp_coverage = st.slider(
                "Savings Plans Coverage", 
                min_value=0, 
                max_value=100, 
                value=0,
                help="Percentage of instances covered by Savings Plans (0-100%). This reduces the calculated savings."
            )
            pricing_settings['sp_coverage'] = sp_coverage / 100.0
        st.caption(f"💎 {sp_coverage}% covered by Savings Plans")
    
    with pricing_col3:
        use_actual_runtime = st.checkbox(
            "Use Actual Runtime",
            value=False,
            help="Use actual instance runtime hours instead of fixed 730 hours/month for more accurate savings."
        )
        pricing_settings['use_actual_runtime'] = use_actual_runtime
    
    if use_actual_runtime:
        st.caption("📈 Using actual runtime hours for cost calculation")
    else:
        st.caption("📅 Using fixed 730 hours/month (average)")
    
    return cw_hours, act_days, threshold, pricing_settings


def get_manager(service_type: str, region: str, env: str):
    """Get service manager instance.
    
    Args:
        service_type: The service type (EC2, RDS, or EBS)
        region: The AWS region
        env: The environment name
        
    Returns:
        Manager instance
    """
    from ui.dashboard.cache import get_manager_cached
    return get_manager_cached(service_type, region, env)
