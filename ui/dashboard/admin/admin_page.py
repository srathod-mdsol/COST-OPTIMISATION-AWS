"""
Admin Page Module - Centralized Admin Interface

Provides a comprehensive admin interface that integrates all admin modules
including authentication, access control, ETL management, and scheduling.
"""

import streamlit as st
from typing import Optional

from ui.dashboard.admin.auth import render_auth_section, get_auth_manager, render_session_info
from ui.dashboard.admin.access_control import check_admin_access, has_admin_users_configured
from ui.dashboard.admin.etl_controls import render_etl_controls, render_etl_lock_status
from ui.dashboard.admin.etl_status import render_etl_history, render_etl_metrics, render_etl_status_summary, get_data_freshness
from ui.dashboard.admin.scheduler import render_scheduler_settings, get_scheduler_status, render_scheduler_status_card
from ui.dashboard.export import ExportController, ReportGenerator


def render_admin_page(session_state=None) -> None:
    """Render the centralized admin page with tab navigation.
    
    Args:
        session_state: Streamlit session state
    """
    if session_state is None:
        session_state = st.session_state
    
    # Page title
    st.markdown('''
    <div style="
        background: linear-gradient(135deg, #232f3e 0%, #3f4a5a 100%);
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    ">
        <h1 style="
            color: #ff9900;
            margin: 0;
            font-size: 1.5rem;
        ">⚙️ Admin Dashboard</h1>
        <p style="
            color: #d1d5db;
            margin: 0.5rem 0 0 0;
            font-size: 0.9rem;
        ">Manage ETL processes, scheduling, and system configuration</p>
    </div>
    ''', unsafe_allow_html=True)
    
    # Check if admin users are configured
    if not has_admin_users_configured():
        st.markdown('''
        <div style="
            background: rgba(255, 153, 0, 0.1);
            border: 1px solid rgba(255, 153, 0, 0.3);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1.5rem;
        ">
            <p style="margin: 0; color: #ff9900;">
                🔓 <strong>Admin Access Unlocked</strong><br>
                No admin users configured. All admin features are accessible.
                Configure ADMIN_USERS in .env to enable authentication.
            </p>
        </div>
        ''', unsafe_allow_html=True)
    
    # Check authentication status
    is_admin = check_admin_access(session_state)
    
    # If not admin, show login
    if not is_admin:
        st.markdown("### 🔐 Admin Login Required")
        render_auth_section(session_state)
        st.warning("Please log in to access admin features.")
        return
    
    # Show admin authenticated state
    render_session_info(session_state)
    
    # Create tabs for admin sections
    tab_overview, tab_data, tab_schedule, tab_history, tab_settings = st.tabs([
        "📊 Overview",
        "📥 Data Management",
        "⏰ Scheduling",
        "📋 Execution History",
        "⚙️ Settings"
    ])
    
    # Tab 1: Overview
    with tab_overview:
        render_overview_tab(session_state)
    
    # Tab 2: Data Management
    with tab_data:
        render_data_management_tab(session_state)
    
    # Tab 3: Scheduling
    with tab_schedule:
        render_scheduling_tab(session_state)
    
    # Tab 4: Execution History
    with tab_history:
        render_history_tab(session_state)
    
    # Tab 5: Settings
    with tab_settings:
        render_settings_tab(session_state)


def render_overview_tab(session_state=None) -> None:
    """Render the admin overview tab.
    
    Args:
        session_state: Streamlit session state
    """
    # System Status
    st.markdown("#### 🔍 System Status")
    
    col1, col2 = st.columns(2)
    
    with col1:
        render_etl_status_summary(session_state)
    
    with col2:
        render_scheduler_status_card(session_state)
    
    st.markdown("---")
    
    # Data Freshness
    st.markdown("#### 📈 Data Freshness")
    
    # Get freshness for each service
    services = ['RDS', 'EC2', 'EBS']
    cols = st.columns(len(services))
    
    for idx, service in enumerate(services):
        with cols[idx]:
            freshness = get_data_freshness(service)
            
            if freshness:
                last_updated = freshness.get('last_updated', 'N/A')
                records = freshness.get('records_count', 0)
                
                st.metric(f"{service}", f"{records:,} records", last_updated)
            else:
                st.metric(f"{service}", "No data", "Never")


def render_data_management_tab(session_state=None) -> None:
    """Render the data management tab with ETL controls.
    
    Args:
        session_state: Streamlit session state
    """
    # Environment selector
    aws_env = session_state.get('aws_environment', 'Default')
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        selected_env = st.selectbox(
            "AWS Environment",
            options=['Default', 'Green', 'Red'],
            index=['Default', 'Green', 'Red'].index(aws_env) if aws_env in ['Default', 'Green', 'Red'] else 0,
            key="admin_aws_env_selector"
        )
        session_state['aws_environment'] = selected_env
    
    with col2:
        st.markdown("<br/>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", help="Refresh environment"):
            st.rerun()
    
    # Render ETL controls
    render_etl_controls(aws_environment=selected_env, session_state=session_state)
    
    # Data Export Section
    st.markdown("---")
    st.markdown("### 📥 Export Data")
    
    # Get data from database for export
    try:
        from etl.data_provider import ETLDataProvider
        from core.config import Config
        
        config = Config()
        provider = ETLDataProvider(db_path=config.ETL_DB_PATH, database_url=config.DATABASE_URL)
        
        # Service selector for export
        export_service = st.selectbox(
            "Select Service to Export",
            options=['RDS', 'EC2', 'EBS'],
            key="export_service_selector"
        )
        
        # Fetch data from raw_instances table filtered by service_type
        data = provider.fetch_all(
            "SELECT * FROM raw_instances WHERE UPPER(service_type) = UPPER(:service_type)",
            {"service_type": export_service}
        )
        
        if data:
            # Use Export Controller to render export UI
            export_controller = ExportController()
            export_controller.render_export_ui(
                data=data,
                title=f"{export_service} Export",
                key=f"export_{export_service.lower()}"
            )
        else:
            st.info(f"No {export_service} data available. Run ETL to populate data.")
            
    except Exception as e:
        st.error(f"Error loading data for export: {str(e)}")


def render_scheduling_tab(session_state=None) -> None:
    """Render the scheduling tab.
    
    Args:
        session_state: Streamlit session state
    """
    render_scheduler_settings(session_state)


def render_history_tab(session_state=None) -> None:
    """Render the execution history tab.
    
    Args:
        session_state: Streamlit session state
    """
    # Metrics
    render_etl_metrics(session_state)
    
    st.markdown("---")
    
    # History table
    render_etl_history(limit=50, session_state=session_state)


def render_settings_tab(session_state=None) -> None:
    """Render the settings tab.
    
    Args:
        session_state: Streamlit session state
    """
    # Authentication settings
    st.markdown("### 🔐 Authentication")
    
    # Render auth section for password management
    render_auth_section(session_state)
    
    st.markdown("---")
    
    # Admin users info
    st.markdown("### 👥 Configured Admin Users")
    
    auth = get_auth_manager()
    users = auth.users
    
    if users:
        for username in users.keys():
            st.write(f"• {username}")
    else:
        st.info("No admin users configured")
    
    st.caption("Add admin users by setting ADMIN_USERS in .env file")
    
    st.markdown("---")
    
    # Session settings
    st.markdown("### ⏱️ Session Settings")
    
    timeout = auth.session_timeout_minutes
    st.metric("Session Timeout", f"{timeout} minutes")
    
    st.markdown("---")
    
    # Environment info
    st.markdown("### 🌐 AWS Environments")
    
    env_info = [
        ("Default", "Primary AWS account"),
        ("Green", "Development/Staging account"),
        ("Red", "Production account")
    ]
    
    for env, desc in env_info:
        st.markdown(f"**{env}**: {desc}")


# Additional utility functions

def render_admin_sidebar(session_state=None) -> bool:
    """Render admin section in sidebar (for backward compatibility).
    
    Args:
        session_state: Streamlit session state
        
    Returns:
        True if admin is authenticated
    """
    if session_state is None:
        session_state = st.session_state
    
    # Render auth section
    is_authenticated = render_auth_section(session_state)
    
    if is_authenticated:
        # Show admin features in sidebar
        st.markdown("---")
        st.markdown("### ⚙️ Admin")
        
        # Quick links to admin page
        st.page_link("Admin", icon="⚙️")
    
    return is_authenticated


def get_admin_status(session_state=None) -> dict:
    """Get comprehensive admin status.
    
    Args:
        session_state: Streamlit session state
        
    Returns:
        Dictionary with admin status information
    """
    if session_state is None:
        session_state = st.session_state
    
    auth = get_auth_manager()
    is_authenticated = check_admin_access(session_state)
    scheduler_status = get_scheduler_status()
    
    return {
        'is_authenticated': is_authenticated,
        'has_admin_users': has_admin_users_configured(),
        'username': session_state.get('auth_user'),
        'scheduler_enabled': scheduler_status['enabled'],
        'schedule_time': scheduler_status['schedule_time']
    }